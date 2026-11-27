# INSERT ALL, INSERT FIRST, and Conditional Inserts in Oracle Database

## 1. When One Source Row Needs to Go Into Multiple Tables

In data loading workflows, a single source row sometimes must generate multiple target rows or be routed to one of several tables depending on conditions. For example:

- A person record is written to the parent table PEOPLE; if the person is a patient, an additional row is written to PATIENTS; if the person is staff, an additional row is written to STAFF.
- Orders are classified into small, medium, large, or priority tables.
- Weekly sales data stored across multiple day columns is converted into multiple daily sales rows.
- A transaction must be recorded in both a history table and a reporting table.
- Staging data needs to be split by business category or status.

You could write multiple INSERT ... SELECT statements, but Oracle supports **multitable insert** to distribute rows from a single source query into multiple tables:

- **INSERT ALL:** executes all matching INTO branches for each source row.
- **INSERT FIRST:** evaluates conditions in order and executes only the first matching branch for each source row.
- **WHEN ... THEN:** specifies the insert condition.
- **ELSE:** specifies the default branch when no WHEN condition is true.

These statements are useful for ETL, staging, data classification, and table structure transformations. This lesson uses Oracle Database 19c syntax.

> The *_LAB tables are illustrative examples. Run DDL/DML only in an authorized lab schema; verify the target tables and transaction state before executing.

## 2. How Does Multitable INSERT Work?

Unlike a regular INSERT INTO ... SELECT statement that writes to only one target table, a multitable insert takes each row from the source query and applies the INTO branches.

~~~text
                    Source SELECT
                         |
             +-----------+-----------+
             |           |           |
           row 1       row 2       row 3
             |           |           |
        evaluate conditions / INTO branches
             |           |           |
       +-----+-----+     |       +---+---+
       |           |     |       |       |
     table A    table B table B table A table C
~~~

A source row can be inserted into one table, multiple tables, or no table if no branch matches and there is no ELSE. A source row can also be inserted multiple times into the same table via different INTO branches.

If the source query returns 100 rows and the statement has three unconditional INTO branches, the total number of inserted rows is 300.

~~~sql
-- Unconditional insert into multiple tables.
INSERT ALL
    INTO target_a (id, value_a) VALUES (source_id, source_value)
    INTO target_b (id, value_b) VALUES (source_id, source_value)
SELECT id AS source_id,
       value AS source_value
FROM source_table;

-- Conditional insert.
INSERT ALL
    WHEN amount < 1000 THEN
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
    WHEN amount >= 1000 THEN
        INTO large_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM orders;
~~~

If the source query returns zero rows, no rows are inserted.

## 3. Unconditional INSERT ALL

### 3.1. Syntax

~~~sql
INSERT ALL
    INTO table_a (column_a1, column_a2)
    VALUES (source_expr_1, source_expr_2)
    INTO table_b (column_b1, column_b2)
    VALUES (source_expr_1, source_expr_2)
SELECT source_expr_1, source_expr_2, ...
FROM source_table
WHERE ...;
~~~

ALL is followed by multiple INTO branches. Oracle executes each branch once for every row returned by the source query.

### 3.2. Writing One Record Into Two Tables

Suppose the system needs to write orders to both an operational table and an audit table:

~~~sql
INSERT ALL
    INTO orders_live (order_id, customer_id, order_total)
    VALUES (order_id, customer_id, order_total)
    INTO orders_audit (order_id, customer_id, order_total, copied_at)
    VALUES (order_id, customer_id, order_total, SYSDATE)
SELECT order_id,
       customer_id,
       order_total
FROM order_source
WHERE import_batch_id = :batch_id;
~~~

For each source row matching import_batch_id, Oracle inserts one row into ORDERS_LIVE and one row into ORDERS_AUDIT. Both rows can share the same ORDER_ID. The audit table can receive additional copy timestamp or source metadata.

### 3.3. One Source, Multiple Tables with Different Structures

Target tables do not need to have the same number of columns or the same structure. Each INTO branch declares its own column list and values:

~~~sql
INSERT ALL
    INTO people_lab (person_id, full_name, person_type)
    VALUES (person_id, full_name, person_type)
    INTO person_contact_lab (person_id, email_address)
    VALUES (person_id, email_address)
    INTO person_status_lab (person_id, status_code, created_at)
    VALUES (person_id, status_code, SYSDATE)
SELECT person_id,
       full_name,
       person_type,
       email_address,
       status_code
FROM person_import_stage;
~~~

The first branch uses three columns, the second uses two columns, and the third uses three columns. Oracle maps values according to the column order declared in each branch.

**Always specify the column list.** If you omit the column list, expressions must provide values for every column in the table's definition order. That is fragile when the schema changes.

## 4. Conditional INSERT ALL

### 4.1. Syntax and Evaluation Order

~~~sql
INSERT ALL
    WHEN condition_1 THEN
        INTO table_a (column_a1, column_a2)
        VALUES (source_expr_1, source_expr_2)
    WHEN condition_2 THEN
        INTO table_b (column_b1, column_b2)
        VALUES (source_expr_1, source_expr_2)
    ELSE
        INTO fallback_table (column_x, column_y)
        VALUES (source_expr_1, source_expr_2)
SELECT source_expr_1, source_expr_2, ...
FROM source_table;
~~~

Conditional INSERT ALL evaluates **all** WHEN conditions for each source row. Every true condition triggers its corresponding INTO list.

If no WHEN condition is true:

- With ELSE: executes the INTO branches under ELSE.
- Without ELSE: skips that source row and inserts into no table.

Oracle Database 19c allows up to 127 WHEN clauses in a single multitable insert statement.

### 4.2. Classifying Orders Into Tables

Suppose the rule is:

| Order value | Target table |
| --- | --- |
| Under 1,000 | SMALL_ORDERS |
| From 1,000 to under 10,000 | MEDIUM_ORDERS |
| 10,000 and above | LARGE_ORDERS |

~~~sql
INSERT ALL
    WHEN order_total < 1000 THEN
        INTO small_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 AND order_total < 10000 THEN
        INTO medium_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id,
       customer_id,
       order_total
FROM orders
WHERE order_date >= DATE '2026-01-01';
~~~

The ranges do not overlap and cover all non-NULL numeric values. Each order is routed into exactly one table.

### 4.3. One Source Row Can Go Into Multiple Tables

The key point of INSERT ALL is that conditions are not mutually exclusive. For example, suppose you want to:

- Put all orders of 1,000 or more into ORDERS_OVER_1000.
- Also put orders of 10,000 or more into ORDERS_VIP.
- Put orders under 1,000 into ORDERS_SMALL.

~~~sql
INSERT ALL
    WHEN order_total >= 1000 THEN
        INTO orders_over_1000 (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO orders_vip (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO orders_small (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

For an order of 15,000, both WHEN conditions are true, so that order is inserted into **both** ORDERS_OVER_1000 and ORDERS_VIP. ELSE does not run because at least one condition matched.

This is how you represent one row belonging to multiple business groups. If you want each order in only one group, you must write mutually exclusive conditions or use INSERT FIRST.

### 4.4. ELSE as the Default Branch

~~~sql
INSERT ALL
    WHEN order_total <= 100000 THEN
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total > 100000 AND order_total <= 200000 THEN
        INTO medium_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO large_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

ELSE is used if no WHEN condition is true. Thus orders above 200,000 go into LARGE_ORDERS. If ORDER_TOTAL is NULL, all comparisons evaluate to UNKNOWN rather than TRUE; that row also goes into ELSE. If NULL must be handled separately, add a condition:

~~~sql
WHEN order_total IS NULL THEN
    INTO invalid_orders (order_id, order_total)
    VALUES (order_id, order_total)
~~~

INSERT ALL evaluates every condition, so branch order is not a precedence rule.

## 5. INSERT FIRST: Execute Only the First True Branch

### 5.1. Difference from INSERT ALL

INSERT FIRST is a conditional multitable insert. Oracle evaluates WHEN conditions in the order they appear. For each source row:

1. Check the first WHEN.
2. If true, execute that branch's INTO list and skip all subsequent WHEN clauses.
3. If false, check the next branch.
4. If no branch is true, execute ELSE if present; otherwise, skip the source row.

| Characteristic | INSERT ALL | INSERT FIRST |
| --- | --- | --- |
| WHEN evaluation | All conditions | In order, stopping at the first true condition |
| Multiple true conditions | Can run multiple branches | Runs only the first true branch |
| ELSE | Runs when no WHEN is true | Runs when no WHEN is true |
| Used for | Distributing one row to multiple targets | Priority-based classification, choosing one branch |

### 5.2. Priority-Based Classification

Suppose orders are classified as:

- 50,000 and above: VIP.
- 10,000 to under 50,000: large.
- 1,000 to under 10,000: medium.
- Remainder: small.

~~~sql
INSERT FIRST
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO medium_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

An order of 75,000 satisfies all three top conditions, but is inserted only into VIP_ORDERS because it is the first true branch. An order of 20,000 goes into LARGE_ORDERS; an order of 2,000 goes into MEDIUM_ORDERS.

### 5.3. WHEN Order Changes the Result

~~~sql
-- Wrong order if you want to separate VIP orders:
INSERT FIRST
    WHEN order_total >= 1000 THEN
        INTO regular_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

The condition ORDER_TOTAL >= 1000 already covers VIP orders. Because INSERT FIRST stops at the first true branch, the VIP branch never receives orders of 50,000 or more.

Place the more specific condition first:

~~~sql
INSERT FIRST
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO regular_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

With INSERT FIRST, read the conditions as a priority chain. A general branch placed before a specialized branch can prevent the specialized branch from ever executing.

## 6. Multiple INTOs Within a Single WHEN Branch

One condition can trigger multiple target tables:

~~~sql
INSERT ALL
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (person_id, admission_date)
        INTO patient_audit_lab (person_id, event_type, logged_at)
        VALUES (person_id, 'ADMISSION', SYSDATE)
    WHEN hired_date IS NOT NULL THEN
        INTO staff_lab (staff_id, hired_date)
        VALUES (person_id, hired_date)
        INTO staff_audit_lab (person_id, event_type, logged_at)
        VALUES (person_id, 'HIRED', SYSDATE)
SELECT person_id, admission_date, hired_date
FROM person_import_stage;
~~~

If a person has a non-NULL ADMISSION_DATE, both PATIENTS_LAB and PATIENT_AUDIT_LAB receive corresponding rows. If HIRED_DATE is also non-NULL, INSERT ALL runs the staff branch as well. One person can be both a patient and staff.

With INSERT FIRST, if both conditions are true, only the first true branch is executed. Choose ALL or FIRST according to the business relationship.

## 7. Transforming Data Structures with INSERT ALL

A common application of INSERT ALL is converting column-based data into multiple rows, also known as manual unpivoting.

### 7.1. From Daily Sales in Columns to Rows

The source table has the structure:

| PRODUCT_ID | WEEK_START | SALES_MON | SALES_TUE | SALES_WED |
| ---: | --- | ---: | ---: | ---: |
| 101 | 2026-11-02 | 100 | 120 | 90 |
| 102 | 2026-11-02 | 80 | 75 | 110 |

The target table DAILY_SALES has columns PRODUCT_ID, SALES_DATE, AMOUNT. Using INSERT ALL:

~~~sql
INSERT ALL
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start, sales_mon)
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start + 1, sales_tue)
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start + 2, sales_wed)
SELECT product_id,
       week_start,
       sales_mon,
       sales_tue,
       sales_wed
FROM weekly_sales;
~~~

Each weekly row produces three daily sales rows. The same target table can appear in multiple INTO branches; this is valid and useful for unpivoting.

### 7.2. Skipping NULL Values

If a day column with no sales can contain NULL and we do not want to create a target row:

~~~sql
INSERT ALL
    WHEN sales_mon IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start, sales_mon)
    WHEN sales_tue IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start + 1, sales_tue)
    WHEN sales_wed IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start + 2, sales_wed)
SELECT product_id,
       week_start,
       sales_mon,
       sales_tue,
       sales_wed
FROM weekly_sales;
~~~

Because the conditions are independent, a weekly row can trigger one, two, or three branches. If all three values are NULL, the source row produces no target rows.

### 7.3. Comparison with UNPIVOT

Oracle also has the UNPIVOT operator in SELECT. If you only need to turn columns into rows inside a source query, UNPIVOT can express it concisely:

~~~sql
SELECT product_id,
       week_start + CASE weekday
           WHEN 'MON' THEN 0
           WHEN 'TUE' THEN 1
           WHEN 'WED' THEN 2
       END AS sales_date,
       amount
FROM weekly_sales
UNPIVOT EXCLUDE NULLS (
    amount FOR weekday IN (
        sales_mon AS 'MON',
        sales_tue AS 'TUE',
        sales_wed AS 'WED'
    )
);
~~~

You can combine the UNPIVOT result with INSERT INTO ... SELECT to save into a target table. Choose the tool based on the goal:

- INSERT ALL: convenient when one source row needs to generate multiple target rows, multiple tables, or multiple calculation branches.
- UNPIVOT: suitable when the primary goal is turning a group of columns into rows within the source query.

## 8. Using the SELECT List to Prepare Source Expressions

WHEN conditions and VALUES expressions reference columns returned by the source query's select list. If you need a calculation involving a source table alias, put that calculation into the select list and give it an alias.

### 8.1. Aliasing Expressions

~~~sql
INSERT ALL
    WHEN adjusted_total >= 10000 THEN
        INTO high_value_orders (order_id, adjusted_total)
        VALUES (source_order_id, adjusted_total)
    ELSE
        INTO normal_orders (order_id, adjusted_total)
        VALUES (source_order_id, adjusted_total)
SELECT o.order_id AS source_order_id,
       o.order_total * 1.05 AS adjusted_total
FROM orders o;
~~~

ADJUSTED_TOTAL is computed in the source query. Both WHEN and VALUES use the column names exposed by the select list.

Do not rely on a source table alias like O inside WHEN or VALUES. Oracle specifies that expressions depending on the select list reference columns returned by the select list. The clearest approach is to project O.ORDER_TOTAL * 1.05 as ADJUSTED_TOTAL and then use that name.

### 8.2. Source Aliases and Target Table Aliases

- Aliases of expressions in the select list can be referenced in WHEN and VALUES.
- Do not declare an alias for a target table in an INTO branch of a multitable insert.
- The order of values in VALUES must match the order of columns in the target list.

~~~sql
INSERT ALL
    WHEN normalized_status = 'ACTIVE' THEN
        INTO active_users (user_id, display_name)
        VALUES (source_user_id, normalized_name)
SELECT u.user_id AS source_user_id,
       TRIM(u.full_name) AS normalized_name,
       UPPER(TRIM(u.status)) AS normalized_status
FROM users u;
~~~

## 9. WHEN Conditions, NULL, and Expressions

### 9.1. Preparing Conditions in the Source Query

~~~sql
INSERT ALL
    WHEN is_valid = 1 THEN
        INTO accepted_rows (record_id, normalized_value)
        VALUES (record_id, normalized_value)
    ELSE
        INTO rejected_rows (record_id, raw_value, reason_code)
        VALUES (record_id, raw_value, 'INVALID')
SELECT record_id,
       raw_value,
       TRIM(raw_value) AS normalized_value,
       CASE
         WHEN raw_value IS NOT NULL
          AND LENGTH(TRIM(raw_value)) <= 100
         THEN 1
         ELSE 0
       END AS is_valid
FROM import_stage;
~~~

Normalization and validation are performed in the source query. WHEN only needs to read IS_VALID.

### 9.2. NULL Is Not FALSE

In SQL, a condition can evaluate to TRUE, FALSE, or UNKNOWN. If AMOUNT is NULL, the expression AMOUNT > 1000 returns UNKNOWN. A WHEN condition only triggers when the expression is TRUE; UNKNOWN does not trigger the branch.

If you want to classify NULL separately:

~~~sql
INSERT ALL
    WHEN amount IS NULL THEN
        INTO invalid_orders (order_id, amount, reason)
        VALUES (order_id, amount, 'MISSING_AMOUNT')
    WHEN amount >= 1000 THEN
        INTO valid_orders (order_id, amount)
        VALUES (order_id, amount)
    ELSE
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM order_stage;
~~~

INSERT ALL evaluates every condition, so the order of the first two branches is not a priority rule. INSERT FIRST has priority ordering; placing the NULL condition first prevents a general branch from catching that row earlier.

### 9.3. Overlapping Conditions

~~~sql
WHEN amount >= 1000 THEN ...
WHEN amount >= 5000 THEN ...
~~~

With INSERT ALL, an amount of 6,000 satisfies both. With INSERT FIRST, only the first true branch runs. When writing conditions, verify whether branches are mutually exclusive, whether a row is intended to be inserted into multiple tables, whether ELSE is needed, and how NULL is handled.

## 10. Inserting Parent and Child Data in One Statement

An important use case is when a single source row creates data in a parent table and one or more child tables. For example, a person is always stored in PEOPLE; a person with an admission date is also stored in PATIENTS; a person with a hire date is also stored in STAFF.

### 10.1. Create Lab Tables

Run only in a lab schema:

~~~sql
CREATE TABLE people_lab (
    person_id   NUMBER PRIMARY KEY,
    given_name  VARCHAR2(50 CHAR) NOT NULL,
    family_name VARCHAR2(50 CHAR) NOT NULL,
    person_type VARCHAR2(20 CHAR)
);

CREATE TABLE patients_lab (
    patient_id NUMBER PRIMARY KEY
               REFERENCES people_lab(person_id),
    admission_date DATE
);

CREATE TABLE staff_lab (
    staff_id NUMBER PRIMARY KEY
             REFERENCES people_lab(person_id),
    hired_date DATE
);
~~~

### 10.2. Insert All Into Parent Table, Conditionally Into Child Tables

With conditional multitable insert, use WHEN 1=1 to represent an always-true branch for the parent table:

~~~sql
INSERT ALL
    WHEN 1 = 1 THEN
        INTO people_lab (person_id, given_name, family_name, person_type)
        VALUES (person_id, given_name, family_name, 'PERSON')
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (person_id, admission_date)
    WHEN hired_date IS NOT NULL THEN
        INTO staff_lab (staff_id, hired_date)
        VALUES (person_id, hired_date)
WITH names AS (
    SELECT 1 AS person_id, 'Ruth' AS given_name, 'Fox' AS family_name,
           DATE '2026-01-10' AS admission_date,
           CAST(NULL AS DATE) AS hired_date
    FROM dual
    UNION ALL
    SELECT 2, 'Isabelle', 'Squirrel',
           DATE '2026-02-15', CAST(NULL AS DATE)
    FROM dual
    UNION ALL
    SELECT 3, 'Justin', 'Frog',
           CAST(NULL AS DATE), DATE '2026-03-01'
    FROM dual
    UNION ALL
    SELECT 4, 'Lisa', 'Owl',
           CAST(NULL AS DATE), CAST(NULL AS DATE)
    FROM dual
)
SELECT person_id, given_name, family_name, admission_date, hired_date
FROM names;
~~~

Result:

- All four people are inserted into PEOPLE_LAB.
- Person 1 and 2 are inserted into PATIENTS_LAB.
- Person 3 is inserted into STAFF_LAB.
- Person 4 has a row only in the parent table.

One source row can generate one parent row and one or more child rows. The example uses IDs from the source so the foreign keys have matching values. Oracle provides an official example of using INSERT ALL to write into PEOPLE and the related PATIENTS and STAFF tables.

### 10.3. A Person Who Is Both Patient and Staff

Because INSERT ALL is used, both conditions can be true at the same time:

~~~text
admission_date IS NOT NULL
hired_date     IS NOT NULL
        |
        +--> insert PEOPLE
        +--> insert PATIENTS
        +--> insert STAFF
~~~

If the requirement is that each person be assigned to only one priority category, switch to INSERT FIRST and order WHEN clauses by priority. SQL executes the rules written; the data model must still define whether a person can be both staff and patient.

## 11. Sequences and Auto-Generated Keys

When a source row is inserted into multiple tables, sometimes the tables need to share the same ID. Oracle sequences have special semantics in multitable inserts.

### 11.1. NEXTVAL in VALUES

According to the Oracle 19c documentation on Sequence Pseudocolumns, in a multitable insert, NEXTVAL references placed in VALUES cause the sequence to increment **once for each input row from SELECT**. If NEXTVAL is referenced multiple times across branches for the same input row, those references receive the same sequence value for that row.

Example of the concept of generating the same ID for parent and child tables:

~~~sql
INSERT ALL
    WHEN 1 = 1 THEN
        INTO people_lab (person_id, given_name, family_name, person_type)
        VALUES (people_seq.NEXTVAL, given_name, family_name, 'PERSON')
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (people_seq.NEXTVAL, admission_date)
SELECT given_name, family_name, admission_date
FROM person_import_stage;
~~~

For each source row, references to PEOPLE_SEQ.NEXTVAL in the branches executed for that row return the same number. This can help share parent/child keys.

**Do not assume each INTO branch increments the sequence once.** If a source row is inserted into three tables, the sequence does not generate three different IDs just because there are three branches. The sequence increments per source row, and repeated references within the same row use the same value.

### 11.2. If Tables Need Different IDs

If each target table needs its own key, design separate ID allocation explicitly:

- Use different sequences for tables with independent ID domains.
- Prepare the required IDs in staging before the multitable insert.
- Use triggers, defaults, or identity columns per design and verify behavior on your running Oracle release.
- Split into separate DML statements if you need control over key generation order or results.

For multitable inserts, do not place NEXTVAL in the source select list expecting a fresh number per branch.

### 11.3. Sequences Do Not Roll Back

Sequences are not regular transactional data. Numbers allocated by NEXTVAL are not returned when a transaction rolls back; gaps in the sequence are normal. Do not use sequences to count committed rows or require gap-free consecutive numbers.

## 12. Default Values, Data Types, and Column Mapping

### 12.1. Each INTO Has a Matching Column List and VALUES

~~~sql
INSERT ALL
    INTO table_a (id, amount, created_at)
    VALUES (source_id, source_amount, SYSDATE)
    INTO table_b (id, description)
    VALUES (source_id, source_description)
SELECT id AS source_id,
       amount AS source_amount,
       description AS source_description
FROM source_table;
~~~

The number of values in VALUES must match the number of columns in the column list. Data types must be compatible. If using expressions or conversions, write them explicitly to avoid NLS-dependent implicit conversion.

### 12.2. Omitting Columns to Use Defaults

If a column does not appear in the column list, Oracle applies the column's default if one exists; if there is no default, the value is typically NULL and may violate NOT NULL.

~~~sql
CREATE TABLE event_archive_lab (
    event_id   NUMBER PRIMARY KEY,
    event_text VARCHAR2(100 CHAR),
    created_at DATE DEFAULT SYSDATE
);

INSERT ALL
    INTO event_archive_lab (event_id, event_text)
    VALUES (event_id, event_text)
SELECT event_id, event_text
FROM event_stage;
~~~

CREATED_AT is omitted from the column list, so it uses the SYSDATE default.

Oracle allows the DEFAULT keyword in INSERT VALUES where syntax permits. For identity columns, verify the value-generation rules and the table's GENERATED ALWAYS/BY DEFAULT mode.

### 12.3. Avoid Depending on Table Column Order

Do not omit the column list when inserting into tables whose structure may evolve. If a target table adds a column, a statement without an explicit column list can fail or map columns unexpectedly. Specifying target columns makes statements easier to maintain.

## 13. INSERT ALL, INSERT FIRST, and CASE

These three constructs are related but serve different roles.

### 13.1. CASE Produces a Value

~~~sql
SELECT order_id,
       CASE
         WHEN order_total >= 50000 THEN 'VIP'
         WHEN order_total >= 10000 THEN 'LARGE'
         WHEN order_total >= 1000 THEN 'MEDIUM'
         ELSE 'SMALL'
       END AS order_class
FROM orders;
~~~

CASE selects one result expression per row. CASE itself does not insert into multiple tables.

### 13.2. INSERT FIRST Chooses an Insert Branch

INSERT FIRST executes the INTO list of the first branch whose condition is TRUE. This is appropriate when classifying a row into one prioritized target group.

### 13.3. INSERT ALL Can Execute Multiple Branches

INSERT ALL evaluates each condition independently. One row can go into multiple groups. It is suitable when a record must be written to multiple tables or matches multiple criteria simultaneously.

| Goal | Typical approach |
| --- | --- |
| Compute a classification label/value per row | CASE |
| Insert each row into one prioritized group | INSERT FIRST |
| Insert each row into all groups it satisfies | INSERT ALL |
| Write one row unconditionally to all target tables | INSERT ALL without WHEN |

## 14. Comparison with Multiple INSERT ... SELECT Statements

You can replace a multitable insert with multiple separate statements:

~~~sql
INSERT INTO small_orders (order_id, order_total)
SELECT order_id, order_total
FROM orders
WHERE order_total < 1000;

INSERT INTO large_orders (order_id, order_total)
SELECT order_id, order_total
FROM orders
WHERE order_total >= 1000;
~~~

| Criterion | Multiple INSERT ... SELECT | Multitable INSERT |
| --- | --- | --- |
| Number of DML statements | Multiple statements | One statement |
| Source logic | May read/transform source multiple times | One source query feeds all branches |
| Branching | Each statement has its own WHERE | WHEN/ELSE within one statement |
| Splitting one row into multiple tables | Possible with multiple statements | Natural via multiple INTOs |
| Transaction | Can commit/roll back per step if intentional | Single statement, statement-level atomic |
| Debugging | Easy to isolate each statement | Must read all branches and conditions together |

If you need a multi-step controlled transaction, separate DML statements in a transaction can be easier to manage. If you need fan-out or routing from a single source set, multitable insert is usually cleaner.

## 15. Transactions, Constraints, and Triggers

### 15.1. Statement Atomicity

A multitable insert is a single DML statement. When an error not handled by error logging causes the statement to fail, Oracle rolls back the changes produced by **that statement**. Earlier statements in the transaction are not automatically rolled back simply because the current multitable insert failed; the transaction remains controlled by the application or user.

### 15.2. Constraints Are Still Enforced

Each target table still enforces its own rules:

- PRIMARY KEY and UNIQUE.
- NOT NULL.
- CHECK.
- FOREIGN KEY.
- Data types, lengths, and precision/scale.

A row can satisfy WHEN and still fail on insert due to a constraint violation. The WHEN condition only decides whether to execute the branch; it does not replace table integrity checks.

### 15.3. Triggers

INSERT triggers defined on target tables can fire for the corresponding inserted rows. If a source row is inserted into two tables, inspect triggers on both tables, especially when triggers generate keys, write audits, modify data, or call packages.

Do not design triggers assuming each source row creates only one target row. With INSERT ALL, one source row can produce multiple inserts.

### 15.4. Verify Data Before Committing

~~~sql
SELECT COUNT(*) FROM small_orders;
SELECT COUNT(*) FROM medium_orders;
SELECT COUNT(*) FROM large_orders;
~~~

After reconciling row counts and values:

~~~sql
COMMIT;
~~~

If an incorrect result is found and not yet committed:

~~~sql
ROLLBACK;
~~~

DDL such as CREATE TABLE, ALTER TABLE, and DROP TABLE performs an implicit commit in Oracle; do not use ROLLBACK expecting to undo DDL.

## 16. Error Logging and Data Load Error Handling

Oracle supports the error_logging_clause in INSERT syntax, including multitable insert. Error logging can be useful when you want to record certain DML errors and continue processing other rows up to REJECT LIMIT.

General workflow:

1. Create an error log table with DBMS_ERRLOG.CREATE_ERROR_LOG for the target table you want to monitor.
2. Add LOG ERRORS INTO and REJECT LIMIT according to supported syntax.
3. Read the error log table to identify the row, error message, and tag.
4. Fix the source data or mapping rules, then re-run the failed subset.

Example of the logging mechanism with a single target table:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'ORDER_ARCHIVE',
        err_log_table_name => 'ERR_ORDER_ARCHIVE'
    );
END;
/

INSERT INTO order_archive (order_id, order_total)
SELECT order_id, order_total
FROM order_stage
LOG ERRORS INTO err_order_archive ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

This is a single-table INSERT example to illustrate the logging mechanism. When applying LOG ERRORS to multitable insert, verify how to create and specify appropriate error log tables for the target tables and the release's error logging limitations. Certain errors, such as deferred constraint violations or certain direct-path/unique-index cases, can still cause the statement to fail without going through error logging.

Error logging does not replace data validation. For critical imports, you should still use staging, data quality checks, count reconciliation, and batch auditing.

## 17. Limitations of Multitable Insert in Oracle 19c

Notable limitations per the SQL Language Reference:

- Multitable insert can only insert into tables, not directly into views or materialized views.
- You cannot insert directly into remote tables with multitable insert.
- You cannot use TABLE collection expressions in multitable insert.
- You cannot use the RETURNING clause with multitable insert.
- A table alias cannot be declared for a target table in an INTO branch.
- WHEN expressions must reference columns returned by the source query's select list.
- A statement can have at most 127 WHEN clauses.
- If any target table is an index-organized table or has a bitmap index, multitable insert cannot be parallelized per Oracle's documented conditions.
- Plan stability is not supported for multitable insert.

### 17.1. Specific Note on Sequences

The Oracle 19c Sequence Pseudocolumns documentation states that NEXTVAL can appear in VALUES of a multitable insert and increments once per source row; repeated references across branches for the same input row receive the same value. Follow the exact VALUES placement and verify results on your running release. Do not place NEXTVAL in the source select list expecting a new number per branch.

### 17.2. No RETURNING

Multitable insert does not support RETURNING. If the application needs to retrieve generated keys or confirm each target row, design an alternative workflow: prepare IDs in the source/staging, use sequences with proper semantics, or use separate INSERT statements with RETURNING when appropriate.

## 18. Performance and Source SELECT Design

### 18.1. Filter Source Rows Before Distributing

~~~sql
INSERT ALL
    WHEN is_valid = 1 THEN
        INTO accepted_orders (order_id, amount)
        VALUES (order_id, amount)
    ELSE
        INTO rejected_orders (order_id, amount, reason)
        VALUES (order_id, amount, 'INVALID')
SELECT order_id,
       amount,
       CASE
         WHEN amount IS NOT NULL AND amount >= 0 THEN 1
         ELSE 0
       END AS is_valid
FROM order_stage
WHERE batch_id = :batch_id;
~~~

WHERE filters the batch to process. WHEN routes each row in the batch. Avoid feeding rows from outside the batch into the statement.

### 18.2. Do Not Repeat Calculations in Every Branch

If multiple branches need the same normalization, compute it in the select list:

~~~sql
SELECT raw_code,
       UPPER(TRIM(raw_code)) AS normalized_code,
       amount,
       amount * exchange_rate AS converted_amount
FROM import_stage;
~~~

Then reference NORMALIZED_CODE or CONVERTED_AMOUNT in WHEN/VALUES. This reduces repetition and makes mapping rules clearer.

### 18.3. Check Fan-Out Row Volume

If there are N source rows and each row can go into multiple target tables, total DML volume can grow rapidly. Before a large batch, estimate source row counts, how many branches can trigger, overlapping conditions, tables requiring audit, and target table indexes/triggers/constraints.

### 18.4. Inspect Execution Plan

~~~sql
EXPLAIN PLAN FOR
INSERT ALL
    WHEN amount < 1000 THEN
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
    WHEN amount >= 1000 THEN
        INTO large_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM order_stage;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN shows the estimated plan. When runtime metrics are needed, use appropriate tools and privileges in a DBA environment; do not infer performance solely from the number of INTO branches.

## 19. Self-Contained Lab Dataset

This section creates small tables to practice order classification. Run only in a lab schema. If tables already exist, use different names or clean up only the objects you created.

### 19.1. Create Source and Target Tables

~~~sql
CREATE TABLE order_stage_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2),
    batch_id NUMBER NOT NULL
);

CREATE TABLE small_orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2)
);

CREATE TABLE medium_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE large_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE vip_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE invalid_orders_lab (
    order_id NUMBER,
    reason_code VARCHAR2(30 CHAR)
);
~~~

### 19.2. Load Source Data

~~~sql
INSERT INTO order_stage_lab VALUES (101, 10, 500, 1);
INSERT INTO order_stage_lab VALUES (102, 11, 2500, 1);
INSERT INTO order_stage_lab VALUES (103, 12, 12000, 1);
INSERT INTO order_stage_lab VALUES (104, 13, 75000, 1);
INSERT INTO order_stage_lab VALUES (105, 14, NULL, 1);
INSERT INTO order_stage_lab VALUES (106, 15, 900, 2);

COMMIT;
~~~

### 19.3. INSERT ALL Classifying One Batch

~~~sql
INSERT ALL
    WHEN order_total IS NULL THEN
        INTO invalid_orders_lab (order_id, reason_code)
        VALUES (order_id, 'MISSING_TOTAL')
    WHEN order_total < 1000 THEN
        INTO small_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 AND order_total < 10000 THEN
        INTO medium_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id, customer_id, order_total
FROM order_stage_lab
WHERE batch_id = 1;
~~~

The order with NULL ORDER_TOTAL is routed to INVALID_ORDERS_LAB. The remaining orders are classified by amount range.

### 19.4. INSERT FIRST with VIP Priority

~~~sql
INSERT FIRST
    WHEN order_total IS NULL THEN
        INTO invalid_orders_lab (order_id, reason_code)
        VALUES (order_id, 'MISSING_TOTAL')
    WHEN order_total >= 50000 THEN
        INTO vip_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO medium_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    ELSE
        INTO small_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id, customer_id, order_total
FROM order_stage_lab
WHERE batch_id = 2;
~~~

For batch 2, order 106 has amount 900 and is placed into SMALL_ORDERS_LAB. VIP conditions are placed before more general conditions.

### 19.5. Reconcile Results

~~~sql
SELECT 'SMALL' AS bucket, COUNT(*) AS row_count
FROM small_orders_lab
UNION ALL
SELECT 'MEDIUM', COUNT(*) FROM medium_orders_lab
UNION ALL
SELECT 'LARGE', COUNT(*) FROM large_orders_lab
UNION ALL
SELECT 'VIP', COUNT(*) FROM vip_orders_lab
UNION ALL
SELECT 'INVALID', COUNT(*) FROM invalid_orders_lab;
~~~

If you re-run the same batch, primary keys can cause duplicate key errors. To practice again, roll back before commit if still in the transaction, or delete the specific lab data loaded for that batch. Do not re-run blindly on business tables.

### 19.6. Clean Up Lab Tables (Optional)

~~~sql
DROP TABLE order_stage_lab PURGE;
DROP TABLE small_orders_lab PURGE;
DROP TABLE medium_orders_lab PURGE;
DROP TABLE large_orders_lab PURGE;
DROP TABLE vip_orders_lab PURGE;
DROP TABLE invalid_orders_lab PURGE;
~~~

DDL performs an implicit commit. Skip this step if you want to keep the data for practice.

## 20. Common Errors

| Error/Symptom | Cause | How to fix |
| --- | --- | --- |
| ORA-00928: missing SELECT keyword | Missing source query at the end of multitable insert or structural error | Check the SELECT at the end of the statement |
| ORA-00913: too many values | Number of expressions in VALUES does not match target column count | Compare column list and VALUES per branch |
| ORA-00947: not enough values | Fewer expressions than target columns | Add missing values or omit columns with defaults from the column list |
| ORA-01400: cannot insert NULL | NULL source value into a NOT NULL column | Check NULL handling, defaults, and WHEN conditions |
| ORA-00001: unique constraint violated | Source data has duplicate keys or batch already loaded | Check keys, source duplicates, and idempotency |
| One row appears in multiple tables | Using INSERT ALL with overlapping WHENs | Verify whether fan-out is intentional or INSERT FIRST is needed |
| VIP branch does not execute | General branch appears earlier in INSERT FIRST | Place specific conditions before general conditions |
| Row is not inserted anywhere | No WHEN matched and no ELSE | Add ELSE or handle skipped cases separately |
| WHEN condition does not recognize expected alias | Expression alias was not exposed from the select list | Put the expression in the select list with an alias and reference that alias |
| Dates/numbers converted incorrectly | Implicit conversion depending on NLS | Use explicit data types and conversions |
| Parent/child keys mismatch | Misunderstanding NEXTVAL semantics across branches | NEXTVAL increments once per source row; branches for the same row get the same value |
| Cannot retrieve returned ID | Multitable insert does not support RETURNING | Prepare IDs in source or use a different DML workflow |
| Batch results cannot be reconciled | Batch ID or audit metadata was not recorded | Include batch key in source and traceable target tables |

## 21. Checklist Before Running a Multitable Insert

1. **What columns does the source query return?** Alias expressions used in WHEN/VALUES.
2. **Which table does each INTO branch write to?** Specify the column list and value order.
3. **Use ALL or FIRST?** Can one row go to multiple branches or only one prioritized branch?
4. **Do conditions overlap?** If yes, confirm that is the intended behavior.
5. **Is ELSE needed?** Clarify whether unmatched rows should be skipped or routed to a default table.
6. **How is NULL handled?** UNKNOWN does not trigger WHEN.
7. **Does a sequence need to share IDs across branches?** NEXTVAL increments once per input row and branches for that row receive the same value.
8. **What constraints, triggers, and indexes exist on target tables?** Check duplicates, NOT NULL, FKs, and side effects.
9. **Is RETURNING needed?** If yes, multitable insert is not directly suitable.
10. **Is error logging needed?** Prepare the error table and understand its limitations.
11. **Is the batch filtered properly?** Avoid accidentally inserting all of staging.
12. **Have results been reconciled before COMMIT?** Check row counts and key values.

## 22. Self-Check Questions

**Question 1.** Which part does a multitable insert use to generate input rows?

**Question 2.** With INSERT ALL without WHEN, how many INTO branches receive each source row?

**Question 3.** If two WHEN conditions are both true in INSERT ALL, what happens?

**Question 4.** If two WHEN conditions are both true in INSERT FIRST, what happens?

**Question 5.** When is the ELSE branch executed?

**Question 6.** If there is no ELSE and no WHEN is true, what happens to the source row?

**Question 7.** Can a WHEN clause directly reference a source table alias like O.AMOUNT? What is the clearer way to write it?

**Question 8.** Does a WHEN condition evaluating to UNKNOWN due to a NULL column trigger the branch?

**Question 9.** Can the same target table be repeated across multiple INTO branches?

**Question 10.** In a multitable insert, does NEXTVAL increment per branch or per source row?

**Question 11.** Why do repeated NEXTVAL references across multiple branches for the same source row receive the same value?

**Question 12.** Does multitable insert support RETURNING?

**Question 13.** Why is a column list needed for each INTO?

**Question 14.** When should you use UNPIVOT instead of INSERT ALL?

<details>
<summary>Answer hints</summary>

1. The SELECT query at the end of the statement.
2. Every unconditional INTO branch is executed once for each source row.
3. All branches whose conditions evaluate to TRUE execute.
4. Only the first branch whose condition evaluates to TRUE executes.
5. When no WHEN condition evaluates to TRUE for the current source row.
6. That source row is skipped and not inserted into any table.
7. Expressions depending on the select list should use columns projected by the select list; put O.AMOUNT or the calculation in the select list with an alias, then reference that alias.
8. No. UNKNOWN is not TRUE.
9. Yes. This is a common technique to turn multiple source columns into multiple rows in the same target table.
10. Once per source row, not once per INTO branch.
11. Oracle uses the same NEXTVAL value for references belonging to a single input row within a multitable insert.
12. No.
13. To map values accurately, avoid depending on table column order, and make maintenance easier.
14. When the primary goal is turning a group of columns into rows in the source query; afterward you can use INSERT INTO ... SELECT to save the result.

</details>

## 23. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): multitable insert syntax, ALL/FIRST, WHEN/ELSE, VALUES mapping, limitations, and official examples.
2. [Oracle Database 19c SQL Language Reference — Sequence Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sequence-Pseudocolumns.html): where NEXTVAL/CURRVAL can be used and how sequences behave in multitable inserts.
3. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT syntax and UNPIVOT for turning columns into rows.
4. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ERRLOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html): creating error logging tables for DML error logging.
5. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plans and DML performance evaluation.

**Key takeaway:** INSERT ALL evaluates every matching branch so one source row can be written to multiple tables; INSERT FIRST stops at the first true WHEN branch. ELSE handles rows matching no condition. The source query provides columns for WHEN and VALUES to use, so use clear aliases, map column lists accurately, control NULLs, and understand sequence semantics. Choose ALL or FIRST according to the exact data distribution rules, then reconcile results before committing.
