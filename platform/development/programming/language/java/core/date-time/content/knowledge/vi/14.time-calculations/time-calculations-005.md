# Tính chênh lệch bằng `ChronoUnit.between()`, `until()` và đơn vị nguyên hoàn chỉnh

Java cung cấp `ChronoUnit.between(start, end)` và `start.until(end, unit)` để tính lượng thời gian giữa hai mốc theo một đơn vị xác định. Hiểu đúng các phương thức này đòi hỏi phân biệt **đơn vị nguyên hoàn chỉnh** với tổng ngày hay thời lượng thực tế. Ví dụ, hai `LocalDateTime` cách nhau 23 giờ cho `ChronoUnit.HOURS.between` là 23, nhưng `ChronoUnit.DAYS.between` là 0 vì chưa đủ một ngày.

## 1. Hai cú pháp, cùng mục tiêu

`ChronoUnit` thuộc `java.time.temporal`. Các đơn vị hay dùng gồm `DAYS`, `WEEKS`, `MONTHS`, `YEARS`, `HOURS`, `MINUTES`, `SECONDS`. Chọn đơn vị phù hợp với câu hỏi:

```java
long days = ChronoUnit.DAYS.between(start, end);
long hours = ChronoUnit.HOURS.between(start, end);
```

Hoặc gọi trên mốc đầu:

```java
long days = start.until(end, ChronoUnit.DAYS);
long hours = start.until(end, ChronoUnit.HOURS);
```

Với cùng hai temporal và một đơn vị được hỗ trợ, hai dạng gọi thường cho cùng kết quả. Về bản chất `ChronoUnit.between(a, b)` gọi `a.until(b, thisUnit)`. Dạng đầu nhấn mạnh đơn vị được hỏi; dạng sau đọc giống “tính từ ngày/giờ này đến ngày/giờ kia”.

## 2. “Đơn vị nguyên hoàn chỉnh” là gì?

Kết quả là số đơn vị nguyên theo quy tắc của kiểu thời gian và đơn vị được chọn; phần lẻ cuối không được làm tròn lên. Khi dùng `LocalDateTime`, ví dụ:

| Bắt đầu | Kết thúc | `HOURS.between` | `DAYS.between` |
| --- | --- | ---: | ---: |
| 01/01 10:00 | 02/01 09:59 | 23 | 0 |
| 01/01 10:00 | 02/01 10:00 | 24 | 1 |
| 01/01 10:00 | 02/01 10:01 | 24 | 1 |
| 02/01 10:00 | 01/01 10:01 | -23 | 0 |
| 02/01 10:00 | 01/01 10:00 | -24 | -1 |

Khoảng 23 giờ 59 phút vẫn chưa đủ 24 giờ, nên chỉ tính 0 ngày nguyên. Khi vượt ranh giới 24 giờ, kết quả là 1; phần phút dư không tạo thành ngày thứ hai. Với chiều âm, kết quả không đủ một đơn vị bị cắt về 0, chứ không làm tròn xuống -1.

## 3. Ví dụ Java chạy được: ngày giờ chưa đủ một ngày

Tạo tệp `ChronoUnitBetweenDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

public class ChronoUnitBetweenDemo {
    public static void main(String[] args) {
        LocalDateTime start = LocalDateTime.of(2024, 1, 1, 10, 0);
        LocalDateTime beforeFullDay = LocalDateTime.of(2024, 1, 2, 9, 59);
        LocalDateTime fullDay = LocalDateTime.of(2024, 1, 2, 10, 0);
        LocalDateTime afterFullDay = LocalDateTime.of(2024, 1, 2, 10, 1);

        System.out.println("Hours before full day: "
                + ChronoUnit.HOURS.between(start, beforeFullDay));
        System.out.println("Days before full day: "
                + ChronoUnit.DAYS.between(start, beforeFullDay));
        System.out.println("Days at exact boundary: "
                + ChronoUnit.DAYS.between(start, fullDay));
        System.out.println("Days after boundary: "
                + ChronoUnit.DAYS.between(start, afterFullDay));
        System.out.println("until hours: "
                + start.until(beforeFullDay, ChronoUnit.HOURS));
        System.out.println("until days: "
                + start.until(beforeFullDay, ChronoUnit.DAYS));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac ChronoUnitBetweenDemo.java
java ChronoUnitBetweenDemo
```

Đầu ra:

```text
Hours before full day: 23
Days before full day: 0
Days at exact boundary: 1
Days after boundary: 1
until hours: 23
until days: 0
```

Với cùng cặp `LocalDateTime` và cùng đơn vị, `until` và `ChronoUnit.between` cho cùng kết quả. Những mốc 23:59 trước ranh giới ngày không được làm tròn thành một đơn vị ngày.

## 4. Đơn vị tháng/năm tuân theo lịch

Không thể chuyển một tháng thành một số ngày cố định: tháng lịch có độ dài 28–31 ngày. Vì vậy, phép tính bằng `MONTHS` phụ thuộc ngày bắt đầu/kết thúc, còn `DAYS` đếm số ngày lịch giữa hai `LocalDate`.

```java
LocalDate start = LocalDate.of(2024, 1, 31);
LocalDate end = LocalDate.of(2024, 2, 29);

System.out.println(ChronoUnit.DAYS.between(start, end));
System.out.println(ChronoUnit.MONTHS.between(start, end));
System.out.println(start.until(end, ChronoUnit.MONTHS));
```

Kết quả:

```text
29
0
0
```

Từ 31/01 đến 29/02 năm nhuận có 29 ngày, nhưng không đủ một tháng nguyên theo phép tính `MONTHS` giữa các ngày này. Không suy ra số tháng bằng cách chia ngày cho 30.

Trong trường hợp ngày tương ứng của tháng tiếp theo:

```java
LocalDate start = LocalDate.of(2024, 1, 15);
LocalDate end1 = LocalDate.of(2024, 2, 14);
LocalDate end2 = LocalDate.of(2024, 2, 15);

System.out.println(ChronoUnit.MONTHS.between(start, end1));
System.out.println(ChronoUnit.MONTHS.between(start, end2));
System.out.println(ChronoUnit.DAYS.between(start, end2));
```

Kết quả:

```text
0
1
31
```

Từ 15/01 đến 14/02 chưa đủ tháng nguyên; tới 15/02 đã đủ một tháng, tương ứng 31 ngày. Nếu yêu cầu là “đủ bao nhiêu tháng theo lịch”, dùng `MONTHS` và thống nhất chính sách ngày cuối tháng trong nghiệp vụ.

## 5. Ngày lịch, đơn vị thời gian và tổng thời lượng

Chọn đúng kiểu đầu vào:

| Kiểu | Ví dụ câu hỏi | Cách tính phù hợp |
| --- | --- | --- |
| `LocalDate` | Chênh nhau bao nhiêu ngày lịch? | `ChronoUnit.DAYS.between(a, b)` |
| `LocalDate` | Bao nhiêu tháng nguyên? | `ChronoUnit.MONTHS.between(a, b)` |
| `LocalDateTime` | Bao nhiêu giờ đồng hồ nguyên giữa hai mốc? | `ChronoUnit.HOURS.between(a, b)` |
| `Instant` | Bao nhiêu giờ thực tế đã trôi qua? | `ChronoUnit.HOURS.between(a, b)` hoặc `Duration.between(a, b)` |
| `LocalDate` | Biểu diễn khoảng theo năm/tháng/ngày? | `Period.between(a, b)` |
| `Instant` | Cần thời lượng với giây và nano giây? | `Duration.between(a, b)` |

`ChronoUnit.DAYS.between(LocalDate, LocalDate)` trả chênh lệch giữa ngày lịch. Với hai `LocalDateTime`, thành phần giờ có thể khiến chưa đạt một ngày đầy đủ dù ngày trên lịch đã khác. Với hai `Instant`, các đơn vị giờ/phút/giây được tính trên trục thời gian thực tế; đơn vị `DAYS` tương ứng các khoảng 24 giờ, không phải lúc nào cũng là “ngày địa phương” quanh DST.

Chương trình đầy đủ:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class ChronoUnitInstantDemo {
    public static void main(String[] args) {
        Instant start = Instant.parse("2024-01-01T00:00:00Z");
        Instant end = Instant.parse("2024-01-02T00:00:00Z");

        System.out.println("ChronoUnit hours: "
                + ChronoUnit.HOURS.between(start, end));
        System.out.println("Duration hours: "
                + Duration.between(start, end).toHours());
    }
}
```

```bash
javac ChronoUnitInstantDemo.java
java ChronoUnitInstantDemo
```

Kết quả:

```text
ChronoUnit hours: 24
Duration hours: 24
```

`Duration` mô tả lượng thời gian theo giây/nano giây, thích hợp cho độ dài thực tế. `ChronoUnit.between` trả một số nguyên theo đơn vị đã chọn. `Period` biểu diễn thành phần lịch theo năm/tháng/ngày. Ba khái niệm này có liên quan nhưng không thay thế nhau.

## 6. `until()` theo đơn vị được chọn

Cú pháp:

```java
long count = start.until(end, ChronoUnit.MONTHS);
```

Phương thức này không trả tháng thập phân; nó trả số tháng nguyên theo quy tắc của kiểu temporal. Ví dụ:

```java
LocalDate start = LocalDate.of(2024, 1, 15);
LocalDate feb14 = LocalDate.of(2024, 2, 14);
LocalDate feb15 = LocalDate.of(2024, 2, 15);

System.out.println(start.until(feb14, ChronoUnit.MONTHS));
System.out.println(ChronoUnit.MONTHS.between(start, feb14));
System.out.println(start.until(feb15, ChronoUnit.MONTHS));
```

Kết quả:

```text
0
0
1
```

`until` và `between` thống nhất khi cùng cặp mốc, kiểu temporal và đơn vị. Không phải mọi kiểu hỗ trợ mọi đơn vị: ví dụ `LocalDate` không có thành phần giờ; một đơn vị không được hỗ trợ có thể ném `UnsupportedTemporalTypeException`. Xác minh kiểu dữ liệu đầu vào và đơn vị có ý nghĩa phù hợp.

## 7. Khoảng có hướng và kết quả âm

Nếu `end` trước `start`, các phép tính có thể trả về số âm. Với `LocalDateTime`, khoảng âm 23 giờ chưa đủ âm một ngày nên `DAYS.between` trả 0; khoảng âm 24 giờ trả -1 ngày.

Tạo tệp `ChronoUnitNegativeDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

public class ChronoUnitNegativeDemo {
    public static void main(String[] args) {
        LocalDateTime later = LocalDateTime.of(2024, 1, 2, 10, 0);
        LocalDateTime earlierBy23Hours = LocalDateTime.of(2024, 1, 1, 11, 0);
        LocalDateTime earlierBy24Hours = LocalDateTime.of(2024, 1, 1, 10, 0);

        System.out.println(ChronoUnit.HOURS.between(later, earlierBy23Hours));
        System.out.println(ChronoUnit.DAYS.between(later, earlierBy23Hours));
        System.out.println(ChronoUnit.DAYS.between(later, earlierBy24Hours));
    }
}
```

```bash
javac ChronoUnitNegativeDemo.java
java ChronoUnitNegativeDemo
```

Kết quả:

```text
-23
0
-1
```

Nếu cần độ lớn không dấu, có thể dùng `Math.abs(ChronoUnit.DAYS.between(a, b))`, nhưng chỉ khi yêu cầu thực sự là khoảng cách tuyệt đối theo đơn vị đó. Với deadline, lịch sử hoặc quy trình trước/sau, dấu âm thường chứa thông tin hữu ích và nên được giữ lại.

## 8. Ranh giới ngày và múi giờ

Khi dữ liệu bắt đầu là timestamp, hãy xác định rõ đang hỏi thời lượng thực tế hay số ngày kinh doanh. Hai `Instant` gần nửa đêm UTC có thể thuộc ngày lịch khác nhau ở Việt Nam và Los Angeles. Nếu cần tính ngày báo cáo, trước tiên chuyển từng `Instant` sang vùng nghiệp vụ rồi mới lấy `LocalDate`:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate startDate = startInstant.atZone(businessZone).toLocalDate();
LocalDate endDate = endInstant.atZone(businessZone).toLocalDate();
long businessDays = ChronoUnit.DAYS.between(startDate, endDate);
```

Đoạn này giả sử hai biến `Instant` đã được cung cấp. Nó tính chênh lệch **ngày lịch theo vùng nghiệp vụ**, không đo số giờ tuyệt đối đã trôi qua. Nếu câu hỏi là “còn bao nhiêu giờ tới thời điểm kết thúc”, hãy so sánh hai `Instant` bằng `Duration` hoặc `ChronoUnit.HOURS`.

Vùng có đổi giờ theo mùa (DST) làm cho một ngày địa phương có thể dài 23 hoặc 25 giờ. Do đó, “một ngày theo lịch” và “24 giờ thực tế” khác nhau. Chọn kiểu và đơn vị có đúng nghĩa với câu hỏi.

## 9. Các lỗi thường gặp

- **Kỳ vọng làm tròn lên:** `between` trả đơn vị nguyên, không biến 23 giờ 59 phút thành 1 ngày.
- **Coi ngày, tháng là độ dài cố định:** tháng dài 28–31 ngày; dùng phép tính lịch thay vì chia cho 30.
- **Nhầm Period với tổng ngày:** `Period.getDays()` chỉ là thành phần ngày; dùng `ChronoUnit.DAYS.between` khi cần tổng ngày.
- **Nhầm ngày lịch với thời lượng thực:** dùng `LocalDate` cho ngày lịch, `Instant`/`Duration` cho thời điểm và thời lượng tuyệt đối.
- **Quên chiều âm:** khi `end` trước `start`, kết quả có hướng và có thể âm.
- **Đếm cả ngày đầu và cuối một cách ngầm định:** `between` là chênh lệch giữa hai mốc; quy tắc bao gồm hai đầu cần được mô hình hóa riêng trong nghiệp vụ.
- **Dùng đơn vị không hỗ trợ:** chọn kiểu temporal có đủ thành phần; xử lý rõ lỗi khi đơn vị không được hỗ trợ.
- **Bỏ qua vùng:** tính ngày nghiệp vụ từ timestamp phải dùng đúng `ZoneId` trước khi lấy ngày local.

## 10. Ví dụ tổng hợp

Tạo tệp `ChronoUnitUntilDemo.java`:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

public class ChronoUnitUntilDemo {
    public static void main(String[] args) {
        LocalDate jan15 = LocalDate.of(2024, 1, 15);
        LocalDate feb14 = LocalDate.of(2024, 2, 14);
        LocalDate feb15 = LocalDate.of(2024, 2, 15);
        System.out.println("Incomplete month: "
                + ChronoUnit.MONTHS.between(jan15, feb14));
        System.out.println("Complete month: "
                + jan15.until(feb15, ChronoUnit.MONTHS));

        LocalDateTime morning = LocalDateTime.of(2024, 1, 1, 10, 0);
        LocalDateTime beforeNextMorning = LocalDateTime.of(2024, 1, 2, 9, 59);
        System.out.println("Hours: "
                + ChronoUnit.HOURS.between(morning, beforeNextMorning));
        System.out.println("Days: "
                + morning.until(beforeNextMorning, ChronoUnit.DAYS));
    }
}
```

Chạy:

```bash
javac ChronoUnitUntilDemo.java
java ChronoUnitUntilDemo
```

Đầu ra:

```text
Incomplete month: 0
Complete month: 1
Hours: 23
Days: 0
```

Các giá trị xác nhận rằng một tháng hoặc một ngày chỉ được tính khi đơn vị nguyên tương ứng đã hoàn chỉnh. Không có một cách tính phù hợp cho mọi câu hỏi: hãy chọn đúng kiểu temporal, đúng đơn vị và đúng chính sách đầu mút.

### Ghi nhớ

`ChronoUnit.between(start, end)` và `start.until(end, unit)` tính số **đơn vị nguyên** từ một mốc đến mốc còn lại. Dùng `DAYS` cho chênh lệch ngày, `MONTHS`/`YEARS` cho đơn vị lịch, và `Duration` hoặc chênh lệch `Instant` cho thời lượng thực tế. Phần lẻ không được làm tròn thành đơn vị tiếp theo; kết quả có thể âm khi đảo thứ tự hai mốc.
