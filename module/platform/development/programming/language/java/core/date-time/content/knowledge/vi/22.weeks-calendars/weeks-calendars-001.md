# Tuần ISO, ngày đầu tuần và năm theo tuần

## Vì sao ngày cuối tháng 12 có thể thuộc tuần 1 của năm sau?

Một báo cáo theo tuần có ngày `2019-12-30`. Nếu chỉ lấy `date.getYear()`, ta nhận năm 2019. Nhưng theo cách đánh số tuần ISO, ngày này là **Thứ Hai của tuần 1, năm theo tuần 2020**.

Ngược lại, `2021-01-01` nằm trong năm lịch 2021 nhưng thuộc **tuần 53 của năm theo tuần 2020**.

Không có mâu thuẫn: ta đang dùng hai cách nhóm ngày khác nhau. Một cách nhóm theo tháng/ngày của năm lịch; cách kia nhóm theo các tuần trọn vẹn. Hiểu ranh giới này giúp tránh báo cáo tách đôi tuần, khóa dữ liệu sai năm và lỗi định dạng chỉ xuất hiện quanh Tết Dương lịch.

Bài này dùng ngày `LocalDate` theo lịch ISO. Trước hết cần hiểu quy tắc tuần, sau đó mới chọn trường hoặc mẫu để đọc, ghi và nhóm dữ liệu.

## 1. Hai tham số định nghĩa cách đánh số tuần

Một tuần dài bảy ngày, nhưng đánh số tuần trong năm còn cần hai lựa chọn:

1. Ngày nào là ngày đầu tuần?
2. Tuần đầu tiên phải có tối thiểu bao nhiêu ngày nằm trong năm mới?

Quy tắc ISO là:

- Bắt đầu tuần vào **Thứ Hai**.
- Tuần 1 phải có **ít nhất bốn ngày** thuộc năm mới.

Trong Java, `WeekFields.ISO` biểu đạt đúng hai lựa chọn này. Một quy tắc chỉ nói “tuần bắt đầu Thứ Hai” vẫn chưa đủ để suy ra cách đánh số tuần của ISO; còn phải biết số ngày tối thiểu của tuần đầu. [Tài liệu `WeekFields`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

Hệ quả dễ nhớ: tuần ISO số 1 là tuần chứa **ngày 04/01**, cũng là tuần chứa **Thứ Năm đầu tiên** của năm.

Tuần 1 không nhất thiết bắt đầu đúng ngày 01/01. Tùy thứ của ngày 01/01, Thứ Hai mở đầu tuần 1 có thể ở cuối tháng 12 năm trước hoặc trong những ngày đầu tháng 1.

## 2. Năm lịch và năm theo tuần

**Năm lịch** của một `LocalDate` là năm mà ngày ấy thuộc về khi viết theo năm–tháng–ngày. Đọc bằng `getYear()`.

**Năm theo tuần (week-based-year)** là năm mà toàn bộ tuần đó được gán vào theo quy tắc đánh số tuần. Trong hệ ISO, một tuần không bị chia làm hai năm theo tuần chỉ vì đi qua 31/12.

Mỗi ngày có thể được biểu diễn theo bộ ba ISO:

```text
năm theo tuần + số tuần trong năm theo tuần + thứ ISO
```

Ví dụ:

```text
2019-12-30 theo ngày lịch
2020-W01-1 theo ngày tuần ISO
     │   │
     │   └── Thứ Hai = 1
     └────── tuần 1 của năm theo tuần 2020
```

`IsoFields.WEEK_BASED_YEAR` và `IsoFields.WEEK_OF_WEEK_BASED_YEAR` cung cấp hai trường năm/tuần này. Thứ trong tuần ISO lấy từ `DayOfWeek`, với Thứ Hai bằng 1 và Chủ nhật bằng 7. [Tài liệu `IsoFields`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)

Bộ ba phải dùng cùng một quy tắc. Ghép năm lịch 2019 với số tuần ISO 1 của ngày 30/12/2019 sẽ tạo một nhãn không còn chỉ đúng tuần của ngày đó.

## 3. Quan sát hai ranh giới năm

### Ranh giới năm 2019 sang 2020

```text
Thứ Hai  Thứ Ba  Thứ Tư  Thứ Năm  Thứ Sáu  Thứ Bảy  Chủ nhật
30/12    31/12   01/01   02/01    03/01   04/01    05/01
└──────────────────── 2020-W01 ───────────────────────────┘
```

Tuần này có năm ngày trong năm 2020, đủ điều kiện là tuần 1 của năm theo tuần 2020. Hai ngày 30 và 31/12/2019 cũng thuộc cùng tuần đó.

### Ranh giới năm 2020 sang 2021

```text
Thứ Hai  Thứ Ba  Thứ Tư  Thứ Năm  Thứ Sáu  Thứ Bảy  Chủ nhật
28/12    29/12   30/12   31/12    01/01   02/01    03/01
└──────────────────── 2020-W53 ───────────────────────────┘

04/01/2021 là Thứ Hai mở đầu 2021-W01
```

Tuần chứa 01/01/2021 chỉ có ba ngày trong năm lịch 2021, nên chưa đủ điều kiện là tuần 1 của năm theo tuần 2021. Nó là tuần cuối của năm theo tuần 2020.

Hai ví dụ cho thấy vì sao chỉ thử các ngày giữa năm thường bỏ sót lỗi tuần/năm.

## 4. Chương trình hoàn chỉnh

Lưu dưới tên `IsoWeekDemo.java`. Chương trình dùng Java 17 trở lên và thư viện chuẩn:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.IsoFields;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;

public class IsoWeekDemo {
    private static void show(String text) {
        LocalDate date = LocalDate.parse(text);
        int weekYear = date.get(IsoFields.WEEK_BASED_YEAR);
        int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);

        System.out.println(date
                + " calendarYear=" + date.getYear()
                + " weekYear=" + weekYear
                + " week=" + week
                + " weekday=" + date.getDayOfWeek().getValue());
    }

    private static int isoWeeksInYear(int weekYear) {
        return LocalDate.of(weekYear, 12, 28)
                .get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);
    }

    public static void main(String[] args) {
        show("2019-12-29");
        show("2019-12-30");
        show("2020-12-31");
        show("2021-01-01");
        show("2021-01-03");
        show("2021-01-04");

        System.out.println("isoFirstDay="
                + WeekFields.ISO.getFirstDayOfWeek());
        System.out.println("isoMinimalDays="
                + WeekFields.ISO.getMinimalDaysInFirstWeek());

        LocalDate date = LocalDate.of(2021, 1, 1);
        LocalDate weekStart = date.with(
                TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        LocalDate weekEndExclusive = weekStart.plusWeeks(1);

        System.out.println("weekStart=" + weekStart);
        System.out.println("weekEndExclusive=" + weekEndExclusive);

        LocalDate firstWeekStart = LocalDate.of(2021, 1, 4).with(
                TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        System.out.println("firstWeekStart2021=" + firstWeekStart);

        System.out.println("isoWeekDate="
                + LocalDate.of(2019, 12, 30)
                        .format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("parsedWeekDate="
                + LocalDate.parse("2020-W01-1", DateTimeFormatter.ISO_WEEK_DATE));

        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
            System.out.println("invalidWeekAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalidWeekRejected");
        }

        System.out.println("weeks2020=" + isoWeeksInYear(2020));
        System.out.println("weeks2021=" + isoWeeksInYear(2021));

        LocalDate comparison = LocalDate.of(2020, 12, 27);
        WeekFields sundayStart = WeekFields.SUNDAY_START;
        System.out.println("isoComparison="
                + comparison.get(WeekFields.ISO.weekBasedYear())
                + "/" + comparison.get(WeekFields.ISO.weekOfWeekBasedYear()));
        System.out.println("sundayComparison="
                + comparison.get(sundayStart.weekBasedYear())
                + "/" + comparison.get(sundayStart.weekOfWeekBasedYear()));

        System.out.println("isoWeekOfCalendarYearJan1="
                + date.get(WeekFields.ISO.weekOfYear()));
        System.out.println("isoWeekOfWeekYearJan1="
                + date.get(WeekFields.ISO.weekOfWeekBasedYear()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 IsoWeekDemo.java
java IsoWeekDemo
```

Stdout:

```text
2019-12-29 calendarYear=2019 weekYear=2019 week=52 weekday=7
2019-12-30 calendarYear=2019 weekYear=2020 week=1 weekday=1
2020-12-31 calendarYear=2020 weekYear=2020 week=53 weekday=4
2021-01-01 calendarYear=2021 weekYear=2020 week=53 weekday=5
2021-01-03 calendarYear=2021 weekYear=2020 week=53 weekday=7
2021-01-04 calendarYear=2021 weekYear=2021 week=1 weekday=1
isoFirstDay=MONDAY
isoMinimalDays=4
weekStart=2020-12-28
weekEndExclusive=2021-01-04
firstWeekStart2021=2021-01-04
isoWeekDate=2020-W01-1
parsedWeekDate=2019-12-30
invalidWeekRejected
weeks2020=53
weeks2021=52
isoComparison=2020/52
sundayComparison=2021/1
isoWeekOfCalendarYearJan1=0
isoWeekOfWeekYearJan1=53
```

## 5. Lấy ngày đầu tuần khác với xác định tuần 1 của năm

Từ ngày 01/01/2021, tìm Thứ Hai gần nhất không sau ngày nguồn:

```java
LocalDate start = date.with(
        TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
```

Đây là đoạn minh họa với biến `date` đã có. Kết quả trong chương trình là 28/12/2020. Nó là đầu tuần chứa ngày nguồn, nhưng tuần đó thuộc năm theo tuần 2020.

Muốn tìm ngày bắt đầu **tuần 1 ISO của một năm theo tuần**, dùng mốc 04/01 của năm ấy rồi lùi về Thứ Hai gần nhất:

```java
LocalDate weekOneStart = LocalDate.of(weekYear, 1, 4).with(
        TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
```

Đây là đoạn minh họa với `weekYear` là năm theo tuần cần tìm.

Hai phép này trả lời hai câu hỏi khác nhau. Không được lấy Thứ Hai trước 01/01 rồi mặc định đó luôn là đầu tuần 1 của năm mới.

Khi biểu diễn một tuần để lọc ngày, có thể dùng khoảng:

```text
[startOfWeek, startOfWeek + 1 tuần)
```

Trong ví dụ, khoảng là `[2020-12-28, 2021-01-04)`. Nó chứa trọn một tuần qua ranh giới năm lịch. Nếu dữ liệu là thời điểm thay vì ngày, còn cần xác định vùng dùng để chuyển các biên ngày thành thời điểm.

## 6. Một năm theo tuần có 52 hoặc 53 tuần

Không nên giả định mọi năm đều có 52 tuần, hoặc dùng “năm nhuận thì có 53 tuần”. Hai tính chất không đồng nghĩa.

Theo tuần ISO, năm có 53 tuần khi ngày 01/01 là Thứ Năm, hoặc là Thứ Tư trong một năm nhuận. Chương trình cho thấy năm theo tuần 2020 có 53 tuần, còn 2021 có 52 tuần.

Cách tính trong hàm `isoWeeksInYear` dựa trên ngày 28/12: ngày này luôn nằm trong tuần ISO cuối cùng của năm theo tuần mang cùng số năm. Số tuần đọc được vì vậy là tổng số tuần của năm theo tuần đó.

Khi nhận dữ liệu từ nguồn như `2021-W53-1`, phải kiểm tra tuần 53 có tồn tại trong năm ấy. Bộ `ISO_WEEK_DATE` được dùng trong chương trình từ chối tổ hợp không hợp lệ; không nên tạo ngày bằng cách cộng tuần từ một mốc rồi bỏ qua việc kết quả đã đi sang năm theo tuần tiếp theo.

Nếu tự xây dựng hàm từ bộ ba năm–tuần–thứ, hãy xác nhận cả phạm vi thứ, số tuần và bộ ba sau khi chuyển đổi. Không chỉ kiểm tra `week <= 53`.

## 7. `weekOfYear()` khác `weekOfWeekBasedYear()`

Tên API gần nhau nhưng mô hình khác nhau:

| Trường | Cách tổ chức |
| --- | --- |
| `weekOfYear()` | Chia tuần trong phạm vi năm lịch; phần đầu chưa đủ điều kiện có thể là tuần 0 |
| `weekOfWeekBasedYear()` | Mỗi tuần thuộc trọn một năm theo tuần |
| `weekBasedYear()` | Năm đi cặp với số tuần trong mô hình năm theo tuần |

Ở ngày 01/01/2021, chương trình cho:

```text
WeekFields.ISO.weekOfYear()          = 0
WeekFields.ISO.weekOfWeekBasedYear() = 53
WeekFields.ISO.weekBasedYear()       = 2020
```

Tuần 0 không có nghĩa ngày này không thuộc tuần nào. Nó là kết quả của cách chia trong phạm vi năm lịch của trường thứ nhất. Trong mô hình năm theo tuần, ngày này thuộc tuần 53/2020. [Phân biệt các trường tuần](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

Với báo cáo theo tuần ISO liền mạch, thường cần cặp `weekBasedYear` và `weekOfWeekBasedYear`. Không ghép một trường tuần từ mô hình này với năm của mô hình khác.

## 8. Ngày đầu tuần có thể thay đổi theo quy ước vùng

`WeekFields.SUNDAY_START` dùng Chủ nhật làm đầu tuần và chỉ cần một ngày cho tuần đầu tiên. Chương trình đã áp dụng hai quy ước cho cùng ngày 27/12/2020:

```text
ISO:             năm theo tuần 2020, tuần 52
Sunday-start/1:  năm theo tuần 2021, tuần 1
```

Đây là hai quy tắc khác nhau, không phải một bên tự tính sai ngày.

`WeekFields.of(locale)` chọn quy tắc theo ngôn ngữ/vùng của `Locale`. Nó hữu ích cho giao diện được bản địa hóa, nhưng khi giao tiếp hoặc thống kê đã cam kết dùng ISO, hãy chọn `WeekFields.ISO` hay `IsoFields` rõ ràng. Không để cấu hình mặc định của máy vô tình quyết định mã tuần dùng làm khóa dữ liệu.

Tên ngày hiển thị và thứ tự đánh số cũng cần được phân biệt. `DayOfWeek.getValue()` luôn dùng quy tắc ISO 1..7; nó không tự đổi Chủ nhật thành 1 chỉ vì giao diện đang hiển thị lịch bắt đầu Chủ nhật. Nếu cần trường thứ theo một `WeekFields` riêng, dùng trường `dayOfWeek()` của chính quy tắc ấy. [Tài liệu `DayOfWeek`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 9. Cẩn thận với `YYYY` khi định dạng ngày

Trong mẫu `DateTimeFormatter`:

| Ký tự | Ý nghĩa |
| --- | --- |
| `u` | Năm theo trục năm của hệ lịch |
| `y` | Năm trong kỷ nguyên |
| `Y` | Năm theo tuần |
| `w` | Tuần trong năm theo tuần |
| `e` | Thứ theo quy tắc tuần được bản địa hóa |

Vì vậy, `YYYY-MM-dd` trộn năm theo tuần với tháng/ngày của ngày lịch. Quanh ranh giới năm, nó có thể in một chuỗi không còn biểu đạt đúng ngày theo ý định ban đầu.

Nếu muốn ngày lịch thông thường, dùng dạng phù hợp như `uuuu-MM-dd` hoặc `ISO_LOCAL_DATE`. Nếu muốn ngày tuần ISO, ưu tiên `DateTimeFormatter.ISO_WEEK_DATE`.

Cũng không nên mặc định một mẫu tự viết `YYYY-'W'ww-e` luôn dùng tuần ISO: các trường tuần được bản địa hóa phụ thuộc `Locale`. Muốn cấu hình ISO chính xác trong một định dạng riêng, có thể xây dựng từ các trường `IsoFields` và thứ ISO cụ thể; trước hết phải xác định hợp đồng đầu ra. [Bảng mẫu và bộ `ISO_WEEK_DATE`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Trong mã nhóm dữ liệu, giữ năm/tuần thành các trường rõ ràng thường dễ kiểm chứng hơn tự ghép một chuỗi định dạng rồi tách lại.

## 10. Thiết kế khóa báo cáo và ca kiểm chứng

Một khóa báo cáo tuần ISO nên có tối thiểu:

```text
(isoWeekBasedYear, isoWeekNumber)
```

Ví dụ ngày 30/12/2019 và 01/01/2020 đều được nhóm vào `(2020, 1)`. Nếu cần khóa cho ngày trong tuần, thêm thứ ISO.

Không chỉ dùng số tuần: tuần 1 xuất hiện ở nhiều năm. Không dùng năm lịch đi kèm số tuần ISO vì sẽ tách một tuần ở ranh giới năm.

Các ca kiểm chứng có ích:

- Ngày 29, 30, 31/12 và ngày 1 đến 4/01.
- Một năm có 52 tuần và một năm có 53 tuần.
- Ngày Chủ nhật và Thứ Hai liền nhau qua ranh giới năm theo tuần.
- Đọc rồi định dạng lại một ngày tuần ISO hợp lệ.
- Tuần 53 trong năm chỉ có 52 tuần.
- Cùng ngày dưới hai quy ước tuần khác nhau nếu sản phẩm hỗ trợ cả hai.

Những kiểm tra này nhắm vào ranh giới mô hình, không chỉ vào cú pháp đẹp của chuỗi ngày.

## 11. Tự thực hành

1. Tuần ISO bắt đầu vào ngày nào và tuần đầu cần tối thiểu bao nhiêu ngày?
2. `2021-01-01` có năm lịch và năm theo tuần ISO lần lượt là gì?
3. Lấy `date.getYear()` rồi ghép số tuần ISO có luôn đúng không?
4. Vì sao chỉ biết tuần bắt đầu Thứ Hai chưa đủ để xác định cách đánh số tuần?
5. Muốn trao đổi chuỗi `2020-W01-1`, nên thử bộ định dạng nào?

Gợi ý đáp án:

1. Thứ Hai và bốn ngày.
2. Năm lịch 2021; năm theo tuần 2020, tuần 53.
3. Không; hai năm có thể khác ở đầu/cuối năm lịch.
4. Còn cần quy tắc số ngày tối thiểu của tuần đầu.
5. `DateTimeFormatter.ISO_WEEK_DATE`.

Hãy chọn quy tắc tuần một cách tường minh, giữ năm theo tuần đi cùng số tuần và kiểm chứng các ngày quanh ranh giới năm.
