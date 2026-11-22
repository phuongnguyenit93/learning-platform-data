# Tài liệu hóa một API CRUD với hợp đồng thành công và lỗi đầy đủ

Một API CRUD chỉ được tài liệu hóa tốt khi người tích hợp biết cách tạo, đọc, cập nhật và xóa tài nguyên; đồng thời biết mỗi thao tác có thể trả về status code nào, body có cấu trúc gì và lỗi được biểu diễn ra sao. Chỉ ghi summary cho controller hoặc để Springdoc tự suy luận schema từ DTO thường chưa đủ cho một hợp đồng ổn định.

Bài thực hành này xây dựng API quản lý sản phẩm bằng Spring Boot và springdoc-openapi. Ta sẽ định nghĩa request DTO, response DTO, validation, error model, controller CRUD, exception handler và OpenAPI annotations. Sau đó, kiểm tra JSON/YAML được sinh ra, gọi thử endpoint và viết integration test để bảo đảm tài liệu khớp với hành vi HTTP thực tế.

## 1. Mục tiêu của bài thực hành

Sau khi hoàn thành, một người tích hợp API có thể:

- Tìm operation tạo, liệt kê, xem chi tiết, cập nhật và xóa sản phẩm.
- Biết path, HTTP method, query/path parameter và request body của từng operation.
- Biết trường nào bắt buộc, kiểu dữ liệu, giới hạn và ví dụ hợp lệ.
- Biết response thành công có status code và schema nào.
- Biết lỗi validation, không tìm thấy tài nguyên, xung đột dữ liệu và lỗi hệ thống có cấu trúc ra sao.
- Dùng Swagger UI hoặc HTTP client để thử request.
- Kiểm tra OpenAPI JSON/YAML và tự động xác minh hợp đồng trong CI.

Phạm vi ví dụ là Spring MVC với REST controller. Nếu dự án dùng Spring WebFlux, thay starter MVC bằng starter WebFlux tương ứng và giữ nguyên nguyên tắc mô tả hợp đồng.

## 2. Bối cảnh API quản lý sản phẩm

API có tài nguyên Product với các thuộc tính:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| id | UUID | Định danh sản phẩm do server tạo |
| sku | String | Mã sản phẩm duy nhất |
| name | String | Tên sản phẩm |
| description | String | Mô tả, có thể để trống |
| price | BigDecimal | Giá không âm |
| category | String | Nhóm sản phẩm |
| createdAt | Instant | Thời điểm tạo |
| updatedAt | Instant | Thời điểm cập nhật gần nhất |

Client không được tự gửi id, createdAt hoặc updatedAt khi tạo sản phẩm. Những giá trị này do server quản lý.

Các operation:

| Method | Path | Chức năng | Thành công |
|---|---|---|---|
| POST | /api/products | Tạo sản phẩm | 201 Created |
| GET | /api/products | Liệt kê sản phẩm | 200 OK |
| GET | /api/products/{id} | Xem chi tiết | 200 OK |
| PUT | /api/products/{id} | Thay thế thông tin sản phẩm | 200 OK |
| DELETE | /api/products/{id} | Xóa sản phẩm | 204 No Content |

Các lỗi được mô tả thống nhất:

| Status | Mã lỗi ví dụ | Trường hợp |
|---|---|---|
| 400 | VALIDATION_FAILED | Request thiếu trường hoặc vi phạm ràng buộc |
| 404 | PRODUCT_NOT_FOUND | Không có sản phẩm tương ứng |
| 409 | SKU_ALREADY_EXISTS | SKU đã được dùng bởi sản phẩm khác |
| 500 | INTERNAL_ERROR | Lỗi không dự kiến ở server |

Status code và mã lỗi là một phần của hợp đồng. Không trả 200 cho mọi trường hợp rồi đặt thông tin lỗi trong body, vì client sẽ khó xử lý đúng theo HTTP semantics.

## 3. Cấu trúc package gợi ý

Có thể tổ chức code như sau:

~~~text
com.acme.catalog
├── CatalogApplication.java
├── config
│   └── OpenApiConfiguration.java
├── product
│   ├── ProductController.java
│   ├── ProductService.java
│   ├── ProductRepository.java
│   ├── Product.java
│   ├── dto
│   │   ├── CreateProductRequest.java
│   │   ├── UpdateProductRequest.java
│   │   ├── ProductResponse.java
│   │   └── ProductPageResponse.java
│   └── error
│       ├── ProductNotFoundException.java
│       └── DuplicateSkuException.java
└── common
    ├── ErrorResponse.java
    ├── FieldViolation.java
    └── ApiExceptionHandler.java
~~~

Tách DTO khỏi entity giúp hợp đồng HTTP không phụ thuộc trực tiếp vào cấu trúc database. Khi thay đổi entity hoặc quan hệ persistence, API response không bị đổi ngoài ý muốn.

## 4. Thêm dependency Springdoc và validation

Với Spring MVC, dependency chính thường là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Thêm Bean Validation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Chọn version springdoc tương thích với Spring Boot của dự án. Nhánh Spring Boot 3 sử dụng springdoc 2.x; nhánh Spring Boot 4 sử dụng springdoc 3.x. Không chọn version chỉ dựa trên số mới nhất mà bỏ qua compatibility matrix.

Springdoc runtime đọc controller, DTO, Jackson metadata và validation annotations để tạo OpenAPI document. Dependency validation giúp các constraint như @NotBlank, @PositiveOrZero và @Size được thực thi khi request được kiểm tra.

## 5. Xác định hợp đồng trước khi viết controller

Trước khi thêm annotation, hãy quyết định rõ:

- Request create có những trường nào?
- Update là thay thế toàn bộ tài nguyên hay chỉ cập nhật một phần?
- ID do client hay server tạo?
- SKU có duy nhất không?
- Giá có được âm không?
- Khi không tìm thấy tài nguyên, trả 404 hay một response khác?
- Khi SKU bị trùng, trả 409 hay 400?
- Delete trả 204 không có body hay 200 có body xác nhận?

Trong bài này, POST tạo tài nguyên mới và trả 201 cùng Location header. PUT thay thế toàn bộ các trường có thể chỉnh sửa. DELETE trả 204 và không có response body. Những lựa chọn này sẽ được dùng nhất quán trong code, tài liệu và test.

## 6. Thiết kế ErrorResponse dùng chung

Lỗi nên có cấu trúc ổn định để client có thể xử lý mà không cần phân tích câu chữ tự do:

~~~java
public class ErrorResponse {

    @Schema(example = "2026-11-20T10:15:30Z")
    private Instant timestamp;

    @Schema(example = "400")
    private int status;

    @Schema(example = "VALIDATION_FAILED")
    private String code;

    @Schema(example = "Request contains invalid fields")
    private String message;

    @Schema(example = "/api/products")
    private String path;

    private List<FieldViolation> fieldErrors;

    // constructors, getters and setters
}
~~~

FieldViolation mô tả lỗi ở từng trường:

~~~java
public class FieldViolation {

    @Schema(example = "price")
    private String field;

    @Schema(example = "must be greater than or equal to 0")
    private String message;

    // constructors, getters and setters
}
~~~

Ví dụ response validation:

~~~json
{
  "timestamp": "2026-11-20T10:15:30Z",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "path": "/api/products",
  "fieldErrors": [
    {
      "field": "name",
      "message": "must not be blank"
    },
    {
      "field": "price",
      "message": "must be greater than or equal to 0"
    }
  ]
}
~~~

Không đưa stack trace, SQL, tên bảng hoặc thông tin bí mật vào ErrorResponse. Message nên an toàn và đủ hữu ích cho client; chi tiết kỹ thuật được ghi trong log nội bộ với correlation ID nếu cần.

## 7. Tạo request DTO cho thao tác create

CreateProductRequest chỉ chứa các trường client được phép gửi:

~~~java
public class CreateProductRequest {

    @NotBlank
    @Size(max = 100)
    @Schema(
        description = "Tên sản phẩm",
        example = "Mechanical Keyboard K8"
    )
    private String name;

    @NotBlank
    @Size(max = 40)
    @Schema(
        description = "Mã SKU duy nhất",
        example = "KB-K8-BLK"
    )
    private String sku;

    @Size(max = 2000)
    @Schema(
        description = "Mô tả sản phẩm",
        example = "Bàn phím cơ layout 75 phần trăm"
    )
    private String description;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Schema(
        description = "Giá bán, không được âm",
        example = "129.90"
    )
    private BigDecimal price;

    @NotBlank
    @Size(max = 80)
    @Schema(
        description = "Danh mục sản phẩm",
        example = "Accessories"
    )
    private String category;

    // constructors, getters and setters
}
~~~

Các annotation có hai vai trò liên quan nhưng khác nhau:

- Bean Validation kiểm tra dữ liệu runtime khi controller nhận request có @Valid.
- Swagger annotations bổ sung mô tả, ví dụ và metadata OpenAPI.

Springdoc có thể suy luận một số ràng buộc từ Bean Validation, nhưng hãy mở JSON sinh ra để xác nhận required, minLength, maxLength và minimum đúng như mong đợi.

## 8. Tạo request DTO cho thao tác update

PUT được dùng như thao tác thay thế các trường chỉnh sửa của tài nguyên:

~~~java
public class UpdateProductRequest {

    @NotBlank
    @Size(max = 100)
    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard K8")
    private String name;

    @NotBlank
    @Size(max = 40)
    @Schema(description = "Mã SKU duy nhất", example = "KB-K8-WHT")
    private String sku;

    @Size(max = 2000)
    @Schema(description = "Mô tả sản phẩm")
    private String description;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Schema(description = "Giá bán", example = "139.90")
    private BigDecimal price;

    @NotBlank
    @Size(max = 80)
    @Schema(description = "Danh mục", example = "Accessories")
    private String category;

    // constructors, getters and setters
}
~~~

Trong hợp đồng này, các trường bắt buộc phải xuất hiện trong PUT. Nếu muốn hỗ trợ cập nhật từng phần, hãy thiết kế PATCH riêng và mô tả rõ cách xử lý trường bị thiếu, trường null và giá trị mới.

Không dùng cùng một DTO cho POST, PUT và response chỉ để giảm số class. Create request không nên cho client gửi id hoặc timestamp do server quản lý; response lại cần công bố những trường đó.

## 9. Tạo ProductResponse

Response chứa dữ liệu server trả về:

~~~java
public class ProductResponse {

    @Schema(example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001")
    private UUID id;

    @Schema(example = "KB-K8-BLK")
    private String sku;

    @Schema(example = "Mechanical Keyboard K8")
    private String name;

    @Schema(example = "Bàn phím cơ layout 75 phần trăm")
    private String description;

    @Schema(example = "129.90")
    private BigDecimal price;

    @Schema(example = "Accessories")
    private String category;

    @Schema(example = "2026-11-20T10:15:30Z")
    private Instant createdAt;

    @Schema(example = "2026-11-20T10:15:30Z")
    private Instant updatedAt;

    // constructors, getters and setters
}
~~~

Response schema cần phản ánh chính xác dữ liệu serialize. Nếu Jackson bỏ qua null, đổi tên field hoặc dùng JsonView, kiểm tra OpenAPI document và response JSON thực tế để bảo đảm hai bên khớp nhau.

## 10. Tạo response cho danh sách có phân trang

Để hợp đồng dễ đọc và không phụ thuộc trực tiếp vào Page implementation, có thể dùng DTO riêng:

~~~java
public class ProductPageResponse {

    private List<ProductResponse> items;

    @Schema(example = "0")
    private int page;

    @Schema(example = "20")
    private int size;

    @Schema(example = "125")
    private long totalElements;

    @Schema(example = "7")
    private int totalPages;

    // constructors, getters and setters
}
~~~

Query parameters:

- category: lọc theo danh mục, không bắt buộc.
- page: chỉ số trang bắt đầu từ 0, mặc định 0.
- size: số phần tử mỗi trang, mặc định 20.

Việc dùng DTO phân trang giúp client không phụ thuộc vào cấu trúc nội bộ của Spring Data Page.

## 11. Định nghĩa domain exception

Service có thể ném exception theo ngữ nghĩa nghiệp vụ:

~~~java
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(UUID id) {
        super("Product not found: " + id);
    }
}

public class DuplicateSkuException extends RuntimeException {
    public DuplicateSkuException(String sku) {
        super("SKU already exists: " + sku);
    }
}
~~~

Không trả trực tiếp message nội bộ từ exception ra client nếu message có thể chứa dữ liệu nhạy cảm. Exception handler sẽ chuyển chúng thành error code và message ổn định.

## 12. Khai báo service contract

Controller không nên chứa logic persistence. Service chịu trách nhiệm nghiệp vụ:

~~~java
public interface ProductService {

    ProductResponse create(CreateProductRequest request);

    ProductPageResponse findAll(String category, int page, int size);

    ProductResponse findById(UUID id);

    ProductResponse update(UUID id, UpdateProductRequest request);

    void delete(UUID id);
}
~~~

Triển khai service phải kiểm tra:

- SKU không bị trùng khi tạo.
- SKU mới không trùng với sản phẩm khác khi cập nhật.
- Sản phẩm tồn tại trước khi xem, sửa hoặc xóa.
- Giá và dữ liệu đầu vào hợp lệ.
- Việc xóa tuân theo chính sách nghiệp vụ.

Các quy tắc này phải được kiểm tra ở server, không chỉ dựa vào schema mà MCP hoặc Swagger UI hiển thị.

## 13. Tạo controller và tag chung

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(
    name = "Products",
    description = "Tạo, tra cứu, cập nhật và xóa sản phẩm"
)
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }
}
~~~

@Tag nhóm các operation liên quan trong Swagger UI. Description nên giải thích phạm vi nghiệp vụ, không chỉ lặp lại tên class.

Mỗi method cần operationId ổn định. Tên method Java có thể được đổi khi refactor, nhưng operationId là một phần metadata mà code generator và consumer có thể dựa vào.

## 14. Tài liệu hóa operation tạo sản phẩm

POST /api/products trả 201 Created, response là ProductResponse. Các lỗi phổ biến gồm 400 khi request không hợp lệ và 409 khi SKU đã tồn tại.

~~~java
@PostMapping
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm",
    description = "Tạo sản phẩm mới. Server tự sinh ID và thời điểm tạo."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Sản phẩm được tạo",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "SKU đã tồn tại",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ResponseEntity<ProductResponse> create(
        @Valid
        @org.springframework.web.bind.annotation.RequestBody
        CreateProductRequest request) {

    ProductResponse created = productService.create(request);
    URI location = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .path("/{id}")
        .buildAndExpand(created.getId())
        .toUri();

    return ResponseEntity.created(location).body(created);
}
~~~

Điểm cần chú ý:

- @Valid kích hoạt Bean Validation trên request DTO.
- 201 thể hiện tài nguyên mới đã được tạo.
- Location trỏ tới URL của tài nguyên vừa tạo.
- Content schema mô tả response body.
- ErrorResponse được dùng nhất quán cho 400 và 409.

## 15. Tài liệu hóa operation liệt kê sản phẩm

GET /api/products hỗ trợ lọc và phân trang:

~~~java
@GetMapping
@Operation(
    operationId = "listProducts",
    summary = "Liệt kê sản phẩm",
    description = "Trả danh sách sản phẩm theo danh mục và phân trang."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Danh sách sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductPageResponse.class)
        )
    )
})
public ProductPageResponse list(
        @Parameter(
            description = "Lọc theo danh mục",
            example = "Accessories"
        )
        @RequestParam(required = false) String category,
        @Parameter(
            description = "Trang bắt đầu từ 0",
            example = "0"
        )
        @RequestParam(defaultValue = "0") int page,
        @Parameter(
            description = "Số phần tử mỗi trang",
            example = "20"
        )
        @RequestParam(defaultValue = "20") int size) {

    return productService.findAll(category, page, size);
}
~~~

Default value và description giúp client hiểu cách gọi. Nếu page hoặc size có giới hạn, hãy xác minh giới hạn đó được kiểm tra ở runtime và mô tả bằng @Parameter hoặc validation tương ứng.

## 16. Tài liệu hóa operation xem chi tiết

GET /api/products/{id} trả 200 nếu có sản phẩm và 404 nếu không tìm thấy:

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getProductById",
    summary = "Xem chi tiết sản phẩm",
    description = "Tra cứu một sản phẩm theo UUID."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ProductResponse getById(
        @Parameter(
            description = "UUID của sản phẩm",
            example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001"
        )
        @PathVariable UUID id) {

    return productService.findById(id);
}
~~~

Parameter path phải được mô tả đúng kiểu UUID. Nếu dùng String trong controller nhưng thực tế chỉ nhận UUID, cân nhắc dùng UUID để Spring và OpenAPI cùng biểu diễn kiểu dữ liệu.

## 17. Tài liệu hóa operation cập nhật

PUT /api/products/{id} thay thế các trường chỉnh sửa và trả 200:

~~~java
@PutMapping("/{id}")
@Operation(
    operationId = "updateProduct",
    summary = "Cập nhật sản phẩm",
    description = "Thay thế các trường có thể chỉnh sửa của sản phẩm."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Sản phẩm đã được cập nhật",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "SKU đã được sản phẩm khác sử dụng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ProductResponse update(
        @PathVariable UUID id,
        @Valid
        @org.springframework.web.bind.annotation.RequestBody
        UpdateProductRequest request) {

    return productService.update(id, request);
}
~~~

PUT thường biểu thị việc thay thế representation theo hợp đồng của API. Nếu chỉ cập nhật một vài trường, hãy thiết kế PATCH hoặc một operation riêng, đồng thời mô tả semantics của trường bị thiếu và trường null.

## 18. Tài liệu hóa operation xóa

DELETE /api/products/{id} trả 204 No Content nếu xóa thành công:

~~~java
@DeleteMapping("/{id}")
@Operation(
    operationId = "deleteProduct",
    summary = "Xóa sản phẩm",
    description = "Xóa sản phẩm theo UUID. Response thành công không có body."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "204",
        description = "Sản phẩm đã được xóa",
        content = @Content
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ResponseEntity<Void> delete(@PathVariable UUID id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

204 không có response body. Không mô tả ErrorResponse cho status 204 và không trả JSON rỗng nếu hợp đồng đã chọn No Content.

## 19. Ghép các method vào controller hoàn chỉnh

Các method ở trên thuộc cùng ProductController. Phần khai báo class và constructor:

~~~java
@RestController
@RequestMapping("/api/products")
@ApiResponse(
    responseCode = "500",
    description = "Lỗi không dự kiến ở server",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ErrorResponse.class)
    )
)
@Tag(
    name = "Products",
    description = "Tạo, tra cứu, cập nhật và xóa sản phẩm"
)
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    // create, list, getById, update, delete
}
~~~

Khi ghép code, đặt các method trong cùng class và import đúng annotation. Với RequestBody, ví dụ dùng fully qualified Spring annotation để tránh nhầm với OpenAPI RequestBody annotation.

## 20. Tạo ControllerAdvice ánh xạ lỗi validation

Spring MVC ném MethodArgumentNotValidException khi request body không vượt qua Bean Validation và controller dùng @Valid.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<FieldViolation> violations = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldViolation(
                error.getField(),
                error.getDefaultMessage()
            ))
            .toList();

        ErrorResponse body = new ErrorResponse(
            Instant.now(),
            400,
            "VALIDATION_FAILED",
            "Request contains invalid fields",
            request.getRequestURI(),
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Nếu dự án dùng Java version chưa hỗ trợ Stream.toList(), thay bằng Collectors.toList(). Kiểu trả về và nội dung response phải được giữ nhất quán với ErrorResponse schema.

## 21. Ánh xạ lỗi không tìm thấy và xung đột

Bổ sung handler cho domain exception:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ErrorResponse> handleNotFound(
        ProductNotFoundException ex,
        HttpServletRequest request) {

    ErrorResponse body = new ErrorResponse(
        Instant.now(),
        404,
        "PRODUCT_NOT_FOUND",
        "Product was not found",
        request.getRequestURI(),
        List.of()
    );

    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}

@ExceptionHandler(DuplicateSkuException.class)
public ResponseEntity<ErrorResponse> handleDuplicateSku(
        DuplicateSkuException ex,
        HttpServletRequest request) {

    ErrorResponse body = new ErrorResponse(
        Instant.now(),
        409,
        "SKU_ALREADY_EXISTS",
        "SKU is already used by another product",
        request.getRequestURI(),
        List.of()
    );

    return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
}
~~~

Không trả nguyên văn exception message nếu nó chứa thông tin database hoặc dữ liệu nội bộ. Client cần mã lỗi ổn định hơn là câu chữ phụ thuộc implementation.

## 22. Ánh xạ lỗi không dự kiến

Có thể có handler dự phòng cho lỗi chưa được phân loại:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<ErrorResponse> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    log.error("Unhandled API error at {}", request.getRequestURI(), ex);

    ErrorResponse body = new ErrorResponse(
        Instant.now(),
        500,
        "INTERNAL_ERROR",
        "An unexpected error occurred",
        request.getRequestURI(),
        List.of()
    );

    return ResponseEntity.internalServerError().body(body);
}
~~~

Handler tổng quát phải đứng sau các handler cụ thể trong logic phân giải exception. Log nội bộ có thể chứa stack trace; response công khai không nên có.

## 23. Mô tả ErrorResponse trong OpenAPI

Có hai cách phổ biến:

1. Khai báo @ApiResponse cho từng operation, dùng schema ErrorResponse.
2. Dùng cơ chế customizer hoặc cấu hình response dùng chung nếu tổ chức có quy ước chuẩn.

Trong bài thực hành, khai báo rõ tại operation để người đọc thấy ngay các status quan trọng. Ví dụ GET /api/products/{id} có 200 và 404; POST có 201, 400 và 409. Lỗi 500 dùng @ApiResponse ở cấp controller để áp dụng response chung cho các operation của controller; method-level response vẫn khai báo các status riêng. Nếu một operation có hành vi lỗi 500 khác, hãy khai báo lại ở method và kiểm tra kết quả sau khi Springdoc hợp nhất metadata.

Springdoc có khả năng đọc thông tin từ ControllerAdvice để xây dựng generic error responses. Tuy nhiên, đừng dựa vào việc framework tự thêm mọi lỗi cho mọi operation mà không kiểm tra JSON cuối cùng. Nếu hợp đồng yêu cầu một status cụ thể, hãy mô tả rõ và xác minh nó xuất hiện trong operation tương ứng.

## 24. Cấu hình thông tin API và security scheme

Có thể khai báo metadata toàn cục:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product Catalog API",
        version = "1.0.0",
        description = "API quản lý danh mục sản phẩm"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

Nếu các operation yêu cầu Bearer token, có thể áp dụng @SecurityRequirement trên controller hoặc từng operation:

~~~java
@SecurityRequirement(name = "bearerAuth")
@RestController
@RequestMapping("/api/products")
public class ProductController {
}
~~~

Security scheme chỉ mô tả cách xác thực trong OpenAPI. Spring Security mới thực thi kiểm tra token và quyền. Nếu một số operation public, đặt security requirement theo operation thay vì áp dụng toàn controller.

## 25. Thêm example cho request và response

Schema example giúp người tích hợp hiểu cách gửi dữ liệu:

~~~json
{
  "name": "Mechanical Keyboard K8",
  "sku": "KB-K8-BLK",
  "description": "Bàn phím cơ layout 75 phần trăm",
  "price": 129.90,
  "category": "Accessories"
}
~~~

Response:

~~~json
{
  "id": "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001",
  "name": "Mechanical Keyboard K8",
  "sku": "KB-K8-BLK",
  "description": "Bàn phím cơ layout 75 phần trăm",
  "price": 129.90,
  "category": "Accessories",
  "createdAt": "2026-11-20T10:15:30Z",
  "updatedAt": "2026-11-20T10:15:30Z"
}
~~~

Example phải khớp schema và validation. Nếu example có price âm trong khi schema đặt minimum 0, tài liệu sẽ gây nhầm lẫn dù code vẫn biên dịch.

Có thể dùng @Schema(example = "...") ở field hoặc @ExampleObject trong @Content nếu cần nhiều ví dụ theo từng operation. Khi có ví dụ phức tạp, kiểm tra YAML/JSON cuối cùng để xác nhận example được gắn vào đúng media type.

## 26. Kiểm tra hợp đồng status code và response body

Trước khi chạy ứng dụng, rà soát bảng sau:

| Operation | Thành công | Lỗi cần mô tả | Body lỗi |
|---|---|---|---|
| POST /api/products | 201 ProductResponse | 400, 409 | ErrorResponse |
| GET /api/products | 200 ProductPageResponse | 500 | ErrorResponse |
| GET /api/products/{id} | 200 ProductResponse | 404 | ErrorResponse |
| PUT /api/products/{id} | 200 ProductResponse | 400, 404, 409 | ErrorResponse |
| DELETE /api/products/{id} | 204 không body | 404 | ErrorResponse |

Không cần khai báo mọi status code có thể tồn tại trong mạng. Chọn những response mà API cam kết hoặc có xử lý có chủ đích. Nếu gateway có thể trả 502 hoặc 504, có thể mô tả ở tài liệu gateway hoặc tầng API nếu đó là một phần hợp đồng công khai.

## 27. Chạy ứng dụng và kiểm tra Swagger UI

Khởi động ứng dụng theo cấu hình dự án:

~~~bash
./mvnw spring-boot:run
~~~

Hoặc chạy:

~~~bash
./gradlew bootRun
~~~

Mở Swagger UI:

~~~text
http://localhost:8080/swagger-ui.html
~~~

OpenAPI JSON mặc định:

~~~text
http://localhost:8080/v3/api-docs
~~~

OpenAPI YAML:

~~~text
http://localhost:8080/v3/api-docs.yaml
~~~

Đường dẫn có thể thay đổi nếu ứng dụng dùng context path hoặc cấu hình springdoc.api-docs.path và springdoc.swagger-ui.path.

## 28. Thử các request CRUD bằng HTTP client

Tạo sản phẩm:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mechanical Keyboard K8",
    "sku": "KB-K8-BLK",
    "description": "Bàn phím cơ layout 75 phần trăm",
    "price": 129.90,
    "category": "Accessories"
  }'
~~~

Liệt kê:

~~~bash
curl -i "http://localhost:8080/api/products?category=Accessories&page=0&size=20"
~~~

Xem chi tiết:

~~~bash
curl -i http://localhost:8080/api/products/4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001
~~~

Cập nhật:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mechanical Keyboard K8 White",
    "sku": "KB-K8-WHT",
    "description": "Bàn phím cơ màu trắng",
    "price": 139.90,
    "category": "Accessories"
  }'
~~~

Xóa:

~~~bash
curl -i -X DELETE http://localhost:8080/api/products/4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001
~~~

Kết quả mong đợi lần lượt là 201, 200, 200, 200 và 204 nếu các thao tác thành công.

## 29. Thử các trường hợp lỗi

Request thiếu name hoặc có price âm:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "",
    "sku": "KB-BAD",
    "price": -10,
    "category": "Accessories"
  }'
~~~

Kết quả mong đợi: 400 với ErrorResponse và fieldErrors chỉ ra name hoặc price.

Tra cứu ID không tồn tại:

~~~bash
curl -i http://localhost:8080/api/products/00000000-0000-0000-0000-000000000000
~~~

Kết quả mong đợi: 404 với code PRODUCT_NOT_FOUND.

Tạo hai sản phẩm có cùng SKU:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Duplicate SKU item",
    "sku": "KB-K8-BLK",
    "price": 99.00,
    "category": "Accessories"
  }'
~~~

Kết quả mong đợi: 409 với code SKU_ALREADY_EXISTS nếu SKU đã được sử dụng.

Đối chiếu response thực tế với schema ErrorResponse. Nếu một handler trả body khác cấu trúc, tài liệu và runtime đang không nhất quán.

## 30. Kiểm tra OpenAPI JSON bằng jq

Lưu document:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Kiểm tra metadata:

~~~bash
jq '{openapi, info, pathCount: (.paths | length)}' target/openapi.json
~~~

Liệt kê path:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Kiểm tra response của POST:

~~~bash
jq '.paths["/api/products"].post.responses' target/openapi.json
~~~

Kiểm tra response của GET theo ID:

~~~bash
jq '.paths["/api/products/{id}"].get.responses' target/openapi.json
~~~

Document phải có status 201 cho create, 200 cho read/update, 204 cho delete và các lỗi đã công bố. Kiểm tra cả content schema, không chỉ kiểm tra status key tồn tại.

## 31. Kiểm tra YAML và Swagger UI

Lấy YAML:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  -o target/openapi.yaml
~~~

Dùng YAML parser hoặc OpenAPI validator để xác minh file hợp lệ. Không đổi phần mở rộng JSON thành YAML.

Trong Swagger UI, kiểm tra:

- Có tag Products.
- Có đủ năm operation CRUD.
- Path parameter id có kiểu UUID.
- Query parameter category, page và size có mô tả/default phù hợp.
- Request body hiển thị các trường và ràng buộc.
- Response 201/200/204 có đúng schema.
- Error response 400/404/409/500 có ErrorResponse.
- Authorize xuất hiện nếu API có security scheme.

Swagger UI là cách quan sát trực quan; OpenAPI JSON/YAML mới là artifact hợp đồng để validator, code generator và CI xử lý.

## 32. Viết integration test cho HTTP contract

Có thể dùng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createProductReturns201AndLocation() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Keyboard K8",
                      "sku": "KB-K8-BLK",
                      "price": 129.90,
                      "category": "Accessories"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.id").exists())
            .andExpect(jsonPath("$.sku").value("KB-K8-BLK"));
    }

    @Test
    void invalidCreateRequestReturns400() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "",
                      "sku": "KB-BAD",
                      "price": -10,
                      "category": "Accessories"
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.fieldErrors").isArray());
    }
}
~~~

Các test này xác minh response HTTP thật qua Spring MVC, Jackson và validation. Nếu ứng dụng dùng security, thêm test authentication/authorization phù hợp hoặc cấu hình test principal.

## 33. Kiểm thử OpenAPI document trong integration test

Có thể gọi endpoint tài liệu từ MockMvc:

~~~java
@Test
void openApiContainsCrudOperationsAndErrorResponses() throws Exception {
    MvcResult result = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode document = objectMapper.readTree(
        result.getResponse().getContentAsString()
    );

    JsonNode paths = document.path("paths");

    assertThat(paths.path("/api/products").path("post")
        .path("responses").has("201")).isTrue();

    assertThat(paths.path("/api/products").path("post")
        .path("responses").has("500")).isTrue();

    assertThat(paths.path("/api/products").path("get")
        .path("responses").has("200")).isTrue();

    assertThat(paths.path("/api/products/{id}").path("get")
        .path("responses").has("404")).isTrue();

    assertThat(paths.path("/api/products/{id}").path("delete")
        .path("responses").has("204")).isTrue();
}
~~~

Ví dụ dùng JsonNode để kiểm tra cấu trúc thay vì tìm chuỗi trong toàn bộ document. Thêm assertion cho 400, 409 và schema ErrorResponse để tránh trường hợp status có mặt nhưng content bị thiếu.

Nếu project dùng nhiều GroupedOpenApi, test từng endpoint group riêng. Một operation có thể có trong default document nhưng bị loại khỏi public group theo thiết kế.

## 34. Phân biệt lỗi runtime với lỗi tài liệu

Một số tình huống cần kiểm tra riêng:

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| POST trả 400 nhưng OpenAPI không mô tả 400 | @ApiResponse và validation contract |
| OpenAPI ghi 201 nhưng code trả 200 | ResponseEntity/status mapping |
| DELETE ghi 204 nhưng trả body | Controller response và serialization |
| ErrorResponse schema có field nhưng JSON thiếu | Jackson inclusion hoặc DTO mapping |
| Swagger UI không hiện operation nhưng JSON có | UI đang chọn sai group hoặc filter |
| JSON có operation nhưng request trả 404 | Runtime mapping, context path hoặc proxy |
| Validation annotation có trong source nhưng schema không có constraint | Dependency, annotation target hoặc version compatibility |
| Response 500 lộ stack trace | Exception handler và error serialization |

Đừng sửa annotation chỉ để làm Swagger UI giống kết quả mong muốn nếu HTTP behavior đang sai. Hãy quyết định hợp đồng trước, rồi sửa runtime hoặc document để cả hai cùng tuân theo.

## 35. Kiểm tra response thành công và lỗi có nhất quán không

Đối chiếu ba nguồn:

1. OpenAPI document.
2. HTTP response từ ứng dụng.
3. Integration test.

Ví dụ với POST:

- OpenAPI nói 201 và ProductResponse.
- HTTP thực tế trả 201, Location và JSON ProductResponse.
- Test xác minh status, header và các field chính.

Với validation:

- OpenAPI nói 400 và ErrorResponse.
- HTTP thực tế trả 400, code VALIDATION_FAILED và fieldErrors.
- Test xác minh status và cấu trúc body.

Nếu một trong ba nguồn khác nhau, hợp đồng chưa hoàn chỉnh. Sửa source hoặc tài liệu rồi chạy lại test.

## 36. Tích hợp OpenAPI validation vào CI

Một pipeline có thể:

1. Chạy unit test và integration test.
2. Khởi động ứng dụng hoặc dùng Maven plugin export OpenAPI.
3. Lưu JSON/YAML vào thư mục build.
4. Parse document.
5. Chạy OpenAPI validator.
6. So sánh với baseline nếu API đã phát hành.
7. Upload artifact đã kiểm tra.

Ví dụ dùng OpenAPI Generator CLI:

~~~bash
openapi-generator-cli validate -i target/openapi.json
~~~

Hoặc dùng Redocly CLI:

~~~bash
npx @redocly/cli lint target/openapi.json
~~~

Khóa version của validator trong CI. Một validator cũ có thể chưa hiểu OpenAPI version hoặc JSON Schema dialect mà dự án sử dụng.

## 37. Những lỗi thường gặp khi tài liệu hóa CRUD

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Không đặt operationId | Client generator tạo tên khó đoán | Đặt operationId ổn định cho mỗi operation |
| Chỉ có summary | Thiếu điều kiện và semantics | Viết description ngắn, rõ |
| Dùng entity làm request/response | Lộ field nội bộ và gắn chặt API với database | Dùng DTO riêng |
| Thiếu @Valid | Constraint không chạy ở request body | Thêm @Valid và validation dependency |
| Không mô tả lỗi | Client không biết schema khi thất bại | Thêm @ApiResponse cho status quan trọng |
| Trả 200 cho create | Mất semantics tạo tài nguyên | Dùng 201 và Location |
| DELETE trả body nhưng mô tả 204 | Runtime và OpenAPI mâu thuẫn | Chọn 204 không body hoặc 200 có schema |
| Error handler trả nhiều cấu trúc | Client phải xử lý nhiều định dạng lỗi | Chuẩn hóa ErrorResponse |
| @Schema example không hợp lệ | Ví dụ gây hiểu nhầm | Đồng bộ example với type và validation |
| Chỉ kiểm tra Swagger UI | Không phát hiện lỗi trong JSON/YAML | Kiểm tra endpoint /v3/api-docs trực tiếp |
| Không test OpenAPI document | Operation hoặc response có thể biến mất | Thêm integration test cho document |
| Chỉ test happy path | Lỗi 400/404/409 chưa được xác minh | Test cả thành công và lỗi |

## 38. Checklist hoàn thành bài thực hành

Trước khi coi API CRUD đã được tài liệu hóa đầy đủ:

- [ ] Mỗi operation có operationId ổn định.
- [ ] Controller có @Tag và description phù hợp.
- [ ] Request DTO tách khỏi entity và response DTO.
- [ ] Validation annotations phản ánh quy tắc nghiệp vụ.
- [ ] OpenAPI schema thể hiện đúng required, type, format và giới hạn.
- [ ] POST trả 201 và Location.
- [ ] GET trả 200 và schema response đúng.
- [ ] PUT mô tả rõ semantics thay thế.
- [ ] DELETE trả 204 không body nếu hợp đồng chọn No Content.
- [ ] Lỗi 400, 404, 409 và 500 có ErrorResponse thống nhất.
- [ ] ControllerAdvice ánh xạ exception sang status code đúng.
- [ ] Security scheme được mô tả nếu API yêu cầu xác thực.
- [ ] JSON và YAML endpoint hoạt động.
- [ ] Swagger UI hiển thị đủ operation, parameter và response.
- [ ] Integration test xác minh cả HTTP behavior và OpenAPI document.
- [ ] CI parse và validate artifact OpenAPI.

## 39. Ghi nhớ

- Hợp đồng CRUD phải mô tả cả request, response thành công và response lỗi.
- Dùng DTO riêng cho create, update và response.
- Bean Validation kiểm tra dữ liệu runtime; springdoc đưa metadata phù hợp vào schema.
- @Operation mô tả mục đích operation; operationId cần ổn định.
- @ApiResponse mô tả status, description, media type và response schema.
- @Parameter làm rõ path/query parameter và ví dụ.
- @Schema bổ sung description, example và ràng buộc cho model.
- @RestControllerAdvice chuẩn hóa exception thành ErrorResponse.
- Status code phải khớp hành vi HTTP thật.
- 204 không có response body; 201 thường đi kèm Location khi tạo tài nguyên.
- Swagger UI là giao diện; OpenAPI JSON/YAML là artifact hợp đồng.
- Integration test cần xác minh cả payload thành công, payload lỗi và cấu trúc document.
- CI nên validate OpenAPI và so sánh baseline trước khi phát hành.

Một API CRUD chỉ có hợp đồng đáng tin cậy khi OpenAPI document, HTTP response và integration test mô tả cùng một hành vi. Hãy định nghĩa DTO và error model trước, gắn metadata rõ cho từng operation, ánh xạ exception về status code ổn định, rồi kiểm tra JSON/YAML và chạy test cả đường thành công lẫn lỗi. Khi ba nguồn khớp nhau, client có thể tích hợp API mà không phải suy đoán hành vi khi request thất bại.

## Tài liệu tham khảo

- Springdoc OpenAPI – Getting Started and FAQ: https://springdoc.org/
- Springdoc OpenAPI – FAQ on validation, annotations and response schemas: https://springdoc.org/faq.html
- Spring Framework – Annotated Controllers and Request Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html
- Spring Boot – Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Swagger Core – OpenAPI Annotations: https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations
