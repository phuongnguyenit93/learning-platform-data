# Key Constraints and Property Type Constraints When Supported

## 1. Context: From a Flexible Property Graph to Contracted Data

Neo4j is a graph database built on the **property graph** model: **nodes** represent entities, **relationships** represent directed connections between entities, and **properties** store descriptive values. Nodes carrying the same label can have different sets of properties. This enables rapid model evolution, but it also allows bad data to slip in unless clear rules are defined.

Suppose a learning platform has `:Course` nodes and `:ENROLLED_IN` relationships:

```mermaid
flowchart LR
    S["Student\nstudentId: S101"] -->|"ENROLLED_IN\nenrollmentId: E9001\nscore: 8.5"| C["Course\ncourseCode: NEO101\ncredits: 3"]
```

In business terms, the system may require:

1. Every course must have a `courseCode` **and** no two courses may share the same code.
2. An enrollment must have an `enrollmentId` **and** no two enrollments may share the same ID.
3. `credits` must be stored as an **integer**, while `score` must be a **floating-point number**.
4. `credits` must fall within an allowed range; `score` must fall within a valid grading scale.

The first two requirements are cleanly expressed with **key constraints**; the third can be checked with **property type constraints**. The fourth is a value-domain rule and is not automatically guaranteed solely by the key and type constraints introduced in this lesson.

This lesson belongs to the **Data Constraints** chapter, focusing on Neo4j schema design, writing Cypher, data ingestion, and coordinating with the Java Driver or Spring Data Neo4j. The core focus is **choosing and applying node/relationship keys and property type constraints with the right scope, version, and edition**.

After this lesson, you will be able to:

- Explain the differences among uniqueness, existence, node key, relationship key, and property type constraints.
- Create key constraints on a single property or a tuple of properties.
- Specify what a type constraint validates and what it does not validate.
- Identify which version/edition details must be verified before running schema commands.
- Audit legacy data, run migrations, and handle write errors once constraints are active.

## 2. What Problems Do Node and Relationship Keys Solve?

In relational systems, a primary key typically represents a record's identity. In Neo4j, a **node key** expresses two invariants simultaneously for nodes within a **label**:

- The key properties are **required to exist**, meaning they cannot be missing or `null`.
- The key tuple is **unique** across nodes carrying that label.

A **relationship key** has the same semantics, except it applies to relationships of a specific **relationship type**.

Crucially, key constraints protect **identifying properties**, not every structural or business rule in the graph. For example, a relationship key on `enrollmentId` does not automatically forbid two relationships with different IDs from connecting the same `Student`–`Course` pair.

### 2.1. Comparing the Options

| Mechanism | Properties Required to Exist? | Values Unique? | Scope |
| --- | --- | --- | --- |
| Node uniqueness | No | Yes, for present values | Nodes with the declared label |
| Node property existence | Yes | No | Nodes with the declared label |
| **Node key** | **Yes, all key components** | **Yes, across the full key tuple** | Nodes with the declared label |
| Relationship key | **Yes, all key components** | **Yes, across the full key tuple** | Relationships of the declared type |
| Property type | No, if only a type constraint exists | No | Nodes or relationships in the declared scope |

If you only place uniqueness on `courseCode`, two `:Course` nodes **without** that property can still exist. A node key closes that gap. If you only place a type constraint on `credits`, the property can still be **absent** without violating the type constraint; add an existence rule if business rules require credits to be present.

## 3. Checking Version and Edition Before Creating Constraints

**Key constraints and property type constraints do not have identical support across all Neo4j versions.** Specifically, for the Neo4j 5.x series:

| Constraint Type | Milestone / How to Read It in Neo4j 5.x | Edition |
| --- | --- | --- |
| Node key | Available in 5.x versions supporting modern Cypher schema syntax | Enterprise |
| Relationship key | Added in the 5.x line, starting in Neo4j 5.7 | Enterprise |
| Node/relationship property type | Added in the 5.x line, starting in Neo4j 5.9 | Enterprise |
| Node uniqueness | Supported earlier; distinct from node key | Available in Community and Enterprise |

These milestones help interpret examples **within the 5.x line**; if you run an older version or a newer release branch (such as calendar-versioned releases), consult the official documentation for your exact running version. Managed Neo4j services may also gate features by deployment tier.

Check the DBMS via Cypher:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

When inspecting the result, verify three details: **Neo4j DBMS version**, **edition**, and **the constraint types supported by that release**. The Java Driver or Spring Data Neo4j version is separate; upgrading the driver does not add schema capabilities to the database.

The `CREATE CONSTRAINT` examples below use Neo4j 5.x syntax where the corresponding feature is supported. When run on Community Edition without key/type constraint support, DDL statements will not become valid merely by adding `IF NOT EXISTS`.

## 4. Node Key: Mandatory and Unique Identity for Nodes

Suppose every course has a system-wide unique `courseCode`. In an environment supporting node keys:

```cypher
CREATE CONSTRAINT course_code_key IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseCode IS NODE KEY;
```

The statement has four parts:

- `course_code_key` is the **constraint name** used for inspection and administration.
- `IF NOT EXISTS` supports repeatable migration runs when a matching constraint already exists; it does not replace verifying the schema.
- `FOR (c:Course)` defines the target as **all nodes carrying the `Course` label**.
- `REQUIRE c.courseCode IS NODE KEY` requires `courseCode` to be both present and unique.

Once the constraint is created:

```cypher
// Valid: new code.
CREATE (:Course {courseCode: 'NEO101', title: 'Introduction to Neo4j'});

// Error: duplicate key NEO101.
CREATE (:Course {courseCode: 'NEO101', title: 'Cypher Fundamentals'});

// Error: missing key.
CREATE (:Course {title: 'Course without a code'});
```

These statements illustrate **separate test cases**. Do not execute the entire block sequentially against a real system after the second statement intentionally fails.

Beyond `CREATE`, operations that remove or alter the key must also obey the constraint:

```cypher
// Invalid if course NEO101 exists and has a node key.
MATCH (c:Course {courseCode: 'NEO101'})
REMOVE c.courseCode;

// Invalid: SET ... = null is equivalent to removing the property.
MATCH (c:Course {courseCode: 'NEO101'})
SET c.courseCode = null;
```

A node key does not restrict the entire database: a `:Resource` node without the `:Course` label can hold the same `courseCode` value. Conversely, a multi-label node that includes `Course` is still governed by the constraint. Adding the `Course` label to a node missing `courseCode` can also be rejected.

### 4.1. Composite Node Key for Multi-Tenant Applications

In a multi-tenant model, a course code may only need to be unique **within each tenant**. Then `tenantId` and `courseCode` form a **composite key**:

```cypher
CREATE CONSTRAINT tenant_course_key IF NOT EXISTS
FOR (c:Course)
REQUIRE (c.tenantId, c.courseCode) IS NODE KEY;
```

Behavior:

| `:Course` Node | Result If No Node with That Key Pair Exists Yet |
| --- | --- |
| `{tenantId: 'T1', courseCode: 'NEO101'}` | Valid |
| `{tenantId: 'T2', courseCode: 'NEO101'}` | Valid, different tenant |
| Creating **another** `{tenantId: 'T1', courseCode: 'NEO101'}` | Key violation |
| `{tenantId: 'T1'}` | Violation due to missing `courseCode` |
| `{courseCode: 'NEO101'}` | Violation due to missing `tenantId` |

A composite key only forbids **duplicating the entire tuple of values**. It does **not** require each `tenantId` to be unique or each `courseCode` to be globally unique across the database.

Choose the right identity before writing the constraint: if two tenants are allowed to reuse the same code, a single-property `courseCode` key will reject valid data. If the entire system allows only one code, a composite key is too permissive and allows duplicates across different tenants.

### 4.2. Key Constraints Do Not Validate Format

Even a node key accepts `courseCode: ''` (an empty string), because `''` is a present value, distinct from `null`. If `''` has not yet been used on another node, it can still be a **technically** unique key while violating business rules.

A node key also does not verify that codes start with `NEO`, check course start dates, automatically uppercase strings, or restrict credit counts. Those invariants require additional validation, normalization, or modeling.

## 5. Relationship Key: Identity for Relationships

Relationships in Neo4j also carry properties; for example, an enrollment has an `enrollmentId`:

```mermaid
flowchart LR
    S["Student\nstudentId: S101"] -->|"ENROLLED_IN\nenrollmentId: E9001"| C["Course\ncourseCode: NEO101"]
```

When your Neo4j version supports relationship keys, you can require every `ENROLLED_IN` relationship to have a non-missing, unique `enrollmentId`:

```cypher
CREATE CONSTRAINT enrollment_id_key IF NOT EXISTS
FOR ()-[r:ENROLLED_IN]-()
REQUIRE r.enrollmentId IS RELATIONSHIP KEY;
```

The scope `FOR ()-[r:ENROLLED_IN]-()` specifies the **relationship type**. Direction between start and end nodes is not part of this schema pattern; every relationship of type `ENROLLED_IN` is in scope.

Enrollment example:

```cypher
MATCH (s:Student {studentId: $studentId})
MATCH (c:Course {courseCode: $courseCode})
CREATE (s)-[r:ENROLLED_IN {
    enrollmentId: $enrollmentId,
    enrolledAt: datetime()
}]->(c)
RETURN r.enrollmentId AS enrollmentId;
```

If `$enrollmentId` is `null` or already belongs to another `ENROLLED_IN` relationship, the write is rejected by the key constraint. If either node is not found by `MATCH`, there are no input rows to create the relationship; **the application must check for zero returned rows** and respond properly for a missing student or course.

### 5.1. Composite Relationship Key

A multi-tenant system can use `(tenantId, enrollmentId)` as the identity of an enrollment:

```cypher
CREATE CONSTRAINT tenant_enrollment_key IF NOT EXISTS
FOR ()-[r:ENROLLED_IN]-()
REQUIRE (r.tenantId, r.enrollmentId) IS RELATIONSHIP KEY;
```

All `ENROLLED_IN` relationships must carry both properties and each pair must be unique. Do not simultaneously keep the single-property `enrollmentId` key from the earlier example if business rules permit two tenants to use the same ID: the single key would make the rule stricter than intended.

### 5.2. What a Relationship Key Cannot Do

A relationship key only protects identifying properties on the relationship. It **does not automatically guarantee**:

- That `ENROLLED_IN` necessarily connects a `Student` to a `Course`; Neo4j ensures both endpoints are existing nodes, not their business labels via key constraints.
- That at most one `ENROLLED_IN` relationship exists between two nodes; two relationships with different IDs can still connect the same node pair.
- That a student cannot enroll in the same course across two different terms/sessions; this question requires an identity rule aligned with business history.

If the requirement is "each student has at most one enrollment record per course", you can model `Enrollment` as a node with composite key `(studentId, courseCode)`, or design concurrency-controlled writes. When multiple valid enrollments across terms are allowed, include `term` or a registration-period identifier. Relationships connected to the `Enrollment` node still need to be written accurately using transactions and validated queries.

## 6. Property Type Constraints: Data Type Consistency

Suppose an application calculates tuition from credit count. If `credits` is sometimes the integer `3` and sometimes the string `'3'`, Java code and Cypher expressions can fail or return unexpected results. A **property type constraint** enforces the stored data type for a property within a label or relationship type scope.

For example, a course has a `STRING` code and an `INTEGER` credit count:

```cypher
CREATE CONSTRAINT course_code_string IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseCode IS :: STRING;

CREATE CONSTRAINT course_credits_integer IF NOT EXISTS
FOR (c:Course)
REQUIRE c.credits IS :: INTEGER;
```

On a relationship, a score or attempt count can have a specific type:

```cypher
CREATE CONSTRAINT enrollment_attempt_integer IF NOT EXISTS
FOR ()-[r:ENROLLED_IN]-()
REQUIRE r.attempt IS :: INTEGER;
```

`IS :: TYPE` is Neo4j 5.x syntax where supported. Supported type names and variants differ by version; before declaring complex types such as lists or temporal types, check the documentation for your running DBMS.

### 6.1. Difference Between Wrong-Type and Absent Properties

| `Course` Data | With `credits IS :: INTEGER` and No Existence Rule |
| --- | --- |
| `credits: 3` | Valid |
| `credits: 0` | Valid by type, even if invalid by business rules |
| `credits: -5` | Valid by type, even if business rules forbid negatives |
| `credits: '3'` | Violation: string is not an integer |
| `credits: 3.0` | Violation if stored as `FLOAT`, even though numerically equal to `3` |
| Missing `credits` | Not forbidden by a **type constraint alone** |

A type constraint **does not** auto-coerce types. Neo4j will not silently convert `'3'` into `3` to satisfy the constraint. Ingestion jobs and the application layer must supply values of the correct type.

### 6.2. Combining Type with Key and Existence Constraints

When `courseCode` is a mandatory identity and `credits` is also required to exist, the design may include:

```cypher
// Require courseCode to be both present and unique.
CREATE CONSTRAINT course_code_key IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseCode IS NODE KEY;

// Code has string type.
CREATE CONSTRAINT course_code_string IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseCode IS :: STRING;

// Credits has integer type.
CREATE CONSTRAINT course_credits_integer IF NOT EXISTS
FOR (c:Course)
REQUIRE c.credits IS :: INTEGER;

// If supported by the edition: credits must be present.
CREATE CONSTRAINT course_credits_required IF NOT EXISTS
FOR (c:Course)
REQUIRE c.credits IS NOT NULL;
```

These constraints express **distinct invariants** and should only be created according to actual requirements after verifying edition and existing data. Avoid adding redundant constraints with overlapping meaning "just in case." For `credits`, even with both type and existence constraints active, checks like `credits > 0` or credit caps still belong in the business layer.

### 6.3. How Java Types Map to Stored Neo4j Types

When the Java Driver passes Cypher parameters, `Integer`/`Long` values typically map to Neo4j `INTEGER`; `Double`/`Float` map to the appropriate floating-point type; `String` stays a string. Thus, an ingestion job that reads credits from a CSV as a string and passes `'3'` directly will violate `IS :: INTEGER`, even though a human sees digits.

The right approach is to validate and parse inputs per policy, reject invalid values, and then pass the proper type. Never rely on the database to auto-cast types or swallow constraint errors.

## 7. Using Key Constraints with `MERGE` and Concurrent Writes

If `Course` has key `(tenantId, courseCode)`, you can find or create the node using **that exact identifying key**:

```cypher
MERGE (c:Course {
    tenantId: $tenantId,
    courseCode: $courseCode
})
ON CREATE SET c.title = $title,
              c.credits = $credits,
              c.createdAt = datetime()
RETURN c.tenantId AS tenantId,
       c.courseCode AS courseCode,
       c.title AS title;
```

If non-key properties can change over time, do not include them in the `MERGE` pattern:

```cypher
// Avoid if title is mutable descriptive data.
MERGE (c:Course {
    tenantId: $tenantId,
    courseCode: $courseCode,
    title: $title
})
RETURN c;
```

If a node already exists with the same key but a different `title`, the full pattern fails to match, `MERGE` attempts to create another node, and a key constraint error occurs. The proper pattern is to `MERGE` on the key, then decide whether to update `title` via `ON MATCH SET` or a dedicated operation.

When two transactions concurrently write a non-existent key, the key constraint acts as **the integrity guardrail**: two nodes with the same key cannot both commit. Even so, the application must still handle lock waits, retries, or conflict errors depending on the case; never treat `MERGE` as a mechanism that resolves every write-concurrency issue by itself.

When a key component is missing, running `MERGE` with `null` in the property pattern is not a valid path for auto-populating keys. The application must validate `tenantId` and `courseCode` before running Cypher.

## 8. Preparing Migrations on Existing Data

Neo4j must validate existing nodes/relationships before creating key or type constraints. If there are records with **duplicate keys**, **missing key components**, or **wrong property types**, the corresponding constraint creation statement will fail. There is no built-in auto-merge, auto-backfill, or type-casting step safe for every business case.

### 8.1. Finding Nodes Missing Keys

```cypher
MATCH (c:Course)
WHERE c.tenantId IS NULL
   OR c.courseCode IS NULL
RETURN elementId(c) AS nodeElementId,
       c.tenantId AS tenantId,
       c.courseCode AS courseCode,
       c.title AS title
LIMIT 50;
```

To assess total volume:

```cypher
MATCH (c:Course)
WHERE c.tenantId IS NULL
   OR c.courseCode IS NULL
RETURN count(c) AS missingKeyCount;
```

### 8.2. Finding Duplicate Composite Keys

```cypher
MATCH (c:Course)
WHERE c.tenantId IS NOT NULL
  AND c.courseCode IS NOT NULL
WITH c.tenantId AS tenantId,
     c.courseCode AS courseCode,
     count(*) AS total,
     collect(elementId(c)) AS nodeIds
WHERE total > 1
RETURN tenantId, courseCode, total, nodeIds
ORDER BY total DESC
LIMIT 50;
```

`elementId()` helps locate records during review, but it should not be turned into a durable business key or stored externally. `collect()` can consume substantial memory if a duplicate group contains many records; on large datasets, separate summary counts from per-group detail retrieval.

Before merging two nodes with duplicate keys, inspect the relationships attached to them. Immediately deleting an extra node can destroy enrollment history, reviews, or related links. The merge process must preserve business semantics, retain necessary data, and fix the upstream ingestion cause that produced duplicates.

### 8.3. Finding Relationships Missing or Duplicating Keys

```cypher
MATCH ()-[r:ENROLLED_IN]->()
WHERE r.enrollmentId IS NULL
RETURN elementId(r) AS relationshipElementId
LIMIT 50;
```

```cypher
MATCH ()-[r:ENROLLED_IN]->()
WHERE r.enrollmentId IS NOT NULL
WITH r.enrollmentId AS enrollmentId,
     count(*) AS total,
     collect(elementId(r)) AS relationshipIds
WHERE total > 1
RETURN enrollmentId, total, relationshipIds
ORDER BY total DESC
LIMIT 50;
```

These queries inspect relationships along their stored direction; they do not automatically restrict start/end node labels. If you plan to apply a **composite** relationship key, check every component of the key tuple.

### 8.4. Finding Wrong-Type Values

On Neo4j versions supporting type predicate syntax, filter `credits` values that are present but not `INTEGER`:

```cypher
MATCH (c:Course)
WHERE c.credits IS NOT NULL
  AND NOT (c.credits IS :: INTEGER)
RETURN elementId(c) AS nodeElementId,
       c.courseCode AS courseCode,
       c.credits AS credits
LIMIT 50;
```

If your version does not support type predicates, choose a type-inspection mechanism compatible with that release (such as application-side export/audit scripts); do not run newer-version syntax and mistake a syntax error for a data audit.

When fixing data, distinguish valid numeric strings like `'3'` from bad values like `'three credits'` or `'3.5'`. Any type conversion must follow a clear policy rather than coercing invalid values into a default number just to make the migration pass.

## 9. Schema Deployment and Verification Workflow

A practical deployment sequence:

1. **Define invariants:** choose single vs. composite keys, node labels or relationship types, mandatory properties, types, and value ranges.
2. **Verify support:** confirm Neo4j DBMS version, edition, schema privileges, and constraint types.
3. **Audit data:** detect duplicates, missing values, wrong types, and inconsistent code formatting (e.g., `'neo101'` vs. `'NEO101'`).
4. **Fix write pipelines first:** normalize and validate data in Java/services/CSV imports so new errors stop arriving; then clean legacy records.
5. **Create constraints via migrations:** execute the corresponding `CREATE CONSTRAINT` statements in an appropriate deployment window, as creation may scan existing data and consume resources.
6. **Re-read schema and test write paths:** verify the constraint actually exists on the right target and properties; test both valid and violating operations.

Verify:

```cypher
SHOW CONSTRAINTS;
```

In Neo4j 5.x releases with the corresponding metadata columns:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

Compare **name**, **constraint type**, **label/relationship type**, and **property list** against the migration plan. `IF NOT EXISTS` only makes the statement repeatable in matching scenarios; it does not guarantee that another constraint with the same name or an older schema already matches your intent.

Key constraints are backed by indexes managed by Neo4j; those indexes can also accelerate key lookup queries. **A property type constraint is not a lookup index.** Avoid creating duplicate indexes on the same schema if a key constraint already provides a backing index; use `SHOW INDEXES` and `EXPLAIN` to evaluate specific queries.

When a constraint is no longer needed, drop it by name:

```cypher
DROP CONSTRAINT course_code_key IF EXISTS;
```

Do this only after assessing impact: subsequent writes will no longer be guarded by that constraint, and the backing index for the key may be removed along with it.

## 10. Java Driver and Spring Data Neo4j: Two Coordinated Check Layers

Neo4j constraints protect data **regardless of the write path**; Java validation provides earlier error feedback and enforces richer business rules.

### 10.1. Parameterized Writes with the Java Driver

Java Driver 5.x example creating a course with key `tenantId + courseCode` and integer `credits`:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import java.util.Map;

public final class CourseWriter {
    private final Driver driver;

    public CourseWriter(Driver driver) {
        this.driver = driver;
    }

    public void createCourse(
            String tenantId,
            String courseCode,
            String title,
            int credits) {

        if (tenantId == null || tenantId.isBlank()
                || courseCode == null || courseCode.isBlank()) {
            throw new IllegalArgumentException("Course is missing an identifier");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Course title must not be blank");
        }
        if (credits <= 0) {
            throw new IllegalArgumentException("Credits must be positive");
        }

        String cypher = """
            CREATE (c:Course {
                tenantId: $tenantId,
                courseCode: $courseCode,
                title: $title,
                credits: $credits
            })
            RETURN c.courseCode AS courseCode
            """;

        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run(cypher, Map.of(
                    "tenantId", tenantId,
                    "courseCode", courseCode,
                    "title", title,
                    "credits", credits
                )).single();
                return null;
            });
        }
    }
}
```

In this example, the application validates `credits > 0` (a domain-range rule), while the type constraint enforces `INTEGER` and the node key enforces mandatory/unique identity. When a user submits an existing key, the database rejects `CREATE` per the key constraint. If the business rule is "find or create", redesign the query around `MERGE` with an explicit update policy.

`Session.executeWrite` runs a write transaction via the driver API. The application must handle write exceptions caused by constraints, return an appropriate business message, and never report success if the transaction fails. A transaction creating multiple nodes/relationships should be structured so that a failure in a later step does not leave partial changes committed.

### 10.2. Spring Data Neo4j

With Spring Data Neo4j, annotations like `@Node`, `@Relationship`, `@Id`, and `@Property` declare how Java objects map to the graph. Validation annotations such as `@NotNull`, `@NotBlank`, and `@Min` take effect only in validation flows where they are properly triggered; **they do not implicitly create key/type constraints in Neo4j**.

When the business key is `(tenantId, courseCode)` while the Java entity uses a technical ID, do not confuse `@Id` with a database business-key constraint. Manage the Cypher schema through proper migrations, let services validate inputs, and still rely on the database to guard integrity if import jobs or other services write data.

## 11. Alternatives When Your Neo4j Version Does Not Support Key/Type Constraints

If the DBMS/edition does not support node keys, relationship keys, or property type constraints, choose mitigations based on **which invariant truly needs protection**.

| Requirement | Practical Approach in Limited Environments | Limitation |
| --- | --- | --- |
| No duplicate `courseCode` on nodes | Node uniqueness constraint if supported by the running version | Does not enforce property presence |
| Mandatory identifying property | API/service/import validation, plus monitoring queries for missing data | No database guarantee equivalent to existence/key |
| `credits` must be `INTEGER` | Parse/validate before writing, post-import data audits | Write paths bypassing validation can still store bad types |
| Relationship with mandatory, unique ID | Choose an alternative identity model combining validation and available constraints | May not achieve guarantees equivalent to a relationship key |

Never claim that `IS UNIQUE` means the same thing as `IS NODE KEY`, or that a Java annotation completely replaces a database constraint. When multiple applications have direct write access, checks outside the database are easy to bypass without shared workflows and controlled privileges.

If such integrity is a hard system requirement, evaluate deploying a supported Neo4j edition/offering or adjusting the data model and write architecture so the requirement is enforced at the appropriate level.

## 12. Hands-On Exercise: Predicting Constraint Behavior

Suppose a test database has:

```cypher
CREATE CONSTRAINT course_key IF NOT EXISTS
FOR (c:Course)
REQUIRE (c.tenantId, c.courseCode) IS NODE KEY;

CREATE CONSTRAINT course_credits_type IF NOT EXISTS
FOR (c:Course)
REQUIRE c.credits IS :: INTEGER;
```

Predict the outcome of each **independent** operation:

| Operation | Expected Outcome |
| --- | --- |
| Create `Course {tenantId:'T1', courseCode:'NEO101', credits:3}` | Succeeds if key pair `T1/NEO101` does not yet exist |
| Create another node with the same `T1/NEO101` | Rejected by the node key |
| Create `T2/NEO101` with `credits:4` | Succeeds if that key pair does not yet exist |
| Create `Course` with only `tenantId:'T1'` | Rejected because `courseCode` is missing |
| Create `T1/NEO102` with `credits:'3'` | Rejected due to wrong type for `credits` |
| Create `T1/NEO103` without `credits` | Not blocked by **the two constraints above** just for missing `credits` |
| Create `T1/NEO104` with `credits:-2` | Not blocked by **the two constraints above** because `-2` is still an integer |
| Remove `tenantId` from a node with the key | Rejected |
| Create a `:Draft` node with a key pair matching a `:Course` | Does not violate the node key on label `Course` |

To block the missing or negative `credits` cases, add an **existence constraint** on `credits` where supported, alongside business validation enforcing credit limits.

For relationship keys, try creating two `:ENROLLED_IN` relationships connecting the same pair of nodes with two different `enrollmentId` values. Explain why **the relationship key does not reject them** when both IDs exist and differ; from there, determine whether the domain needs a relationship key, an `Enrollment` node key, or another control.

## 13. Common Design Mistakes

1. **Choosing the wrong uniqueness scope.** Using a single `courseCode` key in a multi-tenant system can reject valid cross-tenant codes; using a composite key when codes must be globally unique leaves duplicates unblocked across tenants.
2. **Confusing type constraints with mandatory existence.** A missing property still passes a type constraint; add existence or key constraints as required.
3. **Confusing node keys with format validation.** A key can still be an empty string or malformed code without separate validation.
4. **Placing a relationship key and assuming endpoints have the right labels.** A relationship key does not force `ENROLLED_IN` to connect specifically from `Student` to `Course`.
5. **Including descriptive attributes in `MERGE` patterns.** When descriptions change, `MERGE` may attempt to create a duplicate-key record and trigger an error.
6. **Deploying constraints onto dirty data.** Nodes/relationships missing keys, duplicating keys, or holding wrong types cause DDL statements to fail.
7. **Assuming every edition supports everything.** Running Enterprise-feature DDL on Community can fail; applications must accurately account for deployment capabilities.
8. **Assuming migration succeeded solely because `IF NOT EXISTS` was used.** Always re-read the schema and verify the exact constraint, name, label/relationship type, and property list.

## 14. Conclusion

**Node keys** and **relationship keys** are the right choice when an entity's or relationship's identity must be **both mandatory and unique**. **Property type constraints** ensure stored values on nodes/relationships have the **expected type**, but they do not by themselves guarantee property presence, value ranges, or full business rules.

Applying these mechanisms properly requires defining **label/relationship-type scope**, **single vs. composite keys**, **Neo4j version/edition**, legacy data cleanup prior to migration, and write conventions in the Java Driver/Spring Data Neo4j. When schema and application work together properly, the graph maintains stable identities and clear data contracts, making Cypher relationship/path queries and system operations far more reliable.
