# Mapping Relationships with Properties and Controlling Relationship Direction

In Neo4j, a relationship does not merely connect two nodes—it can also carry its own **properties**: start date, role, status, rating score, quantity, effective timestamp, and more. When building a Java application with **Spring Data Neo4j (SDN)**, you must accurately map both **relationship properties** and **edge direction** so that data persisted into the property graph reflects its business meaning.

This lesson belongs to the **Spring Data Neo4j** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, where Neo4j is used to model connected data, query nodes/relationships with Cypher, optimize with indexes and constraints, and integrate the Java Driver and Spring Data Neo4j. The focus is on `@Node`, `@Relationship`, `@RelationshipProperties`, `@TargetNode`, `@RelationshipId`, using `OUTGOING`/`INCOMING`, and scenarios that easily create reversed edges or lose properties during updates.

The examples target modern Spring Data Neo4j, specifically SDN 7.x with Spring Boot 3.x. Exact API details and persistence behavior must be verified against the SDN/Neo4j versions actually running in your project; this lesson is not a substitute for integration testing.

After this lesson, you will be able to:

- Distinguish node properties from relationship properties in a property graph.
- Map a relationship with properties into a `@RelationshipProperties` class with `@TargetNode`.
- Specify the correct relationship direction when reading or writing from either endpoint node.
- Use repositories and services to persist an aggregate containing relationship properties.
- Use explicit Cypher queries when updating a single relationship, avoiding operations on partially loaded aggregates.
- Verify edge direction, edge cardinality, property values, and write failures with integration tests.

## 1. What Is a Relationship with Properties?

Consider a **student course enrollment** domain:

~~~text
(:Student {studentId:'S01', fullName:'An'})
          |
          | [:ENROLLED_IN {
          |    enrollmentKey:'S01|C101',
          |    enrolledOn:date('2026-01-12'),
          |    status:'ACTIVE',
          |    score:85
          | }]
          v
(:Course {code:'C101', title:'Introduction to Graphs'})
~~~

The graph contains:

- A `Student` node storing student details.
- A `Course` node storing course details.
- An `ENROLLED_IN` relationship **pointing from Student to Course**.
- The properties `enrolledOn`, `status`, and `score` describing a **specific enrollment instance/relationship**, not the student or the course itself.

A course can be taken by many students at different dates, with different statuses and scores. Putting `score` or `enrolledOn` on `Course` would lose the distinction across individual enrollments.

A Cypher query reading the correct direction and properties:

~~~cypher
MATCH (s:Student {studentId: 'S01'})
      -[e:ENROLLED_IN]->(c:Course {code: 'C101'})
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrolledOn AS enrolledOn,
       e.status AS status,
       e.score AS score;
~~~

**Important:** a Java class describing relationship properties **does not automatically create an intermediate node**. With `@RelationshipProperties`, the graph still contains one `(:Student)-[:ENROLLED_IN]->(:Course)` edge holding properties—not `(:Student)-[:HAS]->(:Enrollment)-[:FOR]->(:Course)` (or `[:TO]`).

## 2. Comparing Two Models: Edge Properties vs. Intermediate Node

| Criterion | Relationship with properties | `Enrollment` as a separate node |
| --- | --- | --- |
| Structure | `(Student)-[ENROLLED_IN]->(Course)` | `(Student)-[:HAS]->(Enrollment)-[:FOR]->(Course)` |
| Enrollment attributes | Directly on `ENROLLED_IN`. | On the `Enrollment` node. |
| Hops from Student to Course | One relationship. | Typically two relationships. |
| Best suited when | Enrollment is primarily a link between two entities with a few properties. | Enrollment has an independent lifecycle, multiple relationships of its own, complex history, or needs to be referenced as an entity. |
| Trade-off | Harder to model when multiple edge types must point *to the enrollment itself*. | Increases node count and traversal hops; requires managing a richer model. |

There is no blanket rule that "every join table in an RDBMS must become a node" or "every many-to-many relationship must use relationship properties." First establish the **business invariants**: can a student re-enroll in the same course in another term? If so, the same two endpoints may need multiple relationships with distinct `enrollmentKey` values, or an independent `Enrollment` entity with its own identifier to manage each attempt.

In the examples below, we assume **at most one active managed enrollment per student–course pair**; the system can identify the enrollment with a dedicated business key. When moving to a multi-enrollment model, include the term or attempt ID in the key.

## 3. Core Annotations

| Annotation | Placed where? | Effect |
| --- | --- | --- |
| `@Node("Student")` | Node entity class. | Maps the object to a node with label `Student`. |
| `@Id` | Node key field. | Marks the entity identifier property at the SDN layer. |
| `@Relationship(type="ENROLLED_IN", direction=...)` | Field on the node owning the mapping. | Declares the type and **direction relative to the node containing the field**. |
| `@RelationshipProperties` | Class holding edge properties. | Marks the class as representing a relationship with properties. |
| `@TargetNode` | One field inside the relationship properties class. | Points to the **other node** of the mapped relationship. |
| `@RelationshipId` | Field inside the relationship properties class. | Holds SDN's technical identifier for the persisted relationship. |
| `@Property("...")` | Node or relationship properties field, when needed. | Maps a Neo4j property name that differs from the Java field name. |

A standard `@RelationshipProperties` class requires **one `@TargetNode`** and a relationship identifier per SDN's supported mechanism. Do not replace `@RelationshipId` with a node `@Id`; a relationship does not become a node just because Java uses an object to represent it.

`@RelationshipId` is not a business key to expose in APIs. Never assign it yourself or assume a relationship's technical ID remains stable across deletions/recreations or data re-imports. When an external identifier for an enrollment is needed, use a dedicated business property such as `enrollmentKey` and consider an appropriate constraint.

## 4. Complete Mapping of a Relationship with Properties

The example comprises three separate classes in the same Java package: `Student.java`, `Course.java`, and `Enrollment.java`.

### 4.1. Course Node

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Course")
public class Course {
    @Id
    private String code;

    private String title;

    public Course() {
    }

    public Course(String code, String title) {
        this.code = code;
        this.title = title;
    }

    public String getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Here `@Id` is the business key `Course.code`; the example uses an application-supplied string key. If the application wants SDN to generate node keys automatically, `@GeneratedValue`/ID strategy configuration is a separate concern unrelated to relationship direction.

### 4.2. Enrollment Class Mapping Edge Properties

~~~java
import java.time.LocalDate;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Enrollment {
    @RelationshipId
    private Long id;

    @TargetNode
    private Course course;

    private String enrollmentKey;
    private LocalDate enrolledOn;
    private String status;
    private Integer score;

    public Enrollment() {
    }

    public Enrollment(String enrollmentKey, Course course,
                      LocalDate enrolledOn, String status) {
        this.enrollmentKey = enrollmentKey;
        this.course = course;
        this.enrolledOn = enrolledOn;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public Course getCourse() {
        return course;
    }

    public String getEnrollmentKey() {
        return enrollmentKey;
    }

    public LocalDate getEnrolledOn() {
        return enrolledOn;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Integer getScore() {
        return score;
    }

    public void setScore(Integer score) {
        this.score = score;
    }
}
~~~

Note the field groups:

- `id` annotated with `@RelationshipId`: **technical identifier**, not a client-supplied business property. Let SDN manage it.
- `course` annotated with `@TargetNode`: points to the opposite node of the relationship viewed from `Student`.
- `enrollmentKey`, `enrolledOn`, `status`, `score`: **properties of the `ENROLLED_IN` relationship**.
- `LocalDate` suits a date without time-of-day; if the business domain requires timestamps and timezones, consider temporal types supported by Neo4j/SDN and consistent time conventions.

Do not place `@Node` on `Enrollment` in this model. Adding a direct reference field back to `Student` inside `Enrollment` and treating it as a separate relationship can create Java reference cycles and unexpected mapping structures. The root node `Student` is established by the `@Relationship` field shown next.

### 4.3. Student Node Declaring OUTGOING Direction

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Student")
public class Student {
    @Id
    private String studentId;

    private String fullName;

    @Relationship(
        type = "ENROLLED_IN",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Enrollment> enrollments = new ArrayList<>();

    public Student() {
    }

    public Student(String studentId, String fullName) {
        this.studentId = studentId;
        this.fullName = fullName;
    }

    public String getStudentId() {
        return studentId;
    }

    public String getFullName() {
        return fullName;
    }

    public List<Enrollment> getEnrollments() {
        return enrollments;
    }

    public void addEnrollment(Enrollment enrollment) {
        enrollments.add(enrollment);
    }
}
~~~

With `@Relationship(... OUTGOING)` on `Student.enrollments` and `Enrollment.course` marked as `@TargetNode`, the Java model corresponds to:

~~~text
Student entity
  | enrollments: List<Enrollment>
  |    |-- id (relationship identity)
  |    |-- enrollmentKey, enrolledOn, status, score
  |    '-- course: Course (@TargetNode)
  |
  v
Neo4j: (Student)-[e:ENROLLED_IN { ... }]->(Course)
~~~

**Do not confuse:** a `List<Enrollment>` does not mean each `Enrollment` is a node. It is how SDN bundles **relationship + properties + target node** into a Java object.

## 5. Controlling Direction: OUTGOING and INCOMING

Neo4j stores every relationship with a **start node** and an **end node**. In Cypher, direction is expressed with arrows:

~~~cypher
// Traverse from Student to Course.
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
RETURN s.studentId, c.code, e.status;
~~~

~~~cypher
// Same edge, read from the Course side.
MATCH (c:Course)<-[e:ENROLLED_IN]-(s:Student)
RETURN c.code, s.studentId, e.status;
~~~

Both queries **describe the exact same physical edge direction**: `Student → Course`. The second query simply starts from the other end of the edge.

| Where `@Relationship` is placed | Direction | Mapped edge |
| --- | --- | --- |
| `Student` | `OUTGOING` | `(Student)-[:ENROLLED_IN]->(Course)` |
| `Course` | `INCOMING` | `(Student)-[:ENROLLED_IN]->(Course)` |
| `Course` | `OUTGOING` | `(Course)-[:ENROLLED_IN]->(Student)` — opposite of the chosen model |
| `Student` | `INCOMING` | `(Course)-[:ENROLLED_IN]->(Student)` — opposite of the chosen model |

**Rule:** the annotation's direction is **relative to the Java node class declaring the field**, not the direction of "Java pointer navigation" or the name of the relationship-properties class.

### 5.1. Reading from the Course Side with INCOMING

If a screen only needs to know which students are enrolled in a course, a Course-side representation might look like:

~~~java
@Node("Course")
public class CourseView {
    @Id
    private String code;

    @Relationship(
        type = "ENROLLED_IN",
        direction = Relationship.Direction.INCOMING
    )
    private List<Student> students;

    // Other constructors/getters omitted.
}
~~~

This is a **separate mapping example for a Course-centric view**. Do not simultaneously use `Course` and `CourseView` as two aggregates authorized to update the same relationship set unless you fully understand how SDN manages graph persistence. Moreover, `List<Student>` **does not carry relationship properties like `status` or `enrolledOn`** in the Java objects; it only represents the linked nodes. When you need those properties from the Course side, write a dedicated Cypher query/projection, or define a relationship-properties class from that side with `Student` as `@TargetNode` while governing write ownership per aggregate.

Do not assume that the same `Enrollment` class with `@TargetNode Course` can automatically be reused as-is for an `INCOMING` field on `Course`. When mapping from the Course side, the "other" node is `Student`, so the wrapper structure must be designed accordingly.

### 5.2. What Happens with Undirected Queries?

~~~cypher
MATCH (a:Student)-[e:ENROLLED_IN]-(b:Course)
RETURN a.studentId, b.code;
~~~

The pattern `-[e]-` does not constrain direction; while useful for exploratory checks, it can **mask edges created in the wrong direction**. For course enrollment, always specify the arrow explicitly in critical read queries and especially in write queries.

### 5.3. Relationships Do Not Automatically Stay In-Memory Bidirectional Inverses

If `Student.enrollments` is modified in memory, a `Course.students` field on another object is **not automatically synchronized in memory** like an ORM-managed bidirectional association. Both representations can read the same relationship in Neo4j, but object lifecycle, load timing, and save scope remain independent concerns.

In particular, avoid configuring both sides for automatic writes and then saving an object that holds only a **partially loaded edge set**. A later save from one side can delete or overwrite information persisted from the other side depending on aggregate state and mapping rules.

## 6. Repositories and Services Persisting Relationships with Properties

Basic repository definitions:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface StudentRepository
        extends Neo4jRepository<Student, String> {
}
~~~

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CourseRepository
        extends Neo4jRepository<Course, String> {
}
~~~

A service can look up the source and target nodes, then add an `Enrollment` wrapper to the `Student` aggregate:

~~~java
import java.time.LocalDate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrollmentService {
    private final StudentRepository students;
    private final CourseRepository courses;

    public EnrollmentService(StudentRepository students,
                             CourseRepository courses) {
        this.students = students;
        this.courses = courses;
    }

    @Transactional
    public void enroll(String studentId, String courseCode,
                       LocalDate enrolledOn) {
        Student student = students.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Student not found"));
        Course course = courses.findById(courseCode)
            .orElseThrow(() -> new IllegalArgumentException(
                "Course not found"));

        boolean alreadyEnrolled = student.getEnrollments().stream()
            .anyMatch(e -> courseCode.equals(e.getCourse().getCode()));
        if (alreadyEnrolled) {
            throw new IllegalStateException("Already enrolled");
        }

        // Illustrative business key for sample data only.
        String enrollmentKey = studentId + "|" + courseCode;
        student.addEnrollment(new Enrollment(
            enrollmentKey, course, enrolledOn, "ACTIVE"));

        students.save(student);
    }
}
~~~

Assumptions in this example:

1. Both nodes already exist, identifiers are unique, and each Student–Course pair has at most one enrollment.
2. `Student` is loaded with the **complete** relationship set to be managed during `save`; if a query loads only a subset, never assume saving the aggregate is safe.
3. The demo IDs do not contain the `|` character; in production, composite keys must be properly normalized/escaped or use an independent enrollment ID rather than naive string concatenation.
4. `@Transactional` must execute through the Spring proxy with the appropriate Neo4j transaction manager. Self-invocation of a `@Transactional` method from another method in the same bean may bypass proxy transaction interception.
5. The `alreadyEnrolled` check is an application-layer guard **within one read snapshot** and does not prevent race conditions under concurrent requests. Pair it with locking/constraint strategies and concurrency tests for critical data.

After saving successfully, verify with Cypher:

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN]->(c:Course {code: $courseCode})
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrollmentKey AS enrollmentKey,
       e.enrolledOn AS enrolledOn,
       e.status AS status;
~~~

`save(...)` persists the node and aggregate relationships according to SDN's mapping model. Do not treat it as a statement that "merely appends one relationship" in every situation. When updating a single enrollment inside a very large collection, an explicitly written Cypher query is often easier to control.

## 7. Creating and Updating Relationships with Explicit Cypher

When the application only needs to update **one** enrollment without loading the entire student–course graph, place an explicit Cypher query on a repository or invoke it via `Neo4jClient`.

### 7.1. Upserting a Relationship with a Business Key

~~~cypher
MATCH (s:Student {studentId: $studentId})
MATCH (c:Course {code: $courseCode})
MERGE (s)-[e:ENROLLED_IN {
  enrollmentKey: $enrollmentKey
}]->(c)
ON CREATE SET e.enrolledOn = $enrolledOn
SET e.status = $status
RETURN count(e) AS matchedRelationships;
~~~

Key points:

- `MATCH` verifies both endpoints. If either endpoint is missing, **no relationship is created** and `count(e)` is 0; the service must handle that case rather than assuming success.
- `MERGE` matches the **full pattern** including type, direction, endpoints, and the `enrollmentKey` property. If no matching edge exists, a new edge is created.
- If an existing edge connects the same two endpoints from legacy data **without `enrollmentKey`**, `MERGE` can create an additional edge; audit and clean legacy data prior to migration.
- If duplicate edges already exist, a `MERGE` does not consolidate historical duplicates into one edge; investigate and reconcile the root cause.
- `ON CREATE SET` initializes `enrolledOn` only when creating; `SET e.status` runs on both create and match. If business rules allow changing the enrollment date, design a different policy.

A similar query can be declared in a repository:

~~~java
import java.time.LocalDate;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface EnrollmentCommandRepository
        extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student {studentId: $studentId})
        MATCH (c:Course {code: $courseCode})
        MERGE (s)-[e:ENROLLED_IN {
          enrollmentKey: $enrollmentKey
        }]->(c)
        ON CREATE SET e.enrolledOn = $enrolledOn
        SET e.status = $status
        RETURN count(e)
        """)
    long upsertEnrollment(
        @Param("studentId") String studentId,
        @Param("courseCode") String courseCode,
        @Param("enrollmentKey") String enrollmentKey,
        @Param("enrolledOn") LocalDate enrolledOn,
        @Param("status") String status);
}
~~~

Verify the returned count and scalar type mapping on your exact Spring Data Neo4j version. In real applications, invoke this from a `@Transactional` service while validating inputs, write permissions, and uniqueness errors. Never interpolate untrusted dynamic label/type names via string concatenation.

### 7.2. Constraint for the Relationship Key

If the application designates `enrollmentKey` as the global identifier of an enrollment:

~~~cypher
CREATE CONSTRAINT enrollment_key_unique IF NOT EXISTS
FOR ()-[e:ENROLLED_IN]-()
REQUIRE e.enrollmentKey IS UNIQUE;
~~~

This constraint prevents **two `ENROLLED_IN` relationships from sharing the same `enrollmentKey` when the property is present**. It does not guarantee that every relationship has an `enrollmentKey`, nor does it guarantee only one edge exists per Student–Course pair if edges use different keys. When both existence and uniqueness are required, evaluate relationship key/existence constraints available in your Neo4j version and edition, and pair them with clear business key generation and concurrency handling.

For instance, when two concurrent requests enroll the same student in the same course, both may pass the `alreadyEnrolled` check before writing. A constraint on a **deterministically generated business key** blocks committing two edges with the same key; the service must catch the error, re-read state, and decide retry/idempotency behavior properly.

### 7.3. Updating Only an Edge Property

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN {enrollmentKey: $enrollmentKey}]->
      (c:Course {code: $courseCode})
SET e.status = $newStatus
RETURN e.enrollmentKey AS enrollmentKey,
       e.status AS status;
~~~

This query changes only the `status` property on the matching edge. If no relationship matches, it returns 0 rows; the service should distinguish "not found" from "updated." If corrupted data left multiple matching edges between the endpoints, verify the count and handle it rather than silently updating all of them.

### 7.4. Deleting Only the Edge Instead of Deleting Nodes

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN {enrollmentKey: $enrollmentKey}]->
      (c:Course {code: $courseCode})
DELETE e;
~~~

`DELETE e` deletes only the matching relationship **without deleting Student or Course**. Never run `DETACH DELETE s` or `DETACH DELETE c` to "cancel an enrollment"; that deletes the node and all of its other relationships.

If business rules require keeping cancellation history, replace physical deletion with `SET e.status = 'CANCELLED'` or a dedicated event model. That choice affects read queries, edge counts, and the "one active enrollment" invariant.

## 8. Reading from Repositories While Preserving Relationship Properties

A custom `@Query` that returns only `Student` or `Course` may not give SDN enough information to hydrate all relationships and properties as intended. When returning a `Student` aggregate with its `Enrollment` entries, the query must return the root, relationships, and target nodes.

Example:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface StudentGraphRepository
        extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student {studentId: $studentId})
        OPTIONAL MATCH (s)-[e:ENROLLED_IN]->(c:Course)
        RETURN s, collect(e), collect(c)
        """)
    Optional<Student> findWithEnrollments(
        @Param("studentId") String studentId);
}
~~~

`OPTIONAL MATCH` ensures a student with zero enrollments is still returned. `collect(e)` and `collect(c)` pass the related edges and nodes in the result structure so the mapper can reconstruct `Student.enrollments`. Custom query projection/return-shape details can vary slightly across SDN versions; always verify with an integration test.

**Warning about partially loaded aggregates:** if a custom query returns only a subset of enrollments (for example, top 3 or `ACTIVE` only) and you modify `fullName` and call `students.save(student)`, SDN may treat the object's relationship list as the desired target state and **overwrite or delete relationships missing from the object** depending on the SDN version and mapping configuration. Never pass a partially loaded read result into `save` as if it were a complete aggregate without testing the behavior.

If a screen only needs a display list, use a simple read DTO projection to avoid accidental saves:

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN]->(c:Course)
RETURN c.code AS courseCode,
       c.title AS courseTitle,
       e.enrolledOn AS enrolledOn,
       e.status AS status,
       e.score AS score
ORDER BY courseCode;
~~~

This query intentionally returns **tabular rows**, not a root aggregate meant to be saved back. In Java, map these rows via `Neo4jClient` or a repository projection supported by your SDN version.

## 9. Multiple Relationships, Cardinality, and Identity

A learner can enroll in multiple courses:

~~~text
(Student S01)-[:ENROLLED_IN {status:'ACTIVE'}]->(Course C101)
      |
      '--[:ENROLLED_IN {status:'ACTIVE'}]----->(Course C102)
~~~

`List<Enrollment>` models multiple relationships; `Set<Enrollment>` can also fit when Java equality/hashCode semantics are defined properly. Distinguish carefully among:

1. **Java model cardinality:** whether a field is `Enrollment` or `List<Enrollment>`.
2. **Actual relationship count:** Neo4j allows multiple edges of the same type between the same two nodes unless prevented by write logic or constraints.
3. **Technical identity:** `@RelationshipId` managed by SDN to track persisted edges.
4. **Business identity:** `enrollmentKey` assigned by the application and enforced via constraints and write flows.

Do not rely on a `Set` whose `equals`/`hashCode` uses the technical ID while the ID is still `null` to enforce "a student enrolls in a course only once." Two newly constructed objects can represent the same Student–Course pair; service validation and database constraints form the true boundary.

### 9.1. Re-Enrolling in the Same Course Multiple Times

If a student re-enrolls in course C101 in a different term:

~~~text
(Student S01)-[:ENROLLED_IN {
  enrollmentKey:'E-2026-SPRING-S01-C101',
  term:'2026-SPRING'
}]->(Course C101)

(Student S01)-[:ENROLLED_IN {
  enrollmentKey:'E-2026-FALL-S01-C101',
  term:'2026-FALL'
}]->(Course C101)
~~~

These are two distinct relationships with the same endpoints and type but different **enrollment keys**. A `MERGE (s)-[e:ENROLLED_IN]->(c)` without the enrollment key would match both and update the wrong edge. When the domain allows multiple attempts, include `term`/`enrollmentId` in the identifying key and consider whether `Enrollment` should become a standalone node.

## 10. Controlling Paths and Preventing Wrong-Way Edges

A solid design practice is to establish a **canonical direction** for every relationship type and document it explicitly in domain specifications:

| Type | Start node | End node | Meaning |
| --- | --- | --- | --- |
| `ENROLLED_IN` | `Student` | `Course` | Student enrolls in course. |
| `TEACHES` | `Teacher` | `Course` | Instructor teaches course. |
| `PREREQUISITE_OF` | Prerequisite `Course` | Subsequent `Course` | Earlier course is a prerequisite for the later course. |

For relationship types with directional semantics, keep the direction consistent across both Cypher and annotations. A common bug:

~~~cypher
// WRONG with respect to the chosen ENROLLED_IN contract:
MERGE (c:Course {code: $courseCode})
      -[:ENROLLED_IN]->
      (s:Student {studentId: $studentId});
~~~

This statement matches/creates nodes and creates an edge **Course → Student**. That is not reading in reverse from Course—it is physically persisting the wrong direction relative to the model. Having the same two endpoint nodes does not make two oppositely directed edges identical.

Query to detect wrong-way edges:

~~~cypher
MATCH (c:Course)-[e:ENROLLED_IN]->(s:Student)
RETURN c.code AS courseCode,
       s.studentId AS studentId,
       e.enrollmentKey AS enrollmentKey
LIMIT 50;
~~~

In a model permitting only `Student → Course`, this query must return **0 rows**. Whenever rows appear, investigate the writer before fixing; do not bulk-delete blindly, as another use case might be misusing the same relationship type.

### 10.1. Verifying a Student's Expected Relationships

~~~cypher
MATCH (s:Student {studentId: $studentId})
OPTIONAL MATCH (s)-[e:ENROLLED_IN]->(c:Course)
RETURN s.studentId AS studentId,
       count(e) AS relationshipCount,
       count(DISTINCT c) AS distinctCourses,
       collect(DISTINCT c.code) AS courseCodes;
~~~

If business rules allow at most one enrollment per course, `relationshipCount` must equal `distinctCourses` for a student with valid endpoints. If multiple attempts are allowed, **that invariant no longer holds**; switch to validating counts per `enrollmentKey`/`term`.

### 10.2. Detecting Relationships Missing Critical Properties

~~~cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
WHERE e.enrollmentKey IS NULL
   OR e.enrolledOn IS NULL
   OR e.status IS NULL
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrollmentKey AS enrollmentKey,
       e.enrolledOn AS enrolledOn,
       e.status AS status
ORDER BY studentId, courseCode
LIMIT 100;
~~~

This result should be empty if all valid enrollments require these properties. SDN annotations do not automatically turn Java fields into database constraints; enforcing presence requires schema constraints and input validation.

## 11. Transactions, Concurrent Updates, and Missing Data

When creating a relationship and updating related node state, run all atomic writes **inside the same transaction**. Use Spring's `@Transactional` at the proper service boundary or explicit/managed transactions on the Neo4j Java Driver.

Scenarios to handle:

- **Missing endpoint:** `MATCH` returns 0 rows; never report success merely because the statement did not throw an exception.
- **Concurrent transactions:** two requests may both observe the student as not yet enrolled and both attempt to create the edge; unique business keys and retry policies must be tested.
- **Partially loaded aggregate:** avoid calling `save` on an object missing edges due to a filtered custom query.
- **Single-property update:** prefer a targeted query updating just the target relationship's property instead of rewriting the whole aggregate.
- **Duplicate edges in legacy data:** before introducing `MERGE` or a new constraint, audit edge counts and business keys.
- **Canceling an enrollment:** decide between physical deletion and `status = 'CANCELLED'`; each choice affects read queries, history, and the "one active enrollment" invariant.
- **Missing tenant scope:** in multi-tenant systems, `studentId` or `courseCode` may not be globally unique; use composite keys `(tenantId, businessId)` and filter both endpoints.

Example tenant-scoped query when `tenantId` is part of the composite key:

~~~cypher
MATCH (s:Student {
  tenantId: $tenantId, studentId: $studentId
})
MATCH (c:Course {
  tenantId: $tenantId, code: $courseCode
})
MERGE (s)-[e:ENROLLED_IN {
  enrollmentKey: $enrollmentKey
}]->(c)
ON CREATE SET e.enrolledOn = $enrolledOn
SET e.status = $status
RETURN count(e) AS matchedRelationships;
~~~

This variant illustrates the pattern **once `tenantId` has been added to both node types with matching composite constraints**. Do not apply it directly to the Java classes in Section 4 without adding `tenantId` fields and updating keys/write flows.

## 12. Integration Testing: Inspecting the Actual Persisted Graph Shape

A unit test asserting that `student.addEnrollment(...)` succeeds in memory **does not prove** SDN persisted the right properties and edge direction. You need integration tests against a real Neo4j instance—ideally a dedicated test instance/DB (e.g., via Testcontainers) running the same SDN version as the application.

### 12.1. Minimum Test Matrix

| Test | Action | What to assert with Cypher |
| --- | --- | --- |
| T01 | Save a Student with an Enrollment to Course. | Exactly one `Student-[ENROLLED_IN]->Course` edge exists with expected properties. |
| T02 | Reload Student via repository. | `enrollments` contains the target Course and edge property fields. |
| T03 | Query from Course using `INCOMING`. | Sees the original student without creating a reversed edge. |
| T04 | Change `status` of an Enrollment. | Only the matching relationship changes status; endpoint nodes are not wrongly altered. |
| T05 | Delete an enrollment relationship. | Only the edge is deleted; Student and Course remain intact. |
| T06 | Two concurrent requests create the same `enrollmentKey`. | Two edges with the same key are never committed; error is handled properly. |
| T07 | Fixture contains a wrong-way edge. | Detection query catches it; read flows do not treat reversed edges as valid enrollments. |
| T08 | Partially load aggregate then save. | Other relationships are not wiped out; if risk exists, switch to targeted update queries. |
| T09 | Two enrollments in the same course across different terms (if allowed). | Two distinct relationships exist keyed by key/term without overwriting each other. |
| T10 | Missing endpoint. | No new edge is created and the service throws an appropriate business error. |

Tests must start from known fixture data and never share a database with live user data. When asserting commit or rollback behavior, read back in an independent transaction when needed rather than inspecting only in-memory objects.

### 12.2. Cypher Checks for Direction, Properties, and Cardinality

After a test enrolls S01 in C101:

~~~cypher
MATCH (s:Student {studentId: 'S01'})
      -[e:ENROLLED_IN]->(c:Course {code: 'C101'})
RETURN count(e) AS relationshipCount,
       collect(e.status) AS statuses,
       collect(e.enrollmentKey) AS businessKeys,
       collect(e.enrolledOn) AS enrolledDates;
~~~

With a single-enrollment fixture, expect `relationshipCount = 1`, statuses containing `'ACTIVE'`, and matching business key and date. Check the reverse direction:

~~~cypher
MATCH (c:Course {code: 'C101'})
      -[e:ENROLLED_IN]->
      (s:Student {studentId: 'S01'})
RETURN count(e) AS reversedRelationships;
~~~

The expected value of `reversedRelationships` is **0**. If you inspect both directions via an undirected pattern, compare `startNode(e)` and `endNode(e)`; the critical goal is asserting **physical direction**.

### 12.3. Testing the Mapper with a Java Repository

An integration test skeleton:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

@DataNeo4jTest
class RelationshipMappingTest {
    @Autowired
    StudentRepository students;

    @Autowired
    CourseRepository courses;

    @Test
    void loadsRelationshipProperties() {
        Course course = courses.save(
            new Course("C101", "Introduction to Graphs"));
        Student student = new Student("S01", "An");
        student.addEnrollment(new Enrollment(
            "S01|C101", course, LocalDate.of(2026, 1, 12), "ACTIVE"));

        students.save(student);
        Student reloaded = students.findById("S01").orElseThrow();

        assertThat(reloaded.getEnrollments()).hasSize(1);
        Enrollment loaded = reloaded.getEnrollments().get(0);
        assertThat(loaded.getCourse().getCode()).isEqualTo("C101");
        assertThat(loaded.getStatus()).isEqualTo("ACTIVE");
        assertThat(loaded.getEnrolledOn())
            .isEqualTo(LocalDate.of(2026, 1, 12));
    }
}
~~~

This sample illustrates the test API and must run against a **configured Neo4j test instance**; `@DataNeo4jTest` does not start a database automatically on its own. Some test configurations roll back transactions automatically; add Cypher verification in an independent transaction when proving **durability across commits**. When running multiple tests, use isolated fixture keys or clean the test database to prevent false positives/negatives.

## 13. Common Relationship Mapping Errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Edge created in reverse direction | `@Relationship(direction = INCOMING)` placed on Student when model specifies OUTGOING, or reversed Cypher `MERGE`. | Document canonical directions, verify arrows in Cypher, and test direction explicitly. |
| Course node exists but Enrollment properties are missing | Field is `List<Course>` instead of `List<Enrollment>` with `@RelationshipProperties`. | Use a wrapper class with `@TargetNode` and place properties on the wrapper. |
| Unexpected `Enrollment` nodes appear in Neo4j | `@Node` placed on `Enrollment` when edge properties were intended. | Decide cleanly between an intermediate node model and a relationship-properties model. |
| Loading fails to populate Enrollment | Custom Cypher does not return root + relationship + target, or type/direction is wrong. | Verify return shape, annotations, and query with an integration test. |
| Saving deletes unrelated edges | Saving an aggregate loaded with only a subset of relationships. | Use narrow update queries or load the full aggregate; test with pre-existing edges. |
| Duplicate Student–Course edges appear after retry | Missing stable business key or missing concurrency guard. | Design `enrollmentKey` with uniqueness and handle retries/idempotency. |
| Enrollment creation succeeds silently with no edge created | Missing endpoint caused `MATCH` to return 0 rows. | Check affected row count and throw a business exception. |
| Adding `INCOMING` on Course causes unintended overwrites | Two aggregates both write edge state while loaded out of sync. | Designate one write owner and separate read models/projections. |
| `@RelationshipId` exposed as a public enrollment code | Confusing technical ID with business key. | Use a dedicated business key property and constraint. |
| Re-enrollments overwrite each other | `MERGE` matches only endpoints/type without an attempt key. | Include `enrollmentKey`/`term` in the pattern or promote Enrollment to a node. |
| Cross-tenant wrong target node linked | Course looked up by `code` alone when codes collide across tenants. | Scope both endpoints by tenant and use tenant-aware composite keys. |
| Undirected query returns data despite wrong-way edges | Using `-[:ENROLLED_IN]-` where business semantics require a specific arrow. | Use `->` or `<-` per the domain contract. |

## 14. Practice Exercises

**Exercise 1 — Choosing property placement.** A system has `Student`, `Course`, and attributes `score`, `enrolledOn`, `status`. Explain why those three fields belong on the relationship rather than on the `Student` or `Course` node. Describe a scenario that would prompt you to promote `Enrollment` into a separate node.

**Exercise 2 — Two-sided arrows.** Given `(Student)-[:ENROLLED_IN]->(Course)`, write the corresponding `@Relationship` annotation when placed on `Student` and when placed on `Course`. Write two Cypher queries reading the same edge from each direction.

**Exercise 3 — Missing `@TargetNode`.** A `@RelationshipProperties` class contains `status` but lacks a `@TargetNode` field. Explain why the mapper cannot resolve the full endpoint pair, and fix the class.

**Exercise 4 — Duplicate data.** A student has two `ENROLLED_IN` relationships to the same Course, even though business rules allow only one. Design a detection query, data cleanup steps, a constraint, and a service update strategy to prevent recurrence.

**Exercise 5 — Multiple enrollments.** Students can enroll in the same course across two terms. Choose a new identifying key and update the relationship properties class and `MERGE` query. Explain why `MERGE (student)-[:ENROLLED_IN]->(course)` is insufficient.

**Exercise 6 — Partial aggregate.** A repository query fetches only the first three enrollments, and then code edits `fullName` and calls `save(student)`. What risk do the remaining relationships face? Propose a query that updates only the student's name and list the integration tests to run.

**Exercise 7 — Multi-tenant.** Both tenant A and tenant B have a Student with ID `S01` and a Course with code `C101`. Design the keys and `ENROLLED_IN` creation query so data never links across tenants.

**Exercise 8 — Testing direction.** Write two Cypher assertions: one requiring exactly one `Student → Course` edge with `status = 'ACTIVE'`, and one requiring zero `Course → Student` edges of the same type. Explain why checking only Java objects after saving is insufficient.

## 15. Pre-Production Checklist for Relationship Mappings

1. **Domain definition:** which relationships exist, between which node types, and which properties belong to nodes vs. edges?
2. **Canonical direction:** does every type have a documented canonical direction, with `OUTGOING`/`INCOMING` declared accurately relative to the owning Java class?
3. **Identity design:** `@Id` is the node key and `@RelationshipId` is technical; relationship business keys are managed explicitly.
4. **Aggregate boundaries:** who owns writes to the relationship set? Could any partial-load custom query accidentally be passed to `save`?
5. **Data integrity:** proper constraints, endpoint and tenant validation, concurrent update handling, and retry safety.
6. **Read/write testing:** assertions cover nodes, relationship type, direction, cardinality, properties, `INCOMING` reads, and failure cases.
7. **Performance check:** is loading the entire relationship set justified, or should a specific screen use a Cypher projection or narrow update?
8. **Change management:** are migrations prepared for new types/properties, relationship backfills, duplicate detection, and rollback?

**Conclusion:** in Spring Data Neo4j, `@RelationshipProperties` models **edge properties**, `@TargetNode` identifies the opposite node, and `@Relationship(direction=...)` specifies **the physical direction of the relationship relative to the mapped node**. Designing these three aspects carefully—alongside business keys, controlled Cypher queries, and integration tests—ensures your application persists property graphs accurately without duplicate, reversed, or lost relationships during aggregate updates.
