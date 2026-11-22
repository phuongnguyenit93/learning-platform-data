# Quy ước đặt tên trường, ngày giờ, múi giờ và giá trị null trong JSON

Một HTTP API không chỉ cần trả JSON hợp lệ. **Tên trường**, **ngữ nghĩa của ngày giờ**, **timezone/offset** và **cách biểu diễn null** là những phần của hợp đồng dữ liệu mà frontend, mobile app, hệ thống bên thứ ba và các phiên bản backend phải thống nhất. Một thay đổi tưởng nhỏ — đổi `createdAt` thành `created_at`, xuất timestamp không có múi giờ, hoặc bỏ trường `null` — có thể khiến client hiểu sai mà không sinh lỗi biên dịch ở server.

Bài thuộc nhóm **JSON và codec** của Spring Boot web runtime. Nội dung tập trung vào **naming convention**, **Jackson serialize/deserialize**, **Java Time/ISO-8601**, **UTC và timezone vùng địa lý**, **null so với missing/empty**, validation, PATCH semantics và contract tests. Ví dụ dùng **Spring Boot 3.3.13, Spring Framework 6.1, Jackson 2, Spring MVC, Java 21 và Gradle**. WebFlux áp dụng cùng tư duy về hợp đồng JSON nhưng sử dụng reactive HTTP codecs thay vì đường Servlet MVC.

## 1. Java model và JSON public contract là hai lớp khác nhau

Giả sử Java có:

~~~java
public record EventView(
    String eventId,
    String eventName,
    Instant occurredAt
) {}
~~~

Client có thể yêu cầu JSON:

~~~json
{
  "event_id": "evt-42",
  "event_name": "Hội thảo Java",
  "occurred_at": "2026-11-07T03:04:05Z"
}
~~~

Java record component dùng `camelCase` theo convention Java, trong khi JSON dùng `snake_case`. Để duy trì điều này, ứng dụng phải có **naming strategy hoặc annotation cụ thể**, không nên tự tin rằng Jackson tự biết quy ước công khai.

Đường đi của một request/response JSON trong Spring MVC:

~~~text
HTTP request (Content-Type: application/json)
                 |
                 v
@RequestBody / HttpMessageConverter
                 |
                 v
Jackson ObjectMapper deserialize -> Java DTO
                 |
                 v
Controller / Service / Domain
                 |
                 v
Java response DTO
                 |
                 v
Jackson ObjectMapper serialize
                 |
                 v
HTTP response (Content-Type: application/json)
~~~

Spring WebFlux thường dùng `HttpMessageReader` và `HttpMessageWriter` trong reactive codec chain. Cả hai stack có thể dùng Jackson; đừng gọi nhầm API converter của MVC là API duy nhất cho WebFlux.

**Nguyên tắc:** API DTO là biên giới dữ liệu công khai, còn entity/database/internal model có thể có cấu trúc và tên riêng. Serialize thẳng một JPA entity dễ lộ field nội bộ, dính lazy proxy/circular reference hoặc thay đổi JSON ngoài ý muốn khi chỉnh database schema.

## 2. Chọn và duy trì một quy ước tên trường

| Quy ước | Ví dụ | Nhận xét |
| --- | --- | --- |
| `camelCase` | `eventId`, `occurredAt` | Quen thuộc với JavaScript, Java |
| `snake_case` | `event_id`, `occurred_at` | Phổ biến trong HTTP API, data pipelines |
| `kebab-case` | `event-id`, `occurred-at` | Ít phổ biến hơn ở JSON objects |
| `PascalCase` | `EventId`, `OccurredAt` | Có thể gặp trong API legacy |

Không có một tên chuẩn bắt buộc. Vấn đề chính là **nhất quán, dễ dự đoán và không thay đổi tùy tiện**. Ví dụ một API có `created_at`, `updatedAt` và `lastLogin_time` làm client phải nhớ ba kiểu đặt tên.

Các quy tắc hữu ích:

1. Dùng tên mô tả miền nghiệp vụ: `customer_id`, `payment_status`, `created_at`, `total_amount` thay vì `data1`, `val`.
2. Tên boolean nên có semantics rõ, ví dụ `enabled` hoặc `is_enabled`, chọn một chuẩn nhất quán và test tên getter/record của Jackson.
3. Có quy ước acronym: `api_key`, `url`, `http_status`; trong camelCase là `apiKey`, `httpStatus`. Tránh JavaBean getters bất thường như `getURL()` nếu kết quả naming chưa được kiểm thử.
4. Nếu gửi con số có đơn vị, ghi rõ `timeout_ms`, `duration_seconds`, `amount_minor_units`. Không để client đoán.
5. Với business enums, giữ cách viết giá trị nhất quán (`PENDING` hay `pending`) và tài liệu hóa các values có thể có.
6. Không tái sử dụng tên cũ với nghĩa hoàn toàn mới; cần versioning/migration.
7. Các key JSON phân biệt chữ hoa/chữ thường, vì vậy `eventId` khác `eventID`.

### 2.1. Trường hợp API đã phát hành

Đổi field name có thể là breaking change dù Java backend compile bình thường. Trước khi đổi quy ước:

- Đo client nào đang sử dụng field cũ.
- Thống nhất migration version và deprecation schedule.
- Với input, có thể chấp nhận alias tạm thời.
- Với output, có thể giữ field cũ một thời gian hoặc ra API version mới.
- Có tests so sánh JSON schema/contract, không chỉ controller unit tests.

## 3. Ba cách cấu hình tên JSON fields với Jackson

### 3.1. Global property-naming-strategy

Spring Boot 3.3 hỗ trợ property chính thức `spring.jackson.property-naming-strategy`:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

Khi dùng ObjectMapper do Boot cấu hình, Java property `occurredAt` thường được serialize thành `occurred_at`. Global strategy cũng ảnh hưởng chiều deserialize những DTO phù hợp.

**Lưu ý phạm vi:** custom mapper được tạo riêng bằng `new ObjectMapper()` không nhất thiết nhận cấu hình Boot; một số thư viện có ObjectMapper riêng. Global policy cũng có thể ảnh hưởng nhiều API cùng lúc, nên không áp dụng đột ngột cho hệ thống đang có client production.

### 3.2. @JsonNaming trên một API DTO

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record EventView(
    String eventId,
    String eventName,
    Instant occurredAt
) {}
~~~

Đây là class fragment trong một project có Jackson, không phải chương trình Java chỉ cần JDK. Annotation có phạm vi trên type; vì vậy có thể áp dụng `snake_case` cho từng DTO mà không thay đổi hợp đồng của các API khác.

Nếu input và output cùng dùng `snake_case`, cần khai báo/cấu hình thống nhất cho **cả request DTO và response DTO**. Đừng chỉ sửa output rồi quên request binding.

### 3.3. @JsonProperty và @JsonAlias

Khi field legacy có tên chính xác cần giữ:

~~~java
public record LegacyInput(
    @JsonProperty("event_id")
    @JsonAlias("eventId")
    String eventId
) {}
~~~

Đoạn này cần imports từ `com.fasterxml.jackson.annotation`. `@JsonProperty("event_id")` chọn JSON primary name, còn `@JsonAlias("eventId")` cho phép deserialize giá trị với tên cũ vào cùng field. **Alias dành cho input**; serialize vẫn phát tên chính, không tự phát cả hai key.

Nếu client gửi cả primary name và alias, phải xác định behavior mong muốn; tránh gửi các giá trị xung đột rồi dựa vào thứ tự JSON properties. Khi migration kết thúc, cân nhắc loại alias cũ.

### 3.4. Không nhầm bean property names với Map keys

Naming strategy chủ yếu liên quan tên Java bean/record properties. Với `Map<String,Object>`, key được coi là dữ liệu JSON và thường **không tự được chuyển snake_case** như Java member names. Đừng dùng Map tùy ý thay cho DTO chỉ để “hưởng” naming policy.

## 4. Ngày giờ trong JSON: chọn kiểu Java theo ý nghĩa

JSON không có native date/time type. Chuỗi hoặc số chỉ có nghĩa khi API contract quy định cách diễn giải.

| Java type | Có giờ? | Có offset/zone? | Ví dụ JSON | Thích hợp với |
| --- | --- | --- | --- | --- |
| `LocalDate` | Không | Không | `"2026-11-07"` | Sinh nhật, ngày lịch, hạn theo ngày |
| `LocalTime` | Giờ trong ngày | Không | `"09:30:00"` | Giờ mở cửa định kỳ |
| `LocalDateTime` | Có | **Không** | `"2026-11-07T10:04:05"` | Giờ địa phương, chưa xác định instant |
| `Instant` | Có | Mốc UTC | `"2026-11-07T03:04:05Z"` | Tạo/cập nhật bản ghi, sự kiện, audit |
| `OffsetDateTime` | Có | Offset `+07:00` hoặc `Z` | `"2026-11-07T10:04:05+07:00"` | Thời điểm kèm offset |
| `ZonedDateTime` | Có | IANA ZoneId | Cần quy định rõ format hoặc tách zone field | Lịch, DST, múi giờ vùng địa lý |
| `Duration` | Khoảng | Không | `"PT15M"` hoặc số có unit | Timeout, thời lượng |
| `Period` | Đơn vị ngày/tháng/năm | Không | `"P1M"` | Chu kỳ theo lịch |

Đặc biệt, `LocalDateTime` **không có timezone**. Chuỗi `2026-11-07T10:04:05` không nói đó là giờ UTC hay giờ Việt Nam. Nếu client và server tự gán timezone khác nhau, chúng có thể hiểu lệch nhiều giờ mà cả hai vẫn parse JSON thành công.

### 4.1. Instant cho sự kiện tuyệt đối

Các field `created_at`, `updated_at`, `processed_at` và `expires_at` nên biểu diễn một mốc xác định trên timeline. `Instant` giúp so sánh, tính thời gian và lưu trữ độc lập với timezone mặc định của server.

~~~java
Instant instant = Instant.parse("2026-11-07T03:04:05Z");
~~~

Với Jackson Java Time được cấu hình để viết ISO strings, JSON tương ứng là `"2026-11-07T03:04:05Z"`.

### 4.2. OffsetDateTime biểu diễn cùng instant với cách nhìn khác

~~~text
2026-11-07T03:04:05Z
2026-11-07T10:04:05+07:00
~~~

Hai chuỗi trên có cùng instant. Java có thể kiểm tra bằng `OffsetDateTime.parse(...).toInstant()`. Offset `+07:00` không phải tên IANA zone; nhiều nơi có cùng offset, còn một số khu vực thay đổi offset theo daylight saving time.

### 4.3. LocalDate khác timestamp

Ngày sinh `2026-11-07` là ngày lịch; nếu tự chuyển nó thành midnight UTC rồi hiển thị ở timezone khác, có thể thành ngày hôm trước. Khi business cần một **date-only**, lưu `LocalDate` và serialize `yyyy-MM-dd`, không thêm giờ không có ý nghĩa.

## 5. UTC, IANA timezone và DST

Một mô hình hợp lý:

~~~text
Client: local date/time + IANA zone (khi nghiệp vụ cần)
                  |
                  v
Validate DST gap/overlap hoặc offset policy
                  |
                  v
Resolve ra Instant
                  |
             +----+----+
             |         |
             v         v
     Store/compare   Display via user's ZoneId
       as Instant
~~~

- **UTC** là thang tham chiếu thuận tiện cho giao tiếp giữa services, đặc biệt với timestamps nghiệp vụ.
- **ZoneId** như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` mô tả vùng có quy tắc lịch sử/tương lai.
- **Offset** `+07:00` chỉ là độ lệch so với UTC tại một thời điểm; không mô tả đầy đủ luật chuyển giờ của mọi ngày.
- **DST gap**: có thể tồn tại khoảng local time không có thật khi đồng hồ chuyển tới.
- **DST overlap**: một local time có thể ứng với hai instants khi đồng hồ quay lại.

Ví dụ lịch “09:00 mỗi thứ Hai tại Paris” không nên chỉ lưu offset +01:00 vĩnh viễn. Có thể cần lưu `LocalTime`, quy tắc recurrence và `Europe/Paris`; khi tạo từng occurrence thì resolve thành instant theo timezone rules.

**Không dùng `ZoneId.systemDefault()` để suy đoán timezone của client.** Máy dev có thể chạy Asia/Ho_Chi_Minh, server production ở UTC và cluster ở một nơi khác. Timezone cần đến từ contract, cấu hình nghiệp vụ hoặc preference hợp lệ của người dùng.

## 6. Chuẩn chuỗi ngày giờ nên phát hành

Đối với machine-to-machine JSON:

- Ngày lịch: `yyyy-MM-dd`, ví dụ `"2026-11-07"`.
- Timestamp: ISO-8601 / RFC 3339 có `Z` hoặc offset, ví dụ `"2026-11-07T03:04:05Z"`.
- Giữ quy ước fractional seconds ổn định nếu client có yêu cầu precision; phần `.123`, `.123456` hoặc `.123456789` có độ chính xác khác nhau.
- Tránh định dạng theo locale như `07/11/2026 10:04`: có thể bị đọc nhầm tháng/ngày và thiếu timezone.
- Nếu dùng epoch số, ghi rõ seconds vs milliseconds, ví dụ `timestamp_seconds` hoặc `timestamp_ms`. Chênh đơn vị làm lệch thời gian 1000 lần.
- Không lấy substring 10 ký tự đầu của UTC timestamp để quyết định **ngày theo timezone người dùng**, vì cùng instant có thể rơi vào ngày khác ở vùng khác.
- Nếu API phải giữ độ chính xác nano nhưng database chỉ lưu milliseconds, công bố quy tắc làm tròn/cắt bớt; đừng giả định thông tin không bị mất.

## 7. Jackson và Spring Boot 3.3: serialization cấu hình được

`spring-boot-starter-web` thông thường kéo Jackson qua `spring-boot-starter-json`. Boot tự cấu hình ObjectMapper và hỗ trợ `java.time` khi các Jackson modules tương ứng nằm trên classpath.

Để diễn đạt rõ rằng Java Time objects nên được viết thành ISO strings thay vì timestamp số/mảng:

~~~yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
~~~

Spring Boot 3.3 có các key cấu hình như:

- `spring.jackson.property-naming-strategy`: global Java bean naming.
- `spring.jackson.default-property-inclusion`: inclusion policy khi **serialize response**.
- `spring.jackson.time-zone`: timezone format ở một số quá trình Jackson.
- `spring.jackson.serialization.*` và `spring.jackson.deserialization.*`: các Jackson feature switches.

**Không suy rằng `spring.jackson.time-zone=UTC` biến mọi `LocalDateTime` thành timestamp có timezone.** LocalDateTime bản thân không chứa instant/zone. Một số Java Time serializers/deserializers có quy tắc riêng về việc giữ/điều chỉnh offset; nếu hợp đồng cần instant tuyệt đối, normalize thành `Instant` ở API boundary hoặc xác định chính sách cụ thể và test.

### 7.1. @JsonFormat và @DateTimeFormat không thay thế lẫn nhau

- `@JsonFormat` là Jackson annotation cho JSON serialize/deserialize ở field/type tương ứng.
- `@DateTimeFormat` thường được Spring ConversionService sử dụng khi bind query/path/form parameters; không tự sửa việc parse JSON `@RequestBody`.

Ví dụ fragment query:

~~~java
@GetMapping("/calendar")
public String calendar(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

Khác với fragment Jackson field:

~~~java
public record CalendarView(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate date
) {}
~~~

Cả hai cần imports phù hợp, chưa phải chương trình Java độc lập. Chỉ dùng pattern tùy chỉnh khi contract có yêu cầu; các kiểu `LocalDate` và `Instant` thường đã có ISO representation phù hợp.

## 8. Phân biệt null, missing và giá trị rỗng

Các JSON shapes:

~~~json
{}
~~~

~~~json
{"note":null}
~~~

~~~json
{"note":""}
~~~

~~~json
{"note":"Đã ghi"}
~~~

~~~json
{"tags":[]}
~~~

| Biểu diễn | Điều client/server có thể hiểu | Không nên tự đồng nhất với |
| --- | --- | --- |
| Thiếu `note` | Không cung cấp, chưa biết hoặc không cập nhật | `null` |
| `"note":null` | Không có giá trị hoặc lệnh xóa tùy PATCH contract | Chuỗi rỗng |
| `"note":""` | Chuỗi rỗng được cung cấp | Thiếu key |
| `"note":"A"` | Có nội dung | — |
| `"tags":[]` | Danh sách hiện hữu nhưng rỗng | Missing hoặc null |
| `"enabled":false` | Giá trị false rõ ràng | Không cung cấp |
| `"count":0` | Số 0 rõ ràng | Không cung cấp |

Ý nghĩa chính xác thuộc hợp đồng API. Nếu một trường null có nghĩa “chưa biết”, nó khác với collection rỗng có nghĩa “đã biết không có phần tử”.

### 8.1. Response null và input null là hai chiều

- **Serialization**: Java null có được ghi JSON key với value null hay bị lược bỏ?
- **Deserialization**: request thiếu key, explicit null hoặc chuỗi rỗng có được bind giống nhau hay không?
- **Business semantics**: với POST/PUT/PATCH, các trường hợp này có phải xóa/giữ nguyên/đặt default hay báo lỗi?

Đổi một JSON inclusion policy chỉ điều chỉnh **cách phát response**, không thiết kế hết logic cập nhật dữ liệu.

## 9. @JsonInclude và global default-property-inclusion

Jackson có các mode phổ biến:

| Mode | Ý nghĩa |
| --- | --- |
| `ALWAYS` | Ghi property kể cả null khi serializer hỗ trợ |
| `NON_NULL` | Bỏ key khi Java value là null |
| `NON_EMPTY` | Có thể bỏ null, chuỗi rỗng, collection/map rỗng theo định nghĩa “empty” của Jackson |
| `NON_ABSENT` | Bỏ null và các trạng thái absent của một số reference types được hỗ trợ |
| `NON_DEFAULT` | Lược bỏ giá trị default theo các quy tắc Jackson; cần kiểm tra cẩn thận |

Ví dụ:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EventView(String eventId, String note) {}
~~~

Đối tượng `new EventView("evt-42", null)` có JSON thông thường:

~~~json
{"eventId":"evt-42"}
~~~

Với `ALWAYS`, có thể là:

~~~json
{"eventId":"evt-42","note":null}
~~~

Nếu muốn áp dụng chung, Spring Boot 3.3 hỗ trợ key `spring.jackson.default-property-inclusion`:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
~~~

Đây là **policy toàn ObjectMapper phù hợp**, có thể ảnh hưởng nhiều endpoints; trên API đã phát hành cần review breaking changes.

**Tránh lạm dụng NON_EMPTY**: một field `items: []` có thể là trạng thái hợp lệ, rõ ràng hơn field missing. `false` và `0` cũng thường là dữ liệu quan trọng; không được biến thành missing do heuristic nghiệp vụ không rõ.

## 10. Deserialization: thiếu key không luôn gây lỗi

Ví dụ record:

~~~java
public record EventInput(
    String eventName,
    OffsetDateTime scheduledAt,
    String note
) {}
~~~

Trong những cấu hình Jackson thông dụng, **missing `note`** và **explicit JSON `"note":null`** đều có thể thành Java `note == null`. Một record Java không tự suy ra field là required về nghiệp vụ; `@JsonProperty(required=true)` cũng có ngữ nghĩa phụ thuộc creator/deserializer và không nên thay validation.

Hãy dùng starter validation khi cần:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

~~~java
public record EventInput(
    @NotBlank String eventName,
    @NotNull OffsetDateTime scheduledAt,
    String note
) {}
~~~

Trong controller dùng `@Valid @RequestBody EventInput input`. Khi request có tên rỗng hoặc thiếu/đặt null cho `scheduledAt`, Bean Validation sẽ từ chối theo điều kiện tương ứng, thường là HTTP 400.

Cần nhớ:

- `@NotBlank` không cho null, chuỗi rỗng hoặc chỉ có whitespace.
- `@NotNull` yêu cầu đối tượng khác null.
- Một chuỗi timestamp sai format có thể gây lỗi **đọc JSON** trước validation.
- Nếu dùng primitive `int`/`boolean` cho trường optional, nhiều cách bind có thể khiến thiếu key thành `0`/`false`, làm mất dấu “client không gửi”; dùng wrapper và presence tracking khi cần.
- \`@JsonSetter(nulls=Nulls.FAIL)\` và các chế độ SKIP/AS_EMPTY có thể tùy biến explicit null, nhưng không thay thế mô hình dữ liệu rõ semantics.

## 11. PATCH: absent khác explicit null

Đối với cập nhật một phần:

~~~json
{"display_name":"An"}
~~~

có thể nghĩa là cập nhật một field và giữ nguyên field khác; trong khi:

~~~json
{"display_name":null}
~~~

có thể có nghĩa xóa, thiết lập null hoặc không hợp lệ. **Phải định nghĩa contract**, không để framework tự đoán.

Với **JSON Merge Patch (RFC 7396)**, null member có ý nghĩa loại bỏ member; media type là `application/merge-patch+json`. Với **JSON Patch (RFC 6902)**, request là mảng operations khác biệt, thường có media type `application/json-patch+json`. Một endpoint JSON thông thường **không tự thực thi RFC 7396** chỉ vì dùng HTTP PATCH.

Nếu cần phân biệt missing/explicit null trước nghiệp vụ, đọc qua Jackson `JsonNode`:

~~~java
JsonNode note = json.path("note");

if (note.isMissingNode()) {
    // không có key
} else if (note.isNull()) {
    // có key với JSON null
} else if (note.isTextual() && note.asText().isEmpty()) {
    // chuỗi rỗng
}
~~~

`json.path("note")` trả `MissingNode` cho key vắng mặt; còn `json.get("note")` trả Java null khi key không có và `NullNode` khi JSON null. Đoạn trên là fragment dùng trong method có một `JsonNode json` hợp lệ.

Đừng tự viết PATCH bằng cách bind mọi trường vào một DTO mà không biết chúng có được client gửi hay không, rồi set tất cả trường null đè lên dữ liệu hiện tại.

## 12. OpenAPI: required và nullable là hai thuộc tính riêng

Một field có thể:

1. **Required, non-null**: key luôn có, value phải có kiểu hợp lệ.
2. **Required, nullable**: key luôn có, value có thể null.
3. **Optional, non-null when present**: key có thể thiếu, nhưng nếu xuất hiện thì không được null.
4. **Optional, nullable**: key có thể thiếu, nếu có có thể null.

Ví dụ đoạn OpenAPI 3.1/JSON Schema:

~~~yaml
type: object
required:
  - event_id
  - occurred_at
properties:
  event_id:
    type: string
  occurred_at:
    type: string
    format: date-time
  note:
    type:
      - string
      - "null"
~~~

Đây chỉ là phần schema, không phải OpenAPI document độc lập. Key `note` không nằm trong `required` nên có thể vắng mặt; nếu xuất hiện, schema ví dụ cho phép string hoặc null. Không dùng từ “optional” chung chung mà bỏ qua câu hỏi null có hợp lệ không.

## 13. Java độc lập: hai biểu diễn cùng một Instant

Ví dụ chỉ cần **JDK 17+**, không phụ thuộc Spring/Jackson.

**TimeContractDemo.java**

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimeContractDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-11-07T03:04:05Z");
        OffsetDateTime local =
            OffsetDateTime.parse("2026-11-07T10:04:05+07:00");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime displayed = instant.atZone(zone);
        LocalDate date = LocalDate.of(2026, 11, 7);

        System.out.println("Same instant: " +
            instant.equals(local.toInstant()));
        System.out.println("UTC: " + instant);
        System.out.println("Vietnam: " + displayed.toLocalDateTime());
        System.out.println("Calendar date: " + date);
    }
}
~~~

Chạy:

~~~bash
javac TimeContractDemo.java
java TimeContractDemo
~~~

Stdout kỳ vọng chính xác:

~~~text
Same instant: true
UTC: 2026-11-07T03:04:05Z
Vietnam: 2026-11-07T10:04:05
Calendar date: 2026-11-07
~~~

`toLocalDateTime()` trong ví dụ chỉ phục vụ chứng minh cách hiển thị đồng hồ theo vùng, **không** phải gợi ý biến timestamp API thành LocalDateTime thiếu timezone.

## 14. Project Spring Boot runnable: naming, date-time và null

Dự án nhỏ chứng minh:

- Java record components `camelCase` được xuất/nhận JSON `snake_case`.
- `Instant` được viết ra ISO string UTC, input `OffsetDateTime` có offset được chuẩn hóa bằng `toInstant()`.
- `LocalDate` diễn đạt ngày lịch; `zone_id` là field tường minh cho nghiệp vụ cần.
- `@JsonInclude(NON_NULL)` khiến key vắng mặt; `ALWAYS` giữ explicit null.
- `JsonNode` phân biệt absent/null/empty.
- Validation từ chối tên rỗng và timestamp null.

Cấu trúc:

~~~text
json-contract-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/jsoncontract/
    │   │   ├── JsonContractApplication.java
    │   │   └── JsonContractController.java
    │   └── resources/application.yml
    └── test/java/com/example/jsoncontract/
        └── JsonContractControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'json-contract-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/jsoncontract/JsonContractApplication.java**

~~~java
package com.example.jsoncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
~~~

Đây là cấu hình serialize thời gian; ví dụ không bật naming/inclusion toàn hệ thống vì dùng annotations trên DTO cụ thể.

### 14.1. Controller và DTO đầy đủ

**src/main/java/com/example/jsoncontract/JsonContractController.java**

~~~java
package com.example.jsoncontract;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/json")
public class JsonContractController {

    private static final Instant FIXED_INSTANT =
        Instant.parse("2026-11-07T03:04:05Z");

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record EventView(
        String eventId,
        String eventName,
        Instant occurredAt,
        Instant scheduledAt,
        LocalDate eventDate,
        String zoneId,
        String note
    ) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record CreateEventRequest(
        @NotBlank String eventName,
        @NotNull OffsetDateTime scheduledAt,
        String note
    ) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record NullDemo(
        String note,
        String emptyText,
        List<String> emptyTags
    ) {}

    @GetMapping(path = "/example",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public EventView example() {
        return new EventView(
            "evt-42", "Hội thảo Java",
            FIXED_INSTANT, FIXED_INSTANT,
            LocalDate.of(2026, 11, 7),
            "Asia/Ho_Chi_Minh", null
        );
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public EventView echo(@Valid @RequestBody CreateEventRequest request) {
        // Chỉ echo/normalize input; không ghi database.
        return new EventView(
            "evt-echo", request.eventName(),
            FIXED_INSTANT, request.scheduledAt().toInstant(),
            LocalDate.of(2026, 11, 7),
            "Asia/Ho_Chi_Minh", request.note()
        );
    }

    @GetMapping(path = "/null-policy",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public NullDemo nullPolicy() {
        return new NullDemo(null, "", List.of());
    }

    @PostMapping(path = "/inspect-note",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> inspectNote(@RequestBody JsonNode json) {
        JsonNode note = json.path("note");

        if (note.isMissingNode()) {
            return Map.of("state", "absent");
        }
        if (note.isNull()) {
            return Map.of("state", "null");
        }
        if (note.isTextual() && note.asText().isEmpty()) {
            return Map.of("state", "empty-string");
        }
        if (note.isTextual()) {
            return Map.of("state", "value", "value", note.asText());
        }
        return Map.of("state", "unsupported-type");
    }
}
~~~

Những điểm cần đọc kỹ:

- `@JsonNaming` được khai báo trên cả `EventView` và `CreateEventRequest`, giúp đồng bộ quy ước input/output.
- `EventView` có `NON_NULL` nên `note == null` **không xuất hiện** trong JSON. `NullDemo` có `ALWAYS` nên JSON có key `note` với value null.
- `scheduledAt` input có offset: controller chuẩn hóa qua `toInstant()` rồi mới xuất `Instant`, tránh giả định Jackson giữ nguyên dạng offset string qua mọi config.
- `zoneId` là một field tường minh; nó không tự đến từ server timezone.
- `FIXED_INSTANT` phục vụ kiểm thử. Production nên dùng `Clock` được inject và thời gian thực, không hard-code thời điểm.
- `inspectNote` chỉ phân loại, không triển khai JSON Merge Patch hay ghi persistent state.

### 14.2. Khởi chạy và xác minh thủ công

Với JDK 21 và Gradle 8.5+ phù hợp, tại thư mục project:

~~~bash
./gradlew bootRun
~~~

Nếu project chưa có wrapper nhưng có Gradle cài sẵn, tạo wrapper:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Mặc định ứng dụng sẽ phục vụ trên cổng 8080 nếu không có override.

GET ví dụ:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/json/example
~~~

Body dự kiến; thứ tự keys không được đảm bảo:

~~~json
{
  "event_id": "evt-42",
  "event_name": "Hội thảo Java",
  "occurred_at": "2026-11-07T03:04:05Z",
  "scheduled_at": "2026-11-07T03:04:05Z",
  "event_date": "2026-11-07",
  "zone_id": "Asia/Ho_Chi_Minh"
}
~~~

Không có key `note` trong JSON do `NON_NULL`.

POST với thời điểm có offset:

~~~bash
curl -i -X POST http://localhost:8080/api/json/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "event_name":"Meeting",
    "scheduled_at":"2026-11-07T10:04:05+07:00",
    "note":null
  }'
~~~

Kỳ vọng HTTP 200 và dữ liệu chứa:

~~~json
{
  "event_id": "evt-echo",
  "event_name": "Meeting",
  "occurred_at": "2026-11-07T03:04:05Z",
  "scheduled_at": "2026-11-07T03:04:05Z",
  "event_date": "2026-11-07",
  "zone_id": "Asia/Ho_Chi_Minh"
}
~~~

Input `10:04:05+07:00` được chuẩn hóa thành `03:04:05Z` mà không làm đổi instant. Mục đích của POST là echo, không phải tạo resource nên demo trả 200 thay vì tự tuyên bố 201 Created.

### 14.3. Kiểm tra null, empty và missing

~~~bash
curl -s http://localhost:8080/api/json/null-policy
~~~

Kết quả JSON:

~~~json
{"note":null,"empty_text":"","empty_tags":[]}
~~~

Thử các trường hợp input:

~~~bash
curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":null}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":""}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":"hello"}'
~~~

Bốn body theo thứ tự:

~~~json
{"state":"absent"}
~~~

~~~json
{"state":"null"}
~~~

~~~json
{"state":"empty-string"}
~~~

~~~json
{"state":"value","value":"hello"}
~~~

Không so sánh JSON response bằng raw string nếu không cần thiết; JSON object keys có thể đổi thứ tự.

## 15. Test API contract bằng MockMvc và JsonNode

**src/test/java/com/example/jsoncontract/JsonContractControllerTest.java**

~~~java
package com.example.jsoncontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(JsonContractController.class)
class JsonContractControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void snakeCaseDateAndOmittedNullAreStable() throws Exception {
        MvcResult result = mvc.perform(get("/api/json/example")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.event_id").value("evt-42"))
            .andExpect(jsonPath("$.occurred_at")
                .value("2026-11-07T03:04:05Z"))
            .andExpect(jsonPath("$.event_date")
                .value("2026-11-07"))
            .andExpect(jsonPath("$.zone_id")
                .value("Asia/Ho_Chi_Minh"))
            .andReturn();

        JsonNode body = mapper.readTree(
            result.getResponse().getContentAsString());
        assertFalse(body.has("note"));
        assertFalse(body.has("eventId"));
        assertTrue(body.has("event_id"));
    }

    @Test
    void offsetInputIsNormalizedToUtcInstant() throws Exception {
        mvc.perform(post("/api/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "event_name": "Meeting",
                      "scheduled_at": "2026-11-07T10:04:05+07:00",
                      "note": null
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.event_name").value("Meeting"))
            .andExpect(jsonPath("$.scheduled_at")
                .value("2026-11-07T03:04:05Z"));
    }

    @Test
    void blankNameAndNullInstantAreInvalid() throws Exception {
        mvc.perform(post("/api/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"event_name":"","scheduled_at":null}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void nullAndEmptyValuesRemainDifferent() throws Exception {
        MvcResult result = mvc.perform(get("/api/json/null-policy"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
            result.getResponse().getContentAsString());

        assertTrue(body.has("note"));
        assertTrue(body.get("note").isNull());
        assertEquals("", body.get("empty_text").asText());
        assertTrue(body.get("empty_tags").isArray());
        assertEquals(0, body.get("empty_tags").size());
    }

    @Test
    void missingNullAndEmptyAreDifferentRequestStates() throws Exception {
        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("absent"));

        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"note\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("null"));

        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"note\":\"\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("empty-string"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các assertions kiểm tra JSON field names, UTC timestamps, validation và **presence** của key, thay vì chỉ xem response status. `@WebMvcTest` sử dụng MVC test slice mà không mở socket Tomcat thật. Ví dụ code/test đã được rà soát kỹ thuật bằng đọc nguồn; chỉ tuyên bố “đã chạy thành công” khi Gradle thật sự chạy và trả kết quả.

## 16. Những lỗi JSON date/null thường gặp

### 16.1. Xuất LocalDateTime nhưng gọi đó là UTC

`"2026-11-07T10:04:05"` không có offset. Nếu máy A hiểu là UTC, máy B hiểu là +07:00, dữ liệu sẽ lệch giờ. API timestamps nên xuất `Instant` hoặc chuỗi có offset theo contract.

### 16.2. Dựa vào timezone mặc định server

`ZoneId.systemDefault()` phụ thuộc JVM/container; dev và production có thể khác. Chọn timezone từ domain/config hoặc từ preference đã xác minh.

### 16.3. Lấy ngày UTC làm ngày người dùng

Một instant gần midnight UTC có thể thuộc ngày kế tiếp ở Việt Nam hoặc ngày hôm trước tại các vùng khác. Để hiển thị ngày local, convert instant sang `ZoneId` trước khi lấy LocalDate.

### 16.4. Nghĩ offset +07:00 là một timezone vùng

Offset không chứa DST lịch sử/tương lai. Lịch hẹn tương lai cần `ZoneId` và chính sách xử lý DST gap/overlap.

### 16.5. Dùng @DateTimeFormat cho @RequestBody JSON

JSON converter do Jackson xử lý, còn `@DateTimeFormat` thường liên quan ConversionService cho query/path/form. Cần kiểm tra ObjectMapper, JavaTime module và DTO type.

### 16.6. Bật NON_NULL toàn API mà không review

Một số clients phân biệt null với missing. Đổi `default-property-inclusion` có thể phá vỡ behavior dù payload nhìn ngắn hơn.

### 16.7. Đồng nhất [] với null

Collection rỗng thường có nghĩa “đã biết là không có phần tử”; null có thể có nghĩa “chưa biết/chưa tải”. Định nghĩa trước và test.

### 16.8. Dùng primitive cho field optional

`false` hoặc `0` có thể bị coi là default khi input missing. Nếu cần phân biệt, dùng wrapper/presence tracking và validation đúng.

### 16.9. Chỉ dùng @JsonProperty(required=true)

Không thay thế `@Valid`/`@NotNull` và kiểm thử ở HTTP boundary; các hình thức creator/bind có semantics riêng.

### 16.10. Dùng JsonInclude thay cho PATCH semantics

Inclusion ảnh hưởng serialization; PATCH cần biết key missing, key null và chính sách cập nhật riêng, có thể dùng JsonNode hoặc JsonNullable/custom DTO.

### 16.11. Đổi naming strategy đột ngột

Chuyển camelCase sang snake_case có thể thay toàn bộ wire keys. Đây là thay đổi contract cần version, migration và test client.

### 16.12. Serialize JPA entity trực tiếp

Có nguy cơ lộ dữ liệu nhạy cảm, vòng tham chiếu hoặc lazy proxies; hãy sử dụng API DTO có kiểm soát.

### 16.13. JSON number cho tiền tệ

`double` có sai số nhị phân; với tiền/decimal cần `BigDecimal` hoặc minor units, ghi rõ currency, unit và precision. Không coi `null` như số `0` nếu nghiệp vụ phân biệt hai trạng thái.

### 16.14. String date phụ thuộc locale

Chuỗi `07/11/2026` mơ hồ tháng/ngày giữa nhiều khu vực; dùng ISO formats và localize chỉ tại UI.

## 17. Checklist trước khi phát hành API JSON

1. JSON public dùng camelCase hay snake_case, có ngoại lệ không?
2. Naming nằm ở global `spring.jackson.property-naming-strategy`, `@JsonNaming` hay `@JsonProperty`?
3. Input/output DTO được kiểm thử cùng convention chưa?
4. Có ai đang serialize entity hoặc dữ liệu nhạy cảm thẳng ra response không?
5. `created_at`/`updated_at` được biểu diễn bằng `Instant`/offset-bearing timestamp chưa?
6. `LocalDate` chỉ là ngày lịch, không bị tự đổi sang UTC midnight chứ?
7. Các timestamps đều có `Z`/offset, precision và epoch units rõ chưa?
8. Khi nghiệp vụ cần timezone vùng, có IANA `ZoneId` và DST policy chưa?
9. Có phụ thuộc JVM default timezone hoặc locale không?
10. Jackson JavaTime config và `write-dates-as-timestamps=false` đã có contract tests chưa?
11. `spring.jackson.time-zone` có đang bị hiểu sai là thêm zone cho LocalDateTime không?
12. Required/nullable/optional đã được phân biệt trong OpenAPI chưa?
13. Null, missing, `""`, `[]`, `false` và `0` có semantics rõ không?
14. Global hoặc per-type `NON_NULL`/`NON_EMPTY` có làm mất dữ liệu client cần không?
15. Nếu PATCH, có phân biệt absent với explicit null theo contract/media type không?
16. `@Valid` cùng `@NotBlank`/`@NotNull` được bật và test chưa?
17. Nếu đổi tên trường, có migration/versioning và consumer contract tests chưa?
18. Các test đã có timezone offset khác UTC, invalid timestamp, gần midnight và DST chưa?
19. JSON tests so sánh theo parsed fields thay vì thứ tự object keys chứ?
20. Có tài liệu chính thức cho field names, date/time format, null policy và compatibility chưa?

**Kết luận:** JSON trong Spring Boot là một **hợp đồng dữ liệu**. Quy ước tên trường cần ổn định và nhất quán; `Instant` với ISO-8601/UTC phù hợp cho mốc thời gian tuyệt đối, `LocalDate` phù hợp cho ngày lịch và `ZoneId` cần được bảo toàn nếu nghiệp vụ liên quan giờ theo vùng. Quan trọng nhất, **field vắng mặt, explicit null và các giá trị rỗng** không mặc nhiên là một; `@JsonInclude` chỉ quyết định cách serialization, còn request validation/PATCH semantics cần thiết kế riêng. Hãy tài liệu hóa chúng và bảo vệ bằng contract tests.

## Tài liệu tham khảo

- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson auto-configuration, ObjectMapper và custom serializers.
- [Spring Boot 3.3 — JSON application properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jackson.property-naming-strategy`, `spring.jackson.default-property-inclusion`, serialization và timezone.
- [Spring Framework — MVC HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): chuyển đổi JSON HTTP body.
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339): định dạng timestamp có offset.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): null trong merge patch.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902): JSON patch operations.
