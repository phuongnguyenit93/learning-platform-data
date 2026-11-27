# JSON_ARRAYAGG, JSON_OBJECTAGG, and Result Characteristics

## Learning Objectives

After this lesson, you will be able to:

- Use JSON_ARRAYAGG to combine multiple rows into a JSON array.
- Use JSON_OBJECTAGG to build a JSON object from key/value pairs.
- Combine JSON aggregation with GROUP BY, JOIN, and other JSON functions.
- Understand how both functions handle NULL, empty result sets, and duplicate keys.
- Avoid relying on unguaranteed ordering in aggregated results.
- Construct nested JSON results for APIs and reports.
- Choose deduplication, ordering control, and result verification strategies suitable for your MySQL version.

MySQL can aggregate multiple relational rows into a JSON structure directly inside a SQL query. JSON_ARRAYAGG builds an array from values across multiple rows; JSON_OBJECTAGG builds an object from key and value pairs. These two functions are useful when an API needs to return an order with its list of line items, a category with its products, or a user with a settings map.

However, JSON aggregation has several characteristics distinct from GROUP_CONCAT: element ordering, duplicate keys, NULLs, and empty result sets must be clearly understood. Ignoring these rules can cause results to vary with execution plans or contain unexpected data.

Both JSON aggregate functions were introduced in MySQL 5.7.22. CTEs require MySQL 8.0 or later; the ability to use JSON_ARRAYAGG and JSON_OBJECTAGG as window functions was added in MySQL 8.0.14. The window examples in this lesson require version 8.0.14 or later.

## 1. JSON_ARRAYAGG: Combining Multiple Rows into an Array

### 1.1. Syntax and Semantics

Group aggregation syntax:

~~~sql
JSON_ARRAYAGG(expr)
~~~

The function evaluates expr on each row in the group and places the values as elements of a JSON array.

Example product table:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id),
    KEY idx_product_category (category_id)
) ENGINE = InnoDB;

INSERT INTO product (category_id, product_name, unit_price)
VALUES
    (10, 'Mechanical Keyboard', 1250000.00),
    (10, 'Wireless Mouse', 450000.00),
    (10, 'Mouse Pad', 120000.00),
    (20, '27-inch Monitor', 5200000.00);
~~~

Aggregate product names by category:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS product_names
FROM product
GROUP BY category_id;
~~~

MySQL returns a result set consisting of one row per category_id. If the application layer serializes those rows into a JSON response, the shape might look like this:

~~~json
[
  {
    "category_id": 10,
    "product_names": [
      "Mechanical Keyboard",
      "Wireless Mouse",
      "Mouse Pad"
    ]
  },
  {
    "category_id": 20,
    "product_names": [
      "27-inch Monitor"
    ]
  }
]
~~~

This is an illustrative shape. Neither the order of rows returned by SELECT nor the order of elements inside the array is guaranteed without a supported ordering mechanism.

### 1.2. You Can Aggregate Expressions, Not Just a Single Column

expr can be any SQL expression or a JSON value. This makes it possible to build an array of objects:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'productId', product_id,
            'name', product_name,
            'price', unit_price,
            'active', is_active
        )
    ) AS products
FROM product
GROUP BY category_id;
~~~

In the result, each element is a JSON object rather than a manually concatenated string:

~~~json
[
  {
    "category_id": 10,
    "products": [
      {
        "productId": 1,
        "name": "Mechanical Keyboard",
        "price": 1250000.00,
        "active": 1
      }
    ]
  }
]
~~~

SQL values are converted to corresponding JSON types. Strings become JSON strings, numbers become JSON numbers, and NULL becomes JSON null. When using BOOLEAN in MySQL, the underlying storage type is TINYINT(1), so the value may appear as 0 or 1; if an API contract explicitly requires true/false, construct an appropriate JSON expression and verify the actual output.

### 1.3. NULL Values in the Array

If expr for a row evaluates to SQL NULL, JSON_ARRAYAGG preserves that position with JSON null:

~~~sql
SELECT JSON_ARRAYAGG(value_text) AS values_json
FROM (
    SELECT 'alpha' AS value_text
    UNION ALL
    SELECT NULL
    UNION ALL
    SELECT 'gamma'
) AS source_rows;
~~~

The result looks like:

~~~json
["alpha", null, "gamma"]
~~~

The function does not automatically skip rows with NULL values. If you want to exclude them, filter before aggregating:

~~~sql
WITH source_rows AS (
    SELECT 'alpha' AS value_text
    UNION ALL
    SELECT NULL
    UNION ALL
    SELECT 'gamma'
)
SELECT JSON_ARRAYAGG(value_text) AS values_json
FROM source_rows
WHERE value_text IS NOT NULL;
~~~

If NULL means "no data" and its position should be preserved, leave JSON null. If you want the list to contain only actual values, filter explicitly with WHERE.

### 1.4. Empty Input Sets

When an aggregate query has no input rows, JSON_ARRAYAGG returns SQL NULL rather than automatically returning an empty array:

~~~sql
SELECT JSON_ARRAYAGG(product_name) AS products
FROM product
WHERE category_id = 999;
~~~

The result is NULL.

If the API requires always returning an array, even when there are no elements, use COALESCE:

~~~sql
SELECT
    COALESCE(
        JSON_ARRAYAGG(product_name),
        JSON_ARRAY()
    ) AS products
FROM product
WHERE category_id = 999;
~~~

Result:

~~~json
[]
~~~

In a query with GROUP BY, a group with no rows generally does not appear in the output. If you need to return categories with no products as well, start from the CATEGORY table and use LEFT JOIN or a correlated subquery; you cannot expect GROUP BY to invent empty groups on its own.

## 2. JSON_OBJECTAGG: Building an Object from Key/Value Pairs

### 2.1. Syntax and Semantics

Syntax:

~~~sql
JSON_OBJECTAGG(key, value)
~~~

The function creates a JSON object. Each row supplies one key and value pair. Keys are converted to string property names on the JSON object. Consequently, key values of different types that convert to the same string—for example, the number 1 and the string '1'—can produce the same property name and cause key collisions.

Example settings table:

~~~sql
CREATE TABLE user_setting (
    setting_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    setting_key VARCHAR(80) NOT NULL,
    setting_value VARCHAR(500) NULL,
    PRIMARY KEY (setting_id),
    KEY idx_user_setting_user (user_id)
) ENGINE = InnoDB;

INSERT INTO user_setting (user_id, setting_key, setting_value)
VALUES
    (101, 'theme', 'dark'),
    (101, 'language', 'vi'),
    (101, 'page_size', '50'),
    (102, 'theme', 'light'),
    (102, 'language', 'en');
~~~

Build a settings object per user:

~~~sql
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM user_setting
GROUP BY user_id;
~~~

MySQL returns a result set with one row per user_id. If the application layer packages those rows into a JSON response, it may look like:

~~~json
[
  {
    "user_id": 101,
    "settings": {
      "theme": "dark",
      "language": "vi",
      "page_size": "50"
    }
  },
  {
    "user_id": 102,
    "settings": {
      "theme": "light",
      "language": "en"
    }
  }
]
~~~

A JSON object fits when each key has a single value within the group's scope—for example, one theme per user or one config code mapped to one setting.

### 2.2. Keys Cannot Be NULL

A JSON_OBJECTAGG key cannot be NULL. If a row passes a NULL key into the function, MySQL raises an error instead of creating a property named null.

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value)
FROM user_setting;
~~~

Because setting_key is declared NOT NULL in the example, this error does not occur. If the data source allows NULL, filter or handle it explicitly:

~~~sql
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM imported_user_setting
WHERE setting_key IS NOT NULL
GROUP BY user_id;
~~~

Do not mechanically use COALESCE(key, ''). Multiple rows with NULL keys would be converted into the same empty key and collide. Map NULL to a fallback name only if business rules define that name as meaningful and unique.

### 2.3. Values Can Be NULL

Unlike keys, values can be NULL. Such values are represented as JSON null:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM (
    SELECT 'theme' AS setting_key, 'dark' AS setting_value
    UNION ALL
    SELECT 'backup_email', NULL
) AS source_rows;
~~~

Result:

~~~json
{
  "theme": "dark",
  "backup_email": null
}
~~~

JSON null differs from omitting the property. Clients can distinguish an object containing a key with value null from an object lacking that key. Choose the representation that matches your API contract.

### 2.4. Empty Input Sets

When there are no input rows, JSON_OBJECTAGG returns SQL NULL:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value)
FROM user_setting
WHERE user_id = 999;
~~~

If an empty object is needed:

~~~sql
SELECT
    COALESCE(
        JSON_OBJECTAGG(setting_key, setting_value),
        JSON_OBJECT()
    ) AS settings
FROM user_setting
WHERE user_id = 999;
~~~

The result is:

~~~json
{}
~~~

## 3. Duplicate Keys in JSON_OBJECTAGG

This is the most critical characteristic to control when using JSON_OBJECTAGG.

A JSON object should have only one value per property name. If multiple rows in the same group produce the same key, MySQL resolves duplicate keys according to the rule that **the last processed value wins**.

Example:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM (
    SELECT 'theme' AS setting_key, 'light' AS setting_value
    UNION ALL
    SELECT 'theme', 'dark'
) AS duplicate_keys;
~~~

The result retains only one theme property. However, in ordinary aggregation, the order of input rows is not guaranteed. Therefore, you should not rely on either light or dark always being processed last.

### 3.1. Why Can the Result Be Unstable?

Row processing order can change when:

- The optimizer selects a different execution plan.
- Indexes or statistics are updated.
- Data is partitioned or redistributed.
- The query runs on a different MySQL version.
- Join order or derived-table materialization changes.

When keys collide, the resulting object may retain different values across runs even if source data has not changed. An outer ORDER BY does not control the order in which rows enter the aggregate.

### 3.2. Guarantee Unique Keys Before Aggregating

The best approach is designing the data so keys are unique within the group scope:

~~~sql
ALTER TABLE user_setting
    ADD UNIQUE KEY uq_user_setting_key (user_id, setting_key);
~~~

Before adding UNIQUE, inspect and resolve any existing duplicate keys. This constraint ensures each user has at most one row per setting_key.

If the data has multi-version history and you need the latest record, deduplicate before calling JSON_OBJECTAGG.

Example history table with updated_at and setting_id:

~~~sql
WITH ranked_settings AS (
    SELECT
        user_id,
        setting_key,
        setting_value,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, setting_key
            ORDER BY updated_at DESC, setting_id DESC
        ) AS rn
    FROM user_setting_history
)
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM ranked_settings
WHERE rn = 1
GROUP BY user_id;
~~~

ROW_NUMBER selects exactly one row per (user_id, setting_key) pair. updated_at DESC picks the newest version; setting_id DESC acts as a tie-breaker when two records share the same timestamp. The condition rn = 1 ensures each key appears only once before aggregating.

Do not use MAX(setting_value) or MIN(setting_value) as a stand-in for "latest record" when string values lack a matching business order. Explicitly specify the timestamp column and tie-breaker.

## 4. Element Ordering in JSON_ARRAYAGG

### 4.1. Ordinary Aggregation Does Not Guarantee Order

JSON_ARRAYAGG(expr) builds an array from aggregated rows, but element ordering inside the array in ordinary aggregation is undefined. Do not rely on physical table order, index order, or an ORDER BY in a place that does not guarantee aggregate input order.

Example:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS products
FROM product
GROUP BY category_id;
~~~

You cannot guarantee the first element will always be the product with the smallest product_id. If ordering is part of the API contract, design the query with an explicit ordering mechanism.

JSON_ARRAYAGG syntax does not support an ORDER BY clause inside its parentheses like some string aggregate functions do. Placing ORDER BY in the outer query only sorts the output groups, not elements inside each JSON array.

### 4.2. Window Functions Do Not Guarantee Array Ordering Either

Starting in MySQL 8.0.14, JSON_ARRAYAGG can be used as a window function. You can use PARTITION BY to compute an array per group and attach that result to each row in the group:

~~~sql
SELECT
    order_id,
    line_no,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'lineNo', line_no,
            'productId', product_id,
            'name', product_name,
            'quantity', quantity
        )
    ) OVER (
        PARTITION BY order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS items_for_order
FROM order_item;
~~~

The frame ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING makes every row in the partition see all rows of the order. A window function returns one result per row, so the same array is repeated across rows belonging to the same order_id.

**Important point:** MySQL still documents JSON_ARRAYAGG element ordering as undefined, even when used as a window function. ORDER BY inside OVER defines window and frame order, not a documented guarantee on JSON array element order. Therefore, do not use this window function to guarantee an array sorted by line_no.

If element order is a strict requirement of the API contract, fetch the rows with a relational query using an explicit ORDER BY and build the array in the application. For example:

~~~sql
SELECT
    line_no,
    product_id,
    product_name,
    quantity
FROM order_item
WHERE order_id = 1001
ORDER BY line_no;
~~~

The composite key (order_id, line_no) makes line_no unique within each order. The application can read rows in this order and serialize them into a JSON array. Do not rely on physical order, indexes, or ORDER BY inside a subquery to force JSON_ARRAYAGG to sort elements.

JSON_ARRAYAGG also lacks a DISTINCT option in its aggregate syntax. If you want to eliminate duplicate values, deduplicate in a derived table or CTE before aggregating.

### 4.3. Do Not Confuse Object Ordering with Array Ordering

A JSON object is an unordered set of named properties; object member order should never be part of a business contract. A JSON array is an ordered sequence, so element order can carry meaning.

For example:

- A list of order line items should be an array and may need sorting by line_no.
- A settings map keyed by setting_key fits an object; clients access properties by key rather than position.
- A list of statuses in priority order should be an array if ordering matters.

Do not use JSON_OBJECTAGG in place of a list where elements may repeat or require ordering.

## 5. Nested JSON Aggregation

You can nest JSON_OBJECT inside JSON_ARRAYAGG to create multi-level structures. This is a common pattern when an API returns a parent entity along with its child list.

### 5.1. An Order with Its Line Items

Suppose you have:

- sales_order(order_id, order_no, ordered_at)
- order_item(order_id, line_no, product_id, product_name, quantity, unit_price)

Build a JSON array of line items for each order:

~~~sql
SELECT
    oi.order_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'lineNo', oi.line_no,
            'productId', oi.product_id,
            'productName', oi.product_name,
            'quantity', oi.quantity,
            'unitPrice', oi.unit_price
        )
    ) AS items
FROM order_item AS oi
GROUP BY oi.order_id;
~~~

Combine with the orders table:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    o.ordered_at,
    (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', oi.line_no,
                'productId', oi.product_id,
                'productName', oi.product_name,
                'quantity', oi.quantity,
                'unitPrice', oi.unit_price
            )
        )
        FROM order_item AS oi
        WHERE oi.order_id = o.order_id
    ) AS items
FROM sales_order AS o
WHERE o.order_id = 1001;
~~~

If the order has no line items, the correlated subquery returns NULL. If the API contract requires items to always be an array, wrap it in COALESCE:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    COALESCE(
        (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'lineNo', oi.line_no,
                    'productId', oi.product_id,
                    'productName', oi.product_name,
                    'quantity', oi.quantity,
                    'unitPrice', oi.unit_price
                )
            )
            FROM order_item AS oi
            WHERE oi.order_id = o.order_id
        ),
        JSON_ARRAY()
    ) AS items
FROM sales_order AS o
WHERE o.order_id = 1001;
~~~

Using a correlated subquery avoids a common LEFT JOIN pitfall: when there are no child rows, JSON_OBJECT can still be constructed from the null-extended joined row, yielding an array containing one all-null object instead of an empty array.

### 5.2. Nested JSON Objects

You can construct an object for customer details containing an array of orders:

~~~sql
SELECT
    c.customer_id,
    JSON_OBJECT(
        'customerId', c.customer_id,
        'name', c.full_name,
        'email', c.email,
        'orders',
        COALESCE(
            (
                SELECT JSON_ARRAYAGG(
                    JSON_OBJECT(
                        'orderId', o.order_id,
                        'orderNo', o.order_no,
                        'orderedAt', o.ordered_at
                    )
                )
                FROM sales_order AS o
                WHERE o.customer_id = c.customer_id
            ),
            JSON_ARRAY()
        )
    ) AS customer_document
FROM customer AS c
WHERE c.customer_id = 101;
~~~

The result is a JSON object containing an orders property whose value is a JSON array. When nesting JSON functions, MySQL preserves the JSON type of nested JSON expressions rather than concatenating strings manually.

### 5.3. Combining Multiple Aggregation Levels

You can aggregate products by category, and then categories by store or tenant. However, always control cardinality before joining. Joining multiple 1:N branches in a single query multiplies rows and causes JSON_ARRAYAGG to repeat elements.

For example, an order has 3 line items and 2 payments. Directly joining ORDER_ITEM with PAYMENT through SALES_ORDER can yield an intermediate set of 3 x 2 = 6 rows. JSON_ARRAYAGG over line items would then repeat each line item twice.

The safe approach is aggregating each child branch independently before joining:

~~~sql
WITH item_agg AS (
    SELECT
        order_id,
        JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', line_no,
                'productId', product_id,
                'quantity', quantity
            )
        ) AS items
    FROM order_item
    GROUP BY order_id
),
payment_agg AS (
    SELECT
        order_id,
        JSON_ARRAYAGG(
            JSON_OBJECT(
                'paymentId', payment_id,
                'amount', amount,
                'status', payment_status
            )
        ) AS payments
    FROM payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.items, JSON_ARRAY()) AS items,
    COALESCE(p.payments, JSON_ARRAY()) AS payments
FROM sales_order AS o
LEFT JOIN item_agg AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_agg AS p
    ON p.order_id = o.order_id;
~~~

Each CTE produces at most one row per order_id. Joining pre-aggregated results avoids cross-multiplying line items and payments.

## 6. Distinguishing JSON Aggregation from GROUP_CONCAT

GROUP_CONCAT concatenates values into a single string. JSON_ARRAYAGG and JSON_OBJECTAGG produce structured JSON values.

| Criterion | GROUP_CONCAT | JSON_ARRAYAGG | JSON_OBJECTAGG |
|---|---|---|---|
| Output | String | JSON array | JSON object |
| Client access | Must split string manually | Parse JSON array | Parse JSON object |
| Delimiter escaping | Must design manually | JSON handles escaping | JSON handles escaping |
| Multiple rows | Elements joined as text | One element per row | One key/value pair per row |
| Ordering | Supports ORDER BY inside function | Ordinary aggregate does not guarantee order | Should not rely on property order |
| Duplicate keys | No key concept | Duplicate elements are retained | Duplicate keys must be handled |
| Output limits | Truncated by group_concat_max_len and subject to max_allowed_packet | Not truncated by group_concat_max_len; still subject to packet/row limits and resources | Not truncated by group_concat_max_len; still subject to packet/row limits and resources |

GROUP_CONCAT example:

~~~sql
SELECT
    category_id,
    GROUP_CONCAT(product_name ORDER BY product_name SEPARATOR ', ')
        AS product_list
FROM product
GROUP BY category_id;
~~~

The result is a string like Mechanical Keyboard, Wireless Mouse, Mouse Pad. If a product name contains a comma or delimiter character, clients cannot split it reliably without an escaping convention.

With JSON_ARRAYAGG:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS product_list
FROM product
GROUP BY category_id;
~~~

Clients receive a valid JSON array and do not have to split delimiters manually. Still, JSON_ARRAYAGG has its own ordering rules; do not replace GROUP_CONCAT and assume ordering remains guaranteed.

## 7. Controlling Data Types and Nested JSON

### 7.1. SQL NULL and JSON null

Distinguish clearly between:

- SQL NULL: absence of a SQL value.
- JSON null: a null value inside a JSON document.
- Missing key: the object does not contain that property.
- Empty array: a JSON array with zero elements.

Example:

~~~sql
SELECT
    JSON_ARRAY(NULL) AS array_with_null,
    JSON_ARRAY() AS empty_array,
    JSON_OBJECT('value', NULL) AS object_with_null,
    JSON_OBJECT() AS empty_object;
~~~

The results take the form:

~~~json
[
  [null],
  [],
  {"value": null},
  {}
]
~~~

In aggregation, a SQL NULL from JSON_ARRAYAGG's expression becomes JSON null for that row. When there are no input rows, the aggregate returns SQL NULL. COALESCE turns result-level SQL NULL into an empty JSON array/object when that matches the desired contract.

### 7.2. JSON Strings vs JSON Values

If a VARCHAR column contains text that looks like JSON, JSON_OBJECT treats it as a string rather than automatically parsing it into a nested object.

~~~sql
SELECT JSON_OBJECT(
    'metadata',
    '{"source":"web","priority":2}'
) AS result;
~~~

The metadata value becomes a JSON string containing JSON characters, not a nested object.

To parse a valid JSON string into a JSON value, use CAST AS JSON:

~~~sql
SELECT JSON_OBJECT(
    'metadata',
    CAST('{"source":"web","priority":2}' AS JSON)
) AS result;
~~~

The result is a nested object:

~~~json
{
  "metadata": {
    "source": "web",
    "priority": 2
  }
}
~~~

CAST raises an error if the string is not valid JSON. If data comes from untrusted sources or could be malformed, check JSON_VALID before converting.

### 7.3. Numbers, Strings, and Datetimes

JSON aggregation preserves data types from the SQL expression. If a price column is DECIMAL, its value is usually represented as a JSON number. If you want a number formatted as a string, CAST explicitly; conversely, do not convert numbers to strings if clients need to compute with them.

DATE, DATETIME, and TIMESTAMP values are typically represented as datetime strings in JSON. Align on time zone and time format in the API contract; JSON aggregation does not automatically resolve application time zone conventions.

## 8. Window Functions with JSON_OBJECTAGG

JSON_OBJECTAGG can also be used as a window function since MySQL 8.0.14. This is useful when you want to construct an object per partition while retaining detail rows. Unlike JSON_ARRAYAGG, ORDER BY in the window can determine which row comes last when a key appears multiple times.

Example:

~~~sql
SELECT
    user_id,
    setting_key,
    setting_value,
    JSON_OBJECTAGG(setting_key, setting_value) OVER (
        PARTITION BY user_id
    ) AS all_settings
FROM user_setting;
~~~

Each row of a user carries the partition's settings object. If a window ORDER BY is used and keys repeat, the window ordering and frame affect which value is treated as last. For example, to retain the latest value by update time:

~~~sql
SELECT
    user_id,
    setting_key,
    setting_value,
    JSON_OBJECTAGG(setting_key, setting_value) OVER (
        PARTITION BY user_id
        ORDER BY updated_at, setting_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS latest_settings
FROM user_setting_history;
~~~

ORDER BY updated_at, setting_id must define a unique order within the partition. With a whole-partition frame, the last row in that order wins when keys repeat. The most controllable way to produce one object per user remains deduplicating with ROW_NUMBER before aggregating, as shown in section 3.2.

Do not use a window function merely to avoid a GROUP BY step when you want exactly one row per group. A window function preserves every input row; you still need ROW_NUMBER or a representative selection step if you want one row per partition.

## 9. Performance and Operational Limits

JSON aggregation reduces the number of rows transferred from the database to the application, but it is not free.

Cost increases when:

- A group contains a very large number of rows.
- Each element is an object with many properties.
- Nested JSON documents grow large.
- The query joins multiple 1:N branches before aggregating.
- The client needs only a few fields while SQL builds the entire document.
- Many concurrent requests generate large JSON documents simultaneously.

Guidelines:

1. Filter rows before aggregating using WHERE.
2. Select only the columns and expressions needed in the JSON.
3. Aggregate each 1:N branch separately before joining branches.
4. Use indexes for filter predicates and join keys.
5. Limit group sizes or paginate at the parent entity level.
6. Measure latency, memory, and payload size on realistic data; keep max_allowed_packet on server and client in mind when returning large JSON documents.
7. Do not use JSON aggregation to replace all relational query patterns.

Example fetching recent orders for a customer:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', oi.line_no,
                'productName', oi.product_name,
                'quantity', oi.quantity
            )
        )
        FROM order_item AS oi
        WHERE oi.order_id = o.order_id
    ) AS items
FROM sales_order AS o
WHERE o.customer_id = 101
ORDER BY o.ordered_at DESC
LIMIT 20;
~~~

An index on (customer_id, ordered_at) supports filtering and sorting orders per customer. The primary key or an index starting with order_id on ORDER_ITEM supports the subquery fetching line items.

If a single order has hundreds of thousands of line items, building one JSON array can produce an oversized payload. In that case, paginate line items or have the API load details from a dedicated endpoint.

## 10. Verifying JSON Results

You can use JSON functions to verify results:

~~~sql
SELECT
    JSON_VALID(
        JSON_ARRAYAGG(product_name)
    ) AS is_valid_json,
    JSON_TYPE(
        JSON_ARRAYAGG(product_name)
    ) AS result_type
FROM product;
~~~

JSON_TYPE returns ARRAY for JSON_ARRAYAGG results. For JSON_OBJECTAGG, the result is OBJECT when data is present.

You can use JSON_PRETTY for easier reading while debugging:

~~~sql
SELECT JSON_PRETTY(
    JSON_OBJECTAGG(setting_key, setting_value)
) AS formatted_settings
FROM user_setting
WHERE user_id = 101;
~~~

JSON_PRETTY is helpful for manual inspection, but unnecessary in production payloads when clients already parse JSON. Pretty-printing increases transfer size.

When verifying data:

- Confirm JSON_VALID returns 1.
- Confirm JSON_TYPE is properly ARRAY or OBJECT.
- Check element count with JSON_LENGTH.
- Inspect a specific key using JSON_EXTRACT.
- Verify empty arrays and empty objects against the API contract.
- Check for duplicate keys before aggregating objects.

Example:

~~~sql
SELECT
    JSON_LENGTH(products_json) AS product_count,
    JSON_EXTRACT(products_json, '$[0].productId') AS first_product_id
FROM category_product_document;
~~~

JSON_EXTRACT returns a JSON value. If you need a SQL scalar, use JSON_UNQUOTE or the ->> operator depending on the version and expression.

## 11. Common Pitfalls

| Mistake | Consequence | Solution |
|---|---|---|
| Assuming JSON_ARRAYAGG always sorts by index | Array order can change | If order is mandatory, SELECT rows with ORDER BY and serialize the array in the application |
| Using JSON_OBJECTAGG with duplicate keys | Last value wins; result can be unstable | Use a UNIQUE key or ROW_NUMBER to pick one row |
| Passing a NULL key to JSON_OBJECTAGG | Function raises an error | Filter or map keys according to business rules |
| Thinking a NULL value is an error | Overlooks JSON null semantics | Distinguish NULL in keys vs values |
| Expecting an empty set to automatically return [] or {} | Aggregate returns SQL NULL | Use COALESCE with JSON_ARRAY()/JSON_OBJECT() |
| LEFT JOIN followed by child object aggregation | Can produce an all-null object for rows without children | Use a correlated subquery or pre-aggregate children separately |
| Joining multiple 1:N branches before aggregating | JSON elements are multiplied | Aggregate each branch in a CTE/derived table |
| Using JSON_OBJECTAGG for an ordered list | Object is not a list structure | Use JSON_ARRAYAGG |
| Treating JSON text in VARCHAR as a JSON object | Output gets nested as a string | CAST valid JSON strings AS JSON |
| Generating a single massive JSON document | Increases memory, latency, and payload size | Filter, paginate, or split endpoints |

## 12. Hands-on Exercises

### Exercise 1: Aggregating Product Names

Create the PRODUCT table with category_id and product_name. Use JSON_ARRAYAGG to return product name lists by category. Check JSON_TYPE and JSON_LENGTH.

### Exercise 2: Aggregating a User Settings Object

Create USER_SETTING with user_id, setting_key, and setting_value. Use JSON_OBJECTAGG to build one object per user. Test NULL values and observe JSON null.

### Exercise 3: Testing Duplicate Keys

Insert two rows with the same user_id and setting_key but different setting_value. Run JSON_OBJECTAGG multiple times and observe the duplicate-key rule. Then use ROW_NUMBER to select the latest record before aggregating.

### Exercise 4: Returning Orders as JSON

Create SALES_ORDER and ORDER_ITEM. Use JSON_ARRAYAGG(JSON_OBJECT(...)) to produce items for each order. Handle orders with no line items so the result is [].

### Exercise 5: Preventing Duplication from JOIN

Create an order with 3 line items and 2 payments. Try joining both child tables and then aggregating. Count the duplicated elements, then switch to two separate aggregating CTEs and join the results.

### Exercise 6: Distinguishing Window Aggregation from Array Ordering

Use JSON_ARRAYAGG as a window function with PARTITION BY order_id and a full-partition ROWS frame to attach the array to detail rows. Then SELECT rows of one order with ORDER BY line_no and serialize the array in the application. Explain why only the second approach guarantees line_no order.

### Exercise 7: Comparing GROUP_CONCAT and JSON_ARRAYAGG

Create product names containing commas, double quotes, and Unicode characters. Compare GROUP_CONCAT strings against a JSON array. Parse the JSON result on the client and verify every element is preserved intact.

### Exercise 8: Designing an API Contract

Build a JSON response containing customer, orders, and items. Clearly specify which fields are arrays, which are objects, which can be null, and which must be empty arrays when no data exists.

## Conclusion

JSON_ARRAYAGG turns multiple rows into a JSON array; JSON_OBJECTAGG turns multiple key/value pairs into a JSON object. They allow MySQL to return data structures closely aligned with API contracts and reduce manual string concatenation in application code.

To keep results stable, explicitly address array ordering, duplicate object keys, NULL keys, SQL NULLs, and empty groups. When joining multiple 1:N relationship branches, aggregate each branch separately before combining to avoid element multiplication. Finally, verify JSON types, payload sizes, and performance on realistic data.

## References

- MySQL 8.4 Reference Manual — Aggregate Functions: https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html
- MySQL 8.4 Reference Manual — JSON Creation Functions: https://dev.mysql.com/doc/refman/8.4/en/json-creation-functions.html
- MySQL 8.4 Reference Manual — JSON Functions: https://dev.mysql.com/doc/refman/8.4/en/json-functions.html
- MySQL 8.4 Reference Manual — Window Function Concepts and Syntax: https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html
- MySQL 8.4 Reference Manual — Window Function Restrictions: https://dev.mysql.com/doc/refman/8.4/en/window-function-restrictions.html
