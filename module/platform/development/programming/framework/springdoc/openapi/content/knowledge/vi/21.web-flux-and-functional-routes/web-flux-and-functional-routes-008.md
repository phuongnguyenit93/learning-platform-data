# @RouterOperations cho nhiều route trong một bean

Spring WebFlux hỗ trợ khai báo endpoint theo hai phong cách chính: annotation trên controller và functional routing bằng **RouterFunction**. Với functional routing, một bean có thể gom nhiều route GET, POST, PUT hoặc DELETE vào cùng một bộ định tuyến. Vì các route được tạo bằng Java DSL thay vì @GetMapping hay @PostMapping, springdoc-openapi cần metadata tường minh để mô tả từng operation trong OpenAPI.

Annotation **@RouterOperation** mô tả một route; **@RouterOperations** gom nhiều mô tả route trên cùng một bean method trả về RouterFunction. Mỗi phần tử cần khớp với route thực tế về path và HTTP method, đồng thời có thể trỏ tới handler method để springdoc lấy thêm thông tin.

Bài này trình bày cách ánh xạ nhiều route trong một bean thành nhiều operation OpenAPI, cách khai báo request/response schema, các điểm dễ lệch giữa route runtime và tài liệu, cùng cách kiểm tra kết quả tại endpoint API docs.

## 1. Functional routing khác gì annotated controller?

Với annotated controller, Spring nhận biết route từ annotation trên method:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> list() {
        // ...
        return List.of();
    }

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable UUID id) {
        // ...
        return null;
    }
}
~~~

springdoc có thể đọc các mapping như @GetMapping và @PathVariable để tạo operation.

Với functional routing, route được tạo bằng RouterFunctions:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::findById)
        .POST("/api/products", handler::create)
        .build();
}
~~~

Ở đây không có @GetMapping hoặc @PostMapping trên handler để mô tả route. Handler method chỉ nhận ServerRequest và trả về Mono<ServerResponse>. Vì vậy, cần cung cấp metadata OpenAPI để công cụ biết:

- Route dùng path nào?
- HTTP method nào được hỗ trợ?
- Request body hoặc parameter có hình dạng gì?
- Response có status code và schema nào?
- Operation có summary, description, tag hoặc security requirement nào?

## 2. @RouterOperation mô tả một route

Annotation **@RouterOperation** liên kết một route functional với một operation OpenAPI. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| path | Path đầy đủ của route được công bố |
| method | HTTP method như GET, POST, PUT, PATCH hoặc DELETE |
| beanClass | Class chứa handler method được tham chiếu |
| beanMethod | Tên method xử lý request |
| consumes | Media type mà operation nhận, ví dụ application/json |
| produces | Media type mà operation trả về, ví dụ application/json |
| operation | Annotation @Operation chứa metadata OpenAPI chi tiết |

Ví dụ một route:

~~~java
@Bean
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.GET,
    beanClass = ProductHandler.class,
    beanMethod = "list",
    produces = {MediaType.APPLICATION_JSON_VALUE},
    operation = @Operation(
        operationId = "listProducts",
        summary = "Liệt kê sản phẩm",
        description = "Trả về danh sách sản phẩm hiện có."
    )
)
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .build();
}
~~~

Trong ví dụ:

- path và method xác định operation được mô tả.
- beanClass và beanMethod chỉ tới handler xử lý route.
- produces mô tả response media type.
- operation cung cấp operationId, summary và description.

Path trong annotation phải là path mà client gọi được sau khi áp dụng các route predicate hoặc prefix lồng nhau. Không dùng tên method của bean RouterFunction thay cho beanMethod nếu muốn springdoc đọc metadata từ handler class.

## 3. Dùng @RouterOperations cho nhiều route trong một bean

Khi một RouterFunction bean chứa nhiều route, đặt **@RouterOperations** trên bean method và khai báo một **@RouterOperation** cho mỗi operation:

Các import chính trong ví dụ:

~~~java
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "list",
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "listProducts",
            summary = "Liệt kê sản phẩm"
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findById",
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "getProductById",
            summary = "Lấy sản phẩm theo ID"
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        beanClass = ProductHandler.class,
        beanMethod = "create",
        consumes = {MediaType.APPLICATION_JSON_VALUE},
        produces = {MediaType.APPLICATION_JSON_VALUE},
        operation = @Operation(
            operationId = "createProduct",
            summary = "Tạo sản phẩm"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::findById)
        .POST(
            "/api/products",
            RequestPredicates.contentType(MediaType.APPLICATION_JSON),
            handler::create
        )
        .build();
}
~~~

Một bean RouterFunction trên có ba route runtime:

| Runtime route | Handler | OpenAPI operationId |
|---|---|---|
| GET /api/products | list | listProducts |
| GET /api/products/{id} | findById | getProductById |
| POST /api/products | create | createProduct |

Hai operation GET và POST cùng path /api/products vẫn là hai operation khác nhau vì HTTP method khác nhau. Mỗi route cần một phần tử @RouterOperation tương ứng trong @RouterOperations.

Không tạo một @RouterOperation chung cho cả ba route. Một operation OpenAPI chỉ đại diện cho một cặp path và HTTP method.

## 4. Handler class và beanMethod phải được tham chiếu đúng

Functional route thường tham chiếu method của một handler bean:

~~~java
@Component
public class ProductHandler {

    public Mono<ServerResponse> list(ServerRequest request) {
        // Đọc dữ liệu và trả danh sách sản phẩm
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        String id = request.pathVariable("id");
        // Tra cứu sản phẩm theo id
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        // Đọc request body và tạo sản phẩm
        return request.bodyToMono(CreateProductRequest.class)
            .flatMap(body -> ServerResponse
                .status(HttpStatus.CREATED)
                .build());
    }
}
~~~

Trong @RouterOperation:

- beanClass là ProductHandler.class.
- beanMethod là tên method list, findById hoặc create.

Method được tham chiếu phải tồn tại trên bean class mà springdoc có thể phân tích. Nếu đổi tên method trong handler, cần cập nhật beanMethod tương ứng.

### Một handler method có thể xử lý nhiều route không?

Về mặt Java, nhiều route có thể cùng trỏ tới một handler method. Nhưng nếu mỗi route có hợp đồng khác nhau, hãy cân nhắc dùng handler method riêng hoặc mô tả operation rõ ràng bằng metadata riêng cho từng route.

Ví dụ, hai path có thể cùng gọi một method:

~~~java
RouterFunctions.route()
    .GET("/api/products/featured", handler::findFeatured)
    .GET("/api/products/recommended", handler::findFeatured)
    .build();
~~~

OpenAPI vẫn cần hai path operation riêng nếu cả hai URL đều được công bố. Có thể dùng cùng beanClass và beanMethod, nhưng mỗi @RouterOperation cần path chính xác và operationId duy nhất.

## 5. Mô tả request body vì ServerRequest không bộc lộ DTO trực tiếp

Handler functional thường nhận một đối tượng **ServerRequest** thay vì nhận DTO làm tham số method:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProductRequest.class)
        .flatMap(product -> productService.create(product)
            .flatMap(saved -> ServerResponse
                .status(HttpStatus.CREATED)
                .bodyValue(saved)));
}
~~~

springdoc không thể chỉ nhìn kiểu ServerRequest để biết body thực tế là CreateProductRequest. Hãy khai báo request body trong **@Operation**:

~~~java
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.POST,
    beanClass = ProductHandler.class,
    beanMethod = "create",
    consumes = {MediaType.APPLICATION_JSON_VALUE},
    produces = {MediaType.APPLICATION_JSON_VALUE},
    operation = @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(
                    implementation = CreateProductRequest.class
                )
            )
        )
    )
)
~~~

DTO có thể khai báo schema và constraint:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(description = "Tên sản phẩm", example = "Keyboard")
    String name,

    @NotNull
    @Positive
    @Schema(description = "Giá sản phẩm", example = "1250000")
    BigDecimal price
) {}
~~~

Các annotation @Schema và Bean Validation mô tả cấu trúc và ràng buộc dữ liệu. Runtime validation vẫn cần được kích hoạt trong logic xử lý functional endpoint nếu ứng dụng muốn từ chối dữ liệu không hợp lệ; việc khai báo schema trong @RouterOperation không tự gọi Validator.

## 6. Mô tả path variable, query parameter và header

Handler nhận ServerRequest rồi tự đọc parameter:

~~~java
public Mono<ServerResponse> findById(ServerRequest request) {
    UUID id = UUID.fromString(request.pathVariable("id"));
    return productService.findById(id)
        .flatMap(product -> ServerResponse.ok().bodyValue(product));
}

public Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("keyword").orElse("");
    String locale = request.headers()
        .firstHeader("X-Locale");
    // ...
    return ServerResponse.ok().build();
}
~~~

Do parameter không xuất hiện thành tham số Java riêng trên method, hãy mô tả rõ trong **@Operation.parameters**:

~~~java
@Operation(
    operationId = "getProductById",
    summary = "Lấy sản phẩm theo ID",
    parameters = {
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "UUID của sản phẩm",
            schema = @Schema(type = "string", format = "uuid")
        )
    }
)
~~~

Với query parameter:

~~~java
@Parameter(
    name = "keyword",
    in = ParameterIn.QUERY,
    required = true,
    description = "Từ khóa tìm kiếm",
    schema = @Schema(type = "string", minLength = 1)
)
~~~

Với header:

~~~java
@Parameter(
    name = "X-Locale",
    in = ParameterIn.HEADER,
    required = false,
    description = "Ngôn ngữ phản hồi",
    schema = @Schema(type = "string", example = "vi")
)
~~~

Khai báo parameter ở operation tương ứng trong @RouterOperation. Path variable trong path phải có parameter path tương ứng và bắt buộc theo OpenAPI.

## 7. Mô tả response schema và status code

Functional handler thường trả **Mono<ServerResponse>**. Kiểu trả về này không cho biết cụ thể JSON body mà endpoint phát ra. Vì vậy, cần mô tả response bằng @ApiResponse:

~~~java
@Operation(
    operationId = "getProductById",
    summary = "Lấy sản phẩm theo ID",
    responses = {
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm"
        )
    }
)
~~~

Đối với danh sách, có thể dùng schema mảng:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
~~~

Đối với POST tạo mới, mô tả status code thực tế như 201 Created, response body và các lỗi validation có thể xảy ra. Không mặc định mọi operation đều trả 200 nếu handler đang trả 201, 204 hoặc 404.

## 8. Khai báo consumes và produces đồng bộ với route

Trong @RouterOperation:

- **consumes** mô tả media type của request body mà operation nhận.
- **produces** mô tả media type của response.

Ví dụ:

~~~java
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.POST,
    consumes = {MediaType.APPLICATION_JSON_VALUE},
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = ProductHandler.class,
    beanMethod = "create"
)
~~~

Metadata này phải khớp với route predicate và cách handler tạo response:

~~~java
RouterFunctions.route()
    .POST(
        "/api/products",
        RequestPredicates.contentType(MediaType.APPLICATION_JSON)
            .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)),
        handler::create
    )
    .build();
~~~

Nếu route chấp nhận XML nhưng OpenAPI chỉ khai báo application/json, client sẽ hiểu sai hợp đồng. Nếu handler trả text/plain mà produces khai báo application/json, tài liệu và runtime không đồng bộ.

## 9. Route lồng nhau và path hiệu lực

RouterFunction có thể được tổ chức bằng nested route:

~~~java
RouterFunctions.nest(
    RequestPredicates.path("/api"),
    RouterFunctions.route()
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::findById)
        .build()
);
~~~

Path hiệu lực mà client gọi là:

- /api/products
- /api/products/{id}

Khi mô tả bằng @RouterOperations, dùng path đầy đủ sau khi ghép prefix lồng nhau. Không chỉ ghi /products nếu endpoint thực tế được công bố dưới /api/products.

Với route dùng path predicate phức tạp, hãy kiểm tra path cuối cùng được sinh ra trong /v3/api-docs. Nếu một route được lồng nhiều cấp, ghi lại path hiệu lực rõ ràng để tránh thiếu prefix.

## 10. Một path có nhiều method và giới hạn của OpenAPI

Một path có thể chứa nhiều HTTP method:

~~~text
GET    /api/products
POST   /api/products
DELETE /api/products/{id}
~~~

Đây là các operation riêng. OpenAPI mô hình hóa một path item với một operation cho mỗi method. Do đó, mỗi cặp path/method cần một metadata operation riêng.

Ngược lại, nếu runtime có hai route cùng path và cùng method nhưng khác predicate phụ, OpenAPI không có cách biểu diễn hai operation độc lập cùng cặp path/method. Ví dụ hai GET /api/products chỉ khác header X-Client-Type sẽ không thể trở thành hai GET operation khác nhau dưới cùng một path item. Có thể mô tả điều kiện header trong cùng operation bằng parameter hoặc tách endpoint path nếu hợp đồng cần phân biệt rõ.

Không tạo operationId trùng nhau trong cùng tài liệu. Hãy đặt operationId ổn định và duy nhất, nhất là khi client generator dùng chúng để tạo tên method.

## 11. Kết hợp tag, security và response metadata

@Operation bên trong @RouterOperation hỗ trợ nhiều metadata OpenAPI quen thuộc:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm",
    description = "Tạo sản phẩm mới trong danh mục.",
    tags = {"Products"},
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = {
        @ApiResponse(responseCode = "201", description = "Đã tạo sản phẩm"),
        @ApiResponse(responseCode = "400", description = "Request không hợp lệ"),
        @ApiResponse(responseCode = "401", description = "Chưa xác thực")
    }
)
~~~

Nếu tài liệu có security scheme bearerAuth, requirement phải tham chiếu đúng tên scheme đã khai báo. Annotation này chỉ mô tả yêu cầu bảo mật trong OpenAPI; Spring Security vẫn phải xác thực request runtime.

Tag giúp nhóm operation bên trong tài liệu. GroupedOpenApi có thể tiếp tục lọc functional route theo path hoặc package, nhưng group không thay thế metadata operation của @RouterOperation.

## 12. Cấu hình dependency cho WebFlux

Ứng dụng dùng Spring WebFlux cần starter springdoc tương ứng với WebFlux, ví dụ trong Maven:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Giá trị 2.x.y chỉ là placeholder minh họa; thay bằng phiên bản springdoc 2.x tương thích với phiên bản Spring Boot của dự án. Quản lý version theo dependency catalog hoặc property tập trung thay vì rải số version ở nhiều module.

Không ghép starter WebMVC và WebFlux một cách tùy tiện trong cùng ứng dụng. Chọn starter phù hợp với stack web đang chạy để tránh xung đột auto-configuration.

## 13. Kiểm tra tài liệu được sinh ra

Sau khi ứng dụng khởi động, mở endpoint OpenAPI mặc định:

~~~text
http://localhost:8080/v3/api-docs
~~~

Tìm các path và method:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products"]'
~~~

Kết quả mong đợi có cả get và post:

~~~json
{
  "get": {
    "operationId": "listProducts",
    "summary": "Liệt kê sản phẩm"
  },
  "post": {
    "operationId": "createProduct",
    "summary": "Tạo sản phẩm"
  }
}
~~~

Kiểm tra path có biến:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].get'
~~~

Đối chiếu:

1. Tất cả route runtime cần công bố đều có path/method tương ứng.
2. Không có route nào bị khai báo nhầm path hoặc method.
3. operationId là duy nhất trong tài liệu.
4. Request body và parameters có schema đúng.
5. Response status code, media type và schema phản ánh handler.
6. Tag và security requirement tham chiếu đúng metadata đã khai báo.

Nếu dùng GroupedOpenApi, kiểm tra URL tài liệu của từng group thay vì chỉ kiểm tra /v3/api-docs.

## 14. Kiểm thử route runtime và OpenAPI riêng biệt

Kiểm thử functional route bằng WebTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductRoutesTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void productListRouteResponds() {
        webTestClient.get()
            .uri("/api/products")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void openApiContainsProductOperations() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/products'].get.operationId")
            .isEqualTo("listProducts")
            .jsonPath("$.paths['/api/products'].post.operationId")
            .isEqualTo("createProduct");
    }
}
~~~

Hai nhóm kiểm tra có mục tiêu khác nhau:

- Test runtime xác nhận RouterFunction thực sự xử lý request.
- Test OpenAPI xác nhận @RouterOperations tạo đúng metadata tài liệu.

Một test thành công không thay thế test còn lại. Route có thể chạy nhưng thiếu trong tài liệu; tài liệu cũng có thể mô tả route không tồn tại do annotation bị lỗi thời.

## 15. Lỗi thường gặp khi dùng @RouterOperations

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Route chạy nhưng không xuất hiện trong OpenAPI | Thiếu @RouterOperation hoặc @RouterOperations trên bean method | Khai báo metadata cho route |
| Operation có path sai | Annotation không dùng path hiệu lực sau nested route | Ghi path đầy đủ và kiểm tra /v3/api-docs |
| Operation trỏ sai handler | beanClass hoặc beanMethod không khớp | Kiểm tra class và tên method thực tế |
| Đổi tên handler làm tài liệu lỗi | beanMethod vẫn giữ tên cũ | Cập nhật annotation cùng refactor |
| Request body không có schema | Handler chỉ nhận ServerRequest | Khai báo requestBody và @Schema(implementation = ...) |
| Response hiện object chung hoặc rỗng | Handler trả Mono<ServerResponse> | Khai báo ApiResponse và schema tường minh |
| Path variable không được mô tả | ServerRequest.pathVariable không phải tham số Java riêng | Thêm @Parameter với in = PATH |
| Query parameter bị thiếu | Handler đọc queryParam từ ServerRequest | Khai báo @Parameter với in = QUERY |
| consumes/produces không đúng | Metadata không khớp route predicate hoặc response | Đồng bộ annotation, predicate và handler |
| Hai operation có operationId trùng | Sao chép annotation mà không đổi ID | Đặt operationId duy nhất |
| Hai route cùng path/method tạo tài liệu khó hiểu | OpenAPI chỉ có một operation cho mỗi cặp path/method | Hợp nhất điều kiện vào operation hoặc thiết kế path khác |
| GroupedOpenApi không chứa route | Filter path/package không khớp | Kiểm tra group filter và tài liệu của đúng group |

## 16. Quy trình thêm route mới vào một bean hiện có

Khi thêm route vào RouterFunction bean đang có nhiều operation:

1. Thêm route runtime bằng RouterFunctions.route hoặc builder tương ứng.
2. Xác định path hiệu lực, HTTP method, consumes và produces.
3. Xác định handler class và handler method thực tế.
4. Thêm một @RouterOperation mới vào @RouterOperations.
5. Khai báo operationId, summary, parameters, request body, responses, tags và security nếu cần.
6. Kiểm tra không trùng path/method ngoài chủ đích và operationId không trùng.
7. Gọi route thật bằng WebTestClient.
8. Kiểm tra /v3/api-docs hoặc tài liệu group để xác nhận operation xuất hiện đúng.

Hãy coi route predicate và annotation là hai biểu diễn của cùng hợp đồng. Mỗi lần thay đổi path, method hoặc payload, cần cập nhật cả hai và kiểm tra đầu ra.

## 17. Nguyên tắc bảo trì

- Đặt @RouterOperations ngay trên bean method tạo RouterFunction để metadata gần route runtime.
- Một @RouterOperation cho mỗi cặp path/method được công bố.
- Dùng beanClass và beanMethod trỏ tới handler method có thật.
- Ghi path đầy đủ sau khi ghép nested route prefix.
- Khai báo request body và response schema rõ ràng khi handler dùng ServerRequest/ServerResponse.
- Mô tả path/query/header parameter tường minh nếu handler tự đọc từ ServerRequest.
- Đồng bộ consumes và produces với route predicate cùng response thực tế.
- Dùng operationId duy nhất, ổn định.
- Kiểm tra cả route runtime lẫn OpenAPI JSON sau mỗi thay đổi.
- Không coi annotation tài liệu là cơ chế đăng ký route, validation hoặc authorization.

## Kết luận

**@RouterOperation** mô tả một route functional; **@RouterOperations** gom nhiều mô tả trên cùng bean method trả về RouterFunction. Mỗi phần tử cần chỉ đúng path, HTTP method và handler class/method, sau đó bổ sung @Operation để mô tả request, response, parameters, tags và security. Với handler nhận ServerRequest và trả Mono<ServerResponse>, schema thường cần được khai báo tường minh vì kiểu reactive tổng quát không cho biết payload cụ thể. Hãy giữ metadata khớp route predicate, kiểm tra path hiệu lực sau nested routing, rồi xác minh cả request runtime lẫn /v3/api-docs để tránh tài liệu và hành vi thực tế lệch nhau.
