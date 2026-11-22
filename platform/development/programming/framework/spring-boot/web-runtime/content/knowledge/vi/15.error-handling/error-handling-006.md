# ProblemDetail, ErrorResponse và cấu hình Problem Details theo web stack trong Spring Boot

## 1. Mục tiêu bài học

Một REST API không nên mỗi chỗ trả lỗi một kiểu như `{"message":"fail"}`, chuỗi văn bản thuần, HTML error page hoặc stacktrace. Client cần một **hợp đồng lỗi nhất quán** để đọc HTTP status, nhận biết loại lỗi, hiển thị thông báo an toàn và liên hệ log của server khi cần.

Spring Framework hỗ trợ **Problem Details for HTTP APIs** theo **RFC 9457** thông qua ba khái niệm quan trọng:

- `ProblemDetail`: đối tượng mô tả một lỗi HTTP theo các trường chuẩn `type`, `title`, `status`, `detail`, `instance`.
- `ErrorResponse`: hợp đồng Java biểu diễn **status + headers + ProblemDetail body**, thường được các exception của Framework triển khai.
- `ErrorResponseException`: một exception có sẵn thực thi `ErrorResponse`; `ResponseStatusException` là subclass quen thuộc.

Spring Boot cung cấp property để bật xử lý Problem Details cho các exception HTTP đã biết, nhưng **Spring MVC và Spring WebFlux dùng property khác nhau**. Mục tiêu của bài là hiểu cấu trúc RFC 9457, hành vi mặc định, cách cấu hình mỗi stack, cách trả lỗi nghiệp vụ có kiểm soát, bảo mật và kiểm thử.

Ví dụ thực hành chọn **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17**. Ở các major version khác, cần xem lại package, starter, auto-configuration và hành vi xử lý lỗi.

## 2. RFC 9457: một response lỗi có cấu trúc chuẩn

Ví dụ một response API cho tài nguyên không tồn tại:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://example.org/problems/item-not-found",
  "title": "Không tìm thấy mặt hàng",
  "status": 404,
  "detail": "Mặt hàng 27 không tồn tại",
  "instance": "/api/items/27",
  "code": "ITEM_NOT_FOUND"
}
```

Năm thành viên chuẩn của Problem Details:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `type` | URI reference | Xác định **loại** vấn đề; cùng loại lỗi có thể dùng chung URI |
| `title` | String | Mô tả ngắn, thường ổn định cho một loại vấn đề |
| `status` | Integer | HTTP status tương ứng, ví dụ 400, 404, 409, 500 |
| `detail` | String | Mô tả cụ thể hơn cho **lần lỗi** đang xét |
| `instance` | URI reference | Xác định lần xảy ra vấn đề hoặc ngữ cảnh instance của lỗi |

Các trường có thể vắng mặt tùy cách tạo và serialize response; không bắt buộc mọi response phải chứa đủ cả năm. `type` mặc định theo RFC là `about:blank` nếu không được cung cấp, mang ý nghĩa chung theo HTTP status. `status` trong body nên đồng nhất với **HTTP status thực tế**; không tạo response HTTP 200 nhưng JSON lại nói `"status":404`.

`code` trong ví dụ là **extension member** do ứng dụng định nghĩa, không thuộc năm field chuẩn. Dùng `code` ổn định giúp client phân biệt `ITEM_NOT_FOUND`, `EMAIL_ALREADY_USED` hoặc `QUOTA_EXCEEDED` mà không phải phân tích câu văn `detail`.

Media type thường dùng cho JSON là **`application/problem+json`**. Không nhầm với `application/json` thông thường hay `application/problem+xml` khi stack có XML codecs phù hợp.

## 3. ProblemDetail trong Spring Framework

Import:

```java
import org.springframework.http.ProblemDetail;
import org.springframework.http.HttpStatus;
```

Các cách tạo thường dùng:

```java
ProblemDetail a = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

ProblemDetail b = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy tài nguyên");
```

Đặt các field:

```java
b.setTitle("Không tìm thấy tài nguyên");
b.setType(java.net.URI.create(
        "https://example.org/problems/not-found"));
b.setProperty("code", "RESOURCE_NOT_FOUND");
```

Các phương thức đáng nhớ gồm `forStatus(...)`, `forStatusAndDetail(...)`, `getStatus()`, `setTitle(...)`, `setType(...)`, `setDetail(...)`, `setInstance(...)`, `setProperty(...)` và `getProperties()`.

Trong Spring Framework 6.2, khi trả `ProblemDetail` từ `@ExceptionHandler`, Framework có thể tự đặt `instance` theo request path nếu chưa cấu hình. **Đây là hành vi phụ thuộc phiên bản và luồng render**; không tự khẳng định mọi Spring Framework version hoặc mọi response từ `/error` đều có một `instance` giống nhau.

`ProblemDetail` chỉ là object mô tả response. **Tự khởi tạo nó không làm exception tự phát sinh**. Controller phải return nó, return `ResponseEntity<ProblemDetail>`, hoặc ném một exception có cơ chế xử lý phù hợp.

`type` không nhất thiết phải trỏ đến một website đang hoạt động, nhưng với public API nên chọn URI ổn định do tổ chức quản lý, có trang hướng dẫn nếu có thể. URL `https://example.org/problems/...` trong bài chỉ là địa chỉ minh họa.

## 4. ErrorResponse: không đồng nghĩa với ProblemDetail

`ErrorResponse` là interface tại:

```java
import org.springframework.web.ErrorResponse;
```

Các phương thức quan trọng:

| API | Ý nghĩa |
|---|---|
| `getStatusCode()` | HTTP status của response |
| `getHeaders()` | HTTP response headers đi kèm |
| `getBody()` | `ProblemDetail` mô tả lỗi |
| `getTypeMessageCode()` | Message code dùng để quốc tế hóa `type` |
| `getTitleMessageCode()` | Message code dùng để quốc tế hóa `title` |
| `getDetailMessageCode()` | Message code dùng để quốc tế hóa `detail` |
| `getDetailMessageArguments()` | Các argument cho message được địa phương hóa |

Điểm khác biệt:

- **`ProblemDetail`** là phần body theo RFC 9457.
- **`ErrorResponse`** là hợp đồng chứa **HTTP status, headers và body**, giúp Spring Framework thể hiện một exception thành HTTP response có cấu trúc.
- `ErrorResponse` là một interface Java, không phải JSON field hay một endpoint `/error`.
- Nhiều built-in web exceptions của Spring MVC/WebFlux triển khai `ErrorResponse`, cho phép giữ status và headers chuẩn của exception.

Ví dụ lỗi `405 Method Not Allowed` có thể cần response header `Allow`; không nên tự viết tất cả lỗi 405 thành `ProblemDetail` mà làm mất header chuẩn. `ErrorResponse` giữ được cả headers cần thiết.

## 5. ErrorResponseException và ResponseStatusException

`ErrorResponseException` là implementation sẵn có của `ErrorResponse`, có constructor nhận status và `ProblemDetail`:

```java
ProblemDetail conflict = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Mã mặt hàng đã được sử dụng");
conflict.setType(java.net.URI.create(
        "https://example.org/problems/item-code-conflict"));
conflict.setProperty("code", "ITEM_CODE_CONFLICT");

throw new org.springframework.web.ErrorResponseException(
        HttpStatus.CONFLICT, conflict, null);
```

Code này là fragment **bên trong method**; cần `HttpStatus`, `ProblemDetail` imports. Constructor thứ ba là cause, ở đây `null`. Khi exception được bộ xử lý `ErrorResponse` phù hợp tiếp nhận, HTTP status là **409 Conflict**, body theo cấu trúc Problem Details. Không tự bảo đảm mọi filter/proxy có thể xử lý exception này khi nó được ném bên ngoài handler.

`ResponseStatusException` thường phù hợp cho những trường hợp đơn giản:

```java
throw new org.springframework.web.server.ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy mặt hàng");
```

Trong Spring Framework 6.2, `ResponseStatusException` extends `ErrorResponseException`; giá trị `reason` được dùng làm `detail` mặc định. Nếu cần `type` URI, `code` hoặc các property bổ sung, dùng một `ProblemDetail` tùy chỉnh hoặc exception chuyên biệt.

Đối với lỗi nghiệp vụ tái sử dụng ở nhiều controller, nên có exception hoặc error code riêng thay vì lặp `ResponseStatusException` kèm chuỗi message không ổn định.

## 6. Bật Problem Details theo Spring Boot web stack

Trong **Spring Boot 3.5**, các property sau có ý nghĩa rõ ràng:

| Web stack | Property | Giá trị mặc định 3.5 | Khi bật |
|---|---|---|---|
| Spring MVC/Servlet | `spring.mvc.problemdetails.enabled` | `false` | Auto-configure xử lý Problem Details cho built-in MVC exceptions |
| Spring WebFlux/Reactive | `spring.webflux.problemdetails.enabled` | `false` | Auto-configure xử lý Problem Details cho built-in WebFlux exceptions |

Ví dụ project **Spring MVC**:

```properties
spring.mvc.problemdetails.enabled=true
```

Ví dụ project **Spring WebFlux**:

```properties
spring.webflux.problemdetails.enabled=true
```

Hoặc YAML:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

Với project WebFlux, đổi nhánh `mvc` thành `webflux`.

**Không đặt cả hai property một cách máy móc** khi chỉ có một web stack: property của stack không được chọn không làm thay đổi exception handling của stack đang hoạt động. Nếu một ứng dụng có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên **SERVLET/MVC**, dù classpath có WebClient. Kiểm tra dependency tree và `WebApplicationType` trước khi điều tra vì sao bật WebFlux property không có hiệu lực.

Bật Problem Details không có nghĩa **mọi exception bất kỳ** của ứng dụng, lỗi trong filter hoặc lỗi do reverse proxy trả ra đều được chuyển thành RFC 9457. Cần phân biệt các tầng ở các mục tiếp theo.

## 7. Luồng xử lý lỗi trong Spring MVC

Luồng đơn giản với `@RestController`:

```text
HTTP request
    |
    v
Servlet Filter Chain
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> HandlerAdapter -> Controller
    |
    +-- thành công --> HttpMessageConverter --> response
    |
    +-- exception
           |
           v
     HandlerExceptionResolver chain
        |
        +-- @ExceptionHandler / @ControllerAdvice
        +-- ResponseStatusExceptionResolver
        +-- DefaultHandlerExceptionResolver
           |
           v
     ProblemDetail / ErrorResponse hoặc response theo handler
           |
           v
     HTTP status + headers + body
```

Spring Boot cũng có đường xử lý lỗi **`/error`** với `BasicErrorController` và `ErrorAttributes` cho những lỗi được container/Framework chuyển sang error dispatch. Khi bật `spring.mvc.problemdetails.enabled=true`, Boot auto-configure `ResponseEntityExceptionHandler` xử lý những built-in MVC exceptions theo Problem Details. Điều này **không thay thế toàn bộ cơ chế `/error`** trong mọi trường hợp.

Ví dụ lỗi tại controller được xử lý bởi `@RestControllerAdvice` sẽ được biến thành response ngay trong quá trình MVC exception resolution. Nhưng exception xảy ra **trước khi vào DispatcherServlet** (Servlet filter, servlet container) có thể đi theo đường khác.

Thứ tự xử lý quan trọng: custom `@ControllerAdvice` cho cùng loại exception cần có order phù hợp, đặc biệt khi Spring Boot đã đăng ký Problem Details handler với order **0**.

## 8. Luồng xử lý lỗi trong Spring WebFlux

Spring WebFlux dùng `DispatcherHandler` chứ không phải `DispatcherServlet`:

```text
HTTP request
    |
    v
Reactive web server (thường Reactor Netty)
    |
    v
HttpHandler + WebFilter chain
    |
    v
DispatcherHandler
    |
    +-- annotated @RestController / functional RouterFunction
    |
    +-- exception hoặc Mono.error(...)
           |
           +-- @ExceptionHandler / @RestControllerAdvice
           |
           +-- WebExceptionHandler / ErrorWebExceptionHandler
           |
           v
     ProblemDetail / ServerResponse / response phù hợp
```

Spring Boot reactive có error handler dựa trên `ErrorWebExceptionHandler`; `DefaultErrorWebExceptionHandler` và `ErrorAttributes` cung cấp cơ chế lỗi mặc định khi không có handler thích hợp. Bật `spring.webflux.problemdetails.enabled=true` sẽ bổ sung xử lý RFC 9457 cho những built-in WebFlux exceptions trong controller stack.

Phân biệt ba nhóm:

1. **Annotated controllers:** dùng `@ExceptionHandler`/`@RestControllerAdvice`; Spring WebFlux hỗ trợ `ProblemDetail`.
2. **Functional endpoints:** có thể xử lý lỗi bằng các operator Reactor, handler functions, hoặc để exception đi tới reactive error infrastructure.
3. **WebFilter/HTTP server/parser:** lỗi có thể phát sinh trước khi controller handler được chọn; không phải mọi lỗi đi qua `@RestControllerAdvice`.

Không gọi `.block()` trong WebFlux handler chỉ để xây dựng error response; trả `Mono.error(...)`, `ProblemDetail` hoặc `Mono<ResponseEntity<...>>` theo kiểu method phù hợp.

## 9. Trả ProblemDetail từ @ExceptionHandler

Một cách linh hoạt là bắt exception nghiệp vụ và return `ProblemDetail`:

```java
@ExceptionHandler(ItemNotFoundException.class)
public ProblemDetail handleNotFound(ItemNotFoundException ex) {
    ProblemDetail pd = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy mặt hàng " + ex.getItemId());
    pd.setTitle("Không tìm thấy mặt hàng");
    pd.setType(URI.create(
            "https://example.org/problems/item-not-found"));
    pd.setProperty("code", "ITEM_NOT_FOUND");
    return pd;
}
```

Đoạn này là method trong một class `@RestControllerAdvice`, cần class `ItemNotFoundException` có `getItemId()`, import `URI`, `ProblemDetail`, `HttpStatus` và `ExceptionHandler`. Ví dụ đầy đủ cho MVC nằm ở các mục dưới.

Khi return `ProblemDetail`, Spring Framework 6.2 sử dụng `status` của đối tượng để thiết lập HTTP status và ưu tiên các media types chuyên biệt như `application/problem+json` khi JSON serialization có mặt.

**Đừng trả `ResponseEntity.ok(problem)`** nếu `problem.getStatus()` là 404: một response HTTP **200** với body mô tả 404 là không nhất quán. Nếu muốn dùng `ResponseEntity`, đặt status tương ứng:

```java
return ResponseEntity.status(HttpStatus.NOT_FOUND).body(pd);
```

Nếu cần các header như `Retry-After`, `WWW-Authenticate` hoặc `Allow`, giữ những header bắt buộc đúng theo HTTP contract. Không tự thay thế built-in exception response chỉ để đổi title/message nếu làm mất headers quan trọng.

## 10. Spring Boot MVC: project mẫu Java 17

Tạo project Maven **Spring Boot 3.5.x**, Java 17, có parent hoặc dependency management của Boot. Dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Đây là phần `<dependencies>` cho `pom.xml` đã được Spring Boot quản lý phiên bản, không phải toàn bộ POM độc lập.

Cấu trúc:

```text
src/main/java/com/example/problem/mvc/
    MvcApplication.java
    ItemController.java
    ItemNotFoundException.java
    ItemProblemAdvice.java
src/main/resources/
    application.properties
src/test/java/com/example/problem/mvc/
    ItemControllerTest.java
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.problemdetails.enabled=true

# Tránh để mặc định lộ exception/stacktrace trong /error
server.error.include-exception=false
server.error.include-stacktrace=never
server.error.include-message=never
```

Các property `server.error.*` liên quan cơ chế error attributes của Boot, không phải cách tùy chỉnh mọi `ProblemDetail` được tạo bởi `@ExceptionHandler`. Khi muốn thay nội dung Problem Details hãy dùng advice/MessageSource hoặc những cơ chế extension phù hợp.

## 11. MVC: class main và domain exception

File `src/main/java/com/example/problem/mvc/MvcApplication.java`:

```java
package com.example.problem.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
```

File `src/main/java/com/example/problem/mvc/ItemNotFoundException.java`:

```java
package com.example.problem.mvc;

public class ItemNotFoundException extends RuntimeException {

    private final long itemId;

    public ItemNotFoundException(long itemId) {
        super("Item not found");
        this.itemId = itemId;
    }

    public long getItemId() {
        return itemId;
    }
}
```

Exception này chỉ lưu `itemId` để advice tạo response có kiểm soát. Không nhét dữ liệu nhạy cảm, SQL exception hoặc token vào `detail` cho client. Nếu cần log lỗi gốc, log ở server với request ID, không công khai toàn bộ `exception.getMessage()`.

## 12. MVC: @RestController và validate request

File `src/main/java/com/example/problem/mvc/ItemController.java`:

```java
package com.example.problem.mvc;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public Item find(@PathVariable("id") long id) {
        if (id == 7) {
            return new Item(7, "Sách Java");
        }
        throw new ItemNotFoundException(id);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> create(
            @Valid @RequestBody NewItem input) {
        Item created = new Item(8, input.name());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    public record Item(long id, String name) {
    }

    public record NewItem(@NotBlank String name) {
    }
}
```

Controller này chỉ minh họa error handling:

- `GET /api/items/7` trả JSON bình thường.
- `GET /api/items/27` ném `ItemNotFoundException` để advice trả Problem Details.
- `POST /api/items` nhận JSON và chạy `@Valid` trên `NewItem`.
- JSON có `name` rỗng dẫn tới validation error; với `spring.mvc.problemdetails.enabled=true`, built-in MVC exception handler có thể trả Problem Details 400.
- Ví dụ không có database, việc tạo item ID 8 chỉ để minh họa; không xem đây là service lưu mặt hàng hoàn chỉnh.

## 13. MVC: @RestControllerAdvice cho lỗi nghiệp vụ

File `src/main/java/com/example/problem/mvc/ItemProblemAdvice.java`:

```java
package com.example.problem.mvc;

import java.net.URI;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(-1)
public class ItemProblemAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ProblemDetail itemNotFound(ItemNotFoundException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy mặt hàng " + ex.getItemId());

        pd.setTitle("Không tìm thấy mặt hàng");
        pd.setType(URI.create(
                "https://example.org/problems/item-not-found"));
        pd.setProperty("code", "ITEM_NOT_FOUND");
        return pd;
    }
}
```

`@Order(-1)` giúp advice này được xét trước Boot Problem Details advice mặc định có order 0 (ở Boot 3.5). Trong demo, advice chỉ nhận `ItemNotFoundException`, không bắt mọi `RuntimeException` hoặc `Exception`. Những lỗi framework như validation, wrong HTTP method vẫn có thể được handler mặc định xử lý.

Nếu một hệ thống có nhiều `@ControllerAdvice`, cần kiểm tra order và phạm vi các advice. Không tạo một catch-all ở `@Order(HIGHEST_PRECEDENCE)` rồi bất ngờ biến `MethodArgumentNotValidException`, `HttpRequestMethodNotSupportedException` thành 500.

Khi Jackson serialize `ProblemDetail`, các property mở rộng được đưa lên top-level JSON nhờ `ProblemDetailJacksonMixin` do Spring đăng ký. Ví dụ response có thêm `"code":"ITEM_NOT_FOUND"`, không phải mặc định luôn có object `"properties":{...}`.

## 14. Chạy và kiểm tra MVC bằng curl

Ở thư mục project đã có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Request hợp lệ:

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
```

Body mong đợi:

```json
{"id":7,"name":"Sách Java"}
```

Request không có item:

```bash
curl -i -H 'Accept: application/problem+json' \
  http://localhost:8080/api/items/27
```

Trong setup mẫu, HTTP status là 404, `Content-Type` tương thích `application/problem+json`; các field chính có thể là:

```json
{
  "type": "https://example.org/problems/item-not-found",
  "title": "Không tìm thấy mặt hàng",
  "status": 404,
  "detail": "Không tìm thấy mặt hàng 27",
  "instance": "/api/items/27",
  "code": "ITEM_NOT_FOUND"
}
```

`instance` trong Spring Framework 6.2 được điền từ path nếu response đi qua `@ExceptionHandler` và chưa được đặt. Nếu sử dụng version khác, test theo kết quả framework thực tế và RFC contract thay vì coi một chi tiết mặc định là bất biến.

Request body không hợp lệ:

```bash
curl -i -X POST \
  -H 'Accept: application/problem+json' \
  -H 'Content-Type: application/json' \
  --data '{"name":""}' \
  http://localhost:8080/api/items
```

Với Bean Validation provider được cài, kết quả thường là HTTP 400 theo built-in exception handling. Không dự đoán chính xác `detail` của validation error: nó có thể thay đổi theo locale, cấu hình MessageSource hoặc Spring Framework version.

Request JSON đúng:

```bash
curl -i -X POST \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  --data '{"name":"Bút"}' \
  http://localhost:8080/api/items
```

Mong đợi 201 Created, body:

```json
{"id":8,"name":"Bút"}
```

Các response code/body ở đây giả định request tới thẳng demo server, không có Spring Security, reverse proxy hoặc custom exception handler bổ sung.

## 15. MockMvc: kiểm thử RFC 9457 trên MVC

Thêm test dependency trong project Maven đã có dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/problem/mvc/ItemControllerTest.java`:

```java
package com.example.problem.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void itemNotFoundReturnsProblem() throws Exception {
        mvc.perform(get("/api/items/27")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
            .andExpect(jsonPath("$.type").value(
                    "https://example.org/problems/item-not-found"));
    }

    @Test
    void beanValidationReturnsBadRequest() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("{\"name\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void validGetReturnsJson() throws Exception {
        mvc.perform(get("/api/items/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Sách Java"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Test chỉ kiểm tra các field thuộc contract đáng tin (status, media type, error code). Không assert toàn bộ JSON hoặc một message i18n khi nó không phải contract ổn định. Để kiểm tra byte-level HTTP behavior, thêm integration test với embedded server thật, bởi MockMvc không cần mở socket.

Nếu có Spring Security trong project, cần cấu hình test authentication/CSRF phù hợp; các test này giả định chưa thêm starter security.

## 16. Spring WebFlux: project reactive riêng

Để minh họa cách cấu hình web stack khác, tạo **project thứ hai** Spring Boot 3.5, Java 17, chỉ có `spring-boot-starter-webflux` và test starter. Không đặt hai ví dụ MVC và WebFlux có cùng route trong cùng một application context.

Trong `pom.xml` đã được Boot quản lý phiên bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Cấu trúc:

```text
src/main/java/com/example/problem/reactive/
    ReactiveApplication.java
    ReactiveItemController.java
    ReactiveProblemAdvice.java
src/main/resources/
    application.properties
src/test/java/com/example/problem/reactive/
    ReactiveItemControllerTest.java
```

File properties:

```properties
server.port=8080
spring.webflux.problemdetails.enabled=true
```

Đây là property đúng cho **Reactive**. Dùng `spring.mvc.problemdetails.enabled=true` trong project reactive không thay thế cấu hình trên.

## 17. WebFlux: class main và controller reactive

File `src/main/java/com/example/problem/reactive/ReactiveApplication.java`:

```java
package com.example.problem.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
```

File `src/main/java/com/example/problem/reactive/ReactiveItemController.java`:

```java
package com.example.problem.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveItemController {

    @GetMapping("/{id}")
    public Mono<Item> get(@PathVariable("id") long id) {
        if (id == 7) {
            return Mono.just(new Item(7, "Sách Java"));
        }
        return Mono.error(new MissingItem(id));
    }

    public record Item(long id, String name) {
    }

    public static class MissingItem extends RuntimeException {
        private final long itemId;

        public MissingItem(long itemId) {
            super("Item not found");
            this.itemId = itemId;
        }

        public long getItemId() {
            return itemId;
        }
    }
}
```

`Mono.error(new MissingItem(id))` tạo error signal trong reactive pipeline. Không gọi `.block()` trong annotated controller.

Trong ứng dụng thật, `Mono<Item>` thường đến từ một reactive repository hoặc upstream `WebClient`; có thể dùng `switchIfEmpty(Mono.error(...))` để chuyển trường hợp không tìm thấy thành exception. Không tự suy diễn rằng `Mono.empty()` luôn trở thành 404: nếu muốn not-found contract, biểu diễn nó rõ ràng.

## 18. WebFlux: @RestControllerAdvice tạo ProblemDetail

File `src/main/java/com/example/problem/reactive/ReactiveProblemAdvice.java`:

```java
package com.example.problem.reactive;

import java.net.URI;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(-1)
public class ReactiveProblemAdvice {

    @ExceptionHandler(ReactiveItemController.MissingItem.class)
    public ProblemDetail notFound(
            ReactiveItemController.MissingItem error) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy mặt hàng " + error.getItemId());

        pd.setTitle("Không tìm thấy mặt hàng");
        pd.setType(URI.create(
                "https://example.org/problems/item-not-found"));
        pd.setProperty("code", "ITEM_NOT_FOUND");
        return pd;
    }
}
```

Đây là một `@RestControllerAdvice` thực tế cho annotated WebFlux controller. Để WebFlux tích hợp built-in errors theo Problem Details, property `spring.webflux.problemdetails.enabled=true` đã được bật.

Handler trả **đối tượng ProblemDetail**, Framework xử lý để tạo HTTP 404. Không phải manually encode JSON, cũng không cần dùng `ResponseEntity.ok(...)`.

Nếu muốn xử lý exception từ **functional WebFlux endpoint**, dùng pipeline `onErrorResume`/ServerResponse hoặc `ErrorWebExceptionHandler` phù hợp. Một `@RestControllerAdvice` không phải giải pháp toàn cục bảo đảm bắt mọi lỗi từ functional routes và WebFilters.

## 19. WebTestClient: kiểm thử WebFlux

File `src/test/java/com/example/problem/reactive/ReactiveItemControllerTest.java`:

```java
package com.example.problem.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveItemControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void missingItemReturnsProblem() {
        client.get()
            .uri("/api/items/27")
            .accept(MediaType.valueOf("application/problem+json"))
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json"))
            .expectBody()
            .jsonPath("$.status").isEqualTo(404)
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void validItemReturnsJson() {
        client.get()
            .uri("/api/items/7")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("Sách Java");
    }
}
```

`RANDOM_PORT` khởi động embedded reactive server trên cổng ngẫu nhiên, giúp test HTTP thực qua server. Tên package test và auto-configuration API ở đây dành cho **Spring Boot 3.5**, không mặc nhiên áp dụng đúng import cho Spring Boot 4.x.

Chạy trong project WebFlux:

```bash
./mvnw test
```

Không nên chạy đồng thời demo MVC và WebFlux cùng `server.port=8080` trên một máy nếu không muốn xung đột port.

## 20. ResponseEntityExceptionHandler: khi nào cần dùng?

Spring Framework cung cấp class `ResponseEntityExceptionHandler` để xử lý những web exceptions phổ biến theo cấu trúc `ErrorResponse`/Problem Details.

Hai web stack có **package khác nhau**:

```java
// Spring MVC
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
```

```java
// Spring WebFlux
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler
```

Hai dòng trên chỉ mô tả **qualified names được xuống dòng để dễ đọc**, không phải import Java hợp lệ nguyên văn. Trong code Java thật, một import phải đặt đầy đủ trên một dòng.

Trong **Boot 3.5**, khi `spring.mvc.problemdetails.enabled=true` hoặc `spring.webflux.problemdetails.enabled=true`, Boot đã auto-configure một `ResponseEntityExceptionHandler` cho built-in errors của stack tương ứng.

Vì vậy:

- Nếu chỉ cần **một vài lỗi nghiệp vụ**, dùng `@RestControllerAdvice` riêng với `@ExceptionHandler(MyDomainException.class)` như ví dụ, tránh chiếm quyền xử lý tất cả built-in exceptions.
- Nếu cần tùy biến **những built-in exceptions cụ thể**, có thể viết advice có thứ tự đứng trước Boot advice (order nhỏ hơn 0), hoặc chủ động quản lý subclass `ResponseEntityExceptionHandler` theo cấu hình của ứng dụng.
- Nếu tự subclass và override nhiều method, hãy dùng chữ ký method của **đúng Spring Framework version**, vì MVC và WebFlux khác tham số (`WebRequest` so với `ServerWebExchange`).
- Tránh nhiều advice cùng bắt `Exception.class` không có thứ tự rõ ràng: dễ biến 400/404 thành 500 hoặc thay đổi response headers ngoài ý muốn.

Một số built-in errors cần giữ status/headers của Framework, ví dụ 405 có `Allow`, 415 có danh sách accepted media types, 401 có `WWW-Authenticate` theo cơ chế security. Một catch-all trả `ProblemDetail.forStatus(INTERNAL_SERVER_ERROR)` cho mọi exception là thiết kế sai.

## 21. Validation errors: 400 không có nghĩa là lỗi nghiệp vụ tùy ý

Với Spring MVC:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
```

Nếu `@Valid` phát hiện Bean Validation violation và không có `BindingResult` bên cạnh để handler xử lý, Spring MVC thường phát `MethodArgumentNotValidException`. Spring Framework 6.1+ có thêm `HandlerMethodValidationException` cho method validation theo quy tắc riêng.

Với WebFlux annotated controllers, một số lỗi binding/validation được biểu diễn bằng `WebExchangeBindException`, hoặc `HandlerMethodValidationException` khi method validation được áp dụng.

Không nên coi `ProblemDetail` built-in mặc định là danh sách field errors có schema công khai ổn định. Nếu frontend cần danh sách lỗi theo field:

```json
{
  "type": "https://example.org/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Hãy sửa những trường được đánh dấu",
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field": "name", "code": "NotBlank"}
  ]
}
```

`violations` là **extension do API thiết kế**, không phải field chuẩn của RFC 9457 hoặc mặc định bảo đảm xuất hiện trong mọi Boot application. Hãy quyết định có cho phép lộ field names và rejected values không; tuyệt đối tránh trả password, access token và raw request body trong lỗi validation.

Với lỗi JSON không parse được, `HttpMessageNotReadableException` (MVC) có thể phát sinh trước khi object được tạo; không lấy nguyên thông điệp parser có chứa payload vào `detail` gửi cho client.

## 22. Bổ sung các trường mở rộng và correlation ID

`ProblemDetail.setProperty("code", "ITEM_NOT_FOUND")` cho phép thêm extension fields. Với Jackson được Spring cấu hình, Map `properties` có thể được **unwrap** thành top-level JSON.

Các extension hay dùng:

- `code`: mã lỗi máy đọc, ổn định xuyên qua phiên bản API.
- `traceId`: định danh trace để liên hệ log/metrics; không đặt dữ liệu nhạy cảm.
- `requestId`: request correlation ID được tạo hoặc xác minh bởi server.
- `violations`: danh sách lỗi field, dùng schema rõ ràng.
- `retryable`: khi có contract rõ ràng về khả năng retry, không tự gắn cho mọi lỗi 500.

Ví dụ:

```java
ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
pd.setProperty("code", "DUPLICATE_ITEM");
pd.setProperty("traceId", traceId);
```

Đoạn trên là fragment; `traceId` phải đến từ hệ thống tracing/observability thật và được kiểm soát. Không cho client tự gửi một header tùy ý rồi đưa nguyên văn nó vào `traceId` mà không kiểm tra.

Trong Spring Framework 6.2 có cơ chế **`ErrorResponse.Interceptor`** để bổ sung hoặc điều chỉnh dữ liệu Problem Details theo một điểm trung tâm. Có thể đăng ký qua `WebMvcConfigurer` hoặc `WebFluxConfigurer` phù hợp. Đây là công cụ hữu ích khi muốn gắn mã theo dõi vào nhiều error responses thay vì copy code trong mọi advice; cần xem đúng callback signature của phiên bản Framework.

## 23. I18n: type, title và detail qua MessageSource

`ErrorResponse` cung cấp message codes để Spring dùng `MessageSource` nội địa hóa thông điệp. Với Spring Framework 6.2, quy tắc mặc định thường dựa vào tên exception đầy đủ:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
```

Trong đó message code cho `detail` có thể có suffix riêng cho các trường hợp như media type không parse được hoặc validation.

Ví dụ application-defined messages trong `src/main/resources/messages_vi.properties`:

```properties
problemDetail.org.springframework.web.bind.MethodArgumentNotValidException=Dữ liệu gửi lên không hợp lệ
```

Dòng trên chỉ là **minh họa cấu trúc message code theo class**; với một built-in exception cụ thể, cần đối chiếu tên class và message arguments thực tế của phiên bản MVC/WebFlux đang chạy. Đặc biệt Spring Framework có nhiều class khác nhau cho request validation và method validation.

`title` thường mô tả loại vấn đề, có thể dịch; `detail` giải thích lần lỗi cụ thể. Tránh dùng văn bản `detail` làm **mã định danh** để frontend viết logic rẽ nhánh vì câu chữ có thể thay đổi theo locale. Client nên dựa vào `type`/extension `code`.

Nếu app dùng locale theo `Accept-Language`, cần kiểm tra thông điệp được chọn và caching headers khi một response có ngôn ngữ khác nhau theo request. Đừng suy đoán mọi exception được tự dịch nếu chưa cấu hình `MessageSource`.

## 24. Phân biệt ErrorResponse, ErrorAttributes và /error

Trong Boot, có nhiều tầng xử lý:

| Thành phần | MVC hay WebFlux? | Vai trò |
|---|---|---|
| `ProblemDetail` | Cả hai | Model body lỗi RFC 9457 |
| `ErrorResponse` | Cả hai | Java contract: HTTP status, headers, ProblemDetail |
| `ErrorResponseException` | Cả hai | Exception thực thi ErrorResponse |
| `ResponseStatusException` | Cả hai | Exception đặt HTTP status/reason |
| `ResponseEntityExceptionHandler` | Mỗi stack có class riêng | Xử lý built-in web exceptions |
| `BasicErrorController` | MVC/Servlet Boot | Xử lý lỗi qua cơ chế `/error` phù hợp |
| `ErrorAttributes` | Boot, có biến thể package | Thu thập dữ liệu cho error response mặc định |
| `ErrorWebExceptionHandler` | WebFlux Boot | Xử lý lỗi trong reactive HTTP handler chain |
| `@RestControllerAdvice` | Annotated controllers | Xử lý exception trong controller pipeline |

`ErrorAttributes` **không phải** `ErrorResponse`. Chỉnh `server.error.include-message=always` không tự tạo Problem Details, và có thể làm lộ message nội bộ trong response từ `/error`. Không bật `server.error.include-stacktrace=always` trong production chỉ vì cần debug.

Khi muốn đổi lỗi domain cho REST controller, ưu tiên advice. Khi muốn kiểm soát error responses từ toàn bộ reactive handler chain (bao gồm functional endpoints hoặc lỗi ngoài controller), cần xem `ErrorWebExceptionHandler`. Trong MVC, xem cơ chế Servlet/filter/container và `/error`.

## 25. HTTP status, Content-Type và content negotiation

RFC 9457 không tự thay thế ngữ nghĩa HTTP. Dùng status phù hợp:

| Status | Tình huống thường gặp |
|---|---|
| 400 Bad Request | Dữ liệu đầu vào sai cú pháp hoặc validation thất bại |
| 401 Unauthorized | Chưa xác thực, có thể cần `WWW-Authenticate` |
| 403 Forbidden | Đã xác định client không được phép truy cập |
| 404 Not Found | Không có tài nguyên hoặc không tiết lộ sự tồn tại theo policy |
| 405 Method Not Allowed | Method không được phép, cần xem `Allow` |
| 409 Conflict | Xung đột với trạng thái tài nguyên hiện tại |
| 415 Unsupported Media Type | `Content-Type` request không được hỗ trợ |
| 422 Unprocessable Content | Payload đúng cú pháp nhưng không xử lý được về mặt ngữ nghĩa theo contract |
| 429 Too Many Requests | Rate limit, có thể thêm `Retry-After` |
| 500 Internal Server Error | Lỗi ngoài dự kiến, không trả chi tiết kỹ thuật |
| 503 Service Unavailable | Hệ thống tạm thời không phục vụ được |

Response JSON theo Problem Details thường dùng `Content-Type: application/problem+json`. Tuy nhiên kết quả thực tế còn phụ thuộc `Accept`, converter/writer, error handler và proxy. Một browser yêu cầu `text/html` có thể nhận trang HTML lỗi theo cơ chế error page nếu request đi vào đường xử lý khác.

**Không tự gắn `Content-Type: application/problem+json` cho mọi exception nếu response body thực tế là HTML hoặc không có body**. Cũng không đặt HTTP 200 cho error chỉ vì method return được một object Java.

Nếu cùng URL có thể trả HTML và JSON tùy `Accept`, cần kiểm tra cache policy và `Vary` phù hợp; nhất là dữ liệu lỗi liên quan người dùng đã đăng nhập.

## 26. Security và ranh giới xử lý ngoại lệ

`@RestControllerAdvice` nằm trong pipeline của annotated controller. Một số lỗi phát sinh ở tầng khác:

- Servlet Filter (trước `DispatcherServlet`).
- Spring Security authentication/authorization.
- Reverse proxy, WAF, gateway hoặc embedded HTTP parser.
- WebFlux `WebFilter`, reactive server và network connection.
- Background job hoặc async task ngoài request-response HTTP lifecycle.

Các lỗi đó **không được bảo đảm** đi qua `@RestControllerAdvice`. Spring Security có `AuthenticationEntryPoint` và `AccessDeniedHandler` phía Servlet; WebFlux có các reactive security handlers tương ứng. Nếu API yêu cầu chuẩn Problem Details cho 401/403, cần cấu hình đúng **security layer** và giữ các headers cần thiết.

Với lỗi 500, không trả `SQLException`, tên bảng, file path, host nội bộ, stacktrace, token, thông điệp từ downstream chưa lọc hoặc request body thô trong `detail`. Client có thể thấy một thông điệp an toàn như `"Đã xảy ra lỗi, vui lòng thử lại"`, còn server log giữ exception đầy đủ kèm correlation ID.

Cẩn thận với `instance`: nếu chứa toàn bộ request URL kèm query string, có thể vô tình lộ token hoặc PII. Một request path đã chuẩn hóa hoặc opaque error occurrence URI an toàn hơn cho public response.

`type` nên được quản lý như một phần **public error contract**, không trỏ đến tài nguyên có thể biến mất theo mỗi deployment.

## 27. Functional WebFlux: ngoại lệ cần được xử lý đúng luồng

Functional endpoints không phải annotated `@RestController`. Một handler có thể trả `Mono<ServerResponse>`:

```java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        RequestPredicates.GET("/api/check"),
        request -> Mono.error(
            new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Request không hợp lệ")));
```

Đây là một **fragment** minh họa, cần imports `RouterFunction`, `ServerResponse`, `RouterFunctions`, `RequestPredicates`, `Mono`, `ResponseStatusException` và `HttpStatus`, và cần được đăng ký như bean trong project WebFlux. Exception sẽ đi qua cơ chế xử lý lỗi reactive tương ứng; không có bảo đảm một `@ExceptionHandler` trong controller advice sẽ bắt mọi trường hợp.

Nếu muốn chủ động dựng response RFC 9457 từ functional route, có thể map exception bằng `onErrorResume` và tạo `ServerResponse.status(...).contentType(MediaType.valueOf("application/problem+json")).bodyValue(problemDetail)` phù hợp. Cần kiểm tra thứ tự xử lý, error status, body writer và cancel behavior.

Với lỗi không xử lý được trong reactive chain, Boot sử dụng `ErrorWebExceptionHandler`. Tùy chỉnh ở tầng này là quyết định kiến trúc rộng, không nên làm chỉ để đổi một thông báo lỗi cho domain exception.

## 28. Kiểm thử ma trận lỗi thực tế

Không chỉ kiểm thử một response 404. Ma trận nên bao gồm:

| Tình huống | Kết quả muốn kiểm chứng |
|---|---|
| Tài nguyên tồn tại | HTTP 200, body JSON bình thường |
| Tài nguyên không tồn tại | HTTP 404, `type`/extension `code` đúng |
| Request JSON thiếu required field | HTTP 400 và `application/problem+json` khi bật xử lý phù hợp |
| JSON không parse được | HTTP 400, không lộ nội dung parser/stacktrace |
| URL thiếu route | Kiểm tra cơ chế 404 và có/không có Problem Details trong runtime thực tế |
| Sai HTTP method | HTTP 405, `Allow` không bị mất |
| Client gửi Content-Type không phù hợp | HTTP 415 |
| Client chỉ yêu cầu media type không được hỗ trợ | Xem 406 và hợp đồng content negotiation |
| Resource conflict | HTTP 409, error code ổn định |
| Lỗi backend bất ngờ | HTTP 500, detail an toàn, log có trace |
| Không có authentication | HTTP 401 từ Security layer, headers đúng |
| Không đủ quyền | HTTP 403 hoặc 404 theo policy, không rò dữ liệu |
| Browser Accept text/html | Xác minh HTML/error page hoặc problem JSON theo contract đã chọn |
| WebFlux functional route | Xác minh không bị bỏ sót bởi advice chỉ dành annotated controller |
| Đổi locale | Dịch `title/detail` nếu thiết kế dùng i18n, giữ `code/type` ổn định |

Có thể dùng `MockMvc` cho MVC controller-level tests, `WebTestClient` cho reactive controller và integration tests cho proxy, security filter, 404 không match và unexpected errors. Nếu test dùng mock framework trực tiếp, không coi đó là bằng chứng mọi error từ embedded server sẽ có cùng body.

## 29. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bật `spring.webflux.problemdetails.enabled` nhưng MVC không thay đổi | App thực tế chạy SERVLET/MVC | Dùng đúng `spring.mvc.problemdetails.enabled` |
| Mọi lỗi vẫn trả format cũ | Property chưa active, advice khác bắt exception hoặc lỗi qua `/error` | Xem profile, condition report và exception handler order |
| Problem JSON `status=404` nhưng HTTP 200 | Code `ResponseEntity.ok(problem)` | Đồng bộ actual HTTP status và body |
| Dùng `@RestControllerAdvice` nhưng 401/403 không đổi | Lỗi từ Spring Security filter chain | Cấu hình security-specific handlers |
| Lỗi functional WebFlux không vào advice | Advice gắn annotated controller infrastructure | Xử lý functional route hoặc reactive error handler |
| Extension `code` không xuất hiện | Object mapper không được Spring cấu hình MixIn hoặc serialization khác | Kiểm tra Jackson setup và `setProperty` |
| Mọi exception thành 500 | Catch-all advice thay xử lý built-in | Chỉ bắt domain exceptions, giữ status/headers |
| `detail` lộ SQL/stacktrace | Dùng `ex.getMessage()` của lỗi nội bộ | Trả thông báo an toàn, log chi tiết trên server |
| 404 không có `application/problem+json` | Error đến từ `/error` hoặc tầng ngoài controller | Test đúng tầng; cấu hình error handler tương ứng |
| XML/HTML xuất hiện bất ngờ | `Accept`/content negotiation hoặc template/error renderer | Xác định media type và converter hoạt động |
| `title/detail` thay đổi theo ngôn ngữ | MessageSource/i18n | Dùng `type`/`code` để rẽ nhánh client |
| Không có instance | Phiên bản/framework path hoặc handler không tự điền | Tự đặt instance an toàn nếu contract yêu cầu |

## 30. Checklist triển khai

1. Xác định ứng dụng chạy **Spring MVC** hay **Spring WebFlux**; không suy đoán chỉ từ dependency WebClient.
2. Bật đúng `spring.mvc.problemdetails.enabled` hoặc `spring.webflux.problemdetails.enabled`.
3. Dùng `ProblemDetail` cho body RFC 9457 và hiểu `ErrorResponse` là contract status+headers+body.
4. Dùng `ErrorResponseException`/`ResponseStatusException` khi cần ném exception mang status rõ ràng.
5. Với domain errors, trả `ProblemDetail` từ advice có exception mapping cụ thể và order phù hợp.
6. Giữ nguyên HTTP status, media type và những response headers quan trọng.
7. Đặt `type` URI và mã `code` ổn định, có tài liệu API contract.
8. Dùng i18n cho `title/detail`, không dùng message text để client rẽ nhánh.
9. Không lộ SQL, stacktrace, secret, token, rejected values nhạy cảm trong error body.
10. Phân biệt annotated controller errors với `/error`, Servlet Filter, WebFilter, Security và proxy errors.
11. Kiểm thử trên đúng stack: MVC `MockMvc`, reactive `WebTestClient`, integration tests cho network/security.
12. Kiểm tra 400/401/403/404/405/409/415/429/500, `application/problem+json`, `Allow`, correlation ID và cache behavior.
13. Khi chuyển Spring Boot major version, xem lại property mặc định, Javadoc và cách đặt `instance`.

## 31. Tổng kết

**`ProblemDetail` mô tả lỗi**, **`ErrorResponse` định nghĩa cách lỗi gắn với status/headers**, còn **Spring Boot Problem Details auto-configuration** giúp chuyển nhiều built-in web exceptions thành response theo RFC 9457.

Trong Spring Boot 3.5, MVC dùng `spring.mvc.problemdetails.enabled=true`; WebFlux dùng `spring.webflux.problemdetails.enabled=true`. Tạo advice nhỏ cho **lỗi nghiệp vụ**, giữ xử lý built-in của Framework, kiểm tra thứ tự `@ControllerAdvice` và không nghĩ rằng một annotation sẽ bắt tất cả lỗi HTTP ở mọi tầng.

Một error contract tốt không chỉ có JSON đẹp: nó phải nhất quán giữa **HTTP status thực, content type, error code, tài liệu type URI, bảo mật, localization và khả năng kiểm thử**.

## 32. Tài liệu tham khảo

- Spring Boot 3.5 — Servlet Error Handling & Problem Details: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Reactive Error Handling & Problem Details: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework 6.2 — Spring MVC Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — Spring WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2 — ProblemDetail Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework 6.2 — ErrorResponse Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/ErrorResponse.html
- Spring Framework 6.2 — ErrorResponseException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/ErrorResponseException.html
- Spring Framework 6.2 — ResponseEntityExceptionHandler (MVC): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 — ResponseEntityExceptionHandler (WebFlux): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
