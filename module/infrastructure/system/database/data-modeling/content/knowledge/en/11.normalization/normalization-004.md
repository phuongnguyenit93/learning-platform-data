# Third Normal Form and Dependencies That Must Be Separated

In a relational data model, a table can satisfy **First Normal Form (1NF)** and **Second Normal Form (2NF)** yet still repeatedly store a fact that belongs to another entity. When a department name sits on every employee row, renaming the department requires updating many rows, and deleting the last employee can wipe out the department's information. **Third Normal Form (3NF)** helps identify and resolve the class of functional dependencies behind that problem.

The goal of this lesson in the **Normalization** chapter of the **DATABASE_DATA_MODELING** module is to translate business rules into functional dependencies, identify attributes that belong in their owning tables, decompose schemas, and verify correctness using keys, foreign keys, and joins. It also distinguishes the practical rule of thumb "remove transitive dependencies" from the formal definition of 3NF, because not every dependency between two non-primary-key attributes violates 3NF.

## 1. The Problem: An Employee Table Storing Department Information

Suppose an HR system has the following rules:

- Each employee has a unique **employee_id**, a current name, and belongs to one current department.
- Each department has a unique **department_id**, a name, and one current lead.
- Multiple employees can belong to the same department; a department can exist before having any employees.
- When a department's name or lead changes, the change applies to the entire department, not to an individual employee.

Initial table:

| employee_id | employee_name | department_id | department_name | department_lead |
| ---: | --- | ---: | --- | --- |
| 101 | An | 10 | Sales | Bình |
| 102 | Chi | 10 | Sales | Bình |
| 103 | Dũng | 20 | Engineering | Hà |

Illustrative PostgreSQL SQL:

~~~sql
CREATE TABLE employees_flat (
    employee_id     BIGINT PRIMARY KEY,
    employee_name   VARCHAR(100) NOT NULL,
    department_id   BIGINT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    department_lead VARCHAR(100) NOT NULL
);

INSERT INTO employees_flat
    (employee_id, employee_name, department_id,
     department_name, department_lead)
VALUES
    (101, 'An',   10, 'Sales',       'Bình'),
    (102, 'Chi',  10, 'Sales',       'Bình'),
    (103, 'Dũng', 20, 'Engineering', 'Hà');
~~~

The **grain** of the table is **one employee per row**; the only candidate key under these assumptions is **employee_id**. Because the table has only a single-attribute key, there are no partial dependencies on a candidate key: the table satisfies **2NF** once it satisfies 1NF. Even so, the department name and lead are copied across as many rows as there are employees.

This is a design signal that warrants checking against 3NF.

## 2. Reading Functional Dependencies from Business Rules

The notation **X → Y** means that for each value of X, the business rules permit at most one value of Y in any valid data state. A functional dependency is **a rule for all valid states**, and cannot be proven merely from a few sample rows.

For the problem above:

~~~text
employee_id   -> employee_name, department_id
department_id -> department_name, department_lead
~~~

By transitivity of functional dependencies, it follows that:

~~~text
employee_id -> department_id -> department_name
employee_id -> department_id -> department_lead
~~~

Diagram:

~~~mermaid
flowchart LR
    E["employee_id<br/>(candidate key)"]
    N["employee_name"]
    D["department_id"]
    DN["department_name"]
    DL["department_lead"]
    E --> N
    E --> D
    D --> DN
    D --> DL
~~~

The attributes **department_name** and **department_lead** are determined by **department_id**, which is not a superkey of **employees_flat**: multiple employees can share the same **department_id**. They describe the **department**, not an individual employee.

The dependency **department_id → department_name, department_lead** is the point to separate—not because those two columns start with *department_*, but because **each department ID determines a set of department attributes** in the domain under consideration.

### 2.1. Anomalies That Can Arise

**Update anomaly:** changing department 10's lead to Minh while updating only one of the two rows:

~~~sql
BEGIN;

UPDATE employees_flat
SET department_lead = 'Minh'
WHERE employee_id = 101;

SELECT employee_id, department_id, department_lead
FROM employees_flat
WHERE department_id = 10
ORDER BY employee_id;
-- 101 -> Minh, 102 -> Bình: the same department has two leads.

ROLLBACK;
~~~

**Insertion anomaly:** department **30 – Operations** cannot be recorded before it has any employees, because the table requires an **employee_id**.

**Deletion anomaly:** deleting employee 103 removes the only row storing the name **Engineering** and lead **Hà** for department 20.

A single statement `UPDATE ... WHERE department_id = 10` can avoid missing rows in one specific operation. Still, the design forces every write path—including other services, manual edits, or external integrations—to keep copies of the same fact synchronized. Separating the dependency **removes the burden of copy synchronization directly at the storage structure level**.

## 3. Precise Definition of 3NF

Before applying 3NF, keep four concepts clear:

| Concept | Explanation | Example in **employees_flat** |
| --- | --- | --- |
| **Superkey** | A set of attributes that uniquely identifies a row | **{employee_id}** or any superset containing it |
| **Candidate key** | A minimal superkey; removing any component loses unique row identification | **{employee_id}** |
| **Prime attribute** | Belongs to **at least one** candidate key | **employee_id** |
| **Non-prime attribute** | Does not belong to any candidate key | **employee_name**, **department_id**, **department_name**, **department_lead** |

**Formal definition:** a relation **R** is in **3NF** if, for **every non-trivial functional dependency** of the form **X → A**, where **A** is a single attribute, **at least one** of the following two conditions holds:

1. **X is a superkey of R**; or
2. **A is a prime attribute**, meaning it belongs to at least one candidate key of R.

*Non-trivial* means **A is not in X**. This condition is evaluated over all functional dependencies that truly hold under the business rules, including dependencies inferred from known rules.

Equivalently in common teaching, 3NF builds on 2NF by eliminating invalid transitive dependencies between non-key attributes, though that phrasing is a **rule of thumb** rather than an exact test for tables with multiple candidate keys.

### 3.1. Applying 3NF to the Employee Table

Examine **department_id → department_name**:

- This dependency is **non-trivial**: the department name is not in the left-hand side.
- **department_id** is not a superkey of **employees_flat**, because one department has many employees.
- **department_name** does not belong to any candidate key, so it is a non-prime attribute.

Because **both conditions fail**, the relation **does not satisfy 3NF**. The same reasoning applies to **department_id → department_lead**.

By contrast, **employee_id → employee_name, department_id** are valid under 3NF because **employee_id** is a candidate key.

## 4. Decomposing by Fact Ownership

Each fact should be stored at its proper grain:

- **departments**: each row is **one department**, holding its name and lead.
- **employees**: each row is **one employee**, holding employee name and **department_id** referencing the department.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "has"
    DEPARTMENTS {
        bigint department_id PK
        varchar department_name
        varchar department_lead
    }
    EMPLOYEES {
        bigint employee_id PK
        varchar employee_name
        bigint department_id FK
    }
~~~

### 4.1. SQL Schema with Keys and Constraints

~~~sql
CREATE TABLE departments (
    department_id   BIGINT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL,
    department_lead VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    employee_id   BIGINT PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    department_id BIGINT NOT NULL
        REFERENCES departments(department_id)
);

INSERT INTO departments
    (department_id, department_name, department_lead)
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

The primary key of **departments** represents **department_id → department_name, department_lead** in exactly one department row. The primary key of **employees** represents **employee_id → employee_name, department_id**. The foreign key requires each employee to reference an existing department.

In this minimal example, **department_lead** is a display name. If the lead is an employee, a real-world model would likely need **lead_employee_id** as a foreign key along with appropriate rules; a plain name is insufficient to uniquely identify a person.

### 4.2. Re-testing the Three Operations

**Inserting a department with no employees yet:**

~~~sql
INSERT INTO departments
    (department_id, department_name, department_lead)
VALUES (30, 'Operations', 'Lan');
~~~

**Updating department 10's lead in exactly one record:**

~~~sql
UPDATE departments
SET department_lead = 'Minh'
WHERE department_id = 10;
~~~

**Deleting the last employee in department 20:**

~~~sql
DELETE FROM employees
WHERE employee_id = 103;

SELECT department_id, department_name
FROM departments
WHERE department_id = 20;
-- Department 20: Engineering still exists.
~~~

**Reading employees together with department information:**

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name,
    d.department_lead
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

The join produces a *read result* containing the same columns as the flat table, while the department facts are stored only once. To also include departments that have no employees yet, start the query from **departments** and use a **LEFT JOIN**.

## 5. Verifying the Decomposition: Lossless Join and Dependency Preservation

Simply splitting a table into smaller tables is not automatically right. A sound decomposition should consider at least two properties:

1. **Lossless-join decomposition:** when joining the decomposed tables on their shared attributes under valid dependencies, the original relation is reconstructed without generating spurious tuples or losing original tuples.
2. **Dependency preservation:** important functional dependencies can be enforced within individual component tables without having to join all data to validate them.

### 5.1. Why Is the Example Decomposition Lossless?

Denote the attribute sets of the original and decomposed relations:

~~~text
R(employee_id, employee_name,
  department_id, department_name, department_lead)

R1(employee_id, employee_name, department_id)  -- employees
R2(department_id, department_name, department_lead)  -- departments
~~~

The intersection of the two attribute sets is **{department_id}**. The dependency **department_id → department_name, department_lead** shows that the shared attribute set determines **all of R2**. Therefore, by the binary decomposition test, **R1 ⋈ R2** is a lossless join for every original state satisfying the stated functional dependencies.

Each employee row matches **at most one** department row; when the original data is valid and the foreign key is enforced, it matches **exactly one** department row. A department added later without employees yet can still reside in **departments**; such departments do not generate spurious employee rows under an **INNER JOIN**.

A common decomposition bug is joining on a non-unique attribute, causing one row in the first table to pair with multiple rows in the second table and produce spurious rows. That is why functional dependencies and keys must be established before splitting.

### 5.2. Why Are the Key Dependencies Preserved?

~~~text
employees:
  employee_id   -> employee_name, department_id

departments:
  department_id -> department_name, department_lead
~~~

Each dependency is enforced inside a single table by its respective key/superkey. The DBMS does not need to perform a join to detect a department ID having two conflicting department rows.

**Lossless join** and **dependency preservation** are not synonymous: some decompositions are lossless yet cannot preserve all dependencies using single-table constraints alone. When choosing between 3NF and stricter normal forms—especially **BCNF**—both properties must be weighed.

## 6. Special Case: 3NF Permits Some Dependencies Without a Superkey on the Left

The maxim "every non-key attribute must depend directly on the key" is helpful in simple examples, yet can mislead when a table has **multiple candidate keys**.

Consider an abstract relation **R(A, B, C)** with the functional dependencies:

~~~text
AB -> C
C  -> B
~~~

Assume there are no additional business functional dependencies beyond what follows logically from those two rules.

### 6.1. Finding All Candidate Keys

- **AB** determines **C**, so **AB** determines A, B, and C, making it a candidate key.
- **AC** determines **B** via **C → B**, so **AC** is also a candidate key.
- No single attribute determines all of A, B, and C.

The candidate keys are **AB** and **AC**. **A**, **B**, and **C** are all **prime attributes**, because each belongs to at least one candidate key.

### 6.2. Evaluating 3NF and BCNF

Examine **C → B**:

- C is **not** a superkey, because C does not determine A.
- B **is a prime attribute**, because B belongs to candidate key AB.

Thus, this dependency **is permitted in 3NF** under the condition "the right-hand side is a prime attribute." The relation satisfies **3NF** under the assumed dependencies, yet **does not satisfy BCNF**, because BCNF requires the left-hand side of **every non-trivial functional dependency** to be a superkey.

| Criterion | 3NF | BCNF |
| --- | --- | --- |
| Dependency **AB → C** | Valid: AB is a superkey | Valid: AB is a superkey |
| Dependency **C → B** | Valid: B is a prime attribute | **Invalid:** C is not a superkey |

This illustrates why **3NF does not eliminate every form of redundancy**. It allows certain structures to make **dependency preservation** easier.

If we decompose this example into **R1(C, B)** and **R2(A, C)**, the join is lossless because **C → B**, yet **AB → C** can no longer be enforced within a single component table alone. Never mechanically apply "see a dependency, split it" while overlooking the constraints that must remain enforceable.

## 7. Practical Workflow for Normalizing to 3NF

### Step 1: Define Grain and Attributes

Ask whether a row represents **an employee**, **a transaction**, **a product**, or **a line item**. Two columns with the same name do not necessarily share the same temporal meaning or determining rule.

### Step 2: List Business Functional Dependencies

Write down rules such as **department_id → department_name**; do not infer them from sample data alone. Ask whether a department ID can change names over time, whether an employee can belong to multiple departments simultaneously, or whether a product code can ever be reused.

### Step 3: Find All Candidate Keys and Mark Prime Attributes

Do not inspect only **PRIMARY KEY**. A table with a surrogate key **id** can still carry a composite business candidate key, such as **(order_id, line_no)** protected by **UNIQUE** and **NOT NULL**. Adding **id** does not magically remove existing functional dependencies or bring a table into 3NF.

### Step 4: Apply the 3NF Condition

For each non-trivial dependency **X → A**, check:

1. **Is X a superkey?** If yes, the dependency satisfies the condition.
2. If not, **does A belong to at least one candidate key?** If yes, the dependency is still permitted in 3NF.
3. If neither holds, it is a 3NF violation that must be addressed.

Do not judge 3NF solely by asking whether A "is in the primary key"; **prime attributes** are defined across **all candidate keys**.

### Step 5: Decompose and Add Constraints

Move attributes determined by **department_id** to the **departments** table; keep **department_id** as a foreign key in **employees**. Choose appropriate keys and enforce **NOT NULL**, **CHECK**, **UNIQUE**, and foreign keys according to business rules. If using the 3NF synthesis algorithm for a complex dependency set, you can:

1. Find a **minimal cover** of the functional dependencies.
2. Form relations covering the dependencies in the cover, merging compatible relations with the same determinant.
3. Drop relations whose attribute set is completely contained within another relation when appropriate.
4. If no resulting relation contains **a candidate key** of the original relation, add a relation containing a candidate key.

Under the standard conditions and construction of the 3NF synthesis algorithm, the result achieves **lossless join and dependency preservation**. In real projects, still cross-check against business semantics, foreign keys, and constraints that cannot be expressed by functional dependencies alone.

### Step 6: Test Operations and Physical Needs

Test inserting a parent entity with no children yet, updating a fact in one place, deleting the last child record, and running summary queries after decomposition. Then evaluate common joins and needed indexes; indexing choices do not replace proper relational design.

For example, if the application frequently filters employees by department, consider:

~~~sql
CREATE INDEX idx_employees_department_id
ON employees (department_id);
~~~

This index supports predicates on **department_id** and can aid joins; actual effectiveness must be evaluated against query plans and data volume.

## 8. Distinguishing Dependencies to Separate from Intentional Historical Data

Sometimes two columns look redundant yet express **facts at different points in time**.

Suppose **products(product_id, current_price)** holds the current price and **order_lines(order_id, line_no, product_id, unit_price_at_order)** records the price locked in when the order was placed. You must not impose **product_id → unit_price_at_order** simply because multiple orders share a product: purchase price may depend on time, promotions, or specific contracts.

| Situation | Fact Owner | How to Handle |
| --- | --- | --- |
| Current department name on every employee | Department | Move to **departments** for a single authoritative source |
| Current catalog price of a product | Product or active price list | Place in the appropriate pricing entity/rule |
| Locked-in order price | Order line or transaction terms | Keep as a historical transaction fact |
| Data copy in a read/analytical table | Source operational system and sync pipeline | Can intentionally denormalize, provided the authoritative source and acceptable lag are defined |

For effective-dated historical data, functional dependencies may need to include time or version attributes—for instance, **(department_id, effective_from) → department_name** in a history design with explicit temporal rules. Do not impose current-state dependencies onto historical records.

3NF evaluates **a relation together with its business functional dependencies**. Document, graph, or analytical warehouse models may choose different structures due to different query and update patterns; comparisons should rest on constraints, source of truth, read/write cost, and evolvability.

## 9. Exercise: Orders and Customer Information

Consider the table:

| order_id | order_date | customer_id | customer_name | customer_tier |
| --- | --- | --- | --- | --- |
| O01 | 2026-11-20 | C01 | An | GOLD |
| O02 | 2026-11-21 | C01 | An | GOLD |
| O03 | 2026-11-21 | C02 | Bình | SILVER |

Assume:

- **order_id** determines an order, its order date, and the customer who placed it.
- **customer_id** determines the customer's **current** name and membership tier.
- A customer can place multiple orders; a membership tier can change without modifying existing order records.

**Tasks:**

1. Determine the grain and candidate key of the table; explain why the table already satisfies 2NF.
2. Write the key functional dependencies. Which dependencies violate the 3NF definition and why?
3. Give one insertion, update, or deletion scenario that could cause an anomaly.
4. Decompose into **customers** and **orders** tables, specifying primary keys and foreign keys.
5. If the business needs to know the **membership tier at the exact time the order was placed**, should that value be updated whenever the customer changes tiers?

<details>
<summary>Suggested Solution</summary>

The grain is **one order**; the candidate key under the assumptions is **order_id** (a single attribute), so there are no ordinary partial dependencies and it satisfies 2NF.

~~~text
order_id    -> order_date, customer_id
customer_id -> customer_name, customer_tier
~~~

The dependency **customer_id → customer_name, customer_tier** violates 3NF in the flat table: **customer_id** is not a superkey and the two right-hand attributes are non-prime. When customer C01 changes tier, updating only O01 leaves O02 with the old tier. When a customer has no orders yet, the table cannot represent the new customer.

One possible decomposition:

~~~sql
CREATE TABLE customers (
    customer_id   VARCHAR(10) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_tier VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    order_id     VARCHAR(10) PRIMARY KEY,
    order_date   DATE NOT NULL,
    customer_id  VARCHAR(10) NOT NULL
        REFERENCES customers(customer_id)
);
~~~

If the tier **at order placement time** is required, model **tier_at_order** explicitly as a historical fact of the order, or use tier history records with appropriate effective intervals. **Do not** overwrite historical values when the current tier changes. Decide based on audit and reporting requirements.

</details>

## 10. Common Misconceptions to Avoid

| Misconception | Key Takeaway |
| --- | --- |
| "Once in 2NF, there are no anomalies left." | 2NF mainly eliminates partial dependencies on candidate keys; transitive dependencies causing redundancy can still remain. |
| "Every transitive dependency violates 3NF." | Check the **formal definition**: X is a superkey or A is a prime attribute; do not judge from dependency chain shape alone. |
| "Only check columns outside the primary key." | An attribute may belong to **another candidate key** and therefore still be prime. |
| "Adding a single ID key achieves 3NF." | A surrogate key does not alter the underlying business functional dependencies. |
| "Changing column types or adding indexes fixes transitive dependencies." | Data types and indexes do not move facts back to the entity that owns them. |
| "The more tables you split into, the better." | Decomposition must be checked for **lossless join**, dependency preservation, and business goals. |
| "Two identical values in different tables are always wrong." | Historical snapshots, transaction records, and read replicas carry distinct semantics, requiring clear source-of-truth and sync rules. |

## 11. Key Takeaways

**3NF** requires every non-trivial functional dependency **X → A** to satisfy either **X is a superkey** or **A is a prime attribute**. In business schemas with simple candidate keys, the telltale sign is an attribute like **department_name** depending on **department_id** rather than on the employee; extracting a departments table removes duplication and reduces insertion, update, and deletion anomalies.

Good design starts from **grain, candidate keys, functional dependencies, and temporal semantics**, before decomposing and adding constraints. Verify **lossless join** and **dependency preservation** before finalizing the physical schema; only then tune indexes or consider intentional denormalization. **3NF is a clear criterion for verifying relational structure, not a promise that all data risks vanish in every model.**
