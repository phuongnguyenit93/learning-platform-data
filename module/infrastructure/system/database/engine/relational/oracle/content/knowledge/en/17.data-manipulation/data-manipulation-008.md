# Generating Keys with Sequences, Identity Columns, and Retrieving Newly Created Keys in Oracle

## 1. Why Is a Key-Generation Mechanism Needed?

When adding a new customer, order, or transaction, an application typically needs a unique identifier to distinguish that row and link it with other tables. For example, each order needs an `ORDER_ID`; order line items will reference this `ORDER_ID` via a foreign key.

In Oracle, two common mechanisms for generating auto-incrementing numeric keys are:

- **Sequence:** a database object that issues numeric values on demand. The INSERT statement explicitly calls `sequence_name.NEXTVAL`.
- **Identity column:** a column declared to auto-generate values; Oracle manages the number generator attached to that column. The application typically omits the identity column from the INSERT list.

After INSERT, the application may need to retrieve the newly generated key to write child tables or return it in an API response. Oracle supports `RETURNING ... INTO`; sequences also have `CURRVAL` within the same session after `NEXTVAL` has been called. Java/JDBC provides ways to retrieve generated keys through the driver.

Example with a sequence:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;
```

Example with identity:

```sql
INSERT INTO orders (
    customer_id,
    order_date
)
VALUES (
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;
```

In both cases, the new key is retrieved directly from the inserted row.

This lesson belongs to the **Data Manipulation** chapter and focuses on creating sequences, declaring identity columns, choosing between the two mechanisms, retrieving newly generated keys, usage in SQL/PLSQL/JDBC, transaction handling, and considerations around uniqueness, gaps in numbering, and performance.

## 2. Primary Key and Auto-Generated Values Are Two Different Concepts

An ID column is often used as a primary key, but number generation and integrity enforcement are two separate responsibilities:

- **Sequence/identity** supplies values for the column.
- **PRIMARY KEY** guarantees values are non-NULL and unique within the table.

Example:

```sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);
```

`CUSTOMER_ID` is the primary key, yet the table has no auto-generation mechanism yet. The INSERT caller must pass an ID or add a sequence/identity.

A sequence does not automatically create a constraint on a table. When using a sequence to allocate IDs, still declare PRIMARY KEY:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 50;

CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);
```

If a sequence is configured with `CYCLE`, values can wrap around into a previously used range; the primary key constraint will prevent duplicates, causing INSERT to fail. For sequences used for IDs, `NOCYCLE` is standard.

## 3. What Is a Sequence?

A sequence is an independent object in an Oracle schema dedicated to issuing numeric values on demand. Multiple sessions can share a sequence concurrently without locking the table to find the next number.

A sequence can be used for:

- Primary keys of one or multiple tables.
- Technical reference numbers.
- Event sequence numbers.
- Numbers requiring concurrent allocation.

A sequence does not inherently know which table is using it. One sequence can be referenced by multiple statements and multiple tables; therefore, if you need distinct uniqueness per table or object type, design separate rules.

### 3.1. Creating a Sequence

Illustrative syntax:

```sql
CREATE SEQUENCE order_seq
    START WITH 1000
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 50;
```

Meaning:

| Attribute | Meaning |
|---|---|
| `START WITH 1000` | The first value issued is 1000 |
| `INCREMENT BY 1` | Each call increments by one |
| `MINVALUE 1` | Minimum value of an ascending sequence |
| `NOMAXVALUE` | No explicit MAXVALUE limit; Oracle uses default ascending limit |
| `NOCYCLE` | Does not wrap around when reaching the limit |
| `CACHE 50` | Pre-caches a batch of values to reduce allocation overhead |

For ascending sequences, Oracle has default MINVALUE/MAXVALUE values when omitted. When designing systems, state key attributes explicitly so maintainers understand the numbering rules.

### 3.2. Common Sequence Attributes

| Attribute | Effect |
|---|---|
| `START WITH n` | Starting point |
| `INCREMENT BY n` | Step size (positive or negative); cannot be 0 |
| `MINVALUE n` / `NOMINVALUE` | Minimum bound or use default |
| `MAXVALUE n` / `NOMAXVALUE` | Maximum bound or use default |
| `CYCLE` / `NOCYCLE` | Whether to wrap around upon reaching the limit |
| `CACHE n` / `NOCACHE` | Number of values cached or no caching |
| `ORDER` / `NOORDER` | Whether to guarantee sequence numbers are issued in request order |

`CACHE` generally improves performance when multiple sessions request numbers concurrently. `NOCACHE` avoids reserving a batch of numbers in memory, but can increase allocation overhead. Do not choose by guesswork; base it on write load and operational requirements.

`ORDER` governs request ordering, especially in multi-instance environments; it does not guarantee transaction commit order or row read order in queries lacking `ORDER BY`. `NOORDER` is typically appropriate when strict issuance ordering is unnecessary.

### 3.3. Inspecting Sequences in the Data Dictionary

Sequences in the current schema can be viewed via `USER_SEQUENCES`:

```sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM user_sequences
WHERE sequence_name = 'ORDER_SEQ';
```

`LAST_NUMBER` in metadata should not be assumed to be the exact next `NEXTVAL` a session will receive. For cached sequences, metadata reflects the high-water mark related to cached batches, not a precise read of the next in-memory value.

If you need to inspect sequences in other schemas with appropriate privileges, use `ALL_SEQUENCES`; broader administrative privileges can query `DBA_SEQUENCES`.

## 4. NEXTVAL and CURRVAL

A sequence exposes two pseudocolumns:

- `NEXTVAL`: advances and issues the next sequence value.
- `CURRVAL`: reads the most recent value obtained by the **current session** from that sequence.

### 4.1. Fetching the Next Value with NEXTVAL

```sql
SELECT order_seq.NEXTVAL
FROM dual;
```

Each valid reference to `NEXTVAL` advances the sequence by `INCREMENT BY` and returns the new value.

If the sequence starts at 1000 and increments by 1:

| Call | Illustrative value |
|---:|---:|
| 1 | 1000 |
| 2 | 1001 |
| 3 | 1002 |

Actual values depend on whether other sessions or statements have already drawn from the sequence.

### 4.2. Reading CURRVAL

```sql
SELECT order_seq.CURRVAL
FROM dual;
```

`CURRVAL` only works after the current session has called `NEXTVAL` at least once on that sequence. If not yet called, Oracle reports:

```text
ORA-08002: sequence ORDER_SEQ.CURRVAL is not yet defined in this session
```

Valid example:

```sql
SELECT order_seq.NEXTVAL FROM dual;
SELECT order_seq.CURRVAL FROM dual;
```

Both statements must execute in the same database session. Opening a different connection starts a new session without CURRVAL defined until that session calls NEXTVAL itself.

### 4.3. CURRVAL Is Not the Most Recent Value Across the Entire Database

Suppose:

1. Session A calls `ORDER_SEQ.NEXTVAL` and receives 1000.
2. Session B calls `ORDER_SEQ.NEXTVAL` and receives 1001.
3. Session A reads `ORDER_SEQ.CURRVAL`.

Session A still receives 1000. `CURRVAL` does not change to 1001 simply because Session B fetched a newer value.

This is why `CURRVAL` is safe for reading the sequence value retrieved in your own session, yet must never be read from a different connection or arbitrary pooled connection.

## 5. INSERT with a Sequence

### 5.1. Allocating the Key in VALUES

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    status
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE,
    'NEW'
);
```

Oracle fetches a new value from `ORDER_SEQ` to assign to `ORDER_ID`. You do not need a separate SELECT NEXTVAL beforehand if you only need to insert one row and do not need the key prior to inserting.

### 5.2. Reading CURRVAL After INSERT in the Same Session

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
);

SELECT order_seq.CURRVAL AS new_order_id
FROM dual;
```

Because INSERT called `NEXTVAL` in the current session, `CURRVAL` returns the exact sequence value used by that INSERT, provided no other statement in the same session called `NEXTVAL` on that sequence in between.

In applications with multiple steps and helpers sharing a sequence, `RETURNING` is usually clearer for retrieving the key of the exact inserted row.

### 5.3. Allocating Keys for Multiple Rows with INSERT ... SELECT

```sql
INSERT INTO order_archive (
    archive_id,
    order_id,
    archived_at
)
SELECT order_archive_seq.NEXTVAL,
       o.order_id,
       SYSTIMESTAMP
FROM orders o
WHERE o.status = 'CLOSED';
```

A sequence can allocate one value per inserted row in INSERT ... SELECT. Inspect the source row count before running and ensure the target table has appropriate constraints.

### 5.4. Do Not Generate IDs with MAX(ID) + 1

Do not write:

```sql
-- Unsafe approach when multiple sessions are active:
SELECT MAX(order_id) + 1
FROM orders;
```

Two sessions can read the same MAX and compute the same next value. When both attempt to INSERT, one hits a primary key violation or race conflict.

Sequences are designed to allocate numbers concurrently without relying on scanning MAX on the table.

## 6. Retrieving the Newly Inserted Key with RETURNING INTO

`RETURNING ... INTO` is the direct way to obtain column values from the row just modified by DML. For keys generated by sequences or identity columns, this is typically the cleanest choice.

### 6.1. INSERT with Sequence and RETURNING

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    status
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE,
    'NEW'
)
RETURNING order_id INTO :new_order_id;
```

`:new_order_id` is a bind variable registered by the client or application to receive the value. In SQL*Plus/SQLcl, this can be demonstrated as:

```sql
VARIABLE new_order_id NUMBER

INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;

PRINT new_order_id
```

### 6.2. RETURNING in PL/SQL

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        order_date,
        status
    )
    VALUES (
        order_seq.NEXTVAL,
        501,
        SYSDATE,
        'NEW'
    )
    RETURNING order_id INTO v_order_id;

    DBMS_OUTPUT.PUT_LINE('New order ID: ' || v_order_id);
END;
/
```

The variable `v_order_id` receives the key assigned to the exact inserted row. The PL/SQL block does not auto-COMMIT; the transaction remains under caller control.

### 6.3. RETURNING Multiple Columns

You can retrieve multiple values:

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_created_at orders.order_date%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        order_date,
        status
    )
    VALUES (
        order_seq.NEXTVAL,
        501,
        SYSDATE,
        'NEW'
    )
    RETURNING order_id, order_date
    INTO v_order_id, v_created_at;

    DBMS_OUTPUT.PUT_LINE(
        'Order=' || v_order_id ||
        ', created=' || TO_CHAR(v_created_at, 'YYYY-MM-DD HH24:MI:SS')
    );
END;
/
```

The number of expressions in `RETURNING` must match the number of variables in `INTO`.

### 6.4. RETURNING Does Not Mean COMMIT

After INSERT and RETURNING, the application can use the retrieved key to insert child tables within the **same transaction**:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;

INSERT INTO order_items (
    order_id,
    product_id,
    quantity
)
VALUES (
    :new_order_id,
    2001,
    2
);
```

If the detail INSERT fails, you can ROLLBACK both the uncommitted order and detail rows. The allocated sequence value remains consumed; rollback does not return that number to the sequence.

## 7. What Is an Identity Column?

An identity column is a column configured by Oracle to auto-generate values. This feature is supported starting in **Oracle Database 12c Release 1 (12.1)**.

When creating a table with an identity column, applications normally do not need to create a separate sequence or call `NEXTVAL` in INSERT. Oracle manages the number generator bound to the identity column.

### 7.1. Creating a Table with GENERATED ALWAYS AS IDENTITY

```sql
CREATE TABLE customers (
    customer_id NUMBER
        GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
```

Oracle allocates `CUSTOMER_ID` automatically on INSERT. Applications cannot explicitly supply a value to a `GENERATED ALWAYS` column in a normal INSERT.

INSERT:

```sql
INSERT INTO customers (customer_name)
VALUES ('An Nguyen');
```

Omit `CUSTOMER_ID` from the column list; Oracle generates the value automatically.

### 7.2. GENERATED BY DEFAULT AS IDENTITY

```sql
CREATE TABLE products (
    product_id NUMBER
        GENERATED BY DEFAULT AS IDENTITY,
    product_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id)
);
```

With `BY DEFAULT`:

- If INSERT omits `PRODUCT_ID`, Oracle generates a value.
- If INSERT passes an explicit value, Oracle uses the provided value.
- If NULL is passed explicitly, NULL is treated as a provided value; if the column has NOT NULL/PRIMARY KEY, the operation fails rather than auto-generating a number.

Example omitting column:

```sql
INSERT INTO products (product_name)
VALUES ('Keyboard');
```

Example passing ID:

```sql
INSERT INTO products (product_id, product_name)
VALUES (9001, 'Mouse');
```

Only allow applications to pass IDs explicitly when there is a clear data management reason. Mixing manual IDs with auto-generated IDs can cause collisions if manual values fall ahead of or overlap the sequence's current range.

### 7.3. GENERATED BY DEFAULT ON NULL AS IDENTITY

```sql
CREATE TABLE tickets (
    ticket_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    title VARCHAR2(200) NOT NULL,
    CONSTRAINT pk_tickets PRIMARY KEY (ticket_id)
);
```

With `BY DEFAULT ON NULL`:

- Omit `TICKET_ID`: Oracle generates it.
- Pass NULL for `TICKET_ID`: Oracle also generates it.
- Pass an explicit number: Oracle uses that number.

Example:

```sql
-- Oracle automatically generates ticket_id:
INSERT INTO tickets (title)
VALUES ('Cannot sign in');

-- Explicit NULL also triggers generation:
INSERT INTO tickets (ticket_id, title)
VALUES (NULL, 'Payment issue');
```

### 7.4. Comparing the Three Identity Modes

| Mode | Omit column from INSERT | Pass explicit NULL | Pass explicit number |
|---|---|---|---|
| `GENERATED ALWAYS` | Oracle generates | Oracle generates per identity rules | Rejected in normal INSERT |
| `GENERATED BY DEFAULT` | Oracle generates | NULL treated as passed value; constraints may reject | Accepts passed value |
| `GENERATED BY DEFAULT ON NULL` | Oracle generates | Oracle generates | Accepts passed value |

If the application does not need to supply IDs manually, `GENERATED ALWAYS` most clearly expresses the intent to let the database manage keys.

## 8. Customizing Identity Options

Identity columns accept generator options:

```sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED ALWAYS AS IDENTITY (
            START WITH 10000
            INCREMENT BY 1
            CACHE 100
            NOCYCLE
        ),
    customer_id NUMBER NOT NULL,
    invoice_date DATE DEFAULT SYSDATE,
    CONSTRAINT pk_invoices PRIMARY KEY (invoice_id)
);
```

Options such as `START WITH`, `INCREMENT BY`, `CACHE`, `NOCYCLE`, and `ORDER` have the same meaning as sequence settings. Choose them based on system requirements; do not assume identity creates gap-free sequences.

Identity uses an internally managed Oracle sequence. The internal sequence name may appear in metadata, typically with an auto-generated name. Never reference that internal sequence directly in application code; its name and management are Oracle implementation details.

### 8.1. Viewing Identity Metadata

In the current schema:

```sql
SELECT table_name,
       column_name,
       generation_type,
       sequence_name,
       identity_options
FROM user_tab_identity_cols
WHERE table_name = 'INVOICES';
```

`GENERATION_TYPE` indicates the generation mode, while `IDENTITY_OPTIONS` describes the options. The sequence name is displayed for metadata inspection; do not treat it as a stable API.

If you need to inspect identity columns in other schemas with appropriate privileges, use `ALL_TAB_IDENTITY_COLS`; administrative privileges can query `DBA_TAB_IDENTITY_COLS`.

## 9. INSERT and Retrieving Newly Created Keys from Identity

### 9.1. Omitting the Identity Column from the INSERT List

```sql
INSERT INTO customers (
    customer_name,
    created_at
)
VALUES (
    'Binh Tran',
    SYSTIMESTAMP
);
```

Oracle automatically generates `CUSTOMER_ID`. This style does not depend on internal sequence names.

### 9.2. Retrieving the Key with RETURNING INTO

```sql
DECLARE
    v_customer_id customers.customer_id%TYPE;
BEGIN
    INSERT INTO customers (customer_name)
    VALUES ('Chi Le')
    RETURNING customer_id INTO v_customer_id;

    DBMS_OUTPUT.PUT_LINE('New customer ID: ' || v_customer_id);
END;
/
```

`RETURNING` works directly on the newly generated identity column, making it the clearest way to capture the ID for subsequent steps.

### 9.3. Using Explicit DEFAULT

You can instruct Oracle to use the column's default/generator:

```sql
INSERT INTO customers (customer_id, customer_name)
VALUES (DEFAULT, 'Dung Pham');
```

`DEFAULT` requests the column's default/generation value. For identity columns, this is the explicit way if you want to keep the column in the INSERT list without supplying a value manually.

## 10. Sequence or Identity?

| Criterion | Sequence | Identity column |
|---|---|---|
| Version | Available since early Oracle versions | From Oracle 12c Release 1 |
| Object | Independent sequence | Column bound to Oracle-managed generator |
| INSERT | Typically calls `seq.NEXTVAL` | Typically omits identity column |
| Shared across multiple tables | Yes | Each identity is bound to one table's column |
| Allocation control | Flexible, direct NEXTVAL/CURRVAL | Via identity options and column DML |
| Retrieving key after INSERT | `RETURNING`, or CURRVAL in same session | `RETURNING` or JDBC generated keys |
| Legacy schema compatibility | Very suitable | Requires Oracle 12c+ |
| Trigger-based ID assignment | Sometimes used in legacy patterns | Normally no ID trigger needed |

### 10.1. Choose a Sequence When

- The system must support Oracle versions prior to 12c.
- One sequence must issue numbers across multiple tables or object types.
- You need to fetch `NEXTVAL` before INSERT for use across multiple operations in the same transaction.
- Custom numbering rules apply, such as multiple record types sharing one series.
- Existing applications/schemas already rely on sequences and need to preserve that model.

### 10.2. Choose Identity When

- Each table has its own auto-generated key column.
- Database is Oracle 12c Release 1 or newer.
- You want to declare key-generation intent directly in table DDL.
- Applications have no need to reference an internal sequence.
- You want to avoid creating and maintaining triggers solely to assign IDs.

Identity is usually simpler for new tables. Sequences are more flexible when the generator is a shared resource or needs direct manipulation.

## 11. Triggers and Sequences in Legacy Schemas

Before identity columns existed, a common pattern paired a sequence with a `BEFORE INSERT` trigger:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 50;
```

Trigger:

```sql
CREATE OR REPLACE TRIGGER customers_bi
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    IF :NEW.customer_id IS NULL THEN
        :NEW.customer_id := customer_seq.NEXTVAL;
    END IF;
END;
/
```

If INSERT omits `CUSTOMER_ID` or passes NULL, the trigger fetches NEXTVAL and assigns it to `:NEW.CUSTOMER_ID`.

### 11.1. What Challenges Can Triggers Cause?

- The ID generation mechanism is hidden inside a trigger; someone reading INSERT does not see the ID source.
- Debugging requires checking the table, sequence, and trigger together.
- If the application supplies its own ID, it must be clear whether the trigger overwrites or preserves it.
- Triggers can be disabled during certain import/maintenance processes.
- ID allocation logic can be duplicated inconsistently across many triggers.

For new tables on Oracle 12c+, identity reduces the need to write dedicated ID triggers. On legacy schemas, sequence + trigger remains a valid and widespread pattern.

### 11.2. Do Not Attach Both a Trigger and Identity to the Same Column

If a column is already an identity column, do not add another trigger assigning IDs to that same column unless under an intentionally controlled design. Two generation mechanisms on the same column easily cause conflicts or unpredictable behavior.

## 12. Retrieving Newly Generated Keys in Java/JDBC

Java applications often need the parent row's ID to insert child rows. For example: INSERT an order, get `ORDER_ID`, then INSERT `ORDER_ITEMS` rows.

### 12.1. JDBC getGeneratedKeys with Column Name

The Oracle JDBC driver supports generated-key retrieval per its driver implementation. A common pattern requests the driver to return the key column:

```java
String sql =
    "INSERT INTO orders (order_id, customer_id, status) " +
    "VALUES (order_seq.NEXTVAL, ?, ?)";

try (PreparedStatement ps =
         connection.prepareStatement(sql, new String[] {"ORDER_ID"})) {
    ps.setLong(1, customerId);
    ps.setString(2, "NEW");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new IllegalStateException("Expected one inserted order");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated order ID returned");
        }

        BigDecimal orderId = keys.getBigDecimal(1);
        // Use orderId to insert ORDER_ITEMS in the same transaction.
    }
}
```

This pattern requires an Oracle JDBC driver supporting generated-key retrieval for your statement and version. Passing the key column name to `prepareStatement` tells the driver which column to return. Check your actual driver/version documentation, especially with identity columns or complex INSERTs.

### 12.2. RETURNING INTO via a PL/SQL Block

Another clear option is using `CallableStatement` to run a PL/SQL block with `RETURNING INTO`:

```java
String plsql = """
    BEGIN
        INSERT INTO orders (
            order_id,
            customer_id,
            status
        )
        VALUES (
            order_seq.NEXTVAL,
            ?,
            ?
        )
        RETURNING order_id INTO ?;
    END;
    """;

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.setLong(1, customerId);
    cs.setString(2, "NEW");
    cs.registerOutParameter(3, java.sql.Types.NUMERIC);

    cs.execute();

    BigDecimal orderId = cs.getBigDecimal(3);
    // Use orderId for subsequent INSERTs.
}
```

Text blocks require Java 15 or newer; on older Java versions, build the PL/SQL string by concatenating lines. This example assumes `ORDER_ID` is NUMBER and the driver supports binding OUT as NUMERIC.

With identity, omit `ORDER_ID` from the INSERT list while keeping `RETURNING order_id INTO ?`:

```java
String plsql = """
    BEGIN
        INSERT INTO orders (customer_id, status)
        VALUES (?, ?)
        RETURNING order_id INTO ?;
    END;
    """;
```

### 12.3. CURRVAL Over the Same Connection

If the INSERT used `ORDER_SEQ.NEXTVAL`, you can run:

```java
try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(
         "SELECT order_seq.CURRVAL FROM dual")) {
    if (rs.next()) {
        BigDecimal orderId = rs.getBigDecimal(1);
    }
}
```

Mandatory requirement: the INSERT and SELECT CURRVAL must use the **exact same database connection/session**, with no intervening operation in that session calling NEXTVAL on the same sequence. In a connection pool, never read CURRVAL by borrowing a new connection.

For a single-row INSERT, `RETURNING` generally depends less on session state and ties the returned key directly to the inserted row.

### 12.4. Transactions When Inserting Parent and Child Rows

```java
connection.setAutoCommit(false);

try {
    BigDecimal orderId = insertOrderAndGetId(connection, customerId);

    insertOrderItem(connection, orderId, productId, quantity);

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
```

This is an illustrative structure. `insertOrderAndGetId` and `insertOrderItem` must share the same connection. If inserting detail rows fails, rollback discards the uncommitted order too. The sequence still retains consumption of the issued value.

## 13. Sequences Do Not Guarantee Gap-Free Numbering

A common misconception is that IDs must increment `1, 2, 3, 4, 5` with zero gaps. Sequences and identity columns primarily provide likely-unique values, not a gap-free accounting numbering system.

### 13.1. Rollback Does Not Return NEXTVAL

```sql
INSERT INTO orders (order_id, customer_id)
VALUES (order_seq.NEXTVAL, 501);

ROLLBACK;
```

The inserted row is rolled back, yet the allocated NEXTVAL remains consumed. The next call will not reissue that value.

### 13.2. Transaction Errors After Fetching a Number

A sequence may issue a number before INSERT fails due to:

- Primary key violation.
- CHECK or NOT NULL violation.
- Trigger error.
- Rolled-back transaction.
- Application fetching NEXTVAL and then skipping INSERT.

Issued numbers are never refunded.

### 13.3. CACHE and Instance Failures

When using `CACHE`, Oracle pre-allocates a batch of values. If the instance shuts down abnormally, cached but unused values can be lost upon restart. Gaps larger than one unit can therefore appear.

### 13.4. Concurrent Sessions Fetching Numbers

Sessions may fetch sequence values in a different order than their INSERTs finish or COMMIT. A smaller ID does not necessarily commit earlier than a larger ID.

### 13.5. Do Not Use Sequences as Gapless Invoice Numbers if Law Requires Gapless

If business or regulatory rules demand strictly consecutive document numbers without gaps, do not assume sequences satisfy that requirement. You need a controlled business numbering process with locking and void/cancellation handling per applicable regulations. That design differs from technical table keys and carries significant concurrency cost.

## 14. Sequences and Identity in Multi-Session Environments

Sequences are designed so multiple sessions can fetch values without locking the table to find MAX(ID). For non-cycling sequences, issued values do not repeat within the sequence range per its configuration and state.

### 14.1. Uniqueness Does Not Mean Commit Order

Suppose:

1. Session A fetches ID 100.
2. Session B fetches ID 101.
3. Session B inserts and commits.
4. Session A inserts, waits, and commits later.

Row 101 commits before row 100. Therefore, never use IDs to infer exact commit chronology.

If creation time is needed, store a `CREATED_AT` column with an appropriate timestamp. If event ordering is needed, store a dedicated business timestamp or sequence attribute.

### 14.2. ORDER and NOORDER

- `NOORDER` does not guarantee global issuance order matching request arrival; typically provides better performance.
- `ORDER` guarantees sequence issuance follows request order within Oracle semantics, though it does not guarantee transaction commit order and can reduce scalability.

Use ORDER only when there is a real requirement for issuance ordering. When the goal is unique IDs, ORDER is usually unnecessary.

### 14.3. CACHE and NOCACHE

| Setting | Characteristic |
|---|---|
| `CACHE n` | Pre-allocates n values; usually lowers allocation cost and improves performance |
| `NOCACHE` | Does not cache batches; increases allocation cost and still does not prevent gaps |

`NOCACHE` does not make a sequence gap-free. Rollbacks and fetched-but-unused numbers still create gaps.

## 15. Modifying and Managing Sequences

### 15.1. Altering Sequence Attributes

```sql
ALTER SEQUENCE order_seq
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

`ALTER SEQUENCE` modifies allowed attributes of a sequence. Not every initial attribute can be changed the same way; if you need to reset the starting point or perform major reconfiguration, consult Oracle documentation for your version and deployment runbooks.

Do not alter a sequence shared across multiple applications without assessing impact.

### 15.2. Dropping a Sequence

```sql
DROP SEQUENCE order_seq;
```

Drop only after confirming no triggers, SQL statements, jobs, or applications still depend on it. `DROP SEQUENCE` does not delete table rows that already received IDs.

### 15.3. Synchronizing Sequences After Importing Data

A common scenario: importing rows with explicit IDs, then having the application continue using the old sequence. If the sequence issues numbers below the imported MAX(ID), new INSERTs will collide with the primary key.

Before adjusting, check:

```sql
SELECT MAX(order_id) AS max_order_id
FROM orders;
```

Then compare against sequence state using a controlled administrative procedure. Never arbitrarily assume `USER_SEQUENCES.LAST_NUMBER` is the exact next NEXTVAL, especially when the sequence uses CACHE.

One operational approach is pausing writers, adjusting the sequence via a controlled procedure or creating a new sequence with a safe starting point, updating references, and resuming writers. Exact steps depend on version, cache, increment, privileges, and active sessions. Never alter a sequence while applications are concurrently drawing numbers without a synchronization plan.

With identity columns, do not manipulate the internal sequence directly. Use DDL/identity management features supported by Oracle for your running version and verify against the documentation.

## 16. Viewing Identity and Sequence Metadata

### 16.1. Listing Identity Columns

```sql
SELECT table_name,
       column_name,
       generation_type,
       sequence_name,
       identity_options
FROM user_tab_identity_cols
ORDER BY table_name, column_name;
```

### 16.2. Listing Sequences in the Schema

```sql
SELECT sequence_name,
       increment_by,
       min_value,
       max_value,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM user_sequences
ORDER BY sequence_name;
```

### 16.3. Viewing a Table's Primary Key

```sql
SELECT c.constraint_name,
       cc.column_name,
       c.status
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'ORDERS'
  AND c.constraint_type = 'P'
ORDER BY cc.position;
```

Inspect both identity/sequence and PRIMARY KEY to see how the column is generated and whether a constraint protects uniqueness.

## 17. Common Errors

| Error/Symptom | Cause | Resolution |
|---|---|---|
| `ORA-08002: CURRVAL is not yet defined in this session` | Session has not called NEXTVAL yet | Call NEXTVAL in the same session before reading CURRVAL |
| `ORA-00001: unique constraint violated` | Issued ID collides with existing data or sequence drifted after import | Check PK, sequence, and import procedure |
| `ORA-32795: cannot insert into a generated always identity column` | INSERT passed explicit value for ALWAYS identity | Omit column from INSERT or use DEFAULT |
| Identity BY DEFAULT receives NULL and fails | BY DEFAULT does not replace explicit NULL with a number | Use BY DEFAULT ON NULL or omit column from INSERT |
| IDs skip numbers | Rollback, cache, DML errors, concurrent sessions | Normal sequence/identity behavior; do not assume gapless |
| CURRVAL reads wrong number | Different connection/session or another NEXTVAL ran in between | Stay in same session and prefer RETURNING |
| INSERT finishes but generated key missing | Driver/JDBC not registered or statement unsupported | Check driver, pass column name, or use RETURNING INTO |
| Larger ID does not mean later commit | Different sessions commit at independent times | Use timestamp or business ordering column |
| Sequence hits limit | Reached MAXVALUE/MINVALUE with NOCYCLE | Evaluate number range, settings, and safe expansion plan |
| Sequence collides after import | Sequence not synchronized with imported IDs | Pause writers and synchronize under control |

### 17.1. Distinguishing Sequence Errors from Primary Key Errors

A sequence can issue a number valid according to its own state, yet the table already contains that number from an import or manual ID insert. During INSERT, the PRIMARY KEY detects the collision and raises an error. A sequence does not check MAX(ID) in the table before issuing a number.

### 17.2. Do Not Work Around with MAX(ID) + 1 in Application Code

If you hit a sequence-drift error, the fix is synchronizing the sequence via a controlled procedure. Never rewrite code to `SELECT MAX(id)+1`; that introduces a race condition under concurrent requests.

## 18. Comprehensive Lab Exercise

The steps below create dedicated tables and a sequence in a practice schema. Run only if you have object creation privileges and avoid table names colliding with business tables.

### Step 1. Create a Sequence

```sql
CREATE SEQUENCE demo_order_seq
    START WITH 1000
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 20;
```

### Step 2. Create a Table Using the Sequence

```sql
CREATE TABLE demo_orders (
    order_id NUMBER
        CONSTRAINT pk_demo_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP DEFAULT SYSTIMESTAMP,
    status VARCHAR2(20)
);
```

### Step 3. INSERT with NEXTVAL

```sql
INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    501,
    'NEW'
);
```

### Step 4. Read CURRVAL in the Same Session

```sql
SELECT demo_order_seq.CURRVAL AS generated_order_id
FROM dual;
```

Run this in the exact session that executed the INSERT in Step 3.

### Step 5. INSERT and Retrieve Key with RETURNING

```sql
VARIABLE generated_id NUMBER

INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    502,
    'NEW'
)
RETURNING order_id INTO :generated_id;

PRINT generated_id
```

If your tool does not support SQL*Plus bind variable syntax, use a PL/SQL block:

```sql
DECLARE
    v_id demo_orders.order_id%TYPE;
BEGIN
    INSERT INTO demo_orders (
        order_id,
        customer_id,
        status
    )
    VALUES (
        demo_order_seq.NEXTVAL,
        503,
        'NEW'
    )
    RETURNING order_id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('Generated ID=' || v_id);
END;
/
```

### Step 6. Create an Identity Table

```sql
CREATE TABLE demo_identity_orders (
    order_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_demo_identity_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

### Step 7. INSERT and Retrieve Identity ID

```sql
DECLARE
    v_id demo_identity_orders.order_id%TYPE;
BEGIN
    INSERT INTO demo_identity_orders (customer_id)
    VALUES (504)
    RETURNING order_id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('Identity ID=' || v_id);
END;
/
```

### Step 8. Inspect Data and Metadata

```sql
SELECT *
FROM demo_orders
ORDER BY order_id;

SELECT *
FROM demo_identity_orders
ORDER BY order_id;

SELECT table_name,
       column_name,
       generation_type,
       sequence_name
FROM user_tab_identity_cols
WHERE table_name = 'DEMO_IDENTITY_ORDERS';
```

### Step 9. Test Rollback and Observe Gaps

```sql
INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    505,
    'TEST'
);

ROLLBACK;
```

Call NEXTVAL again:

```sql
SELECT demo_order_seq.NEXTVAL
FROM dual;
```

The new value keeps advancing; the value drawn in the rolled-back transaction is not returned to the sequence.

### Step 10. Clean Up Practice Objects

Only after confirming these are objects you created and data is no longer needed:

```sql
DROP TABLE demo_identity_orders PURGE;
DROP TABLE demo_orders PURGE;
DROP SEQUENCE demo_order_seq;
```

`DROP TABLE ... PURGE` drops the table and data, bypassing the recycle bin per command behavior; DDL performs an implicit commit. Never run cleanup commands on business tables or shared objects.

## 19. Key Rules to Remember

| Need | How to use |
|---|---|
| Create an independent number generator | `CREATE SEQUENCE ...` |
| Fetch a new value | `sequence_name.NEXTVAL` |
| Read the last fetched number in same session | `sequence_name.CURRVAL` after NEXTVAL |
| INSERT key from sequence | Pass `sequence_name.NEXTVAL` in VALUES |
| Get exact key of inserted row | `RETURNING id INTO ...` |
| Auto-generated column in Oracle 12c+ | `GENERATED ... AS IDENTITY` |
| Prevent application from passing IDs | `GENERATED ALWAYS` |
| Allow explicit IDs when needed | `GENERATED BY DEFAULT` |
| Explicit NULL also triggers generation | `GENERATED BY DEFAULT ON NULL` |
| Java needs generated key | JDBC `getGeneratedKeys()` per driver support or `RETURNING INTO` |
| Insert multiple child tables with new key | Retrieve ID and use within the same transaction |
| Avoid collisions across sessions | Use sequence/identity, PK, and proper binding |
| Need gap-free document numbers | Design a dedicated business numbering workflow |

## 20. Self-Check Questions

**Question 1.** Does a sequence automatically ensure the column using it is a PRIMARY KEY?

**Answer:** No. A sequence only issues numbers; you must declare a PRIMARY KEY or UNIQUE constraint for the database to enforce uniqueness.

**Question 2.** How do `NEXTVAL` and `CURRVAL` differ?

**Answer:** NEXTVAL allocates a new value; CURRVAL reads the most recent value retrieved by the current session from that sequence.

**Question 3.** Why can CURRVAL raise ORA-08002?

**Answer:** The current session has not yet called NEXTVAL on that sequence.

**Question 4.** Should you use `MAX(id)+1` to generate keys?

**Answer:** No. Multiple sessions can compute the same number; sequences/identity columns are designed for concurrent number allocation.

**Question 5.** Starting from which version does Oracle support identity columns?

**Answer:** Oracle Database 12c Release 1 (12.1).

**Question 6.** Does `GENERATED ALWAYS` allow inserting an explicit ID in a normal INSERT?

**Answer:** No. Omit the column from INSERT or use DEFAULT so Oracle generates the value.

**Question 7.** How do `BY DEFAULT` and `BY DEFAULT ON NULL` differ?

**Answer:** BY DEFAULT triggers the generator when the column is omitted; an explicit NULL is treated as a passed value. BY DEFAULT ON NULL triggers the generator both when the column is omitted and when NULL is passed.

**Question 8.** Why do sequences have gaps after a ROLLBACK?

**Answer:** NEXTVAL is a number allocation independent of transactions; rolling back a row does not refund the issued value.

**Question 9.** Does `CACHE` guarantee a continuous sequence?

**Answer:** No. Caching can skip unused values during instance crashes; rollbacks also create gaps.

**Question 10.** Does `RETURNING INTO` auto-COMMIT?

**Answer:** No. It returns values of the DML row; the transaction remains managed by the caller.

**Question 11.** Should you directly access an identity column's internal sequence by its `ISEQ$$_...` name?

**Answer:** No. That is an Oracle-managed internal detail; use the identity column and RETURNING/JDBC generated keys.

**Question 12.** Is a larger ID guaranteed to commit after a smaller ID?

**Answer:** No. Different sessions can commit in an order different from sequence allocation order.

**Question 13.** Why can a sequence cause ORA-00001 after importing data?

**Answer:** The sequence may be issuing numbers inside the range of imported IDs. Synchronize the sequence with existing data using a controlled procedure.

**Question 14.** In JDBC, why should you not fetch CURRVAL on a new connection?

**Answer:** CURRVAL is session-scoped. A new connection opens a different session that has not called NEXTVAL on that sequence.

## 21. Conclusion

Oracle offers two popular ways to generate numeric keys: **independent sequences** and **identity columns**. Sequences are invoked explicitly via `NEXTVAL`, while `CURRVAL` reads only the value issued in the current session. Identity columns are declared directly on the column with `GENERATED ALWAYS`, `GENERATED BY DEFAULT`, or `GENERATED BY DEFAULT ON NULL`; Oracle manages the underlying generator automatically. Identity is supported from Oracle 12c Release 1 onward, whereas sequences also work on legacy schemas and when a shared generator is needed.

When retrieving a newly inserted key, prefer `RETURNING ... INTO` because the returned value is tied directly to the affected row. In Java/JDBC, use generated keys as supported by the Oracle driver or a PL/SQL block with `RETURNING INTO`. Use the exact same connection when reading CURRVAL, and keep parent/child INSERTs in the same transaction when they belong to one business operation.

Finally, sequences and identity columns **do not guarantee gap-free sequences**. Rollbacks, caching, DML errors, and concurrent sessions create gaps; ID order is also not commit order. Use PRIMARY KEY to enforce uniqueness, avoid `MAX(id)+1`, and if business regulations demand gap-free document numbers, build a dedicated numbering workflow instead of treating sequences as lossless counters.
