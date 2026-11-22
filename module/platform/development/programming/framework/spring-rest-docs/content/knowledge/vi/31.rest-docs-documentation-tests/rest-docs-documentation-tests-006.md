# Kiểm tra lỗi validation và response error

## 1. Vì sao phải kiểm thử và tài liệu hóa response lỗi?

Một API không chỉ có response thành công. Client cũng cần biết server phản hồi thế nào khi request thiếu field bắt buộc, sai định dạng, vi phạm giới hạn hoặc không thỏa quy tắc nghiệp vụ. Nếu chỉ tài liệu hóa HTTP 200/201, người tích hợp sẽ phải tự đoán cấu trúc lỗi và cách xử lý.

Trong **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Các test xác nhận hành vi request/response và sinh snippet cho payload, headers, parameters cùng status. Sau đó snippet được biên soạn trong Asciidoctor/Markdown và đưa vào build/CI.

Chương **Kiểm thử tài liệu** giúp biến thay đổi contract thành tín hiệu kiểm tra. Bài này tập trung vào validation và response error: cách kích hoạt Bean Validation, phân biệt lỗi binding với lỗi nghiệp vụ, chuẩn hóa response qua `@RestControllerAdvice`, viết negative tests và dùng Spring REST Docs để mô tả error contract.

Sau bài học, bạn có thể:

- Kiểm tra request không hợp lệ bằng MockMvc.
- Phân biệt lỗi deserialize/binding, Bean Validation và lỗi nghiệp vụ.
- Thiết kế response lỗi ổn định với error code và field details.
- Dùng `responseFields(...)` hoặc `responseBody(...)` để tài liệu hóa lỗi.
- Dùng `requestFields(...)` khi cần mô tả payload đầu vào và `responseHeaders(...)` cho header lỗi.
- Kiểm tra status, error code, field path và message trong test.
- Đưa negative tests và snippet lỗi vào Asciidoctor/CI.

## 2. Phân loại lỗi đầu vào

Một request không hợp lệ có thể thất bại ở nhiều giai đoạn. Phân biệt chúng giúp API trả status và error code nhất quán.

| Nhóm lỗi | Ví dụ | Nơi thường phát hiện |
| --- | --- | --- |
| JSON parse/deserialization | Body JSON sai cú pháp hoặc kiểu dữ liệu không chuyển đổi được | Jackson/HttpMessageConverter |
| Bean Validation | `name` rỗng, `price` âm, email sai định dạng | `@Valid` / Jakarta Validation |
| Request binding | Thiếu query parameter bắt buộc, path value không chuyển đổi được | Spring MVC argument resolver |
| Multipart validation | Thiếu file, MIME type không hỗ trợ, file rỗng | Controller/service hoặc multipart resolver |
| Domain/business validation | Sản phẩm không thể chuyển trạng thái, số lượng vượt tồn kho | Service/domain layer |
| Authorization | Người dùng không có quyền thao tác | Security filter/method security |

Không phải mọi lỗi đều đi qua controller method. Ví dụ JSON parse error có thể xảy ra trước khi method được gọi; lỗi validation có thể được ném sau khi body đã deserialize; lỗi nghiệp vụ thường phát sinh trong service. Error handler cần bao phủ đúng các exception mà ứng dụng muốn chuẩn hóa.

## 3. Định nghĩa request DTO với Bean Validation

Giả sử endpoint `POST /api/products` nhận:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "email": "owner@example.com"
}
```

DTO có thể khai báo constraint:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @Positive
        Integer price,

        @NotBlank
        @Email
        String email
) {}
```

Controller kích hoạt validation bằng `@Valid`:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductResponse response = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Nếu thiếu `@Valid` (hoặc cơ chế validation tương ứng), các constraint trên DTO có thể không được thực thi khi request đi vào controller. Dự án cũng cần dependency Jakarta Bean Validation implementation phù hợp với phiên bản Spring Boot/Spring Framework đang dùng.

## 4. Thiết kế response error ổn định

Một response lỗi nên có cấu trúc nhất quán để client xử lý theo chương trình. Ví dụ:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "status": 400,
  "path": "/api/products",
  "fieldErrors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "must not be blank"
    },
    {
      "field": "price",
      "code": "Positive",
      "message": "must be greater than 0"
    }
  ]
}
```

Một DTO minh họa:

```java
public record FieldErrorDetail(
        String field,
        String code,
        String message
) {}

public record ApiError(
        String code,
        String message,
        int status,
        String path,
        List<FieldErrorDetail> fieldErrors
) {}
```

Các nguyên tắc thiết kế:

- `code` ổn định, không phụ thuộc câu chữ hiển thị.
- `message` giải thích ngắn gọn cho người tích hợp.
- `status` trùng HTTP status để thuận tiện debug, nhưng HTTP status line vẫn là nguồn chuẩn.
- `path` chỉ chứa path cần thiết; tránh echo query string có thể chứa dữ liệu nhạy cảm.
- `fieldErrors` chỉ xuất hiện khi lỗi gắn với field; có thể là mảng rỗng hoặc vắng mặt theo quy ước thống nhất.
- Không trả stack trace, SQL, tên class nội bộ, đường dẫn file hoặc dữ liệu bí mật.

Nên chuẩn hóa quy tắc về thứ tự field errors nếu muốn snippet và test output ổn định. Không để test phụ thuộc vào thứ tự không được contract cam kết.

## 5. Ánh xạ Bean Validation qua `@RestControllerAdvice`

Với Spring MVC, lỗi Bean Validation cho `@Valid @RequestBody` thường được biểu diễn bằng `MethodArgumentNotValidException`. Có thể ánh xạ exception thành response contract:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception,
            HttpServletRequest request) {

        List<FieldErrorDetail> details =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(error -> new FieldErrorDetail(
                                error.getField(),
                                error.getCode(),
                                error.getDefaultMessage()
                        ))
                        .toList();

        ApiError body = new ApiError(
                "VALIDATION_FAILED",
                "Request contains invalid fields",
                HttpStatus.BAD_REQUEST.value(),
                request.getRequestURI(),
                details
        );

        return ResponseEntity.badRequest().body(body);
    }
}
```

Đây là ví dụ cho Spring MVC và Java hiện đại; import `HttpServletRequest`, `MethodArgumentNotValidException`, `HttpStatus` và collection tương ứng theo dự án. Với phiên bản Spring mới, một số kiểu validation method-level có thể phát sinh exception khác, chẳng hạn `HandlerMethodValidationException`; nếu endpoint sử dụng cơ chế đó, cần xử lý và test riêng.

### 5.1. Xử lý lỗi JSON không parse được

JSON sai cú pháp hoặc không chuyển đổi được có thể phát sinh `HttpMessageNotReadableException`. Đây không phải Bean Validation error vì DTO chưa được tạo thành công để chạy constraint.

```java
@ExceptionHandler(HttpMessageNotReadableException.class)
ResponseEntity<ApiError> handleUnreadableBody(
        HttpMessageNotReadableException exception,
        HttpServletRequest request) {

    ApiError body = new ApiError(
            "INVALID_REQUEST_BODY",
            "Request body is missing or malformed",
            HttpStatus.BAD_REQUEST.value(),
            request.getRequestURI(),
            List.of()
    );

    return ResponseEntity.badRequest().body(body);
}
```

Không đưa thông điệp parser chi tiết trực tiếp ra client nếu nó chứa nội dung nội bộ hoặc quá khó hiểu. Log nguyên nhân đầy đủ ở server với correlation ID; response public nên ổn định.

### 5.2. Xử lý lỗi nghiệp vụ

Giả sử tên sản phẩm đã tồn tại:

```java
public class ProductAlreadyExistsException extends RuntimeException {
    public ProductAlreadyExistsException(String name) {
        super(name);
    }
}
```

Handler:

```java
@ExceptionHandler(ProductAlreadyExistsException.class)
ResponseEntity<ApiError> handleDuplicateProduct(
        ProductAlreadyExistsException exception,
        HttpServletRequest request) {

    ApiError body = new ApiError(
            "PRODUCT_ALREADY_EXISTS",
            "A product with this name already exists",
            HttpStatus.CONFLICT.value(),
            request.getRequestURI(),
            List.of()
    );

    return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
}
```

Lỗi nghiệp vụ thường dùng status 409 khi xung đột với trạng thái hiện tại của resource, nhưng status phải theo contract của API. Không gộp tất cả lỗi vào `400` nếu client cần phân biệt validation, conflict, authorization và server errors.

## 6. Viết negative test bằng MockMvc

Test cần gửi request không hợp lệ và xác nhận cả status lẫn error payload. Ví dụ `name` rỗng, `price` âm và email sai:

```java
@Test
void returnsValidationErrorForInvalidCreateProduct() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "",
                  "price": -10,
                  "email": "not-an-email"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.fieldErrors").isArray())
        .andExpect(jsonPath("$.fieldErrors[*].field",
                containsInAnyOrder("name", "price", "email")));
}
```

`containsInAnyOrder` tránh khóa thứ tự lỗi nếu contract không cam kết thứ tự. Nếu API có quy tắc thứ tự cố định, có thể kiểm tra chính xác thứ tự đó.

Test này chỉ kiểm tra response của ứng dụng khi validation được kích hoạt. Nó cũng cần chạy qua cấu hình test có `@RestControllerAdvice` thực tế. Nếu test dùng standalone MockMvc, phải đăng ký controller advice rõ ràng.

## 7. Dùng Spring REST Docs để tài liệu hóa error response

Một negative test có thể tạo snippet cho request và response lỗi. Ví dụ:

```java
mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "",
              "price": -10,
              "email": "not-an-email"
            }
            """))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-validation-error",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("price").description("Giá bán"),
            fieldWithPath("email").description("Email người quản lý")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi ổn định"),
            fieldWithPath("message").description("Mô tả lỗi tổng quát"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Đường dẫn request"),
            fieldWithPath("fieldErrors").description("Danh sách lỗi validation"),
            fieldWithPath("fieldErrors[].field").description("Tên field không hợp lệ"),
            fieldWithPath("fieldErrors[].code").description("Mã constraint"),
            fieldWithPath("fieldErrors[].message").description("Thông báo validation")
        )
    ));
```

Nếu test chỉ cần tài liệu hóa response lỗi, có thể dùng `responseFields(...)` mà không lặp lại request fields. Ngược lại, khi muốn người đọc biết request gây ra lỗi có hình dạng thế nào, giữ `requestFields(...)` và mô tả payload đầu vào.

Các descriptor phải khớp response thực tế. Nếu response có field mới chưa được mô tả, strict `responseFields(...)` có thể làm test thất bại. Đây là hành vi có ích để phát hiện error contract drift.

### 7.1. Tách snippet cho từng loại lỗi

Không nên gom mọi lỗi vào một operation ID nếu cấu trúc response hoặc nguyên nhân khác nhau. Có thể tạo riêng:

```text
products-create-validation-error/
products-create-invalid-json/
products-create-conflict/
products-create-unauthorized/
```

Mỗi operation ID có thể sinh `http-response.adoc`, `response-fields.adoc` và các snippet khác theo cấu hình. Trang tài liệu có thể include các ví dụ lỗi riêng biệt.

## 8. Tài liệu hóa error response bằng `responseBody(...)`

Khi response lỗi có cấu trúc JSON lớn hoặc thay đổi theo một schema chung, có thể dùng `responseBody(...)` để include body mẫu thay vì mô tả mọi field.

Ví dụ:

```java
.andDo(document("products-create-validation-error",
    responseBody()
));
```

Snippet body giúp người đọc thấy một response lỗi hoàn chỉnh. Tuy nhiên, body snippet không thay thế việc kiểm tra cấu trúc field. Nếu cần contract chi tiết và strict validation, dùng `responseFields(...)`; nếu cần cả schema lẫn ví dụ, có thể dùng cả hai.

Có thể thêm `responseHeaders(...)` nếu error response có header công khai quan trọng:

```java
responseHeaders(
    headerWithName("Content-Type")
        .description("Định dạng response lỗi"),
    headerWithName("X-Correlation-Id")
        .description("Mã dùng để tra cứu log hỗ trợ")
);
```

Chỉ mô tả correlation header nếu ứng dụng thực sự trả header đó. Không ghi token hoặc cookie vào snippet.

## 9. Phân biệt validation error, binding error và domain error

Một trang API tốt nên giúp client hiểu loại lỗi nào có thể xuất hiện.

| Tình huống | Exception/nguồn thường gặp | Status ví dụ | Error code ví dụ |
| --- | --- | --- | --- |
| Field vi phạm `@NotBlank` | `MethodArgumentNotValidException` | 400 | `VALIDATION_FAILED` |
| JSON sai cú pháp | `HttpMessageNotReadableException` | 400 | `INVALID_REQUEST_BODY` |
| Query param không chuyển đổi được | Type mismatch/binding exception | 400 | `INVALID_PARAMETER` |
| Resource đã tồn tại gây conflict | Domain exception | 409 | `PRODUCT_ALREADY_EXISTS` |
| Không có quyền | Security exception/entry point | 401 hoặc 403 | `UNAUTHORIZED` / `FORBIDDEN` |
| Media type không hỗ trợ | `HttpMediaTypeNotSupportedException` | 415 | `UNSUPPORTED_MEDIA_TYPE` |

Đây là bảng định hướng; exception và status thực tế phụ thuộc loại controller argument, Spring version, security configuration và exception handler. Test phải xác nhận hành vi thực tế của ứng dụng.

Không nên viết một handler quá rộng bắt `Exception` rồi trả `400` cho mọi trường hợp. Lỗi lập trình hoặc hệ thống cần được xử lý như server error, không biến thành lỗi request của client.

## 10. Kiểm thử field-level errors

Với `fieldErrors`, test có thể xác nhận path và code của từng lỗi:

```java
.andExpect(jsonPath("$.fieldErrors[?(@.field == 'name')].code")
        .value(hasItem("NotBlank")))
.andExpect(jsonPath("$.fieldErrors[?(@.field == 'price')].code")
        .value(hasItem("Positive")));
```

Cú pháp JSONPath filter có thể phụ thuộc implementation. Nếu khó đọc, dùng `jsonPath("$.fieldErrors").value(...)` với matcher phù hợp hoặc deserialize body thành `ApiError` trong test.

Nếu message được localize theo `Accept-Language`, không nên khóa test vào một chuỗi message duy nhất trừ khi đó là contract. Hãy kiểm tra error code ổn định, field path và status; viết test riêng cho localization khi cần.

Đối với lỗi nested DTO, path có thể là `address.postalCode` hoặc `items[0].quantity` tùy binding result. Tài liệu nên giải thích định dạng path mà API trả về và giữ ví dụ nhất quán.

## 11. WebTestClient và REST Assured

### 11.1. WebTestClient

Ví dụ test negative bằng WebTestClient:

```java
webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "name", "",
        "price", -10,
        "email", "not-an-email"
    ))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody()
    .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
    .consumeWith(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Mã lỗi"),
            fieldWithPath("message").description("Mô tả lỗi"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Đường dẫn request"),
            fieldWithPath("fieldErrors").description("Danh sách lỗi"),
            fieldWithPath("fieldErrors[].field").description("Field lỗi"),
            fieldWithPath("fieldErrors[].code").description("Mã constraint"),
            fieldWithPath("fieldErrors[].message").description("Thông báo")
        )
    ));
```

Đây là ví dụ theo WebTestClient tích hợp Spring REST Docs; kiểu body và cách cấu hình test cần phù hợp stack MVC/WebFlux của ứng dụng. Với WebFlux, exception validation và controller signature có thể khác MVC; cần kiểm tra theo runtime đang dùng.

### 11.2. REST Assured

```java
given(this.spec)
    .filter(document("products-create-validation-error",
        responseFields(
            fieldWithPath("code").description("Mã lỗi"),
            fieldWithPath("message").description("Mô tả lỗi"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Đường dẫn request"),
            fieldWithPath("fieldErrors").description("Danh sách lỗi"),
            fieldWithPath("fieldErrors[].field").description("Field lỗi"),
            fieldWithPath("fieldErrors[].code").description("Mã constraint"),
            fieldWithPath("fieldErrors[].message").description("Thông báo")
        )))
    .contentType("application/json")
    .body(Map.of(
        "name", "",
        "price", -10,
        "email", "not-an-email"
    ))
    .when()
    .post("/api/products")
    .then()
    .statusCode(400)
    .body("code", equalTo("VALIDATION_FAILED"));
```

Cách gắn filter và body phụ thuộc module REST Assured cùng phiên bản. Điều cần giữ là negative assertion và snippet descriptor phản ánh response lỗi thực tế.

## 12. Tổ chức Asciidoctor cho error catalog

Sau khi chạy test, output có thể gồm:

```text
build/generated-snippets/
└── products-create-validation-error/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    ├── response-fields.adoc
    └── response-body.adoc
```

Chỉ các snippet được yêu cầu trong `document(...)` mới được sinh. Ví dụ trang tài liệu:

```adoc
= Product API
:toc: left

== Tạo sản phẩm

=== Request hợp lệ
include::{snippets}/products-create/http-request.adoc[]

=== Lỗi validation

Request gây lỗi:
include::{snippets}/products-create-validation-error/http-request.adoc[]

Response:
include::{snippets}/products-create-validation-error/http-response.adoc[]

Các field trong response lỗi:
include::{snippets}/products-create-validation-error/response-fields.adoc[]
```

Có thể tạo một mục riêng “Error responses” để client tra cứu các lỗi phổ biến. Đừng include body snippet nếu chưa tạo `responseBody()` hoặc snippet body tương ứng.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Constraint không chạy | Thiếu `@Valid` hoặc validation provider | Bật validation và kiểm tra controller signature |
| JSON sai cú pháp không vào handler validation | Deserialize thất bại trước Bean Validation | Xử lý `HttpMessageNotReadableException` riêng |
| Error body không ổn định | Mỗi controller tự tạo response khác nhau | Chuẩn hóa qua `@RestControllerAdvice` |
| Test phụ thuộc thứ tự field errors | Validator không cam kết thứ tự | Dùng matcher không phụ thuộc thứ tự |
| `responseFields(...)` báo field dư | Error DTO có field mới chưa mô tả | Review và cập nhật descriptor |
| Snippet lỗi thiếu field lồng | Descriptor path chưa bao phủ nested error structure | Thêm path như `fieldErrors[].field` |
| Dùng `responseBody()` nhưng mong kiểm tra schema | Body snippet chỉ hiển thị payload mẫu | Thêm `responseFields(...)` để mô tả contract |
| Handler bắt mọi `Exception` thành 400 | Gộp lỗi server với lỗi client | Xử lý exception theo nhóm và giữ 5xx cho lỗi server |
| Test standalone không dùng controller advice | Chưa đăng ký advice vào MockMvc | Dùng context test hoặc `.setControllerAdvice(...)` |
| Error message thay đổi làm test fail | Assertion khóa message không ổn định | Ưu tiên kiểm tra code, status và field path |
| Asciidoctor include thiếu file | Test chưa sinh snippet hoặc sai operation ID | Kiểm tra `document(...)` và task dependency |

## 14. Build và CI

Với Gradle và plugin Asciidoctor đã cấu hình, task tài liệu phải chạy sau test sinh snippet:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Luồng CI:

```text
Negative HTTP tests
        |
        +--> Bean Validation errors
        |
        +--> JSON binding errors
        |
        +--> Domain/business errors
        |
        v
Assert status + error code + field paths
        |
        v
Spring REST Docs response snippets
        |
        v
Asciidoctor / bước xuất Markdown
        |
        v
Kiểm tra include và xuất bản
```

CI nên chạy ít nhất một test cho mỗi nhóm lỗi được công bố. Nếu thay đổi error DTO hoặc exception handler, strict `responseFields(...)` giúp phát hiện field mới chưa được mô tả. Nếu chỉ sửa câu message, test nên tránh phụ thuộc chuỗi không thuộc contract ổn định.

Spring REST Docs thường sinh AsciiDoc. Nếu dự án xuất Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định có file snippet `.md`.

## 15. Bài thực hành

Với endpoint `POST /api/products`:

1. Tạo DTO có `@NotBlank`, `@Positive` và `@Email`.
2. Bật validation và gắn `@Valid` vào `@RequestBody`.
3. Tạo `ApiError` cùng `FieldErrorDetail`.
4. Viết handler cho `MethodArgumentNotValidException`.
5. Viết handler riêng cho JSON parse error và domain conflict.
6. Tạo MockMvc negative test cho tên rỗng, giá âm và email sai.
7. Assert HTTP status, error code và danh sách field errors.
8. Dùng `responseFields(...)` để tài liệu hóa error contract.
9. Thêm `responseBody()` nếu muốn include payload lỗi nguyên bản.
10. Tạo operation ID riêng cho validation, invalid JSON và conflict.
11. Include snippets vào trang Error responses.
12. Chạy test và Asciidoctor trong CI; xác nhận response fields mới chưa mô tả làm test thất bại.

### Câu hỏi tự đánh giá

- `@Valid` kích hoạt bước nào trong quá trình xử lý request?
- `MethodArgumentNotValidException` khác `HttpMessageNotReadableException` như thế nào?
- Vì sao error code nên ổn định hơn message?
- Khi nào dùng status 400 và khi nào dùng 409?
- `responseFields(...)` kiểm tra điều gì trong error payload?
- `responseBody()` khác `responseFields(...)` ở mục tiêu nào?
- Làm thế nào test field errors mà không phụ thuộc thứ tự?
- Vì sao không nên ánh xạ mọi exception thành 400?
- Khi error DTO có field mới, strict REST Docs giúp phát hiện ra sao?

**Ghi nhớ:** Validation test cần kiểm tra cả status lẫn error contract. Dùng `@Valid` cho constraint trên DTO, `@RestControllerAdvice` để chuẩn hóa response, negative tests để xác nhận hành vi và `responseFields(...)` để kiểm tra payload lỗi có được tài liệu hóa đầy đủ. Phân biệt lỗi parse/binding, Bean Validation và domain error để client có thể xử lý đúng.

## Tài liệu tham khảo

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Jakarta Bean Validation.
- [Spring Framework — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): xử lý exception trong Spring MVC.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `responseFields`, `responseBody` và payload snippets.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): tài liệu hóa response headers.
