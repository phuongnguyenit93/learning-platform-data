# Stable Ordering, Out-of-Range Pages, and Data Changing Between Reads

Pagination lets clients read a large result set in smaller chunks. However, sending `page` and `size` does not by itself guarantee that pages remain stable when data changes. If the sort order is non-deterministic, records can appear twice or be skipped even when data has not changed. If inserts or deletes occur between two requests, offset-based pagination can also shift page boundaries. Clients must also handle cases where the requested page is no longer within the result range.

## 1. Why Does Stable Ordering Matter?

A paginated query needs a deterministic order so the server knows which records belong to page 0, page 1, and subsequent pages. Without an explicit `ORDER BY` or `Sort`, the database does not guarantee the order of returned rows. Order can differ across runs due to changes in execution plans, indexes, data, or database configuration.

Even with sorting, if the sorted property contains duplicate values, the order among records with the same value is still not fully determined.

For example, suppose there are the following orders:

| id | createdAt |
|---:|---|
| 101 | 2026-05-10T09:00:00Z |
| 102 | 2026-05-10T09:00:00Z |
| 103 | 2026-05-10T08:30:00Z |
| 104 | 2026-05-10T08:00:00Z |

If sorted only by `createdAt,desc`, orders 101 and 102 share the same value. The database may return them in different orders across two queries. When the page size is small, a record may swap positions across a page boundary.

To establish a more stable order, add a unique property as a secondary criterion:

```http
GET /orders?page=0&size=2&sort=createdAt,desc&sort=id,asc
Accept: application/hal+json
```

Order is determined by `createdAt` descending and then `id` ascending. Because `id` is unique, each order has a deterministic position in the result set at query time.

## 2. Stable Ordering in Spring Data

Spring Data REST accepts sort parameters and converts them into a `Sort` or part of a `Pageable`. You can pass multiple `sort` parameters to create a multi-level sort order:

```http
GET /orders?sort=status,asc&sort=createdAt,desc&sort=id,asc&page=0&size=20
```

Conceptual equivalent:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);
```

Sort names must be property paths that the repository can sort by. Do not use SQL column names or JSON display names if they do not match supported domain properties.

When designing an API, you should:

- Choose a deterministic default sort, usually ending with a unique key.
- Restrict allowed sort properties to avoid expensive queries or sorting by unsuitable fields.
- Use the same sort order for every request while a client is traversing a sequence of pages.
- Preserve filters and sorts when following the `next` link or building the next-page request.

A sort with a unique key establishes a total ordering for the dataset at query time. It resolves ambiguity from duplicate sort values, but it does not freeze data across multiple requests.

## 3. How Does Offset Pagination Work?

Page/size pagination is usually implemented by skipping a number of records and then taking the next batch. With 0-based `page`:

`offset = page × size`

Example with size 20:

| page | offset | Position Range |
|---:|---:|---|
| 0 | 0 | 1–20 |
| 1 | 20 | 21–40 |
| 2 | 40 | 41–60 |

With Spring Data, `Pageable` carries page, size, and sort information so the repository executes the corresponding query. Offset pagination is easy to use and fits UIs with page buttons or the need to jump to a specific page.

However, offset describes a position in the current result set. If the result set changes between reads, the positions of records also change. `page=1` does not mean “continue reading after the last record I received”; it means “skip the first 20 records given the state and ordering at the time this request is processed”.

## 4. Why Can Inserts Cause Duplicate Records?

Suppose a client reads page 0 with size 3, sorted by `createdAt,desc`:

<text>

</text>

Initially the order is:

```text
A, B, C | D, E, F | G, H, I
  page 0  |  page 1
```

The client reads page 0 and receives A, B, C. Before the client requests page 1, a new record X is inserted at the front of the list:

```text
X, A, B | C, D, E | F, G, H, I
  page 0  |  page 1
```

The page 1 request skips the first three elements in the new data and therefore returns C, D, E. The client already received C on page 0 earlier and now receives C again.

Even ordering with a unique secondary key does not prevent this scenario: the current ordering is completely deterministic, yet the record's position shifted because X was inserted ahead of it.

## 5. Why Can Deletes Cause Skipped Records?

The opposite scenario occurs when a record ahead of the offset is deleted.

Initially:

```text
A, B, C | D, E, F | G, H, I
  page 0  |  page 1
```

The client reads page 0 and receives A, B, C. Afterward, A is deleted. The current result set becomes:

```text
B, C, D | E, F, G | H, I
  page 0  |  page 1
```

When the client requests page 1, the server skips the current first three elements B, C, D and returns E, F, G. D was never received by the client, yet it was skipped due to the shifted offset.

Updates to sort properties can produce a similar effect: a record is updated such that it moves from behind to ahead of the boundary, or vice versa. Thus, changing data includes not only inserts/deletes, but also updates to fields participating in sorting or filtering.

## 6. Out-of-Range Pages and Empty Pages

An out-of-range page occurs when the `page` index no longer points to an existing slice of results. For example, a query with 47 results and size 20 has three valid pages: 0, 1, and 2. If the client requests `page=3`, the response typically has an empty collection.

Common cases:

- The client sends a page greater than or equal to `totalPages`.
- The page previously existed, but deleted records reduced the total number of pages.
- A filter was changed so the result count shrank while the client kept the old page.
- A page may be empty because there are no matching results, not necessarily because the endpoint failed.

With `Page<T>`, metadata can report the requested `number`, `size`, `totalElements`, and `totalPages`. If totalPages is 0, the result set has no pages. If the page is out of range, the client must read the metadata and actual content to decide how to render.

Do not assume Spring Data REST always clamps an out-of-range page back to the last page. Exact behavior depends on how the endpoint creates the Page and on the framework version; clients should handle responses per contract rather than relying on server-side auto-adjustment.

## 7. Choosing How to Handle Out-of-Range Pages

The API and client should agree on how to react when a page is no longer valid. Several options:

| Approach | Behavior | When Suitable |
|---|---|---|
| Return empty page with metadata | Keeps requested page; empty content | API follows standard pagination semantics |
| Client falls back to last page | Recalculates from totalPages and reloads | UI wants to keep user near the latest data |
| Client resets to first page | Sets page=0 and reloads | Filter/sort just changed or position cannot be preserved |
| Server rejects request | Returns error per API contract | Application treats out-of-range page as an invalid request |

Example client-side logic:

```text
if (totalPages == 0) {
    showEmptyState();
} else if (requestedPage >= totalPages) {
    loadPage(totalPages - 1);
} else {
    renderCurrentPage();
}
```

This is pseudocode. If the client automatically reloads the last page, avoid infinite loops if data keeps changing. Limit the number of automatic adjustments and rely on metadata from the latest response.

If filters or sorts change, the simplest behavior is usually returning to page 0. Page 5 of an old filter has no stable meaning for a new filter.

## 8. Reducing the Impact of Data Changes Between Requests

There are multiple levels of solutions depending on consistency requirements and system cost.

### 8.1. Stable Sorting with a Unique Key

Always use a deterministic sort, such as `createdAt,desc` and `id,asc`. This prevents the database from arbitrarily changing the order among records sharing the same createdAt.

This solution belongs in almost every paginated API, though it only solves non-deterministic ordering. It does not stop inserts/deletes from shifting offsets.

### 8.2. Consistent Snapshot or Transaction

If business requirements demand that every page reflect the exact same data state, a consistent snapshot or transaction with appropriate isolation may be required. However, holding a transaction open across multiple HTTP requests is usually impractical: transactions can stay open too long, retain resources, and pressure connection pools or the database.

Another approach is creating a server-side snapshot/export job: the server captures the set of IDs or data state at a point in time, and the client traverses that snapshot using a token. This is a custom application design and is not automatically provided by the `page` parameter alone.

### 8.3. Keyset/Seek Pagination

Keyset pagination uses the values of the last read record as an anchor for the next request, instead of skipping N rows. For example, sorting `createdAt DESC, id ASC`. After reading the last record with `createdAt = T` and `id = 42`, the next query can fetch records following that anchor in order:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at DESC, id ASC
LIMIT :size
```

Keyset avoids scanning past newly inserted records at the top of the list and is typically more efficient when paginating deeply through large datasets. It still requires stable sorting and suitable cursor values; deleted records or modified sort keys can still affect results. Keyset is also inconvenient for jumping directly to an arbitrary page number.

Spring Data supports scrolling/Window abstractions in appropriate versions and query types, though not every Spring Data REST search method automatically turns into a cursor endpoint. Exposing cursors over REST usually requires designing endpoints and tokens per the application contract.

## 9. HAL Navigation Links and Client Page Traversal

With HAL representation, clients typically receive links such as `self`, `next`, `prev`, `first`, and `last`. Clients should follow the server-published links to preserve filters, sorts, page size, and base path.

Example:

```json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20&sort=createdAt,desc&sort=id,asc"
    },
    "prev": {
      "href": "/orders?page=0&size=20&sort=createdAt,desc&sort=id,asc"
    },
    "next": {
      "href": "/orders?page=2&size=20&sort=createdAt,desc&sort=id,asc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 1
  }
}
```

The illustrative links may be absent on the first page, on the last page, or when there are no results. If there is no `next` link, the client should not assume a next page still exists based solely on the page number. If data changes, a new response may contain different metadata and navigation links than the previous response.

## 10. API and Client Design Checklist

1. Always define explicit sorting; add a unique key as the final criterion to establish a total ordering.
2. Keep filters and sorts consistent throughout a page-traversal pass.
3. Handle empty collections and out-of-range pages; do not assume the server automatically clamps to the last page.
4. When filters/sorts change, return the client to page 0.
5. Recognize that inserts, deletes, or sort-key updates can cause offset pagination to repeat or skip records.
6. Follow HAL navigation links instead of assembling URLs manually when the server publishes links.
7. If a consistent snapshot is required, consider a snapshot token or session-based export mechanism.
8. If traversing large, continuously changing datasets, consider keyset/cursor pagination instead of offset.
9. Test scenarios involving inserts/deletes between two reads, a shrinking last page, and out-of-range page requests.

Stable ordering is the foundation for deterministic pagination; handling out-of-range pages helps clients recover when result sets change; and snapshot or keyset pagination addresses stricter consistency needs. With Spring Data REST, clients should combine Page metadata and HAL links with a clear policy for mutable data, rather than treating the page number as a fixed pointer into the dataset.