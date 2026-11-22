# `@RouterOperation` cho một route chức năng

Spring WebFlux hỗ trợ khai báo endpoint theo hai phong cách chính. Với annotation controller, ta dùng `@RestController`, `@GetMapping` hoặc `@PostMapping`. Với functional endpoints, ta kết hợp `RouterFunction` để định tuyến request và `HandlerFunction` để xử lý request đó. Phong cách thứ hai giúp mô tả route bằng Java DSL, nhưng không có annotation mapping trên handler như controller thông thường.

`springdoc-openapi` cung cấp `@RouterOperation` để bổ sung metadata OpenAPI cho một route chức năng. Annotation thường được đặt trên method `@Bean` trả về `RouterFunction`. Nó mô tả path, HTTP method, media type và liên kết route với method xử lý trong handler bean. Thuộc tính `operation` cho phép khai báo chi tiết như operation ID, summary, parameters, request body và responses.

## 1. Functional endpoint gồm RouterFunction và HandlerFunction

Trong WebFlux functional routing, hai thành phần có trách nhiệm riêng:

- `RouterFunction<ServerResponse>` xác định request nào khớp route và handler nào được gọi.
- `HandlerFunction<ServerResponse>` nhận `ServerRequest`, thực hiện xử lý và trả về `Mono<ServerResponse>`.

Ví dụ route lấy khách hàng theo ID:

```java
@Bean
RouterFunction<ServerResponse> customerRoutes(CustomerHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/customers/{id}"),
        handler::getById
    );
}
```

Đoạn code trên tạo một route GET. Path được khai báo bằng `RequestPredicates.GET`, còn `handler::getById` là method xử lý. Không có `@GetMapping` trên handler method, vì vậy tài liệu API cần metadata riêng để mô tả route này.

## 2. `@RouterOperation` bổ sung metadata OpenAPI

Với một route chức năng, đặt `@RouterOperation` trên method `@Bean` tạo `RouterFunction`:

```java
@Configuration
class CustomerRoutes {

    @Bean
    @RouterOperation(
        path = "/api/customers/{id}",
        method = RequestMethod.GET,
        produces = MediaType.APPLICATION_JSON_VALUE,
        beanClass = CustomerHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getCustomerById",
            summary = "Lấy khách hàng theo mã",
            description = "Trả về thông tin khách hàng tương ứng với ID.",
            tags = {"Customers"},
            parameters = @Parameter(
                name = "id",
                in = ParameterIn.PATH,
                required = true,
                description = "UUID của khách hàng",
                schema = @Schema(type = "string", format = "uuid")
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Tìm thấy khách hàng",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = CustomerResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "404",
                    description = "Không tìm thấy khách hàng"
                )
            }
        )
    )
    RouterFunction<ServerResponse> getCustomerByIdRoute(CustomerHandler handler) {
        return RouterFunctions.route(
            RequestPredicates.GET("/api/customers/{id}"),
            handler::getById
        );
    }
}
```

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
| --- | --- |
| `path` | Path công khai của route, cần khớp với path trong Router DSL. |
| `method` | HTTP method của route, ví dụ `RequestMethod.GET`. |
| `produces` | Media type mà route trả về, cần khớp với response thực tế. |
| `consumes` | Media type request được route nhận, thường dùng cho POST/PUT có body. |
| `beanClass` | Lớp handler chứa method xử lý route. |
| `beanMethod` | Tên method xử lý trong handler bean. |
| `operation` | Annotation `@Operation` chứa metadata OpenAPI chi tiết. |

`@RouterOperation` mô tả route cho springdoc. Nó không tạo route runtime và không thay thế `RouterFunctions.route(...)`. Nếu annotation khai báo path `/api/customers/{id}` nhưng Router DSL đăng ký `/api/customer/{id}`, tài liệu và ứng dụng sẽ không khớp nhau.

## 3. Liên kết route với handler bean

Handler nên là một Spring bean có method xử lý rõ ràng:

```java
@Component
class CustomerHandler {

    private final CustomerService customerService;

    CustomerHandler(CustomerService customerService) {
        this.customerService = customerService;
    }

    Mono<ServerResponse> getById(ServerRequest request) {
        UUID id = UUID.fromString(request.pathVariable("id"));

        return customerService.findById(id)
            .flatMap(customer -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(CustomerResponse.from(customer)))
            .switchIfEmpty(ServerResponse.notFound().build());
    }
}
```

Trong `@RouterOperation`, `beanClass = CustomerHandler.class` và `beanMethod = "getById"` liên kết metadata với method này. Tên method phải khớp chính xác với handler thực tế. Nếu có nhiều method cùng tên hoặc handler được tạo bằng lambda không có method bean rõ ràng, việc suy luận tham số và kiểu trả về có thể khó hơn; khi đó nên khai báo rõ `@Parameter`, `@RequestBody` và response schema trong `operation`.

Ví dụ trên dùng `ServerRequest` nên Springdoc không thể suy ra kiểu `UUID` từ một tham số Java riêng như khi dùng `@PathVariable`. Vì vậy annotation mô tả `id` tường minh là cần thiết. Nó cũng khai báo response `CustomerResponse` vì handler trả `ServerResponse` tổng quát.

## 4. Path và HTTP method phải giống route runtime

Khi viết functional route, path có thể được tạo bằng một predicate trực tiếp:

```java
RequestPredicates.GET("/api/customers/{id}")
```

Hoặc được ghép từ prefix và nested route:

```java
RouterFunctions.route()
    .path("/api/customers", builder -> builder
        .GET("/{id}", handler::getById))
    .build();
```

Trong cả hai trường hợp, path hiệu lực là `/api/customers/{id}`. `@RouterOperation.path` cần ghi path đầy đủ sau khi áp dụng prefix và nesting, không chỉ ghi phần path con `/{id}`.

Tương tự, method phải khớp predicate thực tế. Nếu Router DSL dùng `POST(...)` nhưng annotation ghi `RequestMethod.GET`, tài liệu sẽ công bố operation sai. Hãy kiểm tra cả method và path sau khi ghép các route lồng nhau.

## 5. Mô tả request body và media type

Với route POST nhận JSON, khai báo `consumes` trên `@RouterOperation` và request body trong `@Operation`:

```java
@Bean
@RouterOperation(
    path = "/api/customers",
    method = RequestMethod.POST,
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE,
    beanClass = CustomerHandler.class,
    beanMethod = "create",
    operation = @Operation(
        operationId = "createCustomer",
        summary = "Tạo khách hàng",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateCustomerRequest.class)
            )
        ),
        responses = @ApiResponse(
            responseCode = "201",
            description = "Khách hàng đã được tạo",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CustomerResponse.class)
            )
        )
    )
)
RouterFunction<ServerResponse> createCustomerRoute(CustomerHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.POST("/api/customers")
            .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON)),
        handler::create
    );
}
```

Ở đây, `consumes` mô tả media type của request body; `produces` mô tả response. Predicate `contentType(...)` trong Router DSL cũng giới hạn request theo `Content-Type`. Cần giữ hai phần đồng bộ để client biết phải gửi JSON và server thực sự chấp nhận JSON.

Nếu route nhận multipart, XML hoặc nhiều media type, khai báo đúng `consumes` và `@Content` tương ứng. Không thêm media type vào OpenAPI nếu handler và codec của WebFlux chưa hỗ trợ định dạng đó.

## 6. Dùng `@RouterOperations` khi một RouterFunction chứa nhiều route

Một method `@Bean` có thể trả về RouterFunction được ghép từ nhiều operation. Khi đó một `@RouterOperation` đơn không đủ để mô tả toàn bộ route. Dùng `@RouterOperations` để khai báo từng operation:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/customers",
        method = RequestMethod.GET,
        beanClass = CustomerHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findCustomers",
            summary = "Liệt kê khách hàng",
            responses = @ApiResponse(responseCode = "200", description = "Danh sách khách hàng")
        )
    ),
    @RouterOperation(
        path = "/api/customers/{id}",
        method = RequestMethod.GET,
        beanClass = CustomerHandler.class,
        beanMethod = "getById",
        operation = @Operation(
            operationId = "getCustomerById",
            summary = "Lấy khách hàng theo mã",
            responses = @ApiResponse(responseCode = "200", description = "Khách hàng")
        )
    )
})
RouterFunction<ServerResponse> customerRoutes(CustomerHandler handler) {
    return RouterFunctions.route()
        .GET("/api/customers", handler::findAll)
        .GET("/api/customers/{id}", handler::getById)
        .build();
}
```

Mỗi `@RouterOperation` đại diện cho một cặp path và HTTP method. `@RouterOperations` là container để gắn nhiều mô tả lên cùng bean method. Nếu một bean chỉ có một route, dùng `@RouterOperation` trực tiếp sẽ đơn giản hơn. Nếu nhóm route lớn, có thể tách thành nhiều bean để metadata và cấu trúc code dễ theo dõi.

## 7. Cấu hình dependency cho WebFlux

Ứng dụng dùng Spring WebFlux cần starter tương ứng của springdoc. Với Spring Boot 3 và springdoc 2.x, ví dụ dùng UI:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Nếu chỉ cần endpoint OpenAPI JSON/YAML và không cần Swagger UI, dùng artifact `springdoc-openapi-starter-webflux-api`. Chọn phiên bản springdoc tương thích với Spring Boot và tránh trộn starter WebFlux với starter WebMVC trong cùng ứng dụng nếu không có kiến trúc đặc biệt được hỗ trợ.

Với Spring Boot 2 và springdoc 1.x, tên artifact và cách cấu hình khác. Hãy theo tài liệu đúng nhánh lớn đang dùng thay vì sao chép dependency 2.x vào dự án cũ.

## 8. Kiểm tra OpenAPI document được sinh ra

Sau khi khởi động ứng dụng, mở `/v3/api-docs` hoặc endpoint đã cấu hình. Với route GET ở ví dụ đầu, document cần có cấu trúc tương tự:

```yaml
paths:
  /api/customers/{id}:
    get:
      operationId: getCustomerById
      summary: Lấy khách hàng theo mã
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy khách hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CustomerResponse'
        '404':
          description: Không tìm thấy khách hàng
```

Tên component và cách springdoc tạo `$ref` có thể khác theo phiên bản hoặc cấu hình. Các điểm cần xác nhận:

- Path và method trong `paths` khớp Router DSL.
- `operationId` duy nhất trong document.
- Path parameter `id` có `required: true` và schema UUID.
- Response code và schema khớp hành vi handler.
- `produces` và `consumes` phản ánh media type thực tế.
- Không có operation trùng hoặc thiếu do route được mô tả nhiều lần.

## 9. Kiểm tra runtime và tài liệu riêng biệt

`@RouterOperation` chỉ mô tả hợp đồng; nó không xác nhận route runtime đã được đăng ký đúng. Cần kiểm tra cả request thực tế:

1. Gọi `GET /api/customers/{id}` với ID tồn tại và xác nhận response `200` cùng JSON body.
2. Gọi với ID không tồn tại và xác nhận response `404` như tài liệu.
3. Gửi sai định dạng ID và xác nhận ứng dụng trả lỗi đầu vào đã được thiết kế.
4. Gọi `/v3/api-docs` và xác nhận operation xuất hiện với path, method, parameter và response đúng.
5. Nếu dùng Swagger UI, thử **Try it out** và so sánh request thực tế với route.

Ví dụ kiểm tra document với `WebTestClient` trong ứng dụng WebFlux:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerOpenApiTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void documentsFunctionalCustomerRoute() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/customers/{id}'].get.operationId")
            .isEqualTo("getCustomerById");
    }
}
```

Test này kiểm tra document. Nên có test riêng cho endpoint `/api/customers/{id}` để xác nhận handler và RouterFunction xử lý request thật.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Route chạy được nhưng không xuất hiện trong OpenAPI | Thiếu `@RouterOperation`, annotation đặt sai bean method hoặc springdoc chưa nhận functional route | Gắn annotation lên method `@Bean` trả RouterFunction và kiểm tra `/v3/api-docs`. |
| OpenAPI có path khác route runtime | `path` trong annotation không khớp Router DSL hoặc quên prefix/nested path | Ghi path hiệu lực đầy đủ và đối chiếu request thực tế. |
| Operation dùng sai HTTP method | `method` trong annotation khác predicate GET/POST/PUT/DELETE | Đồng bộ `RequestMethod` với Router DSL. |
| Parameter path không được mô tả | Handler chỉ nhận `ServerRequest` nên kiểu path variable không suy ra như controller | Khai báo `@Parameter` tường minh trong `@Operation`. |
| Response schema là `ServerResponse` hoặc không rõ | Handler trả kiểu bao ngoài tổng quát | Khai báo response content và `@Schema(implementation = ...)`. |
| Swagger UI hiển thị sai media type | `consumes`/`produces` khác codec hoặc predicate runtime | Đồng bộ annotation, predicate và `ServerResponse.contentType(...)`. |
| Nhiều route trong cùng bean chỉ có một operation | Dùng `@RouterOperation` đơn cho RouterFunction tổng hợp | Dùng `@RouterOperations` hoặc tách mỗi route thành bean riêng. |
| Operation bị trùng | Cùng path/method được phát hiện từ nhiều cấu hình hoặc khai báo lặp | Kiểm tra các annotation và group customizer. |
| `beanMethod` không được resolve | Tên method sai, handler class sai hoặc method overload gây mơ hồ | Kiểm tra `beanClass`, tên method và dùng method handler rõ ràng. |
| `/v3/api-docs` trả lỗi khi phân giải route | Dependency WebFlux/WebMVC hoặc springdoc không tương thích | Dùng đúng starter WebFlux và phiên bản tương thích Spring Boot. |

## 11. Nguyên tắc áp dụng

- Dùng `@RouterOperation` trên method `@Bean` trả về một RouterFunction cần mô tả.
- Đặt `path` và `method` trùng với route thực tế trong Router DSL.
- Liên kết đúng handler bằng `beanClass` và `beanMethod`.
- Dùng `operation` để khai báo operation ID, summary, tag, parameter, request body và response.
- Khai báo path parameter tường minh khi handler nhận `ServerRequest`.
- Mô tả response schema cụ thể thay vì để kiểu `ServerResponse` tổng quát quyết định hợp đồng.
- Dùng `consumes` và `produces` đúng với predicate, codec và response content type.
- Dùng `@RouterOperations` khi một bean method công bố nhiều route.
- Cài đúng starter WebFlux và phiên bản springdoc tương thích.
- Kiểm tra cả `/v3/api-docs` lẫn request runtime bằng `WebTestClient`.

`@RouterOperation` kết nối route được khai báo bằng WebFlux functional DSL với metadata của OpenAPI. Khi path, method, handler và operation metadata khớp nhau, springdoc có thể công bố một hợp đồng rõ ràng cho route dù handler không dùng annotation controller. Đặc tả sinh ra vẫn cần được kiểm tra cùng request runtime để bảo đảm client nhìn thấy đúng endpoint, tham số, media type và response mà ứng dụng thực sự cung cấp.

## Tài liệu tham khảo

- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Springdoc OpenAPI FAQ – Functional Endpoints và `@RouterOperation`](https://springdoc.org/faq.html)
- [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework – `RouterFunction`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunction.html)
- [Swagger Annotations – `@Operation` và `@ApiResponse`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
