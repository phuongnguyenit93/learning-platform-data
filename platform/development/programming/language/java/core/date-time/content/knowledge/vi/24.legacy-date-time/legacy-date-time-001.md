# java.util.Date biểu diễn thời điểm và vì sao tên lớp dễ gây nhầm

## 1. Tên Date khiến người đọc nghĩ tới ngày, nhưng giá trị là thời điểm

Khi nghe “ngày 25/10/2026”, ta thường nghĩ một ngày lịch không có giờ. `java.util.Date` lại biểu diễn **một thời điểm cụ thể với độ chính xác mili giây**, không phải chỉ một bộ năm-tháng-ngày.

Có thể hiểu phần giá trị cốt lõi như số mili giây tính từ mốc `1970-01-01T00:00:00Z`. Với cùng một giá trị đó, cách biểu diễn ngày/giờ ở UTC và Việt Nam có thể khác ngày.

Ví dụ, thời điểm `2026-10-24T18:30:00Z` là buổi tối 24/10 theo UTC nhưng là 01:30 ngày 25/10 tại Việt Nam. Không có hai `Date` khác nhau chỉ vì người đọc muốn hai cách hiển thị ấy: cùng một thời điểm được diễn giải qua hai múi giờ.

Với mã `java.time` mới, kiểu gần nghĩa với `java.util.Date` là `Instant`. Kiểu `LocalDate` lại phù hợp khi dữ liệu thực sự chỉ là ngày lịch, như ngày sinh hoặc ngày được chọn trong một biểu mẫu không có giờ.

## 2. Date lưu gì và không lưu gì?

| Thuộc tính | java.util.Date có lưu không? |
|---|---|
| Thời điểm đến độ chính xác mili giây | Có |
| Múi giờ vùng như Asia/Ho_Chi_Minh | Không |
| Locale/ngôn ngữ hiển thị | Không |
| Chỉ có ngày, không có giờ theo nghĩa LocalDate | Không phải mô hình của lớp |
| Chuỗi định dạng gốc người dùng đã nhập | Không |
| Phần nano giây nhỏ hơn mili giây | Không bảo toàn trong Date thuần |

Không nên nói một đối tượng `Date` “đang ở múi giờ Việt Nam” chỉ vì `toString()` in ra giờ Việt Nam trên máy hiện tại. Múi giờ tham gia lúc chuyển giá trị thành các trường để hiển thị, không phải một thuộc tính múi giờ được giữ trong đối tượng.

Cũng không nên diễn giải `Date` là một chuỗi UTC được lưu bên trong. Đó là một giá trị thời gian; chuỗi là một cách trình bày được tạo sau đó.

### Vì sao có toString() giống lịch địa phương?

`Date.toString()` tạo một chuỗi ngày-giờ có thông tin vùng theo ngữ cảnh mặc định của môi trường. Đầu ra vì vậy có thể khác giữa máy phát triển và máy chủ dù `getTime()` giống nhau.

Muốn xuất định dạng ổn định, chuyển sang `Instant` rồi dùng bộ định dạng và múi giờ đã chọn. Không dùng `Date.toString()` làm hợp đồng trao đổi dữ liệu ngầm và không kết luận dữ liệu đã bị dịch giờ chỉ từ hai dòng nhật ký có múi giờ khác nhau.

## 3. Những phương thức vẫn hữu ích khi làm việc với API cũ

| API | Ý nghĩa |
|---|---|
| `new Date()` | Lấy thời điểm hiện tại của nguồn hệ thống ở độ chính xác mili giây |
| `new Date(epochMillis)` | Tạo từ số mili giây epoch được cung cấp |
| `getTime()` | Đọc giá trị mili giây epoch |
| `setTime(epochMillis)` | Thay đổi thời điểm mà chính đối tượng đang biểu diễn |
| `Date.from(instant)` | Tạo Date từ Instant, trong phạm vi biểu diễn của Date |
| `toInstant()` | Chuyển Date thuần sang Instant |
| `before`, `after`, `compareTo` | So sánh thời điểm giữa các giá trị Date |

Lớp `java.util.Date` không bị đánh dấu deprecated toàn bộ. Nhiều constructor và phương thức cũ dùng các thành phần lịch, phân tích hoặc định dạng chuỗi đã deprecated; không được suy ra rằng mọi phương thức trong bảng trên cũng deprecated.

Vẫn cần hiểu lớp để giao tiếp với thư viện cũ. Tuy nhiên, việc một API trả `Date` không bắt buộc toàn bộ thuật toán mới phải tiếp tục dùng một mô hình thời gian có thể thay đổi.

### Mili giây khác giây

`new Date(1000L)` là thời điểm sau mốc epoch đúng **một giây**, không phải một nghìn giây. `new Date(0L)` là mốc epoch.

Nếu nguồn bên ngoài truyền epoch giây, phải chuyển theo đúng đơn vị, ví dụ `Instant.ofEpochSecond(value)` rồi chuyển ở biên API nếu cần. Đừng truyền thẳng số giây vào constructor nhận mili giây. Nếu nhân để đổi đơn vị, còn phải xét khả năng tràn số; chọn API biểu đạt đơn vị giúp tránh quy ước ngầm.

## 4. Các API thành phần cũ góp phần gây nhầm

Những lời gọi như constructor `Date(year, month, day)` hoặc `getYear()`, `getMonth()`, `getDate()` có nguồn gốc từ thiết kế ban đầu và đã deprecated.

Các quy ước dễ nhầm gồm:

- Năm theo một số API cũ là năm trừ 1900.
- Tháng theo một số API cũ đánh số 0–11.
- Tên `getDate()` lại là ngày trong tháng, không phải trả về một đối tượng Date khác.
- Các trường lịch còn chịu ngữ cảnh múi giờ, không phải những con số được lưu độc lập với thời điểm.

Không dùng chúng để minh họa cách tạo ngày mới trong Java hiện đại. Nếu muốn ngày cụ thể, tạo `LocalDate` bằng năm và tháng thông thường; nếu cần một thời điểm, cần thêm giờ/múi giờ phù hợp rồi chuyển thành `Instant`.

Ví dụ, đổi một `LocalDate` sang `Date` không phải phép ép kiểu không mất nghĩa. Bạn phải quyết định thời điểm nào trong ngày và múi giờ nào. Tự gán nửa đêm ở múi giờ mặc định có thể tạo lỗi dữ liệu khi chuyển qua môi trường khác.

## 5. Chuyển Date và Instant: có thể mất độ chính xác

Ví dụ:

```java
Instant source = Instant.parse("2026-10-24T18:30:00.123456789Z");
Date legacy = Date.from(source);
Instant restored = legacy.toInstant();
```

`restored` là `2026-10-24T18:30:00.123Z`: phần nhỏ hơn mili giây không còn. Không kiểm tra vòng `Instant -> Date -> Instant` luôn bằng tuyệt đối khi đầu vào có phần lẻ vượt khả năng Date lưu.

Chiều `Date` thuần → `Instant` có thể giữ đúng thời điểm mili giây của Date. Khi đi qua lưu trữ hoặc kiểu con khác, cần kiểm tra hợp đồng thật của thành phần ấy thay vì suy rộng từ lớp thuần trong bài.

Múi giờ không cần thiết để chuyển `Date` thuần thành `Instant`, vì cả hai đã biểu diễn thời điểm. Múi giờ chỉ cần khi muốn lấy ngày/giờ địa phương:

```java
LocalDate localDate = legacy.toInstant()
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();
```

Đoạn này cố ý giữ phần ngày theo vùng đã chọn và bỏ phần giờ sau khi chuyển. Kết quả không phải một phép chuyển đổi có thể khôi phục đầy đủ thời điểm ban đầu chỉ từ `LocalDate`.

## 6. Date có thể thay đổi: chú ý tham chiếu dùng chung

Nếu hai biến cùng trỏ tới một `Date`, gọi `setTime` qua một biến làm biến còn lại quan sát thấy giá trị mới:

```java
Date alias = original;
alias.setTime(0L);
```

`final Date` chỉ ngăn biến được gán sang đối tượng khác; nó không cấm `setTime` trên đối tượng. Điều này có thể gây lỗi khi một lớp giữ tham chiếu do nơi gọi cung cấp hoặc trả trực tiếp tham chiếu nội bộ ra ngoài.

Nếu phải giữ `Date` thuần trong một API cũ, có thể sao chép phòng vệ tại cả đầu vào và đầu ra:

```java
Date copy = new Date(original.getTime());
```

Bản sao có cùng thời điểm mili giây nhưng thay đổi về sau của một đối tượng không làm đối tượng kia đổi theo. Chương trình bên dưới minh họa cả hai chiều.

Đây là ví dụ với đối tượng Date thuần trong một luồng. Không mặc định phép sao chép tự giải quyết việc một đối tượng dùng chung đang bị luồng khác sửa; cần có chính sách sở hữu hoặc đồng bộ phù hợp. Với phần xử lý mới, giữ `Instant` bất biến thường giúp hợp đồng đơn giản hơn.

Không thay đổi một `Date` đang làm khóa trong cấu trúc dựa trên `hashCode` hoặc thứ tự. Thay giá trị thời gian sau khi thêm có thể khiến việc tìm kiếm/duy trì thứ tự không còn đúng với giá trị đã lập chỉ mục.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `UtilDateModelDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Nó chỉ dùng nguồn thời gian xác định và không phụ thuộc múi giờ mặc định để tạo đầu ra.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.Objects;

public class UtilDateModelDemo {
    static final class LegacyEvent {
        private final Date occurredAt;

        LegacyEvent(Date occurredAt) {
            Objects.requireNonNull(occurredAt);
            this.occurredAt = new Date(occurredAt.getTime());
        }

        Date occurredAt() {
            return new Date(occurredAt.getTime());
        }
    }

    public static void main(String[] args) {
        Instant source = Instant.parse("2026-10-24T18:30:00.123456789Z");
        Date legacy = Date.from(source);
        Instant retained = legacy.toInstant();

        System.out.println("source=" + source);
        System.out.println("retained=" + retained);
        System.out.println("sameFullPrecision=" + source.equals(retained));
        System.out.println("millisConsistent="
                + (legacy.getTime() == source.toEpochMilli()));
        System.out.println("utcDate="
                + retained.atZone(ZoneOffset.UTC).toLocalDate());
        System.out.println("vietnamDate="
                + retained.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate());
        System.out.println("epochZero=" + new Date(0L).toInstant());
        System.out.println("oneThousandMillis=" + new Date(1000L).toInstant());

        LegacyEvent safe = new LegacyEvent(legacy);
        Date alias = legacy;
        Date independentCopy = new Date(legacy.getTime());
        alias.setTime(0L);
        System.out.println("originalAfterAliasChange=" + legacy.toInstant());
        System.out.println("independentCopy=" + independentCopy.toInstant());
        System.out.println("eventAfterInputChange="
                + safe.occurredAt().toInstant());

        Date returned = safe.occurredAt();
        returned.setTime(0L);
        System.out.println("eventAfterOutputChange="
                + safe.occurredAt().toInstant());

        Date sameMillis = new Date(independentCopy.getTime());
        System.out.println("sameDateValue="
                + independentCopy.equals(sameMillis));
    }
}
```

Biên dịch và chạy:

```shell
javac UtilDateModelDemo.java
java UtilDateModelDemo
```

Kết quả chuẩn:

```text
source=2026-10-24T18:30:00.123456789Z
retained=2026-10-24T18:30:00.123Z
sameFullPrecision=false
millisConsistent=true
utcDate=2026-10-24
vietnamDate=2026-10-25
epochZero=1970-01-01T00:00:00Z
oneThousandMillis=1970-01-01T00:00:01Z
originalAfterAliasChange=1970-01-01T00:00:00Z
independentCopy=2026-10-24T18:30:00.123Z
eventAfterInputChange=2026-10-24T18:30:00.123Z
eventAfterOutputChange=2026-10-24T18:30:00.123Z
sameDateValue=true
```

Các dòng thể hiện những vấn đề riêng:

- `sameFullPrecision=false` do độ chính xác mili giây, không phải do múi giờ.
- Hai dòng ngày địa phương khác nhau nhưng đều được suy ra từ cùng `retained`.
- Thay `alias` cũng thay đối tượng `legacy` vì chúng cùng tham chiếu.
- `independentCopy` không bị thay đổi bởi phép sửa qua alias.
- `LegacyEvent` sao chép khi nhận vào và khi trả ra nên hai phép sửa từ bên ngoài không làm thời điểm nội bộ đổi.
- `sameDateValue` so sánh giá trị Date thuần bằng `equals`, không dùng `==` để so địa chỉ.

## 8. Giữ ranh giới với các kiểu có tên Date khác

`java.util.Date` và `java.sql.Date` không phải cùng hợp đồng chỉ vì cùng tên ngắn. Các kiểu JDBC cũ như `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp` có ý nghĩa riêng; dù kế thừa Date, không được mặc định mọi lời gọi và phép so sánh đều có hành vi y hệt Date thuần.

Ví dụ, `java.sql.Date.toInstant()` không hỗ trợ chuyển theo cách của `java.util.Date`. `Timestamp` còn có phần nano giây riêng. Khi nhận từ một thư viện hoặc JDBC, kiểm tra kiểu thực tế và hợp đồng chuyển đổi thích hợp; tránh sao chép máy móc một hàm dùng `Date` thuần để xử lý mọi kiểu con.

Ở phần xử lý mới, chọn theo ý nghĩa:

| Ý nghĩa dữ liệu | Kiểu thường phù hợp |
|---|---|
| Thời điểm một sự kiện xảy ra | `Instant` |
| Chỉ ngày lịch | `LocalDate` |
| Ngày-giờ địa phương chưa xác định thời điểm duy nhất | `LocalDateTime` |
| Ngày-giờ cần giữ múi giờ vùng | `ZonedDateTime` |

Đừng chuyển mọi trường legacy tên `date` sang cùng một kiểu chỉ bằng tìm-thay. Cần xác định nó đang lưu thời điểm hay ngày dân sự, nơi gọi có đang dựa vào múi giờ mặc định không, và nơi lưu trữ có giữ độ chính xác nào.

## 9. Tự thực hành

1. Đổi phần lẻ của nguồn trong chương trình thành `.123Z`. Vòng chuyển trở lại `Instant` sẽ giữ đúng giá trị đó; giải thích vì sao lần này không mất độ chính xác.
2. Tạo hai Date thuần bằng cùng `getTime()` rồi sửa một đối tượng bằng `setTime`. Kiểm tra chúng ban đầu bằng nhau về giá trị nhưng không dùng chung trạng thái.
3. Giữ nguyên thời điểm nguồn và đổi vùng lấy ngày sang một vùng khác. Xác nhận `getTime()` không thay đổi chỉ vì cách lấy ngày thay đổi.
4. Cho yêu cầu “ngày sinh 25/10/2000”. Giải thích vì sao tự tạo một Date tại nửa đêm không phải lựa chọn trung tính nếu dữ liệu chỉ cần ngày lịch.

Tham khảo: [java.util.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html) và [java.sql.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html) trong Java SE 21.
