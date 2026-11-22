# Ẩn Controller hoặc operation bằng @Hidden

Trong một ứng dụng Spring Boot, không phải mọi endpoint đã đăng ký đều cần xuất hiện trong tài liệu API dành cho người tích hợp. Có thể tồn tại endpoint nội bộ, endpoint phục vụ vận hành, route tương thích ngược hoặc method chỉ dùng cho tác vụ đặc biệt. Springdoc cung cấp annotation @Hidden để loại controller hoặc method khỏi OpenAPI document được sinh.

@Hidden tác động tới quá trình mô tả API. Nó không gỡ Spring bean, không xóa request mapping và không chặn HTTP request. Nếu một endpoint cần hạn chế truy cập, ứng dụng vẫn phải dùng Spring Security và kiểm tra quyền nghiệp vụ. Đây là ranh giới quan trọng nhất khi dùng annotation này.

Bài học giải thích cách ẩn toàn controller, chỉ ẩn một operation, lựa chọn @Operation(hidden = true), xử lý @RestControllerAdvice và exception handler, đồng thời phân biệt việc ẩn operation với việc ẩn parameter hoặc schema. Cuối bài có ví dụ kiểm tra OpenAPI document để xác nhận đúng phần bị ẩn và xác minh hành vi HTTP vẫn tuân theo chính sách bảo mật.

## 1. @Hidden dùng để làm gì?

@Hidden thuộc Swagger annotations:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

Springdoc đọc annotation này khi phân tích controller và tạo OpenAPI document. Tùy vị trí đặt annotation:

- Đặt trên controller để ẩn các operation của controller đó.
- Đặt trên method để ẩn riêng operation tương ứng.
- Đặt trên @RestControllerAdvice để loại advice khỏi phần mô tả được Springdoc xây dựng.
- Đặt trên exception handler method để ảnh hưởng tới việc Springdoc tạo generic error response từ @ControllerAdvice.

Swagger Core khai báo @Hidden có runtime retention và các target gồm TYPE, METHOD, FIELD, ANNOTATION_TYPE. Trong ứng dụng Springdoc, trường hợp thường dùng nhất là type và method. Với field hoặc schema property, @Schema(hidden = true) thường diễn đạt mục tiêu rõ ràng hơn.

## 2. Ẩn toàn bộ Controller

Khi đặt @Hidden trên class controller, Springdoc loại controller đó khỏi tài liệu:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/maintenance")
public class MaintenanceController {

    @GetMapping("/status")
    public MaintenanceStatus getStatus() {
        return maintenanceService.currentStatus();
    }

    @PostMapping("/rebuild-index")
    public RebuildResult rebuildIndex() {
        return maintenanceService.rebuildIndex();
    }
}
~~~

Các operation GET /internal/maintenance/status và POST /internal/maintenance/rebuild-index sẽ không được đưa vào OpenAPI document do Springdoc tạo.

Đây là lựa chọn phù hợp khi toàn bộ controller thuộc một nhóm endpoint không dành cho người tiêu thụ API công khai. Ví dụ:

- Endpoint bảo trì chỉ dành cho đội vận hành.
- Endpoint kiểm tra nội bộ được gọi bởi hệ thống giám sát.
- Endpoint phục vụ tác vụ migration hoặc sửa dữ liệu.
- Controller legacy không muốn công bố trong tài liệu dành cho đối tác.

Nếu chỉ một method trong controller cần ẩn, hãy dùng method-level @Hidden để các operation còn lại vẫn được tài liệu hóa.

## 3. Ẩn riêng một method trong Controller

Có thể giữ controller và các operation công khai, đồng thời loại một method khỏi OpenAPI:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders", description = "Tra cứu và quản lý đơn hàng")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Tra cứu đơn hàng"
    )
    public OrderResponse getById(@PathVariable UUID id) {
        return orderService.getById(id);
    }

    @Hidden
    @PostMapping("/{id}/replay-events")
    public ReplayResult replayEvents(@PathVariable UUID id) {
        return orderService.replayEvents(id);
    }

    @DeleteMapping("/{id}")
    @Operation(
        operationId = "deleteOrder",
        summary = "Xóa đơn hàng"
    )
    public ResponseEntity<Void> delete(@PathVariable UUID id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong document:

- GET /api/orders/{id} vẫn xuất hiện.
- DELETE /api/orders/{id} vẫn xuất hiện.
- POST /api/orders/{id}/replay-events bị ẩn.

Đặt annotation ngay trên method triển khai giúp ý định rõ ràng cho người đọc source. Sau khi thêm annotation, hãy kiểm tra JSON thực tế thay vì chỉ dựa vào việc code biên dịch.

## 4. @Operation(hidden = true) là cách khác để ẩn operation

Springdoc cũng hỗ trợ thuộc tính hidden của @Operation:

~~~java
@PostMapping("/internal/reindex")
@Operation(
    operationId = "reindexCatalog",
    summary = "Tạo lại chỉ mục tìm kiếm",
    hidden = true
)
public ReindexResult reindex() {
    return catalogService.reindex();
}
~~~

Hai cách thường dùng:

~~~java
@Hidden
@PostMapping("/internal/reindex")
public ReindexResult reindex() {
    return catalogService.reindex();
}
~~~

~~~java
@PostMapping("/internal/reindex")
@Operation(hidden = true)
public ReindexResult reindex() {
    return catalogService.reindex();
}
~~~

Chọn một cách cho mỗi operation để tránh metadata dư thừa. @Hidden là annotation tổng quát của Swagger để đánh dấu resource hoặc method không được đọc vào tài liệu; @Operation(hidden = true) diễn đạt trực tiếp rằng operation OpenAPI không được công bố.

## 5. So sánh phạm vi của các cách ẩn

| Cách khai báo | Đối tượng bị ẩn | Các operation khác trong controller |
|---|---|---|
| @Hidden trên controller | Toàn controller | Cũng bị ẩn |
| @Hidden trên method | Method tương ứng | Vẫn được giữ |
| @Operation(hidden = true) | Operation tương ứng | Vẫn được giữ |
| @Hidden trên @RestControllerAdvice | Advice trong quá trình tạo tài liệu | Controller nghiệp vụ vẫn được giữ |
| @Parameter(hidden = true) | Một parameter | Operation vẫn được giữ |
| @Schema(hidden = true) | Schema/property tại vị trí áp dụng | Operation thường vẫn được giữ |

Hãy chọn annotation theo đúng cấp độ muốn ẩn. Dùng nhầm @Parameter(hidden = true) sẽ chỉ làm biến mất parameter, không làm operation biến mất. Dùng @Schema(hidden = true) cũng không phải cách ẩn cả controller.

## 6. Import đúng @Hidden

Annotation cần dùng là:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

Không nhầm với annotation có tên tương tự trong package nội bộ hoặc thư viện khác. Nếu thêm @Hidden mà operation vẫn xuất hiện, kiểm tra import trong source và dependency Swagger annotations thực tế.

Các annotation OpenAPI khác thường đi cùng:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

Sau khi refactor dependency Springdoc hoặc Swagger Core, hãy kiểm tra package và version của annotation được compile vào ứng dụng.

## 7. @Hidden không vô hiệu hóa endpoint

Đây là điểm cần nhớ khi ẩn endpoint nội bộ. @Hidden chỉ điều khiển việc Springdoc đọc endpoint để tạo tài liệu. Spring MVC hoặc Spring WebFlux vẫn có thể đăng ký mapping và tiếp tục nhận request.

Ví dụ:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
public class DiagnosticsController {

    @GetMapping
    public DiagnosticsSnapshot snapshot() {
        return diagnosticsService.snapshot();
    }
}
~~~

Sau khi thêm @Hidden:

- /v3/api-docs không có path /internal/diagnostics.
- Spring vẫn có thể đăng ký GET /internal/diagnostics.
- Request HTTP trực tiếp vẫn có thể chạy nếu vượt qua security filter và các điều kiện runtime khác.

Không dùng việc endpoint vắng mặt trong Swagger UI làm bằng chứng endpoint đã được bảo vệ hoặc không thể truy cập.

## 8. Bảo vệ endpoint bằng Spring Security

Nếu endpoint chỉ dành cho administrator, hãy đặt quy tắc authorization độc lập với @Hidden:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/internal/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ minh họa. Dự án thực tế có thể dùng OAuth2 Resource Server, JWT, session hoặc cơ chế xác thực khác. Quy tắc quan trọng là authorization phải được thực thi ở runtime và được kiểm tra bằng HTTP test.

Có thể kết hợp:

~~~java
@Hidden
@RestController
@RequestMapping("/internal")
public class InternalAdminController {
    // endpoint nội bộ
}
~~~

@Hidden giữ tài liệu công khai gọn và không công bố operation nội bộ. Spring Security kiểm soát ai được gọi endpoint. Hai cơ chế giải quyết hai mục tiêu khác nhau.

## 9. Ẩn ControllerAdvice

Springdoc hỗ trợ @Hidden trên @RestControllerAdvice:

~~~java
@Hidden
@RestControllerAdvice
public class InternalExceptionAdvice {

    @ExceptionHandler(InternalWorkflowException.class)
    ResponseEntity<InternalErrorResponse> handle(
            InternalWorkflowException exception) {
        return ResponseEntity.internalServerError()
            .body(new InternalErrorResponse("INTERNAL_WORKFLOW_ERROR"));
    }
}
~~~

Một advice có thể chứa exception handler chỉ phục vụ nội bộ hoặc không nên xuất hiện trong phần generic error response của tài liệu. Đặt @Hidden trên advice giúp Springdoc bỏ qua advice đó trong quá trình tạo tài liệu tương ứng.

Không đặt annotation trên một advice dùng chung nếu response lỗi của nó cần được mô tả trong API công khai. Trong trường hợp đó, hãy giữ advice được nhận diện và mô tả error schema một cách rõ ràng.

## 10. Ẩn một exception handler method

Có thể ẩn một handler method riêng:

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("PRODUCT_NOT_FOUND"));
    }

    @Hidden
    @ExceptionHandler(InternalWorkflowException.class)
    ResponseEntity<InternalErrorResponse> handleInternal(
            InternalWorkflowException ex) {
        return ResponseEntity.internalServerError()
            .body(new InternalErrorResponse("INTERNAL_WORKFLOW_ERROR"));
    }
}
~~~

Springdoc ghi nhận @Hidden trên exception handler method khi xây dựng generic error responses từ @ControllerAdvice. Điều này ảnh hưởng tới metadata response được tổng hợp trong OpenAPI document; nó không xóa exception handler khỏi Spring runtime.

Nếu muốn người dùng API biết response 404 nhưng không muốn công bố cấu trúc lỗi nội bộ, hãy mô tả 404 bằng schema công khai phù hợp. Đừng ẩn toàn bộ advice chỉ để loại một response nội bộ nếu điều đó làm mất các response lỗi công khai khác.

## 11. Phân biệt @Hidden với @Parameter(hidden = true)

@Parameter(hidden = true) ẩn một parameter khỏi tài liệu:

~~~java
@GetMapping("/me")
public ProfileResponse getCurrentProfile(
        @Parameter(hidden = true)
        @AuthenticationPrincipal UserPrincipal principal) {
    return profileService.getProfile(principal);
}
~~~

Operation GET /me vẫn xuất hiện. Parameter principal không được mô tả như một giá trị mà client phải gửi, vì Spring Security cung cấp nó từ security context.

Một ví dụ khác là parameter kỹ thuật được framework inject:

~~~java
@GetMapping("/report")
public ReportResponse report(
        @RequestParam String period,
        @Parameter(hidden = true) HttpServletRequest request) {
    return reportService.create(period, request.getLocale());
}
~~~

period vẫn là query parameter công khai; request không xuất hiện trong danh sách input của operation.

Nếu mục tiêu là ẩn cả endpoint, dùng @Hidden hoặc @Operation(hidden = true).

## 12. Phân biệt @Hidden với @Schema(hidden = true)

@Schema(hidden = true) phù hợp để ẩn một field hoặc schema property:

~~~java
public class UserResponse {

    private UUID id;

    private String displayName;

    @Schema(hidden = true)
    private String internalRiskMarker;
}
~~~

Operation trả về UserResponse vẫn được công bố, nhưng property internalRiskMarker được loại khỏi schema theo vị trí áp dụng.

Springdoc cũng hỗ trợ ẩn response schema ở cấp operation:

~~~java
@Operation(
    responses = @ApiResponse(
        responseCode = "200",
        content = @Content(schema = @Schema(hidden = true))
    )
)
@GetMapping("/internal/export")
public InternalExport export() {
    return exportService.create();
}
~~~

Trong trường hợp này, operation vẫn có thể tồn tại trong document, nhưng schema của response được ẩn. Nếu muốn loại toàn operation, hãy dùng @Hidden hoặc @Operation(hidden = true).

## 13. Không nhầm ẩn operation với tắt toàn bộ API docs

Một số cơ chế có phạm vi rộng hơn:

| Cơ chế | Phạm vi |
|---|---|
| @Hidden trên controller | Một controller |
| @Hidden trên method | Một operation |
| @Operation(hidden = true) | Một operation |
| GroupedOpenApi filters | Một document group theo package/path |
| springdoc.api-docs.enabled=false | Tắt các endpoint OpenAPI của Springdoc |
| springdoc.swagger-ui.enabled=false | Tắt Swagger UI |

Nếu chỉ cần ẩn một endpoint, không tắt springdoc.api-docs.enabled. Nếu muốn vẫn có JSON nhưng không cần giao diện, điều chỉnh Swagger UI riêng.

## 14. Khi cần khác nhau giữa public và internal document

@Hidden là lựa chọn ở mức annotation và thường loại operation khỏi các OpenAPI document mà Springdoc tạo cho ứng dụng. Nó không phải cơ chế chỉ ẩn trong một group.

Giả sử cùng một operation cần:

- Không xuất hiện trong tài liệu public.
- Vẫn xuất hiện trong tài liệu internal dành cho đội vận hành.

Trong trường hợp này, không nên gắn @Hidden trực tiếp vào method vì mục tiêu là phân biệt theo document group. Hãy cấu hình các GroupedOpenApi với package/path filters phù hợp hoặc dùng customizer riêng cho từng group.

Ví dụ:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .packagesToScan("com.acme.api")
        .pathsToExclude("/internal/**")
        .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
        .group("internal")
        .packagesToScan("com.acme")
        .pathsToMatch("/internal/**")
        .build();
}
~~~

Kiểm tra từng endpoint document, ví dụ /v3/api-docs/public và /v3/api-docs/internal. Đảm bảo internal document cũng được bảo vệ bằng Spring Security nếu không dành cho mọi người dùng.

## 15. Chọn giữa @Hidden và filter

| Nhu cầu | Cách phù hợp |
|---|---|
| Ẩn toàn bộ controller ở mọi document | @Hidden trên controller |
| Ẩn đúng một method ở mọi document | @Hidden trên method hoặc @Operation(hidden = true) |
| Ẩn một package khỏi public group | GroupedOpenApi package filter |
| Ẩn một path khỏi một group | GroupedOpenApi path filter |
| Thêm quy tắc lọc phức tạp theo operation | Customizer riêng cho group |
| Ẩn parameter được framework inject | @Parameter(hidden = true) |
| Ẩn property nội bộ trong schema | @Schema(hidden = true) |

Đừng dùng @Hidden để thay thế group filtering nếu cùng operation phải được công bố trong một document khác.

## 16. Đặt @Hidden trên interface hoặc method kế thừa

Một số controller khai báo contract trên interface rồi triển khai trong class:

~~~java
public interface AdminOperations {

    @PostMapping("/rebuild")
    RebuildResult rebuild();
}

@RestController
@RequestMapping("/internal/index")
public class IndexAdminController implements AdminOperations {

    @Override
    public RebuildResult rebuild() {
        return indexService.rebuild();
    }
}
~~~

Springdoc có thể đọc nhiều loại annotation từ interface, nhưng kết quả cụ thể phụ thuộc cách Spring phân giải handler, proxy và phiên bản thư viện. Khi cần ẩn một operation, vị trí rõ ràng nhất thường là method triển khai thực tế:

~~~java
@Override
@Hidden
public RebuildResult rebuild() {
    return indexService.rebuild();
}
~~~

Nếu vẫn xuất hiện trong document, kiểm tra JSON output, annotation trên interface và implementation, cùng cấu trúc proxy đang dùng. Không giả định Java tự động kế thừa mọi annotation từ interface sang method triển khai.

## 17. Annotation trên custom composed annotation

Swagger Core cho phép @Hidden xuất hiện trên annotation type. Điều này mở khả năng tạo annotation nội bộ để đánh dấu một nhóm controller:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Hidden
public @interface InternalApiController {
}
~~~

Sau đó:

~~~java
@InternalApiController
@RestController
@RequestMapping("/internal/cache")
public class CacheAdminController {
}
~~~

Đây là kỹ thuật meta-annotation; cần kiểm chứng việc Springdoc và phiên bản Swagger annotations đang dùng nhận diện annotation tổng hợp trong đúng cấu trúc ứng dụng. Nếu muốn hành vi dễ đoán nhất, đặt @Hidden trực tiếp trên controller hoặc method và kiểm tra OpenAPI JSON.

## 18. Kiểm tra import và dependency khi @Hidden không có tác dụng

Nếu operation vẫn xuất hiện sau khi thêm annotation, hãy kiểm tra lần lượt:

1. Import có đúng io.swagger.v3.oas.annotations.Hidden không?
2. Annotation được đặt trên đúng class hoặc method mà Spring đăng ký làm handler không?
3. Có interface hoặc proxy làm method được phân giải khác với source đang xem không?
4. Ứng dụng đang chạy artifact mới hay một build cũ?
5. Có nhiều dependency Swagger annotations hoặc Springdoc version xung đột không?
6. Đang xem đúng OpenAPI document và group không?
7. Có customizer thêm lại operation sau khi scan không?

Không chỉ nhìn Swagger UI vì UI có thể đang đọc document khác hoặc cache. Gọi trực tiếp endpoint OpenAPI để xác minh output.

## 19. Kiểm tra operation trong OpenAPI JSON

Giả sử controller có path:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/maintenance")
public class MaintenanceController {

    @GetMapping("/status")
    public MaintenanceStatus status() {
        return maintenanceService.status();
    }
}
~~~

Lấy document:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Tìm path:

~~~bash
jq '.paths | keys' target/openapi.json
~~~

Kiểm tra trực tiếp:

~~~bash
jq '.paths["/internal/maintenance/status"]' target/openapi.json
~~~

Nếu controller bị ẩn đúng, biểu thức cuối trả null. Với method-level hiding, path có thể còn vì operation khác cùng path vẫn tồn tại; khi đó hãy kiểm tra riêng method get, post, delete trong object path.

## 20. Kiểm tra nhiều HTTP method trên cùng một path

Một path có thể chứa nhiều operation:

~~~java
@RestController
@RequestMapping("/api/reports")
public class ReportController {

    @GetMapping("/{id}")
    public ReportResponse get(@PathVariable UUID id) {
        return reportService.get(id);
    }

    @Hidden
    @DeleteMapping("/{id}")
    public void purge(@PathVariable UUID id) {
        reportService.purge(id);
    }
}
~~~

OpenAPI có thể giữ path /api/reports/{id} với operation get, nhưng không có operation delete. Vì vậy, không chỉ kiểm tra path key; phải kiểm tra method bên trong.

~~~bash
jq '.paths["/api/reports/{id}"] | keys' target/openapi.json
~~~

Kết quả mong đợi có get và không có delete.

## 21. Integration test xác minh operation bị ẩn

Có thể kiểm tra OpenAPI document bằng MockMvc và Jackson:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HiddenOperationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void hiddenControllerDoesNotAppearInOpenApi() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode document = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );

        assertThat(document.path("paths")
            .has("/internal/maintenance/status")).isFalse();
    }
}
~~~

Với method-level hiding:

~~~java
@Test
void hiddenMethodIsRemovedButVisibleMethodRemains() throws Exception {
    MvcResult result = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode paths = objectMapper.readTree(
        result.getResponse().getContentAsString()
    ).path("paths");

    JsonNode orderPath = paths.path("/api/orders/{id}");

    assertThat(orderPath.has("get")).isTrue();
    assertThat(orderPath.has("post")).isFalse();
}
~~~

Đổi path và method theo controller thực tế của dự án. Nếu dùng nhiều GroupedOpenApi, gọi đúng URL của từng group và kiểm tra riêng từng document.

## 22. Kiểm tra endpoint vẫn chịu chính sách runtime

Một test OpenAPI chỉ chứng minh operation đã bị ẩn khỏi tài liệu. Nó không chứng minh endpoint đã bị khóa.

Nếu endpoint nội bộ phải yêu cầu quyền ADMIN, cần có HTTP test riêng:

~~~java
@Test
void internalEndpointRejectsAnonymousRequest() throws Exception {
    mockMvc.perform(get("/internal/maintenance/status"))
        .andExpect(status().isUnauthorized());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminCanCallInternalEndpoint() throws Exception {
    mockMvc.perform(get("/internal/maintenance/status"))
        .andExpect(status().isOk());
}
~~~

Status chính xác phụ thuộc cấu hình Spring Security. Một ứng dụng có thể trả 302 khi dùng form login hoặc 403 khi policy được thiết kế như vậy. Điều quan trọng là test phải phản ánh chính sách thực tế.

Nếu endpoint được ẩn nhưng vẫn cho phép anonymous request, đó là hành vi runtime hiện tại; annotation không thay đổi điều đó.

## 23. Ẩn một Controller không thay thế việc tắt Actuator endpoint

Các endpoint Actuator có cơ chế exposure và security riêng. Nếu một endpoint Actuator không nên được cung cấp, cấu hình Actuator và Spring Security theo đúng yêu cầu vận hành.

@Hidden trên controller nghiệp vụ không tự điều khiển Actuator. Tương tự, ẩn một endpoint khỏi OpenAPI không làm endpoint ngừng được expose qua servlet mapping hoặc management port.

Nếu ứng dụng có management server port riêng, kiểm tra cả cổng ứng dụng và cổng quản trị.

## 24. Cache và document group khi kiểm tra kết quả

Springdoc có thể cache OpenAPI description. Khi thay đổi annotation trong môi trường đang chạy, hãy xác nhận document được lấy từ đúng process và đúng cấu hình. Nếu ứng dụng có cấu hình cache riêng hoặc nhiều instance, kiểm tra tất cả instance trước khi kết luận annotation không được áp dụng.

Đối với group:

- /v3/api-docs là document mặc định.
- /v3/api-docs/{group} là document của group.
- Swagger UI có thể đang trỏ tới một group khác.

Một operation vắng mặt trong public group nhưng có trong internal group có thể là kết quả filtering có chủ đích. Không cần thêm @Hidden nếu yêu cầu chỉ là khác nhau giữa các group.

## 25. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thêm @Hidden nhưng operation vẫn có | Import sai hoặc annotation đặt trên method không phải handler thực tế | Kiểm tra import, mapping và implementation |
| Controller biến mất khỏi Swagger UI nhưng route vẫn truy cập được | @Hidden chỉ ẩn tài liệu | Bổ sung Spring Security nếu route cần hạn chế |
| Chỉ parameter biến mất | Dùng @Parameter(hidden = true) | Dùng @Hidden hoặc @Operation(hidden = true) nếu cần ẩn operation |
| Schema property biến mất | Dùng @Schema(hidden = true) | Kiểm tra mục tiêu ẩn; operation có thể vẫn còn |
| Một method biến mất cùng cả controller | @Hidden đặt trên class | Chuyển annotation xuống method nếu chỉ muốn ẩn một operation |
| Operation mất ở mọi group | Dùng @Hidden cho mục tiêu chỉ cần ẩn ở public group | Dùng GroupedOpenApi filter hoặc customizer riêng |
| Exception response không còn trong document | @Hidden trên advice hoặc exception handler | Kiểm tra generic error response và mô tả response công khai tường minh |
| Swagger UI không đổi sau sửa source | UI đọc group/document khác hoặc cache | Gọi /v3/api-docs trực tiếp và kiểm tra đúng instance |
| Endpoint nội bộ vẫn gọi được không cần login | Chỉ dùng @Hidden mà không có authorization | Bảo vệ runtime bằng Spring Security |
| Method-level test báo path vẫn tồn tại | Cùng path còn operation khác | Kiểm tra HTTP method trong path item |

## 26. Quy trình áp dụng @Hidden

Khi quyết định ẩn một phần API:

1. Xác định chính xác controller, method, advice, parameter hay schema cần ẩn.
2. Xác định tài liệu nào cần ẩn: tất cả document hay chỉ một group.
3. Dùng @Hidden trên controller nếu muốn ẩn toàn controller.
4. Dùng @Hidden hoặc @Operation(hidden = true) trên method nếu muốn ẩn một operation.
5. Dùng @Parameter(hidden = true) cho parameter nội bộ.
6. Dùng @Schema(hidden = true) cho property hoặc schema cần ẩn.
7. Với public/internal documents khác nhau, ưu tiên group filter/customizer.
8. Kiểm tra /v3/api-docs và document group liên quan.
9. Viết test xác nhận path/method đã biến mất khỏi document.
10. Viết HTTP test xác nhận runtime authorization vẫn đúng.

Không thay đổi nhiều cơ chế cùng lúc. Sau mỗi thay đổi, kiểm tra OpenAPI JSON và request thực tế để biết annotation đang tác động đúng phạm vi.

## 27. Ghi nhớ

- @Hidden thuộc io.swagger.v3.oas.annotations.Hidden.
- Đặt trên controller để ẩn các operation của controller khỏi tài liệu.
- Đặt trên method để ẩn riêng operation.
- @Operation(hidden = true) là lựa chọn khác để ẩn một operation.
- Springdoc hỗ trợ @Hidden trên @RestController, @RestControllerAdvice và method.
- @Hidden trên exception handler method được xét khi Springdoc tạo generic error response từ ControllerAdvice.
- @Parameter(hidden = true) chỉ ẩn parameter.
- @Schema(hidden = true) ẩn schema/property tại vị trí áp dụng.
- @Hidden không gỡ route và không thực thi authentication/authorization.
- Nếu cần ẩn khác nhau theo document group, dùng GroupedOpenApi filter hoặc customizer.
- Kiểm tra JSON OpenAPI trực tiếp; với method-level hiding, kiểm tra cả HTTP method chứ không chỉ path.
- Test riêng visibility của document và quyền truy cập HTTP.

@Hidden là công cụ kiểm soát phạm vi tài liệu. Nó giúp giữ OpenAPI document tập trung vào các operation mà nhóm người đọc cần biết, trong khi Spring vẫn quản lý endpoint theo cấu hình runtime. Hãy chọn đúng cấp độ annotation, kiểm tra document được sinh và duy trì security test độc lập để bảo đảm việc ẩn tài liệu không bị hiểu nhầm thành bảo vệ endpoint.

## Tài liệu tham khảo

- Springdoc OpenAPI – FAQ: Hide an operation or a controller: https://springdoc.org/faq.html
- Springdoc OpenAPI v2 – FAQ: https://springdoc.org/v2/faq.html
- Springdoc OpenAPI v1 – FAQ: https://springdoc.org/v1/faq.html
- Swagger Core – Hidden annotation API: https://docs.swagger.io/swagger-core/v2.2.40/apidocs/io/swagger/v3/oas/annotations/Hidden.html
- Spring Security – Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
