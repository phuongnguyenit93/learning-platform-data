# Đầu tháng, cuối tháng, đầu năm và cuối năm

## Xác định biên của kỳ lịch thay vì tự đếm ngày

Một báo cáo cần biết tháng chứa ngày `2024-02-18` bắt đầu và kết thúc vào ngày nào. Nếu tự cộng 30 ngày hoặc mặc định ngày cuối luôn là 31, kết quả sẽ sai ở nhiều tháng.

`java.time` cung cấp các bộ điều chỉnh ngày (temporal adjusters) để diễn đạt trực tiếp những yêu cầu như “ngày đầu tháng” hay “ngày cuối năm”. Với `LocalDate`, ta nhận lại một giá trị ngày đã điều chỉnh; ngày nguồn không bị sửa.

Trong bài này, tháng và năm là kỳ lịch ISO: tháng theo lịch thông thường và năm từ 01/01 đến 31/12. Năm tài chính, ngày làm việc cuối tháng hay kỳ chốt riêng của doanh nghiệp là những quy tắc khác.

## 1. Bốn phép điều chỉnh cơ bản

Dùng `date.with(adjuster)` cùng các phương thức trong `TemporalAdjusters`:

| Yêu cầu | Cách viết |
| --- | --- |
| Ngày đầu tháng chứa `date` | `date.with(TemporalAdjusters.firstDayOfMonth())` |
| Ngày cuối tháng chứa `date` | `date.with(TemporalAdjusters.lastDayOfMonth())` |
| Ngày đầu năm chứa `date` | `date.with(TemporalAdjusters.firstDayOfYear())` |
| Ngày cuối năm chứa `date` | `date.with(TemporalAdjusters.lastDayOfYear())` |

Các phép điều chỉnh tính biên theo chính kỳ chứa ngày đầu vào, không theo tháng/năm hiện tại của máy. [Tài liệu `TemporalAdjusters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

Với `date = 2024-02-18`:

```text
Tháng 02/2024:
2024-02-01 ───────── 2024-02-18 ───────── 2024-02-29
đầu tháng           ngày nguồn          cuối tháng

Năm 2024:
2024-01-01 ───────── 2024-02-18 ───────── 2024-12-31
đầu năm             ngày nguồn          cuối năm
```

Đây là điều chỉnh theo vị trí trong lịch, khác với “thêm một tháng” hoặc “thêm 30 ngày”. Đặt ngày về cuối tháng không có nghĩa luôn cộng cùng một số ngày.

## 2. Chương trình hoàn chỉnh

Lưu dưới tên `CalendarBoundariesDemo.java`. Chương trình sử dụng Java 17 trở lên và thư viện chuẩn:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;

public class CalendarBoundariesDemo {
    private static boolean contains(
            LocalDate startInclusive,
            LocalDate endExclusive,
            LocalDate candidate) {
        return !candidate.isBefore(startInclusive)
                && candidate.isBefore(endExclusive);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 18);

        LocalDate monthStart =
                date.with(TemporalAdjusters.firstDayOfMonth());
        LocalDate monthEnd =
                date.with(TemporalAdjusters.lastDayOfMonth());
        LocalDate yearStart =
                date.with(TemporalAdjusters.firstDayOfYear());
        LocalDate yearEnd =
                date.with(TemporalAdjusters.lastDayOfYear());

        LocalDate nextMonthStart =
                date.with(TemporalAdjusters.firstDayOfNextMonth());
        LocalDate nextYearStart =
                date.with(TemporalAdjusters.firstDayOfNextYear());

        System.out.println("original=" + date);
        System.out.println("monthStart=" + monthStart);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("yearStart=" + yearStart);
        System.out.println("yearEnd=" + yearEnd);
        System.out.println("nextMonthStart=" + nextMonthStart);
        System.out.println("nextYearStart=" + nextYearStart);

        System.out.println("normalFebruaryEnd="
                + LocalDate.of(2023, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("century1900End="
                + LocalDate.of(1900, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("century2000End="
                + LocalDate.of(2000, 2, 10)
                        .with(TemporalAdjusters.lastDayOfMonth()));

        YearMonth month = YearMonth.from(date);
        System.out.println("yearMonthStart=" + month.atDay(1));
        System.out.println("yearMonthEnd=" + month.atEndOfMonth());

        System.out.println("monthDayCount="
                + ChronoUnit.DAYS.between(monthStart, nextMonthStart));
        System.out.println("yearDayCount="
                + ChronoUnit.DAYS.between(yearStart, nextYearStart));

        System.out.println("containsLastDay="
                + contains(monthStart, nextMonthStart, monthEnd));
        System.out.println("containsNextMonth="
                + contains(monthStart, nextMonthStart, nextMonthStart));

        LocalDate marchReference = LocalDate.of(2024, 3, 18);
        LocalDate marchStart =
                marchReference.with(TemporalAdjusters.firstDayOfMonth());
        LocalDate aprilStart =
                marchReference.with(TemporalAdjusters.firstDayOfNextMonth());

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime start = marchStart.atStartOfDay(paris);
        ZonedDateTime end = aprilStart.atStartOfDay(paris);

        System.out.println("parisStart=" + start);
        System.out.println("parisEnd=" + end);
        System.out.println("parisElapsedHours="
                + Duration.between(start.toInstant(), end.toInstant()).toHours());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CalendarBoundariesDemo.java
java CalendarBoundariesDemo
```

Stdout với dữ liệu múi giờ chứa các quy tắc năm 2024 dùng trong ví dụ:

```text
original=2024-02-18
monthStart=2024-02-01
monthEnd=2024-02-29
yearStart=2024-01-01
yearEnd=2024-12-31
nextMonthStart=2024-03-01
nextYearStart=2025-01-01
normalFebruaryEnd=2023-02-28
century1900End=1900-02-28
century2000End=2000-02-29
yearMonthStart=2024-02-01
yearMonthEnd=2024-02-29
monthDayCount=29
yearDayCount=366
containsLastDay=true
containsNextMonth=false
parisStart=2024-03-01T00:00+01:00[Europe/Paris]
parisEnd=2024-04-01T00:00+02:00[Europe/Paris]
parisElapsedHours=743
```

Chương trình dùng ngày cố định để kết quả có thể kiểm chứng độc lập với ngày chạy.

## 3. Cuối tháng phụ thuộc cả tháng lẫn năm

Tháng có thể dài 28, 29, 30 hoặc 31 ngày. Năm ảnh hưởng trực tiếp đến tháng 02. Các dòng kiểm tra trong chương trình cho thấy:

- Tháng 02/2023 kết thúc ở ngày 28.
- Tháng 02/2024 kết thúc ở ngày 29.
- Tháng 02/1900 kết thúc ở ngày 28.
- Tháng 02/2000 kết thúc ở ngày 29.

Vì vậy, một bảng cố định “tháng 02 có 28 ngày”, hoặc quy tắc đơn giản chỉ kiểm tra chia hết cho 4, không thay thế đầy đủ quy tắc năm nhuận ISO.

Khi dùng `lastDayOfMonth()`, thư viện lấy giới hạn ngày phù hợp với tháng/năm của giá trị đang điều chỉnh. Không cần viết thêm các nhánh cho từng tháng. [Tài liệu ngày cuối tháng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#lastDayOfMonth())

Tương tự, ngày cuối năm ISO vẫn là 31/12, nhưng vị trí của nó trong năm có thể là ngày thứ 365 hoặc 366. Tính số ngày trong một năm từ hai biên đầu năm liên tiếp sẽ bao quát khác biệt đó.

## 4. Cách viết bằng các trường trực tiếp hoặc `YearMonth`

Với `LocalDate`, có thể dùng:

```java
LocalDate firstDate = date.withDayOfMonth(1);
LocalDate lastDate = date.withDayOfMonth(date.lengthOfMonth());

LocalDate firstDateOfYear = date.withDayOfYear(1);
LocalDate lastDateOfYear = date.withDayOfYear(date.lengthOfYear());
```

Đây là đoạn minh họa với biến `date` đã có. Các cách viết này nêu trực tiếp trường cần thay; bộ điều chỉnh có tên thường dễ đọc khi muốn biểu đạt một quy tắc lịch. Chọn cách nhất quán và rõ nghĩa trong mã, không cần viết cả hai để làm cùng một việc.

Nếu đầu vào đã là một kỳ tháng, giữ `YearMonth`:

```java
YearMonth reportingMonth = YearMonth.of(2024, 2);
LocalDate startDate = reportingMonth.atDay(1);
LocalDate endDateInclusive = reportingMonth.atEndOfMonth();
```

`YearMonth` không giữ ngày, giờ hoặc múi giờ. `atDay(1)` tạo ngày đầu tháng; `atEndOfMonth()` tạo ngày cuối phù hợp với năm và tháng. [Tài liệu `YearMonth`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html)

Cách này tránh tạo một ngày giữa tháng tùy ý chỉ để rồi tìm biên tháng. Chương trình đầy đủ cũng chứng minh kết quả từ `YearMonth` trùng biên tìm được từ ngày nguồn.

## 5. Phân biệt “ngày cuối” và “cận cuối không bao gồm”

Hai đại lượng liên quan nhưng khác nhau:

```text
Ngày cuối tháng 02/2024:
    2024-02-29

Khoảng biểu diễn cả tháng:
    [2024-02-01, 2024-03-01)
```

Dấu `[` nghĩa là lấy cận đầu; dấu `)` nghĩa là không lấy cận cuối.

Khi cần hiển thị ngày cuối để người học thấy lịch, dùng `lastDayOfMonth()`. Khi cần lọc dữ liệu thuộc cả tháng, cách dùng đầu tháng kế tiếp làm cận cuối thường rõ ràng:

```java
LocalDate startInclusive =
        date.with(TemporalAdjusters.firstDayOfMonth());
LocalDate endExclusive =
        date.with(TemporalAdjusters.firstDayOfNextMonth());

boolean inMonth = !candidate.isBefore(startInclusive)
        && candidate.isBefore(endExclusive);
```

Đây là đoạn minh họa, giả định `date` và `candidate` là `LocalDate`.

Quy tắc tương ứng cho năm:

```java
LocalDate startInclusive =
        date.with(TemporalAdjusters.firstDayOfYear());
LocalDate endExclusive =
        date.with(TemporalAdjusters.firstDayOfNextYear());
```

Với tháng 12, cận cuối tự chuyển sang 01/01 năm sau. Không cần tự đặt lại tháng, ngày và năm bằng nhiều nhánh.

Hai khoảng tháng kề nhau có thể dùng chung biên mà không chồng lặp:

```text
Tháng 02: [2024-02-01, 2024-03-01)
Tháng 03: [2024-03-01, 2024-04-01)
```

Đừng đặt tên `endDate` chung chung nếu có thể nhầm cận bao gồm hay không bao gồm. Các tên `endDateInclusive` và `endExclusive` giúp người gọi dùng đúng phép so sánh.

## 6. Khi dữ liệu là thời điểm, còn cần múi giờ xác định kỳ

`LocalDate` chỉ biểu diễn ngày; nó không có giờ và múi giờ. “Đầu tháng” theo ngày chưa tự xác định một `Instant`.

Nếu cần lọc sự kiện theo tháng tại một vùng cụ thể:

1. Xác định biên ngày trong lịch của vùng đó.
2. Chuyển từng biên bằng `atStartOfDay(zone)`.
3. Dùng các `Instant` thu được làm cận đầu bao gồm, cận cuối không bao gồm.

Chương trình minh họa tháng 03/2024 tại Paris:

```text
Đầu tháng:       2024-03-01 00:00 +01:00
Đầu tháng sau:   2024-04-01 00:00 +02:00
Ngày lịch:       31 ngày
Giờ trôi qua:    743 giờ
```

Tháng này có thay đổi offset, nên tổng giờ không phải `31 * 24`. Biên kỳ lịch phải được tính theo lịch và vùng; không thay bằng một khoảng giây cố định.

`atStartOfDay(zone)` chọn thời gian hợp lệ sớm nhất của ngày theo quy tắc vùng. Trong một số trường hợp chuyển đổi múi giờ, thời gian đó không nhất thiết là `00:00`. [Tài liệu `LocalDate.atStartOfDay`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId))

Cũng cần phân biệt:

```java
// Đoạn minh họa: điều chỉnh ngày nhưng không tự đặt giờ về đầu ngày.
ZonedDateTime changedDate =
        originalZoned.with(TemporalAdjusters.firstDayOfMonth());
```

Nếu `originalZoned` có giờ buổi chiều, thao tác điều chỉnh ngày không phải yêu cầu “đầu tháng lúc đầu ngày”. Muốn một biên thời điểm của tháng, hãy biểu đạt cả hai ý như các bước phía trên.

Không dựng cận cuối bằng “ngày cuối lúc 23:59:59” rồi giả định đã bao gồm mọi dữ liệu. Dữ liệu có thể có phần lẻ của giây và độ chính xác khác nhau. Khoảng đến đầu kỳ sau giúp tránh phụ thuộc cách chọn “thời điểm cuối cùng” trước biên.

## 7. Những lỗi dễ gặp

### Quên nhận giá trị trả về

`LocalDate` bất biến. Đoạn sau không đổi biến `date`:

```java
date.with(TemporalAdjusters.firstDayOfMonth());
```

Hãy giữ kết quả khi cần sử dụng:

```java
LocalDate firstDate =
        date.with(TemporalAdjusters.firstDayOfMonth());
```

Không dựa vào việc một phép điều chỉnh có tạo đối tượng khác hay trả lại đối tượng có thể tái sử dụng; điều quan trọng là giá trị trả về.

### Cộng một tháng rồi trừ một ngày từ ngày bất kỳ

```java
LocalDate mistaken = date.plusMonths(1).minusDays(1);
```

Đoạn này không có nghĩa chung là ngày cuối tháng chứa `date`. Nếu `date` nằm giữa tháng, kết quả cũng thường ở giữa tháng kế tiếp.

Nếu dùng cách “đầu tháng sau trừ một ngày”, phải xác định đầu tháng trước hoặc dùng đúng bộ điều chỉnh:

```java
LocalDate lastDate =
        date.with(TemporalAdjusters.firstDayOfNextMonth()).minusDays(1);
```

Dùng trực tiếp `lastDayOfMonth()` thường nói rõ ý định hơn.

### Dùng ngày 31 cho mọi tháng

`withDayOfMonth(31)` không phải cách yêu cầu ngày cuối hợp lệ. Nó có thể ném lỗi ở tháng không có ngày 31. Dùng giới hạn của tháng hoặc bộ điều chỉnh tương ứng.

### Nhầm kỳ lịch với kỳ nghiệp vụ

`lastDayOfMonth()` có thể là thứ Bảy hoặc Chủ nhật. Nó không có ý nghĩa “ngày làm việc cuối tháng”. Tương tự, `firstDayOfYear()` không tự biết năm tài chính bắt đầu từ tháng 4.

Nếu có lịch nghỉ hoặc kỳ tài chính riêng, cần quy tắc bổ sung và dữ liệu phù hợp; không đổi nghĩa các tên API có sẵn.

## 8. Chọn ngày nguồn và kiểm chứng biên

Nếu báo cáo cần tháng hiện tại của người dùng, hãy xác định vùng làm chuẩn và đọc ngày hiện tại một lần, ví dụ:

```java
ZoneId reportingZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate referenceDate = LocalDate.now(reportingZone);
```

Sau đó tính mọi biên từ `referenceDate`. Không gọi `now()` nhiều lần để tính riêng từng biên, vì thao tác có thể đi qua mốc đổi ngày/tháng/năm. Trong kiểm thử, truyền ngày nguồn cố định hoặc nguồn thời gian có thể điều khiển.

Các ca kiểm chứng có ích:

- Ngày giữa tháng và ngày đã ở đầu/cuối tháng.
- Tháng có 30 và 31 ngày.
- Tháng 02 năm nhuận và năm không nhuận.
- Tháng 12 khi tạo cận đầu tháng sau.
- Ngày 31/12 khi tạo cận đầu năm sau.
- Kỳ lịch của một vùng có thay đổi offset nếu kết quả dùng làm khoảng thời điểm.

Đầu vào đã là ngày đầu hoặc cuối kỳ nên cho cùng **giá trị biên** tương ứng. Kiểm tra bằng `equals`, không so sánh tham chiếu bằng `==`.

## 9. Tự thực hành

1. Từ `2024-02-18`, phương thức nào lấy ngày cuối tháng mà không tự kiểm tra năm nhuận?
2. Để lọc cả tháng 02/2024 theo khoảng nửa mở, cận cuối là ngày nào?
3. Vì sao `plusMonths(1).minusDays(1)` từ một ngày tùy ý chưa chắc là cuối tháng?
4. Đầu tháng trên `LocalDate` có tự là một thời điểm UTC không?
5. `lastDayOfMonth()` có bảo đảm kết quả là ngày làm việc không?

Gợi ý đáp án:

1. `date.with(TemporalAdjusters.lastDayOfMonth())`.
2. `2024-03-01`, không bao gồm ngày ấy.
3. Vì chưa đặt ngày về một biên; phép cộng giữ quan hệ với ngày nguồn.
4. Không; cần vùng hoặc offset và quy tắc chọn thời gian trong ngày.
5. Không; nó là ngày cuối theo lịch, không phải lịch làm việc.

Dùng các phép điều chỉnh có tên để tìm biên ngày, phân biệt rõ ngày cuối với cận cuối không bao gồm, và chỉ chuyển sang thời điểm sau khi đã xác định vùng áp dụng.
