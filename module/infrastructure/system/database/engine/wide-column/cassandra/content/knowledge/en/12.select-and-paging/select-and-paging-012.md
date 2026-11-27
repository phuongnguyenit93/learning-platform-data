# Paging with Paging State and Forward-Only Access in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Explain why Cassandra returns large `SELECT` results in **protocol pages** rather than pushing everything in a single response.
2. Distinguish **page size**, `LIMIT`, `PER PARTITION LIMIT`, and the number of records displayed on an API UI page.
3. Use `paging state` to **resume the exact same query** and understand its **forward-only** limitation.
4. Write Java Driver 4.x code in both styles: synchronous auto-fetching `ResultSet` and explicit page-by-page `AsyncResultSet`.
5. Build an API returning `nextPageToken` that preserves the query and bind values while avoiding dropped rows when a page is partially consumed.
6. Explain why paging state does not natively support "page 37," "previous page," or `OFFSET`, and when a keyset cursor is the better choice.
7. Design safely around concurrent data changes, TTLs, unconverged replicas, retries, multi-tenant access, and client-supplied tokens.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Apache Cassandra is a distributed wide-column database: the partition key determines data placement, clustering columns determine row order inside a partition, and replication and consistency govern read execution. Paging keeps Java applications from receiving an entire result set in one response, **yet it never fixes a query with a flawed access path or excessive partition fan-out**.

## 1. Why Paging Exists and Why Is It Called Forward-Only?

Suppose an account generates tens of thousands of events in a single day. An API needs to browse history, while the UI displays only about twenty rows at a time.

If you fetch everything at once:

```sql
-- Never return an entire large history in one HTTP request.
SELECT happened_at, event_id, event_type, summary
FROM event_history_by_user_day
WHERE user_id = ?
  AND event_day = ?;
```

The application would receive far more data than it can display, wasting bandwidth, memory, object mapping, and response latency. Cassandra's native protocol supports **paging**: the server returns results in chunks alongside continuation state whenever more data remains.

```text
Client / Java Driver                          Cassandra
        |                                         |
        |--- SELECT + page size 2 -------------->|
        |<-- rows of page 1 + paging state S1 ---|
        |                                        |
        |--- same SELECT + S1 ------------------>|
        |<-- rows of page 2 + paging state S2 ---|
        |                                        |
        |--- same SELECT + S2 ------------------>|
        |<-- page 3, no more data ---------------|
        |
        +--> nextPageToken = null
```

`Paging state` is an **opaque value**: the application **must not decode it to guess position**, compute `S2` from `S1`, or treat it as a row ID. It exists solely to **advance the current query forward**. To reach the next page, you must normally traverse preceding pages to obtain its state.

**Forward-only** means:

- You can fetch the **next page** from the current paging state.
- Cassandra does not emit a "step back one page" token for previous results.
- There is no efficient random access like "jump straight to page 37" from a page number alone.
- Applications can **store prior page tokens** to re-execute the query from previously visited points, though that is application-level token history rather than native backward paging.

This is a major departure from page-number pagination common in many relational SQL systems.

## 2. How Do Page Size, LIMIT, PER PARTITION LIMIT, and UI Pages Differ?

| Concept | Scope of effect | Not synonymous with |
| --- | --- | --- |
| **Page size** (e.g., `setPageSize(20)`) | Target rows returned per Cassandra **fetch round trip** | Total rows; partition count; row scan limit |
| **`LIMIT 100`** | At most 100 rows **across the entire CQL query** | 100 rows on **each** network page |
| **`PER PARTITION LIMIT 2`** | At most 2 rows **per selected partition** | 2 partitions or 2 rows total |
| **20-item UI page** | Application presentation policy | A protocol page always having exactly 20 rows |
| **Paging state** | Continuation position for **the same query** | `OFFSET`, page number, or business-key cursor |

Example:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = ?
  AND event_day = ?
ORDER BY happened_at DESC, event_id DESC
LIMIT 100;
```

If the Java Driver sets page size `20`, Cassandra returns results across multiple fetches, yet **total results never exceed `LIMIT 100`**. Conversely, if only 6 rows exist, the total is 6—the server never fabricates rows to reach 20 or 100.

**Page size is a hint**, not a hard guarantee that every response contains exactly N rows. The server may return slightly fewer or more rows due to protocol or execution conditions. Consequently, an API requiring "strictly 20 rows per UI page" needs its own **buffering, overfetching, or application-level cursor policy**; never assume each native protocol page has exact cardinality.

**Warning:** Raising `setPageSize` does not make a `WHERE` clause missing the partition key valid. Lowering page size does not fix `ALLOW FILTERING` or reading hundreds of partitions unnecessarily.

## 3. CQL Lab: One Partition with Six Events

### 3.1. Creating the Keyspace and Table

Suppose an application stores events **per user/day**, ordered newest first.

```sql
-- SimpleStrategy/RF=1 is for single-node lab use only.
CREATE KEYSPACE IF NOT EXISTS cassandra_paging_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_paging_lab;

CREATE TABLE IF NOT EXISTS event_history_by_user_day (
    user_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((user_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id DESC);
```

Key components:

| Component | Role | Paging impact |
| --- | --- | --- |
| `(user_id, event_day)` | Composite partition key | Scopes the query to one user/day partition. |
| `happened_at` | First clustering column | Traverses chronologically newest first. |
| `event_id` | Second clustering column | Disambiguates same-timestamp events for deterministic order. |
| `event_type`, `summary` | Regular columns | Display data; do not participate in tokens or key sorting. |

### 3.2. Loading Eight Rows, Six in the Primary Partition

```sql
-- User A, Nov 20: six events.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed list'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened details'
);

-- Two events at the same timestamp: never use timestamp alone as a cursor.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Paid'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'SHIP', 'Shipped'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGOUT', 'Logged out'
);

-- User A/day 21: another partition.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGIN', 'New day'
);

-- User B/day 20: third partition.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 08:30:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'User B'
);
```

The sample dataset has **8 rows across 3 partitions**. The main query for User A / day 20 retrieves **6 rows** in clustering order:

| Order | `happened_at` UTC | `event_id` (suffix) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 13:00 | `...0006` | `LOGOUT` |
| 2 | 12:00 | `...0005` | `SHIP` |
| 3 | 10:00 | `...0004` | `PAY` |
| 4 | 10:00 | `...0003` | `CLICK` |
| 5 | 09:00 | `...0002` | `VIEW` |
| 6 | 08:00 | `...0001` | `LOGIN` |

The two rows at `10:00` are distinguished by `event_id`. Re-running `INSERT` on the same full primary key performs an **upsert** without creating duplicate rows. Expected row counts hold only if the lab table has no extra data or concurrent writes/deletes.

## 4. Inspecting Pages in cqlsh: Tooling vs. CQL

`cqlsh` offers shell commands controlling page display and fetching, for example:

```sql
-- This is a cqlsh command, not CQL SELECT syntax.
PAGING 2;

SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC;

PAGING OFF;
```

With a target page size of two, pages **typically** appear as:

```text
Page 1: LOGOUT/0006, SHIP/0005
Page 2: PAY/0004, CLICK/0003
Page 3: VIEW/0002, LOGIN/0001
```

`PAGING` is a **cqlsh** shell feature, whereas `paging state` is protocol/driver state. Never confuse the terminal's "more" prompt with an API paging token managed by a Java application.

To fetch at most three rows **across the entire query**:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC
LIMIT 3;
```

`LIMIT 3` does not mean each page has three rows; it sets a ceiling on the **complete result set** of the `SELECT` statement.

## 5. Java Driver 4.x: Synchronous Auto-Fetching Pagination

Java Driver 4.x has two primary execution models:

- `session.execute(...)` returns a `ResultSet`. When a synchronous loop crosses a page boundary, the driver **automatically fetches the next page**. A loop that looks like it processes "one page" can accidentally read the entire history.
- `session.executeAsync(...)` returns a `CompletionStage<AsyncResultSet>`. `currentPage()` iterates strictly over rows of the **current page**, and `fetchNextPage()` must be called explicitly when needed.

### 5.1. Synchronous Loop: Convenient Yet Can Drain All Pages

Java 17 and Java Driver 4.x example, assuming an active `CqlSession session` connected to keyspace `cassandra_paging_lab`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare("""
    SELECT happened_at, event_id, event_type
    FROM event_history_by_user_day
    WHERE user_id = ?
      AND event_day = ?
    ORDER BY happened_at DESC, event_id DESC
    """);

UUID userId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

BoundStatement request = prepared.bind(userId, day)
    .setPageSize(2);

ResultSet rs = session.execute(request);
for (Row row : rs) {
    // When current page ends, the driver may automatically fetch the next page.
    System.out.printf("%s %s%n",
        row.getInstant("happened_at"),
        row.getString("event_type"));
}
```

The loop prints **all six rows**, even though `setPageSize(2)` is set. Page size is neither `LIMIT 2` nor a promise that the loop touches only one network response.

This pattern works well for small batch jobs that intend to consume every result, but should **not** be used as-is in an endpoint meant to return a single page and stop.

### 5.2. Reading Only Currently Available Rows Without Auto-Fetching

On a synchronous `ResultSet`, `getAvailableWithoutFetching()` tells you how many rows are **currently buffered** without fetching another page. To capture paging state at a page boundary, grab the state and consume the entire buffered page:

```java
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

ResultSet rs = session.execute(request);

// Save starting position of the NEXT PAGE.
PagingState next = rs.getExecutionInfo().getSafePagingState();

// Must consume the entire current page before using 'next'.
while (rs.getAvailableWithoutFetching() > 0) {
    Row row = rs.one();
    if (row == null) {
        break;
    }
    System.out.println(row.getUuid("event_id"));
}

String nextToken = next == null ? null : next.toString();
```

**Critical trap:** `getSafePagingState()` on execution info points to the **page after the current page**, not the last row the application consumed. If you capture that state and process only **one of two rows** in the current page, the next request starts on page 2 and **drops the remaining row**.

Managing synchronous boundaries via `getAvailableWithoutFetching()` also requires care around when `ExecutionInfo` is read and driver prefetch policies. When your goal is explicit page-by-page control, the asynchronous `AsyncResultSet` API expresses page boundaries much more cleanly.

## 6. Java Driver 4.x: Explicit Page-by-Page Control with AsyncResultSet

### 6.1. Processing Only currentPage()

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

BoundStatement bound = prepared.bind(userId, day)
    .setPageSize(2);

CompletionStage<AsyncResultSet> pageFuture =
    session.executeAsync(bound);

CompletionStage<Void> firstPageOnly = pageFuture.thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getString("event_type"));
    }
    System.out.println("Has more pages? " + page.hasMorePages());
});
```

Without calling `fetchNextPage()`, this snippet **iterates only over the current page**. It does not silently fetch subsequent pages like a synchronous `ResultSet` loop.

### 6.2. Iterating Through All Pages Asynchronously

For a batch task that **deliberately wants to read all** of a bounded partition, chain futures:

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

static CompletionStage<Long> countRowsByPages(
        AsyncResultSet page, long countSoFar) {
    long count = countSoFar;
    for (Row row : page.currentPage()) {
        count++;
        // In production: process Row with bounded resources.
    }

    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(count);
    }
    final long nextCount = count;
    return page.fetchNextPage()
        .thenCompose(next -> countRowsByPages(next, nextCount));
}

// When called inside a method with session and bound:
CompletionStage<Long> total =
    session.executeAsync(bound)
        .thenCompose(page -> countRowsByPages(page, 0L));
```

On the sample data, `total` completes with **6**. This example illustrates protocol page traversal; `countRowsByPages` does **not** replace `SELECT COUNT(*)` for general analytics, and you should never scan huge partitions inside an HTTP handler just to compute a total.

### 6.3. Extracting Paging State from an Async Page

```java
import com.datastax.oss.driver.api.core.cql.PagingState;

session.executeAsync(bound).thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getString("event_type"));
    }

    PagingState state = page.hasMorePages()
        ? page.getExecutionInfo().getSafePagingState()
        : null;

    String nextToken = state == null ? null : state.toString();
    System.out.println("Has nextToken? " + (nextToken != null));
});
```

The library exposes two representations:

- `getPagingState()`: a **raw** `ByteBuffer` without the driver's extra safety check wrapper.
- `getSafePagingState()`: a `PagingState` object that detects reuse against the wrong query or bind values.

Here `safe` refers to **query-matching validation**, **not** cryptographic tampering protection against malicious clients. Token contents must still be protected when sent over HTTP.

## 7. Building a Forward-Only API Returning nextPageToken

Consider the endpoints:

```text
GET /users/{userId}/events?day=2026-11-20
GET /users/{userId}/events?day=2026-11-20&pageToken=...
```

The first request omits `pageToken` and starts from the beginning. The response returns items plus a token for the next page if more data exists. Subsequent requests resend the **same user/day/query**, adding only the paging state.

### 7.1. Sample Application Response

```json
{
  "items": [
    {
      "happenedAt": "2026-11-20T13:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000006",
      "eventType": "LOGOUT"
    },
    {
      "happenedAt": "2026-11-20T12:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000005",
      "eventType": "SHIP"
    }
  ],
  "nextPageToken": "<opaque-token-issued-by-server>"
}
```

This is an **illustrative JSON structure**, not a real paging state token. You cannot synthesize or guess a token from `happenedAt`/`eventId`. When data is exhausted, return `nextPageToken: null` or omit the field per your API contract.

### 7.2. Complete Java Logic for Loading One Page

Java 17 and Java Driver 4.x example. For brevity and readability, HTTP token signing/verification described in Section 8 is **omitted** from this sample function; never expose raw tokens directly in production endpoints.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
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

record EventItem(Instant happenedAt, UUID eventId, String eventType) {}
record EventPage(List<EventItem> items, String nextPageToken) {}

static CompletionStage<EventPage> loadOnePage(
        CqlSession session,
        PreparedStatement prepared,
        UUID userId,
        LocalDate day,
        String previousPageToken) {

    // Query and bind values must stay identical across pages.
    BoundStatement statement = prepared.bind(userId, day)
        .setPageSize(2);

    if (previousPageToken != null && !previousPageToken.isBlank()) {
        // ONLY use raw parsing in lab; production must verify
        // signature/HMAC/AEAD and check tenant and expiry before parsing.
        PagingState previous = PagingState.fromString(previousPageToken);
        statement = statement.setPagingState(previous);
    }

    return session.executeAsync(statement).thenApply(page -> {
        List<EventItem> items = new ArrayList<>();
        for (Row row : page.currentPage()) {
            items.add(new EventItem(
                row.getInstant("happened_at"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }

        PagingState next = page.hasMorePages()
            ? page.getExecutionInfo().getSafePagingState()
            : null;
        String rawNextToken = next == null ? null : next.toString();

        // Production: wrap rawNextToken in a signed/encrypted token
        // bound to userId, day, query version, expiry; never return raw.
        return new EventPage(List.copyOf(items), rawNextToken);
    });
}
```

Usage:

```java
PreparedStatement listQuery = session.prepare("""
    SELECT happened_at, event_id, event_type
    FROM event_history_by_user_day
    WHERE user_id = ?
      AND event_day = ?
    ORDER BY happened_at DESC, event_id DESC
    """);

UUID userId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

CompletionStage<EventPage> first =
    loadOnePage(session, listQuery, userId, day, null);

// After receiving response: keep nextPageToken and send it back
// with the exact same userId and day to fetch the next page.
```

**Production guarantees to enforce:**

1. `loadOnePage` reads only `currentPage()`, never calling `fetchNextPage()`, so it never eagerly drains all pages.
2. `PagingState.fromString` and `setPagingState(PagingState)` preserve the driver's typed state; `setPagingState` validates that the state matches the bound statement.
3. When `hasMorePages()` is false or the state is null, `nextPageToken` is null.
4. Query string, bind values, projection, filters, and `ORDER BY` **must not change** between requests sharing a state.
5. Never treat `setPageSize(2)` as a strict guarantee of two rows in every response. If the UI requires an exact item count, build an application-level page policy.
6. The snippet above is **not safe for untrusted HTTP tokens**, because token authentication is omitted. Use raw tokens only inside trusted systems or labs.

### 7.3. A New Query Cannot Borrow an Old Query's State

Suppose the first request runs:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = ? AND event_day = ?;
```

The next request changes to:

```sql
SELECT happened_at, event_id, event_type, summary
FROM event_history_by_user_day
WHERE user_id = ? AND event_day = ?;
```

Even for the same user and day, **the projection changed and the query string changed**. Never pass the first query's paging state to the second query. Likewise, a token from User A / day 20 cannot be used for User B / day 20 or User A / day 21.

Even when two statements look "almost identical," state is tied to a **specific statement and its exact parameters**. When deploying new API/query versions, track token versions and handle legacy tokens cleanly.

## 8. Securing Paging State Over HTTP

Paging state was not designed as an **authorization ticket** for end users. Per the Java Driver API, `PagingState`'s "safe wrapper" relies on query-matching checks, **not strong cryptographic signatures**; internal validation does not replace HMAC or authenticated encryption.

### 8.1. Risks to Mitigate

- Users modifying tokens or replaying someone else's token.
- Tenant A's token submitted to Tenant B's endpoint.
- Clients sending oversized, malformed, or expired tokens.
- Stale tokens used after schema, query, or driver protocol changes.
- Tokens leaking in URLs, access logs, analytics, browser history, or error dumps.
- Server allowing requests to swap `user_id`, `event_day`, or filter parameters while reusing an old token.

A secure wrapper design can follow:

```text
PagingState.toString()     -- opaque driver state
          |
          v
Payload: {
  pagingState, principal/tenant, userId, day,
  queryVersion, pageSizePolicy, issuedAt, expiresAt
}
          |
          v
AEAD (authenticated encryption) or HMAC + format validation
          |
          v
Short-lived API token sent to client

Next request:
  authenticate -> check expiry/identity/query/scope
  -> extract pagingState -> PagingState.fromString(...)
  -> setPagingState on matching BoundStatement
```

**Do not mistake the diagram above for an already-implemented security protocol.** In production, use vetted cryptography libraries, key management, key rotation, and replay protection where required. If you prefer not to send opaque state externally, store paging state server-side and hand the client a **short-lived reference ID**.

### 8.2. Handling Invalid Tokens

Application rules:

1. Authenticate the user and verify authorization to view `userId` before querying Cassandra.
2. Cap token length, validate format, and verify signature/authenticated encryption.
3. Validate tenant, date, query version, and expiration; never let HTTP inputs override these bindings.
4. Map `IllegalArgumentException`, parse errors, and token mismatches to controlled API errors (e.g., HTTP 400)—never retry Cassandra in a loop.
5. Never write raw tokens or sensitive payloads into access logs or traces.
6. Never claim "an unexpired token guarantees unchanged data"; paging state is **not a snapshot**.

If state becomes invalid after an infrastructure change, return a clear error prompting the client to **restart from page one**, rather than silently altering the query with a mismatched token.

## 9. Why Are Random Page-N Jumps and Previous-Page Jumps Unsupported?

With each page, Cassandra returns the continuation state **for the next page**, not a page-number index:

```text
Start --> page 1 --S1--> page 2 --S2--> page 3 --S3--> page 4
                       ^
                       |
                 want page 3?
                 must have S2
```

To jump directly to page 37 given only the number `37` and `pageSize = 20`, Cassandra has no efficient `SELECT ... OFFSET 720` to skip straight to row 721. Options include:

- **Store paging token history:** the application retains `S1`, `S2`, ... as pages are visited. Navigating back replays the query with the saved token (and **identical query**). Manage memory, expiry, permissions, and data drift.
- **Walk from the start:** fetch and skip prior pages until reaching the desired page. Cost grows linearly with skipped rows.
- **Adjust the UX model:** "Load more" buttons or infinite scroll match paging state far better than random page-number bars.
- **Use a keyset cursor:** when a stable key order exists and the API wants explicit business boundaries.

The Java Driver includes an `OffsetPager` utility to **emulate** fetching page N by running the query from the beginning and discarding earlier rows. It is **not native Cassandra `OFFSET`** and does not eliminate linear scan cost. If used, enforce a strict cap on the maximum page number clients can request.

### 9.1. "Previous" Is Not the Inverse of Paging State

Going to the previous page is an **application-layer feature**. If the client retains the token used before loading the current page, it can re-request that earlier page with that token—though results still reflect current data and consistency on re-read.

Never take `S3` and try to "subtract one" to get `S2`, and never assume state contains a readable/editable offset. **Paging state is opaque and forward-only.**

### 9.2. Multi-Partition Paging Is More Complex Than Single-Partition Paging

```sql
SELECT event_day, happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

This query inspects **two partitions**, since `event_day` is the last component of the composite partition key. Its paging state can resume the multi-partition query, but:

- Clustering order only orders rows **within each partition**, with no global timeline guarantee across hours/days.
- The state does not expose how pages align with partition boundaries and must not be decoded to infer it.
- `LIMIT` does not substitute for capping candidate partitions in `IN`.
- Every continuation request must preserve **the exact same day list, query, and bind values**.

If the product needs "the 20 newest events across multiple days," define how cross-bucket top-N is computed (bounded merge or a query-driven table), rather than assuming paging state provides global ordering.

## 10. Comparing Paging State with Clustering-Key Keyset Cursors

For the lab table, order inside one partition is:

```text
(happened_at DESC, event_id DESC)
```

If a page ends at key `(10:00, ...0004)`, you can request rows **following** it in newest-first order via a tuple boundary:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (happened_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000004
  )
ORDER BY happened_at DESC, event_id DESC
LIMIT 2;
```

Expected output: `CLICK/0003` then `VIEW/0002`. Compare:

| Feature | Driver paging state | Keyset cursor |
| --- | --- | --- |
| How position is stored | Opaque server/driver token | Clustering key tuple from last row of page |
| Next query | **Keep identical query** and bind values, attach state | **Update boundary condition** using last key |
| Business-meaningful position? | Should not decode token | Yes, expressed directly in key columns |
| Jump to arbitrary page N | Not natively supported | Not natively supported without knowing boundary keys |
| Previous page | Application must retain prior token | Can design reversed query carefully, handling order and bounds |
| Duplicate timestamps | Driver tracks position in result set | Must include full key, e.g. `(happened_at,event_id)` |
| Changing data | Not a snapshot | Not a snapshot |
| Coupling | Tightly coupled to query/protocol/state | Coupled to schema, keys, and API sort rules |

Both approaches **fit** different scenarios. Paging state excels for "continue the exact same query" without building custom boundary logic. Keyset cursors shine when an API wants navigation over a **stable business key** with longer-lived cursors, provided schema and ordering semantics stay compatible.

**Never mix both mechanisms arbitrarily:** changing `WHERE` to a new tuple boundary creates a **new query**; never pass the old query's paging state as if the query had not changed.

## 11. Data Changing Between Pages: No Snapshot

Suppose on page 1, the user sees:

```text
Page 1: 13:00/id6, 12:00/id5
Page 2: 10:00/id4, 10:00/id3
Page 3: 09:00/id2, 08:00/id1
```

While the user reads page 1, the system may:

- Insert a new event at `14:00`, ordered **before** already-read rows.
- Delete an event at `10:00`, leaving fewer rows on the next page.
- Expire rows via TTL or expose an update on a chosen replica.
- Experience topology/replica shifts and consistency differences altering visible rows.

**Paging state does not provide a transactional snapshot** of the dataset as of page 1. Therefore:

- Never promise every "next" call returns strictly N rows.
- Never promise a user scrolling a live list will see every row inserted during traversal.
- Never use paging state to certify a multi-partition financial report as "point-in-time consistent."
- Never treat paging state as business deduplication or an exactly-once guarantee.

For greater stability, you can pin a **time window ceiling** (e.g., `happened_at < :asOf`), embed `asOf` in the API token, and keep it fixed across requests. Even with `asOf`, late writes/backfills, deletes, TTLs, and unconverged replicas prevent true snapshot semantics. For strict snapshots, use dedicated snapshot, CDC, or reconciliation mechanisms.

## 12. Performance and Load Limits During Paging

### 12.1. Small Page Sizes Do Not Automatically Make Queries Cheap

| Context | What a small page size helps with | What it does NOT solve |
| --- | --- | --- |
| Moderate partition, rows with large payloads | Reduces rows/bytes per fetch round trip | Total bytes if client drains all pages |
| `IN` across 100 partitions | Splits response into pages | Does not shrink 100 partition-key candidates |
| `ALLOW FILTERING` for rare rows | Caps matching rows emitted per batch | May inspect huge numbers of non-matching rows |
| Heavy tombstones/TTLs | Caps current response frame | Does not remove work to resolve live rows |
| Reading multiple replicas at high consistency | Limits response frame | Does not eliminate replica/reconciliation work |

Tuning page size is a **trade-off**:

- Very small: increases round trips and network overhead when traversing many pages.
- Very large: inflates response size, memory pressure, GC, and tail latency.
- Moderate: balances per-page latency and throughput based on row size, network, QPS, and UI needs.

There is no universal optimal page size for every workload; measure on data distributions resembling production.

### 12.2. Optimize the Query Before Tuning Page Size

Example of a well-scoped daily list query:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC;
```

It supplies the full partition key and projects only needed columns. If data volume is huge, consider smaller buckets or clustering ranges; do not rely on paging to scan a giant hot partition every time a user opens a screen.

### 12.3. Metrics to Monitor

| Metric | Question it answers |
| --- | --- |
| Per-fetch/page p50/p95/p99 latency | Which pages are unexpectedly slow? |
| Rows and bytes per page | Does actual size diverge from target page size? |
| Pages fetched per HTTP request | Is an endpoint accidentally draining all results? |
| In-flight reads and concurrency | Are coordinators/replicas being overloaded? |
| Timeouts, `Unavailable`, retries | Are errors caused by load, consistency, or cluster health? |
| Tombstone warnings and compaction backlog | Is finding live rows too expensive? |
| Java GC/heap and network throughput | Should projection or page size be tightened? |

When errors happen, distinguish:

1. **`InvalidQuery`**: missing keys, invalid `ORDER BY`, or unsupported filter; raising timeouts will not fix it.
2. **Invalid paging state / token mismatch**: wrong query, wrong parameters, corrupted, or expired at the app layer; return a controlled client error without mass retries.
3. **Read timeout / `Unavailable`**: check replicas, consistency, load, page size, read rate, and retry policy.
4. **Data drift across pages**: inspect concurrent writes/deletes/TTLs, consistency, paging strategy, and stabilization bounds.

## 13. Common Pagination Design Mistakes

| Claim or code | Issue | Fix |
| --- | --- | --- |
| `setPageSize(20)` limits the query to 20 rows total | Synchronous `ResultSet` auto-fetches all pages. | Use `LIMIT` for total cap or iterate only `currentPage()`. |
| Capturing paging state after reading half a page | State points to the **start of the next page**, risking dropped rows. | Consume the entire page before issuing that state to clients. |
| Changing `userId`/`day` while keeping old paging state | State is bound to the old query and bind values. | Reuse only with identical statement and parameters. |
| Changing projection/`LIMIT` between requests | Query string and semantics changed. | Start fresh pagination; never reuse old tokens. |
| Manually "editing" paging state bytes | State is opaque, not a calculable offset. | Use driver APIs; never hand-decode state. |
| Jumping to page 50 by guessing a token from page number | No mapping exists from page number to paging state. | Store token history, walk there, or change UX. |
| `OffsetPager` is a fast native `OFFSET` | Utility must fetch and discard rows prior to the target page. | Cap maximum page number and account for linear cost. |
| `getSafePagingState()` secures HTTP tokens | Safe wrapper checks query matching, **not** cryptographic signatures. | Wrap tokens with HMAC/AEAD bound to user/tenant/expiry. |
| Paging supports instant "previous page" natively | Paging state is forward-only. | App must cache prior tokens or use a suitable keyset cursor. |
| Page size 2 guarantees protocol returns strictly 2 rows | Server treats page size as a hint. | Handle actual row counts received and build a separate UI policy. |
| Paging state creates an immutable snapshot | Writes/deletes/TTLs and consistency still affect reads. | Pin a window when appropriate and never promise snapshots. |
| Using only `happened_at` for keyset cursors | Same-timestamp events cause skipped or repeated rows. | Persist both `happened_at` and `event_id`. |
| Using paging to fix broad `ALLOW FILTERING` scans | Underlying path still reads and filters broadly. | Redesign keys, indexes, or partition scope. |
| Retrying every timeout to get the next page | Can trigger retry storms, load spikes, and duplicate processing. | Use bounded retries, idempotency, and backoff. |

## 14. Practice Exercises with Answers

### Exercise 1. Total Rows and Page Fetches

**Question:** User A / day 20 has 6 rows. If target page size is 2 and the server happens to return exactly 2 rows each time, how many fetches are needed to read all rows?

**Answer:** **3 fetches** of 2 rows each. This assumes **the server actually returns 2 rows per fetch**; page size in Cassandra is a hint, so never hardcode three fetches as a protocol guarantee in all cases.

### Exercise 2. Distinguishing LIMIT and Page Size

**Question:** A query has `LIMIT 5` and Java Driver sets `setPageSize(2)`. Can it return 5 rows across the entire query?

**Answer:** Yes, up to **5 rows**, typically across multiple pages; `LIMIT 5` is not overridden by page size 2. There will be no sixth row due to the CQL limit.

### Exercise 3. Why Can a Token Drop a Row?

**Question:** Page 1 contains 2 rows. Java reads the first row, grabs the "next page" token, returns HTTP, and exits. The next request sends that token. What goes wrong?

**Answer:** The second row of page 1 was **never processed**, yet the token already points to **page 2**. The next request skips the second row. Process the entire page before emitting the token, or buffer unprocessed rows at the application layer.

### Exercise 4. Can User A's Token Be Used for User B?

**Question:** A client sends a paging state from `(user A, 2026-11-20)` while changing the URL to `(user B, 2026-11-20)`.

**Answer:** **No.** Paging state is tied to query/bind values and cannot be reused for User B. The API must also authenticate and authorize `userId`, and verify the signed token's principal, scope, and expiry.

### Exercise 5. Returning to Page 2 from Page 5

**Question:** The UI only holds the paging state to reach page 6. Can it reverse the bytes/token to go back to page 2?

**Answer:** No. State is opaque and forward-only. If the application **previously saved** the token that started page 2, it can re-run the query with that token; otherwise, it must walk from the beginning or use a different cursor/UX model.

### Exercise 6. Paging State vs. Keyset Cursor

**Question:** One API only has a "Load more" button and wants minimal cursor logic. Another needs explicit `(happened_at,event_id)` boundaries so users can load older history even across API format changes. Which should each choose?

**Suggested answer:** The "Load more" API running the **exact same query** suits paging state. The API needing explicit business boundaries and long-term control over semantics suits a **keyset cursor** with the full clustering key, fixed window bounds, and cursor validation. Neither provides snapshots or O(1) random access to page N.

### Exercise 7. New Writes During Pagination

**Question:** After a user reads page 1, a `14:00` event is inserted into the partition, ordered ahead of `13:00` under `DESC`. Does paging state guarantee the user sees that new event on subsequent pages?

**Answer:** No. Paging state resumes the query without **snapshotting** data as of page 1; a newly written row sorted ahead of the already-traversed cursor position will likely not appear on later pages. To see fresh items, refresh from the start per UI policy.

## 15. Checklist for Forward-Only Endpoints

1. **Read path:** Does `WHERE` supply the full partition key or a small bounded partition set? Does clustering order serve the UI?
2. **Limits:** Have you distinguished query-wide `LIMIT`, driver page size, and HTTP UI page size?
3. **Driver mode:** Synchronous auto-fetching `ResultSet` vs. asynchronous `AsyncResultSet.currentPage()`? Could the endpoint accidentally drain all pages?
4. **Completeness:** Is the entire current page processed before capturing paging state? Is null returned when no more pages exist?
5. **Query consistency:** Do continuation requests keep the exact CQL string, bind values, projection, filters, and query version?
6. **Security:** Are principal/tenant bindings, expiration, signing/authenticated encryption, malformed-token guards, and log redaction enforced?
7. **Navigation:** Does the UX accept forward-only? If previous/page-N jumps are required, is there a token-history strategy or cost-capped emulation?
8. **Data drift:** Is it clear that paging does not create snapshots, with policies for concurrent writes, TTLs/deletes, and unconverged replicas?
9. **Performance:** Have p95/p99 latency, pages/fetches, bytes, tombstones, timeouts, and concurrency been measured on production-like data?
10. **Retries:** Are query/token errors separated from timeouts/`Unavailable`, with backoff and idempotent handling?
11. **Alternative cursors:** If steadier chronological paging is required, have you evaluated `(happened_at,event_id)` keysets, bucketing, and fixed time windows?

**Remember:** `paging state` is the **opaque continuation position of a specific query**; the Java Driver supports the **"next page"** model cleanly. It is not `OFFSET`, a page number, a complete security token, or a data snapshot. Use `WHERE` with proper primary keys to bound read scope, `page size` to throttle fetches, authenticated wrappers for HTTP paging tokens, and identical query/bind values across continuations.

## References

- [DataStax Java Driver 4.17 — Paging: sync, async, paging state, and OffsetPager](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
- [Java Driver 4.17 — ExecutionInfo API: raw and safe paging state](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html)
- [Java Driver 4.17 — PagingState API: fromString, toString, and security warning](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/PagingState.html)
- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, LIMIT, and ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
