# Object Names, Quoted Identifiers, and Case Sensitivity in Cassandra CQL

## 1. Why Do Naming Rules Matter?

In Apache Cassandra, CQL statements use **identifiers** to refer to keyspaces, tables, columns, user-defined types (UDTs), and certain other schema objects. Identifiers look like ordinary character strings, but **how double quotes are used determines which name Cassandra resolves**.

This is part of the **Keyspaces and Schema** chapter in module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. When designing wide-column tables from queries, partition keys, clustering columns, and table names must be referenced accurately by the application. A case mismatch can cause a CQL statement to report that a table/column is not found, or to point to a different object if a similar name already exists.

After this lesson, you will be able to:

1. Distinguish unquoted identifiers from quoted identifiers.
2. Predict how Cassandra normalizes names when encountering uppercase and lowercase letters.
3. Use proper syntax when a name contains a CQL keyword, uppercase letters, or allowed special characters.
4. Inspect the actual names stored in the schema and use them properly from `cqlsh` and Java applications.
5. Choose low-risk naming conventions for keyspaces, tables, and columns in a distributed environment.

## 2. Two Ways to Write Identifiers in CQL

### 2.1. Unquoted identifiers: without double quotes

**Identifiers not enclosed in double quotes are case-insensitive.** Cassandra normalizes them to lowercase when resolving and storing schema names.

For example, the following forms point to **the same logical name**:

```sql
SELECT customer_id FROM orders_by_customer;
SELECT CUSTOMER_ID FROM ORDERS_BY_CUSTOMER;
SELECT Customer_Id FROM Orders_By_Customer;
```

All three are interpreted equivalently to the lowercase names `customer_id` and `orders_by_customer`, **provided** those tables/columns exist and the keyspace context is right. Cassandra does **not** automatically insert underscores: `CustomerID` is normalized to `customerid`, which differs from `customer_id`.

For custom names, a simple choice is lowercase ASCII letters, digits, and underscores, starting with a letter: `commerce`, `orders_by_customer`, `customer_id`, `created_at`. Different object groups may have different character/length limits depending on the Cassandra version; using simple names improves compatibility.

### 2.2. Quoted identifiers: enclosed in double quotes

**Identifiers in double quotes preserve exact casing and are matched exactly as declared.**

```sql
-- Two columns can carry two different logical names:
"customerid"
"CustomerID"
```

The name `"CustomerID"` is **not equivalent** to unquoted `customerid` or `CUSTOMERID`. Conversely, `"customerid"` written entirely in lowercase matches the unquoted logical name `customerid`.

This rule applies when referencing tables, columns, keyspaces, and schema objects that support quoted identifiers. However, **using double quotes does not mean every arbitrary name is valid for every object type**: for example, keyspaces and tables may be subject to additional naming restrictions in the version in use.

| CQL Written | Name Cassandra Uses for Lookup | Matches `customerid`? |
| --- | --- | --- |
| `customerid` | `customerid` | Yes |
| `CustomerID` | `customerid` | Yes |
| `CUSTOMERID` | `customerid` | Yes |
| `"customerid"` | `customerid` | Yes |
| `"CustomerID"` | `CustomerID` | No |
| `"CUSTOMERID"` | `CUSTOMERID` | No |
| `customer_id` | `customer_id` | No; the underscore is significant |

> Memory tip: **No double quotes → lowercase. With double quotes → keep every character as written.**

### 2.3. Identifiers differ from string literals

In CQL, double quotes and single quotes serve different roles:

| Notation | Role | Example |
| --- | --- | --- |
| `customer_id` | Unquoted identifier | Column name |
| `"CustomerID"` | Quoted identifier | Case-sensitive column name |
| `'CustomerID'` | String literal | **String value** consisting of characters `CustomerID` |
| `'class'`, `'datacenter1'` | String literal inside replication map | Key/value of the `replication` option |

The following example illustrates both quote types in the same statement:

```sql
SELECT "DisplayName"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- "DisplayName" is the column name.
-- On INSERT, 'Nguyễn An' is text data written to that column.
```

Do not replace `"DisplayName"` with `'DisplayName'` to refer to a column: a string literal has no column-identifying function.

## 3. In What Scopes Do Keyspace, Table, and Column Names Live?

Cassandra objects have multi-level naming relationships. For example:

```text
Cassandra Cluster
└── keyspace: naming_lab
    ├── table: people_by_id
    │   ├── column: person_id
    │   ├── column: display_name
    │   └── column: "DisplayName"
    └── table: "PeopleById"  (illustrating another table name)
```

A **table's fully qualified name** has the form `keyspace_name.table_name`. The dot separates namespace and object name; the dot is not a default part of an unquoted identifier.

```sql
SELECT person_id FROM naming_lab.people_by_id;

USE naming_lab;
SELECT person_id FROM people_by_id;
```

`USE naming_lab` sets the default keyspace for the CQL session; it does **not** change replica placement, partition keys, or replication factor. If a table requires a quoted identifier, place double quotes only around the **name component that needs case preservation**:

```sql
-- Syntax when the table was created with the exact name "PeopleById":
SELECT person_id FROM naming_lab."PeopleById";
```

| Object | Typical Example | When Double Quotes Are Needed |
| --- | --- | --- |
| Keyspace | `naming_lab` | An uppercase name declared intentionally, if valid for the version |
| Table | `people_by_id` | `"PeopleById"` differs from `peoplebyid` |
| Column | `person_id` | `"DisplayName"` must be referenced with exact casing |
| UDT and field | `shipping_address`, `city` | Use the exact declared name when the name contains uppercase letters |
| Materialized view, index, and other schema objects | `orders_by_customer` | Name recognition rules and object constraints must be checked per version |

**Note:** Cassandra distributes data based on partition keys and replication strategy, **not** based on whether object names have uppercase letters or quotes. Proper naming ensures CQL accesses the right schema; RF/consistency configuration and key design are separate decisions.

## 4. Hands-On Example: One Normal Name and One Uppercase Name

Commands in this section use a **dedicated lab keyspace**. Suppose `nodetool status` reports the real DC is `datacenter1` and the lab has only one node; change the DC name in CQL if your environment differs.

### Step 1 — Create the keyspace

```sql
CREATE KEYSPACE IF NOT EXISTS naming_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': '1'
}
AND durable_writes = true;
```

Here, `naming_lab` is an **unquoted identifier**. The two strings `'class'` and `'datacenter1'` are literals inside the replication map; they do not follow identifier normalization rules. The DC name must match actual topology, and RF = 1 is only to fit a single-node lab.

### Step 2 — Create a table with some quoted columns

```sql
CREATE TABLE naming_lab.people_by_id (
    person_id uuid PRIMARY KEY,
    name text,
    "DisplayName" text,
    "SELECT" text
);
```

The table has four columns but two name resolution rules:

- `person_id` and `name` are unquoted identifiers, stored in lowercase; unquoted `PERSON_ID` and `Name` still refer to them accurately.
- `"DisplayName"` preserves uppercase `D` and `N`. A query using unquoted `DisplayName` will look for `displayname`, which is **different** from the declared column.
- `"SELECT"` is a quoted identifier using a CQL keyword as a column name. Writing unquoted `SELECT` in a column-name position can cause the parser to treat it as a syntax keyword rather than an identifier.

### Step 3 — Write and read using the exact column names

```sql
INSERT INTO naming_lab.people_by_id (
    person_id, name, "DisplayName", "SELECT"
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'An',
    'Nguyễn An',
    'active'
);

SELECT person_id, NAME, "DisplayName", "SELECT"
FROM NAMING_LAB.PEOPLE_BY_ID
WHERE person_id = 11111111-1111-4111-8111-111111111111;
```

The `SELECT` statement above is valid in terms of name resolution because `NAMING_LAB`, `PEOPLE_BY_ID`, and `NAME` are unquoted, so they normalize to lowercase. The two columns `"DisplayName"` and `"SELECT"` must still be quoted just as when created.

Try predicting which statements **fail** to access the same column:

```sql
-- Wrong: unquoted DisplayName becomes displayname.
SELECT DisplayName
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- Wrong: this is "DISPLAYNAME", not "DisplayName".
SELECT "DISPLAYNAME"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- Correct: write the declared column exactly.
SELECT "DisplayName"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;
```

The first two statements are usually rejected by Cassandra because the corresponding column does not exist in this table. This is an **identifier resolution** error; it is not a replication, RF, or consistency level error.

### Step 4 — Understanding quoted identifiers on table names

In the lab, you can create another table with uppercase letters using the syntax:

```sql
CREATE TABLE naming_lab."PeopleById" (
    person_id uuid PRIMARY KEY,
    city text
);

-- Correct: the table name is stored exactly as PeopleById.
SELECT * FROM naming_lab."PeopleById";

-- Unquoted name is interpreted as peoplebyid.
-- Does not automatically reference "PeopleById".
SELECT * FROM naming_lab.PeopleById;
```

At the end of the example, `naming_lab.PeopleById` points to the logical name `naming_lab.peoplebyid`. If no `peoplebyid` table exists, the query fails; if a separate table with that name exists, the query could go to a **different table**. This is why you should avoid creating multiple names that differ only in casing.

The fact that Cassandra supports quoted identifiers does not mean schema migration systems, ORMs, or backup tools all handle uppercase names conveniently. For new applications, prefer lowercase names to reduce maintenance costs.

## 5. Double Quotes, CQL Keywords, and Special Characters

### Using names that collide with language keywords

CQL has reserved keywords for statements, such as `SELECT`, `FROM`, `WHERE`. If you are forced to use a keyword as a column name, a **quoted identifier** helps the parser disambiguate:

```sql
-- Valid when the table has a column named exactly "SELECT".
SELECT "SELECT" FROM naming_lab.people_by_id;
```

Even so, **avoid keywords as schema names** if you control the new design. Names like `selection_status` or `query_type` are clearer and require fewer double quotes.

### Double quotes inside the identifier itself

When a quoted identifier needs to contain a double quote as part of its name, the CQL rule is to **write two consecutive double quotes** to represent one double quote in the name.

```sql
-- Syntax illustration for identifier:
"a""b"
```

The expression above represents the name consisting of characters `a"b`. This is a syntax rule; **do not assume every Cassandra object type permits every special character**. Keyspaces and tables may be subject to stricter naming rules than columns or some other objects. For real schemas, avoid this style of name.

If a **string value** contains a single quote, the escaping mechanism is different: double the single quote inside the string.

```sql
-- Text value O'Brien:
INSERT INTO naming_lab.people_by_id (person_id, name)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'O''Brien'
);
```

Do not mix up the escaping mechanisms for **identifiers** (`"` mark) and **string literals** (`'` mark).

### Spaces, Unicode, and naming limits

Quoted identifiers can broaden how names are expressed in **some** CQL positions, but whether spaces, Unicode, dots, or special characters are permitted depends on the object type and Cassandra version. Keyspace/table names have their own storage constraints; do not assume merely adding `"..."` lets you use any arbitrary name.

A safe convention for schema components is to use:

```text
customer_profiles
orders_by_customer
created_at
shipping_address
```

Instead of names that force quoting:

```text
"Customer Profiles"
"OrdersByCustomer"
"CREATED AT"
"SELECT"
```

Even when a special name is accepted by CQL, it can still cause trouble for migrations, driver mapping, code generators, shell scripts, or metadata queries.

## 6. Checking the Actual Names Stored in the Schema

Reading metadata is a reliable way to confirm how Cassandra stored an identifier. In `cqlsh`, you can inspect:

```sql
DESCRIBE KEYSPACE naming_lab;
DESCRIBE TABLE naming_lab.people_by_id;
DESCRIBE TABLE naming_lab."PeopleById";
```

The `DESCRIBE` command is a **`cqlsh`** utility, not a universal CQL query that can be sent verbatim through the Cassandra Java Driver.

System metadata tables allow direct querying:

```sql
-- List of stored keyspace names.
SELECT keyspace_name
FROM system_schema.keyspaces
WHERE keyspace_name = 'naming_lab';

-- Table names stored exactly as declared.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'naming_lab';

-- Column names of table people_by_id.
SELECT column_name, kind, position
FROM system_schema.columns
WHERE keyspace_name = 'naming_lab'
  AND table_name = 'people_by_id';
```

If you created the tables from the practice exercise, the metadata results above will include `person_id`, `name`, `DisplayName`, and `SELECT`; Cassandra stores quoted column names with their exact casing.

**Important pitfall:** in `WHERE keyspace_name = 'naming_lab'`, single quotes denote a **string value for comparison**. The following query does not automatically lowercase the value:

```sql
-- This condition filters the string 'PeopleById' in metadata.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'naming_lab'
  AND table_name = 'PeopleById';
```

When comparing values in the `table_name` column, case is significant just like regular data. Identifier normalization rules apply to **column/object names in CQL syntax**, not automatically to the literal `'PeopleById'`.

### Table distinguishing three commonly confused cases

| Example | What is resolved as an identifier? | What is treated as data? |
| --- | --- | --- |
| `SELECT "DisplayName" FROM naming_lab.people_by_id` | `"DisplayName"`, `naming_lab`, `people_by_id` | No literal |
| `WHERE person_id = 11111111-...` | `person_id` | UUID value |
| `WHERE table_name = 'PeopleById'` in metadata | `table_name` | String `'PeopleById'`; not auto-lowercased |

## 7. Impact When Writing Queries from Java Applications

In a Java application using the Cassandra Java Driver, **CQL still follows the exact identifier rules above**, whether queries go through `cqlsh` or the driver. Example with table `naming_lab.people_by_id`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

// session is already configured, connected, and closed per application lifecycle.
String cql = """
    SELECT "DisplayName"
    FROM naming_lab.people_by_id
    WHERE person_id = ?
    """;

PreparedStatement ps = session.prepare(cql);
UUID id = UUID.fromString("11111111-1111-4111-8111-111111111111");
Row row = session.execute(ps.bind(id)).one();
String displayName = row == null ? null : row.getString(0);
```

The snippet uses a **Java text block** (Java 15 and above), DataStax/Apache Cassandra Java Driver 4.x, and an already-connected `CqlSession session`. It uses `?` to bind the **value** of `person_id`, while the identifier `"DisplayName"` must be written accurately in the query text.

If the application uses an older Java version, you can write:

```java
String cql =
    "SELECT \"DisplayName\" FROM naming_lab.people_by_id WHERE person_id = ?";
```

In a Java string literal, `\"` represents one CQL double quote; this double quote is still mandatory at the CQL layer. Do not remove it just because the Java code looks harder to read.

### Identifiers are not bind variables

The prepared statement parameter `?` binds **data values**, not keyspace, table, or column names. The following idea is wrong:

```sql
-- Wrong: cannot bind an identifier for the table name this way.
SELECT * FROM ? WHERE person_id = ?;
```

If an application must select a table dynamically, restrict names to a **fixed allowlist** and build CQL from controlled names rather than concatenating raw user input. Also maintain consistent name quoting across both schema-creation and query statements.

Java Driver 4 also provides `CqlIdentifier` to represent CQL names in metadata/configuration. When using this API, distinguish names parsed as CQL syntax from already-normalized internal names, especially if the schema contains uppercase letters. Do not blindly apply `toLowerCase()` to every name obtained from metadata: that breaks case-sensitive quoted identifiers.

## 8. Common Errors, Causes, and Fixes

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Querying column `DisplayName` reports `Undefined column name` | The actual column is `"DisplayName"`, while `DisplayName` normalized to `displayname` | Check metadata, use `"DisplayName"` with exact spelling |
| Table created as `"PeopleById"` but `SELECT ... FROM PeopleById` fails | Unquoted name becomes `peoplebyid` | Use `"PeopleById"` or standardize schema naming in a controlled migration |
| Trying to create a column named `SELECT` causes parser error | Name collides with a CQL keyword | Change to a non-keyword name, or use a quoted identifier if that name must be kept |
| `SELECT ... WHERE table_name = 'peoplebyid'` does not find table `"PeopleById"` in metadata | String values in metadata are case-sensitive | Compare with `'PeopleById'` |
| Putting `'column_name'` in a column-name position | Confused string literal with identifier | Use `column_name` or `"ColumnName"` |
| Migration script creates a different name than the Java app | Both sides quote names inconsistently | Standardize names in schema and queries; verify metadata after migration |
| Trying to name keyspace/table with spaces thinking quotes alone suffice | Object-type/version-specific naming restrictions | Use lowercase ASCII names with `_` |
| Two similarly named tables return different data | Two distinct objects exist because a quoted name had uppercase | List `system_schema.tables`, check full exact names before selecting a table |

### Migration scenario

A legacy system declared column `"CustomerID"`, while a new application assumes column `customer_id`. Changing only the name in Java code **does not change the schema**. These are two different names in both casing and underscore; you must choose one of these controlled options:

1. Continue querying `"CustomerID"` exactly for compatibility with the legacy schema.
2. Design a new schema/table following the `customer_id` convention and migrate data, queries, and mappers in a planned manner.

Do not assume any column can be arbitrarily renamed with an `ALTER TABLE ... RENAME` command: rename support depends on column kind and Cassandra version. For query-driven tables, creating a new table and migrating data often must be evaluated whenever keys or query models change.

## 9. Self-Check Exercise

Suppose you have:

```sql
CREATE TABLE naming_lab.naming_quiz (
    id uuid PRIMARY KEY,
    product_code text,
    "ProductCode" text,
    "SELECT" text
);
```

Predict which column each reference points to:

| Reference | Result |
| --- | --- |
| `PRODUCT_CODE` | Column `product_code` |
| `Product_Code` | Column `product_code` |
| `"product_code"` | Column `product_code` |
| `ProductCode` | Logical name `productcode`, **not** `"ProductCode"`; this column does not exist in the example |
| `"ProductCode"` | Column `"ProductCode"` |
| `"PRODUCTCODE"` | Different name; no matching column |
| `"SELECT"` | Column `"SELECT"` |
| `'SELECT'` | String literal; not a column name |

Further practice:

1. Run `DESCRIBE TABLE naming_lab.naming_quiz` and query `system_schema.columns` to confirm how names are stored.
2. Write a valid `SELECT` retrieving both `product_code` and `"ProductCode"` in the same statement, filtering by `id`.
3. Try removing double quotes around `"ProductCode"` and observe the error. Explain why the issue is unrelated to partition keys, replication, or consistency levels.
4. In Java, write a prepared statement with a fixed table and use a bind marker for `id`. Ensure the quoted column name is properly escaped in the Java string if not using a text block.

After practice, if you only need to clean up test data:

```sql
-- Run only when certain naming_lab is a disposable lab keyspace.
DROP KEYSPACE IF EXISTS naming_lab;
```

The command above deletes **all** tables and data in keyspace `naming_lab`; verify there are no objects you need to keep before executing.

## 10. Recommended Conventions for Cassandra Projects

A development team using CQL from Java can reduce identifier errors with simple rules:

1. **Use lowercase `snake_case` for keyspaces/tables/columns/UDTs**, avoiding names that differ only in casing.
2. **Do not use CQL keywords** as names; pick business-meaningful names such as `order_status` instead of `"SELECT"`.
3. **Use query-revealing table names** such as `orders_by_customer`, while remembering that the partition key and clustering columns are what determine how data is stored and read.
4. **Maintain the same convention** across migrations, CQL, Java mappings, tests, and operational documentation.
5. **Read actual metadata** when dealing with legacy schemas containing quoted identifiers; do not guess how names were normalized.
6. **Avoid concatenating identifiers from free-form input**; use an allowlist and bind data with prepared statements.

A table named `orders_by_customer` with column `customer_id` is easier to query, log, and inspect than `"OrdersByCustomer"` or `"CustomerID"`. This simplicity is especially valuable when a cluster has many keyspaces, many query-driven denormalized tables, multiple replicas, and many Java components accessing it concurrently.

**Remember:** unquoted identifiers normalize to lowercase; quoted identifiers preserve casing; single quotes represent literals. Understanding these three rules accurately is the foundation for creating schemas, inspecting keyspaces/tables/columns, and writing reliable CQL for Apache Cassandra.
