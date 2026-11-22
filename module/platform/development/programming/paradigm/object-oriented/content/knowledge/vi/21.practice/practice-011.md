# Dự án tổng hợp: Thay đổi yêu cầu và đánh giá thiết kế hệ thống thư viện (Java OOP)

> **Tình huống nối tiếp:** Ở ba bước trước, bạn đã phân tích UC mượn/trả, thiết kế `Book` (đầu sách), `BookCopy` (bản vật lý), `Member` và `Loan`, rồi hiện thực và kiểm thử hệ thống. Hiện tại chỉ thành viên đang hoạt động được mượn, giới hạn **3 phiếu mở**, thời hạn **14 ngày**, không cho mượn nếu có phiếu quá hạn chưa trả. Đây là bài thực hành **thay đổi yêu cầu trên cùng hệ thống**, không chuyển sang bài toán kinh doanh khác.

## 1. Yêu cầu thay đổi từ quản lý thư viện

Giả sử quản lý xác nhận hai yêu cầu mới, có hiệu lực từ một ngày triển khai định trước:

- **CR-01:** Tăng hạn mức từ **3 lên 5 lượt mượn đang mở** cho mỗi thành viên đang hoạt động. Thành viên có khoản quá hạn chưa trả vẫn bị chặn mượn mới.
- **CR-02:** Phân loại đầu sách thành **thông thường (NORMAL)** và **tham khảo (REFERENCE)**. Bản sách thuộc đầu sách tham khảo chỉ được mượn **7 ngày**; sách thông thường vẫn **14 ngày**.
- **CR-03 – tính lịch sử:** hạn trả của **Loan đã tạo trước khi đổi chính sách phải giữ nguyên**. Chính sách chỉ tác động đến Loan mới, không tính lại `dueOn` mỗi lần tra cứu.
- **CR-04 – dữ liệu và độ tin cậy:** cùng một bản sách không được có hai Loan mở; trả sách hai lần vẫn phải bị từ chối. Chính sách mới không làm mất quy tắc thành viên active, overdue và ngày trả hợp lệ.

Các quyết định này là giả định của bài tập. Với dự án thật phải xác nhận: “Tài liệu tham khảo có được đem ra khỏi thư viện không?”, “Chính sách mới có hồi tố không?”, “Ngày nào bắt đầu hiệu lực?”, “Tài liệu cũ chưa gán category thì xếp vào loại nào?”. Không được tự trả lời bằng code khi chưa có người chịu trách nhiệm phê duyệt.

### Tác động tới yêu cầu hiện hữu

| Mã | Trước | Sau khi đổi | Phạm vi tác động |
|---|---|---|---|
| BR-02 / CR-01 | Tối đa 3 Loan mở | Tối đa 5 Loan mở | Policy, test đúng 5/vượt 5 |
| BR-05 / CR-02 | Tất cả bản: 14 ngày | NORMAL: 14; REFERENCE: 7 | Book category, policy, test hạn |
| BR-05 / CR-03 | `dueOn` lưu trong Loan | Vẫn lưu, **không hồi tố** | Loan, dữ liệu lịch sử |
| BR-01,03,04,06,07,08 | Active, available, overdue, trả một lần và đúng ngày | **Giữ nguyên** | Regression tests |
| NFR-01/02 | Cần cập nhật nhất quán nhiều object | Không được nới lỏng | Transaction/locking khi dùng DB |

## 2. Phân tích trách nhiệm trước khi sửa

**Điểm thay đổi tự nhiên** là `BorrowingPolicy`: trong bản trước, `terms()` không nhận thông tin bản sách, vì mọi sách có thời hạn như nhau. Nay chính sách phải biết **loại đầu sách**. Ta sửa hợp đồng một cách có chủ đích thành `termsFor(Member, BookCopy)` và truyền thông tin **tối thiểu** mà policy cần.

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

**Không sửa `Loan.dueOn()` thành phép gọi policy tại thời điểm đọc.** Nếu làm vậy, một Loan mượn trước thay đổi từ 14 ngày có thể “bỗng dưng” đổi hạn còn 7 ngày. `dueOn` là snapshot giao kèo đã chốt lúc mượn. Cập nhật hợp đồng policy có thể làm caller/implementation cũ phải biên dịch lại: đây là một thay đổi API cần được nhận diện, kiểm thử và triển khai có kế hoạch.

Ta cũng không cần `ReferenceLoanService`, `NormalLoanService` và hai kho Loan riêng. Bản sách vẫn là cùng một loại entity, chỉ **chính sách thời hạn** thay đổi theo category; composition phù hợp hơn một cây subclass được tạo chỉ vì 7 hay 14 ngày.

## 3. Code Java 17 hoàn chỉnh: chính sách cũ và mới trên cùng dữ liệu

Tạo file **`LibraryChangeDemo.java`**, không cần thư viện thứ ba. Đoạn demo bảo toàn BR chính của dự án trong cùng một tiến trình, tập trung vào việc thay policy và giữ lịch sử.

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

Chạy:

~~~bash
javac --release 17 LibraryChangeDemo.java
java LibraryChangeDemo
~~~

Kết quả kỳ vọng:

~~~text
Old due: 2026-03-15
Reference due: 2026-03-08
Normal due: 2026-03-15
Active loans: 5
PASS: change + backward compatibility
~~~

**Vì sao ví dụ này khác bước hiện thực trước?** Bài trước dạy cách giữ bất biến và viết test cho từng use case. Bài này đưa **hai chính sách có thời điểm hiệu lực khác nhau** vào cùng một kho Loan và quan sát giới hạn thay đổi: `dueOn` của Loan cũ không đổi, trong khi Loan mới nhận chính sách mới. Để tập trung vào tác động yêu cầu, ví dụ này **suy ra tính sẵn có của BookCopy từ các Loan đang mở**, thay vì đồng thời lưu cả cờ trạng thái trên BookCopy. Đây là một lựa chọn mô hình để tránh hai nguồn sự thật trong RAM; lúc đưa vào DB, tính hiệu năng và transaction phải được đánh giá lại.

## 4. Ma trận nghiệm thu trước/sau

| Test | Chính sách/điều kiện | Kỳ vọng |
|---|---|---|
| CH-01 | Trước thay đổi, NORMAL mượn 01/03 | Hạn 15/03 (14 ngày) |
| CH-02 | Sau thay đổi, REFERENCE mượn 01/03 | Hạn 08/03 (7 ngày) |
| CH-03 | Sau thay đổi, NORMAL mượn 01/03 | Hạn 15/03 |
| CH-04 | Một Loan cũ, đã áp chính sách mới | `dueOn` giữ nguyên |
| CH-05 | Thành viên có đúng 5 Loan mở, mượn bản thứ 6 | `LIMIT_REACHED`, không tạo Loan |
| CH-06 | Thành viên bị khóa | Từ chối, không thay đổi dữ liệu |
| CH-07 | Thành viên có Loan mở hạn hôm qua | Từ chối mượn do quá hạn |
| CH-08 | Trả Loan một lần rồi thử trả tiếp | Lần sau bị từ chối |
| CH-09 | Trả trước `borrowedOn` | Bị từ chối; Loan vẫn mở |
| CH-10 | Hai bản cùng ISBN, mỗi bản có mã riêng | Mượn độc lập; không nhầm book với copy |

Các kiểm thử CH-01 đến CH-05 đã được thể hiện trong `main`; các ca CH-06 đến CH-10 là phần bài tập bắt buộc để nghiệm thu hoàn chỉnh. Với JUnit 5, đưa mỗi ca vào một `@Test`, tạo service/kho mới cho mỗi test để tránh phụ thuộc thứ tự. Dùng `Clock.fixed` hoặc một test clock thay đổi được cho ranh giới ngày và trả sách.

### Kiểm thử quan hệ qua chính sách mới

Một `BorrowingPolicy` tốt nhận đúng dữ liệu nó cần, không đọc một singleton chứa `currentBook`. Có thể thay `RevisedPolicy` bằng fake trả `LoanTerms(1, 2)` để thử service chặn lượt thứ hai và tính hạn 2 ngày. Đây là **đa hình có lý do thực tế**, vì có hai chính sách đã được xác nhận chứ không phải một interface tạo ra chỉ để có interface.

Đừng quên rằng `changePolicy` trong demo là một thao tác được công bố cho người gọi trong RAM. Trong sản phẩm, **thay chính sách phải là hành động quản trị có phân quyền, được audit và gắn thời điểm hiệu lực**; không để bất kỳ HTTP client nào tùy ý đổi nó.

## 5. Chấm thiết kế bằng bằng chứng, không bằng số class

Chọn 5 tiêu chí, mỗi tiêu chí 0–2 điểm và nêu bằng chứng kiểm chứng được:

| Tiêu chí | Cần chứng minh | Bằng chứng trong ví dụ |
|---|---|---|
| **Đúng nghiệp vụ** | NFR/BR/CR được giữ; dữ liệu cũ không bị đổi | CH-01 đến CH-10, `Loan.dueOn` cố định |
| **Tính kết dính (cohesion)** | Loan giữ vòng đời, policy giữ quy tắc, service điều phối | `Loan.returnOn`, `RevisedPolicy.termsFor` |
| **Mức phụ thuộc (coupling/DIP)** | Service không biết cụ thể `LegacyPolicy`/`RevisedPolicy` | `BorrowingPolicy` được inject/đổi |
| **Khả năng kiểm thử** | Không cần thời gian thực, DB hay UI để tính ngày | `Clock.fixed`, Map in-memory |
| **Độ đơn giản (KISS/YAGNI)** | Không thêm factory/registry/class theo tên gọi mà không cần | Một interface policy, hai implementation |

Chấm **0** khi không đáp ứng hoặc không có bằng chứng; **1** khi có nhưng còn hạn chế cụ thể; **2** khi đạt với mã/test phù hợp. Điểm tối đa 10. Trong báo cáo nộp, ghi điểm và dẫn tên test, class hoặc thay đổi cụ thể; đừng tự cho điểm tối đa chỉ vì chương trình chạy một lần.

### Hai phương án cần phản biện

**Phương án A — rải `if (kind == REFERENCE)` vào mỗi nơi tạo Loan.** Ít lớp hơn, nhưng khi cần thay ngày hạn hoặc loại độc giả, những vị trí lặp quy tắc phải được sửa cùng nhau; trường hợp rải nhiều nơi là chi phí thật.

**Phương án B — dùng `BorrowingPolicy`.** Tăng một hợp đồng nhưng gom quyết định theo category vào một nơi, có thể test riêng, thay vào service mà không đổi luồng mượn. Đây là lựa chọn hợp lý khi đã có thay đổi thực tế; tuy nhiên nếu mã chỉ có đúng một call site và hai nhánh cố định, một hàm thuần có test cũng có thể đủ. Hãy nêu **vì sao lựa chọn đáng giá trong dự án cụ thể**.

Một lưu ý tương thích: thay chữ ký `terms()` thành `termsFor(member,copy)` **không phải** refactor giữ nguyên source compatibility. Cần cập nhật implementer, caller, test và tài liệu; khi phát hành thư viện công khai có thể phải cung cấp adapter/migration. Hợp đồng nghiệp vụ cũ vẫn được giữ bởi `LegacyPolicy`, nhưng bề mặt API đã thay đổi có chủ đích.

## 6. Lần thay đổi thứ hai và bài tập bàn giao

Quản lý hỏi tiếp: **“Sách tham khảo không được gia hạn, sách thường có thể gia hạn một lần tối đa 7 ngày.”**

**Việc cần làm:**

1. Làm rõ trường hợp đang quá hạn, sách bị đặt trước, giới hạn ngày tối đa và thời điểm chốt hạn mới. Không mở phương thức `setDueOn` công khai.
2. Thiết kế `extendLoan(loanId, days)` theo nghiệp vụ; nếu một Loan chỉ được gia hạn một lần, phải lưu việc đã gia hạn (`extensionCount`) hoặc lịch sử gia hạn có thể kiểm chứng.
3. `Loan` tự bảo vệ trạng thái “đang mở”, ngày hạn mới phải sau hạn cũ, và số lần gia hạn; một policy quyết định có được gia hạn theo loại sách hay không.
4. Viết bảng test: NORMAL gia hạn 7 ngày được; gia hạn 8 ngày bị từ chối; gia hạn hai lần bị từ chối; REFERENCE bị từ chối; Loan đã trả không được gia hạn; đường lỗi không đổi hạn cũ.
5. Truy vết thay đổi tới yêu cầu, UML, test và lớp chịu trách nhiệm; giải thích có cần thêm một interface khác hay chỉ mở rộng policy hiện tại.

**Nộp bài:** code Java, kết quả test, bảng so sánh thay đổi, sơ đồ lớp và đánh giá 5 trục có bằng chứng. Đối với codebase đã có database, bổ sung migration dữ liệu `kind`, version/effective date của policy và kiểm thử transaction. Khi ràng buộc vượt một Loan (ví dụ mượn bản đã có người khác giữ), tính nguyên tử phải được bảo vệ ở nơi sở hữu giao dịch.

### Checklist nghiệm thu cuối chương

- [ ] Cấu trúc học tập đi từ yêu cầu → class/quan hệ → hiện thực/test → thay đổi yêu cầu trên **cùng miền thư viện**.
- [ ] Giới hạn 3/14 ban đầu và 5/7–14 mới được phân biệt rõ theo thời điểm hiệu lực.
- [ ] Loan đã tạo không bị tính lại hạn do policy mới.
- [ ] Mượn theo `copyId`, một đầu sách có nhiều bản độc lập.
- [ ] Có ca kiểm thử giới hạn, overdue, inactive, trả hai lần và trả ngày sai.
- [ ] Lý giải được khi nào interface policy giúp giảm số nơi sửa, khi nào là thiết kế thừa.
- [ ] Biết phần nào chạy trong một JVM và phần nào đòi transaction/unique constraint khi dùng nhiều node.
- [ ] Đánh giá thiết kế từ bằng chứng và trade-off, không chỉ tên SOLID.

**Kết quả học tập:** Thay đổi yêu cầu không chỉ là thay con số 3 thành 5. Nó buộc bạn xác định dữ liệu nào thuộc giao dịch lịch sử, dữ liệu nào là chính sách có hiệu lực tại thời điểm mới, ai chịu trách nhiệm tính hạn, và phải kiểm thử cả behavior cũ lẫn mới. Đó là cách đánh giá chất lượng của một mô hình OOP sau khi nó gặp thay đổi thật.