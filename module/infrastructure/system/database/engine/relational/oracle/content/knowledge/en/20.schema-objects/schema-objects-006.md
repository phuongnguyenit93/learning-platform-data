# Sequences: NEXTVAL, CURRVAL, CACHE, ORDER, and Key Gaps in Oracle

In Oracle Database, a **sequence** is a schema object that generates a series of numbers according to declared rules. Sequences are commonly used to assign identifiers to new rows, such as order IDs, customer IDs, or transaction IDs. The two most important pseudocolumns are **NEXTVAL** and **CURRVAL**: NEXTVAL fetches the next number, while CURRVAL returns the most recent number that the current session fetched from that sequence.

Sequences are designed for concurrent number generation across multiple sessions. They are neither transactional counters capable of rollback nor tools that guarantee gap-free consecutive numbering. Consequently, the **CACHE**, **ORDER**, and **NOORDER** options affect performance, generation ordering, and the occurrence of gaps.

This lesson covers creating and using sequences, the session scope of CURRVAL, caching and RAC, causes of sequence gaps, inspecting sequences in the Data Dictionary, and choosing between sequences and identity columns based on requirements.

## 1. What Is a Sequence?

A sequence is an independent schema object that generates numeric values according to its configuration. A sequence is not inherently tied to a specific table or column. One or more SQL statements can use the same sequence; a table can also use no sequence at all.

For example, we create a sequence to generate order IDs:

~~~sql
CREATE SEQUENCE lab_order_seq
    START WITH 1001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 50
    NOORDER;
~~~

Meaning:

| Attribute | Value | Meaning |
|---|---:|---|
| START WITH | 1001 | First value generated when the sequence starts |
| INCREMENT BY | 1 | Increment added each time a number is fetched |
| MINVALUE | 1 | Minimum value for an ascending sequence |
| NOMAXVALUE | — | No explicit MAXVALUE; Oracle uses the maximum limit for the sequence type |
| NOCYCLE | — | Does not wrap back to the start upon reaching the limit |
| CACHE | 50 | Pre-caches a batch of values to reduce generation overhead |
| NOORDER | — | Does not enforce global ordering by request time |

Options are specified explicitly so readers understand the behavior. Exact defaults and limits can vary by Oracle version and sequence type; for important objects, declare configurations explicitly rather than relying on defaults.

### 1.1. A Sequence Is Not an Auto-Increment Column

A sequence only generates values. It does not automatically know which table should receive those values and does not by itself enforce uniqueness within a table. To use it as a primary key, supply NEXTVAL in INSERT and declare a PRIMARY KEY or UNIQUE constraint:

~~~sql
CREATE TABLE lab_order (
    order_id      NUMBER(12) PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    created_at    DATE NOT NULL
);

INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'An',
    SYSDATE
);
~~~

The sequence produces a value for ORDER_ID; the primary key is the constraint that guarantees no two rows share the same ORDER_ID in the table.

## 2. NEXTVAL: Fetching the Next Value

NEXTVAL instructs the sequence to issue a new value and advance the sequence by INCREMENT BY.

~~~sql
SELECT lab_order_seq.NEXTVAL
FROM dual;
~~~

If the sequence was just created with START WITH 1001, the first call returns 1001. Subsequent calls return 1002, 1003, 1004... when configured with INCREMENT BY 1.

Example:

~~~sql
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
~~~

Illustrative output:

| Call | GENERATED_ID |
|---:|---:|
| 1 | 1001 |
| 2 | 1002 |
| 3 | 1003 |

These numbers assume no other session called the sequence and the sequence was not used previously. In a concurrent system, other sessions may also fetch values between calls from the current session.

### 2.1. Using NEXTVAL in INSERT

This is the most common usage:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'Binh',
    SYSDATE
);
~~~

There is no need to query MAX(ORDER_ID) and add 1. The MAX + 1 approach can cause duplicate keys when multiple sessions read the same MAX before inserting. Sequences are designed so multiple sessions can fetch numbers without manual synchronization via table reads.

### 2.2. Using NEXTVAL in INSERT ... SELECT

A value can be generated for each inserted row:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
SELECT
    lab_order_seq.NEXTVAL,
    customer_name,
    SYSDATE
FROM lab_order_stage
WHERE import_status = 'READY';
~~~

Each row processed in the outer query block receives one sequence value according to Oracle's NEXTVAL usage rules. Do not rely on SELECT row ordering if business rules require assigning numbers in a specific order; design the source and numbering mechanism appropriately.

## 3. CURRVAL: Most Recent Value in the Current Session

CURRVAL returns the most recent value that the **current session** obtained from NEXTVAL of that sequence.

~~~sql
SELECT lab_order_seq.CURRVAL
FROM dual;
~~~

Crucial requirement: the session must have called NEXTVAL on that sequence at least once beforehand. Otherwise, Oracle raises an error:

~~~text
ORA-08002: sequence LAB_ORDER_SEQ.CURRVAL is not yet defined in this session
~~~

Correct example:

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Both statements in the same session return the same value on the CURRVAL call. CURRVAL does not advance the sequence.

### 3.1. CURRVAL Is Remembered per Session

Suppose:

- Session A calls NEXTVAL and receives 1001.
- Session B calls NEXTVAL and receives 1002.
- Session A calls CURRVAL and receives 1001.
- Session B calls CURRVAL and receives 1002.

Each session maintains its own CURRVAL state:

| Session | NEXTVAL Received | CURRVAL Returned |
|---|---:|---:|
| A | 1001 | 1001 |
| B | 1002 | 1002 |

Session A's CURRVAL does not change simply because session B called NEXTVAL. This is why CURRVAL is useful when a session has just obtained a new ID and needs to reuse that ID within the same session.

### 3.2. COMMIT and ROLLBACK Do Not Reset CURRVAL

Sequence state is not transactional the way table data is:

- COMMIT does not clear the value CURRVAL holds.
- ROLLBACK does not revert the sequence to a previous number.
- CURRVAL remains the session's most recent NEXTVAL until the session calls NEXTVAL again or ends.

A sequence issues numbers independently of whether the transaction containing an INSERT commits or rolls back.

## 4. Using NEXTVAL and CURRVAL in the Same Statement

Within a query block, when NEXTVAL is referenced multiple times for the same processed row, Oracle increments the sequence once for that row and all corresponding sequence references in the row receive the same new value. CURRVAL in that same context returns the current value just generated by NEXTVAL.

Illustrative example:

~~~sql
SELECT
    lab_order_seq.NEXTVAL AS new_value,
    lab_order_seq.CURRVAL AS current_value
FROM dual;
~~~

In a valid session, both columns in the result row reflect the same newly issued value. For clarity when learning and to avoid depending on reference positioning within complex SQL, you can split it into two statements:

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

### 4.1. Retrieving the Newly Inserted ID

In the same session, after INSERT:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'Chi',
    SYSDATE
);

SELECT lab_order_seq.CURRVAL AS inserted_order_id
FROM dual;
~~~

CURRVAL reports the most recent sequence value fetched by the session. In applications, if you need the exact value of the row just inserted, the RETURNING INTO clause is often clearer:

~~~sql
DECLARE
    v_order_id lab_order.order_id%TYPE;
BEGIN
    INSERT INTO lab_order (
        order_id,
        customer_name,
        created_at
    )
    VALUES (
        lab_order_seq.NEXTVAL,
        'Dung',
        SYSDATE
    )
    RETURNING order_id INTO v_order_id;

    DBMS_OUTPUT.PUT_LINE('Inserted order: ' || v_order_id);
END;
/
~~~

RETURNING retrieves the value directly from the affected row. This helps when triggers or other logic might also consume the sequence, since CURRVAL always reflects only the most recent NEXTVAL in the session.

## 5. NEXTVAL Is Not Undone with a Transaction

This is the single most common cause of key gaps.

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
-- Suppose it returns 1004.

ROLLBACK;

SELECT lab_order_seq.NEXTVAL FROM dual;
-- The next value is 1005, not reverting to 1004.
~~~

ROLLBACK undoes only transactional data changes. Fetching a number from a sequence is not undone. Value 1004 was issued and is not re-issued merely because the transaction rolled back.

Similarly, if an INSERT calls NEXTVAL and then violates a constraint, the INSERT rolls back at the statement level, yet the advanced sequence does not step backward:

~~~sql
-- Suppose order_id 1005 already exists.
INSERT INTO lab_order (order_id, customer_name, created_at)
VALUES (1005, 'E', SYSDATE);
-- May raise a unique/primary key error.

SELECT lab_order_seq.NEXTVAL FROM dual;
~~~

This example intentionally uses a potentially duplicate ID to illustrate an INSERT failure. A sequence value generated in a failed statement can still be consumed; never rely on rollback to reclaim numbers.

### 5.1. Why Are Sequences Non-Transactional?

Sequences are designed to issue values rapidly to many concurrent sessions without locking a counter row in a table and waiting for transaction commits. If a sequence had to roll back whenever a transaction rolled back, Oracle would have to synchronize reclaiming issued numbers across all active sessions. That would add complexity and severely degrade concurrency.

Therefore, sequences prioritize concurrency safety and throughput. **Contiguity is not a guarantee of sequences.**

## 6. CACHE and NOCACHE

CACHE instructs Oracle to pre-allocate a batch of sequence values in memory to reduce generation overhead. NOCACHE does not pre-allocate such a batch.

Example:

~~~sql
CREATE SEQUENCE lab_cached_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOORDER
    NOCYCLE;
~~~

Oracle can pre-prepare a range of values for the sequence so NEXTVAL calls do not repeat the same dictionary management work every time. CACHE generally improves performance when a sequence is used frequently.

### 6.1. Caching Does Not Mean Rows Were Inserted

If a sequence uses CACHE 100, that does not mean Oracle created 100 table rows or committed 100 values. The cache is a pool of values managed for number generation; values are returned only as applications invoke NEXTVAL.

### 6.2. Unused Cached Numbers Can Be Lost

Suppose a sequence caches values 1 through 100. Sessions fetch only up to 12 when the instance shuts down or crashes. Remaining cached numbers can be discarded. After the instance restarts, the sequence resumes from the next reserved range; the result can jump past 100.

Model:

~~~text
Allocated cache: 1 ... 100
Application has fetched: 1 ... 12
                       |
                       v
              Instance shutdown/crash
                       |
                       v
           Unused cached numbers are discarded
                       |
                       v
       Next allocation may resume from 101
~~~

This gap is normal CACHE behavior. It does not mean table rows were deleted or that transactions committed the remaining numbers.

### 6.3. Does NOCACHE Eliminate Gaps?

No. NOCACHE avoids losing a batch of unused numbers from an abandoned cache, but it does not eliminate gaps caused by:

- A transaction fetching NEXTVAL and rolling back.
- An INSERT using NEXTVAL failing.
- An application fetching a number and discarding it.
- A statement generating multiple numbers while storing only a subset due to application logic.
- A sequence being altered, restarted, or reconfigured.

NOCACHE can also increase sequence management overhead and lower throughput. Never choose NOCACHE under the assumption that it produces gap-free numbers.

### 6.4. What Cache Size Is Appropriate?

There is no single optimal cache size for every system:

- Infrequently used sequences: a small cache may suffice.
- High-frequency sequences: larger caches generally reduce generation contention.
- RAC applications: additionally consider cache distribution across instances and the ORDER option.
- Frequently restarted systems: large caches can make post-restart jumps wider.

Choose cache size based on throughput, instance count, restart frequency, and gap tolerance. Never treat cache size as a contiguous business numbering mechanism.

## 7. ORDER and NOORDER

ORDER and NOORDER specify requirements on number generation ordering.

- **ORDER** guarantees sequence numbers are generated in the order requested.
- **NOORDER** does not require enforcing that global ordering; Oracle can optimize generation, especially when multiple instances share the sequence.

Example:

~~~sql
CREATE SEQUENCE lab_ordered_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50
    ORDER
    NOCYCLE;
~~~

And:

~~~sql
CREATE SEQUENCE lab_unordered_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50
    NOORDER
    NOCYCLE;
~~~

### 7.1. ORDER Does Not Mean Commit Ordering

Suppose session A gets 10 before session B gets 11. Session A might perform more work and COMMIT after session B. Therefore:

| Event | Session A | Session B |
|---|---|---|
| Fetch NEXTVAL | 10 | 11 |
| Finish DML | Slower | Faster |
| COMMIT | After B | Before A |

Even when the sequence uses ORDER, 10 can still commit after 11. ORDER controls the sequence generation order per request, not:

- Order in which INSERTs finish.
- Order of COMMITs.
- Order in which clients receive responses.
- Row order returned by SELECT without ORDER BY.

If a report needs rows displayed in ascending ID order, specify ORDER BY in the query reading the data.

### 7.2. NOORDER in RAC

In Oracle RAC, multiple instances access the same database. With NOORDER, each instance can use its own sequence cache range. Thus values returned across the cluster may not follow ascending global request time.

Illustrative example:

~~~text
Instance 1 cache: 1 ... 100
Instance 2 cache: 101 ... 200

Instance 2 issues: 101, 102
Instance 1 issues: 1, 2
~~~

Values remain unique under a properly configured sequence, though observed order across instances is not strictly increasing. This trade-off is usually acceptable when the sequence serves solely as a surrogate identifier.

### 7.3. ORDER in RAC Has Overhead

If an application genuinely requires request-time ordering across instances, ORDER may require cross-instance coordination and add synchronization overhead. For heavily used sequences, this can limit scalability.

Choose ORDER only when business requirements truly demand generation ordering. Never enable ORDER just to make IDs look contiguous; ORDER does not eliminate gaps.

## 8. Comparing CACHE/NOCACHE and ORDER/NOORDER

| Option | Primary Effect | Benefit | Limitation |
|---|---|---|---|
| CACHE n | Pre-allocates n values | Typically raises throughput, lowers generation cost | Unused values can be lost on instance shutdown |
| NOCACHE | Does not retain a memory value cache like CACHE | Avoids losing an unused cached range | Does not prevent gaps from rollbacks/errors; can be slower |
| ORDER | Guarantees generation order matches request order | Useful when global generation ordering is required | Can add synchronization overhead, especially in RAC |
| NOORDER | Does not enforce global ordering | Typically better for performance and RAC | Cannot infer cluster-wide request order from values |

CACHE/NOCACHE and ORDER/NOORDER are independent choices. For instance, CACHE 100 NOORDER is typically appropriate for surrogate identifiers; NOCACHE ORDER may be chosen for a specific requirement, yet it still does not produce a gap-free sequence.

## 9. Why Do Sequences Have Key Gaps?

Gaps can occur even when there are no errors in Oracle. Sequences are built to issue numbers, not to guarantee contiguous sequences.

### 9.1. Fetching NEXTVAL Followed by ROLLBACK

~~~sql
INSERT INTO lab_order (order_id, customer_name, created_at)
VALUES (lab_order_seq.NEXTVAL, 'An', SYSDATE);

ROLLBACK;
~~~

The order row is rolled back, yet the NEXTVAL value was consumed. The next INSERT receives the following value.

### 9.2. Failed INSERT

An INSERT may fetch NEXTVAL and then fail due to a unique constraint, check constraint, foreign key, or other error. Statement rollback does not step the sequence back.

### 9.3. Application Fetches a Number Without Using It

Example:

~~~sql
SELECT lab_order_seq.NEXTVAL
FROM dual;
~~~

If an application fetches a number to check and then discards it, that number has still been issued. An INSERT is not needed for a sequence to advance.

### 9.4. Cache Discarded on Instance Shutdown

Unused cached values can be lost when an instance shuts down or crashes. Upon restart, the sequence may resume from a higher range.

### 9.5. Multiple Sessions and Multiple Instances

Multiple sessions concurrently fetch numbers, while some transactions roll back or discard values. With RAC and NOORDER, per-instance caches also cause observed ordering to differ from global ascending order.

### 9.6. Sequence Configuration Changes

ALTER SEQUENCE or administrative operations like restart/recreate can alter the sequence progression according to the new configuration. In operations, control changes to START/INCREMENT/MIN/MAX/CYCLE and do not assume old sequences continue under prior rules.

## 10. Gaps Do Not Mean Lost Data

Suppose the orders table contains these IDs:

| ORDER_ID | CUSTOMER_NAME |
|---:|---|
| 1001 | An |
| 1002 | Binh |
| 1005 | Chi |

The absence of 1003 and 1004 does not prove two orders were deleted. Those numbers may have been allocated to rolled-back transactions, failed INSERTs, or unused session calls.

To know which orders were created or deleted, query business tables and audit/history logs. Never compare ID ranges to infer record counts or successful transaction counts.

Example:

~~~sql
SELECT COUNT(*) AS order_count,
       MIN(order_id) AS min_order_id,
       MAX(order_id) AS max_order_id
FROM lab_order;
~~~

MAX(ORDER_ID) - MIN(ORDER_ID) + 1 does not necessarily equal COUNT(*), because sequences can have gaps and tables can undergo deletions.

## 11. Do Sequences Guarantee Uniqueness?

A sequence supplies distinct values according to its configuration and concurrent allocation mechanics, but it does not replace a uniqueness constraint in the table.

To use a sequence as a primary key:

~~~sql
CREATE TABLE lab_customer (
    customer_id NUMBER(12) PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE SEQUENCE lab_customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 100
    NOORDER;

INSERT INTO lab_customer (customer_id, customer_name)
VALUES (lab_customer_seq.NEXTVAL, 'An');
~~~

The PRIMARY KEY guarantees the table does not contain two rows with the same CUSTOMER_ID. NOCYCLE prevents the sequence from wrapping back to old ranges upon reaching its limit. With CYCLE, values can repeat after reaching the limit; never use a cycling sequence as a long-term unique key without extra design to handle reuse.

If a sequence is dropped/recreated or reconfigured into an already-used number range, key collisions can occur. Sequence administration must inspect actual table data and constraints, not just LAST_NUMBER.

## 12. CYCLE and NOCYCLE Configurations

- **NOCYCLE**: the sequence stops when it reaches MAXVALUE or MINVALUE; subsequent NEXTVAL calls raise an error when no more values exist in the increment direction.
- **CYCLE**: the sequence wraps back to MINVALUE or MAXVALUE according to increment direction upon reaching the limit.

Small sequence example for observation:

~~~sql
CREATE SEQUENCE lab_cycle_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 3
    CYCLE
    NOCACHE
    NOORDER;
~~~

NEXTVAL calls cycle through 1, 2, 3 and wrap back to 1 per configuration. Because values repeat, do not use a CYCLE sequence as a simple primary key if old values remain in the table.

NOCYCLE example:

~~~sql
CREATE SEQUENCE lab_nocycle_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 3
    NOCYCLE
    NOCACHE
    NOORDER;
~~~

After issuing 1, 2, 3, the next NEXTVAL call cannot continue and Oracle reports that the sequence reached its limit. NOCYCLE guards against automatic number reuse, though it does not create a gap-free sequence.

## 13. Negative INCREMENT BY and Descending Sequences

Sequences can ascend or descend:

~~~sql
CREATE SEQUENCE lab_countdown_seq
    START WITH 10
    INCREMENT BY -1
    MINVALUE 1
    MAXVALUE 10
    NOCYCLE
    NOCACHE
    NOORDER;
~~~

Values are issued as 10, 9, 8... down to 1. When the sequence reaches its lower bound, NOCYCLE stops it. Ensure MINVALUE/MAXVALUE align with the increment direction.

Most surrogate keys use ascending sequences. Descending sequences fit only specialized requirements and require careful checks against collisions with existing data.

## 14. Changing Configuration with ALTER SEQUENCE

Certain attributes can be modified:

~~~sql
ALTER SEQUENCE lab_order_seq
    INCREMENT BY 1
    CACHE 200
    NOORDER
    NOCYCLE;
~~~

Adjustable attributes include INCREMENT BY, MINVALUE/MAXVALUE, CYCLE/NOCYCLE, CACHE/NOCACHE, and ORDER/NOORDER, subject to version rules and sequence state. Changing configuration alters generation behavior; review applications using the sequence.

Do not assume ALTER SEQUENCE can arbitrarily reset START WITH on an existing sequence. Sequence restart capability and syntax depend on Oracle version; before altering current values, check your release documentation and verify there is no collision with stored keys.

### 14.1. Dropping a Sequence

~~~sql
DROP SEQUENCE lab_order_seq;
~~~

DROP SEQUENCE removes the sequence object. It does not delete rows in tables holding values issued by the sequence. If a sequence is recreated with START WITH lower than existing keys, subsequent INSERTs can violate the primary key.

## 15. Inspecting Sequence Configuration in the Data Dictionary

In the schema owning the sequence, query USER_SEQUENCES:

~~~sql
SELECT
    sequence_name,
    min_value,
    max_value,
    increment_by,
    cycle_flag,
    order_flag,
    cache_size,
    last_number
FROM user_sequences
WHERE sequence_name = 'LAB_ORDER_SEQ';
~~~

Key columns to inspect:

| Column | Meaning |
|---|---|
| SEQUENCE_NAME | Sequence name |
| MIN_VALUE / MAX_VALUE | Configured bounds |
| INCREMENT_BY | Step increment/decrement |
| CYCLE_FLAG | Whether cycling is enabled |
| ORDER_FLAG | Whether ORDER is enforced |
| CACHE_SIZE | Cache size |
| LAST_NUMBER | Next number / cache boundary recorded in the dictionary |

### 15.1. Be Careful Reading LAST_NUMBER

For cached sequences, LAST_NUMBER is not necessarily the next NEXTVAL value a session will receive. Oracle may record a cache boundary higher than the most recently issued value to reserve the next range. Therefore, never use LAST_NUMBER to claim the exact "next number that will be inserted."

This is also why after a restart, a sequence can jump to a range higher than the last value an application saw.

To check the current session's value after the session has called NEXTVAL, use CURRVAL in that same session. CURRVAL is not a global value across all sessions.

## 16. Sequences in RAC and Scalability

In Oracle RAC, multiple instances serve the same database. Sequences must support concurrent sessions across multiple instances fetching numbers.

### 16.1. NOORDER and Per-Instance Caching

With NOORDER, instances can use separate cache ranges. This avoids global ordering coordination and usually improves scalability. Values issued across instances may appear interleaved over time.

### 16.2. ORDER Requires Global Ordering

ORDER requires the sequence to issue numbers in request order. In RAC, this can require cross-instance coordination and add synchronization overhead. Use it only when generation order is a genuine business requirement, not merely to avoid gaps.

### 16.3. Scalable Sequences

Newer Oracle releases include sequence options tailored for very high concurrency workloads, such as scalable sequences using SCALE. These sequences encode instance/session information into part of the generated value to reduce contention. Values may no longer look like simple unit-incremented readable series.

When using SCALE or EXTEND, consult documentation for your exact Oracle version and check column length/precision limits, uniqueness, application compatibility, and display formatting. Never apply advanced syntax to older Oracle environments without verifying release support.

## 17. Sequences vs. Identity Columns

Oracle introduced identity columns in Oracle Database 12c. Identity columns let you declare auto-generated column values directly in DDL:

~~~sql
CREATE TABLE lab_identity_order (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        (START WITH 1 INCREMENT BY 1 CACHE 50),
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    created_at DATE NOT NULL,
    CONSTRAINT pk_lab_identity_order PRIMARY KEY (order_id)
);
~~~

Two common modes:

- GENERATED ALWAYS AS IDENTITY: Oracle always generates the identity value; users cannot arbitrarily supply a value for the column in a normal INSERT.
- GENERATED BY DEFAULT AS IDENTITY: Oracle generates a value when INSERT omits the column; applications can supply an explicit value per mode rules.

A variant is GENERATED BY DEFAULT ON NULL AS IDENTITY, allowing Oracle to generate a value when the column is omitted or passed as NULL.

| Criterion | Explicit Sequence | Identity Column |
|---|---|---|
| Usage | Call NEXTVAL in SQL/PLSQL | Oracle populates the column automatically |
| Shared across multiple tables | Yes | Identity is bound to a table column |
| Direct sequence control | Yes | Managed via identity properties and an Oracle-managed internal sequence |
| Gaps on rollback/cache? | Yes | Can occur |
| Best suited for | Multiple objects sharing a generator or custom generation logic | Standard auto-generated key columns |

Identity columns are typically backed by an internal sequence mechanism; do not assume they produce gap-free numbers. For technical identifier keys, both sequences and identity columns are valid choices depending on design.

## 18. Why Not Use Sequences for Mandatory Contiguous Document Numbers?

Technical identifier keys and business document numbers serve different purposes.

- Identifier keys distinguish rows and support JOINs/constraints.
- Document numbers may need to follow numbering rules by year, branch, document type, or audit regulations.

Sequences can develop gaps from rollbacks, errors, cache loss, and concurrency. Neither ORDER nor NOCACHE eliminates all those causes. Consequently, if the business requires strictly contiguous document numbering, do not default to standard sequences.

One approach is a scoped business numbering table (for example by document type and year) locked during issuance, incrementing numbers only inside the issuing transaction and tracking cancellations via status/logs. This creates a serialization point, can reduce throughput, and still requires clear rules for issued documents that are later voided. Legal rules vary by industry and jurisdiction; design according to specific compliance requirements.

Never reuse an already-issued number just to fill a gap if audit regulations require preserving a trail. Many systems keep voided documents with a CANCELLED status instead of deleting rows to account for missing numbers.

## 19. Common Errors When Using Sequences

| Symptom | Cause | Resolution |
|---|---|---|
| ORA-08002 | Session called CURRVAL before calling NEXTVAL | Call NEXTVAL in the same session first |
| ORA-08004 | Sequence reached MAXVALUE/MINVALUE with NOCYCLE | Review limits, increment, and sequence strategy |
| ORA-00001 on INSERT | Sequence reconfigured, cycled/restarted, or existing key collision | Check PK, existing data, and sequence configuration |
| ID jumps after ROLLBACK | NEXTVAL is non-transactional | Normal behavior; do not attempt to roll back sequences |
| ID jumps after restart | Unused cache discarded | Accept gaps or tune cache per operational needs |
| IDs out of commit order in RAC | NOORDER or transactions finishing in different order | Do not use sequence IDs as commit clocks; use timestamps/audit |
| LAST_NUMBER exceeds last used ID | Dictionary reflects cache boundary | Do not treat LAST_NUMBER as the exact next value |
| Interleaved ranges across multiple tables | Multiple sessions/tables share one sequence | Define allocation scope clearly; use separate sequences if isolation is needed |

## 20. Practice Exercises

### Exercise 1 — Create a Sequence and Fetch NEXTVAL

Create a sequence starting at 500, incrementing by 1, NOCYCLE, CACHE 20, and NOORDER. Call NEXTVAL five times.

**Question:** What values are returned if no other session uses the sequence?

### Exercise 2 — Session-Scoped CURRVAL

Open two sessions A and B. A calls NEXTVAL; B calls NEXTVAL; then both call CURRVAL.

**Question:** Why does CURRVAL in A not change when B fetches a new number?

### Exercise 3 — ROLLBACK and Gaps

INSERT a row using NEXTVAL and then ROLLBACK. INSERT the next row.

**Question:** Why does the second row's ID not revert to the value used in the rolled-back transaction?

### Exercise 4 — CACHE and NOCACHE

Create two sequences, one with CACHE 50 and one with NOCACHE. Inspect metadata in USER_SEQUENCES. Discuss what can happen to cached ranges during an instance restart.

### Exercise 5 — ORDER and NOORDER

Create two sequences with the same START/INCREMENT, one ORDER and one NOORDER. Compare their configurations in USER_SEQUENCES.

**Question:** Does ORDER guarantee transactions commit in number order?

**Answer:** No. ORDER governs number generation order, not COMMIT order.

### Exercise 6 — NOCYCLE and CYCLE

Create a sequence with MINVALUE 1 MAXVALUE 3, testing NOCYCLE and CYCLE in turn.

**Question:** What happens after all three numbers are issued? Which configuration can reuse old values?

### Exercise 7 — Sequence as a Primary Key

Create a table with a PRIMARY KEY, create a sequence, and INSERT several rows. Then try inserting an ID that already exists.

**Question:** How do the roles of a sequence and a primary key differ?

**Guided answer:** the sequence generates values; the primary key enforces uniqueness in the table.

### Exercise 8 — LAST_NUMBER

Read LAST_NUMBER of a large-cache sequence after calling NEXTVAL a few times.

**Question:** Why should LAST_NUMBER not be relied upon as the exact next value?

### Exercise 9 — Sequence or Identity?

Design an orders table and an order details table. Decide whether to use an explicit sequence or an identity column for the order key, and explain whether the choice eliminates gaps.

### Exercise 10 — Contiguous Document Numbers

A system requires invoice numbers where every skipped number can be accounted for. Propose a numbering and document-status management model, explaining why sequence CACHE/ORDER/NOCACHE is insufficient to guarantee a gap-free series.

## 21. Sequence Configuration Decision Process

Before creating a sequence, answer these questions:

1. Is the sequence for a technical identifier key or a business number?
2. Will one table or multiple tables share the sequence?
3. Is global generation ordering required, or only unique values?
4. Does the system run on a single instance or RAC?
5. What is the expected generation throughput?
6. What level of gaps is acceptable?
7. Should it CYCLE or stop upon reaching its limit?
8. Is NOCACHE needed for an operational requirement, and is its cost understood?
9. Can an identity column simplify DDL?
10. Is a PRIMARY KEY/UNIQUE constraint protecting the target column?

Selection guide:

| Requirement | Configuration Typically Considered |
|---|---|
| Standard identifier key, medium/high workload | CACHE, NOORDER, NOCYCLE |
| Identifier key in RAC | CACHE, NOORDER is usually a sound starting point |
| Generation ordered by request | ORDER after evaluating synchronization cost |
| Reduce risk of losing cache range on restart | NOCACHE, while still accepting gaps from rollbacks/errors |
| Ensure series never wraps around | NOCYCLE with appropriate bounds |
| Auto-generated column in a single table | Consider identity column |
| Document numbers requiring gap accountability | Design a separate business numbering generator and audit trail |

Diagram:

~~~text
Identify numbering purpose
          |
          v
Surrogate key or business number?
       /                 \
  Identifier           Business
      |                    |
      v                    v
Sequence / Identity   Design issuing rules
      |               and audit per business policy
      v
Single instance or RAC?
      |
      v
Need global generation order?
      |                 |
     No                Yes
      |                 |
      v                 v
   NOORDER             ORDER
      |                 |
      +--------+--------+
               |
               v
        Choose CACHE/NOCACHE
               |
               v
        Choose CYCLE/NOCYCLE
               |
               v
     Protect column with PK/UNIQUE
               |
               v
       Check gap tolerance and operations
~~~

A sequence is a transaction-independent number generator. NEXTVAL fetches a new number; CURRVAL remembers the most recent number in the session; CACHE optimizes allocation; ORDER controls generation request order. ROLLBACK does not reclaim issued numbers, caches can lose unused values, and NOORDER in RAC does not guarantee global ordering. Therefore, sequences are well suited for scalable identifier keys, while document numbers requiring strict contiguity must be managed through dedicated business rules and controls.
