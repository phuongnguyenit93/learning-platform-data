# Nhận diện route bằng path, HTTP method, consumes và produces

Trong Spring WebFlux, một functional endpoint được tạo từ các hàm định tuyến (router functions) và hàm xử lý request (handler functions). Router quyết định request nào được chuyển đến handler dựa trên đường dẫn, HTTP method và những điều kiện khác của request. Khi dùng springdoc-openapi, các điều kiện định tuyến này cần được phản ánh chính xác trong OpenAPI để người tích hợp biết endpoint nào tồn tại, gửi loại nội dung nào và có thể nhận loại nội dung nào.

Có bốn yếu tố cần phân biệt:

- **Path** xác định tài nguyên hoặc hành động được gọi.
- **HTTP method** xác định thao tác như GET, POST, PUT, PATCH hoặc DELETE.
- **Consumes** mô tả loại nội dung request mà endpoint chấp nhận, thường dựa trên header Content-Type.
- **Produces** mô tả loại nội dung response mà endpoint cung cấp, thường được chọn theo header Accept và được handler ghi vào response.

Trong functional routing, các yếu tố này thường được kết hợp thành RequestPredicate. Trong OpenAPI, chúng được biểu diễn thành path, operation, requestBody content và response content. Tài liệu phải mô tả đúng route thực thi; annotation OpenAPI chỉ bổ sung metadata và không tự tạo hoặc thay đổi route.

## 1. Route được nhận diện như thế nào?

Một HTTP request có nhiều thuộc tính. Router có thể kiểm tra một hoặc nhiều thuộc tính trước khi chọn handler:

| Điều kiện | Nguồn dữ liệu | Câu hỏi |
|---|---|---|
| Path | URI path | Request gọi tài nguyên nào? |
| HTTP method | GET, POST, PUT, PATCH, DELETE... | Client muốn thực hiện thao tác gì? |
| Consumes | Header Content-Type | Body được gửi lên có định dạng nào? |
| Produces | Header Accept | Client chấp nhận định dạng response nào? |
| Query parameter | Phần query của URI | Request có tham số lọc hoặc phân trang nào? |
| Header | HTTP request headers | Request có đáp ứng điều kiện header không? |

Ví dụ một request:

~~~http
POST /api/products HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "name": "Mechanical Keyboard",
  "price": 1250000
}
~~~

Router có thể nhận request này nếu path là /api/products, method là POST, Content-Type tương thích với application/json và Accept cho biết client chấp nhận application/json. Sau khi route khớp, handler đọc body, gọi nghiệp vụ và tạo response.

## 2. Path và HTTP method xác định operation

Path và method kết hợp để nhận diện một operation. Cùng một path có thể có nhiều operation:

| Path | Method | Ý nghĩa |
|---|---|---|
| /api/products | GET | Liệt kê sản phẩm |
| /api/products | POST | Tạo sản phẩm |
| /api/products/{id} | GET | Lấy chi tiết sản phẩm |
| /api/products/{id} | PUT | Thay thế thông tin sản phẩm |
| /api/products/{id} | DELETE | Xóa sản phẩm |

Trong OpenAPI, mỗi path là một Path Item và mỗi method là một Operation bên trong Path Item đó. Vì vậy, GET và POST cùng dùng /api/products sẽ được mô tả thành hai operation riêng.

Không nên tạo hai route có cùng path và method rồi chỉ khác handler mà không có điều kiện phân biệt rõ. Nếu route khác nhau theo media type, query parameter hoặc header, các điều kiện đó phải được mô tả và kiểm thử.

## 3. Phân biệt annotated controller và functional endpoint

Với annotated controller, Spring WebFlux thường nhận diện route từ annotation:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<ProductResponse> list() {
        return productService.findAll();
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ProductResponse> create(
            @RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

Các annotation @GetMapping, @PostMapping, consumes và produces vừa tham gia ánh xạ request của Spring, vừa là nguồn metadata để springdoc phân tích.

Functional endpoint khai báo route bằng Java DSL:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON)
                .and(accept(MediaType.APPLICATION_JSON)),
            handler::create
        )
        .build();
}
~~~

Ở đây route không được mô tả bằng @GetMapping hoặc @PostMapping. Springdoc cần metadata RouterOperation/RouterOperations để liên kết route với operation OpenAPI. Đây là điểm khác biệt quan trọng khi tài liệu hóa functional endpoint.

## 4. Tạo route bằng RequestPredicate

Spring WebFlux cung cấp các predicate dựng sẵn trong RequestPredicates. Một số hàm thường dùng:

| Predicate | Chức năng |
|---|---|
| GET(path) | Khớp path và HTTP GET |
| POST(path) | Khớp path và HTTP POST |
| PUT(path) | Khớp path và HTTP PUT |
| PATCH(path) | Khớp path và HTTP PATCH |
| DELETE(path) | Khớp path và HTTP DELETE |
| path(pattern) | Khớp path theo pattern |
| contentType(mediaTypes) | Kiểm tra Content-Type của request |
| accept(mediaTypes) | Kiểm tra Accept của request |
| headers(predicate) | Kiểm tra điều kiện trên request headers |
| queryParam(name, predicate) | Kiểm tra query parameter |

Các predicate có thể kết hợp bằng and, or và negate. Ví dụ:

~~~java
RequestPredicate jsonRequest =
    contentType(MediaType.APPLICATION_JSON)
        .and(accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        POST("/api/products").and(jsonRequest),
        handler::create
    );
~~~

Ví dụ trên chỉ chọn handler khi tất cả điều kiện trong predicate đều đúng. Nếu một điều kiện không khớp, RouterFunction có thể tiếp tục tìm route khác đã được kết hợp hoặc trả về trạng thái không tìm thấy route.

## 5. Nhận diện route theo path

Path có thể là đường dẫn cố định hoặc chứa biến:

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::list)
        .GET("/api/products/{id}", handler::get)
        .DELETE("/api/products/{id}", handler::delete)
        .build();
}
~~~

Handler đọc path variable từ ServerRequest:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return productService.findById(id)
        .flatMap(product -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Trong OpenAPI, biến path phải xuất hiện dưới dạng parameter có vị trí path và bắt buộc. springdoc có thể suy ra một số metadata từ cấu hình route, nhưng với functional endpoint nên khai báo rõ parameter trong @Operation để tài liệu có tên, mô tả, kiểu dữ liệu và tính required chính xác.

Ví dụ mô tả path parameter:

~~~java
@Operation(
    operationId = "getProduct",
    summary = "Lấy chi tiết sản phẩm",
    parameters = {
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "Mã định danh sản phẩm."
        )
    }
)
~~~

Tên parameter phải khớp với biến trong path, ví dụ {id}. Nếu path dùng {productId} nhưng tài liệu khai báo productID hoặc id, client generator có thể tạo chữ ký method không đúng với endpoint.

## 6. Nhận diện route theo HTTP method

HTTP method cho biết loại thao tác mà client yêu cầu. Khi khai báo functional route, nên dùng predicate cụ thể như GET, POST, PUT, PATCH và DELETE để tránh một handler vô tình nhận nhiều method.

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/{id}", handler::get)
        .PUT("/api/products/{id}", handler::replace)
        .PATCH("/api/products/{id}", handler::update)
        .DELETE("/api/products/{id}", handler::delete)
        .build();
}
~~~

Trong OpenAPI, từng method được mô tả riêng, kèm summary, request body, response và security requirement tương ứng. Không mô tả một route GET thành POST chỉ vì handler có thao tác ghi dữ liệu bên trong; method trong hợp đồng phải khớp method router thực sự chấp nhận.

Nếu API hỗ trợ HEAD hoặc OPTIONS, hãy kiểm tra route và hành vi runtime thực tế rồi mô tả theo nhu cầu. Không tự giả định mọi route GET đều được tài liệu hóa hoặc triển khai HEAD theo cùng cách.

## 7. Consumes là điều kiện của request body

Consumes mô tả loại media type mà endpoint chấp nhận từ client. Với HTTP, thông tin này thường nằm trong header Content-Type.

Ví dụ route chỉ nhận JSON:

~~~java
RouterFunction<ServerResponse> createRoute(ProductHandler handler) {
    return RouterFunctions.route(
        POST("/api/products")
            .and(contentType(MediaType.APPLICATION_JSON)),
        handler::create
    );
}
~~~

Request hợp lệ có thể là:

~~~http
POST /api/products
Content-Type: application/json

{"name":"Keyboard","price":1250000}
~~~

Request gửi Content-Type: text/plain không thỏa predicate JSON. Trong functional routing, contentType là điều kiện chọn route. Nếu không có route thay thế hoặc xử lý fallback, request có thể kết thúc ở trạng thái không tìm thấy route; không nên mặc định rằng predicate tự sinh phản hồi 415 Unsupported Media Type như một số trường hợp mapping annotation.

Nếu API cần hỗ trợ nhiều loại body, hãy khai báo route riêng hoặc kết hợp predicate có chủ đích, sau đó mô tả tất cả media type được hỗ trợ trong OpenAPI requestBody.content.

## 8. Produces là điều kiện về response representation

Produces mô tả loại response mà endpoint có thể trả về. Client thường gửi header Accept để nêu các media type có thể xử lý:

~~~http
GET /api/products
Accept: application/json
~~~

Functional route có thể dùng accept predicate:

~~~java
RouterFunction<ServerResponse> listRoute(ProductHandler handler) {
    return RouterFunctions.route(
        GET("/api/products")
            .and(accept(MediaType.APPLICATION_JSON)),
        handler::list
    );
}
~~~

Handler vẫn cần tạo response với Content-Type phù hợp:

~~~java
Mono<ServerResponse> list(ServerRequest request) {
    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(productService.findAll(), ProductResponse.class);
}
~~~

Predicate accept kiểm tra media type mà client chấp nhận. Nó không tự biến body thành JSON và cũng không thay thế việc đặt response Content-Type. Việc serialize body còn phụ thuộc codec và kiểu dữ liệu mà WebFlux hỗ trợ.

Nếu Accept không tương thích với route, predicate có thể không khớp và router tiếp tục tìm route khác. Nếu không có route phù hợp, kết quả có thể là 404. Muốn trả 406 Not Acceptable rõ ràng, cần thiết kế fallback hoặc xử lý lỗi tương ứng thay vì chỉ dựa vào accept predicate.

## 9. Kết hợp path, method, consumes và produces

Một endpoint tạo sản phẩm có thể yêu cầu đủ bốn điều kiện:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    RequestPredicate jsonInputAndOutput =
        contentType(MediaType.APPLICATION_JSON)
            .and(accept(MediaType.APPLICATION_JSON));

    return RouterFunctions.route()
        .POST("/api/products", jsonInputAndOutput, handler::create)
        .build();
}
~~~

Điều kiện có thể diễn giải như sau:

| Thành phần | Giá trị |
|---|---|
| Path | /api/products |
| Method | POST |
| Consumes | application/json |
| Produces | application/json |
| Handler | ProductHandler.create |

Client phải gửi JSON và chấp nhận response JSON. Handler đọc body thành DTO, gọi service rồi trả response JSON. Khi mô tả trong OpenAPI, operation POST phải có request body content application/json và response content application/json.

Không dùng một media type trong OpenAPI nếu runtime chỉ hỗ trợ media type khác. Ví dụ route chỉ nhận JSON nhưng requestBody lại quảng bá cả XML sẽ khiến client gửi request không thể được xử lý.

## 10. Mô tả functional route bằng @RouterOperation

Springdoc hỗ trợ mô tả functional endpoint bằng @RouterOperation. Annotation này liên kết một route với handler bean và method tương ứng, đồng thời cung cấp metadata operation cho OpenAPI.

Với một route:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@Bean
@RouterOperation(
    path = "/api/products",
    method = RequestMethod.GET,
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = ProductHandler.class,
    beanMethod = "list",
    operation = @Operation(
        operationId = "listProducts",
        summary = "Liệt kê sản phẩm",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Danh sách sản phẩm."
            )
        }
    )
)
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .build();
}
~~~

Các thuộc tính quan trọng:

- path phải khớp đường dẫn router.
- method phải khớp HTTP method mà route nhận.
- consumes mô tả media type request được chấp nhận.
- produces mô tả media type response.
- beanClass xác định lớp chứa handler.
- beanMethod xác định method xử lý tương ứng.
- operation cung cấp metadata OpenAPI như operationId, summary, parameter, request body, response và security.

@RouterOperation là metadata cho springdoc. Nếu path hoặc method trong annotation khác route thực tế, tài liệu có thể mô tả một endpoint không tồn tại hoặc bỏ sót endpoint thật.

## 11. Dùng @RouterOperations cho nhiều route

Một RouterFunction bean thường chứa nhiều route. Khi đó, dùng @RouterOperations để mô tả từng operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.web.bind.annotation.RequestMethod;

@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = ProductHandler.class,
        beanMethod = "list",
        operation = @Operation(
            operationId = "listProducts",
            summary = "Liệt kê sản phẩm",
            responses = @ApiResponse(
                responseCode = "200",
                description = "Danh sách sản phẩm."
            )
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        consumes = {MediaType.APPLICATION_JSON_VALUE},
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = ProductHandler.class,
        beanMethod = "create",
        operation = @Operation(
            operationId = "createProduct",
            summary = "Tạo sản phẩm",
            responses = @ApiResponse(
                responseCode = "201",
                description = "Sản phẩm đã được tạo."
            )
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/products",
            accept(MediaType.APPLICATION_JSON),
            handler::list
        )
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON)
                .and(accept(MediaType.APPLICATION_JSON)),
            handler::create
        )
        .build();
}
~~~

Hai operation dùng cùng path nhưng khác method nên phải được khai báo thành hai RouterOperation riêng. POST có consumes application/json; cả hai operation đều công bố produces application/json.

Khi có request body, bổ sung @Operation(requestBody = ...) với @Content và @Schema để mô tả DTO. Khi có path variable, khai báo @Parameter với in = ParameterIn.PATH và required = true. Response cũng nên có schema phù hợp với kiểu dữ liệu handler thực sự trả về.

## 12. Mô tả request body và response content

Consumes trong @RouterOperation giúp springdoc biết media type của request. Để tài liệu có schema request body hữu ích, khai báo thêm metadata trong @Operation:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    ),
    responses = {
        @ApiResponse(
            responseCode = "201",
            description = "Sản phẩm đã được tạo.",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        )
    }
)
~~~

Đoạn annotation trên cần các import @Content và @Schema từ Swagger annotations. Dùng tên đầy đủ cho RequestBody để tránh nhầm với annotation RequestBody của Spring.

Schema phải phản ánh DTO mà handler thực sự đọc và trả về. Nếu handler nhận CreateProductRequest nhưng OpenAPI mô tả ProductResponse làm request body, client sẽ tạo payload sai. Nếu handler trả Mono<ProductResponse> nhưng tài liệu khai báo một danh sách, response contract cũng không chính xác.

## 13. Nhiều media type và route thay thế

Một endpoint có thể hỗ trợ nhiều representation, ví dụ JSON và XML. Có thể kết hợp các predicate:

~~~java
RequestPredicate jsonOrXml =
    contentType(MediaType.APPLICATION_JSON)
        .or(contentType(MediaType.APPLICATION_XML));

RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        POST("/api/imports").and(jsonOrXml),
        handler::importData
    );
~~~

Handler cần thực sự đọc được cả hai định dạng, thường thông qua các codec tương ứng. Việc thêm XML predicate không tự cài đặt XML decoder hoặc encoder.

Với response, có thể khai báo các route theo Accept khác nhau:

~~~java
RouterFunction<ServerResponse> exportRoutes(ExportHandler handler) {
    return RouterFunctions.route()
        .GET(
            "/api/reports",
            accept(MediaType.APPLICATION_JSON),
            handler::asJson
        )
        .GET(
            "/api/reports",
            accept(MediaType.TEXT_CSV),
            handler::asCsv
        )
        .build();
}
~~~

Hai route có cùng path và method nhưng khác Accept predicate. Trong OpenAPI, thông thường đây vẫn là một operation GET, với response content chứa cả application/json và text/csv nếu cùng một operation hỗ trợ hai representation. Chỉ tạo hai operation riêng nếu chúng thực sự khác về path hoặc method.

Nếu nhiều route có predicate giao nhau, hãy xác định rõ thứ tự và cách kết hợp. Đừng để một route tổng quát bắt request trước route cụ thể hơn.

## 14. Thứ tự route và điều kiện chồng lấn

Khi ghép nhiều RouterFunction, thứ tự có thể ảnh hưởng route nào được chọn nếu nhiều predicate cùng khớp. Hãy đặt route cụ thể trước route tổng quát và tránh điều kiện chồng lấn không cần thiết.

Ví dụ nên đặt route chi tiết trước:

~~~java
RouterFunction<ServerResponse> routes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products/search", handler::search)
        .GET("/api/products/{id}", handler::get)
        .GET("/api/**", handler::fallbackGet)
        .build();
}
~~~

Route /api/products/search có ý nghĩa riêng. Nếu route tổng quát được đặt trước và có predicate phù hợp rộng hơn, request có thể bị xử lý bởi handler không mong muốn.

Với route lồng nhau hoặc được ghép từ nhiều module, hãy kiểm tra toàn bộ RouterFunction cuối cùng. Không chỉ đọc riêng từng bean vì composition có thể làm thay đổi thứ tự và phạm vi khớp.

## 15. Phản hồi khi media type không phù hợp

Trong functional routing, contentType và accept là predicate chọn route. Khi predicate không khớp, router có thể thử route tiếp theo; nếu không có route phù hợp, request có thể đi tới nhánh không tìm thấy handler.

Điều này khác với việc cho rằng chỉ cần thêm consumes hoặc produces là framework luôn trả đúng 415 hoặc 406. Nếu hợp đồng yêu cầu status rõ ràng, hãy thiết kế fallback và mô tả response đó.

Ví dụ fallback cho request POST vào cùng path nhưng không có route JSON phù hợp:

~~~java
RouterFunction<ServerResponse> routes(ProductHandler handler) {
    return RouterFunctions.route()
        .POST(
            "/api/products",
            contentType(MediaType.APPLICATION_JSON),
            handler::create
        )
        .route(
            request -> request.method() == HttpMethod.POST
                && request.path().equals("/api/products"),
            handler::unsupportedMediaType
        )
        .build();
}
~~~

Handler fallback có thể trả 415:

~~~java
Mono<ServerResponse> unsupportedMediaType(ServerRequest request) {
    return ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
        .bodyValue("Content-Type không được hỗ trợ.");
}
~~~

Tương tự, nếu muốn trả 406 khi Accept không được hỗ trợ, cần một fallback nhận diện path và method nhưng không khớp media type hợp lệ, sau đó trả NOT_ACCEPTABLE. Hãy tránh để fallback tổng quát bắt nhầm request đã được một route hợp lệ xử lý.

Trong OpenAPI, mô tả 415 cho request body có Content-Type không hỗ trợ và 406 cho response representation không được chấp nhận nếu runtime thực sự trả các mã đó. Nếu runtime trả 404 khi không tìm thấy route, tài liệu phải thể hiện hành vi thực tế hoặc ứng dụng cần thay đổi fallback.

## 16. Tích hợp springdoc với WebFlux functional endpoints

Với Spring Boot 3 và springdoc 2.x, ứng dụng WebFlux thường dùng starter springdoc-openapi-starter-webflux-ui. Starter cung cấp tích hợp tài liệu và Swagger UI cho WebFlux. Hãy chọn starter WebFlux thay vì WebMVC khi ứng dụng chạy reactive stack.

Functional endpoint được mô tả bằng RouterOperation/RouterOperations. Đối với annotated controller, springdoc thường có thể đọc trực tiếp mapping annotation. Đối với RouterFunction, cần kiểm tra metadata annotation có bao phủ route và handler mong muốn.

Các bước triển khai:

1. Tạo RouterFunction bean với predicate phản ánh path, method, consumes và produces.
2. Tách handler thành bean có method xử lý rõ ràng.
3. Gắn @RouterOperation hoặc @RouterOperations lên bean route.
4. Khai báo path, method, consumes, produces khớp với router.
5. Khai báo request body, path parameter, response schema và error response trong @Operation.
6. Khởi động ứng dụng và kiểm tra OpenAPI JSON.
7. Mở Swagger UI và thử từng operation với media type tương ứng.

Nếu springdoc không nhận diện route, kiểm tra dependency starter, vị trí annotation, beanClass, beanMethod và phiên bản tương thích giữa Spring Boot, Spring Framework và springdoc.

## 17. Kiểm tra OpenAPI document được sinh ra

Sau khi ứng dụng khởi động, lấy tài liệu:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra path và method:

~~~json
{
  "paths": {
    "/api/products": {
      "get": {
        "operationId": "listProducts"
      },
      "post": {
        "operationId": "createProduct",
        "requestBody": {
          "content": {
            "application/json": {}
          }
        }
      }
    }
  }
}
~~~

Đây là đoạn minh họa cấu trúc, không phải output đầy đủ. Trong tài liệu thật, kiểm tra:

- Path trong OpenAPI khớp route đã đăng ký.
- Method có đúng HTTP verb.
- Path parameter được khai báo đúng tên, vị trí và required.
- Request body content chỉ liệt kê media type mà handler hỗ trợ.
- Response content phản ánh đúng media type và schema.
- operationId duy nhất trong toàn bộ document.
- Error response như 400, 404, 406 hoặc 415 có mặt khi runtime hỗ trợ.
- Security requirement phù hợp với policy của route.

Đối chiếu OpenAPI JSON với hành vi thực tế. Annotation không tự xác nhận rằng route hoạt động hoặc handler serialize đúng định dạng.

## 18. Kiểm thử route bằng WebTestClient

WebTestClient có thể kiểm thử functional route mà không cần khởi chạy server thật:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.reactive.server.WebTestClient.bindToRouterFunction;

class ProductRoutesTest {

    private final WebTestClient client =
        bindToRouterFunction(productRoutes).build();

    @Test
    void createsProductWithJson() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .bodyValue(new CreateProductRequest("Keyboard", 1250000))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
    }

    @Test
    void listsProductsAsJson() {
        client.get()
            .uri("/api/products")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
    }
}
~~~

Ví dụ giả định productRoutes là RouterFunction đã được cấu hình với service test phù hợp. Cần bổ sung test cho path không tồn tại, method không được hỗ trợ, Content-Type không phù hợp, Accept không phù hợp và các fallback 406/415 nếu ứng dụng triển khai chúng.

Ngoài kiểm thử route, nên có kiểm thử tài liệu: gọi /v3/api-docs, đọc JSON rồi xác nhận path, method, consumes, produces và schema. Hai nhóm kiểm thử bổ sung cho nhau: WebTestClient xác minh hành vi route, còn kiểm tra OpenAPI xác minh hợp đồng được công bố.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ khai báo RouterFunction mà không có RouterOperation | Functional route có thể không xuất hiện đầy đủ trong OpenAPI | Bổ sung @RouterOperation hoặc @RouterOperations |
| Path trong annotation khác path runtime | Tài liệu trỏ tới endpoint không tồn tại | Đồng bộ path ở router và metadata |
| Method trong annotation sai | Swagger UI gửi sai HTTP method | Kiểm tra RequestMethod với predicate route |
| Thiếu consumes | Client không biết định dạng body được nhận | Khai báo consumes và requestBody.content |
| Khai báo consumes nhưng handler không đọc được định dạng đó | Request lỗi khi decode body | Kiểm tra codec và kiểu DTO |
| Nhầm Accept với Content-Type | Route khớp sai điều kiện media type | Dùng contentType cho request và accept cho response negotiation |
| Nghĩ accept predicate tự trả 406 | Request không khớp có thể rơi vào 404 | Thiết kế fallback nếu cần 406 rõ ràng |
| Nghĩ contentType predicate tự trả 415 | Request có thể không tìm được route | Thiết kế fallback nếu cần 415 |
| Handler trả Content-Type không khớp produces | Client không xử lý được response | Đặt ServerResponse.contentType đúng và kiểm tra codec |
| Thiếu path parameter trong OpenAPI | Client generator tạo operation thiếu tham số | Khai báo @Parameter với in PATH |
| Nhiều route chồng lấn | Handler không mong muốn nhận request | Thu hẹp predicate và sắp xếp route cụ thể trước |
| Mô tả một operation cho mỗi media type dù path/method giống nhau | Tài liệu lặp hoặc sai cấu trúc | Mô tả nhiều media type trong cùng requestBody/response content khi phù hợp |

## 20. Ghi nhớ

- Path và HTTP method xác định operation mà router nhận.
- Consumes liên quan đến Content-Type của request body.
- Produces liên quan đến Accept và media type của response.
- RequestPredicates cung cấp path, method, contentType và accept; có thể kết hợp bằng and/or/negate.
- Handler phải đọc và ghi đúng media type; predicate không tự serialize body.
- Functional endpoint cần @RouterOperation hoặc @RouterOperations để springdoc liên kết route với metadata OpenAPI.
- Path, method, consumes, produces, beanClass và beanMethod trong annotation phải khớp route/handler thực tế.
- Mô tả rõ path parameter, request body, response schema và error response.
- Predicate không khớp có thể dẫn tới route khác hoặc 404; hãy triển khai fallback nếu cần 406/415 cụ thể.
- Kiểm thử cả route bằng WebTestClient và tài liệu được sinh ra tại /v3/api-docs.

Khi xây dựng WebFlux functional endpoint, hãy xác định rõ path, HTTP method, Content-Type mà request chấp nhận và Accept mà response hỗ trợ. Sau đó liên kết từng route với @RouterOperation để springdoc công bố đúng operation, media type và schema. Đối chiếu OpenAPI JSON với WebTestClient để hợp đồng tài liệu khớp hành vi thực tế.
