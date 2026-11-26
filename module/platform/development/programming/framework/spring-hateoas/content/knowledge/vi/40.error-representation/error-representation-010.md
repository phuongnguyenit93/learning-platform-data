# Kiểm thử lỗi hypermedia

## Mục tiêu

Sau bài này, bạn có thể kiểm thử error representation của REST API dùng Spring HATEOAS, xác nhận lỗi được trả theo Problem Details với media type phù hợp, kiểm tra sự nhất quán giữa HTTP status và trường `status`, xác nhận các metadata như `type`, `instance`, error code và link trợ giúp, đồng thời bảo đảm lỗi không làm lộ stack trace, dữ liệu cá nhân hoặc thông tin nội bộ.

## 1. Vì sao cần kiểm thử lỗi hypermedia?

Một API hypermedia không chỉ cần representation đúng khi request thành công. Client cũng cần hiểu lỗi để quyết định có thể sửa request, xác thực lại, thử lại sau hay chuyển người dùng đến tài liệu trợ giúp.

Ví dụ client yêu cầu một đơn hàng không tồn tại. API có thể trả Problem Details:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store
Link: <https://api.example.com/problem-types/order-not-found>; rel="describedby"
```

```json
{
  "type": "https://api.example.com/problem-types/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng được yêu cầu.",
  "instance": "/orders/8c6c",
  "code": "ORDER_NOT_FOUND"
}
```

Response này cho client biết loại lỗi, status, chi tiết an toàn và đường dẫn đến tài liệu mô tả lỗi. Nó vẫn là error representation; client không nên giả định mọi response đều là HAL resource thành công.

Kiểm thử lỗi hypermedia giúp bảo vệ các phần của hợp đồng sau:

- HTTP status phản ánh đúng kết quả xử lý.
- Body có cấu trúc ổn định để client phân loại lỗi.
- `Content-Type` chỉ ra đúng định dạng error representation.
- Metadata và extension fields không thay đổi tùy tiện.
- Link trợ giúp hoặc hướng dẫn khôi phục có relation rõ ràng.
- Lỗi không tiết lộ stack trace, SQL, token hoặc thông tin nội bộ.
- Các lỗi phát sinh từ Spring MVC và Spring Security cũng có định dạng nhất quán.

## 2. Problem Details và media type application/problem+json

RFC 9457 định nghĩa Problem Details for HTTP APIs, kế thừa định dạng được giới thiệu trong RFC 7807. JSON representation dùng media type:

```http
Content-Type: application/problem+json
```

Các member chuẩn thường gặp:

| Member | Ý nghĩa | Ví dụ |
|---|---|---|
| `type` | URI định danh loại vấn đề | `https://api.example.com/problem-types/order-not-found` |
| `title` | Tên ngắn, ổn định của loại vấn đề | `Không tìm thấy đơn hàng` |
| `status` | HTTP status gắn với vấn đề | `404` |
| `detail` | Giải thích cụ thể cho lần xảy ra lỗi | `Không tìm thấy đơn hàng được yêu cầu.` |
| `instance` | URI reference nhận diện lần xảy ra lỗi | `/orders/8c6c` |

`type` là định danh quan trọng để client phân loại lỗi. Client có thể xử lý dựa trên URI type đã biết mà không phải phân tích chuỗi `detail`, vốn có thể được bản địa hóa hoặc thay đổi cách diễn đạt.

Nên giữ URI `type` ổn định trong suốt vòng đời hợp đồng và cung cấp tài liệu mô tả loại lỗi tại URI đó. Client có thể dùng URI như một định danh ngay cả khi không truy cập tài liệu được.

`status` trong body là thông tin mô tả status của vấn đề. HTTP status line vẫn là nguồn quyết định status thực tế của response; hai giá trị cần khớp nhau.

`detail` nên giải thích điều client có thể làm tiếp theo. Không dùng trường này để đưa stack trace, câu SQL, tên class nội bộ, đường dẫn máy chủ hoặc nội dung exception chưa được lọc.

`instance` nhận diện lần xảy ra lỗi. Có thể dùng request path hoặc URI có mã định danh sự kiện. Không đưa query string vào `instance` nếu nó có thể chứa token hoặc dữ liệu cá nhân.

## 3. ProblemDetail trong Spring Framework

Từ Spring Framework 6, `org.springframework.http.ProblemDetail` cung cấp mô hình Java cho RFC 9457/7807 Problem Details.

Ví dụ tạo một problem:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy đơn hàng được yêu cầu."
);

problem.setType(URI.create(
        "https://api.example.com/problem-types/order-not-found"
));
problem.setTitle("Không tìm thấy đơn hàng");
String occurrenceId = UUID.randomUUID().toString();
problem.setInstance(URI.create("urn:uuid:" + occurrenceId));
problem.setProperty("code", "ORDER_NOT_FOUND");
problem.setProperty("requestId", occurrenceId);
```

Trong hệ thống thực tế, nên dùng request/correlation ID đã được tạo ở filter hoặc tracing layer và ghi cùng ID vào log. Ví dụ dùng UUID để minh họa một URI nhận diện riêng cho lần xảy ra lỗi. Nếu chỉ dùng request path, nhiều lỗi khác nhau trên cùng tài nguyên có thể có cùng `instance`.

Spring hỗ trợ serialize các member chuẩn của `ProblemDetail`. Các property bổ sung được đặt bằng `setProperty(...)` có thể được serialize như extension members khi Jackson integration của Spring được cấu hình.

Không nên giả định mọi property Java đều tự động trở thành member ở top level. Hãy kiểm tra JSON thực tế trong MockMvc hoặc integration test để bảo đảm `code`, `errors` hay `traceId` được xuất hiện đúng vị trí theo hợp đồng.

Spring cũng cung cấp `ErrorResponse` và `ResponseEntityExceptionHandler` để tích hợp Problem Details vào xử lý lỗi của Spring MVC. Ứng dụng nên chọn một cơ chế nhất quán thay vì để mỗi controller tự tạo body theo cấu trúc riêng.

## 4. Xây dựng error handler tập trung

Dùng `@RestControllerAdvice` để ánh xạ exception nghiệp vụ sang Problem Details giúp các endpoint trả cùng cấu trúc lỗi.

Ví dụ:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng được yêu cầu."
        );

        problem.setType(URI.create(
                "https://api.example.com/problem-types/order-not-found"
        ));
        problem.setTitle("Không tìm thấy đơn hàng");
        String occurrenceId = UUID.randomUUID().toString();
        problem.setInstance(URI.create("urn:uuid:" + occurrenceId));
        problem.setProperty("code", "ORDER_NOT_FOUND");
        problem.setProperty("requestId", occurrenceId);

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .header(
                        HttpHeaders.LINK,
                        "<https://api.example.com/problem-types/order-not-found>; rel=\"describedby\""
                )
                .body(problem);
    }
}
```

Ví dụ giả định `OrderNotFoundException` đã được định nghĩa. Điểm cần chú ý:

- `ProblemDetail` mô tả lỗi bằng các member chuẩn.
- `code` là extension ổn định để client có thể xử lý theo mã.
- `instance` dùng URI nhận diện lần xảy ra lỗi và không chứa query string nhạy cảm.
- HTTP status và `ProblemDetail.status` đều là 404.
- `Cache-Control: no-store` ngăn error response có dữ liệu theo request bị lưu ngoài ý muốn.
- Link `describedby` dẫn đến tài liệu mô tả loại lỗi.

Nếu ứng dụng có nhiều loại lỗi, nên tách việc tạo Problem Details vào factory hoặc helper để chuẩn hóa `type`, `title`, `instance`, error code và cache policy. Tránh sao chép logic này ở nhiều controller.

## 5. Link trong error representation

Problem Details không phải HAL và RFC 9457 không định nghĩa member `_links` như HAL. Vì vậy, response `application/problem+json` không tự động có cấu trúc `_links` chỉ vì ứng dụng đang dùng Spring HATEOAS.

Nếu muốn công bố tài liệu hoặc quan hệ hỗ trợ từ error response, có thể dùng HTTP `Link` header theo Web Linking:

```http
Link: <https://api.example.com/problem-types/order-not-found>; rel="describedby"
```

Relation `describedby` cho biết URI target mô tả tài nguyên hoặc vấn đề hiện tại. Một API cũng có thể định nghĩa extension member riêng như `help` hoặc `errors`, nhưng cần tài liệu hóa schema, kiểu dữ liệu và semantics.

Ví dụ extension có hướng dẫn hỗ trợ:

```json
{
  "type": "https://api.example.com/problem-types/invalid-order",
  "title": "Đơn hàng không hợp lệ",
  "status": 422,
  "detail": "Một hoặc nhiều trường không đáp ứng quy tắc nghiệp vụ.",
  "instance": "/orders",
  "code": "INVALID_ORDER",
  "help": {
    "href": "https://docs.example.com/orders/validation",
    "rel": "help"
  }
}
```

`help` ở đây là extension do API định nghĩa, không phải member chuẩn của Problem Details. Client chỉ có thể dựa vào nó nếu hợp đồng công bố rõ.

Không nên trộn cấu trúc HAL `_links` vào `application/problem+json` mà không định nghĩa rõ media type và extension contract. Nếu API chọn một error representation HAL riêng, hãy công bố media type đó và kiểm thử độc lập.

## 6. Kiểm thử lỗi 404 bằng MockMvc

MockMvc cho phép kiểm tra HTTP status, content type và các member trong body.

Ví dụ:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

@Test
void returnsProblemDetailsWhenOrderDoesNotExist() throws Exception {
    mockMvc.perform(get("/orders/{id}", missingOrderId)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problem-types/order-not-found"))
            .andExpect(jsonPath("$.title")
                    .value("Không tìm thấy đơn hàng"))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.detail")
                    .value("Không tìm thấy đơn hàng được yêu cầu."))
            .andExpect(jsonPath("$.instance").value(
                    org.hamcrest.Matchers.startsWith("urn:uuid:")))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.requestId").exists())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL,
                    org.hamcrest.Matchers.containsString("no-store")
            ));
}
```

Test giả định controller/service ném `OrderNotFoundException` và `ApiExceptionHandler` được đăng ký trong test context. Với `@WebMvcTest`, có thể dùng `@Import(ApiExceptionHandler.class)` nếu advice không được component scan tự động.

Không chỉ assert status 404. Nếu body trả HTML hoặc JSON tự do không có `type` và `status`, client sẽ phải dùng logic khác để hiểu lỗi.

## 7. Kiểm thử link mô tả lỗi

Nếu error response công bố link trợ giúp qua HTTP `Link` header, hãy xác nhận cả URI và relation:

```java
@Test
void exposesProblemDocumentationLink() throws Exception {
    mockMvc.perform(get("/orders/{id}", missingOrderId)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(header().string(
                    HttpHeaders.LINK,
                    org.hamcrest.Matchers.containsString(
                            "rel=\"describedby\""
                    )
            ))
            .andExpect(header().string(
                    HttpHeaders.LINK,
                    org.hamcrest.Matchers.containsString(
                            "/problem-types/order-not-found"
                    )
            ));
}
```

Nếu API dùng extension member thay cho Link header, test phải kiểm tra đúng schema extension. Không kiểm tra một field `help` nếu API chưa cam kết field đó.

Link trợ giúp nên trỏ đến tài liệu ổn định, không chứa token hoặc dữ liệu riêng của request. Với lỗi validation, tài liệu có thể giải thích quy tắc và cách sửa dữ liệu. Với lỗi authorization, không công bố link dẫn đến hành động mà principal không có quyền thực hiện.

## 8. Kiểm thử lỗi validation và extension members

Lỗi validation thường cần trả danh sách trường vi phạm. Không nên đưa giá trị người dùng gửi vào error body một cách mặc định vì dữ liệu đó có thể chứa thông tin cá nhân hoặc bí mật.

Ví dụ handler tạo extension `errors` chỉ chứa field và code:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException exception) {

    List<Map<String, String>> errors =
            exception.getBindingResult().getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", error.getCode() == null
                                    ? "invalid"
                                    : error.getCode()
                    ))
                    .collect(Collectors.toList());

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Một hoặc nhiều trường không hợp lệ."
    );

    problem.setType(URI.create(
            "https://api.example.com/problem-types/validation"
    ));
    problem.setTitle("Dữ liệu không hợp lệ");
    String occurrenceId = UUID.randomUUID().toString();
    problem.setInstance(URI.create("urn:uuid:" + occurrenceId));
    problem.setProperty("code", "VALIDATION_FAILED");
    problem.setProperty("requestId", occurrenceId);
    problem.setProperty("errors", errors);

    return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
}
```

Extension `errors` là hợp đồng riêng của API. Ví dụ này cố ý không đưa `rejectedValue` hoặc thông báo exception thô vào body.

Test có thể xác nhận:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_PROBLEM_JSON)
        .content("""
                {
                  "quantity": -1
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors[0].field").value("quantity"))
    .andExpect(jsonPath("$.errors[0].code").exists());
```

Nếu ứng dụng bật Spring Security CSRF, request POST trong test cần token CSRF hoặc cấu hình test tương ứng. Test validation phải đi qua đúng controller và validator, không chỉ gọi trực tiếp exception handler.

## 9. Kiểm thử sự nhất quán giữa HTTP status và body

Client có thể dựa vào HTTP status để quyết định luồng xử lý trước khi đọc body. Vì vậy, status line và member `status` trong Problem Details phải khớp nhau.

Ví dụ:

| Tình huống | HTTP status | Problem status |
|---|---:|---:|
| Request không hợp lệ | 400 | 400 |
| Chưa xác thực | 401 | 401 |
| Không đủ quyền | 403 | 403 |
| Không tìm thấy tài nguyên | 404 | 404 |
| Xung đột trạng thái | 409 | 409 |
| Không chấp nhận media type request | 415 | 415 |
| Không có representation phù hợp với Accept | 406 | 406 |
| Lỗi hệ thống không dự kiến | 500 | 500 |

Nên có test cho các nhóm lỗi quan trọng, không cần tạo một test riêng cho mọi exception class nếu chúng cùng dùng một mapping đã được kiểm chứng. Tuy nhiên, mỗi loại lỗi công khai nên có `type` và code ổn định nếu client cần phân biệt.

Một assertion tổng quát có thể kiểm tra status:

```java
.andExpect(status().isConflict())
.andExpect(jsonPath("$.status").value(409));
```

Không trả HTTP 200 với body mô tả lỗi chỉ vì muốn đơn giản hóa client. Điều đó làm proxy, monitoring, retry policy và client library hiểu sai kết quả.

## 10. Kiểm thử lỗi xác thực và authorization

Các lỗi bảo mật thường được tạo trước khi request đến controller. Vì vậy, `@RestControllerAdvice` không nhất thiết nhận được mọi lỗi 401 hoặc 403.

Trong Spring Security, cần cấu hình `AuthenticationEntryPoint` cho lỗi chưa xác thực và `AccessDeniedHandler` cho lỗi đã xác thực nhưng không đủ quyền. Nếu API yêu cầu Problem Details nhất quán, hai thành phần này cũng phải serialize error representation theo cùng schema.

Cấu hình khái niệm:

```java
http.exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(problemAuthenticationEntryPoint)
        .accessDeniedHandler(problemAccessDeniedHandler)
);
```

`problemAuthenticationEntryPoint` và `problemAccessDeniedHandler` là các bean do ứng dụng cung cấp. Chúng ghi status, `Content-Type: application/problem+json` và body Problem Details trực tiếp vào `HttpServletResponse`.

Các test nên bao gồm:

- Anonymous request đến endpoint cần đăng nhập trả 401 và Problem Details.
- Principal đã đăng nhập nhưng thiếu authority trả 403 và Problem Details.
- Response 401 phải giữ header `WWW-Authenticate` phù hợp với cơ chế xác thực đang dùng.
- Response không tiết lộ tài nguyên bị cấm hoặc chính sách nội bộ.
- Link hành động bị ẩn trong representation không thay thế authorization tại endpoint.
- Khi API dùng 404 để che giấu sự tồn tại tài nguyên, test phản ánh chính sách concealment thay vì mặc định 403.

Ví dụ test 403 với Spring Security Test:

```java
@Test
@WithMockUser(authorities = "ORDER_READ")
void returnsProblemForForbiddenAction() throws Exception {
    mockMvc.perform(post("/orders/{id}/approve", orderId)
                    .with(csrf())
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.type").exists());
}
```

Test này giả định security filter chain đã cấu hình access denied handler trả Problem Details. `@WithMockUser` và `csrf()` cần dependency `spring-security-test`.

## 11. Kiểm thử lỗi do Spring MVC và content negotiation

Không phải mọi lỗi đều đến từ exception nghiệp vụ. Spring MVC có thể tạo lỗi khi:

- Không tìm thấy handler hoặc tài nguyên.
- HTTP method không được hỗ trợ.
- `Accept` không khớp representation được cung cấp.
- `Content-Type` của request body không được hỗ trợ.
- Body không thể deserialize.
- Validation thất bại.

Nếu API muốn các lỗi này đều có Problem Details, cần kiểm tra cách ứng dụng xử lý các exception framework, thường bằng cách mở rộng `ResponseEntityExceptionHandler` hoặc cấu hình handler phù hợp.

Một số status cần phân biệt:

- 404: không tìm thấy route hoặc tài nguyên, tùy nơi phát sinh.
- 405: method không được hỗ trợ; response nên có `Allow` nếu HTTP semantics yêu cầu.
- 406: server không thể cung cấp representation phù hợp với `Accept`.
- 415: server không chấp nhận media type của request body.
- 400: request body sai cú pháp hoặc dữ liệu không hợp lệ, tùy exception và hợp đồng.

Khi kiểm thử 406, hãy xác định error media type có được client chấp nhận hay không. Nếu request chỉ gửi `Accept: application/hal+json` nhưng server trả `application/problem+json`, API cần có chính sách rõ ràng cho error negotiation. Test nên gửi `Accept` phù hợp với error contract hoặc xác nhận hành vi fallback đã được tài liệu hóa.

Ví dụ test 415:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_PROBLEM_JSON)
        .content("not-json"))
    .andExpect(status().isUnsupportedMediaType())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.status").value(415));
```

Test này chỉ pass nếu ứng dụng đã ánh xạ exception media type không được hỗ trợ thành Problem Details. Nếu đang dùng default error handling, hãy cấu hình handler trước khi yêu cầu hợp đồng này.

## 12. Kiểm thử dữ liệu nhạy cảm không xuất hiện trong lỗi

Error response thường được tạo khi hệ thống gặp tình huống bất thường. Đây là nơi dễ vô tình làm lộ thông tin nội bộ nếu trả trực tiếp `exception.getMessage()`.

Không nên đưa vào response:

- Stack trace hoặc tên class exception nội bộ.
- SQL statement, tên bảng, connection string hoặc chi tiết database.
- Token, cookie, session ID hoặc header `Authorization`.
- Giá trị nhạy cảm người dùng gửi trong request.
- Đường dẫn file hệ thống, hostname nội bộ hoặc địa chỉ IP riêng.
- Quy tắc authorization chi tiết có thể hỗ trợ dò tìm tài nguyên.

Test có thể kiểm tra các field nguy hiểm không tồn tại và detail là thông báo đã kiểm soát:

```java
mockMvc.perform(get("/orders/{id}", missingOrderId)
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isNotFound())
    .andExpect(jsonPath("$.stackTrace").doesNotExist())
    .andExpect(jsonPath("$.exception").doesNotExist())
    .andExpect(jsonPath("$.sql").doesNotExist())
    .andExpect(jsonPath("$.detail")
            .value("Không tìm thấy đơn hàng được yêu cầu."));
```

Nếu response có `traceId` hoặc `requestId`, chỉ công bố mã tương quan không mang bí mật. Client có thể gửi mã đó cho bộ phận hỗ trợ; log nội bộ dùng cùng mã để tìm chi tiết mà không đưa stack trace ra ngoài.

## 13. Kiểm thử lỗi không bị cache ngoài ý muốn

Error representation cũng có thể chứa thông tin phụ thuộc người dùng, trạng thái hoặc request. Vì vậy, hãy xác định chính sách cache cho lỗi.

Với lỗi chứa dữ liệu riêng tư hoặc thông tin hỗ trợ gắn với request, có thể trả:

```http
Cache-Control: no-store
```

Kiểm thử header:

```java
.andExpect(header().string(
        HttpHeaders.CACHE_CONTROL,
        org.hamcrest.Matchers.containsString("no-store")
));
```

Không phải mọi lỗi HTTP đều bắt buộc `no-store`; một số response lỗi công khai, ổn định có thể được cache theo chính sách có chủ đích. Nhưng lỗi authorization, validation có dữ liệu đầu vào hoặc error response được cá nhân hóa cần đánh giá kỹ trước khi cho phép shared cache lưu.

Nếu response khác nhau theo ngôn ngữ hoặc media type, hãy kiểm tra `Vary` phù hợp. `Vary` không thay thế `private` hoặc `no-store` cho nội dung phụ thuộc principal.

## 14. Kiểm thử hợp đồng error type ổn định

Client nên phân loại lỗi theo `type` hoặc error code ổn định, không dựa vào chuỗi `detail`.

Ví dụ cùng loại lỗi có thể có detail tiếng Việt hoặc tiếng Anh:

```json
{
  "type": "https://api.example.com/problem-types/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "code": "ORDER_NOT_FOUND"
}
```

```json
{
  "type": "https://api.example.com/problem-types/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng được yêu cầu.",
  "code": "ORDER_NOT_FOUND"
}
```

Hai response vẫn mô tả cùng problem type. Test hợp đồng nên ưu tiên xác nhận:

- `type` và `code` ổn định.
- HTTP status và body status nhất quán.
- Các extension member có kiểu dữ liệu đúng.
- `title` và `detail` có thể thay đổi theo ngôn ngữ nếu API hỗ trợ localization.
- `instance` nhận diện đúng lần xảy ra lỗi mà không làm lộ query data.

Không nên snapshot toàn bộ body nếu nội dung được bản địa hóa hoặc có instance khác nhau theo request. Dùng assertion theo field và semantics.

## 15. Một bộ test error representation nên có

Bảng dưới đây gợi ý phạm vi kiểm thử cho một API Spring HATEOAS:

| Tình huống | Assertion chính |
|---|---|
| Resource không tồn tại | 404, Problem Details, type và code đúng |
| Validation thất bại | 400, extension `errors` có field/code |
| Trạng thái nghiệp vụ xung đột | 409, detail an toàn |
| Chưa xác thực | 401, Problem Details từ AuthenticationEntryPoint |
| Không đủ quyền | 403 hoặc 404 theo chính sách concealment |
| Media type request không hỗ trợ | 415 và error representation đúng |
| Accept không được hỗ trợ | 406 theo error negotiation contract |
| Method không được hỗ trợ | 405 và `Allow` phù hợp |
| Lỗi hệ thống không dự kiến | 500, không lộ exception nội bộ |
| Link tài liệu lỗi | `Link` header có relation `describedby` |
| Cache policy | `no-store` khi response có dữ liệu nhạy cảm |
| Extension contract | `code`, `errors`, `traceId` có kiểu và semantics ổn định |

Không nhất thiết phải gom mọi tình huống vào một test class. Có thể tách test theo exception advice, security filter chain và content negotiation để xác định lỗi nhanh hơn.

## 16. Những lỗi thường gặp

**Chỉ kiểm tra status code.** Client vẫn có thể nhận HTML hoặc JSON không theo hợp đồng. Kiểm tra media type và các member Problem Details.

**Dùng chuỗi detail làm mã lỗi.** Detail có thể thay đổi hoặc bản địa hóa. Dùng `type` và extension code ổn định.

**Để HTTP status khác body status.** Client và monitoring có thể đưa ra kết luận khác nhau. Assert hai giá trị luôn khớp.

**Đưa stack trace vào detail.** Điều này làm lộ cấu trúc nội bộ. Chỉ trả thông báo đã kiểm soát và mã tương quan.

**Coi Problem Details là HAL.** `application/problem+json` không tự có `_links`. Dùng Link header hoặc extension contract được tài liệu hóa nếu cần điều hướng.

**Cho rằng `@RestControllerAdvice` xử lý mọi lỗi.** Lỗi từ Spring Security filter chain có thể không đi qua controller advice. Cấu hình AuthenticationEntryPoint và AccessDeniedHandler.

**Không kiểm tra lỗi framework.** 406, 415 hoặc 405 có thể có body khác lỗi nghiệp vụ. Chuẩn hóa qua exception handling và test thực tế.

**Trả 200 cho error representation.** Client, proxy và monitoring hiểu sai. Dùng HTTP status phù hợp.

**Trả dữ liệu nhạy cảm trong lỗi validation.** Không echo rejected value hoặc request body một cách mặc định.

**Đưa query string vào `instance`.** URI có thể chứa token hoặc thông tin riêng tư. Chỉ dùng path hoặc mã sự kiện an toàn.

**Thêm extension không có tài liệu.** Client không biết schema hoặc semantics. Công bố rõ tên, kiểu và khả năng tương thích của extension.

## 17. Nguyên tắc thiết kế

- Dùng Problem Details với `application/problem+json` cho error representation nếu đó là hợp đồng API.
- Dùng `type` và error code ổn định để client phân loại lỗi.
- Giữ HTTP status và member `status` trong body nhất quán.
- Dùng `detail` an toàn, hướng đến hành động của client.
- Dùng `instance` để nhận diện lỗi mà không đưa query string nhạy cảm vào response.
- Dùng Link header `describedby` hoặc extension được tài liệu hóa cho tài liệu hỗ trợ.
- Không giả định Problem Details tự động là HAL hoặc có `_links`.
- Chuẩn hóa lỗi nghiệp vụ, validation, security và lỗi framework.
- Kiểm tra 401/403 ở Security filter chain riêng.
- Không trả stack trace, SQL, token, cookie hoặc dữ liệu nội bộ.
- Xác định cache policy cho error response.
- Dùng MockMvc và integration test để xác nhận cả status, body, media type, headers và thông tin nhạy cảm.

## Kết luận

Kiểm thử lỗi hypermedia bảo đảm client có thể hiểu và xử lý lỗi theo một hợp đồng ổn định. Problem Details cung cấp cấu trúc chuẩn cho loại vấn đề, status, detail và instance; Spring Framework hỗ trợ mô hình `ProblemDetail` cùng cơ chế xử lý exception. Nếu cần điều hướng đến tài liệu lỗi, API có thể công bố Link header `describedby` hoặc extension đã tài liệu hóa. Với Spring HATEOAS, cần phân biệt error representation `application/problem+json` với HAL resource thành công. MockMvc và integration test phải xác nhận status, media type, body, link hỗ trợ, lỗi từ Spring Security và việc không rò rỉ dữ liệu nội bộ.

## Tài liệu tham khảo

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [Spring Framework Reference – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework API – ProblemDetail](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework API – ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Security Reference – Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

