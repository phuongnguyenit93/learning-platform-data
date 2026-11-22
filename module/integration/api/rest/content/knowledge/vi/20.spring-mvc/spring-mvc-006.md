# Jackson, ObjectMapper và quy tắc tuần tự hóa DTO

## 1. JSON là hợp đồng, không chỉ là kết quả chuyển đổi object

Trong REST API, hai phiên bản server có thể trả cùng **200 OK** nhưng JSON khác nhau: một phiên bản xuất **created_at** dạng chuỗi ISO 8601, phiên bản khác xuất timestamp dạng số; một phiên bản giữ property có giá trị null, phiên bản khác bỏ hẳn. Client có thể lỗi dù nghiệp vụ không đổi.

**Jackson** là thư viện phổ biến để chuyển đổi JSON ↔ Java object. Trong **Spring MVC**, ObjectMapper của Jackson thường được dùng thông qua **MappingJackson2HttpMessageConverter**. Thiết kế API tốt không chỉ cần serialize được DTO mà phải có **quy tắc tên field, kiểu dữ liệu, optional/null, thời gian, enum và phạm vi thông tin được phép trả**.

Bài thuộc chương **Spring MVC** của module **INTEGRATION_API_REST**. Người học kết nối hợp đồng REST (resource, URI, HTTP method/status), DTO, xác thực/phân quyền, xử lý lỗi, OpenAPI và kiểm thử bằng Java/Spring.

Sau bài, bạn cần có thể:

- Giải thích luồng **HttpMessageConverter → ObjectMapper** ở request/response.
- Dùng **request DTO và response DTO** riêng, không public JPA entity.
- Áp dụng **@JsonProperty, @JsonAlias, @JsonInclude, @JsonIgnore** và các quy tắc date/enum/number.
- Phân biệt **missing, null, default** và Bean Validation.
- Cấu hình ObjectMapper an toàn và nhất quán với Spring MVC.
- Viết **@JsonTest**, **MockMvc** và đối chiếu OpenAPI để giữ ổn định wire contract.

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring MVC, Jackson và Jakarta Validation**. Chi tiết version/module phải được kiểm chứng trong project thực tế.

## 2. Spring MVC chuyển đổi HTTP body như thế nào?

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant M as Spring MVC
    participant J as Jackson converter
    participant V as Bean Validation
    participant S as Service
    C->>M: POST /orders + Content-Type application/json
    M->>J: @RequestBody: đọc JSON bytes
    J-->>M: CreateOrderRequest
    M->>V: @Valid request DTO
    V-->>M: Hợp lệ hoặc lỗi
    M->>S: createForUser
    S-->>M: OrderResponse
    M->>J: Serialize DTO
    J-->>C: 201 + Content-Type application/json + JSON
~~~

**@RequestBody** yêu cầu MVC đọc HTTP body thành Java type. **@ResponseBody**, **@RestController** hoặc **ResponseEntity** cho phép giá trị Java được chuyển thành response body. Spring lựa chọn **HttpMessageConverter** dựa trên kiểu Java, media type và cấu hình; khi Jackson hỗ trợ JSON, converter tương ứng sử dụng ObjectMapper.

Request:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{
  "product_id": "prod-42",
  "quantity": 2,
  "shipping_address_id": "addr-8"
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-501
Content-Type: application/json
Cache-Control: no-store

{
  "id": "ord-501",
  "product_id": "prod-42",
  "quantity": 2,
  "status": "PENDING",
  "created_at": "2026-11-18T09:30:00Z"
}
~~~

**ObjectMapper không quyết định HTTP status, quyền truy cập hay transaction.** Nó chỉ đọc/ghi representation. Những trách nhiệm đó thuộc controller/service, Spring Security và tầng dữ liệu.

| Lớp | Quyết định |
| --- | --- |
| **HTTP contract** | URI/method, Content-Type/Accept, 201/400/415, Location, Cache-Control. |
| **JSON/DTO contract** | Tên field, required/optional, kiểu, null, date-time, enum. |
| **Nghiệp vụ/security** | Ai được tạo đơn, ID và trạng thái do ai quyết định, ai được đọc kết quả. |

## 3. Tách DTO đầu vào và đầu ra

Không bind trực tiếp JSON vào persistence entity rồi save. Một entity có thể có **id, tenantId, ownerId, role, status, createdAt**, trong khi client không được cấp quyền điều khiển các field đó.

Dùng Java record làm DTO rõ ràng:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
    @JsonProperty("product_id")
    @NotBlank String productId,

    @NotNull @Min(1) Integer quantity,

    @JsonProperty("shipping_address_id")
    @NotBlank String shippingAddressId
) {}

public record OrderResponse(
    String id,

    @JsonProperty("product_id")
    String productId,

    int quantity,
    OrderStatus status,

    @JsonProperty("created_at")
    Instant createdAt
) {}

public enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}
~~~

**Request DTO** chỉ chứa thông tin người gọi được phép đề xuất. **Response DTO** chỉ chứa thông tin client được phép thấy. Jackson hỗ trợ record trong các phiên bản hiện đại; với code Java 17 + Jackson được Boot 3 quản lý, có thể deserialize record bằng canonical constructor mà không cần tự viết setter.

Controller minh họa:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest body,
            Authentication caller) {

        OrderResponse created =
            service.createForAuthorizedUser(caller, body);

        return ResponseEntity
            .created(URI.create("/api/v1/orders/" + created.id()))
            .cacheControl(CacheControl.noStore())
            .body(created);
    }
}
~~~

**OrderService** là thành phần ứng dụng cần cài đặt; nó lấy tenant và quyền từ danh tính đã được xác thực, kiểm tra quy tắc nghiệp vụ và transaction. **@Valid** chỉ kiểm tra ràng buộc trên DTO, **không thay authorization hoặc unique constraint**. Với POST có session cookie và CSRF protection, request còn phải đáp ứng chính sách CSRF của ứng dụng.

## 4. Tên JSON field và những annotation thường dùng

Tên Java **productId** có thể tương ứng với JSON **product_id**. Chọn quy tắc công khai và giữ ổn định theo version API.

| Annotation/cấu hình | Tác dụng | Điều cần tránh |
| --- | --- | --- |
| **@JsonProperty("product_id")** | Đặt tên field khi đọc và ghi JSON. | Đổi tên property mà không cập nhật OpenAPI/client. |
| **@JsonAlias("productId")** | Chấp nhận alias **khi deserialize**, thường không đổi output name. | Giữ nhiều tên mâu thuẫn khiến request nhập nhằng. |
| **@JsonIgnore** | Bỏ một property khỏi Jackson binding theo ngữ nghĩa annotation. | Coi đây là cơ chế phân quyền duy nhất. |
| **@JsonInclude(NON_NULL)** | Bỏ property có Java value null khi serialize. | Làm mất phân biệt absent với explicit null. |
| **@JsonFormat** | Tùy chỉnh định dạng date/time hoặc kiểu khác. | Dùng nhiều format khác nhau cho cùng loại dữ liệu. |
| **@JsonCreator** | Điều khiển cách khởi tạo type khi đọc JSON. | Tạo constructor mapping mơ hồ khi không cần thiết. |

Khi di trú tên field, có thể chấp nhận dạng cũ:

~~~java
public record CreateOrderRequest(
    @JsonProperty("product_id")
    @JsonAlias("productId")
    @NotBlank String productId,

    @NotNull @Min(1) Integer quantity,

    @JsonProperty("shipping_address_id")
    @NotBlank String shippingAddressId
) {}
~~~

Request dùng **productId** có thể đọc được, nhưng JSON response công bố **product_id**. Nếu client gửi **cả product_id và productId**, cần xác định hành vi, tốt nhất từ chối trường hợp nhập nhằng ở lớp contract/validation; không dựa vào “field xuất hiện sau sẽ thắng”.

Có thể cấu hình **PropertyNamingStrategies.SNAKE_CASE** trên mapper cho toàn API, nhưng thay đổi naming strategy toàn cục dễ làm đổi nhiều endpoint cũ. Với dự án có hợp đồng đã triển khai, annotation cục bộ hoặc mapping theo API version thường dễ kiểm soát hơn.

## 5. Missing, null, empty và giá trị mặc định

Ba input sau không hoàn toàn cùng ngữ nghĩa:

~~~json
{"product_id":"prod-42","quantity":2}
~~~

~~~json
{"product_id":"prod-42","quantity":2,"shipping_address_id":null}
~~~

~~~json
{"product_id":"prod-42","quantity":2,"shipping_address_id":""}
~~~

| Giá trị | Ý nghĩa |
| --- | --- |
| **Missing property** | Client không gửi trường. Server có thể áp default hoặc báo thiếu theo schema. |
| **Explicit null** | Client gửi giá trị null có chủ đích; có thể khác missing. |
| **Empty string** | Giá trị kiểu string hợp lệ về cú pháp, nhưng có thể vi phạm @NotBlank. |
| **0** | Giá trị số bằng 0; không phải missing và có thể vi phạm min. |

Dùng **Integer + @NotNull + @Min(1)** cho quantity giúp phân biệt việc thiếu với một số hợp lệ. Nếu dùng primitive **int**, một số trường hợp thiếu/null có thể bị chuyển thành **0** tùy cấu hình, khiến việc phát hiện thiếu khó hơn.

**@JsonProperty(required = true)** không phải thay thế chung cho Bean Validation: hiệu lực phụ thuộc creator binding, cách deserialize và cấu hình mapper. Hãy ghi **required** trong OpenAPI, dùng @NotNull/@NotBlank và test request **thiếu field**, **field null**, **field rỗng**.

Với output:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record TrackingResponse(String orderId, String trackingCode) {}
~~~

Nếu trackingCode null, property có thể bị **bỏ khỏi JSON**. Điều này khác với JSON có **"trackingCode": null**. Nếu một collection rỗng có ý nghĩa, giữ **items: []** thay vì dùng NON_EMPTY làm biến mất cả property.

**PATCH lưu ý riêng:** nếu contract phân biệt **missing = giữ nguyên** và **null = xóa**, DTO record nullable thông thường có thể làm mất phân biệt này. Cân nhắc **JSON Merge Patch**, JsonNode kiểm tra sự hiện diện, hoặc wrapper mang ba trạng thái thay vì dùng create DTO cho PATCH.

## 6. Instant và định dạng thời gian nhất quán

Các thời điểm nghiệp vụ như **createdAt, completedAt, paidAt** nên dùng type có mốc tuyệt đối, ví dụ **Instant**:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("created_at") Instant createdAt
) {}
~~~

Ví dụ JSON mong muốn:

~~~json
{"id":"ord-501","created_at":"2026-11-18T09:30:00Z"}
~~~

Với **JavaTimeModule** (jackson-datatype-jsr310) và cấu hình xuất date/time thành chuỗi, Instant có thể serialize theo ISO 8601. Spring Boot thường cung cấp cấu hình Jackson/Java Time qua dependency phù hợp, nhưng phải **kiểm tra mapper thực tế và test output**. Mapper tự tạo bằng **new ObjectMapper()** có thể thiếu module/cấu hình cần thiết.

Chọn Java time type theo ý nghĩa:

- **Instant:** thời điểm tuyệt đối, dễ thống nhất UTC.
- **OffsetDateTime:** thời điểm kèm offset; phải thống nhất có giữ offset khi serialize không.
- **LocalDate:** ngày theo lịch như ngày sinh/ngày giao hàng, không phải timestamp.
- **LocalDateTime:** không chứa timezone; không dùng để biểu diễn một sự kiện toàn cầu nếu thiếu ngữ cảnh.

Đừng trả chuỗi mơ hồ như **18/11/2026 16:30** không ghi timezone. **@JsonFormat(pattern = ..., timezone = "UTC")** dùng được khi contract yêu cầu, nhưng áp dụng tràn lan ở mỗi DTO dễ tạo nhiều chuẩn. Kiểm thử bằng cách parse timestamp, không suy số lượng chữ số fractional seconds luôn cố định.

## 7. Số, tiền, enum và collection

**Không dùng double làm nguồn sự thật cho tiền.** Có thể biểu diễn tiền bằng số nguyên ở đơn vị nhỏ đã được hợp đồng định nghĩa:

~~~java
public record MoneyResponse(
    String currency,
    long amountMinor
) {}
~~~

~~~json
{"currency":"VND","amountMinor":120000}
~~~

Nếu dùng **BigDecimal**, cần thống nhất scale/rounding và biểu diễn JSON number hay string. JavaScript Number không biểu diễn chính xác mọi số nguyên 64-bit (giới hạn an toàn khoảng 2^53-1). Với số rất lớn, xem xét biểu diễn **string** và định nghĩa schema tương ứng.

Enum mặc định thường được serialize bằng **tên hằng Java**, ví dụ **"PENDING"**; không nên xuất **ordinal 0/1/2** vì thay đổi thứ tự enum làm thay đổi ý nghĩa. Khi cần wire value ổn định độc lập tên Java, dùng mapping rõ (ví dụ @JsonValue/@JsonCreator) và test round-trip. Client cũ có thể không nhận ra giá trị enum mới; việc thêm trạng thái phải có chiến lược tương thích.

Với collection:

- Mảng rỗng biểu diễn **[]** nếu schema yêu cầu, không tự đổi thành null/absent.
- Map JSON có key kiểu string; không dựa tùy tiện vào toString của enum/object làm key.
- Không hứa thứ tự cố định nếu service trả một Set không có thứ tự; sorting của API phải xác định ở nghiệp vụ/SQL.
- Đừng ép nhị phân lớn vào JSON base64 khi media type binary phù hợp hơn.

## 8. Cấu hình ObjectMapper một lần, dùng nhất quán

**ObjectMapper** được thiết kế để tái sử dụng giữa các request **sau khi cấu hình hoàn tất**. Không tạo **new ObjectMapper()** mỗi lần controller chạy: mapper mới có thể khác cấu hình Spring MVC về JavaTimeModule, naming, null, enum hoặc custom serializer.

Trong Spring Boot 3.x, có thể tùy chỉnh Jackson thông qua **Jackson2ObjectMapperBuilderCustomizer** ở những cấu hình tương thích:

~~~java
@Configuration
public class JsonConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> {
            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
            builder.featuresToEnable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        };
    }
}
~~~

Ví dụ chọn **date/time string** và **strict unknown fields**. Đây là quyết định API minh họa; bật FAIL_ON_UNKNOWN_PROPERTIES trên toàn ứng dụng có thể phá tương thích với client dùng field mở rộng. Nếu ứng dụng tự khai báo ObjectMapper, HttpMessageConverter hoặc có nhiều mapper, phải kiểm tra customizer có thực sự áp dụng cho converter HTTP hay không.

Có thể inject mapper đã cấu hình:

~~~java
@Service
public class AuditJsonWriter {
    private final ObjectMapper mapper;

    public AuditJsonWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String write(Object value) throws JsonProcessingException {
        return mapper.writeValueAsString(value);
    }
}
~~~

Audit/event có thể có contract khác JSON API; khi khác, dùng ObjectWriter/ObjectReader hoặc mapper riêng cấu hình cố định. **Không mutate shared mapper theo từng request**: cấu hình động giữa nhiều thread có thể khiến behavior khó dự đoán.

## 9. Lỗi parse, deserialize và validation thuộc nhánh HTTP nào?

| Tình huống | Bước lỗi | Phản hồi thường dùng |
| --- | --- | --- |
| JSON sai cú pháp | Jackson parser | **400 Bad Request** |
| JSON đúng nhưng không thể ánh xạ vào DTO | Jackson deserializer | **400 Bad Request** |
| DTO đọc được nhưng @NotBlank/@Min sai | Bean Validation | **400** trong cấu hình Spring MVC thường gặp |
| Content-Type là text/plain, endpoint chỉ nhận JSON | Request media type | **415 Unsupported Media Type** |
| Accept yêu cầu XML, server chỉ trả JSON | Response negotiation | **406 Not Acceptable** khi áp dụng |
| Serialize response lỗi vì quan hệ vòng hay mapper sai | Serialize phía server | **5xx**, không đổi thành lỗi input 400 |

Ví dụ:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json

{"product_id":"prod-42","quantity":"two","shipping_address_id":"addr-8"}
~~~

Với quantity là **Integer**, chuỗi **"two"** thường gây lỗi đọc JSON. Nhưng Jackson có cơ chế **type coercion** tùy cấu hình; chuỗi **"2"** có thể được chấp nhận như số nguyên. Nếu API yêu cầu loại JSON number nghiêm ngặt, cần cấu hình coercion và test tương ứng; **FAIL_ON_UNKNOWN_PROPERTIES không kiểm soát loại chuyển đổi này**.

Response lỗi có thể theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-request",
  "title": "Invalid request body",
  "status": 400,
  "detail": "Trường quantity phải là số nguyên hợp lệ."
}
~~~

Dùng **@RestControllerAdvice** hoặc handler thống nhất để xử lý **HttpMessageNotReadableException**, **MethodArgumentNotValidException**. Không trả raw payload có PII, Java class name, SQL hay stack trace cho client. Cũng không catch mọi JsonProcessingException rồi trả 400: **lỗi serializer khi ghi response** thuộc trách nhiệm server.

## 10. JSON binding không thay authorization

Ví dụ nguy hiểm:

~~~java
@GetMapping("/users/{id}")
public UserEntity get(@PathVariable String id) {
    return repository.findById(id).orElseThrow();
}
~~~

Entity có thể chứa **passwordHash, role, secret, audit fields** hoặc quan hệ lazy/bidirectional. Serialize JPA entity trực tiếp có nguy cơ rò thông tin, lỗi lazy loading, N+1 query hoặc vòng lặp vô hạn. **@JsonIgnore** trên vài field không đảm bảo an toàn khi entity phát triển.

Dùng response DTO **whitelist field** và kiểm tra quyền trước:

~~~java
public record PublicUserResponse(String id, String displayName) {}

@GetMapping("/users/{id}")
public PublicUserResponse get(
        @PathVariable String id, Authentication caller) {

    UserEntity user = service.findVisibleUser(caller, id);
    return new PublicUserResponse(
        user.getPublicId(), user.getDisplayName());
}
~~~

Quy tắc bảo mật:

1. **Tách input DTO và output DTO**, không bind JSON vào entity rồi save. Server lấy tenant/owner/role/status từ principal và nghiệp vụ.
2. **Authorize ở service/repository** trước khi trả representation; DTO không phải biện pháp phân quyền.
3. Đặt giới hạn **body bytes, số phần tử, độ sâu JSON, độ dài string** tại ingress/parser tương thích version Jackson, giảm rủi ro DoS.
4. Quyết định xử lý **duplicate keys**. JSON chứa hai quantity khác nhau là nguy hiểm cho giao dịch. Có thể bật **strict duplicate detection** cho Jackson JsonFactory và test thay vì mặc định field sau thắng.
5. Tránh **polymorphic default typing** cho input không tin cậy hoặc cơ chế chấp nhận Java class name do client chọn; dùng DTO/discriminator nằm trong allowlist nếu cần.
6. Không log payload có token, PII, secret. Khi log lỗi parsing, giới hạn độ dài và redaction.

Ví dụ client cố gán dữ liệu không được phép:

~~~json
{
  "product_id": "prod-42",
  "quantity": 2,
  "shipping_address_id": "addr-8",
  "tenant_id": "another-tenant",
  "status": "CONFIRMED"
}
~~~

Với API strict, **unknown fields bị từ chối** theo hợp đồng. Với API tolerant, field dư có thể bị bỏ qua nhưng **không được ảnh hưởng domain entity**. Trong cả hai, Spring Security và service phải quyết định tenant và trạng thái. Trả **Cache-Control: no-store** khi response nhạy cảm theo chính sách, không dựa vào JsonIgnore để bảo vệ cache.

## 11. Cùng hợp đồng trong OpenAPI 3.1

Schema JSON phải khớp DTO, không chỉ dùng mô tả “application/json”.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      summary: Tạo đơn hàng
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Đơn hàng đã được tạo
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          description: JSON hoặc dữ liệu không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền tạo }
        '415': { description: Request media type không hỗ trợ }
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    CreateOrder:
      type: object
      additionalProperties: false
      required: [product_id, quantity, shipping_address_id]
      properties:
        product_id: { type: string, minLength: 1 }
        quantity: { type: integer, minimum: 1 }
        shipping_address_id: { type: string, minLength: 1 }
    Order:
      type: object
      required: [id, product_id, quantity, status, created_at]
      properties:
        id: { type: string }
        product_id: { type: string }
        quantity: { type: integer, minimum: 1 }
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        created_at:
          type: string
          format: date-time
    Problem:
      type: object
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
~~~

**additionalProperties: false** thể hiện request strict. Nếu JSON deserializer của runtime lặng lẽ bỏ unknown fields, OpenAPI và code đang không thống nhất. **required** của JSON Schema không tự động đảm bảo tất cả trường bị thiếu gây lỗi Spring; Bean Validation và test phải xác minh.

Nếu response **created_at** có type string/date-time, không được chuyển sang epoch number mà không cập nhật schema và client. **OrderStatus** có enum trong spec, nên Jackson không tự serialize ordinal hay một chuỗi khác. OpenAPI security scheme mô tả cách xác thực, còn thực thi authz vẫn do Spring Security/service.

## 12. @JsonTest kiểm tra Java ↔ JSON

**@JsonTest** của Spring Boot giúp kiểm thử serializer/deserializer với JacksonTester mà không cần chạy toàn bộ MVC.

~~~java
@JsonTest
class OrderJsonTest {
    @Autowired
    private JacksonTester<CreateOrderRequest> requestJson;

    @Autowired
    private JacksonTester<OrderResponse> responseJson;

    @Test
    void parsesSnakeCaseRequest() throws Exception {
        String raw = """
            {"product_id":"prod-42",
             "quantity":2,
             "shipping_address_id":"addr-8"}
            """;

        CreateOrderRequest dto = requestJson.parseObject(raw);

        assertThat(dto.productId()).isEqualTo("prod-42");
        assertThat(dto.quantity()).isEqualTo(2);
        assertThat(dto.shippingAddressId()).isEqualTo("addr-8");
    }

    @Test
    void writesInstantAsText() throws Exception {
        OrderResponse dto = new OrderResponse(
            "ord-501", "prod-42", 2, OrderStatus.PENDING,
            Instant.parse("2026-11-18T09:30:00Z"));

        var output = responseJson.write(dto);
        assertThat(output)
            .extractingJsonPathStringValue("@.created_at")
            .isEqualTo("2026-11-18T09:30:00Z");
    }
}
~~~

Cần import JacksonTester, AssertJ, JUnit và dependency phù hợp. Nếu mapper runtime dùng custom module/converter mà slice test không load, thêm cấu hình tương ứng hoặc kiểm thử với context MVC thật.

**@JsonTest không tự chạy @Valid** theo pipeline controller: record có trường missing có thể được deserialize thành null, và chỉ bị bác bỏ khi MVC gọi Bean Validation. Vì vậy cần cả test thuần JSON lẫn test HTTP.

| Tình huống Jackson test | Kết quả cần kiểm chứng |
| --- | --- |
| snake_case và alias được hỗ trợ | Parse đúng, serialize tên canonical |
| Instant và LocalDate | Không xuất epoch number ngoài hợp đồng |
| Null tùy chọn và collection rỗng | Có/mất field đúng chính sách |
| Enum không nhận diện | Từ chối hoặc theo quy tắc version đã công bố |
| Dấu nháy, Unicode, newline | Escape/round-trip đúng |
| BigDecimal hoặc long lớn | Precision đúng với client được hỗ trợ |
| Unknown/duplicate keys | Thực thi strict/tolerant policy đã chọn |
| Field bí mật trên entity | Không tồn tại trong response DTO |

## 13. MockMvc kiểm thử trên đường HTTP

JSON slice test chưa xác minh **status, Content-Type, Location, authentication và error mapping**. Dùng MockMvc để kiểm tra HTTP contract:

~~~java
@Test
void validJsonCreatesOrder() throws Exception {
    mockMvc.perform(post("/api/v1/orders")
            .with(user("buyer").roles("BUYER"))
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"product_id":"prod-42",
                 "quantity":2,
                 "shipping_address_id":"addr-8"}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.product_id").value("prod-42"))
        .andExpect(jsonPath("$.quantity").value(2))
        .andExpect(jsonPath("$.created_at").isString())
        .andExpect(jsonPath("$.tenant_id").doesNotExist());
}

@Test
void malformedJsonGets400() throws Exception {
    mockMvc.perform(post("/api/v1/orders")
            .with(user("buyer").roles("BUYER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"quantity\":"))
        .andExpect(status().isBadRequest());
}

@Test
void wrongContentTypeGets415() throws Exception {
    mockMvc.perform(post("/api/v1/orders")
            .with(user("buyer").roles("BUYER"))
            .contentType(MediaType.TEXT_PLAIN)
            .content("quantity=2"))
        .andExpect(status().isUnsupportedMediaType());
}
~~~

Đây là skeleton: cần fixture sản phẩm/địa chỉ, imports, JSON mapper và Security đúng như ứng dụng thực. **user(...)** thuộc spring-security-test; nếu API dùng session cookie với CSRF protection thì test POST cần token CSRF thích hợp, còn Bearer token API phải kiểm thử theo cấu hình thực. Không tắt security chỉ để test pass.

Các bài test bổ sung nên gồm:

1. Thiếu quantity/null/quantity=0 và shipping_address_id rỗng → **400**, Problem Details và không tạo bản ghi.
2. Không có quyền tạo hoặc tenant khác → **401/403** theo security scheme, không đọc/ghi dữ liệu trái quyền.
3. Accept chỉ yêu cầu media type không hỗ trợ → **406** khi contract dùng strict negotiation.
4. Input có tenant_id/owner_id/status → không có mass assignment; nếu strict, trả lỗi.
5. Response Instant parse được, enum/field name khớp OpenAPI và không có field nội bộ.
6. 201 chỉ sau commit; Location trỏ đúng URI. Khi nâng Jackson/Spring, chạy lại regression tests về null/coercion/time.
7. Nếu có nhiều ObjectMapper/converter, gọi API thực để bảo đảm JSON runtime đúng với cấu hình đã test.

**MockMvc không thay được mọi integration test**: khi cần chứng minh transaction, authz và uniqueness thực tế, kiểm thử thêm qua server và database gần môi trường production.

## 14. Thay đổi serializer có thể là breaking change

| Thay đổi | Hậu quả có thể xảy ra |
| --- | --- |
| Đổi tên Java property, bỏ @JsonProperty | Đổi JSON field bất ngờ. |
| Bật NON_NULL toàn cục | Property từng xuất hiện với null nay biến mất. |
| Đổi Instant string sang epoch number | Client không parse được, OpenAPI sai. |
| Dùng enum ordinal | Thêm/đổi thứ tự hằng làm sai nghĩa. |
| Bật FAIL_ON_UNKNOWN_PROPERTIES toàn cục | Client cũ có extension field có thể bị 400. |
| Đổi chính sách coercion | Chuỗi số từng hợp lệ thành lỗi, hoặc ngược lại. |
| Cho deserializer nhận class name từ JSON | Mở rộng bề mặt tấn công và buộc client biết Java class. |

Quy trình thay đổi nên là **hợp đồng wire → DTO/mapper → OpenAPI → @JsonTest → MockMvc → integration test**. Khi cần đổi field name, có thể có giai đoạn đọc alias cũ nhưng output chỉ dùng một tên canonical. Nếu behavior không tương thích, chọn versioning/migration có kế hoạch; không coi JSON format là chi tiết implementation riêng của backend.

## 15. Bài tập: API đặt lịch giao hàng

Thiết kế **POST /api/v1/delivery-bookings** nhận JSON:

~~~json
{
  "order_id": "ord-501",
  "delivery_date": "2026-11-20",
  "time_slot": "MORNING",
  "note": null
}
~~~

Yêu cầu: order_id bắt buộc, chỉ đặt lịch cho đơn thuộc quyền của caller; delivery_date là **LocalDate**; time_slot là enum **MORNING/AFTERNOON**; note có thể missing/null theo quy tắc cần công bố. Response có **booking_id, status, created_at** theo snake_case, trong đó created_at là Instant dạng chuỗi ISO UTC. Client không được tự đặt **tenant_id, owner_id hoặc status**.

Hãy thực hiện:

1. Định nghĩa request/response record DTO, Jackson annotations và Bean Validation.
2. Viết controller Spring nhận JSON, trả **201 Created + Location** và service phân quyền.
3. Quyết định strict/tolerant unknown fields, xử lý missing/null và enum sai; nêu rõ rủi ro duplicate JSON keys.
4. Viết OpenAPI 3.1 schema với required, date/date-time, enum và nullability phù hợp.
5. Viết **@JsonTest** cho snake_case, LocalDate, Instant, enum, note null/missing và Unicode.
6. Viết ít nhất **8 MockMvc/integration tests** bao gồm 201, 400, 401/403, 415, header, no mass assignment và kiểm tra hai tenant.
7. Viết ADR ngắn: quy tắc JSON, lý do chọn strict/tolerant và cách phòng breaking changes khi cập nhật Jackson.

**Sản phẩm:** DTO, controller/service skeleton, OpenAPI, HTTP transcript, test matrix và bảng quyết định serialization.

## 16. Checklist và kết luận

| Câu hỏi | Điều cần chứng minh |
| --- | --- |
| ObjectMapper runtime và test nhất quán? | Naming, time, enum, null được serialize như nhau. |
| DTO input/output tách riêng? | Không bind entity hoặc server-owned fields từ client. |
| Required, missing, null rõ ràng? | Schema và @Valid có test phù hợp. |
| Số, thời gian, enum ổn định? | Không mất precision hoặc tự đổi wire format. |
| Unknown/duplicate JSON có chính sách? | Không để payload nhập nhằng tác động nghiệp vụ. |
| JSON serialization và security tách biệt? | Authn/authz, body limits, không lộ trường entity. |
| HTTP status của lỗi đúng? | 400/406/415 và Problem Details nếu công bố. |
| Có test JSON và HTTP? | @JsonTest, MockMvc, đối chiếu OpenAPI/runtime. |

**Kết luận:** **ObjectMapper thực hiện chuyển đổi; DTO xác định hợp đồng dữ liệu công khai.** Một REST API đáng tin phải ổn định tên field, kiểu, null/missing, date-time, enum và bảo mật; sau đó chứng minh bằng OpenAPI và HTTP tests thay vì dựa vào defaults Jackson như một cam kết không bao giờ thay đổi.




