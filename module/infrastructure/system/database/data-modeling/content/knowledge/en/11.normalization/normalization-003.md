# Second Normal Form and Eliminating Partial Dependencies on Candidate Keys

**Second Normal Form (2NF)** eliminates a classic source of redundancy in relational models: attributes that describe **only part of a candidate key** yet are stored on every row of the full key. As data grows, such a design forces the application to update multiple copies of the same fact and can cause insertion, update, or deletion anomalies.

In translating business requirements into a data model, 2NF guides the designer to answer two questions: **what uniquely identifies a record**, and **does this attribute truly describe the entire record or only one entity participating in the record**? This lesson covers identifying candidate keys, spotting partial dependencies, performing verifiable table decomposition, and distinguishing 2NF from higher normal forms.

## 1. Scenario: An Enrollment Row Containing Information About Three Entities

A training system has the following business rules:

- Each student has a stable **student_id** and a current name.
- Each course has a stable **course_id** and a current course title.
- A student can enroll in multiple courses; a course can have multiple students.
- In this example, a student enrolls in a given course **at most once**.
- A grade belongs to **a specific student's enrollment in a specific course** and may not be graded yet.
- Students and courses can be created before any enrollment exists.

The initial design puts all information into the **enrollments_flat** table:

| student_id | student_name | course_id | course_title | score |
| --- | --- | --- | --- | ---: |
| S01 | An | C10 | SQL Fundamentals | 9 |
| S01 | An | C20 | Java Fundamentals | 8 |
| S02 | Bình | C10 | SQL Fundamentals | 7 |
| S03 | Chi | C30 | Data Design | 9 |

The **grain** of the table is *one student–course pair*. The natural candidate key is **(student_id, course_id)** because a pair appears at most once, whereas **student_id** or **course_id** individually can appear multiple times.

An illustrative schema (PostgreSQL):

~~~sql
CREATE TABLE enrollments_flat (
    student_id    VARCHAR(10) NOT NULL,
    student_name  VARCHAR(100) NOT NULL,
    course_id     VARCHAR(10) NOT NULL,
    course_title  VARCHAR(150) NOT NULL,
    score         NUMERIC(4, 2)
                  CHECK (score BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);

INSERT INTO enrollments_flat
    (student_id, student_name, course_id, course_title, score)
VALUES
    ('S01', 'An',   'C10', 'SQL Fundamentals',  9),
    ('S01', 'An',   'C20', 'Java Fundamentals', 8),
    ('S02', 'Bình', 'C10', 'SQL Fundamentals',  7),
    ('S03', 'Chi',  'C30', 'Data Design',       9);
~~~

Every cell holds a single value, there is a primary key, and no list is crammed into one cell. The table may satisfy **1NF** practice, yet it still fails **2NF** because student and course details are copied across every enrollment.

## 2. Candidate Keys, Prime Attributes, and Functional Dependencies

To evaluate 2NF accurately, distinguish the following concepts.

| Concept | Meaning | Example in the Enrollment Table |
| --- | --- | --- |
| **Superkey** | A set of attributes sufficient to uniquely identify a row | **(student_id, course_id)** or a larger set adding **score** |
| **Candidate key** | A **minimal** superkey: removing any attribute from the key loses unique identification | **(student_id, course_id)** |
| **Primary key** | A candidate key chosen as the primary identifier in the schema | **PRIMARY KEY (student_id, course_id)** |
| **Prime attribute** | Belongs to **at least one** candidate key | **student_id**, **course_id** |
| **Non-prime attribute** | Does not belong to **any** candidate key | **student_name**, **course_title**, **score** |
| **Functional dependency X → Y** | Each value of X determines at most one value of Y in every valid state of the relation | **student_id → student_name** |

Candidate keys must be derived from **business rules**, not merely from the fact that existing rows happen to be distinct. For example, if the system allows a student to retake the same course multiple times, **(student_id, course_id)** no longer suffices to identify an enrollment; you may need **attempt_no**, **enrollment_id**, or another concept of an enrollment attempt.

### 2.1. Functional Dependencies in the Example

According to the business requirements:

~~~text
student_id                  -> student_name
course_id                   -> course_title
(student_id, course_id)     -> score
~~~

Visualized:

~~~mermaid
flowchart TD
    K["Candidate key: (student_id, course_id)"]
    S["student_id"]
    C["course_id"]
    N["student_name"]
    T["course_title"]
    G["score"]
    K --> S
    K --> C
    K --> G
    S --> N
    C --> T
~~~

**score** is an attribute of the enrollment: you cannot know the grade from the student alone or from the course alone. By contrast, **student_name** is determined by **student_id** without **course_id**; **course_title** is determined by **course_id** without **student_id**.

This is the exact signature of a **partial dependency**.

### 2.2. Full Dependency vs. Partial Dependency

Suppose **K** is a candidate key and **A** is a non-prime attribute.

- **A is fully functionally dependent on K** if **K → A** and **no proper subset of K** also determines A.
- **A is partially functionally dependent on K** if there exists a proper subset **X ⊂ K** such that **X → A**.

For the key **K = (student_id, course_id)**:

| Attribute | Dependency Observed from Business Rules | Conclusion |
| --- | --- | --- |
| **student_name** | **student_id → student_name** | Partially dependent on K |
| **course_title** | **course_id → course_title** | Partially dependent on K |
| **score** | Requires both **student_id** and **course_id** to determine | Fully dependent on K |

It is not enough to say "the full key determines every column," because that property holds for any key by definition. You must test **removing components of the key one by one** and see whether the remaining subset still determines the attribute under review.

## 3. Definition of 2NF and When It Applies

A relation is in **2NF** when:

1. The relation is in **First Normal Form (1NF)**.
2. **Every non-prime attribute is fully functionally dependent on every candidate key**; in other words, no non-prime attribute is functionally dependent on **a proper subset** of any candidate key.

The phrase **every candidate key** is crucial. Evaluating only the primary key can overlook another candidate key. Likewise, 2NF speaks specifically about **non-prime attributes**: not every dependency involving prime attributes is automatically a 2NF violation.

### 3.1. Why Do Tables with Composite Keys Require Close Inspection?

If a relation has only **single-attribute** candidate keys, there is no **non-empty** proper subset of a key to form an ordinary partial dependency; a relation already in 1NF satisfies 2NF under common evaluation. Edge cases involving dependencies from the empty set (constant attributes) fall under formal definitions, though they are uncommon in ordinary business modeling.

With a composite key, data in the table may be describing **each side of a relationship** alongside **the relationship itself**. In that situation, check which entity each attribute truly belongs to.

**Note:** a single-column primary key is **not sufficient** to conclude 2NF if the table also has another **composite candidate key**. Section 6 illustrates this.

### 3.2. Three Anomalies Caused by Partial Dependencies

In **enrollments_flat**, try three business changes:

**Updating a student's name:** An changes her display name to An Nguyễn. If only the C10 row is updated, the same **student_id = S01** ends up with two different names.

~~~sql
BEGIN;

UPDATE enrollments_flat
SET student_name = 'An Nguyễn'
WHERE student_id = 'S01' AND course_id = 'C10';

SELECT student_id, course_id, student_name
FROM enrollments_flat
WHERE student_id = 'S01'
ORDER BY course_id;

ROLLBACK;
~~~

**Inserting a course with no students yet:** there is no way to add **C40 – Data Analysis** without creating a dummy enrollment row, because the table requires **student_id**.

**Deleting the last enrollment:** when deleting row **(S03, C30)**, the system also loses the course title **C30 – Data Design** unless a copy exists outside the table.

The issue is not column naming or whether the SQL statement is short or long. **A fact belonging to a student or a course is tied to the lifecycle of an enrollment record**, causing updates and deletes to have unintended side effects.

## 4. Decomposing to Eliminate Partial Dependencies

The fix is to place each fact in a table with the **right grain**:

- **students**: one row per student, owning **student_name**.
- **courses**: one row per course, owning **course_title**.
- **enrollments**: one row per student–course pair, owning **score**.

~~~mermaid
erDiagram
    STUDENTS ||--o{ ENROLLMENTS : "enrolls in"
    COURSES  ||--o{ ENROLLMENTS : "has students"
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    COURSES {
        varchar course_id PK
        varchar course_title
    }
    ENROLLMENTS {
        varchar student_id PK, FK
        varchar course_id PK, FK
        numeric score
    }
~~~

### 4.1. Relational Schema

~~~sql
CREATE TABLE students (
    student_id   VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id    VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(150) NOT NULL
);

CREATE TABLE enrollments (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    course_id VARCHAR(10) NOT NULL
        REFERENCES courses(course_id),
    score NUMERIC(4, 2)
        CHECK (score BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'),
    ('S02', 'Bình'),
    ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'SQL Fundamentals'),
    ('C20', 'Java Fundamentals'),
    ('C30', 'Data Design');

INSERT INTO enrollments (student_id, course_id, score) VALUES
    ('S01', 'C10', 9),
    ('S01', 'C20', 8),
    ('S02', 'C10', 7),
    ('S03', 'C30', 9);
~~~

The **composite primary key** ensures each student can enroll in the same course only once per the example's assumption. **Foreign keys** prevent creating enrollments for nonexistent students or courses. The **score** column allows **NULL** to represent an ungraded enrollment; **CHECK** rejects out-of-range values whenever a grade is provided.

### 4.2. Business Operations After Decomposition

**Updating a student's name in one place:**

~~~sql
UPDATE students
SET student_name = 'An Nguyễn'
WHERE student_id = 'S01';
~~~

**Creating a new course with no students yet:**

~~~sql
INSERT INTO courses (course_id, course_title)
VALUES ('C40', 'Data Analysis');
~~~

**Deleting an enrollment while keeping the course:**

~~~sql
DELETE FROM enrollments
WHERE student_id = 'S03' AND course_id = 'C30';

SELECT course_id, course_title
FROM courses
WHERE course_id = 'C30';
-- C30 still exists, even with no remaining enrollments.
~~~

**Reading back combined information in flat form for the UI:**

~~~sql
SELECT
    e.student_id,
    s.student_name,
    e.course_id,
    c.course_title,
    e.score
FROM enrollments AS e
JOIN students AS s
    ON s.student_id = e.student_id
JOIN courses AS c
    ON c.course_id = e.course_id
ORDER BY e.student_id, e.course_id;
~~~

In a production system, the application may need indexes tailored to queries. For example, **PRIMARY KEY (student_id, course_id)** efficiently supports finding enrollments for a given student. If you frequently fetch the roster of students per course, consider:

~~~sql
CREATE INDEX idx_enrollments_course
ON enrollments (course_id, student_id);
~~~

Indexes are **physical modeling and performance** decisions made after defining the proper relations and constraints; an index by itself cannot fix a partial dependency.

### 4.3. Why Does This Decomposition Preserve Meaning?

The three tables store three types of facts at three clear grains. With the key constraints above, when joining **enrollments → students** on **student_id**, each enrollment row matches exactly one student; when joining **courses** on **course_id**, each row matches exactly one course. Thus, for valid enrollments, the join reconstructs every original enrollment row without generating spurious enrollment pairs.

The functional dependencies are directly protected:

~~~text
students:
    student_id -> student_name

courses:
    course_id -> course_title

enrollments:
    (student_id, course_id) -> score
~~~

Splitting the tables also preserves students or courses that do not yet have enrollments—a state the flat table could not represent. When a query needs **even courses with no students**, start from **courses** and use a **LEFT JOIN**:

~~~sql
SELECT
    c.course_id,
    c.course_title,
    COUNT(e.student_id) AS enrollment_count
FROM courses AS c
LEFT JOIN enrollments AS e
    ON e.course_id = c.course_id
GROUP BY c.course_id, c.course_title
ORDER BY c.course_id;
~~~

The result includes **C40** with **enrollment_count = 0**. Do not use **COUNT(*)** in this example to count enrollments, because **LEFT JOIN** still emits one row for a course with no enrollments.

## 5. Identifying Partial Dependencies Using Rules and Data

Always start from the **business specification**, then confirm against data:

1. **Identify the grain:** does one row in the table represent a student, a course, an enrollment pair, or an exam attempt?
2. **List candidate keys:** which minimal sets of attributes uniquely identify a row **across all valid states**?
3. **Mark non-prime attributes:** which columns do not belong to any candidate key?
4. **Write functional dependencies:** e.g., **student_id → student_name**, **course_id → course_title**.
5. **Test proper subsets of every candidate key:** does part of a key already determine a non-prime attribute?
6. **Design tables that own their facts:** keep entity attributes in entity tables and relationship attributes in the association table.
7. **Verify constraints and joins:** each table has a key, links have foreign keys, and business queries remain accurate after decomposition.

You can check for **signs of inconsistency** in legacy tables:

~~~sql
-- A student_id appearing with multiple student_name values.
SELECT student_id, COUNT(DISTINCT student_name) AS name_count
FROM enrollments_flat
GROUP BY student_id
HAVING COUNT(DISTINCT student_name) > 1;

-- A course_id appearing with multiple course_title values.
SELECT course_id, COUNT(DISTINCT course_title) AS title_count
FROM enrollments_flat
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1;
~~~

These queries detect cases where data already contradicts the expected functional dependencies. **Zero returned rows does not prove 2NF compliance**: a table might happen to be consistent by coincidence, while its structure still permits discrepancies as business data changes.

## 6. Common Pitfall: Inspecting Only the Primary Key and Missing Other Candidate Keys

Suppose a development team replaces the composite primary key with **enrollment_id** and adds a unique constraint on the student–course pair:

~~~sql
CREATE TABLE enrollments_with_id_flat (
    enrollment_id BIGINT PRIMARY KEY,
    student_id VARCHAR(10) NOT NULL,
    student_name VARCHAR(100) NOT NULL,
    course_id VARCHAR(10) NOT NULL,
    course_title VARCHAR(150) NOT NULL,
    score NUMERIC(4, 2),
    UNIQUE (student_id, course_id)
);
~~~

Assuming each student–course pair enrolls at most once, this table has **two candidate keys**:

- **(enrollment_id)**, a single-attribute candidate key chosen as the primary key.
- **(student_id, course_id)**, a composite candidate key enforced by **UNIQUE** and **NOT NULL**.

**student_name** still depends on **student_id**; **course_title** still depends on **course_id**. These are partial dependencies on the composite candidate key **(student_id, course_id)**, so the table **still violates 2NF** even though its primary key is a single column.

The **NOT NULL** condition matters when inferring candidate keys from **UNIQUE** in SQL: some DBMSs allow multiple rows containing **NULL** in columns declared **UNIQUE**; such a constraint is not equivalent to a full candidate key unless nullability is addressed.

Adding a **surrogate key** is useful for identification and referencing, yet it **does not automatically eliminate business dependencies**. You must review all candidate keys, including natural keys enforced by unique constraints.

## 7. Distinguishing 2NF from 1NF and 3NF

| Normal Form | Core Question | Example of Remaining Issues |
| --- | --- | --- |
| **1NF** | Are values properly represented by domain, avoiding hiding independently managed collections in one cell? | Enrollment table has scalar values but repeats **student_name** across courses |
| **2NF** | Is every **non-prime** attribute **fully dependent on every candidate key**? | Enrollment table violates due to **student_id → student_name** and **course_id → course_title** |
| **3NF** | Are there dependencies where a non-key attribute depends through another non-key attribute, or other formal 3NF violations? | Employee table has **employee_id → department_id → department_name** |

The following example has a single-column candidate key and, under standard rules, is already in **2NF**, yet still has a transitive dependency causing redundancy:

~~~text
employees(
    employee_id PRIMARY KEY,
    employee_name,
    department_id,
    department_name
)

employee_id  -> employee_name, department_id
department_id -> department_name
~~~

**department_name** depends on **department_id**, not on the employee directly. Storing the department name on every employee row can cause update anomalies. However, **department_id** is not a subset of the candidate key **(employee_id)**; hence this is not a **partial key dependency** example, but an issue addressed by 3NF.

More precisely, Third Normal Form constrains non-trivial functional dependencies **X → A**: either **X** is a superkey **or** **A** is a prime attribute. In many problems with simple candidate keys, this is commonly taught by removing transitive dependencies between non-key attributes.

### Historical Data Is Not Necessarily Bad Redundancy

Suppose every order line item has **unit_price_at_order**. This price belongs to **the moment the order was placed**, which may differ from the currently listed product price. You must not assume a dependency **product_id → unit_price_at_order** merely because multiple lines sell the same product. If transaction pricing varies by customer, promotion, or time, it is a fact belonging to the **order line**.

Similarly, when designing flattened analytical tables or documents, a system may intentionally duplicate data to serve queries. In that case, document the **source of truth, effective time, and synchronization mechanism**. 2NF is a criterion for evaluating relational structure against functional dependencies, not an absolute ban on identical values or embedded models.

## 8. Practice Exercise: Order Details

A sales system stores:

| order_id | order_date | product_id | product_name | quantity |
| --- | --- | --- | --- | ---: |
| O01 | 2026-11-22 | P10 | Keyboard | 2 |
| O01 | 2026-11-22 | P20 | Mouse | 1 |
| O02 | 2026-11-22 | P10 | Keyboard | 1 |

Assume each order contains multiple products, each product appears **at most once per order**, **order_id** determines the order date, and **product_id** determines the current product name.

**Questions:**

1. What is the grain of the table? What candidate key is appropriate?
2. Write the key functional dependencies for **order_date**, **product_name**, and **quantity**.
3. Which attributes are partially dependent and why?
4. Propose tables to achieve 2NF, specifying primary keys and foreign keys.
5. If you add **order_item_id** as the primary key while keeping **UNIQUE(order_id, product_id)**, can you keep **order_date** and **product_name** in the merged table and automatically achieve 2NF?

<details>
<summary>Suggested Solution</summary>

**Grain:** one product within one order. Candidate key **(order_id, product_id)** assuming each product appears only once per order.

~~~text
order_id                 -> order_date
product_id               -> product_name
(order_id, product_id)   -> quantity
~~~

**order_date** depends solely on **order_id**, and **product_name** depends solely on **product_id**; both are non-prime attributes and violate 2NF. **quantity** depends on the full key pair under the given assumptions.

It can be decomposed into:

~~~text
orders(
    order_id PRIMARY KEY,
    order_date
)

products(
    product_id PRIMARY KEY,
    product_name
)

order_items(
    order_id REFERENCES orders(order_id),
    product_id REFERENCES products(product_id),
    quantity CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
)
~~~

Adding **order_item_id** does not resolve the violation if **(order_id, product_id)** remains a composite candidate key. Attributes belonging to orders and products must be separated. If the business allows repeating the same product across multiple lines in one order, revise the identification assumption and consider **line_no** or **order_item_id**.

</details>

## 9. Common Conceptual Mistakes to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "Having a **PRIMARY KEY** automatically means 2NF." | A key only protects row identity; you must check functional dependencies of non-prime attributes. |
| "You only need to check the primary key." | The 2NF definition checks **all candidate keys**, including natural keys other than the primary key. |
| "Every table with a composite key violates 2NF." | Composite keys are normal; a table satisfies 2NF when non-prime attributes are determined only by the **full key**. |
| "It is enough that the full key determines an attribute." | You must verify that **no proper subset of the key** also determines that attribute. |
| "A table with a single-column key cannot have anomalies." | A table can satisfy 2NF and still suffer from transitive dependencies, 3NF issues, or other constraint gaps. |
| "Once split, foreign keys are optional." | Decomposition creates relationships that must be protected by keys and referential constraints. |
| "Checking a few rows with no conflicts proves normalization." | Functional dependencies must follow from **rules across all valid states**, not just the current data sample. |

## 10. Conclusion

**2NF requires non-prime attributes to be fully functionally dependent on every candidate key**. If an attribute is determined by only part of a composite candidate key, it usually describes an entity or concept with its own lifecycle. Moving that attribute to the appropriate table reduces duplication, prevents insertion/update/deletion anomalies, and enables enforcing business rules directly via primary keys, foreign keys, and domain checks.

When applying this to data design, start from the **grain, all candidate keys, and functional dependencies**, before deciding on decomposition and physical optimizations. Achieving 2NF resolves partial dependencies; you still need to examine **3NF, BCNF**, historical data needs, and query patterns to choose a schema that can evolve and be verified cleanly.
