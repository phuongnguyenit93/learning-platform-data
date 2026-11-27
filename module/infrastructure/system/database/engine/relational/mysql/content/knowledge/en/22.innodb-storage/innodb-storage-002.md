# Clustered Index and Primary-Key Data Organization

In InnoDB, a table is organized around a **clustered index**. The leaf pages of this index store the row data itself, sorted by the clustered key value. When a table has a primary key, the primary key is typically the clustered key. Therefore, primary key design directly affects how InnoDB locates rows, how secondary indexes point to rows, and the cost of storing and updating data.

Understanding the clustered index helps you choose an appropriate primary key, design effective secondary indexes, and explain why primary key lookups usually follow a direct access path whereas secondary index lookups may require an additional lookup.

## 1. What Is a Clustered Index?

A clustered index is a B+Tree structure whose leaf pages hold the table's data records. Internal nodes hold keys and pointers to child pages to guide searches. Records on leaf pages are sorted in the key order of the B+Tree.

For an InnoDB table with primary key `id`, the general structure is as follows:

```text
                 Root / Internal pages
                 [  100 |  200  ]
                  /      |      \
                 /       |       \
                v        v        v
          Leaf page  Leaf page  Leaf page
          id 1..99   id 100..199 id 200..299
          + rows     + rows      + rows
```

The diagram above illustrates only the logical search structure. Inside the data file, pages are not necessarily physically contiguous. InnoDB manages them through page structures and the B+Tree's order links.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;
```

In this table, `customer_id` is the primary key, so the clustered index is organized by `customer_id`. Leaf pages store the customer rows—including `email`, `full_name`, and `city`—rather than just the `customer_id` value alone.

An InnoDB table has only one clustered index because a data row can only be physically clustered in one way. A table can have multiple secondary indexes to support different lookup patterns.

## 2. How Does InnoDB Choose the Clustered Key?

InnoDB chooses the clustered index according to the following priority order:

1. Use the primary key (`PRIMARY KEY`) if the table declares one.
2. If there is no primary key, use the first `UNIQUE` index in which all columns are declared `NOT NULL`.
3. If there is neither a primary key nor a qualifying `UNIQUE NOT NULL` index, InnoDB generates a hidden clustered index based on an internal row ID.

Example of a table with no primary key declared, but a non-null unique key:

```sql
CREATE TABLE devices (
    serial_number VARCHAR(40) NOT NULL,
    model VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_devices_serial (serial_number)
) ENGINE = InnoDB;
```

In this case, `serial_number` can be chosen as the clustered key because it is unique and all columns in the index are `NOT NULL`.

If a table has no primary key and no qualifying unique index, InnoDB creates a hidden 6-byte row ID to organize the clustered index. This row ID is not a column that applications can query directly. Although the table still works, you lose an explicit row identifier for referencing, controlling updates, and designing relationships. Therefore, you should explicitly declare a primary key for InnoDB tables.

## 3. Primary Key Queries Traverse the Clustered Index

When querying by primary key, InnoDB searches directly within the clustered B+Tree and reads the row at the leaf page:

```sql
SELECT customer_id, email, full_name, city
FROM customers
WHERE customer_id = 105;
```

General access path:

1. Start from the root page.
2. Compare `customer_id` to descend to the appropriate internal pages.
3. Reach the leaf page containing key `105`.
4. Read the entire row from the leaf page.

With an equality condition on a unique primary key, the result is at most one row. Queries over a primary key range can also scan leaf pages in key order:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id BETWEEN 100 AND 150
ORDER BY customer_id;
```

This is one reason the primary key matters for performance: it both identifies the row and defines the clustered index order, supporting point lookups and range scans.

## 4. What Does a Secondary Index Store?

A secondary index is a separate B+Tree whose leaf pages store the indexed column values along with the primary key values needed to identify the row in the clustered index.

Example creating a secondary index on city:

```sql
CREATE INDEX idx_customers_city
ON customers (city);
```

When querying by `city`, InnoDB may perform two steps:

1. Find the matching entries in the `idx_customers_city` B+Tree.
2. Retrieve `customer_id` from the secondary index entry and use it to look up the full row in the clustered index.

Example:

```sql
SELECT customer_id, email, full_name
FROM customers
WHERE city = 'Da Nang';
```

If the secondary index does not contain all columns required by the query, InnoDB must look up the clustered index to fetch the missing columns. This is commonly referred to as a bookmark lookup or row access via secondary index.

### Why Does the Primary Key Increase Secondary Index Size?

Every secondary index needs to carry the primary key to identify the corresponding row. Consequently, the wider the primary key, the more space secondary indexes typically consume. With a composite primary key, the necessary primary key components are also stored in secondary index entries.

For example, if a table uses a composite primary key `(tenant_id, order_id)`, secondary indexes must contain enough primary key components to locate the row, excluding components already present in the secondary index itself. If there are many secondary indexes, the carried primary key columns can significantly increase total index size.

Therefore, the primary key should be short and stable. A `BIGINT` primary key generally makes secondary indexes more compact than a long string key, assuming both satisfy business identification requirements.

## 5. Covering Indexes and Avoiding Clustered Index Lookups

If a secondary index contains all the columns needed by a query, InnoDB can return the result directly from the secondary index. This is a covering index, which avoids the row lookup step in the clustered index.

Example:

```sql
CREATE INDEX idx_customers_city_name
ON customers (city, full_name);

SELECT city, full_name
FROM customers
WHERE city = 'Da Nang';
```

All queried columns are in the `(city, full_name)` index, so the query can be covered by this index. In InnoDB, the primary key is also present in secondary indexes, so a query selecting only `customer_id` along with `city` can be covered by a secondary index on `city`.

You should not add too many columns to an index solely to make it a covering index. Wide indexes increase storage usage as well as write, update, and maintenance costs. Base decisions on actual queries and `EXPLAIN` output.

## 6. Composite Primary Keys and Data Order

A primary key can consist of multiple columns. InnoDB sorts the clustered index from left to right across the key components.

Example order-items table:

```sql
CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_items_product (product_id)
) ENGINE = InnoDB;
```

The primary key `(order_id, line_no)` creates a lexicographical order: first by `order_id`, then by `line_no` within the same order.

The following query aligns with the clustered index order:

```sql
SELECT order_id, line_no, product_id, quantity
FROM order_items
WHERE order_id = 7001
ORDER BY line_no;
```

A query filtering only on `line_no` without a condition on `order_id` generally cannot effectively utilize the leading part of the composite key:

```sql
SELECT order_id, line_no
FROM order_items
WHERE line_no = 2;
```

This is the leftmost prefix rule: a composite index `(a, b, c)` efficiently supports conditions starting from `a`, such as `(a)`, `(a, b)`, or `(a, b, c)`. A condition on `b` alone typically requires another index if that query is important.

Choose composite keys according to frequent data access patterns. If most operations fetch all line items of an order, `(order_id, line_no)` is a natural choice. If you need to look up a product across many orders, a secondary index on `product_id` supports that access path.

## 7. Choosing a Primary Key to Reduce Storage and Write Costs

A good primary key typically has the following characteristics:

- **Unique and non-null:** every row has a clear identifier.
- **Compact:** reduces the size of the clustered index and secondary indexes.
- **Stable:** avoids changing the key value after the row is created.
- **Query-aligned:** supports key identity lookups and important range queries.
- **Appropriate data type:** avoids large strings when a numeric or more compact binary type meets requirements.

### Monotonically Increasing Keys

An `AUTO_INCREMENT` key such as `BIGINT UNSIGNED` typically places inserts near the end of the B+Tree:

```sql
CREATE TABLE events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
```

Sequential inserts generally exhibit good locality and reduce inserts into scattered pages. However, under very high concurrent write loads, the trailing page region can become a point of contention; measure before tuning configuration or changing key strategy.

### Random Keys

A `CHAR(36)` string UUID key is considerably longer than a 64-bit integer. Random UUIDs can also scatter inserts across many regions of the B+Tree, leading to more page reads, page splits, and fragmentation than monotonically increasing keys.

If business requirements call for UUIDs, consider storing them as `BINARY(16)` to reduce size compared to `CHAR(36)`. For UUID variants with a time component, you can choose a representation/ordering that improves locality, provided conversion between the application and database is consistent. Do not reorder bytes arbitrarily, as this affects comparison and sorting.

### Avoid Frequently Changing Primary Keys

When a clustered key value changes, InnoDB must move the record to a new position in the clustered index and update secondary indexes carrying that primary key. Therefore, use an immutable identifier as the primary key; mutable business attributes should be placed in regular columns or unique secondary indexes if needed.

## 8. Page Splits and Data Locality

B+Trees are stored in pages. When inserting a row into a nearly full leaf page, InnoDB may have to split the page (page split) to make room. Inserts with monotonically increasing keys tend to concentrate near the end of the tree; random key inserts can affect many different pages.

Page splits are normal B+Tree behavior and do not indicate data corruption. However, high-volume random inserts can increase the frequency of page splits, increase fragmentation, and reduce cache locality. Consider the key characteristics and workload rather than relying solely on a single rule of thumb.

Leaf pages are linked in key order to support sequential scans, but you should not assume that rows with adjacent keys always lie next to each other in the physical file. InnoDB manages page allocation separately; logical index order and physical disk location are two distinct concepts.

## 9. Observing Access Paths with `EXPLAIN`

`EXPLAIN` shows how MySQL expects to access tables and indexes:

```sql
EXPLAIN
SELECT customer_id, email, full_name
FROM customers
WHERE customer_id = 105;
```

For primary key queries, check fields such as:

- `key`: the index MySQL chooses; typically `PRIMARY` for primary key lookups.
- `type`: access type; for example `const` for an equality condition on a unique key with a constant, or `range` for a range query.
- `rows`: estimated number of rows to read.
- `Extra`: additional information such as `Using index` when a covering index can be used.

Compare a primary key query with a secondary index query:

```sql
EXPLAIN
SELECT customer_id, email, full_name
FROM customers
WHERE city = 'Da Nang';

EXPLAIN
SELECT city, full_name
FROM customers
WHERE city = 'Da Nang';
```

The first query may need a clustered index lookup to fetch `email` and `full_name` if the secondary index does not include those columns. The second query can use the covering index `(city, full_name)`. Actual results depend on data, statistics, and existing indexes; inspect execution plans in a representative environment rather than inferring solely from the SQL statement.

## 10. Common Design Mistakes

**Not declaring a primary key.** InnoDB can still create a hidden clustered index, but the application lacks an explicit row identifier. Proactively design a primary key for every table.

**Using an overly wide primary key.** Long string keys or multi-column composite keys inflate the size of secondary indexes. Include only columns genuinely needed for identification and access organization in the primary key.

**Using a mutable column as the clustered key.** Updating the clustered key incurs row movement and secondary index update costs. Prefer a stable key.

**Assuming secondary indexes store full rows.** Secondary index leaf pages primarily store the index key and primary key. If a query needs additional columns, the engine may have to look up the clustered index.

**Creating too many wide indexes.** Every index increases storage usage and write overhead. Create indexes only for important queries, verify with `EXPLAIN`, and monitor the workload.

**Confusing index order with physical file order.** The clustered index orders data by key within the B+Tree structure; it does not guarantee that rows with nearby keys always lie contiguously on storage media.

## 11. Self-Check

1. Why does an InnoDB table have only one clustered index?
2. How does InnoDB choose the clustered index if a table does not declare a `PRIMARY KEY`?
3. Why does a secondary index need to store the primary key?
4. What extra step might a query using a secondary index need to perform to retrieve the full row?
5. How does a covering index reduce access costs?
6. What types of queries does a composite primary key `(order_id, line_no)` support best?
7. Why can random and overly wide primary keys increase storage and write costs?
8. How does `EXPLAIN` help verify clustered index and secondary index selection?
