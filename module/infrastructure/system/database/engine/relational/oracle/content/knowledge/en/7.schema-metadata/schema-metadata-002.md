# Object Names, Quoted Identifiers, and Case Sensitivity in Oracle Database

When writing SQL for Oracle, you can create a table using `CREATE TABLE orders (...)` and query it back using `SELECT * FROM ORDERS` or `SELECT * FROM Orders` without any case issues. However, if a table is created with the name `"Orders"`, Oracle remembers the exact uppercase `O` and lowercase `rders`; when referencing it, you must use the exact spelling and double quotes. This small distinction has a major impact on SQL statements, metadata, Java code, migration scripts, and troubleshooting in multi-schema systems.

In the **Schema and metadata** section, this lesson focuses on how Oracle handles **object names** and **SQL identifiers**: table names, columns, views, schemas, aliases, constraints, sequences, and other named components. We will distinguish **nonquoted identifiers** from **quoted identifiers**, how they appear in the data dictionary, and how to reference them accurately.

After studying this lesson, you will be able to:

- Explain why `orders`, `ORDERS`, and `OrDeRs` are equivalent when **not** quoted.
- Distinguish `ORDERS`, `"ORDERS"`, `"Orders"`, and `"orders"` in SQL statements.
- Write SQL to work with table/column names containing mixed case, spaces, or keywords.
- Use `USER_OBJECTS`, `USER_TABLES`, and `USER_TAB_COLUMNS` to determine the actual object names stored by Oracle.
- Understand the difference between case sensitivity for **identifiers** and for **string values**.
- Choose maintainable naming conventions across SQL, Java/JDBC, ORMs, and migrations.

> **Scope:** The examples are intended for a **practice schema** in an Oracle PDB opened `READ WRITE`. These `CREATE`, `ALTER`, and `DROP` commands actually modify the schema; run them only in your lab environment. Existing usernames, tables, and objects may differ from the examples.

## 1. What is an identifier, and how does it differ from display names and data values?

An **identifier** is a name that SQL syntax uses to refer to an object or a named component. Example:

~~~sql
SELECT order_id, customer_name
FROM orders
WHERE order_id = 10;
~~~

In this statement:

| Component | Type | Meaning |
| --- | --- | --- |
| `orders` | Table identifier | Name of the table to query |
| `order_id` | Column identifier | Column name used in `SELECT` and `WHERE` |
| `customer_name` | Column identifier | Customer name column |
| `10` | Number literal | Numeric value used for comparison |
| `SELECT`, `FROM`, `WHERE` | SQL keywords | Statement syntax, not table/column names |

Compare these two:

~~~sql
-- Column name: identifier
SELECT customer_name
FROM orders;

-- Character string: string literal, not an identifier
SELECT 'customer_name' AS sample_text
FROM dual;
~~~

The first statement reads the value of the `CUSTOMER_NAME` column from each row; the second returns the fixed literal text `customer_name`. **Single quotes `'...'` are used for string literals, while double quotes `"..."` are used for quoted identifiers.**

The same rules apply to schema, table, view, column, sequence, index, constraint, function, package, and query alias names; specific object types may have additional naming constraints depending on the Oracle version.

## 2. Basic rule: nonquoted identifiers

### 2.1. Oracle normalizes to uppercase

When you write an object name **without enclosing it in double quotes**, Oracle treats that identifier in uppercase when storing and matching names. In the following three statements, the table name is interpreted identically:

~~~sql
SELECT * FROM orders;
SELECT * FROM ORDERS;
SELECT * FROM OrDeRs;
~~~

All three spellings refer to the logical name `ORDERS` in the current schema context, provided a matching table/view exists and the user has privileges. This keeps normal SQL from having to worry much about casing in source code.

Table creation example:

~~~sql
CREATE TABLE customer_orders (
    order_id       NUMBER PRIMARY KEY,
    customer_name  VARCHAR2(100),
    order_total    NUMBER(12, 2)
);
~~~

In Oracle metadata, the standard table and column names take the form:

~~~text
TABLE_NAME       = CUSTOMER_ORDERS
COLUMN_NAME      = ORDER_ID
COLUMN_NAME      = CUSTOMER_NAME
COLUMN_NAME      = ORDER_TOTAL
~~~

Even though you typed the names in lowercase, Oracle storing identifier names in uppercase **does not turn data inside the columns into uppercase**. The value `'Alice'` in `CUSTOMER_NAME` remains `'Alice'` according to string storage rules.

### 2.2. Common syntax restrictions

For simple ASCII names, a nonquoted identifier:

- Starts with a **letter**.
- Typically follows with letters, digits, or underscores `_`; Oracle also allows `$` and `#` in standard names, though those two characters are discouraged in application naming conventions.
- Does not contain spaces or hyphens `-` under standard naming.
- Does not use Oracle **reserved** keywords as unquoted names.
- Must satisfy the length limit **measured in bytes**, not visible character count.

Readable and relatively safe names:

~~~text
CUSTOMER_ORDERS
ORDER_ID
CREATED_AT
EMPLOYEE2
REPORT_2026
~~~

The following are not valid nonquoted identifiers under basic ASCII conventions:

~~~text
order status       -- contains a space
2orders            -- starts with a digit
order-total        -- hyphen - is interpreted as an operator
select             -- SELECT is a reserved SQL keyword
~~~

Names with international characters may be affected by character sets and Oracle identifier rules. While using accented Vietnamese characters or special characters may be syntactically possible via quoted identifiers, consider compatibility with drivers, migration tools, shells, and the development team.

### 2.3. Length limits by version

In **Oracle Database 12.2 and later**, most common identifiers such as table/column names have a maximum limit of **128 bytes**; in many versions prior to 12.2, the corresponding limit was **30 bytes**. Some specialized name types still have their own limits or rules, so do not assume *every* name in the system supports 128 bytes.

Example:

~~~text
ORDER_ID                  -- 8 bytes when using ASCII characters
CUSTOMER_DELIVERY_STATUS  -- 24 bytes with ASCII
~~~

With UTF-8, accented characters often take multiple bytes; "128 characters" **does not equal 128 bytes**. For projects that must run across multiple Oracle versions, choose a length convention compatible with the lowest supported version.

## 3. Quoted identifiers: double quotes preserve names and case

### 3.1. Naming exactly as written

If an identifier is enclosed in straight **double quotes** `"..."`, Oracle preserves the exact casing of that name and requires matching references.

~~~sql
CREATE TABLE "Invoices" (
    "InvoiceId"   NUMBER PRIMARY KEY,
    "CustomerID"  NUMBER NOT NULL,
    total_amount  NUMBER(12, 2)
);
~~~

The actual table name is `Invoices`, and the columns are `InvoiceId`, `CustomerID`, and `TOTAL_AMOUNT`. Now:

~~~sql
-- Valid: quoted table and column names must match exactly.
SELECT "InvoiceId", "CustomerID", total_amount
FROM "Invoices";

-- Valid: TOTAL_AMOUNT was created unquoted, so any casing works.
SELECT "InvoiceId", TOTAL_AMOUNT
FROM "Invoices";
~~~

If only `"Invoices"` exists without another table named `INVOICES`:

~~~sql
-- Wrong object: unquoted Invoices resolves to INVOICES.
SELECT * FROM Invoices;

-- Wrong name: uppercase in "INVOICES" does not match "Invoices".
SELECT * FROM "INVOICES";

-- Wrong column name: unquoted InvoiceId resolves to INVOICEID.
SELECT InvoiceId FROM "Invoices";
~~~

Incorrect queries can result in `ORA-00942` (table/view does not exist or is not visible due to privileges) or `ORA-00904` (invalid identifier), depending on position and privileges. However, if the schema **already has** a separate object named `INVOICES`, an unquoted statement can silently query **that object** instead of raising an error. This is why names that differ only in case can cause dangerous confusion.

### 3.2. Four spellings that are not all the same

Suppose you consider four ways of writing a name in a schema:

| SQL spelling | Name Oracle looks up | Equivalent to `orders`? |
| --- | --- | --- |
| `orders` | `ORDERS` | Yes |
| `ORDERS` | `ORDERS` | Yes |
| `"ORDERS"` | `ORDERS` | Yes, if in the same schema and object type |
| `"Orders"` | `Orders` | No |
| `"orders"` | `orders` | No |

Therefore **`"ORDERS"` can refer to the same object created with `CREATE TABLE orders`**, whereas `"Orders"` is not an automatic variant of that name.

Observe this with a self-contained example in a lab schema that has no conflicting table names:

~~~sql
CREATE TABLE orders (
    id NUMBER
);

CREATE TABLE "Orders" (
    id NUMBER
);

-- Query the table stored as ORDERS:
SELECT * FROM orders;
SELECT * FROM "ORDERS";

-- Query the table stored as Orders:
SELECT * FROM "Orders";
~~~

These two tables have **different names within the same schema**. Before applying migrations or running `DROP TABLE`, you must know the exact name stored by Oracle. This example should only be run in a learning schema because intentionally creating two names differing only by case is a poor convention for production.

### 3.3. Spaces, special characters, and keywords

Quoted identifiers allow names that would otherwise be invalid unquoted, such as:

~~~sql
CREATE TABLE "Order Details" (
    "Order ID"   NUMBER PRIMARY KEY,
    "Unit-Price" NUMBER(10, 2),
    "select"     VARCHAR2(30)
);

SELECT "Order ID", "Unit-Price", "select"
FROM "Order Details";
~~~

Oracle treats `"Order Details"` as **one** identifier instead of two words; `"Unit-Price"` as a column name rather than subtraction; and `"select"` as a quoted column name rather than the `SELECT` keyword.

Such names work, but they force every query, Java snippet, migration, ORM mapping, and reporting tool to quote the names accurately. If a system already has a naming convention, **follow the convention** instead of using quotes merely for "pretty" display formatting.

Not every character sequence becomes a valid name just by quoting it. For example, Oracle has specific exceptions such as prohibiting the all-uppercase identifier `"ROWID"`, and disallowing null characters or embedded double quotes inside names per identifier rules; specific object types may also have additional restrictions.

## 4. Case sensitivity rules in practice

### 4.1. Table names and column names are evaluated independently

Create a table in the lab schema:

~~~sql
CREATE TABLE demo_names (
    item_id        NUMBER PRIMARY KEY,
    "DisplayName"  VARCHAR2(80),
    "order status" VARCHAR2(20),
    created_at     DATE
);

INSERT INTO demo_names (
    item_id, "DisplayName", "order status", created_at
) VALUES (
    1, 'Keyboard', 'NEW', SYSDATE
);

COMMIT;
~~~

Actual stored names:

~~~text
Table:
  DEMO_NAMES

Columns:
  ITEM_ID
  DisplayName
  order status
  CREATED_AT
~~~

Valid queries:

~~~sql
SELECT
    item_id,
    "DisplayName",
    "order status",
    CREATED_AT
FROM DEMO_NAMES;

-- Equivalent for unquoted table/column names.
SELECT item_id, "DisplayName", "order status"
FROM demo_names;
~~~

Invalid queries for the exact column name:

~~~sql
-- Oracle looks for column DISPLAYNAME, not "DisplayName".
SELECT DisplayName
FROM demo_names;

-- Oracle looks for column "displayname", not "DisplayName".
SELECT "displayname"
FROM demo_names;
~~~

To query a column created with a quoted identifier, you must write `"DisplayName"` exactly. The unquoted table name `DEMO_NAMES` can be written as `demo_names` because it was created as a nonquoted identifier.

### 4.2. Qualified names: `schema.table.column`

An object name can be resolved from the **current schema** or qualified with the owner:

~~~sql
-- When connected as the table owner:
SELECT "DisplayName"
FROM demo_names;

-- If the schema was created unquoted as LAB_SCHEMA:
SELECT "DisplayName"
FROM lab_schema.demo_names;

-- Equivalent for unquoted schema/table names:
SELECT "DisplayName"
FROM "LAB_SCHEMA"."DEMO_NAMES";
~~~

If your schema was created with a **quoted** name such as `"LabSchema"`, you must write it exactly:

~~~sql
SELECT "DisplayName"
FROM "LabSchema"."DEMO_NAMES";
~~~

The object resolution path is **schema name + object name**, with each part resolved according to its own quoted/unquoted rule. In `"LabSchema"."DEMO_NAMES"`, the dot sits **between two identifiers**; it is not a single identifier containing a dot.

Oracle also has other name resolution rules such as synonyms, default schema, database links, and object types. When multiple objects share a name across different schemas, use explicit owner/alias qualification rather than relying on casing.

### 4.3. Table aliases also follow quoting rules

Aliasing helps write join queries, and an alias is still an identifier:

~~~sql
-- Unquoted alias d: Oracle normalizes it to D.
SELECT d.item_id, d."DisplayName"
FROM demo_names d;

-- Quoted alias "d": must preserve lowercase d.
SELECT "d".item_id, "d"."DisplayName"
FROM demo_names "d";
~~~

Both queries are valid, but they use **two aliases that differ in how they must be referenced**. If you declare the alias `"d"` and then write `D."DisplayName"`, the SQL statement does not reference that alias properly.

Multi-table joins should use simple, consistent, unquoted aliases unless interacting with SQL generated by another system that explicitly requires quoting.

### 4.4. Column aliases and naming result columns

Result column display names also follow quoted/unquoted rules:

~~~sql
SELECT
    item_id AS itemId,
    "DisplayName" AS "displayName",
    "order status" AS "Order Status"
FROM demo_names;
~~~

Normally, the display name for `item_id AS itemId` is normalized by Oracle to `ITEMID`, while the aliases `"displayName"` and `"Order Status"` retain their exact casing and spacing. Some SQL clients can customize header rendering, but the SQL labels returned by Oracle reflect the aliases written.

You can use a quoted alias in the `ORDER BY` clause of the same query:

~~~sql
SELECT item_id AS "itemId"
FROM demo_names
ORDER BY "itemId";
~~~

**Do not confuse a result alias with a physical column**: `AS "itemId"` does not rename the `ITEM_ID` column in the database. Nor does an alias become usable in every clause of the same query block; for example, `WHERE` must still reference the underlying column/expression per SQL syntax rules.

## 5. Data dictionary: where to verify the exact names stored by Oracle

A key habit when troubleshooting errors is to **check metadata instead of guessing**. Oracle stores unquoted names in uppercase and stores quoted names with their exact declared casing. The data dictionary views reflect this.

### 5.1. Inspecting table names via `USER_TABLES`

After creating `DEMO_NAMES` and `"Invoices"` in the examples above, run:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('DEMO_NAMES', 'Invoices')
ORDER BY table_name;
~~~

Sample output:

~~~text
TABLE_NAME
----------
DEMO_NAMES
Invoices
~~~

Notice that **`TABLE_NAME` literally holds the value `Invoices`** rather than being converted to `INVOICES`. If you write:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'INVOICES';
~~~

the query may fail to find `"Invoices"`, because `'INVOICES'` is a **string value** compared against metadata, and string comparison rules apply; by default, binary comparison is case-sensitive. Do not try quoting a **string value** as `"Invoices"` inside `WHERE`: Oracle interprets that as a column identifier, not a string literal.

### 5.2. Inspecting column names via `USER_TAB_COLUMNS`

~~~sql
SELECT
    column_id,
    column_name,
    data_type,
    nullable
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
ORDER BY column_id;
~~~

Sample output:

~~~text
COLUMN_ID  COLUMN_NAME   DATA_TYPE  NULLABLE
---------  ------------  ---------  --------
1          ITEM_ID       NUMBER     N
2          DisplayName   VARCHAR2   Y
3          order status  VARCHAR2   Y
4          CREATED_AT    DATE       Y
~~~

`ITEM_ID` and `CREATED_AT` were normalized to uppercase upon creation; `DisplayName` and `order status` were preserved verbatim.

You can also search for a specific quoted column:

~~~sql
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
  AND column_name = 'DisplayName';
~~~

If the condition says `column_name = 'DISPLAYNAME'`, it looks for a **different string** under standard case-sensitive comparison. This frequently trips up Java code generating metadata queries.

### 5.3. Finding all object types with `USER_OBJECTS`

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('DEMO_NAMES', 'Invoices', 'Orders')
ORDER BY object_name, object_type;
~~~

`USER_OBJECTS` contains many types of schema objects, not only tables. Because different Oracle namespaces can have their own name-collision rules, checking `OBJECT_TYPE` as well helps prevent wrong conclusions when searching for an object.

If you need to inspect objects the current user **has access to in other schemas**, use the appropriate `ALL_*` views (such as `ALL_TABLES`, `ALL_TAB_COLUMNS`); DBAs can use `DBA_*` according to privileges. In multitenant environments, querying from a PDB reflects only that container/privilege scope; the root and `CDB_*` views add `CON_ID` context and should not be treated as a single schema across the whole CDB.

### 5.4. Finding similar names when casing is unknown

If your goal is **discovering** existing objects, you can use:

~~~sql
SELECT table_name
FROM user_tables
WHERE UPPER(table_name) = 'INVOICES'
ORDER BY table_name;
~~~

This query can find `INVOICES`, `Invoices`, and `invoices` if all three exist, because `UPPER` is applied **to the metadata value**. It does not alter SQL name resolution rules when you actually query the table. Once you find the name, you must reference the exact target object, such as `"Invoices"`.

Using `UPPER` in metadata queries is a search tool; do not apply it carelessly to treat objects differing only by case as the same object. Your goal may be to pinpoint one specific object, not merge them.

## 6. Identifier case sensitivity differs from string comparison and collation

This is a critical distinction: the fact that Oracle is case-insensitive for **unquoted identifiers** does not mean all **string data** comparisons are case-insensitive.

Consider:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100)
);

INSERT INTO customers VALUES (1, 'Alice');
INSERT INTO customers VALUES (2, 'ALICE');
COMMIT;
~~~

These two queries reference the **same column name**:

~~~sql
SELECT FULL_NAME FROM customers;
SELECT full_name FROM CUSTOMERS;
~~~

However, filtering on **data values** is a separate matter:

~~~sql
SELECT customer_id
FROM customers
WHERE full_name = 'Alice';
~~~

Under standard case-sensitive binary comparison, `'Alice'` differs from `'ALICE'`. Oracle supports configuring collation and linguistic comparison rules at the version/session/column level, so string comparison behavior can vary. Identifier naming rules **do not automatically reverse** when an administrator changes collation for case-insensitive string searches.

To perform a case-insensitive search explicitly in a simple example, you can write:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE UPPER(full_name) = 'ALICE';
~~~

Applying a transformation to a column can affect index usage; production applications should choose an appropriately designed collation, function-based index, or search strategy. Those choices **concern string values**, not a reason to name a column `"FullName"`.

| What you are examining | Example | Rule to remember |
| --- | --- | --- |
| Unquoted column name | `full_name` and `FULL_NAME` | Generally the same identifier `FULL_NAME` |
| Quoted column name | `"FullName"` and `"FULLNAME"` | Two distinct identifiers |
| String values | `'Alice'` and `'ALICE'` | Comparison result depends on collation/configuration and operator |
| SQL keywords | `select` and `SELECT` | Same SQL keyword, not an object name |

## 7. Schema, current schema, and object namespaces

### 7.1. Name resolution without an explicit owner

For an unqualified name such as `DEMO_NAMES`, Oracle resolves the object within the session's schema context, synonyms, and privileges. In many simple cases, it resolves to a table in the current schema.

~~~sql
-- Connected as the owner of DEMO_NAMES.
SELECT item_id
FROM demo_names;

-- If the table belongs to LAB_SCHEMA and the session has access privileges:
SELECT item_id
FROM LAB_SCHEMA.DEMO_NAMES;
~~~

If the owner was created using the nonquoted identifier `lab_schema`, Oracle stores the name as `LAB_SCHEMA`. If the owner was created using the quoted identifier `"LabSchema"`, referencing `LAB_SCHEMA.DEMO_NAMES` will not automatically map to `"LabSchema"`.

### 7.2. `CURRENT_SCHEMA` does not turn you into another user

A session can set a default schema for resolving unqualified names:

~~~sql
-- Example: execute only if schema APP_SCHEMA exists
-- and you have been granted privileges on the objects to access.
ALTER SESSION SET CURRENT_SCHEMA = APP_SCHEMA;

SELECT * FROM DEMO_NAMES;
~~~

Changing `CURRENT_SCHEMA` **does not alter login identity** (`SESSION_USER`) and **does not grant additional privileges** on tables. It is solely part of name resolution. To accurately access an object with a quoted name, quoting rules must still be followed.

Inspect session context:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 7.3. Identical object names across namespaces

Oracle organizes many schema objects into **namespaces**. For example, tables, views, and several other object types share one set of naming rules; indexes and constraints have separate namespaces as defined by Oracle. Therefore:

- You cannot assume every object type is allowed to share the same name in a schema.
- Nor can you assume a name appearing in `USER_OBJECTS` can appear only once across all `OBJECT_TYPE` values.
- Quoting and casing are only **one part** of duplicate-name checks; object type and namespace also determine the outcome.

If Oracle reports `ORA-00955: name is already used by an existing object`, search for the existing object in `USER_OBJECTS` and verify its name and object type properly. Do not work around it by creating a name differing only by case and ignoring business semantics.

## 8. Common errors and how to read their symptoms

| Scenario | Possible error | Cause to check |
| --- | --- | --- |
| `SELECT DisplayName FROM DEMO_NAMES` when the column was created as `"DisplayName"` | `ORA-00904` | Oracle looks for `DISPLAYNAME`, which does not exist |
| `SELECT * FROM Invoices` when only `"Invoices"` exists | `ORA-00942` | Oracle looks for `INVOICES`; note privileges and owner can also cause this error |
| Running `CREATE TABLE ORDERS` when unquoted `orders` already exists | `ORA-00955` | Both resolve to identifier `ORDERS` in the same namespace |
| Statement uses a table name containing spaces without quotes | Syntax or identifier error | Spaces separate SQL tokens; names created with spaces must be quoted |
| Metadata query misses `"Invoices"` when filtering `TABLE_NAME='INVOICES'` | No rows returned | Comparing metadata string values with mismatched case |
| Java/JDBC/ORM reports table or column does not exist | Typically `ORA-00942`, `ORA-00904` | Framework-generated SQL may quote incorrectly or normalize names differently from DDL |
| Query succeeds but returns data from a similarly named table | May show no error | Both `ORDERS` and `"Orders"` exist in the schema; verify exact name |
| Quoted `"Alias"` in SQL referenced via unquoted `alias` | Typically `ORA-00904` | Quoted aliases must be referenced with exact case |

### 8.1. Diagnostic workflow for object name errors

If you encounter `ORA-00904` or `ORA-00942`:

1. Identify the session's **user and current schema**: `SESSION_USER` and `CURRENT_SCHEMA`; in a CDB, also check `CON_NAME`.
2. Determine **which schema** actually owns the object and whether you have access privileges.
3. Use `USER_OBJECTS`/`USER_TABLES` or `ALL_OBJECTS`/`ALL_TABLES` to get the **exact name**, including casing.
4. Use `USER_TAB_COLUMNS` or `ALL_TAB_COLUMNS` to get the **exact column names**.
5. Inspect the SQL: are quoted identifiers present and placed properly? Was `'value'` confused with `"Identifier"`?
6. If the SQL is application-generated, inspect the **actual SQL sent to Oracle**, rather than looking only at entity annotations or fields.

An `ORA-00942` error **does not always mean the table does not exist**: missing privileges, wrong schema, misdirected synonyms, wrong PDB, or a similarly named object are all possible causes. Likewise, `ORA-00904` can stem from an invalid alias or SQL scope issue, not always casing.

### 8.2. Minimal SQL to find actual names

~~~sql
-- Check session scope.
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;

-- List tables in the logged-in schema, preserving exact casing.
SELECT table_name
FROM user_tables
ORDER BY table_name;

-- List columns of the regular table DEMO_NAMES.
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
ORDER BY column_id;

-- If searching for an object with a similar name:
SELECT object_name, object_type
FROM user_objects
WHERE UPPER(object_name) LIKE '%INVOICE%'
ORDER BY object_type, object_name;
~~~

Note: `USER_*` lists objects belonging to **the corresponding user's schema** and does not automatically switch with `ALTER SESSION SET CURRENT_SCHEMA` to list another user's objects. To view objects owned by other schemas, use `ALL_*` views with appropriate `OWNER` filters and privileges.

## 9. Naming conventions for maintainable schemas and metadata

### 9.1. Recommendations for standard Oracle projects

A straightforward practical convention is:

- Name tables, columns, constraints, and indexes **unquoted** using ASCII characters and underscores to separate words when needed.
- Keep lengths within the limit of the lowest Oracle version supported by the project.
- Use meaningful business names such as `CUSTOMER_ORDERS`, `ORDER_ID`, `CREATED_AT`; avoid SQL keywords.
- Separate schemas/PDBs cleanly by environment and access level; do not resolve conflicts with names that differ only by case.
- Choose one unified strategy across migrations, ORMs, hand-written SQL, and reporting tools.

Common naming example:

~~~sql
CREATE TABLE customer_orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

SELECT order_id, customer_id, created_at
FROM customer_orders;
~~~

Oracle stores `CUSTOMER_ORDERS`, `ORDER_ID`, `CUSTOMER_ID`, and `CREATED_AT`, while SQL authors can follow the team's coding style casing without repetitive quoting.

### 9.2. When should quoted identifiers actually be used?

Quoted identifiers can be appropriate when:

- You must maintain compatibility with an **existing schema** whose names contain mixed case or spaces.
- You need to access objects imported from another tool/system with mandatory naming rules.
- A clearly governed SQL interface requires output labels/aliases with specific casing.

If you only want attractive column headers in a report, using **quoted column aliases** in the `SELECT` statement is usually better than renaming physical columns:

~~~sql
SELECT
    order_id AS "Order ID",
    customer_id AS "Customer",
    created_at AS "Created At"
FROM customer_orders;
~~~

The physical column names stay standard and require no quoting in business queries, while result aliases can be customized for presentation.

### 9.3. Managing names when a system already has quoted objects

If you must work with a table like `"Invoices"`:

- Use the **exact name from metadata** with full double quotes in SQL.
- Do not change `"Invoices"` to `INVOICES` in migrations merely for uppercase consistency; it could refer to a different object.
- Check dependent queries/views, foreign keys, synonyms, scripts, mappings, and privileges before renaming.
- Consider adding a view/synonym layer per governance rules to present an easier naming interface, while understanding namespaces and privileges.

Renaming in the database can break existing application SQL resolution; Oracle DDL generally commits changes, so do not treat a rename operation as an experiment that can be rolled back like an uncommitted `UPDATE`.

## 10. Connections to Java/JDBC, ORM, and auto-generated SQL

### 10.1. JDBC does not fix quoted names for you

Suppose the schema contains `DEMO_NAMES` and column `"DisplayName"` as above. A valid JDBC SQL snippet could be:

~~~java
String sql = """
    SELECT item_id, "DisplayName"
    FROM demo_names
    WHERE item_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
            String name = rs.getString(2);
            System.out.println(id + " -> " + name);
        }
    }
}
~~~

Here the Java text block preserves the double quotes inside the SQL, allowing Oracle to recognize `"DisplayName"`. The `?` placeholder is a **bind parameter for the value** of `item_id`; it does not stand for a table or column name. You cannot write `FROM ?` and bind a table name as a regular string.

When SQL is built dynamically from object names, use an **allowlist of permitted names**, validate identifiers against Oracle rules, and use supported quoting/validation utilities (such as `DBMS_ASSERT` in appropriate PL/SQL contexts). Do not concatenate untrusted object names directly into SQL assuming double quotes eliminate SQL injection.

### 10.2. ORMs may generate SQL with different names than expected

ORM frameworks such as Hibernate/JPA have their own naming strategies and identifier quoting mechanisms. For example:

- Mapping Java `displayName` might be translated by a naming strategy into `DISPLAY_NAME`.
- If the table was created as `"OrderItem"` but the ORM emits unquoted `ORDERITEM`, Oracle will look for a different name.
- If **globally quoted identifiers** are enabled, the ORM may quote every name; this requires migrations and existing tables to match the exact casing emitted by the ORM.

When encountering `ORA-00904`/`ORA-00942` in Java, inspect the **actual SQL generated by the ORM**, and cross-check `USER_TABLES`/`USER_TAB_COLUMNS`, the current schema, and mapping rules. Do not infer from a Java class name that Oracle stores the object with the exact casing of that class.

### 10.3. Metadata APIs and column names in ResultSet

JDBC provides `DatabaseMetaData` for discovering tables and columns; when using patterns or checking metadata names, keep in mind that quoted identifiers can exist in various casings. Uppercasing every name blindly can lose access to objects created with quoted mixed-case names.

Similarly, column names returned in a `ResultSet` may be **column labels** from aliases:

~~~sql
SELECT "DisplayName" AS "displayName"
FROM demo_names;
~~~

In this query, the physical column name is `DisplayName`, while the result label is `displayName`. When serializing to JSON or mapping DTOs, be sure whether you are reading the **database column name** or the **query alias**.

## 11. Complete hands-on lab

These steps use a dedicated schema connected to the correct PDB. If conflicting table names already exist, change the name prefix or create a new lab schema following your administrator's process. Do not run DDL commands on an application schema serving live users.

### Step 1 — Verify schema and container

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name
FROM dual;
~~~

Note your current user/schema. If you are in `CDB$ROOT` or using a system account not meant for exercises, connect as the proper PDB application user.

### Step 2 — Create a table with both identifier types

~~~sql
CREATE TABLE demo_identifier_lab (
    id             NUMBER PRIMARY KEY,
    full_name      VARCHAR2(100),
    "DisplayLabel" VARCHAR2(100),
    "order-status" VARCHAR2(20)
);

INSERT INTO demo_identifier_lab
    (id, full_name, "DisplayLabel", "order-status")
VALUES
    (1, 'Alice', 'Alice (VIP)', 'NEW');

INSERT INTO DEMO_IDENTIFIER_LAB
    (ID, FULL_NAME, "DisplayLabel", "order-status")
VALUES
    (2, 'Bob', 'Bob (REGULAR)', 'PAID');

COMMIT;
~~~

Note: `id` and `full_name` are unquoted so their casing can vary; `"DisplayLabel"` and `"order-status"` must keep their exact spelling and quotes.

### Step 3 — Query using both styles

~~~sql
SELECT ID, FULL_NAME, "DisplayLabel", "order-status"
FROM DEMO_IDENTIFIER_LAB
ORDER BY id;

SELECT id, full_name, "DisplayLabel", "order-status"
FROM demo_identifier_lab
ORDER BY ID;
~~~

Both are valid for the structure just created. Try writing unquoted `DisplayLabel` or `"displaylabel"` to observe the errors in the lab:

~~~sql
-- Expected ORA-00904 if column DISPLAYLABEL does not exist.
SELECT DisplayLabel FROM demo_identifier_lab;

-- Expected ORA-00904 if column "displaylabel" does not exist.
SELECT "displaylabel" FROM demo_identifier_lab;
~~~

These are intentional error examples to recognize identifier rules, not commands to fix with system privileges.

### Step 4 — Observe what names Oracle actually stored

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'DEMO_IDENTIFIER_LAB';

SELECT column_id, column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_IDENTIFIER_LAB'
ORDER BY column_id;
~~~

Expected column names:

~~~text
ID
FULL_NAME
DisplayLabel
order-status
~~~

Distinguish object name metadata from inserted data values. Metadata names follow quoting casing rules; `Alice` and `Bob` remain the contents of `FULL_NAME`.

### Step 5 — Use display aliases to avoid renaming physical columns

~~~sql
SELECT
    id AS "Id",
    full_name AS "Full name",
    "DisplayLabel" AS "Label",
    "order-status" AS "Status"
FROM demo_identifier_lab
ORDER BY "Id";
~~~

These aliases apply only to **query output** and do not modify `USER_TAB_COLUMNS`.

### Step 6 — Clean up the lab table when no longer needed

~~~sql
-- Run only after confirming the table was created by you for the lab.
DROP TABLE demo_identifier_lab PURGE;
~~~

`DROP TABLE ... PURGE` drops the table and bypasses the recycle bin, so **you cannot rely on Flashback Drop to recover the purged table**. If you are unsure whether data should be kept, skip this step or follow an administrator-approved cleanup procedure. Never drop any table just because its name "looks like" a lab table.

## 12. Comprehension check questions

1. `CREATE TABLE customer_orders (...)` is executed unquoted. Do `SELECT * FROM customer_orders`, `CUSTOMER_ORDERS`, and `"CUSTOMER_ORDERS"` reference the same object?
2. Why does `"CustomerOrders"` differ from `CUSTOMERORDERS`?
3. What column name does Oracle store if you create `"DeliveryDate"`? How do you write a `SELECT` for that column?
4. What are the pros and cons of naming a column `"Order Status"`?
5. What do `'...'` and `"..."` mean in Oracle SQL?
6. Why might filtering `USER_TABLES.TABLE_NAME='INVOICES'` miss a table created as `"Invoices"`?
7. A schema contains both `ORDERS` and `"Orders"`. Which table does `SELECT * FROM Orders` query?
8. If a Java class is named `OrderItem` and the generated SQL emits `FROM ORDERITEM`, will it automatically query the `"OrderItem"` table?
9. Why does running `ALTER SESSION SET CURRENT_SCHEMA = APP_SCHEMA` not grant read privileges on tables in `APP_SCHEMA`?
10. Is identifier case sensitivity the same as the rule for comparing `'Alice'` and `'ALICE'` in a `VARCHAR2` column?
11. Why should names differing only by case be avoided when designing a new schema?
12. Does modern Oracle generally limit identifier length by **bytes** or by visible character count?

**Answer key:**

1. Yes, all resolve to `CUSTOMER_ORDERS`, given the same schema and context.
2. A quoted name preserves exact `CustomerOrders`, while an unquoted name is normalized to `CUSTOMERORDERS`.
3. Oracle stores `DeliveryDate`; use `SELECT "DeliveryDate" ...`.
4. It preserves a display-friendly name as-is, but requires exact quoting in every SQL statement and mapping.
5. `'...'` is a string literal; `"..."` is a quoted identifier.
6. `TABLE_NAME` holds the value `Invoices`, while the filter uses the string literal `'INVOICES'`.
7. The `ORDERS` table, not `"Orders"`.
8. No; `ORDERITEM` and `"OrderItem"` are two distinct identifiers.
9. It changes the name-resolution context, not `SESSION_USER` or privileges.
10. No; string data comparisons depend on collation and configuration.
11. They easily cause confusion in queries, migrations, exports, tooling, and schema changes.
12. By **bytes**, with limits varying by Oracle version and object type.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Database Object Names and Qualifiers](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Database-Object-Names-and-Qualifiers.html): nonquoted/quoted identifier rules, case sensitivity, allowed characters, and name lengths.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): definitions of `USER_OBJECTS`, `USER_TABLES`, `USER_TAB_COLUMNS`, `ALL_*`, and `DBA_*`.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): syntax for `CREATE TABLE`, `SELECT`, column aliases, and `ALTER SESSION`.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): differences between identifier naming rules, character sets, and string comparison/collation.
