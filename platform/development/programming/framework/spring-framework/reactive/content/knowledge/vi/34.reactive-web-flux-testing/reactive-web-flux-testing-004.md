# Kiểm tra body rỗng, lỗi validation và ProblemDetail trong Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Kiểm thử WebFlux  
> **Mục tiêu chính:** kiểm tra đúng HTTP contract của REST endpoint reactive khi response không có nội dung, khi dữ liệu request không đạt Bean Validation, và khi API trả lỗi theo RFC 9457 `ProblemDetail`. Bài tập trung vào `WebTestClient`, JUnit 5, Spring WebFlux, `@Valid`, `WebExchangeBindException`, `HandlerMethodValidationException`, `ServerWebInputException`, `ResponseEntity<ProblemDetail>` và các assertion vừa chính xác vừa bền vững.

## 1. Sau bài học, bạn làm được gì?

1. Phân biệt **HTTP 204 No Content**, **HTTP 200 có body dài 0 byte**, **HTTP 200 chứa JSON `null`**, **HTTP 200 chứa JSON `[]`**, và một `Mono.empty()` trong tầng service.
2. Sử dụng `WebTestClient.expectBody().isEmpty()` để kiểm tra response thực sự không có payload.
3. Kiểm tra status, `Content-Type`, `Location`, JSON field, raw bytes và body rỗng theo đúng endpoint contract.
4. Nhận ra sự khác biệt giữa body **không được gửi**, body **JSON sai cú pháp**, body **đúng JSON nhưng vi phạm ràng buộc**, và tham số phương thức vi phạm constraint.
5. Hiểu `@Valid @RequestBody` dẫn tới `WebExchangeBindException`, trong khi constraint trực tiếp lên tham số có thể dẫn tới `HandlerMethodValidationException`.
6. Hiểu tại sao `ServerWebInputException` thường liên quan tới decoding hoặc thiếu request body và không nên gộp tất cả lỗi thành “validation failed”.
7. Thiết kế `ProblemDetail` theo RFC 9457: `type`, `title`, `status`, `detail`, `instance`, thêm `code` hoặc `errors` có kiểm soát.
8. Viết `@RestControllerAdvice` trả lỗi `application/problem+json` nhất quán và tránh lộ dữ liệu nội bộ.
9. Kiểm tra cả nhánh thành công (201/204), nhánh validation (400), business not found (404), lỗi nội bộ (500) và media type không hỗ trợ (415).
10. Phân biệt unit/controller-slice test với HTTP integration test, biết điều gì được kiểm chứng và điều gì chưa.
11. Dùng `StepVerifier` cho publisher ở service và `WebTestClient` cho HTTP contract, không lấy `.block()` làm phương pháp test mặc định.
12. Chạy một project Spring Boot 4.0.9/Java 17+ có validation, ProblemDetail, HTTP tests và lệnh curl đối chiếu.

**Quy tắc chủ chốt:** test REST không chỉ kiểm tra “đã nhận 400”. Nó phải trả lời: request sai ở đâu, response có đúng media type, body có cấu trúc ổn định, có tiết lộ nội bộ hay không, và khi không có nội dung thì có thật sự không gửi byte nào.

## 2. Bản đồ các lớp cần kiểm tra

Một request đi qua nhiều bước trước khi nhận HTTP response:

~~~text
HTTP Client / WebTestClient
       |
       v
WebFlux WebHandler / WebFilter
       |
       v
HandlerMapping / argument resolver
       |
       +-- Chọn method, đọc Content-Type
       +-- Decode JSON thành DTO
       +-- Bean Validation / method validation
       |        |
       |        +-- lỗi: exception -> error handler -> ProblemDetail
       |
       v
Controller method
       |
       v
Mono<T> / Flux<T> / ResponseEntity<T>
       |
       +-- complete empty -> body không có phần tử
       +-- success with value -> JSON codec
       +-- error -> exception mapping
       |
       v
HttpMessageWriter / HTTP status, headers, bytes
       |
       v
WebTestClient assertions
~~~

Những tầng khác nhau có thể cùng trả HTTP 400 nhưng vì lý do khác nhau: request body không tồn tại, codec không đọc được JSON, Bean Validation không đạt, tham số method không đạt ràng buộc. Test chỉ assert 400 sẽ không phát hiện lỗi mapping sai thông điệp hoặc sai cấu trúc body.

Từ góc nhìn API consumer, cần kiểm tra **hợp đồng quan sát được trên đường HTTP**, không chỉ mock controller method và khẳng định repository/service đã được gọi.

## 3. Năm trạng thái “rỗng” thường bị nhầm lẫn

### 3.1. HTTP 204 No Content

`204` thông báo thao tác thành công nhưng **không gửi message content**. Ví dụ DELETE, cập nhật trạng thái hoặc yêu cầu không cần payload:

~~~java
@GetMapping("/no-content")
public Mono<ResponseEntity<Void>> noContent() {
    return Mono.just(
        ResponseEntity.noContent().<Void>build());
}
~~~

Kỳ vọng:
- HTTP status: 204.
- Response body: không có byte dữ liệu.
- Không kỳ vọng JSON `{}` hoặc `null`.
- Không parse response body thành DTO.

### 3.2. HTTP 200 với body rỗng

~~~java
@GetMapping("/empty-ok")
public Mono<ResponseEntity<Void>> emptyOk() {
    return Mono.just(ResponseEntity.ok().<Void>build());
}
~~~

Kỳ vọng là status 200 nhưng body không có nội dung. Đây là một API contract hợp lệ nếu được thiết kế rõ, tuy nhiên đối với lệnh thực thi không trả kết quả, 204 thường thể hiện ý định trực tiếp hơn.

### 3.3. HTTP 200 chứa một danh sách JSON rỗng

~~~java
@GetMapping("/empty-list")
public Mono<List<ItemView>> emptyList() {
    return Mono.just(List.of());
}
~~~

Với JSON codec bình thường, body là `[]`. **Đây không phải response body rỗng**: nó có hai ký tự JSON và đại diện cho một collection tồn tại nhưng có 0 phần tử.

### 3.4. JSON `null`

Payload `null` gồm bốn ký tự (`n`, `u`, `l`, `l`). Nó khác hẳn không có body. Nếu API contract cho phép giá trị `null`, cần kiểm tra chính xác kiểu và semantics. Không suy luận rằng `Mono.empty()` sẽ tự serialize thành JSON `null`.

### 3.5. `Mono.empty()` ở tầng reactive

`Mono.empty()` là một publisher **không phát `onNext`** mà chỉ `onComplete`. Khi WebFlux sử dụng response chưa có body value, kết quả có thể là response không có content với status đã được chọn/để mặc định; `Mono.empty()` **không có nghĩa tự động là HTTP 204**.

Ví dụ:

~~~java
@GetMapping("/ambiguous")
public Mono<String> ambiguous() {
    return Mono.empty();
}
~~~

Cách rõ ràng hơn khi API phải trả 204 là chọn `ResponseEntity.noContent().build()`; đối với lookup không tìm thấy, chọn `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` hoặc một custom not-found exception được ánh xạ rõ.

### 3.6. Bảng kỳ vọng thực tế

| Trường hợp | HTTP status | Payload quan sát được | Test nên dùng |
| --- | ---: | --- | --- |
| Thao tác không trả nội dung | 204 | 0 byte | `expectStatus().isNoContent()` và `expectBody().isEmpty()` |
| Thành công không có payload | 200 | 0 byte | `expectStatus().isOk()` và `expectBody().isEmpty()` |
| Danh sách trống | 200 | `[]` | `expectBody().json("[]")` |
| JSON null rõ ràng | 200 | `null` | Assert raw JSON/body nếu API contract yêu cầu |
| Object JSON rỗng | 200 | `{}` | JSON object tồn tại nhưng không có field |
| Resource không tồn tại | 404 | Có thể là `ProblemDetail` | Assert status + problem fields |
| `Mono<Void>` complete, status mặc định | Thường 200 tùy handler | Không có onNext | Test HTTP thực, không suy đoán status từ Publisher |

Không dùng `expectBody().isEmpty()` để kiểm tra empty list. Với endpoint collection trả `[]`, assertion `isEmpty()` phải fail: như vậy test mới bảo vệ đúng hợp đồng.

## 4. WebTestClient kiểm tra response body rỗng như thế nào?

`WebTestClient` được Spring Framework hỗ trợ cho cả HTTP server thật lẫn cấu hình bind trực tiếp controller/router. Có thể kiểm tra status/header/body:

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody().isEmpty();
~~~

Theo tài liệu Spring Framework, `expectBody()` kiểm tra raw `byte[]` và có assertion `.isEmpty()` cho response không có nội dung. Không chỉ viết `.expectBody(Void.class)`: kiểu `Void` thường được dùng khi **không quan tâm nội dung** hoặc bỏ qua body; nó không trực tiếp chứng minh body thật sự dài 0 byte theo cách `isEmpty()` làm.

### 4.1. Khi muốn kiểm tra raw bytes

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(result -> {
        byte[] bytes = result.getResponseBody();
        org.junit.jupiter.api.Assertions.assertTrue(
            bytes == null || bytes.length == 0);
    });
~~~

Đây là fragment test với biến `client` đã được khởi tạo; `isEmpty()` ngắn gọn hơn cho hợp đồng phổ biến. Với `consumeWith`, phải tính đến response body có thể được framework biểu diễn bằng `null` hoặc mảng rỗng.

### 4.2. Kiểm tra header

~~~java
client.get()
    .uri("/api/demo/no-content")
    .exchange()
    .expectStatus().isNoContent()
    .expectHeader().doesNotExist("Content-Type")
    .expectBody().isEmpty();
~~~

Nếu endpoint được thiết kế không gửi `Content-Type` trong 204, assertion này có thể hữu ích. Không viết assertion về header không nằm trong contract hoặc do gateway tự thêm khi deployment, nếu test chỉ quan tâm semantics của status/body. Chọn mức nghiêm ngặt phù hợp.

### 4.3. 200 body rỗng khác 204

~~~java
client.get()
    .uri("/api/demo/empty-ok")
    .exchange()
    .expectStatus().isOk()
    .expectBody().isEmpty();
~~~

Cả 200 và 204 đều có thể đi kèm 0 byte payload; **status không thay thế body assertion**. Khi frontend chỉ kiểm tra status mà cố parse JSON, `response.json()` có thể lỗi trên response 204 vì không có nội dung JSON.

### 4.4. JSON empty list

~~~java
client.get()
    .uri("/api/demo/empty-list")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .json("[]");
~~~

`json("[]")` kiểm tra nội dung JSON. Với schema phức tạp, dùng JSONPath và `expectBodyList(Dto.class)`; đừng giả định thứ tự phần tử nếu truy vấn phía DB không có `ORDER BY`.

## 5. Validation trong Spring WebFlux diễn ra ở đâu?

Có hai mức validation dễ bị đánh đồng:

1. **Argument-level validation** cho DTO `@Valid @RequestBody` hoặc `@Validated` áp dụng tới object, thường tạo `WebExchangeBindException`.
2. **Method validation** khi constraint như `@Min`, `@NotBlank`, `@NotNull` được đặt trực tiếp lên tham số method/return value; Spring WebFlux có thể tạo `HandlerMethodValidationException`.

Ngoài ra, decoding và required body thường gặp `ServerWebInputException`; thiếu hoặc sai Content-Type có thể dẫn tới nhóm lỗi khác như `UnsupportedMediaTypeStatusException`.

### 5.1. DTO được kiểm tra bằng Bean Validation

~~~java
public record CreateItemRequest(
    @NotBlank @Size(max = 60) String name,
    @NotNull @Min(1) Integer quantity
) {}
~~~

Ràng buộc:
- `name` không được null, empty hoặc chỉ chứa whitespace; tối đa 60 ký tự theo Bean Validation size.
- `quantity` phải tồn tại và lớn hơn hoặc bằng 1.
- Annotation nằm trên record components; validation provider sẽ đọc các constraint tương ứng.
- Không tin rằng `@Valid` tự hoạt động nếu classpath thiếu Jakarta Validation provider (thêm `spring-boot-starter-validation`).

Controller:

~~~java
@PostMapping("/items")
public Mono<ResponseEntity<ItemView>> create(
        @Valid @RequestBody CreateItemRequest request) {

    return service.create(request)
        .map(item ->
            ResponseEntity.created(
                URI.create("/api/demo/items/" + item.id()))
                .body(item));
}
~~~

Đây là **fragment minh họa** với `service`, `ItemView` và `URI` đã định nghĩa. Trong project runnable ở mục 16 sẽ có đầy đủ controller/service/DTO. Nếu DTO không hợp lệ, argument resolver/validator có thể ném `WebExchangeBindException` trước khi method tạo response.

### 5.2. Method-level constraint

~~~java
@GetMapping("/quantity/{amount}")
public Mono<Map<String, Integer>> quantity(
        @PathVariable @Min(1) int amount) {

    return Mono.just(Map.of("amount", amount));
}
~~~

`@Min(1)` gắn **trực tiếp** lên method parameter. Spring WebFlux built-in method validation có thể báo `HandlerMethodValidationException` khi nhận `amount=0`.

Nếu controller có thêm `@Validated` ở class level, Spring có thể dùng AOP method validation thay vì cơ chế handler method validation tích hợp; khi kiểm thử `HandlerMethodValidationException`, **không thêm `@Validated` vào class** chỉ vì thấy validation annotation trong DTO.

### 5.3. `@Valid` không phải một constraint trực tiếp

`@Valid` yêu cầu nested/bean validation. Nếu bạn thêm `@NotNull` trực tiếp lên `@Valid @RequestBody` parameter, method validation có thể trở thành cơ chế ưu tiên thay cho object-only validation. Do đó cùng DTO có thể phát ra loại exception khác nếu method signature đổi.

Spring Framework khuyến nghị xử lý cả `WebExchangeBindException` và `HandlerMethodValidationException` khi API dùng cả argument-level và method-level constraints.

### 5.4. Chú ý request body reactive type

~~~java
public Mono<Void> create(
        @Valid @RequestBody Mono<CreateItemRequest> body) {

    return body.flatMap(service::save).then();
}
~~~

Đây là fragment; validation cho `Mono<CreateItemRequest>` diễn ra khi publisher request body được subscribe, và lỗi có thể đi qua reactive chain. Không gọi `subscribe()` thủ công để “làm cho validation chạy”. Trong bài runnable, controller dùng DTO trực tiếp để hiển thị rõ exception mapping trước handler body.

## 6. Phân loại lỗi request đầu vào

| Tình huống | Phát sinh ở đâu? | Exception thường gặp | HTTP contract khuyến nghị |
| --- | --- | --- | --- |
| POST không có body trong khi `required=true` | Argument resolver | `ServerWebInputException` | 400 `INVALID_BODY` |
| JSON sai cú pháp | Decoder/codec | `ServerWebInputException` (bọc decoding error) | 400 `INVALID_BODY` |
| JSON hợp lệ, field `name` rỗng | Bean Validation | `WebExchangeBindException` | 400 `VALIDATION_FAILED` |
| JSON hợp lệ, `quantity=0` | Bean Validation | `WebExchangeBindException` | 400 `VALIDATION_FAILED` |
| Path `amount=0` với `@Min(1)` | Method validation | `HandlerMethodValidationException` | 400 `METHOD_VALIDATION_FAILED` |
| Unsupported Content-Type | Message reader/content negotiation | `UnsupportedMediaTypeStatusException` | 415, có thể là ProblemDetail |
| Resource ID không tồn tại | Service/lookup | Domain not-found exception | 404 `ITEM_NOT_FOUND` |
| DB/gateway không khả dụng | Service/infrastructure | Timeout, connection error... | 5xx hoặc 503 với detail an toàn |
| Trạng thái nghiệp vụ không thể xử lý | Business rule | Domain validation | 409 hoặc 422 tùy contract |

Đây là **các nhóm thường gặp**; error mapping cụ thể phụ thuộc Spring/Boot configuration và exception handler của ứng dụng. Không viết test đòi một loại exception bên trong nếu mục tiêu cần bảo vệ chỉ là HTTP semantics; tuy nhiên test riêng loại exception ở service/controller layer có thể phát hiện regression trong mapping.

## 7. ProblemDetail là gì?

`ProblemDetail` là abstraction của Spring Framework để diễn tả lỗi HTTP theo **RFC 9457 (Problem Details for HTTP APIs)**. Khi được serialize ở REST API, response thường có media type `application/problem+json`.

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://example.org/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request validation failed",
  "instance": "/api/demo/items",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "name", "message": "must not be blank"},
    {"field": "quantity", "message": "must be greater than or equal to 1"}
  ]
}
~~~

`example.org` là domain dành cho ví dụ tài liệu; production phải dùng namespace và tài liệu lỗi chính thức của API.

### 7.1. Ý nghĩa năm trường chuẩn

| Field | Kiểu | Vai trò |
| --- | --- | --- |
| `type` | URI | Định danh **loại lỗi**; có thể trỏ tới tài liệu |
| `title` | string | Tiêu đề ngắn, ổn định cho loại lỗi |
| `status` | number | HTTP status của lỗi, ví dụ 400/404/500 |
| `detail` | string | Giải thích lỗi cụ thể, an toàn với client |
| `instance` | URI-reference | Xác định request occurrence/path hoặc ID của tình huống lỗi |

Theo RFC, một số field có thể vắng mặt tùy producer; không giả định mọi ProblemDetail ở mọi framework đều chứa toàn bộ năm field trừ khi API contract đã quy định. Trong ví dụ project của bài, ta **chủ động đặt cả năm** để test ổn định.

### 7.2. Các field mở rộng

Spring `ProblemDetail` có `setProperty(String, Object)` để đính kèm extension properties. Với Jackson mixin do Spring đăng ký, các thuộc tính này có thể xuất hiện ở top-level JSON:

~~~java
ProblemDetail problem =
    ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Request validation failed");

problem.setProperty("code", "VALIDATION_FAILED");
problem.setProperty("errors", List.of(
    Map.of("field", "name", "message", "must not be blank")
));
~~~

Ví dụ là fragment cần import `ProblemDetail`, `HttpStatus`, `List`, `Map`. Không nhét nguyên `BindingResult` hoặc exception object vào `properties`; chúng chứa cấu trúc phức tạp, rejected value, thậm chí dữ liệu nhạy cảm.

### 7.3. `type` không phải HTTP status

Nhiều API sai khi đặt `type="400"` hoặc `"VALIDATION_FAILED"` mà không có URI rõ nghĩa. Một cách thiết kế ổn định là dùng URI phân loại:

~~~text
https://example.org/problems/validation-failed
https://example.org/problems/invalid-body
https://example.org/problems/method-validation-failed
https://example.org/problems/item-not-found
https://example.org/problems/internal-error
~~~

Mã `code` là field riêng cho frontend xử lý theo nhánh. `title` dành cho người đọc, `detail` được localize/điều chỉnh theo lỗi, và `type` là định danh của loại lỗi.

### 7.4. HTTP status và field status phải nhất quán

Một response nguy hiểm là HTTP 200 nhưng body `{"status":400,...}`. Client, proxy, tracing và retry thường dựa vào HTTP status thực, không chỉ body JSON.

Test phải xác nhận **cả** `.expectStatus().isBadRequest()` và `.jsonPath("$.status").isEqualTo(400)`; đồng thời kiểm tra Content-Type. Không chỉ assert `$.status=400`.

## 8. Cơ chế ProblemDetail mặc định và custom

Spring Framework hỗ trợ `ErrorResponse`, `ErrorResponseException`, `ProblemDetail` và `ResponseEntityExceptionHandler`. Spring Boot WebFlux có thể bật xử lý lỗi ProblemDetail qua:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Tài liệu Spring Boot 4.0 mô tả property trên để auto-configure xử lý các lỗi built-in theo problem format. Khi cần schema business riêng, có thể thêm `@RestControllerAdvice` cho các exception cụ thể.

Nếu Boot đã có advice từ `ResponseEntityExceptionHandler` với order mặc định, custom advice cho cùng exception nên được ưu tiên, ví dụ:

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {
    // @ExceptionHandler cho các loại lỗi mà API muốn tùy biến.
}
~~~

Đây là fragment; project runnable cung cấp toàn bộ handler. Không đăng ký một catch-all `@ExceptionHandler(Exception.class)` với priority cao để đổi tất cả lỗi thành status 400; như vậy sẽ che 404/415/500 và làm monitoring sai.

Một phương án khác là kế thừa `ResponseEntityExceptionHandler` và override các method xử lý built-in error. Chọn **một chiến lược nhất quán**, hiểu thứ tự advice và kiểm tra kết quả HTTP thực trước khi triển khai.

## 9. Thiết kế field error response an toàn

Khi Bean Validation fail, `WebExchangeBindException` chứa `BindingResult` với danh sách `FieldError` và `ObjectError`. Không nên serialize trực tiếp exception hoặc rejected object ra client.

Ví dụ mapping:

~~~java
List<Map<String, String>> errors =
    exception.getFieldErrors().stream()
        .map(error -> Map.of(
            "field", error.getField(),
            "message",
            error.getDefaultMessage() == null
                ? "invalid"
                : error.getDefaultMessage()))
        .toList();
~~~

Đây là fragment cần `exception` kiểu `WebExchangeBindException` và import `List/Map`. Với input có PII như password, secret, token:
- Chỉ gửi **tên field và thông điệp validation an toàn**.
- Không gửi `rejectedValue`, raw JSON, SQL exception, stack trace.
- Không gửi thông điệp chứa nội dung user đã nhập nếu không cần.
- Có thể dùng mã ổn định như `NOT_BLANK`, `MIN_VALUE` để tránh frontend parse ngôn ngữ tự nhiên.
- Thông điệp validation có thể được localize; test không nên assert nguyên văn message nếu localization không thuộc contract.

Đối với trường `errors`, chọn schema thống nhất: danh sách `{field, code, message}` hoặc map field-to-errors. Không thay schema tùy endpoint. Nếu một field có nhiều lỗi, danh sách cần hỗ trợ nhiều entry cho cùng field.

### 9.1. Kiểm tra nội dung quan trọng nhưng tránh brittle

Nên assert:
- HTTP status `400`.
- Content-Type compatible `application/problem+json`.
- `type` cố định.
- `status=400`.
- `code="VALIDATION_FAILED"`.
- `errors` là array và chứa field liên quan.
- `instance` đúng route khi contract yêu cầu.

Không nên assert:
- Thứ tự `errors` nếu API không quy định.
- Nguyên văn thông điệp quốc tế hóa trong mọi locale.
- Timestamp hoặc request ID ngẫu nhiên là một giá trị cố định.
- Stack trace hoặc class name implementation.

Với project demo, ta chủ động sort `errors` theo tên field để output ổn định, nhưng integration test vẫn ưu tiên kiểm tra schema và semantics.

## 10. Viết assertions cho ProblemDetail bằng WebTestClient

Ví dụ đầy đủ trên API contract:

~~~java
client.post()
    .uri("/api/demo/items")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_PROBLEM_JSON)
    .bodyValue(new CreateItemRequest(" ", 0))
    .exchange()
    .expectStatus().isBadRequest()
    .expectHeader()
        .contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON)
    .expectBody()
    .jsonPath("$.type").isEqualTo(
        "https://example.org/problems/validation-failed")
    .jsonPath("$.title").isEqualTo("Validation failed")
    .jsonPath("$.status").isEqualTo(400)
    .jsonPath("$.detail").isEqualTo("Request validation failed")
    .jsonPath("$.instance").isEqualTo("/api/demo/items")
    .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
    .jsonPath("$.errors").isArray();
~~~

Đoạn trên cần `client` đã được khởi tạo và DTO của project. Thứ tự gọi `.accept(MediaType.APPLICATION_PROBLEM_JSON)` không bắt buộc nếu server luôn trả problem content-type theo handler, nhưng giúp test diễn đạt rõ định dạng mong đợi.

### 10.1. Kiểm tra `$.errors` chứa field cần thiết

Có thể lấy raw body để parse bằng `ObjectMapper`/Jackson hoặc `JsonPath`, rồi assert theo tập hợp tên field thay vì vị trí index. Ví dụ fragment:

~~~java
.expectBody()
.consumeWith(result -> {
    String json = new String(
        result.getResponseBody(), StandardCharsets.UTF_8);

    assertTrue(json.contains("\"field\":\"name\""));
    assertTrue(json.contains("\"field\":\"quantity\""));
});
~~~

Cách `contains` chỉ phù hợp demo nhỏ, vì JSON có thể chèn whitespace hoặc đổi thứ tự. Test production nên parse JSON bằng `ObjectMapper` hoặc JsonPath để kiểm tra cấu trúc, ví dụ dùng `JsonPath.read(json, "$.errors[*].field")` rồi assert một `Set`. Trong project runnable, test chỉ assert `errors` là array để giữ đơn giản và tránh phụ thuộc vào field order.

### 10.2. Kiểm tra `application/problem+json`

`application/problem+json` là media type riêng; không nên chỉ assert `application/json`. Với `WebTestClient`:

~~~java
.expectHeader()
    .contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON)
~~~

Không khẳng định mọi exception mặc định của mọi ứng dụng Boot tự có problem content-type nếu chưa bật hỗ trợ hoặc custom handler tương ứng. Demo đã bật hỗ trợ và có advice để contract ổn định.

### 10.3. Khi nào dùng typed `ProblemDetail`?

Bạn có thể decode trực tiếp:

~~~java
client.post()
    .uri("/api/demo/items")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateItemRequest(" ", 0))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody(ProblemDetail.class)
    .value(problem -> {
        assertEquals(400, problem.getStatus());
        assertEquals("Validation failed", problem.getTitle());
    });
~~~

Lưu ý: deserialization và extension-field handling phụ thuộc ObjectMapper/codec được WebTestClient cấu hình. Nếu chỉ muốn test public JSON contract mà không cần Java type coupling, JSONPath thường rõ ràng hơn.

## 11. Test request body không gửi, JSON sai và Bean Validation sai

Ba trường hợp có thể đều trả 400, nhưng `code` nên khác nhau:

~~~text
POST /api/demo/items
Content-Type: application/json

(no bytes)
    -> 400 INVALID_BODY
~~~

~~~text
POST /api/demo/items
Content-Type: application/json

{not-valid-json
    -> 400 INVALID_BODY
~~~

~~~text
POST /api/demo/items
Content-Type: application/json

{"name":" ","quantity":0}
    -> 400 VALIDATION_FAILED
~~~

Cách phân biệt:
- Không body: argument resolver không có dữ liệu required.
- JSON sai: decoder không tạo được DTO.
- JSON hợp lệ, ràng buộc sai: DTO đã tạo nhưng Bean Validation fail.

Nếu frontend cần hiển thị lỗi theo field, chỉ `VALIDATION_FAILED` mới có `errors` theo field. Với `INVALID_BODY`, không có field errors chính xác vì DTO có thể chưa được parse; trả mã lỗi và lời giải thích an toàn.

### 11.1. Không gộp mọi lỗi thành 422

HTTP 400 phù hợp cho malformed JSON và Bean Validation ở nhiều API Spring. 422 Unprocessable Content có thể là chính sách API cho semantic validation đã được thỏa thuận, nhưng không tự thay đổi status của Spring rồi giả định frontend hiểu.

Mục tiêu test là bảo vệ **contract cụ thể**, không tranh luận rằng tất cả lỗi validation bắt buộc phải là 422. Nếu tổ chức chọn 422, hãy thiết kế exception mapping và test status/body nhất quán.

## 12. Kịch bản “body rỗng” phía request và response là khác nhau

| Góc nhìn | Điều đang kiểm tra | API liên quan |
| --- | --- | --- |
| Request | Client không gửi body required | `@RequestBody(required = true)` mặc định |
| Request | Client gửi body JSON có field rỗng | `@NotBlank`, `@NotNull`, `@Min` |
| Request | Client gửi JSON `{}` | Validation của field bắt buộc có thể fail |
| Response | Server trả 204 zero body | `ResponseEntity.noContent()` |
| Response | Server trả 200 zero body | `ResponseEntity.ok().build()` |
| Response | Server trả JSON `[]` | `Mono.just(List.of())` |
| Response | Server trả ProblemDetail | `ProblemDetail` + `application/problem+json` |

Không sử dụng một test “rỗng” cho cả hai hướng. `expectBody().isEmpty()` kiểm tra **response body**, không kiểm tra request body đã gửi đủ hay chưa.

## 13. Kiểm thử lỗi 404 và 500 mà không lộ thông tin

Một API thường cần hai dạng lỗi khác validation:
- `404`: tài nguyên không có, client có thể điều chỉnh ID hoặc chuyển trạng thái UI.
- `500`: lỗi nội bộ, client không nên nhận SQL/connection details, stack trace hoặc dữ liệu vận hành.

Cả hai có thể dùng `ProblemDetail`:
- 404 `type=https://example.org/problems/item-not-found`, `code=ITEM_NOT_FOUND`, `status=404`.
- 500 `type=https://example.org/problems/internal-error`, `code=INTERNAL_ERROR`, `status=500`, `detail` chung và an toàn.

Test 500 nên kiểm tra:
1. HTTP status 5xx.
2. `Content-Type: application/problem+json`.
3. `$.status=500` và `$.code=INTERNAL_ERROR`.
4. Response **không chứa** raw internal exception message.
5. Có server-side correlation/trace để điều tra mà không lộ raw error cho client.

Không dùng `.expectStatus().isOk()` cho một method lỗi chỉ vì controller đã dùng `onErrorResume(error -> Mono.empty())`: cách đó sẽ biến lỗi thành response thành công rỗng và che giấu sự cố.

## 14. Các loại test nên viết

### 14.1. Service-level unit test với StepVerifier

Nếu một reactive service trả `Mono<Item>` hoặc `Mono.empty()`, test tín hiệu:

~~~java
StepVerifier.create(service.find("missing"))
    .verifyComplete();
~~~

Hoặc khi lỗi:

~~~java
StepVerifier.create(service.create(invalid))
    .expectError(InvalidItemException.class)
    .verify();
~~~

Đây là fragment dùng các kiểu service/exception minh họa, không phải API đầy đủ của demo dưới. StepVerifier kiểm tra **publisher signals**, chưa xác nhận chúng được WebFlux ánh xạ thành HTTP 400/404.

### 14.2. WebTestClient bind trực tiếp controller

~~~java
WebTestClient client = WebTestClient
    .bindToController(controller)
    .build();
~~~

Phù hợp với test route, handler mapping, serialization và body semantics, nhưng khi kiểm tra validation/advice/phụ thuộc cần đăng ký cấu hình tương ứng (`controllerAdvice`, validator...). Nếu dùng `bindToController` mà quên advice, ProblemDetail có thể khác contract của ứng dụng.

### 14.3. HTTP server thật

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiContractTest {
    // WebTestClient.bindToServer() + baseUrl(local.server.port)
}
~~~

Cách này mở context Spring Boot thật, chạy codec/validation/advice đã cấu hình và kiểm tra request/response qua HTTP. Nó không đòi database hoặc external service nếu controller dùng demo service deterministic.

### 14.4. Kiểm thử qua proxy production-like

Một test local không bảo đảm header/caching/compression/CORS/proxy error response ngoài production giống hệt. Với ứng dụng thật, bổ sung staging smoke test qua ingress/API gateway để xác nhận:
- 204 không bị proxy thêm body JSON giả.
- ProblemDetail giữ đúng Content-Type.
- Reverse proxy không biến 400/404 thành HTML lỗi chung.
- Correlation ID vẫn có và không lộ secret.
- Method validation và size limits vẫn đúng.

## 15. Thiết kế test matrix trước khi code

| Tên test | Request | Expected status | Body assertion |
| --- | --- | ---: | --- |
| `noContentHasEmptyPayload` | GET `/no-content` | 204 | `isEmpty()` |
| `okCanHaveEmptyPayload` | GET `/empty-ok` | 200 | `isEmpty()` |
| `emptyListIsJsonArrayNotEmptyBody` | GET `/empty-list` | 200 | JSON `[]` |
| `validItemReturnsCreatedJson` | POST valid JSON | 201 | `id`, `name`, `quantity`, Location |
| `invalidFieldsReturnProblemDetail` | POST blank name, 0 quantity | 400 | ProblemDetail `VALIDATION_FAILED`, errors array |
| `missingRequestBodyReturnsInvalidBody` | POST no body | 400 | ProblemDetail `INVALID_BODY` |
| `malformedJsonReturnsInvalidBody` | POST invalid JSON | 400 | ProblemDetail `INVALID_BODY` |
| `methodParameterConstraintReturnsProblemDetail` | GET `/quantity/0` | 400 | ProblemDetail `METHOD_VALIDATION_FAILED` |
| `missingResourceReturnsProblemDetail404` | GET `/missing` | 404 | ProblemDetail `ITEM_NOT_FOUND` |
| `internalErrorIsSanitized` | GET `/fault` | 500 | ProblemDetail `INTERNAL_ERROR`, no raw exception |
| `unsupportedMediaTypeReturns415` | POST `text/plain` | 415 | Không khẳng định body tùy biến nếu chưa định nghĩa |

Đây là ma trận tối thiểu có chủ đích. Những API production dùng pagination, authentication, multipart hoặc streaming cần thêm các kịch bản riêng; đừng nhét tất cả vào một test “400 error”.

## 16. Project runnable: Spring Boot 4.0.9 + Java 17 + WebFlux

Demo sau có thể chạy không cần database hoặc cloud service. Nó tập trung kiểm tra **HTTP contract** thay vì persistence. Service tạo ID bằng `AtomicLong` để các test không phụ thuộc ID cố định, nhưng không lưu items: đây là API mô phỏng cho bài testing, không phải implementation CRUD production.

### 16.1. Cấu trúc project

~~~text
webflux-problem-contract/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/problem/
│   ├── ProblemContractApplication.java
│   ├── CreateItemRequest.java
│   ├── ItemView.java
│   ├── ItemNotFoundException.java
│   ├── DemoItemService.java
│   ├── DemoController.java
│   └── ApiProblemHandler.java
└── src/test/java/com/example/problem/
    └── ApiContractIntegrationTest.java
~~~

### 16.2. `pom.xml`

Sử dụng Spring Boot 4.0.9 và Java 17+; starter validation cung cấp Jakarta Validation provider. Starter test WebFlux và JUnit 5 ở `test` scope.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-problem-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không thêm `spring-boot-starter-webmvc` vì bài này kiểm tra Spring WebFlux. Cùng tồn tại MVC và WebFlux starter có thể làm Boot chọn servlet web application theo auto-configuration; chỉ thêm stack cần dùng.

### 16.3. `application.properties`

~~~properties
spring.application.name=webflux-problem-contract
spring.webflux.problemdetails.enabled=true
~~~

Property bật xử lý ProblemDetail của Boot WebFlux cho các lỗi built-in được framework hỗ trợ. Custom `ApiProblemHandler` ưu tiên xử lý những lỗi API muốn có schema ổn định. Không dùng config hiển thị stacktrace và exception message ra response production.

### 16.4. `ProblemContractApplication.java`

~~~java
package com.example.problem;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProblemContractApplication.class, args);
    }
}
~~~

### 16.5. `CreateItemRequest.java`

~~~java
package com.example.problem;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateItemRequest(
    @NotBlank @Size(max = 60) String name,
    @NotNull @Min(1) Integer quantity
) {}
~~~

Trường `Integer` thay vì `int` để `@NotNull` phát hiện JSON thiếu field. `quantity=0` bị `@Min(1)` phát hiện. Nếu `name=null`, `@NotBlank` cũng không đạt.

### 16.6. `ItemView.java`

~~~java
package com.example.problem;

public record ItemView(
    String id,
    String name,
    int quantity
) {}
~~~

DTO đầu ra độc lập với request DTO để sau này có thể thay đổi persistence mà không buộc thay schema response.

### 16.7. `ItemNotFoundException.java`

~~~java
package com.example.problem;

public class ItemNotFoundException extends RuntimeException {

    public ItemNotFoundException(String id) {
        super("Item not found: " + id);
    }
}
~~~

Exception đại diện business not-found. Trong API handler không trả nguyên exception message cho client: message có thể chứa ID hoặc dữ liệu nội bộ; thay bằng thông điệp đã chuẩn hóa.

### 16.8. `DemoItemService.java`

~~~java
package com.example.problem;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class DemoItemService {

    private final AtomicLong sequence = new AtomicLong();

    public Mono<ItemView> create(CreateItemRequest request) {
        return Mono.fromSupplier(() ->
            new ItemView(
                Long.toString(sequence.incrementAndGet()),
                request.name().trim(),
                request.quantity()));
    }

    public Mono<ItemView> missing() {
        return Mono.error(new ItemNotFoundException("unknown"));
    }

    public Mono<ItemView> fail() {
        return Mono.error(new IllegalStateException(
            "internal connection endpoint: secret-location"));
    }
}
~~~

`Mono.fromSupplier` tạo item khi Publisher được subscribe; code này chỉ thao tác bộ nhớ, không blocking I/O. Endpoint `/missing`/`/fault` cố ý mô phỏng lỗi để test error contract. Không dùng chuỗi lỗi nội bộ mô phỏng làm response của API.

### 16.9. `DemoController.java`

~~~java
package com.example.problem;

import java.net.URI;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    private final DemoItemService service;

    public DemoController(DemoItemService service) {
        this.service = service;
    }

    @GetMapping("/no-content")
    public Mono<ResponseEntity<Void>> noContent() {
        return Mono.just(
            ResponseEntity.noContent().<Void>build());
    }

    @GetMapping("/empty-ok")
    public Mono<ResponseEntity<Void>> emptyOk() {
        return Mono.just(ResponseEntity.ok().<Void>build());
    }

    @GetMapping(
        value = "/empty-list",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<ItemView>> emptyList() {
        return Mono.just(List.of());
    }

    @PostMapping(
        value = "/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest request) {

        return service.create(request)
            .map(item ->
                ResponseEntity
                    .created(URI.create(
                        "/api/demo/items/" + item.id()))
                    .body(item));
    }

    @GetMapping(
        value = "/quantity/{amount}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Integer>> quantity(
            @PathVariable @Min(1) int amount) {

        return Mono.just(Map.of("amount", amount));
    }

    @GetMapping("/missing")
    public Mono<ItemView> missing() {
        return service.missing();
    }

    @GetMapping("/fault")
    public Mono<ItemView> fault() {
        return service.fail();
    }
}
~~~

Không có `@Validated` ở class level; `@Min(1)` trên path variable dùng built-in method validation. `@Valid @RequestBody` trên record dùng object validation. Không gọi `.block()` hoặc `.subscribe()` trong controller; WebFlux quản lý subscription và response lifecycle.

### 16.10. `ApiProblemHandler.java`

~~~java
package com.example.problem;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> beanValidation(
            WebExchangeBindException exception,
            ServerWebExchange exchange) {

        List<Map<String, String>> errors =
            exception.getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "message",
                    error.getDefaultMessage() == null
                        ? "invalid"
                        : error.getDefaultMessage()))
                .sorted(Comparator.comparing(
                    error -> error.get("field")))
                .toList();

        ResponseEntity<ProblemDetail> response =
            problem(
                exchange,
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Validation failed",
                "Request validation failed");

        response.getBody().setProperty("errors", errors);
        return response;
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.BAD_REQUEST,
            "METHOD_VALIDATION_FAILED",
            "Method validation failed",
            "A request parameter violates a constraint");
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> invalidBody(
            ServerWebInputException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.BAD_REQUEST,
            "INVALID_BODY",
            "Invalid request body",
            "The JSON request body is missing or unreadable");
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException exception,
            ServerWebExchange exchange) {

        return problem(
            exchange,
            HttpStatus.NOT_FOUND,
            "ITEM_NOT_FOUND",
            "Item not found",
            "The requested item does not exist");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ProblemDetail> internalError(
            IllegalStateException exception,
            ServerWebExchange exchange) {

        // Trong production ghi log có request/trace ID an toàn ở server.
        // Không trả exception.getMessage() cho browser.
        return problem(
            exchange,
            HttpStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Internal server error",
            "Unexpected server failure");
    }

    private static ResponseEntity<ProblemDetail> problem(
            ServerWebExchange exchange,
            HttpStatus status,
            String code,
            String title,
            String detail) {

        ProblemDetail pd =
            ProblemDetail.forStatusAndDetail(status, detail);

        pd.setType(URI.create(
            "https://example.org/problems/"
                + code.toLowerCase(Locale.ROOT)
                    .replace('_', '-')));
        pd.setTitle(title);
        pd.setInstance(URI.create(
            exchange.getRequest().getPath().value()));
        pd.setProperty("code", code);

        return ResponseEntity.status(status)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(pd);
    }
}
~~~

Giải thích:
1. Advice xử lý `WebExchangeBindException` trước handler tổng quát cho `ServerWebInputException` vì hai kiểu có quan hệ kế thừa; Spring chọn handler theo kiểu exception cụ thể.
2. `HandlerMethodValidationException` được xử lý riêng, tránh đồng nhất với lỗi body.
3. `ProblemDetail.forStatusAndDetail` đặt `status` và `detail`; chương trình đặt tiếp type/title/instance.
4. `response.getBody().setProperty("errors", ...)` an toàn ở đây vì method `problem` luôn tạo body `ProblemDetail` mới; trong kiến trúc production có thể tách helper trả `ProblemDetail` trước rồi tạo ResponseEntity.
5. `@Order(Ordered.HIGHEST_PRECEDENCE)` ưu tiên custom handler so với auto-configured default advice của Boot cho những loại exception trùng nhau.
6. Các lỗi không custom, như unsupported Content-Type 415, vẫn có thể do Spring Boot error handling mặc định xử lý theo config.
7. Server 500 chỉ trả thông điệp chung, không trả raw exception message chứa thông tin endpoint/secret.
8. `instance` đang dùng path của request, phù hợp demo; trong API thực, cân nhắc trace ID riêng và không đưa PII/secret từ URL vào error payload.

## 17. HTTP integration tests bằng WebTestClient

Test khởi động Spring Boot ở random port để dùng toàn bộ validation, codec, advice và REST route; không phải mock riêng controller.

### 17.1. `ApiContractIntegrationTest.java`

~~~java
package com.example.problem;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiContractIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void noContentHasEmptyPayload() {
        http().get()
            .uri("/api/demo/no-content")
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();
    }

    @Test
    void okCanHaveEmptyPayload() {
        http().get()
            .uri("/api/demo/empty-ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody().isEmpty();
    }

    @Test
    void emptyListIsJsonArrayNotEmptyBody() {
        http().get()
            .uri("/api/demo/empty-list")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody().json("[]");
    }

    @Test
    void validItemReturnsCreatedJson() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(
                new CreateItemRequest("Notebook", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueMatches("Location",
                    "/api/demo/items/[0-9]+")
            .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.name").isEqualTo("Notebook")
                .jsonPath("$.quantity").isEqualTo(3);
    }

    @Test
    void invalidFieldsReturnProblemDetail() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(new CreateItemRequest(" ", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.type").isEqualTo(
                    "https://example.org/problems/validation-failed")
                .jsonPath("$.title").isEqualTo("Validation failed")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.detail").isEqualTo(
                    "Request validation failed")
                .jsonPath("$.instance").isEqualTo(
                    "/api/demo/items")
                .jsonPath("$.code").isEqualTo(
                    "VALIDATION_FAILED")
                .jsonPath("$.errors").isArray();
    }

    @Test
    void missingRequestBodyReturnsInvalidBody() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo(
                    "INVALID_BODY");
    }

    @Test
    void malformedJsonReturnsInvalidBody() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{not-valid-json")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.code").isEqualTo(
                    "INVALID_BODY");
    }

    @Test
    void methodParameterConstraintReturnsProblemDetail() {
        http().get()
            .uri("/api/demo/quantity/0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo(
                    "METHOD_VALIDATION_FAILED");
    }

    @Test
    void missingResourceReturnsProblemDetail404() {
        http().get()
            .uri("/api/demo/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo(
                    "ITEM_NOT_FOUND")
                .jsonPath("$.instance").isEqualTo(
                    "/api/demo/missing");
    }

    @Test
    void internalErrorIsSanitized() {
        http().get()
            .uri("/api/demo/fault")
            .exchange()
            .expectStatus().is5xxServerError()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .consumeWith(result -> {
                byte[] bytes = result.getResponseBody();

                assertNotNull(bytes);

                String body = new String(
                    bytes, StandardCharsets.UTF_8);

                assertFalse(body.contains("secret-location"));
                assertFalse(body.contains("connection endpoint"));
            });
    }

    @Test
    void unsupportedMediaTypeReturns415() {
        http().post()
            .uri("/api/demo/items")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("hello")
            .exchange()
            .expectStatus().isEqualTo(415);
    }
}
~~~

**Lưu ý khi review test:**
- Random port tránh trùng port 8080 trong CI.
- `expectBody().isEmpty()` xác nhận body không có nội dung.
- `emptyList` dùng `.json("[]")`, không dùng `.isEmpty()`.
- Các test body lỗi kiểm tra status + schema + problem content-type.
- 201 check `Location` bằng pattern vì ID tăng động, không assert ID cụ thể.
- Kiểm tra server 500 **không lộ** chi tiết lỗi nội bộ.
- Test 415 chỉ assert status vì cấu trúc lỗi mặc định không phải trọng tâm của custom handler.
- Chưa dùng DB thật, nên test bảo vệ HTTP contract, không chứng minh transactional correctness hoặc connection pool performance.

### 17.2. Test body rỗng bằng typed API

Nếu không cần custom error object:

~~~java
client.delete()
    .uri("/api/items/123")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody().isEmpty();
~~~

Đây là fragment dành cho API có endpoint DELETE tương ứng, **không phải route trong demo mục 16**. Khác với `expectBody(Void.class)`, `isEmpty()` nói rõ yêu cầu 0 byte.

### 17.3. Test một exception ở service mà không khởi động HTTP

~~~java
Mono<ItemView> failing = Mono.error(
    new IllegalArgumentException("invalid quantity"));

StepVerifier.create(failing)
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Đây là fragment JUnit với Reactor Test. Dùng `StepVerifier` để kiểm tra tín hiệu trong service; dùng `WebTestClient` để kiểm tra `IllegalArgumentException` được HTTP mapper chuyển thành status/ProblemDetail đúng. Hai lớp test không thay thế nhau.

## 18. Lệnh chạy và kiểm tra bằng curl

Yêu cầu:
- JDK 17+ và Maven.
- Network tải dependencies Maven lần đầu.
- Port 8080 còn trống nếu chạy mặc định.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

### 18.1. 204 không có body

~~~bash
curl -i http://localhost:8080/api/demo/no-content
~~~

Kỳ vọng status `204 No Content`, không có JSON body. Với `curl -i`, bạn vẫn nhìn thấy header (đó không phải body).

### 18.2. 200 body không có byte

~~~bash
curl -i http://localhost:8080/api/demo/empty-ok
~~~

Kỳ vọng status `200 OK`, body 0 byte. Không suy luận thành `null` hoặc `[]`.

### 18.3. 200 danh sách JSON rỗng

~~~bash
curl -i http://localhost:8080/api/demo/empty-list
~~~

Body:

~~~json
[]
~~~

### 18.4. Tạo item hợp lệ

Linux/macOS shell:

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","quantity":3}'
~~~

Windows CMD:

~~~bat
curl -i -X POST http://localhost:8080/api/demo/items ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Notebook\",\"quantity\":3}"
~~~

Response minh họa; ID được sinh khi request được subscribe:

~~~http
HTTP/1.1 201 Created
Location: /api/demo/items/1
Content-Type: application/json

{"id":"1","name":"Notebook","quantity":3}
~~~

### 18.5. Validation 400 ProblemDetail

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"name":" ","quantity":0}'
~~~

Kỳ vọng `application/problem+json`, `status:400`, `code:VALIDATION_FAILED`, có `errors` của `name` và `quantity`. Thứ tự field errors có thể được sort theo tên do demo handler.

### 18.6. Body không gửi

~~~bash
curl -i -X POST http://localhost:8080/api/demo/items \
  -H "Content-Type: application/json"
~~~

Kỳ vọng 400 `INVALID_BODY`.

### 18.7. Method validation

~~~bash
curl -i http://localhost:8080/api/demo/quantity/0
~~~

Kỳ vọng 400 `METHOD_VALIDATION_FAILED`. Với `/quantity/2`, request hợp lệ và trả JSON `{"amount":2}`.

### 18.8. Domain 404 và lỗi 500

~~~bash
curl -i http://localhost:8080/api/demo/missing
curl -i http://localhost:8080/api/demo/fault
~~~

404 trả `ITEM_NOT_FOUND`; 500 trả `INTERNAL_ERROR` và `detail` an toàn. Không trả chuỗi `internal connection endpoint: secret-location`.

## 19. Hướng tiếp cận khác: Test-first trước khi viết handler

Một cách học thực tế là viết test contract trước:

1. Đặt tên lỗi chuẩn: `INVALID_BODY`, `VALIDATION_FAILED`, `METHOD_VALIDATION_FAILED`, `ITEM_NOT_FOUND`, `INTERNAL_ERROR`.
2. Định nghĩa HTTP status tương ứng.
3. Chọn `application/problem+json`.
4. Quy định trường chuẩn luôn có trong response.
5. Quy định extension `code` ổn định, `errors` chỉ xuất hiện với field validation.
6. Tạo test status/header/JSONPath.
7. Viết controller, service, advice để test đạt.
8. Thêm test security không lộ raw exception.
9. Tách test tại business service và HTTP layer để lỗi được phát hiện đúng chỗ.

Tránh viết advice rồi snapshot toàn bộ JSON vào một test lớn. Snapshot dễ thất bại khi Jackson thay đổi field order hoặc thông điệp localization; test field-by-field rõ hợp đồng hơn.

## 20. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ assert 204 mà không assert body | Body lỗi có thể lọt qua | `expectBody().isEmpty()` |
| Coi `[]` như body 0 byte | Test không phân biệt collection với no-content | Assert JSON `[]` |
| Coi `Mono.empty()` chắc chắn là HTTP 204 | Contract mơ hồ | Trả `ResponseEntity.noContent()` tường minh |
| Gọi `expectBody(Void.class)` và nghĩ đã assert 0 byte | Có thể chỉ bỏ qua content | Dùng raw-body `isEmpty()` |
| Chỉ assert 400 cho tất cả request sai | Không phát hiện mapping nhầm | Assert ProblemDetail `type/code` |
| Quên `spring-boot-starter-validation` | Constraint có thể không chạy | Thêm validation provider và integration test |
| Quên `@Valid` cho body DTO | Bean Validation không được kích hoạt như dự định | Dùng `@Valid @RequestBody` |
| Thêm `@Validated` vào controller mà không hiểu AOP | Exception loại khác dự kiến | Chọn built-in method validation và test |
| Chỉ handle `WebExchangeBindException` | Bỏ sót method-level constraint | Handle thêm `HandlerMethodValidationException` |
| Trả field error với rejectedValue | Lộ password/token/PII | Chỉ trả code/field/message an toàn |
| Trả `exception.getMessage()` khi 500 | Lộ stack/endpoint/DB | Trả detail chung, log server có kiểm soát |
| HTTP 200 nhưng ProblemDetail status 400 | Monitoring/retry/frontend sai | Đồng bộ HTTP status và body status |
| Không đặt `Content-Type` cho custom problem | Client hiểu nhầm JSON schema | `MediaType.APPLICATION_PROBLEM_JSON` |
| Không phân biệt missing body và validation | Frontend hiển thị field errors sai | `INVALID_BODY` riêng |
| Assert exact field errors message theo locale | Test dễ gãy vì internationalization | Assert code/field, chỉ assert message khi contract quy định |
| Assert thứ tự lỗi không có contract | CI flaky | So sánh tập hợp field errors |
| `onErrorResume(error -> Mono.empty())` | Che validation/DB failure thành thành công rỗng | Map từng loại lỗi |
| Dùng `MockMvc` cho WebFlux mà không xác định stack | Test sai runtime/framework | Dùng `WebTestClient` |
| Chỉ `bindToController` và quên advice | Response problem khác production | Register advice hoặc chạy Boot integration test |
| Chỉ assert JSON body, bỏ HTTP status/header | Hợp đồng chưa được bảo vệ đầy đủ | Assert cả status, media type và body |
| Dùng HTTP 204 nhưng gửi JSON `{}` | Vi phạm semantics no-content | Không gửi response body với 204 |
| Trong unit test mock cả codec/validator | Không kiểm tra request parsing thật | Thêm HTTP integration tests |

## 21. Debug khi test validation/ProblemDetail thất bại

### 21.1. Test mong 400 nhưng nhận 201

Kiểm tra:
- `spring-boot-starter-validation` có trên classpath không?
- Request DTO có đúng `jakarta.validation.Valid` trên controller parameter?
- Constraint import từ `jakarta.validation.constraints` hay một package không được kích hoạt?
- Dữ liệu test có thật sự sai? `@Min(1)` vẫn cho `quantity=1`.
- Có code nào tự `onErrorResume` biến lỗi thành fallback thành công không?
- Controller có đang dùng một DTO khác với DTO đã annotate không?

### 21.2. Test mong `VALIDATION_FAILED` nhưng nhận `INVALID_BODY`

Có thể JSON chưa decode thành DTO: sai cú pháp, sai kiểu JSON, required body vắng. Khi đó `ServerWebInputException` phù hợp hơn `WebExchangeBindException`.

Dùng raw request/response của WebTestClient để xác nhận JSON client đã gửi. Không sửa advice để đổi mọi `ServerWebInputException` thành `VALIDATION_FAILED`, vì làm mất phân biệt nguồn lỗi.

### 21.3. Test mong `HandlerMethodValidationException` nhưng nhận lỗi khác

Kiểm tra:
- Constraint có đặt trực tiếp lên method parameter không?
- Có `@Validated` ở class level làm Spring chọn AOP method validation?
- Có Spring Boot validation starter?
- Path variable parse được sang `int` hay lỗi type conversion trước validation?
- Đang dùng Spring Framework phiên bản nào?

Method validation còn có thể bị ảnh hưởng bởi các cấu hình về exception handling và controller proxy. Cách tốt nhất là test **HTTP contract** sau khi boot context chạy, đồng thời unit/integration test exception type nếu việc phân loại là requirement.

### 21.4. `Content-Type` không phải `application/problem+json`

Kiểm tra:
- Có custom handler trả `Map` hoặc DTO thường và để `application/json` không?
- Có bật `spring.webflux.problemdetails.enabled=true`?
- Advice ưu tiên đã được register chưa?
- Exception có bị bắt bởi một handler khác?
- Request gửi Accept header giới hạn không phù hợp?
- Gateway/ingress có thay response content-type không?

Nếu API công bố ProblemDetail, phải test thực tế media type và không chỉ nhìn JSON fields.

### 21.5. Response 204 không empty như kỳ vọng

Kiểm tra:
- Controller có trả `ResponseEntity.noContent().build()` không?
- Có filter/global error handler tự thêm JSON response body?
- Test có thực sự gọi đúng route?
- Có gateway/error page nào chèn body ngoài WebFlux?
- Có nhầm header output của `curl -i` với response body không?

Với test HTTP, `.expectBody().isEmpty()` là bằng chứng rõ hơn việc chỉ nhìn status 204.

## 22. Checklist cho API production

- [ ] Mỗi endpoint quy định rõ 200, 201, 202, 204, 400, 404, 409, 415, 422 và 5xx khi có ý nghĩa.
- [ ] No-content endpoint trả status tường minh, body thật sự 0 byte.
- [ ] Empty collection trả `[]` theo contract, không biến thành 204 không chủ đích.
- [ ] Required JSON body được kiểm tra khi vắng mặt và khi sai cú pháp.
- [ ] `@Valid` và Jakarta Validation provider được cấu hình.
- [ ] Argument validation và method validation được xử lý riêng.
- [ ] Error code ổn định, không phụ thuộc text thông điệp.
- [ ] Error HTTP status bằng `ProblemDetail.status`.
- [ ] ProblemDetail response có `application/problem+json`.
- [ ] `type` dùng URI namespace được version/document phù hợp.
- [ ] `instance` không làm rò rỉ secret trong query/path.
- [ ] Không trả rejected values, raw exceptions, stack traces hoặc internal URLs.
- [ ] Field `errors` có schema rõ, có thể chứa nhiều lỗi cho một field.
- [ ] Có localization policy nếu client hiển thị message.
- [ ] Custom `@RestControllerAdvice` không che toàn bộ 404/415/500.
- [ ] Có test 400 cho invalid DTO, missing body, malformed JSON, method-level constraint.
- [ ] Có test 201 và Location header, 204 no-body, 200 empty-list.
- [ ] Có test 404 business và 500 sanitized.
- [ ] Có HTTP integration test khởi động actual WebFlux context.
- [ ] Có test service-level Publisher signals nếu logic reactive phức tạp.
- [ ] Có trace/correlation ID server-side để điều tra lỗi mà không leak PII.
- [ ] Có staging smoke test qua ingress/API gateway.
- [ ] Kịch bản test tránh lệ thuộc field order và message localization trừ khi contract quy định.

## 23. Bài tập thực hành

**Bài 1 – 204 vs 200.** Tạo hai endpoint không trả payload, một 204 và một 200. Dùng `expectBody().isEmpty()` cho cả hai và kiểm tra status khác nhau.

**Bài 2 – JSON list.** Trả `Mono.just(List.of())` và kiểm tra body `[]`; chứng minh `isEmpty()` không phù hợp.

**Bài 3 – Validation DTO.** Thêm `@Email` cho `contact`, `@Size` cho `name`; gửi dữ liệu sai, kiểm tra field errors mà không lộ rejectedValue.

**Bài 4 – Missing body.** Gửi POST không có body và kiểm tra `INVALID_BODY`.

**Bài 5 – Malformed JSON.** Gửi JSON sai cú pháp và xác minh API không đánh đồng với Bean Validation.

**Bài 6 – Method validation.** Đặt `@Min(1)` cho path variable, test `/quantity/0` và `/quantity/1` với status khác nhau.

**Bài 7 – ProblemDetail chuẩn.** Kiểm tra `type/title/status/detail/instance` và extension `code` bằng JSONPath.

**Bài 8 – Media type.** Bỏ Content-Type hoặc gửi `text/plain` vào endpoint JSON-only; kiểm tra 415 hoặc behavior theo contract đã chọn.

**Bài 9 – 404 domain.** Tạo domain exception riêng cho item không tồn tại; assert 404 + `ITEM_NOT_FOUND`.

**Bài 10 – Bảo mật.** Cho service ném exception chứa giả lập SQL credentials; test response không chứa chuỗi đó.

**Bài 11 – Localization.** Chạy request với `Accept-Language` khác nhau; test mã lỗi ổn định và thông điệp theo policy được hỗ trợ.

**Bài 12 – Functional endpoints.** Viết một RouterFunction trả `ServerResponse.noContent()` và một handler lỗi ProblemDetail; dùng WebTestClient bind-to-router kiểm tra tương đương annotated controller.

**Bài 13 – StepVerifier.** Ở service, viết Mono empty và Mono.error; kiểm tra tín hiệu riêng trước khi kiểm tra HTTP mapping.

**Bài 14 – Contract regression.** Thay 204 thành 200 trong controller và quan sát test fail; thay code `VALIDATION_FAILED` thành `INVALID_BODY` và quan sát lỗi JSONPath.

**Bài 15 – Staging.** Chạy HTTP tests qua gateway thật, xác nhận 204 giữ 0 byte và ProblemDetail giữ Content-Type.

## 24. Tài liệu tham khảo chính thức

1. Spring Framework – WebTestClient, No Content, JSON body và streaming response: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
2. Spring Framework – WebFlux controller validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
3. Spring Framework – `@RequestBody` và Bean Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
4. Spring Framework – Error Responses/ProblemDetail trong WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
5. Spring Framework – `ProblemDetail` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html
6. Spring Boot 4.0 – WebFlux Problem Details configuration: https://docs.spring.io/spring-boot/4.0/reference/web/reactive.html
7. Spring Boot 4.0.9 – Managed dependency coordinates (WebFlux, Validation, Test): https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
8. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
9. HTTP Semantics – RFC 9110 (204/400/404/415/500): https://www.rfc-editor.org/rfc/rfc9110
10. Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
11. Reactor Test/StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html

**Tự đánh giá cuối:** HTTP 204 khác HTTP 200 với body dài 0 byte ở đâu? `[]` có được xem là body rỗng không? Vì sao `@Valid @RequestBody` có thể ném `WebExchangeBindException` nhưng `@Min` trên path variable lại dùng `HandlerMethodValidationException`? Khi request thiếu body, có field validation result chưa? ProblemDetail `status` và HTTP status có cần trùng không? Test nào bảo vệ dữ liệu nội bộ không bị leak? Nếu bạn trả lời được và chạy được các test trong project, bạn đã kiểm tra chính xác body rỗng, validation và ProblemDetail trong WebFlux.
