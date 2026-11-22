# TemporalField và TemporalUnit

## 1. Một thành phần để đọc, một đơn vị để tính

Trong `java.time`, câu hỏi “ngày trong tháng hiện tại là bao nhiêu?” khác với yêu cầu “cộng thêm một ngày”. Câu đầu cần **trường thời gian** (`TemporalField`); câu sau cần **đơn vị thời gian** (`TemporalUnit`). Chúng là hai đối tượng mô tả phép xử lý, không phải bản thân ngày giờ.

Ví dụ với `2024-01-31`: trường `DAY_OF_MONTH` có giá trị 31; đơn vị `DAYS` được dùng để cộng hoặc đếm ngày. `DAY_OF_MONTH` không mang nghĩa “một ngày”, còn `DAYS` không cho biết ngày hiện tại là ngày mấy.

| So sánh | `TemporalField` | `TemporalUnit` |
| --- | --- | --- |
| Câu hỏi chính | Đọc/đặt thành phần nào? | Cộng hoặc đo theo đơn vị nào? |
| Ví dụ | `DAY_OF_MONTH`, `HOUR_OF_DAY` | `DAYS`, `HOURS` |
| Kiểu chuẩn thường dùng | `ChronoField` | `ChronoUnit` |
| Tác vụ điển hình | `getLong(field)`, `with(field, value)` | `plus(amount, unit)`, `until(end, unit)` |

Interface mô tả hợp đồng; enum cung cấp bộ giá trị chuẩn. Vì vậy, có thể khai báo `TemporalField field = ChronoField.DAY_OF_MONTH` và `TemporalUnit unit = ChronoUnit.DAYS`. Không dùng `ordinal()` của enum để lưu ý nghĩa trường/đơn vị trong dữ liệu.

## 2. TemporalField: thành phần có tên, miền và cách đọc

Một trường không chỉ là một nhãn. Nó biết cách kiểm tra khả năng hỗ trợ, lấy giá trị và điều chỉnh một đối tượng thời gian. [TemporalField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalField.html)

| Phương thức | Vai trò |
| --- | --- |
| `isSupportedBy(temporal)` | Đối tượng có trường này không? |
| `getFrom(temporal)` | Đọc giá trị bằng `long` |
| `adjustInto(temporal, newValue)` | Tạo kết quả đã đặt trường |
| `range()` | Miền tổng quát của trường |
| `rangeRefinedBy(temporal)` | Miền được xác định theo đối tượng cụ thể |
| `getBaseUnit()` | Trường được đo bằng đơn vị gì? |
| `getRangeUnit()` | Trường biến thiên trong phạm vi đơn vị nào? |

`DAY_OF_MONTH` đo bằng `DAYS`, giới hạn trong `MONTHS`; `MINUTE_OF_HOUR` đo bằng `MINUTES`, giới hạn trong `HOURS`. “Đơn vị phạm vi” không phải giá trị lớn nhất: với ngày trong tháng, `getRangeUnit()` trả `MONTHS`, còn `range()` mô tả các giá trị số.

Miền tổng quát của `DAY_OF_MONTH` là `1 - 28/31`: tối thiểu luôn là 1, tối đa thay đổi từ 28 đến 31. Khi gắn vào tháng 2 năm nhuận 2024, miền cụ thể là `1 - 29`. Kiểm tra `ChronoField.DAY_OF_MONTH.checkValidValue(31)` chỉ xác nhận 31 thuộc miền tổng quát; không chứng minh ngày 31 tồn tại trong tháng 2.

`ChronoField` còn có trường gộp như `SECOND_OF_DAY`, `EPOCH_DAY`, chứ không chỉ năm/tháng/ngày. Nhiều trường thuộc ngày hoặc giờ, nhưng không phải tất cả đều thuộc một trong hai nhóm: chẳng hạn độ lệch UTC là một loại thông tin khác. Đừng suy ra mọi trường ngày đều có trên mọi đối tượng. [ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html)

## 3. TemporalUnit: đơn vị khác lượng thời gian

`ChronoUnit.DAYS` chỉ là đơn vị ngày. Số 3 kết hợp với đơn vị đó mới diễn đạt yêu cầu cộng ba ngày. `Period.ofDays(3)` và `Duration.ofHours(3)` là các **lượng thời gian** (`TemporalAmount`), không phải `TemporalUnit`.

| Phương thức | Vai trò |
| --- | --- |
| `isSupportedBy(temporal)` | Có thể cộng/trừ đơn vị này không? |
| `addTo(temporal, amount)` | Cộng số đơn vị và trả kết quả |
| `between(start, end)` | Đếm số đơn vị trọn vẹn giữa hai mốc |
| `getDuration()` | Thời lượng đại diện, có thể chỉ là ước lượng |
| `isDurationEstimated()` | Thời lượng đại diện có phải ước lượng không? |
| `isDateBased()` / `isTimeBased()` | Phân loại theo ngày lịch/giờ |

Ví dụ từ 09:15 đến 11:14 có 1 giờ trọn vẹn. `HOURS.between` không trả 1.9833 và không làm tròn thành 2. Với mốc cuối trước mốc đầu, kết quả có thể âm. [TemporalUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalUnit.html)

Đừng đổi tháng thành giây bằng cách nhân số tháng với `MONTHS.getDuration()`. Tháng lịch có số ngày khác nhau; ngày tại vùng áp dụng giờ mùa hè cũng có thể dài hoặc ngắn hơn 24 giờ. Với `ChronoUnit`, các đơn vị ngày lịch có thời lượng ước lượng; các đơn vị giờ như `HOURS` có thời lượng chính xác theo hợp đồng, bỏ qua vấn đề giây nhuận. `FOREVER` là đơn vị nhân tạo, không phải lựa chọn để cộng vô hạn. [ChronoUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoUnit.html)

## 4. Hai cách viết cùng một ý định

Đoạn minh họa trong một phương thức, với `date` là `LocalDate`:

```java
long day1 = date.getLong(ChronoField.DAY_OF_MONTH);
long day2 = ChronoField.DAY_OF_MONTH.getFrom(date);

LocalDate first1 = date.with(ChronoField.DAY_OF_MONTH, 1);
LocalDate first2 = ChronoField.DAY_OF_MONTH.adjustInto(date, 1);

LocalDate next1 = date.plus(3, ChronoUnit.DAYS);
LocalDate next2 = ChronoUnit.DAYS.addTo(date, 3);

long gap1 = date.until(next1, ChronoUnit.DAYS);
long gap2 = ChronoUnit.DAYS.between(date, next1);
```

`TemporalField.resolve(...)` là điểm tích hợp nâng cao cho giai đoạn phân giải các trường khi phân tích chuỗi; nó không phải phương thức thường cần gọi trong mã nghiệp vụ đọc/đặt ngày.

Các cặp biểu đạt cùng mục đích với các kiểu và giá trị trong ví dụ. Thường chọn cách bắt đầu từ đối tượng ngày giờ để người đọc thấy rõ dữ liệu đang được xử lý.

Cơ chế này còn giúp mở rộng API: lớp ngày giờ trực tiếp xử lý các hằng chuẩn `ChronoField`/`ChronoUnit`; với trường hoặc đơn vị khác, lời gọi được chuyển cho phương thức tương ứng của đối tượng trường/đơn vị. Đây là cơ chế phân công xử lý hai chiều, cho phép bổ sung định nghĩa mà không sửa mọi lớp ngày giờ.

## 5. Chương trình chạy được

Lưu thành `FieldUnitDemo.java`. Chương trình đối chiếu đặt trường với cộng đơn vị, miền tổng quát với miền cụ thể và ngày lịch với 24 giờ.

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalField;
import java.time.temporal.TemporalUnit;

public class FieldUnitDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 1, 31);
        TemporalField field = ChronoField.DAY_OF_MONTH;
        TemporalUnit unit = ChronoUnit.DAYS;

        System.out.println("day=" + field.getFrom(date));
        System.out.println("base=" + field.getBaseUnit());
        System.out.println("rangeUnit=" + field.getRangeUnit());
        System.out.println("generalRange=" + field.range());
        System.out.println("februaryRange="
                + field.rangeRefinedBy(LocalDate.of(2024, 2, 10)));

        LocalDate setFirst = date.with(field, 1);
        LocalDate addOne = unit.addTo(date, 1);
        System.out.println("setFirst=" + setFirst);
        System.out.println("addOne=" + addOne);
        System.out.println("original=" + date);
        System.out.println("daysBetween=" + unit.between(date, addOne));
        System.out.println("fullHours=" + ChronoUnit.HOURS.between(
                LocalTime.of(9, 15), LocalTime.of(11, 14)));

        System.out.println("supportsHourField="
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("supportsHourUnit="
                + date.isSupported(ChronoUnit.HOURS));
        System.out.println("dayEstimated=" + ChronoUnit.DAYS.isDurationEstimated());
        System.out.println("hourEstimated=" + ChronoUnit.HOURS.isDurationEstimated());

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, ZoneId.of("Europe/Berlin"));
        ZonedDateTime nextDay = start.plus(1, ChronoUnit.DAYS);
        ZonedDateTime next24Hours = start.plus(24, ChronoUnit.HOURS);
        System.out.println("calendarDay=" + nextDay);
        System.out.println("twentyFourHours=" + next24Hours);
        System.out.println("elapsedHours="
                + Duration.between(start, nextDay).toHours());
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 FieldUnitDemo.java
java FieldUnitDemo
```

Stdout với dữ liệu múi giờ IANA tương ứng quy tắc Berlin năm 2024:

```text
day=31
base=Days
rangeUnit=Months
generalRange=1 - 28/31
februaryRange=1 - 29
setFirst=2024-01-01
addOne=2024-02-01
original=2024-01-31
daysBetween=1
fullHours=1
supportsHourField=false
supportsHourUnit=false
dayEstimated=true
hourEstimated=false
calendarDay=2024-03-31T12:00+02:00[Europe/Berlin]
twentyFourHours=2024-03-31T13:00+02:00[Europe/Berlin]
elapsedHours=23
```

`with(DAY_OF_MONTH, 1)` đặt ngày thành 1 và giữ tháng 1. `plus(1, DAYS)` tiến một ngày sang tháng 2. Cả hai trả giá trị mới; `original` vẫn là ngày 31 tháng 1.

Ở ví dụ Berlin, đổi từ giờ chuẩn sang giờ mùa hè làm một ngày lịch qua mốc chuyển giờ chỉ có 23 giờ thực trôi. Cộng một `DAYS` giữ 12:00 ngày kế tiếp; cộng 24 `HOURS` đi theo trục thời gian và đến 13:00. Ý nghĩa phép toán được quyết định bởi cả đơn vị lẫn kiểu nhận nó. [ZonedDateTime: phép cộng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#plus(long,java.time.temporal.TemporalUnit))

## 6. Kiểm tra khả năng hỗ trợ đúng loại

Một giá trị có thể hỗ trợ một số trường và một số đơn vị, không phải toàn bộ API. Có hai overload dễ nhầm:

```java
date.isSupported(ChronoField.DAY_OF_MONTH); // Có đọc/đặt được trường không?
date.isSupported(ChronoUnit.DAYS);          // Có cộng/trừ theo đơn vị không?
```

Trong thuật toán chỉ đọc, `TemporalAccessor` đủ để kiểm tra trường. Muốn cộng đơn vị cần `Temporal`. Kiểm tra trường không thay cho kiểm tra đơn vị; cả hai trả `false` ở ví dụ giờ với `LocalDate` vì ngày đó không lưu phần giờ.

Khi đọc số lớn, ưu tiên `getLong(field)` nếu hợp đồng trường yêu cầu. `isSupported(field)` đúng vẫn chưa bảo đảm `get(field)` trả `int` được: trường `EPOCH_DAY` trên `LocalDate` có miền lớn hơn `int`. Không bắt mọi ngoại lệ rồi tự trả 0, vì 0 có thể là một giá trị hợp lệ và che giấu việc thiếu dữ liệu.

## 7. Bộ chuẩn không phải toàn bộ khả năng mở rộng

`ChronoField` và `ChronoUnit` đáp ứng phần lớn nhu cầu. Những định nghĩa khác có sẵn trong JDK gồm `IsoFields.QUARTER_OF_YEAR`, `IsoFields.QUARTER_YEARS` và các trường từ `WeekFields`. Trường tuần phụ thuộc quy tắc tuần, nên phải chọn rõ tiêu chuẩn nghiệp vụ thay vì giả định mọi lịch đều có cùng số tuần.

Đoạn minh họa trong một phương thức:

```java
LocalDate date = LocalDate.of(2024, 5, 20);
long quarter = date.getLong(java.time.temporal.IsoFields.QUARTER_OF_YEAR);
LocalDate later = date.plus(1, java.time.temporal.IsoFields.QUARTER_YEARS);
// quarter = 2; later = 2024-08-20.
```

Không cần tự triển khai interface chỉ để cộng vài ngày. Nếu thật sự tạo trường/đơn vị riêng, phải xác định khả năng hỗ trợ, miền, cách điều chỉnh, tính bất biến và an toàn luồng theo hợp đồng; không chỉ đặt một tên mới. [IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)

## 8. Lỗi thường gặp và cách lựa chọn

- **Dùng `DAY_OF_MONTH` như đơn vị:** chọn `with` khi đặt thành phần, chọn `plus` với `DAYS` khi tiến ngày.
- **Xem `range()` là kiểm tra ngày hợp lệ hoàn chỉnh:** dùng miền theo đối tượng và phép tạo ngày thực sự để áp dụng quan hệ năm/tháng/ngày.
- **Xem tháng là số giây cố định:** dùng phép cộng lịch trên kiểu ngày giờ phù hợp.
- **Đếm tháng bằng lấy số tháng của hai ngày trừ nhau:** bỏ qua năm và các đơn vị trọn vẹn; dùng `MONTHS.between` theo yêu cầu đã xác định.
- **Dùng interface quá rộng trong nghiệp vụ cụ thể:** nếu chỉ xử lý `LocalDate`, chữ ký và phương thức như `getDayOfMonth`, `plusDays` thường dễ hiểu hơn.

## 9. Tự thực hành

1. Với `2024-04-20`, dự đoán kết quả của `with(DAY_OF_MONTH, 1)` và `plus(1, DAYS)`.
2. In `DAY_OF_MONTH.rangeRefinedBy` cho tháng 2 năm 2023 và 2024.
3. Đếm phút và giờ trọn vẹn giữa 08:40 và 10:05 bằng hai đơn vị khác nhau.
4. Giải thích vì sao `DAYS.getDuration()` không đủ để tính thời điểm “12:00 ngày mai” ở một múi giờ có chuyển giờ mùa hè.

Đối chiếu: (1) `2024-04-01` và `2024-04-21`; (2) `1 - 28` và `1 - 29`; (3) 85 phút, 1 giờ; (4) đó là yêu cầu lịch địa phương, cần áp dụng quy tắc múi giờ khi cộng ngày.