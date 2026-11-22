# TemporalAccessor để đọc và Temporal để thay đổi giá trị

## 1. Hai hợp đồng trên cùng một giá trị thời gian

Khi viết một hàm xử lý ngày giờ, hãy xác định hàm cần **đọc thông tin** hay cần **tính một giá trị mới**. `TemporalAccessor` cung cấp hợp đồng đọc; `Temporal` mở rộng hợp đồng đó với phép điều chỉnh, cộng, trừ và tính khoảng cách. Một đối tượng `LocalDate` có cả hai khả năng, nhưng biến khai báo theo từng interface sẽ cho phép gọi những phương thức khác nhau.

```text
TemporalAccessor
      ↑ extends
   Temporal
```

`Temporal` kế thừa `TemporalAccessor`, nên một `Temporal` luôn có thể dùng ở vị trí cần `TemporalAccessor`. Chiều ngược lại không đúng: `MonthDay` có thể cung cấp tháng và ngày, nhưng không phải `Temporal`. [Hợp đồng TemporalAccessor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html)

Điểm quan trọng trong tiêu đề bài: **“thay đổi giá trị” nghĩa là nhận kết quả đã điều chỉnh, không phải sửa đối tượng ban đầu**. Các kiểu giá trị quen thuộc như `LocalDate` là bất biến; sau `plus` hoặc `with`, cần giữ kết quả trả về. Khai báo biến theo interface cũng không biến đối tượng thành kiểu dữ liệu khác.

## 2. Đọc bằng trường và truy vấn

Một **trường thời gian** (`TemporalField`) trả lời “thành phần nào?”; ví dụ `ChronoField.YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`. Một **đơn vị thời gian** (`TemporalUnit`) trả lời “cộng/trừ theo đơn vị nào?”; ví dụ `ChronoUnit.DAYS`, `MONTHS`. Hai khái niệm này không thay thế cho nhau.

| Nhu cầu đọc | Phương thức của `TemporalAccessor` |
| --- | --- |
| Kiểm tra có trường hay không | `isSupported(TemporalField)` |
| Đọc giá trị vừa miền `int` | `get(TemporalField)` |
| Đọc bằng `long` | `getLong(TemporalField)` |
| Xem miền giá trị của trường trong ngữ cảnh hiện tại | `range(TemporalField)` |
| Lấy thông tin qua một chiến lược truy vấn | `query(TemporalQuery<R>)` |

Ví dụ `LocalDate.of(2024, 2, 10).range(DAY_OF_MONTH)` cho miền `1 - 29`, vì miền ngày trong tháng phụ thuộc tháng và năm đang có. `getLong` giải quyết nhu cầu số lớn, **không** làm cho một trường chưa được hỗ trợ trở thành đọc được.

Không phải mọi giá trị thời gian đều có năm, giờ hoặc múi giờ. `LocalDate` có ngày nhưng không có giờ; `LocalTime` có giờ nhưng không có ngày; `Instant` biểu diễn một thời điểm trên trục thời gian. Với `Instant`, có thể đọc `INSTANT_SECONDS` bằng `getLong`; không thể tự suy ra `YEAR` mà chưa chọn múi giờ. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Múi giờ và hệ lịch không chỉ là các số nguyên, nên thường lấy qua `TemporalQueries`. Chẳng hạn `date.query(TemporalQueries.zone())` trả `null` với `LocalDate`. Tuy nhiên, **không phải truy vấn nào thiếu dữ liệu cũng trả `null`**: `LocalDate.from(accessor)` có thể ném `DateTimeException` nếu nguồn không đủ thông tin ngày.

## 3. Tạo kết quả mới bằng Temporal

| Phép toán | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `with(field, value)` | Đặt một trường theo quy tắc của kiểu/trường | Đổi tháng thành tháng 2 |
| `with(adjuster)` | Áp dụng quy tắc điều chỉnh | Chọn ngày cuối tháng |
| `plus(amount, unit)` | Cộng một số đơn vị | Cộng 3 ngày |
| `minus(amount, unit)` | Trừ một số đơn vị | Trừ 2 tháng |
| `plus(amount)` / `minus(amount)` | Áp dụng lượng thời gian như `Period` | Cộng một khoảng lịch |
| `until(end, unit)` | Đếm số đơn vị trọn vẹn đến mốc cuối | Số ngày giữa hai ngày |

Kiểm tra `isSupported(TemporalUnit)` trước khi cộng/trừ trong thuật toán tổng quát. Đây là overload khác với `isSupported(TemporalField)` để đọc trường. Một `Temporal` không bắt buộc hỗ trợ mọi đơn vị: `LocalDate` hỗ trợ `DAYS`, nhưng không hỗ trợ `HOURS`.

Đừng hiểu `with` là luôn chỉ thay một con số mà không quan tâm các trường còn lại. Ví dụ đổi tháng của ngày `2024-01-31` sang tháng 2 cho `2024-02-29`; đặt trực tiếp `DAY_OF_MONTH` thành 30 trên một ngày tháng 2 lại không hợp lệ. Quy tắc xử lý phụ thuộc phép toán cụ thể. `until` đếm đơn vị đầy đủ, không làm tròn theo cảm giác: từ 11:30 đến 13:29 có 1 giờ trọn vẹn. [Hợp đồng Temporal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html)

## 4. Chương trình minh chứng: đọc, tính kết quả và kiểm tra khả năng

Lưu thành `TemporalContractsDemo.java`. Chương trình dùng ngày cố định, nên không phụ thuộc ngày chạy hoặc múi giờ của máy.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.MonthDay;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;
import java.time.temporal.UnsupportedTemporalTypeException;

public class TemporalContractsDemo {
    static String readYear(TemporalAccessor value) {
        if (!value.isSupported(ChronoField.YEAR)) {
            return "YEAR unsupported";
        }
        return Long.toString(value.getLong(ChronoField.YEAR));
    }

    static Temporal addDays(Temporal value, long days) {
        if (!value.isSupported(ChronoUnit.DAYS)) {
            throw new IllegalArgumentException("DAYS unsupported");
        }
        return value.plus(days, ChronoUnit.DAYS);
    }

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 1, 31);
        TemporalAccessor readable = original;
        Temporal adjustable = original;

        System.out.println("year=" + readYear(readable));
        System.out.println("hourSupported="
                + readable.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("zone=" + readable.query(TemporalQueries.zone()));
        System.out.println("changed="
                + adjustable.with(ChronoField.MONTH_OF_YEAR, 2));
        System.out.println("next=" + addDays(adjustable, 1));
        System.out.println("original=" + original);
        System.out.println("hoursSupported="
                + adjustable.isSupported(ChronoUnit.HOURS));
        System.out.println("februaryRange="
                + LocalDate.of(2024, 2, 10).range(ChronoField.DAY_OF_MONTH));
        System.out.println("fullHours="
                + LocalTime.of(11, 30).until(LocalTime.of(13, 29), ChronoUnit.HOURS));

        TemporalAccessor anniversary = MonthDay.of(2, 29);
        System.out.println("month=" + anniversary.get(ChronoField.MONTH_OF_YEAR));
        System.out.println(readYear(anniversary));

        TemporalAccessor moment = Instant.parse("2024-01-01T00:00:00Z");
        System.out.println("epochSeconds="
                + moment.getLong(ChronoField.INSTANT_SECONDS));
        try {
            moment.get(ChronoField.INSTANT_SECONDS);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("use getLong for INSTANT_SECONDS");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 TemporalContractsDemo.java
java TemporalContractsDemo
```

Stdout chính xác:

```text
year=2024
hourSupported=false
zone=null
changed=2024-02-29
next=2024-02-01
original=2024-01-31
hoursSupported=false
februaryRange=1 - 29
fullHours=1
month=2
YEAR unsupported
epochSeconds=1704067200
use getLong for INSTANT_SECONDS
```

`readYear` nhận `TemporalAccessor` vì chỉ đọc. `addDays` nhận `Temporal` vì cần cộng ngày. `next` và `changed` đều tính từ `original`, nên hai kết quả không nối tiếp nhau; muốn nối tiếp phải gọi phép toán trên kết quả trước.

`INSTANT_SECONDS` được hỗ trợ nhưng `get` vẫn thất bại: miền của trường vượt `int`, dù một giá trị cụ thể như `1704067200` đang vừa `int`. Vì vậy, `isSupported(field) == true` không có nghĩa là có thể luôn dùng `get(field)`.

## 5. Kiểu khai báo, kiểu kết quả và tính bất biến

Khi giữ `LocalDate`, có thể viết trực tiếp `LocalDate next = date.plusDays(1)`. Khi giữ `Temporal`, chữ ký `plus` trả `Temporal`; trình biên dịch không còn biết kết quả là `LocalDate`.

Đoạn minh họa sau nằm trong một phương thức, không phải chương trình độc lập:

```java
LocalDate date = LocalDate.of(2024, 1, 31);

date.plusDays(1);                    // Bỏ kết quả: date vẫn là 2024-01-31.
LocalDate next = date.plusDays(1);   // next là 2024-02-01.

Temporal general = date;
Temporal result = general.plus(1, ChronoUnit.DAYS);
LocalDate restored = LocalDate.from(result);

TemporalAccessor view = date;
// view.plus(1, ChronoUnit.DAYS);    // Không biên dịch: interface không có plus.
```

`LocalDate.from(result)` phù hợp ở đây vì đầu vào ban đầu là `LocalDate`. Không nên áp dụng cách chuyển này cho kết quả tùy ý từ `Temporal`: nếu kết quả là `LocalTime`, thông tin ngày không tồn tại. Khi nghiệp vụ cần ngày ISO, dùng `LocalDate` ngay trong chữ ký thường rõ ràng hơn. [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)

`TemporalAccessor` là **giao diện đọc**, không phải cam kết rằng mọi lớp triển khai đều bất biến hoặc luồng an toàn. Với `java.time`, hãy dựa vào hợp đồng của kiểu cụ thể; các kiểu giá trị như `LocalDate` và `MonthDay` công bố tính bất biến. Không tự suy ra đặc tính đó cho một lớp tự viết chỉ vì nó triển khai interface.

## 6. Vì sao MonthDay đọc được nhưng không phải Temporal?

`MonthDay.of(2, 29)` lưu ngày 29 tháng 2 mà chưa gắn năm. Không thể tự xác định cộng một ngày phải ra ngày nào trong một năm cụ thể. Kiểu này có phương thức riêng như `withMonth`, `withDayOfMonth`, nhưng không cung cấp hợp đồng `Temporal` cho phép toán cộng/trừ tổng quát.

Điều đó cũng cho thấy “không phải `Temporal`” không đồng nghĩa với “không thể tạo biến thể mới”. Nếu cần một ngày có đầy đủ năm, hãy chọn năm bằng `atYear(year)`, rồi xử lý `LocalDate`. Với ngày 29 tháng 2 và năm không nhuận, `atYear` điều chỉnh về 28 tháng 2; nếu nghiệp vụ cấm điều chỉnh, kiểm tra `isValidYear(year)` trước. [MonthDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html)

## 7. Khi nào nên dùng hai interface?

- Dùng kiểu cụ thể trong phần lớn mã nghiệp vụ: `LocalDate` cho ngày lịch, `Instant` cho thời điểm, `ZonedDateTime` khi cần quy tắc múi giờ.
- Dùng `TemporalAccessor` tại ranh giới tiện ích thực sự cần đọc nhiều kiểu, đồng thời xác định rõ trường nào bắt buộc và xử lý trường thiếu.
- Dùng `Temporal` khi thuật toán thực sự cần điều chỉnh nhiều kiểu, đồng thời xác định đơn vị/trường được hỗ trợ và ý nghĩa nghiệp vụ.

Một ví dụ có sẵn là `DateTimeFormatter.format(TemporalAccessor)`: bộ định dạng cần đọc thông tin, không cần sửa nó. Tuy nhiên, nhận đúng interface chưa bảo đảm định dạng thành công; mẫu có phần giờ vẫn không thể lấy giờ từ `LocalDate`. Khi phân tích chuỗi, ưu tiên `LocalDate.parse` hoặc `formatter.parse(text, LocalDate::from)` nếu kết quả nghiệp vụ đã biết là ngày. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Đừng dùng ép kiểu `(Temporal) accessor` như một phép chuyển đổi dữ liệu. Nếu `accessor` là `MonthDay`, ép kiểu đó gây `ClassCastException`. Chọn đúng hợp đồng đầu vào từ đầu, hoặc thực hiện chuyển đổi có quy tắc và đủ dữ liệu.

## 8. Tự kiểm tra

1. Vì sao `TemporalAccessor value = LocalDate.of(2024, 1, 31)` đọc được năm nhưng không gọi được `plus` qua biến `value`?
2. Vì sao `Instant.isSupported(INSTANT_SECONDS)` đúng mà `get(INSTANT_SECONDS)` vẫn thất bại?
3. Vì sao `date.plusDays(1)` không làm `date` đổi giá trị?
4. Một hàm chỉ hiển thị tháng của `LocalDate` và `MonthDay` cần nhận interface nào?

Gợi ý đối chiếu: (1) phương thức gọi được phụ thuộc kiểu khai báo; (2) hỗ trợ trường và miền `int` là hai điều kiện khác nhau; (3) phải giữ kết quả trả về của kiểu bất biến; (4) `TemporalAccessor`, kèm hợp đồng yêu cầu `MONTH_OF_YEAR`.