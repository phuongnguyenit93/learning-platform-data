# ControllerAdvice và ánh xạ ngoại lệ thành HTTP

Trong Spring MVC, lỗi có thể phát sinh khi controller xử lý nghiệp vụ, khi Spring bind dữ liệu request hoặc khi message converter đọc request body. Nếu mỗi controller tự viết một khối `try/catch` để đổi lỗi thành HTTP response, cách xử lý dễ bị lặp và không nhất quán. Spring cung cấp `@ExceptionHandler`, `@ControllerAdvice` và `@RestControllerAdvice` để tập trung hóa việc chuyển ngoại lệ thành phản hồi HTTP.

Khi kiểm thử, ta cần xác nhận cả hai phần: ngoại lệ nào được xử lý và response nào được gửi về client. Một test tốt kiểm tra HTTP status, response body, content type và header liên quan; chỉ xác nhận controller ném đúng exception chưa chứng minh API đã trả về đúng hợp đồng lỗi.

## 1. Vì sao cần ánh xạ ngoại lệ thành HTTP response?

Một exception Java mô tả lỗi trong chương trình. HTTP response là cách ứng dụng biểu diễn lỗi đó cho client. Hai khái niệm có liên quan nhưng không đồng nhất.

Ví dụ, khi tìm một đơn hàng không tồn tại, service có thể ném `OrderNotFoundException`. API thường chuyển lỗi này thành HTTP `404 Not Found` cùng thông tin đủ để client hiểu tài nguyên nào không được tìm thấy. Khi dữ liệu gửi lên không hợp lệ, API thường trả `400 Bad Request`. Khi trạng thái hiện tại của tài nguyên xung đột với thao tác, có thể dùng `409 Conflict`.

| Tình huống | HTTP status thường dùng | Ý nghĩa với client |
|---|---:|---|
| Tài nguyên không tồn tại | `404 Not Found` | Địa chỉ hoặc định danh không trỏ đến tài nguyên có thể tìm thấy |
| Request sai định dạng hoặc dữ liệu không hợp lệ | `400 Bad Request` | Client cần sửa request |
| Chưa xác thực | `401 Unauthorized` | Client cần cung cấp thông tin xác thực hợp lệ |
| Không có quyền thực hiện | `403 Forbidden` | Danh tính hiện tại không được phép thực hiện thao tác |
| Trạng thái tài nguyên xung đột | `409 Conflict` | Client cần giải quyết xung đột trước khi thử lại |
| Lỗi ngoài dự kiến phía server | `500 Internal Server Error` | Server không thể hoàn tất request |

Status phải phản ánh đúng nguyên nhân và hợp đồng API. Không nên chuyển mọi exception thành `400`, vì lỗi nghiệp vụ hoặc lỗi nội bộ phía server không nhất thiết do client gửi request sai.

## 2. Xử lý ngoại lệ ngay trong controller

`@ExceptionHandler` có thể được đặt trong controller. Phương thức được đánh dấu sẽ xử lý loại exception tương ứng phát sinh từ các handler method trong controller đó.

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(@PathVariable String orderId) {
        if ("missing".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderView(orderId, "CREATED");
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}

record OrderView(String orderId, String status) {
}

record ApiError(String code, String message) {
}

class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    String getOrderId() {
        return orderId;
    }
}
```

`ResponseEntity` cho phép phương thức handler chỉ định status, headers và body. Cách này phù hợp khi ngoại lệ chỉ có ý nghĩa trong một controller hoặc khi cách phản hồi thực sự đặc thù cho controller đó.

Khi nhiều controller cần cùng một quy tắc xử lý, nên đưa handler ra một advice thay vì sao chép phương thức này vào từng controller.

## 3. Tập trung xử lý bằng @ControllerAdvice

`@ControllerAdvice` là một component có thể cung cấp các phương thức xử lý ngoại lệ dùng chung cho nhiều controller. Nó cũng hỗ trợ các khả năng chung khác của controller như `@InitBinder` và `@ModelAttribute`, nhưng trong bài học này ta tập trung vào exception handling.

Ví dụ, chuyển handler của `OrderController` sang một lớp riêng:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
```

Với controller trả về view, `@ControllerAdvice` có thể trả về `ModelAndView` hoặc giá trị phù hợp với cơ chế xử lý view. Nếu API cần trả dữ liệu trong response body, có thể dùng `@ResponseBody` trên phương thức handler hoặc dùng `@RestControllerAdvice`.

`@RestControllerAdvice` kết hợp vai trò của `@ControllerAdvice` và `@ResponseBody`. Do đó, đối tượng được trả về từ exception handler được ghi vào response body thông qua các `HttpMessageConverter`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ApiError handleOrderNotFound(OrderNotFoundException exception) {
        return new ApiError(
            "ORDER_NOT_FOUND",
            "Order " + exception.getOrderId() + " was not found"
        );
    }
}
```

Hai cách trên đều có thể tạo response `404`. `ResponseEntity` phù hợp khi cần quyết định status và header động trong phương thức; `@ResponseStatus` phù hợp khi status cố định cho handler.

## 4. Dùng ProblemDetail cho định dạng lỗi chuẩn

Spring Framework 6 hỗ trợ `ProblemDetail` để biểu diễn lỗi HTTP theo định dạng Problem Details for HTTP APIs (RFC 7807). Đây là lựa chọn hữu ích khi muốn response lỗi có cấu trúc nhất quán giữa các endpoint.

Các thuộc tính chuẩn thường dùng gồm:

- `type`: URI xác định loại vấn đề; giá trị mặc định là `about:blank`.
- `title`: mô tả ngắn loại vấn đề.
- `status`: HTTP status.
- `detail`: giải thích cụ thể cho lần lỗi hiện tại.
- `instance`: URI xác định request hoặc lần xảy ra lỗi.

Có thể thêm các thuộc tính mở rộng cho mã lỗi hoặc dữ liệu nghiệp vụ cần thiết:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Order " + exception.getOrderId() + " was not found"
        );
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }
}
```

Khi Spring MVC ghi `ProblemDetail` ra response, nội dung được tuần tự hóa theo định dạng problem details và sử dụng media type phù hợp, thường là `application/problem+json` cho JSON. Test nên dùng `contentTypeCompatibleWith(...)` để kiểm tra media type mà không phụ thuộc vào các tham số phụ nếu có.

Không đưa stack trace, SQL, tên bảng, token, mật khẩu hoặc thông tin nội bộ nhạy cảm vào `detail`. Chi tiết kỹ thuật phục vụ điều tra nên được ghi ở server log cùng correlation ID; response công khai chỉ nên chứa thông tin client cần để xử lý lỗi.

## 5. Các cách ánh xạ ngoại lệ khác

Ngoài `@ControllerAdvice`, Spring MVC còn có một số cách phổ biến để biểu diễn status.

### @ResponseStatus trên exception

Có thể gắn `@ResponseStatus` trực tiếp lên một loại exception:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
    }
}
```

Khi exception này thoát khỏi controller, Spring có thể ánh xạ nó thành status `404`. Cách này đơn giản cho lỗi có status cố định, nhưng ít linh hoạt hơn advice khi cần một response body thống nhất hoặc cần bổ sung headers và dữ liệu lỗi.

### ResponseStatusException

Khi cần chỉ định status tại nơi phát sinh lỗi, có thể dùng `ResponseStatusException`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

throw new ResponseStatusException(
    HttpStatus.CONFLICT,
    "Order cannot be cancelled in its current state"
);
```

Cách này có thể phù hợp cho một nhánh xử lý nhỏ. Nếu API có định dạng lỗi công khai thống nhất, hãy cân nhắc xử lý `ResponseStatusException` trong advice hoặc dùng một kiểu exception nghiệp vụ riêng để tránh mỗi controller trả lỗi theo một cấu trúc khác nhau.

### Xử lý lỗi mặc định của Spring MVC

Spring MVC đã có các exception resolver để xử lý những lỗi framework và lỗi có status được khai báo. Các lỗi như method không được hỗ trợ, media type không tương thích hoặc request body không đọc được có thể được xử lý bởi cơ chế mặc định của Spring MVC. Nếu cần thay đổi response mặc định, có thể dùng `@ExceptionHandler` trong advice hoặc mở rộng `ResponseEntityExceptionHandler` để tùy chỉnh cách xử lý nhiều exception MVC chuẩn.

Không nên tạo handler tổng quát một cách vội vàng rồi vô tình thay đổi hành vi mặc định của framework. Hãy xác định rõ loại exception cần chuẩn hóa và test status/body tương ứng.

## 6. Phạm vi áp dụng và thứ tự của advice

Theo mặc định, `@ControllerAdvice` có thể áp dụng cho các controller được phát hiện trong ứng dụng. Có thể giới hạn phạm vi bằng các selector như `basePackages`, `basePackageClasses`, `annotations` hoặc `assignableTypes`.

Ví dụ, chỉ áp dụng advice cho controller trong package API:

```java
@RestControllerAdvice(basePackages = "com.example.api")
class ApiExceptionHandler {
    // Các @ExceptionHandler dùng chung cho API.
}
```

Nếu có nhiều advice cùng xử lý exception, thứ tự của chúng ảnh hưởng đến handler được chọn. Có thể chỉ định thứ tự bằng `Ordered`, `@Order` hoặc `@Priority`. Advice có độ ưu tiên cao hơn được xét trước. Trong cùng một advice, Spring ưu tiên exception match trực tiếp ở root hơn match qua cause; giữa các advice khác nhau, một advice có độ ưu tiên cao hơn có thể thắng dù nó match một cause exception.

Vì vậy, khi hai handler có thể cùng nhận một lỗi, hãy kiểm tra cả thứ tự advice và loại exception thực tế được ném ra. Tránh nhiều advice có phạm vi rộng cùng bắt `Exception.class`, vì rất khó dự đoán handler nào chịu trách nhiệm và có thể che mất cách xử lý lỗi cụ thể.

## 7. Kiểm thử ánh xạ ngoại lệ bằng MockMvc

Khi test exception mapping, hãy gửi request thật qua Spring MVC bằng `MockMvc`. Không gọi trực tiếp phương thức handler để thay thế, vì cách gọi trực tiếp bỏ qua `DispatcherServlet`, exception resolver và quy trình ghi response.

Ví dụ controller và exception:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(@PathVariable String orderId) {
        if ("missing".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderView(orderId, "CREATED");
    }
}

record OrderView(String orderId, String status) {
}

class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    String getOrderId() {
        return orderId;
    }
}
```

Advice dùng `ProblemDetail`:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Order " + exception.getOrderId() + " was not found"
        );
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }
}
```

Với Spring Boot, có thể dùng `@WebMvcTest` để nạp slice MVC và import advice cần kiểm tra:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerExceptionTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void mapsMissingOrderToProblemDetailNotFound() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.title").value("Order not found"))
            .andExpect(jsonPath("$.detail")
                .value("Order missing was not found"))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

Test trên kiểm tra toàn bộ đường đi của lỗi: request đến controller, controller ném `OrderNotFoundException`, advice bắt exception, Spring tạo response và `MockMvc` quan sát HTTP result. Các assertion kiểm tra:

- Status thực tế là `404`.
- Response có media type tương thích với `application/problem+json`.
- Các trường `status`, `title`, `detail` và thuộc tính mở rộng `code` đúng với hợp đồng API.

Nếu dự án dùng `@WebMvcTest`, hãy bảo đảm advice được đưa vào test context. Có thể dùng `@Import` như ví dụ hoặc cấu hình test slice để phát hiện component advice cần thiết. Nếu dùng `@SpringBootTest` với `@AutoConfigureMockMvc`, ứng dụng thường nạp cấu hình rộng hơn và advice được component scan như khi chạy ứng dụng.

## 8. Kiểm thử các lỗi request do Spring MVC tạo ra

Không phải mọi lỗi đều do code trong controller chủ động ném. Spring MVC có thể phát hiện lỗi trước khi gọi phương thức controller, chẳng hạn:

- Request body không đọc được hoặc JSON sai cú pháp: thường liên quan `HttpMessageNotReadableException`.
- Dữ liệu không vượt qua validation của `@Valid`: thường liên quan `MethodArgumentNotValidException`.
- Không có handler phù hợp với HTTP method: có thể dẫn đến `405 Method Not Allowed`.
- Media type request không được hỗ trợ: có thể dẫn đến `415 Unsupported Media Type`.
- Media type response không được chấp nhận: có thể dẫn đến `406 Not Acceptable`.

Ví dụ test validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/customers")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        return ResponseEntity.status(201).build();
    }
}

record CreateCustomerRequest(@NotBlank String name) {
}
```

Khi kiểm tra lỗi validation, gửi JSON hợp lệ về cú pháp nhưng vi phạm constraint, sau đó xác nhận response lỗi:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"name":"   "}
            """))
    .andExpect(status().isBadRequest());
```

Nếu advice tùy chỉnh response validation, hãy kiểm tra thêm cấu trúc lỗi và nội dung field error. Một request JSON sai cú pháp kiểm tra một nhánh khác với JSON đúng cú pháp nhưng vi phạm `@NotBlank`; nên có test riêng nếu API cam kết xử lý hai trường hợp khác nhau.

## 9. Những lỗi thường gặp khi viết test exception handler

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Request trả status mặc định thay vì status tùy chỉnh | Advice chưa được nạp, package scan không tìm thấy advice hoặc exception không khớp handler |
| `@ExceptionHandler` không được gọi | Exception xảy ra ngoài request MVC, handler method không nằm trong phạm vi controller/advice hoặc exception thực tế khác dự kiến |
| Handler đúng nhưng body rỗng | `@ControllerAdvice` trả object mà không có `@ResponseBody` hoặc response không được tạo theo cách mong muốn |
| Test slice không thấy advice | `@WebMvcTest` không đưa advice cụ thể vào context test; kiểm tra component scan hoặc `@Import` |
| Status đúng nhưng body sai | Assertion mới chỉ kiểm tra status; kiểm tra serializer, field name, content type và dữ liệu handler trả về |
| Handler tổng quát che mất lỗi cụ thể | Có nhiều advice hoặc handler cùng match; kiểm tra `@Order`, phạm vi advice và kiểu exception |
| Response để lộ thông tin nội bộ | Handler đang trả nguyên exception message hoặc stack trace; chỉ công khai thông tin cần thiết cho client |

Một lỗi quan trọng khác là test gọi trực tiếp `handleOrderNotFound(...)`. Cách đó chỉ kiểm tra Java method và không kiểm tra cơ chế ánh xạ exception của Spring MVC. Để xác nhận API behavior, hãy phát sinh exception trong một request MockMvc và kiểm tra response nhận được.

## 10. Quy trình thiết kế và kiểm thử ánh xạ lỗi

1. Xác định loại lỗi và HTTP status phù hợp với hợp đồng API.
2. Chọn nơi xử lý: `@ExceptionHandler` trong controller cho lỗi cục bộ, hoặc `@ControllerAdvice` / `@RestControllerAdvice` cho quy tắc dùng chung.
3. Chọn cấu trúc response: `ResponseEntity`, `@ResponseStatus`, hoặc `ProblemDetail`.
4. Giữ response công khai ổn định và tránh đưa thông tin nội bộ nhạy cảm vào body.
5. Tạo test MVC với `MockMvc`, bảo đảm controller và advice đều có mặt trong test context.
6. Gửi request làm phát sinh exception và kiểm tra status, content type, body cùng header cần thiết.
7. Bổ sung test cho các lỗi do Spring MVC tạo ra như JSON sai cú pháp hoặc validation thất bại nếu API có tùy chỉnh chúng.

`@ExceptionHandler` xác định cách xử lý một loại exception; `@ControllerAdvice` đưa quy tắc đó ra phạm vi nhiều controller; `@RestControllerAdvice` trả kết quả qua response body. Khi kiểm thử bằng `MockMvc`, ta xác nhận được toàn bộ hợp đồng HTTP mà client nhìn thấy, thay vì chỉ xác nhận một phương thức Java đã chạy.
