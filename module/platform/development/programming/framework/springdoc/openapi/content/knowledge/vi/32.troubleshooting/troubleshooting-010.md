# Mã lỗi hoặc kiểu nội dung bị suy luận khác phản hồi thực tế

Springdoc-openapi đọc controller, annotation, kiểu trả về và cấu hình Spring để tạo phần `responses` trong OpenAPI. Phần này mô tả mã HTTP, nội dung trả về và media type mà client có thể nhận. Khi metadata không thể hiện đầy đủ các nhánh xử lý runtime, Swagger UI có thể hiển thị `200 OK` trong khi ứng dụng trả `201 Created`, `204 No Content` hoặc `404 Not Found`. Tương tự, tài liệu có thể ghi `application/json` trong khi Spring thực tế trả `application/problem+json`, `text/csv` hoặc một loại nội dung khác.

Những khác biệt này thường xuất hiện khi method dùng `ResponseEntity` để chọn status theo điều kiện, khi `@ControllerAdvice` xử lý exception, khi thiếu `@ApiResponse` cho các nhánh lỗi, hoặc khi `produces`/`consumes` không khớp với content negotiation. Cách xử lý đúng là xác định response thực tế trên HTTP, sau đó làm cho metadata OpenAPI mô tả đủ các trường hợp mà API cam kết hỗ trợ.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt status code được suy ra từ annotation với status được chọn trong runtime.
- Xác định khi nào cần `@ResponseStatus`, `ResponseEntity` hoặc `@ApiResponse`.
- Mô tả response thành công, lỗi, response không có body và response tải file.
- Đồng bộ `@ControllerAdvice` với các response được sinh trong OpenAPI.
- Hiểu `springdoc.override-with-generic-response` và tác động của nó.
- Phân biệt `Content-Type`, `Accept`, `consumes` và `produces`.
- Khai báo nhiều response media type bằng `@Content`.
- Mô tả `ProblemDetail` theo `application/problem+json`.
- Phân tích lỗi `406 Not Acceptable` và `415 Unsupported Media Type`.
- Kiểm thử status, header và body thực tế bằng MockMvc.
- Đọc OpenAPI JSON để kiểm tra `responses` và `content`.

## 1. Nhận diện triệu chứng

Một số dấu hiệu thường gặp:

| Biểu hiện | Điều đang xảy ra |
|---|---|
| Swagger UI chỉ có `200` nhưng API trả `201` | Springdoc không có metadata tĩnh về status của nhánh runtime |
| API trả `204` nhưng tài liệu hiển thị schema JSON | Response được mô tả như có body dù runtime không gửi body |
| Swagger UI hiện `Undocumented` sau khi gọi API | Status runtime không có response entry tương ứng trong OpenAPI |
| Tài liệu ghi `application/json` nhưng response header là `application/problem+json` | Media type của error body không được mô tả chính xác |
| API trả `406` khi client gửi `Accept: application/xml` | Server không có representation phù hợp với media type client yêu cầu |
| API trả `415` khi gửi JSON | Request `Content-Type` không khớp với mapping `consumes` hoặc converter |
| Một số endpoint có response lỗi lặp lại | Response từ `@ControllerAdvice` được gộp toàn cục cùng response khai báo riêng |
| Tải file nhưng OpenAPI mô tả object JSON | Kiểu trả về hoặc `@Content` chưa thể hiện binary media type |

Đừng bắt đầu bằng việc sửa Swagger UI. Hãy thu thập response thực tế trước: status line, `Content-Type`, `Content-Disposition` và body. Sau đó mới so sánh với OpenAPI document.

## 2. Phân biệt mô tả tĩnh và response runtime

Springdoc tạo OpenAPI từ những thông tin có thể quan sát khi phân tích Spring application context. Ứng dụng lại quyết định response thực tế khi xử lý từng request.

| Nguồn thông tin | Có thể mô tả điều gì |
|---|---|
| Kiểu trả về controller | Kiểu body dự kiến, ví dụ DTO, collection hoặc `ProblemDetail` |
| `@ResponseStatus` | HTTP status cố định gắn với handler |
| `ResponseEntity` | Status, headers và body do code trả về tại runtime |
| `@ApiResponse` | Status, mô tả, headers và media type được khai báo rõ trong OpenAPI |
| `@ControllerAdvice` / `@ExceptionHandler` | Response khi xử lý exception |
| `@RequestMapping` / `@GetMapping` | Điều kiện mapping, gồm method, `consumes` và `produces` |
| `HttpMessageConverter` | Cách body được chuyển thành representation HTTP |
| `Accept` và `Content-Type` | Representation client yêu cầu và representation request gửi lên |

Ví dụ, một method có kiểu trả về `OrderResponse` không cho biết chắc chắn nó chỉ trả `200`. Nếu code có thể trả `201` khi tạo mới, `202` khi xử lý bất đồng bộ và `409` khi trùng dữ liệu, cả ba trường hợp phải được mô tả.

Spring Framework dùng `ResponseEntity` để trả cả status, headers và body; body thường được chuyển thành representation bởi các `HttpMessageConverter` đã đăng ký. Vì vậy, chỉ nhìn kiểu generic như `ResponseEntity<OrderResponse>` chưa đủ để xác định toàn bộ response runtime. <Link url="https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html" title="Spring Framework: ResponseEntity"/>.

## 3. Mã HTTP bị suy luận không đúng

### 3.1. Dùng @ResponseStatus cho status cố định

Nếu endpoint luôn trả một status, khai báo trực tiếp bằng `@ResponseStatus`:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Ở đây status `201 Created` là một phần cố định của handler. Springdoc có thể dùng metadata này để mô tả response. Cách khai báo này phù hợp khi status không phụ thuộc nhánh xử lý.

### 3.2. Mô tả mọi nhánh của ResponseEntity

Nếu status thay đổi theo điều kiện, hãy khai báo các response tường minh:

~~~java
@Operation(summary = "Tạo hoặc tiếp nhận yêu cầu đặt hàng")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng được tạo ngay",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "202",
        description = "Yêu cầu được tiếp nhận để xử lý bất đồng bộ",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderAcceptedResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Đơn hàng trùng khóa nghiệp vụ",
        content = @Content(
            mediaType = "application/problem+json",
            schema = @Schema(implementation = ProblemDetail.class)
        )
    )
})
@PostMapping
ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
    if (orderService.isDuplicate(request)) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(problemForDuplicate(request));
    }

    if (orderService.requiresAsyncProcessing(request)) {
        return ResponseEntity.accepted()
            .body(orderService.enqueue(request));
    }

    return ResponseEntity.status(HttpStatus.CREATED)
        .body(orderService.create(request));
}
~~~

Ví dụ dùng `ResponseEntity<?>` để làm rõ rằng body có thể khác theo nhánh. Trong code thực tế, có thể dùng một sealed interface hoặc wrapper response nếu đó là mô hình domain phù hợp. Dù kiểu trả về có thể hiện được union type, vẫn cần khai báo từng status code và schema để OpenAPI thể hiện đúng hợp đồng.

Không dựa vào một nhánh test thành công để suy ra toàn bộ response. Hãy liệt kê các status mà endpoint thực sự có thể trả về, gồm cả lỗi validation, conflict, authentication và rate limit nếu chúng thuộc contract.

### 3.3. Response không có body

Với `204 No Content` hoặc `404` chỉ trả status, khai báo `content = @Content` để không tạo schema body:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Đã xóa tài nguyên",
    content = @Content
)
~~~

Springdoc FAQ cũng hướng dẫn dùng `content = @Content` hoặc schema ẩn để mô tả response rỗng. Không khai báo DTO chỉ vì method trả về một kiểu wrapper nếu runtime không gửi body. <Link url="https://springdoc.org/faq.html" title="Springdoc FAQ: response không có content"/>.

## 4. Đồng bộ @ControllerAdvice và response lỗi

Springdoc có thể đưa response từ `@ControllerAdvice` vào các operation được tạo. Property `springdoc.override-with-generic-response` mặc định là `true`; khi bật, response của `@ControllerAdvice` được tự động thêm vào các response đã sinh. <Link url="https://springdoc.org/core-properties.html" title="Springdoc core properties"/>.

Ví dụ một handler lỗi có status cố định:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        return ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            exception.getMessage()
        );
    }
}
~~~

Để Springdoc nhận diện status lỗi tự động từ exception handler, khai báo HTTP code bằng `@ResponseStatus` trên các method xử lý. Đây là hướng dẫn được nêu trong phần error handling của Springdoc. <Link url="https://springdoc.org/features.html" title="Springdoc Features: Error Handling for REST"/>.

Nếu handler trả `ResponseEntity` và status được chọn động trong thân method, hãy xác minh document đã có đủ status. Khi không chắc Springdoc suy ra được mọi nhánh hay không, khai báo response tại operation bằng `@ApiResponse`.

### 4.1. Khi response toàn cục bị lặp hoặc ghi đè

Nếu một response lỗi xuất hiện trên mọi operation nhưng chỉ phù hợp với một số route, xem lại cấu hình:

~~~yaml
springdoc:
  override-with-generic-response: true
~~~

Đặt `false` sẽ ngừng việc tự động thêm các response từ `@ControllerAdvice` vào toàn bộ operation:

~~~yaml
springdoc:
  override-with-generic-response: false
~~~

Khi tắt, hãy tự khai báo các lỗi chung ở đúng operation hoặc qua customizer phù hợp. Không tắt property chỉ để che response trùng mà chưa kiểm tra xem API còn thiếu mô tả lỗi toàn cục nào.

Nếu dùng customizer, hãy bổ sung response vào `ApiResponses` hiện có theo response code. Tránh thay toàn bộ map `responses` vì có thể xóa response thành công hoặc response riêng đã được khai báo bởi annotation.

## 5. Media type trong tài liệu khác Content-Type thực tế

### 5.1. Phân biệt Content-Type và Accept

Hai header này có hướng khác nhau:

| Header | Ý nghĩa |
|---|---|
| `Content-Type` | Kiểu dữ liệu của request body client gửi tới server |
| `Accept` | Kiểu representation client muốn nhận từ server |

Trong Spring mapping:

- `consumes` ràng buộc media type của request body và thường được đối chiếu với `Content-Type`.
- `produces` ràng buộc media type response và được đối chiếu với `Accept`.

Ví dụ:

~~~java
@PostMapping(
    path = "/imports",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importFile(@RequestPart MultipartFile file) {
    return importService.importFile(file);
}
~~~

Nếu client gửi `Content-Type: application/json` vào mapping chỉ nhận multipart, Spring có thể trả `415 Unsupported Media Type`. Nếu client yêu cầu `Accept: application/xml` trong khi endpoint chỉ tạo JSON, Spring có thể trả `406 Not Acceptable`. Thuộc tính `consumes` và `produces` của Spring mapping quyết định điều kiện khớp request và representation được phép trả về. <Link url="https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html" title="Spring Framework: Request Mapping"/>.

### 5.2. Khai báo response media type bằng @Content

`@ApiResponse` mô tả response code và danh sách representation trong `content`. Ví dụ endpoint hỗ trợ JSON và XML:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin đơn hàng",
    content = {
        @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        ),
        @Content(
            mediaType = MediaType.APPLICATION_XML_VALUE,
            schema = @Schema(implementation = OrderResponse.class)
        )
    }
)
~~~

Các media type được liệt kê phải tương ứng với representation mà ứng dụng thật sự có thể tạo. Việc thêm XML vào OpenAPI không tự làm Spring có XML converter; ứng dụng cần converter và mapping tương ứng.

### 5.3. Default media type của Springdoc

Hai property mặc định của Springdoc là:

| Property | Mặc định | Dùng cho |
|---|---|---|
| `springdoc.default-consumes-media-type` | `application/json` | Request media type mặc định |
| `springdoc.default-produces-media-type` | `*/*` | Response media type mặc định |

Tham khảo bảng core properties chính thức. <Link url="https://springdoc.org/core-properties.html" title="Springdoc core properties reference"/>.

Có thể cấu hình khi ứng dụng có default nhất quán:

~~~yaml
springdoc:
  default-consumes-media-type: application/json
  default-produces-media-type: application/json
~~~

Không đặt global default thành JSON nếu ứng dụng có nhiều route trả CSV, binary, XML hoặc Problem Details. Với các route đặc biệt, khai báo `produces` và `@ApiResponse(content = ...)` cụ thể. Default chỉ là giá trị fallback khi metadata mapping không nêu rõ media type; nó không thay đổi cách `HttpMessageConverter` thực sự serialize body.

## 6. Mô tả ProblemDetail và application/problem+json

Spring Framework hỗ trợ Problem Details cho HTTP APIs theo RFC 9457. `ProblemDetail` mang status, title, detail, type, instance và các thuộc tính mở rộng. Khi Spring serialize ProblemDetail bằng Jackson, media type được ưu tiên là `application/problem+json`; nếu có XML converter tương ứng, media type là `application/problem+xml`. <Link url="https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html" title="Spring Framework: Error Responses"/>.

Vì vậy, response lỗi dạng ProblemDetail nên được mô tả bằng đúng media type:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy đơn hàng",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
~~~

Nếu OpenAPI chỉ ghi `application/json`, client generator có thể chọn sai decoder hoặc Swagger UI hiển thị response content không giống header runtime. `application/problem+json` là media type riêng của Problem Details dù payload có cú pháp JSON.

### 6.1. Response lỗi theo RFC 9457

Một response thực tế có thể giống:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng ORD-42",
  "instance": "/api/orders/ORD-42"
}
~~~

Không tự mô tả response này như một DTO lỗi tùy chỉnh nếu body thực tế là `ProblemDetail`. Nếu ứng dụng mở rộng ProblemDetail bằng các field như `code` hoặc `violations`, hãy dùng schema mở rộng tương ứng hoặc định nghĩa một class kế thừa và kiểm thử JSON được serialize đúng.

### 6.2. Exception handler có nhiều media type

Spring Framework cho phép các `@ExceptionHandler` khai báo media type có thể tạo bằng thuộc tính `produces` ở những phiên bản hỗ trợ. Ví dụ một exception có thể trả JSON cho API client và HTML cho browser:

~~~java
@ExceptionHandler(
    value = IllegalArgumentException.class,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ApiError> handleJson(IllegalArgumentException exception) {
    return ResponseEntity.badRequest()
        .body(new ApiError("INVALID_INPUT", exception.getMessage()));
}

@ExceptionHandler(
    value = IllegalArgumentException.class,
    produces = MediaType.TEXT_HTML_VALUE
)
String handleHtml(IllegalArgumentException exception, Model model) {
    model.addAttribute("message", exception.getMessage());
    return "error";
}
~~~

Thuộc tính `produces` của `@ExceptionHandler` có từ Spring Framework 6.2. Content negotiation trong giai đoạn exception handling sẽ chọn handler phù hợp với `Accept`. Với Spring Framework cũ hơn, không dùng ví dụ này; hãy dùng một handler có status/media type cố định hoặc tự điều phối trong một handler duy nhất. <Link url="https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html" title="Spring Framework 6.2: ExceptionHandler API"/>.

Nếu một API endpoint có nhiều representation lỗi, hãy mô tả từng media type và schema trong OpenAPI. Nếu HTML chỉ dành cho browser view và không thuộc API contract, tách rõ route/view khỏi REST API thay vì công bố nó như representation mà API client cần dùng.

### 6.3. Phân biệt HTTP status với mã lỗi nghiệp vụ

HTTP status là mã giao thức như `400`, `404` hoặc `409`. Mã lỗi nghiệp vụ là giá trị trong body như `ORDER_NOT_FOUND` hoặc `ORDER_ALREADY_EXISTS`. Hai giá trị này có mục đích khác nhau:

~~~json
{
  "code": "ORDER_ALREADY_EXISTS",
  "message": "Đơn hàng đã tồn tại",
  "details": {
    "orderNumber": "ORD-42"
  }
}
~~~

Trong OpenAPI, khai báo `responseCode = "409"` cho status HTTP và mô tả schema body chứa field `code`. Không đặt chuỗi `ORDER_ALREADY_EXISTS` vào `responseCode` vì OpenAPI response map dùng mã HTTP hoặc key `default`.

Nếu mã lỗi là một tập giá trị ổn định, định nghĩa enum trong schema để client có thể sinh constant:

~~~java
public enum ApiErrorCode {
    ORDER_NOT_FOUND,
    ORDER_ALREADY_EXISTS,
    INVALID_ORDER_STATE
}

public record ApiError(
    ApiErrorCode code,
    String message,
    Map<String, Object> details
) {
}
~~~

Trong ví dụ trên, import thêm `java.util.Map`.

Khai báo schema response:

~~~java
@ApiResponse(
    responseCode = "409",
    description = "Xung đột trạng thái đơn hàng",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Khi dùng RFC 9457, có thể đặt mã nghiệp vụ trong extension property của `ProblemDetail` hoặc dùng subclass có schema rõ ràng. Kiểm tra JSON thực tế vì map `properties` của ProblemDetail được Jackson render thành các thuộc tính cấp cao nhất.

## 7. Request consumes và response produces không khớp

Các lỗi content negotiation thường bắt đầu từ việc nhầm `Content-Type` với `Accept` hoặc khai báo mapping quá hẹp.

| Client gửi | Mapping Spring | Kết quả thường gặp |
|---|---|---|
| `Content-Type: application/json` | `consumes = application/json` | Request body được đọc bằng JSON converter |
| `Content-Type: text/plain` | `consumes = application/json` | `415 Unsupported Media Type` |
| `Accept: application/json` | `produces = application/json` | JSON response phù hợp |
| `Accept: application/xml` | `produces = application/json` | `406 Not Acceptable` nếu không có representation tương thích |
| Không gửi `Accept` cụ thể | Mapping và converter mặc định | Spring chọn representation có thể ghi |

Kiểm tra mapping ở cả cấp class và method. Với `produces`, mapping cấp method có thể ghi đè danh sách ở cấp class; đừng giả định hai danh sách luôn được cộng lại. Đọc quy tắc mapping của phiên bản Spring Framework mà dự án đang dùng.

### 7.1. Nhiều consumes trên cùng operation

Nếu cùng một path và HTTP method chấp nhận nhiều request media type nhưng cùng semantics, có thể khai báo:

~~~java
@PostMapping(
    path = "/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
ImportResult importData(@RequestBody ImportRequest request) {
    return importService.importData(request);
}
~~~

Khi các mapping được tách thành nhiều method overload nhưng cùng path và HTTP method, Springdoc có thể tạo một OpenAPI operation duy nhất. Tài liệu Springdoc khuyến nghị đặt `@Operation` ở một method phù hợp thay vì lặp metadata khác nhau trên mọi overload; hãy kiểm tra document được tạo để bảo đảm không mất thông tin. <Link url="https://springdoc.org/faq.html" title="Springdoc FAQ: multiple consuming media types"/>.

## 8. Response file, binary và nội dung không phải JSON

Endpoint tải file thường trả `ResponseEntity<Resource>` hoặc `ResponseEntity<byte[]>` cùng header `Content-Disposition`. Nếu tài liệu hiển thị schema object hoặc JSON, hãy mô tả response như binary:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Tệp báo cáo",
    content = @Content(
        mediaType = "application/pdf",
        schema = @Schema(type = "string", format = "binary")
    )
)
~~~

Ví dụ controller:

~~~java
@GetMapping(
    path = "/reports/{id}/download",
    produces = "application/pdf"
)
ResponseEntity<Resource> download(@PathVariable String id) {
    Resource file = reportService.loadPdf(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment()
                .filename("report-" + id + ".pdf")
                .build()
                .toString()
        )
        .body(file);
}
~~~

Nếu endpoint trả CSV, ảnh, ZIP hoặc stream, dùng media type và schema đúng với representation thực tế. Không để default JSON của Springdoc quyết định schema của file response.

## 9. Các property cần kiểm tra

| Property | Mặc định | Khi nào xem xét |
|---|---|---|
| `springdoc.default-consumes-media-type` | `application/json` | Request media type mặc định khi mapping không khai báo rõ |
| `springdoc.default-produces-media-type` | `*/*` | Response media type mặc định khi mapping không khai báo rõ |
| `springdoc.override-with-generic-response` | `true` | Tự động thêm response từ `@ControllerAdvice` vào operation |
| `springdoc.api-docs.enabled` | `true` | Kiểm tra endpoint tài liệu có được bật để đọc JSON hay không |

Không nhầm `springdoc.produces-to-match` với `springdoc.default-produces-media-type`. Property thứ nhất lọc operation theo điều kiện media type khi scan; property thứ hai đặt media type mặc định cho mô tả. Tương tự, `springdoc.consumes-to-match` là điều kiện lọc, không phải cách thay đổi `Content-Type` runtime.

Nếu property được đặt ở nhiều profile, kiểm tra effective configuration của profile đang chạy. Một profile staging có thể dùng JSON và production dùng Problem Details hoặc binary response do bean/customizer khác nhau; OpenAPI phải được tạo từ đúng context cần công bố.

## 10. Cẩn thận khi tùy biến OpenAPI bằng code

Một `OpenApiCustomizer` có thể thêm response chung như rate limit hoặc lỗi hệ thống. Khi thêm response, hãy giữ nguyên các response đã có và chỉ bổ sung entry còn thiếu:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import io.swagger.v3.oas.models.responses.ApiResponses;
~~~

~~~java
@Bean
OpenApiCustomizer addRateLimitResponse() {
    return openApi -> openApi.getPaths().values().forEach(pathItem ->
        pathItem.readOperations().forEach(operation -> {
            ApiResponses responses = operation.getResponses();
            if (responses == null) {
                responses = new ApiResponses();
                operation.setResponses(responses);
            }

            if (!responses.containsKey("429")) {
                responses.addApiResponse(
                    "429",
                    new io.swagger.v3.oas.models.responses.ApiResponse()
                        .description("Đã vượt giới hạn request")
                );
            }
        })
    );
}
~~~

Ví dụ chỉ bổ sung response description. Nếu rate-limit middleware thực tế trả JSON hoặc ProblemDetail, thêm content schema và media type đúng với body. Không khai báo `429` nếu ứng dụng/gateway không thực sự có thể trả status đó cho route.

Một customizer áp dụng cho document mặc định có thể không tự động áp dụng cho tất cả `GroupedOpenApi`. Nếu cần cùng metadata cho các group, dùng customizer toàn cục phù hợp với phiên bản Springdoc của dự án và kiểm tra từng group document.

Không dùng customizer để ép tất cả operation về cùng một response code hoặc media type nếu controller có semantics khác nhau. Metadata chung chỉ nên chứa điều thực sự đúng với mọi operation nhận nó.

## 11. Bảng lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ thấy `200` trong Swagger UI | Không có metadata cho `201`/`202` do `ResponseEntity` chọn động | Khai báo từng `@ApiResponse` hoặc status cố định bằng `@ResponseStatus` |
| Response `204` có schema body | Operation được mô tả như có content | Dùng `content = @Content` |
| Runtime trả `404` nhưng OpenAPI không có `404` | Exception handler thiếu status metadata hoặc generic response bị tắt | Thêm `@ResponseStatus` và kiểm tra `override-with-generic-response` |
| Mọi operation đều có lỗi không liên quan | `@ControllerAdvice` được gộp vào toàn bộ operation | Thu hẹp handler hoặc cân nhắc `springdoc.override-with-generic-response=false` |
| Tài liệu chỉ ghi application/json | `@Content` hoặc mapping chưa nêu Problem Details | Khai báo `application/problem+json` và schema `ProblemDetail` |
| JSON runtime nhưng tài liệu ghi `*/*` | Default produces không được cấu hình cho contract thống nhất | Khai báo `produces` hoặc default property phù hợp |
| `415 Unsupported Media Type` | `Content-Type` không khớp `consumes` hoặc converter | Kiểm tra mapping và request header |
| `406 Not Acceptable` | `Accept` không khớp `produces`/converter | Kiểm tra negotiation và representation được hỗ trợ |
| Swagger UI hiển thị response file là JSON | Thiếu binary schema và media type | Dùng `type = "string", format = "binary"` và đúng media type |
| Response code xuất hiện nhưng thiếu body schema | `@ApiResponse` chỉ có description | Thêm `content` và `@Schema(implementation = ...)` |
| Response content type bị lặp hoặc sai sau customizer | Customizer thay thế map response/content không đúng | Merge theo response code và media type |
| Default docs đúng nhưng group docs sai | Customizer chỉ chạy trên default document hoặc group filter khác | Kiểm tra từng `GroupedOpenApi` và customizer toàn cục |
| Test runtime pass nhưng Swagger UI vẫn sai | Chưa có assertion trên `/v3/api-docs` | Thêm contract test đọc response map và media type |

## 12. Bài thực hành tổng hợp

Tạo API quản lý đơn hàng với các response khác nhau:

1. Tạo endpoint POST trả `201 Created` khi tạo đơn thành công.
2. Tạo nhánh trả `202 Accepted` khi yêu cầu được đưa vào hàng đợi.
3. Tạo nhánh lỗi `409 Conflict` với mã lỗi nghiệp vụ `ORDER_ALREADY_EXISTS`.
4. Tạo endpoint GET không tìm thấy đơn hàng và trả `ProblemDetail` với `404`.
5. Tạo endpoint DELETE trả `204 No Content`.
6. Tạo endpoint tải báo cáo PDF trả `application/pdf` và `Content-Disposition`.
7. Khai báo `@ResponseStatus` cho status cố định.
8. Khai báo `@ApiResponses` cho các nhánh `ResponseEntity`.
9. Định nghĩa `@ControllerAdvice` và kiểm tra `springdoc.override-with-generic-response`.
10. Khai báo `consumes`/`produces` theo đúng representation.
11. Gọi từng endpoint bằng curl với các header `Accept` và `Content-Type` khác nhau.
12. Đọc `/v3/api-docs` và xác minh từng response code, content type, schema.
13. Viết MockMvc tests cho status/header/body thực tế.
14. Viết OpenAPI contract test cho response map.
15. Nếu dùng nhiều group, lặp lại việc xác minh cho từng group.

### Tiêu chí hoàn thành

- [ ] Phân biệt được HTTP status và mã lỗi nghiệp vụ.
- [ ] Giải thích được vì sao kiểu trả về không thể hiện hết status runtime.
- [ ] Dùng `@ResponseStatus` cho status cố định.
- [ ] Dùng `@ApiResponse` cho các nhánh response động.
- [ ] Mô tả được response từ `@ControllerAdvice`.
- [ ] Hiểu tác động của `springdoc.override-with-generic-response`.
- [ ] Phân biệt `Content-Type`, `Accept`, `consumes` và `produces`.
- [ ] Mô tả đúng `application/problem+json` cho `ProblemDetail`.
- [ ] Mô tả response rỗng và binary đúng cách.
- [ ] Chẩn đoán được `406` và `415`.
- [ ] Có MockMvc test xác minh status, media type và body.
- [ ] Có contract test xác minh response codes và content types trong OpenAPI.

## 13. Quy trình chẩn đoán theo từng lớp

Khi status hoặc media type trong Swagger UI không khớp với server, làm theo thứ tự:

1. Gửi request trực tiếp tới endpoint bằng cùng method, path, body và headers mà client đang dùng.
2. Ghi lại HTTP status, `Content-Type`, `Content-Disposition` và response body.
3. Lặp lại request với các giá trị `Accept` và `Content-Type` khác nhau nếu endpoint hỗ trợ nhiều representation.
4. Kiểm tra controller mapping: `@ResponseStatus`, `ResponseEntity`, `consumes` và `produces`.
5. Kiểm tra exception handler: exception nào được bắt, status nào được trả, body nào được serialize.
6. Tải `/v3/api-docs` hoặc group document tương ứng.
7. So sánh `responses` của operation, từng response code, từng media type và schema.
8. Chỉnh metadata hoặc cấu hình default của Springdoc.
9. Chạy lại runtime tests và contract tests để xác nhận cả hai mặt.

### 9.1. Thu thập response thực tế bằng curl

Request JSON thành công:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"productCode":"BOOK-01","quantity":2}' \
  http://localhost:8080/api/orders
~~~

Request kích hoạt lỗi:

~~~bash
curl -i \
  -H "Accept: application/problem+json" \
  http://localhost:8080/api/orders/unknown
~~~

Request yêu cầu media type không được hỗ trợ:

~~~bash
curl -i \
  -H "Accept: application/xml" \
  http://localhost:8080/api/orders/unknown
~~~

Đọc status line và response headers trước khi xem body. Nếu server trả `406` hoặc `415`, kiểm tra điều kiện mapping và converter; việc thêm `@ApiResponse` vào OpenAPI không sửa được lỗi runtime.

### 9.2. Kiểm tra OpenAPI JSON

Lấy document:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
~~~

Xem response của operation bằng `jq`:

~~~bash
jq '.paths["/api/orders"].post.responses' openapi.json
~~~

Xem riêng content type:

~~~bash
jq '.paths["/api/orders"].post.responses["409"].content' openapi.json
~~~

Kết quả cần có các key media type đúng, ví dụ `application/problem+json`. Nếu operation nằm trong group, tải URL `/v3/api-docs/{group}` tương ứng; không kiểm tra nhầm document mặc định.

### 9.3. Kiểm tra response content trong OpenAPI

Một response có body JSON thường có cấu trúc:

~~~json
{
  "responses": {
    "201": {
      "description": "Đơn hàng được tạo",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/OrderResponse"
          }
        }
      }
    },
    "409": {
      "description": "Đơn hàng đã tồn tại",
      "content": {
        "application/problem+json": {
          "schema": {
            "$ref": "#/components/schemas/ProblemDetail"
          }
        }
      }
    }
  }
}
~~~

Trong OpenAPI, mỗi response code là một entry trong `responses`. `content` là map từ media type sang schema và ví dụ của representation tương ứng. Response không có body có thể bỏ `content` hoặc khai báo content rỗng.

## 14. Kiểm thử response runtime bằng MockMvc

Contract test nên xác minh cả HTTP response thật và OpenAPI document. Ví dụ test status và media type:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderResponseContractTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderReturns201Json() throws Exception {
        CreateOrderRequest request =
            new CreateOrderRequest("BOOK-01", 2);

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }

    @Test
    void missingOrderReturnsProblemJson() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "missing")
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.status").value(404));
    }
}
~~~

Các test này kiểm tra status và media type mà Spring thực sự trả. Với API hỗ trợ nhiều nhánh, tạo test riêng cho từng nhánh, kể cả validation, conflict, not found, no content và binary response.

## 15. Kiểm thử OpenAPI response metadata

Có thể tải `/v3/api-docs` bằng MockMvc rồi xác minh response code và content type:

~~~java
@Test
void openApiDocumentsOrderResponseCodesAndMediaTypes() throws Exception {
    String json = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode document = objectMapper.readTree(json);
    JsonNode createOperation = document
        .path("paths")
        .path("/api/orders")
        .path("post");

    JsonNode responses = createOperation.path("responses");
    assertThat(responses.has("201")).isTrue();
    assertThat(responses.has("409")).isTrue();

    assertThat(
        responses.path("201").path("content")
            .has("application/json")
    ).isTrue();

    assertThat(
        responses.path("409").path("content")
            .has("application/problem+json")
    ).isTrue();
}
~~~

Các import cần có:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Điều chỉnh path, method, response code và media type theo API thực tế. Nếu dùng nhiều `GroupedOpenApi`, chạy assertion cho từng document group. Contract test chỉ đọc document không thay thế test runtime; giữ cả hai để phát hiện trường hợp tài liệu đúng nhưng handler trả sai hoặc handler đúng nhưng tài liệu thiếu.

## Tiếp tục học

Sau bài này, hãy kết hợp response metadata với contract testing, error handling và client generation. Một operation chỉ được mô tả chính xác khi status code, media type, schema và body runtime thống nhất; mỗi thay đổi trong exception handler hoặc content negotiation nên được xác minh bằng cả HTTP test lẫn OpenAPI document.

## Tài liệu tham khảo

- [Springdoc Features – Error Handling for REST using @ControllerAdvice](https://springdoc.org/features.html)
- [Springdoc FAQ – Response with empty content and media types](https://springdoc.org/faq.html)
- [Springdoc Core Properties Reference](https://springdoc.org/core-properties.html)
- [Spring Framework – Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework – ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework 6.2 – ExceptionHandler produces attribute](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html)
- [Spring Framework – Error Responses and ProblemDetail](https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
