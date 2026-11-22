# Kiểm thử dữ liệu thiếu, sai kiểu và vượt giới hạn

Khi gửi request bằng `MockMvc`, một bài kiểm thử API cần xác nhận ứng dụng phản hồi đúng với dữ liệu không hợp lệ. Những trường hợp thường gặp gồm thiếu body hoặc thiếu trường bắt buộc, truyền giá trị không chuyển đổi được sang kiểu Java mà controller yêu cầu, và truyền giá trị vượt giới hạn nghiệp vụ như số lượng âm, chuỗi quá dài hoặc trang yêu cầu quá lớn.

Các trường hợp này xảy ra ở những bước khác nhau trong quá trình xử lý request. Spring có thể từ chối request khi không đọc được body, khi chuyển đổi tham số thất bại, hoặc sau khi bind thành công nhưng Bean Validation phát hiện vi phạm. Vì thế, test nên tạo đúng dạng request cần kiểm tra và xác nhận hợp đồng HTTP mà API công bố.

## 1. Những lớp kiểm tra đầu vào trong Spring MVC

Một request đi qua nhiều bước trước khi controller thực hiện nghiệp vụ:

```text
HTTP request
    |
    v
Mapping và kiểm tra điều kiện request
    |
    v
Đọc body / chuyển đổi path variable / query parameter
    |
    v
Bind dữ liệu vào tham số hoặc DTO
    |
    v
Bean Validation (nếu khai báo @Valid / @Validated)
    |
    v
Controller và nghiệp vụ
    |
    v
HTTP response
```

Một số tình huống tiêu biểu:

| Đầu vào | Ví dụ | Bước thường phát hiện | Kết quả HTTP thường gặp |
|---|---|---|---|
| Thiếu request body bắt buộc | Gửi `POST` không có body cho tham số `@RequestBody` | Đọc body | `400 Bad Request` |
| Thiếu trường bắt buộc trong JSON | Bỏ `quantity` khỏi JSON DTO có `@NotNull` | Bean Validation sau khi bind | `400 Bad Request` |
| Sai cú pháp JSON hoặc sai kiểu JSON | Gửi `"quantity": "many"` trong khi Java cần `Integer` | HTTP message converter/Jackson | `400 Bad Request` |
| Thiếu query parameter bắt buộc | Bỏ `pageSize` có `@RequestParam` mặc định `required=true` | Resolve tham số controller | `400 Bad Request` |
| Sai kiểu query/path parameter | Gửi `pageSize=large` cho `int` hoặc id không phải số cho `Long` | Conversion | `400 Bad Request` |
| Vi phạm giới hạn | `quantity=0`, `quantity=101` khi giới hạn từ 1 đến 100 | Bean Validation | `400 Bad Request` |
| Sai media type | Gửi body không phải JSON cho endpoint chỉ nhận JSON | Content negotiation/message converter | `415 Unsupported Media Type` |

Đây là kết quả mặc định thường gặp của Spring MVC. API có thể định nghĩa response body riêng qua `@RestControllerAdvice`; test nên xác nhận status và cấu trúc lỗi thuộc hợp đồng đó thay vì phụ thuộc vào thông báo nội bộ của framework.

## 2. Khai báo hợp đồng đầu vào cho request body

Giả sử API tạo đơn hàng nhận mã sản phẩm và số lượng. DTO dùng wrapper `Integer` để có thể phân biệt trường bị thiếu (`null`) với giá trị số bằng 0:

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

Các constraint thể hiện những điều kiện khác nhau:

- `@NotNull` yêu cầu giá trị phải tồn tại và khác `null`.
- `@NotBlank` yêu cầu chuỗi không null, không rỗng và có ít nhất một ký tự không phải khoảng trắng.
- `@Size(max = 20)` giới hạn độ dài chuỗi tối đa 20 ký tự.
- `@Min(1)` và `@Max(100)` đặt khoảng giá trị hợp lệ cho số lượng, bao gồm cả hai biên 1 và 100.

Nếu dùng `int` thay cho `Integer`, trường JSON bị thiếu có thể nhận giá trị mặc định `0` trong quá trình bind. Khi đó `@NotNull` không thể phát hiện việc trường bị thiếu. Với dữ liệu bắt buộc mà cần phân biệt “không gửi” và “gửi giá trị 0”, wrapper type thường diễn đạt hợp đồng chính xác hơn.

Controller yêu cầu Spring validate DTO sau khi đọc body:

```java
import jakarta.validation.Valid;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderView create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @GetMapping("/search")
    List<OrderView> search(@RequestParam int pageSize) {
        return orderService.search(pageSize);
    }

    @GetMapping("/by-id/{id}")
    OrderView findById(@PathVariable Long id) {
        return orderService.findById(id);
    }
}

interface OrderService {
    OrderView create(CreateOrderRequest request);
    List<OrderView> search(int pageSize);
    OrderView findById(Long id);
}

record OrderView(Long id, String productCode, Integer quantity) {
}
```

`@RequestBody` yêu cầu body được đọc thành `CreateOrderRequest`. `@Valid` yêu cầu Spring chạy Bean Validation trên DTO sau khi chuyển đổi thành công. Nếu thiếu trường hoặc vi phạm constraint, controller không đi vào phần xử lý nghiệp vụ.

Ứng dụng cần có implementation Jakarta Bean Validation trên classpath, thường thông qua `spring-boot-starter-validation` trong Spring Boot. Chỉ khai báo annotation mà thiếu provider thì validation có thể không được thực thi.

## 3. Chuẩn hóa response lỗi cho API

Spring MVC có thể tạo response lỗi mặc định, nhưng API thực tế thường cần một cấu trúc ổn định để client xử lý. Có thể định nghĩa mã lỗi và danh sách vi phạm:

```java
import java.util.List;

record ApiError(String code, List<FieldViolation> violations) {
}

record FieldViolation(String field, String constraint) {
}
```

Một `@RestControllerAdvice` có thể chuyển các lỗi đầu vào phổ biến thành response thống nhất:

```java
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(MethodArgumentNotValidException ex) {
        List<FieldViolation> violations = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(error.getField(), error.getCode()))
                .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED", violations));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadableBody(HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_REQUEST_BODY", List.of()));
    }

    @ExceptionHandler({
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class
    })
    ResponseEntity<ApiError> handleInvalidParameter(Exception ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_PARAMETER", List.of()));
    }
}
```

Ví dụ này giữ response độc lập với thông báo lỗi chi tiết của Jackson hoặc Bean Validation. `constraint` được lấy từ mã constraint như `NotNull`, `NotBlank`, `Min`, `Max` hoặc `Size`; client không phải phân tích một câu thông báo có thể thay đổi theo ngôn ngữ hoặc phiên bản provider.

Trong ứng dụng thực tế, có thể bổ sung mã lỗi riêng cho từng trường hợp, vị trí tham số (`query`, `path`, `body`), giá trị bị từ chối hoặc correlation id. Chỉ đưa dữ liệu an toàn ra response; không trả stack trace, tên class nội bộ hay nội dung exception thô cho client.

## 4. Thiết lập MockMvc cho test controller

Với Spring Boot, `@WebMvcTest` tạo lát cắt MVC và cung cấp `MockMvc` để gửi request mà không cần mở cổng HTTP. Controller có thể dùng service mock để test tập trung vào việc bind, validate và tạo response.

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.beans.factory.annotation.Autowired;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerRequestTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;
}
```

`@WebMvcTest` tập trung vào thành phần web. Nếu controller cần service, repository hoặc một bean nghiệp vụ khác, hãy cung cấp mock hoặc import cấu hình test tương ứng. Trong các test dữ liệu không hợp lệ, service thường không được gọi vì request bị từ chối trước khi đi vào controller.

Các static import thường dùng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Một request JSON được gửi bằng `.contentType(MediaType.APPLICATION_JSON)` và `.content(...)`. Việc đặt đúng `Content-Type` quan trọng vì nó quyết định converter nào được chọn để đọc body.

## 5. Kiểm thử body bị thiếu và trường JSON bị thiếu

Hai trường hợp này khác nhau và thường dẫn đến hai exception khác nhau.

### Thiếu toàn bộ request body

Với `@RequestBody` mặc định `required=true`, request không có body sẽ không thể cung cấp đối tượng đầu vào. Spring thường ném `HttpMessageNotReadableException` và trả `400 Bad Request`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingRequestBody() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Không gửi `.content("")` cũng chính là tình huống body rỗng. Nếu API cho phép body tùy chọn bằng `@RequestBody(required = false)`, hợp đồng sẽ khác và controller phải xử lý giá trị `null` một cách có chủ đích.

### Thiếu một trường bắt buộc trong JSON

Khi body hợp lệ về cú pháp nhưng bỏ `quantity`, Jackson vẫn có thể tạo DTO với `quantity == null`. Bean Validation sau đó phát hiện vi phạm `@NotNull`:

```java
@Test
void rejectsMissingRequiredField() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("NotNull"));
}
```

Thứ tự các lỗi trong danh sách có thể phụ thuộc cách provider trả kết quả. Khi một request chỉ tạo một lỗi như ví dụ này, kiểm tra phần tử đầu tiên là đủ. Nếu request có nhiều lỗi, nên kiểm tra theo tập hợp field/constraint hoặc dùng JSONPath filter để tránh phụ thuộc thứ tự.

### Chuỗi rỗng, chỉ có khoảng trắng và null

`@NotNull`, `@NotEmpty` và `@NotBlank` có ngữ nghĩa khác nhau:

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` |
|---|---:|---:|---:|
| `null` | Không hợp lệ | Không hợp lệ | Không hợp lệ |
| `""` | Hợp lệ | Không hợp lệ | Không hợp lệ |
| `"   "` | Hợp lệ | Hợp lệ | Không hợp lệ |
| `"BOOK"` | Hợp lệ | Hợp lệ | Hợp lệ |

Nếu hợp đồng yêu cầu tên hoặc mã có ký tự thực, `@NotBlank` diễn đạt đúng hơn `@NotNull`. Hãy gửi từng giá trị trong test để xác nhận chính sách mà API muốn áp dụng.

## 6. Kiểm thử JSON sai cú pháp hoặc sai kiểu dữ liệu

JSON có cú pháp hợp lệ chưa chắc có kiểu phù hợp với DTO. Với `quantity` là `Integer`, giá trị sau đây sai kiểu:

```json
{
  "productCode": "BOOK-01",
  "quantity": "many"
}
```

Jackson không thể chuyển chuỗi `"many"` thành số nguyên. Lỗi xảy ra trong bước đọc body, trước Bean Validation, vì vậy handler nhận `HttpMessageNotReadableException` thay vì `MethodArgumentNotValidException`.

```java
@Test
void rejectsWrongJsonValueType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": "many"
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

JSON sai cú pháp cũng bị từ chối ở cùng bước:

```java
@Test
void rejectsMalformedJson() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"productCode\": \"BOOK-01\", \"quantity\": }"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST_BODY"));
}
```

Không nên assertion vào thông báo Jackson như “Cannot deserialize value...” vì nội dung này có thể thay đổi theo phiên bản, cấu hình và ngôn ngữ. Hãy kiểm tra status và mã lỗi công khai của API.

## 7. Kiểm thử query parameter và path variable sai kiểu hoặc bị thiếu

Khác với JSON body, query parameter và path variable thường được chuyển từ chuỗi trong URL sang kiểu Java của tham số controller.

Ví dụ endpoint nhận số trang:

```java
@GetMapping("/search")
List<OrderView> search(@RequestParam int pageSize) {
    return orderService.search(pageSize);
}
```

`pageSize=large` không chuyển đổi được thành `int`:

```java
@Test
void rejectsNonNumericQueryParameter() throws Exception {
    mockMvc.perform(get("/orders/search")
                    .param("pageSize", "large"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
}
```

Nếu `pageSize` là tham số bắt buộc và không được gửi, Spring thường ném `MissingServletRequestParameterException`:

```java
@Test
void rejectsMissingRequiredQueryParameter() throws Exception {
    mockMvc.perform(get("/orders/search"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
}
```

Với path variable, ví dụ `@PathVariable Long id`, giá trị `/orders/by-id/abc` không thể chuyển thành `Long` và thường dẫn đến `MethodArgumentTypeMismatchException`, cũng trả `400` nếu xử lý theo mặc định hoặc advice ở trên. Nếu thiếu hẳn segment `/id`, URL có thể không khớp route và trả `404 Not Found`; đó là lỗi định tuyến, không phải lỗi chuyển đổi kiểu của tham số.

Một tham số khai báo là `String` sẽ nhận chuỗi tùy ý, vì thế `pageSize=large` chỉ là lỗi kiểu khi controller khai báo kiểu đích như `int`, `Integer`, `Long`, enum hoặc một kiểu có converter tương ứng. Hãy kiểm tra đúng chữ ký controller khi thiết kế test.

## 8. Kiểm thử giới hạn dưới, giới hạn trên và độ dài

Kiểm tra giới hạn nên bao phủ cả hai phía của biên. Với `quantity` từ 1 đến 100:

| Giá trị | Kỳ vọng | Constraint liên quan |
|---:|---|---|
| `0` | Từ chối | `@Min(1)` |
| `1` | Chấp nhận | Giá trị biên dưới hợp lệ |
| `100` | Chấp nhận | Giá trị biên trên hợp lệ |
| `101` | Từ chối | `@Max(100)` |

Test cho giá trị vượt biên dưới:

```java
@Test
void rejectsQuantityBelowMinimum() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Min"));
}
```

Test cho giá trị vượt biên trên:

```java
@Test
void rejectsQuantityAboveMaximum() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01",
                              "quantity": 101
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("quantity"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Max"));
}
```

Với chuỗi quá dài, gửi giá trị vượt `@Size(max = 20)`:

```java
@Test
void rejectsProductCodeLongerThanAllowed() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "123456789012345678901",
                              "quantity": 1
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].field").value("productCode"))
            .andExpect(jsonPath("$.violations[0].constraint").value("Size"));
}
```

Một bộ test đầy đủ cũng cần xác nhận giá trị đúng tại biên được chấp nhận. Có thể mock service để trả kết quả và kiểm tra request với `quantity=1` hoặc `quantity=100` đi qua controller. Nếu chỉ kiểm tra các giá trị sai, test chưa chứng minh giới hạn được đặt đúng theo hướng bao gồm hay loại trừ biên.

### Giới hạn số chữ số và số thập phân

Với số tiền hoặc tỷ lệ, chọn constraint phù hợp với kiểu dữ liệu và ý nghĩa nghiệp vụ:

- `@DecimalMin` và `@DecimalMax` kiểm soát cận của `BigDecimal` hoặc kiểu số tương ứng.
- `inclusive = false` dùng khi giá trị đúng bằng cận cũng không hợp lệ.
- `@Digits(integer = ..., fraction = ...)` giới hạn số chữ số phần nguyên và phần thập phân.
- `@Positive`, `@PositiveOrZero`, `@Negative` và `@NegativeOrZero` diễn đạt quy tắc dấu.

Không dùng `double` cho tiền chỉ để tiện kiểm tra giới hạn thập phân. `BigDecimal` thường phù hợp hơn vì biểu diễn số thập phân chính xác và hỗ trợ các constraint tương ứng.

## 9. Phân biệt giới hạn dữ liệu với giới hạn kích thước HTTP

`@Size`, `@Min`, `@Max` và các constraint Bean Validation kiểm tra dữ liệu sau khi request đã được đọc và bind. Chúng không tự giới hạn số byte của HTTP body.

Ví dụ, `@Size(max = 20)` trên `productCode` chỉ kiểm tra độ dài chuỗi đã được chuyển thành DTO. Nếu client gửi một body JSON rất lớn, ứng dụng có thể phải đọc hoặc phân tích body trước khi constraint này được chạy.

Các giới hạn khác thuộc tầng HTTP hoặc hạ tầng:

| Loại giới hạn | Nơi thường cấu hình | Cách kiểm thử phù hợp |
|---|---|---|
| Độ dài chuỗi, số lượng, khoảng ngày | Bean Validation hoặc logic nghiệp vụ | `MockMvc` với giá trị ở dưới, tại và vượt biên |
| Số phần tử trong danh sách JSON | `@Size` trên collection hoặc validator | `MockMvc` với danh sách rỗng, đủ giới hạn và vượt giới hạn |
| Kích thước file upload | Multipart configuration và multipart resolver/container | `MockMvc` multipart để kiểm tra logic ứng dụng; embedded server test để xác nhận giới hạn container |
| Tổng kích thước HTTP request body | Servlet container, proxy, gateway hoặc filter giới hạn body | Kiểm thử tích hợp qua server/hạ tầng thực tế có cấu hình giới hạn |
| Tốc độ gửi request hoặc quota theo client | Gateway, filter hoặc rate limiter | Kiểm thử thành phần đó và test tích hợp qua đường request thực |

`MockMvc` mô phỏng xử lý Spring MVC trong tiến trình test, không mở socket và không đi qua toàn bộ connector của servlet container hay reverse proxy. Vì vậy, test `MockMvc` có thể xác nhận validator của ứng dụng từ chối một chuỗi quá dài, nhưng không đủ để chứng minh Nginx, API Gateway hoặc embedded Tomcat giới hạn request body đúng số byte.

Nếu ứng dụng có filter tự kiểm tra `Content-Length` hoặc đọc giới hạn byte, có thể kiểm thử filter trong chuỗi MockMvc. Tuy nhiên, hành vi của connector đối với request chunked, body thực tế và multipart vẫn cần test qua server được khởi động thật.

## 10. Media type và định dạng request không phù hợp

Kiểm thử dữ liệu sai cũng cần phân biệt lỗi body với lỗi media type. Nếu endpoint khai báo:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
OrderView create(@Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
```

request gửi `Content-Type: text/plain` không phù hợp với `consumes`. Spring thường trả `415 Unsupported Media Type` trước khi Bean Validation chạy.

```java
@Test
void rejectsUnsupportedContentType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("productCode=BOOK-01&quantity=1"))
            .andExpect(status().isUnsupportedMediaType());
}
```

Test này kiểm tra hợp đồng media type, không phải kiểm tra sai kiểu của trường `quantity`. Tương tự, `Accept` mô tả định dạng response mà client có thể nhận; nó khác với `Content-Type`, định dạng body mà client đang gửi.

## 11. Không để nghiệp vụ chạy khi request đã bị từ chối

Khi request sai bị chặn ở bước bind hoặc validation, service không nên được gọi. Có thể xác nhận điều này bằng Mockito:

```java
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotCallServiceWhenRequiredFieldIsMissing() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productCode": "BOOK-01"
                            }
                            """))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Assertion này hữu ích khi ranh giới cần bảo vệ là controller không gọi nghiệp vụ với dữ liệu chưa hợp lệ. Nếu controller có một dependency khác được gọi trước khi validate hoặc có logic trong filter/interceptor, hãy chỉ verify dependency thuộc đúng hợp đồng đang kiểm tra.

## 12. Validation ở tham số phương thức khác với validation DTO

Ví dụ trong bài dùng `@Valid @RequestBody` để validate các field của DTO. Khi đặt constraint trực tiếp trên tham số controller, chẳng hạn `@Min(1) @RequestParam int pageSize`, Spring Framework 6.1 trở lên có cơ chế method validation tích hợp và có thể phát sinh `HandlerMethodValidationException`.

Nếu lớp controller dùng `@Validated` để kích hoạt method validation thông qua proxy, đường xử lý và loại exception có thể khác, thường liên quan đến `ConstraintViolationException`. Khi viết `@RestControllerAdvice`, hãy căn cứ vào cách validation thực tế được kích hoạt trong ứng dụng và xử lý các exception tương ứng. Đừng giả định mọi vi phạm đều là `MethodArgumentNotValidException`.

Đối với bài test, hãy tạo request qua `MockMvc` như client thật và xác nhận response contract cuối cùng. Chỉ assertion loại exception ở unit test dành riêng cho validator hoặc advice khi chính loại exception đó là điều cần kiểm tra.

## 13. Ma trận test đầu vào nên có

Với một endpoint nhận JSON, ma trận cơ bản có thể gồm:

| Nhóm | Request cần gửi | Kỳ vọng |
|---|---|---|
| Body | Không có body | `400`, mã lỗi body thiếu/không đọc được |
| Cấu trúc | JSON sai cú pháp | `400`, mã lỗi body không hợp lệ |
| Kiểu | Trường số nhận chuỗi không chuyển đổi được | `400`, mã lỗi body không hợp lệ |
| Bắt buộc | Thiếu trường `quantity` | `400`, vi phạm `NotNull` |
| Chuỗi | `productCode` là `null`, rỗng hoặc chỉ có khoảng trắng | `400`, vi phạm constraint phù hợp |
| Độ dài | `productCode` dài hơn 20 ký tự | `400`, vi phạm `Size` |
| Cận dưới | `quantity=0` | `400`, vi phạm `Min` |
| Biên dưới | `quantity=1` | Request được chấp nhận |
| Biên trên | `quantity=100` | Request được chấp nhận |
| Cận trên | `quantity=101` | `400`, vi phạm `Max` |
| Query | Thiếu `pageSize` bắt buộc | `400`, mã lỗi parameter |
| Query | `pageSize=large` | `400`, mã lỗi parameter |
| Media type | Gửi `text/plain` cho endpoint chỉ nhận JSON | `415` |

Không nhất thiết phải gom mọi trường hợp vào một test lớn. Mỗi test nên có tên mô tả một lý do từ chối và một kỳ vọng chính. Dùng parameterized test khi nhiều giá trị kiểm tra cùng một quy tắc, ví dụ các giá trị `0` và `101` của giới hạn số lượng.

## 14. Các lỗi thường gặp khi viết test

| Cách làm | Vì sao không tốt | Cách làm rõ hơn |
|---|---|---|
| Chỉ kiểm tra status `400` cho mọi loại dữ liệu sai | Không phân biệt thiếu trường, sai kiểu và vượt giới hạn | Kiểm tra thêm mã lỗi và field/constraint trong response |
| Assertion vào toàn bộ thông báo exception | Phụ thuộc Jackson, Bean Validation provider, locale và phiên bản | Kiểm tra mã lỗi ổn định của API |
| Dùng `int` cho trường bắt buộc rồi kiểm tra `@NotNull` | Primitive không thể biểu diễn `null` | Dùng wrapper như `Integer` nếu cần phân biệt trường thiếu |
| Dùng `@NotNull` cho chuỗi chỉ có khoảng trắng | `@NotNull` vẫn chấp nhận `"   "` | Dùng `@NotBlank` nếu cần nội dung thực |
| Chỉ test giá trị vượt biên | Không chứng minh biên hợp lệ được chấp nhận | Test cả giá trị ngay tại biên và ngay ngoài biên |
| Nghĩ `@Size` giới hạn byte của HTTP body | `@Size` chạy trên giá trị đã bind | Kiểm thử giới hạn body ở tầng filter/container/gateway phù hợp |
| Gửi `pageSize=large` nhưng controller nhận `String` | Spring không có lý do chuyển chuỗi sang số | Khai báo kiểu đích đúng với hợp đồng, ví dụ `int` |
| Kiểm tra service bị gọi trong test validation thất bại | Request phải bị chặn trước nghiệp vụ | Dùng `verifyNoInteractions` hoặc verify phù hợp |

## 15. Quy trình viết một test dữ liệu không hợp lệ

1. Đọc chữ ký endpoint: `@RequestBody`, `@RequestParam`, `@PathVariable`, `consumes` và kiểu Java của từng tham số.
2. Xác định request sai ở bước nào: thiếu dữ liệu, không parse được, không chuyển đổi được hay vi phạm constraint sau khi bind.
3. Dùng `MockMvc` tạo đúng request như client gửi, bao gồm URL, `Content-Type`, body và parameter.
4. Xác nhận HTTP status theo hợp đồng, ví dụ `400` cho dữ liệu không hợp lệ hoặc `415` cho media type không hỗ trợ.
5. Nếu API có error schema, xác nhận mã lỗi, field và constraint ổn định.
6. Xác nhận service không được gọi khi request bị từ chối trước nghiệp vụ.
7. Với giới hạn, test cả hai biên hợp lệ và giá trị ngay bên ngoài mỗi biên.
8. Với giới hạn byte hoặc hành vi phụ thuộc container/proxy, bổ sung test tích hợp qua server/hạ tầng thực tế.

## 16. Tài liệu tham khảo

- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Jakarta Bean Validation trong Spring.
- [Spring Framework Reference — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): đọc request body, message converter và validation.
- [Spring Framework Reference — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): bind query parameter vào tham số controller.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): gửi request và assertion response trong Spring MVC Test.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): ngữ nghĩa constraint và cơ chế validation.

Kiểm thử dữ liệu thiếu, sai kiểu và vượt giới hạn có giá trị nhất khi mỗi request mô phỏng đúng lỗi mà client có thể gửi. Hãy phân biệt lỗi đọc body, lỗi chuyển đổi tham số và lỗi Bean Validation; sau đó kiểm tra response contract ở đúng ranh giới. Điều này giúp test chứng minh API từ chối đầu vào không hợp lệ trước khi nghiệp vụ được thực thi.
