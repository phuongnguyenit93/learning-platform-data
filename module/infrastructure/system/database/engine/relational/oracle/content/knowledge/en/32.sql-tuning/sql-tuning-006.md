# Tuning EXISTS, NOT EXISTS, and Handling Many-to-Many Relationships in Oracle

## 1. Existence problems in SQL

Many business queries do not need to retrieve columns from a related table. They only need to answer: does a customer have an unpaid order, has a student enrolled in a course, does a user have no permissions, or does a product have no inventory row in the target warehouse?

SQL provides two constructs that express this directly:

- **EXISTS:** true when the subquery returns at least one row.
- **NOT EXISTS:** true when the subquery returns zero rows.

Oracle can optimize these patterns into a **semijoin** or **antijoin**. These join types only need to determine whether an outer row has a match; they do not duplicate outer rows by the number of matches like a regular join.

That is why EXISTS and NOT EXISTS are useful when querying many-to-many relationships. They usually express business intent more accurately than JOIN combined with DISTINCT or GROUP BY, while avoiding bugs caused by duplicates and NULLs.

> Content focuses on Oracle Database 19c. The optimizer can transform subqueries into various execution plans; there is no guarantee every EXISTS query will use the exact same join method. Verify using the cursor plan and runtime metrics.

## 2. Many-to-many relationship model

A many-to-many (M:N) relationship occurs when one row in table A can link to multiple rows in table B, and one row in table B can also link to multiple rows in table A.

Example of students and courses:

- A student enrolls in multiple courses.
- A course has multiple enrolled students.

We model this relationship using a junction table `STUDENT_COURSES`:

~~~text
STUDENTS                 STUDENT_COURSES                 COURSES
---------                ----------------                -------
student_id  PK  1 ----<  student_id   FK   >---- 1       course_id PK
name                     course_id    FK                 course_name
                         enrolled_at
                         status

One student has many link rows.
One course has many link rows.
~~~

### 2.1. Creating tables and constraints

~~~sql
CREATE TABLE students (
    student_id NUMBER CONSTRAINT students_pk PRIMARY KEY,
    full_name  VARCHAR2(100) NOT NULL
);

CREATE TABLE courses (
    course_id   NUMBER CONSTRAINT courses_pk PRIMARY KEY,
    course_code VARCHAR2(20) NOT NULL,
    course_name VARCHAR2(200) NOT NULL,
    CONSTRAINT courses_code_uk UNIQUE (course_code)
);

CREATE TABLE student_courses (
    student_id NUMBER NOT NULL,
    course_id  NUMBER NOT NULL,
    enrolled_at DATE DEFAULT SYSDATE NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT student_courses_pk
        PRIMARY KEY (student_id, course_id),
    CONSTRAINT student_courses_student_fk
        FOREIGN KEY (student_id) REFERENCES students(student_id),
    CONSTRAINT student_courses_course_fk
        FOREIGN KEY (course_id) REFERENCES courses(course_id),
    CONSTRAINT student_courses_status_ck
        CHECK (status IN ('ACTIVE', 'CANCELLED', 'COMPLETED'))
);
~~~

The composite primary key `(student_id, course_id)` ensures a student has at most one relationship with a given course under this simple model. If business logic requires storing multiple enrollments across different terms, the key must include term/attempt or use a dedicated `enrollment_id` with a suitable unique constraint.

### 2.2. Junction tables can carry business attributes

A junction table does not only store two foreign keys. It can store enrollment date, status, grade, role, start/end timestamps, or creation source. These attributes belong to the M:N relationship itself, not exclusively to STUDENTS or COURSES.

### 2.3. Avoid storing key lists in a single column

Do not store `course_ids = '10,20,30'` in a single column of STUDENTS and use LIKE or string parsing to find relationships. Doing so forfeits foreign keys, unique constraints, per-key indexes, and consistent data validation.

## 3. EXISTS: checking whether at least one relationship exists

### 3.1. Syntax

~~~sql
SELECT ...
FROM outer_table o
WHERE EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = o.key
);
~~~

The subquery typically contains a correlation predicate referencing rows of the outer query. Logically, EXISTS is true if at least one matching row exists.

`SELECT 1` is a readable convention because values in the select list do not matter; EXISTS only checks whether the subquery returns any row. `SELECT *` generally has the same semantics here, but `SELECT 1` makes intent explicit.

### 3.2. Students enrolled in at least one course

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

The result contains each student who has at least one row in `STUDENT_COURSES`. Whether a student enrolls in 1 course or 10 courses, they appear only once.

### 3.3. Students enrolled in course DB101

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c
      ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
);
~~~

The query returns students who have at least one `ACTIVE` enrollment for course `DB101`. The JOIN inside the subquery only serves to identify matching relationships; the outer query still returns each student at most once.

### 3.4. EXISTS does not need to count all matches

Avoid using `COUNT(*)` solely to test if rows exist:

~~~sql
SELECT s.student_id
FROM students s
WHERE (
    SELECT COUNT(*)
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
) > 0;
~~~

Write directly:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

`COUNT(*)` expresses a counting problem, whereas `EXISTS` expresses an existence problem. Oracle can optimize many expressions, but you should write semantically accurate SQL first.

### 3.5. Do not add ROWNUM = 1 inside EXISTS

Adding `ROWNUM = 1` is unnecessary. EXISTS inherently only needs to know whether the subquery produces a row. `ROWNUM` adds no clarity and can impede certain optimizer transformations depending on structure.

## 4. NOT EXISTS: finding rows with no matching relationship

### 4.1. Syntax

~~~sql
SELECT ...
FROM outer_table o
WHERE NOT EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = o.key
);
~~~

NOT EXISTS is true when the subquery returns an empty set.

### 4.2. Students not enrolled in any course

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

### 4.3. Students not enrolled in DB101

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c
      ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
);
~~~

This asks "no ACTIVE enrollment for DB101", not necessarily "never enrolled in DB101". To include CANCELLED or COMPLETED statuses, omit the status filter or redefine the predicate per business rules.

### 4.4. Predicates inside NOT EXISTS define what must not exist

Compare:

~~~sql
-- No enrollment at all
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
)
~~~

~~~sql
-- No ACTIVE enrollment
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
)
~~~

A student with a CANCELLED enrollment is excluded from the first result yet can appear in the second result. Predicates inside the subquery are part of the business definition, not merely an optimization detail.

## 5. EXISTS and JOIN differ in cardinality

### 5.1. JOIN can multiply outer rows

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id;
~~~

If a student enrolls in 5 courses, the query returns 5 rows for that student. If the goal is merely a list of enrolled students, these extra rows are redundant.

You could add DISTINCT, but DISTINCT may require a sort or hash unique to remove duplicates. The query generates duplicates only to discard them afterward.

### 5.2. EXISTS expresses a semijoin

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

A semijoin retains the outer row if a match exists, without multiplying outer rows by match count. This directly matches "has at least one relationship".

### 5.3. When is JOIN the right choice?

If you need to display columns from each relationship—such as each student alongside every enrolled course—JOIN is the natural choice:

~~~sql
SELECT s.student_id,
       s.full_name,
       c.course_code,
       c.course_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id;
~~~

Do not replace JOIN with EXISTS when the output requires columns from the related table or one row per relationship. Pick the construct matching the desired output shape.

### 5.4. Creating an existence flag in SELECT

~~~sql
SELECT s.student_id,
       s.full_name,
       CASE
           WHEN EXISTS (
               SELECT 1
               FROM student_courses sc
               WHERE sc.student_id = s.student_id
                 AND sc.status = 'ACTIVE'
           )
           THEN 'Y'
           ELSE 'N'
       END AS has_active_course
FROM students s;
~~~

This produces an existence flag without joining and grouping related rows into the outer result.

## 6. Semijoin and antijoin in the Oracle optimizer

### 6.1. Semijoin

A semijoin returns an outer row if at least one row from the inner row source satisfies the join condition. It does not return one outer row per inner match.

Operations you may see:

- NESTED LOOPS SEMI.
- HASH JOIN SEMI.
- MERGE JOIN SEMI.

### 6.2. Antijoin

An antijoin returns an outer row if zero rows from the inner row source satisfy the join condition. It is the natural implementation for NOT EXISTS.

Operations you may see:

- NESTED LOOPS ANTI.
- HASH JOIN ANTI.
- MERGE JOIN ANTI.

Actual operation names depend on the plan, query transformations, and release.

### 6.3. Correlated subquery does not always mean row-by-row looping

Example:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 10
);
~~~

This is a correlated subquery because it references outer alias `S`. However, do not conclude Oracle is forced to execute the subquery once per outer row. The optimizer can unnest the subquery and transform it into a semijoin/antijoin, or pick another plan.

With certain complex queries, aggregates, ROWNUM, set operators, or transformation-blocking constructs, a subquery might not be unnested. The plan may then show FILTER or another operation.

### 6.4. EXISTS does not guarantee physical short-circuiting the way people imagine

Logically, only one match is needed for EXISTS to be TRUE. The optimizer and execution engine can exploit that. However, do not assume every case always stops after a single physical read. Join method, batching, parallel execution, and access paths determine actual work.

Read A-Rows, Starts, Buffers, and operations rather than relying on a slogan like "EXISTS is always faster than JOIN".

### 6.5. EXISTS is not automatically faster than every equivalent construct

The optimizer can transform EXISTS, IN, and certain join patterns into similar plans. Performance depends on outer/inner row counts, selectivity, indexes, statistics, data skew, join method, unnesting feasibility, bind values, and child cursors.

Write EXISTS when the semantics are existence. Then tune based on the plan.

## 7. NOT EXISTS and the NOT IN NULL trap

This is a critical point when writing anti-joins.

### 7.1. NOT IN with a subquery containing NULL

~~~sql
SELECT s.student_id
FROM students s
WHERE s.student_id NOT IN (
    SELECT sc.student_id
    FROM student_courses sc
);
~~~

If the subquery returns even one NULL, the NOT IN comparison can become UNKNOWN for non-matching values. Since WHERE keeps only rows evaluating to TRUE, the result can unexpectedly be empty.

SQL uses three-valued logic:

- TRUE: condition holds.
- FALSE: condition fails.
- UNKNOWN: typically arises when comparing with NULL.

WHERE excludes both FALSE and UNKNOWN.

### 7.2. Simple example

~~~sql
SELECT 1
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

Equivalent condition:

~~~text
10 <> 20 AND 10 <> NULL
TRUE AND UNKNOWN = UNKNOWN
~~~

Consequently, no rows are returned.

### 7.3. NOT EXISTS avoids the same NULL trap as NOT IN

~~~sql
SELECT s.student_id
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

The correlation condition is equality. A NULL in `SC.STUDENT_ID` does not equal any `S.STUDENT_ID`, so it creates no match for the outer row. That NULL does not turn the entire NOT EXISTS condition into UNKNOWN.

In a standard junction table model, `STUDENT_ID` is already NOT NULL. Even so, NOT EXISTS remains the safer default whenever a subquery might produce NULLs.

### 7.4. NOT IN can be used when non-null is guaranteed

If both the outer expression and subquery result are guaranteed NOT NULL, NOT IN has clear semantics. Still, NOT EXISTS usually expresses correlated anti-relationships more directly and does not rely on assuming the subquery never returns NULL.

### 7.5. NULL in outer keys also needs business rules

With:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
)
~~~

if `P.PARENT_ID` is NULL, equality finds no child match, so NOT EXISTS evaluates to TRUE. If business rules do not want to retain outer rows with NULL keys, add:

~~~sql
WHERE p.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM child_table c
      WHERE c.parent_id = p.parent_id
  )
~~~

Do not treat NULL as a key that matches NULL under equality. If business logic treats NULL-to-NULL as belonging together, express those semantics explicitly.

## 8. Designing indexes for many-to-many relationships

### 8.1. Composite primary key supports one direction

With:

~~~sql
PRIMARY KEY (student_id, course_id)
~~~

Oracle creates a corresponding unique index in that column order. This index fits lookups starting from `STUDENT_ID` and can verify `COURSE_ID` directly within the same index.

### 8.2. Access in the reverse direction

If queries commonly start from `COURSE_ID` to find students, `(student_id, course_id)` does not have `COURSE_ID` as the leading column. Consider:

~~~sql
CREATE INDEX student_courses_course_ix
ON student_courses(course_id, student_id);
~~~

This index supports lookups by `COURSE_ID` and provides `STUDENT_ID` directly inside the index entry.

### 8.3. Two common access directions

| Question | Usually helpful index |
| --- | --- |
| Which courses has a student enrolled in? | `(student_id, course_id)` |
| Which students are enrolled in a course? | `(course_id, student_id)` |
| Is student S enrolled in course X? | `(student_id, course_id)` or an index leading with appropriate filter columns |
| Does course X have student S? | `(course_id, student_id)` or reverse unique key |

You do not necessarily need both indexes on every table. Weigh query frequency, junction table size, INSERT/DELETE cost, and index storage.

### 8.4. Foreign keys do not automatically create indexes

Oracle does not automatically create an index on foreign key columns merely because a constraint is declared. When a parent table undergoes key DELETE/UPDATE or experiences child-side JOIN/EXISTS workloads, foreign key indexes are generally useful to avoid scanning the entire child table and reduce locking issues.

For `STUDENT_COURSES`:

- Primary key `(student_id, course_id)` already provides an index leading on `STUDENT_ID`.
- Index `(course_id, student_id)` supports the `COURSE_ID` foreign key and reverse lookups.

### 8.5. Adding status to indexes

If a common query finds ACTIVE enrollments:

~~~sql
WHERE sc.student_id = :student_id
  AND sc.status = 'ACTIVE'
~~~

consider:

~~~sql
CREATE INDEX student_courses_student_status_ix
ON student_courses(student_id, status, course_id);
~~~

If queries start from course:

~~~sql
CREATE INDEX student_courses_course_status_ix
ON student_courses(course_id, status, student_id);
~~~

Indexes must match predicates and access direction. Do not add STATUS to every index by habit; if status has only a few values, selectivity may be low and maintenance overhead may not pay off.

### 8.6. Unique constraints guarantee correctness

If business rules forbid duplicate enrollments, use a unique constraint/primary key. Do not rely solely on:

~~~sql
IF NOT EXISTS (...) THEN
    INSERT ...
END IF;
~~~

Two concurrent sessions can both observe non-existence and both INSERT. A unique constraint is the final enforcement layer. The application must handle `DUP_VAL_ON_INDEX` or the corresponding error under contention.

### 8.7. Model with relationship history

If multiple enrollments over time must be stored:

~~~sql
CREATE TABLE student_enrollments (
    enrollment_id NUMBER PRIMARY KEY,
    student_id NUMBER NOT NULL,
    course_id NUMBER NOT NULL,
    term_code VARCHAR2(20) NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    status VARCHAR2(20) NOT NULL,
    CONSTRAINT enrollment_student_fk
        FOREIGN KEY (student_id) REFERENCES students(student_id),
    CONSTRAINT enrollment_course_fk
        FOREIGN KEY (course_id) REFERENCES courses(course_id),
    CONSTRAINT enrollment_term_uk
        UNIQUE (student_id, course_id, term_code)
);
~~~

If each student can have only one enrollment per course per term, a unique constraint on those three columns enforces the rule. Indexes and EXISTS predicates should reflect the current relationship definition, e.g., including `TERM_CODE` and `STATUS`.

## 9. Common M:N query patterns

### 9.1. Finding a course that has at least one student

~~~sql
SELECT c.course_id,
       c.course_code,
       c.course_name
FROM courses c
WHERE c.course_code = 'DB101'
  AND EXISTS (
      SELECT 1
      FROM student_courses sc
      WHERE sc.course_id = c.course_id
  );
~~~

If you need the student list for that course, use JOIN:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id
WHERE c.course_code = 'DB101';
~~~

### 9.2. Finding students with no ACTIVE enrollment

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

### 9.3. Finding courses with no enrolled students

~~~sql
SELECT c.course_id,
       c.course_code
FROM courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.course_id = c.course_id
);
~~~

This query typically benefits from an index leading on `COURSE_ID`.

### 9.4. Finding students enrolled in at least one of two courses

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code IN ('DB101', 'DB102')
);
~~~

A student enrolled in both courses still appears only once.

### 9.5. Finding students enrolled in both courses

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
)
AND EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB102'
      AND sc.status = 'ACTIVE'
);
~~~

Each EXISTS checks a separate relationship. The optimizer can evaluate the two subqueries using different access paths.

### 9.6. Conditions that must hold on the same link row

Suppose you need students who have a single enrollment that is both ACTIVE and in term 2025A. Put both predicates inside the same EXISTS:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM student_enrollments e
    WHERE e.student_id = s.student_id
      AND e.status = 'ACTIVE'
      AND e.term_code = '2025A'
)
~~~

If written as two separate EXISTS clauses, the two conditions could be satisfied by two different enrollments. Only use two EXISTS clauses if business logic allows two distinct relationships.

### 9.7. Finding students who have completed all required courses

This is a relational division problem. It can be expressed using double NOT EXISTS:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM required_courses rc
    WHERE NOT EXISTS (
        SELECT 1
        FROM student_courses sc
        WHERE sc.student_id = s.student_id
          AND sc.course_id = rc.course_id
          AND sc.status IN ('ACTIVE', 'COMPLETED')
    )
);
~~~

Reading from the inside out:

1. The innermost subquery checks for a required course in which the student does not yet have a valid enrollment.
2. The middle NOT EXISTS identifies required courses missing from the student's enrollments.
3. The outer NOT EXISTS requires that no required course be missing.
4. The result is students satisfying all required courses.

If `REQUIRED_COURSES` is empty, the double NOT EXISTS condition is true for every student under the logic "no required course is missing". If business rules require at least one course in `REQUIRED_COURSES`, add an EXISTS condition on `REQUIRED_COURSES`.

### 9.8. Finding students with at least N relationships

If the question genuinely needs a count, use GROUP BY/HAVING:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.status = 'ACTIVE'
GROUP BY s.student_id, s.full_name
HAVING COUNT(*) >= 3;
~~~

This is a counting problem, not purely an existence check.

## 10. LEFT JOIN ... IS NULL versus NOT EXISTS

Another way to write an anti-join:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
LEFT JOIN student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.student_id IS NULL;
~~~

With properly chosen join conditions and check columns, results can be equivalent to NOT EXISTS.

### 10.1. Placing predicates in the right clause

To find students with no ACTIVE enrollment, the status condition must sit in `ON`:

~~~sql
SELECT s.student_id
FROM students s
LEFT JOIN student_courses sc
  ON sc.student_id = s.student_id
 AND sc.status = 'ACTIVE'
WHERE sc.student_id IS NULL;
~~~

If `SC.STATUS = 'ACTIVE'` is placed in `WHERE` alongside `SC.STUDENT_ID IS NULL`, rows padded by the outer join have `STATUS = NULL` and fail the condition. The query no longer expresses the intended logic.

### 10.2. Choosing a NOT NULL column for the IS NULL check

In the outer join anti-pattern, the column tested with IS NULL must never be NULL on matching rows—typically the primary key or a NOT NULL column. Picking a nullable column risks mistaking matching rows whose value happens to be NULL for unmatched rows.

### 10.3. Why is NOT EXISTS usually clearer?

NOT EXISTS encapsulates all relationship predicates inside one subquery and directly expresses "no matching row exists". It depends less on selecting a non-null marker column and reduces the risk of misplacing predicates between ON and WHERE.

There is no rule that NOT EXISTS is always faster than LEFT JOIN IS NULL. Oracle can transform both into similar antijoins. Pick the clearer, semantically accurate form and compare plans when performance matters.

## 11. Subquery unnesting and conditions affecting transformations

### 11.1. What is unnesting?

Subquery unnesting is a query transformation that merges a subquery into the outer query block so the optimizer can evaluate them jointly. For EXISTS/NOT EXISTS, transformation can produce a semijoin/antijoin.

Example:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 10
);
~~~

The optimizer can process this as a semijoin between `STUDENTS` and `STUDENT_COURSES`.

### 11.2. When might a subquery not be unnested?

Certain constructs can restrict or prevent transformation depending on context:

- ROWNUM inside the subquery.
- Certain aggregates or GROUP BY.
- Set operators.
- Subqueries with complex structures or special semantics.
- Certain outer references or incompatible functions.

Do not memorize a list as an absolute rule across all releases. Check the SQL Tuning Guide and the actual plan.

### 11.3. FILTER operation

If a subquery is not unnested, the plan may show a FILTER operation. That alone does not prove the query is slow. Inspect Starts, A-Rows, buffers, and per-evaluation subquery cost.

If the outer row source is small and the inner lookup has a good index, FILTER with a correlated subquery can be efficient. If the outer source is huge and the subquery iterates many times, a semijoin/hash-based strategy may fit better.

### 11.4. Do not add hints before understanding the plan

Oracle provides optimizer hints affecting join methods and transformations. Do not add hints merely because you want to see HASH JOIN SEMI or NESTED LOOPS SEMI. Hints can destabilize plans as data, statistics, or bind values evolve.

Before hinting, verify SQL semantics, gather statistics, inspect the actual plan/runtime metrics, check indexes and cardinality, and only then consider hints if backed by measurable evidence.

## 12. Choosing indexes and join methods by data scale

### 12.1. Nested Loops Semi/Anti

Nested loops usually fit when the outer row source is relatively small and the inner lookup has an effective index. For instance, if only 10 courses are selected and we need students enrolled in each, Oracle can use nested loops and an index lookup on `STUDENT_COURSES`.

### 12.2. Hash Join Semi/Anti

Hash join can fit when both row sources are large and the optimizer estimates many rows must be processed. Oracle can build a hash structure from one side and probe matches from the other. A B-tree index is not strictly required to use hash semi/anti join.

### 12.3. Merge Join Semi/Anti

Merge join may be chosen when row sources are already suitably ordered or sort/merge costs are competitive. The plan may display MERGE JOIN SEMI or MERGE JOIN ANTI.

### 12.4. No single join method is best for all data sizes

A junction table with a few hundred rows and one with hundreds of millions of rows behave differently. The same SQL can need different plans depending on bind values or data distribution. Never use a fixed hint as a substitute for measuring cardinality, selectivity, and I/O.

## 13. Statistics and cardinality for junction tables

The optimizer needs to know the row count in the junction table, distinct counts of `STUDENT_ID` and `COURSE_ID`, status distribution, average rows per student/course, data skew, and column correlation.

Gather statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'STUDENT_COURSES',
        cascade => TRUE
    );
END;
/
~~~

With heavily skewed data, histograms may be needed on appropriate columns. Do not create histograms on every column by habit; histograms add complexity to plan selection and should be managed per workload.

### 13.1. E-Rows and A-Rows

When reading an actual plan:

- E-Rows is the optimizer's estimated cardinality.
- A-Rows is the actual row count returned by the operation.
- Starts shows how many times the operation was started.
- Buffers shows logical I/O.

If a FILTER subquery has a very high Starts count, check the inner access path and unnesting feasibility. If HASH JOIN SEMI has a large E-Rows discrepancy, check statistics and data skew.

### 13.2. Correlation between columns

Suppose `COURSE_ID = 10` almost always has `STATUS = ACTIVE`, yet the columns have independent statistics. The optimizer may misestimate the combined selectivity of the two predicates.

Extended statistics can help for certain correlated column groups:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'STUDENT_COURSES',
           extension => '(COURSE_ID, STATUS)'
       )
FROM dual;
~~~

After creating extended statistics, re-gather table statistics and inspect the plan. Use them only when there is evidence of correlation and cardinality estimation errors.

## 14. Design mistakes and anti-patterns

| Anti-pattern | Issue | Improvement |
| --- | --- | --- |
| JOIN then DISTINCT solely to check existence | Generates duplicates then discards them | Use EXISTS |
| COUNT(*) > 0 | Counts everything when only row presence is needed | Use EXISTS |
| NOT IN with nullable subquery | NULL can turn condition into UNKNOWN | Use NOT EXISTS |
| Index in only one M:N direction | Reverse queries may scan many rows | Evaluate reversed-column index |
| Check then INSERT without unique constraint | Race condition across sessions | Enforce uniqueness with a constraint |
| Right-table predicate placed in WHERE of LEFT JOIN | Breaks outer join/anti-join semantics | Place match condition in ON |
| Two EXISTS for conditions that must hold on one link row | Conditions can be satisfied by two different relationships | Place predicates in the same EXISTS |
| Confusing no relationship with no ACTIVE relationship | Wrong business semantics | Define status explicitly in subquery |
| Assuming correlated subqueries are always row-by-row | Ignores subquery unnesting | Read actual plan |
| Assuming EXISTS is always faster than JOIN | Picking syntax by slogan | Pick by semantics and measure plans |

## 15. Lab: tuning EXISTS and NOT EXISTS on many-to-many relationships

The lab creates an isolated schema. Plan results can vary across environments.

### 15.1. Create tables

~~~sql
CREATE TABLE lab_students (
    student_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_courses (
    course_id NUMBER PRIMARY KEY,
    course_code VARCHAR2(20) NOT NULL UNIQUE
);

CREATE TABLE lab_student_courses (
    student_id NUMBER NOT NULL,
    course_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    enrolled_at DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT lab_sc_pk PRIMARY KEY (student_id, course_id),
    CONSTRAINT lab_sc_student_fk
        FOREIGN KEY (student_id) REFERENCES lab_students(student_id),
    CONSTRAINT lab_sc_course_fk
        FOREIGN KEY (course_id) REFERENCES lab_courses(course_id),
    CONSTRAINT lab_sc_status_ck
        CHECK (status IN ('ACTIVE', 'CANCELLED', 'COMPLETED'))
);

CREATE INDEX lab_sc_course_student_ix
ON lab_student_courses(course_id, student_id);
~~~

### 15.2. Populate data

~~~sql
INSERT INTO lab_students(student_id, full_name)
SELECT LEVEL,
       'Student ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

INSERT INTO lab_courses(course_id, course_code)
SELECT LEVEL,
       'C' || TO_CHAR(LEVEL, 'FM000')
FROM dual
CONNECT BY LEVEL <= 100;

INSERT INTO lab_student_courses(student_id, course_id, status)
SELECT s.student_id,
       c.course_id,
       CASE
           WHEN MOD(s.student_id + c.course_id, 5) = 0
           THEN 'COMPLETED'
           ELSE 'ACTIVE'
       END
FROM lab_students s
JOIN lab_courses c
  ON c.course_id BETWEEN 1 AND 10
WHERE MOD(s.student_id + c.course_id, 7) = 0;

COMMIT;
~~~

### 15.3. Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_STUDENTS',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_COURSES',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_STUDENT_COURSES',
        cascade => TRUE
    );
END;
/
~~~

### 15.4. Find students with an ACTIVE enrollment

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       s.student_id,
       s.full_name
FROM lab_students s
WHERE EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

View cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Observe whether Oracle uses NESTED LOOPS SEMI, HASH JOIN SEMI, FILTER, or another operation. Check index access, E-Rows, A-Rows, Starts, and Buffers.

### 15.5. Find students with no ACTIVE enrollment

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       s.student_id,
       s.full_name
FROM lab_students s
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

Read the plan and look for an antijoin operation if the subquery was unnested. If FILTER appears, check Starts and inner lookup cost.

### 15.6. Compare with JOIN DISTINCT

~~~sql
SELECT DISTINCT
       s.student_id,
       s.full_name
FROM lab_students s
JOIN lab_student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.status = 'ACTIVE';
~~~

Compare results and plan against EXISTS. Logical results should match; operations may differ. Do not compare Cost alone: examine actual rows, buffers, and elapsed time in the same environment.

### 15.7. Find students not enrolled in course 5

~~~sql
SELECT s.student_id
FROM lab_students s
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 5
);
~~~

Primary key `(student_id, course_id)` supports lookups by both columns.

### 15.8. Find courses with no enrollments

~~~sql
SELECT c.course_id,
       c.course_code
FROM lab_courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.course_id = c.course_id
);
~~~

The query starts from `COURSE_ID`, so index `LAB_SC_COURSE_STUDENT_IX` supports this access direction.

### 15.9. Test NOT IN and NULL

~~~sql
SELECT 1
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

Result has zero rows. Compare with:

~~~sql
SELECT 1
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM dual
    WHERE 20 = 10
       OR CAST(NULL AS NUMBER) = 10
);
~~~

NOT EXISTS checks whether any row satisfies the equality predicate. The subquery above has no matching row, so NOT EXISTS is TRUE.

### 15.10. Clean up the lab

~~~sql
DROP TABLE lab_student_courses PURGE;
DROP TABLE lab_courses PURGE;
DROP TABLE lab_students PURGE;
~~~

Run only after completing the lab and when you no longer need the data.

## 16. Workflow for tuning EXISTS/NOT EXISTS in projects

When an M:N query is slow, follow this sequence:

1. Determine whether the business question is existence, non-existence, listing relationships, or counting relationships.
2. Write SQL matching the semantics: EXISTS, NOT EXISTS, JOIN, or GROUP BY/HAVING accordingly.
3. Identify keys and cardinality of the junction table.
4. Check primary key/unique constraints to prevent duplicate relationships.
5. Check indexes along both directions of the M:N relationship.
6. Check whether status/term/tenant predicates are covered by necessary indexes.
7. Gather appropriate statistics.
8. Retrieve the actual cursor plan via `DBMS_XPLAN.DISPLAY_CURSOR`.
9. Identify semijoin/antijoin, nested loops/hash/merge, or FILTER.
10. Compare E-Rows against A-Rows, Starts, Buffers, and timing.
11. Verify NULL semantics, data type conversions, and predicate placement.
12. Test controlled index/query changes and re-measure across multiple bind values.
13. Test concurrency if an existence check is used to decide relationship INSERTs.
14. Document index design rationale and DML impact.

## 17. Design and tuning checklist

1. **Need existence or related data?** Existence uses EXISTS; needing each relationship uses JOIN.
2. **How is non-existence defined?** No relationship at all, or only no ACTIVE/current-term relationship?
3. **Does the subquery have the proper correlation predicate?** Match on the outer row's key.
4. **Is there duplicate risk?** Use semijoin semantics if only outer rows are needed.
5. **Can NULL appear in a NOT IN subquery?** Prefer NOT EXISTS whenever NULL is possible.
6. **Can the outer key be NULL?** Specify whether those rows should be retained.
7. **Does the junction table have a unique constraint?** Prevent duplicate relationships.
8. **Is there an index for the access direction?** Consider both `(A_ID, B_ID)` and `(B_ID, A_ID)`.
9. **Are status/term predicates supported?** Measure before adding composite indexes.
10. **Are statistics up to date?** Check row counts, NDV, histograms, and skew.
11. **Was the subquery unnested?** Read the operation tree; do not guess from syntax.
12. **Does the join method fit cardinality?** Nested loops, hash, or merge semi/anti.
13. **Is there a FILTER with high Starts?** Check inner lookup and transformation feasibility.
14. **Are functions/implicit conversions on keys?** Use properly typed binds and index-friendly predicates.
15. **Are LEFT JOIN IS NULL predicates placed properly in ON/WHERE?** Pick a NOT NULL column to check.
16. **Is relational division needed?** Double NOT EXISTS can express "satisfies all".
17. **Is there a race condition between check and INSERT?** Unique constraints are the final safeguard.
18. **Have actual plans been measured?** Compare A-Rows, Starts, Buffers, and timing on real data.

## 18. Self-check questions

**Question 1.** When does EXISTS return TRUE?

**Question 2.** When does NOT EXISTS return TRUE?

**Question 3.** Why is SELECT 1 commonly used inside EXISTS?

**Question 4.** How does a semijoin differ from a regular join in output cardinality?

**Question 5.** What type of question does an antijoin solve?

**Question 6.** Why does a correlated subquery not always mean looping row-by-row over outer rows?

**Question 7.** Why can JOIN followed by DISTINCT be redundant when only checking existence?

**Question 8.** Why can NOT IN return an empty result when the subquery contains NULL?

**Question 9.** Does NULL in the inner key make an entire NOT EXISTS condition UNKNOWN?

**Question 10.** Which queries does index `(student_id, course_id)` support well?

**Question 11.** Why might index `(course_id, student_id)` be needed?

**Question 12.** Does Oracle automatically create an index for foreign keys?

**Question 13.** When should two separate EXISTS clauses be used versus putting predicates in a single EXISTS?

**Question 14.** What problem does double NOT EXISTS express?

**Question 15.** Why must LEFT JOIN IS NULL place match conditions in ON?

**Question 16.** When might nested loops semi/anti be appropriate?

**Question 17.** When might hash join semi/anti be appropriate?

**Question 18.** Why shouldn't hints be added before reading the actual plan?

**Question 19.** What do E-Rows, A-Rows, and Starts help diagnose?

**Question 20.** Why does checking EXISTS before INSERT still require a unique constraint?

<details>
<summary>Answer hints</summary>

1. When the subquery returns at least one row.
2. When the subquery returns zero rows.
3. Because select list values do not matter; SELECT 1 clearly shows only existence is checked.
4. Semijoin keeps each outer row at most once even if the inner side has multiple matches; a regular join can duplicate per match.
5. Finding outer rows with no inner match.
6. The optimizer can unnest the subquery into a semijoin/antijoin or other transformation.
7. JOIN creates duplicates per relationship and DISTINCT then removes them; EXISTS expresses existence directly.
8. Because comparisons with NULL yield UNKNOWN and WHERE does not retain UNKNOWN.
9. No. Equality with NULL yields no match; NOT EXISTS evaluates whether the subquery result is empty.
10. Looking up a student's courses and checking relationships starting from student.
11. Supports looking up students by course and queries starting from the course side.
12. No. Indexes must be created explicitly when workload and locking/joins require them.
13. Use two EXISTS if two independent relationships can satisfy them separately; use one EXISTS if conditions must hold on the same link row.
14. Finding outer rows matching every element in a required set, i.e., relational division.
15. To check that no row satisfies the entire join condition; putting predicates in WHERE can break outer join semantics.
16. When the outer row source is small and the inner lookup has an efficient index.
17. When row sources are large and processing many rows makes a hash strategy more competitive.
18. Because hints can force unstable plans and mask root causes like statistics/cardinality.
19. Estimation discrepancies, how many times an operation ran, and actual row volumes.
20. Because two sessions can both see non-existence and both INSERT; a unique constraint protects correctness under concurrency.

</details>

## 19. Official Oracle references

1. [Oracle Database 19c SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): join methods, semijoins, antijoins, and how the optimizer processes joins.
2. [Oracle Database 19c SQL Tuning Guide — Subquery Unnesting](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): query transformations, subquery unnesting, and predicate movement.
3. [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): semantics of the EXISTS condition.
4. [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): IN/NOT IN and condition semantics.
5. [Oracle Database 19c SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): selectivity, cardinality, and optimizer statistics.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): displaying execution plans and runtime statistics.
7. [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): creating B-tree and function-based indexes.
8. [Oracle Database 19c SQL Language Reference — Constraints](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): primary key, unique key, and foreign key constraints.

**Key principle to remember:** Use EXISTS when asking "does at least one matching relationship exist?" and NOT EXISTS when asking "does no matching relationship exist?". They express semijoin/antijoin and avoid multiplying outer rows. For many-to-many relationships, junction tables need keys and indexes matching actual access directions. Pay special attention to NULL in NOT IN, predicate placement in outer joins, conditions that must hold on the same link row, statistics, and actual execution plans. Sound tuning starts from business semantics, then moves to indexes and join methods.
