# Phân biệt lỗi trước handler với lỗi phát sinh khi xử lý kết quả trong Spring Boot

## 1. Tại sao phải xác định lỗi xảy ra ở giai đoạn nào?

Một HTTP request không được chuyển thẳng đến method của controller. Nó có thể bị từ chối trước khi chọn handler, thất bại khi chuyển kiểu tham số, ném exception trong service, hoặc **controller đã return thành công nhưng framework vẫn không serialize được response**. Cùng là HTTP 500, nhưng hai tình huống sau có nguyên nhân và hướng xử lý khác nhau:

- `GET /orders/7` → service ném `IllegalStateException` trước khi trả DTO.
- `GET /orders/7` → controller trả DTO; Jackson gọi getter/custom serializer rồi ném exception khi ghi JSON.

Thêm một phân biệt nữa: khi status và headers **đã commit** (đã phát xuống tầng HTTP), không thể biến phần response đã gửi thành status/body khác, dù framework có bắt được lỗi sau đó.

Bài này thuộc chủ đề **xử lý lỗi** của web runtime, tập trung vào Spring Boot 3.5.x với Spring MVC (Servlet stack), sau đó so sánh Spring WebFlux (reactive stack). Độc giả sẽ có:
- Một mô hình các mốc xử lý request, phân biệt “handler chưa được chọn”, “handler đã được chọn nhưng chưa gọi” và “handler đã trả về nhưng body còn đang ghi”.
- Bảng cơ chế bắt lỗi tương ứng với filter, mapping, argument binding, controller, return-value handler, converter, view và streaming.
- Ví dụ Java 17+ chạy được với Maven, có các request tạo lỗi ở từng mốc và MockMvc tests.
- Cách đọc `HandlerExceptionResolver`, `@RestControllerAdvice`, Servlet error dispatch và `WebExceptionHandler` đúng phạm vi.
- Một checklist gỡ lỗi thực tế, phân biệt response chưa commit và đã commit.

## 2. Định nghĩa chính xác “trước handler”

Từ “trước handler” có hai nghĩa trong trao đổi kỹ thuật:
1. **Handler chưa được chọn**: filter/security hoặc HandlerMapping đang làm việc.
2. **Handler đã được chọn nhưng method chưa thực thi**: argument resolvers đang bind/convert/validate đầu vào.

Nếu chỉ nói “controller không chạy”, cả hai đều đúng, nhưng hệ quả xử lý lỗi rất khác.

| Mốc | Công việc của framework | Ví dụ lỗi | Đã chọn handler? | Đã gọi controller? |
|---|---|---|---|---|
| M0 | Servlet filters, security, gateway nội bộ | Chặn quyền, filter ném exception | Không chắc, thường chưa | Chưa |
| M1 | `HandlerMapping` tìm mapping | 404, 405, 415 hoặc 406 tùy route/media type | Có thể chưa | Chưa |
| M2 | `HandlerAdapter` resolve tham số | `page=abc`, JSON sai, `@Valid` fail | Thường có | Chưa |
| M3 | Handler/controller/service chạy | Không tìm thấy order, conflict nghiệp vụ | Có | Có |
| M4 | Xử lý giá trị trả về / view | `ResponseBodyAdvice`, Jackson, template error | Có | Có, method có thể đã return |
| M5 | Body đang stream và response đã commit | Socket đóng, lỗi ghi chunk sau | Có thể đã xong từ trước | Có thể đã return |

M0–M2 thường được gọi là **pre-controller execution errors**. M4 là **result processing error**. M5 là một trạng thái đặc biệt: lỗi có thể bắt được, nhưng không còn tự do sửa status/header của response.

HTTP status **không phải bằng chứng độc lập về mốc lỗi**. 400 có thể do query conversion, malformed JSON hoặc filter chủ động trả; 500 có thể do service hoặc Jackson serialization.

## 3. Vòng đời Spring MVC: nơi xảy ra từng loại lỗi

~~~text
HTTP request
   |
Servlet container
   |
Servlet Filter chain / Spring Security -------- M0
   |
DispatcherServlet
   |
HandlerMapping (chọn route/handler) ------------ M1
   |
HandlerAdapter
   |
Argument resolvers / conversion / validation -- M2
   |
@Controller / @RestController + service -------- M3
   |
HandlerMethodReturnValueHandler
   |   ResponseEntity / ResponseBodyAdvice
   |   HttpMessageConverter WRITE / ViewResolver
   |   View.render / asynchronous result -------- M4
   |
Servlet response buffer / flush / commit
   |
Streaming / network write ---------------------- M5
   |
HTTP client
~~~

Sơ đồ là khái niệm; một số rendering và streaming có thể diễn ra trong async dispatch hoặc ở thread khác. Đừng suy ra thứ tự của mọi callback chỉ từ vị trí các câu lệnh Java khi dùng bất đồng bộ.

### 3.1. HandlerMapping và lỗi trước khi xác định controller

`HandlerMapping` xét path, HTTP method, headers, `consumes`, `produces` và các điều kiện mapping. Ví dụ:
- Không có URL phù hợp: thường 404.
- Chỉ có GET, client gọi POST: thường 405.
- Endpoint nhận JSON nhưng client gửi `Content-Type: text/plain`: có thể 415.
- Content negotiation không tìm được representation: có thể 406.

Những kết quả này thường xảy ra trước khi controller được gọi. Không phải mọi nhánh đều phát sinh exception giống nhau, và không phải mọi nhánh đều có controller cụ thể để `@ExceptionHandler` cục bộ của nó tham gia.

### 3.2. Argument resolvers và lỗi khi handler đã được chọn

Ví dụ:

~~~java
@GetMapping("/api/parse")
Map<String, Integer> parse(@RequestParam int age) {
    return Map.of("age", age);
}
~~~

Với `GET /api/parse?age=abc`, mapping đã biết `parse` là handler nhưng `"abc"` không convert thành `int`. Lỗi xảy ra **trước khi body của method Java được gọi**, thường biểu hiện thành `MethodArgumentTypeMismatchException` và HTTP 400.

Các ví dụ khác:
- Thiếu `@RequestParam(required=true)`: `MissingServletRequestParameterException`.
- JSON body sai cấu trúc: `HttpMessageNotReadableException`.
- Bean Validation của `@RequestBody`/`@ModelAttribute`: `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException` tùy chữ ký handler.
- Nested data binding thất bại vì type mismatch.

Không gọi các lỗi M2 là “handler không tìm thấy”: đây là lỗi **tạo đối số cho handler đã xác định**.

### 3.3. Lỗi bên trong handler (M3)

Khi method đã bắt đầu, service có thể từ chối nghiệp vụ hoặc lỗi hạ tầng. Ví dụ:

~~~java
@GetMapping("/api/orders/{id}")
OrderView order(@PathVariable long id) {
    return service.findOrder(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}
~~~

Đây là fragment yêu cầu `OrderView`, `service`, `OrderNotFoundException`. Lỗi từ `orElseThrow` xảy ra trong handler, thường nên được map thành 404 bởi một `@ExceptionHandler` biết ngữ cảnh nghiệp vụ. Lỗi connection pool, null pointer hoặc serialization không tự động có nghĩa 404.

## 4. “Handler return” không có nghĩa “response đã trả”

Spring MVC phân tách giá trị do method trả về khỏi cách ghi HTTP result.

Ví dụ:

~~~java
@GetMapping("/api/orders")
ResponseEntity<List<OrderView>> list() {
    return ResponseEntity.ok(service.listOrders());
}
~~~

Sau khi `return`, framework vẫn có thể:
1. Lựa chọn `HandlerMethodReturnValueHandler` theo kiểu trả về.
2. Áp dụng HTTP status và headers của `ResponseEntity`.
3. Chọn media type và `HttpMessageConverter`.
4. Gọi `ResponseBodyAdvice.beforeBodyWrite` nếu có.
5. Serialize Java object thành bytes JSON qua Jackson.
6. Ghi bytes vào Servlet output stream và buffer/flush.
7. Hoàn tất response.

Nếu là `@Controller` trả tên view, `ViewResolver` và template engine còn cần thực hiện `render`. Với `StreamingResponseBody`, `ResponseBodyEmitter` và `SseEmitter`, phần ghi nội dung có thể diễn ra sau thời điểm controller return khá lâu.

### 4.1. Lỗi khi chọn hoặc chạy HttpMessageConverter

Các nguyên nhân:
- Không có converter phù hợp cho return type/media type.
- Custom serializer ném exception.
- DTO có getter lỗi và Jackson truy cập getter lúc viết JSON.
- Jackson gặp object graph/kiểu dữ liệu không thể serialize.
- Converter đã bắt đầu ghi body rồi xuất hiện IOException.

Có thể gặp `HttpMessageNotWritableException`, `JsonMappingException` bọc bên dưới hoặc exception của custom converter. Đừng giả định mọi lỗi converter có class giống nhau.

### 4.2. Lỗi từ ResponseBodyAdvice

`ResponseBodyAdvice` chạy ở bước chuẩn bị ghi body, có thể chỉnh nội dung hoặc ném exception. Đây là một vị trí minh họa **lỗi sau khi controller return** mà không cần làm hỏng một serializer thực tế.

Khi chưa commit, `DispatcherServlet` còn có cơ hội đưa exception đến chuỗi resolver. Khi đã commit, exception handler không thể viết lại status và headers đã gửi.

### 4.3. Lỗi khi render HTML view

Ví dụ controller trả `"orders/detail"`, nhưng Thymeleaf/JSP gặp lỗi template expression hoặc model thiếu dữ liệu. Handler có thể đã return thành công; lỗi nằm ở **view rendering**, không phải ở mapping hay service.

Nếu view đã ghi đủ HTML để response commit trước khi lỗi, một trang lỗi HTML hoàn chỉnh mới không thể thay thế bytes đã gửi. Trong ứng dụng server-rendered, cần kiểm thử cả render thực chứ không chỉ kiểm tra chuỗi view name.

## 5. Lỗi sau khi response đã commit: ranh giới không thể quay lại

Trong Servlet, `HttpServletResponse.isCommitted()` cho biết response đã commit. Các thao tác:

| Thao tác | Có tự commit? | Hệ quả |
|---|---|---|
| `setStatus(...)` / `setHeader(...)` | Chưa nhất thiết | Cập nhật status/headers dự kiến |
| `getWriter()` | Chưa nhất thiết | Lấy writer; có ràng buộc về encoding |
| `writer.write("x")` | Không nhất thiết | Có thể vẫn trong buffer |
| `flushBuffer()` | Có | Status và headers được commit |
| `writer.flush()` / `stream.flush()` | Có thể commit | Cần coi là điểm phát dữ liệu |
| Body đầy buffer | Có thể commit | Tùy kích thước buffer/container |
| `sendError()` / `sendRedirect()` | Commit theo contract tương ứng | Không thể dùng sau commit |
| Container hoàn tất HTTP response | Thông thường commit | Không phải mốc controller return |

Sau commit:
- `setStatus(500)` không đổi được status đã gửi.
- `setHeader` không thể bổ sung header vào phần đã gửi.
- `reset()`, `resetBuffer()`, `sendError()`, `sendRedirect()` có thể ném `IllegalStateException` theo API.
- Client có thể nhận phần body đầu tiên và kết nối bị cắt; không đảm bảo luôn có một JSON lỗi hoàn chỉnh.

Ví dụ:

~~~java
response.setStatus(200);
response.setContentType("text/plain;charset=UTF-8");
response.getWriter().write("first chunk\n");
response.flushBuffer();
throw new IllegalStateException("later failure");
~~~

Dòng cuối ném lỗi sau khi HTTP status 200 đã được commit. Resolver/advice có thể ghi log về lỗi, nhưng **không thể biến bytes đã gửi thành HTTP 500**. Đây là vấn đề protocol, không phải thiếu một annotation nào đó.

Không nhầm `isCommitted=true` ở Servlet container với việc client cuối cùng đã nhận đủ bytes: reverse proxy có thể còn buffer ở phía sau.

## 6. Chain xử lý exception của MVC

Theo hợp đồng Spring MVC, `DispatcherServlet` có thể giao các exception trong quá trình request mapping, handler invocation và xử lý kết quả cho một chuỗi `HandlerExceptionResolver`.

| Resolver / thành phần | Trách nhiệm |
|---|---|
| `ExceptionHandlerExceptionResolver` | Gọi `@ExceptionHandler` ở controller hoặc `@ControllerAdvice`/`@RestControllerAdvice` |
| `ResponseStatusExceptionResolver` | Xử lý `@ResponseStatus` / `ResponseStatusException` |
| `DefaultHandlerExceptionResolver` | Chuyển nhiều lỗi framework MVC thành status thích hợp |
| Custom `HandlerExceptionResolver` | Giải quyết một nhóm lỗi theo chính sách ứng dụng và order |
| Servlet container + Boot `/error` | Fallback khi có status/error dispatch phù hợp hoặc exception chưa giải quyết |

Resolver có thể giải quyết exception hoặc để resolver tiếp theo thử. Một exception được resolver xử lý không nhất thiết luôn tới `/error`; ngược lại, container ERROR dispatch không phải lời gọi trực tiếp đến `@ExceptionHandler`.

### 6.1. @RestControllerAdvice không bao phủ tự động mọi filter exception

Servlet `Filter` chạy **bên ngoài** `DispatcherServlet`. Nếu filter ném exception trước `chain.doFilter`, không thể mặc định một `@RestControllerAdvice` sẽ bắt nó. Trách nhiệm có thể thuộc:
- Filter hoặc Spring Security entry point/denied handler.
- Cơ chế error handling của Servlet container.
- Custom integration chủ động ủy quyền exception vào MVC resolver nếu ứng dụng thực sự cần.

Ngược lại, lỗi bên trong `HandlerMapping` của `DispatcherServlet` có thể tới resolver chain. Một global advice phù hợp có thể tham gia tùy exception; không nên khẳng định “không chọn được handler thì mọi advice đều chắc chắn vô dụng”.

### 6.2. Controller-local và global advice

Nếu handler xác định và có `@ExceptionHandler` cục bộ phù hợp, nó thường được ưu tiên so với global advice. `@RestControllerAdvice` giúp chuẩn hóa response API; `ResponseEntityExceptionHandler` hữu ích khi muốn tùy chỉnh nhiều lỗi MVC chuẩn và Problem Details.

Không dùng một `@ExceptionHandler(Exception.class)` rồi trả cùng HTTP 400 cho mọi lỗi, vì lỗi lập trình, DB hoặc result serialization không phải malformed client input.

## 7. Bảng lựa chọn error strategy theo giai đoạn

| Trường hợp | Controller đã chạy? | Hướng xử lý ưu tiên | Có đổi status lỗi được không? |
|---|---|---|---|
| Filter chặn request | Chưa | Filter/security handler đúng tầng | Có nếu chưa commit |
| Không match route | Chưa | Mapping defaults, global resolver, `/error` tùy trường hợp | Có nếu chưa commit |
| Query/path conversion fail | Chưa | MVC resolver/`@RestControllerAdvice` đúng loại exception | Thường có |
| Malformed JSON body | Chưa | `HttpMessageNotReadableException` handling | Thường có |
| Business rule fail trong controller | Có | `@ExceptionHandler` cho domain exception | Có nếu chưa commit |
| `ResponseBodyAdvice` ném lỗi | Có, đã return | MVC resolver/advice | Có nếu chưa commit |
| Jackson/view render lỗi | Có, đã return | Resolver + error response đơn giản, logs | Phụ thuộc commit |
| Streaming lỗi sau chunk đầu | Có thể đã return từ lâu | Cleanup, logging, tín hiệu lỗi cấp ứng dụng nếu còn khả thi | Không thể đổi status/header đã commit |

**Không xác định nguyên nhân bằng status code một mình.** Cần timeline, exception class/root cause, response commitment và request metadata.

## 8. Demo chạy được với Spring Boot 3.5 và Java 17+

Chương trình tạo năm endpoint:
1. `/api/filter-deny`: filter trả 403 trước DispatcherServlet.
2. `/api/parse?age=abc`: argument resolver không convert được, controller chưa chạy; advice trả 400.
3. `/api/business`: controller ném `BusinessFailure`, advice trả 409.
4. `/api/result?explode=true`: controller trả `ResultPayload`, sau đó `ResponseBodyAdvice` ném `ResultProcessingFailure`; advice trả 500 nếu chưa commit.
5. `/api/late`: controller ghi và flush trước khi ném lỗi; không kỳ vọng một 500 mới.

Việc cố ý ném lỗi trong `ResponseBodyAdvice` là cách **tái hiện lỗi M4 ổn định**, khác với dựa vào một trường hợp serialize Jackson có thể đổi exception theo phiên bản.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>error-stage-demo</artifactId>
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

### 8.2. Source Java đầy đủ

Tạo `src/main/java/example/stages/ErrorStageApplication.java`:

~~~java
package example.stages;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

@SpringBootApplication
public class ErrorStageApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorStageApplication.class, args);
    }
}

class BusinessFailure extends RuntimeException {}
class ResultProcessingFailure extends RuntimeException {}

record ResultPayload(String message, boolean explode) {}

@Component
@Order(-100)
class PreDispatchFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        if ("/api/filter-deny".equals(request.getRequestURI())) {
            response.setStatus(HttpStatus.FORBIDDEN.value());
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("blocked-by-filter");
            return; // không vào DispatcherServlet / controller
        }
        chain.doFilter(request, response);
    }
}

@RestController
@RequestMapping("/api")
class StageController {

    @GetMapping("/parse")
    Map<String, Integer> parse(@RequestParam int age) {
        return Map.of("age", age);
    }

    @GetMapping("/business")
    String business() {
        throw new BusinessFailure();
    }

    @GetMapping("/result")
    ResultPayload result(
            @RequestParam(defaultValue = "false") boolean explode) {
        return new ResultPayload("ready", explode);
    }

    @GetMapping("/late")
    void late(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.OK.value());
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("first chunk\n");
        response.flushBuffer();
        throw new IllegalStateException("failure after commit");
    }
}

@ControllerAdvice
class ResultPhaseAdvice implements ResponseBodyAdvice<Object> {

    @Override
    public boolean supports(
            MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {
        return true;
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> selectedConverterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {

        if (body instanceof ResultPayload payload && payload.explode()) {
            throw new ResultProcessingFailure();
        }
        return body;
    }
}

@RestControllerAdvice
class StageErrors {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<Map<String, String>> badParameter(
            MethodArgumentTypeMismatchException error) {
        return ResponseEntity.badRequest().body(Map.of(
                "phase", "argument-resolution",
                "error", "invalid-parameter"));
    }

    @ExceptionHandler(BusinessFailure.class)
    ResponseEntity<Map<String, String>> business(
            BusinessFailure error) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
                "phase", "handler",
                "error", "business-conflict"));
    }

    @ExceptionHandler(ResultProcessingFailure.class)
    ResponseEntity<Map<String, String>> result(
            ResultProcessingFailure error) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of(
                        "phase", "result-processing",
                        "error", "render-failure"));
    }
}
~~~

Các class package-private cùng `example.stages` được Boot component-scan; chỉ `ErrorStageApplication` là public class trùng tên file. Các exception không có message nhằm tránh leak dữ liệu trong demo. `ResponseBodyAdvice` chỉ ném khi body là `ResultPayload` với `explode=true`; khi error handler trả `Map`, advice không ném lại, tránh vòng lặp lỗi của error response.

`late` chỉ để chứng minh giới hạn sau commit; không được dùng pattern này để thiết kế error handling production.

### 8.3. Chạy và quan sát

~~~bash
mvn spring-boot:run
~~~

Mở terminal khác:

~~~bash
curl -i http://localhost:8080/api/filter-deny
curl -i "http://localhost:8080/api/parse?age=abc"
curl -i http://localhost:8080/api/business
curl -i "http://localhost:8080/api/result?explode=true"
curl -i "http://localhost:8080/api/result?explode=false"
~~~

Kết quả quan trọng (thứ tự JSON keys và một số HTTP headers phụ thuộc runtime):

| Request | Status | Body chính | Giai đoạn |
|---|---:|---|---|
| `/api/filter-deny` | 403 | `blocked-by-filter` | M0 |
| `/api/parse?age=abc` | 400 | JSON `phase=argument-resolution` | M2 |
| `/api/business` | 409 | JSON `phase=handler` | M3 |
| `/api/result?explode=true` | 500 | JSON `phase=result-processing` | M4 |
| `/api/result?explode=false` | 200 | JSON có `message=ready`, `explode=false` | Bình thường |

Gọi `curl -i http://localhost:8080/api/late` riêng để xem tình huống sau `flushBuffer()`. Có thể thấy HTTP 200 và một phần body trước khi stream bị kết thúc; container có thể log exception. **Không** dự đoán một JSON 500 thay cho status đã gửi.

## 9. Kiểm thử MockMvc để phân biệt các giai đoạn

File `src/test/java/example/stages/ErrorStageApplicationTests.java`:

~~~java
package example.stages;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorStageApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void filterRejectsBeforeDispatcher() throws Exception {
        mvc.perform(get("/api/filter-deny"))
                .andExpect(status().isForbidden())
                .andExpect(content().string("blocked-by-filter"));
    }

    @Test
    void argumentConversionFailsBeforeController() throws Exception {
        mvc.perform(get("/api/parse").param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.phase")
                        .value("argument-resolution"));
    }

    @Test
    void handlerExceptionUsesBusinessStatus() throws Exception {
        mvc.perform(get("/api/business"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.phase").value("handler"));
    }

    @Test
    void resultPhaseFailureHappensAfterControllerReturn() throws Exception {
        mvc.perform(get("/api/result").param("explode", "true"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.phase")
                        .value("result-processing"));
    }

    @Test
    void normalResultCanBeSerialized() throws Exception {
        mvc.perform(get("/api/result").param("explode", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("ready"))
                .andExpect(jsonPath("$.explode").value(false));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test này kiểm **HTTP behavior** của ứng dụng MVC thực trong test context. Để chứng minh controller/service không chạy ở nhánh M2 của dự án production, có thể thêm mock service với `verifyNoInteractions(service)`, thay vì chỉ dựa trên body log. Ví dụ demo không cần service.

MockMvc không tái hiện hoàn toàn socket/network/streaming; với lỗi sau commit, nên viết integration test bằng embedded server và HTTP client thật. Không assert rằng một lỗi sau commit sẽ trả JSON 500 mới.

## 10. Spring WebFlux: phân biệt tương tự nhưng error flow reactive

Trên Reactor Netty, Spring WebFlux không dùng `DispatcherServlet` hoặc Servlet `HandlerExceptionResolver`. Luồng khái quát:

~~~text
Reactive HttpHandler
   |
WebExceptionHandler wrappers
   |
WebFilter chain ------------------ lỗi pre-handler
   |
DispatcherHandler
   | HandlerMapping -------------- mapping
   | HandlerAdapter -------------- argument/controller
   | HandlerResultHandler -------- result processing
   |
ServerHttpResponse commit -------- stream/write
~~~

Các điểm quan trọng:
- `WebFilter` có thể phát `Mono.error` trước khi handler được chọn. `@RestControllerAdvice` không nên được xem là catch-all bảo đảm cho mọi lỗi từ filter ngoài phần dispatch.
- `WebExceptionHandler` ở tầng WebHandler chain có thể xử lý lỗi chưa được downstream giải quyết, theo order và contract của nó.
- `HandlerAdapter`/annotated controller của WebFlux có cơ chế xử lý exception, kể cả một số lỗi khi xử lý `HandlerResult`; `DispatcherHandler` cũng có `DispatchExceptionHandler` trong các trường hợp framework hỗ trợ.
- Controller có thể trả `Mono<T>` hoặc `Flux<T>` trước khi reactive work thực sự được subscribe và thực thi.
- `ServerHttpResponse.isCommitted()` vẫn quyết định có thể sửa status/header hay không. Nếu stream đã emit và commit, không có “quay lại” để tạo một HTTP 500 hoàn chỉnh.

Ví dụ fragment:

~~~java
@GetMapping("/events")
Flux<ServerSentEvent<String>> events() {
    return service.events();
}
~~~

Đây là đoạn minh họa trong WebFlux controller có `service` và imports. Exception từ `service.events()` có thể xuất hiện khi publisher được subscribe, sau thời điểm method return. Với SSE, có thể gửi event lỗi **cấp giao thức ứng dụng** nếu stream còn hoạt động, nhưng status HTTP đã commit không đổi.

### 10.1. onErrorResume không phải nút reset response

~~~java
return service.load()
        .onErrorResume(ProductNotFoundException.class,
                ex -> Mono.empty());
~~~

Fragment này chuyển lỗi thành completion rỗng, có thể tạo HTTP 200 với body trống nếu không thiết kế status rõ. Khi đã gửi chunk đầu, `onErrorResume` không thể thu hồi phần status/header/body đã nhận. Với lỗi domain cần 404, chọn response trước khi bắt đầu ghi body hoặc dùng error handling tương ứng của handler.

### 10.2. beforeCommit trong WebFlux

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Request-Observed", "yes");
    return Mono.empty();
});
~~~

Đây là fragment trong `WebFilter` có `ServerWebExchange exchange` và import `Mono`. Callback cần đăng ký sớm. `beforeCommit` là nơi chuẩn bị thông tin trước commit, không phải cơ chế đổi status sau khi stream đã phát dữ liệu.

## 11. Cách thiết kế error responses theo tầng

**Filter/security:** xử lý 401/403 đúng trách nhiệm, dùng authentication entry point/access denied handler nếu ứng dụng có Spring Security. Không trông chờ controller advice xử lý mọi lần từ chối trước mapping.

**Argument binding:** 400 khi request sai cú pháp/chuyển kiểu; 415 khi media type không được hỗ trợ; 405/406 theo hợp đồng routing/negotiation. Không đưa stack trace hay raw payload nhạy cảm vào response.

**Business handler:** map domain exceptions sang status đúng, như 404 khi không tìm thấy tài nguyên, 409 khi conflict. Lỗi hạ tầng thường không phải 400.

**Result processing:** ghi nguyên nhân thực sự (converter, serializer, `ResponseBodyAdvice`, view), tránh vòng lặp khi error response cũng không serialize được. Trả error DTO đơn giản và kiểm tra khả năng response đã commit.

**After commit/streaming:** không cố `sendError` hoặc `resetBuffer` để ghi response mới. Log theo correlation ID, cleanup, ngừng stream hoặc phát tín hiệu lỗi cấp nội dung nếu giao thức cho phép.

Với Spring MVC, `ProblemDetail` và `ResponseEntityExceptionHandler` có thể cung cấp hợp đồng lỗi thống nhất, nhưng không thay thế error handling của filter/security hay cơ chế commit HTTP.

## 12. Quy trình debug khi “controller đã chạy nhưng client nhận 500”

1. Ghi method/path, headers cơ bản, trace ID và status HTTP thực từ client bằng `curl -i`.
2. Kiểm tra filter/security đã quyết định response chưa; controller log có xuất hiện không.
3. Kiểm tra HandlerMapping đã chọn handler nào; nếu không có thì xem 404/405/415/406.
4. Nếu method chưa chạy, xem argument conversion, validation, `@RequestBody` deserialize.
5. Nếu method đã return, xem `HandlerMethodReturnValueHandler`, `ResponseBodyAdvice`, `HttpMessageConverter`, view rendering.
6. Nếu streaming, tìm thời điểm ghi body và `flushBuffer`; log `response.isCommitted()` tại nơi xử lý exception.
7. Kiểm tra có `HandlerExceptionResolver` hoặc controller advice khác đã bắt exception trước không; có `/error` dispatch không.
8. Tìm root cause thay vì chỉ outer exception; serializer, database và client disconnect có thể cùng xuất hiện với status 500 trong log.
9. Kiểm tra error DTO có tự gây lỗi khi converter xử lý lần thứ hai không.
10. Dùng MockMvc/WebTestClient cho HTTP semantics và integration test thật nếu liên quan commit, proxy, async hoặc network.

Nên log `requestId`, tên handler khi có, stage M0–M5, exception class, root cause, response committed và elapsed time. Tránh log access token, cookie hoặc toàn bộ body chứa dữ liệu nhạy cảm.

## 13. Những sai lầm phổ biến

1. **“Lỗi trước controller đồng nghĩa không tìm thấy handler.”** Sai: argument binding có thể fail sau mapping.
2. **“Controller return là HTTP response hoàn tất.”** Sai: còn converter, advice, view, async.
3. **“@RestControllerAdvice bắt được mọi lỗi Servlet Filter.”** Không tự động.
4. **“Mọi HTTP 400 là Bean Validation.”** Có thể do conversion, JSON malformed, missing parameter.
5. **“Mọi 500 là service/database.”** Có thể do Jackson hoặc view rendering sau return.
6. **“Chưa gửi hết body thì đổi status được.”** Sai khi đã commit headers/status.
7. **“sendError sau flush có thể sửa lỗi.”** Có thể ném `IllegalStateException`.
8. **“Exception handler luôn tạo được body mới.”** Converter của error DTO cũng có thể fail, hoặc response đã commit.
9. **“Dùng Exception.class để trả 400 cho mọi lỗi.”** Che lỗi hệ thống và phá hợp đồng HTTP.
10. **“WebFlux exception luôn xảy ra trước khi method return.”** Publisher thường lazy.
11. **“onErrorResume sửa được HTTP status sau chunk đầu.”** Không thể thu hồi bytes đã gửi.
12. **“MockMvc mô phỏng mọi lỗi mạng.”** Phải dùng HTTP integration test với container thật cho commit/stream.
13. **“Cứ thấy controller log là chắc lỗi nằm trong controller.”** Log có thể trước bước serialize.
14. **“Không thấy log controller nghĩa là request không vào Spring.”** Filter/mapping/binding có thể xử lý trước.
15. **“Có route 404 thì @ExceptionHandler của controller nào đó luôn chạy.”** Không có bảo đảm khi handler chưa được chọn.
16. **“Bật stack trace trong error JSON cho dễ debug.”** Có thể tiết lộ dữ liệu nhạy cảm.
17. **“Lỗi lúc render view giống lỗi validation input.”** Khác giai đoạn, nguyên nhân và chiến lược phục hồi.

## 14. Checklist triển khai error handling

- [ ] Xác định rõ filter, mapping, argument, handler, result và committed response.
- [ ] Không trộn lẫn “handler đã chọn” với “controller method đã chạy”.
- [ ] Có test 400 do conversion, 409/404 do nghiệp vụ, 500 do result processing.
- [ ] Lỗi của filter/security được xử lý trong phạm vi phù hợp.
- [ ] Controller advice chỉ bắt các exception có chủ đích, không ép mọi lỗi thành 400.
- [ ] Error response DTO đủ đơn giản, tránh lặp lỗi serializer.
- [ ] Có kiểm thử path có body converter, template hoặc async streaming.
- [ ] Không cố sửa status/header sau commit.
- [ ] Có logging/tracing và cleanup khi streaming bị lỗi.
- [ ] Có HTTP integration tests khi cần kiểm tra network, buffer hoặc reverse proxy.
- [ ] Nếu dùng WebFlux, phân biệt reactive error signal với method return.
- [ ] Không đưa bí mật hoặc stack traces vào response production.

## 15. Kết luận

**Giai đoạn lỗi quan trọng ngang với loại exception.** Lỗi từ Servlet filter trước dispatcher, lỗi mapping/binding trước controller, lỗi trong business handler và lỗi serialize/render sau khi controller return là những tình huống khác nhau. Spring MVC có `HandlerExceptionResolver` để giải quyết nhiều lỗi trong dispatch; WebFlux có pipeline reactive với `WebExceptionHandler` và cơ chế xử lý result riêng. Dù ở stack nào, response **đã commit** thì status và headers không thể sửa lại. Muốn xử lý đúng, cần xác nhận timeline, tìm handler thực sự đã chạy đến mốc nào, kiểm root cause và kiểm thử kết quả qua HTTP.

## Tài liệu tham khảo chính thức

- Spring Framework — Spring MVC exception resolvers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — @ExceptionHandler: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC return values: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — MVC async/streaming: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework — WebFlux exception handling: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html
- Jakarta Servlet — HttpServletResponse: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponse
