# Dự án tổng hợp: Phân tích yêu cầu và tình huống sử dụng (Java OOP)

> **Bối cảnh:** Đây là bước khởi đầu của một dự án hướng đối tượng. Trước khi tạo class hoặc viết Java, nhóm cần thống nhất **ai dùng hệ thống, cần làm gì, vì sao, khi nào thành công và những trường hợp nào phải từ chối**. Bài thực hành sử dụng hệ thống quản lý mượn sách thư viện làm ví dụ xuyên suốt. Các quy tắc cụ thể dưới đây là **giả định của bài tập**; khi làm dự án thật, phải xác nhận với người có quyền quyết định nghiệp vụ.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Chuyển một mô tả mơ hồ thành **phạm vi dự án**, danh sách bên liên quan, yêu cầu chức năng và phi chức năng.
2. Phân biệt **nhu cầu của người dùng**, **quy tắc nghiệp vụ**, **use case**, **tiêu chí nghiệm thu** và **thiết kế class**.
3. Viết đặc tả use case gồm tác nhân, kích hoạt, tiền điều kiện, luồng chính, luồng ngoại lệ, hậu điều kiện.
4. Phát hiện yêu cầu còn thiếu hoặc mâu thuẫn bằng cách đặt câu hỏi và khảo sát các tình huống biên.
5. Từ yêu cầu suy ra mô hình đối tượng Java sơ bộ, kiểm tra tính nhất quán và lập danh sách test trước khi lập trình.

**Đầu ra mong đợi:** tài liệu phạm vi, bảng yêu cầu có mã định danh, danh sách quy tắc nghiệp vụ, sơ đồ use case, ít nhất hai đặc tả use case chi tiết, mô hình miền sơ bộ, bảng truy vết yêu cầu–kiểm thử và các vấn đề cần xác nhận.

## 2. Bài toán và phạm vi

Thư viện của một trung tâm đào tạo đang ghi sổ giấy. Nhân viên khó biết một **bản sách cụ thể** còn cho mượn được hay không, người nào đang mượn và khi nào phải trả. Trung tâm muốn có một ứng dụng Java cơ bản để giảm việc ghi trùng và kiểm tra quy định mượn/trả thống nhất.

**Mục tiêu nghiệp vụ:** nhân viên có thể tra cứu bản sách; ghi nhận mượn và trả chính xác; xem danh sách khoản mượn còn hiệu lực. Mỗi giao dịch phải có kết quả rõ ràng và không làm mất lịch sử.

**Trong phạm vi phiên bản đầu tiên (MVP):**

- Tra cứu đầu sách, các bản sách và trạng thái sẵn có.
- Tra cứu thành viên đã đăng ký; kiểm tra trạng thái tài khoản.
- Tạo lượt mượn cho một bản sách; tính ngày hẹn trả.
- Trả sách; cập nhật trạng thái bản sách và đóng lượt mượn.
- Xem danh sách lượt mượn đang hoạt động của thành viên.

**Ngoài phạm vi phiên bản đầu:** thanh toán phí trễ, đặt chỗ, gửi email/SMS, nhập sách hàng loạt, đăng ký tài khoản trực tuyến, quản lý nhiều chi nhánh. Những mục này có thể được đưa vào backlog sau khi xác nhận nhu cầu.

**Dữ liệu mẫu:** có hai đầu sách “Java căn bản” và “OOP thực hành”; đầu sách đầu tiên có hai bản riêng biệt mang mã BS-001 và BS-002. Thành viên TV-001 đang hoạt động, TV-002 bị khóa. Tách *đầu sách* khỏi *bản sách* ngay từ bước phân tích để tránh nhầm lẫn: một đầu sách có thể có nhiều bản với trạng thái mượn khác nhau.

## 3. Xác định bên liên quan và khai thác yêu cầu

| Bên liên quan | Mục tiêu hoặc mối quan tâm | Câu hỏi nên phỏng vấn |
|---|---|---|
| Nhân viên thư viện (tác nhân chính) | Xử lý mượn/trả nhanh, biết vì sao giao dịch bị từ chối | Ai được tạo giao dịch? Khi mất mạng phải xử lý thế nào? |
| Thành viên (người hưởng lợi) | Biết sách có sẵn, hạn trả, lịch sử mượn | Được mượn tối đa bao nhiêu? Nếu trả trễ thì sao? |
| Quản lý thư viện | Bảo toàn dữ liệu, thống kê tình trạng mượn | Quy định nào được ưu tiên? Ai được phép thay đổi chính sách? |
| Người phát triển/kiểm thử | Có điều kiện rõ ràng để xây dựng và kiểm chứng | “Còn sách”, “quá hạn”, “trả thành công” nghĩa chính xác là gì? |
| Hệ thống lưu trữ/đồng hồ | Cung cấp trạng thái và ngày hiện tại | Ngày được tính theo múi giờ nào? Cần chống ghi trùng ra sao? |

Đừng hỏi chung chung “Anh/chị muốn chức năng gì?”. Hãy đề nghị nhân viên mô tả một giao dịch thực tế, trường hợp bị từ chối, cách sửa sai và chứng từ cần giữ. Quan sát quy trình hiện tại, kiểm tra biểu mẫu, rồi **ghi lại giả định chưa được xác nhận**. Kết quả phỏng vấn phải trở thành yêu cầu có thể kiểm tra, thay vì những tính từ mơ hồ như “nhanh”, “dễ dùng”, “ổn định”.

Ví dụ làm rõ yêu cầu: “Một người chỉ được mượn 3 cuốn” còn mơ hồ. Cần hỏi đó là **3 bản sách đang mượn cùng lúc** hay 3 lượt trong tháng; đúng 3 có được mượn cuốn thứ tư không; sách quá hạn có bị khóa mượn tiếp không. Trong ví dụ này, chọn tối đa 3 lượt **đang mở**, lượt thứ tư bị từ chối.

## 4. Đặc tả yêu cầu có thể kiểm chứng

### 4.1. Yêu cầu chức năng (Functional Requirements)

| ID | Yêu cầu | Điều kiện nghiệm thu cốt lõi | Ưu tiên |
|---|---|---|---|
| FR-01 | Tra cứu đầu sách và bản sách | Hiện đúng mã bản sách và trạng thái sẵn có | Must |
| FR-02 | Tra cứu thành viên | Tìm được thành viên theo mã, biết hoạt động/khóa | Must |
| FR-03 | Ghi nhận mượn một bản sách | Thỏa quy tắc thì tạo đúng một lượt mượn, đặt bản sách thành đang mượn | Must |
| FR-04 | Từ chối lượt mượn không hợp lệ | Trả lý do cụ thể; không thay đổi trạng thái hay tạo lượt mượn | Must |
| FR-05 | Ghi nhận trả sách | Đóng đúng lượt mượn, đặt bản sách thành sẵn có | Must |
| FR-06 | Xem lượt mượn đang mở | Hiển thị thành viên, mã bản sách, ngày mượn, hạn trả | Must |
| FR-07 | Xem lịch sử mượn/trả | Các giao dịch đã trả vẫn tra cứu được | Should |
| FR-08 | Báo cáo sách quá hạn | Lọc các lượt chưa trả có ngày hiện tại sau hạn trả | Could |

“Must / Should / Could” là thứ tự ưu tiên cho phạm vi thực hiện, **không phải** thứ tự gọi hàm Java. Mỗi yêu cầu nên có mã ổn định, người xác nhận và tiêu chí nghiệm thu đi kèm.

### 4.2. Quy tắc nghiệp vụ (Business Rules)

| ID | Quy tắc áp dụng cho bài tập | Ví dụ ranh giới |
|---|---|---|
| BR-01 | Chỉ thành viên đang hoạt động mới được mượn | TV-002 bị khóa → từ chối |
| BR-02 | Mỗi thành viên có tối đa 3 lượt mượn chưa trả tại một thời điểm | Có đúng 3 → từ chối lượt thứ tư |
| BR-03 | Chỉ bản sách trạng thái AVAILABLE mới được mượn | BS-001 đang được mượn → từ chối, dù BS-002 có thể còn |
| BR-04 | Không cho mượn mới nếu thành viên có ít nhất một lượt quá hạn | Hạn trả hôm qua, chưa trả → từ chối |
| BR-05 | Hạn trả = ngày mượn + 14 ngày theo lịch | Mượn ngày 01/03 → hạn 15/03 |
| BR-06 | Mỗi lượt mượn chỉ được trả thành công một lần | Nhấn trả lần hai → từ chối, không ghi trùng |
| BR-07 | Ngày trả không được trước ngày mượn | Ngày trả 05/03, ngày mượn 06/03 → lỗi |
| BR-08 | Quá hạn khi chưa trả và **ngày hiện tại > ngày hẹn trả** | Đúng ngày hẹn trả thì chưa quá hạn |

Các chính sách này cần xác nhận trước khi chuyển thành cấu hình cố định. Đừng tự ý quy định tiền phạt, ngày nghỉ, hoặc gia hạn khi người dùng chưa đưa ra yêu cầu.

### 4.3. Yêu cầu phi chức năng (Non-functional Requirements)

| ID | Thuộc tính chất lượng | Cách kiểm chứng đề xuất |
|---|---|---|
| NFR-01 | Toàn vẹn dữ liệu | Hai yêu cầu mượn đồng thời cùng một bản sách không thể đều thành công |
| NFR-02 | Tính nhất quán | Giao dịch thất bại không để bản sách ở trạng thái đang mượn mà thiếu lượt mượn |
| NFR-03 | Khả năng sử dụng | Lỗi hiển thị rõ mã thành viên/bản sách liên quan và lý do từ chối |
| NFR-04 | Khả năng kiểm thử | Logic chính sách tách khỏi giao diện; ngày hiện tại được truyền vào/qua Clock |
| NFR-05 | Tính bảo trì | Có thể đổi giới hạn mượn hoặc thời hạn mượn mà không sửa nhiều nơi |

**Lưu ý:** số mili giây đáp ứng, số người dùng đồng thời, cơ chế đăng nhập và thời gian lưu lịch sử phải do bên liên quan xác nhận, không nên tự đặt con số để tạo vẻ “đầy đủ”.

## 5. Nhận diện tác nhân và tình huống sử dụng

**Actor (tác nhân)** là vai trò tương tác với hệ thống, không nhất thiết tương đương một class Java. Trong MVP, **Nhân viên thư viện** là tác nhân chính thao tác giao dịch thay cho thành viên; **Thành viên** là người có dữ liệu được xử lý và người hưởng lợi. Nếu sau này có cổng tự phục vụ, Thành viên mới trở thành tác nhân trực tiếp.

| Mã | Use case | Tác nhân chính | Kết quả mong muốn |
|---|---|---|---|
| UC-01 | Tra cứu bản sách | Nhân viên | Biết bản nào hiện có thể cho mượn |
| UC-02 | Cho thành viên mượn sách | Nhân viên | Một lượt mượn được tạo hợp lệ |
| UC-03 | Nhận trả sách | Nhân viên | Đúng lượt mượn được đóng |
| UC-04 | Xem các lượt mượn còn mở | Nhân viên | Có danh sách và hạn trả chính xác |

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

Sơ đồ thể hiện **mục tiêu người dùng và ranh giới hệ thống**, chưa phải sơ đồ các lớp, cũng không quy định màn hình hay API. Nên đặt tên use case theo **động từ + đối tượng**, tránh tên kỹ thuật như “gọi BorrowService” hoặc “ghi bảng loans”.

## 6. Đặc tả chi tiết UC-02 — Cho mượn bản sách

| Thuộc tính | Nội dung |
|---|---|
| ID / Tên | UC-02 — Cho thành viên mượn một bản sách |
| Tác nhân chính | Nhân viên thư viện |
| Kích hoạt | Thành viên yêu cầu mượn một bản có mã xác định |
| Đầu vào | memberId, copyId, ngày giao dịch |
| Tiền điều kiện | Nhân viên có quyền thao tác; mã thành viên và mã bản sách tồn tại |
| Hậu điều kiện thành công | Tạo một Loan đang mở; bản sách chuyển sang ON_LOAN; lưu hạn trả |
| Hậu điều kiện thất bại | Không tạo Loan; trạng thái bản sách và các lượt mượn không đổi |
| Quy tắc liên quan | BR-01 đến BR-05; NFR-01, NFR-02 |

**Luồng thành công:**

1. Nhân viên nhập mã thành viên và quét mã bản sách.
2. Hệ thống tìm thành viên và bản sách; cho xem thông tin để xác nhận.
3. Hệ thống kiểm tra thành viên đang hoạt động, số lượt mượn đang mở, lượt quá hạn và trạng thái của **đúng bản sách đó**.
4. Hệ thống tính ngày hẹn trả bằng ngày giao dịch cộng 14 ngày.
5. Hệ thống lưu lượt mượn, cập nhật trạng thái bản sách như **một giao dịch nhất quán**.
6. Hệ thống trả kết quả gồm mã lượt mượn, mã bản sách và ngày hẹn trả.

**Luồng thay thế và lỗi:**

- **A1 – Thành viên không tồn tại:** thông báo “Không tìm thấy thành viên”; không tạo dữ liệu.
- **A2 – Bản sách không tồn tại:** thông báo “Không tìm thấy bản sách”; không tạo dữ liệu.
- **A3 – Thành viên bị khóa (BR-01):** từ chối mượn.
- **A4 – Đã đủ 3 lượt đang mở (BR-02):** từ chối mượn.
- **A5 – Có lượt quá hạn (BR-04):** từ chối mượn, gợi ý xử lý khoản quá hạn.
- **A6 – Bản sách đang được mượn (BR-03):** từ chối; có thể tìm bản khác cùng đầu sách.
- **A7 – Hai nhân viên cùng mượn một bản:** chỉ một giao dịch được ghi thành công; giao dịch còn lại nhận lỗi xung đột.
- **A8 – Lỗi lưu trữ:** toàn bộ thay đổi phải được hủy; không để Loan và BookCopy lệch trạng thái.

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

**Điểm dễ sai:** nếu hệ thống đọc “AVAILABLE”, rồi hai luồng cùng ghi Loan mà không có kiểm soát đồng thời, một bản sách có thể bị cho mượn hai lần. Yêu cầu NFR-01 phải được giải quyết bằng transaction cùng ràng buộc dữ liệu/khóa hoặc cập nhật có điều kiện khi triển khai kho lưu trữ thật; kiểm tra bằng câu lệnh if trong RAM là chưa đủ.

## 7. Đặc tả chi tiết UC-03 — Nhận trả sách

| Thuộc tính | Nội dung |
|---|---|
| ID / Tên | UC-03 — Trả một lượt mượn |
| Tác nhân chính | Nhân viên thư viện |
| Đầu vào | loanId, ngày trả |
| Tiền điều kiện | Loan tồn tại, đang mở; ngày trả không trước ngày mượn |
| Hậu điều kiện thành công | Loan có returnedAt, bản sách AVAILABLE, lịch sử vẫn được giữ |
| Hậu điều kiện thất bại | Không thay đổi Loan hoặc BookCopy |
| Quy tắc liên quan | BR-06, BR-07; NFR-02 |

**Luồng chính:** (1) nhân viên xác định đúng lượt mượn đang mở; (2) hệ thống kiểm tra ngày trả và trạng thái; (3) hệ thống ghi ngày trả, chuyển bản sách về sẵn có trong cùng một giao dịch; (4) trả biên nhận thành công.

**Ngoại lệ:** mã lượt mượn không tồn tại; lượt đã trả; ngày trả trước ngày mượn; lỗi lưu trữ. Với lượt quá hạn, **vẫn cho trả** trong MVP; việc thu phí là ngoài phạm vi nên không chặn thao tác trả.

## 8. Từ ngôn ngữ nghiệp vụ đến mô hình đối tượng

Tách **danh từ miền** (Member, BookTitle, BookCopy, Loan) khỏi **hành vi phối hợp** (BorrowingService) và **hạ tầng** (LoanRepository, MemberRepository, CopyRepository). Một bản sách là đối tượng riêng; Loan đại diện cho một giao dịch cụ thể, không nên gắn ngày mượn trực tiếp lên BookTitle vì đầu sách có nhiều bản.

| Khái niệm | Thuộc tính trọng yếu | Trách nhiệm gợi ý |
|---|---|---|
| Member | id, active | Xác định thành viên và trạng thái tài khoản |
| BookTitle | isbn, title | Mô tả tác phẩm/đầu sách |
| BookCopy | id, bookTitle, status | Đại diện một bản vật lý, kiểm soát trạng thái |
| Loan | id, member, copy, borrowedOn, dueOn, returnedOn | Ghi vòng đời một lượt mượn |
| BorrowingPolicy | maxActiveLoans, loanDays | Cung cấp/chứng thực chính sách mượn |
| BorrowingService | repositories, policy, Clock | Thực thi UC-02 và UC-03, phối hợp lưu trữ |

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

**Phân biệt use case với class:** UC-02 là một **mục tiêu nghiệp vụ có nhiều bước**; nó có thể cần tương tác giữa Member, BookCopy, Loan, Policy và Repository. Không nên tạo một class cho mỗi dòng bước đi, hoặc xem mọi danh từ trong mô tả là entity bắt buộc.

Thiết kế OOP sơ bộ có thể thay đổi khi xác thực yêu cầu. Chỉ khai báo thuộc tính thực sự cần cho hành vi; dùng **encapsulation** để tránh mã ngoài tự thay đổi trạng thái; phân chia trách nhiệm theo **single responsibility**; truy cập dữ liệu qua interface nếu ứng dụng cần thay được loại lưu trữ.

## 9. Mẫu Java 17 minh họa cách mã hóa quy tắc

Đây là **mô phỏng trong bộ nhớ** để thấy mối quan hệ giữa yêu cầu và kiểm tra nghiệp vụ. Nó chưa có xác thực nhân viên, cơ sở dữ liệu, transaction hoặc an toàn đồng thời. Lưu thành **LibraryDemo.java** và chạy bằng Java 17+.

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

**Tại sao mã ví dụ chưa phải sản phẩm hoàn chỉnh?** Nó so sánh Member bằng tham chiếu đối tượng vì dùng đúng instance trong bộ nhớ; dữ liệu thực cần so sánh bằng **id định danh ổn định**. Kho Loan trong RAM không bền sau khi tắt ứng dụng; cập nhật Loan rồi BookCopy có thể sai lệch nếu lỗi xảy ra giữa chừng. Khi triển khai thật, nên giao việc lưu cho repository, gói thay đổi vào transaction và đảm bảo chỉ một tác nhân đặt được bản sách từ AVAILABLE sang ON_LOAN. Các rủi ro này đã được đặt thành NFR ngay từ lúc phân tích.

## 10. Tình huống nghiệm thu và kiểm thử

Dưới đây là **đặc tả test từ nghiệp vụ**, có thể dùng cho JUnit sau này. Để test ổn định, truyền ngày kiểm thử cố định hoặc dùng Clock được tiêm vào, không phụ thuộc LocalDate.now() trực tiếp.

| Test ID | Yêu cầu liên quan | Given (ban đầu) | When (hành động) | Then (kỳ vọng) |
|---|---|---|---|---|
| T-01 | FR-03, BR-05 | TV-001 hoạt động, BS-001 AVAILABLE, không nợ sách | Mượn ngày 01/03/2026 | Loan mở, hạn 15/03/2026, bản ON_LOAN |
| T-02 | FR-04, BR-01 | Thành viên bị khóa | Mượn BS-001 | MEMBER_INACTIVE, không tạo Loan |
| T-03 | FR-04, BR-02 | Thành viên đã có đúng 3 Loan mở | Mượn thêm bản thứ tư | LIMIT_REACHED, mọi dữ liệu cũ giữ nguyên |
| T-04 | FR-04, BR-03 | BS-001 ON_LOAN | Mượn BS-001 lần nữa | COPY_UNAVAILABLE, không tạo Loan |
| T-05 | FR-04, BR-04, BR-08 | Có Loan mở hạn 14/03 | Mượn ngày 15/03 | OVERDUE_LOAN |
| T-06 | FR-03, BR-08 | Có Loan mở hạn 15/03, không có nợ khác | Mượn ngày 15/03 nếu chưa đạt giới hạn | Không bị chặn vì quá hạn |
| T-07 | FR-05, BR-06 | Loan đang mở | Trả ngày hợp lệ hai lần | Lần đầu thành công; lần sau LOAN_ALREADY_RETURNED |
| T-08 | FR-05, BR-07 | Loan mượn ngày 06/03 | Trả ngày 05/03 | RETURN_BEFORE_BORROW, Loan vẫn mở |
| T-09 | NFR-01 | Một bản AVAILABLE, hai yêu cầu đồng thời | Cùng mượn một copyId | Chính xác một Loan được ghi |
| T-10 | NFR-02 | Kho lưu xảy ra lỗi giữa quá trình mượn | Giao dịch thất bại | Không ghi Loan dở dang hay đổi trạng thái bản sách |

Một kịch bản viết theo cú pháp gần với **Gherkin**:

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

Một test tốt kiểm tra **cả kết quả lẫn bất biến dữ liệu khi thất bại**. Đừng chỉ assert có exception: nếu hàm ném lỗi sau khi đã đổi trạng thái sách thì nghiệp vụ vẫn sai.

## 11. Truy vết yêu cầu → use case → lớp → kiểm thử

| Quy tắc/yêu cầu | Use case | Nơi dự kiến xử lý trong OOP | Test |
|---|---|---|---|
| FR-01 | UC-01 | BookTitle, BookCopy, CatalogService | Test tra cứu theo copyId |
| FR-03, BR-01, BR-02 | UC-02 | BorrowingService, Member, BorrowingPolicy | T-01, T-02, T-03 |
| FR-04, BR-03, BR-04 | UC-02 | BookCopy, Loan, BorrowingService | T-04, T-05, T-06 |
| FR-03, BR-05 | UC-02 | Loan, BorrowingPolicy | T-01 |
| FR-05, BR-06, BR-07 | UC-03 | Loan, BookCopy, BorrowingService | T-07, T-08 |
| NFR-01, NFR-02 | UC-02 / UC-03 | Repository, transaction, ràng buộc lưu trữ | T-09, T-10 |

Bảng truy vết giúp trả lời ba câu hỏi quan trọng: **Yêu cầu này được thực hiện ở đâu? Được kiểm tra bằng gì? Nếu đổi quy tắc, những thành phần nào bị ảnh hưởng?** Chẳng hạn, nếu giới hạn từ 3 lên 5, sửa chính sách và cập nhật T-03; không sửa hàng loạt class giao diện.

## 12. Quy trình thực hành theo nhóm

1. **Thu thập:** mỗi người phỏng vấn một vai trò; tổng hợp 5–10 tình huống mượn/trả thực tế, gồm trường hợp thất bại.
2. **Đặt phạm vi:** chốt MVP, ngoài phạm vi và giả định. Gắn mã FR, NFR, BR. Mỗi câu phải có tiêu chí kiểm chứng.
3. **Đặc tả:** vẽ sơ đồ use case và mô tả đầy đủ UC-02, UC-03. Kiểm tra tiền điều kiện, luồng ngoại lệ, hậu điều kiện.
4. **Phân tích đối tượng:** liệt kê entity, value object, service và kho dữ liệu; vẽ class diagram sơ bộ; gán trách nhiệm theo các quy tắc nghiệp vụ.
5. **Kiểm thử trước thiết kế chi tiết:** viết bảng Given–When–Then với ranh giới, dữ liệu sai, lặp giao dịch, đồng thời và lỗi lưu trữ.
6. **Review cùng bên liên quan:** trình bày ví dụ thực tế, xin xác nhận quy tắc và các quyết định còn mở; chỉ sau đó mới chia task triển khai.

**Checklist trước khi chuyển sang lập trình:**

- [ ] Mỗi yêu cầu chức năng có mã ID, tác nhân, đầu vào và kết quả quan sát được.
- [ ] “Đầu sách” và “bản sách” được phân biệt; mỗi Loan gắn đúng một bản sách.
- [ ] Giới hạn 3, hạn 14 ngày, định nghĩa quá hạn và trạng thái bị khóa đã được xác nhận.
- [ ] UC-02/UC-03 có cả luồng thành công, lỗi và hậu điều kiện không làm hỏng dữ liệu.
- [ ] Các trường hợp đúng giới hạn, vượt giới hạn và trả hai lần đều có test.
- [ ] Yêu cầu về lưu trữ, transaction và truy cập đồng thời đã được ghi rõ.
- [ ] Có bảng truy vết từ yêu cầu đến use case, thành phần dự kiến và kiểm thử.
- [ ] Không còn yêu cầu quan trọng chỉ mô tả bằng từ mơ hồ như “nhanh”, “tốt”, “an toàn”.

## 13. Bài tập mở rộng và tự đánh giá

**Bài A — Phân tích thay đổi:** quản lý cho phép mỗi thành viên mượn tối đa **5 bản**, nhưng tài liệu tham khảo chỉ mượn **7 ngày**. Hãy xác định các FR/BR, use case, lớp và test cần cập nhật. Thảo luận liệu thời hạn mượn nên là thuộc tính cố định của Loan hay do Policy tính khi tạo Loan (gợi ý: lưu **dueOn đã chốt** trong Loan để thay đổi chính sách về sau không tự thay đổi hạn trả của giao dịch cũ).

**Bài B — Làm rõ yêu cầu:** khi quá hạn, thành viên có được trả sách trực tiếp không? Khi trả vào đúng ngày hạn thì hệ thống báo quá hạn hay chưa? Nếu sách bị mất, hệ thống có cho “trả” không? Viết câu hỏi phỏng vấn thay vì tự suy diễn.

**Bài C — Phát hiện lỗi thiết kế:** có đề xuất đặt biến boolean borrowed vào BookTitle và tạo Loan mà không gắn copyId. Hãy nêu ít nhất ba tình huống khiến mô hình này thất bại, rồi chỉnh lại sơ đồ miền.

**Tiêu chí tự đánh giá:** người khác có thể đọc README, dựng lại đúng luồng nghiệp vụ, viết test mà không phải đoán ý; mỗi quy tắc có trường hợp biên; mô hình lớp phục vụ yêu cầu thực tế thay vì được tạo tùy tiện; những quyết định chưa được xác nhận được nêu minh bạch.

---

**Ghi nhớ:** phân tích yêu cầu trả lời **“hệ thống phải làm gì và thế nào là đúng”**; tình huống sử dụng trả lời **“ai tương tác, tương tác khi nào và những nhánh nào có thể xảy ra”**; thiết kế hướng đối tượng mới trả lời **“đối tượng nào giữ dữ liệu và chịu trách nhiệm thực hiện hành vi đó”**. Đi từ yêu cầu có thể kiểm thử đến use case rõ ràng sẽ giúp dự án Java OOP tránh được sai lệch nghiệp vụ ngay từ đầu.