# Fine-Grained Auditing and Applicability Conditions

Fine-Grained Auditing (FGA) is Oracle Database's granular auditing mechanism that records data access when a statement satisfies configured conditions. Rather than logging every access to a table, FGA can focus on security-relevant columns, statement types, and rows.

For instance, security teams may need to know whenever someone reads the `SALARY` column for employees earning above a certain threshold, or when an account accesses customer records classified as sensitive. FGA lets you define policies attached to tables or views, specifying statement types, column lists, and applicability conditions.

FGA is an **audit logging and evidence-generation** mechanism. It does not block users from reading data, replace access privileges, mask data, or replace row-level access controls. To prevent access, use privileges, views, Virtual Private Database (VPD), Oracle Label Security, or another appropriate enforcement mechanism.

## 1. What Problem Does FGA Solve?

Traditional auditing typically records activity by statement type or object. That is useful for knowing which account accessed which table, but can produce excessive noise when only part of a table's data is genuinely sensitive.

FGA lets you define a policy across multiple dimensions:

- **Object:** table or view to monitor.
- **Statement type:** `SELECT`, `INSERT`, `UPDATE`, or `DELETE` per policy.
- **Audit columns:** columns a statement must reference for the policy to trigger.
- **Audit condition:** data condition that must be satisfied.
- **Handler:** optional PL/SQL procedure invoked when an audit event fires.
- **Enabled state:** whether the policy is active or disabled.

For example, `HR.EMPLOYEES` contains both ordinary fields like names and sensitive fields like `SALARY`. An organization may want to audit only queries referencing `SALARY` that access at least one row with `SALARY` of 15,000 or higher.

FGA expresses that policy directly inside the database where data is accessed. Auditing does not rely solely on every application logging properly on its own.

## 2. Distinguishing FGA from Other Security Mechanisms

Security mechanisms serve different purposes. Choosing the wrong one leads to false expectations about a policy's effect.

| Mechanism | Primary goal | Example |
|---|---|---|
| Object privilege | Allow or deny operations on an object | `GRANT SELECT ON HR.EMPLOYEES` |
| Fine-Grained Auditing | Record accesses meeting conditions | Audit when `SALARY` is accessed for sensitive employee groups |
| Unified Auditing | Manage and store audit events centrally via policies | Record logins, privilege usage, and object actions |
| VPD | Restrict which rows users can see | Employees only see records belonging to their department |
| Oracle Label Security | Control access by data labels and sensitivity levels | Only users with matching clearance labels read records |
| Data Redaction | Mask or transform returned values | Hide part of an identification number in query results |

FGA is not VPD. If a user is not permitted to read a row, VPD or access privileges must enforce that restriction. FGA can record that a query accessed data matching an audit condition, but will not strip rows from the result set.

FGA is also not synonymous with Unified Auditing. FGA is a granular data-auditing policy mechanism; Unified Auditing is Oracle's centralized audit trail and policy architecture. In environments with Unified Auditing enabled, FGA records integrate into the unified audit trail. Under traditional auditing setups, check the corresponding FGA audit trail views.

## 3. How an FGA Policy Triggers

An FGA policy attaches to a table or view. When a statement of a monitored type references that object, Oracle evaluates the policy conditions.

Triggering logic works roughly as follows:

1. A SQL statement accesses an object with an FGA policy.
2. The statement type is included in the policy's `statement_types`.
3. The statement references columns matching `audit_column` and `audit_column_opts`, if the policy restricts columns.
4. `audit_condition` is evaluated in the data access context.
5. When policy conditions are satisfied, Oracle creates an audit event per the database's audit trail mechanism.
6. If the policy defines a handler, the handler procedure is invoked per FGA rules.

Column conditions and data conditions serve different roles:

- `audit_column` answers: does the SQL statement reference an audited column?
- `audit_condition` answers: does the accessed data satisfy the condition requiring auditing?

If `audit_column` is `NULL`, the policy does not restrict by column list. If `audit_condition` is `NULL`, the policy does not restrict by row predicate and can audit all accesses matching the remaining criteria.

An FGA audit event serves as evidence of a statement matching the policy. Do not treat the audit trail as a table copying every row read. FGA is not a mechanism for dumping every accessed row to reconstruct query result sets.

## 4. Components of DBMS_FGA.ADD_POLICY

The `DBMS_FGA` package provides the API to create and manage policies. The most common procedure is `ADD_POLICY`.

Illustrative structure:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_HIGH_SALARY',
    audit_condition     => 'SALARY >= 15000',
    audit_column        => 'SALARY',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

Key parameters:

| Parameter | Meaning |
|---|---|
| `object_schema` | Schema owning the table or view |
| `object_name` | Name of the audited table or view |
| `policy_name` | Policy name, unique within the object scope per Oracle rules |
| `audit_condition` | Data condition; `NULL` means no restriction on this condition |
| `audit_column` | List of columns that must be referenced to trigger the policy; `NULL` means no column restriction |
| `statement_types` | Audited statement types |
| `audit_column_opts` | How columns in `audit_column` are combined |
| `handler_schema` | Schema containing the PL/SQL handler if any |
| `handler_module` | Handler procedure name if any |
| `enable` | Enable or disable the policy upon creation |
| `audit_trail` | Historical parameter related to audit trail type; usage depends on version and auditing mode |

Statement types commonly specified are `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Consult release-specific documentation before relying on handling of compound statements or newer syntax such as `MERGE`.

In modern Oracle releases, `audit_trail` in `DBMS_FGA.ADD_POLICY` is a historical parameter whose recording behavior depends on the auditing mode. Do not copy `audit_trail` values from old examples without first verifying whether the database runs traditional auditing or Unified Auditing.

## 5. Audit Condition: Data-Based Criteria

`audit_condition` is a SQL condition expression used to decide whether accessed data falls within audit scope.

Examples:

~~~sql
audit_condition => 'SALARY >= 15000'
~~~

The policy records accesses only when the salary condition is met. Another policy might monitor a specific department's data:

~~~sql
audit_condition => 'DEPARTMENT_ID = 90'
~~~

Or a sensitive status:

~~~sql
audit_condition => 'ACCOUNT_STATUS = ''SUSPENDED'''
~~~

Notice the nested single quotes inside the PL/SQL string: the SQL literal `SUSPENDED` is written with two single quotes on each side inside the `audit_condition` string.

### 5.1 NULL Conditions vs. Populated Conditions

If `audit_condition` is `NULL`, FGA does not filter by row values. The policy can still be scoped via `statement_types` and `audit_column`.

If `audit_condition` has an expression, the policy evaluates that condition during data access. When data matches the condition, an audit event is generated per FGA semantics.

Do not confuse `audit_condition` with the `WHERE` clause of the application's SQL statement. The application's `WHERE` clause determines the result set; the policy's `audit_condition` determines whether that access requires auditing.

For example, suppose the policy condition is `SALARY >= 15000`. An application can query by `department_id` without mentioning salary in its SQL. FGA still applies the policy condition when evaluating accessed data.

### 5.2 Conditions Must Fit the Object

Column names in `audit_condition` must belong to the audited object and be written in valid SQL syntax for the policy. Use explicit column names, compatible data types, and simple expressions.

Appropriate SQL expressions and contexts can distinguish sessions or applications, such as `SYS_CONTEXT` with `USERENV` or a controlled application context. This is useful when a policy needs to check a client identifier or session attribute.

Illustrative example:

~~~sql
audit_condition =>
  'DEPARTMENT_ID = 90 AND SYS_CONTEXT(''USERENV'', ''SESSION_USER'') <> ''SEC_AUDITOR'''
~~~

The expression illustrates referencing session context. Verify exact syntax and condition behavior on your target Oracle version, and ensure application-set contexts cannot be arbitrarily spoofed by users.

Avoid complex logic, mutable state dependencies, or functions with side effects inside `audit_condition`. Policies are evaluated during SQL execution; complex expressions increase overhead and make behavior hard to predict.

### 5.3 NULL, Three-Valued Logic, and Missing Data

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. When a condition involves a `NULL` column, comparison results may be `UNKNOWN` rather than `FALSE`.

Example:

~~~sql
SALARY >= 15000
~~~

If `SALARY` is `NULL`, the condition does not evaluate to `TRUE`. If auditing is also required for rows missing salary values, express it explicitly:

~~~sql
SALARY >= 15000 OR SALARY IS NULL
~~~

Conditions must reflect real policy requirements. Never assume `NULL` is automatically included or excluded from sensitive data.

## 6. Audit Columns and audit_column_opts

`audit_column` scopes the policy to columns referenced by the statement. This reduces irrelevant events when a table has many columns and only a few are sensitive.

Example:

~~~sql
audit_column => 'SALARY, COMMISSION_PCT'
~~~

If `audit_column_opts` is `DBMS_FGA.ANY_COLUMNS`, referencing at least one column in the list satisfies the column check.

If `audit_column_opts` is `DBMS_FGA.ALL_COLUMNS`, the statement must reference every column in the list per policy rules.

| Option | Combination rule |
|---|---|
| `DBMS_FGA.ANY_COLUMNS` | Any single column in the list being referenced suffices |
| `DBMS_FGA.ALL_COLUMNS` | Every column in the list must be referenced |

Example policy tracking salary and commission:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema     => 'HR',
    object_name       => 'EMPLOYEES',
    policy_name       => 'AUDIT_PAY_FIELDS',
    audit_condition   => 'SALARY >= 15000',
    audit_column      => 'SALARY, COMMISSION_PCT',
    statement_types   => 'SELECT',
    audit_column_opts => DBMS_FGA.ANY_COLUMNS
  );
END;
/
~~~

With `ANY_COLUMNS`, a query referencing `SALARY` or `COMMISSION_PCT` can satisfy the column condition. With `ALL_COLUMNS`, the policy requires the statement to reference both columns.

### 6.1 Columns in the SELECT List vs. Columns in Predicates

A column can be referenced in the `SELECT` list, `WHERE`, `JOIN`, `ORDER BY`, or other expressions. When checking whether a policy triggers, examine the entire SQL statement and how Oracle determines referenced columns.

Examples:

~~~sql
-- References SALARY in the SELECT list
SELECT employee_id, salary
FROM hr.employees
WHERE department_id = 90;
~~~

~~~sql
-- References SALARY in the predicate
SELECT employee_id
FROM hr.employees
WHERE salary >= 15000;
~~~

Both statements reference `SALARY`. For a policy tracking `SALARY`, do not inspect only the returned column list.

Conversely:

~~~sql
SELECT employee_id, first_name
FROM hr.employees
WHERE department_id = 90;
~~~

If `SALARY` is not referenced and the policy monitors only `SALARY`, this query may not satisfy the column check. That does not mean salary data is absent from the table; it simply was not accessed via the policy-designated column.

### 6.2 Choosing ANY vs. ALL

Choose `ANY_COLUMNS` when you need to detect access to any sensitive field in the group.

Choose `ALL_COLUMNS` when an event is meaningful only if the statement simultaneously uses every field in the group. This is a narrower case and must be tested with actual SQL.

Do not pick `ALL_COLUMNS` just to reduce event volume without realizing that a SQL query accessing each column separately will not be recorded.

## 7. Statement Types: Which Operations to Audit?

`statement_types` specifies which statement kinds the policy monitors.

Example auditing only `SELECT`:

~~~sql
statement_types => 'SELECT'
~~~

Auditing `SELECT` and `UPDATE`:

~~~sql
statement_types => 'SELECT,UPDATE'
~~~

Common types:

- **SELECT:** reading data.
- **INSERT:** inserting data.
- **UPDATE:** modifying data.
- **DELETE:** deleting data.

Distinguish FGA from DDL auditing. Creating tables, altering structures, granting privileges, or logging in are not the targets of standard FGA statement types. Those events belong in Unified Auditing or appropriate audit policies.

If the system uses `MERGE` or compound statements, verify exact behavior on your running Oracle version. Never assume a policy with `INSERT` and `UPDATE` automatically captures every `MERGE` branch without testing.

### 7.1 Policy Monitoring SELECT Only

A common requirement is recording reads of sensitive data. Example:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema   => 'HR',
    object_name     => 'EMPLOYEES',
    policy_name     => 'AUDIT_SENSITIVE_READ',
    audit_condition => 'DEPARTMENT_ID = 90',
    audit_column    => 'SALARY',
    statement_types => 'SELECT'
  );
END;
/
~~~

This policy focuses on reads of `SALARY` for rows in department 90.

### 7.2 Policy Monitoring Data Modifications

If the requirement is auditing salary changes, configure `UPDATE`:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema   => 'HR',
    object_name     => 'EMPLOYEES',
    policy_name     => 'AUDIT_SALARY_UPDATE',
    audit_condition => 'DEPARTMENT_ID = 90',
    audit_column    => 'SALARY',
    statement_types => 'UPDATE'
  );
END;
/
~~~

An FGA policy records access/modification events meeting conditions, but should not be treated as a mechanism storing full before-and-after values of every modified column. If row-by-row detailed change history is required, evaluate Flashback Data Archive, carefully designed audit triggers, application event logs, or an appropriate CDC solution.

## 8. Creating a Complete FGA Policy

Suppose the requirements are:

- Monitor `HR.EMPLOYEES`.
- Care only about `SELECT` queries.
- Record only when the statement references `SALARY`.
- Record only when rows match `SALARY >= 15000`.
- Do not log bind values unless specifically needed and separately controlled.

Create the policy:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_HIGH_SALARY_READ',
    audit_condition     => 'SALARY >= 15000',
    audit_column        => 'SALARY',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

After creating it, inspect the policy in the data dictionary:

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       policy_text,
       policy_column,
       policy_column_options,
       enabled,
       sel,
       ins,
       upd,
       del
FROM dba_audit_policies
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES';
~~~

Column names and visibility of dictionary views may vary by release and privileges. Without DBA privileges, use an appropriate view such as `ALL_AUDIT_POLICIES` if supported by your version or ask an audit administrator to verify.

### 8.1 Testing the Policy with Different Queries

Suppose data includes several employees in department 90 with varying salaries.

Query referencing `SALARY` that may read sensitive rows:

~~~sql
SELECT employee_id, salary
FROM hr.employees
WHERE department_id = 90;
~~~

Query referencing `SALARY` in the predicate:

~~~sql
SELECT employee_id
FROM hr.employees
WHERE salary >= 15000;
~~~

Query not referencing `SALARY`:

~~~sql
SELECT employee_id, first_name
FROM hr.employees
WHERE department_id = 90;
~~~

During testing, do not run just one SQL query. Test these scenarios:

- Statement references the audited column.
- Statement does not reference the audited column.
- Data contains rows matching the condition.
- Data contains no rows matching the condition.
- Condition evaluates to `UNKNOWN` due to `NULL`.
- Statement types beyond `SELECT` if configured.
- Queries accessing through views or application layers if used by the system.

FGA evaluates policies against accessed data and configured conditions. Verify actual audit events in the audit trail rather than merely seeing that the SQL statement succeeded.

## 9. Policy Lifecycle Management

Once created, policies can be enabled, disabled, or dropped via `DBMS_FGA`.

### 9.1 Temporarily Disabling a Policy

~~~sql
BEGIN
  DBMS_FGA.DISABLE_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ'
  );
END;
/
~~~

The policy still exists, but is not enforced while disabled.

### 9.2 Re-Enabling a Policy

~~~sql
BEGIN
  DBMS_FGA.ENABLE_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ',
    enable        => TRUE
  );
END;
/
~~~

### 9.3 Dropping a Policy

~~~sql
BEGIN
  DBMS_FGA.DROP_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ'
  );
END;
/
~~~

Dropping a policy stops future audit events from being generated under that policy. Dropping a policy does not delete previously generated audit records.

### 9.4 Changing Policy Definitions

When changes are required, you can drop and re-add the policy or use release-appropriate APIs to modify attributes. Save the current policy definition before changing it, and record the operator, timestamp, and reason.

Never edit policies directly by running `UPDATE` on system tables or internal audit tables. Always use Oracle-supported APIs.

## 10. Handler Modules: Reacting When Audit Events Fire

FGA supports specifying `handler_schema` and `handler_module`. A handler is an optional PL/SQL procedure invoked when a matching audit event occurs.

Example parameters:

~~~sql
handler_schema => 'SEC_ADMIN',
handler_module => 'FGA_EVENT_HANDLER'
~~~

The handler procedure can be defined in an administrative schema:

~~~sql
CREATE OR REPLACE PROCEDURE sec_admin.fga_event_handler AS
BEGIN
  -- Perform minimal auxiliary processing per a tested design.
  NULL;
END;
/
~~~

The procedure name in `handler_module` must match the actual procedure and have proper execution privileges. Name resolution, privileges, and error behavior must be verified on your specific release.

Handlers can trigger alerts or auxiliary logging. However:

- Oracle's audit trail remains the primary source of audit evidence.
- Handlers should not replace the audit trail with a custom log table.
- Avoid synchronous network calls or heavy processing inside handlers.
- Avoid triggering recursive queries back against the audited object itself.
- Design handlers so auxiliary errors do not corrupt the main business flow.
- Test overhead, execution privileges, exceptions, and transaction behavior.

If the goal is simply preserving access evidence, a handler is usually unnecessary. Add a handler only when there is a clear reaction requirement and impact on running SQL has been assessed.

## 11. Viewing Audit Records Generated by FGA

Where to read audit records depends on Oracle Database's auditing mode.

### 11.1 Traditional Audit Trail

In traditional auditing configurations, query `DBA_FGA_AUDIT_TRAIL`:

~~~sql
SELECT timestamp,
       db_user,
       os_user,
       userhost,
       client_id,
       object_schema,
       object_name,
       policy_name,
       statement_type,
       sql_text,
       sql_bind
FROM dba_fga_audit_trail
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES'
ORDER BY timestamp DESC;
~~~

`USER_FGA_AUDIT_TRAIL` can be used to view records within the current user's scope per privileges and version. `DBA_COMMON_AUDIT_TRAIL` can unify several traditional audit trail types.

### 11.2 Unified Auditing

When Unified Auditing is active, audit records are viewed in `UNIFIED_AUDIT_TRAIL`. Query common fields such as:

~~~sql
SELECT event_timestamp,
       dbusername,
       os_username,
       userhost,
       client_identifier,
       action_name,
       object_schema,
       object_name,
       sql_text,
       sql_binds,
       unified_audit_policies
FROM unified_audit_trail
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES'
ORDER BY event_timestamp DESC;
~~~

Available columns and how FGA policies link to unified audit records depend on release and configuration. Add filters on policy name or relevant audit fields in the view to narrow results.

If a query returns no records, do not immediately conclude FGA is broken. Determine whether the database runs traditional or unified auditing, whether the policy is enabled, whether the session accessed the right object, whether the statement referenced the audit column, and whether data matched `audit_condition`.

### 11.3 Inspecting User and Application Identifiers

An audit record can provide database user, OS user, host, client identifier, object, policy, statement type, SQL text, and bind data depending on mode/configuration.

These fields help answer:

- Who performed the operation?
- Which host or client did the connection originate from?
- Which object was accessed?
- Which policy triggered?
- What type of statement ran?
- Were SQL text/binds captured per configuration?

Audit records do not necessarily prove human identity if a database account is shared. To trace to end users, applications must reliably set client identifiers and module/action while protecting against context spoofing.

## 12. When to Apply FGA in Security Design

Not every table needs FGA. Apply it when there is a concrete data-auditing requirement expressible by object, statement, column, and condition.

Good fits:

- Regulated personal or financial data access.
- Salary columns, account numbers, identity fields, or sensitive profiles.
- Queries accessing data outside ordinary business scope.
- Monitoring access to rows belonging to special groups.
- Conditional `SELECT` auditing where standard object auditing is too noisy.
- Recording specific DML on sensitive columns or data.

Cases requiring other mechanisms:

- Preventing users from reading certain rows: use VPD or appropriate privileges/views.
- Masking returned values: use Data Redaction or a controlled presentation layer.
- Capturing complete old/new values per row: evaluate Flashback Data Archive, CDC, or proper audit triggers.
- Auditing logins, privilege grants, DDL, role usage, or administrative actions: use Unified Auditing.
- Monitoring every SQL statement in a workload: use performance monitoring tools or scoped tracing.

### 12.1 Clear Policy Requirements

Before creating an FGA policy, answer:

1. Which data or object is considered sensitive?
2. Which actions must be logged?
3. Who or which group must be monitored?
4. Which columns must be referenced?
5. Which row condition triggers auditing?
6. Must service/module/action or client identifiers be distinguished?
7. How long must the audit trail be retained?
8. Who is permitted to read, export, and purge audit records?
9. Are near-real-time alerts needed?
10. How will testing prove the policy misses nothing and avoids excessive noise?

Do not start by creating policies on every table and looking for reasons later. Translate security requirements into testable conditions.

### 12.2 Choosing Object Scope

FGA policies attach to specific objects. If data is accessed across multiple views, synonyms, packages, or schemas, verify the actual access path.

An application may access tables directly, through views, or via definer-rights PL/SQL packages. Test the exact path the application uses. Never assume a policy on one object automatically covers other objects holding similar data.

### 12.3 Conditions Must Be Stable and Explainable

A good policy makes it clear why an access was logged. Conditions should be short, clear, and tied to stable business rules.

If a condition relies on an application context, verify who can set that context and when it is reset. If users can spoof the context, the audit trail can misclassify activity.

If a condition relies on data values, test `NULL`, data types, collation, timezones, and edge cases.

## 13. Does FGA Audit Every Individual Row?

FGA is often misunderstood as writing one record per row read. Its primary goal is recording the accessing statement that satisfied the policy, based on configured data conditions and columns.

If a `SELECT` returns thousands of rows matching `audit_condition`, do not assume the audit trail contains one separate record per row with full row values. Audit events report statement/policy/object and related metadata, not a copy of the result set.

If legal requirements demand knowing precisely which rows were read or which exact values were returned, design additional mechanisms capable of proving that granularity. Assess performance, integrity, bypass resistance, and storage costs.

## 14. FGA and VPD Can Work Together

FGA and VPD can be applied together on the same object because they solve two different goals.

For example:

- VPD restricts department 10 employees to seeing only department 10 data.
- FGA logs when a specially privileged account accesses `SALARY` for employees in department 90.

VPD alters applied predicates to restrict which rows a user sees. FGA generates an audit event when access satisfies the policy. Design and test both mechanisms together to verify the FGA policy evaluates accessed data with the intended semantics in a VPD-protected environment.

Never use FGA in place of VPD. If users must not see rows, an enforcement mechanism is required.

## 15. Performance and Audit Trail Operations

FGA adds work to SQL execution. Cost depends on policy count, `audit_condition` complexity, audited column count, access frequency, audit trail write path, and handler execution if any.

Factors to measure:

- Number of policies attached to the object.
- Complexity of `audit_condition`.
- Number of rows accessed by statements.
- Statement execution frequency.
- Audit trail destination and I/O load.
- Whether handlers perform auxiliary work.
- Concurrency level and retention period.

Simple conditions are usually easier to control than complex expressions. Avoid adding duplicate policies with identical goals, which complicates event interpretation and adds overhead.

### 15.1 Capacity and Retention

Audit trails can grow rapidly if policies are overly broad or applications run high query volumes. Define:

- Retention per legal requirements and organizational policy.
- Expected storage growth and threshold alerts.
- Archive/export procedures.
- Access permissions for audit records.
- Purge workflows after retention expires.
- Retrieval capability during investigations.

Use `DBMS_AUDIT_MGMT` and Oracle-supported audit management workflows to manage data lifecycles. Never delete rows directly from internal `SYS` tables or modify audit trails with ordinary DML.

### 15.2 Protecting the Audit Trail

Because the audit trail is security evidence, enforce strict controls:

- Separate privileges for creating policies, reading audits, and database administration where appropriate.
- Restrict access to `DBA_FGA_AUDIT_TRAIL` or `UNIFIED_AUDIT_TRAIL`.
- Log policy modifications.
- Protect export files and backups.
- Limit `SQL_TEXT` and `SQL_BINDS` capture when they expose sensitive values.
- Monitor policy disabling or retention changes.
- Ensure clock synchronization across database, applications, and monitoring systems.

Business accounts should never hold permissions to alter or delete audit records that may log their own actions.

## 16. FGA Administrative Privileges

Creating and managing policies requires appropriate privileges. Depending on version and configuration, audit administration may rely on roles such as `AUDIT_ADMIN`, execute privilege on `DBMS_FGA`, and privileges on target objects.

Audit trail viewers may need roles such as `AUDIT_VIEWER` or read access on corresponding views per configuration. Never grant `DBA` just so a security team can read audit records.

A typical responsibility model includes:

- Data owners define sensitive columns and business conditions.
- Security/audit administrators manage policies.
- DBAs support configuration, capacity, ADR, and operations.
- Auditors hold scoped read access to the audit trail.
- Application teams provide module/action/client identifiers and test scenarios.

Role names, package privileges, and view access must be verified on your running Oracle version. Apply least privilege and test in non-production before deploying to production.

## 17. Troubleshooting Missing Audit Records

If SQL executes without producing an audit record, check in order:

### Does the Policy Exist and Is It Enabled?

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       enabled,
       policy_text,
       policy_column,
       sel,
       ins,
       upd,
       del
FROM dba_audit_policies
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES';
~~~

Confirm the right schema/object and that the policy is not disabled.

### Is the Statement Type Included in the Policy?

If the policy specifies only `SELECT`, an `UPDATE` will not trigger the policy for that statement type.

### Did the SQL Reference the Audited Column?

Inspect the entire SQL expression, including `SELECT` list, `WHERE`, `JOIN`, and `ORDER BY`. Review `ANY_COLUMNS` vs. `ALL_COLUMNS`.

### Did Any Rows Satisfy audit_condition?

If the condition is `SALARY >= 15000` and no accessed row matches, do not expect an event under that condition.

### Are You Querying the Right Audit Trail?

Determine whether Unified Auditing or traditional audit trail is active. Query the matching view and verify permissions. In unified mode, check `UNIFIED_AUDIT_TRAIL`; for traditional FGA trails, check `DBA_FGA_AUDIT_TRAIL`.

### Are You Querying the Wrong Database, PDB, or Instance?

In CDB/PDB and RAC, verify your connection targets the right container and instance. Do not look for audit events in a different PDB from where the statement ran.

### Did the Handler Fail?

If the policy uses a handler, check compile status, execute privileges, and handler errors. However, distinguish handler errors from whether the policy generated an audit event; verify records in the audit trail itself.

## 18. Multi-Condition Policy Example

Suppose an organization wants to audit when:

- A user accesses `HR.EMPLOYEES`.
- The statement references `SALARY` or `COMMISSION_PCT`.
- At least one row belongs to department 90.
- Only `SELECT` matters.

Policy:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_EXEC_PAY_READ',
    audit_condition     => 'DEPARTMENT_ID = 90',
    audit_column        => 'SALARY, COMMISSION_PCT',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

Illustrative scenario table:

| SQL/request | References audit column? | Matching data? | Expected result |
|---|---|---|---|
| `SELECT SALARY`, department 90 row | Yes | Yes | Audit event |
| `SELECT COMMISSION_PCT`, department 90 row | Yes | Yes | Audit event |
| `SELECT SALARY`, only department 10 | Yes | No | No event for condition |
| `SELECT FIRST_NAME`, department 90 | No | Yes | Fails column condition |
| `SELECT SALARY`, no matching rows | Yes | No | No event for condition |

This table illustrates conceptual policy logic. During live testing, verify how Oracle handles accessed row sets, views, predicate pushdown, bind values, and database version.

If `ANY_COLUMNS` is replaced with `ALL_COLUMNS`, queries referencing only one of the two columns will fail the column check; the policy requires both `SALARY` and `COMMISSION_PCT` to be referenced.

## 19. Limitations and Version-Specific Checks

FGA has evolved across multiple Oracle releases. Older examples may use the `audit_trail` parameter or assumptions about audit record storage that no longer fit current Unified Auditing setups.

Before deploying, verify:

- Oracle Database Release and Release Update.
- Whether the database uses Unified Auditing or traditional auditing.
- `DBMS_FGA.ADD_POLICY` syntax and supported statement types.
- How policies interact with views, synonyms, VPD, and PL/SQL access paths.
- Required privileges to create, enable/disable, and query policies.
- Actual audit trail view and available columns.
- Handler behavior and handler errors.
- Retention and purge management procedures.
- Performance impact on representative workloads.

Do not rely on SQL snippets from another version's documentation without testing. In particular, do not assume audit trails, bind capture, and compound statement behavior are identical across all configurations.

## 20. Production FGA Rollout Workflow

A controlled deployment workflow may include:

1. **Identify sensitive data:** clarify objects, columns, rows, and business activity requiring auditing.
2. **Author policy criteria:** define statement types, `audit_column`, and `audit_condition`.
3. **Identify audit trail source:** traditional or unified; read permissions and retention.
4. **Assess performance:** estimate access frequency, policy count, and condition complexity.
5. **Create policy in test:** use `DBMS_FGA.ADD_POLICY`.
6. **Positive testing:** in-scope statements must produce audit events.
7. **Negative testing:** out-of-scope statements must not produce unintended events.
8. **Test all access paths:** tables, views, application packages, connection pools, and session contexts.
9. **Verify audit trail:** confirm user, object, policy, statement, and timestamp.
10. **Deploy to production:** record operator, timestamp, policy definition, and rollback plan.
11. **Monitor:** track record counts, storage, overhead, and alerts.
12. **Periodic review:** remove unneeded policies, refine conditions, and audit permissions.

A policy should be considered successfully deployed only after proving both that in-scope accesses are logged and out-of-scope accesses do not generate unintended events.

## 21. Common Misconceptions

| Claim | Accurate understanding |
|---|---|
| FGA blocks users from reading sensitive rows | FGA logs events; VPD/privileges enforce access restrictions |
| FGA writes one record per row read | Audit events are not row-by-row result copies |
| `audit_condition` is like the application's `WHERE` | It is a policy condition independent of the SQL predicate |
| `audit_column` checks only the `SELECT` list | Check columns referenced anywhere in the statement expression |
| `NULL` `audit_condition` means no auditing | `NULL` means no data-condition restriction |
| `ALL_COLUMNS` easily replaces `ANY_COLUMNS` | `ALL` requires every column in the list to be referenced |
| FGA replaces Unified Auditing | FGA is granular data auditing; Unified Auditing is the broader audit trail/policy architecture |
| FGA stores complete before/after values on `UPDATE` | Do not treat FGA as a row-image logger; use appropriate solutions for value history |
| Creating the policy is enough | Verify enabled state, audit trail, retention, and workload |
| Seeing no records means the policy isn't running | Wrong object, statement type, column, condition, container, or audit trail view may be the cause |

## 22. Design and Operations Checklist

Before creating a policy:

- [ ] Exact object and schema identified.
- [ ] Statement types to audit identified.
- [ ] Sensitive columns and `ANY`/`ALL` combination defined.
- [ ] `audit_condition` clearly defined, including `NULL` handling.
- [ ] Trustworthy context/session attributes identified.
- [ ] Audit trail aligned with auditing mode.
- [ ] Retention, read permissions, and admin permissions defined.
- [ ] Evaluated whether a handler is genuinely necessary.

During testing:

- [ ] Policy created and enabled.
- [ ] In-scope queries generate audit events.
- [ ] Out-of-scope queries do not generate unintended events.
- [ ] Tested with both matching and non-matching data.
- [ ] Tested `ANY_COLUMNS` and `ALL_COLUMNS` with real SQL.
- [ ] Tested `SELECT` and configured DML statement types.
- [ ] Verified views, VPD, PL/SQL, and connection pools if applicable.
- [ ] Read the right audit trail and confirmed identifier fields.

Post-deployment:

- [ ] Monitor audit trail storage and growth rate.
- [ ] Monitor workload overhead.
- [ ] Restrict read and policy-modification privileges.
- [ ] Monitor handlers and auxiliary errors if used.
- [ ] Use supported APIs to manage retention/purging.
- [ ] Review policies periodically and document changes.

## 23. Conclusion

Fine-Grained Auditing allows Oracle to record data accesses satisfying specific conditions. `DBMS_FGA.ADD_POLICY` defines the object, statement types, audit columns, audit condition, and optional handler. `ANY_COLUMNS` and `ALL_COLUMNS` govern how listed columns are matched; `audit_condition` determines which accessed data warrants logging.

FGA fits when an organization needs selective access evidence for sensitive data. It does not block access, mask values, or replace row-level value history. Good design requires clear policies, both positive and negative testing, reading the right audit trail, and controlling privileges, retention, and overhead.
