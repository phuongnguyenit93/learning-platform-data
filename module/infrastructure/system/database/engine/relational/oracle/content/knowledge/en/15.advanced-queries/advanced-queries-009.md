# The MODEL Clause and Cell-Based Spreadsheet Calculations

In a revenue report, data may be grouped by product and year. From historical revenue, we may want to generate forecast cells for subsequent years, compute variance against budget, allocate targets across months, or propagate values across multiple periods. Writing each calculation as a separate query and JOINing the results quickly makes SQL verbose and difficult to follow.

Oracle Database provides the **MODEL clause** to treat data as a multi-dimensional model composed of **cells**. Each cell is identified by dimension values (*dimensions*) and holds one or more measure values (*measures*). You can reference a cell, compute new values, update existing cells, or create missing cells using *rules*.

This lesson focuses on visualizing the cell grid, declaring `PARTITION BY`, `DIMENSION BY`, `MEASURES`, cell references, `CV()`, `UPDATE`/`UPSERT` rules, evaluation order, iterative calculations, and handling missing values. The main example models revenue forecasting by product and year.

## 1. What Problems Does the MODEL Clause Solve?

Suppose a sales table has columns:

| PRODUCT_ID | FISCAL_YEAR | SALES_AMOUNT |
|---:|---:|---:|
| 10 | 2023 | 100 |
| 10 | 2024 | 120 |
| 20 | 2023 | 80 |
| 20 | 2024 | 88 |

Reporting requirements:

- Keep historical revenue.
- Create a 2025 forecast cell equal to 2024 revenue increased by 10%.
- Next, create a 2026 cell based on the 2025 value.
- Perform this independently for each product.

With ordinary projection, you can compute a forecast column for existing rows, but it is awkward to naturally express **years that do not yet exist as rows in the source table**. MODEL lets you explicitly define cells by dimensions and assignment rules:

~~~text
PRODUCT_ID = 10

FISCAL_YEAR     2023    2024    2025    2026
SALES_AMOUNT     100     120     132     145.2
                              ^       ^
                          new cell new cell

PRODUCT_ID = 20

FISCAL_YEAR     2023    2024    2025    2026
SALES_AMOUNT      80      88     96.8   106.48
~~~

The model does not have to be displayed as a horizontal matrix. The SQL output can still be rows of `PRODUCT_ID`, `FISCAL_YEAR`, and `SALES_AMOUNT`; the matrix visualization simply helps understand referencing and computing on each cell.

### 1.1 Four core concepts to master

| Concept | Meaning in MODEL | Example |
|---|---|---|
| Partition | Independent model group; rules run separately per group | Each `PRODUCT_ID` |
| Dimension | Coordinate used to locate a cell | `FISCAL_YEAR` |
| Measure | Value stored/computed inside a cell | `SALES_AMOUNT` |
| Cell | A single location defined by a dimension tuple within a partition | Product 10, year 2024 |

A helpful mnemonic:

- **Partition** answers: which model is calculated independently?
- **Dimension** answers: which cell?
- **Measure** answers: which value sits inside the cell?
- **Rule** answers: how is the cell's value calculated?

## 2. Preparing the Practice Sales Table

In a practice schema permitted to create tables, run:

~~~sql
CREATE TABLE lab_sales_plan (
    product_id   NUMBER(6) NOT NULL,
    fiscal_year  NUMBER(4) NOT NULL,
    sales_amount NUMBER(14,2),
    CONSTRAINT pk_lab_sales_plan
        PRIMARY KEY (product_id, fiscal_year)
);
~~~

Load data:

~~~sql
INSERT ALL
    INTO lab_sales_plan VALUES (10, 2023, 100)
    INTO lab_sales_plan VALUES (10, 2024, 120)
    INTO lab_sales_plan VALUES (20, 2023, 80)
    INTO lab_sales_plan VALUES (20, 2024, 88)
SELECT 1 FROM dual;

COMMIT;
~~~

Verify:

~~~sql
SELECT product_id, fiscal_year, sales_amount
FROM lab_sales_plan
ORDER BY product_id, fiscal_year;
~~~

The primary key `(PRODUCT_ID, FISCAL_YEAR)` guarantees each product has at most one row per year in the source table. This is also an essential data precondition so the model has a unique cell for every dimension combination within each partition.

## 3. General Structure of the MODEL Clause

General template:

~~~sql
SELECT select_list
FROM source_table
MODEL
    [PARTITION BY (partition_expression, ...)]
    DIMENSION BY (dimension_expression, ...)
    MEASURES (measure_expression, ...)
    [IGNORE NAV | KEEP NAV]
    [RULES
        [UPDATE | UPSERT [ALL]]
        [AUTOMATIC ORDER | SEQUENTIAL ORDER]
        [ITERATE (number) [UNTIL (condition)]]
        (
            measure[cell_reference] = expression,
            ...
        )
    ]
ORDER BY ...;
~~~

This skeleton illustrates common components; when writing actual SQL, follow the exact syntax ordering of the Oracle release in use.

Components:

1. `PARTITION BY` splits the source into independent models.
2. `DIMENSION BY` declares the columns identifying cells.
3. `MEASURES` declares the values that can be read and computed.
4. `RULES` describes how values are assigned to cells.
5. `UPDATE`/`UPSERT` controls whether a cell is created when the target cell does not exist yet.
6. `SEQUENTIAL ORDER`/`AUTOMATIC ORDER` controls rule evaluation order.
7. `ITERATE` allows applying rules repeatedly.

MODEL is an Oracle SQL extension. This syntax cannot be copied verbatim to every other database management system.

## 4. PARTITION BY: Splitting the Model into Independent Groups

Example forecasting revenue independently for each product:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

`PARTITION BY (product_id)` creates a separate model per product. When the rule computes `sales_amount[2025]`, the reference to year 2024 is looked up **within the same product partition**. Thus:

- Product 10's partition uses 120 to compute 2025.
- Product 20's partition uses 88 to compute 2025.

Product 10 will never pick up product 20's 2024 revenue.

### 4.1 Without PARTITION BY

If you do not need separate independent models, `PARTITION BY` can be omitted:

~~~sql
SELECT fiscal_year,
       sales_amount
FROM some_single_product_source
MODEL
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

Then all source rows belong to one model. If the dimensions are insufficient to distinguish rows across products, a single year will no longer identify a unique cell. Therefore, when data contains multiple products, you must normally either:

- Put `PRODUCT_ID` in `PARTITION BY`, or
- Put `PRODUCT_ID` in `DIMENSION BY` if cross-product references within the same model are needed.

Never omit an identifying dimension merely to shorten the SQL statement.

### 4.2 Partition vs. dimension

Two declarations organize the model differently:

~~~sql
PARTITION BY (product_id)
DIMENSION BY (fiscal_year)
~~~

Each product is its own model, and the only dimension is year.

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

All products sit in a single model; each cell is addressed by both product ID and year. Cell references must supply coordinates for the corresponding dimensions.

Choose partition when calculations per group are independent and you want that boundary explicit. Choose multiple dimensions when rules must cross-reference across products or groups within one model.

## 5. DIMENSION BY: Defining Cell Coordinates

With the practice data:

~~~sql
DIMENSION BY (fiscal_year)
~~~

`FISCAL_YEAR` is the dimension. Each year value identifies a slot within the partition:

| Dimension value | Measure at cell |
|---:|---:|
| 2023 | 100 |
| 2024 | 120 |
| 2025 | Not yet in source data |
| 2026 | Not yet in source data |

A dimension does not have to be numeric. It can be a date, string, or expression with a compatible data type. For example:

~~~sql
DIMENSION BY (month_start)
~~~

or:

~~~sql
DIMENSION BY (region_code, fiscal_year)
~~~

### 5.1 Each dimension tuple within a partition must identify one cell

In a single-dimension model, a partition should not contain two source rows with the same `FISCAL_YEAR` representing two distinct values of the same measure. In a multi-dimensional model, the combination of dimensions must uniquely address a cell as required by the model.

If the source has multiple rows for the same product/year, establish the grain first:

~~~sql
SELECT product_id,
       fiscal_year,
       SUM(sales_amount) AS sales_amount
FROM raw_sales
GROUP BY product_id, fiscal_year;
~~~

Then feed the aggregated result into MODEL. Failing to resolve duplicate dimensions can trigger a non-unique dimension error such as `ORA-32638: Non unique addressing in MODEL dimensions`.

Never use `DISTINCT` mechanically to hide duplicates; two rows sharing the same dimensions may carry different measure values that need business aggregation.

### 5.2 Date-typed dimensions

Example monthly model:

~~~sql
SELECT product_id,
       month_start,
       sales_amount
FROM monthly_sales
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (month_start)
    MEASURES (sales_amount)
    RULES (
        sales_amount[DATE '2026-01-01'] =
            sales_amount[DATE '2025-12-01'] * 1.05
    )
ORDER BY product_id, month_start;
~~~

Here dimension values are first-of-month dates. Use date literals for stable cell addressing; never rely on string dates tied to `NLS_DATE_FORMAT`.

## 6. MEASURES: Values Stored Inside Each Cell

`MEASURES` declares the expressions/values stored as cell contents. Example:

~~~sql
MEASURES (sales_amount)
~~~

Multiple measures are allowed:

~~~sql
MEASURES (
    sales_amount,
    budget_amount,
    sales_amount - budget_amount AS variance
)
~~~

In this example:

- `SALES_AMOUNT` is revenue.
- `BUDGET_AMOUNT` is budget.
- `VARIANCE` is a measure computed from the two input expressions.

Measures can be referenced in rules:

~~~sql
RULES (
    variance[2024] = sales_amount[2024] - budget_amount[2024]
)
~~~

A measure is a value inside each cell, not a dimension locating the cell. If you need to address a cell by year and region, those attributes belong in `DIMENSION BY`; putting `SALES_AMOUNT` into `MEASURES` does not make it a coordinate.

## 7. Cell Referencing: measure[dimension value]

In MODEL, a cell reference typically takes the form:

~~~sql
measure[dimension_value]
~~~

With multiple dimensions, supply values in the exact declared dimension order:

~~~sql
measure[dimension_value_1, dimension_value_2]
~~~

Example:

~~~sql
sales_amount[2024]
~~~

means the `SALES_AMOUNT` measure at the cell with `FISCAL_YEAR = 2024` in the current partition.

In a multi-dimensional model:

~~~sql
sales_amount[10, 2024]
~~~

addresses product 10, year 2024 if `DIMENSION BY` order is `(product_id, fiscal_year)`.

### 7.1 Referencing existing vs. non-existent cells

Given source data:

| FISCAL_YEAR | SALES_AMOUNT |
|---:|---:|
| 2023 | 100 |
| 2024 | 120 |

`sales_amount[2024]` references an existing cell. `sales_amount[2025]` addresses a coordinate absent from the input data. A rule can create a new cell when an appropriate UPSERT mode is used.

If a cell does not exist, never assume its measure value is 0. Missing value, absent cell, and present cell with NULL measure are distinct states that must be differentiated.

## 8. CV(): Dimension Value of the Current Cell

`CV()` stands for *current value*. Inside a rule, it returns the current value of the referenced dimension. You can specify the dimension explicitly:

~~~sql
CV(fiscal_year)
~~~

Example:

~~~sql
sales_amount[CV(fiscal_year) - 1]
~~~

If the rule is evaluating year 2025, `CV(fiscal_year)` is 2025; the expression references the 2024 cell.

### 8.1 Using CV to write general rules

Instead of writing each year separately:

~~~sql
sales_amount[2025] = sales_amount[2024] * 1.10,
sales_amount[2026] = sales_amount[2025] * 1.10,
sales_amount[2027] = sales_amount[2026] * 1.10
~~~

you can write a rule spanning a range of years:

~~~sql
sales_amount[FOR fiscal_year FROM 2025 TO 2027 INCREMENT 1] =
    sales_amount[CV(fiscal_year) - 1] * 1.10
~~~

The `FOR` construct in the cell reference generates target dimension values across the range; `CV(fiscal_year)` returns the year being assigned at each rule application. Verify `FOR` syntax and rule combinations against the SQL Language Reference for your target release before using in production.

### 8.2 CV in multi-dimensional models

Suppose:

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

you can reference:

~~~sql
sales_amount[CV(product_id), CV(fiscal_year) - 1]
~~~

This keeps the current cell's `PRODUCT_ID` and steps back one year in `FISCAL_YEAR`. Reversing the dimension order will point to the wrong coordinate or raise an error.

## 9. Basic Rule: Computing One Cell from Another

Example 2025 forecast:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

The rule `sales_amount[2025] = sales_amount[2024] * 1.10` reads as:

1. Target measure is `SALES_AMOUNT`.
2. Target cell has `FISCAL_YEAR = 2025`.
3. Assigned value is the 2024 cell's measure multiplied by 1.10.
4. The rule runs independently within each product partition.

### 9.1 UPDATE and UPSERT

Two crucial modes:

| Mode | When target cell already exists | When target cell does not exist |
|---|---|---|
| `UPDATE` | Updates measure value | Does not create a new cell |
| `UPSERT` | Updates existing cell | Can create a cell for a single-cell target reference per UPSERT rules |

In MODEL, `UPDATE` is the default behavior when no mode is specified. When adding year 2025 that is not yet in the source, use `UPSERT`:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

The result includes a row for year 2025 for each product, even though `LAB_SALES_PLAN` initially lacked those rows. This is **the output of the SELECT statement**, not a direct INSERT into the source table.

### 9.2 UPSERT does not write data back to the source table

MODEL computes over the query's dataset and returns cells in the result set. An `UPSERT` rule creates cells in the result model; it does not `INSERT` into `LAB_SALES_PLAN`.

To persist forecast results into a physical table, use a separate DML statement such as `INSERT INTO ... SELECT ...` or `MERGE`, with appropriate transaction and unique key design.

## 10. Multiple Rules and Evaluation Order

We want to forecast 2025 and 2026 sequentially:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT SEQUENTIAL ORDER (
        sales_amount[2025] = sales_amount[2024] * 1.10,
        sales_amount[2026] = sales_amount[2025] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

The second rule reads the 2025 value produced by the preceding rule. `SEQUENTIAL ORDER` instructs Oracle to apply rules in the exact order they are listed. This fits when one rule depends on the output of a prior rule.

### 10.1 SEQUENTIAL ORDER

`SEQUENTIAL ORDER` evaluates rules in written order. Example:

~~~sql
RULES UPSERT SEQUENTIAL ORDER (
    sales_amount[2025] = sales_amount[2024] * 1.10,
    sales_amount[2026] = sales_amount[2025] * 1.10
)
~~~

The 2025 rule runs first, and then the 2026 rule can use the newly computed 2025 value.

### 10.2 AUTOMATIC ORDER

`AUTOMATIC ORDER` lets Oracle order rule execution according to inter-rule dependencies. It is useful when expressing data dependencies without manually enforcing write order, but should be avoided if rules have order-sensitive side effects that the author has not verified clearly.

Example of independent rules:

~~~sql
RULES UPSERT AUTOMATIC ORDER (
    sales_amount[2025] = sales_amount[2024] * 1.10,
    sales_amount[2026] = sales_amount[2024] * 1.20
)
~~~

Both read year 2024 and do not depend on each other. When rules have dependencies, pick the ordering intentionally and test with small examples before deploying to critical reports.

### 10.3 UPDATE/UPSERT and rule order are two separate decisions

- `UPDATE`/`UPSERT` governs behavior depending on whether the target cell already exists.
- `SEQUENTIAL ORDER`/`AUTOMATIC ORDER` governs how rules are ordered during evaluation.

Do not confuse `UPSERT` with `SEQUENTIAL ORDER`: one controls cell creation, the other controls evaluation order.

## 11. FOR Loops in Cell References

When applying the same formula across multiple dimension values, `FOR` can generate a set of target cells.

Example forecasting from 2025 through 2027:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT SEQUENTIAL ORDER (
        sales_amount[
            FOR fiscal_year FROM 2025 TO 2027 INCREMENT 1
        ] =
            sales_amount[CV(fiscal_year) - 1] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

Each year in the range is a target cell. `CV(fiscal_year)` represents the year currently being processed; the rule reads the preceding year and multiplies by the growth factor.

When using `FOR`, keep in mind:

- The dimension type must support range generation.
- Start/end bounds and increment step must fit the data domain.
- The rule must be able to read the prior source cell; if the preceding year does not exist or its measure is NULL, the outcome depends on missing-value handling.
- `UPSERT` is used when target cells may not exist yet.

For date or string dimensions, do not blindly apply `FROM ... TO ... INCREMENT 1`; use dimension generation forms valid for the data type and supported by Oracle syntax.

## 12. ITERATE: Repeating Rules

`ITERATE(n)` lets you apply the rule set multiple times. This is useful for problems requiring iterative updates, such as simulating compound growth or convergence calculations.

Example illustrating a cell growing by 10% across three iterations:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPDATE SEQUENTIAL ORDER
        ITERATE (3) (
            sales_amount[2024] = sales_amount[2024] * 1.10
        )
ORDER BY product_id, fiscal_year;
~~~

In the example model, the 2024 cell is updated across each iteration. After three rounds, the final value equals the initial value multiplied by the growth factor three times. This example only illustrates iteration mechanics; MODEL inside SELECT produces query results and does not modify the source table.

### 12.1 ITERATE and UNTIL

You can stop early with an `UNTIL` condition:

~~~sql
RULES UPDATE SEQUENTIAL ORDER
    ITERATE (100) UNTIL (ABS(sales_amount[2024] - 200) < 0.01)
    (
        sales_amount[2024] =
            (sales_amount[2024] + 200) / 2
    )
~~~

The example applies an update converging toward 200. The `UNTIL` condition is evaluated between iterations; the maximum count is 100, yet execution stops early once the difference falls below the threshold.

When designing stop conditions:

- Always specify a finite iteration limit to avoid excessive computation.
- Convergence conditions must reflect domain semantics.
- Consider numeric precision and error tolerance.
- Avoid rules that leave values unchanged yet still burn through all iterations.

### 12.2 ITERATION_NUMBER

Inside an iterating rule, the `ITERATION_NUMBER` pseudocolumn gives the current iteration number. It can be used in formulas or conditions:

~~~sql
sales_amount[2024] =
    sales_amount[2024] + ITERATION_NUMBER
~~~

This only illustrates accessing the iteration counter; real formulas must specify initial values and the meaning of each iteration. Do not confuse `ITERATION_NUMBER` with `LEVEL`: one is MODEL's loop counter, the other is depth in a hierarchical query.

## 13. Multiple Dimensions: Product and Region Scenarios

Models can use multiple dimensions. For example, a planning table by region, product, and year:

| REGION_ID | PRODUCT_ID | FISCAL_YEAR | SALES_AMOUNT |
|---|---:|---:|---:|
| NORTH | 10 | 2024 | 120 |
| SOUTH | 10 | 2024 | 90 |
| NORTH | 20 | 2024 | 88 |
| SOUTH | 20 | 2024 | 70 |

One way to define it:

~~~sql
SELECT region_id,
       product_id,
       fiscal_year,
       sales_amount
FROM regional_sales
MODEL
    DIMENSION BY (region_id, product_id, fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount['NORTH', 10, 2025] =
            sales_amount['NORTH', 10, 2024] * 1.10
    )
ORDER BY region_id, product_id, fiscal_year;
~~~

The target cell is identified by three coordinates in the exact dimension order: `REGION_ID`, `PRODUCT_ID`, `FISCAL_YEAR`.

If each region should be an independent partition:

~~~sql
PARTITION BY (region_id)
DIMENSION BY (product_id, fiscal_year)
MEASURES (sales_amount)
~~~

Then within each partition, cell references need only `(product_id, fiscal_year)` coordinates. Both approaches can be valid; pick whichever aligns with how calculations are organized.

## 14. Using CV on the Current Cell Across Multiple Dimensions

With:

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

you can write:

~~~sql
sales_amount[CV(product_id), CV(fiscal_year) - 1]
~~~

This retrieves the same product's value in the prior year. Example computing growth percentage:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       growth_rate
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (
        sales_amount,
        CAST(NULL AS NUMBER(10,4)) AS growth_rate
    )
    RULES UPDATE (
        growth_rate[2024] =
            (sales_amount[2024] - sales_amount[2023])
            / NULLIF(sales_amount[2023], 0)
    )
ORDER BY product_id, fiscal_year;
~~~

The `GROWTH_RATE` measure is declared to calculate 2024 growth relative to 2023 revenue. `NULLIF` protects against division by zero.

To compute across a range of years:

~~~sql
growth_rate[FOR fiscal_year FROM 2024 TO 2026 INCREMENT 1] =
    (sales_amount[CV(fiscal_year)] -
     sales_amount[CV(fiscal_year) - 1])
    / NULLIF(sales_amount[CV(fiscal_year) - 1], 0)
~~~

This assumes prior-year cells can be referenced. If a preceding year is absent, decide how missing cells/NULLs should behave rather than assuming zero.

## 15. UPDATE, UPSERT, and Non-Existent Cells

This distinction determines whether new rows appear in the output.

### 15.1 UPDATE modifies only existing cells

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPDATE (
        sales_amount[2024] = sales_amount[2024] * 1.05
    )
ORDER BY product_id, fiscal_year;
~~~

The 2024 cell already exists, so it is recalculated in the model output. If a rule targets year 2025 which does not exist, `UPDATE` will not create a new row for that year.

### 15.2 UPSERT creates matching target cells

~~~sql
RULES UPSERT (
    sales_amount[2025] = sales_amount[2024] * 1.10
)
~~~

If cell 2025 does not exist yet and the rule references a single target cell, Oracle creates the new cell per UPSERT semantics. This mechanism is commonly used for forecasts, budgets, or future periods lacking source rows.

### 15.3 UPSERT ALL for multi-cell references

`UPSERT ALL` is the variant for rules with multi-cell target references in MODEL syntax. Do not use it as a generic replacement keyword for `UPSERT`; clarify whether the rule targets one specific cell or a set of cells.

For basic problems, prefer explicit single-coordinate cell references or well-defined `FOR` ranges; use wildcard/multi-cell references only after thoroughly understanding how Oracle resolves target cell sets.

## 16. NULL Values, Missing Cells, and NAV

In MODEL, distinguish three states:

1. **Cell does not exist:** the dimension combination is absent from input data and has not been created by any rule.
2. **Cell exists, measure is NULL:** a row exists for that coordinate, with a NULL measure.
3. **Cell exists, measure has a value:** a row exists and the measure holds a concrete value.

Example:

| FISCAL_YEAR | SALES_AMOUNT | Status |
|---:|---:|---|
| 2023 | 100 | Cell exists, measure has value |
| 2024 | NULL | Cell exists, measure is NULL |
| 2025 | — | Cell does not exist yet |

Do not automatically equate the last two rows with 0. A year with no data entered yet differs from a year recorded with revenue still undetermined.

### 16.1 KEEP NAV and IGNORE NAV

`NAV` stands for *null/absent value* in the MODEL context. Two options:

- `KEEP NAV` retains NULL and absent values as NULL during calculation.
- `IGNORE NAV` uses Oracle's default NAV value for the measure's data type; never assume every type defaults to 0.

When unspecified, MODEL defaults to `IGNORE NAV`. Whenever NULL results carry business meaning, consider specifying `KEEP NAV` explicitly.

NAV rules depend on the measure data type; never assume every data type substitutes 0. For numeric measures, NAV behavior can affect addition/multiplication and rule outcomes. When NULL results carry business meaning, specify the handling explicitly and test with sample data.

Example choosing to keep NAV:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    KEEP NAV
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

`KEEP NAV` is useful when preserving missing-data semantics so absent/NULL cells are not interpreted as substituted values. In real formulas, you may need `CASE`, `NVL`, `COALESCE`, or `NULLIF` inside rule expressions to enforce business policy.

### 16.2 Checking NULL before computing

~~~sql
sales_amount[2025] =
    CASE
        WHEN sales_amount[2024] IS NULL THEN NULL
        ELSE sales_amount[2024] * 1.10
    END
~~~

This example clarifies that if 2024 revenue has no value, the 2025 forecast should not be computed as a number either. If business logic intentionally defaults missing revenue to 0:

~~~sql
sales_amount[2025] = NVL(sales_amount[2024], 0) * 1.10
~~~

then make that decision explicit. Replacing NULL with 0 can skew forecasts if NULL actually means data has not been loaded yet.

## 17. Multiple Measures and Interdependent Rules

A model can compute forecast revenue, budget, and variance:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       budget_amount,
       variance_amount
FROM product_finance
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (
        sales_amount,
        budget_amount,
        CAST(NULL AS NUMBER(14,2)) AS variance_amount
    )
    RULES UPDATE (
        variance_amount[2024] =
            sales_amount[2024] - budget_amount[2024]
    )
ORDER BY product_id, fiscal_year;
~~~

`VARIANCE_AMOUNT` is a measure derived from two input measures. You can also define a ratio:

~~~sql
variance_percent[2024] =
    variance_amount[2024] / NULLIF(budget_amount[2024], 0)
~~~

When multiple rules depend on one another, use `SEQUENTIAL ORDER` or `AUTOMATIC ORDER` matching the calculation intent and verify results. Never assume one rule automatically runs earlier just because it appears in another expression; declare order or dependency structure explicitly.

## 18. MODEL vs. GROUP BY, Analytic Functions, and PIVOT

These techniques solve different classes of problems:

| Technique | Main purpose | Characteristics |
|---|---|---|
| `GROUP BY` | Aggregates multiple rows into one row per group | Fits SUM/COUNT/AVG by group |
| Analytic function | Computes over row windows while keeping detail rows | Fits running totals, ranks, moving averages |
| `PIVOT` | Turns categorical values into columns | Fits cross-tab reports |
| `MODEL` | Addresses and computes over cells by dimension | Fits forecasts, allocations, multi-dimensional models, cell-dependent rules |

### 18.1 When GROUP BY is enough

If you only need total revenue by product:

~~~sql
SELECT product_id,
       SUM(sales_amount) AS total_sales
FROM sales_history
GROUP BY product_id;
~~~

MODEL is unnecessary because there is no cell addressing or coordinate-based value creation.

### 18.2 When analytic functions are enough

If you need a running total by year:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       SUM(sales_amount) OVER (
           PARTITION BY product_id
           ORDER BY fiscal_year
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sales
FROM lab_sales_plan;
~~~

Analytic functions are more natural when the calculation is a window over existing rows. MODEL shines when you must reference specific coordinates, generate new cells, or apply multi-step rules.

### 18.3 When MODEL is the right choice

MODEL can be a good fit when:

- Data has clear dimensions such as product, region, month, and year.
- You need to compute values for cells absent from the source.
- Formulas depend on current, prior, or cross-dimension cells.
- Multiple interconnected rules require explicit ordering or iteration.
- You want to keep model logic inside a single SQL statement.

MODEL is not automatically faster than CTEs or analytic functions. Its syntax is complex and computation cost can be high; use it when the problem structure genuinely calls for a cell model.

## 19. ORDER BY After MODEL vs. Ordering Inside the Model

`ORDER BY` at the end of the query sorts **the returned result rows**:

~~~sql
ORDER BY product_id, fiscal_year
~~~

It does not determine rule evaluation order. To control rule order, use `SEQUENTIAL ORDER` or `AUTOMATIC ORDER` in RULES.

Distinction:

- `SEQUENTIAL ORDER`: evaluation order of rules.
- `ORDER BY`: display order of rows after MODEL produces the result.

Do not rely on physical source row order to infer cell order or rule order.

## 20. MODEL and Source Data Filtering

MODEL operates on the row set produced by the source query. If you need to filter historical periods before building the model:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
WHERE fiscal_year >= 2023
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

Source conditions determine which rows enter the model. If year 2024 is filtered out of the source, a rule referencing `sales_amount[2024]` will lack input data to compute. Make sure required input cells still enter the model.

If you only want to display certain rows after calculation, wrap MODEL in an inline view or CTE and filter outside:

~~~sql
WITH modeled AS (
    SELECT product_id,
           fiscal_year,
           sales_amount
    FROM lab_sales_plan
    MODEL
        PARTITION BY (product_id)
        DIMENSION BY (fiscal_year)
        MEASURES (sales_amount)
        RULES UPSERT (
            sales_amount[2025] = sales_amount[2024] * 1.10
        )
)
SELECT product_id, fiscal_year, sales_amount
FROM modeled
WHERE fiscal_year >= 2024
ORDER BY product_id, fiscal_year;
~~~

Separating source from output clearly distinguishes **input data filtering** from **post-calculation cell filtering**.

## 21. Persisting MODEL Results into a Physical Table

MODEL in SELECT does not automatically write back to the source table. To store forecasts, feed the query output into an `INSERT`:

~~~sql
INSERT INTO sales_forecast (
    product_id,
    fiscal_year,
    forecast_amount
)
SELECT product_id,
       fiscal_year,
       sales_amount
FROM (
    SELECT product_id,
           fiscal_year,
           sales_amount
    FROM lab_sales_plan
    MODEL
        PARTITION BY (product_id)
        DIMENSION BY (fiscal_year)
        MEASURES (sales_amount)
        RULES UPSERT (
            sales_amount[2025] = sales_amount[2024] * 1.10
        )
) modeled
WHERE fiscal_year = 2025;
~~~

This illustrates the concept; the target table must have matching columns and constraints, and result filtering must sit in the proper query block. Before running actual DML, verify the SELECT alone, ensure each product has only one forecast row per target year, and handle duplicate keys via an appropriate business `MERGE`/upsert process.

## 22. Common Errors and Troubleshooting Steps

| Symptom/error | Possible cause | Resolution |
|---|---|---|
| `ORA-32638: Non unique addressing in MODEL dimensions` | Multiple source rows share the same dimension tuple in a partition | Check grain; aggregate or fix keys before MODEL |
| Rule does not create new year rows | Using UPDATE instead of UPSERT, or target reference is not suitable for single-cell upsert | Check target cell reference and choose UPSERT |
| Next year's value does not reflect the just-computed year | Rule order/dependency not declared properly | Use SEQUENTIAL ORDER or AUTOMATIC ORDER matching dependencies |
| Forecast result is NULL | Source cell missing or source measure is NULL/NAV | Check cell existence and NAV policy |
| All products get the same value | Missing partition/dimension separating products | Put product in PARTITION BY or DIMENSION BY |
| Wrong cell referenced | Wrong dimension order or coordinate value | Align DIMENSION BY order with cell reference |
| Rule miscomputes current year | Using a constant instead of CV or wrong offset | Use CV(dimension) to reference the current coordinate |
| Result has duplicate rows | Non-unique dimensions or source JOIN multiplied rows | Inspect pre-MODEL data and grain |
| Iteration does not terminate early | UNTIL never satisfied or missing convergence condition | Set a maximum iteration cap and verify stop condition |
| MODEL output mistaken for persisted data | UPSERT in MODEL creates cells only in SELECT output | Use separate INSERT/MERGE to persist |
| SQL fails on another DBMS | MODEL is an Oracle extension | Use equivalent CTE/analytic patterns for that DBMS |

When an error occurs, inspect in this order:

1. Verify source data and grain.
2. Check whether partition + dimension combinations are unique.
3. Match cell references against dimension order.
4. Check whether source cells exist and whether measures are NULL.
5. Check UPDATE/UPSERT mode.
6. Check rule order and iteration conditions.

## 23. Self-Check Practice Exercises

Use `LAB_SALES_PLAN` created in section 2. SELECT MODEL queries do not modify the source table.

### Exercise 1 — Create a one-year forecast

For each product, create a 2025 cell equal to 2024 revenue plus 10%.

- Declare `PARTITION BY (product_id)`.
- Declare `DIMENSION BY (fiscal_year)`.
- Declare `MEASURES (sales_amount)`.
- Use UPSERT to create the missing cell.

Explain why omitting the partition can prevent multiple products' data from being distinguished properly.

### Exercise 2 — Create a multi-year forecast

Create cells for 2025, 2026, and 2027, each growing 10% over the previous year. Write one version using explicit rules and one version using `CV()` and `FOR`.

### Exercise 3 — UPDATE vs. UPSERT

Run the same rule targeting year 2025 using UPDATE and UPSERT. Compare behavior when cell 2025 does not yet exist. Explain why UPDATE does not create new rows.

### Exercise 4 — Multiple dimensions

Create a source with `REGION_ID`, `PRODUCT_ID`, `FISCAL_YEAR`, and `SALES_AMOUNT`. Write a model using:

~~~sql
DIMENSION BY (region_id, product_id, fiscal_year)
~~~

Create a forecast for a specific coordinate. Then move REGION into PARTITION BY and compare cell referencing.

### Exercise 5 — Compute variance

Create a source with `SALES_AMOUNT` and `BUDGET_AMOUNT`. Declare a `VARIANCE_AMOUNT` measure and compute:

~~~sql
sales_amount - budget_amount
~~~

Explain why variance is a measure rather than a dimension.

### Exercise 6 — Test duplicate dimensions

Create two rows with the same `PRODUCT_ID` and `FISCAL_YEAR` but different amounts. Run MODEL and observe the error. Then aggregate the data down to one row per dimension tuple and re-run.

### Exercise 7 — NULLs vs. non-existent cells

Create a year that has a row with `SALES_AMOUNT` equal to NULL; leave the following year with no row at all. Compare both cases when a rule references the measure. State an appropriate policy for business logic.

### Exercise 8 — ITERATE

Create a rule updating the same cell across three iterations, multiplying by 1.10 each round. Calculate the final value by hand and compare with SQL.

### Exercise 9 — UNTIL

Write a rule converging toward a target by averaging the current value and the target. Set a maximum iteration count and a stop condition based on tolerance. Explain what happens if the condition is never met.

### Exercise 10 — Compare with analytic functions

Write an analytic query computing a running total by product/year. Compare with a MODEL forecast. Describe scenarios where analytic functions are simpler and scenarios where MODEL has the advantage.

## 24. Key Takeaways

| Component | Role |
|---|---|
| `PARTITION BY` | Separates independent models |
| `DIMENSION BY` | Declares coordinates locating cells |
| `MEASURES` | Declares values inside cells |
| `RULES` | Declares formulas assigning measures |
| `measure[dimension_value]` | References a cell |
| `CV(dimension)` | Retrieves the current cell's dimension value |
| `UPDATE` | Updates only existing cells |
| `UPSERT` | Updates or creates matching target cells |
| `SEQUENTIAL ORDER` | Applies rules in written order |
| `AUTOMATIC ORDER` | Orders rules by dependency relationships |
| `FOR` | Generates a range of target cell coordinates |
| `ITERATE` | Repeats rules for a number of iterations |
| `UNTIL` | Stops iterating when a condition is met |
| `KEEP NAV` / `IGNORE NAV` | Chooses how NULL/absent values are handled in the model |

The MODEL clause suits problems where data is viewed as a multi-dimensional grid and one cell's value depends on other cells. Determine grain, partitions, dimensions, and measures first before writing cell references and rules. Use `CV()` to express current coordinates, choose UPDATE or UPSERT based on whether target cells already exist, and declare rule order or iteration when dependencies exist. Finally, distinguish missing cells from NULL measures and verify SELECT output before persisting data into a physical table.
