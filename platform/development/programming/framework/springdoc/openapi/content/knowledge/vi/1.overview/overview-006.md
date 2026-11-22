# Những thông tin có thể suy ra tự động và những thông tin cần bổ sung

Springdoc-openapi tạo đặc tả OpenAPI từ controller Spring MVC/WebFlux, kiểu dữ liệu Java, annotation Spring, metadata Jackson, Bean Validation và các annotation OpenAPI. Nhờ đó, nhiều thành phần của API có thể được mô tả mà không phải viết lại thủ công: path, HTTP method, tham số, kiểu request/response và một phần schema.

Tuy nhiên, code chỉ thể hiện một phần hợp đồng API. Springdoc không thể tự hiểu đầy đủ ý nghĩa nghiệp vụ của một trường, vì sao người dùng được phép gọi operation, mọi tình huống lỗi có thể xảy ra, ví dụ dữ liệu thực tế, chính sách phân trang, giới hạn sử dụng hay quy trình giữa nhiều endpoint. Những thông tin này cần được bổ sung bằng annotation, cấu hình hoặc tài liệu đi kèm.

Nguyên tắc quan trọng là dùng khả năng suy luận tự động cho cấu trúc có thể kiểm chứng từ implementation, đồng thời bổ sung tường minh phần ngữ nghĩa và cam kết mà consumer cần biết. Đặc tả tốt không chỉ phản ánh code hiện tại mà còn truyền đạt đúng cách client được phép và nên sử dụng API.

## 1. Hiểu hai nguồn thông tin của OpenAPI document

Một OpenAPI document do springdoc tạo thường kết hợp hai nhóm thông tin:

1. **Thông tin suy ra từ implementation:** Spring mapping, chữ ký method, kiểu Java, generic type, DTO, annotation serialization và validation.
2. **Thông tin được khai báo bổ sung:** mô tả nghiệp vụ, ví dụ, response lỗi, security scheme, security requirement, tag, server, chính sách phiên bản và các quy ước không thể suy luận đáng tin cậy.

Có thể hình dung luồng tạo tài liệu:

~~~text
Spring MVC/WebFlux mappings
          |
          v
Controller methods + Java types
          |
          +---- Jackson / Bean Validation metadata
          |
          +---- Swagger/OpenAPI annotations
          |
          +---- Springdoc configuration/customizers
          |
          v
       OpenAPI model
          |
          v
      JSON / YAML
          |
          v
       Swagger UI
~~~

Swagger UI chỉ trình bày document đã được tạo. Nếu thông tin sai hoặc thiếu trong JSON/YAML, việc đổi giao diện Swagger UI không tự sửa được hợp đồng.

## 2. Những thông tin springdoc thường suy ra được

Khi controller và dependency được cấu hình đúng, springdoc thường có thể suy ra các thông tin cấu trúc sau:

| Thành phần | Nguồn suy luận phổ biến | Lưu ý |
|---|---|---|
| Path | RequestMapping, GetMapping, PostMapping và các mapping khác | Có thể kết hợp prefix từ class và method |
| HTTP method | Annotation mapping của Spring | Cần tránh mapping quá động hoặc custom route không được tích hợp |
| consumes/produces | Mapping và media type khai báo | Không thay thế việc mô tả encoding riêng của từng multipart part |
| Path parameter | PathVariable và placeholder trong path | Nên khai báo tên tường minh |
| Query parameter | RequestParam, kiểu tham số và metadata tên | Tên suy luận phụ thuộc compiler metadata nếu annotation không ghi rõ |
| Header/cookie parameter | RequestHeader, CookieValue | Nên khai báo name/value rõ ràng |
| Request body | RequestBody, RequestPart và kiểu DTO | Multipart cần mô tả schema phù hợp |
| Response schema | Kiểu trả về, generic type và wrapper | ResponseEntity hoặc reactive wrapper không thể hiện mọi nhánh runtime |
| DTO properties | Java bean, record, Jackson metadata | Tên JSON có thể khác tên field Java |
| Enum values | Kiểu enum | Ý nghĩa từng giá trị vẫn cần mô tả |
| Một số constraint | Bean Validation annotations | Không biểu diễn được mọi quy tắc nghiệp vụ |
| Annotation OpenAPI | Schema, Operation, Parameter, ApiResponse... | Đây là metadata được lập trình viên cung cấp, không phải suy luận thuần túy |

Danh sách này mô tả khả năng thường gặp, không phải cam kết rằng mọi cấu trúc tùy biến đều được nhận diện giống nhau ở mọi phiên bản. Sau khi nâng Spring Boot, Spring Framework hoặc springdoc, cần kiểm tra document thực tế.

## 3. Path và HTTP method thường được suy ra từ Spring mapping

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(
            @PathVariable("orderId") UUID orderId) {
        // ...
    }

    @PostMapping
    OrderResponse createOrder(
            @RequestBody CreateOrderRequest request) {
        // ...
    }
}
~~~

Springdoc có thể đọc class-level mapping /api/orders, method-level mapping và HTTP method để tạo các path operation tương ứng.

Thông tin có thể suy ra:

- Operation GET trên /api/orders/{orderId}.
- Operation POST trên /api/orders.
- Path parameter orderId.
- Request body của operation POST dựa trên DTO.

Thông tin cần bổ sung:

- API này dành cho người dùng, nhân viên hay hệ thống nội bộ.
- GET trả về đơn hàng nào và có quy tắc visibility gì.
- POST tạo đơn hàng ở trạng thái nào.
- Điều kiện nghiệp vụ khiến yêu cầu bị từ chối.
- Operation có idempotent hay không theo thiết kế của hệ thống.

Tên path và method không thể thay thế summary hoặc description có ý nghĩa.

## 4. Parameter có thể được suy luận nhưng tên public nên ổn định

Springdoc có thể đọc các annotation như PathVariable, RequestParam, RequestHeader và CookieValue. Khi annotation không có tên tường minh, framework có thể dựa vào tên method parameter.

Ví dụ:

~~~java
@GetMapping("/search")
List<OrderResponse> search(
        @RequestParam(name = "status", required = false) String state,
        @RequestParam(name = "page", defaultValue = "0") int page) {
    // ...
}
~~~

Ở đây tên public là status và page, dù biến Java đầu tiên tên state. Đây là cách tránh phụ thuộc vào việc đổi tên biến source hoặc compiler metadata.

Với API công khai, nên khai báo rõ:

- PathVariable("orderId")
- RequestParam(name = "page")
- RequestHeader(name = "X-Tenant")
- CookieValue(name = "sessionId")

Nếu dựa vào tên method parameter, cần biên dịch Java với -parameters để tên được lưu trong bytecode. Dù đã bật compiler option, tên tường minh vẫn giúp hợp đồng HTTP ổn định khi refactor.

## 5. Request và response schema được suy ra từ kiểu Java

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
        String customerCode,
        List<OrderItemRequest> items
) {}

public record OrderResponse(
        UUID id,
        String status,
        Instant createdAt
) {}
~~~

Springdoc có thể suy ra object schema, property, kiểu dữ liệu, array và reference đến schema lồng nhau từ các kiểu Java.

Tuy nhiên, kiểu Java không nói rõ:

- customerCode là mã khách hàng trong hệ thống nào.
- items có được phép rỗng hay không.
- status có những trạng thái hợp lệ nào và ý nghĩa từng trạng thái.
- createdAt là thời điểm tạo theo UTC hay theo múi giờ nghiệp vụ.
- Trường nào chỉ xuất hiện khi người gọi có quyền đặc biệt.

Hãy dùng Schema và Bean Validation để bổ sung metadata phù hợp:

~~~java
@Schema(name = "CreateOrderRequest")
public record CreateOrderRequest(
        @Schema(
                description = "Mã khách hàng đã được cấp trong hệ thống",
                example = "CUS-10025"
        )
        @NotBlank
        String customerCode,

        @Schema(
                description = "Các dòng hàng cần tạo trong đơn",
                minItems = 1
        )
        @NotEmpty
        List<@Valid OrderItemRequest> items
) {}
~~~

Schema mô tả hợp đồng; validation thực thi các constraint ở runtime. Hai việc liên quan nhưng không thay thế nhau.

## 6. Jackson ảnh hưởng tên và hình dạng JSON

DTO Java có thể được serialize thành JSON theo quy tắc Jackson. Vì vậy, schema do springdoc tạo chịu ảnh hưởng từ các annotation serialization được hỗ trợ.

Ví dụ:

~~~java
public record CustomerResponse(
        @JsonProperty("customer_code")
        String customerCode,
        String displayName
) {}
~~~

Tên property JSON public là customer_code, không phải customerCode. Khi cần tên JSON khác tên Java, hãy kiểm tra OpenAPI schema có phản ánh đúng Jackson configuration.

Các yếu tố cần rà soát:

- JsonProperty và naming strategy.
- JsonIgnore hoặc JsonProperty(access = ...).
- Getter/setter và field visibility.
- Record component.
- Custom serializer/deserializer.
- ObjectMapper được cấu hình toàn cục hoặc theo module.

Không suy ra JSON contract chỉ từ tên field trong source. OpenAPI document và JSON thực tế được serialize cần thống nhất.

## 7. Bean Validation cung cấp một phần constraint

Một số constraint có thể được phản ánh vào schema, ví dụ:

| Annotation | Ý nghĩa thường có thể biểu diễn |
|---|---|
| NotNull / NotBlank / NotEmpty | Giá trị bắt buộc hoặc không rỗng |
| Size | Giới hạn độ dài hoặc số phần tử |
| Min / Max | Giới hạn số |
| DecimalMin / DecimalMax | Giới hạn số thập phân |
| Pattern | Biểu thức chính quy |
| Email | Định dạng email |

Ví dụ:

~~~java
public record RegisterCustomerRequest(
        @NotBlank
        @Size(max = 100)
        String fullName,

        @NotBlank
        @Email
        String email,

        @Min(18)
        @Max(120)
        Integer age
) {}
~~~

Springdoc có thể sử dụng constraint metadata để bổ sung required, minLength, maxLength, pattern, minimum hoặc maximum tùy loại và phiên bản.

Nhưng các quy tắc như “email phải thuộc domain đã được doanh nghiệp xác minh”, “tuổi phải phù hợp sản phẩm” hoặc “mã khách hàng phải thuộc tenant đang đăng nhập” không thể được suy ra đầy đủ từ kiểu Java. Cần mô tả riêng và vẫn phải kiểm tra ở service/domain layer.

## 8. Kiểu enum có thể tạo danh sách giá trị

Enum Java thường cho phép springdoc tạo danh sách giá trị trong schema:

~~~java
public enum OrderStatus {
    DRAFT,
    PENDING,
    PAID,
    CANCELLED
}
~~~

Schema có thể thể hiện enum values. Nhưng tên kỹ thuật chưa giải thích trạng thái:

| Giá trị | Ý nghĩa nghiệp vụ cần bổ sung |
|---|---|
| DRAFT | Đơn được tạo nhưng chưa gửi xác nhận |
| PENDING | Đang chờ xử lý hoặc thanh toán |
| PAID | Đã ghi nhận thanh toán thành công |
| CANCELLED | Đơn đã bị hủy theo quy tắc hệ thống |

Nếu consumer cần hiểu transition, điều kiện hoặc khả năng chuyển trạng thái, hãy mô tả trong Schema description, Operation description hoặc tài liệu quy trình riêng. Danh sách enum không mô tả state machine.

## 9. Những thông tin không nên kỳ vọng springdoc tự hiểu

Các nội dung sau thường cần bổ sung thủ công hoặc thông qua cấu hình chuyên biệt:

| Thông tin | Vì sao cần bổ sung |
|---|---|
| Tên nghiệp vụ và mục đích operation | Tên method chỉ là chi tiết implementation |
| Summary/description hữu ích | Mapping không giải thích ý định của API |
| Ví dụ request/response thực tế | Kiểu Java không tạo được dữ liệu ví dụ có ý nghĩa |
| Error response theo nghiệp vụ | Không phải mọi nhánh exception đều hiện rõ từ chữ ký method |
| Authentication scheme | Spring Security filter chain không tự trở thành OpenAPI security scheme |
| Quyền/scopes cần thiết | Authorization rule không thể suy ra đầy đủ thành hợp đồng consumer |
| Tag và nhóm API theo audience | Package/class không luôn phản ánh cách tổ chức tài liệu mong muốn |
| Server URL theo môi trường | Local, staging, production và gateway có thể khác nhau |
| Rate limit/quota | Thường nằm ở gateway hoặc policy ngoài controller |
| Idempotency và retry semantics | Không thể suy ra chỉ từ HTTP method |
| Pagination/sorting conventions | Cần mô tả cách client sử dụng các parameter |
| Deprecation và sunset policy | Là quyết định vòng đời API |
| Workflow nhiều operation | Cần mô tả thứ tự và điều kiện nghiệp vụ |
| Data classification | Không thể suy ra mức độ nhạy cảm từ kiểu Java |

## 10. Summary và description cần phản ánh ngữ nghĩa

Tên method create, save, process hoặc handle không đủ thông tin cho người tích hợp.

Ví dụ bổ sung:

~~~java
@Operation(
        operationId = "createOrder",
        summary = "Tạo đơn hàng mới",
        description = """
                Tạo đơn hàng từ mã khách hàng và danh sách dòng hàng.
                Hệ thống kiểm tra quyền truy cập khách hàng, giá hiện hành
                và tính hợp lệ của từng dòng hàng trước khi ghi nhận đơn.
                """
)
@PostMapping
OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Summary nên ngắn và phân biệt được operation trong danh sách. Description giải thích điều kiện, tác động và các quy tắc mà client cần biết.

Không đưa bí mật, dữ liệu nội bộ hoặc chi tiết triển khai nhạy cảm vào description.

## 11. Ví dụ request và response cần dữ liệu có ý nghĩa

Schema chỉ cho biết kiểu string, integer hay object. Ví dụ giúp consumer hiểu định dạng và ngữ cảnh:

~~~java
public record CustomerCodeExample(
        @Schema(
                description = "Mã khách hàng",
                example = "CUS-10025",
                minLength = 3,
                maxLength = 20
        )
        String customerCode
) {}
~~~

Với response:

~~~java
@ApiResponse(
        responseCode = "201",
        description = "Đơn hàng đã được tạo",
        content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderResponse.class),
                examples = @ExampleObject(
                        name = "created-order",
                        value = """
                                {
                                  "id": "b4e7b1e0-72d3-4d75-9b8c-01e5c6c83f15",
                                  "status": "PENDING"
                                }
                                """
                )
        )
)
~~~

Ví dụ phải hợp lệ theo schema và không dùng dữ liệu khách hàng thật. Nếu một field có format hoặc enum constraint, example cần tuân thủ chúng.

## 12. Response lỗi cần được mô tả rõ

Từ kiểu trả về OrderResponse, springdoc có thể suy ra response thành công phổ biến. Nhưng implementation có thể ném exception ở nhiều lớp và được xử lý bởi ControllerAdvice.

Consumer cần biết các trường hợp như:

- 400: dữ liệu request không hợp lệ.
- 401: chưa xác thực.
- 403: không có quyền.
- 404: tài nguyên không tồn tại hoặc không hiển thị cho caller.
- 409: xung đột trạng thái hoặc idempotency key.
- 422: dữ liệu hợp lệ về cú pháp nhưng vi phạm quy tắc nghiệp vụ.
- 429: vượt quota hoặc rate limit.
- 500: lỗi hệ thống ngoài dự kiến.

Khai báo response phù hợp:

~~~java
@ApiResponses({
        @ApiResponse(
                responseCode = "201",
                description = "Đơn hàng đã được tạo",
                content = @Content(
                        schema = @Schema(implementation = OrderResponse.class)
                )
        ),
        @ApiResponse(
                responseCode = "400",
                description = "Dữ liệu yêu cầu không hợp lệ",
                content = @Content(
                        schema = @Schema(implementation = ApiError.class)
                )
        ),
        @ApiResponse(
                responseCode = "409",
                description = "Đơn hàng xung đột với trạng thái hiện tại",
                content = @Content(
                        schema = @Schema(implementation = ApiError.class)
                )
        )
})
~~~

Response được mô tả phải khớp với exception handler và status code thực tế. Annotation không tự tạo response lỗi hoặc thay đổi hành vi runtime.

## 13. Authentication và authorization cần khai báo riêng

Spring Security có thể bảo vệ endpoint bằng JWT, session, OAuth2 hoặc custom filter. Springdoc không nên được kỳ vọng tự chuyển toàn bộ cấu hình bảo mật runtime thành security scheme OpenAPI.

Ví dụ khai báo HTTP Bearer:

~~~java
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
)
~~~

Gắn requirement vào operation hoặc class:

~~~java
@Operation(
        summary = "Lấy đơn hàng",
        security = @SecurityRequirement(name = "bearerAuth")
)
~~~

Phân biệt:

- SecurityScheme mô tả cơ chế xác thực.
- SecurityRequirement chỉ ra operation yêu cầu scheme đó.
- Spring Security thực thi authentication và authorization thực tế.

Khai báo scheme mà không gắn requirement có thể khiến Swagger UI biết cách nhập token nhưng operation không được mô tả là cần xác thực. Ngược lại, requirement tham chiếu tên scheme chưa khai báo sẽ tạo document không nhất quán.

## 14. Tag và grouping là quyết định tổ chức tài liệu

Springdoc có thể dùng class/package hoặc cấu hình để nhóm operation, nhưng nhóm phù hợp với người tiêu thụ thường là quyết định thiết kế.

Ví dụ:

~~~java
@Tag(
        name = "Orders",
        description = "Tạo, tra cứu và quản lý vòng đời đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // ...
}
~~~

Với tài liệu lớn, dùng GroupedOpenApi để tạo các document theo audience hoặc miền chức năng:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .build();
}
~~~

Việc operation thuộc public, partner hay internal API không nên chỉ dựa vào tên package. Cần xác định rõ path filter và security policy của từng group.

## 15. Server URL và môi trường triển khai

Controller mapping có thể cho biết path tương đối, nhưng không nhất thiết cho biết URL mà consumer dùng ở production. Ứng dụng có thể chạy sau ingress, API gateway, reverse proxy hoặc context path.

Thông tin nên xác định:

- Public base URL.
- Context path hoặc API prefix.
- HTTP/HTTPS.
- URL dành cho sandbox và production.
- Server variables nếu có.

Có thể khai báo server trong OpenAPI metadata:

~~~java
@OpenAPIDefinition(
        servers = {
                @Server(
                        url = "https://api.example.com",
                        description = "Production API"
                ),
                @Server(
                        url = "https://sandbox-api.example.com",
                        description = "Sandbox API"
                )
        }
)
~~~

Không đưa URL giả định vào document production. Nếu URL thay đổi theo môi trường, dùng cấu hình theo profile hoặc customizer và xác minh output ở từng môi trường.

## 16. Pagination, sorting và filtering cần giải thích

Một method có Pageable hoặc các parameter page, size, sort không tự giải thích đầy đủ cách phân trang của API.

Consumer cần biết:

- Page index bắt đầu từ 0 hay 1.
- Default page size và maximum page size.
- Sort field nào được hỗ trợ.
- Cú pháp sort nhiều trường và chiều ASC/DESC.
- Filter có kết hợp AND hay OR.
- Cursor có hết hạn hay không.
- Response có totalElements, totalPages hoặc nextCursor không.

Dùng Parameter để mô tả parameter và Schema để mô tả response pagination. Nếu có quy ước chung, bổ sung mô tả ở tag hoặc tài liệu API tổng quan.

## 17. Những semantics khác cần bổ sung

Các thông tin sau ảnh hưởng cách client sử dụng API nhưng thường không suy ra được từ method signature:

- **Idempotency:** client có thể retry POST bằng key nào, thời hạn key và hành vi khi gửi lại.
- **Rate limit:** giới hạn request, cửa sổ thời gian và header trả về.
- **Concurrency:** ETag, If-Match hoặc version field dùng chống ghi đè.
- **Retry:** lỗi nào retry được, backoff và giới hạn số lần.
- **Asynchronous processing:** operation trả job ID hay hoàn tất ngay.
- **Webhook/callback:** xác thực callback, retry delivery và thứ tự event.
- **Deprecation:** ngày ngừng hỗ trợ và endpoint thay thế.
- **Data privacy:** field nào nhạy cảm, có bị mask hay không.

Nếu các quy tắc này quan trọng với consumer, hãy đưa vào OpenAPI extension, description hoặc tài liệu vận hành có liên kết rõ ràng.

## 18. Bổ sung metadata ở cấp module

Thông tin tổng quan có thể khai báo bằng OpenAPIDefinition:

~~~java
@OpenAPIDefinition(
        info = @Info(
                title = "Order API",
                version = "1.0.0",
                description = "API quản lý vòng đời đơn hàng",
                contact = @Contact(
                        name = "API Support",
                        email = "api-support@example.com"
                ),
                license = @License(
                        name = "Internal Use"
                )
        ),
        externalDocs = @ExternalDocumentation(
                description = "Hướng dẫn tích hợp",
                url = "https://docs.example.com/order-api"
        )
)
~~~

Đây là dữ liệu do đội API cung cấp. Springdoc không thể tự suy ra title, version public, contact hoặc license từ tên artifact Maven một cách đáng tin cậy.

Không dùng email hoặc URL ví dụ trong môi trường thật; thay bằng địa chỉ đã được tổ chức phê duyệt.

## 19. Dùng customizer khi annotation chưa đủ

Khi metadata được tạo từ cấu hình ngoài, hoặc cần áp dụng quy tắc chung, có thể dùng OpenApiCustomizer:

~~~java
@Bean
OpenApiCustomizer addCommonDescription() {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setDescription(
                    "API dành cho tích hợp đối tác đã được cấp quyền.");
        }
    };
}
~~~

Customizer phù hợp để:

- Bổ sung extension dùng chung.
- Chuẩn hóa tag hoặc server metadata.
- Áp dụng mô tả chung cho document.
- Điều chỉnh schema hoặc operation theo quy tắc hệ thống.

Không nên dùng customizer để che giấu lỗi mapping hoặc ghi đè hàng loạt metadata một cách khó kiểm soát. Với cấu hình group, xác định rõ customizer áp dụng cho document mặc định, từng group hay tất cả group.

## 20. Chọn đúng nơi bổ sung metadata

| Nhu cầu | Cách phù hợp |
|---|---|
| Mô tả toàn API, title, version, contact | OpenAPIDefinition / Info |
| Mô tả một operation | Operation |
| Mô tả một parameter | Parameter |
| Mô tả field/schema | Schema |
| Ví dụ request/response | ExampleObject |
| Response status và error schema | ApiResponse / ApiResponses |
| Authentication mechanism | SecurityScheme |
| Operation yêu cầu authentication | SecurityRequirement |
| Nhóm operation | Tag / GroupedOpenApi |
| Điều chỉnh theo quy tắc toàn cục | OpenApiCustomizer |

Chọn nơi gần với phạm vi thông tin nhất. Không đưa mô tả của một field vào description toàn API hoặc lặp lại cùng một đoạn văn ở mọi operation nếu có thể tái sử dụng schema/component.

## 21. Ví dụ kết hợp suy luận và bổ sung

Controller sau dùng Spring mapping và DTO để tạo phần cấu trúc, đồng thời bổ sung summary, description, response và parameter semantics:

~~~java
@Tag(name = "Orders", description = "Quản lý đơn hàng")
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(
            operationId = "getOrder",
            summary = "Tra cứu đơn hàng",
            description = "Tra cứu một đơn hàng mà người gọi có quyền xem."
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "200",
                    description = "Tìm thấy đơn hàng",
                    content = @Content(
                            schema = @Schema(implementation = OrderResponse.class)
                    )
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "Không tìm thấy đơn hàng",
                    content = @Content(
                            schema = @Schema(implementation = ApiError.class)
                    )
            )
    })
    @GetMapping("/{orderId}")
    OrderResponse getOrder(
            @Parameter(description = "Mã định danh đơn hàng")
            @PathVariable("orderId") UUID orderId) {
        // ...
    }
}
~~~

Springdoc suy ra path, method, path parameter và response type. Annotation bổ sung ý nghĩa operation, mô tả parameter và response status. Runtime service vẫn phải thực hiện kiểm tra quyền và trả đúng status tương ứng.

## 22. Không nhầm mô tả với hành vi thực tế

Annotation OpenAPI không tự:

- Bật authentication hoặc authorization.
- Tạo validation rule ở runtime.
- Thêm response handler.
- Thay đổi HTTP status code.
- Bật rate limit hoặc idempotency.
- Thay đổi JSON serialization.
- Tạo server endpoint mới.

Ví dụ, ApiResponse(responseCode = "404") chỉ mô tả response trong tài liệu. Controller hoặc exception handler vẫn phải thực sự trả HTTP 404 khi tình huống xảy ra.

Tương tự, Schema(requiredMode = REQUIRED) không thay thế Bean Validation. Nếu dữ liệu bắt buộc, cần đảm bảo runtime từ chối dữ liệu thiếu.

## 23. Kiểm tra OpenAPI document sau khi tạo

Không dừng ở việc mở Swagger UI. Hãy tải JSON:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra các path:

~~~bash
jq '.paths | keys' openapi.json
~~~

Kiểm tra operation:

~~~bash
jq '.paths["/api/orders/{orderId}"].get' openapi.json
~~~

Kiểm tra component schema:

~~~bash
jq '.components.schemas' openapi.json
~~~

Kiểm tra security schemes:

~~~bash
jq '.components.securitySchemes' openapi.json
~~~

Đối chiếu output với:

- Mapping thực tế trong controller.
- JSON do ObjectMapper serialize.
- Validation thực tế.
- SecurityFilterChain và quyền của endpoint.
- Exception handler và status code.
- URL public sau gateway/proxy.

Nếu các nguồn này mâu thuẫn, OpenAPI document chưa phải hợp đồng đáng tin cậy.

## 24. Kiểm thử tự động để phát hiện thông tin thiếu

Có thể viết integration test tải /v3/api-docs và kiểm tra các phần quan trọng:

~~~java
@Test
void orderOperationDocumentsExpectedContract() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                    "$.paths['/api/orders/{orderId}'].get.operationId")
                    .value("getOrder"))
            .andExpect(jsonPath(
                    "$.paths['/api/orders/{orderId}'].get.parameters[0].name")
                    .value("orderId"))
            .andExpect(jsonPath(
                    "$.paths['/api/orders/{orderId}'].get.responses.404")
                    .exists());
}
~~~

Test này chỉ là ví dụ kiểm tra cấu trúc. Trong dự án thật, nên duyệt parameter theo name và in thay vì giả định thứ tự mảng, đồng thời kiểm tra schema, security requirement và response content.

Có thể lưu OpenAPI JSON làm artifact trong CI, validate bằng công cụ OpenAPI lint và so sánh với bản phát hành trước để phát hiện breaking change.

## 25. Quy trình quyết định: tự động hay bổ sung?

Với mỗi thông tin trong API, đặt các câu hỏi:

1. Thông tin có thể được suy ra trực tiếp từ Spring mapping hoặc kiểu Java không?
2. Metadata có phản ánh đúng HTTP contract sau Jackson, validation và custom resolver không?
3. Consumer có cần biết ý nghĩa nghiệp vụ mà source code không thể hiện không?
4. Thông tin có ảnh hưởng đến bảo mật, lỗi, retry, version hoặc vận hành không?
5. Có thể khai báo một lần ở cấp schema, tag, class hoặc module thay vì lặp lại không?
6. Có integration test nào xác nhận document đúng với runtime không?

Nếu câu trả lời cho câu 1 và 2 là có, ưu tiên suy luận tự động để tránh lặp lại cấu trúc. Nếu câu 3 hoặc 4 là có, bổ sung metadata tường minh. Nếu câu 6 là không, cân nhắc thêm test trước khi công bố API.

## 26. Checklist hoàn thiện tài liệu API

- [ ] Path và HTTP method khớp Spring mapping.
- [ ] Tên path/query/header/cookie parameter khớp giao thức HTTP.
- [ ] Request và response schema phản ánh JSON thực tế.
- [ ] Jackson annotations và naming strategy được kiểm tra.
- [ ] Bean Validation được phản ánh và thực thi ở runtime.
- [ ] Enum có mô tả ý nghĩa nếu tên giá trị chưa đủ rõ.
- [ ] Operation có summary và description hữu ích.
- [ ] Request/response có example hợp lệ và không chứa dữ liệu thật nhạy cảm.
- [ ] Response lỗi quan trọng có status và schema đúng.
- [ ] Security scheme và requirement khớp chính sách runtime.
- [ ] Tag và GroupedOpenApi phản ánh audience/domain.
- [ ] Server URL đúng môi trường và gateway.
- [ ] Pagination, sorting, retry, idempotency và rate limit được mô tả khi áp dụng.
- [ ] Deprecation và version policy được công bố.
- [ ] OpenAPI JSON được kiểm tra trong CI.
- [ ] Contract được so sánh với bản phát hành trước.

## Kết luận

Springdoc-openapi có thể tự suy ra nhiều thông tin cấu trúc từ Spring mapping, chữ ký controller, kiểu Java, Jackson và Bean Validation. Khả năng này giúp tránh viết lặp lại path, method, parameter và schema. Nhưng implementation không thể tự giải thích đầy đủ ý nghĩa nghiệp vụ, ví dụ thực tế, response lỗi, security policy, server theo môi trường, rate limit, idempotency hay vòng đời API. Hãy để springdoc suy luận phần cấu trúc có thể kiểm chứng, bổ sung phần ngữ nghĩa bằng Operation, Parameter, Schema, ApiResponse, SecurityScheme, Tag và OpenAPI configuration, rồi xác minh JSON/YAML với hành vi runtime. Đó là cách tạo tài liệu vừa gần với code vừa đủ rõ để consumer tích hợp an toàn.

## Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Spring Framework Web MVC documentation](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring Framework WebFlux documentation](https://docs.spring.io/spring-framework/reference/web/webflux.html)
