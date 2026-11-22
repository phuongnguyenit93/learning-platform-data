# Phân biệt ZoneId với offset cố định trong Java 8+

> **Chủ đề:** Múi giờ. Bài viết giải thích `java.time.ZoneId`, `ZoneOffset`, `ZoneRules`, `ZonedDateTime`, `OffsetDateTime` và `Instant`. Các API nền tảng có từ Java 8 và vẫn áp dụng trên JDK hiện đại. Tư tưởng chính: **tên vùng thời gian không phải một UTC offset bất biến**; offset hợp lệ tại một thời điểm là **kết quả của quy tắc vùng**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể phân biệt tên vùng IANA như `Asia/Ho_Chi_Minh`, `Europe/Paris` với các offset `+07:00` và `+01:00`; tra offset bằng `ZoneRules`; chọn đúng `Instant` / `LocalDateTime` / `OffsetDateTime` / `ZonedDateTime`; xử lý giờ không tồn tại hoặc trùng lặp vì DST; và viết mã/test không phụ thuộc zone mặc định của máy.

## 2. Bốn khái niệm không thể thay thế nhau

### 2.1. `Instant` — một mốc tuyệt đối trên timeline

```java
Instant moment = Instant.parse("2024-01-15T12:00:00Z");
```

Đây là **một sự kiện duy nhất**, bất kể người đọc ở Việt Nam, Paris hay New York. `Instant` không giữ tên thành phố hay múi giờ hiển thị. Ký hiệu `Z` chỉ offset UTC zero trong chuỗi ISO.

### 2.2. `LocalDateTime` — ngày và giờ địa phương chưa có vùng

```java
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
```

Giá trị này chỉ có năm, tháng, ngày và giờ; **không có offset hay ZoneId**. Tự bản thân nó không xác định một Instant duy nhất: khi đồng hồ lùi vì DST, có thể tồn tại **hai mốc thực** cùng `02:30`; khi đồng hồ nhảy tới có thể **không có** mốc thực tương ứng.

### 2.3. `ZoneOffset` — một độ lệch UTC cố định

```java
ZoneOffset plusSeven = ZoneOffset.ofHours(7);
ZoneOffset plusOne = ZoneOffset.of("+01:00");
ZoneOffset plusFiveThirty = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset utc = ZoneOffset.UTC;
```

- `+07:00`: giờ địa phương nhanh hơn UTC 7 giờ.
- `+01:00`: nhanh hơn UTC 1 giờ.
- `-04:00`: chậm hơn UTC 4 giờ.
- `Z` / `+00:00`: bằng UTC.

`ZoneOffset` không tự chứa lịch DST, quy định quốc gia hay thay đổi lịch sử. Nó luôn biểu diễn **cùng một offset**, dù tháng 1 hay tháng 7. API Java cho phép offset từ `-18:00` đến `+18:00`, không phải giá trị giờ bất kỳ. Offset cũng không nhất thiết là số giờ nguyên: `+05:30` hoặc `+05:45` đều là các offset hợp lệ.

### 2.4. `ZoneId` — định danh dùng để tra quy tắc múi giờ

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId newYork = ZoneId.of("America/New_York");
```

Các region ID thường có dạng IANA `Area/City`. Với một region, Java lấy `ZoneRules` từ cơ sở dữ liệu timezone của runtime để tính offset **cho từng thời điểm**. Region ID không tự đồng nghĩa một offset hiện tại.

**Điểm tinh tế:** `ZoneOffset` **là một subclass của `ZoneId`**. Vì vậy không phải mọi đối tượng `ZoneId` đều có quy tắc chuyển offset. Hai nhóm chính:

- **Fixed-offset ZoneId**: một offset dùng cho mọi instant; `ZoneOffset` là biểu diễn điển hình.
- **Region-based ZoneId**: tên khu vực gắn với lịch sử/quy tắc tương lai; có thể đổi offset do daylight-saving time hoặc thay đổi luật.

Mã ID có thể ổn định trong khi quy tắc vùng được cập nhật khi chính phủ thay đổi luật. Đối với ngày giờ trong tương lai, không có bảo đảm “offset hiện tại sẽ mãi đúng” cho một region.

### 2.5. `ZoneRules` — ánh xạ thời điểm và giờ địa phương

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneRules rules = paris.getRules();

ZoneOffset winter = rules.getOffset(
        Instant.parse("2024-01-15T12:00:00Z"));
// +01:00.

ZoneOffset summer = rules.getOffset(
        Instant.parse("2024-07-15T12:00:00Z"));
// +02:00.
```

Snippet `ZoneRules` cần `import java.time.zone.ZoneRules;`. Quy tắc được lấy từ vùng có thể chứa chuyển tiếp lịch sử, DST và quy tắc tương lai tùy cơ sở dữ liệu trên runtime.

| Kiểu | Mang thông tin gì? | Đủ để biết một Instant? |
| --- | --- | --- |
| `LocalDateTime` | Ngày + giờ địa phương | **Không**, thiếu offset/zone |
| `ZoneOffset` | Chênh lệch UTC cụ thể | Cùng LocalDateTime thì **có** |
| Region `ZoneId` | ID và quy tắc vùng | Có thể cần giải quyết gap/overlap |
| `OffsetDateTime` | LocalDateTime + offset | **Có**, đúng một Instant |
| `ZonedDateTime` | LocalDateTime + zone + offset đã giải quyết | **Có**, đúng một Instant |
| `Instant` | Mốc tuyệt đối | Đã xác định trên timeline |

## 3. Cùng một Instant, offset vùng thay đổi theo mùa

Ví dụ hai Instant đã biết ở Paris:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
Instant winter = Instant.parse("2024-01-15T12:00:00Z");
Instant summer = Instant.parse("2024-07-15T12:00:00Z");

ZonedDateTime parisWinter = winter.atZone(paris);
ZonedDateTime parisSummer = summer.atZone(paris);
```

Kết quả:

```text
2024-01-15T13:00+01:00[Europe/Paris]
2024-07-15T14:00+02:00[Europe/Paris]
```

Dùng offset `+01:00` cố định cho cùng hai Instant:

```java
ZoneOffset fixed = ZoneOffset.ofHours(1);
ZonedDateTime fixedWinter = winter.atZone(fixed);
ZonedDateTime fixedSummer = summer.atZone(fixed);
```

```text
2024-01-15T13:00+01:00
2024-07-15T13:00+01:00
```

| Đầu vào UTC | Region `Europe/Paris` | Fixed offset `+01:00` |
| --- | --- | --- |
| `2024-01-15T12:00Z` | 13:00, `+01:00` | 13:00, `+01:00` |
| `2024-07-15T12:00Z` | **14:00, +02:00** | **13:00, +01:00** |

Cả hai cách trùng vào mùa đông 2024 nhưng **không trùng trong mùa hè 2024**. Do đó không thể thay `Europe/Paris` bằng một offset cố định trong ứng dụng có lịch địa phương quanh năm.

**Việt Nam:** Với một số Instant hiện đại, `Asia/Ho_Chi_Minh` và `+07:00` cùng cho offset +07. Tuy nhiên, region ID vẫn lưu thông tin **lịch sử và những quy tắc có thể được cập nhật**, còn fixed offset không. Không coi hai khái niệm giống hệt chỉ vì vài kết quả thời gian hiện tại trùng nhau.

## 4. Các cách tạo ID và offset

### Region-based `ZoneId`

```java
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
```

Đây là các ID vùng, không phải số giờ. ID sai hoặc không được hỗ trợ trong cơ sở dữ liệu có thể ném `ZoneRulesException`/`DateTimeException`; phải xác thực dữ liệu nhập.

### `ZoneOffset` — bao gồm độ lệch có phút

```java
ZoneOffset plus7 = ZoneOffset.of("+07:00");
ZoneOffset plus530 = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset utc = ZoneOffset.UTC;
```

Không viết mọi offset bằng số giờ nguyên. Hệ thống có thể cần `+05:30` hoặc các độ lệch không tròn giờ.

### `UTC+07:00` là một fixed-offset ZoneId có tiền tố

```java
ZoneId prefixed = ZoneId.of("UTC+07:00");
ZoneId plain = ZoneId.of("+07:00");

ZoneId normalized = prefixed.normalized();
// normalized trả ZoneOffset +07:00.
```

Java hỗ trợ dạng tiền tố `UTC`/`GMT`/`UT` và offset dạng `+HH:MM`. `ZoneId.of("+07:00")` tạo `ZoneOffset`; `ZoneId.of("UTC+07:00")` giữ ID tiền tố, nhưng rules là **fixed offset**. `normalized()` sẽ trả `ZoneOffset` nếu ID có fixed rules.

Đừng dùng `zone instanceof ZoneOffset` làm phép kiểm duy nhất rằng một ZoneId có quy tắc cố định; một ID có tiền tố có thể không phải object `ZoneOffset`. Dùng `zone.getRules().isFixedOffset()` theo hợp đồng API.

### `ZoneId.systemDefault()` là cấu hình, không phải nghiệp vụ

```java
ZoneId machineZone = ZoneId.systemDefault();
```

Zone mặc định có thể khác giữa laptop, server, container và CI. Nếu dữ liệu nghiệp vụ thuộc vùng Việt Nam/Paris, nên dùng `ZoneId` explicit hoặc inject qua cấu hình đã xác thực, không âm thầm phụ thuộc môi trường triển khai.

## 5. `OffsetDateTime` và `ZonedDateTime` có ý nghĩa khác

```java
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 14, 0);

OffsetDateTime offsetOnly =
        local.atOffset(ZoneOffset.ofHours(2));

ZonedDateTime withRegion =
        local.atZone(ZoneId.of("Europe/Paris"));
```

Ở ngày/giờ này, chúng có thể đại diện cùng một Instant; nhưng:

- `OffsetDateTime` giữ **local date-time + một offset cụ thể**; không giữ vùng địa lý hay quy tắc chuyển offset ở các kỳ khác.
- `ZonedDateTime` giữ **local date-time + ZoneId + offset đã được xác định**. Khi tính ngày/giờ lịch trong region, Java tham chiếu quy tắc vùng.
- `Instant` giữ mốc trên timeline mà không giữ cách hiển thị theo địa phương.

Nếu đang lưu sự kiện “đã xảy ra lúc nào”, `Instant` thường hợp lý; nếu cần tái tạo một lịch “09:00 mỗi thứ Hai tại Paris”, lưu **region ZoneId**, lịch local và policy DST. Không lấy offset của lần tổ chức hiện tại để làm offset của mọi kỳ tiếp theo.


## 6. Hướng chuyển đổi đúng: Instant → vùng; LocalDateTime → cần chọn quy tắc

### 6.1. Có `Instant` thì chuyển sang zone rõ ràng

```java
Instant instant = Instant.parse("2024-01-15T12:00:00Z");

ZonedDateTime paris = instant.atZone(
        ZoneId.of("Europe/Paris"));
ZonedDateTime hcm = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

boolean sameMoment = paris.toInstant().equals(hcm.toInstant());
// true.
```

Từ **một Instant** sang region zone, Java tìm được **đúng một offset** tại Instant đó, nên không có mơ hồ gap/overlap. Đây là cách phù hợp để hiển thị timestamp theo vị trí người dùng.

### 6.2. Có `LocalDateTime` thì chưa biết được Instant

```java
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 14, 0);

Instant parisInstant = local.atZone(
        ZoneId.of("Europe/Paris")).toInstant();

Instant offsetInstant = local.atOffset(
        ZoneOffset.ofHours(1)).toInstant();
```

Hai Instant có thể khác nhau, bởi tháng 7 Paris dùng +02 chứ không phải +01. **Gắn một offset đoán mò** cho local date-time không phải là cách giải quyết chính xác khi biết nguồn đang thuộc vùng nào.

Nếu input vốn có offset, hãy parse `OffsetDateTime`; nếu input có ID vùng cùng offset, có thể parse `ZonedDateTime`. Nếu chỉ nhận chuỗi local, API phải xác định rõ region và cách giải quyết DST.

### 6.3. `withZoneSameInstant` khác `withZoneSameLocal`

```java
ZonedDateTime paris = Instant
        .parse("2024-01-15T12:00:00Z")
        .atZone(ZoneId.of("Europe/Paris"));

ZonedDateTime sameInstant =
        paris.withZoneSameInstant(ZoneOffset.UTC);
// 2024-01-15T12:00Z: GIỮ nguyên Instant.

ZonedDateTime sameLocal =
        paris.withZoneSameLocal(ZoneOffset.UTC);
// 2024-01-15T13:00Z: GIỮ nguyên giờ địa phương 13:00.
```

- `withZoneSameInstant`: đổi **góc nhìn/hiển thị** một sự kiện theo zone mới.
- `withZoneSameLocal`: cố giữ **con số ngày-giờ trên đồng hồ**, nên có thể tạo **một Instant khác**.

Nếu bạn chuyển giờ từ Paris sang Việt Nam để hiển thị cho người nhận, đa số trường hợp cần **same instant**, không phải **same local**. Dùng `withZoneSameLocal` chỉ khi thực sự muốn áp đặt lại “13:00 ở một vùng khác” với ý nghĩa sự kiện thay đổi.

## 7. DST gap: một giờ địa phương không tồn tại

Trong chuyển đổi sang giờ mùa hè ở `Europe/Paris` ngày 31/03/2024, các giờ từ 02:00 đến trước 03:00 là **gap** theo quy tắc vùng (giả sử tzdb hiện hành của runtime).

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime requested = LocalDateTime.of(2024, 3, 31, 2, 30);

List<ZoneOffset> valid =
        paris.getRules().getValidOffsets(requested);
// valid.size() == 0.
```

`getValidOffsets(LocalDateTime)` trả **0 offset** cho gap: không có Instant mà đồng hồ ở Paris thực sự chỉ `02:30` trong bước chuyển đó.

### `atZone` có chính sách tự điều chỉnh

```java
ZonedDateTime resolved = requested.atZone(paris);
// 2024-03-31T03:30+02:00[Europe/Paris].
```

Với gap một giờ ở ví dụ này, Java mặc định **đẩy local time tiến lên theo độ dài gap**. Nếu nghiệp vụ không cho phép tự điều chỉnh giờ (đặt lịch khám đúng giờ, lịch tàu chạy...), phải **kiểm tra trước** và báo người dùng chọn thời gian hợp lệ.

### `ofStrict` từ chối local/offset/zone không hợp lệ

```java
try {
    ZonedDateTime.ofStrict(
            requested, ZoneOffset.ofHours(1), paris);
    throw new AssertionError("Must reject gap");
} catch (DateTimeException expected) {
    // Không thể có 02:30+01 ở Paris tại local date-time này.
}
```

`ofStrict` xác minh offset đã truyền thực sự hợp lệ cho local date-time theo ZoneRules; nếu không hợp lệ, ném `DateTimeException`. Đây là lựa chọn hữu ích khi offset và vùng phải khớp đúng hợp đồng input.

## 8. DST overlap: cùng local time có hai offset

Khi đồng hồ Paris lùi ngày 27/10/2024, thời gian `02:30` xuất hiện hai lần:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);

List<ZoneOffset> valid =
        paris.getRules().getValidOffsets(local);
// [+02:00, +01:00] trong ví dụ.
```

`valid.size()==2` có nghĩa **hai Instant khác nhau** đều có biểu diễn local 02:30 tại Paris.

```java
ZonedDateTime earlier = local.atZone(paris);
// 2024-10-27T02:30+02:00[Europe/Paris].

ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
// 2024-10-27T02:30+01:00[Europe/Paris].
```

Hai mốc thực chênh **3.600 giây**. `ZonedDateTime.of(local,zone)` / `atZone(zone)` thường chọn **offset sớm hơn** nếu không có offset ưu tiên hợp lệ. Khi cần lựa chọn rõ ràng, dùng `withEarlierOffsetAtOverlap` / `withLaterOffsetAtOverlap` hoặc `ofStrict(local, selectedOffset, zone)`.

### Bảng quy tắc tra offset cho local time

| Trường hợp | Số phần tử `getValidOffsets(local)` | Hành vi cần chú ý |
| --- | ---: | --- |
| Bình thường | 1 | Chỉ có một offset hợp lệ |
| DST gap (nhảy tới) | 0 | Giờ local không tồn tại; `atZone` có thể điều chỉnh |
| DST overlap (lùi lại) | 2 | Cùng local time đại diện hai Instant; phải chọn policy |

**Đừng dùng `zone.getRules().getOffset(LocalDateTime)` để tuyên bố luôn có một offset duy nhất:** trong gap/overlap, phương thức đó trả một giá trị “phù hợp/best” chứ không kiểm tra tính duy nhất. Khi bạn cần xác minh input local, dùng `getValidOffsets(local)`, kiểm tra số lượng và có thể dùng `getTransition(local)` để giải thích chỗ chuyển.

### Một `OffsetDateTime` không bảo đảm local time khớp region

```java
LocalDateTime local = LocalDateTime.of(2024, 3, 31, 2, 30);
OffsetDateTime offsetOnly =
        local.atOffset(ZoneOffset.ofHours(1));
```

`OffsetDateTime` vẫn tạo một Instant hợp lệ từ local + fixed offset. Tuy nhiên, biểu diễn “02:30+01” **không đồng nghĩa** local 02:30 thực sự xảy ra tại region Paris ngày đó. Muốn ràng buộc dữ liệu theo vùng Paris, phải kiểm tra ZoneRules chứ không chỉ nhìn số offset.

## 9. Cộng ngày lịch và cộng giờ thực với region/fixed offset

Cộng 1 ngày theo **local timeline** quanh DST có thể cách nhau 23 hoặc 25 giờ trên timeline. Cộng 24 giờ theo `Duration` luôn là 86.400 giây elapsed:

```java
ZonedDateTime paris = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime nextCalendarDay = paris.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris].

ZonedDateTime exactly24Hours = paris.plus(Duration.ofHours(24));
// 2024-03-31T13:00+02:00[Europe/Paris].
```

Nếu thay `Europe/Paris` bằng fixed `+01:00`, **không có bước DST**, nên hai kết quả này đều chỉ giờ 12:00 ngày sau. Điều đó không khiến fixed offset đúng cho lịch ở Paris: nó chỉ loại bỏ luật DST khỏi phép tính. Khi nghiệp vụ yêu cầu “mỗi ngày lúc 12:00 địa phương Paris”, dùng region zone thay vì ép một offset.

Dùng `Instant` và `Duration` cho “đúng 24 giờ sau”; dùng `LocalDate`/`ZonedDateTime.plusDays` theo quy tắc local cho “ngày mai cùng giờ”.


## 10. Chương trình Java hoàn chỉnh, có kiểm tra đầu ra

Ví dụ này dùng hai Instant mùa đông/mùa hè để chứng minh region Paris đổi offset trong khi fixed offset không đổi; kiểm tra `UTC+07:00` dạng fixed prefixed ID; minh họa DST gap/overlap, `ofStrict`, chuyển zone giữ Instant/giữ giờ local; cuối cùng inject `Clock.fixed` để việc gọi `now` có thể lặp lại.

Tạo file **`ZoneIdOffsetDemo.java`**:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class ZoneIdOffsetDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneOffset fixedPlusOne = ZoneOffset.ofHours(1);
        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");

        ZonedDateTime parisWinter = winter.atZone(paris);
        ZonedDateTime parisSummer = summer.atZone(paris);
        ZonedDateTime fixedWinter = winter.atZone(fixedPlusOne);
        ZonedDateTime fixedSummer = summer.atZone(fixedPlusOne);

        ZoneId prefixed = ZoneId.of("UTC+07:00");
        ZoneOffset normalized = (ZoneOffset) prefixed.normalized();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);
        List<ZoneOffset> gapOffsets = paris.getRules().getValidOffsets(gap);
        ZonedDateTime gapResolved = gap.atZone(paris);
        boolean strictGapRejected = false;
        try {
            ZonedDateTime.ofStrict(gap, fixedPlusOne, paris);
        } catch (DateTimeException expected) {
            strictGapRejected = true;
        }

        LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);
        List<ZoneOffset> overlapOffsets =
                paris.getRules().getValidOffsets(overlap);
        ZonedDateTime earlier = overlap.atZone(paris);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        ZonedDateTime utcSameInstant =
                parisWinter.withZoneSameInstant(ZoneOffset.UTC);
        ZonedDateTime utcSameLocal =
                parisWinter.withZoneSameLocal(ZoneOffset.UTC);

        OffsetDateTime fixedOffsetDateTime =
                overlap.atOffset(ZoneOffset.ofHours(2));
        Clock fixedParisClock = Clock.fixed(winter, paris);

        System.out.println("Paris winter: " + parisWinter);
        System.out.println("Paris summer: " + parisSummer);
        System.out.println("Fixed +01 winter: " + fixedWinter);
        System.out.println("Fixed +01 summer: " + fixedSummer);
        System.out.println("Paris winter/summer offsets: "
                + parisWinter.getOffset() + "/" + parisSummer.getOffset());
        System.out.println("Paris fixed rules: "
                + paris.getRules().isFixedOffset());
        System.out.println("Offset fixed rules: "
                + fixedPlusOne.getRules().isFixedOffset());
        System.out.println("Prefixed ID normalized: "
                + prefixed.getId() + " -> " + normalized);
        System.out.println("Gap valid offset count: " + gapOffsets.size());
        System.out.println("Gap resolved in Paris: " + gapResolved);
        System.out.println("Gap rejected by ofStrict: " + strictGapRejected);
        System.out.println("Overlap valid offsets: " + overlapOffsets);
        System.out.println("Overlap earlier: " + earlier);
        System.out.println("Overlap later: " + later);
        System.out.println("Overlap instant difference seconds: "
                + (later.toEpochSecond() - earlier.toEpochSecond()));
        System.out.println("Same instant in UTC: " + utcSameInstant);
        System.out.println("Same local in UTC: " + utcSameLocal);
        System.out.println("OffsetDateTime only: " + fixedOffsetDateTime);
        System.out.println("Fixed clock now: "
                + ZonedDateTime.now(fixedParisClock));

        if (!parisWinter.toString().equals(
                "2024-01-15T13:00+01:00[Europe/Paris]")
                || !parisSummer.toString().equals(
                "2024-07-15T14:00+02:00[Europe/Paris]")
                || !fixedWinter.toString().equals("2024-01-15T13:00+01:00")
                || !fixedSummer.toString().equals("2024-07-15T13:00+01:00")
                || paris.getRules().isFixedOffset()
                || !fixedPlusOne.getRules().isFixedOffset()
                || !normalized.equals(ZoneOffset.ofHours(7))
                || gapOffsets.size() != 0 || !strictGapRejected
                || !gapResolved.toString().equals(
                    "2024-03-31T03:30+02:00[Europe/Paris]")
                || overlapOffsets.size() != 2
                || !earlier.toString().equals(
                    "2024-10-27T02:30+02:00[Europe/Paris]")
                || !later.toString().equals(
                    "2024-10-27T02:30+01:00[Europe/Paris]")
                || later.toEpochSecond() - earlier.toEpochSecond() != 3600L
                || !utcSameInstant.toString().equals("2024-01-15T12:00Z")
                || !utcSameLocal.toString().equals("2024-01-15T13:00Z")
                || !fixedOffsetDateTime.toString().equals(
                    "2024-10-27T02:30+02:00")
                || !ZonedDateTime.now(fixedParisClock).equals(parisWinter)) {
            throw new AssertionError("Zone rules mismatch");
        }
        System.out.println("Checks passed.");
    }
}
```

Lệnh biên dịch trên JDK 17+ (đồng thời kiểm tra khả năng dùng API Java 8):

```bash
javac --release 8 ZoneIdOffsetDemo.java
java ZoneIdOffsetDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24:**

```text
Paris winter: 2024-01-15T13:00+01:00[Europe/Paris]
Paris summer: 2024-07-15T14:00+02:00[Europe/Paris]
Fixed +01 winter: 2024-01-15T13:00+01:00
Fixed +01 summer: 2024-07-15T13:00+01:00
Paris winter/summer offsets: +01:00/+02:00
Paris fixed rules: false
Offset fixed rules: true
Prefixed ID normalized: UTC+07:00 -> +07:00
Gap valid offset count: 0
Gap resolved in Paris: 2024-03-31T03:30+02:00[Europe/Paris]
Gap rejected by ofStrict: true
Overlap valid offsets: [+02:00, +01:00]
Overlap earlier: 2024-10-27T02:30+02:00[Europe/Paris]
Overlap later: 2024-10-27T02:30+01:00[Europe/Paris]
Overlap instant difference seconds: 3600
Same instant in UTC: 2024-01-15T12:00Z
Same local in UTC: 2024-01-15T13:00Z
OffsetDateTime only: 2024-10-27T02:30+02:00
Fixed clock now: 2024-01-15T13:00+01:00[Europe/Paris]
Checks passed.
```

Chương trình dùng `Clock.fixed` cho `now`; vì vậy output không thay đổi theo thời điểm thật. Các mốc chuyển DST ở Paris lấy theo quy tắc vùng từ timezone database hiện hành của JDK đã kiểm thử.

**Giải thích kết quả:** Dòng winter/summer thể hiện sự khác nhau giữa region và fixed offset; `Gap valid offset count: 0` chứng minh một local time không tồn tại; `Overlap valid offsets` cho thấy hai offset hợp lệ, tương ứng hai Instant khác nhau đúng 3600 giây. `Same instant` giữ mốc thực trong khi `Same local` giữ giờ trên đồng hồ, dẫn đến mốc thực khác. Dòng `Fixed clock now` minh họa cách tiêm đồng hồ để test.


## 11. Thiết kế API và lưu trữ ngày giờ trong ứng dụng

### 11.1. Lưu timestamp của một sự kiện đã xảy ra

Dữ liệu “giao dịch được tạo lúc nào” nên có một mốc tuyệt đối như `Instant`:

```java
Instant createdAt = Instant.parse("2024-07-15T12:00:00Z");
ZonedDateTime localView =
        createdAt.atZone(ZoneId.of("Europe/Paris"));
// 2024-07-15T14:00+02:00[Europe/Paris].
```

Có thể lưu Instant dưới dạng ISO-8601 UTC hoặc epoch với **đơn vị rõ ràng**. Khi hiển thị, chuyển từ Instant sang `ZoneId` của người đọc. Nếu cần phục vụ kiểm toán, có thể lưu thêm offset/region dùng khi hiển thị hoặc chính sách giữ tzdb version theo yêu cầu; nhưng không suy đoán nó chỉ từ offset.

### 11.2. Lưu lịch hẹn hoặc lịch định kỳ theo địa phương

Nhu cầu “hàng tuần vào 09:00 sáng tại Paris” phải giữ **local time + region zone** và chính sách DST. Nếu chỉ lưu `+01:00`, lịch sẽ sai vào mùa hè khi Paris dùng +02 trong ví dụ năm 2024.

Đối với một lịch hẹn cụ thể đã xác nhận đúng Instant, có thể lưu cả `Instant` của lần hẹn và thông tin vùng/local của lịch. Khi tạo kỳ tiếp theo, tính theo **ngày-giờ địa phương tại region** rồi mới chuyển sang Instant. Không lặp cộng 7×24 giờ trên Instant nếu yêu cầu là “đúng 09:00 giờ địa phương mỗi tuần” quanh DST.

### 11.3. Nếu API chỉ trả về offset thì không thể suy ra region duy nhất

Một chuỗi như `2024-07-15T14:00:00+02:00` cho đủ thông tin xác định một Instant, nhưng **không chứng minh** thời gian này ở Paris. Nhiều vùng có thể cùng dùng +02 tại một thời điểm. Vì vậy:

```java
OffsetDateTime supplied = OffsetDateTime.parse(
        "2024-07-15T14:00:00+02:00");

Instant event = supplied.toInstant();
```

Nếu nghiệp vụ cần vùng, đòi hỏi cung cấp một ID vùng riêng. Không lấy `+02:00` rồi đoán là `Europe/Paris` bằng mapping hardcode.

### 11.4. Cấu hình và test bằng Clock

```java
Clock productionClock = Clock.systemUTC();

Clock fixedTestClock = Clock.fixed(
        Instant.parse("2024-01-15T12:00:00Z"),
        ZoneId.of("Europe/Paris"));

ZonedDateTime reproducible = ZonedDateTime.now(fixedTestClock);
// 2024-01-15T13:00+01:00[Europe/Paris].
```

Trong ứng dụng, inject `Clock` và `ZoneId` nghiệp vụ vào service; dùng `Clock.fixed` trong test. `ZonedDateTime.now()` không truyền clock/zone có thể phụ thuộc timezone hệ điều hành và thời gian thực, khiến test không lặp lại.

### 11.5. Timezone database phải được quản lý

Quy tắc zone là dữ liệu được nhà cung cấp runtime cập nhật. Các nước có thể thay luật DST hoặc offset; một lịch hẹn tương lai tính lại trên tzdb mới có thể được ánh xạ sang Instant khác so với trước. Nếu hệ thống dùng lịch hẹn dài hạn, phải có policy về **vùng chuẩn, version dữ liệu quy tắc, thời điểm tái tính và thông báo thay đổi**.

Không trông chờ `ZoneId` tự mang một bản sao vĩnh viễn của toàn bộ rules. JavaDoc phân biệt ID ổn định với `ZoneRules` có thể được cập nhật. Không dùng `java.util.TimeZone` / `Calendar` cho thiết kế ngày giờ mới nếu `java.time` đáp ứng được yêu cầu; chỉ chuyển đổi các API cũ tại ranh giới tích hợp cần tương thích.

## 12. Lỗi phổ biến khi dùng ZoneId và offset

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `Europe/Paris == +01:00` quanh năm | Sai vào mùa hè theo ví dụ 2024 | Dùng region ID và rules |
| Cho rằng mọi `ZoneId` là vùng có DST | `ZoneOffset` cũng là `ZoneId`; tiền tố UTC có fixed rules | Kiểm tra loại/quy tắc đúng |
| Coi `+07:00` là định danh duy nhất của Việt Nam | Offset không chứa địa danh/lịch sử | Lưu `Asia/Ho_Chi_Minh` nếu cần vùng |
| Hardcode UTC offset hiện tại cho sự kiện tương lai | Có thể sai khi đổi luật hoặc DST | Tính từ region ở thời điểm cần |
| Dùng `LocalDateTime` để đại diện timestamp tuyệt đối | Không có offset/zone | Dùng `Instant` hoặc `OffsetDateTime` phù hợp |
| Đổi timezone bằng `withZoneSameLocal` khi chỉ muốn hiển thị | Làm thay đổi Instant | `withZoneSameInstant` |
| Parse offset rồi đoán region | Nhiều region trùng offset | Yêu cầu region riêng |
| Chọn offset cho DST gap mà không kiểm tra | Local time không tồn tại trong vùng | `getValidOffsets` / `ofStrict` |
| Tự mặc định overlap chỉ có một Instant | Có thể lệch một giờ | Chọn offset bằng policy rõ |
| `getOffset(LocalDateTime)` được coi là kiểm tra duy nhất | Gap/overlap cần xử lý riêng | `getValidOffsets` và `getTransition` |
| `now()` phụ thuộc default zone trong test | Test khác theo máy/thời gian | Inject `Clock.fixed` và ZoneId |
| Coi `plusDays(1)` bằng đúng 24 giờ thực | Không đúng quanh DST | Dùng `Duration` cho elapsed time |
| Nghĩ `UTC+07:00` là region ID | Đây là ID dạng offset, fixed rules | Dùng IANA region khi cần địa lý |
| Dùng `Etc/GMT+7` vì nghĩ là UTC+7 | Nhóm ID Etc/GMT có dấu theo quy ước POSIX, dễ bị đảo | Dùng `+07:00` hoặc region ID rõ ràng |
| Không cập nhật tzdb/JDK | Quy tắc có thể cũ so với luật hiện hành | Quản lý bản vá runtime, kiểm thử lại lịch |

## 13. Bài tập tự kiểm tra

**Bài 1.** `ZoneId.of("Europe/Paris")` có cùng ý nghĩa với `ZoneOffset.ofHours(1)` không? — **Không**. Có thể cùng offset một số ngày; region Paris có rules theo thời điểm.

**Bài 2.** Tại sao `2024-07-15T12:00Z` hiển thị 14:00 ở Paris nhưng 13:00 với fixed +01? — Paris đang áp dụng +02 trong ví dụ, còn fixed +01 không đổi.

**Bài 3.** Một offset `+05:30` có hợp lệ không? — **Có**. Dùng `ZoneOffset.ofHoursMinutes(5,30)` hoặc `ZoneOffset.of("+05:30")`.

**Bài 4.** `ZoneId.of("UTC+07:00").normalized()` trả gì? — Một `ZoneOffset` tương ứng `+07:00` vì rules của nó cố định.

**Bài 5.** `getValidOffsets(local)` trả 0, 1, 2 có nghĩa gì? — Lần lượt **gap**, **bình thường**, **overlap**.

**Bài 6.** Trong overlap Paris 02:30 ngày 27/10/2024, hai offset hợp lệ là gì? — `+02:00` và `+01:00` trong tzdb đã dùng cho ví dụ.

**Bài 7.** Nếu đã có `Instant`, cách hiển thị theo Việt Nam? — `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))`.

**Bài 8.** Nếu muốn dịch cách hiển thị từ Paris sang UTC nhưng **không đổi Instant**, dùng gì? — `withZoneSameInstant(ZoneOffset.UTC)`.

**Bài 9.** `OffsetDateTime` có đủ thông tin để biết mã region IANA gốc không? — **Không**, nó giữ offset cụ thể, không phải tên khu vực.

**Bài 10.** Khi nào nên chọn `ZoneOffset`? — Khi dữ liệu/định dạng thực sự cần một **UTC offset cố định**, hoặc một bản ghi có offset đã biết; không dùng để thay thế region cho lịch địa phương xuyên các mùa.

**Bài 11.** Vì sao cần `Clock.fixed` trong unit test? — Tránh test phụ thuộc đồng hồ thật và zone mặc định, cho kết quả lặp lại.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — ZoneId](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): region IDs, fixed-offset IDs, `normalized` và cách nạp rules.
- [Oracle Java SE 26 — ZoneOffset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html): offset, phạm vi giá trị, các factory.
- [Oracle Java SE 26 — ZoneRules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): `getOffset`, `getValidOffsets`, `getTransition`, `isFixedOffset`.
- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): `ofStrict`, gap/overlap, `withZoneSameInstant` / `withZoneSameLocal`.
- [Oracle Java SE 26 — OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html): local date-time kèm offset, đổi sang Instant.
- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html) và [Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): mốc timeline, clock có thể kiểm thử.
- [Oracle Java SE 8 — java.time](https://docs.oracle.com/javase/8/docs/api/java/time/package-summary.html): đối chiếu các API đã có từ Java 8.

**Kết luận:** `ZoneOffset` là **con số độ lệch UTC bất biến**; region `ZoneId` là **mã để tra bộ quy tắc offset theo thời điểm**. Khi đã có Instant, chuyển sang region để hiển thị; khi chỉ có LocalDateTime, phải xác nhận vùng và xử lý DST gap/overlap. Giữ region ID cho lịch theo giờ địa phương; dùng Instant cho timestamp đã xảy ra; tránh hardcode offset hiện tại thành quy tắc cho tương lai.
