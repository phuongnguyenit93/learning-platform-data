# ZoneId, ZonedDateTime, OffsetDateTime và thay đổi múi giờ

Trong Java 27, thời gian không chỉ là một con số giờ–phút hay một chuỗi kiểu `2026-07-15 09:00`. Để xử lý lịch họp, thanh toán, log hoặc sự kiện ở nhiều quốc gia, cần phân biệt ba câu hỏi:

1. **Thời điểm thực tế nào?** Ví dụ, một sự kiện xảy ra tại `2026-07-15T12:00:00Z` trên dòng thời gian chung.
2. **Đồng hồ địa phương hiển thị mấy giờ?** Cùng thời điểm đó là 19:00 tại Thành phố Hồ Chí Minh và 08:00 tại New York theo các quy tắc múi giờ áp dụng cho ngày này.
3. **Quy tắc nào quyết định độ lệch UTC?** Một khu vực có thể thay đổi offset do daylight saving time (DST), điều chỉnh pháp luật hoặc cập nhật cơ sở dữ liệu múi giờ.

Nếu chỉ lưu `09:00` hoặc một offset cố định `-05:00` cho mọi lịch hẹn tại New York, ứng dụng có thể tính sai thời điểm khi quy tắc chuyển đổi thay đổi. Bộ API `java.time` giải quyết vấn đề bằng những kiểu dữ liệu có vai trò khác nhau, nổi bật là **`ZoneId`, `ZonedDateTime` và `OffsetDateTime`**.

Bài học thuộc chương **Thời gian và số học chính xác** trong module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung sử dụng các API Java SE 27 đang được hỗ trợ, tập trung vào tính đúng đắn khi đổi múi giờ, xử lý khoảng thời gian không tồn tại/trùng lặp, và chính sách lưu trữ lịch dài hạn. Không dùng cơ chế ngày giờ cũ làm giải pháp mặc định cho code mới.

## 1. Bản đồ khái niệm: ngày giờ địa phương, offset và instant

Trước khi sử dụng từng class, hãy phân biệt các kiểu quan trọng:

| Kiểu | Mang thông tin gì? | Xác định duy nhất một instant? | Dùng khi nào? |
| --- | --- | --- | --- |
| `LocalDate` | Ngày trong lịch, không có giờ hoặc vùng | Không | Ngày sinh, ngày nghỉ, ngày trên biểu mẫu |
| `LocalTime` | Giờ trong ngày, không có ngày hoặc vùng | Không | Giờ mở cửa 09:00 hằng ngày |
| `LocalDateTime` | Ngày và giờ theo đồng hồ địa phương | **Không** | Người dùng chọn ngày–giờ trước khi áp múi giờ |
| `ZoneOffset` | Độ lệch cố định so với UTC, như `+07:00` | Tự nó không | Chuyển đổi theo một offset đã biết |
| `ZoneId` | ID nhận diện tập quy tắc múi giờ, như `Asia/Ho_Chi_Minh` | Tự nó không | Lịch theo vùng địa lý có thể thay đổi offset |
| `Instant` | Một thời điểm trên dòng thời gian UTC | **Có** | Timestamp sự kiện, log, thời điểm hết hạn |
| `OffsetDateTime` | `LocalDateTime` + `ZoneOffset` | **Có** | Trao đổi timestamp có offset, một số API/DB |
| `ZonedDateTime` | `LocalDateTime` + `ZoneId` + offset đã được phân giải | **Có** | Hiển thị và tính toán theo quy tắc khu vực |

Một cách hình dung:

```text
LocalDateTime = 2026-07-15T09:00
        |
        +--- +07:00 (ZoneOffset) ---> OffsetDateTime
        |                              2026-07-15T09:00+07:00
        |                                      |
        |                                      v
        |                                    Instant
        |                              2026-07-15T02:00:00Z
        |
        +--- Asia/Ho_Chi_Minh (ZoneId)
                     |
                     v
          Tra cứu ZoneRules cho ngày này
                     |
                     v
               ZonedDateTime
        2026-07-15T09:00+07:00[Asia/Ho_Chi_Minh]
```

**`LocalDateTime` không phải một instant.** Nó không chứa thông tin để xác định `09:00` là `09:00` ở đâu. Mỗi phép chuyển đổi từ đồng hồ địa phương sang instant phải biết ít nhất một offset hoặc một vùng với chính sách giải quyết những thời điểm nhập nhằng.

## 2. `ZoneId` và `ZoneOffset` khác nhau như thế nào?

`ZoneId` nhận diện cách tra cứu **quy tắc múi giờ**. Có hai nhóm quan trọng:

- **Region-based ID:** ví dụ `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York`. Các vùng này có lịch sử và quy tắc xác định offset cho từng instant.
- **Fixed offset:** ví dụ `Z` (UTC), `+07:00`, `-04:00`. Loại này không tự mang lịch chuyển DST hoặc thay đổi do chính sách của một vùng.

```java
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId paris = ZoneId.of("Europe/Paris");

ZoneOffset plusSeven = ZoneOffset.ofHours(7);
ZoneOffset utc = ZoneOffset.UTC;

System.out.println(vietnam.getId());  // Asia/Ho_Chi_Minh
System.out.println(plusSeven.getId()); // +07:00
System.out.println(utc.getId());       // Z
```

`ZoneOffset` là một subclass của `ZoneId` đại diện cho offset cố định. Vì vậy, một API nhận `ZoneId` cũng có thể được truyền `ZoneOffset`, nhưng **hai loại biểu diễn không tương đương về mặt ý nghĩa**.

### 2.1. Đừng thay tên vùng bằng offset hiện tại

Tại một thời điểm cụ thể:

```java
import java.time.Instant;
import java.time.ZoneId;

ZoneId ny = ZoneId.of("America/New_York");

System.out.println(
        ny.getRules().getOffset(Instant.parse("2026-01-15T12:00:00Z")));
// -05:00

System.out.println(
        ny.getRules().getOffset(Instant.parse("2026-07-15T12:00:00Z")));
// -04:00
```

Đây là kết quả theo các quy tắc TZDB cho ví dụ năm 2026. Offset của New York vào mùa đông và mùa hè **khác nhau**, nên không thể thay thế vùng `America/New_York` bằng `-05:00` khi lên lịch dài hạn.

Tương tự, `ZoneId.systemDefault()` trả vùng mặc định của **môi trường chạy**, không nhất thiết là vùng của người đang dùng ứng dụng. Server triển khai ở UTC không có nghĩa mọi khách hàng đều ở UTC. Khi xử lý lịch theo người dùng, hãy yêu cầu hoặc lưu riêng **IANA zone ID** mà họ chọn.

### 2.2. Không dựa vào mã viết tắt tùy tiện

Những chữ viết tắt như `EST`, `CST`, `IST` có thể gây mơ hồ giữa các quốc gia hoặc chỉ phản ánh một offset mùa vụ. Với API và dữ liệu mới, ưu tiên vùng định danh đầy đủ, ví dụ `America/New_York`, hoặc offset `-05:00` khi chủ đích chỉ cần offset cố định. Không dùng mapping viết tắt cũ làm chuẩn giao tiếp liên hệ thống.

## 3. Cùng một instant, nhiều giờ hiển thị

`Instant` đại diện cho thời điểm độc lập với vùng. Khi **hiển thị** nó tại những khu vực khác nhau, ta nhận những `ZonedDateTime` khác nhau nhưng `toInstant()` vẫn bằng nhau.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant event = Instant.parse("2026-07-15T12:00:00Z");

ZonedDateTime inVietnam =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime inNewYork =
        event.atZone(ZoneId.of("America/New_York"));

System.out.println(inVietnam);
// 2026-07-15T19:00+07:00[Asia/Ho_Chi_Minh]

System.out.println(inNewYork);
// 2026-07-15T08:00-04:00[America/New_York]

System.out.println(inVietnam.toInstant().equals(inNewYork.toInstant()));
// true
```

Đây là phép chuyển đổi **không thay đổi instant**, chỉ thay cách biểu diễn theo quy tắc của mỗi vùng.

Mẫu áp dụng cho timestamp thực tế:

1. Hệ thống ghi nhận hoặc nhận về một `Instant`.
2. Người dùng có `ZoneId` đã chọn.
3. Gọi `instant.atZone(userZone)` khi cần hiển thị.
4. Không sửa timestamp gốc chỉ vì người dùng đổi vị trí hoặc đổi vùng hiển thị.

## 4. `ZonedDateTime`: giờ địa phương kèm quy tắc khu vực

`ZonedDateTime` lưu thông tin tương đương với **`LocalDateTime` + `ZoneId` + offset đã phân giải**. Nó xác định được một instant, đồng thời giữ ID vùng để tính toán theo lịch địa phương trong những lần cộng/trừ tiếp theo.

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime meeting =
        ZonedDateTime.of(2026, 7, 15, 9, 0, 0, 0, zone);

System.out.println(meeting.toLocalDateTime());
// 2026-07-15T09:00
System.out.println(meeting.getZone());
// America/New_York
System.out.println(meeting.getOffset());
// -04:00
System.out.println(meeting.toInstant());
// 2026-07-15T13:00:00Z
```

**Offset** trong `ZonedDateTime` không phải tùy ý: nó được xác định bằng `ZoneRules` của vùng và thông tin thời gian. Trong những thời điểm local bị trùng lặp, offset đã phân giải quyết định instance đại diện cho lần xảy ra nào.

Các đối tượng `java.time` trong ví dụ là **immutable**: `plusDays(...)` hay `withZoneSameInstant(...)` trả đối tượng mới, không đổi đối tượng gốc. Chúng là value-based classes; không đồng bộ hóa bằng monitor của instance ngày giờ hoặc dựa vào danh tính object để thiết kế nghiệp vụ.

## 5. `OffsetDateTime`: ngày giờ gắn một offset cố định

`OffsetDateTime` lưu ngày–giờ và **`ZoneOffset`**, không lưu ID vùng kiểu `America/New_York`. Nó cũng xác định duy nhất một instant:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime recorded =
        OffsetDateTime.parse("2026-07-15T09:00:00-04:00");

System.out.println(recorded.toInstant());
// 2026-07-15T13:00:00Z
System.out.println(recorded.getOffset());
// -04:00
```

`OffsetDateTime` rất hữu ích khi một hệ thống hoặc giao thức đã cung cấp **ngày–giờ kèm offset** và mục tiêu là trao đổi một timestamp không mơ hồ. Nhưng nó **không có thông tin** để biết vùng gốc sẽ đổi sang offset nào vào mùa tiếp theo.

Ví dụ, hai giá trị này có thể biểu diễn cùng instant:

```java
OffsetDateTime a = OffsetDateTime.parse("2026-07-15T09:00-04:00");
OffsetDateTime b = OffsetDateTime.parse("2026-07-15T20:00+07:00");

System.out.println(a.toInstant().equals(b.toInstant())); // true
System.out.println(a.equals(b));                         // false
```

`equals` của `OffsetDateTime` xét cả local date-time và offset, không chỉ instant. Để so cùng **thời điểm thực**, hãy so sánh `toInstant()` hoặc dùng `isEqual(...)` khi phù hợp.

### 5.1. Khi nào dùng loại nào?

| Nhu cầu | Nên ưu tiên |
| --- | --- |
| Một mốc thời gian tuyệt đối, không phụ thuộc nơi hiển thị | `Instant` |
| Timestamp từ API có offset, không cần chính sách vùng sau đó | `OffsetDateTime` |
| Giờ họp theo thành phố hoặc phép cộng theo lịch của một khu vực | `ZonedDateTime` + `ZoneId` |
| Giờ địa phương do người dùng nhập, chưa chọn vùng | `LocalDateTime`, sau đó giải quyết vùng |
| Công việc định kỳ 09:00 tại một vùng kể cả khi DST đổi | Quy tắc lịch địa phương + `ZoneId` + chính sách gap/overlap |

Không nên ép một kiểu dùng cho mọi mục đích. Tính đúng đắn đến từ việc giữ thông tin mà nghiệp vụ **thật sự cần**.

## 6. Đổi múi giờ: giữ instant hay giữ giờ trên đồng hồ?

Trong ứng dụng quốc tế, cụm từ “đổi múi giờ” có hai nghĩa khác nhau:

**A. Giữ nguyên thời điểm thực:** cuộc họp đã lên lịch ở New York; người tại Việt Nam chỉ muốn xem cuộc họp diễn ra lúc mấy giờ theo đồng hồ của mình.

**B. Giữ nguyên giờ địa phương:** chuyển lịch trình từ “09:00 tại New York” thành “09:00 tại Việt Nam”, chấp nhận rằng thời điểm thực tế đã thay đổi.

Hai method của `ZonedDateTime` phản ánh rõ sự khác nhau đó.

### 6.1. `withZoneSameInstant`: không thay đổi instant

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime inNewYork = ZonedDateTime.of(
        2026, 7, 15, 9, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime inVietnam = inNewYork.withZoneSameInstant(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inNewYork);
// 2026-07-15T09:00-04:00[America/New_York]
System.out.println(inVietnam);
// 2026-07-15T20:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(inNewYork.toInstant().equals(inVietnam.toInstant()));
// true
```

Ứng dụng lịch, log, chuyến bay và giao diện nhiều múi giờ thường cần **`withZoneSameInstant`**. Đây là cách hiển thị **cùng một sự kiện**, không phải dời lịch.

### 6.2. `withZoneSameLocal`: cố giữ cùng giờ địa phương

```java
ZonedDateTime inVietnamAtNine = inNewYork.withZoneSameLocal(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inVietnamAtNine);
// 2026-07-15T09:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(inNewYork.toInstant()
        .equals(inVietnamAtNine.toInstant()));
// false
```

`withZoneSameLocal` cố giữ nguyên `LocalDateTime` và tìm offset hợp lệ tại vùng mới. Nếu local time **không hợp lệ** ở vùng mới do DST gap, Java có thể điều chỉnh giờ theo quy tắc giải quyết gap, nên chữ “same local” không có nghĩa tuyệt đối cho mọi đầu vào.

**Cảnh báo:** Không dùng `withZoneSameLocal` cho thao tác “hiển thị lịch họp theo timezone người xem” nếu muốn giữ đúng thời điểm cuộc họp. Nó có thể âm thầm chuyển sự kiện sang instant khác.

## 7. Đổi offset trên `OffsetDateTime`: cũng có hai ngữ nghĩa

`OffsetDateTime` có cặp method tương tự, nhưng đích là `ZoneOffset` thay vì một vùng:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime original =
        OffsetDateTime.parse("2026-07-15T09:00-04:00");

OffsetDateTime sameInstant =
        original.withOffsetSameInstant(ZoneOffset.ofHours(7));
OffsetDateTime sameLocal =
        original.withOffsetSameLocal(ZoneOffset.ofHours(7));

System.out.println(sameInstant);
// 2026-07-15T20:00+07:00
System.out.println(sameLocal);
// 2026-07-15T09:00+07:00

System.out.println(original.toInstant()
        .equals(sameInstant.toInstant())); // true
System.out.println(original.toInstant()
        .equals(sameLocal.toInstant()));   // false
```

Chọn `withOffsetSameInstant` khi chuyển cách biểu diễn của một timestamp. Chỉ chọn `withOffsetSameLocal` nếu nghiệp vụ **cố ý giữ giờ trên đồng hồ và thay đổi instant**.

Muốn phục hồi ngữ nghĩa theo vùng từ một `OffsetDateTime`, phải có **`ZoneId` riêng** và lựa chọn chính sách chuyển phù hợp:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime inNewYork =
        original.atZoneSameInstant(ZoneId.of("America/New_York"));
```

`atZoneSameInstant` giữ instant, tra cứu offset hợp lệ theo vùng. Không thể suy ra chắc chắn ID vùng ban đầu chỉ từ `-04:00` vì nhiều khu vực có thể cùng dùng offset đó tại một thời điểm.

## 8. Vì sao thay đổi DST gây khó: bình thường, gap và overlap

**DST** (*daylight saving time*, giờ mùa hè) thường là việc đẩy đồng hồ lên vào một giai đoạn trong năm và lùi đồng hồ lại khi kết thúc giai đoạn ấy. Nhưng không phải vùng nào cũng có DST, và những thay đổi offset trong thực tế còn có thể do quyết định chính sách không theo mùa.

Với một `LocalDateTime` và một `ZoneId`, `ZoneRules` có ba khả năng:

| Trạng thái local date-time | Số offset hợp lệ | Ý nghĩa |
| --- | --- | --- |
| **Normal** | 1 | Giờ địa phương tương ứng đúng một instant |
| **Gap** | 0 | Đồng hồ nhảy tới; giờ địa phương đó không tồn tại |
| **Overlap** | 2 | Đồng hồ lùi lại; giờ địa phương xảy ra hai lần |

Ví dụ minh họa theo quy tắc `America/New_York` áp dụng cho các ngày chuyển DST năm 2026:

```text
Ngày 08-03-2026 — đồng hồ nhảy tới (gap)

01:59:59 -05:00
       |
       v
03:00:00 -04:00

02:30 không xảy ra ở New York vào ngày này.

Ngày 01-11-2026 — đồng hồ lùi lại (overlap)

01:30 -04:00  (lần thứ nhất)
       |
       v
01:00 -05:00  (quay lại)
       |
       v
01:30 -05:00  (lần thứ hai)
```

Cùng chuỗi `2026-11-01T01:30` tại New York có thể mô tả **hai instant khác nhau**. Đây là lý do việc ghép tùy tiện `LocalDateTime` với zone mà không có chính sách kinh doanh có thể làm lịch hẹn không rõ nghĩa.

### 8.1. Gap: `atZone` điều chỉnh thời gian không tồn tại

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime nonexistent =
        LocalDateTime.of(2026, 3, 8, 2, 30);

ZonedDateTime resolved = nonexistent.atZone(ny);

System.out.println(resolved);
// 2026-03-08T03:30-04:00[America/New_York]
```

Khi rơi vào gap, `LocalDateTime.atZone` (và `ZonedDateTime.of` dùng lịch địa phương) thường **đẩy thời gian tới bằng độ dài của gap**. Trong ví dụ, giờ 02:30 không tồn tại nên được giải quyết thành 03:30.

Đây là chính sách mặc định của API, **không phải** quy tắc bắt buộc của mọi ứng dụng. Với đặt phòng/phẫu thuật/đặt lịch có yêu cầu giờ chính xác, có thể cần **từ chối** 02:30 và yêu cầu người dùng chọn lại.

### 8.2. Overlap: `atZone` chọn offset sớm hơn khi không có sở thích trước đó

```java
LocalDateTime ambiguous =
        LocalDateTime.of(2026, 11, 1, 1, 30);

ZonedDateTime earlier = ambiguous.atZone(ny);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(earlier);
// 2026-11-01T01:30-04:00[America/New_York]

System.out.println(later);
// 2026-11-01T01:30-05:00[America/New_York]

System.out.println(earlier.toInstant());
// 2026-11-01T05:30:00Z

System.out.println(later.toInstant());
// 2026-11-01T06:30:00Z
```

Khi tạo mới từ `LocalDateTime` và `ZoneId`, Java chọn **earlier offset** trong overlap nếu không có offset ưu tiên. `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` cho phép chọn hai nhánh của sự kiện đồng hồ lùi. Hai giá trị có cùng giờ địa phương nhưng khác instant đúng **60 phút** trong ví dụ này.

Ở những trường hợp thay đổi `ZonedDateTime` đã có sẵn, Java có thể ưu tiên **giữ offset trước đó nếu vẫn hợp lệ**, thay vì luôn chọn nhánh sớm. Vì thế không nên mô tả mọi thao tác dựng/đổi ngày giờ là “luôn chọn earlier offset”.

## 9. Kiểm tra gap/overlap bằng `ZoneRules` thay vì đoán

Để ứng dụng chủ động xử lý giờ nhập từ người dùng, có thể truy vấn các offset hợp lệ:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId ny = ZoneId.of("America/New_York");
ZoneRules rules = ny.getRules();

LocalDateTime normal = LocalDateTime.of(2026, 2, 15, 10, 0);
LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);

List<ZoneOffset> one = rules.getValidOffsets(normal);
List<ZoneOffset> zero = rules.getValidOffsets(gap);
List<ZoneOffset> two = rules.getValidOffsets(overlap);

System.out.println(one);  // [-05:00]
System.out.println(zero); // []
System.out.println(two);  // [-04:00, -05:00]
```

`ZoneRules.getValidOffsets(local)` trả danh sách có 0, 1 hoặc 2 phần tử trong các tình huống thông thường được mô tả ở trên. `ZoneRules.getTransition(local)` cho thông tin chuyển đổi tại gap hoặc overlap, bao gồm offset trước/sau và thời lượng thay đổi khi có transition.

**Không dùng `rules.getOffset(local)` để chứng minh giờ đó hợp lệ duy nhất.** Với `LocalDateTime` nằm trong gap hoặc overlap, method có thể cung cấp offset mặc định theo quy tắc, không phải xác nhận lịch hẹn chỉ có một instant.

### 9.1. Chính sách nghiêm ngặt: từ chối gap và overlap chưa được chọn

Đoạn sau là một ví dụ API cho lịch hẹn yêu cầu **người gọi giải quyết sự mơ hồ**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

static ZonedDateTime resolveStrict(
        LocalDateTime local,
        ZoneId zone,
        ZoneOffset selectedOffset) {

    List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

    if (valid.isEmpty()) {
        throw new IllegalArgumentException(
                "Local time is in a gap: " + local);
    }

    if (valid.size() > 1 && selectedOffset == null) {
        throw new IllegalArgumentException(
                "Ambiguous local time; select an offset");
    }

    ZoneOffset offset =
            selectedOffset != null ? selectedOffset : valid.get(0);

    return ZonedDateTime.ofStrict(local, offset, zone);
}
```

Sử dụng:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);

ZonedDateTime chosen = resolveStrict(
        overlap, ny, ZoneOffset.ofHours(-5));
System.out.println(chosen.toInstant());
// 2026-11-01T06:30:00Z

// resolveStrict(LocalDateTime.of(2026, 3, 8, 2, 30), ny, null);
// Ném IllegalArgumentException vì gap.

// resolveStrict(overlap, ny, null);
// Ném IllegalArgumentException vì overlap chưa chọn nhánh.
```

`ZonedDateTime.ofStrict(local, offset, zone)` kiểm tra offset đã chọn có thực sự hợp lệ tại giờ địa phương của vùng đó không; khi không hợp lệ, method ném `DateTimeException`. Không nên bọc tất cả giá trị `selectedOffset` không khớp thành một instant khác mà người dùng không nhận ra.

### 9.2. Khi nào `ofLocal` phù hợp?

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` cho phép ưu tiên một offset hợp lệ nếu đang ở overlap. Nếu offset ưu tiên không hợp lệ, method có thể chọn offset sớm hơn; với gap thì đẩy thời gian tiến theo độ dài gap.

Vì vậy:

- `ofLocal` thích hợp khi chấp nhận chính sách phân giải mềm dẻo.
- `ofStrict` thích hợp khi cần **xác minh chính xác** local time + selected offset + zone.
- Nếu API không được tự sửa giờ nhập của người dùng, hãy kiểm tra `getValidOffsets` trước khi tạo `ZonedDateTime`.

## 10. Số học ngày giờ: cộng **một ngày** khác cộng **24 giờ**

Một điểm dễ gây lỗi trong lịch ở vùng có DST:

- `ZonedDateTime.plusDays(1)` cộng theo **lịch địa phương**. Nó thường giữ cùng giờ hiển thị vào ngày sau, rồi tính lại offset từ zone rules.
- `ZonedDateTime.plusHours(24)` cộng đúng **24 giờ trên dòng thời gian instant**. Sau DST, giờ địa phương có thể khác.

Ví dụ ngày bắt đầu chuyển sang DST tại New York:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2026, 3, 7, 9, 0, 0, 0, ny);

ZonedDateTime byCalendarDay = start.plusDays(1);
ZonedDateTime byExactHours = start.plusHours(24);

System.out.println(start);
// 2026-03-07T09:00-05:00[America/New_York]

System.out.println(byCalendarDay);
// 2026-03-08T09:00-04:00[America/New_York]

System.out.println(byExactHours);
// 2026-03-08T10:00-04:00[America/New_York]

System.out.println(Duration.between(
        start.toInstant(), byCalendarDay.toInstant()).toHours());
// 23

System.out.println(Duration.between(
        start.toInstant(), byExactHours.toInstant()).toHours());
// 24
```

`plusDays` giữ 09:00 đồng hồ địa phương, nhưng hai lần 09:00 chỉ cách nhau **23 giờ thực** do đồng hồ nhảy lên. `plusHours(24)` giữ độ dài elapsed time nên tại ngày sau hiển thị 10:00.

Ngày kết thúc DST có thể ngược lại: một ngày lịch địa phương kéo dài **25 giờ** trong vùng thực hiện chuyển đổi lùi một giờ.

### 10.1. Chọn `Period` hay `Duration`?

**`Period`** mang số năm, tháng, ngày theo lịch. **`Duration`** mang số giây và nano trên dòng thời gian:

```java
import java.time.Duration;
import java.time.Period;

ZonedDateTime nextCalendarDay = start.plus(Period.ofDays(1));
ZonedDateTime twentyFourHours = start.plus(Duration.ofHours(24));

System.out.println(nextCalendarDay.equals(byCalendarDay)); // true
System.out.println(twentyFourHours.equals(byExactHours));  // true
```

Nên chọn theo nghĩa của yêu cầu:

- “Mỗi ngày lúc 09:00 tại New York”: tính theo **lịch địa phương**, dùng `ZoneId`.
- “Sau đúng 24 giờ kể từ khi bấm nút”: tính theo **Duration/Instant**.
- “Ngày mai lúc 02:30” trong vùng có chuyển DST: cần chính sách gap/overlap; chỉ cộng ngày chưa đủ nếu nghiệp vụ không chấp nhận tự dịch giờ.

Với `OffsetDateTime`, một offset đã cố định nên `plusDays(1)` không tự đổi sang offset DST của vùng nào đó. Đó chính là lý do không dùng mỗi `OffsetDateTime` để mô hình hóa lịch hằng ngày của một thành phố.

## 11. Thay đổi quy tắc múi giờ không chỉ là DST

Một `ZoneId` đại diện cho **ID ổn định dùng tra cứu quy tắc**, còn bản thân quy tắc có thể thay đổi theo thời gian. Cơ quan quản lý có thể đổi offset pháp định, hủy hoặc thiết lập DST, thay ngày chuyển đổi, thậm chí thay đổi quy tắc với thông báo rất gần thời điểm áp dụng.

Java sử dụng cơ chế `ZoneRules` và `ZoneRulesProvider`. Provider mặc định trong JDK phục vụ dữ liệu từ **IANA Time Zone Database (TZDB)**. Khi môi trường JDK hoặc cơ sở dữ liệu múi giờ được cập nhật, kết quả tính các sự kiện **tương lai** hoặc lịch sử có thể khác so với trước đó tùy loại thay đổi.

Ví dụ về hai câu hỏi khác nhau:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId zone = ZoneId.of("America/New_York");

// Offset thực sự áp dụng cho một instant đã biết:
ZoneOffset atInstant = zone.getRules().getOffset(
        Instant.parse("2026-07-15T12:00:00Z"));

// Không suy ra offset của tháng 12 từ giá trị tháng 7.
System.out.println(atInstant); // -04:00
```

Thay vì hardcode `-04:00` hoặc `-05:00` cho New York, dùng `ZoneId` và tra quy tắc cho **thời gian cần xét**.

### 11.1. Phụ thuộc phiên bản dữ liệu TZDB

Hai môi trường chạy cùng code Java 27 nhưng có **bản cập nhật tzdb khác nhau** có thể giải quyết một lịch hẹn tương lai khác nhau. Điều này không phải do class `ZonedDateTime` thiếu chính xác, mà do các quy tắc dân sự tương lai có thể thay đổi.

Với hệ thống lịch cần tái lập kết quả, có thể giám sát phiên bản tzdb và kiểm thử các mốc chuyển đổi quan trọng sau khi cập nhật JDK. `ZoneRulesProvider.getVersions(zoneId)` cho phép hỏi các phiên bản rules mà provider cung cấp; **không phải provider nào cũng giữ đầy đủ lịch sử các phiên bản**.

Không kỳ vọng một ID như `America/New_York` tự mang một phiên bản tzdb cố định suốt vòng đời ứng dụng.

### 11.2. `ZoneRulesException` và dữ liệu vùng không sẵn có

`ZoneId.of(...)` có thể thất bại với zone ID không hợp lệ hoặc không được hỗ trợ trong môi trường. Dữ liệu zone đã được lưu/trao đổi cũng có thể không có rules tương ứng tại một runtime khác, khiến `getRules()` ném `ZoneRulesException`.

Với input từ bên ngoài:

- Xác thực zone ID và sự tồn tại của rules phù hợp.
- Không tự lặng lẽ chuyển sang `ZoneId.systemDefault()` nếu giá trị người dùng gửi sai.
- Ghi rõ phương án xử lý khi hệ thống không nhận diện được zone.

## 12. Lưu trữ: timestamp đã xác định và lịch hẹn tương lai là hai bài toán

### 12.1. Sự kiện đã xảy ra: lưu `Instant`

Một log “người dùng xác nhận lúc nào” cần một **instant đã xác định**. Lưu ở dạng UTC/instant hoặc cột timestamp có semantics tương đương của cơ sở dữ liệu giúp so sánh và sắp xếp giữa khu vực. Khi hiển thị, đổi sang `ZoneId` của người xem.

```java
Instant submittedAt = Instant.now();

ZonedDateTime displayTime =
        submittedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Mã ví dụ dùng `Instant.now()` để minh họa runtime thật; trong kiểm thử, nên inject `Clock` thay vì phụ thuộc thời gian hiện tại.

### 12.2. Lịch hẹn được định nghĩa theo vùng: lưu mục đích người dùng

Giả sử khách hàng đặt “ngày 01-11-2026 lúc 01:30 tại New York”. Nếu chỉ lưu `LocalDateTime` sẽ không phân biệt được hai lần 01:30. Nếu chỉ lưu một `Instant`, ứng dụng biết cuộc hẹn xảy ra lúc nào nhưng **mất bối cảnh** vùng và giờ địa phương mà người dùng chọn.

Với lịch hẹn quan trọng, cân nhắc lưu:

- `localDateTime` theo ý định người dùng.
- `zoneId` dạng vùng IANA, ví dụ `America/New_York`.
- Offset/nhánh overlap đã chọn, nếu có.
- Instant đã phân giải để thực thi đúng thời điểm.
- Chính sách nghiệp vụ đối với các lần tính lại khi TZDB được cập nhật.

Không có một cấu trúc lưu trữ duy nhất đúng cho mọi hệ thống. Nếu mục tiêu là **giữ nguyên instant đã cam kết**, instant đã lưu là dữ liệu trọng yếu. Nếu mục tiêu là **giữ đúng giờ địa phương theo luật hiện hành của vùng cho một sự kiện tương lai**, hệ thống có thể cần **tính lại** instant và thông báo người dùng khi quy tắc thay đổi.

### 12.3. Lịch lặp hằng tuần: không cộng 7 × 24 giờ bất biến

Với lịch “thứ Hai 09:00 ở New York”:

- Lưu quy tắc lặp (thứ trong tuần, giờ địa phương) và `ZoneId`.
- Mỗi lần tính phiên tiếp theo, xác định ngày địa phương rồi phân giải sang `ZonedDateTime` theo chính sách gap/overlap.
- Không chỉ cộng `Duration.ofDays(7)` trên `Instant` cho mọi lần lặp nếu cần giữ 09:00 theo đồng hồ thành phố.

`ZonedDateTime.plusWeeks(1)` thực hiện phép cộng theo lịch địa phương, nhưng **vẫn áp dụng chính sách mặc định** của Java nếu giờ rơi vào gap hoặc overlap. Nếu nghiệp vụ yêu cầu từ chối hoặc hỏi lại người dùng, cần bước kiểm tra riêng.

## 13. Format và parse: chuỗi có offset khác chuỗi có zone

`java.time.format.DateTimeFormatter` cung cấp các định dạng ISO-8601 và hỗ trợ định dạng theo locale. Hãy phân biệt thông tin được giữ lại trong chuỗi.

### 13.1. `OffsetDateTime` thường có offset, không có ID vùng

```java
import java.time.OffsetDateTime;

OffsetDateTime offsetTime =
        OffsetDateTime.parse("2026-07-15T09:00:00-04:00");

System.out.println(offsetTime);
// 2026-07-15T09:00-04:00
```

Chuỗi `2026-07-15T09:00-04:00` đủ xác định instant, nhưng không nói người dùng đến từ New York, Toronto hay khu vực nào khác có cùng offset.

### 13.2. `ZonedDateTime` giữ ID vùng trong biểu diễn ISO

```java
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

String value =
        "2026-11-01T01:30:00-05:00[America/New_York]";

ZonedDateTime meeting = ZonedDateTime.parse(value);

System.out.println(meeting.getZone());   // America/New_York
System.out.println(meeting.getOffset()); // -05:00
System.out.println(meeting.toInstant()); // 2026-11-01T06:30:00Z

String encoded =
        meeting.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
System.out.println(encoded);
// 2026-11-01T01:30-05:00[America/New_York]
```

Trong ví dụ overlap, offset trong chuỗi xác định rõ nhánh thứ hai. Tuy vậy, với dữ liệu từ bên ngoài có thể sai, **không nhầm parse thành công với xác nhận một tổ hợp local + offset + zone là hợp lệ theo chính sách của bạn**. Nếu yêu cầu bắt buộc khớp rules của vùng, xác thực bằng `ZoneRules.isValidOffset(...)` hoặc `ZonedDateTime.ofStrict(...)`.

### 13.3. Khi trao đổi qua JSON/API

Hợp đồng API nên chỉ rõ một trong những loại dữ liệu sau:

1. **Instant:** timestamp UTC như `2026-07-15T13:00:00Z`.
2. **OffsetDateTime:** timestamp như `2026-07-15T09:00:00-04:00`.
3. **Lịch theo vùng:** local date-time, IANA `zoneId` và, khi cần, offset/nhánh đã chọn. Có thể bổ sung instant đã giải quyết.

Không chỉ gửi chuỗi `07/15/2026 09:00` mà không có định dạng, zone, offset và locale rõ ràng. Đầu vào user-facing có thể có formatter riêng, nhưng dữ liệu truyền giữa các hệ thống nên dùng hợp đồng nhất quán và có thông tin thời gian đủ dùng.

## 14. So sánh thời điểm: `equals` khác so cùng một instant

Hai đối tượng `ZonedDateTime` có thể chỉ cùng instant nhưng khác vùng, dẫn đến `equals` trả `false`.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant at = Instant.parse("2026-07-15T12:00:00Z");
ZonedDateTime hcm = at.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime ny = at.atZone(ZoneId.of("America/New_York"));

System.out.println(hcm.equals(ny)); // false
System.out.println(hcm.toInstant().equals(ny.toInstant())); // true
System.out.println(hcm.isEqual(ny)); // true
```

Với `OffsetDateTime`, hai giá trị cùng instant nhưng có offset khác nhau cũng không nhất thiết `equals` nhau.

**Quy tắc thiết kế:**

- So **cùng thời điểm thực**: `toInstant().equals(...)`, `isEqual(...)` hoặc so các `Instant`.
- So **giá trị lịch** (bao gồm zone/offset và giờ địa phương): lựa chọn `equals` khi đúng ý nghĩa domain.
- Khi sắp xếp theo trục thời gian, ưu tiên so bằng `Instant`; không suy rằng phép so kiểu ngày giờ địa phương luôn tương đương thứ tự thời gian toàn cầu.

## 15. Đồng hồ hệ thống và kiểm thử: dùng `Clock` khi phù hợp

`ZonedDateTime.now()` và `OffsetDateTime.now()` dựa vào đồng hồ hệ thống và zone mặc định của môi trường. Điều đó tiện cho ứng dụng đơn giản nhưng làm kiểm thử phụ thuộc thời điểm và máy chạy.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-07-15T12:00:00Z"),
        zone);

ZonedDateTime captured = ZonedDateTime.now(fixedClock);

System.out.println(captured);
// 2026-07-15T19:00+07:00[Asia/Ho_Chi_Minh]
```

Inject `Clock` giúp test hành vi quanh DST, hết hạn hoặc cut-off theo ngày. Khi chỉ cần **instant thực tế**, dùng `Instant.now(clock)` và chọn zone riêng lúc hiển thị.

Với lịch của nhiều người dùng, một `Clock` không thay thế cho `ZoneId` của từng người. Đồng hồ cho biết **bây giờ là instant nào**; zone cho biết **hiển thị và lịch địa phương như thế nào**.

## 16. Ví dụ tổng hợp chạy độc lập bằng Java 27

Đặt mã sau vào file `Demo.java`. Ví dụ mô phỏng đổi một instant sang hai vùng, nhận diện gap/overlap và so phép cộng theo lịch với phép cộng theo số giờ thực:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class Demo {
    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");
    private static final ZoneId VIETNAM =
            ZoneId.of("Asia/Ho_Chi_Minh");

    public static void main(String[] args) {
        Instant at = Instant.parse("2026-07-15T12:00:00Z");
        System.out.println(at.atZone(VIETNAM));
        System.out.println(at.atZone(NEW_YORK));
        // 2026-07-15T19:00+07:00[Asia/Ho_Chi_Minh]
        // 2026-07-15T08:00-04:00[America/New_York]

        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);

        List<ZoneOffset> gapOffsets =
                NEW_YORK.getRules().getValidOffsets(gap);
        List<ZoneOffset> overlapOffsets =
                NEW_YORK.getRules().getValidOffsets(overlap);

        System.out.println("Gap options: " + gapOffsets);         // []
        System.out.println("Overlap options: " + overlapOffsets);
        // [-04:00, -05:00]

        ZonedDateTime first = overlap.atZone(NEW_YORK);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println(first.toInstant());
        System.out.println(second.toInstant());
        // 2026-11-01T05:30:00Z
        // 2026-11-01T06:30:00Z

        ZonedDateTime start = ZonedDateTime.of(
                2026, 3, 7, 9, 0, 0, 0, NEW_YORK);
        ZonedDateTime byDay = start.plusDays(1);
        ZonedDateTime byHours = start.plusHours(24);

        System.out.println(byDay.toLocalTime());   // 09:00
        System.out.println(byHours.toLocalTime()); // 10:00
        System.out.println(Duration.between(
                start.toInstant(), byDay.toInstant()).toHours()); // 23

        ZonedDateTime inVietnam =
                first.withZoneSameInstant(VIETNAM);
        System.out.println(first.toInstant()
                .equals(inVietnam.toInstant())); // true
    }
}
```

Biên dịch và chạy:

```shell
javac Demo.java
java Demo
```

Không cần `--enable-preview`. Các kết quả liên quan năm 2026 dựa trên dữ liệu quy tắc vùng New York được cung cấp bởi JDK; nếu một môi trường dùng TZDB đã thay đổi khác thường, hãy dựa vào `getValidOffsets` và dữ liệu zone thực tế khi phân tích.

## 17. Các lỗi phổ biến và hướng xử lý

| Cách làm/nhận định | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Dùng `LocalDateTime` làm timestamp tuyệt đối | Thiếu zone/offset, không biết instant | Dùng `Instant` hoặc giá trị có offset |
| Coi `ZoneId` và `ZoneOffset` là cùng nghĩa | Mất quy tắc lịch sử và tương lai | Giữ IANA region ID cho lịch theo địa phương |
| Lưu `-05:00` cho mọi cuộc hẹn New York | Lệch một giờ trong mùa DST | Lưu `America/New_York` và giải quyết theo ngày |
| Dùng `withZoneSameLocal` khi hiển thị sang vùng mới | Thay đổi instant sự kiện | Dùng `withZoneSameInstant` |
| Nghĩ `withOffsetSameLocal` vẫn giữ instant | Sai thời điểm thực | Dùng `withOffsetSameInstant` |
| Tạo `ZonedDateTime` từ giờ gap mà không kiểm tra | API có thể tự đẩy giờ lên | Xác định chính sách; từ chối hoặc điều chỉnh có thông báo |
| Tạo thời gian trong overlap mà không chọn nhánh | Hai instant có thể hợp lệ | Cho phép chọn offset; xác thực bằng `ofStrict` |
| Cộng `Duration.ofHours(24)` để giữ “09:00 ngày mai” | Sau DST có thể thành 10:00 | Dùng phép cộng theo lịch và kiểm tra zone rules |
| Cộng `plusDays(1)` khi yêu cầu đủ 24 giờ | Có ngày chỉ 23/25 giờ thực | Dùng `plusHours(24)` hoặc `Duration` |
| Dùng `equals` để hỏi “có cùng instant?” | Zone/offset khác khiến kết quả false | So `toInstant()` hoặc `isEqual(...)` |
| Dùng `ZoneId.systemDefault()` như vùng khách hàng | Phụ thuộc cấu hình server | Nhận/lưu zone ID của từng người dùng |
| Dựa vào chữ viết tắt múi giờ ba ký tự | Dễ mơ hồ, không đủ quy tắc | Dùng region ID IANA hoặc offset rõ ràng |
| Coi dữ liệu TZDB không bao giờ đổi | Lịch tương lai có thể khác sau cập nhật | Theo dõi tzdb/JDK và chính sách tính lại |
| Định dạng ngày giờ chỉ có `09:00` | Không phân biệt được vùng/ngày/nhánh overlap | Bổ sung zone, offset hoặc instant theo hợp đồng |
| Gọi `now()` trực tiếp ở nhiều nơi trong test | Kết quả phụ thuộc thời gian thật | Inject `Clock` hoặc dùng instant cố định |
| Nghĩ `OffsetDateTime` tự chuyển DST khi cộng tháng | Không có region rules | Dùng `ZonedDateTime` cho lịch theo vùng |

## 18. Checklist cho ứng dụng nhiều múi giờ

1. **Dữ liệu mô tả instant đã xảy ra hay một giờ địa phương dự kiến?** Chọn kiểu trước khi viết phép tính.
2. **Người dùng đã chọn region `ZoneId` chưa?** Không suy từ vị trí máy chủ hoặc offset hiện tại.
3. **Tại local date-time cần tạo có bao nhiêu offset hợp lệ?** Dùng `ZoneRules.getValidOffsets` nếu giờ cần chính xác.
4. **Gap thì tự dời giờ hay yêu cầu người dùng chọn lại?** Chính sách cần rõ và kiểm thử được.
5. **Overlap thì chọn lần đầu hay lần sau?** Nếu cần phân biệt, lưu offset/instant đã chọn.
6. **Đang đổi vùng để hiển thị hay cố thay đổi giờ địa phương?** Chọn `SameInstant` hoặc `SameLocal` có chủ đích.
7. **Phép cộng là ngày theo lịch hay thời lượng chính xác?** Không đánh đồng `plusDays` và 24 giờ.
8. **Dữ liệu lưu trữ có đủ ngữ nghĩa để tái lập kết quả không?** Xét instant, local time, zone và quy tắc lịch.
9. **Lịch tương lai sẽ được xử lý thế nào khi tzdb đổi?** Cần quyết định giữ instant hay giữ giờ theo địa phương.
10. **API qua mạng có ràng buộc định dạng ISO, offset/zone và cách parse không?** Không chỉ gửi timestamp mơ hồ.
11. **Có dùng dữ liệu TZDB của JDK hiện tại không?** Kiểm thử đặc biệt các vùng có lịch chuyển đổi khó.
12. **Test có phụ thuộc đồng hồ thật hoặc default zone không?** Inject `Clock`, truyền `ZoneId` rõ ràng.

## 19. Tổng kết

Trong Java SE 27, ba kiểu quan trọng có vai trò khác nhau:

- **`ZoneId`** chỉ định **quy tắc** của một vùng địa lý hoặc một fixed offset. Với lịch gắn địa phương, ID vùng như `America/New_York` thường cần thiết hơn một offset được chụp tại một thời điểm.
- **`ZonedDateTime`** lưu ngày–giờ, vùng và offset đã được phân giải. Nó phù hợp để hiển thị theo vùng và thực hiện phép tính theo lịch địa phương, đồng thời phải xử lý gap/overlap do các thay đổi offset.
- **`OffsetDateTime`** lưu ngày–giờ và offset, xác định được instant nhưng **không lưu quy tắc của vùng**. Nó phù hợp cho timestamp/trao đổi dữ liệu khi offset là thông tin cần giữ.

Để chuyển **cùng một sự kiện** sang múi giờ khác, dùng `withZoneSameInstant` hoặc đổi từ `Instant`. Chỉ dùng `withZoneSameLocal` khi thật sự muốn giữ giờ đồng hồ địa phương. Với lịch định kỳ, cần phân biệt **ngày theo lịch** với **số giờ thực**, đồng thời quyết định cách xử lý những local times không tồn tại hoặc xảy ra hai lần.

Cuối cùng, múi giờ là **dữ liệu quy tắc có thể được cập nhật**, không phải một số cộng/trừ UTC bất biến. Thiết kế tốt phải ghi lại đủ ý định của người dùng, kiểm soát chính sách giờ nhập nhằng và coi bản cập nhật TZDB là một tình huống vận hành cần được kiểm thử.

## Tài liệu tham khảo

- [ZoneId (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZoneId.html) — region ID, fixed offset, quy tắc và khả năng thay đổi TZDB.
- [ZoneOffset (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZoneOffset.html) — offset cố định với UTC.
- [ZonedDateTime (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html) — tạo ngày giờ theo vùng, gap/overlap, `withZoneSameInstant`, `withZoneSameLocal`, `plusDays` và `plusHours`.
- [OffsetDateTime (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/OffsetDateTime.html) — ngày giờ với offset, `withOffsetSameInstant` và `withOffsetSameLocal`.
- [ZoneRules (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneRules.html) — `getValidOffsets`, `getTransition`, `getOffset`.
- [ZoneRulesProvider (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneRulesProvider.html) — nguồn dữ liệu quy tắc, các phiên bản rules.
- [Instant (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html) — biểu diễn instant và cách chuyển sang vùng.
- [Duration (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html) và [Period (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html) — elapsed duration so với calendar-based amounts.
- [DateTimeFormatter (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html) — định dạng và parse ISO.
- [Clock (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html) — kiểm soát thời gian và vùng khi kiểm thử.
