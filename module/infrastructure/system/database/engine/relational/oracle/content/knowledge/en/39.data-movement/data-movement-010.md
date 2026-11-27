# External Tables for Reading Files and Processing Data with SQL

Oracle External Tables allow the database to query data stored in files outside the database using standard SQL statements. Instead of loading a file into a physical table first before filtering, joining, or aggregating, you define metadata describing the file structure and how Oracle reads the file. You can then run `SELECT`, `JOIN`, `WHERE`, `GROUP BY`, views, and SQL transformations over that data.

External tables are particularly useful for data ingestion workflows, file reconciliation, processing data exchanged with external systems, and batch-reading large datasets. They provide an SQL access layer over files, letting you leverage Oracle's query optimizer, data types, SQL functions, and data validation capabilities.

A key point to remember is that **external table data remains in operating system files or external storage**. The database stores the table definition and metadata, and on each query Oracle reads data from the file via the declared access driver. External tables are typically read-only to SQL; if you need to persist cleansed data or serve repeated queries, results are usually loaded into a staging or business table.

## 1. What Is an External Table?

An external table is a database object with a column structure like a regular table, but whose data comes from an external source. An external table definition specifies:

- The file or files to read.
- The directory object representing the folder on the database server.
- The access driver used to interpret the data.
- Record and field formatting.
- How file fields map to SQL columns.
- Error-record handling policy and maximum allowed errors.

For example, a system receives an `orders.csv` file from a sales application. You create external table `EXT_ORDERS` describing the fields in the file. You can then query:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID';
```

Oracle reads the file according to the external table definition when executing the SQL statement. No automatic copy of the entire file into a table segment happens merely because the external table was created.

### 1.1. How do external tables differ from regular tables?

| Characteristic | Regular table | External table |
|---|---|---|
| Data storage location | Datafiles managed by Oracle | Files outside the database |
| Data stored in table segment | Yes | Not under the standard external table model |
| Created with `CREATE TABLE` | Yes | Yes, with `ORGANIZATION EXTERNAL` |
| Queryable via SQL | Yes | Yes |
| Direct `INSERT`, `UPDATE`, `DELETE` DML | Yes, with privileges | Not supported like regular tables with `ORACLE_LOADER` |
| Database indexes on data | Can be created | Cannot create indexes like a regular physical table |
| Stored and enforced constraints like regular tables | Yes | Should not rely on external tables to replace target table constraints |
| Data changes | Through transactions/database | Changes when the source file is replaced or edited |
| Transaction rollback | Yes for transactional DML | Cannot roll back source file changes with SQL `ROLLBACK` |

External tables serve well as a read source and integration layer. Physical tables serve well for storing validated data, building indexes, enforcing constraints, and serving frequent business queries.

### 1.2. Architectural components

```text
             File on server / shared storage
                         |
                         v
                  DIRECTORY object
                         |
                         v
                External table metadata
                  +--------------+
                  | SQL columns  |
                  | Access driver|
                  | File location|
                  | Access params|
                  +--------------+
                         |
                         v
                    SQL statement
             SELECT / JOIN / GROUP BY / VIEW
                         |
                         v
                 Results for application
```

The directory object is a logical name inside the database pointing to a server path. The access driver is responsible for reading and parsing the file. The optimizer plans SQL over external tables much like other row sources, within the information and capabilities provided by the driver.

## 2. Access Drivers and External Table Types

The access driver defines how Oracle exchanges data with external files or sources. Common drivers include:

| Driver | Primary purpose |
|---|---|
| `ORACLE_LOADER` | Reads text data such as CSV, delimiter-separated, fixed-width, or supported record formats |
| `ORACLE_DATAPUMP` | Reads and writes Oracle Data Pump external table proprietary binary file format |
| `ORACLE_HDFS`, `ORACLE_HIVE`, and related drivers | Accesses big data sources in supported configurations/versions and products |

For reading text files exported by applications or external systems, `ORACLE_LOADER` is the common choice. Although the driver name contains `LOADER`, with an external table you query data through SQL rather than invoking the SQL*Loader command line for every read.

`ORACLE_DATAPUMP` uses a proprietary binary format, useful when unloading data from a database to files or reading unloaded data back. Files created by this driver are not CSVs and should not be edited with a text editor. Big data drivers depend on Oracle version, configuration, and deployed products.

## 3. Preparing Files and the DIRECTORY Object

### 3.1. Files must reside on the database server

External table files are read by the database server. The file path is the path seen by Oracle Database processes on the server, not a path on the machine running SQL Developer, SQLcl, or a client application.

For example, the file is placed at:

```text
/u01/app/oracle/extdata/orders.csv
```

This folder must exist on the database server and the OS account running Oracle must have read permissions on the file. If the driver needs to create log, bad, or discard files, the OS account also needs appropriate write permissions.

In RAC, the file must be available at the corresponding path on every node that may run external table queries. Typically, place the file on a consistently mounted shared filesystem or storage. If the file exists on only one node while queries run on another node, reading the file may fail depending on the executing instance.

### 3.2. Creating a DIRECTORY object

A DBA or user with directory-creation privileges can declare the path:

```sql
CREATE OR REPLACE DIRECTORY ext_data_dir
AS '/u01/app/oracle/extdata';
```

`EXT_DATA_DIR` is the object name inside the database. The path string is the server-side path. Creating a directory object does not create the physical OS directory and does not grant OS read/write permissions.

### 3.3. Granting privileges on DIRECTORY

The user creating and querying the external table needs appropriate privileges on the directory object. For a read-only external table, grant `READ`:

```sql
GRANT READ ON DIRECTORY ext_data_dir TO app_loader;
```

If Oracle Loader needs to write log, bad, or discard files in the directory, also grant `WRITE`:

```sql
GRANT WRITE ON DIRECTORY ext_data_dir TO app_loader;
```

Database privileges on DIRECTORY and OS permissions are two separate layers. Having `READ ON DIRECTORY` while the OS account cannot read the file still causes queries to fail. Conversely, the OS account being able to read the file while the database user lacks `READ` on the directory object is also insufficient.

Do not grant `READ`/`WRITE` on directories holding sensitive files to `PUBLIC`. Use a dedicated directory for external table data and grant privileges only to the required schema/service.

### 3.4. Inspecting privileges and directory metadata

Common views:

```sql
SELECT directory_name,
       directory_path
FROM all_directories
ORDER BY directory_name;
```

```sql
SELECT grantee,
       table_name AS directory_name,
       privilege,
       grantable
FROM all_tab_privs
WHERE type = 'DIRECTORY'
ORDER BY table_name, grantee, privilege;
```

Visibility depends on user privileges. DBAs can use `DBA_DIRECTORIES` and `DBA_TAB_PRIVS` for a database-wide view.

## 4. Creating Your First External Table with ORACLE_LOADER

Suppose `orders.csv` contains:

```csv
1001,501,2026-10-01,1250.50,PAID
1002,502,2026-10-02,800.00,NEW
1003,501,2026-10-03,420.75,PAID
```

Each line has five fields in order:

1. `ORDER_ID`
2. `CUSTOMER_ID`
3. `ORDER_DATE`
4. `TOTAL_AMOUNT`
5. `ORDER_STATUS`

Create the external table:

```sql
CREATE TABLE ext_orders (
    order_id       NUMBER,
    customer_id    NUMBER,
    order_date     DATE,
    total_amount   NUMBER(12,2),
    order_status   VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        BADFILE 'orders.bad'
        LOGFILE 'orders.log'
        FIELDS TERMINATED BY ','
        MISSING FIELD VALUES ARE NULL
        (
            order_id       INTEGER EXTERNAL,
            customer_id    INTEGER EXTERNAL,
            order_date     CHAR(10) DATE_FORMAT DATE MASK "YYYY-MM-DD",
            total_amount   CHAR(20),
            order_status   CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT 100;
```

Key elements:

- `ORGANIZATION EXTERNAL`: declares this as an external table.
- `TYPE ORACLE_LOADER`: uses the text-reading driver.
- `DEFAULT DIRECTORY`: default directory object for files.
- `RECORDS DELIMITED BY NEWLINE`: each record ends with a newline.
- `FIELDS TERMINATED BY ','`: fields are separated by commas.
- `MISSING FIELD VALUES ARE NULL`: missing fields are interpreted as `NULL` per loader rules.
- `BADFILE`, `LOGFILE`: where rejected records and read-process details are written.
- `LOCATION`: source filename inside the directory.
- `REJECT LIMIT`: maximum rejected records allowed in a single access before the statement errors out.

The example above assumes numeric and date formats match the declared settings. For data exchanged from multiple systems, consider reading fields initially as character strings and converting via SQL after validation.

### 4.1. Querying an external table

Once the table is created and the file is present, query it like a normal table:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount,
       order_status
FROM ext_orders;
```

Filtering data:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-10-01'
  AND order_date <  DATE '2026-11-01';
```

Joining with a database table:

```sql
SELECT e.order_id,
       c.customer_name,
       e.total_amount
FROM ext_orders e
JOIN app.customers c
  ON c.customer_id = e.customer_id
WHERE e.order_status = 'PAID';
```

External tables can be used in views, CTEs, subqueries, aggregates, and normal SQL expressions. Transformations run according to the execution plan selected by the optimizer.

## 5. Record and Field Formatting in ORACLE_LOADER

`ACCESS PARAMETERS` describes the physical structure of the file. This definition must match how the generating system created the file. If delimiter, record terminator, quotes, or data types mismatch, data may shift columns or be rejected.

### 5.1. Newline-delimited records

The most common format puts one record per file line:

```sql
RECORDS DELIMITED BY NEWLINE
```

Across operating systems, newlines can be LF or CRLF. Oracle Loader supports record delimiters per driver rules; if files come from another OS, check line endings if you encounter errors on the last line or trailing carriage returns retained in data.

### 5.2. Delimiter-separated fields

Example pipe-delimited (`|`) file:

```text
1001|501|2026-10-01|1250.50|PAID
1002|502|2026-10-02|800.00|NEW
```

Access parameters:

```sql
FIELDS TERMINATED BY '|'
(
    order_id       INTEGER EXTERNAL,
    customer_id    INTEGER EXTERNAL,
    order_date     CHAR(10) DATE_FORMAT DATE MASK "YYYY-MM-DD",
    total_amount   CHAR(20),
    order_status   CHAR(20)
)
```

Columns map by field order in the file. Do not assume column order in a `SELECT` statement affects how Oracle reads fields; physical mapping is defined by the field list inside access parameters.

### 5.3. Fields enclosed in double quotes

CSV often allows a field to contain the delimiter if wrapped in double quotes:

```csv
1001,501,"01, Main Street",PAID
1002,502,"Warehouse A",NEW
```

You can declare:

```sql
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
(
    order_id      INTEGER EXTERNAL,
    customer_id   INTEGER EXTERNAL,
    address       CHAR(200),
    order_status  CHAR(20)
)
```

`OPTIONALLY ENCLOSED BY` allows fields to be wrapped by an enclosure character. Escaping rules for quotes inside fields must align with the file producer and be tested against Oracle Loader's behavior; do not assume every CSV variant from every application is fully compatible.

### 5.4. Fixed-width files

Not all files use delimiters. Some systems export fixed-length records:

```text
00001001JOHN      0001250.50
00001002MARIA     0000800.00
```

For fixed-width files, declare field positions and lengths using Oracle Loader's positional field syntax rather than `FIELDS TERMINATED BY`. Conceptual example:

```sql
ACCESS PARAMETERS (
    RECORDS FIXED 32
    FIELDS (
        order_id      POSITION(1:8)  CHAR(8),
        customer_name POSITION(9:18) CHAR(10),
        amount_text   POSITION(19:28) CHAR(10)
    )
)
```

Record length and positions must match the actual file format exactly. Account for bytes vs. characters per file encoding and driver rules; with multi-byte characters, never deduce byte offsets solely from visible character counts.

### 5.5. Skipping headers

If the file has a header line:

```csv
ORDER_ID,CUSTOMER_ID,ORDER_DATE,TOTAL_AMOUNT,ORDER_STATUS
1001,501,2026-10-01,1250.50,PAID
```

you can configure skipping the first record:

```sql
ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    SKIP 1
    FIELDS TERMINATED BY ','
    (
        order_id      INTEGER EXTERNAL,
        customer_id   INTEGER EXTERNAL,
        order_date    CHAR(10),
        total_amount  CHAR(20),
        order_status  CHAR(20)
    )
)
```

Use `SKIP 1` only if every file has exactly one header record. If a file lacks a header or the number of leading lines varies, this setting will skip real data.

### 5.6. Missing values, whitespace, and NULL

Text files can represent empty values in several ways: an empty field, whitespace only, two consecutive delimiters, or a token like `NULL`/`N/A`. Confirm the source system's convention.

`MISSING FIELD VALUES ARE NULL` interprets missing fields as `NULL`. For explicit tokens, use `NULLIF` in the field specification per supported loader syntax. Illustrative example:

```sql
FIELDS TERMINATED BY ','
(
    order_id    CHAR(20),
    amount_txt  CHAR(20) NULLIF amount_txt = 'NULL',
    status_txt  CHAR(20)
)
```

For leading/trailing whitespace, use appropriate Oracle Loader trim directives or clean up with `TRIM` in SQL. Distinguish empty strings from `NULL`: in Oracle SQL, zero-length character strings are treated as `NULL` for standard character types.

## 6. Reading Raw Text and Converting via SQL

In data ingestion pipelines, a flexible design is defining the external table with text columns and then using SQL to validate and convert into business data types. This separates file-formatting errors from business-rule errors and enables deliberate reporting of invalid records.

Example file:

```csv
1001,501,2026-10-01,1250.50,PAID
1002,502,not-a-date,800.00,NEW
1003,501,2026-10-03,invalid,PAID
```

Create raw external table:

```sql
CREATE TABLE ext_orders_raw (
    order_id_txt      VARCHAR2(30),
    customer_id_txt   VARCHAR2(30),
    order_date_txt    VARCHAR2(30),
    amount_txt        VARCHAR2(30),
    status_txt        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        BADFILE 'orders_raw.bad'
        LOGFILE 'orders_raw.log'
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_txt     CHAR(30),
            customer_id_txt  CHAR(30),
            order_date_txt   CHAR(30),
            amount_txt       CHAR(30),
            status_txt       CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
```

Then trim whitespace and convert:

```sql
SELECT TO_NUMBER(TRIM(order_id_txt)) AS order_id,
       TO_NUMBER(TRIM(customer_id_txt)) AS customer_id,
       TO_DATE(TRIM(order_date_txt), 'YYYY-MM-DD') AS order_date,
       TO_NUMBER(TRIM(amount_txt), '999999999999D99',
                 'NLS_NUMERIC_CHARACTERS=''.,''') AS total_amount,
       UPPER(TRIM(status_txt)) AS order_status
FROM ext_orders_raw;
```

The query above will raise an error if any value fails conversion. For pipelines that must continue processing valid rows and isolate invalid rows, validate formats before calling conversion functions.

### 6.1. Checking conversion before converting

In Oracle versions supporting `VALIDATE_CONVERSION` (Oracle Database 12.2 and later), you can validate data:

```sql
SELECT order_id_txt,
       order_date_txt,
       amount_txt,
       CASE
           WHEN VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(order_date_txt) AS DATE,
                    'YYYY-MM-DD'
                ) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(amount_txt) AS NUMBER,
                    '999999999999D99',
                    'NLS_NUMERIC_CHARACTERS=''.,'''
                ) = 1
           THEN 'VALID'
           ELSE 'INVALID'
       END AS validation_status
FROM ext_orders_raw;
```

`VALIDATE_CONVERSION` returns 1 if the expression can be converted and 0 otherwise; `NULL` handling follows the function's rules. Add business-rule checks such as non-negative amounts, allowed status lists, and existing foreign keys.

In versions supporting `DEFAULT ... ON CONVERSION ERROR`, it can handle conversion failures in some expressions, though you should not replace error reporting with default values that silently accept bad data.

### 6.2. Separating valid and invalid rows

You can create a classification view:

```sql
CREATE OR REPLACE VIEW v_orders_validated AS
SELECT order_id_txt,
       customer_id_txt,
       order_date_txt,
       amount_txt,
       status_txt,
       CASE
           WHEN VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(TRIM(customer_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(order_date_txt) AS DATE,
                    'YYYY-MM-DD'
                ) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(amount_txt) AS NUMBER,
                    '999999999999D99',
                    'NLS_NUMERIC_CHARACTERS=''.,'''
                ) = 1
           THEN 'Y'
           ELSE 'N'
       END AS is_valid
FROM ext_orders_raw;
```

Read rows to process:

```sql
SELECT *
FROM v_orders_validated
WHERE is_valid = 'Y';
```

Read rows needing investigation:

```sql
SELECT *
FROM v_orders_validated
WHERE is_valid = 'N';
```

In practice, record filename, batch ID, line number, failure reason, and load timestamp into a dedicated reject table for reconciliation and reprocessing. Do not just output an `INVALID` flag if operational workflows need to know which specific column failed.

## 7. Handling Error Records: LOGFILE, BADFILE, DISCARDFILE, and REJECT LIMIT

Oracle Loader can write diagnostic files while reading an external table.

| Component | Purpose |
|---|---|
| Log file | Records file access/read details and loader errors |
| Bad file | Records rows rejected due to format, conversion, or loader conditions |
| Discard file | Records rows excluded by configured discard/WHEN conditions if present |
| Reject limit | Maximum error records allowed before the query aborts |

Example declaration:

```sql
ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    BADFILE 'orders.bad'
    LOGFILE 'orders.log'
    DISCARDFILE 'orders.dsc'
    FIELDS TERMINATED BY ','
    (
        order_id_txt  CHAR(30),
        amount_txt    CHAR(30),
        status_txt    CHAR(20)
    )
)
```

These files are written in the designated directory per external table/loader rules. The database user needs `WRITE` on that directory and Oracle's OS account needs write permission on the folder.

### 7.1. REJECT LIMIT

Example:

```sql
REJECT LIMIT 10;
```

If rejected records exceed the limit, the query terminates with an external table error. You can use:

```sql
REJECT LIMIT UNLIMITED;
```

to let the query continue regardless of reject count, per driver semantics. `UNLIMITED` does not make bad records valid; it only removes the reject abort threshold. Workflows must still monitor bad files and logs so dropped data is not overlooked.

Do not default to `UNLIMITED` for every batch. If a file has widespread formatting errors, the query could complete while producing incomplete results. Set reject limits based on SLAs, source quality, and error-tracking capabilities.

### 7.2. Distinguishing loader errors from business errors

Bad files typically reflect records the loader could not parse according to access parameters. However, business-invalid values such as status `UNKNOWN`, non-existent customer IDs, or negative amounts may still be read cleanly by the loader.

Therefore, enforce two validation layers:

1. **File/format validation:** does the record match the structure, delimiter, encoding, and data types the loader can read?
2. **Business validation:** are values valid against business rules and relational integrity?

A record can pass the first layer yet fail the second. Business validation failures should be logged to a reject table or dedicated audit report.

## 8. Multiple Files in LOCATION and Batch Management

An external table can read one or multiple files listed in `LOCATION`. Example:

```sql
LOCATION (
    'orders_20261001.csv',
    'orders_20261002.csv',
    'orders_20261003.csv'
)
```

Files must reside in the designated directory and conform to the same external table definition. If files differ in schema or delimiters, create separate external tables or normalize the files beforehand.

### 8.1. Filenames and batch conventions

A reliable workflow should use naming conventions capturing data type, date/batch, and status:

```text
orders_20261114_batch001.csv
orders_20261114_batch002.csv
```

Track batch metadata in a database control table, including filename, size, checksum, received timestamp, expected row count, processing status, and loaded row count. An external table only describes how to read; it does not track already-processed files or prevent duplicate loading.

### 8.2. Avoid modifying files while a query runs

Source files must remain stable for the entire query duration. If another process overwrites or modifies a file while Oracle is reading it, results may become inconsistent or raise I/O errors. Producers should write to a temporary filename, finish and close the file, and then atomically rename/move it to the final name used by the external table.

Do not delete or move source files immediately after starting a query before confirming the database has finished reading. Let job orchestration manage file lifecycles and mark batches complete only after SQL succeeds.

## 9. Combining External Tables with SQL and Staging Tables

External tables often serve as the ingestion layer of a pipeline. A typical flow:

```text
File received from external system
          |
          v
   External table (raw)
          |
          v
   Validate format and data
       /           \
      v             v
  Valid rows    Invalid rows
      |             |
      v             v
  Staging table   Reject table
      |
      v
  Transform / JOIN / MERGE
      |
      v
  Business table
```

### 9.1. Loading valid data into staging

Example staging table:

```sql
CREATE TABLE stg_orders (
    batch_id       NUMBER NOT NULL,
    order_id       NUMBER NOT NULL,
    customer_id    NUMBER NOT NULL,
    order_date     DATE NOT NULL,
    total_amount   NUMBER(12,2) NOT NULL,
    order_status   VARCHAR2(20) NOT NULL,
    source_file    VARCHAR2(255),
    loaded_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

Load validated rows:

```sql
INSERT INTO stg_orders (
    batch_id,
    order_id,
    customer_id,
    order_date,
    total_amount,
    order_status,
    source_file
)
SELECT :batch_id,
       TO_NUMBER(TRIM(order_id_txt)),
       TO_NUMBER(TRIM(customer_id_txt)),
       TO_DATE(TRIM(order_date_txt), 'YYYY-MM-DD'),
       TO_NUMBER(TRIM(amount_txt), '999999999999D99',
                 'NLS_NUMERIC_CHARACTERS=''.,'''),
       UPPER(TRIM(status_txt)),
       :source_file
FROM v_orders_validated
WHERE is_valid = 'Y';
```

Once loaded, you can leverage constraints, indexes, statistics, and transactions on the staging table to verify and process data. Filename and batch ID provide row-level lineage back to the source.

### 9.2. Using MERGE to synchronize into the target table

Once staging is validated, use `MERGE`:

```sql
MERGE INTO app.orders t
USING (
    SELECT order_id,
           customer_id,
           order_date,
           total_amount,
           order_status
    FROM stg_orders
    WHERE batch_id = :batch_id
) s
ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_status = s.order_status,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (
        order_id,
        customer_id,
        order_date,
        total_amount,
        order_status
    )
    VALUES (
        s.order_id,
        s.customer_id,
        s.order_date,
        s.total_amount,
        s.order_status
    );
```

`MERGE` updates existing rows and inserts new rows in a single statement. Define update rules explicitly: for example, whether older files may overwrite newer data, and how to handle two records sharing the same `ORDER_ID` within one batch.

### 9.3. Transactions and rerun capability

Reading an external table does not initiate a transaction locking the file like a database table. When loading staging, DML on staging and target tables follows standard SQL transactions. You can `COMMIT` once the batch is verified or `ROLLBACK` if the database load step fails.

However, `ROLLBACK` does not revert source files, delete bad/log files, or undo actions on external systems. Workflows require batch IDs, processing states, and idempotency mechanisms to avoid duplicate loads when jobs rerun.

A common pattern records batches in a control table:

| Field | Meaning |
|---|---|
| `BATCH_ID` | Unique key of the file receipt |
| `FILE_NAME` | Source filename |
| `FILE_CHECKSUM` | File content verification hash |
| `RECEIVED_AT` | Receipt timestamp |
| `STATUS` | RECEIVED, VALIDATING, LOADED, FAILED, or equivalent state |
| `ROW_COUNT` | Expected/read/loaded record counts |
| `ERROR_COUNT` | Error or rejected record count |
| `COMPLETED_AT` | Completion timestamp |

## 10. Optimizing Performance When Reading External Tables

External tables lack buffer-cached segments and indexes like physical tables. Performance depends on file I/O, record format, access driver, predicates, selected columns, parallel execution, and downstream operations.

### 10.1. Select only required columns

Avoid querying `SELECT *` when only a few columns are needed. Explicit projection reduces data flowing through joins, sorts, and aggregates, and avoids reading/parsing unnecessary wide fields when the driver can optimize column projection.

### 10.2. Apply clear predicates

Filter by batch, date, or status as close to the source as possible:

```sql
SELECT order_id,
       customer_id,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date;
```

The optimizer can push predicates into external row-source processing if the driver and format allow. However, with sequential text files, filtering for few rows does not necessarily mean Oracle reads only part of the file; in many cases the entire file must still be scanned to find matching records.

### 10.3. Parallel query

External tables can participate in parallel queries when configuration and driver support it. You can declare a parallel attribute on the external table or use parallel execution per system policy:

```sql
ALTER TABLE ext_orders PARALLEL 4;
```

Parallelism can speed up reading and processing large files if storage, CPU, and file format allow splitting the work. However, raising degree does not guarantee linear speedup. It can raise concurrent I/O, CPU, process counts, and pressure on shared storage.

Whether a file can be split into chunks depends on record format, driver, file location, and version. Some formats or compressed files cannot be split at arbitrary byte offsets because record boundaries must be preserved. Benchmark with representative data and inspect actual execution plans.

### 10.4. Use staging for repeated queries

If the same file must be joined and aggregated multiple times, repeatedly querying the external table causes repeated file I/O. After validation and normalization, load data into a staging table so you can:

- Create appropriate indexes.
- Gather optimizer statistics.
- Use partitioning for large volumes.
- Enforce constraints and transaction control.
- Reuse data without re-parsing the file on every query.

External tables suit the read/ingest step. Staging tables suit multi-step internal processing and repeated queries.

### 10.5. Execution plans and statistics

You can view the plan:

```sql
EXPLAIN PLAN FOR
SELECT order_id,
       customer_id,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID';
```

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Once the actual query has run and runtime details are needed, use `DBMS_XPLAN.DISPLAY_CURSOR` with appropriate runtime statistics. Compare estimated vs. actual rows, elapsed time, I/O, and external table operations. The optimizer may have less distribution metadata than for physical tables; if external data distribution heavily affects join order, staging into a table with gathered statistics yields more stable plans.

## 11. ORACLE_DATAPUMP External Tables

Besides the text loader, Oracle supports the `ORACLE_DATAPUMP` access driver to read and write files in a proprietary Data Pump format. It is useful for exchanging datasets between databases or unloading data to files without creating standard intermediate table segments.

Conceptual example creating an external table via CTAS to unload data:

```sql
CREATE TABLE orders_unload
ORGANIZATION EXTERNAL (
    TYPE ORACLE_DATAPUMP
    DEFAULT DIRECTORY ext_data_dir
    LOCATION ('orders_export_01.dmp')
)
AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_date >= DATE '2026-10-01';
```

In this case, Oracle writes data to the file in the driver's format. This file is not a general dump file interchangeable with Data Pump `expdp`/`impdp`; it is an external table data file. Another `ORACLE_DATAPUMP` external table with a compatible definition can read that file.

Specific operations and limitations depend on version. Never mix `ORACLE_LOADER` syntax such as CSV delimiters with `ORACLE_DATAPUMP`, as the two drivers have different formats and access parameters.

## 12. Security When Using External Tables

External tables open a path from the database to the server filesystem. Therefore, control both database privileges and OS permissions.

### 12.1. Restrict directories

- Create directory objects pointing only to the exact folder needed.
- Grant `READ` only to schemas that need to read files.
- Grant `WRITE` only when creating log/bad/discard files is genuinely required.
- Avoid broad directories such as home directories or folders containing unrelated sensitive data.
- Never grant `CREATE ANY DIRECTORY` to runtime accounts.

### 12.2. Control file sources

Files must originate from trusted sources or be verified before processing. If external applications write files, validate:

- Filename and batch ID.
- Maximum size and expected record count.
- Encoding, delimiter, headers, and schema version.
- Checksums or signatures if required by procedure.
- Anomalous content, oversized fields, and control characters.

Never interpolate user-supplied filenames directly into DDL or arbitrary paths. Directory objects constrain logical paths, yet directory creation/alteration privileges and filesystem permissions must still be strictly governed.

### 12.3. Protect logs and bad files

Log/bad/discard files can contain sensitive data or malformed input values. Apply appropriate permissions, retention, and cleanup. Do not leave error files sitting long-term in directories readable by broad OS users.

## 13. Managing File Changes and External Table Definitions

External tables store metadata inside the database while files can change independently. Operators must therefore manage schema versions and file lifecycles.

### 13.1. File structure changes

If a source system adds columns, reorders columns, changes delimiters, or alters date formats, an old external table definition may misread or reject data. Version file schemas—for instance, `ORDERS_V1`, `ORDERS_V2`—or include version in batch metadata.

Never silently change field order in a CSV while leaving the external table definition unchanged. Coordinate changes between file producers and database consumers.

### 13.2. LOCATION and file replacement

`LOCATION` lists the filename or list of files read by the external table. Overwriting file contents under the same name immediately alters subsequent query results. External tables do not maintain a data snapshot like physical tables.

To preserve rerunnability, store original files under immutable batch names and record checksums. If reprocessing is needed, use the exact original file and batch ID rather than an overwritten file.

### 13.3. Dropping or altering external tables

You can remove an external table definition with `DROP TABLE`. This drops the metadata object inside the database; do not assume it deletes the source files. File management remains the responsibility of filesystem or job orchestration workflows.

## 14. Data Dictionary Views for External Tables

Oracle provides metadata views to inspect external tables and configurations:

| View | Contents |
|---|---|
| `USER_EXTERNAL_TABLES` | External tables in the current schema |
| `ALL_EXTERNAL_TABLES` | External tables whose metadata the user can view |
| `DBA_EXTERNAL_TABLES` | External tables across the database |
| `USER_EXTERNAL_LOCATIONS` | File locations of external tables in the current schema |
| `ALL_EXTERNAL_LOCATIONS` | Viewable file locations |
| `DBA_EXTERNAL_LOCATIONS` | File locations across the database |
| `USER_TAB_COLUMNS` / `ALL_TAB_COLUMNS` | Column metadata of external tables |
| `ALL_DIRECTORIES` / `DBA_DIRECTORIES` | Directory objects and paths |

Example inspecting external tables in the current schema:

```sql
SELECT table_name,
       type_name,
       default_directory_name,
       reject_limit
FROM user_external_tables
ORDER BY table_name;
```

Inspect declared files:

```sql
SELECT table_name,
       location
FROM user_external_locations
ORDER BY table_name, location;
```

Column names may vary slightly across versions; verify the data dictionary description in your target environment when building long-lived administrative scripts.

## 15. Common Errors and Diagnostics

| Symptom | Possible cause | What to check |
|---|---|---|
| `ORA-29913` when accessing external table | Error in external table access driver or file operation | Check accompanying errors, log file, directory, and OS permissions |
| `ORA-29400` | Data cartridge/driver wrapper error | Read accompanying error details and loader log |
| `ORA-01031` | Missing database privilege on directory or other required privilege | Check `READ`/`WRITE` on DIRECTORY and object creation privileges |
| File not found | Wrong `LOCATION`, directory path, or file missing on database server | Check `ALL_DIRECTORIES`, OS path, and exact filename |
| Cannot read file despite READ grant | Oracle OS account lacks read permission or mount unavailable | Check permissions, owner, mount, and traverse permissions on parent folders |
| Many rows rejected | Wrong delimiter, quotes, record terminator, encoding, or data type | Read log/bad file and compare access parameters with sample file |
| Dates/numbers converted incorrectly | Mismatched NLS settings or wrong format mask | Specify format explicitly, check decimal/group separators |
| Vietnamese characters garbled | Mismatched file character set | Identify encoding and declare the matching character set |
| Query is slow | Large file, I/O, unsplittable format, expensive conversions or joins | Inspect plan, row counts, I/O, parallelism, and consider staging |
| Works on one RAC node yet fails on another | File missing from shared path or differing mount permissions | Verify file accessibility from every node eligible to run the service |

When troubleshooting, check in order:

1. External table metadata: are owner, table, driver, and `LOCATION` correct?
2. Directory object: are name and path accurate?
3. Database privileges: does the user have required `READ` and `WRITE`?
4. OS permissions: can Oracle processes read/write the folder and file?
5. File format: do delimiter, record terminator, quotes, encoding, field lengths, and date/number masks match?
6. Log/bad file: which exact records and errors did the loader report?
7. Runtime plan: are there repeated scans, I/O bottlenecks, or oversized joins/aggregates?

Never fix errors by granting overly broad filesystem or database privileges. Pinpoint the exact layer denying access.

## 16. Practical File Ingestion Workflow

An external-table ingestion workflow can be organized as follows:

1. **Receive file:** deliver the file into a permissioned landing folder; avoid using the final filename until writing finishes completely.
2. **Verify file:** check size, checksum, encoding, header, schema version, and expected record count.
3. **Publish file:** atomically rename/move to the immutable filename used by the external table.
4. **Create or select batch metadata:** record `BATCH_ID`, filename, checksum, and status `RECEIVED`.
5. **Query external table:** verify row counts, format, and sample data.
6. **Validate:** check conversions, mandatory fields, value domains, duplicates, and referential integrity.
7. **Isolate errors:** write invalid rows and reasons into a reject table; retain bad/log files per retention policy.
8. **Load staging:** insert valid rows into a staging table within a controlled transaction.
9. **Apply business logic:** use `MERGE` or appropriate DML to update target tables.
10. **Reconcile:** compare source, valid, invalid, staging, and final target counts.
11. **Mark complete:** update batch status and processing timestamp.
12. **Archive/cleanup:** move source files to archive per policy; delete only when retention and audit rules allow.

This workflow turns external tables into a controlled pipeline component rather than an ad-hoc `SELECT` tied to unmonitored changing files.

## 17. Complete Practice Lab

### Step 1: Create directory

DBA creates a directory pointing to the prepared server folder:

```sql
CREATE OR REPLACE DIRECTORY inbound_orders
AS '/u01/app/oracle/inbound/orders';
```

### Step 2: Grant privileges

```sql
GRANT READ, WRITE ON DIRECTORY inbound_orders TO app_loader;
```

### Step 3: Place sample file

File `orders_batch_001.csv`:

```csv
ORDER_ID,CUSTOMER_ID,ORDER_DATE,AMOUNT,STATUS
1001,501,2026-10-01,1250.50,PAID
1002,502,2026-10-02,800.00,NEW
1003,501,2026-10-03,420.75,PAID
```

### Step 4: Create raw external table

```sql
CREATE TABLE ext_orders_batch (
    order_id_txt      VARCHAR2(30),
    customer_id_txt   VARCHAR2(30),
    order_date_txt    VARCHAR2(30),
    amount_txt        VARCHAR2(30),
    status_txt        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY inbound_orders
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        SKIP 1
        BADFILE 'orders_batch_001.bad'
        LOGFILE 'orders_batch_001.log'
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_txt     CHAR(30),
            customer_id_txt  CHAR(30),
            order_date_txt   CHAR(30),
            amount_txt       CHAR(30),
            status_txt       CHAR(20)
        )
    )
    LOCATION ('orders_batch_001.csv')
)
REJECT LIMIT 10;
```

### Step 5: Count and inspect data

```sql
SELECT COUNT(*) AS source_rows
FROM ext_orders_batch;
```

```sql
SELECT *
FROM ext_orders_batch
FETCH FIRST 10 ROWS ONLY;
```

If deterministic ordering is required, add `ORDER BY`; external tables do not guarantee result order matches physical file order.

### Step 6: Validate data

```sql
SELECT COUNT(*) AS invalid_rows
FROM ext_orders_batch
WHERE VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 0
   OR VALIDATE_CONVERSION(TRIM(customer_id_txt) AS NUMBER) = 0
   OR VALIDATE_CONVERSION(
          TRIM(order_date_txt) AS DATE,
          'YYYY-MM-DD'
      ) = 0
   OR VALIDATE_CONVERSION(
          TRIM(amount_txt) AS NUMBER,
          '999999999999D99',
          'NLS_NUMERIC_CHARACTERS=''.,'''
      ) = 0;
```

This example checks convertibility. Add checks for NULLs, negative amounts, invalid statuses, duplicates, and missing customer IDs.

### Step 7: Load into staging

After validating rows, use `INSERT INTO ... SELECT ...` to load into a staging table built with proper data types and constraints. Use a batch ID for traceability and to ensure reruns do not duplicate loads.

### Step 8: Reconcile and save batch

Record rows read, valid rows, errored rows, staging rows, and rows applied to target tables. Transition batch status to `COMPLETED` only when counts satisfy reconciliation rules.

## 18. Misconceptions to Avoid

| Misconception | Correct understanding |
|---|---|
| External tables store files inside the database | Files stay outside; the database stores metadata to read them |
| Creating a DIRECTORY creates an OS folder | DIRECTORY is only an object mapping to a server path |
| Granting READ on DIRECTORY is enough | Oracle's OS account must also be able to read the file |
| A file on a client machine is readable by the database | The file must reside at a location accessible by the database server |
| External tables support DML like regular tables | With `ORACLE_LOADER`, external tables are mainly read-only; load into staging for writes |
| Every SELECT uses data cached in a table segment | Oracle reads the file via the access driver; file edits can change query results |
| Filtering few rows with WHERE guarantees reading few bytes | Sequential text files may still require scanning to locate matching records |
| REJECT LIMIT UNLIMITED makes bad data valid | It only permits exceeding the reject threshold; invalid records still require handling |
| Bad files capture all business errors | Business errors require dedicated validation and logging |
| LOCATION guarantees file immutability | External workflows must manage file replacement and batching |
| External tables guarantee file order | Results have no guaranteed order without `ORDER BY` |
| RAC only needs the file on one node | Every node eligible to execute queries must access the file per configuration |

External tables bring file data into Oracle's SQL world without immediately loading it into table segments. When directories, drivers, record formats, and field mappings are defined accurately, you can filter, join, aggregate, and validate data directly with SQL. In production workflows, use external tables as an input read layer, separate format validation from business validation, load valid data into staging, and manage files as immutable batches. This architecture harnesses Oracle SQL while preserving traceability, reconciliation, and safe reruns.
