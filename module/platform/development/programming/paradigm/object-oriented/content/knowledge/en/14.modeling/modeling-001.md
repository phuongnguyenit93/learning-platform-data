# Gathering Use Cases and Business Rules for OOP Modeling

**Goal:** Start with the user's story, identify **use cases**, **business rules**, and **invariants**, and only then determine object responsibilities and build testable Java APIs. This lesson uses **student course enrollment**; its business rules are illustrative assumptions, not default policies for every learning platform.

## 1. Why Gather Requirements Before Designing Classes?

An initial requirement is often very brief:

> “A student wants to enroll in a course. The system reports success if enrollment is possible.”

Starting immediately with classes such as `Student`, `Course`, `EnrollmentService`, and `Database` risks overlooking questions that determine behavior:

- May students enroll before their accounts are activated?
- What happens when course registration is closed?
- Must prerequisites be completed first, or are exceptions allowed?
- Can a student enroll in the same course twice?
- If two students simultaneously request the last available seat, who gets it?
- What information must be stored and returned after successful enrollment?
- If the notification email fails, is the enrollment still successful?
- Who may change capacity, deadlines, and prerequisite lists?

A **use case** describes a goal an **actor** achieves through interaction with a system. A **business rule** specifies organizational conditions, policies, or constraints that use cases must follow. They complement each other:

- A use case asks: **Who does what, toward which goal, and through which flows?**
- A business rule asks: **Under which conditions may or must the system permit or reject that action?**
- A domain model asks: **Which concepts exist, what state do they hold, and which constraints must they protect?**

Do not assume every noun in a requirement must become a class or every use-case step a method. Modeling translates business language into software responsibilities and contracts.

## 2. Identify Scope and Information Sources

Before interviewing stakeholders, establish the **system boundary**, objectives, and involved parties.

| Element | Question to clarify | Example in the course-enrollment system |
|---|---|---|
| Primary actor | Who initiates the interaction to accomplish the goal? | Student |
| Other stakeholders | Who defines/approves rules, and who is affected? | Academic office, instructors, administrators |
| Goal | What outcome brings value to the actor? | A valid place in a course |
| External systems | Which systems does this depend on? | Authentication, academic records, email |
| Scope | Which part is this application responsible for? | Eligibility checks and enrollment |
| Uncertainty | Who has authority to decide the answer? | Academic office confirms eligibility policy |
| Nonfunctional constraints | Volume, response time, security, auditing? | Concurrent enrollments without exceeding capacity |

A request to “check whether a student has completed course A” may require data from another academic system. Identify the **source of truth**, when it updates, and how the application behaves when that service is unavailable.

## 3. Gather Requirements Through Concrete Scenarios

Combine practical techniques rather than only asking “which screens are needed?”

### Goal-Oriented Interviews

Ask students about their steps, academic staff about policies, and operations teams about exceptions and inconsistent data. For example:

1. “What happened the last time you enrolled in a course, from beginning to end?”
2. “When has the system rejected enrollment even though an authorized staff member granted an exception?”
3. “What counts as **one** course seat: one account, one student, or one enrollment event?”
4. “How should the system decide when two people request the last seat simultaneously?”
5. “What data or event proves enrollment succeeded?”
6. “Who may change the policy, and do we need version history?”

Avoid leading questions like “Should we have an Enroll button?” They shift discussion toward UI before the goal is understood.

### Observation and Process Shadowing

Observe staff processing real cases, inputs, decisions, and exceptional procedures. “Valid enrollment” may conceal credit limits, timetable clashes, prerequisites, and tuition debt checks. Do not add these rules to the model unless stakeholders confirm them.

### Workshops with Examples and Counterexamples

Use numerical examples to clarify ambiguous wording:

| Proposed scenario | Question to settle |
|---|---|
| 1 seat remains; 2 simultaneous requests arrive | Who wins? Is there a queue? |
| A student completed a prerequisite, but academic records have not synchronized | Reject, await synchronization, or conditionally enroll? |
| Already enrolled; the same request is sent again | Report “already enrolled,” return the previous result, or signal an error? |
| Enrollment succeeds; the email fails | Cancel enrollment? Retry notification? |
| Course is full; an administrator increases capacity | Who may do this, and must it be audited? |

Every example should specify **input, prior state, action, expected result, and rationale**. When stakeholders disagree, record the conflict and decision owner rather than picking an answer yourself.

### Lightweight Event Storming

Write down events that have occurred, such as “Student requested enrollment,” “Enrollment rejected,” or “Student enrolled,” then work backward:

- What triggered the event?
- Which actor or object made the decision?
- Which conditions had to hold before the event?
- Must the event be stored, or is the final state enough?
- Does another system react to the event afterward?

Event storming helps reveal responsibility boundaries, but **does not require** event sourcing or a message broker.

## 4. Standardize a Use Case Specification

An example use case, **UC-01 – Enroll in a Course**, within the hypothetical system:

| Attribute | Description |
|---|---|
| **ID / Name** | UC-01 / Enroll in a Course |
| **Goal** | A student obtains a valid enrollment in a course |
| **Primary actor** | Authenticated student |
| **Trigger** | Student requests enrollment in a selected course |
| **Preconditions** | The system identifies both student and course; user has permission to submit the request |
| **Success flow** | 1. Receive request → 2. Load student and course state → 3. Check policies → 4. Enroll atomically → 5. Return confirmation |
| **Alternative flows** | Inactive account, closed registration, missing prerequisites, duplicate enrollment, no remaining seats |
| **Success postconditions** | Exactly one enrollment exists for the student–course pair; available seats decrease according to policy |
| **Failure guarantee** | No new enrollment is created and capacity is never exceeded |
| **Output** | Course ID, student ID, status, and appropriate message |
| **Out of scope for this example** | Payment, withdrawal, waiting lists, manual enrollment by staff |

The “authenticated” precondition differs from the rule that an account must be **active**: a user may be able to sign in but be barred from enrollment by policy. A good use case specification distinguishes them.

Avoid details like “click the green button at the top right” in a **business use case**. That belongs to UI design or interface testing; a use case should remain abstract enough for APIs, web, and mobile clients to achieve the same goal.

## 5. Write Business Rules That Can Be Tested

The following rules are **assumptions chosen for the example**:

| ID | Business rule | Result of violation |
|---|---|---|
| BR-01 | Only students with **active** status may enroll | Reject without enrolling |
| BR-02 | Enrollments are accepted only while registration is **open** | Reject |
| BR-03 | A student must have completed **all prerequisites** for the course | Reject |
| BR-04 | A student may have **at most one** enrollment in the same course | Reject duplicate request |
| BR-05 | Enrollments must not exceed course **capacity** | Reject when full |
| BR-06 | Successful enrollment updates state **atomically** | No partially recorded state |

A well-specified rule includes:

- **Stable ID** for use in use cases, tickets, tests, and documentation.
- **Clear statement** of inputs, conditions, and behavior when conditions are not met.
- **Rule owner**: the business group authorized to make decisions.
- **Applicability**: course type, study program, location, time period, and exceptions.
- **Effective date and version** if policies change by term.
- **Valid and invalid examples** to remove ambiguity.

For example, “eligible to enroll” is not testable. Replace it with “BR-03: before enrollment, the set of completed courses must include every prerequisite of the selected course.”

Distinguish **business rules** from **technical constraints**:

- “A class with capacity = 30 must not enroll more than 30 students” is a business rule.
- “Column `student_id` has type VARCHAR(36)” is a technical choice.
- “Each student may have one enrollment per course” is a business rule; a DB unique constraint on `(course_id, student_id)` is **one mechanism** for enforcing it.

## 6. Specify Failure Flows as Carefully as Success Flows

Do not stop at “save to DB on success.” Build a business decision matrix:

| Initial state | Action | Expected outcome | Rule |
|---|---|---|---|
| Active student, open course, prerequisites met, seat available | Enroll | Success; available seats decrease by 1 | BR-01..06 |
| Inactive student | Enroll | Reject; enrollment count unchanged | BR-01 |
| Registration closed | Enroll | Reject; state unchanged | BR-02 |
| Prerequisites missing | Enroll | Reject; do not reserve a seat | BR-03 |
| Already enrolled in the course | Enroll again | Reject or return prior result, depending on chosen policy | BR-04 |
| Course at capacity | Enroll | Reject; capacity not exceeded | BR-05 |
| Two requests compete for the last seat | Enroll | At most one succeeds | BR-05, BR-06 |

These counterexamples become acceptance criteria and tests. For retransmitted network requests, **establish an idempotency policy**: a “duplicate enrollment” and “retry of the same request” may need different behavior. The simple Java example below **rejects duplicate enrollments** and does not implement idempotency keys.

## 7. Map Use Cases and Business Rules to a Class Model

First separate **concepts**, **state**, **invariants**, and **behavior**:

| Concept | Minimal state | Behavior / responsibility |
|---|---|---|
| `Student` | ID, active status, completed courses | Supplies eligibility facts and keeps student state consistent |
| `Course` | ID, capacity, registration status, prerequisites, enrolled student IDs | Decides whether to accept enrollment; enforces capacity and uniqueness |
| `EnrollmentReceipt` | Course ID, student ID, enrollment count after operation | Returns immutable data to the caller |
| `EnrollmentUseCase` (with a real DB/API) | Required dependencies | Loads data, checks permissions, invokes domain logic, persists in a transaction, returns result |
| Repository / Adapter | Storage technology | Loads/saves domain state and ensures transactions as designed |

Not every noun is a class. “Enroll button,” “screen,” and “email” may belong to presentation or integration rather than the domain. A simple capacity invariant does not justify a separate `CapacityValidator` class when `Course` can own it.

In this simplified example, `Course` can be viewed as an **aggregate root** for seat enrollment if every enrollment is managed through it. In a larger system, enrollment may be its own aggregate, with capacity protected by a reservation service or database. Boundaries should follow actual transactions, access volume, and invariants.

~~~mermaid
classDiagram
    direction LR
    class Student {
        +id: String
        +active: boolean
        +completedCourses: Set
    }
    class Course {
        +id: String
        +capacity: int
        +enroll(Student) EnrollmentReceipt
        +remainingSeats() int
        +closeRegistration()
    }
    class EnrollmentReceipt {
        +courseId: String
        +studentId: String
        +enrolledCount: int
    }
    Course ..> Student : kiểm tra điều kiện
    Course ..> EnrollmentReceipt : tạo kết quả
~~~

The diagram shows **behavioral dependencies**, not enough evidence to infer composition or aggregation. If enrollment has a separate lifecycle, introduce an `Enrollment` entity with identity and state; do not add one merely because the diagram contains several nouns.

## 8. Java 17+: A Sample Implementation Based on the Collected Rules

This is a **runnable, single-file example in `EnrollmentModelingDemo.java`**. It uses in-memory state to illustrate the domain and **does not** replace real database transactions or unique constraints.

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

record Student(String id, boolean active, Set<String> completedCourses) {
    Student {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(completedCourses, "completedCourses");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Student id is blank");
        }
        completedCourses = Set.copyOf(completedCourses);
    }
}

record EnrollmentReceipt(
        String courseId, String studentId, int enrolledCount) {}

final class BusinessRuleViolation extends RuntimeException {
    private final String ruleId;

    BusinessRuleViolation(String ruleId, String message) {
        super(message);
        this.ruleId = ruleId;
    }

    String ruleId() {
        return ruleId;
    }
}

final class Course {
    private final String id;
    private final int capacity;
    private final Set<String> prerequisites;
    private final Set<String> enrolledStudentIds = new LinkedHashSet<>();
    private boolean registrationOpen;

    Course(String id, int capacity, Set<String> prerequisites,
            boolean registrationOpen) {
        this.id = Objects.requireNonNull(id, "id");
        Objects.requireNonNull(prerequisites, "prerequisites");
        if (id.isBlank() || capacity <= 0) {
            throw new IllegalArgumentException("Invalid course");
        }
        this.capacity = capacity;
        this.prerequisites = Set.copyOf(prerequisites);
        this.registrationOpen = registrationOpen;
    }

    // Command: kiểm tra và thay đổi trong cùng vùng đồng bộ.
    synchronized EnrollmentReceipt enroll(Student student) {
        Objects.requireNonNull(student, "student");

        if (!student.active()) {
            throw new BusinessRuleViolation("BR-01", "Student is inactive");
        }
        if (!registrationOpen) {
            throw new BusinessRuleViolation("BR-02", "Registration is closed");
        }
        if (!student.completedCourses().containsAll(prerequisites)) {
            throw new BusinessRuleViolation("BR-03", "Prerequisites missing");
        }
        if (enrolledStudentIds.contains(student.id())) {
            throw new BusinessRuleViolation("BR-04", "Already enrolled");
        }
        if (enrolledStudentIds.size() >= capacity) {
            throw new BusinessRuleViolation("BR-05", "Course is full");
        }

        enrolledStudentIds.add(student.id()); // BR-06 trong 1 JVM
        return new EnrollmentReceipt(
                id, student.id(), enrolledStudentIds.size());
    }

    // Query: không thay đổi dữ liệu.
    synchronized int remainingSeats() {
        return capacity - enrolledStudentIds.size();
    }

    synchronized void closeRegistration() {
        registrationOpen = false;
    }
}

public class EnrollmentModelingDemo {
    public static void main(String[] args) {
        Course oop = new Course("OOP-201", 2, Set.of("JAVA-101"), true);
        Student lan = new Student("ST-01", true, Set.of("JAVA-101"));
        Student minh = new Student("ST-02", true, Set.of("JAVA-101"));

        EnrollmentReceipt result = oop.enroll(lan);
        System.out.println(result);
        System.out.println("Remaining: " + oop.remainingSeats()); // 1

        oop.enroll(minh);
        System.out.println("Remaining: " + oop.remainingSeats()); // 0

        try {
            oop.enroll(new Student(
                    "ST-03", true, Set.of("JAVA-101")));
        } catch (BusinessRuleViolation exception) {
            System.out.println(
                    exception.ruleId() + ": " + exception.getMessage());
            // BR-05: Course is full
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac EnrollmentModelingDemo.java
java EnrollmentModelingDemo
~~~

**Design implications:**

- `Student` is an immutable `record`; `Set.copyOf` prevents callers from changing completed-course data after construction.
- `Course.enroll()` enforces rules owned by the course instead of putting them in a controller and hoping every caller checks them.
- `BusinessRuleViolation.ruleId()` creates **traceability** among BR-xx requirements, code, and tests; internal stack traces should not be shown to end users.
- `synchronized` prevents interleaving between checks and additions when **multiple threads access the same `Course` instance in one JVM**.
- `EnrollmentReceipt` contains only data returned by the use case. A real system may add enrollment ID, status, timestamps, and version when requirements confirm them.

**Important boundary:** If an application runs on several nodes and each loads a separate `Course` from the DB, `synchronized` locks **do not** coordinate across nodes. Enforcing BR-04/BR-05/BR-06 in production requires correct transactions, a unique constraint on `(course_id, student_id)`, locking/optimistic versioning or conditional updates, and checking their results. A business rule is not guaranteed merely because Java contains an `if` statement.

## 9. Trace Requirements to Classes and Tests

A traceability matrix helps manage scope and reveal unverified rules:

| Requirement source | Where it appears in the model | Test case |
|---|---|---|
| UC-01 success flow | `Course.enroll()`, `EnrollmentReceipt` | Eligible student enrolls; available seats decrease by 1 |
| BR-01 | `Student.active()`, `Course.enroll()` | Inactive student is rejected |
| BR-02 | `Course.registrationOpen` | Closed registration is rejected |
| BR-03 | `Student.completedCourses`, `Course.prerequisites` | Missing prerequisite is rejected |
| BR-04 | `Course.enrolledStudentIds` | Second enrollment attempt is rejected |
| BR-05 | `Course.capacity` | Full course rejects enrollment |
| BR-06 | `Course.enroll()` and persistence transaction when using a DB | Failed operation adds no record; competing requests never exceed capacity |

One business criterion may require **multiple** tests, while one test may exercise several rules. Traceability is useful when policy changes: find affected code and tests without putting every rule into a giant class.

### Illustrative JUnit Jupiter 5 Tests

**`EnrollmentModelingTest.java`** (in the same package as the demo file):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Set;

class EnrollmentModelingTest {
    private static Student eligible(String id) {
        return new Student(id, true, Set.of("JAVA-101"));
    }

    @Test
    void successConsumesExactlyOneSeat() {
        Course course = new Course("OOP", 2, Set.of("JAVA-101"), true);

        EnrollmentReceipt receipt = course.enroll(eligible("S-01"));

        assertEquals("OOP", receipt.courseId());
        assertEquals("S-01", receipt.studentId());
        assertEquals(1, receipt.enrolledCount());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void duplicateDoesNotConsumeAnotherSeat() {
        Course course = new Course("OOP", 2, Set.of(), true);
        Student student = new Student("S-01", true, Set.of());
        course.enroll(student);

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class, () -> course.enroll(student));

        assertEquals("BR-04", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void missingPrerequisiteIsRejected() {
        Course course = new Course("OOP", 1, Set.of("JAVA-101"), true);

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-02", true, Set.of())));

        assertEquals("BR-03", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void capacityIsEnforced() {
        Course course = new Course("OOP", 1, Set.of(), true);
        course.enroll(new Student("S-01", true, Set.of()));

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-02", true, Set.of())));

        assertEquals("BR-05", exception.ruleId());
        assertEquals(0, course.remainingSeats());
    }

    @Test
    void closedRegistrationRejectsRequest() {
        Course course = new Course("OOP", 1, Set.of(), true);
        course.closeRegistration();

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-01", true, Set.of())));

        assertEquals("BR-02", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }
}
~~~

These tests check behavior against the chosen rules. They do not prove multi-node uniqueness or atomicity; a real system also needs DB integration tests and suitable concurrency tests.

## 10. Acceptance Criteria Using Given–When–Then

Detailed use cases provide context, while **Given–When–Then** turns individual scenarios into testable acceptance criteria.

~~~gherkin
Feature: Đăng ký khóa học

  Scenario: Đăng ký hợp lệ
    Given sinh viên ST-01 đang hoạt động
      And ST-01 đã hoàn thành JAVA-101
      And khóa OOP-201 đang mở với 1 chỗ trống
    When ST-01 đăng ký OOP-201
    Then hệ thống xác nhận đăng ký thành công
      And OOP-201 có 0 chỗ trống

  Scenario: Từ chối đăng ký trùng
    Given ST-01 đã ghi danh OOP-201
    When ST-01 đăng ký lại OOP-201
    Then hệ thống từ chối theo BR-04
      And số chỗ trống không thay đổi
~~~

The Gherkin is a **scenario specification**; automated execution requires an appropriate tool and step definitions (such as Cucumber). Merely placing it in a README does not execute it.

Not every UI detail is an acceptance criterion. “Green button is visible” might warrant a separate interface test; BR-04 must be enforced at the domain level even when a caller bypasses the web UI.

## 11. Business Flows, State, and Decision Points

~~~mermaid
flowchart TD
    A[Sinh viên yêu cầu ghi danh] --> B[Định danh người yêu cầu và khóa học]
    B --> C{Sinh viên active?}
    C -->|Không| X1[Từ chối BR-01]
    C -->|Có| D{Khóa đang mở?}
    D -->|Không| X2[Từ chối BR-02]
    D -->|Có| E{Đủ môn tiên quyết?}
    E -->|Không| X3[Từ chối BR-03]
    E -->|Có| F{Đã ghi danh?}
    F -->|Có| X4[Từ chối BR-04]
    F -->|Không| G{Còn capacity?}
    G -->|Không| X5[Từ chối BR-05]
    G -->|Có| H[Giữ chỗ và tạo ghi danh nguyên tử]
    H --> I[Trả biên nhận]
~~~

The diagram helps stakeholders identify undefined branches. Its error-check order is **only one illustrative choice**: a real system might check authorization first to avoid exposing course details or handle “already enrolled” differently. Error precedence is part of the contract that stakeholders must confirm.

If there is a longer lifecycle with states such as (`Requested → Approved → Cancelled`), draw a **state machine** and specify transition rules. But if the use case only decides success/failure and has no additional enduring states, do not invent numerous artificial states.

## 12. Business Rules Versus Functional and Nonfunctional Requirements

| Category | Example | Effect on the model |
|---|---|---|
| **Use case / functional requirement** | Student enrolls in a course | Requires orchestration and a returned outcome |
| **Business rule** | Do not exceed capacity or allow duplicates | Domain/transaction invariants and validation |
| **Non-functional requirement** | 99% of requests respond within a stakeholder-approved threshold | Influences database, caching, and load-distribution strategies |
| **Security rule** | Only account owners or authorized staff may enroll on someone else's behalf | Authorization at entry points and other suitable boundaries |
| **Data constraint** | Unique `(course_id, student_id)` | Protects consistency in storage |
| **UI behavior** | Show available seats and disable enrollment when full | Presentation; does not replace command validation |

Do not encode a vague business rule as hard constraints in several places and forget versioning. When the same rule is enforced by API, DB, and UI, specify the **authoritative definition** and a consistency strategy across those layers.

## 13. A Practical Requirements-to-Modeling Workflow

1. **Define goals and the system boundary.** List actors, related systems, and desired outcomes instead of starting with classes.
2. **Gather real stories.** Interview stakeholders, observe workflows, and use data-rich examples and counterexamples. Record who said what and which decisions remain unapproved.
3. **Name use cases using verbs and outcomes.** Examples: “Enroll in Course,” “Withdraw Enrollment,” “Approve Exception.” Give each a clear actor and goal.
4. **Specify main and exceptional flows.** Capture triggers, preconditions, postconditions, failure guarantees, and concurrent scenarios.
5. **Extract business rules separately.** Assign BR-xx IDs, use observable conditions, and specify owner, applicability, exceptions, and version.
6. **Confirm with concrete examples.** Use decision tables and Given–When–Then to confirm boundaries, null/blank cases, duplicates, and concurrency with stakeholders.
7. **Sketch the domain model.** Identify entities, value objects, aggregates, invariants, and responsibilities; introduce abstractions only where justified.
8. **Design APIs and use cases.** Commands should protect rules where data is managed; queries only read. Technical interfaces should not arbitrarily own domain policy.
9. **Create traceability.** Map use case → business rule → class/method → test, maintaining links as requirements change.
10. **Review with stakeholders and operations.** Assess feasibility, errors, auditing, transactions, integrations, and changes over time.

~~~mermaid
flowchart LR
    A[Stakeholder và tình huống thực] --> B[Use case]
    B --> C[Business rules và acceptance criteria]
    C --> D[Domain model và trách nhiệm]
    D --> E[Java API / transaction / persistence]
    E --> F[Test truy vết]
    F -. phát hiện thiếu hoặc mâu thuẫn .-> B
~~~

Modeling is **a controlled iterative process**, not a one-time document. If tests reveal an unclear domain case, return to the rule owner for confirmation rather than adding an `if` based solely on technical judgment.

## 14. Requirements-Gathering Risks and Mitigations

| Mistake | Consequence | Prevention |
|---|---|---|
| Recording only UI requirements | Missing domain rules that alternate APIs can bypass | Capture goal-level use cases |
| Asking one stakeholder to define every rule | Missed exceptions and decision rights | Identify owners, approvers, and affected parties |
| Using words like “valid,” “enough,” or “fast” | Untestable rules | Specify conditions, thresholds, and concrete examples |
| Confusing policy with implementation | Business documents must change when DB/framework changes | Separate business rules from SQL, HTTP, and classes |
| Describing only the happy path | Data failures, concurrency, and retries are undefined | Create decision tables and failure flows |
| Turning every noun into a class | More classes without clear responsibilities; increased coupling | Identify identity, state, and invariants first |
| Validating only in controllers | Jobs/background callers bypass rules | Enforce invariants at suitable domain/storage boundaries |
| Not linking rules to tests | Policy changes with unknown impact | Trace BR-ID to behavioral tests |
| Treating in-memory locking as distributed protection | Capacity can be exceeded across servers | Use suitable database transactions, constraints, and locking |
| Not recording assumptions or scope | Developers silently make stakeholder policy decisions | Maintain open questions, decisions, and versions |

## 15. Practice Exercise

**Another context:** a library lending books to members.

Gather and model the **“Borrow a Book Copy”** use case starting with “Members may borrow available books.” Before coding, propose questions about active accounts, maximum concurrent loans, due dates, specific book copies, reservations, overdue loans, request retries, and multiple members competing for the last copy.

Once the answers are known:

1. Write use case UC-LIB-01 with actor, trigger, success flow, failure branches, and postconditions.
2. Build a BR-LIB-01... table with valid/invalid examples for each confirmed rule.
3. Determine the identities and lifecycles of `BookTitle`, `BookCopy`, `Member`, and `Loan`, including where to protect the last available copy.
4. Draw concise use-case-flow and class diagrams; do not create classes solely from nouns.
5. Write Java APIs for command `borrowCopy(...)` and query `availableCopies(...)`, and check storage-level race conditions.
6. Convert at least three business rules into acceptance tests and map their IDs.

**Completion criteria:** Stakeholders can review scenarios and confirm behavior; developers can identify each class's responsibility; testers can trace every rule to a test case; failure paths cannot leave data violating policy.

---

**Remember:** Good OOP modeling begins with **the outcome users want** and **the conditions under which the organization permits it**. Use cases define goal-oriented flows, business rules define policies/invariants, and Java classes and tests implement, protect, and verify both.
