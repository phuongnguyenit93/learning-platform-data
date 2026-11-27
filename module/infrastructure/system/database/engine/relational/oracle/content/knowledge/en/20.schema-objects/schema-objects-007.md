# Identity vs. Sequences and Key Generation Strategies for Applications in Oracle Database

Each row in a table typically needs an identifier value so applications can reference, update, and join data reliably. Oracle provides two common number-generation mechanisms: **identity columns** and **sequences**. Applications can also generate keys themselves, such as UUIDs, or use existing business keys.

These mechanisms address value generation, but they do not automatically determine the entire key design. Distinguish:

- **Key generation:** creating a new identifier value.
- **Primary key/unique constraint:** ensuring values in the table do not duplicate and can serve as identifiers.
- **Business key:** a value with business meaning, such as an order code or customer code.
- **Surrogate key:** a system-generated substitute key carrying no direct business meaning.

Identity columns usually fit when a table needs a simple auto-incrementing numeric key. Sequences fit when applications need explicit control over when numbers are fetched, want to share a generator across multiple tables, or need numbers prior to INSERT. UUIDs or application-generated keys help when creating identifiers across multiple nodes or when clients operate independently of the database.

This lesson explains mechanics, syntax, trade-offs, uniqueness, gaps in number series, performance, concurrency, retrieving newly generated keys, application integration, and choosing an appropriate strategy.

## 1. Identifier Keys and Key Generation Mechanisms

### 1.1. Primary Key Is Not Synonymous with Identity

A primary key is a data integrity constraint: values must be unique and NOT NULL. Identity is a column attribute enabling Oracle to auto-generate a value upon row insertion.

Example:

```sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
```

This example contains two separate components:

- `GENERATED ALWAYS AS IDENTITY` tells Oracle to generate values for `CUSTOMER_ID`.
- `PRIMARY KEY` guarantees identifiers are unique and NOT NULL.

An identity column does not automatically eliminate the need to declare PK/UK constraints per data design. Declare explicit constraints so the database protects uniqueness even when data is loaded via applications, imports, or administrative procedures.

### 1.2. Natural Keys vs. Surrogate Keys

A **natural key** is one or more attributes inherent to the business domain, such as a book's ISBN or a country code. A **surrogate key** is a value created specifically to identify a row, such as a numeric `CUSTOMER_ID`.

| Criterion | Natural Key | Surrogate Key |
| --- | --- | --- |
| Meaning | Carries business meaning | Usually carries no business meaning |
| Stability | Can change with business rules | Should stay stable across row lifetime |
| Length | May span multiple columns or long strings | Usually small and fixed |
| Key generation | Follows business rules | Identity, sequence, UUID, or application |
| Using as PK | Fits when truly stable and unique | Usually convenient for internal relationships |
| Business constraints | Often requires its own UNIQUE | Still needs UNIQUE for business codes |

A common design uses a surrogate key as the PK and places a UNIQUE constraint on the business key. For example, `CUSTOMER_ID` is the PK, while `TAX_CODE` or a business-issued customer code gets an appropriate UNIQUE constraint.

Avoid using values that frequently change—such as email addresses or phone numbers—as a PK merely because they appear unique today.

### 1.3. Key Generation Does Not Automatically Enforce Uniqueness of All Data

Sequences and identity columns produce distinct values according to their configuration, yet tables still need constraints:

```sql
CREATE TABLE orders (
    order_id NUMBER GENERATED ALWAYS AS IDENTITY,
    order_no VARCHAR2(30) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_no UNIQUE (order_no)
);
```

`ORDER_ID` is the surrogate key. `ORDER_NO` is the business code and needs its own uniqueness rule. Never assume that because `ORDER_ID` is unique, `ORDER_NO` is also unique.

## 2. Identity Columns in Oracle

### 2.1. What Is Identity?

Identity columns were introduced in Oracle Database 12c. An identity column is a numeric column whose value Oracle generates automatically during INSERT according to the declared generation mode.

Simple example:

```sql
CREATE TABLE departments (
    department_id NUMBER GENERATED ALWAYS AS IDENTITY,
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_departments PRIMARY KEY (department_id)
);
```

INSERT does not need to supply `DEPARTMENT_ID`:

```sql
INSERT INTO departments (department_name)
VALUES ('Engineering');

INSERT INTO departments (department_name)
VALUES ('Finance');

COMMIT;
```

Oracle generates the value for the identity column automatically. Application users do not need to call `NEXTVAL` or write number-assigning triggers.

### 2.2. Three Generation Modes

Oracle supports three main declarations:

**GENERATED ALWAYS AS IDENTITY**

Oracle always generates the value. If an INSERT attempts to pass an explicit value for the identity column, the statement is rejected.

```sql
CREATE TABLE always_ids (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_always_ids PRIMARY KEY (id)
);
```

Normal INSERT:

```sql
INSERT INTO always_ids (description)
VALUES ('Generated by Oracle');
```

This fits when applications must not choose PK values manually during normal write flows.

**GENERATED BY DEFAULT AS IDENTITY**

Oracle generates a value when the column is omitted from the INSERT list or when the `DEFAULT` keyword is used. If the application supplies an explicit value, Oracle accepts it.

```sql
CREATE TABLE default_ids (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_default_ids PRIMARY KEY (id)
);
```

Example:

```sql
INSERT INTO default_ids (description)
VALUES ('Oracle generates the id');

INSERT INTO default_ids (id, description)
VALUES (9000, 'Imported id');
```

This mode is convenient for imports or migrations needing to preserve legacy IDs, but explicit values must be controlled. An explicit value could collide with an existing PK or with values Oracle generates on subsequent INSERTs.

**GENERATED BY DEFAULT ON NULL AS IDENTITY**

Oracle generates a value if the column is omitted or explicitly passed as NULL.

```sql
CREATE TABLE default_on_null_ids (
    id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_default_on_null_ids PRIMARY KEY (id)
);
```

Both statements below let Oracle generate the ID:

```sql
INSERT INTO default_on_null_ids (description)
VALUES ('Column omitted');

INSERT INTO default_on_null_ids (id, description)
VALUES (NULL, 'Explicit NULL');
```

This mode is helpful when applications routinely send NULL for unpopulated ID fields. If the application sends a non-NULL number, that value is still accepted per `BY DEFAULT` semantics.

### 2.3. Comparing the Three Modes

| Declaration | Column Omitted from INSERT | Passing NULL | Passing Explicit Number |
| --- | --- | --- | --- |
| `GENERATED ALWAYS` | Oracle generates | Oracle generates | Rejected |
| `GENERATED BY DEFAULT` | Oracle generates | NULL does not trigger generation; identity columns are NOT NULL so typically rejected | Accepted |
| `GENERATED BY DEFAULT ON NULL` | Oracle generates | Oracle generates | Accepted |

If Oracle must always control IDs, choose `GENERATED ALWAYS`. If explicit ID imports are needed, consider `BY DEFAULT`, but manage value and internal-sequence synchronization carefully. If clients may pass NULL, `BY DEFAULT ON NULL` is usually easier to integrate.

### 2.4. Configuring Identity Options

Identity columns use an Oracle-managed sequence generator. Sequence options can be specified in the identity clause:

```sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        (
            START WITH 1000
            INCREMENT BY 1
            CACHE 100
            NOCYCLE
        ),
    invoice_date DATE DEFAULT SYSDATE NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_invoices PRIMARY KEY (invoice_id)
);
```

Meaning:

- `START WITH 1000`: starting value.
- `INCREMENT BY 1`: increments by one unit each time.
- `CACHE 100`: caches a batch of values to reduce generation overhead.
- `NOCYCLE`: does not wrap back to the beginning upon reaching the limit.

If omitted, Oracle uses appropriate identity/sequence defaults. Only customize options with a clear operational rationale.

### 2.5. Only One Identity Column per Table

An Oracle table can have at most one identity column. Identity fits a single auto-generated numeric key per table. If multiple independent generators or a shared series across multiple tables are needed, explicit sequences are more flexible.

An identity column must use an appropriate numeric datatype. Choose precision/scale and value bounds sufficient for the table's lifecycle; prevent an ascending numeric key from hitting datatype limits.

### 2.6. Inspecting Identity Metadata

You can view identity columns in the schema:

```sql
SELECT table_name,
       column_name,
       generation_type,
       identity_options
FROM   user_tab_identity_cols
ORDER  BY table_name, column_name;
```

`GENERATION_TYPE` shows the generation mode; `IDENTITY_OPTIONS` displays related options. Privileges and corresponding views may vary when inspecting other schemas or multitenant environments.

Do not build applications around the internal sequence name Oracle creates for an identity column. Names like `ISEQ$$_...` are implementation details; use identity metadata to inspect configuration and target the identity column itself during INSERTs.

## 3. Explicit Sequences

### 3.1. What Is a Sequence?

A sequence is a schema object dedicated to generating numbers according to ascending/descending rules. Multiple sessions can request values from one sequence concurrently without manually locking a counter row in a table.

Create a sequence:

```sql
CREATE SEQUENCE orders_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 100
    NOCYCLE;
```

Sequences exist independently of tables. A sequence can feed IDs to one table or be shared across multiple tables if design calls for it.

### 3.2. NEXTVAL

`NEXTVAL` asks the sequence to issue a new value:

```sql
SELECT orders_seq.NEXTVAL
FROM   dual;
```

Each `NEXTVAL` call advances the sequence by `INCREMENT BY` and returns the new value. Concurrent sessions calling it simultaneously receive distinct sequence values within a non-cycling series.

Use directly in INSERT:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    total_amount
)
VALUES (
    orders_seq.NEXTVAL,
    100,
    SYSDATE,
    250000
);
```

Applications do not need a separate SELECT on the sequence before INSERT if they only need to write the row.

### 3.3. CURRVAL

`CURRVAL` returns the most recent value that the **current session** obtained from that sequence via `NEXTVAL`.

```sql
SELECT orders_seq.CURRVAL
FROM   dual;
```

A session must call `NEXTVAL` before using `CURRVAL`; otherwise, Oracle raises an error indicating the sequence is not yet defined in the current session (typically ORA-08002).

`CURRVAL` is session-local. It is not a safe way to retrieve a newly created ID if the application switches to another connection in a connection pool. For INSERTs, prefer `RETURNING INTO` to obtain the exact key of the newly inserted row.

### 3.4. Using a Sequence in SELECT for Multi-Row INSERT

A sequence can assign a value to each row of an INSERT ... SELECT statement:

```sql
INSERT INTO order_items (
    item_id,
    order_id,
    product_id,
    quantity
)
SELECT order_items_seq.NEXTVAL,
       s.order_id,
       s.product_id,
       s.quantity
FROM   staging_order_items s
WHERE  s.load_batch_id = :batch_id;
```

Each inserted row receives a new value. This is convenient for batch data loads without running an application-tier loop to allocate numbers.

### 3.5. Key Sequence Options

| Option | Meaning | Notes |
| --- | --- | --- |
| `START WITH` | Starting value | Must account for existing data |
| `INCREMENT BY` | Step size (positive or negative) | Usually 1 for PKs |
| `MINVALUE` / `MAXVALUE` | Sequence range limits | Must cover system lifetime |
| `CACHE n` | Pre-caches a batch of values | Boosts performance; cached numbers can be lost on failure |
| `NOCACHE` | Does not pre-cache values | Can hurt performance; does not eliminate all gaps |
| `CYCLE` | Wraps back to start upon reaching limit | Unsuitable for PKs needing long-term uniqueness |
| `NOCYCLE` | Does not wrap back | Commonly used for identifier keys |
| `ORDER` | Guarantees generation matches request order | Has overhead; not equivalent to COMMIT order |
| `NOORDER` | Does not enforce global request ordering | Usually preferred when throughput is priority |

For PKs, `NOCYCLE` is standard. `CACHE` generally helps performance, especially when many sessions fetch numbers concurrently. Size the cache for your workload and accept that sequences can have gaps.

### 3.6. Sequences Are Independent of Transactions

Sequences are not transactional counters:

```sql
SELECT orders_seq.NEXTVAL FROM dual;

ROLLBACK;
```

A fetched sequence value does not return to the sequence when a transaction rolls back. If you fetch 105 and roll back, the next call may receive 106. Value 105 becomes a gap.

This is intentional: Oracle does not lock and undo a sequence like a normal table row. If rollback reverted sequences, concurrent sessions could receive duplicate values or contend on counter locks far longer.

## 4. How Do Identity Columns and Sequences Differ?

### 4.1. Comparison Table

| Criterion | Identity Column | Explicit Sequence |
| --- | --- | --- |
| Declaration | On a column in CREATE TABLE | Separate CREATE SEQUENCE |
| Generation on INSERT | Oracle generates per generation mode | SQL calls NEXTVAL, column default, or trigger |
| Table binding | Bound to one identity column of one table | Can be used across multiple tables |
| Value control | ALWAYS/BY DEFAULT/BY DEFAULT ON NULL | Application decides when to call NEXTVAL |
| Fetch number before INSERT | No public NEXTVAL API for internal identity | Can fetch NEXTVAL beforehand |
| Shared number series | Not identity's purpose | Well suited |
| Triggers | No key-generation trigger needed | Can use triggers for legacy schemas |
| Simplicity | High for auto-generated PKs | More flexible, requires setup |
| Legacy integration | May require adjusting old INSERTs | Easy to keep existing sequence/trigger patterns |

Identity is built on Oracle's sequence mechanism, with Oracle managing the internal sequence. Do not directly access or alter the internal sequence instead of interacting through the identity column.

### 4.2. When to Choose Identity

Identity generally fits when:
- Each table has its own auto-generated numeric PK.
- The application only needs the ID at INSERT time.
- Sharing a single series across multiple tables is unnecessary.
- You want to avoid key-generation triggers and reduce manual configuration.
- The system runs Oracle 12c or later and the schema supports identity columns.

### 4.3. When to Choose a Sequence

A sequence fits when:
- IDs must be allocated before INSERT.
- One generator must be shared across multiple tables.
- Applications or stored procedures call `NEXTVAL` directly.
- A batch of numbers must be pre-allocated.
- Compatibility with legacy schemas using sequences/triggers is required.
- Multiple series with distinct rules are needed.

### 4.4. Identity Is Not a "Stronger" Version of a Sequence

Identity simplifies attaching a generator to a column. Explicit sequences offer greater control and reusability. Both can produce gaps, both require PK/UK constraints, and neither should be used as a gap-free contiguous document numbering mechanism when business rules impose legal numbering requirements.

## 5. Key-Generating Triggers: The Legacy Pattern

### 5.1. Sequences Combined with Triggers

Before identity columns existed, a common pattern paired a sequence with a BEFORE INSERT trigger:

```sql
CREATE SEQUENCE customers_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

```sql
CREATE OR REPLACE TRIGGER customers_bir
BEFORE INSERT ON customers
FOR EACH ROW
WHEN (NEW.customer_id IS NULL)
BEGIN
    :NEW.customer_id := customers_seq.NEXTVAL;
END;
/
```

The trigger assigns an ID when the application omits `CUSTOMER_ID`. If the application passes a non-NULL ID, the trigger in this example does not overwrite it.

### 5.2. Why Use WHEN NEW...?

The condition:

```sql
WHEN (NEW.customer_id IS NULL)
```

preserves the ability to import explicit IDs. If the trigger assigned `NEXTVAL` unconditionally, application-supplied values would be overwritten.

Even so, allowing manual IDs requires discipline. After importing large IDs, the sequence might still generate lower values and cause collisions. Resynchronize the sequence through a controlled migration procedure.

### 5.3. Drawbacks of Key-Generating Triggers

- Key-generation logic is hidden outside the INSERT statement.
- Harder to trace during debugging and testing.
- Can conflict with applications that also call the sequence directly.
- Easy to overlook during schema migrations or data copies.
- Complex triggers increase DML overhead and introduce unpredictable side effects.

For new schemas, identity is usually simpler when only an auto-generated numeric key is needed. For legacy schemas, sequence/trigger patterns can remain appropriate if applications rely on that behavior.

### 5.4. Sequence as DEFAULT Instead of a Trigger

In Oracle versions supporting sequences in column defaults, you can declare:

```sql
CREATE SEQUENCE audit_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;

CREATE TABLE audit_events (
    event_id NUMBER DEFAULT audit_seq.NEXTVAL NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_audit_events PRIMARY KEY (event_id)
);
```

An INSERT omitting `EVENT_ID` uses the default. Verify syntax and limitations for your running Oracle release. If generation is also needed when clients pass NULL, consider `DEFAULT ON NULL` if supported. Do not combine multiple number-generation mechanisms on the same column without explicit intent.

## 6. Retrieving the Newly Inserted ID

### 6.1. Using RETURNING INTO

With identity:

```sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (customer_id, total_amount)
    VALUES (100, 250000)
    RETURNING order_id INTO l_order_id;

    DBMS_OUTPUT.PUT_LINE('New order id = ' || l_order_id);
END;
/
```

`RETURNING INTO` returns the value of the newly inserted row in the same statement. Applications can bind output parameters via their corresponding driver.

### 6.2. With an Explicit Sequence

```sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        total_amount
    )
    VALUES (
        orders_seq.NEXTVAL,
        100,
        250000
    )
    RETURNING order_id INTO l_order_id;

    DBMS_OUTPUT.PUT_LINE('New order id = ' || l_order_id);
END;
/
```

You can query `CURRVAL` in the same session after calling `NEXTVAL`, but `RETURNING INTO` binds directly to the inserted row and is generally clearer and safer in applications.

### 6.3. Never Use MAX(id) to Retrieve a Newly Created Key

Incorrect approach:

```sql
SELECT MAX(order_id)
FROM orders;
```

If two sessions insert concurrently, the other session may insert a larger ID before the MAX query executes. The MAX value does not prove it is the ID inserted by the current session.

Use `RETURNING INTO`, or use a `NEXTVAL` fetched within the same session if sequence design requires it. Never query MAX to infer a new key.

### 6.4. Connection Pools and Session State

`CURRVAL` belongs to the current database session. In applications using connection pools:
- The INSERT and CURRVAL read must genuinely run on the same physical database session.
- If the pool returns a different connection, CURRVAL may be uninitialized or hold a value from another operation on that session.
- Never assume two repository/service calls always share the same session unless transactions/pooling guarantee it.

Using `RETURNING INTO` in the same DML avoids depending on session state to fetch the ID.

## 7. Gaps in Number Series and Uniqueness

### 7.1. Why Do Sequences Have Gaps?

Sequences do not promise contiguous numbering. Gaps can appear when:
- A transaction fetches NEXTVAL and then rolls back.
- An INSERT fails after the sequence issued a number.
- An application fetches a number without using it.
- A sequence caches a batch of values and the instance stops abnormally before all are used.
- Multiple sessions interleave number fetches and transactions commit out of order.
- An inserted row is later deleted.

Example:

```text
NEXTVAL -> 100
INSERT succeeds
COMMIT

NEXTVAL -> 101
INSERT fails
ROLLBACK

NEXTVAL -> 102
INSERT succeeds
COMMIT

Remaining IDs: 100, 102
```

There is nothing wrong with 101 being missing if the key only needs uniqueness.

### 7.2. Identity Columns Also Have Gaps

Identity columns rely on an internal sequence mechanism, so they can also develop gaps from rollbacks, failed INSERTs, caching, or crashes. Switching from a sequence to an identity column does not turn IDs into a contiguous series.

### 7.3. NOCACHE Does Not Guarantee Gap-Free Numbers

`NOCACHE` avoids losing a batch of cached values in certain instance failure scenarios, but it does not eliminate gaps from rollbacks, DML errors, aborted transactions, or discarded numbers.

Therefore, do not choose NOCACHE expecting contiguous numbers. It can also degrade performance when many sessions fetch sequence values concurrently.

### 7.4. Sequences Guarantee Series Uniqueness, Not Commit Ordering

Suppose:
- Session A gets 100.
- Session B gets 101.
- B commits first.
- A commits later.

The table may observe row 101 committed before row 100. A sequence reflects number allocation order, not commit order or exact business creation time.

In RAC environments, `NOORDER` lets sequences optimize throughput without guaranteeing global cross-instance request ordering. `ORDER` guarantees sequence generation follows request order, yet still does not make COMMIT order match ID order and can add overhead.

### 7.5. Do Not Use Sequences as Contiguous Invoice Numbers If Legal Rules Require Gap-Free Series

Internal PKs and business document numbers are distinct concepts. If invoices require a regulated sequence, build a dedicated design:
- Define the numbering scope (by year, branch, document type).
- Use a numbering table with appropriate serialization/locking.
- Allocate numbers only when the business action is confirmed per regulations.
- Define how voided documents and already-issued numbers are handled.
- Store audit trails to explain valid gaps.

This pattern typically trades off concurrency. Do not use a standard PK sequence expecting it to satisfy contiguous numbering requirements.

## 8. Performance and Concurrency

### 8.1. Why Do Sequences Scale Well Across Many Sessions?

A sequence is specialized for number allocation, avoiding having every session update the same counter row in a table. Oracle manages concurrent allocation and can cache values to reduce synchronization overhead.

An inefficient alternative pattern is:

```sql
SELECT next_id
FROM   id_counter
WHERE  counter_name = 'ORDERS'
FOR UPDATE;

UPDATE id_counter
SET next_id = next_id + 1
WHERE counter_name = 'ORDERS';
```

Every session contends on the same counter row. A sequence is usually far better for ascending surrogate keys.

### 8.2. CACHE and NOCACHE

`CACHE n` allows Oracle to pre-allocate a batch of sequence values, reducing repeated allocation cost. For high-throughput systems, caching is usually beneficial.

`NOCACHE` does not pre-cache values. It can slow sequences under heavy request loads and still does not guarantee a contiguous series.

Choose cache size based on:
- Frequency of NEXTVAL calls.
- Concurrent session count.
- Number of RAC instances if applicable.
- Gap tolerance.
- Performance targets and restart/recovery characteristics.

### 8.3. ORDER and NOORDER

`ORDER` requires values to be issued in sequence request order. `NOORDER` drops that ordering requirement and usually fits when throughput matters more.

Neither guarantees:
- Commit order.
- Transaction completion order.
- Absence of gaps.
- IDs reflecting exact business timestamps.

Do not enable ORDER just to make "IDs look sequential" if the application has no real requirement for generation order.

### 8.4. Indexes on Ascending Keys

PKs are typically backed by unique indexes. With ascending IDs, inserts concentrate on the right-hand edge of the B-tree index. This is standard and usually efficient, though under extremely high workloads contention can appear on hot leaf blocks or cause index block contention.

Do not change an ID strategy based on speculation alone. Measure wait events, index contention, insert rates, and execution statistics before adopting solutions like reverse key indexes or partitioning. Reverse key indexes carry their own limitations, such as being unsuitable for certain key range scans.

### 8.5. UUIDs and Index Locality

Random UUIDs scatter INSERT points across the B-tree index, reducing right-edge hot spots while potentially increasing block splits and reducing locality. Furthermore, UUIDs are usually larger than NUMBERs, inflating PK/FK and index sizes.

If UUIDs are needed for distribution, choose a consistent storage type and format. Never pick UUIDs merely assuming they are always faster than sequences.

## 9. Application-Generated Keys and UUIDs

### 9.1. When Should Applications Generate IDs?

Applications may need to generate IDs before connecting to the database:
- Data is created offline and synchronized later.
- Multiple independent services/databases generate data.
- Distributed systems avoid depending on a central sequence.
- IDs are needed in events/messages before database persistence.
- In-memory object graphs need relationships wired prior to INSERT.

In these scenarios, UUIDs or a distributed ID strategy may fit.

### 9.2. UUIDs

A UUID is a 128-bit identifier often represented as a string like:

```text
550e8400-e29b-41d4-a716-446655440000
```

Applications can generate UUIDs using standard language libraries. Independent nodes can generate IDs without calling a central sequence. Collision probability is minuscule with standard generators, yet the database should still enforce a PRIMARY KEY or UNIQUE constraint to protect uniqueness.

### 9.3. Storing UUIDs in Oracle

You can store UUIDs as `RAW(16)` to avoid the overhead of 36-byte character strings:

```sql
CREATE TABLE distributed_events (
    event_id RAW(16) NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_distributed_events PRIMARY KEY (event_id)
);
```

To let Oracle generate a GUID:

```sql
CREATE TABLE local_events (
    event_id RAW(16) DEFAULT SYS_GUID() NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    CONSTRAINT pk_local_events PRIMARY KEY (event_id)
);
```

`SYS_GUID()` returns a 16-byte RAW value. It is an Oracle-generated GUID; do not assume its format or bit layout matches every standard UUID version expected by external applications. If a specific RFC UUID version is required, use an appropriate generator and convert/store consistently.

### 9.4. RAW(16) vs. CHAR(36)

| Storage Type | Advantages | Considerations |
| --- | --- | --- |
| `RAW(16)` | Compact, omits hyphens, smaller indexes than text | Requires conversion for display or API payloads |
| `CHAR(36)` / `VARCHAR2(36)` | Human-readable, easy to log and exchange | Uses more space, needs case and format normalization |

Use `RAWTOHEX(event_id)` to display a RAW value as a hex string. If applications send UUID text, normalize casing, strip hyphens appropriately, and convert consistently with `HEXTORAW`.

### 9.5. Random UUIDs vs. Time-Ordered UUIDs

Some UUID versions embed time ordering or offer better locality than purely random UUIDs. If an application requires UUIDs under heavy insert workloads, evaluate time-ordered formats, RAW storage, and index behavior.

Never assume `SYS_GUID()` is UUID v7 or strictly time-increasing. Verify the exact properties of the generator in use.

### 9.6. Distributed IDs Beyond UUIDs

Distributed systems may use:
- IDs combining timestamp, node ID, and local sequence.
- Pre-allocated ID ranges per node.
- Snowflake-style IDs.
- Standard-library UUIDs/ULIDs.

These strategies must handle system clocks, node identification, restarts, failover, and duplicate IDs on misconfiguration. When strict distribution is not required, Oracle identity columns or sequences are usually simpler.

## 10. Key Strategies Across Application Archetypes

### 10.1. Single-Database OLTP Applications

Commonly effective pattern:
- Internal NUMBER PK via identity or sequence.
- UNIQUE constraint on business codes.
- FKs referencing the surrogate PK.
- `RETURNING INTO` to retrieve newly created IDs.

Identity usually minimizes configuration. Sequences fit if the application must pre-fetch IDs or share generators.

### 10.2. Multiple Services Writing to One Oracle Database

Options include:
- A shared sequence for an entity type.
- Separate per-table identity columns if tables are independent.
- UUIDs if IDs are generated across services before INSERT.

Never let each service maintain its own counter starting at 1 if they write into the same PK column, as collisions will occur.

### 10.3. Multiple Databases or Offline Sync

UUIDs or distributed IDs fit better when a central sequence cannot be reached. The design needs:
- Consistent, controlled generators.
- Matching datatypes/encodings across systems.
- PK/unique constraints at the destination.
- Conflict-resolution rules during synchronization.
- Idempotency rules for message/event retries.

### 10.4. Large Tables and High Insert Throughput

Cached sequences or identity columns can handle numeric PKs well. Measure index and sequence performance before switching to UUIDs or changing index structures. Use actual metrics to evaluate:
- Cache size.
- Instance count.
- Hot index blocks.
- Partitioning.
- Batch inserts.
- Index maintenance.

### 10.5. Staging Tables and Imported Data

When source data brings its own IDs:
- Keep source IDs in dedicated columns if traceability is needed.
- Generate internal surrogate PKs via identity/sequence.
- Place a UNIQUE constraint on source system + source ID if source identifiers must be unique.
- Never manually import IDs into a BY DEFAULT identity without resynchronizing the generator and checking for collisions.

Example:

```sql
CREATE TABLE imported_customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    source_system VARCHAR2(30) NOT NULL,
    source_customer_id VARCHAR2(80) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    CONSTRAINT pk_imported_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_imported_source_customer
        UNIQUE (source_system, source_customer_id)
);
```

This model decouples internal keys from source-system identifiers.

## 11. Application and ORM Integration

### 11.1. Never Retrieve IDs Using SELECT MAX

Applications should capture the ID directly from the INSERT operation:
- `RETURNING INTO` for Oracle DML.
- Driver/ORM generated-keys APIs where identity/sequences are properly supported.
- `NEXTVAL` prior to INSERT if the application explicitly manages sequences.

Never use `MAX(id)` because concurrent requests can insert newer rows between INSERT and SELECT MAX.

### 11.2. Identity Strategies in ORMs

ORMs can support strategies such as identity, sequence, or UUID. The choice affects when the ORM must execute INSERT to obtain an ID, batch INSERT eligibility, and ID pre-allocation.

- Identity: the ORM typically must execute INSERT for the database to generate the ID before receiving the key.
- Sequence: the ORM can fetch NEXTVAL upfront, assign IDs to entities, and batch INSERTs depending on framework/driver support.
- UUID: the application can assign IDs before INSERT, convenient for building object graphs or events.

Details depend on ORM, version, Oracle dialect, and JDBC driver. Never infer performance solely from strategy names; benchmark with your actual stack.

### 11.3. Using Transactions and FKs Properly

After obtaining the parent ID, the application can use it to insert child rows within the same transaction:

```sql
INSERT INTO orders (customer_id, total_amount)
VALUES (:customer_id, :amount)
RETURNING order_id INTO :order_id;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (:order_id, :product_id, :quantity);
```

If child-row insertion fails, the transaction can ROLLBACK to avoid leaving an order without line items when atomicity is required. Allocated sequence/identity values may still leave gaps after rollback.

### 11.4. Idempotency Is Not Just Having a PK

An order-creation API may be retried by a client after a timeout even though the first attempt committed. Generating a new PK on each attempt does not prevent two duplicate business orders.

Use an idempotency key or request ID protected by a UNIQUE constraint to recognize retried requests. Row identifier keys and deduplication keys serve different purposes.

## 12. Migration and Operations

### 12.1. Migrating from Sequence/Trigger to Identity

Before switching:
1. Inventory every INSERT that explicitly passes an ID.
2. Identify which triggers generate numbers.
3. Determine whether applications call the sequence directly or use CURRVAL.
4. Check existing data and maximum values.
5. Determine whether IDs must be preserved during imports/replication.
6. Verify the Oracle release supports identity columns.
7. Plan cutover, rollback testing, and deployment.

Never simply drop the trigger and add identity without auditing clients. Applications may still pass explicit IDs or query the old sequence.

### 12.2. BY DEFAULT and Imported Data

If `BY DEFAULT` is chosen, explicit IDs are accepted. After importing high values, ensure the next generated identity value will not collide with loaded rows.

Depending on Oracle version and migration method, you may need to adjust the identity generator using supported syntax. Check documentation for your exact release and test on a schema clone. Never directly modify internal `ISEQ$$_...` sequences unless Oracle documents it as a supported administrative API.

### 12.3. Existing Sequences and Starting Values

When creating a sequence for a table with existing data, choose `START WITH` to avoid colliding with existing IDs. For example, if the largest existing ID is 50000, the new sequence can start higher per migration procedures.

Never use `MAX(id)` in runtime application code to allocate IDs; querying MAX is only valid as a locked, controlled migration step to establish a starting point.

### 12.4. Backup and Restore

Sequences/identities are database metadata and must be included in export/import, schema deployment, and backup workflows. When restoring or syncing environments, verify:
- Identity generation mode.
- Sequence increment/cache/cycle settings.
- Next generated value relative to loaded data.
- Related triggers/defaults.
- PK/UK constraints.
- Sequence privileges if using explicit sequences.

## 13. Process for Selecting a Key Generation Strategy

Use these questions:

1. **Must the ID exist before INSERT?** If no, identity is usually simpler; if yes, sequences or application IDs fit better.
2. **Will one table or multiple tables share the series?** One table: identity; shared: sequence.
3. **Do multiple nodes generate data offline?** Consider UUIDs or distributed IDs.
4. **Must legacy IDs be preserved?** Consider BY DEFAULT/ON NULL or staging + mapping, with collision controls.
5. **Is contiguous document numbering required?** Design a dedicated business numbering generator rather than relying on identity/sequence PKs.
6. **Is high insert throughput required?** Benchmark identity/sequence with appropriate caching before choosing UUIDs.
7. **Are ORMs or connection pools involved?** Check strategy, driver support, and generated-key retrieval.
8. **Is the business key stable?** Even with a surrogate PK, add UNIQUE constraints on business keys where needed.

### 13.1. Recommendation Matrix

| Requirement | Commonly Appropriate Strategy |
| --- | --- |
| Auto-generated numeric PK for one table | Identity |
| Need number before INSERT | Sequence |
| Multiple tables sharing one generator | Sequence |
| Legacy schema with triggers | Sequence, or planned migration |
| Offline/distributed ID generation | UUID or distributed ID |
| Import preserving old IDs | Staging/mapping or controlled BY DEFAULT identity |
| Stable business code | Natural/business key with UNIQUE |
| Regulated document numbering | Dedicated business numbering generator |

These are guidelines for common scenarios; factor in Oracle version, frameworks, workload, and specific business rules.

## 14. Comprehensive Lab Exercises

### Exercise 1 — Create an Identity ALWAYS Table

```sql
CREATE TABLE demo_identity_always (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_identity_always PRIMARY KEY (id)
);

INSERT INTO demo_identity_always (name)
VALUES ('Alpha');

SELECT * FROM demo_identity_always;
```

Attempt to INSERT an explicit value for `ID` and observe Oracle rejecting it.

### Exercise 2 — BY DEFAULT

```sql
CREATE TABLE demo_identity_default (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    name VARCHAR2(100),
    CONSTRAINT pk_demo_identity_default PRIMARY KEY (id)
);

INSERT INTO demo_identity_default (name) VALUES ('Generated');
INSERT INTO demo_identity_default (id, name) VALUES (9000, 'Explicit');
```

Explain why the explicit value is accepted and why collisions must be controlled.

### Exercise 3 — BY DEFAULT ON NULL

```sql
CREATE TABLE demo_identity_null (
    id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    name VARCHAR2(100),
    CONSTRAINT pk_demo_identity_null PRIMARY KEY (id)
);

INSERT INTO demo_identity_null (name) VALUES ('Omitted');
INSERT INTO demo_identity_null (id, name) VALUES (NULL, 'Explicit null');
```

Observe that Oracle generates an ID for both rows.

### Exercise 4 — Create a Sequence and Use NEXTVAL

```sql
CREATE SEQUENCE demo_order_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 20
    NOCYCLE;

INSERT INTO demo_orders (order_id, description)
VALUES (demo_order_seq.NEXTVAL, 'First order');
```

Create the `DEMO_ORDERS` table first with an appropriate PK.

### Exercise 5 — CURRVAL

In the same session, call NEXTVAL first and then CURRVAL. Open a new session and try CURRVAL before NEXTVAL to observe the error. Explain the session-local scope of CURRVAL.

### Exercise 6 — Observe Gaps on Rollback

```sql
SELECT demo_order_seq.NEXTVAL FROM dual;
ROLLBACK;
SELECT demo_order_seq.NEXTVAL FROM dual;
```

Explain why the sequence does not revert to the previous value.

### Exercise 7 — Retrieve ID Using RETURNING

```sql
DECLARE
    l_id NUMBER;
BEGIN
    INSERT INTO demo_orders (order_id, description)
    VALUES (demo_order_seq.NEXTVAL, 'Returning example')
    RETURNING order_id INTO l_id;

    DBMS_OUTPUT.PUT_LINE(l_id);
END;
/
```

Explain why RETURNING is superior to SELECT MAX(order_id).

### Exercise 8 — Key-Generating Trigger

Create a sequence and a `BEFORE INSERT` trigger that assigns NEXTVAL only when ID is NULL. Test inserting while omitting ID and inserting with an explicit ID. Analyze the risk if imported values exceed the current sequence.

### Exercise 9 — Inspect Identity Metadata

```sql
SELECT table_name,
       column_name,
       generation_type,
       identity_options
FROM   user_tab_identity_cols
ORDER  BY table_name;
```

Observe the generation mode and identity options.

### Exercise 10 — Compare RAW and VARCHAR2 UUIDs

Create two test tables: one storing UUIDs in `RAW(16)`, another storing 36-character strings. Compare row/index storage and display formatting. Do not conclude performance solely from column size; benchmark with realistic data volumes and comparable workloads.

### Exercise 11 — Verify Business Keys

Create a customer table with a surrogate PK and a UNIQUE constraint on `(source_system, source_customer_id)`. Attempt to INSERT the same source key twice and observe the constraint blocking duplicates.

### Exercise 12 — Design for Distributed Applications

A service generates events offline and syncs to Oracle. Compare:
- Database-allocated sequence during sync.
- Service-generated UUID upfront.
- Distributed ID combining timestamp and node identifier.

Describe impacts on uniqueness, indexes, retries, synchronization, and operations.

## 15. Common Misconceptions

**"Identity automatically acts as a primary key."** Identity generates values; PK/UK constraints must still be declared to enforce uniqueness.

**"Sequences and identity columns always produce contiguous series."** False. Rollbacks, failed INSERTs, caching, and other factors create gaps.

**"NOCACHE eliminates all gaps."** False. NOCACHE does not eliminate gaps from rollbacks or fetched-but-unused values.

**"CURRVAL retrieves another session's ID."** False. CURRVAL returns the most recent NEXTVAL within the current session.

**"SELECT MAX(id) is a safe way to get a newly inserted ID."** False. Another session can insert a higher ID between the two statements.

**"Ascending sequences guarantee COMMITs happen in ID order."** False. Allocation order differs from transaction completion order.

**"UUIDs do not need a UNIQUE constraint."** Constraints are still needed so the database protects data integrity.

**"UUIDs are always faster than NUMBER sequences."** False. UUIDs can enlarge keys and hurt index locality; benchmark for your workload.

**"A trigger and identity should both generate numbers for the same column."** Avoid this. Pick one primary mechanism to prevent duplicate logic or accidental overwrites.

**"Sequences can replace contiguous invoice numbers."** False. Standard sequences do not promise gap-free numbering; document numbering requires dedicated business rules.

## 16. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): identity column declarations and column attributes.
- [Oracle Database SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html): START WITH, INCREMENT, CACHE, ORDER, and sequence options.
- [Oracle Database SQL Language Reference — Sequence Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sequence-Pseudocolumns.html): NEXTVAL and CURRVAL.
- [Oracle Database SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): INSERT, default values, and RETURNING.
- [Oracle Database Reference — USER_TAB_IDENTITY_COLS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_IDENTITY_COLS.html): identity column metadata.
- [Oracle Database SQL Language Reference — SYS_GUID](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_GUID.html): generating RAW GUIDs.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): constraints, indexes, and data modeling.

When choosing a key generation strategy, start from application requirements: whether IDs are needed only at INSERT, fetched beforehand, shared across multiple tables, or generated independently across multiple nodes. Identity simplifies single-table numeric PKs; sequences offer flexibility for flows controlling NEXTVAL; UUIDs or distributed IDs support distributed architectures. Regardless of the choice, declare PK/UNIQUE constraints, retrieve IDs via RETURNING or proper generated-key APIs, and never confuse internal technical keys with business codes requiring dedicated numbering rules.
