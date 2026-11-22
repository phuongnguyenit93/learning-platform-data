# Clock cung cấp thời điểm hiện tại và múi giờ

## 1. “Bây giờ” gồm nguồn thời gian và cách hiểu ngày địa phương

Khi mã gọi `LocalDate.now()`, nó vừa phụ thuộc thời điểm đang chạy vừa phụ thuộc múi giờ mặc định của môi trường. Gần nửa đêm, cùng một thời điểm có thể đã sang ngày mới ở Việt Nam nhưng vẫn là ngày trước theo UTC.

`java.time.Clock` làm hai phụ thuộc này trở thành một đối tượng có thể truyền vào:

- **Nguồn thời điểm:** đồng hồ trả về `Instant` nào khi được hỏi?
- **Múi giờ:** dùng `ZoneId` nào khi chuyển thời điểm ấy thành ngày/giờ địa phương?

Nhờ đó, chức năng có thể đọc “bây giờ” từ một nguồn được cấu hình, còn kiểm thử có thể thay nguồn ấy bằng một đồng hồ được kiểm soát. Không cần phụ thuộc trực tiếp vào thời điểm máy thực sự chạy để kiểm tra một điều kiện ngày tháng.

`Clock` là lớp trừu tượng. Thông thường bạn dùng các phương thức tạo có sẵn rồi truyền nó vào nơi cần thời gian, thay vì tự viết một lớp đồng hồ ngay từ đầu.

## 2. Các phương thức cốt lõi

| Phương thức | Dữ liệu nhận được | Có cần múi giờ để hiểu kết quả không? |
|---|---|---|
| `clock.instant()` | Thời điểm dưới dạng `Instant` | Bản thân thời điểm không phụ thuộc múi giờ |
| `clock.millis()` | Số mili giây từ mốc epoch của đồng hồ | Không phải giờ địa phương; là biểu diễn số của thời điểm |
| `clock.getZone()` | Múi giờ dùng để tạo ngày/giờ | Chính là ngữ cảnh chuyển đổi |
| `clock.withZone(zone)` | Đồng hồ tương ứng với múi giờ khác | Đổi ngữ cảnh ngày/giờ, giữ nguồn thời điểm theo hợp đồng |

`Instant` xác định một điểm trên trục thời gian; không có “Instant theo giờ Việt Nam” khác với “Instant theo UTC” cho cùng một thời điểm. Khi in `Instant`, Java thường dùng hậu tố `Z`; điều đó không có nghĩa nó đã bỏ qua một múi giờ cần được cộng vào giá trị.

`millis()` chỉ giữ độ chính xác mili giây. Nếu cần phần nhỏ hơn mili giây mà nguồn hỗ trợ, dùng `instant()` thay vì chuyển qua `long` rồi tạo lại. Cũng không mặc định rằng một đồng hồ có API nanosecond thì nguồn phần cứng luôn chính xác tới nanosecond.

## 3. now(clock) dùng đồng hồ theo kiểu kết quả

Các kiểu chính của `java.time` có biến thể `now(Clock)`:

```java
Instant instant = Instant.now(clock);
LocalDate today = LocalDate.now(clock);
LocalDateTime local = LocalDateTime.now(clock);
ZonedDateTime zoned = ZonedDateTime.now(clock);
```

Đây là đoạn minh họa trong một phương thức có biến `clock`; chương trình độc lập ở phần 7.

- `Instant.now(clock)` lấy thời điểm; múi giờ của đồng hồ không làm thời điểm dịch đi.
- `LocalDate.now(clock)` dùng thời điểm và múi giờ của đồng hồ để xác định ngày, sau đó chỉ giữ phần ngày.
- `LocalDateTime.now(clock)` giữ ngày-giờ địa phương, không giữ thông tin múi giờ trong kiểu kết quả.
- `ZonedDateTime.now(clock)` giữ ngày-giờ, múi giờ và độ lệch tương ứng tại thời điểm ấy.

Bởi vậy, chọn `Clock.systemUTC()` rồi gọi `LocalDate.now(clock)` có nghĩa lấy **ngày hiện tại theo UTC**, không phải ngày của người dùng ở bất kỳ nơi nào. Nếu chức năng dựa trên ngày Việt Nam, cần cấu hình múi giờ phù hợp hoặc chuyển đổi theo múi giờ được xác định cho chức năng đó.

## 4. Chọn nguồn đồng hồ hệ thống một cách tường minh

Các lựa chọn thường gặp:

```java
Clock utc = Clock.systemUTC();
Clock vietnam = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock machineDefault = Clock.systemDefaultZone();
```

Đoạn này chỉ tạo ba cấu hình đồng hồ, không cam kết thời gian thực hiện tại sẽ là một giá trị cố định nào.

| Lựa chọn | Ý nghĩa phù hợp |
|---|---|
| `systemUTC()` | Nguồn hệ thống, ngữ cảnh UTC; thuận tiện khi chức năng chủ yếu cần thời điểm |
| `system(zone)` | Nguồn hệ thống, múi giờ được cấu hình rõ |
| `systemDefaultZone()` | Nguồn hệ thống với múi giờ mặc định của môi trường tại lúc tạo cấu hình đó |

Múi giờ mặc định có thể khác giữa máy phát triển, máy chủ và môi trường kiểm thử. Nếu kết quả nghiệp vụ phải theo một vùng cụ thể, dùng cấu hình rõ ràng thay vì ngầm dựa vào môi trường.

`Clock.system(zone)` dùng đồng hồ hệ thống sẵn có; nó không tự liên hệ máy chủ thời gian ở vùng đó. Đặt vùng `Asia/Ho_Chi_Minh` không làm máy đổi múi giờ, không đồng bộ lại giờ và không sửa một nguồn hệ thống đang bị lệch.

## 5. withZone đổi cách nhìn ngày/giờ, không cộng bảy giờ vào Instant

Với thời điểm `2026-10-24T18:30:00Z`:

```text
UTC:                  2026-10-24 18:30
Asia/Ho_Chi_Minh:      2026-10-25 01:30
```

Hai cách viết là cùng một thời điểm, nhưng ngày địa phương khác nhau. Có thể tạo một đồng hồ khác bằng `utc.withZone(...)` rồi so sánh các giá trị ngày.

`withZone` không sửa đồng hồ gốc. Cần dùng giá trị trả về, giống nhiều API bất biến của `java.time`. Với đồng hồ hệ thống đang chạy, hai lần đọc liên tiếp từ hai đồng hồ có thể khác nhau vì thời gian đã trôi giữa các lời gọi; đừng kiểm tra rằng chúng luôn bằng nhau từng nano giây rồi kết luận cấu hình múi giờ sai.

Ví dụ ở phần 7 dùng `Clock.fixed` để cùng một `Instant` được trả lại ở mọi lần đọc. Đồng hồ cố định là công cụ giúp quan sát riêng tác động của múi giờ, không phải nguồn thời gian thực cho sản phẩm.

## 6. Truyền Clock và chụp thời điểm một lần khi cần nhất quán

Một lớp dùng thời gian nên nhận `Clock` qua hàm tạo hoặc tham số. Môi trường chạy thật cung cấp đồng hồ hệ thống; kiểm thử có thể cung cấp đồng hồ khác mà không sửa thuật toán.

Nếu cùng một thao tác cần lưu cả thời điểm và ngày địa phương tương ứng, chụp một lần:

```java
Instant captured = clock.instant();
ZonedDateTime localView = captured.atZone(clock.getZone());
```

Không nhất thiết gọi `Instant.now(clock)` rồi `LocalDate.now(clock)` nhiều lần và cho rằng tất cả thuộc một mốc. Khi hệ thống đi qua nửa đêm giữa các lời gọi, ngày đọc sau có thể khác ngày suy ra từ thời điểm đọc trước.

Ngược lại, nếu các thao tác cố ý cần những thời điểm mới ở các bước khác nhau, hãy đọc lại. Truyền `Clock` giúp kiểm soát phụ thuộc; nó không tự đóng băng thời gian hoặc gộp nhiều lời gọi thành một giao dịch thời gian.

Múi giờ của một đồng hồ dùng chung cũng không tự đại diện cho mọi người dùng. Nếu chức năng dùng múi giờ của từng người, giữ nguồn thời điểm chung và xác định rõ múi giờ theo ngữ cảnh yêu cầu, thay vì thay đổi cấu hình toàn cục giữa các yêu cầu.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `ClockSourceDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Các giá trị được cố định để kết quả có thể lặp lại.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class ClockSourceDemo {
    record CurrentView(Instant instant, ZonedDateTime localDateTime) {}

    static final class TimeService {
        private final Clock clock;

        TimeService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        CurrentView currentView() {
            Instant captured = clock.instant();
            return new CurrentView(captured, captured.atZone(clock.getZone()));
        }

        LocalDate today() {
            return LocalDate.now(clock);
        }
    }

    public static void main(String[] args) {
        Instant reference = Instant.parse("2026-10-24T18:30:00Z");
        Clock utc = Clock.fixed(reference, ZoneOffset.UTC);
        Clock vietnam = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("utcZone=" + utc.getZone());
        System.out.println("vietnamZone=" + vietnam.getZone());
        System.out.println("sameInstant="
                + utc.instant().equals(vietnam.instant()));
        System.out.println("instantNow=" + Instant.now(vietnam));
        System.out.println("utcDate=" + LocalDate.now(utc));
        System.out.println("vietnamDate=" + LocalDate.now(vietnam));
        System.out.println("vietnamDateTime=" + ZonedDateTime.now(vietnam));
        System.out.println("millisMatch="
                + (vietnam.millis() == reference.toEpochMilli()));

        TimeService service = new TimeService(vietnam);
        CurrentView view = service.currentView();
        System.out.println("captured=" + view.instant());
        System.out.println("localView=" + view.localDateTime());
        System.out.println("today=" + service.today());
        System.out.println("utcStill=" + utc.getZone());
    }
}
```

Biên dịch và chạy:

```shell
javac ClockSourceDemo.java
java ClockSourceDemo
```

Kết quả chuẩn:

```text
utcZone=Z
vietnamZone=Asia/Ho_Chi_Minh
sameInstant=true
instantNow=2026-10-24T18:30:00Z
utcDate=2026-10-24
vietnamDate=2026-10-25
vietnamDateTime=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
millisMatch=true
captured=2026-10-24T18:30:00Z
localView=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
today=2026-10-25
utcStill=Z
```

`Z` là cách biểu diễn độ lệch 0 của `ZoneOffset.UTC`. Hai đồng hồ trả cùng thời điểm, nhưng `LocalDate.now` cho hai ngày khác nhau vì múi giờ.

`TimeService.currentView()` giữ `Instant` đã chụp và ngày-giờ địa phương được suy ra từ chính thời điểm đó. `today()` là một thao tác đọc riêng; trong ví dụ nó ổn định vì nguồn là đồng hồ cố định. Với nguồn hệ thống, các lần gọi riêng có thể diễn ra ở những thời điểm khác nhau.

Dòng `utcStill=Z` xác nhận việc tạo đồng hồ Việt Nam không thay cấu hình đồng hồ UTC gốc.

## 8. Giới hạn cần hiểu khi dùng Clock

### Không phải đồng hồ đo khoảng chạy đơn điệu

Đồng hồ hệ thống có thể được hiệu chỉnh. `Clock` không cam kết rằng mọi lần đọc đều tăng đều hoặc dùng để đo chính xác thời gian thực thi. Khi cần đo khoảng chạy ngắn trong một tiến trình, công cụ như `System.nanoTime()` có mục đích riêng; không suy ra từ đó một ngày/giờ lịch.

`Duration.between(startInstant, endInstant)` mô tả chênh lệch hai mốc được đọc. Nếu nguồn mốc bị điều chỉnh, đó không tự là phép đo đơn điệu của thời gian chương trình đã chạy.

### Nguồn “hiện tại” có thể là nguồn giả lập

`Clock` là một trừu tượng có thể thay thế. Nó có thể trả một thời điểm cố định hoặc được điều chỉnh để kiểm thử; vì vậy chữ “hiện tại” là hiện tại theo nguồn đang được cung cấp, không tự chứng minh đó là giờ thật bên ngoài.

Kiểm tra nguồn được cấp ở ranh giới cấu hình giúp tránh vô tình dùng đồng hồ kiểm thử trong môi trường chạy thật. Không cần để lớp nghiệp vụ tự kiểm tra loại triển khai rồi từ chối đồng hồ giả: việc chọn nguồn thuộc về nơi dựng ứng dụng.

### Không chứa ngôn ngữ hay chính sách nghiệp vụ

`Clock` không xác định locale hiển thị, ngày làm việc, lịch nghỉ hoặc giờ chốt. Nó cung cấp thời điểm và múi giờ; những quy tắc khác cần các thành phần phù hợp.

Truyền `Clock` vào một lớp cũng chưa đủ nếu lớp ấy vẫn gọi `LocalDate.now()` hoặc `Instant.now()` không tham số ở đường xử lý khác. Khi muốn kiểm soát nguồn thời gian, phải dùng nhất quán nguồn đã nhận tại những nơi cần cùng hợp đồng.

## 9. Tự thực hành

1. Thay thời điểm cố định thành `2026-10-24T16:30:00Z`. Theo UTC là 24/10; theo Việt Nam lúc đó là 23:30 cùng ngày. Quan sát ranh giới đổi ngày so với ví dụ ban đầu.
2. Giữ thời điểm gốc, đổi múi giờ sang `Asia/Tokyo`. Xác nhận `Instant.now` giữ nguyên còn giờ/ngày địa phương được chuyển theo vùng mới.
3. Dựng `TimeService` với hai đồng hồ cố định cùng thời điểm nhưng khác múi giờ. Chỉ ra chức năng nào thay đổi kết quả (`today`) và phần nào phải giữ cùng thời điểm (`captured`).

Tham khảo: [Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html), [LocalDate — now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now(java.time.Clock)) và [Instant — now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#now(java.time.Clock)) trong Java SE 21.
