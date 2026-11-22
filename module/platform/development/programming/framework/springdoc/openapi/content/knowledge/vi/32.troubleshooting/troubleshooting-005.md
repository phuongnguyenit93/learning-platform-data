# Operation biến mất do @Hidden, kế thừa hoặc mapping không được nhận diện

Một operation có thể không xuất hiện trong OpenAPI dù ứng dụng vẫn khởi động và một số API khác vẫn hoạt động. Nguyên nhân thường nằm ở một trong ba lớp: annotation yêu cầu ẩn operation, metadata mapping được đặt trên interface hoặc superclass nhưng không được Spring phân giải như mong đợi, hoặc controller/method không được Spring MVC hay Spring WebFlux đăng ký thành handler mà Springdoc có thể đọc.

Khi xử lý lỗi này, cần phân biệt hai câu hỏi: endpoint có thực sự được Spring đăng ký để nhận HTTP request không, và endpoint đã đăng ký có được đưa vào OpenAPI document hiện tại không? Nếu route vẫn nhận request nhưng không có trong /v3/api-docs, hãy kiểm tra annotation ẩn, bộ lọc package/path, document group và customizer. Nếu route cũng trả 404 hoặc không được handler mapping nhận diện, hãy kiểm tra controller bean, component scan, proxy và mapping annotation.

Bài học đi từ ý nghĩa của @Hidden tới cách Spring xử lý annotation trên interface, kế thừa và request mapping. Phần cuối xây dựng một quy trình chẩn đoán dựa trên handler mapping, OpenAPI JSON, group endpoint và test HTTP để tìm đúng lớp gây mất operation.

## 1. Phân loại hiện tượng trước khi sửa

Không phải mọi trường hợp Swagger thiếu operation đều có cùng nguyên nhân:

| Hiện tượng | Lớp cần kiểm tra đầu tiên |
|---|---|
| HTTP endpoint vẫn hoạt động nhưng OpenAPI không có path | @Hidden, @Operation(hidden), filter, group, customizer |
| Cả HTTP endpoint và OpenAPI đều không có | Controller bean, component scan, mapping registration |
| Path có nhưng thiếu một HTTP method | Method-level @Hidden, mapping condition, operation customizer |
| Method có trong default document nhưng mất trong group | GroupedOpenApi package/path filters |
| Parameter biến mất nhưng operation còn | @Parameter(hidden = true), parameter resolution |
| Schema hoặc property biến mất nhưng operation còn | @Schema(hidden = true), Jackson view hoặc schema customization |
| Endpoint có trên JVM nhưng không có trong profile khác | @Profile, @Conditional, component scan hoặc cấu hình môi trường |
| Mapping nằm trên interface nhưng route không được đăng ký | Cách đặt @RequestMapping, proxy strategy và Spring Framework version |

Trước khi chỉnh annotation, hãy xác nhận URL, HTTP method, profile, context path và OpenAPI endpoint đang kiểm tra. Có thể ứng dụng đang chạy một profile hoặc một document group khác với giả định của người phát triển.

## 2. @Hidden ở cấp controller

Springdoc hỗ trợ annotation io.swagger.v3.oas.annotations.Hidden trên controller. Khi đặt ở cấp type, annotation yêu cầu loại controller khỏi tài liệu:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/reports")
public class InternalReportController {

    @GetMapping
    public List<ReportResponse> listReports() {
        return reportService.findAll();
    }
}
~~~

Trong trường hợp này, operation GET /internal/reports không được đưa vào OpenAPI document. Tuy nhiên, @Hidden chỉ điều khiển việc tạo tài liệu. Nó không vô hiệu hóa bean, không gỡ RequestMappingHandlerMethod và không chặn HTTP request.

Nếu endpoint cần được bảo vệ, hãy dùng Spring Security, authorization ở service hoặc một cơ chế kiểm soát truy cập phù hợp. Ẩn path trong Swagger UI không phải biện pháp bảo mật.

## 3. @Hidden ở cấp method

Có thể ẩn riêng một method mà vẫn công bố những method còn lại của controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable UUID id) {
        return orderService.getById(id);
    }

    @Hidden
    @DeleteMapping("/{id}/purge")
    public void purgeOrder(@PathVariable UUID id) {
        orderService.purge(id);
    }
}
~~~

Operation GET /orders/{id} vẫn xuất hiện, còn DELETE /orders/{id}/purge bị ẩn khỏi OpenAPI.

Đây là cách phù hợp khi controller có cả API công khai và operation chỉ dành cho tác vụ nội bộ. Tuy nhiên, nếu một nhóm tài liệu khác cũng cần operation đó, annotation @Hidden vẫn có thể loại operation khỏi tài liệu nói chung; hãy cân nhắc dùng GroupedOpenApi hoặc customizer theo group thay vì ẩn toàn cục.

## 4. Dùng @Operation(hidden = true)

Một cách khác để ẩn operation là đặt thuộc tính hidden trong annotation Operation:

~~~java
@GetMapping("/diagnostics")
@Operation(
    operationId = "getDiagnostics",
    summary = "Lấy thông tin chẩn đoán",
    hidden = true
)
public DiagnosticsResponse diagnostics() {
    return diagnosticsService.snapshot();
}
~~~

@Operation(hidden = true) có phạm vi rõ ở operation. Có thể dùng khi method đã có các metadata OpenAPI khác nhưng cần ẩn toàn bộ operation.

Không nhầm hidden với deprecated. deprecated báo operation không nên được dùng cho tích hợp mới nhưng vẫn có thể xuất hiện trong tài liệu. hidden loại operation khỏi tài liệu.

## 5. Phân biệt @Hidden, @Parameter(hidden) và @Schema(hidden)

Ba annotation này tác động tới các mức khác nhau:

| Annotation | Đối tượng bị ẩn | Operation có còn không? |
|---|---|---|
| @Hidden trên controller | Toàn bộ controller khỏi tài liệu | Không |
| @Hidden trên method | Method/operation khỏi tài liệu | Không |
| @Operation(hidden = true) | Operation | Không |
| @Parameter(hidden = true) | Một parameter | Có |
| @Schema(hidden = true) | Schema, field hoặc property tại vị trí áp dụng | Thường có |

Ví dụ ẩn một parameter nội bộ:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(
        @PathVariable UUID id,
        @Parameter(hidden = true) @AuthenticationPrincipal UserPrincipal principal) {
    return orderService.getForUser(id, principal);
}
~~~

Operation vẫn có trong OpenAPI; chỉ parameter principal không được mô tả như input mà client phải gửi.

Ví dụ ẩn một property của schema:

~~~java
public class OrderResponse {

    private UUID id;

    @Schema(hidden = true)
    private String internalRiskScore;
}
~~~

Nếu người phát triển đặt nhầm @Parameter(hidden = true) hoặc @Schema(hidden = true) với mục đích ẩn cả endpoint, operation vẫn có thể xuất hiện. Hãy kiểm tra đúng vị trí annotation trước khi sửa code.

## 6. @Hidden trên RestControllerAdvice

Springdoc cũng hỗ trợ @Hidden trên RestControllerAdvice. Điều này hữu ích khi một advice chỉ phục vụ xử lý lỗi nội bộ và không nên xuất hiện như một phần tài liệu API.

~~~java
@Hidden
@RestControllerAdvice
public class InternalExceptionAdvice {

    @ExceptionHandler(InternalWorkflowException.class)
    ResponseEntity<InternalError> handle(InternalWorkflowException ex) {
        return ResponseEntity.internalServerError()
            .body(new InternalError("INTERNAL_WORKFLOW_ERROR"));
    }
}
~~~

Springdoc còn xét @Hidden trên exception handler method khi xây dựng generic error response từ ControllerAdvice. Vì vậy, một operation vẫn còn nhưng phần response lỗi tổng quát thay đổi có thể liên quan tới advice hoặc exception handler bị ẩn.

Đừng đặt @Hidden trên một advice dùng chung nếu các response lỗi của advice đó cần được mô tả trong tài liệu công khai. Hãy tách advice theo phạm vi hoặc dùng cấu hình response phù hợp.

## 7. Kiểm tra import đúng annotation

Trong codebase có thể tồn tại nhiều annotation cùng tên hoặc annotation tùy biến của tổ chức. Annotation ẩn của Swagger là:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

Annotation Operation là:

~~~java
import io.swagger.v3.oas.annotations.Operation;
~~~

Nếu có một annotation nội bộ cũng tên Hidden, hãy xem import thực tế của class hoặc method. Annotation được import nhầm có thể khiến Springdoc không xử lý như dự kiến.

Khi debug, kiểm tra source đã compile hoặc bytecode của class đang chạy, đặc biệt nếu ứng dụng có nhiều module và dependency chứa cùng class name.

## 8. @Hidden có làm endpoint ngừng hoạt động không?

Không. @Hidden là metadata phục vụ quá trình đọc annotation và tạo tài liệu. Spring MVC hoặc WebFlux vẫn có thể đăng ký mapping và gọi method.

Có thể kiểm chứng bằng hai request:

~~~bash
curl -i http://localhost:8080/internal/reports
curl -s http://localhost:8080/v3/api-docs
~~~

Nếu request đầu trả response nhưng JSON thứ hai không có /internal/reports, route vẫn tồn tại nhưng đã bị ẩn khỏi tài liệu.

Đây là hành vi có chủ đích trong nhiều ứng dụng. Tuy nhiên, không dùng việc thiếu path trong OpenAPI làm bằng chứng endpoint không thể truy cập.

## 9. Annotation trên interface được Springdoc hỗ trợ

Springdoc FAQ xác nhận thư viện hỗ trợ annotation từ interface. Vì vậy, một API contract có thể khai báo mapping và OpenAPI metadata trên interface, còn class triển khai cung cấp logic:

~~~java
@RequestMapping("/orders")
public interface OrderApi {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Tra cứu đơn hàng"
    )
    OrderResponse getOrder(@PathVariable UUID id);
}
~~~

Class triển khai:

~~~java
@RestController
public class OrderController implements OrderApi {

    @Override
    public OrderResponse getOrder(UUID id) {
        return orderService.getById(id);
    }
}
~~~

Springdoc có thể đọc các annotation API từ interface. Tuy nhiên, cần phân biệt việc Springdoc đọc metadata với việc Spring MVC thực sự đăng ký handler. Một annotation có thể được nhìn thấy trong quá trình tạo OpenAPI nhưng mapping runtime vẫn phụ thuộc quy tắc phát hiện controller của Spring Framework và cách proxy được tạo.

## 10. Interface method và interface type-level mapping

Có hai vị trí mapping thường được đặt trên interface:

- Method-level mapping như @GetMapping("/{id}").
- Type-level mapping như @RequestMapping("/orders").

Trong một số cấu hình, method-level mapping được phân giải nhưng type-level mapping không được áp dụng như kỳ vọng. Điều này đặc biệt cần chú ý khi controller bị bọc bằng JDK interface proxy.

Spring Framework 6.0 thay đổi cách phát hiện controller: với interface proxy, Spring MVC không còn nhận controller chỉ dựa trên @RequestMapping ở cấp type của interface. Tài liệu Spring Framework đề nghị dùng class-based proxy hoặc đặt @Controller trên interface trong trường hợp đó.

Để giảm mơ hồ, có thể đặt @RestController và base path trên implementation class, còn interface giữ method contract và metadata:

~~~java
public interface OrderApi {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Tra cứu đơn hàng"
    )
    OrderResponse getOrder(@PathVariable UUID id);
}

@RestController
@RequestMapping("/orders")
public class OrderController implements OrderApi {

    @Override
    public OrderResponse getOrder(UUID id) {
        return orderService.getById(id);
    }
}
~~~

Sau thay đổi, kiểm tra cả handler mapping lẫn OpenAPI. Không chỉ nhìn document để kết luận Spring MVC đã đăng ký đúng route.

## 11. Annotation trên superclass và method kế thừa

Một controller có thể kế thừa method từ lớp cha:

~~~java
public abstract class BaseReadController<T> {

    @GetMapping("/{id}")
    public abstract T getById(@PathVariable UUID id);
}

@RestController
@RequestMapping("/customers")
public class CustomerController extends BaseReadController<CustomerResponse> {

    @Override
    public CustomerResponse getById(UUID id) {
        return customerService.getById(id);
    }
}
~~~

Spring và Springdoc phải giải quyết method thực thi, generic type và annotation trên hierarchy. Khi operation biến mất hoặc schema trở thành Object không mong đợi, hãy kiểm tra method được override có giữ mapping và metadata cần thiết hay không.

Java không tự kế thừa mọi annotation. @Inherited chỉ có tác dụng với annotation đặt trên class khi đọc qua superclass; nó không làm annotation trên interface hoặc method tự động được kế thừa. @Hidden của Swagger được khai báo cho TYPE, METHOD, FIELD và ANNOTATION_TYPE nhưng không mang meta-annotation @Inherited.

Vì vậy, đừng giả định @Hidden đặt trên superclass luôn được áp dụng cho mọi subclass, hoặc @Hidden trên interface method chắc chắn được chuyển tới method implementation trong mọi cấu hình. Nếu muốn ẩn một endpoint cụ thể, đặt annotation trực tiếp trên method của controller triển khai là cách rõ ràng nhất. Sau đó kiểm tra output trên đúng version Springdoc.

## 12. Annotation trên interface và annotation trên implementation có thể khác nhau

Ví dụ interface mô tả operation:

~~~java
public interface AdminApi {

    @GetMapping("/audit")
    @Operation(operationId = "getAudit")
    List<AuditEntry> getAudit();
}
~~~

Implementation có thể bổ sung annotation:

~~~java
@RestController
@RequestMapping("/admin")
public class AdminController implements AdminApi {

    @Override
    @Hidden
    public List<AuditEntry> getAudit() {
        return auditService.findRecent();
    }
}
~~~

Nếu operation vẫn xuất hiện, hãy kiểm tra cách phiên bản Springdoc đang hợp nhất annotation giữa interface và implementation. Có thể cần đặt metadata ẩn tại nơi Springdoc thực sự đọc trong cấu trúc controller hiện tại, hoặc dùng OperationCustomizer để loại operation theo path/method một cách rõ ràng.

Một quy tắc hữu ích là giữ contract metadata ở một vị trí nhất quán, tránh lặp @Operation, @Hidden và mapping ở nhiều lớp nếu không có chủ đích.

## 13. Controller có được Spring quản lý không?

Springdoc tạo tài liệu từ endpoint được Spring quản lý. Nếu class chỉ là một Java object thông thường, không được đăng ký thành bean controller, Springdoc không có handler mapping chuẩn để mô tả.

Ví dụ controller được phát hiện:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

Hãy kiểm tra:

- Class có @RestController hoặc @Controller phù hợp không?
- Package có nằm trong component scan không?
- Bean có bị @Profile hoặc @Conditional loại ở profile hiện tại không?
- Module chứa controller có nằm trong runtime classpath không?
- Có cấu hình excludeFilters trong component scan không?
- Bean có khởi tạo thành công không?

Nếu bean không được tạo, việc thêm @Operation hoặc @Hidden sẽ không giải quyết nguyên nhân.

## 14. @Controller không có @ResponseBody

Springdoc FAQ ghi rõ @Controller không có @ResponseBody thường không được xem là REST endpoint để đưa vào tài liệu. Đây là hành vi mặc định vì method có thể trả về tên view thay vì response body.

Ví dụ MVC view controller:

~~~java
@Controller
@RequestMapping("/reports")
public class ReportPageController {

    @GetMapping
    public String index(Model model) {
        return "reports/index";
    }
}
~~~

Nếu method thực sự trả JSON, dùng @RestController hoặc kết hợp @Controller và @ResponseBody:

~~~java
@Controller
@RequestMapping("/api/reports")
public class ReportApiController {

    @ResponseBody
    @GetMapping
    public List<ReportResponse> list() {
        return reportService.findAll();
    }
}
~~~

Với ứng dụng legacy không thể thay đổi annotation, SpringDocUtils có thể đăng ký class bổ sung như REST controller:

~~~java
static {
    SpringDocUtils.getConfig()
        .addRestControllers(LegacyReportController.class);
}
~~~

Chỉ dùng cách này cho class thực sự phục vụ REST response. Không ép mọi @Controller trả view vào OpenAPI.

## 15. Component scan sai package

Một lỗi phổ biến là application class nằm ở package không phải parent của controller package.

Ví dụ cấu trúc:

~~~text
com.acme.application.Application
com.acme.web.order.OrderController
~~~

Nếu component scan chỉ bao phủ com.acme.application, controller trong com.acme.web.order có thể không được phát hiện.

Có thể đặt scan base package có chủ đích:

~~~java
@SpringBootApplication(scanBasePackages = "com.acme")
public class Application {
}
~~~

Không mở rộng component scan tới toàn bộ package gốc nếu điều đó làm khởi tạo thêm bean không mong muốn. Chọn package hẹp và kiểm tra bean thực tế trong ApplicationContext.

## 16. Kiểm tra loại web stack và framework đang dùng

Springdoc tập trung vào endpoint REST được quản lý bởi Spring. Nếu ứng dụng dùng Jersey/JAX-RS với @Path và @GET, Springdoc không tự động mô tả các resource đó như Spring MVC controller.

Phân biệt:

| Web API style | Annotation/mapping thường gặp |
|---|---|
| Spring MVC | @RestController, @RequestMapping, @GetMapping |
| Spring WebFlux annotated controller | @RestController, @RequestMapping, @GetMapping |
| JAX-RS/Jersey | @Path, @GET, @POST |
| Spring functional route | RouterFunction, route DSL |

Với functional route, cần cấu hình và module hỗ trợ phù hợp; không giả định một RouterFunction sẽ được xử lý như method @GetMapping. Nếu ứng dụng kết hợp nhiều web framework, xác định handler mapping nào đang phục vụ URL bị thiếu.

## 17. @RequestMapping trên class và method

Spring MVC kết hợp mapping cấp type và cấp method:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse get(@PathVariable UUID id) {
        return orderService.getById(id);
    }

    @PostMapping
    public OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Mapping cuối cùng được tạo từ class path và method path. Trong ví dụ:

| Method mapping | Path cuối |
|---|---|
| GET /{id} | GET /api/orders/{id} |
| POST | POST /api/orders |

Khi tìm operation, hãy kiểm tra cả mapping cấp class và method. Một path prefix được chuyển sang class khác hoặc thay đổi bằng placeholder có thể làm URL thực tế khác với đường dẫn người phát triển đang tìm trong JSON.

## 18. Không đặt nhiều mapping annotation trên cùng một element

Spring Framework cảnh báo không nên đặt nhiều @RequestMapping hoặc composed mapping annotation trên cùng một class hay method. Nếu có nhiều annotation mapping trên cùng element, Spring ghi warning và chỉ dùng annotation đầu tiên được phát hiện.

Ví dụ không nên viết:

~~~java
@GetMapping("/orders")
@PostMapping("/orders")
public Object orders() {
    return null;
}
~~~

Hãy tách method:

~~~java
@GetMapping("/orders")
public List<OrderResponse> list() {
    return orderService.findAll();
}

@PostMapping("/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Nếu cần một custom composed annotation, tạo một annotation duy nhất meta-annotated với @RequestMapping và đặt một HTTP method/path rõ ràng. Không kết hợp @GetMapping và @PostMapping trên cùng method để mong Spring tạo hai operation.

## 19. Mapping có điều kiện

Một handler có thể chỉ được đăng ký hoặc chỉ khớp request khi các điều kiện phù hợp:

- method: GET, POST, PUT, DELETE...
- params: query parameter phải có hoặc có giá trị cụ thể.
- headers: header phải có hoặc bằng giá trị xác định.
- consumes: Content-Type của request.
- produces: Accept hoặc media type response.
- version: API version nếu framework/configuration hỗ trợ.

Ví dụ:

~~~java
@GetMapping(
    value = "/reports",
    params = "format=summary",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ReportSummary summary() {
    return reportService.summary();
}
~~~

Nếu đang tìm operation GET /reports nhưng method chỉ map khi có params format=summary, hãy kiểm tra điều kiện đó. Operation có thể được biểu diễn trong OpenAPI với parameter tương ứng; nếu metadata thiếu hoặc custom mapping quá phức tạp, document có thể không phản ánh đầy đủ điều kiện runtime.

## 20. Mapping trùng hoặc mơ hồ

Hai method có mapping trùng nhau có thể khiến Spring không đăng ký handler như mong muốn hoặc phát sinh lỗi ambiguous mapping khi khởi động. Hãy đọc startup log, đặc biệt các thông báo liên quan tới RequestMappingHandlerMapping.

Ví dụ:

~~~java
@GetMapping("/{id}")
public OrderResponse find(@PathVariable String id) { ... }

@GetMapping("/{code}")
public OrderResponse findByCode(@PathVariable String code) { ... }
~~~

Hai pattern có cùng cấu trúc và cùng điều kiện HTTP có thể xung đột. Đổi một path rõ ràng, ví dụ /by-code/{code}, hoặc dùng mapping condition có ý nghĩa.

Nếu ứng dụng khởi động thất bại vì ambiguous mapping, OpenAPI generation không thể sửa lỗi này. Hãy giải quyết xung đột handler trước.

## 21. Placeholder và prefix của URL

Ví dụ class-level mapping đặt base path trực tiếp:

~~~java
@RequestMapping("/api/orders")
public class OrderController {
}
~~~

Giá trị thực tế có thể còn chịu ảnh hưởng của property source, profile và servlet configuration. Nếu OpenAPI có path /v2/orders nhưng bạn đang tìm /api/orders, hãy kiểm tra cấu hình đã resolve.

Ngoài ra, các yếu tố sau có thể làm URL khi truy cập khác path trong OpenAPI:

- server.servlet.context-path.
- spring.mvc.servlet.path.
- Reverse proxy prefix.
- Forwarded headers.
- API versioning strategy.

Không thêm context path vào mọi annotation một cách máy móc. Xác định phần path thuộc controller mapping và phần do servlet/proxy cung cấp.

## 22. Bộ lọc package và path của Springdoc

Ngay cả khi controller được đăng ký đúng, Springdoc có thể loại nó khỏi document bằng cấu hình include/exclude.

Ví dụ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.public
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

Nếu controller nằm trong com.acme.api.admin hoặc path bắt đầu bằng /internal, nó có thể không xuất hiện theo cấu hình này.

Springdoc FAQ cũng cung cấp cấu hình chọn package và path để lọc endpoint. Hãy kiểm tra chính xác property binding của version đang dùng; tên property trong tài liệu và cấu hình cũ có thể khác cách viết.

Nếu không cần lọc toàn cục, bỏ các filter không cần thiết rồi kiểm tra lại. Đừng mở toàn bộ package chỉ để làm một operation xuất hiện nếu điều đó vô tình công bố endpoint nội bộ.

## 23. GroupedOpenApi có thể loại operation khỏi một document

Một ứng dụng có thể tạo nhiều OpenAPI document:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .packagesToScan("com.acme.api.public")
        .pathsToMatch("/api/**")
        .build();
}
~~~

Document group có URL mặc định:

~~~text
/v3/api-docs/public
~~~

Nếu operation chỉ nằm trong group internal, nó sẽ không có trong document public. Đây không phải lỗi mất operation toàn hệ thống.

Kiểm tra:

1. /v3/api-docs mặc định.
2. /v3/api-docs/{groupName} của từng group.
3. packagesToScan.
4. pathsToMatch và pathsToExclude.
5. OpenApiCustomizer gắn riêng cho group.

Đừng chỉ kiểm tra Swagger UI đang chọn một group rồi kết luận Springdoc không tạo operation.

## 24. Customizer có thể xóa path hoặc operation sau khi scan

Springdoc cho phép tùy biến OpenAPI document sau khi quét controller. Nếu một OpenApiCustomizer hoặc OperationCustomizer xóa path, method hoặc operation, handler mapping vẫn có thể tồn tại nhưng kết quả cuối cùng không còn operation.

Ví dụ customizer xóa path nội bộ:

~~~java
@Bean
OpenApiCustomizer removeInternalPaths() {
    return openApi -> {
        if (openApi.getPaths() != null) {
            openApi.getPaths().remove("/api/internal/diagnostics");
        }
    };
}
~~~

Khi debug, tìm toàn bộ bean:

- OpenApiCustomizer.
- GlobalOpenApiCustomizer.
- OperationCustomizer.
- GroupedOpenApi.addOpenApiCustomizer.
- GroupedOpenApi.addOperationCustomizer.

Kiểm tra thứ tự thực thi và điều kiện của từng customizer. Một customizer dùng cho group có thể chỉ loại operation khỏi group đó, trong khi default document vẫn giữ.

Nếu customizer xóa operation dựa trên path string, kiểm tra path sau khi placeholder và mapping prefix được resolve. Sai khác dấu slash hoặc version prefix có thể khiến rule lọc áp dụng nhầm.

## 25. API docs bị tắt không đồng nghĩa Swagger UI bị tắt

Hai property điều khiển khác nhau:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

springdoc.api-docs.enabled=false tắt endpoint OpenAPI. springdoc.swagger-ui.enabled=false chỉ tắt giao diện Swagger UI; OpenAPI JSON/YAML vẫn có thể được cung cấp nếu api-docs còn bật.

Nếu toàn bộ document endpoint không truy cập được, kiểm tra property api-docs. Nếu chỉ không mở được trang Swagger UI, kiểm tra UI dependency và property swagger-ui.

Đừng dùng swagger-ui.enabled=false để xử lý một operation cụ thể biến mất khỏi JSON. Nó không phải filter operation.

## 26. Kiểm tra handler mapping bằng Actuator

Spring Boot Actuator có endpoint mappings để xem các handler được đăng ký. Trong môi trường phát triển hoặc test, có thể expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,mappings
~~~

Sau đó kiểm tra:

~~~bash
curl -s http://localhost:8080/actuator/mappings
~~~

Tìm path và controller method cần kiểm tra. Endpoint mappings cho biết Spring đã đăng ký handler nào; OpenAPI document cho biết Springdoc đã đưa operation nào vào tài liệu.

Chẩn đoán theo kết quả:

| Có trong /actuator/mappings | Có trong OpenAPI | Hướng điều tra |
|---|---|---|
| Có | Có | Operation đã được nhận diện |
| Có | Không | @Hidden, group/filter, customizer hoặc metadata |
| Không | Không | Controller bean, mapping, proxy, profile hoặc web stack |
| Không | Có | Kiểm tra document có phải từ runtime/instance khác hoặc customizer tự thêm path |

Không expose /actuator/mappings công khai nếu không cần. Mapping có thể tiết lộ tên controller, path nội bộ và cấu trúc ứng dụng. Bảo vệ endpoint bằng Spring Security hoặc chỉ bật trong profile test.

## 27. Kiểm tra trực tiếp OpenAPI JSON

Không chỉ dựa vào Swagger UI. Gọi endpoint tài liệu:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Tìm path:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Kiểm tra một operation cụ thể:

~~~bash
jq '.paths["/api/orders/{id}"]' target/openapi.json
~~~

Nếu path tồn tại nhưng thiếu method, xem object của path và các method get, post, put, patch, delete. Nếu không có path, kiểm tra filter hoặc @Hidden.

Nếu dùng group, gọi đúng URL group và lưu file riêng:

~~~bash
curl --fail --silent \
  http://localhost:8080/v3/api-docs/public \
  -o target/openapi-public.json
~~~

Document phải được lấy từ đúng instance, profile và version đang điều tra. Tránh so sánh một file đã export trước đó với ứng dụng đang chạy mà không kiểm tra timestamp hoặc commit.

## 28. Kiểm tra annotation ở runtime

Nếu source có @Hidden nhưng operation vẫn xuất hiện, hãy kiểm tra class thực sự được load:

- Xác minh package và class name của bean trong ApplicationContext.
- Kiểm tra import của @Hidden.
- Kiểm tra annotation nằm trên concrete controller hay interface/superclass.
- Kiểm tra method implementation có override method khai báo mapping không.
- Kiểm tra nhiều module có class cùng tên.
- Kiểm tra build output có được cập nhật hay ứng dụng đang chạy artifact cũ.

Có thể dùng reflection trong test để xác nhận annotation:

~~~java
Method method = OrderController.class
    .getDeclaredMethod("purgeOrder", UUID.class);

assertThat(method.isAnnotationPresent(Hidden.class)).isTrue();
~~~

Test này chỉ xác nhận annotation nằm trực tiếp trên method. Nó không chứng minh Springdoc đã áp dụng annotation trong quá trình tạo document. Vẫn cần kiểm tra OpenAPI output.

Nếu annotation đến từ interface hoặc meta-annotation, hãy kiểm tra hierarchy và merged annotation bằng Spring AnnotationUtils hoặc MergedAnnotations phù hợp với version Spring. Không dựa vào getDeclaredAnnotation trên implementation để kết luận annotation không tồn tại ở interface.

## 29. Tạo integration test chống tái phát

Khi sửa lỗi, nên có test xác nhận operation xuất hiện hoặc biến mất đúng chủ đích.

Ví dụ test OpenAPI JSON:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpenApiVisibilityTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void publicOperationIsDocumented() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/v3/api-docs", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
            .contains("/api/orders/{id}")
            .contains("get");
    }

    @Test
    void hiddenOperationIsNotDocumented() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/v3/api-docs", String.class);

        assertThat(response.getBody())
            .doesNotContain("/api/internal/diagnostics");
    }
}
~~~

Ví dụ trên minh họa cách tiếp cận; nên parse JSON bằng Jackson và kiểm tra cấu trúc paths/method thay vì phụ thuộc substring khi suite lớn. Nếu ứng dụng có nhiều group, test từng group riêng.

Đối với operation ẩn nhưng route vẫn phải hoạt động, viết thêm HTTP test:

~~~java
@Test
void hiddenEndpointStillHasItsRuntimePolicy() {
    ResponseEntity<String> response =
        restTemplate.getForEntity("/api/internal/diagnostics", String.class);

    assertThat(response.getStatusCode())
        .isIn(HttpStatus.OK, HttpStatus.UNAUTHORIZED, HttpStatus.FORBIDDEN);
}
~~~

Status mong đợi cần được thay bằng policy thực tế của ứng dụng. Mục tiêu là chứng minh việc ẩn tài liệu không vô tình thay đổi runtime behavior.

## 30. Quy trình chẩn đoán theo thứ tự

Khi một operation biến mất, làm theo trình tự:

1. Ghi lại URL, HTTP method, profile và instance đang kiểm tra.
2. Gọi trực tiếp endpoint REST để biết route còn hoạt động không.
3. Kiểm tra /actuator/mappings trong môi trường được bảo vệ.
4. Gọi /v3/api-docs thay vì chỉ nhìn Swagger UI.
5. Nếu dùng group, gọi đúng /v3/api-docs/{groupName}.
6. Tìm @Hidden trên controller, superclass, interface, method và advice.
7. Tìm @Operation(hidden = true) trên method.
8. Phân biệt @Parameter(hidden = true) và @Schema(hidden = true).
9. Kiểm tra @Controller có @ResponseBody hoặc đổi sang @RestController.
10. Kiểm tra component scan, @Profile và @Conditional.
11. Kiểm tra interface mapping, proxy type và Spring Framework version.
12. Kiểm tra class-level và method-level @RequestMapping.
13. Tìm nhiều mapping annotation trên cùng element và ambiguous mapping.
14. Kiểm tra packages-to-scan, paths-to-match và paths-to-exclude.
15. Kiểm tra customizer có xóa path hoặc operation không.
16. Kiểm tra API version, context path và property placeholder.
17. Restart hoặc refresh đúng instance sau khi đổi cấu hình.
18. Thêm integration test cho hành vi mong đợi.

Không thay đổi nhiều lớp cùng lúc. Mỗi lần chỉ thay một nguyên nhân đã có bằng chứng, sau đó kiểm tra handler mapping và OpenAPI output để xác nhận.

## 31. Bảng nguyên nhân và cách sửa

| Nguyên nhân | Dấu hiệu | Cách xử lý |
|---|---|---|
| @Hidden trên controller | Mọi method của controller biến mất | Bỏ annotation nếu muốn công bố controller |
| @Hidden trên method | Chỉ một operation biến mất | Bỏ hoặc chuyển annotation sang method thực sự cần ẩn |
| @Operation(hidden = true) | Operation không xuất hiện dù mapping hoạt động | Đổi hidden=false hoặc bỏ metadata ẩn |
| Nhầm @Parameter(hidden) | Parameter biến mất nhưng operation vẫn còn | Kiểm tra đúng mục tiêu ẩn |
| Nhầm @Schema(hidden) | Property/schema biến mất | Đặt annotation ở schema đúng hoặc bỏ hidden |
| Annotation nằm trên interface | Kết quả khác giữa interface và implementation | Kiểm tra merged annotation; đặt metadata rõ trên method cụ thể |
| Type-level mapping trên interface với JDK proxy | Controller không được Spring MVC nhận diện | Đặt mapping trên implementation hoặc dùng class-based proxy theo yêu cầu |
| @Controller thiếu @ResponseBody | Method trả view và không vào REST docs | Dùng @RestController hoặc @ResponseBody |
| Controller ngoài component scan | Không có bean và không có mapping | Sửa scan base package |
| Profile/conditional loại bean | Chỉ mất ở một môi trường | Kiểm tra active profile và điều kiện bean |
| Nhiều mapping annotation cùng method | Spring warning và chỉ dùng mapping đầu tiên | Tách method hoặc tạo composed annotation đúng |
| Mapping trùng | Startup error hoặc handler mơ hồ | Làm mapping duy nhất |
| Package/path filter | Chỉ một số path bị loại | Sửa packages-to-scan hoặc paths-to-match/exclude |
| Sai document group | Có trong group khác nhưng không có ở group hiện tại | Kiểm tra GroupedOpenApi |
| Customizer xóa operation | Handler có nhưng OpenAPI không có | Sửa rule của OpenApiCustomizer/OperationCustomizer |
| Kiểm tra nhầm artifact cũ | JSON không đổi dù source đã sửa | Xác nhận process, profile, build và timestamp |

## 32. Ghi nhớ

- @Hidden trên controller ẩn toàn bộ controller khỏi tài liệu; trên method ẩn operation đó.
- @Operation(hidden = true) là lựa chọn trực tiếp để ẩn một operation.
- @Parameter(hidden = true) chỉ ẩn parameter; @Schema(hidden = true) tác động tới schema/property.
- @Hidden không tắt route và không thay thế Spring Security.
- Springdoc hỗ trợ annotation từ interface, nhưng việc Spring MVC đăng ký handler vẫn theo quy tắc mapping và proxy của Spring Framework.
- Từ Spring Framework 6.0, JDK interface proxy không được nhận diện chỉ dựa vào type-level @RequestMapping trên interface.
- Java không tự kế thừa annotation từ interface hoặc method; đặt annotation trực tiếp khi cần kết quả rõ ràng.
- Controller phải là Spring-managed bean; @Controller không có @ResponseBody thường không được xem là REST endpoint.
- Không đặt nhiều @RequestMapping/composed mapping trên cùng element.
- GroupedOpenApi, package/path filters và customizer có thể loại operation khỏi một document.
- So sánh /actuator/mappings với /v3/api-docs để phân biệt lỗi mapping và lỗi tài liệu.
- Kiểm tra từng document group và đúng runtime instance.
- Thêm integration test xác nhận cả visibility trong OpenAPI và runtime behavior.

Khi operation biến mất, hãy xác minh route trong handler mapping trước, rồi kiểm tra OpenAPI document và group cụ thể. @Hidden hoặc customizer có thể chỉ ẩn tài liệu trong khi endpoint vẫn hoạt động; ngược lại, interface mapping, component scan hoặc mapping annotation sai có thể khiến Spring không đăng ký handler ngay từ đầu. Phân biệt hai trường hợp này sẽ giúp sửa đúng nguyên nhân và giữ được hành vi API mong muốn.

## Tài liệu tham khảo

- Springdoc OpenAPI FAQ – Hide an operation or controller: https://springdoc.org/faq.html
- Springdoc OpenAPI FAQ – Interface annotations and controller detection: https://springdoc.org/faq.html
- Swagger Core – Hidden annotation API: https://docs.swagger.io/swagger-core/v2.2.40/apidocs/io/swagger/v3/oas/annotations/Hidden.html
- Spring Framework – Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework – Controller Declaration and AOP Proxies: https://docs.spring.io/spring/reference/web/webmvc/mvc-controller/ann.html
