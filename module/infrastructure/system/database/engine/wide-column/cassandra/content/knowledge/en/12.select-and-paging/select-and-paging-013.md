# Page Size, Rows Returned, and Mutating Data in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Cassandra's page size**, **actual rows returned in a page**, `LIMIT`, and the UI page size exposed by an API.
2. Explain why a page containing fewer rows than `fetch size` does not necessarily mean data is exhausted.
3. Use `paging state` and the `hasMorePages()` signal properly, even when a page has very few or zero matching rows.
4. Analyze the effects of **`INSERT`, `DELETE`, `UPDATE`, TTLs, and replica divergence** while a client pages through results.
5. Distinguish protocol-level paging from **keyset pagination** on clustering keys and `asOf` time bounds.
6. Design Java APIs that avoid skipping unprocessed rows, prevent applying tokens to the wrong query/tenant, and keep page size from hiding unbounded scans.
7. Build reproducible tests with concurrent data mutations, measure performance, and state the exact guarantees an application can accurately promise.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Apache Cassandra is a distributed wide-column database: the partition key routes queries to partitions and replicas, clustering columns order rows within partitions, and replication, consistency, TTLs, compaction, and repair govern what each read observes. Consequently, paging is not merely a UI problem of "20 rows at a time"—it is **a sequence of reads over data that can mutate between calls**.

## 1. One Display Page Does Not Equal One Cassandra Page

Suppose an activity history screen displays **20 events at a time**. At least four quantities are involved:

| Concept | Decided by | Meaning |
| --- | --- | --- |
| **Page size / fetch size** | Java Driver, e.g. `setPageSize(20)` | **Target** row count for one native-protocol fetch. |
| **Actual rows received in page** | Cassandra/driver per fetch | Can differ from the requested page size. |
| **`LIMIT 100`** | CQL statement | Ceiling on total rows **the entire query** may return. |
| **20 items on a UI page** | HTTP contract and app logic | Items presented to users, which may need buffering beyond protocol page boundaries. |

Example:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?
LIMIT 100;
```

With `setPageSize(20)`, if 63 rows match, the client can receive consecutive pages totaling **63 rows**, not just 20. `LIMIT 100` does not force the server to produce 100 rows, nor does it mean **each** page holds 100 rows.

**Page size is treated as a target/hint, not an exact row-count contract**. The server can return fewer rows than requested due to execution mechanics, filtering, response byte caps, or data layout. The row count in one page and the signal indicating **more pages remain** must be evaluated separately.

> Key rule: when using Java Driver `AsyncResultSet`, **`hasMorePages()` is the continuation signal**, not checking `currentPage().size() < pageSize`.

## 2. How Paging Works in a Distributed Query

Visualize a query targeting a full partition key:

```text
HTTP Client
    |
    | GET /accounts/A/events?day=2026-11-20
    v
Java API / Cassandra Java Driver
    |
    | CQL + bound values + page size
    v
Coordinator --------> Replica(s) by token and consistency
    |                         |
    |                         +-- memtable / SSTable
    |                         +-- TTL / tombstones / reconciliation
    |                         +-- clustering order
    v
Page 1: Rows + opaque paging state S1
    |
    | resume with same query + S1
    v
Page 2: Rows + paging state S2 or end of results
    |
    v
...
```

Page size helps **reduce rows and bytes transferred in a single fetch**, not replace key-based predicates. If a query omits the partition key or uses `ALLOW FILTERING` across many partitions, splitting the response into small pages **does not eliminate wide-scan costs**.

A paging state is a continuation position managed by Cassandra/driver for a **specific query**. It is not a table snapshot, not an editable offset, and not the partition key of the last row.

### 2.1. Three Distinct Cost Layers

| Metric | Question it answers | What typically controls it |
| --- | --- | --- |
| Candidate partitions | How many partitions must be searched? | `WHERE` on full partition key, finite `IN` list |
| Rows/values inspected | How much data is processed to find valid rows? | Clustering range, TTLs, tombstones, filtering, SSTables |
| Rows/bytes sent per page | How much data does the client receive in this chunk? | Projection, page size, server execution limits |

Never estimate read cost as `pageSize × pageCount` and assume that equals the physical cells Cassandra read. Returned row counts exclude tombstones and rows filtered out by predicates.

## 3. CQL Lab: Enough Data to See Three Pages

### 3.1. Creating the Keyspace and Table

Suppose an application stores activity for **one account per day**, including events sharing a timestamp with different IDs.

```sql
-- SimpleStrategy/RF=1 is for a single-node lab only;
-- multi-node production uses a replication strategy suited to topology.
CREATE KEYSPACE IF NOT EXISTS cassandra_page_mutation_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_page_mutation_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

| Component | Role | Meaning during paging |
| --- | --- | --- |
| `(account_id, event_day)` | Composite partition key | One day for one account is one partition. |
| `occurred_at` | First clustering column | Traverses time from newest to oldest. |
| `event_id` | Second clustering column | Provides deterministic ordering for same-timestamp events. |
| `event_type`, `summary` | Regular columns | Hold display content; do not govern position. |

### 3.2. Loading Seven Events into the Primary Partition

```sql
-- Account A, Nov 20: 7 rows.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed product'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened details'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Paid'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'SHIP', 'Shipped'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'DELIVER', 'Delivered'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Logged out'
);

-- Account A, day 21: second partition with 2 rows.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'Next day'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 10:00:00+0000',
    00000000-0000-4000-8000-000000000009,
    'VIEW', 'Viewed report'
);

-- Account B, day 20: third partition with 1 row.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000010,
    'LOGIN', 'Account B'
);
```

In a fresh table containing only the sample data, there are **10 rows across three partitions**. The primary partition for account A / day 20 has **seven rows** in default order:

| Position | UTC Time | `event_id` (suffix) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 14:00 | `...0007` | `LOGOUT` |
| 2 | 13:00 | `...0006` | `DELIVER` |
| 3 | 12:00 | `...0005` | `SHIP` |
| 4 | 10:00 | `...0004` | `PAY` |
| 5 | 10:00 | `...0003` | `CLICK` |
| 6 | 09:00 | `...0002` | `VIEW` |
| 7 | 08:00 | `...0001` | `LOGIN` |

The two events at 10:00 are disambiguated by `event_id`. Re-running `INSERT` on the same full primary key performs an upsert without duplicating rows. The mutations practiced in later sections will diverge results from this initial baseline table.

## 4. Does Page Size 3 Always Mean Three Rows per Page?

### 4.1. Testing in cqlsh

```sql
USE cassandra_page_mutation_lab;

-- cqlsh display control command, not SELECT syntax.
PAGING 3;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC;

PAGING OFF;
```

In an **idealized trace**, if the server returns three rows for each full page:

```text
Page 1: 14:00/0007, 13:00/0006, 12:00/0005
Page 2: 10:00/0004, 10:00/0003, 09:00/0002
Page 3: 08:00/0001
           |
           +-- end of results
```

This diagram helps track lab data—it is **not a native protocol guarantee of a 3/3/1 split**. The driver/server can return counts differing from the target size. Clients must process the actual rows received and check whether paging state remains.

### 4.2. Distinguishing "Full N Rows," "Fewer Than N," and "End of Data"

Assume `pageSize = 3`. A page can exhibit:

| Rows received in page | `hasMorePages()` | How to handle |
| ---: | --- | --- |
| 3 | `true` | Process all three; allow fetching next page. |
| 2 | `true` | **More pages still remain**; do not assume completion. |
| 1 | `false` | Final page in this read sequence. |
| 0 | `true` | Empty page yet **more data may exist**; handle with bounded fetch policy. |
| 0 | `false` | Done, no more pages. |

Empty pages that still carry paging state can occur in complex execution paths such as filtering or dense tombstones. It is **not a regular property** of a simple 7-live-row lab.

**Avoid this buggy rule:**

```java
// WRONG: a page's size does not prove the entire query is exhausted.
if (items.size() < requestedPageSize) {
    return "NO_MORE_DATA";
}
```

Instead, when driving pagination with `AsyncResultSet`, inspect `hasMorePages()` and its paging state after **consuming the entire current page**.

## 5. LIMIT, PER PARTITION LIMIT, and Actual Rows Returned

### 5.1. LIMIT Caps the Whole SELECT Statement

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 5;
```

On the baseline data, this returns at most **five rows**: `0007, 0006, 0005, 0004, 0003`. With target page size 3, an ideal split is **3 + 2**, though you should rely only on the total limit and actual end-of-results signal rather than assuming a fixed split.

If `LIMIT 20` runs on a partition with only seven rows, the query still returns **seven rows**, not twenty.

A common pitfall when building HTTP APIs: if CQL specifies `LIMIT 5`, resuming the **same query** via paging state does not allow the next HTTP page to return another five rows beyond the overall cap. To serve "up to five items per HTTP page" across multiple requests, design query semantics accordingly—never confuse query-wide `LIMIT` with per-network-page size.

### 5.2. PER PARTITION LIMIT Across Multiple Partitions

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2;
```

On the baseline data, both partitions (day 20 and day 21) contribute at most two rows each, totaling **four rows**:

| Partition | Retained rows |
| --- | --- |
| Account A / day 20 | `14:00/0007` and `13:00/0006` |
| Account A / day 21 | `10:00/0009` and `09:00/0008` |

**This is not global chronological ordering**, nor does a network page correspond one-to-one with a partition. The per-partition limit applies across the entire CQL result set, rather than "resetting on every page fetch."

Combined:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2
LIMIT 3;
```

no partition contributes more than two rows and **total output is at most three rows**; you cannot assert which day the third row belongs to unless the query carries an appropriate global ordering contract.

### 5.3. Page Count Can Only Be Estimated Under Assumptions

Assuming zero writes/deletes, no filtering, `R` result rows, and every page (except the last) returning strictly `F` rows:

```text
Ideal page count P = ceil(R / F)

R = 7, F = 3  ->  P = ceil(7/3) = 3
R = 5, F = 3  ->  P = ceil(5/3) = 2
```

This is **not a guaranteed API page-count formula**. With mutating data and hint-based page sizes, total `R` can shift between fetches, and page count depends on server framing.

Never run a full-table `COUNT(*)` just to render "Total 123,456 pages": in distributed Cassandra, counting can be prohibitively expensive and still does not give a snapshot matching subsequent page reads.

## 6. Data Mutating During Pagination: Four Scenarios

Suppose at time `T0`, the client fetched page 1:

```text
Page 1 at T0:
  14:00/0007 (LOGOUT)
  13:00/0006 (DELIVER)
  12:00/0005 (SHIP)

State S1: continuation position after page 1
```

Later at `T1`, the client sends a request with `S1`. Between `T0` and `T1`, several mutations may have occurred.

### 6.1. INSERT a New Row Ordered *Ahead* of the Traversed Position

```sql
-- Lab illustration after fetching page 1.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 15:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'REVIEW', 'Newly arrived'
);
```

Because clustering order is descending, the `15:00` row sits **ahead** of `14:00`. A fresh query from the start sees it first, whereas an ongoing paging chain that already passed the head of the list has **no guarantee** of doubling back to pick up that new row.

**Consequence:** "scrolling to the end via Load More" does not mean the user saw every event created while they were browsing. To see brand-new events, clients usually refresh from the top or subscribe to a separate live feed.

### 6.2. INSERT a Row into the *Unread* Region

```sql
-- A late-arriving event with timestamp between 12:00 and 10:00.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000012,
    'BACKFILL', 'Late-arriving event'
);
```

The `11:00` row falls inside the portion the paging sequence is about to read. **It may appear on the next page**, depending on the exact continuation position, replica visibility, and fetch timing. No fixed snapshot guarantees results match **the table at T0**.

This also means "pinning a day" with `event_day = '2026-11-20'` does **not** prevent late writes into that same day.

### 6.3. DELETE an Unread Row

```sql
-- Delete a row by full primary key in the lab.
DELETE FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000004;
```

Once the delete is visible, `PAY/0004` will no longer appear on the next page. That page may be shorter, or subsequent rows may shift up into the returned page. Never assume page 2 always contains the fixed trio `0004, 0003, 0002`.

Deleting in Cassandra writes tombstones; before compaction, reads must process those deletion markers. **Fewer live rows does not necessarily mean proportionally less disk I/O.**

### 6.4. UPDATE a Regular Column or Change the Sort Key

```sql
-- Update a regular column of an unread row.
UPDATE events_by_account_day
SET summary = 'Updated description'
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

The key columns of `VIEW/0002` stay unchanged, yet the `summary` received on the later page reflects the new value rather than the value at `T0`.

If you need to "change the timestamp" (a clustering column), Cassandra **cannot update a primary key in place** to reposition the same row. The application must insert a row at the new key and delete the old one; from a pagination perspective, that **changes both the row set and ordering**, which can violate expectations if the API lacks an ID/version policy.

### 6.5. Summary Table of Scenarios

| Mutation after page 1 | What can happen on subsequent pages | Guarantee you must NOT promise |
| --- | --- | --- |
| INSERT row newer than all seen rows | New row does not appear in remaining pages | "Paging forward sees every newly inserted item." |
| Late INSERT into unread region | New row may appear in the next result set | "Later pages only reflect data from T0." |
| DELETE unread row | Row disappears or page item counts shift | "Next page always holds three expected IDs." |
| UPDATE regular column | Returned value may reflect the newer version | "Consistent data snapshot across all pages." |
| TTL expiration | Row/cell drops out under the newer state | "Page size guarantees N live rows." |
| Replicas converging at different times | Separate reads can observe different states | "Same query reads consistently at one cluster-wide instant." |

**Conclusion:** paging state **resumes traversal**, it does not freeze database contents.

## 7. TTLs, Tombstones, and Why a Page Can Be Very Short

### 7.1. TTL-Expired Rows and Tombstones

In Cassandra, TTLs expire data and deletes create tombstones. The server must evaluate those markers to return only valid live rows and values.

Conceptual illustration:

```text
Partition / clustering slice has 50 positions or data versions
   |
   +-- 42 records/values expired, deleted, or shadowed by tombstones
   +-- 8 live rows matching the query
   |
   v
Response contains at most 8 useful rows from this slice
```

This is an **illustrative diagram**, not an internal guarantee that "50 positions always produce 8 rows." In practice, the storage engine may inspect many cells/SSTables to find live rows; a page returning very few rows can still be slow or trigger tombstone warnings.

Never assume:

```text
Rows returned = 3
=> Cassandra read only 3 rows from disk        (false)
=> Guaranteed to have reached the end          (false)
```

To know whether more pages exist, inspect paging state. To know read cost, inspect metrics/tracing—not returned row count.

### 7.2. Filtering and Empty Pages

When a query filters on a regular column using `ALLOW FILTERING`, many candidate rows can be discarded before emitting any result rows. Depending on version and execution path, a page can arrive with **zero matching rows yet still carry paging state**.

Therefore, async code should enforce a clear policy:

1. Process every row in `currentPage()`, even when empty.
2. Check `hasMorePages()` to detect continuation.
3. Fetch the next page only if the endpoint/job still needs data and **remains within time, page, byte, and request budgets**.
4. If consecutive empty pages occur from an overly broad filter, **never loop infinitely**; stop at the budget limit and revisit the schema/query.

Better yet, design queries around partition keys and clustering ranges to avoid relying on broad filtering paths.

### 7.3. Compaction and Repair Do Not Create Snapshots

Compaction reorganizes SSTables and purges deleted data once safe; repair reconciles replicas. Both affect read amplification and visible state, yet **neither turns a paginated `SELECT` sequence into a transactional snapshot**.

While compaction/repair runs or when a replica lags, tail latency across pages can vary widely. Do not try to optimize solely by "setting page size to 1" and expecting queries to stay cheap.

## 8. Replication, Consistency, and Visibility Timing

Assume a production cluster uses an appropriate replication factor, such as three replicas in one datacenter. Each page is **an independent read** subject to the query's consistency level; a multi-page sequence is not automatically a single read transaction.

- `LOCAL_ONE` requires responses from fewer replicas and can observe unconverged data.
- `LOCAL_QUORUM` requires more local-datacenter replicas depending on RF and health, trading off latency/availability for stronger read guarantees.
- Even using `LOCAL_QUORUM` on every request **does not create a multi-page snapshot** when concurrent writes or deletes happen.
- Compatible write/read consistency levels provide stronger per-operation guarantees in Cassandra's model, which is still distinct from **history-wide snapshot isolation**.

For example, page 1 might read before an update reaches a replica, while page 2 reads after one or more replicas receive that update. Keeping the same query string and paging state does not force two pages to see the same data version.

**Do not multiply row counts by the replication factor.** Three replicas of one partition store copies of the same logical data; `LIMIT` and page size operate on logical result rows, not "one copy per replica."

## 9. Paging State: What Must Stay Identical?

Paging state is an **opaque** value used to continue **the exact same query**. In the Java Driver, especially across HTTP requests, preserve:

| Attribute | When resuming via paging state |
| --- | --- |
| CQL statement / `SELECT` expression | Keep identical (including projection, `WHERE`, `ORDER BY`, and `LIMIT` if present). |
| Bind values | Keep identical `account_id`, `event_day`, time bounds, and all other parameters. |
| Authorization | Re-verify that the caller is permitted to read the account/tenant. |
| State format | Use the driver's paging state API; never craft or guess bytes. |
| Page size | Keep a consistent policy when resuming; arbitrary changes cause unpredictable behavior. |
| Query version | Track schema/API changes and token lifetimes. |

**Never reuse paging state between two requests targeting different data.** For example, a token from account A / day 20 must never be used for account B / day 20 or for account A / day 21; a token from `SELECT event_type` must never be used for `SELECT event_type, summary`.

### 9.1. Next-Page State Is Not a Mid-Page Resume Marker

Imagine an actual protocol page carrying three rows:

```text
Current page:
    row A
    row B
    row C

Paging state S_next -> next page, positioned AFTER the current page
```

If Java consumes only `row A` and sends `S_next` to the client, the next request **drops `row B` and `row C`**. That is an application bug, not a Cassandra pagination flaw.

Rules:

- Process or return **the entire current page** before issuing the next-page token.
- If an API caps items at `N` while the server returns more than `N` in one protocol page, **buffer** the overflow in an application-managed cursor or use a different strategy—never silently discard excess rows and emit the next-page state.
- An alternative is a clustering-key **keyset cursor**, which controls displayed row counts independently of protocol pages.

### 9.2. Paging State Is Not a Security Token

In Java Driver 4.x, APIs like `PagingState.fromString(...)`, `PagingState.toString()`, and `ExecutionInfo.getSafePagingState()` exist. "Safe" validates query/bind-value matching; it **does not mean cryptographically signed or safe for clients to inspect, alter, or share**.

When exposing tokens over HTTP:

1. Authenticate and authorize the user before querying Cassandra.
2. Protect tokens with **HMAC or authenticated encryption (AEAD)**, or store state server-side and return a short-lived reference ID.
3. Bind tenant/account, date, query version, expiration, and API page-size policies inside the token.
4. Cap token length; reject invalid signatures, malformed encodings, or query mismatches with controlled client errors instead of retrying indefinitely.
5. Avoid logging raw tokens in access logs or telemetry unless necessary.

Never equate successfully parsing a paging state with **authorization to view the underlying data**.

## 10. How Can You Reduce Drift Between Pages?

No single flag turns paging state into a snapshot, yet certain strategies **narrow the window of drift**.

### 10.1. Pinning a Time Ceiling (as-of)

Suppose the initial request fixes `asOf = 2026-11-20T15:00:00Z`. Every page applies the same predicate:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at < '2026-11-20 15:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

If a truly new event arrives later at `16:00`, it **falls outside `WHERE`** on every page, anchoring the list to a time window. Subsequent requests must preserve that exact `asOf` bound.

However:

- A **late-arriving write timestamped `11:00`** still enters the dataset because it is below `asOf`.
- Deletes, updates, TTL expirations, and unconverged replicas can still alter pages.
- `asOf` is only a **query window**, **not a transactional snapshot**.

If the product requires "an exact report as of T0," use dedicated mechanisms such as snapshots/exports, immutable event logs, CDC, or reconciliation rather than relying solely on paging state.

### 10.2. Clustering-Key Keyset Cursor

On a table with `CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)`, page 1:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

On the baseline data, the last row of page 1 is `(12:00, ...0005)`. To fetch subsequent rows in descending order:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 12:00:00+0000',
      00000000-0000-4000-8000-000000000005
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

On baseline data, the next page is `PAY/0004`, `CLICK/0003`, `VIEW/0002`. When mutations occur between requests, the row set can still change, yet the application **explicitly controls key boundaries** instead of relying on an opaque state.

**Why must the cursor include `event_id`?** `PAY/0004` and `CLICK/0003` share the 10:00 timestamp. If a page ends at `PAY/0004` and the next query uses only `occurred_at < 10:00`, `CLICK/0003` is skipped. A tuple boundary positions accurately on the **complete clustering key**.

### 10.3. Paging State and Keyset Cursors Have Different Strengths

| Criterion | Paging state | Keyset cursor |
| --- | --- | --- |
| Resuming the exact same CQL query | Ideal | Replaces `WHERE` with a new key boundary |
| Fixed UI item count | Not guaranteed by page size alone | Easy to set `LIMIT N` per query (still subject to live data drift) |
| Visible boundary | Opaque | Last returned clustering key tuple |
| Random jump to page N | Not directly supported | Also unsupported without precomputed boundaries |
| Data mutating between requests | No snapshot | No snapshot |
| CQL constraints | Query and bind values must stay identical | Clustering keys and comparison direction must be valid |
| HTTP token | Must protect state | Must also protect cursor/tenant/asOf |

Never mix an old paging state with a `WHERE` clause rewritten to a new tuple boundary: it is no longer the same query.

## 11. Java Driver 4.x: Reading Actual Row Counts of a Page

Examples below use **Java 17** and **Apache Cassandra Java Driver 4.x**. Assume an active `CqlSession session` connected to `cassandra_page_mutation_lab`.

### 11.1. Avoiding Draining All Pages When You Only Want One HTTP Page

```java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    """);

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");
BoundStatement bound = prepared.bind(accountId, day)
    .setPageSize(3);

ResultSet result = session.execute(bound);

// This loop is NOT limited to one protocol page:
// once the current page ends, synchronous ResultSet may fetch further.
for (Row row : result) {
    System.out.println(row.getString("event_type"));
}
```

On the baseline data, this loop prints **all seven events**. In an HTTP endpoint expecting a single page, never use a synchronous loop like this without controlling fetch boundaries.

### 11.2. AsyncResultSet.currentPage() Iterates Only Over the Current Page

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> firstFuture =
    session.executeAsync(bound);

CompletionStage<Void> displayFirstPage = firstFuture.thenAccept(page -> {
    int actualRows = 0;
    for (Row row : page.currentPage()) {
        actualRows++;
        System.out.println(row.getString("event_type"));
    }
    System.out.println("Actual rows in page: " + actualRows);
    System.out.println("Has more pages: " + page.hasMorePages());
});
```

This counts **the actual rows returned in the current page**. It does **not** assume `actualRows` equals 3, and never fetches the next page unless the application calls `fetchNextPage()` or starts a new request with the saved state.

### 11.3. A Function Returning an HTTP Page and Next State

The sample below returns **the entire current protocol page**, rather than trying to force "every HTTP page always holds three items." HTTP token protection belongs in the service/gateway layer; this snippet is **not safe to accept raw tokens from untrusted clients**.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

record EventItem(Instant occurredAt, UUID eventId,
                 String eventType, String summary) {}

record EventPage(List<EventItem> items, String nextPageState,
                 int actualRows) {}

static CompletionStage<EventPage> fetchOneProtocolPage(
        CqlSession session,
        PreparedStatement query,
        UUID accountId,
        LocalDate day,
        String verifiedDriverState) {

    BoundStatement stmt = query.bind(accountId, day)
        .setPageSize(3);

    if (verifiedDriverState != null && !verifiedDriverState.isBlank()) {
        // Only accept state ALREADY verified and decoded at the API layer.
        PagingState state = PagingState.fromString(verifiedDriverState);
        stmt = stmt.setPagingState(state);
    }

    return session.executeAsync(stmt).thenApply(page -> {
        List<EventItem> items = new ArrayList<>();
        for (Row row : page.currentPage()) {
            items.add(new EventItem(
                row.getInstant("occurred_at"),
                row.getUuid("event_id"),
                row.getString("event_type"),
                row.getString("summary")
            ));
        }

        PagingState next = page.hasMorePages()
            ? page.getExecutionInfo().getSafePagingState()
            : null;

        String stateForNext = next == null ? null : next.toString();
        return new EventPage(
            List.copyOf(items), stateForNext, items.size()
        );
    });
}
```

**Proper production usage:**

1. `verifiedDriverState` must be extracted from an **authenticated API token**, not raw untrusted query parameters.
2. Reuse the **exact same prepared query and bind values** on the next request.
3. Iterate through **all of `currentPage()`** before emitting the next state.
4. Use `actualRows` for metrics and UI rendering—**never to decide whether data is exhausted**.
5. When `page.hasMorePages() == false`, `nextPageState` is null.
6. If `actualRows = 0` while state remains, continue only within UX/budget bounds—never spin in an unbounded HTTP loop.
7. If a UI page strictly requires at most N items when protocol pages vary, buffer/cursor cleanly at exact item boundaries; never slice `items` while returning a state that points past the **entire protocol page**.

### 11.4. Explicitly Fetching the Next Page

```java
session.executeAsync(bound).thenCompose(first -> {
    if (first.hasMorePages()) {
        return first.fetchNextPage();
    }
    return java.util.concurrent.CompletableFuture.completedFuture(first);
}).thenAccept(page -> {
    // page here is the next page if one existed, otherwise the first page.
    for (Row row : page.currentPage()) {
        System.out.println(row.getUuid("event_id"));
    }
});
```

This snippet merely demonstrates `fetchNextPage()`. If an application needs to process **both the first and subsequent pages**, process the first page **before** requesting the next; do not treat the code above as emitting both pages.

## 12. Designing HTTP Contracts When Page Row Counts Vary

A "Load more" API can return:

```json
{
  "items": [
    {
      "occurredAt": "2026-11-20T14:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000007",
      "eventType": "LOGOUT"
    },
    {
      "occurredAt": "2026-11-20T13:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000006",
      "eventType": "DELIVER"
    }
  ],
  "actualCount": 2,
  "hasMore": true,
  "nextPageToken": "<opaque-protected-application-token>"
}
```

This is solely an **example response structure**, not a real paging token or a promise that lab data splits into two rows. **`hasMore` must come from actual continuation state**, not from `actualCount < requestedPageSize`.

### 12.1. Three Contract Options

| Option | Approach | Trade-off |
| --- | --- | --- |
| **One protocol page per HTTP response** | Return all of `currentPage()` plus next state. | Simple, though item counts can vary. |
| **Fixed max N UI items with buffering** | If a protocol page exceeds N, store leftover rows plus state in a server-side cursor. | Controls exact item count; adds API state/TTL/storage complexity. |
| **Keyset cursor + `LIMIT N`** | Each HTTP request queries from the next key boundary. | Requires custom key boundary logic; still no snapshot. |

For simple history endpoints, the first option fits "Load more" buttons well. If UX mandates strictly N items per page (except the last), explicitly handle filtered rows, per-request fetch limits, and mutating data.

### 12.2. Budgets Against Unbounded Scanning

When an app wants to "collect 20 valid items" across multiple pages, enforce caps:

- Maximum **protocol pages** fetched in a single HTTP request?
- Maximum **milliseconds** and response bytes allowed?
- Are consecutive empty pages permitted?
- How many partitions in `WHERE`/`IN` and how many concurrent requests?
- When the budget runs out while state remains, does the API return **fewer items + continuation token** or another status?

Never keep fetching until 20 items are found at any cost; if matching items are sparse in a huge dataset, the request will scan broadly and time out. In that case, fix the table/index design or return smaller pages.

## 13. Measuring and Testing Against Mutating Data

### 13.1. A Reproducible Test Scenario

In a **lab environment**, run:

1. Create the keyspace/table and load the ten baseline rows from Section 3.
2. Query account A / day 20 with `pageSize = 3`; record **the actual IDs and states received**, without assuming a 3/3/1 split.
3. Before the next fetch, run **one** test mutation—for example, `INSERT` an event at 15:00.
4. Resume with the corresponding state, record IDs and row counts per page, and compare against a fresh query from the beginning.
5. Repeat on a **freshly reset lab** with a late write at 11:00, a `DELETE` of 10:00/id4, and an `UPDATE` to summary.
6. Repeat under relevant consistency levels if testing on a multi-replica cluster.
7. Never extrapolate from one run to claim all paging runs behave identically.

**Never run all sample `INSERT`/`DELETE` mutations together and then compare against the "baseline data" tables above**, because the table state has changed. Every experiment needs a clean initial state and clear mutation timestamps.

### 13.2. Metrics to Monitor

| Metric | What it reveals |
| --- | --- |
| `requestedPageSize` and `actualRows` | Divergence between target and actual page sizes. |
| `hasMorePages`, empty-page rate | Whether clients might misread early completion. |
| Fetches per HTTP request | Whether endpoints are unintentionally draining multiple pages. |
| Page latency p50/p95/p99 | Whether specific pages lag due to storage, consistency, or load. |
| Bytes returned, row size, projection | Whether payloads should be trimmed further. |
| Tombstone warnings and read amplification | Whether excessive deleted/expired data is being scanned. |
| Timeout/`Unavailable`/retry counts | Impact of replicas, load, and backoff. |
| Candidate partitions, `IN` list length | Whether paging is masking a high fan-out query. |
| Invalid/expired/mismatched token counts | Health of API contracts and security validation. |

### 13.3. Handling Errors by Root Cause

- **`InvalidQuery`:** missing key predicates, invalid `ORDER BY`, or incompatible syntax; raising timeouts will not fix it.
- **Invalid/mismatched paging state:** token no longer matches query/bind values or is corrupted; reject cleanly and prompt restart from page 1 where appropriate.
- **Read timeout / `Unavailable`:** inspect consistency, replicas, load, partition size, and retry policy; never retry endlessly.
- **Slow page despite few rows:** check tombstones/TTLs, filtering, SSTable reads, and oversized columns.
- **Rows shifting between pages:** verify `INSERT`/`DELETE`/`UPDATE`/TTL timing, consistency, and API snapshot expectations.

## 14. Common Misconceptions

| Misconception | Reality | How to handle it |
| --- | --- | --- |
| "`pageSize(3)` always returns 3 rows per page." | Page size is a hint; actual count can differ. | Count actual rows and check `hasMorePages()`. |
| "A page with 2 rows means we are done." | Paging state may still remain. | Never derive `hasMore` from `items.size()`. |
| "An empty page cannot have a next page." | Filtering/tombstones can produce empty pages with continuation state. | Check state and enforce a fetch budget. |
| "`LIMIT 5` means 5 rows per HTTP page." | `LIMIT` caps **the entire CQL query**. | Separate global cap from page size. |
| "`PER PARTITION LIMIT 2` means 2 rows per page." | It caps **each partition** across the result set. | It does not reset per page. |
| "Iterating synchronous `ResultSet` with `setPageSize(3)` reads only page 1." | The iterator can auto-fetch every page. | Use `AsyncResultSet.currentPage()` or control fetches explicitly. |
| "Once I have state from a page, I only need to process the first row." | State points to the **next page**, risking dropped leftovers. | Process the whole page or buffer remaining items. |
| "Inserting a 15:00 row guarantees it shows up on the next page." | It sits ahead of the already-traversed position. | Refresh the list or use a live-update stream. |
| "Late `INSERT`s are always excluded from active pagination." | They can land inside the unread region. | Define `asOf` bounds and document non-snapshot behavior. |
| "Keeping `WHERE` identical creates a snapshot." | Concurrent writes/deletes/TTLs and replicas still evolve. | Build snapshot/CDC mechanisms if required. |
| "`LOCAL_QUORUM` turns multiple pages into one transaction." | Consistency is not snapshot isolation. | Separate per-read guarantees from multi-read snapshots. |
| "Timestamp alone suffices for a keyset cursor." | Timestamps can collide. | Use tuple `(occurred_at,event_id)`. |
| "Driver's safe token is already safe to expose publicly." | Safe wrapper does not replace cryptographic auth. | Sign/encrypt with scope and expiry. |
| "`LIMIT`/page size makes `ALLOW FILTERING` cheap." | It may still scan many rows before returning results. | Narrow the read path or design tables/indexes. |

## 15. Practice Exercises with Answers

### Exercise 1. Choosing the End-of-Data Signal

**Question:** An API requests `pageSize = 3`. Java receives a page with **2 rows** and `hasMorePages() = true`. Should the API return `nextPageToken = null` because "fewer than three arrived"?

**Answer:** **No.** Fewer rows than page size does not prove data is exhausted. Since continuation state exists, return a token / `hasMore = true` so the client can continue per API policy.

### Exercise 2. Row Counts with LIMIT and Page Size

**Question:** On the baseline partition with seven events, a query has `LIMIT 5` and target page size `3`. What is the maximum total rows returned? Under an ideal full-page split, how many pages is that?

**Answer:** **Five** rows total. Ideally **two pages: 3 + 2**. Never treat that ideal split as a protocol guarantee across all Cassandra execution paths.

### Exercise 3. INSERT Ahead of the Cursor

**Question:** A client received `14:00/0007, 13:00/0006, 12:00/0005` and then a `15:00/0011` event is inserted. Is the next request guaranteed to see `15:00`?

**Answer:** **No.** The new row sits **ahead** of the already-scanned position in descending order. A fresh read from the start sees it, whereas continuing pagination is not guaranteed to revisit the top of the list.

### Exercise 4. DELETE and Subsequent Page Rows

**Question:** After page 1, `PAY/0004` is deleted. Must page 2 still contain `0004, 0003, 0002` as in the baseline data?

**Answer:** No. `0004` will no longer be returned once the next read observes the delete. Row count, contents, and page boundaries can shift. Paging state does not freeze data as of `T0`.

### Exercise 5. Why Not Discard Excess Rows in a Page?

**Question:** Cassandra returns a protocol page with 3 rows `A, B, C`; the UI takes only `A, B` yet the API returns the state pointing to the **next page**. What is wrong?

**Answer:** `C` was neither displayed nor saved, yet the state skips the **entire current page**. Either return all three rows, **buffer `C`** in an application cursor, or switch to a strategy like keyset pagination. Never drop `C` and treat the next-page state as resuming right after `B`.

### Exercise 6. Is as-of a Snapshot?

**Question:** Every request includes `AND occurred_at < '2026-11-20 15:00:00+0000'`. Later, the app writes a late-arriving event timestamped `11:00`. Does `asOf` guarantee excluding that new write?

**Answer:** **No.** Although written later, the event's `11:00` timestamp still sits **below the `15:00` cutoff**. Timestamp `asOf` bounds the key window, **not** commit-time snapshot isolation. Consistent state as of `T0` requires a different mechanism.

### Exercise 7. Two Events Sharing a Timestamp

**Question:** A newest-first page ends at `10:00/0004`. Write the appropriate `WHERE` clause so `10:00/0003` is not skipped on the next page.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000004
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

A tuple boundary on the full clustering key ensures `10:00/0003` is returned; comparing only `occurred_at < 10:00` would skip it.

### Exercise 8. Mutating Data Under High Consistency

**Question:** Every page is read with `LOCAL_QUORUM` on a cluster with an appropriate RF. Can you claim "this is a snapshot of data as of page 1"?

**Answer:** **No.** `LOCAL_QUORUM` governs how many replicas must respond and per-read consistency guarantees in Cassandra's model; it **does not create snapshot isolation across multiple reads**. Writes, deletes, and TTL expirations can still occur between pages.

## 16. Checklist Before Deploying Pagination Over Mutating Data

1. **Partition:** Have you targeted a full partition key or finite partition list, avoiding wide scans masked by page size?
2. **Ordering:** Do clustering order and timestamp tie-breakers fit requirements, especially for keyset cursors?
3. **Counts:** Are page size, actual rows received, query-wide `LIMIT`, `PER PARTITION LIMIT`, and UI page size kept strictly distinct?
4. **Completion:** Do you check `hasMorePages()` / actual continuation state instead of comparing row count to page size?
5. **No dropped rows:** Is the **entire** protocol page consumed or buffered before returning the next-page token?
6. **Mutations:** Does the API document that rows can be added, deleted, updated, or TTL-expired between pages? Are `asOf`, keyset cursors, CDC, or snapshots needed?
7. **Consistency:** Is it understood that replication/consistency never turns multi-page reads into snapshot transactions?
8. **Token security:** Are tokens signed/encrypted or stored server-side, bound to principal/tenant, query version, expiry, bind values, and authorization checks?
9. **Budgets:** Are fetches per request, bytes, latency, concurrency, and consecutive empty pages capped?
10. **Observability:** Have rows/page, `hasMore`, p95/p99, tombstones, timeouts/retries, and byte sizes been measured on production-like data?
11. **Errors:** Are invalid states handled separately from query/timeout errors, preventing retry storms and cross-tenant token misuse?
12. **UX contract:** Does the UI accept variable-sized "Load more" batches, or must buffering/keysets enforce fixed counts?

**Remember:** In Cassandra, **page size is not a guaranteed row count** and **paging state is not a snapshot**. Rely on real continuation signals, consume full pages before issuing tokens, bound read scope in `WHERE`, and set accurate expectations when `INSERT`/`DELETE`/`TTL` mutations occur between reads. When an API needs stronger stability or explicit business boundaries, layer in `asOf` windows, keyset cursors, or dedicated snapshot/reconciliation pipelines.

## References

- [DataStax Java Driver 4.17 — Paging: synchronous, asynchronous, paging state](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
- [Java Driver 4.x — AsyncResultSet API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html)
- [Java Driver 4.x — PagingState API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/PagingState.html)
- [Apache Cassandra Documentation — SELECT, WHERE, LIMIT, PER PARTITION LIMIT, and ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
