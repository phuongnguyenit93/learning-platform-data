# Edition-Based Redefinition, Editioning Views, and Cross-Edition Triggers

Oracle Edition-Based Redefinition (EBR) enables upgrading applications and data access structures while the database continues serving active sessions. EBR allows multiple versions of certain schema objects to coexist across different **editions**. Old sessions keep using the old object versions; new sessions switch to the new edition. While both versions operate concurrently, an **editioning view** provides the column interface over a table and **cross-edition triggers** synchronize DML between old and new structures.

EBR is useful when a release must modify PL/SQL, views, or data representations without shutting down the entire application for an upgrade. It supports phased rollouts, testing the new version live, and controlled traffic cutover.

This lesson uses Oracle Database 19c as its baseline, focusing on:
- Edition models, edition hierarchies, and editioned objects.
- Enabling editions on schemas, creating editions, and selecting editions for sessions/services.
- Editioning views and decoupling application interfaces from base tables.
- Forward and reverse cross-edition triggers.
- Online upgrade workflows including backfilling, validation, cutover, and cleanup.
- Managing old/new sessions, rollbacks, and compatibility.
- Data dictionary views, privileges, limitations, and troubleshooting.
- SQL/PLSQL examples, migration scenarios, labs, and operational checklists.

EBR does not create a physical copy of tables per edition. Tables remain shared data structures; editioned objects such as PL/SQL units and views can have distinct versions per edition. Therefore, data synchronization must be carefully designed when two application versions write concurrently.

## 1. The Zero-Downtime Application Upgrade Problem

Suppose application version 1 uses table `EMPLOYEES` with column `SALARY`. Version 2 needs to logically rename the column to `BASE_SALARY` while also updating the payroll processing package.

Modifying the table and package in-place in a single rollout risks:
- Running version 1 sessions hitting newly altered objects mid-flight.
- Old code querying renamed or dropped columns.
- New sessions rolling out asynchronously across connection pools.
- DML from old versions failing to populate new columns.
- Application rollback failing because the schema switched completely to the new layout.

EBR solves this by maintaining two editions:

~~~text
                    ORA$BASE
                       |
                 APP_EDITION_V1
                       |
                 APP_EDITION_V2
                    /       \
             Old sessions  New sessions
             old package   new package
             old view      new view
                    \       /
                  Shared base table
             salary | base_salary
                       |
                Cross-edition triggers
                  synchronize DML
~~~

During transition:
- Old sessions resolve packages/views via the old edition.
- New sessions resolve packages/views via the new edition.
- The shared base table can hold both old and new columns.
- Cross-edition triggers keep both representations synchronized.
- Once old sessions drain, backward compatibility can end and old structures can be cleaned up in a later release.

## 2. Editions and Edition Hierarchy

### 2.1. What Is an Edition?

An edition is a versioned namespace inside the database. When a session executes in an edition, Oracle resolves editioned objects according to the current edition and its inheritance chain.

A new edition is typically created as a child of the currently active edition. It inherits any editioned objects not yet overridden in the child edition. When a new version of an object is created in the child edition, child-edition sessions see the new version; parent-edition sessions continue seeing the old version.

An edition is NOT:
- A new schema/user.
- A new database.
- A datafile copy.
- An independent copy of tables.
- A transaction or data snapshot.

Multiple editions can reference the exact same physical base table. They differ in which object versions are resolved and which data interface the application sees.

### 2.2. Edition Hierarchy

Editions form a parent/child tree. A database typically starts with root edition `ORA$BASE`. A release can create a child edition:

~~~sql
CREATE EDITION app_v2 AS CHILD OF ora$base;
~~~

Across multiple upgrades, child editions branch off the active release edition:

~~~sql
CREATE EDITION app_v3 AS CHILD OF app_v2;
~~~

A child edition inherits objects from its parent until given its own version inside the child. Creating an edition does not copy every object; it creates a branching point in the versioning mechanism.

Avoid spawning unplanned edition branches. Name editions after releases, record parent editions, and maintain a clear cleanup roadmap.

### 2.3. Current Session Edition

Check which edition the current session is using:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition
FROM dual;
~~~

Switch the current session's edition:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

This command affects only the current session. Other sessions—even within the same connection pool—may still remain on the old edition.

Applications should specify the edition when creating sessions or connect via a database service configured with an edition. Never assume changing the default edition automatically switches already-connected sessions.

## 3. Enabling Editions on Schemas and Creating Editions

### 3.1. Prerequisites

To use EBR:
- Database release supports EBR.
- The schema owning editioned objects has editions enabled.
- Admin users hold privileges to create editions and manage objects.
- Applications connect to the right schema and edition.
- Table changes are designed compatibly during multi-version coexistence.

Enable editions on the application schema:

~~~sql
ALTER USER app_owner ENABLE EDITIONS;
~~~

Execute using an appropriately privileged admin account. This is a schema configuration change; plan ahead before deploying and verify existing objects per release documentation.

### 3.2. Creating an Edition

Example creating a new edition from the current edition:

~~~sql
CREATE EDITION app_v2 AS CHILD OF ora$base;
~~~

Creating editions typically requires system privileges such as `CREATE ANY EDITION`. Edition administration must follow DBA and change management procedures.

### 3.3. Granting Use on an Edition

Grant `USE` on the edition to users needing to connect to it:

~~~sql
GRANT USE ON EDITION app_v2 TO app_owner;
~~~

This grants permission to use the specified edition. It does not replace object privileges such as `SELECT`/`INSERT`/`UPDATE` or package execution rights.

### 3.4. Selecting an Edition for a Session

Once granted:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

Verify:

~~~sql
SELECT
    USER AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition
FROM dual;
~~~

### 3.5. Default Edition

The database has a default edition for sessions not routed to a specific edition. DBAs can manage the default edition as part of release procedures, for example:

~~~sql
ALTER DATABASE DEFAULT EDITION = app_v2;
~~~

Changing the default edition only affects new sessions using the default mechanism; already-connected sessions keep their current edition. Before changing it, check which users/services specify explicit editions and prepare rollback steps.

## 4. Editioned Objects vs. Noneditioned Objects

### 4.1. Editioned Objects

Certain schema object types can be versioned per edition, typically including:
- PL/SQL procedures and functions.
- Packages and package bodies.
- Triggers.
- Views, including editioning views.
- Synonyms.
- Types and certain other object types depending on release.

When a new version is created in a child edition, Oracle preserves the parent version for parent-edition sessions.

### 4.2. Noneditioned Objects

Tables are noneditioned objects. Physical base tables are shared across editions. Several other object types are also noneditionable; the exact list depends on the Oracle release.

This has an important consequence: altering a base table's structure can impact every edition. EBR does not automatically create two versions of a table.

For example:
- Adding a new column is usually compatible with old code if old columns remain untouched.
- Dropping or renaming an old column while old sessions still run breaks old code.
- Changing constraints or data types requires evaluating impact across all active application versions.

### 4.3. Object Inheritance

When a session in a child edition accesses an object that has no version in the child, Oracle resolves to the version inherited from the parent edition. Once the object is created or replaced in the child, the child's own version is used there.

This avoids recompiling or copying the entire schema on every new release. However, monitor invalid objects and dependencies after every change.

### 4.4. Object Editionability

Inspect object metadata:

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    status,
    editionable
FROM user_objects
ORDER BY object_type, object_name;
~~~

For versions across multiple editions, query views suffixed with `_AE` such as `DBA_OBJECTS_AE` or `ALL_OBJECTS_AE` to inspect across editions if permitted.

Do not attempt to create editioned versions of unsupported object types. Consult the SQL Language Reference and EBR Guide for your exact release before selecting objects in your design.

## 5. Editioning Views

### 5.1. Purpose

An editioning view (EV) is a specialized view layer giving each edition a column interface over a base table tailored to that application version.

Applications should access the editioning view rather than accessing the base table directly. When physical layout evolves, DBAs can deploy a new EV version in the new edition while the old edition preserves the old interface.

Example:
- The base table has both `SALARY` and `BASE_SALARY`.
- The old edition has an EV exposing only `SALARY`.
- The new edition has an EV exposing only `BASE_SALARY`.
- The same view name is versioned across editions while the physical table remains singular.

### 5.2. Creating an Editioning View

Example table:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);
~~~

In the old edition, create the editioning view:

~~~sql
CREATE EDITIONING VIEW employees_ev AS
SELECT
    employee_id,
    salary,
    department_id
FROM employees;
~~~

Old code queries `EMPLOYEES_EV` and continues seeing the `SALARY` column.

### 5.3. Restrictions on Editioning Views

Editioning views impose strict rules so Oracle can map DML directly onto a single base table. Typical rules:
- Based on a single base table.
- Selected columns are direct references to base table columns.
- Columns may be aliased/renamed in the view projection.
- No joins, `GROUP BY`, aggregates, or computed expressions allowed in ordinary views.
- No row-filtering predicates in the editioning view definition.
- Cannot aggregate multiple tables.

If joins, filters, or computations are needed, layer an ordinary view on top of the editioning view or use an API/query layer. Verify exact restrictions in the SQL Language Reference for your release.

### 5.4. DML Through Editioning Views

Editioning views are built to pass simple DML straight to the base table. Example:

~~~sql
INSERT INTO employees_ev (employee_id, salary, department_id)
VALUES (1001, 5000, 10);

UPDATE employees_ev
SET salary = 5200
WHERE employee_id = 1001;
~~~

DML maps to the corresponding base table columns. Cross-edition triggers on the base table can synchronize old/new columns during transition.

### 5.5. Access Privileges

A sound design typically:
- Grants `SELECT`/`INSERT`/`UPDATE`/`DELETE` on the editioning view to the application user.
- Restricts or omits direct DML grants on the base table for the application user.
- Reserves base table alteration rights for the schema owner/DBA.
- Prevents application code from depending on physical columns not exposed by the editioning view.

The view layer only delivers value if the application actually uses it. If the application issues DML directly against the base table, much of EBR's schema isolation benefit is lost.

## 6. Compatible Table Structure Changes

Because tables are not versioned per edition, structural upgrades typically follow the expand-and-contract pattern:

1. **Expand:** add new columns or structures while old code continues running.
2. **Bridge:** create cross-edition triggers to sync changes between old and new columns.
3. **Backfill:** copy existing data to the new representation.
4. **Switch:** deploy new code/views and route sessions to the new edition.
5. **Contract:** once zero old sessions remain, drop old triggers/columns in a later release.

Never rename or drop old columns in the initial step. The goal is preserving compatibility while old and new versions run concurrently.

### 6.1. Logical Column Rename Example

Suppose `SALARY` must be replaced by `BASE_SALARY`.

Add the new column to the base table:

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

This modifies the noneditioned table, so both old and new editions see the physical column. However, the old editioning view still exposes only `SALARY`.

### 6.2. Create the New Edition and New View Version

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
ALTER SESSION SET EDITION = app_v2;
~~~

In the new edition, replace the editioning view:

~~~sql
CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT
    employee_id,
    base_salary,
    department_id
FROM employees;
~~~

In the new edition, the application sees `BASE_SALARY`. Sessions in the old edition still see the old EV exposing `SALARY`.

Running `CREATE OR REPLACE` inside the child edition creates/replaces the version in the active edition; be careful not to run it in the parent edition by mistake.

## 7. Cross-Edition Triggers

### 7.1. Why Are Triggers Needed?

During transition, old and new sessions may write to the same base table concurrently using different columns.

If you merely add a column and backfill once:
- Old sessions can keep updating the old column after the backfill.
- The new column becomes stale.
- New sessions can write the new column while old code still reads the old column.
- Both representations diverge.

Cross-edition triggers synchronize DML between old and new data representations while two editions coexist.

### 7.2. Forward Cross-Edition Triggers

A forward trigger propagates changes from old code/edition to the new structure. For instance, when an old session updates `SALARY`, the trigger writes the corresponding value into `BASE_SALARY`.

~~~sql
CREATE OR REPLACE TRIGGER employees_forward_ct
BEFORE INSERT OR UPDATE ON employees
FORWARD CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.base_salary := :NEW.salary;
END;
/
~~~

This example illustrates a one-to-one column mapping. Verify syntax, trigger-owning edition, and firing rules against your Oracle release. Oracle distinguishes `FORWARD` cross-edition triggers from standard DML triggers.

### 7.3. Reverse Cross-Edition Triggers

A reverse trigger propagates changes from the new version back into the form old code understands. When a new session updates `BASE_SALARY`, the trigger updates `SALARY`:

~~~sql
CREATE OR REPLACE TRIGGER employees_reverse_ct
BEFORE INSERT OR UPDATE ON employees
REVERSE CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.salary := :NEW.base_salary;
END;
/
~~~

Reverse triggers are helpful when old-edition sessions remain active while the new edition starts writing. Once all old sessions have drained, reverse syncing is no longer required.

### 7.4. Enabling and Disabling Triggers

Cross-edition triggers can be created `DISABLE`d in preparation before cutover. Enable once verified:

~~~sql
ALTER TRIGGER employees_forward_ct ENABLE;
ALTER TRIGGER employees_reverse_ct ENABLE;
~~~

Trigger states must be managed as part of the release runbook. Never enable triggers before confirming target columns, mappings, and data are ready.

### 7.5. Triggers Must Be Idempotent and Controlled

In complex migrations:
- Clearly define which edition holds authoritative data at each stage.
- Ensure forward and reverse triggers do not unexpectedly overwrite each other.
- Avoid issuing recursive DML against the same table from inside triggers.
- Keep trigger logic concise, deterministic, and auditable.
- Handle `NULL`s, defaults, datatype conversions, and validation errors.
- Check trigger firing order relative to existing triggers.
- Measure redo/latency overhead introduced by trigger execution.

Cross-edition triggers do not replace backfilling. They maintain sync for DML occurring while two editions coexist.

## 8. End-to-End EBR Workflow

An online upgrade should follow distinct phases.

### 8.1. Preparation Phase

- Identify editioned objects vs. noneditioned objects.
- Enable editions on the schema beforehand.
- Record the current edition and object dependencies.
- Design base table changes using expand-and-contract.
- Create backfill and reconciliation plans.
- Prepare privileges, services, connection pools, and rollbacks.
- Define the maximum coexistence window.

### 8.2. Expand the Base Table

Add new columns or structures while the old version keeps running:

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

Do not drop `SALARY` in this phase.

### 8.3. Create the Child Edition

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
GRANT USE ON EDITION app_v2 TO app_owner;
~~~

Then switch the deployment session to the new edition:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

### 8.4. Create New Versions of Editioning Views and PL/SQL

In the new edition:
- Replace the EV to expose `BASE_SALARY`.
- Create packages/procedures/functions compatible with the new schema.
- Compile and check dependencies.
- Do not route production traffic before smoke testing.

### 8.5. Create and Enable the Forward Trigger

Create the forward trigger so DML from the old edition keeps populating the new column. Enable it per the change plan before or right as backfilling begins, leaving zero gap where old DML is missed.

### 8.6. Backfill Historical Data

Migrate existing values:

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;
~~~

This example assumes `SALARY` is always populated and `BASE_SALARY IS NULL` identifies unbackfilled rows. If `NULL` is a valid value, use a migration marker or explicit distinguishing logic.

For large tables:
- Run by primary-key range or batches.
- Commit in controlled batches.
- Monitor undo, redo, locks, and elapsed time.
- Support resumability.
- Avoid running one giant transaction if it causes undo pressure.
- Reconcile remaining unbackfilled rows after each batch.

### 8.7. Create the Reverse Trigger

Before opening the new edition for writes, create/enable the reverse trigger if old sessions still need to read the old column. This keeps both representations synchronized when the new application updates `BASE_SALARY`.

### 8.8. Pre-Cutover Verification

- Compare row counts.
- Compare `SALARY` and `BASE_SALARY` row-by-row.
- Check `NULL`s and out-of-range values.
- Confirm triggers are `ENABLED`.
- Confirm new packages/views are `VALID`.
- Run integration tests inside the new edition.
- Check which editions active sessions are using.
- Confirm rollback paths and service routing.

### 8.9. Cutover

Route new sessions to the new edition. Use an edition-configured service or set the session edition on connect.

Existing open sessions do not switch editions automatically. Let them run for a bounded window, then drain/close them per plan.

### 8.10. Drain the Old Edition

Monitor old-edition session counts, in-flight requests, long transactions, and connection pools. End the compatibility phase only when zero sessions/workers require the old edition and data is verified.

### 8.11. Contract and Cleanup

Once zero legacy consumers remain:
- Disable/drop unneeded cross-edition triggers.
- Update final views/packages.
- Drop the old column in a separate change once dependencies are gone.
- Retire old editions once no sessions or dependencies remain.
- Back up before cleanup and record the final release.

Do not drop the old edition immediately after switching services. The old edition is part of your rollback window until you confirm rollback is no longer needed.

## 9. Complete Illustrative Example: SALARY to BASE_SALARY

### 9.1. Initial Schema

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);

CREATE EDITIONING VIEW employees_ev AS
SELECT employee_id, salary, department_id
FROM employees;
~~~

The old version reads and writes `EMPLOYEES_EV.SALARY`.

### 9.2. Expand

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

Keep the `SALARY` column intact.

### 9.3. Create New Edition

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
GRANT USE ON EDITION app_v2 TO app_owner;
ALTER SESSION SET EDITION = app_v2;
~~~

### 9.4. Replace Editioning View in app_v2

~~~sql
CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT employee_id, base_salary, department_id
FROM employees;
~~~

The new version uses `BASE_SALARY`. The EV version in `APP_V1` still exposes `SALARY`.

### 9.5. Sync DML from Old Edition

In the appropriate edition per EBR workflow:

~~~sql
CREATE OR REPLACE TRIGGER employees_forward_ct
BEFORE INSERT OR UPDATE ON employees
FORWARD CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.base_salary := :NEW.salary;
END;
/
~~~

Enable when preparing to start coexistence:

~~~sql
ALTER TRIGGER employees_forward_ct ENABLE;
~~~

### 9.6. Backfill Existing Rows

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;
~~~

If the table is very large, run in batches and verify remaining row count:

~~~sql
SELECT COUNT(*) AS rows_not_backfilled
FROM employees
WHERE base_salary IS NULL;
~~~

### 9.7. Sync DML from New Edition

~~~sql
CREATE OR REPLACE TRIGGER employees_reverse_ct
BEFORE INSERT OR UPDATE ON employees
REVERSE CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.salary := :NEW.base_salary;
END;
/
~~~

Enable before the new edition starts writing if the old edition remains active:

~~~sql
ALTER TRIGGER employees_reverse_ct ENABLE;
~~~

### 9.8. Verify Both Columns Match

~~~sql
SELECT COUNT(*) AS mismatched_rows
FROM employees
WHERE salary <> base_salary
   OR salary IS NULL AND base_salary IS NOT NULL
   OR salary IS NOT NULL AND base_salary IS NULL;
~~~

In this example `SALARY` is `NOT NULL`. With real data, use appropriate NULL-safe comparisons and check data types/rounding.

### 9.9. New Application

Code in `APP_V2` queries:

~~~sql
SELECT employee_id, base_salary, department_id
FROM employees_ev
WHERE employee_id = :employee_id;
~~~

Old code continues querying `SALARY` via the old view version. Cross-edition triggers keep both columns synchronized throughout coexistence.

### 9.10. Post-Cutover

Once old sessions have drained:
- Stop reverse synchronization if no old consumers remain.
- Confirm zero dependencies on `SALARY`.
- Schedule a separate contract change to drop the old column.
- Clean up cross-edition triggers and old editions in dependency order.
- Take backups and run regression tests after cleanup.

This example illustrates only a one-to-one column mapping. Real data transformations may require normalization functions, `NULL` handling, rounding, timezones, or historical adjustments; design and test dedicated mappings accordingly.

## 10. Large Data Backfills and Avoiding Race Conditions

### 10.1. Why Does Backfilling Need Triggers?

Suppose backfilling starts at 10:00 and finishes at 10:30. During those 30 minutes, the old application can still update `SALARY`. Without a forward trigger, already-backfilled rows could turn stale and unbackfilled rows could hold outdated values.

The forward trigger ensures every DML from the old edition keeps populating the new column.

### 10.2. Batched Backfilling

Example processing by `employee_id` range:

~~~sql
UPDATE employees
SET base_salary = salary
WHERE employee_id >= :low_id
  AND employee_id < :high_id
  AND base_salary IS NULL;

COMMIT;
~~~

Loop across small ranges and save progress checkpoints. Size ranges based on table size, redo/undo capacity, and lock duration.

### 10.3. Avoid Overwriting Fresh Data

The `BASE_SALARY IS NULL` condition here avoids overwriting rows already updated by triggers or the new application, assuming `NULL` strictly means unbackfilled.

If `NULL` is a valid business value, use a migration marker or separate status flag to distinguish them. Never use naive predicates without understanding data semantics.

### 10.4. Post-Backfill Reconciliation

Count:
- Total rows.
- Unconverted rows.
- Mismatched rows.
- Rows with unexpected `NULL` values.
- Rows updated during the backfill window.

For complex transformations, share the exact same migration function across both backfill and trigger to prevent diverging logic.

## 11. Managing Services and Connection Pools

### 11.1. Session Editions Do Not Switch Automatically

A connection pool may hold connections opened before cutover. Even after the service's default edition switches, existing sessions stay on their current edition until disconnected or handled via supported mechanisms.

Plan for:
- Draining old connection pools.
- Preventing old connections from being reused after cutover.
- Creating new pools/services bound to the new edition.
- Monitoring sessions remaining on the old edition.
- Handling long transactions and background jobs.

### 11.2. Binding Editions to Database Services

Oracle services can be configured so new sessions connecting via that service use a designated edition. Service editions can be managed via `DBMS_SERVICE` in appropriate DBA workflows.

Illustrative example:

~~~sql
BEGIN
    DBMS_SERVICE.MODIFY_SERVICE(
        service_name => 'app_v2_service',
        edition      => 'APP_V2'
    );
END;
/
~~~

Verify service names, privileges, and supported parameters for your release and service management tool (`DBMS_SERVICE`, `srvctl`, or cloud services). Never run illustrative commands in production without confirming existing services and HA configuration.

### 11.3. Inspecting Sessions

Inspect the current edition from inside a session:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME')
FROM dual;
~~~

DBAs can use dynamic performance views and data dictionary views to monitor sessions, services, editions, and connection pools. Capture before/after evidence at cutover.

## 12. PL/SQL Dependencies and Invalid Objects

### 12.1. Edition-Scoped Dependencies

Packages, procedures, and functions can depend on editioning views and other editioned objects. When replacing views or packages in a new edition, compile and test dependencies within that edition.

### 12.2. Compiling and Inspecting

~~~sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Check compile errors:

~~~sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
ORDER BY name, sequence;
~~~

These views reflect the current schema/session context. When inspecting across multiple editions, query cross-edition data dictionary views if permitted.

### 12.3. Never Compile in the Wrong Edition

Before running DDL/compile scripts, verify:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME')
FROM dual;
~~~

Running a script that creates a package in the parent edition can alter the version used by active legacy sessions. Every migration script should log its active edition at startup and fail fast if it is not the expected edition.

## 13. Data Dictionary Views for EBR

### 13.1. Listing Editions

~~~sql
SELECT
    edition_name,
    parent_edition_name
FROM dba_editions
ORDER BY edition_name;
~~~

### 13.2. Objects Across Editions

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    edition_name,
    status
FROM dba_objects_ae
WHERE owner = 'APP_OWNER'
ORDER BY object_name, edition_name;
~~~

`DBA_OBJECTS_AE` lets you inspect object versions across editions. Dictionary read access depends on DBA grants.

### 13.3. Editioning Views

~~~sql
SELECT
    owner,
    view_name,
    table_name
FROM dba_editioning_views
WHERE owner = 'APP_OWNER'
ORDER BY view_name;
~~~

### 13.4. Edition-Enabled Schemas

Check user/schema metadata via release-appropriate dictionary views, for example:

~~~sql
SELECT username, editions_enabled
FROM dba_users
WHERE username = 'APP_OWNER';
~~~

### 13.5. Trigger Metadata

~~~sql
SELECT
    owner,
    trigger_name,
    table_name,
    status,
    triggering_event
FROM dba_triggers
WHERE owner = 'APP_OWNER'
ORDER BY trigger_name;
~~~

Use dedicated cross-edition trigger views if provided by your release and privileges allow; combine trigger metadata with source code and DDL deployment logs to verify `FORWARD`/`REVERSE` direction and owning edition.

## 14. EBR vs. DBMS_REDEFINITION

EBR and `DBMS_REDEFINITION` may appear together in an upgrade project, yet they solve two distinct problems.

| Criterion | Edition-Based Redefinition | DBMS_REDEFINITION |
|---|---|---|
| Goal | Version code/schema interfaces by edition | Change physical table structure online |
| Primary objects | Editioned objects, editioning views, cross-edition triggers | Tables and dependent objects |
| Concurrent code versions | Yes | Not the primary goal |
| Data sync | Cross-edition triggers and migration logic | Internal synchronization during redefinition |
| Physical table | Shared across editions | Builds interim table then syncs/swaps |
| Best fit | Application releases requiring version coexistence | Online structural changes to large tables |

If you only need to alter a table definition or change storage/partitioning, `DBMS_REDEFINITION` may fit better. If two versions of PL/SQL/views must run simultaneously, EBR addresses that directly. Both techniques can be combined per architecture and release plans.

## 15. Limitations and Considerations

- Not all schema objects are editionable.
- Base tables do not have separate versions per edition.
- Table changes can affect every edition.
- Editioning views have stricter definition limits than ordinary views.
- Cross-edition triggers add DML logic and can increase redo/latency.
- Extended coexistence increases testing and operational complexity.
- Object dependencies can cause invalid objects during API changes.
- Certain features, object types, or integrations require release-specific handling.
- EBR does not replace backups, restore drills, or database rollbacks.
- EBR does not automatically roll back business data already written in the new format.

Not every migration needs EBR. For simple, backward-compatible changes where brief downtime is acceptable, a standard rolling deployment is far simpler. Choose EBR when coexistence/online upgrade benefits outweigh the design, trigger, and testing overhead.

## 16. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ORA-38802` | User does not have editions enabled or invalid edition condition | Check edition-enabled schema and DDL operation |
| `ORA-38803` | Edition does not exist or is invalid | Inspect `DBA_EDITIONS` and edition hierarchy |
| `ORA-38804` | Cannot drop edition due to dependencies/child editions | Identify dependencies, child editions, and cleanup order |
| `ORA-38805` | Object cannot be manipulated in current edition context | Verify editionability and session edition |
| `ORA-38818` | Disallowed reference to object in another edition | Check dependencies and edition visibility |
| `ORA-04063` | Package/view has errors | Check `USER_ERRORS`/`DBA_ERRORS` and compile in right edition |
| `ORA-04098` | Trigger invalid upon firing | Check trigger source, dependencies, and compile errors |
| New column `NULL` after backfill | Forward trigger not enabled or backfill incomplete | Check triggers, batch progress, and mismatch query |
| Two columns out of sync | Missing one trigger direction or buggy mapping | Inspect forward/reverse triggers and DML paths |
| New sessions hit old edition | Service/pool not switched | Check service edition and create/drain connection pools |
| Old sessions fail post-deploy | Old column/view dropped or broken incompatibly | Restore compatibility and drain old sessions before contract |
| Cutover cannot roll back | New data cannot be mapped back to old format | Maintain reverse mapping and verify downgrade feasibility |
| Triggers slow down DML | Complex trigger or runs on every row | Simplify mapping, measure contention, and batch backfill |
| Package `VALID` yet app fails | Runtime behavior/API differs across editions | Run integration tests against actual service/edition |

The first error logged in the alert log or client is often more informative than final cascading errors. Record current edition, object owner, object type, and deployment step when errors occur.

## 17. EBR Deployment Runbook

### Pre-Release
- Record current/default edition and edition hierarchy.
- Confirm schemas have editions enabled.
- Inventory editioned and noneditioned objects.
- Define base table changes and compatibility window.
- Design new editioning views.
- Design forward/reverse triggers.
- Estimate backfill, redo, undo, and storage.
- Verify service/connection pool routing.
- Ensure RMAN backups and a rollback plan exist.

### During Deployment
- Expand tables with compatible changes.
- Create the child edition.
- Deploy new view/package versions in the child edition.
- Create and verify cross-edition triggers.
- Enable the forward trigger at the planned moment.
- Backfill in batches.
- Reconcile old/new data.
- Enable the reverse trigger if old sessions remain active.
- Run smoke/integration tests in the new edition.
- Route new sessions/services to the new edition.

### Post-Cutover
- Monitor old and new sessions.
- Monitor trigger errors, invalid objects, and DML latency.
- Reconcile both data representations.
- Drain old pools/sessions.
- Retain the old edition throughout the rollback window.
- Once stable, clean up triggers and old columns in a separate release.
- Back up and update runbooks/edition inventories.

## 18. Lab: Creating Two Editions and an Editioning View

Perform this in an isolated Oracle lab with an appropriately privileged user. Never run these DDL commands on a production schema.

### 18.1. Enable Editions and Create Table

~~~sql
ALTER USER lab_app ENABLE EDITIONS;
~~~

Connect as `LAB_APP` or a DBA executing DDL in that schema:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL
);

CREATE EDITIONING VIEW employees_ev AS
SELECT employee_id, salary
FROM employees;
~~~

### 18.2. Create a New Edition

~~~sql
CREATE EDITION lab_v2 AS CHILD OF ora$base;
GRANT USE ON EDITION lab_v2 TO lab_app;
~~~

### 18.3. Add Column and Replace View in New Edition

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
ALTER SESSION SET EDITION = lab_v2;

CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT employee_id, base_salary
FROM employees;
~~~

Open another session in the parent edition to confirm the old view still exposes `SALARY`, while the session in `LAB_V2` sees `BASE_SALARY`.

### 18.4. Cross-Edition Triggers

Create the forward trigger and reverse trigger following Section 7 examples; verify trigger source and status before enabling.

### 18.5. Backfill and Verify

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;

SELECT COUNT(*)
FROM employees
WHERE salary <> base_salary
   OR salary IS NULL AND base_salary IS NOT NULL
   OR salary IS NOT NULL AND base_salary IS NULL;
~~~

### 18.6. Test Coexistence

- Session A uses the old edition and updates via the old EV.
- Session B uses `LAB_V2` and updates via the new EV.
- Confirm triggers synchronize values in the proper direction.
- Commit/roll back each session independently.
- Observe edition contexts and base table data.

### 18.7. Clean Up Lab

Clean up only after zero sessions use the test edition. Drop triggers, views, tables, and editions in dependency order; never run `DROP EDITION CASCADE` without knowing which objects will be removed.

## 19. Practice Exercises

1. Explain why creating a child edition does not create a copy of tables.
2. Create two editions and verify the same package name can hold different implementations.
3. Create an editioning view in the parent edition and replace its version in the child edition.
4. Demonstrate that an existing session does not automatically switch editions when the default edition changes.
5. Add a new column to a base table without breaking the old view interface.
6. Write a forward trigger syncing an old column to a new column.
7. Write a reverse trigger and test DML from the new edition.
8. Backfill a large table by primary-key range while saving progress checkpoints.
9. Reconcile two columns and identify mismatched rows.
10. Design service/pool cutover and an old-session draining procedure.
11. Analyze a scenario where rollback is impossible because new data lacks a reverse mapping.
12. Compare EBR vs. `DBMS_REDEFINITION` for a real-world migration.

## 20. Post-Lab Cleanup and Safeguards

- Confirm sessions are using the right editions.
- Check object statuses and dependencies.
- Check trigger `ENABLED`/`DISABLED` states match expectations.
- Never drop base tables or shared columns while other editions still depend on them.
- Never drop editions with active child editions, sessions, or dependencies.
- Archive DDL, edition maps, and migration logs.
- Back up before cleaning up old structures.
- Maintain the rollback window per change plan.
- Revoke `USE` on lab editions when no longer needed.
- Never leave test cross-edition triggers active outside the lab window.

## Summary

Edition-Based Redefinition lets multiple versions of editioned objects coexist inside one database. Old and new sessions can run different packages/views while accessing shared base tables. Editioning views provide per-edition column interfaces; cross-edition triggers sync DML between old and new structures during coexistence.

An EBR rollout typically progresses through expand, bridge, backfill, switch, drain, and contract. Add new columns while keeping old ones, create a child edition, replace editioning views and PL/SQL in the child, sync data via forward/reverse triggers, and route new sessions/services to the new edition. Retire old columns and editions only when zero sessions or dependencies still need them.

EBR is an online upgrade deployment tool, not a physical table-versioning mechanism or backup/recovery replacement. Success depends on compatible design, resumable backfilling, data reconciliation, service routing, connection pool management, and a tested rollback plan.

## Oracle Reference Documentation

- [Oracle Database Development Guide — Edition-Based Redefinition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/editions.html) — editions, editioned objects, editioning views, and cross-edition triggers.
- [Oracle Database SQL Language Reference — CREATE EDITION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-EDITION.html) — creating editions and parent/child relationships.
- [Oracle Database SQL Language Reference — CREATE VIEW (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html) — view and editioning view syntax.
- [Oracle Database SQL Language Reference — CREATE TRIGGER (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html) — trigger syntax, crossedition clauses, and trigger behavior.
- [Oracle Database PL/SQL Packages and Types Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/) — `DBMS_SERVICE` and service management packages.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — user, service, session, and database administration.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_REDEFINITION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html) — online table redefinition.

When deploying on Oracle releases other than 19c, cross-check the EBR guide and SQL Language Reference for your exact version—specifically editionability, cross-edition trigger syntax, editioning view restrictions, service edition routing, object dependencies, and cleanup behavior.
