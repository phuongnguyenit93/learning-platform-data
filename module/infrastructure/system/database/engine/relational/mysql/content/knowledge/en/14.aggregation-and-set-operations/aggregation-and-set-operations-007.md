# GROUP_CONCAT, Concatenation Order, and the group_concat_max_len Limit

## Objectives

After this lesson, you will be able to:

- Use `GROUP_CONCAT()` to combine multiple row values into a single string within each group.
- Sort values directly inside the function with `ORDER BY` and choose a delimiter with `SEPARATOR`.
- Combine `DISTINCT`, `CONCAT_WS()`, and `COALESCE()` to handle duplicates or `NULL` values.
- Distinguish concatenation order inside `GROUP_CONCAT()` from group ordering in the outer query.
- Configure `group_concat_max_len` at the session/global scope and detect truncated results.
- Choose an appropriate representation for aggregated data, avoiding unsafe delimited strings as an interchange format.
- Evaluate the cost of `DISTINCT`, sorting, and string concatenation on large groups.

## 1. What Is GROUP_CONCAT Used For?

`GROUP_CONCAT()` is a MySQL aggregate function. It takes expression values from multiple rows in the same group and concatenates them into a single string. It is commonly used to produce lists of names, labels, product codes, or statuses associated with a parent entity.

For example, a customer has multiple orders. Instead of returning one row per order, a report can return one row per customer with their order IDs concatenated into a list:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id) AS order_ids
FROM orders
GROUP BY customer_id;
```

Illustrative result:

| customer_id | order_ids |
|---:|---|
| 101 | `5001,5002,5008` |
| 102 | `5003,5004` |
| 103 | `5005` |

By default, values are separated by a comma. Do not assume any specific element order if `ORDER BY` is not specified inside the function.

### 1.1. Syntax

```sql
GROUP_CONCAT(
    [DISTINCT] expr
    [ORDER BY {col_name | expr} [ASC | DESC] [, ...]]
    [SEPARATOR str_val]
)
```

- `expr`: expression to concatenate for each row.
- `DISTINCT`: removes duplicate values before concatenating.
- `ORDER BY`: specifies the order of values inside the resulting string.
- `SEPARATOR`: specifies the delimiter string; default is comma `,`.

Because `GROUP_CONCAT()` is an aggregate function, it typically appears in `SELECT` alongside `GROUP BY`, though it can also aggregate the entire result set when `GROUP BY` is omitted.

### 1.2. Concatenating the Entire Result Set into One String

Without `GROUP BY`, the function produces a single aggregated result across all matching rows:

```sql
SELECT GROUP_CONCAT(order_id ORDER BY order_id) AS all_order_ids
FROM orders;
```

The query returns one row. If there are no non-NULL values to concatenate, the result is `NULL`.

## 2. Sorting Inside GROUP_CONCAT

### 2.1. ORDER BY Inside the Function Controls Concatenation Order

Suppose the `order_items` table stores order line items:

```sql
CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_order_line (order_id, line_no)
) ENGINE = InnoDB;
```

To concatenate product names in line-item order:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        product_name
        ORDER BY line_no ASC, item_id ASC
        SEPARATOR ' | '
    ) AS product_list
FROM order_items
GROUP BY order_id;
```

`ORDER BY` is inside `GROUP_CONCAT()`, so it determines the order of product names within the string. `item_id` serves as a tie-breaker so the order remains deterministic if two rows share the same `line_no`.

### 2.2. Outer ORDER BY Does Not Sort Elements Inside the String

The two `ORDER BY` placements play different roles:

```sql
SELECT
    order_id,
    GROUP_CONCAT(product_name SEPARATOR ', ') AS product_list
FROM order_items
GROUP BY order_id
ORDER BY order_id DESC;
```

`ORDER BY order_id DESC` sorts the output rows (the order groups). It does not determine the order of product names inside `product_list`.

To control both levels:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        product_name
        ORDER BY line_no, item_id
        SEPARATOR ', '
    ) AS product_list
FROM order_items
GROUP BY order_id
ORDER BY order_id DESC;
```

### 2.3. Sorting by Expressions

You can sort by priority status, timestamp, or a computed expression:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR '; '
    ) AS recent_orders
FROM orders
GROUP BY customer_id;
```

If multiple rows can tie on the sort key, add a unique column so the order is deterministic. Do not rely on physical row order or index scan order when `ORDER BY` is omitted.

## 3. Choosing a Delimiter with SEPARATOR

### 3.1. Using the Default Delimiter

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id) AS order_ids
FROM orders
GROUP BY customer_id;
```

The default output looks like `5001,5002,5008`.

### 3.2. Using a Custom Delimiter

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ' / '
    ) AS order_ids
FROM orders
GROUP BY customer_id;
```

`SEPARATOR` takes a fixed string literal. You can use a comma with a space, semicolon, pipe, or another character suited to display needs.

### 3.3. Empty SEPARATOR

If you want values concatenated directly with no delimiter:

```sql
SELECT GROUP_CONCAT(product_code ORDER BY product_code SEPARATOR '')
       AS combined_codes
FROM products;
```

Without a delimiter, boundaries between values may no longer be distinguishable. Use this only when the output format has fixed lengths or another structural rule allowing each element to be parsed.

### 3.4. Data Containing the Delimiter Itself

If product names can contain `,` and the output also uses a comma, a reader or client parser cannot reliably tell which commas separate elements. For example, `Tea, green, Coffee` could be three items or two items depending on the original data.

Therefore:

- Use `GROUP_CONCAT()` for display strings when formatting is controlled.
- If the output must be parsed back, define and test an explicit escape/unescape rule.
- If structured data interchange is required, consider JSON instead of inventing a comma-separated format.

`GROUP_CONCAT()` does not automatically escape delimiters that appear in data. Do not treat a concatenated string as valid CSV or a safe serialization format without proper quoting, escaping, and encoding.

## 4. DISTINCT and Removing Duplicate Values

### 4.1. DISTINCT Inside GROUP_CONCAT

When a JOIN query produces repeated rows, `DISTINCT` can eliminate duplicate values before concatenating:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        DISTINCT status
        ORDER BY status
        SEPARATOR ', '
    ) AS statuses
FROM orders
GROUP BY customer_id;
```

Each status appears only once in the customer's list.

### 4.2. DISTINCT Is Affected by Collation

For string expressions, whether two values are treated as duplicates depends on charset/collation. Under a case-insensitive collation, `Paid` and `PAID` may be treated as the same value when `DISTINCT` is applied.

Verification example:

```sql
SELECT
    GROUP_CONCAT(DISTINCT status ORDER BY status) AS distinct_statuses
FROM orders;
```

If case sensitivity is required, choose an appropriate collation or explicitly cast/convert the expression to the desired collation. Do not assume `DISTINCT` always compares raw bytes.

### 4.3. DISTINCT Can Hide JOIN Issues

Suppose a query joins an orders table with a status history table where each order has multiple history rows. `GROUP_CONCAT(product_name)` might repeat products because the JOIN multiplies row count.

Adding `DISTINCT` may make the string look cleaner, yet it can also mask a cardinality bug or drop legitimate business duplicates. Before using it, inspect the post-JOIN row count and understand why duplicates occur. When needed, aggregate in a separate subquery keyed appropriately before joining the result.

Pre-aggregation structure example:

```sql
SELECT
    oi.order_id,
    GROUP_CONCAT(
        oi.product_name
        ORDER BY oi.line_no, oi.item_id
        SEPARATOR ', '
    ) AS products
FROM order_items AS oi
GROUP BY oi.order_id;
```

This query produces exactly one row per `order_id` before combining with other one-to-many tables.

## 5. Combining Multiple Columns per Row

`GROUP_CONCAT()` accepts a single expression. When you want multiple columns from the same row in each element, construct an expression using `CONCAT()` or `CONCAT_WS()`.

### 5.1. Using CONCAT

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(product_name, ' x ', quantity)
        ORDER BY line_no, item_id
        SEPARATOR '; '
    ) AS item_summary
FROM order_items
GROUP BY order_id;
```

Each line item becomes a segment such as `Keyboard x 2`; segments are joined by `; `.

Note: `CONCAT()` returns `NULL` if any of its arguments is `NULL`. Because `GROUP_CONCAT()` ignores expressions that evaluate to `NULL`, the entire element can vanish from the output.

### 5.2. Using CONCAT_WS to Handle NULL

`CONCAT_WS(separator, ...)` skips `NULL` arguments after the separator:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        CONCAT_WS(' ', first_name, middle_name, last_name)
        ORDER BY last_name, first_name
        SEPARATOR ' | '
    ) AS customer_names
FROM customer_contacts
GROUP BY customer_id;
```

`CONCAT_WS()` allows `middle_name` to be `NULL` without turning the entire expression into `NULL`. However, if all data arguments are NULL, the expression evaluates to an empty string; decide whether to keep or exclude such empty elements.

### 5.3. Casting and Formatting Numbers/Datetimes

When concatenating monetary amounts, quantities, or datetimes, format explicitly:

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(
            product_name,
            ' (', quantity,
            ', ', FORMAT(unit_price, 2), ')'
        )
        ORDER BY line_no, item_id
        SEPARATOR ' | '
    ) AS item_details
FROM order_items
GROUP BY order_id;
```

`FORMAT()` creates a display string and can apply locale-based grouping separators; do not use its output as numeric input for further calculations. For financial reports or APIs, keep numbers in numeric types until the final presentation step.

## 6. Handling NULL and Groups with No Values

### 6.1. GROUP_CONCAT Ignores NULL

`NULL` values in the expression are ignored during concatenation:

```sql
SELECT
    GROUP_CONCAT(phone ORDER BY phone SEPARATOR ', ') AS phone_list
FROM customers;
```

Customers with `phone IS NULL` do not contribute a `NULL` item to the string.

### 6.2. When No Non-NULL Values Exist, the Result Is NULL

If every value in a group is NULL or the input set has no matching rows, `GROUP_CONCAT()` returns `NULL`:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(phone ORDER BY phone) AS phone_list
FROM customers
GROUP BY customer_id;
```

If an API expects an empty string instead of NULL, use `COALESCE()`:

```sql
SELECT
    customer_id,
    COALESCE(
        GROUP_CONCAT(phone ORDER BY phone SEPARATOR ', '),
        ''
    ) AS phone_list
FROM customers
GROUP BY customer_id;
```

This is a formatting choice. `NULL` and an empty string carry different semantics; convert to `''` only if the consumer explicitly expects that convention.

### 6.3. LEFT JOIN and Groups with No Child Rows

To display all customers, including those with no orders yet:

```sql
SELECT
    c.customer_id,
    c.full_name,
    GROUP_CONCAT(
        o.order_id
        ORDER BY o.created_at DESC, o.order_id DESC
        SEPARATOR ', '
    ) AS order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
```

For customers without orders, `o.order_id` is NULL due to LEFT JOIN and `GROUP_CONCAT()` returns NULL. To display an empty string instead, wrap with `COALESCE()`.

Do not blindly write `GROUP_CONCAT(CONCAT(o.order_id, ':', o.status))` in a LEFT JOIN query without checking nulls. If the expression produces a placeholder or empty string for NULL-extended rows, the result may violate intent. Check for NULL inside the expression or use `CASE WHEN o.order_id IS NOT NULL THEN ... END`.

## 7. GROUP_CONCAT and GROUP BY

### 7.1. One Concatenated String per Group

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ', '
    ) AS order_ids
FROM orders
GROUP BY customer_id;
```

Each `customer_id` forms one group. `COUNT(*)` counts rows in the group, and `GROUP_CONCAT()` concatenates order IDs for that same group.

### 7.2. ONLY_FULL_GROUP_BY

When `ONLY_FULL_GROUP_BY` is enabled, columns in `SELECT` must be grouped, aggregated, or determined by MySQL to be functionally dependent on the grouping columns under that version's rules.

Unsafe example:

```sql
-- customer_name is neither grouped nor aggregated
SELECT
    customer_id,
    customer_name,
    GROUP_CONCAT(order_id)
FROM orders
GROUP BY customer_id;
```

If `customer_name` is not a column of `orders` or lacks a valid functional dependency, the query may be rejected. The clear solution is to JOIN the customers table and group by the required columns:

```sql
SELECT
    c.customer_id,
    c.full_name,
    GROUP_CONCAT(o.order_id ORDER BY o.order_id) AS order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
```

Do not disable `ONLY_FULL_GROUP_BY` merely to make a query run. Define the exact rule selecting a representative value for each group.

### 7.3. Filtering Groups with HAVING

`WHERE` filters rows before grouping; `HAVING` filters group results after aggregation:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY order_id) AS order_ids,
    COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
HAVING COUNT(*) >= 3;
```

Only customers with at least three orders in the selected time range appear. `HAVING` can reference aggregate expressions, but should not replace `WHERE` for standard row-level filtering.

## 8. group_concat_max_len and Result Limits

### 8.1. Default Value

MySQL caps the result length of `GROUP_CONCAT()` via the `group_concat_max_len` system variable. The default value is typically `1024` bytes. The practical upper limit is also constrained by `max_allowed_packet`.

Inspect the values:

```sql
SELECT
    @@SESSION.group_concat_max_len AS session_group_concat_max_len,
    @@GLOBAL.group_concat_max_len AS global_group_concat_max_len,
    @@max_allowed_packet AS max_allowed_packet;
```

Length is measured in bytes, not display characters. With `utf8mb4`, a single character can take up to four bytes; therefore, a 1024-byte limit can hold fewer than 1024 characters.

### 8.2. Truncated Results

If the concatenated string exceeds the limit, MySQL truncates the result to the configured limit and emits a warning. The query still returns a seemingly valid string that is silently missing trailing items. This is a serious risk when using `GROUP_CONCAT()` for reports or data exchange.

Test example:

```sql
SET SESSION group_concat_max_len = 32;

SELECT GROUP_CONCAT(product_name ORDER BY item_id SEPARATOR ', ')
       AS product_list
FROM order_items;

SHOW WARNINGS;
```

`SHOW WARNINGS` must run immediately after the SELECT statement to inspect warnings emitted by that statement. In practice, restore or set an appropriate session limit after testing.

### 8.3. Increasing the Limit for the Current Session

```sql
SET SESSION group_concat_max_len = 16384;

SELECT @@SESSION.group_concat_max_len;
```

A SESSION change affects only the current connection. This is usually the right choice when only one report needs longer strings. There is no need to alter server-wide configuration for an isolated query.

### 8.4. Setting a GLOBAL Default

```sql
SET GLOBAL group_concat_max_len = 16384;
```

The GLOBAL value becomes the default for new sessions; existing sessions retain their own SESSION values. To persist across restarts, use the server configuration file or version-supported persist mechanism after evaluating server memory and workload.

Configuration example:

```ini
[mysqld]
group_concat_max_len = 16384
```

Do not raise the limit to a massive number out of habit. Large limits allow huge groups to allocate large strings in memory, increase network transfer costs, and put pressure on the application. Choose a limit matching a meaningful maximum result size.

### 8.5. max_allowed_packet Remains a Ceiling

Increasing `group_concat_max_len` does not mean infinitely long strings can be returned. `max_allowed_packet` limits the maximum packet/result size permitted in client-server communication and can cap actual output. Both variables must be considered together; do not raise `max_allowed_packet` without understanding its impact on server/client memory and application needs.

### 8.6. Checking Warnings in Application Code

In JDBC, the application can inspect warnings on `Statement`/`ResultSet` depending on the driver:

```java
try (var statement = connection.createStatement()) {
    try (var result = statement.executeQuery(
            "SELECT GROUP_CONCAT(order_id) FROM orders")) {
        if (result.next()) {
            String orderIds = result.getString(1);
        }
    }

    SQLWarning warning = statement.getWarnings();
    while (warning != null) {
        // Log SQLState, vendor code, and message for monitoring
        warning = warning.getNextWarning();
    }
}
```

This example requires importing `java.sql.SQLWarning`. How warnings are attached to Statement/Connection can depend on the driver; verify on your Connector/J version and do not ignore warnings simply because no exception was thrown.

## 9. Result Data Type and Charset

`GROUP_CONCAT()` returns a string. Its result type and binary/nonbinary properties depend on the arguments and configuration. In MySQL, when `group_concat_max_len` does not exceed 512, result metadata may be `VARCHAR`/`VARBINARY`; when larger than 512, it may be `TEXT`/`BLOB` correspondingly. Applications should read it as an appropriate string/byte type rather than relying on a fixed metadata type across configuration changes.

The character set of the input expression affects the result character set. When concatenating multilingual text, ensure columns and the connection use a suitable charset, typically `utf8mb4`. Avoid improper charset conversions before concatenating, as `GROUP_CONCAT()` cannot repair existing mojibake.

Verification example:

```sql
SELECT
    CHARSET(GROUP_CONCAT(full_name ORDER BY full_name)) AS result_charset,
    COLLATION(GROUP_CONCAT(full_name ORDER BY full_name)) AS result_collation
FROM customers;
```

For binary data, the result may be binary. Do not assume every aggregated output is UTF-8 text.

## 10. GROUP_CONCAT in Real-World Queries

### 10.1. Product List per Order

```sql
SELECT
    oi.order_id,
    GROUP_CONCAT(
        CONCAT(oi.product_name, ' x', oi.quantity)
        ORDER BY oi.line_no, oi.item_id
        SEPARATOR '; '
    ) AS items
FROM order_items AS oi
GROUP BY oi.order_id;
```

### 10.2. Unique Tag List per Post

```sql
SELECT
    pt.post_id,
    GROUP_CONCAT(
        DISTINCT t.tag_name
        ORDER BY t.tag_name
        SEPARATOR ', '
    ) AS tags
FROM post_tags AS pt
JOIN tags AS t
  ON t.tag_id = pt.tag_id
GROUP BY pt.post_id;
```

### 10.3. Chronological Status History

```sql
SELECT
    order_id,
    GROUP_CONCAT(
        CONCAT(status, ' @ ', DATE_FORMAT(changed_at, '%Y-%m-%d %H:%i:%s'))
        ORDER BY changed_at, history_id
        SEPARATOR ' -> '
    ) AS status_history
FROM order_status_history
GROUP BY order_id;
```

Ordering by `changed_at` and `history_id` keeps the history stable when multiple events share the same timestamp.

### 10.4. Combining with Filter Conditions

```sql
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ', '
    ) AS paid_orders
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
```

Only `PAID` orders enter the aggregation; `HAVING` keeps customers with at least two matching orders.

## 11. GROUP_CONCAT, JSON_ARRAYAGG, and Interchange Formats

`GROUP_CONCAT()` works well for display strings or simple lists. If you need to return structured data to an API, `JSON_ARRAYAGG()` may be a better fit:

```sql
SELECT
    order_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'itemId', item_id,
            'productName', product_name,
            'quantity', quantity
        )
    ) AS items_json
FROM order_items
GROUP BY order_id;
```

JSON preserves data-type boundaries and escapes strings according to specification, making it safer than manually splitting comma-delimited strings. However, verify JSON support in your MySQL version and check result size limits.

Do not assume element ordering in `JSON_ARRAYAGG()` is guaranteed if your version's documentation does not specify ordering. If element order is a business requirement, check sorting support in your target version or sort downstream using a guaranteed mechanism. `GROUP_CONCAT()` lets you declare `ORDER BY` directly inside the function.

## 12. Performance and Practical Limits

### 12.1. DISTINCT and ORDER BY Have a Cost

In a large group, `DISTINCT` must identify duplicate values; `ORDER BY` inside the function must sort values prior to concatenation. Both can increase CPU, memory, and temporary processing overhead.

Use `DISTINCT` only when semantics require deduplication. Use `ORDER BY` when element order matters—though for reports and APIs, declaring it is usually advisable for deterministic output.

### 12.2. Filter Data Before Aggregating

Reduce the number of rows entering groups using `WHERE` whenever conditions apply per row:

```sql
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY created_at DESC, order_id DESC) AS order_ids
FROM orders
WHERE created_at >= '2026-01-01'
  AND status = 'PAID'
GROUP BY customer_id;
```

Indexes can assist filtering and grouping depending on data distribution, though no single index fits all queries. Use `EXPLAIN` to inspect the access path and measure on production-like data.

### 12.3. Avoid Building Giant Strings for Unbounded Groups

A single customer might have millions of events. Concatenating every ID into one string is rarely a good way to return data. Consider:

- Paginating detail records instead of concatenating everything.
- Restricting the time window or item count as required by the report.
- Building scheduled summary/materialized tables if the report is queried frequently.
- Returning JSON or multiple structured rows rather than a hard-to-parse string.
- Separating the detail-list endpoint from the summary-metrics endpoint.

`group_concat_max_len` is purely a technical cap, not a business policy permitting silent omission of the rest of a list.

### 12.4. Inspect Execution Plans and Data Volume

```sql
EXPLAIN
SELECT
    customer_id,
    GROUP_CONCAT(order_id ORDER BY created_at DESC, order_id DESC)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Observe the chosen index, estimated rows, grouping strategy, and filter conditions. You can use `EXPLAIN ANALYZE` on supported MySQL versions to inspect actual row counts and timing; since it executes the query, consider production load before running it.

## 13. Common Pitfalls

| Mistake | Consequence | Solution |
|---|---|---|
| Omitting ORDER BY inside the function | Element order is non-deterministic | Declare `ORDER BY` with a unique tie-breaker |
| Using only outer ORDER BY | Sorts groups only, not elements inside the string | Place ORDER BY inside `GROUP_CONCAT()` |
| Not increasing `group_concat_max_len` when needed | Output is truncated with a warning | Check limits, raise SESSION limit sensibly, and inspect warnings |
| Assuming the limit is measured in characters | UTF-8 strings can be truncated earlier than expected | Measure in bytes and account for multi-byte characters |
| Using DISTINCT to mask a JOIN bug | Drops meaningful duplicates or hides wrong cardinality | Check JOIN relationships and pre-aggregate by key |
| Concatenating strings and parsing by comma | Values containing the delimiter corrupt structure | Use explicit escaping or structured JSON |
| Failing to handle NULL | All-NULL results return NULL; CONCAT elements may vanish | Use `CONCAT_WS`, `CASE`, or `COALESCE` as intended |
| Setting max_len excessively high | Huge group strings strain memory and network transfer | Bound item count or change query/API design |
| Assuming JSON_ARRAYAGG has default ordering | Element order may not be guaranteed | Check version docs and sort deterministically |

## 14. Quick Verification Query Set

```sql
-- Ordered list with custom separator
SELECT
    customer_id,
    GROUP_CONCAT(
        order_id
        ORDER BY created_at DESC, order_id DESC
        SEPARATOR ' | '
    ) AS order_list
FROM orders
GROUP BY customer_id;

-- Deduplicate statuses according to the expression's collation
SELECT
    customer_id,
    GROUP_CONCAT(DISTINCT status ORDER BY status SEPARATOR ', ') AS statuses
FROM orders
GROUP BY customer_id;

-- Handle NULL result
SELECT
    customer_id,
    COALESCE(GROUP_CONCAT(phone ORDER BY phone), '') AS phone_list
FROM customers
GROUP BY customer_id;

-- Check limits
SELECT
    @@SESSION.group_concat_max_len,
    @@GLOBAL.group_concat_max_len,
    @@max_allowed_packet;

-- Set limit for the current session
SET SESSION group_concat_max_len = 16384;

-- Run the aggregate query to verify
SELECT GROUP_CONCAT(order_id ORDER BY order_id SEPARATOR ', ')
FROM orders;

-- Check warnings immediately after the aggregate query being monitored
SHOW WARNINGS;
```

These queries use `orders` and `customers` as examples. `SHOW WARNINGS` must run immediately after the statement being checked; running another SQL statement in between may clear or replace the warnings from the aggregate query.

## 15. Checklist When Using GROUP_CONCAT

- [ ] Clearly defined the grouping unit and applied `GROUP BY` on the right key.
- [ ] Included `ORDER BY` inside the function whenever element order matters.
- [ ] Added a unique tie-breaker if sort values can tie.
- [ ] Chosen a `SEPARATOR` suitable for display that does not introduce ambiguity with data.
- [ ] Confirmed `DISTINCT` reflects business semantics and checked collation behavior.
- [ ] Understood that `NULL` values are skipped and an all-NULL result is NULL.
- [ ] Checked `group_concat_max_len` and `max_allowed_packet`.
- [ ] Checked warnings to detect string truncation.
- [ ] Accounted for byte length when data uses multi-byte charsets like utf8mb4.
- [ ] Measured the cost of sorting, deduplication, and large groups.
- [ ] Avoided using concatenated strings as serialization without explicit escaping rules.
- [ ] Considered JSON or pagination when exchanging large structured lists.

## 16. Conclusion

`GROUP_CONCAT()` combines multiple values within a group into a single string. `ORDER BY` inside the function controls concatenation order, `SEPARATOR` picks the delimiter, and `DISTINCT` removes duplicates according to the expression's comparison rules. NULL values are skipped; if there are no values to concatenate, the result is NULL.

Result length is bounded by `group_concat_max_len` and `max_allowed_packet`. When exceeded, the string may be truncated with a warning while the query still returns a result. Set sensible session limits, inspect warnings, enforce deterministic ordering, and choose JSON or pagination when handling large structured lists.
