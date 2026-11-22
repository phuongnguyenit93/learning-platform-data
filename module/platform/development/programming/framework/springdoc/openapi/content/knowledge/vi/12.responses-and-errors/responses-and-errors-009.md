# Mô tả lỗi thống nhất bằng DTO hoặc ProblemDetail

Một API tốt cần mô tả rõ cả kết quả thành công lẫn những tình huống request không thể hoàn tất. Khi mỗi controller trả lỗi theo một cấu trúc khác nhau, client phải viết nhiều nhánh xử lý và khó phân biệt lỗi nghiệp vụ với lỗi kỹ thuật. Một hợp đồng lỗi thống nhất giúp client xử lý tự động, hỗ trợ quan sát hệ thống và làm cho tài liệu OpenAPI dễ sử dụng hơn.

Trong Spring Boot, có hai cách phổ biến để chuẩn hóa response lỗi:

- **DTO lỗi riêng của ứng dụng:** tự thiết kế cấu trúc như mã lỗi, thông điệp, đường dẫn, mã tương quan và danh sách lỗi validation.
- **ProblemDetail:** dùng mô hình chuẩn của Spring Framework dựa trên RFC 9457 để biểu diễn chi tiết một lỗi HTTP.

springdoc-openapi có thể mô tả cả hai cách bằng schema, ví dụ và annotation @ApiResponse. Việc chọn cách nào phụ thuộc vào hợp đồng hiện tại, nhu cầu tương thích và mức độ muốn tuân theo chuẩn HTTP. Dù chọn cách nào, cấu trúc JSON, HTTP status và tài liệu OpenAPI phải thống nhất với hành vi thật của ứng dụng.

## 1. Vì sao cần một định dạng lỗi thống nhất?

Giả sử cùng một API có ba endpoint trả lỗi theo ba hình dạng:

~~~json
{
  "message": "Không tìm thấy sản phẩm"
}
~~~

~~~json
{
  "error": "PRODUCT_NOT_FOUND",
  "description": "Sản phẩm không tồn tại"
}
~~~

~~~json
{
  "status": 400,
  "errors": [
    {
      "field": "price",
      "message": "Giá phải lớn hơn 0"
    }
  ]
}
~~~

Client phải kiểm tra nhiều tên field và nhiều cấu trúc khác nhau. Việc ghi log, hiển thị lỗi cho người dùng hoặc tự động thử lại cũng trở nên phức tạp.

Một hợp đồng lỗi nhất quán mang lại các lợi ích:

- Client có thể dùng một bộ xử lý chung cho phần lớn lỗi.
- Mã lỗi máy đọc được giúp client phân biệt lỗi nghiệp vụ mà không phải phân tích câu chữ.
- Lỗi validation có thể chỉ rõ field và quy tắc không đạt.
- Trace ID hoặc correlation ID giúp liên kết response với log và trace của server.
- OpenAPI có thể tái sử dụng một schema lỗi cho nhiều operation.
- Nhóm phát triển dễ kiểm thử và phát hiện khi hành vi runtime lệch khỏi hợp đồng.

Định dạng thống nhất không có nghĩa mọi lỗi đều có cùng HTTP status. 400, 401, 403, 404, 409 và 500 vẫn diễn đạt những tình huống khác nhau; phần body chỉ cần có cấu trúc nhất quán.

## 2. Hai lựa chọn: DTO lỗi riêng và ProblemDetail

| Tiêu chí | DTO lỗi riêng | ProblemDetail |
|---|---|---|
| Cấu trúc | Do ứng dụng thiết kế | Theo RFC 9457 |
| Tên field | Tự chọn, ví dụ code, message, violations | Các member chuẩn như type, title, status, detail, instance |
| Mở rộng | Thêm field theo hợp đồng của ứng dụng | Thêm extension member |
| Tích hợp Spring MVC | Dùng @RestControllerAdvice và ResponseEntity | Spring Framework hỗ trợ trực tiếp |
| Media type | Thường là application/json | application/problem+json |
| Phù hợp | API đã có định dạng lỗi riêng hoặc cần cấu trúc đặc thù | API mới hoặc muốn dùng chuẩn lỗi HTTP phổ biến |

DTO riêng có thể là lựa chọn hợp lý khi một hệ thống đã có hợp đồng lỗi được nhiều client sử dụng. ProblemDetail phù hợp khi muốn dùng một định dạng chuẩn và các member có ý nghĩa rõ ràng giữa nhiều hệ thống.

Không nên công bố một DTO tùy ý dưới media type application/problem+json rồi coi đó là Problem Details. Nếu chọn media type này, body cần tuân theo cấu trúc và ngữ nghĩa của RFC 9457. Nếu body có cấu trúc riêng như {code, message, path}, dùng application/json hoặc media type riêng đã được thống nhất.

## 3. ProblemDetail và RFC 9457

RFC 9457 định nghĩa định dạng Problem Details for HTTP APIs. Đây là chuẩn hiện hành thay thế RFC 7807. Spring Framework 6 cung cấp lớp org.springframework.http.ProblemDetail để biểu diễn response theo chuẩn này.

Một Problem Detail có thể chứa các member chuẩn:

| Member | Kiểu thường dùng | Ý nghĩa |
|---|---|---|
| type | URI reference | Định danh loại vấn đề; nếu không có thì mặc định là about:blank |
| title | String | Tiêu đề ngắn, ổn định cho loại vấn đề |
| status | Integer | HTTP status tương ứng với vấn đề |
| detail | String | Giải thích cụ thể cho lần xảy ra lỗi |
| instance | URI reference | Định danh lần xảy ra lỗi cụ thể |

Ngoài các member chuẩn, server có thể thêm extension member như code, traceId hoặc violations. Các extension cần có tên và kiểu dữ liệu nhất quán.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Không tìm thấy sản phẩm",
  "status": 404,
  "detail": "Không tìm thấy sản phẩm có mã 42.",
  "instance": "/api/v1/products/42",
  "code": "PRODUCT_NOT_FOUND",
  "traceId": "8f3a1b7c2d"
}
~~~

type nên là URI ổn định để client có thể nhận diện loại lỗi. Có thể trỏ URI đó đến trang tài liệu giải thích nguyên nhân và cách xử lý. title nên ổn định theo loại lỗi; detail có thể thay đổi theo lần xảy ra cụ thể. status trong body phải nhất quán với HTTP status thực tế trên response.

Trong ví dụ, instance dùng request path để định vị request gây lỗi. Nếu cần định danh duy nhất từng lần xảy ra, có thể dùng URI occurrence riêng hoặc bổ sung request ID/trace ID ổn định; không dùng instance như mã loại lỗi.

Không đưa stack trace, câu lệnh SQL, tên máy chủ nội bộ, token, thông tin xác thực hoặc dữ liệu cá nhân nhạy cảm vào detail hay extension member.

## 4. Thiết kế DTO lỗi riêng

Nếu ứng dụng cần cấu trúc riêng, nên định nghĩa DTO rõ ràng và ổn định. Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

@Schema(name = "ApiErrorResponse", description = "Cấu trúc lỗi thống nhất của API.")
public record ApiErrorResponse(
    @Schema(description = "Thời điểm phát sinh lỗi theo UTC.",
            example = "2026-11-20T10:30:00Z")
    Instant timestamp,

    @Schema(description = "HTTP status trả về.", example = "404")
    int status,

    @Schema(description = "Mã lỗi ổn định để client xử lý.",
            example = "PRODUCT_NOT_FOUND")
    String code,

    @Schema(description = "Thông điệp an toàn dành cho client.",
            example = "Không tìm thấy sản phẩm được yêu cầu.")
    String message,

    @Schema(description = "Đường dẫn request gây lỗi.",
            example = "/api/v1/products/42")
    String path,

    @Schema(description = "Mã tương quan để tra cứu log.",
            example = "8f3a1b7c2d")
    String traceId,

    List<FieldViolation> violations
) {
    public record FieldViolation(
        @Schema(example = "price")
        String field,

        @Schema(example = "Giá phải lớn hơn 0.")
        String message
    ) {
    }
}
~~~

Các field có trách nhiệm khác nhau:

- status cho biết mã HTTP, còn HTTP status line vẫn là nguồn trạng thái giao thức chính.
- code là mã máy đọc được, nên giữ ổn định qua các phiên bản.
- message là thông điệp an toàn để hiển thị hoặc ghi nhận ở client; không dùng nó làm khóa logic.
- path cho biết endpoint liên quan.
- traceId giúp đội vận hành tìm log tương ứng.
- violations chứa lỗi theo field khi request không đạt validation.

Nếu một response không có lỗi theo field, có thể trả danh sách rỗng thay vì null để client xử lý đơn giản. Cần thống nhất quy ước này trong toàn bộ API.

## 5. Xây dựng response lỗi tập trung bằng @RestControllerAdvice

@RestControllerAdvice cho phép gom các phương thức xử lý exception vào một nơi. Annotation này kết hợp vai trò của @ControllerAdvice và @ResponseBody, vì vậy đối tượng trả về được ghi thành response body.

Ví dụ xử lý lỗi không tìm thấy sản phẩm và lỗi validation:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.List;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleProductNotFound(
            ProductNotFoundException ex,
            HttpServletRequest request) {

        var body = new ApiErrorResponse(
            Instant.now(),
            HttpStatus.NOT_FOUND.value(),
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm được yêu cầu.",
            request.getRequestURI(),
            MDC.get("traceId"),
            List.of()
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleValidation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        List<ApiErrorResponse.FieldViolation> violations =
            ex.getBindingResult().getFieldErrors().stream()
                .map(error -> new ApiErrorResponse.FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        var body = new ApiErrorResponse(
            Instant.now(),
            HttpStatus.BAD_REQUEST.value(),
            "VALIDATION_FAILED",
            "Dữ liệu request không hợp lệ.",
            request.getRequestURI(),
            MDC.get("traceId"),
            violations
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Ví dụ giả định ứng dụng có ProductNotFoundException, DTO ApiErrorResponse và cấu hình MDC đặt traceId trong logging context. Nếu chưa có trace ID, có thể trả null, bỏ field hoặc tạo mã tương quan theo quy ước chung.

MethodArgumentNotValidException thường phát sinh khi tham số @RequestBody được đánh dấu @Valid và dữ liệu vi phạm Bean Validation. Nếu ứng dụng dùng @Validated cho method validation, một số lỗi có thể đi qua loại exception khác; cần xử lý theo phiên bản Spring và cách bật method validation của dự án.

Không trả nguyên văn error.getDefaultMessage() nếu message có thể chứa dữ liệu nội bộ hoặc chưa được kiểm soát. Với API công khai, nên dùng message đã được chuẩn hóa và có thể bản địa hóa.

## 6. Ánh xạ lỗi nghiệp vụ sang HTTP status và error code

Mỗi loại lỗi nên có mã HTTP và mã lỗi máy đọc được phù hợp. Ví dụ:

| HTTP status | Error code ví dụ | Tình huống |
|---|---|---|
| 400 Bad Request | VALIDATION_FAILED | Body sai định dạng hoặc vi phạm validation |
| 401 Unauthorized | AUTHENTICATION_REQUIRED | Thiếu hoặc thông tin xác thực không hợp lệ |
| 403 Forbidden | ACCESS_DENIED | Đã xác thực nhưng không có quyền |
| 404 Not Found | PRODUCT_NOT_FOUND | Không tìm thấy tài nguyên |
| 409 Conflict | ORDER_STATE_CONFLICT | Trạng thái hiện tại không cho phép thao tác |
| 415 Unsupported Media Type | UNSUPPORTED_MEDIA_TYPE | Content-Type không được endpoint hỗ trợ |
| 429 Too Many Requests | RATE_LIMIT_EXCEEDED | Vượt giới hạn request |
| 500 Internal Server Error | INTERNAL_ERROR | Lỗi không dự kiến ở server |

Đây là ví dụ quy ước, không phải danh sách bắt buộc cho mọi API. Chọn status theo bản chất lỗi và giữ nhất quán giữa các endpoint. 401 và 403 không thay thế nhau; 409 nên dùng khi xung đột với trạng thái tài nguyên; 500 không nên được dùng để che lỗi validation hoặc lỗi nghiệp vụ đã biết.

code nên ổn định và không phụ thuộc ngôn ngữ. message có thể được dịch hoặc điều chỉnh câu chữ mà không làm hỏng logic client. Tránh yêu cầu client so sánh nguyên văn message để quyết định nhánh xử lý.

## 7. Sử dụng ProblemDetail trong Spring Framework

Spring Framework 6 cung cấp ProblemDetail trong package org.springframework.http. Có thể tạo đối tượng bằng forStatus hoặc forStatusAndDetail, sau đó bổ sung thông tin chuẩn và extension member.

Ví dụ:

~~~java
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;

@RestControllerAdvice
public class ProblemExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail handleProductNotFound(
            ProductNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy sản phẩm được yêu cầu."
        );

        problem.setType(URI.create(
            "https://api.example.com/problems/product-not-found"
        ));
        problem.setTitle("Không tìm thấy sản phẩm");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "PRODUCT_NOT_FOUND");
        problem.setProperty("traceId", MDC.get("traceId"));

        return problem;
    }
}
~~~

Khi Spring MVC ghi một ProblemDetail, framework hỗ trợ media type application/problem+json và dùng status được khai báo trong đối tượng để thiết lập HTTP response. Hãy kiểm tra response thực tế trong phiên bản Spring đang chạy.

ProblemDetail có thể thêm extension bằng setProperty. Spring/Jackson hỗ trợ ghi các property mở rộng thành member cấp cao nhất trong JSON thay vì gom chúng vào một object properties. Ví dụ code và traceId sẽ nằm cùng cấp với type, title, status, detail và instance.

## 8. Bật hỗ trợ Problem Details trong Spring Boot

Spring Boot 3 với Spring MVC có thể bật hỗ trợ Problem Details cho các lỗi HTTP được framework xử lý bằng cấu hình:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Khi bật, Spring Boot đăng ký cơ chế xử lý Problem Details cho một số exception chuẩn của Spring MVC. Cấu hình này không tự động biến mọi exception nghiệp vụ của ứng dụng thành ProblemDetail. Với exception riêng như ProductNotFoundException, vẫn cần @ExceptionHandler hoặc cơ chế xử lý tương ứng.

Nếu cần tùy biến cách xử lý các exception MVC chuẩn, có thể kế thừa ResponseEntityExceptionHandler trong một lớp @ControllerAdvice và override các phương thức phù hợp, ví dụ xử lý lỗi body không đọc được hoặc validation. Cần kiểm tra chữ ký phương thức theo phiên bản Spring Framework đang dùng vì một số phương thức có thể thay đổi giữa các phiên bản.

Các lỗi xác thực và phân quyền có thể xảy ra trong Spring Security filter chain trước khi request đến controller. Vì vậy, @RestControllerAdvice không nhất thiết xử lý được tất cả lỗi 401 và 403. Hãy cấu hình AuthenticationEntryPoint và AccessDeniedHandler để trả cùng định dạng lỗi với phần còn lại của API.

## 9. So sánh hai ví dụ response

### 9.1. DTO riêng

~~~json
{
  "timestamp": "2026-11-20T10:30:00Z",
  "status": 404,
  "code": "PRODUCT_NOT_FOUND",
  "message": "Không tìm thấy sản phẩm được yêu cầu.",
  "path": "/api/v1/products/42",
  "traceId": "8f3a1b7c2d",
  "violations": []
}
~~~

Đây là cấu trúc do ứng dụng định nghĩa. Client có thể dựa vào code, status và violations. Nếu dùng cấu trúc này, media type thường là application/json.

### 9.2. ProblemDetail

~~~json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Không tìm thấy sản phẩm",
  "status": 404,
  "detail": "Không tìm thấy sản phẩm có mã 42.",
  "instance": "/api/v1/products/42",
  "code": "PRODUCT_NOT_FOUND",
  "traceId": "8f3a1b7c2d"
}
~~~

Đây là Problem Details với hai extension member code và traceId. Response nên dùng application/problem+json. Các member chuẩn có ý nghĩa theo RFC 9457; extension bổ sung thông tin riêng cho ứng dụng.

## 10. Mô tả DTO lỗi bằng OpenAPI và springdoc

Nếu controller trả lỗi theo DTO riêng, có thể khai báo response trong @ApiResponse:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping
@Operation(summary = "Tạo sản phẩm")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Sản phẩm đã được tạo."
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Mã sản phẩm đã tồn tại.",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    )
})
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    // ...
}
~~~

Đối với lỗi có ví dụ JSON, thêm @ExampleObject vào @Content để người tích hợp nhìn thấy payload thực tế. Có thể dùng cùng một schema cho nhiều status, nhưng description phải giải thích điều kiện phát sinh từng lỗi.

## 11. Mô tả ProblemDetail trong OpenAPI

Khi dùng ProblemDetail, khai báo media type application/problem+json và mô tả schema cùng ví dụ:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy sản phẩm.",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class),
        examples = @ExampleObject(
            name = "product-not-found",
            value = """
                {
                  "type": "https://api.example.com/problems/product-not-found",
                  "title": "Không tìm thấy sản phẩm",
                  "status": 404,
                  "detail": "Không tìm thấy sản phẩm có mã 42.",
                  "instance": "/api/v1/products/42",
                  "code": "PRODUCT_NOT_FOUND",
                  "traceId": "8f3a1b7c2d"
                }
                """
        )
    )
)
~~~

Schema của ProblemDetail thể hiện các member chuẩn. Các extension được thêm động qua setProperty có thể không xuất hiện đầy đủ trong schema sinh tự động. Nếu client cần biết rõ extension như code, traceId hoặc violations, hãy mô tả chúng trong component schema riêng và dùng schema đó trong @ApiResponse, đồng thời giữ ví dụ trùng với JSON runtime.

Ví dụ schema tài liệu cho một Problem Detail có extension:

~~~yaml
ApiProblem:
  type: object
  properties:
    type:
      type: string
      format: uri
    title:
      type: string
    status:
      type: integer
      format: int32
    detail:
      type: string
    instance:
      type: string
      format: uri-reference
    code:
      type: string
    traceId:
      type: string
~~~

Các member chuẩn không nhất thiết đều phải xuất hiện trong mọi Problem Detail; hãy đặt required chỉ khi API thực sự bảo đảm member đó luôn có mặt. Extension cũng nên có kiểu và ý nghĩa ổn định.

## 12. Tái sử dụng response lỗi trong nhiều operation

Nếu mọi endpoint dùng cùng cấu trúc lỗi, không nên lặp lại annotation dài ở mọi controller mà không có quy ước. Có thể tái sử dụng response bằng cách:

- Tạo annotation tổng hợp chứa các @ApiResponse thường gặp.
- Khai báo reusable response trong OpenAPI components và tham chiếu bằng $ref.
- Dùng OpenApiCustomizer để bổ sung response chung theo quy tắc của dự án.

Ví dụ reusable response trong YAML:

~~~yaml
components:
  responses:
    ValidationError:
      description: Request không vượt qua kiểm tra dữ liệu.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    InternalError:
      description: Server gặp lỗi không dự kiến.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
paths:
  /api/v1/products:
    post:
      responses:
        '400':
          $ref: '#/components/responses/ValidationError'
        '500':
          $ref: '#/components/responses/InternalError'
~~~

Một @RestControllerAdvice xử lý exception ở runtime không đảm bảo mọi operation trong tài liệu OpenAPI tự động liệt kê tất cả response tương ứng. Hãy kiểm tra /v3/api-docs; nếu response toàn cục chưa xuất hiện, dùng annotation, reusable response hoặc customizer để bổ sung.

## 13. Mô tả lỗi validation theo field

Lỗi validation thường cần nhiều thông tin hơn một thông điệp chung. Client cần biết field nào không hợp lệ và quy tắc nào bị vi phạm.

Ví dụ DTO lỗi:

~~~java
public record ValidationViolation(
    String field,
    String code,
    String message,
    Object rejectedValue
) {
}
~~~

Có thể trả về:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu request không hợp lệ.",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Email không đúng định dạng."
    },
    {
      "field": "quantity",
      "code": "Positive",
      "message": "Số lượng phải lớn hơn 0."
    }
  ]
}
~~~

rejectedValue có thể hữu ích trong hệ thống nội bộ nhưng cần cân nhắc trước khi trả ra ngoài. Giá trị bị từ chối có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc thông tin nhạy cảm. Với API công khai, thường chỉ cần tên field, mã quy tắc và thông điệp an toàn.

Đối với DTO lồng nhau hoặc collection, tên field có thể chứa đường dẫn như items[0].quantity. Hãy thống nhất định dạng đường dẫn để client có thể liên kết lỗi với trường nhập liệu.

## 14. Xử lý lỗi không dự kiến và bảo vệ thông tin nội bộ

Exception handler tổng quát có thể bắt các exception không dự kiến và trả 500 Internal Server Error với mã lỗi chung:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<ApiErrorResponse> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    log.error("Unexpected API error at {}", request.getRequestURI(), ex);

    var body = new ApiErrorResponse(
        Instant.now(),
        HttpStatus.INTERNAL_SERVER_ERROR.value(),
        "INTERNAL_ERROR",
        "Đã xảy ra lỗi trong quá trình xử lý yêu cầu.",
        request.getRequestURI(),
        MDC.get("traceId"),
        List.of()
    );

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
}
~~~

Log nội bộ có thể lưu stack trace để điều tra. Response gửi client chỉ nên chứa thông tin đủ để nhận diện lỗi và liên hệ hỗ trợ. Không trả ex.getMessage() một cách mặc định vì thông điệp exception có thể chứa câu SQL, đường dẫn file, tên lớp hoặc dữ liệu nhạy cảm.

Đặt handler tổng quát sau các handler cụ thể về mặt thiết kế và tránh bắt exception quá rộng rồi biến mọi tình huống thành 500. Những lỗi HTTP đã biết cần giữ đúng status và error code.

## 15. Bản địa hóa thông điệp lỗi

Mã lỗi nên ổn định và không phụ thuộc ngôn ngữ. Thông điệp có thể được bản địa hóa theo locale của client:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu request không hợp lệ.",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Email không đúng định dạng."
    }
  ]
}
~~~

Spring hỗ trợ MessageSource và LocaleResolver để tra thông điệp theo locale. Với Bean Validation, message key có thể được đặt trong annotation và phân giải từ resource bundle. Nếu API hỗ trợ Accept-Language, hãy xác định rõ ngôn ngữ mặc định và cách xử lý locale không được hỗ trợ.

Client nên dựa vào code để xử lý logic và dùng message để hiển thị. Không dùng nội dung đã dịch làm mã định danh.

## 16. Kiểm thử hợp đồng lỗi

Kiểm thử cần xác minh cả HTTP status, media type và nội dung JSON. Ví dụ với DTO riêng:

~~~java
mockMvc.perform(post("/api/v1/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "",
              "price": -1
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.violations").isArray());
~~~

Với ProblemDetail:

~~~java
mockMvc.perform(get("/api/v1/products/42"))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.valueOf("application/problem+json")
    ))
    .andExpect(jsonPath("$.type").value(
        "https://api.example.com/problems/product-not-found"
    ))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
~~~

Đây là đoạn kiểm thử minh họa; cần thay endpoint, payload và mã lỗi theo ứng dụng. Ngoài kiểm thử runtime, nên kiểm tra OpenAPI JSON để xác nhận:

1. Operation khai báo các response lỗi mà API thực sự có thể trả về.
2. Mỗi response có đúng media type.
3. Schema và example khớp với body runtime.
4. HTTP status trong response body khớp status line.
5. Các extension member quan trọng được mô tả trong schema.
6. Các lỗi xác thực/phân quyền từ Spring Security cũng theo cùng hợp đồng.

## 17. Thay đổi hợp đồng lỗi mà không phá vỡ client

Định dạng lỗi là một phần của API contract. Khi đã được client sử dụng, thay đổi tên field, kiểu dữ liệu hoặc ý nghĩa error code có thể gây breaking change.

Một số quy tắc an toàn:

- Giữ nguyên error code đã công bố; thêm code mới khi có loại lỗi mới.
- Có thể bổ sung field tùy chọn nếu client được thiết kế để bỏ qua field chưa biết.
- Không đổi kiểu status từ number sang string.
- Không đổi media type mà không đánh giá tác động tới client.
- Không đổi ý nghĩa của detail hoặc message thành khóa logic.
- Khi thay đổi cấu trúc lớn, cân nhắc phiên bản API hoặc một giai đoạn chuyển tiếp có tài liệu rõ ràng.

ProblemDetail có lợi thế là các member chuẩn đã có ngữ nghĩa chung. Extension member vẫn là một phần hợp đồng riêng của API và cần được quản lý tương tự DTO.

## 18. Chọn phương án phù hợp

| Tình huống | Gợi ý |
|---|---|
| API mới, muốn dùng chuẩn HTTP phổ biến | Ưu tiên ProblemDetail theo RFC 9457 |
| API hiện tại đã có DTO lỗi được nhiều client sử dụng | Tiếp tục DTO và chuẩn hóa dần nếu cần |
| Cần danh sách lỗi validation theo field | DTO riêng hoặc extension violations trên ProblemDetail |
| Cần tích hợp với lỗi Spring MVC chuẩn | Dùng ProblemDetail và hỗ trợ của Spring Framework |
| Cần một cấu trúc lỗi đặc thù cho sản phẩm | Dùng DTO có schema rõ ràng |
| Có lỗi phát sinh trong Spring Security filter chain | Chuẩn hóa cả AuthenticationEntryPoint và AccessDeniedHandler |

Không cần trộn hai định dạng trong cùng một endpoint nếu không có lý do rõ ràng. Nếu hệ thống đang chuyển từ DTO sang ProblemDetail, hãy quy định endpoint nào dùng định dạng nào, công bố media type tương ứng và tránh để client phải đoán cấu trúc theo từng loại exception.

## 19. Ghi nhớ

- Chuẩn hóa lỗi giúp client xử lý nhất quán và giúp OpenAPI tái sử dụng schema.
- DTO riêng phù hợp với hợp đồng đặc thù; ProblemDetail là lựa chọn chuẩn hóa theo RFC 9457.
- ProblemDetail có các member type, title, status, detail, instance và cho phép extension member.
- application/problem+json dành cho response theo Problem Details; DTO riêng thường dùng application/json.
- Dùng @RestControllerAdvice để xử lý exception tập trung; xử lý lỗi Spring Security riêng ở filter chain.
- Error code nên ổn định và máy đọc được; message nên an toàn, có thể bản địa hóa.
- Không trả stack trace hoặc chi tiết nội bộ cho client.
- Springdoc cần mô tả response status, media type, schema và example; đừng giả định advice tự thêm mọi response vào từng operation.
- Kiểm thử cả response runtime và tài liệu /v3/api-docs.

Khi chuẩn hóa lỗi cho Spring Boot, hãy chọn một hợp đồng mà client có thể dựa vào lâu dài. Dùng DTO nếu ứng dụng cần cấu trúc riêng, hoặc ProblemDetail nếu muốn theo RFC 9457. Sau đó triển khai xử lý tập trung, khai báo rõ response bằng springdoc và kiểm thử để bảo đảm status, media type, schema cùng payload luôn khớp nhau.
