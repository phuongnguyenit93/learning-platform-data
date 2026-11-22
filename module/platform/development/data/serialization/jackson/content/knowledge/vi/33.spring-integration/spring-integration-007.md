# Kiểm soát định dạng ngày giờ, tên trường và chính sách null

Khi Jackson được tích hợp vào Spring, JSON request và response trở thành một phần của API contract. Contract đó không chỉ quy định tên class Java hay kiểu field. Nó còn quy định ngày giờ được biểu diễn thế nào, property Java tương ứng với tên JSON nào, và ứng dụng hiểu ra sao khi một field bị thiếu hoặc có giá trị null.

Nếu các quy tắc này không được thiết kế rõ, hai service có thể đọc cùng một JSON thành những giá trị khác nhau. Ví dụ, một timestamp có offset +07:00 có thể bị chuẩn hóa sang UTC; tên field được đổi theo naming strategy có thể làm client cũ không gửi đúng key; hoặc null bị bỏ qua khiến thao tác cập nhật không xóa được giá trị như mong muốn.

Trong Spring, cần phối hợp ba lớp:

- **Jackson mapping** chuyển đổi giữa JSON và Java, gồm date/time, property name và null handling.
- **Spring MVC/WebFlux binding** đưa request body, query parameter và path variable vào đúng cơ chế chuyển đổi.
- **Validation và nghiệp vụ** xác nhận dữ liệu đã ánh xạ có hợp lệ và được phép dùng hay không.

Bài học này tập trung vào cách định nghĩa các quy tắc đó một cách nhất quán, kiểm thử chúng và tránh thay đổi wire contract ngoài ý muốn.

## 1. Ba phần của JSON contract

Giả sử API nhận một hồ sơ:

~~~json
{
  "display_name": "An",
  "birth_date": "1998-04-12",
  "registered_at": "2026-11-12T08:30:00Z",
  "middle_name": null
}
~~~

DTO Java có thể biểu diễn:

~~~java
public class ProfileRequest {
    private String displayName;
    private LocalDate birthDate;
    private Instant registeredAt;
    private String middleName;

    // Getter và setter.
}
~~~

Có ba quyết định riêng:

1. **Định dạng ngày giờ**: birth_date chỉ là ngày lịch; registered_at là một thời điểm tuyệt đối.
2. **Tên trường**: displayName ánh xạ thành display_name.
3. **Chính sách null**: middle_name được gửi null có ý nghĩa gì? Có được phép bỏ qua, xóa giá trị hiện tại hay từ chối?

Nếu các quyết định này được để mặc định ở nhiều nơi, contract có thể khác nhau giữa request DTO, response DTO, batch job và message consumer. Nên định nghĩa chúng có chủ đích và có test.

## 2. Chọn đúng kiểu Java cho ngày giờ

Trước khi cấu hình format, cần chọn kiểu biểu diễn đúng ý nghĩa dữ liệu. Các kiểu date/time không thể thay thế cho nhau.

| Kiểu Java | Ý nghĩa | Ví dụ wire value thường dùng |
|---|---|---|
| LocalDate | Ngày lịch, không có giờ và múi giờ | 2026-11-12 |
| LocalTime | Giờ trong ngày, không có ngày/múi giờ | 09:30:00 |
| LocalDateTime | Ngày và giờ địa phương, không có offset/múi giờ | 2026-11-12T09:30:00 |
| OffsetDateTime | Ngày giờ kèm UTC offset | 2026-11-12T09:30:00+07:00 |
| ZonedDateTime | Ngày giờ gắn với ZoneId và quy tắc múi giờ | 2026-11-12T09:30:00+07:00[Asia/Ho_Chi_Minh] |
| Instant | Một thời điểm trên timeline UTC | 2026-11-12T02:30:00Z |
| Duration | Khoảng thời gian theo giây/nanosecond | PT15M |
| Period | Khoảng thời gian theo năm/tháng/ngày | P1Y2M |

### 2.1. Dùng LocalDate cho ngày sinh, ngày hóa đơn và ngày lịch

Ngày sinh hoặc ngày hóa đơn thường không đại diện cho một thời điểm cụ thể. Dùng LocalDate:

~~~java
private LocalDate birthDate;
~~~

JSON:

~~~json
{
  "birthDate": "1998-04-12"
}
~~~

Không nên dùng Date hoặc Instant cho ngày sinh nếu ứng dụng không có giờ và timezone. Một ngày lịch có thể bị lệch sang ngày trước/sau khi bị diễn giải như một timestamp rồi đổi múi giờ.

### 2.2. Dùng Instant cho thời điểm tuyệt đối

Nếu cần lưu thời điểm một giao dịch được tạo, Instant là lựa chọn rõ ràng:

~~~java
private Instant createdAt;
~~~

Wire format ISO-8601 thường dùng UTC với hậu tố Z:

~~~json
{
  "createdAt": "2026-11-12T02:30:00Z"
}
~~~

Instant không lưu timezone ban đầu của người gửi. Nó biểu diễn một điểm trên timeline. Nếu cần biết người dùng nhập giờ theo múi giờ nào, lưu thêm ZoneId hoặc offset theo contract.

### 2.3. Dùng OffsetDateTime khi offset của client có ý nghĩa

OffsetDateTime giữ offset như +07:00 hoặc -05:00:

~~~java
private OffsetDateTime scheduledAt;
~~~

JSON:

~~~json
{
  "scheduledAt": "2026-11-12T09:30:00+07:00"
}
~~~

Hai giá trị 09:30+07:00 và 02:30Z biểu diễn cùng một thời điểm, nhưng offset được trình bày khác nhau. Nếu ứng dụng cần giữ offset mà client gửi, hãy kiểm tra cấu hình điều chỉnh timezone khi deserialize.

### 2.4. LocalDateTime không xác định được một thời điểm tuyệt đối

LocalDateTime chỉ chứa ngày và giờ địa phương. Nó không có offset hoặc timezone.

~~~json
{
  "meetingTime": "2026-11-12T09:30:00"
}
~~~

Không thể suy ra chắc chắn thời điểm UTC từ giá trị này nếu không biết timezone. Nếu hệ thống dùng LocalDateTime cho lịch hẹn, contract cần nói rõ timezone được lấy từ đâu: cấu hình tenant, địa điểm, profile người dùng hay một field riêng.

Không nên âm thầm coi LocalDateTime là UTC hoặc timezone của server. Kết quả có thể thay đổi khi ứng dụng chạy ở môi trường khác.

### 2.5. Offset không giống ZoneId

OffsetDateTime giữ độ lệch UTC tại thời điểm đó. ZoneId như Europe/Paris hoặc Asia/Ho_Chi_Minh còn chứa quy tắc timezone theo lịch sử và tương lai, bao gồm daylight saving time ở những vùng có áp dụng.

Nếu nghiệp vụ cần giữ vùng thời gian để tính lịch trong tương lai, chỉ lưu offset có thể chưa đủ. Có thể lưu:
- LocalDateTime của lịch địa phương.
- ZoneId của địa điểm.
- Hoặc ZonedDateTime theo một wire format được công bố rõ.

Hãy chọn kiểu theo ý nghĩa nghiệp vụ, không chỉ theo chuỗi JSON đang có.

## 3. Đăng ký hỗ trợ java.time trong Jackson

Các kiểu thuộc java.time được hỗ trợ qua module Jackson Java Time, thường là dependency jackson-datatype-jsr310.

Với Maven:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
~~~

Nếu dự án dùng Jackson BOM hoặc dependency management của Spring Boot, để hệ thống quản lý version tương thích thay vì khai báo một version độc lập.

Với ObjectMapper thuần, có thể đăng ký JavaTimeModule:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
~~~

Hoặc dùng cơ chế khám phá module:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();
~~~

Trong Spring Boot, Jackson auto-configuration thường tự đăng ký module có trên classpath vào mapper do Boot tạo. Không nên đăng ký module trùng lặp một cách tùy tiện; hãy kiểm tra cấu hình thực tế của ứng dụng.

Nếu gặp lỗi kiểu Java 8 date/time không được hỗ trợ, hãy xác nhận dependency Java Time có mặt và mapper đang dùng thật sự là mapper đã được cấu hình module. Một custom ObjectMapper tự tạo có thể không kế thừa các cấu hình/module mà Spring Boot đã tự động thiết lập.

## 4. Dùng ISO-8601 làm wire format mặc định

ISO-8601 là lựa chọn phù hợp cho phần lớn API vì dễ đọc, có quy ước offset và được nhiều nền tảng hỗ trợ.

Ví dụ:

~~~json
{
  "date": "2026-11-12",
  "localTime": "09:30:00",
  "localDateTime": "2026-11-12T09:30:00",
  "offsetDateTime": "2026-11-12T09:30:00+07:00",
  "instant": "2026-11-12T02:30:00Z"
}
~~~

Đối với Java Time, Jackson thường serialize thành chuỗi ISO khi tắt chế độ timestamp. Có thể cấu hình:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
        .build();
~~~

Hai feature có vai trò khác nhau:

- WRITE_DATES_AS_TIMESTAMPS kiểm soát cách serialize date/time thành số hoặc dạng timestamp thay vì chuỗi.
- ADJUST_DATES_TO_CONTEXT_TIME_ZONE ảnh hưởng cách một số kiểu date/time có offset/zone được điều chỉnh theo timezone của context khi deserialize.

Nếu API cần giữ offset được gửi trong OffsetDateTime, hãy kiểm tra và cấu hình adjustment phù hợp. Không nên mặc định mọi kiểu date/time đều cần giữ nguyên cùng một loại timezone; Instant vốn biểu diễn thời điểm UTC.

## 5. Cấu hình ngày giờ trong Spring Boot

Với Spring Boot, có thể cấu hình nhiều quy tắc Jackson qua application.yml:

~~~yaml
spring:
  jackson:
    time-zone: UTC
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      write-dates-as-timestamps: false
    deserialization:
      adjust-dates-to-context-time-zone: false
      fail-on-null-for-primitives: true
~~~

Ý nghĩa:
- time-zone đặt timezone mặc định cho các kiểu date/time phụ thuộc timezone.
- property-naming-strategy áp dụng quy tắc tên property toàn cục.
- default-property-inclusion kiểm soát việc serialize property null.
- write-dates-as-timestamps tắt biểu diễn timestamp dạng số khi serializer hỗ trợ feature này.
- adjust-dates-to-context-time-zone giúp tránh tự điều chỉnh một số giá trị có offset theo context timezone.
- fail-on-null-for-primitives yêu cầu từ chối explicit JSON null khi target là primitive.

Cấu hình Spring Boot có thể thay đổi theo phiên bản và dòng Jackson đang dùng. Hãy xác nhận property được hỗ trợ trong phiên bản dự án; đặc biệt không giả định spring.jackson.date-format sẽ áp dụng cùng một cách cho cả java.util.Date và mọi kiểu java.time.

### 5.1. date-format không phải quy tắc chung cho mọi kiểu thời gian

Thuộc tính spring.jackson.date-format chủ yếu cấu hình DateFormat cho các kiểu date legacy như java.util.Date. Java Time module dùng serializer/deserializer riêng và có thể cần @JsonFormat hoặc cấu hình module tương ứng.

Vì vậy, nếu API có cả Date, LocalDate, Instant và OffsetDateTime, đừng chỉ đặt date-format rồi kỳ vọng mọi field có cùng representation. Hãy kiểm thử từng kiểu.

### 5.2. Tùy chỉnh Jackson bằng builder customizer

Nếu cần cấu hình Java thay cho YAML, với Spring Boot sử dụng Jackson 2 có thể dùng Jackson2ObjectMapperBuilderCustomizer:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.timeZone(TimeZone.getTimeZone("UTC"));
            builder.featuresToDisable(
                    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS,
                    DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE
            );
        };
    }
}
~~~

Customizer được áp dụng vào builder mà Spring Boot dùng để tạo mapper auto-configured. Đây thường là cách phù hợp khi muốn bổ sung quy tắc mà vẫn giữ các module và cấu hình Boot đã thiết lập.

Nếu ứng dụng dùng Spring Boot/Jackson 3 hoặc một cấu hình MVC/WebFlux tùy chỉnh, tên lớp và extension point có thể khác. Hãy theo API của phiên bản thực tế thay vì copy cấu hình Jackson 2 vào một dự án Jackson 3.

## 6. Dùng @JsonFormat cho format của từng property

Khi một field cần format riêng, có thể dùng @JsonFormat:

~~~java
public class ReportRequest {

    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    private LocalDate reportDate;

    @JsonFormat(
            shape = JsonFormat.Shape.STRING,
            pattern = "yyyy-MM-dd'T'HH:mm:ssXXX"
    )
    private OffsetDateTime submittedAt;

    // Getter và setter.
}
~~~

JSON:

~~~json
{
  "reportDate": "2026-11-12",
  "submittedAt": "2026-11-12T09:30:00+07:00"
}
~~~

Pattern dùng các ký hiệu của DateTimeFormatter:
- yyyy: năm.
- MM: tháng.
- dd: ngày.
- HH: giờ 00–23.
- mm: phút.
- ss: giây.
- XXX: offset dạng Z hoặc ±HH:MM.

Phân biệt MM là tháng với mm là phút. Nhầm hai ký hiệu này là lỗi format phổ biến.

Với format chuẩn ISO, thường không cần khai báo pattern nếu serializer mặc định đã đáp ứng contract. Chỉ dùng pattern riêng khi API hoặc hệ thống đối tác yêu cầu một representation cụ thể.

### 6.1. Không dùng một pattern cho mọi kiểu

LocalDate không có giờ hoặc offset. Instant là thời điểm UTC. OffsetDateTime có offset. Một pattern có timezone/offset không có ý nghĩa giống nhau với tất cả các kiểu.

Hãy chọn pattern theo kiểu Java:
- LocalDate: yyyy-MM-dd.
- LocalTime: HH:mm:ss hoặc format có fractional seconds theo yêu cầu.
- LocalDateTime: yyyy-MM-dd'T'HH:mm:ss.
- OffsetDateTime: format có offset như yyyy-MM-dd'T'HH:mm:ssXXX.

Nếu cần hỗ trợ nanosecond, hãy quy định số chữ số fractional second và test round trip. Không nên cắt phần thập phân chỉ vì UI không hiển thị nó nếu backend cần độ chính xác đó.

### 6.2. @JsonFormat và timezone

Với Date legacy, timezone trong @JsonFormat thường có tác động trực tiếp đến việc format/parse. Với Java Time, hành vi phụ thuộc kiểu và serializer/deserializer cụ thể; LocalDate không có timezone để chuyển đổi.

Đừng gắn timezone UTC vào mọi field chỉ để "đồng nhất". Hãy phân biệt:
- Thời điểm tuyệt đối: thường serialize UTC.
- Giờ địa phương: cần ZoneId theo nghiệp vụ.
- Ngày lịch: không chuyển timezone.

## 7. Spring @DateTimeFormat khác @JsonFormat

Đây là khác biệt quan trọng khi tích hợp Spring.

- @JsonFormat điều khiển Jackson khi serialize/deserialize JSON body.
- @DateTimeFormat thường điều khiển Spring ConversionService khi bind query parameter, path variable hoặc form data.

Ví dụ request body:

~~~json
{
  "date": "2026-11-12"
}
~~~

DTO:

~~~java
public class SearchRequest {

    @JsonFormat(pattern = "yyyy-MM-dd")
    private LocalDate date;

    // Getter và setter.
}
~~~

Query parameter:

~~~text
GET /reports?date=2026-11-12
~~~

Controller:

~~~java
@GetMapping("/reports")
public ReportResponse getReport(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date
) {
    return reportService.findByDate(date);
}
~~~

Không nên chỉ thêm @DateTimeFormat vào field rồi kỳ vọng Jackson dùng nó cho JSON request body. Hai con đường binding khác nhau.

## 8. Tên trường JSON và tên property Java

Tên property Java và tên JSON không cần giống nhau. Ví dụ Java dùng camelCase:

~~~java
private String displayName;
private Instant createdAt;
~~~

API có thể dùng snake_case:

~~~json
{
  "display_name": "An",
  "created_at": "2026-11-12T02:30:00Z"
}
~~~

Có ba cách thường dùng để định nghĩa mapping.

### 8.1. Naming strategy toàn cục

Cấu hình SNAKE_CASE:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
~~~

Trong Spring Boot:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

Khi đó displayName có thể được ánh xạ thành display_name và createdAt thành created_at.

Naming strategy áp dụng theo quy tắc cho property của model được mapper xử lý. Đây là lựa chọn thuận tiện nếu toàn bộ API dùng chung một quy ước.

### 8.2. @JsonNaming cho một class

Nếu chỉ một DTO dùng snake_case:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ProfileResponse {
    private String displayName;
    private Instant createdAt;

    // Getter và setter.
}
~~~

Class khác vẫn có thể dùng camelCase theo mapper mặc định. Cách này hữu ích khi tích hợp với đối tác có naming convention riêng.

### 8.3. @JsonProperty cho một field cụ thể

Nếu chỉ một số property cần tên đặc biệt:

~~~java
public class PaymentResponse {

    @JsonProperty("transaction_id")
    private String transactionId;

    @JsonProperty("amount_cents")
    private Long amountCents;

    // Getter và setter.
}
~~~

@JsonProperty xác định tên property trong JSON. Nó phù hợp khi tên wire format phải cố định dù Java refactor hoặc naming strategy toàn cục thay đổi.

Không nên trộn nhiều naming rule mà không có quy ước. Khi annotation ghi đè naming strategy, hãy test tên thực tế được serialize và deserialize.

## 9. Hỗ trợ tên field cũ bằng @JsonAlias

Khi API đổi tên property, consumer có thể cần chấp nhận tên cũ trong một giai đoạn migration.

~~~java
public class ProfileRequest {

    @JsonProperty("display_name")
    @JsonAlias({"displayName", "full_name"})
    private String displayName;

    // Getter và setter.
}
~~~

Khi deserialize, Jackson có thể chấp nhận các tên alias đã khai báo. Khi serialize, tên chính thức được xác định bởi JsonProperty là display_name.

Điều này giúp:
- Đọc được payload của client cũ.
- Công bố một tên chuẩn mới.
- Chuyển đổi client theo từng giai đoạn.
- Tránh phải duy trì nhiều DTO chỉ vì tên field khác nhau.

Alias là chính sách đọc đầu vào. Nó không có nghĩa serializer sẽ phát tất cả tên alias. Nên có thời hạn loại bỏ alias sau khi các client đã chuyển sang tên chính thức.

Nếu payload gửi đồng thời nhiều alias cho cùng một property, hãy xác định hành vi mong muốn và test. Không nên để thứ tự field trong JSON quyết định một cách ngẫu nhiên giá trị cuối cùng mà ứng dụng chấp nhận.

## 10. Phân biệt tên field với thứ tự field

@JsonPropertyOrder có thể quy định thứ tự property khi serialize:

~~~java
@JsonPropertyOrder({
        "id",
        "display_name",
        "created_at"
})
public class ProfileResponse {
    // Properties.
}
~~~

JSON object về mặt ngữ nghĩa không nên phụ thuộc vào thứ tự key. Tuy vậy, thứ tự có thể hữu ích cho:
- Snapshot test.
- Log dễ đọc.
- Hệ thống cũ có parser không tuân thủ chuẩn tốt.
- Tài liệu hoặc ví dụ.

Không dùng thứ tự field như một cơ chế bảo mật hoặc validation. Consumer phải đọc theo tên property, không dựa vào vị trí key.

## 11. READ_ONLY và WRITE_ONLY cho field theo chiều dữ liệu

Jackson có thể kiểm soát property chỉ xuất hiện ở một chiều:

~~~java
public class UserResponse {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    private String displayName;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;
}
~~~

Ý nghĩa:
- READ_ONLY: field được serialize ra JSON nhưng không nhận giá trị từ JSON input.
- WRITE_ONLY: field được deserialize từ JSON input nhưng không serialize ra output.

Cách này có thể hữu ích cho các property nhạy cảm hoặc do server quản lý. Tuy nhiên, request DTO và response DTO riêng thường rõ ràng hơn khi API có nhiều field khác nhau giữa hai chiều.

Không dùng READ_ONLY như cơ chế authorization duy nhất. Service vẫn phải bảo đảm client không thể thay đổi field nội bộ qua endpoint khác.

## 12. Chính sách null có hai chiều khác nhau

Một điểm dễ nhầm là null khi serialize và null khi deserialize là hai vấn đề riêng.

### 12.1. Serialization inclusion: có đưa null vào JSON output không?

@JsonInclude điều khiển property nào xuất hiện trong JSON khi serialize.

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProfileResponse {
    private String displayName;
    private String middleName;
}
~~~

Nếu middleName là null, output có thể bỏ field đó:

~~~json
{
  "displayName": "An"
}
~~~

Các lựa chọn thường gặp:

| Include | Ý nghĩa tổng quát |
|---|---|
| ALWAYS | Luôn đưa property vào output |
| NON_NULL | Bỏ property có giá trị null |
| NON_ABSENT | Bỏ null và các giá trị absent của kiểu hỗ trợ |
| NON_EMPTY | Bỏ null và giá trị được xem là rỗng như chuỗi/collection rỗng |
| NON_DEFAULT | Bỏ giá trị được xem là default theo quy tắc Jackson |

Cấu hình toàn cục trong Spring Boot:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
~~~

Hoặc trên một class/field:

~~~java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
private List<String> tags;
~~~

NON_EMPTY khác NON_NULL. Một list rỗng không phải null, nhưng có thể bị loại khỏi output nếu dùng NON_EMPTY.

### 12.2. Deserialization: xử lý null trong JSON input thế nào?

Khi JSON có:

~~~json
{
  "middleName": null
}
~~~

Jackson cần quyết định:
- Gán null cho property.
- Bỏ qua lần gán này và giữ giá trị hiện tại.
- Dùng giá trị empty.
- Báo lỗi.

Có thể dùng @JsonSetter:

~~~java
public class ProfileRequest {

    private String middleName;

    @JsonSetter(
            value = "middleName",
            nulls = Nulls.FAIL
    )
    public void setMiddleName(String middleName) {
        this.middleName = middleName;
    }
}
~~~

Nulls.FAIL từ chối explicit null cho property này. Những lựa chọn khác:

- SET: gán null theo hành vi thông thường.
- SKIP: bỏ qua setter khi input là null.
- AS_EMPTY: yêu cầu deserializer dùng empty value của kiểu đích.
- FAIL: ném lỗi mapping.
- DEFAULT: dùng chính sách mặc định.

Không nên suy ra null input policy từ JsonInclude. NON_NULL chỉ quyết định output serialization, không có nghĩa Jackson sẽ từ chối null khi đọc.

## 13. Phân biệt missing, null và empty

Ba request sau có thể mang ý nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{"middleName": null}
~~~

~~~json
{"middleName": ""}
~~~

- Missing: client không gửi property.
- Explicit null: client gửi property với giá trị null.
- Empty string: client gửi một chuỗi có độ dài bằng 0.

Nếu property có initializer hoặc setter không được gọi khi thiếu field, missing có thể giữ giá trị ban đầu. Explicit null thường gán null trừ khi @JsonSetter hoặc creator policy thay đổi hành vi. Empty string vẫn là string rỗng trừ khi coercion config hoặc deserializer định nghĩa cách khác.

Đối với collection, cần phân biệt thêm:
- Field bị thiếu.
- Field null.
- Collection rỗng [].
- Collection có phần tử null [null].
- Collection có phần tử rỗng.

Các trạng thái này không nên bị nhập làm một nếu API dùng chúng để cập nhật dữ liệu.

## 14. Nulls.SKIP, AS_EMPTY và FAIL trong thực tế

### 14.1. SKIP: giữ giá trị hiện tại khi input là null

~~~java
public class PreferencesRequest {

    private String locale = "vi-VN";

    @JsonSetter(value = "locale", nulls = Nulls.SKIP)
    public void setLocale(String locale) {
        this.locale = locale;
    }

    public String getLocale() {
        return locale;
    }
}
~~~

Nếu JSON không có locale, setter không được gọi. Nếu JSON gửi locale = null, setter cũng bị bỏ qua, nên giá trị initializer có thể được giữ.

Điều này có thể hữu ích với một số update request, nhưng cần hiểu rõ: null không thể dùng để xóa locale theo contract này.

### 14.2. AS_EMPTY: chuyển null thành empty value

~~~java
public class SearchRequest {

    @JsonSetter(value = "tags", nulls = Nulls.AS_EMPTY)
    private List<String> tags = new ArrayList<>();

    // Getter và setter.
}
~~~

Với collection có empty value phù hợp, explicit null có thể trở thành collection rỗng. Hãy test kiểu dữ liệu cụ thể và deserializer đang dùng; empty value có thể khác nhau giữa String, collection, array và custom type.

### 14.3. FAIL: từ chối null tường minh

~~~java
public class TransferRequest {

    @JsonSetter(value = "amount", nulls = Nulls.FAIL)
    private BigDecimal amount;

    // Getter và setter.
}
~~~

Cách này hữu ích khi null không có ý nghĩa hợp lệ. Nếu field cũng bắt buộc phải xuất hiện, cần kiểm tra missing riêng; Nulls.FAIL chỉ xử lý explicit null.

### 14.4. contentNulls cho phần tử collection/map

Có thể kiểm soát null bên trong collection:

~~~java
public class BatchRequest {

    @JsonSetter(contentNulls = Nulls.FAIL)
    private List<String> codes;

    // Getter và setter.
}
~~~

Cấu hình contentNulls áp dụng cho nội dung collection/map được hỗ trợ. Ví dụ, field codes có thể không null nhưng một phần tử [null] vẫn bị từ chối.

## 15. Null cho primitive và creator property

Primitive Java không thể giữ null. Ví dụ int và boolean:

~~~java
public class FeatureRequest {
    private int retryCount;
    private boolean enabled;
}
~~~

Nếu JSON gửi retryCount = null, hành vi mặc định có thể đưa về giá trị primitive mặc định tùy đường binding và cấu hình. Để từ chối explicit null cho primitive:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
~~~

Nếu property được truyền qua constructor/creator, có thêm các feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .build();
~~~

Các feature creator áp dụng cho property được bind qua creator. Chúng không tự biến mọi setter property thành bắt buộc.

Với request API, wrapper type thường dễ biểu đạt null hơn:

~~~java
public class FeatureRequest {
    @NotNull
    private Integer retryCount;

    @NotNull
    private Boolean enabled;

    // Getter và setter.
}
~~~

Sau mapping, Bean Validation có thể từ chối null. Nếu cần phân biệt missing với explicit null, hãy dùng constructor có presence logic hoặc một biểu diễn request có trạng thái rõ ràng.

## 16. Null, missing và PATCH semantics

Với API cập nhật, ba trạng thái có thể mang nghĩa:

| JSON input | Ý nghĩa cập nhật có thể chọn |
|---|---|
| Không có field | Giữ nguyên giá trị hiện tại |
| Field có null | Xóa giá trị hiện tại |
| Field có value | Thay bằng giá trị mới |

Đây là semantics phổ biến cho partial update, nhưng Jackson không tự áp dụng quy tắc nghiệp vụ này cho mọi DTO.

Nếu DTO chỉ có String field:
- Missing và explicit null có thể cùng cho kết quả null.
- Code không biết client có chủ động yêu cầu xóa hay không.

Có thể giữ presence flag trong custom setter/deserializer:

~~~java
public class ProfilePatchRequest {

    private String middleName;
    private boolean middleNameProvided;

    @JsonSetter("middleName")
    public void setMiddleName(String middleName) {
        this.middleNameProvided = true;
        this.middleName = middleName;
    }

    public boolean isMiddleNameProvided() {
        return middleNameProvided;
    }

    public String getMiddleName() {
        return middleName;
    }
}
~~~

Nếu property bị thiếu, setter không chạy và flag là false. Nếu JSON có explicit null, setter chạy với null và flag là true.

Service có thể áp dụng:
- provided = false: giữ nguyên.
- provided = true và value = null: xóa.
- provided = true và value khác null: cập nhật.

Đây chỉ là một cách triển khai. Với API dùng JSON Merge Patch hoặc một thư viện kiểu JsonNullable, cần tuân theo semantics của format/library tương ứng. Không nên dùng Optional một cách tùy tiện vì Optional trong DTO không tự bảo đảm phân biệt đủ ba trạng thái.

## 17. Empty string và coercion là chính sách riêng

Empty string không đồng nghĩa null. Jackson có thể có coercion behavior cho một số kiểu đích và cấu hình. Ví dụ, chuỗi rỗng gửi vào một số kiểu non-text có thể được từ chối, chuyển thành null hoặc xử lý theo coercion action.

Nếu API yêu cầu một số nguyên phải được gửi dưới dạng JSON number, không nên chấp nhận:
- "42" dưới dạng string.
- "" dưới dạng empty string.
- 42.5 dưới dạng floating-point.

Với Jackson có CoercionConfig:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
        )
        .setCoercion(
                CoercionInputShape.EmptyString,
                CoercionAction.Fail
        )
        .setCoercion(
                CoercionInputShape.Float,
                CoercionAction.Fail
        );
~~~

API CoercionConfig có từ các phiên bản Jackson 2.x tương ứng; hãy kiểm tra phiên bản cụ thể. Cần cấu hình theo logical type hoặc kiểu đích phù hợp, không mặc định một thiết lập cho Integer sẽ điều khiển mọi kiểu.

Đối với string field, dùng Bean Validation như @NotBlank nếu không cho phép chuỗi chỉ có whitespace. Null policy và blank policy là hai điều kiện riêng.

## 18. Bean Validation kiểm tra constraint sau khi Jackson ánh xạ

Jackson trả lời câu hỏi: JSON có thể chuyển thành object Java theo contract mapping hay không?

Bean Validation trả lời: object đã tạo có đáp ứng constraint dữ liệu hay không?

Ví dụ:

~~~java
public class CreateEventRequest {

    @NotBlank
    private String eventName;

    @NotNull
    private LocalDate eventDate;

    @NotNull
    private Instant occurredAt;

    @Size(max = 100)
    private String description;

    // Getter và setter.
}
~~~

Trong Spring MVC:

~~~java
@PostMapping("/events")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateEventRequest request
) {
    eventService.create(request);
    return ResponseEntity.accepted().build();
}
~~~

Nếu JSON không parse được hoặc sai kiểu, Spring thường ném HttpMessageNotReadableException bao quanh lỗi Jackson. Nếu mapping thành công nhưng constraint không đạt, Spring MVC có thể ném MethodArgumentNotValidException.

Không dùng @JsonInclude hoặc @JsonSetter thay cho @NotNull, @NotBlank, @Past, @Future hoặc constraint nghiệp vụ. Chúng giải quyết các tầng khác nhau.

## 19. Cấu hình mapper theo phạm vi trong Spring

Một cấu hình global có thể tiện nhưng ảnh hưởng đến mọi DTO được mapper đó xử lý. Nếu một đối tác cần format ngày khác hoặc naming convention khác, hãy cân nhắc phạm vi riêng.

Các lựa chọn:
- Global ObjectMapper cho contract chung của ứng dụng.
- @JsonFormat/@JsonProperty/@JsonNaming trên DTO riêng.
- ObjectReader/ObjectWriter chuyên biệt cho một kiểu hoặc một thao tác.
- Custom HttpMessageConverter hoặc mapper riêng khi endpoint thật sự cần contract khác.
- DTO riêng cho từng API boundary.

Không nên tạo một ObjectMapper mới tùy tiện trong controller vì có thể bỏ qua module, mix-in, naming strategy, custom serializer và cấu hình bảo mật đã được Spring Boot thiết lập.

### 19.1. Không thay đổi mapper dùng chung sau khi ứng dụng đã chạy

ObjectMapper được thiết kế để cấu hình trước rồi tái sử dụng. Nếu thay đổi feature hoặc module trong lúc nhiều request đang sử dụng, hành vi có thể không nhất quán.

Hãy:
1. Khai báo mapper/customizer ở cấu hình Spring.
2. Hoàn tất module và feature trước khi mapper được sử dụng.
3. Tạo reader/writer biến thể nếu cần cấu hình riêng.
4. Dùng DTO/annotation để giới hạn format theo property.
5. Kiểm thử các contract khác nhau bằng mapper/reader thực tế.

## 20. Xử lý lỗi binding trong Spring mà không lộ dữ liệu

Lỗi date format, field type hoặc null policy thường xuất hiện dưới dạng HttpMessageNotReadableException trong Spring MVC.

Có thể ánh xạ sang response lỗi có cấu trúc:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> handleUnreadableBody(
            HttpMessageNotReadableException exception
    ) {
        ApiError error = new ApiError(
                "INVALID_REQUEST_BODY",
                "Request body has an invalid format or value"
        );

        return ResponseEntity.badRequest().body(error);
    }
}
~~~

Response DTO:

~~~java
public record ApiError(
        String code,
        String message
) {
}
~~~

Không trả nguyên văn exception message hoặc raw JSON value nếu chúng có thể chứa dữ liệu nhạy cảm. Có thể ghi request ID, loại lỗi và property path đã được lọc trong log nội bộ.

Lỗi validation có thể được xử lý riêng để trả field và constraint code phù hợp. Đừng dựa vào việc parse chuỗi message của Jackson bằng regex vì message không phải API contract ổn định.

## 21. Kiểm thử format ngày giờ và timezone

Test cần kiểm tra cả deserialize lẫn serialize.

### 21.1. LocalDate dùng format ngày lịch

~~~java
@Test
void readsLocalDateAsIsoDate() throws Exception {
    ProfileRequest request = mapper.readValue(
            """
            {"birthDate":"1998-04-12"}
            """,
            ProfileRequest.class
    );

    assertEquals(
            LocalDate.of(1998, 4, 12),
            request.getBirthDate()
    );
}
~~~

### 21.2. Instant giữ đúng thời điểm

~~~java
@Test
void readsInstantAsUtcMoment() throws Exception {
    EventRequest request = mapper.readValue(
            """
            {"occurredAt":"2026-11-12T09:30:00+07:00"}
            """,
            EventRequest.class
    );

    assertEquals(
            Instant.parse("2026-11-12T02:30:00Z"),
            request.getOccurredAt()
    );
}
~~~

Hai chuỗi có offset khác nhau nhưng cùng biểu diễn một Instant phải cho cùng thời điểm.

### 21.3. OffsetDateTime có giữ offset theo contract không?

~~~java
@Test
void preservesOffsetWhenConfiguredToKeepIt() throws Exception {
    OffsetRequest request = mapper.readValue(
            """
            {"scheduledAt":"2026-11-12T09:30:00+07:00"}
            """,
            OffsetRequest.class
    );

    assertEquals(
            ZoneOffset.ofHours(7),
            request.getScheduledAt().getOffset()
    );
}
~~~

Test này cần chạy trên mapper có cấu hình timezone adjustment phù hợp. Nếu mapper cố ý chuẩn hóa theo context timezone, assertion phải phản ánh contract đã chọn.

### 21.4. Round trip theo wire format

~~~java
@Test
void serializesDateTimeAsIsoStrings() throws Exception {
    EventResponse response = new EventResponse(
            LocalDate.of(2026, 11, 12),
            Instant.parse("2026-11-12T02:30:00Z")
    );

    String json = mapper.writeValueAsString(response);

    assertTrue(json.contains("2026-11-12"));
    assertTrue(json.contains("2026-11-12T02:30:00Z"));
}
~~~

Không chỉ kiểm tra object sau deserialize. Hãy kiểm tra JSON output vì output format cũng là một phần của API contract.

## 22. Kiểm thử tên trường và alias

Test naming strategy:

~~~java
@Test
void serializesUsingSnakeCase() throws Exception {
    String json = snakeCaseMapper.writeValueAsString(
            new ProfileResponse("An")
    );

    assertTrue(json.contains("\"display_name\""));
}
~~~

Test alias đầu vào và tên chuẩn đầu ra:

~~~java
@Test
void acceptsLegacyAliasButWritesCanonicalName() throws Exception {
    ProfileRequest request = mapper.readValue(
            """
            {"displayName":"An"}
            """,
            ProfileRequest.class
    );

    String json = mapper.writeValueAsString(request);

    assertTrue(json.contains("\"display_name\""));
    assertFalse(json.contains("\"displayName\""));
}
~~~

Hãy test thêm:
- Field nested.
- Collection of DTO.
- Property có @JsonProperty ghi đè naming strategy.
- Hai alias cùng xuất hiện.
- Tên field sai chính tả.
- READ_ONLY/WRITE_ONLY theo cả hai chiều.

## 23. Kiểm thử null, missing và empty riêng biệt

Với mỗi field quan trọng, tạo các input:
- Không có key.
- Key có null.
- Key có chuỗi rỗng.
- Key có giá trị hợp lệ.
- Key có giá trị sai kiểu.

Ví dụ test null fail:

~~~java
@Test
void rejectsExplicitNullForRequiredField() {
    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                    """
                    {"amount":null}
                    """,
                    TransferRequest.class
            )
    );
}
~~~

Test missing sau mapping và Bean Validation:

~~~java
@Test
void rejectsMissingAmountThroughValidation() throws Exception {
    TransferRequest request = mapper.readValue(
            "{}",
            TransferRequest.class
    );

    Set<ConstraintViolation<TransferRequest>> violations =
            validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

Test PATCH presence:

~~~java
@Test
void distinguishesMissingFromExplicitNull() throws Exception {
    ProfilePatchRequest missing = mapper.readValue(
            "{}",
            ProfilePatchRequest.class
    );

    ProfilePatchRequest explicitNull = mapper.readValue(
            """
            {"middleName":null}
            """,
            ProfilePatchRequest.class
    );

    assertFalse(missing.isMiddleNameProvided());
    assertTrue(explicitNull.isMiddleNameProvided());
    assertNull(explicitNull.getMiddleName());
}
~~~

Các test này giúp ngăn một thay đổi cấu hình null vô tình làm thay đổi semantics của update API.

## 24. Kiểm thử contract qua Spring MVC

Unit test ObjectMapper rất hữu ích, nhưng Spring có thể dùng mapper/converter khác với mapper được tạo trong test. Vì vậy, với endpoint quan trọng nên có MockMvc hoặc WebTestClient test.

Một ví dụ MockMvc:

~~~java
@Test
void acceptsIsoDateAndSnakeCaseBody() throws Exception {
    mockMvc.perform(post("/profiles")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    {
                      "display_name": "An",
                      "birth_date": "1998-04-12"
                    }
                    """))
            .andExpect(status().isCreated());
}
~~~

Nên có thêm test:
- Ngày sai format trả 400.
- Offset không hợp lệ trả 400.
- Tên field canonical được chấp nhận.
- Alias cũ được chấp nhận trong thời gian migration.
- Null bị từ chối đúng field.
- Empty string bị validation từ chối.
- Response dùng đúng naming strategy và date format.
- Error response không chứa raw input.

## 25. Các lỗi cấu hình thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng Date/Instant cho ngày sinh | Ngày có thể lệch khi đổi timezone | Dùng LocalDate |
| Dùng LocalDateTime cho thời điểm tuyệt đối | Không có offset để xác định instant | Dùng Instant/OffsetDateTime |
| Coi offset là timezone | Mất quy tắc DST/ZoneId | Lưu ZoneId nếu nghiệp vụ cần |
| Chỉ đặt spring.jackson.date-format | Java Time có serializer riêng | Test từng kiểu, dùng @JsonFormat/module phù hợp |
| Nhầm @DateTimeFormat với @JsonFormat | Query/path binding khác JSON body | Dùng annotation theo đúng conversion path |
| Đổi naming strategy global mà không test client | Wire field names thay đổi | Version contract, alias hoặc DTO riêng |
| Nghĩ @JsonAlias thay tên khi serialize | Alias chủ yếu dùng khi đọc | Đặt tên output bằng @JsonProperty |
| Dùng NON_NULL để từ chối null input | Inclusion chỉ điều khiển output | Dùng @JsonSetter, creator policy và validation |
| Coi missing giống explicit null | PATCH không phân biệt giữ/xóa | Dùng presence flag hoặc kiểu tri-state |
| Dùng primitive cho field có thể null | Không biểu diễn được null | Dùng wrapper và validation |
| Dùng NON_EMPTY thay NON_NULL | Empty string/list cũng có thể bị bỏ | Chọn inclusion theo contract |
| Dùng @JsonFormat cho mọi field | Một pattern không phù hợp mọi kiểu | Chọn format theo semantic type |
| Tạo ObjectMapper riêng trong controller | Mất cấu hình Spring Boot | Dùng mapper được inject/customize |
| Trả exception message nguyên văn | Có thể lộ raw value hoặc nội bộ | Response lỗi tĩnh, có mã ổn định |

## 26. Quy trình thiết kế date/time, naming và null policy

Khi tạo hoặc thay đổi DTO Spring:

1. Chọn kiểu Java theo ý nghĩa: LocalDate cho ngày lịch, Instant cho thời điểm, OffsetDateTime/ZonedDateTime khi offset/zone cần được giữ.
2. Quy định wire format, ưu tiên ISO-8601 nếu không có yêu cầu đối tác khác.
3. Xác định timezone mặc định và liệu offset đầu vào có cần được giữ hay chuẩn hóa.
4. Thêm Java Time module và kiểm tra mapper Spring Boot thực tế đã dùng module.
5. Chọn naming strategy global hoặc annotation trên DTO; tránh đổi tên wire field ngoài kế hoạch.
6. Dùng @JsonAlias cho giai đoạn đọc tên cũ và giữ một tên canonical khi serialize.
7. Quy định null output bằng JsonInclude.
8. Quy định explicit null input bằng JsonSetter/creator policy.
9. Phân biệt missing, null, empty string và collection rỗng.
10. Dùng wrapper/creator/presence flag khi cần biết field có được gửi hay không.
11. Dùng Bean Validation cho constraint sau mapping và domain service cho quy tắc nghiệp vụ.
12. Kiểm thử ObjectMapper và endpoint Spring bằng request/response thật.
13. Trả lỗi có cấu trúc, không echo raw payload hoặc exception message.
14. Khi thay đổi contract, duy trì alias hoặc versioning trong thời gian chuyển đổi.

## 27. Những điểm cần nhớ

- Ngày lịch, local date-time và thời điểm tuyệt đối cần các kiểu Java khác nhau.
- LocalDate không có timezone; Instant là thời điểm UTC; OffsetDateTime giữ offset; ZoneId giữ quy tắc vùng thời gian.
- Java Time cần module jackson-datatype-jsr310; Spring Boot thường tự cấu hình module trên classpath cho mapper auto-configured.
- ISO-8601 là wire format phù hợp cho phần lớn API.
- WRITE_DATES_AS_TIMESTAMPS điều khiển cách serialize; ADJUST_DATES_TO_CONTEXT_TIME_ZONE ảnh hưởng việc điều chỉnh timezone khi deserialize một số kiểu.
- @JsonFormat dành cho Jackson JSON body; @DateTimeFormat thường dành cho Spring query/path/form binding.
- Naming strategy, @JsonNaming và @JsonProperty quyết định tên property trên wire.
- @JsonAlias giúp đọc tên cũ nhưng không thay canonical output name.
- @JsonInclude điều khiển output; @JsonSetter và creator/null features điều khiển input.
- Missing, explicit null, empty string và empty collection là các trạng thái khác nhau.
- Nulls.SKIP, AS_EMPTY và FAIL phải được chọn theo semantics của field.
- Primitive không thể giữ null; dùng wrapper khi null/presence có ý nghĩa.
- Bean Validation kiểm tra constraint sau mapping; authorization và domain service vẫn cần thiết.
- Cấu hình mapper một lần trong Spring và tái sử dụng; tránh tạo mapper riêng trong controller.
- Test cả request lẫn response qua mapper và Spring endpoint để giữ contract ổn định.

Định dạng ngày giờ, tên trường và null policy là ba phần không thể tách rời của JSON contract. Chọn đúng kiểu thời gian giúp tránh sai lệch timezone; quy định tên field rõ ràng giúp client và server hiểu cùng một payload; phân biệt missing, null và empty giúp thao tác tạo/cập nhật có semantics chính xác. Khi các quy tắc được cấu hình ở đúng lớp Spring/Jackson và được kiểm thử qua request/response thực tế, API dễ tích hợp hơn và ít bị thay đổi hành vi ngoài ý muốn.

