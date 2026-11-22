# Liên kết beanClass, beanMethod và chữ ký handler

Với Spring WebFlux functional endpoints, route được khai báo bằng một <code>RouterFunction</code> thay vì mapping annotation trên controller. springdoc-openapi không thể luôn suy ra đầy đủ operation từ route predicate và method reference, vì vậy cần mô tả rõ route bằng <code>@RouterOperation</code> hoặc <code>@RouterOperations</code>.

Hai thuộc tính <code>beanClass</code> và <code>beanMethod</code> liên kết operation OpenAPI với method xử lý thực tế. <code>beanClass</code> xác định lớp chứa handler; <code>beanMethod</code> xác định method trong lớp đó. Khi kết hợp với <code>path</code>, HTTP method và metadata trong <code>@Operation</code>, springdoc có thể gắn tài liệu vào đúng functional route.

Handler functional thường nhận một đối tượng <code>ServerRequest</code> và trả về <code>Mono&lt;ServerResponse&gt;</code>. Chữ ký này không thể hiện trực tiếp DTO request/response như một controller method thông thường. Vì vậy, cần khai báo tường minh parameter, request body và response schema khi kiểu dữ liệu không thể suy ra từ chữ ký handler.

## 1. Functional route gồm route predicate và handler

Trong WebFlux, một functional endpoint thường có hai phần:

- **Route predicate** xác định HTTP method, path, content type hoặc điều kiện request.
- **Handler function** nhận <code>ServerRequest</code>, xử lý request và tạo <code>ServerResponse</code>.

Ví dụ route:

~~~java
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/products/{id}"),
        handler::getById
    );
}
~~~

Predicate <code>GET("/products/{id}")</code> chọn request phù hợp. Method reference <code>handler::getById</code> chuyển request đến handler. Vì method reference không chứa metadata OpenAPI như summary, response schema hoặc tên operation, ta cần liên kết và mô tả riêng.

## 2. Vai trò của beanClass và beanMethod

Trong <code>@RouterOperation</code>:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| <code>path</code> | Path của route được công bố trong OpenAPI | <code>/products/{id}</code> |
| <code>method</code> | HTTP method của route | <code>RequestMethod.GET</code> |
| <code>beanClass</code> | Lớp Spring bean chứa handler method | <code>ProductHandler.class</code> |
| <code>beanMethod</code> | Tên method xử lý request trong bean class | <code>"getById"</code> |
| <code>produces</code> | Media type response mà route tạo ra | <code>application/json</code> |
| <code>consumes</code> | Media type request mà route chấp nhận | <code>application/json</code> |
| <code>operation</code> | Metadata OpenAPI bổ sung cho operation | <code>@Operation(...)</code> |

<code>beanClass</code> là lớp của handler được gọi, không nhất thiết là lớp cấu hình chứa method <code>@Bean</code>. <code>beanMethod</code> là tên method trong lớp handler, không phải tên method factory tạo <code>RouterFunction</code>.

Ví dụ, nếu route được đăng ký bằng <code>handler::getById</code>, phần liên kết sẽ là:

~~~java
beanClass = ProductHandler.class,
beanMethod = "getById"
~~~

Không truyền chuỗi <code>"handler::getById"</code> vào <code>beanMethod</code>. Thuộc tính này nhận tên method Java để springdoc tra cứu metadata của handler.

## 3. Khai báo một route bằng @RouterOperation

Với một functional route duy nhất trong bean method, có thể dùng <code>@RouterOperation</code>:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
class ProductRoutes {

    @Bean
    @RouterOperation(
        path = "/products/{id}",
        method = RequestMethod.GET,
        produces = {"application/json"},
        beanClass = ProductHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getProductById",
            summary = "Lấy sản phẩm theo mã",
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Tìm thấy sản phẩm",
                    content = @Content(
                        mediaType = "application/json",
                        schema = @Schema(
                            implementation = ProductResponse.class
                        )
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Không tìm thấy sản phẩm"
                )
            }
        )
    )
    RouterFunction<ServerResponse> productRoute(ProductHandler handler) {
        return RouterFunctions.route(
            RequestPredicates.GET("/products/{id}"),
            handler::getById
        );
    }
}
~~~

Ở đây, <code>path</code> và <code>method</code> mô tả route HTTP. <code>beanClass</code> và <code>beanMethod</code> chỉ ra method xử lý. <code>operation</code> bổ sung operationId, summary và response schema.

Giá trị <code>path</code> và <code>method</code> trong annotation phải khớp với predicate trong route builder. Nếu annotation mô tả GET nhưng route thực tế là POST, tài liệu sẽ không phản ánh đúng API.

## 4. Khai báo nhiều route bằng @RouterOperations

Một <code>RouterFunction</code> có thể ghép nhiều route bằng <code>andRoute</code> hoặc builder. Khi đó, dùng <code>@RouterOperations</code> để khai báo một operation cho từng route:

Ví dụ dưới đây là cấu hình thay thế cho ví dụ một route ở phần trước. Trong dự án, giữ một bean route phù hợp với số lượng route thực tế; không khai báo hai bean cùng đăng ký một path/method.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
class ProductRoutes {

    @Bean
    @RouterOperations({
        @RouterOperation(
            path = "/products/{id}",
            method = RequestMethod.GET,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = ProductHandler.class,
            beanMethod = "getById",
            operation = @Operation(
                operationId = "getProductById",
                summary = "Lấy sản phẩm theo mã",
                parameters = {
                    @Parameter(
                        name = "id",
                        in = ParameterIn.PATH,
                        required = true,
                        description = "Mã sản phẩm",
                        schema = @Schema(type = "string")
                    )
                },
                responses = {
                    @ApiResponse(
                        responseCode = "200",
                        description = "Tìm thấy sản phẩm",
                        content = @Content(
                            mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(
                                implementation = ProductResponse.class
                            )
                        )
                    ),
                    @ApiResponse(
                        responseCode = "404",
                        description = "Không tìm thấy sản phẩm"
                    )
                }
            )
        ),
        @RouterOperation(
            path = "/products",
            method = RequestMethod.POST,
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = ProductHandler.class,
            beanMethod = "create",
            operation = @Operation(
                operationId = "createProduct",
                summary = "Tạo sản phẩm",
                requestBody = @RequestBody(
                    required = true,
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(
                            implementation = CreateProductRequest.class
                        )
                    )
                ),
                responses = {
                    @ApiResponse(
                        responseCode = "201",
                        description = "Đã tạo sản phẩm",
                        content = @Content(
                            mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(
                                implementation = ProductResponse.class
                            )
                        )
                    ),
                    @ApiResponse(
                        responseCode = "400",
                        description = "Request không hợp lệ"
                    )
                }
            )
        )
    })
    RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
        return RouterFunctions.route(
                RequestPredicates.GET("/products/{id}"),
                handler::getById
            )
            .andRoute(
                RequestPredicates.POST("/products")
                    .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)),
                handler::create
            );
    }
}
~~~

Trong ví dụ, cùng một bean route công bố hai operation:

- GET <code>/products/{id}</code> liên kết với <code>ProductHandler.getById</code>.
- POST <code>/products</code> liên kết với <code>ProductHandler.create</code>.

Mỗi <code>@RouterOperation</code> cần mô tả đúng path, method, bean class và bean method của route tương ứng. Không dùng một <code>@RouterOperation</code> chung cho nhiều route có chữ ký hoặc schema khác nhau.

## 5. Chữ ký handler và điều springdoc có thể suy luận

Một handler functional thường có dạng:

~~~java
Mono<ServerResponse> getById(ServerRequest request)
~~~

hoặc:

~~~java
ServerResponse health(ServerRequest request)
~~~

Với reactive handler, kiểu trả về ngoài cùng là <code>Mono&lt;ServerResponse&gt;</code>. DTO thực tế có thể được tạo bên trong <code>ServerResponse.bodyValue(...)</code> hoặc <code>body(...)</code>, không xuất hiện trong generic return type của method.

Do đó, không nên kỳ vọng springdoc tự suy ra toàn bộ hợp đồng từ chữ ký:

| Thành phần | Chữ ký handler thể hiện | Cách mô tả khi cần |
|---|---|---|
| Path variable | Nằm trong <code>ServerRequest</code> | Khai báo <code>@Parameter(in = PATH)</code> |
| Query parameter | Đọc bằng <code>request.queryParam(...)</code> | Khai báo <code>@Parameter(in = QUERY)</code> |
| Header | Đọc từ <code>request.headers()</code> | Khai báo <code>@Parameter(in = HEADER)</code> nếu là tham số hợp đồng |
| Request body | Đọc bằng <code>bodyToMono(...)</code> hoặc <code>bodyToFlux(...)</code> | Khai báo <code>requestBody</code> và schema |
| Response body | Đóng gói trong <code>ServerResponse</code> | Khai báo response content và schema |
| Status code | Chọn bằng <code>ServerResponse.ok()</code>, <code>created()</code>, <code>notFound()</code>... | Khai báo từng <code>@ApiResponse</code> |

Đây là khác biệt quan trọng giữa functional endpoint và controller method nhận DTO trực tiếp. Chữ ký handler vẫn cần được liên kết bằng <code>beanClass</code>/<code>beanMethod</code>, nhưng schema của payload thường phải được bổ sung qua <code>@Operation</code>.

## 6. Ví dụ handler có chữ ký rõ ràng

Handler có thể là một Spring bean độc lập:

~~~java
import java.net.URI;

import org.springframework.stereotype.Component;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
class ProductHandler {

    private final ProductService service;

    ProductHandler(ProductService service) {
        this.service = service;
    }

    public Mono<ServerResponse> getById(ServerRequest request) {
        String id = request.pathVariable("id");

        return service.findById(id)
            .flatMap(product ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product)
            )
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
            .flatMap(service::create)
            .flatMap(product ->
                ServerResponse.created(
                        URI.create("/products/" + product.productId())
                    )
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product)
            );
    }
}

interface ProductService {
    Mono<ProductResponse> findById(String id);
    Mono<ProductResponse> create(CreateProductRequest request);
}

record CreateProductRequest(String name, Integer price) {}

record ProductResponse(String productId, String name, Integer price) {}
~~~

Trong ví dụ:

- <code>getById</code> đọc path variable bằng <code>request.pathVariable("id")</code>.
- <code>create</code> đọc body JSON thành <code>CreateProductRequest</code>.
- Cả hai method trả <code>Mono&lt;ServerResponse&gt;</code>, dù payload thực tế là <code>ProductResponse</code>.
- GET có thể trả 200 hoặc 404; POST có thể trả 201 hoặc lỗi request.

Khi khai báo <code>@RouterOperation</code>, cần chỉ ra response schema là <code>ProductResponse</code> và request schema là <code>CreateProductRequest</code>. Nếu chỉ dựa vào <code>Mono&lt;ServerResponse&gt;</code>, tài liệu có thể thiếu schema body.

## 7. Mô tả path, query và header parameter

Handler nhận một <code>ServerRequest</code>, nên các giá trị path/query/header không xuất hiện dưới dạng tham số Java riêng. Hãy khai báo chúng trong <code>@Operation.parameters</code>.

Ví dụ route tìm kiếm:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Parameter;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@RouterOperation(
    path = "/products",
    method = RequestMethod.GET,
    beanClass = ProductHandler.class,
    beanMethod = "search",
    operation = @Operation(
        operationId = "searchProducts",
        parameters = {
            @Parameter(
                name = "keyword",
                in = ParameterIn.QUERY,
                required = false,
                description = "Từ khóa tìm kiếm",
                schema = @Schema(type = "string")
            ),
            @Parameter(
                name = "page",
                in = ParameterIn.QUERY,
                required = false,
                description = "Số trang bắt đầu từ 0",
                schema = @Schema(type = "integer", minimum = "0")
            ),
            @Parameter(
                name = "X-Tenant-Id",
                in = ParameterIn.HEADER,
                required = true,
                description = "Mã tenant",
                schema = @Schema(type = "string")
            )
        }
    )
)
~~~

Các parameter trong annotation phải tương ứng với cách handler đọc dữ liệu:

~~~java
Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("keyword").orElse("");
    int page = request.queryParam("page")
        .map(Integer::parseInt)
        .orElse(0);
    String tenantId = request.headers()
        .firstHeader("X-Tenant-Id");
    // ...
}
~~~

Nếu parameter là bắt buộc, handler hoặc tầng validation phải thực sự từ chối request thiếu giá trị. <code>required = true</code> chỉ mô tả hợp đồng OpenAPI, không tự thêm validation cho functional route.

Không khai báo các header kỹ thuật như <code>Host</code>, <code>Content-Length</code> hoặc header do browser tự quản lý thành tham số nghiệp vụ thông thường. Với header xác thực, ưu tiên mô tả bằng security scheme.

## 8. Mô tả request body và response body

Với functional handler, request body thường được đọc bên trong method. Cần khai báo schema ở <code>@Operation.requestBody</code>:

~~~java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = CreateProductRequest.class)
    )
)
~~~

Response body cần khai báo trong từng <code>@ApiResponse</code>:

~~~java
responses = {
    @ApiResponse(
        responseCode = "201",
        description = "Đã tạo sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu request không hợp lệ"
    )
}
~~~

Nếu response là <code>204 No Content</code>, không khai báo schema body. Nếu response trả danh sách, dùng schema kiểu mảng hoặc DTO trang tương ứng. Nếu có nhiều status code, khai báo riêng để người tiêu thụ biết body nào có thể xuất hiện.

## 9. Đọc chữ ký handler và chọn kiểu bean method

springdoc cần tìm đúng method trong lớp được khai báo bởi <code>beanClass</code>. Vì vậy:

- <code>beanClass</code> phải trỏ đến đúng lớp handler.
- <code>beanMethod</code> phải trùng tên method Java.
- Method nên có tên duy nhất, dễ nhận diện.
- Handler bean phải được Spring quản lý và được dùng để xây dựng route.
- Nếu dùng method overload cùng tên, việc tra cứu metadata có thể trở nên mơ hồ; nên đổi tên các handler method để mỗi route có một method riêng.

Ví dụ tên rõ ràng:

~~~java
Mono<ServerResponse> getProductById(ServerRequest request)
Mono<ServerResponse> createProduct(ServerRequest request)
Mono<ServerResponse> searchProducts(ServerRequest request)
~~~

Sau đó dùng chính tên method trong annotation:

~~~java
beanClass = ProductHandler.class,
beanMethod = "getProductById"
~~~

Tên method không phải operationId. <code>beanMethod</code> dùng để liên kết tới Java handler; <code>operationId</code> là định danh operation trong OpenAPI, nên đặt theo quy ước client code generation của dự án.

## 10. Khi nào dùng @RouterOperation và @RouterOperations?

| Trường hợp | Annotation phù hợp |
|---|---|
| Một route được đăng ký trong một bean method | <code>@RouterOperation</code> |
| Nhiều route được ghép trong một <code>RouterFunction</code> bean | <code>@RouterOperations</code> |
| Một route cần metadata operation chi tiết | Đặt <code>@Operation</code> trong thuộc tính <code>operation</code> |
| Route có parameter/body/response không suy ra từ handler | Khai báo rõ trong <code>@Operation</code> |

Không cần tạo một class handler riêng cho mỗi route, nhưng cách tổ chức đó có thể giúp liên kết rõ ràng. Nếu một handler class có nhiều method, khai báo từng <code>@RouterOperation</code> với đúng <code>beanMethod</code>.

Với route lồng nhau hoặc được tạo qua hàm helper, annotation vẫn phải mô tả path/method cuối cùng được công bố. Nếu route được sinh động theo cấu hình runtime, cần xác minh springdoc có thể nhìn thấy cấu trúc route đó; khi không thể, cân nhắc bổ sung OpenAPI bằng customizer hoặc cấu hình tài liệu tĩnh phù hợp.

## 11. Kiểm tra tài liệu OpenAPI được sinh ra

Sau khi khởi động ứng dụng, truy cập endpoint mặc định:

~~~text
http://localhost:8080/v3/api-docs
~~~

Với từng functional route, kiểm tra:

1. Path và HTTP method khớp với route predicate.
2. <code>operationId</code> và summary đúng operation.
3. Path/query/header parameter có đúng tên, vị trí và required.
4. Request body có media type và schema đúng với kiểu handler đọc.
5. Response có đúng status code, media type và schema body.
6. Không có operation trùng hoặc thiếu do route composition.
7. <code>beanClass</code> và <code>beanMethod</code> đã liên kết đúng handler.

Một phần OpenAPI kỳ vọng cho route tạo sản phẩm có thể tương tự:

~~~yaml
paths:
  /products:
    post:
      operationId: createProduct
      summary: Tạo sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Đã tạo sản phẩm
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "400":
          description: Request không hợp lệ
~~~

Sau đó mở Swagger UI và dùng Try it out trên môi trường thử nghiệm. Kiểm tra request thực tế được gửi đúng path, method, content type và body. So sánh response runtime với schema đã sinh.

## 12. Lỗi thường gặp

**Dùng tên route bean method thay cho handler method.** <code>beanMethod</code> phải là method xử lý request trong <code>beanClass</code>, không phải method <code>@Bean</code> trả về <code>RouterFunction</code>.

**Đặt sai beanClass.** Nếu <code>beanClass</code> trỏ đến lớp cấu hình route thay vì lớp chứa handler method, springdoc không tìm thấy chữ ký mong muốn.

**Tên beanMethod không tồn tại hoặc bị overload.** Dùng tên method chính xác và ưu tiên method name duy nhất cho mỗi route.

**Path hoặc HTTP method không khớp predicate.** Đối chiếu <code>@RouterOperation.path</code>/<code>method</code> với <code>RequestPredicates</code> hoặc builder thực tế.

**Chỉ dựa vào ServerRequest để sinh parameter.** Các path/query/header được đọc động bên trong handler; khai báo rõ bằng <code>@Parameter</code> trong operation.

**Response schema bị thiếu.** <code>Mono&lt;ServerResponse&gt;</code> không cho biết DTO được ghi vào body; khai báo schema bằng <code>@ApiResponse</code>.

**Request body không có schema.** Khi handler gọi <code>bodyToMono</code>, khai báo <code>requestBody</code> và schema tương ứng.

**Annotation mô tả route nhưng predicate không có route đó.** Metadata OpenAPI không tạo route runtime. Đảm bảo route builder thực sự đăng ký endpoint.

**Một RouterFunction có nhiều route nhưng chỉ mô tả một operation.** Dùng <code>@RouterOperations</code> và liệt kê từng route cần công bố.

**Tài liệu và runtime khác nhau.** Kiểm tra cả <code>/v3/api-docs</code> lẫn request thực tế trong WebTestClient hoặc Swagger UI.

## 13. Danh sách rà soát trước khi công bố

- [ ] Mỗi functional route có metadata OpenAPI tương ứng.
- [ ] <code>beanClass</code> trỏ đúng lớp handler.
- [ ] <code>beanMethod</code> trỏ đúng method xử lý request.
- [ ] Tên handler method rõ ràng, không gây mơ hồ do overload.
- [ ] Path và HTTP method khớp route predicate.
- [ ] Parameter được khai báo tường minh khi handler đọc qua ServerRequest.
- [ ] Request body có media type và schema phù hợp.
- [ ] Response khai báo đúng status, media type và schema.
- [ ] Các route ghép trong cùng RouterFunction đều có operation tương ứng.
- [ ] Đã kiểm tra <code>/v3/api-docs</code> và Swagger UI.
- [ ] Đã thử request thực tế và đối chiếu với hợp đồng OpenAPI.

## Tài liệu tham khảo

- [springdoc-openapi – WebFlux functional endpoints](https://springdoc.org/#webflux-fn): khai báo tài liệu cho functional route bằng <code>@RouterOperation</code> và <code>@RouterOperations</code>.
- [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): route predicate, handler function, ServerRequest và ServerResponse.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): mô tả operation, parameter, request body và response.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): cấu trúc operation trong OpenAPI.
