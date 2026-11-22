# Bài tập tổng hợp từ Controller đến hợp đồng được kiểm chứng và phát hành

Một API chỉ sẵn sàng cho client khi ba phần khớp nhau: controller thực thi đúng hành vi HTTP, OpenAPI mô tả chính xác hành vi đó, và quy trình phát hành cung cấp đúng tài liệu đã được kiểm tra. Việc mở được Swagger UI hoặc tạo được file JSON chưa đủ để chứng minh hợp đồng đáng tin cậy. Một operation có thể được mô tả sai status code, schema có thể không phản ánh JSON thực tế, hoặc file được công bố có thể không thuộc đúng phiên bản ứng dụng.

Bài thực hành này xây dựng một quy trình hoàn chỉnh với Order API. Ta bắt đầu từ yêu cầu nghiệp vụ, tạo request/response DTO, controller và exception handler, sau đó dùng springdoc-openapi sinh tài liệu. Tiếp theo, ta viết integration test cho HTTP behavior và OpenAPI document, kiểm tra tính hợp lệ và tương thích, đóng gói artifact, phát hành tài liệu theo version, rồi xác minh endpoint tài liệu sau khi triển khai.

Kết quả mong muốn là một OpenAPI artifact có thể review, validate, so sánh với bản trước và phân phối cho client. Các ví dụ dùng Spring Boot 3, Spring MVC và Spring Security Resource Server; nếu dự án dùng Boot 4 hoặc WebFlux, hãy chọn starter và API tương thích với nền tảng thực tế.

## 1. Kết quả cần đạt

Sau bài thực hành, người học có thể:

- Xác định hợp đồng HTTP trước khi triển khai controller.
- Thiết kế DTO tách biệt với entity và cấu trúc persistence.
- Mô tả path, method, parameter, request body, response, error và security.
- Sinh OpenAPI JSON/YAML từ ứng dụng Spring Boot bằng Springdoc.
- Kiểm tra hành vi HTTP và nội dung OpenAPI bằng integration test.
- Phát hiện khác biệt giữa hợp đồng hiện tại và bản đã phát hành.
- Phân loại thay đổi tương thích và breaking change.
- Đóng gói tài liệu cùng version và commit tương ứng.
- Phát hành tài liệu public/internal theo đúng phạm vi.
- Xác minh artifact được công bố có thể tải xuống và đúng nội dung.

## 2. Bối cảnh nghiệp vụ và phạm vi API

Ứng dụng quản lý đơn hàng cho một cửa hàng trực tuyến. Một client đã xác thực có thể tạo đơn hàng, xem đơn hàng theo ID và yêu cầu hủy đơn. Quy tắc nghiệp vụ:

- Client gửi customerId và danh sách item khi tạo đơn.
- Server tự sinh orderId, trạng thái ban đầu và timestamp.
- Mỗi item phải có productId và quantity lớn hơn 0.
- Đơn hàng chỉ được hủy khi còn ở trạng thái PENDING.
- Đơn hàng không tồn tại trả 404.
- Đơn hàng đã xử lý hoặc đã hủy không thể hủy lần nữa; trường hợp này trả 409.
- Request không hợp lệ trả 400.
- Endpoint yêu cầu Bearer JWT; thiếu hoặc sai token trả 401, thiếu quyền trả 403.

Các operation được công bố:

| Method | Path | Mục đích | Thành công |
|---|---|---|---|
| POST | /api/orders | Tạo đơn hàng | 201 Created |
| GET | /api/orders/{orderId} | Xem đơn hàng | 200 OK |
| POST | /api/orders/{orderId}/cancel | Hủy đơn hàng đang chờ | 200 OK |

Hợp đồng lỗi:

| Status | Error code | Điều kiện |
|---|---|---|
| 400 | VALIDATION_FAILED | Request thiếu hoặc sai dữ liệu |
| 401 | UNAUTHORIZED | Token không có hoặc không hợp lệ |
| 403 | FORBIDDEN | Người dùng không đủ quyền |
| 404 | ORDER_NOT_FOUND | Không tìm thấy đơn hàng |
| 409 | ORDER_STATE_CONFLICT | Trạng thái hiện tại không cho phép thao tác |
| 500 | INTERNAL_ERROR | Lỗi không dự kiến ở server |

Status code là một phần của contract. Không trả 200 cho tất cả tình huống rồi bắt client phân tích một chuỗi message để biết request thành công hay thất bại.

## 3. Luồng làm việc tổng thể

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ và quy tắc HTTP"] --> B["DTO, validation và controller"]
    B --> C["Spring handler mappings và security"]
    C --> D["Springdoc phân tích metadata"]
    D --> E["OpenAPI JSON/YAML"]
    E --> F["HTTP integration tests"]
    E --> G["OpenAPI validation"]
    F --> H["Contract và compatibility checks"]
    G --> H
    H --> I["Đóng gói artifact theo version"]
    I --> J["Phát hành developer portal hoặc artifact store"]
    J --> K["Xác minh URL và nội dung sau phát hành"]
~~~

Mỗi bước tạo ra bằng chứng cho bước tiếp theo. Controller là nguồn thực thi; OpenAPI là hợp đồng được công bố; test xác nhận hai phần khớp nhau; artifact đã kiểm tra mới được đưa vào kênh phát hành.

## 4. Cấu trúc project gợi ý

~~~text
com.acme.shop
├── ShopApplication.java
├── config
│   ├── OpenApiConfiguration.java
│   └── SecurityConfiguration.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   ├── Order.java
│   ├── OrderStatus.java
│   └── dto
│       ├── CreateOrderRequest.java
│       ├── OrderItemRequest.java
│       ├── OrderResponse.java
│       └── OrderItemResponse.java
└── common
    ├── ApiError.java
    ├── FieldViolation.java
    └── ApiExceptionHandler.java
~~~

Tách DTO khỏi entity để thay đổi database không tự động làm thay đổi API. Controller nhận request DTO, service xử lý nghiệp vụ và trả response DTO. Springdoc đọc kiểu dữ liệu và annotation trên các lớp này để tạo schema.

## 5. Chọn dependency phù hợp với nền tảng

Với Spring Boot 3 và Spring MVC, dùng starter Springdoc 2.x tương thích với Boot minor đang chạy:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x-compatible-version</version>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Giá trị version ở trên là placeholder hướng dẫn. Thay bằng release Springdoc được công bố tương thích với Spring Boot minor của project. Với Boot 4, dùng dòng Springdoc 3.x; với Boot 2, kiểm tra dòng 1.x và module tương ứng.

Nếu chỉ cần OpenAPI JSON/YAML mà không cần Swagger UI, chọn starter API-only phù hợp. Nếu ứng dụng dùng WebFlux, chọn starter WebFlux. Không thêm đồng thời MVC và WebFlux starter nếu ứng dụng không có chủ đích chạy cả hai web stack.

## 6. Xác định contract trước khi viết code

Hãy ghi rõ quyết định API trước khi tạo controller:

| Thành phần | Quyết định trong bài |
|---|---|
| ID | UUID do server tạo |
| Create request | customerId và items |
| Quantity | Số nguyên từ 1 trở lên |
| Initial status | PENDING |
| Create response | 201, OrderResponse và Location |
| Read response | 200, OrderResponse |
| Cancel response | 200, OrderResponse sau cập nhật |
| Invalid request | 400, ApiError |
| Missing order | 404, ApiError |
| Invalid state transition | 409, ApiError |
| Authentication | HTTP Bearer JWT |

Quyết định trước giúp code và tài liệu cùng tuân theo một contract. Nếu đổi cancel thành 204, phải cập nhật controller, OpenAPI response và integration test cùng lúc.

## 7. Tạo DTO cho item trong request

~~~java
public class OrderItemRequest {

    @NotNull
    @Schema(
        description = "Định danh sản phẩm",
        example = "a1d2c3e4-1111-4222-8333-123456789abc"
    )
    private UUID productId;

    @NotNull
    @Min(1)
    @Schema(
        description = "Số lượng phải lớn hơn 0",
        minimum = "1",
        example = "2"
    )
    private Integer quantity;

    // constructors, getters and setters
}
~~~

Bean Validation kiểm tra dữ liệu khi request được xử lý với @Valid. Springdoc có thể sử dụng constraint phổ biến để bổ sung metadata vào schema. Với custom validator, hãy kiểm tra OpenAPI output; không mặc định mọi quy tắc nghiệp vụ đều được chuyển thành JSON Schema constraint.

## 8. Tạo CreateOrderRequest

~~~java
public class CreateOrderRequest {

    @NotNull
    @Schema(
        description = "UUID của khách hàng đặt đơn",
        example = "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc"
    )
    private UUID customerId;

    @NotEmpty
    @Valid
    @Size(max = 50)
    @ArraySchema(
        schema = @Schema(implementation = OrderItemRequest.class),
        arraySchema = @Schema(
            description = "Danh sách item, từ 1 đến 50 phần tử"
        )
    )
    private List<OrderItemRequest> items;

    // constructors, getters and setters
}
~~~

Client không gửi orderId, status, totalAmount hoặc createdAt. Những trường này do server quản lý. Không dùng entity Order làm request chỉ để giảm số class; entity có thể chứa field nội bộ và quan hệ persistence không thuộc hợp đồng HTTP.

## 9. Tạo response DTO

~~~java
public class OrderItemResponse {

    @Schema(format = "uuid")
    private UUID productId;

    @Schema(example = "2")
    private int quantity;

    @Schema(example = "49.95")
    private BigDecimal unitPrice;

    @Schema(example = "99.90")
    private BigDecimal lineTotal;

    // constructors, getters and setters
}
~~~

~~~java
public class OrderResponse {

    @Schema(format = "uuid")
    private UUID orderId;

    @Schema(format = "uuid")
    private UUID customerId;

    @Schema(
        description = "Trạng thái đơn hàng",
        example = "PENDING"
    )
    private OrderStatus status;

    @Schema(example = "99.90")
    private BigDecimal totalAmount;

    @Schema(format = "date-time")
    private Instant createdAt;

    private List<OrderItemResponse> items;

    // constructors, getters and setters
}
~~~

Schema response phải khớp JSON serialize thực tế. Nếu Jackson đổi tên property, bỏ null hoặc định dạng timestamp, hãy kiểm tra document và response HTTP để tránh contract sai.

## 10. Chuẩn hóa error model

~~~java
public class FieldViolation {

    @Schema(example = "items[0].quantity")
    private String field;

    @Schema(example = "must be greater than or equal to 1")
    private String message;

    // constructors, getters and setters
}
~~~

~~~java
public class ApiError {

    @Schema(format = "date-time")
    private Instant timestamp;

    @Schema(example = "400")
    private int status;

    @Schema(example = "VALIDATION_FAILED")
    private String code;

    @Schema(example = "Request contains invalid fields")
    private String message;

    @Schema(example = "/api/orders")
    private String path;

    private List<FieldViolation> fieldErrors;

    // constructors, getters and setters
}
~~~

Ví dụ lỗi validation:

~~~json
{
  "timestamp": "2026-11-20T10:15:30Z",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "path": "/api/orders",
  "fieldErrors": [
    {
      "field": "items[0].quantity",
      "message": "must be greater than or equal to 1"
    }
  ]
}
~~~

Không đưa stack trace, SQL, token hoặc thông tin bí mật vào error body. Message công khai cần ổn định và đủ giúp client xử lý; chi tiết kỹ thuật ghi vào log nội bộ.

## 11. Tạo domain exception

~~~java
public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(UUID orderId) {
        super("Order not found: " + orderId);
    }
}

public class OrderStateConflictException extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

Service kiểm tra trạng thái trước khi hủy:

~~~java
public OrderResponse cancel(UUID orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    if (order.getStatus() != OrderStatus.PENDING) {
        throw new OrderStateConflictException(
            "Only pending orders can be cancelled"
        );
    }

    order.setStatus(OrderStatus.CANCELLED);
    return mapper.toResponse(repository.save(order));
}
~~~

Đây là logic minh họa. Trong ứng dụng thực tế, cần xử lý đồng thời khi hai request cùng hủy một đơn, ví dụ optimistic locking hoặc cập nhật có điều kiện trong database.

## 12. Tạo Controller và Tag

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Tạo, tra cứu và hủy đơn hàng"
)
@SecurityRequirement(name = "bearerAuth")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

@Tag nhóm operation trong Swagger UI. @SecurityRequirement cho biết các operation của controller yêu cầu security scheme đã khai báo. Nếu một operation public, đặt security requirement theo từng method thay vì gắn ở cấp class.

## 13. Tài liệu hóa operation tạo đơn hàng

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng",
    description = "Tạo đơn hàng mới. Server sinh ID, trạng thái PENDING và timestamp."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng đã được tạo",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Thiếu hoặc token không hợp lệ"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Không có quyền tạo đơn hàng"
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Lỗi không dự kiến ở server",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {

    OrderResponse created = orderService.create(request);
    URI location = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .path("/{orderId}")
        .buildAndExpand(created.getOrderId())
        .toUri();

    return ResponseEntity.created(location).body(created);
}
~~~

POST trả 201 Created và Location trỏ tới tài nguyên mới. Kiểu generic của ResponseEntity cho Springdoc biết response body là OrderResponse; @ApiResponse bổ sung status và schema rõ ràng cho các trường hợp quan trọng.

## 14. Tài liệu hóa operation tra cứu đơn hàng

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Tra cứu đơn hàng",
    description = "Trả về đơn hàng theo UUID."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Thiếu hoặc token không hợp lệ"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Không có quyền xem đơn hàng"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Lỗi không dự kiến ở server",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public OrderResponse getById(
        @Parameter(
            description = "UUID của đơn hàng",
            example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001"
        )
        @PathVariable UUID orderId) {
    return orderService.findById(orderId);
}
~~~

UUID được dùng trực tiếp trong method signature để Spring và OpenAPI cùng thể hiện kiểu string với format uuid. Parameter path là bắt buộc vì URL template cần giá trị orderId.

## 15. Tài liệu hóa operation hủy đơn

~~~java
@PostMapping("/{orderId}/cancel")
@Operation(
    operationId = "cancelOrder",
    summary = "Hủy đơn hàng",
    description = "Chỉ hủy được đơn đang ở trạng thái PENDING."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Đơn hàng đã chuyển sang CANCELLED",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Thiếu hoặc token không hợp lệ"
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Không có quyền hủy đơn hàng"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Trạng thái hiện tại không cho phép hủy",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "500",
        description = "Lỗi không dự kiến ở server",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public OrderResponse cancel(@PathVariable UUID orderId) {
    return orderService.cancel(orderId);
}
~~~

Hủy đơn là một hành động có side effect nên dùng POST cho action endpoint là lựa chọn có thể hiểu được trong contract này. Description nói rõ điều kiện trạng thái; 409 thể hiện xung đột với trạng thái tài nguyên hiện tại.

## 16. Ghép các method vào Controller hoàn chỉnh

Ba method create, getById và cancel được đặt trong cùng OrderController:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders", description = "Tạo, tra cứu và hủy đơn hàng")
@SecurityRequirement(name = "bearerAuth")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    // create(...)
    // getById(...)
    // cancel(...)
}
~~~

Khi ghép source, giữ đúng các annotation method ở các phần trước. Không tạo hai method cùng mapping và không đặt nhiều composed mapping annotation trên cùng method.

## 17. Chuẩn hóa exception bằng ControllerAdvice

Validation lỗi được chuyển thành ApiError:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<FieldViolation> violations = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldViolation(
                error.getField(),
                error.getDefaultMessage()
            ))
            .toList();

        ApiError body = new ApiError(
            Instant.now(),
            400,
            "VALIDATION_FAILED",
            "Request contains invalid fields",
            request.getRequestURI(),
            violations
        );
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Với Java version chưa hỗ trợ Stream.toList(), dùng Collectors.toList(). Cấu trúc ApiError phải khớp schema đã khai báo trong OpenAPI.

## 18. Ánh xạ lỗi 404 và 409

~~~java
@ExceptionHandler(OrderNotFoundException.class)
ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException ex,
        HttpServletRequest request) {

    ApiError body = new ApiError(
        Instant.now(),
        404,
        "ORDER_NOT_FOUND",
        "Order was not found",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}

@ExceptionHandler(OrderStateConflictException.class)
ResponseEntity<ApiError> handleConflict(
        OrderStateConflictException ex,
        HttpServletRequest request) {

    ApiError body = new ApiError(
        Instant.now(),
        409,
        "ORDER_STATE_CONFLICT",
        "Current order state does not allow this operation",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
}
~~~

Message công khai không cần chứa chi tiết nội bộ từ exception. Error code ổn định giúp client xử lý bằng logic thay vì so sánh câu chữ.

## 19. Xử lý lỗi không dự kiến

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<ApiError> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    log.error("Unhandled API error at {}", request.getRequestURI(), ex);

    ApiError body = new ApiError(
        Instant.now(),
        500,
        "INTERNAL_ERROR",
        "An unexpected error occurred",
        request.getRequestURI(),
        List.of()
    );
    return ResponseEntity.internalServerError().body(body);
}
~~~

Exception handler tổng quát chỉ là lớp dự phòng. Không để response công khai chứa stack trace, tên bảng, SQL hoặc thông tin xác thực. Các exception bảo mật có thể được Spring Security xử lý ở filter chain trước khi request tới ControllerAdvice; test 401/403 ở đúng tầng. Trong ví dụ, ApiError được dùng cho lỗi do controller và ControllerAdvice xử lý. 401/403 được tạo ở security layer; nếu muốn chúng cũng trả ApiError, cấu hình AuthenticationEntryPoint và AccessDeniedHandler tương ứng rồi mô tả content schema cho hai response đó.

## 20. Khai báo OpenAPI metadata và Bearer scheme

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop Order API",
        version = "1.0.0",
        description = "API tạo, tra cứu và hủy đơn hàng"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

Giá trị info.version là version của hợp đồng API được công bố. Nó không tự động bằng version Maven, version Spring Boot hoặc version Git tag. Hãy chọn một chính sách version rõ ràng và giữ nhất quán giữa document, artifact và release notes.

## 21. Cấu hình Spring Security Resource Server

Với JWT Resource Server, cấu hình runtime có thể theo dạng:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/v3/api-docs", "/v3/api-docs/**",
                    "/v3/api-docs.yaml", "/swagger-ui/**",
                    "/swagger-ui.html").permitAll()
                .requestMatchers("/api/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ))
            .build();
    }
}
~~~

Đây là cấu hình minh họa. Trong production, có thể cần bảo vệ tài liệu OpenAPI hoặc tách public/internal document theo chính sách tổ chức. Nếu tài liệu công khai, chỉ permit các endpoint thực sự cần công khai. Nếu tài liệu nội bộ, bảo vệ cả JSON, YAML và Swagger UI.

Security scheme trong OpenAPI chỉ mô tả cách client gửi token. Spring Security mới xác minh token và áp dụng authorization. Không đưa token thật vào example hoặc file OpenAPI.

## 22. Thêm cấu hình package và path scan

Nếu ứng dụng có nhiều controller, giới hạn phạm vi document bằng cấu hình có chủ đích:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.shop.order
  paths-to-match:
    - /api/**
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

Không dùng package/path filter để che giấu một endpoint mà hệ thống vẫn cho phép truy cập khi mục tiêu thực sự là bảo mật. Filter chỉ điều khiển phạm vi tài liệu.

Nếu có nhiều nhóm public và internal, tạo GroupedOpenApi riêng và kiểm tra từng document.

## 23. Sinh OpenAPI JSON và YAML

Khởi động ứng dụng với profile dùng để kiểm tra:

~~~bash
./mvnw spring-boot:run
~~~

Lấy JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Lấy YAML:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  -o target/openapi.yaml
~~~

Đường dẫn thực tế có thể đổi do context path, reverse proxy hoặc springdoc properties. Nếu dùng group, gọi endpoint của group tương ứng. Lưu artifact từ đúng commit và profile sẽ được phát hành.

## 24. Kiểm tra document ở mức cấu trúc

Đọc metadata:

~~~bash
jq '{openapi, info, pathCount: (.paths | length)}' target/openapi.json
~~~

Liệt kê path:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Kiểm tra operation tạo đơn:

~~~bash
jq '.paths["/api/orders"].post' target/openapi.json
~~~

Kiểm tra response của cancel:

~~~bash
jq '.paths["/api/orders/{orderId}/cancel"].post.responses' target/openapi.json
~~~

Kiểm tra security scheme:

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

Document cần có đủ ba operation, path parameter UUID, request schema, response thành công, lỗi và Bearer scheme. Không chỉ kiểm tra file tồn tại hoặc JSON parse được; hãy xác minh contract fields.

## 25. Kiểm tra Swagger UI

Mở Swagger UI theo path đã cấu hình, thường là:

~~~text
http://localhost:8080/swagger-ui.html
~~~

Kiểm tra:

- Có tag Orders.
- Có đủ POST create, GET by ID và POST cancel.
- operationId và summary có ý nghĩa.
- orderId hiển thị là path parameter bắt buộc, format UUID.
- Request body hiển thị customerId và items.
- Quantity có minimum 1.
- Response 201, 200 và các lỗi có schema phù hợp.
- Security scheme bearerAuth xuất hiện trong Authorize.

Swagger UI là giao diện đọc OpenAPI document. Nếu UI không hiển thị operation, gọi JSON endpoint trực tiếp để phân biệt lỗi document với lỗi UI/group selection.

## 26. Viết HTTP integration test cho tạo đơn

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser
    void createOrderReturns201AndLocation() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc",
                      "items": [
                        {
                          "productId": "a1d2c3e4-1111-4222-8333-123456789abc",
                          "quantity": 2
                        }
                      ]
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.orderId").exists())
            .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
~~~

Ví dụ dùng mock user để tập trung kiểm tra contract controller. Nếu test security token thật, cấu hình JWT test decoder hoặc test resource server phù hợp. Dữ liệu repository cần được cô lập để test có thể chạy lặp lại.

## 27. Kiểm tra validation và lỗi nghiệp vụ

~~~java
@Test
@WithMockUser
void invalidOrderReturns400() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "f5b5e4d1-aaaa-4bbb-8ccc-123456789abc",
                  "items": [
                    {
                      "productId": "a1d2c3e4-1111-4222-8333-123456789abc",
                      "quantity": 0
                    }
                  ]
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.fieldErrors").isArray());
}

@Test
@WithMockUser
void unknownOrderReturns404() throws Exception {
    mockMvc.perform(get(
            "/api/orders/00000000-0000-0000-0000-000000000000"
        ))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
~~~

Thêm test 409 cho order không ở trạng thái PENDING. Test phải tạo trạng thái ban đầu có thể tái lập, gọi cancel và xác minh response code ORDER_STATE_CONFLICT.

## 28. Kiểm tra authentication và authorization

Nếu API yêu cầu JWT, cần test ít nhất:

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Không có token | 401 |
| Token sai chữ ký hoặc hết hạn | 401 |
| Token hợp lệ nhưng thiếu scope/role | 403 |
| Token hợp lệ và đủ quyền | Request được xử lý |

Không chỉ test với @WithMockUser rồi kết luận JWT Resource Server đã cấu hình đúng. @WithMockUser thường kiểm tra authorization ở test context; test token nên xác minh decoder, issuer, audience và authority mapping theo cấu hình ứng dụng.

## 29. Viết test cho OpenAPI document

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentContainsOrderOperationsAndResponses() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode document = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        JsonNode paths = document.path("paths");

        assertThat(paths.path("/api/orders").path("post")
            .path("responses").has("201")).isTrue();

        assertThat(paths.path("/api/orders/{orderId}").path("get")
            .path("responses").has("404")).isTrue();

        assertThat(paths.path("/api/orders/{orderId}/cancel").path("post")
            .path("responses").has("409")).isTrue();

        assertThat(document.path("components")
            .path("securitySchemes").has("bearerAuth")).isTrue();
    }
}
~~~

Path và operation trong assertion phải khớp mapping cuối cùng của controller. Nếu code dùng cancel path dạng /{orderId}/cancel, kiểm tra đúng path đó; ví dụ trên minh họa cách truy vấn cấu trúc document.

Thêm assertion cho requestBody, schema OrderResponse, ApiError và path parameter. Test document phải phát hiện trường hợp operation còn nhưng response hoặc security metadata bị mất.

## 30. Kiểm tra JSON và YAML bằng validator

JSON parse thành công chưa bảo đảm document tuân thủ OpenAPI. Dùng validator tương thích với OpenAPI version mà document phát ra.

Ví dụ với OpenAPI Generator CLI:

~~~bash
openapi-generator-cli validate -i target/openapi.json
~~~

Ví dụ với Redocly CLI:

~~~bash
npx @redocly/cli lint target/openapi.yaml
~~~

Pin version công cụ trong CI và dùng cùng cấu hình lint giữa các nhánh. Nếu dự án có rule riêng về operationId, tag, security hoặc error schema, đưa các rule đó vào lint configuration.

Không tự ý tắt rule chỉ để pipeline xanh. Nếu rule không phù hợp, ghi rõ lý do và điều chỉnh policy có review.

## 31. Phân biệt lỗi OpenAPI với lỗi runtime

| Hiện tượng | Nơi điều tra |
|---|---|
| HTTP route chạy nhưng không có operation | @Hidden, package/path filters, group hoặc customizer |
| OpenAPI có operation nhưng HTTP trả 404 | Mapping runtime, context path hoặc instance |
| OpenAPI ghi 201 nhưng controller trả 200 | ResponseEntity và status handling |
| Schema ghi quantity tối thiểu 1 nhưng server nhận 0 | @Valid, validation dependency và service rules |
| Response body khác schema | Jackson, DTO mapping và custom serializer |
| Swagger UI không hiện operation nhưng JSON có | UI URL, group selection hoặc cache |
| Security scheme có trong document nhưng endpoint cho anonymous | Spring Security runtime configuration |

So sánh ba nguồn: OpenAPI document, HTTP response thực tế và integration tests. Khi một nguồn khác hai nguồn còn lại, contract chưa được kiểm chứng.

## 32. Phân loại thay đổi tương thích và breaking change

Trước khi phát hành, so sánh document mới với baseline đã công bố.

| Thay đổi | Tác động thường gặp |
|---|---|
| Thêm optional query parameter | Thường tương thích |
| Thêm operation mới | Thường tương thích |
| Thêm required request field | Có thể breaking với client cũ |
| Xóa request/response field | Có thể breaking |
| Đổi kiểu dữ liệu hoặc format | Breaking |
| Đổi path hoặc HTTP method | Breaking |
| Đổi response status hoặc schema | Có thể breaking |
| Thêm enum value | Có thể làm client exhaustive switch lỗi |
| Siết validation | Có thể phá request trước đây hợp lệ |
| Thay security requirement | Có thể phá client tích hợp |
| Ẩn hoặc xóa operation | Breaking với client đang dùng operation |

Không phải mọi thay đổi thêm đều an toàn. Ví dụ, thêm enum value có thể làm code client sinh ra không xử lý được giá trị mới. Đánh giá theo cách consumer sử dụng contract, không chỉ theo cấu trúc JSON.

## 33. So sánh với baseline bằng công cụ diff

Lưu baseline của release trước, ví dụ openapi-released.json. Sau khi sinh document mới, chạy công cụ diff:

~~~bash
oasdiff breaking openapi-released.yaml target/openapi.yaml
~~~

Lệnh minh họa dùng CLI oasdiff; pin version và kiểm tra cú pháp của release công cụ được chọn. Một số tổ chức dùng OpenAPI diff plugin trong Maven hoặc CI service tương đương.

Pipeline nên:

1. Dừng phát hành nếu có breaking change chưa được chấp thuận.
2. Cho phép thay đổi tương thích qua review thông thường.
3. Yêu cầu version API mới hoặc migration plan khi breaking change được chấp thuận.
4. Lưu báo cáo diff cùng artifact.

Không coi kết quả diff là thay thế review nghiệp vụ. Công cụ có thể phát hiện thay đổi schema nhưng không hiểu hết semantics của API.

## 34. Quản lý version của hợp đồng

Phân biệt các version:

| Loại version | Ý nghĩa |
|---|---|
| Spring Boot | Nền tảng ứng dụng |
| Springdoc | Thư viện sinh OpenAPI |
| OpenAPI specification | Phiên bản chuẩn được ghi trong document |
| API contract version | Version do đội API quản lý trong info.version hoặc release policy |
| Application build version | Version artifact ứng dụng |

Không để các version này thay thế nhau. Một ứng dụng có thể nâng Springdoc mà contract không đổi; cũng có thể thay đổi API contract mà không nâng Springdoc.

Đối với breaking change, chọn versioning policy rõ ràng: version path như /api/v2, header-based versioning hoặc policy khác của tổ chức. Document phải phản ánh chính xác version được công bố.

## 35. Đóng gói artifact OpenAPI

Sau khi test và validation đạt, tạo thư mục artifact theo version:

~~~text
build/
└── api-contract/
    ├── openapi.json
    ├── openapi.yaml
    ├── compatibility-report.txt
    └── manifest.json
~~~

Manifest có thể ghi:

~~~json
{
  "service": "shop-order-api",
  "apiVersion": "1.0.0",
  "applicationVersion": "2026.11.20",
  "sourceRevision": "git-commit-sha",
  "openapiFile": "openapi.yaml"
}
~~~

Giá trị manifest là metadata minh họa. Trong CI, lấy version và commit từ build environment; không hard-code commit giả vào artifact.

Lưu cả JSON và YAML nếu consumer cần hai định dạng. Nếu chỉ một định dạng là nguồn chuẩn, xác định rõ định dạng canonical và sinh định dạng còn lại từ cùng document để tránh drift.

## 36. Quy trình CI tổng hợp

Một pipeline tối thiểu có các bước:

~~~text
1. Checkout source
2. Resolve dependency versions
3. Compile và unit tests
4. Start application với profile dành cho contract
5. Export OpenAPI JSON/YAML
6. Parse và lint document
7. Run HTTP integration tests
8. Run OpenAPI document tests
9. Compare với released baseline
10. Build artifact và manifest
11. Publish artifact sau khi các gate đạt
12. Verify artifact từ URL đã publish
~~~

Có thể chia thành nhiều job, nhưng artifact được publish phải là đúng file đã qua validation và diff. Không sinh lại document từ một runtime khác sau khi kiểm tra rồi publish file khác.

## 37. Ví dụ script kiểm tra contract trong CI

~~~bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="$CONTRACT_BASE_URL"
OUT_DIR="target/api-contract"

mkdir -p "$OUT_DIR"

curl --fail --silent --show-error \
  "$BASE_URL/v3/api-docs" \
  -o "$OUT_DIR/openapi.json"

curl --fail --silent --show-error \
  "$BASE_URL/v3/api-docs.yaml" \
  -o "$OUT_DIR/openapi.yaml"

openapi-generator-cli validate -i "$OUT_DIR/openapi.json"
oasdiff breaking "contracts/released/openapi.yaml" "$OUT_DIR/openapi.yaml"

printf '%s\n' "OpenAPI contract checks passed"
~~~

Đây là khung lệnh minh họa. Pipeline thực tế cần khởi động ứng dụng trước và đặt biến môi trường CONTRACT_BASE_URL, cấu hình authentication nếu endpoint tài liệu được bảo vệ, pin version CLI và quyết định cách xử lý exit code khi diff tìm thấy breaking change.

Nếu chưa có baseline cho release đầu tiên, tạo baseline sau khi contract được review và phê duyệt. Không bỏ qua diff gate vĩnh viễn chỉ vì lần đầu chưa có file so sánh.

## 38. Phát hành tài liệu

Chọn một kênh phân phối phù hợp:

- Artifact repository nội bộ.
- Developer portal.
- Static documentation site.
- Object storage có versioned path.
- API catalog hoặc portal dành cho đối tác.

Ví dụ đường dẫn phát hành:

~~~text
https://docs.example.invalid/apis/shop-order/1.0.0/openapi.yaml
https://docs.example.invalid/apis/shop-order/1.0.0/openapi.json
~~~

Đây là URL minh họa. Khi phát hành, giữ artifact immutable theo version. Nếu cần alias latest, cập nhật alias sau khi version cụ thể đã được publish và kiểm tra.

Không publish internal group hoặc tài liệu có thông tin không dành cho đối tác lên public portal. OpenAPI document có thể tiết lộ endpoint, schema và security assumptions ngay cả khi không chứa dữ liệu thực tế.

## 39. Xác minh sau phát hành

Sau khi publish:

1. Tải JSON/YAML từ URL public hoặc internal đã công bố.
2. Parse file và kiểm tra OpenAPI version.
3. Kiểm tra info.title và info.version.
4. Xác nhận paths và operationId quan trọng.
5. Xác nhận security schemes.
6. Chạy validator trên artifact tải xuống.
7. So sánh checksum với artifact đã qua CI.
8. Mở developer portal và kiểm tra đúng version.
9. Thử link từ tài liệu hướng dẫn hoặc SDK generator.

Không chỉ xác nhận upload command trả exit code 0. Cần kiểm tra nội dung tải xuống có đúng artifact đã được kiểm chứng.

## 40. Rollback và xử lý lỗi phát hành

Nếu tài liệu đã publish sai:

- Giữ artifact sai để audit nếu chính sách yêu cầu.
- Đánh dấu version hoặc portal entry là withdrawn/deprecated theo quy trình.
- Khôi phục alias latest về version đã xác minh trước đó.
- Publish artifact sửa với version hoặc patch release phù hợp.
- Chạy lại validator và compatibility diff.
- Thông báo thay đổi qua kênh phát hành được tổ chức cho phép.

Không ghi đè âm thầm một artifact version đã được consumer tải xuống. Consumer có thể đã sinh SDK hoặc lưu bản contract cũ; thay đổi immutable file sẽ làm mất khả năng tái lập.

## 41. Bảo vệ tài liệu và phân chia public/internal

OpenAPI là metadata, nhưng vẫn có thể tiết lộ bề mặt API. Trước khi publish, xác định:

- Tài liệu nào public.
- Tài liệu nào chỉ dành cho nhân viên hoặc đối tác.
- Endpoint nội bộ có bị loại khỏi public group không.
- Swagger UI có cần authentication không.
- JSON/YAML endpoint có cùng chính sách access với UI không.
- Example có chứa token, email hoặc dữ liệu thật không.
- Server URL có trỏ tới môi trường production phù hợp không.

Ẩn operation bằng @Hidden không thay thế authorization. Ngược lại, bảo vệ Swagger UI nhưng để JSON endpoint public cũng có thể làm lộ document. Kiểm tra toàn bộ URL phục vụ tài liệu.

## 42. Checklist trước khi phát hành

- [ ] Controller mapping khớp contract đã duyệt.
- [ ] Request/response DTO tách khỏi entity.
- [ ] Validation được kích hoạt ở runtime.
- [ ] OperationId ổn định và duy nhất.
- [ ] Request body, parameter và response schema có mô tả.
- [ ] Status code thành công và lỗi khớp runtime.
- [ ] Security scheme khớp cách xác thực thực tế.
- [ ] Public/internal group được lọc đúng.
- [ ] OpenAPI JSON/YAML được export từ đúng profile.
- [ ] OpenAPI validator chạy thành công.
- [ ] HTTP integration tests đạt.
- [ ] OpenAPI document tests đạt.
- [ ] Breaking change diff được review.
- [ ] Version contract và application build được ghi riêng.
- [ ] Artifact có manifest và source revision.
- [ ] Artifact được publish theo version immutable.
- [ ] URL sau phát hành tải được đúng nội dung.

## 43. Bảng xử lý sự cố trong quy trình end-to-end

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có path trong document | Controller không được scan hoặc bị filter/hidden | Spring mappings, package scan, group và @Hidden |
| Path có nhưng thiếu response lỗi | Thiếu @ApiResponse hoặc advice không được phản ánh | Kiểm tra operation responses và ControllerAdvice |
| Schema khác JSON thực tế | Jackson, DTO mapping hoặc custom serializer | So sánh response thật với components/schemas |
| Validation test không trả 400 | Thiếu @Valid hoặc validation dependency | Kiểm tra request binding và provider |
| 401/403 không như document | Security filter chain hoặc authority mapping | Test token và scope/role |
| Validator báo lỗi | OpenAPI document không hợp lệ hoặc schema sai | Đọc vị trí lỗi và sửa metadata |
| Diff báo breaking change | Path, required field, type, response hoặc security đổi | Review baseline và consumer impact |
| Artifact publish nhưng portal không đổi | Cache, alias hoặc URL version sai | Tải trực tiếp URL version cụ thể |
| Public doc có internal path | Group filter hoặc customizer cấu hình sai | Kiểm tra từng document group |
| UI không khớp JSON | UI trỏ document khác hoặc cache | Kiểm tra config URL và tải JSON trực tiếp |

## 44. Bài tập mở rộng

Sau khi hoàn thành luồng cơ bản, mở rộng theo các yêu cầu:

1. Thêm GET /api/orders hỗ trợ pagination và filter theo status; mô tả query parameter và response page.
2. Thêm idempotency key cho POST create; mô tả header, behavior khi gửi lại cùng key và response conflict.
3. Thêm endpoint chỉ ADMIN mới được xem; thể hiện security requirement và test 403.
4. Tạo public và internal GroupedOpenApi; xác minh operation chỉ xuất hiện đúng group.
5. Thêm enum status và đánh giá ảnh hưởng khi thêm giá trị mới.
6. Tạo contract baseline version 1.0.0, sau đó thử xóa một response field để xem diff báo gì.
7. Thiết kế version 2 cho thay đổi breaking và publish song song hai document.
8. Thêm checksum vào manifest và xác minh sau khi tải artifact từ portal.

## 45. Ghi nhớ

- Hợp đồng phải được xác định trước khi viết controller.
- Spring mapping và security điều khiển runtime; OpenAPI annotations mô tả contract.
- DTO và Bean Validation cung cấp schema và ràng buộc đầu vào.
- ControllerAdvice chuẩn hóa error response, còn security filter có thể xử lý 401/403 trước controller.
- Springdoc sinh OpenAPI từ handler mapping và metadata; JSON/YAML là artifact cần kiểm tra.
- HTTP integration tests xác minh status, header và body thực tế.
- OpenAPI document tests xác minh path, operation, schema, response và security.
- Validator kiểm tra cấu trúc; compatibility diff phát hiện thay đổi so với baseline.
- Springdoc version, OpenAPI specification version, API contract version và application version là các loại version khác nhau.
- Chỉ publish artifact đã qua test, validation và review.
- Artifact phát hành nên immutable và gắn với version cùng source revision.
- Xác minh lại URL sau publish để chắc chắn consumer nhận đúng nội dung.
- Ẩn operation khỏi tài liệu không thay thế authentication hoặc authorization.

Quy trình hoàn chỉnh kết nối controller, metadata, OpenAPI, test và phát hành thành một chuỗi có thể kiểm chứng. Hãy giữ contract nhất quán từ quyết định nghiệp vụ tới HTTP response, kiểm tra document được sinh thay vì chỉ nhìn annotation, so sánh với baseline trước khi release và xác minh artifact sau khi publish. Khi các bước này được tự động hóa, OpenAPI trở thành hợp đồng có thể review và tái lập, thay vì một trang Swagger chỉ được kiểm tra thủ công.

## Tài liệu tham khảo

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc OpenAPI FAQ: https://springdoc.org/faq.html
- Spring Boot testing documentation: https://docs.spring.io/spring-boot/reference/testing/index.html
- Spring Security OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- OpenAPI Generator validation: https://openapi-generator.tech/docs/usage/
- oasdiff: https://github.com/Tufin/oasdiff
- Redocly CLI lint: https://redocly.com/docs/cli/commands/lint
