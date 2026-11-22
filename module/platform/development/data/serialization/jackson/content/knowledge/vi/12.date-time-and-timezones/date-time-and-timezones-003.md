# Biểu diễn Instant, OffsetDateTime và ZonedDateTime theo hợp đồng

Khi một ứng dụng Java trao đổi ngày giờ qua JSON, điều quan trọng đầu tiên là xác định dữ liệu đang mô tả **một thời điểm trên dòng thời gian**, **một thời điểm kèm độ lệch UTC**, hay **một thời điểm gắn với múi giờ khu vực có quy tắc lịch sử và quy tắc giờ mùa hè**. Ba kiểu `Instant`, `OffsetDateTime` và `ZonedDateTime` của Java biểu diễn những ý nghĩa khác nhau. Nếu chọn sai kiểu hoặc để Jackson tự áp dụng múi giờ ngữ cảnh ngoài ý muốn, JSON sau khi đọc/ghi có thể giữ đúng con số nhưng làm mất ý nghĩa thời gian ban đầu.

Trong Jackson Databind, module `jackson-datatype-jsr310` cung cấp serializer và deserializer cho các kiểu `java.time`. Hợp đồng JSON nên quy định rõ định dạng, độ chính xác, múi giờ và việc có cần giữ tên múi giờ khu vực hay không. Với API trao đổi giữa các hệ thống, chuỗi ISO-8601 thường là lựa chọn dễ hiểu và ít nhập nhằng hơn timestamp số.

## 1. Ba khái niệm thời gian cần phân biệt

### 1.1. Instant: một điểm duy nhất trên dòng thời gian

`Instant` biểu diễn một thời điểm tuyệt đối theo trục thời gian UTC. Nó không lưu múi giờ khu vực hoặc offset ban đầu của người gửi. Có thể hình dung `Instant` là số giây và phần nano giây tính từ epoch `1970-01-01T00:00:00Z`.

Ví dụ:

```java
Instant occurredAt = Instant.parse("2026-11-12T09:30:00Z");
```

Chuỗi ISO-8601 có hậu tố `Z` cho biết thời điểm được biểu diễn theo UTC. Cùng một `Instant` có thể được hiển thị ở các múi giờ khác nhau mà không thay đổi thời điểm thực tế:

```java
Instant instant = Instant.parse("2026-11-12T09:30:00Z");

ZonedDateTime inVietnam = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime inParis = instant.atZone(ZoneId.of("Europe/Paris"));
```

Hai giá trị `ZonedDateTime` có giờ địa phương khác nhau, nhưng cùng chỉ đến một `Instant`.

`Instant` phù hợp cho thời điểm sự kiện đã xảy ra hoặc cần được so sánh toàn cục: thời điểm tạo đơn hàng, thời điểm nhận message, thời điểm ghi log, thời điểm thanh toán hoặc thời điểm một job hoàn tất.

### 1.2. OffsetDateTime: ngày giờ địa phương kèm offset UTC

`OffsetDateTime` gồm ngày, giờ, phần nano giây và một `ZoneOffset` cố định, ví dụ `+07:00` hoặc `-05:00`. Offset cho phép xác định một `Instant`, nhưng không chứa tên múi giờ khu vực như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`.

```java
OffsetDateTime receivedAt = OffsetDateTime.parse(
        "2026-11-12T16:30:00+07:00"
);

Instant sameInstant = receivedAt.toInstant();
```

`2026-11-12T16:30:00+07:00` và `2026-11-12T09:30:00Z` là hai cách biểu diễn cùng một thời điểm. Tuy vậy, `OffsetDateTime` còn giữ offset `+07:00` mà người gửi đã cung cấp, trong khi `Instant` chỉ giữ thời điểm UTC.

Offset không chứa bộ quy tắc lịch sử hoặc giờ mùa hè của một vùng. `+01:00` không cho biết đó là Paris, London hay một vùng khác từng có cùng offset. Vì vậy, `OffsetDateTime` phù hợp khi hợp đồng cần giữ offset trong payload nhưng không cần tên múi giờ khu vực.

### 1.3. ZonedDateTime: ngày giờ, offset và múi giờ khu vực

`ZonedDateTime` kết hợp ngày giờ địa phương, offset đang áp dụng và `ZoneId`. `ZoneId` có thể là tên vùng IANA như `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York` hoặc một offset cố định.

```java
ZonedDateTime appointment = ZonedDateTime.of(
        2026, 11, 12,
        16, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

Một biểu diễn có tên vùng thường có dạng:

```text
2026-11-12T16:30:00+07:00[Asia/Ho_Chi_Minh]
```

Giá trị này mang nhiều thông tin hơn `OffsetDateTime`: ngoài offset `+07:00`, nó còn cho biết các quy tắc múi giờ của vùng `Asia/Ho_Chi_Minh`. Những quy tắc đó có thể thay đổi theo thời gian do quyết định pháp lý của quốc gia hoặc khu vực.

`ZonedDateTime` phù hợp cho lịch hẹn, giờ mở cửa, lịch chạy định kỳ hoặc sự kiện mà ý nghĩa phụ thuộc vào múi giờ của địa điểm. Ví dụ, “cuộc họp lúc 09:00 tại Paris” cần giữ `Europe/Paris`; chỉ giữ `+01:00` sẽ không đủ để xử lý đúng khi quy tắc giờ mùa hè thay đổi.

## 2. So sánh ý nghĩa và dữ liệu được giữ lại

| Kiểu | Thành phần được giữ | Có xác định được Instant? | Có giữ tên vùng IANA? |
|---|---|---:|---:|
| `Instant` | Điểm trên dòng thời gian UTC | Có | Không |
| `OffsetDateTime` | Local date-time + offset cố định | Có | Không |
| `ZonedDateTime` | Local date-time + offset đang áp dụng + ZoneId | Có | Có, nếu ZoneId là vùng có tên |

Một cách chọn nhanh:

- Dùng `Instant` khi chỉ cần biết **khi nào** sự kiện xảy ra trên toàn cầu.
- Dùng `OffsetDateTime` khi hợp đồng cần giữ **giờ địa phương và offset mà nguồn gửi**.
- Dùng `ZonedDateTime` khi nghiệp vụ cần giữ **múi giờ khu vực và quy tắc của vùng đó**.

Không nên chọn `ZonedDateTime` chỉ vì tên của nó có chữ “zone”. Nếu hệ thống chỉ cần ghi nhận một thời điểm sự kiện, `Instant` thường đơn giản và ít mang theo trạng thái không cần thiết hơn.

## 3. Cấu hình Jackson để xử lý java.time

Các ví dụ dưới đây dùng Jackson 2.x với Java Time module. Project cần dependency `jackson-datatype-jsr310` tương thích với các artifact Jackson Databind đang sử dụng.

Ví dụ Maven:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

Nếu project sử dụng Jackson BOM hoặc BOM của framework, để BOM quản lý version của module thay vì pin một version riêng không đồng bộ.

### 3.1. Đăng ký JavaTimeModule

Có thể cấu hình `ObjectMapper` tường minh:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
        .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
        .build();
```

Các lựa chọn trên có ý nghĩa:

- `JavaTimeModule` đăng ký serializer/deserializer cho các kiểu `java.time` được hỗ trợ.
- `WRITE_DATES_AS_TIMESTAMPS` được tắt để ngày giờ được ghi thành chuỗi thay vì timestamp số hoặc dạng mảng cho một số kiểu.
- `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` được tắt để việc deserialize không tự điều chỉnh giá trị về múi giờ ngữ cảnh của mapper, nhờ đó giữ offset hoặc zone từ input khi kiểu đích hỗ trợ thông tin đó.
- `WRITE_DATES_WITH_ZONE_ID` được bật để `ZonedDateTime` có thể ghi thêm ZoneId dạng `[Europe/Paris]`, thay vì chỉ ghi offset.

Trong các phiên bản Jackson có `SerializationFeature.WRITE_DATES_WITH_CONTEXT_TIME_ZONE`, nếu mục tiêu là giữ múi giờ nằm trong giá trị `ZonedDateTime`, có thể tắt feature này để timezone ngữ cảnh không ghi đè timezone của giá trị:

```java
mapper.disable(SerializationFeature.WRITE_DATES_WITH_CONTEXT_TIME_ZONE);
```

Hãy xác nhận feature có trong phiên bản Jackson của project trước khi dùng. Quan trọng nhất là chọn rõ chính sách timezone của mapper và kiểm tra JSON đầu ra thực tế; không nên để timezone mặc định của máy chạy quyết định hợp đồng API.

### 3.2. Tại sao cần tắt WRITE_DATES_AS_TIMESTAMPS?

Nếu `WRITE_DATES_AS_TIMESTAMPS` được bật, Jackson có thể ghi các kiểu thời gian thành số hoặc cấu trúc dạng mảng tùy loại và cấu hình độ chính xác. Với `Instant`, timestamp số có thể được biểu diễn theo giây kèm phần thập phân hoặc mili giây; ý nghĩa phụ thuộc cấu hình nanosecond. Với các kiểu local date/time, một số serializer có thể ghi mảng thành phần.

Ví dụ chuỗi ISO dễ đọc:

```json
{
  "occurredAt": "2026-11-12T09:30:00Z",
  "receivedAt": "2026-11-12T16:30:00+07:00",
  "scheduledAt": "2026-11-12T16:30:00+07:00[Asia/Ho_Chi_Minh]"
}
```

Chuỗi cho biết trực tiếp UTC marker, offset hoặc zone ID. Timestamp số ngắn hơn, nhưng consumer phải biết đơn vị là giây hay mili giây và phải hiểu quy tắc phần thập phân. Với hợp đồng API công khai, ISO-8601 thường dễ trao đổi hơn.

## 4. Biểu diễn ba kiểu trong cùng một DTO

Giả sử một sự kiện cần lưu thời điểm phát sinh, thời điểm nhận từ hệ thống đối tác và giờ hẹn tại một địa điểm:

```java
public record EventTimes(
        Instant occurredAt,
        OffsetDateTime receivedAt,
        ZonedDateTime scheduledAt
) {
}
```

Tạo dữ liệu mẫu:

```java
EventTimes event = new EventTimes(
        Instant.parse("2026-11-12T09:30:00Z"),
        OffsetDateTime.parse("2026-11-12T16:30:05+07:00"),
        ZonedDateTime.of(
                2026, 11, 13,
                9, 0, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh")
        )
);

String json = mapper.writeValueAsString(event);
```

Với cấu hình dạng chuỗi và zone ID ở trên, JSON có thể được biểu diễn như sau:

```json
{
  "occurredAt": "2026-11-12T09:30:00Z",
  "receivedAt": "2026-11-12T16:30:05+07:00",
  "scheduledAt": "2026-11-13T09:00:00+07:00[Asia/Ho_Chi_Minh]"
}
```

Deserialize về đúng DTO:

```java
EventTimes restored = mapper.readValue(json, EventTimes.class);
```

Khi giữ nguyên zone ID và không điều chỉnh theo context timezone, `scheduledAt` có thể khôi phục cả múi giờ khu vực. Nếu JSON chỉ chứa `2026-11-13T09:00:00+07:00`, consumer vẫn xác định được instant nhưng không biết tên vùng ban đầu.

## 5. Vì sao OffsetDateTime và ZonedDateTime có thể thay đổi khi deserialize?

Jackson có feature `DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE`. Khi feature được bật, một số kiểu date/time có timezone có thể được điều chỉnh về timezone trong context của mapper/deserialization. Điều này có thể khiến offset hoặc zone nhận được khác với chuỗi JSON gốc, dù thời điểm tuyệt đối vẫn tương đương.

Ví dụ JSON:

```json
{
  "time": "2026-11-12T16:30:00+07:00"
}
```

Nếu mapper đang dùng UTC làm context timezone và điều chỉnh được bật, giá trị sau deserialize có thể được chuẩn hóa về UTC. Khi đó, ứng dụng có thể thấy `09:30Z` thay cho `16:30+07:00`.

Hai giá trị này biểu diễn cùng một instant, nhưng không bằng nhau theo mọi phép so sánh:

```java
OffsetDateTime original = OffsetDateTime.parse(
        "2026-11-12T16:30:00+07:00"
);
OffsetDateTime utc = original.withOffsetSameInstant(ZoneOffset.UTC);

boolean sameMoment = original.isEqual(utc); // true
boolean sameRepresentation = original.equals(utc); // false
```

Nếu hợp đồng yêu cầu giữ offset nguồn, tắt `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` và kiểm tra round-trip. Nếu hợp đồng yêu cầu chuẩn hóa về UTC, có thể giữ chính sách chuẩn hóa nhưng nên biểu diễn field là `Instant` hoặc chuyển đổi tường minh ở boundary để ý định rõ ràng.

## 6. OffsetDateTime và ZonedDateTime không thể thay thế nhau

Một offset là độ lệch số học so với UTC tại một thời điểm, ví dụ `+02:00`. Một ZoneId khu vực như `Europe/Paris` là tập quy tắc theo thời gian. Offset của vùng có thể thay đổi giữa mùa đông và mùa hè.

Ví dụ Paris có thể dùng offset `+01:00` vào mùa đông và `+02:00` vào mùa hè. Nếu chỉ lưu:

```text
2026-07-15T09:00:00+02:00
```

ứng dụng biết giờ địa phương và offset tại thời điểm đó. Nó không biết người dùng chọn `Europe/Paris`, `Europe/Berlin` hay một vùng khác có cùng offset.

Nếu nghiệp vụ cần biết vùng cụ thể, giữ `ZonedDateTime` hoặc lưu thêm `ZoneId` riêng. Ví dụ hợp đồng có thể tách:

```json
{
  "localDateTime": "2026-07-15T09:00:00",
  "zoneId": "Europe/Paris"
}
```

Consumer có thể kết hợp local date-time và zone ID để áp dụng quy tắc của vùng. Cách tách này đôi khi dễ dùng với hệ thống không hỗ trợ cú pháp bracket zone ID của Java.

## 7. Giờ mùa hè và thời điểm không tồn tại hoặc bị lặp

Các vùng có daylight saving time (DST) tạo ra hai tình huống quan trọng khi chuyển giữa giờ mùa đông và giờ mùa hè:

- **Gap:** đồng hồ nhảy về phía trước, tạo ra một khoảng giờ địa phương không tồn tại.
- **Overlap:** đồng hồ lùi lại, khiến một khoảng giờ địa phương xuất hiện hai lần với hai offset khác nhau.

Ví dụ tại `Europe/Paris`, một thời điểm địa phương trong vùng overlap có thể tương ứng với hai instant khác nhau. `ZonedDateTime` giữ offset đã được chọn cùng zone ID, vì vậy nó phân biệt được hai lần xuất hiện đó.

Java có quy tắc mặc định khi tạo `ZonedDateTime` từ local date-time và zone:

```java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId paris = ZoneId.of("Europe/Paris");

ZonedDateTime defaultChoice = ZonedDateTime.of(local, paris);
ZonedDateTime laterChoice = defaultChoice.withLaterOffsetAtOverlap();
```

Ngày 25 tháng 10 năm 2026 là ngày chuyển khỏi giờ mùa hè tại Paris; `02:30` xuất hiện hai lần. Java mặc định chọn offset sớm hơn theo quy tắc của `ZonedDateTime`; `withLaterOffsetAtOverlap()` chọn lần xuất hiện muộn hơn. Nếu ứng dụng cần một lựa chọn cụ thể, hãy biểu diễn và kiểm tra lựa chọn đó thay vì để người dùng hiểu nhầm rằng local date-time luôn xác định duy nhất một instant.

Với thời gian rơi vào gap, Java thường điều chỉnh local time về phía trước theo độ dài gap để tạo một thời điểm hợp lệ. Nếu nghiệp vụ không cho phép tự điều chỉnh giờ hẹn, cần kiểm tra `ZoneRules.getValidOffsets(localDateTime)` trước khi tạo giá trị:

```java
List<ZoneOffset> validOffsets = paris.getRules().getValidOffsets(local);

if (validOffsets.isEmpty()) {
    // Local date-time nằm trong DST gap: thời điểm địa phương không tồn tại.
} else if (validOffsets.size() > 1) {
    // Local date-time nằm trong overlap: cần chọn một offset cụ thể.
} else {
    // Có đúng một offset hợp lệ.
}
```

Đối với lịch hẹn hoặc lịch chạy định kỳ, xử lý gap/overlap là một phần của nghiệp vụ và nên được ghi rõ trong hợp đồng.

## 8. Chuyển đổi giữa Instant, OffsetDateTime và ZonedDateTime

Java cung cấp các phương thức chuyển đổi giúp giữ hoặc thay đổi đúng thành phần thời gian. Cần chọn phương thức theo mục đích:

### 8.1. Từ Instant sang múi giờ khu vực

```java
Instant instant = Instant.parse("2026-11-12T09:30:00Z");
ZonedDateTime zoned = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

`atZone(...)` giữ nguyên instant và tính lại giờ địa phương/offset theo ZoneId.

### 8.2. Từ OffsetDateTime sang Instant

```java
OffsetDateTime received = OffsetDateTime.parse(
        "2026-11-12T16:30:00+07:00"
);
Instant instant = received.toInstant();
```

Chuyển đổi này giữ thời điểm tuyệt đối, nhưng `Instant` không giữ lại offset ban đầu.

### 8.3. Từ ZonedDateTime sang OffsetDateTime

```java
ZonedDateTime zoned = ZonedDateTime.now(ZoneId.of("Europe/Paris"));
OffsetDateTime offsetDateTime = zoned.toOffsetDateTime();
```

Kết quả giữ local date-time và offset tại thời điểm đó, nhưng bỏ tên vùng và các quy tắc khu vực.

### 8.4. Thay đổi zone nhưng giữ cùng instant

```java
ZonedDateTime paris = ZonedDateTime.now(ZoneId.of("Europe/Paris"));
ZonedDateTime tokyo = paris.withZoneSameInstant(ZoneId.of("Asia/Tokyo"));
```

`withZoneSameInstant(...)` giữ thời điểm tuyệt đối và tính lại giờ địa phương theo zone mới.

### 8.5. Thay đổi zone nhưng cố giữ giờ địa phương

```java
ZonedDateTime newLocalZone = paris.withZoneSameLocal(
        ZoneId.of("Asia/Tokyo")
);
```

`withZoneSameLocal(...)` cố giữ các thành phần giờ địa phương, vì vậy instant có thể thay đổi. Nếu giờ địa phương không hợp lệ trong zone mới do DST gap hoặc overlap, Java áp dụng quy tắc giải quyết của `ZonedDateTime`.

Hai phương thức `withZoneSameInstant` và `withZoneSameLocal` phục vụ hai mục đích khác nhau. Khi đổi múi giờ để hiển thị một sự kiện đã xảy ra, thường dùng `withZoneSameInstant`. Khi chuyển một lịch địa phương sang vùng khác và chủ đích là giữ giờ trên đồng hồ, cần xem xét `withZoneSameLocal` cùng các quy tắc DST.

## 9. Hợp đồng JSON nên chọn dạng nào?

Không có một kiểu thời gian duy nhất phù hợp cho mọi field. Hợp đồng nên phản ánh ý nghĩa nghiệp vụ của dữ liệu.

| Ý nghĩa field | Kiểu Java đề xuất | Dạng JSON điển hình |
|---|---|---|
| Thời điểm sự kiện xảy ra | `Instant` | `"2026-11-12T09:30:00Z"` |
| Thời điểm nhận kèm offset từ nguồn | `OffsetDateTime` | `"2026-11-12T16:30:00+07:00"` |
| Lịch hẹn tại một vùng cụ thể | `ZonedDateTime` | `"2026-11-12T16:30:00+07:00[Asia/Ho_Chi_Minh]"` |
| Hệ thống consumer không hỗ trợ bracket zone ID | `Instant` và field `zoneId` riêng, hoặc local date-time + zone ID | Object JSON tách các thành phần |

Một API có thể dùng `Instant` cho `createdAt` và `updatedAt`, nhưng dùng `ZonedDateTime` cho lịch hẹn cần giữ múi giờ địa điểm. Không nên đổi tất cả field sang cùng một kiểu chỉ để cấu hình serializer đơn giản hơn.

### 9.1. Dùng Instant cho audit timestamp

```java
public record AuditEvent(
        String action,
        Instant occurredAt
) {
}
```

Giá trị `occurredAt` không phụ thuộc nơi người dùng xem sự kiện. Khi hiển thị, tầng giao diện chuyển instant sang ZoneId của người dùng.

### 9.2. Dùng ZonedDateTime cho lịch hẹn theo địa điểm

```java
public record Appointment(
        String title,
        ZonedDateTime startsAt
) {
}
```

Nếu lịch hẹn được định nghĩa là “09:00 giờ Paris”, giữ `Europe/Paris` để áp dụng đúng quy tắc vùng khi tính toán hoặc hiển thị ở tương lai. Chỉ giữ offset của ngày tạo lịch có thể không đủ nếu quy tắc DST thay đổi trước ngày hẹn.

### 9.3. Dùng OffsetDateTime khi offset nguồn là một phần dữ liệu

```java
public record PartnerMessage(
        String messageId,
        OffsetDateTime partnerTimestamp
) {
}
```

Nếu cần audit offset mà đối tác đã gửi, `OffsetDateTime` thể hiện rõ ý nghĩa này. Nếu cần cả instant chuẩn hóa và ZoneId mà đối tác tuyên bố, hãy lưu chúng thành các field riêng thay vì cố suy ra ZoneId từ offset.

## 10. Dùng @JsonFormat khi cần định dạng riêng

Mặc định, các serializer của Java Time module sử dụng định dạng ISO phù hợp với từng kiểu. Nếu hợp đồng yêu cầu pattern riêng, có thể dùng `@JsonFormat` trên property hoặc cấu hình writer/reader tương ứng.

Ví dụ chỉ định property được biểu diễn bằng chuỗi:

```java
public record EventPayload(
        @JsonFormat(shape = JsonFormat.Shape.STRING)
        Instant occurredAt
) {
}
```

Với `OffsetDateTime`, một pattern có thể gồm offset:

```java
public class PartnerPayload {
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
    private OffsetDateTime sentAt;
}
```

`XXX` biểu diễn offset theo dạng như `+07:00` hoặc `Z`. Nếu pattern bỏ offset, consumer có thể không xác định được instant duy nhất. Với `ZonedDateTime`, pattern cần chứa thông tin zone ID nếu hợp đồng muốn giữ tên vùng, ví dụ ký hiệu `VV` của `DateTimeFormatter`.

Không nên dùng pattern chỉ có giờ địa phương như `yyyy-MM-dd HH:mm:ss` cho dữ liệu cần xác định một instant, trừ khi hợp đồng cung cấp múi giờ ở field khác. Chuỗi `2026-11-12 16:30:00` không cho biết đó là giờ của vùng nào.

`@JsonFormat(timezone = "UTC")` có thể làm thay đổi cách diễn giải hoặc biểu diễn giá trị theo timezone được chỉ định. Chỉ dùng khi hợp đồng thật sự yêu cầu chuẩn hóa UTC; không thêm annotation này một cách máy móc vào mọi property.

## 11. Timestamp số, giây và mili giây

Timestamp số thường được tính từ Unix epoch, nhưng có hai đơn vị phổ biến:

- Epoch seconds: số giây kể từ `1970-01-01T00:00:00Z`.
- Epoch milliseconds: số mili giây kể từ cùng mốc.

Ví dụ cùng một thời điểm có thể được biểu diễn bằng một số giây hoặc một số mili giây lớn hơn một nghìn lần. Nếu contract chỉ ghi `timestamp: 1794475800` mà không định nghĩa đơn vị, consumer có thể hiểu sai thời gian.

Jackson có `SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` và `DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS` để ảnh hưởng cách diễn giải timestamp số trong các trường hợp tương ứng. Để tránh nhập nhằng, nên ưu tiên chuỗi ISO-8601 hoặc đặt tên/đặc tả đơn vị rõ ràng, ví dụ `epochMillis`.

Nếu phải dùng epoch milliseconds:

```java
long epochMillis = instant.toEpochMilli();
Instant restored = Instant.ofEpochMilli(epochMillis);
```

Lưu ý `toEpochMilli()` chỉ giữ độ chính xác đến mili giây; phần nano giây nhỏ hơn mili giây sẽ bị loại bỏ. Nếu hệ thống cần độ chính xác nano giây, dùng ISO string có phần thập phân hoặc một hợp đồng timestamp có đơn vị và độ chính xác được định nghĩa rõ.

## 12. Kiểm tra round-trip và phép so sánh

Test ngày giờ nên xác nhận ý nghĩa cần giữ, không chỉ so sánh chuỗi JSON theo mắt.

```java
EventTimes original = new EventTimes(
        Instant.parse("2026-11-12T09:30:00Z"),
        OffsetDateTime.parse("2026-11-12T16:30:05+07:00"),
        ZonedDateTime.of(
                2026, 11, 13,
                9, 0, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh")
        )
);

String json = mapper.writeValueAsString(original);
EventTimes restored = mapper.readValue(json, EventTimes.class);

assertEquals(original.occurredAt(), restored.occurredAt());
assertEquals(original.receivedAt(), restored.receivedAt());
assertEquals(original.scheduledAt(), restored.scheduledAt());
```

Các phép so sánh của Java Time có ngữ nghĩa khác nhau:

- `Instant.equals(...)` so sánh điểm trên dòng thời gian.
- `OffsetDateTime.equals(...)` so sánh local date-time và offset; dùng `isEqual(...)` khi chỉ cần biết hai giá trị có cùng instant.
- `ZonedDateTime.equals(...)` so sánh local date-time, offset và zone; dùng `isEqual(...)` khi chỉ cần so sánh instant.

Ví dụ:

```java
OffsetDateTime plusSeven = OffsetDateTime.parse(
        "2026-11-12T16:30:00+07:00"
);
OffsetDateTime utc = OffsetDateTime.parse(
        "2026-11-12T09:30:00Z"
);

assertTrue(plusSeven.isEqual(utc));
assertFalse(plusSeven.equals(utc));
```

Nếu hợp đồng cần giữ offset/zone gốc, hãy kiểm tra cả representation. Nếu hợp đồng chỉ cần giữ thời điểm tuyệt đối, hãy kiểm tra `isEqual` hoặc chuyển về `Instant` trước khi so sánh.

Nên có test riêng cho:

- `Instant` có và không có phần nano giây.
- `OffsetDateTime` với offset dương, âm và UTC.
- `ZonedDateTime` có ZoneId khu vực và output có bracket zone ID.
- Deserialize khi context timezone của mapper khác timezone trong payload.
- DST gap và overlap nếu nghiệp vụ sử dụng vùng có giờ mùa hè.
- Timestamp số nếu contract bắt buộc dùng seconds hoặc milliseconds.

## 13. Những lỗi thiết kế thường gặp

### 13.1. Dùng LocalDateTime cho một sự kiện cần instant

`LocalDateTime` không chứa offset hoặc zone. `2026-11-12T09:30:00` không thể xác định thành một instant nếu không có thêm múi giờ. Với thời điểm tạo log, thanh toán hoặc message, dùng `Instant` thường phù hợp hơn.

### 13.2. Cho rằng offset chính là timezone

`+07:00` không tương đương với `Asia/Ho_Chi_Minh`. Offset là độ lệch tại một thời điểm; ZoneId là bộ quy tắc khu vực theo thời gian. Nếu cần quy tắc tương lai hoặc lịch sử, giữ ZoneId.

### 13.3. Ghi ZonedDateTime nhưng làm mất ZoneId

Nếu serializer chỉ ghi `2026-11-12T16:30:00+07:00`, consumer chỉ khôi phục được offset. Bật `WRITE_DATES_WITH_ZONE_ID` hoặc tách ZoneId thành field riêng khi hợp đồng cần giữ tên vùng.

### 13.4. Để context timezone tự thay đổi giá trị

`ADJUST_DATES_TO_CONTEXT_TIME_ZONE` có thể làm offset/zone sau deserialize khác với dữ liệu gốc. Chọn rõ việc có chuẩn hóa hay giữ representation, rồi cấu hình mapper tương ứng.

### 13.5. Lưu giờ hẹn tương lai như một Instant mà bỏ mất ý nghĩa địa phương

Nếu người dùng đặt lịch “09:00 theo giờ Paris”, lưu một instant tính từ offset hiện tại có thể không giữ được ý nghĩa lịch khi quy tắc vùng thay đổi. Giữ ZoneId và chính sách giải quyết DST cho lịch hẹn tương lai.

### 13.6. Dùng timestamp số mà không ghi đơn vị

Giây, mili giây và nano giây không thể được suy ra an toàn chỉ từ một con số. Đặc tả đơn vị hoặc dùng chuỗi ISO-8601.

## 14. Quy trình thiết kế hợp đồng ngày giờ

Khi thêm một field ngày giờ vào DTO, hãy quyết định theo trình tự:

1. Xác định field mô tả một instant đã xảy ra hay một giờ địa phương gắn với địa điểm.
2. Nếu chỉ cần instant, chọn `Instant` và chuẩn hóa JSON thành UTC với hậu tố `Z`.
3. Nếu cần giữ offset nguồn, chọn `OffsetDateTime` và giữ offset trong chuỗi JSON.
4. Nếu cần giữ quy tắc vùng, chọn `ZonedDateTime` và bảo đảm JSON giữ ZoneId hoặc truyền ZoneId ở field riêng.
5. Chọn ISO string hay timestamp số; nếu là timestamp số, ghi rõ đơn vị và độ chính xác.
6. Cấu hình `JavaTimeModule`, timestamp feature và timezone adjustment trước khi mapper được sử dụng.
7. Test round-trip, context timezone khác biệt và DST nếu liên quan đến nghiệp vụ.

Với mapper dùng chung, cấu hình module và feature một lần trong giai đoạn khởi tạo. Không bật/tắt timezone hoặc timestamp feature trên mapper theo từng request; nếu hai luồng cần hợp đồng khác nhau, tạo reader/writer hoặc mapper chuyên biệt đã cấu hình trước.

## 15. Ghi nhớ

`Instant` lưu một thời điểm tuyệt đối; `OffsetDateTime` lưu ngày giờ cùng offset cố định; `ZonedDateTime` lưu ngày giờ cùng offset đang áp dụng và ZoneId. Ba kiểu này không thay thế nhau vì chúng giữ lượng thông tin và ý nghĩa nghiệp vụ khác nhau.

Với Jackson 2.x, đăng ký `JavaTimeModule`, thường tắt `WRITE_DATES_AS_TIMESTAMPS` để dùng ISO string, cân nhắc `WRITE_DATES_WITH_ZONE_ID` để giữ tên vùng cho `ZonedDateTime`, và kiểm soát `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` để tránh thay đổi offset/zone ngoài ý muốn. Hợp đồng tốt phải nói rõ field biểu diễn instant, offset hay múi giờ khu vực; phải xác định đơn vị nếu dùng timestamp số; và phải có test cho round-trip cùng các trường hợp DST liên quan.
