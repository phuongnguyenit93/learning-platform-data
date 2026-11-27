# Managing DDL, PL/SQL, and Reference Data with Version Control

An Oracle schema is part of the application. Tables, columns, indexes, constraints, sequences, views, packages, procedures, triggers, and reference data all affect how the application behaves. If these changes are only applied manually in each environment, over time development, test, and production can end up with different structures even while running the same application version.

Version control for databases helps track change history, review before deployment, rebuild the schema from scratch, and determine exactly which changes a database has received. The goal is not merely to put SQL files into Git, but to build an ordered, controllable migration process with deployment evidence and error-handling strategies suited to Oracle's behavior.

In Oracle, it is especially important to note that many DDL statements cause an implicit commit. Therefore, a migration containing `CREATE`, `ALTER`, `DROP`, or `TRUNCATE` cannot be rolled back like an ordinary DML transaction. Schema change strategies must be designed to roll forward, with state verification steps and separate data/application recovery plans.

## 1. Why Put the Database Under Version Control?

A Java application has its source code in Git, but if the Oracle schema is not managed with the same discipline, the source code alone is not enough to reproduce a running environment.

For example, consider a release adding payment status tracking. The changes might include:

- Adding the `PAYMENT_STATUS` column to the `ORDERS` table.
- Adding a constraint to enforce valid status values.
- Creating an index to support reporting queries.
- Modifying the `ORDER_API` package to update the status.
- Inserting standard status codes into the `PAYMENT_STATUSES` table.
- Granting privileges to the runtime role to read the new table.

If you only commit the Java code and forget the migration, the new application may run on a developer's machine but fail when deployed to test or production. Conversely, if a DBA modifies production directly without scripts in the repository, subsequent environments cannot rebuild the exact schema.

### 1.1. Benefits of Database Version Control

| Benefit | Practical Meaning |
|---|---|
| Change history | Know who changed a table, package, or reference data, and in which release |
| Environment reproducibility | Ability to create a new schema using the same migration sequence |
| Review | DBAs and developers review DDL, privileges, indexes, and data migrations before deployment |
| Consistency | Development, test, staging, and production receive the same approved changes |
| Audit | Evidence of migration files, Git commits, and execution runs across each environment |
| Drift detection | Compare the actual schema against the expected state in the repository |
| Roll forward | Once a migration has been applied, a follow-up migration can be created to fix issues in a controlled way |
| CI/CD | Pipelines can automatically spin up a test database and verify migrations before release |

### 1.2. Database Schema Is Also Source Code

DDL and PL/SQL are the source code of the database. They require:

- Version history.
- Naming conventions and file organization rules.
- Review and approval.
- Testing.
- A deployment process.
- Ownership and maintenance responsibility.

A PL/SQL package edited directly in production using SQL Developer without being saved to Git is an out-of-band change. Even if the application keeps running, the next environment build may lose that change.

## 2. Classifying Database Changes

Not every SQL file has the same lifecycle. You need to distinguish between types of changes to choose the right versioning approach.

| Type | Example | Common Management Approach |
|---|---|---|
| Structural DDL | Create table, add column, constraint, index, sequence | Versioned migration |
| PL/SQL | Package spec/body, procedure, function, trigger | Versioned or repeatable migration depending on the tool |
| View/synonym | Create or replace view, synonym | Versioned or repeatable migration |
| Privileges | `GRANT`, `REVOKE`, role, directory | Reviewed migration managed per environment |
| Reference data | Status codes, transaction types, fixed catalogs | Seed/versioned data migration or repeatable upsert |
| Business data | Customers, orders, transactions | Not packaged as schema seed; handled via business workflows/separate imports |
| Data migration | Transforming existing data values/structures | Controlled versioned data migration with reconciliation |
| Environment config | Endpoints, credentials, paths, service names | Secret/config management, not hard-coded into shared migrations |

### 2.1. Schema Migration vs. Data Migration

A schema migration changes the structure of the database. For example, adding a `SOURCE_SYSTEM` column or creating an index.

A data migration changes existing data. For example, converting a status code from `P` to `PAID`, populating default values for a new column, or splitting one column into two.

These two types of changes may be related, but they should be distinguished in design. DDL usually causes an implicit commit and modifies metadata; DML can run inside a transaction, but a large data migration can generate massive undo/redo, hold locks for a long time, and impact the workload.

### 2.2. Reference Data vs. Business Data

Reference data is a small, stable set of values used by code as codes or catalogs, such as:

- `ORDER_STATUS`: NEW, PAID, CANCELLED.
- `PAYMENT_METHOD`: CARD, BANK_TRANSFER, CASH.
- `COUNTRY_CODE` or document types in a system-managed catalog.
- Internal classification codes shared across multiple modules.

Business data such as customers, orders, and payment transactions should not be placed into shared seed migrations. Business data is created through the application, imports, or operational processes.

## 3. Git Repository for the Database

A clear directory structure helps locate migrations and identify what type each script belongs to. For example:

```text
database/
  oracle/
    migrations/
      V001__create_reference_tables.sql
      V002__create_customers.sql
      V003__create_orders.sql
      V004__add_payment_status.sql
      V005__create_order_indexes.sql
      V006__grant_runtime_privileges.sql
    repeatable/
      R__order_api_package.sql
      R__customer_search_view.sql
    seed/
      reference/
        V001__seed_order_statuses.sql
        V002__seed_payment_methods.sql
    rollback-notes/
      V004__rollback_notes.md
    test-data/
      integration/
        customers.sql
        orders.sql
    README.md
```

This is an illustrative layout. If using Flyway, file names and locations must follow Flyway's configuration. If using Liquibase, you can organize XML/YAML/JSON/SQL changelogs and include child files. Avoid mixing multiple conventions in the same directory so the tool does not get confused about which migrations to run.

### 3.1. Migrations Must Have a Deterministic Order

A versioned migration should have a unique version that increments according to the team's rules. For example:

```text
V001__create_customers.sql
V002__create_products.sql
V003__create_orders.sql
V004__create_order_items.sql
```

Migration tools sort by version or the declared changelog order. Never rely on file ordering in Windows Explorer, Git commit order, or file modification timestamps.

### 3.2. Executed Migrations Must Be Treated as Immutable

Once migration `V004` has been executed in a shared environment, do not edit the contents of `V004` to "rewrite history." Tools usually store a checksum or equivalent metadata; modifying an already-executed file can cause validation to fail or leave environments out of sync.

If a fix is needed, create a new migration, such as `V007__correct_payment_status_constraint.sql`. The new migration describes the transition from the current schema state to the desired state.

During local development before a migration is shared or executed in a shared environment, the team may squash or reorder migrations according to internal conventions. Once a migration is released, its history must remain immutable.

### 3.3. Review Migrations Like Code

A database pull request should inform reviewers about:

- Which objects are added, modified, or dropped.
- Whether existing data is modified.
- Whether locks or table rewrites occur.
- Whether indexes are created online or offline and whether they take a long time.
- Whether dependent packages, views, or triggers are affected.
- Whether privileges need to be granted or revoked.
- Whether old and new application versions are compatible during rollout.
- What state the database will be in if the migration fails.

Do not simply attach screenshots from SQL Developer. Migrations must be saved as files that can be reviewed, re-run on fresh environments, and traced in Git.

## 4. Migration Tools: Flyway and Liquibase

Two common tools in the Java ecosystem are Flyway and Liquibase. Both manage database change history, though their configuration models and changelogs differ.

### 4.1. Flyway

Flyway commonly uses versioned migrations with file naming conventions such as:

```text
V1__create_customer_table.sql
V2__create_order_table.sql
V3__add_order_status.sql
```

Flyway stores migration history in a schema history table (by default typically `flyway_schema_history`). When executed, it determines which migrations have been applied, which are pending, and validates checksums based on configuration.

Repeatable migrations typically take the form:

```text
R__order_api_package.sql
R__reporting_views.sql
```

Repeatable migrations are re-executed whenever their checksum changes and are typically used for objects whose entire definition can be replaced with `CREATE OR REPLACE`, such as views or packages. Versioned migrations and repeatable migrations serve different roles; do not use repeatable migrations to replace structural state-transition migrations.

Spring Boot configuration example:

```yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration/oracle
    schemas: APP_OWNER
    default-schema: APP_OWNER
    validate-on-migrate: true
```

Exact property names and capabilities depend on the Spring Boot/Flyway version. Use configuration matching the deployed dependencies.

### 4.2. Liquibase

Liquibase manages changes through a changelog. Changelogs can be written in XML, YAML, JSON, or SQL format. Each changeSet has an id, an author, and the change definition.

Simple YAML example:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customers
      author: database-team
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: customer_id
                  type: NUMBER(12)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_name
                  type: VARCHAR2(200)
                  constraints:
                    nullable: false
```

Liquibase tracks state in tables such as `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`. For Oracle-specific SQL/PLSQL, you can use SQL changesets or `sqlFile` to preserve native syntax.

### 4.3. High-Level Comparison

| Criterion | Flyway | Liquibase |
|---|---|---|
| Primary model | Versioned and repeatable migration files | Changelog composed of changeSets |
| Description format | SQL is the most common approach | SQL or XML/YAML/JSON |
| History | Schema history table | DATABASECHANGELOG and DATABASECHANGELOGLOCK |
| Rollback | Depends on edition/features and scripts/strategy | Rollback can be declared per changeSet, though not all Oracle operations are reversible |
| Fit for Oracle-specific SQL | Natural when using SQL migrations | Can use SQL changesets/sqlFile |
| Database-agnostic abstraction | Focused on SQL or Java migrations | Provides cross-database changeset abstractions |

Choosing a tool depends on the team, release process, extent of Oracle-specific SQL usage, and existing systems. Do not run two migration tools simultaneously on the same schema without clearly defined ownership.

## 5. Oracle DDL Characteristics and Migration Implications

Oracle automatically commits before executing many DDL statements and commits after the DDL succeeds. Therefore, a migration containing both DDL and DML is not necessarily a single transaction that can be rolled back entirely.

Example:

```sql
UPDATE app.orders
SET order_status = 'PAID'
WHERE order_status = 'P';

ALTER TABLE app.orders ADD payment_reference VARCHAR2(100);

ROLLBACK;
```

Before executing the `ALTER TABLE` DDL, Oracle may commit the `UPDATE` DML. The final `ROLLBACK` will not restore the updated rows. This is a major difference from some other databases where developers expect DDL to participate in transactions.

### 5.1. Do Not Design Migrations Around DDL Rollback

For Oracle, assume that any DDL that succeeds is already committed. If a migration fails after running a few DDL statements, the schema may be left in a partial state. The deployment process must:

- Identify which statements succeeded.
- Inspect existing objects and migration history.
- Avoid blindly re-running scripts containing non-idempotent DDL.
- Create a forward-fix migration or execute an approved recovery procedure.
- Record the state so other environments do not diverge.

### 5.2. DDL Can Invalidate Dependent Objects

Modifying a table can put dependent views, packages, triggers, or functions into an `INVALID` state. Oracle can automatically recompile certain objects when they are accessed, but compilation may fail if the PL/SQL source is no longer compatible.

After a migration affecting dependent objects, inspect `USER_OBJECTS`/`DBA_OBJECTS`, check compilation errors, and recompile in dependency order as needed.

### 5.3. DDL Locks and Deployment Duration

Some DDL statements require metadata locks or scan/rewrite data. For example, adding constraints, changing data types, creating indexes, or moving tables can impact sessions accessing the object. Always estimate execution time on data volumes close to production.

Online options such as `CREATE INDEX ONLINE` or `ALTER TABLE ...` with online capabilities depend on the edition, version, object type, and operation. Do not add `ONLINE` out of habit without confirming support.

## 6. Ordering DDL Migrations by Dependency

Oracle objects have dependency relationships. Tables must exist before foreign keys; package bodies require package specs; views require source tables or views; triggers require tables; synonyms require target objects or can be created beforehand though resolution depends on the target object.

A typical ordering:

1. Users/schemas, tablespaces/quotas, and required grants.
2. Sequences or identity strategies.
3. Base tables and columns.
4. Primary keys, unique constraints, and check constraints.
5. Foreign keys following parent-child relationships.
6. Additional indexes.
7. Views and materialized views.
8. Types, package specifications, and package bodies.
9. Standalone procedures/functions.
10. Triggers, synonyms, and grants for runtime roles.
11. Reference data required by the application.

The exact order depends on dependencies. For example, a package spec may reference a type; a package body may reference another package. Build a dependency graph when schemas become complex.

### 6.1. Create Tables Before Referencing Constraints

If `ORDERS` references `CUSTOMERS`, the `CUSTOMERS` table must be created before creating the foreign key on `ORDERS`.

```sql
CREATE TABLE customers (
    customer_id NUMBER(12) CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL
);
```

```sql
CREATE TABLE orders (
    order_id NUMBER(12) CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL
);
```

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);
```

Separating constraints into their own migration can be useful when migrations need to populate base data, validate, or control locks. For new schemas, constraints can also be declared directly inside `CREATE TABLE` if dependencies are already in place.

### 6.2. Package Specification Before Package Body

The package spec exposes the API; the package body contains the implementation. When creating from scratch, the spec must exist before the body:

```sql
CREATE OR REPLACE PACKAGE app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER);
END order_api;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE app.orders
        SET order_status = 'PAID'
        WHERE order_id = p_order_id;
    END mark_paid;
END order_api;
/
```

In scripts run via SQL*Plus/SQLcl, a `/` on its own line submits the buffered PL/SQL block for execution. When executed via JDBC or a migration tool, delimiter handling may differ. Configure the tool so it does not pass `/` as part of the SQL text and does not split the package body at internal semicolons.

### 6.3. Compiling and Verifying PL/SQL

`CREATE OR REPLACE` can create an object in an `INVALID` state if there are compilation errors. Scripts should not rely solely on DDL not throwing an exception to conclude that a package works.

Check objects:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'TRIGGER')
ORDER BY object_name, object_type;
```

Check compile errors:

```sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, type, sequence;
```

You can recompile a package:

```sql
ALTER PACKAGE app.order_api COMPILE SPECIFICATION;
ALTER PACKAGE app.order_api COMPILE BODY;
```

If compilation fails due to missing direct privileges or dependencies, fix the root cause. Never grant broad privileges like `SELECT ANY TABLE` just to make a package compile.

## 7. Version Control for PL/SQL

PL/SQL source should be stored in dedicated files named to reflect the schema and object. For example:

```text
database/oracle/plsql/
  packages/
    order_api.pks.sql
    order_api.pkb.sql
    customer_api.pks.sql
    customer_api.pkb.sql
  procedures/
    reconcile_orders.sql
  functions/
    calculate_tax.sql
  triggers/
    orders_biu.sql
```

`.pks.sql` is commonly used for package specifications; `.pkb.sql` for package bodies. This is a repository convention, not an Oracle-enforced extension.

### 7.1. One Object, One Source of Truth

Avoid keeping duplicate copies of the same package across multiple release folders without specifying which one is canonical. If the same package is created from different scripts, a deployment could accidentally overwrite a newer implementation with an older one.

There should be one canonical definition for each object and clear rules for how the migration tool uses it:

- Versioned migrations contain one-time changes.
- Repeatable migrations contain the full definition of replaceable objects.
- Changelogs include PL/SQL files in dependency order.

Do not both create a package body in a versioned migration and keep a repeatable file for the same object without clear ordering. If both run, the final result depends on execution order.

### 7.2. Versioned or Repeatable for PL/SQL?

There are two common approaches:

**Versioned migration:** each package change gets its own version. History shows which release modified the package. This fits when every change must be an immutable state transition.

**Repeatable migration:** the file contains the full package/view definition. When the checksum changes, the tool re-runs `CREATE OR REPLACE`. This is convenient for objects whose definitions can be replaced in full.

The choice depends on the tool and release policy. For repeatable migrations, ensure the file always contains the complete definition and runs after required versioned migrations. For versioned migrations, never edit already-executed files.

### 7.3. Separating Spec and Body

Separating the package spec and body lets reviewers inspect API changes separately from implementation changes. Modifying the spec can invalidate dependent callers and widen the recompilation scope; modifying the body typically impacts compile dependencies less, though it can still trigger invalidation/compilation behavior depending on object dependencies.

If only the implementation changes, there is no need to modify the package spec. This helps minimize compile cascades and keeps the API stable.

### 7.4. PL/SQL Compile Settings

Some packages depend on compiler settings, conditional compilation, or session/environment settings. If the repository needs to control these, store the required compile configuration and ensure pipelines use the same database version/settings.

Do not hard-code environment paths or credentials into PL/SQL. Use a configuration table, secure application context, or an appropriate secret/config mechanism with controlled access.

## 8. Managing Reference Data with Migrations

Reference data is often used by the application as part of its contract. If Java code starts sending status `REFUNDED` before the `ORDER_STATUSES` table in production has that value, operations may fail due to foreign key or validation errors.

Therefore, code changes and reference data changes must be deployed in a synchronized, safe order.

### 8.1. Seeding Reference Data with INSERT

Example table:

```sql
CREATE TABLE order_statuses (
    status_code VARCHAR2(20) CONSTRAINT pk_order_statuses PRIMARY KEY,
    status_name VARCHAR2(100) NOT NULL,
    is_terminal CHAR(1) DEFAULT 'N' NOT NULL,
    CONSTRAINT ck_order_status_terminal CHECK (is_terminal IN ('Y', 'N'))
);
```

Seed:

```sql
INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('NEW', 'New order', 'N');

INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('PAID', 'Paid', 'N');

INSERT INTO order_statuses(status_code, status_name, is_terminal)
VALUES ('CANCELLED', 'Cancelled', 'Y');
```

This is a one-time data migration. On a fresh schema, it inserts the initial rows. If run again on a schema that already has the data, the primary key prevents duplicate inserts. That is desirable when a versioned migration must run exactly once.

### 8.2. MERGE for Reference Data Requiring Synchronization

If reference data is repeatedly updated to match a canonical state, `MERGE` can synchronize it:

```sql
MERGE INTO order_statuses t
USING (
    SELECT 'NEW' AS status_code, 'New order' AS status_name, 'N' AS is_terminal FROM dual
    UNION ALL
    SELECT 'PAID', 'Paid', 'N' FROM dual
    UNION ALL
    SELECT 'CANCELLED', 'Cancelled', 'Y' FROM dual
) s
ON (t.status_code = s.status_code)
WHEN MATCHED THEN
    UPDATE SET
        t.status_name = s.status_name,
        t.is_terminal = s.is_terminal
WHEN NOT MATCHED THEN
    INSERT (status_code, status_name, is_terminal)
    VALUES (s.status_code, s.status_name, s.is_terminal);
```

`MERGE` is appropriate when a canonical data definition needs to be re-applied. However, if production allows administrators to edit descriptions or reference attributes, `MERGE` could overwrite those edits. Clearly define which columns are owned by code and which are managed by operations.

### 8.3. Immutable Reference Data vs. Configuration Data

Not all lookup tables should be overwritten by migrations. You can classify them as:

- **Immutable reference:** status codes or data types defined by the product; changed via migrations.
- **Operational configuration:** thresholds, endpoints, feature flags, or parameters tuned by operations; managed through a dedicated configuration tool.
- **Business-maintained catalog:** catalogs maintained by users/business administrators; not re-seeded by migrations on every deploy.

This classification prevents new migrations from accidentally overwriting valid production configuration.

### 8.4. Do Not Delete Reference Codes Currently in Use

If status `CANCELLED` is already used across millions of order rows, deleting the status from the lookup table can violate foreign keys or strip historical meaning. Typically, mark it as inactive (`ACTIVE = 'N'`) instead of deleting it.

If deletion is truly necessary, inspect all foreign keys, historical data, reports, packages, and downstream code. Changing a reference code is a contract change, not just deleting a seed row.

## 9. Data Migrations for Existing Data

When the schema changes, existing data may need to be transformed. For example, changing `ORDER_STATUS` from a single-character code to a full code.

### 9.1. Simple Migration

```sql
UPDATE orders
SET order_status = CASE order_status
    WHEN 'N' THEN 'NEW'
    WHEN 'P' THEN 'PAID'
    WHEN 'C' THEN 'CANCELLED'
    ELSE order_status
END
WHERE order_status IN ('N', 'P', 'C');

COMMIT;
```

For large data migrations, estimate row counts, undo/redo volume, lock duration, and re-runnability. If a migration might be re-run, the condition must strictly target only rows that have not yet been converted.

### 9.2. Multi-Phase Migrations

Large changes should be broken down into compatible steps:

1. Add a new nullable column.
2. Deploy code that can read both old and new columns while still writing in a compatible way.
3. Backfill existing data in batches.
4. Switch code to write/read the new column.
5. Confirm no consumers still use the old column.
6. Add constraints/`NOT NULL` if needed.
7. Drop the old column in a later release.

This pattern is commonly called expand-and-contract. It reduces risk when the application runs multiple instances and cannot be stopped entirely to deploy schema and code at the exact same moment.

### 9.3. Batch Backfilling

Avoid always running a massive `UPDATE` on a very large table during peak hours. Split the work into chunks by primary key or partition:

```sql
UPDATE orders
SET normalized_status = order_status
WHERE order_id >= :from_id
  AND order_id < :to_id
  AND normalized_status IS NULL;
```

An orchestrating job selects key ranges, commits each batch, and records checkpoints. Define:

- Batch size.
- Pause interval between batches.
- How to resume after an error.
- Number of rows processed and remaining.
- Impact on indexes, undo, redo, and replication.

If the backfill must run concurrently with the application, ensure the new code does not write incompatible values and does not skip rows created or updated during the backfill.

### 9.4. Post-Data-Migration Reconciliation

After transformation, compare row counts per status and check NULLs, keys, and aggregates. For example:

```sql
SELECT order_status, COUNT(*)
FROM orders
GROUP BY order_status
ORDER BY order_status;
```

Save before/after counts and validation results in the deployment log. Only mark the migration complete once all expected data conditions are met.

## 10. Versioning GRANTs, Roles, and Database Privileges

Privileges are also part of the schema contract. If a new package needs to read a table in another schema, the migration must grant the appropriate direct object privileges to the package owner. If a runtime user needs to call the package, grant `EXECUTE` or the corresponding role.

Example:

```sql
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;

GRANT EXECUTE
ON app_owner.order_api
TO app_runtime_role;
```

Never grant broad administrative privileges such as `DBA`, `SELECT ANY TABLE`, or `CREATE ANY PROCEDURE` just to avoid deployment errors. Grant exact privileges based on the object and execution context.

### 10.1. Direct Grants for Stored PL/SQL

With definer-rights PL/SQL, session roles are disabled during unit execution. If a package owner needs to access objects in another schema, grant privileges directly to the owner as required. Therefore, the `GRANT` migration must precede the package compilation migration or occur before the package is invoked.

### 10.2. GRANT and REVOKE Must Be Reviewed

Privilege changes can widen or narrow the access surface. Reviews should ask:

- Is the grantee a user, a role, or `PUBLIC`?
- Which objects are being accessed?
- Can privileges be granted at the column level?
- Are `WITH GRANT OPTION` or `WITH ADMIN OPTION` actually needed?
- Does the runtime user truly need DDL privileges?
- Are there old privileges to revoke, and how does that affect the grant chain?

### 10.3. Managing Privileges Per Environment

Some grants are identical across all environments; certain privileges or directory paths vary per environment. Do not create a single shared migration containing environment-specific passwords, hosts, paths, or admin users. Use managed placeholders/configuration or separate reviewed bootstrap scripts.

## 11. Repeatable Migrations and CREATE OR REPLACE

Objects such as views, packages, procedures, and functions can often be replaced via `CREATE OR REPLACE`. That is why they fit repeatable migrations in some tools.

View example:

```sql
CREATE OR REPLACE VIEW app.v_paid_orders AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_status = 'PAID';
```

Package body example:

```sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
    PROCEDURE mark_paid(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE app.orders
        SET order_status = 'PAID'
        WHERE order_id = p_order_id;
    END mark_paid;
END order_api;
/
```

### 11.1. Exercise Caution with Replace

`CREATE OR REPLACE` is not always impact-free. Changing a package spec can invalidate dependent objects. Changing a view can break client contracts if column counts or data types change. Changing a trigger can alter DML side effects.

Therefore, repeatable migrations do not mean any definition can be changed without versioning or review. Public API changes must be treated as application compatibility changes.

### 11.2. Compile Errors and Warnings

After deploying PL/SQL, check object statuses and `USER_ERRORS`/`DBA_ERRORS`. Some compile errors may only appear when dependencies or privileges are missing. Pipelines should fail if required objects remain `INVALID` or have compilation errors.

## 12. SQL*Plus, SQLcl, and PL/SQL Delimiters

Oracle SQL scripts have specific quirks when run through command-line clients:

- DML statements end with `;`.
- PL/SQL blocks usually end with `END;` followed by `/` on its own line to submit the block.
- `/` is a SQL*Plus/SQLcl command, not an SQL token sent to the database.
- Migration tools may have their own rules for recognizing statement delimiters.

Script example:

```sql
CREATE OR REPLACE PROCEDURE app.rebuild_summary AS
BEGIN
    NULL;
END;
/
```

If a migration tool does not recognize the slash delimiter, it may pass `/` in the JDBC statement and cause a syntax error. If the tool splits on every `;`, the package body will be broken into multiple invalid statements. Configure delimiters or statement splitting according to the tool's documentation and verify with integration tests running the actual scripts.

### 12.1. Do Not Mix SQL*Plus Commands into JDBC SQL

Commands like `SET SERVEROUTPUT ON`, `PROMPT`, `WHENEVER SQLERROR`, and `SPOOL` are client commands, not SQL sent over JDBC. A file that runs in SQLcl may not run verbatim through Flyway/Liquibase JDBC.

If a script must run via SQL*Plus/SQLcl, specify that tool explicitly in the deployment pipeline. If it must run via a JDBC migration tool, keep the file in syntax supported by the tool.

## 13. Verifying the Schema After Migration

Migration history shows which files the tool executed, but does not always prove every database object matches its expected definition. A DBA might make manual edits afterward, or a deployment could be interrupted.

### 13.1. Checking Object Status

```sql
SELECT object_type,
       status,
       COUNT(*) AS object_count
FROM user_objects
GROUP BY object_type, status
ORDER BY object_type, status;
```

Find invalid objects:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
```

### 13.2. Checking Constraints

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM user_constraints
ORDER BY table_name, constraint_type, constraint_name;
```

### 13.3. Checking Indexes

```sql
SELECT index_name,
       table_name,
       status,
       uniqueness
FROM user_indexes
ORDER BY table_name, index_name;
```

### 13.4. Checking Migration History

For Flyway, inspect the schema history table according to the project's schema/configuration. For Liquibase, inspect `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`. These tables are tool metadata; do not edit them manually to force a migration to pass without understanding the actual state.

### 13.5. Schema Drift

Schema drift is the difference between the actual database and the expected definition in the repository. Drift can arise from:

- Manual hotfixes in production that are never committed back.
- Scripts run outside the migration tool.
- Migrations run in one environment but skipped in another.
- Operators modifying grants, indexes, or packages.
- Edited tool history or a database restored from a snapshot at a different point in time.

To control drift, restrict direct DDL, audit changes, periodically compare metadata/DDL, and bring all hotfixes into Git via corresponding migrations. Do not automatically overwrite production just because a schema diff reports differences; first understand why they differ and assess the impact.

## 14. Rollback, Roll Forward, and Error Recovery

Database rollback is usually more complex than application rollback because schema/data may already have changed and new transactions may already be using the new structure.

### 14.1. Rollback Scripts Are Not Always Safe

For example, a migration adds a column:

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

A rollback might be:

```sql
ALTER TABLE orders DROP COLUMN payment_reference;
```

However, if the new application has already written data into that column, rolling back will cause data loss. Therefore, being able to write an inverse DDL statement does not mean a rollback is safe from a business perspective.

### 14.2. Roll Forward

For Oracle production, a safer strategy is usually creating a new migration to fix the current state:

```sql
-- V008__correct_payment_reference_length.sql
ALTER TABLE orders MODIFY payment_reference VARCHAR2(200);
```

The new migration records the change and preserves history. If the prior migration already ran in some environments, do not edit the old file and leave environments with divergent histories.

### 14.3. Distinguishing Application Rollback from Database Rollback

You can roll back the Java version while keeping the new column in the schema if the schema change is backward compatible. This is a key benefit of expand-and-contract.

Example:

1. Add nullable column `PAYMENT_REFERENCE`.
2. Deploy new code that writes to the new column while old code can ignore it.
3. Shift traffic and verify.
4. Only in a later release drop the old column or tighten constraints.

If a schema change breaks the old code immediately, rolling back the application may fail. Therefore, assess compatibility between application versions N and N-1.

### 14.4. Mid-Execution DDL Failure

If a migration has multiple DDL statements and fails on the third statement, the first two may already have committed. Recovery procedure:

1. Halt deployment so dependent migrations do not continue running.
2. Check tool logs and identify the last statement that succeeded.
3. Inspect actual objects/constraints/indexes in Oracle.
4. Check whether migration history recorded a failure.
5. Create an appropriate repair/forward-fix plan.
6. Only re-run once the schema has been brought to the expected state.
7. Document the incident and update migrations/tests if needed.

Do not delete rows from the migration history table or repeatedly re-run scripts via trial-and-error in production.

## 15. Expand-and-Contract for Zero-Downtime Deployments

When an application has multiple instances or requires rolling deployments, database and application code can coexist across multiple versions. Migrations should ensure old and new code both work during the transition period.

### 15.1. Adding a New Column

Suppose you are migrating from `CUSTOMER_NAME` to `DISPLAY_NAME`:

**Expand:**

```sql
ALTER TABLE customers ADD display_name VARCHAR2(200);
```

Deploy code that reads `DISPLAY_NAME` if present and falls back to `CUSTOMER_NAME`; when writing, write to both columns during the transition period.

Backfill data:

```sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;

COMMIT;
```

Once all instances run the new code and data is reconciled, switch reads/writes completely to `DISPLAY_NAME`.

**Contract:** in a later release, confirm no consumers still use `CUSTOMER_NAME`, then drop the old column.

### 15.2. Safely Adding NOT NULL

Adding a `NOT NULL` column to a large table may require defaults/backfilling and has version-dependent impact. A phased rollout approach:

1. Add the column as nullable.
2. Deploy code that always writes the new value.
3. Backfill existing rows in batches.
4. Verify no NULLs remain.
5. Add a constraint or alter the column to NOT NULL in a manner appropriate for the version/workload.

This avoids a sudden, massive change during peak hours.

### 15.3. Changing Enums/Reference Data

If Java code needs a new status `REFUNDED`, insert the code into the reference table before deploying code that begins writing that status. If new code runs before the seed, foreign keys or validation may reject the data.

When removing an old status, wait until all instances and consumers stop using it. This is also expand-and-contract at the reference data level.

## 16. Managing Reference Data Across Environments

Reference data may differ across environments. For instance, certain test codes exist only in development/test, whereas production has business codes configured by operations.

Separate them into:

- **Shared seed:** mandatory codes required for the application to behave identically across environments.
- **Test-only seed:** fixture data that must never be deployed to production.
- **Environment-specific configuration:** values that differ by environment, injected via config/secrets or controlled migration parameters.
- **Operationally managed data:** data managed by admins/business teams, never overwritten by migrations.

Never place passwords, production endpoints, API keys, or real personal data in seed scripts. Use synthetic data and test-only domains.

### 16.1. Seed Data Must Have Ownership

Every reference table should define who owns its data:

| Data | Owner | Change Mechanism |
|---|---|---|
| Code-defined order statuses | Development/database team | Versioned migration |
| Operational feature flags | Operations/product | Config management or admin UI |
| Standard country list | Data governance | Import/versioned reference process |
| Test customers/orders | Test suite | Dedicated fixtures, cleaned up after tests |

Without clear ownership, migrations and admin actions can overwrite each other.

### 16.2. Do Not Hard-Code Auto-Increment IDs for All References

For reference codes with stable meaning, using natural codes like `PAID` and `CANCELLED` is usually easier to deploy than sequence IDs that vary across environments. If the schema uses surrogate keys, ensure code-to-ID mappings are created consistently and the application does not assume specific IDs across environments unless that is a managed contract.

## 17. CI/CD Workflow for Database Migrations

A basic pipeline may include:

```text
Developer creates migration in Git
              |
              v
       Pull request review
              |
              v
   Static checks / SQL linting
              |
              v
 Provision Oracle test database
              |
              v
   Run all migrations from zero
              |
              v
    Run upgrade from prior version
              |
              v
     Compile PL/SQL and validate
              |
              v
       Seed and integration tests
              |
              v
     Build deployment artifact
              |
              v
   Deploy to staging / approval
              |
              v
       Deploy to production
              |
              v
   Verify history, objects and app
```

### 17.1. Testing from an Empty Database

Creating a fresh database/schema and running all migrations from scratch helps catch:

- Migrations missing dependencies.
- PL/SQL files with broken delimiter handling.
- Missing reference seeds.
- Insufficient grants.
- Scripts relying on pre-existing objects not created in the repository.

### 17.2. Testing Upgrades from an Older Version

Building fresh from zero is not enough. Production usually contains data and a schema at an older version. The pipeline should restore/clone a database with a representative structure and data volume, then run migrations from the old version to the new version.

This uncovers long locks, data conversion errors, constraints that fail validation, and inadequate backfill durations.

### 17.3. Verifying PL/SQL After Migration

Pipelines can query `USER_OBJECTS` and `USER_ERRORS` to fail if critical packages/views/procedures remain invalid or have compile errors. Afterward, run smoke tests invoking key database APIs.

### 17.4. Do Not Let Every Application Instance Run Migrations

If every Spring Boot instance starts up and runs migrations itself, ensure the migration tool uses locking so only one process applies changes at a time. In production, many organizations use a dedicated deployment job to run migrations before rolling out the application. This separates DDL privileges from the runtime account and gives better control over deployment timing.

Runtime users usually do not need `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE` privileges. Separating the migration user and runtime user reduces application privileges.

## 18. Safe Multi-Environment Deployment

Development, test, staging, and production must receive the same migration artifact while using separate connection configurations and privileges.

| Environment | Purpose | Controls |
|---|---|---|
| Local development | Developers test changes | Dedicated schema, fast reset, synthetic data |
| CI database | Automated verification | Fresh build and upgrade tests, torn down after run |
| Integration/test | Multi-service testing | Consistent migrations, controlled seeding |
| Staging | Production simulation | Near-production data volume/structure, deployment rehearsal |
| Production | Real data | Change approval, backup/restore plan, monitoring, and runbook |

### 18.1. Same Artifact, Different Configuration

Migrations should describe identical schema changes across environments. Values like hosts, passwords, directory paths, or environment-specific tablespaces should be managed via configuration/placeholders per the tool's policy.

Avoid manually editing migration files solely for production. If different behavior is required, use controlled configuration or clearly documented conditional migrations.

### 18.2. Deployment Privileges

You can use:

- A migration account with the required DDL privileges.
- A runtime account with only the required DML/EXECUTE privileges.
- A DBA/operator account for specialized administrative operations.

Never store migration credentials in the repository. CI fetches secrets at runtime from a secret manager and never prints them to logs.

### 18.3. Audit and Change Records

Each deployment should record:

- Git commit/tag or artifact version.
- List of executed migrations.
- Target database/service/PDB.
- Start/end timestamps.
- Outcome and errors.
- Approver or approving pipeline.
- Results of object, constraint, and PL/SQL verification.

This links source code changes to database changes during incident investigations.

## 19. Handling Production Hotfixes

Sometimes an emergency fix must be applied directly in production under change management procedures. If a hotfix occurs, do not let it remain outside Git.

The process should be:

1. Record the exact DDL/PLSQL executed and the approver.
2. Save the hotfix script into the repository immediately after resolution.
3. Create a new migration version describing the state required in other environments.
4. Test the migration on a clone or staging environment with a near-production schema.
5. Mark the production environment as having received the corresponding change following the migration tool's proper workflow.
6. Compare schemas to catch any remaining discrepancies.

Do not edit old migrations to pretend production followed the same history as other environments. If production was manually hotfixed, perform explicit reconciliation so tool history and schema state do not conflict.

## 20. Schema Drift and DDL Comparison

Version control alone does not prevent drift if users can still run out-of-band DDL. Combine it with:

- Restricting DDL privileges in production.
- Auditing DDL or using an appropriate change tracking mechanism.
- Periodically comparing DDL between the repository and the database.
- Checking invalid objects, constraint statuses, and grants.
- Bringing all hotfixes back into migration history.

Oracle provides `DBMS_METADATA` to extract object DDL. Example:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM dual;
```

You can use `DBMS_METADATA.GET_DDL` for packages, views, indexes, and other objects by object type. Output must be normalized before diffing because storage clauses, tablespaces, segment attributes, and metadata may differ across environments even when schemas are logically equivalent.

Do not extract production DDL and overwrite the repository without review. A diff is evidence for investigation, not a safe auto-sync command.

## 21. Oracle Edition-Based Redefinition and Online Changes

For systems requiring high availability, Oracle Edition-Based Redefinition (EBR) can help deploy application/database changes by edition, reducing application downtime. EBR uses editions to maintain multiple versions of PL/SQL objects and editioning views using Oracle-supported mechanisms.

EBR is not a migration tool feature and does not fit every schema. It requires designing editionable objects, editioning views, cross-edition triggers, or corresponding synchronization mechanisms depending on the change type.

Core principles:

- Design the schema to be editionable upfront.
- Identify which objects are editionable and which are noneditionable.
- Manage editions and deployment order with version-controlled scripts.
- Test sessions in both old and new editions.
- Plan how to switch services/sessions to the new edition and retire old editions.

When not using EBR, expand-and-contract remains the standard approach for deploying compatible schemas during rolling deployments.

## 22. Managing Indexes and Constraints in Releases

Indexes and constraints can significantly affect deployment duration. A migration adding an index on a large table can consume substantial I/O and CPU and contend with application workloads.

### 22.1. Creating Indexes

```sql
CREATE INDEX ix_orders_customer_date
    ON app.orders(customer_id, order_date);
```

Before creating an index, inspect the query workload, cardinality, column order, and existing indexes. Do not create duplicate or near-duplicate indexes without evaluation.

Depending on the version/edition and conditions, you can use online index creation:

```sql
CREATE INDEX ix_orders_customer_date
    ON app.orders(customer_id, order_date)
    ONLINE;
```

`ONLINE` does not eliminate all locks or overhead. Verify syntax, limitations, and licensing/edition support for the environment.

### 22.2. Adding Foreign Keys to Tables with Existing Data

If a large table already contains data, adding an FK with validation must verify existing rows. If orphan rows exist, the command fails. Before the migration, run queries to check for orphan rows and plan data cleanup.

Oracle supports `ENABLE NOVALIDATE` in certain strategies to enforce constraints on new DML without validating all historical data immediately; validation can then run separately. However, this is a temporary state that must be tracked so teams do not forget to validate in test/production.

### 22.3. Constraints and Indexes

Primary key/unique constraints typically rely on indexes to enforce uniqueness. When a migration creates a constraint, Oracle may create an index or use a suitable existing index. Avoid creating redundant indexes alongside indexes backing constraints.

## 23. Common Mistakes in Database Version Control

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Flyway checksum mismatch | An already-executed migration file was modified | Restore the historical file; create a new migration; only run repair under controlled procedures |
| Migration reports object already exists | Script partially executed or environment drifted | Inspect objects and history; do not add `IF EXISTS` assuming unsupported syntax |
| PL/SQL object INVALID | Missing dependency, compile error, or missing direct privilege | Inspect `USER_ERRORS`, dependencies, and grants |
| Package body fails to compile after deploy | Incompatible change in package spec or type | Deploy in dependency order and recompile |
| FK migration fails | Existing data has orphan rows or parent is not yet created | Check data and dependencies before enabling validation |
| Seed duplicate key | Migration re-ran or data was created manually | Define ownership; use versioned one-time inserts or intentional upserts |
| Migration passes in dev but fails in prod | Different data volume, privileges, edition/version, or object state | Test upgrades on a clone with near-production data |
| DDL partially executes then fails | Oracle implicit commit | Inspect each object's state and create a repair/forward migration |
| Runtime app errors after schema deploy | Code and schema incompatible during rolling deployment | Use expand-and-contract and verify N/N-1 compatibility |
| Drift across environments | Hotfix or manual changes outside Git | Audit, run schema diff, and capture hotfixes in migrations |
| PL/SQL script split incorrectly | Migration tool does not recognize slash delimiter | Configure statement splitting properly for Oracle PL/SQL |
| Concurrent migration runs | Multiple app instances start migrations simultaneously | Use tool locking or a dedicated deployment job |

## 24. End-to-End Workflow from Requirement to Production

A database change can follow these steps:

1. **Requirement analysis:** identify objects, data, APIs, and compatibility requirements to change.
2. **Migration design:** choose DDL, data migrations, PL/SQL, and grants; map dependencies.
3. **Create files in Git:** assign version, file name, and directory per convention.
4. **Review:** DBAs/developers evaluate locks, storage, data loss, privileges, and rollback/forward strategy.
5. **Test from zero:** build a fresh schema, run all migrations and seeds.
6. **Test upgrade:** run from the previous version with representative data.
7. **Compile/validate:** check object status, constraints, and reference data.
8. **Integration test:** run the application with the runtime account and corresponding services.
9. **Deploy to staging:** measure timing and verify the runbook.
10. **Deploy to production:** use a migration job, dedicated credentials, and an appropriate change window.
11. **Verify:** check history, object statuses, invalid PL/SQL, data checks, and the application.
12. **Reconcile:** bring any hotfixes or operational changes back into version control.

## 25. Checklist for a Database Pull Request

| Item | Question to Answer |
|---|---|
| Scope | Which objects are created, modified, or dropped? |
| Version | Is the migration version unique and compliant with conventions? |
| Immutability | Were any files already executed in shared environments modified? |
| Dependency | Are tables, types, package specs/bodies, views, and grants ordered correctly? |
| DDL behavior | Are there implicit commits, locks, or table rewrites? |
| Data migration | Are scope limits, batch size, undo/redo, and retry strategies defined? |
| Reference data | Is data owned by code or operations; does it overwrite environment data? |
| PL/SQL | Are script delimiters correct; were compile errors checked? |
| Privileges | Are direct grants, roles, and runtime access minimal? |
| Compatibility | Can old and new code run concurrently during rollout? |
| Recovery | If it fails midway, how is schema state identified and repaired? |
| Testing | Was it tested both on a fresh schema and as an upgrade from the prior version? |
| Evidence | Are migration logs, schema history, and verification results captured? |
| Environment | Are sensitive credentials, hosts, and paths excluded from Git? |

Managing DDL, PL/SQL, and reference data with version control turns the database into a reviewable, testable, and reproducible part of the product. In Oracle, migrations must be designed around dependencies, account for implicit DDL commits, keep executed migrations immutable, and use new migrations to fix state. PL/SQL must be deployed with proper delimiters and compile dependencies; reference data needs clear ownership and code-compatible ordering; large data migrations require batching and reconciliation. Combining Git, migration tools, CI databases, and expand-and-contract deployment practices keeps environments consistent and makes database changes as traceable as application changes.
