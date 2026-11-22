# Kiểm thử HTTP thành công, validation và ánh xạ lỗi

Một API HTTP tốt cần được kiểm thử ở cả hai phía của hợp đồng: request hợp lệ phải tạo ra response thành công với status, header và body chính xác; request không hợp lệ phải bị từ chối trước khi nghiệp vụ chạy và được ánh xạ thành error response nhất quán. Với Spring MVC, `MockMvc` cho phép kiểm tra toàn bộ luồng xử lý request trong MVC mà không cần mở HTTP server thật.

Bài thực hành này xây dựng một endpoint tạo và tra cứu đơn hàng. Ta sẽ kết hợp `@Valid`, Jakarta Bean Validation, `@RestControllerAdvice`, `ProblemDetail` và `MockMvc` để kiểm tra:

- Request hợp lệ và response `201 Created`.
- Trường bắt buộc bị thiếu hoặc giá trị vượt giới hạn.
- JSON sai cú pháp hoặc không chuyển đổi được kiểu.
- Path variable sai kiểu.
- Lỗi nghiệp vụ như đơn hàng không tồn tại hoặc mã sản phẩm bị trùng.
- Việc service không được gọi khi request bị từ chối ở bước bind/validation.

## 1. Hiểu các bước xử lý một request

Spring MVC xử lý request qua nhiều bước. Xác định đúng bước phát sinh lỗi giúp chọn đúng exception handler và viết assertion phù hợp.

```text
HTTP request
    |
    v
Mapping: path, HTTP method, consumes, produces
    |
    v
Đọc body / chuyển đổi path variable và query parameter
    |
    v
Bind dữ liệu vào DTO hoặc tham số controller
    |
    v
Bean Validation qua @Valid / @Validated
    |
    v
Controller gọi service nghiệp vụ
    |
    v
Tạo response thành công
    |
    +---- exception ở bất kỳ bước nào ----+
                                          |
                                          v
                               Exception resolver / advice
                                          |
                                          v
                               HTTP error response
```

Các loại lỗi thường gặp không cùng một nguồn:

| Request hoặc tình huống | Bước phát hiện | Exception thường gặp | Status thường dùng |
|---|---|---|---:|
| Thiếu toàn bộ body bắt buộc | Đọc body | `HttpMessageNotReadableException` | 400 |
| JSON sai cú pháp | Deserialize body | `HttpMessageNotReadableException` | 400 |
| JSON có giá trị sai kiểu | Deserialize body | `HttpMessageNotReadableException` | 400 |
| DTO thiếu field hoặc vi phạm constraint | Bean Validation | `MethodArgumentNotValidException` | 400 |
| Path/query parameter không chuyển đổi được | Argument conversion | `MethodArgumentTypeMismatchException` | 400 |
| Không tìm thấy đơn hàng | Nghiệp vụ | `OrderNotFoundException` | 404 |
| Mã đơn hàng hoặc mã sản phẩm bị trùng | Nghiệp vụ | `DuplicateOrderException` | 409 |
| Gửi media type không được hỗ trợ | Request mapping/converter | `HttpMediaTypeNotSupportedException` | 415 |

Status là một phần của hợp đồng HTTP. Body lỗi bổ sung thông tin để client hiểu loại lỗi và xử lý phù hợp. Không nên trả cùng một status cho mọi trường hợp chỉ vì tất cả đều làm request thất bại.

## 2. Chuẩn bị dependency validation

Với Spring Boot, cần có implementation Jakarta Bean Validation trên classpath. Thông thường thêm starter sau:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu không có validation provider, các annotation như `@NotBlank`, `@Min` hoặc `@Size` có thể không được thực thi. Chỉ thêm annotation vào DTO không tự cung cấp implementation validation.

Các ví dụ dùng `jakarta.validation.*`, phù hợp với Spring Framework 6 và Spring Boot 3 trở lên. Dự án Spring cũ dùng `javax.validation.*` và cần điều chỉnh package theo phiên bản.

## 3. Định nghĩa DTO và quy tắc đầu vào

Giả sử API tạo đơn hàng nhận mã sản phẩm và số lượng. Ta dùng `Integer` thay vì `int` cho trường bắt buộc để phân biệt trường bị thiếu với giá trị số 0.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 20)
        String productCode,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

Các constraint có ý nghĩa riêng:

| Constraint | Quy tắc |
|---|---|
| `@NotNull` | Giá trị phải khác `null` |
| `@NotBlank` | Chuỗi không null, không rỗng và không chỉ chứa khoảng trắng |
| `@Size(max = 20)` | Chuỗi có tối đa 20 ký tự |
| `@Min(1)` | Số lượng tối thiểu là 1, bao gồm 1 |
| `@Max(100)` | Số lượng tối đa là 100, bao gồm 100 |

Nếu dùng primitive `int`, field JSON bị thiếu có thể trở thành giá trị mặc định `0`. Khi đó `@NotNull` không thể phát hiện việc client không gửi field. Wrapper `Integer` cho phép DTO giữ `null`, để validation xác định trường bắt buộc chưa được cung cấp.

Ta định nghĩa response độc lập với DTO request:

```java
import java.util.UUID;

public record OrderResponse(
        UUID id,
        String productCode,
        int quantity,
        String status
) {
}
```

Tách request và response giúp API kiểm soát chính xác dữ liệu client được gửi và dữ liệu server công bố. Ví dụ, client không được tự gửi `status` hoặc `id` nếu đó là dữ liệu do hệ thống quản lý.

## 4. Định nghĩa service và controller

Service là ranh giới nghiệp vụ mà controller gọi sau khi request đã được bind và validate:

```java
import java.util.UUID;

public interface OrderApplicationService {
    OrderResponse create(CreateOrderRequest request);

    OrderResponse findById(UUID id);
}
```

Controller khai báo hai endpoint. `POST /api/orders` tạo đơn hàng và trả `201 Created` cùng `Location` header. `GET /api/orders/{id}` tra cứu đơn hàng bằng UUID.

```java
import java.net.URI;
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderApplicationService orderService;

    OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderResponse created = orderService.create(request);
        URI location = URI.create("/api/orders/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        return orderService.findById(id);
    }
}
```

`@RequestBody` yêu cầu Spring đọc body thành `CreateOrderRequest`. `@Valid` kích hoạt Bean Validation sau khi deserialize thành công. Nếu validation thất bại, Spring xử lý exception trước khi gọi `orderService.create(...)`.

`consumes = application/json` ràng buộc định dạng body của endpoint POST. Nếu client gửi media type không được hỗ trợ, Spring có thể trả `415 Unsupported Media Type` trước khi gọi controller.

## 5. Định nghĩa exception nghiệp vụ

Các exception nghiệp vụ biểu diễn kết quả mà controller cần chuyển thành status HTTP:

```java
import java.util.UUID;

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(UUID id) {
        super("Order " + id + " was not found");
    }
}

class DuplicateOrderException extends RuntimeException {
    DuplicateOrderException(String productCode) {
        super("An order already exists for product " + productCode);
    }
}
```

Exception có thể chứa chi tiết hữu ích cho log hoặc xử lý nội bộ. Không nhất thiết phải đưa nguyên văn `getMessage()` ra client. Error response công khai nên dùng mã ổn định và thông điệp đã được kiểm soát.

## 6. Ánh xạ lỗi bằng ProblemDetail

Spring Framework 6 trở lên cung cấp `ProblemDetail` để biểu diễn Problem Details for HTTP APIs. Spring MVC serialize đối tượng này thành response theo media type `application/problem+json`.

Các thuộc tính chuẩn:

| Field | Ý nghĩa |
|---|---|
| `type` | URI định danh loại vấn đề |
| `title` | Tên ngắn của loại vấn đề |
| `status` | HTTP status tương ứng |
| `detail` | Mô tả cụ thể của lần lỗi này |
| `instance` | URI tham chiếu request gây ra vấn đề |

Có thể bổ sung field riêng như `code` hoặc `errors` bằng `setProperty(...)`. Các thuộc tính mở rộng được serialize ở cấp cao nhất của JSON.

Tạo một `@RestControllerAdvice` để gom cách xử lý lỗi:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleValidation(MethodArgumentNotValidException ex) {
        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "constraint", error.getCode()))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");
        problem.setType(URI.create(
                "https://api.example.test/problems/validation-error"));
        problem.setTitle("Request validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);
        return problem;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail handleUnreadableBody(HttpMessageNotReadableException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "The request body is missing or cannot be read.");
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-request-body"));
        problem.setTitle("Invalid request body");
        problem.setProperty("code", "INVALID_REQUEST_BODY");
        return problem;
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ProblemDetail handleInvalidParameter(MethodArgumentTypeMismatchException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "A request parameter has an invalid value.");
        problem.setType(URI.create(
                "https://api.example.test/problems/invalid-parameter"));
        problem.setTitle("Invalid request parameter");
        problem.setProperty("code", "INVALID_PARAMETER");
        return problem;
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested order does not exist.");
        problem.setType(URI.create(
                "https://api.example.test/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(DuplicateOrderException.class)
    ProblemDetail handleDuplicateOrder(DuplicateOrderException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "An order with the supplied product code already exists.");
        problem.setType(URI.create(
                "https://api.example.test/problems/duplicate-order"));
        problem.setTitle("Duplicate order");
        problem.setProperty("code", "DUPLICATE_ORDER");
        return problem;
    }
}
```

Các handler trên giữ response body ổn định. Client có thể dựa vào `code` hoặc `type` để phân nhánh; không cần phân tích exception message. Handler validation trả thêm danh sách `errors`, mỗi phần tử có tên field và mã constraint.

`error.getCode()` thường là mã như `NotBlank`, `NotNull`, `Min`, `Max` hoặc `Size`. Nếu API cần mã lỗi nghiệp vụ ổn định qua nhiều phiên bản validation provider, có thể ánh xạ các constraint này sang mã do ứng dụng tự định nghĩa.

Trong ví dụ, import `MissingServletRequestParameterException` chưa được dùng và có thể bỏ khỏi file thực tế; phần handler chỉ xử lý `MethodArgumentTypeMismatchException`. Nếu API có query parameter bắt buộc, có thể thêm handler riêng cho exception thiếu parameter.

## 7. Thiết lập MockMvc test slice

`@WebMvcTest` tạo một MVC slice thay vì toàn bộ ứng dụng. Ta import exception advice và thay service bằng Mockito mock trong Spring context.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerHttpTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderApplicationService orderService;
}
```

`@MockitoBean` có trong Spring Framework 6.2 trở lên. Với Spring Boot 3.4 trở lên, đây là lựa chọn hiện đại thay cho `@MockBean` cũ. Nếu dự án dùng Spring Boot cũ hơn chưa có Spring Framework 6.2, thay import và annotation bằng `org.springframework.boot.test.mock.mockito.MockBean`.

`@Import(ApiExceptionHandler.class)` bảo đảm advice tham gia vào MVC slice. Nếu bỏ import và advice không được nạp bởi test configuration, request lỗi có thể đi qua handler mặc định thay vì schema mà API mong muốn.

## 8. Kiểm thử request thành công

Test thành công cần kiểm tra nhiều phần của hợp đồng:

- HTTP status là `201 Created`.
- `Location` header trỏ tới resource vừa tạo.
- Response có media type JSON.
- Body có đúng `id`, `productCode`, `quantity` và `status`.
- Service được gọi đúng một lần với request đã bind.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void createsOrderAndReturnsResourceLocation() throws Exception {
    UUID id = UUID.fromString("d2b6d39e-7df4-4e2e-8fd3-40c11a2d79c0");
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);
    OrderResponse response = new OrderResponse(
            id, "BOOK-01", 2, "CREATED");

    when(orderService.create(request)).thenReturn(response);

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 2
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "Location", "/api/orders/" + id))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$.productCode").value("BOOK-01"))
            .andExpect(jsonPath("$.quantity").value(2))
            .andExpect(jsonPath("$.status").value("CREATED"));

    verify(orderService).create(request);
}
```

`MockMvc` chạy request qua Spring MVC, bind JSON thành record và gọi controller. `@MockitoBean` cung cấp service mock để test kiểm soát response mà không cần database.

`contentType(...)` mô tả định dạng request body. `accept(...)` mô tả định dạng response mà client mong nhận. Hai header này có mục đích khác nhau và nên được khai báo đúng trong test.

## 9. Kiểm thử field bắt buộc bị thiếu

Khi JSON không có `quantity`, Jackson có thể tạo DTO với `quantity == null` vì kiểu của field là `Integer`. Sau đó `@NotNull` phát hiện vi phạm và Spring ném `MethodArgumentNotValidException`.

```java
import org.springframework.http.MediaType;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingRequiredQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/validation-error"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].constraint").value("NotNull"));

    verifyNoInteractions(orderService);
}
```

Test này xác nhận cả response contract lẫn thứ tự xử lý: service không được gọi khi request chưa hợp lệ. Đây là assertion quan trọng nếu service có side effect như ghi database hoặc gọi dịch vụ bên ngoài.

Trong trường hợp request tạo nhiều field error, không nên phụ thuộc vào vị trí `[0]` vì thứ tự validation error không phải lúc nào cũng là hợp đồng. Hãy dùng JSONPath filter theo field hoặc deserialize danh sách lỗi rồi so sánh theo tập hợp. Ví dụ trên chỉ tạo một lỗi nên kiểm tra phần tử đầu tiên là rõ ràng.

## 10. Kiểm thử giá trị vượt giới hạn

Với `quantity` từ 1 đến 100, cần kiểm tra cả hai biên hợp lệ và giá trị ngay ngoài biên.

| Giá trị | Kết quả mong đợi | Constraint |
|---:|---|---|
| 0 | Từ chối | `@Min(1)` |
| 1 | Chấp nhận | Biên dưới hợp lệ |
| 100 | Chấp nhận | Biên trên hợp lệ |
| 101 | Từ chối | `@Max(100)` |

Ví dụ kiểm tra số lượng bằng 0:

```java
@Test
void rejectsQuantityBelowMinimum() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"))
            .andExpect(jsonPath("$.errors[0].constraint").value("Min"));

    verifyNoInteractions(orderService);
}
```

Kiểm tra độ dài chuỗi:

```java
@Test
void rejectsProductCodeLongerThanTwentyCharacters() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "123456789012345678901",
                              "quantity": 1
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].field").value("productCode"))
            .andExpect(jsonPath("$.errors[0].constraint").value("Size"));
}
```

Đối với giá trị biên hợp lệ, test cần stub service và xác nhận endpoint chấp nhận `quantity=1` hoặc `quantity=100`. Chỉ test giá trị sai chưa chứng minh constraint được đặt đúng theo hướng bao gồm hay loại trừ biên.

## 11. Kiểm thử JSON sai cú pháp hoặc sai kiểu

JSON sai cú pháp hoặc có giá trị không thể chuyển đổi sang kiểu Java sẽ thất bại trước Bean Validation. Ví dụ `quantity` cần là số nguyên nhưng client gửi chuỗi `"many"`:

```json
{
  "productCode": "BOOK-01",
  "quantity": "many"
}
```

Jackson không thể deserialize giá trị này thành `Integer`. Spring thường phát sinh `HttpMessageNotReadableException`, không phải `MethodArgumentNotValidException`.

```java
@Test
void rejectsWrongJsonValueType() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": "many"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));

    verifyNoInteractions(orderService);
}
```

JSON sai cú pháp cũng được xử lý ở bước đọc body:

```java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("{\"productCode\":\"BOOK-01\",\"quantity\":}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Không assertion vào nguyên văn thông báo Jackson. Nội dung exception có thể thay đổi theo phiên bản, cấu hình hoặc locale. Hãy kiểm tra mã lỗi công khai và status mà API cam kết.

## 12. Kiểm thử body bị thiếu hoàn toàn

`@RequestBody` mặc định có `required = true`. Nếu request không có body, Spring không thể cung cấp `CreateOrderRequest` cho controller và thường ném `HttpMessageNotReadableException`.

```java
@Test
void rejectsMissingRequestBody() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));

    verifyNoInteractions(orderService);
}
```

Trường hợp này khác với JSON hợp lệ nhưng thiếu một field. Body rỗng bị từ chối trong bước đọc body; body có JSON object nhưng thiếu `quantity` có thể bind thành DTO rồi bị Bean Validation từ chối.

Nếu API cho phép body tùy chọn bằng `@RequestBody(required = false)`, hợp đồng sẽ khác. Controller phải xử lý `null` có chủ đích và test cần phản ánh chính sách đó.

## 13. Kiểm thử path variable sai kiểu

Endpoint GET nhận `UUID`. Khi client gửi `/api/orders/not-a-uuid`, Spring không chuyển đổi được path variable thành UUID và phát sinh `MethodArgumentTypeMismatchException`.

```java
@Test
void rejectsInvalidOrderIdFormat() throws Exception {
    mockMvc.perform(get("/api/orders/not-a-uuid")
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));

    verifyNoInteractions(orderService);
}
```

Lưu ý phân biệt:

- `/api/orders/not-a-uuid`: path khớp route, nhưng giá trị không chuyển đổi được sang UUID; thường là `400`.
- `/api/orders`: route GET `/{id}` không khớp vì thiếu segment; thường là `404`.
- UUID hợp lệ nhưng không có đơn hàng: controller gọi service và service ném `OrderNotFoundException`; API trả `404` theo ánh xạ nghiệp vụ.

Ba tình huống có thể có cùng cảm giác “không tìm thấy đơn hàng” từ phía client, nhưng xảy ra ở những bước khác nhau và có ý nghĩa khác nhau.

## 14. Kiểm thử lỗi nghiệp vụ 404 và 409

Khi UUID hợp lệ nhưng đơn hàng không tồn tại, service ném `OrderNotFoundException`. Advice ánh xạ thành `404 Not Found`:

```java
import java.util.UUID;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@Test
void mapsMissingOrderToNotFoundProblem() throws Exception {
    UUID id = UUID.fromString("d2b6d39e-7df4-4e2e-8fd3-40c11a2d79c0");
    when(orderService.findById(id)).thenThrow(new OrderNotFoundException(id));

    mockMvc.perform(get("/api/orders/{id}", id)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/order-not-found"))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
```

Khi service phát hiện mã sản phẩm đã tồn tại, nó ném `DuplicateOrderException`. Advice ánh xạ thành `409 Conflict`:

```java
@Test
void mapsDuplicateOrderToConflictProblem() throws Exception {
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);
    when(orderService.create(request))
            .thenThrow(new DuplicateOrderException("BOOK-01"));

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PROBLEM_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 2
                            }
                            """))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.test/problems/duplicate-order"))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("DUPLICATE_ORDER"));
}
```

Các test này kiểm tra cả status HTTP và `status` trong Problem Detail body. Hai giá trị cần nhất quán. `type` và `code` là các định danh ổn định hơn `detail`, vốn là thông điệp dành cho con người.

## 15. Kiểm tra content negotiation và media type

`Content-Type` và `Accept` giải quyết hai vấn đề khác nhau:

| Header | Câu hỏi |
|---|---|
| `Content-Type` | Body request đang được gửi theo định dạng nào? |
| `Accept` | Client muốn nhận response theo định dạng nào? |

Với endpoint tạo đơn hàng, client gửi JSON nên đặt `Content-Type: application/json`. Khi request thành công, client có thể yêu cầu `application/json`; khi request lỗi, client có thể yêu cầu `application/problem+json`.

Nếu endpoint khai báo `consumes = application/json` nhưng client gửi `text/plain`, Spring thường trả `415 Unsupported Media Type`. Đây không phải lỗi Bean Validation vì body chưa được bind vào DTO.

Nếu client gửi `Accept` không tương thích với representation mà endpoint có thể tạo, Spring có thể trả `406 Not Acceptable`. Khi thiết kế API, hãy quyết định rõ response success và error media type được hỗ trợ. Test nên gửi `Accept` đúng với hợp đồng mà endpoint công bố.

## 16. Phân biệt validation, conversion và lỗi nghiệp vụ

Ba nhóm lỗi này cần test riêng vì chúng được phát hiện ở những thời điểm khác nhau.

| Nhóm | Ví dụ | Service có được gọi không? | Assertion chính |
|---|---|---:|---|
| Validation | `quantity = 0`, thiếu `productCode` | Không | `400`, `VALIDATION_FAILED`, field/constraint |
| Conversion/deserialization | `quantity = "many"`, UUID sai định dạng | Không | `400`, mã body/parameter không hợp lệ |
| Nghiệp vụ | Mã đơn hàng trùng, đơn hàng không tồn tại | Có | `409` hoặc `404`, business error code |

Nếu test chỉ kiểm tra status `400`, nó chưa chứng minh lỗi được phân loại đúng. Một JSON sai kiểu và một giá trị hợp lệ về kiểu nhưng vi phạm `@Min` đều có thể trả `400`, nhưng client có thể cần thông tin khác nhau để sửa request.

## 17. Xác nhận không có side effect khi request bị từ chối

Một assertion có giá trị trong test validation là xác nhận service không được gọi. Ví dụ:

```java
@Test
void doesNotCallServiceWhenQuantityIsInvalid() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Điều này chứng minh request bị chặn trước khi đi vào nghiệp vụ. Nó hữu ích khi service có side effect như ghi database, publish event hoặc gọi hệ thống thanh toán.

Không dùng `verifyNoInteractions(...)` cho test business exception nếu service chính là nơi phát sinh exception. Trong trường hợp đó, hãy verify service được gọi đúng một lần và assertion response phản ánh exception mà service ném ra.

## 18. Tổ chức test class đầy đủ

Một test class thực tế có thể nhóm các trường hợp theo hợp đồng endpoint:

```java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerHttpTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderApplicationService orderService;

    @Test
    void createsOrder() throws Exception {
        // Stub service, gửi JSON hợp lệ, kiểm tra 201, Location và body.
    }

    @Test
    void rejectsMissingQuantity() throws Exception {
        // Gửi JSON thiếu field, kiểm tra 400 và NotNull.
    }

    @Test
    void rejectsQuantityOutsideRange() throws Exception {
        // Gửi quantity = 0 hoặc 101, kiểm tra Min/Max.
    }

    @Test
    void rejectsMalformedBody() throws Exception {
        // Gửi JSON sai cú pháp, kiểm tra INVALID_REQUEST_BODY.
    }

    @Test
    void rejectsInvalidUuid() throws Exception {
        // Gửi path variable không chuyển đổi được, kiểm tra INVALID_PARAMETER.
    }

    @Test
    void mapsMissingOrder() throws Exception {
        // Stub service ném OrderNotFoundException, kiểm tra 404.
    }

    @Test
    void mapsDuplicateOrder() throws Exception {
        // Stub service ném DuplicateOrderException, kiểm tra 409.
    }
}
```

Đoạn trên là cấu trúc tổng hợp; trong test thực tế, thay phần comment bằng các request và expectation cụ thể đã trình bày ở các mục trước. Tên test nên mô tả hành vi quan sát được, không phụ thuộc tên exception nội bộ nếu exception đó không phải một phần của hợp đồng.

## 19. Những lỗi thường gặp khi viết test

| Cách làm | Vấn đề | Cách làm tốt hơn |
|---|---|---|
| Chỉ kiểm tra status `400` cho mọi đầu vào sai | Không xác nhận lỗi được phân loại đúng | Kiểm tra `code`, `type`, field và constraint |
| Dùng `int` cho field bắt buộc rồi kỳ vọng `@NotNull` bắt được field thiếu | Primitive không biểu diễn `null` | Dùng wrapper như `Integer` nếu cần phân biệt field không gửi |
| Cho rằng JSON sai kiểu là lỗi Bean Validation | Deserialize thất bại trước validation | Xử lý `HttpMessageNotReadableException` |
| Cho rằng UUID sai định dạng là lỗi nghiệp vụ 404 | Conversion thất bại trước service | Kiểm tra `MethodArgumentTypeMismatchException` và status 400 |
| Đưa exception message thô vào response | Có thể lộ dữ liệu nội bộ và thay đổi theo implementation | Dùng mã lỗi ổn định và detail công khai |
| Không import advice trong MVC slice | Test dùng handler mặc định thay vì error schema ứng dụng | `@Import(ApiExceptionHandler.class)` |
| Mock service bằng `@Mock` nhưng gọi bean Spring | Mock field không thay dependency trong context | Dùng `@MockitoBean` hoặc `@MockBean` theo phiên bản |
| Chỉ test giá trị vượt biên | Không chứng minh biên hợp lệ được chấp nhận | Test giá trị ngay tại biên và ngoài biên |
| So sánh thứ tự danh sách validation error | Thứ tự không nhất thiết là hợp đồng | Tìm lỗi theo field/code hoặc chuẩn hóa thứ tự |

## 20. Khi nào cần thêm integration test?

`@WebMvcTest` xác nhận controller, binding, validation, advice và response trong Spring MVC slice. Nó không chứng minh toàn bộ ứng dụng có thể kết nối database hoặc broker.

Nếu mục tiêu là xác nhận luồng HTTP đi qua service, repository và PostgreSQL thật, hãy bổ sung test rộng hơn, chẳng hạn `@SpringBootTest` với Testcontainers. Nếu cần xác nhận server connector, port hoặc TLS, chạy ứng dụng trên server thật với cổng ngẫu nhiên rồi gửi request qua HTTP client.

Phạm vi test nên tương ứng với rủi ro:

| Rủi ro | Test phù hợp |
|---|---|
| Controller bind sai DTO hoặc trả sai status | `@WebMvcTest` + MockMvc |
| Validation không được bật hoặc advice không được áp dụng | MVC slice với validation provider và advice thật |
| Repository query/migration sai | Integration test với database thật |
| HTTP transport/TLS/connector sai | Test server thật |
| Nghiệp vụ thuần sai | Unit test service/domain |

Không cần dùng `@SpringBootTest` cho mọi test controller. Dùng slice để có feedback nhanh, sau đó bổ sung một số integration test đại diện cho các ranh giới cần xác nhận.

## 21. Checklist cho một endpoint HTTP

Trước khi hoàn tất test suite cho endpoint, hãy xác nhận:

- Request hợp lệ trả status thành công đúng với semantics HTTP.
- Header `Location`, `Content-Type` và các header quan trọng được kiểm tra.
- Response body có đúng field và dữ liệu công khai.
- Field bắt buộc bị thiếu được từ chối.
- Chuỗi rỗng, khoảng trắng và giá trị vượt giới hạn được kiểm tra theo constraint.
- JSON sai cú pháp hoặc sai kiểu được ánh xạ thành lỗi đọc body.
- Path/query parameter không chuyển đổi được có error mapping phù hợp.
- Lỗi nghiệp vụ trả status và mã lỗi phù hợp.
- Service không được gọi khi request bị từ chối trước nghiệp vụ.
- Error body không tiết lộ stack trace hoặc chi tiết implementation.
- MVC slice có import exception advice và đúng mock bean.
- Các biên tích hợp database/broker/server thật có test ở phạm vi phù hợp.

## 22. Tài liệu tham khảo

- [Spring Framework Reference — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): bind request body và validation trong Spring MVC.
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Jakarta Bean Validation.
- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse` và exception handling.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): gửi request và assertion response trong Spring MVC Test.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices và hỗ trợ kiểm thử Spring Boot.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng Problem Details cho HTTP API.

Kiểm thử HTTP thành công, validation và ánh xạ lỗi cần chứng minh cả request hợp lệ lẫn các đường thất bại. Hãy phân biệt lỗi đọc body, lỗi conversion, vi phạm Bean Validation và exception nghiệp vụ; sau đó xác nhận status, media type và error code công khai bằng MockMvc. Khi request bị từ chối trước nghiệp vụ, kiểm tra service không được gọi để bảo đảm không có side effect ngoài ý muốn.
