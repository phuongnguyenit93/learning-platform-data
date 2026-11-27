# Relationship Between User, Schema, and Object Ownership

## 1. The problem: who logs in, who owns the table, and who can use the table?

Imagine a sales system with an `ORDERS` table. A deployment process creates the table, a Java backend reads and writes orders, and a reporting team only needs to view the data. If every component logs into Oracle Database using a single account with full privileges, it becomes difficult to separate responsibilities and limit damage if credentials are leaked or a program executes an erroneous SQL statement.

Oracle solves this problem with related but **non-identical** concepts:

- **Database user (user):** an identity managed by Oracle for authentication and authorization. A user can be granted privileges to connect, create objects, or read and modify another user's objects.
- **Schema:** a namespace and collection of **schema objects** associated with a database user. In Oracle, a **schema has the same name as its corresponding user**.
- **Owner (object owner):** the user/schema to which an object belongs. For the table `SALES.ORDERS`, the owner is `SALES`, regardless of which session is running `SELECT`, `INSERT`, or managing the table according to granted privileges.
- **Privilege:** the ability to perform an Oracle-permitted action, such as `CREATE TABLE`, `SELECT` on a table, or `EXECUTE` on a package.
- **Role:** a set of privileges that can be granted to a user or another role to simplify privilege management.

Example diagram:

```text
                          ORACLE DATABASE / PDB
                                    |
             +----------------------+----------------------+
             |                      |                      |
           User                  User                   User
         LAB_OWNER              LAB_API               LAB_REPORT
             |                      |                      |
             v                      |                      |
      Schema LAB_OWNER              |                      |
        +--------------+            |                      |
        | LAB_ORDERS   |<-----------+------ GRANT SELECT, INSERT
        | LAB_CUSTOMERS|            |
        | Package ...  |            +-----------------------+
        +--------------+                                    |
             ^                                              |
             +------------------ GRANT SELECT --------------+
```

In the example above, `LAB_OWNER` owns the tables; `LAB_API` and `LAB_REPORT` are only **granted privileges to use** the parts they need. Having access privileges **does not automatically turn the grantee account into the owner**.

The goal of this lesson is to accurately distinguish `user`, `schema`, `owner`, `role`, and `privilege`; understand how Oracle resolves object names; know how to query metadata about ownership and granted privileges; and practice separating the data-owning account from application accounts.

## 2. User and schema: one-to-one in name, different in role

### 2.1. What is a database user?

A **database user** is an Oracle security object. A user can be authenticated by a password or other configured mechanisms; an account can be locked, expired, or have its own authentication policy. To open a standard login session, a user must have a valid authentication mechanism **and session creation privilege**, commonly the `CREATE SESSION` system privilege.

A user is typically associated with:

| Component | Purpose |
|---|---|
| Identity/username | Distinguishes the account during authentication, privilege granting, and activity auditing |
| Authentication mechanism | Determines how the user is verified when connecting |
| System privileges | Privileges such as `CREATE SESSION`, `CREATE TABLE`, `CREATE VIEW` |
| Object privileges | Privileges on tables, views, sequences, procedures, etc., in other schemas |
| Roles | Groups of privileges granted to the user, directly or via other roles |
| Default/temporary tablespace and quota | Configures where objects are stored, the temporary area, and the allowed space limit |
| Account status/profile | Policies for login status, passwords, resources, or session limits |

**Having a user does not mean the user is allowed to log in.** For example, an account dedicated to owning a schema can be locked to prevent direct logins after objects have been deployed; application sessions use a different account granted specific privileges.

### 2.2. What is a schema?

In Oracle, a **schema is the collection of schema objects belonging to a database user**. Those objects are typically referenced in the form:

```sql
schema_name.object_name
```

Example:

```sql
SELECT order_id, total_amount
FROM sales.orders;
```

Here:

- `SALES` is the **schema/owner** of the table.
- `ORDERS` is the object name.
- The person running the query **does not have to be** the user `SALES`; they only need the appropriate privilege.

When a user is created, Oracle establishes a schema with the **same name as the user**. To start having objects in the schema, valid DDL must be executed with appropriate privileges. There is no independent administrative operation like "create a schema `SALES` and then attach it to user `OTHER_USER`" under Oracle's standard model.

Oracle does have a `CREATE SCHEMA` statement to execute a batch of object creation and privilege grant operations under specific conditions; **the name of this command does not mean it creates an independent schema-user** as in some other database management systems.

### 2.3. How are user and schema similar and different?

For example, creating the database user `LAB_OWNER` creates a corresponding schema also named `LAB_OWNER`. When this user creates the table `LAB_ORDERS` in its own schema, the fully qualified name is:

```text
LAB_OWNER.LAB_ORDERS
```

In metadata, the table's owner will be `LAB_OWNER`. However, the two terms answer different questions:

| Question | Appropriate concept |
|---|---|
| "Who logs in and authenticates to the database?" | User/session |
| "Which namespace does the object belong to?" | Schema |
| "Who owns the `ORDERS` table?" | Owner |
| "Which tables can this account `SELECT` from?" | Object privileges/roles |
| "Can this account create tables?" | System privileges and related conditions |
| "Where are the datafiles storing the table located?" | Tablespace, segment, datafile, not the username |

### 2.4. Schema differs from database and tablespace

These are three layers that are frequently confused:

```text
DATABASE (or PDB in a multitenant environment)
  |
  +-- User/Schema LAB_OWNER
  |     +-- LAB_ORDERS (table)
  |     +-- IDX_LAB_ORDERS (index)
  |     +-- API_ORDER_PKG (package)
  |
  +-- User/Schema LAB_REPORT
  |     +-- REPORT_VIEW (view)
  |
  +-- Tablespace USERS
  |     +-- Segments belonging to multiple different schemas
  |
  +-- Tablespace APP_INDEX
        +-- Index segments per configuration
```

- **Database/PDB** is the scope containing multiple users/schemas and other objects.
- **Schema** organizes objects by **ownership and name**.
- **Tablespace** organizes **logical storage space** for segments. Multiple schemas can place segments in the same tablespace; one schema can also have segments across multiple tablespaces.

Setting `DEFAULT TABLESPACE USERS` for a user does **not** turn the `USERS` tablespace into "that user's schema." Moving a segment to a different tablespace also does **not** change the table's owner.

## 3. Object ownership: who does an object belong to?

### 3.1. What are schema objects?

A schema can contain many types of objects, such as:

| Type | Example | Role |
|---|---|---|
| **Table** | `LAB_OWNER.LAB_ORDERS` | Stores row/column data |
| **View** | `LAB_OWNER.V_ACTIVE_ORDERS` | Stores a query definition for accessing data |
| **Index** | `LAB_OWNER.IDX_ORDERS_CUSTOMER` | Supports access paths and certain constraints |
| **Sequence** | `LAB_OWNER.ORDER_SEQ` | Generates sequential values |
| **Procedure/function** | `LAB_OWNER.CREATE_ORDER` | PL/SQL code stored in the schema |
| **Package** | `LAB_OWNER.ORDER_API` | Groups PL/SQL declarations and operations |
| **Trigger** | `LAB_OWNER.TRG_ORDER_AUDIT` | Code fired by a matching event |
| **Private synonym** | `LAB_REPORT.ORDERS` | Alias referencing another object |
| **Materialized view** | `LAB_OWNER.MV_SALES_MONTHLY` | Stored query results updated via an appropriate refresh mechanism |

**Not every Oracle object is a schema object.** Users, roles, tablespaces, profiles, and database-level settings follow a different administrative model. Certain global object types such as public synonyms should also not be treated the same as private synonyms inside a user schema.

### 3.2. Ownership is tied to the object name, not the query runner

Example:

```sql
SELECT *
FROM lab_owner.lab_orders;
```

Even if the SQL statement is executed by `LAB_API`, the table still belongs to `LAB_OWNER`.

When `LAB_API` performs a granted operation:

```sql
INSERT INTO lab_owner.lab_orders (order_id, customer_name, total_amount)
VALUES (1001, 'Lan', 250000);
```

**The owner of the table does not change.** The row of data may have been created by a transaction from `LAB_API`, but the owner of the **table object** remains `LAB_OWNER`. If the application needs to know who created each order, it must design audit columns or an appropriate logging mechanism; the "owner" field in metadata does not answer the question "who created this row."

### 3.3. An owner's privileges on their own objects

The owner has the right to manage and operate on their own objects according to Oracle's rules; for instance, an owner generally does not need to `GRANT SELECT` to themselves on a table they own. However, **ownership does not imply having every system privilege**:

- Owning a table does not automatically grant the privilege to create new users.
- Owning a table does not automatically grant the privilege to read tables in arbitrary schemas.
- Owning a package does not automatically grant the privilege to create or alter another user's objects.
- Creating new object types still requires the appropriate system privilege and accompanying conditions.

In operations, you should distinguish **the privilege to create objects**, **object ownership**, and **the privilege to use existing objects**. These three are not the same.

## 4. Who becomes the owner when creating an object?

### 4.1. Creating an object in one's own schema

Suppose the session is logged in as `LAB_OWNER`, and has been granted `CREATE TABLE` along with the required quota:

```sql
CREATE TABLE lab_orders (
    order_id     NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);
```

Because no schema prefix is specified, the table is typically created in the user's schema according to the current DDL context and rules. In this example, the fully qualified name is `LAB_OWNER.LAB_ORDERS`.

### 4.2. Creating an object in another schema is a special-privilege case

An administrative account granted appropriate privileges can execute DDL statements to create or modify objects in another schema, for example:

```sql
-- Illustrates syntax and administrative privilege scope only.
CREATE TABLE lab_owner.admin_created_table (
    id NUMBER
);
```

To do this, the session must have the **appropriate system privilege** such as `CREATE ANY TABLE` and satisfy related conditions. When the command is valid, the owner of the table is `LAB_OWNER`, **not necessarily the user who executed the DDL**.

`ANY` privileges allow cross-schema impact and have a broad scope. Do not grant these privileges to regular application accounts.

### 4.3. Does renaming a table change its owner?

No. Renaming an object within the same schema changes the object's name, not its owning schema. To transfer data ownership between schemas, you typically need an appropriate migration process such as creating the object in the target schema, moving/copying the data, and migrating grants, dependencies, and related metadata. Do not assume that running `ALTER SESSION SET CURRENT_SCHEMA` or changing the `schema.table` string can change the owner.

### 4.4. How does `DROP USER ... CASCADE` affect a schema?

Because a schema is tied to its user, dropping a user with `CASCADE` can drop **all objects belonging to that schema** and affect objects in other schemas that reference them. This is a destructive operation that requires backup/restore procedures, dependency assessment, and scope confirmation before a DBA executes it.

```sql
-- DANGEROUS COMMAND, shown for recognition only; DO NOT RUN on real data environments.
-- DROP USER lab_owner CASCADE;
```

## 5. Oracle privileges: system privilege, object privilege, and role

### 5.1. System privilege: permission to perform an operation type

A **system privilege** allows a user to perform a category of operations within the scope defined by that privilege.

| Privilege | Meaning |
|---|---|
| `CREATE SESSION` | Allows opening a login session when authentication and account status conditions are met |
| `CREATE TABLE` | Allows creating tables in the schema subject to privilege scope and storage conditions |
| `CREATE VIEW` | Allows creating views in the schema subject to privilege and dependency rules |
| `CREATE SEQUENCE` | Allows creating sequences in the schema |
| `CREATE PROCEDURE` | Allows creating eligible PL/SQL program objects in the schema |
| `CREATE ANY TABLE` | Privilege to create tables in other schemas under Oracle rules; broad scope |
| `SELECT ANY TABLE` | Privilege to read many tables/views across schemas within privilege scope; very broad scope |

Do not assume that someone with `CREATE SESSION` automatically has `SELECT` on application tables, or that someone with `CREATE TABLE` can automatically run `CREATE TABLE OTHER_SCHEMA.X` without the corresponding `ANY` privilege.

### 5.2. Object privilege: permission on a specific object

An **object privilege** applies to a specific object or eligible object type:

```sql
GRANT SELECT ON lab_orders TO lab_report;
GRANT SELECT, INSERT ON lab_orders TO lab_api;
```

These two lines are executed by the owner `LAB_OWNER` in the example. Result:

- `LAB_REPORT` can read `LAB_OWNER.LAB_ORDERS`.
- `LAB_API` can read and insert data into `LAB_OWNER.LAB_ORDERS`.
- Being granted `SELECT` does not grant `UPDATE`, `DELETE`, `ALTER`, or `DROP` on the table.
- Being granted `INSERT` does not change the table's owner to `LAB_API`.

Some commonly used privileges:

| Object type | Common object privileges | Example |
|---|---|---|
| Table/view | `SELECT`, `INSERT`, `UPDATE`, `DELETE` per Oracle conditions | `GRANT SELECT ON lab_orders ...` |
| Sequence | `SELECT` to fetch sequence values when permitted | `GRANT SELECT ON order_seq ...` |
| Procedure/function/package | `EXECUTE` | `GRANT EXECUTE ON order_api ...` |

Beyond the examples above, Oracle supports additional privileges depending on the object type and version. Grant only the privileges actually needed, and verify specific behavior when designing access policies.

### 5.3. Roles help manage multiple privileges

When multiple reporting accounts need to read the same group of tables, a role can be used to group privileges:

```sql
-- Executed by an administrative account with privilege to create roles.
CREATE ROLE app_report_role;

-- Executed by the owner or an account with privilege to grant object privileges.
GRANT SELECT ON lab_owner.lab_orders TO app_report_role;

-- Executed by an account with privilege to grant the role.
GRANT app_report_role TO lab_report;
```

From then on, `LAB_REPORT` can receive privileges through the role when the role is enabled and the execution context allows using role-based privileges.

**Specifically for stored PL/SQL in the database:** when compiling **definer's rights** objects, privileges on referenced objects usually must be **granted directly to the program owner**, rather than only through a role. Role rules also depend on the execution mode (`AUTHID DEFINER` vs. `AUTHID CURRENT_USER`) and Oracle features for program units. Therefore, a `SELECT` statement that runs in a SQL worksheet does not guarantee that a procedure containing that exact `SELECT` will compile if the privilege only comes from a role.

### 5.4. `GRANT`, `REVOKE`, `WITH GRANT OPTION`, `WITH ADMIN OPTION`

| Mechanism | Purpose |
|---|---|
| `GRANT` | Grants a privilege or role according to the grantor's authority |
| `REVOKE` | Revokes a granted privilege or role according to Oracle rules |
| `WITH GRANT OPTION` | Allows the recipient of an **object privilege** to further grant that privilege on the object to eligible users/roles |
| `WITH ADMIN OPTION` | Used with a **system privilege or role** to allow administering grants of that privilege/role per Oracle rules |

Example:

```sql
-- In LAB_OWNER's session:
GRANT SELECT ON lab_orders TO lab_report;

-- When revoking the direct grant:
REVOKE SELECT ON lab_orders FROM lab_report;
```

After `REVOKE`, if `LAB_REPORT` is still permitted access through a role or another active privilege, revoking **a single direct grant** may not be enough to block all access paths. All active privileges must be reviewed.

**Do not grant `WITH GRANT OPTION` just so an application can read a table.** Re-granting rights can expand access scope unexpectedly.

## 6. Hands-on SQL: separating owner, API, and reporting accounts

This section builds a self-contained example with three users to clearly observe the relationship between ownership and privileges. Only use a **practice database/PDB** and an administrative account permitted to create users. Administrative steps may require DBA assistance. Do not run user/role creation commands on production systems without an approved procedure.

### Step 1. Prepare accounts using an administrative user

The passwords in the example are placeholders and must be replaced with appropriate values provided by your environment's secret management. `USERS` is an example tablespace name; if your environment does not have that tablespace, use the tablespace designated by your DBA.

```sql
-- Run in a practice PDB using an administrative user with appropriate privileges.
CREATE USER lab_owner
    IDENTIFIED BY "<replace_with_owner_password>"
    DEFAULT TABLESPACE users;

CREATE USER lab_api
    IDENTIFIED BY "<replace_with_api_password>";

CREATE USER lab_report
    IDENTIFIED BY "<replace_with_report_password>";

GRANT CREATE SESSION, CREATE TABLE TO lab_owner;
GRANT CREATE SESSION TO lab_api, lab_report;

ALTER USER lab_owner QUOTA 20M ON users;
```

Explanation:

- Each `CREATE USER` creates a database identity and a schema of the same name.
- `LAB_OWNER` is permitted to create tables in its own schema.
- `LAB_API` and `LAB_REPORT` are permitted to open sessions; they **have not yet been granted privileges to read `LAB_OWNER` tables**.
- The quota granted to `LAB_OWNER` is a storage condition for creating tables in the example tablespace; quota and DDL privileges are two separate mechanisms.
- In real environments, configuring account status, profile, authentication, default/temp tablespaces, privileges, and quotas must follow DBA policies.

### Step 2. Create the table using the schema-owning account

Connect via SQL*Plus/SQLcl or SQL Developer as `LAB_OWNER`, then run:

```sql
CREATE TABLE lab_orders (
    order_id      NUMBER NOT NULL,
    customer_name VARCHAR2(100) NOT NULL,
    total_amount  NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT ck_lab_orders_total CHECK (total_amount >= 0)
);

INSERT INTO lab_orders (order_id, customer_name, total_amount)
VALUES (1001, 'Nguyen Lan', 250000);

INSERT INTO lab_orders (order_id, customer_name, total_amount)
VALUES (1002, 'Tran Minh', 420000);

COMMIT;
```

Here the table's fully qualified name is `LAB_OWNER.LAB_ORDERS`. You do not need to type the `LAB_OWNER.` prefix when working inside the matching schema; however, when accessing from another user, specifying the fully qualified name helps avoid confusion.

### Step 3. Check the owner from metadata

Still as `LAB_OWNER`:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'LAB_ORDERS';
```

`USER_OBJECTS` is metadata for objects in the current user's schema, so it does not have an `OWNER` column like `ALL_OBJECTS`. To see the owner explicitly, you can run:

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE owner = 'LAB_OWNER'
  AND object_name = 'LAB_ORDERS';
```

The newly created object has owner `LAB_OWNER`. Unquoted names like `lab_orders` are stored by Oracle in uppercase according to standard identifier rules, so the dictionary filter uses `'LAB_ORDERS'`.

### Step 4. Attempt access from another account before granting privileges

Log in as `LAB_REPORT` and try:

```sql
SELECT order_id, total_amount
FROM lab_owner.lab_orders;
```

If the user has no other privilege allowing them to read the table, Oracle denies access. When referencing a nonexistent or invisible table, the typical error is `ORA-00942: table or view does not exist`. This error **does not necessarily** mean the table has not been created; Oracle also uses it to avoid leaking object existence information when privileges are absent.

### Step 5. The owner grants the exact required privileges

Return to the `LAB_OWNER` session:

```sql
GRANT SELECT ON lab_orders TO lab_report;
GRANT SELECT, INSERT ON lab_orders TO lab_api;
```

`GRANT` statements are processed by Oracle as DCL statements and take effect according to database rules. Afterward:

**As `LAB_REPORT`:**

```sql
SELECT order_id, customer_name, total_amount
FROM lab_owner.lab_orders
ORDER BY order_id;
```

**As `LAB_API`:**

```sql
INSERT INTO lab_owner.lab_orders (order_id, customer_name, total_amount)
VALUES (1003, 'Le An', 150000);

COMMIT;

SELECT COUNT(*) AS total_orders
FROM lab_owner.lab_orders;
```

When `LAB_API` inserts a row, the new row still resides in `LAB_OWNER.LAB_ORDERS`. Committing the transaction as `LAB_API` **does not transfer table ownership**.

### Step 6. Inspect the grant list

In the `LAB_OWNER` session, inspect direct grants made by the owner:

```sql
SELECT table_name,
       grantee,
       privilege,
       grantable
FROM user_tab_privs_made
WHERE table_name = 'LAB_ORDERS'
ORDER BY grantee, privilege;
```

In the `LAB_REPORT` session, inspect directly received object privileges:

```sql
SELECT owner,
       table_name,
       privilege,
       grantor
FROM user_tab_privs_recd
WHERE owner = 'LAB_OWNER'
  AND table_name = 'LAB_ORDERS';
```

`USER_TAB_PRIVS_MADE` and `USER_TAB_PRIVS_RECD` focus on **grants recorded within the scope of those views**; to analyze all effective privileges, you also need to inspect roles, system privileges, and execution context.

### Step 7. Clean up practice resources

At the end of the lab, a DBA can assist with revoking privileges and dropping the demonstration tables and accounts per standard procedures. In particular, `DROP TABLE` and `DROP USER ... CASCADE` are destructive to data and can affect dependencies; only perform them after confirming the exact environment and objects authorized for removal.

## 7. Object names with and without a schema prefix

### 7.1. Why can `SELECT * FROM orders` pick the wrong table?

Suppose a PDB contains two schemas:

```text
SALES.ORDERS
REPORT.ORDERS
```

The SQL statement:

```sql
SELECT * FROM orders;
```

only states the **unqualified name** `ORDERS`. Oracle must resolve the name based on the current schema context, existing objects, and name resolution rules (including synonyms if applicable). Therefore, this SQL statement alone is not enough to determine which table is being read.

Using the fully qualified name makes intent explicit:

```sql
SELECT * FROM sales.orders;
```

Writing `SALES.ORDERS` **does not grant privileges by itself**. If the current user is not permitted to access it, the SQL statement still fails.

### 7.2. `CURRENT_SCHEMA` vs. `SESSION_USER`

Within a SQL session, you can query:

```sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

- **`SESSION_USER`**: the user identity of the login session.
- **`CURRENT_SCHEMA`**: the default schema used when resolving certain unqualified object names.

Oracle allows setting the session's default schema:

```sql
ALTER SESSION SET CURRENT_SCHEMA = LAB_OWNER;

SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

If executed as `LAB_REPORT`, after `ALTER SESSION`:

```text
SESSION_USER   = LAB_REPORT
CURRENT_SCHEMA = LAB_OWNER
```

You can write:

```sql
SELECT order_id FROM lab_orders;
```

instead of:

```sql
SELECT order_id FROM lab_owner.lab_orders;
```

but only if `LAB_REPORT` **already has the `SELECT` privilege**. `ALTER SESSION SET CURRENT_SCHEMA` **does not re-authenticate**, **does not change the user**, and **does not grant additional object privileges**.

If you need to restore the original schema context in the example session:

```sql
ALTER SESSION SET CURRENT_SCHEMA = LAB_REPORT;
```

### 7.3. Does a synonym change ownership?

A synonym is an **alias** for an object name. For example, if `LAB_REPORT` has `CREATE SYNONYM` and `SELECT` on the underlying table:

```sql
-- In LAB_REPORT's session:
CREATE SYNONYM my_orders FOR lab_owner.lab_orders;

SELECT order_id FROM my_orders;
```

In this example:

- `LAB_REPORT.MY_ORDERS` is a **private synonym** belonging to schema `LAB_REPORT`.
- `LAB_OWNER.LAB_ORDERS` remains a table owned by `LAB_OWNER`.
- Creating a synonym **does not grant read privileges on the underlying table**.

This is why metadata may show a user owning a `SYNONYM` while **not owning the table** referenced by that synonym.

**Public synonyms** have a broader name resolution scope and require careful administration to avoid naming conflicts and confusion about the source object.

### 7.4. Case-sensitive names using double quotes

Oracle normally converts **unquoted** identifiers to uppercase in metadata:

```sql
CREATE TABLE demo_case (id NUMBER);
-- Standard dictionary name: DEMO_CASE
```

If you intentionally create quoted identifiers:

```sql
CREATE TABLE "DemoCase" ("Id" NUMBER);
```

the name is preserved with its exact casing, and referencing SQL statements must use double quotes and matching case, such as `"DemoCase"."Id"`.

For application systems, following an unquoted naming convention for table and column names typically keeps writing SQL, running migrations, and reading metadata simpler.

## 8. Viewing users, owners, and privileges via the data dictionary

Oracle provides multiple groups of dictionary views. You must distinguish **the scope of visible data** from **the privileges required to query the views**.

### 8.1. `USER_`, `ALL_`, `DBA_`: three perspectives

| View prefix | General scope | Examples |
|---|---|---|
| `USER_...` | Objects/information belonging to the connected user's schema | `USER_TABLES`, `USER_OBJECTS`, `USER_INDEXES` |
| `ALL_...` | Objects/information accessible or visible based on privileges and view rules | `ALL_TABLES`, `ALL_OBJECTS`, `ALL_TAB_COLUMNS` |
| `DBA_...` | Broader administrative perspective across the database/container | `DBA_USERS`, `DBA_OBJECTS`, `DBA_TAB_PRIVS` |

Typically, application users can query `USER_` and appropriate `ALL_` views. `DBA_` views require appropriate dictionary viewing privileges; do not grant administrative privileges just to run a learning query.

**Note:** `ALL_OBJECTS` shows objects visible within the scope of the view, but **you should not treat every row as proof that the user can perform every operation on that object**. To know what specific operations are allowed, you still need to check the corresponding privileges.

### 8.2. Viewing objects in the currently connected schema

```sql
SELECT object_name,
       object_type,
       status,
       created
FROM user_objects
ORDER BY object_type, object_name;
```

When connected as `LAB_OWNER`, the result lists objects belonging to that schema. `USER_OBJECTS` does not need an owner column because its scope is already restricted to the current user.

Viewing tables and indexes in the schema:

```sql
SELECT table_name, tablespace_name
FROM user_tables
ORDER BY table_name;

SELECT index_name, table_name, tablespace_name
FROM user_indexes
ORDER BY table_name, index_name;
```

Do not confuse `TABLESPACE_NAME` with the owner. It is where the corresponding segment is allocated, not the object's owning identity.

### 8.3. Viewing owners of visible objects

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'LAB_ORDERS'
ORDER BY owner, object_type;
```

The `OWNER` column identifies the schema that owns the object. If the current user lacks privilege to see the object, `ALL_OBJECTS` may return no matching row even if the object actually exists in the database.

To filter tables in a specific schema:

```sql
SELECT owner, table_name, tablespace_name
FROM all_tables
WHERE owner = 'LAB_OWNER'
ORDER BY table_name;
```

### 8.4. Administrative perspective: user list and object ownership

For a DBA user with appropriate privileges:

```sql
SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace
FROM dba_users
WHERE username IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY username;
```

Viewing ownership counts from metadata:

```sql
SELECT owner, object_type, COUNT(*) AS object_count
FROM dba_objects
WHERE owner IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

This is an **object dictionary** count and does not directly indicate segment storage size or row counts; not all object types have their own storage segments.

### 8.5. Viewing privileges on objects

In the owner's (`LAB_OWNER`) session:

```sql
SELECT table_name, grantee, privilege, grantable
FROM user_tab_privs_made
WHERE table_name = 'LAB_ORDERS';
```

As a DBA:

```sql
SELECT owner, table_name, grantee, privilege, grantable
FROM dba_tab_privs
WHERE owner = 'LAB_OWNER'
  AND table_name = 'LAB_ORDERS'
ORDER BY grantee, privilege;
```

Viewing directly granted system privileges in an administrative scope:

```sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY grantee, privilege;
```

Viewing granted roles:

```sql
SELECT grantee, granted_role, admin_option, default_role
FROM dba_role_privs
WHERE grantee IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY grantee, granted_role;
```

To inspect privileges and roles **active in the current session**:

```sql
SELECT privilege FROM session_privs ORDER BY privilege;

SELECT role FROM session_roles ORDER BY role;
```

Privileges can be granted directly, via roles, or under special policies/modes. Therefore, you should inspect metadata alongside session context and test operations in a practice environment when behavior needs verification.

## 9. Object ownership and PL/SQL execution rights

Distinguishing user/schema/owner is especially important when working with **stored procedures, functions, packages, or views**.

### 9.1. Which schema does a procedure belong to?

Suppose:

```text
LAB_OWNER.ORDER_API (package)
LAB_OWNER.LAB_ORDERS (table)
LAB_API            (application user)
```

A package created by `LAB_OWNER` belongs to the `LAB_OWNER` schema. For `LAB_API` to call the package, it typically needs `EXECUTE`:

```sql
-- Granted by the owner in LAB_OWNER's session:
GRANT EXECUTE ON order_api TO lab_api;
```

**The `EXECUTE` privilege does not transfer package ownership.** The caller and the owner remain two distinct entities.

### 9.2. Definer's rights vs. invoker's rights

Oracle supports two execution privilege models for stored PL/SQL:

| Model | Common clause | Primary meaning |
|---|---|---|
| **Definer's rights** | `AUTHID DEFINER` (typically the default for stored PL/SQL) | Code runs under the privilege context of the program owner, with rules restricting roles and name resolution |
| **Invoker's rights** | `AUTHID CURRENT_USER` | Code runs under the privilege context of the caller where applicable, following Oracle's invoker-rights rules |

Example definition:

```sql
CREATE OR REPLACE PROCEDURE lab_owner.show_order_count
AUTHID DEFINER
AS
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM lab_owner.lab_orders;

    DBMS_OUTPUT.PUT_LINE('Order count: ' || v_count);
END;
/
```

This is an illustrative example and requires `CREATE PROCEDURE`, the existence of `LAB_OWNER.LAB_ORDERS`, and matching conditions. A caller wanting to run the procedure may need:

```sql
GRANT EXECUTE ON lab_owner.show_order_count TO lab_api;
```

With **definer's rights**, an account that only has `EXECUTE` on the program unit can execute the encapsulated operations under the owner's privileges without needing direct grants on all underlying tables. This is useful for exposing a controlled API. However, the owner must design the procedure safely, validate inputs, and avoid exposing data operations beyond business intent.

With **invoker's rights**, privilege checks and execution context differ; do not simply change `AUTHID` and assume the program will continue working identically. In Oracle versions with `INHERIT PRIVILEGES` policies, related privilege inheritance rules must also be considered where applicable.

### 9.3. Why a role-based grant can suffice for `SELECT` but fail to compile a procedure

Suppose `LAB_DEV` is granted the role `APP_READ_ROLE`, which has read privilege on `LAB_OWNER.LAB_ORDERS`. The developer runs:

```sql
SELECT COUNT(*) FROM lab_owner.lab_orders;
```

and the query succeeds in a SQL worksheet. However, when creating a **definer's rights** stored procedure referencing that table, Oracle normally requires the table privilege to be **granted directly to the procedure's owner** to compile and operate consistently under stored object privilege rules.

A direct grant may be required, such as:

```sql
-- In the table owner's session:
GRANT SELECT ON lab_orders TO lab_dev;
```

This is the classic scenario of "direct SQL runs fine, but procedure compilation fails." You must check the privileges granted directly to the **user owning the program unit**, not just roles enabled in the development session.

## 10. Designing accounts for Java/Spring applications

For applications connecting to Oracle via JDBC, the account used in the connection pool generally **does not need to own all the tables**.

### 10.1. Separating owner and runtime user

Reference architecture:

```text
                    CI/CD / DBA / Migration
                              |
                         LAB_OWNER
                              |
                   Creates/alters tables, indexes,
                   views, packages per process
                              |
                 Schema LAB_OWNER
                       /           \
           Limited GRANT          GRANT SELECT
                    /                  \
              LAB_API               LAB_REPORT
                |                       |
           Java Backend          Reporting Tasks
```

In this model:

- **Schema owner** is used by controlled schema-change processes.
- **Runtime account** such as `LAB_API` only holds privileges necessary for application operation, such as `SELECT`, `INSERT`, `UPDATE` on designated tables or `EXECUTE` on API packages.
- **Reporting account** such as `LAB_REPORT` receives read-only privileges within an appropriate scope.
- Passwords/credentials are managed centrally and never committed to repositories or stored in plaintext in distributable configuration files.

This model limits the blast radius of application bugs. For example, a SQL bug running under `LAB_API` should never have pre-existing `DROP USER` or `CREATE ANY TABLE` privileges.

### 10.2. How should the application reference tables?

If the backend connects as `LAB_API` while the table belongs to `LAB_OWNER`, SQL should typically use:

```sql
SELECT order_id, total_amount
FROM lab_owner.lab_orders
WHERE order_id = :order_id;
```

In standard JDBC, an equivalent example typically uses `?` placeholders:

```java
String sql = """
    SELECT order_id, total_amount
    FROM lab_owner.lab_orders
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Map result row to an application object.
        }
    }
}
```

The Java snippet above uses a text block (Java 15+) and assumes an existing `Connection`, `orderId`, and appropriate JDBC imports. It illustrates querying a table in **another schema** and binding values, not a complete application.

If you choose to use `ALTER SESSION SET CURRENT_SCHEMA = LAB_OWNER`, consider how it interacts with the connection pool: connections can be reused across requests. Modified session state must be set and reset cleanly to prevent unrelated queries from accidentally using the wrong default schema.

### 10.3. Does a migration tool need to log in as the owner?

When a tool such as Flyway or Liquibase creates tables, views, or packages, you must determine **which account runs the DDL**, the **target schema**, and the **effective privileges**. You can use a controlled owner account or a deployment account with appropriate DDL privileges per policy. Do not grant broad `ANY` privileges to runtime accounts just to make migrations work.

Schema names should remain consistent across scripts; grants to runtime users and roles should be managed as part of structural changes. If you deploy objects to a new schema, old grants and dependencies do not automatically transfer to that schema.

## 11. Multitenant: does a user/schema live in CDB or PDB?

Oracle Database deployed with the **CDB/PDB** architecture introduces an additional scope distinction:

- **CDB (container database):** contains the root container and pluggable databases (PDBs), along with corresponding structural components.
- **PDB:** a logical database environment that can hold users/schemas, tables, and application objects.
- **Local user:** a user created within the scope of a single PDB under Oracle's supported model.
- **Common user:** a user whose identity/privilege scope spans the CDB according to common user rules; naming and creation follow version/configuration rules, commonly involving the `C##` prefix in standard configurations.

For example, two PDBs can both have a user/schema named `APP_OWNER` with **two completely independent datasets**:

```text
CDB
  |
  +-- PDB_SALES
  |     +-- APP_OWNER.ORDERS
  |
  +-- PDB_TEST
        +-- APP_OWNER.ORDERS
```

Sharing the name `APP_OWNER` does not mean those two tables are the same object or that a user in one PDB can automatically read tables in the other PDB. When checking owners in `ALL_OBJECTS` or `DBA_OBJECTS`, you must know **which container/PDB you are connected to**. Administrative privileges and `CDB_...` views also have their own requirements and scope.

For practice environments, connect to the service of the correct PDB before creating users or running DDL. The SQL examples in this lesson are designed for standard practice PDBs/schemas, not for guiding common user creation in the CDB root.

## 12. Common error scenarios

| Symptom | Possible cause | What to check |
|---|---|---|
| `ORA-00942: table or view does not exist` when running `SELECT` from another schema | Wrong schema/table name, object does not exist in the connected PDB, or user lacks access privilege | `CURRENT_SCHEMA`, fully qualified name, `SELECT` privilege, synonyms, PDB |
| `ORA-01031: insufficient privileges` during DDL or operations | Missing appropriate system/object privilege | Direct privileges, roles, `ANY` scope, owner and execution context |
| `ORA-01950: no privileges on tablespace ...` when creating/writing objects | User lacks quota or tablespace usage conditions | Quota, default tablespace, segment creation scope |
| `CREATE TABLE` succeeds under user A, but user B cannot see it | B lacks privileges or is querying the wrong schema/PDB | `ALL_OBJECTS`, `GRANT`, B's connection |
| `SELECT` works in worksheet, but procedure fails to compile | Privilege was granted only via a role, not directly to the program owner | `USER_ERRORS`, `USER_TAB_PRIVS_RECD`, direct privilege grants |
| `ALTER SESSION SET CURRENT_SCHEMA` completed, yet table still cannot be read | Changing the default schema **does not grant privileges** | `SESSION_USER`, `CURRENT_SCHEMA`, object grants |
| `SELECT * FROM ORDERS` returns data from an unexpected table | Name resolution matched an object/synonym in the current schema | Fully qualified `OWNER.OBJECT`, synonyms, session state |
| Synonym created, yet `SELECT` still fails | A synonym is only an alias and grants no object privileges | Privileges on the underlying target object |
| Same schema name in two environments yields different results | Connected to different PDBs/databases | Service name, `SYS_CONTEXT`, PDB metadata |
| Direct privilege `REVOKE`d, yet user can still read | User holds privileges through a role or another system privilege | Grant list, roles, effective session privileges |

### Quick troubleshooting checklist when a table cannot be accessed

1. **Identify the session identity and current schema**:

   ```sql
   SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
          SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
   FROM dual;
   ```

2. **Explicitly qualify the object with its owner**, e.g., `LAB_OWNER.LAB_ORDERS`, then verify the name and PDB using an account permitted to view metadata.
3. **Inspect effective direct privileges and roles** for the operation being performed.
4. **Distinguish plain SQL from stored PL/SQL**: role-based privilege evaluation can differ.
5. **Request only the required privileges**, such as `SELECT` on the specific table or `EXECUTE` on the specific package, instead of granting `ANY` privileges as a "quick fix."

## 13. Key true and false statements to remember

| Statement | Verdict | Explanation |
|---|---|---|
| "In Oracle, a schema has the same name as its database user." | True | A schema is tied to its corresponding user within the database/PDB scope |
| "A user with `CREATE SESSION` can read all tables." | False | Session creation privilege differs from object privileges |
| "A user granted `SELECT` on a table becomes the owner of that table." | False | Ownership does not change when privileges are granted |
| "A schema is the same thing as a tablespace." | False | A schema organizes objects by owner; a tablespace organizes storage |
| "One schema can contain multiple tables, views, indexes, and procedures." | True | These are schema objects |
| "A tablespace can only hold objects from one schema." | False | Multiple schemas can share the same tablespace |
| "Creating a synonym automatically grants read privilege on the target table." | False | A synonym is an alias; privileges are needed on the target object |
| "When `CURRENT_SCHEMA` changes, `SESSION_USER` changes with it." | False | These are two separate attributes |
| "When `LAB_API` inserts a row into `LAB_OWNER.LAB_ORDERS`, the owner becomes `LAB_API`." | False | The table's owner remains `LAB_OWNER` |
| "A procedure may require a direct grant even though worksheet SQL works via a role." | True in many definer's rights cases | Depends on privilege evaluation during program compilation/execution |
| "A user gains permission to `DROP` any schema simply by adding the schema prefix." | False | Fully qualified syntax does not replace privileges |
| "An object's owner can be viewed via `ALL_OBJECTS.OWNER` when the object is visible." | True | Metadata returns the owner within the view's scope and access rights |
| "Having the same name `APP_OWNER` in two PDBs guarantees they are the same single table." | False | Each PDB has its own data/user/schema scope under multitenant architecture |

## 14. Self-check exercises

### Question 1

A database contains the table `HR.EMPLOYEES`. User `REPORT` is granted `SELECT ON HR.EMPLOYEES`. Who is the owner?

**Answer:** `HR`. `REPORT` has read privilege, not ownership of the table.

### Question 2

`REPORT` runs:

```sql
ALTER SESSION SET CURRENT_SCHEMA = HR;
SELECT * FROM employees;
```

Does the first statement turn user `REPORT` into `HR`?

**Answer:** No. The session identity remains `REPORT`; only the default schema used to resolve unqualified names changes to `HR`. The `SELECT` only succeeds if the user has privileges on the table.

### Question 3

A user has `CREATE TABLE` but is not allowed to allocate space in their default tablespace. Is having `CREATE TABLE` enough to create a table with a segment in that tablespace?

**Answer:** Not necessarily. Relevant storage/quota requirements and tablespace state must also be satisfied.

### Question 4

User `REPORT` creates a private synonym `ORDERS` pointing to `SALES.ORDERS`. Which two objects exist, and who owns them?

**Answer:** `REPORT.ORDERS` is a synonym owned by `REPORT`; `SALES.ORDERS` remains a table owned by `SALES`. A synonym neither transfers ownership nor grants read privileges.

### Question 5

Package `APP.PKG_ORDER` is owned by `APP`, and user `API` has `EXECUTE` privilege on the package. Can `API` automatically create or modify the package code?

**Answer:** No. `EXECUTE` only allows invoking the program within privilege limits; privileges to alter/create objects and ownership are separate concepts.

### Question 6

You inspect `USER_OBJECTS` for `LAB_API` and do not see `LAB_OWNER.LAB_ORDERS`, yet `SELECT * FROM LAB_OWNER.LAB_ORDERS` runs successfully. Is there a contradiction?

**Answer:** No. `USER_OBJECTS` only lists objects belonging to **schema `LAB_API`**; the table belongs to `LAB_OWNER`. Access visibility can be checked via `ALL_OBJECTS`, `ALL_TABLES`, and the relevant grant metadata.

### Question 7

A developer is granted `SELECT` on another owner's table via a role; direct SQL succeeds, but a definer's rights procedure fails to compile due to insufficient privileges. What should you check first?

**Answer:** Check **direct grants to the schema owning the procedure**, because privileges from roles may not be used during compilation/execution under stored PL/SQL privilege rules.

### Question 8

An application needs to read and insert orders into `LAB_OWNER.LAB_ORDERS`. Which privilege is more appropriate for `LAB_API`: `SELECT, INSERT ON LAB_OWNER.LAB_ORDERS` or `SELECT ANY TABLE`?

**Answer:** Specific object privileges `SELECT, INSERT` on the required table enforce the principle of least privilege and limit blast radius if the application encounters a bug.

## 15. Conclusion

In Oracle Database, a **user** is the security identity used to log in and receive privileges; a **schema** is the namespace and collection of objects tied to that user; and the **owner** identifies which schema owns each object. These three concepts are closely related but must be distinguished from **privileges**, **roles**, **tablespaces**, and **sessions**.

Whenever you see `SALES.ORDERS`, read `SALES` as the **schema/owner**, while whether another account can `SELECT`, `INSERT`, `UPDATE`, or `EXECUTE` depends on granted privileges. `GRANT` opens usage rights without changing ownership; `CURRENT_SCHEMA` assists with unqualified name resolution without changing the user or creating new privileges; and synonyms create aliases without turning the target object into an object owned by the synonym creator.

Understanding this model accurately helps you write clear SQL, query metadata properly via `USER_`/`ALL_`/`DBA_` views, design least-privilege access for Java backends, and separate **data ownership, deployment, and usage** into manageable responsibilities.
