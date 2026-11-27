# Unindexed Foreign Keys and Contention on Parent-Child Data

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Locking and Concurrency  
> **Objective:** Understand the role of indexes on foreign key columns in child tables in Oracle; explain why DELETE or updating a referenced key on the parent table can cause a table-level lock on the child table when the foreign key is unindexed; distinguish TM locks from TX row locks; design indexes for single-column and composite foreign keys; recognize blocking, deadlocks, and index maintenance overhead; verify using two sessions and dictionary/performance views.

## 1. The problem: operations on a parent can impact the child table

Consider two tables:

- PARENT: stores parent entities, each row having a unique key.
- CHILD: stores child entities referencing the parent via a foreign key.

Example:

~~~sql
CREATE TABLE departments (
    department_id NUMBER CONSTRAINT pk_departments PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);

CREATE TABLE employees (
    employee_id NUMBER CONSTRAINT pk_employees PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
);
~~~

The PRIMARY KEY of DEPARTMENTS is backed by a unique index. However, Oracle **does not automatically create an index on the foreign key column in the child table** EMPLOYEES.DEPARTMENT_ID.

This does not disable the foreign key. Oracle still enforces referential integrity on INSERT/UPDATE of child rows and on DELETE/modification of parent keys. However, if the FK column in the child table lacks an appropriate index, certain operations on the parent table may need to inspect the child table expensively and acquire a broader table-level lock.

In OLTP systems, a common scenario is:

1. Session A deletes a parent row or changes a referenced key.
2. Oracle must ensure no child row violates the foreign key.
3. If the FK on the child table is unindexed, Oracle may acquire a TM Share lock on the child table during the check.
4. Session B wanting to INSERT/UPDATE/DELETE another row in the child table may have to wait, even though that row is unrelated to the parent being deleted.

This is why foreign key indexes are often considered for **concurrency**, beyond speeding up JOIN queries or child-row lookups.

## 2. Foreign keys and both sides of the relationship

A foreign key is declared on the child table:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id);
~~~

Both sides play different roles:

| Side | Key | Role |
|---|---|---|
| Parent table | PRIMARY KEY or UNIQUE key | Uniquely identifies the referenced row |
| Child table | FOREIGN KEY | Validates that the referenced value exists in the parent |

The index on the parent table and the index on the child table serve two different goals:

- The unique index on the parent key supports finding parent rows and enforcing uniqueness.
- The index on the child FK supports quickly finding child rows by parent key, reducing referential check cost and avoiding certain broad table locks.

Do not confuse having a primary key index on the parent table with the child table having an index. Creating a PRIMARY KEY on DEPARTMENTS does not automatically create an index on EMPLOYEES.DEPARTMENT_ID.

## 3. Why can an unindexed FK cause contention?

When deleting a parent row, Oracle must determine whether any child rows currently reference that key. If child rows exist and no cascading delete action is declared, the operation is rejected to protect referential integrity.

If the FK on the child table is unindexed, the check may require scanning the child table. To ensure no other session concurrently inserts a child row referencing that parent while Oracle checks and deletes the parent, Oracle may acquire a TM Share lock on the child table.

A TM Share lock conflicts with the TM Row Exclusive lock required by normal DML on the child table. Consequently, an INSERT/UPDATE/DELETE on the child table may be blocked even if it touches a completely different row.

### 3.1. Illustrative scenario

Suppose the PARENT table has two rows:

~~~text
PARENT_ID
---------
1
2
~~~

The CHILD table has one row referencing parent 2:

~~~text
CHILD_ID | PARENT_ID
---------+----------
101      | 2
~~~

There is no index on CHILD.PARENT_ID.

Session A runs:

~~~sql
DELETE FROM parent
WHERE parent_id = 1;
~~~

Parent 1 has no child rows. Oracle still must verify that no new child rows reference parent 1 before completing the delete. When the FK is unindexed, this operation may acquire a TM Share lock on CHILD to protect the check.

Session B runs:

~~~sql
UPDATE child
SET child_note = 'checked'
WHERE child_id = 101;
~~~

Even though row CHILD_ID = 101 references parent 2, the UPDATE still needs a DML lock on table CHILD. A's TM lock can force B to wait. This is table-level contention on the child table, not because A and B are modifying the same CHILD row.

If an appropriate index exists on CHILD.PARENT_ID, Oracle can locate child rows via the index and avoid this kind of broad table-level lock in typical cases. Row locks and actual conflicts on the exact same data still apply.

### 3.2. Not every parent DELETE succeeds

If parent 1 has child rows and the FK lacks ON DELETE CASCADE or ON DELETE SET NULL, the parent DELETE is rejected due to the referential constraint, typically with:

~~~text
ORA-02292: integrity constraint violated - child record found
~~~

An FK index does not change this rule. The index only assists in finding child rows and reducing certain contention; it does not allow deleting a parent that is still referenced.

## 4. TM locks and TX locks: distinguishing the right wait type

Oracle uses multiple enqueue types. Two types commonly need to be distinguished when investigating FK contention:

- **TM enqueue:** lock at the table object level, associated with DML/DDL operations and protecting table structures.
- **TX enqueue:** transaction-related lock, typically appearing when a session waits for another transaction to release a row lock or waits on a transaction-related resource.

Normal DML typically acquires a TM Row Exclusive lock on the modified table. In addition, it locks the actually modified rows with row-level locks.

### 4.1. Common TM modes

Modes commonly shown in V$LOCK.LMODE and REQUEST:

| Mode | Common Name | General Meaning |
|---:|---|---|
| 2 | Row Share (RS) | Table-level shared lock |
| 3 | Row Exclusive (RX) | Normal DML on a table |
| 4 | Share (S) | Stronger shared lock, can conflict with DML RX |
| 5 | Share Row Exclusive (SRX) | Combines share and row exclusive |
| 6 | Exclusive (X) | Table-level exclusive lock |

In an unindexed FK scenario, a TM Share lock on the child table can conflict with the TM Row Exclusive lock Session B needs to run DML. Specific modes depend on the operation and context; when investigating, inspect TYPE, LMODE, REQUEST, object, and blocker together rather than inferring from a single column.

### 4.2. Comparison table

| Symptom | Usually Involved Lock Type | Scope |
|---|---|---|
| Two sessions UPDATE the same row | TX/row lock | The contested row |
| Parent DELETE with unindexed child FK | TM lock on the child table may appear | Can impact unrelated DML on the child table |
| Normal DML on a table | TM Row Exclusive with row locks | Table at DML level and actually modified rows |
| DDL conflicting with DML | TM/table lock and DDL lock | Table object |
| Deadlock between two transactions | Lock wait cycle, usually involving TX | Multiple rows/resources in different orders |

Do not label every wait scenario a "row lock." If the event is enq: TM - contention, check table enqueues and objects. If the event is enq: TX - row lock contention, locate the transaction holding the row or related resource.

## 5. Creating an index on a foreign key column

For a single-column relationship:

~~~sql
CREATE INDEX ix_employees_department_id
ON employees(department_id);
~~~

This index allows Oracle to find EMPLOYEES rows whose DEPARTMENT_ID matches a specific parent key without scanning the entire child table under suitable access paths.

An FK index also helps queries such as:

~~~sql
SELECT e.employee_id,
       e.employee_name
FROM employees e
WHERE e.department_id = :p_department_id;
~~~

and JOINs:

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.department_id = :p_department_id;
~~~

However, the primary reason emphasized in this lesson is that the index helps Oracle verify parent-child relationships and avoid certain broad table locks when operating on parent keys.

### 5.1. An index is not mandatory to declare an FK

Oracle allows creating a foreign key without an index on the child table. The constraint is still enforced and invalid data is still rejected.

Therefore:

- The FK constraint protects data integrity.
- The FK index improves access paths and concurrency behavior in certain operations.
- The two objects serve different purposes; one does not replace the other.

Lacking an FK index does not mean data is corrupt. It is a design decision to evaluate against the workload, especially the frequency of parent DELETEs/key updates and concurrent DML on the child table.

## 6. Composite foreign keys and index column order

Suppose a parent table has a composite unique key of TENANT_ID and PARENT_CODE:

~~~sql
CREATE TABLE tenant_parent (
    tenant_id NUMBER NOT NULL,
    parent_code VARCHAR2(30 CHAR) NOT NULL,
    parent_name VARCHAR2(100),
    CONSTRAINT pk_tenant_parent
        PRIMARY KEY (tenant_id, parent_code)
);
~~~

Child table:

~~~sql
CREATE TABLE tenant_child (
    child_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    parent_code VARCHAR2(30 CHAR) NOT NULL,
    child_name VARCHAR2(100),
    CONSTRAINT fk_tenant_child_parent
        FOREIGN KEY (tenant_id, parent_code)
        REFERENCES tenant_parent(tenant_id, parent_code)
);
~~~

An appropriate index on the FK:

~~~sql
CREATE INDEX ix_tenant_child_parent
ON tenant_child(tenant_id, parent_code);
~~~

With a composite index, the FK columns should be placed as the leading columns of the index so the database can search by the full parent key. Additional columns can follow if needed by query workloads:

~~~sql
CREATE INDEX ix_tenant_child_parent_status
ON tenant_child(tenant_id, parent_code, status);
~~~

An index like:

~~~sql
CREATE INDEX ix_tenant_child_status_parent
ON tenant_child(status, tenant_id, parent_code);
~~~

does not have the FK columns in the leading position. If a check only filters by TENANT_ID and PARENT_CODE, this index typically does not offer as favorable an access path as one starting with the FK columns.

When designing, consider:

- Are all columns in the foreign key covered?
- Are the FK columns in the leading prefix?
- Does the column order match predicates and workload?
- Does an existing index already cover the same prefix?
- Does the index duplicate another index?

### 6.1. FK as part of a larger existing index

There is no need to create a new index if the child table already has an index where the FK columns form the leading prefix.

For example, if the FK is (DEPARTMENT_ID) and you already have:

~~~sql
CREATE INDEX ix_emp_department_status
ON employees(department_id, status);
~~~

This index already starts with DEPARTMENT_ID, so it can serve child lookups for the FK. Before creating an extra single-column index on DEPARTMENT_ID, inspect existing indexes and execution plans.

If the FK is (TENANT_ID, PARENT_CODE), an index on (TENANT_ID, PARENT_CODE, CREATED_AT) can support FK lookups. An index on (CREATED_AT, TENANT_ID, PARENT_CODE) does not have the FK in its leading prefix.

## 7. Impact of each parent-child operation

| Operation | FK Check / Impact | Role of Child Index |
|---|---|---|
| INSERT child row | Confirms parent key exists | Does not replace parent check; child index is maintained on insert |
| UPDATE FK column in child | Checks new parent key | Helps FK lookup; index entry must be updated |
| DELETE child row | Removes reference from child set | Index entry must be maintained; helps find/delete by FK |
| DELETE parent row | Confirms no children remain or applies ON DELETE action | Finds child rows fast and reduces broad table lock risk when FK was unindexed |
| UPDATE referenced key in parent | Protects reference; usually rejected if children remain | Supports checking child rows and reduces contention |
| DELETE parent with ON DELETE CASCADE | Deletes related child rows | Finds child rows fast; child rows still must be locked and deleted |

Oracle does not support ON UPDATE CASCADE in standard foreign key syntax. Updating a parent key that is currently referenced will typically be rejected while child rows exist; key changes must be handled via a dedicated workflow.

### 7.1. INSERT child row

When INSERTing into CHILD with an FK value, Oracle must verify that the parent row exists. If no matching parent exists, the DML is rejected, typically with ORA-02291.

~~~sql
INSERT INTO employees (
    employee_id, employee_name, department_id
)
VALUES (1001, 'An', 9999);
~~~

If department 9999 does not exist, the FK constraint blocks the INSERT. An FK index on the child table does not eliminate the parent check; it mainly assists parent-to-child lookups and requires index maintenance.

### 7.2. UPDATE FK on child table

~~~sql
UPDATE employees
SET department_id = 20
WHERE employee_id = 1001;
~~~

Oracle verifies that department 20 exists. Since DEPARTMENT_ID is in the FK index, changing its value also requires maintaining the index entry. The index speeds up lookups at the cost of extra write maintenance.

### 7.3. DELETE parent row without ON DELETE CASCADE

~~~sql
DELETE FROM departments
WHERE department_id = 10;
~~~

If employees still reference department 10, Oracle rejects the delete to preserve integrity. An FK index helps locate child rows quickly and reduces broad table-level locks in applicable scenarios.

### 7.4. ON DELETE CASCADE

~~~sql
ALTER TABLE employees
DROP CONSTRAINT fk_employees_department;

ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id)
ON DELETE CASCADE;
~~~

When deleting a department, referencing employees can be deleted along with it. This performs multiple DML changes on the child table, so undo, redo, index maintenance, and row locks on those child rows must be accounted for.

The FK index helps Oracle locate rows to cascade more efficiently. It does not eliminate row locks on deleted rows, nor does it prevent blocking against transactions modifying those rows.

### 7.5. ON DELETE SET NULL

~~~sql
ALTER TABLE employees
DROP CONSTRAINT fk_employees_department;

ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id)
ON DELETE SET NULL;
~~~

When deleting a department, DEPARTMENT_ID of child rows is set to NULL if the column allows it. Child rows are UPDATEd, incurring undo/redo, index maintenance, and locking costs. The FK index helps identify the set of rows to update.

## 8. When does an FK index have high concurrency value?

An index is especially worth considering when:

- The parent table has frequent DELETEs.
- Referenced keys on the parent can be UPDATEd by business workflows.
- The child table receives continuous INSERT/UPDATE/DELETE from many sessions.
- A parent DML operation affects none or few child rows yet could cause broad blocking.
- The child table is large and full-table scans to verify relationships are expensive.
- ON DELETE CASCADE/SET NULL affects substantial numbers of child rows.
- Queries frequently filter/JOIN by the FK.

An index may bring less value if the child table is very small, data is nearly read-only, parent keys are never deleted/changed, and the workload has no contention. Still, decisions should weigh potential future business changes.

Do not mechanically apply "every FK must have an index." Evaluate concurrency risk, maintenance cost, and real workload.

## 9. Cost of an FK index

An FK index is not free. On child INSERT, Oracle must add an entry. On FK UPDATE, old/new entries must be maintained. On child DELETE, entry deletion must be maintained.

| Child Table Operation | FK Index Cost |
|---|---|
| INSERT CHILD | Adds entry to index |
| UPDATE FK column | Updates corresponding entry |
| UPDATE non-FK column | Usually does not alter FK index entry |
| DELETE CHILD | Maintains entry deletion |
| Bulk load | Many entries built/maintained; can become a significant cost |

Indexes also consume storage, buffer cache, redo, and maintenance work. On extremely write-heavy child tables, adding many indexes can lower INSERT throughput.

### 9.1. Choosing B-tree vs. bitmap?

For OLTP tables with concurrent DML, a B-tree index is the standard choice for an FK. A bitmap index on an FK column can create broad lock/contention ranges when modifying rows, especially with multiple concurrent sessions. Bitmap indexes generally suit analytical workloads with low concurrent DML and require careful evaluation before use on transactional tables.

### 9.2. Avoiding duplicate indexes

If a composite index already starts with the FK columns, an additional single-column index may be unnecessary. Multiple similar indexes increase write and storage costs without proportional benefit.

## 10. Checking which FKs lack an appropriate index

First, list foreign keys and their columns in order:

~~~sql
SELECT c.table_name,
       c.constraint_name,
       cc.position,
       cc.column_name
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

Next, list indexes and their column order:

~~~sql
SELECT table_name,
       index_name,
       column_position,
       column_name
FROM user_ind_columns
ORDER BY table_name, index_name, column_position;
~~~

Match each FK against indexes on the same child table. A candidate index should have all FK columns as its leading prefix. Do not merely check whether the column name appears anywhere in the index; column position matters.

For example, if the FK is DEPARTMENT_ID:

- Index (DEPARTMENT_ID) qualifies.
- Index (DEPARTMENT_ID, STATUS) also has a matching leading prefix.
- Index (STATUS, DEPARTMENT_ID) does not have DEPARTMENT_ID in the leading position.

If inspecting other schemas, DBAs can use DBA_CONSTRAINTS, DBA_CONS_COLUMNS, DBA_INDEXES, and DBA_IND_COLUMNS instead of USER views. Pay attention to owner, index status, visibility, and partitioning during evaluation.

### 10.1. Viewing existing indexes on a table

~~~sql
SELECT i.index_name,
       i.uniqueness,
       i.status,
       c.column_position,
       c.column_name
FROM user_indexes i
JOIN user_ind_columns c
  ON c.index_name = i.index_name
 AND c.table_name = i.table_name
WHERE i.table_name = 'EMPLOYEES'
ORDER BY i.index_name, c.column_position;
~~~

Object names in USER views are typically stored in uppercase unless created with quoted identifiers.

### 10.2. Checking constraints

~~~sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       r_constraint_name,
       delete_rule
FROM user_constraints
WHERE table_name IN ('DEPARTMENTS', 'EMPLOYEES')
ORDER BY table_name, constraint_type, constraint_name;
~~~

DELETE_RULE shows the constraint's delete behavior, such as NO ACTION or CASCADE/SET NULL per metadata. Check ENABLED/VALIDATED status before assuming all existing data has been validated.

## 11. Monitoring TM contention and blockers

When DML on a child table waits, inspect sessions and events:

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

If the event is enq: TM - contention, investigate table enqueues and related objects. If the event is enq: TX - row lock contention, locate the transaction holding the row lock or related TX resource.

### 11.1. Viewing TM/TX locks

~~~sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM v$lock
WHERE type IN ('TM', 'TX')
ORDER BY type, sid;
~~~

Meaning:

- TYPE: enqueue type, such as TM or TX.
- ID1/ID2: resource identifiers specific to the lock type.
- LMODE: mode currently held by the session.
- REQUEST: mode requested by the session.
- BLOCK: whether the session is blocking other sessions per this column.

For TM locks, ID1 typically corresponds to object ID. You can look it up in DBA_OBJECTS:

~~~sql
SELECT object_id,
       owner,
       object_name,
       object_type
FROM dba_objects
WHERE object_id = :p_object_id;
~~~

### 11.2. Viewing locked objects

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

V$LOCKED_OBJECT is useful for viewing object-level DML locks; it does not enumerate every row lock as a list of rows. Combine V$SESSION, V$LOCK, SQL_ID, and the blocker chain to find the root cause.

V$ and DBA views may require SELECT_CATALOG_ROLE or explicit grants. Do not require regular application accounts to hold DBA privileges just to run DML.

## 12. Two-session example: reproducing contention

Perform this in a dedicated lab schema. Open two independent database sessions and disable auto-commit in your SQL tool if needed to keep transactions open.

### 12.1. Prepare the data

~~~sql
CREATE TABLE lab_parent (
    parent_id NUMBER CONSTRAINT pk_lab_parent PRIMARY KEY,
    parent_name VARCHAR2(50)
);

CREATE TABLE lab_child (
    child_id NUMBER CONSTRAINT pk_lab_child PRIMARY KEY,
    parent_id NUMBER NOT NULL,
    child_note VARCHAR2(100),
    CONSTRAINT fk_lab_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES lab_parent(parent_id)
);

INSERT INTO lab_parent VALUES (1, 'Parent 1');
INSERT INTO lab_parent VALUES (2, 'Parent 2');
INSERT INTO lab_child VALUES (101, 2, 'Existing child');
COMMIT;
~~~

No index has been created on LAB_CHILD.PARENT_ID yet.

### 12.2. Session A: operation on the parent

Run in Session A without committing:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
~~~

Parent 1 has no child rows. Oracle still must guard the FK verification before deleting.

### 12.3. Session B: DML on an unrelated child row

Run in Session B:

~~~sql
UPDATE lab_child
SET child_note = 'Updated by session B'
WHERE child_id = 101;
~~~

Row 101 references parent 2, not parent 1. When the FK lacks an index, Session B may wait on the TM lock on LAB_CHILD held by Session A while processing the parent DELETE.

In Session B, check V$SESSION to see the event, wait time, and BLOCKING_SESSION. In Session A, inspect SQL_ID and open transactions.

### 12.4. End the transaction

In Session A:

~~~sql
ROLLBACK;
~~~

After A rolls back, Session B can proceed. Check results and data state.

### 12.5. Create the FK index and retry

Create the index:

~~~sql
CREATE INDEX ix_lab_child_parent_id
ON lab_child(parent_id);
~~~

Repeat the operation in Session A:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
~~~

In Session B, run the UPDATE on child 101 as above. With an appropriate FK index, the broad table-level lock caused by an unindexed FK is typically avoided; unrelated DML can proceed. Waiting can still occur if two sessions touch the same row, same parent key, constraints, or other shared resources.

Roll back Session A after testing:

~~~sql
ROLLBACK;
~~~

### 12.6. Clean up lab data

~~~sql
DROP TABLE lab_child PURGE;
DROP TABLE lab_parent PURGE;
~~~

Drop only the lab tables you created. Never run lock-holding tests or DROP on production schemas.

## 13. Deadlocks and parent-child operation ordering

An FK index reduces a broad form of contention, but it does not eliminate deadlocks or every lock wait.

For example, two transactions operating in opposite orders:

- Session A locks parent and then updates child.
- Session B locks child and then performs an operation needing parent.

If each session waits for a resource held by the other, a wait cycle can form. Oracle detects the deadlock and reports ORA-00060.

Reduce the risk:

- Standardize table and row access order within transactions.
- Keep transactions short.
- Avoid calling external services or waiting for users while holding locks.
- Design batches partitioned by parent key if possible.
- Use FK indexes to avoid unnecessary table-level locks in applicable scenarios.
- Investigate deadlock traces, blockers, and actual SQL before changing schema.

Do not treat creating an FK index as a cure-all for every ORA-00060; deadlocks also depend on locking order across multiple resources.

## 14. FK indexes and query performance

Beyond concurrency, FK indexes support common queries:

### 14.1. Finding all children of a parent

~~~sql
SELECT *
FROM employees
WHERE department_id = :p_department_id;
~~~

### 14.2. Parent-child JOIN

~~~sql
SELECT d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name;
~~~

### 14.3. DELETE CASCADE

If the relationship uses ON DELETE CASCADE, Oracle needs to find child rows to delete. An FK index can reduce the cost of locating child rows, especially when the child table is large and each parent has only a few children.

The optimizer can still choose a full table scan if the matching row ratio is high or statistics indicate it is cheaper. An index does not guarantee every query uses the index.

## 15. Special cases to consider

### 15.1. Small child tables

If a child table has only a few dozen rows and little concurrent DML, a full scan may be cheap and contention negligible. A new index adds maintenance cost. Measure first.

### 15.2. Write-heavy child tables

For child tables with heavy concurrent INSERT/UPDATE, rare parent DELETEs still mean an FK index adds cost to every write. Balance index maintenance overhead against blocking risk on the child table. In many OLTP systems, reducing table-wide contention outweighs the cost of adding a small B-tree index, but confirm against your workload.

### 15.3. Composite foreign keys

Create an index containing all FK columns in the leading prefix. If an existing index covers that exact prefix, there is no need to create a duplicate just because of index naming.

### 15.4. DISABLED or NOVALIDATE constraints

If an FK is not ENABLED/VALIDATED, data validation semantics may differ from a fully validated constraint. Do not assume the locking behavior of a disabled FK matches an enabled FK. Check metadata before investigating.

### 15.5. Deferred constraints

A DEFERRABLE constraint can defer validation until an appropriate point in the transaction. That shifts when errors surface, without removing data integrity requirements or automatically eliminating lock contention. Check DEFERRABLE/DEFERRED status and transaction design.

### 15.6. Partitioning

Partitioned child tables may use local or global indexes. The index strategy must align with the partition key, FK lookups, and partition maintenance operations. Do not assume a local index always replaces every global access path; check execution plans and integrity requirements for your Oracle release.

## 16. Decision workflow for creating an FK index

~~~text
Does the child table have a FOREIGN KEY?
          |
          v
Check existing indexes
          |
          +-- Is there an index with all FK columns
          |   in the leading prefix?
          |          |
          |          +-- Yes --> Evaluate workload; avoid duplicates
          |          |
          |          +-- No
          v
Does parent have DELETE / key updates?
Does child have concurrent DML?
Is child large or does it use cascade?
          |
          +-- Yes --> Prioritize evaluating a B-tree FK index
          |
          +-- No  --> Weigh query and concurrency benefits
                         against maintenance cost
          |
          v
Create index in an appropriate window
          |
          v
Verify metadata + execution plans
          |
          v
Monitor TM/TX waits and DML throughput
~~~

This is an evaluation workflow, not a rule to blindly index every foreign key.

## 17. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating only a PK index on parent and assuming child FK is indexed | Parent DELETE can cause TM contention on child table | Check indexes separately on the child table |
| Leaving child FK unindexed in high-concurrency OLTP | Parent DML can block unrelated DML on child | Evaluate a B-tree FK index |
| Placing FK columns after unrelated columns in index | No suitable leading prefix for FK lookups | Place FK columns first in the index |
| Creating an extra index despite an existing composite prefix | Increases write/storage overhead | Inventory existing indexes first |
| Assuming FK index allows deleting a parent with children | Still violates referential integrity | Use ON DELETE action if business logic intends it |
| Assuming index eliminates all locks | Row locks and transaction waits still exist | Distinguish TM vs. TX and check blockers |
| Using bitmap FK index for concurrent OLTP writes | Can increase lock contention | Evaluate B-tree |
| Leaving cascade FK unindexed on a large child table | Locating and deleting child rows is expensive | Index FK and measure cascade |
| Creating indexes without evaluating DML overhead | Slower INSERT/UPDATE/DELETE | Measure read/write trade-off |
| Killing waiting sessions without finding the blocker | Fails to address root cause | Inspect blocker chain and transaction owner |

## 18. Implementation checklist

- [ ] Identify parent table, child table, and all foreign key columns.
- [ ] Verify FK is ENABLED/VALIDATED and check its delete rule.
- [ ] Inspect existing indexes on the child table.
- [ ] Confirm all FK columns form the leading prefix of at least one suitable index.
- [ ] Check whether composite indexes serve additional workloads and avoid duplicates.
- [ ] Evaluate parent DELETE/key update frequency and ON DELETE CASCADE/SET NULL.
- [ ] Evaluate concurrent DML volume on the child table.
- [ ] Measure TM contention and blockers before/after if possible.
- [ ] Verify the new index does not introduce unacceptable write/storage overhead.
- [ ] Check execution plans for child-lookup and cascade queries.
- [ ] Test with two sessions in a lab schema, including parent DML and unrelated child DML.
- [ ] Establish an index creation/rebuild procedure suitable for production and partitioning.

## 19. Core takeaways

- Foreign key constraints reside on the child table; primary/unique indexes on the parent table do not automatically index child FKs.
- FK constraints protect integrity; FK indexes speed up child-row lookups and reduce certain broad table-level locks.
- When an FK is unindexed, DELETE or updating a referenced key on the parent table can cause Oracle to acquire a TM Share lock on the child table while checking references.
- A TM Share lock can conflict with the TM Row Exclusive lock of other DML on the child table, even DML on unrelated rows.
- An appropriate FK index usually lets Oracle check child rows via B-tree and avoid that broad contention; it does not eliminate row locks, TX waits, or all blocking.
- If child rows actually exist, parent DELETE is still rejected unless allowed by an ON DELETE action; an index does not change business rules.
- For composite FKs, place all FK columns in the leading prefix of the index; inspect existing indexes before adding new ones.
- FK indexes carry INSERT/UPDATE/DELETE, redo, storage, and maintenance costs; decide based on workload.
- Track enq: TM - contention and enq: TX - row lock contention separately to identify the true scope of contention.
- Two-session testing and before/after measurement are practical ways to verify whether an index resolves your system's bottleneck.

### Oracle documentation to consult

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Data concurrency and consistency, locks, transactions, and integrity constraints.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing indexes, tables, and database objects.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CREATE INDEX, foreign key constraints, DELETE, and referential actions.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Enqueue waits, blocking sessions, and execution plans.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — V$LOCK, V$SESSION, V$LOCKED_OBJECT, and performance views.

Specific lock modes and how the optimizer accesses data depend on the DML type, constraints, Oracle version, and configuration. Consult documentation for your exact release, verify indexes by leading columns, and reproduce with two sessions in a lab schema before modifying a production schema.
