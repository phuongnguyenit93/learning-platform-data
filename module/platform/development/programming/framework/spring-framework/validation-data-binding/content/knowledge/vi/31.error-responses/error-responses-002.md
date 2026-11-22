# Giữ mã lỗi, đường dẫn, tham số và thông báo cần thiết trong phản hồi validation của Spring

## 1. Bài toán: trả HTTP 400 chưa đủ để client sửa đúng trường

Giả sử một người dùng gửi đơn hàng có hai dòng:

~~~json
{
  "customerName": "",
  "items": [
    {"sku": "PEN", "quantity": 0},
    {"sku": "", "quantity": 2}
  ]
}
~~~

Nếu API chỉ trả:

~~~json
{"error": "Validation failed"}
~~~

frontend không biết trường nào sai, thuộc dòng hàng nào, cần sửa theo ngưỡng nào, hay nên hiển thị thông báo gì. Nếu backend lại trả nguyên `exception.getMessage()` hoặc `exception.toString()` thì có nguy cơ lộ tên class, tên method, dữ liệu bị từ chối và thông tin nội bộ; đồng thời chuỗi lỗi khó giữ ổn định khi nâng Spring/Jakarta provider.

Một phản hồi hữu ích hơn:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Fix the listed fields.",
  "code": "REQUEST_VALIDATION_FAILED",
  "issues": [
    {
      "code": "NotBlank",
      "path": "customerName",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {},
      "message": "Customer name is required"
    },
    {
      "code": "Min",
      "path": "items[0].quantity",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {"minimum": 1},
      "message": "Quantity must be at least 1"
    },
    {
      "code": "NotBlank",
      "path": "items[1].sku",
      "location": "body",
      "parameterIndex": 0,
      "parameters": {},
      "message": "SKU is required"
    }
  ]
}
~~~

Trong ví dụ này:

- **`code` ở cấp response** là mã nghiệp vụ ổn định cho loại lỗi request: `REQUEST_VALIDATION_FAILED`.
- **`issues[*].code`** là mã lỗi cụ thể (`NotBlank`, `Min`, `typeMismatch`…). Client dùng nó để phân loại, analytics và hỗ trợ nhiều ngôn ngữ.
- **`path`** giữ nguyên đường dẫn property/index: `items[0].quantity` xác định chính xác dòng hàng số 0.
- **`location`** cho biết vị trí nhận input (`body`, `form`, `query`, `header`, …), tránh nhầm hai trường có cùng tên ở các nguồn khác nhau.
- **`parameterIndex`** cho biết vị trí tham số trong chữ ký handler method, hữu ích khi có method validation.
- **`parameters`** giữ những thuộc tính công khai cần thiết của constraint, ví dụ `minimum=1` để giao diện có thể hiển thị quy tắc.
- **`message`** là văn bản đã được giải quyết theo locale dành cho con người; client **không nên dựa vào nội dung message để ra quyết định logic**.

Đó là trọng tâm bài học: **giữ đủ thông tin để client hành động, nhưng không bê nguyên đối tượng exception ra ngoài**. Ví dụ chọn định dạng **Problem Details / RFC 9457** với trường mở rộng `code` và `issues`. Đây là một contract API do ứng dụng tự thiết kế, không phải Spring tự sinh ra các fields `issues`, `location` và `parameters` mặc định.

Bài dùng **Java 17**, **Spring Boot 3.5.7 / Spring Framework 6.2**, namespace `jakarta.validation.*` và một demo **Spring MVC**. Những nguyên tắc metadata cũng áp dụng được cho WebFlux, nhưng exception binding và HTTP lifecycle có những khác biệt được nêu riêng.

## 2. Sáu mảnh dữ liệu trong một validation issue

### 2.1. Mã lỗi ổn định

Mã lỗi phải biểu diễn **loại vi phạm**, không phải toàn bộ câu thông báo.

Ví dụ:

| Mã nguồn thường gặp | Nghĩa | Cách dùng ở client |
| --- | --- | --- |
| `NotBlank` | Chuỗi không được null/rỗng/toàn khoảng trắng | Đánh dấu ô nhập bắt buộc |
| `NotNull` | Giá trị bắt buộc | Yêu cầu có giá trị |
| `NotEmpty` | Collection/chuỗi không được rỗng | Yêu cầu ít nhất một mục |
| `Min` | Giá trị phải từ một ngưỡng trở lên | Hiển thị ngưỡng `minimum` |
| `Size` | Độ dài/kích thước trong khoảng | Hiển thị `minLength`/`maxLength` khi công khai |
| `typeMismatch` | Chuyển kiểu khi binding thất bại | Yêu cầu nhập đúng định dạng |
| `INVALID_VALUE` | Fallback được ứng dụng định nghĩa | Hiển thị lỗi chung không lộ nội bộ |

Trong Spring, `FieldError#getCode()` thường trả mã tổng quát như `NotBlank` hoặc `typeMismatch`. `FieldError#getCodes()` trả **danh sách mã với mức độ cụ thể khác nhau**, ví dụ `NotBlank.orderForm.customerName`, `NotBlank.customerName`, `NotBlank.java.lang.String`, `NotBlank` (danh sách cụ thể tùy resolver). Không nên xuất toàn bộ danh sách ra public API: nó có thể mang tên class, object name hoặc chi tiết nội bộ.

Một chiến lược tốt: **whitelist mã nguồn có chủ đích** rồi chuẩn hóa thành contract công khai; nếu không nhận diện được, trả `INVALID_VALUE`. Nếu ứng dụng có mã riêng như `inventory.insufficient`, đăng ký nó trong một bảng ánh xạ công khai và viết test ổn định, không chuyển tự do mọi code nội bộ ra client.

### 2.2. Đường dẫn (path)

Path cho biết **đối tượng và vị trí lỗi**:

~~~text
customerName
shippingAddress.city
items[0].quantity
items[1].sku
labels[priority]
contacts[support].email
~~~

`FieldError#getField()` lưu đúng field path của BindingResult. Với list/array, index trong `[0]`, `[1]` quan trọng; với map, key trong `[priority]` có thể quan trọng. **Không cắt bỏ index** hoặc chỉ lấy phần cuối như `quantity` vì frontend sẽ không biết hàng nào cần sửa.

Phân biệt:

- **Field error** có đường dẫn property cụ thể.
- **Object/global error** áp dụng cho cả đối tượng hoặc quan hệ giữa các fields, có thể không có path đơn lẻ. API nên cho phép `path=""` hoặc `path=null` theo contract đã thống nhất, cùng một mã cấp object.
- **Method parameter error** có tên request argument hoặc index của parameter.
- **Cross-parameter error** liên quan nhiều đối số cùng lúc, không nên tự gán bừa vào một field.

Đường dẫn `items[0].quantity` là cú pháp Spring property path; nó **không phải** JSON Pointer `/items/0/quantity`. Nếu frontend yêu cầu JSON Pointer, backend phải có bộ chuyển path được kiểm thử (bao gồm dấu chấm, key map và escaping), không đơn giản thay dấu ngoặc bằng dấu gạch chéo.

### 2.3. Nguồn vị trí (location)

`path="id"` có thể chỉ một query parameter, path variable hoặc field trong JSON. Thêm `location`:

~~~json
{"location":"query","path":"id"}
~~~

Hoặc:

~~~json
{"location":"body","path":"id"}
~~~

Không dùng tên class của Spring như `RequestParamMethodArgumentResolver` làm public location; client chỉ cần từ vựng ổn định như `query`, `path`, `header`, `body`, `form`, `crossParameter`.

### 2.4. Vị trí tham số phương thức

Khi Spring MVC 6.1+ method validation được kích hoạt bởi `@Min`, `@NotBlank` trực tiếp trên parameter, `HandlerMethodValidationException#getParameterValidationResults()` nhóm lỗi theo `MethodParameter`.

Từ đó có:

~~~java
int index = result.getMethodParameter().getParameterIndex();
~~~

Đây là **chỉ số zero-based trong Java handler method**, không phải thứ tự input trên HTML form. Có thể thêm `parameterIndex` để debugging hoặc mapping ở một client có contract cố định. Tuy nhiên, khi controller refactor/thêm parameter, chỉ số sẽ thay đổi; muốn **tên public ổn định**, ưu tiên khai báo tường minh `@RequestParam(name="units")` và lấy `units` làm `path`.

### 2.5. Các tham số của constraint

Ví dụ `@Min(1)` có attribute `value=1`; `@Size(min=2,max=20)` có `min=2, max=20`. Thông tin này hữu ích để client tạo giao diện:

~~~json
{
  "code": "Min",
  "path": "items[0].quantity",
  "parameters": {"minimum": 1}
}
~~~

Jakarta `ConstraintViolation#getConstraintDescriptor().getAttributes()` chứa **nhiều thông tin**: `message`, `groups`, `payload` và các attributes custom khác. **Không serialize cả map attributes**. Hãy whitelist những gì client được biết, ví dụ `minimum`, `minLength`, `maxLength`. Với custom constraints có metadata nhạy cảm (policy identifier, regex bí mật, tenant limits), tuyệt đối không xuất hàng loạt.

### 2.6. Message đã dịch

`message` là lời nhắc cho người dùng:

~~~text
vi: Số lượng phải từ 1 trở lên
en: Quantity must be at least 1
~~~

Đừng bắt client phân tích từ vựng `"phải từ"` hay `"at least"` để suy ra ngưỡng; dùng `code` và `parameters`. Ngôn ngữ có thể được chọn bởi `Accept-Language`, `LocaleResolver`, tài khoản người dùng hoặc quy tắc product. Thống nhất quy trình địa phương hóa ở server và client để tránh dịch trùng.

## 3. Spring lấy các phần dữ liệu ở đâu?

### 3.1. `MethodArgumentNotValidException`: lỗi trên một argument object

Khi handler có:

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // ...
}
~~~

Nếu `OrderRequest` chứa các constraints và request JSON không đạt, Spring MVC thường ném `MethodArgumentNotValidException`. Exception này có:

~~~java
BindingResult result = ex.getBindingResult();

List<FieldError> fields = result.getFieldErrors();
List<ObjectError> globals = result.getGlobalErrors();
~~~

Với từng `FieldError`:

~~~java
String field = error.getField();
String code = error.getCode();
String message = error.getDefaultMessage();
Object[] args = error.getArguments();
~~~

`getArguments()` là arguments dùng khi resolve message codes, **không bảo đảm là một public constraint-parameter schema**. Nó có thể chứa đối tượng `MessageSourceResolvable`, field names, constraint values và các giá trị khác. Đừng trả nguyên args cho client.

`FieldError#getRejectedValue()` có thể chứa dữ liệu người dùng, gồm token, số giấy tờ hoặc nội dung riêng tư. **Không đưa rejected value ra public error JSON** chỉ vì UI muốn “điền lại” form; frontend đã có bản input nó vừa gửi.

### 3.2. `HandlerMethodValidationException`: lỗi trực tiếp trên method

Với Spring MVC 6.1+:

~~~java
@GetMapping("/quote")
public String quote(
        @RequestParam(name = "units")
        @Min(1) int units) {
    return "units=" + units;
}
~~~

Vi phạm `units=0` sẽ đi theo built-in method validation và thường ném `HandlerMethodValidationException` với HTTP 400. API chính:

~~~java
ex.getParameterValidationResults();
ex.getCrossParameterValidationResults();
ex.isForReturnValue();
ex.getStatusCode();
ex.visitResults(...);
~~~

Từng `ParameterValidationResult` có:
- `getMethodParameter()`: tham số Java method liên quan.
- `getResolvableErrors()`: các `MessageSourceResolvable` tương ứng direct violations.
- `getContainerIndex()` và `getContainerKey()`: index/key nếu validation vào phần tử collection/map.
- `unwrap(resolvable, ConstraintViolation.class)`: từ Spring Framework 6.2, có thể lấy lại metadata Jakarta constraint ở những lỗi thích hợp.

Nếu result là `ParameterErrors` (subclass), ta có thêm interface `Errors` để lấy `getFieldErrors()`/`getGlobalErrors()` của nested object. Không giả định mọi method-validation result đều là `FieldError`.

### 3.3. `BindingResult` phân biệt lỗi field và lỗi object

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError field) {
        // field.getField()
    } else {
        // Lỗi ở cấp đối tượng: không có field path cụ thể.
    }
}
~~~

Dùng `getAllErrors()` khi cần **không bỏ sót object-level violations**. Chỉ lấy `getFieldErrors()` có thể khiến constraint kiểm tra nhiều thuộc tính của cùng một object bị mất trong phản hồi.

### 3.4. Conversion errors khác constraint violations

Ví dụ form gửi:

~~~text
items[0].quantity=abc
~~~

Java property là `Integer`, nên `WebDataBinder` không thể chuyển `abc` thành số. `FieldError#getCode()` thường là `typeMismatch`. Không có `ConstraintViolation` Jakarta tương ứng, vì lỗi đến từ chuyển kiểu **trước validation**.

Còn:

~~~text
items[0].quantity=0
~~~

chuyển thành Integer thành công; `@Min(1)` phát hiện sai và phát sinh constraint violation. Cả hai cùng có thể nằm trong `BindingResult` nhưng nguồn gốc khác nhau; bộ chuyển response phải xử lý cả hai **mà không ép mọi FieldError phải unwrap thành Jakarta ConstraintViolation**.

### 3.5. Những lỗi xảy ra trước binding

- JSON không hợp lệ: `HttpMessageNotReadableException`.
- Required query parameter bị thiếu: `MissingServletRequestParameterException`.
- Query `units=abc` trong khi method nhận `int`: `MethodArgumentTypeMismatchException`.
- Media type không hỗ trợ: `HttpMediaTypeNotSupportedException`.

Đây không nhất thiết là `MethodArgumentNotValidException`. Nếu product cần hợp đồng lỗi thống nhất, viết handlers tương ứng và giữ `location/path/code/message` theo dữ liệu exception cung cấp; **không giả định `FieldError` luôn tồn tại**.

## 4. Thiết kế ProblemDetail và contract cho frontend

Spring Framework 6.x có `org.springframework.http.ProblemDetail` hỗ trợ RFC 9457. Các trường tiêu chuẩn:

| Trường | Ý nghĩa |
| --- | --- |
| `type` | URI định danh loại vấn đề |
| `title` | Tên loại lỗi ngắn gọn |
| `status` | HTTP status |
| `detail` | Diễn giải tổng quát |
| `instance` | URI instance của request nếu được set |

Spring cho thêm properties tùy chỉnh qua `ProblemDetail#setProperty(String,Object)`; Jackson mixin của Spring làm chúng xuất hiện dưới dạng top-level JSON properties. Ta bổ sung:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Fix the listed fields.",
  "code": "REQUEST_VALIDATION_FAILED",
  "issues": []
}
~~~

**Các nguyên tắc contract:**

1. `code` dùng để xử lý logic; message chỉ để hiển thị.
2. Giữ **toàn bộ issue hợp lệ**: nếu một field vi phạm hai constraints, đừng tự gộp chỉ còn một lỗi trừ khi product đã quyết định.
3. Sắp xếp issues khi muốn response deterministic; đừng dựa vào thứ tự duyệt `Set<ConstraintViolation<?>>`.
4. Không gửi raw `ConstraintViolation`, `FieldError` hay Throwable trực tiếp qua Jackson.
5. Đừng dùng `getRejectedValue()` hay `getArgument()` làm public `parameters`.
6. Với return-value validation, lỗi thuộc server: **không tiết lộ thông tin về response hoặc method nội bộ** và giữ HTTP 500.
7. Giới hạn tối đa số lượng issues trong API public nếu form có thể phát sinh hàng nghìn lỗi; ghi nhận chính sách cắt bớt một cách tường minh bằng `truncated`/`total` nếu product cần.

Ví dụ hai issues cùng field là hợp lệ:

~~~json
{
  "issues": [
    {"code":"NotBlank","path":"customerName","message":"Required"},
    {"code":"Size","path":"customerName","message":"At most 30 characters"}
  ]
}
~~~

Đây là minh họa thiết kế tối giản (thiếu các fields khác để ngắn gọn). Nó cho thấy **không mất một issue chỉ vì trùng path**; frontend tự chọn hiển thị tất cả hay chỉ issue đầu tiên.

### Trường hợp API muốn JSON Pointer

`items[0].quantity` dễ dùng khi frontend cũng sử dụng indexed form names. Một số UI/schema library lại muốn JSON Pointer:

~~~text
/items/0/quantity
~~~

Đừng đổi đại dấu chấm và ngoặc bằng regex nếu Map keys có dấu chấm, dấu `~`, `/` hoặc các ký tự đặc biệt. JSON Pointer (RFC 6901) có cơ chế escape `~0` và `~1`; mapping từ property path Spring sang JSON tree cần một parser/canonicalization đáng tin cậy. Nếu chưa có, giữ nguyên `path` của Spring và ghi rõ grammar trong API contract.

## 5. Ví dụ Maven Java 17 + Spring Boot 3.5.7

Project minh họa một **định dạng lỗi thống nhất** cho ba nguồn:
1. JSON body `@Valid @RequestBody` với nested list.
2. HTML/form URL-encoded `@Valid @ModelAttribute`, gồm lỗi `typeMismatch`.
3. Query `@RequestParam @Min`, tức built-in method validation của Spring MVC 6.1+.

Đồng thời có endpoint cố tình sai **return-value constraint** để chứng minh không trả chi tiết nội bộ.

### 5.1. Cây thư mục

~~~text
pom.xml
src/main/java/com/example/errors/
  ErrorResponseApplication.java
  LineItemInput.java
  OrderRequest.java
  OrderController.java
  ApiIssue.java
  ValidationErrorAdvice.java
src/main/resources/
  messages.properties
  messages_vi.properties
src/test/java/com/example/errors/
  ValidationErrorAdviceTest.java
~~~

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>structured-validation-errors</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
    </dependencies>
</project>
~~~

`spring-boot-starter-web` chạy Spring MVC; `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider; `spring-boot-starter-test` có JUnit 5 và MockMvc. Không dùng WebFlux starter trong project này, tránh nhầm hai loại exception của Servlet/reactive stack.

### 5.3. Main application

~~~java
// src/main/java/com/example/errors/ErrorResponseApplication.java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorResponseApplication.class, args);
    }
}
~~~

### 5.4. DTO của phần tử list

~~~java
// src/main/java/com/example/errors/LineItemInput.java
package com.example.errors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class LineItemInput {

    @NotBlank(message = "{order.sku.required}")
    private String sku;

    @NotNull(message = "{order.quantity.required}")
    @Min(value = 1, message = "{order.quantity.min}")
    private Integer quantity;

    public LineItemInput() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

`quantity=0` hợp lệ về conversion nhưng vi phạm `@Min(1)`; `quantity=abc` trong **form** gây `typeMismatch` trước validation. Với JSON, Jackson có cơ chế deserialize riêng; nếu JSON gửi một giá trị không chuyển được thành Integer, nó có thể dẫn tới `HttpMessageNotReadableException` thay vì `FieldError`. Không áp cùng kỳ vọng lỗi conversion cho hai đường input khác nhau.

### 5.5. Request DTO với nested list

~~~java
// src/main/java/com/example/errors/OrderRequest.java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

import java.util.ArrayList;
import java.util.List;

public class OrderRequest {

    @NotBlank(message = "{order.customer.required}")
    private String customerName;

    @NotEmpty(message = "{order.items.required}")
    private List<@Valid LineItemInput> items = new ArrayList<>();

    public OrderRequest() {}

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public List<LineItemInput> getItems() {
        return items;
    }

    public void setItems(List<LineItemInput> items) {
        this.items = items;
    }
}
~~~

`@Valid` trên phần tử list yêu cầu kiểm tra `LineItemInput.sku` và `LineItemInput.quantity`. Khi provider chuyển lỗi sang Spring BindingResult, nested paths thường là `items[0].sku`, `items[0].quantity`. `@NotEmpty` trên chính list phát hiện trường hợp không có dòng hàng.

Dùng kiểu `List<@Valid LineItemInput>` để khai báo cascade rõ ở element type. Với một DTO không dùng list, `@Valid` trên property nested object cũng tương tự. Không xem `@Valid` là một constraint độc lập — nó là chỉ dẫn cascade.

### 5.6. Controller: JSON, form, query và return

~~~java
// src/main/java/com/example/errors/OrderController.java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class OrderController {

    @InitBinder("orderForm")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "items[*].sku",
                "items[*].quantity");
        binder.setAutoGrowCollectionLimit(16);
    }

    @PostMapping(path = "/api/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> createJson(
            @Valid @RequestBody OrderRequest request) {

        return Map.of(
                "accepted", true,
                "itemCount", request.getItems().size());
    }

    @PostMapping(path = "/api/orders/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> createForm(
            @Valid @ModelAttribute("orderForm") OrderRequest form) {

        return Map.of(
                "accepted", true,
                "itemCount", form.getItems().size());
    }

    @GetMapping("/api/quotes")
    public String quote(
            @RequestParam(name = "units")
            @Min(value = 1, message = "{order.units.min}")
            int units) {

        return "units=" + units;
    }

    @GetMapping("/api/broken")
    @NotBlank
    public String brokenReturn() {
        return ""; // Cố tình sai hậu điều kiện của server.
    }
}
~~~

Không đặt `@Validated` cấp class trên controller: Spring MVC 6.1+ có built-in handler method validation. Thêm `@Validated` cấp class có thể chuyển sang AOP proxy và tạo loại exception khác; bài cần giữ ví dụ nhất quán với `HandlerMethodValidationException`.

`@InitBinder("orderForm")` dùng cho **form property binding**; `setAllowedFields` không phải bộ lọc JSON deserialization của `@RequestBody`. Trong production hãy dùng input DTO chỉ chứa những fields công khai, kiểm soát ownership và phân quyền ở service. Ở đây response thành công đơn giản để tập trung vào lỗi.

### 5.7. Một record biểu diễn mỗi issue

~~~java
// src/main/java/com/example/errors/ApiIssue.java
package com.example.errors;

import java.util.Map;

public record ApiIssue(
        String code,
        String path,
        String location,
        Integer parameterIndex,
        Map<String, Object> parameters,
        String message) {
}
~~~

`record` của Java 17 là một immutable carrier; Jackson trong Spring Boot 3.5 serialize các components thành JSON properties. Tên `parameters` chỉ chứa **metadata đã whitelist**. Không đặt `Object rejectedValue`, `Throwable cause` hoặc `Object[] arguments` vào record này.

`path` dùng `""` cho lỗi cấp object/cross-parameter nếu không có field xác định. `parameterIndex` có thể null khi lỗi không gắn với một parameter riêng. Với code dự án này, lỗi body và form đều có handler argument ở index 0, nên ghi được `parameterIndex=0`.

### 5.8. Advice: chuyển Spring errors thành ProblemDetail an toàn

~~~java
// src/main/java/com/example/errors/ValidationErrorAdvice.java
package com.example.errors;

import jakarta.validation.ConstraintViolation;
import org.springframework.core.MethodParameter;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestControllerAdvice
public class ValidationErrorAdvice {

    // Mã framework/constraint được quyết định công khai.
    private static final Set<String> PUBLIC_CODES = Set.of(
            "NotBlank", "NotNull", "NotEmpty",
            "Min", "Size", "typeMismatch");

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidObject(
            MethodArgumentNotValidException ex) {

        String location = ex.getParameter()
                .hasParameterAnnotation(ModelAttribute.class)
                ? "form" : "body";
        int parameterIndex =
                ex.getParameter().getParameterIndex();

        List<ApiIssue> issues = new ArrayList<>();

        // getAllErrors() bao gồm field lẫn object-level errors.
        for (ObjectError error :
                ex.getBindingResult().getAllErrors()) {

            String path = error instanceof FieldError field
                    ? field.getField() : "";

            issues.add(new ApiIssue(
                    publicCode(error.getCode()),
                    path,
                    location,
                    parameterIndex,
                    safeParameters(error),
                    safeMessage(error.getDefaultMessage())));
        }
        return problem(HttpStatus.BAD_REQUEST,
                "REQUEST_VALIDATION_FAILED", issues);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> invalidMethod(
            HandlerMethodValidationException ex) {

        // Hậu điều kiện lỗi là lỗi server: không tiết lộ contract.
        if (ex.isForReturnValue()) {
            return problem(HttpStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_CONTRACT_ERROR", List.of());
        }

        List<ApiIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            int index =
                    result.getMethodParameter().getParameterIndex();

            if (result instanceof ParameterErrors beanErrors) {
                // Nested errors trong @Valid DTO.
                for (ObjectError error : beanErrors.getAllErrors()) {
                    String path =
                            error instanceof FieldError field
                                    ? field.getField() : "";

                    issues.add(new ApiIssue(
                            publicCode(error.getCode()),
                            path,
                            "body",
                            index,
                            safeParameters(error),
                            safeMessage(error.getDefaultMessage())));
                }
                continue;
            }

            // Direct parameter constraints: @Min, @NotBlank, ...
            String basePath =
                    requestParameterName(result.getMethodParameter());
            String path = withContainerPath(basePath, result);

            for (MessageSourceResolvable error :
                    result.getResolvableErrors()) {

                issues.add(new ApiIssue(
                        publicCode(error.getCodes()),
                        path,
                        "query",
                        index,
                        safeParameters(result, error),
                        safeMessage(error.getDefaultMessage())));
            }
        }

        // Cross-parameter constraints: không gán nhầm vào 1 field.
        for (MessageSourceResolvable error :
                ex.getCrossParameterValidationResults()) {
            issues.add(new ApiIssue(
                    publicCode(error.getCodes()),
                    "",
                    "crossParameter",
                    null,
                    Map.of(),
                    safeMessage(error.getDefaultMessage())));
        }

        return problem(ex.getStatusCode(),
                "REQUEST_VALIDATION_FAILED", issues);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> invalidQueryType(
            MethodArgumentTypeMismatchException ex) {

        ApiIssue issue = new ApiIssue(
                "typeMismatch",
                ex.getName(),
                "query",
                ex.getParameter().getParameterIndex(),
                Map.of(),
                "Query parameter has an invalid type");

        // Không xuất ex.getValue() hoặc Throwable details.
        return problem(HttpStatus.BAD_REQUEST,
                "REQUEST_VALIDATION_FAILED", List.of(issue));
    }

    private static ResponseEntity<ProblemDetail> problem(
            HttpStatusCode status,
            String code,
            List<ApiIssue> issues) {

        ProblemDetail body = ProblemDetail.forStatus(status);
        boolean internal = status.is5xxServerError();

        body.setType(URI.create(internal
                ? "urn:problem:internal-contract"
                : "urn:problem:invalid-request"));
        body.setTitle(internal ? "Internal error" : "Invalid request");
        body.setDetail(internal
                ? "Server could not produce a valid result."
                : "Fix the listed fields.");
        body.setProperty("code", code);

        List<ApiIssue> sorted = issues.stream()
                .sorted(Comparator.comparing(ApiIssue::location)
                        .thenComparing(ApiIssue::path)
                        .thenComparing(ApiIssue::code))
                .toList();
        body.setProperty("issues", sorted);

        return ResponseEntity.status(status).body(body);
    }

    private static String safeMessage(String message) {
        return message == null || message.isBlank()
                ? "Invalid value" : message;
    }

    // Giữ mã tổng quát có hợp đồng; không xuất tên class/method.
    private static String publicCode(String code) {
        return code != null && PUBLIC_CODES.contains(code)
                ? code : "INVALID_VALUE";
    }

    private static String publicCode(String[] codes) {
        if (codes == null) {
            return "INVALID_VALUE";
        }
        // Spring cung cấp codes từ cụ thể đến tổng quát.
        for (int i = codes.length - 1; i >= 0; i--) {
            if (PUBLIC_CODES.contains(codes[i])) {
                return codes[i];
            }
        }
        return "INVALID_VALUE";
    }

    private static String requestParameterName(
            MethodParameter parameter) {

        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);

        if (annotation != null) {
            String explicit = annotation.name().isBlank()
                    ? annotation.value() : annotation.name();
            if (!explicit.isBlank()) {
                return explicit;
            }
        }

        String javaName = parameter.getParameterName();
        return javaName != null
                ? javaName
                : "arg" + parameter.getParameterIndex();
    }

    private static String withContainerPath(
            String path,
            ParameterValidationResult result) {

        if (result.getContainerIndex() != null) {
            return path + "[" + result.getContainerIndex() + "]";
        }
        Object key = result.getContainerKey();
        if (key != null) {
            // Chỉ cho phép key ngắn, dạng public identifier.
            String text = String.valueOf(key);
            return text.matches("[A-Za-z0-9_-]{1,40}")
                    ? path + "[" + text + "]"
                    : path + "[key]";
        }
        return path;
    }

    // FieldError/ObjectError có thể wrap ConstraintViolation
    // hoặc lỗi conversion; không được giả định unwrap luôn thành công.
    private static Map<String, Object> safeParameters(
            ObjectError error) {
        try {
            ConstraintViolation<?> violation =
                    error.unwrap(ConstraintViolation.class);
            return safeConstraintAttributes(violation);
        } catch (IllegalArgumentException unavailable) {
            return Map.of();
        }
    }

    private static Map<String, Object> safeParameters(
            ParameterValidationResult result,
            MessageSourceResolvable error) {
        try {
            ConstraintViolation<?> violation =
                    result.unwrap(error, ConstraintViolation.class);
            return safeConstraintAttributes(violation);
        } catch (IllegalArgumentException unavailable) {
            return Map.of();
        }
    }

    private static Map<String, Object> safeConstraintAttributes(
            ConstraintViolation<?> violation) {

        String kind = violation.getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName();
        Map<String, Object> attributes =
                violation.getConstraintDescriptor().getAttributes();
        Map<String, Object> safe = new LinkedHashMap<>();

        // Không xuất nguyên message, groups, payload hoặc regex.
        if ("Min".equals(kind)
                && attributes.get("value") instanceof Number min) {
            safe.put("minimum", min.longValue());
        }
        if ("Size".equals(kind)) {
            if (attributes.get("min") instanceof Number min) {
                safe.put("minLength", min.intValue());
            }
            if (attributes.get("max") instanceof Number max) {
                safe.put("maxLength", max.intValue());
            }
        }
        return safe;
    }
}
~~~

**Điều quan trọng về tính runnable:** file này nhắm **Spring Framework 6.2**. API `ParameterValidationResult.unwrap(error, ConstraintViolation.class)` có từ Spring 6.2; nếu compile với 6.1, cần điều chỉnh cách lấy metadata và không dùng API chưa tồn tại. `getParameterValidationResults()` là API nên dùng trong 6.2 thay cho một số phương thức đã deprecated. Các imports, kiểu `ApiIssue` và Spring Boot dependencies đã khai báo để ví dụ có thể biên dịch như một project đầy đủ.

**Giới hạn được làm rõ trong code:**
- `PUBLIC_CODES` là allowlist cho contract công khai; errors khác trở về `INVALID_VALUE`. Project thực nên mở rộng danh sách theo constraints đã đăng ký.
- `getDefaultMessage()` dùng để giữ thông báo đã được Bean Validation/Spring resolve theo locale. Nếu cần locale-specific Spring message resolution cho custom `MessageSourceResolvable`, có thể inject `MessageSource` và gọi `getMessage(resolvable,locale)`.
- `safeConstraintAttributes` chỉ công bố ngưỡng số học phù hợp, không serialize cả `ConstraintDescriptor`.
- `ParameterErrors` dùng `getAllErrors()` để giữ cả field/global errors.
- Cross-parameter errors được đặt `location=crossParameter` và `path=""`, không gán tùy tiện vào một argument.
- Lỗi return cố ý chỉ trả 500 với `issues=[]` và mã server tổng quát; trong hệ thống thật phải ghi log nội bộ an toàn để điều tra.
- Trong demo, direct method constraints chỉ có query parameter `units`, nên `location=query` là chính xác. Nếu thêm direct constraints ở `@PathVariable`, `@RequestHeader` hoặc body, phải **phân loại dựa trên annotation**, ví dụ qua `HandlerMethodValidationException.Visitor`, không giữ cứng `query` cho tất cả.
- Với `ParameterErrors`, demo đặt `location=body` vì DTO trực tiếp dùng JSON body. Nếu thêm method-validation form DTO hoặc multipart, cần xác định đúng annotation/argument source trong contract.
- `withContainerPath` sử dụng index/key sẵn có, đồng thời thay key lạ bằng placeholder để tránh đưa tùy ý một map key chứa ký tự nhạy cảm vào response.

### 5.9. Resource bundles để message có ngôn ngữ

**`src/main/resources/messages.properties`:**

~~~properties
order.customer.required=Customer name is required
order.items.required=At least one line item is required
order.sku.required=SKU is required
order.quantity.required=Quantity is required
order.quantity.min=Quantity must be at least {value}
order.units.min=Units must be at least {value}
~~~

**`src/main/resources/messages_vi.properties`:**

~~~properties
order.customer.required=Tên khách hàng không được trống
order.items.required=Cần ít nhất một dòng hàng
order.sku.required=Mã hàng không được trống
order.quantity.required=Số lượng là bắt buộc
order.quantity.min=Số lượng phải từ {value} trở lên
order.units.min=Số đơn vị phải từ {value} trở lên
~~~

Spring Boot có tích hợp application `MessageSource` với constraint message interpolation khi provider đã được cấu hình. `{value}` trong `@Min(value=1)` là constraint attribute do Bean Validation provider resolve, không phải một `MessageFormat {0}` thông thường. Để thay đổi locale theo request trong MVC, client có thể gửi `Accept-Language: vi` khi ứng dụng dùng locale resolver phù hợp.

## 6. Kiểm thử bằng MockMvc: đừng chỉ assert HTTP status

### 6.1. Bộ integration tests

~~~java
// src/test/java/com/example/errors/ValidationErrorAdviceTest.java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationErrorAdviceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonErrorsKeepCodeAndExactIndexedPaths() throws Exception {
        mvc.perform(post("/api/orders")
                .locale(Locale.ENGLISH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerName":"",
                      "items":[
                        {"sku":"PEN","quantity":0},
                        {"sku":"","quantity":2}
                      ]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("REQUEST_VALIDATION_FAILED"))
            .andExpect(jsonPath("$.issues.length()").value(3))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("customerName")))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("items[0].quantity")))
            .andExpect(jsonPath("$.issues[*].path",
                    hasItem("items[1].sku")));
    }

    @Test
    void minConstraintKeepsItsPublicThreshold() throws Exception {
        mvc.perform(post("/api/orders")
                .locale(Locale.ENGLISH)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"Lan",
                     "items":[{"sku":"PEN","quantity":0}]}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("Min"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("items[0].quantity"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("body"))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Quantity must be at least 1"));
    }

    @Test
    void formTypeMismatchKeepsIndexedFieldPath() throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", "Lan")
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("items[0].quantity"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("form"));
    }

    @Test
    void directQueryConstraintKeepsNameAndParameterIndex()
            throws Exception {
        mvc.perform(get("/api/quotes")
                .locale(Locale.ENGLISH)
                .param("units", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("Min"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("units"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"))
            .andExpect(jsonPath("$.issues[0].parameterIndex")
                    .value(0))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1));
    }

    @Test
    void malformedQueryNumberStillHasSafeError() throws Exception {
        mvc.perform(get("/api/quotes").param("units", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("units"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"));
    }

    @Test
    void invalidServerReturnDoesNotLeakInternals()
            throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("INTERNAL_CONTRACT_ERROR"))
            .andExpect(jsonPath("$.issues.length()").value(0));
    }

    @Test
    void validJsonAndValidQueryStillWork() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"Lan",
                     "items":[{"sku":"PEN","quantity":2}]}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemCount").value(1));

        mvc.perform(get("/api/quotes").param("units", "2"))
            .andExpect(status().isOk());
    }

    @Test
    void vietnameseMessageDoesNotChangeStableCode()
            throws Exception {
        mvc.perform(get("/api/quotes")
                .locale(Locale.forLanguageTag("vi"))
                .param("units", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("Min"))
            .andExpect(jsonPath("$.issues[0].parameters.minimum")
                    .value(1))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Số đơn vị phải từ 1 trở lên"));
    }
}
~~~

**Kỳ vọng:** 8 JUnit tests PASS (một test chứa hai requests hợp lệ). Đây là kết quả kỳ vọng dựa trên contract/code, không phải khẳng định Maven đã thực thi trong một môi trường build. Phần `jsonPath("$.issues.length()")` sử dụng JSONPath expression của Spring test, và các lỗi được advice sort trước khi serialize.

### 6.2. Chạy test và server

~~~bash
mvn test
mvn spring-boot:run
~~~

Ví dụ request JSON lỗi:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"customerName":"","items":[{"sku":"PEN","quantity":0}]}'
~~~

Có thể kiểm tra response HTTP 400 với `code` ổn định `REQUEST_VALIDATION_FAILED`, các issue paths và `minimum=1`. Việc JSON keys xuất hiện theo thứ tự nào không phải một contract nên client không được phụ thuộc vào thứ tự object properties; mảng `issues` đã được sort bởi application.

Nếu chạy trên PowerShell, chú ý cách quote JSON tùy shell. Khi test tự động, dùng `MockMvc` thay vì phụ thuộc lệnh `curl`/server.

## 7. Phân loại lỗi và giữ ngữ nghĩa HTTP

Không phải mọi lỗi có “validation” trong tên đều thuộc cùng trách nhiệm.

| Tình huống | Loại lỗi | HTTP thường phù hợp | Nên lộ metadata? |
| --- | --- | --- | --- |
| `@NotBlank` trên JSON DTO field | Input không hợp lệ | 400 | Code, path, message, params an toàn |
| `@Min` trên `@RequestParam` | Method parameter không hợp lệ | 400 | Tên query, parameterIndex, giới hạn |
| `typeMismatch` trong form DTO | Data binding | 400 | Code, path; không rejected value |
| Query number parse sai | Argument conversion | 400 | Tên tham số, code typeMismatch |
| JSON syntax lỗi | Deserialization | 400 | Mã `INVALID_JSON`, không raw body/parser trace |
| Required parameter thiếu | Resolution | 400 | Mã `MISSING_PARAMETER`, tên tham số công khai |
| Custom business invariant không thỏa | Domain validation | 400 hoặc 409/422 theo API contract | Mã nghiệp vụ ổn định |
| Constraint trên controller return value không thỏa | Lỗi server | 500 | Chỉ mã server, không lộ return value |
| Provider/configuration bị lỗi `ConstraintDeclarationException` | Bug/config server | 500 | Mã server tổng quát |

**Không biến mọi validation exception thành 400.** Spring `HandlerMethodValidationException` phân biệt lỗi **input (400)** và lỗi **return (500)** bằng `isForReturnValue()`/`getStatusCode()`. Nếu application advice luôn trả `ResponseEntity.badRequest()` cho loại exception này, nó có thể che giấu bug server và làm hỏng cả alerting lẫn contract HTTP.

Với domain rules, HTTP 422 đôi khi được dùng cho nội dung hợp lệ về cú pháp nhưng không đáp ứng nghiệp vụ; HTTP 409 cho xung đột trạng thái. Đây là lựa chọn thiết kế API, **không phải mã tự động của Jakarta Bean Validation**. Nhất quán và document contract còn quan trọng hơn việc ép một chuẩn mọi use case.

## 8. Những phần bổ sung quan trọng trong API production

### 8.1. Không bỏ sót object-level constraints

Một custom constraint có thể kiểm tra `startDate <= endDate` trên cả class. Nó có thể đưa lỗi vào `BindingResult#getGlobalErrors()` thay vì `getFieldErrors()`. Nếu chỉ duyệt field errors, bạn sẽ mất rule này.

Trong API, nên biểu diễn:

~~~json
{
  "code": "DATE_RANGE_INVALID",
  "path": "",
  "location": "body",
  "parameterIndex": 0,
  "parameters": {},
  "message": "End date must not be before start date"
}
~~~

Khi dùng mã tùy chỉnh như `DATE_RANGE_INVALID`, **đưa nó vào allowlist public codes** và thêm integration test. Nếu không, ví dụ `ValidationErrorAdvice` mặc định trả `INVALID_VALUE`. Không để field path trống bị hiểu là backend quên điền; contract nên nêu rõ đó là lỗi toàn object.

### 8.2. Multi-field constraints

Nếu rule áp dụng hai trường, có hai lựa chọn:
- Giữ một **object-level issue** với code riêng và một cấu trúc `relatedPaths` nếu cần.
- Trong `ConstraintValidatorContext`, chủ động gắn violation vào một hoặc nhiều fields nếu hợp đồng UX yêu cầu.

Đừng tự động tạo hai lỗi với cùng message ở cả hai fields chỉ vì constraint xem xét hai trường. Điều đó có thể khiến frontend hiển thị thừa và bộ đếm lỗi sai.

### 8.3. Validation groups

`@Validated(SomeGroup.class)` thay đổi tập constraints được kiểm tra. API error response **không cần** công bố tên Java group class ra ngoài. Chỉ cần mã, path, tham số công khai và message của violation thực sự phát sinh.

Nếu cùng một rule áp dụng cho Create/Update nhưng có message/giới hạn khác, test từng endpoint và từng group; đừng hard-code ngưỡng `minimum=1` cho mọi context. Trong ví dụ, ngưỡng được lấy từ `ConstraintDescriptor` đã phát sinh violation, nên thay đổi annotation sẽ được phản ánh đúng khi test chạy.

### 8.4. Container index và Map key

`ParameterValidationResult#getContainerIndex()` và `getContainerKey()` giúp xác định **phần tử nào** của method parameter container có lỗi. Không cố đoán index/key từ `MessageSourceResolvable#getDefaultMessage()`.

Khi Map key do client gửi có thể chứa email, token hoặc thông tin nhạy cảm, không echo nguyên key mà chưa có policy. Có thể:
- Chỉ cho key thuộc whitelist/public vocabulary.
- Thay key bằng ordinal/canonical identifier.
- Dùng `path` đã được chuẩn hóa với placeholder và thêm `containerIndex`/`containerKey` công khai khi an toàn.

Demo sử dụng `withContainerPath` theo kiểu key đơn giản; các hệ thống Map phức tạp cần parser và escaping riêng.

### 8.5. Thông báo và parameters không cùng một lớp dữ liệu

`MessageSourceResolvable#getArguments()` có thể chứa metadata/arguments để render message, nhưng **nó không tự trở thành contract `parameters` public**. Ngoài constraint attributes, còn có arguments của Spring message resolution, field labels, hay values tùy loại error. Đừng serialize toàn bộ args.

Mã mẫu dùng `ConstraintViolation#getConstraintDescriptor().getAttributes()` khi unwrap được và chỉ công bố `minimum`/`minLength`/`maxLength` từ các constraint được biết. Với conversion errors, `parameters={}` vì không có Jakarta descriptor. Nếu cần `expectedType="integer"`, tự thiết kế một whitelist theo DTO schema chứ không trả nguyên `Class<?>`/exception target type.

### 8.6. Localization của Spring MessageSource

Bean Validation message template có dạng:

~~~java
@Min(value=1, message="{order.quantity.min}")
~~~

File `messages_vi.properties` có thể chứa:

~~~properties
order.quantity.min=Số lượng phải từ {value} trở lên
~~~

Server interpolates thành message tiếng Việt, trong khi `code="Min"` và `parameters={"minimum":1}` không đổi. Điều này giúp frontend giữ cùng behavior khi locale thay đổi.

Với **binding errors** như `typeMismatch`, message có thể đi theo Spring `MessageSource` và `MessageCodesResolver`; đó là đường translation khác với Bean Validation. Để trải nghiệm đa ngữ hoàn chỉnh, thêm và test các keys typeMismatch/missing-parameter tương ứng. Với demo, code và path của lỗi typeMismatch được giữ, còn text chung có thể do Spring cung cấp hoặc do advice định nghĩa.

## 9. Vì sao không nên xuất nguyên `FieldError` hay `ConstraintViolation`?

### 9.1. Data leakage

Các object framework có thể giữ:
- Giá trị user đã gửi (`rejectedValue`, `invalidValue`, `getArgument()`).
- Full property path chứa key mang dữ liệu riêng.
- Bean/object names, Java class names, method parameter types.
- Raw error arguments và cause chains.
- Các attributes trong constraint descriptor như regex, group class, payload.

Nếu serialize trực tiếp, API schema có thể đổi theo framework version hoặc xuất dữ liệu nhạy cảm. Mục đích của public issue DTO là **chuyển dữ liệu thô thành ngữ nghĩa phù hợp cho client**.

### 9.2. Không nên ghi log tất cả values

Ngay cả ở logs nội bộ, không ghi raw form body/headers/rejected values nếu không có yêu cầu và chính sách bảo vệ dữ liệu. Ưu tiên: correlation ID, trace ID, API route, public issue code, path đã kiểm soát, số lượng issues, HTTP status. Với lỗi server cần debugging, lưu exception stack trace ở hệ thống log bảo mật, không trả nó cho client.

### 9.3. Dữ liệu không đáng tin cậy trong path và message

`path` có thể bao gồm Map key do client kiểm soát; `message` từ custom validators có thể chứa input được nối vào. Nếu frontend render trực tiếp như HTML, có nguy cơ XSS. UI phải escape output, server tránh chèn raw input vào messages, và các keys/path cần giới hạn/encode. **ProblemDetail không tự giải quyết XSS**; nó chỉ là một cấu trúc JSON.

## 10. Kết hợp ResponseEntityExceptionHandler và @ControllerAdvice

Trong Spring MVC, `ResponseEntityExceptionHandler` có sẵn các hook như:
- `handleMethodArgumentNotValid(...)`.
- `handleHandlerMethodValidationException(...)`.
- `handleTypeMismatch(...)`.
- `handleHttpMessageNotReadable(...)`.

Có thể **extend `ResponseEntityExceptionHandler`** rồi override đúng hook để xây `ProblemDetail` nhất quán. Cách này rất hữu ích nếu dự án có nhiều exception built-in cần chuẩn hóa, và còn hỗ trợ `MessageSource` cho `type/title/detail`. Ví dụ runnable dùng `@RestControllerAdvice` với ba `@ExceptionHandler` riêng để tập trung vào việc giữ metadata.

**Không trộn hai mô hình thiếu kiểm soát:** nếu class advice đã extend `ResponseEntityExceptionHandler`, nó được Spring đăng ký các exception handlers sẵn có. Viết thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` trong chính class đó có thể tạo **ambiguous exception mappings**. Chọn một con đường và test handler registration.

Spring `ProblemDetail` định nghĩa một bộ fields chuẩn, nhưng `issues` là extension do ta bổ sung. Nếu client chỉ hiểu RFC 9457 cơ bản, nó vẫn có thể đọc `status`/`title`/`detail`; client của ứng dụng có thể đọc thêm `issues`.

## 11. WebFlux có gì khác?

Tư duy giữ metadata giống nhau, nhưng các lớp exception và pipeline reactive khác:

- Với `@Valid @ModelAttribute` WebFlux, object-only validation thường tạo **`WebExchangeBindException`**, có `getBindingResult()` để đọc field/global errors.
- Với Spring WebFlux 6.1+ có direct method constraints, **`HandlerMethodValidationException`** cũng có thể xuất hiện. Nó chứa `ParameterValidationResult` tương tự, nhưng handler response phải hợp với WebFlux lifecycle.
- Với `@RequestBody` WebFlux, JSON được đọc qua `HttpMessageReader`/Jackson; không mặc định chuyển mọi conversion failure thành `FieldError`.
- Có thể dùng `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` của reactive stack hoặc `@RestControllerAdvice` với reactive-compatible signatures.
- Không bê nguyên `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` (Servlet MVC) vào app WebFlux.

Trong các ứng dụng trả `Mono<ResponseEntity<ProblemDetail>>`, hãy tạo dữ liệu response từ exception/validation metadata mà framework cung cấp, không block event-loop để lookup database trong exception handler. Với localization/trace metadata dùng reactive context phù hợp; không cho rằng `ThreadLocal` đi xuyên qua mọi boundary Reactor.

## 12. Checklist và các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Client chỉ thấy “Validation failed” | Backend bỏ code/path/details | Dùng issues có schema ổn định |
| UI không biết dòng hàng nào sai | Backend rút `items[0].quantity` còn `quantity` | Giữ nguyên indexed field path |
| Hai lỗi cùng field bị mất một | Backend dùng `Map<path,message>` ghi đè | Dùng `List<ApiIssue>` |
| Lỗi toàn object không xuất hiện | Chỉ duyệt `getFieldErrors()` | Dùng `getAllErrors()` và path rỗng cho global |
| `@Min` có code nhưng không có ngưỡng | Không giữ constraint metadata | Whitelist `value` thành `minimum` |
| API lộ group/payload/regex | Serialize toàn bộ `ConstraintDescriptor.attributes` | Chỉ lấy tham số public |
| API lộ input người dùng | Xuất `rejectedValue`/`getArgument()` | Không echo raw invalid values |
| `Min` bị hiển thị thành tên Java class | Xuất toàn bộ `getCodes()` | Chọn một public error code |
| Lỗi query `units=abc` không đi qua validator | Converter lỗi trước method validation | Xử lý `MethodArgumentTypeMismatchException` |
| JSON sai kiểu không sinh FieldError | Jackson báo lỗi deserialization | Xử lý `HttpMessageNotReadableException` riêng |
| Lỗi return bị trả 400 | Advice đánh đồng mọi `HandlerMethodValidationException` | Dùng `isForReturnValue()`/`getStatusCode()` |
| Locale thay đổi làm logic client hỏng | Client parse `message` | Branch theo `code` và `parameters` |
| `getContainerKey()` bị đưa ra nguyên dạng | Map key có thể chứa dữ liệu nhạy cảm | Canonicalize/whitelist keys |
| Một yêu cầu có nhiều vấn đề nhưng chỉ lấy lỗi đầu | Gọi `getFieldError()` một lần | Lấy toàn bộ errors và sort |
| `BindingResult` không xuất hiện đúng chỗ | Không đặt ngay sau validated argument | Sửa chữ ký handler; test framework flow |
| Source code chạy trên Spring 6.1 báo thiếu `unwrap` | API unwrap trên ParameterValidationResult mới ở 6.2 | Nâng lên 6.2 hoặc điều chỉnh mapper |
| WebFlux sử dụng advice MVC | Nhầm package servlet/reactive | Dùng exception handler đúng stack |

### Checklist trước khi public API

1. Đã định nghĩa `type`/`status`/response-level `code` và versioning strategy.
2. `issues[*].code` chỉ thuộc danh sách đã công bố, dùng được lâu dài.
3. `path` giữ chính xác nested property/index và quy ước cho object-level errors.
4. `location` phân biệt body/form/query/header/path/cross-parameter khi có.
5. `parameterIndex` được hiểu là zero-based, và tên request public có thể thay thế index khi API refactor.
6. `parameters` chỉ chứa dữ liệu public từ constraint attributes đã whitelist.
7. `message` đã giải quyết theo locale và không được client parse logic.
8. Không xuất raw invalid/rejected values, exception cause, stack trace hoặc internal class names.
9. Validation input giữ HTTP 400; return invalid giữ HTTP 500, không lộ internals.
10. Test cả JSON binding, form conversion, direct method constraint, object/global errors, localization và các loại lỗi khác.
11. Có policy về số lượng issues tối đa, thứ tự sắp xếp, duplicate issues và path escaping.
12. Viết regression tests cho contract của error responses trước khi nâng Spring/Jakarta provider.

## 13. Tài liệu tham khảo

- Spring Framework 6.2 — Spring MVC Validation, `MethodArgumentNotValidException` và `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error Responses, `ProblemDetail` và RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — `ObjectError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — `ParameterValidationResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 — `ParameterErrors` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring Framework 6.2 — `HandlerMethodValidationException` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Validation 3.1 specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
