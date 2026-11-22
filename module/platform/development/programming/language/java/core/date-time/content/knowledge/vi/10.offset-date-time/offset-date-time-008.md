# Lựa chọn dữ liệu có offset khi trao đổi qua giao thức trong Java

## 1. Vấn đề cần giải quyết

Khi ứng dụng Java gửi và nhận ngày giờ qua HTTP/JSON, message queue, gRPC hoặc một hợp đồng dữ liệu khác, câu hỏi đầu tiên không phải là “dùng chuỗi định dạng nào?” mà là **thông tin thời gian nào bên nhận phải tái tạo được**:

1. **Một thời điểm tuyệt đối** trên dòng thời gian (ví dụ một đơn hàng được tạo đúng lúc nào).
2. **Ngày giờ địa phương kèm độ lệch UTC** tại nơi phát sinh sự kiện (ví dụ hóa đơn ghi `09:30 +07:00`).
3. **Quy tắc múi giờ của một khu vực** để tính giờ địa phương trong tương lai (ví dụ cuộc họp hằng tuần lúc 09:30 tại `Europe/Paris`).
4. **Một ngày hoặc giờ dân sự** không gắn với thời điểm tuyệt đối (ví dụ ngày sinh, giờ mở cửa cố định).

Đối với chủ đề *ngày giờ có offset*, kiểu quan trọng là **`OffsetDateTime`**: nó chứa ngày, giờ địa phương và `ZoneOffset`, ví dụ `2026-07-01T09:30:15+07:00`. Giá trị đó xác định được một `Instant` vì offset cho biết giờ địa phương chênh bao nhiêu so với UTC.

**Offset không phải múi giờ khu vực.** `+07:00` là chênh lệch cố định so với UTC; `Asia/Ho_Chi_Minh` là định danh vùng với quy tắc do cơ sở dữ liệu múi giờ cung cấp. Hai thông tin có mục đích khác nhau, nên lựa chọn dữ liệu giao thức phải xuất phát từ yêu cầu nghiệp vụ.

## 2. Phân biệt các kiểu `java.time`

| Kiểu | Chứa gì? | Có xác định được thời điểm UTC không? | Khi nên dùng |
| --- | --- | --- | --- |
| `Instant` | Mốc trên dòng thời gian UTC, không gắn cách hiển thị địa phương | **Có** | Audit log, `createdAt`, `updatedAt`, timestamp sự kiện, thứ tự xử lý |
| `OffsetDateTime` | Ngày + giờ + offset UTC cụ thể | **Có** | API cần truyền cả thời điểm và offset được biểu diễn ở phía nguồn |
| `ZonedDateTime` | Ngày + giờ + offset + `ZoneId` vùng | **Có** | Lập lịch/hiển thị theo quy tắc khu vực, dữ liệu phụ thuộc DST |
| `LocalDateTime` | Ngày + giờ, không offset và không vùng | **Không** | Giá trị giờ địa phương thuần túy khi hợp đồng cung cấp vùng ở trường khác |
| `LocalDate` | Ngày lịch | **Không** | Sinh nhật, ngày nghỉ, hạn theo ngày |
| `LocalTime` | Giờ trong một ngày | **Không** | Giờ mở cửa, thời điểm lặp lại trong ngày |
| `OffsetTime` | Giờ trong ngày + offset nhưng **không có ngày** | Không xác định đủ một `Instant` nếu thiếu ngày | Ít dùng; giao thức thực sự định nghĩa giờ có offset mà không cần ngày |

Ví dụ `2026-07-01T09:30:15+07:00` và `2026-07-01T02:30:15Z` có **giờ đồng hồ và offset khác nhau nhưng cùng một mốc thời gian**.

Nếu API chỉ cần một timestamp duy nhất, `Instant` cùng chuỗi UTC thường rõ nghĩa và dễ chuẩn hóa. Nếu phía nhận còn cần biết sự kiện đã được biểu diễn bằng offset nào ở phía gửi, `OffsetDateTime` phù hợp hơn. Nếu phải biết **khu vực nào** để tuân theo quy tắc đổi giờ trong tương lai, phải truyền thêm `ZoneId`.

## 3. Offset biểu thị điều gì trong dữ liệu gửi đi?

Một giá trị như:

```text
2026-07-01T09:30:15+07:00
```

gồm:

- `2026-07-01`: ngày địa phương.
- `T`: ký tự ngăn ngày và giờ theo biểu diễn ISO 8601.
- `09:30:15`: giờ địa phương.
- `+07:00`: độ lệch `UTC+07:00`, tức đồng hồ địa phương **đi trước UTC bảy giờ**.

Thời điểm UTC tương ứng là `2026-07-01T02:30:15Z`. Ký tự `Z` chỉ offset bằng 0 (`UTC+00:00`). Ví dụ `-04:00` có nghĩa giờ địa phương **chậm hơn UTC bốn giờ**. Để suy ra UTC từ ngày giờ có offset: **lấy giờ địa phương trừ offset**.

Hãy tách biệt ba thông tin:

```text
LocalDateTime  2026-07-01T09:30:15         (không xác định Instant)
OffsetDateTime 2026-07-01T09:30:15+07:00   (xác định Instant)
ZonedDateTime  2026-07-01T09:30:15+07:00[Asia/Ho_Chi_Minh]
                                               (biết thêm ZoneId)
```

Đừng tự ghép `+07:00` vào một `LocalDateTime` chỉ vì máy chủ đặt tại Việt Nam: người dùng và hệ thống đối tác có thể ở bất kỳ khu vực nào.

## 4. Chọn cấu trúc dữ liệu cho hợp đồng API

### Trường hợp A: chỉ cần biểu diễn thời điểm sự kiện

Ví dụ: `createdAt`, `paidAt`, `deliveredAt`. Nên chuẩn hóa thành **UTC timestamp**:

```json
{
  "eventId": "evt-1024",
  "occurredAt": "2026-07-01T02:30:15Z"
}
```

Phía Java tiếp nhận bằng `Instant` khi hợp đồng chỉ cần mốc tuyệt đối. Cách này loại bỏ nguy cơ mỗi máy chủ tự hiểu một `LocalDateTime` theo `ZoneId.systemDefault()`. Khi hiển thị cho người dùng, đổi `Instant` sang vùng người dùng lựa chọn.

### Trường hợp B: cần giữ offset được biểu diễn từ nguồn

Ví dụ: chứng từ, biên bản, dấu giờ người gửi đã xác nhận, hoặc hợp đồng có quy định phải bảo toàn offset. Truyền một chuỗi `OffsetDateTime`:

```json
{
  "transactionId": "tx-42",
  "occurredAt": "2026-07-01T09:30:15+07:00"
}
```

Java phân tích với `OffsetDateTime.parse(...)`. Hệ thống nhận có thể lấy `Instant` chính xác, đồng thời vẫn biết offset gốc là `+07:00`. Nếu chuyển ngay thành UTC rồi chỉ lưu `Instant`, **không thể suy ra offset gốc** từ thời điểm tuyệt đối.

Chỉ bảo toàn offset khi nghiệp vụ có lý do: mọi chuỗi timestamp đều có thể chuẩn hóa UTC để so sánh, nhưng việc chuẩn hóa có thể làm mất thông tin về **cách biểu diễn của nguồn** nếu đó là một yêu cầu lưu trữ.

### Trường hợp C: cần quy tắc giờ theo khu vực

Ví dụ: cuộc họp lúc 09:30 mỗi thứ Hai theo giờ Paris, lịch mở cửa hoặc job chạy theo giờ địa phương. Chỉ có `+01:00` hay `+02:00` sẽ không cho biết cách xử lý DST ở các ngày khác.

Một hợp đồng có thể chuyển **thời điểm đã chốt** cùng với **định danh vùng**:

```json
{
  "startsAt": "2026-07-01T09:30:15+02:00",
  "timeZone": "Europe/Paris"
}
```

Trường `startsAt` xác định thời điểm; `timeZone` cho biết quy tắc vùng. Bên nhận phải kiểm tra chúng **phù hợp nhau** nếu cả hai được xem là dữ liệu có tính ràng buộc. Với lịch lặp lại, còn cần truyền quy tắc lịch (ngày trong tuần, giờ địa phương, cách xử lý DST gap/overlap), bởi một timestamp đơn lẻ không mô tả lịch trong tương lai.

### Trường hợp D: giá trị không phải timestamp

Ví dụ ngày sinh nên dùng `"2000-08-14"` như một `LocalDate`. Nếu tạo `Instant` bằng cách tự giả định nửa đêm UTC, ngày hiển thị có thể biến thành hôm trước khi xem ở múi giờ phía tây UTC. Không thêm offset vào dữ liệu vốn chỉ là một ngày lịch.

## 5. Quy ước định dạng khi trao đổi

Đối với JSON API chung, nên công bố rõ một **tập con tương thích RFC 3339/ISO 8601**, chẳng hạn:

```text
2026-07-01T09:30:15+07:00
2026-07-01T02:30:15Z
2026-07-01T02:30:15.123Z
```

Các thỏa thuận quan trọng:

1. **Bắt buộc offset** đối với trường được định nghĩa là timestamp có offset. Không chấp nhận `2026-07-01T09:30:15` nếu không có quy tắc giải nghĩa rõ ràng.
2. **Khai báo chính sách chuẩn hóa**: ví dụ luôn phát UTC `Z` nhưng chấp nhận cả offset khác zero ở đầu vào, hoặc bảo toàn offset đầu vào nếu cần.
3. **Thống nhất độ chính xác**: giây, mili giây hay nano giây; không giả định đối tác hỗ trợ đầy đủ nano giây. `java.time` có thể giữ nano giây, nhưng database/gateway hoặc ngôn ngữ khác có thể làm tròn/cắt.
4. **Truyền kiểu JSON string** với dạng thời gian có thể đọc được khi ưu tiên tính tương thích. Nếu dùng số epoch, phải ghi rõ **seconds** hay **milliseconds**, không đoán theo độ lớn số.
5. **Không tùy tiện sử dụng tên hoặc viết tắt múi giờ** như `CST`, `PST` để thay offset: nhiều tên viết tắt mơ hồ và phụ thuộc ngữ cảnh. Với lịch theo vùng, dùng IANA `ZoneId` như `America/New_York`.
6. **Phân biệt ràng buộc parser Java và hợp đồng công khai**: `DateTimeFormatter.ISO_OFFSET_DATE_TIME` là formatter ISO cho `OffsetDateTime`; không mặc định mọi chuỗi Java có thể parse đều phù hợp chính xác tập con RFC 3339 mà API đã công bố. Cần validation ở biên giao thức theo hợp đồng.

Ví dụ lỗi hợp đồng:

```json
{
  "occurredAt": "2026-07-01 09:30:15",
  "timeZone": "+07"
}
```

Dữ liệu này gây nhiều cách hiểu vì `occurredAt` thiếu offset, định dạng ngày giờ không được định nghĩa theo hợp đồng trên và trường `timeZone` trộn khái niệm offset với vùng. Một giá trị `ZoneOffset` chỉ nên mang ý nghĩa offset; trường `timeZone` dành cho định danh vùng nếu nghiệp vụ cần.

## 6. Java 17+: nhận, đổi và kiểm tra `OffsetDateTime`

Tạo tệp **`OffsetProtocolDemo.java`**:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public class OffsetProtocolDemo {
    public static void main(String[] args) {
        String payload = "2026-07-01T09:30:15+07:00";

        OffsetDateTime received = OffsetDateTime.parse(
                payload, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        Instant instant = received.toInstant();
        OffsetDateTime utc = received.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime partner = OffsetDateTime.parse(
                "2026-07-01T02:30:15Z");

        System.out.println("Received: " + received);
        System.out.println("Instant: " + instant);
        System.out.println("UTC: " + utc);
        System.out.println("Same instant: " + received.isEqual(partner));
        System.out.println("equals: " + received.equals(partner));

        OffsetDateTime changedMeaning =
                received.withOffsetSameLocal(ZoneOffset.UTC);
        System.out.println("Same local, new offset: " + changedMeaning);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac OffsetProtocolDemo.java
java OffsetProtocolDemo
```

Đầu ra:

```text
Received: 2026-07-01T09:30:15+07:00
Instant: 2026-07-01T02:30:15Z
UTC: 2026-07-01T02:30:15Z
Same instant: true
equals: false
Same local, new offset: 2026-07-01T09:30:15Z
```

Giải thích:

- `toInstant()` biểu diễn đúng mốc tuyệt đối, không kèm offset địa phương của nguồn.
- `withOffsetSameInstant(ZoneOffset.UTC)` **giữ nguyên sự kiện**, đổi giờ đồng hồ từ 09:30:15 xuống 02:30:15 và offset thành `Z`.
- `isEqual(...)` kiểm tra cùng `Instant`, do đó trả `true`.
- `equals(...)` của `OffsetDateTime` còn xét ngày giờ địa phương và offset. Hai đối tượng mang hai biểu diễn khác nhau dù cùng `Instant`, nên kết quả là `false`.
- `withOffsetSameLocal(ZoneOffset.UTC)` giữ giờ đồng hồ **09:30:15** và gắn offset `Z`; điều này đổi `Instant` sang **09:30:15Z**, tức thay đổi thời điểm thực. Không dùng thao tác đó để chuẩn hóa timestamp khi gửi qua giao thức.

Khi so sánh hoặc sắp thứ tự các sự kiện theo thời điểm, ưu tiên `toInstant()` hoặc `isEqual()` theo đúng mục đích. Không lấy kết quả `OffsetDateTime.equals()` làm phép kiểm tra “cùng một sự kiện diễn ra tại cùng một thời điểm”.

## 7. Parse và validate ở ranh giới giao thức

Một API nhận chuỗi ngày giờ nên parse thành kiểu Java **khớp với hợp đồng đã chọn**, rồi mới chuyển sang mô hình lưu trữ. Ví dụ phương thức nhận timestamp có offset:

```java
// Đoạn minh họa; cần import java.time.* và java.time.format.*.
static Instant parseTimestampWithOffset(String value) {
    OffsetDateTime dateTime =
            OffsetDateTime.parse(value, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    return dateTime.toInstant();
}
```

`OffsetDateTime.parse` ném `DateTimeParseException` nếu chuỗi không parse được. Trong API, có thể ánh xạ lỗi này thành phản hồi **400 Bad Request** hoặc lỗi validation tương ứng của giao thức; không nên tự ý thử nhiều định dạng ngầm rồi đoán offset.

Nếu hợp đồng có quy định chặt hơn, chẳng hạn bắt buộc giây, tối đa ba chữ số phần lẻ và cấm offset giây, cần kiểm tra bổ sung bằng validator/formatter riêng hoặc schema trước khi parse. Parse thành công theo Java **không thay thế việc kiểm tra toàn bộ contract**.

Nếu cần bảo toàn offset đầu vào, trả hoặc lưu `OffsetDateTime` gốc. Nếu chỉ cần mốc sự kiện, lưu `Instant`; khi tạo phản hồi, việc chọn `Z` hay offset của người xem là một chính sách hiển thị.

## 8. Đừng trộn epoch timestamp và chuỗi có offset

Một số giao thức dùng số Unix epoch (số giây hoặc mili giây tính từ `1970-01-01T00:00:00Z`). Đây là **thời điểm tuyệt đối**, không mang offset ban đầu:

```java
// Hai dạng có đơn vị khác nhau:
Instant fromSeconds = Instant.ofEpochSecond(epochSeconds);
Instant fromMillis = Instant.ofEpochMilli(epochMilliseconds);
```

Đoạn trên là minh họa, với `epochSeconds` và `epochMilliseconds` là biến `long` được khai báo ở nơi gọi. Chọn sai đơn vị khiến thời điểm sai rất lớn, dù cú pháp vẫn hợp lệ.

Nếu API cần cả timestamp và offset gốc, định nghĩa **hai trường có ý nghĩa rõ ràng** hoặc một chuỗi `OffsetDateTime`, tránh thiết kế gửi một epoch number rồi buộc phía nhận đoán `+07:00` từ địa chỉ IP hay timezone máy chủ.

## 9. Offset và DST: điều gì không thể suy ra từ `+02:00`?

Đây là ranh giới quan trọng khi trao đổi dữ liệu cho lịch hẹn:

- `2026-07-01T09:30:15+02:00` xác định một mốc UTC, **nhưng không chứng minh** địa điểm là Paris, Berlin hay khu vực nào.
- Chỉ `+02:00` không cho biết vào mùa đông khu vực đó sẽ dùng `+01:00` hay tiếp tục `+02:00`.
- `ZoneId.of("Europe/Paris")` cho phép Java áp dụng quy tắc lịch sử và tương lai từ tzdb của JDK, bao gồm DST gap (giờ địa phương bị bỏ qua) và overlap (giờ địa phương bị lặp).
- Một hợp đồng lịch lặp lại phải xử lý những thời điểm địa phương không tồn tại hoặc tồn tại hai lần. `OffsetDateTime` của một sự kiện đã chốt **không tự giải quyết** chính sách đó.

Nếu truyền cả `startsAt` và `timeZone`, cần đặt rõ câu hỏi: khi một offset truyền vào **không hợp lệ** với `ZoneId` tại ngày giờ địa phương tương ứng, bên nhận **báo lỗi** hay ưu tiên thông tin nào? Với hợp đồng yêu cầu chúng đồng nhất, báo lỗi sẽ tránh việc âm thầm đổi thời điểm.

Ví dụ kiểm tra một offset có hợp lệ với vùng tại giờ địa phương đã cho:

```java
// Đoạn minh họa; cần import java.time.*.
static boolean offsetMatchesZone(
        OffsetDateTime dateTime, ZoneId zone) {
    return zone.getRules().isValidOffset(
            dateTime.toLocalDateTime(), dateTime.getOffset());
}
```

Lưu ý: phép kiểm tra này xác định **cặp giờ địa phương + offset có thể xảy ra trong vùng**; nó không có nghĩa offset đó là mã nhận dạng duy nhất của vùng.

## 10. Thiết kế DTO và các điểm cần kiểm tra khi tích hợp

Một DTO Java cho timestamp có offset có thể dùng trực tiếp `OffsetDateTime`:

```java
import java.time.OffsetDateTime;

// Đoạn minh họa DTO bằng record, không chứa hàm main:
public record EventRequest(String eventId, OffsetDateTime occurredAt) {}
```

Trong ứng dụng sử dụng Jackson hoặc một bộ codec khác, việc parse `OffsetDateTime` từ JSON string phụ thuộc **cấu hình serializer/deserializer**, module hỗ trợ Java Time và contract đang dùng. Java SE chỉ cung cấp `java.time`; không giả định rằng tất cả framework đều tự cấu hình JSON serialization giống nhau.

Các điểm cần thống nhất giữa producer và consumer:

1. **Tên, kiểu và ý nghĩa trường**: `occurredAt` là thời điểm UTC, chuỗi có offset hay chỉ local time?
2. **Dạng chuẩn khi gửi và dạng chấp nhận khi nhận**: bắt buộc offset, dùng `Z` cho UTC, có chấp nhận phần giây thập phân không?
3. **Chính sách độ chính xác và làm tròn**: giữ bao nhiêu chữ số phần lẻ khi qua JSON, database và hàng đợi?
4. **Offset gốc có phải dữ liệu nghiệp vụ cần bảo toàn không?** Nếu có, không chỉ lưu `Instant`.
5. **`ZoneId` có cần thiết cho lịch lặp lại hoặc hiển thị theo khu vực không?** Nếu có, truyền một trường riêng được định nghĩa rõ.
6. **Null và giá trị vắng mặt**: trường bắt buộc nên được validate; không thay bằng `now()` hoặc timezone mặc định trừ khi hợp đồng quy định.
7. **Khả năng tương thích đa ngôn ngữ**: kiểm thử producer/consumer khác nền tảng với các offset dương, âm, UTC và mốc đổi ngày.

Ví dụ tài liệu hợp đồng ngắn, rõ nghĩa:

```text
occurredAt: required string, timestamp with UTC offset.
Format: yyyy-MM-dd'T'HH:mm:ss[.fraction](Z|+HH:mm|-HH:mm).
Meaning: an exact instant; received offsets may vary.
Response policy: emit UTC (Z), preserving the same instant.
Fraction policy: up to 3 digits; precision beyond milliseconds rejected.
No timezone inferred from server settings.
```

Dòng trên diễn đạt **quy ước dữ liệu** bằng mô tả, không phải một `DateTimeFormatter` pattern có thể sao chép nguyên văn (dấu ngoặc và ký hiệu tùy chọn có cách hiểu khác nhau giữa các hệ). Phần schema/validator thực tế phải triển khai đúng quy ước này.

## 11. Lỗi thường gặp và cách sửa

| Sai sót | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gửi `LocalDateTime` cho timestamp nhưng không kèm offset/vùng | Consumer tự đoán UTC hoặc múi giờ máy chủ | Dùng `Instant` hoặc `OffsetDateTime`; quy định rõ contract |
| Sửa `+07:00` thành `Z` mà giữ nguyên `09:30` | Thời điểm thực bị lệch 7 giờ | Dùng `withOffsetSameInstant(UTC)` hoặc `toInstant()` |
| Xem offset như `ZoneId` của một thành phố | Không biết quy tắc DST và thay đổi theo mùa | Truyền `ZoneId` riêng nếu bài toán cần vùng |
| Dùng `equals()` để kiểm tra hai biểu diễn có cùng `Instant` | Có thể nhận `false` với cùng sự kiện | Dùng `isEqual()` hoặc so `toInstant()` |
| Gửi epoch number không định nghĩa seconds/milliseconds | Dịch mốc thời gian sai | Nêu rõ đơn vị và kiểm thử ví dụ chuẩn |
| Phụ thuộc `ZoneId.systemDefault()` khi deserialize | Hành vi khác giữa laptop và máy chủ | Dùng offset/vùng trong contract, không suy đoán |
| Giữ timestamp có nano giây rồi qua hệ thống chỉ giữ milli giây | Mất chính xác, có thể đổi thứ tự sát nhau | Thỏa thuận precision và quy tắc cắt/làm tròn |
| Parse “được” là chấp nhận mọi biến thể Java cho HTTP API | Tính tương thích với client khác không được bảo đảm | Giới hạn định dạng/độ dài phần lẻ và validate rõ |

## 12. Tình huống tự kiểm tra

**Câu 1.** Backend nhận `2026-07-01T09:30:15+07:00`, consumer ở UTC muốn biết thời điểm diễn ra. Có cần gửi lại cùng chuỗi có `+07:00` không?

**Đáp án:** Không bắt buộc nếu offset nguồn không có giá trị nghiệp vụ. Có thể chuẩn hóa thành `2026-07-01T02:30:15Z`, giữ nguyên `Instant`. Nếu hợp đồng yêu cầu bảo toàn offset ban đầu, vẫn phải lưu/truyền nó.

**Câu 2.** Hai bên trao đổi lịch 09:00 hằng ngày tại Paris. Có đủ nếu truyền `09:00+02:00`?

**Đáp án:** Không. Một offset cố định không cho biết những ngày Paris chuyển giữa giờ chuẩn và DST. Cần quy tắc lịch, `ZoneId` và chính sách xử lý gap/overlap.

**Câu 3.** `OffsetDateTime.parse("2026-07-01T09:30:15+07:00")` và `OffsetDateTime.parse("2026-07-01T02:30:15Z")` có bằng nhau?

**Đáp án:** `isEqual()` trả `true` vì cùng `Instant`, còn `equals()` trả `false` vì ngày giờ địa phương và offset khác nhau.

**Câu 4.** Hợp đồng API yêu cầu `occurredAt` là timestamp có offset, client gửi `2026-07-01T09:30:15`. Phía server nên tự hiểu theo múi giờ máy chủ?

**Đáp án:** Không. Chuỗi đó không có offset nên không xác định được `Instant` theo hợp đồng; nên trả lỗi validation và yêu cầu client gửi offset rõ ràng.

**Điểm cần nhớ:** Chọn `Instant` khi trao đổi **mốc tuyệt đối**, chọn `OffsetDateTime` khi mốc tuyệt đối còn cần **giữ offset được biểu diễn**, và bổ sung `ZoneId` khi nghiệp vụ phụ thuộc **quy tắc giờ của một khu vực**. Giao thức phải mô tả rõ định dạng, precision, chính sách UTC và cách xử lý dữ liệu thiếu offset.