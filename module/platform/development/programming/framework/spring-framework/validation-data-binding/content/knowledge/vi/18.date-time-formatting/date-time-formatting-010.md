# Kiểm thử ngày không tồn tại, năm nhuận và thời điểm chuyển giờ trong Spring

## 1. Mục tiêu: kiểm thử cả định dạng, lịch và múi giờ

Dữ liệu ngày giờ đi vào ứng dụng Spring qua query parameter, path variable, form, JSON hoặc cấu hình thường bắt đầu từ chuỗi. Một chuỗi có vẻ đúng mẫu chưa chắc là **ngày có thật**, và một ngày giờ địa phương hợp lệ về lịch chưa chắc là **thời điểm xác định duy nhất** trong một múi giờ.

Ví dụ ba lỗi có bản chất khác nhau:

- `2025-02-29` có đúng dáng `yyyy-MM-dd`, nhưng ngày 29/02/2025 không tồn tại vì 2025 không nhuận.
- `2024-02-29` tồn tại vì 2024 nhuận; parser quá lỏng hoặc kiểm tra sai có thể loại oan trường hợp này.
- `2024-03-10T02:30` là ngày và giờ hợp lệ trong `LocalDateTime`, nhưng **không tồn tại** tại `America/New_York`: đồng hồ chuyển từ 01:59:59 lên 03:00 vào ngày bắt đầu daylight saving time (DST) năm đó.

Một trường hợp khác còn nguy hiểm hơn: `2024-11-03T01:30` xuất hiện **hai lần** tại `America/New_York` khi đồng hồ quay lùi. Nó có thể tương ứng hai `Instant` cách nhau 60 phút. Nếu hệ thống đặt lịch hoặc lưu transaction theo thời điểm, tự chọn một trong hai sẽ tạo hành vi khó giải thích.

Bài học này trình bày cách lập bảng ca kiểm thử, viết bộ test Java 17+, xử lý đầu vào qua Spring MVC, phân biệt parse lỗi với DST gap/overlap, và bảo đảm kết quả ổn định giữa máy lập trình, CI và máy chủ.

## 2. Chọn kiểu dữ liệu trước khi kiểm thử

| Kiểu | Mô tả | Có chịu ảnh hưởng DST khi bản thân được tạo? |
| --- | --- | --- |
| `LocalDate` | Ngày lịch, ví dụ `2024-02-29` | Không: không có giờ hoặc zone |
| `LocalTime` | Giờ địa phương, ví dụ `01:30` | Không: không có ngày hoặc zone |
| `LocalDateTime` | Ngày + giờ địa phương, ví dụ `2024-11-03T01:30` | Chưa: không có zone để đối chiếu |
| `ZoneId` | Vùng với bộ quy tắc lịch sử, ví dụ `America/New_York` | Dùng để xét các chuyển đổi DST |
| `ZoneOffset` | Độ lệch UTC cố định, ví dụ `-04:00` | Không chứa lịch quy tắc đổi giờ |
| `OffsetDateTime` | Local date-time + một offset cố định | Xác định được `Instant`, nhưng offset cần hợp lệ nếu cũng biết region zone |
| `ZonedDateTime` | Ngày giờ + region zone + offset đã được giải quyết | Có; quy tắc zone quyết định chuyển từ local time sang instant |
| `Instant` | Một thời điểm tuyệt đối trên UTC timeline | Không mơ hồ; biểu diễn giờ địa phương phụ thuộc zone |

**Quy tắc thiết kế:** ngày sinh, ngày nghỉ, ngày hết hạn kiểu date-only thường nên là `LocalDate`. Lịch họp tại một thành phố cần thêm `ZoneId` (và đôi khi cần chọn offset trong giờ trùng). Event log hoặc thời gian giao dịch đã xác định nên lưu `Instant`.

`ZoneId.of("America/New_York")` dùng cơ sở dữ liệu quy tắc múi giờ (tzdb); `ZoneOffset.of("-05:00")` chỉ là độ lệch cố định. Không dùng một offset cố định để suy luận mọi giờ địa phương quanh năm tại New York.

## 3. Ngày không tồn tại và quy tắc năm nhuận

Trong lịch ISO/Gregorian proleptic mà `java.time` sử dụng:

1. Năm chia hết cho 4 thường là năm nhuận.
2. Nhưng năm chia hết cho 100 không nhuận.
3. Ngoại lệ: năm chia hết cho 400 vẫn nhuận.

Ví dụ: 2024 và 2000 nhuận; 2025 và 1900 không nhuận. Java cung cấp `Year.isLeap(year)` và `Year.of(year).isLeap()`, vì thế không cần viết lại công thức trong code production.

Một số ca lịch tối thiểu:

| Chuỗi ISO | Kết quả đúng | Lý do |
| --- | --- | --- |
| `2024-02-29` | Hợp lệ | Năm nhuận |
| `2025-02-29` | Không hợp lệ | 2025 không nhuận |
| `2000-02-29` | Hợp lệ | Năm thế kỷ chia hết 400 |
| `1900-02-29` | Không hợp lệ | Năm thế kỷ không chia hết 400 |
| `2024-04-30` | Hợp lệ | Tháng 4 có 30 ngày |
| `2024-04-31` | Không hợp lệ | Tháng 4 không có ngày 31 |
| `2024-13-01` | Không hợp lệ | Tháng 13 không tồn tại |
| `2024-00-10` | Không hợp lệ | Tháng 0 không tồn tại |
| `2024-01-32` | Không hợp lệ | Ngày 32 không tồn tại |
| `2024-12-31` | Hợp lệ | Ngày cuối năm |
| `2025-01-01` | Hợp lệ | Qua ranh giới năm |

Không chỉ kiểm tra dạng chuỗi bằng regex như `\\d{4}-\\d{2}-\\d{2}`. Regex có thể xác nhận bố cục `2025-02-29`, nhưng không biết ngày đó không tồn tại. Chuyển chuỗi thành `LocalDate` với parser nghiêm ngặt mới kiểm tra đủ giới hạn lịch.

### 3.1. STRICT, SMART và LENIENT

JDK `DateTimeFormatter` có ba chế độ giải quyết ngày:

- `ResolverStyle.STRICT`: từ chối ngày không hợp lệ, ví dụ 29/02 năm không nhuận.
- `ResolverStyle.SMART`: có thể điều chỉnh một ngày vượt cuối tháng về ngày cuối tháng; ví dụ 29/02/2025 có thể thành 28/02/2025.
- `ResolverStyle.LENIENT`: cho phép tràn trường và tính bù, phù hợp một số bài toán chuyên biệt nhưng nguy hiểm cho dữ liệu người dùng cần tính chính xác.

Một điểm dễ bỏ sót: `DateTimeFormatter.ofPattern("uuuu-MM-dd")` có **resolver style mặc định là SMART**. Ngược lại, `DateTimeFormatter.ISO_LOCAL_DATE` là formatter ISO có **resolver style STRICT**. Đừng kết luận tất cả cách parse ngày trong Java đều strict chỉ vì ví dụ `LocalDate.parse("2025-02-29")` mặc định đã lỗi.

Ví dụ fragment Java:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

DateTimeFormatter smart = DateTimeFormatter.ofPattern("uuuu-MM-dd");
DateTimeFormatter strict = smart.withResolverStyle(ResolverStyle.STRICT);

System.out.println(LocalDate.parse("2025-02-29", smart));
// 2025-02-28: SMART điều chỉnh ngày cuối tháng

LocalDate.parse("2025-02-29", strict);
// Ném DateTimeParseException: STRICT không chấp nhận ngày đó
```

Nếu cần một pattern tùy chỉnh như `dd/MM/uuuu`, tạo formatter strict rõ ràng:

```java
DateTimeFormatter dateFormat = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);
```

Ở `java.time.DateTimeFormatter`, `uuuu` là năm theo thang proleptic; `yyyy` là *year-of-era*. Dùng `yyyy` với resolver strict mà không cung cấp era có thể khiến ngày bình thường cũng parse thất bại. Đối với pattern Java Time strict có năm thông thường, `uuuu` thường ít gây bất ngờ hơn.

Lưu ý: `@DateTimeFormat(pattern = "...")` của Spring có xử lý pattern và ngữ nghĩa parser riêng tùy kiểu đích/phiên bản Spring; kiểm thử hợp đồng Spring thực tế thay vì suy ra y nguyên từ mọi factory method JDK.

## 4. DST: gap, overlap và thời gian bình thường

`ZoneRules.getValidOffsets(LocalDateTime)` cho biết những offset thực sự được phép tại ngày giờ địa phương trong một `ZoneId`:

| Kết quả | Ý nghĩa | Hành động với ứng dụng cần lịch chính xác |
| --- | --- | --- |
| 0 offset | **Gap**: giờ địa phương không tồn tại do đồng hồ nhảy tới | Từ chối và yêu cầu chọn giờ khác, hoặc chính sách điều chỉnh được công bố rõ |
| 1 offset | **Normal**: xác định duy nhất một instant | Có thể chuyển bằng offset hợp lệ |
| 2 offset | **Overlap**: giờ địa phương lặp lại khi đồng hồ quay lui | Hỏi người dùng/nhận offset trong request hoặc chọn chính sách sớm/muộn tường minh |

Các ví dụ cố định dưới đây lấy từ quy tắc `America/New_York` năm 2024, tránh phụ thuộc giờ hiện tại của máy chạy:

- **Gap:** ngày 10/03/2024, sau 01:59:59 giờ địa phương là 03:00:00. `2024-03-10T02:30` không có offset hợp lệ.
- **Overlap:** ngày 03/11/2024, đồng hồ từ 02:00 daylight time quay về 01:00 standard time. `2024-11-03T01:30` có offset `-04:00` và `-05:00`.
- **Normal:** `2024-03-10T01:30` có offset `-05:00`; `2024-03-10T03:30` có offset `-04:00`.

### 4.1. Vì sao dùng atZone() một mình không đủ để phát hiện lỗi?

`LocalDateTime.atZone(zone)` thường cố giải quyết ngày giờ: với gap, nó **đẩy giờ lên** theo độ dài khoảng chuyển đổi; với overlap, nó thường chọn **offset sớm hơn**. Tức là:

```java
var zone = java.time.ZoneId.of("America/New_York");
var gap = java.time.LocalDateTime.of(2024, 3, 10, 2, 30);
System.out.println(gap.atZone(zone).toLocalDateTime());
// 2024-03-10T03:30
```

Đây là hành vi được JDK định nghĩa, nhưng không nhất thiết hợp đồng nghiệp vụ mong muốn. Với đơn đặt chỗ 02:30, im lặng đổi thành 03:30 có thể sai. Muốn **không tự dịch giờ** và **không tự chọn trong overlap**, hãy tra `getValidOffsets(local)` trước khi tạo `ZonedDateTime`.

### 4.2. Hai instant cho một giờ trùng

Ở `America/New_York`:

| Local datetime | Offset | Instant UTC |
| --- | --- | --- |
| `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

Hai mốc UTC chênh nhau **60 phút**. Với một hệ thống cần duy nhất thời điểm, client có thể gửi `OffsetDateTime` chứa offset hoặc gửi thêm lựa chọn `early/later`; ứng dụng cần đối chiếu offset với `ZoneRules` của zone đã chọn.

**Không phải nơi nào cũng đổi DST.** `Asia/Ho_Chi_Minh` không có kỳ chuyển DST thường niên hiện nay, nhưng dùng `America/New_York` trong test sẽ chứng minh được cơ chế gap/overlap, kể cả khi CI chạy tại Việt Nam. Các quy tắc zone có thể được cập nhật theo tzdb; nên ghi nhận phiên bản JDK/tzdb nếu test liên quan tương lai xa hoặc quốc gia thay đổi luật giờ.

## 5. Ví dụ Java 17+ độc lập, kết quả xác định

Tạo file **`TemporalEdgeCaseDemo.java`** với nội dung đầy đủ dưới đây (chỉ dùng thư viện JDK):

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.zone.ZoneRules;
import java.util.Locale;

public class TemporalEdgeCaseDemo {

    private static final DateTimeFormatter STRICT_DMY =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static void checkDate(String text) {
        try {
            System.out.println(text + " -> "
                    + LocalDate.parse(text, STRICT_DMY));
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> INVALID");
        }
    }

    public static void main(String[] args) {
        System.out.println("2024 leap=" + Year.isLeap(2024));
        System.out.println("2025 leap=" + Year.isLeap(2025));
        System.out.println("1900 leap=" + Year.isLeap(1900));
        System.out.println("2000 leap=" + Year.isLeap(2000));

        checkDate("29/02/2024");
        checkDate("29/02/2025");
        checkDate("31/04/2024");

        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("gap-offset-count="
                + rules.getValidOffsets(gap).size());
        System.out.println("atZone-adjusted="
                + gap.atZone(newYork).toLocalDateTime());

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        System.out.println("overlap-offsets="
                + rules.getValidOffsets(overlap));

        ZonedDateTime early = overlap.atZone(newYork);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();

        System.out.println("overlap-early=" + early.getOffset());
        System.out.println("overlap-late=" + late.getOffset());
        System.out.println("instant-difference-minutes="
                + Duration.between(early.toInstant(), late.toInstant())
                        .toMinutes());
    }
}
```

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

```bash
javac TemporalEdgeCaseDemo.java
java TemporalEdgeCaseDemo
```

Stdout dự kiến với quy tắc tzdb New York thông thường cho năm 2024:

```text
2024 leap=true
2025 leap=false
1900 leap=false
2000 leap=true
29/02/2024 -> 2024-02-29
29/02/2025 -> INVALID
31/04/2024 -> INVALID
gap-offset-count=0
atZone-adjusted=2024-03-10T03:30
overlap-offsets=[-04:00, -05:00]
overlap-early=-04:00
overlap-late=-05:00
instant-difference-minutes=60
```

Giải thích: `checkDate` dùng strict resolver nên **không có phép tự sửa ngày**. Hai phép `getValidOffsets` phân biệt gap và overlap một cách tường minh. `atZone` trong ví dụ chỉ để **chứng minh hành vi tự điều chỉnh/chọn offset** của API Java; với nghiệp vụ cần bắt lỗi, không dùng kết quả này làm bước kiểm tra duy nhất.

Nếu cần giữ đúng local datetime và offset, `ZonedDateTime.ofStrict(local, offset, zone)` xác nhận offset được phép theo quy tắc zone; nó ném `DateTimeException` nếu kết hợp không hợp lệ.

## 6. Cách thiết kế lớp kiểm tra có thể tái sử dụng

Với tính năng đặt lịch, ta có thể chủ động từ chối cả gap và overlap, buộc người dùng cung cấp một giá trị không mơ hồ. Đây là **một chính sách nghiệp vụ cụ thể**, không phải chính sách mặc định duy nhất của Spring hoặc Java.

**File `src/main/java/com/example/calendar/StrictAppointmentTime.java`:**

```java
package com.example.calendar;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

public final class StrictAppointmentTime {
    private StrictAppointmentTime() {}

    public static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets = rules.getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in zone: " + local);
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Local time is ambiguous in zone: " + local);
        }

        // Một offset duy nhất, được xác thực bởi ZoneRules.
        return ZonedDateTime.ofStrict(local, offsets.get(0), zone);
    }
}
```

Ở đây:
- `offsets.isEmpty()` biểu diễn giờ không tồn tại do DST gap.
- `offsets.size() > 1` biểu diễn giờ bị lặp do DST overlap.
- `ofStrict` buộc đúng kết hợp local datetime, zone, offset.
- Code không gọi `LocalDateTime.now()`, không sử dụng timezone mặc định của JVM; kiểm thử có thể xác định kết quả.

Khi muốn **hỗ trợ** giờ bị trùng thay vì từ chối, đổi API để nhận offset hoặc sự lựa chọn cụ thể. Ví dụ offset `-04:00` và `-05:00` đều hợp lệ cho `2024-11-03T01:30` ở New York; client cần chỉ rõ một trong hai. Nếu offset không thuộc `rules.getValidOffsets(local)`, báo lỗi thay vì âm thầm thay offset.

## 7. Unit test JUnit 5: bao phủ ngày vô lý, nhuận, gap, overlap

**File `src/test/java/com/example/calendar/TemporalRulesTest.java`:**

```java
package com.example.calendar;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TemporalRulesTest {

    private static final DateTimeFormatter STRICT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void leapYearAndCenturyRules() {
        assertTrue(Year.isLeap(2024));
        assertFalse(Year.isLeap(2025));
        assertFalse(Year.isLeap(1900));
        assertTrue(Year.isLeap(2000));

        assertEquals(LocalDate.of(2024, 2, 29),
                LocalDate.parse("29/02/2024", STRICT));
        assertEquals(LocalDate.of(2000, 2, 29),
                LocalDate.parse("29/02/2000", STRICT));
    }

    @Test
    void rejectsImpossibleCalendarDates() {
        for (String input : List.of(
                "29/02/2025",
                "29/02/1900",
                "31/04/2024",
                "32/01/2024",
                "10/13/2024")) {

            assertThrows(DateTimeParseException.class,
                    () -> LocalDate.parse(input, STRICT),
                    "Should reject: " + input);
        }
    }

    @Test
    void detectsDaylightSavingGap() {
        var gap = LocalDateTime.of(2024, 3, 10, 2, 30);

        assertTrue(NEW_YORK.getRules()
                .getValidOffsets(gap).isEmpty());

        assertThrows(IllegalArgumentException.class,
                () -> StrictAppointmentTime.resolve(gap, NEW_YORK));

        // atZone() sẽ tự dời giờ lên 03:30,
        // do đó không thể dùng riêng atZone() để chứng minh giờ hợp lệ.
        assertEquals(LocalDateTime.of(2024, 3, 10, 3, 30),
                gap.atZone(NEW_YORK).toLocalDateTime());
    }

    @Test
    void detectsDaylightSavingOverlap() {
        var overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        var offsets = NEW_YORK.getRules().getValidOffsets(overlap);

        assertEquals(List.of(
                ZoneOffset.ofHours(-4),
                ZoneOffset.ofHours(-5)), offsets);

        assertThrows(IllegalArgumentException.class,
                () -> StrictAppointmentTime.resolve(overlap, NEW_YORK));

        ZonedDateTime early = overlap.atZone(NEW_YORK);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();

        assertEquals(Instant.parse("2024-11-03T05:30:00Z"),
                early.toInstant());
        assertEquals(Instant.parse("2024-11-03T06:30:00Z"),
                late.toInstant());
        assertEquals(60,
                Duration.between(early.toInstant(), late.toInstant())
                        .toMinutes());
    }

    @Test
    void resolvesUnambiguousTime() {
        var local = LocalDateTime.of(2024, 3, 10, 1, 30);
        var resolved = StrictAppointmentTime.resolve(local, NEW_YORK);

        assertEquals(ZoneOffset.ofHours(-5), resolved.getOffset());
        assertEquals(Instant.parse("2024-03-10T06:30:00Z"),
                resolved.toInstant());
    }
}
```

Đây là JUnit 5 thực thi trong **dự án có dependency JUnit Jupiter**; tên package phải khớp file `StrictAppointmentTime` phía trên. Test không cần server hay database. Nếu ứng dụng dùng Gradle với cấu hình test JUnit Platform chuẩn, chạy task test tương ứng; với dự án Java đơn giản, JUnit vẫn cần được đưa vào test classpath.

Phân loại assertion theo tầng:
- Test **calendar** xác minh ngày có thật và ranh giới năm nhuận.
- Test **DST** xác minh 0/1/2 offset và chính sách từ chối gap/overlap.
- Test **instant** xác minh mốc UTC cụ thể, không chỉ chuỗi hiển thị.
- Test **độc lập môi trường** không đổi timezone máy; luôn truyền `ZoneId` và sử dụng thời gian cố định.

## 8. Kiểm thử khi dữ liệu đi qua Spring MVC

Nếu query parameter mang kiểu `LocalDate` hoặc `LocalDateTime`, Spring MVC sẽ parse chuỗi qua cơ chế formatting/data binding. Có thể dùng `@DateTimeFormat(iso = ...)` để chỉ rõ hợp đồng đầu vào.

Ví dụ controller có hai endpoint, minh họa **ngày lịch** và **giờ hẹn tại zone được chỉ định**.

**File `src/main/java/com/example/calendar/CalendarController.java`:**

```java
package com.example.calendar;

import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CalendarController {

    @GetMapping("/calendar/date")
    public String date(
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {
        return day.toString();
    }

    @GetMapping("/calendar/appointment")
    public String appointment(
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            LocalDateTime local,
            @RequestParam String zone) {

        ZoneId zoneId;
        try {
            zoneId = ZoneId.of(zone);
        } catch (DateTimeException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid zone");
        }

        try {
            ZonedDateTime resolved =
                    StrictAppointmentTime.resolve(local, zoneId);
            return resolved.toInstant().toString();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Nonexistent or ambiguous local time", ex);
        }
    }
}
```

Controller này yêu cầu dự án Spring MVC có dependency Web và component scan bao phủ package trên; nó **không** phải một chương trình chạy độc lập bằng `javac`. Với `StrictAppointmentTime` đã tạo, hợp đồng mong đợi là:

| Request | Kết quả |
| --- | --- |
| `GET /calendar/date?day=2024-02-29` | 200, body `2024-02-29` |
| `GET /calendar/date?day=2025-02-29` | 400 do parse/bind ngày không hợp lệ |
| `GET /calendar/date?day=2024-04-31` | 400 do parse/bind ngày không hợp lệ |
| `GET /calendar/appointment?local=2024-03-10T01:30:00&zone=America/New_York` | 200, body `2024-03-10T06:30:00Z` |
| `GET /calendar/appointment?local=2024-03-10T02:30:00&zone=America/New_York` | 400 do gap, do logic nghiệp vụ tự kiểm tra |
| `GET /calendar/appointment?local=2024-11-03T01:30:00&zone=America/New_York` | 400 do overlap, do logic nghiệp vụ tự kiểm tra |
| `GET /calendar/appointment?local=2024-11-03T01:30:00&zone=Invalid/Zone` | 400 do zone không hợp lệ |

**Phân biệt hai lớp lỗi:** Khi `@DateTimeFormat` không tạo được `LocalDate`, Spring MVC xử lý lỗi chuyển kiểu ở bước binding (thông thường HTTP 400 với `@RequestParam`). Trong khi đó, `2024-03-10T02:30:00` **vẫn là LocalDateTime hợp lệ**; parser date-time có thể bind thành công, nhưng chính ứng dụng phải kiểm tra `ZoneRules` và trả 400 cho gap. Tương tự, giờ trùng không phải một ngày giờ sai cú pháp: cần chính sách chọn/từ chối overlap.

### 8.1. Khi dùng @ModelAttribute và BindingResult

Giả sử form có một `LocalDate`: nếu chuỗi có sai định dạng hoặc ngày không có thật, lỗi chuyển đổi có thể được đưa vào `BindingResult` với mã như `typeMismatch`. Bean Validation `@NotNull`, `@Future` hoặc `@Past` kiểm tra giá trị **sau khi chuyển đổi được**; các annotation này không tự nhận biết gap/overlap trên một `LocalDateTime` thiếu zone.

Ví dụ `@Future` trên `LocalDateTime` còn phụ thuộc clock hiện tại, nên không dùng nó làm bằng chứng ngày lịch/zone hợp lệ. Để kiểm thử `@Future` một cách ổn định, cần kiểm soát clock/cấu hình validation thích hợp, thay vì dựa vào thời gian thật tại CI.

### 8.2. JSON có cùng logic parse không?

Không mặc định. `@RequestBody` JSON thường được Jackson deserialize theo cấu hình `ObjectMapper` và Java Time module. `@DateTimeFormat` thuộc Spring formatting dành cho binding; `@JsonFormat` thuộc Jackson. Vì vậy hãy có **bộ test riêng cho JSON** nếu endpoint nhận JSON.

Một JSON chứa `{"local":"2024-03-10T02:30:00","zone":"America/New_York"}` có thể tạo `LocalDateTime` và `String` hợp lệ ở tầng deserialize; quy tắc kiểm tra DST vẫn phải được gọi ở tầng nghiệp vụ.

## 9. Lập ma trận kiểm thử trước khi viết code

Một ma trận kiểm thử đầy đủ cần xét tối thiểu ba chiều độc lập:

### Chiều A: tính hợp lệ của ngày lịch

| Phân nhóm | Ví dụ | Assertion |
| --- | --- | --- |
| Ngày bình thường | 15/06/2024 | Parse thành `LocalDate.of(2024,6,15)` |
| Ranh giới cuối tháng | 30/04/2024; 31/04/2024 | Một giá trị pass, một giá trị fail |
| Năm nhuận | 29/02/2024 | Pass |
| Năm không nhuận | 29/02/2025 | Fail |
| Quy tắc 100/400 | 29/02/1900; 29/02/2000 | Fail rồi pass |
| Sai miền số | Tháng 00, 13; ngày 00, 32 | Fail |
| Sai pattern | 2024/02/29 khi chỉ cho `dd/MM/uuuu` | Fail |
| Dữ liệu rỗng / null | `""`, `null` | Test tách riêng theo hợp đồng API |
| Dư khoảng trắng | `" 29/02/2024 "` | Test rõ chính sách `trim`/không trim |

### Chiều B: kết hợp giờ địa phương với múi giờ

| Phân nhóm | Ví dụ | Assertion |
| --- | --- | --- |
| Giờ thường trước đổi DST | New York 2024-03-10 01:30 | Một offset `-05:00` |
| Gap | New York 2024-03-10 02:30 | Không có offset; từ chối theo chính sách strict |
| Giờ thường sau gap | New York 2024-03-10 03:30 | Một offset `-04:00` |
| Overlap | New York 2024-11-03 01:30 | Hai offset, `-04:00` và `-05:00` |
| Giờ thường sau overlap | New York 2024-11-03 02:30 | Một offset `-05:00` |
| Region không dùng DST thường niên hiện nay | Ho Chi Minh 2024-03-10 02:30 | Kiểm tra theo quy tắc region, không tự áp quy tắc New York |
| Zone ID sai | `Invalid/Zone` | Lỗi rõ, không thay bằng mặc định |

### Chiều C: điểm tiếp nhận dữ liệu

- **Unit:** gọi `LocalDate.parse`, `Year.isLeap` và `ZoneRules.getValidOffsets`.
- **Spring formatting:** kiểm tra `ConversionService`/`@DateTimeFormat` được cấu hình thật sự.
- **MVC integration:** kiểm tra status/body HTTP với `MockMvc` cho query/form, đặc biệt 400 khi parse hoặc validation fail.
- **JSON integration:** kiểm tra Jackson deserialize và chính sách nghiệp vụ đối với body JSON.
- **Persistence:** xác minh lưu `Instant`/offset/zone không làm mất thông tin cần thiết, và đọc lại vẫn tái tạo đúng lịch hẹn.

Ma trận nên dùng cùng các fixture cố định ở nhiều tầng, nhưng mỗi tầng phải kiểm tra trách nhiệm của chính nó. Không viết test chỉ đơn giản lặp lại code implementation mà không chứng minh quy tắc hoặc hành vi người dùng thấy được.

## 10. Mẹo kiểm thử với đồng hồ, locale và timezone của hệ thống

### 10.1. Tránh ngày giờ hiện tại

Không dùng `LocalDate.now()` hoặc `ZonedDateTime.now()` làm dữ liệu khẳng định trong test ranh giới lịch/DST: cùng một test có thể chạy khác hôm nay, qua nửa đêm hoặc khi CI đặt timezone khác. Sử dụng ngày tuyệt đối như năm 2024 hoặc tạo `Clock.fixed(Instant.parse(...), zone)` cho code chủ động sử dụng clock.

### 10.2. Không dựa vào timezone mặc định

`ZoneId.systemDefault()` phụ thuộc máy. Với một test nghiệp vụ, truyền `ZoneId.of("America/New_York")` hoặc zone trong hợp đồng. Thay đổi toàn cục `TimeZone.setDefault(...)` trong test chạy song song dễ ảnh hưởng ca khác. Tránh điều đó nếu có thể.

### 10.3. Ghi nhận giới hạn dữ liệu tzdb

Luật đổi giờ do chính phủ quyết định và có thể thay đổi. JDK phân phối phiên bản tzdb; quy tắc lịch sử 2024 của New York là fixture ổn định để dạy gap/overlap. Nếu hệ thống phải đặt lịch nhiều năm về sau, cần lưu zone ID và chọn cách ứng xử khi bộ quy tắc được cập nhật; không chỉ lưu một offset tính sẵn nhiều năm trước.

### 10.4. Locale và pattern

`05/11/2024` có thể được hiểu là 5/11 hoặc 11/5 tùy pattern/locale. Chọn ISO `yyyy-MM-dd` cho giao tiếp máy, dùng pattern rõ ràng cho giao diện đã thỏa thuận. `DateTimeFormatter.ofPattern(..., Locale.ROOT)` giảm phụ thuộc locale trong một số pattern, nhưng không thay thế việc chỉ ra thứ tự ngày/tháng/năm. Các style phụ thuộc dữ liệu locale/JDK có thể thay đổi; dùng format ổn định cho API và assertion.

### 10.5. DateFormatter (legacy) khác java.time

Khi tầng cũ dùng `java.util.Date` hoặc `SimpleDateFormat`, cần nhớ `SimpleDateFormat` mặc định **lenient=true** nếu không cấu hình. Nó có thể tự điều chỉnh ngày sai. Muốn từ chối ngày không tồn tại, đặt `setLenient(false)`, chọn timezone rõ và không chia sẻ một instance `SimpleDateFormat` mutable giữa threads. Đối với code Java hiện đại, ưu tiên `java.time` immutable và strict resolver.

Đừng kết luận từ test parser legacy rằng bộ converter `LocalDate` hoặc Spring MVC trong ứng dụng có cùng hành vi. Kiểm tra đúng đường đi của input.

## 11. Các sai lầm thường gặp

1. **Chỉ check regex:** `2025-02-29` vẫn lọt qua biểu thức kiểm tra `yyyy-MM-dd`.
2. **Quên năm thế kỷ:** điều kiện `year % 4 == 0` phân loại sai năm 1900.
3. **Dùng formatter SMART để xác nhận giá trị nhập:** ngày sai có thể biến thành ngày cuối tháng mà không gây lỗi.
4. **Dùng pattern `yyyy` với strict resolver Java Time mà quên era:** dữ liệu ngày bình thường có thể fail; cân nhắc `uuuu`.
5. **Tin rằng LocalDateTime đã biết múi giờ:** `LocalDateTime` không chứa zone/offset, nên không tự biết DST gap/overlap.
6. **Gọi `atZone()` rồi coi mọi kết quả là hợp lệ:** API có thể đẩy giờ gap lên hoặc chọn một offset trong overlap.
7. **Lưu một offset cố định thay cho zone region:** DST/lịch sử của region có thể khác trong tương lai.
8. **Để CI dùng default timezone:** test qua máy khác sẽ thay đổi kết quả và rất khó tái hiện.
9. **Kiểm thử Spring query nhưng bỏ qua JSON:** MVC formatter và Jackson là hai luồng giải mã khác nhau.
10. **Coi mọi lỗi là Bean Validation:** sai lịch có thể bị từ chối ngay ở conversion, còn DST cần validation/nghiệp vụ có zone.
11. **Không kiểm tra hai instant ở overlap:** so sánh chuỗi `01:30` che giấu khoảng cách 60 phút.
12. **Test chỉ một ngày 29/02:** phải có năm thường, năm chia hết 100 và 400 để xác nhận đúng quy tắc nhuận.

## 12. Checklist hoàn thành một bộ test ngày giờ

1. Xác định giá trị là ngày lịch, giờ địa phương, offset date-time hay instant.
2. Chỉ rõ format nhận vào, `Locale`, `ZoneId` và chính sách xử lý chuỗi trống/không đúng pattern.
3. Test ngày hợp lệ, cuối tháng, ngày không tồn tại và đầy đủ trường hợp năm nhuận đặc biệt.
4. Nếu cần parse nghiêm ngặt, dùng `ResolverStyle.STRICT` hoặc formatter chuẩn đã xác minh strict; không để SMART tự sửa ngày sai.
5. Với lịch theo region zone, gọi `ZoneRules.getValidOffsets` để phát hiện riêng normal/gap/overlap; thực hiện chính sách nghiệp vụ có thể giải thích và kiểm thử.
6. So sánh `Instant` khi xác nhận thời điểm; kiểm tra cả offset và zone ID nếu giao diện phải giữ nguyên ý định người đặt lịch.
7. Viết unit test JDK và integration test Spring MVC/JSON tương ứng nguồn dữ liệu thật.
8. Làm test độc lập ngày chạy, timezone mặc định và locale của máy; ghi nhận JDK/tzdb cho những test liên quan thay đổi lịch tương lai.

### Tài liệu tham khảo

- [Java 21 — Year.isLeap (quy tắc năm nhuận)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html).
- [Java 21 — ResolverStyle: STRICT, SMART, LENIENT](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).
- [Java 21 — DateTimeFormatter: parse và resolver style](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java 21 — ZoneRules.getValidOffsets và getTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html).
- [Java 21 — ZonedDateTime và xử lý gap/overlap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html).
- [Spring Framework — @DateTimeFormat](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html).
- [Spring Framework — Type Conversion trong MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- [Spring Framework — Date and Time Formatting with JDK 20 and higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher).
