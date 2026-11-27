# Renaming, Changing Data Types, Adding Constraints, and Handling Dependent Objects

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Change and Upgrade  
> **Objective:** Perform controlled Oracle schema changes; rename tables/columns, convert data types, add or modify constraints; identify dependent objects and applications; understand DDL impact, invalidation, indexes, views, triggers, PL/SQL, and synonyms; plan backward compatibility, testing, cutover, and recovery after changes.

## 1. The Schema Is a Contract Between Database and Application

A schema is not just a list of tables and columns. It is a contract shared by many components:

- Java applications, Spring Boot, JPA/Hibernate, and batch jobs.
- Views, materialized views, triggers, packages, procedures, and functions.
- Foreign keys, primary keys, unique/check constraints, and indexes.
- Synonyms, database links, and stored SQL.
- ETL, BI/reporting, Data Pump, scheduler jobs, and integration systems.
- Monitoring, auditing, replication, and migration tools.

A seemingly minor change like renaming a column can break SQL queries in applications, views, or packages. Changing a data type can alter comparisons, sorting, calculations, index access, and JDBC mappings. Adding a constraint can fail because historical data violates the rule.

Therefore, schema evolution must answer four questions:

1. What is the exact change and why is it needed?
2. Which objects, applications, and processes depend on the changed part?
3. How do we deploy it while remaining compatible during transition?
4. How do we verify and recover if a step fails?

**Oracle DDL performs implicit commits.** Never assume a migration containing multiple DDL statements will roll back atomically like a DML transaction.

## 2. Classifying Changes Before Deployment

| Change Category | Examples | Primary Risks |
|---|---|---|
| Object rename | `RENAME TABLE`, `RENAME COLUMN` | SQL, views, packages, and apps referencing the old name |
| Increase/decrease length | `VARCHAR2(100)` to `VARCHAR2(300)` | Storage, index key length, client validation |
| Data type change | `VARCHAR2` to `NUMBER`, `DATE` to `TIMESTAMP` | Data conversion, precision, nulls, indexes, and constraints |
| Add constraint | `NOT NULL`, `CHECK`, `UNIQUE`, `FK` | Invalid existing data, locks, and validation cost |
| Modify constraint | `ENABLE`/`DISABLE`, `VALIDATE`/`NOVALIDATE` | Different enforcement between old and new data |
| Key change | Change PK/UK or FK | Referential relationships, indexes, and applications |
| Major structural change | Split tables, merge tables, partitioning | Data migration, cutover, and multi-version compatibility |

Do not apply the exact same workflow to every change. Renames mainly impact metadata and dependencies; data type conversions and constraint validations may scan or update massive data volumes.

## 3. Surveying the Schema Before Modifying It

Before writing `ALTER TABLE`, capture the current state to establish a baseline and know what to verify afterward.

### 3.1. Confirm Database and Schema

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Confirm you are connected to the right database, PDB, schema, and environment. Many migration incidents begin by running the right script against the wrong service or container.

### 3.2. Save Current DDL

Use `DBMS_METADATA` to extract object definitions before changing them:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'ORDERS',
           'APP_OWNER'
       )
FROM dual;
~~~

You can extract DDL for indexes, constraints, or views using the corresponding object type. Save the output to the change record or internal version control per security policy.

`DBMS_METADATA` is evidence of the current definition, not a data backup, and does not replace RMAN backups.

### 3.3. List Columns and Data Types

~~~sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       data_precision,
       data_scale,
       nullable,
       data_default
FROM dba_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
~~~

Metadata columns distinguish byte length from character length. For `VARCHAR2`, `CHAR_USED` indicates `BYTE` vs. `CHAR` length semantics.

### 3.4. List Constraints

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       delete_rule,
       search_condition
FROM dba_constraints
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_type, constraint_name;
~~~

Common constraint types:

- `P`: Primary key.
- `U`: Unique.
- `R`: Referential integrity/foreign key.
- `C`: Check constraint, including `NOT NULL` represented in dictionary metadata.

Inspect columns belonging to constraints:

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       column_name,
       position
FROM dba_cons_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_name, position;
~~~

### 3.5. List Indexes

~~~sql
SELECT owner,
       index_name,
       index_type,
       table_name,
       uniqueness,
       status,
       visibility,
       tablespace_name
FROM dba_indexes
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY index_name;
~~~

Inspect index columns:

~~~sql
SELECT index_owner,
       index_name,
       table_owner,
       table_name,
       column_name,
       column_position,
       descend
FROM dba_ind_columns
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY index_name, column_position;
~~~

Do not conclude an index remains optimal simply because its status is `VALID`. After data type changes or data shifts, evaluate execution plans and statistics.

## 4. Finding Dependent Objects

Oracle maintains dependency metadata for many object types. `DBA_DEPENDENCIES` is a starting point, not an exhaustive finder for every possible reference.

### 4.1. DBA_DEPENDENCIES

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM dba_dependencies
WHERE referenced_owner = 'APP_OWNER'
  AND referenced_name = 'ORDERS'
ORDER BY owner, type, name;
~~~

Results reveal views, packages, procedures, functions, triggers, or other objects referencing the table.

Dependency metadata cannot detect dynamically concatenated SQL strings, SQL inside application codebases, external ETL pipelines, or queries generated by BI tools.

### 4.2. Search PL/SQL Source

~~~sql
SELECT owner,
       name,
       type,
       line,
       text
FROM dba_source
WHERE UPPER(text) LIKE '%ORDERS%'
ORDER BY owner, name, type, line;
~~~

This is a raw text search. It can yield false positives from comments or string literals and miss references split across lines or built dynamically.

### 4.3. Inspect Views

~~~sql
SELECT owner,
       view_name,
       text_length
FROM dba_views
WHERE owner IN ('APP_OWNER', 'REPORT_OWNER')
ORDER BY owner, view_name;
~~~

Read `DBA_VIEWS.TEXT` or use `DBMS_METADATA.GET_DDL` to examine exact definitions. Check both direct views and nested views.

### 4.4. Inspect Synonyms

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY owner, synonym_name;
~~~

A synonym is an object name alias. It does not automatically preserve compatibility when the target object is renamed or moved across schemas. Check private/public synonyms, target owners/names, and database links if present.

### 4.5. Check Triggers

~~~sql
SELECT owner,
       trigger_name,
       table_owner,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM dba_triggers
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY owner, trigger_name;
~~~

Triggers may reference renamed columns or changed data types. Inspect trigger bodies, compound triggers, package calls inside triggers, and cross-table side effects.

### 4.6. External Dependencies Outside the Database

Beyond the data dictionary, search:

- Source code repositories and ORM entity mappings.
- Native SQL, JPQL, and named queries.
- Stored SQL in configuration files.
- ETL/Data Integration jobs.
- BI/reporting dashboards.
- Schedulers and shell scripts.
- CDC/replication configurations.
- API payloads, message schemas, and data contracts.
- Stored procedures in remote databases calling across database links.

No dictionary query replaces searching application repositories and confirming with integration system owners.

## 5. Renaming Tables

Oracle supports `RENAME` to rename an object within a schema:

~~~sql
RENAME orders TO sales_orders;
~~~

After renaming, the object is accessed by the new name. The old name is no longer the active table name.

### 5.1. What Does Renaming a Table Impact?

Check:

- SQL in applications and batch jobs.
- Views/materialized views referencing the table.
- PL/SQL packages/procedures/functions.
- Triggers and dynamic SQL.
- Synonyms pointing to the old name.
- Foreign keys and constraints.
- ETL, BI, and reports.
- Database link consumers.
- ORM `@Table(name = ...)`.
- Migration scripts and deployment configs.

Never assume dependencies have their source code rewritten automatically to use the new name. Oracle tracks dependency invalidation, but external applications are not updated by Oracle.

### 5.2. Preserving Compatibility with the Old Name

If transitioning across multiple releases, consider creating a compatibility view or synonym under the old name, depending on read/write needs and privileges.

For example, if the new table is named `SALES_ORDERS`, create a compatibility view:

~~~sql
CREATE OR REPLACE VIEW orders AS
SELECT order_id,
       customer_id,
       status,
       created_at
FROM sales_orders;
~~~

This view helps some legacy queries keep working. However:

- Not all views are automatically updatable.
- DML through a view may require `INSTEAD OF` triggers.
- Renamed columns must be aliased back to their old names.
- Grants on the view must be applied and verified.
- Query plans and semantics may shift.
- Any old object sharing the name must be handled before creating the view.

Do not deploy compatibility views without thoroughly testing privileges, DML behavior, and performance.

### 5.3. Renaming a Table Does Not Copy Data

`RENAME` only changes the object's name. It does not create a copy or relocate data to different storage. If your goal is moving data, changing layout, or changing partitioning, use a different procedure.

## 6. Renaming Columns

Use `ALTER TABLE ... RENAME COLUMN`:

~~~sql
ALTER TABLE orders
RENAME COLUMN order_status TO status;
~~~

Renaming a column updates column metadata. Existing data remains in the same column rather than being copied to a new column.

### 6.1. Places Requiring Updates

- SQL `SELECT`/`INSERT`/`UPDATE`/`DELETE`.
- Views and materialized views.
- PL/SQL source code.
- Triggers.
- Function-based index expressions.
- Check constraint expressions.
- Virtual column expressions.
- Partition/subpartition key expressions.
- ORM entity fields and `@Column` annotations.
- DTO projections and row mappers.
- Reports, ETL jobs, and external consumers.

Some metadata dependencies are tracked by Oracle and objects get invalidated/recompiled. However, source still containing the old column name will fail to compile until fixed.

### 6.2. Views Using SELECT *

A view defined with `SELECT *` does not act as a dynamic contract automatically reflecting newly added columns. Oracle expands the wildcard when the view is created; when table structure changes, inspect/recreate the view to produce the intended projection.

Avoid `SELECT *` in views or API views if the underlying schema changes regularly.

### 6.3. Direct Rename vs. Expand-Contract

If all consumers can be stopped and deployed simultaneously, a direct rename may fit.

If the application uses rolling deployments or multiple systems share the database, renaming directly breaks old versions during transition. Use expand-contract:

1. Add a new column with the new name.
2. Update applications to read both or read the new column once ready.
3. Dual-write or backfill according to the defined strategy.
4. Verify data across both columns is consistent.
5. Migrate all consumers to the new column.
6. Stop writing the old column.
7. Drop the old column in a later release.

This takes more time and temporary storage, but avoids a sudden breaking column-name cutover.

## 7. Changing Data Types: Compatible Changes vs. Data Conversions

Not all data type changes carry equal risk.

Lower-risk examples:

- Widening `VARCHAR2` length from 100 to 300.
- Increasing `NUMBER` precision while keeping compatible scale.
- Increasing `CHAR`/`VARCHAR2` length as needed.

Examples requiring deep analysis:

- `VARCHAR2` to `NUMBER`.
- `NUMBER` to `VARCHAR2`.
- `DATE` to `TIMESTAMP`.
- `VARCHAR2` to `DATE`/`TIMESTAMP`.
- `CLOB` to `VARCHAR2`.
- `BLOB` to `RAW`.
- Decreasing scale (rounding or truncating fractional digits).
- Changing character set or length semantics.

### 7.1. MODIFY Column

Example increasing length:

~~~sql
ALTER TABLE customers
MODIFY (customer_name VARCHAR2(300 CHAR));
~~~

Example increasing precision:

~~~sql
ALTER TABLE invoice_lines
MODIFY (quantity NUMBER(18, 3));
~~~

Exact syntax and feasibility depend on data type, existing data, constraints, indexes, partitioning, and Oracle release.

Increasing length differs fundamentally from converting data types. Shrinking length or reducing precision/scale can fail if existing data does not fit, or cause data loss.

### 7.2. Checking Data Before Conversion

When converting `VARCHAR2` to `NUMBER`, check unconvertible values first:

~~~sql
SELECT order_id,
       amount_text
FROM staging_orders
WHERE amount_text IS NOT NULL
  AND VALIDATE_CONVERSION(amount_text AS NUMBER) = 0;
~~~

`VALIDATE_CONVERSION` is available on supported Oracle releases. On older releases, use an appropriate safe conversion check rather than naive regexes when numeric formats involve separators, locales, or exponents.

Also verify:

- `NULL` and empty string semantics.
- Negative/positive signs.
- Decimal separators.
- Thousands separators.
- Leading/trailing whitespace.
- Values exceeding precision.
- Values exceeding target scale.
- Date strings against NLS formats.
- Timezones and daylight saving transitions when converting timestamps.

### 7.3. Is the Conversion Lossy?

For instance, `NUMBER(12,2)` to `NUMBER(10,0)` can lose fractional digits or overflow precision. `DATE` to `TIMESTAMP` does not inherently lose time data, though it cannot fabricate missing fractional seconds or timezones. `TIMESTAMP WITH TIME ZONE` to `DATE` discards timezone offsets and fractional seconds.

Define exact business conversion rules before writing DDL.

## 8. Shadow Column Strategy for Data Type Changes

For populated tables requiring real type conversion, adding a new column is usually safer than altering the data type in place.

Suppose `AMOUNT_TEXT` is `VARCHAR2` and must become `NUMBER`.

### Step 1 — Add the New Column

~~~sql
ALTER TABLE orders
ADD (amount_number NUMBER(18, 2));
~~~

This DDL performs an implicit commit. Prepare change records and check space/metadata before running.

### Step 2 — Batched Backfill

~~~sql
UPDATE orders
SET amount_number =
    TO_NUMBER(amount_text DEFAULT NULL ON CONVERSION ERROR)
WHERE amount_number IS NULL
  AND amount_text IS NOT NULL;
~~~

`DEFAULT ... ON CONVERSION ERROR` depends on Oracle release support. Do not use it if conversion errors must be surfaced and resolved; instead, record a reject list and reconcile invalid rows.

On large tables, backfill by primary key range or batch key to bound undo, redo, lock duration, and workload impact.

### Step 3 — Dual-Write

During transition, the application writes both old and new columns, or writes one authoritative source and syncs the other via controlled logic.

Avoid two independent writers drifting out of sync. Designate a single source of truth and define handling when one write fails.

### Step 4 — Reconcile

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM orders
WHERE amount_text IS NOT NULL
  AND (
      amount_number IS NULL
      OR amount_number <> TO_NUMBER(
          amount_text DEFAULT NULL ON CONVERSION ERROR
      )
  );
~~~

Reconciliation must account for rounding, scale, and business formatting. For monetary amounts, never round automatically without a business-owner-approved rule.

### Step 5 — Switch Consumers

Update views, packages, triggers, reports, ORM mappings, and application queries to use `AMOUNT_NUMBER`. Monitor errors and data integrity.

### Step 6 — Retire the Old Column

Once zero consumers read or write the old column, stop dual-writing and retain only the new column. Dropping the old column is a separate contract step after the application rollback window closes.

### Step 7 — Drop the Old Column in a Separate Change

~~~sql
ALTER TABLE orders DROP COLUMN amount_text;
~~~

`DROP COLUMN` is DDL and cannot be rolled back in a normal transaction. Retain snapshots/backups and verify dependencies before executing.

## 9. Limitations on Direct In-Place Data Type Changes

Oracle enforces strict rules on `ALTER TABLE MODIFY`. Some changes are allowed only when the column is empty or existing data meets conversion rules; compatible expansions such as increasing length can often execute directly.

Before using `MODIFY`, verify:

- Whether the column contains data.
- Source and target data types.
- Precision, scale, length, and character semantics.
- Whether the column participates in PK/UK/FK/CHECK constraints.
- Whether the column participates in indexes, function-based indexes, or partition keys.
- Whether the table has LOBs, object types, virtual columns, or dependent views.
- Whether constraints or indexes must be disabled or rebuilt.
- Which online operations your Oracle release supports.

Never conclude from an empty lab table that an `ALTER` statement will succeed on a billion-row production table.

### 9.1. Changing Length Semantics

`VARCHAR2(100 BYTE)` and `VARCHAR2(100 CHAR)` do not share the same byte limit. Under multibyte character sets, actual character capacities differ.

Check `CHAR_USED`, `CHAR_LENGTH`, and `DATA_LENGTH` before and after the change. Verify whether the application validates by bytes or characters.

### 9.2. NUMBER Precision and Scale

`NUMBER(p,s)` has maximum precision and scale limits enforced by Oracle. Decreasing scale can round values; decreasing precision can overflow existing values.

Check `MIN`/`MAX`, integer digit counts, decimal digit counts, and rounding rules. Financial data must be tested using `BigDecimal`, never arbitrary floating-point conversions.

### 9.3. DATE and TIMESTAMP

Oracle `DATE` stores date and time down to seconds, without fractional seconds or timezone. `TIMESTAMP` supports fractional seconds; `TIMESTAMP WITH TIME ZONE` carries timezone metadata.

Before converting:

- Identify database/session timezones.
- Determine whether existing values represent local time or UTC.
- Check application mappings.
- Determine whether timezone offsets must be preserved.
- Check query filters and indexes.
- Verify API formats and serialization.

You cannot recover unrecorded timezone information simply by converting `DATE` to `TIMESTAMP WITH TIME ZONE`.

## 10. Adding a NOT NULL Constraint

A `NOT NULL` column requires every row to hold a non-null value.

~~~sql
ALTER TABLE customers
MODIFY (customer_name NOT NULL);
~~~

This fails if the table currently contains any `NULL` rows.

Check first:

~~~sql
SELECT COUNT(*) AS null_count
FROM customers
WHERE customer_name IS NULL;
~~~

If `NULL` rows exist:

1. Define the replacement business rule.
2. Backfill valid values or remediate invalid rows.
3. Prevent new application writes from inserting `NULL`.
4. Re-check counts.
5. Add and validate the constraint.

Never blindly replace `NULL` with an empty string. In Oracle, an empty `VARCHAR2` string is treated as `NULL`; dummy defaults can corrupt business semantics.

### 10.1. Adding CHECK NOT NULL in Phases

A check constraint can serve as a transitional step:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT ck_customers_name_nn
CHECK (customer_name IS NOT NULL)
ENABLE NOVALIDATE;
~~~

Once historical data is cleaned and verified, validate:

~~~sql
ALTER TABLE customers
ENABLE VALIDATE CONSTRAINT ck_customers_name_nn;
~~~

Finally, you can normalize into `NOT NULL` column metadata via `ALTER TABLE MODIFY` if appropriate for your release and schema design. Do not leave redundant constraints around without reason.

## 11. Adding CHECK Constraints

`CHECK` constraints restrict column values by condition:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount_nonnegative
CHECK (total_amount >= 0)
ENABLE VALIDATE;
~~~

Before adding, check for violating rows:

~~~sql
SELECT order_id,
       total_amount
FROM orders
WHERE total_amount < 0;
~~~

Note SQL `CHECK` semantics: expressions evaluating to `UNKNOWN` due to `NULL` do not violate a `CHECK` constraint. If a value is mandatory, add `NOT NULL` separately.

Example:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
~~~

If `STATUS` allows `NULL`, this `CHECK` does not substitute for `NOT NULL`.

## 12. Adding UNIQUE and PRIMARY KEY Constraints

### 12.1. Checking for Duplicates

~~~sql
SELECT customer_code,
       COUNT(*) AS duplicate_count
FROM customers
GROUP BY customer_code
HAVING COUNT(*) > 1;
~~~

For composite constraints, group by all key columns. Verify `NULL` semantics and collation/character comparison rules for the data types.

### 12.2. Adding UNIQUE

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_code
UNIQUE (customer_code);
~~~

### 12.3. Adding PRIMARY KEY

~~~sql
ALTER TABLE customers
ADD CONSTRAINT pk_customers
PRIMARY KEY (customer_id);
~~~

A primary key requires both uniqueness and `NOT NULL`. Oracle may reuse a suitable existing index or create a new index to enforce the constraint, depending on configuration and DDL.

Before adding, inspect existing indexes, tablespaces, key lengths, data distribution, and duplicate/null values. Avoid creating redundant indexes if a suitable index already exists.

## 13. Adding FOREIGN KEY Constraints

A foreign key ensures child table values reference valid parent table keys.

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);
~~~

The referenced columns must form a matching primary key or unique key. Data types and column attributes must satisfy Oracle compatibility rules.

Check for orphan rows first:

~~~sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers c
      WHERE c.customer_id = o.customer_id
  );
~~~

### 13.1. Indexing Foreign Keys

Oracle does not automatically create an index for every foreign key. An index on an FK is often beneficial for joins and reduces locking contention when parent keys are updated or deleted, though decisions depend on workload.

Example:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
~~~

For composite FKs, review column order and query patterns before indexing.

### 13.2. ON DELETE Behavior

You can specify `ON DELETE CASCADE` or `SET NULL` where appropriate:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_lines_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ON DELETE CASCADE;
~~~

`CASCADE` can delete large numbers of child rows when a parent is deleted. Use it only when business semantics genuinely require it. `SET NULL` requires nullable columns. Never add `CASCADE` just to bypass FK errors.

## 14. ENABLE, DISABLE, VALIDATE, and NOVALIDATE

Constraints have two orthogonal aspects:

- **ENABLE/DISABLE:** whether enforcement applies to new DML.
- **VALIDATE/NOVALIDATE:** whether existing data has been checked against the constraint.

| State | Existing Data | New DML |
|---|---|---|
| `ENABLE VALIDATE` | Checked and certified | Enforced |
| `ENABLE NOVALIDATE` | Legacy data not guaranteed valid | New DML enforced per constraint |
| `DISABLE VALIDATE` | Validated, but enforcement disabled | Not enforced like `ENABLE` |
| `DISABLE NOVALIDATE` | Legacy data not guaranteed valid | Not enforced |

Exact behavior also depends on constraint type and operation. Consult the Oracle SQL Reference for specific states.

### 14.1. Creating an Unvalidated Constraint

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount
CHECK (total_amount >= 0)
ENABLE NOVALIDATE;
~~~

This enforces rules on new data without immediately scanning/validating the entire existing table. However, historical rows may still violate the constraint.

Never report a constraint as fully valid when `VALIDATED = NOT VALIDATED`.

### 14.2. Validating After Cleanup

~~~sql
ALTER TABLE orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

Oracle checks existing data. If any violating rows remain, the command fails and the constraint does not reach the validated state.

### 14.3. Checking Status

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_name;
~~~

Verify actual dictionary status after migration rather than relying solely on script exit codes.

## 15. DEFERRABLE Constraints

Certain constraints can be declared `DEFERRABLE` to postpone checking until commit time:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_lines_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Within a transaction, you can toggle mode:

~~~sql
SET CONSTRAINTS fk_lines_order DEFERRED;
~~~

or:

~~~sql
SET CONSTRAINTS fk_lines_order IMMEDIATE;
~~~

`DEFERRABLE` is useful for multi-step operations, such as temporarily inserting child rows before parent rows within the same transaction. Not every constraint or use case needs deferred checking.

Verify commit behavior in tests. A JPA flush is not equivalent to a commit; deferred constraints may only raise errors when the transaction commits.

## 16. Indexes and Dependent Objects After Changes

### 16.1. Indexes

After renaming a column, column-based indexes stay attached via metadata, though index names and dependent queries should be reviewed. Never assume every index expression or function-based index still retains its intended meaning.

After data type conversions, check:

- Index status.
- Column ordering.
- Function-based expressions.
- Selectivity and statistics.
- Key lengths.
- Partitioned index statuses.
- Before/after execution plans.

### 16.2. Views and Materialized Views

Views depending on modified columns/tables may turn invalid or fail compilation after renames, drops, or type changes. Inspect `DBA_OBJECTS` and compile errors.

Materialized views also carry refresh dependencies, logs, and refresh modes. Base table changes can affect refresh behavior or query rewrite. Plan full refreshes or rebuilds per design.

### 16.3. PL/SQL Packages and Triggers

Stored PL/SQL depending on modified objects may become invalidated on metadata changes. Oracle automatically recompiles on invocation when possible, but compilation fails if source still references old names or incompatible columns.

Check:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'REPORT_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

View compile errors:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM dba_errors
ORDER BY owner, name, sequence;
~~~

### 16.4. Synonyms

Synonyms hold logical names for target objects. When a target table is renamed or moved to another schema, synonyms may stop resolving to the expected object.

Inspect `DBA_SYNONYMS` and test resolution as the application principal. Synonyms do not migrate data or rewrite SQL source in consumers.

### 16.5. Triggers and Constraints

Triggers attach to tables and have PL/SQL bodies referencing columns. Inspect trigger statuses, bodies, and behavior after DDL. Constraints may still exist yet require verifying conditions and column mappings in the dictionary.

### 16.6. Dynamic SQL and Applications

Oracle dependency metadata cannot track SQL concatenated from strings. Search source repositories, configs, scheduler scripts, ETL jobs, and reports.

Example:

~~~sql
l_sql := 'SELECT old_status FROM orders WHERE order_id = :b1';
OPEN l_cursor FOR l_sql USING p_order_id;
~~~

Column names inside dynamic SQL are not analyzed by the compiler like static SQL. After a rename, such queries may only fail at runtime.

## 17. Handling Invalid Objects After Migration

After schema changes, list all invalid objects:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Compile specific objects once source is updated:

~~~sql
ALTER VIEW report_orders COMPILE;
ALTER PACKAGE order_api COMPILE;
ALTER PACKAGE order_api COMPILE BODY;
ALTER PROCEDURE close_order COMPILE;
ALTER FUNCTION calculate_total COMPILE;
~~~

Do not run mass recompilations before confirming dependencies and source have been updated. Compiling merely re-validates an object; it does not fix broken references.

You can use `DBMS_UTILITY.COMPILE_SCHEMA` or `UTL_RECOMP` per DBA procedures when many objects need recompiling. Schedule carefully, monitor errors, and avoid unexpected production load spikes.

## 18. Expand-Contract for Non-Simultaneous Deployments

For applications using rolling deployments or serving multiple consumers, schema changes need a compatibility phase.

~~~text
Phase 1: EXPAND
    Add new column/object
    Keep old interface working
    Deploy code that understands old + new

Phase 2: MIGRATE
    Backfill existing rows
    Dual-write or synchronize
    Reconcile data
    Move consumers to new interface

Phase 3: CONTRACT
    Stop old reads/writes
    Remove old dependencies
    Drop old column/object in a later release
~~~

### 18.1. Expand

Add new columns as nullable or with compatible defaults. Do not drop old columns. Add indexes/constraints in phases.

### 18.2. Migrate

Backfill in batches. Monitor progress, conversion errors, and data skew. Applications can dual-write while maintaining one source of truth and reconciliation.

### 18.3. Contract

Drop old columns/objects only after:

- No application version reads/writes the old names.
- No batch/ETL/report depends on them.
- Database dependencies have been updated.
- New data has been verified.
- A backup/recovery plan is in place.
- The change is approved.

Never contract right after deploying a new version if rolling deployment or application rollback could still bring old code back.

## 19. Online Redefinition for Large Tables

For large tables needing minimal downtime, Oracle `DBMS_REDEFINITION` supports online table redefinition in eligible scenarios.

High-level workflow:

1. Verify table eligibility with `CAN_REDEF_TABLE`.
2. Create an interim table with the target structure.
3. Invoke `START_REDEF_TABLE`.
4. Copy dependent objects via `COPY_TABLE_DEPENDENTS` per plan.
5. Sync incremental changes via `SYNC_INTERIM_TABLE`.
6. Verify data consistency and dependencies.
7. Invoke `FINISH_REDEF_TABLE` in a cutover window.
8. Verify objects, grants, constraints, indexes, and applications.
9. Clean up interim objects per runbook.

Core API check:

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP_OWNER',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

This illustrates only the eligibility check. `START_REDEF_TABLE`, `COPY_TABLE_DEPENDENTS`, `SYNC_INTERIM_TABLE`, and `FINISH_REDEF_TABLE` require exact parameters, privileges, storage, and conditions per Oracle release.

Online redefinition does not mean zero risk or zero downtime. Test on a representative data clone and check unsupported types/features, space overhead, materialized view logs, dependent objects, and cutover duration.

## 20. DDL Implicit Commits and Migration Recovery

Oracle DDL commits implicitly before executing and upon successful completion. Therefore:

- Never run DDL inside business transactions requiring rollback.
- Never rely on Spring `@Transactional` to roll back `CREATE`/`ALTER`/`DROP`/`TRUNCATE`.
- If a script contains multiple DDL statements, earlier ones may already be applied when a later one fails.
- Migration tool rollback scripts execute new inverse operations rather than rolling back the original transaction.

### 20.1. Break Migrations into Small Steps

Example data type change:

1. Add shadow column.
2. Add supporting indexes/constraints if needed.
3. Deploy compatible code.
4. Backfill.
5. Validate.
6. Switch consumers.
7. Drop old column in a separate migration.

Each step has preconditions, postconditions, and a recovery/forward-fix plan.

### 20.2. Maintain a Migration Ledger

Record:

- Change ID and migration version.
- Database, PDB, and schema.
- Executed DDL.
- Start/end timestamps.
- Operator/executor.
- Row counts and object counts.
- Constraint/index statuses.
- Invalid objects.
- Compatible application version.
- Verification evidence and ticket.

### 20.3. Recovering When DDL Fails

Do not reflexively re-run the entire script. First:

1. Identify the last statement that succeeded.
2. Query the dictionary to see if objects/columns/constraints already exist.
3. Inspect backfilled data and constraint states.
4. Check migration tool history.
5. Determine whether any DML was implicitly committed.
6. Write a dedicated forward-fix or cleanup script.
7. Re-run idempotent steps only after confirming actual state.

## 21. Testing Schema Changes

### 21.1. Pre-DDL Checks

- Does data fit the new data type?
- Are there `NULL`s, duplicates, or orphan rows?
- Are there dependent objects?
- Are consumers using old names?
- Are indexes, partitions, or LOB features impacted?
- Are tablespace and undo/redo capacities sufficient?
- Are there lock or downtime risks?

### 21.2. Post-DDL Checks

- Column names/types/lengths/precision match.
- Constraint status and `validated` state match.
- Index statuses are valid.
- Views/packages/triggers compile cleanly.
- Synonyms resolve properly.
- Application queries/ORM mappings work.
- Data reconciliation passes.
- Execution plans and latency show no regressions.
- Jobs/ETL/reports operate normally.
- Grants, auditing, and security policies remain intact.

### 21.3. Edge-Case Data Testing

For data type conversions:

- `NULL`.
- Empty strings.
- Min/max boundary values.
- Negative/positive numbers.
- Decimal rounding.
- Unicode/multibyte strings.
- Date boundaries/leap days.
- Timestamps/timezones.
- Malformed strings.
- Values exceeding precision/length.

For constraints:

- Valid data.
- Violating data.
- Duplicate keys.
- Orphan FKs.
- `NULL` in required columns.
- Concurrent inserts violating uniqueness.
- Deferred constraints at commit.

### 21.4. Test on Real Oracle

H2 or other databases cannot substitute for Oracle when testing:

- DDL implicit commits.
- Data dictionary behavior.
- PL/SQL invalidation.
- Oracle data type conversions.
- `ENABLE NOVALIDATE`/`VALIDATE`.
- `DEFERRABLE` constraints.
- `DBMS_REDEFINITION`.
- Partitioned objects.
- Oracle optimizer and index behavior.

Use an Oracle integration environment matching production's release/RU and character set.

## 22. Schema Change Deployment Runbook

### Step 1 — Confirm Objective

Document old and new objects, columns, data types/constraints, consumers, business rules, RTO/downtime budget, and owner.

### Step 2 — Inventory Dependencies

Collect `DBMS_METADATA`, `DBA_DEPENDENCIES`, `DBA_SOURCE`, `DBA_VIEWS`, `DBA_SYNONYMS`, `DBA_TRIGGERS`, `DBA_CONSTRAINTS`, `DBA_INDEXES`, and application references.

### Step 3 — Inspect Data

Run duplicate, `NULL`, orphan, and conversion validation queries. Record counts and sanitized error samples.

### Step 4 — Assess Capacity and Impact

Estimate table scans, backfills, index builds, redo/undo, locks, storage, and validation runtime. Check RAC/Data Guard impact if applicable.

### Step 5 — Prepare Migrations

Write small-step scripts with preconditions and postconditions. Prepare rollback/forward fixes and compatibility code.

### Step 6 — Backup and Approval

Confirm backup/recovery points, change window, approvers, communications, and stop criteria. Remember DDL cannot be rolled back via ordinary transactions.

### Step 7 — Execute

Run in order. Record output, timings, row counts, and step statuses. Halt whenever a postcondition fails.

### Step 8 — Verify Dependencies

Compile/test views, packages, and triggers; verify invalid objects, synonyms, indexes, constraints, and application consumers.

### Step 9 — Business Verification

Run smoke tests, data reconciliation, batch/report tests, and performance comparisons.

### Step 10 — Close the Change

Archive evidence, update schema documentation, ORM mappings, migration versions, and runbooks. Hand off follow-up items to owners.

## 23. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Direct rename while old app runs | Old SQL fails immediately | Use expand-contract or coordinated cutover |
| Searching only `DBA_DEPENDENCIES` | Misses dynamic SQL and external apps | Search source/config/ETL and confirm with owners |
| Shrinking `VARCHAR2` length unchecked | DDL fails or loses data on conversion | Check max lengths and multibyte widths |
| `VARCHAR2` to `NUMBER` without validation | Bad data crashes migration | Use `VALIDATE_CONVERSION` and reject lists |
| Arbitrarily reducing `NUMBER` scale | Rounding or precision loss | Define business rounding rules and reconcile |
| Adding `NOT NULL` with existing `NULL`s | `ALTER` fails | Backfill and validate first |
| `CHECK` constraint forgetting `NULL` | `NULL` still passes check | Add `NOT NULL` explicitly if required |
| Adding FK with orphan rows | Constraint fails validation | Find and resolve orphans first |
| Treating `ENABLE NOVALIDATE` as `VALIDATE` | Historical rows may still violate | Check `DBA_CONSTRAINTS.VALIDATED` |
| Assuming indexes stay optimal after type change | Plan regressions or unusable indexes | Inspect indexes and execution plans |
| Skipping compile/test of dependent objects | Invalid objects surface at runtime | Precompile and run smoke tests |
| Using `SELECT *` in views/APIs | Unexpected projections after schema change | List columns explicitly |
| Putting DDL inside rollbackable transaction | DML before DDL commits prematurely | Separate DDL from business transactions |
| Blindly re-running failed migrations | Object-exists errors or inconsistent state | Inspect dictionary and forward-fix |
| Dropping old column right after deploy | App rollback loses compatibility | Keep a compatibility window |
| Testing only on H2 | Misses Oracle semantics | Run Oracle integration tests |

## 24. Pre- and Post-Schema-Change Checklist

### Before the Change

- [ ] Confirmed database, PDB, owner, and object.
- [ ] Saved current DDL using `DBMS_METADATA`.
- [ ] Inventoried columns, constraints, indexes, and partitions.
- [ ] Checked `DBA_DEPENDENCIES` and PL/SQL source.
- [ ] Searched dynamic SQL, synonyms, views, triggers, and materialized views.
- [ ] Identified application/ORM/ETL/BI consumers.
- [ ] Validated data for conversions, `NULL`s, duplicates, and orphans.
- [ ] Evaluated locks, scans, redo/undo, and storage.
- [ ] Defined downtime/online strategy.
- [ ] Prepared backups, change approval, and forward-fix plans.
- [ ] Verified old/new application compatibility during rollout.

### After the Change

- [ ] Verified column names/types/precision/lengths.
- [ ] Verified constraints are `ENABLED` and `VALIDATED` as required.
- [ ] Verified index statuses and statistics.
- [ ] Verified views/materialized views refresh or compile.
- [ ] Verified packages/procedures/functions/triggers are `VALID`.
- [ ] Verified synonyms and grants.
- [ ] Tested dynamic SQL and application queries.
- [ ] Reconciled before/after data.
- [ ] Ran smoke tests, batch jobs, and reports.
- [ ] Compared execution plans and latency.
- [ ] Checked invalid objects and error logs.
- [ ] Archived migration evidence and updated documentation.

## 25. Key Takeaways

- The schema is a contract shared by the database, applications, PL/SQL, ETL, BI, and other consumers.
- `RENAME TABLE` and `RENAME COLUMN` update metadata names; they do not automatically rewrite application SQL or dynamic SQL.
- Before renaming, dropping, or changing types, inventory dependencies via dictionary views and external codebase searches.
- `DBA_DEPENDENCIES` is a starting point, not an exhaustive list of all references.
- `DBMS_METADATA.GET_DDL` saves baseline object definitions; it does not replace data backups.
- Increasing length differs from converting data types; type conversions require checking data, precision, scale, encoding, constraints, and indexes.
- For risky conversions, shadow columns, batched backfills, dual-writes, reconciliation, and cutover are safer than in-place modifications.
- `NOT NULL`, `CHECK`, `UNIQUE`, `PRIMARY KEY`, and `FOREIGN KEY` constraints must be checked against existing data before enabling/validating.
- `CHECK` does not substitute for `NOT NULL` because `UNKNOWN` from `NULL` does not violate `CHECK`.
- `ENABLE NOVALIDATE` enforces new data without proving existing rows comply; `VALIDATE` checks existing rows.
- `DEFERRABLE` constraints may check only at commit; testing flush alone is insufficient.
- Indexes, views, materialized views, triggers, packages, synonyms, and dynamic SQL must all be checked after schema changes.
- Views using `SELECT *` do not automatically pick up columns added later; prefer explicit column lists.
- Oracle invalidates dependent PL/SQL/views and attempts auto-recompilation, but source referencing old names fails compilation.
- Expand-contract preserves compatibility during rolling deployments; drop old columns/objects only after zero legacy consumers remain.
- `DBMS_REDEFINITION` supports certain online table redefinitions, subject to prerequisites, dependencies, and cutover testing.
- Oracle DDL performs implicit commits; Spring `@Transactional` and `ROLLBACK` cannot undo DDL or DML committed prior to DDL.
- Multi-DDL migrations can complete partially; inspect the dictionary and forward-fix rather than blindly re-running scripts.
- Test schema changes on an Oracle version/RU matching production with representative data and concurrency.
- Verify metadata, data, application behavior, execution plans, and dependent objects before closing the change.

### Oracle Reference Documentation

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — `ALTER TABLE`, `RENAME`, constraints, data type modification, `DROP`, and `TRUNCATE`.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Schema objects, dependencies, indexes, constraints, and maintenance.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — `DBA_DEPENDENCIES`, `DBA_TAB_COLUMNS`, `DBA_CONSTRAINTS`, `DBA_CONS_COLUMNS`, `DBA_INDEXES`, `DBA_OBJECTS`, and `DBA_ERRORS`.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_METADATA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html) — Extracting object definitions.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html) — Online table redefinition APIs and prerequisites.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — Dependencies, DDL, transactions, and object lifecycles.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/) — Large table maintenance and partitioning considerations.

DDL capabilities, online operations, data type conversion restrictions, and dependency behaviors vary by Oracle release and object type. Confirm exact release documentation, test against representative schemas and data volumes, and use a dedicated change window with a forward-recovery plan for production schema evolution.
