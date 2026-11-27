# INCLUDE, EXCLUDE, QUERY, and Selecting Data Scope

Oracle Data Pump is Oracle Database's toolset for exporting and importing data, commonly invoked via **expdp** and **impdp**. A Data Pump job can process an entire database, one or more schemas, a set of tables, a tablespace, or a selected set of objects. Beyond selecting objects, Data Pump can also control which metadata is exported/imported and, during export, which table rows are written into the dump file.

Four mechanisms must be distinguished:

- **Selecting job mode/scope** using parameters such as `FULL`, `SCHEMAS`, `TABLES`, `TABLESPACES`, or `TRANSPORT_TABLESPACES`. This step defines the initial dataset the job considers.
- **INCLUDE** specifies object types or specific objects to include in the job. This is a metadata filter.
- **EXCLUDE** omits object types or specific objects from the job. This is also a metadata filter.
- **QUERY** filters table rows during Data Pump Export using an SQL condition. It determines which rows are written to the dump file, not which metadata types are selected.

Understanding the exact order and scope of these mechanisms helps create purpose-built dump files, reduce size, shorten export/import time, and avoid omitting dependent objects.

## 1. Choose Job Scope Before Filtering Objects

Data Pump provides multiple export/import modes. The mode defines the initial set of objects; INCLUDE and EXCLUDE further narrow the metadata set within that scope.

| Mode | Parameter | Scope |
|---|---|---|
| Full database | `FULL=YES` | Objects within full export/import scope that the account is authorized to process |
| Schema | `SCHEMAS=HR,SALES` | Objects belonging to the specified schemas |
| Table | `TABLES=HR.EMPLOYEES,HR.DEPARTMENTS` | Specified tables along with related metadata and data per job |
| Tablespace | `TABLESPACES=USERS,APP_DATA` | Objects belonging to the specified tablespaces per Data Pump rules |
| Transportable tablespace | `TRANSPORT_TABLESPACES=...` | Moves a tablespace set via the transportable mechanism |

Mode parameters represent different ways of defining scope. A job cannot arbitrarily combine `FULL`, `SCHEMAS`, and `TABLES` as independent filters. Choose the mode matching your goal before adding filters.

Example exporting a schema:

~~~text
SCHEMAS=HR
~~~

Exporting two tables:

~~~text
TABLES=HR.EMPLOYEES,HR.DEPARTMENTS
~~~

Exporting the full database:

~~~text
FULL=YES
~~~

Full export requires appropriate privileges, typically a Data Pump full-database role such as `DATAPUMP_EXP_FULL_DATABASE`. Actual required privileges also depend on objects and version. Do not assume a schema owner account can run a full database export.

### Object scope vs. row scope

Choosing `TABLES=HR.ORDERS` means the job processes the ORDERS table in the HR schema. It does not automatically restrict rows by date or status. If only a subset of rows is needed, a row filter mechanism such as QUERY during export is required.

Conversely, `QUERY` does not automatically select additional schemas or tables. It applies only to table data within the already-selected job scope. Define the mode first, then use INCLUDE/EXCLUDE and QUERY as appropriate.

## 2. INCLUDE: Include Only Selected Objects in the Job

`INCLUDE` restricts which object types or object names are included in the job. The object type name must be a valid object path in the running mode.

Example schema export including only tables whose names start with EMP:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"LIKE 'EMP%'"
~~~

Example schema export taking only two tables:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"IN ('EMPLOYEES','DEPARTMENTS')"
~~~

The examples above filter metadata by the TABLE object path and table name. Usable object paths depend on the mode and Oracle version.

### How does INCLUDE filter object types?

If you specify:

~~~text
INCLUDE=TABLE
~~~

Data Pump brings tables into the job. Necessary dependent metadata for the selected objects may be included according to Data Pump dependency rules, such as components required to create the tables. Therefore, INCLUDE should not be viewed as an isolated file list containing only a single metadata line type.

To control additional object types, you can specify multiple INCLUDE filters in a parameter file, for example:

~~~text
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
INCLUDE=PROCEDURE
~~~

INCLUDE filters can be used to specify the exact set of object types to process. However, object dependencies can still influence exported/imported metadata. When designing a job that takes only certain object types, read the log and inspect the dump with SQLFILE before importing into a target system.

### INCLUDE by object name

Name expressions such as `LIKE` or `IN` can be used in object filters:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"LIKE 'EMP%'"
~~~

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"IN ('EMPLOYEES','DEPARTMENTS')"
~~~

For object names created in Oracle without double quotes, names are typically stored in uppercase. Filter expressions must match how names are stored in the data dictionary. For case-sensitive names created with quoted identifiers, verify the exact stored name before writing filters.

## 3. EXCLUDE: Omit Objects from the Job

`EXCLUDE` removes an object type or specific objects from the job. This mechanism is useful when you want to export/import nearly the entire scope while skipping certain unnecessary objects.

Example schema export skipping audit and staging tables:

~~~text
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
~~~

Example exporting a schema while excluding optimizer statistics metadata:

~~~text
SCHEMAS=HR
EXCLUDE=STATISTICS
~~~

Object path names must be valid in the corresponding mode. Not every object type can be filtered in every mode.

### EXCLUDE and dependencies

When excluding an object, Data Pump may also exclude metadata dependent on that object. For example, if a table is excluded, objects depending on that table may be omitted from the job per dependency rules. This can affect indexes, constraints, triggers, grants, or related metadata.

Therefore, if you need to omit a specific metadata type while keeping the table, choose the exact appropriate object path and verify the output. Do not assume excluding one object path leaves dependent components unaffected.

### INCLUDE and EXCLUDE cannot be used together in one job

A single Data Pump job does not allow specifying both INCLUDE and EXCLUDE simultaneously. Choose one strategy:

- Use INCLUDE when you want to explicitly state which object types to process.
- Use EXCLUDE when you want to process a broad scope and omit a few unnecessary objects.

For example, if the goal is exporting the HR schema while omitting audit tables, use SCHEMAS with EXCLUDE. If the goal is exporting only tables, views, and procedures, use SCHEMAS with INCLUDE.

## 4. Object Paths and Finding Valid Filter Names

Object type names in INCLUDE/EXCLUDE are Data Pump object paths. They do not always match familiar SQL object type names. Some object paths have specific names or hierarchies depending on the export mode.

Oracle provides views describing object paths by mode:

- `DATABASE_EXPORT_OBJECTS`: object paths usable in full database export/import.
- `SCHEMA_EXPORT_OBJECTS`: object paths usable in schema mode.
- `TABLE_EXPORT_OBJECTS`: object paths usable in table mode.

You can query the list of object paths in the database:

~~~sql
SELECT object_path,
       comments
FROM   schema_export_objects
ORDER BY object_path;
~~~

For full export:

~~~sql
SELECT object_path,
       comments
FROM   database_export_objects
ORDER BY object_path;
~~~

For table mode:

~~~sql
SELECT object_path,
       comments
FROM   table_export_objects
ORDER BY object_path;
~~~

These views help identify exact object path names and descriptions in the current release. If an account cannot access the views, a DBA can grant appropriate read privileges or run the query using an administrative account.

Do not guess object paths from dictionary view names like DBA_TABLES or DBA_INDEXES. Use Data Pump's object path lists to avoid invalid filter errors.

## 5. QUERY: Filtering Data Rows During Export

`QUERY` allows Data Pump Export to select a subset of table rows using an SQL condition. It affects table data; table metadata is still processed according to the mode and other filters.

Example exporting only open orders:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

Example filtering by date:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
~~~

Example combining multiple conditions:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND ORDER_DATE >= DATE '2026-01-01'"
~~~

General syntax:

~~~text
QUERY=[schema.][table_name:] query_clause
~~~

Where `query_clause` is typically a valid WHERE clause. For a table-specific query, specify the table name explicitly; when working across multiple schemas, include the schema to avoid name ambiguity. QUERY is a Data Pump Export (`expdp`) parameter; do not use it as an object metadata filter in Import.

### QUERY does not replace TABLES or SCHEMAS

`QUERY` does not define the object scope. Example:

~~~text
SCHEMAS=HR
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

The job remains a schema export. QUERY filters only the specified table's data according to syntax and applicable conditions; other tables in the schema do not automatically disappear just because they lack their own QUERY.

For simple cases, use TABLES mode to clearly restrict the target table being filtered:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

This makes the job easy to understand, easy to verify, and reduces the risk of accidentally exporting unneeded tables.

### QUERY filters rows, not columns

QUERY is a row-selection condition. Example:

~~~text
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

selects rows where STATUS is OPEN, while still exporting the table's columns per table structure. If you need to omit columns or alter data structure, design a separate approach such as a view, staging table, REMAP_DATA, or post-import SQL operations.

### SQL conditions and data types

The QUERY condition must be valid for the source table and database. Pay attention to:

- Using data-type-appropriate literals, such as DATE literals instead of NLS-dependent date strings.
- Using column names matching the table and identifier naming.
- Checking NULL semantics when using comparison conditions.
- Using parentheses in multi-operator conditions to make logical precedence explicit.
- If using functions or expressions, confirming the expression runs on the source database.
- Never interpolating unvalidated user input into dynamically constructed QUERY strings.

Example of a safer date condition:

~~~text
QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01' AND ORDER_DATE < DATE '2027-01-01'"
~~~

The condition above creates a half-open date range, suitable for DATE columns that may contain a time component.

## 6. Comparing INCLUDE, EXCLUDE, and QUERY

| Criterion | INCLUDE | EXCLUDE | QUERY |
|---|---|---|---|
| Target | Object type or object name | Object type or object name | Table data rows |
| Purpose | Select only necessary metadata | Omit unnecessary metadata | Extract a subset of rows by condition |
| Used in | Data Pump Export and Import | Data Pump Export and Import | Data Pump Export |
| Example | `INCLUDE=TABLE` | `EXCLUDE=STATISTICS` | `QUERY=ORDERS:"WHERE STATUS='OPEN'"` |
| Alters metadata scope? | Can limit processed metadata | Can omit metadata from job | No; only filters exported rows |
| Combines with mode? | Yes | Yes | Yes, within supported modes/scopes |

A helpful mnemonic:

- Mode answers: **which data region does the job consider?**
- INCLUDE/EXCLUDE answers: **which object metadata is processed?**
- QUERY answers: **which table rows are exported?**
- CONTENT answers: **does the job process metadata, table data, or both?**

## 7. CONTENT and Related Scope Parameters

`CONTENT` controls what kind of content Data Pump Export/Import processes:

| CONTENT | Meaning |
|---|---|
| ALL | Metadata and table data |
| METADATA_ONLY | Metadata, without exporting table rows |
| DATA_ONLY | Table data, without exporting metadata |

Example exporting metadata only for a schema:

~~~text
SCHEMAS=HR
CONTENT=METADATA_ONLY
~~~

Example exporting data only for a table:

~~~text
TABLES=HR.ORDERS
CONTENT=DATA_ONLY
~~~

`CONTENT=DATA_ONLY` does not filter rows on its own. To subset rows, use QUERY during export when supported by mode and configuration. Similarly, `CONTENT=METADATA_ONLY` does not mean taking only certain columns; it omits table data from the job.

### TABLES and partitions

In table mode, you can specify a partition or subpartition using Data Pump syntax. Example:

~~~text
TABLES=SH.SALES:SALES_Q1_2026
~~~

Partition selection is useful when moving data by period or splitting jobs into smaller units. Confirm the partition name exists, access privileges, and version-supported syntax.

Selecting a partition and using QUERY operate at two different levels: partition selection defines the physical/logical data segment processed; QUERY filters rows within the exported table data scope. Verify specific combination rules in your Oracle version.

## 8. Practical Example: Exporting a Set of Tables with INCLUDE

Suppose you need to export the HR schema but want only tables and views in scope. You can use a parameter file:

**hr_objects.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects_%U.dmp
LOGFILE=hr_objects.log
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
PARALLEL=2
METRICS=YES
~~~

Run:

~~~bash
expdp system@ORCL PARFILE=hr_objects.par
~~~

The job specifies schema HR and the INCLUDEd object paths. Necessary dependent metadata may be processed per dependency rules. Inspect the log to verify processed object counts and use SQLFILE if you want to review DDL before import.

## 9. Practical Example: Exporting a Schema While Excluding Unneeded Tables

Suppose schema HR contains business tables and temporary/audit tables. You need to export the entire schema except two tables that do not need to be moved.

**hr_without_audit.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_clean_%U.dmp
LOGFILE=hr_clean.log
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
PARALLEL=2
METRICS=YES
~~~

Run:

~~~bash
expdp system@ORCL PARFILE=hr_without_audit.par
~~~

When EXCLUDEing a table, note that dependent objects may also be omitted per dependency rules. After export, check the log and expected DDL content to ensure the remaining objects still satisfy deployment requirements.

## 10. Practical Example: Exporting a Subset of Table Rows

Suppose you only need to bring OPEN orders since the beginning of 2026 into a reporting system.

**orders_open.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_open_%U.dmp
LOGFILE=orders_open.log
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND ORDER_DATE >= DATE '2026-01-01'"
PARALLEL=2
METRICS=YES
~~~

Run:

~~~bash
expdp system@ORCL PARFILE=orders_open.par
~~~

When importing the dump file, Data Pump creates or loads the table from the dump contents. The exported rows are precisely those matching the QUERY condition. Table metadata does not transform into a conditional view; this is a subset data export of the table.

If you need multiple different condition sets, create separate export jobs or design an appropriate staging workflow. Avoid cramming multiple unrelated conditions into a single unchecked QUERY.

## 11. Import and the Impact of INCLUDE/EXCLUDE

Data Pump Import (`impdp`) also supports INCLUDE and EXCLUDE to select metadata imported from the dump file. Initial import scope is set by FULL, SCHEMAS, TABLES, or an equivalent mode; filters then limit which objects are created or processed.

Example importing a schema while creating only tables and views:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects_%U.dmp
LOGFILE=hr_import.log
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
~~~

Example importing a schema while excluding a table:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_full_%U.dmp
LOGFILE=hr_import_no_audit.log
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
~~~

During import, INCLUDE/EXCLUDE control object metadata in the dump. If the dump was exported with QUERY, rows already filtered out during export will not magically reappear during import.

QUERY is an Export row-filtering mechanism. If you need to import a different row subset than what is already in the dump, design a separate data-processing step, such as importing into a staging schema and running INSERT ... SELECT with WHERE, or creating a properly filtered dump from the source.

### Checking DDL before import using SQLFILE

You can generate an SQL file containing the DDL Data Pump plans to execute:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects.dmp
SQLFILE=hr_preview.sql
SCHEMAS=HR
~~~

Run:

~~~bash
impdp system@ORCL PARFILE=preview.par
~~~

SQLFILE lets you inspect DDL statements generated from the dump and current filters. It does not execute those DDL statements and does not replace checking table data contents. This is a useful way to verify object scope before importing into a target database.

## 12. Combining Filters Without Confusing Scope

You can visualize Data Pump scope in layers:

~~~text
Mode / Job scope
(FULL, SCHEMAS, TABLES, TABLESPACES)
          |
          v
Metadata filters
(INCLUDE or EXCLUDE)
          |
          v
Selected objects and dependencies
          |
          v
Table data
(CONTENT and QUERY in Export)
          |
          v
Dump file / Import target
~~~

For example, if the goal is exporting the ORDERS table, taking only necessary metadata and only OPEN orders:

1. Select TABLES mode with HR.ORDERS.
2. If object types need filtering, use INCLUDE or EXCLUDE appropriately.
3. Use QUERY to select rows with STATUS = 'OPEN'.
4. Select CONTENT=ALL if both metadata and data are needed.
5. Inspect logs, dump, and DDL before import.

Do not use EXCLUDE to solve row-filtering problems, or use QUERY to omit indexes/triggers. The two filter types operate on different layers.

## 13. Quoting and Parameter Files

INCLUDE, EXCLUDE, and QUERY expressions often contain double quotes, single quotes, commas, and special characters. How shells handle quotes differs between Linux/Unix and Windows. Therefore, parameter files are usually easier to control than passing complex filters directly on the command line.

Example parameter file:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders.log
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND AMOUNT >= 1000"
~~~

Then invoke:

~~~bash
expdp system@ORCL PARFILE=orders.par
~~~

Key notes:

- Use double quotes around the filter expression to preserve the condition string.
- Use single quotes for internal SQL literals.
- If a condition contains single quotes inside a value, escape them according to SQL syntax.
- Do not arbitrarily append a semicolon at the end of a QUERY value if it alters the WHERE string.
- On Windows, PowerShell and Command Prompt have different quoting rules; test using a parameter file.
- Protect parameter files if they contain credentials. Prefer Oracle Wallet or an appropriate authentication mechanism instead of writing plaintext passwords in files.

## 14. Verifying Export/Import Scope

Do not rely solely on the job finishing with a success status. Verify actual object scope and row counts.

### Reading Data Pump logs

Enable METRICS for additional object count and processing time details:

~~~text
METRICS=YES
LOGTIME=ALL
~~~

The log shows processed objects, errors, warnings, and job progress. When a filter fails to match an object path or object name, the log is usually the first place to spot that the actual scope differs from expectations.

### Reviewing planned DDL

Use `impdp ... SQLFILE=...` to write DDL to an inspection file. Compare the list of tables, indexes, constraints, triggers, sequences, packages, and required objects against migration requirements.

### Checking row counts after import

After import, compare row counts on source and target using the exact QUERY condition. For example, on the source:

~~~sql
SELECT COUNT(*)
FROM   hr.orders
WHERE  status = 'OPEN'
AND    order_date >= DATE '2026-01-01';
~~~

On the target:

~~~sql
SELECT COUNT(*)
FROM   hr.orders;
~~~

If the dump was exported with the condition above and no other filtering/transformation occurred, the row count in the target table should match the exported row count. For partitioned tables or transform workflows, compare per exact partition scope and applied conditions.

### Checking object metadata

Cross-check critical objects using data dictionary views such as DBA_TABLES, DBA_INDEXES, DBA_CONSTRAINTS, DBA_TRIGGERS, DBA_OBJECTS, and DBA_TAB_PRIVS. Choose views matching available privileges. For invalid objects after import, check status and recompile according to deployment procedures.

## 15. Common Errors and Troubleshooting

### ORA-39001 or invalid filter errors

Possible causes include an incorrect object path, malformed INCLUDE/EXCLUDE expression, mismatched object name, or a filter unsupported in the current mode. Look up the object path from the export objects view for the exact mode and check quoting.

### More objects exported than expected

Check the initial mode, INCLUDE/EXCLUDE, object dependencies, and how name expressions were applied. If the goal is only a specific set of tables, consider using TABLES mode to restrict scope first.

### Table has metadata but zero data rows

The job may have used CONTENT=METADATA_ONLY, the table may have no rows matching QUERY, or table data may fall outside job scope. Check CONTENT, QUERY, the log, and source row counts.

### QUERY raises an SQL error

Check column names, data types, date literals, quotes, and the WHERE expression. Run the corresponding SQL condition directly on the source database before exporting. If the expression references complex columns or functions, confirm privileges and execution context.

### Import misses dependent objects

Review filters and dependency rules. Excluding a table or object path can also exclude dependent metadata. Use SQLFILE to preview planned DDL, adjust filters, and regenerate the dump or rerun import per plan.

### Filter is correct yet the job runs slowly

INCLUDE/EXCLUDE only reduces metadata work within applicable scope; QUERY may still need to scan large amounts of data to evaluate the condition. Check the execution plan of the source condition, indexes, partition pruning, dump size, PARALLEL, and I/O capacity. Increasing PARALLEL does not guarantee faster execution if storage or CPU is already saturated.

## 16. Designing a Filtered Data Pump Job

1. **Define the objective.** Do you need the whole database, schemas, tables, or partitions? Metadata, data, or both?
2. **Select the mode.** Choose one primary scope such as FULL, SCHEMAS, or TABLES.
3. **List required objects.** Identify required tables, views, sequences, packages, procedures, triggers, constraints, indexes, and grants.
4. **Choose INCLUDE or EXCLUDE.** Use INCLUDE when the list of object types to process is clear; use EXCLUDE when omitting only a few objects from a broad scope.
5. **Check dependencies.** Look up object paths, understand dependency relationships, and preview DDL with SQLFILE when needed.
6. **Define row filters.** If only a subset of rows is needed, use QUERY in Data Pump Export and test the WHERE condition on the source.
7. **Select CONTENT.** Decide whether to export/import metadata, data, or both.
8. **Prepare a parameter file.** Keep filters and quoting out of the command line; protect credentials.
9. **Run a test job and inspect logs.** Verify objects, row counts, warnings, and errors.
10. **Verify on target.** Use SQLFILE, the data dictionary, and row-count reconciliation matching the chosen conditions.

## 17. Key Principles When Selecting Scope

- Mode defines the initial broad scope; INCLUDE/EXCLUDE filter metadata inside that scope.
- INCLUDE and EXCLUDE are mutually exclusive strategies in a single job; do not specify both simultaneously.
- Object paths must be valid for the mode. Look them up in DATABASE_EXPORT_OBJECTS, SCHEMA_EXPORT_OBJECTS, or TABLE_EXPORT_OBJECTS.
- Dependencies can cause related metadata to be pulled in or omitted alongside selected objects.
- QUERY filters table data rows in Data Pump Export; it does not filter object types and does not replace TABLES/SCHEMAS.
- CONTENT controls whether metadata/data is processed, not row-filtering criteria.
- Use parameter files to manage quoting and reuse configurations.
- Read logs and inspect SQLFILE to confirm scope before importing into critical systems.
- Reconcile row counts between source and target using exact WHERE conditions, partitions, and job scope.
- Store parameter files, logs, and filter details with migration records so jobs can be reproduced or audited.

Accurate Data Pump scoping combines mode, object filters, and row filters. When each parameter is applied at the proper layer, export/import jobs remain clear, verifiable, and precisely aligned with metadata and data movement requirements.
