# Querying CDB_*, DBA_*, ALL_*, and USER_* in Oracle Multitenant

In Oracle Database, when checking where a table exists, what objects a schema owns, or which tables a user is permitted to access, we normally query the **data dictionary views**. In a **Container Database (CDB)** environment with multiple **Pluggable Databases (PDBs)**, your choice of view and connection context determines the scope of data returned.

A query like `SELECT * FROM DBA_TABLES` does not mean "list tables across every PDB." If run inside a PDB, it reflects metadata for the **current PDB**. If run in `CDB$ROOT`, the `DBA_*` family reflects the root context rather than automatically aggregating all PDBs. When cross-container lookup is needed, the `CDB_*` family is usually the right choice, accompanied by `CON_ID` and appropriate privilege requirements.

This lesson explains how to distinguish the four view families `CDB_*`, `DBA_*`, `ALL_*`, and `USER_*`; how to identify the current container; how to write queries using `CON_ID` to avoid confusing same-named tables across different PDBs; and limitations on metadata access privileges. Examples use SQL*Plus/SQLcl and Oracle Database 19c+ syntax in a multitenant architecture context.

## 1. Context: CDB, PDBs, and Metadata

### 1.1. Why Does Multitenant Change How You Query?

A **CDB** consists of a root and can contain multiple PDBs:

- **`CDB$ROOT`**: root container holding CDB-level shared metadata and infrastructure.
- **`PDB$SEED`**: Oracle-managed template PDB used to create new PDBs.
- **Application PDBs**: e.g., `SALES_PDB`, `HR_PDB`, where tables, schemas, and applications operate logically independently.

```text
                   Oracle CDB
                       |
          +------------+-------------+
          |            |             |
      CDB$ROOT     PDB$SEED      Application PDBs
                                      |
                              +-------+-------+
                              |               |
                           SALES_PDB        HR_PDB
                              |               |
                           APP.ORDERS       APP.ORDERS
```

In the example above, two tables share the exact same name `APP.ORDERS`, yet belong to **two different PDBs**. To uniquely identify an object when querying across the CDB, you need **container**, **owner**, and **object name**; some object types also have namespaces or subobjects.

### 1.2. What Is a Data Dictionary View?

The **data dictionary** is the set of metadata describing database object structures and states: tables, columns, indexes, users, roles, grants, tablespaces, constraints, etc. Oracle provides views for users to query according to scope and privileges.

For example:

- `USER_TABLES`: tables owned by the current user.
- `ALL_TABLES`: tables within the scope the current user can access/see.
- `DBA_TABLES`: table metadata within the currently connected database/container, if granted corresponding metadata-read privileges.
- `CDB_TABLES`: view for querying tables across multiple containers, with a `CON_ID` column, when query context and privileges match.

These views hold **metadata**, not the full business row data of the tables. Reading `DBA_TABLES` is not equivalent to reading every row in `APP.ORDERS`.

### 1.3. Four Questions to Answer Before Choosing a View

1. **Which container are you connected to?** Root or a PDB?
2. **Whose objects do you need to see?** Your own, accessible objects, all objects in the PDB, or across PDBs?
3. **How far do your metadata-read privileges reach?** System privileges, view privileges, or role-granted privileges may affect results.
4. **Do you need container identification?** A table, user, or tablespace name can appear across multiple PDBs.

Skipping any of these questions can produce a query that runs without error yet gets misinterpreted.

## 2. Comparing CDB_*, DBA_*, ALL_*, and USER_*

### 2.1. Quick Comparison Table

| View Family | Typical Information Scope | Who Typically Uses It? | Key Identifying Column |
|---|---|---|---|
| **`USER_*`** | Objects **owned by the current database user** in the current container context | Developers, schema owners | Often omits `OWNER` since owner is the connected user |
| **`ALL_*`** | Objects the current user **can access** per privileges and view visibility rules | Applications, developers, report users | Usually includes `OWNER` to distinguish schemas |
| **`DBA_*`** | Metadata of the **current database/container**, not just the logged-in user | DBAs in a PDB or root | Usually includes `OWNER`; does not include `CON_ID` by default |
| **`CDB_*`** | Metadata across multiple containers in a CDB, **within allowed privileges and visibility** | Central DBAs, authorized common users | **`CON_ID`**, usually alongside `OWNER` |

The `*` in view family names is a **notational convention**, not a valid SQL wildcard. For example, write `SELECT ... FROM CDB_TABLES` or `SELECT ... FROM DBA_OBJECTS`, never `FROM CDB_*`.

### 2.2. Distinguishing via a Concrete Scenario

Suppose:

- `SALES_PDB` contains `APP.ORDERS`, `APP.CUSTOMERS`, and `REPORT.SALES_SUMMARY`.
- `HR_PDB` contains `APP.EMPLOYEES` and another table also named `APP.ORDERS`.
- User `APP` logs into `SALES_PDB`.
- User `REPORT_USER` holds `SELECT` on `APP.ORDERS` in `SALES_PDB`, but does not own the table.

Conceptually:

| Query Context | View | Notable Result |
|---|---|---|
| `APP` in `SALES_PDB` | `USER_TABLES` | Tables owned by `APP` inside `SALES_PDB` |
| `REPORT_USER` in `SALES_PDB` | `ALL_TABLES` | Can see `APP.ORDERS` if privileges/visibility conditions permit |
| DBA in `SALES_PDB` | `DBA_TABLES` | Tables across all schemas in `SALES_PDB` |
| DBA in `CDB$ROOT` | `DBA_TABLES` | Metadata for **root**, not a merged list of `SALES_PDB` and `HR_PDB` |
| Authorized common user in `CDB$ROOT` | `CDB_TABLES` | Can see `APP.ORDERS` across multiple PDBs, distinguished by `CON_ID` |

`ALL_*` does not mean "all objects in the database." **ALL** here means **the scope of objects the user is permitted to access**. Likewise, `DBA_*` does not mean just anyone can read them: reading `DBA_*` views generally requires appropriate dictionary access privileges.

## 3. Always Identify the Container Before Querying

### 3.1. Checking with SQL*Plus or SQLcl

```sql
SHOW CON_NAME;
```

Example output:

```text
CON_NAME
------------------------------
SALES_PDB
```

If you see `CDB$ROOT`, you are in the root; if you see `SALES_PDB`, you are in that PDB.

A SQL query independent of SQL*Plus/SQLcl to gather more details:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID')        AS container_id,
       SYS_CONTEXT('USERENV', 'SESSION_USER')  AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM   dual;
```

**`SESSION_USER`** is the logged-in database user; **`CURRENT_SCHEMA`** is the default schema used to resolve unqualified object names. These two values can differ if the session ran `ALTER SESSION SET CURRENT_SCHEMA`. Changing `CURRENT_SCHEMA` does not grant privileges and does not make the database user the owner of another schema's objects.

### 3.2. Listing Containers When Privileged

From the root, an account permitted to read the corresponding dynamic performance view can run:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM   v$containers
ORDER  BY con_id;
```

**Illustrative** output:

```text
CON_ID  NAME        OPEN_MODE   RESTRICTED
------  ----------  ----------  ----------
1       CDB$ROOT    READ WRITE  NO
2       PDB$SEED    READ ONLY   NO
3       SALES_PDB   READ WRITE  NO
4       HR_PDB      READ WRITE  NO
```

Common IDs:

- `CON_ID = 1`: `CDB$ROOT`.
- `CON_ID = 2`: `PDB$SEED`.
- `CON_ID >= 3`: application PDBs or other Oracle-managed containers per architecture.
- Some **dynamic performance views** use `CON_ID = 0` to represent CDB-wide data or data not tied to a single container. Do not apply that interpretation mechanically to every view and every row.

`CON_ID` is a container identifier within the **current CDB**; do not hard-code the number 3 as meaning "permanent `SALES_PDB`" in another system or after unplug/plug operations. In reports, join with the container name through an appropriate view.

### 3.3. Switching Containers When Authorized

A common administrative account with required privileges can switch into a PDB:

```sql
-- Execute only if the user holds the required privileges.
ALTER SESSION SET CONTAINER = SALES_PDB;

SHOW CON_NAME;
```

After switching containers, the exact same `SELECT ... FROM DBA_TABLES` query can return a **different dataset** because it reflects the new container context.

Do not assume every local user in a PDB can arbitrarily switch to another PDB. `SET CONTAINER` privilege, user validity in the target container, and security policies must all be satisfied.

## 4. The USER_* Family: Metadata Owned by the Current User

### 4.1. When Should You Use It?

Use `USER_*` when the question is:

- "Which tables does the currently logged-in account own?"
- "What indexes does my schema have?"
- "What are the columns and constraints on tables I own?"
- "Are my objects VALID or INVALID?"

For example, after logging in as `APP` into `SALES_PDB`:

```sql
SELECT table_name,
       tablespace_name,
       status
FROM   user_tables
ORDER  BY table_name;
```

To inspect objects in general:

```sql
SELECT object_type,
       object_name,
       status
FROM   user_objects
ORDER  BY object_type, object_name;
```

Many views in the `USER_*` family omit the `OWNER` column because the connected user itself is the owner. Do not blindly copy a `DBA_TABLES` query referencing `OWNER` onto `USER_TABLES` assuming that column exists.

### 4.2. Inspecting Column Structure

```sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       nullable
FROM   user_tab_columns
WHERE  table_name = 'ORDERS'
ORDER  BY column_id;
```

Unquoted object names are stored by Oracle in uppercase by default; hence `TABLE_NAME = 'ORDERS'` matches a table created without a quoted identifier. If a table was created with a case-sensitive quoted name, match the exact stored casing.

### 4.3. USER_* Is Not the Whole PDB

If `APP` does not own `REPORT.SALES_SUMMARY`, `APP`'s `USER_TABLES` will not list it even if `APP` has been granted `SELECT` on that table.

To list **accessible tables**, consider `ALL_TABLES`. To inventory all tables in the PDB with DBA privileges, use `DBA_TABLES`.

### 4.4. USER_* Is Per PDB

The same username (e.g., `APP`) can exist as separate **local users** in two PDBs, each owning different objects. Logging into `SALES_PDB` and running `USER_TABLES` will not return tables belonging to `APP` in `HR_PDB`.

This is intentional in multitenant: each PDB has its own metadata and security boundary. Never assume identical usernames mean a single unified account across all PDBs.

## 5. The ALL_* Family: Metadata of Objects the User Can Access

### 5.1. Difference Between ALL_* and USER_*

`ALL_*` is useful when you **do not own** an object yet need to work with objects granted to you. For instance, user `REPORT_USER` in `SALES_PDB` is granted access to table `APP.ORDERS`.

```sql
SELECT owner,
       table_name,
       tablespace_name
FROM   all_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

If the current user holds the required privilege on `APP.ORDERS`, that table appears in `ALL_TABLES`; it will **not appear in `REPORT_USER`'s `USER_TABLES`** because that user does not own the table.

The visibility scope of each `ALL_*` view depends on metadata type and view definition; do not treat every `ALL_*` view as an identical filter over `SELECT` privileges.

### 5.2. Querying Columns of a Granted Schema

```sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

The `OWNER` column is vital: the same PDB might contain both `APP.ORDERS` and `ARCHIVE.ORDERS`. Filtering solely by `TABLE_NAME='ORDERS'` could return columns from multiple tables across schemas.

### 5.3. ALL_* Does Not Cross PDB Boundaries

`ALL_TABLES` in `SALES_PDB` is scoped to the **currently connected PDB** and does not aggregate tables the user might see in `HR_PDB`. Even if a common user holds privileges in multiple PDBs, connecting to one PDB does not turn `ALL_TABLES` into a CDB-wide query.

### 5.4. Inspecting Object-Related Privileges

When checking object privileges visible in the user's context, you can use a view like `ALL_TAB_PRIVS` with `OWNER`, `TABLE_NAME`, `GRANTEE`, and `PRIVILEGE`:

```sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM   all_tab_privs
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY grantee, privilege;
```

Interpret the output according to the view definition and the user's metadata visibility; it does not mean all effective privileges are described solely by direct grant rows. Privileges can also come from roles, system privileges, or other security mechanisms. Checking a session's full effective privileges sometimes requires additional views and context.

## 6. The DBA_* Family: Metadata in the Connected Container

### 6.1. When Connected to a PDB

A DBA working in `SALES_PDB` can query:

```sql
SELECT owner,
       table_name,
       tablespace_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

The output reflects `APP` tables inside **SALES_PDB**, without automatically including tables from `HR_PDB`.

This is appropriate when an administrator wants to inspect **all schemas of a specific PDB** without needing cross-container lookups.

### 6.2. When Connected to CDB$ROOT

If the DBA is in the root and runs:

```sql
SHOW CON_NAME;

SELECT owner,
       table_name
FROM   dba_tables
WHERE  owner = 'APP';
```

`DBA_TABLES` reflects the **root context**. The query does not automatically find `APP.ORDERS` in `SALES_PDB` or `HR_PDB`. To inventory multiple PDBs simultaneously, use the `CDB_*` family in the appropriate context and privilege scope.

### 6.3. Commonly Used DBA_* Views

| View | Representative Metadata | Example Use Case |
|---|---|---|
| `DBA_TABLES` | Tables by owner, tablespace, storage attributes | Inventorying tables across schemas in a PDB |
| `DBA_OBJECTS` | Objects, object types, VALID/INVALID status | Checking invalid objects after deployment |
| `DBA_TAB_COLUMNS` | Columns and data types | Reading table structures of other schemas |
| `DBA_INDEXES` | Indexes and status | Investigation / index inventory |
| `DBA_CONSTRAINTS` | Primary key, foreign key, check, unique... | Inspecting constraint models |
| `DBA_USERS` | List and attributes of database users | Checking account statuses per container |
| `DBA_ROLE_PRIVS`, `DBA_SYS_PRIVS` | Role grants and system privilege grants | Auditing privileges |
| `DBA_TABLESPACES`, `DBA_DATA_FILES` | Tablespaces and datafiles per container scope | Inspecting storage configuration |

Each view has its own columns and visibility criteria; check each view's definition in Oracle documentation rather than assuming they share identical column lists.

### 6.4. Access to DBA_* Is Not Granted by Default

An application user holding only `CREATE SESSION` cannot necessarily query `DBA_TABLES`. These views usually require the DBA to grant **appropriate dictionary read privileges**, such as via a catalog-lookup role or required object privileges per system policy.

Do not grant `SELECT ANY DICTIONARY` or broad administrative privileges just so an application can read a few table names. When business needs can be met with `USER_*` or `ALL_*`, using those view families avoids unnecessary privilege expansion.

## 7. The CDB_* Family: Cross-Container Lookup

### 7.1. Meaning of CDB_*

In Oracle Multitenant, many `CDB_<name>` views provide metadata lookup across multiple containers in the CDB. For example:

| Container-Level View | Corresponding In-Container View | Typical Data |
|---|---|---|
| `CDB_TABLES` | `DBA_TABLES` | Tables across visible containers |
| `CDB_OBJECTS` | `DBA_OBJECTS` | Object metadata, status, and type |
| `CDB_TAB_COLUMNS` | `DBA_TAB_COLUMNS` | Columns of tables/views across containers |
| `CDB_USERS` | `DBA_USERS` | Database users per container |
| `CDB_TABLESPACES` | `DBA_TABLESPACES` | Tablespace metadata per container |
| `CDB_DATA_FILES` | `DBA_DATA_FILES` | Datafiles per container |
| `CDB_ROLE_PRIVS` | `DBA_ROLE_PRIVS` | Role grants per container |

Not every `DBA_*` view has a matching `CDB_*` counterpart; verify exact view names and definitions in the Oracle Database Reference for your release.

**The most important column is `CON_ID`.** When querying across multiple PDBs, always include `CON_ID` in reports or join with container names to avoid accidentally merging data.

### 7.2. Example: Finding APP.ORDERS Across the Entire CDB

Connect using an account with cross-container query privileges in `CDB$ROOT`:

```sql
SHOW CON_NAME;

SELECT con_id,
       owner,
       table_name,
       tablespace_name
FROM   cdb_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY con_id;
```

**Illustrative** output:

```text
CON_ID  OWNER  TABLE_NAME  TABLESPACE_NAME
------  -----  ----------  ---------------
3       APP    ORDERS      APP_DATA
4       APP    ORDERS      USERS
```

Two rows share the same `OWNER` and `TABLE_NAME` yet have different `CON_ID` values, meaning they belong to **two different containers**. Do not interpret them as synchronized replicas of the same table; each table has its own data, privileges, and lifecycle.

### 7.3. Displaying PDB Names Instead of Only CON_ID

You can join `CDB_TABLES` with `V$CONTAINERS` in the root:

```sql
SELECT c.name             AS container_name,
       t.con_id,
       t.owner,
       t.table_name,
       t.tablespace_name
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
AND    t.table_name = 'ORDERS'
ORDER  BY c.name, t.owner, t.table_name;
```

Expected output based on the example data:

```text
CONTAINER_NAME  CON_ID  OWNER  TABLE_NAME  TABLESPACE_NAME
--------------  ------  -----  ----------  ---------------
HR_PDB          4       APP    ORDERS      USERS
SALES_PDB       3       APP    ORDERS      APP_DATA
```

In administrative reports, **container name + owner + table name** is much clearer than just concatenating `OWNER.TABLE_NAME`.

### 7.4. Counting Tables by PDB and Owner

```sql
SELECT c.name AS container_name,
       t.owner,
       COUNT(*) AS table_count
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner IN ('APP', 'REPORT')
GROUP  BY c.name, t.owner
ORDER  BY c.name, t.owner;
```

This query returns the **count of tables the session is permitted to see via the view**, not necessarily the exact total across all PDBs if the user has restricted privileges/visibility.

`COUNT(*)` on `CDB_TABLES` is not the number of data rows inside the tables, nor the count of physical segments or storage size.

### 7.5. Finding INVALID Objects Across Multiple PDBs

```sql
SELECT c.name AS container_name,
       o.con_id,
       o.owner,
       o.object_type,
       o.object_name,
       o.status
FROM   cdb_objects o
JOIN   v$containers c
       ON c.con_id = o.con_id
WHERE  o.status = 'INVALID'
AND    o.owner NOT IN ('SYS', 'SYSTEM')
ORDER  BY c.name, o.owner, o.object_type, o.object_name;
```

This query is helpful after a deployment or upgrade to spot `INVALID` metadata objects by container.

Do not assume every object with `STATUS='INVALID'` carries the same severity: examine object type, dependencies, and compile/validation cause. Metadata views report status; they do not automatically explain the full root cause.

### 7.6. Listing Users by PDB

```sql
SELECT c.name AS container_name,
       u.con_id,
       u.username,
       u.common,
       u.account_status
FROM   cdb_users u
JOIN   v$containers c
       ON c.con_id = u.con_id
WHERE  u.username IN ('APP', 'REPORT_USER', 'C##MONITOR')
ORDER  BY c.name, u.username;
```

The `COMMON` column distinguishes common (`YES`) from local (`NO`) users per reported metadata. A common user can have metadata rows in multiple containers; do not treat each row of `CDB_USERS` as an OS account or an independent identity.

## 8. How Container Scope and Access Privileges Affect Results

### 8.1. CDB_* Does Not Mean "See Everything Regardless of Privileges"

To read cross-container metadata, a user typically must:

- Connect properly to **`CDB$ROOT`** with an appropriate account.
- Hold **`SELECT` privilege on the view** or appropriately configured dictionary read privileges.
- Hold **visibility to the containers' data** being queried. For common users, the **`CONTAINER_DATA`** attribute and Oracle rules for container data objects can restrict which containers are returned.
- Account for the open mode/accessibility of each PDB and release-specific constraints.

Therefore, a `CDB_TABLES` query that runs cleanly yet returns only a few PDBs **is not enough to conclude** the remaining PDBs have no tables. The session may simply lack visibility into them.

### 8.2. Common Users and Local Users

A **common user** is defined at the CDB level and can exist across multiple containers in the multitenant architecture. Common usernames normally carry the `C##` prefix under default configuration. A **local user** exists only within a specific PDB.

| Characteristic | Common User | Local User |
|---|---|---|
| Identity scope | CDB-wide, usable across multiple containers | Single PDB |
| Typical purpose | Multi-PDB admin/monitoring or shared tasks | Application schemas, business users |
| Cross-container lookup | Possible when granted right privileges and visibility | Does not gain CDB-wide access merely by logging in |
| Where normally created? | Root via common user mechanism | Target PDB |

Holding metadata query privileges in one PDB does not automatically grant the same privileges in another PDB. Additionally, **common** privileges and **local** privileges are separate concepts to evaluate when issuing grants.

### 8.3. What Is CONTAINER_DATA?

Oracle uses the `CONTAINER_DATA` attribute to specify the scope of containers a common user can view through **container data objects**, including the relevant cross-container views.

Conceptual example:

```text
CDB$ROOT
  |
  +-- SALES_PDB
  +-- HR_PDB
  +-- FINANCE_PDB

Common user C##MONITOR:
  Permitted container data visibility: CDB$ROOT, SALES_PDB
  Not permitted to see: HR_PDB, FINANCE_PDB
```

Even if `SELECT` on `CDB_TABLES` is granted, if `CONTAINER_DATA` allows only a narrow set of containers, the output may include only metadata for root and `SALES_PDB`. Expanding view read privileges does not automatically expand visibility across all PDBs.

Configuring `CONTAINER_DATA` is typically the responsibility of DBAs managing CDB-wide security. Syntax and modification rules can vary by container data object type, user type, and version; do not modify the attribute just to "fill out report rows" without data-scope approval.

### 8.4. Distinguishing Metadata Read Privileges from Object Operation Privileges

A user may be allowed to read `CDB_TABLES` and know `APP.ORDERS` exists in `HR_PDB` while having **no `SELECT` privilege on the business data inside that table**. Conversely, a user with `SELECT` on a table in `SALES_PDB` does not necessarily have privileges to read `DBA_TABLES` or `CDB_TABLES`.

These two privilege groups serve different purposes:

- **Dictionary/catalog privileges**: viewing metadata about the database.
- **Object privileges**: executing operations like `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on business objects.

When designing monitoring accounts, grant only what is strictly required. Avoid using `SYS` as a routine metadata-reporting account.

### 8.5. Watch Out for Closed or Unavailable PDBs

`OPEN_MODE` and access restrictions can affect collecting metadata from a PDB, especially in cross-container tools and queries. If rows for a PDB are missing, check:

```sql
SELECT name, open_mode, restricted
FROM   v$containers
ORDER  BY con_id;
```

Never open a production PDB just to complete a report without operational authorization. When full observation is not possible, reports must explicitly state the readable scope at the time of querying.

## 9. Comparing the Same Goal Across All Four View Families

Suppose you want to find table `ORDERS` in schema `APP`:

### 9.1. Developer Logged Into Schema APP Inside SALES_PDB

```sql
-- APP is the table owner.
SELECT table_name
FROM   user_tables
WHERE  table_name = 'ORDERS';
```

Short query, requiring no elevated dictionary privileges. It does not look outside schema `APP`.

### 9.2. REPORT_USER Granted Access on APP.ORDERS

```sql
SELECT owner,
       table_name
FROM   all_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
```

This query looks within the scope of objects accessible to the user inside `SALES_PDB`; it does not inspect `HR_PDB`.

### 9.3. DBA Administering SALES_PDB

```sql
SELECT owner,
       table_name
FROM   dba_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
```

The DBA queries metadata inside the current PDB. Output may look identical to the `ALL_TABLES` query above for the `APP.ORDERS` row, yet the **privilege scope differs**.

### 9.4. Central DBA Administering the Whole CDB

```sql
SELECT c.name AS pdb_name,
       t.owner,
       t.table_name
FROM   cdb_tables t
JOIN   v$containers c ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
AND    t.table_name = 'ORDERS'
AND    c.name NOT IN ('CDB$ROOT', 'PDB$SEED')
ORDER  BY c.name;
```

This query lists `APP.ORDERS` across PDBs visible to the user. It also explicitly excludes root and seed to focus the report on application PDBs.

## 10. Querying Table and Object Structures in the Right Scope

### 10.1. With Application-Level Privileges Only

For example, a user needs to inspect columns of a granted table:

```sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

Using `ALL_TAB_COLUMNS` is standard for schema-discovery tools running under an application account, provided the user holds sufficient privileges for that metadata to appear.

### 10.2. When a DBA Needs All Columns in One PDB

```sql
SELECT owner,
       table_name,
       column_name,
       data_type
FROM   dba_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

The query uses the dictionary scope of the **currently connected container**.

### 10.3. When Comparing Structures Across PDBs

In the root with appropriate privileges:

```sql
SELECT c.name AS container_name,
       tc.owner,
       tc.table_name,
       tc.column_id,
       tc.column_name,
       tc.data_type,
       tc.data_length,
       tc.nullable
FROM   cdb_tab_columns tc
JOIN   v$containers c ON c.con_id = tc.con_id
WHERE  tc.owner = 'APP'
AND    tc.table_name = 'ORDERS'
ORDER  BY c.name, tc.column_id;
```

This example helps detect two PDBs having different column structures despite sharing a table name. Comparing only names and `DATA_TYPE` may be insufficient for special data types; depending on needs, inspect `DATA_PRECISION`, `DATA_SCALE`, `CHAR_USED`, `CHAR_LENGTH`, and other attributes too.

### 10.4. Tracking Invalid Objects in the Right PDB

If the DBA manages only `SALES_PDB`:

```sql
SELECT owner,
       object_type,
       object_name,
       status
FROM   dba_objects
WHERE  status = 'INVALID'
AND    owner = 'APP'
ORDER  BY object_type, object_name;
```

To monitor the entire CDB, switch to `CDB_OBJECTS` and include `CON_ID`. Never query `DBA_OBJECTS` from the root and conclude no PDB has any invalid objects left.

## 11. Common Interpretation Mistakes

### 11.1. "Running DBA_TABLES in Root Shows Every PDB"

**False.** `DBA_TABLES` reflects the dictionary of the current container. In the root, use `CDB_TABLES` with appropriate privileges to inventory PDBs, or connect individually to each PDB to query `DBA_TABLES`.

### 11.2. "CDB_TABLES Shows Two APP.ORDERS, So There Is a Duplicate Table"

**False.** One row with `CON_ID=3` and another with `CON_ID=4` can indicate two independent tables in two PDBs. Always include container name and owner before comparing or reporting.

### 11.3. "ALL_TABLES Lists All Tables in the Database"

**False.** `ALL_TABLES` is based on objects accessible to the current user; a user missing privileges sees fewer tables than a DBA even inside the same PDB.

### 11.4. "No Rows in CDB_USERS Means the PDB Has No Users"

**Insufficient evidence.** The querying common user may lack privileges/`CONTAINER_DATA`, the PDB may have state restrictions, or the username filter may be wrong.

### 11.5. "USER_TABLES Has an OWNER Column Just Like DBA_TABLES"

**Do not assume so.** Many `USER_*` views omit `OWNER` because the owner is already the current user. Check view column definitions before porting a query from one family to another.

### 11.6. "Changing CURRENT_SCHEMA to APP Makes USER_TABLES Show APP's Tables"

**Invalid assumption.** `ALTER SESSION SET CURRENT_SCHEMA` changes unqualified name resolution; it does not change the login identity or grant ownership. To inspect another schema, use `ALL_*` or `DBA_*` per current privileges.

### 11.7. "Having SELECT on the Dictionary Guarantees SELECT on Every Business Table"

**False.** Reading metadata and reading table data are separate privileges. Never assume business data access simply because the dictionary confirms a table exists.

### 11.8. "CON_ID Is a Fixed PDB Name Across Environments"

**False.** `CON_ID` identifies a container within the current CDB. In reports comparing CDBs or spanning administrative operations, rely on the container's proper name/identity rather than hard-coding numeric meanings.

## 12. Diagnosing Unexpected Query Results

### 12.1. Expected Table Is Missing

For example, `ALL_TABLES` returns no row for `APP.ORDERS`:

1. Check `SHOW CON_NAME`: are you connected to the right PDB?
2. Check `SESSION_USER` and `CURRENT_SCHEMA`: which user and default schema are active?
3. Check owner/table name: the dictionary name might differ from expectations due to quoted identifiers.
4. Check whether the user holds access privileges on the target object.
5. If an inventory independent of the application user's privileges is needed, ask a DBA to check `DBA_TABLES` in the same PDB.

Do not jump to assuming the table was dropped just because one user cannot see it in `ALL_TABLES`.

### 12.2. CDB_* Returns Fewer PDBs Than Expected

If querying from the root returns only `SALES_PDB` metadata:

1. Check the PDB list and `OPEN_MODE` via `V$CONTAINERS`.
2. Confirm the query is actually running in `CDB$ROOT`.
3. Check the user's view read privileges and **`CONTAINER_DATA`** scope per current policy.
4. Verify the `WHERE` clause is not unintentionally filtering out PDBs or schemas.
5. Report object counts only for the PDBs actually observed; explicitly state the collection scope.

### 12.3. Encountering ORA-00942 or ORA-01031

- **`ORA-00942: table or view does not exist`**: the object does not exist under the referenced name or the user lacks appropriate access privileges; you might also be in the wrong container.
- **`ORA-01031: insufficient privileges`**: insufficient privileges to perform the requested operation.

Being able to read `USER_TABLES` does not mean the user can read `DBA_TABLES` or `CDB_TABLES`. Grant only the exact required privileges within approved scope; never elevate system privileges casually while investigating a metadata query.

### 12.4. Errors When Switching PDBs

An `ALTER SESSION SET CONTAINER = ...` command can fail due to insufficient privileges, a nonexistent/unavailable target container, or an invalid user in the target container. Querying metadata from a PDB does not require ordinary applications to hold PDB-switching privileges; for applications, the standard approach is connecting through the corresponding PDB's service.

### 12.5. SQL Runs Fine Yet Reports Wrong Counts

Typical causes:

- Counting `COUNT(*)` by `OWNER` while forgetting `CON_ID`, merging objects from multiple PDBs.
- Joining `CDB_*` views without including `CON_ID` in the join condition with container metadata.
- Failing to exclude root/seed when intending to count only application PDBs.
- Mixing tables with partitions/subobjects when picking views from a different family or metadata type.
- Treating rows hidden by missing privileges as nonexistent objects.

In reports, always document **which CDB/PDB**, **which login user**, **metadata visibility privileges**, and the **timestamp** of the check.

## 13. Guided Practice

The exercises below use read-only metadata queries only. `SALES_PDB`, `HR_PDB`, `APP`, and `ORDERS` are examples; substitute real values from your learning environment. No new tables need to be created if sample schemas already exist.

### Exercise 1 — Identify Session Scope

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME')       AS container_name,
       SYS_CONTEXT('USERENV','SESSION_USER')   AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM   dual;
```

**Question:** If the output shows `SALES_PDB` and `SESSION_USER=APP`, whose tables does `USER_TABLES` return metadata for?

**Hint:** Tables owned by database user `APP` inside `SALES_PDB`.

### Exercise 2 — Compare USER_TABLES and ALL_TABLES

```sql
SELECT table_name
FROM   user_tables
ORDER  BY table_name;

SELECT owner, table_name
FROM   all_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

**Question:** Why can row counts differ when executed as `REPORT_USER`?

**Hint:** `USER_TABLES` shows only tables owned by `REPORT_USER`, whereas `ALL_TABLES` can show `APP` tables that `REPORT_USER` is permitted to access.

### Exercise 3 — Inspect Schemas in One PDB

Using an appropriate DBA account, connect directly to `SALES_PDB` or enter the PDB via an authorized method:

```sql
SHOW CON_NAME;

SELECT owner, COUNT(*) AS table_count
FROM   dba_tables
WHERE  owner IN ('APP', 'REPORT')
GROUP  BY owner
ORDER  BY owner;
```

**Question:** Can this result be used to claim how many tables `APP` has in `HR_PDB`?

**Hint:** No; this is metadata in the currently connected container only.

### Exercise 4 — Cross-Container Statistics

With an appropriate common user in the root:

```sql
SHOW CON_NAME;

SELECT c.name AS container_name,
       t.owner,
       COUNT(*) AS table_count
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
GROUP  BY c.name, t.owner
ORDER  BY c.name, t.owner;
```

**Question:** If only `SALES_PDB` appears, does that prove `HR_PDB` has no `APP` user?

**Hint:** No. First verify privileges, `CONTAINER_DATA`, PDB state, and filter conditions.

### Exercise 5 — Cross-Check Columns of Same-Named Tables

```sql
SELECT c.name AS container_name,
       col.column_id,
       col.column_name,
       col.data_type
FROM   cdb_tab_columns col
JOIN   v$containers c
       ON c.con_id = col.con_id
WHERE  col.owner = 'APP'
AND    col.table_name = 'ORDERS'
ORDER  BY c.name, col.column_id;
```

**Question:** If `SALES_PDB` has column `DISCOUNT_RATE` while `HR_PDB` does not, what can be concluded?

**Hint:** The two tables sharing the same owner/table name in the two PDBs have different structures; review deployment/schema migration processes if they are expected to match.

## 14. Checklist When Writing Metadata Reports

Before sending a report to administration or development teams, verify the following:

| Question | How to Verify |
|---|---|
| Is the report in root or which PDB? | `SHOW CON_NAME`, `SYS_CONTEXT('USERENV','CON_NAME')` |
| Which user is running it? | `SESSION_USER` |
| Need own objects or accessible objects? | Choose `USER_*` or `ALL_*` |
| Need all schemas of a single PDB? | `DBA_*` from the right PDB, with appropriate privileges |
| Need multiple PDBs? | `CDB_*` from root, subject to privileges and `CONTAINER_DATA` scope |
| Could object names collide across PDBs? | Include `CON_ID` and container name |
| Are all PDBs confirmed observed? | Cross-check `V$CONTAINERS`, open states, and privileges |
| Comparing the same type of metadata? | Check view definitions, columns, and object types |
| How should zero rows be interpreted? | Distinguish nonexistent from missing privileges / wrong container |
| Are broader privileges needed? | Request least dictionary privilege for the task; avoid expanding business privileges |

**Decision pattern for choosing a view:**

```text
Need to view object metadata?
      |
      +-- Only owned by logged-in user? --------> USER_*
      |
      +-- Objects the user can access? ---------> ALL_*
      |
      +-- All schemas in current PDB? ----------> DBA_* (with privileges)
      |
      +-- Multiple PDBs in CDB?
               |
               +-- Connect in CDB$ROOT
               +-- Hold appropriate dictionary/container privileges
               +-- Use CDB_* + CON_ID + container name
```

## 15. Review Questions

1. Why cannot `DBA_TABLES` executed in `CDB$ROOT` replace `CDB_TABLES` when aggregating across application PDBs?
2. An account in `SALES_PDB` does not own `APP.ORDERS` yet holds `SELECT` on it. Should it start with `USER_TABLES` or `ALL_TABLES`?
3. Two `CDB_TABLES` rows share `OWNER='APP'` and `TABLE_NAME='ORDERS'` but have different `CON_ID`s. Is this duplicated data?
4. Does `ALL_TABLES` mean seeing every table of every schema in the CDB?
5. Why can a common user in root read `CDB_USERS` yet still miss users from certain PDBs?
6. Should you drop the `CON_ID` column when exporting a `CDB_OBJECTS` report to CSV?
7. If a user in a PDB gets `ORA-00942` running `SELECT * FROM DBA_TABLES`, what should you check before requesting broad admin rights?
8. Does `ALTER SESSION SET CURRENT_SCHEMA=APP` turn the session into user `APP`?
9. Which view lists all `INVALID` objects in **one PDB**? What if you want to check multiple PDBs?
10. Why should the PDB name be included when inventorying same-named objects or users?

**Answer hints:**

1. `DBA_*` reflects the current container; `CDB_*` enables viewing metadata across multiple containers per privileges.
2. `ALL_TABLES`; the user does not own the table so `USER_TABLES` is unsuitable.
3. No; they can be two independent tables in two PDBs.
4. No; only within the scope of objects accessible to the user in the current container.
5. It may be restricted by `CONTAINER_DATA`, privileges, PDB state, and container visibility.
6. No; omitting `CON_ID` makes it hard to distinguish same-named objects across PDBs.
7. Verify the right container, exact view name, and current dictionary read privileges.
8. No; it only changes the default schema for name resolution.
9. `DBA_OBJECTS` inside the PDB; `CDB_OBJECTS` from the root with appropriate privileges for multiple PDBs.
10. Because usernames/object names can repeat across PDBs; container name identifies exact ownership location.

## 16. Official Oracle References for Further Reading

- [Oracle Database Concepts — Multitenant Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): fundamentals of CDB, root, seed, PDBs, and metadata scope.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): definitions of data dictionary views and dynamic performance views.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): CDB/PDB management, connections, and container navigation.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): common/local users, privileges, and security boundaries in multitenant.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): `ALTER SESSION` syntax and SQL expressions.
- [Oracle Database Reference — DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLES.html): columns and semantics of table metadata.
- [Oracle Database Reference — CDB_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CDB_TABLES.html): querying table metadata across containers.
- [Oracle Database Reference — V$CONTAINERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-CONTAINERS.html): container IDs, names, and states.

When querying the dictionary in Oracle Multitenant, determine **connected container**, **question scope**, **metadata read privileges**, and **container ID of each result row**. Use `USER_*` for objects you own; `ALL_*` for objects you can access; `DBA_*` for metadata inside the current container; and `CDB_*` with `CON_ID` when reporting across multiple PDBs within permitted privilege scope.
