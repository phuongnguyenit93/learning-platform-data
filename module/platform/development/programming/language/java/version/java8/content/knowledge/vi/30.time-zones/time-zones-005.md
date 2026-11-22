# Giữ cùng thời điểm hoặc giữ cùng giờ địa phương khi đổi vùng (`ZonedDateTime`)

Một ngày giờ có múi giờ chứa hai câu chuyện khác nhau: **nó chỉ đúng khoảnh khắc nào trên dòng thời gian?** và **đồng hồ ở một địa điểm đang chỉ mấy giờ?** Khi đổi từ `Asia/Ho_Chi_Minh` sang `Europe/Paris` hoặc `America/New_York`, hai yêu cầu thường gặp là:

1. **Giữ cùng thời điểm (same instant):** sự kiện vẫn xảy ra tại đúng khoảnh khắc ban đầu; chỉ thay đổi cách biểu diễn ngày, giờ và offset theo vùng mới. Ví dụ đổi múi giờ **để hiển thị** một giao dịch đã xảy ra cho người ở nước khác.
2. **Giữ cùng giờ địa phương (same local):** cố giữ nguyên ngày và giờ đồng hồ đã chọn, nhưng áp dụng quy tắc offset của vùng mới; vì thế **thời điểm thực thường thay đổi**. Ví dụ chuyển **địa điểm tổ chức một cuộc hẹn 09:30** từ Việt Nam sang Paris, trong khi ban tổ chức yêu cầu buổi hẹn ở nơi mới cũng diễn ra lúc 09:30 địa phương.

Java 8 cung cấp hai phương thức chính trong `ZonedDateTime`: `withZoneSameInstant(ZoneId)` và `withZoneSameLocal(ZoneId)`. Chúng vẫn là API hiện hành. Ngoài ra, `OffsetDateTime` có `withOffsetSameInstant(ZoneOffset)` và `withOffsetSameLocal(ZoneOffset)`; khi chuyển từ một timestamp có offset sang một múi giờ vùng, còn có `atZoneSameInstant(ZoneId)` và `atZoneSimilarLocal(ZoneId)`.

**Lưu ý quan trọng:** `withZoneSameLocal` có nghĩa là "cố giữ cùng giờ địa phương **nếu hợp lệ**", không phải một lời hứa rằng mọi giờ đồng hồ đều tồn tại trong vùng đích. Tại điểm chuyển giờ mùa hè (DST), giờ có thể bị **bỏ qua (gap)** hoặc **lặp hai lần (overlap)**. Bài học giải thích chính xác điều đó và cách kiểm thử.

Các API dưới đây có từ Java 8 và vẫn áp dụng trên các JDK hiện đại; ví dụ hoàn chỉnh có thể biên dịch/chạy bằng JDK 17+.

## 1. Bốn thành phần cần phân biệt

| Kiểu | Dữ liệu nó mang | Điều có thể suy ra |
| --- | --- | --- |
| `Instant` | Một mốc thời gian thực trong UTC | Có thể đổi sang mọi `ZoneId` để hiển thị |
| `LocalDateTime` | Ngày + giờ đồng hồ, **không zone/offset** | Chưa đủ xác định một `Instant` |
| `ZoneId` | Tên vùng và quy tắc múi giờ, ví dụ `Europe/Paris` | Cho biết offset đúng tại một instant hoặc các offset hợp lệ của một local date-time |
| `ZonedDateTime` | Ngày giờ địa phương + vùng + offset được áp dụng | Có cả `toLocalDateTime()` và `toInstant()` |
| `ZoneOffset` | Độ lệch UTC cố định, ví dụ `+07:00` | Không mang lịch chuyển DST của một vùng |
| `OffsetDateTime` | Local date-time + offset cố định | Xác định được `Instant`, **không** lưu tên vùng IANA |

Chẳng hạn:

```text
Instant:         2026-01-20T02:30:00Z
ZoneId:          Asia/Ho_Chi_Minh
ZonedDateTime:   2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh]

Instant:         2026-01-20T02:30:00Z
ZoneId:          Europe/Paris
ZonedDateTime:   2026-01-20T03:30+01:00[Europe/Paris]
```

Đó là **hai cách nhìn của cùng một `Instant`**. Nếu buộc giờ đồng hồ Paris vẫn là 09:30, kết quả lại là:

```text
ZonedDateTime:   2026-01-20T09:30+01:00[Europe/Paris]
Instant:         2026-01-20T08:30:00Z
```

So với mốc ban đầu `02:30Z`, sự kiện đã **lùi sang một khoảnh khắc khác, muộn hơn 6 giờ thực**. Không có cách nào vừa giữ nguyên `Instant` vừa giữ nguyên `LocalDateTime` khi offset của hai vùng tại mốc đó khác nhau.

### Công thức nhắc lại

```text
local date-time = UTC date-time + offset
UTC date-time   = local date-time - offset
```

Với nguồn `09:30+07:00`: UTC = 02:30Z. Giữ **cùng instant** khi sang `+01:00`: giờ địa phương mới = 03:30. Giữ **cùng local 09:30** khi sang `+01:00`: UTC mới = 08:30Z.

## 2. So sánh hai phương thức `ZonedDateTime`

```java
ZonedDateTime sameInstant = original.withZoneSameInstant(targetZone);
ZonedDateTime sameLocal   = original.withZoneSameLocal(targetZone);
```

Đây là hai dòng minh họa; `original` là một `ZonedDateTime` và `targetZone` là `ZoneId`.

| Tiêu chí | `withZoneSameInstant(targetZone)` | `withZoneSameLocal(targetZone)` |
| --- | --- | --- |
| Mục tiêu | Bảo toàn **mốc thời gian thực** | Bảo toàn **giờ lịch địa phương nếu hợp lệ** |
| `getZone()` | Đổi thành vùng đích | Đổi thành vùng đích |
| `getOffset()` | Tính theo quy tắc vùng đích **tại instant cũ** | Chọn offset phù hợp với **local date-time cũ**, có thể phải điều chỉnh khi DST |
| `toInstant()` | **Không đổi** | **Thường đổi** nếu offset khác; có thể tình cờ bằng |
| `toLocalDateTime()` | Thường đổi ngày/giờ | Giữ nếu hợp lệ; **dịch lên** nếu rơi vào gap |
| DST gap/overlap | Không mơ hồ vì bắt đầu từ instant đã biết | Cần quy tắc giải quyết local time trong vùng đích |
| Ví dụ nghiệp vụ | Hiển thị một giao dịch cho người ở múi giờ khác | Chuyển lịch hẹn sang một địa điểm khác nhưng vẫn 09:30 ở địa điểm mới |

Hai phương thức tạo **đối tượng mới bất biến**; chúng không sửa `original`. `ZonedDateTime` là immutable và có thể sử dụng theo giá trị, không làm việc dựa vào identity của instance.

### Một lưu ý về chữ "cùng"

- Với `same instant`, **giá trị `toInstant()` mới bằng cũ**. Đây là bất biến của phép đổi.
- Với `same local`, **giá trị `toLocalDateTime()` mới bằng cũ nếu thời gian đó tồn tại trong vùng đích**. Khi gặp gap, không thể làm đúng cả điều kiện "cùng local" và "thuộc zone hợp lệ"; API ưu tiên tạo ngày giờ hợp lệ bằng cách điều chỉnh.
- Với hai vùng có cùng offset tại ngày đó, hai phép đổi có thể tình cờ trả cùng một mốc và cùng local fields. Việc trùng kết quả trong một test **không chứng minh** hai phương thức là tương đương trong mọi trường hợp.

## 3. Ví dụ nền: Việt Nam sang Paris

Dữ liệu nguồn là một sự kiện lúc `2026-01-20T02:30:00Z`, được biểu diễn tại Việt Nam:

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");

Instant event = Instant.parse("2026-01-20T02:30:00Z");
ZonedDateTime source = event.atZone(vietnam);
// 2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh].
```

### 3.1. Đổi vùng chỉ để người Paris xem **cùng sự kiện**

```java
ZonedDateTime displayInParis = source.withZoneSameInstant(paris);
// 2026-01-20T03:30+01:00[Europe/Paris].

boolean sameEvent =
    source.toInstant().equals(displayInParis.toInstant());
// true.
```

Ngày 20/01/2026, Paris ở offset `+01:00`. Vì thế cùng `02:30Z` hiển thị là `03:30` ở Paris, không phải `09:30`. Đây là phép đổi **đúng** với event log, giao dịch và sự kiện đã diễn ra.

### 3.2. Đổi **địa điểm** của lịch hẹn mà vẫn giữ 09:30

```java
ZonedDateTime rescheduledInParis = source.withZoneSameLocal(paris);
// 2026-01-20T09:30+01:00[Europe/Paris].

Instant newInstant = rescheduledInParis.toInstant();
// 2026-01-20T08:30:00Z.
```

Cùng ngày 20/01, cả Việt Nam và Paris đều đang có 09:30 địa phương, nhưng hai cuộc hẹn **khác instant**. Kết quả mới xảy ra sau cuộc hẹn Việt Nam 6 giờ thực.

Có thể kiểm tra bằng:

```java
boolean sameClock = source.toLocalDateTime()
    .equals(rescheduledInParis.toLocalDateTime()); // true

long differenceHours =
    Duration.between(source.toInstant(), newInstant).toHours();
// 6.
```

**Sai lầm nghiệp vụ điển hình:** người dùng chọn "hiển thị giao dịch theo giờ Paris", nhưng backend gọi `withZoneSameLocal(paris)`. Điều đó **thay đổi thời điểm giao dịch**, có thể khiến audit, SLA hoặc số liệu ngày sai. Phải gọi `withZoneSameInstant(paris)` hoặc xuất phát từ `Instant.atZone(paris)`.

## 4. Đổi vùng có thể đổi cả **ngày lịch**

Nếu thời điểm ban đầu nằm gần nửa đêm, `withZoneSameInstant` có thể tạo ngày khác tại vùng mới. Điều này là **đúng**, không phải lỗi chuyển đổi.

```java
Instant atUtcMidnight = Instant.parse("2026-01-20T00:30:00Z");

ZonedDateTime hcm = atUtcMidnight.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
// 2026-01-20T07:30+07:00[Asia/Ho_Chi_Minh].

ZonedDateTime ny = atUtcMidnight.atZone(
    ZoneId.of("America/New_York"));
// 2026-01-19T19:30-05:00[America/New_York].
```

Với một event, **ngày hiển thị thuộc về zone người xem hoặc nghiệp vụ**; không mặc định ngày UTC là ngày của mọi người dùng. Nếu tính báo cáo doanh thu theo `LocalDate` của chi nhánh, phải áp dụng đúng `ZoneId` khi phân nhóm.

Ngược lại, với dữ liệu là một **ngày lịch thuần** (ngày sinh, ngày nghỉ), **không nên** biến `LocalDate` thành `Instant` 00:00Z rồi chuyển vùng. Dùng đúng `LocalDate` để tránh vô tình làm ngày sinh đổi sang hôm trước tại zone âm.

## 5. `OffsetDateTime`: cùng quy tắc nhưng chỉ có offset

`OffsetDateTime` giữ local date-time và **offset cố định**, không giữ quy tắc DST của vùng. Hai phương thức tương ứng:

```java
OffsetDateTime offsetView = source.toOffsetDateTime();

OffsetDateTime asUtcSameInstant =
    offsetView.withOffsetSameInstant(ZoneOffset.UTC);

OffsetDateTime asUtcSameLocal =
    offsetView.withOffsetSameLocal(ZoneOffset.UTC);
```

Với `source` `09:30+07:00`:

```text
offsetView:        2026-01-20T09:30+07:00
asUtcSameInstant:  2026-01-20T02:30Z
asUtcSameLocal:    2026-01-20T09:30Z
```

Cách đầu **chuyển cách biểu diễn sang UTC** mà vẫn là `02:30Z`. Cách sau **gán lại offset UTC cho giờ đồng hồ 09:30**, khiến mốc thực thành `09:30Z`, tức lệch 7 giờ so với event ban đầu.

| API | Bảo toàn | Hợp đồng |
| --- | --- | --- |
| `OffsetDateTime.withOffsetSameInstant(offset)` | `Instant` | Local fields đổi theo chênh lệch offset |
| `OffsetDateTime.withOffsetSameLocal(offset)` | `LocalDateTime` | Instant đổi khi offset mới khác |
| `OffsetDateTime.toInstant()` | Mốc thực | Tách instant khỏi offset đã hiển thị |
| `Instant.atOffset(offset)` | Instant đầu vào | Tạo cách biểu diễn có offset cố định |

**Không dùng `withOffsetSameLocal(UTC)` để "chuẩn hóa timestamp về UTC"** trừ khi nghiệp vụ thật sự muốn **diễn giải lại** local clock của người dùng là UTC. Để chuẩn hóa instant, dùng `toInstant()` hoặc `withOffsetSameInstant(ZoneOffset.UTC)`.

### So `equals` và `isEqual`

`OffsetDateTime.equals(...)` xét cả local date-time và offset. Hai cách biểu diễn khác offset có thể **không `equals`** nhưng **cùng instant**:

```java
OffsetDateTime a =
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00");
OffsetDateTime b =
    OffsetDateTime.parse("2026-01-20T02:30:00Z");

boolean fullRepresentationEqual = a.equals(b);  // false
boolean timelineEqual = a.isEqual(b);           // true
```

Với `ZonedDateTime`, quy tắc tương tự: `equals` xét local date-time, offset và zone; `isEqual` hoặc `toInstant().equals(...)` xét mốc thời gian thực.

Khi kiểm thử `withZoneSameInstant`, nên so `Instant`. Khi kiểm thử mục tiêu giữ giờ địa phương, nên so `toLocalDateTime()` **và kiểm tra riêng gap/overlap**, không chỉ so chuỗi format.

## 6. `OffsetDateTime` chuyển sang **ZoneId vùng**

Nếu nhận một API timestamp có offset rồi cần đưa vào vùng IANA, Java còn có:

```java
OffsetDateTime input =
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00");

ZonedDateTime targetSameInstant =
    input.atZoneSameInstant(ZoneId.of("Europe/Paris"));

ZonedDateTime targetSimilarLocal =
    input.atZoneSimilarLocal(ZoneId.of("Europe/Paris"));
```

Trường hợp 20/01/2026:

- `atZoneSameInstant(paris)` → `2026-01-20T03:30+01:00[Europe/Paris]`.
- `atZoneSimilarLocal(paris)` → `2026-01-20T09:30+01:00[Europe/Paris]` nếu local time hợp lệ.

Tên phương thức thứ hai **là `SimilarLocal`**, không phải `SameLocal`; nó cố giữ local fields theo quy tắc `ZonedDateTime.ofLocal(...)` vì DST có thể ngăn giữ hoàn toàn như cũ.

Nếu một `OffsetDateTime` có offset gốc trùng **một offset hợp lệ tại local time của zone đích** khi xảy ra overlap, `atZoneSimilarLocal` sẽ **ưu tiên offset gốc**. Điều này có thể xác định lượt sớm/muộn của một giờ bị lặp. Nếu offset gốc không hợp lệ cho local time mới, quy tắc resolver sẽ chọn offset phù hợp theo hợp đồng `ofLocal`.

**Cẩn thận với `toZonedDateTime()`:** khi gọi trên `OffsetDateTime`, nó tạo `ZonedDateTime` có ZoneId là **chính fixed offset**, không tự suy ra region như `Europe/Paris`. Muốn region cụ thể, dùng `atZoneSameInstant(region)`/`atZoneSimilarLocal(region)` theo ý nghĩa nghiệp vụ.

## 7. DST: vì sao `withZoneSameLocal` không bảo đảm giữ 100% local time?

Một `ZoneId` vùng có **quy tắc thay đổi offset**. Ở giờ đổi DST, mỗi `LocalDateTime` có thể có:

| Trạng thái | `getValidOffsets(local)` | Ý nghĩa |
| --- | --- | --- |
| Bình thường | 1 offset | Một local time ứng với đúng một instant |
| **Gap** | 0 offset | Giờ đồng hồ **không tồn tại** |
| **Overlap** | 2 offset | Cùng một local time xuất hiện **hai lần** |

`ZoneRules.getValidOffsets(local)` giúp phân biệt trường hợp. Đối với một `Instant` đã biết, `ZoneRules.getOffset(instant)` xác định được một offset; không xảy ra mơ hồ như lúc bắt đầu từ `LocalDateTime`.

### 7.1. Gap tại New York: 02:30 không tồn tại

Tại `America/New_York`, ngày `2024-03-10` đồng hồ chuyển từ gần 02:00 sang 03:00. Local time `2024-03-10T02:30` thuộc gap:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);

List<ZoneOffset> offsets = ny.getRules().getValidOffsets(missing);
// [].
```

Giả sử người dùng chọn đúng local time `02:30` tại Việt Nam trước khi chuyển cuộc hẹn sang New York:

```java
ZonedDateTime source = ZonedDateTime.of(
    missing, ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime result = source.withZoneSameLocal(ny);
// 2024-03-10T03:30-04:00[America/New_York].
```

**Điều đáng chú ý:** yêu cầu "giữ 02:30 theo đồng hồ New York" **không khả thi** vào ngày đó. Theo resolver mặc định, Java dịch local time **lên bằng độ dài gap** (một giờ trong ví dụ), nên được `03:30`.

Nếu gọi:

```java
ZonedDateTime sameEvent = source.withZoneSameInstant(ny);
// 2024-03-09T14:30-05:00[America/New_York].
```

Nó giữ **instant của 02:30 ở Việt Nam** và chỉ tìm giờ địa phương New York tương ứng, không cần giải quyết giờ New York `02:30` bị thiếu. Vì xuất phát từ một instant hợp lệ, `withZoneSameInstant` tránh mơ hồ gap/overlap của local input.

**Hệ quả về API:** đừng báo cho người dùng rằng họ đã đặt lịch chính xác `02:30` trong vùng đích nếu backend đã tự dịch thành `03:30`. Có thể **từ chối** input hoặc công bố chính sách tự dịch và ghi lại giờ đã resolve.

### 7.2. Overlap: 01:30 có hai instant

Tại New York ngày `2024-11-03`, đồng hồ lùi từ giờ DST sang giờ tiêu chuẩn. `2024-11-03T01:30` xảy ra hai lần:

```java
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
List<ZoneOffset> valid = ny.getRules().getValidOffsets(overlap);
// [-04:00, -05:00].
```

Hai cách resolve:

```java
ZonedDateTime earlier = overlap.atZone(ny);
// 2024-11-03T01:30-04:00[America/New_York].

ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
// 2024-11-03T01:30-05:00[America/New_York].
```

Cùng **01:30 local**, nhưng:

- `earlier.toInstant()` = `2024-11-03T05:30:00Z`.
- `later.toInstant()` = `2024-11-03T06:30:00Z`.
- Hai instant cách nhau **60 phút thực**.

Có thể chủ động dùng `withEarlierOffsetAtOverlap()` hoặc `withLaterOffsetAtOverlap()` khi nghiệp vụ có chính sách cho hai lượt. Với ứng dụng đặt chỗ, nếu không thể tự suy ra mong muốn người dùng, nên yêu cầu chọn **offset/lượt 01:30** thay vì lấy mặc định mà không thông báo.

### 7.3. `withZoneSameLocal` và offset được ưu tiên

Bên dưới, `withZoneSameLocal` dùng logic tương đương `ZonedDateTime.ofLocal(localDateTime, targetZone, preferredOffset)`, với offset cũ là **ứng viên ưu tiên**:

- Nếu local date-time **hợp lệ duy nhất**, dùng offset hợp lệ của vùng đích.
- Nếu **overlap** và offset cũ **vẫn hợp lệ** trong vùng mới, có thể **giữ offset cũ**; nếu không, resolver chọn offset sớm theo quy tắc.
- Nếu **gap**, dịch local time **tiến lên theo độ dài gap**, dùng offset sau bước chuyển.
- Nếu thay về chính zone đang có, không có lý do thay mốc hoặc local field (đối tượng có thể được trả lại).

Đối với `OffsetDateTime.atZoneSimilarLocal`, offset của chính `OffsetDateTime` cũng được sử dụng như **preferred offset** khi phù hợp với zone đích.

Ví dụ chứng minh trường hợp giữ offset muộn trong overlap:

```java
OffsetDateTime chosenLater =
    OffsetDateTime.parse("2024-11-03T01:30:00-05:00");

ZonedDateTime result =
    chosenLater.atZoneSimilarLocal(ZoneId.of("America/New_York"));
// 2024-11-03T01:30-05:00[America/New_York].
```

Ở đây `-05:00` là một offset hợp lệ tại `01:30`, nên resolver không tự chuyển về `-04:00`. Nhưng đây vẫn không phải cơ chế kiểm chứng một lựa chọn mơ hồ ở biên API: khi nhận lịch đặt chỗ mới, hãy **xác nhận cả local time và offset hợp lệ** theo chính sách nghiệp vụ.

## 8. Khi cần **cấm** tự điều chỉnh hoặc tự chọn offset

Một hệ thống đặt vé, giao dịch tài chính hoặc lịch làm việc có thể cần **strict validation**:

1. Nhận `LocalDateTime` và `ZoneId` đích.
2. Gọi `zone.getRules().getValidOffsets(local)`.
3. Nếu có 0 offset: từ chối giờ không tồn tại hoặc yêu cầu người dùng chọn giờ khác.
4. Nếu có 2 offset: yêu cầu người dùng chọn một offset được phép hoặc dùng chính sách chọn "lượt đầu/lượt sau" đã công bố.
5. Nếu có đúng 1 offset: dùng `ZonedDateTime.ofStrict(local, offset, zone)`.
6. Sau đó mới xác định `Instant` để lưu/sắp lịch.

Một hàm minh họa chỉ nhận giờ **không mơ hồ**:

```java
static ZonedDateTime resolveStrict(LocalDateTime local, ZoneId zone) {
    List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
    if (valid.size() != 1) {
        throw new IllegalArgumentException(
            "Local time is missing or ambiguous");
    }
    return ZonedDateTime.ofStrict(local, valid.get(0), zone);
}
```

Hàm này dùng `java.time.*` và `java.util.*`, là ví dụ đặt trong một lớp, không phải chương trình độc lập. Nó từ chối cả gap lẫn overlap; nếu nghiệp vụ cho phép overlap, cần thêm tham số `selectedOffset` và xác thực trước khi `ofStrict`.

Nếu chuyển một lịch sang vùng khác và *bắt buộc giữ nguyên local clock*, hãy **kiểm tra tính hợp lệ trước khi đổi**, thay vì gọi `withZoneSameLocal` rồi âm thầm dùng kết quả đã dịch giờ.

### Vì sao `ZoneRules.getOffset(LocalDateTime)` chưa đủ?

Khi input là một `LocalDateTime`, có thể có 0 hoặc 2 offset. `getOffset(local)` trả về một **offset phù hợp theo chính sách mặc định**, không chứng minh local time là duy nhất hoặc thậm chí tồn tại. Muốn kiểm tra dữ liệu người dùng nhập, hãy dùng `getValidOffsets(local)` và/hoặc `getTransition(local)`.

## 9. Chọn phép đổi theo yêu cầu nghiệp vụ

| Tình huống | Hành động đúng ban đầu | Vì sao |
| --- | --- | --- |
| Giao dịch đã xảy ra 02:30Z, khách ở Paris muốn xem giờ địa phương | `instant.atZone(paris)` hoặc `zoned.withZoneSameInstant(paris)` | Giữ sự kiện, chỉ đổi cách hiển thị |
| Nhật ký hệ thống phục vụ audit xuyên vùng | Lưu `Instant`, chuyển vùng để hiển thị | Mốc thực không được bị đổi khi chọn timezone |
| Phân nhóm sự kiện theo **ngày địa phương** của người dùng | `instant.atZone(userZone).toLocalDate()` | Ngày địa phương có thể khác ngày UTC |
| Cuộc họp đổi địa điểm nhưng vẫn diễn ra lúc 09:30 nơi mới | Ghép local 09:30 + `ZoneId` mới và **resolve DST có chính sách** | Mốc thực thay đổi theo offset vùng mới |
| Lịch lặp "09:30 thứ Hai tại New York" | Giữ `LocalTime`, quy tắc lịch, `ZoneId`; tính mỗi occurrence | Không thể cộng cố định số giây qua các lần DST |
| SLA đúng 24 giờ sau một sự kiện | `Instant.plus(Duration.ofHours(24))` | Đo thời gian thực, không phải ngày lịch |
| "Cùng giờ ngày mai" tại một địa điểm | Phép toán lịch địa phương, có chính sách DST | Một ngày địa phương có thể 23/25 giờ |
| Client chỉ gửi `LocalDateTime` không zone | Yêu cầu thêm vùng hoặc quy tắc hợp đồng | Không thể tự suy ra instant duy nhất |
| API nhận timestamp có offset và cần đổi cách xem sang vùng IANA | `OffsetDateTime.atZoneSameInstant(zone)` | Offset gốc đã xác định instant |
| API nhận timestamp có offset nhưng phải **gán lại** giờ đồng hồ cho vùng mới | `atZoneSimilarLocal(zone)` + validation gap/overlap | Cố giữ giờ địa phương, phải biết chính sách giải quyết |

### Chuyển vùng hiển thị không được biến thành sửa event

Trong code review, những tên hàm như `convertTimeZone` hoặc `toLocal` thường mơ hồ. Nên đặt tên theo **bất biến muốn giữ**:

- `displayInstantAtZone(instant, viewerZone)`.
- `moveLocalAppointmentToZone(localDateTime, targetZone, policy)`.
- `resolveScheduledLocalTime(localDateTime, zoneId, selectedOffset)`.

Ngữ nghĩa nằm trong hợp đồng, không nằm ở việc nhìn thấy chữ "zone" trong tên API. Nếu chỉ đổi vị trí người xem, không nên có một thao tác làm thay đổi timestamp lưu trữ.

## 10. Thiết kế API và lưu trữ: bảo toàn ý nghĩa đầu vào

### 10.1. Event đã xảy ra: dữ liệu nền là `Instant`

Payload ISO có offset rõ:

```json
{
  "eventId": "evt-42",
  "occurredAt": "2026-01-20T02:30:00Z"
}
```

Để hiển thị cho người ở Paris, trả hoặc tính `2026-01-20T03:30:00+01:00` từ **cùng instant**. Không ghi đè `occurredAt` thành instant khác chỉ vì client chọn vùng hiển thị mới.

Nếu đầu vào là `2026-01-20T09:30:00+07:00`, parse `OffsetDateTime` rồi lấy `toInstant()`; cùng mốc `02:30Z`. Nếu cần phục vụ chứng từ gốc, lưu **offset/chuỗi đầu vào riêng** theo chính sách audit; `Instant` không giữ tên vùng/offset trình bày ban đầu.

### 10.2. Lịch dự định: lưu `LocalDateTime + ZoneId`

Payload đặt lịch theo địa điểm:

```json
{
  "localStart": "2026-01-20T09:30:00",
  "timeZoneId": "Europe/Paris"
}
```

Backend phải resolve theo quy tắc Paris tại ngày đó, xử lý gap/overlap rõ ràng và lưu `Instant` nếu lịch đã chốt. Với lịch hẹn tương lai chịu cập nhật tzdb, ứng dụng nên quyết định **giữ instant đã xác nhận** hay **giữ ý định local** khi quy tắc zone thay đổi.

Các dữ liệu khác nhau có thể cần các field khác nhau:

- `createdAt`/`confirmedAt`: `Instant`.
- `plannedLocalStart`: `LocalDateTime`.
- `plannedTimeZoneId`: string zone IANA, ví dụ `Europe/Paris`.
- `resolvedStartAt`: `Instant` sau khi xác nhận.
- `chosenOffset`: chỉ lưu riêng nếu cần phân biệt overlap/audit hoặc replay đúng lựa chọn.

Không dùng một cột `TIMESTAMP` mơ hồ cho cả ba ý nghĩa. PostgreSQL `timestamptz` biểu diễn mốc thực nhưng **không lưu tên IANA region gốc**; muốn phục hồi vùng lịch đã chọn, phải lưu zone ID ở trường riêng. Quy tắc mapping cụ thể của JDBC/ORM/DB phải được kiểm tra trên triển khai thực.

### 10.3. Không suy timezone từ `ZoneOffset`

`+01:00` không đồng nghĩa với `Europe/Paris` vì offset đó có thể thuộc nhiều vùng; Paris cũng có thể `+02:00` vào mùa hè. `OffsetDateTime` không đủ mô hình hóa lịch hẹn tái diễn theo IANA rules.

Nếu user yêu cầu "09:30 ở Paris", lưu region `Europe/Paris`. Nếu user chỉ gửi `09:30+01:00`, bạn biết một instant khi có ngày nhưng **không biết chắc vị trí địa lý hoặc quy tắc tương lai**.

## 11. `plusDays`, `Duration` và việc giữ giờ đồng hồ

Ngoài đổi zone, một nguồn lỗi phổ biến là dùng phép cộng theo timeline khi nghiệp vụ muốn giữ local clock.

| Yêu cầu | Phép toán thường phù hợp |
| --- | --- |
| 24 giờ thực tiếp theo | `instant.plus(Duration.ofHours(24))` |
| Cùng giờ địa phương ngày mai | `zoned.plusDays(1)` với chính sách DST |
| Cuộc họp mỗi thứ Hai lúc 09:30 | Quy tắc lịch theo `LocalDate/LocalTime/ZoneId`, resolve từng lần |
| Tính độ dài thực giữa hai mốc | `Duration.between(a.toInstant(), b.toInstant())` |
| Tính khoảng theo ngày/tháng/năm lịch | `Period` hoặc phép toán calendar |

Với DST, một ngày tại New York có thể dài 23 hoặc 25 giờ thực. `ZonedDateTime.plusDays(1)` là phép toán theo **local timeline** và giải quyết offset theo quy tắc; còn cộng `Duration.ofDays(1)` theo instant timeline là **24 giờ thực**. Việc hai kết quả khác nhau không tự có nghĩa một kết quả sai; câu hỏi là **nghiệp vụ cần bất biến nào**.

## 12. Kiểm thử đúng bất biến và không lệ thuộc hệ điều hành

Đừng chỉ kiểm tra output chuỗi sau một phép đổi timezone. Test nên đặt **bất biến** cụ thể:

```java
ZonedDateTime original = /* một datetime đã có zone */;
ZoneId target = ZoneId.of("Europe/Paris");

ZonedDateTime view = original.withZoneSameInstant(target);
if (!original.toInstant().equals(view.toInstant())) {
    throw new AssertionError("Instant changed");
}
```

Đây là snippet minh họa: phải thay comment bằng `ZonedDateTime` thật trước khi chạy.

Với same-local ở **giờ hợp lệ**:

```java
ZonedDateTime moved = original.withZoneSameLocal(target);
boolean localKept =
    original.toLocalDateTime().equals(moved.toLocalDateTime());
```

Nhưng nếu local time đích rơi vào gap, `localKept` hợp lệ có thể bằng `false`. Không test `withZoneSameLocal` bằng cách ép giữ local time **cho mọi vùng và mọi ngày**; thay bằng test quyết định nghiệp vụ khi gap/overlap.

### Bộ test nên có

- Chuyển Việt Nam → Paris vào mùa đông và mùa hè (offset Paris khác nhau).
- Chuyển sang vùng UTC âm để kiểm tra **ngày có thể lùi**.
- Giữ instant với cùng/different zone và so `toInstant()`.
- Giữ local hợp lệ và so `toLocalDateTime()`.
- Gap tại `America/New_York` `2024-03-10T02:30`: **không có offset hợp lệ**, same-local được dịch lên 03:30 theo resolver.
- Overlap `2024-11-03T01:30`: có hai offset `-04:00`, `-05:00`; cả hai đều là local 01:30 nhưng khác instant một giờ.
- Bảo toàn preferred offset khi `atZoneSimilarLocal` gặp overlap và offset gốc còn hợp lệ.
- `OffsetDateTime.withOffsetSameInstant` vs `withOffsetSameLocal`.
- Input zone ID/offset không hợp lệ và trường null; đáp ứng lỗi rõ.
- Các nguồn `Clock.fixed(...)` trong test có thời gian hiện tại, thay vì phụ thuộc ngày/giờ máy CI.
- Đối với DB/API, round-trip timestamp khác offset nhưng cùng instant; định nghĩa precision trước khi dùng `equals`.
- Khi đổi zone theo UI, **mốc lưu trữ không đổi** và thứ tự các event vẫn theo instant.
- Với lịch lặp, case trước/sau DST theo local clock.
- Nếu dùng tzdb tùy phiên bản môi trường, test với dữ liệu/cấu hình đã biết và quy định chính sách cập nhật.

## 13. Chương trình Java hoàn chỉnh và kết quả chạy thật

Tạo file **`ZoneConversionSemanticsDemo.java`**. Chương trình dùng các API hiện có từ Java 8, chạy được với JDK 17+; không cần thư viện ngoài. Nó kiểm tra cả hai phép đổi, `OffsetDateTime`, gap/overlap và ưu tiên offset trong overlap. Các `check(...)` sẽ ném `AssertionError` nếu bất biến không đúng.

```java
import java.time.*;
import java.util.*;

public class ZoneConversionSemanticsDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneId ny = ZoneId.of("America/New_York");
        Instant event = Instant.parse("2026-01-20T02:30:00Z");

        ZonedDateTime source = event.atZone(vietnam);
        ZonedDateTime sameInstant = source.withZoneSameInstant(paris);
        ZonedDateTime sameLocal = source.withZoneSameLocal(paris);

        check(source.toInstant().equals(sameInstant.toInstant()),
                "same-instant changed the instant");
        check(source.toLocalDateTime().equals(sameLocal.toLocalDateTime()),
                "same-local changed a valid local date-time");
        check(!source.toInstant().equals(sameLocal.toInstant()),
                "same-local should represent another instant");

        System.out.println("source VN: " + source);
        System.out.println("Paris same instant: " + sameInstant);
        System.out.println("Paris same local: " + sameLocal);
        System.out.println("preserved instant: " +
                source.toInstant().equals(sameInstant.toInstant()));
        System.out.println("preserved local: " +
                source.toLocalDateTime().equals(sameLocal.toLocalDateTime()));
        System.out.println("same-local instant: " + sameLocal.toInstant());
        System.out.println("instant difference hours: " +
                Duration.between(source.toInstant(), sameLocal.toInstant())
                        .toHours());

        OffsetDateTime offsetView = source.toOffsetDateTime();
        OffsetDateTime offsetSameInstant =
                offsetView.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime offsetSameLocal =
                offsetView.withOffsetSameLocal(ZoneOffset.UTC);
        System.out.println("offset same instant: " + offsetSameInstant);
        System.out.println("offset same local: " + offsetSameLocal);
        System.out.println("offset instant preserved: " +
                offsetView.toInstant().equals(offsetSameInstant.toInstant()));

        LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);
        ZonedDateTime missingFromVn = ZonedDateTime.of(missing, vietnam);
        ZonedDateTime adjusted = missingFromVn.withZoneSameLocal(ny);
        ZonedDateTime displaySameEvent =
                missingFromVn.withZoneSameInstant(ny);

        System.out.println("NY gap offsets: " +
                ny.getRules().getValidOffsets(missing));
        System.out.println("gap same local adjusted: " + adjusted);
        System.out.println("gap same instant: " + displaySameEvent);
        System.out.println("gap local identical: " +
                missing.equals(adjusted.toLocalDateTime()));

        LocalDateTime ambiguous = LocalDateTime.of(2024, 11, 3, 1, 30);
        ZonedDateTime early = ambiguous.atZone(ny);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();
        System.out.println("NY overlap offsets: " +
                ny.getRules().getValidOffsets(ambiguous));
        System.out.println("NY overlap earlier: " + early);
        System.out.println("NY overlap later: " + late);
        System.out.println("overlap instant gap minutes: " +
                Duration.between(early.toInstant(), late.toInstant())
                        .toMinutes());

        OffsetDateTime chosenLater =
                OffsetDateTime.parse("2024-11-03T01:30:00-05:00");
        System.out.println("similar local preferred offset: " +
                chosenLater.atZoneSimilarLocal(ny));
        System.out.println("same instant conversion: " +
                chosenLater.atZoneSameInstant(ny));

        check(ny.getRules().getValidOffsets(missing).isEmpty(),
                "DST gap should have no valid offsets");
        check(ny.getRules().getValidOffsets(ambiguous).size() == 2,
                "DST overlap should have two valid offsets");
        check(adjusted.toLocalTime().equals(LocalTime.of(3, 30)),
                "gap adjustment");
        check(Duration.between(early.toInstant(), late.toInstant())
                .equals(Duration.ofHours(1)), "overlap difference");
        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ZoneConversionSemanticsDemo.java
java ZoneConversionSemanticsDemo
```

Đầu ra chuẩn đã kiểm chứng:

```text
source VN: 2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh]
Paris same instant: 2026-01-20T03:30+01:00[Europe/Paris]
Paris same local: 2026-01-20T09:30+01:00[Europe/Paris]
preserved instant: true
preserved local: true
same-local instant: 2026-01-20T08:30:00Z
instant difference hours: 6
offset same instant: 2026-01-20T02:30Z
offset same local: 2026-01-20T09:30Z
offset instant preserved: true
NY gap offsets: []
gap same local adjusted: 2024-03-10T03:30-04:00[America/New_York]
gap same instant: 2024-03-09T14:30-05:00[America/New_York]
gap local identical: false
NY overlap offsets: [-04:00, -05:00]
NY overlap earlier: 2024-11-03T01:30-04:00[America/New_York]
NY overlap later: 2024-11-03T01:30-05:00[America/New_York]
overlap instant gap minutes: 60
similar local preferred offset: 2024-11-03T01:30-05:00[America/New_York]
same instant conversion: 2024-11-03T01:30-05:00[America/New_York]
all checks passed
```

### Diễn giải kết quả dễ nhầm

1. **VN → Paris same instant:** 09:30 Việt Nam tương ứng 03:30 Paris, vẫn là 02:30Z.
2. **VN → Paris same local:** cả hai đều 09:30 trên đồng hồ nhưng mốc mới là 08:30Z, lệch 6 giờ.
3. **Offset UTC:** `withOffsetSameInstant(UTC)` tạo 02:30Z; `withOffsetSameLocal(UTC)` tạo 09:30Z.
4. **Gap:** 02:30 ngày 10/03/2024 ở New York không tồn tại nên `withZoneSameLocal` trả 03:30; `withZoneSameInstant` từ instant Việt Nam lại là ngày 09/03/2024 lúc 14:30 New York.
5. **Overlap:** 01:30 tại New York có `-04:00` và `-05:00`, hai mốc cách nhau 60 phút.
6. **Ưu tiên offset:** `OffsetDateTime` 01:30-05:00 chuyển sang vùng New York với `atZoneSimilarLocal` giữ `-05:00` vì nó hợp lệ trong overlap.
7. **Assertion:** chương trình in `all checks passed` chỉ khi cả các kiểm tra bất biến và DST đều đúng.

Các ví dụ DST trên sử dụng quy tắc timezone cho New York năm 2024; Java lấy rules từ tzdb cung cấp bởi JDK. Với ứng dụng yêu cầu tái lập lịch sử pháp lý khi tzdb có thể thay đổi, cần xác định phiên bản quy tắc và chính sách audit tương ứng.

## 14. Những lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `withZoneSameLocal` để đổi timezone hiển thị event | Thay đổi instant của giao dịch/sự kiện | `withZoneSameInstant` |
| Dùng `withZoneSameInstant` để giữ lịch 09:30 khi đổi địa điểm | Giờ đồng hồ vùng mới bị đổi | Local date-time + `ZoneId` + chính sách resolve |
| Nghĩ `withZoneSameLocal` bảo đảm local time không đổi trong mọi DST | Gap không có giờ hợp lệ; Java dịch giờ lên | Kiểm tra `getValidOffsets`, công bố/từ chối theo policy |
| Chỉ so `toString()` khi cần chứng minh cùng instant | Chuỗi có thể khác zone/offset dù cùng mốc | So `toInstant()` |
| Chỉ so `equals` giữa hai `ZonedDateTime` khác vùng | `equals` xét zone/local fields, không chỉ mốc | `isEqual`/`toInstant` |
| Dùng `withOffsetSameLocal(UTC)` để chuẩn hóa API UTC | Gán UTC cho giờ đồng hồ, làm sai instant | `toInstant` hoặc `withOffsetSameInstant(UTC)` |
| Nghĩ `OffsetDateTime` chứa tên region | Nó chỉ có offset, không có IANA ZoneId | Lưu `ZoneId` riêng nếu cần |
| Gọi `OffsetDateTime.toZonedDateTime` rồi nghĩ Java tự chọn Paris | Nó dùng fixed offset như ZoneId | `atZoneSameInstant(paris)` |
| Không phân biệt `atZoneSameInstant` và `atZoneSimilarLocal` | Chuyển timestamp sai mốc | Chọn bất biến theo nghiệp vụ |
| Coi offset New York luôn -05:00 | DST mùa hè dùng -04:00 | Tra `ZoneRules` tại mốc/ngày cụ thể |
| Không xử lý overlap 01:30 hai lần | Có thể chốt sai một trong hai instant | Chọn offset/lượt sớm hoặc muộn rõ ràng |
| Gọi `getOffset(local)` để xác nhận không mơ hồ | Có thể trả một offset ưu tiên ngay cả gap/overlap | `getValidOffsets(local)` và strict policy |
| Dùng `Duration.ofDays(1)` cho lịch "cùng giờ ngày mai" | Có thể lệch 1 giờ khi DST | Calendar local operation và resolve |
| Nghĩ mọi ngày địa phương dài đúng 24 giờ | Gap/overlap khiến 23/25 giờ | Tính ranh giới theo zone |
| Lưu `LocalDateTime` như một timestamp tuyệt đối | Không có offset/zone, không biết instant | `Instant` hoặc ISO offset-aware |
| Lưu chỉ instant cho lịch địa phương lặp lại | Mất quy tắc giờ đồng hồ mong muốn | LocalDate/LocalTime + ZoneId + recurrence |
| Lấy timezone mặc định server làm zone người dùng | Khi deploy sang khu vực khác, kết quả đổi | Nhận ZoneId từ domain/user config |
| So timestamp chuỗi khác offset bằng từ điển | Thứ tự chuỗi không phản ánh timeline | Parse `Instant` và so |
| Chuyển giờ trước khi xử lý precision DB | Có thể mất nano và làm test bằng object sai | Thống nhất precision, integration test |
| Tự trừ 7/8 giờ bằng số cứng trong code | DST và quy tắc vùng có thể đổi | Dùng `java.time`, ZoneId/ZoneRules |
| Giữ preferred offset không hợp lệ trong vùng mới | Vi phạm quy tắc local time | `ofStrict` hoặc resolver hợp lệ |
| Mặc định mọi lịch đã chốt phải tính lại khi tzdb đổi | Có thể làm lịch đã xác nhận dịch instant | Quy định rõ source of truth & policy |

## 15. Bài tập thực hành có lời giải

### Bài 1 — Hiển thị cùng sự kiện

Một đơn hàng tạo lúc `2026-01-20T02:30:00Z`. Người dùng ở Việt Nam và Paris phải thấy hai giờ khác nhau. Có tạo hai `Instant` trong database không?

**Đáp án:** Không. Lưu một `Instant`. Mỗi UI gọi `instant.atZone(userZone)` hoặc `withZoneSameInstant(zone)` để hiển thị. Giờ Việt Nam là 09:30, Paris mùa đông là 03:30, nhưng mốc thực giống nhau.

### Bài 2 — Chuyển buổi họp 09:30 sang Paris

Một cuộc họp dự định `2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh]` được **chuyển địa điểm tổ chức** sang Paris, yêu cầu "vẫn lúc 09:30 địa phương". Phép đổi nào có ý nghĩa?

**Đáp án:** Giữ local date-time và resolve theo `Europe/Paris`, có thể dùng `withZoneSameLocal(paris)` nếu chấp nhận resolver. Tại ngày đó 09:30 Paris là `08:30Z`, không còn `02:30Z`. Với dữ liệu lịch quan trọng, validate DST trước khi chốt.

### Bài 3 — Giữ instant hay giữ local?

`2026-01-20T09:30+07:00` đổi sang UTC bằng `withOffsetSameInstant(UTC)` được gì? Bằng `withOffsetSameLocal(UTC)` được gì?

**Đáp án:** Same instant → `2026-01-20T02:30Z`; same local → `2026-01-20T09:30Z`. Hai kết quả cách nhau 7 giờ.

### Bài 4 — Gap tại New York

Một người yêu cầu lịch đúng `2024-03-10T02:30` ở New York. `withZoneSameLocal(ny)` có giữ nguyên 02:30 được không?

**Đáp án:** Không. Giờ đó không tồn tại. Theo resolver mặc định, nó được dịch lên `03:30-04:00`. Nếu nghiệp vụ cấm tự dịch, kiểm tra `getValidOffsets(local)` rồi từ chối.

### Bài 5 — Overlap hai lựa chọn

`2024-11-03T01:30` ở New York có hai offset nào và cách nhau bao lâu?

**Đáp án:** `-04:00` và `-05:00`. Hai instant tương ứng là `05:30Z` và `06:30Z`, lệch 60 phút. Có thể chọn bằng `withEarlierOffsetAtOverlap`/`withLaterOffsetAtOverlap` hoặc strict policy.

### Bài 6 — Dùng `atZoneSimilarLocal`

Một `OffsetDateTime` `2024-11-03T01:30-05:00` chuyển sang `America/New_York` bằng `atZoneSimilarLocal`. Offset nào được chọn?

**Đáp án:** `-05:00` vì là một offset hợp lệ trong overlap và được ưu tiên từ giá trị gốc. Không có lý do tự chuyển về `-04:00`.

### Bài 7 — Ngày địa phương khác UTC

Event là `2026-01-20T00:30Z`. Ngày giờ ở New York là bao nhiêu?

**Đáp án:** `2026-01-19T19:30-05:00`. Đổi bằng `instant.atZone(ZoneId.of("America/New_York"))`; giữ instant, nhưng ngày địa phương lùi một ngày.

### Bài 8 — Lịch lặp qua DST

Một lớp học ở New York bắt đầu 09:00 mỗi thứ Hai. Có thể lưu một instant và cứ cộng đúng 168 giờ cho mỗi buổi không?

**Đáp án:** Không nếu yêu cầu là **09:00 theo đồng hồ New York** ở mọi lần. Giữ quy tắc lịch + `LocalTime 09:00` + `ZoneId`, resolve từng ngày với policy DST.

### Bài 9 — Kiểm thử invariants

Hai phương thức `ZonedDateTime` nên được kiểm tra bằng field nào?

**Đáp án:** `withZoneSameInstant` → so `toInstant()` giữa trước và sau. `withZoneSameLocal` → so `toLocalDateTime()` **ở giờ hợp lệ**, đồng thời test riêng gap/overlap để chấp nhận hoặc từ chối theo nghiệp vụ.

### Bài 10 — Chỉ có offset, thiếu vùng

API nhận `2026-01-20T09:30:00+07:00`, có suy ra chắc chắn zone là `Asia/Ho_Chi_Minh` không?

**Đáp án:** Không. Offset +07:00 có thể thuộc nhiều khu vực. Nếu cần múi giờ vùng để tính lịch tương lai, API phải nhận `ZoneId` riêng.

## 16. Checklist khi review code

- [ ] Đã nêu rõ yêu cầu **giữ cùng Instant** hay **giữ cùng LocalDateTime**?
- [ ] Với event, log, transaction, SLA: ưu tiên bất biến instant khi đổi vùng?
- [ ] Với lịch hẹn/lịch lặp: giữ ý định local + region và giải quyết đúng theo DST?
- [ ] Dùng `withZoneSameInstant` thay vì `withZoneSameLocal` cho thay đổi chỉ thuộc UI?
- [ ] Nếu dùng `withZoneSameLocal`, đã xác định chính sách gap/overlap?
- [ ] Khi nhập giờ thiếu, đã từ chối hoặc công bố giờ bị dịch?
- [ ] Khi giờ bị lặp, đã chọn offset/lượt 01:30 phù hợp nghiệp vụ?
- [ ] Kiểm tra `getValidOffsets` thay vì đoán offset của local time?
- [ ] Đã phân biệt `OffsetDateTime.withOffsetSameInstant`/`withOffsetSameLocal`?
- [ ] Khi từ `OffsetDateTime` sang region, chọn `atZoneSameInstant`/`atZoneSimilarLocal` đúng?
- [ ] Có hiểu `toZonedDateTime()` của `OffsetDateTime` chỉ giữ fixed-offset zone?
- [ ] API timestamp tuyệt đối có offset rõ (ISO), lịch địa phương có ZoneId IANA?
- [ ] Schema DB bảo toàn instant và/hoặc local schedule theo đúng ý nghĩa?
- [ ] Không dựa vào timezone mặc định của máy chủ, driver hoặc giao diện?
- [ ] Các mốc gần nửa đêm được test qua nhiều vùng UTC dương/âm?
- [ ] Có kiểm tra mùa đông/mùa hè của vùng có DST, lịch lặp và ngày 23/25 giờ?
- [ ] So `Instant` khi kiểm tra "cùng thời điểm"; không chỉ so string hay `equals` đầy đủ?
- [ ] Test dùng ngày và ZoneId cố định, có chính sách tzdb update?
- [ ] Code ví dụ/prod không sử dụng API đã lỗi thời; chuẩn `java.time` đang được hỗ trợ?

**Ghi nhớ:** khi đổi vùng, **`withZoneSameInstant` giữ cùng sự kiện**, còn **`withZoneSameLocal` cố giữ cùng giờ đồng hồ địa phương** và có thể **đổi instant**; riêng DST gap còn có thể khiến local time phải điều chỉnh. Đừng chọn phương thức từ tên "đổi timezone" chung chung; hãy chọn từ **bất biến nghiệp vụ cần được giữ**.

### Tài liệu chính thức còn được duy trì

- [`ZonedDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): `withZoneSameInstant`, `withZoneSameLocal`, `ofLocal`, `ofStrict`, `withEarlierOffsetAtOverlap`/`withLaterOffsetAtOverlap`.
- [`OffsetDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html): `withOffsetSameInstant`, `withOffsetSameLocal`, `atZoneSameInstant`, `atZoneSimilarLocal`.
- [`ZoneRules` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets(LocalDateTime)`, gap/overlap và offset theo instant.
- [`Instant` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): timeline và `atZone(ZoneId)`.
- [`ZoneId` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): region IDs và offset rules.
- [`Duration` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): đo thời lượng giữa hai instant.