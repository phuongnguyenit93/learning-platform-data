# Cộng trừ thời gian khi đi qua ranh giới ngày, tháng và năm với `LocalDateTime`

Một phép tính đơn giản như `2026-01-31T23:30.plusHours(2)` phải trả về **`2026-02-01T01:30`**. Không cần tự tăng ngày hoặc đổi tháng; `java.time.LocalDateTime` xử lý các ranh giới theo quy tắc lịch ISO-8601. Tuy nhiên, **cộng một tháng không giống cộng một số ngày cố định**, các ngày cuối tháng cần điều chỉnh và phép tính trên `LocalDateTime` **không áp dụng quy tắc múi giờ/DST**.

Bài học này giúp bạn chọn đúng phép cộng/trừ theo *giờ đồng hồ*, *ngày lịch*, *tháng lịch* và *năm lịch*, cũng như kiểm tra những trường hợp dễ sai ở cuối tháng, năm nhuận và giao thừa.

## 1. Hiểu đối tượng đang tính toán

`LocalDateTime` kết hợp ngày và giờ địa phương theo lịch ISO, có độ chính xác đến nano giây. Nó chứa các trường năm, tháng, ngày, giờ, phút, giây, nano giây, nhưng **không chứa `ZoneId`, `ZoneOffset` hoặc một `Instant`**.

Ví dụ:

~~~java
LocalDateTime start = LocalDateTime.of(2026, 1, 31, 23, 30);
LocalDateTime result = start.plusHours(2);
System.out.println(result); // 2026-02-01T01:30
~~~

*Đây là đoạn minh họa để đặt trong một method với `import java.time.LocalDateTime;`.*

`plusHours(2)` cộng vào giờ địa phương, tự mang phần vượt 24 giờ sang **ngày kế tiếp**. Vì `LocalDateTime` bất biến, `start` vẫn là `2026-01-31T23:30`; bạn phải **nhận giá trị trả về** nếu muốn sử dụng thời điểm địa phương đã tính.

Không cần tự viết logic kiểu “nếu giờ vượt 23 thì tăng ngày”. Java tự kiểm soát số ngày mỗi tháng và năm nhuận, bao gồm đổi tháng, đổi năm theo cả chiều cộng và trừ.

## 2. Cộng hoặc trừ đơn vị nhỏ: tự vượt ngày, tháng, năm

Các phương thức phổ biến:

| Đơn vị | Cộng | Trừ | Điều xảy ra ở ranh giới |
| --- | --- | --- | --- |
| Nano giây | `plusNanos(n)` | `minusNanos(n)` | Mang sang giây/phút/giờ nếu vượt |
| Giây | `plusSeconds(n)` | `minusSeconds(n)` | Mang sang phút, ngày mới khi cần |
| Phút | `plusMinutes(n)` | `minusMinutes(n)` | Mang sang giờ và ngày |
| Giờ | `plusHours(n)` | `minusHours(n)` | Mang sang ngày, tháng, năm |
| Ngày | `plusDays(n)` | `minusDays(n)` | Tiến/lùi theo lịch ISO |
| Tuần | `plusWeeks(n)` | `minusWeeks(n)` | Mỗi tuần là 7 ngày lịch |
| Tháng | `plusMonths(n)` | `minusMonths(n)` | Giữ ngày trong tháng nếu tồn tại; nếu không, điều chỉnh cuối tháng |
| Năm | `plusYears(n)` | `minusYears(n)` | Điều chỉnh ngày 29/02 khi năm đích không nhuận |

### Qua nửa đêm và hết tháng

~~~java
LocalDateTime a = LocalDateTime.of(2026, 1, 31, 23, 30);
LocalDateTime b = a.plusHours(2);
// a: 2026-01-31T23:30
// b: 2026-02-01T01:30

LocalDateTime c = LocalDateTime.of(2026, 3, 1, 0, 0);
LocalDateTime d = c.minusNanos(1);
// d: 2026-02-28T23:59:59.999999999
~~~

Đối tượng `d` không mang offset UTC; việc chuyển từ tháng Ba về tháng Hai là phép trừ trên ngày/giờ đồng hồ ISO thuần túy.

### Qua đêm giao thừa, cả chiều cộng và trừ

~~~java
LocalDateTime yearEnd = LocalDateTime.of(2025, 12, 31, 23, 50);
LocalDateTime newYear = yearEnd.plusMinutes(20);
// 2026-01-01T00:10

LocalDateTime firstMinutes = LocalDateTime.of(2026, 1, 1, 0, 15);
LocalDateTime oldYear = firstMinutes.minusMinutes(30);
// 2025-12-31T23:45
~~~

Không cần kiểm tra “ngày cuối năm” theo mã tự viết. Các phương thức tính toán của `LocalDateTime` sẽ đi tới ngày hợp lệ kế tiếp hoặc trước đó, miễn là kết quả vẫn nằm trong phạm vi hỗ trợ.

## 3. Điểm khó nhất: cộng tháng và năm có thể phải sửa ngày cuối tháng

Khác cộng giờ/phút, **một tháng không có số ngày cố định**. Khi cộng hoặc trừ tháng, Java thực hiện về cơ bản:

1. Tính năm và tháng đích.
2. Thử giữ nguyên ngày trong tháng từ giá trị gốc.
3. Nếu tháng đích không có ngày đó, dùng **ngày cuối cùng hợp lệ** của tháng đích.
4. Giữ các trường giờ, phút, giây và nano giây của `LocalDateTime` khi thao tác tháng/năm không đòi thay đổi chúng.

Ví dụ:

| Giá trị ban đầu | Phép tính | Kết quả |
| --- | --- | --- |
| `2026-01-31T10:15` | `plusMonths(1)` | `2026-02-28T10:15` |
| `2024-01-31T10:15` | `plusMonths(1)` | `2024-02-29T10:15` |
| `2026-03-31T08:00` | `minusMonths(1)` | `2026-02-28T08:00` |
| `2024-02-29T12:00` | `plusYears(1)` | `2025-02-28T12:00` |
| `2024-03-01T00:00` | `minusDays(1)` | `2024-02-29T00:00` |

Năm 2024 nhuận nên tháng Hai có ngày 29; năm 2025 và 2026 không nhuận nên tháng Hai chỉ có 28 ngày. **Không thể giữ ngày 31 ở tháng Hai**; hành vi điều chỉnh này là quy tắc cố định của `LocalDateTime.plusMonths`/`minusMonths`, không phải lỗi làm tròn của máy.

### Phép cộng và trừ tháng không luôn hoàn tác cho nhau

~~~java
LocalDateTime original = LocalDateTime.of(2026, 1, 31, 8, 0);
LocalDateTime february = original.plusMonths(1);
// 2026-02-28T08:00

LocalDateTime back = february.minusMonths(1);
// 2026-01-28T08:00 — KHÔNG phải 31/01.
~~~

Đây là hệ quả của việc **ngày 31 đã bị điều chỉnh thành 28**. Sau bước đầu, đối tượng trung gian không còn thông tin rằng yêu cầu ban đầu neo ở “ngày 31” của tháng.

Với hóa đơn định kỳ, bảng lương hoặc lịch chạy mỗi tháng, cần định nghĩa rõ nghiệp vụ là **“ngày 31 nếu có, nếu không lấy cuối tháng”**, **“ngày cuối tháng”**, hay **“cứ sau một tháng kể từ lần trước”**. Chúng không phải lúc nào cũng cho cùng kết quả.

## 4. Thứ tự biến đổi cũng làm kết quả khác nhau

Các phép cộng ngày và tháng nói chung **không giao hoán** khi có bước điều chỉnh cuối tháng:

~~~java
LocalDateTime x = LocalDateTime.of(2026, 1, 30, 8, 0);

LocalDateTime firstMonth = x.plusMonths(1).plusDays(1);
// 2026-03-01T08:00
// 30/01 + 1 tháng -> 28/02; + 1 ngày -> 01/03.

LocalDateTime firstDay = x.plusDays(1).plusMonths(1);
// 2026-02-28T08:00
// 30/01 + 1 ngày -> 31/01; + 1 tháng -> 28/02.
~~~

Nên viết thứ tự phép tính sao cho phản ánh đúng câu chữ nghiệp vụ. Không tự đổi thứ tự `plusMonths` và `plusDays` vì nghĩ rằng đều là phép cộng thời gian.

### Lịch lặp hằng tháng: giữ một ngày neo gốc

~~~java
LocalDateTime anchor = LocalDateTime.of(2026, 1, 31, 9, 0);

LocalDateTime repeated =
        anchor.plusMonths(1).plusMonths(1);
// 2026-03-28T09:00

LocalDateTime fromAnchor =
        anchor.plusMonths(2);
// 2026-03-31T09:00
~~~

Nếu lịch định nghĩa **“lần thứ N sau ngày 31/01”**, tính từ `anchor.plusMonths(n)` sẽ giữ ý định ngày gốc tốt hơn cách lặp `result = result.plusMonths(1)`. Nếu lịch thật sự định nghĩa “sau một tháng tính từ lần phát sinh trước”, kết quả lặp lại có thể lại là điều mong muốn. Hãy ghi rõ quy tắc thay vì mặc định hai cách tương đương.

## 5. Chương trình Java 17+ đầy đủ: kiểm chứng tất cả ranh giới

Tạo tệp **`LocalDateTimeBoundaryDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class LocalDateTimeBoundaryDemo {
    public static void main(String[] args) {
        LocalDateTime endJan =
                LocalDateTime.of(2026, 1, 31, 23, 30);
        endJan.plusHours(2); // Bỏ kết quả, endJan không đổi.
        System.out.println("original = " + endJan);

        LocalDateTime afterMidnight = endJan.plusHours(2);
        System.out.println("plusHours(2) = " + afterMidnight);

        LocalDateTime lastMinute =
                LocalDateTime.of(2025, 12, 31, 23, 50);
        System.out.println("newYear = "
                + lastMinute.plusMinutes(20));
        System.out.println("minusMinutes(30) = "
                + LocalDateTime.of(2026, 1, 1, 0, 15)
                               .minusMinutes(30));

        System.out.println("month2026 = "
                + LocalDateTime.of(2026, 1, 31, 10, 15)
                               .plusMonths(1));
        System.out.println("month2024 = "
                + LocalDateTime.of(2024, 1, 31, 10, 15)
                               .plusMonths(1));
        System.out.println("leapPlusYear = "
                + LocalDateTime.of(2024, 2, 29, 12, 0)
                               .plusYears(1));
        System.out.println("minusMonth = "
                + LocalDateTime.of(2026, 3, 31, 8, 0)
                               .minusMonths(1));

        LocalDateTime jan30 =
                LocalDateTime.of(2026, 1, 30, 8, 0);
        System.out.println("monthThenDay = "
                + jan30.plusMonths(1).plusDays(1));
        System.out.println("dayThenMonth = "
                + jan30.plusDays(1).plusMonths(1));

        LocalDateTime anchor =
                LocalDateTime.of(2026, 1, 31, 9, 0);
        System.out.println("chainTwoMonths = "
                + anchor.plusMonths(1).plusMonths(1));
        System.out.println("fromAnchorTwoMonths = "
                + anchor.plusMonths(2));

        System.out.println("daysBetweenDateTimes = "
                + ChronoUnit.DAYS.between(endJan, afterMidnight));
        System.out.println("daysBetweenDates = "
                + ChronoUnit.DAYS.between(
                    endJan.toLocalDate(),
                    afterMidnight.toLocalDate()));

        ZonedDateTime paris =
                ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0,
                        ZoneId.of("Europe/Paris"));
        System.out.println("parisBase = " + paris);
        System.out.println("parisPlusDay = " + paris.plusDays(1));
        System.out.println("parisPlus24h = " + paris.plusHours(24));
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac LocalDateTimeBoundaryDemo.java
java LocalDateTimeBoundaryDemo
~~~

Kết quả:

~~~text
original = 2026-01-31T23:30
plusHours(2) = 2026-02-01T01:30
newYear = 2026-01-01T00:10
minusMinutes(30) = 2025-12-31T23:45
month2026 = 2026-02-28T10:15
month2024 = 2024-02-29T10:15
leapPlusYear = 2025-02-28T12:00
minusMonth = 2026-02-28T08:00
monthThenDay = 2026-03-01T08:00
dayThenMonth = 2026-02-28T08:00
chainTwoMonths = 2026-03-28T09:00
fromAnchorTwoMonths = 2026-03-31T09:00
daysBetweenDateTimes = 0
daysBetweenDates = 1
parisBase = 2024-03-30T12:00+01:00[Europe/Paris]
parisPlusDay = 2024-03-31T12:00+02:00[Europe/Paris]
parisPlus24h = 2024-03-31T13:00+02:00[Europe/Paris]
~~~

Các phép toán trong đầu ra được đối chiếu với Java; dữ liệu đầu vào cố định nên không phụ thuộc ngày hiện tại. Những dòng về `Europe/Paris` minh họa theo quy tắc DST năm 2024 của vùng này.

## 6. “Đi qua ngày mới” không giống “đủ một ngày đã trôi qua”

Trong chương trình vừa chạy, `endJan` là `2026-01-31T23:30` và `afterMidnight` là `2026-02-01T01:30`. Hai giá trị cách nhau **2 giờ đồng hồ địa phương**, nhưng thuộc **hai ngày lịch** khác nhau:

- `ChronoUnit.DAYS.between(endJan, afterMidnight)` trả về **0**, vì chưa có một đơn vị ngày hoàn chỉnh giữa hai `LocalDateTime`.
- `ChronoUnit.DAYS.between(endJan.toLocalDate(), afterMidnight.toLocalDate())` trả về **1**, vì hai phần **ngày lịch** cách nhau một ngày.

Nếu muốn **đếm số ranh giới ngày đã vượt**, lấy phần `LocalDate` trước khi tính khoảng cách ngày. Nếu muốn đếm **số đơn vị ngày hoàn chỉnh** trong một khoảng local date-time, đừng bỏ phần giờ.

Cũng vì lý do đó, việc đổi phút, giờ thành “ngày” không thể thay thế trực tiếp yêu cầu kế toán “ngày nào”. Tính đúng loại dữ liệu trước, sau đó mới quyết định dùng `ChronoUnit`, `Period` hay `Duration`.

## 7. `Period` và `Duration`: hai kiểu lượng thời gian khác nhau

Java hỗ trợ hai cách diễn đạt phổ biến:

| Kiểu | Diễn đạt | Ví dụ | Dùng khi |
| --- | --- | --- | --- |
| `Period` | Năm, tháng, ngày theo lịch | `Period.ofMonths(1)` | Quy tắc “sang tháng sau”, “sang năm sau”, kỳ lịch |
| `Duration` | Lượng thời gian theo giây/nano giây | `Duration.ofHours(24)` | Thời lượng đã trôi qua, timeout, khoảng giờ/phút/giây |

Ví dụ với `LocalDateTime`:

~~~java
LocalDateTime start = LocalDateTime.of(2026, 1, 31, 23, 30);

LocalDateTime nextCalendarMonth = start.plus(Period.ofMonths(1));
// 2026-02-28T23:30

LocalDateTime after24HoursOnClock = start.plus(Duration.ofHours(24));
// 2026-02-01T23:30
~~~

*Đoạn này dùng import `java.time.LocalDateTime`, `java.time.Period` và `java.time.Duration`; có thể đặt trong method bất kỳ.*

**Một tháng và 24 giờ không thể xem là tương đương.** Thậm chí `Period.ofDays(1)` và `Duration.ofDays(1)` dù cho cùng ngày giờ khi cộng vào một `LocalDateTime` thông thường, lại thể hiện ý nghĩa khác nếu bạn chuyển qua mô hình **có vùng múi giờ**.

Ở đây `LocalDateTime` **không biết DST**: `plusDays(1)` và `plusHours(24)` đi tới cùng giá trị ngày giờ địa phương, vì nó chỉ tính trên lịch và đồng hồ ISO. Nhưng một ngày **theo lịch trong một vùng** có thể dài **23 hoặc 25 giờ thực**.

## 8. Khi có `ZoneId`: ngày lịch và 24 giờ thực có thể khác

Hai dòng cuối của ví dụ Java cho thấy thời điểm 12:00 tại Paris trước ngày đổi DST:

~~~java
ZonedDateTime paris =
        ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0,
                ZoneId.of("Europe/Paris"));

ZonedDateTime nextCalendarDay = paris.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris]

ZonedDateTime after24ElapsedHours = paris.plusHours(24);
// 2024-03-31T13:00+02:00[Europe/Paris]
~~~

*Đây là đoạn minh họa trong method với import `java.time.ZonedDateTime` và `java.time.ZoneId`.*

Ngày 31/03/2024, Paris chuyển từ UTC+01 sang UTC+02. Khoảng 12:00 ngày 30/03 tới 12:00 ngày 31/03 theo đồng hồ Paris dài **23 giờ thực**, nên:

- `plusDays(1)`: giữ ý định **cùng giờ 12:00 vào ngày lịch kế tiếp**. Với `ZonedDateTime`, ngày là đơn vị theo local timeline.
- `plusHours(24)`: cộng **24 giờ đã trôi qua** trên instant timeline, kết quả đồng hồ là **13:00** ngày 31/03.

Vì vậy hãy xác định trước bài toán hỏi **“ngày mai cùng giờ”** hay **“sau đúng 24 giờ”**. Nếu nghiệp vụ cần timeline tuyệt đối để tính timeout hoặc hạn xử lý theo giây, dùng `Instant`/`Duration` với vùng khi hiển thị. Nếu nghiệp vụ cần lịch hẹn địa phương, dùng ngày/giờ local cùng `ZoneId` và quy tắc xử lý chuyển DST.

Khi chỉ có `LocalDateTime`, một ngày giờ rơi trong **gap** (không tồn tại) hoặc **overlap** (xảy ra hai lần) tại vùng DST vẫn có thể được biểu diễn như những trường số bình thường. Chỉ khi gắn zone và giải quyết quy tắc vùng mới biết instant nào hợp lệ. **Không gọi `LocalDateTime` là timestamp tuyệt đối** và không kỳ vọng phép cộng giờ của nó đã xử lý DST.

## 9. Những sai lầm thực tế khi tính hạn và lịch định kỳ

### Lỗi 1: Tự tính số ngày của tháng

~~~java
// Dễ sai nếu tự giả định tháng Hai 28 ngày mỗi năm:
LocalDateTime manuallyComputed = LocalDateTime.of(2024, 2, 28, 10, 0);

// Java tự nhận biết năm nhuận:
LocalDateTime computed =
        LocalDateTime.of(2024, 1, 31, 10, 0).plusMonths(1);
// 2024-02-29T10:00
~~~

Đoạn này nằm trong method và cần `LocalDateTime` được import. Khi chỉ muốn một ngày lịch không chứa giờ, nên dùng `LocalDate` thay vì thêm giờ 00:00 không cần thiết.

### Lỗi 2: Cộng theo ngày cố định khi quy định là tháng

`plusDays(30)` không đồng nghĩa `plusMonths(1)`:

- Từ `2026-01-31T10:00`, `plusDays(30)` ra **`2026-03-02T10:00`**.
- Từ cùng giá trị, `plusMonths(1)` ra **`2026-02-28T10:00`**.

Trong hợp đồng, “sau 30 ngày”, “sau một tháng” và “ngày cuối tháng tới” có thể là ba cách tính khác nhau. Chọn phép toán dựa theo **quy định chính xác**, không dựa vào kết quả gần đúng.

### Lỗi 3: Bỏ giá trị trả về

~~~java
LocalDateTime deadline = LocalDateTime.of(2025, 12, 31, 23, 0);
deadline.plusHours(2);              // Không đổi deadline.
deadline = deadline.plusHours(2);   // Bây giờ deadline là 2026-01-01T01:00.
~~~

Các kiểu giá trị `java.time` chính là **immutable**. Gán lại biến làm biến trỏ đến kết quả, không sửa đối tượng cũ.

### Lỗi 4: Giả định cộng và trừ tháng luôn là hai phép ngược nhau

`2026-01-31.plusMonths(1).minusMonths(1)` ra **28/01**, không phải 31/01. Muốn khôi phục giá trị cũ phải **giữ bản gốc**; khi tính lịch định kỳ, giữ ngày neo để tránh trôi ngày qua các tháng ngắn.

### Lỗi 5: Dùng phần ngày để tính đúng 24 giờ

`2026-01-31T23:30` tới `2026-02-01T01:30` vượt qua **một ranh giới ngày**, nhưng khoảng giữa chỉ **hai giờ local**. Muốn đếm ngày lịch và muốn đếm giờ đã trôi qua là hai câu hỏi khác nhau; nếu cần giờ đã trôi qua chính xác qua DST, dùng instant.

### Lỗi 6: Quên kiểm tra phạm vi hợp lệ hoặc input bất thường

`LocalDateTime` hỗ trợ phạm vi năm hữu hạn và ngày hợp lệ theo lịch. Tạo `2026-02-30` hoặc cộng số năm đủ lớn để vượt phạm vi sẽ gây ngoại lệ, không tự quay vòng vô hạn. `DateTimeException` có thể xảy ra với giá trị kết quả không hợp lệ; một số toán tử số lượng cực lớn có thể gây `ArithmeticException`. Với dữ liệu từ người dùng, kiểm tra điều kiện nghiệp vụ và phản hồi lỗi có ý nghĩa.

## 10. Checklist trước khi viết phép cộng trừ ngày giờ

1. Dữ liệu có thực sự là `LocalDateTime` (ngày và giờ địa phương), hay phải dùng `LocalDate`, `ZonedDateTime`, `Instant`?
2. Đơn vị “ngày/tháng/năm” là **đơn vị lịch**, còn “giờ/phút/giây” là lượng **thời gian đã trôi qua** hay chỉ là phép tính giờ đồng hồ?
3. Phép cộng `plusMonths` hoặc `plusYears` có thể đi vào **tháng ngắn hơn/năm không nhuận** không?
4. Với lịch định kỳ, có cần **giữ ngày neo gốc** để tránh trôi ngày ở lần tiếp theo không?
5. Nếu chain nhiều phép tính, thứ tự biến đổi đã phản ánh đúng yêu cầu chưa?
6. Đã **nhận lại kết quả** của `plus...`, `minus...`, `with...` chưa?
7. Nếu cần đếm ngày, đang đếm **ranh giới ngày lịch** hay **các ngày hoàn chỉnh giữa hai local date-time**?
8. Nếu có múi giờ và DST, đã tách yêu cầu **“ngày mai cùng giờ”** khỏi **“sau đúng 24 giờ”** chưa?
9. Đã thử test qua nửa đêm, cuối tháng 28/29/30/31 ngày, giao thừa, năm nhuận, cộng/trừ âm và vùng DST (nếu áp dụng) chưa?

### Tự kiểm tra

- `2026-01-31T23:30.plusHours(2)` bằng bao nhiêu? **`2026-02-01T01:30`**.
- `2025-12-31T23:50.plusMinutes(20)` bằng bao nhiêu? **`2026-01-01T00:10`**.
- `2024-01-31T10:15.plusMonths(1)` ra 28 hay 29/02? **29/02/2024**, vì 2024 nhuận.
- `2024-02-29T12:00.plusYears(1)` sẽ ném lỗi vì 2025 không có 29/02? **Không**; Java điều chỉnh về **`2025-02-28T12:00`**.
- Tại sao `plusMonths(1).plusDays(1)` có thể khác `plusDays(1).plusMonths(1)`? **Vì cộng tháng có thể điều chỉnh về ngày cuối hợp lệ**.
- `LocalDateTime.plusDays(1)` có đảm bảo đã trôi qua đúng 24 giờ UTC khi áp vùng? **Không**; `LocalDateTime` chưa có zone, còn ngày địa phương ở vùng DST có thể dài 23/25 giờ.

**Ghi nhớ:** `LocalDateTime` tự thực hiện cộng trừ qua ngày, tháng, năm theo lịch ISO và giữ tính bất biến. Điểm cần chú ý là **tháng/năm có số ngày khác nhau**, phép điều chỉnh cuối tháng **có thể làm mất ngày neo**, thứ tự các phép biến đổi **quan trọng**, và `LocalDateTime` **không tự giải quyết múi giờ hoặc DST**.