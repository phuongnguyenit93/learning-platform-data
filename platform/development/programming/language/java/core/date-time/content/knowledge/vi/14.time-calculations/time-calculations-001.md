# Chọn phép tính theo ngày lịch hoặc theo dòng thời gian

Khi xử lý ngày giờ, Java cần diễn đạt đúng ý định của nghiệp vụ: **giữ một ngày/giờ trên lịch** hay **dịch chuyển một thời lượng cố định trên trục thời gian**. Hai việc này có thể trả về kết quả khác nhau khi đi qua giờ mùa hè (DST), cuối tháng hoặc cuối năm.

Trong `java.time`, các kiểu chính là `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `Instant`, `Period` và `Duration`. Hãy chọn theo ý nghĩa cần giữ, không chỉ dựa vào chữ “ngày”, “giờ” hoặc “tháng” trong yêu cầu.

## 1. Hai cách nghĩ khác nhau

**Phép tính theo lịch** giữ ý nghĩa các đơn vị lịch như ngày, tháng, năm hoặc giờ địa phương trong một vùng cụ thể. Ví dụ: “ngày mai lúc 09:00 tại Hà Nội”, “thêm một tháng cho hóa đơn”, “cùng giờ vào ngày làm việc kế tiếp”.

**Phép tính theo dòng thời gian** dịch chuyển bằng một khoảng thời gian có độ dài xác định. Ví dụ: “sau đúng 24 giờ”, “timeout sau 30 giây”, “đo khoảng giữa lúc gửi và nhận một yêu cầu”.

| Nhu cầu | Kiểu/API phù hợp |
| --- | --- |
| Ngày lịch kế tiếp | `LocalDate.plusDays(1)` |
| Tháng lịch tiếp theo | `LocalDate.plusMonths(1)` hoặc `Period.ofMonths(1)` |
| Cùng giờ địa phương ngày mai tại một vùng | `ZonedDateTime.plusDays(1)` |
| Sau đúng 24 giờ | `Instant.plus(Duration.ofHours(24))` |
| Timeout 10 giây | `Duration.ofSeconds(10)` |
| Đo từ lúc bắt đầu đến kết thúc | `Duration.between(start, end)` |
| Lặp 09:00 mỗi ngày ở một thành phố | Ngày/`LocalTime` + `ZoneId` và chính sách DST |

**Một ngày lịch không phải lúc nào cũng tương đương 24 giờ thực.** Tại vùng có DST, thời gian thực giữa hai giờ trưa của hai ngày lịch liền kề có thể là 23 hoặc 25 giờ. Ngược lại, `Duration.ofDays(1)` luôn bằng 86.400 giây.

## 2. Phân biệt Period và Duration

`Period` biểu diễn thành phần lịch theo năm, tháng, ngày. `Duration` biểu diễn thời lượng theo giây và nano giây.

| Đặc điểm | `Period` | `Duration` |
| --- | --- | --- |
| Ý nghĩa | Thành phần năm/tháng/ngày theo lịch | Khoảng thời gian có độ dài xác định |
| Ví dụ | `Period.ofMonths(1)` | `Duration.ofHours(24)` |
| Đơn vị ngày | Một ngày lịch | `Duration.ofDays(1)` luôn là 86.400 giây |
| Đơn vị tháng | Có; áp dụng theo lịch cụ thể | Không có tháng cố định theo giây |
| Phù hợp | Ngày kỳ hạn, ngày lịch kế tiếp, tháng/năm lịch | Timeout, retry delay, thời gian thực giữa hai Instant |

```java
import java.time.Duration;
import java.time.Period;

Period oneMonth = Period.ofMonths(1);
Period oneCalendarDay = Period.ofDays(1);
Duration twentyFourHours = Duration.ofHours(24);
Duration oneDurationDay = Duration.ofDays(1);

System.out.println(oneMonth);         // P1M
System.out.println(oneCalendarDay);   // P1D
System.out.println(twentyFourHours);  // PT24H
System.out.println(oneDurationDay);  // PT24H
```

Đây là đoạn minh họa cần đặt trong một phương thức Java. `Period.ofDays(1)` nói một ngày lịch; `Duration.ofDays(1)` nói 24 giờ. `Period.ofMonths(1)` không thể quy đổi thành một số giây cố định nếu chưa có ngày/tháng và quy tắc lịch cụ thể.

## 3. Cộng ngày và tháng bằng LocalDate

`LocalDate` chỉ chứa ngày lịch, không có giờ hoặc múi giờ. Dùng nó khi bài toán thực sự là về ngày:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate invoiceDate = LocalDate.of(2024, 1, 31);

System.out.println(invoiceDate.plusDays(1));              // 2024-02-01
System.out.println(invoiceDate.plusMonths(1));            // 2024-02-29
System.out.println(invoiceDate.plus(Period.ofMonths(1))); // 2024-02-29
```

Khi cộng tháng, nếu ngày đó không tồn tại trong tháng đích thì Java điều chỉnh về ngày cuối tháng. Vì vậy 31/01/2024 cộng một tháng thành 29/02/2024. Với năm thường, 31/01/2023 cộng một tháng thành 28/02/2023:

```java
LocalDate january31 = LocalDate.of(2023, 1, 31);
System.out.println(january31.plusMonths(1)); // 2023-02-28
```

Đây là quy tắc điều chỉnh ngày tháng của API, nhưng không thay thế chính sách riêng của nghiệp vụ. Nếu kỳ hạn thanh toán yêu cầu “ngày cuối cùng của mỗi tháng”, cân nhắc `YearMonth.atEndOfMonth()` hoặc một quy tắc cuối tháng được định nghĩa rõ; đừng giả định mọi hợp đồng đều muốn cách điều chỉnh mặc định.

## 4. Cùng giờ địa phương ngày hôm sau: dùng ZonedDateTime.plusDays

`ZonedDateTime` chứa ngày giờ, `ZoneId` và offset đã được phân giải. Khi yêu cầu là “vẫn lúc 12:00 vào ngày lịch kế tiếp tại New York”, hãy thực hiện phép tính lịch trên `ZonedDateTime`:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime beforeDst = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);
ZonedDateTime tomorrowAtNoon = beforeDst.plusDays(1);

System.out.println(beforeDst);
// 2024-03-09T12:00-05:00[America/New_York]
System.out.println(tomorrowAtNoon);
// 2024-03-10T12:00-04:00[America/New_York]
System.out.println(Duration.between(
        beforeDst.toInstant(), tomorrowAtNoon.toInstant()).toHours());
// 23
```

Đây là đoạn minh họa cần đặt trong phương thức Java. New York bắt đầu DST ngày 10/03/2024, khiến offset đổi từ `-05:00` thành `-04:00`. `plusDays(1)` giữ trưa ngày kế tiếp theo lịch địa phương, nhưng hai mốc trưa chỉ cách nhau 23 giờ thực.

Cách này phù hợp với lịch họp, lịch hẹn, lời nhắc địa phương và ca làm theo giờ vùng. Với một giờ nằm đúng khoảng DST không tồn tại hoặc bị lặp, vẫn cần chính sách xử lý gap/overlap; phép tính lịch không tự xác định nghiệp vụ muốn từ chối hay điều chỉnh giờ.

## 5. Sau đúng 24 giờ: dùng Duration hoặc Instant

Nếu ý nghĩa là “sau đúng 24 giờ kể từ bây giờ”, hãy dịch chuyển một thời điểm bằng `Duration`:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));

System.out.println(after24Hours);
// 2024-03-10T13:00-04:00[America/New_York]
```

Cộng đúng 24 giờ dẫn đến 13:00, vì khoảng thời gian thực là mục tiêu. Nếu dùng `Instant`, ý nghĩa còn rõ hơn:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2024-03-09T17:00:00Z");
Instant after24Hours = start.plus(Duration.ofHours(24));

System.out.println(after24Hours); // 2024-03-10T17:00:00Z
System.out.println(Duration.between(start, after24Hours).toHours()); // 24
```

Dùng `Duration` cho timeout, retry delay, độ trễ mạng, khoảng nghỉ “đúng 15 phút”, hoặc thời lượng giữa hai mốc. Không dùng `Duration.ofDays(1)` khi ý định là “ngày mai cùng giờ địa phương”; không dùng `Period.ofDays(1)` nếu yêu cầu bắt buộc đúng 86.400 giây.

## 6. Ví dụ Java 17+ chạy hoàn chỉnh

Lưu thành **`CalendarVsTimelineDemo.java`**:

```java
import java.time.*;

public class CalendarVsTimelineDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZonedDateTime beforeDst = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYork);

        ZonedDateTime sameLocalTimeTomorrow = beforeDst.plusDays(1);
        ZonedDateTime exactly24HoursLater =
                beforeDst.plus(Duration.ofHours(24));

        System.out.println("Start: " + beforeDst);
        System.out.println("Calendar + 1 day: " + sameLocalTimeTomorrow);
        System.out.println("Timeline + 24 hours: " + exactly24HoursLater);
        System.out.println("Calendar elapsed hours: "
                + Duration.between(beforeDst.toInstant(),
                                  sameLocalTimeTomorrow.toInstant()).toHours());
        System.out.println("Timeline elapsed hours: "
                + Duration.between(beforeDst.toInstant(),
                                  exactly24HoursLater.toInstant()).toHours());

        LocalDate endOfJanuary = LocalDate.of(2024, 1, 31);
        System.out.println("Plus one calendar month: "
                + endOfJanuary.plusMonths(1));
        System.out.println("Period of one month: "
                + endOfJanuary.plus(Period.ofMonths(1)));

        Instant start = Instant.parse("2024-03-09T17:00:00Z");
        System.out.println("Instant + 24h: "
                + start.plus(Duration.ofHours(24)));
    }
}
```

Biên dịch và chạy:

```bash
javac CalendarVsTimelineDemo.java
java CalendarVsTimelineDemo
```

**stdout** đã kiểm tra bằng Java 17:

```text
Start: 2024-03-09T12:00-05:00[America/New_York]
Calendar + 1 day: 2024-03-10T12:00-04:00[America/New_York]
Timeline + 24 hours: 2024-03-10T13:00-04:00[America/New_York]
Calendar elapsed hours: 23
Timeline elapsed hours: 24
Plus one calendar month: 2024-02-29
Period of one month: 2024-02-29
Instant + 24h: 2024-03-10T17:00:00Z
```

Kết quả cho thấy:
1. `plusDays(1)` giữ giờ địa phương trưa ngày hôm sau, thời lượng thực là 23 giờ.
2. `plus(Duration.ofHours(24))` cộng đúng 24 giờ, nên giờ địa phương thành 13:00.
3. Ngày 31/01 cộng một tháng được điều chỉnh về ngày cuối tháng 2.
4. `Instant` + 24 giờ giữ chính xác khoảng trên dòng thời gian.

## 7. Không áp dụng phép tính thời lượng khi đang xử lý ngày lịch

Một `LocalDate` không có giờ hoặc zone. Vì thế, `LocalDate.plusDays(1)` là phép tính ngày lịch hợp lý, trong khi cộng “86.400 giây” đòi hỏi giả định rằng ngày có thể biểu diễn thành một mốc thời gian thực. Nếu yêu cầu là “ngày nghỉ tiếp theo”, “ngày sinh nhật kế tiếp” hoặc “ngày lập hóa đơn kế tiếp”, hãy dùng API lịch và quy tắc nghiệp vụ tương ứng.

Một `LocalDateTime` cũng không có zone. Nó cho phép cộng trường ngày/giờ trên lịch, nhưng không đủ để xác định chính xác thời lượng thực nếu chưa biết offset/vùng. Muốn đo chênh lệch thời gian giữa hai địa điểm, trước hết cần quy đổi mỗi mốc sang `Instant` với zone/offset đúng.

Một `ZonedDateTime` có vùng địa lý nên có thể thực hiện cả phép tính lịch lẫn phép tính thời lượng. Sự khác biệt nằm ở kiểu phần cộng: `plusDays(1)` là đơn vị lịch, còn `plus(Duration.ofHours(24))` là thời lượng cố định.

## 8. Tình huống thực tế và cách chọn

| Yêu cầu | Cách giải thích đúng |
| --- | --- |
| “Nhắc lúc 09:00 ngày mai tại Hà Nội” | Ngày lịch ngày mai + `LocalTime` 09:00 + `ZoneId` Việt Nam; phân giải theo zone khi cần chạy nhắc |
| “Hết hạn đúng 24 giờ sau khi tạo đơn” | `createdAt.plus(Duration.ofHours(24))` |
| “Thanh toán sau một tháng” | Quy định một tháng lịch và cách xử lý cuối tháng, dùng `Period` hoặc phép tính tháng |
| “Cùng giờ ngày mai ở New York” | `ZonedDateTime.plusDays(1)` và kiểm tra DST nếu cần |
| “Retry lại sau 30 giây” | `Duration.ofSeconds(30)` |
| “Đo thời gian giữa gửi và nhận” | Hai `Instant` rồi `Duration.between(start, end)` |
| “Ngày cuối tháng” | `YearMonth.atEndOfMonth()` hoặc quy tắc cuối tháng cụ thể |
| “Sau 365 ngày” | Cộng đúng 365 ngày theo ý nghĩa được yêu cầu; không mặc nhiên coi đó là một năm lịch |
| “Cùng ngày giờ trên lịch vào tháng sau” | `LocalDate.plusMonths(1)` hoặc `ZonedDateTime.plusMonths(1)` với chính sách ngày cuối tháng |
| “Ca 22:00–06:00 sáng hôm sau” | Xác định ngày bắt đầu/kết thúc và zone; tính thời lượng thực từ hai thời điểm đã phân giải |

Một trường có tên `expiresAt` thường nói về một thời điểm tuyệt đối; `dueDate` có thể là ngày lịch; `openTime` thường chỉ giờ mở cửa. Hãy chốt ngữ nghĩa từ yêu cầu nghiệp vụ trước khi chọn kiểu hoặc phép cộng.

## 9. DST, cuối tháng và các ranh giới

**DST:** ngày địa phương có thể dài 23 hoặc 25 giờ thực. Phép lịch và phép thời lượng có thể cho giờ địa phương khác nhau.

**Cuối tháng:** tháng có 28, 29, 30 hoặc 31 ngày. Java điều chỉnh ngày nếu ngày nguồn không tồn tại trong tháng đích; nghiệp vụ cuối tháng có thể cần quy tắc riêng.

**Năm nhuận:** `Duration.ofDays(365)` không phải một năm lịch. Nếu yêu cầu là năm tiếp theo, dùng phép tính lịch trên `LocalDate` hoặc `ZonedDateTime` và làm rõ chính sách ngày 29/02.

**Nửa đêm:** cùng `Instant` có thể rơi vào các ngày lịch khác nhau tùy zone. Chuyển sang zone nghiệp vụ trước khi lấy `LocalDate` để phân nhóm báo cáo hoặc xác định ngày hết hạn.

**Giờ lặp/giờ bị bỏ qua:** một `LocalDateTime` có thể không tồn tại hoặc xuất hiện hai lần tại vùng DST. Khi chuyển một giờ địa phương thành thời điểm thực, xem xét `ZoneRules.getValidOffsets(local)` và quyết định từ chối, điều chỉnh hay chọn offset theo chính sách đã thống nhất.

## 10. Lỗi thường gặp

1. **Dùng `Duration.ofDays(1)` cho “ngày mai cùng giờ”.** Nó cộng 24 giờ thực và có thể làm giờ địa phương lệch qua DST.
2. **Dùng `Period.ofDays(1)` cho timeout 24 giờ.** Period là đơn vị lịch; Duration là khoảng cố định.
3. **Coi tháng bằng 30 ngày.** Độ dài tháng thay đổi; dùng phép tính lịch.
4. **Coi năm bằng 365 ngày.** Năm nhuận khiến quy tắc này sai cho năm lịch.
5. **Cộng Duration vào `LocalDateTime` rồi coi kết quả là một Instant.** LocalDateTime thiếu zone/offset; nó không xác định thời điểm tuyệt đối.
6. **Đo chênh lệch giữa hai giờ địa phương không cùng vùng.** Quy đổi sang `Instant` trước rồi dùng `Duration.between`.
7. **Bỏ qua gap/overlap DST.** Giờ địa phương có thể không tồn tại hoặc bị lặp; lịch hẹn cần chính sách rõ.
8. **Coi `plusMonths(1)` là cộng cố định số giây.** Đây là phép tính lịch, có thể điều chỉnh ngày cuối tháng.
9. **Dùng thời gian mặc định của máy chủ.** Với logic phụ thuộc vùng/ngày hôm nay, truyền `ZoneId` rõ ràng và dùng `Clock` khi cần kiểm thử ổn định.
10. **Không xác định “một ngày” có nghĩa gì.** Làm rõ “ngày liền kế” hay “86.400 giây” trong hợp đồng nghiệp vụ.

## 11. Kiểm thử cần có

| Ca kiểm thử | Mong đợi |
| --- | --- |
| New York 12:00 ngày 09/03/2024 cộng một ngày lịch | 12:00 ngày 10/03, thời lượng thực 23 giờ |
| Cùng mốc cộng 24 giờ | 13:00 ngày 10/03, thời lượng thực 24 giờ |
| 31/01/2024 cộng một tháng | 29/02/2024 |
| Cộng một ngày tại vùng không đổi DST | Xác minh cả local value và Instant |
| Hẹn tại giờ DST gap | Áp chính sách: từ chối hoặc điều chỉnh đã công bố |
| Hẹn tại giờ DST overlap | Chọn/ghi lại một trong hai offset nếu cần duy nhất một Instant |
| Đo hai sự kiện | So sánh hai Instant và dùng Duration.between |
| Timeout | Kiểm tra tổng giây và giới hạn thời lượng |

Trong JUnit 5, có thể khẳng định hai kết quả bằng `assertEquals` trên `ZonedDateTime` hoặc `Instant`, và kiểm tra `Duration.between(start.toInstant(), end.toInstant()).toHours()` bằng 23 hay 24 ở các ca DST. Khi kiểm thử, so sánh cả **giờ địa phương** lẫn **thời điểm thực** giúp làm rõ ý định của phép tính.

## 12. Bảng API nhanh

| Mục tiêu | API |
| --- | --- |
| Ngày lịch kế tiếp | `LocalDate.plusDays(1)` |
| Tháng lịch kế tiếp | `LocalDate.plusMonths(1)` / `Period.ofMonths(1)` |
| Cùng giờ địa phương ngày mai tại vùng | `ZonedDateTime.plusDays(1)` |
| Cộng đúng một ngày 24 giờ | `Instant.plus(Duration.ofDays(1))` |
| Timeout cố định | `Duration.ofSeconds/Minutes/Hours(...)` |
| Thời lượng giữa hai mốc | `Duration.between(Instant, Instant)` |
| Ngày cuối tháng | `YearMonth.atEndOfMonth()` |
| Chuyển một thời điểm sang vùng hiển thị | `Instant.atZone(zone)` |
| Kiểm tra giờ địa phương ở DST | `ZoneRules.getValidOffsets(local)` |

**Ghi nhớ:** Dùng `Period` và phép tính lịch cho năm/tháng/ngày; dùng `Duration` và `Instant` cho thời lượng cố định. Khi giữ giờ địa phương theo một vùng, dùng `ZonedDateTime` và `ZoneId`. Trước khi viết phép tính, hãy nói rõ yêu cầu cần giữ **ngày/giờ trên lịch** hay cần dịch chuyển **một số giây thực**.
