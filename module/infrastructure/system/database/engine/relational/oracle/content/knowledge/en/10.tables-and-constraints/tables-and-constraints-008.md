# DEFERRABLE and Constraint Checking at Commit Time

In Oracle Database, constraints protect data integrity: primary keys prevent duplicate identifiers, foreign keys reference valid parent rows, values must satisfy allowed domains, and mandatory columns cannot be missing. Normally, Oracle validates constraints immediately when a DML statement finishes. However, some transactions must **temporarily pass through a state that violates a constraint**, as long as **all data is valid before the transaction commits**.

For example, when migrating a set of reference codes, an application may need to insert child rows before parent rows; or when swapping two positions with a UNIQUE constraint, the intermediate step creates a temporary duplicate even though the final result has none. Oracle handles these scenarios via the **`DEFERRABLE`** attribute and **`IMMEDIATE`/`DEFERRED`** checking modes.

This lesson explains check timing, how to declare and switch modes per transaction, examples of commit-time failures, usage in Java JDBC, metadata inspection, and key limitations.

## 1. When Can a Constraint Be Checked?

Within a multi-statement SQL transaction, we can distinguish:

- **End-of-statement checking (IMMEDIATE)**: every INSERT, UPDATE, or DELETE statement must leave data satisfying all constraints currently in immediate mode. If violated, that statement fails.
- **End-of-transaction checking (DEFERRED)**: for constraints declared deferrable and currently in DEFERRED mode, Oracle allows temporary invalid intermediate states within the same transaction, validating at COMMIT or when the application switches back to IMMEDIATE.
- **Does not mean disabling the constraint**: the final state must still be valid to commit. Otherwise, COMMIT fails and the transaction cannot succeed.

~~~text
Transaction T
  |
  +-- Statement 1: insert child referencing a parent that does not exist yet
  |       |
  |       +-- IMMEDIATE: fails at statement 1
  |       |
  |       +-- DEFERRED: temporarily allowed, awaits checking
  |
  +-- Statement 2: insert matching parent row
  |
  +-- COMMIT
          |
          +-- Final data satisfies constraint --> COMMIT succeeds
          |
          +-- Violation still remains ---------> COMMIT fails, transaction rolls back
~~~

Importantly, **IMMEDIATE does not necessarily mean checking row-by-row mid-statement**. When one statement updates multiple rows, Oracle evaluates immediate constraints under statement-level checking semantics. DEFERRED differs by allowing violations to persist **across multiple statement boundaries** within the same transaction.

## 2. Distinguishing DEFERRABLE from DEFERRED

These two similar terms are not synonymous:

| Concept | Meaning | Scope |
| --- | --- | --- |
| **DEFERRABLE** | Constraint is declared **capable** of deferred checking | Property of the constraint definition |
| **NOT DEFERRABLE** | Constraint cannot be switched to end-of-transaction checking | Property of the constraint definition |
| **INITIALLY IMMEDIATE** | Each transaction starts in immediate checking mode by default | Initial constraint configuration |
| **INITIALLY DEFERRED** | Each transaction starts in deferred checking mode by default | Initial constraint configuration |
| **SET CONSTRAINTS ... IMMEDIATE** | Switches checking mode back to immediate in the current transaction | Per-transaction control |
| **SET CONSTRAINTS ... DEFERRED** | Switches a deferrable constraint to deferred mode in the current transaction | Per-transaction control |

A **`DEFERRABLE INITIALLY IMMEDIATE`** constraint is checked immediately in most transactions, and deferred only in specific transactions where the application calls `SET CONSTRAINTS`.

Conversely, a **`DEFERRABLE INITIALLY DEFERRED`** constraint waits until transaction end by default, yet an application can still trigger early checking with `SET CONSTRAINTS ... IMMEDIATE`.

**NOT DEFERRABLE** does not mean a constraint is unimportant; it means it cannot be switched to deferred checking via `SET CONSTRAINTS`. If `DEFERRABLE` is omitted in the definition, the default is **`NOT DEFERRABLE`**.

### 2.1. Design Matrix

| Declaration | Default When Transaction Starts | Can Call `SET CONSTRAINTS ... DEFERRED`? |
| --- | --- | --- |
| No DEFERRABLE specified | IMMEDIATE (NOT DEFERRABLE) | No |
| NOT DEFERRABLE INITIALLY IMMEDIATE | IMMEDIATE | No |
| DEFERRABLE INITIALLY IMMEDIATE | IMMEDIATE | Yes |
| DEFERRABLE INITIALLY DEFERRED | DEFERRED | Yes |

You cannot declare **`NOT DEFERRABLE INITIALLY DEFERRED`** expecting "deferred by default and unchangeable"; those two clauses contradict each other. To default to end-of-transaction checking, the constraint must be declared `DEFERRABLE`.

## 3. Why Is Deferred Checking Needed?

### 3.1. Inserting Parent and Child Out of Order

Normally, to insert an **NHAN_VIEN** (employee) row with a foreign key to **PHONG_BAN** (department), the application must insert the department first:

~~~text
PHONG_BAN (ma_phong = 10)
    |
    +--- NHAN_VIEN (ma_nv = 101, ma_phong = 10)
~~~

During an import batch, however, it may be convenient to insert employees first and departments afterward, provided both occur within one transaction. With a DEFERRABLE foreign key set to DEFERRED, the intermediate state is permitted.

### 3.2. Swapping UNIQUE Values

Suppose two rows hold ranking positions 1 and 2, where each position must be unique:

~~~text
Before:
  Item A -> position 1
  Item B -> position 2

Goal:
  Item A -> position 2
  Item B -> position 1
~~~

Updating A to 2 first temporarily leaves two rows at position 2. Updating B first temporarily leaves two rows at position 1. With a `UNIQUE DEFERRABLE` constraint, the application can defer validation until after both UPDATEs, when no duplicate remains.

### 3.3. Circular Foreign Key Relationships

Example:

- Every employee belongs to a department.
- Every department must designate an employee as department manager.

In some designs, two tables reference each other. When creating both a new department and its new manager, no insertion order satisfies all mandatory foreign keys on the very first statement. Deferring the appropriate foreign key within **a single transaction** resolves the dependency cycle. However, sometimes it is better to **redesign the relationship or manager assignment timing** rather than deferring constraints for every operation.

## 4. Syntax for Creating DEFERRABLE Constraints

In Oracle, deferrability can be declared when creating the constraint, for example with FOREIGN KEY and UNIQUE:

~~~sql
CREATE TABLE phong_ban_dt (
    ma_phong  NUMBER(6) CONSTRAINT pk_pb_dt PRIMARY KEY,
    ten_phong VARCHAR2(100 CHAR) NOT NULL
);

CREATE TABLE nhan_vien_dt (
    ma_nv     NUMBER(6) CONSTRAINT pk_nv_dt PRIMARY KEY,
    ma_phong  NUMBER(6) NOT NULL,
    ho_ten    VARCHAR2(100 CHAR) NOT NULL,

    CONSTRAINT fk_nv_phong_dt
        FOREIGN KEY (ma_phong)
        REFERENCES phong_ban_dt (ma_phong)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

In this example:

- **PK_PB_DT** and **PK_NV_DT** are standard primary keys.
- **FK_NV_PHONG_DT** is a **DEFERRABLE** foreign key, defaulting to **IMMEDIATE** mode.
- **MA_PHONG NOT NULL** still requires a department code to be supplied; deferring the foreign key **does not** make a NULL department code valid.
- Constraints are explicitly named so `SET CONSTRAINTS` can reference them and error messages are clear.

For workflows that routinely require deferring by default, declare the foreign key as:

~~~sql
CONSTRAINT fk_constraint_name
    FOREIGN KEY (parent_id)
    REFERENCES parent_table (parent_id)
    DEFERRABLE INITIALLY DEFERRED
~~~

This is **an illustrative syntax fragment inside `CREATE TABLE` or `ALTER TABLE ADD CONSTRAINT`**, not a standalone runnable SQL statement. Choose the default mode to match business needs: most online transactional systems should prefer IMMEDIATE to catch errors early, reserving DEFERRED for operations that genuinely require it.

### 4.1. DEFERRABLE Cannot Be Toggled Arbitrarily After Creation

In Oracle, you cannot use a single `ALTER CONSTRAINT` command to switch an existing constraint directly from **NOT DEFERRABLE** to **DEFERRABLE** or vice versa. Changing deferrability typically requires a controlled plan to **drop and recreate the constraint** with the updated definition.

Replacing a constraint affects keys, backing indexes, validation of existing rows, and DDL implicit commits. Never do this casually inside a business transaction or in production without a full migration and test plan.

## 5. Lab 1: Immediately Checked Foreign Key

Using **PHONG_BAN_DT** and **NHAN_VIEN_DT** created above, assume both tables are initially empty. Try inserting an employee before the department exists:

~~~sql
-- Deliberately fails because department 10 does not exist yet.
INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (101, 10, 'Nguyen An');
~~~

Because **FK_NV_PHONG_DT** defaults to `INITIALLY IMMEDIATE`, the statement fails—typically with **`ORA-02291`** (`integrity constraint violated - parent key not found`).

Crucially, the error happens **at the INSERT statement**, without waiting for COMMIT. If an application runs a large transaction, failing fast pinpoints the faulty step right when it occurs.

To reset before re-running exercises in the same schema:

~~~sql
ROLLBACK;
~~~

This merely cleans up any uncommitted DML; the rejected INSERT never entered the table. Calling ROLLBACK is not what makes an immediate constraint enforce checks.

## 6. Lab 2: Deferring a Foreign Key Check, Then Fixing Before COMMIT

In a new transaction, set **FK_NV_PHONG_DT** to DEFERRED before inserting:

~~~sql
-- Applies to the current transaction.
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

-- Parent missing temporarily: permitted because FK is deferred.
INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (101, 10, 'Nguyen An');

-- Insert parent before commit.
INSERT INTO phong_ban_dt (ma_phong, ten_phong)
VALUES (10, 'Business Department');

-- Explicitly validate the FK right now.
SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;

COMMIT;
~~~

Between the two INSERTs, the transaction contains an employee referencing a nonexistent department. After the second INSERT, the data satisfies the foreign key, so **`SET CONSTRAINTS ... IMMEDIATE`** validates cleanly and COMMIT accepts the transaction.

Verify the result:

~~~sql
SELECT nv.ma_nv, nv.ho_ten, pb.ten_phong
FROM nhan_vien_dt nv
JOIN phong_ban_dt pb
  ON pb.ma_phong = nv.ma_phong
ORDER BY nv.ma_nv;
~~~

The result shows employee **101** in **Business Department**.

**`SET CONSTRAINTS` does not modify the `DEFERRABLE` metadata stored in the schema**; it adjusts check timing only for the current transaction. Once the transaction ends, the next transaction starts with each constraint's `INITIALLY` setting.

### 6.1. Why Check Early with IMMEDIATE?

If a transaction still has more work to perform after establishing relationships, calling:

~~~sql
SET CONSTRAINTS ALL IMMEDIATE;
~~~

catches any deferred constraint violations **before the application performs additional work**. Switching to IMMEDIATE forces Oracle to validate those constraints immediately; if any violation remains, `SET CONSTRAINTS` fails.

However, **`SET CONSTRAINTS ALL IMMEDIATE` is not `COMMIT`**. DML changes are still uncommitted. Even if early checking succeeds, the application must still call `COMMIT` to finish the transaction. Non-deferrable constraints always check under their own rules and are unaffected by this command.

## 7. Lab 3: Catching a Violation When Switching Back to IMMEDIATE

Suppose the matching department is never inserted:

~~~sql
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (102, 999, 'Tran Binh');

-- Deliberately fails because PHONG_BAN_DT(999) does not exist.
SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;
~~~

`SET CONSTRAINTS IMMEDIATE` checks the foreign key's current state and fails because **999** is absent from the parent table. This catches the error early, before COMMIT.

Here, if you do not want to create department 999, undo the transaction:

~~~sql
ROLLBACK;
~~~

Or, if the business truly wants department 999, insert that parent row and re-run validation, provided the transaction is still active and privileges allow it. Not every `SET CONSTRAINTS` error means data was partially committed; distinguish a **failed constraint check** from a **failed COMMIT**.

### 7.1. Visible Within the Transaction, Hidden from Other Sessions

While a foreign key is deferred, the transaction's own session sees the newly inserted child row temporarily lacking a parent. Other sessions under standard isolation do not see uncommitted DML from this transaction.

Even so, a temporarily invalid intermediate state can still affect **triggers, subsequent SQL in the same transaction, Java logic, and other checks**. Therefore, use deferral only within logic specifically designed to handle intermediate states.

## 8. Lab 4: A Violation Persisting Until COMMIT

Another scenario is when the application never brings data into a valid state:

~~~sql
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (103, 998, 'Le Chi');

-- Deliberately triggers failure at COMMIT.
COMMIT;
~~~

Because **PHONG_BAN_DT(998)** does not exist, COMMIT checks the deferred foreign key and cannot complete. Oracle typically raises related errors such as:

~~~text
ORA-02091: transaction rolled back
ORA-02291: integrity constraint (...) violated - parent key not found
~~~

When a deferred constraint is violated at COMMIT, **Oracle rolls back the failed transaction**—it never accepts half the transaction while discarding only the bad row. You must then start a fresh transaction with valid data; never treat a failed COMMIT as partially persisted.

Verify:

~~~sql
SELECT ma_nv, ma_phong, ho_ten
FROM nhan_vien_dt
ORDER BY ma_nv;
~~~

If only the successful transaction from Section 6 ran earlier, the table still contains employee **101** and not employee **103**. Exact error messages may vary by version or driver; the crucial point is that **no invalid data is ever committed**.

### 8.1. A COMMIT Error Differs from an INSERT Error

| Moment | Error Behavior | Key Takeaway |
| --- | --- | --- |
| INSERT when FK is immediate | Statement is rejected | Violating row is not added; transaction may continue other work depending on the app |
| `SET CONSTRAINTS ... IMMEDIATE` while still invalid | Validation switch fails | Fix data or roll back; never assume changes committed |
| COMMIT while FK is deferred and invalid | Commit cannot succeed | Entire transaction rolls back |
| COMMIT after all deferred constraints hold | Transaction commits | Changes are persisted per transaction rules |

In Java applications, if JDBC throws an exception on COMMIT, never report success to the user. Log the error, determine transaction status from the error type, and apply controlled retry policies if appropriate.

## 9. Lab 5: UNIQUE DEFERRABLE and Swapping Values

The foreign key example showed cross-table dependencies. Another case involves temporarily duplicate values during multi-row updates, where the final state must be unique.

### 9.1. Creating a Table with UNIQUE DEFERRABLE

~~~sql
CREATE TABLE thu_tu_dt (
    ma_muc  NUMBER(6) CONSTRAINT pk_tt_dt PRIMARY KEY,
    vi_tri  NUMBER(5) NOT NULL,

    CONSTRAINT uq_tt_vitri_dt
        UNIQUE (vi_tri)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO thu_tu_dt (ma_muc, vi_tri) VALUES (1, 1);
INSERT INTO thu_tu_dt (ma_muc, vi_tri) VALUES (2, 2);
COMMIT;
~~~

The table holds two rows with **VI_TRI** values 1 and 2. Running a separate UPDATE directly:

~~~sql
-- Deliberately fails in immediate mode because position 2 already exists.
UPDATE thu_tu_dt
SET vi_tri = 2
WHERE ma_muc = 1;
~~~

This statement is rejected by **UQ_TT_VITRI_DT**, typically with **ORA-00001**. Even though the ultimate intent is a swap, the first statement alone leaves two rows at position 2.

### 9.2. Swapping Inside a Deferred Transaction

~~~sql
SET CONSTRAINTS uq_tt_vitri_dt DEFERRED;

UPDATE thu_tu_dt
SET vi_tri = 2
WHERE ma_muc = 1;

UPDATE thu_tu_dt
SET vi_tri = 1
WHERE ma_muc = 2;

SET CONSTRAINTS uq_tt_vitri_dt IMMEDIATE;

COMMIT;
~~~

After both UPDATEs:

~~~sql
SELECT ma_muc, vi_tri
FROM thu_tu_dt
ORDER BY ma_muc;
~~~

Result:

| MA_MUC | VI_TRI |
| --- | --- |
| 1 | 2 |
| 2 | 1 |

The mid-transaction duplicate was resolved before checking. There was no need to drop the UNIQUE constraint or use a sentinel value like `-1` just to sidestep an intermediate collision.

**Note:** Whether a **single UPDATE** swapping two rows requires deferral depends on statement-level checking mechanics and DML structure. This exercise uses **two separate UPDATEs** to clearly demonstrate end-of-transaction checking, rather than claiming every swap pattern fails in IMMEDIATE mode.

### 9.3. Index Mechanism for UNIQUE DEFERRABLE

For a UNIQUE or PRIMARY KEY declared DEFERRABLE, Oracle may use a **nonunique index** to back the constraint, since temporary duplicate keys can exist inside a deferred transaction. This differs from creating a fixed **UNIQUE index** that blocks duplicates immediately at the index level.

When designing constraints, indexes, and DEFERRABLE transitions, inspect metadata and plan deployments carefully. Never swap out a backing index arbitrarily or assume all UNIQUE constraints use the exact same index type.

## 10. INITIALLY DEFERRED: Waiting Until Transaction End by Default

In earlier examples, a **`DEFERRABLE INITIALLY IMMEDIATE`** constraint needed `SET CONSTRAINTS` to defer checking. If a business model routinely processes out-of-order relationships early in a transaction, choose **`INITIALLY DEFERRED`** at creation time.

Standalone example:

~~~sql
CREATE TABLE lo_hang_dd (
    ma_lo    NUMBER(6) CONSTRAINT pk_lo_dd PRIMARY KEY,
    ten_lo   VARCHAR2(100 CHAR) NOT NULL
);

CREATE TABLE mat_hang_dd (
    ma_mat_hang NUMBER(6) CONSTRAINT pk_mh_dd PRIMARY KEY,
    ma_lo       NUMBER(6) NOT NULL,
    ten_mat_hang VARCHAR2(100 CHAR) NOT NULL,

    CONSTRAINT fk_mh_lo_dd
        FOREIGN KEY (ma_lo)
        REFERENCES lo_hang_dd (ma_lo)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Because **FK_MH_LO_DD** defers checking by default, this transaction can insert the child row first without calling `SET CONSTRAINTS`:

~~~sql
INSERT INTO mat_hang_dd
    (ma_mat_hang, ma_lo, ten_mat_hang)
VALUES (501, 20, 'Item A');

INSERT INTO lo_hang_dd
    (ma_lo, ten_lo)
VALUES (20, 'Batch 20');

COMMIT;
~~~

The final state is valid, so commit succeeds. If you forget to create `LO_HANG_DD(20)`, COMMIT fails.

### 10.1. Subsequent Transactions Still Start in the INITIALLY State

Example of a transaction wanting errors caught early:

~~~sql
SET CONSTRAINTS fk_mh_lo_dd IMMEDIATE;

-- Violation is caught at the end of the INSERT statement without waiting for COMMIT.
INSERT INTO mat_hang_dd
    (ma_mat_hang, ma_lo, ten_mat_hang)
VALUES (502, 999, 'Item without batch');
~~~

This INSERT fails immediately because the foreign key is IMMEDIATE in the current transaction. Run **`ROLLBACK`** to finish the test.

Keep in mind: **`INITIALLY`** sets only the **default mode when a transaction begins**; it does not mean the constraint can never switch modes.

## 11. SET CONSTRAINTS: Scope, Naming, and Limits

Conceptual syntax:

~~~sql
SET CONSTRAINTS ALL DEFERRED;

SET CONSTRAINTS ALL IMMEDIATE;

SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;
~~~

The change applies only to the **current transaction**. After COMMIT or ROLLBACK, the next transaction reverts to each constraint's declared `INITIALLY` mode.

### 11.1. ALL Does Not Turn NOT DEFERRABLE into DEFERRABLE

**`SET CONSTRAINTS ALL DEFERRED`** applies deferred mode only to constraints that are deferrable. **`NOT DEFERRABLE`** constraints cannot be switched to DEFERRED. Using `ALL` does not "unlock everything" in the database.

If you only need to defer one foreign key in a transaction, **name it explicitly** rather than using `ALL`. Unnecessarily deferring unrelated UNIQUE or FK constraints delays error detection and complicates debugging.

### 11.2. Do Not Treat SET CONSTRAINTS as a Permanent Configuration Command

`SET CONSTRAINTS` does not alter structures in the data dictionary. Compare with:

~~~sql
CREATE TABLE ... (
    ...
    CONSTRAINT fk_name FOREIGN KEY (...)
        REFERENCES ...
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Constraint DDL defines schema attributes, whereas `SET CONSTRAINTS` affects checking behavior only inside one session's current transaction. In a connection pool, subsequent transactions must never assume an earlier request left `DEFERRED` mode enabled permanently.

### 11.3. Keep DDL Out of Workflows Fixing Temporary Violations

`CREATE TABLE`, `ALTER TABLE`, and `DROP CONSTRAINT` are DDL and carry **implicit commit** rules in Oracle. If a transaction currently holds temporary rows violating a deferred constraint, never run an `ALTER TABLE` mid-transaction to "tweak a definition" before continuing. DDL triggers a commit boundary, causing the current transaction to fail or behave unexpectedly.

Prepare schema and constraint definitions **before** starting DML transactions that use deferral.

## 12. Distinguishing DEFERRABLE from ENABLE, VALIDATE, and DISABLE

These attributes appear side by side in constraint metadata yet answer **different** questions:

| Attribute / State | Question It Answers | Key Distinction |
| --- | --- | --- |
| **DEFERRABLE / NOT DEFERRABLE** | Can checking timing be postponed within a transaction? | Declared when creating the constraint |
| **INITIALLY DEFERRED / IMMEDIATE** | When does a new transaction check by default? | Only the starting default |
| **SET CONSTRAINTS ... DEFERRED** | What deferral is the current transaction requesting? | Does not modify definition metadata |
| **ENABLE / DISABLE** | Is Oracle enforcing the constraint per its active mode? | DISABLE is not the same as deferred |
| **VALIDATE / NOVALIDATE** | Has existing data been verified against the constraint? | Not synonymous with checking at COMMIT |

**DEFERRED is not DISABLED.** Deferred constraints still require valid data before COMMIT; disabled is a separate administrative state with data-protection consequences. Never disable an FK or UNIQUE constraint in an application just to handle an intermediate state that deferral solves cleanly.

Likewise, **NOVALIDATE** governs validation of existing rows and enforcement policy—it is not another way of saying `INITIALLY DEFERRED`.

During migrations and bulk loads, keep these states clearly separated to avoid leaving inconsistent data behind.

## 13. Inspecting Metadata via USER_CONSTRAINTS

After creating the example tables, check whether constraints are declared DEFERRABLE:

~~~sql
SELECT table_name,
       constraint_name,
       constraint_type,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE table_name IN (
    'PHONG_BAN_DT',
    'NHAN_VIEN_DT',
    'THU_TU_DT',
    'LO_HANG_DD',
    'MAT_HANG_DD'
)
ORDER BY table_name, constraint_name;
~~~

Key columns:

- **CONSTRAINT_TYPE**: commonly **P** for primary key, **U** for unique, **R** for foreign key, **C** for check, and other types per Oracle metadata.
- **DEFERRABLE**: indicates whether the constraint was declared deferrable.
- **DEFERRED**: shows the constraint's **`INITIALLY`** setting—not a reliable way to ask "did this session just run `SET CONSTRAINTS DEFERRED`?"
- **STATUS**: ENABLED or DISABLED.
- **VALIDATED**: constraint data-validation status.

For instance, `FK_NV_PHONG_DT` shows **`DEFERRABLE`** and initial mode **`IMMEDIATE`**. `FK_MH_LO_DD` shows initial mode **`DEFERRED`**. Running `SET CONSTRAINTS` inside a transaction does not change these two definition columns.

### 13.1. Viewing Columns Belonging to a Constraint

~~~sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.table_name IN ('NHAN_VIEN_DT', 'THU_TU_DT')
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

This query identifies which columns belong to each constraint—handy when a table has multiple FKs/UNIQUEs or system-generated constraint names.

### 13.2. Viewing Which Key a Foreign Key References

~~~sql
SELECT fk.constraint_name AS fk_name,
       fk.table_name AS child_table,
       parent.constraint_name AS referenced_constraint,
       parent.table_name AS parent_table,
       fk.deferrable,
       fk.deferred
FROM user_constraints fk
JOIN user_constraints parent
  ON parent.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.table_name IN ('NHAN_VIEN_DT', 'MAT_HANG_DD')
ORDER BY fk.table_name, fk.constraint_name;
~~~

**R_CONSTRAINT_NAME** is the referenced key constraint on the parent table. Within the same practice schema, joining like this suffices to locate the parent. Across multiple real schemas, also match owner in **`ALL_CONSTRAINTS`** or **`DBA_CONSTRAINTS`** to avoid colliding constraint names across schemas.

## 14. Java JDBC: Managing a Transaction with Deferred Constraints

A Java application must execute **`SET CONSTRAINTS` and all related DML on the same `Connection` and inside the same transaction**. This is frequently missed when using connection pools or repositories that open a fresh connection per call.

Example assuming a configured Oracle JDBC `DataSource`, existing tables from Section 4, and unused IDs:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class ImportNhanVienService {
    private final DataSource dataSource;

    public ImportNhanVienService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void taoNhanVienVaPhongBan(long maNv, long maPhong)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // Defer only the specific FK needed in this transaction.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS fk_nv_phong_dt DEFERRED"
                    );
                }

                try (PreparedStatement insertNv =
                         connection.prepareStatement(
                           "INSERT INTO nhan_vien_dt " +
                           "(ma_nv, ma_phong, ho_ten) VALUES (?, ?, ?)")) {
                    insertNv.setLong(1, maNv);
                    insertNv.setLong(2, maPhong);
                    insertNv.setString(3, "Employee from Java");
                    insertNv.executeUpdate();
                }

                try (PreparedStatement insertPhong =
                         connection.prepareStatement(
                           "INSERT INTO phong_ban_dt " +
                           "(ma_phong, ten_phong) VALUES (?, ?)")) {
                    insertPhong.setLong(1, maPhong);
                    insertPhong.setString(2, "Department from Java");
                    insertPhong.executeUpdate();
                }

                // Catch any issues before calling COMMIT if possible.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE"
                    );
                }

                connection.commit();
            } catch (SQLException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                connection.setAutoCommit(originalAutoCommit);
            }
        }
    }
}
~~~

This example highlights transaction boundaries:

1. **`getConnection()`** obtains a connection from the DataSource.
2. **`setAutoCommit(false)`** prevents the two INSERTs from auto-committing individually.
3. **`SET CONSTRAINTS ... DEFERRED`** applies to the transaction on that connection.
4. Both tables are written within the same transaction, even though the child precedes the parent.
5. **`SET CONSTRAINTS ... IMMEDIATE`** verifies state before COMMIT.
6. **`commit()`** runs only if all steps succeed.
7. On `SQLException`, the service attempts **`rollback()`**; any rollback exception is attached as suppressed rather than masking the original error.

In production systems, also handle recovery if restoring autocommit fails or the connection drops. Avoid retrying write transactions without idempotency guards and commit-state verification.

### 14.1. Why Does AutoCommit Matter So Much?

With **`autoCommit = true`**, every successful DML statement commits immediately under JDBC semantics. A transaction cannot preserve a child-without-parent state across auto-committed statements: when the child INSERT triggers a COMMIT, Oracle checks the deferred FK and the transaction fails.

Thus, calling **`SET CONSTRAINTS DEFERRED`** while letting repositories borrow separate connections or use autocommit will not work. One genuine transaction must span every step.

### 14.2. Using Spring and @Transactional

In Spring, **`@Transactional`** can manage a transaction across a service method calling multiple repositories, provided all operations share the same transaction manager/DataSource and join the same transaction.

You can run `SET CONSTRAINTS` via JDBC/`JdbcTemplate` inside the Spring-managed transaction and then run DML. In that case, **never call `Connection.commit()` or `rollback()` manually** on a Spring-managed connection. Watch out for multiple DataSources, nested transactions, propagation settings, or asynchronous calls: operations splitting into separate transactions will not share the deferred mode.

Conceptual example:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ThemDonViService {
    private final JdbcTemplate jdbc;

    public ThemDonViService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void taoNhanVienVaPhongBan() {
        jdbc.execute("SET CONSTRAINTS fk_nv_phong_dt DEFERRED");

        jdbc.update(
            "INSERT INTO nhan_vien_dt " +
            "(ma_nv, ma_phong, ho_ten) VALUES (?, ?, ?)",
            301, 30, "Spring Employee"
        );

        jdbc.update(
            "INSERT INTO phong_ban_dt (ma_phong, ten_phong) " +
            "VALUES (?, ?)",
            30, "Spring Department"
        );

        jdbc.execute("SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE");
        // Spring transaction manager commits when the method finishes cleanly.
    }
}
~~~

This assumes Spring JDBC and an appropriate transaction manager are configured, the IDs do not already exist, and the method is invoked through the Spring proxy so `@Transactional` takes effect. Bypassing the proxy or mixing DataSources outside the transaction changes behavior.

**A deferred constraint error during Spring's commit step** occurs after the last Java line in the service method finishes—at the proxy/transaction manager boundary. Design error handling at the transaction boundary, not only around individual `jdbc.update` calls.

## 15. Correctness, Performance, and Operations

### 15.1. Do Not Defer Checks Unnecessarily

An immediate constraint catches violations right at the offending statement. With deferred constraints, an error may surface only after many SQL statements, after the transaction has consumed extra CPU, I/O, undo/redo, and held locks longer.

Therefore:

- Mark constraints `DEFERRABLE` only when business flows genuinely need it.
- If only one import/swap operation needs deferral, declare **`DEFERRABLE INITIALLY IMMEDIATE`** and enable `DEFERRED` locally.
- Once data arrangement finishes, consider calling **`SET CONSTRAINTS ... IMMEDIATE`** to validate early.
- Avoid overly long transactions, which increase cost and obscure error diagnosis.
- Never use deferral as a substitute for validating input sources or clean transaction design.

### 15.2. Deferring Constraints Does Not Replace Locking and Isolation

Deferred FK/UNIQUE constraints **do not control execution ordering across concurrent sessions**. Two concurrent transactions still obey Oracle's locking, isolation, and integrity checks. A COMMIT may wait on or fail due to another transaction's uncommitted changes or locks.

Never assume "the constraint is deferred" means there are no locks or contention. For workloads with concurrent writes on shared keys, run concurrency tests rather than only single-session sequential tests.

### 15.3. Not Every Other Constraint Gets Deferred

A single `DEFERRABLE` constraint in DEFERRED mode does not automatically defer **primary keys, NOT NULLs, other FKs, or `NOT DEFERRABLE` constraints**. For example, `FK_NV_PHONG_DT` can be deferred, yet `MA_PHONG` in `NHAN_VIEN_DT` remains **`NOT NULL`** and employee IDs must still satisfy the PK.

In an import transaction, never assume calling `SET CONSTRAINTS` for one foreign key allows all structurally invalid rows to slip through until commit.

### 15.4. Alternative Strategies

Sometimes a better option exists:

- **Sort input in parent → child order** when no cyclic dependencies exist.
- **Staging tables** to receive raw data, validate integrity, and load into core tables in clean transactions.
- **Single-statement updates** when possible, avoiding multiple UPDATEs that pass through invalid intermediate states.
- **Redesign cyclic relationships**, or allow one link to start `NULL` and update once both sides exist, if business rules permit.
- **Deferrable constraints** when end-of-transaction integrity is a natural requirement—not as a workaround for poorly controlled application logic.

No single approach fits every transaction. Weigh atomicity, concurrency, data volume, and early-validation needs.

## 16. Diagnosing Errors with DEFERRED Constraints

When a COMMIT fails, start from the constraint identifier rather than switching constraints to DISABLE.

**Step 1 — Capture error code and constraint name.** `ORA-02291` typically points to a missing parent record; `ORA-02292` involves deleting a parent with children; `ORA-00001` is a uniqueness violation. At commit time, `ORA-02091` often accompanies it.

**Step 2 — Inspect the constraint definition.**

~~~sql
SELECT constraint_name,
       table_name,
       constraint_type,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE constraint_name = 'FK_NV_PHONG_DT';
~~~

**Step 3 — Inspect transaction data.** If still pre-commit or in a reproduction test, compare child reference values against parent keys. Once COMMIT rolls back due to a deferred constraint violation, uncommitted rows are gone; rely on application logs, input datasets, or controlled reproduction.

**Step 4 — Check transaction boundaries.** Confirm `SET CONSTRAINTS`, child INSERT, and parent INSERT ran on the same connection without autocommit or intervening DDL.

**Step 5 — Cross-check data types and keys.** An FK can reference a unique key or primary key; column names may differ. Query `USER_CONS_COLUMNS` and `R_CONSTRAINT_NAME` to confirm the exact columns involved.

**Step 6 — Check early before commit.** During debugging, you can call `SET CONSTRAINTS ... IMMEDIATE` to isolate which statement group caused the error. Do not leave arbitrary mid-step checks in places where the transaction is intentionally still incomplete.

**Step 7 — Fix the root cause.** Create missing parents or remove invalid children; ensure final values for UNIQUE are truly distinct; fix locking/transaction bugs properly. Never drop a constraint just because one transaction inserted rows out of order.

### 16.1. Common Error Codes

| Error Code | Typical Scenario | When Does It Appear? |
| --- | --- | --- |
| **ORA-02291** | FK points to nonexistent parent | At an immediate statement or deferred FK check |
| **ORA-02292** | Parent delete/update blocked by child FK | At an immediate statement or deferred FK check |
| **ORA-00001** | Duplicate PRIMARY KEY / UNIQUE key | At an immediate statement or deferred constraint check |
| **ORA-02091** | Transaction rolled back, e.g., deferred constraint violation at commit | When the transaction cannot complete |
| **ORA-02447** or context-specific equivalent | Invalid constraint state change requested | On invalid `SET CONSTRAINTS` / definition operations, depending on version and statement |

You do not need to memorize every error code to master this lesson. What matters is distinguishing **a rejected statement**, **a failed `IMMEDIATE` check**, and **a failed `COMMIT`**.

## 17. End-to-End Practice Workflow

To see the interplay between both checking modes clearly:

1. Create `PHONG_BAN_DT` and `NHAN_VIEN_DT` with `FK_NV_PHONG_DT` as **`DEFERRABLE INITIALLY IMMEDIATE`**.
2. Insert a child referencing a nonexistent parent without calling `SET CONSTRAINTS`. Observe the error immediately at INSERT.
3. Start a new transaction and run **`SET CONSTRAINTS fk_nv_phong_dt DEFERRED`**.
4. Insert the child first, then insert the matching parent; run **`SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE`** and `COMMIT`. Observe the transaction succeeding.
5. Start another transaction, insert a child without creating its parent; try switching the constraint to `IMMEDIATE` and observe the failure.
6. `ROLLBACK`, repeat the missing-parent scenario, and proceed straight to `COMMIT`; observe the error and transaction rollback.
7. Create `THU_TU_DT` and swap two unique values using two UPDATEs inside a deferred transaction.
8. Create `LO_HANG_DD`/`MAT_HANG_DD` to observe **`INITIALLY DEFERRED`** working without calling `SET CONSTRAINTS` upfront.
9. Query `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` to match definitions against observed behavior.
10. Try a Java JDBC or Spring example to manage transactions and commit-time errors.

To clean up the practice schema, drop only the sandbox tables created by this lesson, children before parents:

~~~sql
DROP TABLE nhan_vien_dt PURGE;
DROP TABLE phong_ban_dt PURGE;
DROP TABLE thu_tu_dt PURGE;
DROP TABLE mat_hang_dd PURGE;
DROP TABLE lo_hang_dd PURGE;
~~~

**`DROP TABLE` is DDL**, carrying implicit commit rules; never run it in environments holding data you need to keep. `PURGE` bypasses the normal recycle bin, so use it only when you are sure these objects are disposable practice data.

## 18. Common Misconceptions

**"DEFERRABLE means always checked at COMMIT."** Incorrect. `DEFERRABLE` only means it can be deferred. If it is `INITIALLY IMMEDIATE` and the transaction never switches to `DEFERRED`, it still checks immediately.

**"INITIALLY DEFERRED means never checked mid-transaction."** Incorrect. Calling `SET CONSTRAINTS ... IMMEDIATE` triggers early validation.

**"SET CONSTRAINTS ALL DEFERRED disables every constraint."** Incorrect. It does not turn `NOT DEFERRABLE` constraints into `DEFERRED`, nor does it disable constraints.

**"DEFERRED is the same as DISABLE CONSTRAINT."** Incorrect. Deferred constraints still enforce integrity before COMMIT; disabled is a different administrative state.

**"If INSERT succeeds, the transaction is guaranteed to commit."** Incorrect. With deferred constraints, statements can succeed while COMMIT later fails.

**"A COMMIT failure on a deferred FK still keeps the earlier INSERTed rows."** Incorrect when a deferred constraint fails at COMMIT: the transaction rolls back.

**"You can convert NOT DEFERRABLE to DEFERRABLE using SET CONSTRAINTS alone."** Incorrect. `SET CONSTRAINTS` switches checking mode only for constraints already declared deferrable.

**"A connection-pooled app can call SET CONSTRAINTS on connection A and INSERT on connection B."** Incorrect across transaction boundaries. All statements must share the same transaction.

**"INITIALLY DEFERRED eliminates the need for transactions."** Incorrect. Transaction boundaries determine when deferred constraints check; autocommit triggers commit after every statement.

**"Temporary invalid states are always harmless."** Incorrect. Triggers, subsequent SQL in the same transaction, and application logic must still account for intermediate states.

**"Reading USER_CONSTRAINTS.DEFERRED tells you whether the current transaction called SET CONSTRAINTS."** Incorrect. That column reflects the constraint's `INITIALLY` mode, not dynamic mode changes inside an active transaction.

## 19. Self-Practice Questions

1. Distinguish **DEFERRABLE**, **DEFERRED**, **INITIALLY IMMEDIATE**, and **INITIALLY DEFERRED** across schema properties vs. transaction state.
2. In the employee/department example, why does inserting an employee before the department fail in IMMEDIATE mode yet succeed when the FK is deferred?
3. After calling `SET CONSTRAINTS fk_nv_phong_dt DEFERRED`, what happens at COMMIT if the referenced department still has not been created?
4. When `SET CONSTRAINTS ... IMMEDIATE` catches an error, why cannot you treat that state as a successful COMMIT?
5. Why is `MA_PHONG NOT NULL` on the employee table still necessary even though the foreign key is `DEFERRABLE`?
6. An application has just one daily workflow requiring temporary UNIQUE duplicates. Should you choose `INITIALLY IMMEDIATE` or `INITIALLY DEFERRED`, and why?
7. Why does swapping two positions using two separate UPDATE statements require attention to UNIQUE checking mode across statement boundaries?
8. A Java client has autocommit enabled, calls `SET CONSTRAINTS DEFERRED`, and runs multiple INSERTs. What is the risk to the transaction?
9. If a Spring service uses `@Transactional` yet a repository opens its own connection outside the transaction manager, will the service's `SET CONSTRAINTS` affect those INSERTs?
10. How do `DEFERRABLE` and `DEFERRED` in `USER_CONSTRAINTS` differ? Why is metadata alone insufficient to infer the mode set in an active transaction?
11. Why shouldn't you run `ALTER TABLE DROP CONSTRAINT` mid-transaction when you only need to defer an FK temporarily?
12. For a large batch import, compare three approaches: sorting parent rows before child rows, importing via a staging table, and using deferrable FKs.
13. If a UNIQUE constraint is deferred yet two rows still share the same value at COMMIT, does Oracle commit the valid rows and skip only the conflict?
14. How can a circular FK between `PHONG_BAN` and `NHAN_VIEN` use `DEFERRABLE`? When should you redesign the relationship instead?
15. When a commit-time error occurs in JDBC, why should the service report failure and avoid blind automatic retries without duplicate-prevention locks?

**DEFERRABLE is the capability to defer checking; DEFERRED is the mode active within a transaction.** Oracle permits temporary constraint violations to complete multi-step operations, yet **COMMIT can succeed only if all active constraints are satisfied**. Understanding `INITIALLY IMMEDIATE`/`DEFERRED`, `SET CONSTRAINTS`, statement-end vs. transaction-end checking, and JDBC/Spring boundaries lets you use this mechanism cleanly without compromising database integrity.
