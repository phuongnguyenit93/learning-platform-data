# Dự án tổng hợp: Hiện thực và kiểm thử hành vi mượn/trả sách (Java 17)

> **Vị trí trong chuỗi thực hành:** Tiếp nối bài phân tích yêu cầu (FR-01…FR-08, BR-01…BR-08) và bài thiết kế lớp–quan hệ. Bài này chuyển thiết kế `Book` (đầu sách), `BookCopy` (bản vật lý), `Member`, `Loan` và `BorrowingService` thành mã chạy được cùng kiểm thử hành vi. **Quy tắc giữ nguyên:** thành viên đang hoạt động, tối đa **3 phiếu mở**, không có phiếu quá hạn chưa trả; bản sách phải AVAILABLE, hạn trả **14 ngày**. Phiên bản này vẫn là ứng dụng in-memory, chưa có database.

## 1. Hợp đồng cần hiện thực

| ID | Given/When | Then – kết quả bắt buộc |
|---|---|---|
| BR-01 | Thành viên bị khóa yêu cầu mượn | Từ chối; không tạo Loan |
| BR-02 | Thành viên đã có 3 Loan mở, muốn mượn thêm | Từ chối phiếu thứ tư |
| BR-03 | Bản sách `BS-001` đã ON_LOAN | Không tạo Loan mới cho **BS-001**, dù bản `BS-002` cùng đầu sách còn sẵn |
| BR-04 | Có Loan mở với `today > dueOn` | Chặn mượn mới; đúng ngày hạn chưa là quá hạn |
| BR-05 | Mượn 01/03/2026 | `dueOn = 15/03/2026` |
| BR-06 | Trả một Loan hai lần | Lần hai bị từ chối, không ghi ngày trả mới |
| BR-07 | Trả ngày trước `borrowedOn` | Từ chối, Loan và BookCopy không đổi |
| BR-08 | Loan còn mở, `today == dueOn` | Chưa quá hạn; `today > dueOn` mới quá hạn |
| NFR-01/02 | Hai tác vụ cùng mượn một bản hoặc một thao tác lưu trữ lỗi | Chỉ một lượt thành công và không có trạng thái nửa chừng theo phạm vi bảo đảm của hệ thống |

`Book` ở ví dụ chính là đầu sách (`BookTitle` trong tài liệu yêu cầu). **Mượn theo `copyId`, tuyệt đối không dùng ISBN làm khóa mượn**, vì một đầu sách có thể có nhiều bản. `BorrowingPolicy` có vai trò cung cấp giới hạn và số ngày mượn; `Clock` được tiêm để test ngày chính xác.

### Luồng hành vi cần bảo vệ

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

## 2. Cấu trúc bài chạy độc lập

Dùng Java 17 và Maven, tạo:

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

Để dễ chép và chạy, các kiểu được khai báo **nested** trong một lớp công khai duy nhất. Khi dự án lớn hơn, tách chúng thành các file riêng theo cùng hợp đồng.

## 3. Code Java đầy đủ – `LibraryPractice.java`

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

Biên dịch file chính (không cần JUnit):

~~~bash
javac -encoding UTF-8 -d out src/main/java/vn/example/library/LibraryPractice.java
java -cp out vn.example.library.LibraryPractice
~~~

Kết quả dự kiến:

~~~text
Hạn trả: 2026-03-15
BS-001: ON_LOAN
BS-002: AVAILABLE
Đã trả? true
BS-001: AVAILABLE
~~~

Điểm cần quan sát: `BS-001` và `BS-002` cùng một ISBN nhưng có trạng thái độc lập. Trong `borrow`, ngày trả được chốt ngay khi tạo Loan. `BorrowingService` điều phối ràng buộc giữa Member, Loan, BookCopy; `Loan` và `BookCopy` tự kiểm tra điều kiện nội tại. Caller không có setter công khai thay ngày/ trạng thái.

## 4. Kiểm thử nghiệm thu – `LibraryPracticeTest.java`

Dùng **JUnit Jupiter 5** cùng package, tạo `src/test/java/vn/example/library/LibraryPracticeTest.java`.

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

Test `invalidReturnPreservesStateAndSecondReturnFails` chủ động lùi đồng hồ trên **chính service đang giữ Loan**, xác nhận lỗi không thay đổi Loan/BookCopy, sau đó khôi phục ngày hợp lệ và thử trả hai lần.

Chạy toàn bộ với:

~~~bash
mvn clean test
~~~

Điều kiện PASS: exit code 0, mọi JUnit test xanh, 0 failures/0 errors. Có 6 test cốt lõi trong ví dụ; bổ sung test ngày trả sai và giao dịch đồng thời để bao phủ thêm NFR.

## 5. Vì sao thiết kế có giới hạn?

- **Một JVM / một service instance:** `synchronized` trên `BorrowingService` khiến hai request dùng đúng cùng instance không thể cùng vượt qua check-then-act tại một thời điểm. Nó **không bảo vệ** hai instance hoặc hai JVM có kho lưu khác nhau.
- **Chưa có database transaction:** trong demo, thay đổi `BookCopy` và lưu `Loan` là hai bước trên object ở RAM. Một lỗi nghiêm trọng giữa hai bước hoặc việc lưu vào DB thật đòi hỏi transaction/rollback và constraint thích hợp; tên method `borrow` không tạo atomicity phân tán.
- **Mã Loan tuần tự:** `nextNumber` chỉ duy nhất trong phạm vi một service; không dùng nó như mã toàn cục khi có nhiều tiến trình. Repository/DB cần khóa duy nhất và ID generator phù hợp.
- **Chưa có role cho nhân viên:** yêu cầu phân quyền thao tác mượn/trả thuộc boundary ứng dụng; không nên coi `Member.active` là phân quyền của người gọi.
- **Snapshot trạng thái BookCopy:** `Loan` và `BookCopy` cùng biểu diễn một phần vòng đời; nếu triển khai database, cần cập nhật trong một transaction hoặc chọn mô hình trạng thái suy ra từ Loan mở để tránh lệch.
- **Lỗi ngày giờ:** `Clock` giúp cố định thời điểm; hệ thống nhiều múi giờ phải thống nhất `ZoneId` và thời điểm chốt ngày giao dịch.
- **Giới hạn cố ý về hệ thống thực:** chưa có trả sách mất/hỏng, phạt quá hạn, email, đặt chỗ hoặc nhiều chi nhánh; không mở interface cho từng hành vi chỉ vì dự đoán tương lai.

## 6. Mở rộng kiểm thử và bàn giao

Đường lỗi ngày trả trước ngày mượn đã nằm trong `invalidReturnPreservesStateAndSecondReturnFails`. Hãy bổ sung ca trả quá hạn, mã phiếu không tồn tại, mượn lại sau trả, và hai bản cùng ISBN cùng được mượn bởi hai thành viên khác nhau.

Đối với concurrency cùng một `BorrowingService`, tạo hai task cùng gọi `borrow` trên một `BookCopy` đang AVAILABLE; kiểm tra **chỉ một** thành công và một bị từ chối. Khi thay backend bằng DB hoặc phân tán, chuyển test sang integration test xác nhận unique constraint/index cho Loan mở của mỗi `copyId`, transaction và xử lý xung đột đúng hợp đồng.

### Bảng truy vết nghiệm thu

| Yêu cầu | Đối tượng/method | Test |
|---|---|---|
| BR-01, FR-04 | `Member.active`, `BorrowingService.borrow` | `inactiveMemberAndBorrowedCopyAreRejected` |
| BR-02, FR-04 | `BorrowingService.activeCount` | `fourthOpenLoanIsRejected` |
| BR-03 | `BookCopy.checkOut` | `createsLoanForExactlyOneBookCopy` |
| BR-04, BR-08 | `Loan.isOverdue`, service borrow | `overdueStartsAfterDueDateAndBlocksNewBorrow` |
| BR-05 | `Loan.dueOn` | `createsLoanForExactlyOneBookCopy` |
| BR-06 | `Loan.close`, service return | `invalidReturnPreservesStateAndSecondReturnFails` |
| BR-07 | `Loan.close` | `invalidReturnPreservesStateAndSecondReturnFails` |
| NFR-01/02 | Lock/transaction tại kho | Integration test khi có DB; stress test cùng service |

**Tiêu chí hoàn thành:** `mvn clean test` chạy thành công; tạo được hai bản cùng ISBN với trạng thái độc lập; giới hạn 3, hạn 14 ngày, quy tắc khóa/quá hạn/trả được kiểm thử; mã không cho caller ghi trực tiếp Loan/BookCopy; và người học phân biệt rõ bảo đảm trong RAM một JVM với transaction dữ liệu lâu bền.