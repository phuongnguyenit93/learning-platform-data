# @ControllerAdvice, @ExceptionHandler và giới hạn suy luận lỗi

## 1. Vì sao xử lý lỗi là một phần của hợp đồng API?

Một API không chỉ mô tả dữ liệu khi request thành công. Client còn cần biết server phản hồi ra sao khi tài nguyên không tồn tại, dữ liệu đầu vào không hợp lệ, người gọi chưa được xác thực hoặc một quy tắc nghiệp vụ bị vi phạm.

Nếu mỗi controller tự xử lý lỗi theo cách riêng, response có thể thiếu nhất quán: endpoint trả chuỗi, endpoint khác trả object JSON, nơi dùng status 400 nhưng nơi khác dùng 422 cho cùng một loại lỗi. Client phải viết nhiều nhánh xử lý và khó phân biệt lỗi nghiệp vụ với lỗi hệ thống.

Spring Boot cung cấp cơ chế xử lý ngoại lệ tập trung bằng **@ControllerAdvice** và **@ExceptionHandler**. Springdoc OpenAPI có thể dùng metadata từ các handler này để mô tả response lỗi trong tài liệu. Tuy nhiên, mã nguồn có thể phát sinh nhiều ngoại lệ ở service, repository, security filter hoặc tầng chuyển đổi dữ liệu; không phải mọi nhánh lỗi đều có thể được suy luận chính xác chỉ từ chữ ký controller.

Cần phối hợp ba phần:

- **Runtime exception handling** quyết định ngoại lệ nào được bắt và HTTP response thực tế được trả về.
- **OpenAPI response description** mô tả status code, header, media type và schema lỗi cho client.
- **Integration/contract testing** xác minh tài liệu trùng khớp với hành vi của ứng dụng.

Mục tiêu là công bố các lỗi mà client có thể gặp, với cấu trúc ổn định và status code có ý nghĩa.

## 2. Luồng xử lý ngoại lệ trong Spring MVC

Một request có thể thất bại ở nhiều giai đoạn:

1. Spring nhận request và tìm handler phù hợp.
2. HttpMessageConverter/Jackson đọc body và chuyển JSON thành Java object.
3. Bean Validation kiểm tra DTO hoặc tham số.
4. Controller gọi service và các thành phần nghiệp vụ.
5. Ngoại lệ có thể phát sinh từ controller, service, repository hoặc tầng bảo mật.
6. Spring tìm exception handler phù hợp.
7. Handler tạo response gồm status, headers và body.
8. Client nhận response theo hợp đồng HTTP.

Ví dụ, JSON sai cú pháp có thể gây **HttpMessageNotReadableException** trước khi phương thức controller được gọi. Request body deserialize thành công nhưng vi phạm @NotBlank có thể gây **MethodArgumentNotValidException**. Service không tìm thấy sản phẩm có thể ném **ProductNotFoundException**. Ba trường hợp này có nguồn gốc khác nhau nhưng đều có thể được ánh xạ thành response lỗi có cấu trúc.

Springdoc không chạy request qua các bước trên để phát hiện mọi lỗi. Thư viện tạo OpenAPI document từ metadata của ứng dụng, annotation và cấu hình mà nó có thể quan sát. Vì vậy, việc khai báo exception handler và response metadata rõ ràng rất quan trọng.

## 3. @ControllerAdvice và @RestControllerAdvice

**@ControllerAdvice** cho phép áp dụng các thành phần xử lý chung cho nhiều controller. Nó thường được dùng cho exception handling, data binding hoặc model attribute dùng chung.

**@RestControllerAdvice** là biến thể kết hợp @ControllerAdvice và @ResponseBody. Kết quả trả về từ handler được ghi vào response body thông qua message converter, phù hợp với REST API trả JSON.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {
    // Các phương thức @ExceptionHandler dùng chung
}
~~~

Nếu dùng @ControllerAdvice trong ứng dụng REST, handler có thể trả ResponseEntity hoặc dùng thêm @ResponseBody để body được serialize. Với REST API, @RestControllerAdvice thường giúp ý định rõ ràng hơn.

Có thể giới hạn phạm vi advice bằng package, annotation hoặc kiểu controller. Ví dụ, một advice có thể chỉ áp dụng cho controller thuộc package api.admin. Phạm vi runtime này cũng cần được cân nhắc khi mô tả response chung trong OpenAPI.

## 4. @ExceptionHandler ánh xạ ngoại lệ thành response

Annotation **@ExceptionHandler** chỉ định phương thức xử lý một hoặc nhiều loại exception. Spring tìm handler phù hợp khi ngoại lệ phát sinh trong phạm vi áp dụng.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleProductNotFound(
        ProductNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm"
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

Phương thức trên chuyển ProductNotFoundException thành HTTP 404 với body ApiError. Handler có thể nhận exception, WebRequest, HttpServletRequest hoặc các tham số hỗ trợ khác tùy tình huống.

Một handler có thể xử lý nhiều loại exception:

~~~java
@ExceptionHandler({
    InvalidOrderException.class,
    OrderStateConflictException.class
})
public ResponseEntity<ApiError> handleOrderErrors(RuntimeException exception) {
    ApiError body = new ApiError(
        "ORDER_INVALID",
        "Yêu cầu không phù hợp với trạng thái đơn hàng"
    );

    return ResponseEntity.unprocessableEntity().body(body);
}
~~~

Khi gom nhiều exception vào một handler, cần bảo đảm chúng thực sự có cùng ý nghĩa HTTP và cùng cấu trúc lỗi. Nếu một loại lỗi cần status hoặc error code khác, nên tách handler để hợp đồng không trở nên mơ hồ.

## 5. @ResponseStatus và ResponseEntity

Spring có hai cách phổ biến để xác định status của response lỗi.

### 5.1. Dùng @ResponseStatus

Có thể gắn @ResponseStatus lên exception class:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

Khi exception được ném và không bị handler khác thay thế, Spring ánh xạ nó thành status 404. Thuộc tính reason có thể cung cấp lý do, nhưng với REST API nên tránh đưa thông tin nội bộ hoặc chi tiết nhạy cảm vào reason.

Cũng có thể đặt @ResponseStatus trên phương thức @ExceptionHandler:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
@ResponseStatus(HttpStatus.NOT_FOUND)
public ApiError handle(ProductNotFoundException exception) {
    return new ApiError("PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm");
}
~~~

Với @RestControllerAdvice, ApiError được serialize thành response body.

### 5.2. Dùng ResponseEntity

ResponseEntity phù hợp khi status hoặc header phụ thuộc dữ liệu và logic xử lý:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ApiError> handle(ProductNotFoundException exception) {
    ApiError body = new ApiError(
        "PRODUCT_NOT_FOUND",
        "Không tìm thấy sản phẩm"
    );

    return ResponseEntity
        .status(HttpStatus.NOT_FOUND)
        .header("X-Error-Code", "PRODUCT_NOT_FOUND")
        .body(body);
}
~~~

ResponseEntity cho phép điều khiển status, header và body trong cùng một kết quả. Dù dùng cách nào, response OpenAPI cần mô tả đúng status và payload thực tế.

Không nên giả định @ResponseStatus hoặc @ExceptionHandler tự tạo đầy đủ schema lỗi trong mọi phiên bản/cấu hình Springdoc. Hãy xác minh document và bổ sung @ApiResponse khi cần.

## 6. Thiết kế một error response thống nhất

Một API có thể chuẩn hóa lỗi bằng DTO dùng chung:

~~~java
public record ApiError(
    String code,
    String message,
    String path
) {}
~~~

Ví dụ JSON:

~~~json
{
  "code": "PRODUCT_NOT_FOUND",
  "message": "Không tìm thấy sản phẩm",
  "path": "/api/products/42"
}
~~~

Các trường thường hữu ích:

| Trường | Mục đích |
|---|---|
| code | Mã lỗi ổn định để client xử lý theo chương trình |
| message | Thông báo dễ hiểu cho người dùng hoặc lập trình viên |
| path | Đường dẫn request phát sinh lỗi |
| timestamp | Thời điểm ghi nhận lỗi nếu cần đối soát |
| traceId | Mã tương quan để tra log giữa các dịch vụ |
| violations | Danh sách lỗi validation theo trường |

Không nhất thiết phải đưa tất cả trường vào mọi response. Cần chọn cấu trúc phù hợp với nhu cầu client và chính sách dữ liệu. Error code nên ổn định hơn message vì message có thể được thay đổi, dịch ngôn ngữ hoặc điều chỉnh cách diễn đạt.

Tránh trả stack trace, SQL, tên bảng, đường dẫn file nội bộ, token hoặc chi tiết cấu hình trong response công khai. Thông tin kỹ thuật đầy đủ nên nằm trong log có kiểm soát truy cập; response chỉ nên cung cấp thông tin cần thiết để client hiểu và xử lý lỗi.

## 7. Dùng ProblemDetail khi ứng dụng hỗ trợ

Spring Framework 6 cung cấp **ProblemDetail** để biểu diễn lỗi theo định dạng Problem Details for HTTP APIs. Spring Boot 3 có thể sử dụng kiểu này trong REST exception handling.

Ví dụ:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ProblemDetail> handleNotFound(
    ProductNotFoundException exception
) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy sản phẩm được yêu cầu"
    );

    problem.setTitle("Product not found");
    problem.setProperty("code", "PRODUCT_NOT_FOUND");

    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
}
~~~

ProblemDetail có các thuộc tính chuẩn như type, title, status, detail và instance; ứng dụng có thể thêm extension properties như code. Springdoc có thể mô tả kiểu này tùy phiên bản và cấu hình. Nếu cần hợp đồng ổn định cho client, hãy kiểm tra JSON serialize thực tế và schema sinh ra, đặc biệt khi thêm thuộc tính tùy biến.

Không nên vừa dùng ProblemDetail vừa công bố một ApiError schema khác cho cùng response nếu runtime chỉ trả một trong hai. Chọn cấu trúc thống nhất hoặc mô tả rõ các media type/response variant nếu thực sự có nhiều định dạng.

## 8. Khai báo response lỗi tường minh bằng @ApiResponse

Annotation **@ApiResponse** thuộc OpenAPI annotations và dùng để mô tả một response của operation. Các thuộc tính quan trọng gồm:

- **responseCode**: HTTP status code hoặc giá trị default.
- **description**: ý nghĩa response.
- **content**: media type và schema body.
- **headers**: các response header mà client cần biết.
- **links**: liên kết tới operation liên quan nếu hợp đồng cần mô tả.

Ví dụ:

~~~java
@GetMapping("/api/products/{id}")
@Operation(summary = "Lấy sản phẩm theo mã")
@ApiResponses({
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
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ProductResponse findById(@PathVariable Long id) {
    return productService.getByIdOrThrow(id);
}
~~~

Khai báo này mô tả response thành công 200 và lỗi 404. Controller/service vẫn phải thực sự trả các kết quả tương ứng. Annotation không thay đổi logic xử lý ngoại lệ.

Nếu một response không có body, có thể khai báo description mà không cần content:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Xóa tài nguyên thành công"
)
~~~

Không nên gắn schema body cho 204 No Content nếu runtime không trả body.

## 9. Giới hạn suy luận lỗi từ @ControllerAdvice

Springdoc có hỗ trợ thu thập thông tin response từ các phương thức trong @ControllerAdvice/@RestControllerAdvice. Trong các phiên bản hỗ trợ, các response này có thể được đưa vào nhiều operation như **generic responses**. Cấu hình springdoc.override-with-generic-response điều khiển việc áp dụng response chung này; giá trị mặc định thường bật trong các phiên bản có hỗ trợ, nhưng cần kiểm tra cấu hình và tài liệu đúng phiên bản dự án.

Cơ chế này hữu ích với lỗi thật sự có thể phát sinh trên hầu hết endpoint, chẳng hạn một response xác thực chung hoặc lỗi hệ thống chuẩn hóa. Tuy nhiên, nó có giới hạn quan trọng:

- Springdoc không phân tích toàn bộ call graph để biết endpoint nào có thể ném một exception.
- Một handler có thể chỉ áp dụng cho một nhóm controller, nhưng response suy luận tự động có thể xuất hiện rộng hơn phạm vi nghiệp vụ mong muốn tùy cách cấu hình.
- Exception có thể được ném bởi service, repository, filter hoặc thư viện bên ngoài mà không được thể hiện trên chữ ký controller.
- Một exception có thể được xử lý bởi nhiều lớp, thứ tự ưu tiên và phạm vi advice ảnh hưởng đến handler thực sự được gọi.
- Status code và body có thể phụ thuộc điều kiện runtime, không thể suy ra chỉ từ kiểu exception.
- Handler có thể trả response khác nhau theo loại exception hoặc theo dữ liệu request.

Ví dụ, ProductNotFoundException chỉ có thể phát sinh ở endpoint tìm sản phẩm. Nếu response 404 từ advice được thêm như generic response vào mọi operation, tài liệu có thể khiến client nghĩ endpoint tạo đơn hàng, đăng nhập hoặc tải báo cáo cũng có thể trả lỗi 404 với cùng ý nghĩa. Đây là tài liệu dư thừa hoặc gây hiểu nhầm.

Vì vậy, generic response chỉ nên dùng khi response thực sự chung và phù hợp với phạm vi operation. Với lỗi phụ thuộc nghiệp vụ hoặc endpoint cụ thể, nên khai báo response tại operation liên quan.

## 10. Điều khiển generic responses bằng springdoc.override-with-generic-response

Trong các phiên bản Springdoc hỗ trợ thuộc tính này, có thể tắt việc ghi đè/bổ sung generic responses từ @ControllerAdvice:

~~~yaml
springdoc:
  override-with-generic-response: false
~~~

Khi tắt, nhóm phát triển cần khai báo các response cần thiết trực tiếp trên operation hoặc bằng một cơ chế tùy biến OpenAPI có phạm vi rõ ràng. Điều này hữu ích khi advice xử lý nhiều exception khác nhau nhưng không phải endpoint nào cũng có thể phát sinh chúng.

Nếu bật generic responses, hãy xem OpenAPI JSON để xác định response nào đang được thêm vào operation. Đừng mặc định mọi response trong advice đều phù hợp cho toàn bộ API.

Tên thuộc tính, mặc định và chi tiết áp dụng có thể thay đổi theo dòng Springdoc. Khi nâng cấp, đối chiếu cấu hình của đúng phiên bản dependency. Việc thay đổi thuộc tính chỉ ảnh hưởng cách tạo tài liệu; nó không thay đổi cách Spring xử lý exception ở runtime.

## 11. Khi nào dùng response chung và khi nào dùng response riêng?

Có thể chia lỗi thành hai nhóm để quyết định cách công bố:

| Nhóm lỗi | Ví dụ | Cách mô tả phù hợp |
|---|---|---|
| Lỗi hạ tầng hoặc giao thức có thể xuất hiện rộng | 401, 403, lỗi xác thực chung, 500 | Response dùng chung nếu thực sự áp dụng cho các operation liên quan |
| Lỗi nghiệp vụ theo operation | 404 sản phẩm, 409 trùng mã đơn, 422 trạng thái đơn không hợp lệ | Khai báo trên operation có thể phát sinh lỗi |
| Lỗi validation của một loại request | 400 với violations theo DTO | Khai báo cho operation nhận DTO đó hoặc nhóm operation cùng quy tắc |
| Lỗi upload | 413 quá dung lượng, 415 media type không hỗ trợ | Khai báo cho endpoint upload hoặc nhóm endpoint tương ứng |
| Lỗi phụ thuộc quyền trên tài nguyên | 403 hoặc 404 tùy chính sách che giấu tài nguyên | Mô tả theo chính sách bảo mật và endpoint thực tế |

Một response chung không nhất thiết phải xuất hiện ở mọi endpoint. Nếu Spring Security bảo vệ một số đường dẫn, response 401/403 có thể chỉ liên quan đến những operation đó. Nếu một số endpoint public, không nên đưa response xác thực vào tài liệu như thể chúng bắt buộc phải đăng nhập.

Tài liệu tốt phản ánh điều client có thể gặp trong phạm vi cụ thể, không phải danh sách mọi exception có mặt trong ứng dụng.

## 12. Các lỗi thường gặp và cách ánh xạ

Một số exception phổ biến trong Spring MVC:

| Exception/tình huống | Nguyên nhân | Response thường dùng |
|---|---|---|
| MethodArgumentNotValidException | DTO request vi phạm Bean Validation | 400 Bad Request |
| HttpMessageNotReadableException | JSON sai cú pháp, sai kiểu hoặc không đọc được body | 400 Bad Request |
| HandlerMethodValidationException | Method validation trên handler, trong các phiên bản Spring Framework hỗ trợ | Thường 400 Bad Request |
| ConstraintViolationException | Constraint validation ở method/service hoặc tầng khác | Phụ thuộc nơi phát sinh và exception mapping |
| ProductNotFoundException | Không tìm thấy tài nguyên | 404 Not Found |
| DuplicateResourceException | Xung đột dữ liệu hoặc mã định danh | 409 Conflict |
| AccessDeniedException | Người dùng đã xác thực nhưng không đủ quyền | 403 Forbidden |
| AuthenticationException | Xác thực thất bại hoặc thiếu thông tin xác thực | 401 Unauthorized theo security entry point |
| ResponseStatusException | Ứng dụng chủ động yêu cầu status cụ thể | Theo status được chỉ định |
| Exception không dự kiến | Lỗi hệ thống chưa được xử lý riêng | Thường 500 Internal Server Error |

Bảng này chỉ là định hướng. Status thực tế phụ thuộc exception handler, Spring Security entry point, cấu hình framework và chính sách API. Ví dụ ConstraintViolationException có thể được xử lý thành 400, 422 hoặc response khác tùy tầng phát sinh và quy ước dự án.

Với Spring Framework 6.1 trở lên, method validation trên controller có thể sử dụng HandlerMethodValidationException trong một số trường hợp. Ứng dụng nâng cấp từ phiên bản cũ cần kiểm tra exception thực tế và cập nhật handler tương ứng.

## 13. Mô tả lỗi validation và lỗi parse JSON

Lỗi validation và lỗi parse thường cùng trả 400 nhưng nguyên nhân khác nhau.

**Validation error** xảy ra sau khi JSON đã được chuyển thành DTO. Ví dụ name rỗng, price âm hoặc danh sách items vượt giới hạn. Response có thể liệt kê lỗi theo field:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request chứa dữ liệu không hợp lệ",
  "violations": [
    {
      "field": "name",
      "message": "Tên sản phẩm không được để trống"
    },
    {
      "field": "price",
      "message": "Giá phải lớn hơn 0"
    }
  ]
}
~~~

**Parse/binding error** xảy ra khi Jackson không thể đọc body, chẳng hạn JSON sai cú pháp hoặc chuỗi không chuyển được thành số. Response có thể dùng cùng ApiError schema nhưng code khác:

~~~json
{
  "code": "INVALID_REQUEST_BODY",
  "message": "Nội dung JSON không hợp lệ"
}
~~~

Nếu hai trường hợp có cùng cấu trúc response, có thể tái sử dụng một schema với code khác nhau. Nếu violations chỉ xuất hiện ở validation error, mô tả trường này là tùy chọn hoặc dùng schema riêng cho từng loại lỗi.

Không nên công bố thông báo Jackson nguyên gốc nếu nó chứa chi tiết parser, tên lớp hoặc nội dung nhạy cảm. Hãy chuẩn hóa message cho client và ghi chi tiết kỹ thuật vào log.

## 14. Khai báo response chung bằng OpenAPI configuration

Nếu nhiều operation thật sự dùng chung một response, có thể cấu hình metadata OpenAPI theo cách tập trung. Một cách là khai báo response tại các operation bằng annotation; cách khác là dùng customizer để bổ sung response theo quy tắc có phạm vi rõ.

Ví dụ annotation ở operation:

~~~java
@Operation(
    summary = "Lấy danh sách sản phẩm",
    responses = {
        @ApiResponse(
            responseCode = "400",
            description = "Tham số truy vấn không hợp lệ",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "500",
            description = "Lỗi hệ thống",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    }
)
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Nếu dùng OpenApiCustomizer, cần kiểm soát operation nào được bổ sung response. Không nên thêm response nghiệp vụ một cách vô điều kiện vào mọi operation chỉ để giảm annotation lặp lại. Một customizer có thể dựa trên path, tag hoặc nhóm API để giới hạn phạm vi, nhưng logic đó cần được kiểm tra khi path/tag thay đổi.

Với response schema dùng chung, có thể tái sử dụng component schema:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          example: PRODUCT_NOT_FOUND
        message:
          type: string
          example: Không tìm thấy sản phẩm
        path:
          type: string
          example: /api/products/42
~~~

Nếu response object có cùng cấu trúc nhưng khác error code, dùng một schema chung có thể phù hợp. Nếu response validation có violations hoặc response authentication có challenge header, hãy mô tả phần khác biệt tương ứng.

## 15. Response header và media type trong lỗi

Một error response có thể chứa header mà client cần xử lý. Ví dụ 401 có thể cần WWW-Authenticate; 429 có thể có Retry-After; response lỗi có thể có trace ID.

Có thể mô tả header trong @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "429",
    description = "Vượt giới hạn request",
    headers = {
        @Header(
            name = "Retry-After",
            description = "Số giây cần chờ trước khi thử lại",
            schema = @Schema(type = "integer", format = "int32")
        ),
        @Header(
            name = "X-Trace-Id",
            description = "Mã tương quan để tra log",
            schema = @Schema(type = "string")
        )
    },
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Response body có thể là application/json hoặc application/problem+json nếu API dùng Problem Details. Media type phải khớp với response thực tế. Chỉ thêm media type vào OpenAPI không khiến Spring tự serialize theo định dạng đó; cần cấu hình converter và handler tương ứng.

Với 401, cơ chế xác thực còn có thể yêu cầu header WWW-Authenticate. Hãy kiểm tra security entry point và response thật, vì header có thể do Spring Security tạo thay vì @ExceptionHandler trong controller advice.

## 16. Bảo mật và phạm vi thông tin lỗi

Error response cần giúp client khắc phục request nhưng không tiết lộ chi tiết nội bộ. Nên:

- Trả mã lỗi ổn định, message phù hợp với người nhận.
- Không trả stack trace hoặc exception class name trong API công khai.
- Không đưa SQL, đường dẫn nội bộ, token, session ID hoặc dữ liệu cá nhân vào message.
- Dùng traceId/correlationId để nhóm vận hành tra log.
- Không tiết lộ sự tồn tại của tài nguyên nếu chính sách bảo mật yêu cầu che giấu.
- Đồng bộ thông tin trong response với chính sách 401/403/404 của hệ thống.

Một số hệ thống cố ý trả 404 thay vì 403 để không tiết lộ tài nguyên có tồn tại hay không. Đây là quyết định bảo mật và nghiệp vụ; OpenAPI phải phản ánh hành vi công khai mà client thực sự nhận được.

Không nên mô tả lỗi chi tiết trong tài liệu nếu server đã chủ động che giấu thông tin đó. Ví dụ schema có thể công bố code và message chung mà không liệt kê tên bảng hoặc điều kiện nội bộ.

## 17. Kiểm thử exception handler và hợp đồng OpenAPI

Để xác minh response lỗi, cần kiểm tra cả runtime lẫn tài liệu.

**Kiểm thử runtime:**

- Gửi JSON sai cú pháp.
- Gửi DTO thiếu trường bắt buộc hoặc vi phạm constraint.
- Gọi endpoint với ID không tồn tại.
- Gửi request gây xung đột nghiệp vụ.
- Gọi endpoint không có token hoặc thiếu quyền.
- Kích hoạt lỗi hệ thống được kiểm soát.
- Kiểm tra status, Content-Type, header và body.

**Kiểm tra OpenAPI:**

1. Tải /v3/api-docs hoặc tài liệu của group tương ứng.
2. Kiểm tra từng operation có response code cần thiết.
3. Xác minh schema của error body đúng với JSON runtime.
4. Xác minh response không body không khai báo content sai.
5. Kiểm tra response header như Retry-After, Location hoặc WWW-Authenticate nếu cần.
6. Xác định generic response từ @ControllerAdvice có được áp dụng đúng phạm vi.
7. Kiểm tra response lỗi không xuất hiện dư thừa ở endpoint không liên quan.
8. So sánh tài liệu giữa các phiên bản để phát hiện thay đổi phá vỡ client.

Một test tích hợp có thể dùng MockMvc:

~~~java
mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
~~~

Test này xác minh hành vi HTTP. Có thể bổ sung test đọc OpenAPI document hoặc kiểm tra file JSON đã sinh để xác nhận response 404 được mô tả bằng schema ApiError.

## 18. Các lỗi thường gặp khi dùng @ControllerAdvice với Springdoc

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Response lỗi không xuất hiện trong Swagger UI | Handler chưa được Springdoc nhận diện, thiếu @ApiResponse hoặc generic response đã bị tắt |
| Một response lỗi xuất hiện trên mọi endpoint | Generic responses từ @ControllerAdvice đang được áp dụng rộng hơn phạm vi nghiệp vụ |
| Có status 404 trong tài liệu nhưng runtime trả 200 | Annotation mô tả không khớp logic controller/service |
| Response body hiển thị schema rỗng | Kiểu trả về handler quá chung, generic bị mất hoặc thiếu schema implementation |
| Có response code nhưng thiếu content | Chưa mô tả media type/schema hoặc response thực tế không có body |
| Lỗi validation không có trong tài liệu | Chưa khai báo response 400 hoặc cơ chế tự động không bao phủ exception thực tế |
| Lỗi parse JSON bị nhầm với validation | Chưa phân biệt HttpMessageNotReadableException và MethodArgumentNotValidException |
| Response 401 thiếu header | Header được tạo ở Spring Security entry point nhưng chưa được mô tả |
| Handler trả ProblemDetail nhưng tài liệu hiển thị DTO khác | Schema override hoặc model resolver chưa phản ánh serializer runtime |
| Response lặp hoặc mô tả mâu thuẫn | Cả generic response và @ApiResponse tại operation cùng khai báo khác nhau |

Khi gặp vấn đề, hãy xem OpenAPI JSON trước để xác định response được thêm từ annotation operation, controller advice hay customizer. Sau đó gọi endpoint để xác minh status và body thực tế. Không nên sửa tài liệu chỉ dựa vào giao diện Swagger UI.

## 19. Quy trình xây dựng hợp đồng lỗi nhất quán

Một quy trình thực tế cho ứng dụng Spring Boot có thể gồm:

1. Xác định các nhóm lỗi mà client cần xử lý: validation, not found, conflict, authentication, authorization và server error.
2. Chọn một cấu trúc error response ổn định hoặc sử dụng ProblemDetail theo chính sách ứng dụng.
3. Tạo exception class và @RestControllerAdvice để ánh xạ exception thành status, header và body.
4. Bổ sung handler cho lỗi Jackson, Bean Validation và method validation theo phiên bản Spring đang dùng.
5. Khai báo @ApiResponse cho lỗi theo operation; chỉ dùng generic responses cho lỗi thực sự chung.
6. Quyết định có bật springdoc.override-with-generic-response hay không dựa trên phạm vi advice và kết quả tài liệu.
7. Kiểm tra /v3/api-docs để loại response dư thừa hoặc schema sai.
8. Viết integration test cho các trường hợp lỗi quan trọng.
9. Đưa kiểm tra OpenAPI và contract diff vào quy trình review/phát hành.

Không cần liệt kê mọi exception nội bộ mà client không thể hoặc không cần xử lý. Hãy tập trung vào những kết quả HTTP có ý nghĩa trong hợp đồng công khai.

## 20. Nguyên tắc sử dụng @ControllerAdvice và @ExceptionHandler

Khi kết hợp exception handling với Springdoc OpenAPI, hãy giữ các nguyên tắc:

1. Dùng @RestControllerAdvice để chuẩn hóa response lỗi cho REST API.
2. Dùng @ExceptionHandler để ánh xạ từng nhóm exception sang status và body phù hợp.
3. Dùng @ResponseStatus hoặc ResponseEntity để quyết định HTTP response thực tế.
4. Dùng @ApiResponse/@ApiResponses để công bố status, content, schema và header cho client.
5. Phân biệt response chung với response chỉ phát sinh ở một operation.
6. Hiểu giới hạn của generic responses từ @ControllerAdvice và cấu hình springdoc.override-with-generic-response.
7. Không giả định Springdoc phân tích được mọi exception có thể phát sinh từ service, repository hoặc filter.
8. Chuẩn hóa error code và tránh rò rỉ thông tin nội bộ.
9. Kiểm tra OpenAPI document cùng response runtime và integration test.

@ControllerAdvice và @ExceptionHandler quyết định cách ứng dụng xử lý ngoại lệ; Springdoc dùng metadata có thể quan sát để mô tả response trong hợp đồng. Vì một exception handler không cho biết chắc mọi endpoint nào có thể phát sinh lỗi, nhóm phát triển cần chọn rõ lỗi nào là chung, lỗi nào thuộc operation cụ thể và xác minh tài liệu sau khi sinh. Điều đó giúp client hiểu đúng status code, cấu trúc lỗi và cách khôi phục request.

