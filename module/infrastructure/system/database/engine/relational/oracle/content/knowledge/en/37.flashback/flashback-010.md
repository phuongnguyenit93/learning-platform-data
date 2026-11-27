# Flashback Data Archive and Feature Prerequisite Verification

Flashback Data Archive (FDA), formerly known as Oracle Total Recall, is a mechanism for storing table data change history for far longer than standard UNDO retention. When Flashback Archive is enabled on a table, Oracle stores modified row versions into database-managed historical storage. Users can query data as of a past point in time or inspect versions across a range using Flashback Query.

FDA is suited for applications needing to look up data history over months or years, for example:

- Viewing customer information prior to an update.
- Investigating changes to prices, credit limits, or contract statuses.
- Supporting audit requirements and business history lookups.
- Comparing current values with previous versions.
- Recovering certain logical data after erroneous DML operations.

FDA is not a complete audit log and does not replace backups. It primarily stores row-level DML history for archived tables; it does not automatically capture all DDL statements, end-user identities, business reasons, or off-database activities. If audit evidence is required, combine it with Unified Auditing, application auditing, CDC, or history tables as needed.

An important distinction is that FDA maintains its own storage and retention, whereas regular Flashback Query depends heavily on UNDO. FDA enables querying history older than the UNDO window, though only for changes tracked after the table was archive-enabled and within the archive's retention limit.

## 1. What is Flashback Data Archive?

Flashback Data Archive is an Oracle-managed historical storage area. When archiving is enabled on a table, Oracle tracks committed DML changes and writes historical row versions into internal history tables belonging to the Flashback Archive.

Conceptual diagram:

~~~text
Application
   |
   | INSERT / UPDATE / DELETE
   v
Business table with Flashback Archive enabled
   |
   | Oracle records row versions
   v
Flashback Data Archive
   |
   +--> Internal history table
   |
   +--> History storage tablespace
   |
   +--> Retention and purge policy
            |
            v
     Flashback Query
       AS OF / VERSIONS
~~~

Users query the table using SQL Flashback Query. Oracle combines current data, version metadata, and history data to return historical state.

### 1.1 How does FDA differ from UNDO?

UNDO serves read consistency, rollbacks, and certain Flashback features while undo remains retained. Undo segments are reused according to undo management rules.

FDA stores history in dedicated archive tablespaces according to configured retention. History does not depend solely on whether undo segments still survive.

| Criterion | UNDO | Flashback Data Archive |
|---|---|---|
| Primary purpose | Read consistency, rollback, recent version recovery | Long-term storage of row versions |
| Storage area | Undo tablespace | Flashback Archive tablespace |
| Retention duration | UNDO_RETENTION is a target, still subject to space/guarantee | Retention of each Flashback Archive |
| Requires per-table enablement | No | Yes |
| Querying | Flashback Query within undo window | AS OF/VERSIONS can query archive history |
| Best suited for | Short-term history, read consistency | Long-term data history |

### 1.2 FDA does not automatically archive all tables

Only tables explicitly assigned to a Flashback Archive are tracked. Creating a Flashback Archive does not mean every table in the database automatically stores history.

### 1.3 FDA is not retroactive

When archiving is enabled on a table at time T, FDA begins tracking changes from that point onward per Oracle's mechanism. It does not reconstruct years of history prior to enablement.

If history prior to deployment is needed, it must come from other sources such as auditing, CDC, backup/recovery, or existing history tables.

## 2. Core components

A typical FDA setup includes:

- **Flashback Archive:** Object managing retention and one or more history tablespaces.
- **Tablespace:** Storage container holding history data.
- **Quota:** Limit on how much space the archive may consume in a tablespace.
- **Retention:** Duration for which history must be kept.
- **Archived table:** Business table with Flashback Archive enabled.
- **History table:** Oracle-managed internal table storing row versions.
- **FBDA background process:** Background process handling historical data under Oracle architecture.

Never access or modify internal history tables directly. Use Flashback Query syntax and Oracle-supported dictionary views.

### 2.1 A Flashback Archive can span multiple tablespaces

An archive can be configured with a history tablespace and additional tablespaces can be added as needed. Oracle manages distribution of history data under the FDA mechanism.

### 2.2 Retention belongs to the archive

Retention is attached to the Flashback Archive, not the UNDO_RETENTION parameter. Retention can be modified under archive administration procedures.

### 2.3 Multiple archives in one database

A database can have multiple Flashback Archives with distinct retention/quota settings to classify data—for instance, a 1-year history archive and a 7-year history archive.

Not every table must share the same archive. Design according to data classification, business requirements, and storage capacity.

## 3. Creating a tablespace for history

Place history data in a dedicated tablespace to isolate capacity, I/O, backups, and operational permissions.

Example:

~~~sql
CREATE TABLESPACE fda_ts
DATAFILE '/u02/oradata/ORCL/fda_ts01.dbf'
SIZE 2G
AUTOEXTEND ON NEXT 256M MAXSIZE 20G;
~~~

The path and sizes are illustrative only. In production, you must:

- Select an appropriate storage tier.
- Forecast history data generation rate.
- Calculate retention in months/years.
- Verify autoextend and filesystem/ASM limits.
- Monitor I/O and backup windows.
- Configure alerts when the tablespace approaches full.

Do not reuse the same illustrative datafile or path across environments.

## 4. Creating a Flashback Data Archive

Example creating an archive retaining history for 5 years:

~~~sql
CREATE FLASHBACK ARCHIVE fda_5y
TABLESPACE fda_ts
QUOTA 20G
RETENTION 5 YEAR;
~~~

Where:

- FDA_5Y is the Flashback Archive name.
- TABLESPACE specifies the tablespace holding history data.
- QUOTA caps the space the archive may consume in that tablespace.
- RETENTION 5 YEAR defines how long history data is retained.

Syntax, retention units, and options can vary by Oracle release. Verify the SQL Language Reference for your exact version before deploying.

### 4.1 Setting a default archive

You can designate one archive as the default:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y SET DEFAULT;
~~~

When Flashback Archive is enabled on a table without specifying an archive name, Oracle can use the default archive if one exists and the operator holds appropriate privileges.

### 4.2 Inspecting created archives

Commonly used dictionary views:

- DBA_FLASHBACK_ARCHIVE.
- DBA_FLASHBACK_ARCHIVE_TS.
- DBA_FLASHBACK_ARCHIVE_TABLES.
- USER_FLASHBACK_ARCHIVE.
- USER_FLASHBACK_ARCHIVE_TABLES.

Example:

~~~sql
SELECT *
FROM dba_flashback_archive;
~~~

Archive tablespaces:

~~~sql
SELECT *
FROM dba_flashback_archive_ts;
~~~

Archive-enabled tables:

~~~sql
SELECT *
FROM dba_flashback_archive_tables;
~~~

Column names and access privileges can vary by release. Use DESC or query ALL_TAB_COLUMNS to verify metadata before writing shared monitoring scripts.

## 5. Enabling Flashback Archive on a table

Once the archive exists, enable it per table:

~~~sql
ALTER TABLE employees
FLASHBACK ARCHIVE fda_5y;
~~~

If a default archive is configured:

~~~sql
ALTER TABLE employees
FLASHBACK ARCHIVE;
~~~

From the moment it is enabled, Oracle begins tracking DML changes on the table under the FDA mechanism.

### 5.1 Enabling archive at table creation

In releases supporting this syntax, you can specify a Flashback Archive during CREATE TABLE:

~~~sql
CREATE TABLE employee_contracts (
    contract_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    contract_status VARCHAR2(30),
    effective_date DATE
)
FLASHBACK ARCHIVE fda_5y;
~~~

Verify exact release syntax before embedding it in schema creation scripts.

### 5.2 Checking enabled tables

~~~sql
SELECT *
FROM dba_flashback_archive_tables
WHERE owner_name = 'HR'
  AND table_name = 'EMPLOYEES';
~~~

Column names may vary by version; when unsure, use SELECT * or inspect dictionary metadata to confirm.

### 5.3 Disabling archive on a table

~~~sql
ALTER TABLE employees
NO FLASHBACK ARCHIVE;
~~~

Once disabled, new changes to the table are no longer archived under that configuration. Previously stored history may remain in the archive until retention expires or it is purged/dropped per procedure.

Disabling archiving does not immediately delete prior history.

## 6. Querying historical data with AS OF

Flashback Archive lets you query a table's state at a point in time:

~~~sql
SELECT employee_id,
       employee_name,
       salary
FROM employees
AS OF TIMESTAMP
    TIMESTAMP '2026-01-01 00:00:00'
WHERE employee_id = 100;
~~~

Or by SCN:

~~~sql
SELECT employee_id,
       employee_name,
       salary
FROM employees
AS OF SCN 123456789
WHERE employee_id = 100;
~~~

AS OF returns a snapshot at the requested point. When you need to view multiple versions across a range, use VERSIONS BETWEEN.

### 6.1 Points before archiving was enabled

If you query a timestamp prior to when FDA was enabled on the table, Oracle can only use UNDO if sufficient data remains. FDA holds no history for the period before tracking started.

### 6.2 Joining multiple tables

You can query multiple tables at the same point in time:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees AS OF TIMESTAMP
       TIMESTAMP '2026-01-01 00:00:00' e
JOIN departments AS OF TIMESTAMP
       TIMESTAMP '2026-01-01 00:00:00' d
  ON d.department_id = e.department_id;
~~~

Ensure all involved tables retain the required history for that timestamp. If only one table has FDA enabled, historical queryability for the join may be bounded by the other table and UNDO.

## 7. Querying multiple versions with VERSIONS BETWEEN

VERSIONS BETWEEN lets you view row versions across an SCN or timestamp interval:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2026-01-01 00:00:00'
AND TIMESTAMP '2026-06-30 23:59:59'
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Pseudocolumns:

| Pseudocolumn | Meaning |
|---|---|
| VERSIONS_STARTSCN | Starting SCN of the row version |
| VERSIONS_ENDSCN | Ending SCN of the row version |
| VERSIONS_STARTTIME | Starting timestamp |
| VERSIONS_ENDTIME | Ending timestamp |
| VERSIONS_XID | Transaction ID that created the version |
| VERSIONS_OPERATION | I, U, or D |

### 7.1 INSERT history

When a row is INSERTed and committed, a row version is created. VERSIONS_OPERATION can display I in matching results.

### 7.2 UPDATE history

Each committed UPDATE creates a new version and ends the prior version. VERSIONS BETWEEN can return multiple values for the same primary key.

### 7.3 DELETE history

DELETE can be represented by a version tied to operation D. This lets you investigate values before the row was deleted, while history remains within retention.

### 7.4 FDA and UNDO working together

FDA enables long-term history storage, though recent changes may still be read from UNDO before history data is processed or depending on access path. Do not assume every freshly committed version appears instantaneously in the internal archive history table.

## 8. How do FDA and Flashback Versions Query differ?

VERSIONS BETWEEN is query syntax. Flashback Data Archive is a long-term history storage mechanism. They complement each other.

| Criterion | UNDO-only Versions Query | Versions Query with FDA |
|---|---|---|
| Syntax | VERSIONS BETWEEN | VERSIONS BETWEEN |
| History source | UNDO | UNDO and FDA history data |
| Queryable span | Bounded by undo retention/remaining undo | Can be much longer via archive retention |
| Per-table enablement | Not required | Table must be archive-enabled |
| Pre-FDA history | Only if UNDO remains | FDA does not backfill old history |
| Multi-month/year retention | Not guaranteed | Follows archive retention |

### 8.1 FDA does not replace Flashback Database

Flashback Database uses flashback logs to rewind the entire database to a prior point in time. FDA stores row-level history for enabled tables.

| Mechanism | Scope |
|---|---|
| Flashback Query AS OF | Table snapshot at a single point |
| Flashback Versions Query | Row versions across an interval |
| Flashback Data Archive | Long-term row version history storage |
| Flashback Table | Reverts tables to a prior state under supported conditions |
| Flashback Database | Rewinds the database to a timestamp/SCN |

Do not use FDA as a substitute for database backups or Flashback Database.

## 9. Managing retention

Retention defines how long Oracle keeps history inside a Flashback Archive.

Example:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
MODIFY RETENTION 7 YEAR;
~~~

Changing retention requires evaluating:

- Legal/business requirements.
- Current history storage volume.
- DML velocity and change rate.
- Retention duration by data classification.
- Backup and storage costs.
- Time needed for investigations.

### 9.1 Retention is not UNDO_RETENTION

UNDO_RETENTION governs the target for retaining undo. FDA retention governs how long history is kept in the Flashback Archive.

Do not raise UNDO_RETENTION to substitute for a multi-year FDA policy. Conversely, do not use FDA retention to fix read consistency errors in long-running queries.

### 9.2 Retention expiration

Expired history data can be purged by Oracle under archive management mechanisms. Actual cleanup timing does not necessarily coincide to the exact second retention expires; treat retention as a retention policy rather than an exact physical file deletion SLA.

### 9.3 Retention and legal hold requirements

If an organization needs to retain history longer than standard policy due to an investigation or legal hold, establish an approved retention governance process. Never shorten retention or purge archives while data is under active investigation.

## 10. Purging history

Oracle supports purging history prior to a timestamp or purging the entire archive within syntax supported by your release.

Example purging data older than one year:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
PURGE BEFORE TIMESTAMP
    (SYSTIMESTAMP - INTERVAL '1' YEAR);
~~~

Example purging all history:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
PURGE ALL;
~~~

PURGE ALL is a high-impact operation that can erase history needed by queries. Execute it only with approval, retention/legal hold clearance, and a runbook.

### 10.1 Purge vs. DROP archive

- PURGE removes history data within the specified scope.
- DROP FLASHBACK ARCHIVE removes the archive object itself and can destroy associated history.

Do not use DROP merely to free a few GB of history when retention/purge can manage it.

### 10.2 Checks before purging

- Which archive is targeted?
- Which tables are attached to the archive?
- What time range is being deleted?
- Is there an active legal hold or audit request?
- Are suitable backups available if evidence must be preserved?
- Are applications actively running historical queries?

## 11. Adding and removing Flashback Archive tablespaces

As history data grows, you can add tablespaces:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
ADD TABLESPACE fda_ts2
QUOTA 50G;
~~~

Example removing a tablespace:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
REMOVE TABLESPACE fda_ts2;
~~~

Removing a tablespace must satisfy Oracle's conditions, including remaining stored data and how the archive manages history segments. Never drop a tablespace at the SQL layer before archive metadata is updated and confirmed safe.

### 11.1 Quota

Quota caps the space a Flashback Archive may occupy in a tablespace. If the quota is too small, the archive may fail to store history data as expected.

Monitor all of the following:

- Configured quota.
- Used tablespace space.
- Remaining physical storage.
- History growth rate.
- Retention.

### 11.2 Sizing estimation

Rough estimate:

~~~text
History capacity
  ≈ average changed row volume per day
    × retention days
    × storage overhead factor
    + safety margin
~~~

This is only a planning model. Row width, repeated updates to the same row, index/history metadata, compression, and DML distribution alter real-world consumption. Measure on a representative workload.

## 12. Administrative and usage privileges for FDA

FDA has dedicated system and object privileges. Separate the role that administers archives from the role that enables archiving on tables and the role that queries data.

### 12.1 FLASHBACK ARCHIVE ADMINISTER

The FLASHBACK ARCHIVE ADMINISTER system privilege permits managing Flashback Archives—creating, altering, or dropping archives per Oracle rules.

Example:

~~~sql
GRANT FLASHBACK ARCHIVE ADMINISTER TO fda_admin;
~~~

Do not grant this privilege to all application schemas. It governs retention and historical storage areas.

### 12.2 FLASHBACK ARCHIVE object privilege

You can grant usage of a specific archive to a user/schema:

~~~sql
GRANT FLASHBACK ARCHIVE ON fda_5y TO hr_owner;
~~~

Exact privileges required to enable archiving on a table depend on ownership and operation. The user running ALTER TABLE still needs ALTER privilege on the table. Verify against the SQL Language Reference for your release.

### 12.3 Privileges to query history

Users querying the table need SELECT and appropriate Flashback privileges per database policy. Example table-level grants:

~~~sql
GRANT SELECT ON hr.employees TO auditor;
GRANT FLASHBACK ON hr.employees TO auditor;
~~~

Do not grant FLASHBACK ANY TABLE to a user who only needs to inspect one table's history. Use narrowly scoped object privileges and roles.

### 12.4 Role separation

| Role | Responsibility |
|---|---|
| DBA/FDA admin | Create archives, quotas, retention, tablespaces, purges |
| Schema owner | Enable/disable archiving on schema-owned tables |
| Auditor/analyst | SELECT data and run authorized historical queries |
| Security/compliance | Approve retention, privileges, and legal holds |
| Storage admin | Ensure capacity, backups, and storage availability |

## 13. Checking dictionary views

Commonly used views:

| View | Purpose |
|---|---|
| DBA_FLASHBACK_ARCHIVE | Details of Flashback Archives |
| DBA_FLASHBACK_ARCHIVE_TS | Archive tablespaces and quotas |
| DBA_FLASHBACK_ARCHIVE_TABLES | Archive-enabled tables |
| USER_FLASHBACK_ARCHIVE | Archives visible to the user |
| USER_FLASHBACK_ARCHIVE_TABLES | Archived tables in the current schema |
| DBA_TABLES | Table metadata |
| DBA_TABLESPACES | Tablespace metadata |

Example listing archives:

~~~sql
SELECT *
FROM dba_flashback_archive
ORDER BY flashback_archive_name;
~~~

Checking tables:

~~~sql
SELECT *
FROM dba_flashback_archive_tables
ORDER BY owner_name, table_name;
~~~

Checking tablespaces:

~~~sql
SELECT *
FROM dba_flashback_archive_ts
ORDER BY flashback_archive_name, tablespace_name;
~~~

Do not hard-code column lists from one version into scripts meant for multiple releases. Inspect view structure using:

~~~sql
SELECT column_name,
       data_type
FROM all_tab_columns
WHERE owner = 'SYS'
  AND table_name = 'DBA_FLASHBACK_ARCHIVE'
ORDER BY column_id;
~~~

## 14. Monitoring history capacity

History data resides in the archive's tablespace. You can use DBA_SEGMENTS/DBA_DATA_FILES/DBA_FREE_SPACE for an overview:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS segment_mb
FROM dba_segments
GROUP BY tablespace_name
ORDER BY segment_mb DESC;
~~~

Checking datafiles:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
ORDER BY tablespace_name, file_name;
~~~

Internal history tables carry system-generated names. Never rely on name patterns to edit or drop segments. Manage everything through Flashback Archive, tablespaces, and dictionary metadata.

### 14.1 Capacity alerts

Alert on:

- History tablespace reaching 70%, 85%, 95%.
- Autoextend approaching MAXSIZE.
- Filesystem/ASM disk group nearing full.
- Archive quota nearly exhausted.
- Abnormally high history growth.
- FBDA background process errors.

Specific thresholds should reflect growth velocity and the lead time needed to provision storage.

## 15. Which tables can use Flashback Archive?

Not every table/object supports FDA in every release. Restrictions can involve:

- Special datatypes or column structures.
- Temporary tables.
- Nested tables or object-relational types.
- External tables.
- Tables using certain special structures.
- Certain partition maintenance operations.
- DDLs altering table structure.
- Tables already carrying incompatible attributes or features.

For example, datatypes/features such as LONG, certain collection types, BFILE, or specialized structures may face restrictions depending on release. Do not treat this list as exhaustive across all versions.

Before enabling FDA for a large schema:

1. Build a table inventory.
2. Check datatypes and attributes.
3. Check partitioning/LOBs/indexes.
4. Review DDL/deployment workflows.
5. Test enablement on a schema clone.
6. Run representative DML and historical queries.

### 15.1 DDL and Flashback Archive

FDA focuses on tracking DML history. Do not treat it as a schema versioning tool.

Some DDLs may be restricted while a table is archived; certain schema changes require disable/re-enable steps or release-supported procedures. Before running ALTER TABLE, MOVE, TRUNCATE, partition maintenance, or datatype changes, consult Oracle documentation and test in an equivalent environment.

### 15.2 TRUNCATE is not like DELETE

DELETE is row-by-row DML. TRUNCATE is a segment-level DDL. Do not assume FDA will record a DELETE version for every row when TRUNCATE runs.

If per-row deletion history is required, use DELETE per procedure or design audit/CDC; do not substitute TRUNCATE.

### 15.3 Dropping tables

DROP TABLE is DDL and may follow specific rules with Flashback Archive. Never use this operation as a shortcut to erase history. Check release documentation and archive state before dropping objects.

## 16. FDA does not automatically record end users or business reasons

Flashback Archive can surface row versions, SCNs, timestamps, and transaction metadata via Flashback Query. However, those fields are not complete audit context.

Example Versions Query:

~~~sql
SELECT employee_id,
       salary,
       versions_starttime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '30' DAY
AND SYSTIMESTAMP
WHERE employee_id = :employee_id;
~~~

To know which request modified data, applications should set:

- MODULE.
- ACTION.
- CLIENT_IDENTIFIER.
- Correlation/request ID in application logs.
- Audit policies for sensitive actions.

Never place tokens, passwords, or unnecessary personal data inside module/action/client identifier fields.

## 17. FDA and Flashback Transaction Query

VERSIONS_XID can be used to locate the corresponding transaction ID. Under supported conditions, FLASHBACK_TRANSACTION_QUERY can provide transaction metadata and UNDO_SQL.

Example:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :xid;
~~~

Information may be incomplete if transaction metadata or undo has expired. Some details depend on supplemental logging and access privileges.

UNDO_SQL is investigative support data, not a guaranteed-safe rollback script. Check side effects, triggers, foreign keys, transaction ordering, and current state before using any SQL statement for recovery.

## 18. FDA vs. auditing/CDC

FDA answers the question "what versions did a row go through?". Auditing/CDC can also answer "who performed it, from which application, under which request, and why?" if the system is designed to capture them.

| Requirement | FDA | Audit/CDC/history table |
|---|---|---|
| Store row versions over time | Yes | Possible |
| Query with AS OF/VERSIONS | Yes | Must implement or process manually |
| Multi-month/year retention | Yes, per archive policy | Per solution retention |
| End actor/user | Not automatically guaranteed | Can record |
| Business reason/request ID | Not automatically guaranteed | Can record |
| DDL auditing | Not primary purpose | Audit/deployment logs are better suited |
| Stream events to external systems | Not a CDC stream | CDC is built for that |
| Tamper-resistant history | Not an immutable audit store | Can be designed immutable/off-host |

If compliance auditing is required, FDA can serve as a supplementary source, though it should not be the sole source when proving actor and intent is necessary.

## 19. FDA and Flashback Table

Flashback Table can return one or more tables to their state at a timestamp/SCN if conditions are met. FDA can supply long-term history supporting certain Flashback Query cases, yet that does not mean every Flashback Table operation works indefinitely.

General syntax example:

~~~sql
FLASHBACK TABLE employees
TO TIMESTAMP
    (TIMESTAMP '2026-01-01 00:00:00');
~~~

Flashback Table has requirements such as row movement and performs write operations. Check prerequisites, foreign keys, triggers, replication, and applications before running.

Never run Flashback Table in production just to "preview". Use SELECT AS OF/VERSIONS first to confirm the data needing recovery.

## 20. FDA and backup/recovery

A Flashback Archive is database data and must be protected in the backup strategy. Tablespaces storing history data must be backed up like any other critical tablespace.

An FDA protection plan requires:

- Backing up archive tablespace datafiles.
- Backing up control file/SPFILE.
- Backing up archived redo logs if in ARCHIVELOG mode.
- Protecting archive metadata.
- Checking retention post-restore.
- Rehearsing historical queries after a restore.

### 20.1 Do not confuse FDA retention with backup retention

FDA retention governs logical history kept in the archive. RMAN retention policy governs which physical backups to retain.

The two policies are independent:

| Policy | Governs |
|---|---|
| Flashback Archive retention | Row history inside FDA |
| RMAN retention policy | Datafile/controlfile/archivelog backups |
| UNDO_RETENTION | Undo retention target |
| Audit retention | Audit records |

If old RMAN backups are deleted, current FDA history can still remain. Conversely, if FDA is purged, old RMAN backups may still contain historical data as of those backup points.

### 20.2 Restoring an archive tablespace

If a tablespace containing a Flashback Archive is lost, it must be recovered via RMAN procedures while ensuring archive metadata and segments are restored consistently. Do not recreate an archive with the same name and expect Oracle to automatically reconnect old history if the datafiles/history segments were lost.

### 20.3 Cloning/PDB moves

When cloning databases/PDBs, understand how archive metadata, tablespaces, history data, and retention will transfer. Test on a clone before applying to production environments.

## 21. Checking feature status and licensing prerequisites

This topic calls for checking feature prerequisites because Flashback Data Archive has a history of name changes, release-specific support, and licensing terms. Separate three questions:

1. Does the database release/edition support the feature?
2. Is the feature configured and actively used in this environment?
3. Does the organization hold the license/entitlement to use that feature?

These three questions are not equivalent.

### 21.1 Identifying database version

~~~sql
SELECT banner
FROM v$version;
~~~

Or:

~~~sql
SELECT version,
       version_full
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

The VERSION_FULL column may not exist in older releases. Check dictionary metadata if writing cross-version scripts.

### 21.2 Identifying edition

~~~sql
SELECT banner
FROM v$version
WHERE banner LIKE '%Edition%';
~~~

In environments with appropriate privileges, you can inspect:

~~~sql
SELECT parameter,
       value
FROM v$option
WHERE parameter LIKE '%Flashback%';
~~~

V$OPTION and V$VERSION provide technical environment details. They do not prove the organization purchased or is contractually entitled to use an option/feature.

### 21.3 Checking feature usage metadata

Oracle provides a view tracking feature usage:

~~~sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date,
       last_sample_date
FROM dba_feature_usage_statistics
WHERE LOWER(name) LIKE '%flashback%'
ORDER BY name;
~~~

This view helps DBAs/license owners recognize feature usage recorded by the database. Data can depend on sampling intervals, release, and tracking mechanisms. Never treat its output as a final licensing report.

### 21.4 Feature usage does not equal entitlement

The following do not prove licensing:

- Being able to create a Flashback Archive.
- Being able to run ALTER TABLE ... FLASHBACK ARCHIVE.
- V$OPTION showing TRUE.
- DBA_FEATURE_USAGE_STATISTICS recording usage.
- Having binaries installed that support the feature.

Technical capability and commercial right to use are separate matters. Always cross-check the Oracle Licensing Information manual for your exact release, edition, platform, cloud service, and organizational order documents.

### 21.5 Total Recall vs. Flashback Data Archive naming

Older documentation may refer to the feature as Oracle Total Recall; newer documentation typically uses Flashback Data Archive. When researching licensing, search both the historical name and the current name, and verify for your exact release.

Do not generalize a licensing conclusion from an old blog post to all versions. Terms can vary by release, edition, licensing program, and cloud service.

### 21.6 Verifying entitlement with the license owner

Before enabling FDA in production, send the following details to your license owner/Oracle account team:

- Database version and Release Update.
- Edition.
- Deployment model: on-premises, engineered system, or cloud service.
- Feature to be used: Flashback Data Archive.
- Whether databases/PDBs/standbys/dev/test will also use it.
- Contract/order documents and applicable metrics.
- Applicable Oracle Licensing Information documentation.

Proceed with deployment only once entitlement is confirmed per organizational process.

## 22. Difference between version and edition

Version answers which release the database runs. Edition answers which product/edition is installed. License entitlement answers whether the organization holds contractual rights to use the feature.

| Information | Example verification source | Sufficient to confirm licensing? |
|---|---|---|
| Version | V$VERSION, PRODUCT_COMPONENT_VERSION | No |
| Edition | Banner/version metadata | No |
| Option visibility | V$OPTION | No |
| Feature usage | DBA_FEATURE_USAGE_STATISTICS | No |
| Contract entitlement | Order documents, licensing records | Authoritative source to verify |
| Product feature matrix | Licensing Information/User Guide for exact release | Must be paired with contract |

Never conclude "it's licensed" just because a SQL command executes successfully. Conversely, if a feature is technically unavailable, determine whether it is a release, edition, configuration, or privilege restriction.

## 23. Configuring FDA in CDB/PDB

In multitenant environments, determine in which container the Flashback Archive is managed and to which PDB the tables belong.

Before creating an archive:

- Connect to the right CDB root or PDB.
- Verify the tablespace resides in the appropriate container.
- Identify the user administering the archive.
- Identify which schema/PDB owns the archived tables.
- Check privileges and history management behavior in that container.

Example checking the container:

~~~sql
SHOW CON_NAME;
~~~

Or:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Do not assume an archive created in root works identically across all PDBs or all releases. Verify multitenant documentation for your version.

## 24. FDA in RAC and Data Guard

### 24.1 RAC

In RAC, instances share access to database storage. History tablespaces and associated files must reside on cluster-supported shared storage. Monitor capacity and background processes at the appropriate database/instance level.

Never place history datafiles on one node's local filesystem if other instances cannot access them.

### 24.2 Data Guard

Flashback Archive data is stored in tablespaces and changes are written to redo under standard database mechanics. The standby receives/applies redo to keep archive data synchronized with the database.

Verify:

- Does the archive tablespace exist on the standby?
- Is redo apply keeping up?
- After a switchover, do archive queries work?
- Are retention/purge settings consistent?
- Are primary/standby backups adequate?

Do not test queries only on primary and assume DR is ready. Rehearse switchover/failover and run historical queries on the target database.

## 25. Performance and storage impact

FDA increases storage consumption because historical versions are preserved. Cost depends on:

- Number of archive-enabled rows.
- Frequency of UPDATE/DELETE.
- Row width.
- Number of times a row changes within retention.
- Retention duration.
- Datatypes.
- Compression/storage characteristics.
- Purge schedule.

An OLTP table updating the same row multiple times per minute can generate far more history than an insert-once table.

### 25.1 Measure before scaling out

Run tests:

1. Capture baseline tablespace usage.
2. Enable FDA on a representative subset of tables.
3. Run real workload or simulated data.
4. Measure daily history growth.
5. Extrapolate across retention.
6. Verify backup duration and restores.

Do not multiply current row counts by retention years and treat that as an accurate forecast.

### 25.2 DML impact

FDA can introduce extra background work and I/O to store history. Measure latency, throughput, CPU, and storage I/O before and after enabling on a representative workload.

### 25.3 FBDA background process

Oracle uses a background process dedicated to Flashback Data Archive to process history. If history is not stored as expected, check the alert log, background processes, and archive tablespace instead of modifying internal history tables directly.

## 26. Schema changes and migrations

Before deploying DDL on an FDA-enabled table:

- Verify whether the DDL type is supported.
- Check whether archiving must be temporarily disabled.
- Determine whether existing history will be preserved.
- Inspect indexes, partitions, LOBs, and constraints.
- Check application compatibility.
- Test on a clone.

Do not treat NO FLASHBACK ARCHIVE followed by ALTER TABLE as a safe default pattern. Disabling archiving can lose tracking of changes during the pause window.

When schema changes are necessary:

1. Plan downtime or online DDL.
2. Identify any history gap window.
3. Back up and test.
4. Perform release-supported operations.
5. Re-enable archiving if needed.
6. Verify dictionary views and historical queries.

## 27. Workflow for investigating long-term data changes

Suppose you need to trace contract status change history over 3 years:

1. Confirm the CONTRACTS table had FDA enabled prior to the period being investigated.
2. Verify the archive and retention cover 3 years.
3. Confirm the history tablespace still holds the data.
4. Query with AS OF or VERSIONS BETWEEN by SCN/TIMESTAMP.
5. Filter by contract_id.
6. Inspect STARTSCN/ENDSCN/XID/OPERATION.
7. Correlate XID with audit/application context if needed.
8. Save results according to data protection policy.

Example:

~~~sql
SELECT contract_id,
       contract_status,
       effective_date,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM contracts
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2023-01-01 00:00:00'
AND TIMESTAMP '2026-01-01 00:00:00'
WHERE contract_id = :contract_id
ORDER BY versions_starttime;
~~~

If FDA was only enabled on the table starting in 2025, the query cannot synthesize 2023–2024 history. Another data source is needed for that earlier period.

## 28. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| No history visible prior to FDA enablement | FDA does not backfill | Check old audits/backups/CDC |
| AS OF returns snapshot error | Timestamp too old for UNDO/FDA or object restriction | Check archive enablement, retention, and object |
| Archive tablespace full | Inadequate quota/retention/growth sizing | Expand storage, add tablespaces, review retention |
| Cannot enable archive on table | Missing privileges or unsupported table feature | Check privileges and release restrictions |
| DDL rejected | Table is FDA-enabled and operation is unsupported | Check DDL docs and migration runbook |
| History query missing rows | Retention/purge/enablement window | Inspect archive metadata and enablement time |
| FDA admin cannot create archive | Missing privilege/tablespace quota | Check FLASHBACK ARCHIVE ADMINISTER |
| History query fails to run | Missing SELECT/FLASHBACK privilege | Grant minimal object privileges |
| FBDA process error | Storage, metadata, or background issue | Check alert log and involve DBA |
| Feature runs technically but license unclear | Technical capability confused with entitlement | Verify licensing information and contract |
| Dropping archive loses history | Destructive operation | Backups, approvals, and purge policies |
| Treating FDA as an audit log | Missing actor/reason/request context | Combine with auditing/CDC/application logs |

## 29. Common mistakes

| Mistake | Consequence | Right approach |
|---|---|---|
| Thinking creating an archive tracks all tables automatically | No history for un-enabled tables | Run ALTER TABLE ... FLASHBACK ARCHIVE |
| Thinking FDA backfills old history | Cannot query pre-enablement period | Record enablement date and rely on other history sources |
| Confusing FDA retention with UNDO_RETENTION | Misconfigured retention design | Manage the two policies independently |
| Thinking FDA is a complete audit trail | Missing actor, reason, and DDL | Combine Unified Auditing/CDC/application logs |
| Editing SYS_FBA_* directly | Can corrupt metadata/history | Use supported SQL/dictionary interfaces only |
| Running Purge ALL to free disk immediately | Permanent loss of long-term history | Review retention/legal hold first |
| Dropping tablespace before removing from archive | Data loss or inconsistent metadata | Manage via ALTER FLASHBACK ARCHIVE |
| Enabling FDA on every table | Unnecessary storage/I/O overhead | Select tables by data classification |
| Failing to estimate history growth | Tablespace/quota exhaustion | Benchmark and configure alerts |
| Thinking DDL is stored like DML | Incomplete schema history | Use DDL auditing/deployment logs |
| Using feature usage views to confirm licensing | Wrong licensing conclusions | Cross-check contracts/licensing guides |
| Using V$OPTION as proof of entitlement | Technical capability confused with commercial rights | Confirm with license owner |
| Testing only on primary | DR/PDB unprepared | Perform restore/switchover drills |
| Failing to back up history tablespaces | Cannot query history after recovery | Include FDA tablespaces in backups |

## 30. Flashback Data Archive deployment checklist

**Requirements**

- Which tables require history retention?
- How long must history be kept?
- Is row history or audit evidence required?
- Are actor/request/reason fields needed?
- Is there pre-deployment historical data?

**Feature prerequisites**

- Database version/Release Update confirmed?
- Edition/platform confirmed?
- Is Flashback Data Archive supported in that configuration?
- Is license entitlement confirmed by the license owner?
- Are there special terms for cloud/DR/test/standby?

**Storage and retention**

- Dedicated tablespace created?
- Quota and autoextend appropriate?
- History growth benchmarked?
- Retention approved by business/compliance?
- Purge/legal hold policies defined?
- Capacity alerts configured?

**Privileges**

- Does the FDA admin hold FLASHBACK ARCHIVE ADMINISTER?
- Does the schema owner hold necessary rights to enable tables?
- Do auditors hold only appropriate SELECT/FLASHBACK object privileges?
- Avoided overly broad system privileges?

**Operations**

- Tables enabled against the right archive?
- AS OF/VERSIONS queries verified?
- DDL migration runbook ready?
- Backups include history tablespaces?
- Restore tests verify historical queries?
- RAC/Data Guard/PDB tested?

## 31. Self-check hands-on exercises

Execute in a lab schema and database with verified entitlement to use the feature.

### Exercise 1 — Create a tablespace

Create a dedicated tablespace for history; verify datafile, autoextend, and sizing.

### Exercise 2 — Create a Flashback Archive

Create an archive with 1-year retention and suitable quota. Query DBA_FLASHBACK_ARCHIVE to verify.

### Exercise 3 — Enable archive on a table

Create a demo table and run ALTER TABLE ... FLASHBACK ARCHIVE. Verify in DBA_FLASHBACK_ARCHIVE_TABLES.

### Exercise 4 — INSERT/UPDATE/DELETE

Run multiple DML statements and commit. Query VERSIONS BETWEEN to inspect row versions.

### Exercise 5 — AS OF

Query the table at a timestamp between two UPDATEs. Compare against current data.

### Exercise 6 — Compare UNDO and FDA

In a lab with suitable retention, query a milestone older than the UNDO window yet still within FDA. Note the differences.

### Exercise 7 — Modify retention

Change archive retention in the lab. Observe metadata and how expired history is managed.

### Exercise 8 — Purge

Generate test history data, purge an older interval, and verify historical queries. Never run PURGE ALL on important data.

### Exercise 9 — Tablespace capacity

Monitor DBA_SEGMENTS and DBA_DATA_FILES before/after an update workload. Estimate daily growth.

### Exercise 10 — Privileges

Create separate FDA admin and schema owner accounts. Test minimal privilege grants, archive enablement, and historical queries.

### Exercise 11 — Feature usage

Query DBA_FEATURE_USAGE_STATISTICS for Flashback names. Explain why this is not proof of licensing.

### Exercise 12 — Backup/restore

Back up the database containing the FDA tablespace, restore in the lab, and confirm historical queries work post-recovery.

## 32. Remember

| Concept | Key point to remember |
|---|---|
| Flashback Data Archive | Stores long-term row history per retention |
| Total Recall | Historical name for the feature |
| FDA tablespace | Storage area holding history data |
| History table | Oracle-managed internal table; never modify directly |
| FBDA | Background process handling history |
| CREATE FLASHBACK ARCHIVE | Creates an archive with tablespace/quota/retention |
| ALTER TABLE ... FLASHBACK ARCHIVE | Enables history tracking for a table |
| NO FLASHBACK ARCHIVE | Disables tracking for a table |
| AS OF | Views state at a single point |
| VERSIONS BETWEEN | Views multiple row versions across a range |
| FDA retention | Duration history is kept in the archive |
| UNDO_RETENTION | Undo retention target, independent of FDA retention |
| PURGE | Deletes history within a specified scope |
| FLASHBACK ARCHIVE ADMINISTER | Archive administration privilege |
| FLASHBACK ARCHIVE object privilege | Privilege to use an archive |
| DBA_FLASHBACK_ARCHIVE | Archive metadata |
| DBA_FLASHBACK_ARCHIVE_TS | Archive tablespaces/quotas |
| DBA_FLASHBACK_ARCHIVE_TABLES | Archive-enabled tables |
| DBA_FEATURE_USAGE_STATISTICS | Feature usage stats; does not prove licensing |
| License entitlement | Right to use under contract and licensing guides |

Flashback Data Archive enables storing row version history far beyond UNDO for tracked tables. Create archives in dedicated tablespaces, set retention/quotas per business requirements, assign role-based privileges, and query using AS OF/VERSIONS. FDA does not backfill history before enablement, is not a complete audit trail, and does not replace RMAN backups. When verifying feature prerequisites, separate version/edition, technical capability, and contractual entitlement; DBA_FEATURE_USAGE_STATISTICS and V$OPTION provide technical details, not license confirmation. Before production rollout, test DML, DDL, purging, backup/restore, and historical queries in an equivalent environment.
