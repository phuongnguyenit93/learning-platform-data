# plusMonths() ở cuối tháng và tính không đảo ngược của phép tính thời gian

Trong Java Date-Time API (`java.time`), `plusMonths(...)` và `minusMonths(...)` thực hiện phép tính theo **lịch**, không cộng/trừ một số giây cố định. Khi ngày gốc không tồn tại trong tháng đích, Java điều chỉnh nó về ngày hợp lệ cuối cùng của tháng đó. Vì vậy **cộng một tháng rồi trừ một tháng không phải lúc nào cũng khôi phục ngày ban đầu**.

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);
LocalDate next = start.plusMonths(1); // 2023-02-28
LocalDate back = next.minusMonths(1); // 2023-01-28
~~~

Kết quả là `2023-01-28`, không phải `2023-01-31`. Ngày 31 đã bị điều chỉnh khi chuyển sang tháng 2/2023; giá trị trung gian không còn lưu ý định “ngày mong muốn là 31”.

## 1. Quy tắc điều chỉnh cuối tháng

Với `LocalDate.plusMonths(n)`, Java tính tháng đích, giữ ngày hiện tại nếu ngày đó tồn tại ở tháng đích, và nếu không thì chọn ngày cuối tháng đích.

| Ngày gốc | Phép tính | Kết quả | Giải thích |
|---|---|---|---|
| `2023-01-15` | `plusMonths(1)` | `2023-02-15` | Ngày 15 tồn tại |
| `2023-01-31` | `plusMonths(1)` | `2023-02-28` | Tháng 2/2023 có 28 ngày |
| `2024-01-31` | `plusMonths(1)` | `2024-02-29` | 2024 là năm nhuận |
| `2024-03-31` | `minusMonths(1)` | `2024-02-29` | Tháng 2/2024 có 29 ngày |
| `2024-05-31` | `plusMonths(1)` | `2024-06-30` | Tháng 6 có 30 ngày |

Đây là hành vi hợp lệ theo lịch ISO, không phải lỗi hay ngoại lệ. Các phép tính giữ giá trị ngày hợp lệ trong lịch; chúng không giữ lại thông tin về ngày mong muốn trước khi điều chỉnh.

Năm nhuận cũng quan trọng:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plusYears(1)); // 2025-02-28
~~~

Năm 2025 không có ngày 29/02 nên kết quả được điều chỉnh về 28/02/2025.

## 2. Vì sao phép cộng-trừ không đảo ngược?

Một phép biến đổi không thể hoàn nguyên nếu giá trị trung gian đã mất thông tin. Từ `2023-02-28`, Java không thể biết người dùng ban đầu muốn ngày 28 hay đã bắt đầu từ ngày 31 rồi bị điều chỉnh.

~~~text
2023-01-31
    | plusMonths(1)
    v
2023-02-28  (ngày 31 không tồn tại)
    | minusMonths(1)
    v
2023-01-28  (không trở lại ngày 31)
~~~

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
LocalDate feb28 = jan31.plusMonths(1);
LocalDate returned = feb28.minusMonths(1);

System.out.println("start = " + jan31);
System.out.println("after plus = " + feb28);
System.out.println("after minus = " + returned);
System.out.println("restored = " + returned.equals(jan31));
~~~

~~~text
start = 2023-01-31
after plus = 2023-02-28
after minus = 2023-01-28
restored = false
~~~

Do đó `minusMonths(1)` không phải phép “undo” tổng quát cho `plusMonths(1)`. Quy tắc này cũng ảnh hưởng `plusYears(1)` ở ngày nhuận.

## 3. Cộng từng tháng và cộng nhiều tháng một lần

Cách chia bước tính cũng có thể thay đổi kết quả:

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
LocalDate oneMonthTwice = jan31.plusMonths(1).plusMonths(1);
LocalDate twoMonthsOnce = jan31.plusMonths(2);
System.out.println("one month twice = " + oneMonthTwice);
System.out.println("two months once = " + twoMonthsOnce);
~~~

~~~text
one month twice = 2023-03-28
two months once = 2023-03-31
~~~

Lần cộng đầu tiên biến 31/01 thành 28/02. Lần cộng thứ hai bắt đầu từ ngày 28 nên đến 28/03. Nhưng phép cộng hai tháng trực tiếp bắt đầu từ 31/01 và đến tháng 3, nơi ngày 31 tồn tại.

Vì vậy `date.plusMonths(1).plusMonths(1)` không nhất thiết bằng `date.plusMonths(2)`. Với lịch thanh toán, nhắc việc hoặc gia hạn hợp đồng, cần xác định quy tắc rõ ràng: mỗi kỳ tính từ ngày đã điều chỉnh, từ ngày gốc mong muốn, hay theo ngày cuối tháng.

## 4. Xây dựng lịch lặp lại theo ý định

### Cộng dồn theo kỳ trước

Nếu mỗi kỳ tiếp theo được tính từ ngày thực tế của kỳ trước, dùng `current.plusMonths(1)`. Ví dụ 31/01 → 28/02 → 28/03. Đây là lịch cộng dồn, và việc về ngày 28 sau tháng ngắn là một phần của quy tắc.

### Giữ ngày ưu tiên qua các tháng

Nếu ý định là “ngày 31 khi tháng có ngày đó; nếu không thì ngày cuối tháng; tháng sau quay lại ngày 31 khi có thể”, lưu ngày ưu tiên riêng, không cộng dồn trên giá trị đã điều chỉnh.

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

static LocalDate dateInTargetMonth(YearMonth targetMonth, int preferredDay) {
    int day = Math.min(preferredDay, targetMonth.lengthOfMonth());
    return targetMonth.atDay(day);
}
~~~

Đây là phương thức minh họa cần đặt trong lớp Java, không phải chương trình độc lập. Ví dụ dùng ngày mong muốn từ ngày gốc:

~~~java
LocalDate original = LocalDate.of(2023, 1, 31);
YearMonth march = YearMonth.from(original).plusMonths(2);
LocalDate target = dateInTargetMonth(march, original.getDayOfMonth());
// 2023-03-31
~~~

Ứng dụng thật nên lưu ý định ban đầu (ngày ưu tiên hoặc quy tắc cuối tháng) cùng ngày thực tế của từng kỳ.

### Luôn chọn ngày cuối tháng

Khi nghiệp vụ ghi rõ “ngày cuối mỗi tháng”, dùng `YearMonth.atEndOfMonth()`:

~~~java
YearMonth february = YearMonth.of(2023, 2);
LocalDate last = february.atEndOfMonth(); // 2023-02-28
~~~

Với tháng 2 năm nhuận, API trả ngày 29. Cộng tháng trên `YearMonth` rồi gọi `atEndOfMonth()` diễn đạt đúng mục tiêu hơn việc chọn cố định ngày 28, 30 hoặc 31.

## 5. LocalDateTime và ZonedDateTime

`LocalDateTime.plusMonths(...)` dùng cùng quy tắc điều chỉnh ngày lịch, trong khi phần giờ thường được giữ nguyên:

~~~java
LocalDateTime dt = LocalDateTime.of(2023, 1, 31, 10, 15);
System.out.println(dt.plusMonths(1)); // 2023-02-28T10:15
System.out.println(dt.plusMonths(1).minusMonths(1));
// 2023-01-28T10:15
~~~

Với `ZonedDateTime`, Java còn áp dụng quy tắc múi giờ tại ngày giờ đích. Giờ địa phương có thể nằm trong khoảng DST không tồn tại hoặc trùng lặp, khiến giờ hoặc offset được điều chỉnh.

~~~java
ZonedDateTime zoned = ZonedDateTime.of(
        2024, 3, 31, 2, 30, 0, 0, ZoneId.of("Europe/Paris"));
System.out.println("zoned source = " + zoned);
System.out.println("zoned + month = " + zoned.plusMonths(1));
System.out.println("zoned round trip = " +
        zoned.plusMonths(1).minusMonths(1));
~~~

~~~text
zoned source = 2024-03-31T03:30+02:00[Europe/Paris]
zoned + month = 2024-04-30T03:30+02:00[Europe/Paris]
zoned round trip = 2024-03-30T03:30+01:00[Europe/Paris]
~~~

Ngày 31/03/2024 lúc 02:30 không tồn tại tại Paris theo quy tắc DST của môi trường thử nghiệm, nên Java điều chỉnh lên 03:30 ngay khi tạo giá trị. Cộng tháng điều chỉnh ngày 31 thành ngày 30 của tháng 4; trừ tháng không hoàn nguyên giá trị ban đầu. Khi gỡ lỗi, phân biệt điều chỉnh ngày cuối tháng với việc xử lý gap/overlap của múi giờ.

## 6. Những phép biến đổi khác cũng có thể không đảo ngược

| Phép biến đổi | Lý do | Ví dụ |
|---|---|---|
| `plusMonths(1)` ở cuối tháng | Ngày không tồn tại ở tháng đích được điều chỉnh | 31/01 → 28/02 |
| `plusYears(1)` từ ngày nhuận | Ngày 29/02 không có trong năm thường | 29/02/2024 → 28/02/2025 |
| `truncatedTo(ChronoUnit.MINUTES)` | Giây và nano bị loại bỏ | 10:15:42.5 → 10:15 |
| `Instant.toEpochMilli()` | Mất độ chính xác dưới mili giây | Nano bị bỏ |
| Phân giải giờ DST gap/overlap | Quy tắc vùng có thể chọn hoặc điều chỉnh giờ | Giờ địa phương có thể thay đổi |

Hãy phân biệt điều chỉnh **theo lịch** với **giảm độ chính xác**. Cả hai đều có thể làm kết quả không còn đủ thông tin để khôi phục đầu vào ban đầu.

## 7. Chương trình Java 17 chạy độc lập

Lưu thành **`MonthArithmeticDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZonedDateTime;
import java.time.ZoneId;

public class MonthArithmeticDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2023, 1, 31);
        LocalDate feb28 = jan31.plusMonths(1);
        LocalDate back = feb28.minusMonths(1);
        System.out.println("Jan 31 + 1 month = " + feb28);
        System.out.println("then - 1 month = " + back);
        System.out.println("round trip restored = " + back.equals(jan31));

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("leap day + 1 year = " + leapDay.plusYears(1));
        System.out.println("Jan 31 + 2 months = " + jan31.plusMonths(2));
        System.out.println("Jan 31 + Period 2 months = " +
                jan31.plus(Period.ofMonths(2)));

        LocalDateTime dt = LocalDateTime.of(2023, 1, 31, 10, 15);
        System.out.println("datetime + month = " + dt.plusMonths(1));
        System.out.println("datetime then back = " +
                dt.plusMonths(1).minusMonths(1));

        ZonedDateTime zoned = ZonedDateTime.of(
                2024, 3, 31, 2, 30, 0, 0, ZoneId.of("Europe/Paris"));
        System.out.println("zoned source = " + zoned);
        System.out.println("zoned + month = " + zoned.plusMonths(1));
        System.out.println("zoned round trip = " +
                zoned.plusMonths(1).minusMonths(1));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MonthArithmeticDemo.java
java MonthArithmeticDemo
~~~

Đầu ra đã xác minh với `javac --release 17`:

~~~text
Jan 31 + 1 month = 2023-02-28
then - 1 month = 2023-01-28
round trip restored = false
leap day + 1 year = 2025-02-28
Jan 31 + 2 months = 2023-03-31
Jan 31 + Period 2 months = 2023-03-31
datetime + month = 2023-02-28T10:15
datetime then back = 2023-01-28T10:15
zoned source = 2024-03-31T03:30+02:00[Europe/Paris]
zoned + month = 2024-04-30T03:30+02:00[Europe/Paris]
zoned round trip = 2024-03-30T03:30+01:00[Europe/Paris]
~~~

## 8. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Nghĩ cộng một tháng rồi trừ sẽ khôi phục giá trị | Ngày gốc có thể đã bị điều chỉnh | Kiểm thử các ngày 28–31 và năm nhuận |
| Cộng tháng liên tiếp nhưng mong luôn về ngày 31 | Bước sau nhận ngày trung gian đã điều chỉnh | Lưu ngày ưu tiên và tính theo kỳ mục tiêu |
| Dùng ngày 30 cố định cho “cuối tháng” | Mỗi tháng có độ dài khác nhau | Dùng `YearMonth.atEndOfMonth()` |
| Coi `Period.ofMonths(1)` là 30 ngày cố định | `Period` là khoảng lịch | Dùng `Duration` cho thời lượng giây/giờ cố định |
| Bỏ qua DST trên `ZonedDateTime` | Giờ địa phương/offset có thể được điều chỉnh | Kiểm tra quy tắc `ZoneId` và DST |
| Dùng timestamp để lưu ý định “ngày cuối tháng” | `Instant` chỉ là điểm thời gian, không giữ lịch lặp | Lưu quy tắc lịch và vùng phù hợp |
| Dựa vào phép tính ngược để phục hồi dữ liệu | Thông tin đã mất không thể suy ra chắc chắn | Lưu giá trị gốc hoặc metadata nghiệp vụ |

## 9. Tự kiểm tra

1. `LocalDate.of(2023, 1, 31).plusMonths(1)` trả ngày nào? **2023-02-28**.
2. Trừ một tháng từ kết quả đó được gì? **2023-01-28**, không phải ngày 31.
3. Vì sao không đảo ngược? **Ngày 31 đã bị điều chỉnh về ngày cuối tháng 2; giá trị trung gian không còn lưu ngày mong muốn gốc**.
4. Cộng một tháng hai lần và cộng hai tháng trực tiếp có luôn giống nhau không? **Không**: 28/03 so với 31/03 trong ví dụ.
5. 29/02/2024 cộng một năm trở thành gì? **28/02/2025**.
6. API nào thể hiện trực tiếp quy tắc “cuối tháng”? **`YearMonth.atEndOfMonth()`**.
7. `LocalDateTime.plusMonths` có giữ giờ không? **Có**, trong khi điều chỉnh ngày theo lịch.
8. Vì sao `ZonedDateTime` còn phức tạp hơn? **Còn phải giải quyết offset và các quy tắc DST của vùng**.
9. Nếu cần giữ ngày mong muốn 31 cho các kỳ sau, nên làm gì? **Lưu ngày ưu tiên hoặc chính sách cuối tháng, không cộng dồn từ ngày đã điều chỉnh**.

**Ghi nhớ:** `plusMonths()` tuân theo lịch và điều chỉnh ngày không tồn tại về cuối tháng. Vì vậy phép cộng-trừ tháng không luôn khả nghịch, và cộng nhiều bước có thể khác cộng một lần. Với lịch lặp, hãy xác định rõ ý định “cộng dồn”, “giữ ngày ưu tiên” hay “cuối tháng”; với `ZonedDateTime` còn cần xét vùng múi giờ/DST.

### Tài liệu tham khảo

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html)
- [Java SE 17 — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html)
