# Xử lý trường không biết, enum không hợp lệ và dữ liệu lồng nhau trong Spring Boot JSON

## 1. Mục tiêu của bài học

Một HTTP API thường nhận JSON từ trình duyệt, mobile app, hệ thống đối tác hoặc message gateway. JSON hợp lệ về cú pháp vẫn có thể **không hợp lệ theo hợp đồng dữ liệu**: client gửi một trường không được định nghĩa, dùng giá trị enum không tồn tại, bỏ trống object con hoặc truyền mảng chứa phần tử lỗi. Trên Spring Boot, Jackson và HTTP codecs thực hiện chuyển JSON thành Java object; validation và error handling phải tiếp tục kiểm tra ý nghĩa dữ liệu trước khi gọi nghiệp vụ.

Bài học tập trung vào ba tình huống:

1. **Trường không biết (unknown property):** JSON chứa key không ánh xạ vào property của DTO, ví dụ gửi "isAdmin":true vào request đăng ký chỉ có email và name.
2. **Enum không hợp lệ:** JSON gửi chuỗi không thuộc enum hoặc gửi số bị Jackson ánh xạ sang thứ tự khai báo nếu không cấu hình nghiêm ngặt.
3. **Dữ liệu lồng nhau:** object, list, null, missing field và phần tử list không đạt ràng buộc; cần deserialize đúng rồi validate xuyên qua cấu trúc.

Kết thúc bài, bạn cần:

- Phân biệt lỗi syntax JSON, lỗi deserialize, lỗi Bean Validation và lỗi nghiệp vụ.
- Chọn chế độ strict/lenient cho unknown fields; biết ảnh hưởng của FAIL_ON_UNKNOWN_PROPERTIES, @JsonIgnoreProperties và @JsonAlias.
- Nhận diện enum string, numeric ordinal, case, null, @JsonEnumDefaultValue và các lựa chọn tương thích ngược.
- Dùng DTO Java 17 record với @NotBlank, @NotNull, @Min, @NotEmpty và @Valid cho object/list lồng nhau.
- Biến lỗi đầu vào thành HTTP 400 rõ ràng, không để lộ stack trace hoặc dữ liệu nhạy cảm.
- Viết ví dụ Spring Boot 3.3.x dùng WebFlux.fn và WebTestClient, đồng thời biết khác biệt với Spring MVC.
- Thiết kế regression tests cho cả trường hợp đúng và sai ở mọi tầng JSON.

**Phạm vi phiên bản:** Các cấu hình và mã Jackson cụ thể trong bài dùng **Spring Boot 3.3.x + Jackson 2 + Java 17+**. Spring Boot 4.0 chuyển Jackson 3 thành lựa chọn mặc định, thay đổi package và một số property/configuration API. Không sao chép nguyên cấu hình Jackson 2 sang Boot 4 mà không xem migration guide.

## 2. JSON đi vào ứng dụng bằng cách nào?

Với HTTP request:

~~~http
POST /api/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Các bước điển hình trên Spring Boot:

~~~text
HTTP request body
    |
    v
Web runtime (Tomcat/Jetty/Reactor Netty)
    |
    v
Spring MVC HttpMessageConverter
  hoặc Spring WebFlux HttpMessageReader / Jackson2JsonDecoder
    |
    v
Jackson parse + data binding
    |
    +-- JSON lỗi cú pháp? -> lỗi đọc body
    +-- unknown property ở strict mode? -> lỗi mapping
    +-- enum không nhận diện? -> lỗi mapping
    |
    v
CreateOrderRequest và các nested records
    |
    v
Bean Validation hoặc custom validation
    |
    +-- thiếu required? -> 400 validation
    +-- quantity <= 0? -> 400 validation
    |
    v
Application service / domain
    |
    v
HTTP status + response DTO + JSON encoder
~~~

Jackson là công cụ chuyển JSON thành Java object; nó không thay thế tất cả quy tắc nghiệp vụ. Ví dụ JSON có quantity = 0 vẫn có thể được Jackson chuyển sang Integer 0 thành công; phải dùng validation để từ chối. Ngược lại, giá trị enum "TURBO" không có trong enum có thể thất bại **trước khi tạo DTO**, nên Bean Validation chưa được gọi.

Trên WebFlux.fn, ServerRequest.bodyToMono(CreateOrderRequest.class) đọc body qua codec. Trên Spring MVC, @RequestBody dùng HttpMessageConverter. Cơ chế lỗi và exception type có khác nhau, nhưng nguyên tắc hợp đồng JSON, DTO và Jackson gần nhau.

## 3. Bốn lớp lỗi không được đánh đồng

| Lớp | Ví dụ | Phát hiện | HTTP thường phù hợp |
| --- | --- | --- | --- |
| JSON syntax | Thiếu dấu ngoặc hoặc dấu nháy | JSON parser | 400 |
| JSON mapping | Trường lạ trong strict mode, enum "TURBO", object thành string | Jackson deserializer | 400 |
| DTO validation | shipping.city rỗng, lines[0].quantity = 0 | Jakarta Bean Validation | 400 |
| Business rules | Mã hàng không tồn tại, đơn bị trùng hoặc hết hàng | Domain/service | 400/404/409/422 theo API contract |

Một stack trace Jackson có thể chứa đường dẫn field và vị trí lỗi; thông tin này hữu ích cho log nội bộ, nhưng không nên trả nguyên văn cho client. Hãy chuẩn hóa response có mã lỗi, message an toàn và danh sách field hợp lệ khi cần.

Những status khác cũng quan trọng:

- 415 Unsupported Media Type: Content-Type không có decoder phù hợp, ví dụ gửi text/plain tới endpoint chỉ nhận JSON.
- 413 Payload Too Large: HTTP body vượt giới hạn đã cấu hình.
- 401/403: liên quan authentication/authorization, không được che thành lỗi JSON.
- 500: lỗi lập trình hoặc dependency thật, không được bắt tất cả rồi đổi thành 400.

## 4. Trường không biết là gì?

Giả sử DTO chỉ có:

~~~java
public record UserRequest(String name, String email) {
}
~~~

Client gửi:

~~~json
{
  "name": "Lan",
  "email": "lan@example.test",
  "isAdmin": true
}
~~~

Key isAdmin **không có property tương ứng** trong UserRequest. Đây là unknown JSON field. Nó khác với một field có mặt nhưng chứa giá trị null hoặc sai kiểu.

Khi mapping vào DTO tĩnh, Jackson có thể:

- **Strict:** từ chối unknown key bằng UnrecognizedPropertyException hoặc một lỗi mapping được bọc trong exception HTTP.
- **Lenient:** bỏ qua unknown key và tạo DTO từ các trường đã nhận diện.
- **Custom handling:** một @JsonAnySetter, deserializer hoặc handler chuyên biệt lưu/ghi nhận unknown key theo thiết kế.

Không thể kết luận mọi unknown field đều bị từ chối chỉ từ việc sử dụng record. Phải xét cấu hình mapper, annotation, mixin và cơ chế deserializer.

### 4.1. Mặc định Jackson 2 so với Spring Boot 3

Jackson 2 ObjectMapper nguyên bản thường bật FAIL_ON_UNKNOWN_PROPERTIES; Spring Boot 3.x có cấu hình mặc định thân thiện hơn và tắt việc fail unknown properties cho mapper được Boot auto-configure. Đây là một điểm thường gây nhầm khi chuyển từ unit test new ObjectMapper() sang ứng dụng Spring Boot thật.

Không nên kiểm tra chế độ strict bằng cách tạo một new ObjectMapper() tùy ý rồi suy ra đó là ObjectMapper của HTTP codec. Hãy xác minh mapper/configuration mà ứng dụng web thực sự dùng, và chạy HTTP integration test.

### 4.2. Khi nào nên strict?

Strict phù hợp khi:

- API là lệnh ghi quan trọng: thanh toán, phân quyền, cập nhật trạng thái, quản trị.
- Sai tên field có thể khiến hệ thống âm thầm bỏ qua ý định của client.
- Contract được công bố bằng OpenAPI/JSON Schema và các client cần được sửa sớm.
- Bạn muốn phát hiện lỗi typo như delivaryMethod thay vì bỏ qua nó.
- Dữ liệu inbound cần kiểm soát thay đổi schema chặt chẽ.

Ví dụ một đối tác gửi shipping.adress thay cho shipping.address. Trong chế độ lenient, field sai có thể bị bỏ qua rồi thành null, nếu validation không đầy đủ sẽ gây lỗi sâu hơn. Strict giúp lỗi xuất hiện sớm tại ranh giới API.

### 4.3. Khi nào có thể lenient?

Lenient có thể hữu ích cho:

- Client/server rolling upgrade mà phiên bản mới thêm field không ảnh hưởng bản cũ.
- Event schema thiết kế để consumer bỏ qua những thuộc tính bổ sung.
- Endpoint read/import dữ liệu bên ngoài với chính sách bảo toàn/trích xuất riêng.
- DTO cũ được hỗ trợ tạm thời trong một giai đoạn migration được kiểm thử.

**Không đồng nghĩa với bảo mật:** bỏ qua unknown fields không cho phép client ghi trực tiếp trường nhạy cảm, nhưng cũng không thay thế việc dùng input DTO riêng, server-side authorization và kiểm soát mass assignment.

## 5. Cấu hình strict unknown fields trong Spring Boot 3.3

Một cách cấu hình rõ ràng cho mapper mặc định của Boot 3.x là:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
      fail-on-numbers-for-enums: true
~~~

Hai cờ này độc lập:

- FAIL_ON_UNKNOWN_PROPERTIES: lỗi khi một field không được xử lý bởi DTO/deserializer.
- FAIL_ON_NUMBERS_FOR_ENUMS: không nhận số nguyên JSON làm enum theo ordinal.

Ví dụ với file .properties:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.deserialization.fail-on-numbers-for-enums=true
~~~

Đây là cấu hình theo **Jackson 2 / Spring Boot 3.x**. Khi bật globally, các DTO mới cũng chịu ảnh hưởng. Nên chạy regression tests trước khi deploy vì một client cũ gửi field bổ sung có thể bắt đầu nhận HTTP 400.

Có thể cấu hình bằng Java nếu cần kiểm soát tập trung:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer strictJson() {
    return builder -> builder.featuresToEnable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS
    );
}
~~~

Đoạn này cần import Jackson2ObjectMapperBuilderCustomizer từ org.springframework.boot.autoconfigure.jackson và DeserializationFeature từ com.fasterxml.jackson.databind. Đặt nó trong @Configuration phù hợp của Boot 3.x. Trong project hoàn chỉnh ở dưới, chỉ dùng application.yml để tránh đăng ký trùng cấu hình.

**Lưu ý quan trọng:** Nếu project tự tạo ObjectMapper riêng, Jackson2JsonDecoder riêng hoặc codecs custom, các property spring.jackson.* có thể không đi vào mapper đang được endpoint sử dụng. Đừng tuyên bố strict đã bật chỉ vì thấy YAML; phải kiểm thử request HTTP thật. Trên Spring Boot 4/Jackson 3, kiểu mapper và tên property đã thay đổi.

## 6. Ngoại lệ theo DTO: @JsonIgnoreProperties

Đôi khi hệ thống muốn strict mặc định, nhưng một DTO tích hợp legacy có thể nhận field mới từ đối tác. Trong Jackson 2, có thể đặt:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PartnerEvent(
        String externalId,
        String type
) {
}
~~~

Annotation trên loại này yêu cầu bỏ qua các thuộc tính JSON không map được cho PartnerEvent, ngay cả khi chính sách global nghiêm ngặt hơn. Đây là một **ngoại lệ có chủ đích**, không nên lạm dụng toàn bộ DTO ghi.

Một phương án khác là đổi tên/nhận alias có kiểm soát:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;

public record RenameRequest(
        @JsonAlias("customer_id") String customerId
) {
}
~~~

Khi đọc JSON, customer_id có thể được nhận như alias của customerId. @JsonAlias chủ yếu giúp deserialization, không tự bắt serialization xuất ra tên alias; JSON output thường theo tên property chính nếu không có cấu hình khác.

**Nên chọn gì?**

- Client gửi typo không được hỗ trợ: strict 400.
- Client cũ dùng tên trước đây nhưng migration còn hiệu lực: @JsonAlias rõ ràng.
- Partner gửi metadata mở rộng không quan trọng cho consumer: @JsonIgnoreProperties(ignoreUnknown=true) có phạm vi.
- Muốn lưu extra fields: thiết kế Map/JsonNode chuyên biệt, xác định validation, storage, quota và quyền, thay vì cho tất cả extras đi thẳng vào entity.

## 7. Trường lạ ở nhiều cấp lồng nhau

Unknown property không chỉ xuất hiện ở object gốc. Ví dụ:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000",
    "gps": "21.0,105.8"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Nếu strict mapper đang deserialize shipping thành Address record không có gps, mapping có thể thất bại tại đường dẫn shipping.gps. Nếu có @JsonIgnoreProperties(ignoreUnknown=true) trên **Address**, chỉ unknown fields của Address được bỏ qua. Annotation trên DTO gốc không nên bị xem là bảo đảm mọi class lồng nhau cũng tự được ignore; xem đúng class và type của từng cấp.

Với Map<String,Object>, JsonNode hoặc raw JSON tree, key bất kỳ là một phần dữ liệu map/tree, nên không có cùng ý niệm “unknown Java property” như binding vào DTO tĩnh. Nếu yêu cầu validate schema của map/tree, cần JSON Schema, custom validator hoặc kiểm tra business riêng.

Không đưa thẳng một object tree tự do vào ORM entity và mong unknown-field strictness tự tạo an toàn. Giới hạn kích thước, depth, key count và các thao tác có thể thực hiện phải được thiết kế riêng.

## 8. Enum không hợp lệ: các dạng cần phân biệt

Cho enum:

~~~java
public enum DeliveryMethod {
    STANDARD,
    EXPRESS
}
~~~

Các JSON giá trị:

| JSON | Hành vi mong đợi ở chế độ strict | Giải thích |
| --- | --- | --- |
| "STANDARD" | Hợp lệ | Enum name đúng |
| "EXPRESS" | Hợp lệ | Enum name đúng |
| "SAME_DAY" | Lỗi deserialize | Không thuộc enum |
| "express" | Thường lỗi | Mặc định Jackson 2 phân biệt hoa/thường |
| 1 | Lỗi nếu FAIL_ON_NUMBERS_FOR_ENUMS=true | Nếu không bật, Jackson 2 có thể ánh xạ theo ordinal |
| null | Có thể deserialize thành null | Cần @NotNull để từ chối |
| Không có key | Có thể thành null trong DTO record | Cần @NotNull hoặc required creator policy |
| {} | Không hợp lệ cho enum thông thường | JSON object khác kiểu enum string |

Một lỗi quan trọng là **numeric ordinal coercion**. Nếu enum đang là STANDARD(ordinal=0), EXPRESS(ordinal=1), một JSON number 1 có thể trở thành EXPRESS với Jackson 2 khi không cấm. Thêm/xóa/sắp xếp enum constants có thể thay đổi ý nghĩa của số, nên không xây public API dựa trên ordinal.

**Hợp đồng khuyến nghị:** nhận và phát enum bằng chuỗi có tên ổn định, kiểm tra tên chính xác, không chấp nhận ordinal. Nếu API công khai cần tên khác enum constant, dùng @JsonValue/@JsonCreator hoặc DTO chuyển đổi được thiết kế và kiểm thử.

## 9. Chọn chính sách cho unknown enum value

Có ba chiến lược phổ biến, nhưng ý nghĩa hoàn toàn khác nhau:

### 9.1. Từ chối: phương án phù hợp cho command quan trọng

Giữ Jackson 2 mặc định về string enum: unknown string gây lỗi mapping; kết hợp FAIL_ON_NUMBERS_FOR_ENUMS=true và Bean Validation @NotNull. Dùng cho lệnh tạo đơn, thanh toán, quyền và trạng thái không thể đoán.

Ví dụ deliveryMethod="DRONE" bị từ chối thay vì tự đổi sang STANDARD, bởi chọn sai phương thức giao hàng là một lỗi nghiệp vụ.

### 9.2. Chuyển sang null: có nguy cơ mất thông tin

Jackson 2 có:

~~~java
DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL
~~~

Khi bật, unknown enum string có thể trở thành null. Không dùng cờ này như một cách “sửa lỗi” chung: nếu field là optional, người dùng có thể không biết một giá trị đã bị vứt; với collection enum, null có thể bị loại khỏi EnumSet/EnumMap. Nếu dùng, cần định nghĩa rõ null semantics và validation.

### 9.3. Chuyển sang hằng UNKNOWN với @JsonEnumDefaultValue

Jackson 2 hỗ trợ:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum ExternalEventType {
    CREATED,
    UPDATED,
    @JsonEnumDefaultValue UNKNOWN
}
~~~

Để bật fallback:

~~~java
mapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

Đoạn mapper là minh họa; mapper phải là ObjectMapper thực sự dùng để deserialize. Nếu không có @JsonEnumDefaultValue, chỉ bật feature sẽ không tự tạo hằng mặc định. Cơ chế này phù hợp hơn cho **event/read model cần forward compatibility**, không mặc nhiên phù hợp cho command gây hiệu ứng thực.

Cần quyết định UNKNOWN được xử lý ra sao: lưu raw value ở metadata riêng, bỏ qua an toàn, cảnh báo giám sát hay chuyển luồng xử lý; đừng tự tạo tác vụ nghiệp vụ với trạng thái UNKNOWN. Khi đồng thời bật fallback UNKNOWN và AS_NULL, Jackson 2 ưu tiên default enum feature nếu có.

## 10. Enum đổi tên, alias và tương thích API

Khi đổi enum constant từ STANDARD sang ECONOMY, các client cũ gửi STANDARD có thể lỗi dù Java compile bình thường. Cần xem enum là **một phần hợp đồng API có version**.

Các lựa chọn:

- Giữ giá trị wire format cũ và chỉ đổi tên nội bộ qua explicit mapping.
- Tạo DTO API với string/enum ổn định, chuyển sang domain enum trong service.
- Đọc nhiều alias bằng custom @JsonCreator và serialize một tên chính bằng @JsonValue.
- Có giai đoạn deprecation, test backward compatibility và thống kê usage.
- Chỉ dùng UNKNOWN fallback cho consumer có chính sách xử lý giá trị mới.

Ví dụ enum đọc giá trị public bằng creator (snippet độc lập):

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ApiDelivery {
    STANDARD("standard"),
    EXPRESS("express");

    private final String code;

    ApiDelivery(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static ApiDelivery fromJson(String raw) {
        for (ApiDelivery value : values()) {
            if (value.code.equals(raw)) {
                return value;
            }
        }
        throw new IllegalArgumentException("Unsupported delivery method");
    }
}
~~~

Code yêu cầu Java 17+ nhưng không cần Spring để biên dịch nếu có Jackson annotations dependency. Hợp đồng JSON là "standard"/"express", không phụ thuộc enum.name(). Hãy kiểm thử số/null/case và exception wrapping; nếu muốn tuyệt đối từ chối numeric coercion, giữ cấu hình strict tương ứng và xác minh behavior thực của creator.

## 11. Dữ liệu lồng nhau: ba tầng cần xử lý

Giả sử request tạo đơn gồm:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2},
    {"sku": "BOOK-02", "quantity": 1}
  ]
}
~~~

Ba lớp dữ liệu:

1. **Root object:** customerId và deliveryMethod.
2. **Nested object:** shipping có recipient/city/postalCode.
3. **Nested collection:** lines là List<OrderLine>; mỗi phần tử có sku/quantity.

JSON decoder có thể tạo đầy đủ records nếu tên/kiểu dữ liệu tương thích. Nhưng những lỗi sau phải xét riêng:

- shipping thiếu hoàn toàn -> thường được binding thành null nếu không có strict creator policy.
- shipping là string thay vì object -> lỗi mapping.
- shipping.city là "" -> mapping thành công, validation @NotBlank mới từ chối.
- lines là [] -> mapping thành empty list, @NotEmpty mới từ chối.
- lines có phần tử null -> cần constraint @NotNull ở element.
- lines[0].quantity bằng 0 -> @Min(1) mới từ chối.
- lines[0].quantity bị thiếu -> dùng Integer + @NotNull để phát hiện, thay vì int mặc định 0 làm khó phân biệt nguồn lỗi.
- JSON có field lạ ở lines[0] -> strict unknown property kiểm tra tại OrderLine.

**Không lẫn Java null và JSON missing:** thiếu field và field được gán null có thể dẫn tới cùng Java null khi Jackson tạo object. Nếu hợp đồng cần phân biệt hai trạng thái này, cần cơ chế creator presence, JsonNode hoặc DTO chứa trạng thái hiện diện riêng; Bean Validation @NotNull chỉ bảo đảm có giá trị sau binding, không phân biệt nguồn.

## 12. Bean Validation xuyên qua nested object và list

Jakarta Bean Validation trong Spring Boot 3.x dùng package jakarta.validation.*. Với DTO lồng nhau, constraint của nested class chỉ được áp dụng khi bật **cascaded validation** đúng chỗ:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull DeliveryMethod deliveryMethod,
        @NotNull @Valid Address shipping,
        @NotEmpty List<@NotNull @Valid OrderLine> lines
) {
}
~~~

Đối với Address:

~~~java
public record Address(
        @NotBlank String recipient,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}
~~~

Đối với OrderLine:

~~~java
public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

Các snippet trên cần import jakarta.validation.Valid và jakarta.validation.constraints.*; project hoàn chỉnh ở phần 17 có file và import đầy đủ.

Ý nghĩa:

- @NotBlank từ chối null, "" và chuỗi toàn whitespace đối với CharSequence.
- @NotNull bảo đảm reference không null.
- @NotEmpty từ chối null và collection rỗng.
- @Min(1) bảo đảm số ít nhất bằng 1; @Min riêng **không** từ chối null.
- @Valid trên shipping yêu cầu kiểm tra các constraint bên trong Address.
- List<@NotNull @Valid OrderLine> yêu cầu phần tử không null và cascade vào từng OrderLine.
- Các lỗi có thể có path shipping.city hoặc lines[0].quantity tùy validator và danh sách dữ liệu.

Không tự giả định @Valid trên root sẽ đi sâu vào mọi cấp khi chưa gắn @Valid cho nested field/list element. Unit test hoặc integration test phải chứng minh lỗi sâu được trả ra đúng.

### 12.1. @JsonProperty(required=true) có thay thế @NotNull không?

Không. Required trong JSON creator/binding liên quan đến sự hiện diện của property theo hợp đồng Jackson; nó không thay thế tất cả semantics validation, không bảo đảm chuỗi không trống, số lớn hơn 0 hoặc object con hợp lệ. Tùy phiên bản/creator configuration, nhiều annotation chỉ tác động một số cách khởi tạo object.

Đối với API công khai, nên giữ DTO rõ ràng và dùng Bean Validation cho giá trị sau binding. Nếu cần phân biệt absent/null hoặc những quy tắc creator phức tạp, bổ sung test Jackson tương ứng.

## 13. Validation trong MVC khác WebFlux.fn thế nào?

**Spring MVC annotated controller:** thường dùng @Valid @RequestBody CreateOrderRequest request khi có validation provider phù hợp. Lỗi binding có thể tạo HttpMessageNotReadableException, lỗi Bean Validation thường tạo MethodArgumentNotValidException. Với @RestControllerAdvice có thể chuẩn hóa chúng thành HTTP 400.

**Spring WebFlux annotated controller:** có thể dùng @Valid cùng @RequestBody theo API reactive, nhưng exception/validation flow khác MVC, nhất là khi argument là Mono<T>. Cần kiểm tra WebExchangeBindException, ServerWebInputException và test annotation/method validation theo version.

**Spring WebFlux.fn:** request.bodyToMono(CreateOrderRequest.class) chỉ thực hiện body decoding, **không mặc nhiên chạy tất cả Bean Validation constraints** như thể có @Valid ở annotated controller. Nên inject jakarta.validation.Validator vào HandlerFunction và gọi validator.validate(dto), hoặc xây cơ chế validation tương đương có kiểm soát.

Ví dụ:

~~~java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(requestDto);

if (!violations.isEmpty()) {
    List<String> fields = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .distinct()
            .sorted()
            .toList();
    // Tạo ServerResponse 400 theo API contract.
}
~~~

Đoạn này cần biến validator/requestDto đã tồn tại; project hoàn chỉnh bên dưới có method tương ứng. **Không trả giá trị bị từ chối hoặc nguyên exception message** một cách mù quáng: nó có thể chứa PII, token hoặc tên internal class.

## 14. Codec WebFlux và HttpMessageConverter MVC

Trong Spring WebFlux, Spring WebFlux HTTP message readers/writers sử dụng codec tương thích với media type; với Jackson 2 có Jackson2JsonDecoder/Encoder trong cấu hình phù hợp. bodyToMono đọc Publisher từ request body rồi decode sang object. Với Spring MVC, HttpMessageConverter đọc body của Servlet request.

Khác biệt mà người học cần nắm:

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| API vào phổ biến | @RequestBody CreateOrderRequest | bodyToMono(CreateOrderRequest.class) hoặc @RequestBody Mono<T> |
| JSON infrastructure Boot 3.x | MappingJackson2HttpMessageConverter | Jackson2JsonDecoder/Encoder |
| Chỗ xử lý lỗi decode | HttpMessageNotReadableException | Có thể gặp DecodingException, ServerWebInputException |
| Validation | @Valid/Bean Validation trong annotated binding | Annotated hoặc explicit Validator cho functional handlers |
| HTTP body | Theo Servlet read/write | Publisher/Reactive Streams |
| Chọn media type | Content-Type và Accept | Content-Type và Accept |
| Threading | Servlet stack | Reactive stack, tránh block event-loop |

Cùng một ObjectMapper được Boot cấu hình có thể được dùng bởi nhiều component, nhưng nếu ứng dụng tự tạo codec/mapper khác, cấu hình chung chưa chắc đã tác động chúng. Vì thế test qua HTTP có giá trị hơn unit test new ObjectMapper riêng.

**Chú ý lỗi 415:** request body text/plain không được JSON reader nhận có thể trở thành UnsupportedMediaTypeStatusException/415. Không nên bắt toàn bộ Exception và ép thành INVALID_JSON 400, vì như vậy che mất distinction về media type.

## 15. Phân loại error response an toàn

Đề xuất một cấu trúc ngắn:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed",
  "fields": [
    "shipping.city",
    "lines[0].quantity"
  ]
}
~~~

Các mã dễ xử lý từ client:

- INVALID_JSON: syntax/mapping lỗi, gồm enum lạ hoặc field lạ dưới strict policy.
- MISSING_BODY: không có JSON body.
- VALIDATION_FAILED: DTO đã decode nhưng không thỏa constraint.
- UNSUPPORTED_MEDIA_TYPE: Content-Type sai, trả 415 theo layer framework.
- BUSINESS_RULE_VIOLATION: JSON hợp lệ nhưng lệnh bị từ chối theo domain policy.

Đừng trả raw com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException hoặc raw stack trace. Với strict unknown fields, thông báo nội bộ có thể chứa tên type, field path và thậm chí JSON input. Client nên nhận mã lỗi ổn định; log nội bộ có thể ghi sanitized path và trace ID để điều tra.

Nếu API cần trả chính xác field lỗi mapping, hãy giải mã JsonMappingException.getPath() có giới hạn và sanitize; không gửi nguyên bản exception.getMessage() vì chứa chi tiết máy chủ, giá trị input hoặc tên class.

## 16. Chính sách strict/lenient và hợp đồng phiên bản API

Không có một cờ “đúng cho tất cả”:

| Trường hợp | Unknown field | Unknown enum | Nested validation |
| --- | --- | --- | --- |
| Tạo đơn/thanh toán | Thường strict | Từ chối | Bắt buộc |
| API admin/quyền | Strict | Từ chối | Bắt buộc |
| Consumer event nhiều version | Có thể lenient có kiểm soát | Có thể UNKNOWN | Bắt buộc cho dữ liệu cần sử dụng |
| Import dữ liệu chưa chuẩn hóa | Parse riêng/JsonNode | Log và phân loại | Kiểm tra theo schema import |
| Read model đối tác | Có thể @JsonIgnoreProperties cục bộ | Alias/fallback theo hợp đồng | Kiểm tra trước khi dùng |

Nên chọn chính sách khi thiết kế API, không đổi toàn cục trong production chỉ để xử lý một request lỗi. Nếu nâng strictness, chuẩn bị contract tests, thông báo client, metrics lỗi mới, canary deployment và rollback.

**Một DTO dành cho input không nên là JPA entity:** tách request DTO khỏi entity để client không vô tình điều khiển trường isAdmin, internalStatus, cost hoặc ownerId. Unknown-field strictness bảo vệ contract, nhưng quyền truy cập phải được kiểm soát ở service/security.

## 17. Project thực hành: Java 17 + Spring Boot 3.3 + WebFlux.fn

Project dưới đây chạy một API POST /api/orders, dùng Jackson 2 strict đối với unknown fields và numeric enum values, nhận nested JSON, gọi Jakarta Bean Validation **thủ công trong WebFlux.fn**, rồi trả 201/400 với response có cấu trúc.

Điều kiện: JDK 17+, Gradle Wrapper tương thích Spring Boot 3.3, Maven Central và port trống. Ví dụ dùng AtomicLong để cấp ID trong RAM, không có database; sau restart ID có thể bắt đầu lại. Đây là project phục vụ học JSON/codec, không phải thiết kế order system production.

### 17.1. Cấu trúc dự án

~~~text
json-contract-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/json/
        JsonContractApplication.java
        DeliveryMethod.java
        Address.java
        OrderLine.java
        CreateOrderRequest.java
        OrderCreated.java
        ApiError.java
        OrderHandler.java
        OrderRoutes.java
      resources/
        application.yml
    test/
      java/example/json/
        JsonContractApplicationTests.java
~~~

### 17.2. settings.gradle

~~~groovy
rootProject.name = 'json-contract-demo'
~~~

### 17.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Để giữ WebFlux làm web stack, ví dụ không thêm spring-boot-starter-web. Khi có cả MVC/WebFlux starters, Spring Boot thường chọn Servlet MVC. Với project thực tế, dùng dependency versions do build quản lý.

### 17.4. application.yml

~~~yaml
spring:
  application:
    name: json-contract-demo
  jackson:
    deserialization:
      fail-on-unknown-properties: true
      fail-on-numbers-for-enums: true

server:
  port: 8080
~~~

Hai flags là cơ sở của hai regression tests: trường lạ và enum số phải thất bại ở tầng JSON decode. Nếu flags không đi vào HTTP mapper thực tế, tests sẽ cho biết.

### 17.5. JsonContractApplication.java

~~~java
package example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
~~~

### 17.6. DeliveryMethod.java

~~~java
package example.json;

public enum DeliveryMethod {
    STANDARD,
    EXPRESS
}
~~~

### 17.7. Address.java

~~~java
package example.json;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String recipient,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}
~~~

### 17.8. OrderLine.java

~~~java
package example.json;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

Dùng Integer thay cho int để phân biệt missing/null với giá trị zero đã gửi. @Min(1) phát hiện 0 hoặc số âm; @NotNull phát hiện null.

### 17.9. CreateOrderRequest.java

~~~java
package example.json;

import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull DeliveryMethod deliveryMethod,
        @NotNull @Valid Address shipping,
        @NotEmpty List<@NotNull @Valid OrderLine> lines
) {
}
~~~

Validation cascade vào shipping và từng OrderLine. Với shipping=null, @NotNull từ chối; với lines=[] hoặc null, @NotEmpty từ chối. Nếu lines có phần tử null, @NotNull ở type-use phát hiện.

### 17.10. OrderCreated.java

~~~java
package example.json;

public record OrderCreated(
        long id,
        DeliveryMethod deliveryMethod,
        int lineTypes
) {
}
~~~

lineTypes là số dòng mặt hàng, không phải tổng số quantity.

### 17.11. ApiError.java

~~~java
package example.json;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<String> fields
) {
}
~~~

Chỉ trả tên field lỗi, không trả nguyên input (đặc biệt khi payload có dữ liệu nhạy cảm).

### 17.12. OrderHandler.java

~~~java
package example.json;

import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final Validator validator;
    private final AtomicLong ids = new AtomicLong();

    public OrderHandler(Validator validator) {
        this.validator = validator;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(input -> {
                    Set<ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(input);

                    if (!violations.isEmpty()) {
                        List<String> fields = violations.stream()
                                .map(v -> v.getPropertyPath().toString())
                                .distinct()
                                .sorted()
                                .toList();

                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "VALIDATION_FAILED",
                                        "Request validation failed",
                                        fields));
                    }

                    long id = ids.incrementAndGet();
                    OrderCreated output = new OrderCreated(
                            id,
                            input.deliveryMethod(),
                            input.lines().size());

                    return ServerResponse
                            .created(URI.create("/api/orders/" + id))
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(output);
                })
                .switchIfEmpty(Mono.defer(
                        () -> badJson("MISSING_BODY",
                                "JSON body is required")))
                .onErrorResume(DecodingException.class,
                        ex -> badJson("INVALID_JSON",
                                "Malformed or incompatible JSON"))
                .onErrorResume(ServerWebInputException.class,
                        ex -> badJson("INVALID_JSON",
                                "Malformed or incompatible JSON"));
    }

    private Mono<ServerResponse> badJson(
            String code, String message) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(code, message, List.of()));
    }
}
~~~

Phân tích chính xác luồng:

1. bodyToMono decode JSON thành CreateOrderRequest và các nested records.
2. Unknown property hoặc enum không hợp lệ làm codec phát lỗi; hai onErrorResume ở đây chỉ xử lý DecodingException hoặc ServerWebInputException phù hợp. Những exception khác không tự bị biến thành 400.
3. Khi decode được object, Validator kiểm tra field và nested object/list. Nếu có lỗi, trả 400 VALIDATION_FAILED với danh sách path, không làm tăng ID.
4. Nếu body rỗng, Mono.empty được chuyển thành 400 MISSING_BODY.
5. Nếu hợp lệ, tăng AtomicLong và trả HTTP 201 Created, Location=/api/orders/{id}, body OrderCreated.

**Ranh giới quan trọng:** Một số lỗi body có thể được framework đóng gói khác nhau theo version/codec. Nếu trong project thực exception không rơi vào hai loại trên, dùng error handler cấp web phù hợp và test thực tế, không mở rộng bừa thành onErrorResume(Exception.class,...) làm che lỗi server. Nếu request Content-Type sai, hãy để lỗi media type ở framework thành 415 thay vì ép sang INVALID_JSON.

Trong project production, nên tách endpoint DTO khỏi persistence/domain, có service và database transaction, authorization, idempotency, metrics và validation liên quan business.

### 17.13. OrderRoutes.java

~~~java
package example.json;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRouter(
            OrderHandler handler) {
        return RouterFunctions.route()
                .POST("/api/orders", handler::create)
                .build();
    }
}
~~~

Không thêm RequestPredicates.contentType(application/json) vào route này: nếu predicate không match, request có thể trả 404 trước khi codec báo 415. Router chỉ xét method/path; body decoder xử lý media type.

## 18. Chạy project và kiểm tra với curl

Sau khi đặt source đúng package/path và tạo Gradle Wrapper tương thích, trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi server chạy ở port 8080, gửi JSON hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "customerId": "C-101",
    "deliveryMethod": "EXPRESS",
    "shipping": {
      "recipient": "Mai",
      "city": "Ha Noi",
      "postalCode": "10000"
    },
    "lines": [
      {"sku": "BOOK-01", "quantity": 2}
    ]
  }'
~~~

Nếu đây là lệnh hợp lệ đầu tiên sau startup, kỳ vọng HTTP 201 Created, Location=/api/orders/1 và body tương đương:

~~~json
{"id":1,"deliveryMethod":"EXPRESS","lineTypes":1}
~~~

Không phụ thuộc thứ tự key JSON hoặc ID cố định sau nhiều request. API minh họa chỉ cấp ID, không lưu đơn vào cơ sở dữ liệu.

### 18.1. Unknown property ở root

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "isAdmin": true,
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Với strict config, JSON bị từ chối khi deserialize. HTTP mong đợi là 400 và payload kiểu:

~~~json
{"code":"INVALID_JSON","message":"Malformed or incompatible JSON","fields":[]}
~~~

### 18.2. Unknown property ở nested object

Gửi shipping.gps:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000",
    "gps": "unknown"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Cũng kỳ vọng 400 INVALID_JSON khi strict mapper thực sự áp dụng đến Address. Đây là test quan trọng để chứng minh strictness không chỉ ở root.

### 18.3. Enum string sai

Thay deliveryMethod="EXPRESS" thành "SAME_DAY". Enum không có hằng SAME_DAY nên kỳ vọng 400 INVALID_JSON, không chuyển sang STANDARD.

### 18.4. Enum number sai kiểu hợp đồng

Thay deliveryMethod="EXPRESS" thành deliveryMethod=1 (JSON number). Nhờ fail-on-numbers-for-enums=true, kỳ vọng 400 INVALID_JSON. Nếu tắt cờ này trên Jackson 2, 1 có thể ánh xạ sang EXPRESS theo ordinal, gây API trở nên mong manh khi thứ tự enum đổi.

### 18.5. Nested validation sai

Đổi shipping.city thành "" hoặc lines[0].quantity thành 0. JSON vẫn deserialize được, nhưng @NotBlank hoặc @Min khiến Validator trả 400 VALIDATION_FAILED. Body error có danh sách fields như shipping.city hoặc lines[0].quantity, không có raw input.

## 19. WebTestClient integration tests

Test dưới đây dùng **HTTP server thực với RANDOM_PORT** để kiểm tra route, JSON decoder đang được Boot cấu hình, validation và HTTP response. Nó không chỉ gọi trực tiếp một ObjectMapper giả định.

Tệp src/test/java/example/json/JsonContractApplicationTests.java:

~~~java
package example.json;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class JsonContractApplicationTests {

    @Autowired
    WebTestClient client;

    private static final String VALID_JSON = """
            {
              "customerId":"C-101",
              "deliveryMethod":"EXPRESS",
              "shipping":{
                "recipient":"Mai",
                "city":"Ha Noi",
                "postalCode":"10000"
              },
              "lines":[
                {"sku":"BOOK-01","quantity":2}
              ]
            }
            """;

    @Test
    void validNestedPayloadReturns201() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID_JSON)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.deliveryMethod").isEqualTo("EXPRESS")
                .jsonPath("$.lineTypes").isEqualTo(1);
    }

    @Test
    void unknownRootFieldIsRejected() {
        String json = VALID_JSON.replace(
                "\"customerId\":\"C-101\"",
                "\"customerId\":\"C-101\",\"isAdmin\":true");

        expectInvalidJson(json);
    }

    @Test
    void unknownNestedFieldIsRejected() {
        String json = VALID_JSON.replace(
                "\"city\":\"Ha Noi\"",
                "\"city\":\"Ha Noi\",\"gps\":\"secret\"");

        expectInvalidJson(json);
    }

    @Test
    void invalidEnumStringIsRejected() {
        String json = VALID_JSON.replace(
                "\"EXPRESS\"", "\"SAME_DAY\"");

        expectInvalidJson(json);
    }

    @Test
    void numericEnumIsRejected() {
        String json = VALID_JSON.replace(
                "\"deliveryMethod\":\"EXPRESS\"",
                "\"deliveryMethod\":1");

        expectInvalidJson(json);
    }

    @Test
    void nestedBlankCityFailsValidation() {
        String json = VALID_JSON.replace(
                "\"city\":\"Ha Noi\"", "\"city\":\"\"");

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void nestedQuantityZeroFailsValidation() {
        String json = VALID_JSON.replace(
                "\"quantity\":2", "\"quantity\":0");

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void missingBodyReturnsBadRequest() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("MISSING_BODY");
    }

    private void expectInvalidJson(String json) {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("INVALID_JSON");
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

**Điểm QA:** Java test helper dùng String.replace với những đoạn có mặt chính xác trong VALID_JSON (không có khoảng trắng quanh dấu hai chấm ở cùng dòng), nên thực sự thay đổi đầu vào; test không chỉ gửi lại JSON hợp lệ. VALID_JSON là text block của Java 17. Với test environment có custom exception handlers, cần điều chỉnh assertion theo API contract được triển khai và xác minh code thực.

Thêm regression tests nếu dự án cần: JSON syntax hỏng, duplicate field, array rỗng, phần tử list null, shipping null, missing deliveryMethod, wrong type, body quá lớn, Content-Type text/plain, trailing tokens và oversized nested structures.

## 20. Vấn đề null, missing field và primitive trong JSON

Java type quyết định rất nhiều hành vi khi deserialize:

~~~java
record BadLine(String sku, int quantity) {}
record BetterLine(String sku, Integer quantity) {}
~~~

Với BadLine, nếu quantity thiếu/null và không bật strict primitive feature, Jackson 2 có thể cung cấp default số 0, nên ứng dụng không biết client thật sự gửi 0 hay không gửi. Với BetterLine, thiếu/null có thể thành Java null, dễ bị @NotNull phát hiện.

Các chiến lược rõ ràng:

- Dùng boxed Integer/Long thay primitive cho trường input required nếu cần nhận diện thiếu.
- Dùng @NotNull cùng @Min/@Max.
- Dùng @NotBlank cho chuỗi required, @NotEmpty cho collection.
- Dùng @Valid cho nested object và list elements.
- Nếu missing và explicit null phải có behavior khác nhau, cần schema/creator hoặc representation có presence tracking.
- Không dùng @JsonInclude(NON_NULL) để suy ra input validation; nó chủ yếu liên quan serialization của response.

Jackson 2 còn có FAIL_ON_NULL_FOR_PRIMITIVES, FAIL_ON_MISSING_CREATOR_PROPERTIES, FAIL_ON_NULL_CREATOR_PROPERTIES. Chúng có semantics riêng, có thể hữu ích trong contract nghiêm ngặt nhưng dễ ảnh hưởng đến nhiều DTO. Không bật toàn bộ chỉ để sửa một field; phải thử với test cụ thể.

## 21. Numeric coercion và trường hợp enum số

Jackson 2 có thể coerce dữ liệu giữa các kiểu, ví dụ JSON string "2" sang numeric property trong một số cấu hình, hoặc number sang enum ordinal nếu không cấm. Những thao tác đó không tương đương với validation.

Với public API yêu cầu JSON type chặt, ngoài fail-on-numbers-for-enums, có thể cấu hình Jackson CoercionConfig trong Jackson 2 và kiểm thử các đầu vào:

- "quantity":"2" (chuỗi) thay vì quantity:2 (số).
- "deliveryMethod":1 (số) thay vì "EXPRESS".
- "lines":{} thay vì array.
- "shipping":[] thay vì object.
- Empty string cho object nested.
- Float 1.2 cho Integer.
- Null cho primitive và boxed type.

Không nên dựa vào behavior coercion mặc định của một Jackson version mà không có contract tests; các cờ/naming APIs thay đổi theo phiên bản. Dùng DTO và validation đã có để đưa lỗi về đúng ranh giới.

## 22. JSON tree và dữ liệu mở rộng có kiểm soát

Khi một nguồn JSON thực sự có nhiều field thay đổi, dùng DTO tĩnh strict có thể không phù hợp. Có thể chọn JsonNode hoặc Map<String, JsonNode> cho phần payload mở rộng:

~~~java
public record PartnerPayload(
        String id,
        Map<String, JsonNode> metadata
) {
}
~~~

Snippet cần import Map và com.fasterxml.jackson.databind.JsonNode cho Jackson 2. Nó không có nghĩa mọi metadata được cho phép làm gì cũng được. Cần:

- Giới hạn key được chấp nhận hoặc validate namespace.
- Giới hạn tổng số key, depth, string length và payload size.
- Không cho metadata điều khiển authorization hoặc SQL query không được ràng buộc.
- Không log nguyên token/password.
- Cân nhắc schema version và compatibility của payload mở.

Khi mapping vào JsonNode, Jackson lưu cây JSON thay vì gán từng field của domain DTO. Do đó FAIL_ON_UNKNOWN_PROPERTIES không thể thay thế JSON Schema validation cho raw tree.

## 23. Kiểm tra lỗi duplicate keys và tấn công tài nguyên

Một JSON document có thể lặp key:

~~~json
{
  "deliveryMethod": "STANDARD",
  "deliveryMethod": "EXPRESS"
}
~~~

Nhiều parser/binder dùng giá trị sau cùng hoặc xử lý duplicate theo cơ chế riêng. JSON lặp field có thể gây **parser differential** giữa gateway, WAF, chữ ký payload và backend. Với API nhạy cảm, cần xác định chính sách duplicate keys ở cả gateway và Jackson, bật strict duplicate detection nếu phù hợp và test thực tế.

Không nhầm FAIL_ON_READING_DUP_TREE_KEY (tập trung tree model) với cơ chế strict duplicate detection ở parser khi binding DTO. Chúng không có phạm vi hoàn toàn giống nhau.

Đồng thời cần kiểm soát:

- Kích thước HTTP body ở proxy/server và codec.
- Độ sâu nesting và số phần tử list.
- Chuỗi và số quá dài.
- Multipart/file payload ở endpoint khác.
- Rate limit, request timeout và cancellation.
- Mức độ chi tiết của JSON error logging.

Bảo vệ tài nguyên không thể dựa duy nhất vào @Valid sau khi toàn bộ body đã được decode, bởi một payload quá lớn có thể tiêu tốn tài nguyên trước bước validation.

## 24. Dùng log và tracing để chẩn đoán lỗi JSON

Khi gặp 400 ở production:

1. Kiểm tra Content-Type và media type của endpoint.
2. Phân biệt parser syntax error, mapping error và Bean Validation bằng exception type.
3. Xác định JSON path nếu có nhưng sanitize dữ liệu.
4. Xác nhận strictness theo HTTP mapper/codec đang được dùng.
5. Xem schema version và client version; có phải client mới thêm field?
6. Kiểm tra enum wire values; có đổi tên/hằng hoặc client gửi số?
7. Kiểm tra cascade @Valid và nullable fields trong nested DTO.
8. Xem giới hạn body/nesting nếu lỗi chỉ xảy ra với payload lớn.
9. Reproduce bằng WebTestClient từ payload đã loại thông tin nhạy cảm.
10. Sau sửa, bổ sung test để ngăn lỗi quay lại.

Các metrics hữu ích: số lần INVALID_JSON, VALIDATION_FAILED, UNSUPPORTED_MEDIA_TYPE; tỷ lệ theo route và client version; số lỗi unknown field khi rollout strict mode; tỷ lệ rejected enum values. Tránh dùng raw field value làm metric label vì gây cardinality và có nguy cơ rò PII.

## 25. Chiến lược forward compatibility và rolling upgrade

Khi client/server triển khai lệch phiên bản, strictness là quyết định hợp đồng:

- **Request command:** thường yêu cầu rõ field, enum và nested validation. Nếu client gửi field lạ, 400 giúp lộ mismatch ngay.
- **Response đọc bởi client cũ:** có thể chấp nhận unknown response fields để client cũ vẫn hoạt động khi server thêm dữ liệu.
- **Event-driven consumer:** thường cần bỏ qua extras hoặc đưa unknown enum vào dead-letter/quarantine thay vì xử lý sai.
- **Migration:** alias cũ/mới theo thời gian có giới hạn, metrics deprecation và tests cho từng client version.

Dùng OpenAPI/JSON Schema để công bố các trường required/optional, enum allowed values và mô hình nested. Nhưng tài liệu schema không thay thế runtime validation; cần duy trì code/test để không lệch nhau.

**Một ví dụ nguy hiểm:** client gửi "isAdmin":true vào request cập nhật profile, server bỏ qua field và vẫn trả 200; client có thể tưởng quyền đã được cập nhật. Strict mode trả 400 rõ ràng hơn, nhưng quyền thực tế vẫn phải được phân quyền ở service/server.

## 26. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Unknown field không bị từ chối | Boot mapper đang lenient, @JsonIgnoreProperties hoặc custom codec | Kiểm tra FAIL_ON_UNKNOWN_PROPERTIES, annotation, HTTP integration test |
| Unknown field ở nested vẫn được nhận | Type nested có ignoreUnknown, Map/JsonNode hoặc converter riêng | Kiểm tra kiểu nested và cách decode |
| Enum "EXPRESS" được chấp nhận nhưng "express" lỗi | Enum case-sensitive | Định nghĩa wire format, không tự bật insensitive tùy tiện |
| Enum số 1 được nhận | Ordinal coercion chưa bị cấm | Bật FAIL_ON_NUMBERS_FOR_ENUMS và test |
| Unknown enum biến thành null | Bật READ_UNKNOWN_ENUM_VALUES_AS_NULL | Kiểm tra null policy và @NotNull |
| Unknown enum thành UNKNOWN | Bật default enum feature + annotation | Kiểm tra use case, tránh xử lý UNKNOWN như lệnh hợp lệ |
| shipping.city rỗng vẫn được chấp nhận | Thiếu cascade @Valid hoặc thiếu Validator | Kiểm tra field annotation và validation path |
| lines[0].quantity thiếu mà thành 0 | Dùng int primitive và default | Dùng Integer + @NotNull, test missing/null |
| POST JSON trả 415 | Sai Content-Type hoặc thiếu codec | Kiểm tra headers, starter, codec |
| POST JSON trả 400 nhưng client thấy stack trace | Error handler trả exception message thô | Chuẩn hóa ApiError, sanitize |
| WebFlux.fn không validate DTO | bodyToMono chỉ decode | Inject Validator.validate sau decode |
| JSON strict trong unit test nhưng HTTP vẫn lenient | Test ObjectMapper khác HTTP mapper | Test qua RANDOM_PORT và API |
| Sau update Boot lỗi JSON import | Jackson2 vs Jackson3 đổi package/API | Theo migration guide đúng Boot version |
| JSON response bị sai tên field | Naming strategy hoặc @JsonProperty khác | Test serialized contract, kiểm tra mapper |
| Parse payload quá lớn làm nghẽn memory | Không có request/codec size limit | Giới hạn tầng server/proxy/codec |

## 27. Bài thực hành nâng cao

1. **Unknown root:** Gửi isAdmin vào JSON tạo đơn; xác nhận 400 INVALID_JSON ở strict mode. Sau đó thử lenient trên một DTO riêng và ghi sự khác biệt.
2. **Unknown nested:** Gửi shipping.gps và lines[0].notes; xác nhận đường dẫn nested bị strict mapper từ chối.
3. **Enum string:** Gửi SAME_DAY và express; ghi status, exception type và response đã sanitize.
4. **Enum ordinal:** Gửi 1/0; kiểm tra behavior trước/sau FAIL_ON_NUMBERS_FOR_ENUMS; chứng minh vì sao ordinal không thích hợp cho wire format.
5. **Enum default:** Tạo DTO event riêng có @JsonEnumDefaultValue UNKNOWN; kiểm thử client mới gửi một value lạ và policy xử lý UNKNOWN. Không áp dụng vào lệnh giao hàng thật.
6. **Nested validation:** Thử shipping=null, city="", lines=[], lines=[null], quantity=0 và quantity không được gửi; so danh sách fields.
7. **Strict creator:** Thiết kế yêu cầu phân biệt missing và explicit null; triển khai validation/presence tracking và test từng case.
8. **Error format:** Tạo mã lỗi ổn định, request ID và các field hợp lệ; bảo đảm client không thấy raw stack trace hoặc secret.
9. **Compatibility:** Tạo alias customer_id qua @JsonAlias rồi loại bỏ sau thời gian migration đã cam kết.
10. **Security:** Thử duplicate keys, payload nested sâu, body quá lớn, JSON type coercion; đặt giới hạn và đo phản ứng.
11. **Web stacks:** Thực hiện endpoint tương đương ở Spring MVC @RestController; xác minh exception type khác WebFlux nhưng API error contract giống nhau.
12. **Deploy:** Dùng cùng artifact/mapper trên staging và production, so config flags và theo dõi tỷ lệ 400 sau rollout.

Một bài thực hành đạt khi có source, HTTP requests, tests pass, JSON status/response thực tế và phân tích vì sao mỗi trường hợp lỗi ở parser, mapping, validation hay business layer. Không bịa output test hoặc benchmark khi chưa chạy trên môi trường thực.

## 28. Tự kiểm tra

1. Unknown JSON property khác null value như thế nào?
2. FAIL_ON_UNKNOWN_PROPERTIES của Jackson 2 và cấu hình mặc định Boot 3.x khác nhau ra sao?
3. Vì sao phải kiểm tra ObjectMapper của HTTP codec chứ không chỉ new ObjectMapper() trong unit test?
4. Khi nào @JsonIgnoreProperties(ignoreUnknown=true) phù hợp?
5. @JsonAlias có làm Jackson serialize bằng tên alias hay không?
6. Vì sao enum số là một hợp đồng dễ bị phá khi thay đổi thứ tự khai báo?
7. READ_UNKNOWN_ENUM_VALUES_AS_NULL và READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE khác nhau ở đâu?
8. @JsonEnumDefaultValue có tác dụng khi chưa bật feature tương ứng không?
9. Tại sao @NotNull là ràng buộc cần thiết với enum input?
10. Vì sao một Address object lồng nhau cần @Valid?
11. Vì sao lines cần cả @NotEmpty lẫn @Valid trên phần tử?
12. Integer và int khác nhau thế nào khi JSON không có quantity?
13. Khi nào decoder thất bại trước Bean Validation?
14. WebFlux.fn bodyToMono có tự chạy hết Jakarta Bean Validation không?
15. HttpMessageConverter MVC khác WebFlux codec về stack xử lý như thế nào?
16. Vì sao lỗi Content-Type nên trả 415 thay vì bị ép thành INVALID_JSON 400?
17. Vì sao không trả raw Jackson exception message cho client?
18. Trường unknown trong JsonNode có bị FAIL_ON_UNKNOWN_PROPERTIES xử lý như property DTO không?
19. Duplicate JSON keys có rủi ro gì khi gateway và backend xử lý khác nhau?
20. Spring Boot 4.x thay đổi gì đáng chú ý về Jackson packages và mapper?
21. Những test nào chứng minh strict mode áp dụng cho unknown nested properties và enum ordinal?
22. Khi nào nên dùng strict request DTO nhưng lenient response/event consumer?

## 29. Tài liệu tham khảo

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): spring.jackson.deserialization.* và các cấu hình liên quan.
- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): cách Boot 3 tích hợp Jackson.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): ServerRequest.bodyToMono, ServerResponse, error handling và codec.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): xử lý body qua reactive readers/writers.
- [Jackson 2 — DeserializationFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/DeserializationFeature.html): FAIL_ON_UNKNOWN_PROPERTIES, enum-number policy và unknown enum features.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/): @Valid cascade, constraints và collection element validation.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi Jackson 3, package, configuration properties và mapper.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm tra JSON decoder, status và response trong WebFlux.

**Kết luận:** JSON parser/mapper quyết định cấu trúc có đọc được không; Bean Validation quyết định DTO có đủ ràng buộc hay không; service quyết định nghiệp vụ có được thực hiện không. Với unknown fields và enum không hợp lệ, hãy chọn một chính sách có chủ đích và có tests. Với dữ liệu lồng nhau, phải validate xuyên qua object/list. Chỉ khi ranh giới này rõ ràng thì phản hồi lỗi JSON mới chính xác, an toàn và dễ bảo trì.
