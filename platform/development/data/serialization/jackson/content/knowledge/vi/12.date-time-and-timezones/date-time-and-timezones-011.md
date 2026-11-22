# Quản lý thay đổi định dạng thời gian giữa các phiên bản API

Ngày giờ là một phần của hợp đồng dữ liệu, không chỉ là kiểu thuộc tính trong Java. Một API có thể trả thời điểm dưới dạng chuỗi ISO-8601, timestamp epoch, ngày không có giờ hoặc ngày giờ kèm múi giờ. Khi định dạng thay đổi giữa các phiên bản API, client có thể parse sai, hiểu nhầm múi giờ, mất độ chính xác hoặc diễn giải cùng một giá trị thành một thời điểm khác.

Với Jackson, việc chuyển kiểu Java sang JSON và ngược lại có thể được cấu hình bằng Java Time module, annotation, serializer/deserializer và DTO riêng theo phiên bản. Tuy nhiên, Jackson chỉ thực hiện quy tắc mapping đã được cấu hình. Nó không tự quyết định ý nghĩa nghiệp vụ của một thời điểm, không thể suy ra múi giờ còn thiếu và không thể bảo đảm một thay đổi định dạng là tương thích với mọi client.

Muốn quản lý thay đổi an toàn, trước hết phải xác định dữ liệu đang biểu diễn **một thời điểm tuyệt đối**, **ngày giờ địa phương**, **ngày lịch**, hay **thời gian gắn với một vùng địa lý**. Sau đó mới chọn kiểu Java, format JSON và chiến lược versioning tương ứng.

## 1. Định dạng thời gian là một phần của API contract

Giả sử một API trả về trường:

```json
{
  "eventTime": "2026-11-12T09:30:00"
}
```

Chuỗi trên có ngày và giờ nhưng không có offset hoặc timezone. Client không thể biết đó là 09:30 ở Thành phố Hồ Chí Minh, UTC hay một múi giờ khác. Nếu server âm thầm đổi chuỗi thành:

```json
{
  "eventTime": "2026-11-12T02:30:00Z"
}
```

thì ý nghĩa của trường đã thay đổi: chuỗi mới xác định một thời điểm UTC, còn chuỗi cũ chỉ biểu diễn giờ địa phương chưa xác định. Đây không đơn thuần là thay đổi dấu phân cách hay cách hiển thị.

Một hợp đồng thời gian cần quy định ít nhất:

| Thành phần | Câu hỏi cần chốt |
|---|---|
| Ý nghĩa | Đây là instant, local date-time, ngày lịch hay lịch hẹn theo vùng? |
| Kiểu JSON | Chuỗi, số epoch hay cấu trúc object? |
| Format | ISO-8601 nào, pattern cụ thể nào, có phần giây thập phân không? |
| Múi giờ | UTC, offset cố định hay timezone có tên như Asia/Ho_Chi_Minh? |
| Độ chính xác | Giây, mili giây, micro giây hay nano giây? |
| Giá trị thiếu/null | Field có bắt buộc không; null có nghĩa gì? |
| Phạm vi hợp lệ | Có chấp nhận offset nào, năm nào, giá trị ngoài giới hạn nào? |
| Tương thích | Client cũ có đọc được format mới không; server mới có tiếp tục nhận format cũ không? |

Không nên thay đổi format chỉ vì một format khác dễ đọc hơn. Nếu thay đổi ảnh hưởng đến ý nghĩa hoặc khả năng parse của client, hãy xem đó là thay đổi hợp đồng và lập kế hoạch versioning.

## 2. Chọn kiểu Java theo ngữ nghĩa thời gian

Trước khi chọn format JSON, cần chọn kiểu Java đúng. Những kiểu trong java.time không thể thay thế tùy tiện cho nhau.

| Kiểu Java | Biểu diễn | Có xác định một instant duy nhất không? | Ví dụ |
|---|---|---:|---|
| Instant | Điểm trên timeline UTC | Có | Thời điểm một sự kiện xảy ra. |
| OffsetDateTime | Ngày giờ cùng UTC offset | Có | 2026-11-12T09:30:00+07:00. |
| ZonedDateTime | Ngày giờ cùng timezone ID | Có, sau khi áp dụng quy tắc vùng | Lịch chạy tại Asia/Ho_Chi_Minh. |
| LocalDateTime | Ngày và giờ địa phương, không offset | Không | 09:30 ngày 12/11 trên đồng hồ địa phương. |
| LocalDate | Ngày lịch, không có giờ | Không phải instant | Ngày sinh, ngày hóa đơn. |
| LocalTime | Giờ trong ngày, không có ngày | Không phải instant | Giờ mở cửa. |
| Duration | Khoảng thời gian theo giây/nanosecond | Không phải thời điểm | Thời gian xử lý 15 phút. |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | Không phải thời điểm | Thời hạn một tháng. |

### 2.1. Instant và OffsetDateTime

Nếu trường biểu diễn thời điểm sự kiện xảy ra, Instant thường là kiểu phù hợp. Nó lưu thời điểm trên timeline và không mang timezone hiển thị của người dùng.

OffsetDateTime lưu ngày giờ cùng offset. Ví dụ 2026-11-12T09:30:00+07:00 và 2026-11-12T02:30:00Z biểu diễn cùng một instant nhưng giữ cách biểu diễn offset khác nhau.

```java
Instant instant = Instant.parse("2026-11-12T02:30:00Z");

OffsetDateTime localOffset = OffsetDateTime.parse(
    "2026-11-12T09:30:00+07:00"
);

System.out.println(instant.equals(localOffset.toInstant())); // true
```

Nếu API cần bảo toàn offset mà client gửi lên, OffsetDateTime có thể phù hợp hơn Instant. Nếu API chỉ cần xác định thời điểm tuyệt đối và quy ước đầu ra là UTC, Instant làm rõ ý định.

### 2.2. ZonedDateTime và timezone ID

Offset như +07:00 chỉ cho biết chênh lệch so với UTC tại một thời điểm. Nó không lưu quy tắc lịch sử hoặc quy tắc DST của một vùng địa lý.

ZonedDateTime có thể giữ timezone ID như Asia/Ho_Chi_Minh, Europe/Paris hoặc America/New_York. Điều này quan trọng với lịch chạy định kỳ hoặc lịch hẹn cần tuân theo giờ địa phương khi quy tắc DST thay đổi.

Nếu nghiệp vụ cần “09:00 theo giờ địa phương của chi nhánh mỗi ngày”, lưu một LocalTime cùng timezone ID có thể đúng hơn lưu một instant cố định. Nếu nghiệp vụ cần “sự kiện đã xảy ra lúc nào”, lưu instant thường đúng hơn.

### 2.3. LocalDateTime không tự có múi giờ

LocalDateTime phù hợp khi dữ liệu thực sự là ngày giờ trên lịch địa phương và không đại diện một instant. Ví dụ giờ mở cửa 09:00, hoặc một trường nhập liệu chưa được gắn timezone.

Không tự chuyển LocalDateTime thành UTC bằng cách giả định timezone mặc định của server. Cùng một LocalDateTime có thể ánh xạ tới các instant khác nhau ở các vùng khác nhau; một số thời điểm còn có thể không tồn tại hoặc bị lặp khi chuyển giờ mùa hè.

Nếu API hiện tại trả LocalDateTime nhưng client đang hiểu nó như instant, đó là sự mơ hồ của hợp đồng cần được giải quyết bằng tài liệu và migration, không thể sửa chỉ bằng đổi annotation.

## 3. Các dạng JSON thời gian phổ biến

Một thời điểm có thể được biểu diễn theo nhiều cách.

### 3.1. ISO-8601 dạng chuỗi

Đây là cách phổ biến và dễ đọc:

```json
{
  "occurredAt": "2026-11-12T02:30:00Z",
  "localAppointment": "2026-11-12T09:30:00+07:00",
  "businessDate": "2026-11-12"
}
```

Ưu điểm:

- Thể hiện được offset hoặc Z khi trường đại diện instant.
- Dễ đọc khi debug và lưu log.
- Có thể giữ phần giây thập phân với độ chính xác được định nghĩa.
- Tương thích với nhiều thư viện client và ngôn ngữ.

Điểm cần quy định là format cụ thể: có bắt buộc Z không, có cho phép offset khác UTC không, có bắt buộc phần giây không, và số chữ số phần thập phân tối đa là bao nhiêu.

### 3.2. Epoch timestamp dạng số

Một API có thể dùng số mili giây hoặc giây tính từ Unix epoch:

```json
{
  "occurredAtEpochMillis": 1794450600000
}
```

Số epoch cần có quy ước đơn vị rõ ràng. 1794441000 có thể là giây, còn 1794441000000 có thể là mili giây; nếu không ghi đơn vị trong tên field hoặc schema, client dễ nhầm.

Epoch biểu diễn instant, không giữ offset hay timezone ban đầu. Nếu client cần hiển thị theo vùng, client phải chuyển instant sang timezone thích hợp.

### 3.3. Object nhiều thành phần

Một số API chọn cấu trúc object để thể hiện cả thời gian và timezone:

```json
{
  "localDateTime": "2026-11-12T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Cách này có thể hữu ích với lịch hẹn hoặc lịch chạy định kỳ. Tuy nhiên, cần định nghĩa cách xử lý timezone ID không hợp lệ, thời điểm bị lặp hoặc không tồn tại do DST và việc cập nhật tz database.

## 4. Jackson hỗ trợ Java Time như thế nào?

Với Jackson 2.x, các kiểu trong java.time thường được hỗ trợ qua module jackson-datatype-jsr310, cung cấp JavaTimeModule.

Dependency Maven điển hình:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

Nếu dự án dùng BOM của Jackson hoặc framework BOM, để dependency management chọn version tương thích thay vì khai báo version rời rạc.

Đăng ký module:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
```

Trong framework, module có thể được tự động đăng ký qua cơ chế cấu hình của framework. Hãy xác nhận mapper thực tế đã có module thay vì đăng ký nhiều mapper khác nhau với hành vi không đồng nhất.

### 4.1. Chọn dạng chuỗi thay vì timestamp cho Java Time

Một cấu hình thường dùng khi API cần chuỗi ISO:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Feature WRITE_DATES_AS_TIMESTAMPS ảnh hưởng cách serialize các kiểu ngày giờ được module hỗ trợ. Khi tắt feature, các kiểu Java Time thường được ghi dưới dạng chuỗi theo serializer tương ứng. Khi bật, một số kiểu có thể được ghi dưới dạng số hoặc array tùy kiểu và cấu hình.

Không nên dựa vào default của một phiên bản hoặc framework cụ thể. Hãy cấu hình tường minh và kiểm thử JSON thực tế mà API phát ra.

### 4.2. Định dạng theo property bằng JsonFormat

Khi một field có format cụ thể, có thể dùng annotation:

```java
public class EventResponse {
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    private Instant occurredAt;

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd"
    )
    private LocalDate businessDate;
}
```

Với OffsetDateTime, có thể chỉ định pattern có offset:

```java
public class AppointmentResponse {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX"
    )
    private OffsetDateTime startsAt;
}
```

Pattern phải phù hợp với kiểu và hợp đồng. XXX biểu diễn offset dạng Z hoặc +07:00 trong các trường hợp tương ứng. Nếu bỏ phần giây thập phân, dữ liệu có nano/micro/millisecond có thể bị làm tròn hoặc mất tùy serializer/format; hãy quyết định rõ precision trước khi dùng pattern cố định.

JsonFormat không tự bổ sung timezone cho LocalDateTime. Thuộc tính timezone trong annotation có thể ảnh hưởng cách diễn giải/ghi ở một số kiểu và serializer, nhưng không biến một local date-time vốn không có zone thành một instant có ngữ nghĩa đầy đủ. Dùng đúng kiểu Java trước khi cấu hình format.

## 5. Vì sao đổi định dạng có thể phá vỡ client?

Một thay đổi thời gian có thể tác động theo nhiều cách:

| Thay đổi | Rủi ro với client |
|---|---|
| Chuỗi không offset thành chuỗi có Z | Client có thể diễn giải lại timezone hoặc từ chối pattern mới. |
| Offset cụ thể thành UTC Z | Parser cứng có thể yêu cầu dấu +/-HH:mm; logic hiển thị có thể thay đổi. |
| Chuỗi thành epoch number | Client đang gọi parser chuỗi có thể lỗi kiểu dữ liệu. |
| Epoch giây thành epoch mili giây | Client vẫn parse được số nhưng thời điểm sai lệch theo hệ số 1000. |
| Bỏ phần thập phân | Mất precision; hai sự kiện gần nhau có thể trở thành cùng timestamp. |
| Tăng precision | Parser hoặc schema client có thể giới hạn số chữ số. |
| Đổi LocalDateTime thành instant | Cần quy tắc timezone; không thể chuyển đúng nếu dữ liệu cũ không có thông tin vùng. |
| Đổi tên field | Client cũ không tìm thấy field. |
| Đổi null thành field bị bỏ | Client có thể phân biệt khác nhau giữa null và missing. |

Ngay cả khi hai chuỗi biểu diễn cùng instant, chúng vẫn có thể không tương thích với client dùng format cứng. Ngược lại, hai chuỗi có cùng hình thức nhưng thiếu offset có thể bị hiểu thành những instant khác nhau ở hai môi trường.

## 6. Ví dụ thay đổi format giữa API v1 và v2

Giả sử API v1 trả thời điểm dưới dạng ISO-8601 có offset:

```json
{
  "id": "evt-42",
  "occurredAt": "2026-11-12T09:30:00+07:00"
}
```

API v2 chuẩn hóa thời điểm về UTC:

```json
{
  "id": "evt-42",
  "occurredAt": "2026-11-12T02:30:00Z"
}
```

Hai giá trị trên biểu diễn cùng instant. Tuy nhiên, thay đổi vẫn cần được đánh giá theo cách client parse:

- Client dùng ISO parser tổng quát có thể chấp nhận cả offset +07:00 và Z.
- Client yêu cầu đúng chuỗi có +07:00 có thể từ chối Z.
- Client hiển thị nguyên chuỗi thay vì chuyển timezone có thể cho người dùng thấy khác biệt.
- Client dùng LocalDateTime có thể bỏ hoặc không xử lý offset đúng.

DTO riêng theo version làm rõ hợp đồng:

```java
public record EventV1Response(
    String id,
    OffsetDateTime occurredAt
) {}

public record EventV2Response(
    String id,
    Instant occurredAt
) {}
```

Mapper cho cả hai version nên được cấu hình rõ ràng. Nếu serializer của OffsetDateTime giữ offset và serializer Instant ghi UTC, hai DTO thể hiện ý định khác nhau ngay trong kiểu Java.

```text
Domain event (Instant)
        |
        +--> API v1 mapper --> V1 DTO / offset format
        |
        +--> API v2 mapper --> V2 DTO / UTC format
```

Nếu domain chỉ lưu Instant, muốn trả lại offset ban đầu của client thì cần lưu thêm offset hoặc timezone metadata. Không thể khôi phục offset gốc chỉ từ Instant.

## 7. Chiến lược versioning cho thay đổi format

Có nhiều cách version API. Chọn một cách nhất quán với hệ thống hiện tại; đừng thay đổi format âm thầm trong cùng một hợp đồng đang được client sử dụng.

### 7.1. Version theo path

Ví dụ:

```text
GET /api/v1/events/evt-42
GET /api/v2/events/evt-42
```

Mỗi version có DTO và quy tắc thời gian riêng. Ưu điểm là routing, tài liệu và quan sát rõ ràng. Nhược điểm là phải duy trì nhiều phiên bản trong giai đoạn chuyển đổi.

### 7.2. Version qua media type hoặc header

Ví dụ:

```http
Accept: application/vnd.example.event-v1+json
```

hoặc:

```http
Accept: application/vnd.example.event-v2+json
```

Server chọn representation theo media type. Cách này giữ URL ổn định nhưng yêu cầu client và gateway xử lý header chính xác, đồng thời cần tài liệu rõ về content negotiation.

### 7.3. Thêm field mới trong cùng version

Nếu có thể giữ nguyên semantics field cũ, một giai đoạn chuyển tiếp có thể bổ sung field mới:

```json
{
  "id": "evt-42",
  "occurredAt": "2026-11-12T09:30:00",
  "occurredAtUtc": "2026-11-12T02:30:00Z"
}
```

Đây chỉ là ví dụ minh họa. Nếu occurredAt cũ không có timezone, server không được tự tạo occurredAtUtc bằng một timezone ngầm không được công bố. Phải có quy tắc xác định timezone từ dữ liệu hoặc từ hợp đồng. Nếu không thể xác định, hãy trả lỗi/đánh dấu dữ liệu chưa xác định hoặc version hóa representation.

Khi thêm field:

1. Công bố field mới và ý nghĩa chính xác.
2. Giữ field cũ trong thời gian tương thích.
3. Hướng dẫn client chuyển sang field mới.
4. Theo dõi mức sử dụng field cũ nếu có telemetry phù hợp.
5. Chỉ loại bỏ field cũ trong một version/breaking release đã công bố.

### 7.4. Không đổi kiểu JSON của field hiện tại một cách âm thầm

Đổi từ:

```json
{ "occurredAt": "2026-11-12T02:30:00Z" }
```

sang:

```json
{ "occurredAt": 1794450600000 }
```

là thay đổi kiểu JSON string thành number. Client có schema, model hoặc parser cố định có thể lỗi ngay. Nếu cần epoch, cân nhắc field mới có tên thể hiện đơn vị như occurredAtEpochMillis hoặc tạo version representation mới.

## 8. Giữ backward compatibility khi nhận dữ liệu thời gian

Chiều đọc thường có thể linh hoạt hơn chiều ghi. Server mới có thể tiếp tục nhận format cũ trong giai đoạn migration, đồng thời phát format mới cho API version mới.

Ví dụ, một endpoint legacy chấp nhận chuỗi ISO có offset:

```java
OffsetDateTime parseLegacyOffset(String value) {
    return OffsetDateTime.parse(value);
}
```

Nếu chuỗi cũ là LocalDateTime không có offset, không thể gọi OffsetDateTime.parse và mong Java tự đoán timezone. Cần nhận thêm timezone từ field/header/cấu hình đã được hợp đồng định nghĩa:

```java
Instant toInstant(LocalDateTime local, ZoneId zone) {
    return local.atZone(zone).toInstant();
}
```

Phải quyết định rõ cách xử lý thời điểm DST bị gap hoặc overlap. LocalDateTime.atZone có quy tắc mặc định để giải quyết một số trường hợp; nếu nghiệp vụ cần từ chối thời điểm mơ hồ, hãy kiểm tra ZoneRules.getValidOffsets(local) và xử lý rõ ràng.

### 8.1. Dùng custom deserializer khi cần nhiều format đầu vào

Nếu một field cần nhận hai format legacy và format mới trong giai đoạn chuyển đổi, có thể viết deserializer chuyên biệt. Ví dụ sau chấp nhận ISO offset date-time trước, sau đó thử format local cũ với timezone được quy định rõ:

```java
public final class EventTimeDeserializer
        extends JsonDeserializer<Instant> {

    private final ZoneId legacyZone = ZoneId.of("Asia/Ho_Chi_Minh");

    @Override
    public Instant deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String text = parser.getValueAsString();
        if (text == null) {
            return (Instant) context.handleUnexpectedToken(
                Instant.class, parser
            );
        }

        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (DateTimeParseException offsetFailure) {
            try {
                LocalDateTime local = LocalDateTime.parse(
                    text, DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
                );
                return local.atZone(legacyZone).toInstant();
            } catch (DateTimeParseException legacyFailure) {
                legacyFailure.addSuppressed(offsetFailure);
                return (Instant) context.handleWeirdStringValue(
                    Instant.class,
                    text,
                    "Expected an offset date-time or the documented legacy local format"
                );
            }
        }
    }
}
```

Đăng ký cho một DTO:

```java
public class EventRequest {
    @JsonDeserialize(using = EventTimeDeserializer.class)
    private Instant occurredAt;
}
```

Ví dụ này giả định timezone legacy đã được xác định bằng hợp đồng. Trong ứng dụng thực tế, không nên hard-code Asia/Ho_Chi_Minh nếu các nguồn legacy có timezone khác nhau. Khi timezone thay đổi theo tenant hoặc request, truyền nó qua context có phạm vi rõ ràng hoặc chuyển đổi ở service layer.

### 8.2. Chỉ linh hoạt ở chiều đọc, giữ output ổn định

Một chiến lược migration hữu ích:

- Input parser chấp nhận format cũ và mới trong thời hạn chuyển đổi.
- Output serializer của version API chỉ phát một format chuẩn.
- Log/metric ghi nhận format cũ đang được sử dụng.
- Tài liệu chỉ rõ ngày kết thúc hỗ trợ format legacy.

Không nên để serializer phát format khác nhau tùy theo dữ liệu đầu vào nếu API cần representation ổn định. Nếu cần giữ offset gốc, hãy mô hình hóa offset như dữ liệu có chủ đích thay vì để hành vi ngẫu nhiên của parser quyết định.

## 9. Serializer riêng cho API version

Khi API v1 và v2 có format đầu ra khác nhau, DTO riêng thường dễ hiểu hơn một serializer toàn cục có nhiều nhánh điều kiện.

Ví dụ v1 trả OffsetDateTime, v2 trả Instant:

```java
public record EventV1Response(
    String id,
    OffsetDateTime occurredAt
) {}

public record EventV2Response(
    String id,
    Instant occurredAt
) {}

public EventV1Response toV1(Event event, ZoneOffset publicOffset) {
    OffsetDateTime value = event.occurredAt().atOffset(publicOffset);
    return new EventV1Response(event.id(), value);
}

public EventV2Response toV2(Event event) {
    return new EventV2Response(event.id(), event.occurredAt());
}
```

Ở đây publicOffset phải đến từ hợp đồng API hoặc cấu hình được công bố, không lấy tùy tiện từ timezone mặc định của máy chủ.

Nếu format cần cố định chính xác, cấu hình mapper/reader/writer theo version:

```java
ObjectMapper apiMapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectWriter v1Writer = apiMapper.writerFor(EventV1Response.class);
ObjectWriter v2Writer = apiMapper.writerFor(EventV2Response.class);
```

Nếu cùng một kiểu Java cần được serialize theo hai format khác nhau, có thể dùng hai DTO representation hoặc hai writer với cấu hình riêng. Tránh thay đổi cấu hình ObjectMapper dùng chung giữa các request để chọn format version; điều đó tạo race condition và làm output phụ thuộc thứ tự request.

## 10. Precision và rounding khi đổi format

Thời gian có thể lưu nano giây trong Java Instant, nhưng API hoặc database có thể chỉ giữ mili giây hoặc giây. Thay đổi format thường kéo theo thay đổi precision.

Ví dụ:

```text
2026-11-12T02:30:00Z
2026-11-12T02:30:00.123Z
2026-11-12T02:30:00.123456789Z
```

Ba chuỗi có độ chính xác biểu diễn khác nhau. Nếu v1 chỉ trả giây, v2 trả nano giây, client mới có thêm thông tin nhưng client cũ có thể không parse được hoặc không giữ được precision khi round-trip.

Khi thiết kế:

- Xác định precision được lưu ở database và domain model.
- Xác định precision public API cam kết.
- Không giả định client sẽ giữ được nano giây chỉ vì JSON có nhiều chữ số.
- Nếu cần giảm precision, quy định truncation hay rounding.
- Không dùng số epoch mà không công bố đơn vị và precision.

Ví dụ truncate về mili giây trước khi phát API:

```java
Instant apiValue = eventTime.truncatedTo(ChronoUnit.MILLIS);
```

Truncate và round là hai hành vi khác nhau. Nếu cần round, hãy định nghĩa quy tắc riêng và kiểm thử giá trị ở ranh giới. Đừng để một pattern JsonFormat vô tình làm mất dữ liệu mà không có chủ đích.

## 11. Timezone, offset và DST khi migration

Một trong những lỗi nguy hiểm nhất là thay đổi timezone mặc định mà không thay đổi tên field hoặc version API.

### 11.1. Offset không phải timezone

Offset +07:00 là một giá trị offset. Asia/Ho_Chi_Minh là timezone ID có bộ quy tắc vùng. Với các khu vực có DST, offset có thể thay đổi theo ngày. Một offset đơn lẻ không đủ để tái tạo mọi quy tắc tương lai hoặc lịch sử của một vùng.

### 11.2. Local time có thể mơ hồ

Ở vùng có DST, khi đồng hồ lùi lại, một giờ địa phương có thể xuất hiện hai lần. Khi đồng hồ tiến lên, một khoảng giờ địa phương có thể không tồn tại. Nếu API nhận LocalDateTime và ZoneId, cần quy định:

- Từ chối thời gian không hợp lệ?
- Chọn offset sớm hơn hay muộn hơn khi thời gian xuất hiện hai lần?
- Tự điều chỉnh thời gian bị gap hay trả lỗi validation?

Không để các lựa chọn này phụ thuộc ngầm vào implementation hoặc phiên bản timezone database.

### 11.3. Lưu instant và timezone khi cần cả hai

Một lịch hẹn có thể cần cả instant để thực thi và timezone để hiển thị:

```json
{
  "startsAt": "2026-11-12T02:30:00Z",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Instant trả lời “sự kiện xảy ra lúc nào trên timeline”; timezone trả lời “hiển thị theo quy tắc vùng nào”. Nếu người dùng thay đổi timezone hoặc quy tắc vùng được cập nhật, ứng dụng vẫn có thể xác định semantics đã chọn.

## 12. Xử lý field cũ, field mới và null

Khi version API thay đổi, không chỉ format string thay đổi. Field có thể bị đổi tên, thêm mới hoặc bỏ đi. Cần định nghĩa hành vi với:

| Payload | Câu hỏi cần trả lời |
|---|---|
| Field thời gian bị thiếu | Dùng default, giữ giá trị cũ hay báo lỗi? |
| Field có null | Có nghĩa xóa, chưa biết hay không áp dụng? |
| Field là chuỗi rỗng | Có bị từ chối hay xem như thiếu? |
| Field có format cũ | Có tiếp tục nhận trong thời gian migration? |
| Field có format mới | Version cũ có từ chối hay bỏ qua? |
| Cả field cũ và mới cùng xuất hiện | Field nào có ưu tiên; có kiểm tra chúng tương đương không? |

Nếu tạm thời phát cả hai field:

```json
{
  "occurredAtLegacy": "2026-11-12T09:30:00+07:00",
  "occurredAt": "2026-11-12T02:30:00Z"
}
```

Server nên bảo đảm hai field biểu diễn cùng instant. Nếu client gửi cả hai trong request và chúng mâu thuẫn, trả lỗi rõ ràng thay vì chọn một field âm thầm. Nếu field mới là nguồn chuẩn, tài liệu phải công bố thứ tự ưu tiên và thời điểm field cũ bị ngừng hỗ trợ.

## 13. Migration theo giai đoạn

Một kế hoạch migration có thể chia thành các giai đoạn:

### Giai đoạn 1: Kiểm kê và định nghĩa hợp đồng

1. Tìm mọi endpoint/message dùng ngày giờ.
2. Ghi lại kiểu Java, format JSON thực tế và timezone đang áp dụng.
3. Phân loại từng field là instant, local date-time, date, time hay duration.
4. Kiểm tra client hiện có parse format theo ISO tổng quát hay pattern cứng.
5. Xác định precision và hành vi null/missing.

### Giai đoạn 2: Bổ sung khả năng tương thích ở server

1. Thêm parser nhận format mới và format cũ nếu có thể xác định semantics an toàn.
2. Tạo DTO hoặc reader riêng cho version mới.
3. Chuẩn hóa output của từng API version.
4. Thêm metric/log không chứa dữ liệu nhạy cảm để nhận biết client còn gửi format cũ.
5. Viết test cho payload cũ, mới và trường hợp mơ hồ.

### Giai đoạn 3: Chuyển client

1. Công bố format mới và ví dụ parse cho từng ngôn ngữ client.
2. Phát hành client SDK có hỗ trợ format mới.
3. Chuyển client theo nhóm và theo dõi lỗi parse.
4. Giữ thời gian chuyển tiếp đủ dài theo vòng đời phát hành của client.

### Giai đoạn 4: Ngừng format cũ

1. Xác nhận không còn client hợp lệ dùng format cũ hoặc đã có ngoại lệ được phê duyệt.
2. Công bố thời điểm loại bỏ.
3. Loại bỏ parser legacy và field cũ trong version API phù hợp.
4. Giữ test hợp đồng cho version vẫn được hỗ trợ.

Nếu thay đổi là breaking change, nên tạo version API mới hoặc một cơ chế version representation đã có trong hệ thống. Không nên dựa vào việc đa số client parse được để âm thầm đổi hợp đồng.

## 14. Kiểm thử hợp đồng thời gian

Test cần kiểm tra cả giá trị Java sau deserialize và JSON thực tế sau serialize. Chỉ test object-to-object không đủ để xác nhận format public.

### 14.1. Test round-trip ISO offset

```java
@Test
void readsAndWritesOffsetDateTime() throws Exception {
    ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    String json = """
        {"occurredAt":"2026-11-12T09:30:00+07:00"}
        """;

    EventV1Response event =
        mapper.readValue(json, EventV1Response.class);

    assertEquals(
        OffsetDateTime.parse("2026-11-12T09:30:00+07:00"),
        event.occurredAt()
    );

    String output = mapper.writeValueAsString(event);
    JsonNode tree = mapper.readTree(output);
    assertEquals(
        "2026-11-12T09:30:00+07:00",
        tree.path("occurredAt").asText()
    );
}
```

Nếu API cam kết offset gốc được giữ nguyên, assertion cần kiểm tra chính chuỗi offset. Nếu API chỉ cam kết instant, so sánh toInstant() và không phụ thuộc representation offset.

### 14.2. Test cùng instant ở hai offset

```java
@Test
void differentOffsetsCanRepresentSameInstant() {
    OffsetDateTime local =
        OffsetDateTime.parse("2026-11-12T09:30:00+07:00");
    OffsetDateTime utc =
        OffsetDateTime.parse("2026-11-12T02:30:00Z");

    assertEquals(local.toInstant(), utc.toInstant());
}
```

Test này ngăn việc so sánh chuỗi khi nghiệp vụ cần so sánh thời điểm tuyệt đối.

### 14.3. Test precision

```java
@Test
void apiPrecisionIsMilliseconds() {
    Instant source = Instant.parse("2026-11-12T02:30:00.123456789Z");
    Instant apiValue = source.truncatedTo(ChronoUnit.MILLIS);

    assertEquals(
        Instant.parse("2026-11-12T02:30:00.123Z"),
        apiValue
    );
}
```

### 14.4. Test local time và timezone

```java
@Test
void convertsLocalDateTimeUsingDocumentedZone() {
    LocalDateTime local =
        LocalDateTime.parse("2026-11-12T09:30:00");
    ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

    Instant actual = local.atZone(zone).toInstant();

    assertEquals(
        Instant.parse("2026-11-12T02:30:00Z"),
        actual
    );
}
```

Nếu API nhận vùng có DST, bổ sung test cho gap/overlap theo quy tắc nghiệp vụ. Không chỉ test một ngày mùa đông hoặc mùa hè.

### 14.5. Test compatibility matrix

| Server | Client | Điều cần xác nhận |
|---|---|---|
| v1 | client v1 | Format cũ vẫn hoạt động trong thời gian hỗ trợ. |
| v2 | client v2 | Format mới được parse đúng. |
| v2 nhận request cũ | client v1 | Parser legacy hoạt động nếu đã cam kết tương thích. |
| v1 nhận request mới | client v2 | Có lỗi rõ ràng hoặc fallback được công bố; không đoán format. |
| v2 output cho client v1 | client v1 | Chỉ thực hiện nếu format mới đã được chứng minh tương thích. |

Kiểm thử thêm:

- Z, offset dương và offset âm.
- Timestamp có/không có phần giây thập phân.
- Mili giây và nano giây.
- Ngày cuối tháng, năm nhuận và ranh giới ngày.
- LocalDate không có timezone.
- Field thiếu, null và chuỗi rỗng.
- Giá trị ngoài range hoặc format không hợp lệ.
- Timezone ID không tồn tại.
- DST gap/overlap ở vùng có DST.

## 15. Tài liệu hóa format cho client

Mỗi field thời gian nên có mô tả đủ cụ thể để client không phải suy luận.

Ví dụ tài liệu cho occurredAt trong API v2:

```yaml
occurredAt:
  type: string
  format: date-time
  description: >
    Thời điểm sự kiện theo UTC. Giá trị được trả dưới dạng ISO-8601
    với hậu tố Z. Độ chính xác tối đa là mili giây.
  example: "2026-11-12T02:30:00.123Z"
```

Nếu dùng epoch:

```yaml
occurredAtEpochMillis:
  type: integer
  format: int64
  description: >
    Số mili giây kể từ Unix epoch UTC (1970-01-01T00:00:00Z).
  example: 1794450600123
```

Format date-time trong OpenAPI thường biểu diễn RFC 3339 date-time. Hãy kiểm tra công cụ sinh client có hỗ trợ đúng kiểu offset/precision cần thiết không; schema chỉ là một phần của hợp đồng, ví dụ và mô tả timezone vẫn cần rõ ràng.

## 16. Những lỗi thiết kế nên tránh

**Dùng LocalDateTime cho một sự kiện tuyệt đối.** Không có offset hoặc timezone thì không xác định được instant. Chọn Instant hoặc OffsetDateTime khi cần thời điểm tuyệt đối.

**Dùng timezone mặc định của server để chuyển dữ liệu cũ.** Môi trường triển khai có thể khác timezone; kết quả chuyển đổi sẽ thay đổi giữa máy dev, CI và production.

**Đổi epoch seconds thành milliseconds mà giữ nguyên tên field.** JSON vẫn là number nên client có thể không báo lỗi nhưng thời điểm sẽ sai rất xa.

**Đổi format string trong cùng API version mà không kiểm tra client.** Parser cứng hoặc SDK cũ có thể ngừng hoạt động.

**Cho phép nhiều format nhưng không quy định ưu tiên.** Client có thể gửi field cũ và mới mâu thuẫn; server không nên âm thầm chọn một giá trị.

**Dùng JsonFormat để giải quyết thiếu timezone.** Annotation định dạng không thể khôi phục thông tin timezone chưa từng được gửi.

**Dùng một ObjectMapper mutable cho nhiều version.** Thay đổi cấu hình giữa request có thể tạo output không ổn định; dùng DTO/reader/writer riêng hoặc mapper đã cấu hình cố định.

**Bỏ precision mà không công bố.** Client có thể dựa vào độ chính xác để sắp xếp hoặc khử trùng lặp sự kiện.

## 17. Checklist quyết định trước khi thay đổi format

- [ ] Đã xác định field là instant, local date-time, date, time hay duration.
- [ ] Đã chọn kiểu Java phù hợp (Instant, OffsetDateTime, ZonedDateTime, LocalDateTime, ...).
- [ ] Đã quy định JSON string hay number và format cụ thể.
- [ ] Nếu dùng epoch, đã ghi rõ giây/mili giây và precision.
- [ ] Đã xác định timezone/offset và cách xử lý DST.
- [ ] Đã xác định precision, rounding/truncation và range.
- [ ] Đã định nghĩa hành vi field thiếu, null và chuỗi rỗng.
- [ ] Đã kiểm tra client hiện tại và SDK có parser format cứng hay không.
- [ ] Đã chọn versioning path/header hoặc chiến lược field bổ sung.
- [ ] Đã tạo DTO/serializer riêng nếu các version có representation khác nhau.
- [ ] Đã cấu hình JavaTimeModule và mapper một cách tường minh.
- [ ] Đã viết test serialize, deserialize, round-trip và compatibility matrix.
- [ ] Đã tài liệu hóa ví dụ input/output và kế hoạch ngừng format cũ.

## 18. Nguyên tắc cốt lõi

Thay đổi định dạng thời gian giữa các phiên bản API cần bắt đầu từ ngữ nghĩa dữ liệu. Một instant, một giờ địa phương và một ngày lịch là ba khái niệm khác nhau; đổi kiểu Java hoặc format JSON mà không phân biệt chúng có thể làm thay đổi thời điểm thực tế.

Hãy dùng kiểu java.time phù hợp, cấu hình JavaTimeModule và format Jackson tường minh, duy trì DTO/representation riêng khi API versions có hợp đồng khác nhau, và chỉ chuyển đổi local time khi timezone đã được xác định. Trong giai đoạn migration, server có thể nhận format cũ và mới nếu có quy tắc chuyển đổi rõ ràng, nhưng output của từng API version nên ổn định. Test cả precision, offset, timezone, null/missing và client cũ trước khi loại bỏ format legacy.
