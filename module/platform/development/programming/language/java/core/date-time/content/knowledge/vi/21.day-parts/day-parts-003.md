# MonthDay cho ngày kỷ niệm không gắn năm

## 1. Một ngày lặp lại trong năm khác với một ngày cụ thể

“Ngày kỷ niệm là 20 tháng 11” chưa xác định năm nào. Đây là trường hợp của `MonthDay`: một giá trị gồm **tháng và ngày trong tháng**, không có năm, giờ hay múi giờ. Dạng văn bản chuẩn là `--11-20`; hai dấu gạch đầu thể hiện phần năm không có.

Dùng `MonthDay` để lưu phần tháng/ngày của sinh nhật, ngày thành lập hoặc một mốc lịch dương lặp hằng năm. Dùng `LocalDate` nếu cần lưu ngày diễn ra sự kiện đầy đủ, ví dụ ngày sinh thật để tính tuổi. Hai kiểu có thể cùng xuất hiện: lưu `LocalDate` làm dữ liệu gốc, rồi lấy `MonthDay.from(birthDate)` để so khớp ngày sinh trong năm.

| Dữ liệu cần giữ | Kiểu phù hợp |
| --- | --- |
| Ngày 20 tháng 11, không gắn năm | `MonthDay` |
| Ngày 20 tháng 11 năm 1995 | `LocalDate` |
| Tháng 11 năm 2025, không có ngày | `YearMonth` |
| Một thời điểm gửi lời chúc thực tế | Cần thêm ngày, giờ và múi giờ |

`MonthDay` thuộc lịch ISO, bất biến và an toàn luồng. Nó không tự diễn tả ngày lễ âm lịch, “thứ Hai đầu tiên của tháng”, hoặc một thời điểm tuyệt đối. [MonthDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html)

## 2. Tạo, đọc và chuyển đổi

Đoạn minh họa trong một phương thức:

```java
MonthDay anniversary = MonthDay.of(11, 20);
MonthDay same = MonthDay.of(java.time.Month.NOVEMBER, 20);
MonthDay parsed = MonthDay.parse("--11-20");
MonthDay fromDate = MonthDay.from(LocalDate.of(1995, 11, 20));

int monthNumber = anniversary.getMonthValue(); // 11, không phải chỉ số từ 0.
java.time.Month month = anniversary.getMonth();
int day = anniversary.getDayOfMonth();        // 20.
LocalDate in2025 = anniversary.atYear(2025);   // 2025-11-20.
```

`of` kiểm tra sự tồn tại của cặp tháng/ngày: tháng 13 hoặc ngày 31 tháng 4 không hợp lệ và gây `DateTimeException`. `parse` không nhận chuỗi sai dạng hoặc cặp tháng/ngày không hợp lệ; lỗi phân tích chuỗi là `DateTimeParseException`.

Có thể hiển thị `dd/MM` bằng một `DateTimeFormatter` phù hợp. Tuy nhiên, không đặt năm vào mẫu rồi mong `MonthDay` có năm để định dạng. Khi trao đổi dữ liệu, dạng `--MM-dd` giữ rõ việc không có năm hơn một ngày đầy đủ với năm giả.

## 3. Ngày 29 tháng 2 hợp lệ trong MonthDay

`MonthDay.of(2, 29)` hợp lệ vì chưa chọn năm. Ngày 30 tháng 2 vẫn không hợp lệ: không có năm ISO nào chứa ngày đó.

Sau khi chọn năm, phải phân biệt ba hành vi:

| Thao tác với `--02-29` | Năm nhuận 2024 | Năm thường 2025 |
| --- | --- | --- |
| `isValidYear(year)` | `true` | `false` |
| `atYear(year)` | `2024-02-29` | `2025-02-28` |
| Yêu cầu giữ đúng 29/2 | Có ngày tương ứng | Không có ngày tương ứng |

`atYear` **điều chỉnh 29 tháng 2 về 28 tháng 2** khi cần, không tự ném lỗi chỉ vì năm không nhuận. Nếu hệ thống phải bỏ qua năm thường hoặc chuyển sang 1 tháng 3, cần quy tắc nghiệp vụ riêng.

Quy tắc năm nhuận ISO là chia hết cho 4, trừ các năm tròn thế kỷ không chia hết cho 400. Vì vậy, 2100 không nhuận còn 2000 có nhuận. Không tìm lần 29/2 tiếp theo bằng cách luôn cộng 4 vào năm. [Year.isLeap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html#isLeap(long))

Chính sách cho sinh nhật 29/2 là lựa chọn của ứng dụng hoặc yêu cầu nghiệp vụ cụ thể; hành vi mặc định của thư viện không tự xác lập một quy tắc pháp lý về ngày sinh hay tuổi.

## 4. So khớp một ngày kỷ niệm hôm nay

Ý tưởng cơ bản là bỏ năm của hôm nay rồi so sánh giá trị:

```java
MonthDay anniversary = MonthDay.of(11, 20);
LocalDate today = LocalDate.of(2025, 11, 20);
boolean isAnniversary = anniversary.equals(MonthDay.from(today)); // true.
```

Cách này khớp **đúng tháng/ngày**, nên sinh nhật 29/2 sẽ không khớp ngày nào trong năm thường. Nếu nghiệp vụ có chính sách thay thế, hãy tính ngày thực tế của năm đó theo chính sách rồi so với `today`.

Ngày “hôm nay” phụ thuộc múi giờ. Trong ứng dụng thực, lấy `LocalDate.now(clock)` từ một `Clock` có múi giờ nghiệp vụ rõ ràng; truyền đồng hồ vào giúp kiểm tra được các tình huống gần nửa đêm và cuối năm. `MonthDay.now()` tự lấy đồng hồ/múi giờ mặc định, nên không nên ẩn lựa chọn đó trong một tác vụ gửi lời chúc cho nhiều vùng. [Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

## 5. Tính lần xuất hiện tiếp theo với chính sách 29/2 rõ ràng

Chương trình dưới đây hỗ trợ ba quy tắc: chuyển về 28/2, chuyển sang 1/3, hoặc chỉ nhận đúng ngày 29/2. “Lần tiếp theo” được định nghĩa **bao gồm hôm nay**. Hàm trả `LocalDate`, vì sau khi chọn năm ta đã có một ngày cụ thể.

Lưu thành `AnniversaryDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;
import java.util.Optional;

public class AnniversaryDemo {
    enum LeapPolicy { FEBRUARY_28, MARCH_1, LEAP_YEARS_ONLY }

    static Optional<LocalDate> occurrence(
            MonthDay anniversary, int year, LeapPolicy policy) {
        Objects.requireNonNull(anniversary, "anniversary");
        Objects.requireNonNull(policy, "policy");
        Year.of(year); // Kiểm tra năm thuộc miền biểu diễn hợp lệ.
        if (anniversary.isValidYear(year)) {
            return Optional.of(anniversary.atYear(year));
        }
        // Với MonthDay hợp lệ, trường hợp còn lại là 29/2 trong năm thường.
        return switch (policy) {
            case FEBRUARY_28 -> Optional.of(LocalDate.of(year, 2, 28));
            case MARCH_1 -> Optional.of(LocalDate.of(year, 3, 1));
            case LEAP_YEARS_ONLY -> Optional.empty();
        };
    }

    static LocalDate nextOccurrence(
            MonthDay anniversary, LocalDate today, LeapPolicy policy) {
        Objects.requireNonNull(today, "today");
        for (int year = today.getYear(); year <= Year.MAX_VALUE; year++) {
            Optional<LocalDate> candidate = occurrence(anniversary, year, policy);
            if (candidate.isPresent() && !candidate.get().isBefore(today)) {
                return candidate.get();
            }
        }
        throw new DateTimeException("No representable next occurrence");
    }

    public static void main(String[] args) {
        MonthDay anniversary = MonthDay.parse("--02-29");
        LocalDate today = LocalDate.of(2025, 2, 28);

        System.out.println("anniversary=" + anniversary);
        System.out.println("valid2024=" + anniversary.isValidYear(2024));
        System.out.println("valid2025=" + anniversary.isValidYear(2025));
        System.out.println("default2025=" + anniversary.atYear(2025));
        System.out.println("februaryPolicy="
                + nextOccurrence(anniversary, today, LeapPolicy.FEBRUARY_28));
        System.out.println("marchPolicy="
                + nextOccurrence(anniversary, today, LeapPolicy.MARCH_1));
        System.out.println("leapOnly="
                + nextOccurrence(anniversary, today, LeapPolicy.LEAP_YEARS_ONLY));
        System.out.println("afterMarch=" + nextOccurrence(anniversary,
                LocalDate.of(2025, 3, 2), LeapPolicy.FEBRUARY_28));
        System.out.println("ordinary=" + nextOccurrence(MonthDay.of(11, 20),
                LocalDate.of(2025, 12, 31), LeapPolicy.LEAP_YEARS_ONLY));
        System.out.println("adjustedMonth=" + MonthDay.of(1, 31).withMonth(4));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 AnniversaryDemo.java
java AnniversaryDemo
```

Stdout chính xác:

```text
anniversary=--02-29
valid2024=true
valid2025=false
default2025=2025-02-28
februaryPolicy=2025-02-28
marchPolicy=2025-03-01
leapOnly=2028-02-29
afterMarch=2026-02-28
ordinary=2026-11-20
adjustedMonth=--04-30
```

Hàm duyệt từ năm hiện tại: nếu ngày đã qua, xét năm sau; nếu chính sách chỉ nhận năm nhuận, bỏ qua năm không có ngày tương ứng. Vì vậy nó xử lý cả việc qua cuối năm và các năm thế kỷ không nhuận.

Nhánh báo lỗi ở giới hạn năm tránh giả định luôn có một kết quả tương lai trong miền biểu diễn của `LocalDate`. Nếu muốn “sau hôm nay” theo nghĩa nghiêm ngặt, đổi điều kiện thành `candidate.get().isAfter(today)`; không cần cộng một ngày vào `today`, vốn có thể vượt miền khi `today` là `LocalDate.MAX`.

## 6. Điều chỉnh và so sánh: những điểm dễ hiểu sai

### Bất biến và quy tắc ngày cuối tháng

`withMonth`/`withDayOfMonth` trả kết quả mới. Đổi tháng của `--01-31` sang tháng 4 cho `--04-30`, vì ngày 31 không tồn tại ở tháng mới. Ngược lại, yêu cầu trực tiếp `MonthDay.of(4, 30).withDayOfMonth(31)` không hợp lệ và gây `DateTimeException`.

Vì thế, kiểm tra dữ liệu đầu vào với `of` khác với điều chỉnh một giá trị có sẵn bằng `withMonth`; đừng dùng kết quả điều chỉnh làm bằng chứng rằng dữ liệu gốc hợp lệ.

### Thứ tự trong một năm không phải khoảng cách đến lần tới

`compareTo`, `isBefore`, `isAfter` so theo tháng rồi ngày. `--01-01` đứng trước `--12-31`, nhưng nếu hôm nay là 31/12 thì lần 1/1 kế tiếp chỉ cách một ngày. Để đếm số ngày còn lại, trước hết tính `LocalDate` của lần xuất hiện tiếp theo, rồi dùng `ChronoUnit.DAYS.between(today, next)`.

### Không có phép cộng ngày tổng quát

`MonthDay` triển khai `TemporalAccessor` và `TemporalAdjuster`, nhưng không triển khai `Temporal`; nó không có `plusDays`. Muốn cộng ngày, hãy xác định năm bằng một chính sách rõ ràng rồi xử lý `LocalDate`. Không dùng ép kiểu để biến tháng/ngày thành một ngày đầy đủ.

### Dùng như một quy tắc điều chỉnh

Với ngày ISO, `date.with(monthDay)` đặt phần tháng/ngày và giữ năm, có điều chỉnh khi 29/2 không tồn tại. Ví dụ `LocalDate.of(2025, 8, 1).with(MonthDay.of(2, 29))` cho `2025-02-28`. Nó không tự chọn “lần kỷ niệm tiếp theo”: kết quả có thể nằm trước `date`. [LocalDate.with](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#with(java.time.temporal.TemporalAdjuster))

## 7. Kiểm tra trước khi dùng cho lịch nhắc

- Giữ đúng ý nghĩa dữ liệu: không tạo năm 1970 hoặc 2000 làm năm giả rồi vô tình coi đó là ngày sinh thật.
- Quy định rõ chính sách 29/2 và việc có tính hôm nay là lần kế tiếp hay không.
- Kiểm tra mốc cuối năm, ngày thường, năm nhuận, năm thế kỷ như 2100 và chính ngày kỷ niệm.
- Nếu gửi thông báo theo giờ, bổ sung giờ và múi giờ sau khi đã xác định ngày; `MonthDay` không tự lên lịch hoặc chống gửi trùng.

Để dùng ngày âm lịch hoặc quy tắc tôn giáo đặc thù, cần mô hình lịch/chuyển đổi phù hợp; một cặp tháng/ngày ISO không lưu đủ quy tắc đó.

## 8. Tự thực hành

1. Lấy `MonthDay` từ `LocalDate.of(2000, 7, 10)` rồi gắn vào năm 2026.
2. Với ngày kỷ niệm 29/2 và hôm nay 1/3/2096, tìm lần tiếp theo theo `LEAP_YEARS_ONLY`.
3. Thay quy tắc của hàm bằng điều kiện chỉ nhận ngày sau hôm nay và kiểm tra đúng ngày kỷ niệm.
4. Tính số ngày còn lại đến ngày 1/1 khi hôm nay là 31/12/2025.

Đối chiếu: (1) `--07-10`, rồi `2026-07-10`; (2) `2104-02-29`, vì 2100 không nhuận; (3) dùng so sánh `isAfter`; (4) ngày đích `2026-01-01`, khoảng cách 1 ngày.