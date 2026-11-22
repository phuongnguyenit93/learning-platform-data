# Capstone project: Implementing and testing book lending/return behavior (Java 17)

> **Place in the exercise series:** Continues requirements analysis (FR-01…FR-08, BR-01…BR-08) and class/relationship design. This lesson turns `Book` (title), `BookCopy` (physical copy), `Member`, `Loan`, and `BorrowingService` into runnable code with behavioral tests. **Rules retained:** members must be active, have at most **3 open loans** and no overdue outstanding loan; copies must be AVAILABLE, with a **14-day** loan term. This is still an in-memory application without a database.

## 1. Contract to implement

| ID | Given/When | Then — required result |
|---|---|---|
| BR-01 | Blocked member requests a loan | Reject; do not create Loan |
| BR-02 | Member already has 3 open Loans and attempts another | Reject the fourth loan |
| BR-03 | Copy `BS-001` is already ON_LOAN | Do not create a Loan for **BS-001**, even if `BS-002` of the same title is available |
| BR-04 | An open Loan has `today > dueOn` | Block new loans; a loan due today is not overdue |
| BR-05 | Borrow on 01/03/2026 | `dueOn = 15/03/2026` |
| BR-06 | Return a Loan twice | Reject the second attempt; do not overwrite return date |
| BR-07 | Return date precedes `borrowedOn` | Reject; Loan and BookCopy unchanged |
| BR-08 | Open Loan with `today == dueOn` | Not overdue; overdue only when `today > dueOn` |
| NFR-01/02 | Two tasks borrow one copy concurrently, or storage fails mid-operation | Exactly one loan succeeds and no partial state remains within system guarantees |

`Book` represents a title (`BookTitle` in requirements). **Always lend by `copyId`, never by ISBN**, because a title can have multiple copies. `BorrowingPolicy` provides limits and loan duration; `Clock` is injected for deterministic date tests.

### Behavior flow to protect

~~~mermaid
sequenceDiagram
    actor Staff as Nhân viên
    participant S as BorrowingService
    participant P as BorrowingPolicy
    participant C as BookCopy
    participant L as Loan
    Staff->>S: borrow(memberId, copyId)
    S->>S: Tìm Member và BookCopy
    S->>P: terms()
    S->>S: Kiểm tra active, quota, overdue, available
    alt Hợp lệ
        S->>L: new Loan(... dueOn)
        S->>C: checkOut()
        S->>S: Ghi Loan
        S-->>Staff: Loan, copy ON_LOAN
    else Không hợp lệ
        S-->>Staff: Exception, giữ nguyên state
    end
~~~

## 2. Standalone exercise structure

Create a Java 17 + Maven project:

~~~text
library-practice/
├── pom.xml
└── src/
    ├── main/java/vn/example/library/
    │   └── LibraryPractice.java
    └── test/java/vn/example/library/
        └── LibraryPracticeTest.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>library-practice</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

For easy copying and execution, types are declared **nested** in one public class. In larger projects, split them into separate files while keeping the same contracts.

## 3. Complete Java code — `LibraryPractice.java`

~~~java
package vn.example.library;

import java.time.Clock;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;

public final class LibraryPractice {
    private LibraryPractice() {}

    private static String nonblank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " is required");
        }
        return value.trim();
    }

    // Book là ĐẦU sách; nhiều BookCopy có thể tham chiếu một Book.
    public record Book(String isbn, String title) {
        public Book {
            isbn = nonblank(isbn, "isbn");
            title = nonblank(title, "title");
        }
    }

    public record Member(String id, String name, boolean active) {
        public Member {
            id = nonblank(id, "memberId");
            name = nonblank(name, "name");
        }
    }

    public enum CopyStatus { AVAILABLE, ON_LOAN }

    public static final class BookCopy {
        private final String id;
        private final Book book;
        private CopyStatus status = CopyStatus.AVAILABLE;

        public BookCopy(String id, Book book) {
            this.id = nonblank(id, "copyId");
            this.book = Objects.requireNonNull(book, "book");
        }

        public String id() { return id; }
        public Book book() { return book; }
        public CopyStatus status() { return status; }

        private void checkOut() {
            if (status != CopyStatus.AVAILABLE) {
                throw new IllegalStateException("COPY_UNAVAILABLE");
            }
            status = CopyStatus.ON_LOAN;
        }

        private void checkIn() {
            if (status != CopyStatus.ON_LOAN) {
                throw new IllegalStateException("COPY_NOT_ON_LOAN");
            }
            status = CopyStatus.AVAILABLE;
        }
    }

    public static final class Loan {
        private final String id;
        private final String memberId;
        private final String copyId;
        private final LocalDate borrowedOn;
        private final LocalDate dueOn;
        private LocalDate returnedOn;

        private Loan(String id, String memberId, String copyId,
                LocalDate borrowedOn, LocalDate dueOn) {
            this.id = nonblank(id, "loanId");
            this.memberId = nonblank(memberId, "memberId");
            this.copyId = nonblank(copyId, "copyId");
            this.borrowedOn = Objects.requireNonNull(borrowedOn);
            this.dueOn = Objects.requireNonNull(dueOn);
            if (!dueOn.isAfter(borrowedOn)) {
                throw new IllegalArgumentException("INVALID_DUE_DATE");
            }
        }

        public String id() { return id; }
        public String memberId() { return memberId; }
        public String copyId() { return copyId; }
        public LocalDate borrowedOn() { return borrowedOn; }
        public LocalDate dueOn() { return dueOn; }
        public LocalDate returnedOn() { return returnedOn; }
        public boolean isOpen() { return returnedOn == null; }

        public boolean isOverdue(LocalDate today) {
            return isOpen() && Objects.requireNonNull(today)
                    .isAfter(dueOn);
        }

        private void close(LocalDate date) {
            Objects.requireNonNull(date, "date");
            if (!isOpen()) {
                throw new IllegalStateException("LOAN_ALREADY_RETURNED");
            }
            if (date.isBefore(borrowedOn)) {
                throw new IllegalArgumentException("RETURN_BEFORE_BORROW");
            }
            returnedOn = date;
        }
    }

    public record LoanTerms(int maxActive, int loanDays) {
        public LoanTerms {
            if (maxActive <= 0 || loanDays <= 0) {
                throw new IllegalArgumentException("INVALID_POLICY");
            }
        }
    }

    @FunctionalInterface
    public interface BorrowingPolicy {
        LoanTerms terms();
    }

    // Một implementation của hợp đồng, không cần factory/DI framework.
    public static final class FixedPolicy implements BorrowingPolicy {
        private final LoanTerms terms;

        public FixedPolicy(int maxActive, int loanDays) {
            terms = new LoanTerms(maxActive, loanDays);
        }

        @Override
        public LoanTerms terms() { return terms; }
    }

    public static final class BorrowingService {
        private final Map<String, Member> members = new HashMap<>();
        private final Map<String, BookCopy> copies = new HashMap<>();
        private final Map<String, Loan> loans = new HashMap<>();
        private final BorrowingPolicy policy;
        private final Clock clock;
        private long nextNumber = 1L;

        public BorrowingService(BorrowingPolicy policy, Clock clock) {
            this.policy = Objects.requireNonNull(policy, "policy");
            this.clock = Objects.requireNonNull(clock, "clock");
        }

        public synchronized void register(Member member) {
            Objects.requireNonNull(member, "member");
            if (members.putIfAbsent(member.id(), member) != null) {
                throw new IllegalArgumentException("DUPLICATE_MEMBER");
            }
        }

        public synchronized void addCopy(BookCopy copy) {
            Objects.requireNonNull(copy, "copy");
            if (copies.putIfAbsent(copy.id(), copy) != null) {
                throw new IllegalArgumentException("DUPLICATE_COPY");
            }
        }

        public synchronized Loan borrow(String memberId, String copyId) {
            String memberKey = nonblank(memberId, "memberId");
            String copyKey = nonblank(copyId, "copyId");
            Member member = members.get(memberKey);
            BookCopy copy = copies.get(copyKey);
            if (member == null) {
                throw new NoSuchElementException("MEMBER_NOT_FOUND");
            }
            if (copy == null) {
                throw new NoSuchElementException("COPY_NOT_FOUND");
            }

            LocalDate today = LocalDate.now(clock);
            LoanTerms terms = Objects.requireNonNull(
                    policy.terms(), "terms");
            if (!member.active()) {
                throw new IllegalStateException("MEMBER_INACTIVE");
            }

            long activeCount = loans.values().stream()
                    .filter(l -> l.isOpen()
                            && l.memberId().equals(memberKey))
                    .count();
            if (activeCount >= terms.maxActive()) {
                throw new IllegalStateException("LIMIT_REACHED");
            }

            boolean overdue = loans.values().stream()
                    .anyMatch(l -> l.memberId().equals(memberKey)
                            && l.isOverdue(today));
            if (overdue) {
                throw new IllegalStateException("OVERDUE_LOAN");
            }
            if (copy.status() != CopyStatus.AVAILABLE) {
                throw new IllegalStateException("COPY_UNAVAILABLE");
            }

            LocalDate due = today.plusDays(terms.loanDays());
            long next = Math.addExact(nextNumber, 1L);
            Loan loan = new Loan("L-" + nextNumber, member.id(),
                    copy.id(), today, due);

            // Một critical section trên service trong MỘT JVM.
            copy.checkOut();
            loans.put(loan.id(), loan);
            nextNumber = next;
            return loan;
        }

        public synchronized Loan returnLoan(String loanId) {
            Loan loan = loans.get(nonblank(loanId, "loanId"));
            if (loan == null) {
                throw new NoSuchElementException("LOAN_NOT_FOUND");
            }
            BookCopy copy = copies.get(loan.copyId());
            LocalDate today = LocalDate.now(clock);

            // Kiểm tra trước cả hai object để lỗi không ghi nửa chừng.
            if (!loan.isOpen()) {
                throw new IllegalStateException("LOAN_ALREADY_RETURNED");
            }
            if (today.isBefore(loan.borrowedOn())) {
                throw new IllegalArgumentException("RETURN_BEFORE_BORROW");
            }
            if (copy == null || copy.status() != CopyStatus.ON_LOAN) {
                throw new IllegalStateException("COPY_STATE_MISMATCH");
            }
            loan.close(today);
            copy.checkIn();
            return loan;
        }

        public synchronized int activeCount(String memberId) {
            return (int) loans.values().stream()
                    .filter(l -> l.isOpen()
                            && l.memberId().equals(memberId)).count();
        }

        public synchronized CopyStatus copyStatus(String copyId) {
            BookCopy copy = copies.get(copyId);
            if (copy == null) {
                throw new NoSuchElementException("COPY_NOT_FOUND");
            }
            return copy.status();
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                java.time.Instant.parse("2026-03-01T00:00:00Z"),
                java.time.ZoneOffset.UTC);
        BorrowingService service = new BorrowingService(
                new FixedPolicy(3, 14), clock);
        Book title = new Book("ISBN-1", "Java căn bản");
        service.register(new Member("TV-001", "An", true));
        service.addCopy(new BookCopy("BS-001", title));
        service.addCopy(new BookCopy("BS-002", title));

        Loan loan = service.borrow("TV-001", "BS-001");
        System.out.println("Hạn trả: " + loan.dueOn());
        System.out.println("BS-001: " + service.copyStatus("BS-001"));
        System.out.println("BS-002: " + service.copyStatus("BS-002"));
        service.returnLoan(loan.id());
        System.out.println("Đã trả? " + !loan.isOpen());
        System.out.println("BS-001: " + service.copyStatus("BS-001"));
    }
}
~~~

Compile the main file (without JUnit):

~~~bash
javac -encoding UTF-8 -d out src/main/java/vn/example/library/LibraryPractice.java
java -cp out vn.example.library.LibraryPractice
~~~

Expected output:

~~~text
Hạn trả: 2026-03-15
BS-001: ON_LOAN
BS-002: AVAILABLE
Đã trả? true
BS-001: AVAILABLE
~~~

Observe that `BS-001` and `BS-002` share an ISBN but retain independent states. In `borrow`, the due date is fixed when the Loan is created. `BorrowingService` coordinates constraints across Member, Loan, and BookCopy; `Loan` and `BookCopy` enforce their own internal conditions. Callers have no public setters for dates or status.

## 4. Acceptance testing — `LibraryPracticeTest.java`

Use **JUnit Jupiter 5** in the same package; create `src/test/java/vn/example/library/LibraryPracticeTest.java`.

~~~java
package vn.example.library;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import vn.example.library.LibraryPractice.*;

class LibraryPracticeTest {
    // Đồng hồ thay đổi được trong test; app code chỉ biết Clock.
    static final class AdjustableClock extends Clock {
        private LocalDate day = LocalDate.of(2026, 3, 1);

        void on(int dayOfMonth) {
            day = LocalDate.of(2026, 3, dayOfMonth);
        }

        void setDate(LocalDate nextDay) {
            day = nextDay;
        }

        @Override public ZoneId getZone() { return ZoneOffset.UTC; }

        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(instant(), zone);
        }

        @Override public Instant instant() {
            return day.atStartOfDay(ZoneOffset.UTC).toInstant();
        }
    }

    private AdjustableClock clock;
    private BorrowingService service;
    private Book book;

    @BeforeEach
    void setUp() {
        clock = new AdjustableClock();
        service = new BorrowingService(new FixedPolicy(3, 14), clock);
        book = new Book("ISBN-1", "Java căn bản");
        service.register(new Member("TV-001", "An", true));
        service.register(new Member("TV-002", "Bình", false));
        for (int i = 1; i <= 4; i++) {
            service.addCopy(new BookCopy("BS-00" + i, book));
        }
    }

    @Test
    void createsLoanForExactlyOneBookCopy() {
        Loan loan = service.borrow("TV-001", "BS-001");
        assertEquals(LocalDate.of(2026, 3, 15), loan.dueOn());
        assertEquals(CopyStatus.ON_LOAN, service.copyStatus("BS-001"));
        assertEquals(CopyStatus.AVAILABLE, service.copyStatus("BS-002"));
        assertEquals(1, service.activeCount("TV-001"));
    }

    @Test
    void inactiveMemberAndBorrowedCopyAreRejected() {
        assertThrows(IllegalStateException.class,
                () -> service.borrow("TV-002", "BS-001"));
        Loan first = service.borrow("TV-001", "BS-001");
        assertThrows(IllegalStateException.class,
                () -> service.borrow("TV-001", "BS-001"));
        assertEquals(1, service.activeCount("TV-001"));
        assertTrue(first.isOpen());
    }

    @Test
    void fourthOpenLoanIsRejected() {
        service.borrow("TV-001", "BS-001");
        service.borrow("TV-001", "BS-002");
        service.borrow("TV-001", "BS-003");
        assertThrows(IllegalStateException.class,
                () -> service.borrow("TV-001", "BS-004"));
        assertEquals(3, service.activeCount("TV-001"));
        assertEquals(CopyStatus.AVAILABLE, service.copyStatus("BS-004"));
    }

    @Test
    void overdueStartsAfterDueDateAndBlocksNewBorrow() {
        Loan first = service.borrow("TV-001", "BS-001");
        clock.on(15);
        assertFalse(first.isOverdue(LocalDate.now(clock)));
        service.borrow("TV-001", "BS-002"); // đúng ngày hạn không chặn
        clock.on(16);
        assertTrue(first.isOverdue(LocalDate.now(clock)));
        assertThrows(IllegalStateException.class,
                () -> service.borrow("TV-001", "BS-003"));
        assertEquals(CopyStatus.AVAILABLE, service.copyStatus("BS-003"));
    }

    @Test
    void invalidReturnPreservesStateAndSecondReturnFails() {
        Loan loan = service.borrow("TV-001", "BS-001");
        // Dùng cùng service/kho; lùi đồng hồ trước ngày mượn.
        clock.setDate(LocalDate.of(2026, 2, 28));
        assertThrows(IllegalArgumentException.class,
                () -> service.returnLoan(loan.id()));
        assertTrue(loan.isOpen());
        assertEquals(CopyStatus.ON_LOAN, service.copyStatus("BS-001"));

        clock.setDate(LocalDate.of(2026, 3, 1));
        service.returnLoan(loan.id());
        assertFalse(loan.isOpen());
        assertThrows(IllegalStateException.class,
                () -> service.returnLoan(loan.id()));
        assertEquals(CopyStatus.AVAILABLE, service.copyStatus("BS-001"));
    }

    @Test
    void duplicateMemberAndCopyIdsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.register(new Member("TV-001", "Khác", true)));
        assertThrows(IllegalArgumentException.class,
                () -> service.addCopy(new BookCopy("BS-001", book)));
    }
}
~~~

Test `invalidReturnPreservesStateAndSecondReturnFails` deliberately moves the clock backward on **the same service holding the Loan**, confirms the error preserves Loan/BookCopy state, restores a valid date, and attempts to return twice.

Run the complete suite with:

~~~bash
mvn clean test
~~~

PASS conditions: exit code 0, all JUnit tests green, 0 failures/0 errors. The example contains 6 core tests; add invalid-return-date and concurrency tests for broader NFR coverage.

## 5. Why does the design have limitations?

- **One JVM / one service instance:** `synchronized` on `BorrowingService` prevents two requests to the same instance from both passing check-then-act simultaneously. It **does not protect** different instances or JVMs with separate stores.
- **No database transaction:** in the demo, updating `BookCopy` and storing a `Loan` are two steps on RAM objects. A serious failure between them, or real database persistence, requires appropriate transactions/rollback and constraints; naming a method `borrow` does not provide distributed atomicity.
- **Sequential Loan IDs:** `nextNumber` is unique only within one service; do not use it as a global ID across processes. Repositories/databases need unique constraints and a suitable ID generator.
- **No staff roles:** borrowing/return authorization belongs at the application boundary; do not mistake `Member.active` for caller authorization.
- **BookCopy status snapshot:** `Loan` and `BookCopy` each represent part of the lending lifecycle; in a database, update them in one transaction or derive copy status from open Loans to avoid inconsistency.
- **Date/time problems:** `Clock` fixes the current time for tests; systems spanning timezones must standardize `ZoneId` and when transaction dates are finalized.
- **Intentional real-system limits:** lost/damaged returns, overdue fines, emails, reservations, and multiple branches are excluded; do not add interfaces for hypothetical future behaviors.

## 6. Additional tests and handoff

The invalid return-date path is covered by `invalidReturnPreservesStateAndSecondReturnFails`. Add tests for overdue returns, unknown loan IDs, borrowing again after a return, and borrowing two copies with the same ISBN by different members.

For concurrency within one `BorrowingService`, launch two tasks calling `borrow` on the same AVAILABLE `BookCopy`; assert **exactly one** succeeds and one is rejected. When migrating to a database or distributed backend, use integration tests for unique constraints/indexes on active Loans per `copyId`, transactions, and contract-compliant conflict handling.

### Acceptance traceability table

| Requirement | Object/method | Test |
|---|---|---|
| BR-01, FR-04 | `Member.active`, `BorrowingService.borrow` | `inactiveMemberAndBorrowedCopyAreRejected` |
| BR-02, FR-04 | `BorrowingService.activeCount` | `fourthOpenLoanIsRejected` |
| BR-03 | `BookCopy.checkOut` | `createsLoanForExactlyOneBookCopy` |
| BR-04, BR-08 | `Loan.isOverdue`, service borrow | `overdueStartsAfterDueDateAndBlocksNewBorrow` |
| BR-05 | `Loan.dueOn` | `createsLoanForExactlyOneBookCopy` |
| BR-06 | `Loan.close`, service return | `invalidReturnPreservesStateAndSecondReturnFails` |
| BR-07 | `Loan.close` | `invalidReturnPreservesStateAndSecondReturnFails` |
| NFR-01/02 | Lock/transaction at the store | Integration test with DB; stress test on one service |

**Completion criteria:** `mvn clean test` passes; two copies with the same ISBN retain independent status; the loan limit of 3, a term of 14 days, and rules for blocked/overdue/returned cases are tested; callers cannot directly alter Loan/BookCopy; and learners understand the difference between one-JVM in-memory guarantees and durable database transactions.
