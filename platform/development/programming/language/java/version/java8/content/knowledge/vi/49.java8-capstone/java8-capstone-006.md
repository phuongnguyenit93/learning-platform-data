# Lịch hẹn nhiều múi giờ với Clock và DateTimeFormatter

**Chủ đề cha:** Thực hành. **Đề bài:** Thiết kế lịch hẹn giữa người dùng ở nhiều múi giờ bằng API hiện đại trong gói `java.time`. Bài tập trung vào `Instant`, `LocalDateTime`, `ZonedDateTime`, `ZoneId`, `ZoneRules`, `Clock` và `DateTimeFormatter`; xử lý chuyển đổi giờ địa phương, giờ mùa hè (DST), lịch hẹn lặp lại, định dạng theo ngôn ngữ và kiểm thử thời gian một cách xác định.

**Phiên bản:** Các API ngày giờ được trình bày có từ **Java 8** và vẫn được hỗ trợ trên JDK hiện hành. Chương trình mẫu dùng cú pháp Java 17+, nhưng các lớp `Clock`, `Instant`, `ZoneId`, `ZonedDateTime` và `DateTimeFormatter` đều thuộc API Java 8.

> **Quy tắc cốt lõi:** Một cuộc hẹn đã xác nhận cần một thời điểm duy nhất trên dòng thời gian (`Instant`). Mỗi người tham gia xem thời điểm đó theo múi giờ của họ (`ZoneId`). Nếu người dùng nhập giờ địa phương cho một ngày trong tương lai, ứng dụng phải xử lý rõ ràng trường hợp giờ đó không tồn tại hoặc xuất hiện hai lần khi đồng hồ đổi giờ. `Clock` giúp kiểm soát nguồn thời gian khi chạy và khi kiểm thử; `DateTimeFormatter` giúp hiển thị/parsing ngày giờ theo locale và múi giờ đã chọn.

## 1. Bài toán lịch hẹn nhiều múi giờ

Giả sử người tổ chức ở Thành phố Hồ Chí Minh đặt cuộc họp lúc 09:00 ngày 06-11-2026. Một người tham gia ở New York cần biết cuộc họp diễn ra lúc mấy giờ tại địa phương của họ.

Không thể chỉ cộng hoặc trừ một số giờ cố định, vì chênh lệch múi giờ có thể thay đổi theo ngày. New York áp dụng giờ mùa hè trong một phần năm; Thành phố Hồ Chí Minh không đổi giờ theo mùa. Một cuộc họp vào tháng 7 và một cuộc họp vào tháng 12 có thể có độ lệch khác nhau.

Quy trình đúng:

1. Nhận ngày/giờ địa phương người tổ chức muốn đặt.
2. Nhận mã múi giờ vùng của người tổ chức.
3. Kiểm tra giờ địa phương có hợp lệ theo quy tắc múi giờ tại ngày đó không.
4. Giải quyết DST gap/overlap theo chính sách đã công bố.
5. Chuyển thành một `Instant` để lưu và so sánh.
6. Hiển thị cùng `Instant` trong `ZoneId` của từng người tham gia.
7. Định dạng kết quả bằng `DateTimeFormatter` và `Locale` phù hợp.

Ví dụ ngày 06-11-2026:

| Người xem | Múi giờ | Giờ địa phương |
| --- | --- | --- |
| Người tổ chức | `Asia/Ho_Chi_Minh` | 09:00, 06-11-2026 |
| Người tham gia | `America/New_York` | 21:00, 05-11-2026 |
| Dòng thời gian chuẩn | UTC | 02:00, 06-11-2026 |

Cả hai giờ địa phương cùng biểu diễn một thời điểm: `2026-11-06T02:00:00Z`. Không tạo hai cuộc họp khác nhau cho hai người.

## 2. Phân biệt các kiểu ngày giờ trong java.time

Mỗi kiểu biểu diễn một khái niệm riêng. Chọn đúng kiểu quan trọng hơn việc chọn một formatter đẹp.

| Kiểu | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `Instant` | Một điểm duy nhất trên dòng thời gian UTC | Thời điểm cuộc hẹn đã xác nhận, timestamp sự kiện, so sánh thời điểm |
| `LocalDate` | Ngày lịch, không có giờ và múi giờ | Ngày nghỉ, ngày sinh, ngày trên lịch |
| `LocalTime` | Giờ trên đồng hồ, không có ngày và múi giờ | Giờ mở cửa, giờ bắt đầu ca |
| `LocalDateTime` | Ngày và giờ địa phương, không có múi giờ/offset | Dữ liệu người dùng nhập trước khi giải quyết múi giờ |
| `ZoneId` | ID múi giờ, thường gắn với quy tắc của một vùng địa lý | `Asia/Ho_Chi_Minh`, `America/New_York` |
| `ZoneOffset` | Độ lệch cụ thể so với UTC, ví dụ `+07:00` | Offset đã được xác định tại một thời điểm |
| `OffsetDateTime` | Ngày giờ địa phương kèm offset cố định | Timestamp có offset nhưng không cần quy tắc vùng |
| `ZonedDateTime` | Ngày giờ địa phương, offset và múi giờ vùng | Hiển thị/biểu diễn giờ theo quy tắc một vùng |

### 2.1. Instant là chuẩn chung để so sánh và lưu thời điểm đã chốt

`Instant` không có múi giờ hiển thị. Nó biểu diễn số giây và phần nano giây tính từ epoch UTC 1970-01-01T00:00:00Z.

```java
Instant meeting = Instant.parse("2026-11-06T02:00:00Z");

ZonedDateTime inHcm =
        meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime inNewYork =
        meeting.atZone(ZoneId.of("America/New_York"));

System.out.println(inHcm);
System.out.println(inNewYork);
```

Cả hai `ZonedDateTime` có cùng `toInstant()`. Khi so sánh thời điểm, dùng `Instant` hoặc các phép so sánh theo instant; không so sánh hai chuỗi giờ địa phương.

### 2.2. LocalDateTime chưa xác định được một thời điểm

`LocalDateTime` chỉ chứa ngày và giờ trên lịch. Giá trị `2026-11-01T01:30` có thể:
- Tương ứng với một thời điểm nếu múi giờ đang có đúng một offset.
- Không tương ứng với thời điểm nào nếu đồng hồ bỏ qua giờ đó.
- Tương ứng với hai thời điểm nếu đồng hồ quay lùi và lặp lại giờ đó.

Vì thế, không lưu một `LocalDateTime` đơn lẻ làm định danh duy nhất cho cuộc hẹn đã xác nhận. Cần thêm `ZoneId` và giải quyết quy tắc của vùng đó.

### 2.3. ZoneId vùng khác với ZoneOffset cố định

`ZoneOffset.of("+07:00")` luôn biểu diễn offset +07:00. Nó không chứa lịch sử hoặc quy tắc DST của một vùng địa lý.

`ZoneId.of("Asia/Ho_Chi_Minh")` xác định một vùng có quy tắc múi giờ được cung cấp bởi `ZoneRulesProvider`. Với một thời điểm cụ thể, quy tắc vùng xác định offset phù hợp.

Dùng ID vùng khi người dùng chọn một địa điểm hoặc khi cần lịch hẹn lặp lại theo giờ địa phương. Dùng offset khi giao thức thực sự chỉ cung cấp offset tại một thời điểm.

Không dùng tên viết tắt như `CST`, `IST` hoặc `EST` để lưu lựa chọn múi giờ. Một chữ viết tắt có thể được dùng ở nhiều vùng với nghĩa khác nhau và không thể thay thế một ID vùng có quy tắc đầy đủ.

## 3. Chuyển đổi giữa các múi giờ

### 3.1. Từ giờ địa phương sang thời điểm

Khi người dùng chọn 09:00 tại Thành phố Hồ Chí Minh:

```java
LocalDateTime requested =
        LocalDateTime.of(2026, 11, 6, 9, 0);

ZoneId organizerZone =
        ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime organizerTime =
        requested.atZone(organizerZone);

Instant meetingInstant = organizerTime.toInstant();
```

Đối với ngày và giờ thông thường, vùng có một offset hợp lệ và phép chuyển đổi xác định được một instant.

`ZonedDateTime.of(localDateTime, zone)` và `LocalDateTime.atZone(zone)` là cách thuận tiện để tạo ngày giờ có vùng. Tuy nhiên, các factory này có chính sách tự giải quyết DST gap/overlap mặc định. Với lịch hẹn do người dùng nhập, thường nên kiểm tra tính hợp lệ và yêu cầu lựa chọn rõ ràng trước khi xác nhận.

### 3.2. Từ một Instant sang giờ của người tham gia

```java
ZoneId attendeeZone =
        ZoneId.of("America/New_York");

ZonedDateTime attendeeTime =
        meetingInstant.atZone(attendeeZone);
```

Đây là phép chuyển đổi an toàn: instant giữ nguyên, chỉ cách hiển thị theo vùng thay đổi.

Nếu có nhiều người tham gia, thực hiện cùng phép chuyển đổi với từng `ZoneId`. Không cộng/trừ giờ bằng tay và không tái tạo instant từ giờ hiển thị của từng người.

### 3.3. Dùng cùng một instant cho mọi người tham gia

Một hệ thống đặt lịch nên có một trường thời điểm chuẩn, ví dụ:

```java
record Appointment(
        Instant startsAt,
        Instant endsAt,
        String organizerZoneId,
        String requestedLocalDateTime,
        String selectedOffset) {
}
```

Các trường bổ sung lưu lại lựa chọn của người tổ chức để hiển thị/audit. `startsAt` và `endsAt` vẫn là nguồn sự thật để xác định thời điểm cuộc hẹn đã chốt.

Khi hiển thị:
- Chuyển `startsAt` sang vùng người đang xem.
- Định dạng giờ địa phương, offset và ID vùng.
- Có thể hiển thị thêm giờ của người tổ chức nếu cuộc họp có nhiều bên.
- Luôn thể hiện ngày tháng đầy đủ khi cuộc họp rơi vào ngày trước hoặc ngày sau tại một vùng khác.

## 4. Daylight Saving Time: gap và overlap

Một múi giờ vùng không nhất thiết có offset cố định quanh năm. Khi quy tắc đổi giờ, việc ánh xạ từ `LocalDateTime` sang `Instant` có thể có ba trường hợp.

### 4.1. Normal: một offset hợp lệ

Trong phần lớn thời gian, một giờ địa phương chỉ có một offset hợp lệ.

Ví dụ: `2026-11-06T09:00` tại `America/New_York` có một offset hợp lệ theo quy tắc ngày đó.

### 4.2. Gap: không tồn tại giờ địa phương được yêu cầu

Khi đồng hồ nhảy tiến, một đoạn giờ địa phương bị bỏ qua. Ví dụ tại New York ngày 08-03-2026, đồng hồ chuyển từ 01:59:59 sang 03:00:00. Giờ 02:30 không tồn tại.

`LocalDateTime` `2026-03-08T02:30` tại `America/New_York` có **0 offset hợp lệ**.

Nếu ứng dụng tự động đổi 02:30 thành 03:30, người dùng có thể không nhận ra cuộc hẹn đã thay đổi. Chính sách cần chọn một trong các cách:
- Từ chối và yêu cầu chọn giờ khác.
- Dời đến thời điểm hợp lệ kế tiếp.
- Dời theo độ dài gap, nếu nghiệp vụ cho phép.
- Dùng quy tắc được công bố cho lịch lặp lại và thông báo người dùng.

Không mặc định rằng mọi gap dài đúng một giờ; có vùng thay đổi offset với độ dài khác.

### 4.3. Overlap: một giờ địa phương xuất hiện hai lần

Khi đồng hồ quay lùi, một đoạn giờ địa phương được lặp lại. Tại New York ngày 01-11-2026, giờ 01:30 xảy ra hai lần:
- Lần đầu với offset `-04:00`.
- Lần thứ hai với offset `-05:00`.

Vì vậy, `2026-11-01T01:30` tại `America/New_York` có **2 offset hợp lệ**, tương ứng hai instant khác nhau cách nhau một giờ.

Ứng dụng cần chọn chính sách:
- Chọn lần xuất hiện đầu tiên.
- Chọn lần xuất hiện thứ hai.
- Yêu cầu người dùng chọn offset.
- Với lịch lặp lại, áp dụng một chính sách đã được công bố và nhất quán.

Không hiển thị hai lựa chọn chỉ bằng chữ "01:30". Hãy hiển thị thêm offset hoặc nhãn lần xuất hiện, ví dụ `01:30 UTC-04:00` và `01:30 UTC-05:00`.

### 4.4. ZoneRules cho biết số offset hợp lệ

`ZoneRules.getValidOffsets(LocalDateTime)` trả danh sách offset có thể áp dụng:

| Số phần tử | Trường hợp | Cách xử lý |
| ---: | --- | --- |
| 0 | Gap | Giờ địa phương không tồn tại; xem `getTransition` |
| 1 | Normal | Dùng offset duy nhất |
| 2 | Overlap | Chọn offset theo policy hoặc hỏi người dùng |

Tài liệu API mô tả offset ở phần tử đầu tiên của overlap là offset sớm hơn; phần tử thứ hai là offset muộn hơn. API cũng ghi nhận trường hợp lý thuyết có nhiều hơn hai offset, nên code có thể từ chối trường hợp bất thường đó thay vì tự suy diễn.

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);

ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

System.out.println(offsets);
System.out.println(rules.getTransition(local));
```

Khi có gap hoặc overlap, `getTransition(local)` trả về `ZoneOffsetTransition` mô tả chuyển đổi, gồm offset trước/sau và thời điểm địa phương trước/sau transition.

## 5. Viết hàm giải quyết giờ địa phương một cách tường minh

Hàm sau:
- Từ chối giờ thuộc gap.
- Dùng offset duy nhất trong trường hợp bình thường.
- Cho phép chọn lần đầu hoặc lần thứ hai trong overlap.
- Kiểm tra lại lựa chọn bằng `ZonedDateTime.ofStrict`.

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;
import java.util.List;

public class LocalTimeResolver {
    enum OverlapChoice {
        EARLIER,
        LATER
    }

    public static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone,
            OverlapChoice choice) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets = rules.getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException(
                    "Local time falls in a DST gap: "
                    + local + " in " + zone);
        }

        if (offsets.size() > 2) {
            throw new DateTimeException(
                    "Unexpected number of valid offsets: "
                    + offsets.size());
        }

        ZoneOffset selected;
        if (offsets.size() == 1) {
            selected = offsets.get(0);
        } else {
            selected = choice == OverlapChoice.EARLIER
                    ? offsets.get(0)
                    : offsets.get(1);
        }

        return ZonedDateTime.ofStrict(local, selected, zone);
    }
}
```

`ofStrict` kiểm tra local date-time, offset và zone có tạo thành tổ hợp hợp lệ không. Nếu offset không phù hợp với quy tắc vùng, method ném `DateTimeException`.

Ở tầng UI/API, hãy chuyển lỗi gap thành thông báo có thể hành động: "Giờ này không tồn tại do đổi giờ mùa hè; hãy chọn giờ khác". Với overlap, yêu cầu người dùng chọn lần xuất hiện hoặc offset. Không gửi exception nội bộ thẳng cho người dùng.

## 6. Clock: kiểm soát nguồn thời gian

`Clock` là abstraction cung cấp instant hiện tại và zone dùng để chuyển instant thành ngày giờ. Nó cho phép code nghiệp vụ nhận nguồn thời gian từ bên ngoài, thay vì gọi đồng hồ hệ thống ở nhiều nơi.

Các factory thường dùng:

| API | Công dụng |
| --- | --- |
| `Clock.systemUTC()` | Đồng hồ hệ thống, quy đổi theo UTC |
| `Clock.system(ZoneId)` | Đồng hồ hệ thống trong vùng chỉ định |
| `Clock.fixed(Instant, ZoneId)` | Đồng hồ luôn trả cùng instant, phù hợp kiểm thử |
| `Clock.offset(Clock, Duration)` | Dịch thời gian của clock gốc về tương lai/quá khứ |
| `Clock.tick(Clock, Duration)` | Clock chỉ thay đổi theo các nhịp thời gian chỉ định |

### 6.1. Truyền Clock vào service

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AppointmentService {
    private final Clock clock;

    public AppointmentService(Clock clock) {
        this.clock = clock;
    }

    public Instant nowInstant() {
        return Instant.now(clock);
    }

    public ZonedDateTime nowIn(ZoneId zone) {
        return ZonedDateTime.now(clock.withZone(zone));
    }
}
```

Khi chạy production, có thể inject `Clock.systemUTC()` hoặc `Clock.system(zone)`. Trong test, inject `Clock.fixed(...)`.

Cách này giúp:
- Kiểm thử logic trước/sau thời hạn mà không phải chờ.
- Tái hiện chính xác lỗi phụ thuộc ngày/giờ.
- Kiểm tra thời điểm ở các múi giờ khác nhau.
- Tránh test chập chờn do test chạy qua nửa đêm hoặc đổi ngày.

### 6.2. Clock.fixed trong unit test

```java
Instant fixedInstant =
        Instant.parse("2026-11-06T02:00:00Z");

Clock fixedClock = Clock.fixed(
        fixedInstant,
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant now = Instant.now(fixedClock);
ZonedDateTime localNow = ZonedDateTime.now(fixedClock);
```

Mọi lần đọc instant từ `fixedClock` đều nhận cùng một instant. Test không còn phụ thuộc vào ngày giờ thực tế trên máy chạy.

### 6.3. Clock.offset để kiểm thử thời gian tương lai

```java
Clock base = Clock.fixed(
        Instant.parse("2026-11-06T02:00:00Z"),
        ZoneId.of("UTC"));

Clock tomorrow = Clock.offset(base, Duration.ofDays(1));

System.out.println(Instant.now(tomorrow));
```

`Clock.offset` hữu ích khi test thời hạn hết hạn, lịch nhắc hoặc thời gian gia hạn. Không cần sửa đồng hồ hệ điều hành.

### 6.4. Clock không phải đồng hồ đo thời gian thực thi

`Clock` cung cấp thời gian lịch để ứng dụng hiểu "bây giờ là lúc nào". Nó không bảo đảm monotonic (không lùi/nhảy) và không nên dùng để benchmark hoặc đo elapsed time.

Đo khoảng thời gian thực thi trong cùng một process bằng `System.nanoTime()`:

```java
long start = System.nanoTime();

// Công việc cần đo

long elapsedNanos = System.nanoTime() - start;
```

Dùng `Instant`/`Clock` cho timestamp nghiệp vụ; dùng `System.nanoTime()` cho thời lượng thực thi.

## 7. DateTimeFormatter: định dạng và phân tích ngày giờ

`DateTimeFormatter` hỗ trợ:
- Pattern tùy chỉnh.
- ISO date/time format.
- Format theo `Locale`.
- Gắn zone để format instant theo vùng cụ thể.
- Parse chuỗi thành các kiểu `java.time`.
- Quy định cách giải quyết field bằng `ResolverStyle`.

Formatter là immutable và thread-safe, vì vậy có thể tạo hằng static dùng chung.

### 7.1. Pattern thường dùng

| Pattern | Ý nghĩa |
| --- | --- |
| `u` / `uuuu` | Năm theo proleptic year |
| `y` / `yyyy` | Year-of-era |
| `Y` | Week-based year; không dùng thay cho năm lịch thông thường |
| `M` / `MM` | Tháng |
| `d` / `dd` | Ngày trong tháng |
| `H` / `HH` | Giờ 0–23 |
| `h` / `hh` | Giờ 1–12 |
| `m` / `mm` | Phút |
| `s` / `ss` | Giây |
| `X` / `XXX` | Offset, với dạng zero offset thường biểu diễn bằng Z |
| `x` | Offset, zero offset biểu diễn dạng số |
| `Z` | Offset theo kiểu RFC/formatter |
| `V` / `VV` | ID múi giờ vùng; dùng `VV` cho ID đầy đủ |
| `z` | Tên hiển thị múi giờ theo locale, có thể là tên viết tắt |

**Lỗi pattern thường gặp:**
- `MM` là tháng; `mm` là phút.
- `HH` là giờ 24h; `hh` là giờ 12h.
- `uuuu` phù hợp với năm ISO trong parsing strict; `yyyy` biểu diễn year-of-era.
- `YYYY` là week-based year, có thể khác năm lịch vào đầu/cuối năm.

Ví dụ formatter có cả offset và ID vùng:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX '['VV']'",
                Locale.ROOT);
```

Kết quả có dạng `2026-11-06 09:00 +07:00 [Asia/Ho_Chi_Minh]`. Offset cho biết độ lệch tại thời điểm đó; ID vùng cho biết quy tắc địa lý được sử dụng.

### 7.2. Locale và ZoneId là hai lựa chọn độc lập

`Locale` quyết định ngôn ngữ, thứ tự hiển thị và cách viết tên tháng/ngày theo quy ước địa phương. `ZoneId` quyết định cách chuyển instant sang giờ địa phương.

Ví dụ, người dùng có thể:
- Dùng giao diện tiếng Việt nhưng xem lịch theo `America/New_York`.
- Dùng giao diện tiếng Anh nhưng xem lịch theo `Asia/Ho_Chi_Minh`.

Không suy ra múi giờ chỉ từ locale hoặc ngôn ngữ. Một locale có thể được dùng ở nhiều múi giờ.

### 7.3. Format theo locale cho giao diện người dùng

```java
DateTimeFormatter localized =
        DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"))
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String text = localized.format(
        Instant.parse("2026-11-06T02:00:00Z"));

System.out.println(text);
```

Formatter trên nhận `Instant` và chuyển sang zone được chỉ định trước khi format. Kết quả văn bản phụ thuộc locale data của JDK, vì vậy không nên viết unit test so sánh chuỗi localized tuyệt đối nếu test chạy trên nhiều JDK/vendor. Hãy test instant, zone và các field quan trọng; test chuỗi giao diện theo locale/provider cụ thể khi cần.

### 7.4. Format cho API và dữ liệu máy đọc

Với API, log hoặc dữ liệu trao đổi, ưu tiên định dạng ISO-8601 có offset rõ ràng:

```java
String utcText =
        DateTimeFormatter.ISO_INSTANT.format(instant);

String zonedText =
        DateTimeFormatter.ISO_ZONED_DATE_TIME.format(
                instant.atZone(ZoneId.of("America/New_York")));
```

`ISO_INSTANT` biểu diễn thời điểm UTC với hậu tố Z. `ISO_ZONED_DATE_TIME` có thể chứa offset và ID vùng. Nếu giao thức cần cả thời điểm và vùng gốc, hãy truyền cả hai rõ ràng thay vì chỉ gửi một chuỗi local time.

### 7.5. Parse input strict

Với input lịch hẹn, không nên tự động sửa ngày sai như 30-02 thành một ngày khác. Dùng `ResolverStyle.STRICT` và pattern năm `uuuu`:

```java
DateTimeFormatter inputFormat =
        DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDateTime requested =
        LocalDateTime.parse("2026-11-06 09:00", inputFormat);
```

Sau bước parse, vẫn cần zone ID và logic gap/overlap. Parse thành công chỉ chứng minh chuỗi là ngày giờ lịch hợp lệ; nó chưa chứng minh local time tồn tại trong múi giờ đã chọn.

## 8. Lịch hẹn một lần và lịch hẹn lặp lại

Hai loại lịch có quy tắc lưu trữ khác nhau.

### 8.1. Cuộc hẹn một lần đã xác nhận

Khi người dùng xác nhận một cuộc hẹn, hệ thống đã giải quyết local time, zone và DST thành một instant cụ thể. Nên lưu:
- Instant bắt đầu và kết thúc.
- Zone ID được dùng để hiển thị.
- Local date-time ban đầu nếu cần audit.
- Offset đã chọn nếu local time thuộc overlap.
- Người tạo, thời điểm tạo và các thông tin nghiệp vụ liên quan.

Nếu người dùng đổi múi giờ hiển thị sau đó, instant của cuộc hẹn không thay đổi; chỉ cách hiển thị thay đổi.

### 8.2. Lịch lặp lại theo giờ địa phương

Ví dụ "họp mỗi thứ Hai lúc 09:00 tại New York" không phải một danh sách instant cách nhau đúng 7 × 24 giờ.

Nên lưu:
- Quy tắc lặp (ví dụ thứ Hai hàng tuần).
- Giờ địa phương 09:00.
- Zone ID `America/New_York`.
- Chính sách xử lý gap/overlap.
- Ngày bắt đầu/kết thúc hoặc số lần lặp nếu có.

Mỗi occurrence được tính theo ngày lịch và quy tắc vùng của occurrence đó. Không chỉ cộng một duration cố định vào instant trước.

### 8.3. Duration và Period khác nhau quanh DST

`Duration` biểu diễn thời lượng trên timeline; `Period` biểu diễn lượng ngày/tháng/năm theo lịch.

- `Duration.ofHours(24)` luôn là 24 giờ đã trôi qua.
- `Period.ofDays(1)` biểu diễn ngày lịch tiếp theo.
- `ZonedDateTime.plusDays(1)` thực hiện phép cộng theo ngày địa phương; kết quả instant có thể cách instant ban đầu 23, 24 hoặc 25 giờ quanh thay đổi DST.

Ví dụ:

```java
ZonedDateTime before =
        ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0,
                ZoneId.of("America/New_York"));

ZonedDateTime nextCalendarDay = before.plusDays(1);
ZonedDateTime after24Hours = before.plus(Duration.ofHours(24));
```

Vào cuối tuần chuyển sang giờ mùa hè, hai kết quả có thể khác nhau về giờ địa phương. Nếu nghiệp vụ là "mỗi ngày lúc 09:00", hãy tính occurrence từ local date và local time, rồi giải quyết với ZoneRules. Nếu nghiệp vụ là "cứ đúng 24 giờ", dùng Duration trên timeline.

### 8.4. Thay đổi luật múi giờ trong tương lai

Luật múi giờ do chính quyền từng khu vực quyết định và có thể thay đổi. Cơ sở dữ liệu IANA TZDB được cập nhật định kỳ để phản ánh thay đổi đó. Một cuộc hẹn cách vài tháng hoặc vài năm có thể bị ảnh hưởng nếu chính quyền thay đổi giờ mùa hè hoặc offset.

Khi luật thay đổi, sản phẩm cần quyết định:
- **Giữ nguyên instant:** cuộc hẹn diễn ra đúng thời điểm đã chốt, dù giờ hiển thị địa phương có thể đổi.
- **Giữ nguyên giờ địa phương:** cuộc họp vẫn diễn ra lúc 09:00 theo luật mới của vùng, nên instant có thể thay đổi.
- **Yêu cầu xác nhận lại:** phù hợp cuộc họp quan trọng hoặc có nhiều người tham gia.

Không có lựa chọn nào đúng cho mọi nghiệp vụ. Ghi rõ policy và thông báo cho người dùng nếu việc cập nhật rule làm thay đổi giờ họ nhìn thấy.

## 9. Dữ liệu múi giờ và cập nhật tzdb

`ZoneId` vùng lấy quy tắc qua `ZoneRulesProvider`. Quy tắc có thể khác nhau giữa các phiên bản dữ liệu múi giờ được cài trong từng runtime.

Kiểm tra phiên bản tzdb mà JVM hiện tại cung cấp:

```java
NavigableMap<String, ZoneRules> versions =
        ZoneRulesProvider.getVersions("America/New_York");

String loadedVersion = versions.lastKey();
System.out.println(loadedVersion);
```

Giá trị này cho biết version mà provider hiện tại cung cấp cho zone đó; nó không chứng minh đó là bản IANA mới nhất trên Internet.

Tại ngày 06-11-2026, IANA đã công bố tzdb 2026f ngày 27-10-2026. Tuy nhiên, runtime cụ thể có thể chứa dữ liệu cũ hơn. Trong môi trường kiểm thử JDK 24.0.2 của bài này, `ZoneRulesProvider` báo New York dùng version 2025b. Đây là lý do phải kiểm tra runtime/container thực tế thay vì giả định JDK đã chứa bản tzdb mới nhất.

Khi triển khai:
- Cập nhật JDK/runtime image theo quy trình vận hành.
- Kiểm tra version tzdb sau cập nhật.
- Chạy regression test các lịch hẹn gần transition.
- Có quy trình tính lại/đánh giá các occurrence trong tương lai.
- Nếu cần dữ liệu mới hơn runtime cung cấp, đánh giá giải pháp cập nhật tzdb theo tài liệu của vendor/JDK; không sửa trực tiếp file timezone nội bộ của JVM trong production.

`ZoneId` được serialize chủ yếu bằng ID; một runtime khác có thể không có cùng rule set. Khi lấy rules từ một ID không được hỗ trợ hoặc dữ liệu không tương thích, API có thể ném `ZoneRulesException`. Với hệ thống nhiều node, nên đồng bộ phiên bản JDK/tzdb và theo dõi sự khác nhau giữa các node.

## 10. Thiết kế API cho dịch vụ đặt lịch

Một API nhận lịch hẹn nên phân biệt dữ liệu người dùng nhập với thời điểm đã được resolve.

Ví dụ request:

~~~json
{
  "localDateTime": "2026-11-06T09:00:00",
  "timeZone": "Asia/Ho_Chi_Minh",
  "overlapChoice": "EARLIER"
}
~~~

Quy trình xử lý:
1. Parse local date-time bằng formatter strict.
2. Tạo `ZoneId` từ ID vùng.
3. Gọi `getValidOffsets`.
4. Nếu gap, trả lỗi validation kèm gợi ý giờ hợp lệ.
5. Nếu overlap, yêu cầu hoặc áp dụng lựa chọn đã được người dùng chấp thuận.
6. Dùng `ZonedDateTime.ofStrict` để xác nhận.
7. Lưu instant cùng thông tin vùng/lựa chọn cần thiết.
8. Trả response có instant chuẩn và giờ địa phương đã resolve.

Ví dụ response:

~~~json
{
  "startsAt": "2026-11-06T02:00:00Z",
  "organizerTime": "2026-11-06T09:00:00+07:00[Asia/Ho_Chi_Minh]",
  "organizerZone": "Asia/Ho_Chi_Minh"
}
~~~

Đối với overlap, response nên bao gồm offset được chọn. Nếu client gửi local time kèm offset, server vẫn cần kiểm tra offset đó có nằm trong danh sách hợp lệ của zone cho local time đã nhập không.

### 10.1. So sánh thời gian và kiểm tra xung đột lịch

Để phát hiện hai cuộc họp giao nhau, chuyển cả hai về instant:

```java
boolean overlaps(
        Instant startA, Instant endA,
        Instant startB, Instant endB) {

    return startA.isBefore(endB)
            && startB.isBefore(endA);
}
```

Không so sánh chuỗi "09:00" của hai vùng. Cần kiểm tra end sau start và định nghĩa rõ khoảng thời gian là đóng/mở ở biên nào. Với quy ước khoảng nửa mở `[start, end)`, hai cuộc hẹn liền nhau tại cùng một thời điểm kết thúc/bắt đầu không bị xem là giao nhau.

### 10.2. Hiển thị lời mời họp

Lời mời nhiều vùng nên có:
- Ngày và giờ ở vùng người nhận.
- ID vùng hoặc tên vùng rõ ràng.
- Offset tại thời điểm họp nếu có nguy cơ nhầm.
- Giờ của người tổ chức khi cần.
- Link/calendar payload chứa instant chuẩn.

Tránh chỉ gửi "09:00 CST". Nếu người nhận đổi múi giờ trên thiết bị, ứng dụng lịch có thể hiển thị lại theo vùng hiện tại; instant vẫn giữ nguyên.

## 11. Chương trình Java 17+: Lịch hẹn HCM – New York, Clock và DST

Chương trình này:
- Nhận giờ địa phương 09:00 tại HCM.
- Chuyển sang instant.
- Hiển thị giờ New York.
- Dùng fixed clock để có output xác định.
- Kiểm tra số offset trong gap và chọn hai offset của overlap.
- In version tzdb mà JVM hiện tại cung cấp.

Tạo file `AppointmentTimeDemo.java`:

~~~java
import java.time.*;
import java.time.zone.*;
import java.time.format.*;
import java.util.*;

public class AppointmentTimeDemo {
    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, boolean later) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException("DST gap");
        }
        if (offsets.size() > 2) {
            throw new DateTimeException(
                    "Unexpected multiple valid offsets");
        }

        ZoneOffset offset = offsets.size() == 1
                ? offsets.get(0)
                : offsets.get(later ? offsets.size() - 1 : 0);

        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime local =
                LocalDateTime.of(2026, 11, 6, 9, 0);

        ZonedDateTime organizer =
                resolve(local, hcm, false);

        Instant meeting = organizer.toInstant();
        ZonedDateTime attendee = meeting.atZone(newYork);

        DateTimeFormatter format =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX '['VV']'",
                        Locale.ROOT);

        System.out.println("Organizer: " + format.format(organizer));
        System.out.println("New York: " + format.format(attendee));
        System.out.println("UTC instant: "
                + DateTimeFormatter.ISO_INSTANT.format(meeting));

        Clock fixed = Clock.fixed(meeting, hcm);
        System.out.println("Fixed clock: "
                + format.format(ZonedDateTime.now(fixed)));

        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("Spring gap offsets: "
                + newYork.getRules().getValidOffsets(gap).size());

        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        ZonedDateTime first = resolve(overlap, newYork, false);
        ZonedDateTime second = resolve(overlap, newYork, true);

        System.out.println("Overlap earlier: " + first.getOffset()
                + " -> " + first.toInstant());
        System.out.println("Overlap later: " + second.getOffset()
                + " -> " + second.toInstant());

        String tzdb = ZoneRulesProvider
                .getVersions(newYork.getId()).lastKey();
        System.out.println("Loaded New York tzdb: " + tzdb);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AppointmentTimeDemo.java
java AppointmentTimeDemo
~~~

**Stdout trên JDK 24.0.2 trong môi trường kiểm thử:**

~~~text
Organizer: 2026-11-06 09:00 +07:00 [Asia/Ho_Chi_Minh]
New York: 2026-11-05 21:00 -05:00 [America/New_York]
UTC instant: 2026-11-06T02:00:00Z
Fixed clock: 2026-11-06 09:00 +07:00 [Asia/Ho_Chi_Minh]
Spring gap offsets: 0
Overlap earlier: -04:00 -> 2026-11-01T05:30:00Z
Overlap later: -05:00 -> 2026-11-01T06:30:00Z
Loaded New York tzdb: 2025b
~~~

Dòng cuối phụ thuộc dữ liệu tzdb của runtime, vì vậy có thể khác trên JDK/vendor khác. Các dòng giờ, offset và instant phía trên được xác định bởi rules đang cài trong runtime.

## 12. Java 17+: Bộ kiểm tra Clock, DST và DateTimeFormatter

Tạo file `AppointmentTimeChecks.java`:

~~~java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class AppointmentTimeChecks {
    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, boolean later) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException("DST gap");
        }
        if (offsets.size() > 2) {
            throw new DateTimeException(
                    "Unexpected multiple valid offsets");
        }

        return ZonedDateTime.ofStrict(
                local,
                offsets.get(offsets.size() == 1
                        ? 0 : (later ? 1 : 0)),
                zone);
    }

    public static void main(String[] args) {
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        Instant fixed = Instant.parse("2026-11-06T02:00:00Z");
        Clock clock = Clock.fixed(fixed, hcm);

        check(Instant.now(clock).equals(fixed), "fixed instant");
        check(ZonedDateTime.now(clock).getZone().equals(hcm),
                "clock zone");

        LocalDateTime meeting =
                LocalDateTime.of(2026, 11, 6, 9, 0);

        ZonedDateTime organizer = resolve(meeting, hcm, false);
        ZonedDateTime attendee =
                organizer.toInstant().atZone(newYork);

        check(organizer.toInstant().equals(attendee.toInstant()),
                "same instant");
        check(attendee.getHour() == 21
                && attendee.getDayOfMonth() == 5,
                "zone conversion");

        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 8, 2, 30);
        check(newYork.getRules().getValidOffsets(gap).isEmpty(),
                "gap");

        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);
        check(newYork.getRules().getValidOffsets(overlap).size() == 2,
                "overlap");

        ZonedDateTime first = resolve(overlap, newYork, false);
        ZonedDateTime second = resolve(overlap, newYork, true);

        check(Duration.between(first.toInstant(), second.toInstant())
                .equals(Duration.ofHours(1)), "overlap choice");

        DateTimeFormatter strict =
                DateTimeFormatter
                        .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        check(LocalDateTime.parse("2026-11-06 09:00", strict)
                .equals(meeting), "strict parsing");

        DateTimeFormatter display =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX '['VV']'",
                        Locale.ROOT);

        check(display.format(organizer).contains("Asia/Ho_Chi_Minh"),
                "organizer zone");
        check(display.format(attendee).contains("America/New_York"),
                "attendee zone");

        System.out.println("Clock injection and zone: PASS");
        System.out.println("Cross-zone instant conversion: PASS");
        System.out.println("DST gap and overlap handling: PASS");
        System.out.println("Strict parsing and zone formatting: PASS");
        System.out.println("All checks: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AppointmentTimeChecks.java
java AppointmentTimeChecks
~~~

**Stdout:**

~~~text
Clock injection and zone: PASS
Cross-zone instant conversion: PASS
DST gap and overlap handling: PASS
Strict parsing and zone formatting: PASS
All checks: PASS
~~~

Hai chương trình đã được biên dịch bằng `javac --release 17` và chạy thành công trên JDK 24.0.2. Bộ test xác nhận fixed clock, chuyển đổi cùng instant giữa hai vùng, DST gap/overlap, strict parsing và hiển thị zone ID.

## 13. Lỗi thường gặp khi làm lịch nhiều múi giờ

1. **Lưu LocalDateTime làm thời điểm duy nhất:** không có zone nên chưa xác định được instant.
2. **Chỉ lưu offset:** offset cố định không chứa quy tắc vùng cho ngày khác.
3. **Dùng tên viết tắt múi giờ:** chữ viết tắt có thể mơ hồ.
4. **Cộng/trừ số giờ bằng tay:** DST và luật vùng làm độ lệch thay đổi theo ngày.
5. **Dùng ZoneId.systemDefault() trong logic nghiệp vụ:** kết quả phụ thuộc cấu hình máy/container.
6. **Coi Locale là múi giờ:** locale quyết định cách trình bày, không quyết định zone.
7. **Coi gap và overlap là cùng một trường hợp:** gap có 0 offset; overlap có 2.
8. **Chấp nhận giờ gap mà không báo người dùng:** cuộc hẹn có thể bị dịch chuyển âm thầm.
9. **Không yêu cầu lựa chọn khi overlap:** cùng giờ địa phương có thể tương ứng hai instant.
10. **Cho rằng DST luôn đổi một giờ:** transition có thể có độ dài khác.
11. **Dùng ZonedDateTime.of mà không hiểu chính sách mặc định:** gap được đẩy tới giờ hợp lệ và overlap chọn offset mặc định.
12. **Dùng Duration 24 giờ cho lịch "cùng giờ ngày mai":** giờ địa phương có thể thay đổi qua DST.
13. **Dùng Period khi nghiệp vụ cần đúng số giây:** ngày lịch không tương đương 24 giờ elapsed.
14. **Tạo từng cuộc hẹn cho từng người bằng local time:** có nguy cơ tạo các instant khác nhau.
15. **Format chỉ HH:mm:** thiếu ngày và zone, gây nhầm khi qua nửa đêm ở vùng khác.
16. **Format offset mà không lưu ZoneId:** không thể tái hiện quy tắc vùng cho recurrence.
17. **Dùng yyyy trong parser strict cho ISO year:** nên dùng uuuu.
18. **Nhầm MM và mm:** tháng và phút khác nhau.
19. **Dùng YYYY thay uuuu:** week-based year có thể khác năm lịch.
20. **Dùng formatter theo default locale trong API:** output có thể thay đổi theo máy chạy.
21. **Parse strict nhưng không kiểm tra ZoneRules:** chuỗi local hợp lệ chưa chắc tồn tại trong vùng đó.
22. **Dùng Clock để đo hiệu năng:** wall clock không bảo đảm monotonic; dùng nanoTime.
23. **Hard-code một phiên bản tzdb:** dữ liệu vùng được cập nhật theo thay đổi luật.
24. **Giả định mọi node có cùng tzdb:** container/JDK khác nhau có thể trả offset khác cho lịch tương lai.
25. **Không xác định policy khi luật đổi:** không rõ giữ instant hay giữ giờ địa phương.
26. **Lưu recurrence thành chuỗi instant cố định:** không bảo đảm cuộc họp giữ nguyên giờ địa phương.
27. **Không test ngày đổi DST:** bug có thể chỉ xuất hiện vài ngày trong năm.
28. **So sánh chuỗi ngày giờ:** so sánh Instant hoặc khoảng thời gian đã chuẩn hóa.
29. **Không kiểm tra end > start:** cuộc hẹn có thể có khoảng thời gian âm hoặc bằng 0.
30. **Không ghi offset đã chọn trong overlap:** khó audit vì sao cuộc họp được resolve thành instant cụ thể.

## 14. Checklist triển khai

- [ ] Input local date/time được parse strict?
- [ ] Người dùng hoặc request cung cấp zone ID vùng rõ ràng?
- [ ] Có kiểm tra `ZoneRules.getValidOffsets` trước khi xác nhận?
- [ ] Gap được từ chối hoặc xử lý theo policy đã công bố?
- [ ] Overlap có lựa chọn offset rõ ràng?
- [ ] Dùng `ZonedDateTime.ofStrict` để xác nhận offset?
- [ ] Cuộc hẹn một lần được lưu bằng `Instant`?
- [ ] Lịch lặp lại giữ local time, ZoneId và recurrence rule?
- [ ] Policy khi tzdb thay đổi đã được quyết định?
- [ ] Mọi người tham gia được hiển thị từ cùng một instant?
- [ ] UI hiển thị ngày, giờ và zone/offset khi cần?
- [ ] Locale và ZoneId được cấu hình độc lập?
- [ ] DateTimeFormatter dùng locale rõ ràng?
- [ ] Formatter parsing dùng ResolverStyle phù hợp?
- [ ] Service nhận Clock qua constructor/DI?
- [ ] Test dùng Clock.fixed hoặc Clock.offset?
- [ ] Elapsed-time measurement dùng System.nanoTime?
- [ ] Có kiểm thử gap, overlap và ngày bình thường?
- [ ] CI kiểm tra version tzdb trên runtime/container?
- [ ] Các node production có runtime/timezone data đồng bộ?
- [ ] Có test cuộc hẹn qua nửa đêm ở một số vùng?
- [ ] Có kiểm tra xung đột theo Instant và khoảng [start, end)?
- [ ] Có kiểm thử lịch lặp lại qua thay đổi DST?
- [ ] Có thông báo cho người dùng nếu giờ tương lai thay đổi do luật mới?

## 15. Tình huống kiểm thử bổ sung

| Tình huống | Điều cần xác nhận |
| --- | --- |
| HCM 09:00, New York cùng ngày | Instant giống nhau, giờ địa phương khác nhau |
| New York 02:30 ngày spring-forward | Gap được phát hiện, không xác nhận âm thầm |
| New York 01:30 ngày fall-back | Có hai offset; policy chọn đúng |
| Một cuộc hẹn qua nửa đêm ở người nhận | Ngày địa phương hiển thị chính xác |
| Lịch lặp 09:00 hàng tuần | Giữ giờ địa phương theo recurrence policy |
| Duration 24 giờ qua DST | Khác với một ngày lịch nếu offset thay đổi |
| Locale tiếng Việt, zone New York | Văn bản tiếng Việt nhưng giờ theo New York |
| Locale tiếng Anh, zone HCM | Văn bản tiếng Anh nhưng giờ theo HCM |
| Máy chạy đổi default zone | Kết quả nghiệp vụ không thay đổi nếu zone đã chỉ định |
| Clock.fixed | Test có output xác định |
| Clock.offset | Test thời hạn trong tương lai/quá khứ |
| JDK/tzdb được cập nhật | Occurrence tương lai được đánh giá lại theo policy |
| API nhận offset không hợp lệ | Server từ chối offset không thuộc ZoneRules |
| Hai lịch liền nhau | Không bị đánh dấu giao nhau nếu dùng khoảng [start, end) |
| Nhiều node có tzdb khác nhau | Phát hiện khác biệt và đồng bộ dữ liệu |

## 16. Câu hỏi ôn tập

1. Vì sao Instant phù hợp để lưu thời điểm cuộc hẹn đã xác nhận?
2. LocalDateTime thiếu thông tin gì để xác định một instant?
3. ZoneId khác ZoneOffset ở điểm nào?
4. Vì sao không nên dùng CST/IST/EST làm ID múi giờ?
5. DST gap có bao nhiêu valid offset?
6. DST overlap có bao nhiêu valid offset?
7. ZoneRules.getTransition dùng để làm gì?
8. Vì sao cần ZonedDateTime.ofStrict khi người dùng chọn offset?
9. Chính sách mặc định của ZonedDateTime.of khi gặp gap/overlap là gì?
10. Clock.fixed giúp ích gì trong unit test?
11. Khi nào nên dùng Clock.systemUTC?
12. Clock có phải công cụ đo thời gian thực thi không?
13. Vì sao System.nanoTime phù hợp hơn để đo elapsed time?
14. Locale và ZoneId khác nhau thế nào?
15. Vì sao nên dùng uuuu cho parser ISO strict?
16. Pattern MM và mm khác nhau thế nào?
17. Vì sao formatter nên được tạo với Locale rõ ràng?
18. Khi nào nên dùng Duration, khi nào dùng Period?
19. Vì sao lịch lặp lại lúc 09:00 không nên chỉ lưu một chuỗi Instant?
20. Khi luật múi giờ thay đổi, hệ thống cần quyết định điều gì?
21. Vì sao hai node có thể hiển thị khác giờ cho cùng lịch tương lai?
22. ZoneRulesProvider.getVersions cung cấp thông tin gì?
23. Vì sao nên hiển thị cả offset và zone ID khi giờ bị lặp?
24. Vì sao mọi người tham gia phải nhận cùng một Instant?

**Gợi ý đáp án:** (1) Nó xác định một điểm duy nhất trên timeline. (2) Zone/offset. (3) ZoneId chứa quy tắc vùng; ZoneOffset là độ lệch cụ thể. (4) Chữ viết tắt mơ hồ và không chứa rule đầy đủ. (5) 0. (6) Thông thường 2. (7) Lấy transition gây gap/overlap. (8) Để xác nhận offset phù hợp với local time và zone. (9) Gap được điều chỉnh tới giờ hợp lệ sau gap; overlap dùng offset sớm hơn theo mặc định. (10) Cố định instant để test lặp lại. (11) Khi cần timestamp chuẩn không phụ thuộc default zone. (12) Không. (13) Nó phù hợp đo elapsed time monotonic trong process. (14) Locale định dạng/ngôn ngữ; ZoneId quy định giờ địa phương. (15) uuuu là proleptic year. (16) MM là tháng; mm là phút. (17) Tránh output phụ thuộc máy. (18) Duration cho thời lượng trên timeline; Period cho ngày lịch. (19) Mỗi occurrence cần giữ cùng giờ địa phương theo rule vùng. (20) Giữ instant hay giữ local wall-clock. (21) Runtime có thể dùng phiên bản tzdb khác nhau. (22) Các version ZoneRules hiện có của provider cho zone. (23) Để phân biệt hai lần xuất hiện. (24) Để tất cả cùng tham dự một sự kiện tại một thời điểm.

**Kết luận:** Lịch hẹn nhiều múi giờ cần tách thời điểm chuẩn khỏi cách hiển thị địa phương. Dùng `Instant` cho cuộc hẹn đã chốt, `ZoneId` và `ZoneRules` để chuyển đổi theo luật vùng, xử lý DST gap/overlap theo policy rõ ràng, `Clock` để kiểm soát "bây giờ" và `DateTimeFormatter` để định dạng/parsing theo locale. Với lịch lặp lại, lưu giờ địa phương, vùng và recurrence rule; theo dõi cập nhật tzdb và xác định trước cách xử lý khi luật múi giờ thay đổi.

## Tài liệu tham khảo chính thức

- **Java SE 27 API — java.time package:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/package-summary.html
- **Clock, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html
- **Instant, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html
- **ZoneId, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZoneId.html
- **ZoneRules, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneRules.html
- **ZoneOffsetTransition, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html
- **ZonedDateTime, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html
- **DateTimeFormatter, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html
- **DateTimeFormatter pattern syntax, Java SE 27:** https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html#patterns
- **IANA Time Zone Database releases:** https://www.iana.org/time-zones/releases
- **IANA time zone and daylight-saving data:** https://www.iana.org/time-zones/tz-link
