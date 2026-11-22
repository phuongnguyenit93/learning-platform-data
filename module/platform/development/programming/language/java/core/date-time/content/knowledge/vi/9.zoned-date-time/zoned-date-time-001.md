# `ZonedDateTime`: ngày giờ địa phương, `ZoneId` và độ lệch đã xác định

Một `ZonedDateTime` trong Java không chỉ nói “ngày 27/10/2024 lúc 02:30”. Nó mô tả **ngày giờ địa phương trong một vùng múi giờ cụ thể và offset đã được giải quyết**. Nhờ vậy, đối tượng cũng xác định được **một `Instant` duy nhất** trên dòng thời gian UTC.

Ví dụ:

~~~text
2024-10-27T02:30+02:00[Europe/Paris]
└────── ngày giờ ────┘└offset┘└─ ZoneId ─┘
~~~

Ở đây:

- **`2024-10-27T02:30`** là các trường ngày, giờ trên đồng hồ địa phương (`LocalDateTime`).
- **`Europe/Paris`** là ID vùng múi giờ (`ZoneId`), giúp tra cứu quy tắc đổi offset theo thời gian.
- **`+02:00`** là offset UTC đã chọn cho ngày giờ đó (`ZoneOffset`).
- Toàn bộ giá trị tương ứng **`2024-10-27T00:30:00Z`** trên UTC timeline, thông qua `toInstant()`.

Cùng ngày `2024-10-27` tại Paris, còn có giá trị hợp lệ `2024-10-27T02:30+01:00[Europe/Paris]`, nhưng giá trị này lại tương ứng **`2024-10-27T01:30:00Z`**. Vì đồng hồ được chỉnh lùi khi kết thúc giờ mùa hè (DST), chỉ `LocalDateTime` cộng `ZoneId` chưa chắc phân biệt được hai lần 02:30; offset được chọn là phần không thể bỏ qua.

## 1. Ba lớp thông tin cần đọc từ một `ZonedDateTime`

| Thành phần | Java | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Ngày giờ địa phương | `getYear()`, `getMonthValue()`, `getDayOfMonth()`, `getHour()` hoặc `toLocalDateTime()` | `2024-10-27T02:30` | Giờ hiển thị trên đồng hồ ở vùng được chọn |
| Vùng múi giờ | `getZone()` | `Europe/Paris` | Danh tính vùng và bộ quy tắc lịch sử/tương lai |
| Offset đã xác định | `getOffset()` | `+02:00` | Độ lệch cụ thể so với UTC ở thời điểm đó |
| Instant suy ra | `toInstant()` | `2024-10-27T00:30:00Z` | Thời điểm duy nhất trên dòng thời gian |

`ZoneId` **không đồng nghĩa** `ZoneOffset`. `Europe/Paris` không phải “múi giờ `+01:00` mãi mãi”: theo quy tắc DST năm 2024, Paris sử dụng `+01:00` vào mùa đông và `+02:00` vào mùa hè. Offset được xác định bằng cách **kết hợp ngày giờ và quy tắc vùng** hoặc bắt đầu từ một instant đã biết.

Một `ZoneId` còn có thể là offset cố định, chẳng hạn `ZoneOffset.ofHours(7)`; nhưng khi nghiệp vụ gắn với một địa phương thực tế, nên dùng ID vùng IANA như `Asia/Ho_Chi_Minh` để mô hình hóa quy tắc vùng thay vì tự giả định offset cố định cho mọi thời kỳ.

## 2. Khác biệt với `LocalDateTime`, `OffsetDateTime` và `Instant`

| Kiểu | Chứa gì? | Có xác định được instant? | Dùng khi |
| --- | --- | --- | --- |
| `LocalDateTime` | Năm/tháng/ngày và đồng hồ, **không có zone/offset** | Chưa | Lịch hẹn theo giờ địa phương trước khi chọn vùng |
| `OffsetDateTime` | Local date-time + **offset** | Có | Truyền/lưu mốc có offset, không cần danh tính vùng |
| `ZonedDateTime` | Local date-time + **ZoneId + offset hợp lệ đã giải quyết** | Có | Ngày giờ ở một vùng có quy tắc đổi offset |
| `Instant` | Mốc UTC tuyệt đối | Có | Log, timestamp sự kiện, so sánh mốc toàn cầu |

Chẳng hạn `2026-01-15T07:30+07:00` (**`OffsetDateTime`**) chỉ ra `2026-01-15T00:30:00Z`, nhưng **không chứng minh** đây là Việt Nam: nhiều vùng có thể cùng offset. `2026-01-15T07:30+07:00[Asia/Ho_Chi_Minh]` (**`ZonedDateTime`**) bổ sung chính ID vùng.

`Instant` không mang ngày giờ địa phương hay region ID. Nếu đã có `Instant`, dùng `instant.atZone(zone)` để tạo một `ZonedDateTime` cho người xem, và `zoned.toInstant()` để quay lại mốc gốc. Hai vùng có thể có ngày giờ khác nhau nhưng **vẫn là một sự kiện**.

## 3. Cách tạo `ZonedDateTime`: bắt đầu từ đâu?

### 3.1. Từ instant đã biết — không mơ hồ

~~~java
Instant occurredAt = Instant.parse("2026-01-15T00:30:00Z");

ZonedDateTime inVietnam =
        occurredAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
// 2026-01-15T07:30+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime inLosAngeles =
        occurredAt.atZone(ZoneId.of("America/Los_Angeles"));
// 2026-01-14T16:30-08:00[America/Los_Angeles]
~~~

*Đây là đoạn mã đặt trong method với import các kiểu `java.time` cần thiết.*

Vì đầu vào đã xác định **một instant**, quy tắc `ZoneRules` sẽ xác định **một offset duy nhất tại instant đó**; chuyển `Instant → ZonedDateTime` không vướng sự mơ hồ DST. Hai local date-time có thể khác **cả ngày**, nhưng `inVietnam.toInstant().equals(inLosAngeles.toInstant())` vẫn là `true`.

Nếu đã có `ZonedDateTime` và cần đổi vùng mà **giữ nguyên sự kiện**, dùng `withZoneSameInstant(otherZone)`. Không dùng `withZoneSameLocal(otherZone)` cho yêu cầu này: phương thức sau cố giữ ngày giờ trên đồng hồ và có thể làm **thay đổi instant**.

### 3.2. Từ ngày giờ địa phương và vùng — có chính sách giải quyết

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);

ZonedDateTime resolved = local.atZone(paris);
// 2024-10-27T02:30+02:00[Europe/Paris]
~~~

*Đây là đoạn mã trong method, cần import `ZoneId`, `LocalDateTime`, `ZonedDateTime`.*

`atZone` áp dụng **quy tắc mặc định**: tại overlap nó thường chọn offset sớm hơn, còn tại gap sẽ điều chỉnh giờ tiến qua khoảng trống. Cách chọn này mang tính kỹ thuật; với bài toán đặt lịch hoặc thanh toán đòi chính xác, cần kiểm tra gap/overlap và quyết định theo chính sách nghiệp vụ.

Một chương trình có thể tạo trực tiếp bằng `ZonedDateTime.of(year, month, day, hour, minute, second, nano, zone)` hoặc `ZonedDateTime.of(localDateTime, zone)`; chúng cũng giải quyết theo quy tắc vùng. Không hiểu “`of` luôn giữ được mọi ngày giờ người dùng nhập”: DST gap có thể buộc phải điều chỉnh.

### 3.3. Từ chuỗi có zone ID và offset

~~~java
ZonedDateTime event = ZonedDateTime.parse(
        "2024-10-27T02:30:00+01:00[Europe/Paris]");

System.out.println(event.toInstant());
// 2024-10-27T01:30:00Z
~~~

Chuỗi chuẩn có đủ giờ địa phương, offset và zone giúp mô tả chính xác **lần thứ hai** của 02:30 trong DST overlap. `ZonedDateTime.parse` sử dụng bộ quy tắc resolver của formatter; **đừng dùng hành vi parse như cơ chế kiểm tra nghiêm ngặt mọi tổ hợp offset và zone do người dùng nhập**. Nếu yêu cầu nghiêm ngặt rằng local time và offset phải hợp lệ theo quy tắc vùng tại ngày đó, có thể parse từng thành phần theo hợp đồng dữ liệu và dùng `ZonedDateTime.ofStrict(local, offset, zone)`.

## 4. Gap và overlap: vì sao cần offset đã xác định?

Một vùng múi giờ có DST có thể rơi vào ba tình huống khi gắn `LocalDateTime`:

| `zone.getRules().getValidOffsets(local)` | Trạng thái | Cách hiểu |
| --- | --- | --- |
| Một offset | Bình thường | Local date-time tương ứng một instant |
| Danh sách rỗng | **Gap** | Giờ không tồn tại tại vùng vì đồng hồ tiến lên |
| Hai offset | **Overlap** | Giờ xuất hiện hai lần vì đồng hồ lùi |

### 4.1. Overlap: hai cách diễn giải `02:30` ở Paris

Ngày **27/10/2024**, Paris kết thúc DST. `2024-10-27T02:30` có hai offset:

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);

System.out.println(paris.getRules().getValidOffsets(overlap));
// [+02:00, +01:00]

ZonedDateTime first = overlap.atZone(paris);
ZonedDateTime second = first.withLaterOffsetAtOverlap();
~~~

Bảng kết quả:

| Giá trị `ZonedDateTime` | Instant |
| --- | --- |
| `2024-10-27T02:30+02:00[Europe/Paris]` | `2024-10-27T00:30:00Z` |
| `2024-10-27T02:30+01:00[Europe/Paris]` | `2024-10-27T01:30:00Z` |

`withEarlierOffsetAtOverlap()` chọn offset sớm hơn theo quy tắc API; `withLaterOffsetAtOverlap()` chọn offset muộn hơn. Đối tượng `ZonedDateTime` giữ offset **đã được chọn**, nhờ đó `toInstant()` trả mốc nhất quán. Với lịch giao dịch 02:30, chỉ lưu `LocalDateTime` và zone ID rồi quên lựa chọn offset có thể làm mất thông tin “lần đầu hay lần hai”.

### 4.2. Gap: một giờ không tồn tại

Ngày **31/03/2024**, Paris bắt đầu DST và bỏ qua khoảng giờ địa phương từ 02:00 tới 02:59:59:

~~~java
LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);

System.out.println(paris.getRules().getValidOffsets(gap));
// []

System.out.println(gap.atZone(paris));
// 2024-03-31T03:30+02:00[Europe/Paris]
~~~

`gap.atZone(paris)` mặc định dịch 02:30 lên 03:30. **Không có instant hợp lệ nào diễn ra lúc đúng 02:30 địa phương ở Paris ngày đó.** Nghiệp vụ có thể muốn từ chối giờ nhập, đề xuất giờ hợp lệ gần nhất hoặc tự điều chỉnh; cần chọn một chính sách rõ ràng thay vì ngầm để API quyết định.

### 4.3. Khi cần kiểm tra nghiêm ngặt

~~~java
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime chosen = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(1), zone);
// Lần thứ hai, offset +01:00 hợp lệ.

ZonedDateTime invalid = ZonedDateTime.ofStrict(
        local, ZoneOffset.UTC, zone);
// Ném DateTimeException: UTC (+00:00) không hợp lệ cho local này.
~~~

Đoạn minh họa trong method với import `java.time`, trong đó **lời gọi `invalid` sẽ ném ngoại lệ** và không được chạy tiếp nếu không bắt lỗi. `ofStrict` từ chối gap hay offset không hợp lệ thay vì tự điều chỉnh. Trường hợp overlap, nó giúp bạn xác định chính xác offset đã được người dùng chọn; nếu nghiệp vụ **không muốn tự chọn một trong hai**, hãy kiểm tra `getValidOffsets` rồi yêu cầu chọn.

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` cũng cho phép chỉ định **offset ưu tiên khi hợp lệ**; khi offset được yêu cầu không hợp lệ, phương thức này vẫn có thể dùng chính sách mặc định. Vì vậy `ofStrict` phù hợp hơn nếu phải từ chối mọi tổ hợp local/offset/zone không nhất quán.

## 5. Chương trình Java 17+ chạy được

Tạo tệp **`ZonedDateTimePartsDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZonedDateTimePartsDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("valid offsets = "
                + paris.getRules().getValidOffsets(overlap));

        ZonedDateTime first = overlap.atZone(paris);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("first instant = " + first.toInstant());
        System.out.println("second instant = " + second.toInstant());

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        System.out.println("gap offsets = "
                + paris.getRules().getValidOffsets(gap));
        System.out.println("gap adjusted = " + gap.atZone(paris));

        try {
            ZonedDateTime.ofStrict(overlap, ZoneOffset.UTC, paris);
        } catch (DateTimeException ex) {
            System.out.println("strict rejected = "
                    + ex.getClass().getSimpleName());
        }

        Instant absolute = Instant.parse("2026-01-15T00:30:00Z");
        ZonedDateTime vn =
                absolute.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ZonedDateTime la =
                vn.withZoneSameInstant(
                        ZoneId.of("America/Los_Angeles"));

        System.out.println("VN = " + vn);
        System.out.println("LA = " + la);
        System.out.println("same instant = "
                + vn.toInstant().equals(la.toInstant()));
        System.out.println("same local time = "
                + vn.toLocalDateTime()
                    .equals(la.toLocalDateTime()));

        ZonedDateTime before =
                ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);
        System.out.println("plus day = " + before.plusDays(1));
        System.out.println("plus 24 hours = "
                + before.plusHours(24));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ZonedDateTimePartsDemo.java
java ZonedDateTimePartsDemo
~~~

Kết quả:

~~~text
valid offsets = [+02:00, +01:00]
first = 2024-10-27T02:30+02:00[Europe/Paris]
second = 2024-10-27T02:30+01:00[Europe/Paris]
first instant = 2024-10-27T00:30:00Z
second instant = 2024-10-27T01:30:00Z
gap offsets = []
gap adjusted = 2024-03-31T03:30+02:00[Europe/Paris]
strict rejected = DateTimeException
VN = 2026-01-15T07:30+07:00[Asia/Ho_Chi_Minh]
LA = 2026-01-14T16:30-08:00[America/Los_Angeles]
same instant = true
same local time = false
plus day = 2024-03-31T12:00+02:00[Europe/Paris]
plus 24 hours = 2024-03-31T13:00+02:00[Europe/Paris]
~~~

Các đầu ra đã được đối chiếu với Java. Ví dụ phụ thuộc vào quy tắc `Europe/Paris` đã ghi nhận cho năm 2024 và `America/Los_Angeles` tại tháng 01/2026; cơ sở dữ liệu múi giờ của Java (`tzdb`) cần có các quy tắc lịch sử tương ứng.

Điểm đáng học từ chương trình:

1. `overlap` có hai offset; `ZonedDateTime` cụ thể mang offset đã chọn nên `toInstant()` không mơ hồ.
2. `gap` không có offset hợp lệ; `atZone` tự dịch giờ, còn `ofStrict` có thể từ chối các tổ hợp không hợp lệ.
3. Cùng instant UTC biểu diễn thành ngày giờ khác nhau ở Việt Nam và Los Angeles; round-trip `toInstant()` giữ cùng sự kiện.
4. `plusDays(1)` và `plusHours(24)` có thể đưa tới giờ địa phương khác nhau khi đi qua một lần đổi DST.

## 6. Kiểm tra từng thành phần trong mã Java

~~~java
ZonedDateTime zdt = Instant.parse("2026-01-15T00:30:00Z")
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime local = zdt.toLocalDateTime();
// 2026-01-15T07:30

ZoneId zone = zdt.getZone();
// Asia/Ho_Chi_Minh

ZoneOffset offset = zdt.getOffset();
// +07:00

Instant instant = zdt.toInstant();
// 2026-01-15T00:30:00Z
~~~

*Đây là ví dụ trong một method, sử dụng import các kiểu `java.time`.*

`toLocalDateTime()` **làm mất thông tin vùng và offset ở giá trị trả về**, nhưng không làm thay đổi `zdt`. Nếu bạn chỉ lưu `local`, có thể không biết instant gốc khi DST overlap. Khi chuyển `zdt.toLocalDate()` hoặc `zdt.toLocalTime()`, hãy nhớ đó cũng chỉ là **phần hiển thị theo zone của `zdt`**, không phải mốc UTC độc lập.

### Quy tắc kiểm tra tính nhất quán

Một `ZonedDateTime` hợp lệ phải gắn offset nhất quán với instant và `ZoneId` theo quy tắc zone được dùng để tạo nó. Với `ZonedDateTime` hiện có:

~~~java
ZoneOffset expected =
        zdt.getZone().getRules().getOffset(zdt.toInstant());
boolean consistent = expected.equals(zdt.getOffset());
// true
~~~

Đoạn này trong method với import `java.time.ZoneOffset`. Khi dữ liệu được tạo/parse theo quy tắc hợp lệ, offset và instant tương ứng nhau. Nếu dữ liệu `ZonedDateTime` được lưu thành **chuỗi** rồi một hệ thống khác parse lại với phiên bản tzdb hoặc chính sách khác, cần xác định mục tiêu là **bảo tồn instant gốc** hay **giữ ý định giờ địa phương**; các yêu cầu đó có thể xung đột khi quy tắc vùng thay đổi.

## 7. Chuyển vùng: “cùng instant” khác “cùng local”

Hai thao tác này thường bị nhầm:

| Phương thức | Ưu tiên giữ | Điều có thể thay đổi |
| --- | --- | --- |
| `withZoneSameInstant(otherZone)` | **Instant** | Ngày giờ địa phương, offset, zone |
| `withZoneSameLocal(otherZone)` | **Local date-time** nếu có thể | Instant, offset, zone; giờ local vẫn có thể điều chỉnh nếu gap |

Ví dụ `2026-01-15T07:30+07:00[Asia/Ho_Chi_Minh]`:

~~~java
ZonedDateTime vietnam = Instant.parse(
        "2026-01-15T00:30:00Z")
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime sameInstant = vietnam.withZoneSameInstant(
        ZoneId.of("America/Los_Angeles"));
// 2026-01-14T16:30-08:00[America/Los_Angeles]

ZonedDateTime sameLocal = vietnam.withZoneSameLocal(
        ZoneId.of("America/Los_Angeles"));
// 2026-01-15T07:30-08:00[America/Los_Angeles]
// Instant khác mốc gốc!
~~~

Đoạn này nằm trong method với import từ `java.time`. Chọn `withZoneSameInstant` để một sự kiện xuất hiện đúng giờ tại các vùng của người xem. Chọn `withZoneSameLocal` chỉ khi chủ đích là **diễn giải lại cùng giờ đồng hồ ở vùng khác**, ví dụ một cuộc họp cần “07:30 theo giờ địa phương mới” và nghiệp vụ chấp nhận thay đổi instant.

## 8. Cộng ngày theo lịch khác cộng 24 giờ thực

Một `ZonedDateTime` có cả giờ địa phương **và** vị trí trên timeline nên kết quả phụ thuộc **loại đơn vị cộng**.

Với `Europe/Paris` trước ngày bắt đầu DST 31/03/2024:

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0, ZoneId.of("Europe/Paris"));

ZonedDateTime calendarNext = start.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris]

ZonedDateTime elapsed24h = start.plusHours(24);
// 2024-03-31T13:00+02:00[Europe/Paris]
~~~

Vì đồng hồ Paris tiến thêm một giờ, từ trưa ngày 30 tới trưa ngày 31 chỉ **23 giờ thực**.

- `plusDays(1)` xử lý **ngày theo local timeline**: cố giữ giờ địa phương như “trưa ngày hôm sau”, rồi giải quyết offset theo zone.
- `plusHours(24)` cộng **24 giờ trên instant timeline**, nên tại Paris hôm sau là 13:00.

Sự khác biệt có ý nghĩa trong lịch lặp, đặt lịch, tính SLA và thời hạn. Nếu bài toán là “mỗi ngày lúc 12:00 tại Paris”, nên vận dụng phép ngày lịch. Nếu bài toán là “sau đủ 24 giờ kể từ sự kiện”, dùng `Duration`/`Instant` (hoặc các phép cộng giờ trên `ZonedDateTime` khi muốn giữ zone hiển thị).

## 9. So sánh đối tượng và so sánh thời điểm

Hai `ZonedDateTime` ở **hai zone khác nhau** có thể trỏ đến cùng một `Instant`. Vì vậy cần chọn đúng ý nghĩa của phép so sánh:

~~~java
Instant instant = Instant.parse("2026-01-15T00:30:00Z");
ZonedDateTime vietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime losAngeles =
        instant.atZone(ZoneId.of("America/Los_Angeles"));

boolean sameObjectValue = vietnam.equals(losAngeles);
// false: vùng/ngày giờ địa phương khác.

boolean samePointInTime =
        vietnam.toInstant().equals(losAngeles.toInstant());
// true: cùng instant.

boolean sameByTimeline = vietnam.isEqual(losAngeles);
// true: so sánh thời điểm.
~~~

Đoạn minh họa trong method với import `java.time.Instant`, `ZonedDateTime`, `ZoneId`.

`equals()` của `ZonedDateTime` xem các thành phần biểu diễn (local date-time, offset, zone), nên hai cách hiển thị khác nhau thường không bằng nhau dù cùng instant. `isEqual()`, `isBefore()`, `isAfter()` phù hợp khi mục tiêu là so sánh **thời điểm trên timeline**. Với dữ liệu chỉ quan tâm thứ tự hoặc bằng nhau theo timestamp, chuyển sang `Instant` làm khóa hoặc so sánh giúp tránh nhầm lẫn giữa thời điểm và hình thức biểu diễn.

## 10. `ZonedDateTime` bất biến: nhớ nhận kết quả

~~~java
ZonedDateTime meeting = ZonedDateTime.of(
        2026, 1, 15, 9, 0, 0, 0, ZoneId.of("Asia/Ho_Chi_Minh"));

meeting.plusDays(1); // Bỏ kết quả: meeting vẫn 15/01.
meeting = meeting.plusDays(1); // meeting chuyển sang 16/01.
~~~

Các phương thức `plus...`, `minus...`, `with...`, `withZoneSameInstant`, `withLaterOffsetAtOverlap` trả về **giá trị kết quả**, không sửa đối tượng nguồn. Việc gán lại chỉ đổi biến tham chiếu. Đừng dựa vào việc Java luôn cấp phát một đối tượng vật lý khác nếu nội dung không đổi (ví dụ `plusDays(0)`); hãy so sánh **giá trị/instant**, không dựa vào toán tử đồng nhất tham chiếu `==`.

## 11. Thiết kế dữ liệu: khi nào giữ zone cùng instant?

### Sự kiện đã xảy ra

Một thanh toán được xác nhận lúc `2026-01-15T00:30:00Z` là sự kiện tuyệt đối. Thông thường nên lưu **`Instant confirmedAt`** trong hệ thống (hoặc timestamp có hợp đồng UTC rõ ràng), và dùng `confirmedAt.atZone(viewerZone)` để hiển thị. Người xem ở Việt Nam và Los Angeles có thể thấy ngày khác nhau mà không làm thay đổi sự kiện.

Đối với log và xử lý thứ tự toàn cầu, `Instant` còn tránh nhầm hai lần 02:30 trong DST overlap.

### Lịch hẹn hoặc quy tắc theo giờ địa phương

Cuộc họp “09:00 ở Paris” cần **`LocalDateTime` cùng `ZoneId`** như đầu vào nghiệp vụ, sau đó giải quyết gap/overlap để chọn instant. Nếu phải tái hiện lựa chọn của người đặt trong DST overlap, giữ thêm offset đã chốt hoặc instant được tạo. Với lịch trong tương lai xa hoặc lặp theo giờ địa phương, cân nhắc giữ **local date-time, zone ID và chính sách cập nhật** nếu thay đổi quy tắc DST.

Mốc `ZonedDateTime` đã giải quyết giúp biểu diễn sự kiện theo vùng, nhưng không tự thay thế mọi yêu cầu lịch lặp: “mỗi thứ Hai lúc 09:00” có ý nghĩa theo lịch địa phương và cần tính từng lần theo zone.

### API/JSON

Biểu diễn có cả offset và zone có thể viết:

~~~json
{
  "scheduledLocalDateTime": "2024-10-27T02:30:00",
  "zoneId": "Europe/Paris",
  "selectedOffset": "+01:00",
  "scheduledInstant": "2024-10-27T01:30:00Z"
}
~~~

Đây là minh họa một hợp đồng lưu đủ dữ liệu để kiểm tra lựa chọn overlap. Không nhất thiết cần cả bốn trường cho mọi API; quyết định theo nhu cầu: nếu chỉ gửi sự kiện đã xảy ra, `Instant` ISO có `Z` thường đủ. Nếu gửi lịch hẹn theo giờ địa phương, cần **zone ID**, quy định xử lý gap/overlap và khả năng bảo tồn ý định người dùng.

Một chuỗi dạng `2024-10-27T02:30:00+01:00[Europe/Paris]` là biểu diễn ISO zoned dễ đọc, nhưng phía nhận phải hỗ trợ kiểu này. Với API công khai, mô tả rõ kiểu và quy tắc parse/validate, đừng dựa vào timezone mặc định của server.

## 12. Lỗi phổ biến khi làm việc với `ZonedDateTime`

| Nhầm lẫn | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Nghĩ `ZonedDateTime` chỉ là `LocalDateTime + ZoneId` | DST overlap cần biết offset nào đã giải quyết | Kiểm tra `getOffset()`; giữ offset/instant được chọn |
| Nghĩ `ZoneId` luôn là offset cố định | Vùng có thể đổi offset theo ngày | Dùng ID vùng và `ZoneRules` |
| Cho rằng mọi local date-time đều tồn tại | DST gap có 0 offset hợp lệ | Kiểm tra `getValidOffsets` hoặc dùng `ofStrict` |
| Cho rằng mọi local date-time đều xảy ra một lần | DST overlap có thể có 2 offset | Yêu cầu chọn lần/offset rõ ràng |
| Coi `atZone` là kiểm tra nghiêm ngặt | Nó có chính sách điều chỉnh gap/chọn overlap | Chủ động validate khi không được tự điều chỉnh |
| Dùng `withZoneSameLocal` để đổi múi giờ hiển thị | Có thể thay đổi instant | Dùng `withZoneSameInstant` |
| Cộng 24 giờ cho lịch “ngày mai cùng giờ” | Sai giờ dân sự khi DST | Cộng ngày theo local timeline |
| Lấy `toLocalDateTime()` rồi bỏ offset/zone | Mất tính duy nhất của instant khi lưu trữ | Giữ `Instant` hoặc zoned/offset đã xác định |
| So sánh `equals` khi chỉ cần cùng thời điểm | Hai zone biểu diễn khác nhau vẫn cùng instant | So sánh `toInstant()` hoặc `isEqual()` |
| Dùng `ZoneId.systemDefault()` không chủ đích | Phụ thuộc máy triển khai | Lấy zone từ người dùng/địa điểm/nghiệp vụ |

### Tự kiểm tra

1. `ZonedDateTime` lưu thông tin nào quan trọng ngoài ngày giờ địa phương? **`ZoneId` và offset đã được giải quyết**, nhờ đó chuyển sang `Instant` duy nhất.
2. `2024-10-27T02:30+02:00[Europe/Paris]` và `2024-10-27T02:30+01:00[Europe/Paris]` có cùng instant không? **Không**; cách nhau một giờ UTC.
3. Vì sao `LocalDateTime.of(2024,3,31,2,30).atZone(Paris)` trả 03:30? **Do 02:30 ở Paris nằm trong DST gap**, nên API mặc định điều chỉnh.
4. Nếu đã có `Instant` rồi gọi `atZone(paris)`, có cần hỏi người dùng chọn offset không? **Không**; instant xác định offset theo quy tắc vùng.
5. Đổi vùng hiển thị mà giữ cùng sự kiện cần dùng phương thức nào? **`withZoneSameInstant()`**, hoặc từ instant gọi `atZone(zoneMới)`.
6. Tại sao `ZonedDateTime.plusDays(1)` có thể khác `plusHours(24)`? **Một phép theo ngày lịch địa phương; một phép theo số giờ trên instant timeline**, DST có thể làm kết quả đồng hồ chênh lệch.
7. Khi nghiệp vụ chỉ cần timestamp tuyệt đối, nên dùng `ZonedDateTime` làm dữ liệu duy nhất không? **Thường giữ `Instant`** làm mốc nguồn và chuyển thành `ZonedDateTime` khi cần ngữ cảnh địa phương.

**Ghi nhớ:** `ZonedDateTime` chứa **ngày giờ địa phương, `ZoneId` và offset đã xác định**. `ZoneId` giúp hiểu quy tắc múi giờ; offset phân biệt lựa chọn cụ thể tại DST overlap; `toInstant()` xác định mốc tuyệt đối. Hãy biết mình đang tính trên **lịch địa phương** hay **dòng thời gian thực**, và giữ đầy đủ thông tin cần thiết khi lưu trữ/truyền dữ liệu.