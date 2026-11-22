# ChronoField và ChronoUnit thường dùng

## 1. Trường mô tả thành phần; đơn vị mô tả lượng thay đổi

Khi thao tác với ngày giờ, hai câu hỏi sau nhìn gần giống nhau nhưng dùng hai nhóm API khác nhau:

- “Ngày này nằm ở **tháng nào**?” là đọc một trường (field): `ChronoField.MONTH_OF_YEAR`.
- “Ngày này **cộng thêm bao nhiêu tháng**?” là tính theo một đơn vị (unit): `ChronoUnit.MONTHS`.

Ví dụ ngày `2024-02-29` có trường tháng bằng 2. Cộng 3 ngày vào ngày ấy cho `2024-03-03`. Số 2 mô tả thành phần của một ngày; số 3 là lượng dịch chuyển theo đơn vị ngày. Không đổi chỗ hai khái niệm này.

`ChronoField` là tập các trường chuẩn, triển khai `TemporalField`; `ChronoUnit` là tập các đơn vị chuẩn, triển khai `TemporalUnit`. Cả hai là `enum` trong gói `java.time.temporal`. Chúng là những đối tượng mô tả loại trường hoặc đơn vị, không tự chứa một ngày giờ cụ thể.

| Nhu cầu | Nhóm phù hợp | Ví dụ |
| --- | --- | --- |
| Đọc số ngày trong tháng của ngày đang có | Trường | `date.get(ChronoField.DAY_OF_MONTH)` |
| Đặt ngày trong tháng thành 1 | Trường | `date.with(ChronoField.DAY_OF_MONTH, 1)` |
| Cộng 3 ngày | Đơn vị | `date.plus(3, ChronoUnit.DAYS)` |
| Đếm số ngày giữa hai ngày | Đơn vị | `ChronoUnit.DAYS.between(start, end)` |
| Tìm giới hạn ngày hợp lệ của tháng đang xét | Phạm vi của trường | `date.range(ChronoField.DAY_OF_MONTH)` |

Trong mã ứng dụng đơn giản, `date.getMonthValue()`, `date.withDayOfMonth(1)` và `date.plusDays(3)` thường dễ đọc hơn. Dùng các hằng trường/đơn vị khi cần chọn thao tác qua tham số, duyệt các thành phần hay xây công cụ xử lý ngày giờ dùng chung.

## 2. Những ChronoField thường gặp

Bảng này dùng ý nghĩa theo lịch ISO của các kiểu `LocalDate`, `LocalTime` và các kiểu liên quan.

| Trường | Ý nghĩa | Giá trị/điểm cần nhớ |
| --- | --- | --- |
| `YEAR` | Năm theo trục năm liên tục | Ví dụ 2024; có năm 0 và năm âm |
| `MONTH_OF_YEAR` | Số tháng trong năm | 1..12; tháng 1 là 1 |
| `DAY_OF_MONTH` | Số ngày trong tháng | Tùy tháng/năm, tối đa 28..31 |
| `DAY_OF_YEAR` | Số thứ tự ngày trong năm | 1..365 hoặc 366 |
| `DAY_OF_WEEK` | Thứ trong tuần | Thứ Hai = 1, Chủ nhật = 7 |
| `HOUR_OF_DAY` | Giờ trong ngày | 0..23 |
| `MINUTE_OF_HOUR` | Phút trong giờ | 0..59 |
| `SECOND_OF_MINUTE` | Giây trong phút | 0..59 trong các kiểu ISO đang xét |
| `NANO_OF_SECOND` | Phần nano giây trong giây hiện tại | 0..999.999.999 |
| `SECOND_OF_DAY` | Số giây tính từ đầu ngày | 0..86.399 |
| `NANO_OF_DAY` | Số nano giây tính từ đầu ngày | Giá trị lớn; đọc bằng `getLong` |
| `EPOCH_DAY` | Số ngày so với ngày gốc ISO 1970-01-01 | Ngày gốc có giá trị 0; không phải số mili giây |
| `INSTANT_SECONDS` | Số giây của thời điểm so với mốc epoch | Dùng trên kiểu có thông tin thời điểm, như `Instant` |
| `OFFSET_SECONDS` | Độ lệch UTC tính bằng giây | Cần kiểu có offset, như `OffsetDateTime` |

Với `2024-02-29`, `DAY_OF_MONTH` là 29 còn `DAY_OF_YEAR` là 60. Với `12:34:56`, `SECOND_OF_MINUTE` là 56 còn `SECOND_OF_DAY` là `12 * 3600 + 34 * 60 + 56 = 45296`. Chọn sai trường có thể vẫn nhận được một số hợp lệ nhưng mang ý nghĩa sai.

Không dùng số thứ tự `ordinal()` của enum làm giá trị lịch. Ví dụ muốn đọc thứ trong tuần, dùng `DAY_OF_WEEK` hoặc `getDayOfWeek().getValue()`, không suy luận từ vị trí khai báo enum.

`YEAR_OF_ERA` và `YEAR` cũng không hoàn toàn đồng nghĩa: một bên là năm trong kỷ nguyên, một bên là năm trên trục liên tục. Với dữ liệu trước Công nguyên hoặc năm 0, phải giữ đúng mô hình; không thay hằng này bằng hằng kia chỉ vì chúng giống nhau ở các năm hiện đại. Chi tiết hợp đồng nằm trong [ChronoField](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoField.html).

## 3. Đọc, đặt và xem phạm vi trường

### 3.1. Đọc bằng get hoặc getLong

`get(field)` trả về `int`; `getLong(field)` trả về `long`. Nhưng không được hiểu rằng `get` luôn dùng được miễn là giá trị hiện tại nhỏ.

Một số trường có miền giá trị lớn hơn `int`. `LocalTime.get(NANO_OF_DAY)` không hỗ trợ cách đọc bằng `int`; phải dùng `getLong(NANO_OF_DAY)`. Điều này vẫn đúng khi thời gian đang đọc là nửa đêm và số nano giây hiện tại bằng 0. Giới hạn phụ thuộc hợp đồng của trường và kiểu, không chỉ số đang lưu.

Với thời gian `12:34:56.123456789`:

```text
HOUR_OF_DAY      = 12
SECOND_OF_DAY    = 45296
NANO_OF_SECOND   = 123456789
NANO_OF_DAY      = 45296123456789
```

`getLong` chỉ thay cách biểu diễn số trả về; nó không bổ sung thành phần bị thiếu. Một `LocalDate` không có giờ, nên gọi `getLong(HOUR_OF_DAY)` vẫn không hợp lệ. Xem quy tắc đọc ở [TemporalAccessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAccessor.html).

### 3.2. Đặt một trường bằng with

`date.with(DAY_OF_MONTH, 1)` yêu cầu một ngày có ngày trong tháng là 1. Nó không có nghĩa “cộng thêm một ngày”; thao tác cộng dùng `plus(1, DAYS)`.

Các kiểu chuẩn đang dùng của `java.time` là bất biến. Giá trị trả về từ `with` hoặc `plus` phải được giữ lại; đối tượng ban đầu không bị sửa.

Hành vi khi giá trị đích không hợp lệ phụ thuộc trường và kiểu. Ví dụ đặt `DAY_OF_MONTH = 30` trong tháng 2 báo `DateTimeException`, trong khi đổi tháng từ ngày 31 sang tháng 2 bằng trường `MONTH_OF_YEAR` có thể lùi về ngày hợp lệ cuối tháng. Không áp một quy tắc xử lý ngày sai cho tất cả các trường.

### 3.3. Phạm vi chung khác phạm vi theo ngày cụ thể

- `ChronoField.DAY_OF_MONTH.range()` mô tả phạm vi chung của trường, với giá trị tối đa có thể tới 31.
- `date.range(ChronoField.DAY_OF_MONTH)` xét ngữ cảnh ngày đó. Nếu `date` thuộc tháng 2/2024, giá trị tối đa là 29; tháng 2/2023 thì là 28.

Ví dụ một biểu mẫu chọn ngày cho tháng 2/2024 không nên lấy số 31 từ phạm vi chung rồi cho rằng đó là ngày hợp lệ của tháng được chọn. Khi đã biết năm-tháng, hãy xác thực trong ngữ cảnh đó.

`getBaseUnit()` và `getRangeUnit()` giúp hiểu cấu trúc trường: với `DAY_OF_MONTH`, đơn vị cơ sở là `DAYS`, còn chu kỳ bao chứa là `MONTHS`. Điều này giải thích “đếm ngày bên trong tháng”; nó không có nghĩa một tháng luôn có một số ngày cố định.

## 4. Những ChronoUnit thường dùng

| Đơn vị | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| `NANOS` | Dịch chuyển/đo theo nano giây | 1 giây = 1.000.000.000 nano giây |
| `MICROS` | Dịch chuyển/đo theo micro giây | 1 giây = 1.000.000 micro giây |
| `MILLIS` | Dịch chuyển/đo theo mili giây | 1 giây = 1.000 mili giây |
| `SECONDS` | Thời gian theo giây | Thường dùng với thời điểm và thời gian |
| `MINUTES` | Thời gian theo phút | Đơn vị thời gian |
| `HOURS` | Thời gian theo giờ | Đơn vị thời gian |
| `DAYS` | Dịch chuyển/đo theo ngày | Ý nghĩa phải gắn với kiểu đang dùng |
| `WEEKS` | Dịch chuyển/đo theo tuần | 7 ngày theo lịch ISO |
| `MONTHS` | Lịch theo tháng | Không đổi thành số giây cố định |
| `YEARS` | Lịch theo năm | Phải tính năm nhuận và ngày hợp lệ |

Các đơn vị lớn hơn như `DECADES`, `CENTURIES`, `MILLENNIA` tồn tại nhưng ít gặp trong xử lý lịch ứng dụng thông thường. `FOREVER` là đơn vị nhân tạo dùng cho mô hình phạm vi; không coi nó là một khoảng có thể cộng vào mọi ngày giờ.

### 4.1. Cộng, trừ và đo khoảng cách

Ba dạng API thường dùng:

- `value.plus(amount, unit)` và `value.minus(amount, unit)`: tạo giá trị sau dịch chuyển.
- `unit.between(start, end)`: đo lượng đơn vị hoàn chỉnh giữa hai giá trị.
- `start.until(end, unit)`: dạng tương đương để yêu cầu phép đo từ phía giá trị đầu.

Với hai `LocalDate` là 28/2/2024 và 1/3/2024, `DAYS.between` là 2. Đảo chiều hai giá trị cho -2. Hai giá trị cùng ngày cho 0. Đây là chênh lệch ngày; nếu nghiệp vụ đếm số ngày xuất hiện và tính cả hai đầu, đó là quy tắc đếm khác cần được nêu rõ.

Nên dùng hai đầu mút cùng kiểu và xác định rõ ý nghĩa dữ liệu. Một số API cho phép chuyển đầu mút thứ hai sang kiểu của đầu mút thứ nhất, nhưng không nên dựa vào chuyển đổi ngầm khi nó có thể bỏ thông tin.

### 4.2. between trả số đơn vị hoàn chỉnh

Từ `2024-01-10T23:00` đến `2024-01-11T01:00`:

| Phép đo | Kết quả | Đang trả lời câu hỏi nào? |
| --- | --- | --- |
| `HOURS.between` trên hai `LocalDateTime` | 2 | Có bao nhiêu giờ hoàn chỉnh? |
| `DAYS.between` trên hai `LocalDateTime` | 0 | Có bao nhiêu ngày hoàn chỉnh theo cách đo của kiểu này? |
| `DAYS.between` trên hai `toLocalDate()` | 1 | Hai ngày lịch cách nhau bao nhiêu bước? |

Không có mâu thuẫn: khi bỏ phần giờ, câu hỏi đã thay đổi. Đừng tự chuyển sang `LocalDate` nếu yêu cầu cần số khoảng 24 giờ đầy đủ.

Phần dư không tạo ra số thập phân trong kết quả `long`; phép đo đơn vị hoàn chỉnh bỏ phần chưa đủ theo hướng về 0. Ví dụ 2 giờ theo một chiều và -2 giờ theo chiều ngược lại vẫn tương ứng 0 ngày hoàn chỉnh cho hai đầu mút trên.

Với tháng cũng cần cẩn thận: `2024-01-31.plusMonths(1)` được `2024-02-29`, nhưng `MONTHS.between` trên hai `LocalDate` này trả 0. Phép cộng tháng có bước điều chỉnh ngày không hợp lệ; phép đo tháng hoàn chỉnh không đơn giản đảo ngược mọi phép cộng. Hãy kiểm tra đúng kết quả nghiệp vụ mong muốn thay vì giả định hai phép toán luôn là nghịch đảo.

### 4.3. Độ dài ước lượng không phải quy tắc đổi mọi đơn vị

`ChronoUnit` có `isDateBased()`, `isTimeBased()`, `isDurationEstimated()` và `getDuration()`. Các đơn vị ngày/tháng/năm thuộc nhóm theo lịch; đơn vị từ nano giây đến nửa ngày thuộc nhóm theo thời gian. `FOREVER` không thuộc hai nhóm đó.

`MONTHS.getDuration()` không cho số giây thực tế của một tháng cụ thể. Ngay cả `DAYS` cũng được đánh dấu có độ dài ước lượng: một ngày trên lịch có múi giờ có thể chịu thay đổi độ lệch UTC. Với `ZonedDateTime`, cộng một ngày theo lịch và cộng 24 giờ có thể cho kết quả khác nhau khi chuyển giờ mùa hè.

Vì thế, phải chọn cả **kiểu dữ liệu** lẫn **đơn vị**. `DAYS` trên ngày lịch, `HOURS` trên khoảng thời gian và `DAYS` trên một thời điểm không tự động mang cùng ý nghĩa nghiệp vụ. Hợp đồng của đơn vị được mô tả tại [ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html).

## 5. Mỗi kiểu chỉ hỗ trợ những trường và đơn vị phù hợp

| Kiểu | Trường hỗ trợ điển hình | Đơn vị hỗ trợ điển hình | Ví dụ không hỗ trợ |
| --- | --- | --- | --- |
| `LocalDate` | `YEAR`, `DAY_OF_MONTH`, `EPOCH_DAY` | `DAYS`, `MONTHS`, `YEARS` | `HOUR_OF_DAY`, `HOURS` |
| `LocalTime` | `HOUR_OF_DAY`, `NANO_OF_DAY` | `NANOS`, `SECONDS`, `HOURS` | `YEAR`, `DAYS` |
| `LocalDateTime` | Các trường ngày và giờ địa phương | `HOURS`, `DAYS`, `MONTHS` | `INSTANT_SECONDS`, `OFFSET_SECONDS` |
| `YearMonth` | `YEAR`, `MONTH_OF_YEAR` | `MONTHS`, `YEARS` | `DAY_OF_MONTH`, `DAYS` |
| `Instant` | `INSTANT_SECONDS`, `NANO_OF_SECOND` | `NANOS`, `SECONDS`, `HOURS` | `YEAR`, `MONTHS` |

Bảng nêu các ví dụ phổ biến, không liệt kê toàn bộ khả năng.

Một `Instant` biểu diễn thời điểm trên trục thời gian, nhưng không tự chọn múi giờ để trả về năm hoặc giờ địa phương. Muốn đọc năm của thời điểm tại một nơi, phải chuyển bằng múi giờ rõ ràng, chẳng hạn `instant.atZone(zone).getYear()`. Không tự gán UTC nếu câu hỏi thực tế nói đến ngày giờ của địa phương khác.

Có hai dạng kiểm tra hỗ trợ:

- `value.isSupported(ChronoField.DAY_OF_MONTH)`: hỏi về trường.
- `value.isSupported(ChronoUnit.DAYS)`: hỏi về đơn vị.

Chúng là hai phép kiểm tra khác nhau dù cùng tên phương thức. Nếu biết chắc kiểu và thao tác, có thể gọi trực tiếp. Khi trường/đơn vị được chọn động, kiểm tra trước giúp trả thông báo có ý nghĩa; không cần gọi thử rồi che mọi ngoại lệ.

`isSupported` trả `true` cũng không đảm bảo mọi lượng cộng hay mọi giá trị đặt đều hợp lệ. Ví dụ `LocalDate` hỗ trợ `DAY_OF_MONTH`, nhưng tháng 2 vẫn không chấp nhận ngày 30. Lượng cộng quá lớn còn có thể vượt miền biểu diễn.

## 6. Chương trình Java 17+ kiểm chứng trường, đơn vị và lỗi

Lưu mã sau thành `FieldsAndUnits.java`. Đây là chương trình độc lập dùng các kiểu trong JDK, không cần thư viện ngoài. Các hàm kiểm tra chủ động ném `AssertionError` nếu kết quả sai, nên không cần bật cờ `-ea`.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;

public class FieldsAndUnits {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(12, 34, 56, 123_456_789);
        eq(date.get(ChronoField.YEAR), 2024);
        eq(date.get(ChronoField.MONTH_OF_YEAR), 2);
        eq(date.get(ChronoField.DAY_OF_MONTH), 29);
        eq(date.get(ChronoField.DAY_OF_YEAR), 60);
        eq(date.get(ChronoField.DAY_OF_WEEK), 4);
        eq(time.get(ChronoField.HOUR_OF_DAY), 12);
        eq(time.get(ChronoField.SECOND_OF_DAY), 45_296);
        eq(time.getLong(ChronoField.NANO_OF_DAY), 45_296_123_456_789L);
        eq(ChronoField.DAY_OF_MONTH.range().getMaximum(), 31L);
        eq(date.range(ChronoField.DAY_OF_MONTH).getMaximum(), 29L);
        eq(ChronoField.DAY_OF_MONTH.getBaseUnit(), ChronoUnit.DAYS);
        eq(ChronoField.DAY_OF_MONTH.getRangeUnit(), ChronoUnit.MONTHS);

        eq(date.with(ChronoField.DAY_OF_MONTH, 1),
                LocalDate.of(2024, 2, 1));
        eq(date.plus(3, ChronoUnit.DAYS), LocalDate.of(2024, 3, 3));
        eq(date, LocalDate.of(2024, 2, 29));
        eq(date.isSupported(ChronoField.HOUR_OF_DAY), false);
        eq(date.isSupported(ChronoUnit.HOURS), false);
        eq(time.isSupported(ChronoUnit.DAYS), false);
        eq(YearMonth.of(2024, 2).isSupported(ChronoField.DAY_OF_MONTH), false);
        eq(YearMonth.of(2024, 2).isSupported(ChronoUnit.MONTHS), true);
        eq(Instant.EPOCH.isSupported(ChronoField.INSTANT_SECONDS), true);
        eq(Instant.EPOCH.isSupported(ChronoField.YEAR), false);
        eq(Instant.EPOCH.isSupported(ChronoUnit.MONTHS), false);
        eq(Instant.EPOCH.getLong(ChronoField.INSTANT_SECONDS), 0L);

        rejects(UnsupportedTemporalTypeException.class,
                () -> date.get(ChronoField.HOUR_OF_DAY));
        rejects(UnsupportedTemporalTypeException.class,
                () -> date.plus(1, ChronoUnit.HOURS));
        rejects(UnsupportedTemporalTypeException.class,
                () -> time.get(ChronoField.NANO_OF_DAY));
        rejects(DateTimeException.class,
                () -> date.with(ChronoField.DAY_OF_MONTH, 30));

        LocalDate start = LocalDate.of(2024, 2, 28);
        LocalDate end = LocalDate.of(2024, 3, 1);
        eq(ChronoUnit.DAYS.between(start, end), 2L);
        eq(start.until(end, ChronoUnit.DAYS), 2L);
        eq(ChronoUnit.DAYS.between(end, start), -2L);
        LocalDate jan31 = LocalDate.of(2024, 1, 31);
        eq(jan31.plus(1, ChronoUnit.MONTHS), date);
        eq(ChronoUnit.MONTHS.between(jan31, date), 0L);

        LocalDateTime night = LocalDateTime.of(2024, 1, 10, 23, 0);
        LocalDateTime morning = LocalDateTime.of(2024, 1, 11, 1, 0);
        eq(ChronoUnit.HOURS.between(night, morning), 2L);
        eq(ChronoUnit.DAYS.between(night, morning), 0L);
        eq(ChronoUnit.DAYS.between(night.toLocalDate(),
                morning.toLocalDate()), 1L);
        eq(ChronoUnit.DAYS.isDateBased(), true);
        eq(ChronoUnit.HOURS.isTimeBased(), true);
        eq(ChronoUnit.DAYS.isDurationEstimated(), true);
        eq(ChronoUnit.HOURS.isDurationEstimated(), false);

        System.out.println("dayOfYear=" + date.get(ChronoField.DAY_OF_YEAR));
        System.out.println("nanoOfDay=" + time.getLong(ChronoField.NANO_OF_DAY));
        System.out.println("maxDay=" + date.range(ChronoField.DAY_OF_MONTH).getMaximum());
        System.out.println("plus3Days=" + date.plus(3, ChronoUnit.DAYS));
        System.out.println("elapsedHours=" + ChronoUnit.HOURS.between(night, morning));
        System.out.println("completeDays=" + ChronoUnit.DAYS.between(night, morning));
        System.out.println("calendarDateSteps=" + ChronoUnit.DAYS.between(
                night.toLocalDate(), morning.toLocalDate()));
        System.out.println("completeMonths=" + ChronoUnit.MONTHS.between(jan31, date));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 FieldsAndUnits.java
java FieldsAndUnits
```

Stdout:

```text
dayOfYear=60
nanoOfDay=45296123456789
maxDay=29
plus3Days=2024-03-03
elapsedHours=2
completeDays=0
calendarDateSteps=1
completeMonths=0
PASS checks=40
```

Dòng cuối xác nhận 40 lần kiểm tra đã hoàn thành, bao gồm cả các thao tác được yêu cầu phải ném ngoại lệ. Hàm `rejects` sẽ làm chương trình thất bại nếu thao tác không ném lỗi hoặc ném loại lỗi không mong đợi; việc bắt lỗi trong ví dụ không phải âm thầm bỏ qua lỗi.

Ba dòng `elapsedHours`, `completeDays` và `calendarDateSteps` dùng cùng một cặp thời gian để làm lộ khác biệt giữa câu hỏi về giờ hoàn chỉnh, ngày hoàn chỉnh và chênh lệch ngày lịch. Hai dòng `maxDay` và `completeMonths` kiểm tra những điểm dễ suy luận sai ở ranh giới tháng.

## 7. Lỗi thường gặp

- **Dùng trường thay đơn vị:** `DAY_OF_MONTH` mô tả thành phần của một ngày; `DAYS` mô tả đơn vị tính. Chọn nhóm dựa vào câu hỏi “đọc/đặt thành phần” hay “dịch chuyển/đo khoảng cách”.
- **Nhầm số tháng bắt đầu từ 0:** `MONTH_OF_YEAR` của lịch ISO bắt đầu từ 1. Không áp quy ước của API cũ vào `java.time`.
- **Dùng get cho mọi trường:** với `NANO_OF_DAY`, `EPOCH_DAY` hoặc `INSTANT_SECONDS` trên các kiểu tương ứng, dùng cách đọc `long` theo hợp đồng.
- **Dùng getLong để chữa trường không tồn tại:** đổi độ rộng số không tạo ra giờ cho `LocalDate` hay năm địa phương cho `Instant`.
- **Lấy phạm vi trường chung để xác thực một ngày cụ thể:** dùng phạm vi gắn với đối tượng hoặc kiểm tra năm-tháng cụ thể.
- **Nhầm thay trường với cộng lượng:** đặt ngày thành 1 khác cộng một ngày; đặt giờ thành 3 khác cộng ba giờ.
- **Cho rằng between luôn là số lần đã gọi plus:** các phép điều chỉnh ở cuối tháng có thể làm giả định đó sai.
- **Quy đổi tháng/năm sang số giây cố định:** phải dùng lịch cụ thể hoặc hai đầu mút cụ thể.
- **Bỏ mất kết quả trả về:** các kiểu chuẩn bất biến không thay đổi biến ban đầu chỉ bằng một lời gọi `plus` hay `with`.

## 8. Thực hành chọn API

1. **Đọc tháng của `2024-11-05`.** Dùng `get(MONTH_OF_YEAR)` hoặc `getMonthValue()`; kết quả là 11. `MONTHS` không phải một trường để đọc tháng.

2. **Từ `2024-11-05`, tạo ngày đầu cùng tháng và ngày sau hai tuần.** Phép thứ nhất dùng `with(DAY_OF_MONTH, 1)`, cho `2024-11-01`. Phép thứ hai dùng `plus(2, WEEKS)`, cho `2024-11-19`. Cả hai giữ nguyên đối tượng gốc.

3. **Đọc số nano giây từ đầu ngày tại `00:00:00`.** Dùng `getLong(NANO_OF_DAY)`, nhận 0. Không thay bằng `get` chỉ vì giá trị hiện tại nhỏ.

4. **Đếm tháng giữa hai kỳ hóa đơn `2024-01` và `2024-02`.** Nếu dữ liệu thực sự là kỳ theo tháng, dùng hai `YearMonth`; `MONTHS.between` cho 1. Đừng tự biến thành ngày 31/1 và 29/2 rồi mong phép đo tháng hoàn chỉnh trên `LocalDate` luôn có cùng ý nghĩa.

5. **Một tiện ích nhận trường do người dùng chọn nhưng dữ liệu là `LocalDate`.** Nếu người dùng chọn `HOUR_OF_DAY`, tiện ích nên báo trường không phù hợp với dữ liệu; không tự thêm giờ 00:00 để làm cho thao tác có vẻ thành công.

Khi chọn hằng, hãy diễn đạt câu hỏi trước: đang đọc thành phần nào, thay thành phần nào, cộng theo đơn vị nào, hay đo bao nhiêu đơn vị hoàn chỉnh giữa hai giá trị. Sau đó kiểm tra kiểu dữ liệu có đủ thông tin để trả lời câu hỏi ấy.
