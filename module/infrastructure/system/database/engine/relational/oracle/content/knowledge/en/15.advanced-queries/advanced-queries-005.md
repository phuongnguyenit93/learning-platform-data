# PIVOT, UNPIVOT, and Reshaping Reporting Data in Oracle Database

In operational systems, data is typically stored in a format where **each row is an event or a record**, whereas reports often need to present data where **each group is a row and each value category is a column**. For example, a revenue table has one row per region and quarter, while a report needs columns Q1, Q2, Q3, and Q4 on the same region row. This is converting from long format to wide format.

Oracle Database supports two transformations in SQL:

- **PIVOT** groups rows and turns values of a column into result columns, usually combined with aggregate functions such as SUM, COUNT, AVG, MIN, or MAX.
- **UNPIVOT** turns multiple columns playing the same role into rows, creating one column for the dimension label/name and one or more columns for values.

These two transformations are useful when producing quarterly revenue reports, counts by status, monthly KPIs, timesheets, survey data, or when normalizing a source table spread across many columns. This lesson explains Oracle syntax, implicit grouping in PIVOT, multiple aggregates, PIVOT XML, UNPIVOT and NULLs, conditional aggregation alternatives, limitations of round-trip conversions, and a hands-on lab.

## 1. Long Format vs. Wide Format Data

Suppose revenue data is stored in long format:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |

Each row represents a combination of region and quarter. This format works well for storing data, adding new quarters, and aggregating across multiple dimensions.

However, a report may want wide format:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE |
|---|---:|---:|---:|
| North | 100 | 120 | 90 |
| South | 80 | 110 | 130 |

PIVOT converts the values in the QUARTER column into the columns Q1_REVENUE, Q2_REVENUE, and Q3_REVENUE.

In the opposite direction, if you receive a wide table from an Excel file or legacy system:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE |
|---|---:|---:|---:|
| North | 100 | 120 | 90 |
| South | 80 | 110 | 130 |

UNPIVOT can convert the quarter columns back into:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |

The long model is generally more flexible for storage and analytics. Wide format is often convenient for certain report layouts, forms, or UIs. Do not convert data to wide format merely because the result table looks nicer if downstream applications require a dynamically structured dataset.

## 2. PIVOT: Converting Values into Columns

### 2.1 Basic syntax

~~~sql
SELECT ...
FROM source_table_or_subquery
PIVOT (
    aggregate_function(measure_column)
    FOR pivot_column
    IN (
        pivot_value_1 [AS column_alias_1],
        pivot_value_2 [AS column_alias_2],
        ...
    )
);
~~~

Components:

| Component | Role |
|---|---|
| Data source | Table or subquery supplying dimensions, pivot key, and measure |
| aggregate_function | Aggregate function such as SUM, COUNT, AVG, MIN, MAX |
| measure_column | Value to be aggregated |
| pivot_column | Column whose values will become output columns |
| IN (...) | List of pivot values requested in the output |
| column_alias | Readable name for the column generated from a pivot value |

PIVOT does not merely rotate columns. It **aggregates rows** across the remaining columns of the data source. This is essential to understand before using it in reports.

### 2.2 Quarterly PIVOT example

Suppose there is a SALES table with REGION, QUARTER, and AMOUNT. Query:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

The result has columns REGION, Q1, Q2, Q3, Q4. Each region becomes a row; SUM(amount) computes total revenue for each quarter.

To make column names more descriptive, assign an alias to the aggregate function:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Oracle generates column names combining the pivot value alias and the aggregate alias, such as Q1_REVENUE, Q2_REVENUE, Q3_REVENUE, and Q4_REVENUE.

### 2.3 Why is an inline view needed?

In the example, the subquery selects only three columns:

- REGION: the dimension to keep as rows.
- QUARTER: the dimension to rotate into columns.
- AMOUNT: the measure being aggregated.

Passing only the required columns into the PIVOT source clearly controls the grouping dimensions. If you include SALE_ID, CUSTOMER_ID, or CREATED_AT in the source without using them as the pivot key or measure, those columns become implicit grouping keys and cause the result to have more rows than expected.

This is a key characteristic of Oracle PIVOT: **source columns not used in the pivot clause or as measure arguments participate in implicit grouping**. Always construct an inline view with the exact set of required columns before pivoting.

## 3. Implicit Grouping in PIVOT

### 3.1 PIVOT automatically groups by remaining columns

Example:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

Oracle groups by REGION because:

- QUARTER is the pivot column.
- AMOUNT is the measure being SUMmed.
- REGION is the remaining column.

The result has one row per REGION within the grouped dataset.

### 3.2 Adding an unwanted column changes the grouping level

~~~sql
SELECT *
FROM (
    SELECT sale_id,
           region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

Because SALE_ID is neither the pivot column nor the measure, it becomes part of the implicit grouping. If each sale_id is unique, the output can turn into one row per transaction instead of one row per region.

To aggregate by REGION, remove SALE_ID from the inline view:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

### 3.3 PIVOT has no explicit GROUP BY

In PIVOT syntax, grouping columns are determined implicitly from the source. Do not mechanically add an outer GROUP BY. If you need to change the aggregation level, control the inline view's SELECT list or apply a subquery/grouping before PIVOT.

## 4. PIVOT with Multiple Aggregate Functions

A report may require revenue, transaction count, and average value for each quarter. Oracle lets you list multiple aggregates inside the same PIVOT:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue,
    COUNT(*) AS transaction_count,
    AVG(amount) AS average_amount
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Output columns are generated for each combination of pivot value and aggregate alias, for example:

- Q1_REVENUE
- Q1_TRANSACTION_COUNT
- Q1_AVERAGE_AMOUNT
- Q2_REVENUE
- Q2_TRANSACTION_COUNT
- Q2_AVERAGE_AMOUNT

Exact names depend on the declared aliases. Choose short, clear, non-colliding aliases to avoid ambiguous generated column names or exceeding the version's identifier length limit.

### 4.1 COUNT(*) and COUNT(measure) behave differently

Suppose a transaction has a NULL AMOUNT:

- COUNT(*) counts the transaction row.
- COUNT(amount) counts only rows with a non-NULL AMOUNT.
- SUM(amount) ignores NULL values; if all values in the group are NULL, the sum can be NULL.

This is an important distinction when reporting transaction counts and total amounts.

### 4.2 Missing data vs. NULL data

If a region has one Q2 row with NULL AMOUNT, COUNT(*) indicates that a transaction row exists, COUNT(amount) indicates there is no non-NULL amount value, and SUM(amount) does not produce a known total amount.

If there are no Q2 rows at all for that region, the pivot result for the measure may be NULL or a count value according to aggregate semantics. To distinguish clearly, include both COUNT(*) and COUNT(measure) in the report when business logic needs to distinguish:

1. No transaction rows exist.
2. Transaction rows exist, but the measure has not been recorded.
3. Transaction rows exist with measure equal to 0.

Do not convert every NULL to 0 if these three states carry different meanings.

## 5. PIVOT with Filtering and Multiple Dimensions

### 5.1 Filtering data before PIVOT

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
    WHERE sale_year = 2026
      AND status = 'CONFIRMED'
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

WHERE sits inside the inline view, filtering source rows before aggregation. This is a clean way to define the report scope.

### 5.2 Pivoting by status

Example of order counts by status:

~~~sql
SELECT *
FROM (
    SELECT region,
           order_status,
           order_id
    FROM orders
)
PIVOT (
    COUNT(order_id) AS order_count
    FOR order_status IN (
        'NEW' AS new,
        'PAID' AS paid,
        'CANCELLED' AS cancelled
    )
);
~~~

The result can have NEW_ORDER_COUNT, PAID_ORDER_COUNT, and CANCELLED_ORDER_COUNT per REGION. Use COUNT(order_id) if ORDER_ID is a non-NULL key; COUNT(*) can also be used to count source rows.

### 5.3 Multi-dimensional pivot by grouping level

If you want to report by REGION and CHANNEL, keep both in the inline view:

~~~sql
SELECT *
FROM (
    SELECT region,
           channel,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
)
ORDER BY region, channel;
~~~

The result has one row per REGION and CHANNEL combination. Both columns serve as implicit grouping columns because neither is the pivot key or the measure.

## 6. Static PIVOT and Value Lists

### 6.1 The IN list is fixed in the SQL statement

In standard PIVOT, the values in IN are declared explicitly:

~~~sql
FOR quarter IN (
    'Q1' AS q1,
    'Q2' AS q2,
    'Q3' AS q3,
    'Q4' AS q4
)
~~~

This lets Oracle know the metadata and output column names when parsing the SQL statement. If a new value such as Q5 appears in the data without Q5 listed in IN, a Q5 column will not automatically appear in the static pivot result.

### 6.2 Aliases for pivot values

Aliases name the output columns:

~~~sql
FOR month_no IN (
    1 AS jan,
    2 AS feb,
    3 AS mar
)
~~~

When combined with an aggregate alias:

~~~sql
PIVOT (
    SUM(amount) AS total
    FOR month_no IN (1 AS jan, 2 AS feb, 3 AS mar)
)
~~~

the columns are named JAN_TOTAL, FEB_TOTAL, and MAR_TOTAL.

Use explicit aliases rather than relying on names auto-generated from literals, especially when pivot values are long strings or contain special characters.

### 6.3 Values omitted from IN

If the data contains an unlisted pivot value such as Q5, static PIVOT does not create a Q5 column. Rows with Q5 are not included in any of the Q1–Q4 columns. Verify the data scope and category list before publishing reports.

## 7. PIVOT XML for Flexible Value Sets

When categories change frequently and the full list is not known in advance, Oracle supports PIVOT XML. The output uses an XMLType column to represent pivot values instead of generating a data-dependent number of relational columns.

### 7.1 Using a subquery in IN

~~~sql
SELECT *
FROM (
    SELECT region,
           product,
           amount
    FROM sales
)
PIVOT XML (
    SUM(amount) AS revenue
    FOR product IN (
        SELECT DISTINCT product
        FROM sales
    )
);
~~~

The subquery in IN determines the set of product values. For PIVOT XML using a subquery, the value set must meet Oracle's uniqueness requirement; DISTINCT is commonly used when selecting from the source table.

The result contains the grouping columns along with one XMLType column holding the pivoted data. The application must read/parse the XML to render each category.

### 7.2 Using ANY

~~~sql
SELECT *
FROM (
    SELECT region,
           product,
           amount
    FROM sales
)
PIVOT XML (
    SUM(amount) AS revenue
    FOR product IN (ANY)
);
~~~

ANY instructs Oracle to include the pivot values present in the relevant data of each group in the XML output. This is a useful option when you want to represent actual categories without listing them manually.

### 7.3 PIVOT XML does not generate dynamic relational columns

PIVOT XML still returns a fixed result set schema in which the pivoted data is packed inside XMLType. If the client requires Q1, Q2, and Q3 columns generated dynamically in SQL metadata, XML does not turn itself into separate relational columns.

To get truly dynamic columns, the application usually has to generate dynamic SQL from the category list, parse the new SQL statement, and handle the resulting schema accordingly. Validate values and identifiers placed into dynamic SQL; never concatenate raw user input into SQL.

## 8. UNPIVOT: Converting Multiple Columns into Rows

### 8.1 Basic syntax

~~~sql
SELECT ...
FROM source_table
UNPIVOT [INCLUDE NULLS | EXCLUDE NULLS] (
    measure_column
    FOR pivot_column
    IN (
        source_column_1 [AS value_1],
        source_column_2 [AS value_2],
        ...
    )
);
~~~

Components:

| Component | Role |
|---|---|
| measure_column | Result column holding values taken from the source columns |
| pivot_column | Result column holding labels indicating which source column the value came from |
| source_column | Wide columns to be converted into rows |
| value alias | Label for each source column, e.g., Q1 or JAN |
| INCLUDE NULLS | Keeps unpivoted rows whose measure is NULL |
| EXCLUDE NULLS | Drops unpivoted rows whose measure is NULL; this is the default |

UNPIVOT does not aggregate data. It transforms a multi-column layout into multiple rows.

### 8.2 Quarterly UNPIVOT example

Suppose the QUARTERLY_SALES_WIDE table has:

| REGION | Q1_SALES | Q2_SALES | Q3_SALES | Q4_SALES |
|---|---:|---:|---:|---:|
| North | 100 | 120 | 90 | 130 |
| South | 80 | 110 | 130 | 140 |

Query:

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Output:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| North | Q4 | 130 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |
| South | Q4 | 140 |

Source columns Q1_SALES...Q4_SALES become values of a single REVENUE column; source column names are mapped into labels in QUARTER.

### 8.3 Non-unpivoted columns are preserved

In the example, REGION does not appear in the IN list, so it is kept as the identifying column for each group of rows. If the table also has CUSTOMER_ID, PRODUCT, or YEAR and those columns are not unpivoted, they are preserved in the output as well.

Include only the necessary identifying columns in the source if you want the result to remain easy to read without multiplying rows excessively.

## 9. INCLUDE NULLS and EXCLUDE NULLS

By default, UNPIVOT uses EXCLUDE NULLS. Source columns with NULL values will not produce rows in the output. You can use INCLUDE NULLS to keep them.

### 9.1 Example with NULL and zero

Suppose:

| REGION | Q1_SALES | Q2_SALES | Q3_SALES |
|---|---:|---:|---:|
| North | 100 | NULL | 0 |

Default UNPIVOT:

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3'
    )
);
~~~

The result contains only Q1 with 100 and Q3 with 0. The Q2 row is omitted because the source value is NULL. The value 0 is kept because 0 is not NULL.

### 9.2 INCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT INCLUDE NULLS (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3'
    )
);
~~~

The result includes Q1, Q2, and Q3; Q2 has a NULL REVENUE. This is the choice when reports must distinguish:

- A period with a value of 0.
- A period with unrecorded/missing data.

### 9.3 NULL carries business meaning

If NULL means "data not yet reported", dropping rows during UNPIVOT can lose that fact. If NULL means "not applicable", business logic may prefer excluding it. Choose INCLUDE or EXCLUDE based on data semantics, not simply to get fewer rows.

## 10. UNPIVOT Multiple Measures Simultaneously

A wide table may store both quantity and revenue per quarter:

| REGION | Q1_QTY | Q1_REVENUE | Q2_QTY | Q2_REVENUE |
|---|---:|---:|---:|---:|
| North | 10 | 1000 | 12 | 1300 |
| South | 8 | 800 | 9 | 950 |

You can unpivot by column tuples:

~~~sql
SELECT region,
       quarter,
       quantity,
       revenue
FROM quarterly_metrics_wide
UNPIVOT (
    (quantity, revenue)
    FOR quarter IN (
        (q1_qty, q1_revenue) AS 'Q1',
        (q2_qty, q2_revenue) AS 'Q2',
        (q3_qty, q3_revenue) AS 'Q3',
        (q4_qty, q4_revenue) AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Each pair Q1_QTY/Q1_REVENUE becomes one Q1 row with two measures: QUANTITY and REVENUE. The same applies to the remaining quarters.

### 10.1 Columns must have compatible data types

UNPIVOT requires columns placed in the same measure group to have compatible data types according to Oracle rules. For a single measure, source columns must belong to the same data type group; Oracle has conversion rules within the numeric group. Do not arbitrarily mix NUMBER with VARCHAR2 or DATE in the same measure.

For multi-measure UNPIVOT, corresponding columns across tuples must be compatible position by position: all quantity columns compatible with one another, all revenue columns compatible with one another. Otherwise Oracle may raise an incompatible datatype error.

If source columns have different types, explicitly CAST them to the target type in an inline view before UNPIVOT, while specifying formatting and how unconvertible data should be handled.

### 10.2 INCLUDE NULLS with multiple measures

With multi-column tuples, define the NULL policy for the whole measure group and test on representative data. INCLUDE NULLS is useful if you need to retain periods where one or more measures are unrecorded; the application must understand that each measure can be NULL independently.

## 11. PIVOT vs. Conditional Aggregation

You do not always need PIVOT syntax. Report columns can be built using aggregates combined with CASE:

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2_revenue,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3_revenue,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4_revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

This is **conditional aggregation**.

### 11.1 Comparing the two approaches

PIVOT:

~~~sql
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
);
~~~

Conditional aggregation:

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4
FROM sales
GROUP BY region;
~~~

Both approaches produce equivalent results when using the same grouping, conditions, and aggregate semantics.

| Criterion | PIVOT | Conditional aggregation |
|---|---|---|
| Intent to rotate values into columns | Direct, recognizable syntax | Requires writing CASE for each column |
| Different conditions per column | May require extra expressions or query layers | Flexible inside each CASE |
| Multiple aggregates | Supports multiple functions in one PIVOT | Write multiple aggregate expressions |
| Static category list | Explicit IN list | Explicit CASE list |
| Dynamic categories | PIVOT XML or dynamic SQL | Dynamic SQL or long/XML format |
| Ease of handling special logic | Fits standard pivot patterns | Often more flexible |

### 11.2 Counting transactions and counting non-NULL values

~~~sql
SELECT region,
       COUNT(CASE WHEN quarter = 'Q1' THEN 1 END) AS q1_rows,
       COUNT(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_known_amounts,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue
FROM sales
GROUP BY region;
~~~

Q1_ROWS counts Q1 rows; Q1_KNOWN_AMOUNTS counts only rows with non-NULL AMOUNT; Q1_REVENUE sums non-NULL amounts. These three columns help reports distinguish no transactions, transactions with missing amount, and transactions with amount equal to 0.

### 11.3 Do not default SUM NULL to 0

If no rows match a quarter, SUM(CASE WHEN ... THEN amount END) returns NULL. You can use NVL:

~~~sql
NVL(
  SUM(CASE WHEN quarter = 'Q1' THEN amount END),
  0
) AS q1_revenue
~~~

Do this only if the report intentionally represents "no value" as 0. If you must distinguish no transactions occurring from transactions with unrecorded amounts, preserve NULL and add an appropriate COUNT.

### 11.4 PIVOT is not inherently faster

PIVOT and conditional aggregation can be transformed by the optimizer into similar aggregation operations. Do not claim one syntax is always faster than the other. Pick the one that expresses the logic clearly, then measure on realistic data and inspect the execution plan when tuning is needed.

## 12. PIVOT and UNPIVOT Are Not Perfect Inverses

In appearance, PIVOT turns long into wide; UNPIVOT turns wide into long. Yet the two operations do not always reverse each other cleanly.

### 12.1 PIVOT usually aggregates and loses detail

If the source has:

| REGION | QUARTER | AMOUNT |
|---|---|---:|
| North | Q1 | 100 |
| North | Q1 | 50 |

PIVOT SUM produces Q1 = 150. A subsequent UNPIVOT only recovers a single North/Q1/150 row; it cannot know there were originally two transactions of 100 and 50.

Detailed granularity was lost due to SUM. To preserve detail, you would need to retain the transaction key or avoid aggregating at that level; however, the pivoted output would then contain more rows.

### 12.2 EXCLUDE NULLS drops additional rows

If the wide table has a NULL Q2, default UNPIVOT drops the Q2 row. Even without prior aggregation losing data, choosing EXCLUDE NULLS loses the fact that the Q2 cell existed with no value.

Use INCLUDE NULLS if you need to preserve NULL cells structurally.

### 12.3 Static PIVOT keeps only listed categories

If the IN list only contains Q1–Q4 while source data has Q5, no Q5 column is created. Therefore pivoting and then unpivoting cannot recover categories omitted from the list.

### 12.4 Without a row key, original order cannot be restored

Relations in Oracle have no guaranteed natural order. After PIVOT/UNPIVOT, without a key and ORDER BY, you cannot reconstruct the original row order. If row order or record identity must be preserved, store keys and sort explicitly.

## 13. PIVOT/UNPIVOT in Report Design

### 13.1 When stored data should be long format

Model:

~~~text
SALES
  SALE_ID
  REGION
  SALE_DATE
  PRODUCT_ID
  AMOUNT
~~~

works well when:

- Categories change over time.
- There are many years, months, quarters, or statuses.
- Filtering, grouping, joining, and multi-dimensional analytics are needed.
- Data is ingested continuously from transactions.

There is no need to add Q1, Q2, Q3, and Q4 columns to the transaction table just for quarterly reporting.

### 13.2 When wide format is appropriate

Wide format can be useful when:

- Exporting reports with a fixed column count.
- Creating cross-tab tables for human readers.
- Integrating with Excel templates or UIs that expect each period as a column.
- Feeding downstream systems with a fixed schema.

Produce wide format in an appropriate view, query, or reporting mart layer rather than compromising a normalized transactional model.

### 13.3 Separating the data layer and presentation layer

A maintainable architecture typically looks like:

~~~text
Long-format transaction table
          |
          v
Filter and normalize data
          |
          v
Aggregate by dimensions
          |
          v
PIVOT / conditional aggregation
          |
          v
Wide report for users
~~~

If the system needs to reuse figures across multiple reports, consider a view or materialized view depending on frequency, latency, and refresh policy. PIVOT in a SELECT does not create a physical table or persist results on its own.

## 14. Lab: PIVOT Long-Format Revenue Data

The statements in this section are intended for a private practice schema with table creation privileges and appropriate quota. Do not run test DDL/DML in a production schema. Oracle DDL such as CREATE TABLE performs an implicit commit.

### 14.1 Create the source table

~~~sql
CREATE TABLE lab_sales_long (
    sale_id NUMBER PRIMARY KEY,
    region  VARCHAR2(20) NOT NULL,
    quarter VARCHAR2(2) NOT NULL,
    amount  NUMBER(12,2)
);
~~~

### 14.2 Load data

~~~sql
INSERT INTO lab_sales_long VALUES (1, 'North', 'Q1', 100);
INSERT INTO lab_sales_long VALUES (2, 'North', 'Q1', 50);
INSERT INTO lab_sales_long VALUES (3, 'North', 'Q2', 120);
INSERT INTO lab_sales_long VALUES (4, 'North', 'Q3', 90);
INSERT INTO lab_sales_long VALUES (5, 'South', 'Q1', 80);
INSERT INTO lab_sales_long VALUES (6, 'South', 'Q2', 110);
INSERT INTO lab_sales_long VALUES (7, 'South', 'Q3', 130);
INSERT INTO lab_sales_long VALUES (8, 'East', 'Q2', NULL);
INSERT INTO lab_sales_long VALUES (9, 'East', 'Q4', 0);
COMMIT;
~~~

The dataset includes multiple transactions for North/Q1, a NULL measure at East/Q2, and a 0 value at East/Q4.

### 14.3 Inspect source data

~~~sql
SELECT region,
       quarter,
       amount
FROM lab_sales_long
ORDER BY region, quarter, sale_id;
~~~

### 14.4 Pivot revenue by quarter

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Expected totals:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE | Q4_REVENUE |
|---|---:|---:|---:|---:|
| East | NULL | NULL | NULL | 0 |
| North | 150 | 120 | 90 | NULL |
| South | 80 | 110 | 130 | NULL |

North's Q1 is 150 because there are two rows: 100 and 50. East's Q2 is NULL because its only row has AMOUNT NULL; East's Q4 is 0 because there is a row with value 0.

### 14.5 Pivot multiple aggregates

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue,
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

For East/Q2, observe:

- Q2_REVENUE is NULL because that row's amount is NULL.
- Q2_ROW_COUNT reflects that one source row exists.
- Q2_KNOWN_AMOUNT_COUNT is 0 because there are no non-NULL amounts.

For East/Q4, an amount of 0 is a known value; COUNT(amount) counts this row. This is how to distinguish NULL from zero.

### 14.6 Compare with conditional aggregation

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2_revenue,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3_revenue,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4_revenue
FROM lab_sales_long
GROUP BY region
ORDER BY region;
~~~

Compare with the PIVOT output. With the same grouping and aggregates, the totals match.

## 15. Lab: UNPIVOT Wide Data

### 15.1 Create the wide table

~~~sql
CREATE TABLE lab_sales_wide (
    region    VARCHAR2(20) PRIMARY KEY,
    q1_sales  NUMBER(12,2),
    q2_sales  NUMBER(12,2),
    q3_sales  NUMBER(12,2),
    q4_sales  NUMBER(12,2)
);
~~~

### 15.2 Load data

~~~sql
INSERT INTO lab_sales_wide VALUES ('North', 100, 120, NULL, 0);
INSERT INTO lab_sales_wide VALUES ('South', 80, NULL, 90, 140);
COMMIT;
~~~

North/Q3 and South/Q2 are NULL; North/Q4 is 0.

### 15.3 Default UNPIVOT EXCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM lab_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

The output omits North/Q3 and South/Q2 because those cells are NULL. North/Q4 still appears with revenue 0.

### 15.4 UNPIVOT INCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM lab_sales_wide
UNPIVOT INCLUDE NULLS (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

The output contains all eight region/quarter combinations, including the two NULL rows. This is the right option when you need to preserve missing-data state for each period.

### 15.5 UNPIVOT multiple measures

Create an illustrative table:

~~~sql
CREATE TABLE lab_quarter_metrics (
    region      VARCHAR2(20),
    q1_qty      NUMBER(10),
    q1_revenue  NUMBER(12,2),
    q2_qty      NUMBER(10),
    q2_revenue  NUMBER(12,2)
);
~~~

Load:

~~~sql
INSERT INTO lab_quarter_metrics VALUES ('North', 10, 1000, 12, 1300);
INSERT INTO lab_quarter_metrics VALUES ('South', 8, 800, 9, 950);
COMMIT;
~~~

Query:

~~~sql
SELECT region,
       quarter,
       quantity,
       revenue
FROM lab_quarter_metrics
UNPIVOT (
    (quantity, revenue)
    FOR quarter IN (
        (q1_qty, q1_revenue) AS 'Q1',
        (q2_qty, q2_revenue) AS 'Q2'
    )
)
ORDER BY region, quarter;
~~~

Each pair of columns becomes one row with two measures. When adding a new quarter, you must add the source columns and the corresponding tuple in the IN list.

### 15.6 Clean up lab tables

Drop only tables you created in your practice schema after confirming you no longer need the data. Do not put DROP TABLE in scripts that could accidentally run against production; DDL performs an implicit commit and you cannot rely on ROLLBACK to recover.

## 16. Dynamic PIVOT: When Categories Change

A static PIVOT statement must declare its IN list at parse time. If a report needs to add columns automatically based on existing categories, there are two main approaches.

### 16.1 PIVOT XML

PIVOT XML allows using a subquery or ANY to determine pivot values dynamically, returning the pivoted result in XMLType. This works well when the client can process XML or requires a fixed result-set schema.

### 16.2 Generating dynamic SQL

The application can query the category list, build a validated literal/alias list, and generate a new PIVOT statement. Each category list produces a different result-set shape.

When generating dynamic SQL:

- Pull categories only from a controlled data source or allowlist.
- Escape literals properly; never concatenate raw user input.
- Identifiers/aliases cannot be substituted using regular bind variables; validate and quote identifiers according to Oracle rules.
- Data filter values should still use bind variables.
- The client must handle column metadata changing across executions.

There is no standard static SELECT statement that returns an arbitrary data-driven number of relational columns while keeping fixed metadata. If the application does not truly require dynamic columns, returning long-format data is usually simpler.

## 17. Common Errors and Misconceptions

| Error/misconception | Cause | How to handle |
|---|---|---|
| PIVOT just renames columns without aggregating | PIVOT performs aggregation and implicit grouping | Choose an appropriate aggregate |
| Output has too many rows | PIVOT source has extra unwanted columns becoming grouping keys | Trim the inline view's SELECT list |
| New category values automatically appear as columns | Static PIVOT creates only columns in the IN list | Update IN, use PIVOT XML, or use dynamic SQL |
| PIVOT returns NULL so I assumed no rows exist | Rows may exist with a NULL measure | Add COUNT(*) and COUNT(measure) |
| COUNT(*) and COUNT(amount) are the same | COUNT(amount) ignores NULLs | Pick based on counting rows vs. counting known values |
| UNPIVOT drops some periods | Default is EXCLUDE NULLS | Use INCLUDE NULLS if NULL cells must be kept |
| Zero values get dropped during UNPIVOT | Confusing 0 with NULL | 0 is kept; check data types and source values |
| UNPIVOT works on any mix of column types | Source columns must share a compatible datatype group | CAST in an inline view when justified |
| PIVOT followed by UNPIVOT always restores original data | Aggregation, EXCLUDE NULLS, and omitted categories lose information | Preserve keys/detail and verify semantics |
| PIVOT is always faster than CASE | Optimizer and workload decide | Compare actual plans on representative data |
| Dynamic columns can be bound like WHERE values | The IN list determines column metadata at parse time | Use XML or safe dynamic SQL generation |
| PIVOT XML creates a separate relational column per category | XML packs values into one XMLType column | Parse XML or use dynamic SQL if separate columns are needed |

## 18. Performance and Architectural Choices

### 18.1 Control the number of grouping dimensions

PIVOT groups by all remaining source columns. Bringing too many columns into the inline view can multiply groups and fragment results. Select only the exact dimensions to retain before pivoting.

### 18.2 Filter early when possible

If reporting on only one year or status, place the filter inside the inline view to restrict the source. This makes the data scope clear and can reduce the number of rows to aggregate. The optimizer still decides physical execution order based on cost and transformations.

### 18.3 Indexing for the source query

Indexes can help filter predicates and joins prior to PIVOT/UNPIVOT. For example, a report filtering by YEAR, REGION, and QUARTER may warrant checking existing indexes, selectivity, partitioning, and workload. Do not create indexes based solely on one sample SQL query.

### 18.4 PIVOT in views and materialized views

A view containing PIVOT encapsulates query logic and does not persist results by itself. If a report is heavy and run frequently, evaluate a materialized view or reporting table based on freshness requirements, refresh schedule, and query rewrite capabilities. This is a separate architectural decision, not a requirement of PIVOT syntax.

### 18.5 Inspecting the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2, 'Q3' AS q3, 'Q4' AS q4)
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN shows the estimated plan, not real-time measurements. When tuning, inspect the actual plan, cardinality, sort/hash operations, I/O, CPU, and representative data volumes.

## 19. Reporting Query Design Checklist

Before writing PIVOT or UNPIVOT, determine:

1. Is the input data in long or wide format?
2. Does each source row represent a transaction, a group, or a pre-aggregated summary?
3. Which columns must be kept as dimensions?
4. Which column is the pivot key, and which is the measure?
5. Do you need SUM, COUNT, AVG, MIN, or MAX?
6. If the measure is NULL, should the report keep NULL, display 0, or distinguish from missing rows?
7. Are categories fixed? If dynamic, can the client handle XML or changing column schemas?
8. For UNPIVOT, do you need INCLUDE NULLS?
9. Do the source columns belong to compatible datatype groups?
10. Does PIVOT lose detail via aggregation? Do transaction keys need to be kept?
11. What sort order does the output need? Add an explicit ORDER BY.
12. Does the query need indexes, partition pruning, a view, or a materialized view?

## 20. Self-Study Exercises

**Question 1 — Quarterly PIVOT.** From LAB_SALES_LONG, write a query turning Q1, Q2, Q3, Q4 into total revenue columns by REGION.

Hint:

~~~sql
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
);
~~~

**Question 2 — Implicit grouping.** If SALE_ID is added to the inline view in Question 1, why can the result turn into multiple rows per REGION?

Hint: SALE_ID is neither the pivot key nor the measure, so it becomes part of the implicit grouping.

**Question 3 — Multiple aggregates.** Add COUNT(*) and COUNT(amount) to PIVOT to distinguish source row count from known measure count.

Hint: Give each aggregate a distinct alias so generated column names are clear.

**Question 4 — UNPIVOT NULL.** Run default UNPIVOT on LAB_SALES_WIDE and explain why North/Q3 does not appear.

Hint: The default is EXCLUDE NULLS. Re-run with INCLUDE NULLS to keep that row.

**Question 5 — Zero and NULL.** Why does North/Q4 still appear in default UNPIVOT even though revenue is 0?

Hint: 0 is a numeric value; only NULL is excluded.

**Question 6 — Dynamic pivot.** When new product categories are added every month, state two approaches so the report reflects new categories.

Hint: PIVOT XML with a subquery/ANY or safe dynamic SQL generation. If the client accepts long-format data, dynamic pivoting may not be needed.

**Question 7 — PIVOT then UNPIVOT.** If two North/Q1 transactions are 100 and 50, can PIVOT SUM followed by UNPIVOT restore both individual transactions?

Hint: No. SUM combined them into 150 and lost the identity of the two source rows.

**Question 8 — Choosing PIVOT vs. CASE.** A report needs Q1 confirmed revenue, Q2 revenue across all statuses, and Q3 failed transaction count. Which approach makes it easier to express separate conditions per column?

Hint: Conditional aggregation with CASE is usually more flexible when each column has a different predicate.

## 21. Summary

PIVOT and UNPIVOT are two tools for reshaping reporting data in Oracle:

- **PIVOT** turns values of a dimension into columns while applying aggregates such as SUM or COUNT. Remaining source columns form implicit grouping, so the inline view should contain only the intended dimensions and measures.
- **PIVOT XML** supports flexible categories by returning pivoted data inside XMLType; getting dynamic relational columns requires XML processing or controlled dynamic SQL generation.
- **UNPIVOT** converts multiple columns into rows and generates labels for the source columns. Default is EXCLUDE NULLS; INCLUDE NULLS preserves cells without values.
- **Conditional aggregation** is a flexible alternative when each report column needs its own condition or explicit logic control.
- PIVOT and UNPIVOT are not perfect inverses: aggregation, excluded NULLs, and omitted categories can lose information.

Design transactional data with clear semantics, apply PIVOT/UNPIVOT in the reporting layer where appropriate, manage grouping and NULLs carefully, and inspect execution plans on representative data. With a solid grasp of these rules, you can produce readable cross-tab reports while maintaining accuracy and maintainability in Oracle queries.
