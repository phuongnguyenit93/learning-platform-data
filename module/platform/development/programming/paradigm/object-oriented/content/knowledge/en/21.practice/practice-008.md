# Capstone project: Requirements analysis and use cases (Java OOP)

> **Context:** This is the starting point of an object-oriented project. Before defining classes or writing Java, the team must agree on **who uses the system, what they need, why, what constitutes success, and which cases must be rejected**. The exercise uses library lending management as a running example. The specific rules below are **exercise assumptions**; in a real project, confirm them with authorized business decision-makers.

## 1. Learning outcomes

After this exercise, you can:

1. Turn a vague description into **project scope**, a stakeholder list, and functional and nonfunctional requirements.
2. Distinguish **user needs**, **business rules**, **use cases**, **acceptance criteria**, and **class design**.
3. Specify use cases with actors, triggers, preconditions, main flows, exception flows, and postconditions.
4. Identify missing or contradictory requirements by asking questions and exploring boundary scenarios.
5. Derive a preliminary Java object model, check consistency, and list tests before implementation.

**Expected deliverables:** a scope statement, identified requirements table, business-rule list, use-case diagram, at least two detailed use-case specifications, preliminary domain model, requirements-to-tests traceability matrix, and open questions needing confirmation.

## 2. Problem and scope

A training center library currently uses paper records. Staff struggle to tell whether a **specific book copy** can be borrowed, who currently has it, and when it is due. The center wants a basic Java application to prevent duplicate records and enforce lending/return rules consistently.

**Business objectives:** staff can look up copies, record loans and returns accurately, and view active loans. Each transaction must have an unambiguous outcome and preserve history.

**In scope for the first version (MVP):**

- Search book titles, their copies, and availability status.
- Look up registered members and check account status.
- Create a loan for a book copy and calculate its due date.
- Return a book, update copy status, and close the loan.
- List a member's currently active loans.

**Out of scope for the first version:** late-fee payments, reservations, email/SMS, bulk book import, online registration, and multiple branches. These can enter the backlog after needs are confirmed.

**Sample data:** two titles, “Java căn bản” and “OOP thực hành”; the first title has two distinct copies, BS-001 and BS-002. Member TV-001 is active, while TV-002 is blocked. Distinguish a *book title* from a *book copy* during analysis: one title may have multiple copies with different loan statuses.

## 3. Identifying stakeholders and eliciting requirements

| Stakeholder | Goal or concern | Interview questions |
|---|---|---|
| Library staff (primary actor) | Process loans/returns quickly and explain rejections | Who can create transactions? What happens during a network outage? |
| Member (beneficiary) | Know availability, due dates, and loan history | How many books may be borrowed? What happens with late returns? |
| Library manager | Preserve data and monitor lending activity | Which policies take priority? Who may change them? |
| Developer/tester | Get explicit implementation and verification criteria | What exactly do "available", "overdue", and "successful return" mean? |
| Storage system/clock | Supply current state and date | Which timezone applies to dates? How is duplicate recording prevented? |

Do not ask only "What features do you want?" Ask staff to walk through a real transaction, a rejection, error correction, and records that must be retained. Observe the current process and forms, then **record unconfirmed assumptions**. Interviews should yield testable requirements instead of vague adjectives such as "fast", "easy", or "reliable".

For example, "A person may borrow only 3 books" is ambiguous. Does it mean **3 copies on loan concurrently** or 3 loans per month? If someone has exactly 3 loans, may they borrow a fourth copy? Are further loans blocked if one is overdue? This exercise chooses at most 3 **open loans**; the fourth is rejected.

## 4. Testable requirements specification

### 4.1. Functional requirements

| ID | Requirement | Core acceptance condition | Priority |
|---|---|---|---|
| FR-01 | Search book titles and copies | Display correct copy IDs and availability | Must |
| FR-02 | Search members | Find members by ID and show active/blocked status | Must |
| FR-03 | Record a book-copy loan | If rules pass, create exactly one loan and mark the copy on loan | Must |
| FR-04 | Reject invalid loan requests | Explain the reason; do not change state or create a loan | Must |
| FR-05 | Record book returns | Close the correct loan and mark the copy available | Must |
| FR-06 | List open loans | Display member, copy ID, borrow date, and due date | Must |
| FR-07 | View loan/return history | Returned transactions remain searchable | Should |
| FR-08 | Report overdue books | Filter unreturned loans where current date exceeds the due date | Could |

“Must / Should / Could” prioritizes implementation scope; it is **not** the order in which Java functions are invoked. Each requirement needs a stable ID, approver, and acceptance criteria.

### 4.2. Business rules

| ID | Rule used in this exercise | Boundary example |
|---|---|---|
| BR-01 | Only active members may borrow | Blocked TV-002 → reject |
| BR-02 | Each member may have at most 3 unreturned loans at once | Exactly 3 → reject the fourth |
| BR-03 | Only a copy with AVAILABLE status can be borrowed | BS-001 on loan → reject, even if BS-002 remains available |
| BR-04 | Reject new loans if a member has at least one overdue loan | Due yesterday, not yet returned → reject |
| BR-05 | Due date = borrow date + 14 calendar days | Borrow on 01/03 → due 15/03 |
| BR-06 | Each loan may be successfully returned only once | Second return attempt → reject, do not duplicate |
| BR-07 | Return date must not precede borrow date | Return 05/03, borrowed 06/03 → error |
| BR-08 | Overdue means not returned and **current date > due date** | Not overdue on the due date itself |

Confirm these policies before fixing them in configuration. Do not invent fines, holidays, or renewal rules without user requirements.

### 4.3. Nonfunctional requirements

| ID | Quality attribute | Suggested verification |
|---|---|---|
| NFR-01 | Data integrity | Two concurrent requests for the same copy cannot both succeed |
| NFR-02 | Consistency | Failed transactions must not leave a copy marked on loan without a loan record |
| NFR-03 | Usability | Errors clearly show relevant member/copy IDs and rejection reasons |
| NFR-04 | Testability | Policy logic is separate from UI; current date is passed in or supplied through Clock |
| NFR-05 | Maintainability | Change loan limits or duration without editing many locations |

**Note:** Response-time milliseconds, concurrent-user counts, authentication mechanisms, and history-retention periods need stakeholder confirmation; do not invent figures to appear "complete".

## 5. Identifying actors and use cases

An **actor** is a role interacting with the system, not necessarily a Java class. In the MVP, **Library staff** is the primary actor carrying out transactions for members; **Members** are beneficiaries whose data is handled. Members become direct actors only if a self-service portal is added.

| ID | Use case | Primary actor | Desired result |
|---|---|---|---|
| UC-01 | Search book copies | Staff | Know which copies are currently lendable |
| UC-02 | Lend a book to a member | Staff | Create one valid loan |
| UC-03 | Accept a book return | Staff | Close the correct loan |
| UC-04 | View open loans | Staff | Obtain an accurate list and due dates |

~~~mermaid
flowchart LR
    NV["Nhân viên thư viện"]
    subgraph SYS["Hệ thống mượn/trả sách"]
        UC1(["UC-01 Tra cứu bản sách"])
        UC2(["UC-02 Mượn sách"])
        UC3(["UC-03 Trả sách"])
        UC4(["UC-04 Xem lượt mượn mở"])
    end
    NV --> UC1
    NV --> UC2
    NV --> UC3
    NV --> UC4
~~~

The diagram describes **user goals and the system boundary**, not a class diagram or UI/API design. Name use cases using **verb + object**, avoiding technical names such as "call BorrowService" or "write to loans table".

## 6. Detailed UC-02 specification — Lending a book copy

| Attribute | Description |
|---|---|
| ID / Name | UC-02 — Lend one book copy to a member |
| Primary actor | Library staff |
| Trigger | A member requests a copy identified by its ID |
| Input | memberId, copyId, transaction date |
| Preconditions | Staff member is authorized; member ID and copy ID exist |
| Success postconditions | Create an open Loan, mark copy ON_LOAN, and save due date |
| Failure postconditions | No Loan is created; copy and loan states remain unchanged |
| Related rules | BR-01 through BR-05; NFR-01, NFR-02 |

**Success flow:**

1. Staff enter member ID and scan the book copy ID.
2. System finds the member and copy and displays details for confirmation.
3. System checks active membership, number of open loans, overdue loans, and the status of **that exact copy**.
4. System calculates the due date by adding 14 days to the transaction date.
5. System saves the Loan and updates copy status as **one consistent transaction**.
6. System returns loan ID, copy ID, and due date.

**Alternative and error flows:**

- **A1 – Member not found:** show "Member not found"; create no records.
- **A2 – Copy not found:** show "Book copy not found"; create no records.
- **A3 – Member blocked (BR-01):** reject loan.
- **A4 – Already has 3 open loans (BR-02):** reject loan.
- **A5 – Overdue loan exists (BR-04):** reject and suggest resolving the overdue loan.
- **A6 – Copy currently on loan (BR-03):** reject; another copy of the same title may be available.
- **A7 – Two staff members lend one copy concurrently:** exactly one transaction succeeds; the other receives a conflict error.
- **A8 – Storage failure:** roll back all changes; Loan and BookCopy must not be left inconsistent.

~~~mermaid
sequenceDiagram
    actor NV as Nhân viên
    participant UI as Giao diện
    participant S as BorrowingService
    participant R as Kho dữ liệu
    NV->>UI: Yêu cầu mượn(memberId, copyId)
    UI->>S: borrow(memberId, copyId, ngày)
    S->>R: Đọc Member, BookCopy, Loan đang mở
    R-->>S: Dữ liệu hiện tại
    alt Tất cả quy tắc hợp lệ
        S->>R: Lưu Loan + đổi trạng thái bản sách (atomic)
        R-->>S: Thành công
        S-->>UI: Biên nhận và hạn trả
    else Vi phạm quy tắc hoặc xung đột
        S-->>UI: Mã lỗi và lý do
    end
    UI-->>NV: Hiển thị kết quả
~~~

**Common pitfall:** If two threads both read AVAILABLE and then write Loan records without concurrency control, the same copy can be loaned twice. Implement NFR-01 with transactions plus storage constraints/locking or conditional updates against a real database; an if statement in RAM is insufficient.

## 7. Detailed UC-03 specification — Returning a book

| Attribute | Description |
|---|---|
| ID / Name | UC-03 — Return one loan |
| Primary actor | Library staff |
| Input | loanId, return date |
| Preconditions | Loan exists and is open; return date is not before borrow date |
| Success postconditions | Loan has returnedAt, copy is AVAILABLE, and history is preserved |
| Failure postconditions | Neither Loan nor BookCopy changes |
| Related rules | BR-06, BR-07; NFR-02 |

**Main flow:** (1) Staff identify the correct open loan; (2) system validates return date and state; (3) system records the return date and makes the copy available in one transaction; (4) system returns a success receipt.

**Exceptions:** unknown loan ID; already returned; return date before borrow date; storage failure. In the MVP, **overdue copies can still be returned**; fee collection is out of scope and must not block returns.

## 8. From business language to an object model

Separate **domain nouns** (Member, BookTitle, BookCopy, Loan) from **coordinating behavior** (BorrowingService) and **infrastructure** (LoanRepository, MemberRepository, CopyRepository). A book copy is a distinct object; Loan represents one transaction. Do not store borrow dates directly on BookTitle because a title has multiple copies.

| Concept | Key attributes | Suggested responsibility |
|---|---|---|
| Member | id, active | Identify a member and account status |
| BookTitle | isbn, title | Describe a work/book title |
| BookCopy | id, bookTitle, status | Represent a physical copy and control its status |
| Loan | id, member, copy, borrowedOn, dueOn, returnedOn | Record a loan's lifecycle |
| BorrowingPolicy | maxActiveLoans, loanDays | Provide/enforce lending policy |
| BorrowingService | repositories, policy, Clock | Execute UC-02 and UC-03, coordinating persistence |

~~~mermaid
classDiagram
    class Member {
        +String id
        +boolean active
    }
    class BookTitle {
        +String isbn
        +String title
    }
    class BookCopy {
        +String id
        +CopyStatus status
    }
    class Loan {
        +String id
        +LocalDate borrowedOn
        +LocalDate dueOn
        +LocalDate returnedOn
    }
    class BorrowingService {
        +borrow(memberId, copyId)
        +returnCopy(loanId)
    }
    BookTitle "1" --> "0..*" BookCopy : bao_gồm
    Member "1" --> "0..*" Loan : thực_hiện
    BookCopy "1" --> "0..*" Loan : lịch_sử
    BorrowingService ..> Loan : xử_lý
~~~

**Use cases versus classes:** UC-02 is a **multi-step business goal**; it may require interactions among Member, BookCopy, Loan, Policy, and Repository. Do not make a class for every step or treat every noun in the description as a mandatory entity.

The preliminary OOP design may change as requirements are validated. Declare only attributes needed for behavior; use **encapsulation** to prevent external state tampering; assign responsibilities by **single responsibility**; access data through interfaces when storage types need to be interchangeable.

## 9. Java 17 example of encoding business rules

This **in-memory simulation** illustrates the connection between requirements and business validation. It lacks staff authentication, a database, transactions, and concurrency safety. Save it as **LibraryDemo.java** and run with Java 17+.

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class LibraryDemo {
    enum CopyStatus { AVAILABLE, ON_LOAN }

    static final class Member {
        final String id;
        final boolean active;

        Member(String id, boolean active) {
            this.id = Objects.requireNonNull(id);
            this.active = active;
        }
    }

    static final class BookCopy {
        final String id;
        private CopyStatus status = CopyStatus.AVAILABLE;

        BookCopy(String id) {
            this.id = Objects.requireNonNull(id);
        }

        boolean isAvailable() {
            return status == CopyStatus.AVAILABLE;
        }

        void checkOut() {
            if (!isAvailable()) throw new IllegalStateException("COPY_UNAVAILABLE");
            status = CopyStatus.ON_LOAN;
        }

        void checkIn() {
            if (status != CopyStatus.ON_LOAN)
                throw new IllegalStateException("COPY_NOT_ON_LOAN");
            status = CopyStatus.AVAILABLE;
        }
    }

    static final class Loan {
        final Member member;
        final BookCopy copy;
        final LocalDate borrowedOn;
        final LocalDate dueOn;
        private LocalDate returnedOn;

        Loan(Member member, BookCopy copy, LocalDate borrowedOn, int loanDays) {
            this.member = member;
            this.copy = copy;
            this.borrowedOn = borrowedOn;
            this.dueOn = borrowedOn.plusDays(loanDays); // BR-05
        }

        boolean isOpen() {
            return returnedOn == null;
        }

        boolean isOverdue(LocalDate today) {
            return isOpen() && today.isAfter(dueOn); // BR-08
        }

        void close(LocalDate date) {
            if (!isOpen()) throw new IllegalStateException("LOAN_ALREADY_RETURNED");
            if (date.isBefore(borrowedOn))
                throw new IllegalArgumentException("RETURN_BEFORE_BORROW");
            returnedOn = date;
        }
    }

    static final class BorrowingService {
        private static final int MAX_ACTIVE = 3;
        private static final int LOAN_DAYS = 14;
        private final List<Loan> loans = new ArrayList<>();

        Loan borrow(Member member, BookCopy copy, LocalDate today) {
            Objects.requireNonNull(member);
            Objects.requireNonNull(copy);
            Objects.requireNonNull(today);

            if (!member.active)                    // BR-01
                throw new IllegalStateException("MEMBER_INACTIVE");

            long activeCount = loans.stream()
                .filter(l -> l.member == member && l.isOpen())
                .count();
            if (activeCount >= MAX_ACTIVE)          // BR-02
                throw new IllegalStateException("LIMIT_REACHED");

            boolean hasOverdue = loans.stream()
                .anyMatch(l -> l.member == member && l.isOverdue(today));
            if (hasOverdue)                         // BR-04
                throw new IllegalStateException("OVERDUE_LOAN");

            if (!copy.isAvailable())                // BR-03
                throw new IllegalStateException("COPY_UNAVAILABLE");

            Loan loan = new Loan(member, copy, today, LOAN_DAYS);
            copy.checkOut();
            loans.add(loan);
            return loan;
        }

        void returnCopy(Loan loan, LocalDate returnedOn) {
            if (!loans.contains(loan))
                throw new IllegalArgumentException("LOAN_NOT_FOUND");
            Objects.requireNonNull(returnedOn);
            if (!loan.isOpen())
                throw new IllegalStateException("LOAN_ALREADY_RETURNED");
            if (returnedOn.isBefore(loan.borrowedOn))
                throw new IllegalArgumentException("RETURN_BEFORE_BORROW");

            loan.close(returnedOn);                // BR-06, BR-07
            loan.copy.checkIn();
        }
    }

    public static void main(String[] args) {
        Member member = new Member("TV-001", true);
        BookCopy copy = new BookCopy("BS-001");
        BorrowingService service = new BorrowingService();

        LocalDate borrowedOn = LocalDate.of(2026, 3, 1);
        Loan loan = service.borrow(member, copy, borrowedOn);
        System.out.println("Hạn trả: " + loan.dueOn);  // 2026-03-15
        System.out.println("Còn sách? " + copy.isAvailable()); // false

        service.returnCopy(loan, LocalDate.of(2026, 3, 15));
        System.out.println("Đã trả? " + !loan.isOpen()); // true
        System.out.println("Còn sách? " + copy.isAvailable()); // true
    }
}
~~~

**Why is the example not production-ready?** It compares Member objects by reference because it uses the same in-memory instances; real data requires stable **identity IDs**. The RAM Loan store does not survive application restarts; updates to Loan and BookCopy can diverge on an intervening failure. Production code should delegate persistence to repositories, wrap state changes in transactions, and ensure only one actor can move a copy from AVAILABLE to ON_LOAN. These risks were specified as NFRs during requirements analysis.

## 10. Acceptance scenarios and tests

The following are **business-level test specifications** suitable for later JUnit tests. For deterministic tests, pass a fixed test date or inject Clock rather than calling LocalDate.now() directly.

| Test ID | Related requirements | Given (initial state) | When (action) | Then (expected) |
|---|---|---|---|---|
| T-01 | FR-03, BR-05 | TV-001 active, BS-001 AVAILABLE, no overdue loans | Borrow on 01/03/2026 | Open Loan, due 15/03/2026, copy ON_LOAN |
| T-02 | FR-04, BR-01 | Member blocked | Borrow BS-001 | MEMBER_INACTIVE, no Loan created |
| T-03 | FR-04, BR-02 | Member already has exactly 3 open Loans | Borrow a fourth copy | LIMIT_REACHED, prior data unchanged |
| T-04 | FR-04, BR-03 | BS-001 ON_LOAN | Borrow BS-001 again | COPY_UNAVAILABLE, no Loan created |
| T-05 | FR-04, BR-04, BR-08 | Open Loan due 14/03 | Borrow on 15/03 | OVERDUE_LOAN |
| T-06 | FR-03, BR-08 | Open Loan due 15/03, with no other overdue loan | Borrow on 15/03 if below limit | Not blocked for overdue status |
| T-07 | FR-05, BR-06 | Open Loan | Return twice on valid dates | First succeeds; second LOAN_ALREADY_RETURNED |
| T-08 | FR-05, BR-07 | Loan borrowed on 06/03 | Return on 05/03 | RETURN_BEFORE_BORROW, Loan stays open |
| T-09 | NFR-01 | One AVAILABLE copy, two concurrent requests | Both try to borrow the same copyId | Exactly one Loan is recorded |
| T-10 | NFR-02 | Storage fails during borrowing | Transaction fails | No partial Loan or copy-state change |

One scenario expressed in a **Gherkin-like** syntax:

~~~gherkin
Feature: Cho mượn bản sách
  Scenario: Từ chối khi thành viên đã đạt giới hạn
    Given thành viên "TV-001" đang hoạt động
    And thành viên có đúng 3 lượt mượn chưa trả
    And bản sách "BS-004" đang sẵn có
    When nhân viên yêu cầu cho "TV-001" mượn "BS-004"
    Then hệ thống trả lỗi "LIMIT_REACHED"
    And không tạo thêm lượt mượn
    And bản sách "BS-004" vẫn sẵn có
~~~

A good test checks **both outcomes and data invariants after failure**. Do not merely assert that an exception is thrown: if the function changes a copy's state before throwing, the business operation is still wrong.

## 11. Traceability: requirement → use case → class → test

| Requirement/rule | Use case | Expected OOP owner | Test |
|---|---|---|---|
| FR-01 | UC-01 | BookTitle, BookCopy, CatalogService | Copy lookup by copyId |
| FR-03, BR-01, BR-02 | UC-02 | BorrowingService, Member, BorrowingPolicy | T-01, T-02, T-03 |
| FR-04, BR-03, BR-04 | UC-02 | BookCopy, Loan, BorrowingService | T-04, T-05, T-06 |
| FR-03, BR-05 | UC-02 | Loan, BorrowingPolicy | T-01 |
| FR-05, BR-06, BR-07 | UC-03 | Loan, BookCopy, BorrowingService | T-07, T-08 |
| NFR-01, NFR-02 | UC-02 / UC-03 | Repository, transactions, storage constraints | T-09, T-10 |

The traceability table answers three questions: **Where is this requirement implemented? How is it tested? Which components change if the rule changes?** For example, if the limit changes from 3 to 5, update the policy and T-03 without changing every UI class.

## 12. Team exercise workflow

1. **Elicit:** each person interviews one role; collect 5–10 realistic lending/return scenarios, including failures.
2. **Define scope:** agree on MVP, exclusions, and assumptions. Assign FR, NFR, and BR IDs. Every statement needs testable criteria.
3. **Specify:** draw the use-case diagram and fully describe UC-02, UC-03. Check preconditions, error flows, and postconditions.
4. **Analyze objects:** list entities, value objects, services, and repositories; sketch a class diagram; assign responsibilities using business rules.
5. **Design tests before implementation:** write Given–When–Then scenarios for boundaries, invalid data, repeated transactions, concurrency, and storage failures.
6. **Review with stakeholders:** present concrete examples, get approval for policies and open decisions, and only then distribute implementation tasks.

**Checklist before implementation:**

- [ ] Each functional requirement has an ID, actor, input, and observable result.
- [ ] Book titles and physical copies are distinguished; every Loan references the correct copy.
- [ ] The limit of 3, duration of 14 days, overdue definition, and blocked status are confirmed.
- [ ] UC-02/UC-03 describe successful/error flows and postconditions that preserve data.
- [ ] Tests cover exact limits, exceeded limits, and duplicate returns.
- [ ] Persistence, transactions, and concurrent-access requirements are explicitly recorded.
- [ ] A traceability table links requirements to use cases, intended components, and tests.
- [ ] No critical requirement is described only with vague words such as "fast", "good", or "safe".

## 13. Extension exercises and self-assessment

**Exercise A — Analyze a change:** Management raises the member limit to **5 copies**, while reference materials may be borrowed for only **7 days**. Identify FRs/BRs, use cases, classes, and tests that need updating. Discuss whether loan duration belongs as a fixed Loan attribute or should be calculated by Policy at creation (hint: store the **finalized dueOn** in Loan so future policy changes do not retroactively alter old loans).

**Exercise B — Clarify requirements:** Can overdue members return books directly? Is a return on the due date considered late? Can a lost book be "returned"? Write interview questions rather than inventing answers.

**Exercise C — Find a design flaw:** Someone suggests putting a boolean borrowed flag on BookTitle and creating Loans without copyId. Describe at least three failure scenarios for this model, then correct the domain diagram.

**Self-assessment criteria:** Another reader can use the README to reconstruct the business flow and write tests without guessing; every rule has boundary cases; the class model addresses actual requirements rather than arbitrary structure; and unconfirmed decisions are stated clearly.

---

**Remember:** requirements analysis asks **"what must the system do, and what is correct?"**; use cases ask **"who interacts, when, and along which possible flows?"**; only then does object-oriented design ask **"which objects own the data and perform the behavior?"**. Moving from testable requirements to clear use cases helps Java OOP projects avoid early business-rule misunderstandings.
