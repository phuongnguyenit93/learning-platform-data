# ZoneRules và ZoneOffsetTransition: hiểu quy tắc múi giờ trong Java

**`ZoneRules`** và **`ZoneOffsetTransition`** nằm trong package `java.time.zone`, thuộc API ngày giờ Java được giới thiệu bởi JSR 310 từ **Java 8**. Chúng vẫn là API hiện hành để trả lời hai câu hỏi khó mà một độ lệch UTC cố định không thể giải quyết:

- **Tại một `Instant` đã biết, vùng múi giờ có offset UTC nào?**
- **Tại một giờ đồng hồ địa phương (`LocalDateTime`), có bao nhiêu offset hợp lệ?** Giờ ấy có thể xảy ra **một lần**, **không xảy ra** (*gap*) hoặc **xảy ra hai lần** (*overlap*) vì đồng hồ thay đổi theo quy định của vùng.

Khi lên lịch hẹn, nhận timestamp từ người dùng, tính giờ họp xuyên biên giới hoặc kiểm tra lịch hoạt động qua mùa DST, hai lớp này giúp xác định **quy tắc thực tế của vùng** và **chính sách xử lý giờ không tồn tại/mơ hồ**.

Bài học trình bày cơ chế, bảng API, chương trình Java 17+ chạy được, kết quả stdout cố định theo dữ liệu TZDB được kiểm tra, lỗi thường gặp và cách thiết kế một bộ phân giải giờ địa phương không âm thầm làm sai lịch hẹn. Các API cốt lõi đều có từ Java 8 và còn được sử dụng hiện nay; không dùng `java.util.TimeZone`/`Calendar` như mô hình chính.

## 1. Ba kiểu dữ liệu không được nhầm lẫn

| Kiểu | Đang biểu diễn gì? | Có đủ dữ liệu để xác định moment duy nhất? |
| --- | --- | --- |
| `Instant` | Một điểm xác định trên timeline UTC | **Có**, tự thân là một moment |
| `LocalDateTime` | Ngày và giờ trên đồng hồ, **không có zone/offset** | **Không** |
| `ZoneOffset` | Độ lệch UTC, ví dụ `-05:00` hay `+07:00` | Chỉ offset, **không có ngày giờ** |
| `ZoneId` | Định danh vùng như `America/New_York` | Cần kết hợp với ngày/giờ hoặc Instant |
| `ZonedDateTime` | Ngày giờ + vùng + offset đã được giải quyết | **Có**, sau khi giải quyết |
| `OffsetDateTime` | Ngày giờ + một offset cụ thể | **Có**, nhưng không giữ region rules |

`ZoneOffset.ofHours(7)` mô tả đúng một độ lệch `+07:00`. Nó không hứa rằng một vùng lãnh thổ luôn dùng offset này trong toàn bộ lịch sử. Ngược lại, `ZoneId.of("Asia/Ho_Chi_Minh")` là một **region ID**; `zone.getRules()` cung cấp quy tắc có hiệu lực theo thời gian của vùng đó.

`LocalDateTime.of(2024,11,3,1,30)` là một giá trị ngày giờ **hợp lệ về lịch**, nhưng tại New York nó rơi vào đoạn đồng hồ quay lùi. Vì vậy không có một `Instant` duy nhất nếu chưa chọn offset phù hợp. Đây chính là lý do `ZoneRules` tồn tại.

## 2. `ZoneRules` là gì và lấy ở đâu?

`ZoneRules` biểu diễn **các quy tắc làm offset của một zone biến đổi theo thời gian**, bao gồm thay đổi lịch sử và các thuật toán dự báo chuyển offset về sau nếu dữ liệu nhà cung cấp có. Một bộ quy tắc có thể gồm:
- Offset chuẩn và offset thực tế theo `Instant`.
- Các lần chuyển offset cụ thể, được biểu diễn bởi `ZoneOffsetTransition`.
- Quy tắc sinh lần chuyển trong những năm sau phần lịch sử đã được định nghĩa, dùng `ZoneOffsetTransitionRule`.
- Thông tin để kiểm tra một `LocalDateTime` có **0, 1 hoặc nhiều offset hợp lệ**.

Cách lấy chuẩn:

```java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();
```

Đoạn mã nằm trong phương thức đã import `java.time.ZoneId` và `java.time.zone.ZoneRules`.

**`ZoneRules` không phải `ZoneId`.** `ZoneId` là tên vùng để ứng dụng lưu và truyền; `ZoneRules` là bộ dữ liệu quy tắc liên kết với tên ấy. Các quy tắc được cung cấp thông qua `ZoneRulesProvider`, thường dựa trên dữ liệu múi giờ kèm theo JDK. Chúng có thể thay đổi theo phiên bản TZDB hoặc nhà cung cấp quy tắc, vì chính sách của địa phương có thể thay đổi.

`ZoneRules` là lớp **immutable, thread-safe**. Không nên dùng một bản copy quy tắc lưu vĩnh viễn trong database thay cho region ID mà không có chiến lược cập nhật. Các luật DST tương lai không phải hằng số vĩnh viễn.

### `isFixedOffset()`

`rules.isFixedOffset()` trả true khi bộ quy tắc **không thay đổi offset giữa các instant**. `ZoneOffset.ofHours(7).getRules().isFixedOffset()` trả true. Ngược lại, `America/New_York` có các chuyển đổi nên trả false.

**Không được suy luận từ offset ở ngày hôm nay rằng một region có fixed offset.** Muốn biết rule set thật sự có biến đổi, hỏi `isFixedOffset()`; lưu ý các region có thể thay đổi offset trong lịch sử ngay cả khi hiện tại không dùng DST.

## 3. Hai timeline và nguồn gốc của gap/overlap

Một múi giờ liên kết hai timeline:
- **Instant timeline**: thứ tự liên tục của các moment thực.
- **Local timeline**: chuỗi ngày giờ mà người dân nhìn thấy trên đồng hồ địa phương.

Chuyển từ một `Instant` sang giờ địa phương là **xác định** với quy tắc zone đang có: ở một moment cụ thể có một offset áp dụng. Vì vậy `rules.getOffset(instant)` trả offset tương ứng.

Chiều ngược lại **không luôn xác định**:

```text
Instant ── (ZoneRules) ──> LocalDateTime + ZoneOffset
                    một instant → một offset

LocalDateTime ── (ZoneRules) ──> [ZoneOffset]
                    có thể có 0, 1 hoặc 2 offset
```

Ba trạng thái điển hình:

| Trạng thái | Số offset hợp lệ thường gặp | Điều gì xảy ra? |
| --- | --- | --- |
| **Normal** | 1 | Giờ địa phương diễn ra đúng một lần |
| **Gap** | 0 | Đồng hồ nhảy **tiến**, một đoạn giờ địa phương không từng xảy ra |
| **Overlap** | 2 | Đồng hồ quay **lùi**, một đoạn giờ địa phương xảy ra hai lần |

Tài liệu `ZoneRules` lưu ý về mặt lý thuyết có thể có tình huống phức tạp hơn hai offset trong những chuyển đổi bất thường liên tiếp; trên dữ liệu múi giờ thực tế thông thường là 0/1/2. Vì vậy khi viết logic xử lý chung, dùng kích thước danh sách thực tế; nếu nghiệp vụ chỉ cho phép 1 hoặc 2, xử lý trường hợp bất thường bằng lỗi có chủ đích.

## 4. API `ZoneRules` cần thuộc nhóm ý nghĩa

| Phương thức | Tham số | Mục đích |
| --- | --- | --- |
| `getOffset(Instant)` | Moment đã biết | Lấy offset thực sự áp dụng tại moment đó |
| `getOffset(LocalDateTime)` | Đồng hồ địa phương | Lấy offset *phù hợp nhất*, **chưa chứng minh duy nhất/hợp lệ** |
| `getValidOffsets(LocalDateTime)` | Đồng hồ địa phương | Trả danh sách các offset hợp lệ; rỗng khi gap |
| `getTransition(LocalDateTime)` | Đồng hồ địa phương | Trả `ZoneOffsetTransition` nếu nằm trong gap/overlap; normal → `null` |
| `isValidOffset(LocalDateTime, ZoneOffset)` | Local + offset cụ thể | Kiểm tra offset có hợp lệ cho local time trong zone này không |
| `getStandardOffset(Instant)` | Moment đã biết | Offset **chuẩn** tại thời điểm đó |
| `getDaylightSavings(Instant)` | Moment đã biết | Mức chênh giữa offset thực và offset chuẩn dạng `Duration` |
| `isDaylightSavings(Instant)` | Moment đã biết | Có áp dụng daylight savings tại moment không |
| `isFixedOffset()` | Không | Bộ quy tắc có một offset cố định không |
| `nextTransition(Instant)` | Mốc trên timeline | Tìm lần đổi offset tiếp theo, có thể `null` |
| `previousTransition(Instant)` | Mốc trên timeline | Tìm lần đổi offset trước đó, có thể `null` |
| `getTransitions()` | Không | Danh sách các transition **được định nghĩa đầy đủ** |
| `getTransitionRules()` | Không | Danh sách quy tắc thuật toán cho các năm sau danh sách transition cụ thể |

**Phương thức quan trọng nhất khi nhận giờ hẹn từ người dùng là `getValidOffsets`**, không phải chỉ `getOffset(localDateTime)`. Phương thức thứ hai có thể trả một offset “best effort” trong gap, mặc dù offset ấy **không hợp lệ cho local time đang hỏi**.

## 5. Đọc offset của một `Instant`: không có ambiguity

Đầu vào là một `Instant` cố định:

```java
ZoneId ny = ZoneId.of("America/New_York");
ZoneRules rules = ny.getRules();

ZoneOffset winter = rules.getOffset(
        Instant.parse("2024-01-15T12:00:00Z"));
ZoneOffset summer = rules.getOffset(
        Instant.parse("2024-07-15T12:00:00Z"));
```

Với các quy tắc New York năm 2024, `winter` bằng `-05:00` và `summer` bằng `-04:00`. Không có việc chọn giữa hai offset tại **một Instant đã biết**.

Đừng lấy `LocalDateTime.now()` làm đầu vào cho logic audit timestamp nếu ý định là “moment thực”. Lấy `Instant.now(clock)`, sau đó chuyển qua zone của người dùng để hiển thị:

```java
Instant timestamp = Instant.parse("2024-07-15T12:00:00Z");
ZonedDateTime local = timestamp.atZone(ny);
// 2024-07-15T08:00-04:00[America/New_York]
```

`Instant` còn dùng để so thứ tự timeline, đo elapsed time và lưu thời điểm giao dịch. `LocalDateTime` nên được giữ cho yêu cầu dạng “09:00 tại một địa điểm” trước khi giải quyết zone và quy tắc DST.

## 6. Offset chuẩn và daylight saving time

`getStandardOffset(instant)` khác `getOffset(instant)`. Offset **standard** là nền thời gian tiêu chuẩn của vùng tại instant đó; offset thực tế có thể cộng thêm mức tiết kiệm ánh sáng ban ngày (*daylight saving time*). `getDaylightSavings` trả `Duration` biểu diễn chênh lệch này; không mặc định mọi vùng đều là đúng +1 giờ.

Trong ví dụ New York năm 2024:
- Mùa đông: offset thực `-05:00`, standard `-05:00`, daylight savings `PT0S`.
- Mùa hè: offset thực `-04:00`, standard `-05:00`, daylight savings `PT1H`.
- `isDaylightSavings(summerInstant)` trả true.

Đừng suy ra DST bằng cách thấy offset nào “trông lớn hơn” hoặc lấy offset hiện tại trừ offset được hardcode theo quốc gia. Dùng các API trên `ZoneRules` tại **Instant đang quan tâm**. Trong lịch sử, vùng có thể chuyển cả **standard offset** mà không chỉ đổi DST, và độ dài chuyển đổi cũng không bắt buộc là một giờ.

## 7. Chương trình đầy đủ: đọc `ZoneRules` ở mùa đông/mùa hè

Tạo `ZoneRulesLookupDemo.java`:

```java
import java.time.*;
import java.time.zone.ZoneRules;

public class ZoneRulesLookupDemo {
    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");
        ZoneRules r = ny.getRules();

        Instant winter = Instant.parse(
                "2024-01-15T12:00:00Z");
        Instant summer = Instant.parse(
                "2024-07-15T12:00:00Z");
        LocalDateTime normal = LocalDateTime.of(
                2024, 2, 1, 12, 0);

        System.out.println("zone = " + ny);
        System.out.println("fixed = " + r.isFixedOffset());
        System.out.println("winter offset = " + r.getOffset(winter));
        System.out.println("summer offset = " + r.getOffset(summer));
        System.out.println("winter standard = " +
                r.getStandardOffset(winter));
        System.out.println("summer standard = " +
                r.getStandardOffset(summer));
        System.out.println("winter savings = " +
                r.getDaylightSavings(winter));
        System.out.println("summer savings = " +
                r.getDaylightSavings(summer));
        System.out.println("summer DST = " +
                r.isDaylightSavings(summer));
        System.out.println("normal valid offsets = " +
                r.getValidOffsets(normal));
        System.out.println("normal transition = " +
                r.getTransition(normal));

        ZoneRules fixed = ZoneOffset.ofHours(7).getRules();
        System.out.println("UTC+7 fixed = " + fixed.isFixedOffset());
        System.out.println("UTC+7 offset = " +
                fixed.getOffset(winter));
    }
}
```

```bash
javac -encoding UTF-8 ZoneRulesLookupDemo.java
java ZoneRulesLookupDemo
```

```text
zone = America/New_York
fixed = false
winter offset = -05:00
summer offset = -04:00
winter standard = -05:00
summer standard = -05:00
winter savings = PT0S
summer savings = PT1H
summer DST = true
normal valid offsets = [-05:00]
normal transition = null
UTC+7 fixed = true
UTC+7 offset = +07:00
```

Các dòng **normal valid offsets = [-05:00]** và **normal transition = null** minh họa một ngày giờ không nằm trong vùng chuyển đổi. `ZoneOffset.ofHours(7)` tạo offset cố định; đây không phải cách thay thế `ZoneId.of("Asia/Ho_Chi_Minh")` trong dữ liệu cần biết lịch sử/quy tắc region.

Các đầu vào ở ví dụ đều cố định nên không phụ thuộc timezone hệ thống; kết quả thực thi đã được kiểm tra với JDK 24 và dữ liệu vùng New York 2024. Dữ liệu IANA/TZDB có thể thay đổi khi nhà chức trách sửa luật; nếu cập nhật JDK làm thay đổi dữ liệu vùng, cần xác minh lại những kỳ vọng gắn với zone.

## 8. Gap: khi đồng hồ nhảy tiến

Tại vùng `America/New_York` ngày **10/03/2024**, đồng hồ chuyển từ **01:59:59-05:00** sang **03:00:00-04:00**. Khoảng địa phương từ **02:00** đến trước **03:00** **không xảy ra**. Đây là **gap**.

`LocalDateTime.of(2024,3,10,2,30)` vẫn là đối tượng LocalDateTime hợp lệ, nhưng **không có offset hợp lệ** để ánh xạ 02:30 tại New York sang một Instant.

```java
ZoneRules r = ZoneId.of("America/New_York").getRules();
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

r.getValidOffsets(gap); // [] — danh sách rỗng
r.getOffset(gap);       // -05:00 — chỉ là offset "best"
r.isValidOffset(gap, ZoneOffset.ofHours(-5)); // false
r.getTransition(gap);  // ZoneOffsetTransition không null
```

**Cảnh báo:** `getOffset(gap)` trả `-05:00` (offset trước khi chuyển), nhưng **không có nghĩa 02:30-05:00 là một thời điểm có thật tại New York**. Đây là lý do phải xem `getValidOffsets` và `getTransition` khi cần validate input địa phương.

Một transition gap có:
- `offsetBefore = -05:00`.
- `offsetAfter = -04:00`.
- `getDateTimeBefore() = 2024-03-10T02:00`.
- `getDateTimeAfter() = 2024-03-10T03:00`.
- `getInstant() = 2024-03-10T07:00:00Z`.
- `getDuration() = PT1H` và `isGap() = true`.

Không giả định gap luôn là một giờ. `ZoneOffsetTransition.getDuration()` cho biết chênh lệch thực tế; một số lịch sử múi giờ có những thay đổi không phải 60 phút.

## 9. `ZoneOffsetTransition` mô tả điều gì?

`ZoneOffsetTransition` là đối tượng mô tả **một lần offset thay đổi làm local timeline không liên tục**, thường gặp tại chuyển DST. Lớp này là **immutable, thread-safe** và có từ Java 8.

| API | Ý nghĩa |
| --- | --- |
| `getInstant()` | Instant chuyển đổi; offset mới bắt đầu áp dụng từ đó |
| `getOffsetBefore()` | Offset ngay trước transition |
| `getOffsetAfter()` | Offset ngay từ transition trở đi |
| `getDateTimeBefore()` | Biểu diễn giờ địa phương tại ranh giới theo offset **trước** |
| `getDateTimeAfter()` | Biểu diễn giờ địa phương tại ranh giới theo offset **sau** |
| `getDuration()` | Hiệu giữa hai offset dạng `Duration`: **dương khi gap**, **âm khi overlap** |
| `isGap()` | Đồng hồ tiến, xuất hiện giờ địa phương không tồn tại |
| `isOverlap()` | Đồng hồ lùi, xuất hiện giờ địa phương lặp |
| `isValidOffset(ZoneOffset)` | Offset có hợp lệ trong transition đang xét không |
| `toEpochSecond()` | Instant chuyển đổi biểu diễn bằng epoch seconds |

Đối với gap `-05:00 → -04:00`, duration `+01:00`. Đối với overlap `-04:00 → -05:00`, duration `-01:00`.

**Hai biểu diễn `getDateTimeBefore` + `getOffsetBefore` và `getDateTimeAfter` + `getOffsetAfter` dùng để mô tả cùng ranh giới timeline**, nhưng trong trường hợp gap, “giờ địa phương phía trước” ở chính ranh giới không phải một cuộc hẹn có thể tồn tại theo offset cũ. Hãy coi chúng là **mô tả chuyển đổi**, không tự tạo lịch hẹn dựa vào ranh giới mà không kiểm tra.

Thông thường lấy `ZoneOffsetTransition` từ `ZoneRules.getTransition(local)`, `nextTransition(instant)` hoặc `previousTransition(instant)`. Factory `ZoneOffsetTransition.of(...)` được API cung cấp chủ yếu cho việc xây `ZoneRules`; ứng dụng thường **không tự tạo luật múi giờ** để thay cho dữ liệu IANA của một vùng có thật.

## 10. Chương trình đầy đủ: đọc gap transition

Tạo `GapTransitionDemo.java`:

```java
import java.time.*;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class GapTransitionDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();
        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        ZoneOffsetTransition t = rules.getTransition(gap);

        System.out.println("gap offsets = " +
                rules.getValidOffsets(gap));
        System.out.println("gap best offset = " +
                rules.getOffset(gap));
        System.out.println("gap transition instant = " +
                t.getInstant());
        System.out.println("gap before local = " +
                t.getDateTimeBefore());
        System.out.println("gap after local = " +
                t.getDateTimeAfter());
        System.out.println("gap offset before = " +
                t.getOffsetBefore());
        System.out.println("gap offset after = " +
                t.getOffsetAfter());
        System.out.println("gap duration = " + t.getDuration());
        System.out.println("gap isGap = " + t.isGap());
        System.out.println("gap isOverlap = " + t.isOverlap());

        System.out.println("gap offset valid = " +
                rules.isValidOffset(
                        gap, ZoneOffset.ofHours(-5)));
        System.out.println("gap atZone = " + gap.atZone(zone));

        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(-5), zone);
        } catch (DateTimeException ex) {
            System.out.println(
                    "gap strict = DateTimeException");
        }
    }
}
```

```bash
javac -encoding UTF-8 GapTransitionDemo.java
java GapTransitionDemo
```

```text
gap offsets = []
gap best offset = -05:00
gap transition instant = 2024-03-10T07:00:00Z
gap before local = 2024-03-10T02:00
gap after local = 2024-03-10T03:00
gap offset before = -05:00
gap offset after = -04:00
gap duration = PT1H
gap isGap = true
gap isOverlap = false
gap offset valid = false
gap atZone = 2024-03-10T03:30-04:00[America/New_York]
gap strict = DateTimeException
```

`gap.atZone(zone)` mặc định **đẩy 02:30 tiến một giờ tới 03:30-04:00**. Đây là hành vi giải quyết gap của `ZonedDateTime`, **không phải xác nhận rằng người dùng ban đầu đã yêu cầu 03:30**.

Nếu nghiệp vụ là “lịch khám lúc 02:30 đúng như khách đã chọn”, tự điều chỉnh thành 03:30 mà không thông báo có thể sai. Dùng `getValidOffsets(gap).isEmpty()` để **từ chối hoặc yêu cầu chọn lại giờ**, hoặc áp dụng chính sách đẩy giờ được mô tả rõ trong sản phẩm.

`ZonedDateTime.ofStrict(local, offset, zone)` yêu cầu offset được cung cấp **thực sự hợp lệ** trong zone tại local time, nên ném `DateTimeException` cho local time nằm trong gap.

## 11. Overlap: một giờ đồng hồ xảy ra hai lần

Tại New York ngày **03/11/2024**, đồng hồ quay từ gần **02:00-04:00** về **01:00-05:00**. Giờ địa phương `01:30` xảy ra hai lần:

| Giờ cục bộ | Offset | Instant |
| --- | --- | --- |
| `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

Cả hai đều là **giờ có thật**, cách nhau 60 phút trên timeline. `LocalDateTime` **không đủ** để xác định cuộc hẹn là lần thứ nhất hay lần thứ hai.

```java
ZoneRules rules =
        ZoneId.of("America/New_York").getRules();
LocalDateTime overlap =
        LocalDateTime.of(2024, 11, 3, 1, 30);

rules.getValidOffsets(overlap); // [-04:00, -05:00]
rules.getOffset(overlap);       // -04:00, offset trước chuyển
rules.getTransition(overlap);   // transition có isOverlap() == true
```

Theo JavaDoc, khi có hai offset, `getValidOffsets` trả offset **sớm hơn** tại chỉ số 0 và offset **muộn hơn** tại chỉ số 1. “Sớm hơn/muộn hơn” ở đây nói về lựa chọn theo quá trình chuyển offset, không đồng nghĩa so sánh độ lớn số học của chuỗi `-04:00` và `-05:00`.

Với transition năm 2024:
- `offsetBefore = -04:00`.
- `offsetAfter = -05:00`.
- `getDateTimeBefore() = 2024-11-03T02:00`.
- `getDateTimeAfter() = 2024-11-03T01:00`.
- `getInstant() = 2024-11-03T06:00:00Z`.
- `getDuration() = PT-1H` và `isOverlap() = true`.

**Overlap không phải lỗi dữ liệu tự thân**. Nó là hiện tượng hợp lệ của múi giờ. Lỗi xảy ra khi ứng dụng chọn một instant **mà không nêu chính sách** hoặc làm mất offset đã được người dùng xác định.

## 12. Chương trình đầy đủ: đọc overlap và chọn hai Instant

Tạo `OverlapTransitionDemo.java`:

```java
import java.time.*;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class OverlapTransitionDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();
        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);
        ZoneOffsetTransition t =
                rules.getTransition(overlap);

        System.out.println("overlap offsets = " +
                rules.getValidOffsets(overlap));
        System.out.println("overlap best offset = " +
                rules.getOffset(overlap));
        System.out.println("overlap transition instant = " +
                t.getInstant());
        System.out.println("overlap before local = " +
                t.getDateTimeBefore());
        System.out.println("overlap after local = " +
                t.getDateTimeAfter());
        System.out.println("overlap offset before = " +
                t.getOffsetBefore());
        System.out.println("overlap offset after = " +
                t.getOffsetAfter());
        System.out.println("overlap duration = " +
                t.getDuration());
        System.out.println("overlap isGap = " + t.isGap());
        System.out.println("overlap isOverlap = " + t.isOverlap());

        ZonedDateTime early = overlap.atZone(zone);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();

        System.out.println("earlier = " + early);
        System.out.println("later = " + late);
        System.out.println("earlier instant = " +
                early.toInstant());
        System.out.println("later instant = " +
                late.toInstant());
        System.out.println("instants apart minutes = " +
                Duration.between(
                        early.toInstant(), late.toInstant())
                        .toMinutes());

        System.out.println("strict later = " +
                ZonedDateTime.ofStrict(
                        overlap, ZoneOffset.ofHours(-5), zone));
        System.out.println("overlap -05 valid = " +
                rules.isValidOffset(
                        overlap, ZoneOffset.ofHours(-5)));
    }
}
```

```bash
javac -encoding UTF-8 OverlapTransitionDemo.java
java OverlapTransitionDemo
```

```text
overlap offsets = [-04:00, -05:00]
overlap best offset = -04:00
overlap transition instant = 2024-11-03T06:00:00Z
overlap before local = 2024-11-03T02:00
overlap after local = 2024-11-03T01:00
overlap offset before = -04:00
overlap offset after = -05:00
overlap duration = PT-1H
overlap isGap = false
overlap isOverlap = true
earlier = 2024-11-03T01:30-04:00[America/New_York]
later = 2024-11-03T01:30-05:00[America/New_York]
earlier instant = 2024-11-03T05:30:00Z
later instant = 2024-11-03T06:30:00Z
instants apart minutes = 60
strict later = 2024-11-03T01:30-05:00[America/New_York]
overlap -05 valid = true
```

`atZone` chọn offset sớm hơn trong trường hợp này khi không có offset trước đó để giữ, tức `-04:00`. `withLaterOffsetAtOverlap()` chọn `-05:00`; hai giá trị giữ cùng `LocalDateTime` nhưng `toInstant()` khác nhau.

Nếu ứng dụng lưu một cuộc hẹn cụ thể, hãy lưu **Instant đã chốt** cùng **ZoneId/offset và LocalDateTime khi cần bảo toàn cách người dùng đặt lịch**. Chỉ giữ chuỗi `2024-11-03 01:30 America/New_York` mà không có chính sách overlap có thể không đủ để khôi phục moment đã chọn.

## 13. `getOffset(LocalDateTime)` không phải “validator”

Đây là cạm bẫy quan trọng nhất của `ZoneRules`:

| LocalDateTime tại New York | `getValidOffsets` | `getOffset(local)` | Có moment duy nhất? |
| --- | --- | --- | --- |
| `2024-02-01T12:00` | `[-05:00]` | `-05:00` | Có |
| `2024-03-10T02:30` | `[]` | `-05:00` | **Không có moment hợp lệ** |
| `2024-11-03T01:30` | `[-04:00, -05:00]` | `-04:00` | **Có hai moment hợp lệ** |

Hợp đồng `getOffset(LocalDateTime)` nói nó trả offset phù hợp: **offset duy nhất** khi bình thường, **offset trước transition** nếu gap hoặc overlap. Trong hai trường hợp đặc biệt, đây là “best available” chứ không phải một chứng nhận hợp lệ.

Để xử lý đúng:
1. Lấy `List<ZoneOffset> offsets = rules.getValidOffsets(local)`.
2. Nếu **rỗng**: gặp gap; tùy domain mà từ chối hoặc chuyển sang giờ khác có thông báo.
3. Nếu **một**: dùng offset đó, có thể tạo `ZonedDateTime.ofStrict(...)`.
4. Nếu **nhiều**: yêu cầu chọn policy (offset sớm hơn/muộn hơn, lựa chọn đã lưu, hoặc từ chối lịch mơ hồ).
5. Kiểm tra offset được chọn bằng `isValidOffset` hoặc dùng `ofStrict` để bảo toàn hợp đồng.

**Không tự chọn `getOffset(local)` trong mọi nhánh rồi gọi `local.toInstant(offset)`.** `LocalDateTime.toInstant(ZoneOffset)` có thể tạo được instant từ một offset được truyền, nhưng nó không biết offset đó có hợp lệ tại region zone hay không. Phải xác minh bằng `ZoneRules` nếu tính chính xác múi giờ là yêu cầu.

## 14. Các cách `ZonedDateTime` giải quyết local time

Các API phổ biến có mục đích khác nhau:

- `local.atZone(zone)` hoặc `ZonedDateTime.of(local, zone)`: dùng cơ chế mặc định; **gap dịch tiến** một khoảng bằng gap; **overlap chọn offset sớm hơn** nếu không có offset cũ để giữ.
- `ZonedDateTime.ofLocal(local, zone, preferredOffset)`: cho phép đưa offset ưu tiên. Nếu offset đó hợp lệ trong overlap thì dùng nó; không hợp lệ thì fallback theo quy tắc mặc định, **không phải strict validator**.
- `ZonedDateTime.ofStrict(local, offset, zone)`: bảo đảm sự kết hợp `local + offset + zone` hợp lệ, nếu không thì ném `DateTimeException`.
- `zoned.withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()`: đổi giữa hai offset ở overlap nếu có; ngoài overlap không có tác dụng tương ứng.
- `instant.atZone(zone)` hoặc `ZonedDateTime.ofInstant(instant, zone)`: bắt đầu từ **Instant** nên không có ambiguity của LocalDateTime.
- `zoned.withZoneSameInstant(otherZone)`: đổi cách hiển thị vùng, **giữ moment**.
- `zoned.withZoneSameLocal(otherZone)`: cố giữ local clock, **có thể đổi moment**.

Một yêu cầu “người dùng nhập 02:30 tại New York” thường khác với yêu cầu “sự kiện lúc Instant X cần hiển thị theo giờ New York”. Đừng bắt một API đảm nhiệm cả hai mà không có contract rõ.

## 15. Ví dụ thực tế: bộ phân giải lịch hẹn yêu cầu lựa chọn tường minh

Dưới đây là một chính sách **strict** cho lịch hẹn đơn lẻ:
- Giờ trong gap ⇒ trả lỗi, không tự dời.
- Giờ trong overlap nhưng chưa chọn offset ⇒ trả lỗi “mơ hồ”.
- Giờ bình thường ⇒ lấy offset hợp lệ duy nhất.
- Nếu người dùng cung cấp offset, kiểm tra offset thuộc `getValidOffsets`; chỉ tạo `ZonedDateTime` khi kết hợp hợp lệ.

Tạo `SchedulePolicyDemo.java`:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

public class SchedulePolicyDemo {
    static ZonedDateTime resolveStrict(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset chosen) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> valid =
                rules.getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Nonexistent local time");
        }
        if (valid.size() > 1 && chosen == null) {
            throw new IllegalArgumentException(
                    "Ambiguous local time");
        }

        ZoneOffset offset =
                chosen == null ? valid.get(0) : chosen;

        if (!rules.isValidOffset(local, offset)) {
            throw new IllegalArgumentException(
                    "Invalid offset for zone");
        }

        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");

        System.out.println("normal = " +
                resolveStrict(
                        LocalDateTime.of(2024, 2, 1, 12, 0),
                        ny, null));

        try {
            resolveStrict(
                    LocalDateTime.of(2024, 3, 10, 2, 30),
                    ny, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("gap error = " +
                    ex.getMessage());
        }

        try {
            resolveStrict(
                    LocalDateTime.of(2024, 11, 3, 1, 30),
                    ny, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("overlap error = " +
                    ex.getMessage());
        }

        ZonedDateTime choice = resolveStrict(
                LocalDateTime.of(2024, 11, 3, 1, 30),
                ny, ZoneOffset.ofHours(-5));

        System.out.println("chosen overlap = " + choice);
        System.out.println("chosen instant = " +
                choice.toInstant());
    }
}
```

```bash
javac -encoding UTF-8 SchedulePolicyDemo.java
java SchedulePolicyDemo
```

```text
normal = 2024-02-01T12:00-05:00[America/New_York]
gap error = Nonexistent local time
overlap error = Ambiguous local time
chosen overlap = 2024-11-03T01:30-05:00[America/New_York]
chosen instant = 2024-11-03T06:30:00Z
```

Đây là **một chính sách nghiệp vụ mẫu**, không phải Java bắt buộc mọi ứng dụng phải từ chối gap/overlap. Một ứng dụng nhắc lịch có thể muốn dời giờ sau gap; một ứng dụng đặt lịch khám có thể cần yêu cầu người dùng chọn lại. Điểm bắt buộc là chính sách phải **tường minh, có test và không đánh mất lựa chọn của người dùng**.

Đối số `chosen` ở ví dụ được phép null để biểu thị chưa chọn offset, **không phải ánh xạ null thành một Instant mặc định**. Trong API lớn, nên cân nhắc mô hình kiểu trả kết quả có trạng thái rõ thay vì dùng `IllegalArgumentException` trần ở UI layer.

## 16. Tìm chuyển đổi tiếp theo và trước đó

`ZoneRules.nextTransition(Instant)` lấy lần đổi offset **sau** một moment, `previousTransition(Instant)` lấy lần đổi **trước** một moment. Cả hai có thể trả `null` khi không còn/không có transition được biết ở hướng tìm kiếm tương ứng, ví dụ zone có fixed offset.

Có thể dùng để:
- Cảnh báo người dùng về lịch hẹn gần ngày đổi giờ.
- Kiểm tra log giao dịch quanh mốc chuyển thời gian.
- Xác định có thay đổi offset trong một khoảng báo cáo không.
- Đặt test cho boundary ngay trước và sau transition.
- Phân tích chênh lệch giờ hiển thị giữa hai ngày.

```java
ZoneRules rules =
        ZoneId.of("America/New_York").getRules();

ZoneOffsetTransition next =
        rules.nextTransition(
                Instant.parse("2024-01-01T00:00:00Z"));

ZoneOffsetTransition previous =
        rules.previousTransition(
                Instant.parse("2024-12-01T00:00:00Z"));
```

Đoạn minh họa giả định import `java.time.*` và `java.time.zone.*`. Lưu ý **tham số của hai phương thức là Instant**, không phải LocalDateTime. Nếu đang có local clock mơ hồ, phải giải quyết nó trước khi tìm transition theo timeline.

Không lặp tìm `nextTransition` với cùng một Instant không đổi, vì sẽ gặp lại một chuyển đổi. Nếu cần duyệt nhiều transition, cập nhật mốc sang instant chuyển đổi hoặc ngay sau đó tùy mục đích, và luôn có điều kiện dừng để tránh vòng lặp vô hạn.

## 17. `getTransitions()` và `getTransitionRules()` khác nhau

`ZoneRules` có hai loại thông tin chuyển đổi:

1. **`getTransitions()`**: danh sách các `ZoneOffsetTransition` **đã được định nghĩa đầy đủ** trong rule set, thường dùng cho lịch sử nhưng cũng có thể có chuyển đổi tương lai được ghi cụ thể.
2. **`getTransitionRules()`**: danh sách các `ZoneOffsetTransitionRule` mô tả **thuật toán tạo transition cho những năm sau phần được định nghĩa đầy đủ**, thường là quy tắc DST lặp hằng năm.

**Không cho rằng `getTransitions()` chứa mọi ngày đổi DST mãi mãi**. Các transition trong tương lai có thể được sinh từ `ZoneOffsetTransitionRule` khi tra cứu, không cần hiện diện trực tiếp trong danh sách transition lịch sử.

`ZoneOffsetTransitionRule` có thông tin như tháng, ngày trong tháng, thứ trong tuần, giờ, kiểu định nghĩa thời gian và offset trước/sau. Nó có `createTransition(year)` để tạo transition cho năm cần xem theo rule hiện có.

Ví dụ ở mức minh họa (**không phải chương trình độc lập**):

```java
for (ZoneOffsetTransitionRule rule :
        zone.getRules().getTransitionRules()) {
    ZoneOffsetTransition candidate =
            rule.createTransition(2030);
    // Chỉ là dự báo theo rule set hiện tại.
}
```

Không hardcode rằng mọi vùng luôn có hai rule/năm hoặc luôn đổi đúng một giờ. Một vùng có thể không có DST, có ít hoặc không có transition được mô hình hóa, hoặc có lịch sử thay đổi phức tạp. **Quy tắc năm 2030 ở runtime hiện tại không phải cam kết rằng luật của năm 2030 sẽ giữ nguyên**.

Với nhu cầu lấy transition kế tiếp thực tế, `nextTransition(instant)` thường trực tiếp và ít lỗi hơn tự gộp danh sách lịch sử với các rule định kỳ.

## 18. Chương trình đầy đủ: next/previous transition và nguồn rule

Tạo `TransitionSearchDemo.java`:

```java
import java.time.*;
import java.time.zone.*;

public class TransitionSearchDemo {
    public static void main(String[] args) {
        ZoneRules rules =
                ZoneId.of("America/New_York").getRules();

        ZoneOffsetTransition next = rules.nextTransition(
                Instant.parse("2024-01-01T00:00:00Z"));
        ZoneOffsetTransition prev = rules.previousTransition(
                Instant.parse("2024-12-01T00:00:00Z"));

        System.out.println("next transition = " +
                next.getInstant());
        System.out.println("next type = " +
                (next.isGap() ? "GAP" : "OVERLAP"));
        System.out.println("previous transition = " +
                prev.getInstant());
        System.out.println("previous type = " +
                (prev.isGap() ? "GAP" : "OVERLAP"));

        System.out.println("recurring rules? = " +
                !rules.getTransitionRules().isEmpty());
        System.out.println("historical transitions available? = " +
                !rules.getTransitions().isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 TransitionSearchDemo.java
java TransitionSearchDemo
```

```text
next transition = 2024-03-10T07:00:00Z
next type = GAP
previous transition = 2024-11-03T06:00:00Z
previous type = OVERLAP
recurring rules? = true
historical transitions available? = true
```

Trong rule set New York của JDK đã kiểm tra, `getTransitions()` và `getTransitionRules()` đều không rỗng. **Không dựa vào số phần tử cụ thể của hai danh sách** làm quy tắc chung cho mọi phiên bản TZDB hoặc mọi zone.

Khi cần xử lý zone cố định, `nextTransition` có thể trả `null`. Đối với source không bảo đảm có thay đổi offset, hãy kiểm tra null trước khi gọi `getInstant()`, thay vì cho rằng mọi vùng đều có DST.

## 19. Cộng ngày lịch và cộng giờ thực qua transition

Một `ZonedDateTime` kết hợp ngày giờ địa phương với region zone và offset đã giải quyết. Tuy nhiên, cộng **một ngày lịch** và cộng **24 giờ elapsed** là hai phép tính khác nhau qua DST:

```java
ZonedDateTime base = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime plusDay = base.plusDays(1);
ZonedDateTime plusHours = base.plusHours(24);
```

- `plusDays(1)`: giữ ngày giờ địa phương theo phép cộng lịch, giải quyết zone; kết quả **12:00 ngày hôm sau** nhưng elapsed time chỉ 23 giờ tại điểm nhảy DST năm 2024.
- `plusHours(24)`: cộng đúng 24 giờ timeline; kết quả địa phương **13:00 ngày hôm sau**.
- `Duration.ofDays(1)` là 86.400 giây, không thay được quy tắc “ngày lịch tiếp theo” trong mọi vùng.
- Ngược lại tại overlap, một ngày lịch có thể là 25 giờ.

Nếu ứng dụng quy định “gửi báo cáo vào 12:00 giờ địa phương ngày tiếp theo”, dùng date-based arithmetic và region zone; nếu quy định “hết hạn đúng sau 24 giờ”, dùng instant + `Duration.ofHours(24)`. Hai chính sách đều có thể đúng, nhưng giải quyết các mục tiêu khác nhau.

## 20. Chương trình đầy đủ: ngày lịch và 24 giờ elapsed

Tạo `CalendarVsElapsedDemo.java`:

```java
import java.time.*;

public class CalendarVsElapsedDemo {
    public static void main(String[] args) {
        ZonedDateTime base = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0,
                ZoneId.of("America/New_York"));
        ZonedDateTime nextDay = base.plusDays(1);
        ZonedDateTime plus24h = base.plusHours(24);

        System.out.println("start = " + base);
        System.out.println("plusDays(1) = " + nextDay);
        System.out.println("plusHours(24) = " + plus24h);

        System.out.println("elapsed plus day = " +
                Duration.between(
                        base.toInstant(),
                        nextDay.toInstant()).toHours());
        System.out.println("elapsed plus hours = " +
                Duration.between(
                        base.toInstant(),
                        plus24h.toInstant()).toHours());
    }
}
```

```bash
javac -encoding UTF-8 CalendarVsElapsedDemo.java
java CalendarVsElapsedDemo
```

```text
start = 2024-03-09T12:00-05:00[America/New_York]
plusDays(1) = 2024-03-10T12:00-04:00[America/New_York]
plusHours(24) = 2024-03-10T13:00-04:00[America/New_York]
elapsed plus day = 23
elapsed plus hours = 24
```

`ZoneOffsetTransition` giải thích vì sao chênh lệch ở đây phát sinh: vùng đổi từ `-05:00` sang `-04:00` trong khoảng giữa hai ngày. Đừng tìm “lỗi cộng ngày của Java” khi thật ra yêu cầu đang lẫn **calendar time** với **elapsed time**.

## 21. Fixed offset không phải tên vùng

`ZoneOffset.of("+07:00")` là offset **cố định**, không giữ quy tắc lịch sử của một vùng. Nó có thể là lựa chọn phù hợp nếu giao thức chỉ truyền độ lệch UTC thực tế của một timestamp:

```java
ZoneOffset fixed = ZoneOffset.ofHours(7);
ZoneRules rules = fixed.getRules();

rules.isFixedOffset(); // true
```

Nhưng cuộc họp tái diễn “09:00 hằng ngày tại một thành phố” thường cần **region ZoneId** (ví dụ `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`) vì:
- Region có thể có thay đổi lịch sử hoặc chính sách tương lai.
- Offset của một ngày không mặc nhiên là offset của ngày khác.
- Một offset có thể được nhiều vùng dùng ở cùng thời điểm.
- Không thể suy ra region từ offset `+07:00`.

Lưu trữ ngày hẹn tốt thường phân biệt:
- **Moment đã chốt**: `Instant`.
- **Giờ địa phương người dùng chọn**: `LocalDateTime`.
- **Vùng mang quy tắc**: `ZoneId`.
- **Offset đã chọn ở overlap**: `ZoneOffset` hoặc `ZonedDateTime` được resolve.

Tùy sản phẩm, có thể không cần lưu tất cả bốn trường; nhưng khi cần tái dựng chính xác ý định đặt lịch, đừng vứt thông tin vùng hoặc lựa chọn overlap.

## 22. Dữ liệu múi giờ có thể thay đổi: quản lý TZDB và reproducibility

`ZoneRules` được cung cấp bởi `ZoneRulesProvider` của runtime. Dữ liệu ngày giờ thực tế có thể được cập nhật khi:
- Nhà chức trách thay đổi DST, giờ chuẩn hoặc ngày áp dụng.
- Bản phát hành JDK/TZDB bổ sung hoặc sửa lịch sử múi giờ.
- Ứng dụng dùng một rules provider khác, tùy cấu hình và môi trường.

Vì vậy:
- **Không hardcode lịch DST của năm hiện tại** rồi tái sử dụng cho mọi năm. Hãy hỏi `ZoneRules` của **ngày/Instant thực sự**.
- **Không dùng offset ở thời điểm hiện tại** để quy đổi một `LocalDateTime` nhiều tháng trước/sau.
- Đối với **lịch tương lai**, chính sách vùng có thể thay đổi, cần thiết kế cách điều chỉnh và thông báo cho người dùng.
- Đối với **sự kiện đã xảy ra**, giữ `Instant` đã chốt làm mốc timeline để không làm thay đổi lịch sử giao dịch khi quy tắc region được cập nhật.
- Trong test dùng các mốc có quy tắc đã kiểm tra; ghi rõ dữ liệu TZDB nếu test phụ thuộc chi tiết lịch sử. Tránh giả định quy tắc vùng luôn giống nhau trên mọi máy có phiên bản JDK khác.
- `ZoneId.getRules()` có thể dùng rules provider động; cache lâu dài phải cân nhắc chính sách cập nhật. Đừng trộn các bản rules không đồng nhất trong cùng một phép quyết định mà không có chiến lược.

Đừng suy ra “zone không có DST hôm nay” là “không bao giờ có transition”; `isFixedOffset` và các lookup lịch sử có nghĩa khác với `isDaylightSavings(Instant.now())`.

## 23. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai? | Cách làm tốt hơn |
| --- | --- | --- |
| `local.toInstant(rules.getOffset(local))` trong mọi tình huống | Offset trả về có thể chỉ là “best” khi gap/overlap | `getValidOffsets` + policy |
| Coi `getValidOffsets(local).isEmpty()` là lỗi của `LocalDateTime.of` | LocalDateTime hợp lệ về lịch nhưng có thể rơi DST gap | Phân biệt local validity và zone validity |
| Thấy `getOffset(local) == -05:00` và kết luận giờ gap hợp lệ | Gap có **0 offset hợp lệ** | `isValidOffset` hoặc `getValidOffsets` |
| Xử lý overlap bằng cách tự chọn offset mới nhất mà không lưu | Có hai Instant thật | Chọn tường minh; lưu lựa chọn |
| Dùng `getTransition(local)` mà không kiểm tra null | Normal case trả null | Kiểm tra gap/overlap hoặc null |
| Dùng `nextTransition(...).getInstant()` mà không kiểm tra | Fixed zone/cạnh thời gian có thể không còn transition | Kiểm tra null |
| Cho rằng `getTransitions()` là toàn bộ tương lai | Future recurrence có thể ở `getTransitionRules()` | Dùng lookup `nextTransition`/rules |
| Tự dựng lịch chuyển DST bằng ngày Chủ nhật cố định | Quy tắc lịch sử/vùng thay đổi | `ZoneRulesProvider`/TZDB |
| Giả định transition luôn dài 60 phút | Có những thay đổi không phải 1 giờ | `getDuration()` |
| Giả định mọi zone có DST | Nhiều vùng có fixed offset/không DST | `isFixedOffset` và rule queries |
| Nhầm `getStandardOffset` với offset áp dụng mùa hè | Standard và actual có thể khác | `getOffset(Instant)` và `getDaylightSavings` |
| Nhầm `+07:00` với `Asia/Ho_Chi_Minh` | Offset thiếu region rules | Giữ ZoneId khi cần lịch sử/lịch tương lai |
| Dùng `withZoneSameLocal` để giữ moment | Nó có thể đổi Instant | `withZoneSameInstant` |
| Dùng `plusHours(24)` để biểu diễn ngày lịch kế tiếp | Qua DST giờ đồng hồ có thể khác | `plusDays(1)` và policy calendar |
| Dùng `plusDays(1)` cho timeout 24 giờ | Qua DST elapsed time có thể là 23/25 giờ | `Instant` + `Duration` |
| Bắt mọi `DateTimeException` rồi âm thầm dời giờ | Che input mơ hồ/không tồn tại | Trả trạng thái validation rõ |
| Lưu mỗi `LocalDateTime` cho event timestamp | Không có zone/offset để khôi phục Instant | Lưu `Instant` hoặc offset/zone đã resolve |
| Suy luận ngày chuyển đổi từ offset của `now()` | Offset hiện tại không nói offset năm khác | Tra theo ngày/Instant thực tế |

**Thread-safety** của `ZoneRules`/`ZoneOffsetTransition` không tự giải quyết việc **chọn chính sách**. Nhiều thread đọc cùng rule set an toàn, nhưng quyết định khi gap/overlap vẫn là trách nhiệm nghiệp vụ.

## 24. Checklist xây lịch hẹn theo zone

Trước khi triển khai tính năng lịch hoặc nhắc việc có zone:

1. **Xác định dữ liệu đầu vào**: là `Instant` đã biết, hay `LocalDateTime` + `ZoneId` mà người dùng chọn?
2. **Chuẩn hóa ID vùng** bằng `ZoneId.of(id)`; quản lý lỗi `DateTimeException`/`ZoneRulesException` nếu ID hoặc rules không khả dụng.
3. **Không thay region bằng offset** trừ khi hợp đồng thật sự chỉ cần offset cố định.
4. **Tra `getValidOffsets(local)`** khi nhận giờ địa phương cần ánh xạ sang timeline.
5. **Xác định policy gap**: từ chối, dời tiến hoặc yêu cầu chọn giờ khác; không âm thầm đổi ý định.
6. **Xác định policy overlap**: chọn earlier/later, giữ offset đã biết hoặc yêu cầu người dùng chọn.
7. **Dùng `ZonedDateTime.ofStrict`** khi cần xác nhận kết hợp local+offset+zone hợp lệ, hoặc dùng cách tạo khác với chính sách được ghi rõ.
8. **Lưu Instant đã chốt**, và giữ zone/local/offset khi cần tái hiện cách sự kiện được đặt.
9. **Tách lịch tái diễn khỏi event đã chốt**: quy tắc “09:00 địa phương mỗi ngày” không giống chuỗi instant cách nhau 24 giờ.
10. **Kiểm tra các mốc chuyển đổi** bằng `nextTransition`, `previousTransition`; chú ý có thể null.
11. **Test cả normal/gap/overlap** và offset cụ thể, không chỉ kiểm tra một ngày bất kỳ.
12. **Quan sát TZDB/runtime version** trong môi trường production; có chiến lược cập nhật khi luật địa phương thay đổi.

Bộ kiểm thử tối thiểu có thể sử dụng cùng ba local date-time New York 2024 được trình bày trong bài. Kiểm tra kết quả `getValidOffsets`, `ofStrict`, hai Instant của overlap, và sự khác nhau của `plusDays/plusHours`.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** `ZoneRules` có nhiệm vụ gì?  
**Đáp án:** Cung cấp quy tắc offset của `ZoneId` theo thời gian, kể cả những lần chuyển đổi, giúp đổi từ Instant hoặc xử lý LocalDateTime theo zone.

**Câu 2.** `getOffset(Instant)` và `getOffset(LocalDateTime)` khác nhau thế nào?  
**Đáp án:** Instant đã xác định moment nên offset duy nhất. LocalDateTime có thể gap/overlap, method chỉ trả best offset, chưa chắc hợp lệ/duy nhất.

**Câu 3.** `getValidOffsets(local)` trả gì cho gap?  
**Đáp án:** Danh sách rỗng. Không có offset hợp lệ cho giờ địa phương ấy trong zone đó.

**Câu 4.** `getValidOffsets(local)` trả gì trong overlap New York 03/11/2024 lúc 01:30?  
**Đáp án:** `[-04:00, -05:00]`, hai offset tương ứng hai Instant khác nhau.

**Câu 5.** `rules.getTransition(local)` có trả một transition trong ngày giờ bình thường không?  
**Đáp án:** Không; trả `null` nếu local time không nằm trong gap/overlap.

**Câu 6.** Trong gap New York 10/03/2024 02:30, `rules.getOffset(local)` trả `-05:00`; offset ấy có hợp lệ cho 02:30 không?  
**Đáp án:** Không. `rules.isValidOffset(local, -05:00)` là false, `getValidOffsets` rỗng.

**Câu 7.** `ZoneOffsetTransition.isGap()` và `getDuration()` cho đổi `-05:00 → -04:00`?  
**Đáp án:** `isGap` true, `getDuration` = `PT1H`, thời gian địa phương bị bỏ qua một giờ.

**Câu 8.** `getDuration()` của overlap `-04:00 → -05:00` là bao nhiêu?  
**Đáp án:** `PT-1H`; giá trị âm thể hiện đồng hồ lùi một giờ.

**Câu 9.** `2024-11-03T01:30-04:00` và `2024-11-03T01:30-05:00` có cùng Instant không?  
**Đáp án:** Không; lần lượt là `05:30Z` và `06:30Z`, cách nhau 60 phút.

**Câu 10.** API nào dùng khi phải **từ chối** offset không hợp lệ cho một LocalDateTime tại một zone?  
**Đáp án:** Kiểm tra `getValidOffsets`/`isValidOffset` và dùng `ZonedDateTime.ofStrict(local, offset, zone)`. Nó ném `DateTimeException` nếu offset sai.

**Câu 11.** Tại sao `getTransitions()` không nhất thiết là danh sách mọi lần đổi DST tương lai?  
**Đáp án:** Một phần tương lai có thể được mô hình bằng `getTransitionRules()` và sinh theo năm.

**Câu 12.** Múi giờ cố định có thể có `nextTransition` không?  
**Đáp án:** Với rule set fixed offset, không có lần chuyển tiếp và `nextTransition` có thể trả `null`.

**Câu 13.** Vì sao lịch “12:00 ngày mai ở New York” khác timeout sau 24 giờ?  
**Đáp án:** Qua DST, ngày lịch có thể trôi qua 23/25 giờ. `plusDays(1)` giữ local clock; `plusHours(24)` giữ elapsed 24 giờ.

**Câu 14.** Vì sao lưu duy nhất `+07:00` không thể thay cho `Asia/Ho_Chi_Minh`?  
**Đáp án:** Offset không chứa tên vùng hoặc quy tắc lịch sử/tương lai. Khi cần lịch theo vùng, giữ `ZoneId`.

**Câu 15.** Năm sau các mốc chuyển DST có bắt buộc giống năm 2024 không?  
**Đáp án:** Không. Quy tắc thuộc TZDB/nhà cung cấp và có thể được cập nhật theo luật, vì vậy không hardcode cho tương lai.

## 26. Kết luận

- **`ZoneRules`** biết offset áp dụng tại một `Instant` và cách xử lý `LocalDateTime` theo zone.
- **`getValidOffsets(LocalDateTime)`** là cửa ngõ nhận diện **normal / gap / overlap**; `getOffset(local)` chỉ trả offset tốt nhất và **không đủ** để xác thực lịch hẹn.
- **`ZoneOffsetTransition`** mô tả mốc thay đổi offset, hai giờ địa phương tại ranh giới, offset trước/sau, duration dương của gap và âm của overlap.
- **`ZonedDateTime.ofStrict`** dùng khi yêu cầu offset hợp lệ tường minh; `atZone` có chính sách tự điều chỉnh gap/overlap mà ứng dụng phải hiểu.
- **`nextTransition`/`previousTransition`** tìm lần chuyển theo Instant; `getTransitions` và `getTransitionRules` mô hình các transition cụ thể và quy tắc tái diễn.
- **Không đồng nhất region ZoneId với fixed ZoneOffset, không đồng nhất ngày lịch với 24 giờ elapsed, không hardcode DST** khi API có thể tra rule theo ngày/Instant.
- Các API này **có từ Java 8 và vẫn còn phù hợp**; luôn xét khả năng thay đổi dữ liệu TZDB khi quản lý lịch tương lai.

### Tài liệu chính thức còn áp dụng (Oracle Java SE 26)

- [`java.time.zone.ZoneRules` — valid offsets, transitions, daylight savings](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html)
- [`java.time.zone.ZoneOffsetTransition` — gap, overlap, before/after/duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html)
- [`java.time.zone.ZoneOffsetTransitionRule` — quy tắc tạo transition theo năm](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransitionRule.html)
- [`java.time.zone.ZoneRulesProvider` — nguồn dữ liệu vùng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRulesProvider.html)
- [`java.time.ZoneId`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html), [`ZoneOffset`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html)
- [`java.time.ZonedDateTime` — xử lý local timeline, `ofStrict` và earlier/later overlap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [`java.time.Duration`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html) — elapsed time và toán tử Duration.
