# Bảo toàn thời điểm và đánh giá mất thông tin vùng thời gian

Ngày giờ trong Java không chỉ là một con số hoặc một chuỗi. Một giá trị có thể biểu diễn **thời điểm tuyệt đối trên dòng thời gian**, **giờ địa phương trên đồng hồ**, **độ lệch UTC (offset)** hoặc **một vùng thời gian có quy tắc lịch sử và quy tắc giờ mùa hè (DST)**. Các kiểu này không mang cùng một lượng thông tin.

Khi Jackson chuyển ngày giờ thành JSON rồi đọc lại, lựa chọn kiểu Java và định dạng JSON quyết định thông tin nào còn được giữ. Nếu chỉ lưu một thời điểm UTC, ứng dụng có thể giữ chính xác thời điểm nhưng mất vùng thời gian ban đầu. Nếu chỉ lưu giờ địa phương, ứng dụng có thể giữ giờ trên đồng hồ nhưng không xác định được một thời điểm tuyệt đối.

Để thiết kế đúng, cần phân biệt các kiểu `Instant`, `OffsetDateTime`, `ZonedDateTime` và `LocalDateTime`, sau đó chọn định dạng và cấu hình Jackson theo mục đích dữ liệu.

## 1. Thời điểm, offset và vùng thời gian là gì?

Ba khái niệm thường bị dùng lẫn:

- **Instant (thời điểm):** một điểm duy nhất trên dòng thời gian, độc lập với múi giờ hiển thị.
- **UTC offset:** độ lệch so với UTC tại một thời điểm, ví dụ `+07:00` hoặc `-05:00`.
- **Time zone (vùng thời gian):** một định danh như `Europe/Paris` hoặc `Asia/Tokyo`, đi kèm bộ quy tắc lịch sử và có thể thay đổi theo ngày, mùa hoặc quyết định pháp lý.

Ví dụ cùng một thời điểm có thể được hiển thị ở hai vùng:

```text
Instant: 2026-11-12T09:00:00Z

UTC:              2026-11-12 09:00 +00:00
Asia/Tokyo:       2026-11-12 18:00 +09:00
America/New_York: 2026-11-12 04:00 -05:00
```

Ba cách viết biểu diễn cùng một thời điểm, nhưng thông tin offset và vùng hiển thị khác nhau.

Một offset như `+09:00` không nói rằng dữ liệu thuộc vùng `Asia/Tokyo`. Nhiều vùng có thể có cùng offset tại một thời điểm; một vùng cũng có thể thay đổi offset theo quy tắc DST. Vì vậy, lưu offset không tương đương với lưu ZoneId.

## 2. Các kiểu ngày giờ quan trọng trong java.time

| Kiểu Java | Thông tin được giữ | Có xác định được Instant không? |
|---|---|---|
| `Instant` | Thời điểm tuyệt đối trên dòng thời gian | Có |
| `OffsetDateTime` | Ngày giờ địa phương cùng UTC offset | Có |
| `ZonedDateTime` | Ngày giờ, offset và ZoneId có quy tắc | Có |
| `LocalDateTime` | Ngày và giờ trên đồng hồ, không offset/zone | Không |
| `LocalDate` | Ngày lịch, không giờ và không zone | Không |
| `LocalTime` | Giờ trên đồng hồ, không ngày và không zone | Không |
| `ZoneId` | Định danh vùng thời gian và quy tắc của vùng | Không đứng riêng nếu thiếu ngày giờ |

### 2.1. Instant: lưu thời điểm tuyệt đối

`Instant` biểu diễn một thời điểm trên dòng thời gian, thường được dùng cho:

- Thời điểm tạo bản ghi.
- Thời điểm thanh toán hoặc nhận sự kiện.
- Timestamp của log, audit và message.
- Mốc thời gian cần so sánh giữa nhiều hệ thống.

```java
Instant instant = Instant.parse("2026-11-12T09:00:00Z");
```

`Instant` không lưu múi giờ gốc của người gửi. Khi cần hiển thị cho người dùng, chuyển nó sang vùng thời gian mong muốn:

```java
ZoneId zone = ZoneId.of("Asia/Tokyo");
ZonedDateTime localView = instant.atZone(zone);
```

Nếu JSON đầu vào là `2026-11-12T16:00:00+07:00` và ứng dụng đọc vào `Instant`, thời điểm sẽ được chuẩn hóa thành `2026-11-12T09:00:00Z`. Thời điểm vẫn đúng, nhưng offset `+07:00` ban đầu không còn nằm trong đối tượng Instant.

### 2.2. OffsetDateTime: giữ offset nhưng không giữ vùng

`OffsetDateTime` chứa ngày giờ cùng một UTC offset cụ thể:

```java
OffsetDateTime value =
    OffsetDateTime.parse("2026-11-12T16:00:00+07:00");
```

Kiểu này xác định được một Instant:

```java
Instant instant = value.toInstant();
```

Nó giữ được `+07:00`, nhưng không biết offset đó đến từ vùng nào. Nó không thể trả lời liệu thời gian này thuộc `Asia/Bangkok`, `Asia/Ho_Chi_Minh` hay một vùng khác có cùng offset vào thời điểm đó.

Dùng `OffsetDateTime` khi hợp đồng cần giữ offset do nguồn gửi và không cần áp dụng quy tắc vùng thời gian trong tương lai.

### 2.3. ZonedDateTime: giữ ZoneId và quy tắc vùng

`ZonedDateTime` gồm ngày giờ, offset tại thời điểm đó và ZoneId:

```java
ZonedDateTime meeting = ZonedDateTime.of(
    2026, 11, 12,
    10, 0, 0, 0,
    ZoneId.of("Europe/Paris")
);
```

Đối tượng này giữ thông tin vùng `Europe/Paris`, cho phép Java áp dụng bộ quy tắc của vùng để xác định offset tại ngày giờ tương ứng.

`ZonedDateTime` phù hợp khi:

- Người dùng đặt lịch theo giờ địa phương của một thành phố.
- Hệ thống cần tính ngày giờ theo DST.
- Cần giữ vùng thời gian gốc để hiển thị hoặc tính toán lại.
- Một sự kiện có ý nghĩa gắn với vùng, ví dụ lịch mở cửa hoặc lịch họp địa phương.

### 2.4. LocalDateTime: chỉ là giờ địa phương

`LocalDateTime` không chứa offset hoặc ZoneId:

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 12, 10, 0);
```

Giá trị này chỉ có nghĩa "ngày 12 tháng 11 năm 2026, lúc 10 giờ". Không thể xác định đó là 10 giờ ở Tokyo, Paris hay New York nếu không có vùng bổ sung.

Không nên dùng `LocalDateTime` cho timestamp của một sự kiện đã xảy ra nếu hệ thống cần so sánh chính xác thời điểm giữa các vùng. Nó phù hợp cho dữ liệu lịch dân sự như giờ mở cửa hoặc giờ hẹn khi vùng thời gian được lưu riêng.

## 3. Jackson xử lý ngày giờ như thế nào?

JSON không có kiểu date/time riêng. Ngày giờ thường được trao đổi dưới dạng:

- String theo ISO-8601/RFC 3339.
- Số timestamp theo một đơn vị đã thống nhất.
- Một object JSON có các trường thành phần.

Để Jackson ánh xạ các kiểu `java.time` như `Instant`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime`, ứng dụng Jackson 2.x thường cần module:

```groovy
implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
```

Hoặc Maven:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

Trong ứng dụng Spring Boot, module phù hợp thường được dependency management và auto-configuration tích hợp theo phiên bản Boot. Nếu tự tạo `ObjectMapper` riêng, cần đăng ký module tương ứng.

### 3.1. Cấu hình JavaTimeModule và chuỗi ISO

Một cấu hình thường dùng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Khi tắt `WRITE_DATES_AS_TIMESTAMPS`, các kiểu ngày giờ Java Time thường được ghi dưới dạng chuỗi văn bản thay vì dạng timestamp số hoặc array.

Ví dụ:

```java
Instant instant = Instant.parse("2026-11-12T09:00:00Z");

String json = mapper.writeValueAsString(instant);
```

Kết quả có dạng:

```json
"2026-11-12T09:00:00Z"
```

Chuỗi ISO dễ đọc, có thể kiểm tra bằng mắt và thể hiện rõ offset nếu kiểu dữ liệu chứa offset. Tuy nhiên, định dạng chuỗi cụ thể vẫn phụ thuộc kiểu Java và feature của Jackson.

### 3.2. Bật ZoneId khi serialize ZonedDateTime

Một điểm rất quan trọng: `ZonedDateTime` có thể chứa ZoneId trong Java object, nhưng định dạng JSON mặc định có thể chỉ phát ra ngày giờ cùng offset, không kèm tên vùng.

Ví dụ, giá trị trong Java:

```java
ZonedDateTime parisTime = ZonedDateTime.of(
    2026, 11, 12, 10, 0, 0, 0,
    ZoneId.of("Europe/Paris")
);
```

Nếu chỉ ghi ngày giờ cùng offset:

```json
"2026-11-12T10:00:00+01:00"
```

thì người đọc biết offset là `+01:00`, nhưng không biết ZoneId ban đầu là `Europe/Paris`.

Để giữ ZoneId trong chuỗi serialize, có thể bật:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
    .build();
```

Đầu ra của `ZonedDateTime` có thể chứa phần ZoneId trong ngoặc vuông:

```json
"2026-11-12T10:00:00+01:00[Europe/Paris]"
```

Khi đọc lại vào `ZonedDateTime`, thông tin vùng có thể được khôi phục cùng offset và ngày giờ. Hãy xác nhận cấu hình serializer/deserializer của phiên bản Jackson đang dùng và kiểm thử round-trip thực tế.

### 3.3. Instant và OffsetDateTime có ý nghĩa khác nhau khi serialize

Ví dụ:

```java
Instant instant = Instant.parse("2026-11-12T09:00:00Z");

OffsetDateTime offsetTime =
    OffsetDateTime.parse("2026-11-12T16:00:00+07:00");
```

Hai giá trị trên đại diện cùng một thời điểm. Nhưng:

- Serialize `Instant` thể hiện thời điểm chuẩn hóa theo UTC.
- Serialize `OffsetDateTime` giữ offset `+07:00`.
- Serialize `ZonedDateTime` có thể giữ cả ZoneId nếu bật `WRITE_DATES_WITH_ZONE_ID`.

Chọn kiểu dựa trên thông tin mà hợp đồng cần giữ, không chỉ dựa trên chuỗi đầu vào trông như thế nào.

## 4. Mất thông tin gì khi chuyển giữa các kiểu?

Hãy xét một chuỗi có đầy đủ offset và vùng:

```text
2026-11-12T10:00:00+01:00[Europe/Paris]
```

Các kiểu đích giữ thông tin khác nhau:

| Kiểu đích | Kết quả khái niệm | Thông tin mất |
|---|---|---|
| `ZonedDateTime` | 10:00 +01:00, `Europe/Paris` | Không mất thành phần chính nếu parse đúng |
| `OffsetDateTime` | 10:00 +01:00 | Mất ZoneId `Europe/Paris` |
| `Instant` | 09:00Z | Mất offset gốc và ZoneId |
| `LocalDateTime` | 10:00 | Mất offset, ZoneId và khả năng xác định Instant |

Sơ đồ:

```text
ZonedDateTime
  local date-time + offset + ZoneId
          |
          +----> OffsetDateTime
          |       local date-time + offset
          |       (mất ZoneId)
          |
          +----> Instant
          |       thời điểm tuyệt đối
          |       (mất offset gốc và ZoneId)
          |
          +----> LocalDateTime
                  giờ trên đồng hồ
                  (mất offset, ZoneId, Instant)
```

Một chuyển đổi có thể không làm sai thời điểm nhưng vẫn làm mất ngữ cảnh. Đây là khác biệt giữa **bảo toàn Instant** và **bảo toàn toàn bộ thông tin thời gian nguồn**.

### 4.1. Chuyển ZonedDateTime thành Instant

```java
Instant instant = zonedDateTime.toInstant();
```

Đây là chuyển đổi đúng khi chỉ cần giữ thời điểm. Không thể khôi phục ZoneId ban đầu từ Instant nếu không lưu thêm thông tin.

### 4.2. Chuyển ZonedDateTime thành OffsetDateTime

```java
OffsetDateTime offsetDateTime =
    zonedDateTime.toOffsetDateTime();
```

Thời điểm và offset tại thời điểm đó được giữ lại. Bộ quy tắc vùng như DST, tên vùng và thông tin lịch sử không còn trong kiểu đích.

### 4.3. Chuyển ZonedDateTime thành LocalDateTime

```java
LocalDateTime localDateTime =
    zonedDateTime.toLocalDateTime();
```

Giữ phần giờ trên đồng hồ. Nếu chuyển ngược lại, phải cung cấp ZoneId và có thể phải giải quyết trường hợp giờ không tồn tại hoặc bị lặp do DST.

## 5. Offset không thay thế được ZoneId

Offset là một con số cố định tại một thời điểm. ZoneId là tên vùng gắn với quy tắc.

Ví dụ:

```java
ZoneOffset offset = ZoneOffset.of("+01:00");
ZoneId region = ZoneId.of("Europe/Paris");
```

Vào mùa đông, Paris có thể dùng `+01:00`; vào mùa hè, vùng này dùng `+02:00`. Nếu chỉ lưu `+01:00`, ứng dụng không biết cần thay đổi sang `+02:00` cho một ngày trong mùa hè.

Ví dụ cùng một giờ địa phương:

```java
LocalDateTime local = LocalDateTime.of(2026, 7, 1, 10, 0);

ZonedDateTime paris = local.atZone(ZoneId.of("Europe/Paris"));
ZonedDateTime fixed = local.atZone(ZoneOffset.of("+01:00"));
```

Hai giá trị có thể tạo ra hai Instant khác nhau vì offset của Paris vào tháng 7 có thể là `+02:00`, còn offset cố định vẫn là `+01:00`.

Do đó:

- Dùng `ZoneOffset` khi cần một độ lệch cố định.
- Dùng `ZoneId` khi cần quy tắc của một vùng địa lý.
- Dùng `ZonedDateTime` khi một ngày giờ cụ thể cần gắn với vùng.
- Dùng `OffsetDateTime` khi cần giữ offset mà không cần quy tắc vùng.

## 6. DST làm cho giờ địa phương có thể mơ hồ

Một số vùng thời gian điều chỉnh đồng hồ theo DST. Khi đồng hồ chuyển sang giờ mùa hè hoặc trở lại giờ chuẩn, một số giờ địa phương có thể:

- Không tồn tại (gap): đồng hồ nhảy qua một khoảng thời gian.
- Xuất hiện hai lần (overlap): đồng hồ quay lùi, một giờ trên đồng hồ được lặp lại.

Ví dụ ở `Europe/Paris`:

- Khi chuyển sang giờ mùa hè, một giờ như 02:30 có thể không tồn tại trong ngày chuyển đổi.
- Khi quay về giờ chuẩn, 02:30 có thể xuất hiện hai lần với hai offset khác nhau.

Một `LocalDateTime` như `2026-10-25T02:30` không đủ để xác định một thời điểm duy nhất nếu vùng thời gian đang có overlap.

Có thể kiểm tra các offset hợp lệ bằng `ZoneRules`:

```java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

List<ZoneOffset> offsets =
    zone.getRules().getValidOffsets(local);
```

Kết quả có thể có:

- 0 offset: giờ địa phương không tồn tại do gap.
- 1 offset: giờ địa phương xác định duy nhất.
- 2 offset: giờ địa phương bị lặp do overlap.

`LocalDateTime.atZone(zone)` có quy tắc xử lý gap/overlap mặc định, ví dụ điều chỉnh giờ trong gap và chọn một offset trong overlap. Nếu nghiệp vụ cần người dùng chọn rõ lần xuất hiện nào, hãy kiểm tra `getValidOffsets` và yêu cầu lựa chọn thay vì để mặc định quyết định thay.

## 7. Bảo toàn thời điểm khác với bảo toàn lịch hẹn

Hai loại dữ liệu thời gian có mục đích khác nhau.

### 7.1. Sự kiện đã xảy ra

Ví dụ: một giao dịch được xác nhận lúc nào, một message được nhận lúc nào, một log được tạo lúc nào.

Đối với các sự kiện này, điều quan trọng nhất thường là Instant:

```java
Instant createdAt = Instant.now();
```

Lưu dưới dạng UTC giúp so sánh, sắp xếp và đồng bộ giữa nhiều dịch vụ. Nếu cần biết người dùng nhìn thấy giờ nào hoặc sự kiện được tạo theo vùng nào, lưu thêm ZoneId/offset nguồn như metadata riêng.

### 7.2. Lịch hẹn trong tương lai

Ví dụ: cuộc họp lúc 09:00 mỗi thứ Hai tại Paris. Mục tiêu nghiệp vụ thường là giữ giờ địa phương theo vùng, kể cả khi quy tắc DST thay đổi.

Chỉ lưu một Instant có thể làm mất ý định "09:00 tại Paris". Nếu quy tắc vùng thay đổi trong tương lai, hiển thị theo Instant cố định có thể không còn là 09:00 địa phương.

Với lịch hẹn, có thể lưu:

```text
localDateTime = 2027-04-12T09:00
zoneId        = Europe/Paris
resolvedInstant = ... (nếu cần cho lịch đã xác nhận)
```

Khi cần thực thi hoặc gửi thông báo, ứng dụng áp dụng quy tắc của ZoneId để tính Instant tương ứng. Với lịch lặp lại, giữ local time và ZoneId là đặc biệt quan trọng; một Instant duy nhất không thể mô tả toàn bộ quy tắc lặp theo giờ địa phương.

## 8. Timestamp số và chuỗi ISO-8601

Jackson có thể serialize ngày giờ thành số timestamp hoặc chuỗi.

### 8.1. Timestamp số

Timestamp số cần có đơn vị rõ ràng:

- Epoch seconds: số giây kể từ mốc Unix epoch.
- Epoch milliseconds: số mili giây kể từ mốc Unix epoch.
- Một số cấu hình Java Time có thể dùng giây dạng thập phân để biểu diễn nano giây.

Ví dụ hai giá trị số khác đơn vị:

```text
Epoch seconds:      1794474000
Epoch milliseconds: 1794474000000
```

Nếu bên gửi dùng milliseconds nhưng bên nhận hiểu là seconds, thời điểm sẽ sai rất lớn.

Jackson có các feature như `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` và `READ_DATE_TIMESTAMPS_AS_NANOSECONDS` ảnh hưởng cách diễn giải timestamp cho các kiểu Java Time. Cấu hình mặc định và hành vi cụ thể phụ thuộc module/kiểu dữ liệu. Với `java.util.Date`, timestamp thường được hiểu theo milliseconds; không nên mặc định quy tắc của mọi kiểu ngày giờ là giống nhau.

Nếu dùng timestamp số, hợp đồng API phải ghi rõ đơn vị, độ chính xác và quy tắc đọc/ghi. Tránh dùng một trường `timestamp` mà không định nghĩa seconds hay milliseconds.

### 8.2. Chuỗi ISO-8601

Ví dụ:

```json
{
  "createdAt": "2026-11-12T09:00:00Z",
  "scheduledAt": "2026-11-12T10:00:00+01:00"
}
```

Chuỗi ISO có ưu điểm:

- Dễ đọc và debug.
- Có thể thể hiện offset.
- Ít mơ hồ hơn timestamp số về đơn vị.
- Phù hợp với các hệ thống và ngôn ngữ khác nhau.

Tuy nhiên, chuỗi ISO có offset chưa chắc có ZoneId. Nếu cần giữ vùng như `Europe/Paris`, phải truyền rõ ZoneId hoặc lưu trường zone riêng.

## 9. Cấu hình mapper để bảo toàn zone

Một cấu hình Jackson 2.x thường dùng khi muốn ghi ngày giờ dưới dạng chuỗi và giữ ZoneId của `ZonedDateTime`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
    .build();
```

Ví dụ round-trip:

```java
ZonedDateTime original = ZonedDateTime.of(
    2026, 11, 12, 10, 0, 0, 0,
    ZoneId.of("Europe/Paris")
);

String json = mapper.writeValueAsString(original);

ZonedDateTime restored =
    mapper.readValue(json, ZonedDateTime.class);

System.out.println(original.equals(restored));
System.out.println(original.getZone());
System.out.println(restored.getZone());
```

Với cấu hình giữ ZoneId, mục tiêu là bảo toàn:

- Ngày giờ địa phương.
- Offset tại thời điểm đó.
- ZoneId của vùng.
- Instant tương ứng.

Nếu tắt `WRITE_DATES_WITH_ZONE_ID`, chuỗi có thể chỉ còn offset. Khi đọc lại, ứng dụng có thể giữ đúng Instant nhưng không khôi phục được region zone ban đầu.

### 9.1. Lưu zone thành trường riêng

Một thiết kế API rõ ràng khác là tách dữ liệu:

```json
{
  "localDateTime": "2026-11-12T10:00:00",
  "zoneId": "Europe/Paris"
}
```

DTO:

```java
public record ZonedSchedule(
    LocalDateTime localDateTime,
    String zoneId
) {
}
```

Khi cần tạo ZonedDateTime:

```java
ZonedDateTime scheduled = schedule.localDateTime()
    .atZone(ZoneId.of(schedule.zoneId()));
```

Cách này làm rõ hợp đồng, dễ dùng với hệ thống không hỗ trợ chuỗi ISO có phần `[Europe/Paris]`, và giúp validation ZoneId riêng. Nếu cần xác định đúng một lần xuất hiện trong DST overlap, phải bổ sung offset được chọn hoặc một chính sách rõ ràng.

## 10. @JsonFormat và định dạng ngày giờ

`@JsonFormat` có thể điều khiển pattern hoặc timezone cho một property:

```java
import com.fasterxml.jackson.annotation.JsonFormat;

public class EventRequest {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX"
    )
    private OffsetDateTime occurredAt;

    public OffsetDateTime getOccurredAt() {
        return occurredAt;
    }

    public void setOccurredAt(OffsetDateTime occurredAt) {
        this.occurredAt = occurredAt;
    }
}
```

Trong pattern trên, `XXX` biểu diễn offset dạng `+07:00` hoặc `Z`.

Một số lưu ý:

- Pattern cần phù hợp kiểu Java và định dạng mà bên gửi thực sự dùng.
- `LocalDateTime` không có offset; thêm pattern hoặc timezone không tự làm cho nó trở thành một Instant.
- `OffsetDateTime` giữ offset, nhưng không tự giữ tên vùng.
- Với `ZonedDateTime`, nếu cần ZoneId, hãy kiểm soát rõ cách ghi zone ID; có thể dùng `WRITE_DATES_WITH_ZONE_ID` hoặc một hợp đồng trường riêng.
- Không dùng timezone mặc định của máy chủ làm quy tắc nghiệp vụ ngầm.

Nếu cần dùng timezone trong `@JsonFormat`, hãy xác định rõ liệu muốn chuyển đổi một thời điểm sang timezone hiển thị hay chỉ parse một local date-time theo timezone quy ước. Hai thao tác có ý nghĩa khác nhau.

## 11. Mất thông tin khi chuyển đổi và lưu trữ

Bảng dưới đây tóm tắt một số thao tác thường gặp:

| Thao tác | Instant có được giữ? | Offset gốc? | ZoneId gốc? |
|---|---|---|---|
| `ZonedDateTime.toInstant()` | Có | Không | Không |
| `ZonedDateTime.toOffsetDateTime()` | Có | Có | Không |
| `ZonedDateTime.toLocalDateTime()` | Không còn xác định được | Không | Không |
| Serialize `ZonedDateTime` chỉ với offset | Có thể giữ | Có | Có thể mất |
| Serialize `ZonedDateTime` kèm ZoneId | Có | Có | Có |
| Lưu `Instant` cùng ZoneId riêng | Có | Có thể lưu riêng nếu cần | Có |

Không phải mọi mất mát đều là lỗi. Nếu hệ thống chỉ cần sắp xếp sự kiện, Instant thường đủ. Nếu hệ thống phải tái hiện chính xác giờ địa phương và vùng nguồn, cần giữ thêm offset/ZoneId.

Điều quan trọng là quyết định dựa trên nghiệp vụ và ghi rõ trong schema/API.

## 12. Lựa chọn kiểu theo mục đích

| Nhu cầu | Kiểu nên cân nhắc | Lý do |
|---|---|---|
| Timestamp tạo bản ghi, log, audit | `Instant` | Một mốc tuyệt đối, dễ đồng bộ |
| API cần giữ offset do client gửi | `OffsetDateTime` | Giữ ngày giờ cùng offset |
| Lịch hẹn theo vùng địa lý và DST | `ZonedDateTime` hoặc `LocalDateTime` + `ZoneId` | Giữ ngữ cảnh giờ địa phương và quy tắc vùng |
| Ngày sinh, ngày hóa đơn, ngày nghỉ | `LocalDate` | Không cần thời điểm hay múi giờ |
| Giờ mở cửa hàng ngày | `LocalTime` + `ZoneId` riêng nếu cần | Là giờ trên đồng hồ, có thể lặp theo lịch |
| Sự kiện cần giữ cả thời điểm và vùng người gửi | `Instant` + `ZoneId`/offset metadata | Tách thời điểm tuyệt đối khỏi ngữ cảnh nguồn |

Một mô hình lưu trữ có thể cần nhiều trường hơn một kiểu ngày giờ duy nhất. Ví dụ, một cuộc họp có thể lưu Instant để đồng bộ lịch, đồng thời lưu ZoneId để hiển thị theo vùng mà người tạo đã chọn.

## 13. Kiểm thử round-trip và kiểm tra mất thông tin

Đừng chỉ kiểm tra rằng JSON parse thành công. Hãy kiểm tra đúng thông tin nghiệp vụ cần được bảo toàn.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;

class ZonedDateTimeSerializationTest {
    private final ObjectMapper mapper = createMapper();

    @Test
    void preservesInstantAndZoneId() throws Exception {
        ZonedDateTime original = ZonedDateTime.of(
            2026, 11, 12, 10, 0, 0, 0,
            ZoneId.of("Europe/Paris")
        );

        String json = mapper.writeValueAsString(original);

        ZonedDateTime restored =
            mapper.readValue(json, ZonedDateTime.class);

        assertEquals(original.toInstant(), restored.toInstant());
        assertEquals(original.getOffset(), restored.getOffset());
        assertEquals(original.getZone(), restored.getZone());
    }

    private static ObjectMapper createMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID)
            .build();
    }
}
```

Nếu nghiệp vụ chỉ cần Instant, test nên xác nhận `toInstant()` bằng nhau. Nếu cần giữ offset, so sánh `getOffset()`. Nếu cần giữ vùng, so sánh `getZone()`. Mỗi assertion kiểm tra một loại thông tin khác nhau.

Với dữ liệu có DST, nên có test cho:

- Ngày nằm trong thời gian chuẩn.
- Ngày nằm trong thời gian mùa hè.
- Local time rơi vào DST gap.
- Local time rơi vào DST overlap.
- Round-trip qua JSON khi có ZoneId.
- Hành vi khi timezone database thay đổi giữa các lần triển khai nếu lịch tương lai là dữ liệu quan trọng.

## 14. Các lỗi thường gặp

**Dùng LocalDateTime cho timestamp sự kiện.** Giá trị không có offset hoặc zone nên không xác định được thời điểm tuyệt đối. Dùng Instant hoặc kiểu có offset nếu cần đồng bộ.

**Cho rằng offset là ZoneId.** `+01:00` không cho biết vùng nào đã tạo ra offset đó. Lưu ZoneId riêng nếu cần quy tắc vùng.

**Serialize ZonedDateTime nhưng quên ZoneId.** Nếu đầu ra chỉ có offset, khi đọc lại có thể giữ Instant nhưng mất region zone. Bật `WRITE_DATES_WITH_ZONE_ID` hoặc lưu ZoneId riêng.

**Dùng timestamp số mà không ghi đơn vị.** Seconds và milliseconds khác nhau 1.000 lần. Thống nhất đơn vị trong hợp đồng.

**Dùng timezone mặc định của máy chủ.** Kết quả có thể thay đổi giữa môi trường local, staging và production. Dùng ZoneId rõ ràng.

**Coi giờ địa phương luôn xác định một thời điểm duy nhất.** DST có thể tạo gap hoặc overlap. Dùng ZoneRules để kiểm tra khi nghiệp vụ yêu cầu chính xác.

**Chỉ test chuỗi JSON mà không test ý nghĩa thời gian.** Một chuỗi có thể parse được nhưng đã mất ZoneId hoặc offset. Kiểm tra Instant, offset và ZoneId riêng biệt.

## 15. Ghi nhớ

- `Instant` giữ thời điểm tuyệt đối, nhưng không giữ offset hoặc ZoneId gốc.
- `OffsetDateTime` giữ ngày giờ cùng offset, nhưng không giữ quy tắc của một vùng địa lý.
- `ZonedDateTime` giữ ngày giờ, offset và ZoneId trong Java.
- `LocalDateTime` chỉ giữ giờ địa phương; không thể xác định Instant nếu thiếu vùng hoặc offset.
- Dùng `JavaTimeModule` cho các kiểu Java Time và tắt `WRITE_DATES_AS_TIMESTAMPS` nếu hợp đồng chọn chuỗi ISO.
- Bật `WRITE_DATES_WITH_ZONE_ID` hoặc lưu ZoneId thành trường riêng khi cần giữ vùng thời gian.
- Offset không thay thế ZoneId; DST có thể tạo giờ không tồn tại hoặc xuất hiện hai lần.
- Với sự kiện đã xảy ra, ưu tiên Instant; với lịch tương lai theo giờ địa phương, giữ LocalDateTime và ZoneId theo ý nghĩa nghiệp vụ.
- Kiểm thử round-trip riêng cho Instant, offset và ZoneId để biết chính xác thông tin nào còn được bảo toàn.

