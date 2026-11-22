# YearMonth cho kỳ báo cáo và hạn theo tháng

## 1. Khi một tháng là một giá trị nghiệp vụ

“Kỳ báo cáo tháng 02/2024” chưa chỉ ra ngày nào trong tháng, giờ nào hay múi giờ nào. Dùng `LocalDate.of(2024, 2, 1)` để biểu diễn kỳ có thể làm người đọc hiểu nhầm ngày 01 có ý nghĩa nghiệp vụ riêng, trong khi nó chỉ là ngày đại diện do người viết tự chọn.

`YearMonth` mô hình hóa trực tiếp tổ hợp **năm và tháng**. Theo [Java API của YearMonth](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html), kiểu này dùng lịch ISO và không chứa ngày trong tháng, giờ hoặc múi giờ.

```java
YearMonth period = YearMonth.of(2024, 2);
```

Giá trị `2024-02` phù hợp để biểu diễn kỳ tổng hợp doanh thu mẫu, tháng sử dụng dịch vụ, tháng kế hoạch hoặc tháng đến hạn. Khi cần một ngày cụ thể, ta bổ sung chính sách để chuyển từ `YearMonth` sang `LocalDate`.

| Thông tin cần biểu diễn | Kiểu phù hợp |
| --- | --- |
| Tháng Hai nói chung, không có năm | `Month` |
| Tháng 02/2024 | `YearMonth` |
| Ngày 29/02/2024 | `LocalDate` |
| Một thời điểm xác định trên dòng thời gian | `Instant` |
| Ngày giờ gắn với vùng | `ZonedDateTime` |

`YearMonth` là bất biến: `plusMonths` trả một giá trị mới. Nó không phải `LocalDate` bị ẩn phần ngày và cũng không đại diện sẵn cho đầu tháng hoặc cuối tháng.

## 2. Tạo, đọc và di chuyển giữa các kỳ

Các cách thường gặp, giả sử đã import các lớp tương ứng:

```java
YearMonth explicit = YearMonth.of(2024, 2);
YearMonth parsed = YearMonth.parse("2024-02");
YearMonth fromDate = YearMonth.from(LocalDate.of(2024, 2, 29));

int year = explicit.getYear();
int monthNumber = explicit.getMonthValue();

YearMonth next = explicit.plusMonths(1);
YearMonth previous = explicit.minusMonths(1);
YearMonth nextYear = explicit.plusYears(1);
```

Định dạng mặc định khi `parse`/`toString` với các năm thông dụng là `uuuu-MM`, chẳng hạn `2024-02`. Chuỗi `02/2024` cần bộ định dạng phù hợp, không phải định dạng mặc định. Chuỗi chỉ chứa `02` cũng chưa xác định một kỳ vì thiếu năm.

Để hiển thị theo cách khác, có thể định dạng mà vẫn giữ `YearMonth` làm dữ liệu:

```java
DateTimeFormatter display = DateTimeFormatter.ofPattern("MM/uuuu");
String label = explicit.format(display); // 02/2024
```

Đây là đoạn minh họa với `DateTimeFormatter` từ `java.time.format`. Chuỗi hiển thị không nên trở thành cơ sở cho phép tính hay sắp xếp thời gian. Ví dụ sắp xếp từ điển các nhãn `MM/uuuu` sẽ ưu tiên tháng trước năm, không theo thứ tự kỳ thực tế.

`plusMonths` xử lý đổi năm đúng theo lịch:

- `2023-12.plusMonths(1)` cho `2024-01`.
- `2024-01.minusMonths(1)` cho `2023-12`.
- `2024-02.plusMonths(12)` cho `2025-02`.

Không tự tăng `monthNumber++` rồi duy trì các nhánh tháng 13 hoặc tháng 0. Cũng không cộng `30` ngày để giả lập một tháng; độ dài tháng thay đổi.

## 3. Chuyển kỳ báo cáo thành khoảng ngày

Với một kỳ `period`, có ba mốc hữu ích:

```java
LocalDate firstDay = period.atDay(1);
LocalDate lastDay = period.atEndOfMonth();
LocalDate nextFirstDay = period.plusMonths(1).atDay(1);
```

Đối với tháng 02/2024:

| Mốc | Giá trị |
| --- | --- |
| Ngày đầu tháng | `2024-02-01` |
| Ngày cuối tháng | `2024-02-29` |
| Ngày đầu tháng tiếp theo | `2024-03-01` |

### 3.1. Ưu tiên khoảng nửa mở cho việc lọc dữ liệu

Một hợp đồng dễ ghép các kỳ liền nhau là:

**[ngày đầu tháng, ngày đầu tháng tiếp theo)**

Ngày đầu được lấy; ngày kết thúc bị loại. Điều kiện thành viên:

```java
boolean inside = !date.isBefore(firstDay)
        && date.isBefore(nextFirstDay);
```

Khoảng tháng 02/2024 chứa 29/02 nhưng không chứa 01/03. Khoảng tháng 03 bắt đầu đúng tại mốc mà tháng 02 kết thúc, nên một ngày không bị tính hai lần chỉ vì hai kỳ dùng chung ranh giới.

Nếu dữ liệu thật sự chỉ có `LocalDate`, khoảng đóng từ ngày đầu đến `atEndOfMonth()` cũng có thể dùng khi hợp đồng ghi rõ cả hai đầu đều được tính. Điều quan trọng là tên biến và toán tử lọc phải thống nhất; không đặt tên `toExclusive` rồi dùng `<=`.

### 3.2. Không tạo “giây cuối cùng của tháng”

Với dữ liệu có thời gian, `23:59:59` chưa phải mọi giá trị cuối ngày vì còn phần giây lẻ. Dùng `23:59:59.999` cũng gắn logic với độ chính xác mili giây của một cách lưu trữ cụ thể.

Ranh giới kết thúc loại trừ tránh việc phải tìm giá trị cuối cùng trước tháng sau:

```sql
WHERE occurred_at >= :fromInclusive
  AND occurred_at <  :toExclusive
```

Đây là điều kiện SQL minh họa với tham số; hai tham số phải có kiểu và ý nghĩa thời gian phù hợp với cột thực tế. `YearMonth` chưa tự quyết định chúng là ngày địa phương, ngày giờ địa phương hay thời điểm UTC.

### 3.3. Khi dữ liệu lưu bằng Instant, chọn vùng trước khi tạo ranh giới

Một kỳ báo cáo tháng theo giờ của đơn vị phải có `ZoneId` nghiệp vụ. Sau khi đã chọn vùng, có thể tạo hai mốc:

```java
Instant fromInclusive =
        period.atDay(1).atStartOfDay(businessZone).toInstant();
Instant toExclusive =
        period.plusMonths(1).atDay(1)
                .atStartOfDay(businessZone).toInstant();
```

Đoạn minh họa giả sử `period` là `YearMonth` và `businessZone` là `ZoneId` đã xác định. [LocalDate.atStartOfDay(ZoneId)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId)) chọn thời gian hợp lệ sớm nhất của ngày theo quy tắc vùng; không nên mặc định mọi vùng luôn có một mốc 00:00 hợp lệ trong mọi ngày lịch sử.

Không tính mốc cuối bằng cách lấy mốc đầu rồi cộng `30 * 24` giờ. Tháng có số ngày khác nhau; tại các vùng có chuyển đổi giờ, số giờ đã trôi qua giữa hai ranh giới lịch còn có thể thay đổi.

Việc chọn vùng cần nhất quán cho toàn bộ báo cáo. Múi giờ máy chủ không tự trở thành múi giờ nghiệp vụ chỉ vì chương trình đang chạy trên máy đó.

## 4. Hạn theo tháng cần thêm một chính sách ngày

`YearMonth` chỉ xác định tháng đến hạn. Để có ngày đến hạn, phải trả lời: **ngày mong muốn không tồn tại trong tháng thì xử lý thế nào?**

Ví dụ hạn danh nghĩa ngày 31:

| Chính sách | Tháng 02/2024 | Ý nghĩa |
| --- | --- | --- |
| Bắt buộc đúng ngày | Từ chối vì không có ngày 31 | Người gọi phải sửa đầu vào hoặc chọn quy tắc khác |
| Ngày danh nghĩa hoặc cuối tháng nếu thiếu | `2024-02-29` | Giữ ngày danh nghĩa cho các tháng khác |
| Luôn cuối tháng | `2024-02-29` | Không dùng ngày danh nghĩa, tháng nào cũng lấy ngày cuối |

Hai chính sách sau cùng cho kết quả giống nhau khi ngày danh nghĩa là 31, nhưng không luôn giống nhau. Nếu ngày danh nghĩa là 30 thì tháng 03 theo chính sách thứ hai là 30/03, còn “luôn cuối tháng” là 31/03.

### 4.1. atDay() kiểm tra đúng ngày, không tự lùi về cuối tháng

`isValidDay(day)` cho biết ngày có tồn tại trong tháng này hay không. `atDay(day)` tạo `LocalDate` nếu hợp lệ và ném `DateTimeException` nếu không hợp lệ.

```java
YearMonth february = YearMonth.of(2024, 2);

boolean valid = february.isValidDay(30); // false
LocalDate end = february.atEndOfMonth(); // 2024-02-29
// february.atDay(30) se nem DateTimeException.
```

Không nhầm `atDay(31)` với một yêu cầu “cứ lấy ngày cuối tháng”. Phương thức này có hợp đồng kiểm tra nghiêm ngặt.

### 4.2. Lùi về cuối tháng phải được viết thành chính sách rõ ràng

Nếu chính sách chọn ngày danh nghĩa hoặc ngày cuối khi thiếu, công thức là:

```java
int actualDay = Math.min(nominalDay, targetMonth.lengthOfMonth());
LocalDate dueDate = targetMonth.atDay(actualDay);
```

Phải xác thực `nominalDay` thuộc `1..31` trước. Nếu chỉ dùng `Math.min` mà nhận `99`, chương trình sẽ âm thầm chuyển một đầu vào sai thành ngày cuối tháng. Nếu nhận `0` hoặc số âm, phép lấy min cũng không biến nó thành ngày hợp lệ.

`lengthOfMonth()` xét cả năm, vì thế tháng 02/2024 có 29 ngày, còn tháng 02/2023 có 28. Không duy trì bảng độ dài tháng cố định và quên năm nhuận.

Nếu chính sách thực sự là cuối tháng, gọi trực tiếp `targetMonth.atEndOfMonth()` thể hiện ý định rõ hơn việc giả vờ luôn có ngày danh nghĩa 31.

### 4.3. Ngày lịch và ngày làm việc là hai tầng

Ngày cuối tháng có thể rơi vào cuối tuần hoặc ngày nghỉ của đơn vị. `YearMonth` không chứa lịch nghỉ và không biết có nên dời hạn về trước hay về sau.

Một thiết kế rõ có thể gồm:

1. Từ kỳ và quy tắc ngày tạo **hạn theo lịch**.
2. Áp dụng chính sách ngày làm việc nếu nghiệp vụ yêu cầu.
3. Áp dụng giờ chốt và múi giờ nếu cần một thời điểm đến hạn.

Không tự thêm quy tắc dời ngày chỉ vì đó là ngày nghỉ. Việc dời sang tháng mới có thể ảnh hưởng tháng gốc của hạn; cần giữ riêng kỳ nghiệp vụ và ngày đến hạn sau điều chỉnh.

## 5. Tránh hạn bị lệch dần khi cộng tháng liên tiếp

Xét một lịch định kỳ muốn đến hạn vào ngày 31 mỗi tháng, thiếu thì lấy cuối tháng:

```java
LocalDate january31 = LocalDate.of(2024, 1, 31);
LocalDate february29 = january31.plusMonths(1);
LocalDate march29 = february29.plusMonths(1);
```

Kết quả cuối là 29/03. Khi cộng từ 29/02, đối tượng không còn thông tin “ngày danh nghĩa ban đầu là 31”. Nó chỉ biết ngày hiện tại là 29.

Trong khi đó:

```java
LocalDate march31 = january31.plusMonths(2);
```

cho 31/03. Phép cộng trực tiếp và hai lần cộng một tháng có thể khác nhau do việc điều chỉnh ngày tại tháng trung gian.

Để lịch định kỳ giữ đúng ý định, nên lưu riêng:

- Kỳ gốc, chẳng hạn `YearMonth.of(2024, 1)`.
- Ngày danh nghĩa, chẳng hạn `31`.
- Chính sách khi thiếu ngày.
- Chỉ số kỳ cần tính.

Với mỗi kỳ, tính `targetMonth = firstMonth.plusMonths(index)` rồi áp dụng lại chính sách ngày danh nghĩa. Không lấy hạn đã bị rút ngắn của kỳ trước làm nguồn duy nhất cho kỳ sau.

| Kỳ | Giữ ngày danh nghĩa 31 | Cộng tiếp từ ngày kết quả trước |
| --- | --- | --- |
| 01/2024 | 31/01 | 31/01 |
| 02/2024 | 29/02 | 29/02 |
| 03/2024 | 31/03 | 29/03 |

Đây là quyết định mô hình nghiệp vụ, không phải lỗi của `LocalDate.plusMonths`. Phương thức đó xử lý đúng đầu vào hiện tại; nó không thể nhớ một quy tắc định kỳ đã không được lưu.

## 6. Chương trình Java 17+ đầy đủ

Lưu thành `YearMonthPeriodDemo.java`:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class YearMonthPeriodDemo {
    record DateRange(LocalDate fromInclusive, LocalDate toExclusive) {
        DateRange {
            Objects.requireNonNull(fromInclusive);
            Objects.requireNonNull(toExclusive);
            if (toExclusive.isBefore(fromInclusive)) {
                throw new IllegalArgumentException("Reversed range");
            }
        }

        boolean contains(LocalDate date) {
            Objects.requireNonNull(date);
            return !date.isBefore(fromInclusive)
                    && date.isBefore(toExclusive);
        }
    }

    static DateRange reportingRange(YearMonth period) {
        Objects.requireNonNull(period);
        return new DateRange(
                period.atDay(1),
                period.plusMonths(1).atDay(1));
    }

    static LocalDate dueOnDayOrMonthEnd(
            YearMonth targetMonth, int nominalDay) {
        Objects.requireNonNull(targetMonth);
        if (nominalDay < 1 || nominalDay > 31) {
            throw new IllegalArgumentException("Day must be 1..31");
        }
        return targetMonth.atDay(
                Math.min(nominalDay, targetMonth.lengthOfMonth()));
    }

    public static void main(String[] args) {
        YearMonth february = YearMonth.parse("2024-02");
        DateRange range = reportingRange(february);
        System.out.println("period = " + february);
        System.out.println("length = " + february.lengthOfMonth());
        System.out.println("start = " + range.fromInclusive());
        System.out.println("end exclusive = " + range.toExclusive());
        System.out.println("month end = " + february.atEndOfMonth());
        System.out.println("contains leap day = "
                + range.contains(LocalDate.of(2024, 2, 29)));
        System.out.println("contains next month = "
                + range.contains(LocalDate.of(2024, 3, 1)));
        System.out.println("valid day 30 = " + february.isValidDay(30));

        try {
            february.atDay(30);
        } catch (DateTimeException ex) {
            System.out.println("strict day -> "
                    + ex.getClass().getSimpleName());
        }

        YearMonth first = YearMonth.of(2024, 1);
        for (int index = 0; index < 3; index++) {
            YearMonth target = first.plusMonths(index);
            System.out.println("anchored " + target + " = "
                    + dueOnDayOrMonthEnd(target, 31));
        }

        LocalDate january31 = first.atDay(31);
        LocalDate sequential = january31.plusMonths(1).plusMonths(1);
        LocalDate direct = january31.plusMonths(2);
        System.out.println("sequential date = " + sequential);
        System.out.println("direct date = " + direct);

        YearMonth from = YearMonth.of(2023, 12);
        YearMonth to = YearMonth.of(2024, 3);
        System.out.println("month distance = "
                + ChronoUnit.MONTHS.between(from, to));
        for (YearMonth cursor = from;
                cursor.isBefore(to);
                cursor = cursor.plusMonths(1)) {
            System.out.println("report = " + cursor);
        }

        Clock fixed = Clock.fixed(
                Instant.parse("2024-02-29T23:30:00Z"),
                ZoneOffset.UTC);
        System.out.println("current UTC period = " + YearMonth.now(fixed));
        System.out.println("current business period = " + YearMonth.now(
                fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))));
        System.out.println("unchanged period = " + february);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 YearMonthPeriodDemo.java
java YearMonthPeriodDemo
```

Stdout:

```text
period = 2024-02
length = 29
start = 2024-02-01
end exclusive = 2024-03-01
month end = 2024-02-29
contains leap day = true
contains next month = false
valid day 30 = false
strict day -> DateTimeException
anchored 2024-01 = 2024-01-31
anchored 2024-02 = 2024-02-29
anchored 2024-03 = 2024-03-31
sequential date = 2024-03-29
direct date = 2024-03-31
month distance = 3
report = 2023-12
report = 2024-01
report = 2024-02
current UTC period = 2024-02
current business period = 2024-03
unchanged period = 2024-02
```

`DateRange` trong ví dụ biểu diễn khoảng nửa mở trên `LocalDate`, cho phép hai đầu bằng nhau để biểu diễn khoảng rỗng nhưng từ chối khoảng đảo ngược. `reportingRange` luôn tạo một tháng hoàn chỉnh.

`dueOnDayOrMonthEnd` có tên thể hiện chính sách lùi về cuối tháng. Nó không nhận một ngày đã điều chỉnh ở kỳ trước, nên vòng lặp tạo hạn quay lại 31/03 thay vì tiếp tục giữ 29/03.

Dòng `unchanged period` cho thấy các phép tính không sửa `february`. Để cập nhật biến đang duyệt, phải gán lại kết quả `cursor = cursor.plusMonths(1)`.

## 7. Duyệt kỳ và đo khoảng cách theo tháng

Đếm số kỳ từ tháng 12/2023 đến trước tháng 03/2024:

```java
long count = ChronoUnit.MONTHS.between(
        YearMonth.of(2023, 12),
        YearMonth.of(2024, 3)); // 3
```

Ba kỳ tương ứng là 12/2023, 01/2024 và 02/2024. Nếu muốn gồm cả tháng 03, đó là một hợp đồng khác; với khoảng tăng dần trên các kỳ tháng, có thể chuyển đầu cuối bao gồm sang đầu cuối loại trừ bằng `endInclusive.plusMonths(1)` khi còn trong miền biểu diễn.

Đối với đầu cuối trước đầu đầu, `between` có thể trả số âm. Một API chỉ nhận khoảng tăng dần nên xác thực và từ chối đầu vào đảo ngược thay vì dùng `Math.abs` để âm thầm đổi ý nghĩa yêu cầu.

Vòng lặp `YearMonth` phù hợp để:

- Sinh đủ danh sách kỳ trong một biểu đồ, kể cả kỳ chưa có dữ liệu.
- Khởi tạo các ô thống kê giá trị `0` cho tháng thiếu.
- Tính các hạn định kỳ từ kỳ gốc.
- Giới hạn báo cáo theo một chuỗi tháng xác định.

Không duyệt từng ngày rồi loại các ngày không phải ngày 01 chỉ để tạo danh sách tháng. Mô hình và bước duyệt đều nên theo đúng đơn vị tháng.

Nếu đưa `YearMonth` vào `Map` hoặc tập hợp, dùng `equals` để so sánh giá trị; không dùng `==`. `YearMonth` có thứ tự thời gian tự nhiên qua `compareTo`, `isBefore` và `isAfter`.

## 8. “Tháng hiện tại” phụ thuộc đồng hồ và múi giờ

Giá trị `YearMonth.of(2024, 2)` tự nó không có múi giờ. Nhưng để trả lời “bây giờ là tháng nào?”, chương trình phải lấy một thời điểm hiện tại và diễn giải theo vùng.

`YearMonth.now()` dùng đồng hồ và múi giờ mặc định của hệ thống. Điều này có thể không đúng với vùng của đơn vị sử dụng. `YearMonth.now(zone)` chọn rõ vùng; `YearMonth.now(clock)` còn cho phép kiểm soát đồng hồ để kiểm chứng.

Ví dụ trong chương trình giữ cố định thời điểm `2024-02-29T23:30:00Z`:

- Theo UTC, vẫn là tháng 02/2024.
- Theo `Asia/Ho_Chi_Minh` trong ví dụ, đã là sáng 01/03/2024, nên kỳ hiện tại là tháng 03/2024.

Hai kết quả không mâu thuẫn vì chúng dùng hai cách diễn giải địa phương của cùng thời điểm.

Đối với báo cáo quá khứ, nên truyền kỳ cụ thể vào hàm thay vì hàm tự gọi `now()`. Nếu một tác vụ chạy lại sau khi sang tháng mới, kỳ cần xử lý vẫn phải theo yêu cầu ban đầu, không bị đổi theo ngày chạy lại.

Tương tự, nếu một quy trình có nhiều bước và cần cùng “kỳ hiện tại”, xác định kỳ một lần ở đầu quy trình rồi truyền xuống. Không đọc đồng hồ lại ở mỗi bước ngay sát ranh giới tháng.

## 9. Tách kỳ, hạn ngày và thời điểm hết hạn

Ba giá trị sau không đồng nhất:

| Giá trị | Ví dụ | Thông tin còn cần nếu muốn xác định thời điểm |
| --- | --- | --- |
| Kỳ | `2024-02` | Ngày, giờ và quy tắc vùng |
| Ngày đến hạn | `2024-02-29` | Giờ chốt, vùng và quy ước bao gồm ngày |
| Thời điểm hết hạn loại trừ | Một `Instant` cụ thể | Đã có mốc trên dòng thời gian |

Nếu quy tắc cho phép sử dụng hết ngày đến hạn theo lịch địa phương, một cách mô hình hóa là lấy đầu ngày tiếp theo làm mốc kết thúc loại trừ. Nhưng điều này chỉ đúng khi đó là chính sách đã chọn; hạn lúc 17 giờ không thể dùng chung quy tắc đó.

Giữ `YearMonth` làm khóa kỳ giúp việc hạn được điều chỉnh sang ngày đầu tháng sau không làm mất liên hệ với kỳ gốc. Ví dụ kỳ dịch vụ tháng 02 vẫn là `2024-02` dù quy tắc nghiệp vụ đưa ngày xử lý sang đầu tháng 03.

Khi trao đổi dữ liệu, chuỗi chuẩn `2024-02` là cách biểu diễn gọn cho kỳ thông dụng. Lớp đọc/ghi dữ liệu vẫn phải cấu hình cách chuyển đổi phù hợp với công nghệ đang dùng; Java không tự bảo đảm mọi bộ tuần tự hóa hoặc mọi cơ sở dữ liệu đều có kiểu `YearMonth` gốc.

Nếu hệ thống lưu kỳ bằng ngày đầu tháng hoặc cặp cột năm/tháng, hãy ghi rõ đó là biểu diễn lưu trữ và kiểm tra ràng buộc. Tránh để một ngày đại diện giả bị dùng nhầm như ngày giao dịch hoặc ngày đến hạn thực.

## 10. Giới hạn và lỗi thường gặp

`YearMonth` có miền năm hữu hạn theo API. Ví dụ tạo khoảng báo cáo cho tháng cuối cùng của miền bằng cách cộng một tháng sẽ vượt miền. Ứng dụng thường dùng một phạm vi năm hẹp hơn; cần xác thực đầu vào theo phạm vi được hỗ trợ thay vì dựa vào giả định mọi phép cộng đều thành công.

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng một số tháng `1..12` làm khóa kỳ | Trộn dữ liệu của nhiều năm | Dùng năm và tháng cùng nhau |
| Dùng `LocalDate` ngày 01 nhưng không nói đó là ngày đại diện | Nhầm kỳ với ngày thực | Mô hình kỳ bằng `YearMonth` |
| Cộng 30 ngày để sang tháng sau | Lệch kỳ | Dùng `plusMonths` |
| Gọi `atDay(31)` và mong tự lấy cuối tháng | Ngoại lệ ở tháng ngắn | Dùng `atEndOfMonth` hoặc chính sách có tên rõ |
| Lấy min mà không kiểm tra ngày danh nghĩa | Đầu vào 99 có thể bị che thành ngày cuối | Xác thực `1..31` trước |
| Cộng tháng từ hạn đã điều chỉnh kỳ trước | Hạn bị lệch dần | Tính từng kỳ từ ngày danh nghĩa gốc |
| Lấy “giây cuối tháng” làm đầu cuối | Bỏ sót dữ liệu phần giây | Dùng đầu tháng sau loại trừ |
| Dùng giờ máy chủ để chọn kỳ nghiệp vụ | Lệch tháng gần ranh giới | Chọn vùng và đồng hồ rõ ràng |
| Không gán lại kết quả `plusMonths` | Biến duyệt không thay đổi | Gán kết quả mới |
| Coi hết tháng luôn đồng nghĩa đúng 30 ngày hoặc số giờ cố định | Sai độ dài khoảng | Tạo ranh giới theo lịch và vùng |

## 11. Tự kiểm chứng và thực hành

1. Tạo khoảng cho tháng 02/2023 và tháng 02/2024. Kiểm tra `lengthOfMonth`, `atEndOfMonth` và ngày đầu tháng sau.
2. Kiểm tra `contains` với ngày ngay trước kỳ, ngày đầu kỳ, ngày cuối kỳ và ngày đầu kỳ tiếp theo. Chỉ hai trường hợp ở trong kỳ phải được chấp nhận.
3. Tạo hạn ngày danh nghĩa 30 từ tháng 01 đến tháng 03/2024. Kết quả cần là 30/01, 29/02, 30/03; so sánh với chính sách luôn cuối tháng.
4. Tạo hạn ngày danh nghĩa 31 trong năm 2023. Tháng 02 dùng 28/02, tháng 03 phải trở lại 31/03 nếu dùng chính sách đã mô tả.
5. Thử ngày danh nghĩa `0`, `32` và `99`. Hàm phải báo đầu vào sai, không tự sửa thành một ngày có vẻ hợp lệ.
6. Duyệt từ 11/2023 đến trước 02/2024. Phải sinh đúng ba kỳ và xử lý đổi năm tự nhiên.
7. Dùng một `Clock.fixed` sát ranh giới tháng để kiểm tra chọn kỳ theo UTC và theo vùng nghiệp vụ. Không cần chờ đồng hồ thật sang tháng.
8. Viết hàm nhận một kỳ và một vùng, trả hai `Instant` làm ranh giới tháng. Kiểm tra dữ liệu đúng tại mốc đầu được lấy và đúng tại mốc cuối bị loại.
9. Giả sử hạn ngày nghỉ phải dời về ngày làm việc trước đó. Mô tả chỗ áp dụng chính sách ngày làm việc mà không sửa cách nhận diện kỳ tháng.
10. Giải thích vì sao một kỳ báo cáo, một ngày đến hạn và một thời điểm hết hạn nên được lưu hoặc truyền bằng các kiểu có ý nghĩa riêng.

Điểm cần giữ rõ là `YearMonth` xác định kỳ; chính sách ngày xác định hạn theo lịch; quy tắc giờ và múi giờ mới xác định một mốc trên dòng thời gian. Khi mỗi bước có hợp đồng riêng, việc xử lý tháng ngắn, năm nhuận và ranh giới kỳ trở nên nhất quán.
