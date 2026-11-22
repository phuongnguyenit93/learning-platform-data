# Kiểm thử binding, validation, ProblemDetail và ControllerAdvice trong Spring MVC

## 1. Mục tiêu và bức tranh tổng thể

Một API HTTP đúng không chỉ trả 200 cho request hợp lệ. Nó phải **chuyển dữ liệu từ HTTP thành đối tượng Java đúng cách (binding)**, từ chối input vi phạm ràng buộc (**validation**), trả status và cấu trúc lỗi nhất quán (**ProblemDetail**), đồng thời xử lý lỗi tập trung mà không làm lộ chi tiết hệ thống (**@ControllerAdvice**).

Ví dụ endpoint tạo đơn nhận JSON có mã hàng `sku` và số lượng `quantity`. Những trường hợp cần test gồm: body đúng, body rỗng, JSON sai cú pháp, Content-Type sai, `sku` chỉ chứa khoảng trắng, `quantity` nhỏ hơn 1, query parameter không chuyển được sang số, path variable vượt ràng buộc, và đơn hàng không tìm thấy.

Bài sử dụng **Spring MVC (Servlet)** với Spring Framework 6.1 / Spring Boot 3.3.x và Java 17. Trọng tâm là dùng **MockMvc** thực thi tầng MVC cùng converters, data binding, Jakarta Bean Validation, exception resolver và advice; **không cần khởi động cổng HTTP thật** trong slice test.

Học xong bạn có thể:
1. Phân biệt binding lỗi, conversion lỗi và Bean Validation lỗi; biết exception nào sẽ xuất hiện.
2. Dùng `@WebMvcTest`, `MockMvc`, `@Valid`, `@ModelAttribute`, `@RequestBody`, `@RequestParam` và `@PathVariable` có mục đích.
3. Viết `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler` để chuyển các lỗi Spring MVC thành `ProblemDetail` chuẩn và bổ sung field errors.
4. Kiểm tra status, header `application/problem+json`, JSON body và việc controller **không chạy nhánh nghiệp vụ** nếu input không hợp lệ.
5. Xây dựng bộ test vừa có đường thành công, vừa có lỗi validation/conversion/exception, đồng thời biết những gì slice test không bảo đảm.

## 2. HTTP request đi qua Spring MVC như thế nào?

~~~mermaid
flowchart TD
    A[HTTP request] --> B[DispatcherServlet và HandlerMapping]
    B --> C[Argument resolver và HttpMessageConverter]
    C -->|JSON/form/query/path hợp lệ về cú pháp| D[Data binding và conversion]
    D -->|Có @Valid / constraint| E[Jakarta Bean Validation]
    E -->|PASS| F[Controller method]
    F --> G[Service / business result]
    G --> H[Response serialization]
    C -->|JSON không đọc được| I[Exception resolver]
    D -->|Conversion/required thiếu| I
    E -->|Validation FAIL| I
    F -->|Domain exception| I
    I --> J[ControllerAdvice / ResponseEntityExceptionHandler]
    J --> K[HTTP status + ProblemDetail JSON]
~~~

Đây là luồng khái niệm. Spring MVC có nhiều argument resolvers và exception resolvers, nên một số bước được lồng trong nhau; diagram nhằm phân biệt **nguồn phát sinh lỗi**. Nếu lỗi đã bị bắt và xử lý ở controller bằng `BindingResult`, nó có thể không chuyển sang advice.

| Nguồn input | Annotation thường gặp | Cách Spring đọc | Ví dụ lỗi |
| --- | --- | --- | --- |
| JSON request body | `@RequestBody` | Jackson/HttpMessageConverter | JSON sai → `HttpMessageNotReadableException` |
| Query string | `@RequestParam` | Converter + binder | `page=abc` không thành int → `MethodArgumentTypeMismatchException` |
| Path | `@PathVariable` | URI template + Converter | `/orders/abc` không thành long |
| Form/query bind object | `@ModelAttribute` | DataBinder điền JavaBean/constructor binding | Sai kiểu field tạo binding errors |
| Bean Validation object | `@Valid` trên DTO | Jakarta Validator (khi có dependency) | `@NotBlank`, `@Min` không đạt |
| Constraint trực tiếp trên method parameter | `@Min`/`@NotBlank` | Built-in method validation từ Spring 6.1 | `HandlerMethodValidationException` |

**Binding khác validation**: JSON `{"quantity":"abc"}` không giải mã được sang int nên chưa có DTO đúng để áp dụng `@Min` như thông thường. Ngược lại `{"quantity":0}` giải mã được thành int nhưng thất bại ràng buộc `@Min(1)`.

## 3. Validation trên DTO và validation trên method khác nhau

### 3.1. Validation một object

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) int quantity
) {}
~~~

Đặt `@Valid` tại tham số controller:

~~~java
@PostMapping
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Chỉ đến đây nếu request đã giải mã và validation thành công.
}
~~~

Với Spring MVC, khi `@Valid @RequestBody` được validation ở mức object, **thường ném `MethodArgumentNotValidException`** nếu không đặt `Errors`/`BindingResult` ngay sau tham số và không có ràng buộc trực tiếp khác đòi hỏi method validation.

**Điều kiện tiên quyết:** ứng dụng phải có `spring-boot-starter-validation` (Jakarta Validation provider, thường là Hibernate Validator). Chỉ thêm `jakarta.validation.Valid` nhưng không có validator phù hợp sẽ không bảo đảm ràng buộc được thực thi.

Với `@NotBlank`, chuỗi null, rỗng và toàn whitespace bị từ chối. Với `@Min(1)`, các giá trị 0 hoặc âm bị từ chối. Nếu field primitive `int` không xuất hiện, Java có thể nhận giá trị mặc định 0 sau deserialization tùy cấu hình, rồi `@Min` bắt được; nhưng để phân biệt **thiếu hẳn field** với **field có giá trị 0**, dùng `Integer` kết hợp `@NotNull` và `@Min(1)`.

### 3.2. BindingResult thay đổi đường xử lý

Một controller khác có thể viết:

~~~java
@PostMapping("/preview")
ResponseEntity<?> preview(
        @Valid @RequestBody CreateOrderRequest request,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid preview");
    }
    return ResponseEntity.ok("Preview allowed");
}
~~~

Đoạn minh họa này thuộc một controller đã có `@RequestMapping`; cần imports Java/Spring và DTO ở ví dụ trước. **BindingResult phải đứng ngay sau argument cần bắt lỗi**. Khi xử lý cục bộ, bạn chủ động xây response; advice không nhất thiết nhận `MethodArgumentNotValidException` cho lỗi này. Không truyền mọi lỗi về HTTP 200 để “có body”; status phải phản ánh tính hợp lệ.

### 3.3. Validation trực tiếp trên method parameters (Spring 6.1+)

~~~java
@GetMapping("/{id}")
OrderResponse getOrder(@PathVariable @Min(1) long id) {
    return service.find(id);
}
~~~

`@Min` đặt trực tiếp lên tham số method yêu cầu **method validation**; Spring MVC 6.1 có built-in support và lỗi input thường là `HandlerMethodValidationException`. Việc thêm class-level `@Validated` có thể chuyển sang cơ chế AOP method validation khác; không tự thêm `@Validated` lên toàn controller nếu mục tiêu là kiểm thử cơ chế built-in này.

| Tình huống | Exception điển hình | Phản hồi nên test |
| --- | --- | --- |
| `@Valid @RequestBody` với field `@NotBlank` sai | `MethodArgumentNotValidException` | 400 và field errors |
| `@Valid @ModelAttribute` với field `@Min` sai | `MethodArgumentNotValidException` | 400 và field errors |
| `@PathVariable @Min(1)` nhận 0 | `HandlerMethodValidationException` | 400 (với input violation) |
| `@RequestParam int page` nhận `abc` | `MethodArgumentTypeMismatchException` / nhóm type mismatch | 400 |
| Thiếu required `@RequestParam` | `MissingServletRequestParameterException` | 400 |
| JSON sai cú pháp hoặc JSON mapping không thể hoàn tất | `HttpMessageNotReadableException` | 400 |
| `Content-Type: text/plain` cho endpoint tiêu thụ JSON | `HttpMediaTypeNotSupportedException` | 415 |
| Resource không tồn tại do nghiệp vụ | Custom `OrderNotFoundException` | 404 |
| Client không chấp nhận response media type | `HttpMediaTypeNotAcceptableException` | 406 |

Các status/mapping cuối cùng còn phụ thuộc exception handlers và Spring configuration. Không dựa vào một bảng cứng mà bỏ qua kiểm thử **response thực tế của ứng dụng**.

## 4. ProblemDetail: kiểm thử hợp đồng lỗi thay vì thông báo tùy ý

Spring Framework 6 hỗ trợ `org.springframework.http.ProblemDetail` theo mô hình **RFC 9457 Problem Details for HTTP APIs**. Body JSON điển hình:

~~~json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request validation failed",
  "instance": "/api/orders",
  "errors": {
    "quantity": "must be greater than or equal to 1",
    "sku": "must not be blank"
  }
}
~~~

`type`, `title`, `status`, `detail`, `instance` là các member chuẩn; `errors` là extension của ứng dụng. Ví dụ mô tả **shape kỳ vọng**; message và locale của validator có thể thay đổi. Khi soạn test, chỉ kiểm tra chính xác message khi thông điệp đã thuộc API contract cố định, tránh ràng buộc vào text ngẫu nhiên của framework.

- **type:** URI nhận diện loại vấn đề; nếu không đặt, thường là `about:blank`.
- **title:** tên lỗi ngắn, có tính phân loại.
- **status:** HTTP status dạng số trong body; phải đồng nhất với status line.
- **detail:** giải thích an toàn cho người gọi, không chứa SQL, stack trace hoặc nội dung nội bộ.
- **instance:** URI của request bị lỗi; Spring có thể điền đường dẫn hiện tại nếu ứng dụng không đặt.
- **extensions:** thêm mã lỗi, field errors, correlation ID có kiểm soát. Jackson do Spring cấu hình thường serialize `ProblemDetail.setProperty("errors", ...)` ở **top-level JSON**, không bắt buộc nằm dưới `properties`.

Với `ProblemDetail` được return từ `@ExceptionHandler` hoặc controller, Spring MVC ưu tiên media type `application/problem+json` khi thương lượng nội dung. Hãy dùng `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)` trong MockMvc để chịu được tham số charset không quan trọng.

**Không đồng nhất “mọi lỗi của Spring Boot tự trả ProblemDetail”**. Có hai lựa chọn:
1. Spring Boot có tùy chọn `spring.mvc.problemdetails.enabled=true` để cấu hình xử lý lỗi framework theo ProblemDetail.
2. Ứng dụng tự khai báo `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler` để chủ động xử lý lỗi MVC và mở rộng response.

Ví dụ đầy đủ trong bài sử dụng **cách 2**, không cần bật property tương ứng. Tránh cấu hình đồng thời nhiều advice có trách nhiệm chồng chéo mà không xác định thứ tự `@Order`. Nếu đã bật Boot auto-config ProblemDetail, cần xét mức ưu tiên advice tùy chỉnh đối với handler tự động.

### 4.1. Những điều không nên lộ qua lỗi

Không trả trực tiếp `exception.getMessage()` cho tất cả exception 500: thông điệp có thể chứa SQL, đường dẫn file, class/package, host nội bộ hoặc token. Các field errors nên chứa **tên trường client được phép biết** và thông điệp đã kiểm tra an toàn. Khi thêm `traceId`, nên dùng ID tương quan sinh từ hệ thống quan sát; không cho phép client ghi đè dữ liệu tin cậy một cách tự do.

Đừng trả 500 cho lỗi nhập liệu 400, cũng đừng biến mọi exception thành 400. Cách phân loại có ảnh hưởng đến hành vi retry, UX, cache và vận hành.

## 5. @RestControllerAdvice và ResponseEntityExceptionHandler

`@ControllerAdvice` tập hợp xử lý dùng chung cho nhiều controller, gồm `@ExceptionHandler`, `@InitBinder` và `@ModelAttribute`. `@RestControllerAdvice` tương đương ControllerAdvice có semantics response body, rất tiện cho JSON API.

`ResponseEntityExceptionHandler` có handler sẵn cho nhiều exception của Spring MVC (body không đọc được, media type sai, binding/validation, method không hỗ trợ...). Khi kế thừa:
- **Override protected methods** như `handleMethodArgumentNotValid`, `handleHandlerMethodValidationException` để tùy biến lỗi framework.
- Thêm `@ExceptionHandler` **chỉ cho exception nghiệp vụ** của mình như OrderNotFoundException.
- Tránh khai báo thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` cạnh một subclass ResponseEntityExceptionHandler, vì handler cơ sở đã đăng ký nhóm exception đó; mapping cạnh tranh có thể tạo lỗi ambiguous exception mapping.
- Trả `ResponseEntity` với status và body đồng nhất; dùng `handleExceptionInternal` nếu muốn giữ quy trình xử lý tập trung của base class.
- Không thêm `@ExceptionHandler(Exception.class)` bắt hết nếu chưa có yêu cầu rõ và kế hoạch logging/500, vì sẽ che lỗi lập trình, lỗi framework và status đúng.

Ví dụ chữ ký override trên **Spring Framework 6.1**:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        status, "Request validation failed");
    problem.setTitle("Invalid request");
    return handleExceptionInternal(ex, problem, headers, status, request);
}
~~~

`HttpStatusCode` (không còn `HttpStatus` ở vị trí parameter đó) là phần quan trọng để biên dịch đúng Spring 6.1. Đây là đoạn tích hợp, class đầy đủ xuất hiện ở ví dụ sau.

## 6. Bài thực hành đầy đủ: Spring MVC + ProblemDetail + MockMvc

Demo có endpoint POST tạo đơn, GET tra cứu đơn, GET search dùng ModelAttribute, và GET quote dùng RequestParam. Không có database để giữ bài tập tập trung vào request mapping và lỗi HTTP. Application được tạo bằng Spring Boot **3.3.13**, Java 17+, Maven; dependency validation khai báo riêng.

### 6.1. Cấu trúc

~~~text
mvc-errors-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── MvcErrorsApplication.java
    │   ├── OrderController.java
    │   └── ApiProblemAdvice.java
    └── test/java/demo/
        └── OrderControllerWebTest.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>mvc-errors-demo</artifactId>
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

Ba dependencies đảm nhiệm: Spring MVC + Jackson; Jakarta Bean Validation + Hibernate Validator; JUnit 5/MockMvc/assertions. Ví dụ không cài Spring Security, vì FilterChain xác thực/CSRF sẽ làm thay đổi status và cấu hình test; dự án có Security cần kiểm thử security thực tế, không mặc định tắt filter.

### 6.3. MvcErrorsApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcErrorsApplication.class, args);
    }
}
~~~

### 6.4. OrderController.java

~~~java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record CreateOrderRequest(
        @NotBlank String sku,
        @Min(1) int quantity
    ) {}

    public record OrderResponse(long id, String sku, int quantity) {}

    public static class SearchCriteria {
        @Min(1)
        private Integer page;

        public Integer getPage() {
            return page;
        }

        public void setPage(Integer page) {
            this.page = page;
        }
    }

    public static class OrderNotFoundException extends RuntimeException {
        public OrderNotFoundException(long id) {
            super("Order " + id + " was not found");
        }
    }

    @PostMapping(consumes = "application/json")
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest input) {
        OrderResponse output = new OrderResponse(
            42L, input.sku(), input.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(output);
    }

    @GetMapping("/{id}")
    public OrderResponse find(@PathVariable @Min(1) long id) {
        if (id != 42L) {
            throw new OrderNotFoundException(id);
        }
        return new OrderResponse(42L, "A-7", 2);
    }

    @GetMapping("/search")
    public String search(@Valid @ModelAttribute SearchCriteria filter) {
        return "page=" + filter.getPage();
    }

    @GetMapping("/quote")
    public String quote(@RequestParam int quantity) {
        return "quantity=" + quantity;
    }
}
~~~

**Lý do cố ý viết như vậy:**
- `create` cho thấy `@RequestBody` + Jackson + Bean Validation `@NotBlank`/`@Min`, HTTP 201 khi thành công.
- `find` có `@Min` trực tiếp ở argument method để minh họa `HandlerMethodValidationException`; **không đặt `@Validated` ở class**, tránh thay đổi cơ chế Spring MVC 6.1.
- `search` nhận query `page` vào bean bằng `@ModelAttribute`; `page=0` bind thành Integer nhưng không đạt `@Min(1)`.
- `quote` nhận `int`, dùng để kiểm lỗi conversion `quantity=abc` hoặc thiếu tham số.
- Exception OrderNotFoundException đại diện cho lỗi nghiệp vụ. Việc response cố định và không lưu database giúp test độc lập với persistence; ứng dụng thật gọi service nhưng test MVC có thể mock service riêng.

**Chú ý mapping GET:** `/search` và `/quote` là các path cụ thể, Spring ưu tiên path cụ thể hơn `/{id}`. `/api/orders/abc` sẽ chọn pattern `/{id}` nhưng không thể bind thành long, nên là lỗi conversion, khác `/api/orders/999` chuyển được thành long và dẫn tới domain 404.

### 6.5. ApiProblemAdvice.java

~~~java
package demo;

import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import demo.OrderController.OrderNotFoundException;

@RestControllerAdvice
public class ApiProblemAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "Request validation failed");
        problem.setTitle("Invalid request");

        Map<String, String> fieldErrors = new TreeMap<>();
        ex.getBindingResult().getFieldErrors().forEach(error ->
            fieldErrors.putIfAbsent(
                error.getField(),
                error.getDefaultMessage() == null
                    ? "Invalid value" : error.getDefaultMessage()));

        problem.setProperty("errors", fieldErrors);
        return handleExceptionInternal(
            ex, problem, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "Method parameter validation failed");
        problem.setTitle("Invalid parameter");

        return handleExceptionInternal(
            ex, problem, headers, status, request);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Requested order does not exist");
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Class này là cấu hình xử lý lỗi **đúng phiên bản 6.1**. `ResponseEntityExceptionHandler` tiếp tục xử lý lỗi JSON không đọc được, thiếu query, sai Content-Type và lỗi built-in khác mà ta không override. `@RestControllerAdvice` được component scan cùng package demo khi chạy ứng dụng. Custom exception 404 được đặt mã lỗi máy đọc được là ORDER_NOT_FOUND; không cần gửi exception message có ID thật nếu đó là thông tin không nên tiết lộ.

`TreeMap` làm thứ tự tên field ổn định để dễ đọc response, nhưng **test JSON không nên dựa vào thứ tự field**. `putIfAbsent` chọn thông điệp đầu tiên cho mỗi field; một field có thể vi phạm nhiều constraint. Hệ thống có nhu cầu UI chi tiết có thể trả **danh sách lỗi theo field** thay vì một string, phải định nghĩa contract trước. Spring Jackson mix-in có thể hiển thị extension `errors` và `code` ở top-level JSON.

### 6.6. OrderControllerWebTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiProblemAdvice.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonReturns201AndMappedDto() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"A-7","quantity":2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.sku").value("A-7"))
            .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidBodyReturnsProblemWithFieldErrors() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"   ","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.title").value("Invalid request"))
            .andExpect(jsonPath("$.errors.sku").exists())
            .andExpect(jsonPath("$.errors.quantity").exists());
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{broken json"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .content("sku=A-7"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void modelAttributeValidationReturns400() throws Exception {
        mvc.perform(get("/api/orders/search")
                .param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title").value("Invalid request"))
            .andExpect(jsonPath("$.errors.page").exists());
    }

    @Test
    void validQueryBindsToModelAttribute() throws Exception {
        mvc.perform(get("/api/orders/search")
                .param("page", "2"))
            .andExpect(status().isOk())
            .andExpect(content().string("page=2"));
    }

    @Test
    void malformedQueryNumberReturns400() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("quantity", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryReturns400() throws Exception {
        mvc.perform(get("/api/orders/quote"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directMethodConstraintUsesMethodValidation() throws Exception {
        mvc.perform(get("/api/orders/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title").value("Invalid parameter"))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void notFoundDomainErrorReturns404Problem() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void existingResourceReturnsSuccessfulJson() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("A-7"));
    }
}
~~~

Chạy trong thư mục `mvc-errors-demo`:

~~~bash
mvn -q test
~~~

Bộ mã cung cấp **11 phương thức JUnit @Test**. Nếu chạy thành công, Maven trả exit code 0 và Surefire tạo báo cáo ở `target/surefire-reports/`. Chế độ `-q` có thể không in dòng tổng hợp trên stdout; **không giả định test đã PASS khi chưa chạy ở máy thực**. Khi test fail, đọc stack trace cùng resolved exception/response của MockMvc; không sửa assertion chỉ để che hành vi bất ngờ.

Chạy server thật:

~~~bash
mvn spring-boot:run
~~~

Lệnh thử request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-7","quantity":2}'

curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":" ","quantity":0}'

curl -i http://localhost:8080/api/orders/999
~~~

Với demo này, response của lệnh thứ nhất dự kiến **HTTP 201** với body như sau (bỏ qua headers, thời điểm và whitespace):

~~~json
{"id":42,"sku":"A-7","quantity":2}
~~~

Lệnh thứ hai dự kiến **HTTP 400** và ProblemDetail chứa `title: "Invalid request"`, cùng hai field errors cho sku/quantity. Lệnh thứ ba dự kiến **HTTP 404**, `code: "ORDER_NOT_FOUND"`. Các trường `detail` hoặc validation messages được bản địa hóa tùy cấu hình validator; test không khóa text đó một cách không cần thiết.

**Về khả năng chạy:** đây là project Maven mẫu độc lập, được thiết kế theo API Spring 6.1. Việc xây dựng test trong bài giúp người đọc chạy kiểm tra trên máy của mình; bài này không đưa ra bằng chứng test đã thực thi ngoài môi trường được mô tả.

## 7. Vì sao dùng @WebMvcTest và khi nào phải kiểm thử đầy đủ?

`@WebMvcTest(OrderController.class)` tải một lát cắt MVC: controller, mapping/argument resolvers, converters, MVC configuration, validation và những advice liên quan. `@Import(ApiProblemAdvice.class)` làm explicit rằng chính advice của API được dùng khi test (ngay cả khi scan thay đổi). MockMvc tạo request/response ở tầng Servlet mô phỏng mà không bind TCP port.

| Cách test | Phần được kiểm tra | Giới hạn |
| --- | --- | --- |
| Unit test gọi trực tiếp `controller.create(dto)` | Logic Java trong method | Không chạy JSON binding, validation, mapping, advice |
| MockMvc `standaloneSetup` | Mapping MVC tối thiểu, test nhanh và có thể gắn advice thủ công | Cần tự cấu hình converter/validator/resolvers; dễ lệch production |
| `@WebMvcTest` + MockMvc | MVC slice, validation, Jackson, advice, handler mappings | Không tải toàn bộ service/database/infra |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Cấu hình app đầy đủ cùng MockMvc | Nặng hơn, vẫn không tự chứng minh socket/TLS/proxy |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client | Full app qua TCP local, HTTP serialization thật | Tốn tài nguyên, còn phụ thuộc cách mock infra và cấu hình test |
| Contract/E2E | Tương thích producer-consumer và deployment thực | Chậm, đòi hỏi quản lý test data và môi trường |

Nếu controller inject một service, `@WebMvcTest` **không tự tải** tất cả `@Service`, repository hay bean nghiệp vụ. Với Spring Boot 3.3 có thể dùng `@MockBean` để cung cấp dependency trong slice test hoặc `@Import` config test cần thiết; chú ý API mock annotation có thay đổi ở các nhánh Boot mới, tránh dùng annotation không thuộc version dự án.

Khi dùng Spring Security, `@WebMvcTest` có thể tải FilterChain. Request POST có thể bị 403 vì CSRF **trước khi** chạm vào controller, và 401/403 có thể do authentication. Hãy viết test security đúng `spring-security-test` với user/CSRF nếu cần; không tắt security tùy ý rồi kết luận endpoint production xử lý validation ổn.

## 8. Kiểm thử sâu hơn data binding và validation

### 8.1. Tách ba nguồn lỗi

Giả sử endpoint POST nhận int quantity:
- `{"quantity":2}`: JSON hợp lệ, binding OK, `@Min` OK.
- `{"quantity":0}`: JSON hợp lệ, binding OK, Bean Validation FAIL.
- `{"quantity":"not-a-number"}`: Jackson/type conversion FAIL trước validation.
- `{"quantity":null}`: hành vi phụ thuộc primitive/wrapper và cấu hình Jackson; test contract của mình thay vì giả định.
- Body rỗng và `@RequestBody(required=true)`: thường `HttpMessageNotReadableException` dẫn đến 400.
- Thiếu Content-Type hoặc `text/plain`: có thể gây 415 bởi `consumes="application/json"`; kiểm tra cả body lẫn header request.

Hai lỗi có status cùng 400 **không có nghĩa cùng loại**. Với API công khai, nên có mã máy đọc được phân biệt `VALIDATION_FAILED`, `INVALID_JSON`, `INVALID_PARAMETER` nếu client thực sự cần; không suy ra code từ tiếng Anh trong `detail`.

### 8.2. Lỗi trong @ModelAttribute có thể là binding hoặc validation

Với `@Valid @ModelAttribute SearchCriteria`:
- `?page=2`: String "2" chuyển thành Integer 2, pass `@Min(1)`.
- `?page=0`: chuyển thành Integer 0, validation fail.
- `?page=abc`: conversion không thành Integer; binder ghi field error, tùy exception resolution của signature có thể thành `MethodArgumentNotValidException` với BindingResult.
- `?page=`: có thể bind thành null khi dùng `Integer`, và `@Min` **không thay thế `@NotNull`**; nếu page bắt buộc, thêm `@NotNull`.
- Unknown query parameter: nếu không có matching property, nó thường không được bind, nhưng điều này không phải chính sách bảo mật đủ cho mọi DTO.

Đối với mutable object, **tránh mass assignment**: không bind thẳng entity có các field `admin`, `price`, `role`, `ownerId` từ input không tin cậy. Dùng DTO riêng, constructor binding hoặc giới hạn `DataBinder.setAllowedFields(...)` ở `@InitBinder` khi thích hợp. Unit test DTO không bắt được vấn đề này nếu không chạy MVC binder với request thật.

### 8.3. Validation groups và custom constraints

`@Validated(SomeGroup.class)` có thể chọn nhóm Bean Validation khác `@Valid` mặc định khi áp dụng cho object parameter. Nếu ứng dụng có POST create và PATCH update với điều kiện field khác nhau, hãy test **từng group** và khả năng thiếu/null riêng. Với custom `ConstraintValidator`, test ít nhất:
1. Giá trị hợp lệ và giá trị không hợp lệ;
2. Null/blank theo policy;
3. Unicode, biên số, độ dài;
4. Message/code và locale nếu là hợp đồng API.

**Bean Validation không thể thay thế kiểm tra nghiệp vụ có trạng thái**: unique SKU trong DB, quyền sửa order, số dư hay inventory cần service/database/race-condition tests. Tránh nhồi query DB vào ConstraintValidator khiến request binding tạo phụ thuộc ẩn.

### 8.4. Assert business side effects không xảy ra

Khi controller inject service, test invalid input nên kiểm tra service **không được gọi**. Ví dụ tích hợp dùng Mockito:

~~~java
mvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\" \",\"quantity\":0}"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(orderService);
~~~

Đây là snippet không độc lập; `orderService` là Mockito mock được inject vào controller và cần static import Mockito.verifyNoInteractions. Với demo không có service, nên chỉ kiểm status/body như ví dụ hoàn chỉnh. Việc service không được gọi là tiêu chí an toàn khi validation bảo vệ thao tác tạo dữ liệu thật.

## 9. Kiểm thử hợp đồng ProblemDetail ổn định

Một bộ assertion tốt tách **schema contract** khỏi chi tiết tình cờ:
- Kiểm status HTTP và body status đồng nhất;
- Header Content-Type tương thích `application/problem+json`;
- `type` (khi ứng dụng định nghĩa) và `code` của domain error ổn định;
- `title`/field errors có tồn tại, đúng key/shape;
- `instance` tương ứng path request, không chứa query nhạy cảm;
- Không có stack trace, package name, credential, SQL trong response;
- Không phụ thuộc thứ tự thuộc tính JSON hoặc thứ tự field errors;
- Test với locale khác nếu messages được quốc tế hóa.

Nếu public API đã công bố `type` URI cụ thể như `https://api.example.test/problems/validation-error`, test chính xác URI đó và tài liệu hóa lâu dài. Nếu chưa công bố, `about:blank` là giá trị mặc định hợp lệ, **không nên tự bịa URI** chỉ để đủ năm field.

### Localized messages

Spring MVC có `MessageSource` để resolve validation messages và ProblemDetail detail/title. Test locale bằng `Accept-Language` nếu ứng dụng hỗ trợ. Tránh so sánh chính xác thông điệp mặc định như "must not be blank" nếu có thể đổi theo Hibernate Validator, Spring version hoặc locale; thay vào đó kiểm tra field name và mã lỗi. Nếu giao diện thật dựa vào chuỗi thông điệp, hãy **sở hữu và phiên bản hóa thông điệp đó**, chứ không để framework nội bộ tự quyết định.

### Tương tác nhiều ControllerAdvice

Một ứng dụng có thể có advice chỉ dành cho REST API và advice khác cho MVC HTML. `@RestControllerAdvice(basePackages=...)`, `assignableTypes`, `annotations` và `@Order` giới hạn phạm vi/ưu tiên. Test nhiều controllers để bảo đảm response HTML không vô tình nhận JSON ProblemDetail, và lỗi domain của module này không bị advice catch-all module khác bắt trước.

Trong Spring Boot khi bật `spring.mvc.problemdetails.enabled=true`, handler tự động có thể cùng chịu trách nhiệm exception framework. Phải thiết kế override và thứ tự rõ ràng, không chỉ copy một `@RestControllerAdvice` rồi giả định chắc chắn được chọn đầu tiên.

## 10. Các sai lầm phổ biến khi viết MockMvc test

1. **Chỉ gọi trực tiếp controller:** không test Servlet binding, Jackson hay advice; thêm MockMvc request chứa HTTP headers/body thật.
2. **Quên spring-boot-starter-validation:** `@NotBlank`/`@Min` xuất hiện trong code nhưng không có validator. Đưa một test input sai và xác minh phải 400.
3. **Không phân biệt conversion với validation:** test `quantity=abc` nhưng mong field error giống `quantity=0`; xác nhận đúng exception path.
4. **Class-level @Validated làm thay đổi path method validation:** tránh nếu muốn kiểm Spring MVC 6.1 built-in HandlerMethodValidationException.
5. **Viết @ExceptionHandler trùng với ResponseEntityExceptionHandler:** có thể gây ambiguous exception mapping; override protected handler đúng loại.
6. **Assert chính xác mọi ký tự message mặc định:** dễ vỡ theo locale/validator version; test contract tự sở hữu.
7. **Quên Content-Type hoặc Accept:** một endpoint `consumes=application/json` có thể trả 415 trước bước body decoding.
8. **Bỏ qua các trường hợp body rỗng và malformed:** chỉ test validation đúng kiểu dữ liệu sẽ thiếu một nhóm 400 quan trọng.
9. **Trả HTTP 200 kèm `{"success":false}` cho validation:** gây nhầm client, caching và metrics; trả 400/422 theo hợp đồng API.
10. **Bọc mọi exception thành HTTP 500 có raw message:** lộ thông tin hệ thống; phân loại lỗi, log nội bộ riêng.
11. **Dùng @WebMvcTest rồi giả định database/transaction thật đã được test:** slice test chỉ bao phủ MVC; thêm service/persistence/integration tests theo rủi ro.
12. **Tắt filters để vượt lỗi 403:** đang che security path thực; test authentication/CSRF có chủ đích.
13. **Mock hết MVC converters:** có thể làm mất Jackson/config thật và tạo false positive; ưu tiên slice dùng configuration production phù hợp.
14. **Giả định mọi 400 trả cùng schema:** MissingServletRequestParameterException, malformed JSON và method validation có thể đi các handler khác; viết API contract chung nếu cần rồi test từng loại.
15. **Không kiểm status-body consistency:** body `status:400` nhưng HTTP line 200 là contract lỗi.
16. **Test chỉ kiểm exception class:** kiểm response JSON và content type mà client thật đọc, vì advice có thể map sai dù exception đúng.

## 11. Ma trận test đề nghị cho một REST controller

| Input/đường đi | Dự kiến | Vì sao cần |
| --- | --- | --- |
| JSON body đầy đủ, hợp lệ | 201/200 với response DTO | Chứng minh mapping và serializer |
| JSON thiếu field bắt buộc | 400 field errors | Chặn dữ liệu thiếu |
| Field blank, âm hoặc vượt min/max | 400 field errors | Chứng minh Bean Validation chạy |
| JSON hỏng syntax | 400 ProblemDetail | Chứng minh lỗi parsing được xử lý |
| JSON field sai kiểu | 400, không gọi business service | Chặn conversion sai |
| Content-Type không hỗ trợ | 415 | Chứng minh media type contract |
| Query parameter không chuyển kiểu | 400 | Binding lỗi ngoài body |
| Thiếu query parameter required | 400 | Không chấp nhận giá trị vắng mặt |
| `@ModelAttribute` không hợp lệ | 400 field errors | Chứng minh binder + validator |
| `@PathVariable` vi phạm `@Min` | 400 | Chứng minh method validation 6.1 |
| Resource không tồn tại | 404 với mã nghiệp vụ | Chứng minh custom ControllerAdvice |
| Lỗi không dự kiến ở service | 500 response không lộ stack trace | Chứng minh error boundary |
| Request không đăng nhập/thiếu quyền | 401/403 nếu có security | Chứng minh filters/advice không phá security |
| Accept không tương thích | 406 khi contract áp dụng | Chứng minh content negotiation |
| Locale vi/en | Messages đúng ngôn ngữ nếu có hỗ trợ | Giảm rủi ro UI/i18n |

Chọn những test phù hợp với thực tế endpoint; mục tiêu không phải tăng số lượng assertion mà là **bao phủ các cơ chế riêng** và bảo vệ hợp đồng mà client đang dựa vào.

## 12. Quy trình khi một test thất bại

1. Đọc HTTP request đã tạo (method, URL, Content-Type, Accept, JSON, query). Lỗi 415 thường xuất hiện trước validation.
2. Đọc **resolved exception** của MockMvc; phân biệt HttpMessageNotReadableException, MethodArgumentNotValidException, HandlerMethodValidationException và lỗi nghiệp vụ.
3. Kiểm tra advice nào được component scan/import, thứ tự `@Order`, xem có mapping trùng hay không.
4. Kiểm tra dependency validation/provider, Bean Validation group, các annotation trực tiếp trên method parameters và vị trí BindingResult.
5. Kiểm tra response HTTP status và body ProblemDetail cùng content type; lỗi negotiation có thể làm body khác dự kiến.
6. Chỉ sau khi xác định nguyên nhân mới sửa code hoặc test; không đơn giản chuyển expected 400 thành 500 để test xanh.
7. Khi thay API contract, test lại consumer expectations, đặc biệt keys `errors`, `code`, `type`, nullable fields và semantics.

## 13. Kết luận

Một bộ kiểm thử Spring MVC đáng tin phải bao quát **HTTP binding → conversion → validation → controller → exception resolver/ControllerAdvice → response ProblemDetail**. `@WebMvcTest` + MockMvc đủ nhẹ để xác minh đa số cơ chế ở tầng MVC, còn service/database/security/transport thật cần được bổ sung bởi những test tương ứng.

`ProblemDetail` giúp tiêu chuẩn hóa thông tin lỗi nhưng không tự sửa thiết kế API: ứng dụng phải nhất quán về status, field errors, mã nghiệp vụ, bảo mật thông tin và thứ tự advice. Điều đặc biệt quan trọng từ Spring 6.1 là xử lý **cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException`**, vì method signature quyết định tầng validation được kích hoạt.

## Tài liệu tham khảo

- Spring Boot 3.3 — Testing Spring Boot Applications / @WebMvcTest: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 API — @WebMvcTest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses / RFC 9457 ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.1 — ProblemDetail Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
