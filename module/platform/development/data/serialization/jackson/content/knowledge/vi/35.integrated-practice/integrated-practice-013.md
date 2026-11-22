# Tích hợp DTO vào ứng dụng Spring và kiểm chứng dữ liệu HTTP

Trong ứng dụng Spring, Jackson thường được gọi tự động ở ranh giới HTTP. Khi controller nhận request có body JSON, Spring dùng một HttpMessageConverter phù hợp để đọc byte và chuyển JSON thành DTO Java. Khi controller trả về object, converter lại dùng Jackson để ghi object thành response body. Vì vậy, một DTO có thể hoạt động đúng khi gọi ObjectMapper trực tiếp nhưng vẫn gặp lỗi khi đi qua HTTP do cấu hình converter, Content-Type, Accept header, validation hoặc cách Spring xử lý exception.

Tích hợp đúng cần nhìn cả luồng dữ liệu: HTTP request đi vào controller, Jackson deserialize thành request DTO, Bean Validation kiểm tra dữ liệu, service xử lý nghiệp vụ, response DTO được tạo và Jackson serialize thành HTTP response. Kiểm chứng phải chạy qua chính Spring MVC/WebFlux pipeline mà ứng dụng sử dụng, đồng thời có fixture độc lập để xác nhận wire contract.

Bài này tập trung vào Spring Boot/Spring MVC và cách Jackson chuyển DTO qua HTTP. Các API cụ thể có thể khác giữa phiên bản Spring Framework, Spring Boot và Jackson; hãy dùng phiên bản được dependency management của dự án quản lý.

## 1. Luồng DTO qua HTTP trong Spring MVC

Một request JSON đi vào ứng dụng Spring MVC theo luồng khái quát:

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
DispatcherServlet
    |
    v
HandlerMapping / HandlerAdapter
    |
    v
HttpMessageConverter
    |
    v
Jackson ObjectMapper
    |
    v
Request DTO
    |
    v
Bean Validation
    |
    v
Controller / Service
    |
    v
Response DTO
    |
    v
Jackson ObjectMapper
    |
    v
HttpMessageConverter
    |
    v
HTTP response body
~~~

Spring MVC dùng HttpMessageConverter để chuyển đổi giữa HTTP body và object Java. Với JSON, converter thường dùng là MappingJackson2HttpMessageConverter trong hệ sinh thái Jackson 2.

Controller không cần tự gọi mapper.readValue() cho request body thông thường. Spring đọc body, chọn converter dựa trên media type và bind vào kiểu tham số của handler.

## 2. DTO là ranh giới dữ liệu của API

DTO (Data Transfer Object) mô tả dữ liệu được gửi hoặc nhận qua một ranh giới. Trong ứng dụng web, thường nên có:

- Request DTO: dữ liệu client được phép gửi.
- Response DTO: dữ liệu server cam kết trả về.
- Domain/entity model: dữ liệu và quy tắc bên trong ứng dụng.

Ví dụ:

~~~text
HTTP JSON
    |
    v
CreateOrderRequest
    |
    v
Application service
    |
    v
Order domain/entity
    |
    v
OrderResponse
    |
    v
HTTP JSON
~~~

DTO giúp kiểm soát wire contract độc lập với database schema và domain model. Nếu trả thẳng JPA entity, API có thể vô tình để lộ field nội bộ, quan hệ lazy, cấu trúc persistence hoặc cho client ghi những field không được phép.

## 3. Vì sao không nên nhận trực tiếp JPA entity?

Ví dụ entity:

~~~java
@Entity
public class UserEntity {
    @Id
    private Long id;
    private String email;
    private String passwordHash;
    private boolean admin;
    private Instant createdAt;
}
~~~

Nếu dùng entity làm tham số @RequestBody, client có thể gửi field mà ứng dụng không định cho phép thay đổi, chẳng hạn admin hoặc passwordHash. Đây là dạng mass assignment: dữ liệu đầu vào được bind trực tiếp vào một object có nhiều quyền ghi hơn API contract.

Entity cũng có thể chứa quan hệ hai chiều, lazy proxy hoặc collection lớn khiến serializer tạo vòng lặp, phát sinh truy vấn ngoài ý muốn hoặc tạo response quá lớn.

Hãy tạo request DTO chỉ có field client được phép gửi và response DTO chỉ có field API cần công bố. Service thực hiện mapping giữa DTO và domain/entity.

## 4. Thiết kế request DTO

Một request tạo đơn hàng:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerReference,
    @NotEmpty List<@Valid CreateOrderLineRequest> lines,
    @Size(max = 500) String note
) {
}
~~~

~~~java
public record CreateOrderLineRequest(
    @NotBlank String sku,
    @Positive int quantity
) {
}
~~~

Request DTO chỉ chứa thông tin đầu vào mà endpoint chấp nhận. Các field do server quản lý như database id, createdAt, payment status hoặc internal flag không nên xuất hiện trong request chỉ vì entity có các field đó.

Với Java record, Jackson cần phiên bản hỗ trợ record phù hợp. Record được hỗ trợ trong các phiên bản Jackson hiện đại; nếu dự án dùng phiên bản cũ, hãy kiểm tra yêu cầu constructor/parameter-name module hoặc dùng class DTO thông thường.

## 5. Thiết kế response DTO

Response DTO có thể là:

~~~java
public record OrderResponse(
    long id,
    String customerReference,
    String status,
    List<OrderLineResponse> lines,
    Instant createdAt
) {
}
~~~

~~~java
public record OrderLineResponse(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {
}
~~~

Response DTO định nghĩa rõ các field được trả cho client. Khi domain model thay đổi, API response có thể giữ nguyên nếu contract không cần đổi.

Không trả các field nội bộ như password hash, access token, internal notes hoặc dữ liệu vận hành chỉ vì chúng có getter trên entity.

## 6. Controller dùng @RestController

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderResponse response = orderService.create(request);
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(response);
    }
}
~~~

@RestController kết hợp @Controller và @ResponseBody cho các handler method. @RequestBody yêu cầu Spring đọc HTTP body thành kiểu Java. @Valid yêu cầu áp dụng Bean Validation trên object đã bind.

ResponseEntity cho phép endpoint kiểm soát status, header và body. Khi trả OrderResponse, Spring chọn HttpMessageConverter để serialize object.

## 7. Spring chọn HttpMessageConverter như thế nào?

Spring MVC có một danh sách HttpMessageConverter. Khi đọc request, framework xét kiểu tham số, Content-Type và converter có thể đọc kiểu đó. Khi ghi response, framework xét kiểu trả về, Accept header và media type mà converter có thể ghi.

Với JSON, MappingJackson2HttpMessageConverter dùng Jackson. Các converter khác có thể xử lý String, byte array, form data, resource, XML hoặc định dạng khác nếu được đăng ký.

Vì vậy, việc ObjectMapper hoạt động khi gọi trực tiếp không đảm bảo controller sẽ dùng đúng mapper. Spring có thể đang dùng converter với mapper được cấu hình khác, hoặc request có Content-Type khiến converter JSON không được chọn.

## 8. Content-Type và Accept là hai header khác nhau

Content-Type mô tả định dạng của request body mà client gửi:

~~~http
Content-Type: application/json
~~~

Accept mô tả định dạng response mà client muốn nhận:

~~~http
Accept: application/json
~~~

Không dùng hai header này thay thế cho nhau:

- Content-Type sai hoặc không được hỗ trợ có thể dẫn đến 415 Unsupported Media Type.
- Accept không tương thích với response có thể dẫn đến 406 Not Acceptable.
- JSON malformed hoặc bind thất bại thường dẫn đến 400 Bad Request nếu ứng dụng giữ xử lý mặc định phù hợp.

Khi kiểm thử HTTP, cần đặt cả hai header rõ ràng để test không phụ thuộc default của client hoặc framework.

## 9. Khai báo consumes và produces

Endpoint có thể khai báo media type:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

consumes giới hạn media type của request body mà handler chấp nhận. produces giới hạn media type response mà handler có thể tạo.

Nếu endpoint chỉ hỗ trợ JSON, khai báo tường minh giúp hợp đồng dễ hiểu và giúp Spring chọn handler chính xác. Nếu endpoint hỗ trợ nhiều format, cần thiết kế converter và test từng media type.

## 10. Ví dụ request và response HTTP

Request:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "customerReference": "WEB-2026-100",
  "lines": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ],
  "note": "Deliver after 5 PM"
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": 501,
  "customerReference": "WEB-2026-100",
  "status": "PENDING",
  "lines": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "unitPrice": 125000.00
    }
  ],
  "createdAt": "2026-11-12T10:15:30Z"
}
~~~

Request và response có thể có cấu trúc khác nhau. Client không cần gửi id, status, unitPrice hoặc createdAt nếu đó là dữ liệu do server tạo.

## 11. Cấu hình ObjectMapper trong Spring Boot

Spring Boot thường tự cấu hình Jackson và đăng ký mapper/converter dựa trên dependency có trong ứng dụng. Nên sử dụng cấu hình được Spring Boot quản lý để HTTP converter và các bean khác dùng cùng chính sách.

Tránh tạo một ObjectMapper thủ công trong controller hoặc service:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

Mapper này có thể thiếu JavaTimeModule, naming strategy, custom serializer, mix-in hoặc feature mà mapper HTTP của Spring đang có.

Nếu cần tùy chỉnh, hãy dùng cơ chế cấu hình Jackson của Spring Boot thay vì tự tạo mapper rời rạc.

## 12. Tùy chỉnh Jackson bằng Jackson2ObjectMapperBuilderCustomizer

Trong Spring Boot dùng Jackson 2, có thể cung cấp customizer:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );
        };
    }
}
~~~

Ví dụ này yêu cầu ngày giờ được ghi theo dạng text thay vì timestamp nếu module và kiểu dữ liệu áp dụng feature đó. Các module Java Time và thiết lập mặc định khác có thể được Spring Boot đăng ký theo classpath/version.

Không tạo thêm ObjectMapper bean một cách tùy tiện. Việc khai báo ObjectMapper bean riêng có thể khiến auto-configuration của Spring Boot lùi lại hoặc thay đổi mapper mà converter sử dụng. Nếu cần thay toàn bộ mapper, phải cấu hình đầy đủ các module và converter liên quan.

## 13. Dùng cấu hình Jackson do Spring quản lý

Trong service có thể inject mapper để xử lý dữ liệu nội bộ:

~~~java
@Service
public class EventPayloadService {
    private final ObjectMapper objectMapper;

    public EventPayloadService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }
}
~~~

Nếu mapper bean được dùng chung với MVC converter, service và HTTP có thể có cùng naming/date/null policy. Tuy nhiên, nếu service cần một format khác cho event hoặc persistence, nên tạo mapper profile có chủ đích và đặt tên rõ.

Không mutate mapper sau khi đã bắt đầu dùng. Cấu hình mapper trước khi ứng dụng nhận request để tránh behavior thay đổi giữa các thread.

## 14. Đăng ký custom module

Nếu có custom serializer/deserializer, đăng ký module vào cấu hình mapper mà Spring sử dụng:

~~~java
public class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule() {
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
~~~

Spring Boot có thể tự đăng ký bean Module với mapper được auto-configure tùy cấu hình/version. Cách khai báo chính xác cần theo phiên bản Spring Boot đang dùng.

Sau khi đăng ký, test qua MockMvc để xác nhận converter HTTP thực sự dùng module. Unit test gọi mapper riêng chỉ xác nhận module hoạt động khi được gắn vào mapper đó.

## 15. Không trộn phiên bản Jackson tùy tiện

Spring Boot dependency management thường quản lý phiên bản Jackson tương thích với phiên bản Boot. Không nên nâng riêng jackson-databind mà giữ jackson-core và module dataformat ở một phiên bản không tương thích.

Hãy:

- Dùng Spring Boot BOM/dependency management nếu dự án áp dụng.
- Kiểm tra dependency tree khi có nhiều phiên bản Jackson.
- Đồng bộ Core, Databind, Annotations và module liên quan.
- Chỉ override version khi có lý do và đã kiểm thử tương thích.

Nếu ứng dụng dùng Jackson 2, converter thường có tên MappingJackson2HttpMessageConverter. API có thể thay đổi trong thế hệ Spring/Jackson mới; hãy tham khảo Javadoc đúng version thay vì sao chép cấu hình từ project khác.

## 16. Validation DTO bằng Jakarta Bean Validation

Với Spring Boot 3 và Spring Framework 6, validation thường dùng package jakarta.validation:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    @Size(max = 100)
    String name,

    @NotBlank
    @Email
    String email,

    @Min(18)
    int age
) {
}
~~~

Đặt @Valid trên tham số @RequestBody:

~~~java
@PostMapping
public CustomerResponse create(
        @Valid @RequestBody CreateCustomerRequest request) {
    return customerService.create(request);
}
~~~

Spring bind JSON thành DTO trước, sau đó chạy Bean Validation. Nếu constraint thất bại, MVC thường ném MethodArgumentNotValidException và không gọi phần thân controller theo luồng thông thường.

Ở các phiên bản Spring Boot cũ hơn, project có thể dùng javax.validation thay vì jakarta.validation. Không trộn hai namespace trong cùng một cấu hình validation.

## 17. Phân biệt lỗi parse với lỗi validation

Hai trường hợp:

JSON sai kiểu:

~~~json
{
  "name": 123,
  "email": "mai@example.test"
}
~~~

JSON bind được nhưng vi phạm constraint:

~~~json
{
  "name": " ",
  "email": "not-an-email"
}
~~~

Trường hợp đầu có thể thất bại trong Jackson databinding tùy coercion policy. Trường hợp sau thường tạo DTO thành công rồi Bean Validation báo lỗi.

Hãy phân biệt:

- JSON syntax error: parser không đọc được cú pháp.
- Binding/type error: JSON hợp lệ nhưng không ánh xạ được vào DTO.
- Validation error: DTO được tạo nhưng vi phạm constraint.
- Business rule error: dữ liệu hợp lệ về hình dạng nhưng không hợp lệ theo nghiệp vụ.

Các nhóm lỗi này có thể có HTTP status và error body khác nhau theo API contract.

## 18. Xử lý lỗi validation bằng @RestControllerAdvice

Có thể chuẩn hóa lỗi:

~~~java
public record ApiError(
    String code,
    String message,
    List<FieldViolation> violations
) {
}

public record FieldViolation(
    String field,
    String message
) {
}
~~~

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException ex) {

        List<FieldViolation> violations =
            ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        ApiError body = new ApiError(
            "VALIDATION_FAILED",
            "Request data is invalid",
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Thông báo trả cho client nên ổn định, dễ hiểu và không chứa stack trace hoặc dữ liệu nhạy cảm. Nếu API cần đa ngôn ngữ, có thể dùng message code và MessageSource thay vì hard-code câu hiển thị.

## 19. Xử lý lỗi JSON malformed và binding

Spring MVC thường bọc lỗi đọc body trong HttpMessageNotReadableException. Có thể xử lý:

~~~java
@ExceptionHandler(HttpMessageNotReadableException.class)
public ResponseEntity<ApiError> handleUnreadableBody(
        HttpMessageNotReadableException ex) {

    ApiError body = new ApiError(
        "INVALID_REQUEST_BODY",
        "Request body is malformed or has an unsupported value",
        List.of()
    );

    return ResponseEntity.badRequest().body(body);
}
~~~

Không trả nguyên exception message cho client. Message có thể chứa tên class nội bộ, tên property, đoạn input hoặc chi tiết implementation.

Log nội bộ có thể ghi exception class, cause và trace id theo policy; không ghi toàn bộ request body.

## 20. Chuẩn hóa error response

API có thể dùng một error envelope:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request data is invalid",
  "violations": [
    {
      "field": "email",
      "message": "must be a well-formed email address"
    }
  ]
}
~~~

Các lỗi parse, validation, business và not found có thể dùng cùng cấu trúc nhưng khác code/status.

Nếu dùng ProblemDetail của Spring Framework 6, có thể chuẩn hóa theo Problem Details for HTTP APIs. Chọn một contract và giữ nhất quán giữa endpoint; không để mỗi controller tự tạo một JSON lỗi khác nhau.

## 21. Mapping business error sang HTTP status

Một số status thường gặp:

| Trường hợp | Status thường dùng |
|---|---:|
| Tạo tài nguyên thành công | 201 Created |
| Đọc/cập nhật thành công | 200 OK |
| Xóa thành công không có body | 204 No Content |
| JSON malformed hoặc request không bind được | 400 Bad Request |
| Chưa xác thực | 401 Unauthorized |
| Không có quyền | 403 Forbidden |
| Không tìm thấy tài nguyên | 404 Not Found |
| Xung đột trạng thái hoặc duplicate | 409 Conflict |
| Content-Type không hỗ trợ | 415 Unsupported Media Type |
| Accept không tương thích | 406 Not Acceptable |
| Lỗi nội bộ | 500 Internal Server Error |

Status chính xác phụ thuộc semantics endpoint và API contract. Không trả 200 cho mọi lỗi chỉ vì controller đã nhận được request.

## 22. DTO lồng nhau và @Valid cascade

Validation ở DTO cha không tự động kiểm tra mọi field của object con nếu không có cascade validation:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerReference,
    @NotEmpty List<@Valid CreateOrderLineRequest> lines
) {
}
~~~

@Valid trên generic element cho phép validation từng item của List. Có thể đặt @Valid trên field/property nested object:

~~~java
public record AddressRequest(
    @NotBlank String city,
    @NotBlank String countryCode
) {
}

public record CreateCustomerRequest(
    @NotBlank String name,
    @Valid AddressRequest address
) {
}
~~~

Nếu address bắt buộc phải có, thêm @NotNull. @Valid chỉ yêu cầu validate object khi nó hiện diện; nó không thay thế constraint bắt buộc.

## 23. Kiểm tra kích thước collection và chuỗi

Bean Validation có thể giới hạn:

~~~java
public record SearchRequest(
    @Size(max = 100) List<@NotBlank String> tags,
    @Size(max = 200) String query
) {
}
~~~

@Size giới hạn số phần tử hoặc độ dài chuỗi sau khi object đã được tạo. Nó không thay thế giới hạn HTTP body bytes vì Jackson vẫn phải đọc body trước khi validation chạy.

Để bảo vệ tài nguyên:

- Giới hạn request body ở server/gateway.
- Đặt giới hạn parser cho nesting/token nếu phù hợp.
- Giới hạn collection count ở validation/business layer.
- Đặt timeout và rate limit.

## 24. Quy tắc null, missing và default trong DTO

JSON phân biệt property bị thiếu và property có giá trị null:

~~~json
{"name": "Mai"}
~~~

~~~json
{"name": "Mai", "email": null}
~~~

Với DTO mutable có field initializer, property missing có thể giữ giá trị khởi tạo; explicit null có thể ghi đè thành null. Với record/constructor-based DTO, behavior phụ thuộc creator và cấu hình.

Không nên dựa vào default ngầm nếu giá trị đó quan trọng với API. Hãy định nghĩa rõ:

- Field bắt buộc hay optional.
- Null có được chấp nhận không.
- Missing có dùng default không.
- Empty string/list có ý nghĩa gì.
- Response có bỏ null hay luôn ghi null.

## 25. Điều khiển null trong response bằng JsonInclude

Có thể dùng:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerResponse(
    long id,
    String name,
    String middleName
) {
}
~~~

Nếu middleName là null, property có thể bị bỏ khỏi JSON. Nếu API contract yêu cầu property luôn xuất hiện với null, không dùng NON_NULL cho trường hợp đó.

Không áp dụng global NON_NULL nếu một số endpoint cần phân biệt null và missing. Có thể cấu hình ở class/property hoặc dùng response DTO khác nhau.

## 26. Tên JSON property và naming strategy

Java có thể dùng camelCase:

~~~java
public record CustomerResponse(
    String firstName,
    String postalCode
) {
}
~~~

API có thể yêu cầu snake_case:

~~~json
{
  "first_name": "Mai",
  "postal_code": "550000"
}
~~~

Cấu hình naming strategy toàn mapper:

~~~java
builder.propertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
~~~

Hoặc đặt tên riêng:

~~~java
public record CustomerResponse(
    @JsonProperty("first_name") String firstName,
    @JsonProperty("postal_code") String postalCode
) {
}
~~~

Naming strategy toàn cục ảnh hưởng nhiều DTO được mapper xử lý. Nếu chỉ một contract có tên đặc biệt, annotation rõ ràng hoặc mapper profile riêng có thể dễ kiểm soát hơn.

## 27. Alias cho tên cũ khi API tiến hóa

Nếu client cũ gửi tên property cũ, có thể dùng @JsonAlias:

~~~java
public record CustomerRequest(
    @JsonProperty("displayName")
    @JsonAlias({"name", "display_name"})
    String displayName
) {
}
~~~

@JsonAlias hỗ trợ các tên đầu vào bổ sung khi deserialize. Khi serialize, tên chính vẫn theo property name/JsonProperty.

Alias nên có kế hoạch loại bỏ và được ghi trong API migration notes. Đừng thêm alias vô hạn mà không biết client nào còn sử dụng.

## 28. Enum trong HTTP DTO

Enum mặc định thường được ghi bằng tên:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "PAID"
}
~~~

Nếu API dùng code lowercase, có thể dùng @JsonValue hoặc custom serializer:

~~~java
public enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }
}
~~~

Test HTTP phải xác nhận cả chiều đọc và ghi enum theo contract. Cần xác định behavior khi nhận enum value không biết: reject, map về UNKNOWN hoặc xử lý bằng custom deserializer.

## 29. Ngày giờ trong request/response

Với API, nên chọn kiểu Java phản ánh semantics:

- Instant cho thời điểm tuyệt đối.
- OffsetDateTime khi cần giữ offset được gửi.
- LocalDate cho ngày lịch không có thời điểm.
- LocalDateTime khi nghiệp vụ thực sự dùng local wall-clock time và có timezone context riêng.

Ví dụ response:

~~~json
{
  "createdAt": "2026-11-12T10:15:30Z",
  "businessDate": "2026-11-12"
}
~~~

Không dùng LocalDateTime để đại diện một thời điểm toàn cầu nếu API không có quy tắc timezone. Một chuỗi không có offset có thể được diễn giải khác nhau ở các vùng khác nhau.

## 30. Cấu hình Java Time và định dạng ngày giờ

Trong Spring Boot, JavaTimeModule thường được quản lý qua Jackson auto-configuration khi dependency tương ứng có mặt. Nếu tự cấu hình mapper, phải xác nhận module đã đăng ký.

Có thể tắt timestamp output:

~~~java
builder.featuresToDisable(
    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
);
~~~

Với format riêng:

~~~java
public record ReportRequest(
    @JsonFormat(pattern = "yyyy-MM-dd")
    LocalDate reportDate
) {
}
~~~

Dùng format riêng chỉ khi API contract yêu cầu. ISO-8601 thường dễ tương tác hơn với client đa nền tảng.

## 31. BigDecimal cho dữ liệu tiền tệ

Request:

~~~json
{
  "amount": 123456.7800,
  "currency": "VND"
}
~~~

DTO:

~~~java
public record MoneyRequest(
    @NotNull BigDecimal amount,
    @NotBlank String currency
) {
}
~~~

BigDecimal tránh sai số binary floating-point như double. Tuy nhiên, JSON number không bắt buộc mọi client giữ scale/trailing zeros. Nếu scale là phần contract, hãy kiểm tra serializer/parser và client; có thể dùng string decimal theo schema rõ ràng nếu cần bảo toàn lexical form.

Không dùng double cho tiền chỉ vì JavaScript client dễ xử lý. Cần xác định precision, scale, rounding mode và miền giá trị.

## 32. Kiểm soát kiểu số và overflow

Nếu DTO khai báo int:

~~~java
public record QuantityRequest(int quantity) {
}
~~~

JSON number ngoài miền int có thể khiến Jackson báo lỗi mapping hoặc bị coercion tùy cấu hình/version. Không nên giả định mọi mapper đều xử lý overflow giống nhau.

Với số lớn, dùng long hoặc BigInteger theo miền nghiệp vụ. Với decimal, dùng BigDecimal. Thêm validation như @Positive, @DecimalMin hoặc custom constraint sau khi bind.

Test các giá trị ở biên:

- Integer.MIN_VALUE / MAX_VALUE.
- Long.MIN_VALUE / MAX_VALUE.
- Số vượt miền target.
- Decimal nhiều chữ số.
- Null và string thay cho number.

## 33. Unknown property và khả năng tương thích client

Nếu client gửi field mới, server có thể:

- Từ chối unknown property.
- Bỏ qua field chưa biết.
- Giữ field trong extension map qua @JsonAnySetter.

Ví dụ:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record PartnerWebhook(
    String eventId,
    String eventType
) {
}
~~~

Với record, annotation ở class áp dụng theo Jackson hỗ trợ của phiên bản đang dùng. Cần kiểm thử behavior thực tế.

Không bật ignore unknown toàn cục chỉ để tránh lỗi mà không xem xét contract. Với endpoint nội bộ cần phát hiện producer gửi sai schema, strict mode có thể hữu ích. Với webhook đối tác cần forward compatibility, tolerant mode có thể phù hợp hơn.

## 34. Polymorphic DTO qua HTTP

Nếu request có nhiều subtype, JSON cần discriminator rõ:

~~~json
{
  "type": "card",
  "amount": 250000,
  "lastFour": "1234"
}
~~~

Ví dụ model:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "type"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPaymentRequest.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferRequest.class, name = "bank-transfer")
})
public sealed interface PaymentRequest
    permits CardPaymentRequest, BankTransferRequest {
}
~~~

~~~java
public record CardPaymentRequest(
    BigDecimal amount,
    String lastFour
) implements PaymentRequest {
}
~~~

Chỉ dùng subtype đã được cho phép. Tránh bật default typing rộng cho dữ liệu HTTP không tin cậy; type metadata tùy ý có thể mở rộng bề mặt rủi ro khi deserialize.

## 35. Content negotiation khi hỗ trợ nhiều định dạng

Nếu endpoint hỗ trợ JSON và XML, Spring cần converter tương ứng và endpoint có thể khai báo nhiều media type:

~~~java
@PostMapping(
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public OrderResponse create(
        @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Đây là ví dụ khái niệm; để XML hoạt động cần module/converter XML tương ứng và DTO có mapping XML phù hợp. Không phải cứ thêm APPLICATION_XML_VALUE là Spring tự biết chuyển mọi DTO sang XML.

Test từng cặp Content-Type/Accept và xác nhận converter được chọn. Nếu API chỉ hỗ trợ JSON, khai báo JSON rõ và trả 415/406 phù hợp cho format không hỗ trợ.

## 36. HTTP status 415 khi Content-Type không đúng

Ví dụ client gửi:

~~~http
POST /api/orders
Content-Type: text/plain

{"customerReference":"WEB-1","lines":[]}
~~~

Body có hình dạng JSON nhưng Content-Type là text/plain. Spring có thể không chọn JSON converter cho tham số @RequestBody và trả 415.

Đây là lỗi giao thức HTTP, không phải lỗi cú pháp JSON. Test cần xác nhận Content-Type chính xác.

## 37. HTTP status 406 khi Accept không phù hợp

Nếu endpoint chỉ produces application/json nhưng client gửi:

~~~http
Accept: application/xml
~~~

Spring có thể trả 406 Not Acceptable vì không có converter/representation phù hợp.

Không nên ép trả JSON bất chấp Accept nếu API contract tuân theo content negotiation. Nếu API luôn chỉ trả JSON, tài liệu hóa điều đó và kiểm tra behavior của framework.

## 38. Response body rỗng và status 204

Endpoint xóa:

~~~java
@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

204 No Content không có response body. Không cần Jackson serialize null thành JSON.

Test nên xác nhận status 204 và body rỗng. Đừng mong có Content-Type application/json khi response không có representation body.

## 39. Kiểm tra HTTP bằng MockMvc

MockMvc chạy Spring MVC request handling trong môi trường mock servlet, không cần mở cổng mạng thật. Nó vẫn có thể kiểm tra controller, argument resolver, message converter, validation và exception handling nếu cấu hình test phù hợp.

Ví dụ test:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
~~~

Tên annotation thay mock bean có thể phụ thuộc Spring Boot/Spring Framework version. Một số project cũ dùng @MockBean. Hãy dùng API có trong version quản lý bởi dự án.

## 40. Test POST request qua MockMvc

~~~java
@Test
void createsOrderFromJson() throws Exception {
    given(orderService.create(any(CreateOrderRequest.class)))
        .willReturn(new OrderResponse(
            501L,
            "WEB-2026-100",
            "PENDING",
            List.of(),
            Instant.parse("2026-11-12T10:15:30Z")
        ));

    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerReference": "WEB-2026-100",
                  "lines": [
                    {"sku": "BOOK-01", "quantity": 2}
                  ]
                }
                """))
        .andExpect(status().isCreated())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ))
        .andExpect(jsonPath("$.id").value(501))
        .andExpect(jsonPath("$.status").value("PENDING"));
}
~~~

Test này đi qua HTTP message conversion của Spring MVC. Nó xác nhận JSON request được bind thành request DTO và response DTO được serialize thành JSON.

Nếu project Java chưa hỗ trợ text block, dùng chuỗi nối hoặc fixture resource. Tránh tạo request body bằng mapper đang được kiểm thử.

## 41. Dùng fixture độc lập trong MockMvc

Thay vì nhúng JSON dài trong test:

~~~java
String requestJson = Fixtures.readUtf8(
    "http/order/create-v1-valid.json"
);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated());
~~~

Expected response có thể được so sánh với fixture:

~~~java
String expected = Fixtures.readUtf8(
    "http/order/create-v1-response.json"
);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andExpect(content().json(expected));
~~~

content().json thường so sánh JSON theo cấu trúc và có tùy chọn strictness tùy phiên bản Spring Test. Nếu cần kiểm tra field không mong muốn hoặc kiểu node cụ thể, dùng JsonNode/JsonPath assertion bổ sung.

## 42. MockMvc test validation

Fixture invalid:

~~~json
{
  "customerReference": " ",
  "lines": [
    {"sku": "", "quantity": 0}
  ]
}
~~~

Test:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(invalidJson))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.violations").isArray());
~~~

Có thể verify service không được gọi:

~~~java
verifyNoInteractions(orderService);
~~~

Điều này xác nhận request bị từ chối ở validation boundary trước khi vào nghiệp vụ.

## 43. MockMvc test JSON malformed

Fixture malformed:

~~~json
{"customerReference":"WEB-1","lines":[
~~~

Test:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(malformedJson))
    .andExpect(status().isBadRequest());
~~~

Nếu ứng dụng có @RestControllerAdvice, kiểm tra error code và shape response. Không phụ thuộc nguyên văn parser message vì nó có thể thay đổi giữa Jackson versions.

## 44. Test sai Content-Type

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.TEXT_PLAIN)
        .content(validJson))
    .andExpect(status().isUnsupportedMediaType());
~~~

Test này xác nhận endpoint không chấp nhận text/plain. Body có nội dung JSON không làm thay đổi media type mà client đã khai báo.

## 45. Test Accept không hỗ trợ

~~~java
mockMvc.perform(get("/api/orders/501")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isNotAcceptable());
~~~

Kết quả phụ thuộc produces và converter được đăng ký. Nếu ứng dụng có XML converter, XML có thể là representation hợp lệ và test cần xác nhận XML thay vì 406.

## 46. Test field name và property presence

Dùng JsonPath:

~~~java
mockMvc.perform(get("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").value("Mai"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
~~~

Nếu API dùng snake_case:

~~~java
.andExpect(jsonPath("$.first_name").value("Mai"))
~~~

Test nên xác nhận cả field cần có và field không được xuất hiện. Kiểm tra riêng field nhạy cảm giúp ngăn vô tình làm lộ dữ liệu khi DTO hoặc mapper thay đổi.

## 47. Test null và missing trong response

Nếu response policy yêu cầu bỏ null:

~~~java
mockMvc.perform(get("/api/customers/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.middleName").doesNotExist());
~~~

Nếu yêu cầu xuất null:

~~~java
.andExpect(jsonPath("$.middleName").value(nullValue()))
~~~

Cách viết matcher cần import Hamcrest tương ứng. Điều quan trọng là test phân biệt property không tồn tại và property có giá trị null.

## 48. Test ngày giờ và timezone qua HTTP

Fixture response:

~~~json
{
  "createdAt": "2026-11-12T10:15:30Z"
}
~~~

Test:

~~~java
mockMvc.perform(get("/api/orders/501"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.createdAt")
        .value("2026-11-12T10:15:30Z"));
~~~

Không dùng thời gian hiện tại trong expected. Cố định Instant trong service mock và xác nhận wire format đúng.

## 49. Test BigDecimal qua HTTP

Response fixture:

~~~json
{
  "amount": 123.4500
}
~~~

Nếu chỉ so sánh numeric value, JsonPath hoặc JsonNode có thể so sánh số theo cách phù hợp. Nếu scale/trailing zeros thuộc contract, hãy kiểm tra raw numeric token hoặc dùng String representation theo quy định API.

Đừng dùng Java double trong test để tạo expected amount. Dùng new BigDecimal("123.4500") để tránh đưa sai số binary vào dữ liệu test.

## 50. @WebMvcTest và @SpringBootTest khác nhau

@WebMvcTest tập trung vào lớp web:

- Controller.
- MVC configuration được chọn.
- HttpMessageConverter.
- Validation và controller advice theo cấu hình test.

Các dependency service thường được mock.

@SpringBootTest tải application context rộng hơn và phù hợp khi cần xác nhận cấu hình tích hợp thực tế:

- ObjectMapper bean production.
- Custom module.
- Converter configuration.
- Controller advice.
- Filter/interceptor.
- Security chain nếu được bật trong test.

Test slice nhanh và tập trung. Full context test chậm hơn nhưng xác nhận nhiều cấu hình thật hơn. Có thể dùng cả hai với mục tiêu rõ ràng.

## 51. Test HTTP thật bằng random port

Nếu cần kiểm tra server/container và network boundary, chạy Spring Boot với random port:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;
}
~~~

Gửi request qua client:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.setAccept(List.of(MediaType.APPLICATION_JSON));

HttpEntity<String> request =
    new HttpEntity<>(requestJson, headers);

ResponseEntity<String> response = restTemplate.postForEntity(
    "/api/orders",
    request,
    String.class
);
~~~

Test này đi qua HTTP server đang chạy trên port ngẫu nhiên. Nó có thể phát hiện vấn đề filter, server configuration, compression hoặc converter wiring mà MockMvc không bao phủ hoàn toàn.

## 52. WebTestClient trong ứng dụng reactive

Nếu ứng dụng dùng Spring WebFlux, request/response thường đi qua codec thay vì Spring MVC HttpMessageConverter. WebTestClient là công cụ kiểm thử HTTP phù hợp:

~~~java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    )
    .expectBody()
    .jsonPath("$.status").isEqualTo("PENDING");
~~~

WebFlux có codec configuration và backpressure model riêng. Không áp dụng trực tiếp cấu hình MappingJackson2HttpMessageConverter của MVC cho WebFlux. Hãy cấu hình Jackson2JsonEncoder/Decoder qua WebFlux codecs theo đúng phiên bản.

## 53. Test client serialization độc lập

Nếu service gọi một API khác bằng RestClient, WebClient hoặc RestTemplate, client cũng có serialization boundary:

~~~text
Service DTO
    |
    v
HTTP client converter/codec
    |
    v
Request bytes
    |
    v
Remote API
~~~

Test client cần xác nhận:

- Method và URL.
- Content-Type và Accept.
- Request DTO được serialize đúng.
- Response JSON được deserialize đúng.
- Error status được xử lý đúng.

Có thể dùng MockRestServiceServer cho RestTemplate/RestClient ở những phiên bản hỗ trợ, WebClient mock server hoặc WireMock/MockWebServer cho HTTP integration. Công cụ cụ thể phụ thuộc client stack của dự án.

## 54. Không kiểm tra chỉ bằng gọi controller method trực tiếp

Một unit test:

~~~java
OrderResponse response = controller.create(request);
~~~

chỉ kiểm tra logic method. Nó không chạy:

- HttpMessageConverter.
- Jackson HTTP serialization/deserialization.
- Content negotiation.
- Request validation được kích hoạt bởi MVC.
- Controller advice và exception resolver.
- Filter và interceptor.

Unit test controller vẫn hữu ích cho logic điều phối, nhưng không chứng minh DTO đi qua HTTP đúng. Cần ít nhất một lớp test MockMvc hoặc HTTP integration cho contract.

## 55. Kiểm tra mapper HTTP có cùng cấu hình với mapper inject

Trong một số test, có thể inject ObjectMapper và so sánh output:

~~~java
String direct = objectMapper.writeValueAsString(responseDto);
~~~

Nhưng response thực tế qua MVC còn phụ thuộc converter. Để kiểm chứng:

1. Dùng MockMvc gọi endpoint.
2. Lấy response body.
3. Parse response body bằng JsonNode hoặc so sánh với fixture.
4. Kiểm tra Content-Type và status.

Không kết luận HTTP converter dùng cùng mapper chỉ vì có một ObjectMapper bean trong context; hãy xác nhận qua request thực tế hoặc inspect converter configuration trong test.

## 56. Dùng @JsonTest cho DTO-level tests

Spring Boot có @JsonTest để kiểm tra serialization/deserialization theo cấu hình Jackson slice:

~~~java
@JsonTest
class OrderResponseJsonTest {

    @Autowired
    JacksonTester<OrderResponse> json;

    @Test
    void writesExpectedResponse() throws Exception {
        OrderResponse response = OrderFixtures.response();

        assertThat(json.write(response))
            .isEqualToJson(
                Fixtures.readUtf8(
                    "http/order/order-response-v1.json"
                )
            );
    }
}
~~~

@JsonTest phù hợp để kiểm tra DTO và mapper configuration. Nó không thay thế MockMvc test vì không kiểm tra route, status, Content-Type hoặc toàn bộ MVC request handling.

## 57. Kiểm tra custom serializer qua HTTP

Giả sử Money có custom serializer:

~~~java
public record Money(BigDecimal amount, String currency) {
}
~~~

API có thể yêu cầu:

~~~json
{
  "amount": "123.4500",
  "currency": "VND"
}
~~~

DTO:

~~~java
public record PaymentResponse(Money total) {
}
~~~

Unit test serializer xác nhận Money mapping. MockMvc test xác nhận serializer đã đăng ký vào mapper mà MVC converter sử dụng. Nếu chỉ test custom serializer riêng, có thể bỏ sót việc module không được đăng ký trong application context.

## 58. DTO và nested entity mapping

Service nên chuyển domain/entity sang response DTO:

~~~java
public OrderResponse toResponse(Order order) {
    List<OrderLineResponse> lines = order.getLines()
        .stream()
        .map(line -> new OrderLineResponse(
            line.getSku(),
            line.getQuantity(),
            line.getUnitPrice()
        ))
        .toList();

    return new OrderResponse(
        order.getId(),
        order.getCustomerReference(),
        order.getStatus().name(),
        lines,
        order.getCreatedAt()
    );
}
~~~

Mapping này nên được test riêng để xác nhận domain data chuyển thành response DTO đúng. Sau đó test HTTP xác nhận DTO được ghi đúng.

Tách mapping test và HTTP serialization test giúp định vị lỗi:

- Domain-to-DTO mapping sai.
- Jackson serialize sai.
- Spring converter không dùng đúng cấu hình.

## 59. Không gọi service hoặc repository trong custom serializer

Serializer/deserializer nên tập trung chuyển đổi representation. Nếu serializer gọi database để lấy tên khách hàng hoặc gọi service để kiểm tra quyền, mỗi lần ghi response có thể tạo N+1 query hoặc latency không ổn định.

Hãy nạp dữ liệu cần thiết trong service rồi đưa vào response DTO. Jackson chỉ chuyển DTO thành wire data.

Điều này giúp serialization dễ test, dễ benchmark và không gây side effect khi mapper chạy.

## 60. Kiểm tra lỗi body rỗng

Request có @RequestBody bắt buộc nhưng body rỗng có thể dẫn đến lỗi đọc body:

~~~http
POST /api/orders
Content-Type: application/json
Content-Length: 0
~~~

Test nên xác nhận status và error envelope theo contract. Nếu endpoint cho phép body optional, dùng required=false hoặc thiết kế endpoint khác một cách có chủ đích.

Không để body rỗng vô tình tạo DTO toàn null rồi chạy nghiệp vụ.

## 61. Kiểm tra request body quá lớn

Bean Validation chỉ chạy sau khi Jackson bind. Vì vậy, @Size trên field không bảo vệ ứng dụng khỏi body quá lớn trước khi parse.

Giới hạn nên được đặt ở:

- Reverse proxy/API gateway.
- Servlet container/request handling.
- Multipart/file upload configuration.
- Message broker.
- Bounded input stream hoặc tầng đọc body.

Ngoài body size, có thể cần giới hạn nesting depth, string length, number length và collection size.

Test tích hợp nên xác nhận request vượt giới hạn bị từ chối với status phù hợp và không làm service xử lý dữ liệu.

## 62. Kiểm tra Unicode và escaping

Fixture HTTP nên có dữ liệu Unicode:

~~~json
{
  "name": "Nguyễn Thị Mai",
  "city": "Đà Nẵng",
  "note": "A & B < C"
}
~~~

Test xác nhận:

- UTF-8 được xử lý đúng.
- Không mất dấu tiếng Việt.
- JSON escaping hợp lệ.
- String không bị encode/decode hai lần.

Đừng so sánh response bằng byte nếu không có yêu cầu canonical encoding. Parse JSON và so sánh giá trị thường bền vững hơn.

## 63. Kiểm tra JSON không bị double-encode

Một lỗi thường gặp là serialize object thành String JSON rồi trả String đó từ controller:

~~~java
@GetMapping
public String get() throws JsonProcessingException {
    return mapper.writeValueAsString(response);
}
~~~

Spring có thể coi String là response body text và áp dụng converter String, hoặc xử lý media type theo cấu hình. Nếu controller trả object:

~~~java
@GetMapping
public OrderResponse get() {
    return response;
}
~~~

Spring dùng JSON converter để serialize đúng một lần.

Chỉ tự serialize thành String khi endpoint thực sự cần trả raw JSON text và đã kiểm soát Content-Type/headers rõ ràng. Thông thường hãy trả DTO.

## 64. Tránh trả JsonNode nếu contract là DTO ổn định

Controller có thể trả JsonNode khi response động:

~~~java
public JsonNode getDynamicPayload() {
    return dynamicPayload;
}
~~~

Đây là lựa chọn hợp lý nếu dữ liệu thực sự có schema động hoặc cần proxy JSON. Nhưng với API contract ổn định, response DTO có kiểu rõ giúp:

- Dễ validate và tài liệu hóa.
- Dễ refactor.
- Dễ kiểm tra compile-time.
- Tránh field động ngoài ý muốn.

Nếu trả JsonNode, cần test schema/shape và giới hạn kích thước/nesting theo nhu cầu.

## 65. Kiểm tra field lạ trong request HTTP

Tạo fixture:

~~~json
{
  "customerReference": "WEB-1",
  "lines": [],
  "admin": true
}
~~~

Nếu API strict, test có thể mong 400 do unknown property. Nếu tolerant, test xác nhận admin bị bỏ qua và không làm thay đổi quyền. Không được để field client tự gửi có thể bật flag nhạy cảm.

Đối với request DTO, strictness là lựa chọn hợp đồng. Với webhook/event versioned, tolerant mode có thể giúp forward compatibility. Cần test và tài liệu hóa rõ.

## 66. Test backward compatibility của request DTO

Khi thêm field mới:

- Payload cũ không có field mới có còn đọc được không?
- Default của field mới có đúng không?
- Null explicit có khác missing không?
- Response cũ có thay đổi ngoài ý muốn không?
- Client cũ có hiểu response mới không?

Giữ fixture request của phiên bản API trước và chạy bằng mapper hiện tại. Nếu API có version trong path/header, tổ chức fixture theo version.

Không cập nhật fixture cũ thành shape mới rồi bỏ mất bằng chứng tương thích ngược.

## 67. Test response contract sau thay đổi DTO

Khi thêm field vào response DTO, client strict có thể bị ảnh hưởng. Test expected response đầy đủ giúp phát hiện field mới.

Nếu field mới là breaking change, cân nhắc API versioning hoặc rollout tương thích. Nếu additive field được phép, cập nhật contract fixture và tài liệu.

Không đổi tên field hoặc enum wire value chỉ vì Java property được refactor. Tên wire là contract bên ngoài.

## 68. API versioning và DTO version riêng

Có thể tách DTO theo API version:

~~~java
public record OrderResponseV1(
    long id,
    String status
) {
}

public record OrderResponseV2(
    long id,
    String status,
    Instant createdAt
) {
}
~~~

Domain service có thể dùng cùng model nội bộ, còn mapper chuyển sang response DTO phù hợp version.

Không nên dùng một DTO với nhiều cờ ẩn để phục vụ mọi version nếu nó làm wire contract khó hiểu. DTO version riêng làm rõ field và default của từng API.

## 69. Content-Length và streaming response

Khi response được ghi trực tiếp ra OutputStream, server có thể không biết Content-Length trước khi serialize. HTTP server/container có thể dùng chunked transfer encoding hoặc cơ chế framing phù hợp protocol.

Không buffer toàn bộ response chỉ để tự đặt Content-Length nếu payload lớn và server có thể stream. Nếu client hoặc gateway yêu cầu Content-Length, cân nhắc chi phí buffer và giới hạn kích thước.

Streaming response có thể giảm buffering của serialized bytes nhưng object graph vẫn có thể nằm trong heap. Với dữ liệu rất lớn, cân nhắc streaming từng phần tử thay vì tạo một List khổng lồ rồi serialize.

## 70. Streaming JSON qua HTTP

Với response dạng array lớn, có thể dùng StreamingResponseBody trong Spring MVC:

~~~java
@GetMapping(
    value = "/api/orders/export",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public StreamingResponseBody export() {
    return outputStream -> {
        try (JsonGenerator generator =
                 jsonFactory.createGenerator(outputStream)) {
            generator.writeStartArray();
            for (OrderExportRow row : exportService.streamRows()) {
                mapper.writeValue(generator, row);
            }
            generator.writeEndArray();
        }
    };
}
~~~

Đây là ví dụ minh họa. Cần kiểm tra cách đóng generator và stream theo ownership của framework, xử lý lỗi giữa chừng và transaction/cursor lifecycle. StreamingResponseBody chạy trên async executor; cần cấu hình thread pool và timeout phù hợp.

Nếu dùng repository Stream, đóng stream/release resource đúng cách sau khi ghi response. Không giữ database cursor sau khi client đã ngắt kết nối.

## 71. Phân biệt Spring MVC và WebFlux khi cấu hình Jackson

Spring MVC:

- Servlet request/response.
- HttpMessageConverter.
- MappingJackson2HttpMessageConverter với Jackson 2.
- MockMvc cho test slice HTTP.

Spring WebFlux:

- Reactive request/response.
- HttpMessageReader/HttpMessageWriter và codecs.
- Jackson2JsonDecoder/Encoder trong nhiều cấu hình Jackson 2.
- WebTestClient cho test.

Không sao chép cấu hình converter MVC sang WebFlux. Chọn API theo stack đang chạy.

## 72. Kiểm thử HTTP client và server bằng cùng fixture

Trong hệ thống service-to-service, một fixture có thể dùng ở hai nơi:

- Server test đọc fixture để xác nhận endpoint chấp nhận request.
- Client test so sánh request mà client phát ra với fixture.

Tuy nhiên, không dùng output từ client implementation để làm expected cho server test nếu cả hai cùng dùng một DTO/configuration có thể sai. Fixture phải bắt nguồn từ contract hoặc một ví dụ được duyệt.

Có thể chia fixture theo direction:

~~~text
http/
  order/
    client-request/
    server-request/
    server-response/
    client-response/
~~~

## 73. Kiểm tra response headers ngoài Content-Type

API có thể cần:

- Location khi tạo resource.
- Cache-Control.
- ETag.
- Correlation/request id.
- Content-Disposition khi tải file.
- Retry-After khi rate limit.

Jackson chỉ xử lý body. Test HTTP cần xác nhận headers và status cùng với body.

Ví dụ tạo resource:

~~~java
return ResponseEntity
    .created(URI.create("/api/orders/" + response.id()))
    .body(response);
~~~

Test:

~~~java
.andExpect(status().isCreated())
.andExpect(header().string("Location", "/api/orders/501"))
~~~

## 74. Không để error handler vô tình serialize lỗi thành 200

Nếu controller advice bắt exception rồi trả object lỗi nhưng không đặt status, framework có thể trả 200 tùy cách method được khai báo.

Dùng ResponseEntity hoặc @ResponseStatus để đặt status rõ:

~~~java
return ResponseEntity
    .status(HttpStatus.BAD_REQUEST)
    .body(error);
~~~

Test phải xác nhận cả status và error body. Client thường quyết định retry/auth/validation dựa trên status, không chỉ nội dung JSON.

## 75. Security và Jackson polymorphism trong HTTP

Không bật default typing tổng quát cho payload HTTP không tin cậy nếu không có một allowlist và thiết kế an toàn. Type metadata cho phép input ảnh hưởng đến kiểu Java được khởi tạo; cấu hình rộng có thể mở ra rủi ro deserialize.

Nếu cần polymorphism:

- Dùng base type cụ thể.
- Khai báo subtype được phép.
- Dùng discriminator ổn định.
- Từ chối subtype không biết theo policy.
- Test input có type id lạ.

Request DTO nên là kiểu đơn giản và không có behavior nguy hiểm trong constructor/setter.

## 76. Không để dữ liệu HTTP quyết định class tùy ý

Tránh các thiết kế như:

~~~json
{
  "@class": "some.runtime.Type",
  "value": "..."
}
~~~

nếu type id có thể trỏ tới class tùy ý. API nên dùng một tập subtype được công bố và ánh xạ discriminator sang các DTO an toàn.

Đối với webhook hoặc event từ bên ngoài, xác thực nguồn gửi và schema/version trước khi xử lý nghiệp vụ. Jackson deserialize không thay thế authentication/authorization.

## 77. Kiểm tra request body và logging

Không log toàn bộ request/response body mặc định. Payload có thể chứa:

- PII.
- Token hoặc credential.
- Dữ liệu thanh toán.
- Secret nội bộ.
- Nội dung người dùng.

Log metadata có kiểm soát:

- route/operation.
- content type.
- body size.
- duration.
- status.
- correlation id.
- error category.

Nếu cần debug payload, dùng sampling và redaction có kiểm soát, retention ngắn và quyền truy cập phù hợp. Không để exception message hoặc parser snippet làm lộ body ngoài ý muốn.

## 78. Kiểm tra cấu hình ObjectMapper thực tế trong integration test

Nếu cần xác nhận mapper bean:

~~~java
@SpringBootTest
class JacksonConfigurationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void usesExpectedDateConfiguration() throws Exception {
        Instant instant = Instant.parse("2026-11-12T10:15:30Z");
        String json = objectMapper.writeValueAsString(instant);
        assertEquals("\"2026-11-12T10:15:30Z\"", json);
    }
}
~~~

Ví dụ này kiểm tra mapper bean trực tiếp. Vẫn cần MockMvc/HTTP test để xác nhận MVC converter dùng cùng policy.

Nếu ứng dụng có nhiều mapper, inject bằng qualifier hoặc dùng bean name rõ ràng. Đừng dựa vào một bean ObjectMapper duy nhất nếu thực tế có mapper profile riêng.

## 79. Kiểm tra HttpMessageConverter đã đăng ký

Trong test cấu hình MVC, có thể inspect RequestMappingHandlerAdapter hoặc danh sách converter để hiểu Spring đang dùng converter nào. Tuy nhiên, test black-box qua MockMvc thường có giá trị hơn vì nó kiểm tra kết quả cuối cùng.

Nếu cần custom converter:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Chỉnh converter hiện có hoặc thêm converter có chủ đích.
    }
}
~~~

Ưu tiên extend danh sách converter hiện có nếu muốn giữ các converter mặc định. Override configureMessageConverters có thể thay đổi danh sách mặc định tùy cách cấu hình; hãy hiểu hệ quả trước khi dùng.

## 80. Dùng custom ObjectMapper cho một converter riêng

Nếu endpoint cần format khác biệt, có thể tạo converter riêng với mapper riêng và giới hạn media type hoặc target type. Cần tránh hai converter cùng có thể đọc/ghi cùng kiểu và media type nhưng có cấu hình khác nhau, vì thứ tự converter có thể ảnh hưởng kết quả.

Một cấu hình nhiều mapper nên trả lời:

- Mapper nào dùng cho public API?
- Mapper nào dùng cho partner format?
- Mapper nào dùng cho internal event?
- Converter nào chọn mapper nào?
- Endpoint nào chấp nhận media type nào?

Kiểm thử bằng HTTP để bảo đảm routing converter không mơ hồ.

## 81. Test response không có field nội bộ

Một test an toàn:

~~~java
mockMvc.perform(get("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.email").value("mai@example.test"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.admin").doesNotExist());
~~~

Nếu field nội bộ được thêm vào entity hoặc response DTO trong tương lai, test này giúp phát hiện việc vô tình công bố field đó.

## 82. Kiểm tra HTTP response có đúng shape collection

Nếu API trả danh sách:

~~~json
[
  {"id": 1, "status": "PENDING"},
  {"id": 2, "status": "PAID"}
]
~~~

Test cần xác nhận root là array, số phần tử và thứ tự nếu có ý nghĩa:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$").isArray())
    .andExpect(jsonPath("$.length()").value(2))
    .andExpect(jsonPath("$[0].id").value(1));
~~~

Đừng vô tình đổi response thành object wrapper { "items": [...] } nếu contract đang là root array, hoặc ngược lại.

## 83. Kiểm tra lỗi enum và discriminator không biết

Fixture:

~~~json
{
  "status": "UNKNOWN_NEW_STATUS"
}
~~~

hoặc:

~~~json
{
  "type": "unregistered-payment",
  "amount": 100
}
~~~

Test cần xác nhận API trả status/error code đúng và không gọi service nếu mapping thất bại. Không để lỗi subtype lạ bị chuyển thành một subtype mặc định mà không có policy.

Nếu cần forward compatibility, có thể dùng enum UNKNOWN hoặc wrapper string; hãy định nghĩa rõ behavior.

## 84. Contract test giữa producer và consumer

Khi nhiều service trao đổi JSON, fixture HTTP có thể trở thành một phần contract test:

- Producer test xác nhận response JSON.
- Consumer test xác nhận request/response fixture được đọc đúng.
- Contract test xác nhận field name, type, required/optional và enum values.

Có thể dùng OpenAPI schema, JSON Schema hoặc contract testing tool tùy hệ sinh thái. Jackson unit test chỉ xác nhận mapping; nó không tự chứng minh producer và consumer thống nhất toàn bộ API.

## 85. Kiểm tra OpenAPI và DTO annotations

Nếu dùng springdoc hoặc Swagger/OpenAPI, DTO annotations có thể được dùng để sinh schema/tài liệu. Tuy nhiên, Jackson annotation và OpenAPI schema annotation có mục đích khác nhau.

Hãy kiểm tra tài liệu sinh ra có khớp wire behavior:

- Field name.
- Required/optional.
- Nullability.
- Enum values.
- Format date/time.
- Nested object và array.
- Discriminator.

Một OpenAPI schema có thể mô tả sai nếu chỉ dựa vào tên Java hoặc thiếu annotation riêng. Test/document review nên xem cả schema lẫn HTTP fixture.

## 86. Kiểm tra Content-Type và charset

JSON trên HTTP thường dùng UTF-8. Client nên gửi application/json. Nếu charset được khai báo, server/framework có thể xử lý theo quy tắc media type và version.

Không tự chuyển body thành String bằng charset hệ điều hành. Khi đọc byte fixture trong test, dùng UTF-8 rõ ràng.

Test Unicode giúp phát hiện lỗi decode sai charset, double encoding hoặc response bị mất ký tự.

## 87. Kiểm tra gzip và compression

Nếu server/client bật gzip:

- Content-Type vẫn mô tả representation, ví dụ application/json.
- Content-Encoding mô tả compression, ví dụ gzip.
- Content-Length có thể là số byte compressed nếu được gửi.

Compression nằm ngoài Jackson serializer. Đo JSON bytes trước nén và HTTP bytes sau nén là hai metric khác nhau.

Integration test có thể gửi Accept-Encoding: gzip và xác nhận Content-Encoding nếu server hỗ trợ. Đừng so sánh compressed bytes với JSON fixture text.

## 88. Kiểm tra request bị client ngắt giữa chừng

Với body lớn hoặc streaming request, client có thể ngắt kết nối trong khi server đang đọc. Parser có thể ném IOException hoặc server container báo client abort.

Ứng dụng cần:

- Không coi mọi IOException là lỗi JSON malformed.
- Giải phóng stream/resource.
- Không tiếp tục nghiệp vụ nếu body chưa đọc đầy đủ.
- Log error category và trace id.
- Tránh retry vô hạn trên request đã bị ngắt.

Integration test cho disconnect khó hơn MockMvc; có thể dùng HTTP client thật và server test nếu luồng streaming quan trọng.

## 89. Kiểm tra timeout và giới hạn request

Độ trễ HTTP có thể đến từ:

- Client gửi body chậm.
- Server chờ body.
- Jackson parse/bind.
- Validation.
- Service/database.
- Jackson serialize.
- Client nhận response chậm.

Đặt timeout ở tầng server/client và đo các đoạn riêng. Jackson parser không phải cơ chế timeout mạng. Với request body lớn, cần cả size limit và read timeout.

## 90. Kiểm tra lỗi serialization khi tạo response

Deserialize thành công không đảm bảo serialize response luôn thành công. Custom serializer có thể ném exception, lazy entity có thể truy cập database đã đóng, hoặc object graph có vòng lặp.

Test response cần chạy endpoint thật với dữ liệu đại diện và xác nhận:

- Status đúng.
- Body đúng.
- Content-Type đúng.
- Không có exception khi serialize.
- Không phát field nội bộ.

Nếu serialization exception xảy ra sau khi response đã bắt đầu ghi, server có thể không còn khả năng trả error JSON chuẩn. Tránh tạo response stream quá sớm trước khi hoàn tất các bước có thể thất bại nếu contract yêu cầu error body nhất quán.

## 91. Kiểm tra circular reference

Entity hai chiều:

~~~text
Order -> Customer -> Orders -> Order -> ...
~~~

Nếu serialize trực tiếp, có thể xảy ra recursion hoặc cần annotation xử lý reference. DTO giúp tạo một response graph có hướng rõ ràng, không phản chiếu toàn bộ quan hệ persistence.

Nếu thực sự cần reference metadata, dùng annotation Jackson phù hợp như JsonManagedReference/JsonBackReference hoặc JsonIdentityInfo sau khi thiết kế contract. Test JSON output để xác nhận không lặp vô hạn và client hiểu được cấu trúc.

## 92. Kiểm tra Lazy Loading và N+1 khi serialize

Jackson gọi getter để lấy property. Nếu getter trên entity truy cập lazy relationship, serialization có thể kích hoạt truy vấn database.

Hậu quả:

- Response latency tăng theo số item.
- N+1 query.
- LazyInitializationException khi session đóng.
- Payload lớn ngoài dự kiến.

Mapping entity sang DTO trong transaction/service layer giúp kiểm soát dữ liệu cần nạp. Không để Jackson vô tình quyết định truy vấn database bằng cách duyệt entity graph.

## 93. Kiểm tra DTO immutable và constructor

DTO immutable giúp hạn chế trạng thái không hợp lệ:

~~~java
public record CustomerRequest(
    @NotBlank String name,
    @Email String email
) {
}
~~~

Jackson dùng creator/constructor để tạo record. Test qua HTTP cần kiểm tra:

- Property name đúng với component name hoặc JsonProperty.
- Missing/null behavior.
- Coercion type.
- Validation sau khi tạo record.

Nếu dùng class immutable có constructor riêng, có thể cần @JsonCreator và @JsonProperty hoặc parameter metadata tùy cách compile và Jackson version.

## 94. Kiểm tra field read-only và write-only

Một field có thể chỉ xuất hiện trong request hoặc response:

- Password có thể được nhận khi tạo tài khoản nhưng không bao giờ trả lại.
- createdAt chỉ được trả về do server quản lý.

Có thể dùng DTO riêng là cách rõ ràng nhất. Jackson cũng có JsonProperty.Access.READ_ONLY/WRITE_ONLY trong một số thiết kế:

~~~java
public class AccountDto {
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;
}
~~~

Nếu dùng chung DTO hai chiều, test cả request lẫn response để bảo đảm field không xuất hiện sai hướng. Với dữ liệu nhạy cảm, DTO riêng thường dễ kiểm soát hơn.

## 95. Kiểm tra naming và format theo endpoint

Một mapper global có thể áp dụng naming strategy/date format cho mọi endpoint. Nếu một đối tác cần format riêng, đừng thay đổi global mapper chỉ để đáp ứng một endpoint.

Có thể:

- Tạo DTO có annotation cụ thể.
- Tạo mapper profile riêng.
- Tạo converter riêng cho media type riêng.
- Dùng endpoint adapter chuyển DTO nội bộ sang partner DTO.

Test endpoint phải xác nhận mapper/converter phù hợp được chọn.

## 96. Tách mapping unit test khỏi HTTP integration test

Một bộ kiểm thử có thể gồm:

| Loại test | Điều cần xác nhận |
|---|---|
| DTO mapping test | Domain/entity → request/response DTO |
| Jackson DTO test | DTO ↔ JSON bằng ObjectMapper |
| MVC slice test | Route, converter, validation, status, JSON body |
| Full HTTP integration test | Server, filters, security, network behavior |
| Contract test | Producer/consumer thống nhất schema |

Không cần mọi trường hợp phải chạy full application context. Chọn test nhỏ nhất có thể chứng minh behavior cần kiểm tra, rồi có một số integration test bảo vệ đường đi HTTP quan trọng.

## 97. Một cấu trúc package tham khảo

~~~text
com.example.orders/
  api/
    OrderController.java
    request/
      CreateOrderRequest.java
      CreateOrderLineRequest.java
    response/
      OrderResponse.java
      OrderLineResponse.java
    error/
      ApiError.java
      ApiExceptionHandler.java
  application/
    OrderService.java
  domain/
    Order.java
    OrderLine.java
  infrastructure/
    persistence/
      OrderEntity.java
      OrderRepository.java
    jackson/
      JacksonConfiguration.java
~~~

Package là gợi ý, không phải quy tắc bắt buộc. Điều quan trọng là API DTO, domain và persistence model có ranh giới rõ.

## 98. Một cấu trúc test tham khảo

~~~text
src/test/java/com/example/orders/
  api/
    OrderControllerTest.java
    OrderHttpIntegrationTest.java
    ApiExceptionHandlerTest.java
  api/request/
    CreateOrderRequestJsonTest.java
  api/response/
    OrderResponseJsonTest.java
  application/
    OrderServiceTest.java

src/test/resources/http/orders/
  request/
    create-v1-valid.json
    create-v1-invalid.json
    create-v1-unknown-field.json
  response/
    create-v1-201.json
    validation-error-v1.json
~~~

Fixture request và response được tách riêng. Test DTO tập trung Jackson mapping; test controller tập trung HTTP contract.

## 99. Ví dụ end-to-end flow trong test

Một test tích hợp có thể:

1. Nạp fixture create request.
2. Gửi POST với Content-Type và Accept là application/json.
3. Xác nhận controller nhận đúng DTO bằng cách kiểm tra kết quả service hoặc response.
4. Xác nhận status 201.
5. Xác nhận Content-Type.
6. So sánh response JSON với fixture độc lập.
7. Xác nhận Location header nếu endpoint tạo resource.
8. Xác nhận không có field nội bộ.

Ví dụ này kiểm tra toàn bộ đường đi HTTP mà client quan sát. Nếu service/database được mock, đây là MVC integration test; nếu chạy database và server thật, đó là full integration test.

## 100. Checklist khi đưa DTO vào endpoint mới

Trước khi phát hành endpoint:

- Xác định request DTO và response DTO riêng.
- Không bind trực tiếp entity có field nội bộ.
- Định nghĩa field required, optional, nullable và default.
- Định nghĩa tên JSON property và enum wire values.
- Chọn kiểu số/ngày giờ phù hợp semantics.
- Thêm validation và cascade validation cho nested object.
- Chọn policy unknown property.
- Cấu hình ObjectMapper qua Spring quản lý.
- Đảm bảo custom module được HTTP converter sử dụng.
- Khai báo consumes/produces.
- Xử lý malformed body, validation và business errors.
- Trả status code và error envelope ổn định.
- Đặt request size/parser limits.
- Viết fixture read/write độc lập.
- Test bằng MockMvc hoặc WebTestClient theo stack.
- Test Content-Type, Accept, null, unknown field và Unicode.
- Kiểm tra response không lộ field nội bộ.
- Kiểm tra OpenAPI/schema nếu dự án công bố contract.

## 101. Quy trình kiểm chứng dữ liệu HTTP

Một quy trình có thể áp dụng cho mỗi endpoint:

1. Viết request DTO từ contract.
2. Viết response DTO từ contract.
3. Xác định mapping sang domain/entity và ngược lại.
4. Cấu hình validation và error handling.
5. Xác nhận mapper/converter của Spring dùng đúng module và naming/date policy.
6. Chuẩn bị fixture request độc lập.
7. Chuẩn bị fixture response expected độc lập.
8. Viết DTO-level Jackson tests.
9. Viết MockMvc/WebTestClient test cho request hợp lệ.
10. Test malformed JSON, sai type, validation, unknown property và null/missing.
11. Test Content-Type, Accept và status code.
12. Test response headers và field không được công bố.
13. Chạy full HTTP integration test cho luồng quan trọng.
14. Kiểm tra contract/schema và client tương thích.

Sơ đồ:

~~~text
API contract
    |
    v
Request DTO + Response DTO
    |
    v
Spring Jackson configuration
    |
    v
Controller + validation + service
    |
    v
HTTP fixture tests
    |
    v
MockMvc / WebTestClient
    |
    v
Full HTTP integration / contract tests
~~~

## 102. Các lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Request JSON không bind | Content-Type sai hoặc converter không phù hợp | Kiểm tra request header và converter |
| Field luôn null | Sai tên property, creator hoặc mapper config | Fixture deserialize và inspect DTO |
| Ngày giờ lỗi | Thiếu Java Time module hoặc format không khớp | Test mapper Spring và HTTP |
| Unknown field gây 400 | Strict policy đang bật | Xác định contract tolerant/strict |
| Validation không chạy | Thiếu @Valid hoặc validation dependency | Test MockMvc với fixture invalid |
| Response field bị thiếu | JsonInclude, view hoặc DTO mapping | So sánh response fixture |
| Response lộ field nội bộ | Dùng entity hoặc DTO quá rộng | Test field absence |
| 415 | Request Content-Type không được hỗ trợ | Kiểm tra consumes/converter |
| 406 | Accept không phù hợp produces | Kiểm tra Accept và response converter |
| Response JSON bị quote thêm | Controller trả JSON dưới dạng String | Trả DTO để converter serialize |
| Latency tăng khi serialize | Lazy loading hoặc custom serializer có I/O | Profile và kiểm tra DTO mapping |
| Test trực tiếp pass nhưng HTTP fail | Test bỏ qua HttpMessageConverter | Dùng MockMvc/HTTP test |

## 103. Nguyên tắc thực hành

- Dùng DTO riêng cho request và response ở ranh giới HTTP.
- Để Spring HttpMessageConverter thực hiện Jackson mapping.
- Dùng ObjectMapper được Spring Boot quản lý và cấu hình trước khi phục vụ request.
- Không tạo mapper mới trong controller hoặc mỗi request.
- Giữ phiên bản Jackson đồng bộ theo dependency management.
- Khai báo Content-Type, Accept, consumes và produces rõ ràng.
- Phân biệt parse error, binding error, validation error và business error.
- Dùng @Valid cho request DTO và cascade validation cho object/collection lồng nhau.
- Quy định rõ missing, null, empty, default và unknown property.
- Dùng BigDecimal cho decimal cần chính xác và kiểu ngày giờ phản ánh timezone semantics.
- Không bật polymorphic default typing rộng cho HTTP input không tin cậy.
- Không trả entity trực tiếp hoặc để Jackson kích hoạt lazy database access.
- Chuẩn hóa error response và HTTP status.
- Kiểm thử DTO bằng fixture độc lập.
- Kiểm thử controller qua MockMvc hoặc WebTestClient, không chỉ gọi method trực tiếp.
- Kiểm tra cả status, headers, Content-Type và response body.
- Test field bắt buộc, field không được xuất hiện, Unicode, enum, date/time và numeric boundary.
- Giới hạn body size ở tầng transport và cấu trúc parser phù hợp.
- Không log toàn bộ payload hoặc dữ liệu nhạy cảm.
- Giữ fixture theo API/schema version để bảo vệ tương thích.

Tích hợp DTO với Spring chỉ hoàn chỉnh khi dữ liệu đi qua HTTP đúng như contract mà client nhìn thấy. DTO xác định hình dạng dữ liệu, Jackson chuyển đổi giữa wire format và Java, còn Spring chọn converter, kích hoạt validation và tạo HTTP response. Khi cấu hình mapper trong application context, tách request/response DTO, xử lý lỗi rõ ràng và kiểm chứng bằng fixture qua MockMvc hoặc HTTP integration test, các lỗi chỉ xuất hiện ở ranh giới HTTP sẽ được phát hiện trước khi phát hành.
