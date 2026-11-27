# SQL Profiles, SQL Patches, SQL Tuning Advisor, and License Compliance Checks

## 1. Context: Addressing SQL with Suboptimal Execution Plans

When a SQL statement runs slowly, first identify the cause using the SQL text, bind values, execution plan, and runtime metrics. Causes may include missing or stale statistics, inaccurate cardinality estimates, suboptimal access paths, poor join order/join methods, poorly structured SQL, or plan changes following a deployment.

Oracle provides several mechanisms to influence how the optimizer processes a SQL statement without necessarily modifying application code:

- **SQL Tuning Advisor** analyzes SQL statements and provides tuning recommendations.
- **SQL Profile** supplies supplementary statistical metadata for a SQL statement so the optimizer produces better cardinality/selectivity estimates.
- **SQL Patch** attaches optimizer hints to a SQL statement to influence optimization.
- **SQL Plan Baseline** manages the set of accepted execution plans to prevent plan regressions.

These mechanisms serve distinct purposes. SQL Tuning Advisor is an analysis and recommendation tool; SQL Profiles and SQL Patches are objects used by the optimizer while optimizing a statement; SQL Plan Baselines focus on controlling which plans are permitted for execution. Do not treat them as interchangeable names for the same feature.

## 2. SQL Profile

### 2.1. What Is a SQL Profile?

A SQL Profile is a database object containing supplementary statistical information for a specific SQL statement. You can think of it as query-level statistics: the optimizer uses this metadata alongside object statistics, system statistics, bind values, and the current environment to estimate costs and choose an execution plan.

SQL Profiles are typically recommended by SQL Tuning Advisor when analysis reveals that optimizer estimates diverge significantly from figures obtained via sampling or partial execution of the statement. A Profile can include cardinality adjustments so the optimizer estimates row counts more accurately.

For example, the optimizer might estimate that a combined condition across two columns returns 100 rows, while actual data yields around 20,000 rows. With such an underestimate, the optimizer might pick nested loops and index access where a hash join or full scan would be more suitable. A SQL Profile can provide additional metadata to correct the estimate and let the optimizer reconsider the plan.

### 2.2. A SQL Profile Does Not Lock a Specific Execution Plan

A SQL Profile is not a directive forcing the optimizer to use one specific plan hash. It supplies auxiliary statistical metadata; the optimizer can still choose a different plan when data, indexes, statistics, bind values, or environment settings change.

This differs from a SQL Plan Baseline. A Profile mainly corrects input estimates for the optimizer; a baseline governs which plans are accepted. If the goal is improving cardinality estimates, consider a Profile. If the goal is curbing plan regressions and retaining a verified plan, evaluate SQL Plan Management.

### 2.3. When Should You Consider a SQL Profile?

A SQL Profile can be useful when:

- The SQL exhibits a large gap between estimated rows and actual rows.
- The optimizer misestimates predicate selectivity or post-join cardinality.
- Standard statistics have been reviewed yet still fail to describe the statement's data characteristics well.
- The SQL contains correlated predicates, complex expressions, or bind values that make estimation difficult.
- The Advisor verifies against representative data and proposes a Profile that improves test results.

A Profile does not replace fixing table/column statistics when base statistics are missing or stale. If the root cause is changed data without refreshed statistics, fix the base statistics first and re-evaluate.

### 2.4. Viewing Existing SQL Profiles

Commonly used views include `DBA_SQL_PROFILES` and `USER_SQL_PROFILES`:

```sql
SELECT name,
       category,
       status,
       force_matching,
       created,
       description
FROM dba_sql_profiles
ORDER BY created DESC;
```

`STATUS` shows whether the Profile is enabled or disabled; `FORCE_MATCHING` indicates whether SQL matching normalizes literals. Inspect both the SQL text/signature and the actual SQL statement targeted by the Profile rather than looking solely at the object name.

## 3. SQL Patch

### 3.1. What Is a SQL Patch?

A SQL Patch is a database object that attaches a set of optimizer hints to a SQL statement identified by SQL text or `SQL_ID`. When a matching SQL statement is parsed, Oracle can apply the patch's hints during optimization.

SQL Patches are helpful when a DBA needs to influence optimizer choices without modifying application SQL. For instance, after analyzing plans and testing, a DBA may want to apply a hint to change an access path or join method for one specific SQL statement.

SQL Patches are also used by SQL Repair Advisor to provide workarounds for severe SQL compilation or execution bugs. In that case, a patch can steer the optimizer to a different execution plan to avoid hitting the error. This purpose differs from SQL Tuning Advisor, which focuses on performance analysis and tuning recommendations.

### 3.2. How Does a SQL Patch Differ from a SQL Profile?

| Criterion | SQL Profile | SQL Patch |
|---|---|---|
| Primary contents | Auxiliary statistical metadata, estimate adjustments | Optimizer hints attached to a SQL statement |
| Goal | Improve cardinality/selectivity estimates | Directly influence optimization choices via hints |
| Locks a specific plan? | No | Not an absolute plan-stability mechanism; effectiveness depends on applied hints |
| Requires changing application SQL? | No | No |
| Common creation method | Recommended by SQL Tuning Advisor and accepted by DBA | Created with `DBMS_SQLDIAG.CREATE_SQL_PATCH` or accepted from SQL Repair Advisor |

If optimizer estimates are wrong, adding hints via a SQL Patch can mask the root cause and yield a poor plan as data evolves. Before creating a patch, identify what issue the hint addresses and test on a representative workload.

### 3.3. Creating a SQL Patch Manually

Oracle provides `DBMS_SQLDIAG.CREATE_SQL_PATCH`, which accepts SQL text or `SQL_ID` along with a hint string:

```sql
DECLARE
  l_patch_name VARCHAR2(128);
BEGIN
  l_patch_name := DBMS_SQLDIAG.CREATE_SQL_PATCH(
    sql_id      => 'SQL_ID_HERE',
    hint_text   => 'FULL(o)',
    name        => 'PATCH_ORDERS_FULL',
    description => 'Test full scan for the target SQL',
    category    => 'DEFAULT',
    validate    => TRUE
  );

  DBMS_OUTPUT.PUT_LINE(l_patch_name);
END;
/
```

This is an illustrative example: replace `SQL_ID_HERE` with the real `SQL_ID` and `o` with the table alias in the SQL statement. Hints must reference valid aliases and query blocks. If the SQL has multiple query blocks, verify query block names and hint syntax in the corresponding Oracle/MOS documentation. `VALIDATE => TRUE` asks Oracle to validate the supplied hints; successful object creation still requires checking the execution plan to confirm the hint actually took effect.

Another approach passes `sql_text` instead of `sql_id`:

```sql
DECLARE
  l_patch_name VARCHAR2(128);
BEGIN
  l_patch_name := DBMS_SQLDIAG.CREATE_SQL_PATCH(
    sql_text  => q'[
      SELECT o.order_id, o.amount
      FROM orders o
      WHERE o.customer_id = :customer_id
    ]',
    hint_text => 'INDEX(o IX_ORDERS_CUSTOMER)',
    name      => 'PATCH_ORDERS_CUSTOMER',
    validate  => TRUE
  );
END;
/
```

The index name in the example must exist and alias `o` must match the actual SQL. Never apply hints on guesswork alone; verify the plan and runtime metrics afterward.

### 3.4. Viewing, Disabling, Enabling, and Dropping a SQL Patch

The `DBA_SQL_PATCHES` view lists SQL Patches in the database:

```sql
SELECT name,
       category,
       status,
       force_matching,
       created,
       description
FROM dba_sql_patches
ORDER BY created DESC;
```

You can disable a patch to test its impact:

```sql
BEGIN
  DBMS_SQLDIAG.ALTER_SQL_PATCH(
    name            => 'PATCH_ORDERS_FULL',
    attribute_name  => 'STATUS',
    attribute_value => 'DISABLED'
  );
END;
/
```

Re-enable it with `attribute_value => 'ENABLED'`. When no longer needed, drop it:

```sql
BEGIN
  DBMS_SQLDIAG.DROP_SQL_PATCH(
    name => 'PATCH_ORDERS_FULL'
  );
END;
/
```

Modifying status or dropping a patch requires appropriate administrative privileges. Per package documentation, `ALTER_SQL_PATCH` requires the `ALTER ANY SQL PATCH` privilege; `DROP_SQL_PATCH` requires `DROP ANY SQL PATCH`. The `DBMS_SQLDIAG` package follows a security model requiring the `ADVISOR` role; exact privileges also depend on the subprogram and operation.

### 3.5. Exact Matching, Force Matching, and Category

A SQL Patch binds to the SQL text's identifier/signature. When calling `ACCEPT_SQL_PATCH` for a patch recommended by a SQL diagnosis task, the `FORCE_MATCH` parameter can normalize literals into bind variables so the patch applies to SQL statements sharing the same normalized structure. When `FALSE`, literals are not normalized this way.

For example, two SQL statements:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
```

may be matched differently depending on exact vs. force matching. Force matching widens scope and can therefore affect bind/literal values with differing selectivities. Do not enable force matching without checking the associated data groups and plans.

SQL Patches also have a `CATEGORY`. Sessions must use the matching category via the `SQLDIAGNOSE_CATEGORY` parameter for patches in that category to be considered. The default category is `DEFAULT`. Check session configuration and category when a patch exists yet the plan does not change.

Note: `CREATE_SQL_PATCH` and `ACCEPT_SQL_PATCH` have different parameter signatures. `FORCE_MATCH` is documented on the `ACCEPT_SQL_PATCH` API; do not add that parameter to `CREATE_SQL_PATCH` examples.

## 4. SQL Tuning Advisor

### 4.1. Role

SQL Tuning Advisor analyzes high-load SQL and recommends ways to improve performance. The Advisor uses the Automatic Tuning Optimizer to analyze a SQL statement and may recommend:

- Gathering or refreshing missing/stale statistics.
- Creating appropriate indexes.
- Rewriting the SQL statement.
- Creating a SQL Profile.
- Creating a SQL Plan Baseline or recommending an alternative plan in supported cases.

The Advisor returns findings, rationale, estimated performance benefit, and implementation commands/APIs. Recommendations should be reviewed by a DBA before implementation, especially when changes affect multiple applications or diverse bind value groups.

### 4.2. Input Sources

SQL Tuning Advisor can analyze SQL pulled from several sources, such as:

- Shared SQL area/cursor cache.
- Automatic Database Diagnostic Monitor (ADDM).
- Automatic Workload Repository (AWR).
- SQL Tuning Set (STS).

When picking an input source, understand both data conditions and licensing requirements for that source. AWR, ADDM, and many historical views belong to the Oracle Diagnostics Pack; reading that data carries separate licensing requirements. Do not use AWR merely because the Advisor accepts AWR as an input source.

### 4.3. Creating and Running a Tuning Task with DBMS_SQLTUNE

Example creating a task for a `SQL_ID` currently in the cursor cache:

```sql
DECLARE
  l_task_name VARCHAR2(128);
BEGIN
  l_task_name := DBMS_SQLTUNE.CREATE_TUNING_TASK(
    sql_id     => 'SQL_ID_HERE',
    scope      => 'COMPREHENSIVE',
    time_limit => 300,
    task_name  => 'TUNE_ORDERS_SQL'
  );

  DBMS_SQLTUNE.EXECUTE_TUNING_TASK(
    task_name => l_task_name
  );
END;
/
```

View the report:

```sql
SELECT DBMS_SQLTUNE.REPORT_TUNING_TASK(
         task_name => 'TUNE_ORDERS_SQL'
       ) AS report
FROM dual;
```

Tasks can take significant time depending on scope, time limit, SQL complexity, and data source. Run them on a test system or within a suitable maintenance window when production workloads are sensitive.

### 4.4. Accepting a SQL Profile Recommended by the Advisor

If the report includes a SQL Profile finding and testing shows a valid improvement, the DBA can accept the Profile:

```sql
BEGIN
  DBMS_SQLTUNE.ACCEPT_SQL_PROFILE(
    task_name => 'TUNE_ORDERS_SQL',
    name      => 'PROFILE_ORDERS_SQL',
    replace   => TRUE
  );
END;
/
```

Not every task recommends a SQL Profile. Call `ACCEPT_SQL_PROFILE` only when the task report contains that recommendation. For on-demand tasks, the DBA decides whether to accept. Automatic SQL Tuning can be configured to accept Profiles automatically via maintenance task parameters; verify system policy before enabling it.

To remove a Profile when needed:

```sql
BEGIN
  DBMS_SQLTUNE.DROP_SQL_PROFILE(
    name => 'PROFILE_ORDERS_SQL'
  );
END;
/
```

Dropping a Profile also requires assessing its impact on execution plans and workloads beforehand.

## 5. Distinguishing SQL Profiles, SQL Patches, and SQL Plan Baselines

All three objects can influence optimizer plan selection, yet they solve different problems:

| Mechanism | Information Stored | How It Acts | When to Consider |
|---|---|---|---|
| SQL Profile | Auxiliary statistics, cardinality adjustments | Improves optimizer estimates | Estimates are wrong despite reviewing normal statistics |
| SQL Patch | Optimizer hints | Attaches hints to the SQL statement | Need to apply a specific directive without editing application SQL |
| SQL Plan Baseline | Accepted plans and plan status flags | Restricts which plans the optimizer may choose | Need to curb plan regressions after environment changes |

For example, if the optimizer picks nested loops due to an underestimated row count, a SQL Profile can correct the estimate so the optimizer naturally picks a better plan. If you have identified a specific hint that resolves an issue and want to attach it to the SQL statement, consider a SQL Patch. If a plan is already verified and the operational requirement is preventing switches to unaccepted plans, a SQL Plan Baseline fits better.

Avoid stacking multiple mechanisms on the same SQL statement without knowing how they interact. When a Profile, Patch, and Baseline coexist, inspect the actual execution plan, SQL management views, and each object's status to see what the optimizer is using.

## 6. Oracle License Compliance Checks

### 6.1. Identify the Exact Edition and Deployment

Usage rights depend on edition, deployment model, and specific contracts. Oracle Database 19c Licensing Information distinguishes categories such as:

- **Standard Edition 2 (SE2):** the 19c feature matrix does not permit Oracle Tuning Pack.
- **Enterprise Edition (EE) and EE on Engineered Systems (EE-ES) on-premises:** Oracle Tuning Pack is a separately licensed management pack.
- **Certain Oracle Cloud services:** licensing documentation notes offerings such as Base Database Service EE/EE-HP/EE-EP and Exadata Database Service include Tuning Pack per the corresponding offering.

Never infer licensing rights simply because a package exists in the database or a user can call an API. Verify the exact offering, deployment tier, purchased/BYOL licenses, and applicable contract terms.

### 6.2. SQL Tuning Advisor and SQL Profiles Require Tuning Pack

Oracle Database 19c Licensing Information lists **SQL Tuning Advisor** and **SQL Profiles** among the features of the Oracle Tuning Pack. The documentation also states that Oracle Tuning Pack requires Oracle Diagnostics Pack.

For on-premises EE/EE-ES, Tuning Pack is an extra-cost option; in some cloud offerings, entitlement may be included. The documentation also states that all methods of accessing Tuning Pack functionality—including Enterprise Manager, command-line APIs, or querying underlying repository data—require a Tuning Pack license.

Consequently, clicking buttons in Enterprise Manager is not the only action counted as using Advisor/Profiles. Calling `DBMS_SQLTUNE`, enabling Automatic SQL Tuning, or deploying SQL Profiles must also be evaluated against licensing terms.

### 6.3. SQL Patch Must Be Verified Separately

SQL Patch is documented under `DBMS_SQLDIAG` with APIs such as `CREATE_SQL_PATCH`, `ACCEPT_SQL_PATCH`, `ALTER_SQL_PATCH`, and `DROP_SQL_PATCH`. In the Oracle Tuning Pack table of the 19c Licensing Information manual, Oracle lists SQL Tuning Advisor and SQL Profiles, while not listing SQL Patch as a separate line item.

Do not conclude from SQL Patch not appearing as a separate line that every way of creating, accepting, or using patches is license-free. Distinguish creating a patch manually via API from running SQL Repair Advisor or management tooling that may carry separate licensing conditions. In real deployments, confirm exact API paths and offerings against your Oracle contract or Oracle License Management Services.

### 6.4. Diagnostics Pack and Historical Data Sources

Oracle Diagnostics Pack includes features such as AWR, ADDM, and ASH. Many `DBA_HIST_*` historical views also fall under Diagnostics Pack, except those explicitly listed as exceptions in licensing documentation.

If SQL Tuning Advisor is run on SQL sourced from AWR/ADDM or operators query Diagnostics Pack data, Diagnostics Pack entitlement is required. Because Tuning Pack requires Diagnostics Pack, using Advisor/Profiles on on-premises EE generally requires both packs.

### 6.5. CONTROL_MANAGEMENT_PACK_ACCESS Is Not a License

The `CONTROL_MANAGEMENT_PACK_ACCESS` parameter technically enables or disables Diagnostics Pack and Tuning Pack features:

| Value | Meaning |
|---|---|
| `DIAGNOSTIC+TUNING` | Enables Diagnostics Pack and Tuning Pack features in the database |
| `DIAGNOSTIC` | Enables Diagnostics Pack features only |
| `NONE` | Disables both Diagnostics Pack and Tuning Pack |

Check the current setting:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'control_management_pack_access';
```

This parameter is solely a technical access control. Having `DIAGNOSTIC+TUNING` does not prove an organization purchased licenses; conversely, setting `NONE` does not alter contract terms by itself. DBAs should configure the parameter in alignment with actual entitlements and operational policy.

### 6.6. Feature Usage Statistics Are Not Proof of Entitlement

Oracle provides the `options_packs_usage_statistics.sql` script to review detected feature, option, and management pack usage. Licensing documentation explicitly notes that the script output is informational only and **does not represent entitlement or license requirements**.

Therefore, do not rely on a usage report or parameter value alone to conclude whether an organization has usage rights. When in doubt, review contracts, license orders, cloud offerings, and version-specific licensing documentation, and contact Oracle License Management Services or your Oracle representative for official confirmation.

## 7. Distinguishing SQL Patch from Oracle Software Patches

The term "SQL Patch" is easily confused with software patches applied via OPatch/datapatch.

| Term | Meaning |
|---|---|
| SQL Patch (`DBMS_SQLDIAG`) | Object containing hints attached to a SQL statement, influencing the optimizer |
| Oracle software patch | Patch for Oracle Home/database binaries and SQL scripts, installed via patching procedures |
| `DBA_SQL_PATCHES` | View listing optimizer SQL Patch objects |
| `DBA_REGISTRY_SQLPATCH` | View recording installations/rollbacks of SQL patch scripts applied by datapatch after OPatch |

For example, `DBA_SQL_PATCHES` inspects optimizer patches:

```sql
SELECT name, category, status, created
FROM dba_sql_patches
ORDER BY created DESC;
```

Meanwhile, `DBA_REGISTRY_SQLPATCH` records software patch installation history:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

The two views have similar names but serve completely different purposes. Do not query `DBA_REGISTRY_SQLPATCH` looking for an optimizer hint patch on a `SQL_ID`.

## 8. Safe Workflow in Production Environments

1. Collect the `SQL_ID`, SQL text, representative bind values, and relevant child cursors/plan hashes.
2. Use `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics to identify mismatches between estimated and actual rows, buffer-heavy operations, or time bottlenecks.
3. Check table/index statistics, extended statistics, histograms, indexes, SQL text, and optimizer environment before applying any SQL management object.
4. If automated analysis is needed and entitlement is verified, run SQL Tuning Advisor; review the report, rationale, and estimated benefit.
5. If the Advisor recommends a SQL Profile, validate on a representative workload and accept it if estimates improve without regressing other bind groups.
6. If a specific hint must be applied, evaluate a SQL Patch; confirm exact SQL signature, aliases/query blocks, category, and force matching scope.
7. If the goal is stabilizing a verified plan, consider a SQL Plan Baseline instead of misusing Profiles/Patches as plan-pinning tools.
8. Record creator, reason, `SQL_ID`/signature, object name, category, before/after plans, deployment date, and rollback steps.
9. Monitor post-deployment; disable or drop the Profile/Patch when no longer needed or if a plan regression appears.
10. Verify entitlements before using Advisor, Profiles, AWR/ADDM/ASH, or related APIs. Never treat database parameters or feature usage reports as licenses.

## 9. Pre-Deployment Checklist

| Question | What to Confirm |
|---|---|
| Have exact `SQL_ID` and SQL text been identified? | Avoid targeting the wrong SQL or multiple statements sharing a purpose |
| Are execution plans and runtime statistics captured? | Establish a measured baseline before changes |
| Is the problem estimates, hints, or plan regression? | Choose Profile, Patch, or Baseline for the right problem |
| Have multiple bind values been tested? | Avoid optimizing one value while slowing another group |
| Does the Patch target the right query block/table alias? | Hints must actually be recognized and applied |
| Are category and force matching appropriate? | Avoid overly broad matching or sessions missing the category |
| Is there a rollback procedure? | Know how to disable/drop the object and re-verify plans |
| Have edition, cloud offering, and licenses been verified? | Do not use features merely because an API is callable |
| Are AWR/ADDM/ASH or SQL Tuning Advisor used? | Verify Diagnostics Pack/Tuning Pack entitlements accordingly |

## Oracle Reference Documentation

- [Oracle Database 19c Licensing Information — Management Packs and permitted features](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html)
- [Oracle Database 19c SQL Tuning Guide — Analyzing SQL with SQL Tuning Advisor](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/sql-tuning-advisor.html)
- [Oracle Database 19c SQL Tuning Guide — Managing SQL Profiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-sql-profiles.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SQLDIAG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQLDIAG.html)
- [Oracle Database 19c Database Reference — DBA_SQL_PATCHES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SQL_PATCHES.html)
- [Oracle Database 19c Database Reference — DBA_REGISTRY_SQLPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REGISTRY_SQLPATCH.html)
