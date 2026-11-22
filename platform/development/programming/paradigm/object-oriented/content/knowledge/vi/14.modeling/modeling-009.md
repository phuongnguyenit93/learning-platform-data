# Đối chiếu mô hình với mã và tình huống thực tế trong OOP Java

> **Mục tiêu:** Biết kiểm tra một mô hình hướng đối tượng có diễn tả đúng tình huống nghiệp vụ, được hiện thực đúng bằng Java và tiếp tục đúng khi hệ thống vận hành hay không. Bài học dùng tình huống **mượn và trả bản sách tại thư viện** để thực hành đối chiếu hai chiều giữa yêu cầu, sơ đồ, mã nguồn, kiểm thử và dữ liệu thực tế.

## 1. Ba góc nhìn cần khớp nhau

Một mô hình đẹp chưa chắc đúng. Sơ đồ có thể ghi “mỗi bản sách chỉ có một lượt mượn đang hoạt động” nhưng chương trình vẫn cho hai người mượn cùng bản sách. Ngược lại, mã có thể chạy tốt trên một dữ liệu mẫu nhưng không thể hiện chính sách trả muộn, hoàn trả hay giới hạn lượt mượn.

Khi đối chiếu, cần nhìn **ba nguồn chứng cứ**:

1. **Tình huống thực tế và quy tắc nghiệp vụ:** Ai thực hiện việc gì? Điều kiện nào phải đúng? Điều gì xảy ra khi không hợp lệ, khi làm lại thao tác hoặc khi hai người thao tác đồng thời?
2. **Mô hình thiết kế:** Những khái niệm nào có danh tính và trạng thái? Quan hệ giữa chúng có bội số, vòng đời, quyền sở hữu và trách nhiệm đúng không? Ràng buộc nằm ở đâu?
3. **Mã và hành vi chạy:** Kiểu dữ liệu, API, mức truy cập, lệnh thay đổi trạng thái, transaction và test có thực thi đúng điều mô hình hứa hẹn không?

~~~mermaid
flowchart TD
    R[Use case, ví dụ thực tế, business rule] <-->|kiểm chứng ý nghĩa| M[Mô hình lớp, quan hệ, invariant]
    M <-->|đối chiếu cấu trúc và trách nhiệm| C[Java API và implementation]
    C <-->|kiểm thử hành vi| T[Test và dữ liệu chạy thật]
    T -. lỗi hoặc trường hợp chưa rõ .-> R
~~~

**Đối chiếu không chỉ một chiều “UML → code”.** Khi kiểm tra một chương trình đang tồn tại, ta có thể đi ngược từ code/test về mô hình, rồi hỏi người phụ trách nghiệp vụ liệu hành vi đang chạy có thật sự được mong muốn không. Nếu khác nhau, **không tự mặc định** sơ đồ đúng hoặc code đúng: tìm quyết định nghiệp vụ và cập nhật các phần tương ứng.

## 2. Bắt đầu từ tình huống quan sát được

Giả sử thư viện đưa ra yêu cầu ban đầu:

> “Độc giả đang hoạt động được mượn bản sách còn sẵn. Khi trả sách, bản sách có thể cho mượn lại.”

Từ câu này, cần chủ động hỏi các trường hợp biên:

| Câu hỏi | Quyết định minh họa cho bài |
|---|---|
| Mượn một đầu sách hay một bản vật lý? | Mượn **một BookCopy** có mã bản riêng |
| Người dùng bị khóa tài khoản? | Không được mượn |
| Tối đa bao nhiêu bản đang mượn? | **3 bản** mỗi độc giả |
| Mỗi bản đang được mượn bởi bao nhiêu người? | Tối đa **1 lượt mượn đang hoạt động** |
| Thời hạn mượn? | **14 ngày**, tính theo ngày hiện hành |
| Trả một phiếu đã trả rồi? | Báo lỗi, không tạo thêm thao tác trả |
| Khi trả sách có xóa lịch sử mượn? | Không; lưu ngày trả để truy vết |
| Hai độc giả tranh bản cuối cùng? | Tối đa một yêu cầu thành công |
| Có cho gia hạn, giữ chỗ, xử lý phạt? | Chưa thuộc phạm vi minh họa |

Các quyết định trên là **giả định của ví dụ**, không phải quy tắc thư viện phổ quát. Trong dự án thật phải ghi người phê duyệt, thời điểm hiệu lực, ngoại lệ và những câu hỏi còn mở.

### Chuyển thành use case

**UC-BORROW: Mượn một bản sách**

- **Actor chính:** Độc giả (qua nhân viên thủ thư hoặc ứng dụng).
- **Trigger:** Độc giả yêu cầu mượn bản có `copyId`.
- **Tiền điều kiện:** Hệ thống nhận diện được độc giả và bản sách.
- **Luồng thành công:** Kiểm tra tài khoản → giới hạn lượt mượn → bản còn sẵn → tạo phiếu mượn → đánh dấu bản đang được mượn → trả mã phiếu và hạn trả.
- **Luồng thay thế:** Tài khoản bị khóa; bản không tồn tại; độc giả đủ 3 lượt; bản đang có phiếu mượn còn hiệu lực; lỗi lưu dữ liệu.
- **Hậu điều kiện thành công:** Một phiếu mượn mới có hiệu lực và bản sách không thể bị mượn lần thứ hai cùng lúc.
- **Bảo đảm khi thất bại:** Không tạo nửa phiếu, không vượt giới hạn.

**UC-RETURN: Trả bản sách**

- **Trigger:** Thủ thư nhận bản sách và mã phiếu.
- **Luồng thành công:** Tìm phiếu đang hoạt động → ghi ngày trả → bản có thể mượn tiếp.
- **Luồng thay thế:** Không tìm thấy phiếu hoặc phiếu đã trả → báo lỗi, không làm mất lịch sử.
- **Hậu điều kiện:** Phiếu cũ vẫn được giữ với `returnedOn`; nó không còn được tính là lượt mượn đang hoạt động.

Một use case tốt diễn tả **kết quả và lỗi**, không trói vào “nhấn nút xanh” hay một framework.

## 3. Chuyển các quyết định thành quy tắc có ID

| ID | Business rule | Dữ liệu liên quan | Ví dụ cần kiểm tra |
|---|---|---|---|
| **BR-01** | Chỉ `Member.active == true` được mượn | Member | Member bị khóa bị từ chối |
| **BR-02** | Mỗi Member có tối đa 3 Loan đang hoạt động | Member, Loan | Mượn bản thứ tư bị từ chối |
| **BR-03** | Một BookCopy có tối đa 1 Loan đang hoạt động tại một thời điểm | BookCopy, Loan | Hai người tranh bản cuối |
| **BR-04** | Ngày hẹn trả = ngày mượn + 14 ngày | Loan, ngày nghiệp vụ | Ngày 15/10 → hạn 29/10 |
| **BR-05** | Chỉ phiếu chưa trả mới được thực hiện thao tác trả | Loan | Trả phiếu hai lần bị từ chối |
| **BR-06** | Trả sách không xóa lịch sử Loan | Loan | Phiếu cũ vẫn truy vấn được |
| **BR-07** | Khi thao tác mượn thất bại, không được tạo dữ liệu mượn một phần | Loan, persistence | Không có nửa phiếu |
 
Đầu vào không tồn tại, ID rỗng, dữ liệu sai dạng và lỗi kết nối cũng cần hợp đồng rõ; đây có thể là quy tắc validation kỹ thuật hoặc một business rule riêng tùy phạm vi.

**Không coi danh sách quy tắc là chỉ dẫn duy nhất để code.** Ví dụ BR-03 cần chốt thêm: “phiếu mượn đang hoạt động” nghĩa là `returnedOn == null` hay có trạng thái quá hạn riêng? Trong ví dụ này, một phiếu quá hạn nhưng **chưa trả** vẫn chiếm bản sách.

## 4. Dựng mô hình khái niệm: phân biệt đầu sách, bản sách và phiếu mượn

Ba đối tượng sau không thể gộp tùy tiện:

- **BookTitle:** mô tả đầu sách/tác phẩm hoặc ấn bản; nhiều bản vật lý có thể cùng đầu sách.
- **BookCopy:** một bản cụ thể, có `copyId` riêng; đối tượng bị chiếm dụng khi được mượn.
- **Loan:** một lần mượn cụ thể của một Member đối với một BookCopy, với ngày mượn, hạn trả và ngày hoàn trả.

Sơ đồ khái niệm:

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

**Lưu ý bội số rất quan trọng:** Một `BookCopy` có thể có **nhiều Loan trong lịch sử**, nhưng **tối đa một Loan còn hoạt động**. Multiplicity `0..*` trên toàn bộ lịch sử **không** tự biểu diễn được điều kiện “tối đa một active”; phải ghi constraint bổ sung và thực thi bằng code + lưu trữ. Đây là ví dụ điển hình về việc **đối chiếu mô hình với tình huống thực**: vẽ một đường liên kết chưa đủ.

Đừng vội vẽ composition giữa `Member` và `Loan`: nếu xóa tài khoản thành viên, chính sách lưu lịch sử có thể yêu cầu giữ phiếu mượn. Quan hệ sở hữu/vòng đời phải được quyết định từ yêu cầu, không suy diễn từ việc có field tham chiếu.

### Bảng ánh xạ mô hình sang Java

| Thành phần mô hình | Cách triển khai minh họa | Cần đối chiếu |
|---|---|---|
| Member có identity và active | `record Member(String id, boolean active)` | ID khác rỗng; active có đúng nghĩa miền không |
| Bản vật lý có identity | `record BookCopy(String id, String title)` | Không dùng title làm khóa duy nhất |
| Phiếu mượn có trạng thái | `record Loan(..., returnedOn)` | Còn hoạt động khi `returnedOn == null` |
| Giới hạn 3 lượt | `Library.borrow()` đếm phiếu active | Không đếm toàn bộ lịch sử |
| Một bản đang mượn | `Library.borrow()` kiểm tra active loan cùng copy | Atomic khi có cạnh tranh |
| Thao tác trả | `Library.returnLoan()` thay Loan bằng phiên bản có ngày trả | Không xóa bản ghi lịch sử |
| Hạn trả | `LocalDate.now(clock).plusDays(14)` | Clock/timezone, chính sách ngày nghỉ |

## 5. Java 17: một mô hình nhỏ có thể chạy và kiểm chứng

Ví dụ dùng **một JVM và trạng thái trong bộ nhớ** để tập trung vào việc mô hình thực thi đúng rule. Các public API được giản lược; trên môi trường thật sẽ có repository, transaction, authentication và logging phù hợp.

Tạo tệp **`LibraryModelDemo.java`**:

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

Biên dịch và chạy (JDK 17+):

~~~bash
javac LibraryModelDemo.java
java LibraryModelDemo
~~~

Kết quả mong đợi:

~~~text
2026-10-29
false
Copy is already loaned
true
false
~~~

### Tại sao các quyết định Java này bám mô hình?

- `Member` và `BookCopy` có danh tính riêng: mã **bản sách** khác tên đầu sách. Nếu chỉ dùng `title` làm khóa, một đầu sách có nhiều bản sẽ không được mô hình hóa đúng.
- `Loan` giữ cả `borrowedOn`, `dueOn` và `returnedOn` để biết phiếu nào còn hiệu lực và giữ được lịch sử.
- `Loan.returnOn()` trả **giá trị mới** thay cho sửa record; record Java là kiểu bất biến nông nếu các thành phần bất biến, và ở đây các thành phần là `String`/`LocalDate`.
- `Library.borrow()` kiểm tra BR-01, BR-02, BR-03 rồi ghi; không chỉ kiểm tra trong controller. Query `isAvailable()` không tự thay đổi trạng thái.
- `Clock` được truyền vào để test ngày tháng không phụ thuộc giờ máy. Với nghiệp vụ nhiều khu vực, phải xác định timezone của thư viện và quy tắc thời hạn trước khi dùng `LocalDate.now(clock)`.
- `synchronized` bảo đảm toàn bộ thao tác trên **cùng instance Library trong một JVM** không xen ngang giữa kiểm tra và ghi. Nó không đồng bộ nhiều tiến trình hoặc nhiều máy.
- Trong phương thức `borrow`, Java cho phép gọi đồng bộ `activeLoanCount` và `isAvailable` từ một method đang giữ cùng monitor: `synchronized` là khóa tái nhập (*reentrant*).

Đây là **một cách hiện thực minh họa**, không phải kết luận mô hình phải có đúng một lớp `Library` ôm ba map. Khi cần lưu trữ thật, các map và việc phát sinh ID sẽ chuyển tới các thành phần tương ứng, nhưng các invariant cần vẫn được bảo vệ ở ranh giới giao dịch.

## 6. Kiểm chứng chiều ngược: từ mã suy ra mô hình có đang đúng?

Khi review hoặc bảo trì dự án, đi từ thực thể code về yêu cầu, theo chuỗi:

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

Ví dụ sau là các **mismatch** thường gặp:

| Mô hình/yêu cầu nói | Mã lại làm | Vì sao lệch | Hướng sửa |
|---|---|---|---|
| Một bản sách chỉ có 1 loan active | `borrow()` chỉ kiểm tra `copy != null` | Không kiểm tra phiếu active | Kiểm tra tại lúc ghi và dùng DB constraint/lock khi cần |
| Mỗi độc giả mượn tối đa 3 bản | Đếm tổng số `Loan` trong lịch sử | Người đã trả 3 bản bị chặn vĩnh viễn | Chỉ đếm `returnedOn == null` |
| Trả sách giữ lịch sử | `loans.remove(loanId)` | Mất dấu vết nghiệp vụ | Cập nhật trạng thái/ngày trả |
| Hạn trả 14 ngày | `LocalDate.now()` ở nhiều nơi | Test không ổn định, timezone mơ hồ | Xác định clock/date policy tại một ranh giới |
| Đối tượng Loan không sửa tùy tiện | `public setReturnedOn` không validation | Có thể ghi ngày trả trước ngày mượn | Command `returnOn` kiểm tra invariant |
| Một bản vật lý có mã riêng | Dùng ISBN làm khóa `BookCopy` | Không quản lý được hai bản cùng ISBN | Thêm copy ID riêng |
| Không vượt 1 loan active trên nhiều node | Dùng `synchronized` trên mỗi node | Lock không chia sẻ qua tiến trình | Transaction + constraint/locking ở DB |
| Query không giữ chỗ | Getter gọi ngầm `borrow` | Hiển thị làm thay đổi dữ liệu | Tách query và command rõ ràng |

**Nguyên tắc review:** Không sửa chỉ để đường UML trông giống Java. Nếu sản phẩm đã đổi chính sách được phê duyệt, mô hình cũ có thể đã lỗi thời. Lưu quyết định thay đổi và cập nhật sơ đồ/luật/test cùng nhau.

## 7. Kiểm thử truy vết được từng quy tắc

Một test có ý nghĩa phải trả lời “điều gì đúng hay sai theo BR-xx?” chứ không chỉ xác nhận class có field `loans`.

**Tệp `LibraryModelTest.java`**, đặt cùng package với file `LibraryModelDemo.java`, dùng **JUnit Jupiter 5**:

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

Bộ test này có thể chạy khi dự án cấu hình JUnit Jupiter 5 (ví dụ qua Maven/Gradle); lệnh `javac` đơn thuần chỉ biên dịch ví dụ `LibraryModelDemo.java`, không tự cung cấp thư viện JUnit.

**Điểm còn thiếu:** Các test trên chứng minh hành vi tuần tự trong bộ nhớ. Chúng chưa chứng minh tính đúng đắn khi dữ liệu lưu ở DB hoặc nhiều node; test tích hợp phải kiểm tra ranh giới transaction, unique constraint, rollback và tranh chấp thật ở tầng lưu trữ.

## 8. Kiểm tra một tình huống đồng thời: lời hứa của UML có được giữ?

Trong sơ đồ, một BookCopy có thể có nhiều Loan trong **lịch sử** nhưng tối đa một Loan **đang hoạt động**. Nếu hai độc giả gửi yêu cầu gần như cùng lúc:

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

Thứ tự A trước B chỉ là **một** lịch thực thi minh họa. Nếu B giành lock trước, B có thể thành công. Bất biến cần bảo vệ là **không đồng thời có hai phiếu active** cho cùng copy, chứ không phải “A luôn thắng”.

### Test cạnh tranh cùng một JVM

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

**Tại sao test này có ý nghĩa?** Nó thử đúng một tình huống có thể làm sai mô hình: hai luồng tranh cùng một bản sách. Nhưng nó vẫn **không** xác nhận hệ thống nhiều node. Đặc biệt, test cạnh tranh có thể không lặp lại mọi lịch thực thi; cần cơ chế đồng bộ được chứng minh bằng ranh giới transaction và các phép kiểm tra tích hợp phù hợp.

### Khi dùng database

Để BR-03 tiếp tục đúng trong hệ thống phân tán, cần ngăn hai transaction cùng tạo Loan active cho một BookCopy. Một lựa chọn với **PostgreSQL**, nếu lưu `returned_on` là `NULL` khi chưa trả:

~~~sql
CREATE UNIQUE INDEX uq_active_loan_copy
ON loan(copy_id)
WHERE returned_on IS NULL;
~~~

Chỉ số này đảm bảo tối đa một hàng active theo `copy_id` tại tầng DB, ngay cả khi hai node cùng ghi. Nhưng **BR-02 tối đa 3 loan active mỗi Member** không được bảo vệ chỉ bởi index trên copy: cần transaction với khóa phù hợp theo member, một cơ chế reservation counter atomic, hoặc thiết kế concurrency khác được kiểm chứng.

Quy trình production thường có transaction, xử lý lỗi unique constraint thành lỗi nghiệp vụ rõ ràng, và chính sách retry/idempotency nếu client gửi lại cùng ý định mượn do mất kết nối. Dùng constraint hỗ trợ domain invariant không làm domain model trở nên vô ích: một bên thể hiện chính sách, một bên bảo vệ tính nhất quán ở ranh giới dữ liệu.

## 9. So sánh cấu trúc tĩnh và luồng chạy động

Sơ đồ lớp mô tả **ai liên quan với ai**. Luồng chạy mô tả **thao tác nào xảy ra và theo thứ tự nào**. Cần cả hai khi kiểm tra một use case có nhiều bước.

| Thắc mắc | Bằng chứng nên xem |
|---|---|
| Loan có thuộc về đúng một member và copy không? | Class diagram, kiểu dữ liệu, foreign keys |
| Return phải giữ lịch sử không? | Business rule, `returnLoan()`, test lịch sử |
| Loan đang active được xác định thế nào? | Định nghĩa trạng thái, query, test |
| Có thể có hai active loan cùng copy không? | Concurrency/transaction/unique constraint |
| Mượn khi tài khoản inactive có bị từ chối? | Use case, command validation, test |
| Hạn trả 14 ngày tính ở timezone nào? | Quy tắc nghiệp vụ, Clock, test ngày |
| Nếu DB ghi thất bại, có nửa dữ liệu không? | Transaction boundary, integration test |
| Mã đã thay đổi so với sơ đồ chưa? | Code review, diff, sơ đồ phiên bản hiện tại |

Một mô hình **không cần** chứa toàn bộ chi tiết của code, nhưng những quyết định có ảnh hưởng đến nghiệp vụ phải khớp. Ví dụ cấu trúc `HashMap` trong demo là chi tiết triển khai; yêu cầu “mỗi copy có tối đa một active loan” mới là hợp đồng đáng lưu trong mô hình.

## 10. Phát hiện chênh lệch từ tình huống thực tế

Giả sử trong vận hành xuất hiện các phản hồi:

- “Độc giả đổi thẻ, hệ thống coi họ là người mới và cho mượn quá giới hạn.”
- “Bản sách đã được trả nhưng vẫn báo đang mượn.”
- “Nhân viên nhập sai ngày trả và lịch sử có ngày trước ngày mượn.”
- “Thư viện có ba chi nhánh, hai máy vẫn cho mượn cùng bản sách cuối.”

Cách xử lý không nên bắt đầu bằng một dòng `if` ngẫu nhiên. Trước tiên xác định **mô hình nào đang sai hoặc thiếu**:

| Sự cố | Câu hỏi mô hình | Bổ sung cần cân nhắc |
|---|---|---|
| Đổi thẻ tạo “người mới” | Identity của Member là người hay thẻ thư viện? | Member ID ổn định, LibraryCard như thực thể/giá trị khác |
| Đã trả vẫn báo đang mượn | Return là trạng thái Loan hay thuộc tính tạm của BookCopy? | Định nghĩa nguồn sự thật, đồng bộ chỉ mục |
| Ngày trả sai | Ai xác thực ngày trả? Có cho điều chỉnh có audit? | Lệnh sửa có phân quyền và lưu lịch sử sửa |
| Hai chi nhánh cùng mượn | Boundary giao dịch thực ở đâu? | DB constraint/lock, quy trình phân tán |
| Lượt mượn cũ bị xóa | Có chính sách lưu lịch sử/audit không? | Entity Loan có vòng đời và retention rõ |

**Đừng nhầm lỗi hiển thị với lỗi domain.** Số sách “còn sẵn” hiển thị chậm có thể là query cache, trong khi bản ghi mượn đã đúng. Hãy kiểm tra hệ thống nguồn sự thật và thời điểm quan sát trước khi sửa model.

## 11. Làm sao biết một sơ đồ lớp đã khớp Java?

Một vòng review ngắn gọn, có thể lặp trong code review:

1. **Đối chiếu danh tính:** Mỗi entity có ID đúng nghĩa chưa? `BookTitle` khác `BookCopy`; dùng title/ISBN thay mã bản sẽ gây sai trong tình huống nhiều bản.
2. **Đối chiếu thuộc tính:** `borrowedOn`, `dueOn`, `returnedOn` và `active` có đúng kiểu và trạng thái không? Cho phép `null` có chủ đích hay vô tình?
3. **Đối chiếu API:** Phương thức đặt ở đúng chủ thể? `borrow` là command; `isAvailable` là query; có setter nào cho phép bypass invariant không?
4. **Đối chiếu quan hệ:** Một Loan gắn một Member/copy; một Member/copy có nhiều Loan theo lịch sử. Multiplicity có nêu rõ “active” hay “history”?
5. **Đối chiếu vòng đời:** Xóa/thay đổi entity nào ảnh hưởng phiếu mượn? Nếu có quy tắc lưu lịch sử, không dùng cascade delete tùy tiện.
6. **Đối chiếu hợp đồng lỗi:** Bản không tồn tại, thành viên bị khóa, đã hết hạn mức, bản hết chỗ, phiếu đã trả, lỗi DB — phải có kết quả xác định.
7. **Đối chiếu cạnh tranh:** Các kiểm tra trước command có được giữ nguyên tử đến khi commit hay không?
8. **Đối chiếu test:** Mỗi quy tắc có ít nhất một test hành vi có khả năng thất bại khi code vi phạm không? Có cần integration/contract test?
9. **Đối chiếu tài liệu triển khai:** Nếu đã chuyển từ map sang DB, sơ đồ mức domain có thể giữ nguyên nhưng sơ đồ component/persistence phải cập nhật.
10. **Đối chiếu stakeholder:** Có thay đổi chính sách được duyệt khiến sơ đồ và test cũ không còn đúng không?

Khi phát hiện chênh lệch, ghi ngắn gọn: **hành vi mong đợi → hành vi thực tế → bằng chứng → quyết định sửa → test xác nhận**. Điều này giúp tránh tranh luận cảm tính về sơ đồ “đẹp” hay tên class “chuẩn”.

## 12. Ma trận truy vết từ yêu cầu đến test

| ID | Tình huống | Mô hình/chủ thể | Java API / cơ chế | Bằng chứng kiểm thử |
|---|---|---|---|---|
| UC-BORROW | Độc giả mượn bản còn sẵn | Member, BookCopy, Loan | `Library.borrow` | `borrowCreatesActiveLoanWithCorrectDueDate` |
| BR-01 | Tài khoản bị khóa | Member | Kiểm tra `active` trong command | `inactiveMemberCannotBorrow` |
| BR-02 | Đủ 3 bản active | Loan theo Member | `activeLoanCount` + kiểm tra giới hạn | `fourthActiveLoanIsRejected` |
| BR-03 | Một bản không có hai loan active | BookCopy – Loan | `isAvailable` + lock/DB constraint | `sameCopyCannotBeBorrowedTwice`; concurrency test |
| BR-04 | Hạn trả sau 14 ngày | Loan | `Clock` và `plusDays(14)` | Test ngày cụ thể |
| BR-05 | Không trả lại phiếu đã trả | Loan | `Loan.returnOn` | `returningKeepsHistoryAndMakesCopyAvailable` |
| BR-06 | Lưu phiếu lịch sử | Loan | Update `returnedOn`, không remove | Truy vấn phiếu sau khi trả |
| BR-07 | Không ghi dang dở | Lưu trữ phiếu mượn | Trong RAM một lock; production cần transaction | Integration test rollback/atomicity |

Một quy tắc có thể có nhiều tầng bảo vệ: **domain validation** để diễn đạt và báo lỗi phù hợp; **database constraint** để chặn vi phạm khi nhiều tiến trình cùng ghi. Cùng bảo vệ một invariant không phải lúc nào cũng là sao chép vô ích.

**Đọc ma trận theo chiều ngược:** Nếu một method public có side effect nhưng không truy vết được tới use case/điều kiện nào, cần kiểm tra nó có tạo hành vi ngoài yêu cầu hay không. Nếu một BR không có API hoặc test nào chứng minh, đó là khoảng trống kiểm chứng.

## 13. Đối chiếu thay đổi sau khi sản phẩm đã chạy

Mô hình là **tài liệu sống**. Ví dụ thư viện quyết định từ học kỳ mới cho phép giáo viên mượn 6 bản thay vì 3 bản:

1. Ghi rõ chính sách mới: ai được hưởng, thời gian áp dụng, trường hợp đã mượn trước đó.
2. Cập nhật BR-02 thành quy tắc theo **vai trò hoặc chính sách**; tránh thay số 3 bằng số 6 cho mọi Member.
3. Thảo luận nơi quản lý policy: một `BorrowingPolicy` có thể phù hợp nếu nhiều vai trò, ngày hiệu lực và điều kiện ngoại lệ; khi luật vẫn đơn giản, constant trong domain có thể đủ.
4. Cập nhật mô hình, Java API và test; kiểm tra hợp đồng tương thích cho caller.
5. Xem lại schema/configuration nếu thay đổi đòi thêm thông tin vai trò và version.
6. Triển khai và quan sát thực tế có vi phạm trong dữ liệu cũ hay không.

Có thể biểu diễn thay đổi bằng policy:

~~~java
interface BorrowingPolicy {
    int maxActiveLoans(Member member);
}
~~~

Đây là **đề xuất mở rộng**, không phải phần có sẵn trong demo. Nếu thêm interface chỉ để che một hằng số không bao giờ biến đổi, thiết kế có thể phức tạp hơn cần thiết. Trích xuất trách nhiệm khi nó có lý do thay đổi rõ.

## 14. Những cạm bẫy thường gặp

| Sai lầm | Tại sao có hại | Cách sửa |
|---|---|---|
| “Sơ đồ có đường nối nên mọi rule đã được bảo đảm” | Association không tự giới hạn số loan active | Ghi constraint và bảo vệ lúc ghi |
| “Code chạy demo là đủ” | Happy path không bao phủ lỗi và cạnh tranh | Test phản ví dụ và boundary |
| “Hễ có class trong UML phải có file cùng tên” | Mô hình khái niệm có thể khác cấu trúc triển khai | Chọn mức trừu tượng, nêu mapping |
| “Field `final` làm object bất biến” | Tham chiếu final vẫn có thể trỏ collection mutable | Đóng gói, snapshot, constructor validation |
| “`synchronized` giải quyết mọi tranh chấp” | Lock chỉ có hiệu lực tại một đối tượng/JVM | Ràng buộc transaction ở tầng lưu trữ dùng chung |
| “Loan lịch sử là thuộc sở hữu của Member nên được xóa theo Member” | Chính sách audit/retention có thể khác | Xác định vòng đời từ nghiệp vụ |
| “Chỉ sửa code, không sửa tài liệu/test” | Model drift, lỗi quay lại trong lần sau | Duy trì traceability trong thay đổi |
| “Chỉ sửa sơ đồ cho trông giống code” | Có thể hợp thức hóa một bug đang chạy | Kiểm chứng lại với yêu cầu được duyệt |
| “Dữ liệu thật khác mô hình thì bỏ qua” | Bug có thể đã xuất hiện trong DB | Kiểm tra migration, backfill, integrity |

## 15. Bài tập: đối chiếu đơn đặt hàng thực tế

Một nhóm phát triển có sơ đồ `Customer "1" -- "0..*" Order` và `Order "1" *-- "1..*" OrderLine`. Nhưng khi chạy:

- API tạo `Order` không cần `OrderLine`, để ở trạng thái `DRAFT`.
- `confirm()` từ chối khi danh sách dòng rỗng.
- `OrderLine` có `productId` và giá chốt lúc mua.
- Một Product được nhiều OrderLine tham chiếu.

Hãy thực hiện:

1. Kiểm tra multiplicity `1..*` của `OrderLine` có sai với trạng thái draft không. Đề xuất sơ đồ với `0..*` và constraint **confirmed order must contain >=1 line**.
2. Phân biệt Product độc lập với OrderLine thuộc đơn. Chọn association hay composition và nêu lý do từ vòng đời.
3. Liệt kê ít nhất bốn use case hoặc phản ví dụ: thêm dòng, xác nhận đơn rỗng, sửa đơn đã xác nhận, thay giá catalog sau khi chốt đơn.
4. Viết test đảm bảo `total` của đơn đã chốt không vô tình đổi theo giá catalog hiện tại.
5. Với nhiều yêu cầu xác nhận cùng lúc, đề xuất cách bảo vệ trạng thái chuyển đổi và tính nhất quán trong database.
6. Viết một ma trận traceability gồm ID quy tắc, nơi bảo vệ, test và bằng chứng chạy.

**Tiêu chí đạt:** Người đọc xác định được **chênh lệch mô hình nào là có chủ đích theo trạng thái**, chênh lệch nào là bug, và một cách kiểm chứng cụ thể cho mỗi quyết định.

---

**Ghi nhớ:** Đối chiếu mô hình với mã và tình huống thực tế là một vòng kiểm chứng **hai chiều**: lấy use case/rule để hỏi mô hình và code có đúng không, dùng test/dữ liệu vận hành để phát hiện giả định thiếu, rồi cập nhật những phần phải thay đổi. Giá trị của mô hình nằm ở **hành vi và invariant kiểm chứng được**, không ở việc sơ đồ chứa thật nhiều hộp và mũi tên.