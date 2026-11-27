# SQL SECURITY DEFINER/INVOKER and Access Privileges Through Views

A view is a query object stored in a schema. Beyond simplifying SQL, a view can also provide a data access interface with a selected scope of columns or rows. In MySQL, the SQL SECURITY clause determines which account's privileges are used when a statement accessing the view executes: the account that defined the view (DEFINER) or the account calling the view (INVOKER).

With SQL SECURITY DEFINER, users can be granted SELECT on the view without needing direct privileges on the underlying tables. MySQL checks underlying table read privileges against the DEFINER account. This approach is suitable for providing restricted data to reporting teams or applications. With SQL SECURITY INVOKER, underlying table access privileges are checked against the user calling the view; the view does not elevate privileges for the user.

These two modes are part of the authorization model, not merely a syntax option. Choosing the wrong one can prevent users from reading the view, or cause a view to unintentionally expose data that the calling account should not see. This lesson focuses on how MySQL determines the security context, required privileges when creating and querying views, applying least privilege, and auditing DEFINER accounts in operations.

## 1. Views and Security Context

A view stores a SELECT statement under an object name in a schema. Example:

```sql
CREATE VIEW reporting.v_order_summary AS
SELECT
    order_id,
    created_at,
    status,
    total_amount
FROM sales.orders;
```

When a user runs:

```sql
SELECT *
FROM reporting.v_order_summary;
```

MySQL needs to determine which privileges are used to read sales.orders. That decision is based on the view's SQL SECURITY attribute.

Two modes:

- SQL SECURITY DEFINER: checks access privileges on underlying objects against the view's DEFINER account.
- SQL SECURITY INVOKER: checks access privileges on underlying objects against the account executing the query.

If SQL SECURITY is omitted, MySQL defaults to DEFINER.

### 1.1. Who Is DEFINER?

DEFINER is the MySQL account recorded alongside the view definition. If DEFINER = ... is not specified, the account creating the view becomes the definer.

Example:

```sql
CREATE DEFINER = 'view_owner'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.v_order_summary AS
SELECT order_id, status, total_amount
FROM sales.orders;
```

In this example, 'view_owner'@'localhost' is the account used to check privileges on sales.orders when the view is invoked in DEFINER mode.

An account name consists of both user and host. 'view_owner'@'localhost' and 'view_owner'@'10.%' are two different accounts and can have different privileges.

### 1.2. Who Is INVOKER?

INVOKER is the connected account running the SELECT statement on the view. When using SQL SECURITY INVOKER, privileges on the tables and columns referenced in the view definition are checked against this account.

Example:

```sql
CREATE SQL SECURITY INVOKER
VIEW reporting.v_order_summary_invoker AS
SELECT order_id, status, total_amount
FROM sales.orders;
```

If report_reader calls the view, MySQL checks report_reader's required privileges on the columns of sales.orders. Having SELECT privilege on the view alone is not enough if the account lacks the necessary privileges on underlying objects.

## 2. Comparing DEFINER and INVOKER

| Criterion | SQL SECURITY DEFINER | SQL SECURITY INVOKER |
|---|---|---|
| Security context when reading underlying tables | DEFINER account | Account calling the view |
| Does the caller need direct privileges on underlying tables? | No, if privileges on the view are granted and the definer has required privileges | Yes, needs corresponding underlying privileges |
| Can the view be used to provide a restricted column set? | Yes, a common pattern | Cannot hide underlying privileges if the caller already has direct SELECT on those columns |
| Can it provide data to users without underlying table privileges? | Yes | No |
| Primary risk | Definer has overly broad privileges or view exposes unintended data | Caller lacks privileges on underlying tables/columns so queries fail |
| Suitable use case | Controlled access gateway for applications/reporting | Reusable SQL view while preserving per-caller privileges |

Easy-to-remember summary:

- DEFINER: the caller can read what the view permits, within the scope of the definer's privileges.
- INVOKER: the caller of the view must have privileges to read the underlying data required by the view query.

This description speaks to the security context when MySQL checks privileges. It does not mean DEFINER automatically restricts rows per user. The WHERE condition in the view must be designed to match data requirements.

## 3. Privileges Required When Creating a View

To create a view, the account executing the statement needs CREATE VIEW privilege on the target schema and SELECT privilege on the columns referenced in the SELECT defining the view.

Example preparing schema and table:

```sql
CREATE DATABASE IF NOT EXISTS sales;
CREATE DATABASE IF NOT EXISTS reporting;

CREATE TABLE sales.orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_email VARCHAR(320) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Create a dedicated account to serve as definer:

```sql
CREATE USER 'view_owner'@'localhost'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT CREATE VIEW ON reporting.*
    TO 'view_owner'@'localhost';

GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';
```

Then connect as the view_owner account and create the view. When DEFINER is not specified, this account becomes the definer:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_tenant_order_summary AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Creating the view and executing the view are two separate privilege check points. The account creating the view needs privileges to define the SELECT statement. When the view is called, MySQL continues checking privileges according to SQL SECURITY and the privileges existing at that time.

### 3.1. Specifying a DEFINER Different from the Current Account

You can explicitly write DEFINER = 'user'@'host' in CREATE VIEW. However, creating an object with a definer different from the current account is governed by special administrative privileges; privilege names and requirements can vary across MySQL versions.

In MySQL 8.0 releases, definer-related privileges have changed across versions, involving dynamic privileges such as SET_USER_ID, SET_ANY_DEFINER, and ALLOW_NONEXISTENT_DEFINER. Do not grant these privileges broadly just to create views.

A more controllable pattern is connecting with the service account intended as the definer, granting that account only the necessary CREATE VIEW and SELECT privileges, and creating the view while logged in as that account.

## 4. Granting SELECT Privilege on a View to Users

After the view is created, an administrator grants privileges on the view itself to the reader group:

```sql
CREATE USER 'report_reader'@'10.%'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'report_reader'@'10.%';
```

With an SQL SECURITY DEFINER view, report_reader can read the view without needing direct SELECT privileges on sales.orders, provided that:

- The caller has SELECT privilege on the view.
- The DEFINER account exists and has sufficient privileges on the underlying tables/columns needed by the view.
- The view does not depend on another object that the definer lacks privileges to access.
- Other application and server security conditions are satisfied.

Do not also run GRANT SELECT ON sales.* for report_reader if the goal is to force users to go through the view. Direct privileges on underlying tables can allow them to read data outside the view's scope.

### 4.1. Verifying Granted Privileges

Log in with the reporting reader account and test:

```sql
SELECT *
FROM reporting.v_tenant_order_summary
LIMIT 20;
```

Verify that direct access to the underlying table is denied if the account was not granted direct privileges:

```sql
SELECT *
FROM sales.orders
LIMIT 20;
```

Expected outcome: querying through the view succeeds; querying the underlying table directly returns a privilege error. This is an important test to confirm the authorization model works as intended.

Inspect account privileges:

```sql
SHOW GRANTS FOR 'report_reader'@'10.%';
SHOW GRANTS FOR 'view_owner'@'localhost';
```

SHOW GRANTS helps inspect both view privileges and definer privileges. If using roles, check granted roles and their activation status according to the account's policy.

## 5. How Can a View Restrict Columns and Rows?

A DEFINER view can expose only required columns and add filter conditions:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_public_orders AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status IN ('PAID', 'PENDING');
```

The customer_email column does not appear in the view. Anyone with only SELECT on the view cannot read this column through the view.

The WHERE condition also excludes rows with other statuses. However, if the view is not designed around a tenant or user context, that condition does not automatically create per-tenant row-level security.

For example, if every report_reader can view all tenants, the view above only filters status rather than isolating tenants. It should not be called tenant data isolation.

### 5.1. Creating Separate Views by Data Scope

If an application needs a fixed tenant scope, you can create a view with a specific tenant condition and grant the corresponding view only to that user group:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_tenant_42_orders AS
SELECT
    order_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE tenant_id = 42
  AND status <> 'CANCELLED';
```

This approach works when scopes are fixed in number and permissions are clearly managed. If there are thousands of tenants or tenants change dynamically by user, creating one view per tenant is usually hard to manage. A more appropriate authorization architecture is needed, such as a service layer enforcing tenant checks, separate schemas/databases, or a data model with dedicated access controls.

Do not use a client-settable session variable as the sole basis of security if the client can modify that variable itself.

## 6. SQL SECURITY INVOKER and Privileges on Underlying Tables

An INVOKER view is still useful for standardizing queries, giving business names, and reusing JOINs/filters. However, it does not let users borrow the privileges of the view creator.

Example creating the view:

```sql
CREATE SQL SECURITY INVOKER
VIEW reporting.v_orders_invoker AS
SELECT
    order_id,
    status,
    total_amount
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Grant privileges to the reader account:

```sql
GRANT SELECT
ON reporting.v_orders_invoker
TO 'report_reader'@'10.%';

GRANT SELECT (
    order_id,
    status,
    total_amount
)
ON sales.orders
TO 'report_reader'@'10.%';
```

When report_reader queries the view, MySQL checks privileges on the underlying table columns against that account. If the view references additional columns in WHERE, JOIN, GROUP BY, or expressions, required privileges must include the referenced columns according to MySQL's privilege checking rules.

In the example above, the user can also SELECT those three granted columns directly from sales.orders. Therefore, INVOKER is suitable when you want to preserve the caller's privileges, not when you need to hide underlying tables.

### 6.1. Testing Missing Privileges

If the account is only granted SELECT on the view without SELECT on the underlying table, querying through the INVOKER view will fail:

```sql
-- Run as report_reader after only receiving GRANT SELECT on the view:
SELECT *
FROM reporting.v_orders_invoker;
```

Then grant underlying column privileges as in the previous example and retry. Comparing both attempts clearly demonstrates that INVOKER uses the caller's privileges.

## 7. What Privileges Must DEFINER Have When the View Is Called?

With SQL SECURITY DEFINER, MySQL uses the definer's security context to check underlying objects. The DEFINER account needs the required privileges on tables, views, routines, or objects referenced in the view definition.

For example, view_owner was only granted SELECT on certain columns:

```sql
SHOW GRANTS FOR 'view_owner'@'localhost';
```

If an administrator later revokes a required privilege:

```sql
REVOKE SELECT (total_amount)
ON sales.orders
FROM 'view_owner'@'localhost';
```

The view referencing total_amount may no longer execute because the definer lacks privileges on that column. Creating the view successfully earlier does not mean privileges remain guaranteed forever.

Restore the required privilege:

```sql
GRANT SELECT (total_amount)
ON sales.orders
TO 'view_owner'@'localhost';
```

This is why definer privileges must be managed as a dependency of the view. When altering privileges on underlying tables, check dependent views, routines, and applications.

## 8. DEFINER Account Lifecycle

The DEFINER account is part of the view metadata. If the account is dropped, renamed, or loses necessary privileges, an SQL SECURITY DEFINER view may fail to execute.

Common problems:

- Dropping a service account while forgetting views referencing it.
- Restoring a schema to another environment without creating the definer account.
- Migrations creating views with a developer's personal account as the definer.
- A definer having overly broad privileges, such as server-wide administrative privileges.
- Changing privileges on underlying tables causing views to fail at runtime.

### 8.1. Using a Stable Service Account

Use a dedicated account for serving as a definer, with a clear name and specific host:

```sql
CREATE USER 'report_view_definer'@'localhost'
    IDENTIFIED BY 'managed-outside-the-application';
```

Grant only the privileges needed by the view, such as SELECT on specific columns of source tables. Do not use root or a DBA account as the definer just because it already has all privileges.

A definer account does not need to be an application account that logs in regularly. Appropriate authentication, network, and account policies can be applied to restrict direct logins, though you should verify account locking and account management behavior on the running server version before deploying.

### 8.2. Checking Which Definer a View Has

Inspect the definition:

```sql
SHOW CREATE VIEW reporting.v_tenant_order_summary;
```

Inspect metadata of views in a schema:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'reporting'
ORDER BY TABLE_NAME;
```

Important fields:

| Field | Meaning |
|---|---|
| DEFINER | Account recorded as definer |
| SECURITY_TYPE | DEFINER or INVOKER |
| CHECK_OPTION | NONE, LOCAL, or CASCADED |
| IS_UPDATABLE | Whether the view is updatable according to MySQL conditions |

You can use this output to verify that definers exist and compare them against the list of managed service accounts. Checking accounts and privileges should be done using an account with sufficient privileges to inspect metadata and grants.

## 9. Privileges to Create a View with a Different DEFINER

A DBA may need to deploy a view using a migration account while wanting the definer to be a stable service account. When using the DEFINER clause to specify an account different from the current user, MySQL requires appropriate administrative privileges.

Syntax example:

```sql
CREATE DEFINER = 'report_view_definer'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.v_orders_for_reports AS
SELECT
    order_id,
    status,
    total_amount
FROM sales.orders;
```

Do not grant special privileges to every developer just to run this statement. Let a controlled deployment pipeline perform the operation, or connect as the definer account to create the view.

Names and scopes of dynamic privileges related to DEFINER vary across MySQL releases. Before granting privileges in production, check documentation for the exact version and restrict privileges for migration accounts. In particular, allowing a nonexistent definer to be set can create orphaned views, causing runtime failures or risk if that account is later recreated.

## 10. View Privileges and Underlying Table Privileges

The following table summarizes privilege checking:

| Scenario | DEFINER | INVOKER |
|---|---|---|
| Caller has SELECT on view | Required | Required |
| Caller has SELECT on underlying table | Not required if definer has sufficient privileges | Needs appropriate privileges on underlying objects |
| Definer has SELECT on underlying table | Required | Not used as security context on call |
| Definer has underlying privileges revoked | Can cause the view to fail | Does not affect caller's privileges under INVOKER mechanism |
| Caller has underlying privileges revoked | View can still run if caller keeps SELECT on view and definer has sufficient privileges | View may fail |
| Caller has direct GRANT on underlying table | Can read outside the view if that privilege allows | Can read within the scope of granted privileges |

An important point: GRANT SELECT on a view does not automatically grant SELECT on underlying tables. Nor should you grant SELECT on the source schema to users merely because they need to run a DEFINER view.

## 11. GRANT, REVOKE, and the Least Privilege Principle

An authorization model should have three clear account groups:

1. Owner/definer account: granted read access to the exact columns or objects the view needs.
2. Reader account/role: only has SELECT on the permitted views.
3. Deployment/DBA account: has privileges to create or modify views according to deployment procedures.

Example applying least privilege:

```sql
GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'report_reader'@'10.%';
```

Revoking privileges on the view:

```sql
REVOKE SELECT
ON reporting.v_tenant_order_summary
FROM 'report_reader'@'10.%';
```

Revoking underlying privileges from the definer:

```sql
REVOKE SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
FROM 'view_owner'@'localhost';
```

Check the impact before running REVOKE. If the view is still used by applications, revoking underlying privileges can cause runtime queries to fail.

### 11.1. Using Roles for Reader Groups

MySQL supports roles for grouping privileges:

```sql
CREATE ROLE 'orders_report_reader';

GRANT SELECT
ON reporting.v_tenant_order_summary
TO 'orders_report_reader';

GRANT 'orders_report_reader'
TO 'report_reader'@'10.%';

SET DEFAULT ROLE 'orders_report_reader'
TO 'report_reader'@'10.%';
```

Roles help grant the same set of privileges to multiple accounts. You still need to verify default roles or active session roles; do not assume a granted role automatically activates in every session if configuration differs from expectations.

Do not include SELECT privileges on underlying tables in a reader role if the goal is to permit reading only through a DEFINER view.

## 12. SQL SECURITY and Nested Views

A view can reference another view. In that case, the security context is determined along the view chain and each view's SQL SECURITY attribute.

Example:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_order_base AS
SELECT order_id, tenant_id, status
FROM sales.orders;

CREATE SQL SECURITY INVOKER
VIEW reporting.v_order_dashboard AS
SELECT order_id, tenant_id, status
FROM reporting.v_order_base;
```

Do not assume that because the outer view uses DEFINER, every inner view automatically shares the same definer. Inspect each view's definition and test using the actual application account.

When designing multi-layer views:

- Keep the structure simple and easy to trace.
- Document the security mode of each view explicitly.
- Verify the definer of each object.
- Check underlying privileges and view privileges at each layer.
- Test with an actual reader account, not only a DBA account.
- Avoid creating overly deep view chains that obscure privilege checks and performance.

## 13. SQL SECURITY Does Not Replace CHECK OPTION

SQL SECURITY determines which account is used for privilege checks. WITH CHECK OPTION is a separate mechanism, applicable to updatable views to ensure rows INSERTed/UPDATEd through the view still satisfy the view's condition.

Example:

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_pending_orders AS
SELECT order_id, status, total_amount
FROM sales.orders
WHERE status = 'PENDING'
WITH CASCADED CHECK OPTION;
```

CHECK OPTION does not grant privileges and does not replace GRANT/REVOKE. Nor does it turn a view into a general-purpose row-level security mechanism. If a user only has SELECT on the view, they cannot UPDATE through it; if write privileges are granted, evaluate updatability and CHECK OPTION separately.

Distinguish between them:

| Mechanism | What Does It Protect? |
|---|---|
| SQL SECURITY DEFINER/INVOKER | Security context used to check privileges |
| GRANT/REVOKE | Which objects an account is allowed to access |
| WHERE in a view | Which rows appear in view results |
| WITH CHECK OPTION | Rows written through an updatable view must satisfy the view condition |
| PRIMARY/UNIQUE/CHECK/FK constraints | Data integrity rules enforced by the database |

## 14. Lab: Reader Only Accesses Data Through a DEFINER View

Perform this in a lab environment with appropriate DBA privileges.

### Step 1: Prepare Account and Privileges for the Definer

```sql
CREATE USER 'view_owner'@'localhost'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT CREATE VIEW ON reporting.*
    TO 'view_owner'@'localhost';

GRANT SELECT (
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
)
ON sales.orders
TO 'view_owner'@'localhost';
```

### Step 2: Connect as view_owner and Create the View

```sql
CREATE SQL SECURITY DEFINER
VIEW reporting.v_safe_orders AS
SELECT
    order_id,
    tenant_id,
    status,
    total_amount,
    created_at
FROM sales.orders
WHERE status <> 'CANCELLED';
```

Because the connected account is view_owner and no separate DEFINER is specified, this account becomes the definer.

### Step 3: Grant View Privileges to the Reader

```sql
CREATE USER 'view_reader'@'10.%'
    IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT
ON reporting.v_safe_orders
TO 'view_reader'@'10.%';
```

Do not grant SELECT on sales.orders to view_reader.

### Step 4: Test as view_reader

```sql
SELECT *
FROM reporting.v_safe_orders
LIMIT 20;
```

The query should succeed if the account, view, and definer privileges are all correct.

Attempt direct access to the source table:

```sql
SELECT *
FROM sales.orders
LIMIT 20;
```

This query must be rejected because view_reader has no privileges on the underlying table.

### Step 5: Revoke a Definer Privilege to Observe Dependency

In the lab, try revoking a column privilege that the view requires:

```sql
REVOKE SELECT (total_amount)
ON sales.orders
FROM 'view_owner'@'localhost';
```

Re-run the view query as view_reader. The query will fail because the definer no longer has the required privilege. Restore the privilege after testing:

```sql
GRANT SELECT (total_amount)
ON sales.orders
TO 'view_owner'@'localhost';
```

This experiment demonstrates that a DEFINER view depends on the runtime privileges of the definer account, not merely the creator's privileges at DDL time.

## 15. Troubleshooting Checklist When a View Reports a Privilege Error

When an application encounters a SELECT error on a view, inspect in this order:

1. Identify the actually connected account: CURRENT_USER() and USER().
2. Check whether the account has SELECT on the view using SHOW GRANTS.
3. Check SHOW CREATE VIEW to see DEFINER and SQL SECURITY.
4. For DEFINER, verify the definer account exists and has SELECT on all required underlying objects/columns.
5. For INVOKER, verify the caller's privileges on referenced tables/columns.
6. If views are nested, check SQL SECURITY and DEFINER for each inner view.
7. Check whether schemas/tables/columns were renamed or dropped after a migration.
8. Test with the actual application account, not just a DBA account.
9. After adjusting privileges, re-run the query and verify the correct data scope.
10. Record GRANT/REVOKE changes in the privilege management workflow.

Helpful commands:

```sql
SELECT
    USER() AS connection_identity,
    CURRENT_USER() AS privilege_identity;

SHOW CREATE VIEW reporting.v_safe_orders;

SHOW GRANTS FOR 'view_reader'@'10.%';
SHOW GRANTS FOR 'view_owner'@'localhost';
```

In normal queries, USER() reflects the connection identity, while CURRENT_USER() reflects the account used for privilege checking. When running through a DEFINER view, the security context inside the view can cause CURRENT_USER() to reflect the definer. Use them as diagnostic tools, not as an uncontrolled custom authorization mechanism based on returned strings.

## 16. Common Security Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Using root as DEFINER | View executes with overly broad privileges | Create a dedicated definer account with least privilege |
| Thinking GRANT SELECT on a view automatically grants underlying table access | Misunderstands runtime mechanism | Distinguish DEFINER and INVOKER |
| Granting SELECT on the source schema to readers | Users can read outside the view | Grant SELECT only on necessary views |
| Creating a DEFINER view with an insufficiently strict WHERE | View can expose out-of-scope rows | Review predicates and tenant model |
| Using INVOKER to hide underlying tables | Callers still need privileges on underlying tables/columns | Use a DEFINER view if access should go through the view |
| Dropping a definer account without reviewing dependencies | Views can fail at runtime | Check INFORMATION_SCHEMA.VIEWS before migrations |
| Revoking definer privileges without testing | Live views can fail | Manage definer privileges as dependencies |
| Allowing developers to set arbitrary DEFINERs | Objects can be created with unintended security contexts | Restrict dynamic privileges and control deployments |
| Confusing CHECK OPTION with SQL SECURITY | View does not enforce rules as expected | Understand that privileges and write validation are separate concerns |
| Only testing as DBA | Fails to catch missing privileges on application accounts | Test with actual accounts |

## 17. Secure View Design Checklist

Before creating a view:

- Determine whether the view is for SQL reuse or as a data access gateway.
- Choose DEFINER if callers need access through the view without underlying table privileges.
- Choose INVOKER if callers must undergo their own underlying privilege checks.
- Specify a stable definer account; avoid personal accounts or root.
- Grant the definer exact SELECT privileges on required columns/objects.
- Expose only needed columns and write accurate business filter conditions.
- Review nested views and the SQL SECURITY of each layer.
- Separate view creation privileges from view read privileges if the operational model requires it.

After creating:

- Inspect SHOW CREATE VIEW.
- Inspect INFORMATION_SCHEMA.VIEWS.
- GRANT SELECT on the exact view to the right account/role.
- Confirm readers do not have unintended direct privileges on source tables.
- Test queries using the actual application account.
- Test failure behavior when the definer lacks privileges in a lab environment.
- Track definer accounts across migration/backup/restore workflows.
- Periodically audit views with nonexistent definers or overly broad privileges.

## 18. Key Takeaways

- SQL SECURITY determines the security context when accessing a view.
- DEFINER uses the privileges of the view's defining account; INVOKER uses the privileges of the calling account.
- If SQL SECURITY is not specified, MySQL defaults to DEFINER.
- Callers of a DEFINER view need SELECT on the view; they do not need direct privileges on underlying tables if the definer has sufficient privileges.
- Callers of an INVOKER view need privileges on the view as well as corresponding underlying privileges on referenced objects/columns.
- Creating a view requires CREATE VIEW on the target schema and SELECT on columns used in the definition.
- DEFINER should be a stable service account with minimal privileges; avoid using root or personal accounts.
- Definer privileges must remain intact when the view runs; revoking underlying privileges can break the view.
- GRANT SELECT on a view is not equivalent to granting SELECT on source tables.
- A DEFINER view can restrict columns/rows, but predicates must accurately reflect the security scope; it does not automatically create per-tenant row-level security.
- SHOW CREATE VIEW, SHOW GRANTS, and INFORMATION_SCHEMA.VIEWS help verify security mode, definer, and privileges.
- WITH CHECK OPTION checks rows written through updatable views; it does not replace SQL SECURITY or GRANT/REVOKE.
- Nested views require checking the security context of each layer.
- Do not broadly grant special privileges to set arbitrary DEFINERs; exact privilege requirements depend on the MySQL version.

SQL SECURITY DEFINER/INVOKER is a critical boundary between a view's privileges and the caller's privileges. Choose the mode based on access goals, use a least-privilege definer, grant SELECT on the appropriate views, and test with real accounts to ensure users only see authorized data.

## References

- MySQL 8.0 Reference Manual — CREATE VIEW Statement: https://dev.mysql.com/doc/refman/8.0/en/create-view.html
- MySQL 8.0 Reference Manual — Stored Object Access Control: https://dev.mysql.com/doc/refman/8.0/en/stored-objects-security.html
- MySQL 8.0 Reference Manual — View Restrictions: https://dev.mysql.com/doc/refman/8.0/en/view-restrictions.html
- MySQL 8.0 Reference Manual — GRANT Statement: https://dev.mysql.com/doc/refman/8.0/en/grant.html
- MySQL 8.0 Reference Manual — The VIEWS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-views-table.html
