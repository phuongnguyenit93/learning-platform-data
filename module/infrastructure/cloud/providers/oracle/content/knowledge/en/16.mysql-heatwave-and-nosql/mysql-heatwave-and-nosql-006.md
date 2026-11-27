# HeatWave Cluster and Analytical Query Processing

## 1. Objectives and Context

In the **MySQL HeatWave and NoSQL** chapter of the Oracle Cloud Infrastructure (OCI) learning path, this lesson presents how a HeatWave cluster accelerates analytical queries on MySQL data, from processing architecture to data loading, offload verification, and operations.

After this lesson, you will be able to:

- Distinguish a MySQL DB system, InnoDB, and a HeatWave cluster.
- Explain why scan, join, and aggregation queries can benefit from HeatWave.
- Prepare tables, load data, and confirm tables are ready for queries.
- Verify whether a query uses the `RAPID` secondary engine.
- Evaluate correctness, data freshness, performance, resources, and cost.
- Build a workflow to monitor and handle fallbacks or load failures.

The main examples use **InnoDB tables inside the DB system**. HeatWave also provides Lakehouse for processing data from Object Storage and other capabilities, but those load paths have separate prerequisites. Do not extrapolate InnoDB table update behavior to all Lakehouse sources.

Schema names, sample data, time targets, and hypothetical benchmark numbers in this lesson are for learning purposes only. Shapes, limits, features, and metadata must be checked against the service version in use.

## 2. Architecture: MySQL Receives SQL, HeatWave Accelerates Analytics

### 2.1. Core Components

| Component | Role |
| --- | --- |
| MySQL DB system | Provides the MySQL endpoint, authentication, SQL processing, and database operations |
| InnoDB | Primary storage engine for transactional tables in the examples |
| HeatWave cluster | Distributed analytical processing cluster storing data in an optimized format and executing offloaded queries |
| RAPID | Name of the secondary engine used to associate tables with the HeatWave processing path |
| Load and change propagation mechanism | Brings initial data and eligible changes from source tables into HeatWave |

A HeatWave cluster provides a distributed, scale-out, in-memory, hybrid-columnar query engine. It attaches to the MySQL DB system rather than replacing the application endpoint with individual analytics node endpoints. [HeatWave cluster overview](https://docs.oracle.com/en-us/iaas/mysql-database/doc/heatwave.html).

A single MySQL connection can still run queries on InnoDB or offload eligible queries to HeatWave. Therefore, merely seeing that the application connects to the DB system does not tell you which engine executed a specific query.

### 2.2. High-Level Processing Flow

~~~mermaid
flowchart LR
    APP["Java App / BI / MySQL client"]
    SQL["MySQL endpoint: auth, SQL, and optimizer"]
    INNO["InnoDB on DB system"]
    HW["HeatWave cluster: RAPID"]
    RES["Results returned to client"]

    APP --> SQL
    SQL -->|"Transactions and primary-path queries"| INNO
    INNO -->|"Initial load and change propagation"| HW
    SQL -->|"Eligible analytical queries"| HW
    INNO --> RES
    HW --> RES
~~~

The diagram depicts two execution paths; it does not mean clients arbitrarily write directly into HeatWave memory. Transactional operations on this dataset still go through the DB system's InnoDB tables.

### 2.3. Why Columnar Representation and Distributed Processing Help

A revenue report may need to read millions of rows while using only a few columns: date, product, quantity, and price. An analytics-oriented format processes only the needed columns, while cluster nodes share the work of scanning, joining, and aggregating.

HeatWave uses vectorized processing and distributes data across nodes. When executing a query, operators can process blocks of data rather than processing one record at a time in the same manner as a traditional execution path. [HeatWave architecture and query processing](https://dev.mysql.com/doc/heatwave/en/mys-hw-about-heatwave.html).

Actual gains depend on the data, query, node count, work balance, and communication overhead. Do not assume doubling nodes cuts every query's runtime exactly in half.

## 3. Choosing Suitable Workloads and Defining Evaluation Criteria

### 3.1. Candidates Worth Testing

- Reports reading many records, filtering by time, and running `GROUP BY`.
- Joins between large transactional tables and dimension/catalog tables.
- Aggregations of revenue, quantities, distributions, and trends.
- Ad hoc analytics reading far more data than a typical lookup query.
- Workloads where heavy reporting competes with transactions for resources.

A query fetching a single order by primary key may already be very fast on InnoDB. Distributed planning and execution overhead is not guaranteed to benefit such small access patterns.

### 3.2. Defining "Faster" in Service-Level Terms

Hypothetical requirement example:

~~~text
90-day revenue report:
- Results are accurate per order-status and discount rules.
- p95 does not exceed 5 seconds at 8 concurrent users.
- OLTP continues meeting its own targets during the same test window.
- After valid data changes, reports reflect updates according to
  the verified consistency mechanism and configuration.

Operations:
- Required tables are all ready in HeatWave.
- Visibility into when queries fall back to the DB system.
- Defined analytics service recovery time after restart.
~~~

These are project-defined criteria, not Oracle performance guarantees.

Do not measure query runtime alone. Measure load/recovery time, impact on the DB system, concurrency, errors, correctness, and total configuration cost.

### 3.3. Separating Three States

| State | Evidence Required |
| --- | --- |
| Cluster created and active | Resource status, node status, and work requests |
| Tables loaded and ready | Load status of every required table |
| Query actually uses HeatWave | `EXPLAIN`, controlled execution, and appropriate telemetry |

These three states are related but do not substitute for one another. An active cluster can still be missing a table; all tables loaded can still leave a query ineligible for offload.

## 4. Preparing OCI Resources, Connectivity, and Permissions

### 4.1. Initial Prerequisites

You need:

- A DB system with a HeatWave-supported shape and configuration.
- A HeatWave cluster created with appropriate resources.
- Network path to the DB system's MySQL endpoint.
- Compatible MySQL client or connector.
- A database identity with privileges to prepare/load within the assigned scope.
- OCI permissions to manage or observe the cluster per assigned role.

When adding a cluster in OCI, choose a service-supported shape and node count; you can use the node estimator. For HA DB systems, the cluster attaches to the primary instance per the service model. [Adding a HeatWave cluster](https://docs.oracle.com/en-us/iaas/mysql-database/doc/adding-heatwave-cluster.html).

Do not open application connections directly to internal HeatWave node networks. Use the MySQL endpoint and network design documented by the service.

### 4.2. Separation of Duties

| Identity | Responsibilities |
| --- | --- |
| OCI infrastructure admin | Create, resize, monitor work requests, and manage cluster costs |
| Data/load manager | Inspect schemas, execute DDL/loads, and troubleshoot load errors |
| Analytics user | `SELECT` on authorized data or views |
| Observer | Read required metrics and metadata within scope |

OCI IAM cloud resource governance and MySQL privileges are two separate layers. Never grant `ALTER`/DDL or server-wide admin privileges to reporting accounts just to make queries offload.

Automated routines and Performance Schema tables have their own privilege requirements. If runtime cannot read monitoring metadata, use an appropriate operational identity; do not promote runtime to administrator.

### 4.3. Recording Version and Configuration Before Hands-On Steps

In an authorized MySQL session:

~~~sql
SELECT VERSION();

SHOW VARIABLES LIKE 'autocommit';
SHOW VARIABLES LIKE 'use_secondary_engine';

SHOW GLOBAL STATUS LIKE 'rapid_cluster_status';
~~~

Record the DB system, version, shape/node count, and environment purpose. If a table or variable does not exist in the active version, check documentation for that exact version rather than assuming the cluster is broken.

The session-level changes to `autocommit` and engine settings in later sections must run in a **separate analytics session with no active business transaction open**.

## 5. Sample Dataset: Daily Revenue by Category

### 5.1. Data Model

Three tables:

- `product`: product catalog.
- `sales_order`: order date, region, and status.
- `order_item`: line-item quantity, unit price, and discount rate.

Problem: aggregate revenue for `PAID` orders by date and category. Exclude cancelled orders; each line contributes `quantity × unit_price × (1 - discount)`.

The dataset is tiny for easy reconciliation. It does not represent large-scale speedup potential and may not be auto-selected for offload by the optimizer under normal mode.

### 5.2. Creating the Schema and Tables

Execute using an appropriate deployment identity in a test environment, with an unused schema name:

~~~sql
CREATE DATABASE analytics_lab CHARACTER SET utf8mb4;

CREATE TABLE analytics_lab.product (
    product_id BIGINT NOT NULL,
    product_name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE TABLE analytics_lab.sales_order (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE analytics_lab.order_item (
    order_id BIGINT NOT NULL,
    line_no INT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    discount DECIMAL(5, 4) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, line_no)
) ENGINE = InnoDB;
~~~

Never run test schema creation or cleanup commands against a production schema. Using primary keys here also ensures unambiguous record identification for data operations and reconciliation.

### 5.3. Loading Data into InnoDB First

~~~sql
INSERT INTO analytics_lab.product
    (product_id, product_name, category)
VALUES
    (1, 'Keyboard', 'PERIPHERAL'),
    (2, 'Mouse', 'PERIPHERAL'),
    (3, 'Monitor', 'DISPLAY'),
    (4, 'Laptop', 'COMPUTER');

INSERT INTO analytics_lab.sales_order
    (order_id, order_date, region, status)
VALUES
    (1001, '2026-11-01', 'HCM', 'PAID'),
    (1002, '2026-11-01', 'HN', 'PAID'),
    (1003, '2026-11-02', 'HCM', 'CANCELLED'),
    (1004, '2026-11-02', 'DN', 'PAID');

INSERT INTO analytics_lab.order_item
    (order_id, line_no, product_id, quantity, unit_price, discount)
VALUES
    (1001, 1, 1, 2,   500000.00, 0.0000),
    (1001, 2, 2, 1,   200000.00, 0.0000),
    (1002, 1, 3, 1,  3000000.00, 0.1000),
    (1003, 1, 4, 1, 15000000.00, 0.0000),
    (1004, 1, 2, 3,   200000.00, 0.0000),
    (1004, 2, 3, 1,  3200000.00, 0.0000);
~~~

If your client uses explicit transactions, commit the sample data before moving to the load step. Do not toggle `autocommit` arbitrarily in the middle of another transaction.

At this point, the data is in InnoDB; you cannot yet claim corresponding data exists in HeatWave.

## 6. Loading Tables into HeatWave

### 6.1. Selecting Tables and Columns for Queries

Before loading:

1. List the queries requiring acceleration.
2. Identify all accessed tables and columns.
3. Check data types, SQL modes, and features against your version.
4. Estimate memory footprint and load duration.
5. Choose an execution window compatible with OLTP load.

A three-table join requires all three tables to be ready per query offload prerequisites. Never load only the large fact table and assume small dimension tables will automatically be read from InnoDB on the same execution path.

If a column is excluded from the secondary engine, any query touching that column must be re-evaluated. Decisions to shrink memory footprint must be paired with a query inventory.

### 6.2. Auto Parallel Load: Dryrun First

Run on the test schema:

~~~sql
CALL sys.heatwave_load(
    JSON_ARRAY('analytics_lab'),
    JSON_OBJECT('mode', 'dryrun')
);
~~~

Dryrun helps inspect errors/warnings, estimates, and generated load scripts; it does not load data into the cluster yet. Read the report—especially proposed schema/secondary-engine changes—before moving to a real load. [Auto Parallel Load](https://dev.mysql.com/doc/heatwave/en/mys-hw-auto-parallel-load.html).

Report table names and output details can vary across versions. Follow the guidance in the routine's output and your DB system's documentation; never copy an old `sys` table query and assume the routine succeeded if that query errors out.

Once errors are resolved and scope is confirmed, run:

~~~sql
CALL sys.heatwave_load(
    JSON_ARRAY('analytics_lab'),
    JSON_OBJECT('mode', 'normal')
);
~~~

Read the summary and inspect each table. The routine may report an error on one table while continuing with others; the `CALL` returning does not prove the entire schema loaded completely.

Dryrun is also an operation that consumes resources and generates operational output/reports; do not describe it as having zero impact.

### 6.3. Manual Path to Understand the Secondary Engine

This is an illustrative alternative; do not re-run it if the routine load already succeeded:

~~~sql
ALTER TABLE analytics_lab.product
    SECONDARY_ENGINE = RAPID;
ALTER TABLE analytics_lab.sales_order
    SECONDARY_ENGINE = RAPID;
ALTER TABLE analytics_lab.order_item
    SECONDARY_ENGINE = RAPID;

ALTER TABLE analytics_lab.product SECONDARY_LOAD;
ALTER TABLE analytics_lab.sales_order SECONDARY_LOAD;
ALTER TABLE analytics_lab.order_item SECONDARY_LOAD;
~~~

`SECONDARY_ENGINE = RAPID` defines the secondary engine, while `SECONDARY_LOAD` loads data into the HeatWave processing path. Some versions offer guided loads that auto-prepare the secondary engine; explicit declarations here clarify both concepts. [Defining the secondary engine](https://dev.mysql.com/doc/heatwave/en/mys-hw-defining-secondary-engine.html).

Do not change the primary engine to `RAPID`. In this model, InnoDB remains the primary engine for transactional tables.

### 6.4. Loading Is Part of the Resource Budget

Initial loading reads and transforms data from the DB system, so it can affect OLTP. Schedule it carefully and observe CPU, memory, I/O, and application latency.

If large ingest batches occur, reload strategies and change propagation must be evaluated against volume, version, and acceptable analytics downtime windows. Do not assume one optimal method fits every data size. [Methods for loading data from a DB system](https://dev.mysql.com/doc/heatwave/en/mys-hw-loading-data.html).

## 7. Confirming Tables Are Ready

### 7.1. Checking Per-Table Status

Using an observer identity with appropriate privileges:

~~~sql
SELECT
    i.TABLE_NAME,
    t.LOAD_STATUS,
    t.NROWS,
    t.SIZE_BYTES
FROM performance_schema.rpd_table_id AS i
JOIN performance_schema.rpd_tables AS t
    ON t.ID = i.ID
WHERE i.SCHEMA_NAME = 'analytics_lab'
ORDER BY i.TABLE_NAME;
~~~

This example uses documented HeatWave metadata; if your version has column or privilege differences, consult that version's metadata schema. [Monitoring load progress and status](https://dev.mysql.com/doc/heatwave/en/mys-hw-metadata-queries-load-progress.html).

Key statuses to recognize:

| Status | Operational Interpretation |
| --- | --- |
| `NOLOAD_RPDGSTABSTATE` | Not yet loaded |
| `LOADING_RPDGSTABSTATE` | Currently loading |
| `AVAIL_RPDGSTABSTATE` | Loaded and available for queries |
| `STALE_RPDGSTABSTATE` | Update issue encountered; HeatWave data requires remediation |
| `UNAVAIL_RPDGSTABSTATE` | Unavailable |

Status lists and details vary by version. Never use a "cluster healthy" status to ignore an unavailable table. [rpd_tables reference](https://dev.mysql.com/doc/heatwave/en/mys-hw-rpd-tables-table.html).

If any of the three required tables is missing or not ready, do not conclude queries are ready.

### 7.2. Metadata Checks Differ from Result Verification

`NROWS`, load status, and footprint help catch missing tables or incomplete loads. However, they do not replace business report reconciliation.

A table with the expected row count can still hold bad source data. A query running on the right engine can still join on the wrong key or double-count revenue.

Separate three checks:

1. All objects loaded.
2. Query executed on the expected engine.
3. Results satisfy business rules.

## 8. Verifying Query Offload and Running Reports

### 8.1. Query Path Prerequisites in This Lesson

For the illustrative analytical queries, you need prepared/loaded tables, supported SQL constructs and data types, and proper session settings.

HeatWave documentation requires `autocommit` enabled for the described offload path, and `use_secondary_engine` set to `ON` or `FORCED`. SQL modes, functions, and query limits must still be checked by version. [HeatWave query prerequisites](https://dev.mysql.com/doc/heatwave/en/mys-hw-query-prerequisites.html).

In a fresh analytics session with no other transactions:

~~~sql
SET SESSION autocommit = 1;

SHOW VARIABLES LIKE 'autocommit';
SHOW VARIABLES LIKE 'use_secondary_engine';
~~~

Switching `autocommit` from 0 to 1 can commit an active transaction. Therefore, never run this setup step arbitrarily on an active business connection.

### 8.2. `ON`, `OFF`, and `FORCED`

| Value | Role |
| --- | --- |
| `OFF` | Do not use the secondary engine for queries in the session |
| `ON` | Allow HeatWave when suitable; may fall back to the primary engine |
| `FORCED` | Require secondary engine execution or fail with an error if impossible |

These modes are session-scoped. [use_secondary_engine variable](https://dev.mysql.com/doc/heatwave/en/heatwave-system-variables.html).

In normal operations, `ON` lets the optimizer choose the right path. During verification, `FORCED` prevents a query from succeeding on InnoDB and being mistakenly assumed accelerated by HeatWave.

`FORCED` does not add support for unsupported SQL and does not make unloaded tables available. Nor is it a setting to apply broadly across all transactional connections.

### 8.3. Using `EXPLAIN` to Inspect the Planned Path

With the small dataset, set `FORCED` in a dedicated test session:

~~~sql
SET SESSION use_secondary_engine = 'FORCED';

EXPLAIN
SELECT
    o.order_date,
    p.category,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(
        SUM(i.quantity * i.unit_price * (1 - i.discount)),
        2
    ) AS revenue
FROM analytics_lab.sales_order AS o
JOIN analytics_lab.order_item AS i
    ON i.order_id = o.order_id
JOIN analytics_lab.product AS p
    ON p.product_id = i.product_id
WHERE o.status = 'PAID'
  AND o.order_date >= '2026-11-01'
  AND o.order_date < '2026-12-01'
GROUP BY o.order_date, p.category
ORDER BY o.order_date, p.category;
~~~

In traditional `EXPLAIN` output, `Using secondary engine RAPID` in the `Extra` column indicates the query is planned for offload to HeatWave. [EXPLAIN and confirming offload](https://dev.mysql.com/doc/heatwave/en/mys-hw-run-query.html).

`EXPLAIN` is plan evidence at inspection time; actually execute the query and observe the real output. Never treat `EXPLAIN` duration as report execution time.

### 8.4. Executing the Query

~~~sql
SELECT
    o.order_date,
    p.category,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(
        SUM(i.quantity * i.unit_price * (1 - i.discount)),
        2
    ) AS revenue
FROM analytics_lab.sales_order AS o
JOIN analytics_lab.order_item AS i
    ON i.order_id = o.order_id
JOIN analytics_lab.product AS p
    ON p.product_id = i.product_id
WHERE o.status = 'PAID'
  AND o.order_date >= '2026-11-01'
  AND o.order_date < '2026-12-01'
GROUP BY o.order_date, p.category
ORDER BY o.order_date, p.category;
~~~

Expected output from the sample data:

| order_date | category | order_count | revenue |
| --- | --- | ---: | ---: |
| 2026-11-01 | DISPLAY | 1 | 2700000.00 |
| 2026-11-01 | PERIPHERAL | 1 | 1200000.00 |
| 2026-11-02 | DISPLAY | 1 | 3200000.00 |
| 2026-11-02 | PERIPHERAL | 1 | 600000.00 |

Total revenue is **7,700,000.00**. Cancelled order 1003 is excluded; the monitor on order 1002 receives a 10% discount.

`order_count` is the count of distinct orders **within each group**. Do not sum these four values and conclude there are four paid orders: there are only three `PAID` orders, and order 1004 appears across two category groups. Distinct counts are not always additive across groups.

After the verification session, return the engine setting to the desired state:

~~~sql
SET SESSION use_secondary_engine = 'ON';
~~~

If the application uses a pool, ensure session state is reset before the connection is reused for other work. Never let `FORCED` from a test leak into unrelated runtime queries.

### 8.5. Query Succeeds Without Offloading

Common root-cause groups:

- A required table or column is not in HeatWave.
- Cluster or table is unavailable.
- `autocommit` or session settings do not meet requirements.
- Unsupported functions, operators, SQL modes, or data types.
- Query is too cheap for offload to be chosen under `ON` mode.
- Optimizer chooses another path per the version's offload heuristics.

Diagnostic documentation explains cost-threshold or dynamic offload decisions depending on version. [Debugging query offload](https://dev.mysql.com/doc/heatwave/en/mys-hw-debugging-queries.html).

Capture the SQL, session configuration, `EXPLAIN`, and error within permitted data boundaries. Use `FORCED` in a test session to clarify the reason, then fix the root cause. Never tweak optimizer variables en masse or disable validation checks just to force a "RAPID" line in output.

## 9. Data Changes After Loading: Change Propagation

### 9.1. Update Path for InnoDB Tables

After a table is loaded in an eligible mode, `INSERT`/`UPDATE`/`DELETE` changes from the DB system are propagated to the corresponding HeatWave data via change propagation.

DML on the DB system does not wait for the entire propagation step to finish. A HeatWave query needing newly updated data can trigger propagation of required changes per service mechanics. [Change propagation](https://dev.mysql.com/doc/heatwave/en/mys-hw-change-propagation.html).

Do not turn an internal propagation interval described in documentation into an SLA promising every dashboard always reflects every change within that exact millisecond count. Account for table status, load mode, errors, and query wait time.

Result correctness and availability must be evaluated together. If a table goes stale due to propagation errors, queries may stop offloading; do not interpret this as HeatWave silently returning stale results with no signal.

### 9.2. Monitoring Propagation System-Wide and Per Table

Observation examples:

~~~sql
SHOW GLOBAL STATUS LIKE 'rapid_change_propagation_status';

SELECT
    i.TABLE_NAME,
    t.POOL_TYPE,
    t.LOAD_STATUS
FROM performance_schema.rpd_table_id AS i
JOIN performance_schema.rpd_tables AS t
    ON t.ID = i.ID
WHERE i.SCHEMA_NAME = 'analytics_lab'
ORDER BY i.TABLE_NAME;
~~~

`POOL_TYPE` distinguishes transactional paths with change propagation from snapshot paths; exact value names vary by version. Never infer from the global variable being `ON` alone that every table uses propagation. [Monitoring change propagation](https://dev.mysql.com/doc/heatwave/en/mys-hw-metadata-queries-change-propagation.html).

If intentionally using snapshots, establish a refresh workflow aligned with business requirements. "Loaded" does not automatically mean "continuously updated."

### 9.3. Testing a Committed Change

Keep the reporting session with appropriate `autocommit`. In a **separate writer session** holding `UPDATE` privileges, modify order 1004 in the test dataset:

~~~sql
START TRANSACTION;

UPDATE analytics_lab.sales_order
SET status = 'CANCELLED'
WHERE order_id = 1004;

COMMIT;
~~~

Re-run the report from the analytics session, confirming the query still uses the expected engine path and produces matching results. With the post-change sample data, only the two rows on 2026-11-01 remain, totaling **3,900,000.00**.

Record commit time and query completion time. If errors occur or expectations fail, inspect propagation, table status, and execution path instead of adding a fixed `sleep` command and calling it solved.

After the test, the writer can restore the sample data:

~~~sql
START TRANSACTION;

UPDATE analytics_lab.sales_order
SET status = 'PAID'
WHERE order_id = 1004;

COMMIT;
~~~

Reconcile the report back to its initial state. Never compare InnoDB and HeatWave timings across two different mutated dataset states.

### 9.4. Lakehouse Sources Need a Separate Workflow

If data is read from Object Storage via Lakehouse, verify file formats, external tables, access policies, and supported load/refresh mechanisms. Never expect replacing a source file to behave identically to an `UPDATE` on an InnoDB table.

If extending the solution to Lakehouse later, explicitly add freshness requirements and source-change detection mechanisms.

## 10. Measuring Performance Against a Baseline

### 10.1. Comparing the Same Query and Same Data

A minimal comparison:

1. Select a stable representative dataset or controlled comparison checkpoint.
2. Record version, cluster shape/nodes, and DB system configuration.
3. Run the query with `use_secondary_engine = 'OFF'` to obtain the InnoDB baseline.
4. Run the same query with `FORCED` to verify the `RAPID` path.
5. Verify equivalent results before comparing timings.
6. Repeat following an agreed warm-up and measurement plan.
7. Restore session settings appropriately after testing.

Never alter indexes, SQL, or data between the two measurement paths and attribute the entire difference to the engine. If separate tuning is performed, clearly label it as a tuned-option comparison with differing conditions documented.

### 10.2. Small Data Only Verifies the Flow

The dataset in this lesson has only a handful of rows. It is suitable for checking permissions, loading, offload, monetary expressions, and post-commit updates.

It is insufficient to evaluate scan speed, join distribution, memory footprint, data skew, or scalability.

A performance PoC requires data with representative scale, distribution, and selectivity, including cases such as:

- Fact tables orders of magnitude larger than dimension tables.
- Skewed keys appearing with very high frequency.
- Uneven time-series data growth.
- Queries with high group counts or large result sets.
- Multiple concurrent users executing queries.

### 10.3. Recording Latency, Concurrency, and OLTP Impact

| Metric Group | What to Record |
| --- | --- |
| Reports | Median/p95, sample count, errors, timeouts, and result size |
| Workload | Arrival rate, concurrency, query mix, and test duration |
| HeatWave | Per-node CPU, memory, network, and executed queries |
| DB system | CPU/I/O, transaction latency, load/propagation overhead |
| Data | Size, row count, distribution, version/data checkpoint |
| Operations | Load, reload, start/recovery times, and manual steps |

A single query dropping from 40 seconds to 3 seconds in isolation does not prove eight concurrent users will all achieve a 5-second p95.

Likewise, fast reports whose initial load causes OLTP to breach SLOs must be addressed through scheduling, sizing, or deployment architecture.

### 10.4. Example of Reading Metrics

The numbers below are purely hypothetical, solely to illustrate the calculation:

| Query | InnoDB | HeatWave | InnoDB/HeatWave Time Ratio |
| --- | --- | --- | --- |
| Large revenue aggregation | 48 seconds | 2.4 seconds | 20x |
| Join and grouping | 12 seconds | 1.5 seconds | 8x |
| Single-row lookup | 0.003 seconds | 0.008 seconds | 0.375x |

The final row shows a distributed analytical path may not suit tiny lookups. In operations, let the optimizer choose the appropriate path rather than forcing every `SELECT` onto HeatWave.

Never take the speedup factor of the fastest query as the factor for the entire application. You can weight total workload time by query frequency, while still enforcing separate p95, error, and concurrency constraints.

## 11. Estimating Memory, Node Count, and Concurrency

### 11.1. InnoDB Size Does Not Equal HeatWave Footprint

Never take raw data file size or backup size and divide it directly by one node's RAM.

Footprint depends on:

- Actual tables and columns loaded.
- Data types, lengths, and distinct value counts.
- Compression/encoding applied.
- Data distribution across nodes.
- Memory needed during load operations.
- Query, join, sort, and aggregation workspaces.
- Concurrency and growth.

A schema with large text columns unused by reports can have a very different loading plan from a schema where all columns are queried. Column exclusions must be paired with workload compatibility checks.

### 11.2. Using the Estimator as a Starting Point

OCI provides a node count estimator based on tables/columns and in-memory compression. Under-provisioning can cause loads or queries to fail; over-provisioning inflates costs. [Estimating HeatWave node count](https://docs.oracle.com/en-us/iaas/mysql-database/doc/generating-node-count-estimate.html).

Workflow:

1. Select the dataset and projected workload.
2. Run the appropriate dryrun/estimator.
3. Resolve data type or load-scope errors.
4. Select an initial configuration.
5. Measure footprint and queries at target concurrency.
6. Adjust for growth scenarios.

Estimating just enough memory to hold data does not prove target concurrency will hit latency goals. Queries may need extra workspace or hit CPU/network limits.

### 11.3. An Illustrative Capacity Budget Model

Suppose a PoC on a representative dataset yields these estimates:

~~~text
Loaded data:                                   600 GiB
Projected workspace at target concurrency:     180 GiB
Projected management and other overhead:        60 GiB
Total modeled demand:                          840 GiB

If targeting 80% utilization:
    Effective memory budget required
    = 840 / 0.80
    = 1,050 GiB
~~~

If in the same model each node contributes 256 GiB of effective budget, the preliminary calculation is `ceil(1,050 / 256) = 5` nodes.

These are hypothetical numbers for illustration—not official OCI shapes, available memory capacities, or reserve ratios. Verify service limits, estimator output, and actual memory distribution; never replace service reports with this formula.

The workspace figure in the example represents an aggregate budget evaluated for target concurrency, not a claim that every query allocates fixed memory or scales linearly.

### 11.4. Monitoring Per Node and Data Skew

Cluster-wide memory may look ample while a single node faces severe pressure. Similarly, low average CPU does not rule out part of a task hitting a bottleneck.

Data skew occurs when certain keys or groups dominate data volume. Joins or `GROUP BY` operations can then create uneven work distribution.

When queries scale poorly despite adding nodes, check:

- Do all nodes show similar resource utilization?
- Does a join generate excessive intermediate rows?
- Do a few keys dominate the dataset?
- Is the result set too large to ship back to the client?
- Does the query contain low-parallelism stages or heavy data-exchange overhead?

Use version-supported optimization mechanisms and advisors where appropriate. Do not keep adding nodes without evidence identifying the bottleneck.

## 12. Monitoring the Cluster, Tables, and Analytics Service

### 12.1. Monitoring Layers

| Layer | Signals | Operational Question |
| --- | --- | --- |
| OCI resources | Cluster/node status, work requests | Is the cluster active or undergoing changes? |
| Load | Progress, missing tables, warnings/errors | Are all required tables ready? |
| Data | Pool type, load status, propagation | Are tables updating per the chosen strategy? |
| Queries | HeatWave query counts, engine, errors, duration | Are reports actually running on the intended path? |
| Compute resources | Per-node CPU, memory, network | Which resource limit is being approached? |
| DB system | OLTP latency, I/O, CPU, and connections | Are analytics, loads, or fallbacks impacting transactions? |
| BI application | Queues, timeouts, result sizes, caches | Are users getting accurate and timely results? |

OCI provides metrics such as `HeatWaveHealth`, `HeatWaveDataLoadProgress`, `HeatWaveStatements`, CPU, and memory within appropriate resource scopes. [Monitoring HeatWave metrics](https://docs.oracle.com/en-us/iaas/mysql-database/doc/monitoring-heatwave-metrics.html).

Select the exact resource and dimensions, especially when viewing per-node vs. aggregated views. Aggregate metric changes alone do not prove a specific query offloaded; correlate timestamps with query telemetry.

### 12.2. Alerts Must Have Actionable Runbooks

Design alert examples, not default service thresholds:

- Required table not in ready state outside change windows.
- Load stalled or finished with failed tables.
- Reports consistently breaching runtime targets.
- HeatWave query count drops sharply while analytics requests keep rising.
- Per-node memory or CPU nears limits observed in PoC.
- OLTP slows down after multiple reports fall back.
- Cluster stays in recovery longer than the analytics service budget.

Every alert needs an owning team, diagnostic context, and remediation steps. A "cluster reloading" alert during a maintenance window requires a different response than an unplanned reload.

### 12.3. "Healthy" Is Not Proof That Reports Work

An analytics health check should include a small, meaningful query that verifies the expected engine, privileges, required tables, and output.

Do not run heavy full-scan queries too frequently as health checks. Design probes with bounded load, timeouts, and least-privilege accounts.

For dashboards with caching, separate database errors from unrefreshed caches. UI render time can include query time, data transfer, BI processing, and cache behavior.

## 13. Operations Across Restarts, Resizes, and Schema Changes

### 13.1. Resource State vs. Serving State

After start/restart or configuration changes, recovery or reload time may be required before all tables are usable for analytics again.

The service includes persistence mechanisms to recover loaded HeatWave data; resize details, shape changes, and reload requirements depend on version/configuration. [Managing a HeatWave cluster](https://docs.oracle.com/en-us/iaas/mysql-database/doc/managing-heatwave-cluster.html).

Runbooks should verify:

1. Work request completed.
2. Cluster/nodes are in the expected state.
3. Required tables are ready.
4. Verification query offloads cleanly.
5. Output and latency meet targets.

Never treat "cluster started" as the moment reports are guaranteed to serve normally.

### 13.2. Recovery Persistence Does Not Replace Database Backups

HeatWave includes persistent storage supporting data recovery for the cluster. It serves the accelerator's lifecycle; it does not replace backup, PITR, or DR strategies for business data in the DB system.

Accidental valid deletion of source data committed to InnoDB still requires an appropriate database recovery plan. Adding analytical nodes does not create a standby for the transactional database either.

Design RPO/RTO for source data separately from analytics service recovery time. The two targets are related but distinct.

### 13.3. Resizing Requires Impact Assessment

Before resizing:

- Re-run node estimation against current data.
- Check elastic resize or normal resize prerequisites for your configuration.
- Confirm whether reloads are needed, query impact, and expected duration.
- Pick a suitable low-load window.
- Define post-operation acceptance criteria.

Do not promise zero disruption for every resize. Nor should you downsize node counts based purely on data footprint without accounting for workspace and concurrency.

### 13.4. DDL Must Be Paired with Offload Verification

When altering schemas:

1. Identify tables/columns tied to analytical queries.
2. Check whether the DDL is supported on loaded tables.
3. Evaluate unload/reload requirements or other coordination steps.
4. After migration, verify load status and compatibility.
5. Re-run critical queries, reconcile results, and inspect `EXPLAIN`.

A migration succeeding on InnoDB may still require steps to restore the analytical path. Never check only the OLTP endpoint and declare deployment complete.

## 14. Diagnosing and Resolving Common Issues

### 14.1. Tables Not Loaded or Partially Loaded

Start with the routine summary and per-table status. Distinguish missing privileges, incompatible data types, insufficient memory, and an inactive cluster.

Address failed tables by root cause, then re-verify the tables accessed by queries. Do not repeatedly run full-schema loads in a loop when the blocker is a single column or resource limit.

If the cluster is inactive, some routine paths may execute only dryrun/checks depending on version mechanics. Always verify final load status rather than inferring success from `CALL` completion.

### 14.2. Query Not Offloading

| Symptom | Area to Investigate |
| --- | --- |
| No `RAPID` indicator in `EXPLAIN` | Session mode, loaded tables/columns, compatibility, and optimizer decision |
| Succeeds under `ON`, errors under `FORCED` | Capture the error and cross-check offload prerequisites |
| Small query runs on InnoDB under `ON` | Evaluate suitability and cost; not necessarily an incident |
| Query stops offloading after adding a column | Is the column in the secondary engine and supported? |
| BI client behaves differently from MySQL CLI | `autocommit`, generated SQL, SQL mode, and session settings |
| Fact table loaded but join fails | Check all related dimension/query tables |
| Reports slow after restart | Has load/recovery finished, or are queries falling back? |

Use scoped diagnostics to fix SQL or configuration. If SQL is unsupported, consider rewriting with identical semantics and verifying results, or intentionally keeping that query on the primary path.

### 14.3. Stale Tables from Propagation Errors

Collect load status, pool type, errors, and recent data/schema change history. Some cases have service-driven self-recovery; others require manual unload/reload per version guidelines.

Once confirmed that a test table requires reload:

~~~sql
ALTER TABLE analytics_lab.sales_order SECONDARY_UNLOAD;
ALTER TABLE analytics_lab.sales_order SECONDARY_LOAD;
~~~

Unload affects the data representation in the secondary engine; it does not drop the InnoDB table. However, it makes that table's analytical path unavailable during processing.

Never run bulk unloads in production without coordinating queries, source load, and service availability requirements. After reloading, verify queries, outputs, and propagation—do not merely check that the final command returned without error.

### 14.4. Fallback Increasing DB System Load

Under `ON` mode, queries that cannot offload can fall back to the primary engine. If multiple heavy reports fall back together, the DB system experiences a very different load profile than when the cluster serves normally.

Define application-level policies:

- Cap report concurrency.
- Set appropriate timeouts and monitor execution engine.
- Pause or queue reports when the accelerator is unavailable.
- Classify which reports are permitted to fall back.
- For queries strictly requiring HeatWave, evaluate using `FORCED` within verified connections/queries and returning controlled errors.

The choice must align with service objectives. `FORCED` prevents silent load shifting, at the trade-off that queries fail when the accelerator is unavailable.

### 14.5. Different Results Across Two Runs

Before concluding the engine is wrong, check:

- Did both reads query the same data checkpoint?
- Did a writer commit between the two measurements?
- Are time filters, timezones, and SQL modes identical?
- Does a join multiply rows?
- Are floating-point arithmetic or non-deterministic ordering involved?
- Did the application/BI layer cache or apply extra rounding?

This lesson uses `DECIMAL` and explicit filter rules to reconcile revenue. For approximate numeric types, define business-appropriate tolerances rather than comparing formatted display strings arbitrarily.

## 15. Cost Control and Automation

### 15.1. Accounting for All Cost Components

Estimate costs across:

- MySQL DB system serving transactions and SQL intake.
- HeatWave cluster based on resources and uptime.
- Storage, backups, networking, and add-on services in use.
- Lakehouse storage if enabled with stored data.
- Load, recovery, validation, and operational effort.

Never compare cluster cost solely against a single query's runtime. Evaluate the entire workload and required service levels.

Per billing documentation, stopping a cluster pauses billing for the cluster and starting resumes it; Lakehouse storage follows separate rules and may continue incurring charges while stopped. Other DB system components must also be evaluated separately. [HeatWave billing](https://docs.oracle.com/en-us/iaas/mysql-database/doc/billing.html).

### 15.2. Scheduled Stops Must Account for Startup Recovery Time

If analytics only runs during business hours, you can evaluate an operating schedule compatible with service rules. The schedule must allow time for:

~~~text
Start cluster
    -> recovery/reload
    -> verify tables
    -> verification query
    -> open reporting traffic
~~~

Do not start the cluster the exact minute users open dashboards and expect every table to be ready immediately.

Measure both cost savings and recovery duration before deciding on frequent stops. For unscheduled workloads, an always-on option may fit better.

### 15.3. Automation Must Verify Outcomes

A workflow can manage cluster state, run controlled loads, inspect metadata, and send status notifications.

Conditions should be encoded explicitly:

- Correct target DB system/schema and version.
- No overlapping incompatible administrative operations.
- Timeouts and persisted work request/error tracking.
- All required tables are ready.
- Verification query executes on the intended engine.
- Designated recipients notified when criteria fail.

A script that merely calls the "start" API and reports success has not completed the analytics readiness objective. Final status must tie to actual report readiness.

## 16. Hands-On Practice and Completion Evidence

### 16.1. Preparation

Use a test DB system with a supported HeatWave cluster, appropriate privileges, MySQL connectivity, and data isolated from production.

If resources are not yet provisioned, you can still complete schema design, queries, and measurement plans. In that case, do not claim load/offload or performance as verified.

### 16.2. Sequence

1. Record DB system, version, cluster configuration, and objectives.
2. Create the three sample tables and insert data into InnoDB.
3. Confirm source data is committed.
4. Run Auto Parallel Load dryrun and inspect errors/warnings.
5. Load using normal mode or a clearly understood manual path.
6. Verify all three tables show ready status.
7. Open a dedicated analytics session and check `autocommit` and engine mode.
8. Use `EXPLAIN` and `FORCED` to verify the query.
9. Reconcile report rows and total revenue of 7,700,000.00.
10. Using a separate writer, change order 1004 status, commit, and reconcile the 3,900,000.00 total.
11. Restore sample data and verify again.
12. Return session settings to the appropriate state after testing.
13. When evaluating performance, replace the small dataset with a representative workload and run a separate measurement plan.
14. Review configurations and clean up test resources once no longer needed within your assigned admin scope.

### 16.3. Results Record Table

| Item | Evidence |
| --- | --- |
| Cluster | Configuration, status, and related work requests |
| Data | Source row counts, commit state, and schema scope |
| Load | Summary, warnings, errors, and status of all three tables |
| Offload | Session config, `EXPLAIN`, and verified execution |
| Results | Revenue groups and reconciled calculations |
| Updates | Committed change and post-change report |
| Performance | Representative dataset, load, sample counts, latency, and errors |
| Resources | CPU/memory/network, OLTP impact, and footprint |
| Operations | Start/recovery/reload times and fallback handling |
| Cost | Resource scope and usage duration assumptions |

Completing the SQL flow on a small dataset demonstrates how the mechanism works. Only after measuring on a representative workload do you have a basis to size a cluster or commit to service targets.

## 17. Core Principles to Apply

HeatWave provides an accelerated analytical processing path for properly prepared data while applications continue using the DB system's MySQL interface.

During deployment, always connect four pieces of evidence: **tables ready, query offloaded, results accurate, and performance meeting targets**. Monitor ongoing data updates, OLTP load, recovery behavior, and cost to sustain those outcomes in production.

Autopilot and automated mechanisms assist with estimation, loading, and optimization. The operator's responsibility remains selecting the right workloads, confirming version-specific behavior, and verifying real application goals.
