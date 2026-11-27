# Private Synonyms, Public Synonyms, and Object Resolution Risks in Oracle

In an Oracle system, tables and views often reside in a schema owned by one team or application. Other applications still need access to them without repeating long schema names in every SQL statement. A synonym provides an alternative name for a database object. As a result, applications can reference a table via a short or stable name even when the actual object lives in another schema.

Oracle has two main types of synonyms:

- **Private synonym:** created in a specific schema, serving naming within that schema's scope.
- **Public synonym:** created in the special `PUBLIC` schema, providing a shared name any schema can reference.

A synonym is strictly a naming layer. It does not create a copy of a table, transfer ownership, automatically grant SELECT/INSERT/UPDATE/DELETE privileges, or alter privileges on the target object. If a synonym points to the wrong object, a SQL statement can still succeed while reading or modifying the wrong data. This is a significant risk when systems use multiple schemas, public synonyms, `CURRENT_SCHEMA`, or unqualified object names.

After this lesson, you will be able to:

- Explain what a synonym is and distinguish private from public synonyms.
- Create, replace, inspect, and drop synonyms using SQL.
- Understand how Oracle resolves unqualified names and the role of CURRENT_SCHEMA.
- Recognize when a local object shadows a public synonym.
- Distinguish invalid synonym errors, missing target errors, missing privilege errors, and circular synonym chains.
- Understand that synonyms do not grant privileges, do not replace schema qualification, and do not guarantee the target object is always right.
- Use the data dictionary to inspect owner, target, database link, and reference status.
- Manage synonyms across dev/test/prod environments, migrations, dependencies, and database links.
- Reduce the risk of querying the wrong table using naming rules, privilege checks, and schema qualification.

> Examples use hypothetical schemas HR, APP, and SALES. Replace them with your actual schemas and corresponding privileges. Object names in examples are illustrative; do not assume the HR schema or sample tables exist in your database.

## 1. What Is a Synonym?

A synonym is an alternative name (alias) for a database object. A synonym stores metadata about the object it points to, including owner, object name, and optionally a database link.

For example, the EMPLOYEES table belongs to the HR schema. Schema APP is granted read privilege on this table:

```sql
GRANT SELECT ON hr.employees TO app;
```

User APP can create a private synonym:

```sql
CREATE SYNONYM employees
FOR hr.employees;
```

Then query:

```sql
SELECT employee_id, first_name, last_name
FROM employees;
```

Oracle resolves EMPLOYEES to the synonym in schema APP and forwards the reference to HR.EMPLOYEES. Data still resides in HR.EMPLOYEES; the synonym contains no rows.

### 1.1. A Synonym Is Not a View

| Characteristic | Synonym | View |
| --- | --- | --- |
| Nature | Alias for another object | Object storing a SELECT query definition |
| Stores own data | No | Standard views store no data; materialized views store results |
| Transforms columns/rows | No | Can project columns, join, filter, or compute expressions |
| Privileges | Does not grant privileges on target | Has view and underlying object privilege mechanisms per Oracle rules |
| Purpose | Simplifies names and hides location/owner | Provides a data interface via a query |

A synonym cannot add a WHERE clause, rename columns, or hide a complex data structure like a view does. If row/column restrictions per access policy are needed, consider views or appropriate security mechanisms; a synonym is not a data access control layer.

### 1.2. Object Types a Synonym Can Point To

Synonyms are commonly used for tables, views, sequences, procedures, functions, packages, materialized views, object types, and other schema objects Oracle allows referencing via synonyms. A synonym can also point to a remote object over a database link.

A synonym is not a way to alias a schema, a tablespace, or an arbitrary SELECT statement. The target object must match the reference type expected by the SQL/PLSQL statement.

### 1.3. Synonyms Can Be Created Before the Target Exists

Oracle permits creating a synonym referencing an object that does not yet exist or is currently inaccessible. A successful CREATE SYNONYM therefore does not prove the target exists or that the user holds privileges on it.

Only when the synonym is used does Oracle resolve the target object and check privileges. If the target is missing or invalid, the SQL statement fails even though the synonym remains in the dictionary. Always verify targets after creation and during deployment steps.

## 2. Private Synonyms

A private synonym belongs to a specific schema. It lets that schema use an alias for a target without repeating the owner name in every SQL statement.

### 2.1. Creating a Private Synonym in the Current Schema

Suppose you are connected as user APP with SELECT privilege on HR.EMPLOYEES:

```sql
CREATE SYNONYM employees
FOR hr.employees;
```

Query through the synonym:

```sql
SELECT employee_id, first_name
FROM employees;
```

Equivalent in target to:

```sql
SELECT employee_id, first_name
FROM hr.employees;
```

A private synonym does not make APP the owner of HR.EMPLOYEES. The table owner remains HR.

### 2.2. Creating a Private Synonym in Another Schema

A user with CREATE ANY SYNONYM can create a private synonym in another schema:

```sql
CREATE SYNONYM app.employee_directory
FOR hr.employees;
```

This privilege has broad scope and must be granted carefully. If creating synonyms only in your own schema, CREATE SYNONYM is sufficient.

### 2.3. Private Synonyms Can Point to Same-Schema or Cross-Schema Objects

A synonym does not require the target to reside in a different schema:

```sql
CREATE SYNONYM active_orders
FOR app.orders;
```

This creates an alias for APP.ORDERS. This can help decouple application names from physical names, but avoid redundant aliases that obscure what the true target is.

### 2.4. Privileges to Create and Drop Private Synonyms

| Action | Typical Privilege Required |
| --- | --- |
| Create synonym in own schema | CREATE SYNONYM |
| Create synonym in another schema | CREATE ANY SYNONYM |
| Drop synonym in own schema | Synonym owner |
| Drop synonym in another schema | DROP ANY SYNONYM |

A synonym owner can drop their own synonym with DROP SYNONYM. Dropping a synonym in another schema requires DROP ANY SYNONYM. Powerful administrative privileges like ANY privileges should be granted only when truly needed.

Drop a private synonym:

```sql
DROP SYNONYM employees;
```

If the synonym belongs to another schema and dropping is permitted:

```sql
DROP SYNONYM app.employee_directory;
```

DROP SYNONYM removes only the alias. It does not drop the table, view, sequence, or procedure the synonym points to.

## 3. Public Synonyms

A public synonym is created in the special PUBLIC schema. It provides a shared name so multiple schemas can reference the same target without each schema creating its own private synonym.

### 3.1. Creating a Public Synonym

Suppose HR.EMPLOYEES is a shared table:

```sql
CREATE PUBLIC SYNONYM employees
FOR hr.employees;
```

Once created, schemas can write:

```sql
SELECT employee_id, first_name
FROM employees;
```

However, the SELECT succeeds only if the executing user holds the required privileges on HR.EMPLOYEES. A public synonym does not grant SELECT to everyone.

### 3.2. Privileges to Create and Drop Public Synonyms

| Action | Privilege |
| --- | --- |
| Create public synonym | CREATE PUBLIC SYNONYM |
| Drop public synonym | DROP PUBLIC SYNONYM |

These are broad system privileges. In enterprise environments, typically only DBAs or authorized deployment accounts should manage public synonyms.

Drop a public synonym:

```sql
DROP PUBLIC SYNONYM employees;
```

This removes only the synonym named EMPLOYEES in PUBLIC; it does not drop HR.EMPLOYEES.

### 3.3. Public Synonym Does Not Mean Public Data

Three concepts must be kept separate:

1. **Public synonym:** provides a broadly resolvable name.
2. **Object privilege:** allows a user to SELECT, INSERT, UPDATE, DELETE, or EXECUTE on the target.
3. **System privilege/role:** permission to perform a class of actions or manage a scope of objects.

A public synonym can exist and be visible to a user who lacks read privileges on the target table. When that user queries through the synonym, Oracle still checks target privileges and rejects the query if missing.

Example:

```sql
CREATE PUBLIC SYNONYM payroll_data
FOR hr.payroll;

-- User APP does not automatically have read access to HR.PAYROLL.
-- DBA/owner must grant appropriate privilege if APP is allowed:
GRANT SELECT ON hr.payroll TO app;
```

Never treat public synonyms as a data-sharing mechanism or a replacement for GRANT.

## 4. How Do Private and Public Synonyms Differ?

| Criterion | Private Synonym | Public Synonym |
| --- | --- | --- |
| Owning schema | Specific schema | PUBLIC |
| Name scope | Belongs to that schema's namespace | Database-wide shared name |
| Create privilege | CREATE SYNONYM; or CREATE ANY SYNONYM for another schema | CREATE PUBLIC SYNONYM |
| Drop privilege | Owner or DROP ANY SYNONYM within scope | DROP PUBLIC SYNONYM |
| Impact of changing target | Affects statements using that private synonym | Can affect many schemas using the shared name |
| Conflict potential | With same-namespace objects in owning schema | Can be shadowed by local names during unqualified resolution |
| Governance | Typically managed by schema/application owner | Typically requires centralized governance |

### 4.1. When to Use Private Synonyms

Private synonyms fit when:

- An application needs a short name for a table in another data schema.
- Each application schema needs its own mapping to a distinct target.
- Deploying dev/test/prod with identical logical names but environment-controlled distinct targets.
- Avoiding database-wide shared names.

For example, APP_DEV.ORDERS and APP_TEST.ORDERS can be private synonyms pointing to separate data schemas. Ensure environment configurations are never mixed up during deployment.

### 4.2. When to Use Public Synonyms

Public synonyms fit when an object genuinely needs a shared name across many schemas under centralized DBA governance:

- A shared utility package or view.
- An object with a stable name referenced by many applications.
- Compatibility with legacy applications relying on unqualified names.

Avoid creating public synonyms for every table just to shorten SQL. Every public synonym expands the global naming surface, can mask missing schema qualification bugs, and makes switching targets harder to control.

## 5. How Does Oracle Resolve Synonym Names?

The biggest risk with synonyms is rarely the CREATE statement itself, but unqualified SQL statements. When encountering an unqualified name, Oracle must determine which object that name represents in the current session context.

### 5.1. Unqualified Names

For a reference such as:

```sql
SELECT *
FROM employees;
```

Oracle searches for the name in the current schema (CURRENT_SCHEMA), including local objects or matching private synonyms. If no local name is found, Oracle searches for a public synonym of the same name. Once a synonym is found, Oracle resolves the target it points to and checks access privileges on that target.

Conceptual resolution flow:

```text
Unqualified name: EMPLOYEES
             |
             v
      CURRENT_SCHEMA
             |
       Matching name?
          /       \
        Yes        No
        |            |
        v            v
  Use local object/ Search PUBLIC synonyms
  private synonym      |
                       v
                Matching synonym?
                  /          \
                Yes           No
                |               |
                v               v
          Resolve target     Name cannot
        & check privileges   be resolved
```

This is a conceptual model for unqualified object names; specific syntax and PL/SQL contexts may follow additional resolution rules. When target certainty is critical, specify both owner and object name.

### 5.2. Local Objects Shadow Public Synonyms

Suppose the DBA creates:

```sql
CREATE PUBLIC SYNONYM employees
FOR hr.employees;
```

APP can query EMPLOYEES via the public synonym if granted SELECT on HR.EMPLOYEES. Later, if a table or view named EMPLOYEES is created in the APP schema, the statement:

```sql
SELECT *
FROM employees;
```

inside APP resolves to that local object. The public synonym is no longer chosen for this unqualified name.

This is a form of shadowing. The application may keep running without errors while reading APP.EMPLOYEES instead of HR.EMPLOYEES. If both tables share similar columns, the mistake may go unnoticed and silently produce wrong business results.

### 5.3. Private Synonyms and In-Schema Objects

Private synonyms live in the owning schema's namespace. Two objects in the same namespace cannot share the same name within one schema. Thus, if APP already has a private synonym EMPLOYEES, APP cannot simultaneously create a table/view of the same name in that namespace; conversely, if table EMPLOYEES already exists, a same-named private synonym cannot be created.

Public synonyms reside in the PUBLIC namespace, so they can share names with objects inside a schema. Local objects take precedence when unqualified names are resolved within that schema.

### 5.4. Using Schema Qualification to Specify the Target

Compare:

```sql
-- Depends on CURRENT_SCHEMA and synonym resolution:
SELECT employee_id FROM employees;

-- Explicitly specifies owner and object:
SELECT employee_id FROM hr.employees;
```

HR.EMPLOYEES bypasses a same-named synonym in APP or a public synonym EMPLOYEES. If HR.EMPLOYEES is itself a synonym, Oracle continues resolving that synonym; qualification specifies the schema where lookup starts, not necessarily guaranteeing the final object is a physical table.

For critical statements involving finance, payroll, access control, or migrations, qualify schema names explicitly in SQL to avoid depending on public synonyms or session settings.

## 6. CURRENT_SCHEMA and SESSION_USER

Oracle has several closely related schema/user concepts that are not identical:

- SESSION_USER: the authenticated user who opened the session.
- CURRENT_SCHEMA: the default schema used when resolving unqualified names.
- CURRENT_USER: the active identity in certain security/PLSQL contexts; can differ from SESSION_USER when executing definer-rights code.

### 6.1. Checking Session Context

```sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

For instance, APP can change its default schema:

```sql
ALTER SESSION SET CURRENT_SCHEMA = hr;
```

Unqualified names like EMPLOYEES are then searched in HR first. SESSION_USER remains APP. Changing CURRENT_SCHEMA does not log in as HR, transfer ownership, or grant extra privileges on HR. APP can still perform only what APP's privileges permit.

### 6.2. Why Can CURRENT_SCHEMA Cause Surprises?

Connection pools reuse sessions. If a previous request ran:

```sql
ALTER SESSION SET CURRENT_SCHEMA = reporting;
```

and failed to reset the default schema, the next request may resolve the same SQL statement against REPORTING instead of APP. This session configuration bug can cause reading or writing the wrong data.

If an application sets CURRENT_SCHEMA per tenant or application schema:

- Set the schema in an explicit session initialization hook.
- Reset the schema before returning connections to the pool.
- Never assume each request receives a fresh session.
- Log CURRENT_SCHEMA in diagnostics when results vary across connections.
- Use schema qualification for sensitive SQL.

### 6.3. CURRENT_SCHEMA Is Not a Security Mechanism

Changing CURRENT_SCHEMA only changes where Oracle starts looking up unqualified names. It does not let a user read another schema's data without grants. Never use ALTER SESSION SET CURRENT_SCHEMA as a substitute for GRANTs, roles, VPD, or authorization controls.

## 7. Synonym Chains and Resolution Errors

A synonym can point to another synonym. Oracle must then follow multiple hops to locate the final target. This sometimes appears in legacy systems, but increases troubleshooting complexity.

### 7.1. Valid Synonym Chains

Example:

```sql
CREATE SYNONYM app.employee_alias
FOR hr.employee_directory;

CREATE SYNONYM hr.employee_directory
FOR hr.employees;
```

By name, APP.EMPLOYEE_ALIAS points to HR.EMPLOYEE_DIRECTORY, which points to HR.EMPLOYEES. Each hop can be modified independently, so debugging requires tracing the entire chain rather than stopping at the first synonym.

This example requires synonym-creation privileges in the respective schemas; the second statement runs as HR or via an account with CREATE ANY SYNONYM.

### 7.2. Nonexistent or Invalid Synonym Targets

A synonym can persist after its target is dropped or renamed. When SQL uses the synonym, Oracle cannot complete target resolution. A common error is:

```text
ORA-00980: synonym translation is no longer valid
```

Check:

1. Does the synonym still exist?
2. Are TABLE_OWNER and TABLE_NAME accurate?
3. Does the target exist in the specified schema?
4. Was the target renamed or dropped in a recent deployment?
5. If DB_LINK is set, are the database link and remote object operational?

ORA-00942 (table or view does not exist) can also occur when the target is missing or the user lacks access privileges. Never immediately conclude a table was dropped from that message alone; inspect owner, object, and privileges.

### 7.3. Looping Synonym Chains

Example:

```sql
CREATE SYNONYM app.a FOR app.b;
CREATE SYNONYM app.b FOR app.a;
```

The two synonyms reference each other in a cycle. When Oracle follows the chain, it cannot find a final target. Typical error:

```text
ORA-01775: looping chain of synonyms
```

Avoid multi-hop synonym chains without clear justification. A private synonym pointing directly to the final object is far easier to manage.

### 7.4. Synonyms Do Not Auto-Update When Targets Change

A synonym stores the target's name. If HR.EMPLOYEES is renamed, synonyms do not automatically guess the new table name. Perform a controlled migration:

1. Identify dependent synonyms and code.
2. Create the new target or rename per plan.
3. Update/recreate synonyms.
4. Verify privileges on the new target.
5. Recompile/validate dependent objects if needed.
6. Run smoke tests from the application schema.

Never treat CREATE OR REPLACE SYNONYM as a harmless change: repointing a target can make the exact same SQL query hit a different dataset.

## 8. Creating, Replacing, and Dropping Synonyms

### 8.1. CREATE SYNONYM

Private synonym in the current schema:

```sql
CREATE SYNONYM order_header
FOR sales.orders;
```

Private synonym in a specified schema (requires CREATE ANY SYNONYM if not the owner):

```sql
CREATE SYNONYM app.order_header
FOR sales.orders;
```

Public synonym:

```sql
CREATE PUBLIC SYNONYM order_header
FOR sales.orders;
```

### 8.2. CREATE OR REPLACE SYNONYM

When a synonym already exists and its target must change, use OR REPLACE:

```sql
CREATE OR REPLACE SYNONYM order_header
FOR sales.orders_v2;
```

For public synonyms:

```sql
CREATE OR REPLACE PUBLIC SYNONYM order_header
FOR sales.orders_v2;
```

OR REPLACE updates the synonym definition under the same name. It does not rename the target table, move data, or grant privileges on the new target. After repointing, verify privileges, columns expected by applications, and dependent objects. Changing a synonym can make the same SQL access a completely different object.

### 8.3. DROP SYNONYM and DROP PUBLIC SYNONYM

Drop a private synonym:

```sql
DROP SYNONYM order_header;
```

Drop a public synonym:

```sql
DROP PUBLIC SYNONYM order_header;
```

DROP commands remove only the alias. They never drop the target. If applications depend on the dropped synonym, unqualified SQL may stop resolving or resolve to another name (such as a same-named public synonym).

### 8.4. There Is No ALTER SYNONYM to Change Targets

To change a target, use CREATE OR REPLACE SYNONYM or DROP and recreate. Use controlled replacement in migrations. CREATE OR REPLACE avoids an outage window where the synonym name briefly disappears, though dependent code and targets must still be verified afterward.

## 9. Synonyms Pointing to Objects Over a Database Link

A synonym can point to an object in a remote database over a database link:

```sql
CREATE SYNONYM remote_customers
FOR crm.customers@crm_link;
```

The application can reference:

```sql
SELECT customer_id, customer_name
FROM remote_customers;
```

Oracle uses database link CRM_LINK to connect to the remote database and access CRM.CUSTOMERS. The synonym stores only the reference name; it does not create the database link, verify network connectivity, or grant remote privileges.

### 9.1. Conditions for Queries to Succeed

- The database link exists and is valid in the executing user's context.
- Remote service/host names and connection details are accurate.
- The remote database is available.
- The remote account holds privileges on CRM.CUSTOMERS.
- The remote object still exists with compatible schema/columns.
- Network ACLs, wallets, or connection settings (if applicable) permit access.

If a synonym specifies a DB_LINK but the link is dropped or the remote database is unavailable, SQL statements fail even though the local synonym still exists.

### 9.2. Private vs. Public Database Links

Database links also have their own scope:

- Private database links belong to the schema that created them.
- Public database links can be used more broadly subject to privileges and database configuration.

Do not confuse public synonyms with public database links. A public synonym can reference a database link, but that does not turn a private database link into a public one or share remote credentials with every user.

### 9.3. Risks of Public Synonyms Pointing to Remote Systems

A public synonym to a database link can couple many applications to a single remote service. If the remote endpoint, credentials, or table structure change, multiple schemas are affected simultaneously.

Best practices:

- Use meaningful synonym names that clearly indicate the data source.
- Manage database link creation/deletion centrally.
- Monitor remote dependency health.
- Run connectivity and query smoke tests after every deployment.
- Never place sensitive details in scripts/logs or share database links beyond authorized scope.

## 10. Inspecting Synonyms in the Data Dictionary

Oracle provides dictionary views to inspect synonyms. Object names in the dictionary are typically stored in uppercase unless created with quoted identifiers.

### 10.1. USER_SYNONYMS

List synonyms owned by the current schema:

```sql
SELECT
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM user_synonyms
ORDER BY synonym_name;
```

Key columns:

| Column | Meaning |
| --- | --- |
| SYNONYM_NAME | Alias name |
| TABLE_OWNER | Owner of the referenced object (if specified) |
| TABLE_NAME | Target object name |
| DB_LINK | Database link if the target resides in a remote database |

USER_SYNONYMS covers synonyms owned by the current schema; public synonyms do not belong to user schemas and require checking other views.

### 10.2. ALL_SYNONYMS

List synonyms visible to the user within view scope:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'EMPLOYEES'
ORDER BY owner;
```

Public synonyms have OWNER = PUBLIC. Results can also include private synonyms owned by other schemas visible under metadata rules. Inspect both OWNER and target, not just the synonym name.

### 10.3. DBA_SYNONYMS

DBA_SYNONYMS allows administrators to view all synonyms in the database:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM dba_synonyms
ORDER BY owner, synonym_name;
```

DBA_ views require appropriate dictionary privileges. If an application user lacks access, use ALL_SYNONYMS or request details from a DBA per process.

### 10.4. Finding Same-Named Synonyms Across Multiple Owners

When a SQL statement resolves unexpectedly, query all synonyms sharing that name:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = UPPER(:name_to_find)
ORDER BY
    CASE WHEN owner = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
         THEN 1
         WHEN owner = 'PUBLIC'
         THEN 2
         ELSE 3
    END,
    owner;
```

This ordering merely helps readers inspect CURRENT_SCHEMA and PUBLIC synonyms first. It is not an exact replica of the full name-resolution algorithm for every statement type.

### 10.5. Checking Whether a Target Exists in a Local Schema

For local targets:

```sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = UPPER(:target_owner)
  AND object_name = UPPER(:target_name)
ORDER BY object_type;
```

ALL_OBJECTS shows whether the object exists and its VALID/INVALID status where applicable. For remote targets, query metadata on the remote database over the link if privileged, or check directly on the remote system.

## 11. Dependencies and Impact of Changing Synonyms

A synonym introduces an intermediate naming layer. Views, procedures, functions, packages, or application SQL may rely on that name. Changing the target can affect column structures, privileges, and dependent code behavior.

### 11.1. Finding Dependent Objects

Schema dependency views assist investigation:

```sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = UPPER(:synonym_or_target_name)
ORDER BY type, name;
```

For database-wide visibility with privileges, DBAs can query DBA_DEPENDENCIES. Interpret results by object name and referenced owner/type; synonym chains or dynamic SQL can make dependency discovery non-trivial.

### 11.2. Static SQL vs. Dynamic SQL

- Static SQL in PL/SQL is analyzed at compile time and records corresponding dependency metadata.
- Dynamic SQL (EXECUTE IMMEDIATE) is resolved at runtime; dependencies may not appear completely like static SQL.
- Java/JDBC applications sending SQL text at runtime must also be searched in source code/configs/logs, not only via the data dictionary.

Thus USER_DEPENDENCIES is a valuable source, though not an exhaustive list of every consumer of a synonym.

### 11.3. Safe Target-Change Procedure

Before running CREATE OR REPLACE SYNONYM:

1. Inspect the current synonym and record the old target.
2. Locate dependent objects and application SQL using the alias name.
3. Verify the new target has matching structure, data, and owner.
4. Confirm required direct privileges exist on the new target.
5. Test the new synonym in a dev/test schema.
6. Schedule the change, update the synonym, and validate dependent code.
7. Run smoke tests using the exact application user, roles, and session context.
8. Monitor for ORA-00942, ORA-00980, ORA-01775, and privilege errors post-deploy.
9. Keep a rollback plan back to the old target if post-deployment checks fail.

Never repoint a production synonym to another table merely because two tables share column names. Verify semantics, data, triggers, constraints, transaction behavior, and privileges.

## 12. Synonyms and Access Privileges

Synonyms handle naming only. Privileges are always checked on the target object.

### 12.1. Granting Privileges on the Target

For example, HR owns EMPLOYEES and APP needs read access:

```sql
GRANT SELECT ON hr.employees TO app;
```

APP creates a private synonym:

```sql
CREATE SYNONYM employees FOR hr.employees;
```

APP can write:

```sql
SELECT employee_id, first_name
FROM employees;
```

If GRANT is omitted while the synonym is still created, the SELECT statement fails. Errors may surface as object-does-not-exist or insufficient-privileges depending on context; verify privileges on the target.

### 12.2. Synonyms Are Not an Object-Hiding Layer

A short alias does not keep the target secret. Metadata reveals owner and target; users with privileges on the target can still access it via schema-qualified names if known.

Never use synonyms to:

- Hide sensitive schemas.
- Replace GRANT/REVOKE.
- Enforce tenant boundaries.
- Restrict rows or columns.
- Grant privileges to users merely because they can see a public synonym.

If row/column controls are needed, consider views, VPD/FGAC, Database Vault, or security mechanisms aligned with your architecture and Oracle version.

### 12.3. Direct Privileges in Definer-Rights PL/SQL

Packages/procedures executing with DEFINER rights follow different privilege rules than direct session SQL. When compiling and running static SQL inside definer-rights PL/SQL, the program unit's owner needs direct object privileges; privileges inherited solely through roles are generally insufficient to compile/execute definer-rights code.

Creating a synonym in the package owner's schema does not substitute for direct GRANTs on the target. When hitting privilege errors only inside PL/SQL while the same SELECT works in a SQL worksheet, inspect AUTHID, the program unit owner, and direct grants.

### 12.4. Public Synonyms Widen Usage Surface

Public synonyms make a target name easy to reference from many schemas. For sensitive targets, prefer private synonyms or schema qualification and grant privileges only to required users. Never create a public synonym for an object just because one application wants a shorter name.

## 13. Object Resolution Risks and Mitigation

### 13.1. Same SQL, Different Target by Session

The SQL statement:

```sql
SELECT COUNT(*) FROM orders;
```

can resolve to APP.ORDERS in a session with CURRENT_SCHEMA = APP, yet resolve to REPORTING.ORDERS in a session with CURRENT_SCHEMA = REPORTING. If multiple schemas contain objects with the same name, unqualified code can return different results without any syntax error.

### 13.2. Public Synonyms Shadowed by Local Objects

A DBA creates public synonym ORDERS pointing to SALES.ORDERS. The application uses the public synonym. A later migration creates a table APP.ORDERS for staging data. Unqualified SQL inside APP silently starts reading APP.ORDERS. Behavior changes even though the original SELECT statement was never modified.

Before creating a new object, check for same-named public synonyms:

```sql
SELECT owner, synonym_name, table_owner, table_name
FROM all_synonyms
WHERE synonym_name = UPPER(:new_object_name);
```

Also check local objects:

```sql
SELECT object_name, object_type
FROM user_objects
WHERE object_name = UPPER(:new_object_name);
```

### 13.3. Synonym Target Changed While Applications Are Running

If a public or private synonym is updated via CREATE OR REPLACE, subsequent sessions using that name resolve to the new target. Applications may encounter:

- Missing columns.
- Different datatypes.
- Data belonging to a different tenant or environment.
- Missing privileges on the new target.
- Different triggers, constraints, or semantics.
- Different execution plans due to different indexes/statistics on the new object.

Treat target changes as API/schema contract changes and deploy them as tested migrations.

### 13.4. Similar Names and Quoted Identifiers

Oracle normally folds unquoted identifiers to uppercase. Names created with quoted identifiers are case-sensitive:

```sql
CREATE SYNONYM "EmployeeAlias"
FOR hr.employees;
```

References must then preserve exact quoted casing:

```sql
SELECT * FROM "EmployeeAlias";
```

Quoted names complicate code generators, ORMs, migrations, and dictionary queries. Standard practice is using unquoted identifiers consistent with Oracle's uppercase conventions.

### 13.5. Dev/Test/Prod Environments

A dangerous deployment bug occurs when a synonym in TEST accidentally points to PROD, or a synonym in PROD points to a test schema. Verify mappings per environment:

| Environment | Application Schema | Expected Target |
| --- | --- | --- |
| DEV | APP_DEV | DATA_DEV |
| TEST | APP_TEST | DATA_TEST |
| PROD | APP | DATA |

Never hard-code production endpoints into shared multi-environment scripts. Use controlled deployment variables/configs and log the actual resolved target for operator verification.

### 13.6. Risk Mitigation Principles

- Qualify owner names in sensitive SQL.
- Prefer private synonyms for local application needs.
- Restrict public synonyms and CREATE/DROP PUBLIC SYNONYM privileges.
- Avoid long or circular synonym chains.
- Never repoint targets outside controlled migrations.
- Verify CURRENT_SCHEMA management in connection pools.
- Inspect the data dictionary after deployments.
- Test with the exact application user, roles, schema context, and database links.
- Log targets and configuration versions during incident investigation.

## 14. Lab Exercise: Observing Private/Public Synonyms and Shadowing

The steps below require privileges to create schema objects and synonyms. Use a test schema; do not create common object names in shared schemas.

### 14.1. Create the Target Table

Run as DATA_OWNER (or an equivalent test schema):

```sql
CREATE TABLE lab_departments (
    department_id NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Engineering');
INSERT INTO lab_departments VALUES (20, 'Finance');
COMMIT;
```

Grant read privilege to application user APP:

```sql
GRANT SELECT ON data_owner.lab_departments TO app;
```

### 14.2. Create a Private Synonym in APP

Connect as APP:

```sql
CREATE SYNONYM departments
FOR data_owner.lab_departments;

SELECT department_id, department_name
FROM departments
ORDER BY department_id;
```

Results should show Engineering and Finance. Inspect the synonym:

```sql
SELECT synonym_name, table_owner, table_name
FROM user_synonyms
WHERE synonym_name = 'DEPARTMENTS';
```

### 14.3. Create a Same-Named Public Synonym

DBA or user with CREATE PUBLIC SYNONYM:

```sql
CREATE PUBLIC SYNONYM departments
FOR data_owner.lab_departments;
```

Since APP already has a private synonym with the same name, APP continues using its private synonym. Public synonyms act as a fallback when no matching name exists in the current schema.

### 14.4. Observe Shadowing with a Local Object

In APP, the private synonym DEPARTMENTS occupies that name in the namespace, so a table with the same name cannot be created. To observe public synonym shadowing, use a separate name that has only a public synonym:

DBA:

```sql
CREATE PUBLIC SYNONYM shared_departments
FOR data_owner.lab_departments;
```

APP:

```sql
SELECT department_id, department_name
FROM shared_departments;
```

Then create table APP.SHARED_DEPARTMENTS in the test schema:

```sql
CREATE TABLE shared_departments (
    department_id NUMBER(4),
    department_name VARCHAR2(80)
);

INSERT INTO shared_departments
VALUES (99, 'Local test object');
COMMIT;
```

Re-run:

```sql
SELECT department_id, department_name
FROM shared_departments;
```

The result is now the Local test object row from APP.SHARED_DEPARTMENTS. The SQL statement did not change, yet the local object took precedence over the public synonym.

Compare with the schema-qualified query:

```sql
SELECT department_id, department_name
FROM data_owner.lab_departments;
```

This query still reads the two rows from DATA_OWNER.LAB_DEPARTMENTS.

### 14.5. Restore the Test Environment

Drop the local object first:

```sql
DROP TABLE shared_departments;
```

If the public synonyms are no longer needed, DBA drops them:

```sql
DROP PUBLIC SYNONYM shared_departments;
DROP PUBLIC SYNONYM departments;
```

APP can drop the private synonym:

```sql
DROP SYNONYM departments;
```

Do not drop DATA_OWNER.LAB_DEPARTMENTS while other lab exercises still need it.

## 15. Common Error Reference Table

| Error/Symptom | Possible Cause | Investigation Path |
| --- | --- | --- |
| ORA-00942 | Target missing or user lacks privileges | Check owner, object, GRANTs, and database link |
| ORA-00980 | Synonym translation is no longer valid | Check target name, owner, renamed/dropped object, and DB link |
| ORA-01775 | Looping chain of synonyms | Trace TABLE_OWNER/TABLE_NAME and fix the chain |
| ORA-01031 | Insufficient privileges for operation or target access | Check CREATE/DROP SYNONYM and object privileges |
| CREATE SYNONYM reports name already used | Private synonym/table/view already exists in namespace | Query USER_OBJECTS and USER_SYNONYMS |
| SELECT returns data from another schema | Public synonym shadowed, CURRENT_SCHEMA changed, or wrong target | Check CURRENT_SCHEMA, local objects, and ALL_SYNONYMS |
| Synonym exists yet SELECT fails | Synonym does not grant target privileges | Check direct GRANTs and remote privileges |
| PL/SQL fails on privileges while SQL worksheet works | Definer-rights code lacks direct grant or different owner | Check AUTHID and direct privileges for owner |
| Remote synonym fails | DB link, network, credentials, or remote object error | Check DB link and query directly on remote database |
| Post-deploy code hits wrong table | CREATE OR REPLACE repointed target or wrong environment mapping | Compare old/new targets and run smoke tests |

## 16. Best Practices

1. **Treat synonyms as name aliases.** They are not tables, security views, or privilege grants.
2. **Qualify targets explicitly.** Use owner.object in sensitive SQL and deployment documentation.
3. **Prefer private synonyms for local needs.** Create public synonyms only when a database-wide shared name is truly necessary.
4. **Keep public synonym admin privileges tightly scoped.** CREATE/DROP PUBLIC SYNONYM can impact many applications.
5. **Check local objects before relying on public synonyms.** Local objects shadow same-named public synonyms.
6. **Verify CURRENT_SCHEMA in connection pools.** Set and restore session context systematically.
7. **Never use synonyms to replace GRANTs.** Users still need privileges on target objects.
8. **Avoid synonym chains and circular references.** Point directly to the final target whenever possible.
9. **Verify targets after CREATE/OR REPLACE.** Successful creation does not prove the target exists or is accessible.
10. **Manage synonyms as part of migrations.** Record old/new targets, dependent code, and rollback plans.
11. **Validate environment mappings.** DEV/TEST/PROD must point to their respective schemas and database links.
12. **Test using the actual application user.** DBA privileges can mask missing grants on real accounts.
13. **Use the dictionary for diagnostics.** Query USER_SYNONYMS, ALL_SYNONYMS, DBA_SYNONYMS, and dependencies.
14. **Avoid overusing quoted identifiers.** Consistent naming conventions reduce resolution and migration issues.

## 17. Self-Check Questions

1. What is a synonym, and does it store the target's data?
2. How does a private synonym differ from a public synonym in owning schema and name scope?
3. Why does a public synonym not automatically grant SELECT to all users?
4. What privilege is needed to create a private synonym in the current schema?
5. What privilege is needed to create a synonym in another schema?
6. What privileges are needed to create and drop public synonyms?
7. If APP has a table EMPLOYEES and PUBLIC has a synonym EMPLOYEES, which object does an unqualified SELECT in APP read?
8. How does CURRENT_SCHEMA differ from SESSION_USER?
9. Why must connection pools manage CURRENT_SCHEMA carefully?
10. What ambiguity does schema qualification like HR.EMPLOYEES eliminate?
11. Why can CREATE SYNONYM succeed even when the target does not yet exist?
12. How does ORA-00980 differ from ORA-00942?
13. What issue does ORA-01775 typically indicate?
14. How can synonym chains complicate debugging?
15. How do USER_SYNONYMS, ALL_SYNONYMS, and DBA_SYNONYMS differ in scope?
16. What does DB_LINK in USER_SYNONYMS indicate?
17. Why do synonyms not replace direct grants for definer-rights PL/SQL?
18. Why should CREATE OR REPLACE SYNONYM be treated as an impactful migration?
19. What components does a public synonym pointing to a remote object depend on?
20. What steps confirm an application accesses the right target after deployment?

## 18. Mental Model

```text
                 SYNONYM
                    |
         Alias name for an object
                    |
          +---------+----------+
          |                    |
          v                    v
    PRIVATE SYNONYM       PUBLIC SYNONYM
    Single schema          PUBLIC schema
    Local scope            Shared name
          |                    |
          +---------+----------+
                    |
                    v
             NAME RESOLUTION
                    |
         CURRENT_SCHEMA first
         PUBLIC synonym second
                    |
                    v
              TARGET OBJECT
                    |
      Check object privileges
      and database link if any
                    |
                    v
              SQL EXECUTES

RISKS
  - Local object shadows public synonym
  - Unexpected CURRENT_SCHEMA
  - Target dropped/renamed
  - Looping synonym chain
  - Missing privileges on target
  - Wrong DEV/TEST/PROD mapping

RISK MITIGATION
  - Schema qualification
  - Private synonyms as needed
  - Centralized public synonym governance
  - Dictionary and dependency checks
  - Smoke tests using application user
```

**Key takeaway:** private and public synonyms provide only alias names. Oracle resolves unqualified names against the current schema before considering public synonyms; local objects can shadow public names. Synonyms do not grant privileges and do not guarantee targets remain valid. Verify CURRENT_SCHEMA, dictionary owner/target mappings, privileges on target objects, and all dependencies before deploying or modifying synonyms.
