# Sequences, Identity Columns, Generated Keys, and RETURNING in JDBC

Java applications frequently need to generate a primary key for a new record and immediately retrieve that key value to write related data, return results to an API, or update an in-memory object. With Oracle Database, there are several ways to do this: using a database sequence, using an identity column, requesting JDBC generated keys, or using the SQL RETURNING ... INTO clause.

These mechanisms are related but not identical:
- **Sequence**: an independent Oracle schema object generating a sequence of numbers; applications can fetch NEXTVAL beforehand or use it directly inside INSERT.
- **Identity column**: a column whose values Oracle automatically generates using an internal sequence tied to the table.
- **JDBC generated keys**: a JDBC API allowing applications to read database-generated values after a DML statement.
- **RETURNING INTO**: Oracle SQL syntax returning values from rows just affected by INSERT/UPDATE/DELETE; Oracle JDBC provides extended APIs to read those values.

This lesson uses Oracle Database 19c and Java JDBC as its reference baseline, focusing on:
- Creating, using, altering, and managing sequences.
- Distinguishing sequences from identity columns.
- Declaring identity columns: ALWAYS, BY DEFAULT, and BY DEFAULT ON NULL.
- Retrieving auto-generated keys via JDBC getGeneratedKeys().
- Using Oracle RETURNING ... INTO through Oracle JDBC APIs.
- Handling batch inserts, transactions, connection pools, and concurrency.
- Data type mapping, resource management, and exception handling.
- Data migration, import/export, metadata inspection, and troubleshooting.

Exact syntax and capabilities depend on the Oracle Database release, Oracle JDBC driver (ojdbc), Java version, and statement type. Always test on your application's actual driver/runtime; do not assume a JDBC feature behaves identically across every driver version.

## 1. The key generation problem in applications

Suppose an application manages orders. When creating an order, the database must assign a unique ORDER_ID. The application must also insert ORDER_ITEM rows referencing that order.

Business flow:

~~~text
Java application
      |
      | INSERT order
      v
Oracle Database assigns ORDER_ID
      |
      | Return ORDER_ID to Java
      v
Java inserts ORDER_ITEM rows using ORDER_ID
      |
      v
COMMIT transaction
~~~

The application needs the ID immediately after INSERT, yet it should never compute it manually with MAX(ORDER_ID) + 1. Two concurrent sessions can read the same MAX and generate the same value; uncommitted transactions also make the result unstable.

Common requirements:
- Unique primary keys when multiple sessions insert concurrently.
- No extra query against the table just to locate the newly inserted row.
- Obtaining the ID within the same transaction.
- Support for batch inserts when throughput is needed.
- Independence from commit ordering.
- Proper handling of transaction rollbacks and connection pools.

Oracle provides sequences and identity columns to generate numbers; JDBC provides multiple ways to retrieve them.

## 2. Oracle sequences

A sequence is a schema object that generates a series of numbers according to configuration. Sequences are independent of tables: multiple tables can share a single sequence, and a sequence can be invoked without an INSERT.

### 2.1. Creating a sequence

~~~sql
CREATE SEQUENCE order_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9999999999999999999999999999
    CACHE 100
    NOORDER
    NOCYCLE;
~~~

Key attributes:

| Attribute | Meaning |
| --- | --- |
| START WITH | Starting value |
| INCREMENT BY | Step increment/decrement |
| MINVALUE / MAXVALUE | Lower/upper bounds |
| CACHE n | Oracle pre-allocates a batch of values in memory |
| NOCACHE | Does not cache a batch of sequence values |
| ORDER | Guarantees sequence values are issued in request order |
| NOORDER | Does not require global ordering across requests |
| CYCLE | Wraps around when reaching the limit |
| NOCYCLE | Does not wrap around; errors when exhausted |

For ascending primary keys, a common configuration is INCREMENT BY 1, NOCYCLE, and CACHE sized appropriately for the workload.

### 2.2. Fetching NEXTVAL

~~~sql
SELECT order_seq.NEXTVAL
FROM dual;
~~~

Each NEXTVAL call issues a new value from Oracle. That increment happens independently of transaction commit/rollback.

It can be used directly inside INSERT:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, :customer_id, 'NEW');
~~~

There is no need to run a prior SELECT if the application does not need to know the ID before inserting.

### 2.3. Fetching CURRVAL

Once a session has called NEXTVAL, you can retrieve the most recent value issued by the sequence within that same session:

~~~sql
SELECT order_seq.CURRVAL
FROM dual;
~~~

CURRVAL is per-session state. If the current session has not yet called NEXTVAL on that sequence, Oracle raises ORA-08002.

In JDBC, NEXTVAL and CURRVAL must execute on the same physical database session. When using a connection pool, a single getConnection() holds one connection for the transaction; do not close the connection and borrow a new one to query CURRVAL.

### 2.4. NEXTVAL and CURRVAL with an INSERT

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, :customer_id, 'NEW');

SELECT order_seq.CURRVAL FROM dual;
~~~

Both statements must execute on the same connection/session. The CURRVAL value is the ID issued to that session, unaffected by interleaved NEXTVAL calls from other sessions.

### 2.5. Do not use MAX(id) + 1

Unsafe approach:

~~~sql
SELECT NVL(MAX(order_id), 0) + 1
FROM orders;
~~~

Followed by using the result for INSERT.

Two transactions can read the same MAX value and compute the same next ID. A unique constraint will cause at least one transaction to fail. Without a unique constraint, duplicate keys will corrupt data.

Oracle designed sequences for concurrency; no table lock is needed to issue numbers.

### 2.6. Sequences are not gapless

A sequence guarantees generated values do not duplicate within its configured bounds, but it does not guarantee an unbroken gap-free number series.

Gaps can appear when:
- A transaction fetches NEXTVAL and then rolls back.
- An application fetches NEXTVAL but never inserts.
- An instance crash discards cached-but-unused values.
- The sequence is altered/restarted or its cache size changes.
- Multiple sessions fetch values and commit in a different order.

Do not use a sequence for legal invoice numbers that must be continuous if business/regulatory rules require gapless numbering. That requires a dedicated serialized numbering design with auditing and rollback handling compliant with regulations.

### 2.7. CACHE and NOCACHE

CACHE n lets Oracle pre-allocate a batch of sequence values to reduce overhead under high request concurrency. Upon an abnormal instance shutdown, cached unused values can be lost, creating gaps.

NOCACHE reduces cached values, but does not make a sequence gapless. Transaction rollbacks and other factors still produce gaps.

For insert-heavy systems, caching generally improves throughput. Size the cache to the workload rather than setting NOCACHE out of fear of gaps.

### 2.8. ORDER and NOORDER

ORDER forces the sequence to issue values in request order. In RAC, guaranteeing global ordering can increase coordination overhead and hurt throughput.

NOORDER does not guarantee global chronological issuance order across instances; it still issues distinct values. For primary keys, uniqueness is usually all that matters, not IDs reflecting exact chronological order.

Never infer that a larger ID always means a later commit. Sequence allocation order is not commit order.

### 2.9. CYCLE and NOCYCLE

CYCLE allows a sequence to wrap back to MINVALUE/MAXVALUE after reaching its limit. For primary keys, wrapping can collide with existing keys.

Therefore, primary-key sequences normally use NOCYCLE. Monitor bounds and data types well before a sequence nears exhaustion.

### 2.10. Inspecting sequences

~~~sql
SELECT
    sequence_owner,
    sequence_name,
    min_value,
    max_value,
    increment_by,
    cycle_flag,
    order_flag,
    cache_size,
    last_number
FROM all_sequences
WHERE sequence_name = 'ORDER_SEQ';
~~~

LAST_NUMBER in the view is not necessarily the last value consumed by an application; when caching is enabled, it can reflect the next cache boundary. Never rely on this column alone to determine the exact ID just inserted.

### 2.11. Altering sequences

Example changing cache:

~~~sql
ALTER SEQUENCE order_seq CACHE 500;
~~~

Changing increment:

~~~sql
ALTER SEQUENCE order_seq INCREMENT BY 10;
~~~

Sequence alterations must be planned because applications may rely on assumptions about increments or bounds. Never alter a production sequence merely to fill gaps.

## 3. Identity columns in Oracle

An identity column is a numeric column whose value Oracle generates automatically when an INSERT omits a value according to the declared policy. Oracle has supported identity columns since Oracle Database 12c; Oracle 19c supports all common variants.

Identity columns simplify schemas by eliminating manual sequences and triggers for every table.

### 3.1. GENERATED ALWAYS AS IDENTITY

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(200) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);
~~~

With GENERATED ALWAYS, Oracle always generates the identity value. Applications cannot supply an explicit value for the identity column in normal INSERTs; attempting to supply one is rejected.

Use this when the database must strictly control ID issuance.

### 3.2. GENERATED BY DEFAULT AS IDENTITY

~~~sql
CREATE TABLE products (
    product_id NUMBER
        GENERATED BY DEFAULT AS IDENTITY,
    product_name VARCHAR2(200) NOT NULL,
    CONSTRAINT products_pk PRIMARY KEY (product_id)
);
~~~

If INSERT omits PRODUCT_ID, Oracle generates it. If the application supplies a value, Oracle accepts the supplied value.

This form is useful when importing legacy data while preserving IDs, though you must manage the risk of explicit values colliding with future generated IDs.

### 3.3. GENERATED BY DEFAULT ON NULL AS IDENTITY

~~~sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    invoice_number VARCHAR2(40) NOT NULL,
    CONSTRAINT invoices_pk PRIMARY KEY (invoice_id)
);
~~~

This form allows providing an explicit ID; if no value is provided or the provided value is NULL, Oracle automatically generates the identity.

Key difference:
- BY DEFAULT: an explicitly supplied NULL does not trigger identity generation the way ON NULL does.
- BY DEFAULT ON NULL: when an explicit value is NULL, Oracle generates an identity value.

### 3.4. Configuring the identity sequence

Options can be specified for the internal sequence:

~~~sql
CREATE TABLE events (
    event_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        (START WITH 1000 INCREMENT BY 1 CACHE 100 NOCYCLE),
    event_type VARCHAR2(100) NOT NULL
);
~~~

Oracle manages the internal sequence backing the identity column. Internal names typically look like ISEQ$$_...; do not depend on that name in applications and do not alter/drop the internal sequence as a business object.

### 3.5. Identity and primary keys

Identity only specifies how Oracle generates values. It does not replace data integrity constraints. Declare a PRIMARY KEY or UNIQUE constraint so the database enforces uniqueness.

Example:

~~~sql
CREATE TABLE departments (
    department_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT departments_pk PRIMARY KEY (department_id)
);
~~~

### 3.6. Inspecting identity metadata

~~~sql
SELECT
    table_name,
    column_name,
    generation_type,
    identity_options
FROM user_tab_identity_cols
ORDER BY table_name, column_name;
~~~

USER_TAB_IDENTITY_COLS shows identity columns and generation types. ALL_TAB_IDENTITY_COLS or DBA_TAB_IDENTITY_COLS can be used according to privileges.

### 3.7. When to use sequences vs. identity columns?

| Need | Sequence | Identity |
| --- | --- | --- |
| Generate primary key for one table | Suitable | Very suitable |
| One sequence shared across tables | Yes | Not the primary goal |
| Obtain ID before INSERT | Easy via NEXTVAL | Usually retrieved after INSERT |
| Control an independent sequence object | Yes | Oracle manages internal sequence |
| Simpler schema, less boilerplate | Requires sequence and DML usage | Cleaner |
| Import explicit IDs | Supported | Depends on ALWAYS/BY DEFAULT |
| Integrate legacy triggers | Common | May require migration changes |

Choose identity for new tables when you want the database to manage IDs directly in the column definition. Choose a sequence when sharing across tables, needing IDs prior to INSERT, or maintaining compatibility with legacy schemas/applications.

## 4. INSERT and retrieving IDs with JDBC

JDBC offers several ways to retrieve database-generated values after an INSERT. The right choice depends on schema, Oracle JDBC driver, and batching needs.

### 4.1. Using sequence NEXTVAL inside INSERT

This clearly fits schemas using sequences:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, ?, ?)
~~~

Java:

~~~java
String sql = """
    INSERT INTO orders (order_id, customer_id, status)
    VALUES (order_seq.NEXTVAL, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, "NEW");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted order, got " + rows);
    }
}
~~~

This alone does not return the ID to Java. If the ID is needed, query CURRVAL on the same connection after INSERT, or use JDBC generated keys/RETURNING.

### 4.2. SELECT NEXTVAL first, then INSERT

When the application needs the ID before inserting (for example, to build domain objects or write dependent rows), fetch the sequence value first:

~~~sql
SELECT order_seq.NEXTVAL FROM dual
~~~

Java:

~~~java
long orderId;

try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT order_seq.NEXTVAL FROM dual");
     ResultSet rs = ps.executeQuery()) {

    if (!rs.next()) {
        throw new SQLException("Sequence did not return a value");
    }
    orderId = rs.getLong(1);
}

String insertSql = """
    INSERT INTO orders (order_id, customer_id, status)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setLong(1, orderId);
    ps.setLong(2, customerId);
    ps.setString(3, "NEW");
    ps.executeUpdate();
}
~~~

Both operations must share the same Connection to stay within the same transaction. Sequence allocations do not roll back; if the INSERT fails, the fetched ID remains consumed.

### 4.3. INSERT then SELECT CURRVAL

If the INSERT SQL uses order_seq.NEXTVAL, you can query:

~~~sql
SELECT order_seq.CURRVAL FROM dual
~~~

Java:

~~~java
long orderId;

try (PreparedStatement insert = connection.prepareStatement("""
        INSERT INTO orders (order_id, customer_id, status)
        VALUES (order_seq.NEXTVAL, ?, ?)
        """)) {

    insert.setLong(1, customerId);
    insert.setString(2, "NEW");
    insert.executeUpdate();
}

try (PreparedStatement current = connection.prepareStatement(
        "SELECT order_seq.CURRVAL FROM dual");
     ResultSet rs = current.executeQuery()) {

    if (!rs.next()) {
        throw new SQLException("CURRVAL was not returned");
    }
    orderId = rs.getLong(1);
}
~~~

Never fetch CURRVAL on a different connection. With connection pools, keep the exact same connection from INSERT through the CURRVAL query.

## 5. JDBC getGeneratedKeys()

JDBC provides Statement.RETURN_GENERATED_KEYS and PreparedStatement.getGeneratedKeys() to read values generated by an INSERT. The Oracle JDBC driver supports generated keys, though specifying which columns to return must be configured explicitly and tested on your running driver version.

### 5.1. Using the RETURN_GENERATED_KEYS flag

Standard JDBC example:

~~~java
String sql = """
    INSERT INTO customers (customer_name)
    VALUES (?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "An Nguyen");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted customer");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated key returned");
        }

        long customerId = keys.getLong(1);
        System.out.println("customerId=" + customerId);
    }
}
~~~

With Oracle JDBC, using the generic flag may return ROWID or driver-dependent behavior if the generated key column is not specified. When you need the primary key value, explicitly request the column name instead of assuming the first column is the ID.

### 5.2. Specifying the columns to return

~~~java
String sql = """
    INSERT INTO customers (customer_name)
    VALUES (?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"CUSTOMER_ID"})) {

    ps.setString(1, "An Nguyen");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No CUSTOMER_ID returned");
        }

        long customerId = keys.getLong("CUSTOMER_ID");
    }
}
~~~

Column names must match metadata recognized by the Oracle JDBC driver; unquoted columns typically use uppercase. If the driver or schema uses quoted/case-sensitive identifiers, verify via metadata and integration tests.

### 5.3. Generated keys with identity columns

Example table:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(200) NOT NULL,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);
~~~

JDBC insert only supplies the name:

~~~java
String sql = "INSERT INTO customers (customer_name) VALUES (?)";

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"CUSTOMER_ID"})) {

    ps.setString(1, "An Nguyen");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Oracle did not return CUSTOMER_ID");
        }
        long customerId = keys.getLong(1);
    }
}
~~~

Verify this pattern against your exact ojdbc artifact and database release. If the driver does not return the column as expected, use Oracle DML RETURNING or sequence/CURRVAL per design.

### 5.4. Reading the right data type

If the key is NUMBER within Java long bounds, getLong can be used. If NUMBER has larger magnitude/scale, use BigDecimal:

~~~java
BigDecimal generatedId = keys.getBigDecimal(1);
~~~

Do not use getInt for keys that could exceed 32-bit limits. Check wasNull() if a returned column could be NULL.

### 5.5. Closing the ResultSet

getGeneratedKeys() returns a ResultSet. Close it using try-with-resources to release cursors/resources. Also close the PreparedStatement when done. Do not hold the generated-keys ResultSet longer than the transaction needs.

## 6. Oracle DML RETURNING INTO from JDBC

Oracle SQL supports RETURNING ... INTO to return values from rows just affected by INSERT, UPDATE, or DELETE. This syntax can return one or multiple columns and avoids re-querying the table.

SQL example:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, :customer_name)
RETURNING customer_id INTO :generated_id;
~~~

In SQL*Plus/PLSQL, bind variables can be used in their own syntax. In JDBC, Oracle provides extended APIs on OraclePreparedStatement.

### 6.1. Concept of registerReturnParameter

With Oracle JDBC, the general workflow is:
1. Create an OraclePreparedStatement for DML containing RETURNING ... INTO ?.
2. Register the SQL type of output binds using registerReturnParameter.
3. Set input binds.
4. Call executeUpdate().
5. Obtain the ResultSet via getReturnResultSet().
6. Read returned values and close the result set.

### 6.2. INSERT RETURNING example

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

import oracle.jdbc.OraclePreparedStatement;

String sql = """
    INSERT INTO customers (customer_id, customer_name)
    VALUES (customer_seq.NEXTVAL, ?)
    RETURNING customer_id INTO ?
    """;

try (OraclePreparedStatement ps =
         (OraclePreparedStatement) connection.prepareStatement(sql)) {

    ps.setString(1, "An Nguyen");
    ps.registerReturnParameter(2, Types.NUMERIC);

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted customer");
    }

    try (ResultSet returned = ps.getReturnResultSet()) {
        if (!returned.next()) {
            throw new SQLException("RETURNING produced no value");
        }

        long customerId = returned.getLong(1);
    }
}
~~~

This is an Oracle-specific API, not a portable API across all JDBC drivers. Import oracle.jdbc.OraclePreparedStatement and use an ojdbc version compatible with your Java runtime.

### 6.3. Returning multiple columns

SQL example:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, ?)
RETURNING customer_id, created_at INTO ?, ?
~~~

Register each output parameter by position and SQL type:

~~~java
ps.registerReturnParameter(2, Types.NUMERIC);
ps.registerReturnParameter(3, Types.TIMESTAMP);
~~~

After executeUpdate, read the two columns from getReturnResultSet(). Output bind positions must match the order in RETURNING INTO. SQL types must match the returned columns.

### 6.4. UPDATE RETURNING

Example:

~~~sql
UPDATE orders
SET status = ?
WHERE order_id = ?
RETURNING status, updated_at INTO ?, ?
~~~

Use RETURNING to fetch updated status and timestamp without issuing another SELECT. If UPDATE affects multiple rows, verify the return semantics/API of the driver and statement; single-row updates are easier to control.

### 6.5. DELETE RETURNING

Oracle also allows returning values before rows are deleted:

~~~sql
DELETE FROM orders
WHERE order_id = ?
RETURNING order_id, status INTO ?, ?
~~~

Applications can record audit/events from the returned values. Verify deleted row count and transaction permissions before committing.

### 6.6. Limitations and compatibility

- OraclePreparedStatement is an Oracle extension, introducing coupling to Oracle JDBC.
- Output binding APIs/behaviors must be verified per ojdbc version.
- DML RETURNING has restrictions with certain DML forms, triggers, views, and table structures; consult the SQL Language Reference.
- If a statement affects multiple rows, multi-row return capability depends on the DML type and API/driver; do not assume single-row examples behave identically.
- For portable applications, consider JDBC generated keys or querying a sequence on the same connection.

Never cast PreparedStatement arbitrarily if the connection/driver is not Oracle. Use connection.prepareStatement from the Oracle JDBC implementation and verify the actual driver.

## 7. Comparing ways to retrieve generated IDs

| Approach | Needs Oracle-specific API? | Gets ID before INSERT? | Extra query? | Key notes |
| --- | --- | --- | --- | --- |
| SELECT sequence.NEXTVAL then INSERT | No | Yes | No post-insert query | Same connection/transaction |
| INSERT sequence.NEXTVAL then SELECT CURRVAL | No | No | Yes | CURRVAL is per-session |
| JDBC getGeneratedKeys | Not in API; behavior depends on driver | No | No | Explicitly specify key columns |
| Oracle RETURNING INTO | Yes | No | No | OraclePreparedStatement extension |
| Identity + getGeneratedKeys | JDBC API; depends on ojdbc | No | No | Test returned columns |
| Identity + RETURNING INTO | Yes | No | No | Uses Oracle-specific API |

Practical choices:
- Application needs ID before INSERT: fetch sequence NEXTVAL.
- Schema uses sequences and portable code is desired: use NEXTVAL then CURRVAL on the same connection.
- Table uses identity and driver supports it cleanly: use getGeneratedKeys with explicit column names.
- Need multiple columns after DML or want to avoid a follow-up SELECT: use Oracle RETURNING INTO.
- Using an ORM framework: check the dialect/generator strategy supported by the framework instead of mixing mechanisms.

## 8. Transactions and connection pools

### 8.1. Sequence allocation is outside transaction rollback

Example:
1. Session fetches order_seq.NEXTVAL = 101.
2. Inserts row with ID 101.
3. Transaction rolls back.

The row is rolled back, yet the sequence does not revert to 101. The next fetch may receive 102.

This is normal behavior and must be factored into business design.

### 8.2. Multiple statements in the same transaction

Java example:

~~~java
connection.setAutoCommit(false);

try {
    long orderId = nextOrderId(connection);

    insertOrder(connection, orderId, customerId);
    insertOrderItems(connection, orderId, items);

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

INSERT order and INSERT order_items share the same ID and transaction. If a step fails, data rolls back while the sequence value remains consumed.

### 8.3. CURRVAL and pooled connections

CURRVAL belongs to the Oracle session, not a Java thread or abstract transaction object. A connection pool may hand out a different physical connection after a previous connection is returned.

Therefore:
- Execute NEXTVAL/INSERT/CURRVAL on the exact same held Connection.
- Do not close the connection between steps.
- Never store CURRVAL in a static field shared across requests.
- Never call a sequence on connection A and CURRVAL on connection B.

### 8.4. Generated keys and commit

Generated keys can be read after executeUpdate before commit. The ID has been allocated, but the row is not yet committed data visible to other sessions. Only commit confirms the transaction.

If you publish the ID to a message queue/API before commit and the transaction rolls back, downstream systems may receive an ID with no corresponding row. Use proper transaction boundaries or the outbox pattern if events must stay consistent with commits.

## 9. Batch inserts

Batch inserts reduce round trips when inserting many rows. Retrieving generated keys for batches varies by driver and DML strategy.

### 9.1. Batching with sequences in SQL

~~~java
String sql = """
    INSERT INTO order_items (item_id, order_id, product_id, quantity)
    VALUES (order_item_seq.NEXTVAL, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, orderId);
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

This is straightforward when Java does not need each generated ID back. If per-row IDs are needed, choose a supporting API/driver and verify mapping between batch results and key results.

### 9.2. Fetching sequence ranges before batching

Another approach is fetching NEXTVAL multiple times and assigning IDs to Java objects before the batch insert. You can call the sequence repeatedly or use SQL techniques to fetch multiple values appropriately. Never assume consecutive values always reflect commit order.

### 9.3. Generated keys in batches

JDBC defines generated keys, though batch key retrieval support depends on the driver. Test:
- Whether the number of returned keys matches the number of inserted rows.
- Whether key order matches batch order.
- What happens if a batch element fails.
- Whether the driver returns per-row keys during batch updates.

Without required guarantees, use explicit sequences and keep IDs in application objects for deterministic mapping.

## 10. Sequences and identity columns in migrations

### 10.1. Importing data with explicit IDs

When importing into a table with an identity column:
- GENERATED ALWAYS may reject explicit ID inserts in standard import operations.
- GENERATED BY DEFAULT allows supplying IDs.
- GENERATED BY DEFAULT ON NULL generates values when imported values are NULL.

Data Pump has transform and metadata handling options by release; check exact identity behavior prior to migration. Never modify internal ISEQ$$_... sequences directly.

### 10.2. Syncing sequences after import

If imported data preserves IDs higher than the sequence's current value, subsequent inserts can collide with primary keys. Determine the maximum imported value and advance the sequence past a safe point using a supported procedure.

Never just run ALTER SEQUENCE ... INCREMENT BY ... in production without accounting for concurrency. During synchronization, prevent other sessions from drawing sequence values or perform it during a controlled maintenance window.

### 10.3. Identity columns after import

Identity columns have internal sequences. After Data Pump import, verify:
- Column generation type.
- Identity options.
- That newly generated values exceed imported IDs.
- Primary key/unique constraints are valid.
- Legacy triggers are no longer generating duplicate IDs.
- Applications are not simultaneously supplying explicit IDs outside policy.

### 10.4. Do not assume contiguous IDs after migration

If a migration import preserves original IDs, gaps may exist. If a sequence is adjusted, the next value may jump. IDs are surrogate keys; never use them to infer row counts or business ordering.

## 11. Trigger-based sequence generators in legacy schemas

Before identity columns became common, Oracle often used sequences paired with BEFORE INSERT triggers.

Example:

~~~sql
CREATE SEQUENCE employee_seq START WITH 1 INCREMENT BY 1 CACHE 100 NOCYCLE;

CREATE OR REPLACE TRIGGER employees_bir
BEFORE INSERT ON employees
FOR EACH ROW
WHEN (NEW.employee_id IS NULL)
BEGIN
    :NEW.employee_id := employee_seq.NEXTVAL;
END;
/
~~~

The application inserts without passing EMPLOYEE_ID; the trigger assigns NEXTVAL.

Points to note:
- Triggers only fire when DML hits the table and the trigger is enabled.
- If the application passes a non-NULL ID, the WHEN condition may bypass the generator.
- Triggers can hide ID-generation logic from application SQL.
- During import/migration, triggers and sequences must be synchronized.
- Do not add both an identity column and a trigger generator to the same column without explicit design.

For new schemas, identity columns are usually cleaner. For legacy schemas or shared sequences, sequence + trigger remains a valid pattern.

## 12. JDBC type mapping and null handling

### 12.1. NUMBER and Java types

| Oracle SQL | Commonly used Java/JDBC |
| --- | --- |
| NUMBER(10,0) | long or BigDecimal |
| NUMBER(p,s) | BigDecimal when precision/scale must be preserved |
| TIMESTAMP | Timestamp or LocalDateTime per driver/API |
| VARCHAR2 | String |
| RAW | byte[] |

For large NUMBER generated keys, prefer BigDecimal if values might not fit in long. Avoid narrowing casts that risk overflow.

### 12.2. Reading NULL

ResultSet.getLong() returns 0 if the SQL value is NULL; call wasNull() to distinguish NULL from 0:

~~~java
long id = rs.getLong(1);
if (rs.wasNull()) {
    throw new SQLException("Generated key is NULL");
}
~~~

Primary keys should never be NULL, yet checking helps catch mapping/driver bugs early.

### 12.3. Bind variables

Use PreparedStatement bind variables for inputs. Never concatenate user input into SQL. For RETURNING outputs, register the exact JDBC type for each bind position.

## 13. Complete JDBC repository example

The example below demonstrates an identity column + generated keys. Transaction boundaries are managed by the service layer so multiple operations can be combined.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class CustomerRepository {
    private static final String INSERT_SQL = """
        INSERT INTO customers (customer_name)
        VALUES (?)
        """;

    public long insert(Connection connection, String customerName)
            throws SQLException {

        try (PreparedStatement ps = connection.prepareStatement(
                INSERT_SQL, new String[] {"CUSTOMER_ID"})) {

            ps.setString(1, customerName);

            int affected = ps.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                    "Expected one inserted customer, got " + affected);
            }

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException(
                        "Oracle JDBC returned no CUSTOMER_ID");
                }

                long id = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("CUSTOMER_ID was NULL");
                }
                return id;
            }
        }
    }
}
~~~

Service managing the transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        long customerId =
            customerRepository.insert(connection, "An Nguyen");

        addressRepository.insertDefaultAddress(connection, customerId);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

In production, add policies for rollback exceptions, transaction timeouts, logging, and framework exception translation. Never log sensitive data or passwords.

## 14. Common errors

| Error/symptom | Possible cause | Resolution |
| --- | --- | --- |
| ORA-08002 | Calling CURRVAL before NEXTVAL in session | Call NEXTVAL first on the same session |
| ORA-08004 | Sequence reached NOCYCLE limit | Check MAXVALUE/INCREMENT and plan expansion |
| ORA-00001 | Duplicate primary key ID | Check post-import sequence sync or explicit IDs passed by app |
| Generated keys empty | Driver did not return keys as requested | Specify column names or use RETURNING/sequence |
| Generated key is ROWID | Driver used default generated-key behavior | Pass columnNames in prepareStatement |
| ClassCastException with OraclePreparedStatement | Driver/connection is not a compatible Oracle implementation | Check ojdbc and connection provider |
| RETURNING ResultSet empty | Wrong output bind position/type or DML affected 0 rows | Check SQL, registerReturnParameter, and affected rows |
| Sequence has gaps | Rollbacks, cache loss, or fetched-but-uninserted values | Normal behavior; do not use sequence as gapless counter |
| IDs out of commit order | NEXTVAL allocation order differs from commit order | Use timestamps/separate business ordering |
| ORA-00942 when selecting sequence | Sequence missing or insufficient privileges | Check owner, synonyms, and SELECT privilege |
| Identity insert rejected | GENERATED ALWAYS while app supplied ID | Remove column from INSERT or adjust policy carefully |
| Identity import duplicate ID | Internal generator did not advance past imported values | Inspect identity metadata and adjust per procedure |
| Batch key count mismatch | Driver batch generated-keys support varies | Test driver; use explicit sequences for guaranteed mapping |

## 15. Design checklist

### Database
- Choose sequence or identity based on requirements.
- Enforce PRIMARY KEY/UNIQUE constraints.
- Choose CACHE/NOCACHE suited to throughput.
- Typically use NOCYCLE for primary keys.
- Do not rely on IDs to reflect commit order.
- Monitor sequence limits and identity metadata.
- Have a post-import generator synchronization procedure.

### JDBC
- Use PreparedStatement and bind variables.
- Choose getGeneratedKeys, RETURNING, or sequence/CURRVAL.
- For Oracle generated keys, explicitly specify returned column names.
- Verify ojdbc version and Java compatibility.
- Read generated values with the right data type.
- Close ResultSet/Statement.
- Keep the same connection when using CURRVAL.
- Manage transactions and rollbacks explicitly.

### Migration and operations
- Identify identity generation types.
- Check legacy triggers/sequences.
- Compare MAX(ID) against generator state after import.
- Test subsequent inserts after migration.
- Check unique constraints and invalid objects.
- Never manipulate internal identity sequences directly.
- Test batch inserts and connection pooling.

## 16. Lab: sequences and JDBC CURRVAL

### Step 1: Create table and sequence

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    description VARCHAR2(100) NOT NULL
);

CREATE SEQUENCE lab_order_seq
    START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;
~~~

### Step 2: Fetch NEXTVAL

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Run CURRVAL before NEXTVAL in a fresh session to observe ORA-08002.

### Step 3: Insert and fetch CURRVAL

~~~sql
INSERT INTO lab_orders (order_id, description)
VALUES (lab_order_seq.NEXTVAL, 'First order');

SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Execute both on the same session.

### Step 4: Test rollback

~~~sql
SAVEPOINT before_insert;
INSERT INTO lab_orders (order_id, description)
VALUES (lab_order_seq.NEXTVAL, 'Rollback sample');
ROLLBACK TO before_insert;
SELECT lab_order_seq.NEXTVAL FROM dual;
~~~

Observe that the sequence does not rewind on rollback.

### Step 5: Test two sessions

Open two SQL sessions and alternate calling NEXTVAL. Confirm each session receives distinct values; each session's CURRVAL reflects that session's own last NEXTVAL.

## 17. Lab: identity and generated keys

### Step 1: Create identity table

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    CONSTRAINT lab_customers_pk PRIMARY KEY (customer_id)
);
~~~

### Step 2: Insert without supplying ID

~~~sql
INSERT INTO lab_customers (customer_name)
VALUES ('Customer A');

SELECT * FROM lab_customers;
~~~

### Step 3: Test NULL and explicit values

~~~sql
INSERT INTO lab_customers (customer_id, customer_name)
VALUES (NULL, 'Customer B');

INSERT INTO lab_customers (customer_id, customer_name)
VALUES (9000, 'Imported Customer');
~~~

Confirm BY DEFAULT ON NULL generates an ID on NULL, while explicit values are accepted.

### Step 4: Inspect metadata

~~~sql
SELECT
    table_name,
    column_name,
    generation_type,
    identity_options
FROM user_tab_identity_cols
WHERE table_name = 'LAB_CUSTOMERS';
~~~

### Step 5: Run JDBC generated keys

Use the Java repository from section 13, changing table/column to LAB_CUSTOMERS/CUSTOMER_ID. Confirm getGeneratedKeys() returns the right ID with your ojdbc version.

## 18. Lab: Oracle RETURNING INTO

### Step 1: Create table and sequence

~~~sql
CREATE TABLE lab_returning (
    id NUMBER PRIMARY KEY,
    label VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE SEQUENCE lab_returning_seq START WITH 1 CACHE 20 NOCYCLE;
~~~

### Step 2: INSERT RETURNING

Use OraclePreparedStatement:

~~~java
String sql = """
    INSERT INTO lab_returning (id, label)
    VALUES (lab_returning_seq.NEXTVAL, ?)
    RETURNING id, created_at INTO ?, ?
    """;

try (OraclePreparedStatement ps =
         (OraclePreparedStatement) connection.prepareStatement(sql)) {

    ps.setString(1, "returning-demo");
    ps.registerReturnParameter(2, Types.NUMERIC);
    ps.registerReturnParameter(3, Types.TIMESTAMP);

    ps.executeUpdate();

    try (ResultSet rs = ps.getReturnResultSet()) {
        if (rs.next()) {
            long id = rs.getLong(1);
            Timestamp createdAt = rs.getTimestamp(2);
        }
    }
}
~~~

Verify the exact Oracle JDBC driver version and API signature. If the driver does not support this bind pattern, use getGeneratedKeys or sequence/CURRVAL.

### Step 3: UPDATE RETURNING

Change label or update status, using RETURNING to read post-update values. Check affected row counts and returned results.

### Step 4: Transaction

Test commit and rollback. Confirm RETURNING returns values within the active transaction while rollback still removes the row; sequence allocation is not refunded.

## 19. Lab cleanup

~~~sql
DROP TABLE lab_orders PURGE;
DROP SEQUENCE lab_order_seq;

DROP TABLE lab_customers PURGE;

DROP TABLE lab_returning PURGE;
DROP SEQUENCE lab_returning_seq;
~~~

Only run cleanup on lab schemas. Never drop sequences/tables shared by applications.

## Summary

A sequence is an independent Oracle object suited for controlling number issuance, sharing across multiple tables, or obtaining IDs before INSERT. An identity column simplifies schemas by letting Oracle auto-generate values for a column. Neither guarantees gap-free numbering; sequence allocations do not roll back with transactions, and allocation order is not commit order.

JDBC can retrieve generated keys via getGeneratedKeys(). With Oracle, explicitly specify returned column names and test on the actual ojdbc driver because default behavior may not return the primary key as expected. Oracle DML RETURNING ... INTO can return multiple values after INSERT/UPDATE/DELETE via the OraclePreparedStatement extension. When using CURRVAL, call it after NEXTVAL on the same Oracle session/connection.

Pick a consistent mechanism aligned with your schema and framework. Synchronize sequences/identities after migrations, test batching and connection pools, use bind variables, close resources, and manage transactions explicitly. Never use MAX(id)+1, and never use sequences as gapless counters for legal business documents.

## Oracle and JDBC reference documentation

- [Oracle Database SQL Language Reference — CREATE SEQUENCE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html) — sequence options, NEXTVAL, and CURRVAL.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — identity column syntax and generation types.
- [Oracle Database SQL Language Reference — INSERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html) — INSERT and RETURNING clause.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — Oracle JDBC APIs, generated keys, and DML returning.
- [Oracle JDBC API Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/) — OraclePreparedStatement, registerReturnParameter, and getReturnResultSet.
- [JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — prepareStatement, generated keys, and executeUpdate.
- [JDBC API — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html) — RETURN_GENERATED_KEYS.

When deploying on another Oracle release or JDBC driver, cross-check the matching version of the SQL Language Reference, JDBC Developer's Guide, and API Reference, especially regarding identity generation, getGeneratedKeys(), RETURNING INTO, batch updates, and driver compatibility.
