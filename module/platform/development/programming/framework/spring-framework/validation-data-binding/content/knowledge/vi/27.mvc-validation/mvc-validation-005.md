# Method validation tích hợp từ Spring Framework 6.1 trong Spring MVC

## 1. Spring MVC 6.1 đã thay đổi điều gì?

Trước Spring Framework 6.1, một cách thường dùng để kiểm tra ràng buộc trên **tham số phương thức controller** là thêm `@Validated` ở cấp class, để Spring AOP chặn lời gọi method và kích hoạt Jakarta Bean Validation. Từ **Spring Framework 6.1**, Spring MVC có **built-in method validation** dành cho các handler `@RequestMapping`. Cơ chế này nằm trong quy trình xử lý request của Spring MVC, **không cần proxy AOP để kiểm tra chính các handler methods**.

Ví dụ handler:

~~~java
@GetMapping("/codes")
public String code(
        @RequestParam @NotBlank String prefix,
        @RequestParam @Min(1) int number) {
    return prefix + "-" + number;
}
~~~

Với Spring MVC 6.1+ được cấu hình Bean Validation provider phù hợp:

- `GET /codes?prefix=INV&number=3` hợp lệ: method có thể chạy và trả `INV-3`.
- `GET /codes?prefix=&number=3` vi phạm `@NotBlank` trên tham số `prefix`.
- `GET /codes?prefix=INV&number=0` vi phạm `@Min(1)` trên tham số `number`.
- Các violation do **MVC built-in method validation** thường được biểu diễn bằng `HandlerMethodValidationException`. Lỗi đối số đầu vào tương ứng với **HTTP 400**.

Cũng có thể khai báo constraint **trên method để kiểm tra giá trị trả về**:

~~~java
@GetMapping("/broken")
@NotBlank
public String broken() {
    return "";
}
~~~

Ở đây body method đã chạy và trả chuỗi rỗng, sau đó Spring MVC kiểm tra hậu điều kiện. Violation trên **return value** được biểu diễn bằng `HandlerMethodValidationException` với **HTTP 500**, vì đây là lỗi phía server chứ không phải lỗi input của khách hàng.

**Điểm mấu chốt:** `@Valid` và `@Validated` trên một DTO thường kích hoạt kiểm tra đối tượng riêng lẻ; constraint **trực tiếp** như `@NotBlank`, `@Min`, `@NotNull` trên tham số phương thức (hoặc constraint trên return method) kích hoạt **method validation**. Khi cả hai tồn tại, method validation bao trùm luôn các ràng buộc lồng nhau của `@Valid`.

Trong bài này “Spring Framework 6.1+” chỉ cơ chế có từ 6.1 và tiếp tục tồn tại trong Spring Framework 6.2. Ví dụ runnable dùng **Java 17 / Spring Boot 3.5.7 / Spring Framework 6.2**, với annotation và package `jakarta.validation.*`. Không trộn mã Javax Validation của Spring Boot 2.x vào ví dụ.

## 2. Phân biệt hai đường validation trong Spring MVC

Từ 6.1, cùng một controller có thể gặp **hai kiểu validation khác nhau**. Chọn đúng đường sẽ quyết định loại exception, cách lấy thông tin lỗi và cách xử lý HTTP.

| Trường hợp | Cơ chế thường áp dụng | Exception thường gặp | HTTP mặc định |
| --- | --- | --- | --- |
| `@Valid @RequestBody OrderInput`, không có direct method constraint nào khác | Kiểm tra riêng request object | `MethodArgumentNotValidException` | 400 |
| `@Valid @ModelAttribute OrderForm`, không có `BindingResult` ngay sau và không có direct method constraint | Kiểm tra riêng model attribute | `MethodArgumentNotValidException` | 400 |
| `@RequestParam @Min(1) int quantity` | Built-in **method validation** | `HandlerMethodValidationException` | 400 |
| `@RequestHeader @NotBlank String token` | Built-in method validation | `HandlerMethodValidationException` | 400 |
| `@RequestParam @Min(1) int priority` cùng `@Valid @RequestBody OrderInput body` | Built-in method validation, gồm nested validation của `body` | `HandlerMethodValidationException` | 400 |
| `@NotBlank` trên method trả về `String` | Built-in return-value method validation | `HandlerMethodValidationException` | 500 |
| `@RequestParam int quantity` nhận chuỗi `abc` | Type conversion/binding **trước validation** | Có thể `MethodArgumentTypeMismatchException` | 400 |
| `@RequestParam(required=true) String name` bị thiếu | Request argument resolution, **trước validation** | Có thể `MissingServletRequestParameterException` | 400 |

Không xem bảng là “mọi annotation đều gây đúng exception đó”. Điều kiện kích hoạt khác nhau theo chữ ký handler, vị trí `Errors`/`BindingResult`, sự hiện diện của provider và cơ chế tích hợp. Bảng phản ánh các trường hợp Spring MVC 6.1/6.2 thông dụng.

### 2.1. Vì sao `@Valid` một mình không kích hoạt method validation?

`@Valid` thuộc Jakarta Validation là chú thích **cascade**, yêu cầu kiểm tra constraints của một object lồng nhau. Nó **không phải `@Constraint`**. Trái lại, `@NotNull`, `@NotBlank`, `@Min` là các constraint annotations.

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderInput body) {
    // Một request object được validate riêng.
}
~~~

Nếu không có direct method constraints khác, Spring MVC có thể validate `body` qua cơ chế argument resolver; khi object có lỗi mà không có `Errors`/`BindingResult` ngay sau, `MethodArgumentNotValidException` thường được ném ra.

Nếu khai báo thêm:

~~~java
@PostMapping("/orders")
public void create(
        @RequestParam @Min(1) int priority,
        @Valid @RequestBody OrderInput body) {
    // Phải kiểm tra cả direct constraint và nested object.
}
~~~

`@Min(1)` làm method validation trở nên cần thiết. **Method validation thay thế đường object-only** vì nó bao phủ cả direct constraint trên `priority` và nested constraints trong `body`. Khi vi phạm, Spring MVC dùng `HandlerMethodValidationException`, không phải tự động có hai exception cho hai tham số.

### 2.2. `@NotNull` và “required” không giống nhau hoàn toàn

~~~java
@RequestParam(required = true) String name
~~~

Trong trường hợp tham số request không tồn tại, Spring MVC có thể báo lỗi ngay ở **argument resolution**, trước khi Bean Validation nhận giá trị. Còn:

~~~java
@RequestParam(required = false) @NotNull String name
~~~

cho phép resolver tạo giá trị `null` nhưng ràng buộc `@NotNull` sẽ phát hiện nó khi method validation chạy. Hai lựa chọn có thể đều dẫn đến HTTP 400, **nhưng đường xử lý, exception và nội dung lỗi không nhất thiết giống nhau**.

Tương tự, `@Valid` không tự cấm `null`. Nếu handler thực sự chấp nhận `null` ở giai đoạn resolution, hãy dùng constraint phù hợp như `@NotNull` khi cần. Với `@RequestBody(required=true)`, thiếu body có thể bị xử lý trước khi validation diễn ra.

## 3. Luồng xử lý bên trong MVC

~~~text
HTTP request
  |
  v
DispatcherServlet
  |
  v
HandlerMapping chọn @RequestMapping method
  |
  v
HandlerAdapter phân giải method arguments
  |  - @RequestParam / @PathVariable / @RequestHeader
  |  - @RequestBody qua HttpMessageConverter (Jackson)
  |  - @ModelAttribute qua WebDataBinder
  |  - Chuyển kiểu, kiểm tra missing argument và lỗi binding
  |
  +--> Nếu chỉ có @Valid cho command object:
  |       argument resolver có thể validate object riêng lẻ
  |       và ném MethodArgumentNotValidException
  |
  v
Nếu method yêu cầu built-in method validation:
  HandlerMethodValidator kiểm tra direct parameters
  và nested constraints được khai báo qua @Valid
  |
  +--> Violation ở argument KHÔNG được xử lý tại chỗ
  |       -> HandlerMethodValidationException (400)
  |
  v
Gọi thân controller method
  |
  v
Nếu có return-value constraints: kiểm tra giá trị trả về
  |
  +--> Violation ở return
  |       -> HandlerMethodValidationException (500)
  |
  v
Response rendering: String/JSON/ModelAndView...
~~~

Sơ đồ là mô hình khái quát cho trường hợp không có custom resolver/interceptor. Spring xử lý chi tiết từng loại argument theo cơ chế phù hợp trước khi method được gọi; method validation không thay thế **JSON deserialization**, **data binding**, **type conversion**, hay **kiểm tra authorization**.

Trong Spring Framework 6.1+, thành phần xử lý method validation ở MVC là `HandlerMethodValidator`, còn đối tượng lỗi là `HandlerMethodValidationException`. `HandlerMethodValidationException` triển khai `MethodValidationResult`: có dữ liệu về method, target, từng tham số, lỗi cross-parameter và cờ cho biết violation thuộc return.

So sánh với Spring AOP method validation:

- Spring MVC built-in xử lý **handler methods** như một phần của dispatching.
- Spring AOP có `MethodValidationPostProcessor`, thường dùng cho các **service beans** có `@Validated` cấp class và lời gọi qua proxy.
- AOP service validation thường ném `jakarta.validation.ConstraintViolationException` theo mặc định, hoặc `MethodValidationException` nếu cấu hình adaptation. **Không đồng nhất** hai loại đó với `HandlerMethodValidationException` của MVC.
- Tự gọi `this.serviceMethod(...)` trong một service có thể bỏ qua Spring proxy; MVC dispatch không dựa trên self-invocation để kích hoạt built-in handler validation.

## 4. Điều kiện và cách kích hoạt built-in method validation

Để hoạt động theo cơ chế MVC mới, cần:

1. Ứng dụng dùng **Spring Framework 6.1 trở lên** với Spring MVC `@RequestMapping` controllers.
2. Có Jakarta Bean Validation provider phù hợp (ví dụ Hibernate Validator). Trong Spring Boot 3.x, dùng `spring-boot-starter-validation`.
3. Có **constraint trực tiếp trên parameter của handler** như `@Min`, `@NotBlank`, hoặc constraint trên **return value** của method. `@Valid` đơn thuần không phải trigger này.
4. **Bỏ `@Validated` ở cấp class controller** khi muốn dùng built-in MVC method validation. Giữ annotation cấp class sẽ khiến method validation đi theo đường **AOP proxy**, trái với mục đích migration.
5. Chữ ký handler và request arguments hợp lệ về type/binding để tới được bước method validation. Nếu conversion thất bại từ trước, sẽ gặp exception khác.

Ví dụ đúng cho cơ chế mới:

~~~java
@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping("/greet")
    public String greet(@RequestParam @NotBlank String name) {
        return "Hello " + name;
    }
}
~~~

**Không thêm `@Validated` trên `ApiController`**. Lệnh `@RestController` chứa chức năng `@Controller` và `@ResponseBody`; nó không phải annotation tự kích hoạt constraint, nhưng phù hợp để khai báo handler REST.

Ví dụ dễ gây nhầm khi nâng cấp:

~~~java
@RestController
@Validated // Cơ chế AOP class-level, không phải MVC built-in.
class LegacyController {
    @GetMapping("/greet")
    String greet(@RequestParam @NotBlank String name) {
        return "Hello " + name;
    }
}
~~~

Khi nâng từ Spring 6.0 lên 6.1+, cần xem lại mục tiêu sử dụng `@Validated`: nếu annotation chỉ được thêm để kiểm tra direct method constraints, hãy cân nhắc **xóa ở cấp class** và chuyển handler sang cơ chế tích hợp. Sau khi xóa, **kiểm tra lại exception handlers và validation groups**; không giả định toàn bộ hành vi cũ giữ nguyên.

## 5. Dự án Spring Boot 3.5.7 đầy đủ, chạy được

Ví dụ triển khai cả hai đường validation, return validation, và trường hợp `BindingResult` hoạt động cạnh direct constraints. Dùng **Java 17**, Maven và Spring Boot 3.5.7.

### 5.1. Cấu trúc tệp

~~~text
pom.xml
src/main/java/com/example/mvcvalidation/
  MvcValidationApplication.java
  OrderInput.java
  OrderController.java
src/test/java/com/example/mvcvalidation/
  OrderControllerTest.java
~~~

Không cần database, không cần tự khai báo `MethodValidationPostProcessor` và không cần `spring-boot-starter-aop` chỉ để kiểm tra handler qua MVC built-in.

### 5.2. Maven

~~~xml
<!-- pom.xml -->
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
    <artifactId>mvc-method-validation</artifactId>
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

`spring-boot-starter-web` hỗ trợ Spring MVC, JSON deserialization và embedded server; `spring-boot-starter-validation` đưa Jakarta Validation implementation vào classpath; `spring-boot-starter-test` hỗ trợ JUnit 5 và `MockMvc`. Không khai báo `@EnableWebMvc` để giữ cấu hình MVC của Spring Boot mặc định.

### 5.3. Ứng dụng

~~~java
// src/main/java/com/example/mvcvalidation/MvcValidationApplication.java
package com.example.mvcvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcValidationApplication.class, args);
    }
}
~~~

### 5.4. DTO dùng chung cho JSON và form

~~~java
// src/main/java/com/example/mvcvalidation/OrderInput.java
package com.example.mvcvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderInput {

    @NotBlank(message = "Mã hàng không được trống")
    private String productCode;

    @NotNull(message = "Số lượng là bắt buộc")
    @Min(value = 1, message = "Số lượng tối thiểu là 1")
    private Integer quantity;

    public OrderInput() {
    }

    public String getProductCode() {
        return productCode;
    }

    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

DTO có public no-args constructor/getter/setter để Jackson đọc JSON và `WebDataBinder` xử lý HTML form. Trong dự án thực, input DTO chỉ nên chứa các field được phép nhận từ client, không bind trực tiếp vào entity có property nhạy cảm.

### 5.5. Controller: năm tình huống trong cùng một class

~~~java
// src/main/java/com/example/mvcvalidation/OrderController.java
package com.example.mvcvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class OrderController {

    // 1. Direct method parameter constraints.
    @GetMapping("/codes")
    public String code(
            @RequestParam @NotBlank String prefix,
            @RequestParam @Min(1) int serial) {
        return prefix + "-" + serial;
    }

    // 2. Return-value method constraint.
    @GetMapping("/broken")
    @NotBlank(message = "Kết quả không được để trống")
    public String broken() {
        return ""; // Cố tình sai để quan sát lỗi HTTP 500.
    }

    // 3. Chỉ validate một request DTO: object-only validation.
    @PostMapping(
            path = "/orders/object",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public String objectOnly(@Valid @RequestBody OrderInput input) {
        return input.getProductCode();
    }

    // 4. Có direct constraint, MVC method validation bao gồm @Valid DTO.
    @PostMapping(
            path = "/orders/method",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public String withMethodValidation(
            @RequestParam @Min(1) int priority,
            @Valid @RequestBody OrderInput input) {
        return input.getProductCode() + ":" + priority;
    }

    // 5. BindingResult ngay sau @ModelAttribute.
    @PostMapping(
            path = "/orders/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public String formWithLocalErrors(
            @RequestParam @Min(1) int priority,
            @Valid @ModelAttribute("orderInput") OrderInput input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "errors:" + errors.getErrorCount();
        }
        return "ok:" + input.getProductCode();
    }
}
~~~

**Không có `@Validated` cấp class** trên `OrderController`. Đây là chủ đích của ví dụ.

Đọc lần lượt:

- `GET /api/codes`: `@NotBlank` và `@Min` là direct constraints trên method parameters. Khi sai và không có `BindingResult` thích hợp, Spring MVC tạo `HandlerMethodValidationException` (400).
- `GET /api/broken`: method trả `""`, constraint `@NotBlank` trên method thất bại ở **return value**; exception là `HandlerMethodValidationException` với status 500.
- `POST /api/orders/object`: chỉ `@Valid @RequestBody`, không có direct method constraint. Khi `OrderInput` sai, Spring MVC thường ném `MethodArgumentNotValidException`.
- `POST /api/orders/method`: có `@Min(1)` trực tiếp trên `priority`; vì vậy method validation kiểm tra cả `priority` lẫn nested constraints của `OrderInput`, báo `HandlerMethodValidationException`.
- `POST /api/orders/form`: có direct constraint `@Min(1)`, nhưng `BindingResult` được đặt **ngay sau `@ModelAttribute`**. Nếu chỉ lỗi bên trong `OrderInput`, method vẫn có thể được gọi để xử lý `errors`. Nếu `priority` cũng sai, method validation ném exception vì **không có `Errors` ngay sau tham số `priority`**.

`BindingResult` trong form handler **không xử lý lỗi của toàn bộ method** theo kiểu global. Nó chỉ gắn với tham số model attribute ngay trước nó. Quy tắc này đặc biệt quan trọng khi handler có nhiều object và direct parameter constraints.

### 5.6. MockMvc integration test

~~~java
// src/test/java/com/example/mvcvalidation/OrderControllerTest.java
package com.example.mvcvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validDirectParameters() throws Exception {
        mvc.perform(get("/api/codes")
                .param("prefix", "INV")
                .param("serial", "3"))
            .andExpect(status().isOk())
            .andExpect(content().string("INV-3"));
    }

    @Test
    void directParameterViolationsUseMvcMethodValidation()
            throws Exception {
        mvc.perform(get("/api/codes")
                .param("prefix", " ")
                .param("serial", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());
                assertFalse(ex.isForReturnValue());
                assertFalse(ex.getParameterValidationResults().isEmpty());
            });
    }

    @Test
    void invalidReturnIsServerError() throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());
                assertTrue(ex.isForReturnValue());
            });
    }

    @Test
    void objectOnlyValidationHasArgumentException()
            throws Exception {
        mvc.perform(post("/api/orders/object")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productCode":"","quantity":2}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException()));
    }

    @Test
    void methodConstraintAlsoValidatesNestedDto()
            throws Exception {
        mvc.perform(post("/api/orders/method")
                .param("priority", "1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productCode":"","quantity":2}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    HandlerMethodValidationException.class,
                    result.getResolvedException()));
    }

    @Test
    void bindingResultHandlesOnlyItsOwnArgument()
            throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("priority", "1")
                .param("productCode", "")
                .param("quantity", "2"))
            .andExpect(status().isOk())
            .andExpect(content().string("errors:1"));
    }

    @Test
    void otherInvalidMethodParameterStillThrows()
            throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("priority", "0")
                .param("productCode", "")
                .param("quantity", "2"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    HandlerMethodValidationException.class,
                    result.getResolvedException()));
    }
}
~~~

Test dùng Java 17 **text blocks** cho JSON. Các assert quan trọng không chỉ nhìn status HTTP mà còn xác định **đúng loại exception** và đối với return, `ex.isForReturnValue()` là `true`.

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

Kết quả **kỳ vọng**: 7 test PASS với cấu hình mặc định đã nêu. Cụ thể: direct arguments hợp lệ trả 200; invalid direct arguments trả 400/`HandlerMethodValidationException`; return invalid trả 500; object-only invalid trả 400/`MethodArgumentNotValidException`; mixed validation trả 400/`HandlerMethodValidationException`; `BindingResult` cho phép handler xử lý lỗi của form; lỗi method parameter khác vẫn trả 400. Log Maven/Surefire không được ghi cứng vì phụ thuộc môi trường thực thi. Các case đã được rà soát về API và hành vi dự kiến, nhưng phần trình bày không khẳng định đã chạy Maven thực tế.

Để chạy HTTP server và thử thủ công:

~~~bash
mvn spring-boot:run
~~~

Sau đó:

~~~bash
curl -i "http://localhost:8080/api/codes?prefix=INV&serial=3"
curl -i "http://localhost:8080/api/codes?prefix=&serial=0"
curl -i "http://localhost:8080/api/broken"
~~~

Request hợp lệ trả body `INV-3`; request thứ hai nhận 400; request thứ ba nhận 500. Nội dung body lỗi là quyết định của cơ chế error response và cấu hình ứng dụng, có thể bị Spring Boot/ErrorAttributes/`@ControllerAdvice` tùy biến, nên không cố định JSON lỗi khi chỉ kiểm tra semantics.

## 6. Tìm hiểu `HandlerMethodValidationException`

Class `org.springframework.web.method.annotation.HandlerMethodValidationException` được thêm từ **Spring Framework 6.1**. Nó mang dữ liệu lỗi đã được Spring chuyển thành abstraction tiện dùng cho controller layer, thay vì chỉ cung cấp raw `Set<ConstraintViolation<?>>`.

Các API cần biết:

| API | Ý nghĩa |
| --- | --- |
| `getStatusCode()` | 400 cho validation lỗi ở input; 500 cho return-value violation theo cơ chế này |
| `isForReturnValue()` | `true` nếu vi phạm return value; `false` nếu vi phạm tham số |
| `getMethod()` | Java `Method` đã được kiểm tra |
| `getTarget()` | Target của method invocation |
| `getParameterValidationResults()` | Danh sách lỗi theo từng tham số/result |
| `getCrossParameterValidationResults()` | Lỗi ràng buộc liên tham số, nếu có |
| `visitResults(Visitor)` | Phân loại lỗi theo annotation loại tham số: request parameter, model attribute, request body, v.v. |

**Không dựa vào `getMessage()` rồi parse chuỗi để xác định field**. Message là mô tả cho con người, có thể được địa phương hóa, thay đổi theo version/provider. Dùng metadata của `ParameterValidationResult` và `ParameterErrors` để đưa lỗi về đúng input field.

### 6.1. `ParameterValidationResult` cho direct constraints

Đối với `@RequestParam @Min(1) int priority`, một `ParameterValidationResult` chứa tham số và tập lỗi có thể đọc bằng:

~~~java
// Đoạn minh họa, giả sử đã bắt HandlerMethodValidationException ex:
for (var result : ex.getParameterValidationResults()) {
    int parameterIndex = result.getMethodParameter().getParameterIndex();
    var resolvableErrors = result.getResolvableErrors();

    // parameterIndex và error codes dùng để xây response an toàn.
}
~~~

Ở đây `getResolvableErrors()` là danh sách `MessageSourceResolvable`; có error codes và arguments để resolve bản dịch bằng `MessageSource`. Khi đối tượng là collection/map lồng nhau, `ParameterValidationResult` có thêm `getContainer()`, `getContainerIndex()` hoặc `getContainerKey()` tùy loại phần tử bị lỗi. Không cố suy ra index/key bằng tách chuỗi message.

### 6.2. `ParameterErrors` cho object lồng nhau

Khi lỗi đến từ một DTO có `@Valid`, loại kết quả có thể là `ParameterErrors` (subclass của `ParameterValidationResult` và triển khai interface `Errors`):

~~~java
// Đoạn minh họa trong bộ xử lý result:
if (result instanceof org.springframework.validation.method.ParameterErrors nested) {
    for (var fieldError : nested.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();

        // Ví dụ: field="productCode", code="NotBlank".
    }
}
~~~

Đừng gắn cùng một xử lý cho tất cả results: direct parameter violation không nhất thiết có `FieldError`, trong khi nested object validation có thể có. Nguyên tắc là giữ dữ liệu lỗi theo **tham số**, sau đó phân biệt direct errors và nested field errors.

### 6.3. Visitor để xử lý theo loại tham số

Spring cung cấp `HandlerMethodValidationException.Visitor` để dispatch từng nhóm `ParameterValidationResult` theo annotation mà controller sử dụng. Đây là API phù hợp nếu một hệ thống có nhiều kiểu input:

~~~java
// Đoạn minh họa trong exception handler, với biến ex đã tồn tại.
// Imports:
// org.springframework.web.bind.annotation.RequestParam
// org.springframework.web.bind.annotation.ModelAttribute
// org.springframework.validation.method.ParameterValidationResult
// org.springframework.validation.method.ParameterErrors

ex.visitResults(new HandlerMethodValidationException.Visitor() {

    @Override
    public void requestParam(
            RequestParam annotation, ParameterValidationResult result) {
        // result.getMethodParameter(), result.getResolvableErrors()
    }

    @Override
    public void modelAttribute(
            ModelAttribute annotation, ParameterErrors errors) {
        // errors.getFieldErrors()
    }

    @Override
    public void other(ParameterValidationResult result) {
        // Các kiểu không có callback riêng hoặc fallback.
    }
});
~~~

Visitor có thêm callback cho những loại annotation như `@RequestHeader`, `@PathVariable`, `@RequestBody`, `@RequestPart`. Các phương thức nhận annotation có thể nhận giá trị `null` tùy cách Spring phân loại tham số. Đoạn minh họa trên không tự tạo response; mục đích là giới thiệu API để tách lỗi theo đúng nguồn nhập liệu.

**Cross-parameter constraints** có thể sinh lỗi không gắn với một tham số đơn; kiểm tra thêm `getCrossParameterValidationResults()`, thay vì chỉ đọc `getParameterValidationResults()`.

## 7. Xử lý lỗi HTTP với `@ControllerAdvice`

Ứng dụng thực nên có **một hợp đồng lỗi ổn định**. Nhưng đừng biến mọi validation failure thành HTTP 400:

- Nếu **client gửi tham số không hợp lệ**, 400 thường đúng.
- Nếu **controller trả dữ liệu vi phạm return contract**, đây thường là bug hoặc lỗi server; giữ 500, ghi log an toàn và tránh đưa chi tiết nội bộ vào response.
- Nếu lỗi xảy ra trước method validation do JSON syntax, conversion hoặc required parameter, exception khác cần được xử lý qua hệ thống exception resolution tương ứng.

### 7.1. Một `@RestControllerAdvice` tùy chọn

Ví dụ sau là **thành phần tùy chọn**, không phải file bắt buộc để chạy bộ test tối giản ở mục 5. Nếu thêm vào ứng dụng, nó thay đổi body lỗi nhưng vẫn giữ status tương ứng.

~~~java
// src/main/java/com/example/mvcvalidation/ApiValidationAdvice.java
package com.example.mvcvalidation;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> onMethod(
            HandlerMethodValidationException ex) {

        HttpStatusCode status = ex.getStatusCode();
        String detail = ex.isForReturnValue()
                ? "Kết quả phía server vi phạm hợp đồng."
                : "Tham số yêu cầu không hợp lệ.";

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(status, detail);

        if (!ex.isForReturnValue()) {
            var indexes = ex.getParameterValidationResults().stream()
                    .map(r -> r.getMethodParameter().getParameterIndex())
                    .distinct()
                    .toList();
            problem.setProperty("parameterIndexes", indexes);
        }

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> onArgument(
            MethodArgumentNotValidException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                ex.getStatusCode(), "Dữ liệu trong đối tượng không hợp lệ.");

        var fields = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField())
                .distinct()
                .toList();
        problem.setProperty("fields", fields);

        return ResponseEntity.status(ex.getStatusCode()).body(problem);
    }
}
~~~

Điểm tốt của ví dụ:
- Dùng `ex.getStatusCode()` để **giữ khác biệt 400/500**.
- Không trả raw input, exception stack trace hay provider metadata nhạy cảm.
- Lỗi return có thông điệp tổng quát; lỗi input có thể liệt kê index tham số và field để client sửa.

Trong dự án lớn, có thể **extend `ResponseEntityExceptionHandler`** và override các phương thức xử lý phù hợp, thay vì tạo nhiều handler trùng nhau. Nếu đã extend class này, không đồng thời định nghĩa các `@ExceptionHandler` trùng loại exception trong cùng advice gây ambiguity. `ProblemDetail` và `MessageSource` hỗ trợ biểu diễn lỗi có cấu trúc, localization và chi tiết nhất quán.

### 7.2. Địa phương hóa thông điệp

`MethodArgumentNotValidException` có `BindingResult` với `FieldError`; `HandlerMethodValidationException` có `ParameterValidationResult#getResolvableErrors()` và `ParameterErrors`. Các đối tượng này liên quan `MessageSourceResolvable`, cho phép giải mã error codes theo `MessageSource` và locale.

Không ghép `constraint.getMessage()` hoặc `exception.getMessage()` vào một JSON tùy tiện rồi hy vọng đồng nhất. Thiết kế response có:
- Mã lỗi ổn định (ví dụ `INVALID_ARGUMENT`).
- Tên hoặc vị trí tham số phù hợp.
- Tên field nếu là nested object.
- Message đã được localize, tránh leak rejected values.
- Không tiết lộ chi tiết của return-value violation ra bên ngoài.

Với ứng dụng có client công khai, cân nhắc dùng cấu trúc `ProblemDetail` theo RFC 9457 cùng cơ chế error handling của Spring. Chuỗi `title`, `detail` và các properties mở rộng nên có contract rõ ràng để client không phải parse ngôn ngữ tự nhiên.

## 8. `BindingResult` và `Errors` bên cạnh method validation

Đây là điểm thay đổi rất thực tế khi nâng cấp từ validation từng argument sang validation toàn method. Một handler có thể được gọi **ngay cả khi có validation errors**, với điều kiện **mọi** lỗi đều thuộc các method arguments có `Errors` hoặc `BindingResult` **ngay sau** trong chữ ký.

Ví dụ:

~~~java
@PostMapping("/preview")
public String preview(
        @RequestParam @Min(1) int priority,
        @Valid @ModelAttribute("orderInput") OrderInput form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "form-invalid";
    }
    return "ok";
}
~~~

Giải thích:

- `priority` có direct constraint `@Min(1)`, vì vậy MVC kích hoạt method validation.
- `form` có `@Valid`, được kiểm tra nested constraints.
- `BindingResult` nằm **ngay sau `form`**, nên controller có thể xử lý lỗi của chính form đó.
- Nếu `priority=1` hợp lệ nhưng `form.productCode` trống, handler có thể được gọi và `errors.hasErrors()` là `true`.
- Nếu `priority=0` vi phạm direct constraint, không có `Errors` ngay sau `priority` để xử lý lỗi đó tại chỗ; Spring MVC ném `HandlerMethodValidationException`.

Không đặt `BindingResult` ở cuối method cách xa đối tượng được validate; Spring cần quan hệ adjacency rõ ràng. Nhiều form objects cần nhiều `BindingResult` tương ứng. Không dùng một `BindingResult` cho mọi đối số scalar.

**Không áp dụng quy tắc trên một cách mù quáng với return-value constraints.** Return validation xảy ra sau khi handler chạy và không thể “được xử lý tại chỗ” bằng `BindingResult` của một input argument trước đó.

## 9. Migration từ Spring Framework 6.0 lên 6.1+

### 9.1. Trước nâng cấp: controller dùng AOP proxy

Trong nhiều codebase cũ:

~~~java
@RestController
@Validated
class LegacyOrderController {

    @GetMapping("/orders")
    String list(@RequestParam @Min(1) int limit) {
        return "count=" + limit;
    }
}
~~~

Lúc này class-level `@Validated` khiến method validation có thể chạy thông qua Spring AOP (khi có `MethodValidationPostProcessor` và proxy thích hợp). Lỗi từ AOP thường thuộc nhóm `ConstraintViolationException` thay vì `HandlerMethodValidationException`. Việc ánh xạ HTTP status khi đó phụ thuộc exception handlers, không nên tự giả định luôn là 400.

### 9.2. Sau nâng cấp: loại bỏ class-level `@Validated` nếu chọn MVC built-in

~~~java
@RestController
class ModernOrderController {

    @GetMapping("/orders")
    String list(@RequestParam @Min(1) int limit) {
        return "count=" + limit;
    }
}
~~~

Với Bean Validation provider được tích hợp trong MVC 6.1+, direct constraint `@Min(1)` được xử lý bởi MVC; lỗi tham số được mô tả qua `HandlerMethodValidationException` và có HTTP 400 theo mặc định.

**Không chỉ xóa annotation mà bỏ qua kiểm thử.** Các điểm cần kiểm tra:

| Trước 6.1 / AOP | Sau 6.1 / MVC built-in | Việc phải làm |
| --- | --- | --- |
| `@Validated` cấp controller | Bỏ annotation cấp controller khi chọn MVC built-in | Kiểm tra nơi khác có cần `@Validated` không |
| Bắt `ConstraintViolationException` ở advice | Có thể nhận `HandlerMethodValidationException` | Bổ sung xử lý loại mới |
| Logic tự trả 400 cho mọi violation | MVC phân biệt input 400 và return 500 | Giữ đúng status |
| Chỉ test object-only `@Valid` | Test cả direct parameters và return | Viết MockMvc test |
| Tự đọc raw `ConstraintViolation#getPropertyPath()` | Dùng `ParameterValidationResult`, `ParameterErrors` | Cập nhật mapping lỗi |
| Method validation qua proxy có giới hạn AOP | Built-in nằm trong MVC handler pipeline | Không cần proxy handler để áp constraint |
| `@Validated(SomeGroup.class)` ở class | Có thể ảnh hưởng group/validation semantics | Rà soát group behavior và cấu hình validator |

Nếu ứng dụng cố tình dùng AOP method validation ở controller hoặc có xử lý group phức tạp, không nhất thiết phải chuyển ngay; nhưng cần **chọn một chiến lược rõ ràng** và test các lỗi với đúng exception.

### 9.3. Kiểm tra các case thường bị bỏ sót

- `@Valid @RequestBody` **không có** direct method constraint: vẫn thường đi theo object-only validation.
- Cùng handler **thêm `@Min`** trên một `@RequestParam`: có thể đổi exception cho validation failures của request body.
- Method có constraint trên **return value**: có thể trả 500 sau khi thân method chạy.
- `@RequestParam(required=true)` bị thiếu: exception có thể ném **trước** Bean Validation.
- JSON sai cú pháp: `HttpMessageNotReadableException`, không phải method constraint.
- Conversion chuỗi sang số thất bại: type-mismatch exception, không phải `@Min` violation.
- `BindingResult` liền sau một object: handler có thể được gọi nếu mọi errors đều thuộc những đối số có `Errors` ngay sau.
- `@Validated` cấp class của controller vô tình chưa được xóa: vẫn có thể chạy theo AOP.

## 10. Những tình huống nâng cao

### 10.1. Nested validation và container element constraints

~~~java
public class BatchInput {
    @NotEmpty
    private List<@NotBlank String> codes;

    public List<String> getCodes() {
        return codes;
    }

    public void setCodes(List<String> codes) {
        this.codes = codes;
    }
}
~~~

Khi tham số `@Valid @RequestBody BatchInput body` được kiểm tra, Bean Validation có thể áp `@NotEmpty` lên list và `@NotBlank` lên từng phần tử. Container element constraints cần value extractors; với `List` chúng thường được provider hỗ trợ sẵn.

Nếu cùng method có `@RequestParam @Min(1) int priority`, nested violations ở `BatchInput` thuộc method validation flow. Lỗi nhiều phần tử có thể xuất hiện trong `ParameterErrors` hoặc `ParameterValidationResult` cùng metadata container index/key. Không tự giả định cứ có `List` thì `@Valid` sẽ được kích hoạt nếu loại input đó không được framework validate theo handler signature.

Ví dụ `BatchInput` ở đây chỉ minh họa cấu trúc DTO; không phải một tệp bắt buộc trong project ở mục 5.

### 10.2. Cross-parameter constraints

Một custom constraint áp dụng cho **mảng tham số** method, ví dụ “`start` phải nhỏ hơn hoặc bằng `end`”, được triển khai bằng `ConstraintValidator<MyConstraint, Object[]>` với:

~~~java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
~~~

Đây là đoạn annotation minh họa trong một validator, không phải class standalone. Spring MVC method validation có thể nhận lỗi cross-parameter, và `HandlerMethodValidationException#getCrossParameterValidationResults()` cho phép đọc chúng. Lỗi này không nhất thiết thuộc một `@RequestParam` cụ thể, nên không cố ánh xạ vào một field khi chưa thiết kế đúng `ConstraintValidatorContext`.

Khi dùng inheritance/interface trên method parameters, chú ý quy tắc Jakarta Validation: không được thêm preconditions trên một method override; constraints trên return có thể bổ sung theo những giới hạn của chuẩn. Spring MVC 6.1 không loại bỏ các quy tắc Bean Validation đó.

### 10.3. Groups

`@Validated` của Spring có thể chọn validation groups. Nhưng riêng **class-level `@Validated` trên controller** sẽ ảnh hưởng việc MVC dùng built-in method validation hay AOP proxy. Nếu trước đây dự án dùng `@Validated(Group.class)` cấp controller và nay muốn bỏ để chuyển sang MVC 6.1+, phải thiết kế lại cách chọn nhóm theo API hỗ trợ và kiểm tra tương tác với custom `Validator`; không giả định migration giữ nguyên group selection.

`@Valid` của Jakarta chỉ yêu cầu cascade, không chọn group. Với nested object, group conversion `@ConvertGroup` có thể có tác dụng khi cascade. Mọi lựa chọn group cần có test tích hợp riêng thay vì chỉ test từng bean bằng `validator.validate(bean, Group.class)`.

### 10.4. Async return và reactive publishers

Khi handler trả `CompletableFuture<T>`, `DeferredResult<T>`, `Callable<T>` hoặc publisher, không được mặc định rằng constraint trên type parameter được kiểm tra tại đúng thời điểm giá trị bất đồng bộ xuất hiện như một direct synchronous return. Spring MVC có cơ chế async request processing riêng, và Bean Validation không tự “await” mọi wrapper. Với async return, hãy xác định đối tượng thực sự được validate, integration hỗ trợ gì và viết test cho thời điểm response hoàn tất.

Trong ứng dụng Spring WebFlux, cũng có phương thức method validation tích hợp từ Spring Framework 6.1, nhưng luồng WebFlux không phải Servlet MVC `HandlerMethodValidator` của bài này; không sao chép nguyên mọi kết luận về exception và argument resolution mà không kiểm tra tài liệu WebFlux.

### 10.5. Custom validators và cấu hình toàn cục

Khi có provider Jakarta Validation trên classpath, Spring MVC thường đăng ký global `Validator` phù hợp (ví dụ `LocalValidatorFactoryBean`). Có thể tùy biến qua `WebMvcConfigurer#getValidator()` hoặc sử dụng local `@InitBinder` validators theo nhu cầu.

Cần phân biệt:
- `@InitBinder` tùy biến data binder, formatters và local validators cho arguments.
- `LocalValidatorFactoryBean` là adapter/kết nối Bean Validation với Spring.
- `MethodValidationPostProcessor` phục vụ AOP method validation của beans, **không phải điều kiện bắt buộc** cho MVC built-in.
- `HandlerMethodValidator` xử lý các method constraints trên MVC handlers khi điều kiện tích hợp thỏa.

Nếu tự thay global validator bằng implementation không hỗ trợ Bean Validation đầy đủ, hành vi method validation có thể thay đổi. Kiểm tra cả conversion/binding và executable validation sau khi tùy biến.

### 10.6. Constructor và service method validation

`@RequestMapping` handler validation của MVC không phải cơ chế “mọi method trong ứng dụng đều được validate”. Service beans thường dùng `@Validated` class-level với AOP proxy; constructor validation cần integration riêng hoặc `ExecutableValidator`. Đừng bỏ `@Validated` khỏi service chỉ vì MVC 6.1 có built-in method validation: **hai phạm vi khác nhau**.

## 11. Chẩn đoán lỗi và các anti-patterns

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| `@Min` trên controller parameter không chạy | Thiếu provider, framework chưa đủ phiên bản, đường dispatch không qua MVC, constraint đặt sai chỗ | Kiểm tra dependency, phiên bản Spring, handler signature và MockMvc test |
| Lỗi `@Valid @RequestBody` vẫn là `MethodArgumentNotValidException` | Chữ ký không có direct method constraint | Đây có thể là hành vi đúng; kiểm tra bảng ở mục 2 |
| Thêm `@Min` rồi exception DTO đổi loại | Method validation thay thế object-only validation | Xử lý `HandlerMethodValidationException` bên cạnh loại cũ |
| Handler bị từ chối mặc dù có `BindingResult` | Có lỗi trên **tham số khác** không có `Errors` ngay sau | Kiểm tra từng argument của method |
| `BindingResult` không nhận đúng lỗi | Không đặt ngay sau `@ModelAttribute` / `@RequestBody` | Sửa thứ tự method arguments |
| Lỗi thiếu tham số hoặc JSON invalid không vào method exception handler | Lỗi ở resolution/deserialization trước validation | Bắt đúng `MissingServletRequestParameterException` / `HttpMessageNotReadableException` |
| Phản hồi return invalid bị trả HTTP 400 | Advice tùy chỉnh map mọi validation lỗi thành 400 | Dùng `ex.isForReturnValue()` hoặc `ex.getStatusCode()` |
| Test MockMvc không thấy method validation | Thiếu global validator hoặc custom standalone MVC setup khác Spring Boot | Dùng `@SpringBootTest @AutoConfigureMockMvc` hoặc cấu hình `standaloneSetup` đủ validator |
| Controller vẫn ném `ConstraintViolationException` từ proxy | `@Validated` cấp class còn tồn tại; AOP method validation được kích hoạt | Nếu chọn MVC built-in, bỏ class-level `@Validated`, test lại |
| Client thấy cả giá trị nhạy cảm trong response | Mapping trực tiếp `getArgument()`, raw violation/rejected value | Chỉ trả trường và mã lỗi an toàn |
| Service gọi nội bộ không validate | Spring AOP self-invocation bỏ qua proxy | Test qua bean injected; không nhầm với MVC built-in |
| Không xác định được lỗi ở list index nào | Bỏ qua container metadata | Dùng `ParameterValidationResult#getContainerIndex()` / `getContainerKey()`, hoặc `ParameterErrors` |

### Một quy trình debug hiệu quả

1. Xác nhận **Spring MVC version** và classpath có `spring-boot-starter-validation`/provider.
2. Đọc **chữ ký handler**: `@Valid` chỉ nằm trên object hay có direct `@Constraint` ở method argument/return?
3. Kiểm tra controller có `@Validated` cấp class không. Nếu mục tiêu là cơ chế MVC 6.1+, gỡ annotation đó.
4. Tách lỗi **resolution/binding** khỏi lỗi **Bean Validation**: missing parameter, JSON sai, type mismatch có thể xuất hiện sớm hơn.
5. Gửi request tối giản qua `MockMvc`, xác nhận **HTTP status**, `resolvedException` và `isForReturnValue()`.
6. Đọc `ParameterValidationResult`/`ParameterErrors` để tìm param/field, không parse message.
7. Kiểm tra `BindingResult` liền sau object nếu muốn xử lý lỗi cục bộ.
8. Nếu đã có `@ControllerAdvice`, kiểm tra thứ tự/resolver và mapping status; không thay 500 bằng 400.
9. Khi nâng cấp từ AOP, test đồng thời error types trước/sau và không ảnh hưởng service validation.

## 12. Checklist áp dụng vào dự án

- [ ] Project dùng Spring Framework **6.1+**; Java/Jakarta Validation versions tương thích.
- [ ] Controller dành cho MVC built-in **không có `@Validated` ở cấp class**.
- [ ] Direct method constraints (trên tham số hoặc return) được khai báo đúng kiểu và đúng vị trí.
- [ ] Hiểu rằng `@Valid` đơn thuần **không phải direct constraint**, nên object-only validation có thể giữ `MethodArgumentNotValidException`.
- [ ] `@ControllerAdvice` xử lý cả `MethodArgumentNotValidException` và `HandlerMethodValidationException`, đồng thời bảo toàn status 400/500.
- [ ] `BindingResult`/`Errors` nếu dùng luôn đặt **ngay sau** argument tương ứng; lỗi ở argument khác vẫn được xử lý theo cơ chế method validation.
- [ ] Các lỗi binding/JSON/required parameters có nhánh xử lý riêng; không xem mọi HTTP 400 là constraint violation.
- [ ] Viết MockMvc integration tests cho hợp lệ, direct parameter invalid, nested DTO invalid, return invalid, và local `BindingResult`.
- [ ] Giữ service method validation qua `@Validated`/AOP khi cần; không nhầm phạm vi MVC với toàn ứng dụng.
- [ ] Response errors không lộ token, dữ liệu người dùng, raw rejected values hoặc stack trace.

## 13. Tài liệu tham khảo

- Spring Framework 6.2, **Spring MVC Validation** (giải thích hai mức validation, `@Validated` và `BindingResult`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2, **MVC validation configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 Javadoc, **HandlerMethodValidationException**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc, **ParameterValidationResult**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 Javadoc, **ParameterErrors**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring Framework 6.2, **Spring-driven Method Validation (AOP)**: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Boot 3.5, **Validation**: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Validation, **Bean Validation specification**: https://jakarta.ee/specifications/bean-validation/
