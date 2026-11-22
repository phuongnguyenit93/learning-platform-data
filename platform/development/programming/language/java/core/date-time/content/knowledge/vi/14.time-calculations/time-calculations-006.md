# Phép tính trên các kiểu thời gian khác nhau và yêu cầu kiểu tương thích trong Java

Các phép tính thời gian của `java.time` không chỉ phụ thuộc vào đơn vị được cộng/trừ mà còn phụ thuộc **kiểu temporal đang nhận phép tính**. `LocalDate` mô tả ngày lịch, `LocalDateTime` mô tả ngày giờ địa phương, `Instant` là mốc tuyệt đối, còn `ZonedDateTime` gắn giờ địa phương với quy tắc vùng. Vì vậy, cùng một `TemporalAmount` có thể hợp lệ với kiểu này nhưng không hợp lệ với kiểu khác.

Ví dụ quan trọng:

~~~java
LocalDate date = LocalDate.of(2026, 1, 31);

System.out.println(date.plus(Period.ofMonths(1)));
// 2026-02-28

try {
    System.out.println(date.plus(Duration.ofDays(1)));
} catch (UnsupportedTemporalTypeException ex) {
    System.out.println("LocalDate + Duration: unsupported");
}
~~~

`Period.ofMonths(1)` phù hợp với ngày lịch; `Duration.ofDays(1)` là lượng thời gian 24 giờ gồm giây/nano giây, trong khi `LocalDate` không có trường giờ/giây để áp dụng kiểu phép tính đó. **Đừng chỉ dựa vào việc hai biểu thức đều “cộng một ngày” trong lời nói thông thường**: xác định câu hỏi đang nói về ngày lịch, giờ đồng hồ hay thời lượng thực.

## 1. Ba khái niệm API cần phân biệt

| Khái niệm | Kiểu | Mô tả |
| --- | --- | --- |
| Giá trị thời gian (temporal) | `LocalDate`, `LocalDateTime`, `Instant`, `ZonedDateTime`… | Đối tượng nhận phép tính |
| Lượng thời gian | `TemporalAmount` | Đối tượng mô tả khoảng cần cộng/trừ, ví dụ `Duration`, `Period` |
| Đơn vị thời gian | `TemporalUnit` | Đơn vị được truyền vào `plus(long, unit)`, ví dụ `ChronoUnit.DAYS`, `HOURS`, `MONTHS` |

Hai phương thức nhìn gần giống nhau nhưng có hợp đồng riêng:

~~~java
date.plus(Period.ofMonths(1));  // Nhận TemporalAmount
date.plus(1, ChronoUnit.MONTHS); // Nhận số lượng + TemporalUnit
~~~

Cả hai đều trả về **giá trị mới**, không sửa đối tượng nguồn. Kết quả còn phụ thuộc vào việc kiểu temporal có hỗ trợ đơn vị đó hay không.

### `Period`: đơn vị theo lịch

`Period` biểu diễn năm, tháng và ngày theo lịch, như `Period.ofMonths(1)`, `Period.ofDays(7)`. Nó phù hợp cho câu hỏi “tháng kế tiếp”, “thêm 7 ngày lịch”, “sau một năm theo lịch”. Tuy nhiên, **`Period` không tự mang `ZoneId`**; một `Period` chỉ được áp dụng vào giá trị temporal đang có.

### `Duration`: lượng giây và nano giây cố định

`Duration` biểu diễn thời lượng theo giây và nano giây. `Duration.ofHours(1)` bằng 3.600 giây; `Duration.ofDays(1)` bằng 86.400 giây (24 giờ). Nó phù hợp để đo timeout, khoảng thời gian đã trôi qua, hoặc cộng một lượng cố định vào `Instant`.

Vì vậy một tháng lịch **không thể đại diện chính xác** bằng một `Duration` cố định. Cũng đừng cho rằng một ngày trên đồng hồ của mọi vùng luôn tương đương 24 giờ thực: DST có thể làm ngày địa phương dài 23 hoặc 25 giờ.

### `ChronoUnit`: chọn đơn vị trực tiếp

`ChronoUnit` là enum hiện thực `TemporalUnit`. Một số đơn vị như `NANOS`, `SECONDS`, `MINUTES`, `HOURS`, `DAYS`, `WEEKS`, `MONTHS`, `YEARS` thường dùng trong phép tính và đo khoảng cách. Kiểu temporal quyết định đơn vị có được hỗ trợ không. `LocalDate` hỗ trợ `DAYS` và `MONTHS`, nhưng không hỗ trợ `HOURS`; `Instant` hỗ trợ giờ/ngày như lượng giây trên timeline nhưng không hỗ trợ tháng/năm lịch.

## 2. Ma trận tương thích thực tế

Bảng này tóm tắt các tình huống thường gặp. “Có” nghĩa là phép tính có ngữ nghĩa được hỗ trợ cho trường hợp minh họa; luôn kiểm tra đơn vị cụ thể và phạm vi giá trị.

| Kiểu temporal | `Period.ofDays(1)` | `Period.ofMonths(1)` | `Duration.ofDays(1)` | `Duration.ofHours(1)` | `plus(1, DAYS)` | `plus(1, HOURS)` | `plus(1, MONTHS)` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `LocalDate` | Có | Có | Không | Không | Có | Không | Có |
| `LocalTime` | Không | Không | Có nếu đơn vị giờ/giây được hỗ trợ | Có | Có (vòng qua nửa đêm) | Có | Không |
| `LocalDateTime` | Có | Có | Có | Có | Có | Có | Có |
| `Instant` | Có: ngày được tính là 24 giờ | Không | Có | Có | Có: ngày là 24 giờ | Có | Không |
| `OffsetDateTime` | Có | Có | Có | Có | Có | Có | Có |
| `ZonedDateTime` | Có | Có | Có | Có | Có | Có | Có |

**Lưu ý quan trọng:**

- `LocalTime.plus(Period.ofDays(1))` không được hiểu là tiến qua một ngày lịch: `LocalTime` không mang ngày. Những trường hợp không áp dụng được lượng `Period` có thành phần lịch sẽ báo `UnsupportedTemporalTypeException`.
- `Instant.plus(Period.ofDays(1))` được hỗ trợ vì trường ngày được diễn giải trên timeline như **24 giờ**; nhưng `Instant.plus(Period.ofMonths(1))` không có khái niệm tháng lịch trên instant và không được hỗ trợ.
- `ZonedDateTime` nhận các loại lượng thời gian/đơn vị nói trên, nhưng ý nghĩa khác nhau: cộng ngày/tháng/năm theo local timeline, cộng giờ/giây theo timeline thời lượng. Vì thế DST có thể khiến kết quả hiển thị khác nhau.
- Một phép tính có thể hợp lệ nhưng vẫn **sai ý nghĩa nghiệp vụ**. `Instant.plus(Period.ofDays(1))` là cộng 24 giờ; nếu yêu cầu là ngày mai cùng giờ ở Paris, phải tính trên `ZonedDateTime`.

Ma trận hướng dẫn chọn API, không thay thế tài liệu hợp đồng của từng phương thức và không bao hàm mọi trường hợp biên, calendar, overflow hoặc lượng thời gian hỗn hợp.

## 3. Vì sao một số phép tính ném `UnsupportedTemporalTypeException`?

Các kiểu `java.time` triển khai các giao diện chung, nhưng không phải mọi loại thời gian đều có mọi trường hay đơn vị. `LocalDate` có ngày-tháng-năm nhưng **không có giờ, phút, giây**; `Instant` biểu diễn mốc trên timeline chứ không có “tháng địa phương”; `LocalTime` không có ngày hoặc tháng để thay đổi.

Ví dụ:

~~~java
LocalDate date = LocalDate.of(2026, 1, 31);

date.plus(1, ChronoUnit.MONTHS); // hợp lệ: 2026-02-28
date.plus(1, ChronoUnit.HOURS);  // UnsupportedTemporalTypeException
~~~

Khi gọi `plus(amount)`, kiểu temporal xử lý `TemporalAmount.addTo(this)`; chính lượng thời gian sẽ thực hiện các phép `plus` tương ứng. Vì vậy, `Period` và `Duration` có các thành phần/đơn vị khác nhau, và kiểu temporal đích phải hỗ trợ chúng.

Ví dụ khác:

~~~java
Instant timestamp = Instant.parse("2026-01-15T00:00:00Z");

timestamp.plus(Duration.ofHours(3)); // 2026-01-15T03:00:00Z
timestamp.plus(1, ChronoUnit.MONTHS); // UnsupportedTemporalTypeException
~~~

`Instant` không có múi giờ để biết “một tháng địa phương” dài bao lâu. Nếu nghiệp vụ yêu cầu một tháng lịch, hãy chọn vùng và ngày giờ địa phương trước, chẳng hạn `zoned.plusMonths(1)`, hoặc tính trên `LocalDate`/`LocalDateTime` rồi giải thích bằng `ZoneId`.

**Đừng bắt mọi ngoại lệ rồi tiếp tục với giá trị mặc định.** Một đơn vị không được hỗ trợ thường biểu thị lỗi mô hình hóa: bạn có thể đang dùng kiểu sai cho nghiệp vụ. Nên chọn đúng kiểu temporal hoặc kiểm tra ngoại lệ ở biên API khi đầu vào cho phép nhiều đơn vị.

## 4. Java 17+: chương trình kiểm chứng kiểu và đơn vị tương thích

Tạo tệp **`TemporalCompatibilityDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;

public class TemporalCompatibilityDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 1, 31);

        System.out.println("datePlusPeriod = "
                + date.plus(Period.ofMonths(1)));
        try {
            date.plus(Duration.ofDays(1));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("datePlusDuration = "
                    + ex.getClass().getSimpleName());
        }

        Instant instant = Instant.parse("2026-01-15T00:00:00Z");
        System.out.println("instantPlusDuration = "
                + instant.plus(Duration.ofHours(3)));
        try {
            instant.plus(1, ChronoUnit.MONTHS);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("instantPlusMonths = "
                    + ex.getClass().getSimpleName());
        }

        LocalDateTime local =
                LocalDateTime.of(2026, 1, 31, 23, 30);
        System.out.println("ldtPlusDuration = "
                + local.plus(Duration.ofHours(2)));
        System.out.println("ldtPlusPeriod = "
                + local.plus(Period.ofMonths(1)));

        ZonedDateTime paris = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0,
                ZoneId.of("Europe/Paris"));
        System.out.println("zonedPlusDurationDay = "
                + paris.plus(Duration.ofDays(1)));
        System.out.println("zonedPlusPeriodDay = "
                + paris.plus(Period.ofDays(1)));

        System.out.println("datePlusOneMonth = "
                + date.plus(1, ChronoUnit.MONTHS));
        System.out.println("ldtPlus24Hours = "
                + local.plus(24, ChronoUnit.HOURS));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TemporalCompatibilityDemo.java
java TemporalCompatibilityDemo
~~~

Kết quả:

~~~text
datePlusPeriod = 2026-02-28
datePlusDuration = UnsupportedTemporalTypeException
instantPlusDuration = 2026-01-15T03:00:00Z
instantPlusMonths = UnsupportedTemporalTypeException
ldtPlusDuration = 2026-02-01T01:30
ldtPlusPeriod = 2026-02-28T23:30
zonedPlusDurationDay = 2024-03-31T13:00+02:00[Europe/Paris]
zonedPlusPeriodDay = 2024-03-31T12:00+02:00[Europe/Paris]
datePlusOneMonth = 2026-02-28
ldtPlus24Hours = 2026-02-01T23:30
~~~

Kết quả đã được kiểm tra bằng Java JShell với các giá trị đầu vào cố định. Có thể rút ra:

- `LocalDate.plus(Period.ofMonths(1))` điều chỉnh 31/01 về ngày hợp lệ cuối tháng Hai.
- `LocalDate.plus(Duration.ofDays(1))` thất bại vì `LocalDate` không hỗ trợ phần thời lượng theo giây/giờ.
- `Instant.plus(Duration.ofHours(3))` hợp lệ, nhưng `Instant.plus(1, MONTHS)` thất bại vì tháng lịch cần ngữ cảnh lịch.
- `LocalDateTime` không có zone, nên cộng 24 giờ và cộng một ngày đều chuyển trường giờ tới ngày kế tiếp theo lịch, nhưng `plus(Period.ofMonths(1))` tuân theo quy tắc cuối tháng.
- `ZonedDateTime` của Paris cho kết quả 13:00 khi cộng 24 giờ nhưng 12:00 khi cộng một ngày lịch qua thời điểm đổi DST.

## 5. Đơn vị tương thích chưa chắc có nghĩa nghiệp vụ tương thích

Một lỗi tinh vi là chọn một phép tính **được Java hỗ trợ** nhưng không đáp ứng đúng câu hỏi.

### “Sau 24 giờ” và “ngày mai cùng giờ”

~~~java
ZonedDateTime meeting = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime sameClockTomorrow = meeting.plusDays(1);
ZonedDateTime elapsed24Hours = meeting.plus(Duration.ofHours(24));
~~~

Cả hai lời gọi hợp lệ nhưng kết quả khác nhau khi đi qua DST. `sameClockTomorrow` đáp ứng lịch địa phương; `elapsed24Hours` đáp ứng khoảng thời lượng cố định.

### “Một tháng sau” và “30 ngày sau”

~~~java
LocalDate invoiceDate = LocalDate.of(2026, 1, 31);

System.out.println(invoiceDate.plusMonths(1)); // 2026-02-28
System.out.println(invoiceDate.plusDays(30));   // 2026-03-02
~~~

Hai phép tính đều hợp lệ trên `LocalDate`, nhưng không tương đương. Chọn theo điều khoản hợp đồng chứ không theo việc phương thức có cùng kiểu trả về.

### Ngày lịch không phải một timestamp

~~~java
LocalDate billingDate = LocalDate.of(2026, 1, 31);
LocalDate nextBillingDate = billingDate.plus(Period.ofMonths(1));
~~~

Đây phù hợp với ngày hóa đơn hoặc ngày hiệu lực. Nếu yêu cầu là “tác vụ chạy đúng 24 giờ sau thời điểm phát hành”, cần `Instant` và `Duration`. Nếu yêu cầu “đầu ngày theo giờ Hà Nội”, cần kết hợp `LocalDate` với `ZoneId` để có biên instant.

## 6. Cách chọn phép tính theo kiểu dữ liệu

| Nhu cầu | Kiểu và phép tính nên xem xét | Lý do |
| --- | --- | --- |
| Hạn sau 45 phút | `Instant.plus(Duration.ofMinutes(45))` | Thời lượng cố định |
| Ngày lịch tiếp theo | `LocalDate.plusDays(1)` | Chỉ quan tâm lịch |
| Một tháng sau ngày hóa đơn | `LocalDate.plusMonths(1)` | Theo tháng lịch và có quy tắc cuối tháng |
| Lịch hẹn ngày mai cùng giờ trong một vùng | `ZonedDateTime.plusDays(1)` | Giữ giờ dân sự theo vùng và áp quy tắc DST |
| Hết hạn sau 24 giờ kể từ một sự kiện | `Instant.plus(Duration.ofHours(24))` | Cộng đúng 86.400 giây |
| Kỳ hạn 1 năm theo lịch địa phương | `LocalDate`/`LocalDateTime` + `Period.ofYears(1)` | Tuân theo lịch, gồm các quy tắc cuối tháng/năm nhuận |
| Sự kiện tuyệt đối chuyển cho người xem ở vùng khác | `Instant.atZone(zone)` | Bảo toàn instant, đổi biểu diễn |
| Khoảng cách giữa hai timestamp | `Duration.between(a, b)` khi cả hai có timeline | Đo thời lượng; không suy luận ngày/tháng lịch |

Chọn kiểu từ **ý nghĩa nghiệp vụ trước**, rồi kiểm tra Java hỗ trợ phép tính hay không. Nếu kết quả không phù hợp, đổi đơn vị cho đúng hoặc đổi kiểu temporal có ngữ nghĩa phù hợp; đừng lách ngoại lệ bằng cách biến ngày thành timestamp giả.

## 7. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cộng `Duration` vào `LocalDate` | Ném `UnsupportedTemporalTypeException` | Dùng `Period`/đơn vị ngày tháng, hoặc chọn kiểu chứa giờ nếu thực sự cần thời lượng |
| Cộng tháng vào `Instant` | Không có khái niệm tháng địa phương trên timeline | Chọn `ZoneId` và tính theo ngày/giờ lịch |
| Dùng `Period.ofDays(1)` như một khoảng 24 giờ trên `Instant` mà không nói rõ | Người đọc dễ nhầm đơn vị lịch với thời lượng cố định | Dùng `Duration.ofDays(1)` nếu nghĩa là 86.400 giây |
| Dùng `Duration.ofDays(1)` cho “ngày mai cùng giờ” tại vùng DST | Có thể lệch 1 giờ | Cộng ngày trên `ZonedDateTime` |
| Nghĩ mọi phép `plus(...)` đều mutating | Bỏ kết quả khiến biến không đổi | Gán lại hoặc nhận giá trị trả về |
| Nghĩ phép tính hợp lệ là đúng nghiệp vụ | “30 ngày” có thể khác “một tháng” | Làm rõ đơn vị/ranh giới trong yêu cầu |
| Chỉ bắt ngoại lệ và trả lại giá trị gốc | Che lỗi mô hình hóa | Kiểm tra kiểu, đơn vị và thông báo lỗi rõ ràng |

## 8. Checklist review code

1. Temporal đang dùng là `LocalDate`, `LocalDateTime`, `Instant` hay `ZonedDateTime`? Kiểu đó có các trường cần thiết cho phép tính không?
2. Amount là `Period` (năm/tháng/ngày theo lịch) hay `Duration` (giây/nano giây)? Đơn vị có đúng với yêu cầu?
3. Phương thức `plus(amount)` hay `plus(n, unit)` đó có hỗ trợ kiểu/đơn vị cụ thể không?
4. Nếu phép tính gắn với vùng múi giờ, có cần phân biệt ngày lịch với thời lượng qua DST?
5. Kết quả có đi qua cuối tháng, năm nhuận hoặc giới hạn phạm vi không?
6. Đã nhận giá trị trả về từ phép biến đổi immutable chưa?
7. Unit test có kiểm tra cả kết quả đúng lẫn trường hợp không hỗ trợ hay không?

### Tự kiểm tra

- `LocalDate.plus(Period.ofMonths(1))` hợp lệ không? **Có**, tính theo tháng lịch.
- `LocalDate.plus(Duration.ofDays(1))` hợp lệ không? **Không**, `Duration` dùng giây/nano giây mà `LocalDate` không có.
- `Instant.plus(Duration.ofDays(1))` là bao lâu? **86.400 giây**.
- `Instant.plus(1, ChronoUnit.MONTHS)` hợp lệ không? **Không**, instant không chứa tháng lịch.
- `ZonedDateTime.plusDays(1)` và `plus(Duration.ofDays(1))` luôn cho cùng giờ địa phương không? **Không**, đi qua DST có thể khác một giờ.
- Nếu nghiệp vụ cần ngày làm việc, `Period.ofDays(1)` đã đủ chưa? **Chưa**; cần quy tắc ngày làm việc, cuối tuần và ngày lễ.

**Ghi nhớ:** Kiểu temporal quy định bạn có thể thay đổi trường nào; `TemporalAmount`/`TemporalUnit` quy định phép tính muốn áp dụng; nghiệp vụ mới quyết định phép tính nào đúng. `Period` diễn đạt đơn vị lịch, `Duration` diễn đạt thời lượng cố định, còn `ChronoUnit` là lựa chọn đơn vị. Hãy kiểm tra **cả tính tương thích API lẫn ý nghĩa thực tế** trước khi dùng kết quả.