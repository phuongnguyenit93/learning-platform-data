# Kiểm tra request, response và schema lỗi

Một OpenAPI document chỉ có giá trị khi nó phản ánh đúng những gì API thực sự nhận và trả về. Kiểm thử hợp đồng cần xác nhận cả hai phía: request hợp lệ hoặc không hợp lệ được xử lý theo quy tắc đã công bố; response thành công và response lỗi có status, header, media type và schema đúng với tài liệu.

Với Spring Boot và springdoc-openapi, nên kiểm thử ba lớp:

1. **HTTP runtime contract:** endpoint nhận đúng method, path, query/header, content type và request body; trả đúng status, header, media type và response body.
2. **OpenAPI document contract:** /v3/api-docs mô tả đúng operation, parameter, request schema, response schema và lỗi.
3. **Sự nhất quán giữa runtime và tài liệu:** mọi hành vi quan trọng của server đều được mô tả, và mọi contract được công bố đều có thể thực hiện hoặc được giải thích rõ.

Một test chỉ kiểm tra HTTP 200 chưa đủ. Endpoint có thể trả 200 nhưng thiếu field bắt buộc, trả sai content type hoặc OpenAPI vẫn mô tả một request body khác với DTO runtime. Tương tự, document có schema đẹp nhưng controller không bật Bean Validation thì server vẫn có thể chấp nhận dữ liệu sai.

## 1. Contract của request gồm những gì?

Request contract xác định cách client được phép gọi operation. Với mỗi endpoint, kiểm tra các phần:

| Thành phần | Điều cần xác minh | Ví dụ |
|---|---|---|
| HTTP method và path | Đúng operation được công bố | POST /api/products |
| Path parameter | Tên, kiểu, format và required | id là UUID |
| Query parameter | Tên, kiểu, default, giới hạn | page >= 0, size <= 100 |
| Header | Header bắt buộc hoặc tùy chọn | Idempotency-Key |
| Content-Type | Định dạng request body được hỗ trợ | application/json |
| Accept | Định dạng response client yêu cầu | application/json |
| Request body | Schema, required field, constraint | name, price, category |
| Security | Authentication và authorization | Bearer token với scope phù hợp |

Một request hợp lệ phải đáp ứng cả cấu trúc và quy tắc nghiệp vụ. Ví dụ, price có thể là số dương theo schema, nhưng server còn có thể kiểm tra SKU có bị trùng hoặc sản phẩm có thuộc danh mục đang hoạt động hay không. Những quy tắc đó cần được mô tả và kiểm thử riêng.

## 2. Contract của response gồm status, header và body

Response contract không chỉ là JSON schema. Nó còn bao gồm status code, media type, header và điều kiện phát sinh response.

| Kết quả | Status thường dùng | Nội dung cần kiểm tra |
|---|---:|---|
| Tạo tài nguyên thành công | 201 Created | Body mới và Location |
| Đọc tài nguyên thành công | 200 OK | Schema response |
| Xóa thành công không có body | 204 No Content | Không có response body |
| Request sai cấu trúc hoặc validation | 400 Bad Request | Error schema và field violations |
| Chưa xác thực | 401 Unauthorized | Authentication challenge nếu có |
| Không đủ quyền | 403 Forbidden | Error response theo security policy |
| Không tìm thấy | 404 Not Found | Error schema |
| Xung đột nghiệp vụ | 409 Conflict | Error code và thông tin xung đột |
| Media type request không hỗ trợ | 415 Unsupported Media Type | Request Content-Type |
| Không thể tạo representation được yêu cầu | 406 Not Acceptable | Header Accept |
| Request hợp lệ về cú pháp nhưng không xử lý được theo policy | 422 Unprocessable Content | Chỉ dùng nếu API quy định status này |

Đây là các lựa chọn phổ biến, không phải quy tắc bắt buộc mọi API phải trả cùng status. Chọn status theo semantics của ứng dụng, sau đó dùng nhất quán trong controller, exception handler, OpenAPI và test.

Ví dụ, API có thể chọn 400 cho mọi lỗi validation hoặc dùng 422 cho một số lỗi semantic. Điều quan trọng là không để tài liệu mô tả 422 trong khi runtime luôn trả 400.

## 3. Bean Validation phải khớp với request schema

Springdoc có thể suy luận một số constraint từ Bean Validation annotations. Nhưng annotation OpenAPI chỉ mô tả contract; Bean Validation mới thực thi các constraint trong request.

Thêm dependency validation nếu ứng dụng chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

DTO ví dụ:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 1, max = 80)
    @Schema(
        description = "Tên hiển thị của sản phẩm.",
        example = "Bút bi",
        minLength = 1,
        maxLength = 80
    )
    String name,

    @NotNull
    @Positive
    @Digits(integer = 8, fraction = 2)
    @Schema(
        description = "Giá bán phải lớn hơn 0.",
        example = "12500.00",
        minimum = "0",
        exclusiveMinimum = true
    )
    BigDecimal price,

    @NotNull
    @Schema(description = "Nhóm sản phẩm.", example = "STATIONERY")
    ProductCategory category
) {}
~~~

Controller cần kích hoạt validation bằng @Valid:

~~~java
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());
    return ResponseEntity.created(location).body(created);
}
~~~

Nếu thiếu @Valid, một số constraint trên DTO có thể không được thực thi ở ranh giới request như mong muốn. Nếu chỉ thêm @Schema(minLength = 1) mà không có @NotBlank hoặc validator tương ứng, tài liệu có thể yêu cầu chuỗi không rỗng trong khi server vẫn nhận chuỗi rỗng.

Với Spring Boot 3 trở lên, Bean Validation dùng package jakarta.validation.*. Dự án Spring Boot 2 dùng javax.validation.*. Không trộn hai namespace trong cùng ứng dụng.

### Phân biệt required với nullable

Một property có thể:

- Bắt buộc phải xuất hiện trong request.
- Có thể xuất hiện nhưng nhận giá trị null.
- Không bắt buộc và có thể bị bỏ qua.

@NotNull và @NotBlank ảnh hưởng validation runtime. @Schema và kiểu Java ảnh hưởng cách OpenAPI mô tả. Hãy kiểm tra trường required trong schema được sinh ra, nhất là khi dùng record, constructor binding, Jackson configuration hoặc custom converter.

## 4. Kiểm thử request hợp lệ

Với Spring MVC, dùng MockMvc để gửi request qua MVC stack và xác minh response:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductWithValidRequest() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Bút bi",
                      "price": 12500.00,
                      "category": "STATIONERY"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.id").isNotEmpty())
            .andExpect(jsonPath("$.name").value("Bút bi"))
            .andExpect(jsonPath("$.price").value(12500.00))
            .andExpect(jsonPath("$.category").value("STATIONERY"));
    }
}
~~~

Test này kiểm tra method, path, content type, status, header và một số field trong response. Trong test thực tế, nên dùng test database hoặc mock service theo mục tiêu: kiểm thử controller contract hay kiểm thử tích hợp đầy đủ với persistence.

Nếu response có Location, kiểm tra URL trỏ tới tài nguyên vừa tạo. Nếu API dùng ETag, pagination headers hoặc correlation ID, đưa các header đó vào contract tests.

## 5. Kiểm thử request sai và validation error

Một bộ test request nên bao gồm các tình huống:

- Thiếu field bắt buộc.
- Field có chuỗi rỗng hoặc chỉ có khoảng trắng.
- Số nằm ngoài giới hạn.
- Enum value không tồn tại.
- UUID hoặc ngày giờ sai format.
- JSON sai cú pháp.
- Content-Type không được hỗ trợ.
- Query parameter thiếu hoặc vượt giới hạn.

Ví dụ request thiếu name và có price âm:

~~~java
@Test
void rejectsInvalidProductRequest() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .content("""
                {
                  "name": " ",
                  "price": -10,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.title").value("Request validation failed"))
        .andExpect(jsonPath("$.errors").isArray())
        .andExpect(jsonPath("$.errors.length()").value(2));
}
~~~

Số lượng lỗi phụ thuộc validator, DTO và cấu hình ứng dụng. Test minh họa giả định hai field vi phạm và exception handler gom lỗi vào mảng errors. Nếu implementation chỉ trả một lỗi đầu tiên, hãy viết test theo policy đó và mô tả đúng trong OpenAPI.

Không nên chỉ kiểm tra status 400. Nếu response lỗi không có schema ổn định, consumer sẽ phải tự đoán cấu trúc body hoặc xử lý riêng từng endpoint.

## 6. Chuẩn hóa error response bằng Problem Details

Spring Framework 6 cung cấp ProblemDetail để biểu diễn lỗi HTTP theo Problem Details for HTTP APIs, hiện được chuẩn hóa trong RFC 9457. Với Spring Boot 3+, có thể dùng ProblemDetail làm body cho lỗi HTTP.

Một Problem Details document thường có các field:

| Field | Ý nghĩa |
|---|---|
| type | URI định danh loại vấn đề; thường dùng URI tài liệu lỗi |
| title | Tóm tắt loại lỗi |
| status | HTTP status tương ứng |
| detail | Giải thích cụ thể cho lần xảy ra lỗi |
| instance | URI định danh lần xảy ra lỗi |
| Extension members | Field bổ sung do API định nghĩa, ví dụ errors, traceId |

Ví dụ response validation:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/products",
  "errors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Name must not be blank."
    },
    {
      "field": "price",
      "code": "Positive",
      "message": "Price must be greater than zero."
    }
  ]
}
~~~

application/problem+json là media type của Problem Details. Không mô tả error body này là application/json nếu runtime thực sự trả application/problem+json.

### Tạo schema rõ ràng cho lỗi validation

Vì ProblemDetail cho phép extension members động, có thể tạo DTO chỉ dùng để mô tả schema OpenAPI:

~~~java
@Schema(name = "ValidationProblem", description = "Problem Details cho lỗi validation.")
public record ValidationProblem(
    URI type,
    String title,
    Integer status,
    String detail,
    URI instance,
    List<FieldViolation> errors
) {}

@Schema(name = "FieldViolation", description = "Một lỗi validation trên field.")
public record FieldViolation(
    String field,
    String code,
    String message
) {}
~~~

DTO này mô tả wire shape mà ứng dụng cam kết trả. Nếu runtime trả ProblemDetail với extension errors, hãy bảo đảm tên field, kiểu dữ liệu và nullability của JSON thực tế khớp với ValidationProblem. Không dùng một schema minh họa khác với response thực tế.

## 7. Xây dựng exception handler nhất quán

@RestControllerAdvice có thể chuyển các exception validation và nghiệp vụ thành Problem Details:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException exception,
        HttpServletRequest request
    ) {
        List<Map<String, String>> errors =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "code", error.getCode() == null ? "Invalid" : error.getCode(),
                    "message", error.getDefaultMessage() == null
                        ? "Invalid value"
                        : error.getDefaultMessage()
                ))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "One or more request fields are invalid."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"
        ));
        problem.setTitle("Request validation failed");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
        ProductNotFoundException exception,
        HttpServletRequest request
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested product does not exist."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/product-not-found"
        ));
        problem.setTitle("Product not found");
        problem.setInstance(URI.create(request.getRequestURI()));

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Đây là ví dụ Spring MVC. Với WebFlux, dùng các API reactive tương ứng và không phụ thuộc HttpServletRequest. Khi xử lý lỗi validation, chỉ đưa field, code và thông báo đã được phép công khai vào response; không trả stack trace, SQL, class name nội bộ hoặc giá trị bí mật từ request.

Các exception khác như JSON parse error, type mismatch, constraint violation hoặc conflict có thể cần handler riêng. Nếu muốn toàn API có cùng schema lỗi, hãy định nghĩa rõ mapping cho các nhóm exception và test từng nhóm.

## 8. Mô tả error schema trong OpenAPI bằng @ApiResponse

Controller nên công bố cả response thành công lẫn response lỗi có thể xảy ra:

~~~java
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm mới"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Sản phẩm đã được tạo",
        headers = @Header(
            name = "Location",
            description = "URL của sản phẩm vừa tạo.",
            schema = @Schema(type = "string", format = "uri")
        ),
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request body không hợp lệ",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ValidationProblem.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "SKU đã tồn tại",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ApiProblem.class)
        )
    )
})
@PostMapping("/api/products")
ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    // Implementation
}
~~~

Ví dụ dùng ApiProblem cho lỗi nghiệp vụ chung:

~~~java
@Schema(name = "ApiProblem", description = "Problem Details cho lỗi API.")
public record ApiProblem(
    URI type,
    String title,
    Integer status,
    String detail,
    URI instance
) {}
~~~

Nếu controller đã dùng @ApiResponse để mô tả response, kiểm tra rằng status code và content type khớp với exception handler. Không khai báo 400 schema là ValidationProblem nếu handler thực tế trả một object khác.

Với lỗi có thể xảy ra trên nhiều endpoint, có thể dùng @ApiResponse ở cấp controller hoặc cấu hình OpenAPI customizer để chuẩn hóa. Chỉ công bố response dùng chung khi runtime thực sự có thể trả nó; không thêm một danh sách status code chung chung cho mọi operation.

## 9. Lỗi do Spring Security nằm ngoài controller advice thông thường

Một request có thể bị từ chối trước khi đi tới controller. Authentication và authorization thường được xử lý trong Spring Security filter chain, thông qua AuthenticationEntryPoint hoặc AccessDeniedHandler. Vì vậy, @RestControllerAdvice không phải lúc nào cũng bắt được 401 và 403.

Hãy kiểm tra riêng:

- Request không có token hoặc token không hợp lệ trả 401 theo security policy.
- User đã xác thực nhưng thiếu quyền trả 403.
- Response có challenge header phù hợp nếu dùng HTTP authentication scheme cần nó.
- Error body có đúng schema mà OpenAPI công bố.
- Endpoint /v3/api-docs và Swagger UI được bảo vệ theo policy riêng.

Nếu API dùng Problem Details cho lỗi bảo mật, cấu hình AuthenticationEntryPoint và AccessDeniedHandler để trả cùng media type/schema. Nếu Spring Security trả một body mặc định khác, hãy mô tả đúng body đó hoặc chuẩn hóa implementation; không giả định exception handler của controller sẽ thay đổi response do filter chain tạo ra.

## 10. Kiểm thử JSON sai cú pháp và lỗi chuyển đổi kiểu

Validation chỉ chạy sau khi request body được parse thành object. JSON sai cú pháp, enum không hợp lệ hoặc UUID sai format có thể phát sinh lỗi trước khi Bean Validation được gọi.

Ví dụ JSON không hợp lệ:

~~~java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{ \"name\": "))
        .andExpect(status().isBadRequest());
}
~~~

Ví dụ enum không tồn tại:

~~~java
@Test
void rejectsUnknownCategory() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Bút bi",
                  "price": 12500,
                  "category": "UNKNOWN"
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Hai test trên kiểm tra status tối thiểu. Nếu API cam kết mọi lỗi parse đều trả Problem Details, bổ sung assertion content type, type URI, title và status trong body. Các exception thường gặp gồm HttpMessageNotReadableException, MethodArgumentTypeMismatchException và ConstraintViolationException; exception cụ thể phụ thuộc vị trí binding và cấu hình Spring.

Đừng gom tất cả lỗi thành một status mà không có policy. Ví dụ, malformed JSON thường là 400; unsupported Content-Type là 415; Accept không tương thích có thể là 406. Kiểm thử riêng để phát hiện việc converter hoặc content negotiation thay đổi ngoài ý muốn khi nâng cấp Spring.

## 11. Kiểm thử content negotiation

Endpoint có thể hỗ trợ nhiều media type. Test phải xác nhận cả trường hợp được hỗ trợ và bị từ chối:

~~~java
@Test
void rejectsUnsupportedRequestContentType() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.TEXT_PLAIN)
            .content("name=Bút bi"))
        .andExpect(status().isUnsupportedMediaType());
}

@Test
void rejectsUnacceptableResponseType() throws Exception {
    mockMvc.perform(get("/api/products")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
}
~~~

Ví dụ giả định operation chỉ hỗ trợ JSON. Nếu ứng dụng có converter XML hoặc wildcard mapping, status có thể khác; hãy kiểm tra đúng cấu hình runtime. OpenAPI content phải liệt kê các media type server thực sự hỗ trợ.

## 12. Kiểm tra OpenAPI document được sinh ra

Springdoc tạo document từ Spring mappings, annotations, model và cấu hình. Nên có test trực tiếp endpoint /v3/api-docs để kiểm tra document, thay vì chỉ mở Swagger UI bằng mắt.

Ví dụ kiểm tra request body, response thành công và error schema:

~~~java
@Test
void publishesProductRequestAndResponseSchemas() throws Exception {
    mockMvc.perform(get("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/api/products'].post").exists())
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.requestBody.required"
        ).value(true))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.requestBody.content['application/json'].schema.$ref"
        ).value("#/components/schemas/CreateProductRequest"))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['201'].content['application/json'].schema.$ref"
        ).value("#/components/schemas/ProductResponse"))
        .andExpect(jsonPath(
            "$.paths['/api/products'].post.responses['400'].content['application/problem+json'].schema.$ref"
        ).value("#/components/schemas/ValidationProblem"));
}
~~~

Tên component schema có thể được springdoc đặt theo class name hoặc tùy chỉnh bằng @Schema(name = ...). Nếu dự án dùng schema naming strategy khác, điều chỉnh assertion theo document mong muốn; đừng bỏ kiểm tra chỉ vì tên component thay đổi ngoài ý muốn.

### Kiểm tra constraint trong schema

Có thể xác minh OpenAPI phản ánh các giới hạn quan trọng:

~~~java
@Test
void publishesProductValidationConstraints() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.CreateProductRequest.properties.name.minLength"
        ).value(1))
        .andExpect(jsonPath(
            "$.components.schemas.CreateProductRequest.properties.name.maxLength"
        ).value(80));
}
~~~

Constraint nào xuất hiện trong OpenAPI phụ thuộc annotation, Bean Validation integration, schema version và cấu hình springdoc. Hãy kiểm tra các constraint quan trọng nhất của API thay vì khóa test vào mọi chi tiết nội bộ có thể thay đổi khi nâng dependency.

### Kiểm tra schema lỗi

~~~java
@Test
void publishesValidationProblemSchema() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.type"
        ).exists())
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.status.type"
        ).value("integer"))
        .andExpect(jsonPath(
            "$.components.schemas.ValidationProblem.properties.errors.type"
        ).value("array"))
        .andExpect(jsonPath(
            "$.components.schemas.FieldViolation.properties.field.type"
        ).value("string"));
}
~~~

Test document này chỉ chứng minh schema được công bố. Test runtime ở phần trước mới xác minh response thật có cấu trúc tương ứng. Cần có cả hai để tránh trường hợp tài liệu đúng nhưng handler sai hoặc handler đúng nhưng tài liệu thiếu schema.

## 13. Kiểm tra response lỗi thực tế khớp schema

Sau khi kiểm tra OpenAPI document, gửi request sai và xác minh body:

~~~java
@Test
void validationProblemMatchesPublishedShape() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .content("""
                {
                  "name": "",
                  "price": 0,
                  "category": "STATIONERY"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/validation-error"
        ))
        .andExpect(jsonPath("$.title").value("Request validation failed"))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.detail").isNotEmpty())
        .andExpect(jsonPath("$.instance").value("/api/products"))
        .andExpect(jsonPath("$.errors[0].field").isNotEmpty())
        .andExpect(jsonPath("$.errors[0].code").isNotEmpty())
        .andExpect(jsonPath("$.errors[0].message").isNotEmpty());
}
~~~

Để test bền vững, chỉ assert thứ tự errors nếu API cam kết thứ tự đó. Nếu không, đọc mảng và tìm lỗi theo field. Không so sánh toàn bộ JSON bằng một chuỗi cố định khi các field instance, timestamp hoặc trace ID có thể thay đổi.

Schema lỗi nên ổn định ở những field mà client cần xử lý bằng code: type URI, status, error code và field name. Message dành cho con người có thể thay đổi hoặc được bản địa hóa; client không nên dùng câu message để quyết định nhánh nghiệp vụ.

## 14. Dùng WebTestClient cho ứng dụng WebFlux

Nếu ứng dụng chạy WebFlux, dùng WebTestClient thay vì MockMvc để kiểm tra reactive web stack:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveProductContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void rejectsInvalidRequestWithProblemDetails() {
        webTestClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue("""
                {
                  "name": "",
                  "price": -1,
                  "category": "STATIONERY"
                }
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            )
            .expectBody()
            .jsonPath("$.status").isEqualTo(400)
            .jsonPath("$.errors").exists();
    }

    @Test
    void exposesOpenApiDocument() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/products'].post").exists();
    }
}
~~~

Không trộn MockMvc và WebTestClient tùy tiện. Dùng test client tương ứng với web stack đang chạy để test qua đúng filter chain, codec và message reader/writer.

## 15. Phân biệt kiểm tra cú pháp OpenAPI với kiểm tra HTTP contract

Một OpenAPI document hợp lệ về cú pháp chưa chắc mô tả đúng server. Nên tách ba loại kiểm tra:

| Loại kiểm tra | Phát hiện được | Không chứng minh được |
|---|---|---|
| Parse/validate OpenAPI | JSON/YAML sai cú pháp, cấu trúc không hợp lệ, reference không phân giải | Controller runtime có trả đúng response hay không |
| OpenAPI lint | Thiếu operationId, description, response, naming rule hoặc policy của tổ chức | Request/response thực tế có tuân thủ schema hay không |
| HTTP contract validation | Request/response thực tế lệch path, status, header, media type hoặc schema đã công bố | Nghiệp vụ có đúng về mặt kinh doanh hay không |
| Business integration test | Quy tắc nghiệp vụ và tương tác service/database | Tất cả consumer bên ngoài đã dùng contract đúng hay chưa |

Ví dụ, JSON document có thể parse thành công nhưng response 400 không được mô tả. Ngược lại, OpenAPI có thể mô tả 400 hoàn hảo nhưng exception handler runtime trả HTML hoặc stack trace. Cần chạy các lớp kiểm tra phù hợp với rủi ro của API.

### Validate OpenAPI document trong CI

Sau khi export document từ /v3/api-docs, có thể dùng OpenAPI Generator CLI để kiểm tra tính hợp lệ cơ bản:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

Với YAML:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

Validator kiểm tra cấu trúc đặc tả theo khả năng của phiên bản công cụ. Nó không thay thế contract test đối với HTTP response thật. Nếu tổ chức dùng linter riêng, cấu hình rule set và version rõ ràng để kết quả CI có thể lặp lại.

## 16. So sánh OpenAPI document với baseline

Khi API thay đổi, cần biết thay đổi nào ảnh hưởng consumer. Có thể lưu OpenAPI document của release gần nhất làm baseline rồi so sánh với document của nhánh hiện tại.

Những thay đổi cần chú ý:

- Xóa path hoặc HTTP method.
- Xóa parameter hoặc đổi parameter từ optional thành required.
- Đổi request/response property type hoặc format.
- Thu hẹp enum value mà client cũ có thể gửi hoặc nhận.
- Thay đổi response status hoặc media type.
- Đổi security requirement hoặc OAuth scope.
- Đổi nullability, required field hoặc pagination semantics.
- Xóa error response mà client đang xử lý.

Thêm response status hoặc property mới cũng cần đánh giá theo cách client deserialize. Một số thay đổi có vẻ additive nhưng vẫn gây lỗi cho client strict khi gặp enum value mới hoặc field lạ. Không chỉ dựa vào nhãn breaking/non-breaking của tool; hãy xét cách consumer thực tế sinh code và parse JSON.

Trong CI, có thể chạy bước diff sau khi document mới được tạo:

~~~text
OpenAPI current
      |
      v
Parse and lint
      |
      v
Compare with released baseline
      |
      +---- breaking change ----> fail or require explicit approval
      |
      +---- compatible change --> continue
      |
      v
Run runtime contract tests
      |
      v
Publish build artifact
~~~

Baseline phải là document đã phát hành cho consumer, không phải file cũ bất kỳ trong workspace. Nếu API có nhiều group hoặc version, so sánh đúng cặp tài liệu tương ứng.

## 17. Kiểm tra response schema với dữ liệu thực tế

Schema trong OpenAPI mô tả shape của response. Test runtime nên xác minh:

- Property bắt buộc có mặt khi contract yêu cầu.
- Kiểu JSON đúng: string, number, integer, boolean, object hoặc array.
- Format phù hợp: date, date-time, uuid, uri hoặc format tùy chỉnh.
- Enum value nằm trong tập được công bố.
- Nullability đúng với schema.
- Array item có cấu trúc đúng.
- Không trả field nội bộ hoặc dữ liệu nhạy cảm ngoài contract.

Ví dụ kiểm tra response có danh sách:

~~~java
mockMvc.perform(get("/api/products")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items[0].id").isNotEmpty())
    .andExpect(jsonPath("$.items[0].name").isString())
    .andExpect(jsonPath("$.items[0].price").isNumber());
~~~

Các assertion theo path giúp test dễ đọc. Với schema lớn, nhiều operation hoặc nhiều ví dụ response, nên bổ sung một validator đọc OpenAPI document và kiểm tra response JSON theo schema để giảm số assertion thủ công.

Đừng mặc định property không được mô tả thì server không được trả. OpenAPI Schema Object có thể cho phép additional properties tùy schema. Nếu muốn cấm field lạ hoặc cần kiểm soát chặt, khai báo rõ policy và dùng validator phù hợp.

## 18. Kiểm tra lỗi nghiệp vụ và lỗi hệ thống

Không phải lỗi nào cũng là validation error. Phân nhóm lỗi để schema và test phản ánh đúng nguyên nhân:

| Nhóm lỗi | Ví dụ | Contract cần xác minh |
|---|---|---|
| Request syntax | JSON sai, UUID không parse được | Status, Problem Details type và message |
| Request validation | Tên rỗng, giá âm | Field violations và error code |
| Resource lookup | Product ID không tồn tại | 404 và error type |
| Business conflict | SKU đã được dùng | 409 và conflict code |
| Authentication | Token thiếu hoặc hết hạn | 401 và authentication challenge |
| Authorization | User không có quyền | 403 |
| Dependency failure | Database hoặc service ngoài không sẵn sàng | 5xx theo policy, không lộ nội bộ |

Không trả 500 cho lỗi input mà server có thể xác định là 400. Không trả 404 cho lỗi phân quyền chỉ để che sự tồn tại của tài nguyên nếu policy không quy định như vậy. Các quyết định security có thể chọn response khác nhau, nhưng phải được ghi rõ trong contract.

Với lỗi 5xx, Problem Details nên cung cấp type/title ổn định và một correlation ID nếu cần hỗ trợ vận hành. Không đưa stack trace, hostname nội bộ, câu SQL, secret hoặc exception message thô vào detail.

## 19. Kiểm tra error schema không làm rò rỉ dữ liệu

Một error body hữu ích cho client không cần tiết lộ implementation. Test nên đảm bảo:

- Không có stackTrace, exceptionClass hoặc SQL statement.
- Không phản hồi lại password, access token, cookie hoặc secret trong request.
- Không có thông tin cá nhân không cần thiết.
- Message không chứa tên bảng, tên package hoặc địa chỉ service nội bộ.
- Field-level errors chỉ chứa tên field công khai và mã lỗi ổn định.
- Correlation ID có định dạng dự kiến nhưng không dùng làm thông tin xác thực.

Ví dụ kiểm tra không lộ stack trace:

~~~java
@Test
void doesNotExposeInternalExceptionDetails() throws Exception {
    MvcResult result = mockMvc.perform(
            get("/api/products/00000000-0000-0000-0000-000000000000")
        )
        .andExpect(status().isNotFound())
        .andReturn();

    String body = result.getResponse().getContentAsString();
    assertThat(body).doesNotContain("java.lang.");
    assertThat(body).doesNotContain("SELECT ");
    assertThat(body).doesNotContain("password");
    assertThat(body).doesNotContain("Bearer ");
}
~~~

Test phải dùng một endpoint và fixture có thể tái hiện lỗi ổn định. Không nên kiểm tra bằng một chuỗi quá chung nếu message nghiệp vụ hợp lệ có thể chứa từ đó; trong dự án thực tế, assert vào các field dành cho nội bộ như stackTrace hoặc kiểm tra schema allowlist sẽ chính xác hơn.

## 20. Kiểm tra security response riêng

Nếu Spring Security dùng custom AuthenticationEntryPoint và AccessDeniedHandler, viết test riêng cho cả hai:

Để dùng MockMvc request post-processor user(...) trong test, thêm dependency spring-security-test ở scope test nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
@Test
void unauthenticatedRequestUsesDocumentedErrorContract() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isUnauthorized())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(401))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/unauthorized"
        ));
}

@Test
void forbiddenRequestUsesDocumentedErrorContract() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(user("reader").roles("READER")))
        .andExpect(status().isForbidden())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(403));
}
~~~

Các test giả định security configuration trả Problem Details với media type đã nêu. Nếu policy trả 401/403 body rỗng hoặc dùng schema riêng, cập nhật OpenAPI và test theo policy thực tế. Cũng kiểm tra WWW-Authenticate khi authentication scheme yêu cầu header này.

## 21. Ma trận kiểm thử request/response/error

Một ma trận ngắn giúp nhóm phát triển kiểm tra có hệ thống:

| Nhóm | Request | Kỳ vọng runtime | Kỳ vọng OpenAPI |
|---|---|---|---|
| Happy path | JSON hợp lệ | 2xx/201, body và headers đúng | Request/response schema đầy đủ |
| Required field | Thiếu property bắt buộc | 400 hoặc policy đã chọn | required list và error response |
| Constraint | Chuỗi rỗng, số âm, vượt giới hạn | 400/422 theo policy | min/max, pattern, format |
| Parse | JSON sai, enum/UUID sai | 400 | Error schema cho parse/type error |
| Content-Type | Gửi media type không hỗ trợ | 415 | Request content chỉ liệt kê media type được hỗ trợ |
| Accept | Yêu cầu representation không hỗ trợ | 406 | Response content đúng media type |
| Not found | ID không tồn tại | 404 | Error response 404 |
| Conflict | Dữ liệu trùng hoặc trạng thái xung đột | 409 | Error response 409 |
| Security | Thiếu token hoặc thiếu role | 401/403 | Security requirement và error response |
| Server error | Dependency thất bại | 5xx theo policy | Error response không lộ chi tiết nội bộ |

Không cần test mọi tổ hợp có thể có. Chọn test theo rủi ro, những nhánh contract đã công bố và các lỗi từng xảy ra trong production.

## 22. Lưu ý theo phiên bản Spring Boot và web stack

Một số API lỗi và package thay đổi giữa các major version:

| Nền tảng | Cách triển khai error response |
|---|---|
| Spring Boot 3 / Spring Framework 6 trở lên | Có thể dùng ProblemDetail và media type application/problem+json |
| Spring Boot 2 / Spring Framework 5 | Không có ProblemDetail trong Spring Framework; dùng DTO lỗi riêng hoặc thư viện phù hợp |
| Spring MVC | Dùng @RestControllerAdvice, HandlerExceptionResolver và Servlet Security handlers |
| Spring WebFlux | Dùng reactive exception handling, WebExceptionHandler và WebFlux Security handlers |

Không sao chép trực tiếp code ProblemDetail vào dự án Spring Boot 2. Nếu cần cùng một contract lỗi giữa nhiều major version, định nghĩa DTO lỗi độc lập với framework rồi viết adapter cho từng web stack.

Trong Spring MVC, validation cho request body thường phát sinh MethodArgumentNotValidException. Validation ở method parameter hoặc controller method có thể phát sinh exception khác tùy phiên bản Spring và cách dùng @Validated. Trong WebFlux, kiểu exception và cách ghi response có thể khác MVC. Test dựa trên hành vi HTTP cuối cùng thay vì phụ thuộc quá nhiều vào tên exception nội bộ.

## 23. Đưa contract checks vào CI

Một pipeline CI nên chạy các bước theo thứ tự:

1. Compile và chạy unit tests.
2. Khởi động ứng dụng với profile kiểm thử và cấu hình dữ liệu ổn định.
3. Tải OpenAPI JSON/YAML từ endpoint runtime.
4. Parse và validate OpenAPI document.
5. Chạy lint và policy checks cho operation, parameter, schema và error responses.
6. So sánh document với baseline đã phát hành để phát hiện breaking changes.
7. Chạy HTTP contract tests cho happy path và negative cases.
8. Kiểm tra error schema, security responses và content negotiation.
9. Lưu OpenAPI document và test reports thành build artifacts.

Không publish tài liệu chỉ vì endpoint /v3/api-docs trả 200. Chỉ publish khi document parse được, lint đạt policy và các test runtime quan trọng đã chạy thành công.

Ví dụ các gate có thể đặt trong pipeline:

~~~text
Build application
       |
       v
Start test server
       |
       v
Export OpenAPI document
       |
       v
Validate + lint + compare baseline
       |
       v
Run HTTP contract tests
       |
       v
Stop test server
       |
       v
Publish OpenAPI + test reports
~~~

Nếu test server được start bằng Maven plugin, bảo đảm có cleanup ngay cả khi một bước giữa pipeline thất bại. Nếu ứng dụng dùng database/container phụ, quản lý lifecycle và dữ liệu test để kết quả không phụ thuộc lần chạy trước.

## 24. Lỗi thường gặp khi kiểm tra request, response và schema lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| OpenAPI có minLength nhưng server nhận chuỗi rỗng | Chỉ khai báo @Schema, thiếu Bean Validation hoặc @Valid | Thêm constraint runtime và kích hoạt validation |
| Request sai trả 500 | Exception validation/parse không được ánh xạ đúng | Bổ sung exception handler và test status |
| Request body lỗi trả HTML | Error handling mặc định hoặc filter khác ghi response | Chuẩn hóa error response và content type |
| 400 response không có schema trong OpenAPI | Thiếu @ApiResponse hoặc customizer | Khai báo Problem Details schema |
| OpenAPI nói application/json nhưng runtime trả problem+json | Annotation không khớp exception handler | Khai báo media type application/problem+json |
| Test không thấy 401/403 trong @RestControllerAdvice | Security filter chain xử lý trước controller | Test và cấu hình AuthenticationEntryPoint/AccessDeniedHandler |
| JSONPath test phụ thuộc thứ tự errors | Mảng violation không có thứ tự contract | Tìm phần tử theo field/code thay vì index cố định |
| Schema ValidationProblem không giống body thực tế | DTO schema chỉ là ví dụ hoặc extension properties khác shape | Đồng bộ field/type/nullability và test JSON runtime |
| Swagger UI hiển thị schema đúng nhưng server sai | Chỉ kiểm tra tài liệu, chưa test HTTP | Thêm runtime contract tests |
| Response test chỉ kiểm tra status | Thiếu assertion header, content type và body | Kiểm tra toàn bộ response contract |
| Error body lộ stack trace hoặc SQL | Trả exception message nội bộ | Dùng error code/message công khai và test rò rỉ |
| Enum mới làm client cũ lỗi | Consumer parse enum strict | Đánh giá enum evolution và versioning policy |
| OpenAPI diff báo nhiều thay đổi không liên quan | Generator/configuration không ổn định | Chuẩn hóa schema naming, ordering và môi trường build |
| Test chạy được local nhưng fail CI | Profile, locale, clock hoặc dữ liệu không ổn định | Cố định test config, fixture và timezone |

## 25. Quy trình kiểm thử một operation hoàn chỉnh

Với mỗi operation quan trọng, có thể áp dụng trình tự:

1. Đọc OpenAPI operation: method, path, security, parameters, request body và response.
2. Gửi một request hợp lệ và xác minh status, headers, media type, body.
3. Gửi request thiếu required field và request vi phạm constraint.
4. Gửi JSON sai cú pháp, enum hoặc path/query parameter sai kiểu.
5. Gửi Content-Type và Accept không được hỗ trợ.
6. Kiểm tra các lỗi nghiệp vụ như not found và conflict.
7. Kiểm tra 401/403 qua security filter chain.
8. Xác minh mọi response lỗi có đúng type, title, status, detail, instance và extension fields.
9. Tải /v3/api-docs và xác minh schema request, success response và error response.
10. Validate/lint document và so sánh với baseline trong CI.

Đối với API public hoặc có nhiều consumer, lưu request/response examples làm fixture để contract tests phát hiện thay đổi không chủ ý. Khi schema thay đổi, review cả OpenAPI diff lẫn tác động tới consumer sinh SDK.

## 26. Tài liệu tham khảo

- [Springdoc OpenAPI – Getting Started and Features](https://springdoc.org/): cách springdoc sinh OpenAPI từ Spring Boot, annotations và model.
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html): các câu hỏi thường gặp về schema, response và cấu hình.
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Bean Validation trong Spring.
- [Spring Framework – Request Body Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validation cho controller method và request body trong Spring MVC.
- [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation trong WebFlux controller.
- [Spring Framework – Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse và xử lý lỗi REST.
- [Spring Security – Authentication Entry Point](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): xử lý authentication trong security filter chain.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): mô tả request body.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): mô tả response theo status code.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): schema, properties, required và constraints.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng error response có cấu trúc và application/problem+json.
- [OpenAPI Generator – Validate](https://openapi-generator.tech/docs/usage/#validate): kiểm tra OpenAPI document trong build/CI.
