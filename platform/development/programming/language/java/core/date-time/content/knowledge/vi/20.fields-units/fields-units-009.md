# UnsupportedTemporalTypeException khi chọn sai trường hoặc đơn vị

## 1. Lỗi nói về hợp đồng của phép toán

`UnsupportedTemporalTypeException` thường xuất hiện khi yêu cầu một thông tin hoặc phép tính mà đối tượng thời gian không hỗ trợ. Ví dụ, đọc giờ từ `LocalDate` hoặc cộng tháng vào `Instant` đều đặt một yêu cầu không phù hợp với mô hình dữ liệu.

Đây là ngoại lệ lúc chạy, thuộc nhánh:

```text
RuntimeException
└── DateTimeException
    └── UnsupportedTemporalTypeException
```

Không cần khai báo `throws` để chương trình biên dịch, nhưng vẫn phải sửa nguyên nhân hoặc xử lý tại ranh giới phù hợp. Nó không có nghĩa dữ liệu ngày giờ đã hỏng. [UnsupportedTemporalTypeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/UnsupportedTemporalTypeException.html)

Trong thông báo lỗi, “field” là **trường** như `HourOfDay`; “unit” là **đơn vị** như `Hours`. Đừng sửa một trường thành đơn vị chỉ vì chúng cùng có chữ “giờ”: đọc thành phần và cộng lượng là hai tác vụ khác nhau.

## 2. Các tình huống cần phân biệt

| Lời gọi | Vì sao thất bại? | Hướng sửa đúng ý nghĩa |
| --- | --- | --- |
| `LocalDate.get(HOUR_OF_DAY)` | Ngày không có phần giờ | Dùng kiểu có giờ hoặc bỏ yêu cầu giờ |
| `LocalDate.plus(1, HOURS)` | Ngày không hỗ trợ cộng giờ | Chọn dữ liệu ngày giờ nếu nghiệp vụ cần giờ |
| `Instant.get(YEAR)` | Chưa có múi giờ để suy ra năm địa phương | Chọn `ZoneId`, chuyển sang kiểu có múi giờ |
| `Instant.plus(1, MONTHS)` | Tháng lịch không có thời lượng cố định trên trục thời gian | Chọn lịch/múi giờ để cộng tháng |
| `LocalDate.get(EPOCH_DAY)` | Miền trường quá lớn cho `get` trả `int` | Dùng `getLong(EPOCH_DAY)` |
| `Duration.get(MINUTES)` | `get` chỉ hỗ trợ các đơn vị biểu diễn của lượng | Dùng `toMinutes()` nếu cần tổng phút |

Trường hợp `EPOCH_DAY` rất dễ chẩn đoán sai: **trường được hỗ trợ nhưng phương thức đọc không phù hợp**. Không phải mọi `UnsupportedTemporalTypeException` đều được giải quyết bằng kiểm tra `isSupported` rồi giữ nguyên lời gọi. [TemporalAccessor.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html#get(java.time.temporal.TemporalField))

## 3. Tìm đúng đối tượng nhận và thao tác gây lỗi

Khi đọc stack trace, đi từ thông báo và các khung JDK đến dòng mã ứng dụng đầu tiên. Ghi lại:

1. Kiểu thực tế của đối tượng nhận, ví dụ `LocalDate`, `Instant`, hoặc một kết quả phân tích chuỗi.
2. Phương thức đang gọi: `get`, `getLong`, `with`, `plus`, `format`, `between`...
3. Trường/đơn vị bị yêu cầu và ý nghĩa nghiệp vụ cần đạt.
4. Dữ liệu còn thiếu hoặc giới hạn phương thức đọc.

Nếu lỗi là `HourOfDay`, kiểm tra xem mình có đang định dạng một `LocalDate` bằng mẫu có giờ không. Nếu lỗi là `Seconds` khi cộng một `Duration` vào ngày, hãy nhớ phép áp dụng lượng có thể dùng đơn vị khác với tên factory đã tạo nó.

Không viết logic điều khiển bằng cách so khớp toàn bộ `getMessage()`. Nội dung thông báo hỗ trợ chẩn đoán, không phải mã lỗi ổn định cho nghiệp vụ.

## 4. Chương trình tạo lỗi có kiểm soát và sửa từng nguyên nhân

Lưu thành `UnsupportedDemo.java`. Các lời gọi sai được đặt riêng để thấy rõ loại ngoại lệ; hàm `show` chỉ phục vụ minh chứng, không phải khuôn xử lý lỗi cho mọi ứng dụng.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

public class UnsupportedDemo {
    static void show(String label, Runnable action) {
        try {
            action.run();
        } catch (DateTimeException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 6, 15);
        Instant instant = Instant.parse("2024-06-15T12:30:00Z");
        Duration duration = Duration.ofMinutes(90);
        DateTimeFormatter dateAndTime =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");

        show("readHour", () -> date.get(ChronoField.HOUR_OF_DAY));
        show("addHour", () -> date.plus(1, ChronoUnit.HOURS));
        show("readYear", () -> instant.get(ChronoField.YEAR));
        show("addMonth", () -> instant.plus(1, ChronoUnit.MONTHS));
        show("readEpochInt", () -> date.get(ChronoField.EPOCH_DAY));
        show("durationGetMinutes", () -> duration.get(ChronoUnit.MINUTES));
        show("formatHour", () -> date.format(dateAndTime));

        System.out.println("epochSupported="
                + date.isSupported(ChronoField.EPOCH_DAY));
        System.out.println("epochLong=" + date.getLong(ChronoField.EPOCH_DAY));
        System.out.println("utcYear=" + instant.atZone(ZoneOffset.UTC).getYear());
        System.out.println("totalMinutes=" + duration.toMinutes());
        System.out.println("dateOnly="
                + date.format(DateTimeFormatter.ISO_LOCAL_DATE));
        System.out.println("explicitMidnight="
                + date.atStartOfDay().format(dateAndTime));

        show("invalidMonth", () -> date.with(ChronoField.MONTH_OF_YEAR, 13));
        show("beyondDateRange", () -> LocalDate.MAX.plusDays(1));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 UnsupportedDemo.java
java UnsupportedDemo
```

Stdout chính xác:

```text
readHour: UnsupportedTemporalTypeException
addHour: UnsupportedTemporalTypeException
readYear: UnsupportedTemporalTypeException
addMonth: UnsupportedTemporalTypeException
readEpochInt: UnsupportedTemporalTypeException
durationGetMinutes: UnsupportedTemporalTypeException
formatHour: UnsupportedTemporalTypeException
epochSupported=true
epochLong=19889
utcYear=2024
totalMinutes=90
dateOnly=2024-06-15
explicitMidnight=2024-06-15 00:00
invalidMonth: DateTimeException
beyondDateRange: DateTimeException
```

`explicitMidnight` là ví dụ **bổ sung một giờ được chọn rõ ràng**, không phải khôi phục giờ vốn có trong `LocalDate`. Chỉ dùng khi nghiệp vụ thật sự quy định bắt đầu từ nửa đêm. Hai dòng cuối cho thấy giá trị mới không hợp lệ hoặc kết quả vượt miền là vấn đề khác với chọn sai loại trường/đơn vị.

## 5. isSupported giúp ở đâu, còn thiếu điều gì?

Với đầu vào tổng quát, kiểm tra trường trước khi đọc:

```java
// value có kiểu TemporalAccessor; đây là đoạn trong một phương thức.
if (value.isSupported(ChronoField.HOUR_OF_DAY)) {
    long hour = value.getLong(ChronoField.HOUR_OF_DAY);
    System.out.println(hour);
} else {
    System.out.println("Không có trường giờ trong ngày");
}
```

Với phép cộng/trừ, kiểm tra overload nhận `TemporalUnit` trên `Temporal`. Đọc trường và tính theo đơn vị không suy ra lẫn nhau: `Instant` cộng được `HOURS` nhưng không đọc trực tiếp được `HOUR_OF_DAY`. [Instant: các trường và đơn vị](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Ngay cả khi `isSupported` trả `true`, vẫn phải chọn phương thức đọc phù hợp với miền số, kiểm tra giá trị mới và xem xét giới hạn kết quả. `LocalDate.MAX` hỗ trợ ngày nhưng không thể tiến thêm ngày; `MONTH_OF_YEAR` được hỗ trợ nhưng tháng 13 vẫn sai. [LocalDate: phép cộng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#plus(long,java.time.temporal.TemporalUnit))

Nếu khả năng là bắt buộc, có thể từ chối đầu vào không phù hợp trước phép toán với lỗi rõ ràng. Nếu thông tin là tùy chọn, dùng một kết quả vắng mặt có nghĩa. Không tự trả 0 khi không đọc được giờ, vì 0 cũng là nửa đêm hợp lệ.

## 6. Lỗi có thể xuất hiện gián tiếp qua formatter và amount

### Bộ định dạng yêu cầu trường không có

`DateTimeFormatter` đọc các trường từ đối tượng đầu vào. Mẫu `uuuu-MM-dd HH:mm` cần cả ngày lẫn giờ, nên không thể định dạng trực tiếp một `LocalDate` dù mẫu đúng cú pháp.

Có hai hướng sửa theo yêu cầu: chỉ hiển thị ngày bằng formatter ngày, hoặc tạo dữ liệu có giờ bằng một quy tắc rõ ràng. Thêm `withZone` vào formatter không tự tạo giờ cho một ngày không có thời điểm; với `Instant`, chỉ định múi giờ lại là điều kiện để có thể suy ra các trường lịch địa phương. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

### Lượng thời gian dùng đơn vị khi áp dụng

`Duration.ofDays(1)` biểu diễn 24 giờ theo giây/nano giây. Cộng nó vào `LocalDate` có thể thất bại với đơn vị giây, dù `LocalDate` cộng được `DAYS`. Nếu muốn tiến một ngày lịch trên `LocalDate`, dùng `plusDays(1)` hoặc `Period.ofDays(1)`, vì đó mới là ý nghĩa cần diễn đạt.

`Duration.ofMinutes(90)` cũng không hỗ trợ `get(MINUTES)`: `get` đọc đơn vị biểu diễn, không thực hiện mọi phép chuyển đổi. Dùng `toMinutes()` cho tổng phút trọn vẹn; dùng `getSeconds()` nếu cần phần giây được lưu. [Duration.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html#get(java.time.temporal.TemporalUnit))

## 7. Bắt ngoại lệ mà không che mất lỗi thiết kế

Vì `UnsupportedTemporalTypeException` kế thừa `DateTimeException`, nếu có nhiều `catch` thì nhánh cụ thể phải đặt trước nhánh cha:

```java
try {
    // Một thao tác ngày giờ tại ranh giới cần xử lý lỗi.
} catch (java.time.temporal.UnsupportedTemporalTypeException ex) {
    // Báo kiểu dữ liệu không đáp ứng trường/đơn vị được yêu cầu.
} catch (DateTimeException ex) {
    // Xử lý các lỗi ngày giờ khác theo hợp đồng.
}
```

Đoạn trên minh họa thứ tự `catch`, không phải chương trình độc lập. Không dùng multi-catch chứa cả lớp cha và lớp con: Java không cho phép các lựa chọn có quan hệ kế thừa như vậy.

Trong mã nghiệp vụ biết chắc đầu vào là `LocalDate`, đọc một trường giờ thường là lỗi lập trình cần sửa. Trong công cụ nhận trường/đơn vị do người dùng chọn, có thể kiểm tra trước và báo lựa chọn không phù hợp. Không bắt rồi thử ngẫu nhiên các kiểu chuyển đổi, không âm thầm dùng múi giờ hệ thống, và không thêm dữ liệu giả chỉ để lỗi biến mất.

## 8. Tự thực hành

1. Tạo lỗi khi đọc `DAY_OF_MONTH` từ `LocalTime`, rồi giải thích vì sao thay `get` bằng `getLong` không giúp.
2. Đọc `EPOCH_DAY` từ `LocalDate` bằng `get` và `getLong`; đối chiếu với `isSupported`.
3. Định dạng một `Instant` bằng mẫu ngày giờ với múi giờ UTC được chọn rõ ràng.
4. Phân biệt lỗi do trường không được hỗ trợ với lỗi tạo ngày 30 tháng 2.

Đối chiếu: (1) dữ liệu không có ngày; `getLong` chỉ đổi miền số, không thêm thông tin; (2) trường có hỗ trợ nhưng `get` không phù hợp miền; (3) dùng formatter có `withZone(ZoneOffset.UTC)` hoặc chuyển `instant.atZone(ZoneOffset.UTC)`; (4) yêu cầu không phù hợp kiểu khác với giá trị ngày không hợp lệ.