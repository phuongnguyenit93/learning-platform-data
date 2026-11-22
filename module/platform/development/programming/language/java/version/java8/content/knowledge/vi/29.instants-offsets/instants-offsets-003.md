# ZoneOffset và độ lệch UTC trong Java 8+ (`java.time`)

`ZoneOffset` thuộc gói `java.time`, biểu diễn **độ lệch cố định giữa giờ đồng hồ địa phương và UTC**. Nếu một thời điểm UTC là `02:30Z` và offset là `+07:00` thì giờ địa phương tương ứng là `09:30`; nếu offset là `-03:30` thì giờ địa phương tương ứng là `23:00 của ngày hôm trước`.

Đây là kiến thức nền để đọc timestamp ISO 8601, chuyển `LocalDateTime` thành một thời điểm thực (`Instant`), truyền ngày giờ có offset qua API, và hiểu vì sao **offset không thay thế múi giờ vùng (`ZoneId`) khi có quy tắc giờ mùa hè/DST hoặc lịch hẹn tương lai**.

`ZoneOffset` có từ Java 8, vẫn được hỗ trợ trong Java hiện đại. Trong bài sử dụng API Java 8 còn áp dụng; ví dụ đầy đủ chạy được trên JDK 17+ và chỉ dùng thư viện chuẩn.

## 1. UTC, offset và zone: ba khái niệm khác nhau

- **UTC (Coordinated Universal Time):** mốc tham chiếu cho các thời điểm. Hậu tố `Z` trong timestamp ISO biểu diễn **offset 0 so với UTC**, ví dụ `2026-01-20T02:30:00Z`.
- **UTC offset:** một lượng chênh lệch có dấu so với UTC, ví dụ `+07:00`, `+05:30`, `-03:30`. Nó được biểu diễn bằng `ZoneOffset`.
- **Time-zone region:** một vùng theo quy tắc lịch sử và pháp lý, ví dụ `Asia/Ho_Chi_Minh` hoặc `America/New_York`. Nó được biểu diễn bằng `ZoneId` vùng và có thể áp dụng các offset khác nhau ở những ngày khác nhau.

Công thức suy diễn giờ đồng hồ khi **đã biết một instant**:

```text
local datetime = UTC datetime + offset
UTC datetime   = local datetime - offset
```

Ví dụ:

| UTC | Offset | Giờ địa phương |
| --- | --- | --- |
| `2026-01-20 02:30Z` | `+07:00` | `2026-01-20 09:30` |
| `2026-01-20 02:30Z` | `+05:30` | `2026-01-20 08:00` |
| `2026-01-20 02:30Z` | `Z` (0) | `2026-01-20 02:30` |
| `2026-01-20 02:30Z` | `-03:30` | `2026-01-19 23:00` |

Dấu `+` nghĩa là **giờ địa phương đi trước UTC**; dấu `-` nghĩa là **giờ địa phương đi sau UTC**. Đây là chỗ dễ nhầm: khi đang có giờ địa phương `09:30+07:00` và muốn tìm UTC, bạn **trừ 7 giờ**, thu được `02:30Z`, chứ không cộng tiếp 7 giờ.

**Offset không phải tên quốc gia.** Nhiều vùng có thể cùng offset tại một thời điểm nhưng có lịch sử và quy tắc đổi giờ khác nhau. `ZoneOffset.of("+07:00")` không chứa các quy tắc cho riêng Hà Nội, Bangkok hay một vùng cụ thể.

## 2. Vị trí của `ZoneOffset` trong `java.time`

Các kiểu thời gian có ý nghĩa khác nhau:

| Kiểu | Chứa gì? | Biết một instant duy nhất? | Ví dụ |
| --- | --- | --- | --- |
| `LocalDate` | Ngày theo lịch | Không | `2026-01-20` |
| `LocalTime` | Giờ đồng hồ | Không | `09:30` |
| `LocalDateTime` | Ngày + giờ, không zone/offset | **Không** | `2026-01-20T09:30` |
| `ZoneOffset` | Độ lệch so với UTC | Không, vì chưa có ngày/giờ | `+07:00` |
| `Instant` | Mốc tuyệt đối trên dòng thời gian | **Có** | `2026-01-20T02:30:00Z` |
| `OffsetDateTime` | LocalDateTime + ZoneOffset | **Có** | `2026-01-20T09:30+07:00` |
| `ZonedDateTime` | LocalDateTime + ZoneId vùng + offset đã xác định | **Có** | `2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh]` |
| `ZoneId` vùng | Định danh vùng và bộ quy tắc offset | Không, nếu chỉ có ZoneId | `America/New_York` |

`ZoneOffset` kế thừa `ZoneId` và cung cấp một zone có **quy tắc offset cố định**. Tuy nhiên, `ZoneId.of("America/New_York")` là một vùng mà offset phụ thuộc ngày/giờ. Đừng viết code dùng `ZoneOffset` cố định cho một lịch cần theo quy tắc tương lai của vùng có DST.

Đối với một sự kiện đã chốt, `Instant` thường là dữ liệu nền phù hợp; `ZoneOffset` là một cách nhìn/local representation của instant đó. Đối với lịch đặt trước "09:00 giờ địa phương mỗi thứ Hai", phải lưu thêm **giờ địa phương, ZoneId và quy tắc lặp**, chứ không thể chỉ cố định một offset đã thấy hôm nay.

## 3. Tạo `ZoneOffset` bằng các factory hiện hành

`ZoneOffset` là lớp bất biến, thread-safe và **value-based**. Dùng các factory được cung cấp, không tự định nghĩa offset bằng chuỗi không chuẩn:

```java
ZoneOffset utc = ZoneOffset.UTC;
ZoneOffset plusSeven = ZoneOffset.of("+07:00");
ZoneOffset alsoSeven = ZoneOffset.ofHours(7);
ZoneOffset india = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset minusThreeThirty = ZoneOffset.ofHoursMinutes(-3, -30);
ZoneOffset secondsBased = ZoneOffset.ofTotalSeconds(25_200);
```

Bảng API:

| Cách tạo | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| `ZoneOffset.UTC` | Offset UTC bằng 0 | `Z` |
| `ZoneOffset.of(String)` | Parse định dạng offset được hỗ trợ | `+07:00` |
| `ZoneOffset.ofHours(int)` | Dịch theo số giờ nguyên | `-04:00` |
| `ZoneOffset.ofHoursMinutes(int,int)` | Dịch theo giờ và phút | `+05:30` |
| `ZoneOffset.ofHoursMinutesSeconds(int,int,int)` | Bao gồm cả giây nếu cần | `+05:30:45` |
| `ZoneOffset.ofTotalSeconds(int)` | Tạo từ tổng số giây có dấu | `25200` giây → `+07:00` |
| `ZoneOffset.from(TemporalAccessor)` | Trích offset từ đối tượng thời gian có trường `OFFSET_SECONDS` | Offset của `OffsetDateTime` |

Ví dụ kiểm tra tương đương:

```java
ZoneOffset a = ZoneOffset.of("+07:00");
ZoneOffset b = ZoneOffset.ofHours(7);
ZoneOffset c = ZoneOffset.ofTotalSeconds(7 * 3600);

System.out.println(a.equals(b)); // true
System.out.println(b.equals(c)); // true
System.out.println(a.getTotalSeconds()); // 25200
```

**Không dùng `==` để so sánh hai `ZoneOffset`.** Đây là lớp value-based và API chỉ bảo đảm `equals` theo số giây offset; việc cache instance là chi tiết triển khai, không phải hợp đồng về object identity. Cũng **không dùng instance `ZoneOffset` làm khóa đồng bộ** (monitor).

### Quy tắc dấu của giờ, phút, giây

Với `ofHoursMinutes(-3,-30)`, cả giờ và phút cùng dấu âm. `ofHoursMinutes(-3,30)` **không hợp lệ** vì dấu không nhất quán, sẽ ném `DateTimeException`.

Nếu tổng offset nhỏ hơn 1 giờ về phía âm, có thể dùng `ofHoursMinutes(0,-30)`. Khi dùng string, viết `"-00:30"` hoặc `"-03:30"` rõ nghĩa.

Độ lệch UTC trong ứng dụng thực tế **không bắt buộc là bội số của một giờ**. Có các offset theo nửa giờ, 45 phút; dữ liệu lịch sử có thể bao gồm **giây**. Không làm tròn mọi offset thành `int hours` và không tự giả định phút bằng 0.

## 4. Phạm vi, định dạng và chuẩn hóa offset

Theo API `java.time.ZoneOffset`, miền hỗ trợ là **`-18:00` tới `+18:00`**, tính cả hai đầu mút, tức tổng số giây từ **`-64.800` đến `+64.800`**. Đây là ràng buộc của Java, không có nghĩa mọi offset trong miền đều là offset đang được một vùng dân cư sử dụng.

```java
ZoneOffset max = ZoneOffset.MAX;   // +18:00
ZoneOffset min = ZoneOffset.MIN;   // -18:00

ZoneOffset.of("+19:00"); // DateTimeException
```

Các dạng `ZoneOffset.of(String)` có thể nhận gồm:

```text
Z           UTC
+7          giờ với một chữ số (được chuẩn hóa thành +07:00)
+07         hai chữ số giờ
+07:00      dạng có dấu và dấu hai chấm
+0700       dạng liền giờ/phút
-03:30      dạng âm có dấu
+05:30:45   dạng có cả phần giây
```

`getId()` chuẩn hóa đầu ra thành `Z` khi offset 0; thành `±HH:MM` khi số giây bằng 0; hoặc `±HH:MM:SS` khi có giây khác 0. Ví dụ:

```java
ZoneOffset.of("+07:00").getId(); // "+07:00"
ZoneOffset.UTC.getId();         // "Z"
ZoneOffset.of("-03:30").getId(); // "-03:30"
```

**Phân biệt parser linh hoạt và chuẩn hợp đồng API.** `ZoneOffset.of("+7")` có thể chấp nhận đầu vào, nhưng JSON/RFC 3339 công khai nên thống nhất chuỗi với offset đầy đủ dạng `+07:00` hoặc `Z`. Giá trị có **offset chứa giây** là trường hợp đặc biệt trong API Java và **không phải dạng RFC 3339 phổ biến cho timestamp**, nên cần thỏa thuận schema/định dạng nếu trao đổi với hệ thống khác.

### Phép so sánh `compareTo` có thứ tự đáng chú ý

`ZoneOffset.compareTo(...)` dùng **thứ tự giảm dần theo tổng số giây**, ví dụ sort natural cho:

```text
[Z, +07:00, +05:30, -03:30]
```

sẽ ra:

```text
[+07:00, +05:30, Z, -03:30]
```

Đừng giả định `compareTo` mặc định sắp số âm trước, số dương sau theo trị số; nếu muốn thứ tự tăng theo `getTotalSeconds()`, viết `Comparator.comparingInt(ZoneOffset::getTotalSeconds)`.

## 5. Chuyển `Instant` thành ngày giờ có offset

`Instant` chỉ một thời điểm; từ nó có thể tạo các cách biểu diễn địa phương khác nhau mà **không thay đổi mốc thời gian thực**:

```java
Instant instant = Instant.parse("2026-01-20T02:30:00Z");
ZoneOffset vietnam = ZoneOffset.of("+07:00");
ZoneOffset india = ZoneOffset.of("+05:30");

OffsetDateTime inVietnam = instant.atOffset(vietnam);
OffsetDateTime inIndia = instant.atOffset(india);

System.out.println(inVietnam); // 2026-01-20T09:30+07:00
System.out.println(inIndia);   // 2026-01-20T08:00+05:30
```

Cả hai `OffsetDateTime` đều cho cùng `Instant` khi gọi `toInstant()`:

```java
boolean sameInstant = inVietnam.toInstant().equals(inIndia.toInstant());
// true
```

Vì vậy một API có thể chấp nhận cả `2026-01-20T09:30:00+07:00` và `2026-01-20T08:00:00+05:30` nếu mục tiêu là thu nhận **thời điểm thực**, sau đó chuẩn hóa về `Instant`/UTC ở backend.

## 6. Chuyển `LocalDateTime` thành `Instant` bằng offset

Một `LocalDateTime` **tự nó không xác định được một instant**. Khi thêm `ZoneOffset`, công thức mới xác định một điểm trên dòng thời gian:

```java
LocalDateTime local = LocalDateTime.of(2026, 1, 20, 9, 30);
ZoneOffset offset = ZoneOffset.of("+07:00");

Instant instant = local.toInstant(offset);
// 2026-01-20T02:30:00Z.
```

Đoạn này hợp lệ **khi đầu vào thật sự là 09:30 tại offset +07:00**. Nếu người dùng chỉ gõ 09:30 ở vùng có DST mà không gửi offset, không được tự gắn offset đang áp dụng cho giờ hiện tại của server.

Có thể tạo `OffsetDateTime` rồi lấy instant:

```java
OffsetDateTime dateTime = OffsetDateTime.of(local, offset);
Instant same = dateTime.toInstant();
```

Cũng có thể tạo từ `Instant` và zone/offset:

```java
OffsetDateTime view = OffsetDateTime.ofInstant(
    Instant.parse("2026-01-20T02:30:00Z"),
    ZoneOffset.of("+07:00"));
```

Điểm cần nhớ: **từ `Instant` → offset/local time là phép biểu diễn; từ `LocalDateTime` + offset → `Instant` là phép diễn giải có điều kiện**. Nếu offset đầu vào sai, instant suy ra cũng sai nhưng API Java không thể đoán ý định thật của người dùng.

## 7. Hai thao tác giống tên nhưng khác nghĩa: `SameInstant` và `SameLocal`

`OffsetDateTime` có hai phép đổi offset đặc biệt:

| Phương thức | Bảo toàn | Điều gì đổi? | Hệ quả |
| --- | --- | --- | --- |
| `withOffsetSameInstant(newOffset)` | **Instant** | Local date/time được điều chỉnh theo offset mới | Cùng sự kiện, nhìn từ offset khác |
| `withOffsetSameLocal(newOffset)` | **LocalDateTime** | Instant thay đổi theo offset mới | Gán một offset khác cho cùng giờ đồng hồ |

Ví dụ:

```java
OffsetDateTime original =
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00");

OffsetDateTime asIndia =
    original.withOffsetSameInstant(ZoneOffset.of("+05:30"));
// 2026-01-20T08:00+05:30; vẫn là 02:30Z.

OffsetDateTime reinterpreted =
    original.withOffsetSameLocal(ZoneOffset.of("+05:30"));
// 2026-01-20T09:30+05:30; nay là 04:00Z.
```

**Chọn `SameInstant`** khi đổi cách hiển thị nhưng giữ nguyên sự kiện. **Chọn `SameLocal`** chỉ khi chủ đích của domain là giữ 09:30 giờ đồng hồ và gán offset khác, đồng nghĩa thay đổi **mốc thời gian thực**.

Sai lầm nguy hiểm: nhận timestamp `09:30+07:00` của một giao dịch, gọi `withOffsetSameLocal(UTC)` để "chuyển về UTC". Kết quả sẽ là 09:30Z — **lệch 7 giờ**. Đúng là `withOffsetSameInstant(UTC)`, hoặc lấy `toInstant()` rồi serialize.

`OffsetDateTime` là bất biến: các phương thức `withOffset...` trả về đối tượng mới; không thay đổi instance ban đầu.

## 8. `equals`, `isEqual` và so sánh mốc thời gian

Hai `OffsetDateTime` có thể đại diện cùng instant nhưng khác local time và offset:

```java
OffsetDateTime a =
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00");
OffsetDateTime b =
    OffsetDateTime.parse("2026-01-20T08:00:00+05:30");

System.out.println(a.equals(b));  // false
System.out.println(a.isEqual(b)); // true
```

- `equals` xét toàn bộ thông tin local date-time và offset, nên hai cách biểu diễn khác nhau không `equals`.
- `isEqual` xét hai mốc trên dòng thời gian; dùng khi chỉ quan tâm hai timestamp có cùng instant.
- `toInstant().equals(...)` cũng kiểm tra cùng instant và thuận tiện để lưu trữ, đối chiếu mốc.
- `isBefore` và `isAfter` trên `OffsetDateTime` so các instant thực. Không so string datetime khác offset bằng phép so từ điển để xác định thứ tự thời gian.
- `OffsetDateTime.compareTo` ưu tiên so theo instant, rồi phân biệt local date-time trong trường hợp instant bằng nhau để nhất quán với `equals`. Vì vậy `compareTo(...) == 0` **không** tương đương `isEqual(...)` trong mọi trường hợp; nếu mục tiêu chỉ là timeline, chuẩn hóa về `Instant`.

Khi xử lý các timestamp offset-aware từ nhiều bên, một chiến lược tốt là parse thành `Instant` cho các phép so thời gian và **giữ offset ban đầu như metadata riêng** nếu yêu cầu audit/UX thực sự cần.

## 9. Offset cố định không phải múi giờ vùng có DST

Điểm phân biệt quan trọng nhất là **một `ZoneOffset` cố định không mô hình hóa lịch chuyển giờ hoặc thay đổi pháp lý**:

```java
ZoneOffset fixed = ZoneOffset.of("-05:00");
ZoneId newYork = ZoneId.of("America/New_York");

Instant winter = Instant.parse("2024-01-15T12:00:00Z");
Instant summer = Instant.parse("2024-07-15T12:00:00Z");

System.out.println(newYork.getRules().getOffset(winter)); // -05:00
System.out.println(newYork.getRules().getOffset(summer)); // -04:00
```

New York năm 2024 có offset `-05:00` trong mùa đông và `-04:00` trong mùa hè. Nhưng `fixed` luôn là `-05:00` ở mọi instant. Với một `Instant` mùa hè:

```java
Instant summer = Instant.parse("2024-07-15T12:00:00Z");

System.out.println(summer.atZone(ZoneId.of("America/New_York")));
// 2024-07-15T08:00-04:00[America/New_York]

System.out.println(summer.atOffset(ZoneOffset.of("-05:00")));
// 2024-07-15T07:00-05:00
```

**Hai cách hiển thị đều mô tả cùng instant 12:00Z**, nhưng chỉ biểu diễn vùng New York đúng vào ngày mùa hè ấy khi dùng `ZoneId`. Không suy ra “New York luôn -05:00” từ một timestamp mùa đông.

`ZoneId.getRules().getOffset(instant)` trả **offset có hiệu lực tại instant**; vì đã biết instant, kết quả duy nhất. Nhưng nếu bắt đầu từ **`LocalDateTime` chưa gắn offset**, đặc biệt trong giờ đổi DST, có thể có **0, 1 hoặc 2 offset hợp lệ**, cần giải quyết theo nghiệp vụ.

### DST gap và overlap

Ví dụ theo quy tắc `America/New_York` năm 2024:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(zone.getRules().getValidOffsets(gap));
// []: 02:30 không tồn tại tại lần nhảy giờ mùa xuân.

System.out.println(zone.getRules().getValidOffsets(overlap));
// [-04:00, -05:00]: 01:30 xảy ra hai lần.
```

Với **gap** không tồn tại instant phù hợp cho local time đã cho. Với **overlap** phải chọn một trong hai offset nếu lịch/đặt chỗ cần xác định instant duy nhất. Một hệ thống có thể yêu cầu khách chọn offset hoặc hiển thị hai lựa chọn, hoặc có chính sách mặc định công bố.

`LocalDateTime.atZone(zone)` có chính sách giải quyết mặc định đối với giờ thiếu/trùng; **đừng sử dụng ngầm** nếu nghiệp vụ đòi từ chối giờ không hợp lệ hoặc bắt buộc khách chọn lượt đầu/lượt sau.

### Nếu cần nghiêm ngặt

```java
static ZonedDateTime strict(LocalDateTime local, ZoneId zone) {
    List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
    if (valid.size() != 1) {
        throw new IllegalArgumentException("Gap or overlap");
    }
    return ZonedDateTime.ofStrict(local, valid.get(0), zone);
}
```

Đây là method minh họa; cần import `java.time.*` và `java.util.*`. Nó chỉ chấp nhận giờ địa phương có đúng một offset; nếu cần xử lý overlap hợp lệ với offset do người dùng chọn, kiểm tra `valid.contains(chosenOffset)` rồi dùng `ZonedDateTime.ofStrict(local,chosenOffset,zone)`.

## 10. Phân biệt cách thiết kế API và database

### API về sự kiện đã xảy ra

Nếu dữ liệu là thời điểm một giao dịch được ghi nhận, nên trả ISO timestamp có offset rõ; thường chọn UTC `Z`:

```json
{
  "transactionId": "tx-8",
  "occurredAt": "2026-01-20T02:30:00Z"
}
```

Nếu bên gửi cung cấp local time kèm offset:

```json
{
  "occurredAt": "2026-01-20T09:30:00+07:00"
}
```

Hai payload diễn tả cùng instant. Backend có thể parse `OffsetDateTime` và lưu `Instant`. Nếu cần biết offset dùng khi khách ký giao dịch, lưu offset đã ghi nhận **ở một field khác có định nghĩa rõ**; từ `Instant` không thể suy ra offset đầu vào duy nhất.

Đừng đặt tên `timeZone` cho giá trị `"+07:00"` khi người dùng/nghiệp vụ cần **tên vùng múi giờ**. Đặt `utcOffset` hoặc `offsetSeconds` cho chênh lệch; `timeZoneId` cho vùng IANA.

### API đặt lịch địa phương

Một cuộc hẹn `09:30` theo giờ địa phương ở một thành phố nên truyền:

```json
{
  "localStart": "2026-01-20T09:30:00",
  "timeZoneId": "Asia/Ho_Chi_Minh"
}
```

Backend parse `LocalDateTime` + `ZoneId` và giải quyết offset tại **ngày cụ thể**. Nếu là giờ ở vùng có DST, phải có chính sách gap/overlap. Không thêm một offset cố định của thời điểm tạo lịch rồi dùng lại cho tất cả lần hẹn.

### Lưu trữ

- **Mốc event đã xảy ra:** lưu instant hoặc timestamp database có semantics UTC/instant được kiểm chứng.
- **Thời gian hẹn tương lai theo địa điểm:** lưu local start, zone ID và resolved instant (nếu đã chốt), với chính sách thống nhất về việc cập nhật tzdb.
- **Offset lịch sử:** chỉ lưu thêm nếu phục vụ audit, đối chiếu chuỗi người dùng nhìn thấy hoặc nguồn gốc dữ liệu.
- **Giờ lặp lại theo lịch:** lưu local time + zone ID + quy tắc lặp, không cố định `OffsetDateTime` của lần đầu tiên cho mọi lần tiếp theo.

Không đánh đồng tên kiểu SQL có chữ `WITH TIME ZONE` với việc mọi cơ sở dữ liệu sẽ lưu **nguyên tên ZoneId**. Ví dụ PostgreSQL `timestamptz` biểu diễn instant và **không giữ ZoneId gốc**; session có thể quyết định cách render. Với JDBC/ORM, thực hiện integration test cho driver và DB thực tế, vì chính sách chuyển đổi và precision không giống nhau ở mọi engine.

## 11. Format và parse timestamp có offset

`DateTimeFormatter.ISO_OFFSET_DATE_TIME` được thiết kế để parse/format ngày giờ có offset:

```java
String input = "2026-01-20T09:30:00+07:00";
OffsetDateTime parsed = OffsetDateTime.parse(
    input, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
Instant normalized = parsed.toInstant();
// 2026-01-20T02:30:00Z.
```

Có thể định nghĩa format để hiển thị:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
    "uuuu-MM-dd'T'HH:mm:ssXXX");

String formatted = formatter.format(parsed);
// 2026-01-20T09:30:00+07:00.
```

Trong pattern, `XXX` thường tạo offset theo dạng ISO có dấu hai chấm `+07:00` và `Z` khi offset 0; `XX` có thể tạo dạng liền `+0700`. Hãy xác định format cho API thay vì mặc định một frontend bất kỳ parse mọi biến thể được Java hỗ trợ.

**Cảnh báo pattern:** `yyyy` là year-of-era, `uuuu` là proleptic year; `YYYY` là **week-based-year** và dễ tạo ngày sai năm gần ranh giới năm. Dùng formatter ISO chuẩn khi hợp đồng phù hợp, tránh tự đặt pattern không cần thiết.

Đối với epoch timestamp, **giây khác milliseconds**; `Instant.ofEpochSecond(...)` không nhận số millisecond. Nếu lưu offset dưới dạng số, `getTotalSeconds()` cho số giây có dấu, ví dụ `+07:00` → `25200`. Không dùng `25200` như đơn vị phút hoặc milliseconds.

## 12. Giá trị `ZoneOffset` có thể lấy từ đâu?

| Nguồn | Cách lấy đúng | Giới hạn |
| --- | --- | --- |
| Client gửi `+07:00` | `ZoneOffset.of("+07:00")` | Chỉ có offset, không có ZoneId vùng |
| Client gửi ISO timestamp có offset | `OffsetDateTime.parse(...).getOffset()` | Biết offset **tại timestamp đó**, không biết region gốc |
| Có `ZonedDateTime` | `zoned.getOffset()` | Offset hiệu lực tại thời điểm của ZonedDateTime |
| Có `ZoneId` và `Instant` | `zone.getRules().getOffset(instant)` | Lấy đúng offset của vùng tại instant |
| Có `LocalDateTime` và `ZoneId` | `zone.getRules().getValidOffsets(local)` | Có thể 0/1/2 offset do DST |
| Chỉ có `LocalDateTime` | **Không đủ dữ liệu** | Không tự đoán offset của hệ điều hành |

Không lấy `ZoneId.systemDefault()` để suy ra offset cho mọi tác vụ, trừ khi đó chính là chính sách được định nghĩa rõ. Khi ứng dụng chạy trên nhiều vùng/kubernetes nodes, default zone có thể khác nhau, gây dữ liệu không nhất quán.

### UTC và phép so với offset 0

`ZoneOffset.UTC`, `ZoneOffset.of("Z")` và `ZoneOffset.of("+00:00")` đều biểu diễn **offset bằng 0** và bằng nhau theo `equals`. `getId()` chuẩn hóa về `Z`.

`"GMT"`, `"UTC"`, `"UTC+07:00"` có thể được `ZoneId.of(...)` hiểu như ID vùng đặc biệt có rules offset cố định; đừng mặc định chúng là một region IANA có lịch DST. Nếu cần địa điểm cụ thể, chọn vùng như `Europe/Paris` hoặc `America/New_York`.

## 13. Thứ tự thời gian và dữ liệu báo cáo nhiều nguồn

Nếu một dịch vụ nhận sự kiện từ nhiều vùng, không so:

```text
2026-01-20T08:00:00+05:30
2026-01-20T09:30:00+07:00
```

bằng cách so từ điển để xác định sự kiện nào trước; chúng cùng mốc `02:30Z`. Hãy parse sang `Instant` rồi sắp theo time-line:

```java
List<OffsetDateTime> events = Arrays.asList(
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00"),
    OffsetDateTime.parse("2026-01-20T08:00:00+05:30"));

List<Instant> instants = events.stream()
    .map(OffsetDateTime::toInstant)
    .sorted()
    .collect(Collectors.toList());
// Hai phần tử Instant bằng nhau.
```

Các đoạn mã này dùng `java.util.*`, `java.time.*` và `java.util.stream.Collectors`. Để tạo thứ tự ổn định khi nhiều event cùng instant, thêm một khóa phụ như event ID, sequence hoặc thời gian hệ thống ghi nhận; **chỉ sắp theo instant** không thể phân biệt các sự kiện đồng thời.

Nếu yêu cầu nghiệp vụ tính "ngày của người dùng", hãy chuyển `Instant` sang `ZoneId` của người xem rồi lấy `toLocalDate()`. Đừng mặc định ngày UTC bằng ngày địa phương. Ví dụ `2026-01-20T02:30Z` có thể vẫn là ngày 19/01 ở vùng UTC âm.

## 14. Lưu ý về tính đúng đắn, tương tranh và hiệu năng

- `ZoneOffset` là immutable/thread-safe và không cần khóa để tái sử dụng. Các factory có thể cache một số object, nhưng không được dựa vào việc hai biến cùng tham chiếu.
- `ZoneOffset` **không thay đổi theo thời gian**; muốn offset theo region và instant, dùng `ZoneId` rồi tra `ZoneRules`.
- Việc parse offset ID không hợp lệ có thể ném `DateTimeException`; đọc input từ API phải bắt lỗi và trả mã lỗi phù hợp, không dựa vào offset default.
- Chênh lệch ±18h là giới hạn lớp, không phải validation nghiệp vụ cho mọi hệ thống. Có thể giới hạn whitelist zone IANA nếu sản phẩm chỉ phục vụ một tập vùng.
- Đừng dùng `ZoneOffset` để tính "đúng 24 giờ cho ngày hôm sau tại một thành phố". Qua DST, **một ngày lịch có thể 23/25 giờ**, trong khi `Duration.ofHours(24)` luôn là 24 giờ thực.
- Đừng lấy offset từ một bản ghi mùa đông rồi gán cho bản ghi mùa hè của cùng region; tra rules **tại instant tương ứng**.
- `OffsetDateTime` mang offset và xác định instant; nó không mang toàn bộ thông tin region hoặc quy tắc lịch. Muốn lịch định kỳ theo giờ địa phương, phải giữ `ZoneId` riêng.
- `LocalDateTime.toInstant(offset)` không kiểm tra rằng offset đó **thật sự hợp lệ với một region** ở ngày đó. Nó chỉ diễn giải local time theo offset được cung cấp. Nếu cần đối chiếu với region, kiểm tra `ZoneRules.getValidOffsets` hoặc dùng `ZonedDateTime.ofStrict(...)`.
- `DateTimeFormatter` immutable/thread-safe khi dùng đúng. Dữ liệu API và UI có thể dùng format khác nhau, nhưng hợp đồng round-trip phải rõ.
- Dữ liệu từ database cần kiểm tra **precision** (milli/micro/nanosecond) khi đối chiếu; việc chuyển `ZoneOffset` không tự giải quyết mất precision ở tầng lưu trữ.

## 15. Chương trình Java hoàn chỉnh có thể biên dịch/chạy

Tạo file **`ZoneOffsetDemo.java`**. Ví dụ chỉ dùng các API có từ Java 8 và không cần thư viện ngoài. Nó kiểm tra: tạo offset có dấu, tổng số giây, hai cách nhìn của cùng instant, phân biệt `SameInstant`/`SameLocal`, vùng New York đổi offset theo DST, thứ tự natural của `ZoneOffset` và ngoại lệ khi input sai.

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

public class ZoneOffsetDemo {
    public static void main(String[] args) {
        ZoneOffset utc = ZoneOffset.UTC;
        ZoneOffset vietnam = ZoneOffset.ofHours(7);
        ZoneOffset india = ZoneOffset.ofHoursMinutes(5, 30);
        ZoneOffset negative = ZoneOffset.ofHoursMinutes(-3, -30);
        ZoneOffset fromSeconds = ZoneOffset.ofTotalSeconds(25_200);

        System.out.println("offset IDs: " + Arrays.asList(
                utc.getId(), vietnam.getId(), india.getId(), negative.getId()));
        System.out.println("UTC seconds: " + utc.getTotalSeconds());
        System.out.println("+07 seconds: " + vietnam.getTotalSeconds());
        System.out.println("same +07 offset: " + vietnam.equals(fromSeconds));

        Instant instant = Instant.parse("2026-01-20T02:30:00Z");
        OffsetDateTime localVietnam = instant.atOffset(vietnam);
        OffsetDateTime localIndia = localVietnam.withOffsetSameInstant(india);
        OffsetDateTime changedInstant = localVietnam.withOffsetSameLocal(india);
        System.out.println("instant: " + instant);
        System.out.println("in Vietnam offset: " + localVietnam);
        System.out.println("in India offset: " + localIndia);
        System.out.println("same instant preserved: " +
                instant.equals(localIndia.toInstant()));
        System.out.println("same local changed instant: " +
                changedInstant.toInstant());
        System.out.println("offset date-time equals: " +
                localVietnam.equals(localIndia));
        System.out.println("offset date-time isEqual: " +
                localVietnam.isEqual(localIndia));

        LocalDateTime requested = LocalDateTime.of(2026, 1, 20, 9, 30);
        System.out.println("local +07 -> instant: " +
                requested.toInstant(vietnam));
        System.out.println("parsed: " +
                OffsetDateTime.parse("2026-01-20T09:30:00+07:00",
                    DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant());

        ZoneId newYork = ZoneId.of("America/New_York");
        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");
        System.out.println("NY winter offset: " +
                newYork.getRules().getOffset(winter));
        System.out.println("NY summer offset: " +
                newYork.getRules().getOffset(summer));
        System.out.println("NY summer regional: " + summer.atZone(newYork));
        System.out.println("NY summer fixed -05: " +
                summer.atOffset(ZoneOffset.of("-05:00")));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        System.out.println("NY gap offsets: " +
                newYork.getRules().getValidOffsets(gap));
        System.out.println("NY overlap offsets: " +
                newYork.getRules().getValidOffsets(overlap));

        List<ZoneOffset> sorted = Arrays.asList(
                ZoneOffset.UTC, vietnam, india, negative)
                .stream().sorted().collect(Collectors.toList());
        System.out.println("offset natural ordering: " + sorted);
        System.out.println("minimum supported: " + ZoneOffset.MIN);
        System.out.println("maximum supported: " + ZoneOffset.MAX);

        try {
            ZoneOffset.of("+19:00");
            System.out.println("out of range accepted unexpectedly");
        } catch (DateTimeException ex) {
            System.out.println("out of range: DateTimeException");
        }
        try {
            ZoneOffset.ofHoursMinutes(-3, 30);
            System.out.println("inconsistent sign accepted unexpectedly");
        } catch (DateTimeException ex) {
            System.out.println("sign mismatch: DateTimeException");
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 ZoneOffsetDemo.java
java ZoneOffsetDemo
```

Kết quả chuẩn:

```text
offset IDs: [Z, +07:00, +05:30, -03:30]
UTC seconds: 0
+07 seconds: 25200
same +07 offset: true
instant: 2026-01-20T02:30:00Z
in Vietnam offset: 2026-01-20T09:30+07:00
in India offset: 2026-01-20T08:00+05:30
same instant preserved: true
same local changed instant: 2026-01-20T04:00:00Z
offset date-time equals: false
offset date-time isEqual: true
local +07 -> instant: 2026-01-20T02:30:00Z
parsed: 2026-01-20T02:30:00Z
NY winter offset: -05:00
NY summer offset: -04:00
NY summer regional: 2024-07-15T08:00-04:00[America/New_York]
NY summer fixed -05: 2024-07-15T07:00-05:00
NY gap offsets: []
NY overlap offsets: [-04:00, -05:00]
offset natural ordering: [+07:00, +05:30, Z, -03:30]
minimum supported: -18:00
maximum supported: +18:00
out of range: DateTimeException
sign mismatch: DateTimeException
```

### Giải thích các kết quả then chốt

1. `offset IDs` gồm `Z` (UTC 0), `+07:00`, `+05:30` và `-03:30`; tất cả đều là giá trị offset hợp lệ.
2. `+07 seconds: 25200` xác nhận đơn vị **giây có dấu**, không phải phút.
3. `in Vietnam offset` và `in India offset` thay đổi ngày/giờ địa phương nhưng vẫn là `2026-01-20T02:30Z`.
4. `withOffsetSameLocal` giữ 09:30 khi đổi sang +05:30, nên instant đổi thành `04:00Z`.
5. `OffsetDateTime.equals` là `false` dù `isEqual` là `true` cho hai cách biểu diễn cùng instant.
6. `NY winter` là -05:00 còn `NY summer` là -04:00; fixed -05:00 không mô tả đúng giờ địa phương New York vào mùa hè.
7. `NY gap offsets` rỗng; `NY overlap offsets` gồm hai offset khác nhau.
8. Natural ordering của `ZoneOffset` đặt offset **lớn hơn về trị giây trước**; số liệu được minh họa bằng sort.
9. `ZoneOffset.MAX/MIN` xác nhận ±18:00, và các input `+19:00`/không nhất quán dấu đều phát sinh `DateTimeException`.

Đầu ra trên đã được đối chiếu với chương trình chạy thực tế. Các kết quả lịch sử về vùng New York dựa trên tzdb đang được cung cấp cho các ngày minh họa; nếu môi trường dùng dữ liệu quy tắc khác, cần xác nhận chính sách cập nhật tzdb khi phục vụ ứng dụng pháp lý/audit.

## 16. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Nhầm `+07:00` là UTC nhanh hơn 7 giờ khi đổi về UTC cũng cộng 7 | Sai dấu, timestamp lệch 14 giờ nếu cộng sai hai lần | `UTC = local - offset` |
| Dùng `ZoneOffset` thay cho `ZoneId` vùng | Không chứa lịch DST/quy tắc đổi giờ | Dùng `ZoneId.of("Area/City")` |
| Lấy offset đang có hôm nay rồi gán cho lịch năm sau | Offset vùng có thể khác theo ngày | `zone.getRules().getOffset(instant)` hoặc resolve local time theo zone |
| Coi `LocalDateTime` là instant | Thiếu offset hoặc zone | Ghép với offset đúng hoặc ZoneId có chính sách |
| Dùng `withOffsetSameLocal` để chuyển sang UTC | Vô tình đổi instant | `withOffsetSameInstant(ZoneOffset.UTC)` |
| Dùng `==` để so các ZoneOffset | Dựa vào caching/identity không cam kết | `equals` |
| Coi `OffsetDateTime.equals` và `isEqual` như nhau | Hai cách nhìn cùng instant có thể khác offset | So `toInstant()`/`isEqual` nếu quan tâm mốc |
| Tạo offset âm với phút dương ở `ofHoursMinutes` | Dấu các thành phần không nhất quán | `ofHoursMinutes(-3,-30)` |
| Không kiểm tra miền ±18 giờ | Có thể ném `DateTimeException` | Validate input, xử lý lỗi rõ |
| Coi `ZoneOffset.compareTo` là ascending số học | API sắp **descending** theo giây | Dùng `comparingInt(getTotalSeconds)` nếu cần tăng |
| Giả định mọi offset đều là số giờ nguyên | Có offset nửa giờ, 45 phút và giây lịch sử | Dùng `ZoneOffset` đầy đủ |
| Chỉ giữ offset của giờ hẹn tương lai | Không giữ ý định vùng khi DST/luật thay đổi | Lưu `ZoneId` và local schedule |
| Gán offset 0 cho mọi chuỗi thiếu offset | Tự tạo instant sai | Từ chối input thiếu thông tin, hoặc quy định rõ zone |
| So timestamp string có offset khác nhau bằng từ điển | Không phản ánh thứ tự instant | Parse sang `Instant` rồi so |
| Tưởng `timestamptz` giữ nguyên tên vùng | Database thường lưu instant, không lưu ZoneId gốc | Lưu zone riêng khi cần |
| Đưa offset chứa giây vào mọi API RFC 3339 | Có thể ngoài định dạng được client hỗ trợ | Chuẩn hóa định dạng theo schema |
| Mặc định `ZoneId.systemDefault` là vùng người dùng | Máy server có zone khác | Nhận region từ domain/user |
| Dùng `getOffset(LocalDateTime)` để chốt một overlap mà không kiểm tra | Có thể chọn offset mặc định trái nghiệp vụ | `getValidOffsets` và chính sách chọn |
| Không kiểm tra DST gap/overlap | Có thể nhận giờ không tồn tại hoặc hai instant | Strict resolution hoặc chính sách công bố |
| Dùng `Instant` để lưu sinh nhật rồi hiển thị theo zone | Ngày lịch có thể bị dịch | `LocalDate` cho birthday |

## 17. Bài tập tự luyện

### Bài 1 — Tính UTC đúng dấu

Giờ địa phương là `2026-01-20T09:30` tại offset `+07:00`. Instant là gì?

**Đáp án:** `2026-01-20T02:30:00Z`. Dùng `LocalDateTime.parse("2026-01-20T09:30").toInstant(ZoneOffset.of("+07:00"))`.

### Bài 2 — Offset không nguyên giờ

Từ `Instant.parse("2026-01-20T02:30:00Z")`, giờ địa phương theo `+05:30` là gì?

**Đáp án:** `2026-01-20T08:00`. Dùng `instant.atOffset(ZoneOffset.of("+05:30"))`.

### Bài 3 — So cùng instant

Hai chuỗi `2026-01-20T09:30+07:00` và `2026-01-20T08:00+05:30` có `OffsetDateTime.equals` bằng nhau không?

**Đáp án:** Không, vì local time và offset khác. Nhưng `isEqual` và `toInstant().equals(...)` là `true`.

### Bài 4 — Sai lầm khi đổi offset

Cho `2026-01-20T09:30+07:00`. Gọi `withOffsetSameLocal(ZoneOffset.UTC)` có giữ nguyên sự kiện không?

**Đáp án:** Không. Nó giữ nguyên giờ đồng hồ `09:30` nhưng đổi instant thành `09:30Z`. Muốn cùng instant, dùng `withOffsetSameInstant(UTC)` để nhận `02:30Z`.

### Bài 5 — Mùa hè New York

Tại `2024-07-15T12:00Z`, offset vùng `America/New_York` là gì? Có thể thay bằng `-05:00` cố định không?

**Đáp án:** Quy tắc cho ngày đó là `-04:00`. Nếu dùng `-05:00` sẽ hiển thị `07:00` thay vì `08:00` ở New York, dù cả hai cách vẫn diễn tả instant 12:00Z với offset của chính nó.

### Bài 6 — Giờ mơ hồ

`2024-11-03T01:30` ở New York có bao nhiêu offset hợp lệ?

**Đáp án:** Hai offset: `-04:00` và `-05:00`. Chỉ local date-time + region chưa đủ xác định một instant; phải chọn offset hoặc chính sách overlap.

### Bài 7 — Miền lệch UTC

`ZoneOffset.of("+19:00")` có hợp lệ không?

**Đáp án:** Không. Java hỗ trợ offset từ `-18:00` đến `+18:00`. Giá trị ngoài miền ném `DateTimeException`.

### Bài 8 — Kiểm tra natural sorting

Nếu sắp `[Z,+07:00,+05:30,-03:30]` với `Collections.sort` theo natural order của `ZoneOffset`, nhận kết quả gì?

**Đáp án:** `[+07:00, +05:30, Z, -03:30]`. `compareTo` của lớp này dùng thứ tự giảm dần theo tổng số giây.

### Bài 9 — Bảo toàn vùng gốc

Một API nhận `2026-01-20T09:30:00+07:00`. Có thể suy ra người gửi chắc chắn ở `Asia/Ho_Chi_Minh` không?

**Đáp án:** Không. Offset `+07:00` có thể ứng với nhiều vùng khác nhau. Nếu tên vùng quan trọng, API phải gửi `timeZoneId` riêng hoặc liên kết với dữ liệu địa điểm đã xác định.

### Bài 10 — Truy vấn theo ngày ở vùng có DST

Nên tính các mốc ngày New York bằng cách lấy start UTC rồi cộng chính xác 86.400 giây không?

**Đáp án:** Không mặc định. Một ngày địa phương có thể 23 hoặc 25 giờ. Tính `day.atStartOfDay(zone).toInstant()` và `day.plusDays(1).atStartOfDay(zone).toInstant()` để tạo khoảng nửa mở theo lịch địa phương.

## 18. Checklist cho code review

- [ ] Xác định rõ dữ liệu là `Instant`, `LocalDateTime`, `OffsetDateTime` hay lịch theo `ZoneId`.
- [ ] Không gán `ZoneOffset` tùy tiện cho một `LocalDateTime` không rõ vùng.
- [ ] Khi đổi múi giờ chỉ để hiển thị, dùng `SameInstant` thay vì `SameLocal`.
- [ ] Đã phân biệt offset cố định và quy tắc của vùng trong lịch tương lai?
- [ ] Có kiểm tra DST gap/overlap nếu parse local time với region?
- [ ] Input `ZoneOffset.of(...)` được validate và xử lý `DateTimeException`?
- [ ] Offset âm được tạo đúng dấu giờ/phút/giây?
- [ ] Đơn vị `getTotalSeconds()`/epoch seconds/milliseconds được ghi rõ?
- [ ] So các `ZoneOffset` bằng `equals`, không dùng `==`?
- [ ] So sự kiện theo `Instant` thay vì raw timestamp string hoặc chỉ `LocalDateTime`?
- [ ] Khi cần region, đã lưu IANA `ZoneId` riêng khỏi numeric offset?
- [ ] Có làm rõ precision và format ISO timestamp cho API/client?
- [ ] Database và ORM đã có round-trip test với offset/instant/region và precision?
- [ ] UI dùng zone người dùng/địa điểm thay vì zone mặc định server?
- [ ] Đã test offset 0, offset âm, offset nửa giờ, giá trị ngoài ±18 và mốc đổi DST?
- [ ] Có chính sách xử lý khi tzdb cập nhật đối với lịch hẹn tương lai và audit?

**Kết luận:** `ZoneOffset` trả lời câu hỏi **"giờ địa phương lệch UTC bao nhiêu?"**; `Instant` trả lời **"sự kiện xảy ra chính xác lúc nào?"**; `ZoneId` vùng trả lời **"cần áp dụng quy tắc múi giờ nào tại ngày/giờ đó?"**. Chọn đúng kiểu, phân biệt `SameInstant` và `SameLocal`, và không lấy một offset cố định làm thay thế toàn bộ quy tắc vùng.

### Tài liệu Oracle chính thức còn được duy trì

- [`ZoneOffset` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html): factory methods, phạm vi ±18 giờ, ID normalization, total seconds, natural ordering, value-based semantics.
- [`ZoneId` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): zone ID vùng, offset cố định, dữ liệu múi giờ và quy tắc vùng.
- [`OffsetDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html): `toInstant`, `withOffsetSameInstant`, `withOffsetSameLocal`, `isEqual`.
- [`Instant` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): thời điểm tuyệt đối và `atOffset`/`atZone`.
- [`ZoneRules` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): `getOffset(Instant)` và `getValidOffsets(LocalDateTime)`.
- [`DateTimeFormatter` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO offset date-time và pattern `X`/`XXX`.