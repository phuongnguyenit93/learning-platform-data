# JSR 310 và hệ kiểu java.time: mô hình ngày giờ hiện đại trong Java

## 1. Vì sao phải hiểu **mô hình kiểu** trước khi tính ngày giờ?

**JSR 310** (*Date and Time API*) là đặc tả đưa bộ API ngày giờ hiện đại vào Java 8 dưới các package `java.time` và các package con. Các lớp này **vẫn là lựa chọn chủ đạo trong Java hiện nay**. Chúng mô tả nhiều khái niệm khác nhau: **ngày trên lịch**, **giờ trên đồng hồ**, **thời điểm duy nhất trên trục thời gian**, **độ lệch UTC**, **múi giờ có quy tắc lịch sử**, **khoảng thời gian thực** và **khoảng thời gian theo lịch**.

Một lỗi thiết kế phổ biến là dùng một kiểu cho tất cả: ví dụ lưu `LocalDateTime` cho thời điểm thanh toán, dùng `Instant` cho ngày sinh, hoặc dùng `Duration.ofDays(1)` để tăng “một ngày lịch” qua thời điểm đổi giờ mùa hè. Các biểu thức có thể biên dịch nhưng **không thể hiện đúng nghiệp vụ**.

Hãy luôn hỏi:

1. Dữ liệu chỉ có **ngày** (ngày sinh, ngày đến hạn) hay có cả **giờ**?
2. Cần biết một **instant duy nhất** hay chỉ một giờ địa phương chưa gắn múi giờ?
3. Có cần giữ **vùng múi giờ** (ví dụ `Asia/Ho_Chi_Minh`, `America/New_York`) hay chỉ có **offset** (ví dụ `+07:00`)?
4. “Thêm một ngày” nghĩa là **ngày lịch tiếp theo** hay **đúng 24 giờ đã trôi qua**?
5. Khi parse, hiển thị, lưu database, gọi API hay viết test, thông tin múi giờ và lịch nào phải được bảo toàn?

Bài học trình bày từ hệ kiểu đến chuyển đổi, phép tính, DST, format/parse và thiết kế API. Tất cả ví dụ runnable sử dụng **JDK 17+** để dễ kiểm thử; nội dung cốt lõi của JSR 310, `LocalDate`, `Instant`, `ZonedDateTime`, `Duration`, `Period`, `Clock` và `DateTimeFormatter` đã có từ **Java 8**. Trọng tâm là API **còn áp dụng**, không học thuộc cách làm lỗi thời.

## 2. Ba trục phân loại: lịch, trục thời gian và ngữ cảnh múi giờ

Hình dung hai câu hỏi riêng:

**A. Đang nói về ngày/giờ trên mặt đồng hồ hay về một khoảnh khắc trên trục thời gian?**

- `2024-02-29`: một **ngày lịch**, chưa có giờ.
- `09:45:30`: một **giờ trong ngày**, chưa có ngày.
- `2024-02-29T09:45:30`: ngày và giờ **theo đồng hồ**, nhưng chưa biết ở đâu.
- `2024-02-29T02:45:30Z`: một **thời điểm duy nhất**, định danh trên timeline UTC.
- `2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]`: một cách biểu diễn của **thời điểm đó** trong múi giờ cụ thể.

**B. Nếu có ngày giờ địa phương, đã biết cách quy đổi về UTC chưa?**

`LocalDateTime` **không có** offset hoặc zone; cùng `2024-02-29T09:45` ở Hà Nội và New York thường chỉ các instant khác nhau. `OffsetDateTime` gắn offset cụ thể, nên có thể suy ra instant. `ZonedDateTime` gắn cả `ZoneId` để chọn offset theo quy tắc có hiệu lực cho ngày giờ tương ứng.

**C. Đang đo thời lượng vật lý hay khoảng lịch?**

`Duration.ofHours(24)` là đúng 86.400 giây; `Period.ofDays(1)` là **một ngày lịch**. Nếu một múi giờ điều chỉnh daylight saving time (DST), hai phép tính trên một `ZonedDateTime` có thể kết thúc tại **hai giờ địa phương khác nhau**.

Không có một lớp “DateTime” duy nhất giải quyết mọi trục; **việc có nhiều kiểu là chủ đích của JSR 310**, giúp sai khác ngữ nghĩa xuất hiện ngay trong API.

## 3. Bảng tra cứu các kiểu chính trong `java.time`

| Kiểu | Chứa thông tin gì? | Có zone/offset? | Tình huống phù hợp |
| --- | --- | --- | --- |
| `LocalDate` | Năm–tháng–ngày trong lịch ISO | Không | Ngày sinh, ngày nghỉ, ngày đến hạn |
| `LocalTime` | Giờ–phút–giây–nano trong ngày | Không | Giờ mở cửa, thời điểm trên đồng hồ không gắn ngày |
| `LocalDateTime` | Ngày + giờ địa phương | Không | Lịch hẹn “09:00 ngày X” chưa xác định zone |
| `Instant` | Điểm duy nhất trên timeline, giây/nano so với epoch UTC | Không giữ vùng múi giờ | Thời gian sự kiện, log, mốc tạo bản ghi |
| `OffsetDateTime` | Ngày giờ địa phương + một `ZoneOffset` | Có offset, không có region rules | API truyền ngày giờ kèm `+07:00` |
| `ZonedDateTime` | Ngày giờ + `ZoneId` + offset được giải quyết | Có region/rules và offset | Lịch hẹn thuộc một múi giờ cụ thể, DST |
| `OffsetTime` | Giờ trong ngày + offset | Có offset nhưng không có ngày | Giờ giờ địa phương với offset trong giao thức |
| `ZoneId` | Định danh múi giờ/offset | Chính là thông tin zone | `Asia/Ho_Chi_Minh`, `Europe/Paris` |
| `ZoneOffset` | Chênh lệch cố định so với UTC | Offset duy nhất | `Z`, `+07:00`, `-05:00` |
| `Duration` | Khoảng thời gian theo giây và nano | Không | Timeout, thời gian chạy, elapsed time |
| `Period` | Khoảng lịch theo năm, tháng, ngày | Không | Cộng tháng, niên hạn, chu kỳ |
| `Year` | Năm riêng lẻ | Không | Khóa năm thống kê |
| `YearMonth` | Năm và tháng | Không | Kỳ lương, kỳ kế toán |
| `MonthDay` | Tháng và ngày, chưa có năm | Không | Sinh nhật tái diễn (cần quy tắc cho 29/2) |
| `Month` / `DayOfWeek` | Enum tháng hoặc thứ | Không | Quy tắc lịch, hiển thị tên tháng/thứ |
| `Clock` | Nguồn lấy “hiện tại” với zone | Có zone của đồng hồ | Test cố định thời gian, inject thời gian |
| `DateTimeFormatter` | Formatter/parser bất biến | Có thể định dạng thông tin zone nếu type hỗ trợ | Giao tiếp ISO 8601 và hiển thị theo locale |

Đa số lớp trên dùng lịch **ISO-8601** theo hệ lịch Gregorian kéo dài về quá khứ (*proleptic Gregorian*). Cần chú ý dữ liệu lịch sử/nhật lịch của quốc gia có thể yêu cầu cách mô hình hóa khác; `java.time.chrono` phục vụ những lịch phi ISO có chủ đích, không phải mặc định cho mọi nghiệp vụ.

**`OffsetTime` chưa định danh một Instant**, vì không có **ngày**. Ngược lại, `OffsetDateTime` có đủ ngày+giờ+offset nên xác định được một instant. `LocalDate` và `YearMonth` cũng không tự cho ra timestamp nếu chưa chọn giờ và zone.

## 4. Các package tạo nên kiến trúc JSR 310

- **`java.time`:** những lớp chính như `LocalDate`, `Instant`, `ZonedDateTime`, `Duration`, `Period`, `ZoneId`, `Clock`.
- **`java.time.format`:** `DateTimeFormatter`, `DateTimeFormatterBuilder`, `ResolverStyle` và `DateTimeParseException` để parse/format và quyết định mức nghiêm ngặt.
- **`java.time.temporal`:** các giao diện và công cụ mức thấp `Temporal`, `TemporalAccessor`, `TemporalField`, `TemporalUnit`, `TemporalAmount`; các tiện ích `ChronoUnit`, `ChronoField`, `TemporalAdjusters`, `WeekFields`.
- **`java.time.zone`:** `ZoneRules`, `ZoneOffsetTransition` và `ZoneRulesProvider`; là nơi tìm các quy tắc offset/DST gắn với vùng múi giờ.
- **`java.time.chrono`:** các hệ niên lịch khác ISO qua `Chronology` và lớp tương ứng; dùng khi domain thực sự cần.
  
Đây không phải hệ kiểu để kế thừa tùy tiện mọi lớp. Các kiểu chính là **immutable, thread-safe, value-based** theo hợp đồng API; các phép `plusDays`, `withMonth`, `atZone` thường **trả đối tượng mới**, không sửa đối tượng cũ. Không dựa vào phép so sánh identity `==`, identity hash code hoặc `synchronized` trên đối tượng value-based.

Một lớp chỉ biểu diễn những thuộc tính có nghĩa của nó: `LocalDate.getHour()` không tồn tại; `Instant.getDayOfMonth()` không có nghĩa độc lập với zone. Muốn biết ngày địa phương từ `Instant`, trước hết phải **chọn `ZoneId`**.

## 5. Sự bất biến và phép xây dựng type-safe

Các factory hiện đại như `of`, `parse`, `now`, `from` tạo đối tượng đúng kiểu và xác thực miền giá trị. `LocalDate.of(2023, 2, 29)` ném `DateTimeException` vì 2023 không nhuận; không tạo một “ngày sai” rồi âm thầm sửa ở mọi trường hợp.

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalDate next = date.plusDays(1);

// date vẫn là 2024-02-29
// next là 2024-03-01
```

Các kiểu hỗ trợ method chain:
- `LocalDateTime.of(date, time)` kết hợp ngày và giờ **không zone**.
- `localDateTime.atZone(zone)` giải quyết một ngày giờ địa phương sang vùng múi giờ cụ thể; có thể cần quy tắc DST.
- `zonedDateTime.toInstant()` chiếu xuống timeline; `toLocalDateTime()` chỉ lấy lại mặt đồng hồ và **bỏ thông tin zone**.
- `Instant.atZone(zone)` biểu diễn cùng một moment theo zone được chọn.

**Không nên tự đổi lớp bằng cách parse một chuỗi `toString()`** trừ khi hợp đồng format rõ ràng. Java đã có các phương thức chuyển đổi type-safe như `toInstant`, `atZone`, `toLocalDate` và các factory `ofInstant`/`from`.

## 6. Ví dụ đầy đủ: các loại giá trị trên cùng một ngày

Tạo tệp `CoreTypesDemo.java`:

```java
import java.time.*;
import java.time.temporal.TemporalAdjusters;

public class CoreTypesDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(9, 45, 30);
        LocalDateTime local = LocalDateTime.of(date, time);

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = local.atZone(zone);

        System.out.println("date = " + date);
        System.out.println("time = " + time);
        System.out.println("local = " + local);
        System.out.println("zoned = " + zoned);
        System.out.println("offset = " + zoned.toOffsetDateTime());
        System.out.println("instant = " + zoned.toInstant());

        System.out.println("yearMonth days = " +
                YearMonth.of(2024, 2).lengthOfMonth());
        System.out.println("monthDay = " + MonthDay.from(date));
        System.out.println("weekday = " + date.getDayOfWeek());
        System.out.println("next Monday = " +
                date.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("unchanged original = " + date);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 CoreTypesDemo.java
java CoreTypesDemo
```

Đầu ra đã kiểm chứng:

```text
date = 2024-02-29
time = 09:45:30
local = 2024-02-29T09:45:30
zoned = 2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]
offset = 2024-02-29T09:45:30+07:00
instant = 2024-02-29T02:45:30Z
yearMonth days = 29
monthDay = --02-29
weekday = THURSDAY
next Monday = 2024-03-04
unchanged original = 2024-02-29
```

Đọc kết quả:
- `LocalDateTime` chỉ ghi `2024-02-29T09:45:30`, không tự khẳng định đó là giờ Hà Nội hay New York.
- Khi gắn `Asia/Ho_Chi_Minh`, offset có hiệu lực tại ngày được chọn là `+07:00`. Đổi sang UTC tương ứng `02:45:30Z`.
- `OffsetDateTime` in ngày giờ và `+07:00` nhưng không giữ vùng `[Asia/Ho_Chi_Minh]`; `ZonedDateTime` giữ region ID.
- `YearMonth.of(2024,2).lengthOfMonth()` là 29 vì năm nhuận. `MonthDay` có cách hiển thị `--MM-dd`, **không tự gồm năm**.
- `date.with(TemporalAdjusters.next(MONDAY))` trả ngày thứ Hai kế tiếp. `date` vẫn bất biến.

Đây là các mốc thời gian cố định nên stdout không phụ thuộc vào múi giờ mặc định của máy.

## 7. `Instant`, UTC, epoch và khái niệm “cùng một thời điểm”

`Instant` diễn đạt **một điểm trên timeline** dựa trên thời gian epoch (gốc `1970-01-01T00:00:00Z`). Nó lưu độ chính xác đến nanosecond bằng các thành phần giây và nano; **điều đó không đồng nghĩa đồng hồ hệ thống luôn chính xác đến một nano giây**.

`Instant.parse("2024-01-01T00:00:00Z")` và `Instant.ofEpochMilli(1704067200000L)` mô tả cùng một instant. Ký hiệu `Z` trong ISO-8601 chỉ UTC/offset zero.

Các điều cần phân biệt:
- **Epoch seconds vs epoch milliseconds:** `Instant.ofEpochSecond(s)` nhận **giây**, `Instant.ofEpochMilli(ms)` nhận **milli giây**. Nhầm đơn vị có thể làm thời điểm sai hàng thập kỷ/hàng nghìn năm hoặc vượt miền hợp lệ.
- **Timeline vs wall clock:** `Instant` không lưu thông tin người dùng ở múi giờ nào. Khi hiển thị, chọn `ZoneId`.
- **UTC offset vs timezone region:** `+07:00` là chênh lệch cố định; `Asia/Ho_Chi_Minh` là ID có quy tắc vùng qua thời gian.
- **Cùng instant, nhiều cách hiển thị:** `2024-01-01T00:00Z[UTC]` và `2024-01-01T07:00+07:00[Asia/Ho_Chi_Minh]` là cùng moment.
- **LocalDateTime không phải Instant:** không thể từ `LocalDateTime` duy nhất suy ra một instant nếu không có offset/zone và chính sách giải quyết giờ chồng/gap.

Với audit/event timestamp, `Instant` thường là lựa chọn rõ ràng. Nhưng đối với lịch sinh nhật “ngày 29/2” hay giờ mở cửa “09:00”, `Instant` thường buộc phải chọn một ngày/zone một cách không cần thiết.

## 8. `ZoneId`, `ZoneOffset` và sự khác nhau giữa OffsetDateTime/ZonedDateTime

**`ZoneOffset`** mô tả độ lệch cụ thể so với UTC: `Z`, `+07:00`, `-05:00`. Nó không chứa bộ luật “ngày nào chuyển sang giờ mùa hè”.

**`ZoneId`** có thể là region như `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York`, hoặc một offset ID. Region được liên kết với **`ZoneRules`** mô tả offset có hiệu lực theo thời điểm, kể cả các thay đổi lịch sử và quy định.

**`OffsetDateTime`** đủ để suy ra một instant vì có ngày/giờ và offset. Tuy nhiên, chỉ lưu `2024-01-01T09:00+07:00` **không biết đó là lịch hẹn thuộc vùng nào**, và không biết vùng đó có thể thay đổi offset theo ngày trong tương lai.

**`ZonedDateTime`** gồm ngày giờ theo zone cùng offset đã được giải quyết, thích hợp khi lịch hẹn gắn với vùng `America/New_York` và cần áp dụng quy tắc zone của ngày cụ thể.

Hai phép chuyển zone rất dễ nhầm:
- `withZoneSameInstant(targetZone)`: **giữ nguyên moment**, đổi giờ địa phương cho đúng target zone.
- `withZoneSameLocal(targetZone)`: cố **giữ giờ địa phương** tại zone mới; instant thường **thay đổi** (và trong DST gap/overlap có thể có bước điều chỉnh giờ).

### Quy tắc dữ liệu lưu trữ

Nếu một hệ thống quản lý cuộc hẹn tái diễn “09:00 hàng ngày tại Paris”, cần giữ cả **LocalTime**, quy tắc lịch và `Europe/Paris`; không nên lưu duy nhất offset `+01:00` vì Paris còn có `+02:00` vào một số thời điểm. Nếu hệ thống lưu “thời điểm giao dịch đã xảy ra”, một `Instant` là dữ liệu chính và zone có thể chỉ là phần metadata để hiển thị.

**Không suy ra zone từ offset đơn thuần**: nhiều region có thể cùng dùng `+07:00` tại một thời điểm.

## 9. Ví dụ đầy đủ: giữ instant hay giữ mặt đồng hồ?

Tạo tệp `TimeZoneDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimeZoneDemo {
    public static void main(String[] args) {
        Instant moment = Instant.parse("2024-01-01T00:00:00Z");
        ZonedDateTime utc = moment.atZone(ZoneId.of("UTC"));
        ZonedDateTime hcm = utc.withZoneSameInstant(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        ZonedDateTime changed = hcm.withZoneSameLocal(
                ZoneId.of("UTC"));

        System.out.println("instant = " + moment);
        System.out.println("UTC = " + utc);
        System.out.println("HCM = " + hcm);
        System.out.println("same instant = " +
                moment.equals(hcm.toInstant()));
        System.out.println("same local changed instant = " +
                !changed.toInstant().equals(hcm.toInstant()));
        System.out.println("same local result = " + changed);
        System.out.println("epoch milliseconds = " +
                moment.toEpochMilli());
    }
}
```

```bash
javac -encoding UTF-8 TimeZoneDemo.java
java TimeZoneDemo
```

```text
instant = 2024-01-01T00:00:00Z
UTC = 2024-01-01T00:00Z[UTC]
HCM = 2024-01-01T07:00+07:00[Asia/Ho_Chi_Minh]
same instant = true
same local changed instant = true
same local result = 2024-01-01T07:00Z[UTC]
epoch milliseconds = 1704067200000
```

Ở hai dòng `UTC` và `HCM`, mặt đồng hồ khác nhau nhưng `toInstant()` giống nhau. `withZoneSameLocal(UTC)` giữ con số `07:00`, khiến instant mới thành `07:00Z`, **khác** instant gốc `00:00Z`. Đừng dùng hai phương thức thay thế cho nhau.

## 10. DST: gap, overlap và vì sao LocalDateTime chưa đủ

Tại một vùng có điều chỉnh DST, quy tắc múi giờ có thể tạo ba trạng thái cho một `LocalDateTime`:

| Tình huống | Số offset hợp lệ | Ý nghĩa |
| --- | --- | --- |
| Bình thường | **1** | Ngày giờ địa phương xác định một offset |
| **Gap** (nhảy đồng hồ về phía trước) | **0** | Có những giờ địa phương **không hề xảy ra** |
| **Overlap** (quay đồng hồ về phía sau) | **2** | Một giờ địa phương xuất hiện **hai lần**, chỉ hai instant khác nhau |

Ví dụ được cố định ở vùng `America/New_York` trong năm 2024:
- Ngày **2024-03-10**, `02:30` nằm trong **gap** của đợt chuyển DST. `LocalDateTime.of(2024,3,10,2,30).atZone(zone)` sẽ **điều chỉnh tiến** thành `03:30-04:00` theo cơ chế giải quyết chuẩn.
- Ngày **2024-11-03**, `01:30` ở **overlap**: có thể là `01:30-04:00` hoặc `01:30-05:00`, tương ứng hai instant cách nhau một giờ.
- `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` dùng để chọn offset cụ thể ở overlap.
- Nếu nghiệp vụ không chấp nhận tự điều chỉnh giờ trong gap, kiểm tra `zone.getRules().getValidOffsets(localDateTime)` hoặc dùng API giải quyết nghiêm ngặt như `ZonedDateTime.ofStrict(...)` với offset hợp lệ.

**Đừng mặc định mọi vùng có DST** hoặc dùng offset hiện tại cho một ngày ở quá khứ/tương lai. Các quy tắc múi giờ là dữ liệu có thể thay đổi theo luật và phiên bản TZDB của runtime; ngày giờ cho lịch tương lai cần chính sách cập nhật rõ.

## 11. Một ngày lịch **không luôn là** 24 giờ trên timeline

Với `ZonedDateTime`, các phép cộng đơn vị **ngày/tháng/năm** hoạt động theo ý nghĩa **lịch địa phương**, còn các phép cộng **giờ/phút/giây** tương ứng ý nghĩa **khoảng thời gian thực** trên timeline. Ví dụ ngày đổi DST:
- `zdt.plusDays(1)` giữ **giờ địa phương** nếu có thể, nhưng elapsed time có thể 23 hoặc 25 giờ.
- `zdt.plusHours(24)` luôn thêm **24 giờ thực**, nhưng giờ địa phương cuối có thể đổi.
- `Duration.ofDays(1)` là 86.400 giây, **không phải lịch ngày mai**.
- `Period.ofDays(1)` mô tả cộng một ngày lịch trên kiểu ngày phù hợp.

Với yêu cầu “hạn cuối cùng giờ địa phương vào ngày mai”, dùng thao tác **theo lịch** và region zone; với “timeout đúng 24 giờ” dùng `Duration.ofHours(24)`. Tránh hardcode `24*60*60*1000` rồi cho rằng đó là “mỗi ngày” trong mọi hệ thống.

## 12. Ví dụ đầy đủ: DST và kiểm tra offset hợp lệ

Tạo tệp `DstDemo.java`:

```java
import java.time.*;

public class DstDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        ZonedDateTime base = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, zone);
        ZonedDateTime day = base.plusDays(1);
        ZonedDateTime hours = base.plusHours(24);

        System.out.println("base = " + base);
        System.out.println("plus one day = " + day);
        System.out.println("plus 24 hours = " + hours);
        System.out.println("elapsed day hours = " +
                Duration.between(
                        base.toInstant(), day.toInstant()).toHours());

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("gap valid offsets = " +
                zone.getRules().getValidOffsets(gap).size());
        System.out.println("gap resolved = " + gap.atZone(zone));

        LocalDateTime overlap = LocalDateTime.of(
                2024, 11, 3, 1, 30);
        ZonedDateTime earlier = overlap.atZone(zone);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("overlap valid offsets = " +
                zone.getRules().getValidOffsets(overlap).size());
        System.out.println("overlap earlier = " + earlier);
        System.out.println("overlap later = " + later);
        System.out.println("overlap elapsed minutes = " +
                Duration.between(
                        earlier.toInstant(), later.toInstant()).toMinutes());
    }
}
```

```bash
javac -encoding UTF-8 DstDemo.java
java DstDemo
```

```text
base = 2024-03-09T12:00-05:00[America/New_York]
plus one day = 2024-03-10T12:00-04:00[America/New_York]
plus 24 hours = 2024-03-10T13:00-04:00[America/New_York]
elapsed day hours = 23
gap valid offsets = 0
gap resolved = 2024-03-10T03:30-04:00[America/New_York]
overlap valid offsets = 2
overlap earlier = 2024-11-03T01:30-04:00[America/New_York]
overlap later = 2024-11-03T01:30-05:00[America/New_York]
overlap elapsed minutes = 60
```

Kết quả đã được kiểm chứng trên JDK với quy tắc vùng New York tương ứng các mốc 2024. **Đầu ra chứa offset theo vùng** nên các kiểm thử production phải dùng TZDB của JDK cập nhật và chấp nhận rằng dữ liệu vùng được chính quyền điều chỉnh có thể thay đổi trong tương lai.

Một `LocalDateTime` tự nó vẫn tạo được `2024-03-10T02:30`; chỉ khi gắn region và hỏi offset mới phát hiện đây là một giờ không xảy ra ở New York. Một nhà lập lịch tốt phải quyết định **đẩy giờ**, **từ chối** hay **yêu cầu người dùng chọn** khi có gap/overlap.

## 13. `Duration` và `Period`: hai phép đo mang đơn vị khác nhau

`Duration` là thời lượng theo **giây và phần nano**, thường hợp với đo elapsed time, timeout, delay, token expiry hoặc khoảng cách giữa hai instant. `Duration.between(startInstant, endInstant)` trả `Duration` có thể dương, âm hoặc zero tùy thứ tự.

`Period` là khoảng cách **năm–tháng–ngày**, thường dùng với `LocalDate`, ví dụ tăng chu kỳ thanh toán theo tháng hoặc tính chênh lệch lịch. Tháng có 28/29/30/31 ngày, nên `Period.ofMonths(1)` **không có độ dài giây cố định**.

| Nhu cầu | Kiểu/operation | Đơn vị được bảo toàn |
| --- | --- | --- |
| Timeout 90 giây | `Duration.ofSeconds(90)` | 90 giây thật |
| Đã trôi qua bao lâu | `Duration.between(t1, t2)`, t1/t2 là Instant | Giây/nano |
| Ngày lịch tiếp theo | `LocalDate.plusDays(1)` | Một ngày lịch |
| Cộng một tháng lịch | `LocalDate.plusMonths(1)` hoặc `Period.ofMonths(1)` | Một tháng lịch, có quy tắc ngày cuối |
| Tính năm/tháng/ngày giữa hai ngày | `Period.between(date1, date2)` | Thành phần lịch |
| Đếm số ngày lịch giữa hai LocalDate | `ChronoUnit.DAYS.between(d1, d2)` | Số ngày lịch |
| Tính số giờ giữa hai instant | `Duration.between(t1,t2).toHours()` | Giờ elapsed |

**Không dùng `Period.between` cho hai Instant**; chữ ký `Period.between(LocalDate, LocalDate)` gắn với lịch. Tương tự, `Duration.between` cần temporal có đơn vị thời gian phù hợp; `LocalDate` không có field giờ nên không đại diện đầy đủ cho elapsed seconds.

### Cộng tháng và xử lý ngày cuối

`LocalDate.of(2024,1,31).plusMonths(1)` trả `2024-02-29`, chứ không ném lỗi do “31/2” không hợp lệ. Java dùng quy tắc điều chỉnh ngày về **ngày hợp lệ cuối của tháng kết quả**. Điều này vẫn cần được business xác nhận: các quy tắc thanh toán “ngày 31 mỗi tháng” có thể có chính sách khác (ví dụ ngày làm việc cuối tháng).

### `Period.between` có thể không đơn giản là số ngày

`Period.between(2024-01-31, 2024-03-01)` cho `P1M1D`, không phải `P30D` hay một con số ngày duy nhất. Nếu muốn biết số ngày lịch thực sự giữa hai LocalDate, dùng `ChronoUnit.DAYS.between` hoặc `start.until(end, ChronoUnit.DAYS)`.

## 14. Ví dụ đầy đủ: Period, Duration, ngày nhuận và week-based year

Tạo tệp `ArithmeticDemo.java`:

```java
import java.time.*;
import java.time.temporal.WeekFields;

public class ArithmeticDemo {
    public static void main(String[] args) {
        LocalDate jan = LocalDate.of(2024, 1, 31);
        LocalDate feb = jan.plusMonths(1);

        System.out.println("jan = " + jan);
        System.out.println("plus one month = " + feb);
        System.out.println("period = " +
                Period.between(jan, LocalDate.of(2024, 3, 1)));

        System.out.println("duration = " +
                Duration.between(
                        Instant.parse("2024-01-01T00:00:00Z"),
                        Instant.parse("2024-01-01T01:30:00Z")));

        System.out.println("weekday = " + jan.getDayOfWeek());
        System.out.println("week year = " +
                LocalDate.of(2019, 12, 30)
                        .get(WeekFields.ISO.weekBasedYear()));
        System.out.println("calendar year = " +
                LocalDate.of(2019, 12, 30).getYear());

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("invalid date = DateTimeException");
        }
    }
}
```

```bash
javac -encoding UTF-8 ArithmeticDemo.java
java ArithmeticDemo
```

```text
jan = 2024-01-31
plus one month = 2024-02-29
period = P1M1D
duration = PT1H30M
weekday = WEDNESDAY
week year = 2020
calendar year = 2019
invalid date = DateTimeException
```

`Period` in theo ISO dạng `P1M1D` (1 tháng, 1 ngày), còn `Duration` in `PT1H30M` (1 giờ, 30 phút). Đây là **hai phép đo khác nhau**.

Trường hợp `2019-12-30` thuộc **calendar year 2019** nhưng thuộc **ISO week-based year 2020**: một bài học quan trọng khi viết báo cáo tuần và format ngày. Không dùng số tuần hoặc week-based-year để thay thế năm lịch khi domain không muốn thế.

## 15. `DateTimeFormatter`: biểu diễn chuỗi là lớp ngoài cùng

`DateTimeFormatter` là lớp **immutable và thread-safe** để format/parse. Nên ưu tiên các formatter ISO chuẩn như `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT`, `ISO_OFFSET_DATE_TIME`, `ISO_ZONED_DATE_TIME` khi giao tiếp giữa các hệ thống, hoặc dùng pattern/locale rõ ràng khi cần định dạng cho người dùng.

Điều cần nhớ: **format không bổ sung được dữ liệu mà type không có**. Một `LocalDateTime` không mang offset/zone; chỉ thay pattern không thể tự biến nó thành một instant xác định. Muốn format một instant thành giờ ở Việt Nam, chuyển `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` hoặc dùng formatter có zone được thiết lập có chủ đích.

### Pattern dễ nhầm

| Mẫu | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `uuuu` | Năm proleptic ISO | Phù hợp parse nghiêm ngặt |
| `yyyy` | Năm trong niên đại (year-of-era) | Không đồng nhất hoàn toàn với `uuuu`; với STRICT parsing thiếu era có thể gặp khác biệt |
| `YYYY` | **Week-based-year** | Không phải năm lịch; dễ sai quanh cuối/đầu năm |
| `MM` | Tháng trong năm | Hai chữ `M` là số tháng hai chữ số |
| `mm` | **Phút** | Không phải tháng |
| `dd` | Ngày trong tháng | Khác `DD` là ngày trong năm |
| `HH` | Giờ 0–23 | Khác `hh` là giờ 1–12 cần ngữ cảnh AM/PM |
| `X` / `XXX` | Offset ISO | Dạng cụ thể theo số ký tự |
| `VV` | Zone ID | Chỉ hữu ích khi dữ liệu có zone ID |
| `SSS` | Phần giây ở độ chính xác milli | Không mặc định chứng minh clock có độ chính xác milli |

Đừng dùng `YYYY-MM-dd` để biểu diễn ngày lịch thông thường. `YYYY` là week-based-year, có thể thuộc năm khác ngay từ cuối tháng 12; ngữ nghĩa tuần và locale còn ảnh hưởng cách định nghĩa week-based year.

### Parse nghiêm ngặt và lỗi dữ liệu

`DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT).withResolverStyle(ResolverStyle.STRICT)` cho phép tách ngày theo format UI và **từ chối ngày không hợp lệ** như 31/02. Mẫu `uuuu` đặc biệt hữu ích cho strict parse ngày ISO. Nếu hệ thống cho phép chuẩn hóa giá trị sai kiểu “32/1 thành đầu tháng sau”, phải định nghĩa chính sách riêng, không ngầm chấp nhận như thể đầu vào hợp lệ.

`LocalDate.parse(...)`, `Instant.parse(...)`, `ZonedDateTime.parse(...)` trả type phù hợp hoặc ném `DateTimeParseException` khi chuỗi không parse được. Không dùng `LocalDateTime.parse(...)` cho chuỗi ISO có zone rồi nghĩ zone đã được giữ.

## 16. `Clock`: lấy thời gian hiện tại đúng và viết test tái lập

`LocalDate.now()`, `Instant.now()`, `ZonedDateTime.now()` tiện trong code ứng dụng, nhưng nếu logic nghiệp vụ gọi trực tiếp đồng hồ hệ thống, test có thể phụ thuộc thời điểm chạy và múi giờ mặc định.

`Clock` cho phép **truyền nguồn thời gian** vào service:

```java
class DeadlineService {
    private final Clock clock;

    DeadlineService(Clock clock) {
        this.clock = clock;
    }

    LocalDate today() {
        return LocalDate.now(clock);
    }

    Instant currentInstant() {
        return Instant.now(clock);
    }
}
```

Đoạn minh họa giả định `import java.time.*;`. Trong production có thể truyền `Clock.systemUTC()` hoặc `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` theo nhu cầu. Trong test dùng `Clock.fixed(Instant.parse("...Z"), zone)` để **đóng băng** thời gian. `Clock.offset` có thể tạo đồng hồ lệch một khoảng và `Clock.tick` tạo đồng hồ tick theo chu kỳ khi thật sự cần.

**Không dựa vào `ZoneId.systemDefault()` trong test cần đầu ra xác định**. Default zone phụ thuộc cấu hình môi trường. Đối với backend có nhiều khu vực, truyền `ZoneId` rõ ràng theo user/tenant/domain sẽ giúp tránh lỗi giữa các máy chạy.

Lưu ý: `Clock.fixed` chỉ phục vụ test/định nghĩa “thời gian hiện tại” giả lập; không phải để dùng làm đồng hồ thời gian thực của ứng dụng. Khi đo thời lượng thực thi ngắn, các cơ chế đo monotonic như `System.nanoTime()` cho elapsed time trong cùng process thường thích hợp hơn việc trừ hai wall-clock time (vì đồng hồ hệ thống có thể được điều chỉnh).

## 17. Ví dụ đầy đủ: formatter STRICT, Clock.fixed và chuyển đổi ISO

Tạo tệp `FormatClockDemo.java`:

```java
import java.time.*;
import java.time.format.*;
import java.util.Date;
import java.util.Locale;

public class FormatClockDemo {
    public static void main(String[] args) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDate date = LocalDate.of(2024, 2, 29);
        System.out.println("formatted = " + format.format(date));
        System.out.println("parsed = " +
                LocalDate.parse("29/02/2024", format));

        try {
            LocalDate.parse("31/02/2024", format);
        } catch (DateTimeParseException ex) {
            System.out.println("bad parse = DateTimeParseException");
        }

        Clock fixed = Clock.fixed(
                Instant.parse("2024-08-15T10:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("fixed instant = " + Instant.now(fixed));
        System.out.println("fixed local date = " + LocalDate.now(fixed));
        System.out.println("fixed local time = " + LocalTime.now(fixed));
        System.out.println("fixed zoned = " + ZonedDateTime.now(fixed));

        Instant reference = Instant.parse("2024-08-15T03:30:00Z");
        System.out.println("offset parsed instant = " +
                OffsetDateTime.parse(
                        "2024-08-15T10:30:00+07:00").toInstant());
        System.out.println("epoch = " + reference.toEpochMilli());
        System.out.println("date bridge = " +
                Date.from(reference).toInstant());
    }
}
```

```bash
javac -encoding UTF-8 FormatClockDemo.java
java FormatClockDemo
```

```text
formatted = 29/02/2024
parsed = 2024-02-29
bad parse = DateTimeParseException
fixed instant = 2024-08-15T10:30:00Z
fixed local date = 2024-08-15
fixed local time = 17:30
fixed zoned = 2024-08-15T17:30+07:00[Asia/Ho_Chi_Minh]
offset parsed instant = 2024-08-15T03:30:00Z
epoch = 1723692600000
date bridge = 2024-08-15T03:30:00Z
```

Giải thích:
- Pattern sử dụng `uuuu` để parse năm của ngày theo proleptic calendar với `ResolverStyle.STRICT`; `31/02/2024` bị từ chối.
- Một `Clock.fixed` có **instant 10:30Z** và **zone +07:00**, nên `Instant.now(fixed)` vẫn là `10:30Z`, còn `LocalTime.now(fixed)` là `17:30`. Đây là hai cách nhìn **cùng thời điểm**.
- `OffsetDateTime.parse(...+07:00).toInstant()` cho `03:30Z` vì trừ độ lệch 7 giờ.
- `Date.from(reference).toInstant()` minh họa **cầu nối tương thích** với API nhận `java.util.Date`. Không khuyến khích dùng `Date` thay `java.time` trong code mới; chỉ chuyển đổi ở ranh giới thư viện đang cần `Date`.
- `toEpochMilli()` dùng **millisecond**. Không nhầm kết quả này với số giây epoch.

## 18. `Temporal`, `ChronoUnit` và `TemporalAdjusters`: thao tác cấp thấp

Các type trong `java.time` hỗ trợ những interface để code có thể dùng chung khi thật sự cần:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| `TemporalAccessor` | Đọc các field từ một temporal | `get(ChronoField.DAY_OF_MONTH)` khi type hỗ trợ |
| `Temporal` | Temporal có thể điều chỉnh (trả bản sao) | `date.with(ChronoField.DAY_OF_MONTH, 15)` |
| `TemporalAmount` | Một lượng thời gian/lịch | `Duration`, `Period` |
| `TemporalUnit` | Đơn vị tính toán | `ChronoUnit.DAYS`, `ChronoUnit.HOURS` |
| `TemporalAdjuster` | Quy tắc điều chỉnh temporal | `TemporalAdjusters.lastDayOfMonth()` |
| `WeekFields` | Quy tắc tuần phụ thuộc locale/ISO | `WeekFields.ISO.weekBasedYear()` |

Các ví dụ hữu ích:

```java
LocalDate due = LocalDate.of(2024, 2, 10)
        .with(TemporalAdjusters.lastDayOfMonth());
// 2024-02-29

long days = ChronoUnit.DAYS.between(
        LocalDate.of(2024, 2, 28),
        LocalDate.of(2024, 3, 1));
// 2 (2024 là năm nhuận)

LocalDate nextMonday = LocalDate.of(2024, 2, 29)
        .with(TemporalAdjusters.next(DayOfWeek.MONDAY));
// 2024-03-04
```

Đây là **đoạn minh họa nằm trong phương thức** sau khi import `java.time.*` và `java.time.temporal.*`; các kết quả đã dựa trên dữ liệu lịch cố định. Dùng các method chuyên biệt `plusDays`, `getDayOfWeek`, `atZone` khi rõ nghĩa hơn interface tổng quát. Không giả định mọi `Temporal` hỗ trợ mọi field/unit; gọi một field không được hỗ trợ có thể ném `UnsupportedTemporalTypeException`.

### `YearMonth` và dữ liệu kỳ

`YearMonth.of(2024, 2)` là kỳ **tháng 2/2024**, không phải một ngày cụ thể. Khi cần ngày đầu kỳ: `yearMonth.atDay(1)`. Khi cần cuối kỳ: `yearMonth.atEndOfMonth()`. Đây là cách tránh lấy ngày `2024-02-01` thay thế cho “tháng 2” nếu domain thực sự chỉ có một giá trị tháng.

### `WeekFields` và sai lệch năm tại ranh giới tuần

`WeekFields.ISO` dùng tuần bắt đầu thứ Hai, tuần 1 có ít nhất bốn ngày trong năm. Ngày `2019-12-30` có **calendar year 2019** nhưng **week-based-year 2020**. Vì vậy, pattern `YYYY`/các field week-year không phải cách thay thế trung tính cho năm lịch `uuuu`. Với báo cáo tuần theo tổ chức dùng quy tắc khác, phải dùng `WeekFields` tương ứng, không giả định mọi quốc gia cùng quy tắc đầu tuần.

## 19. Hỗ trợ lịch phi ISO: `java.time.chrono`

Lịch ISO-8601 phù hợp cho phần lớn dữ liệu giao tiếp liên hệ giữa các hệ thống. Tuy nhiên, `java.time.chrono` có API cho các hệ lịch khác, ví dụ `JapaneseDate`, `HijrahDate`, `MinguoDate` và `ThaiBuddhistDate` khi nghiệp vụ yêu cầu.

Điểm thiết kế:
- Không dùng `Chronology` thay cho lựa chọn múi giờ: **lịch** và **timezone** là hai trục độc lập.
- Không mặc định một con số năm trong lịch khác tương ứng với năm ISO; cần converter/hợp đồng đúng chronology.
- Trong database, API và dữ liệu giao tiếp, thường ưu tiên kiểu ISO hoặc `Instant`/offset đã thống nhất. Chỉ chuyển sang lịch địa phương cho mục đích nghiệp vụ/hiển thị khi cần.
- Nếu hệ thống yêu cầu quy tắc niên lịch đặc biệt (lễ theo lịch tôn giáo, niên hiệu...), cần kiểm chứng bộ luật lịch từ domain; `java.time.chrono` là công cụ, không tự tạo ý nghĩa nghiệp vụ.

`java.time.chrono` **không phải API đã lỗi thời**; đây là phần tùy chọn đang còn được duy trì. Nhưng không cần đưa chrono vào mọi chương trình chỉ để “quốc tế hóa” khi hệ thống dùng lịch ISO.

## 20. Thiết kế lưu trữ, truyền API và tương thích thư viện

### Event timestamp

Với bản ghi sự kiện “đã xảy ra lúc nào”, một `Instant` hoặc chuẩn trao đổi ISO-8601 có offset rõ ràng giúp hai hệ thống ở hai múi giờ nhận ra cùng moment. Ví dụ `2024-08-15T03:30:00Z` và `2024-08-15T10:30:00+07:00` cùng một instant.

Khi lưu timestamp vào database, phải xác minh **kiểu cột, driver, time-zone session và hợp đồng truy vấn**, vì tên SQL `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` và cách ánh xạ có thể khác nhau giữa hệ quản trị. Không tuyên bố có một mapping JDBC/database chung cho mọi hệ thống nếu chưa kiểm tra.

### Lịch hẹn theo vùng

Với yêu cầu “họp 09:00 mỗi thứ Hai tại Paris”, lưu **giờ địa phương + vùng `Europe/Paris` + quy tắc tái diễn**, rồi tính các instant theo ngày cụ thể. Chỉ lưu một instant của buổi họp đầu tiên hoặc `+01:00` không đủ mô tả toàn bộ lịch tái diễn khi DST thay đổi.

### Ngày sinh, ngày hết hạn theo lịch

Dùng `LocalDate`. Không ép ngày sinh thành `Instant` bằng cách mặc định `00:00Z` nếu domain không có múi giờ, vì hiển thị ở zone khác có thể thành ngày hôm trước và tạo lỗi khó phát hiện.

### Giờ mở cửa không có ngày

Dùng `LocalTime` cộng với `ZoneId`/lịch áp dụng nếu cần xác định các occurrence thật. `LocalTime.of(9,0)` chỉ là 09:00 trên đồng hồ, chưa phải một instant.

### Dữ liệu epoch nhận từ API ngoài

Luôn ghi rõ **đơn vị giây hay milli giây**, phạm vi, tính UTC, và xử lý giá trị vượt miền. `Instant.ofEpochSecond`, `ofEpochMilli` là API tương ứng. Đừng tự suy đoán từ số chữ số nếu format dữ liệu chưa được công bố.

### Kết nối sang API chỉ chấp nhận `java.util.Date`

Tại boundary thư viện, có thể đổi:

```java
Instant instant = Instant.parse("2024-08-15T03:30:00Z");
java.util.Date old = java.util.Date.from(instant);
Instant back = old.toInstant();
```

Đoạn này minh họa một adapter, không khuyến nghị dùng API cũ làm mô hình chính. Khi đổi về `Date`, phải chú ý độ chính xác có thể bị giới hạn ở mili giây; không giả định giữ nguyên toàn bộ nanoseconds của `Instant`.

## 21. Những lỗi thường gặp

1. **Dùng `LocalDateTime` làm event timestamp** mà không giữ offset/zone: cùng mặt đồng hồ có thể có nhiều instant hoặc không có instant ở DST.
2. **Dùng `Instant` làm ngày sinh**: đưa thêm giờ/zone không có trong nghiệp vụ, dễ lệch ngày khi hiển thị.
3. **Nhầm `ZoneId` với `ZoneOffset`**: `+07:00` không có cùng thông tin lịch sử và quy tắc như region zone.
4. **Giữ `withZoneSameLocal` khi cần cùng instant**: làm thay đổi điểm trên timeline; thường nên dùng `withZoneSameInstant`.
5. **Giả sử một ngày luôn 24 giờ trong vùng có DST**: `plusDays(1)` và `plusHours(24)` có thể khác nhau.
6. **Tạo một `LocalDateTime` trong gap rồi coi nó hợp lệ ở vùng đó**: cần kiểm tra `ZoneRules.getValidOffsets` hoặc policy resolve.
7. **Không xử lý overlap**: một giờ địa phương lặp hai lần có thể chỉ hai instant khác nhau; chọn offset theo nghiệp vụ.
8. **Dùng `Duration` thay `Period` cho chu kỳ tháng/năm**: tháng/năm có độ dài biến động.
9. **Dùng `Period` như một số ngày cố định**: `P1M1D` không phải độ dài giây cố định.
10. **Dùng `YYYY` khi định dạng năm lịch**: week-based-year có thể đổi năm ở cuối tháng 12; dùng `uuuu` hoặc pattern phù hợp.
11. **Nhầm `MM` và `mm`**, hoặc `HH` với `hh`: parse/format sai thông tin.
12. **Parse ngày không hợp lệ mà không đặt policy**: dùng `ResolverStyle.STRICT` khi cần từ chối dữ liệu sai.
13. **Để timezone mặc định của server quyết định logic nghiệp vụ**: khác máy/region có thể khác ngày; truyền `Clock` và `ZoneId` rõ.
14. **Truyền timestamp số không ghi đơn vị**: nhầm epoch seconds với milliseconds.
15. **Dùng `LocalDate.now()` trong test cố định kỳ vọng**: test phụ thuộc ngày hệ thống, đứt gãy vào nửa đêm; dùng `Clock.fixed`.
16. **Tưởng immutable đồng nghĩa cứ gọi `plusDays` là sửa đối tượng**: phải nhận giá trị trả về.
17. **Dùng một formatter pattern không có zone để “cứu” LocalDateTime**: thiếu offset/zone không thể được bổ sung chỉ bằng cách format chuỗi.
18. **Dựa vào dữ liệu timezone cũ cho lịch tương lai**: chính sách DST có thể thay đổi, cần cập nhật TZDB và thiết kế cách giải quyết.
19. **Dùng `Date`/`Calendar` làm model chính khi viết code mới**: JSR 310 đã có type chính xác hơn; chỉ chuyển đổi ở boundary tương thích khi cần.
20. **Dùng `equals` của local/offset/zoned type mà không rõ muốn so instant hay biểu diễn**: hai giá trị có thể chỉ cùng moment nhưng khác offset/zone; nếu chỉ quan tâm timeline, so `toInstant()`.

## 22. Bảng quyết định nhanh theo yêu cầu

| Câu hỏi trong nghiệp vụ | Kiểu nên cân nhắc | Điều phải xác định thêm |
| --- | --- | --- |
| Ngày sinh của người dùng là gì? | `LocalDate` | ISO hoặc chronology khác? |
| Cửa hàng mở lúc mấy giờ mỗi ngày? | `LocalTime` | Region zone, lịch nghỉ và DST nếu có |
| Cuộc hẹn tại Paris 09:00 ngày X? | `LocalDateTime` + `ZoneId`, hoặc `ZonedDateTime` khi đã resolve | Gap/overlap policy |
| Một request được nhận đúng lúc nào? | `Instant` | Độ chính xác clock, nguồn và serialization |
| API gửi `2024-08-15T10:30:00+07:00`? | `OffsetDateTime` | Offset có đủ hay phải lưu region? |
| Cần giữ tên vùng cho lịch tương lai? | `ZonedDateTime`/`ZoneId` và quy tắc lịch | TZDB, recurrence |
| Khoảng chờ 90 giây? | `Duration.ofSeconds(90)` | Clock/timer dùng để đo |
| Thêm 1 tháng vào kỳ kế toán? | `YearMonth` hoặc `Period.ofMonths(1)` | Ngày cuối tháng, ngày làm việc |
| Thống kê theo tuần ISO? | `WeekFields.ISO` | Tuần bắt đầu thứ Hai, week-based-year |
| Hiển thị cho người dùng Việt Nam? | `DateTimeFormatter` + `Locale` + `ZoneId` | Format UI, offset/zone phải có nếu từ Instant |
| Test logic tại “ngày hôm nay”? | `Clock.fixed(...)` | Instant và zone cố định |

Không có một lớp tối ưu cho tất cả. Chọn kiểu **thể hiện chính xác những thông tin domain đã biết và không tự bịa phần còn thiếu**. Một timestamp tốt không thay thế được ngày lịch, và một ngày lịch tốt không tự là timestamp.

## 23. Bài tập tự kiểm tra

**Câu 1.** `LocalDateTime.of(2024,2,29,9,45)` có thể đổi thẳng sang một `Instant` xác định mà không biết zone/offset không?  
**Đáp án:** Không. Nó chỉ mang ngày và giờ theo đồng hồ, không có đủ thông tin để chọn moment trên timeline.

**Câu 2.** `Instant` có ghi nhớ người dùng ở `Asia/Ho_Chi_Minh` không?  
**Đáp án:** Không. Nó là một moment; vùng múi giờ phải được quản lý riêng và chọn khi hiển thị.

**Câu 3.** `2024-01-01T00:00Z` và `2024-01-01T07:00+07:00` có khác moment không?  
**Đáp án:** Không, hai biểu diễn là cùng `Instant`.

**Câu 4.** Lịch hẹn “09:00 mỗi ngày ở New York” nên lưu chỉ offset `-05:00` mãi mãi không?  
**Đáp án:** Không. Offset tại New York thay đổi theo mùa/năm; cần region `America/New_York` và quy tắc ngày cụ thể.

**Câu 5.** Vì sao `zdt.plusDays(1)` có thể khác `zdt.plusHours(24)`?  
**Đáp án:** Một ngày lịch có thể dài 23 hoặc 25 giờ ở điểm đổi DST; cộng ngày theo local timeline khác cộng 24 giờ trên instant timeline.

**Câu 6.** Khi `2024-03-10T02:30` tại New York là gap, `atZone` mặc định làm gì?  
**Đáp án:** Giải quyết bằng cách đẩy sang `03:30-04:00` theo độ dài gap. Nếu không chấp nhận policy này, cần validate/resolve nghiêm ngặt.

**Câu 7.** Tại sao `2024-11-03T01:30` tại New York có thể là hai instant?  
**Đáp án:** Đây là overlap khi đồng hồ lùi. Hai offset hợp lệ `-04:00` và `-05:00` định danh hai moment khác nhau.

**Câu 8.** “Chờ đúng 24 giờ” nên dùng `Duration` hay `Period`?  
**Đáp án:** `Duration.ofHours(24)`. `Period.ofDays(1)` là một ngày lịch.

**Câu 9.** “Thêm một tháng” có phải luôn cộng 30 ngày không?  
**Đáp án:** Không. `LocalDate.plusMonths(1)` là phép cộng lịch, có thể điều chỉnh về ngày cuối của tháng kết quả.

**Câu 10.** `YYYY-MM-dd` có phải luôn bằng `uuuu-MM-dd` không?  
**Đáp án:** Không. `YYYY` là week-based-year, có thể khác năm lịch quanh ranh giới năm.

**Câu 11.** Làm sao viết test `LocalDate.now()` ổn định qua ngày?  
**Đáp án:** Inject `Clock` và dùng `LocalDate.now(clock)` với `Clock.fixed(instant, zone)`.

**Câu 12.** API trả epoch `1723692600000` mà không ghi đơn vị có đủ không?  
**Đáp án:** Không. Cần contract xác định seconds/milliseconds; số này trong ví dụ là milliseconds của `2024-08-15T03:30Z`.

**Câu 13.** Có nên mặc định dùng `java.time.chrono` cho mọi dự án quốc tế không?  
**Đáp án:** Không. Thường giữ ISO trong giao tiếp/lưu trữ; chuyển chronology khác khi domain thực sự cần.

**Câu 14.** Khi lấy ngày hiện tại cho người dùng Việt Nam từ một `Instant`, phải làm gì?  
**Đáp án:** Chuyển instant sang `ZoneId.of("Asia/Ho_Chi_Minh")` rồi lấy `toLocalDate()`; không lấy ngày UTC rồi giả định đó là ngày Việt Nam.

## 24. Ghi nhớ

- **JSR 310** là nền tảng của `java.time` có từ Java 8 và **vẫn áp dụng** trong JDK hiện nay.
- **`LocalDate` = ngày lịch; `LocalTime` = giờ địa phương; `LocalDateTime` = ngày+giờ không zone; `Instant` = moment duy nhất.**
- **`ZoneOffset` = độ lệch UTC cố định; `ZoneId` = định danh vùng với các quy tắc lịch sử/DST.** `OffsetDateTime` lưu offset, `ZonedDateTime` giữ region.
- **`Duration` đo giây/nano, `Period` đo năm/tháng/ngày theo lịch.** Qua DST, `plusDays(1)` khác `plusHours(24)`.
- **Date-time objects là immutable/thread-safe/value-based**: nhận bản sao trả về, không dựa vào identity.
- **`Clock`** giúp test thời gian tái lập và giảm phụ thuộc hệ thống; **`DateTimeFormatter`** dùng để format/parse rõ contract và locale.
- Chú ý gap/overlap, `YYYY` vs `uuuu`, epoch unit, zone mặc định, dữ liệu TZDB và loại SQL timestamp.
- Hãy chọn kiểu theo **ngữ nghĩa nghiệp vụ**, không dùng `LocalDateTime`/`Instant` hoán đổi mọi tình huống.

### Tài liệu Java API chính thức, hiện còn áp dụng

- [`java.time` — package tổng quan, ISO calendar, bất biến, thread-safe](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
- [`Instant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html), [`LocalDate`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html), [`LocalDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html)
- [`ZoneId`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html), [`ZoneOffset`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html), [`ZonedDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html), [`OffsetDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html)
- [`ZoneRules`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html) — offset hợp lệ, gap và overlap
- [`Duration`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html) và [`Period`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
- [`DateTimeFormatter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html) — pattern, parser và resolver style
- [`Clock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html) — nguồn thời gian có thể inject/test
- [`ChronoUnit`, `TemporalAdjusters`, `WeekFields`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/package-summary.html)
- [`java.time.chrono`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/package-summary.html) — niên lịch phi ISO khi nghiệp vụ yêu cầu
