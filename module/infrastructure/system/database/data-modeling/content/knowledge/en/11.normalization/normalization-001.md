# Insertion, Update, and Deletion Anomalies and Their Root in Redundant Data

A table may be easy to query early on, yet become hard to maintain when the same business fact is stored across multiple rows. If a single insert, update, or delete operation fails to handle all of those copies, data can end up missing, contradictory, or unintentionally lost. These are the three **data anomalies** (*insertion, update, deletion anomalies*) commonly used to explain why relational models need normalization.

In data design, the goal is not only to store the current state, but also to **accurately represent business facts, allow them to change independently, and enforce consistency constraints**. This lesson starts from a practical example, identifies the root causes, and then decomposes the schema to resolve them.

## 1. The Problem: Storing Employees Along with Department Information

Suppose an HR system has the following rules:

- Each employee belongs to one department at a time.
- Each department has its own ID, name, and manager.
- A department can still exist before it has any employees.
- When a department's name or manager changes, that change applies to every employee in the department.

The initial design merges all information into a single table; **each row represents one employee**:

| employee_id | employee_name | department_id | department_name | department_manager |
| ---: | --- | ---: | --- | --- |
| 101 | An | 10 | Sales | Bình |
| 102 | Chi | 10 | Sales | Bình |
| 103 | Dũng | 20 | Engineering | Hà |

SQL example (PostgreSQL-compatible syntax):

~~~sql
CREATE TABLE employee_department_flat (
    employee_id         BIGINT PRIMARY KEY,
    employee_name       VARCHAR(100) NOT NULL,
    department_id       BIGINT NOT NULL,
    department_name     VARCHAR(100) NOT NULL,
    department_manager  VARCHAR(100) NOT NULL
);

INSERT INTO employee_department_flat
    (employee_id, employee_name, department_id,
     department_name, department_manager)
VALUES
    (101, 'An',   10, 'Sales',       'Bình'),
    (102, 'Chi',  10, 'Sales',       'Bình'),
    (103, 'Dũng', 20, 'Engineering', 'Hà');
~~~

The immediate benefit is retrieving both employee and department information without a join. In return, the values **Sales** and **Bình** appear once for *each* employee in department 10, even though in reality there is only one department with one current set of attributes.

Notably, having multiple employees share department ID **10** is not an error in itself. The department ID is a necessary reference to express the relationship. The problem lies in the fact that **the department name and manager, which belong to the department**, are copied into every employee record.

## 2. The Three Types of Anomalies

### 2.1. Insertion Anomaly

**Requirement:** create a new department with ID **30**, name **Operations**, and manager **Lan**, before the department has hired any employees.

In the flat table, department information cannot be inserted on its own because every row must have **employee_id** as its primary key. The following illustrative statement will be rejected:

~~~sql
-- Error illustration: employee_id is the primary key and cannot be NULL.
INSERT INTO employee_department_flat
    (employee_id, employee_name, department_id,
     department_name, department_manager)
VALUES
    (NULL, 'No employee yet', 30, 'Operations', 'Lan');
~~~

If we create a "dummy employee" to fill the primary key, the system ends up storing data that violates business reality. If we wait until an employee is hired to record the department, the system cannot represent an existing department that currently has no members.

**Root nature:** the existence of the *department* entity is forced to depend on the existence of the *employee* entity, contrary to business requirements.

### 2.2. Update Anomaly

**Requirement:** change the manager of department **10** from **Bình** to **Minh**.

The flat design forces the application to update *all* employee rows in department 10. If only An's row is updated, we get:

| employee_id | department_id | department_manager |
| ---: | ---: | --- |
| 101 | 10 | Minh |
| 102 | 10 | Bình |

This is the result of the following scenario, tested independently on the sample data:

~~~sql
BEGIN;

UPDATE employee_department_flat
SET department_manager = 'Minh'
WHERE employee_id = 101;

SELECT employee_id, department_id, department_manager
FROM employee_department_flat
WHERE department_id = 10
ORDER BY employee_id;

ROLLBACK;
~~~

The same **department_id = 10** now has two different manager values. The system cannot tell which value is correct by looking at the data alone. An update filtered by **department_id** could fix all matching rows in one statement, yet the design still forces every write path to remember the rule "update all copies simultaneously"; data imports, integrations, or manual edits all risk missing rows.

**Root nature:** a change to *a single fact* must be reflected across *multiple storage locations*.

### 2.3. Deletion Anomaly

**Requirement:** employee Dũng (ID **103**) leaves the company. Dũng is currently the last remaining employee in department **20**.

~~~sql
BEGIN;

DELETE FROM employee_department_flat
WHERE employee_id = 103;

SELECT *
FROM employee_department_flat
WHERE department_id = 20;
-- No rows remain.

ROLLBACK;
~~~

Deleting the employee also wipes out the department name **Engineering** and manager **Hà**, because that was the only record holding those two pieces of information. After the deletion, the table no longer shows whether department 20 ever existed or is still active with zero employees.

**Root nature:** deleting one entity unintentionally deletes information belonging to another entity.

### 2.4. Quick Comparison

| Anomaly Type | Desired Valid Operation | Consequence of Flat Table | Immediate Cause |
| --- | --- | --- | --- |
| **Insertion** | Create a department with no employees yet | Cannot be represented without creating a dummy employee | Department data depends on an employee row |
| **Update** | Change a department's manager | Multiple rows can store conflicting values | One fact has multiple copies that must stay synchronized |
| **Deletion** | Delete the last employee | All department information is lost | Two entities with different lifecycles are merged together |

These anomalies are **structural risks**. The absence of conflicting values in a table so far does not prove the design is safe; the failure may simply surface when a specific data change scenario occurs.

## 3. Root Cause: Redundant Data and Functional Dependencies

### 3.1. Identifying "What Each Row Is About"

In the example above, the row granularity (*grain*) is **one employee**. However, some columns describe the employee while others describe the department:

- **employee_id → employee_name, department_id**: an employee ID determines the employee's name and current department.
- **department_id → department_name, department_manager**: a department ID determines the department's current name and manager.

The notation **X → Y** denotes a *functional dependency*: for a given value of X, there is only one valid value of Y in any data state permitted by the business rules under consideration. This is a statement about the business domain, not a conclusion drawn merely because a few sample rows happen to match.

From these two rules, we get a dependency chain:

~~~text
employee_id
    |---> employee_name
    |
    +---> department_id
               |---> department_name
               +---> department_manager
~~~

The department name and manager depend on **department_id**, rather than directly on the employee itself. In a table whose candidate key is **employee_id**, this is a transitive dependency from the key to non-key attributes through **department_id**—a classic sign of not yet satisfying **Third Normal Form (3NF)**. With a single-column primary key, this table may still satisfy **2NF**; not every form of redundancy should be mistaken for a 2NF violation.

The key principle is that **each business fact should have one authoritative place where it is managed**. If each department name is stored only once in the department record, renaming it becomes a single operation on the exact entity that owns that information.

### 3.2. Not Every Repeated Value Is Harmful Redundancy

Distinguish between three situations:

1. **Intentional repeated reference:** multiple employees store **department_id = 10** to indicate they belong to department 10. This is normal relationship representation in the relational model.
2. **Copied descriptive attributes:** every employee stores **department_name = Sales** even though that name belongs to department 10. This is a source of update anomaly risk.
3. **Historical records at different points in time:** an order retains the product name or unit price *at checkout time* for later reconciliation. This value may differ from current product catalog data because the two columns reflect **two time-bound facts**, not merely two copies that must be updated together.

To determine whether redundancy causes anomalies, ask: **Who owns the attribute? What point in time does the attribute describe? What rule requires different rows to have the same value?**

## 4. Fixing via Entity Separation and Explicit Constraints

Because department information has an independent lifecycle, split the table into:

- **departments:** each row is a department; stores ID, name, and manager.
- **employees:** each row is an employee; stores employee attributes and a foreign key pointing to the department.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "has"
    DEPARTMENTS {
        bigint department_id PK
        varchar department_name
        varchar department_manager
    }
    EMPLOYEES {
        bigint employee_id PK
        varchar employee_name
        bigint department_id FK
    }
~~~

Schema example:

~~~sql
CREATE TABLE departments (
    department_id      BIGINT PRIMARY KEY,
    department_name    VARCHAR(100) NOT NULL,
    department_manager VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    employee_id   BIGINT PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    department_id BIGINT NOT NULL
        REFERENCES departments(department_id)
);

INSERT INTO departments
    (department_id, department_name, department_manager)
VALUES
    (10, 'Sales',       'Bình'),
    (20, 'Engineering', 'Hà');

INSERT INTO employees
    (employee_id, employee_name, department_id)
VALUES
    (101, 'An',   10),
    (102, 'Chi',  10),
    (103, 'Dũng', 20);
~~~

The primary key on **departments** guarantees that each department ID has only one row holding that department's data. The foreign key on **employees** guarantees that an employee references an existing department. These constraints directly enforce the business rules rather than leaving synchronization entirely to application code.

### 4.1. Re-testing the Three Operations

**Inserting a department with no employees yet:**

~~~sql
INSERT INTO departments
    (department_id, department_name, department_manager)
VALUES (30, 'Operations', 'Lan');
-- Valid even though no row in employees references department 30 yet.
~~~

**Changing a manager:** only a single value needs to be updated.

~~~sql
UPDATE departments
SET department_manager = 'Minh'
WHERE department_id = 10;
~~~

**Deleting the last employee in a department:** department information remains intact.

~~~sql
DELETE FROM employees
WHERE employee_id = 103;

SELECT department_id, department_name
FROM departments
WHERE department_id = 20;
-- Still returns department 20: Engineering.
~~~

These three examples can be executed sequentially on the data created in section 4. The DBMS can also block deleting a **department** that is still referenced by employees under default foreign key behavior; if the business needs employee reassignment, department closure, or cascading deletion, a dedicated rule must be defined.

### 4.2. Using Joins When Full Information Is Needed

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name,
    d.department_manager
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

A join can produce a **query result** identical to the original flat table at the employee grain, while the underlying department data is still stored only once. This decomposition preserves all employee information as long as the foreign key is valid and **department_id** is a unique key on the departments table.

To also see departments that do not yet have any employees, query from **departments** using a **LEFT JOIN**:

~~~sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
~~~

Department **30** will appear with **employee_count = 0**. This is a representational capability the flat table lacked.

## 5. Early Detection with Queries and Design Questions

In legacy data, you can check whether the same department ID already contains multiple names or managers:

~~~sql
SELECT
    department_id,
    COUNT(*) AS employee_rows,
    COUNT(DISTINCT department_name) AS distinct_names,
    COUNT(DISTINCT department_manager) AS distinct_managers
FROM employee_department_flat
GROUP BY department_id
HAVING COUNT(DISTINCT department_name) > 1
    OR COUNT(DISTINCT department_manager) > 1;
~~~

This query returns departments showing signs of conflict across rows. However, **zero returned rows does not mean the design is safe**: current data may simply happen to be consistent. Nor can this query find departments without employees, since the flat table cannot store that case in the first place.

When reviewing a table, test it with these questions:

1. **Grain:** which entity or event does each row represent?
2. **Attribute ownership:** which entity do the names, statuses, and attributes in the row actually belong to?
3. **Independent insertion:** can entity A be created when no related entity B exists yet?
4. **Single-place update:** does changing one business fact force updates across multiple rows?
5. **Safe deletion:** does deleting the last row of a group lose information that still needs to be retained?
6. **Constraints:** do primary keys, foreign keys, uniqueness rules, and functional dependencies accurately reflect the business rules?
7. **Time:** are two identical values copies of a current state, or independent historical snapshots?

### Misleading Workarounds

| Approach | Why It Fails to Address the Root Cause |
| --- | --- |
| Using **SELECT DISTINCT** to hide duplicate rows | Only patches read output; does not fix storage structure or write risks |
| Adding **UNIQUE (department_id, department_name)** to the flat table | Both prevents multiple employees in the same department with the same department name and fails to guarantee that one department ID has only one name across different rows |
| Wrapping all updates in a transaction | A transaction makes the written operations atomic, but it cannot automatically know if the application missed a copy |
| Only checking that current data has no conflicts | Cannot test the ability to insert an empty department or losing a department when the last employee is deleted |
| Splitting tables while omitting foreign keys | Eliminates attribute duplication, yet allows references to nonexistent departments |

When normalizing, also inspect newly exposed constraints. For example, if a **manager** is an employee in the system, the manager attribute should likely be **manager_employee_id** referencing an employee, paired with appropriate management rules. Using a free-text person name as in this minimal example is insufficient to guarantee manager identity in a real system.

## 6. When Is Redundant Data Intentionally Accepted?

Normalization reduces write anomalies, yet there are cases where keeping repeated data is a sound decision:

- **Read-optimized tables / materialized views:** copying department names into a reporting model to reduce joins. Requires defining the authoritative source of truth and a refresh, reconciliation, or rebuild process.
- **Historical snapshots:** retaining product name and unit price at order placement time; transaction records reflect past events and must not automatically change with the current catalog.
- **Analytical warehouses:** dimensional models or flattened tables may prioritize aggregation speed, trading off for synchronization pipelines and clear definitions of when data takes effect.

In these cases, you must clarify the **source of truth**, **effective time**, **update mechanism**, **acceptable latency**, and **drift detection**. Intentional duplication with a maintenance mechanism is fundamentally different from accidental duplication that forces every business write to synchronize manually.

## 7. Practice Exercise

Consider a course enrollment table:

| student_id | student_name | course_id | course_name | lecturer |
| ---: | --- | --- | --- | --- |
| 1 | Mai | C01 | SQL Fundamentals | Thảo |
| 2 | Nam | C01 | SQL Fundamentals | Thảo |
| 1 | Mai | C02 | Data Design | Phúc |

Assume **each student has one current name**, **each course has one current name and one current lecturer**, a student can enroll in multiple courses, and a course can exist with no enrolled students yet.

**Tasks:**

1. Identify one insertion scenario, one update scenario, and one deletion scenario that can cause anomalies.
2. State the core functional dependencies and determine an appropriate key for an enrollment record.
3. Propose tables, primary keys, and foreign keys so that a course with zero enrollments can still be stored.

<details>
<summary>Suggested Solution</summary>

- **Insertion:** without an enrolled student, you cannot insert a row solely to register course C03. **Update:** changing the lecturer for C01 requires updating every enrollment row for C01. **Deletion:** deleting the last enrollment for C02 can wipe out course C02's information.
- Functional dependencies: **student_id → student_name**; **course_id → course_name, lecturer**. If a student enrolls in a course at most once, the pair **(student_id, course_id)** identifies an enrollment record.
- Split into **students(student_id PK, student_name)**, **courses(course_id PK, course_name, lecturer)**, and **enrollments(student_id FK, course_id FK, PRIMARY KEY(student_id, course_id))**. The **courses** table exists independently of **enrollments**, so courses with no students can be retained.

</details>

## 8. Key Takeaways

**Insertion anomalies** prevent representing an independent fact; **update anomalies** allow multiple copies of one fact to contradict each other; **deletion anomalies** cause unintended data loss. The root cause is usually placing attributes of multiple entities—with different functional dependencies and lifecycles—into a single table at an inappropriate grain.

When designing a relational data model, identify the entities, grain, and functional dependencies first; then place each attribute under the entity that owns it, use keys to link them, and use constraints to protect correctness. You may denormalize for performance or historical fidelity, but it must be a deliberate, controlled choice rather than a temporary patch for structural inconsistency.
