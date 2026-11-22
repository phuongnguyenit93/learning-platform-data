# Capstone project: Changing requirements and evaluating library-system design (Java OOP)

> **Continuing scenario:** In the previous three stages, you analyzed lending/return use cases, designed `Book` (title), `BookCopy` (physical copy), `Member`, and `Loan`, then implemented and tested the system. Currently only active members may borrow, with a limit of **3 open loans**, a **14-day** term, and no new borrowing while overdue loans remain open. This exercise introduces **changing requirements in the same system**, rather than switching business domains.

## 1. Change requests from library management

Assume management confirms two new requirements effective from a specified deployment date:

- **CR-01:** Raise the limit from **3 to 5 open loans** for each active member. Members with overdue unreturned loans are still blocked from new borrowing.
- **CR-02:** Categorize titles as **normal (NORMAL)** or **reference (REFERENCE)**. Copies of reference titles may be borrowed for only **7 days**; normal titles retain **14 days**.
- **CR-03 — Historical accuracy:** Due dates for **Loans created before the policy change must remain unchanged**. The new policy affects only new Loans; it must not recalculate `dueOn` on every lookup.
- **CR-04 — Data and reliability:** One copy cannot have two open Loans; duplicate returns must still be rejected. The new policy preserves active-member, overdue-loan, and valid-return-date rules.

These decisions are assumptions for the exercise. Real projects must confirm: "May reference materials leave the library?" "Are new policies retroactive?" "What is the effective date?" "Which category applies to legacy titles with no category?" Do not answer unapproved business questions in code.

### Impact on existing requirements

| ID | Before | After change | Affected areas |
|---|---|---|---|
| BR-02 / CR-01 | At most 3 open Loans | At most 5 open Loans | Policy, tests at 5 and above 5 |
| BR-05 / CR-02 | All copies: 14 days | NORMAL: 14; REFERENCE: 7 | Book category, policy, due-date tests |
| BR-05 / CR-03 | `dueOn` stored in Loan | Still stored, **not retroactive** | Loan, historical data |
| BR-01,03,04,06,07,08 | Active, available, overdue, one-time returns, and valid dates | **Unchanged** | Regression tests |
| NFR-01/02 | Requires consistent multi-object updates | Must not be weakened | Transactions/locking with DB |

## 2. Analyze responsibilities before editing

The **natural change point** is `BorrowingPolicy`: previously `terms()` needed no book-copy details because all loans had equal durations. Now policies must account for **book category**. Intentionally update the contract to `termsFor(Member, BookCopy)` and pass only the **minimum information** the policy needs.

~~~mermaid
classDiagram
    class Book {
        +isbn() String
        +title() String
        +kind() BookKind
    }
    class BookKind {
        <<enumeration>>
        NORMAL
        REFERENCE
    }
    class BookCopy {
        +id() String
        +book() Book
    }
    class LoanTerms {
        +maxActive() int
        +loanDays() int
    }
    class BorrowingPolicy {
        <<interface>>
        +termsFor(Member, BookCopy) LoanTerms
    }
    class LegacyPolicy
    class RevisedPolicy
    class BorrowingService {
        -BorrowingPolicy policy
        +borrow(memberId,copyId) Loan
        +changePolicy(policy) void
    }
    class Loan {
        +borrowedOn() LocalDate
        +dueOn() LocalDate
        +isOpen() boolean
    }
    BookCopy --> Book
    Book --> BookKind
    BorrowingPolicy <|.. LegacyPolicy
    BorrowingPolicy <|.. RevisedPolicy
    BorrowingService --> BorrowingPolicy
    BorrowingService --> Loan
~~~

**Do not replace `Loan.dueOn()` with a policy lookup at read time.** Otherwise a Loan originally due in 14 days could "suddenly" have only 7 days after a policy change. `dueOn` is a snapshot of terms fixed when borrowing. Updating the policy interface may force old callers/implementations to recompile; this API change requires explicit identification, tests, and a deployment plan.

There is no need for `ReferenceLoanService`, `NormalLoanService`, or two separate Loan stores. Copies remain the same entity type; only the **loan-duration policy** varies by category. Composition is more appropriate than introducing a subclass tree solely for 7- or 14-day terms.

## 3. Complete Java 17 code: legacy and revised policies over shared data

Create **`LibraryChangeDemo.java`** with no third-party libraries. The demo preserves the project's core BRs within one process, focusing on policy substitution and historical preservation.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class LibraryChangeDemo {
    enum BookKind { NORMAL, REFERENCE }

    record Book(String isbn, String title, BookKind kind) {
        Book {
            if (isbn == null || isbn.isBlank()
                    || title == null || title.isBlank()) {
                throw new IllegalArgumentException("Invalid book");
            }
            Objects.requireNonNull(kind, "kind");
        }
    }

    record BookCopy(String id, Book book) {
        BookCopy {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Invalid copyId");
            }
            Objects.requireNonNull(book, "book");
        }
    }

    record Member(String id, boolean active) {
        Member {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Invalid memberId");
            }
        }
    }

    record LoanTerms(int maxActive, int loanDays) {
        LoanTerms {
            if (maxActive <= 0 || loanDays <= 0) {
                throw new IllegalArgumentException("Invalid policy");
            }
        }
    }

    interface BorrowingPolicy {
        LoanTerms termsFor(Member member, BookCopy copy);
    }

    static final class LegacyPolicy implements BorrowingPolicy {
        public LoanTerms termsFor(Member member, BookCopy copy) {
            Objects.requireNonNull(member);
            Objects.requireNonNull(copy);
            return new LoanTerms(3, 14);
        }
    }

    static final class RevisedPolicy implements BorrowingPolicy {
        public LoanTerms termsFor(Member member, BookCopy copy) {
            Objects.requireNonNull(member);
            Objects.requireNonNull(copy);
            int days = copy.book().kind() == BookKind.REFERENCE ? 7 : 14;
            return new LoanTerms(5, days);
        }
    }

    static final class Loan {
        private final String id;
        private final String memberId;
        private final String copyId;
        private final LocalDate borrowedOn;
        private final LocalDate dueOn;
        private LocalDate returnedOn;

        Loan(String id, String memberId, String copyId,
             LocalDate borrowedOn, LocalDate dueOn) {
            this.id = Objects.requireNonNull(id);
            this.memberId = Objects.requireNonNull(memberId);
            this.copyId = Objects.requireNonNull(copyId);
            this.borrowedOn = Objects.requireNonNull(borrowedOn);
            this.dueOn = Objects.requireNonNull(dueOn);
            if (!dueOn.isAfter(borrowedOn)) {
                throw new IllegalArgumentException("Invalid due date");
            }
        }

        String id() { return id; }
        String memberId() { return memberId; }
        String copyId() { return copyId; }
        LocalDate borrowedOn() { return borrowedOn; }
        LocalDate dueOn() { return dueOn; }
        boolean isOpen() { return returnedOn == null; }

        boolean isOverdue(LocalDate day) {
            return isOpen() && Objects.requireNonNull(day).isAfter(dueOn);
        }

        void returnOn(LocalDate day) {
            Objects.requireNonNull(day);
            if (!isOpen()) {
                throw new IllegalStateException("ALREADY_RETURNED");
            }
            if (day.isBefore(borrowedOn)) {
                throw new IllegalArgumentException("RETURN_BEFORE_BORROW");
            }
            returnedOn = day;
        }
    }

    static final class BorrowingService {
        private final Map<String, Member> members = new HashMap<>();
        private final Map<String, BookCopy> copies = new HashMap<>();
        private final Map<String, Loan> loans = new HashMap<>();
        private BorrowingPolicy policy;
        private final Clock clock;
        private long sequence = 1;

        BorrowingService(BorrowingPolicy policy, Clock clock) {
            this.policy = Objects.requireNonNull(policy);
            this.clock = Objects.requireNonNull(clock);
        }

        synchronized void register(Member member) {
            Objects.requireNonNull(member);
            if (members.putIfAbsent(member.id(), member) != null) {
                throw new IllegalArgumentException("DUPLICATE_MEMBER");
            }
        }

        synchronized void addCopy(BookCopy copy) {
            Objects.requireNonNull(copy);
            if (copies.putIfAbsent(copy.id(), copy) != null) {
                throw new IllegalArgumentException("DUPLICATE_COPY");
            }
        }

        synchronized void changePolicy(BorrowingPolicy updated) {
            policy = Objects.requireNonNull(updated);
        }

        synchronized Loan borrow(String memberId, String copyId) {
            Member member = members.get(memberId);
            BookCopy copy = copies.get(copyId);
            if (member == null || copy == null) {
                throw new IllegalArgumentException("UNKNOWN_MEMBER_OR_COPY");
            }
            if (!member.active()) {
                throw new IllegalStateException("MEMBER_INACTIVE");
            }

            LocalDate today = LocalDate.now(clock);
            LoanTerms terms = Objects.requireNonNull(
                    policy.termsFor(member, copy));
            long active = loans.values().stream()
                    .filter(l -> l.memberId().equals(memberId) && l.isOpen())
                    .count();
            if (active >= terms.maxActive()) {
                throw new IllegalStateException("LIMIT_REACHED");
            }
            if (loans.values().stream().anyMatch(l ->
                    l.memberId().equals(memberId) && l.isOverdue(today))) {
                throw new IllegalStateException("OVERDUE_LOAN");
            }
            if (loans.values().stream().anyMatch(l ->
                    l.copyId().equals(copyId) && l.isOpen())) {
                throw new IllegalStateException("COPY_UNAVAILABLE");
            }

            LocalDate due = today.plusDays(terms.loanDays());
            long next = Math.addExact(sequence, 1L);
            Loan loan = new Loan("L-" + sequence,
                    memberId, copyId, today, due);
            loans.put(loan.id(), loan);
            sequence = next;
            return loan;
        }

        synchronized void returnLoan(String loanId) {
            Loan loan = loans.get(loanId);
            if (loan == null) {
                throw new IllegalArgumentException("LOAN_NOT_FOUND");
            }
            loan.returnOn(LocalDate.now(clock));
        }

        synchronized int activeCount(String memberId) {
            return (int) loans.values().stream()
                    .filter(l -> l.memberId().equals(memberId) && l.isOpen())
                    .count();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void rejected(Runnable action) {
        try {
            action.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("Expected business rejection");
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-03-01T00:00:00Z"), ZoneOffset.UTC);
        BorrowingService service =
                new BorrowingService(new LegacyPolicy(), fixed);
        service.register(new Member("TV-001", true));

        Book normal = new Book("ISBN-N", "Java căn bản", BookKind.NORMAL);
        Book reference = new Book("ISBN-R", "OOP tham khảo",
                BookKind.REFERENCE);
        service.addCopy(new BookCopy("BS-001", normal));
        service.addCopy(new BookCopy("BS-002", reference));
        for (int i = 3; i <= 6; i++) {
            service.addCopy(new BookCopy("BS-00" + i, normal));
        }

        // Giao dịch trước lúc thay chính sách.
        Loan oldLoan = service.borrow("TV-001", "BS-001");
        check(oldLoan.dueOn().equals(LocalDate.of(2026, 3, 15)),
                "Old loan must have 14 days");

        // Chính sách mới có hiệu lực cho các giao dịch tiếp theo.
        service.changePolicy(new RevisedPolicy());
        Loan referenceLoan = service.borrow("TV-001", "BS-002");
        Loan standardLoan = service.borrow("TV-001", "BS-003");
        service.borrow("TV-001", "BS-004");
        service.borrow("TV-001", "BS-005");

        check(referenceLoan.dueOn().equals(
                LocalDate.of(2026, 3, 8)), "Reference = 7 days");
        check(standardLoan.dueOn().equals(
                LocalDate.of(2026, 3, 15)), "Normal = 14 days");
        check(oldLoan.dueOn().equals(
                LocalDate.of(2026, 3, 15)), "History unchanged");
        check(service.activeCount("TV-001") == 5, "Exactly five active");
        rejected(() -> service.borrow("TV-001", "BS-006"));

        System.out.println("Old due: " + oldLoan.dueOn());
        System.out.println("Reference due: " + referenceLoan.dueOn());
        System.out.println("Normal due: " + standardLoan.dueOn());
        System.out.println("Active loans: " + service.activeCount("TV-001"));
        System.out.println("PASS: change + backward compatibility");
    }
}
~~~

Run:

~~~bash
javac --release 17 LibraryChangeDemo.java
java LibraryChangeDemo
~~~

Expected output:

~~~text
Old due: 2026-03-15
Reference due: 2026-03-08
Normal due: 2026-03-15
Active loans: 5
PASS: change + backward compatibility
~~~

**How does this example differ from the previous implementation stage?** The previous lesson showed how to enforce invariants and test individual use cases. This one applies **two policies with different effective periods** to the same Loan store and examines the impact of changing requirements: existing Loans retain their `dueOn`, while new Loans use the revised policy. To focus on the requirement change, this example **derives BookCopy availability from open Loans** instead of also storing a status flag on BookCopy. This modeling choice avoids two sources of truth in RAM; performance and transactional guarantees must be reassessed for a database implementation.

## 4. Before-and-after acceptance matrix

| Test | Policy/condition | Expected result |
|---|---|---|
| CH-01 | Before change, NORMAL loan on 01/03 | Due 15/03 (14 days) |
| CH-02 | After change, REFERENCE loan on 01/03 | Due 08/03 (7 days) |
| CH-03 | After change, NORMAL loan on 01/03 | Due 15/03 |
| CH-04 | Existing Loan after new policy takes effect | `dueOn` remains unchanged |
| CH-05 | Member has exactly 5 open Loans and requests copy number 6 | `LIMIT_REACHED`, no Loan created |
| CH-06 | Blocked member | Reject without changing data |
| CH-07 | Member has an open Loan due yesterday | Reject new borrowing because of overdue status |
| CH-08 | Return a Loan and attempt to return it again | Reject the second attempt |
| CH-09 | Return before `borrowedOn` | Reject; Loan remains open |
| CH-10 | Two copies share an ISBN but have separate IDs | Allow independent loans; do not confuse titles with copies |

Tests CH-01 through CH-05 are illustrated in `main`; CH-06 through CH-10 are required exercises for full acceptance coverage. With JUnit 5, write each case as an `@Test` and create a new service/store per test to avoid order dependencies. Use `Clock.fixed` or a mutable test clock to exercise date boundaries and returns.

### Testing object relationships under the revised policy

A well-designed `BorrowingPolicy` receives only the data it needs instead of reading a singleton containing `currentBook`. You can replace `RevisedPolicy` with a fake returning `LoanTerms(1, 2)` to verify that the service rejects the second loan and assigns a 2-day term. This is **polymorphism backed by an actual requirement**, since two policies have been confirmed rather than introducing an interface solely for its own sake.

Remember that `changePolicy` in the demo is exposed to in-memory callers. In production, **policy changes must be authorized, audited administrative actions with effective dates**; arbitrary HTTP clients must not be allowed to change policies.

## 5. Evaluate design using evidence, not class counts

Choose 5 criteria, score each from 0–2 points, and cite verifiable evidence:

| Criterion | What to demonstrate | Evidence in this example |
|---|---|---|
| **Business correctness** | NFR/BR/CR rules remain valid and historical data is preserved | CH-01 through CH-10, with fixed `Loan.dueOn` |
| **Cohesion** | Loan owns its lifecycle, policy owns rules, service orchestrates | `Loan.returnOn`, `RevisedPolicy.termsFor` |
| **Dependency level (coupling/DIP)** | Service does not depend on concrete `LegacyPolicy`/`RevisedPolicy` | `BorrowingPolicy` can be injected/replaced |
| **Testability** | Dates can be computed without real time, a DB, or UI | `Clock.fixed`, in-memory Map |
| **Simplicity (KISS/YAGNI)** | No needless factory/registry/classes introduced by name alone | One policy interface, two implementations |

Assign **0** when requirements are unmet or evidence is absent; **1** when partly satisfied with specific limitations; **2** when supported by suitable code/tests. Maximum score is 10. In your submission, include scores and specific tests, classes, or changes as evidence; do not award full marks solely because the program runs once.

### Two approaches to critique

**Option A — Scatter `if (kind == REFERENCE)` across every Loan creation site.** This uses fewer classes, but changing loan periods or member categories would require updating repeated rules in multiple places, creating real maintenance costs.

**Option B — Use `BorrowingPolicy`.** This adds a contract but centralizes category-based decisions, supports focused tests, and can be replaced in the service without altering the lending flow. It is justified by the actual requirement change; however, with just one call site and two fixed branches, a tested pure function may also suffice. Explain **why your choice is valuable in this particular project**.

A compatibility consideration: changing the signature from `terms()` to `termsFor(member,copy)` **does not preserve source compatibility**. Update implementers, callers, tests, and documentation; a public library may also need an adapter or migration. `LegacyPolicy` continues to support the old business contract, while the public API intentionally changes.

## 6. Second change request and handoff exercise

Management then asks: **“Reference books cannot be renewed; normal books may be renewed once for at most 7 days.”**

**Tasks:**

1. Clarify currently overdue loans, reserved books, maximum extension duration, and when the new due date is finalized. Do not expose a public `setDueOn` method.
2. Design `extendLoan(loanId, days)` according to business rules; if a Loan can be extended only once, record whether it was extended (`extensionCount`) or maintain an auditable renewal history.
3. `Loan` must protect its own "open" state, require new due dates after existing ones, and enforce the renewal count; a policy decides whether a book category is eligible for renewal.
4. Write test cases: NORMAL may extend 7 days; an 8-day extension is rejected; a second extension is rejected; REFERENCE is rejected; returned Loans cannot be extended; failed requests preserve the original due date.
5. Trace changes to requirements, UML, tests, and responsible classes; explain whether another interface is necessary or the current policy should be extended.

**Deliverables:** Java code, test results, a change-comparison table, a class diagram, and evidence-based evaluation across 5 dimensions. For codebases with databases, also include a migration for `kind`, policy version/effective date, and transaction tests. When constraints span more than one Loan (for example, borrowing a copy already held by someone else), enforce atomicity at the transaction-owning boundary.

### Final acceptance checklist

- [ ] Follow the learning sequence from requirements → classes/relationships → implementation/tests → changed requirements in **the same library domain**.
- [ ] Distinguish original limits of 3/14 from revised limits of 5/7–14 by effective date.
- [ ] Existing Loans do not have due dates recalculated by the new policy.
- [ ] Borrow by `copyId`, with multiple independent copies per title.
- [ ] Test limits, overdue, inactive members, duplicate returns, and invalid return dates.
- [ ] Explain when a policy interface reduces change locations and when it is unnecessary design.
- [ ] Distinguish one-JVM guarantees from transactions/unique constraints required across nodes.
- [ ] Evaluate design from evidence and trade-offs, not just SOLID terminology.

**Learning outcome:** A requirement change is more than replacing 3 with 5. It requires identifying historical transaction data, newly effective policies, responsibility for calculating due dates, and tests covering both old and new behavior. This is how an OOP model's quality is evaluated when real requirements evolve.
