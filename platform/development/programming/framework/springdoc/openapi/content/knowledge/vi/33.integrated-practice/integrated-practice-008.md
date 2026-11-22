# Tài liệu hóa cùng một miền API trên MVC và WebFlux

Một miền nghiệp vụ có thể được cung cấp qua hai ứng dụng Spring Boot: một ứng dụng dùng Spring Web MVC trên Servlet stack và một ứng dụng dùng Spring WebFlux trên reactive stack. Dù cách xử lý request khác nhau, consumer vẫn cần nhìn thấy cùng một HTTP contract: path, method, parameter, request body, response schema, status code, security và quy tắc validation.

springdoc-openapi có starter riêng cho MVC và WebFlux. Mỗi ứng dụng sinh OpenAPI Description từ controller và cấu hình của chính runtime đó. Vì vậy, cần thiết kế hai adapter sao cho chúng công bố cùng hợp đồng, rồi kiểm tra hai document và response thực tế bằng cùng một bộ contract test.

Bài thực hành dùng miền Catalog với ba operation:

| Operation | Method và path | Mục đích |
|---|---|---|
| Lấy sản phẩm | GET /api/products/{id} | Trả về một sản phẩm |
| Tìm sản phẩm | GET /api/products?keyword=... | Trả về danh sách sản phẩm |
| Tạo sản phẩm | POST /api/products | Tạo sản phẩm mới |

Hai ứng dụng dùng chung API DTO và quy tắc nghiệp vụ. MVC và WebFlux có controller adapter, web stack, cấu hình springdoc và runtime riêng.

## 1. Phân biệt hai web stack

Spring Web MVC chạy trên Servlet API. Request được xử lý qua Servlet container như Tomcat hoặc Jetty; controller thường trả object, ResponseEntity hoặc kiểu bất đồng bộ được framework hỗ trợ.

Spring WebFlux là web framework reactive, non-blocking. Nó thường chạy trên Reactor Netty, nhưng cũng có thể dùng Tomcat hoặc Jetty với reactive adapter. Controller có thể trả Mono hoặc Flux; functional endpoint dùng RouterFunction và HandlerFunction.

| Khía cạnh | Spring MVC | Spring WebFlux |
|---|---|---|
| Runtime model | Servlet, request thread được quản lý theo mô hình Servlet | Reactive Streams, non-blocking event loop |
| Starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Body conversion | HttpMessageConverter | HttpMessageReader và HttpMessageWriter |
| Controller phổ biến | @RestController và @RequestMapping | @RestController và @RequestMapping |
| Reactive return type | Có thể hỗ trợ Mono/Flux qua ReactiveAdapterRegistry | Hỗ trợ Mono/Flux tự nhiên |
| Functional endpoint | MVC.fn có mô hình riêng | WebFlux.fn dùng RouterFunction |
| springdoc API starter | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| springdoc UI starter | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |

Điểm cần nhớ: hai stack dùng nhiều annotation controller giống nhau, nhưng không phải cùng một runtime. MVC dùng message converter; WebFlux dùng codec. Việc cùng có @GetMapping không đảm bảo mọi kiểu tham số, kiểu trả về, streaming hoặc custom converter sẽ hoạt động giống nhau.

## 2. Vì sao nên tách thành hai ứng dụng hoặc hai deployable adapter?

Spring Boot chọn web application type trong lúc khởi động. Nếu một classpath có cả spring-boot-starter-web và spring-boot-starter-webflux, Boot mặc định auto-configure Spring MVC. Lý do phổ biến là nhiều ứng dụng MVC thêm WebFlux chỉ để sử dụng WebClient.

Có thể ép application type thành REACTIVE, nhưng điều đó vẫn chỉ chọn một stack cho ứng dụng đang chạy. Một Spring Boot application context thông thường không tự tạo hai HTTP server độc lập để cùng phục vụ MVC và WebFlux.

Với bài toán cần kiểm tra cùng một miền API trên cả hai stack, cách rõ ràng là tạo hai deployable riêng:

~~~mermaid
flowchart TB
    subgraph Shared["Shared contract and application"]
      DTO["API DTO / validation"]
      USE["Use cases / domain services"]
      RULES["Business rules"]
    end
    subgraph MVC["Catalog MVC application"]
      MC["MVC controller adapter"]
      MD["springdoc WebMVC"]
      MS["Servlet server"]
      MC --> MD
      MC --> MS
    end
    subgraph FLUX["Catalog WebFlux application"]
      FC["WebFlux controller adapter"]
      FD["springdoc WebFlux"]
      FS["Reactive server"]
      FC --> FD
      FC --> FS
    end
    DTO --> MC
    DTO --> FC
    USE --> MC
    USE --> FC
    RULES --> USE
~~~

Ví dụ cấu trúc multi-module:

~~~text
catalog/
  catalog-contract/
    ProductRequest.java
    ProductResponse.java
    ApiError.java
  catalog-application/
    CatalogUseCases.java
    CatalogService.java
  catalog-mvc-app/
    ProductMvcController.java
    OpenApiConfiguration.java
    application.yml
  catalog-webflux-app/
    ProductWebFluxController.java
    OpenApiConfiguration.java
    application.yml
  contract-tests/
    CatalogContractTest.java
~~~

Hai app có thể dùng chung DTO, validation constraints, service port và policy nghiệp vụ. Mỗi app chỉ cài web adapter và springdoc starter tương ứng. CI khởi động hai app ở hai port hoặc hai job riêng.

Không thêm cả hai web starter vào một app chỉ để có thể ghi hai bộ controller. Cách đó làm kết quả auto-configuration phụ thuộc classpath và khiến việc xác định stack đang chạy khó hơn.

## 3. Chốt một HTTP contract dùng chung

Trước khi viết controller, mô tả hợp đồng mà cả hai adapter phải tuân thủ. Với Catalog API:

| Thành phần | Hợp đồng |
|---|---|
| Base path | /api/products |
| Lấy theo ID | GET /api/products/{id} |
| Tìm kiếm | GET /api/products?keyword=... |
| Tạo mới | POST /api/products |
| ID | UUID |
| Tên sản phẩm | Chuỗi không rỗng, tối đa 120 ký tự |
| Giá | Số thập phân, không âm |
| Tạo thành công | 201 Created và ProductResponse |
| Không tìm thấy | 404 và ApiError |
| Validation thất bại | 400 và ApiError |
| Content type | application/json |

Contract nên xác định rõ:

- OperationId ổn định, không phụ thuộc tên method nội bộ.
- Schema và tên component được đặt rõ ràng.
- Required field, nullable, enum và format thống nhất.
- Response code và response body cho từng tình huống.
- Error format thống nhất, ví dụ RFC 9457 Problem Details hoặc một ApiError schema riêng.
- Security scheme và quyền truy cập tương ứng.
- Quy tắc pagination, sorting và filtering.

OpenAPI mô tả giao tiếp HTTP mà client nhìn thấy. Nó không mô tả thread model, event loop, backpressure hoặc việc service bên trong dùng blocking hay reactive repository.

## 4. Chia sẻ DTO và validation

Đặt request/response DTO trong module contract để cả hai ứng dụng dùng cùng một định nghĩa:

~~~java
package example.catalog.contract;

import java.math.BigDecimal;
import java.util.UUID;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CreateProductRequest")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Tên sản phẩm hiển thị cho người mua.",
        example = "Mechanical Keyboard"
    )
    String name,

    @DecimalMin("0.00")
    @Schema(
        description = "Giá bán theo đơn vị tiền tệ của cửa hàng.",
        example = "1250000.00"
    )
    BigDecimal price
) {}

@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(example = "e8b2f4a0-13b7-4c65-9c3f-1c7e6d4a0001")
    UUID id,

    @Schema(example = "Mechanical Keyboard")
    String name,

    @Schema(example = "1250000.00")
    BigDecimal price
) {}
~~~

Trong code thật, mỗi public type Java nằm trong file riêng. Đoạn trên gom hai record để minh họa DTO dùng chung.

Validation annotation vừa có thể được springdoc dùng để suy ra constraint trong schema, vừa được runtime validation thực thi khi controller bật @Valid. Tuy vậy, hai việc này phải được kiểm tra riêng:

- OpenAPI có thể hiển thị maxLength, minimum và required đúng.
- Runtime MVC/WebFlux phải thực sự trả 400 khi request vi phạm constraint.
- JSON serialization của hai stack phải giữ cùng tên field, number format, null handling và date/time format.

Nếu module contract dùng @Schema, nó cần dependency swagger-annotations tương thích. Giữ dependency này trong API contract module; không kéo toàn bộ springdoc runtime vào domain/application core.

## 5. Tách application use case khỏi web adapter

Controller không nên tự chứa business rule. Hai ứng dụng gọi cùng một application service hoặc hai implementation tuân thủ cùng port.

Một port đơn giản:

~~~java
public interface CatalogUseCases {
    ProductResponse getProduct(UUID id);
    List<ProductResponse> searchProducts(String keyword);
    ProductResponse createProduct(CreateProductRequest request);
}
~~~

Nếu service dùng JDBC hoặc thư viện blocking, MVC có thể gọi trực tiếp. WebFlux adapter không được gọi blocking database/client trên event-loop thread. Có thể tạm offload lời gọi blocking:

~~~java
Mono.fromCallable(() -> catalogUseCases.getProduct(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là cách chuyển tiếp khi dùng application service blocking. Nó không biến persistence layer thành non-blocking. Với WebFlux thực sự reactive, thiết kế port và implementation trả Mono/Flux, dùng reactive driver và giữ luồng non-blocking xuyên suốt.

Điều quan trọng với tài liệu API là publisher wrapper không phải một phần của JSON contract. Client nhận ProductResponse hoặc danh sách ProductResponse, không nhận object Mono hay Flux.

## 6. Cài springdoc starter phù hợp

Chọn starter theo web stack và nhu cầu xuất tài liệu:

| Nhu cầu | MVC | WebFlux |
|---|---|---|
| Chỉ xuất OpenAPI JSON/YAML | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| Có Swagger UI | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |
| Có Scalar UI | springdoc-openapi-starter-webmvc-scalar | springdoc-openapi-starter-webflux-scalar |

Ví dụ Maven cho Spring Boot 3.5.x và springdoc 2.10.0:

~~~xml
<!-- catalog-mvc-app -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

~~~xml
<!-- catalog-webflux-app -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu chỉ cần JSON/YAML để CI lấy tài liệu, dùng starter api thay vì ui. Điều này tránh đóng gói Swagger UI vào runtime không cần giao diện.

Với Spring Boot 4.x, dùng springdoc 3.x và kiểm tra compatibility matrix của release. Tài liệu hiện hành minh họa springdoc 3.2.0 cho Boot 4; ứng dụng Boot 3 tiếp tục dùng nhánh springdoc 2.x. Không dùng chung một version springdoc nếu hai ứng dụng có Spring Boot major khác nhau mà chưa xác nhận ma trận tương thích.

Mỗi app chỉ khai báo starter phù hợp với web stack của chính nó.

## 7. Cấu hình OpenAPI metadata giống nhau

Hai app nên công bố cùng title, description, version, tag và security scheme. Tách server URL theo môi trường hoặc cấu hình riêng cho từng app.

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Catalog API",
        version = "v1",
        description = "API quản lý và tra cứu sản phẩm."
    )
)
public class OpenApiConfiguration {
}
~~~

Nếu API có nhiều miền hoặc audience, dùng group với tên nhất quán:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/products/**")
            .build();
    }
}
~~~

Đặt cấu hình tương đương trong cả MVC app và WebFlux app. Khi group có tên catalog, document thường được phục vụ tại:

~~~text
/v3/api-docs/catalog
/v3/api-docs.yaml/catalog
~~~

Đường dẫn group và YAML endpoint có thể phụ thuộc cấu hình springdoc. Kiểm tra URL thực tế của từng app sau khi khởi động.

Nếu cùng một class OpenApiGroupConfiguration được đóng gói trong module dùng chung, cần chắc chắn cả hai app đều scan bean đó. Nếu cấu hình riêng từng app, giữ nội dung và group name đồng bộ.

## 8. Viết MVC controller cho Catalog

MVC controller dùng DTO và application service chung. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Tra cứu và quản lý sản phẩm.")
public class ProductMvcController {

    private final CatalogUseCases catalog;

    public ProductMvcController(CatalogUseCases catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ProductResponse getById(@PathVariable UUID id) {
        return catalog.getProduct(id);
    }

    @GetMapping
    @Operation(
        operationId = "searchProducts",
        summary = "Tìm sản phẩm theo từ khóa"
    )
    public List<ProductResponse> search(
            @RequestParam(required = false) String keyword) {
        return catalog.searchProducts(keyword);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Tạo sản phẩm thành công",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Dữ liệu request không hợp lệ",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ProductResponse create(
            @Valid @RequestBody CreateProductRequest request) {
        return catalog.createProduct(request);
    }
}
~~~

Đặt operationId tường minh để tên operation trong OpenAPI không đổi khi refactor tên method Java. Các response quan trọng nên được mô tả rõ bằng @ApiResponse thay vì chỉ dựa vào return type.

## 9. Viết WebFlux controller cho cùng contract

WebFlux controller dùng cùng path, HTTP method, DTO, validation và operationId. Ví dụ sau giả định application service blocking và minh họa cách offload nó khỏi event loop:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Tra cứu và quản lý sản phẩm.")
public class ProductWebFluxController {

    private final CatalogUseCases catalog;

    public ProductWebFluxController(CatalogUseCases catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public Mono<ProductResponse> getById(@PathVariable UUID id) {
        return Mono.fromCallable(() -> catalog.getProduct(id))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping
    @Operation(
        operationId = "searchProducts",
        summary = "Tìm sản phẩm theo từ khóa"
    )
    public Mono<List<ProductResponse>> search(
            @RequestParam(required = false) String keyword) {
        return Mono.fromCallable(() -> catalog.searchProducts(keyword))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Tạo sản phẩm thành công",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Dữ liệu request không hợp lệ",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public Mono<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        return Mono.fromCallable(() -> catalog.createProduct(request))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đoạn code cần các import Reactor như Mono và Schedulers, cùng các annotation Spring và Swagger giống controller MVC. Tùy version Spring Framework, kiểu reactive ở tham số @RequestBody được WebFlux hỗ trợ trực tiếp.

Nếu application service đã reactive, không bọc lại bằng fromCallable/boundedElastic. Gọi Mono/Flux từ port trực tiếp để giữ non-blocking. Không đưa blocking JDBC hoặc RestTemplate lên event-loop thread.

Hai controller không cần có cùng chữ ký method. Điều cần giống nhau là HTTP contract và JSON payload mà client quan sát.

## 10. Kiểm tra schema sinh ra từ reactive return type

OpenAPI mô tả giá trị response được serialize, không mô tả wrapper Reactor:

| Chữ ký Java | Schema client cần thấy |
|---|---|
| MVC: ProductResponse | ProductResponse object |
| WebFlux: Mono<ProductResponse> | ProductResponse object |
| MVC: List<ProductResponse> | Array of ProductResponse |
| WebFlux: Mono<List<ProductResponse>> | Array of ProductResponse |

Nếu document xuất hiện schema Mono hoặc Flux như một object thông thường, cần kiểm tra dependency, generic type resolution và springdoc version. Không sửa schema bằng cách ẩn wrapper trước khi hiểu nguyên nhân.

Đặt @Schema(name = "ProductResponse") và @Schema(name = "CreateProductRequest") ở DTO nếu cần tên component ổn định. Kiểm tra components.schemas trong hai document sau khi export.

## 11. Mô tả error response giống nhau

MVC và WebFlux có cơ chế xử lý exception khác nhau ở tầng runtime, nhưng consumer nên nhận cùng error contract. Có thể dùng DTO chung:

~~~java
@Schema(name = "ApiError")
public record ApiError(
    String code,
    String message,
    String traceId
) {}
~~~

Hai app ánh xạ exception nghiệp vụ sang cùng status và ApiError. Có thể dùng @RestControllerAdvice cho annotated controllers, nhưng hãy kiểm thử exception mapping riêng trên mỗi stack. WebFlux functional handlers có thể cần WebExceptionHandler hoặc xử lý lỗi trong RouterFunction.

Mô tả response ở operation:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Dữ liệu request không hợp lệ",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Không chỉ khai báo response 400 trong OpenAPI. Gửi request sai thực tế đến cả hai app và xác minh status, content type, field và message theo chính sách của API.

## 12. Validation và binding phải được kiểm tra trên cả hai stack

Dùng cùng DTO giúp chia sẻ constraint, nhưng quá trình binding và validation vẫn đi qua hạ tầng khác:

- MVC dùng HttpMessageConverter và MVC validation integration.
- WebFlux dùng HttpMessageReader/HttpMessageWriter và reactive validation integration.
- Custom Jackson configuration có thể được áp dụng qua cấu hình converter hoặc codec khác nhau.
- Constraint ở method parameter có thể phụ thuộc @Validated và method validation configuration.

Test ít nhất:

1. Thiếu field bắt buộc.
2. Chuỗi vượt maxLength.
3. Giá trị số âm.
4. UUID sai định dạng.
5. JSON malformed.
6. Content-Type không hỗ trợ.
7. Request body rỗng.

Hai stack cần trả cùng status code và error schema theo contract. Nếu một bên trả 400 còn bên kia trả 500, đó là contract drift dù OpenAPI document của chúng giống nhau.

## 13. Response streaming là trường hợp cần tài liệu riêng

Với collection thông thường, dùng application/json và một schema array để giữ cùng hình dạng response. Không chọn Flux chỉ vì ứng dụng dùng WebFlux.

Nếu API thực sự stream:

- WebFlux có thể ghi các phần tử từ Flux theo reactive streaming.
- Spring MVC cũng hỗ trợ reactive return types và streaming response, nhưng cách buffer/flush phụ thuộc media type và return value adapter.
- text/event-stream thường dùng cho Server-Sent Events.
- application/x-ndjson hoặc media type streaming khác cần được client và server thống nhất.

OpenAPI cần khai báo đúng produces, response content type và schema của từng event/item. Tài liệu không tự mô tả backpressure, tốc độ phát, retry, reconnect hoặc giới hạn buffer.

Không mô tả một endpoint stream là JSON array thông thường nếu client thực tế phải đọc từng event. Test với client thật và kiểm tra Content-Type, framing, flush behavior và xử lý lỗi giữa stream.

## 14. WebFlux functional endpoints

WebFlux có thể khai báo route bằng RouterFunction thay vì annotated controller. Khi đó không có method @GetMapping để springdoc tự đọc metadata theo cách annotated controller.

Springdoc hỗ trợ mô tả functional route qua @RouterOperation, @RouterOperations và OpenApiCustomizer. Khi dùng cách này, khai báo rõ:

- Path và HTTP method.
- OperationId, summary và description.
- Request parameter hoặc request body.
- Response code, media type và schema.
- Security requirement.

Ví dụ route:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/{id}", handler::getById)
        .POST("/api/products", handler::create)
        .build();
}
~~~

Route trên mô tả runtime routing. Để có OpenAPI operation đầy đủ, bổ sung metadata bằng annotation/configuration mà springdoc hỗ trợ cho phiên bản đang dùng. Đừng giả định chỉ có RouterFunction là đủ để sinh request/response schema chính xác.

Nếu miền API có cả annotated controller và functional route, dùng cùng naming convention, schema và operationId. Kiểm tra không có path/method bị khai báo hai lần.

## 15. Chia OpenAPI group giống nhau

Hai ứng dụng nên dùng cùng group name và path filter:

~~~java
@Bean
GroupedOpenApi productsApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**")
        .build();
}
~~~

Nếu app MVC dùng group catalog còn app WebFlux dùng group products, pipeline và portal sẽ phải xử lý hai quy ước khác nhau. Giữ group name ổn định giúp script export, dashboard và consumer tìm tài liệu theo cùng URL pattern.

Nếu mỗi app có API nội bộ khác nhau, tạo group riêng và loại chúng khỏi public contract. Không để một app vô tình công bố actuator, admin hoặc debug endpoint chỉ vì scan toàn bộ application.

## 16. Bảo đảm server URL và metadata nhất quán

Hai ứng dụng thường chạy trên host hoặc port khác nhau:

~~~text
MVC:     http://localhost:8081/v3/api-docs/catalog
WebFlux: http://localhost:8082/v3/api-docs/catalog
~~~

Đây là URL tải tài liệu. Field servers trong OpenAPI document là base URL mà client dùng gọi API. Nếu hai app phục vụ cùng một API contract qua hai host khác nhau, server URL có thể khác nhau mà path/schema vẫn giống.

Khi so sánh contract:

- Giữ nguyên document gốc để kiểm tra deployment URL.
- So sánh riêng servers để xác minh từng môi trường.
- Có thể tạo bản normalized chỉ để semantic diff, bỏ servers nếu host khác nhau là chủ đích.
- Không bỏ paths, security, schema hoặc response chỉ để diff ít dòng hơn.
- Giữ info.title, info.version, tags và operationId thống nhất.

Nếu hai app có base path khác nhau, cần xác định đó có phải contract khác nhau hay không. Không tự xóa prefix trong bước normalize nếu consumer phải gọi path khác.

## 17. Sinh OpenAPI document từ hai ứng dụng

Khởi chạy MVC và WebFlux trên port riêng với cùng API group:

~~~bash
# MVC app
./gradlew :catalog-mvc-app:bootRun --args='--server.port=8081'

# WebFlux app, chạy trong terminal/job riêng
./gradlew :catalog-webflux-app:bootRun --args='--server.port=8082'
~~~

Tải hai document:

~~~bash
mkdir -p build/openapi

curl -fsS http://localhost:8081/v3/api-docs/catalog \
  -o build/openapi/catalog-mvc.json

curl -fsS http://localhost:8082/v3/api-docs/catalog \
  -o build/openapi/catalog-webflux.json
~~~

Nếu dùng group hoặc API docs path tùy chỉnh, thay URL tương ứng. Kiểm tra file tồn tại, không rỗng và parse được:

~~~bash
test -s build/openapi/catalog-mvc.json
test -s build/openapi/catalog-webflux.json

jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/catalog-mvc.json

jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/catalog-webflux.json
~~~

## 18. So sánh hai OpenAPI document

Trước tiên so sánh thông tin cấp cao:

~~~bash
jq -r '.info.title, .info.version, (.paths | keys[])' \
  build/openapi/catalog-mvc.json

jq -r '.info.title, .info.version, (.paths | keys[])' \
  build/openapi/catalog-webflux.json
~~~

Kiểm tra các thành phần quan trọng:

- Cùng OpenAPI version và info.version.
- Cùng path và HTTP method.
- Cùng operationId.
- Cùng request parameter, required flag và schema.
- Cùng request body content type và schema.
- Cùng response code, media type và schema.
- Cùng security scheme và operation-level security.
- Cùng component schema name, property, enum và validation constraint.

Nếu chỉ khác server URL, tạo bản phục vụ so sánh:

~~~bash
jq 'del(.servers)' build/openapi/catalog-mvc.json \
  > build/openapi/catalog-mvc-normalized.json

jq 'del(.servers)' build/openapi/catalog-webflux.json \
  > build/openapi/catalog-webflux-normalized.json
~~~

Giữ lại hai file gốc. Bản normalized chỉ dùng để so sánh phần contract không phụ thuộc host:

~~~bash
oasdiff diff \
  build/openapi/catalog-mvc-normalized.json \
  build/openapi/catalog-webflux-normalized.json
~~~

Nếu cần kiểm tra breaking change so với baseline đã được phê duyệt:

~~~bash
oasdiff breaking \
  api/openapi/catalog-baseline.yaml \
  build/openapi/catalog-mvc-normalized.json

oasdiff breaking \
  api/openapi/catalog-baseline.yaml \
  build/openapi/catalog-webflux-normalized.json
~~~

Diff rỗng hoặc không có breaking change là tín hiệu tốt, nhưng không chứng minh runtime behavior giống nhau. Cần chạy contract tests trên cả hai app.

## 19. Dùng cùng bộ runtime contract test

Tách test case khỏi web stack. Mỗi test case định nghĩa:

- HTTP method và path.
- Header và query parameter.
- Request body.
- Expected status.
- Expected content type.
- JSON assertions hoặc schema.
- Security requirement.

Sau đó chạy cùng test data với base URL MVC và WebFlux.

Ví dụ bảng test:

| Test | Request | Kết quả mong đợi |
|---|---|---|
| Get existing product | GET /api/products/{id} | 200, ProductResponse |
| Get missing product | GET /api/products/{unknown} | 404, ApiError |
| Search products | GET /api/products?keyword=keyboard | 200, JSON array |
| Create product | POST với request hợp lệ | 201, ProductResponse |
| Missing name | POST thiếu name | 400, ApiError |
| Invalid UUID | GET với UUID sai | 400, error contract |
| Unsupported media type | POST với content type không hỗ trợ | 415 |
| Unauthorized | Gọi operation có security khi thiếu token | 401 |
| Forbidden | Token không đủ quyền | 403 |

MVC thường được kiểm tra bằng MockMvc hoặc HTTP client thật. WebFlux có thể dùng WebTestClient. Có thể dùng cùng fixture JSON và cùng assertion layer, chỉ thay test client hoặc base URL.

Đừng chỉ test response body. Hãy so sánh status code, Content-Type, header Location/ETag, pagination metadata, error structure và serialization.

## 20. Kiểm tra security parity

Nếu hai app cùng cung cấp public API, chúng phải có cùng authentication/authorization contract:

- Cùng security scheme trong OpenAPI.
- Cùng scope/role cần thiết cho operation.
- Cùng cách trả 401 và 403.
- Cùng CORS policy nếu consumer cross-origin.
- Không để docs group của một app công bố endpoint nội bộ.

Runtime security configuration có thể khác implementation: MVC dùng servlet SecurityFilterChain; WebFlux dùng reactive security chain và WebFilter. Đừng copy nguyên cấu hình MVC sang WebFlux.

OpenAPI security scheme mô tả credential client cần gửi. Nó không thay thế Spring Security runtime. Chạy test không token, token hợp lệ, token hết hạn và token thiếu scope trên cả hai app.

## 21. Serialization parity giữa converter và codec

MVC dùng HttpMessageConverter; WebFlux dùng HttpMessageReader/HttpMessageWriter. DTO giống nhau chưa chắc JSON giống nhau nếu hai app cấu hình serialization khác:

- Property naming strategy.
- Null inclusion.
- Enum serialization.
- Date/time format và timezone.
- BigDecimal scale và number serialization.
- Custom serializer/deserializer.
- Polymorphic type metadata.
- Jackson module được đăng ký.

Đặt serialization policy trong module cấu hình dùng chung khi phù hợp, nhưng vẫn xác minh effective converter/codec của mỗi app. Đặc biệt, nếu custom MVC HttpMessageConverter hoặc WebFlux Codec, kiểm tra springdoc và runtime dùng cùng kiểu dữ liệu.

## 22. Đồng bộ exception và response documentation

Hai app cần cùng ánh xạ lỗi nghiệp vụ:

| Lỗi | HTTP status | Response |
|---|---|---|
| Không tìm thấy sản phẩm | 404 | ApiError hoặc ProblemDetail |
| Request validation thất bại | 400 | ApiError hoặc ProblemDetail |
| Thiếu authentication | 401 | Security error |
| Không đủ quyền | 403 | Security error |
| Content-Type không hỗ trợ | 415 | ApiError hoặc ProblemDetail |
| Lỗi không dự kiến | 500 | Error response không tiết lộ stack trace |

Nếu một app dùng @RestControllerAdvice và app kia dùng WebExceptionHandler, cả hai vẫn có thể tạo cùng body. Điều cần kiểm tra là HTTP contract, không phải class xử lý exception có cùng tên.

Khai báo các response code trong @ApiResponses hoặc OpenApiCustomizer để OpenAPI không chỉ mô tả 200. Tránh công bố stack trace hoặc exception message nội bộ trong production.

## 23. Pipeline CI cho cả hai stack

CI nên build và export độc lập, sau đó so sánh:

~~~yaml
steps:
  - name: Test MVC
    run: ./gradlew :catalog-mvc-app:test

  - name: Test WebFlux
    run: ./gradlew :catalog-webflux-app:test

  - name: Export MVC OpenAPI
    run: ./gradlew :catalog-mvc-app:generateOpenApiDocs

  - name: Export WebFlux OpenAPI
    run: ./gradlew :catalog-webflux-app:generateOpenApiDocs

  - name: Compare contracts
    run: ./scripts/compare-catalog-openapi.sh
~~~

Tên task và cấu hình plugin phải khớp với Gradle plugin thực tế trong từng module. Mỗi app cần dùng đúng springdoc starter, port, profile và API docs URL. Nếu task tự khởi động app, không để hai task tranh cùng port.

CI cần fail hoặc yêu cầu review khi:

- Một path/method bị thiếu ở một stack.
- operationId thay đổi ngoài dự kiến.
- Request/response schema khác nhau.
- Security requirement khác nhau.
- Một stack xuất endpoint nội bộ ngoài group.
- Runtime contract test cho cùng fixture trả kết quả khác.

Lưu hai document gốc, normalized diff và test report thành artifact gắn với cùng commit.

## 24. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| App dự kiến WebFlux nhưng đang chạy MVC | Có cả hai web starter và Boot chọn MVC | Tách deployable hoặc chọn rõ application type |
| MVC có docs nhưng WebFlux không có | Dùng nhầm webmvc starter trong WebFlux app | Đổi sang webflux-api hoặc webflux-ui |
| Hai document có operationId khác | Để springdoc tự sinh từ tên method | Đặt operationId tường minh |
| WebFlux document lộ Mono/Flux schema | Generic type resolution hoặc dependency không đúng | Kiểm tra starter, return type và schema component |
| DTO giống nhưng JSON khác | Converter/codec hoặc Jackson config khác | So sánh response thực tế và thống nhất serialization |
| WebFlux chậm hoặc nghẽn event loop | Gọi blocking service trên event loop | Dùng reactive I/O hoặc offload blocking work |
| MVC trả list nhưng WebFlux stream | Khác media type/Flux semantics | Chốt contract collection hoặc streaming rõ ràng |
| Functional route không xuất hiện trong OpenAPI | RouterFunction thiếu metadata | Dùng @RouterOperation(s) hoặc OpenApiCustomizer |
| Hai docs group có tập path khác | pathsToMatch/packagesToScan không đồng bộ | Dùng cùng group name và filter |
| Security scheme giống nhưng hành vi khác | Runtime security chain khác | Test MVC servlet security và WebFlux reactive security |
| Error body khác nhau | Exception mapping riêng chưa đồng bộ | Dùng cùng error DTO và contract tests |
| Diff chỉ khác host | servers khác theo deployment | So sánh riêng servers và normalize cho contract diff |

## 25. Quy trình thực hành hoàn chỉnh

1. Viết contract cho miền Catalog trước khi chọn web stack.
2. Tạo module DTO, validation và schema dùng chung.
3. Tạo application service hoặc port không phụ thuộc MVC/WebFlux.
4. Tạo MVC app với springdoc WebMVC starter.
5. Tạo WebFlux app với springdoc WebFlux starter.
6. Đặt cùng path, method, operationId, tag, response và security metadata.
7. Cấu hình cùng OpenAPI group.
8. Chạy từng app riêng và tải JSON/YAML.
9. So sánh document và kiểm tra schema.
10. Chạy cùng contract fixtures trên cả hai runtime.
11. Kiểm tra validation, serialization, error, security và streaming.
12. Lưu baseline chung và đưa so sánh vào CI.

Sau khi thay đổi DTO hoặc controller, chạy lại cả hai bộ test. Không cập nhật baseline chỉ vì một stack sinh document khác; trước tiên xác định thay đổi có chủ đích hay là contract drift.

## 26. Checklist trước khi công bố

- [ ] MVC và WebFlux là hai deployable có web stack được xác định rõ.
- [ ] Không vô tình thêm cả hai web starter vào một app rồi giả định Boot chạy song song hai stack.
- [ ] Hai app dùng chung DTO, validation rule và application contract.
- [ ] Mỗi app dùng đúng springdoc starter.
- [ ] springdoc version tương thích với Spring Boot version của từng app.
- [ ] OpenAPI info, group name, tags và operationId thống nhất.
- [ ] Path, method, parameter, request body và response schema giống nhau.
- [ ] Security scheme và runtime authorization parity đã được test.
- [ ] Error status và error body giống nhau.
- [ ] Converter và codec serialize cùng DTO nhất quán.
- [ ] WebFlux không chạy blocking work trên event-loop.
- [ ] Streaming endpoint khai báo đúng media type và behavior.
- [ ] Functional routes có metadata OpenAPI tường minh.
- [ ] Hai OpenAPI document được validate và semantic diff.
- [ ] Runtime contract tests chạy trên cả MVC và WebFlux.
- [ ] Baseline và artifact gắn với cùng commit.

## 27. Tài liệu tham khảo chính thức

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): nhánh springdoc theo Spring Boot.
- [springdoc-openapi Current Documentation](https://springdoc.org/): starter và cấu hình cho nhánh Boot 4.
- [springdoc-openapi Modules](https://springdoc.org/v2/modules.html): starter WebMVC/WebFlux, API-only và UI cho Spring Boot 3.
- [springdoc-openapi FAQ](https://springdoc.org/v2/faq.html): GroupedOpenApi, path/package filters và các lưu ý khi sinh tài liệu.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/reactive.html): WebFlux, annotated controllers và hành vi khi cùng có MVC/WebFlux starter.
- [Spring Framework – WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): annotation controller và path mapping.
- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Mono/Flux, streaming và response encoding.
- [Spring Framework – MVC Return Values](https://docs.spring.io/spring-framework/reference/7.1/web/webmvc/mvc-controller/ann-methods/return-types.html): reactive return types và HttpMessageConverter.

## Kết luận

Để tài liệu hóa cùng một miền API trên MVC và WebFlux, hãy bắt đầu từ một HTTP contract chung rồi triển khai hai web adapter độc lập. Chia sẻ DTO, validation và use case; chọn đúng springdoc WebMVC hoặc WebFlux starter cho từng app; giữ ổn định path, operationId, schema, security và error response. Sau đó sinh hai OpenAPI document, so sánh chúng và chạy cùng bộ contract tests trên cả hai runtime. OpenAPI cho biết client nhìn thấy contract nào, còn kiểm thử HTTP mới xác nhận hai implementation thực sự tuân thủ contract đó.
