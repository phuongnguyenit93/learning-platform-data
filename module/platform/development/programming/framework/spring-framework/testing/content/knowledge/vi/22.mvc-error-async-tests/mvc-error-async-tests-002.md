# Kiểm thử ProblemDetail hoặc cấu trúc lỗi riêng

Trong Spring MVC, một request không hợp lệ hoặc không thể hoàn tất thường kết thúc bằng một HTTP error response. Bài kiểm thử cần xác nhận cả status lẫn cách API mô tả lỗi trong response body. Một API có thể dùng `ProblemDetail` theo định dạng Problem Details for HTTP APIs, hoặc một cấu trúc riêng như `{ code, message, errors }`. Hai cách đều có thể phù hợp; điều quan trọng là response trở thành hợp đồng ổn định mà client có thể dựa vào.

`MockMvc` cho phép gửi request vào luồng xử lý Spring MVC và đọc response mà không cần mở cổng HTTP. Qua đó, test có thể kiểm tra exception được ánh xạ thành đúng status, content type, trường dữ liệu và phần mở rộng. Với request xử lý bất đồng bộ, test còn cần thực hiện bước async dispatch để quan sát response cuối cùng.

## 1. Exception và error response là hai phần khác nhau

Exception mô tả điều gì đã xảy ra bên trong ứng dụng. Error response mô tả điều client cần biết qua HTTP. Không nên để chi tiết exception nội bộ tự động trở thành hợp đồng API.

Ví dụ, service có thể ném `OrderNotFoundException` khi không tìm thấy đơn hàng. API có thể chuyển exception đó thành:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
```

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "instance": "/orders/42",
  "code": "ORDER_NOT_FOUND"
}
```

Client cần biết request thất bại vì tài nguyên không tồn tại và có thể xử lý mã `ORDER_NOT_FOUND`. Client không cần biết exception được ném từ class nào, method nào hoặc stack trace ra sao.

Một test error response thường có bốn câu hỏi:

1. HTTP status có đúng với loại lỗi không?
2. `Content-Type` có đúng định dạng mà API cam kết không?
3. Body có các trường bắt buộc và mã lỗi ổn định không?
4. Body có vô tình tiết lộ thông tin nội bộ hoặc dữ liệu nhạy cảm không?

## 2. ProblemDetail là gì?

`ProblemDetail` là kiểu dữ liệu Spring Framework cung cấp từ Spring Framework 6 để biểu diễn Problem Details for HTTP APIs. Định dạng này bắt nguồn từ RFC 7807 và hiện được mô tả trong RFC 9457. Khi trả một `ProblemDetail` từ Spring MVC, response thường dùng media type `application/problem+json`.

Các thuộc tính chuẩn gồm:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `type` | URI định danh loại vấn đề | `https://api.example.com/problems/order-not-found` |
| `title` | Tên ngắn gọn của loại vấn đề | `Order not found` |
| `status` | HTTP status phù hợp với vấn đề | `404` |
| `detail` | Mô tả cụ thể sự cố của request này | `The requested order does not exist.` |
| `instance` | URI tham chiếu lần xảy ra vấn đề | `/orders/42` |

`type` thường là định danh ổn định cho loại lỗi. Nếu không cung cấp, giá trị mặc định là `about:blank`, có nghĩa vấn đề không có một định danh loại cụ thể ngoài status HTTP. `detail` dành cho thông tin của lần xảy ra cụ thể; không nên dùng nó làm mã để client phân nhánh logic.

Spring cho phép thêm thuộc tính mở rộng thông qua `ProblemDetail.setProperty(...)`. Ví dụ `code`, `errors`, `field` hoặc `traceId` có thể được thêm vào body cùng với các thuộc tính chuẩn. Với Jackson integration của Spring, các thuộc tính mở rộng được serialize như những thuộc tính JSON ở cấp cao nhất của Problem Detail.

## 3. Tạo ProblemDetail trong `@RestControllerAdvice`

`@RestControllerAdvice` áp dụng exception handler cho các controller và ghi response body trực tiếp. Một exception nghiệp vụ có thể được ánh xạ sang Problem Detail như sau:

```java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(
            OrderNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested order does not exist.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return problem;
    }
}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long orderId) {
        super("Order " + orderId + " was not found");
    }
}
```

`ProblemDetail.forStatusAndDetail(...)` khởi tạo body với status và detail. Handler đặt thêm `type`, `title`, `instance` và mã lỗi riêng. Spring MVC sử dụng status của `ProblemDetail` làm status response khi trả trực tiếp đối tượng này.

Trong ví dụ, thông báo exception chứa mã đơn hàng nhưng `detail` công khai không cần lặp lại dữ liệu đó. Nếu API muốn hiển thị mã đơn hàng, có thể thêm thuộc tính được kiểm soát như `orderId`; hãy cân nhắc quyền truy cập và dữ liệu nhạy cảm trước khi đưa vào response.

## 4. Chuẩn hóa lỗi validation bằng ProblemDetail

Khi DTO có `@Valid @RequestBody`, vi phạm Bean Validation thường tạo `MethodArgumentNotValidException`. Advice có thể chuyển các field error thành thuộc tính mở rộng `errors`:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ValidationProblemAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleInvalidRequest(MethodArgumentNotValidException ex) {
        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "code", error.getCode()))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation-error"));
        problem.setTitle("Request validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);

        return problem;
    }
}
```

Đoạn code dùng `URI` nên cần import `java.net.URI` trong file chứa class. `error.getCode()` là mã constraint như `NotBlank`, `Min` hoặc `Size`; client có thể dựa vào mã này thay vì phân tích thông báo tự nhiên phụ thuộc locale.

Nếu nhiều lỗi được trả về, không nên giả định thứ tự field error luôn cố định. Có thể sắp xếp theo field/code trước khi trả response nếu thứ tự là một phần của hợp đồng, hoặc viết test kiểm tra tập lỗi mà không phụ thuộc thứ tự.

Trong ứng dụng Spring MVC, các lỗi bind và validation tiêu chuẩn còn được hỗ trợ qua `ResponseEntityExceptionHandler` và các kiểu `ErrorResponse`. Nếu cần tùy biến nhiều exception chuẩn của MVC, có thể kế thừa `ResponseEntityExceptionHandler` rồi override phương thức xử lý tương ứng. Cách này giúp giữ nguyên các header và status mặc định mà framework đã tính toán. Với một vài exception nghiệp vụ riêng, `@ExceptionHandler` thường gọn hơn.

## 5. Khi nào chọn cấu trúc lỗi riêng?

Một số API đã có schema lỗi từ trước hoặc cần định dạng phù hợp với nhiều loại client. Khi đó, có thể dùng DTO riêng thay vì Problem Detail:

```java
import java.util.List;

record ApiError(
        String code,
        String message,
        int status,
        List<ApiFieldError> errors) {
}

record ApiFieldError(String field, String code) {
}
```

Advice có thể trả schema đó bằng `ResponseEntity`:

```java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class CustomApiErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(OrderNotFoundException ex) {
        ApiError body = new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order does not exist.",
                HttpStatus.NOT_FOUND.value(),
                List.of());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
```

Khi dùng schema riêng, status HTTP và trường `status` trong body phải nhất quán. Nếu API trả lỗi bằng `application/json`, test cần kiểm tra đúng content type đó. Không nên yêu cầu `application/problem+json` cho một response vốn không theo Problem Details.

| Tiêu chí | ProblemDetail | Schema lỗi riêng |
|---|---|---|
| Chuẩn hóa giữa nhiều API | Có các thuộc tính chuẩn theo Problem Details | Do ứng dụng tự định nghĩa |
| Mở rộng field | Có `properties` được serialize thành extension members | Thêm field vào DTO |
| Media type thường dùng | `application/problem+json` | Thường là `application/json` |
| Tích hợp Spring MVC | Được Spring hỗ trợ trực tiếp | Trả qua `ResponseEntity` hoặc object thông thường |
| Tương thích hợp đồng cũ | Có thể cần thay đổi client | Có thể giữ nguyên schema đã công bố |

Điều cần tránh là trộn hai schema tùy tiện giữa các endpoint. Nếu API đã công bố một cấu trúc lỗi, thay đổi sang Problem Detail là thay đổi hợp đồng và cần được xử lý như một thay đổi API có chủ đích.

## 6. Kiểm thử ProblemDetail bằng MockMvc

Giả sử controller ném `OrderNotFoundException` khi service không tìm thấy đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return orderService.find(id);
    }
}
```

Trong `@WebMvcTest`, import advice để nó tham gia MVC slice:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiProblemAdvice.class)
class OrderControllerProblemTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsProblemDetailWhenOrderDoesNotExist() throws Exception {
        when(orderService.find(42L))
                .thenThrow(new OrderNotFoundException(42L));

        mockMvc.perform(get("/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.type").value(
                        "https://api.example.com/problems/order-not-found"))
                .andExpect(jsonPath("$.title").value("Order not found"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail").value(
                        "The requested order does not exist."))
                .andExpect(jsonPath("$.instance").value("/orders/42"))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

Test kiểm tra cả status HTTP lẫn `status` trong body. Hai giá trị phải cùng là `404`. `contentTypeCompatibleWith(...)` phù hợp khi cần kiểm tra media type tương thích mà không khóa vào chi tiết tham số charset.

Nếu controller trả `ProblemDetail` trực tiếp, Spring MVC chọn `application/problem+json` cho response. Gửi `Accept: application/problem+json` trong test làm rõ định dạng mà client yêu cầu. Nếu API hỗ trợ nhiều representation, hãy kiểm tra từng nhánh content negotiation theo hợp đồng đã công bố.

## 7. Kiểm thử thuộc tính mở rộng và validation errors

Với lỗi validation, test nên xác nhận loại problem và các field bị từ chối. Ví dụ:

```java
@Test
void returnsProblemDetailWithFieldErrors() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/validation-error"))
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"));
}
```

Ví dụ này giả định DTO có `@Min(1)` trên `quantity` và advice validation ở phần trước đã được import vào test context. Nếu một request tạo nhiều lỗi, hãy dùng JSONPath filter hoặc deserialize danh sách rồi so sánh theo tập hợp để không phụ thuộc thứ tự.

Các assertion quan trọng thường là:

- HTTP status là `400`.
- `type` nhận diện nhóm lỗi validation.
- `code` là mã ổn định của API.
- `errors` chứa đúng field và constraint bị vi phạm.
- Không có stack trace, exception class hoặc thông tin nội bộ trong body.

## 8. Kiểm thử cấu trúc lỗi riêng

Nếu API dùng `ApiError`, test nên xác nhận đúng schema riêng và content type:

```java
@Test
void returnsCustomErrorEnvelope() throws Exception {
    when(orderService.find(42L))
            .thenThrow(new OrderNotFoundException(42L));

    mockMvc.perform(get("/orders/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value(
                    "The requested order does not exist."))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.errors").isArray());
}
```

Ở đây không kiểm tra `$.type` hay `$.title`, bởi custom envelope không phải Problem Detail. Test xác nhận đúng hợp đồng mà client thực sự nhận.

Nếu custom schema có nhiều field tùy chọn, hãy phân biệt field luôn có mặt với field chỉ xuất hiện trong một số loại lỗi. Có thể dùng `jsonPath(...).doesNotExist()` để xác nhận field nhạy cảm hoặc không thuộc hợp đồng không bị trả ra.

## 9. Kiểm thử exception chuẩn của Spring MVC

Không phải mọi lỗi đều do exception nghiệp vụ tự tạo. Spring MVC có thể phát sinh các exception như:

| Exception | Tình huống thường gặp | Status mặc định thường thấy |
|---|---|---:|
| `MethodArgumentNotValidException` | DTO `@Valid` có field không hợp lệ | `400` |
| `HttpMessageNotReadableException` | Body thiếu, JSON sai cú pháp hoặc không deserialize được | `400` |
| `MethodArgumentTypeMismatchException` | Query/path parameter không chuyển đổi được | `400` |
| `MissingServletRequestParameterException` | Thiếu query parameter bắt buộc | `400` |
| `HttpRequestMethodNotSupportedException` | Gọi HTTP method không được endpoint hỗ trợ | `405` |
| `HttpMediaTypeNotSupportedException` | `Content-Type` không được hỗ trợ | `415` |
| `NoHandlerFoundException` hoặc `NoResourceFoundException` | Không có handler/resource phù hợp, tùy cấu hình và phiên bản | `404` |

Spring Framework cung cấp `ResponseEntityExceptionHandler` để xử lý tập exception MVC chuẩn. Khi ứng dụng cần Problem Detail cho các lỗi framework, có thể kế thừa lớp này hoặc dùng cấu hình Problem Details của Spring Boot. Sau đó dùng MockMvc để xác nhận response của từng trường hợp quan trọng, vì cấu hình exception resolver, advice và phiên bản framework đều ảnh hưởng đến response cuối cùng.

Trong Spring Boot, có thể bật xử lý Problem Details được auto-configure cho các lỗi MVC chuẩn bằng:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

Thiết lập này hỗ trợ các exception MVC mà cơ chế mặc định biết cách xử lý. Nó không tự định nghĩa semantics cho exception nghiệp vụ như `OrderNotFoundException`; ứng dụng vẫn cần handler hoặc cơ chế ánh xạ riêng cho các loại đó. Nếu đã có `@ControllerAdvice` riêng, cần hiểu thứ tự ưu tiên giữa các advice để biết handler nào thực sự xử lý exception.

## 10. Kiểm thử lỗi trong luồng bất đồng bộ

Trong Spring MVC, controller có thể trả `Callable`, `DeferredResult`, `WebAsyncTask` hoặc `CompletableFuture`. Khi xử lý bất đồng bộ, request ban đầu có thể kết thúc bằng trạng thái async trước khi response cuối cùng sẵn sàng.

Nếu tác vụ async hoàn tất bằng exception, Spring thực hiện async dispatch để tiếp tục xử lý qua chuỗi MVC. Exception resolver và `@ExceptionHandler` có thể tạo cùng một Problem Detail hoặc custom envelope như luồng đồng bộ.

Ví dụ controller trả `Callable`:

```java
import java.util.concurrent.Callable;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports/async")
    Callable<String> generateReport() {
        return () -> {
            throw new ReportUnavailableException();
        };
    }
}

class ReportUnavailableException extends RuntimeException {
}
```

Advice ánh xạ exception đó:

```java
@ExceptionHandler(ReportUnavailableException.class)
ProblemDetail handleReportUnavailable() {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "The report service is temporarily unavailable.");
    problem.setType(URI.create(
            "https://api.example.com/problems/report-unavailable"));
    problem.setTitle("Report unavailable");
    problem.setProperty("code", "REPORT_UNAVAILABLE");
    return problem;
}
```

Test cần thực hiện hai bước: xác nhận request đã chuyển sang async, sau đó dispatch kết quả để nhận response cuối:

```java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

@Test
void mapsAsyncFailureToProblemDetail() throws Exception {
    MvcResult asyncResult = mockMvc.perform(get("/reports/async")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(request().asyncStarted())
            .andReturn();

    mockMvc.perform(asyncDispatch(asyncResult))
            .andExpect(status().isServiceUnavailable())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/report-unavailable"))
            .andExpect(jsonPath("$.status").value(503))
            .andExpect(jsonPath("$.code").value("REPORT_UNAVAILABLE"));
}
```

`asyncDispatch(...)` sử dụng kết quả async gắn với `MvcResult` để tiếp tục xử lý response. Nếu tác vụ async phụ thuộc một latch, mock service hoặc callback do test điều khiển, hãy hoàn tất điều kiện đó trước khi dispatch. Không nên kiểm tra body ngay ở lần `perform` đầu tiên vì khi ấy response cuối có thể chưa được tạo.

Với `DeferredResult`, logic tương tự áp dụng khi producer gọi `setErrorResult(exception)`. Với `CompletableFuture`, exception hoàn tất future theo trạng thái exceptional; MockMvc vẫn cần async dispatch để quan sát response. Test cũng nên phân biệt timeout của async request với exception nghiệp vụ: timeout có thể được xử lý qua timeout callback hoặc exception resolver riêng.

## 11. Những lỗi không đi qua `@RestControllerAdvice`

`@RestControllerAdvice` xử lý exception trong luồng xử lý Spring MVC. Một số lỗi xảy ra trước khi request đến `DispatcherServlet` hoặc được xử lý ở filter chain, chẳng hạn:

- Xác thực thất bại trước controller.
- Người dùng đã xác thực nhưng không đủ quyền.
- Rate limiter hoặc filter từ chối request.
- Reverse proxy hoặc servlet container từ chối request trước khi MVC đọc body.

Các lỗi này thường được xử lý bởi thành phần tương ứng như `AuthenticationEntryPoint`, `AccessDeniedHandler`, filter, gateway hoặc container. Không nên kỳ vọng `@ExceptionHandler` trong controller advice tự định dạng tất cả các lỗi đó.

Nếu API yêu cầu cùng một error schema cho cả MVC và Spring Security, hãy cấu hình schema ở cả hai ranh giới và viết test cho từng đường đi. MockMvc có thể kiểm tra security filter chain khi test được cấu hình với Spring Security; test đó cần gửi request qua filter chain thực của test, không chỉ gọi controller trực tiếp.

## 12. Kiểm tra an toàn và tính ổn định của error body

Một error response tốt cần đủ thông tin để client xử lý nhưng không làm lộ nội bộ. Những nội dung sau thường không nên xuất hiện trong response công khai:

- Stack trace đầy đủ hoặc tên class exception nội bộ.
- SQL, câu lệnh truy vấn hoặc thông tin kết nối database.
- Đường dẫn file nội bộ, thư mục triển khai hoặc biến môi trường.
- Token, cookie, authorization header hoặc dữ liệu cá nhân không cần thiết.
- Nội dung exception thô có thể chứa input do người dùng gửi.

Test có thể xác nhận những field nhạy cảm không xuất hiện:

```java
mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.stackTrace").doesNotExist())
        .andExpect(jsonPath("$.exception").doesNotExist())
        .andExpect(jsonPath("$.sql").doesNotExist());
```

Chỉ kiểm tra những field mà ứng dụng có nguy cơ trả ra hoặc schema cần cấm. Không cần liệt kê mọi tên field tưởng tượng trong tất cả test. Quan trọng hơn là không đưa exception hoặc object nội bộ trực tiếp vào body.

Mã lỗi như `ORDER_NOT_FOUND` hoặc `VALIDATION_FAILED` nên ổn định qua các phiên bản. `detail` có thể được điều chỉnh để rõ nghĩa hơn, nhưng client không nên dùng câu văn tự nhiên làm khóa logic. Nếu cần correlation id, hãy thêm một thuộc tính có tên rõ ràng và bảo đảm giá trị đó không phải bí mật.

## 13. Những assertion nên ưu tiên

| Nội dung | Assertion MockMvc | Mục đích |
|---|---|---|
| HTTP status | `status().isNotFound()` | Xác nhận status thực tế |
| Media type Problem Details | `contentTypeCompatibleWith(APPLICATION_PROBLEM_JSON)` | Xác nhận định dạng response |
| Problem type | `jsonPath("$.type").value(...)` | Nhận diện loại vấn đề ổn định |
| Title | `jsonPath("$.title").value(...)` | Xác nhận tên lỗi |
| Status trong body | `jsonPath("$.status").value(404)` | Bảo đảm khớp status HTTP |
| Mã lỗi riêng | `jsonPath("$.code").value(...)` | Cho client phân nhánh theo mã |
| Field validation | `jsonPath("$.errors...")` | Xác nhận lỗi đầu vào cụ thể |
| Field không được phép | `jsonPath("$.stackTrace").doesNotExist()` | Ngăn lộ dữ liệu nội bộ |

Tránh so sánh toàn bộ JSON body bằng một chuỗi dài nếu thứ tự property hoặc danh sách lỗi không phải hợp đồng. Dùng JSONPath để kiểm tra các field có ý nghĩa, hoặc deserialize thành DTO rồi so sánh các giá trị cần thiết.

## 14. Lỗi thường gặp khi kiểm thử error response

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
|---|---|---|
| Chỉ kiểm tra status `400` hoặc `500` | Không xác nhận body mà client sử dụng | Kiểm tra content type, type/code và field quan trọng |
| Kiểm tra `detail` bằng nguyên văn thông báo exception | Gắn test với nội dung nội bộ, locale hoặc phiên bản thư viện | Dùng mã lỗi ổn định và detail công khai có chủ đích |
| Kiểm tra `$.type` trên custom envelope | Schema riêng có thể không có Problem Details fields | Assertion đúng schema thực tế của endpoint |
| Kiểm tra `application/json` cho ProblemDetail | Bỏ qua media type Problem Details | Kiểm tra `application/problem+json` |
| Giả định `@RestControllerAdvice` bắt mọi lỗi | Filter, security và container có ranh giới xử lý riêng | Test đúng filter/entry point/gateway chịu trách nhiệm |
| Đọc body ngay sau async `perform` đầu tiên | Request có thể chưa hoàn tất | Dùng `asyncStarted()` rồi `asyncDispatch(...)` |
| So sánh danh sách validation error theo vị trí cố định | Thứ tự lỗi có thể thay đổi | So sánh theo field/code hoặc chuẩn hóa thứ tự |
| Trả exception message hoặc stack trace cho client | Có thể tiết lộ chi tiết triển khai | Ánh xạ sang thông điệp công khai và mã lỗi ổn định |

## 15. Quy trình kiểm thử một error contract

1. Xác định lỗi đến từ controller/service, MVC binding/validation, async processing hay filter/security.
2. Xác định schema endpoint công bố: Problem Detail hay custom error envelope.
3. Xác nhận exception được ánh xạ tại đúng advice, resolver hoặc filter handler.
4. Dùng MockMvc gửi request gây ra lỗi theo đúng đường xử lý.
5. Kiểm tra HTTP status và content type.
6. Kiểm tra các field bắt buộc, mã lỗi, extension properties và các field nhạy cảm không được xuất hiện.
7. Với validation, xác nhận field/constraint; với async, xác nhận async start và thực hiện async dispatch.
8. Nếu lỗi phát sinh trong security/filter/container, test ở đúng ranh giới đó thay vì chỉ kiểm tra controller advice.
9. Giữ test độc lập với stack trace, thứ tự lỗi không được cam kết và thông báo exception nội bộ.

## 16. Tài liệu tham khảo

- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse và xử lý exception trong Spring MVC.
- [Spring Framework Javadoc — `ProblemDetail`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html): các thuộc tính chuẩn và extension properties.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): gửi request và kiểm tra response.
- [Spring Framework Reference — Testing Asynchronous Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): kiểm thử request MVC bất đồng bộ.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng chuẩn Problem Details.
- [Spring Boot Application Properties — `spring.mvc.problemdetails.enabled`](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): bật xử lý Problem Details được Spring Boot auto-configure.

Kiểm thử error response cần chứng minh client nhận được một hợp đồng rõ ràng khi request thất bại. Dùng `ProblemDetail` khi muốn theo chuẩn Problem Details, dùng DTO riêng khi API đã có schema phù hợp, và luôn kiểm tra status, media type cùng các mã/field công khai. Với xử lý bất đồng bộ, hoàn tất async dispatch trước khi xác nhận body cuối cùng.
