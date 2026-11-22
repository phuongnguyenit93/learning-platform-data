# `operationId` và schema cần khai báo rõ cho route không suy luận đủ

Trong Spring WebFlux, functional endpoint thường được khai báo bằng `RouterFunction<ServerResponse>` và xử lý request trong các handler trả về `Mono<ServerResponse>` hoặc `Mono<Void>`. Cách viết này linh hoạt, nhưng chữ ký handler thường không thể hiện đầy đủ hợp đồng HTTP. Ví dụ, kiểu trả về `Mono<ServerResponse>` không cho biết response body là một `ProductResponse`, một danh sách sản phẩm hay một cấu trúc lỗi. Khi route được tạo bằng lambda hoặc ghép từ nhiều router, springdoc cũng không phải lúc nào suy ra được operation name, parameter và schema như với controller annotation.

Với springdoc-openapi, có thể khai báo metadata cho functional route bằng `@RouterOperation` hoặc `@RouterOperations`. Trong metadata đó, đặt `operationId` ổn định và mô tả rõ request, response, content type cùng schema. Tài liệu được sinh từ các khai báo này sẽ có hợp đồng rõ ràng hơn cho Swagger UI, validator và công cụ tạo client.

## 1. Vì sao functional route cần metadata tường minh?

Controller annotation thường đặt HTTP mapping và mô tả OpenAPI gần nhau:

```java
@GetMapping("/api/products/{id}")
ProductResponse getProduct(@PathVariable UUID id) {
    return productService.getById(id);
}
```

Từ `@GetMapping`, `@PathVariable` và kiểu trả về, springdoc có thể suy ra nhiều thông tin như HTTP method, path parameter và response schema.

Functional route thường được khai báo theo cách khác:

```java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products/{id}", handler::getById)
            .build();
}
```

Ở đây, route được mô tả trong DSL. Handler nhận `ServerRequest` và tự tạo `ServerResponse`. Chữ ký `Mono<ServerResponse>` không bộc lộ kiểu body cuối cùng. Thông tin path variable cũng được đọc từ `request.pathVariable("id")`, nên không có `@PathVariable` để springdoc dựa vào.

Vì vậy, với functional route, cần cung cấp rõ các phần sau khi không thể suy luận đáng tin cậy:

- HTTP method và path.
- `operationId` và summary.
- Path, query và header parameter.
- Request body, media type và schema.
- Các response code, media type và response schema.
- Security requirement nếu operation cần xác thực.

## 2. Vai trò của `@RouterOperation` và `@RouterOperations`

Springdoc cung cấp hai annotation chính để liên kết metadata OpenAPI với functional route:

| Annotation | Cách dùng |
|---|---|
| `@RouterOperation` | Mô tả metadata cho một route cụ thể |
| `@RouterOperations` | Gom nhiều `@RouterOperation` trên một bean khai báo nhiều route |

Các thuộc tính quan trọng của `@RouterOperation` gồm:

- `path`: đường dẫn route, phải khớp route thực tế.
- `method`: HTTP method như `GET`, `POST`, `PUT` hoặc `DELETE`.
- `beanClass`: class chứa handler method được liên kết.
- `beanMethod`: tên method xử lý route.
- `produces`: media type response, ví dụ `application/json`.
- `consumes`: media type request, ví dụ `application/json`.
- `operation`: annotation `@Operation` chứa `operationId`, mô tả, parameter, request body, response và security.

Với springdoc-openapi 2.x, các annotation router nằm trong package `org.springdoc.core.annotations`. Dự án cần dùng WebFlux starter tương ứng với phiên bản Spring Boot và springdoc đang cài đặt.

## 3. `operationId` là định danh của operation

`operationId` là tên định danh duy nhất của một operation trong OpenAPI document. Công cụ sinh SDK thường dùng giá trị này để đặt tên method trong client. Ví dụ:

```yaml
paths:
  /api/products/{id}:
    get:
      operationId: getProductById
```

Một SDK có thể tạo method tương ứng như `getProductById(...)`. Nếu `operationId` thay đổi, tên method trong SDK sinh lại cũng có thể thay đổi, ảnh hưởng mã nguồn client.

Quy tắc đặt tên nên áp dụng:

- Dùng tên mô tả hành động và tài nguyên, ví dụ `listProducts`, `getProductById`, `createProduct`.
- Bảo đảm duy nhất trong một OpenAPI document.
- Tránh tên chung chung như `handle`, `process` hoặc `route1`.
- Tránh phụ thuộc tên lambda hoặc tên method nội bộ dễ thay đổi.
- Giữ ổn định khi chỉ refactor cấu trúc handler mà hợp đồng API không đổi.
- Không tái sử dụng một `operationId` cho hai method HTTP khác nhau trên cùng hoặc khác path.

`operationId` không phải URL, không phải tên bean và không thay thế path/method. Nó là định danh trong hợp đồng API.

## 4. Liên kết metadata với handler method

Ví dụ handler có các method được đặt tên rõ ràng:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
class ProductHandler {

    private final ProductService productService;

    ProductHandler(ProductService productService) {
        this.productService = productService;
    }

    Mono<ServerResponse> list(ServerRequest request) {
        return productService.findAll()
                .collectList()
                .flatMap(products -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(products));
    }

    Mono<ServerResponse> getById(ServerRequest request) {
        UUID id = UUID.fromString(request.pathVariable("id"));
        return productService.findById(id)
                .flatMap(product -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(product))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
                .flatMap(productService::create)
                .flatMap(product -> ServerResponse
                        .created(URI.create("/api/products/" + product.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(product));
    }
}
```

`ProductService` là service nghiệp vụ được inject vào handler; các method minh họa trả về publisher reactive tương ứng với dữ liệu sản phẩm.

Router bean liên kết từng route đến đúng handler method:

```java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::getById)
            .POST("/api/products", handler::create)
            .build();
}
```

Khi mô tả OpenAPI, `beanClass` trỏ đến `ProductHandler.class`, còn `beanMethod` là tên method tương ứng như `list`, `getById` hoặc `create`. Việc đặt handler trong bean có method rõ ràng giúp metadata dễ liên kết và dễ bảo trì hơn so với khai báo toàn bộ logic dưới dạng lambda ẩn danh.

## 5. Khai báo `operationId` và response schema cho nhiều route

Ví dụ dưới đây mô tả ba route sản phẩm bằng `@RouterOperations`. Phần metadata đặt trên bean tạo router:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "list",
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
            operationId = "listProducts",
            summary = "Liệt kê sản phẩm",
            responses = {
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
            }
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "getById",
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
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
                @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm")
            }
        )
    ),
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.POST,
        beanClass = ProductHandler.class,
        beanMethod = "create",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE,
        operation = @Operation(
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
                    description = "Sản phẩm đã được tạo",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = ProductResponse.class)
                    )
                ),
                @ApiResponse(responseCode = "400", description = "Dữ liệu không hợp lệ")
            }
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::getById)
            .POST("/api/products", handler::create)
            .build();
}
```

Điểm cần chú ý:

- Mỗi `@RouterOperation` mô tả một cặp path và HTTP method.
- `path`, `method`, `beanClass` và `beanMethod` phải trỏ đến route/handler tương ứng.
- `operationId` được khai báo tường minh và không trùng nhau.
- Response danh sách dùng `@ArraySchema` để biểu diễn mảng các `ProductResponse`.
- Response đơn dùng `@Schema(implementation = ProductResponse.class)`.
- Request body của `POST` tham chiếu `CreateProductRequest`.
- `produces` và `consumes` mô tả media type của route, còn `@Content` mô tả schema của payload.

Nếu route DSL thực tế khác metadata, OpenAPI có thể mô tả sai endpoint. Hãy cập nhật route và annotation cùng nhau.

## 6. Khai báo schema DTO bằng `@Schema`

Với functional handler, schema body nên được thể hiện bằng DTO cụ thể. Ví dụ:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Schema(name = "CreateProductRequest", description = "Dữ liệu tạo sản phẩm")
public record CreateProductRequest(
    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard")
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(description = "Giá bán", example = "129.90", minimum = "0.01")
    @DecimalMin("0.01")
    BigDecimal price
) {}

@Schema(name = "ProductResponse", description = "Thông tin sản phẩm")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", format = "uuid", example = "8f14e45f-ea4f-4f8d-9b8a-4f4c3a2d1e00")
    UUID id,

    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard")
    String name,

    @Schema(description = "Giá bán", example = "129.90")
    BigDecimal price,

    @Schema(description = "Thời điểm tạo", format = "date-time", example = "2026-05-20T10:15:30Z")
    Instant createdAt
) {}
```

`@Schema` mô tả tên, ý nghĩa, định dạng và ví dụ của từng trường. Bean Validation như `@NotBlank`, `@Size` và `@DecimalMin` mô tả thêm ràng buộc đầu vào; springdoc có thể phản ánh nhiều constraint này vào schema tùy phiên bản và cấu hình. Dù vậy, validation runtime vẫn cần được kích hoạt trong ứng dụng.

Đặt `implementation` trỏ đến DTO cụ thể giúp tài liệu không phải suy luận kiểu dữ liệu từ `ServerResponse`. Với kiểu generic như `List<ProductResponse>`, cần dùng `@ArraySchema` để khai báo schema phần tử.

## 7. Khai báo path parameter rõ ràng

Functional handler thường lấy path variable từ `ServerRequest`:

```java
String rawId = request.pathVariable("id");
UUID id = UUID.fromString(rawId);
```

Do không có `@PathVariable`, hãy mô tả parameter trong `@Operation`:

```java
operation = @Operation(
    operationId = "getProductById",
    parameters = {
        @io.swagger.v3.oas.annotations.Parameter(
            name = "id",
            in = io.swagger.v3.oas.annotations.enums.ParameterIn.PATH,
            required = true,
            description = "UUID của sản phẩm",
            schema = @Schema(type = "string", format = "uuid")
        )
    },
    responses = {
        @ApiResponse(responseCode = "200", description = "Tìm thấy sản phẩm")
    }
)
```

Tên `id` phải khớp `{id}` trong path. Path parameter luôn bắt buộc trong OpenAPI; đặt `required = true` để metadata thể hiện điều đó. Nếu tên trong annotation khác tên route variable, tài liệu và request thực tế sẽ không đồng nhất.

## 8. Khai báo query parameter và header

Giả sử handler đọc query parameter `page` và `size` bằng `request.queryParam(...)`. Có thể mô tả chúng bằng `@Parameter`:

```java
parameters = {
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Số trang, bắt đầu từ 0",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Số phần tử mỗi trang",
        schema = @Schema(type = "integer", minimum = "1", maximum = "100", defaultValue = "20")
    ),
    @Parameter(
        name = "X-Request-Source",
        in = ParameterIn.HEADER,
        description = "Nguồn gửi request",
        required = false,
        schema = @Schema(type = "string", example = "admin-console")
    )
}
```

Khai báo parameter phải phản ánh đúng cách handler xử lý request:

- Nếu `page` không được gửi, handler có thực sự dùng 0 không?
- Nếu `size` không được gửi, giá trị runtime mặc định là bao nhiêu?
- Nếu `size` lớn hơn 100, handler trả lỗi hay tự giới hạn?
- Header có thực sự được đọc và có ảnh hưởng nghiệp vụ không?

`defaultValue` trong `@Schema` là metadata OpenAPI. Nó không tự gán giá trị cho `ServerRequest`. Handler phải áp dụng default runtime và validation riêng.

## 9. Mô tả request body cho route POST/PUT/PATCH

Với functional endpoint, handler thường gọi `request.bodyToMono(...)`:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProductRequest.class)
            .flatMap(productService::create)
            .flatMap(product -> ServerResponse
                    .created(URI.create("/api/products/" + product.id()))
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product));
}
```

OpenAPI không thể dựa vào `Mono<ServerResponse>` để biết body là `CreateProductRequest`. Hãy khai báo request body trong `@Operation`:

```java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Thông tin sản phẩm cần tạo",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateProductRequest.class)
    )
)
```

Đối với `PUT` hoặc `PATCH`, chọn DTO phù hợp với ngữ nghĩa cập nhật. Nếu `PATCH` cho phép bỏ qua field, schema nên mô tả đúng field optional và semantics của giá trị `null`; không dùng DTO tạo mới nếu quy tắc cập nhật khác nhau.

## 10. Mô tả response schema cho `Mono<ServerResponse>`

Handler có thể trả response bằng nhiều nhánh:

```java
Mono<ServerResponse> getById(ServerRequest request) {
    UUID id = UUID.fromString(request.pathVariable("id"));

    return productService.findById(id)
            .flatMap(product -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(product))
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Kiểu Java của method vẫn là `Mono<ServerResponse>`, nhưng HTTP response có hai trường hợp:

| Status | Body | Mô tả OpenAPI |
|---|---|---|
| `200` | `ProductResponse` | `application/json` với schema `ProductResponse` |
| `404` | Không có body trong ví dụ | Mô tả không tìm thấy sản phẩm |

Đừng khai báo một response `200` duy nhất nếu handler có thể trả `404`, `400`, `409` hoặc status khác. Tài liệu nên liệt kê các nhánh response thực tế mà client cần xử lý.

## 11. Mô tả response danh sách và reactive publisher

Một handler có thể trả `Flux<ProductResponse>` ở tầng service nhưng gom thành list trước khi ghi response:

```java
Mono<ServerResponse> list(ServerRequest request) {
    return productService.findAll()
            .collectList()
            .flatMap(products -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(products));
}
```

Nếu HTTP response là JSON array, schema phải thể hiện mảng:

```java
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
```

Không nhầm kiểu reactive trong Java với cấu trúc JSON trên wire. `Mono<T>` thường phát ra một giá trị; `Flux<T>` có thể phát nhiều giá trị. Nhưng HTTP body có thể là JSON object, JSON array, NDJSON hoặc Server-Sent Events tùy cách handler ghi response và media type được chọn.

Nếu route phát `text/event-stream` hoặc `application/x-ndjson`, hãy mô tả media type và cấu trúc event/record thực tế. Không mô tả một stream như JSON array nếu client nhận các phần tử theo định dạng streaming riêng.

## 12. Khai báo lỗi và response không có body

Response không có body chỉ cần `description`, không cần schema giả. Ví dụ:

```java
@ApiResponse(responseCode = "204", description = "Đã xóa sản phẩm")
```

Với lỗi có cấu trúc, nên dùng DTO chung như `ApiErrorResponse`:

```java
@Schema(name = "ApiErrorResponse", description = "Thông tin lỗi API")
public record ApiErrorResponse(
    @Schema(example = "PRODUCT_NOT_FOUND") String code,
    @Schema(example = "Không tìm thấy sản phẩm") String message,
    @Schema(format = "date-time") Instant timestamp
) {}
```

Khai báo response:

```java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiErrorResponse.class)
    )
)
```

Nếu exception handler dùng `ProblemDetail` hoặc một error envelope khác, hãy khai báo schema tương ứng với JSON thực tế. Không mô tả `ApiErrorResponse` nếu runtime trả một cấu trúc khác.

## 13. Mô tả security requirement cho functional route

Functional route vẫn có thể dùng các cơ chế bảo mật như controller endpoint. Có thể gắn security requirement trong `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@Operation(
    operationId = "deleteProduct",
    summary = "Xóa sản phẩm",
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = {
        @ApiResponse(responseCode = "204", description = "Đã xóa sản phẩm"),
        @ApiResponse(responseCode = "401", description = "Chưa xác thực"),
        @ApiResponse(responseCode = "403", description = "Không đủ quyền")
    }
)
```

Scheme `bearerAuth` phải được khai báo trong `components.securitySchemes` bằng `@SecurityScheme` hoặc OpenAPI configuration. Security annotation chỉ mô tả hợp đồng; Spring Security vẫn phải xác minh token và phân quyền request.

Nếu một route public nằm trong document có security toàn cục, cần mô tả operation đó là public bằng requirement phù hợp và kiểm tra kết quả `/v3/api-docs`. Không suy luận rằng route không có `@SecurityRequirement` luôn là public, vì nó có thể kế thừa security từ document.

## 14. Route lồng nhau và router được ghép từ nhiều module

Ứng dụng WebFlux có thể chia router theo module:

```java
@Bean
RouterFunction<ServerResponse> apiRoutes(
        RouterFunction<ServerResponse> productRoutes,
        RouterFunction<ServerResponse> orderRoutes) {
    return productRoutes.and(orderRoutes);
}
```

Mỗi router con có thể có metadata riêng. Khi ghép router, cần đảm bảo annotation metadata được đặt tại bean mà springdoc có thể phát hiện theo cơ chế của phiên bản đang dùng, và `path`/`method` vẫn khớp route sau khi áp dụng prefix hoặc nesting.

Với nested route:

```java
RouterFunctions.route()
    .path("/api/v1", builder -> builder
        .GET("/products/{id}", handler::getById))
    .build();
```

Đường dẫn hiệu lực là `/api/v1/products/{id}`. Metadata OpenAPI phải mô tả đường dẫn hiệu lực mà client gọi, không chỉ phần path tương đối `/products/{id}`.

Nếu route được tạo động từ cấu hình hoặc plugin, cân nhắc tạo OpenAPI document qua customizer có kiểm soát thay vì cố gắn annotation tĩnh cho các route không tồn tại cố định. Dù dùng cách nào, output cuối cùng phải là một OpenAPI document hợp lệ.

## 15. Kiểm tra `operationId` và schema trong OpenAPI output

Sau khi khởi động ứng dụng, tải tài liệu:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Kiểm tra các operation:

```bash
jq '.paths["/api/products"].get.operationId' openapi.json
jq '.paths["/api/products"].get.responses["200"].content["application/json"].schema' openapi.json
jq '.paths["/api/products"].post.requestBody.content["application/json"].schema' openapi.json
```

Kiểm tra path parameter:

```bash
jq '.paths["/api/products/{id}"].get.parameters' openapi.json
```

Kết quả cần xác nhận:

- Mỗi route có đúng HTTP method và path.
- `operationId` tồn tại, đúng tên và không trùng.
- Path parameter có tên khớp path template và được đánh dấu required.
- Query/header parameter có đúng vị trí, kiểu và default/example.
- Request body có đúng required, media type và schema.
- Response `200`, `201`, `204`, `400`, `404`... có đúng mô tả và schema.
- Array response dùng `type: array` và `$ref` đến schema phần tử.
- Các `$ref` trỏ đến schema tồn tại trong `components.schemas`.

Swagger UI hiển thị kết quả trực quan, nhưng kiểm tra JSON/YAML trực tiếp giúp phát hiện chính xác metadata bị thiếu hoặc liên kết sai.

## 16. Kiểm tra route metadata bằng test

Có thể viết integration test gọi endpoint `/v3/api-docs` và xác nhận các trường quan trọng. Ví dụ ý tưởng với `WebTestClient`:

```java
webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/products'].get.operationId")
        .isEqualTo("listProducts")
        .jsonPath("$.paths['/api/products'].get.responses['200']")
        .exists();
```

Đối với schema, có thể kiểm tra `$ref` và `components.schemas.ProductResponse`. Test nên tập trung vào hợp đồng quan trọng: operationId, request body, response schema, status code và security requirement. Không cần snapshot toàn bộ document nếu thứ tự hoặc metadata phụ có thể thay đổi không ảnh hưởng hợp đồng.

Ngoài test tài liệu, cần test route runtime bằng `WebTestClient`: xác nhận method/path đúng, content type đúng, body được deserialize, lỗi được ánh xạ đúng status và authorization hoạt động.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Functional route không xuất hiện trong OpenAPI | Thiếu `@RouterOperation`/`@RouterOperations` hoặc springdoc không phát hiện router | Kiểm tra WebFlux starter và metadata trên router bean |
| Có path nhưng thiếu operationId | Không khai báo `operation.operationId` | Đặt operationId tường minh trong `@Operation` |
| operationId bị trùng | Tái sử dụng tên giữa nhiều route | Đặt tên duy nhất trong document và kiểm tra bằng validator |
| Response schema là `ServerResponse` hoặc không rõ | Springdoc không biết body được tạo động trong handler | Khai báo `@Content(schema = @Schema(implementation = ...))` |
| Danh sách được mô tả thành object đơn | Thiếu `@ArraySchema` | Khai báo array schema và kiểu phần tử |
| Request body không xuất hiện | Handler dùng `bodyToMono` nhưng metadata không khai báo body | Dùng `@Operation.requestBody` với schema DTO |
| Path parameter không có trong tài liệu | Handler đọc từ `ServerRequest` | Khai báo `@Parameter(in = PATH, ...)` |
| Route metadata trỏ sai handler | Sai `beanClass`, `beanMethod`, path hoặc method | Đồng bộ annotation với RouterFunction thực tế |
| Swagger UI hiển thị sai content type | `produces`/`consumes` hoặc `@Content.mediaType` không khớp | Kiểm tra media type của route và response thực tế |
| Tài liệu có 200 nhưng runtime trả 404 | Chỉ khai báo response thành công | Bổ sung các response branch thực tế |
| Nested route sai path trong OpenAPI | Metadata chỉ ghi path con, bỏ prefix | Ghi path hiệu lực mà client gọi |
| Annotation thay đổi nhưng docs không cập nhật như mong đợi | Cache tài liệu hoặc cấu hình group khác | Tải đúng group endpoint và kiểm tra JSON trực tiếp |

## 18. Quy trình thiết kế route có hợp đồng rõ ràng

1. Khai báo route bằng `RouterFunction` và đặt handler method có tên rõ ràng.
2. Liệt kê từng cặp HTTP method/path và ánh xạ đến `beanClass`/`beanMethod`.
3. Gắn `@RouterOperation` cho một route hoặc `@RouterOperations` cho nhiều route.
4. Đặt `operationId` duy nhất, ổn định và có ý nghĩa với client generator.
5. Mô tả path/query/header parameter, request body và media type.
6. Khai báo response code và schema cụ thể; dùng `@ArraySchema` cho mảng.
7. Dùng DTO riêng cho request/response và bổ sung `@Schema` cho field quan trọng.
8. Mô tả security requirement và response lỗi theo runtime.
9. Tải `/v3/api-docs`, kiểm tra operationId, `$ref`, parameters và response.
10. Chạy OpenAPI validator cùng integration test cho tài liệu và route thực tế.

## 19. Nguyên tắc thiết kế

- Coi `RouterFunction` là cấu hình route runtime; coi `@RouterOperation` là metadata hợp đồng OpenAPI.
- Không kỳ vọng kiểu `Mono<ServerResponse>` tự cho biết schema body.
- Khai báo `operationId` ổn định và duy nhất trong document.
- Giữ `path`, `method`, `beanClass`, `beanMethod` khớp với route/handler thực tế.
- Khai báo schema DTO tường minh cho request và response.
- Dùng `@ArraySchema` cho response collection và mô tả đúng streaming media type.
- Liệt kê đầy đủ status code mà handler có thể trả.
- Giữ OpenAPI metadata đồng bộ với route DSL, validation và serialization runtime.
- Kiểm tra JSON/YAML được sinh, không chỉ nhìn giao diện Swagger UI.
- Dùng validator và integration test để phát hiện operationId trùng hoặc schema sai.

## Kết luận

Functional route trong Spring WebFlux thường không cung cấp đủ thông tin để springdoc suy luận operationId, parameter và schema body từ chữ ký handler. `@RouterOperation` mô tả một route; `@RouterOperations` gom metadata cho nhiều route. Hãy liên kết chính xác path, HTTP method, handler bean/method, đặt `operationId` ổn định và khai báo request/response schema bằng `@Schema`, `@Content` và `@ArraySchema`. Khi kiểm tra `/v3/api-docs`, cần đối chiếu metadata với route DSL và response thực tế để hợp đồng OpenAPI có thể dùng tin cậy cho Swagger UI, validation và code generation.
