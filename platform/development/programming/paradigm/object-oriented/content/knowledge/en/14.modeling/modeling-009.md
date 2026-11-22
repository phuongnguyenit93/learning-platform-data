# Validating OOP Models Against Java Code and Real Scenarios

> **Goal:** Learn to verify that an object-oriented model accurately represents business situations, is implemented correctly in Java, and remains correct during system operation. This lesson uses **borrowing and returning physical library book copies** to practice two-way traceability among requirements, diagrams, source code, tests, and real data.

## 1. Three Perspectives That Must Agree

An elegant model is not necessarily correct. A diagram may say “one active loan per copy,” while code still lets two people borrow the same copy. Conversely, code may pass one sample dataset yet omit late-return, return, or borrowing-limit policies.

Validation needs **three sources of evidence**:

1. **Real scenarios and business rules:** Who performs which action? Which conditions must hold? What happens for invalid requests, repeated operations, or simultaneous users?
2. **Design model:** Which concepts have identity and state? Do relationships accurately represent multiplicity, lifecycle, ownership, and responsibilities? Where are invariants enforced?
3. **Code and runtime behavior:** Do types, APIs, access levels, state changes, transactions, and tests enforce the model's promises?

~~~mermaid
flowchart TD
    R[Use case, ví dụ thực tế, business rule] <-->|kiểm chứng ý nghĩa| M[Mô hình lớp, quan hệ, invariant]
    M <-->|đối chiếu cấu trúc và trách nhiệm| C[Java API và implementation]
    C <-->|kiểm thử hành vi| T[Test và dữ liệu chạy thật]
    T -. lỗi hoặc trường hợp chưa rõ .-> R
~~~

**Validation is not just one-way from UML to code.** When reviewing existing software, work backward from code and tests to the model, then ask the domain owner whether observed behavior is intended. When they differ, **do not assume** the diagram or code is automatically right: find the domain decision and update the relevant artifacts.

## 2. Start with Observable Scenarios

Suppose the library's original requirement is:

> “Active members can borrow available book copies. Returning a copy makes it available for borrowing again.”

This raises important edge-case questions:

| Question | Assumption used in this lesson |
|---|---|
| Are loans for a title or a physical copy? | Borrow **one BookCopy** with its own unique copy ID |
| What if the account is suspended? | Borrowing is disallowed |
| How many active loans per member? | At most **3 copies** per member |
| How many people can borrow one copy? | At most **1 active loan at a time** |
| Loan duration? | **14 days** measured by calendar date |
| Returning an already returned loan? | Report an error; do not record another return |
| Does returning erase loan history? | No; retain the return date for traceability |
| Two members competing for the final available copy? | At most one request succeeds |
| Renewals, reservations, or fines? | Outside this example's scope |

These are **illustrative assumptions**, not universal library rules. Real projects must record policy approvers, effective dates, exceptions, and unresolved questions.

### Convert Them into Use Cases

**UC-BORROW: Borrow a Book Copy**

- **Primary actor:** Member (through a librarian or application).
- **Trigger:** Member requests a copy identified by `copyId`.
- **Preconditions:** The system can identify both member and copy.
- **Success flow:** Verify account → check active-loan limit → check copy availability → create loan → mark copy borrowed → return loan ID and due date.
- **Alternative flows:** Suspended account; missing copy; member already has 3 active loans; copy already has an active loan; persistence failure.
- **Success postcondition:** Exactly one new active loan exists, and the copy cannot be borrowed a second time concurrently.
- **Failure guarantee:** No partial loan record and no limit violation.

**UC-RETURN: Return a Book Copy**

- **Trigger:** Librarian receives the copy and loan identifier.
- **Success flow:** Find active loan → record return date → make copy available again.
- **Alternative flows:** Loan not found or already returned → report an error without deleting history.
- **Postcondition:** The previous loan remains stored with `returnedOn` and no longer counts as active.

A good use case describes **outcomes and failures**, not green-button clicks or framework specifics.

## 3. Turn Decisions into Identified Rules

| ID | Business rule | Relevant data | Example to verify |
|---|---|---|---|
| **BR-01** | Only `Member.active == true` may borrow | Member | Suspended member is rejected |
| **BR-02** | Each Member may have at most 3 active Loans | Member, Loan | Fourth copy is rejected |
| **BR-03** | A BookCopy may have at most 1 active Loan at any time | BookCopy, Loan | Two members competing for the last copy |
| **BR-04** | Due date = borrowing date + 14 days | Loan, business date | Borrowed 15/10 → due 29/10 |
| **BR-05** | Only an unreturned loan may be returned | Loan | Second return is rejected |
| **BR-06** | Returns do not erase Loan history | Loan | Previous loan remains queryable |
| **BR-07** | Failed borrowing must not create partial records | Loan, persistence | No half-completed loan |
 
Missing inputs, blank IDs, malformed data, and connection failures also require explicit contracts; depending on scope they may be technical validation requirements or separate business rules.

**Do not treat the rule list as the sole coding instruction.** BR-03 still needs a decision: does “active loan” mean `returnedOn == null`, or is overdue a distinct state? In this example, an overdue but **unreturned** loan still occupies the copy.

## 4. Build the Conceptual Model: Titles, Copies, and Loans

These three concepts must not be merged indiscriminately:

- **BookTitle:** Describes a work/title or edition; several physical copies may share one title.
- **BookCopy:** One physical copy with its own `copyId`; this is the resource occupied during borrowing.
- **Loan:** One member's specific borrowing event for one copy, including borrowed date, due date, and returned date.

Conceptual diagram:

~~~mermaid
classDiagram
    direction LR
    class Member {
        +String id
        +boolean active
    }
    class BookCopy {
        +String id
        +String title
    }
    class Loan {
        +String id
        +String memberId
        +String copyId
        +LocalDate borrowedOn
        +LocalDate dueOn
        +LocalDate returnedOn
        +isActive() boolean
        +returnOn(LocalDate) Loan
    }
    class Library {
        -Map members
        -Map copies
        -Map loans
        +borrow(memberId, copyId) Loan
        +returnLoan(loanId) void
        +isAvailable(copyId) boolean
    }
    Member "1" -- "0..*" Loan : lịch sử mượn
    BookCopy "1" -- "0..*" Loan : lịch sử bản sách
    Library --> Member : quản lý dữ liệu
    Library --> BookCopy : quản lý dữ liệu
    Library --> Loan : quản lý dữ liệu
~~~

**Multiplicity matters:** A `BookCopy` may have **many historical Loans**, but **at most one active Loan**. A historical `0..*` multiplicity **does not by itself represent** the active-loan constraint; document it separately and enforce it in code plus storage. This is a clear example of **checking the model against real scenarios**: one association line is insufficient.

Do not automatically model composition between `Member` and `Loan`: deletion of member accounts may need to preserve historical loans under retention policies. Decide ownership and lifecycle from requirements rather than from the existence of reference fields.

### Mapping the Model to Java

| Model component | Sample implementation | What to verify |
|---|---|---|
| Member has identity and active status | `record Member(String id, boolean active)` | Nonblank ID; does active reflect the domain meaning? |
| Physical copy has identity | `record BookCopy(String id, String title)` | Title is not used as a unique identifier |
| Loan has state | `record Loan(..., returnedOn)` | Active means `returnedOn == null` |
| Maximum 3 active loans | `Library.borrow()` counts active loans | Do not count all historical loans |
| Copy is currently borrowed | `Library.borrow()` checks active loan for the same copy | Atomic under contention |
| Return operation | `Library.returnLoan()` replaces Loan with a version containing return date | Preserve the historical record |
| Due date | `LocalDate.now(clock).plusDays(14)` | Clock/time zone, holiday policy |

## 5. Java 17: A Small Runnable, Verifiable Model

The example uses **one JVM and in-memory state** to focus on whether the model enforces its rules. Public APIs are simplified; production needs appropriate repositories, transactions, authentication, and logging.

Create **`LibraryModelDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record Member(String id, boolean active) {
    Member {
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Member id is blank");
        }
    }
}

record BookCopy(String id, String title) {
    BookCopy {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(title, "title");
        if (id.isBlank() || title.isBlank()) {
            throw new IllegalArgumentException("Invalid book copy");
        }
    }
}

record Loan(
        String id,
        String memberId,
        String copyId,
        LocalDate borrowedOn,
        LocalDate dueOn,
        LocalDate returnedOn) {

    Loan {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(memberId, "memberId");
        Objects.requireNonNull(copyId, "copyId");
        Objects.requireNonNull(borrowedOn, "borrowedOn");
        Objects.requireNonNull(dueOn, "dueOn");
        if (id.isBlank() || memberId.isBlank() || copyId.isBlank()) {
            throw new IllegalArgumentException("Invalid loan id/reference");
        }
        if (dueOn.isBefore(borrowedOn)) {
            throw new IllegalArgumentException("Due date before borrow date");
        }
        if (returnedOn != null && returnedOn.isBefore(borrowedOn)) {
            throw new IllegalArgumentException("Return date before borrow date");
        }
    }

    boolean isActive() {
        return returnedOn == null;
    }

    Loan returnOn(LocalDate day) {
        Objects.requireNonNull(day, "day");
        if (!isActive()) {
            throw new IllegalStateException("Loan already returned");
        }
        return new Loan(
                id, memberId, copyId, borrowedOn, dueOn, day);
    }
}

final class Library {
    private static final int MAX_ACTIVE_LOANS = 3;

    private final Clock clock;
    private final Map<String, Member> members = new HashMap<>();
    private final Map<String, BookCopy> copies = new HashMap<>();
    private final Map<String, Loan> loans = new HashMap<>();
    private long nextLoanNumber = 1;

    Library(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    synchronized void addMember(Member member) {
        Objects.requireNonNull(member, "member");
        if (members.putIfAbsent(member.id(), member) != null) {
            throw new IllegalArgumentException("Duplicate member");
        }
    }

    synchronized void addCopy(BookCopy copy) {
        Objects.requireNonNull(copy, "copy");
        if (copies.putIfAbsent(copy.id(), copy) != null) {
            throw new IllegalArgumentException("Duplicate copy");
        }
    }

    // Query: số phiếu chưa trả của một member.
    synchronized long activeLoanCount(String memberId) {
        return loans.values().stream()
                .filter(loan -> loan.memberId().equals(memberId))
                .filter(Loan::isActive)
                .count();
    }

    // Query: chỉ đọc, không giữ sách.
    synchronized boolean isAvailable(String copyId) {
        if (!copies.containsKey(copyId)) {
            throw new IllegalArgumentException("Unknown book copy");
        }
        return loans.values().stream()
                .filter(Loan::isActive)
                .noneMatch(loan -> loan.copyId().equals(copyId));
    }

    // Command: kiểm tra và tạo phiếu trong cùng một lock.
    synchronized Loan borrow(String memberId, String copyId) {
        Member member = members.get(memberId);
        if (member == null) {
            throw new IllegalArgumentException("Unknown member");
        }
        if (!member.active()) {
            throw new IllegalStateException("Inactive member"); // BR-01
        }
        if (activeLoanCount(memberId) >= MAX_ACTIVE_LOANS) {
            throw new IllegalStateException("Loan limit"); // BR-02
        }
        if (!isAvailable(copyId)) {
            throw new IllegalStateException("Copy is already loaned"); // BR-03
        }

        LocalDate today = LocalDate.now(clock);
        Loan loan = new Loan(
                "L-" + nextLoanNumber++,
                memberId,
                copyId,
                today,
                today.plusDays(14), // BR-04
                null);
        loans.put(loan.id(), loan); // Chỉ ghi sau khi tất cả rule đạt.
        return loan;
    }

    synchronized void returnLoan(String loanId) {
        Loan old = loans.get(loanId);
        if (old == null) {
            throw new IllegalArgumentException("Unknown loan");
        }
        // returnOn từ chối Loan đã trả (BR-05).
        // Thay giá trị trong map, không xóa lịch sử (BR-06).
        loans.put(loanId, old.returnOn(LocalDate.now(clock)));
    }

    synchronized Optional<Loan> findLoan(String loanId) {
        return Optional.ofNullable(loans.get(loanId));
    }
}

public class LibraryModelDemo {
    public static void main(String[] args) {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-10-15T09:00:00Z"),
                ZoneOffset.UTC);
        Library library = new Library(fixedClock);

        library.addMember(new Member("M-01", true));
        library.addMember(new Member("M-02", true));
        library.addCopy(new BookCopy("C-001", "Java Fundamentals"));

        Loan loan = library.borrow("M-01", "C-001");

        System.out.println(loan.dueOn());                // 2026-10-29
        System.out.println(library.isAvailable("C-001")); // false

        try {
            library.borrow("M-02", "C-001");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage()); // Copy is already loaned
        }

        library.returnLoan(loan.id());
        System.out.println(library.isAvailable("C-001")); // true
        System.out.println(library.findLoan(loan.id())
                .orElseThrow().isActive());              // false
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac LibraryModelDemo.java
java LibraryModelDemo
~~~

Expected output:

~~~text
2026-10-29
false
Copy is already loaned
true
false
~~~

### Why Do These Java Choices Reflect the Model?

- `Member` and `BookCopy` have independent identities: a **physical copy** ID is different from a book title. Using only `title` as the key would fail to model multiple copies of the same title.
- `Loan` retains `borrowedOn`, `dueOn`, and `returnedOn` to distinguish active loans and preserve history.
- `Loan.returnOn()` returns a **new value** instead of mutating a record. Java records are shallowly immutable when their components are immutable; here the components are `String` and `LocalDate`.
- `Library.borrow()` checks BR-01, BR-02, and BR-03 before recording data rather than relying only on controller checks. The `isAvailable()` query does not mutate state.
- An injected `Clock` makes date tests independent of system time. For libraries spanning regions, specify the appropriate time zone and due-date policy before using `LocalDate.now(clock)`.
- `synchronized` keeps operations on **the same Library instance in one JVM** from interleaving between validation and updates. It does not coordinate separate processes or servers.
- Inside `borrow`, Java permits synchronized calls to `activeLoanCount` and `isAvailable` while holding the same monitor because `synchronized` uses a *reentrant* lock.

This is **one illustrative implementation**, not proof that the model requires one `Library` class containing three maps. Real persistence can move maps and ID generation into appropriate collaborators while keeping invariants protected at the transaction boundary.

## 6. Reverse Validation: Does the Code Still Match the Model?

During reviews or maintenance, work backward from code entities to requirements:

~~~mermaid
flowchart TD
    A[Đọc API public của class] --> B[Kiểm tra trạng thái được giữ và quyền thay đổi]
    B --> C[Đối chiếu quan hệ, multiplicity, ownership]
    C --> D[Truy vết từng BR vào lệnh thực thi]
    D --> E[Chạy test với ví dụ thực tế và phản ví dụ]
    E --> F{Có sai lệch?}
    F -->|Có| G[Hỏi lại business owner và sửa model/code/test]
    F -->|Không| H[Ghi nhận bằng chứng và phiên bản]
    G --> D
~~~

Common **mismatches** include:

| Model / requirement says | Code does | Why it diverges | Possible correction |
|---|---|---|---|
| Only 1 active loan per copy | `borrow()` checks only `copy != null` | Fails to check active loans | Validate at write time and use DB constraints/locks as needed |
| At most 3 copies per member | Counts every historical `Loan` | Someone who returned 3 copies is blocked forever | Count only `returnedOn == null` |
| Returns preserve history | Calls `loans.remove(loanId)` | Erases domain history | Update return date/state instead |
| Due date after 14 days | Calls `LocalDate.now()` in many places | Nonrepeatable tests, ambiguous time zone | Define one clock/date-policy boundary |
| Loan state cannot be changed arbitrarily | Exposes `public setReturnedOn` without validation | Could record a return before the borrow date | Validate invariants with `returnOn` command |
| Each physical copy has a unique code | Uses ISBN as the `BookCopy` key | Cannot distinguish copies sharing an ISBN | Add independent copy IDs |
| At most 1 active loan per copy across nodes | Uses per-node `synchronized` | Locks do not cross process boundaries | Database transaction plus constraint/locking |
| Availability query does not reserve copies | Getter secretly invokes `borrow` | Display operations mutate data | Distinguish queries from commands |

**Review principle:** Do not change code merely to make UML resemble Java. If the product has adopted an approved new policy, the old model may be outdated. Record decisions and update diagrams, rules, and tests together.

## 7. Tests Traceable to Individual Rules

A useful test answers “what does BR-xx require?” rather than simply asserting a class has a `loans` field.

**File `LibraryModelTest.java`**, in the same package as `LibraryModelDemo.java`, using **JUnit Jupiter 5**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class LibraryModelTest {
    private static Library freshLibrary() {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-10-15T09:00:00Z"),
                ZoneOffset.UTC);
        Library library = new Library(fixed);
        library.addMember(new Member("M-01", true));
        library.addMember(new Member("M-02", true));
        library.addCopy(new BookCopy("C-01", "Java"));
        return library;
    }

    @Test
    void borrowCreatesActiveLoanWithCorrectDueDate() {
        Library library = freshLibrary();

        Loan loan = library.borrow("M-01", "C-01");

        assertTrue(loan.isActive());
        assertEquals("2026-10-29", loan.dueOn().toString()); // BR-04
        assertEquals(1, library.activeLoanCount("M-01"));
        assertFalse(library.isAvailable("C-01"));           // BR-03
    }

    @Test
    void sameCopyCannotBeBorrowedTwice() {
        Library library = freshLibrary();
        library.borrow("M-01", "C-01");

        assertThrows(IllegalStateException.class,
                () -> library.borrow("M-02", "C-01"));

        assertEquals(1, library.activeLoanCount("M-01"));
        assertEquals(0, library.activeLoanCount("M-02"));
    }

    @Test
    void returningKeepsHistoryAndMakesCopyAvailable() {
        Library library = freshLibrary();
        Loan loan = library.borrow("M-01", "C-01");

        library.returnLoan(loan.id());

        Loan history = library.findLoan(loan.id()).orElseThrow();
        assertFalse(history.isActive());                     // BR-06
        assertNotNull(history.returnedOn());
        assertTrue(library.isAvailable("C-01"));
        assertThrows(IllegalStateException.class,
                () -> library.returnLoan(loan.id()));        // BR-05
    }

    @Test
    void inactiveMemberCannotBorrow() {
        Library library = freshLibrary();
        library.addMember(new Member("M-03", false));

        assertThrows(IllegalStateException.class,
                () -> library.borrow("M-03", "C-01"));

        assertTrue(library.isAvailable("C-01"));             // BR-01
    }

    @Test
    void fourthActiveLoanIsRejected() {
        Library library = freshLibrary();
        library.addCopy(new BookCopy("C-02", "OOP"));
        library.addCopy(new BookCopy("C-03", "Patterns"));
        library.addCopy(new BookCopy("C-04", "Testing"));

        library.borrow("M-01", "C-01");
        library.borrow("M-01", "C-02");
        library.borrow("M-01", "C-03");

        assertThrows(IllegalStateException.class,
                () -> library.borrow("M-01", "C-04"));       // BR-02
        assertEquals(3, library.activeLoanCount("M-01"));
        assertTrue(library.isAvailable("C-04"));
    }
}
~~~

This test suite can run when the project configures JUnit Jupiter 5 (for example, through Maven/Gradle); plain `javac` compiles `LibraryModelDemo.java` but does not supply JUnit libraries automatically.

**Remaining gap:** These tests verify sequential in-memory behavior, not correctness with a database or multiple nodes. Integration tests must verify transaction boundaries, unique constraints, rollback, and real contention at the persistence layer.

## 8. Concurrency Check: Does the UML Promise Hold?

The diagram permits multiple **historical** Loans for one BookCopy but at most one **active** Loan. If two members request the same copy almost simultaneously:

~~~mermaid
sequenceDiagram
    participant A as Độc giả A
    participant B as Độc giả B
    participant L as Library
    A->>L: borrow(M-01, C-01)
    B->>L: borrow(M-02, C-01)
    Note over L: Lock cùng instance trong Java
    L-->>A: Loan L-1 (thành công)
    L-->>B: Từ chối, copy đã được mượn
~~~

A-before-B is merely **one illustrative interleaving**. If B gets the lock first, B may succeed. The invariant is **never two simultaneous active loans** on the same copy, not “A must always win.”

### Contention Test Within One JVM

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class LibraryConcurrencyTest {
    @Test
    void onlyOneBorrowSucceedsForSameCopy() throws Exception {
        Library library = new Library(Clock.systemUTC());
        library.addMember(new Member("A", true));
        library.addMember(new Member("B", true));
        library.addCopy(new BookCopy("C", "Java"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Boolean> first = () -> attempt(library, "A", start);
        Callable<Boolean> second = () -> attempt(library, "B", start);

        try {
            Future<Boolean> a = pool.submit(first);
            Future<Boolean> b = pool.submit(second);
            start.countDown();

            int success = (a.get() ? 1 : 0) + (b.get() ? 1 : 0);
            assertEquals(1, success);
            assertFalse(library.isAvailable("C"));
        } finally {
            pool.shutdownNow();
        }
    }

    private static boolean attempt(
            Library library, String memberId, CountDownLatch start)
            throws InterruptedException {
        start.await();
        try {
            library.borrow(memberId, "C");
            return true;
        } catch (IllegalStateException expected) {
            return false;
        }
    }
}
~~~

**Why is this test useful?** It directly exercises a scenario that could violate the model: two threads competing for one copy. Still, it **does not validate multi-node behavior**, and a contention test cannot explore every possible schedule. Concurrency correctness requires enforced transaction boundaries and appropriate integration verification.

### Using a Database

To preserve BR-03 in a distributed system, two transactions must not create active Loans for one BookCopy. With **PostgreSQL**, if `returned_on` is stored as `NULL` until return, one option is:

~~~sql
CREATE UNIQUE INDEX uq_active_loan_copy
ON loan(copy_id)
WHERE returned_on IS NULL;
~~~

This index ensures at most one active row per `copy_id` at the database level, even with concurrent writes from separate nodes. But the **BR-02 limit of 3 active loans per Member** is not enforced by the copy index: use a transaction with suitable member locking, an atomic reservation counter, or another verified concurrency design.

Production typically needs transactions, translation of unique-constraint violations into clear business errors, and retry/idempotency policies for clients resubmitting borrowing requests after network loss. Database constraints support domain invariants rather than making domain models unnecessary: one expresses the policy, the other protects consistency at the persistence boundary.

## 9. Compare Static Structure with Dynamic Execution

Class diagrams show **who relates to whom**. Runtime flows show **which actions occur and in what order**. Both matter when validating multi-step use cases.

| Question | Evidence to inspect |
|---|---|
| Does each Loan belong to exactly one member and copy? | Class diagram, data types, foreign keys |
| Must return preserve history? | Business rule, `returnLoan()`, history tests |
| How is an active Loan defined? | State definition, queries, tests |
| Could two active Loans refer to one copy? | Concurrency/transaction/unique constraint |
| Is borrowing rejected for an inactive account? | Use case, command validation, test |
| Which time zone applies to the 14-day due date? | Business rule, Clock, date tests |
| Does a failed DB write leave partial data? | Transaction boundary, integration tests |
| Has code diverged from the diagram? | Code review, diff, current diagram version |

A model **need not contain** every implementation detail, but domain-impacting decisions must align. For example, `HashMap` in the demo is an implementation choice; “at most one active Loan per copy” is the contract worth preserving in the model.

## 10. Detecting Gaps from Real Operational Scenarios

Suppose users report these production incidents:

- “A member changed library cards and the system treated them as a new member, allowing borrowing beyond the limit.”
- “A returned copy is still reported as on loan.”
- “A staff member entered the wrong return date, making history show a return before borrowing.”
- “A library has three branches, and two terminals still lend the same last available copy.”

Do not start with a random `if`. First determine **which part of the model is missing or wrong**:

| Incident | Modeling question | Possible improvement |
|---|---|---|
| Card replacement creates a “new member” | Does Member identity represent a person or a library card? | Stable Member ID and separate LibraryCard entity/value |
| Returned copy still appears borrowed | Is return a Loan state or temporary BookCopy attribute? | Define source of truth and synchronize indexes |
| Incorrect return date | Who validates dates? Are audited corrections permitted? | Authorized correction command and change history |
| Same copy borrowed at two branches | Where is the real transaction boundary? | DB constraint/lock and distributed workflow |
| Old loan record deleted | What retention/audit policy applies? | Loan lifecycle and retention rules |

**Do not confuse a display issue with a domain error.** An outdated “available copies” count might come from a query cache even when loan data is correct. Check the source of truth and observation timing before changing the model.

## 11. How Can You Tell a Class Diagram Matches Java?

A concise review cycle, repeatable during code review:

1. **Verify identity:** Does every entity have a meaningful ID? `BookTitle` differs from `BookCopy`; using a title/ISBN instead of a copy ID fails for multiple physical copies.
2. **Verify attributes:** Are `borrowedOn`, `dueOn`, `returnedOn`, and `active` correctly typed and modeled? Is `null` allowed intentionally or by accident?
3. **Verify APIs:** Are methods owned by the right objects? `borrow` is a command and `isAvailable` is a query; can any setter bypass an invariant?
4. **Verify relationships:** One Loan refers to one Member/copy; each Member/copy may have many historical Loans. Do multiplicities distinguish active versus historical?
5. **Verify lifecycle:** How do entity deletion or changes affect loans? Avoid arbitrary cascade deletion when history must be retained.
6. **Verify error contracts:** Missing copy, suspended member, quota reached, unavailable copy, returned loan, DB failure—each needs a defined outcome.
7. **Verify concurrency:** Are pre-command checks preserved atomically through commit?
8. **Verify tests:** Does each rule have at least one behavioral test that fails if code violates it? Are integration/contract tests needed?
9. **Verify implementation documentation:** Moving from maps to a DB might leave a domain diagram valid while requiring updated component/persistence diagrams.
10. **Verify stakeholder decisions:** Has an approved policy change invalidated an older diagram or test?

For each discrepancy, record **expected behavior → observed behavior → evidence → resolution decision → confirming test**. This replaces subjective debate about attractive diagrams or “standard” class names.

## 12. Requirements-to-Test Traceability Matrix

| ID | Scenario | Model / owner | Java API / mechanism | Test evidence |
|---|---|---|---|---|
| UC-BORROW | Member borrows an available copy | Member, BookCopy, Loan | `Library.borrow` | `borrowCreatesActiveLoanWithCorrectDueDate` |
| BR-01 | Account suspended | Member | Check `active` in the command | `inactiveMemberCannotBorrow` |
| BR-02 | Already has 3 active copies | Loans for Member | `activeLoanCount` plus limit validation | `fourthActiveLoanIsRejected` |
| BR-03 | One copy has no two active loans | BookCopy – Loan | `isAvailable` plus lock/DB constraint | `sameCopyCannotBeBorrowedTwice`; concurrency test |
| BR-04 | Due date after 14 days | Loan | `Clock` and `plusDays(14)` | Specific date-based test |
| BR-05 | Cannot return an already returned loan | Loan | `Loan.returnOn` | `returningKeepsHistoryAndMakesCopyAvailable` |
| BR-06 | Retain loan history | Loan | Update `returnedOn`, do not remove | Query loan after returning |
| BR-07 | Do not persist partial updates | Loan persistence | One in-memory lock; production requires transaction | Rollback/atomicity integration test |

One rule may have several enforcement layers: **domain validation** expresses policy and meaningful errors, while **database constraints** prevent violations from concurrent writers. Protecting the same invariant in both places is not necessarily wasteful duplication.

**Read the matrix backward:** A side-effecting public method without a traceable use case or policy deserves review for unintended behavior. A business rule lacking a proving API or test exposes a verification gap.

## 13. Validate Changes After Production Deployment

Models are **living documentation**. Suppose the library decides that next term teachers may borrow 6 copies instead of 3:

1. Record the new policy: who qualifies, effective dates, and treatment of existing loans.
2. Revise BR-02 into a **role- or policy-based rule**; do not replace 3 with 6 for every Member.
3. Decide where policy belongs: `BorrowingPolicy` may be suitable for multiple roles, effective dates, and exceptions; a domain constant may suffice while the rule remains simple.
4. Update the model, Java APIs, and tests; check compatibility for callers.
5. Revisit schema/configuration if role information or versioning is needed.
6. Deploy and observe whether older data now violates any constraints.

The change could be represented by a policy:

~~~java
interface BorrowingPolicy {
    int maxActiveLoans(Member member);
}
~~~

This is **a proposed extension**, not existing functionality in the demo. Creating an interface just to hide a constant that never varies may introduce needless complexity. Extract responsibilities when they have a clear reason to change.

## 14. Common Pitfalls

| Mistake | Why it is harmful | Corrective action |
|---|---|---|
| “The diagram has an association, so all rules are guaranteed” | Associations do not cap active loans | Document and enforce constraints during writes |
| “The demo runs, so the model is proven” | Happy paths omit failures and contention | Test counterexamples and boundaries |
| “Every UML class needs a same-named source file” | Conceptual models can differ from implementation structure | Choose an abstraction level and document mappings |
| “A `final` field makes its object immutable” | A final reference can still point to a mutable collection | Encapsulation, snapshots, constructor validation |
| “`synchronized` resolves all concurrency” | A lock applies only to one object/JVM | Enforce transactions at the shared persistence layer |
| “Historical loans belong to Member, so delete them with Member” | Auditing/retention may require another lifecycle | Derive lifecycles from domain policy |
| “Only update code, not documentation/tests” | Model drift and recurring regressions | Maintain traceability during changes |
| “Update diagrams only to resemble code” | May legitimize an existing bug | Validate against approved requirements |
| “Ignore production data that differs from the model” | Bugs may already exist in stored records | Investigate migrations, backfills, and integrity |

## 15. Exercise: Validate a Real Order Model

A team has diagrams `Customer "1" -- "0..*" Order` and `Order "1" *-- "1..*" OrderLine`. But the running application behaves as follows:

- The API creates an `Order` with no `OrderLine` in `DRAFT` state.
- `confirm()` rejects orders with no lines.
- `OrderLine` stores `productId` and the unit price captured at purchase time.
- A single Product may be referenced by many OrderLines.

Complete these tasks:

1. Check whether multiplicity `1..*` for `OrderLine` contradicts draft orders. Propose `0..*` with a **confirmed order must contain >=1 line** constraint.
2. Distinguish independent Products from order-owned OrderLines. Choose association or composition and justify it using lifecycles.
3. List at least four use cases or counterexamples: adding a line, confirming an empty order, modifying a confirmed order, and changing catalog prices after checkout.
4. Write a test ensuring an order's captured `total` does not change unexpectedly when current catalog prices change.
5. For concurrent confirmations, propose protection for state transitions and database consistency.
6. Build a traceability matrix of rule IDs, enforcement points, tests, and execution evidence.

**Success criteria:** Readers can distinguish **state-dependent intentional model differences** from actual bugs and describe a concrete verification method for every decision.

---

**Remember:** Comparing a model with code and real situations is a **two-way** verification cycle: use cases/rules challenge the design and implementation; tests and operational data reveal missing assumptions; then update the affected artifacts. A model's value lies in **verifiable behavior and invariants**, not in diagram box and arrow counts.
