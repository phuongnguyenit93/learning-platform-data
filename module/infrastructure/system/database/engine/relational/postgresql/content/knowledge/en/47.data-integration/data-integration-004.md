# Pushing Down Predicates, JOINs, and Aggregates to a Remote Server in PostgreSQL

When PostgreSQL queries data through a foreign table, the SQL sent from the local database to the remote server can be executed in two very different ways. The local server can request many remote rows and filter, JOIN, and GROUP BY them locally; or it can send a large portion of the work to the remote server, receiving only the final matching rows or aggregated results. The second approach is called **query pushdown** (pushing query processing down to the remote server).

Pushdown typically reduces data transferred over the network, reduces round trips between the two servers, and takes advantage of the indexes, CPU, statistics, and resources of the server that owns the data. However, PostgreSQL only pushes an expression down when the foreign-data wrapper (FDW) determines that it can be executed safely while preserving exact semantics. With **postgres_fdw**, WHERE predicates, JOINs between foreign tables on the same server, aggregates, ORDER BY, and LIMIT can be pushed down in eligible cases. The planner still retains the right to choose a different plan if cost estimates indicate that another approach is better.

Therefore, you cannot look at a SQL query and assume that the entire statement ran on the remote server. You must inspect the execution plan using EXPLAIN VERBOSE, especially the Remote SQL section, to know exactly what is sent remotely and what still executes on the local server.

This lesson focuses on predicate pushdown, join pushdown, and aggregate pushdown with postgres_fdw; it also explains shippability conditions, user mappings, data types/collations, cost estimates, transaction semantics, and how to observe and troubleshoot cases where pushdown does not occur.

~~~text
                  Local PostgreSQL
                         |
                    SQL query
                         |
                         v
                  Query planner
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Shippable expressions     Local-only work
             |                       |
             v                       v
       Remote SQL request       Local Filter/Join/
             |                  Aggregate/Sort
             v                       ^
        Remote server                |
      WHERE / JOIN / GROUP BY        |
             |                       |
             v                       |
       Reduced result set -----------+
                         |
                         v
                   Final result
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **Data Integration**, on the topic **“Pushing Down Predicates, JOINs, and Aggregates to a Remote Server”**.

---

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain query pushdown and why reducing data transfer between PostgreSQL servers matters.
2. Distinguish local-server processing from remote-server processing.
3. Describe the role of FDWs and postgres_fdw.
4. Set up a foreign server, user mapping, and foreign tables for hands-on practice.
5. Identify projection pushdown and predicate pushdown.
6. Explain which WHERE conditions can be sent to the remote server.
7. Understand the concept of a shippable expression and the IMMUTABLE requirement.
8. Configure the extensions option to allow certain extension functions/operators to be shipped.
9. Explain join pushdown and the requirement that foreign tables share the same foreign server and user mapping.
10. Recognize when the planner decides to fetch each table separately instead of sending a JOIN.
11. Understand aggregate pushdown, GROUP BY, HAVING, and limitations by expression/FDW version.
12. Use EXPLAIN VERBOSE to inspect Remote SQL.
13. Distinguish Remote SQL from local Filter, Hash Join, HashAggregate, or Sort nodes in the local plan.
14. Read Foreign Scan costs and understand use_remote_estimate.
15. Update foreign table statistics using ANALYZE.
16. Tune fetch_size and understand its limitations.
17. Distinguish fetch_size from batch_size.
18. Understand the impact of data types, collations, and version differences on pushdown.
19. Explain how user mappings affect JOIN pushdown eligibility and remote permissions.
20. Monitor queries on both the local server and the remote server.
21. Distinguish beneficial pushdown from pushdown that overloads the remote server.
22. Design queries to improve pushdown eligibility while preserving exact semantics.
23. Investigate queries that unexpectedly filter or aggregate locally.
24. Build a checklist, runbook, and lab to measure pushdown effectiveness.

**Scope:** The focus is postgres_fdw between PostgreSQL servers. Other FDWs may support different pushdown capabilities. Exact behavior depends on the PostgreSQL version, remote server version, extensions, schemas, user mappings, and cost estimates. Always verify the actual execution plan in the target environment.

---

## 2. What Is Query Pushdown?

Query pushdown is when an FDW offloads part of a query's operations to a remote system so that the remote system executes them. Local PostgreSQL still coordinates the query and may continue processing the remaining steps.

### 2.1. Without Pushdown

Suppose a remote table has 10 million rows, but the application only needs 500 rows matching a date and status condition.

If the condition is not pushed down:

1. The local server requests rows from the foreign table.
2. The remote server returns a large amount of data.
3. The local server performs a Filter.
4. The local server retains 500 rows.

Unnecessary data has already traveled across the network.

### 2.2. With Predicate Pushdown

If WHERE is shipped:

1. The local server sends the query with the filter condition to the remote server.
2. The remote server uses indexes or an appropriate scan to filter.
3. The remote server returns only the matching rows.
4. The local server processes a much smaller result set.

### 2.3. With JOIN Pushdown

If two foreign tables reside on the same remote server and share the same user mapping, the FDW can send the JOIN to be executed by the remote server.

Instead of pulling both tables locally and joining them, the local server receives the already-filtered JOIN result.

### 2.4. With Aggregate Pushdown

If GROUP BY and aggregate expressions are shippable, the remote server can return one row per group instead of sending all raw rows to the local server.

For example, the remote server has 20 million orders, but only total revenue by month and region is needed. If aggregation is pushed down, the returned data might be only a few hundred rows.

### 2.5. Pushdown Is Not a Global Switch

A query can be partially pushed down:
- WHERE is shipped, while another condition runs locally.
- JOIN is shipped, while a JOIN with a local table runs locally.
- Aggregate is shipped, while an expression in SELECT runs locally.
- ORDER BY or LIMIT is shipped in some plans, while other parts remain local.

You must inspect each node in the plan.

---

## 3. FDWs and postgres_fdw

A Foreign Data Wrapper is an integration layer that allows PostgreSQL to access data residing outside the current database using foreign tables.

### 3.1. Components

| Component | Role |
| --- | --- |
| Extension | Installs the FDW implementation |
| Foreign server | Describes the remote data source and connection options |
| User mapping | Maps a local role to remote credentials/identity |
| Foreign table | Local schema representation of a remote table/view |
| FDW planner hooks | Decide which expressions and operations can be pushed down |
| FDW executor | Executes remote requests and streams rows back locally |

### 3.2. postgres_fdw

postgres_fdw is an FDW shipped with PostgreSQL contrib modules for accessing data on another PostgreSQL server. It provides natural SQL syntax via foreign tables and can optimize WHERE, JOIN, and certain upper-level operations.

### 3.3. A Foreign Table Does Not Store a Copy of the Data

A foreign table is metadata on the local server. Rows are read from the remote server when the query runs, unless data is materialized or copied separately.

### 3.4. Pushdown Is Determined by the FDW

The PostgreSQL planner asks the FDW which paths can be executed remotely. Each FDW has different capabilities. An FDW accessing another PostgreSQL instance can typically push down far more expression types than an FDW accessing CSV files, REST APIs, or NoSQL systems.

### 3.5. Not Equivalent to a Full Distributed Query Engine

postgres_fdw allows combining remote and local data, but it does not automatically turn multiple PostgreSQL servers into a distributed cluster with a full global optimizer, 2PC distributed transactions, or complete global statistics.

---

## 4. Setting Up postgres_fdw

The examples assume one local PostgreSQL server and one remote PostgreSQL server. Replace hostnames, databases, roles, and schemas with your lab environment values.

### 4.1. Install the Extension on the Local Server

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

postgres_fdw must be installed in the local database where the foreign server will be created.

### 4.2. Create the Foreign Server

~~~sql
CREATE SERVER sales_remote
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'remote-db.example.test',
    port '5432',
    dbname 'sales'
);
~~~

The foreign server describes the remote endpoint. Do not put a username or password here; credentials belong in the user mapping or an appropriate authentication mechanism.

### 4.3. Create the User Mapping

~~~sql
CREATE USER MAPPING FOR reporting_user
SERVER sales_remote
OPTIONS (
    user 'sales_reader',
    password 'replace-with-secret-reference'
);
~~~

This example uses a placeholder. Do not commit real passwords into migration repositories, tickets, or logs. In production, use approved secret management and authentication policies.

### 4.4. Create a Local Schema

~~~sql
CREATE SCHEMA remote_sales;
~~~

This schema is simply a local namespace to hold foreign table definitions.

### 4.5. Import the Foreign Schema

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (orders, customers)
FROM SERVER sales_remote
INTO remote_sales;
~~~

This command creates foreign table definitions based on remote objects. You can use CREATE FOREIGN TABLE manually if you need explicit control over names, columns, or options.

### 4.6. Inspect Foreign Tables

~~~sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
ORDER BY foreign_table_schema, foreign_table_name;
~~~

### 4.7. Verify Metadata Alignment

Data types, column names, and collations on the foreign table should match the remote table. Mismatched declarations can cause unexpected conversions or cause predicates to be evaluated differently.

### 4.8. Access Privileges

The local role needs privileges to use the foreign server, schema, and foreign tables. The remote mapped role needs SELECT privileges on the remote objects. Pushdown does not bypass the remote user's permissions.

---

## 5. Projection Pushdown: Fetching Only Needed Columns

Projection pushdown is when the FDW requests only the columns that the query actually needs.

### 5.1. Example Selecting All Columns

~~~sql
SELECT *
FROM remote_sales.orders;
~~~

The query requests every column. If the table has large payloads or many unused columns, data transfer can be substantial.

### 5.2. Selecting Only Required Columns

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM remote_sales.orders;
~~~

The FDW can fetch only the columns required by the query and any local expressions.

### 5.3. Projection Combined with a Predicate

~~~sql
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= DATE '2026-01-01';
~~~

If WHERE is shipped, the remote server both filters rows and returns only the needed columns.

### 5.4. Benefits

- Reduces bytes transferred over the network.
- Reduces serialization/deserialization overhead.
- Reduces local memory usage and tuple processing.
- Can leverage index-only or index scans if the remote plan is suitable.

### 5.5. SELECT * in Views and Reporting

A view using SELECT * can unintentionally pull extra columns when the remote schema changes. For integration queries, select explicit columns to keep payloads predictable.

---

## 6. Predicate Pushdown with WHERE

Predicate pushdown is sending filter conditions to the remote server.

### 6.1. Built-in Conditions

~~~sql
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE customer_id = 42
  AND total_amount > 1000;
~~~

Built-in data types and operators are generally shippable when semantics are compatible.

### 6.2. Combining Multiple Predicates

~~~sql
SELECT
    order_id,
    customer_id,
    created_at
FROM remote_sales.orders
WHERE status IN ('paid', 'shipped')
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
~~~

The remote server can apply these conditions before sending results.

### 6.3. AND and OR

A boolean expression can be shipped if all of its required components are shippable. If part of it is not shippable, the FDW may ship only the safe clauses and keep the rest local, depending on how the planner splits the expression.

### 6.4. Predicates on Join Keys

A WHERE condition filtering a foreign table before a JOIN can reduce the number of rows that need to be joined. If the JOIN is also pushed down, the remote server can combine filtering and joining in the same remote query.

### 6.5. Range Predicates

Date/time or numeric range predicates are especially useful when the remote table has a matching index:

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Using a half-open interval helps avoid boundary bugs at the end of a period.

### 6.6. Predicate Pushdown Does Not Create Indexes

The FDW only sends the condition. The remote server still needs appropriate indexes or an efficient execution plan. If the remote server has to sequentially scan the entire table, network traffic may drop, but remote CPU/I/O will still be high.

---

## 7. Shippability: Conditions for Sending an Expression Remotely

Shippability is whether an expression can be safely executed on the remote server with the exact same semantics required by the local query.

### 7.1. Built-in Types, Operators, and Functions

By default, postgres_fdw only considers WHERE clauses using built-in types, operators, and functions as candidates for shipping. This reduces the risk that local and remote servers interpret the same function/operator name differently.

### 7.2. IMMUTABLE

Functions and operators in shipped clauses must satisfy the IMMUTABLE requirement. An IMMUTABLE function is guaranteed by PostgreSQL to return the same result for the same arguments, without depending on current time, session settings, or database state.

### 7.3. STABLE and VOLATILE

Functions with STABLE or VOLATILE volatility do not meet the IMMUTABLE requirement for shipping under this mechanism. For example, a function depending on the current time or a random value could produce different results if evaluated on two servers or at two different times.

### 7.4. User-Defined Functions

~~~sql
CREATE FUNCTION public.normalize_code(value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT upper(trim(value));
$$;
~~~

Even though the function is declared IMMUTABLE, it is not automatically shipped simply because of that attribute. By default, it is not part of the built-in set. You either need extension shippability configuration or must evaluate the expression locally.

### 7.5. Do Not Mark a Function IMMUTABLE Just for Speed

A volatility declaration is a semantic contract. Declaring it inaccurately can produce wrong query results due to constant folding, caching, and pushdown. Never change a function's volatility if it depends on tables, configuration, timezone, or external state.

### 7.6. Mixed Expressions

A WHERE clause may contain:
- A remote column.
- A built-in operator.
- A built-in function.
- A local parameter.
- A user-defined function.
- A collation-sensitive operation.

The FDW evaluates the full expression and may ship only the safe portion.

### 7.7. Constants and Parameters

Constants can be rendered in remote SQL. Values coming from local expressions or parameters must be evaluated in the context of the plan. Do not assume every correlated subquery or local parameter will be converted into a remote predicate.

---

## 8. Allowing Extension Functions to Be Shipped

postgres_fdw provides the server option extensions to specify PostgreSQL extensions installed on both local and remote servers with compatible versions.

### 8.1. Configuration

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD extensions 'my_immutable_extension');
~~~

If the option is already set, use SET instead of ADD. The option takes a list of extension names, not a list of function names.

### 8.2. Requirements

- The extension must exist on both local and remote servers.
- Versions must be compatible.
- Shipped functions/operators must be IMMUTABLE.
- Semantics must be identical between the two servers.

### 8.3. Operator Responsibility

Listing an extension in the extensions option is an assertion that the extension exists and behaves equivalently on both sides. PostgreSQL does not automatically prove that both extension installations behave identically.

### 8.4. Do Not List Every Extension

Only add extensions that are genuinely needed and verified. Do not grant shippability to extensions whose behavior depends on external state or differs across versions.

### 8.5. Checking Function Volatility

~~~sql
SELECT
    n.nspname,
    p.proname,
    p.provolatile,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname = 'normalize_code';
~~~

provolatile contains values indicating immutable, stable, and volatile. Inspect the catalog on both local and remote servers if a function is shipped.

### 8.6. When Equivalence Cannot Be Guaranteed

Keep the function running locally or normalize data before passing it into the foreign query. Never trade correctness for lower network traffic.

---

## 9. Collation and Data Type Compatibility

A predicate may be shipped yet produce different results if local and remote servers do not interpret types or collations identically.

### 9.1. Declare Matching Data Types

Foreign table columns should be declared with the same data types as the remote table. Avoid mapping remote numeric to text or timestamp to a different type without a clear reason.

### 9.2. Text Collations

Text comparisons and sorting depend on collation. If local and remote servers use different providers or locales, a text predicate or JOIN can produce different semantics.

### 9.3. Importing Collations

IMPORT FOREIGN SCHEMA provides the import_collate option. Disabling collation import can avoid errors about missing collation names, but it carries the serious risk of causing local collations to mismatch remote data.

### 9.4. Inspecting Collations

~~~sql
SELECT
    n.nspname,
    c.collname,
    c.collprovider,
    c.collcollate,
    c.collctype
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
ORDER BY n.nspname, c.collname;
~~~

Compare the output across both servers and confirm that columns and indexes use matching collations.

### 9.5. Timestamps and Timezones

postgres_fdw sets certain session parameters on remote sessions, including TimeZone UTC, DateStyle ISO, and IntervalStyle postgres. This helps stabilize representations, though applications must still maintain consistent timezone semantics.

### 9.6. Numeric Precision

Verify numeric precision/scale, floating-point behavior, and casts. Local/remote conversions can affect predicates and grouping.

### 9.7. Cross-Version Built-ins

postgres_fdw may treat built-in immutable functions/operators as shippable. If an older remote PostgreSQL server lacks a newer function known to the local server, the remote query can fail with function does not exist. Check version compatibility or write the query so that the expression evaluates locally.

---

## 10. JOIN Pushdown

JOIN pushdown allows the remote server to combine data from multiple foreign tables before returning rows to the local server.

### 10.1. Two Foreign Tables on the Same Remote Server

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

If the planner chooses join pushdown, the Remote SQL will include both the JOIN and the WHERE. The remote server can use indexes on the join keys and filter columns.

### 10.2. Same Foreign Server Requirement

Foreign tables participating in join pushdown must belong to the same foreign server object, meaning the same configured remote endpoint/database.

### 10.3. User Mapping Requirement

The table references must use the same user mapping. If they are accessed under different remote identities, postgres_fdw cannot simply send a single JOIN under one remote identity.

### 10.4. Shippability of Join Clauses

Join expressions must use shippable types, operators, and functions. A join condition containing local-only functions or incompatible semantics can force the join to run locally.

### 10.5. The Planner May Still Choose Not to Push the JOIN

Even when a JOIN is shippable, postgres_fdw may estimate that fetching each table separately is more efficient. Cost, cardinality, local joins, and query shape all influence the decision.

### 10.6. JOIN Between Two Different Foreign Servers

~~~sql
SELECT *
FROM remote_sales.orders AS o
JOIN remote_hr.employees AS e
    ON e.employee_id = o.sales_rep_id;
~~~

If the two tables belong to different foreign servers, a standard JOIN cannot be sent to a single remote server. Local PostgreSQL typically must fetch rows from each side and join them locally, unless a specific FDW or distributed system provides another mechanism.

### 10.7. JOIN Between a Foreign Table and a Local Table

~~~sql
SELECT
    o.order_id,
    d.department_name
FROM remote_sales.orders AS o
JOIN public.department AS d
    ON d.department_id = o.department_id;
~~~

The remote server does not have the local table public.department. The local server must execute this JOIN. Predicates referencing only remote columns can still be shipped before rows are transferred back.

### 10.8. Filter Before Join

Include meaningful filters on remote tables in the query so the planner has the opportunity to push them down. However, do not rewrite queries purely cosmetically; preserve semantics and verify with EXPLAIN.

### 10.9. Outer Joins

LEFT/RIGHT/FULL JOIN have specific semantics regarding NULL extension. A condition placed in ON and a condition placed in WHERE are not equivalent in all cases. Do not move predicates between ON and WHERE just to force pushdown if doing so changes the result.

### 10.10. Lateral and Correlated Operations

LATERAL, correlated subqueries, or local parameters can produce parameterized foreign scans. Pushdown behavior depends on the FDW and the plan. Inspect Remote SQL and the number of times Foreign Scan executes; never assume a single remote request.

---

## 11. Aggregate Pushdown: GROUP BY and Aggregate Functions

Aggregate pushdown enables the remote server to compute aggregated results before returning data to the local server.

### 11.1. GROUP BY Example

~~~sql
SELECT
    date_trunc('month', created_at) AS month,
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY 1, 2
ORDER BY 1, 2;
~~~

If the expressions and aggregate calls are shippable, the remote server can perform filtering, grouping, and aggregation. The local server receives only the group rows.

### 11.2. Aggregate Functions

Common aggregates such as count, sum, min, max, and avg can usually be pushed down when the corresponding function, operator, and types are shippable and the query shape is supported.

### 11.3. GROUP BY Expressions

Expressions in GROUP BY must be shippable. A grouping key containing a local-only function can prevent aggregate pushdown or cause part of the processing to happen locally.

### 11.4. HAVING

HAVING filters groups after aggregation. Shippable HAVING conditions can be sent remotely. If a condition is not shippable, the planner may evaluate it locally or decline to push the aggregate depending on the structure required.

### 11.5. FILTER in Aggregates

~~~sql
SELECT
    customer_id,
    count(*) AS all_orders,
    count(*) FILTER (WHERE status = 'paid') AS paid_orders,
    sum(total_amount) FILTER (WHERE status = 'paid') AS paid_revenue
FROM remote_sales.orders
GROUP BY customer_id;
~~~

Both the FILTER expressions and the aggregate implementation must be shippable. Specific support depends on the PostgreSQL/FDW version and query plan; inspect Remote SQL.

### 11.6. DISTINCT Inside Aggregates

~~~sql
SELECT
    customer_id,
    count(DISTINCT product_id)
FROM remote_sales.order_items
GROUP BY customer_id;
~~~

DISTINCT inside an aggregate can affect deparsing/shipping capability depending on the aggregate and FDW version. Do not apply a blanket rule to every aggregate. Use EXPLAIN VERBOSE to verify.

### 11.7. ORDER BY Inside Aggregates

~~~sql
SELECT
    customer_id,
    string_agg(product_name, ', ' ORDER BY product_name)
FROM remote_sales.order_items
GROUP BY customer_id;
~~~

Aggregates with ORDER BY require compatible remote sort semantics and sort operators. This case must be verified in practice, especially with collations or custom types.

### 11.8. Grouping Sets, ROLLUP, and CUBE

Advanced grouping constructs may not be pushed down by postgres_fdw in certain plans or versions. If not shipped, the local server may have to fetch rows and aggregate them locally. Always inspect the plan instead of assuming every GROUP BY is handled remotely.

### 11.9. Non-Shippable Aggregates

A user-defined aggregate or an aggregate function missing or incompatible on the remote server cannot be safely executed remotely. If the local server must compute it, input rows may need to be transferred back.

### 11.10. Query-Level DISTINCT

SELECT DISTINCT is not the same as DISTINCT inside an aggregate. Do not infer the pushdown capability of one form of DISTINCT from the other.

### 11.11. Aggregate and JOIN Together

A query may need to join foreign tables first and then group. If both the JOIN and the aggregate are pushable, the remote server can run the entire pipeline. If the join cannot be pushed down, aggregation may also be pulled locally because its input is produced locally.

### 11.12. Checking Row Counts After Aggregation

The benefit is greatest when the number of groups is much smaller than the number of input rows. If nearly every row forms a distinct group, aggregate pushdown may not significantly reduce the payload.

---

## 12. ORDER BY, LIMIT, and OFFSET Pushdown

Upper-level operations such as sorting and limiting can also be shipped when semantics are equivalent and supported by the FDW.

### 12.1. ORDER BY

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
ORDER BY created_at DESC;
~~~

If ORDER BY is shipped, the remote server can use an index or sort before sending rows.

### 12.2. LIMIT

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
ORDER BY created_at DESC
LIMIT 100;
~~~

If the remote server executes LIMIT, only 100 rows are transferred instead of all matching rows.

### 12.3. OFFSET

~~~sql
SELECT order_id
FROM remote_sales.orders
ORDER BY order_id
LIMIT 100 OFFSET 500;
~~~

OFFSET can be pushed down in eligible cases, though deep pagination can still require substantial remote scanning/sorting. Keyset pagination typically offers more stable performance when a suitable index exists.

### 12.4. ORDER BY Must Share Identical Semantics

Collation, NULL ordering, data type, and operator differences can cause remote ordering to differ from local ordering. The FDW should only ship sorting when identical semantics are guaranteed.

### 12.5. LIMIT Does Not Replace Filtering

If a query lacks selective predicates, LIMIT only caps the number of returned rows; the remote server may still need to scan or sort many rows to find the top rows.

---

## 13. Query Plans: EXPLAIN VERBOSE Is the Most Important Tool

You cannot confirm pushdown from SQL syntax or execution time alone. Read the plan.

### 13.1. EXPLAIN

~~~sql
EXPLAIN
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid';
~~~

EXPLAIN displays the local plan and cost estimates.

### 13.2. EXPLAIN VERBOSE

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid';
~~~

With postgres_fdw, the Foreign Scan output can show the Remote SQL field. This is the SQL sent to the remote server.

### 13.3. Example Plan with Predicate Pushdown

Illustrative output:

~~~text
Foreign Scan on remote_sales.orders
  Output: order_id, total_amount
  Remote SQL: SELECT order_id, total_amount
              FROM public.orders
              WHERE (status = 'paid'::text)
~~~

The status predicate is sent remotely. Actual table/schema names and casts depend on the foreign table mapping.

### 13.4. Example with Local Filter

~~~text
Foreign Scan on remote_sales.orders
  Output: order_id, status, total_amount
  Filter: (local_normalize(status) = 'paid'::text)
  Remote SQL: SELECT order_id, status, total_amount
              FROM public.orders
~~~

In this example, local_normalize is not shipped. The remote server returns the needed rows and columns, and the local server applies the Filter.

### 13.5. Example JOIN Pushdown

~~~text
Foreign Scan
  Remote SQL: SELECT o.order_id, c.customer_name
              FROM public.orders o
              JOIN public.customers c
                ON c.customer_id = o.customer_id
              WHERE (o.status = 'paid'::text)
~~~

The Remote SQL contains the JOIN. This indicates that the join is executed remotely.

### 13.6. Example Aggregate Pushdown

~~~text
Foreign Scan
  Remote SQL: SELECT status, count(*), sum(total_amount)
              FROM public.orders
              GROUP BY status
~~~

If an Aggregate node still appears in the local plan above Foreign Scan, verify whether Remote SQL already grouped the data or if the local server is performing additional aggregation.

### 13.7. A Local Plan Can Have Multiple Foreign Scans

A single query can produce multiple Foreign Scan nodes. Read the full plan to identify which node performs joins/aggregates and how many times remote queries are sent.

### 13.8. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY status;
~~~

EXPLAIN ANALYZE executes the query for real. Use it only when you understand the workload and impact. Local BUFFERS does not automatically capture full remote buffer usage; inspect the remote server separately.

### 13.9. EXPLAIN Does Not Prove the Remote Query Is Fast

Shipped Remote SQL does not guarantee a good remote plan. Run EXPLAIN on the remote server with the corresponding SQL and check indexes, rows, buffers, waits, and query duration.

### 13.10. Save Before/After Plans

When tuning, record:
- SQL.
- EXPLAIN VERBOSE.
- EXPLAIN ANALYZE where appropriate.
- Remote SQL.
- Estimated/actual rows.
- Bytes transferred if telemetry is available.
- Local/remote CPU and I/O.
- End-to-end duration.

---

## 14. Cost Estimation and Pushdown Selection

The planner selects a plan based on row estimates and costs. Pushdown may be valid yet not chosen if the cost model estimates another alternative to be cheaper.

### 14.1. use_remote_estimate

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD use_remote_estimate 'true');
~~~

This option tells postgres_fdw to issue a remote EXPLAIN to obtain row count and cost estimates. It can also be set on a foreign table to override the server setting.

### 14.2. When use_remote_estimate=false

postgres_fdw uses local estimates and adds FDW overhead. Estimates can be inaccurate if local statistics for the foreign table are stale or missing.

### 14.3. ANALYZE Foreign Table

~~~sql
ANALYZE remote_sales.orders;
~~~

ANALYZE reads remote data to build local statistics for the foreign table. This improves local estimates when remote estimates are not used.

### 14.4. Cost of Remote Estimates

Remote EXPLAIN adds network round trips and planning overhead. For simple queries or high-latency links, planning cost can become noticeable.

### 14.5. fdw_startup_cost

This option represents the startup overhead of a foreign scan, such as connection setup, remote parse/planning, and initialization.

### 14.6. fdw_tuple_cost

This option represents the additional cost per tuple transferred between remote and local servers. It may be tuned for network latency/bandwidth, but should not be altered solely to force the planner into a desired plan.

### 14.7. Stale Statistics

If the remote table changes frequently, local statistics can quickly become outdated. A plan that was optimal yesterday can become inefficient after cardinality shifts.

### 14.8. The Planner May Fetch Tables Separately

Even when JOIN pushdown is valid, the planner may estimate that fetching each table separately and joining locally is cheaper. Check estimates and remote indexes before forcing changes.

### 14.9. Do Not Tune Costs by Guesswork

Compare:
- Network latency and throughput.
- Remote CPU/I/O.
- Rows and bytes returned.
- Local CPU/memory.
- Remote query duration.
- Planning overhead.
- Remote server concurrency.

---

## 15. fetch_size and Round Trips

fetch_size determines how many rows postgres_fdw retrieves in each fetch operation.

### 15.1. Default

The default is typically 100 rows. It can be configured on the foreign server or foreign table.

### 15.2. Server-Level Configuration

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD fetch_size '1000');
~~~

If the option already exists, use SET.

### 15.3. Table-Level Configuration

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (ADD fetch_size '2000');
~~~

A table-level setting overrides the server-level setting.

### 15.4. fetch_size Is Not Predicate Pushdown

fetch_size changes how already-selected rows are fetched in batches. It does not make WHERE or JOIN shippable.

### 15.5. fetch_size Too Small

Can cause excessive round trips, increasing latency and protocol overhead.

### 15.6. fetch_size Too Large

Can increase memory consumption and the volume of data buffered at once. Choose a value based on row width, network characteristics, and concurrency.

### 15.7. Measure Instead of Guessing

Benchmark multiple fetch_size values and measure latency, memory, and network traffic. Use a representative workload, not just a single tiny query.

---

## 16. async_capable and Multiple Foreign Scans

postgres_fdw provides the async_capable option for certain Append plans.

### 16.1. Meaning

Async execution allows multiple subplans of an Append node to execute concurrently rather than sequentially, when supported by the plan and FDW.

### 16.2. Configuration

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD async_capable 'true');
~~~

Or configure it at the foreign table level depending on the supported version/option scope.

### 16.3. Default

This option defaults to false. Enabling it does not guarantee that every query will run in parallel.

### 16.4. Same Foreign Server and User Mapping

To preserve data consistency, postgres_fdw typically uses a single connection per foreign server and executes queries sequentially on that connection unless table references use different user mappings. Therefore, async may provide no benefit in some scenarios.

### 16.5. Async Does Not Replace JOIN Pushdown

Async Append executes multiple subplans concurrently. It is not a mechanism for sending a JOIN between two tables to the remote server.

### 16.6. Inspect the Plan

Verify the Async Append/Append node and actual behavior. Do not draw conclusions solely from having enabled the option.

---

## 17. Common Reasons Pushdown Does Not Happen

| Cause | Common Symptom | How to Check |
| --- | --- | --- |
| Non-shippable function | Filter runs locally | Remote SQL and local Filter |
| Incompatible operator/type | Expression is not shipped | Catalog, type mapping |
| Function is not IMMUTABLE | Ineligible for shipping | pg_proc.provolatile |
| Extension not listed in extensions | Extension function runs locally | Foreign server options |
| Mismatched extension versions | Unsafe or remote error | Local/remote extension inventory |
| Different foreign servers | Local JOIN | Foreign server mapping |
| Different user mappings | JOIN pushdown restricted | User mapping identities |
| Local table in JOIN | That JOIN must run locally | Plan nodes |
| Planner estimates remote join as costly | Fetch separately then join | Costs and statistics |
| Different collations | Not shipped or unsafe semantics | Type/collation metadata |
| Older remote server version | Function/operator does not exist | Remote SQL and server version |
| Non-shippable GROUP BY/aggregate expression | Local aggregate | Aggregate/Foreign Scan nodes |
| Unsupported grouping construct | Local aggregation | EXPLAIN VERBOSE |
| Query shape contains local expressions | Part of query runs locally | Remote SQL |
| Stale statistics | Suboptimal plan chosen | ANALYZE/remote EXPLAIN |

### 17.1. Not Every Local Filter Is a Bug

An expression may require local evaluation to preserve semantics. The goal is to reduce data transfer while staying accurate, not to ship everything at all costs.

### 17.2. Inspect Each Expression Individually

Break complex queries down into:
- Built-in predicates.
- User-defined functions.
- Collation-sensitive conditions.
- Local-table joins.
- Aggregate expressions.

Run EXPLAIN VERBOSE after each change to isolate which expression affects pushdown.

---

## 18. Optimizing Predicates to Reduce Data Transfer

### 18.1. Filter Early Using Shippable Conditions

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

These are built-in conditions that are readily shipped when schemas are compatible.

### 18.2. Avoid Wrapping Remote Columns in Local-Only Functions

~~~sql
SELECT order_id
FROM remote_sales.orders
WHERE public.local_normalize(status) = 'paid';
~~~

If the function is not shippable, the remote server may have to return many rows for local evaluation.

If the logic can be safely expressed with a built-in expression or an extension configured as shippable, re-check the plan. Do not alter logic if behavior differs.

### 18.3. Use Ranges Instead of Column Functions When Semantics Allow

Instead of:

~~~sql
WHERE date_trunc('day', created_at) = TIMESTAMP '2026-11-14 00:00:00'
~~~

You can write:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
~~~

Range predicates are usually index-friendly on created_at and avoid per-row function evaluation. Handle timezones accurately according to the timestamp type and business rules.

### 18.4. Avoid Unnecessary Casts on Remote Columns

~~~sql
WHERE customer_id::text = '42'
~~~

A cast can prevent index usage or change shippability. Use a literal of the matching type:

~~~sql
WHERE customer_id = 42
~~~

### 18.5. Do Not Move Predicates Locally Just for Convenience

Every query rewrite must preserve NULL semantics, timezone, collation, and type coercion.

---

## 19. Optimizing JOIN Pushdown

### 19.1. Keep Remote Tables on the Same Foreign Server

If two tables live in the same remote PostgreSQL database, define them through the same foreign server object so the planner can consider join pushdown.

### 19.2. Keep User Mappings Consistent

If one table uses mapping A and another uses mapping B, postgres_fdw cannot treat them as the same remote identity for standard join pushdown.

### 19.3. Verify Remote Indexes

The remote server needs appropriate indexes on:
- Join keys.
- Filter predicates.
- Sort keys.
- Grouping keys if applicable.

### 19.4. Select Only Necessary Columns

Do not pull large unused columns into SELECT or JOIN. This reduces network payload if the join still must execute locally.

### 19.5. Avoid Local Expressions in Join Keys When Possible

If a JOIN key uses a local-only function or incompatible cast, the join may not be shipped. Standardize data types and schemas remotely whenever possible.

### 19.6. Do Not Force Every Join to the Remote Server

The remote server may become overloaded, or the local server may already have a smaller dataset. Compare costs and resources before optimizing.

### 19.7. Remote Views

A remote view can encapsulate JOIN logic on the remote side. A foreign table can point to the view via schema/table mapping. This is useful when the logic belongs to the remote data owner, though view versions and dependencies must be managed.

---

## 20. Optimizing Aggregate Pushdown

### 20.1. Aggregate Remotely When Data Shares the Same Source

If all data required for GROUP BY lives on the same remote server, write the query so the FDW can ship both grouping and aggregate expressions.

### 20.2. Reduce Group Cardinality

Aggregate pushdown helps most when input rows are large and group counts are small. For example, revenue by month/region usually reduces data volume dramatically.

### 20.3. Check Aggregate Functions

Prefer built-in aggregates first. For custom aggregates, confirm that the remote server has the identical definition and that the FDW version treats them as shippable.

### 20.4. Grouping Expressions

Prefer built-in expressions and compatible types. A local-only function in GROUP BY can force local aggregation.

### 20.5. HAVING

If HAVING is shippable, the remote server discards unwanted groups before returning rows. If HAVING contains local-only expressions, local processing may be needed.

### 20.6. Window Functions

Window functions are a distinct class of operations from ordinary aggregates. Do not assume that aggregate pushdown implies window operations are also pushed down. Check the specific plan.

### 20.7. Grouping Sets

ROLLUP, CUBE, and GROUPING SETS must be checked for support in your PostgreSQL/FDW version. If not shipped, consider a remote view/materialized view or accept local aggregation over pre-filtered input rows.

### 20.8. Remote Materialized Aggregates

For recurring reports, a remote materialized view or summary table can be more efficient than recomputing aggregates each time. Plan the refresh schedule, freshness SLA, and access permissions.

---

## 21. Combining Remote and Local Data

Not every query can run entirely on the remote server. Some workloads must split the pipeline.

### 21.1. Remote Filter Followed by Local Join

~~~sql
SELECT
    o.order_id,
    d.region_name
FROM (
    SELECT order_id, region_id
    FROM remote_sales.orders
    WHERE created_at >= DATE '2026-01-01'
      AND status = 'paid'
) AS o
JOIN public.region_dimension AS d
    ON d.region_id = o.region_id;
~~~

The remote server can filter orders first. The local server receives only order_id and region_id and joins them with the local dimension table.

### 21.2. Remote Join Followed by Local Enrichment

If a remote join between orders and customers is pushed down, the local server may only need to enrich the result with a local currency mapping or reporting configuration table.

### 21.3. Local Aggregate After Remote Filtering

When an aggregate expression cannot be shipped, you should still push down safe predicates to shrink input rows for the local aggregate.

### 21.4. Materialize Results Locally

If remote data is queried repeatedly and a freshness window is acceptable, you can copy it into a local staging table or materialized view. This trades query-time network traffic for batch synchronization and local storage.

### 21.5. Evaluate Consistency

Materializing data introduces lag relative to the remote source. Document refresh timestamps, watermarks, and report semantics clearly.

---

## 22. Transaction and Snapshot Semantics

Pushdown affects how data is read across multiple statements within the same local transaction.

### 22.1. Remote Transactions

When a local query accesses a foreign table, postgres_fdw opens a corresponding remote transaction for the local transaction if one is not already open.

### 22.2. Isolation Level

The remote transaction uses SERIALIZABLE when the local transaction is SERIALIZABLE; otherwise, it uses REPEATABLE READ as documented.

### 22.3. Snapshot Consistency

This ensures that multiple scans on the remote server within the same local transaction observe a consistent snapshot of data.

### 22.4. READ COMMITTED Surprise

Under local READ COMMITTED, users may expect each statement to see a fresh snapshot. However, the corresponding remote transaction can retain its REPEATABLE READ snapshot across the local transaction, so successive queries may continue seeing the same remote data snapshot.

### 22.5. Savepoints

postgres_fdw manages remote savepoints corresponding to local subtransactions.

### 22.6. Two-Phase Commit

postgres_fdw does not currently support preparing remote transactions for two-phase commit. Do not treat a transaction writing both locally and remotely as a distributed atomic transaction guaranteed by 2PC.

### 22.7. Long Transactions

Long-running local transactions hold open remote transactions, connections, and snapshots. Keep transactions short, avoid idle-in-transaction states, and monitor remote connections.

---

## 23. Security and Access Control with Pushdown

### 23.1. Remote Identity

Remote queries execute using the identity configured in the user mapping. Remote role privileges determine which tables and views can be read.

### 23.2. Row-Level Security

If remote tables enforce RLS, the remote user mapping and remote policies govern which rows are returned. The local role does not automatically replace the remote identity.

### 23.3. Least Privilege

Create a remote role with SELECT privileges only on the required schemas and tables. Never use a remote superuser for reporting FDWs.

### 23.4. User Mappings

User mappings may contain credentials. Restrict who can view or modify mappings, and never expose raw options in logs or tickets.

### 23.5. Public User Mappings

A PUBLIC user mapping can grant connection access to many local roles. Use it only intentionally and when remote privileges are strictly scoped.

### 23.6. TLS

Protect local-to-remote connections with TLS according to policy. Pushdown reduces bytes transferred, but it does not replace transport encryption.

### 23.7. EXPLAIN VERBOSE

Remote SQL exposes query structure, table names, and literals. Avoid embedding sensitive data or secrets in SQL literals. Restrict sharing plans outside authorized teams.

### 23.8. Remote search_path

postgres_fdw sets remote search_path to pg_catalog only for sessions it opens. Functions, triggers, or rules executing remotely must schema-qualify object names or specify an appropriate search_path in the function definition.

### 23.9. Function Side Effects

Only ship functions with appropriate behavior that are verified immutable. Never use the extension allowlist to run functions with side effects or reliance on remote state.

---

## 24. Monitoring Queries on Both Sides

Tuning pushdown requires observability on both local and remote servers.

### 24.1. Local pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE query ILIKE '%remote_sales%'
ORDER BY query_start;
~~~

The local query text typically shows the SQL submitted by the client. It does not necessarily contain the full deparsed remote SQL.

### 24.2. Remote pg_stat_activity

On the remote server, look for connections from the local host or matching application_name:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 500) AS remote_query
FROM pg_catalog.pg_stat_activity
WHERE application_name LIKE '%postgres_fdw%'
ORDER BY query_start;
~~~

The application_name value can be customized; adjust the filter for your environment.

### 24.3. postgres_fdw.application_name

You can configure application_name to identify remote sessions in pg_stat_activity and logs. Choose a meaningful name such as reporting_fdw or analytics_gateway.

### 24.4. Remote Logs

Enable logging according to policy to inspect remote SQL, durations, and errors. Avoid logging sensitive parameters or secrets.

### 24.5. Wait Events

A local Foreign Scan may wait on network or remote responses. A remote backend may wait on I/O, locks, or CPU. Identify which server is the bottleneck.

### 24.6. Connection Reuse

By default, postgres_fdw caches remote connections for reuse within a local session. Many concurrent local sessions can open many remote backends; monitor remote connection capacity.

---

## 25. Reading Pushdown Signals in Execution Plans

| Plan observation | Interpretation |
| --- | --- |
| Remote SQL contains WHERE | Predicate was shipped |
| Remote SQL selects only a few columns | Projection was shipped |
| Remote SQL contains JOIN | Join was shipped |
| Remote SQL contains GROUP BY/aggregates | Aggregate was shipped |
| Foreign Scan has local Filter | A predicate still runs locally |
| Hash Join above Foreign Scan | Local join occurs |
| HashAggregate above Foreign Scan | Local aggregation |
| Sort above Foreign Scan | Local sort |
| Multiple Foreign Scan nodes | May issue multiple remote scans/queries |
| Actual rows much higher than estimated | Statistics or cost estimates may be stale |
| Remote query slow while local CPU is low | Bottleneck is on remote server or network |
| Remote returns many rows then local filters | Predicate pushdown is ineffective |

### 25.1. Remote SQL Is Direct Evidence

Do not look solely at the Foreign Scan node. Read Remote SQL to see the actual SELECT list, WHERE, JOIN, GROUP BY, ORDER BY, and LIMIT sent.

### 25.2. Local Nodes Can Still Appear After Pushdown

Part of a query may run remotely while the remainder runs locally. That does not automatically indicate a bad plan.

### 25.3. Actual Rows Matter

If estimates are far off, the planner may select an inappropriate join order or pushdown decision. Compare estimated rows against actual rows.

### 25.4. Inspect the Remote Plan Separately

Copy the Remote SQL and run EXPLAIN on the remote server to verify index scans, join algorithms, aggregation strategies, sorts, and buffers.

---

## 26. Tuning Remote Estimates and Statistics

### 26.1. Enable Remote Estimates

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD use_remote_estimate 'true');
~~~

This allows postgres_fdw to query the remote server for estimates. Weigh planning overhead against remote load.

### 26.2. Analyze the Foreign Table Locally

~~~sql
ANALYZE remote_sales.orders;
~~~

Local statistics are useful when use_remote_estimate=false.

### 26.3. Frequently Changing Foreign Tables

Schedule ANALYZE based on change rate and planner sensitivity. Stale statistics produce inaccurate cardinality estimates.

### 26.4. Remote Table Statistics

The remote server also needs regular ANALYZE/autoanalyze. The remote planner relies on its own statistics to choose index, join, and aggregate plans.

### 26.5. Two Layers of Statistics

- Local statistics: help the local planner estimate Foreign Scan costs.
- Remote statistics: help the remote planner optimize Remote SQL.

Improving one layer does not automatically fix the other.

### 26.6. Inspecting pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals
FROM pg_catalog.pg_stats
WHERE schemaname = 'remote_sales'
  AND tablename = 'orders';
~~~

These are local statistics for the foreign table if collected; they are not the remote table's direct catalog stats.

### 26.7. ANALYZE Sampling

Some PostgreSQL versions support the analyze_sampling option to choose remote or local sampling. Consult the documentation for your specific version before configuring it.

---

## 27. Performance-Related postgres_fdw Options

| Option | Scope | Impact |
| --- | --- | --- |
| use_remote_estimate | Server/table | Requests remote EXPLAIN for cost/row estimates |
| fdw_startup_cost | Server | Startup overhead of Foreign Scan |
| fdw_tuple_cost | Server | Per-tuple transfer overhead |
| extensions | Server | Allowlist of extensions with shippable immutable functions/operators |
| fetch_size | Server/table | Number of rows retrieved per fetch |
| async_capable | Server/table per version | Enables async execution in Append plans |
| keep_connections | Server | Keeps or closes remote connections after transactions |
| application_name | Server/config | Identifies remote sessions |
| batch_size | Server/table | Number of rows per insert batch, not read fetch size |

### 27.1. Tune Options Only with a Hypothesis

For example:
- High network latency and small fetch_size: test increasing fetch_size.
- Inaccurate local estimates: test ANALYZE or use_remote_estimate.
- Remote queries unidentifiable: set application_name.
- Multiple Append scans: evaluate async_capable.

### 27.2. batch_size Does Not Help SELECT Pushdown

batch_size primarily applies to inserts and COPY into foreign tables. Do not use it to optimize SELECT queries returning many rows.

### 27.3. Keep Connections

Keeping connections open reduces connection setup overhead. On the other hand, the remote server must maintain more idle connections. Evaluate pool and connection limits alongside lifecycle policies.

---

## 28. Cross-Version Compatibility

Local and remote servers do not necessarily run the same major version.

### 28.1. Remote Missing a Built-in Function

A newer built-in function on the local server may be considered shippable, while an older remote server does not yet have it. Remote SQL will fail.

### 28.2. Verify Function Availability

Before shipping expressions containing newer functions, verify that the function exists and has equivalent semantics on the remote server.

### 28.3. Optimization Fence Workaround

In documented cases, you can wrap a foreign table in a subquery with OFFSET 0 to prevent an incompatible or newer expression inside/above it from being pushed down, forcing local evaluation:

~~~sql
SELECT
    public.local_only_function(remote_rows.status)
FROM (
    SELECT status
    FROM remote_sales.orders
    OFFSET 0
) AS remote_rows;
~~~

This is a planner-control technique, not a default optimization. It can alter the plan and cost. Always verify with EXPLAIN VERBOSE.

### 28.4. Remote Extension Versions

When using the extensions option, local and remote extension versions must be compatible, and functions/operators must behave identically.

### 28.5. Data Type Differences

Newer data types or differing casts can cause Remote SQL to fail or convert values differently. Maintain a schema compatibility matrix for long-lived integrations.

---

## 29. Alternatives When Pushdown Is Not Feasible

### 29.1. Accept Local Processing

If the input dataset is small, a local join or aggregate may be fast and simple enough.

### 29.2. Create a Remote View

Place the JOIN/aggregate logic on the remote server and point a foreign table to that view. This works well when the logic belongs alongside the source data.

### 29.3. Remote Materialized View

Use when heavy aggregates are queried repeatedly and a refresh lag is acceptable.

### 29.4. Materialize Locally

Copy a bounded dataset into a local staging table or materialized view if multiple local queries reuse it. Monitor freshness and incremental refreshes.

### 29.5. Synchronize Data Instead of Live Querying

If an application runs continuous reports over large remote datasets, ETL/CDC into an analytics store may be more appropriate than query-time FDW access.

### 29.6. Choose the Right Architecture

FDW is well-suited for query federation and remote data access. It is not always the best fit for high-volume analytical workloads or joins across many high-latency sources.

---

## 30. Measuring Pushdown Effectiveness

Do not judge solely by whether Remote SQL looks short or long.

### 30.1. Key Metrics to Measure

- End-to-end query latency.
- Remote execution time.
- Local execution time.
- Rows returned from remote.
- Bytes transferred over the network.
- Number of fetch round trips.
- Remote CPU/I/O.
- Local CPU/memory.
- Planning time.
- Connection count.
- Concurrent query impact.

### 30.2. Compare Two Plans

Establish a non-pushdown baseline or equivalent query, then compare against the pushdown plan. Ensure identical results and the same data snapshot.

### 30.3. Measure Selective Predicates

A predicate retaining 0.1% of rows offers major network savings. A predicate retaining 95% of rows may provide much smaller gains.

### 30.4. Measure Aggregate Reduction

Compare remote input rows against the number of returned groups. If group count is close to input row count, aggregate pushdown does not significantly reduce data transfer.

### 30.5. Remote Server Load

Pushdown shifts CPU work to the remote server. If the remote server is already busy serving its primary workload, local queries could cause remote service degradation.

### 30.6. Concurrency

Benchmarking a single query may look great yet fail to reflect concurrent sessions. Test under near-production concurrency.

### 30.7. Cache Effects

Repeated runs can warm caches. Record warm/cold cache states clearly and avoid comparing test runs conducted under different conditions.

---

## 31. End-to-End Example: Predicate Pushdown

Assume remote orders has tens of millions of rows and an index on created_at/status.

### 31.1. Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    order_id,
    customer_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01';
~~~

### 31.2. What to Look For

Remote SQL should contain both the status and created_at predicates. If only SELECT columns appear without WHERE, the local plan may be filtering after fetching rows.

### 31.3. Inspect the Remote Index

On the remote server, run EXPLAIN on the equivalent Remote SQL. Check index scan, bitmap scan, or sequential scan and actual rows.

### 31.4. Test a Local-Only Expression

Add a user-defined function not in the shippable allowlist and compare Remote SQL. Observe the local Filter node.

### 31.5. Conclusion

Predicate pushdown is valuable when the remote server can filter near the source and return substantially fewer rows.

---

## 32. End-to-End Example: Join Pushdown

### 32.1. Two Foreign Tables on the Same Server

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

### 32.2. Inspect Remote SQL

Check for JOIN and WHERE inside Remote SQL. If present, the remote server is executing that join and filter.

### 32.3. Adding a Local Table

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    d.region_name
FROM remote_sales.orders AS o
JOIN public.region_dimension AS d
    ON d.region_id = o.region_id
WHERE o.status = 'paid';
~~~

Observe the Foreign Scan and local Join node. The remote filter can still be shipped while the local join cannot be shipped.

### 32.4. Testing a Different Mapping

Create a separate foreign server/table mapping to demonstrate how join pushdown is restricted when references use different user mappings. Never use production credentials in a lab.

### 32.5. Conclusion

Sharing the same server and mapping enables JOIN pushdown eligibility; the planner still decides based on cost and shippability.

---

## 33. End-to-End Example: Aggregate Pushdown

### 33.1. Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY status
HAVING count(*) > 100
ORDER BY status;
~~~

### 33.2. What to Look For

Remote SQL should contain WHERE, GROUP BY, and the aggregate calls if all expressions are shippable.

### 33.3. Test a Non-Shippable Expression

Add a local-only function to a grouping expression or HAVING. Observe whether the aggregate stays remote, splits partially, or runs locally.

### 33.4. Test Grouping Sets

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY ROLLUP(status);
~~~

Check the actual plan; grouping sets should not be assumed pushable across all versions.

### 33.5. Measure Row Counts

Compare remote input cardinality against returned group rows. Evaluate network savings.

### 33.6. Conclusion

Aggregate pushdown drastically reduces data when group counts are small, but shippability of the aggregates and all grouping expressions must be verified.

---

## 34. Runbook: Predicate Not Pushed Down

### Step 1: Capture the Plan

Run EXPLAIN VERBOSE and save the Remote SQL.

### Step 2: Identify the Local Filter

Look for a Filter node above Foreign Scan and expressions missing from Remote SQL.

### Step 3: Classify the Expression

Check:
- Built-in vs. user-defined function/operator.
- Volatility.
- Extension membership.
- Type/collation.
- Remote version compatibility.

### Step 4: Check the Extension Option

If the expression belongs to an extension, verify the extension exists on both servers, versions are compatible, and it is declared in the extensions option.

### Step 5: Verify Semantics

Confirm that the function/operator truly behaves identically. Do not declare an extension shippable just to eliminate a local Filter.

### Step 6: Rewrite Safely If Appropriate

Use built-in predicates or range conditions when equivalent. Verify NULL/timezone/collation semantics.

### Step 7: Re-run EXPLAIN

Confirm the predicate appears in Remote SQL and query results remain unchanged.

---

## 35. Runbook: JOIN Not Pushed Down

### Step 1: Inspect Foreign Scan Nodes

Identify which foreign server each table is accessed through.

### Step 2: Check User Mappings

Verify whether the table references use the same remote identity.

### Step 3: Check for Local Relations

If the query joins with a local table, that join must run locally.

### Step 4: Check Join Expressions

Inspect types, casts, collations, functions, and operators in the join condition.

### Step 5: Check Costs

The planner may fetch tables separately if estimates indicate it is cheaper. Compare row counts/costs and remote indexes.

### Step 6: Inspect Remote SQL

If Remote SQL contains both remote tables and the JOIN, pushdown occurred. Otherwise, locate the local join node.

### Step 7: Adjust Schema/Query Carefully

Standardize types/collations or use a remote view if appropriate. Re-test results and performance.

---

## 36. Runbook: Aggregate Unexpectedly Running Locally

### Step 1: Inspect the Aggregate Node

Check whether HashAggregate/GroupAggregate sits above Foreign Scan.

### Step 2: Read Remote SQL

Verify whether GROUP BY and aggregate calls appear.

### Step 3: Check Shippability

Inspect the aggregate function, input expressions, GROUP BY expressions, and HAVING.

### Step 4: Check Query Shape

Look for local joins, grouping sets, window functions, subqueries, or expressions that prevent aggregate pushdown.

### Step 5: Verify Remote Compatibility

Ensure the remote server has matching functions/types/operators and compatible semantics.

### Step 6: Optimize Whatever Can Be Shipped

Push shippable predicates down before aggregation to reduce input rows if the aggregate cannot be pushed entirely.

### Step 7: Consider Remote Views/Materialization

If an aggregate query is critical and runs frequently, a remote view or materialized view may be a cleaner solution.

---

## 37. Lab 1: Installing postgres_fdw and Creating Foreign Tables

Use two PostgreSQL instances in development/staging. One acts as local, the other as remote.

### 37.1. Create Data on the Remote Server

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE sales.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
);

CREATE INDEX orders_status_created_idx
    ON sales.orders(status, created_at);

CREATE INDEX orders_customer_idx
    ON sales.orders(customer_id);
~~~

### 37.2. Load Sample Data

~~~sql
INSERT INTO sales.customers
SELECT
    g,
    'Customer ' || g,
    CASE WHEN g % 3 = 0 THEN 'north'
         WHEN g % 3 = 1 THEN 'central'
         ELSE 'south'
    END
FROM generate_series(1, 1000) AS g;

INSERT INTO sales.orders
SELECT
    g,
    ((g - 1) % 1000) + 1,
    CASE WHEN g % 4 = 0 THEN 'paid'
         WHEN g % 4 = 1 THEN 'pending'
         ELSE 'shipped'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 300) * INTERVAL '1 day',
    (g % 10000) / 10.0
FROM generate_series(1, 500000) AS g;
~~~

### 37.3. Install postgres_fdw Locally

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

### 37.4. Create Server and Mapping

~~~sql
CREATE SERVER sales_lab
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'remote-host',
    port '5432',
    dbname 'remote_db'
);

CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_lab
OPTIONS (
    user 'sales_reader',
    password 'lab-only-secret'
);
~~~

Use dedicated credentials for the lab and never commit them to a repository.

### 37.5. Import Tables

~~~sql
CREATE SCHEMA remote_sales;

IMPORT FOREIGN SCHEMA sales
LIMIT TO (customers, orders)
FROM SERVER sales_lab
INTO remote_sales;
~~~

### 37.6. Verify

~~~sql
SELECT count(*) FROM remote_sales.orders;
SELECT count(*) FROM remote_sales.customers;
~~~

### 37.7. Conclusion

Foreign tables let you query remote data using local SQL. The next step is observing the queries sent to the remote server.

---

## 38. Lab 2: Observing Predicate Pushdown

### 38.1. Unfiltered Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, status, created_at
FROM remote_sales.orders;
~~~

Observe Remote SQL and the number of columns fetched.

### 38.2. Filtered Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-06-01 00:00:00+00';
~~~

### 38.3. Verify Remote SQL

Remote SQL should include both the status and created_at conditions if shipped.

### 38.4. Test a Built-in Function

Add lower/upper or another built-in text operation. Check whether the function appears in Remote SQL.

### 38.5. Test a User-Defined Function

Create a local function not included in the extension allowlist and use it in WHERE. Observe the local Filter and Remote SQL.

### 38.6. Conclusion

Predicate pushdown is confirmed via Remote SQL; a local Filter indicates expressions still evaluated locally.

---

## 39. Lab 3: Observing JOIN Pushdown

### 39.1. JOIN Two Foreign Tables

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

### 39.2. Inspect Remote SQL

Check whether the remote SQL includes a JOIN between sales.orders and sales.customers.

### 39.3. JOIN with a Local Table

Create a local table:

~~~sql
CREATE TABLE public.region_bonus (
    region TEXT PRIMARY KEY,
    bonus_rate NUMERIC(5,4) NOT NULL
);
~~~

Run a query joining the foreign tables with region_bonus. Observe the local join node and Remote SQL.

### 39.4. Test Different Mappings

In the lab environment, create a different mapping for one foreign table/server reference and observe the impact on join pushdown.

### 39.5. Read Actual Rows

Run EXPLAIN ANALYZE on the lab dataset. Compare rows returned by the remote server against pre-JOIN row counts.

### 39.6. Conclusion

JOIN pushdown depends on sharing the same foreign server, user mapping, shippability, and cost decisions.

---

## 40. Lab 4: Aggregate Pushdown

### 40.1. Simple GROUP BY

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY status;
~~~

### 40.2. Inspect Remote SQL

Look for GROUP BY, count, and sum inside Remote SQL.

### 40.3. Add HAVING

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count
FROM remote_sales.orders
GROUP BY status
HAVING count(*) > 100;
~~~

Check whether HAVING is shipped.

### 40.4. Test a Grouping Expression

Add date_trunc or a built-in expression to GROUP BY. Confirm the expression is supported remotely.

### 40.5. Test Grouping Sets

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY ROLLUP(status);
~~~

Observe whether the aggregate remains local or is shipped.

### 40.6. Compare Row Counts

Use remote counts/EXPLAIN and local result cardinality to estimate data reduction.

### 40.7. Conclusion

Aggregate pushdown can reduce hundreds of thousands of rows to a handful of groups, depending on expressions and query shape.

---

## 41. Lab 5: Cost Estimates and fetch_size

### 41.1. Enable Remote Estimates

~~~sql
ALTER SERVER sales_lab
OPTIONS (ADD use_remote_estimate 'true');
~~~

### 41.2. Run EXPLAIN

Re-run filter/join/aggregate queries and observe estimated rows and costs. Planning may trigger remote EXPLAIN requests.

### 41.3. Disable Remote Estimates and Run ANALYZE

~~~sql
ALTER SERVER sales_lab
OPTIONS (SET use_remote_estimate 'false');

ANALYZE remote_sales.orders;
ANALYZE remote_sales.customers;
~~~

### 41.4. Compare Estimates

Compare plans before and after ANALYZE. When remote tables change, re-run ANALYZE as needed.

### 41.5. Test fetch_size

~~~sql
ALTER SERVER sales_lab
OPTIONS (ADD fetch_size '1000');
~~~

Run a query returning many rows and measure duration and memory. Then test other suitable values.

### 41.6. Distinguish fetch_size from Pushdown

Changing fetch_size does not make WHERE/JOIN/aggregates appear in Remote SQL. It only changes how rows already selected by the remote query are fetched.

### 41.7. Conclusion

Cost estimates influence plan selection; fetch_size influences transfer batching. These two mechanisms address two distinct aspects of performance.

---

## 42. Practice Exercises

### Exercise 1 — Concepts

Define query pushdown and distinguish it from copying data locally.

### Exercise 2 — Pushdown Layers

Explain projection, predicate, join, aggregate, sort, and limit pushdown.

### Exercise 3 — FDW Architecture

Describe extensions, foreign servers, user mappings, and foreign tables.

### Exercise 4 — Setup

Write SQL to install postgres_fdw, create a server, create a mapping, and import a foreign schema.

### Exercise 5 — Projection

Write a query selecting only three columns from a foreign table and explain the benefits over SELECT *.

### Exercise 6 — Predicate

Write a query filtering orders by status and a date range. State what Remote SQL should contain.

### Exercise 7 — Shippability

Explain why postgres_fdw defaults to shipping only built-in operators/functions in WHERE.

### Exercise 8 — IMMUTABLE

Distinguish IMMUTABLE, STABLE, and VOLATILE. Why does volatility affect pushdown?

### Exercise 9 — User-Defined Functions

A function is declared IMMUTABLE but is not in the built-in set. What is required for postgres_fdw to ship it?

### Exercise 10 — Extensions Option

Explain the extensions option and the operator's responsibility when marking an extension shippable.

### Exercise 11 — Type Compatibility

A remote numeric column is declared locally as text. What issues can arise?

### Exercise 12 — Collation

Why can differing local/remote collations cause predicates or ORDER BY to return different results?

### Exercise 13 — Join Pushdown

Write a JOIN between remote orders and customers sharing the same foreign server and user mapping.

### Exercise 14 — Different Servers

Two foreign tables belong to two different foreign servers. Why can't postgres_fdw send a single standard JOIN to one server?

### Exercise 15 — Different Mappings

Explain how different user mappings impact JOIN pushdown.

### Exercise 16 — Local Join

Write a query joining foreign orders with a local dimension table. Which parts can be shipped and which must run locally?

### Exercise 17 — Outer Join Semantics

Explain why moving a predicate from ON to WHERE can change LEFT JOIN results.

### Exercise 18 — Aggregate Pushdown

Write a query with GROUP BY status, COUNT, and SUM; state the requirements for the aggregate to be shipped.

### Exercise 19 — HAVING

Distinguish WHERE and HAVING. When can HAVING be pushed remotely?

### Exercise 20 — Aggregate FILTER

Write a COUNT(*) FILTER query and identify which expressions must be shippable.

### Exercise 21 — DISTINCT Aggregate

Distinguish COUNT(DISTINCT x) from SELECT DISTINCT. Why must you check the plan instead of generalizing?

### Exercise 22 — Grouping Sets

Test ROLLUP/CUBE/GROUPING SETS on your target version and explain the plan when pushdown does not happen.

### Exercise 23 — Window Functions

Distinguish ordinary aggregate pushdown from window-function execution.

### Exercise 24 — ORDER BY/LIMIT

Write a top-100 orders query and verify whether Remote SQL contains ORDER BY/LIMIT.

### Exercise 25 — EXPLAIN VERBOSE

Explain Remote SQL, local Filter, Hash Join, and HashAggregate in a Foreign Scan plan.

### Exercise 26 — EXPLAIN ANALYZE

State the risks of running EXPLAIN ANALYZE on a large remote query and how to collect remote metrics.

### Exercise 27 — use_remote_estimate

Explain this option and the tradeoff between remote planning round trips and local estimates.

### Exercise 28 — ANALYZE Foreign Table

Write the command to update local statistics for a foreign table and explain when it needs to be re-run.

### Exercise 29 — fdw_startup_cost/fdw_tuple_cost

Explain both options and why you should not change them solely to force the planner to choose pushdown.

### Exercise 30 — fetch_size

Explain fetch_size, its default behavior, and the impact of setting it too small or too large.

### Exercise 31 — batch_size

Distinguish batch_size from fetch_size and explain why batch_size does not optimize SELECT.

### Exercise 32 — async_capable

Describe async execution in Append and why enabling the option does not guarantee parallel execution.

### Exercise 33 — Cross-Version

A remote server lacks a newer built-in function that the local planner considers shippable. Describe the error and remediation options.

### Exercise 34 — Remote RLS

A remote table has row-level security. Which user mapping determines returned rows, and what must be verified?

### Exercise 35 — Snapshot

Explain remote REPEATABLE READ behavior inside a local READ COMMITTED transaction and its impact on successive queries.

### Exercise 36 — Two-Phase Commit

Why shouldn't you assume postgres_fdw provides distributed 2PC for local and remote writes?

### Exercise 37 — Remote Monitoring

Write a query to find postgres_fdw sessions on the remote server and list key metrics to observe.

### Exercise 38 — Predicate Troubleshooting

A function in WHERE still runs locally. Design a diagnostic sequence checking volatility, extension allowlist, type/collation, and Remote SQL.

### Exercise 39 — Join Troubleshooting

A JOIN between two foreign tables is not pushed down. List possible causes and how to verify each.

### Exercise 40 — End-to-End Tuning

A report must join two remote tables, filter by month, group by region, and join with a local currency table. Set up the foreign server/mapping, write the query, verify each pushdown stage, tune statistics/fetch_size, measure network and remote CPU, and propose alternatives if the aggregate or JOIN cannot be shipped.

---

## 43. Pushdown Deployment Checklist

| Item | What to Verify |
| --- | --- |
| FDW | Correct wrapper and version |
| Remote endpoint | Correct host/port/database |
| User mapping | Remote identity and least privilege |
| Foreign tables | Column names/types match remote |
| Collations | Local/remote semantics compatible |
| Projection | Fetch only needed columns |
| Predicate | WHERE appears in Remote SQL |
| Function volatility | Shipped expressions satisfy IMMUTABLE |
| Extension allowlist | Only compatible extensions in extensions option |
| JOIN server | Tables share the same foreign server |
| JOIN mapping | References use the same user mapping |
| JOIN expressions | Types/operators/functions are shippable |
| Aggregate | Aggregate functions and grouping expressions are shippable |
| HAVING | Conditions are shippable |
| Grouping sets | Verify version/FDW support |
| ORDER BY/LIMIT | Remote SQL includes expected sort/limit |
| Cost estimates | Appropriate use_remote_estimate or local stats |
| Local statistics | Foreign tables ANALYZEd as needed |
| Remote statistics | Remote tables ANALYZEd/autoanalyzed |
| fetch_size | Benchmarked for row width/concurrency |
| batch_size | Tuned only for write/COPY workloads |
| Async | Plan actually uses async-capable Append |
| Remote indexes | Indexes match predicates/joins/sorts |
| Remote load | CPU/I/O/connections not overloaded |
| Network | Rows/bytes/round trips measured |
| EXPLAIN | Remote SQL and local nodes recorded |
| EXPLAIN ANALYZE | Run only when impact is understood |
| Remote monitoring | pg_stat_activity/logs/query stats |
| Security | TLS, grants, RLS, and secret handling |
| Transaction | Snapshot/remote transaction behavior understood |
| Compatibility | Remote server/extensions have compatible versions |
| Correctness | Pre/post-rewrite results verified |
| Operations | Error runbook and owner defined |

## Conclusion

Pushing down predicates, JOINs, and aggregates to a remote server helps PostgreSQL reduce network data transfer and leverage processing right where the data resides. With postgres_fdw, predicate pushdown relies on built-in or allowlisted extension objects, and functions/operators must satisfy shippability and IMMUTABLE requirements. JOIN pushdown requires foreign tables to share the same foreign server and user mapping, while aggregate pushdown depends on aggregate functions, grouping expressions, and query shapes supported by the FDW.

Key principles to remember:

1. **Pushdown is decided by the FDW and planner.** Do not infer it from SQL syntax.
2. **Only shippable WHERE clauses are sent remotely.** Built-in objects are the default; extension functions must be declared and verified.
3. **IMMUTABLE is a strict requirement.** Never misdeclare volatility just to force pushdown.
4. **JOIN pushdown has server and identity boundaries.** Sharing the same foreign server and user mapping is essential.
5. **Aggregate pushdown must be verified.** Inspect aggregates, GROUP BY, HAVING, and expressions in Remote SQL.
6. **EXPLAIN VERBOSE is direct proof.** Read Remote SQL alongside local Filter/Join/Aggregate nodes.
7. **Statistics drive plan choices.** Remote estimates and local ANALYZE address two different estimation layers.
8. **fetch_size does not enable pushdown.** It only adjusts how already-selected rows are fetched.
9. **Data types and collations must be compatible.** Mismatches can cause errors or alter semantics.
10. **Pushdown shifts work to the remote server.** Measure remote CPU/I/O and network, not just local query time.
11. **Transaction semantics still matter.** postgres_fdw coordinates remote transactions/snapshots with the local transaction but does not provide 2PC.
12. **Not every query needs full pushdown.** Combining remote filtering with local joins/aggregates can be a sound plan.
13. **Security follows the remote identity.** User mappings, RLS, TLS, and secret handling must be controlled.
14. **Optimization must preserve correctness.** Always compare output, plans, and workload metrics before and after changes.

A solid tuning workflow starts with EXPLAIN VERBOSE, identifies which rows and expressions still execute locally, checks shippability and user mappings, and then measures impact on both servers. The goal is to minimize data transfer and total end-to-end cost while preserving semantics, access controls, and data consistency.

## References

- [PostgreSQL 18 — postgres_fdw](https://www.postgresql.org/docs/18/postgres-fdw.html)
- [PostgreSQL 18 — EXPLAIN](https://www.postgresql.org/docs/18/sql-explain.html)
- [PostgreSQL 18 — Foreign Data Wrappers](https://www.postgresql.org/docs/18/ddl-foreign-data.html)
