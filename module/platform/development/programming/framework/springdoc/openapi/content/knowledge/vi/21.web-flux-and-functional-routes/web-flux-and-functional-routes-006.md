# `RouterFunction`, handler và lý do cần bổ sung siêu dữ liệu

Spring WebFlux cho phép xây dựng endpoint theo hai phong cách chính: annotation controller như `@RestController` và functional endpoint dựa trên `RouterFunction`. Với functional endpoint, route predicate xác định HTTP method, path và điều kiện request; một handler function nhận `ServerRequest` rồi tạo `ServerResponse`. Cách tổ chức này linh hoạt, nhưng thông tin về hợp đồng HTTP thường nằm rải rác giữa route và handler thay vì tập trung trên các annotation controller.

Springdoc hỗ trợ tài liệu hóa functional endpoint bằng `@RouterOperation` và `@RouterOperations`. Các annotation này bổ sung thông tin OpenAPI cho từng route: path, HTTP method, media type, handler method và metadata `@Operation` như summary, parameter, request body, response, schema, tag hoặc security. Nhờ vậy, tài liệu có thể mô tả rõ hợp đồng mà runtime đang thực thi.

## 1. Ba thành phần trong functional endpoint

Một functional endpoint WebFlux thường gồm ba phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `RouterFunction<ServerResponse>` | Khai báo cách ghép request predicate với handler |
| `HandlerFunction<ServerResponse>` | Xử lý request và tạo response bất đồng bộ |
| `ServerRequest` / `ServerResponse` | API đọc dữ liệu request và xây dựng response của WebFlux |

Ví dụ đơn giản:

```java
@Bean
RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .GET("/api/books/{id}", handler::findById)
        .build();
}
```

`GET("/api/books", handler::findAll)` ghép predicate GET và path với method tham chiếu trong handler. Route thứ hai ghép `/api/books/{id}` với `findById`. Bản thân các dòng route không mang các annotation như `@GetMapping`, `@PathVariable` hoặc `@RequestParam`.

## 2. Handler xử lý request và response

Handler thường là một Spring bean riêng. Nó nhận `ServerRequest`, đọc path variable/query/header/body khi cần, gọi service rồi trả về `Mono<ServerResponse>` theo hợp đồng của `HandlerFunction<ServerResponse>`.

Ví dụ handler tra cứu sách:

```java
package com.example.books;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    private final BookService bookService;

    public BookHandler(BookService bookService) {
        this.bookService = bookService;
    }

    public Mono<ServerResponse> findAll(ServerRequest request) {
        return bookService.findAll()
            .collectList()
            .flatMap(books -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(books));
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return bookService.findById(id)
            .flatMap(book -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(book))
            .switchIfEmpty(ServerResponse.notFound().build());
    }
}
```

Trong ví dụ, `findAll` trả danh sách sách dưới dạng JSON. `findById` lấy `id` từ path variable, trả JSON nếu tìm thấy và trả `404 Not Found` nếu không có bản ghi. Logic nghiệp vụ vẫn nằm ở service; handler điều phối request và định dạng response.

Một DTO response có thể là:

```java
public record BookResponse(
    Long id,
    String title
) {}
```

## 3. Vì sao functional route cần bổ sung metadata?

Với annotation controller, Springdoc thường có thể đọc nhiều thông tin trực tiếp từ method mapping và tham số:

```java
@GetMapping("/api/books/{id}")
public BookResponse findById(@PathVariable long id) { ... }
```

Từ annotation và kiểu tham số, Springdoc có cơ sở suy ra path, HTTP method, path parameter và một phần response schema.

Trong functional endpoint, route và handler tách biệt:

- Route builder chứa path và HTTP method, nhưng không có `@GetMapping`.
- Handler thường chỉ nhận một `ServerRequest`, nên reflection không thấy từng path variable hoặc query parameter dưới dạng tham số Java riêng.
- Kiểu trả về của handler thường là `Mono<ServerResponse>`, không chỉ rõ kiểu DTO thực tế được ghi vào body.
- `ServerResponse` có thể được tạo theo nhiều nhánh: JSON, văn bản, status khác nhau hoặc không có body.
- `consumes`, `produces`, header predicate và ý nghĩa nghiệp vụ có thể nằm trong route predicate hoặc logic handler.

Vì vậy, chỉ nhìn chữ ký method `Mono<ServerResponse>` không đủ để xác định response là `BookResponse`, `List<BookResponse>` hay body rỗng. Springdoc cần metadata bổ sung để biết operation phải được mô tả thế nào.

Đây là lý do `@RouterOperation` liên kết một route với mô tả OpenAPI tường minh. Annotation không thay đổi cách route chạy; nó bổ sung hợp đồng dành cho tài liệu và công cụ client.

## 4. Mô tả một route bằng `@RouterOperation`

`@RouterOperation` được đặt trên method `@Bean` trả về `RouterFunction`. Nó mô tả một operation và có thể liên kết với method trong handler bằng `beanClass` và `beanMethod`.

Ví dụ cho route lấy danh sách sách:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Bean
@RouterOperation(
    path = "/api/books",
    method = RequestMethod.GET,
    produces = {MediaType.APPLICATION_JSON_VALUE},
    beanClass = BookHandler.class,
    beanMethod = "findAll",
    operation = @Operation(
        operationId = "listBooks",
        summary = "Liệt kê sách",
        description = "Trả về danh sách sách dưới dạng JSON",
        tags = {"Books"},
        responses = @ApiResponse(
            responseCode = "200",
            description = "Danh sách sách",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                array = @ArraySchema(
                    schema = @Schema(implementation = BookResponse.class)
                )
            )
        )
    )
)
public RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .build();
}
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `path` | Path của route cần mô tả |
| `method` | HTTP method như `GET`, `POST`, `PUT`, `DELETE` |
| `produces` | Media type response được công bố |
| `consumes` | Media type request body được chấp nhận |
| `headers` | Điều kiện header nếu route có ràng buộc header |
| `beanClass` | Class chứa handler method cần liên kết |
| `beanMethod` | Tên method xử lý route |
| `operation` | Metadata OpenAPI tường minh cho operation |

Trong ví dụ, `beanClass = BookHandler.class` và `beanMethod = "findAll"` giúp Springdoc liên hệ operation với method xử lý. `@Operation` mô tả operationId, summary, tag và response schema. Response được khai báo là mảng `BookResponse`, dù kiểu trả về Java của handler là `Mono<ServerResponse>`.

## 5. Mô tả nhiều route bằng `@RouterOperations`

Một `RouterFunction` thường ghép nhiều route. Khi đó, dùng `@RouterOperations` để khai báo metadata cho từng operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.Parameter;
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
        path = "/api/books",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = BookHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "listBooks",
            summary = "Liệt kê sách",
            tags = {"Books"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Danh sách sách",
                content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    array = @ArraySchema(
                        schema = @Schema(implementation = BookResponse.class)
                    )
                )
            )
        )
    ),
    @RouterOperation(
        path = "/api/books/{id}",
        method = RequestMethod.GET,
        produces = {MediaType.APPLICATION_JSON_VALUE},
        beanClass = BookHandler.class,
        beanMethod = "findById",
        operation = @Operation(
            operationId = "getBookById",
            summary = "Lấy sách theo mã",
            tags = {"Books"},
            parameters = @Parameter(
                name = "id",
                in = ParameterIn.PATH,
                required = true,
                description = "Mã sách",
                schema = @Schema(type = "integer", format = "int64", example = "42")
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Tìm thấy sách",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = BookResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Không tìm thấy sách"
                )
            }
        )
    )
})
public RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .GET("/api/books", handler::findAll)
        .GET("/api/books/{id}", handler::findById)
        .build();
}
```

Mỗi `@RouterOperation` tương ứng với một route predicate. Cần bảo đảm `path`, `method`, `beanClass` và `beanMethod` khớp với route/handler thực tế. Nếu khai báo thiếu hoặc sai một trong các giá trị này, tài liệu có thể thiếu operation hoặc gắn metadata nhầm endpoint.

Trong ví dụ, response danh sách được biểu diễn bằng `@ArraySchema` với phần tử `BookResponse`, nhờ đó OpenAPI thể hiện đúng kiểu array và schema của từng phần tử.

## 6. Mô tả path, query và header parameter

Functional handler đọc tham số qua `ServerRequest`, vì vậy các tham số thường không thể được suy ra từ chữ ký Java như trong controller annotation.

Ví dụ handler đọc query parameter:

```java
public Mono<ServerResponse> search(ServerRequest request) {
    String keyword = request.queryParam("q").orElse("");
    int page = request.queryParam("page")
        .map(Integer::parseInt)
        .orElse(0);

    return bookService.search(keyword, page)
        .collectList()
        .flatMap(results -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(results));
}
```

Trong metadata `@Operation`, khai báo parameter tường minh:

```java
parameters = {
    @Parameter(
        name = "q",
        in = ParameterIn.QUERY,
        required = false,
        description = "Từ khóa tìm kiếm",
        schema = @Schema(type = "string", example = "spring")
    ),
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        required = false,
        description = "Số trang, bắt đầu từ 0",
        schema = @Schema(type = "integer", minimum = "0", example = "0")
    )
}
```

Các vị trí thường dùng gồm `PATH`, `QUERY`, `HEADER` và `COOKIE`. Path parameter phải được khai báo `required = true` trong OpenAPI. Tên parameter phải khớp với tên handler thực sự đọc qua `pathVariable`, `queryParam`, `headers` hoặc cookie.

Nếu route có header predicate, ví dụ chỉ khớp `X-API-VERSION=v2`, hãy mô tả điều kiện đó trong metadata phù hợp và cân nhắc khai báo header parameter để client hiểu cách gọi. Header parameter trong OpenAPI không tự tạo điều kiện định tuyến; route predicate runtime vẫn phải được khai báo riêng.

## 7. Mô tả request body và response

Vì handler thường nhận `ServerRequest`, Springdoc không thể luôn suy ra kiểu DTO từ một tham số `@RequestBody`. Khi route nhận body, hãy khai báo request body trong `@Operation` bằng annotation OpenAPI:

```java
requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    description = "Thông tin sách cần tạo",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class)
    )
)
```

Tương tự, response cần khai báo status code, media type và schema thực tế. Ví dụ một handler có thể trả `201 Created` với `BookResponse`, `400 Bad Request` với DTO lỗi và `409 Conflict` khi mã sách đã tồn tại. Những nhánh này nên được thể hiện bằng nhiều `@ApiResponse`.

Không khai báo schema chỉ dựa trên kiểu `Mono<ServerResponse>`. Hãy xem body mà handler thực sự ghi qua `bodyValue`, `body`, `bodyToMono` hoặc cơ chế serialize khác. Nếu response không có body, chỉ khai báo status và description, không thêm content giả.

## 8. Mô tả `consumes` và `produces`

Functional route có thể giới hạn media type bằng predicate hoặc kiểm tra header trong handler. Metadata `@RouterOperation` có thể mô tả media type request/response để OpenAPI thể hiện đúng hợp đồng.

Ví dụ route nhận JSON:

```java
return RouterFunctions.route()
    .POST("/api/books", RequestPredicates.contentType(MediaType.APPLICATION_JSON), handler::create)
    .build();
```

`RequestPredicates.contentType(...)` khớp với `Content-Type` của request và phù hợp với điều kiện nhận JSON (`consumes`). `RequestPredicates.accept(...)` khớp với header `Accept` và phù hợp khi chọn representation response (`produces`). Ví dụ nếu muốn route chỉ xử lý request có body JSON và client chấp nhận JSON, có thể kết hợp hai predicate:

```java
RequestPredicates.contentType(MediaType.APPLICATION_JSON)
    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON))
```

Với route nhận body JSON, cần bảo đảm handler thực sự kiểm tra/đọc body và runtime chỉ chấp nhận media type phù hợp. Trong `@RouterOperation`, khai báo `consumes = {MediaType.APPLICATION_JSON_VALUE}`; với response JSON, khai báo `produces = {MediaType.APPLICATION_JSON_VALUE}`.

Không nhầm `consumes` với `produces`:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `consumes` | Định dạng body request mà operation chấp nhận |
| `produces` | Định dạng body response mà operation trả về |

Metadata không tự cài đặt `HttpMessageReader`, `HttpMessageWriter` hoặc converter. Nếu ứng dụng khai báo `application/xml` nhưng không có codec XML phù hợp, tài liệu có thể công bố một khả năng mà runtime không thực hiện được.

## 9. Mô tả security cho functional route

`@Operation` trong `@RouterOperation` có thể chứa `security` giống operation của annotation controller:

```java
operation = @Operation(
    operationId = "listBooks",
    summary = "Liệt kê sách",
    security = @SecurityRequirement(name = "bearerAuth"),
    responses = @ApiResponse(responseCode = "200", description = "Thành công")
)
```

Scheme `bearerAuth` phải được khai báo trong `components.securitySchemes`, ví dụ bằng `@SecurityScheme`. Tên tham chiếu phải khớp chính xác với tên scheme.

Security metadata chỉ mô tả yêu cầu bảo mật trong OpenAPI. WebFlux Security vẫn phải cấu hình `SecurityWebFilterChain`, xác thực token và phân quyền request thực tế. Không xem annotation tài liệu là cơ chế chặn truy cập.

## 10. Liên kết route với handler bằng `beanClass` và `beanMethod`

Hai thuộc tính này hữu ích khi route sử dụng method reference hoặc handler function được khai báo tách biệt:

```java
@RouterOperation(
    path = "/api/books/{id}",
    method = RequestMethod.GET,
    beanClass = BookHandler.class,
    beanMethod = "findById",
    operation = @Operation(summary = "Lấy sách theo mã")
)
```

`beanClass` chỉ class chứa method handler; `beanMethod` là tên method. Cặp này giúp Springdoc tìm method tương ứng để kết nối route metadata với handler. Tên method cần đúng với method Java thực tế.

Nếu có nhiều method overload cùng tên hoặc handler được tạo bằng lambda inline, việc liên kết có thể không rõ ràng. Trong trường hợp đó, nên tách handler thành method có tên rõ ràng và khai báo metadata cụ thể cho từng route. Điều này cũng giúp unit test handler và quản lý tài liệu dễ hơn.

## 11. Khi nào dùng `@RouterOperation` và khi nào dùng customizer?

| Cơ chế | Phù hợp khi |
| --- | --- |
| `@RouterOperation` | Mô tả tường minh một functional route |
| `@RouterOperations` | Mô tả nhiều route được ghép trong một `RouterFunction` bean |
| `@Operation` lồng bên trong | Cung cấp summary, tags, parameters, request body, responses, security và metadata operation |
| `OpenApiCustomizer` | Điều chỉnh toàn bộ tài liệu sau khi Springdoc tạo OpenAPI model |

Với functional endpoint, `@RouterOperation` thường là cách trực tiếp nhất để liên kết route predicate và handler với operation. `OpenApiCustomizer` phù hợp cho thay đổi cấp tài liệu hoặc quy tắc áp dụng rộng, nhưng không nhận trực tiếp method handler như metadata gắn trên route.

Không mặc định dùng `OperationCustomizer` dành cho annotation controller để xử lý functional route. Extension point đó gắn với `HandlerMethod` của Spring MVC; functional route WebFlux không nhất thiết có `HandlerMethod` tương ứng. Dùng annotation route chuyên biệt hoặc customizer cấp OpenAPI tùy mục tiêu.

## 12. Những lỗi thường gặp khi tài liệu hóa functional endpoint

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Route chạy nhưng không xuất hiện trong OpenAPI | Chưa khai báo `@RouterOperation` hoặc cấu hình route metadata chưa được nhận diện | Gắn annotation vào bean `RouterFunction` và kiểm tra path/method |
| Operation xuất hiện nhưng response schema rỗng/chung chung | Handler trả `Mono<ServerResponse>` nên kiểu body không suy ra được | Khai báo response schema bằng `@ApiResponse` và `@Schema` |
| Path parameter không được mô tả | Handler đọc `request.pathVariable()` thay vì nhận `@PathVariable` | Khai báo `@Parameter(in = PATH, required = true)` |
| Query parameter không xuất hiện | Handler đọc `request.queryParam()` | Khai báo parameter `QUERY` trong `@Operation` |
| Metadata gắn nhầm handler | `beanClass` hoặc `beanMethod` sai | Đối chiếu class và tên method thực tế |
| Path hoặc method trong tài liệu sai | `@RouterOperation` không khớp route predicate | Đồng bộ `path`, `method` với RouterFunction |
| Request body không đúng schema | Handler đọc body thủ công nhưng thiếu `requestBody` metadata | Khai báo content, media type và DTO schema |
| Swagger UI hiển thị JSON nhưng runtime trả XML | `produces` hoặc response content không khớp codec/handler | Đồng bộ metadata với `ServerResponse` và codec thực tế |
| Security không được thể hiện | Thiếu `security` trong operation hoặc scheme chưa khai báo | Khai báo scheme và requirement khớp tên |
| Dùng `OperationCustomizer` nhưng không có handler method | Functional route không có Spring MVC `HandlerMethod` tương ứng | Dùng `@RouterOperation` hoặc `OpenApiCustomizer` phù hợp |

## 13. Kiểm tra OpenAPI được sinh từ functional route

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc tài liệu group tương ứng. Kiểm tra:

1. Từng `RouterFunction` route mong đợi có mặt trong `paths`.
2. HTTP method đúng với route predicate.
3. Path parameter được khai báo đầy đủ và bắt buộc.
4. Query/header parameter có tên, vị trí, kiểu và mô tả chính xác.
5. `requestBody.content` khớp media type và DTO handler đọc.
6. `responses` phản ánh các status code và body thực tế.
7. Schema tham chiếu đúng DTO, không chỉ hiển thị kiểu `ServerResponse`.
8. Tags, operationId và security requirement có giá trị đúng.

Đồng thời gọi thử endpoint bằng HTTP client hoặc WebTestClient. Ví dụ:

```java
webTestClient.get()
    .uri("/api/books/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(42);
```

Kiểm tra runtime và OpenAPI cùng nhau: tài liệu đúng không chứng minh handler thực thi đúng; endpoint chạy đúng cũng không chứng minh tài liệu đã mô tả đủ hợp đồng.

## 14. Checklist cho `RouterFunction` và handler

- [ ] Route predicate xác định rõ HTTP method, path và điều kiện request.
- [ ] Handler có method riêng, tên rõ ràng và xử lý `ServerRequest`/`ServerResponse` đúng hợp đồng.
- [ ] `@RouterOperation` hoặc `@RouterOperations` được gắn vào bean `RouterFunction` phù hợp.
- [ ] `path` và `method` khớp route predicate runtime.
- [ ] `beanClass` và `beanMethod` tham chiếu đúng handler.
- [ ] `@Operation` mô tả summary, operationId, tag và security khi cần.
- [ ] Path/query/header parameter được khai báo tường minh khi handler đọc trực tiếp từ `ServerRequest`.
- [ ] Request body có media type và schema đúng DTO.
- [ ] Response có đủ status code, media type và schema cho từng nhánh.
- [ ] `consumes`/`produces` khớp predicate, codec và response thực tế.
- [ ] Scheme bảo mật đã khai báo và requirement tham chiếu đúng tên.
- [ ] Đã kiểm tra `/v3/api-docs` và gọi thử route bằng WebTestClient hoặc HTTP client.

`RouterFunction` mô tả cách định tuyến, handler mô tả cách xử lý request, còn OpenAPI mô tả hợp đồng dành cho client. Vì functional endpoint không dựa vào annotation mapping trên từng tham số và kiểu trả về thường chỉ là `Mono<ServerResponse>`, nhóm cần bổ sung metadata bằng `@RouterOperation` hoặc `@RouterOperations`. Khi metadata khớp route và handler thực tế, Springdoc có thể tạo tài liệu đầy đủ về path, method, parameter, body, response và security cho ứng dụng WebFlux.
