# Tính khoảng ngày bằng `Period.between()` trong Java

Khi cần tính khoảng cách giữa hai ngày lịch, Java cung cấp `Period.between(startDate, endDate)`. Phương thức này trả về một **khoảng thời gian theo năm, tháng và ngày lịch** (`Period`), phù hợp cho tuổi, thời hạn hợp đồng, thời gian giữa hai mốc ngày hoặc thông tin kiểu “1 năm, 2 tháng, 5 ngày”.

Điểm quan trọng: `Period` không đồng nghĩa với tổng số ngày. Khoảng từ ngày 15/01 đến 20/03 có thể được biểu diễn thành 2 tháng 5 ngày, trong khi tổng số ngày phụ thuộc độ dài thực của từng tháng trong khoảng đó. Nếu nghiệp vụ cần “bao nhiêu ngày đã trôi qua”, hãy dùng `ChronoUnit.DAYS.between()`; nếu cần thời lượng chính xác đến giờ/phút/giây, hãy dùng kiểu và API phù hợp như `Duration` hoặc chênh lệch giữa hai `Instant`.

## 1. `Period` và `Period.between()` là gì?

`Period` thuộc package `java.time`, biểu diễn một lượng thời gian theo ba thành phần lịch:

- **Years**: số năm.
- **Months**: số tháng, không tự quy đổi thành ngày.
- **Days**: số ngày còn lại sau khi tách năm và tháng theo quy tắc của phép tính.

Cú pháp:

```java
Period period = Period.between(startDate, endDate);
```

Trong đó `startDate` và `endDate` là hai đối tượng `LocalDate`. Kết quả được chuẩn hóa theo cách tính lịch của Java sao cho `startDate.plus(period)` đưa về `endDate` đối với trường hợp `LocalDate` thông thường trong ISO calendar.

Ví dụ:

```java
LocalDate start = LocalDate.of(2024, 1, 15);
LocalDate end = LocalDate.of(2025, 3, 20);

Period period = Period.between(start, end);
System.out.println(period);
System.out.println(period.getYears());
System.out.println(period.getMonths());
System.out.println(period.getDays());
```

Kết quả:

```text
P1Y2M5D
1
2
5
```

`P1Y2M5D` là dạng biểu diễn chuẩn của Period: **1 năm, 2 tháng và 5 ngày**. Chữ `P` mở đầu cho biểu diễn khoảng thời gian; `Y`, `M`, `D` lần lượt là năm, tháng, ngày. Chữ `M` có nghĩa là tháng ở vị trí này, khác với phút trong một chuỗi thời gian có thành phần giờ.

## 2. Ví dụ đầy đủ, có thể chạy

Tạo tệp **`PeriodBetweenDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Period;

public class PeriodBetweenDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 1, 15);
        LocalDate end = LocalDate.of(2025, 3, 20);

        Period period = Period.between(start, end);

        System.out.println("Start: " + start);
        System.out.println("End: " + end);
        System.out.println("Period: " + period);
        System.out.println("Years: " + period.getYears());
        System.out.println("Months: " + period.getMonths());
        System.out.println("Days: " + period.getDays());
        System.out.println("Total months: " + period.toTotalMonths());
        System.out.println("Add back: " + start.plus(period));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac PeriodBetweenDemo.java
java PeriodBetweenDemo
```

Kết quả:

```text
Start: 2024-01-15
End: 2025-03-20
Period: P1Y2M5D
Years: 1
Months: 2
Days: 5
Total months: 14
Add back: 2025-03-20
```

Ta thấy `Period.between()` cho ra năm, tháng và ngày theo lịch; `toTotalMonths()` chỉ tổng hợp phần năm/tháng thành **14 tháng**, không cộng thêm 5 ngày. Dòng `Add back` xác nhận `start.plus(period)` khôi phục đúng ngày kết thúc.

## 3. Cách đọc các thành phần của Period

Các phương thức thường dùng:

| API | Trả về | Ý nghĩa |
| --- | --- | --- |
| `getYears()` | `int` | Thành phần năm |
| `getMonths()` | `int` | Thành phần tháng |
| `getDays()` | `int` | Thành phần ngày |
| `toTotalMonths()` | `long` | Tổng năm và tháng quy đổi theo 12 tháng/năm |
| `isZero()` | `boolean` | Period có bằng 0 hay không |
| `isNegative()` | `boolean` | Period có âm hay không |
| `plus(other)` | `Period` | Cộng các thành phần lịch |
| `minus(other)` | `Period` | Trừ các thành phần lịch |
| `normalized()` | `Period` | Chuẩn hóa phần tháng theo 12 tháng/năm |

**Đừng hiểu nhầm** `getMonths()` là tổng số tháng của toàn khoảng. Trong ví dụ 1 năm 2 tháng 5 ngày, `getMonths()` trả `2`; tổng phần năm/tháng là `toTotalMonths() == 14`. `toTotalMonths()` cũng không phải tổng số ngày.

Tương tự, `getDays()` là thành phần ngày của Period, không phải số ngày đã trôi qua giữa hai mốc. Muốn tính tổng ngày theo lịch, hãy dùng `ChronoUnit.DAYS.between(start, end)`.

## 4. Tính tổng số ngày khác với tính năm/tháng/ngày

Hai API trả lời hai câu hỏi khác nhau:

```java
long totalDays = ChronoUnit.DAYS.between(start, end);
Period calendarPeriod = Period.between(start, end);
```

- `ChronoUnit.DAYS.between(start, end)`: đếm chênh lệch ngày từ ngày bắt đầu đến ngày kết thúc; kết quả là một số nguyên.
- `Period.between(start, end)`: tạo khoảng lịch theo năm, tháng và ngày.
- `Period.getDays()`: chỉ lấy phần ngày còn lại của Period, không phải `totalDays`.

Ví dụ tệp **`PeriodVersusDaysDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class PeriodVersusDaysDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 1, 15);
        LocalDate end = LocalDate.of(2025, 3, 20);

        Period period = Period.between(start, end);
        long totalDays = ChronoUnit.DAYS.between(start, end);

        System.out.println("Period: " + period);
        System.out.println("Period days component: " + period.getDays());
        System.out.println("Total days: " + totalDays);
    }
}
```

```bash
javac PeriodVersusDaysDemo.java
java PeriodVersusDaysDemo
```

Kết quả:

```text
Period: P1Y2M5D
Period days component: 5
Total days: 430
```

Khoảng này tương đương 430 ngày trôi qua nhưng có cách biểu diễn lịch là 1 năm, 2 tháng và 5 ngày. Số ngày thay đổi tùy các tháng và năm nhuận nằm trong khoảng; không thể lấy số năm nhân 365 rồi cộng số tháng nhân 30 để thay thế phép tính lịch.

## 5. Biên tháng và ngày cuối tháng

Ngày trong tháng không phải lúc nào cũng có cùng số ngày. `Period.between()` tính theo quy tắc của lịch và ngày thật ở hai đầu mốc.

Ví dụ từ 31/01 đến 28/02/2023:

```java
LocalDate start = LocalDate.of(2023, 1, 31);
LocalDate end = LocalDate.of(2023, 2, 28);
System.out.println(Period.between(start, end));
```

Kết quả:

```text
P28D
```

Vì không thể cộng một tháng vào ngày 31/01 rồi coi ngày 28/02 là “đúng một tháng + 0 ngày” theo thuật toán `Period.between`; phép tính cụ thể trả về 28 ngày để khi cộng Period trở lại ngày bắt đầu đạt chính xác ngày kết thúc. Các phép thêm tháng khác (`plusMonths`) có quy tắc điều chỉnh ngày không tồn tại về ngày cuối tháng hợp lệ. Bởi vậy, nên dùng đúng API thể hiện nghiệp vụ thay vì tự giả định mọi tháng có 30 ngày.

Một ví dụ khác là từ 29/02/2024 đến 28/02/2025:

```java
LocalDate start = LocalDate.of(2024, 2, 29);
LocalDate end = LocalDate.of(2025, 2, 28);
System.out.println(Period.between(start, end));
```

Kết quả:

```text
P11M30D
```

Dù con người có thể mô tả khoảng này là “gần một năm” hoặc một năm theo một chính sách tính tuổi cụ thể, Period của Java thể hiện khoảng thành 11 tháng 30 ngày theo quy tắc của phép tính. Nếu nghiệp vụ tuổi, hạn thanh toán hoặc hợp đồng có quy định riêng về ngày cuối tháng/ngày nhuận, cần xác minh định nghĩa nghiệp vụ; không thay chính sách đó bằng một giả định chung.

## 6. Khoảng ngày theo chiều ngược

Nếu ngày kết thúc trước ngày bắt đầu, `Period.between(start, end)` trả về Period âm theo chênh lệch có hướng. Nó không tự đổi thứ tự ngày để luôn trả kết quả dương.

Ví dụ:

```java
LocalDate start = LocalDate.of(2025, 5, 20);
LocalDate end = LocalDate.of(2025, 3, 15);
Period period = Period.between(start, end);

System.out.println(period);
System.out.println(start.plus(period));
System.out.println(period.isNegative());
```

Kết quả:

```text
P-2M-5D
2025-03-15
true
```

Khi cần khoảng không dấu, hãy quyết định rõ chính sách. Ví dụ, có thể sắp xếp hai ngày trước khi tính hoặc sử dụng `Math.abs(ChronoUnit.DAYS.between(a, b))` nếu yêu cầu thật sự là số ngày tuyệt đối. Đừng tùy tiện lấy giá trị tuyệt đối của từng thành phần Period để tạo lại một khoảng dương: nó có thể không còn đúng quan hệ lịch với hai ngày gốc.

Lưu ý rằng Period không yêu cầu mọi thành phần có cùng dấu trong tất cả các trường hợp được tạo thủ công. Ví dụ `Period.of(1, -2, 3)` là một giá trị có thành phần hỗn hợp; `normalized()` không giải quyết toàn bộ ý nghĩa nghiệp vụ của những giá trị như vậy, mà chủ yếu chuẩn hóa phần tháng theo 12 tháng/năm. Kết quả từ `Period.between()` nên được sử dụng theo chính cặp ngày đã tính.

## 7. So sánh, chuẩn hóa và cộng Period

`Period` là immutable: các phép cộng/trừ trả về một đối tượng mới, không sửa đối tượng hiện tại.

```java
Period first = Period.of(1, 14, 0);
Period normalized = first.normalized();

System.out.println(first);
System.out.println(normalized);
System.out.println(normalized.toTotalMonths());
```

Kết quả:

```text
P1Y14M
P2Y2M
26
```

`normalized()` chuyển 14 tháng thành 1 năm 2 tháng. Nó không đổi tháng thành ngày bởi độ dài tháng không cố định; cũng không tự giải quyết các thành phần ngày theo lịch vì cần ngày bắt đầu để biết tháng cụ thể dài bao nhiêu.

Khi có ngày bắt đầu và muốn tính ngày kết thúc, có thể làm:

```java
LocalDate end = start.plus(period);
```

Trong đó `start` là `LocalDate` và `period` là khoảng có sẵn. Đối với bài toán ngày lịch, đây là phép tính dễ kiểm tra bằng cách cộng lại. Nếu Period được tạo thủ công, hãy kiểm tra nó có phù hợp định nghĩa của nghiệp vụ trước khi áp dụng.

## 8. Khi nào không nên dùng Period?

| Yêu cầu | Lựa chọn thích hợp | Lý do |
| --- | --- | --- |
| “Từ ngày A đến ngày B có bao nhiêu ngày?” | `ChronoUnit.DAYS.between(A, B)` | Cần tổng số ngày, không phải các thành phần lịch |
| “Bao nhiêu năm, tháng, ngày?” | `Period.between(A, B)` | Kết quả diễn giải theo lịch |
| “Một thao tác mất bao lâu tính bằng giây/nano giây?” | `Duration` hoặc chênh lệch `Instant` | Đo khoảng trên trục thời gian |
| “Còn bao nhiêu giờ đến một thời điểm cụ thể?” | `Duration.between(nowInstant, targetInstant)` | Giờ thực tế không đồng nghĩa ngày lịch |
| “Một tháng sau ngày bắt đầu” | `date.plusMonths(1)` khi phù hợp chính sách | Cần quy tắc xử lý ngày cuối tháng |
| “Ngày kế toán thuộc tháng nào?” | Tính ngày theo múi giờ nghiệp vụ trước, rồi lấy `LocalDate` | Ngày kinh doanh có thể khác ngày UTC |

`Period` thường kết hợp với `LocalDate`, không phải để đo thời lượng chính xác giữa hai timestamp. Nếu đầu vào là `Instant`, trước hết cần xác định ngày địa phương theo múi giờ nghiệp vụ rồi mới tính Period:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessStart = startInstant.atZone(businessZone).toLocalDate();
LocalDate businessEnd = endInstant.atZone(businessZone).toLocalDate();
Period datePeriod = Period.between(businessStart, businessEnd);
```

Đây là đoạn minh họa, giả sử `startInstant` và `endInstant` đã được cung cấp. Nó tính chênh lệch giữa **ngày địa phương**, không đo khoảng giờ tuyệt đối. Hai instant cách nhau 24 giờ cũng không nhất thiết cho Period một ngày nếu vùng và mốc giờ làm chúng nằm ở hai ngày lịch khác nhau hoặc cùng ngày lịch.

## 9. Quy ước đầu mút và tránh lỗi nghiệp vụ

`Period.between(start, end)` tính khoảng có hướng sao cho cộng Period vào ngày bắt đầu đưa đến ngày kết thúc. Khi giao diện nói “số ngày trong hợp đồng”, phải làm rõ đó là chênh lệch giữa hai ngày hay số ngày bao gồm cả ngày đầu và ngày cuối.

Ví dụ, giữa 01/06 và 03/06:

- `ChronoUnit.DAYS.between(...)` là 2.
- Nếu quy định đếm cả ngày 01/06 và 03/06, số ngày theo cách đếm bao gồm hai đầu là 3.

Đó là hai quy ước nghiệp vụ khác nhau. Nếu thật sự cần đếm bao gồm cả hai đầu, hãy diễn đạt rõ điều kiện, chẳng hạn lấy chênh lệch ngày rồi cộng 1 trong trường hợp hợp lệ; không thay đổi định nghĩa của `Period.between()`.

Những lỗi thường gặp:

1. **Coi `getDays()` là tổng số ngày.** Nó chỉ là thành phần ngày của Period. Dùng `ChronoUnit.DAYS.between` khi cần con số tổng.
2. **Coi 1 tháng luôn bằng 30 ngày.** Tháng lịch dài 28–31 ngày; dùng `Period` hoặc các API lịch.
3. **Dùng Period để đo thời lượng đến giây.** Period không có giờ, phút, giây; dùng `Duration` hoặc `Instant`.
4. **Bỏ qua ngày kết thúc trước ngày bắt đầu.** Period có thể âm; xác định trước có cần giữ hướng hay chỉ cần độ lớn.
5. **Không xác định múi giờ khi đầu vào là timestamp.** Chuyển hai Instant sang đúng ngày nghiệp vụ bằng `ZoneId` rồi mới tính khoảng ngày.
6. **Giả sử ngày nhuận luôn có cách tính tuổi như 365 ngày.** Chính sách tuổi/pháp lý cần định nghĩa riêng; Period phản ánh chênh lệch lịch của Java.

## 10. Ví dụ kiểm tra một bộ tình huống

Chương trình sau gộp các trường hợp quan trọng, có thể chạy độc lập với Java 17+.

Tạo tệp **`PeriodEdgeCases.java`**:

```java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class PeriodEdgeCases {
    private static void show(LocalDate start, LocalDate end) {
        Period p = Period.between(start, end);
        System.out.println(start + " -> " + end + " = " + p
                + " ; years=" + p.getYears()
                + ", months=" + p.getMonths()
                + ", days=" + p.getDays()
                + ", totalDays=" + ChronoUnit.DAYS.between(start, end)
                + ", addBack=" + start.plus(p));
    }

    public static void main(String[] args) {
        show(LocalDate.of(2024, 1, 15), LocalDate.of(2025, 3, 20));
        show(LocalDate.of(2023, 1, 31), LocalDate.of(2023, 2, 28));
        show(LocalDate.of(2024, 2, 29), LocalDate.of(2025, 2, 28));
        show(LocalDate.of(2025, 5, 20), LocalDate.of(2025, 3, 15));
    }
}
```

Chạy:

```bash
javac PeriodEdgeCases.java
java PeriodEdgeCases
```

Kết quả:

```text
2024-01-15 -> 2025-03-20 = P1Y2M5D ; years=1, months=2, days=5, totalDays=430, addBack=2025-03-20
2023-01-31 -> 2023-02-28 = P28D ; years=0, months=0, days=28, totalDays=28, addBack=2023-02-28
2024-02-29 -> 2025-02-28 = P11M30D ; years=0, months=11, days=30, totalDays=365, addBack=2025-02-28
2025-05-20 -> 2025-03-15 = P-2M-5D ; years=0, months=-2, days=-5, totalDays=-66, addBack=2025-03-15
```

Điều cần quan sát không chỉ là chuỗi Period, mà còn là `totalDays` và `addBack`. Số ngày tổng và thành phần Period trả lời hai câu hỏi khác nhau; cộng Period trở lại là một cách kiểm tra tính phù hợp của cặp ngày.

## Ghi nhớ

Dùng `Period.between(start, end)` khi muốn **diễn tả chênh lệch lịch theo năm, tháng và ngày**. Dùng `ChronoUnit.DAYS.between(start, end)` khi cần **tổng số ngày**. Dùng `Duration`/chênh lệch `Instant` cho **thời lượng thực tế**. Luôn xác định cách đếm đầu mút, chiều khoảng và múi giờ nghiệp vụ trước khi chuyển kết quả thành quy tắc của sản phẩm.
