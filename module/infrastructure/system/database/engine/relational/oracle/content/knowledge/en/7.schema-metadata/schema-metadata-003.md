# Name Resolution by Schema, CURRENT_SCHEMA, and Synonyms

When an application runs `SELECT * FROM orders`, Oracle must answer a question before reading data: **which object is `ORDERS`?** In a database with multiple schemas, `APP_OWNER.ORDERS`, `REPORT_OWNER.ORDERS`, or a synonym named `ORDERS` pointing to a table in another schema might all exist. Two sessions executing the exact same SQL text can sometimes access two different objects because their **name resolution context** differs.

This lesson explains how Oracle resolves schema-unqualified names, how `CURRENT_SCHEMA` affects the search scope, the roles of **private synonyms** and **public synonyms**, how to verify target objects via metadata, and why **finding a name does not mean having access privileges**. DDL operations in the examples are only for an authorized practice schema.

## 1. Three ways to reference an object

Suppose a PDB has a schema `APP_OWNER` that owns the `ORDERS` table, and user `REPORT_USER` needs to read this table. Three ways of writing the query can lead to the same table:

~~~sql
-- 1. Explicitly specify the owner: no default schema needed.
SELECT order_id, amount FROM app_owner.orders;

-- 2. After the session changes CURRENT_SCHEMA to APP_OWNER:
SELECT order_id, amount FROM orders;

-- 3. If REPORT_USER has a synonym APP_ORDERS pointing to APP_OWNER.ORDERS:
SELECT order_id, amount FROM app_orders;
~~~

The prerequisite is that each approach must be configured properly and the user must have **`SELECT` privilege on the target table**. All three yield the same result in this simple example, yet carry different meanings:

| Reference style | What information does Oracle use to find the object? | What scope does it affect? |
|---|---|---|
| `APP_OWNER.ORDERS` | Schema name and object name written explicitly | Only that specific reference in that SQL statement |
| `ORDERS` | `CURRENT_SCHEMA` and synonym lookup rules | All unqualified names in matching SQL statements |
| `APP_ORDERS` | Synonym named `APP_ORDERS`, then the object it points to | An alias usable across multiple SQL statements |

None of these approaches grants read/write privileges by itself. None of them switches the session to another PDB.

~~~mermaid
flowchart TD
    A["SQL: SELECT ... FROM orders"] --> B["Which PDB is the session in?"]
    B --> C["What is CURRENT_SCHEMA?"]
    C --> D["Search for matching object or private synonym"]
    D --> E["If not matched, check public synonyms"]
    E --> F["Identify target object"]
    F --> G{"Has privileges and valid object?"}
    G -->|Yes| H["Parse/execute SQL"]
    G -->|No| I["Report appropriate error"]
~~~

This diagram illustrates the mental flow for **simple object names** (tables, views, and many common schema objects). Oracle also has dedicated rules for packages, types, PL/SQL elements, database links, quoted identifiers, and SQL inside stored objects. Do not treat this diagram as the complete resolution grammar for every name in Oracle.

## 2. Schema, user, and container are three concepts to keep separate

### 2.1 What is a schema?

A **schema** is a namespace containing database objects belonging to a user, such as tables, views, sequences, packages, indexes, and synonyms. In Oracle, a schema is tied to a database user; the user/schema name is typically the starting point for identifying an object.

Example:

~~~text
PDB SALES_PDB
├── APP_OWNER
│   ├── ORDERS       (table)
│   ├── PRODUCTS     (table)
│   └── ORDER_API    (package)
├── REPORT_OWNER
│   └── ORDERS       (a different table)
└── REPORT_USER
    └── APP_ORDERS   (private synonym, if created)
~~~

`APP_OWNER.ORDERS` and `REPORT_OWNER.ORDERS` are two distinct fully qualified names. When you type `SELECT * FROM ORDERS` without specifying a schema, Oracle must use the **session context** to pick the right object.

### 2.2 Container/PDB defines the search boundary

In Oracle multitenant, multiple PDBs can each contain a schema named `APP_OWNER`, with each schema holding its own tables. `APP_OWNER.ORDERS` in `SALES_PDB` is not by default the same object as `APP_OWNER.ORDERS` in `REPORT_PDB`.

First, identify the container you are connected to:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID') AS container_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`ALTER SESSION SET CURRENT_SCHEMA` only changes the **default schema within the current container**; it **does not change the PDB**. To query another PDB normally, the application must connect to **that PDB's service** using an appropriate account. Switching containers within a session is a separate administrative feature with specific conditions and the `SET CONTAINER` privilege; do not use `CURRENT_SCHEMA` as a substitute.

### 2.3 A service name is also not a schema

Example JDBC connection string:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/sales_service
spring.datasource.username=report_user
~~~

`sales_service` routes the connection, `report_user` is the database login user, and the default `CURRENT_SCHEMA` usually matches the login user's schema when the session is initialized. You can use `SYS_CONTEXT` to verify all three; do not infer the schema name solely from the service or URL.

## 3. How does Oracle resolve names without a schema prefix?

Consider a direct SQL statement in a session:

~~~sql
SELECT order_id FROM orders;
~~~

For a simple reference to a table or view, a useful mental model is:

1. **In the current schema:** Oracle checks for a schema object named `ORDERS` matching the SQL statement's context.
2. **Private synonym:** if no direct object is found, Oracle checks for a matching private synonym within the name resolution scope.
3. **Public synonym:** if no higher-priority object or private synonym exists, Oracle may consider a public synonym named `ORDERS`.
4. **Target object and privileges:** once the target is identified, Oracle checks the object, usage type, and required privileges; if not satisfied, the statement fails.

This is a precedence model for **common unqualified names**. Special namespaces and reference forms can have different rules, such as `package.procedure` or `schema.object`; when diagnosing, inspect the **actual SQL** rather than applying this order to every case.

### 3.1 Example of a local name shadowing a public synonym

Suppose the database has a public synonym `ORDERS` pointing to `APP_OWNER.ORDERS`. If `REPORT_OWNER` already owns a table `REPORT_OWNER.ORDERS` and the session sets `CURRENT_SCHEMA = REPORT_OWNER`:

~~~sql
SELECT * FROM orders;
~~~

then the direct object name in the active schema takes precedence, so the SQL statement references **`REPORT_OWNER.ORDERS`**, rather than automatically going through the public synonym.

This explains why a SQL statement that used to work via a public synonym can change behavior or fail after an identically named object is created in the schema. **A public synonym does not force every session to use the same object**, because a more specific local name has higher precedence during resolution.

### 3.2 Private synonyms and objects sharing a namespace

Private synonyms reside inside a schema. Tables, views, sequences, and private synonyms share a common schema namespace in typical cases; you cannot simply create a private synonym named `ORDERS` if that schema already has a table named `ORDERS`. When you need an alias to avoid collisions, use a clear name like `APP_ORDERS` or `ORDER_READ_API`.

Conversely, public synonyms reside in the public namespace; a local object can shadow a public synonym. Therefore, when managing a multi-team system, avoid creating overly generic public synonyms like `DATA`, `ORDERS`, or `USER`.

### 3.3 A name with a dot is not always a table

Example:

~~~sql
SELECT * FROM app_owner.orders;
~~~

Here `APP_OWNER.ORDERS` is a reference qualified by schema and object; if `APP_OWNER` contains a **private synonym** named `ORDERS`, the qualified name may resolve to that synonym depending on rules and object types. To prove which actual table is targeted, query `ALL_OBJECTS` and `ALL_SYNONYMS` rather than guessing from the dotted syntax.

Expressions such as `package_name.function_name` or `schema.package_name.procedure_name` follow resolution rules tied to packages, PL/SQL components, and other namespaces; a dot does not always carry a single meaning.

## 4. How do SESSION_USER, CURRENT_USER, CURRENT_SCHEMA, and USER differ?

One common source of confusion is assuming that "whichever user you log in as, every object name always belongs to that schema."

Run:

~~~sql
SELECT USER AS user_expression,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

| Value | Interpretation in a normal direct SQL session |
|---|---|
| `USER` / `SESSION_USER` | The user of the login session |
| `CURRENT_USER` | The user context used for applicable privilege/execution checks; can differ in stored PL/SQL under definer's/invoker's rights models |
| `CURRENT_SCHEMA` | The schema Oracle uses by default to resolve many unqualified object names |

Immediately after a normal user login, these values usually match. However, you can change **`CURRENT_SCHEMA` without changing the login user**.

### 4.1 Changing CURRENT_SCHEMA within a session

Log in as `REPORT_USER` with read privilege on `APP_OWNER.ORDERS` and run:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS schema_before
FROM dual;

ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS schema_after
FROM dual;
~~~

Expected sample output:

~~~text
Before: SESSION_USER=REPORT_USER, CURRENT_SCHEMA=REPORT_USER
After:  SESSION_USER=REPORT_USER, CURRENT_SCHEMA=APP_OWNER
~~~

Afterward, unqualified names can be resolved in `APP_OWNER`:

~~~sql
SELECT order_id, amount
FROM orders;
~~~

`ALTER SESSION SET CURRENT_SCHEMA` **does not re-authenticate**, **does not change the user**, **does not grant new privileges**, **does not change the PDB**, and **does not move objects from one schema to another**.

If `REPORT_USER` does not yet have `SELECT` privilege on `APP_OWNER.ORDERS`, resolving the right name still will not allow the `SELECT` statement to succeed.

When you want to restore the practice session to its original schema:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;

SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 4.2 CURRENT_SCHEMA vs. ALTER SESSION SET CONTAINER

~~~sql
-- Change default schema, remaining in the same container:
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;
~~~

The command above is fundamentally different from:

~~~sql
-- Only for a common user with sufficient privileges and matching session/target:
ALTER SESSION SET CONTAINER = SALES_PDB;
~~~

In the second example, Oracle switches the **session's container** when conditions are met. `CURRENT_SCHEMA` cannot be used as a shortcut to "query across PDBs."

### 4.3 CURRENT_SCHEMA is not a privilege to create or modify objects

When `CURRENT_SCHEMA` changes, unqualified SQL or DDL statements may be interpreted against the new schema. Therefore, be extra careful with commands such as `CREATE TABLE`, `ALTER TABLE`, or grant operations: **explicitly specify the schema when working with multiple owners**, verify `OWNER` afterward, and do not assume changing the schema grants `CREATE ANY TABLE` or other administrative privileges.

`ALTER SESSION SET CURRENT_SCHEMA` normally adjusts only session context and can be run without special administrative privileges. Privileges on the **actual object** remain an independent check.

## 5. End-to-end example with two accounts

The following statements assume you have a **practice PDB** and two users prepared by an administrator:

- `APP_OWNER` owns the business table and has privileges to create tables in its own schema.
- `REPORT_USER` has privileges to create private synonyms in its own schema for the synonym exercises; it does not have read privilege on `APP_OWNER.ORDERS` until granted.

**Do not run these commands in a production schema.** They are sample data creation and privilege-granting operations for this lesson.

### 5.1 In the APP_OWNER connection: create table and grant read access

~~~sql
-- Run while logged in as APP_OWNER, inside the practice PDB.
CREATE TABLE orders (
    order_id NUMBER(10) PRIMARY KEY,
    amount   NUMBER(12,2) NOT NULL
);

INSERT INTO orders (order_id, amount) VALUES (101, 125000);
INSERT INTO orders (order_id, amount) VALUES (102, 84000);
COMMIT;

-- APP_OWNER is the table owner and grants only the required SELECT privilege.
GRANT SELECT ON orders TO report_user;
~~~

Only after the grant can `REPORT_USER` read the table according to the granted privilege. To perform `INSERT` or `UPDATE` from `REPORT_USER`, corresponding privileges are needed; **`SELECT` does not imply write privileges**.

### 5.2 In the REPORT_USER connection: fully qualified names are always explicit

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;

SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

The second query uses a fully qualified name, so it does not depend on whether `CURRENT_SCHEMA` matches `APP_OWNER`, within the connected PDB and granted `SELECT` privilege.

Assuming `REPORT_USER` has no table/view/synonym named `ORDERS`, the statement:

~~~sql
SELECT order_id, amount
FROM orders;
~~~

can fail with `ORA-00942`. This error **does not mean** `APP_OWNER.ORDERS` does not exist; the unqualified name either did not resolve to the right object or privileges were insufficient.

### 5.3 Change CURRENT_SCHEMA and use the short name

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT order_id, amount
FROM orders
ORDER BY order_id;

SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

The query returns the same data as calling `APP_OWNER.ORDERS`, yet the login user remains `REPORT_USER`. This illustrates the difference between the **default name-resolution schema** and the **object owner**.

Before trying a private synonym in the `REPORT_USER` schema, restore:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;
~~~

### 5.4 Create a private synonym in REPORT_USER

~~~sql
-- Run while logged in as REPORT_USER, CURRENT_SCHEMA=REPORT_USER.
-- Requires appropriate CREATE SYNONYM privilege.
CREATE SYNONYM app_orders FOR app_owner.orders;

SELECT order_id, amount
FROM app_orders
ORDER BY order_id;
~~~

`APP_ORDERS` is an **alias**. It does not store a copy of the two rows in `ORDERS` and is not a view duplicating data. When using this alias, Oracle resolves to `APP_OWNER.ORDERS` via synonym metadata, then applies actual privilege checks.

To verify the real object, you can still query:

~~~sql
SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

If `APP_OWNER` inserts new rows and commits, reading through the synonym gives `REPORT_USER` access to the target table under Oracle's read consistency rules; a synonym has no separate dataset to "sync."

### 5.5 If you lack the CREATE SYNONYM privilege

Creating the alias may fail due to missing DDL privileges. You can still complete the name-resolution portion of the lesson using `APP_OWNER.ORDERS` and `ALTER SESSION SET CURRENT_SCHEMA`; for the private synonym section, ask an administrator to grant the appropriate privilege **in the practice environment** or provide an existing synonym. You do not need `CREATE PUBLIC SYNONYM` or broad administrative privileges just to run this example.

## 6. Synonym: an alias, not a table, view, or GRANT

Oracle supports synonyms to provide an alternate reference name for another object. A synonym can point to a table, view, sequence, package, procedure, function, type, and other supported object types; in some configurations, a synonym can also reference an object over a database link.

~~~mermaid
flowchart LR
    A["REPORT_USER runs SELECT FROM app_orders"] --> B["Private synonym REPORT_USER.APP_ORDERS"]
    B --> C["Table APP_OWNER.ORDERS"]
    D["SELECT privilege on APP_OWNER.ORDERS"] --> C
    C --> E["Actual data in ORDERS"]
~~~

Key points:

- **A synonym is alias metadata.** It creates no data copy and no separate index for the alias.
- **A synonym grants no privileges.** The user needs privileges to operate on the target object, even if the synonym name resolves successfully.
- **A synonym can become unusable** if the target object is renamed/dropped, privileges are revoked, or the synonym chain becomes invalid.
- **A synonym does not change the owning schema.** The data remains in `APP_OWNER.ORDERS`; the alias `REPORT_USER.APP_ORDERS` resides in `REPORT_USER`'s schema.
- **A synonym does not cross PDB boundaries.** It is evaluated within the relevant container and access context, not as a shortcut to fetch tables from another PDB.

### 6.1 Private synonym

Create in the practice user's schema:

~~~sql
CREATE SYNONYM order_reader FOR app_owner.orders;
~~~

Query:

~~~sql
SELECT * FROM order_reader;
~~~

Other users do not automatically see `REPORT_USER`'s private synonym when typing the same short name in their own schemas. Where privileges and object types permit, a private synonym can also be referenced using its qualified name `REPORT_USER.ORDER_READER`, though privileges on the target object are still checked.

Creating a private synonym in **another schema** requires higher privileges (such as `CREATE ANY SYNONYM`) and must be carefully governed; regular users should only create aliases in schemas they are authorized to own.

### 6.2 Public synonym

A **public synonym** resides in the public namespace of the database/container within its scope. It enables sessions without a higher-priority object or private synonym to resolve the same name, such as Oracle-supplied or DBA-configured public synonyms.

Syntax shown **for administrators**, not to be run in a regular user lab:

~~~sql
-- DDL example for authorized administrators only:
CREATE PUBLIC SYNONYM app_orders_global FOR app_owner.orders;
~~~

This command requires `CREATE PUBLIC SYNONYM` and modifies the shared namespace. A public synonym does not automatically grant `SELECT` on `APP_OWNER.ORDERS` to all users; privileges must still be granted **on the target object** according to requirements and policy.

| Attribute | Private synonym | Public synonym |
|---|---|---|
| Where the alias name lives | Specific schema | `PUBLIC` namespace within database/container scope |
| Typical creator | Schema owner with `CREATE SYNONYM` | DBA/user with `CREATE PUBLIC SYNONYM` |
| Visibility | Resolves within matching schema context and privileges | Can be found when no higher-priority name exists |
| Copies the table? | No | No |
| Grants privileges on target table? | No | No |
| Generic naming risk | Primarily within that schema | Higher, as it can collide with names across multiple applications |

### 6.3 Synonym pointing to another synonym

A synonym can point to another name; overly long chains or loops make tracing difficult, and a **circular synonym chain** can trigger `ORA-01775: looping chain of synonyms`. When investigating, trace `TABLE_OWNER`, `TABLE_NAME`, and `DB_LINK` rather than looking only at the first alias.

Example of chained metadata (illustrative only):

~~~text
REPORT_USER.ORDERS_API
  -> APP_OWNER.ORDERS

REPORT_USER.ORDERS_OLD
  -> REPORT_USER.ORDERS_API
  -> APP_OWNER.ORDERS
~~~

In new designs, simple aliases and clear names are generally easier to manage than multi-hop synonym chains.

### 6.4 Synonym pointing through a database link

If the system already has a database link configured, a synonym can reference a remote object, as shown in this **syntax example**:

~~~sql
-- Syntax illustration; SALES_REMOTE_LINK must exist and be authorized.
CREATE SYNONYM remote_orders FOR app_owner.orders@SALES_REMOTE_LINK;
~~~

In that case, querying also depends on the database link, connectivity, user, and privileges on the remote database. `DB_LINK` in synonym metadata indicates the remote reference path; do not assume the target resides in the same local PDB/datafiles. This example does not require creating a database link or opening connections to another system.

## 7. Finding the exact object via metadata

When you suspect a SQL statement is going through a synonym or an unexpected current schema, inspect **session context**, **homonymous objects**, **synonyms**, and **privileges**. Each group is exposed by dedicated data dictionary views.

### 7.1 Verify the session first

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Suppose the output is:

~~~text
SESSION_USER  CURRENT_USER  CURRENT_SCHEMA  CON_NAME   SERVICE_NAME
------------ ------------- --------------- ---------- --------------
REPORT_USER   REPORT_USER   APP_OWNER       SALES_PDB  sales_service
~~~

Key takeaway: the logged-in user is still `REPORT_USER`, yet unqualified SQL can resolve inside `APP_OWNER`. When diagnosing, do not read only `SESSION_USER` and assume every object belongs to that schema.

### 7.2 Find objects with the same name

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'ORDERS'
ORDER BY owner, object_type;
~~~

Example:

~~~text
OWNER         OBJECT_NAME  OBJECT_TYPE  STATUS
------------  -----------  -----------  -------
APP_OWNER     ORDERS       TABLE        VALID
REPORT_OWNER  ORDERS       TABLE        VALID
~~~

`ALL_OBJECTS` shows **objects observable by the user according to metadata access/privileges**. It does not necessarily list every object in the database, especially if the account has limited privileges. For authorized administrative accounts, `DBA_OBJECTS` widens the scope per privileges. Since unquoted identifiers are normally normalized to uppercase by Oracle, examples search for `'ORDERS'` rather than `'orders'`.

### 7.3 Find private/public synonyms

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('ORDERS', 'APP_ORDERS', 'APP_ORDERS_GLOBAL')
ORDER BY owner, synonym_name;
~~~

| Column | What does it identify? |
|---|---|
| `OWNER` | Synonym owner, e.g., `REPORT_USER` or `PUBLIC` |
| `SYNONYM_NAME` | Alias that SQL can reference |
| `TABLE_OWNER` | Schema/owner of the object referenced by the synonym |
| `TABLE_NAME` | Target object name declared in the synonym |
| `DB_LINK` | Database link name if the alias points to a remote object; usually `NULL` if local |

`ALL_SYNONYMS` reflects synonyms observable by the user within the view's scope, including applicable public synonyms. `USER_SYNONYMS` focuses on synonyms owned by the user; `DBA_SYNONYMS` is only for accounts with corresponding full-view privileges.

A listed synonym **does not guarantee the target object still exists, has the expected type, or that the user has privileges to use it**. Synonym metadata only shows **the name the alias declares as its target**.

### 7.4 View privileges on the object

~~~sql
SELECT grantor,
       grantee,
       owner,
       table_name,
       privilege
FROM all_tab_privs
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

`ALL_TAB_PRIVS` lists object privileges observable by the user. If the table owner granted `SELECT` directly, the corresponding grant can appear within the query scope. However, privileges can come from roles, `PUBLIC`, or other administrative mechanisms; **a missing row does not by itself prove no privilege path exists**. For stored PL/SQL, role-based privileges also follow special rules.

There is no `GRANT SELECT ON app_orders ...` to treat a synonym as equivalent to the data-bearing table: **grant privileges on the target object** (`APP_OWNER.ORDERS`) as needed.

### 7.5 USER_OBJECTS does not follow CURRENT_SCHEMA

A frequent misconception: after setting `CURRENT_SCHEMA = APP_OWNER`, querying `USER_OBJECTS` and expecting it to display all objects in `APP_OWNER`.

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT object_name, object_type
FROM user_objects
WHERE object_name = 'ORDERS';
~~~

`USER_OBJECTS` describes objects belonging to the **user** per the view's context; it does not automatically become "objects of whichever schema was set in `CURRENT_SCHEMA`" via `ALTER SESSION`. To check `APP_OWNER.ORDERS` observable by the user, query `ALL_OBJECTS` with `OWNER = 'APP_OWNER'`; with administrative privileges, `DBA_OBJECTS` can be used. After the example, restore `CURRENT_SCHEMA` if needed.

## 8. Unqualified names, qualified names, and double quotes

### 8.1 Unquoted names are normally normalized to uppercase

Oracle processes most unquoted identifiers in uppercase:

~~~sql
SELECT * FROM app_owner.orders;
SELECT * FROM APP_OWNER.ORDERS;
~~~

Both statements use unquoted identifiers and therefore reference the same normalized name (when the object exists and privileges are sufficient). That is why in `ALL_OBJECTS`, you usually see `OBJECT_NAME = 'ORDERS'`.

### 8.2 Quoted names preserve exact casing

If a schema owner creates:

~~~sql
-- In a test schema only
CREATE TABLE "OrderItems" (
    "OrderId" NUMBER PRIMARY KEY
);
~~~

then normal queries must preserve the exact spelling:

~~~sql
SELECT "OrderId"
FROM "OrderItems";
~~~

`SELECT OrderId FROM OrderItems` causes Oracle to interpret the unquoted identifiers as `ORDERID` and `ORDERITEMS`; it may fail to find the created `"OrderItems"` object. Synonyms and schema names are also subject to corresponding quoting/case rules. Using quoted identifiers should have a clear justification because they increase typos and discrepancies across tools/ORMs.

### 8.3 Fully qualified names keep the path clear

When reading logs or debugging an API, the statement:

~~~sql
SELECT order_id FROM app_owner.orders WHERE order_id = :id;
~~~

lets the reader immediately see which schema the author intended to use within the connected PDB. If the object at `APP_OWNER.ORDERS` is a synonym rather than a table, metadata still must be checked to determine the final target. Fully qualified names reduce dependence on mid-session `CURRENT_SCHEMA` changes, though they do not fix the wrong service/PDB or missing privileges.

## 9. Impact in Java applications, JDBC, and connection pools

In a Java or Spring application, a repository might execute SQL like:

~~~java
String sql = "SELECT order_id, amount FROM orders WHERE order_id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 101L);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Process returned record.
        }
    }
}
~~~

Assume the application has the proper JDBC imports and `Connection connection` is properly initialized. The `?` binds the value of `order_id`, while the name `orders` in the SQL still has to be **resolved by Oracle to a specific object**.

If the application uses a connection pool, each physical connection maintains its own session state. A request calling:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_OWNER;
~~~

and returning the connection to the pool without resetting context can cause the next request executing `FROM orders` to hit a different schema than intended. The result can be the wrong table, insufficient privileges, or incorrect business figures.

### 9.1 More stable choices for applications

| Scenario | Easier-to-control organization |
|---|---|
| Application always accesses a single schema | Use explicit `APP_OWNER.ORDERS` names, or configure the default schema consistently across all connections |
| Application needs to abstract the owner name | Use managed private synonyms, tracking aliases and target object privileges |
| Application uses multiple schemas in the same PDB | Use schema-qualified names for critical objects, and manage privileges under least privilege |
| Application uses multiple PDBs | Configure connections/services per PDB; never use `CURRENT_SCHEMA` as a substitute for PDBs |
| Pool reuses sessions | Initialize/reset session state explicitly; never let an earlier request accidentally alter context for the next |
| ORM auto-generates SQL | Check schema naming configuration and actual generated SQL; verify owners via metadata on errors |

Do not concatenate user-supplied schema names directly into SQL:

~~~java
// Unsafe if schemaName comes directly from uncontrolled input:
String sql = "SELECT * FROM " + schemaName + ".orders";
~~~

A bind variable `?` only represents a **data value**, never an identifier such as a schema, table, or column name. If the system must select schemas dynamically, use a controlled allowlist and validate identifiers before constructing SQL; do not view `CURRENT_SCHEMA` as a substitute for access control.

### 9.2 SQL inside compiled PL/SQL has its own context

Do not assume that changing `CURRENT_SCHEMA` in a session redirects all static SQL inside an already compiled package/procedure to a same-named table in another schema. With **definer's rights** and **invoker's rights**, Oracle applies dedicated rules for execution context, privileges, and object resolution. Static SQL in stored objects may already be resolved and bound with dependencies at compile time, while dynamic SQL depends on its specific execution context.

When direct SQL returns the expected result but code inside a package cannot find the object, check **the package owner, execution rights mode, dependencies, and direct grants** alongside `CURRENT_SCHEMA`. Never try to fix stored PL/SQL errors merely by setting `CURRENT_SCHEMA` on the client.

## 10. Diagnosing errors when Oracle cannot find or use an object

| Error/symptom | Possible cause | How to investigate |
|---|---|---|
| `ORA-00942: table or view does not exist` | Name did not resolve to a valid object, wrong schema/PDB, or missing SELECT privilege | Check `CON_NAME`, `CURRENT_SCHEMA`, query `ALL_OBJECTS`, and inspect privileges |
| `ORA-01031: insufficient privileges` | User lacks privilege for the specific operation | Check object/system privileges against the actual SQL statement |
| `ORA-00980: synonym translation is no longer valid` | Synonym cannot resolve a valid target, target changed, or inaccessible via privileges/link | Query `ALL_SYNONYMS` then check target object, DB link, and privileges |
| `ORA-01775: looping chain of synonyms` | Synonym points in a loop through aliases | Trace the chain `OWNER.SYNONYM_NAME → TABLE_OWNER.TABLE_NAME` |
| `ORA-00955: name is already used by an existing object` | Alias/object name conflicts within the corresponding namespace | Check `ALL_OBJECTS` and `ALL_SYNONYMS` before creating |
| `PLS-00201: identifier must be declared` | PL/SQL cannot see the name or lacks appropriate privileges in compile/execution context | Check package owner, direct grants, AUTHID mode, and dependencies |
| Same `FROM orders` yet two users see different data | Different `CURRENT_SCHEMA`, different local objects or synonyms, or different PDBs | Compare `CON_NAME`, `CURRENT_SCHEMA`, `ALL_OBJECTS`, and `ALL_SYNONYMS` across both sessions |
| Changed `CURRENT_SCHEMA` yet `SELECT` still fails | No privilege on the target table/view | Request minimal grant on target object; do not treat schema switching as granting access |
| One schema sees an alias, another does not | Private synonym exists only within its schema and matching lookup scope | Check synonym `OWNER` and how the SQL statement references it |
| Public synonym works in one schema, fails or differs in another | A local object/private synonym has higher precedence than the public alias | Check for colliding names in the current schema |

**`ORA-00942` is not proof on its own that a table was dropped.** Oracle can return this message when a user lacks privileges on the object they are trying to access. Before recreating a table or renaming objects, verify container, schema, synonyms, and grants.

### 10.1 Inspection sequence when SELECT reports an error

~~~mermaid
flowchart TD
    A["SELECT FROM orders errors or returns wrong data"] --> B["Verify CON_NAME / service"]
    B --> C["Verify SESSION_USER and CURRENT_SCHEMA"]
    C --> D{"Using schema.object syntax?"}
    D -->|Yes| E["Look up object/synonym in the specified schema"]
    D -->|No| F["Look up object/private synonym in current schema"]
    F --> G["If needed, check public synonyms"]
    E --> H["Verify target object and privileges"]
    G --> H
    H --> I{"Valid object and privileges?"}
    I -->|Yes| J["Inspect actual SQL, schema, and data"]
    I -->|No| K["Correct the name, privileges, or synonym"]
~~~

This sequence prioritizes **non-mutating** observations. For large tables, you can test resolution and read access with a query that fetches zero rows:

~~~sql
SELECT *
FROM app_owner.orders
WHERE 1 = 0;
~~~

This query helps catch name or privilege errors without scanning rows to return results. It does not prove all DML operations or table performance are healthy, and it must still be executed in the right PDB.

## 11. Hands-on lab: demonstrating every mechanism with the same table

In a practice PDB where `APP_OWNER.ORDERS` already exists and `REPORT_USER` has been granted `SELECT`, perform the following steps:

**Step 1 — Record the initial state**

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name
FROM dual;
~~~

Note the connection's service as well. Confirm using the `REPORT_USER` account before continuing.

**Step 2 — Try the owner-qualified name**

~~~sql
SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

Explain why this statement does not require `CURRENT_SCHEMA = APP_OWNER`, yet still requires the user's `SELECT` privilege.

**Step 3 — Change current schema and try the short name**

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT order_id, amount FROM orders ORDER BY order_id;

SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Compare the login user before and after. If the table output looks unusual, check the target object and privileges before modifying any data.

**Step 4 — Restore CURRENT_SCHEMA to REPORT_USER**

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;
~~~

**Step 5 — Use a private synonym**

If granted synonym creation privilege:

~~~sql
CREATE SYNONYM app_orders FOR app_owner.orders;

SELECT order_id, amount
FROM app_orders
ORDER BY order_id;
~~~

If the synonym `APP_ORDERS` already exists, do not re-run `CREATE`; use the existing alias or request a different practice name. Note that creating an alias requires no data duplication and creates no new read privileges on the target.

**Step 6 — Inspect metadata**

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE object_name IN ('ORDERS', 'APP_ORDERS')
ORDER BY owner, object_name;

SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'APP_ORDERS';
~~~

Fill in the results in the table:

| SQL statement/lookup | Initial schema or synonym | Actual target object | Required privilege |
|---|---|---|---|
| `APP_OWNER.ORDERS` | `APP_OWNER` | `APP_OWNER.ORDERS` | `SELECT` on the table |
| `ORDERS` after `CURRENT_SCHEMA=APP_OWNER` | `APP_OWNER` | `APP_OWNER.ORDERS` if it is the table created above | `SELECT` on the table |
| `APP_ORDERS` when `CURRENT_SCHEMA=REPORT_USER` | `REPORT_USER.APP_ORDERS` | `APP_OWNER.ORDERS` | `SELECT` on the table |

**Step 7 — Discuss instead of testing broad privileges**

Another user using `REPORT_OWNER` also has a table named `ORDERS`. Predict what happens when their session runs `FROM ORDERS`, when `CURRENT_SCHEMA` is changed to `APP_OWNER` (if privileges still allow), and when `APP_OWNER.ORDERS` is written directly. Also explain the case with a public synonym `ORDERS` and why local objects take precedence.

### Self-check questions

1. Under what circumstances do `SESSION_USER` and `CURRENT_SCHEMA` differ? Which command can make them differ in a direct SQL session?
2. Does `ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER` make `REPORT_USER` the owner of `ORDERS`? Does it grant `SELECT` automatically?
3. Why does a public synonym not guarantee that every session running `FROM ORDERS` accesses the same table?
4. How do you tell whether `APP_ORDERS` is a table, view, or synonym, and if it is a synonym, where it points?
5. How do `ALL_OBJECTS` and `USER_OBJECTS` behave differently after `CURRENT_SCHEMA` has been changed?
6. Why can `APP_OWNER.ORDERS` still refer to two different objects when connecting to two different PDBs?
7. Why can a bind variable pass `:id` but cannot directly substitute a schema or table name in an identifier position?
8. If an application uses a connection pool and changes `CURRENT_SCHEMA` between requests, what risk arises?

## 12. Key takeaways to avoid querying the wrong object

A SQL statement in Oracle is interpreted within the **session context**, not solely from the character string displayed in the editor. Whenever you see:

~~~sql
SELECT * FROM orders;
~~~

ask yourself:

- Which **PDB/service** is the session connected to?
- What is `CURRENT_SCHEMA`, and does it differ from `SESSION_USER`?
- In the active schema, is there a table/view or private synonym named `ORDERS`? Is there a public synonym with the same name?
- What object does the synonym point to, and does it go through a database link?
- Does the executing user hold the necessary privileges on the target object?

If you want certainty about the target schema, write `APP_OWNER.ORDERS` explicitly and confirm the container. If you need stable aliases, use managed synonyms and verify metadata; if you change `CURRENT_SCHEMA`, control session state and connection pooling carefully. **Schema-qualified names, CURRENT_SCHEMA, and synonyms are three different naming/resolution mechanisms; none of them replaces privilege and container checks.**
