# Truyền `Clock` vào lớp nghiệp vụ

## 1. Lớp nghiệp vụ dùng thời gian, nơi khởi tạo chọn nguồn thời gian

Một dịch vụ mượn sách cần ghi nhận lúc phát hành phiếu, xác định ngày mượn và tính ngày trả. Nếu dịch vụ tự gọi `Instant.now()` hoặc `LocalDate.now()` ở bên trong, nguồn thời gian trở thành chi tiết bị giấu. Kiểm thử không dễ đặt dịch vụ vào một ngày cụ thể, còn quy tắc vùng có thể phụ thuộc máy đang chạy.

Truyền `Clock` vào lớp nghĩa là cung cấp nguồn thời gian như một phụ thuộc rõ ràng. Lớp vẫn thực hiện cùng nghiệp vụ; nơi lắp đối tượng quyết định dùng đồng hồ hệ thống khi chạy thật hay đồng hồ cố định khi kiểm thử.

[Java SE 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) mô tả cách dùng nguồn giờ có thể thay thế và truyền nó vào phần mã cần “hiện tại”. Không bắt buộc phải có một khung tiêm phụ thuộc: hàm khởi tạo Java bình thường đã thực hiện được việc này.

```text
Nơi khởi tạo
    chọn Clock và cấu hình vùng
                 ↓
Lớp nghiệp vụ nhận phụ thuộc
    đọc mốc → áp quy tắc → trả kết quả
```

Điểm thay đổi là ai sở hữu quyết định chọn nguồn giờ, không phải thêm nhánh “nếu đang kiểm thử” vào thuật toán.

## 2. Thiết kế hàm khởi tạo

Một cấu trúc thường dùng là nhận `Clock` bắt buộc và giữ trong trường `final`:

```java
// Minh họa cấu trúc trong một lớp, chưa phải chương trình độc lập.
private final Clock clock;

LoanService(Clock clock) {
    this.clock = Objects.requireNonNull(clock);
}
```

Hàm khởi tạo thể hiện rằng lớp cần nguồn thời gian để làm việc. `requireNonNull()` từ chối cấu hình thiếu sớm; `final` tránh việc một thao tác khác âm thầm thay nguồn giờ sau khi đối tượng đã được tạo.

Cách này không buộc lớp nhận `Clock.fixed()` trực tiếp. Nó chỉ nhận hợp đồng `Clock`; đồng hồ cụ thể được chọn ở nơi khởi tạo. Một clock hệ thống vẫn tiếp tục chạy dù trường tham chiếu là `final`: `final` không có nghĩa thời gian bị đóng băng.

Nếu một lớp chỉ tính toán từ một mốc đã được cung cấp, có thể không cần giữ `Clock`. Chẳng hạn, một hàm thuần túy nhận ngày mượn rồi tính ngày trả sẽ dễ kiểm thử trực tiếp. Đặt nguồn đồng hồ ở lớp thật sự có trách nhiệm quyết định lúc nào lấy “hiện tại”, thay vì truyền nó qua mọi hàm chỉ để phục vụ một phép cộng ngày.

## 3. Thời điểm và vùng nghiệp vụ phải có vai trò rõ ràng

`Clock` có cả `instant()` và `getZone()`. Có hai cách tổ chức hợp lý tùy hợp đồng:

| Cách tổ chức | Cách đọc ngày | Khi nào phù hợp |
| --- | --- | --- |
| Vùng của clock chính là vùng nghiệp vụ | `LocalDate.now(clock)` | Nguồn giờ và vùng luôn được cấu hình cùng nhau |
| Nguồn mốc và vùng nghiệp vụ được cung cấp riêng | Đọc một `Instant`, rồi `LocalDate.ofInstant(instant, businessZone)` | Cần tách nguồn giờ chung khỏi vùng của đơn vị nghiệp vụ |

Chương trình trong bài chọn cách thứ hai. `Clock` cung cấp thời điểm, còn `businessZone` xác định ngày của thư viện. Vì vậy, clock kiểm thử có thể mang vùng UTC nhưng ngày mượn vẫn được tính theo `Asia/Ho_Chi_Minh` đã truyền riêng.

[Java SE 21 — LocalDate.ofInstant()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#ofInstant(java.time.Instant,java.time.ZoneId)) thực hiện việc lấy ngày từ thời điểm và vùng cụ thể. Đây không phải phép sửa thời điểm; một thời điểm có thể thuộc hai ngày khác nhau khi nhìn theo hai vùng.

Không cần truyền hai cấu hình vùng nếu thiết kế đã chọn vùng trong clock làm nguồn duy nhất. Điều cần tránh là mã vừa đọc `LocalDate.now(clock)` ở một chỗ, vừa chuyển theo một vùng khác ở chỗ khác mà không có hợp đồng rõ ràng.

## 4. Quy tắc của ví dụ dịch vụ mượn sách

Ví dụ chỉ tính thông tin phiếu, với hợp đồng:

- Mã sách phải có nội dung.
- `issuedAt` là một thời điểm quan sát từ clock.
- `borrowedOn` là ngày tại thư viện theo `businessZone` từ chính thời điểm ấy.
- `dueOn` là ngày mượn cộng 14 ngày lịch.

Ví dụ không lưu kho dữ liệu và không thực hiện trừ số lượng sách; nó cô lập phần phụ thuộc thời gian để quan sát. “Cộng 14 ngày” ở đây có nghĩa `plusDays(14)`, không tự thêm lịch nghỉ hoặc quy tắc ngày làm việc.

## 5. Chương trình chạy đầy đủ

Lưu mã vào `BusinessClockDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Các kỳ vọng sai sẽ ném `AssertionError`, không cần bật `-ea`:

```java
import java.time.*;
import java.util.Objects;

public class BusinessClockDemo {
    record LoanReceipt(String bookId, Instant issuedAt,
                       LocalDate borrowedOn, LocalDate dueOn) {}

    static final class LoanService {
        private final Clock clock;
        private final ZoneId businessZone;

        LoanService(Clock clock, ZoneId businessZone) {
            this.clock = Objects.requireNonNull(clock);
            this.businessZone = Objects.requireNonNull(businessZone);
        }

        LoanReceipt borrow(String bookId) {
            Objects.requireNonNull(bookId);
            if (bookId.isBlank()) {
                throw new IllegalArgumentException("bookId is blank");
            }
            Instant observedNow = clock.instant();
            LocalDate borrowedOn = LocalDate.ofInstant(observedNow, businessZone);
            LocalDate dueOn = borrowedOn.plusDays(14);
            return new LoanReceipt(bookId, observedNow, borrowedOn, dueOn);
        }
    }

    private static void expect(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        Instant observed = Instant.parse("2025-12-31T18:00:00Z");
        Clock testClock = Clock.fixed(observed, ZoneOffset.UTC);
        ZoneId libraryZone = ZoneId.of("Asia/Ho_Chi_Minh");
        LoanService service = new LoanService(testClock, libraryZone);
        LoanReceipt receipt = service.borrow("BOOK-42");

        expect("BOOK-42", receipt.bookId(), "book");
        expect(observed, receipt.issuedAt(), "issuedAt");
        expect(LocalDate.of(2026, 1, 1), receipt.borrowedOn(), "borrowedOn");
        expect(LocalDate.of(2026, 1, 15), receipt.dueOn(), "dueOn");
        expect(receipt, service.borrow("BOOK-42"), "same inputs");

        LoanService utcLibrary = new LoanService(testClock, ZoneOffset.UTC);
        LoanReceipt utcReceipt = utcLibrary.borrow("BOOK-42");
        expect(LocalDate.of(2025, 12, 31), utcReceipt.borrowedOn(), "UTC date");
        expect(LocalDate.of(2026, 1, 14), utcReceipt.dueOn(), "UTC dueOn");

        Clock laterClock = Clock.fixed(
                Instant.parse("2026-01-01T18:00:00Z"), ZoneOffset.UTC);
        LoanReceipt later = new LoanService(laterClock, libraryZone)
                .borrow("BOOK-42");
        expect(LocalDate.of(2026, 1, 2), later.borrowedOn(), "later date");
        expect(LocalDate.of(2026, 1, 16), later.dueOn(), "later dueOn");
        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BusinessClockDemo.java
java BusinessClockDemo
```

Kết quả:

```text
book = BOOK-42
issuedAt = 2025-12-31T18:00:00Z
borrowedOn = 2026-01-01
dueOn = 2026-01-15
same inputs = LoanReceipt[bookId=BOOK-42, issuedAt=2025-12-31T18:00:00Z, borrowedOn=2026-01-01, dueOn=2026-01-15]
UTC date = 2025-12-31
UTC dueOn = 2026-01-14
later date = 2026-01-02
later dueOn = 2026-01-16
all checks passed
```

`LoanReceipt` là một `record` dùng để mang kết quả. Việc so sánh hai phiếu trong dòng `same inputs` chỉ kiểm chứng cùng dữ liệu và cùng mốc của phép tính không có tác dụng phụ trong bài cho cùng kết quả. Nó không có nghĩa một nghiệp vụ mượn sách thực tế được phép thực hiện hai lần hoặc đã có cơ chế chống trùng.

## 6. Vì sao chỉ đọc clock một lần trong `borrow()`?

`observedNow` được dùng cho cả `issuedAt` và phép suy ra `borrowedOn`. Hai thông tin vì vậy mô tả cùng một lần quan sát. Nếu gọi `clock.instant()` để lấy thời điểm rồi lại gọi nguồn giờ khác để lấy ngày, hai bước có thể nằm hai phía của nửa đêm khi chạy thật.

Clock cố định giúp kiểm thử lặp lại, còn cách lấy một mốc giúp thao tác chạy thật có tính nhất quán theo hợp đồng. Hai lợi ích liên quan nhưng không thay thế cho nhau.

Không nên đọc “hiện tại” ngay trong hàm khởi tạo rồi giữ mãi như ngày của mọi lần mượn. Một dịch vụ có thể sống qua nhiều ngày; cần đọc clock ở thời điểm xử lý nghiệp vụ nếu quy tắc là dùng ngày của từng thao tác.

Ngược lại, khi yêu cầu một chuỗi thao tác dùng chung mốc đã được chốt ở đầu yêu cầu, lớp ngoài có thể đọc một lần rồi truyền `Instant` ấy xuống các hàm tính toán. Mốc quan sát phải được đặt ở ranh giới có ý nghĩa, không tự thay đổi chỉ vì thuận tiện khi viết mã.

## 7. Lắp nguồn giờ chạy thật và nguồn giờ kiểm thử

Khi khởi tạo mã chạy thật, có thể viết trong cùng phạm vi truy cập được lớp ví dụ:

```java
Clock productionClock = Clock.systemUTC();
ZoneId libraryZone = ZoneId.of("Asia/Ho_Chi_Minh");
LoanService production = new LoanService(productionClock, libraryZone);
```

Nguồn `systemUTC()` cung cấp thời gian hệ thống. Do lớp đã chọn vùng nghiệp vụ riêng, vùng của clock không được dùng để suy ra ngày mượn. Nếu chọn thiết kế chỉ nhận clock và dùng vùng của nó, nơi khởi tạo có thể cấp `Clock.system(libraryZone)` thay cho cách trên.

Khi kiểm thử, `Clock.fixed()` cung cấp đúng mốc cần thử. Chương trình tạo một clock cho thời điểm cuối năm và một clock khác cho ngày sau đó; không cần đổi đồng hồ toàn máy, chờ sang ngày mới hoặc thay thuật toán trong `LoanService`.

Nếu ứng dụng dùng một khung quản lý phụ thuộc, cấu hình ngoài lớp có thể tạo nguồn giờ rồi truyền qua hàm khởi tạo giống như các phụ thuộc khác. Bản thân lớp nghiệp vụ không cần biết ai khởi tạo nó và không cần tải cấu hình môi trường để quyết định đang chạy kiểm thử hay chạy thật.

## 8. Các lỗi khiến việc truyền `Clock` không còn hiệu quả

**Nhận clock nhưng không dùng.** Một nhánh vẫn gọi `Instant.now()` không đối số thì mốc của nhánh đó không được kiểm soát bởi clock đã cấp. Cần theo dõi tất cả những điểm lấy “hiện tại” liên quan đến kết quả đang kiểm tra.

**Tự tạo clock hệ thống bên trong phương thức.** `Clock.systemUTC().instant()` ở trong `borrow()` vẫn gắn cứng với nguồn thật. Tạo clock ở nơi lắp đối tượng mới làm rõ quyền thay nguồn.

**Dùng biến clock toàn cục có thể thay đổi.** Các kiểm thử hoặc yêu cầu chạy song song có thể ảnh hưởng nhau khi ghi đè nguồn giờ. Cung cấp phụ thuộc cho đối tượng phù hợp giúp phạm vi cấu hình rõ ràng hơn.

**Lưu `now` thành hằng lúc khởi động.** Nó tạo một mốc cũ chứ không cung cấp một nguồn giờ đang chạy. Giữ clock để đọc khi cần; chỉ giữ một `Instant` cố định khi nghiệp vụ thật sự muốn chốt mốc đó.

**Trộn ngày lịch với thời lượng.** Hạn trả trong bài là ngày lịch cộng 14 ngày. Nếu quy định yêu cầu chính xác một số giây kể từ lúc phát hành, phải mô hình hóa bằng thời điểm/thời lượng tương ứng. Việc đã truyền Clock không tự quyết định đúng đơn vị nghiệp vụ.

## 9. Kiểm tra hành vi của lớp, không chỉ kiểm tra clock

Các kỳ vọng trong chương trình xác nhận thông tin phiếu: dấu thời gian, ngày mượn, ngày trả. Trường hợp cuối năm giúp thấy rõ ảnh hưởng vùng; trường hợp clock khác giúp xác nhận mỗi lần xử lý dùng nguồn đã cấp thay vì mốc được chụp lúc viết chương trình.

Clock chỉ kiểm soát phần mã đọc nó. Nếu sau này thêm cơ sở dữ liệu tự tạo `CURRENT_TIMESTAMP`, một bộ lập lịch hoặc dịch vụ khác tự lấy giờ, cần biết nguồn ấy có thuộc phạm vi kiểm thử hiện tại hay không. Không có tác dụng tự động thay toàn bộ nguồn thời gian của ứng dụng chỉ bằng một tham số trong `LoanService`.

Bài tập: đổi thời hạn mượn thành 7 ngày lịch nhưng giữ nguyên mốc và vùng của phiếu đầu. Ngày mượn vẫn là `2026-01-01`, ngày trả phải là `2026-01-08`. Sau đó chỉ đổi clock sang thời điểm `2026-01-01T18:00:00Z`: ngày mượn tại thư viện thành `2026-01-02`. Giải thích được vì sao không cần sửa mã lấy giờ của lớp khi đổi kịch bản kiểm thử là bạn đã hiểu ranh giới trách nhiệm của Clock được truyền vào.
