# Kiểm tra tổ hợp ngày giờ, độ lệch và múi giờ bằng ZonedDateTime.ofStrict()

## 1. Vì sao cần kiểm tra strict?

Một `LocalDateTime` mô tả ngày và giờ địa phương (ví dụ `2026-11-01T01:30`), chưa chứa múi giờ hay offset. Một `ZoneId` như `America/New_York` chỉ ra vùng và quy tắc chuyển đổi giờ; một `ZoneOffset` như `-05:00` cho độ lệch UTC cụ thể. Để biến ngày giờ địa phương thành một thời điểm tuyệt đối, tổ hợp các thông tin phải **phù hợp với quy tắc múi giờ tại đúng ngày giờ ấy**.

Ví dụ, New York thường có offset `-05:00` vào mùa đông và `-04:00` vào mùa hè. Ngày 01/07/2026, cuộc hẹn lúc 09:30 New York tương ứng `2026-07-01T13:30:00Z` vì offset hợp lệ là `-04:00`. Nếu client gửi 09:30, `-05:00` và `America/New_York`, việc tính `toInstant(-05:00)` vẫn cho một mốc hợp lệ về mặt toán học nhưng **không còn là 09:30 ở New York**.

Để ngăn tổ hợp không nhất quán, Java cung cấp:

```java
ZonedDateTime.ofStrict(
    LocalDateTime localDateTime,
    ZoneOffset offset,
    ZoneId zone
);
```

Đây là **cú pháp minh họa**, không phải lời gọi có thể biên dịch độc lập: các tên kiểu đại diện cho tham số. Khi dùng đúng giá trị, `ofStrict()` trả về một `ZonedDateTime`; khi `offset` không hợp lệ với `localDateTime` trong `zone`, nó ném `DateTimeException`. Nó **không tự chỉnh giờ** trong DST gap và **không tự chọn offset** trong DST overlap.

Bài học tập trung vào ý nghĩa của `ofStrict`, cách lấy offset hợp lệ, so sánh với các API có chính sách giải quyết giờ tự động và vận dụng vào hệ thống lịch.

## 2. Các kiểu ngày giờ liên quan

| Kiểu | Ý nghĩa | Ví dụ | Có đủ xác định Instant? |
| --- | --- | --- | --- |
| `LocalDateTime` | Ngày và giờ địa phương, không mang offset/zone | `2026-07-01T09:30` | Không |
| `ZoneOffset` | Độ lệch UTC cố định tại một thời điểm | `-04:00`, `+07:00` | Cần thêm LocalDateTime |
| `ZoneId` | Danh tính vùng và quy tắc offset/DST | `America/New_York` | Cần mốc hoặc ngày giờ và chính sách giải quyết |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | `2026-07-01T09:30-04:00` | Có |
| `ZonedDateTime` | Ngày giờ địa phương + zone ID + offset đã giải quyết | `2026-07-01T09:30-04:00[America/New_York]` | Có |
| `Instant` | Thời điểm tuyệt đối trên timeline UTC | `2026-07-01T13:30:00Z` | Chính là mốc tuyệt đối |

`ZoneId` vùng chứa quy tắc múi giờ do tzdb của JDK cung cấp. `ZoneOffset` là một lớp con của `ZoneId`, nhưng một offset cố định như `-05:00` **không** cho biết rằng New York dùng `-04:00` vào mùa hè. Không nên coi offset ở hiện tại là luật áp dụng cho mọi ngày.

### Ba kết quả từ một LocalDateTime và ZoneId

Do Daylight Saving Time (DST), một ngày giờ đồng hồ tại vùng có thể có:

- **Một offset hợp lệ:** thời điểm thông thường, ánh xạ tới một `Instant`.
- **Không có offset hợp lệ (gap):** đồng hồ địa phương nhảy tiến; giờ người dùng nhập **không xảy ra**.
- **Hai offset hợp lệ (overlap):** đồng hồ quay lùi; cùng giờ người dùng nhập xảy ra **hai lần**, mỗi lần ứng với một `Instant` khác.

Trong New York năm 2026:

| Ngày giờ địa phương | Trạng thái | Offset hợp lệ |
| --- | --- | --- |
| `2026-07-01T09:30` | Bình thường, mùa hè | `-04:00` |
| `2026-12-01T09:30` | Bình thường, mùa đông | `-05:00` |
| `2026-03-08T02:30` | DST gap | Không có |
| `2026-11-01T01:30` | DST overlap | `-04:00` và `-05:00` |

Chính tại gap/overlap, việc “ghép ngày giờ với vùng” không có câu trả lời duy nhất hoặc không có câu trả lời hợp lệ. `ofStrict()` buộc caller đưa một offset cụ thể và xác thực offset đó.

## 3. Chữ ký, tham số và hành vi của ofStrict()

API của Java SE 17:

```java
public static ZonedDateTime ofStrict(
    LocalDateTime localDateTime,
    ZoneOffset offset,
    ZoneId zone
)
```

Đoạn trên là **khai báo chữ ký minh họa**, không phải class chạy độc lập.

- `localDateTime`: ngày giờ địa phương người dùng muốn giữ nguyên.
- `offset`: độ lệch UTC cụ thể, chẳng hạn `-04:00`.
- `zone`: múi giờ vùng cung cấp quy tắc cho ngày giờ đó.
- **Trả về**: `ZonedDateTime` mang đúng local, đúng zone và offset đã được chứng minh hợp lệ.
- **Sai tổ hợp**: ném `DateTimeException`; ví dụ gap hoặc offset không hợp lệ trong vùng.
- **Đối số null**: ném `NullPointerException`; kiểm tra đầu vào trước khi gọi.
- **Không có policy ngầm**: không tự dời local time hoặc tự thay offset nếu không hợp lệ.

Ví dụ hợp lệ:

```java
import java.time.*;

LocalDateTime summer = LocalDateTime.of(2026, 7, 1, 9, 30);
ZoneId ny = ZoneId.of("America/New_York");
ZoneOffset offset = ZoneOffset.of("-04:00");

ZonedDateTime meeting = ZonedDateTime.ofStrict(summer, offset, ny);
Instant instant = meeting.toInstant();
// meeting: 2026-07-01T09:30-04:00[America/New_York]
// instant: 2026-07-01T13:30:00Z
```

Đây là các câu lệnh đặt trong method. Kết quả `meeting` giữ chính xác `09:30` và offset `-04:00` ở New York. `instant` là mốc sự kiện UTC duy nhất đã được xác nhận.

**Ý nghĩa của “strict”:** xác thực **tính phù hợp giữa local date-time, offset và luật của ZoneId**. Nó khác `DateTimeFormatter.withResolverStyle(ResolverStyle.STRICT)`, vốn kiểm tra cách phân tích chuỗi thành ngày/giờ theo lịch. Có thể parse đúng `2026-03-08T02:30` thành `LocalDateTime` nhưng vẫn không được phép đặt lịch lúc ấy ở New York.

## 4. Tra cứu quy tắc múi giờ trước khi tạo ZonedDateTime

`ZoneRules` thuộc package `java.time.zone`. Lấy từ một vùng bằng `zone.getRules()`, sau đó truy vấn offset hợp lệ:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = ny.getRules();

List<ZoneOffset> options = rules.getValidOffsets(local);
// [-04:00, -05:00]

boolean allowed = rules.isValidOffset(local, ZoneOffset.of("-05:00"));
// true
```

Những method quan trọng:

| Method | Trả lời câu hỏi | Chú ý |
| --- | --- | --- |
| `getValidOffsets(LocalDateTime)` | Có những offset nào hợp lệ cho giờ local? | Danh sách thường 0, 1 hoặc 2 phần tử |
| `isValidOffset(local, offset)` | Offset được chọn có nằm trong danh sách hợp lệ? | Hữu ích khi client gửi offset |
| `getTransition(LocalDateTime)` | Tại local này có gap/overlap và offset chuyển đổi thế nào? | Thường trả `null` khi không ở chuyển giờ |
| `getOffset(Instant)` | Tại mốc UTC đã biết, offset của vùng là bao nhiêu? | Một giá trị duy nhất |
| `getOffset(LocalDateTime)` | Offset được API đề xuất theo quy tắc giải quyết local? | Không dùng thay cho strict validation ở gap/overlap |

**Điểm rất dễ nhầm:** `getOffset(LocalDateTime)` có thể trả offset dựa trên quy tắc mặc định ngay cả trong giờ local không hợp lệ; để kiểm tra nghiêm ngặt, dùng `getValidOffsets` hoặc chính `ofStrict`.

### Chọn offset theo số phần tử

```java
List<ZoneOffset> valid = rules.getValidOffsets(local);

if (valid.isEmpty()) {
    // Gap: giờ địa phương không tồn tại.
} else if (valid.size() == 1) {
    // Bình thường: có đúng một offset hợp lệ.
} else {
    // Overlap: hai offset hợp lệ; phải có chính sách chọn lần.
}
```

Snippet trên là logic điều kiện bên trong method, với `rules` và `local` được khai báo trước. Với giao dịch/lịch hẹn nghiêm ngặt, nếu ở overlap nên hỏi người dùng chọn offset/lần xuất hiện hoặc áp dụng chính sách được công bố. Sau khi chọn xong, dùng `ofStrict` để kiểm tra thêm lần cuối.

## 5. Ca bình thường: offset hợp lệ và offset sai

New York ngày **01/07/2026** đang áp dụng DST, nên offset đúng là `-04:00`:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);

ZonedDateTime correct = ZonedDateTime.ofStrict(
    local, ZoneOffset.of("-04:00"), ny);
// 2026-07-01T09:30-04:00[America/New_York]
```

Nhưng nếu client lưu nhầm offset mùa đông:

```java
try {
    ZonedDateTime.ofStrict(local, ZoneOffset.of("-05:00"), ny);
} catch (DateTimeException ex) {
    System.out.println("Offset khong hop le");
}
```

Giá trị `-05:00` là offset đúng cú pháp và dùng ở New York trong những ngày khác, nhưng **không hợp lệ ở local datetime đầu vào**. Vì vậy `ofStrict` ném lỗi. Nó ngăn bug phổ biến: tính `09:30-05:00` thành `14:30Z` rồi tưởng rằng cuộc họp New York đã được xác nhận đúng, trong khi mốc thực phải là `13:30Z`.

Nếu chỉ dùng `local.atOffset(ZoneOffset.of("-05:00"))` hoặc `local.toInstant(offset)`, Java không biết “New York” để xác thực. Hai API đó hữu ích nếu offset đầu vào đã được tin cậy và ngữ cảnh không yêu cầu kiểm tra vùng.

## 6. DST gap: giờ local không tồn tại

Ngày **08/03/2026** tại New York, đồng hồ tiến từ khoảng `01:59:59` lên `03:00`. Bởi vậy `02:30` không hề xảy ra. Java vẫn có thể tạo `LocalDateTime.of(2026,3,8,2,30)` (vì đây là ngày giờ hợp lệ về mặt lịch), nhưng không thể xác định một offset hợp lệ cho **vùng New York**.

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2026, 3, 8, 2, 30);

List<ZoneOffset> valid = ny.getRules().getValidOffsets(missing);
// [] — gap
```

Vì danh sách rỗng, cả `-05:00` và `-04:00` đều không thỏa yêu cầu “02:30 ở New York trong ngày đó”:

```java
try {
    ZonedDateTime.ofStrict(missing, ZoneOffset.of("-05:00"), ny);
} catch (DateTimeException ex) {
    System.out.println("Gio khong ton tai");
}
```

### ofStrict khác atZone ra sao ở gap?

```java
ZonedDateTime automatic = missing.atZone(ny);
// 2026-03-08T03:30-04:00[America/New_York]
```

`atZone` (hoặc `ZonedDateTime.of(local, zone)`) **điều chỉnh** giờ qua gap theo thời lượng chuyển đổi: 02:30 được đẩy thành 03:30. `ofStrict` giữ yêu cầu phải chính xác: *không* âm thầm điều chỉnh mà từ chối tổ hợp.

Với ứng dụng đặt khám, lịch bay, chốt giao dịch, việc dời giờ một cách ngầm định có thể thay đổi điều mà người dùng muốn. Có thể từ chối và yêu cầu chọn lại, hoặc áp dụng quy tắc tự dời rõ ràng cho từng sản phẩm. Chính sách là quyết định nghiệp vụ; `ofStrict` cung cấp phép kiểm tra nghiêm ngặt để thực hiện chính sách đó.

## 7. DST overlap: cùng giờ local xuất hiện hai lần

Ngày **01/11/2026** tại New York, đồng hồ lùi một giờ và `01:30` xuất hiện hai lần:

| Lần xuất hiện | LocalDateTime | ZoneOffset | Instant |
| --- | --- | --- | --- |
| Lần đầu | `2026-11-01T01:30` | `-04:00` | `2026-11-01T05:30:00Z` |
| Lần sau | `2026-11-01T01:30` | `-05:00` | `2026-11-01T06:30:00Z` |

`ofStrict` chấp nhận **cả hai tổ hợp** vì cả hai offset đều hợp lệ ở giờ local này:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2026, 11, 1, 1, 30);

ZonedDateTime first = ZonedDateTime.ofStrict(
    repeated, ZoneOffset.of("-04:00"), ny);

ZonedDateTime second = ZonedDateTime.ofStrict(
    repeated, ZoneOffset.of("-05:00"), ny);

Instant firstInstant = first.toInstant();   // 2026-11-01T05:30:00Z
Instant secondInstant = second.toInstant(); // 2026-11-01T06:30:00Z
```

Hai mốc cách nhau **60 phút thực**, dù hiển thị cùng 01:30 trên đồng hồ địa phương. Nếu dùng offset `-06:00`, `ofStrict` ném `DateTimeException` vì không thuộc offset hợp lệ trong vùng.

### Có phải ofStrict tự chọn lần đầu/lần sau?

Không. Caller phải cung cấp một `ZoneOffset` cụ thể. Nếu người dùng chỉ chọn `01:30` và `America/New_York`, ứng dụng cần hiển thị hai lựa chọn hoặc dùng policy đã được thông báo. `ZonedDateTime.ofLocal(local, zone, preferredOffset)` có thể ưu tiên offset nếu hợp lệ nhưng có fallback; `ofStrict` không có fallback như vậy.

Khi đã có lựa chọn, lưu `Instant` để đánh dấu mốc tuyệt đối, đồng thời lưu `ZoneId` nếu cần tái hiện giờ tổ chức hoặc xây quy tắc lịch lặp.

## 8. So sánh các API tạo ZonedDateTime

| API | Tham số | Khi ở gap | Khi ở overlap |
| --- | --- | --- | --- |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Đầy đủ local, offset, zone | Ném lỗi | Chấp nhận offset hợp lệ do caller chọn; từ chối offset khác |
| `LocalDateTime.atZone(zone)` | Local + zone | Tự đẩy tới giờ hợp lệ sau gap | Mặc định chọn offset sớm hơn |
| `ZonedDateTime.of(local, zone)` | Local + zone | Tương tự `atZone` | Tương tự `atZone` |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Local, zone và offset ưu tiên | Điều chỉnh qua gap | Dùng preferred nếu hợp lệ, nếu không chọn theo quy tắc mặc định |
| `ZonedDateTime.ofInstant(instant, zone)` | Instant và zone | Không mơ hồ vì instant đã rõ | Không mơ hồ |
| `ZonedDateTime.ofInstant(local, offset, zone)` | Local+offset xác định instant rồi biểu diễn ở zone | Không xác thực local và offset theo kiểu strict; local output có thể thay đổi | Tính instant từ local+offset |
| `LocalDateTime.atOffset(offset)` | Local + offset | Không biết zone để kiểm tra | Không biết zone để kiểm tra |

Trong quy trình nhận input từ người dùng muốn đặt lịch đúng giờ đã chọn, `ofStrict` là API phù hợp khi cần xác nhận **offset được yêu cầu phải hợp lệ**. Dùng `atZone` khi chính sách mặc định xử lý DST được chấp nhận. Dùng `ofInstant` khi bạn đã có thời điểm tuyệt đối cần hiển thị theo zone.

Nhầm lẫn đặc biệt thường gặp là dùng `ofLocal` với tham số `preferredOffset` như thể nó là offset bắt buộc. Nếu preferred offset không hợp lệ ở vùng, API có thể chọn offset khác; đó không phải hành vi strict.

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo file **`ZonedDateTimeStrictDemo.java`**. Chương trình này dùng dữ liệu cố định, in kết quả chính xác cho thời gian bình thường, gap, overlap và trường hợp offset không hợp lệ.

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

public class ZonedDateTimeStrictDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime summer = LocalDateTime.of(2026, 7, 1, 9, 30);
        ZoneOffset summerOffset = ZoneOffset.of("-04:00");
        ZonedDateTime normal =
                ZonedDateTime.ofStrict(summer, summerOffset, newYork);
        System.out.println("Normal offsets: " + rules.getValidOffsets(summer));
        System.out.println("Normal: " + normal);
        System.out.println("Normal instant: " + normal.toInstant());
        System.out.println("Wrong summer offset valid: " +
                rules.isValidOffset(summer, ZoneOffset.of("-05:00")));

        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap default: " + gap.atZone(newYork));
        boolean gapRejected = false;
        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.of("-05:00"), newYork);
        } catch (DateTimeException ex) {
            gapRejected = true;
        }
        System.out.println("Gap strict rejected: " + gapRejected);

        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> overlapOffsets = rules.getValidOffsets(overlap);
        System.out.println("Overlap offsets: " + overlapOffsets);
        ZonedDateTime earlier =
                ZonedDateTime.ofStrict(overlap, overlapOffsets.get(0), newYork);
        ZonedDateTime later =
                ZonedDateTime.ofStrict(overlap, overlapOffsets.get(1), newYork);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());
        System.out.println("Different instant: " +
                !earlier.toInstant().equals(later.toInstant()));

        boolean invalidRejected = false;
        try {
            ZonedDateTime.ofStrict(overlap, ZoneOffset.of("-06:00"), newYork);
        } catch (DateTimeException ex) {
            invalidRejected = true;
        }
        System.out.println("Invalid overlap offset rejected: " + invalidRejected);
    }
}
```

Chạy trong thư mục chứa file bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ZonedDateTimeStrictDemo.java
java ZonedDateTimeStrictDemo
```

**Stdout đã được kiểm tra:**

```text
Normal offsets: [-04:00]
Normal: 2026-07-01T09:30-04:00[America/New_York]
Normal instant: 2026-07-01T13:30:00Z
Wrong summer offset valid: false
Gap offsets: []
Gap default: 2026-03-08T03:30-04:00[America/New_York]
Gap strict rejected: true
Overlap offsets: [-04:00, -05:00]
Earlier instant: 2026-11-01T05:30:00Z
Later instant: 2026-11-01T06:30:00Z
Different instant: true
Invalid overlap offset rejected: true
```

Phân tích output: vào tháng 7, New York có offset `-04:00`; `-05:00` không hợp lệ cho giờ đó. Thời gian gap không có offset và được `atZone` tự dời, trong khi `ofStrict` từ chối. Giờ overlap có hai offset hợp lệ, tạo hai instant khác nhau; `-06:00` bị từ chối.

Quy tắc New York trong ví dụ phụ thuộc dữ liệu timezone (tzdb) của JDK cho năm 2026. Nếu luật địa phương thay đổi, các kết quả trong tương lai có thể khác sau khi cập nhật JDK/tzdb.

## 10. Thiết kế resolver thực tế

Một API đặt lịch có thể nhận:

```json
{
  "localStart": "2026-11-01T01:30:00",
  "timeZone": "America/New_York",
  "selectedOffset": "-05:00"
}
```

Ở đây người dùng chọn **lần thứ hai** của 01:30 New York, tương ứng `2026-11-01T06:30:00Z`. Server cần parse ba trường, kiểm tra danh sách offset hợp lệ rồi mới tạo và lưu mốc.

Quy trình khuyến nghị:

1. Parse `localStart` thành `LocalDateTime`; parse `timeZone` thành `ZoneId` (báo lỗi nếu vùng không được hỗ trợ).
2. Parse `selectedOffset` thành `ZoneOffset` nếu có. Nếu không có, để null và quyết định theo trạng thái vùng.
3. Lấy `valid = zone.getRules().getValidOffsets(local)`.
4. Nếu `valid` rỗng, báo giờ không tồn tại. Nếu có 1 offset, dùng offset đó; nếu request gửi offset khác thì báo không tương thích.
5. Nếu có 2 offset, yêu cầu caller chọn một giá trị trong danh sách theo chính sách nghiệp vụ.
6. Gọi `ZonedDateTime.ofStrict(local, chosenOffset, zone)` để bảo đảm tính hợp lệ trước khi lưu.
7. Lưu `toInstant()` làm mốc UTC, kèm `ZoneId` nếu cần giữ ngữ cảnh vùng tổ chức hoặc lịch lặp.

### Ví dụ class resolver Java 17+

Lưu dưới tên **`StrictMeetingResolver.java`** nếu muốn tích hợp vào ứng dụng:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public final class StrictMeetingResolver {
    private StrictMeetingResolver() {}

    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset requestedOffset) {

        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> valid = rules.getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Gio dia phuong khong ton tai trong mui gio");
        }

        ZoneOffset chosen;
        if (valid.size() == 1) {
            chosen = valid.get(0);
            if (requestedOffset != null && !chosen.equals(requestedOffset)) {
                throw new IllegalArgumentException(
                        "Offset khong hop le cho ngay gio va vung");
            }
        } else {
            if (requestedOffset == null) {
                throw new IllegalArgumentException(
                        "Gio trung: can chon offset");
            }
            if (!valid.contains(requestedOffset)) {
                throw new IllegalArgumentException("Offset khong hop le");
            }
            chosen = requestedOffset;
        }

        return ZonedDateTime.ofStrict(local, chosen, zone).toInstant();
    }
}
```

Đây là class thư viện không có `main()`, có thể biên dịch riêng:

```bash
javac -encoding UTF-8 StrictMeetingResolver.java
```

Dùng trong service hoặc unit test:

```java
Instant confirmed = StrictMeetingResolver.resolve(
    LocalDateTime.of(2026, 11, 1, 1, 30),
    ZoneId.of("America/New_York"),
    ZoneOffset.of("-05:00"));
// 2026-11-01T06:30:00Z
```

Chính sách của resolver: **gap bị từ chối**, **overlap cần offset lựa chọn**, thời gian bình thường tự chọn offset duy nhất nếu request không truyền offset. Đây là một ví dụ chính sách rõ ràng; ứng dụng thực tế có thể chọn policy khác, nhưng nên để phía người dùng biết. Bảo đảm thông báo lỗi nghiệp vụ phù hợp ngôn ngữ giao diện.

### Nếu client chỉ gửi local và zone?

Khi còn thiếu offset và vùng ở overlap, chưa thể chắc chắn người dùng muốn mốc nào. Server nên trả danh sách lựa chọn có offset và thông tin “lần đầu/lần sau” hoặc một trạng thái yêu cầu xác nhận. Không nên tự chọn mà giao diện không thông báo. Khi đã xác định xong, lưu:

```json
{
  "startInstant": "2026-11-01T06:30:00Z",
  "organizerZone": "America/New_York"
}
```

Mốc `startInstant` giúp sắp xếp sự kiện và tính khoảng thực; `organizerZone` giúp hiển thị giờ tổ chức đúng vùng và phục vụ các quy tắc địa phương sau này. Chỉ lưu một `LocalDateTime` trong overlap sẽ làm mất thông tin lựa chọn lần xuất hiện.

## 11. Lưu trữ và kiểm thử

### 11.1. Thiết kế dữ liệu

| Dữ liệu | Kiểu Java | Khi nào cần |
| --- | --- | --- |
| Ngày giờ user nhập | `LocalDateTime` | Trước khi giải quyết theo zone |
| Offset đã chọn | `ZoneOffset` | Đặc biệt khi overlap |
| Vùng tổ chức | `ZoneId` | Giữ ngữ cảnh vùng và lịch sử/quy tắc |
| Mốc sự kiện đã chốt | `Instant` | Lưu bản ghi event đã xác định |
| Thời lượng thực | `Duration` trên hai `Instant` | Đo elapsed time đúng qua DST |

Các kiểu SQL `TIMESTAMP WITHOUT TIME ZONE` và `TIMESTAMP WITH TIME ZONE` có semantics khác nhau giữa các DB. Nhiều DB không giữ nguyên ID vùng IANA trong trường timestamp; nếu cần tái tạo `America/New_York` hãy lưu zone ID riêng. Không tự áp timezone server cho chuỗi local trần từ request.

### 11.2. Bộ test bắt buộc

| Ca | Input | Kết quả mong đợi |
| --- | --- | --- |
| Bình thường mùa hè | `2026-07-01 09:30`, NY, `-04:00` | Thành công: `2026-07-01T13:30Z` |
| Offset sai mùa hè | Cùng local/NY, `-05:00` | `DateTimeException` |
| Gap | `2026-03-08 02:30`, NY, `-05:00` | `DateTimeException` |
| Gap với offset mới | Cùng local/NY, `-04:00` | `DateTimeException` |
| Overlap lần đầu | `2026-11-01 01:30`, NY, `-04:00` | `05:30Z` |
| Overlap lần sau | Cùng local/NY, `-05:00` | `06:30Z` |
| Offset sai overlap | Cùng local/NY, `-06:00` | `DateTimeException` |
| Giờ bình thường mùa đông | `2026-12-01 09:30`, NY, `-05:00` | Thành công |
| Zone offset cố định | `2026-07-01 09:30`, zone `+07:00` và offset `+07:00` | Thành công |
| Resolver thiếu offset ở overlap | Giờ overlap và offset null | Báo lỗi cần lựa chọn |
| Input null | `ofStrict(null, offset, zone)` | `NullPointerException` |
| Zone ID lạ | `ZoneId.of("No/Such_Zone")` | Lỗi ID không được hỗ trợ |

Test bằng ngày giờ, offset và zone tường minh để không phụ thuộc đồng hồ thật. Nếu service có thêm điều kiện “cuộc hẹn phải sau hiện tại”, truyền `Clock` cho service, dùng `Clock.fixed(...)` trong test rồi so **hai `Instant`** đã xác định. Tránh gọi `LocalDateTime.now()` theo múi giờ mặc định của CI.

### 11.3. Chú ý tzdb và thời gian tương lai

Zone rules có thể thay đổi khi luật địa phương được sửa và JDK cập nhật tzdb. Một thời điểm đã chốt cần lưu `Instant`; muốn giữ biểu diễn giờ tổ chức, lưu cả `ZoneId` và dữ liệu lựa chọn offset nếu yêu cầu audit. Lịch lặp “09:00 thứ Hai tại New York” phải áp dụng zone rules cho từng occurrence, không lưu cứng một offset hiện tại.

## 12. Sai lầm thường gặp

1. **Dùng `atZone` và nghĩ rằng mọi giờ local đều hợp lệ.** Ở gap, `atZone` mặc định dời giờ; `ofStrict` từ chối.
2. **Chỉ lưu `LocalDateTime` và `ZoneId` trong overlap.** Không phân biệt được hai lần 01:30 nếu thiếu lựa chọn offset hoặc `Instant`.
3. **Nghĩ `ofStrict` tự chọn offset.** Caller phải cung cấp offset; nếu sai, API ném lỗi.
4. **Nhầm strict của `DateTimeFormatter` với strict của `ZonedDateTime`.** Một cái kiểm tra parse ngày/giờ; cái kia kiểm tra offset so với luật vùng.
5. **Dùng offset mùa đông cho cuộc họp mùa hè.** Offset có thể hợp lệ ở ngày khác nhưng sai trong ngày đang xét.
6. **Dùng `ZoneOffset` như tên vùng.** Offset không chứa quy tắc DST của thành phố.
7. **Gọi `getOffset(LocalDateTime)` để xác thực input strict.** Dùng `getValidOffsets`/`isValidOffset`.
8. **Dùng `ofLocal` với preferred offset như kiểm tra strict.** `ofLocal` có thể fallback khi preferred không hợp lệ.
9. **Cố khôi phục tên vùng chỉ từ `Instant` hoặc `ZoneOffset`.** Mốc tuyệt đối và offset riêng không ghi lại danh tính vùng ban đầu.
10. **Tự lấy `ZoneId.systemDefault()` khi request có vùng rõ.** Điều đó khiến kết quả phụ thuộc máy chủ.
11. **So sự kiện bằng chuỗi local.** Hai giờ local giống nhau ở overlap có thể là hai instant khác nhau.
12. **Giữ offset cố định cho lịch lặp tương lai.** DST làm thay đổi offset; cần zone ID và áp luật theo từng occurrence.
13. **Giữ exception rồi tự sửa giờ mà không có policy.** Cần thông báo lỗi, yêu cầu chọn lại hoặc policy minh bạch.
14. **Coi tất cả khoảng ngày lịch là 24 giờ.** Qua DST, cộng một ngày local và cộng 24 giờ trên timeline có thể khác nhau.

## 13. Bài tập tự luyện

### Bài 1 — Xác thực mùa hè

Cho `LocalDateTime.of(2026,7,1,9,30)` và `America/New_York`. Thử `ofStrict` với `-04:00` và `-05:00`, giải thích vì sao chỉ một tổ hợp hợp lệ. Khi thành công, in `toInstant()`.

### Bài 2 — Cùng local, hai instant

Tạo `LocalDateTime.of(2026,11,1,1,30)`. Lấy danh sách offset hợp lệ của New York, gọi `ofStrict` cho cả hai, so `Duration.between(first.toInstant(), second.toInstant()).toMinutes()`. Kỳ vọng `60` phút.

### Bài 3 — Gap và chính sách

Với `2026-03-08T02:30` ở New York, chứng minh `getValidOffsets` rỗng; thử `ofStrict` với cả offset trước/sau DST. So hành vi với `atZone`. Viết thông báo lỗi hướng người dùng chọn giờ tồn tại.

### Bài 4 — API có chọn offset

Thiết kế request gồm `localStart`, `timeZone`, `selectedOffset`; khi có 1 offset thì có thể bỏ `selectedOffset`, khi có 2 offset thì yêu cầu lựa chọn, khi có 0 offset thì báo lỗi. Trả về `Instant` và `ZoneId` khi xác nhận thành công.

### Bài 5 — Unit test

Viết test JUnit 5 cho resolver: bình thường, gap, overlap thiếu lựa chọn, overlap chọn lần đầu, chọn lần sau, offset sai và zone không tồn tại. Xác nhận đúng exception và kết quả instant; đừng dựa vào giờ hiện tại của máy.

## 14. Checklist kết thúc

- [ ] Mô tả được ba đối số của `ZonedDateTime.ofStrict(local, offset, zone)`.
- [ ] Phân biệt `LocalDateTime`, `ZoneOffset`, `ZoneId`, `ZonedDateTime` và `Instant`.
- [ ] Biết vì sao offset có thể hợp lệ ở ngày này nhưng sai vào ngày khác trong cùng vùng.
- [ ] Phát hiện DST gap bằng danh sách offset rỗng và DST overlap bằng hai offset.
- [ ] Hiểu `ofStrict` từ chối tổ hợp sai thay vì âm thầm điều chỉnh.
- [ ] Phân biệt `ofStrict`, `atZone`, `ofLocal`, `atOffset` và `ofInstant`.
- [ ] Chọn policy hiển thị/giao diện rõ ràng khi giờ địa phương mơ hồ.
- [ ] Chuyển đối tượng đã xác thực sang `Instant` để lưu event tuyệt đối.
- [ ] Test đủ trường hợp thành công, sai offset, gap, overlap và giờ theo mùa.
- [ ] Không dựa timezone của máy hoặc offset “hiện tại” để tính lịch trong tương lai.

## Tài liệu Java 17 chính thức

- [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html)
- [ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [DateTimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DateTimeException.html)
