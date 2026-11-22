# Tìm đầu tháng, cuối tháng và ngày trong tuần kế tiếp với TemporalAdjusters (Java 8+)

Trong ứng dụng quản lý lịch, kế toán và báo cáo, câu hỏi “ngày đầu tháng là ngày nào?”, “tháng này kết thúc ngày nào?” hoặc “thứ Hai tiếp theo rơi vào ngày nào?” xuất hiện thường xuyên. Thay vì tự tính số ngày trong tháng, viết phép cộng ngày thủ công hay dùng múi giờ mặc định của máy, Java cung cấp bộ API `java.time` rõ nghĩa, bất biến và tiếp tục được hỗ trợ ở các JDK hiện đại.

Bài này tập trung vào `TemporalAdjusters.firstDayOfMonth()`, `lastDayOfMonth()`, `firstDayOfNextMonth()`, `next(DayOfWeek)`, `nextOrSame(DayOfWeek)`, `firstInMonth`, `lastInMonth`, `dayOfWeekInMonth` cùng `YearMonth` và `Clock`. Điểm cốt lõi là phân biệt **ngày lịch**, **giờ địa phương** và **thời điểm thực (Instant)**, đồng thời xác định chính xác “kế tiếp” có bao gồm hôm nay hay không.

## 1. Chọn loại dữ liệu theo hợp đồng

| Nhu cầu | Kiểu Java | Lý do |
| --- | --- | --- |
| Một ngày trên lịch, không có giờ/zone | `LocalDate` | Thích hợp nhất để tìm đầu, cuối tháng và thứ trong tuần |
| Một kỳ tháng, ví dụ `2024-02` | `YearMonth` | Không cần đặt một ngày giả trong tháng |
| Thứ trong tuần | `DayOfWeek` | Enum `MONDAY` đến `SUNDAY` |
| Chiến lược điều chỉnh ngày | `TemporalAdjuster` | Được dùng qua `date.with(adjuster)` |
| Factory của các quy tắc điều chỉnh chuẩn | `TemporalAdjusters` | Có `firstDayOfMonth`, `next`, `lastInMonth`... |
| Hôm nay theo vùng và đồng hồ kiểm thử được | `Clock` + `LocalDate.now(clock)` | Không phụ thuộc timezone/ngày của máy CI |
| Ngày giờ chưa biết múi giờ | `LocalDateTime` | Chứa local date và local clock |
| Ngày giờ có vùng cụ thể | `ZonedDateTime` | Dùng quy tắc IANA/DST khi cần |
| Sự kiện đã xảy ra | `Instant` | Có một vị trí xác định trên timeline |

**`LocalDate` không phải một timestamp UTC.** Ngày 01/03 có thể bắt đầu tại các instant khác nhau giữa Việt Nam và Mỹ. Mọi phép “đầu tháng” và “thứ Hai” nên được xác định trước trên ngày lịch đúng vùng nghiệp vụ, chỉ chuyển sang `Instant` khi biết `ZoneId` và giờ cần dùng.

## 2. `TemporalAdjuster`, `TemporalAdjusters` và `with(...)`

`TemporalAdjuster` là interface đại diện cho một quy tắc điều chỉnh giá trị `Temporal`. Lớp `TemporalAdjusters` cung cấp các factory method `static` tạo những quy tắc ngày phổ biến. Cách áp dụng rõ ràng được API khuyến nghị là gọi `with(adjuster)` trên đối tượng cần điều chỉnh.

~~~java
import java.time.*;
import java.time.temporal.*;

LocalDate date = LocalDate.of(2024, 2, 15);

LocalDate first = date.with(TemporalAdjusters.firstDayOfMonth());
LocalDate last = date.with(TemporalAdjusters.lastDayOfMonth());
LocalDate nextMonday =
        date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
~~~

Kết quả lần lượt là `2024-02-01`, `2024-02-29` và `2024-02-19`. Vì `LocalDate` bất biến, `with(...)` **trả giá trị mới**, không sửa `date`. Nếu gọi `date.with(adjuster);` mà không gán kết quả, biến `date` vẫn giữ ngày cũ.

Một adjuster có thể tái sử dụng:

~~~java
TemporalAdjuster monthEnd = TemporalAdjusters.lastDayOfMonth();

LocalDate leap = LocalDate.of(2024, 2, 15).with(monthEnd);
LocalDate normal = LocalDate.of(2025, 2, 15).with(monthEnd);
// leap = 2024-02-29; normal = 2025-02-28.
~~~

`TemporalAdjusters` chuẩn có triển khai bất biến. Không dùng adjuster dựa trên trường `DAY_OF_MONTH` trực tiếp trên một `Instant` (không có trường ngày lịch): muốn lấy tháng từ một instant, phải chuyển nó sang `LocalDate` theo vùng múi giờ phù hợp.

## 3. Lấy ngày đầu tháng

Với một `LocalDate` bất kỳ:

~~~java
LocalDate base = LocalDate.of(2024, 2, 15);
LocalDate first = base.with(TemporalAdjusters.firstDayOfMonth());
// 2024-02-01.
~~~

Những cách diễn đạt khác vẫn đang được hỗ trợ:

~~~java
LocalDate byMethod = base.withDayOfMonth(1);
LocalDate byYearMonth = YearMonth.from(base).atDay(1);
~~~

Chúng đều mô tả ngày 1 của **tháng đang chứa ngày nguồn**, không phải tháng sau. Nếu ngày nguồn đã là ngày 1, kết quả có cùng giá trị; không cần nhảy sang tháng khác.

**Không dùng `base.plusMonths(1)` để tìm đầu tháng sau**: từ 15/02/2024 phép đó trả 15/03/2024; cần `firstDayOfNextMonth()` hoặc dịch `YearMonth` rồi `atDay(1)`.

## 4. Tìm ngày cuối tháng đúng cả năm nhuận

`TemporalAdjusters.lastDayOfMonth()` đặt ngày trong tháng thành ngày cuối hợp lệ. API dùng tháng/năm thật, nên tự xử lý 28, 29, 30 hoặc 31 ngày:

~~~java
LocalDate leap = LocalDate.of(2024, 2, 15)
        .with(TemporalAdjusters.lastDayOfMonth());
// 2024-02-29.

LocalDate common = LocalDate.of(2025, 2, 15)
        .with(TemporalAdjusters.lastDayOfMonth());
// 2025-02-28.
~~~

| Tháng | Ngày cuối |
| --- | --- |
| `2024-01` | `2024-01-31` |
| `2024-02` (nhuận) | `2024-02-29` |
| `2025-02` (thường) | `2025-02-28` |
| `2024-04` | `2024-04-30` |
| `2024-12` | `2024-12-31` |

Cách khác:

~~~java
LocalDate lastViaLength = base.withDayOfMonth(base.lengthOfMonth());
LocalDate lastViaMonth = YearMonth.from(base).atEndOfMonth();
~~~

Cả hai đều đúng khi đầu vào là `LocalDate` hợp lệ. `YearMonth.atEndOfMonth()` thường phù hợp nhất nếu nghiệp vụ là “ngày chốt kỳ tháng”, không gắn với một ngày cụ thể đầu vào.

Không tự tạo ngày `31` của mọi tháng: `LocalDate.of(2025,2,31)` ném `DateTimeException`. Nếu ngày dự kiến là một input chưa xác minh, có thể dùng `YearMonth.isValidDay(day)`.

## 5. Ngày đầu tháng tiếp theo

`firstDayOfNextMonth()` xử lý cả đổi năm:

~~~java
LocalDate base = LocalDate.of(2024, 2, 15);
LocalDate nextStart =
        base.with(TemporalAdjusters.firstDayOfNextMonth());
// 2024-03-01.

LocalDate december = LocalDate.of(2024, 12, 20);
LocalDate january = december.with(
        TemporalAdjusters.firstDayOfNextMonth());
// 2025-01-01.
~~~

Tương đương:

~~~java
YearMonth month = YearMonth.from(base);
LocalDate nextStart2 = month.plusMonths(1).atDay(1);
LocalDate nextStart3 = base.withDayOfMonth(1).plusMonths(1);
~~~

**Phân biệt:** `date.plusMonths(1)` thường giữ số ngày, còn `firstDayOfNextMonth()` luôn tìm ngày `1`. `LocalDate.of(2024,1,31).plusMonths(1)` cho `2024-02-29` vì ngày 31 không tồn tại trong tháng 2; `firstDayOfNextMonth()` từ cùng ngày là `2024-02-01`.

## 6. `YearMonth` giúp mô hình hóa kỳ tháng

`YearMonth` chứa năm và tháng, không chứa ngày, giờ hoặc zone. Khi record của bạn là kỳ báo cáo `2024-02`, dùng `YearMonth` thay vì `LocalDate` với ngày giả:

~~~java
YearMonth period = YearMonth.of(2024, 2);
LocalDate first = period.atDay(1);
LocalDate last = period.atEndOfMonth();
int days = period.lengthOfMonth();
YearMonth next = period.plusMonths(1);
// 2024-02-01, 2024-02-29, 29, 2024-03.
~~~

| API | Vai trò |
| --- | --- |
| `YearMonth.of(year,month)` | Tạo kỳ tháng |
| `YearMonth.from(localDate)` | Lấy năm/tháng từ ngày |
| `atDay(1)` | Ngày đầu tháng |
| `atEndOfMonth()` | Ngày cuối tháng |
| `lengthOfMonth()` | Số ngày thực của tháng |
| `isLeapYear()` | Kiểm tra năm nhuận ISO |
| `isValidDay(day)` | Xác thực ngày trong tháng |
| `plusMonths(n)` / `minusMonths(n)` | Dịch kỳ nguyên tháng |
| `YearMonth.now(clock)` | Lấy kỳ tháng từ đồng hồ chỉ định |

Quy tắc năm nhuận ISO/Gregorian: năm chia hết cho 4 thường là năm nhuận; năm tròn thế kỷ không chia hết cho 400 là ngoại lệ. Năm 2000 nhuận, 1900 không nhuận, 2024 nhuận, 2025 không nhuận. API có sẵn tính toán đúng mà không cần viết thuật toán năm nhuận riêng.

## 7. Thứ trong tuần **tiếp theo**: `next` so với `nextOrSame`

Giả sử đầu vào là **thứ Năm 15/02/2024**. Hai hợp đồng đều hợp lý nhưng khác nhau:

- `next(DayOfWeek.X)`: tìm lần xuất hiện đầu tiên của thứ X **sau ngày hiện tại**, không bao gồm hôm nay.
- `nextOrSame(DayOfWeek.X)`: nếu hôm nay chính là thứ X thì **giữ hôm nay**; nếu không, tìm lần xuất hiện kế tiếp.

~~~java
LocalDate base = LocalDate.of(2024, 2, 15); // THURSDAY.

LocalDate nextMon = base.with(
        TemporalAdjusters.next(DayOfWeek.MONDAY));
// 2024-02-19.

LocalDate nextThu = base.with(
        TemporalAdjusters.next(DayOfWeek.THURSDAY));
// 2024-02-22.

LocalDate nextOrSameThu = base.with(
        TemporalAdjusters.nextOrSame(DayOfWeek.THURSDAY));
// 2024-02-15.
~~~

| Ngày nguồn | Adjuster | Kết quả |
| --- | --- | --- |
| `2024-02-15` (THURSDAY) | `next(MONDAY)` | `2024-02-19` |
| `2024-02-15` | `next(FRIDAY)` | `2024-02-16` |
| `2024-02-15` | `next(THURSDAY)` | `2024-02-22` |
| `2024-02-15` | `nextOrSame(THURSDAY)` | `2024-02-15` |
| `2024-02-15` | `next(SUNDAY)` | `2024-02-18` |

Khi trùng ngày mục tiêu, `next` nhảy đúng **bảy ngày**. Kiểm chứng với thứ Sáu 06/11/2026:

~~~java
LocalDate friday = LocalDate.of(2026, 11, 6);

LocalDate strictNext = friday.with(
        TemporalAdjusters.next(DayOfWeek.FRIDAY));
// 2026-11-13.

LocalDate inclusive = friday.with(
        TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY));
// 2026-11-06.
~~~

"Cuộc hẹn thứ Sáu **tuần sau**" và "cuộc hẹn thứ Sáu **gần nhất, kể cả hôm nay**" không cùng một hợp đồng. Đừng dùng `nextOrSame` chỉ vì muốn code ngắn hơn; phải biết ngày hiện tại có hợp lệ cho nghiệp vụ hay không.

`DayOfWeek` dùng giá trị enum `MONDAY` đến `SUNDAY` theo ISO (thứ Hai = 1, Chủ nhật = 7). Không trộn với các hằng số số học của các thư viện lịch khác; dùng `DayOfWeek.MONDAY` để tự mô tả ý nghĩa.

## 8. Tìm thứ trước: `previous` và `previousOrSame`

Có hai quy tắc đối xứng:

~~~java
LocalDate base = LocalDate.of(2024, 2, 15); // THURSDAY.

LocalDate previous = base.with(
        TemporalAdjusters.previous(DayOfWeek.THURSDAY));
// 2024-02-08.

LocalDate previousOrSame = base.with(
        TemporalAdjusters.previousOrSame(DayOfWeek.THURSDAY));
// 2024-02-15.
~~~

| API | Trường hợp ngày nguồn đã trùng thứ mục tiêu |
| --- | --- |
| `next(DOW)` | Tìm ngày sau, +7 ngày |
| `nextOrSame(DOW)` | Giữ ngày hiện tại |
| `previous(DOW)` | Tìm ngày trước, -7 ngày |
| `previousOrSame(DOW)` | Giữ ngày hiện tại |

Để tìm **ngày thứ Hai bắt đầu tuần ISO** chứa một ngày, `date.with(previousOrSame(MONDAY))` thường đúng. Nhưng nếu hệ thống có tuần bắt đầu Chủ nhật hoặc quy tắc tính tuần theo địa phương, phải chọn chính sách qua `WeekFields` thay vì áp đặt mọi trường hợp luôn bắt đầu thứ Hai.

## 9. Thứ đầu, cuối và lần xuất hiện thứ n **trong tháng**

`TemporalAdjusters` cho các quy tắc tính theo tháng:

~~~java
LocalDate date = LocalDate.of(2024, 2, 15);

LocalDate firstMonday = date.with(
        TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
// 2024-02-05.

LocalDate lastFriday = date.with(
        TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY));
// 2024-02-23.

LocalDate secondFriday = date.with(
        TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.FRIDAY));
// 2024-02-09.
~~~

| Quy tắc | Kết quả trong tháng 02/2024 |
| --- | --- |
| `firstInMonth(MONDAY)` | `2024-02-05` |
| `lastInMonth(FRIDAY)` | `2024-02-23` |
| `dayOfWeekInMonth(2,FRIDAY)` | `2024-02-09` |
| `dayOfWeekInMonth(-1,FRIDAY)` | `2024-02-23` |
| `dayOfWeekInMonth(-2,FRIDAY)` | `2024-02-16` |

**Thứ Sáu xuất hiện lần thứ hai** trong tháng khác với **thứ Sáu thuộc tuần lịch số hai**. Số tuần có thể phụ thuộc cách định nghĩa tuần bắt đầu thứ Hai hay Chủ nhật, còn `dayOfWeekInMonth(2,FRIDAY)` luôn đếm occurrence của FRIDAY từ đầu tháng.

### Ordinal có thể vượt ranh giới tháng

`TemporalAdjusters.dayOfWeekInMonth` xử lý ordinal một cách **linh hoạt (lenient)**. Nó không bảo đảm kết quả luôn thuộc tháng gốc nếu truyền occurrence không tồn tại:

~~~java
LocalDate feb = LocalDate.of(2024, 2, 15);
LocalDate fifthFriday = feb.with(
        TemporalAdjusters.dayOfWeekInMonth(5, DayOfWeek.FRIDAY));
// 2024-03-01, không còn trong tháng 2.
~~~

Tháng 02/2024 chỉ có các thứ Sáu 02/02, 09/02, 16/02, 23/02. Lần thứ năm rơi vào 01/03. API không ném exception để bảo vệ yêu cầu "phải nằm trong tháng"; bạn phải kiểm tra:

~~~java
YearMonth period = YearMonth.from(feb);
boolean validOccurrence = YearMonth.from(fifthFriday).equals(period);
// false.
~~~

Ordinal `0` còn có thể chọn lần cuối của tháng trước theo định nghĩa lenient; ordinal âm đếm ngược từ cuối tháng. Nếu domain chỉ cho phép lần 1–4/5 thuộc tháng, validate trước và kiểm tra `YearMonth` của kết quả.

## 10. Ghép các adjuster có thứ tự rõ ràng

Yêu cầu "thứ Hai **đầu tiên của tháng sau**" khác "thứ Hai **kế tiếp sau hôm nay**":

~~~java
LocalDate base = LocalDate.of(2024, 2, 15);

LocalDate nextMonday = base.with(
        TemporalAdjusters.next(DayOfWeek.MONDAY));
// 2024-02-19.

LocalDate firstMondayNextMonth = base
        .with(TemporalAdjusters.firstDayOfNextMonth())
        .with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
// 2024-03-04.
~~~

Có thể bắt đầu từ `YearMonth`:

~~~java
YearMonth month = YearMonth.of(2024, 2).plusMonths(1);

LocalDate firstMonday = month.atDay(1).with(
        TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
// 2024-03-04.

LocalDate lastFriday = month.atEndOfMonth().with(
        TemporalAdjusters.previousOrSame(DayOfWeek.FRIDAY));
// 2024-03-29.
~~~

Tại đây `previousOrSame(FRIDAY)` được áp dụng trên **ngày cuối tháng**, nên tìm thứ Sáu cuối cùng cùng tháng. Việc ghép quy tắc theo từng bước có tên rõ giúp code review tránh hiểu nhầm giữa kỳ hiện tại/kỳ sau.

### Lịch "cuối tháng" lặp lại qua tháng 2

Nếu hợp đồng nói "hạn là ngày cuối của từng tháng", lấy mỗi kỳ từ `YearMonth`:

~~~java
YearMonth anchor = YearMonth.of(2024, 1);

LocalDate jan = anchor.atEndOfMonth(); // 2024-01-31.
LocalDate feb = anchor.plusMonths(1).atEndOfMonth(); // 2024-02-29.
LocalDate mar = anchor.plusMonths(2).atEndOfMonth(); // 2024-03-31.
~~~

Không tính kỳ kế bằng cách lấy **ngày hạn trước** và cộng `plusMonths(1)` lặp lại:

~~~java
LocalDate drift = LocalDate.of(2024, 1, 31)
        .plusMonths(1)
        .plusMonths(1);
// 2024-03-29, không phải cuối tháng 3.
~~~

Ngày 31/01 được điều chỉnh thành 29/02 (tháng 2 nhuận), sau đó ngày 29 tiếp tục sang 29/03. Đây là hành vi hợp lệ của `plusMonths` nhưng không phù hợp hợp đồng **luôn cuối tháng**. Nên giữ quy tắc neo vào kỳ năm–tháng gốc.

## 11. `Clock`: "hôm nay" của vùng nào?

Một `TemporalAdjuster` không tự đọc đồng hồ. Nếu yêu cầu là **thứ Hai tiếp theo kể từ hôm nay**, trước hết tính hôm nay theo zone của người dùng/chi nhánh:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock clock = Clock.systemUTC();

LocalDate today = LocalDate.now(clock.withZone(zone));
LocalDate nextMonday = today.with(
        TemporalAdjusters.next(DayOfWeek.MONDAY));
YearMonth currentMonth = YearMonth.from(today);
~~~

`Clock.systemUTC()` lấy instant từ đồng hồ hệ thống. `clock.withZone(zone)` cung cấp góc nhìn ngày/giờ theo zone cụ thể; `LocalDate.now(clock)` tính ngày lịch theo zone của clock. Không mặc định `LocalDate.now()` dùng timezone đúng của người dùng: overload không tham số phụ thuộc timezone JVM.

### Test bằng `Clock.fixed`

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-06T00:30:00Z"),
        ZoneOffset.UTC);

LocalDate inVietnam = LocalDate.now(
        fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh")));
// 2026-11-06.

LocalDate inNewYork = LocalDate.now(
        fixed.withZone(ZoneId.of("America/New_York")));
// 2026-11-05.
~~~

Cùng một `Instant` nhưng hai vùng có thể là **hai ngày khác nhau**. Với kỳ báo cáo gần ranh giới ngày/tháng, nếu backend và frontend chọn zone khác nhau thì logic "tháng này" có thể lệch kỳ. Truyền `Clock` qua constructor/dependency injection giúp kiểm thử tất định; ở production dùng clock hệ thống, còn test dùng `Clock.fixed(...)`.

## 12. "Ngày làm việc kế tiếp" khác "thứ Hai kế tiếp"

`next(MONDAY)` chỉ tìm **thứ Hai** tiếp theo. Nó không tìm **ngày làm việc kế tiếp** từ một ngày bất kỳ. Ví dụ nếu hôm nay thứ Ba, ngày làm việc kế tiếp theo lịch nghỉ thứ Bảy/Chủ nhật là thứ Tư, còn `next(MONDAY)` nhảy sang tuần sau.

Một hàm đơn giản khi **chỉ nghỉ cuối tuần**:

~~~java
static LocalDate nextBusinessWeekday(LocalDate date) {
    LocalDate candidate = date.plusDays(1);
    while (candidate.getDayOfWeek() == DayOfWeek.SATURDAY
            || candidate.getDayOfWeek() == DayOfWeek.SUNDAY) {
        candidate = candidate.plusDays(1);
    }
    return candidate;
}
~~~

Với thứ Sáu `2026-11-06`, kết quả là thứ Hai `2026-11-09`. Với Chủ nhật `2026-11-08` cũng ra `2026-11-09`.

Nếu muốn tái sử dụng như một `TemporalAdjuster`, Java có `TemporalAdjusters.ofDateAdjuster(...)`:

~~~java
TemporalAdjuster nextBusinessDay = TemporalAdjusters.ofDateAdjuster(
        day -> {
            LocalDate result = day.plusDays(1);
            while (result.getDayOfWeek() == DayOfWeek.SATURDAY
                    || result.getDayOfWeek() == DayOfWeek.SUNDAY) {
                result = result.plusDays(1);
            }
            return result;
        });

LocalDate next = LocalDate.of(2026, 11, 6).with(nextBusinessDay);
// 2026-11-09.
~~~

**Đây chưa phải business-calendar đầy đủ.** Ngày lễ quốc gia, ngày nghỉ bù, lịch ngân hàng, giờ cắt lệnh hoặc chế độ làm việc từng cơ sở là dữ liệu nghiệp vụ riêng. Nếu có các yêu cầu đó, hãy đưa lịch nghỉ vào một service hoặc tập dữ liệu được quản lý, không coi mọi thứ Hai–Sáu đều làm việc.

## 13. Đầu tháng/đầu ngày và truy vấn khoảng thời gian nửa mở

Một `LocalDate` là **ngày lịch** chứ không phải mốc thời gian thực. Đối với một bảng lưu `Instant` hoặc timestamp của event, trước khi lọc dữ liệu theo kỳ tháng của chi nhánh cần chọn `ZoneId`, rồi chuyển **hai ranh giới** sang `Instant`.

~~~java
YearMonth reportMonth = YearMonth.of(2024, 2);
LocalDate fromDate = reportMonth.atDay(1);
LocalDate toDateExclusive = reportMonth.plusMonths(1).atDay(1);
// fromDate = 2024-02-01.
// toDateExclusive = 2024-03-01.
~~~

Khoảng ngày nửa mở `[fromDate, toDateExclusive)` lấy trọn tháng 2, kể cả 29/02, nhưng không lấy 01/03. Khác với việc dựng mốc 23:59:59 cuối tháng, nửa mở không phụ thuộc độ phân giải nano/micro/millisecond của database.

Với event đã được lưu dưới dạng instant:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = fromDate.atStartOfDay(businessZone).toInstant();
Instant to = toDateExclusive.atStartOfDay(businessZone).toInstant();
~~~

Bộ lọc SQL tương ứng:

~~~sql
SELECT event_id, occurred_at
FROM event_log
WHERE occurred_at >= :from_inclusive
  AND occurred_at < :to_exclusive
ORDER BY occurred_at, event_id;
~~~

Hãy bind `from` và `to` vào kiểu timestamp phù hợp với **driver/database thực tế**. Nếu cột là SQL `DATE` mang đúng nghĩa ngày lịch thì dùng hai ngày typed, không cần ép sang UTC.

**Vì sao không cộng số ngày × 24 giờ để suy đầu tháng sau?** Ở vùng có DST, một ngày địa phương có thể chỉ chứa 23 giờ hoặc dài 25 giờ. Ví dụ tại New York:

~~~java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime start = LocalDate.of(2024, 3, 10)
        .atStartOfDay(ny);
ZonedDateTime end = LocalDate.of(2024, 3, 11)
        .atStartOfDay(ny);

long hours = Duration.between(
        start.toInstant(), end.toInstant()).toHours();
// 23 giờ thực.
~~~

Một kỳ tháng tại New York đi qua bước đổi DST cũng có tổng số giờ thực khác phép cộng `daysInMonth * 24`. Tính ranh giới từ hai `LocalDate.atStartOfDay(zone)` để phản ánh đúng lịch địa phương.

**`atStartOfDay(zone)` không luôn biểu thị 00:00 trên đồng hồ.** Với một số vùng/ngày lịch sử có transition ngay gần nửa đêm, API chọn **thời điểm hợp lệ sớm nhất** của ngày. Điều này hữu ích để xây dựng khoảng dữ liệu theo local date mà không tự đoán offset.

## 14. Dùng adjuster trên `LocalDateTime` và `ZonedDateTime`

Các thao tác điều chỉnh ngày không nhất thiết làm mất giờ đang có:

~~~java
LocalDateTime meeting = LocalDateTime.of(2024, 2, 15, 9, 30);

LocalDateTime atMonthStart = meeting.with(
        TemporalAdjusters.firstDayOfMonth());
// 2024-02-01T09:30.

LocalDateTime nextMonday = meeting.with(
        TemporalAdjusters.next(DayOfWeek.MONDAY));
// 2024-02-19T09:30.
~~~

`LocalDateTime` không mang offset và cũng không phải `Instant`. Các kết quả này mới là **ngày/giờ theo đồng hồ địa phương**, chưa xác định được sự kiện toàn cầu. Với lịch hẹn thực, cần kết hợp một `ZoneId` và kiểm tra giờ DST.

`ZonedDateTime.with(adjuster)` có thể điều chỉnh trên local timeline, sau đó áp quy tắc múi giờ vùng. Đừng giả định mọi ngày/giờ địa phương đều có đúng một offset.

### Gap của DST: giờ không tồn tại

New York ngày 10/03/2024 nhảy từ khoảng 02:00 lên 03:00. Do đó **02:30 không tồn tại**:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDate.of(2024, 3, 10).atTime(2, 30);

List<ZoneOffset> choices = ny.getRules().getValidOffsets(local);
// [] — không có offset hợp lệ.

ZonedDateTime adjusted = local.atZone(ny);
// 2024-03-10T03:30-04:00[America/New_York].
~~~

`atZone` có chính sách mặc định **dịch giờ tiến lên** qua gap. Trong ứng dụng đặt lịch cần đúng giờ khách chọn, điều này có thể không phù hợp: nên kiểm tra `getValidOffsets`, từ chối giờ không tồn tại hoặc yêu cầu lựa chọn rõ.

Trong **overlap** mùa thu, local time có thể có **hai offset hợp lệ**; phải có chính sách chọn lượt trước/lượt sau nếu cần một instant duy nhất. Không dùng riêng `LocalDateTime` làm khóa duy nhất cho sự kiện khi vùng có DST overlap.

Với bài toán chỉ cần **ngày trong tuần**, nên tính trước bằng `LocalDate` rồi kết hợp `LocalTime`/`ZoneId` theo quy định nghiệp vụ; điều này dễ test hơn việc điều chỉnh instant không biết vùng.

## 15. Đầu tuần theo ISO và theo locale

`DayOfWeek.MONDAY`, `TUESDAY`... là các thứ trong tuần theo ISO. Tuy vậy, cụm "đầu tuần" là một **quy tắc hiển thị và nghiệp vụ**, không cố định giống nhau ở mọi địa phương.

Với lịch tuần ISO bắt đầu thứ Hai:

~~~java
LocalDate date = LocalDate.of(2024, 2, 15);
LocalDate isoWeekStart = date.with(
        TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
// 2024-02-12.
~~~

`WeekFields.ISO` xác định tuần bắt đầu vào MONDAY và quy tắc số ngày tối thiểu của tuần đầu tiên. Với sản phẩm theo địa phương, có `WeekFields.of(locale)` để lấy `getFirstDayOfWeek()`; không lấy locale mặc định của server nếu hợp đồng của người dùng đã có một locale cụ thể.

Không nhầm:

- **`dayOfWeekInMonth(2,FRIDAY)`:** thứ Sáu **xuất hiện lần thứ 2** tính từ đầu tháng.
- **Week of month** theo `WeekFields`: một số tuần theo quy tắc tuần bắt đầu và số ngày tối thiểu. Thứ Sáu xuất hiện lần thứ 2 không nhất thiết thuộc tuần được đánh số 2 ở mọi locale.

Nếu bài toán là lịch theo tuần ISO, dùng quy tắc ISO có chủ đích. Nếu bài toán là tuần bắt đầu Chủ nhật, phải nêu rõ và thay `previousOrSame` bằng thứ phù hợp.

## 16. Chọn API ngắn gọn theo bài toán

| Ý định chính | API nên chọn | Lưu ý |
| --- | --- | --- |
| Đầu tháng từ một ngày | `date.with(firstDayOfMonth())` hoặc `withDayOfMonth(1)` | Giữ tháng hiện tại |
| Cuối tháng từ một ngày | `date.with(lastDayOfMonth())` | Tự xử lý năm nhuận |
| Đầu và cuối kỳ `YearMonth` | `atDay(1)` / `atEndOfMonth()` | Không cần ngày giả |
| Đầu tháng sau | `firstDayOfNextMonth()` | Không dùng `date.plusMonths(1)` |
| Thứ sau hôm nay | `next(DOW)` | Bắt buộc sau, không bao gồm hôm nay |
| Thứ hôm nay hoặc sau | `nextOrSame(DOW)` | Có thể trả hôm nay |
| Thứ trước hôm nay | `previous(DOW)` | Không bao gồm hôm nay |
| Thứ trước hoặc hôm nay | `previousOrSame(DOW)` | Có thể trả hôm nay |
| Thứ Hai đầu tháng | `firstInMonth(MONDAY)` | Một occurrence trong tháng |
| Thứ Sáu cuối tháng | `lastInMonth(FRIDAY)` | Khác thứ Sáu kế tiếp |
| Thứ Sáu xuất hiện lần thứ n | `dayOfWeekInMonth(n,FRIDAY)` | Kiểm tra có vượt tháng không |
| Ngày làm việc kế tiếp | Lịch ngày nghỉ + custom adjuster | `next(MONDAY)` không đủ |
| Hôm nay của chi nhánh | `LocalDate.now(clock.withZone(zone))` | Không dùng timezone máy chủ |
| Lọc event cả tháng | Hai `LocalDate` đầu kỳ và đầu kỳ sau | Khoảng nửa mở, chuyển qua `Instant` với ZoneId |

## 17. Chương trình Java hoàn chỉnh, đã biên dịch và chạy

Tạo file **`MonthWeekAdjustersDemo.java`**. Chương trình dùng toàn API có từ Java 8, biên dịch trên JDK 17+ và không cần thư viện ngoài. Mọi ngày và đồng hồ đều được cố định, không phụ thuộc timezone hoặc ngày hiện tại của máy. Mã trình bày đầu/cuối tháng, năm nhuận, các biến thể `next`/`previous`, thứ trong tháng, `Clock.fixed`, ngày làm việc kế tiếp và giới hạn DST; phần cuối có **9 phép kiểm tra bất biến**.

~~~java
import java.time.*;
import java.time.temporal.*;
import java.util.*;

public class MonthWeekAdjustersDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static LocalDate nextBusinessWeekday(LocalDate date) {
        LocalDate candidate = date.plusDays(1);
        while (candidate.getDayOfWeek() == DayOfWeek.SATURDAY ||
               candidate.getDayOfWeek() == DayOfWeek.SUNDAY) {
            candidate = candidate.plusDays(1);
        }
        return candidate;
    }

    public static void main(String[] args) {
        LocalDate source = LocalDate.of(2024, 2, 15);
        YearMonth month = YearMonth.from(source);
        LocalDate first = source.with(TemporalAdjusters.firstDayOfMonth());
        LocalDate last = source.with(TemporalAdjusters.lastDayOfMonth());
        LocalDate firstNext = source.with(
                TemporalAdjusters.firstDayOfNextMonth());
        System.out.println("source: " + source + " (" + source.getDayOfWeek() + ")");
        System.out.println("month start: " + first);
        System.out.println("month end: " + last);
        System.out.println("next month start: " + firstNext);
        System.out.println("YearMonth first: " + month.atDay(1));
        System.out.println("YearMonth last: " + month.atEndOfMonth());
        System.out.println("days in February 2024: " + month.lengthOfMonth());
        System.out.println("days in February 2025: " +
                YearMonth.of(2025, 2).lengthOfMonth());
        System.out.println("next Monday: " +
                source.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("next Thursday: " +
                source.with(TemporalAdjusters.next(DayOfWeek.THURSDAY)));
        System.out.println("next-or-same Thursday: " +
                source.with(TemporalAdjusters.nextOrSame(DayOfWeek.THURSDAY)));
        System.out.println("previous Thursday: " +
                source.with(TemporalAdjusters.previous(DayOfWeek.THURSDAY)));
        System.out.println("previous-or-same Thursday: " +
                source.with(TemporalAdjusters.previousOrSame(DayOfWeek.THURSDAY)));
        System.out.println("first Monday in month: " +
                source.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY)));
        System.out.println("last Friday in month: " +
                source.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY)));
        System.out.println("second Friday in month: " +
                source.with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.FRIDAY)));
        System.out.println("month contains source: " +
                (!source.isBefore(first) && source.isBefore(firstNext)));

        LocalDateTime meeting = source.atTime(9, 30);
        System.out.println("meeting month start: " +
                meeting.with(TemporalAdjusters.firstDayOfMonth()));
        System.out.println("meeting next Monday: " +
                meeting.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));

        LocalDate friday = LocalDate.of(2026, 11, 6);
        System.out.println("Friday strict next: " +
                friday.with(TemporalAdjusters.next(DayOfWeek.FRIDAY)));
        System.out.println("Friday next-or-same: " +
                friday.with(TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY)));
        System.out.println("next weekday after Friday: " +
                nextBusinessWeekday(friday));
        System.out.println("next weekday after Sunday: " +
                nextBusinessWeekday(friday.plusDays(2)));

        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-06T00:30:00Z"), ZoneOffset.UTC);
        ZoneId vn = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId ny = ZoneId.of("America/New_York");
        System.out.println("fixed date in Vietnam: " +
                LocalDate.now(fixed.withZone(vn)));
        System.out.println("fixed date in New York: " +
                LocalDate.now(fixed.withZone(ny)));

        LocalDate dst = LocalDate.of(2024, 3, 10);
        ZonedDateTime dstStart = dst.atStartOfDay(ny);
        ZonedDateTime dstEnd = dst.plusDays(1).atStartOfDay(ny);
        System.out.println("NY DST day start: " + dstStart);
        System.out.println("NY DST next day start: " + dstEnd);
        System.out.println("NY DST day elapsed hours: " +
                Duration.between(dstStart.toInstant(), dstEnd.toInstant()).toHours());
        LocalDateTime invalidMeeting = dst.atTime(2, 30);
        System.out.println("NY invalid local offsets: " +
                ny.getRules().getValidOffsets(invalidMeeting));
        System.out.println("NY default meeting resolution: " +
                invalidMeeting.atZone(ny));

        check(first.equals(month.atDay(1)), "month start mismatch");
        check(last.equals(month.atEndOfMonth()), "month end mismatch");
        check(last.plusDays(1).equals(firstNext), "exclusive bound mismatch");
        check(source.with(TemporalAdjusters.next(DayOfWeek.THURSDAY))
                .equals(source.plusWeeks(1)), "strict next mismatch");
        check(source.with(TemporalAdjusters.nextOrSame(DayOfWeek.THURSDAY))
                .equals(source), "inclusive next mismatch");
        check(nextBusinessWeekday(friday).equals(LocalDate.of(2026, 11, 9)),
                "weekday policy");
        check(!source.isBefore(first) && source.isBefore(firstNext), "range");
        check(Duration.between(dstStart.toInstant(), dstEnd.toInstant())
                .equals(Duration.ofHours(23)), "DST month-day check");
        check(ny.getRules().getValidOffsets(invalidMeeting).isEmpty(),
                "DST gap must be empty");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 MonthWeekAdjustersDemo.java
java MonthWeekAdjustersDemo
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
source: 2024-02-15 (THURSDAY)
month start: 2024-02-01
month end: 2024-02-29
next month start: 2024-03-01
YearMonth first: 2024-02-01
YearMonth last: 2024-02-29
days in February 2024: 29
days in February 2025: 28
next Monday: 2024-02-19
next Thursday: 2024-02-22
next-or-same Thursday: 2024-02-15
previous Thursday: 2024-02-08
previous-or-same Thursday: 2024-02-15
first Monday in month: 2024-02-05
last Friday in month: 2024-02-23
second Friday in month: 2024-02-09
month contains source: true
meeting month start: 2024-02-01T09:30
meeting next Monday: 2024-02-19T09:30
Friday strict next: 2026-11-13
Friday next-or-same: 2026-11-06
next weekday after Friday: 2026-11-09
next weekday after Sunday: 2026-11-09
fixed date in Vietnam: 2026-11-06
fixed date in New York: 2026-11-05
NY DST day start: 2024-03-10T00:00-05:00[America/New_York]
NY DST next day start: 2024-03-11T00:00-04:00[America/New_York]
NY DST day elapsed hours: 23
NY invalid local offsets: []
NY default meeting resolution: 2024-03-10T03:30-04:00[America/New_York]
all checks passed
~~~

Giải thích các ý quan trọng trong output:

1. `firstDayOfMonth()` và `YearMonth.atDay(1)` đều cho 01/02; `lastDayOfMonth()` và `YearMonth.atEndOfMonth()` đều cho 29/02 vì năm 2024 nhuận.
2. `next(THURSDAY)` trả 22/02, trong khi `nextOrSame(THURSDAY)` trả 15/02 do được phép chọn hôm nay.
3. `lastInMonth(FRIDAY)` trả 23/02 và `dayOfWeekInMonth(2, FRIDAY)` trả 09/02, là **hai yêu cầu khác nhau**.
4. `LocalDateTime.with(adjuster)` điều chỉnh ngày nhưng giữ `09:30` vì không có zone ở bước đó.
5. Thứ Sáu 06/11/2026: `next(FRIDAY)` là 13/11, còn "ngày làm việc kế tiếp" theo quy tắc cuối tuần là 09/11.
6. Cùng `Clock.fixed` nhưng một ngày ở Việt Nam và New York có thể khác nhau, minh họa vì sao không phụ thuộc timezone máy chủ.
7. Ngày 10/03/2024 ở New York có **23 giờ thực** giữa hai ranh giới đầu ngày.
8. Local time `02:30` trong DST gap có danh sách offset rỗng; resolver mặc định đưa nó sang `03:30`.
9. Dòng `all checks passed` chỉ được in sau khi cả **9 assertion** đã thành công.

## 18. Lỗi phổ biến khi tìm ranh giới tháng và ngày trong tuần

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giả định tháng nào cũng 30 hoặc 31 ngày | Sai tháng 2 và các tháng có 30 ngày | `YearMonth.lengthOfMonth()` / `atEndOfMonth()` |
| Mặc định tháng 2 luôn kết thúc ngày 28 | Sai năm nhuận | `lastDayOfMonth()` |
| Tự tạo ngày 31/02 để "lấy cuối tháng" | `DateTimeException` | `YearMonth.atEndOfMonth()` |
| Dùng `date.plusMonths(1)` để tìm ngày 1 tháng sau | Thường vẫn giữ ngày giữa tháng | `firstDayOfNextMonth()` |
| Dùng `next(MONDAY)` khi muốn chấp nhận thứ Hai hôm nay | Nhảy sang tuần sau | `nextOrSame(MONDAY)` |
| Dùng `nextOrSame` khi yêu cầu bắt buộc sau hôm nay | Có thể chọn chính hôm nay | `next` |
| Gọi `previous(MONDAY)` để lấy đầu tuần khi ngày là thứ Hai | Lùi bảy ngày ngoài ý muốn | `previousOrSame(MONDAY)` nếu tuần bắt đầu thứ Hai |
| Nhầm `next(FRIDAY)` và `lastInMonth(FRIDAY)` | Tìm thứ Sáu gần nhất, không phải cuối tháng | `lastInMonth` |
| Cho rằng `dayOfWeekInMonth(5,FRIDAY)` chắc trong tháng | Có thể rơi sang tháng sau | Kiểm tra `YearMonth.from(result)` |
| Nhầm "thứ Sáu thứ 2" với "thứ Sáu trong tuần lịch số 2" | Sai theo locale/định nghĩa tuần | Phân biệt occurrence và `WeekFields` |
| Gọi `date.with(adjuster)` rồi bỏ kết quả | Đối tượng ban đầu không đổi | Lưu giá trị trả về |
| Dùng `LocalDate.now()` cho lịch của mọi người dùng | Phụ thuộc default timezone JVM | `LocalDate.now(clock.withZone(userZone))` |
| Đưa trực tiếp `Instant` vào adjuster theo ngày | `Instant` thiếu trường lịch | Xác định zone rồi tạo `LocalDate` |
| Sử dụng ngày cuối tháng lúc `23:59:59` để lọc log | Có thể mất event cuối ngày hoặc sai precision | Khoảng nửa mở `[start,nextStart)` |
| Cộng `daysInMonth*24` giờ để suy đầu tháng tiếp | Sai qua DST | Tính hai ngày đầu tháng theo `ZoneId` |
| Nhầm `LocalDateTime` với instant toàn cầu | Thiếu offset/zone | Resolve với vùng cụ thể và policy DST |
| Áp dụng adjuster lên lịch có DST rồi bỏ qua gap | Một local time có thể bị dịch sang giờ khác | `getValidOffsets` và validation |
| Coi thứ Hai kế tiếp là ngày làm việc kế tiếp | Bỏ qua các ngày làm việc xen giữa | Business calendar riêng |
| Chỉ loại thứ Bảy/Chủ nhật trong lịch tài chính | Không xử lý ngày lễ/ngày bù | Nguồn holiday calendar có thẩm quyền |
| Cộng `plusMonths(1)` lặp từ ngày hạn cuối tháng trước | Có thể trôi ngày 31 → 29 | `YearMonth.plusMonths(n).atEndOfMonth()` |
| Dùng chuỗi display `dd/MM/yyyy` để so thứ tự ngày | Dễ sai do locale/format | Parse `LocalDate` ISO, so bằng API typed |
| Test phụ thuộc ngày thật trên máy CI | Flaky ở ranh giới ngày/tháng | `Clock.fixed` và zone explicit |

## 19. Bài tập có lời giải

### Bài 1 — Tháng 2 của năm thường và năm nhuận

Từ `2024-02-15` và `2025-02-15`, tìm hai ngày cuối tháng.

**Đáp án:**

~~~java
LocalDate end2024 = LocalDate.of(2024, 2, 15)
        .with(TemporalAdjusters.lastDayOfMonth());
LocalDate end2025 = LocalDate.of(2025, 2, 15)
        .with(TemporalAdjusters.lastDayOfMonth());
// 2024-02-29; 2025-02-28.
~~~

### Bài 2 — Đầu tháng sau khác cộng một tháng

Từ `2024-12-20`, `firstDayOfNextMonth()` trả gì?

**Đáp án:** `2025-01-01`. Còn `plusMonths(1)` trả `2025-01-20`, không phải đầu kỳ.

### Bài 3 — "Thứ Năm tiếp theo" khi hôm nay là thứ Năm

Ngày nguồn là `2024-02-15`. Dùng `next(THURSDAY)` và `nextOrSame(THURSDAY)` có gì khác?

**Đáp án:** `2024-02-22` so với `2024-02-15`. Một hàm loại hôm nay, một hàm bao gồm hôm nay.

### Bài 4 — Thứ Hai đầu tháng 3

Từ `2024-02-15`, tìm thứ Hai đầu tiên **của tháng sau**.

**Đáp án:**

~~~java
LocalDate answer = LocalDate.of(2024, 2, 15)
        .with(TemporalAdjusters.firstDayOfNextMonth())
        .with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
// 2024-03-04.
~~~

Không dùng riêng `next(MONDAY)` vì nó trả 19/02, vẫn thuộc tháng 2.

### Bài 5 — Thứ Sáu cuối tháng

Từ một ngày bất kỳ trong tháng 02/2024, tìm thứ Sáu cuối cùng.

**Đáp án:** `with(TemporalAdjusters.lastInMonth(FRIDAY))` → `2024-02-23`. Có thể lấy `YearMonth.of(2024,2).atEndOfMonth()` rồi `previousOrSame(FRIDAY)`.

### Bài 6 — Thứ Sáu thứ năm không tồn tại trong tháng 2

`dayOfWeekInMonth(5,FRIDAY)` trên tháng 02/2024 cho gì?

**Đáp án:** `2024-03-01`, vì tháng 2 chỉ có bốn thứ Sáu. Kết quả có thể vượt tháng do cách xử lý lenient. Kiểm tra `YearMonth.from(result)` trước khi ghi lịch của kỳ.

### Bài 7 — Ngày làm việc sau thứ Sáu

Thứ Sáu `2026-11-06`, lịch đơn giản nghỉ thứ Bảy/Chủ nhật. Ngày làm việc tiếp theo?

**Đáp án:** Thứ Hai `2026-11-09`. Với ngân hàng hoặc lịch có ngày lễ, cần kiểm tra holiday calendar; `next(MONDAY)` không thay thế logic next business day cho mọi ngày nguồn.

### Bài 8 — Hai ngày khác nhau từ một clock

Với `Clock.fixed(2026-11-06T00:30Z)`, vì sao Việt Nam là ngày 06/11 còn New York là 05/11?

**Đáp án:** Hai vùng có offset khác nhau tại cùng instant; `LocalDate.now(clock.withZone(zone))` tính ngày lịch theo vùng tương ứng. Dùng zone nghiệp vụ khi tìm "tháng này" để tránh sai ranh giới.

### Bài 9 — Lọc toàn bộ tháng 2 không mất ngày 29

Dữ liệu event lưu theo `Instant`. Cần lọc tháng 02/2024 theo giờ Việt Nam. Tạo ranh giới thế nào?

**Đáp án:** Dùng `YearMonth.of(2024,2).atDay(1)` và `YearMonth.of(2024,2).plusMonths(1).atDay(1)`, rồi chuyển cả hai bằng `atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh")).toInstant()`. Truy vấn `>= from AND < to`.

### Bài 10 — Lịch cuối tháng không bị trôi ngày

Từ tháng 1/2024, cần ngày cuối ba tháng 1, 2 và 3. Có nên lấy kết quả tháng trước rồi cộng tháng không?

**Đáp án:** Nên lấy `YearMonth.of(2024,1).plusMonths(n).atEndOfMonth()` để lần lượt được 31/01, 29/02, 31/03. Cộng trực tiếp từ ngày 31/01 qua 29/02 rồi sang 29/03 sẽ không còn là ngày cuối tháng 3.

### Bài 11 — DST và lịch hẹn

Người dùng chọn ngày `2024-03-10`, giờ `02:30` tại New York. Có thể tự chốt instant mà không hỏi gì thêm không?

**Đáp án:** Giờ này nằm trong DST gap, `getValidOffsets(local)` rỗng. `atZone` mặc định có thể điều chỉnh thành 03:30; nếu nghiệp vụ yêu cầu giờ chính xác, cần từ chối hoặc áp dụng chính sách đã công bố.

## 20. Checklist khi đưa vào production

- [ ] Đã phân biệt `LocalDate`, `YearMonth` và `Instant` đúng ý nghĩa?
- [ ] Đầu tháng dùng `firstDayOfMonth` hoặc `atDay(1)`?
- [ ] Cuối tháng dùng `lastDayOfMonth` hoặc `atEndOfMonth`, không hardcode ngày 28/30/31?
- [ ] Đã test năm nhuận, tháng 2 và tháng 12 sang tháng 1?
- [ ] `firstDayOfNextMonth` có được dùng thay vì `date.plusMonths(1)` khi muốn đầu kỳ?
- [ ] `next` hay `nextOrSame` phù hợp việc bao gồm hôm nay?
- [ ] `previous` và `previousOrSame` có xử lý đúng khi ngày đầu vào trùng thứ mục tiêu?
- [ ] Khi tính thứ Sáu cuối tháng, đã dùng `lastInMonth` thay vì `next`?
- [ ] Khi yêu cầu occurrence thứ n, đã xác nhận kết quả vẫn nằm trong tháng?
- [ ] Có phân biệt occurrence thứ n và tuần số n theo `WeekFields`?
- [ ] `with(adjuster)` có được gán kết quả đúng vì kiểu ngày bất biến?
- [ ] "Hôm nay" và "tháng này" có dùng `Clock` với vùng người dùng/chi nhánh?
- [ ] Tests có `Clock.fixed` và ngày nguồn cố định, không phụ thuộc máy chạy?
- [ ] Truy vấn tháng dùng `[startInclusive,endExclusive)`?
- [ ] Khi lọc timestamp `Instant`, đã chuyển cả hai ranh giới qua cùng `ZoneId`?
- [ ] Nếu lịch có giờ địa phương, đã xử lý DST gap/overlap khi tạo instant?
- [ ] Ngày làm việc có lịch nghỉ/ngày lễ thật khi ứng dụng yêu cầu?
- [ ] Kỳ cuối tháng được neo vào `YearMonth` thay vì cộng tháng lặp từ ngày đã bị clamp?
- [ ] Không tự biến ngày lịch thành UTC midnight khi chưa có zone?
- [ ] Dữ liệu API/DB được parse/format bằng kiểu ngày giờ có ngữ nghĩa rõ?

**Ghi nhớ:** `firstDayOfMonth()` và `lastDayOfMonth()` tìm ranh giới **ngày lịch**, `YearMonth` biểu diễn **kỳ tháng**, còn `next(DOW)` tìm ngày đúng thứ **sau ngày hiện tại**; `nextOrSame(DOW)` có thể nhận chính hôm nay. Kết hợp `Clock`, `ZoneId` và ranh giới tháng nửa mở sẽ giúp các phép tính không bị phụ thuộc timezone máy chủ hoặc sai qua DST.

### Tài liệu Oracle chính thức đang được duy trì

- [`TemporalAdjusters` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjusters.html): `firstDayOfMonth`, `lastDayOfMonth`, `firstDayOfNextMonth`, `next`, `nextOrSame`, `firstInMonth`, `lastInMonth` và `dayOfWeekInMonth`.
- [`TemporalAdjuster` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjuster.html): chiến lược chỉnh ngày, `adjustInto`.
- [`LocalDate` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html): `with`, `lengthOfMonth`, `atStartOfDay(ZoneId)`.
- [`YearMonth` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/YearMonth.html): `atDay`, `atEndOfMonth`, `lengthOfMonth` và `plusMonths`.
- [`DayOfWeek` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/DayOfWeek.html): thứ ISO và giá trị enum.
- [`Clock` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): `fixed`, `withZone`, dependency injection đồng hồ.
- [`ZonedDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): local timeline, DST gap/overlap.
- [`WeekFields` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/WeekFields.html): quy tắc tuần theo ISO hoặc locale.
