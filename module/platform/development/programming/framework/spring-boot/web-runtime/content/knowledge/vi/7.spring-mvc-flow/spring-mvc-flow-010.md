# Thời điểm phản hồi HTTP được commit và giới hạn thay đổi status/header trong Spring MVC

## 1. Mục tiêu của bài học

Trong Spring Boot dùng Spring MVC và Servlet stack, ứng dụng có thể thiết lập HTTP status, response headers và nội dung trả về qua `ResponseEntity`, annotations, filters, interceptors, `@ExceptionHandler` hoặc trực tiếp với `HttpServletResponse`. Nhưng những thay đổi ấy chỉ có hiệu lực nếu được thực hiện **trước khi phản hồi HTTP được commit**.

Một lỗi phổ biến là ghi hoặc flush một phần body rồi mới muốn đổi status từ 200 sang 500 hoặc thêm header `Location`, `Set-Cookie` hay `Access-Control-Allow-Origin`. Khi phần status và headers đã được gửi theo cơ chế của Servlet container, ứng dụng không thể quay ngược để viết lại chúng.

Sau khi học, bạn cần:
- Hiểu chính xác `committed` nghĩa là gì và phân biệt với việc viết/chạy xong controller.
- Nhận biết những lệnh làm commit response: `flushBuffer()`, flush writer/output stream, buffer đầy, `sendError()` và `sendRedirect()`.
- Phân biệt `setStatus`, `setHeader`, `addHeader`, `reset()` và `resetBuffer()` trước/sau commit.
- Chọn đúng thời điểm thiết lập status/headers trong `DispatcherServlet`, filters, interceptors, `ResponseEntity` và exception handlers.
- Thiết kế xử lý lỗi và streaming hợp lý khi không thể thay status sau khi gửi dữ liệu.
- Kiểm chứng với mã Java 17+ chạy trong Spring Boot 3.x và công cụ HTTP thực tế.

Phạm vi chính là **Spring MVC trên Jakarta Servlet**, thường dùng Tomcat nhúng khi khai báo `spring-boot-starter-web`. WebFlux/Netty có các API và cơ chế commit riêng; không áp dụng nguyên xi `HttpServletResponse` cho WebFlux.

## 2. Commit là gì?

Một HTTP response gồm:
1. **Status:** ví dụ 200 OK, 201 Created, 400 Bad Request, 500 Internal Server Error.
2. **Headers:** ví dụ `Content-Type`, `Location`, `Cache-Control`, `Set-Cookie`.
3. **Body:** JSON, HTML, văn bản, bytes file, các chunk hoặc event.

**Commit** trong Servlet nghĩa là status và response headers đã được ghi ra phía client ở tầng response của server. Theo hợp đồng Jakarta Servlet, `response.isCommitted()` trả `true` khi phản hồi đã commit.

Điều đó dẫn đến hai hệ quả:
- **Trước commit:** trong giới hạn API, có thể thay status, header, loại nội dung và phần body đang buffer.
- **Sau commit:** không thể thay status hoặc các header đã gửi. Vẫn có thể tiếp tục truyền các byte body nếu stream còn mở, nhưng không thể chuyển phần phản hồi đã bắt đầu thành một response lỗi HTTP khác.

Commit **không đồng nghĩa**:
- Controller vừa `return`.
- Đã gọi `response.getWriter()`.
- Đã gọi một lần `writer.write(...)` nhưng dữ liệu vẫn nằm trong buffer.
- Body đã gửi hết hoặc client chắc chắn nhận được mọi byte. Network và reverse proxy có thể còn buffer dữ liệu sau khi container commit.

Trên HTTP/1.1, ta thường nghĩ đến status line + headers được gửi. Trên HTTP/2, thông tin tương đương được mang bởi HEADERS frame và `:status` pseudo-header; giới hạn thay đổi status/headers sau commit vẫn giữ nguyên về mặt ý nghĩa.

## 3. Vòng đời response trong Spring MVC

Dòng xử lý điển hình của một request Servlet đồng bộ:

~~~text
Client
  |
Servlet container (Tomcat / Jetty / Undertow)
  |
Servlet Filter chain
  |  thiết lập một số header trước khi gọi chain
  v
DispatcherServlet
  |
HandlerMapping -> HandlerInterceptor.preHandle
  |
HandlerAdapter -> @Controller / @RestController
  |
Giải quyết return value / exception
  |  ResponseEntity, @ResponseBody, @ResponseStatus
  |  HttpMessageConverter hoặc ViewResolver
  v
Serialize body / render view / ghi servlet response
  |
Buffer / flush / commit
  |
Container gửi bytes qua mạng
  |
Filter trở về / completion callbacks
~~~

Sơ đồ thể hiện tiến trình khái niệm; một số xử lý rendering và ghi response có thể diễn ra trước khi các callback muộn được gọi.

**Vị trí an toàn để chọn status và headers** thường là lúc controller tạo `ResponseEntity` hoặc trước khi bắt đầu ghi body. `HttpMessageConverter` thường chọn representation dựa trên return value và media type, sau đó ghi body. Commit thực tế có thể xảy ra lúc flush, lúc buffer đầy hoặc khi container kết thúc phản hồi; do đó **không có quy tắc “cứ return controller là đã commit”**.

### 3.1. Đối với response JSON thông thường

Ví dụ handler trả:

~~~java
@GetMapping("/items/{id}")
ResponseEntity<ItemDto> get(@PathVariable long id) {
    ItemDto item = service.find(id);
    return ResponseEntity.ok()
            .header("X-Item-Version", "1")
            .body(item);
}
~~~

Đoạn này là fragment của một controller đã có `ItemDto` và `service`, không phải chương trình độc lập. Spring MVC đọc `ResponseEntity`, áp dụng status/headers và chuyển DTO qua `HttpMessageConverter` để serialize. Nếu trong quá trình ghi JSON xảy ra lỗi sau khi buffer đã được flush, exception handler không thể đảm bảo đổi response thành 500 với body JSON lỗi hoàn chỉnh.

### 3.2. Đối với JSP, Thymeleaf hoặc ViewResolver

Với `@Controller` trả về view name, rendering view cũng ghi vào response. Có thể chưa commit khi handler trả về, nhưng view hoặc template lớn có thể làm buffer đầy rồi commit trước khi toàn bộ view hoàn tất. Vì vậy lỗi trong quá trình render có thể xảy ra sau commit.

## 4. Những thao tác khiến response commit

| Thao tác/tình huống | Có gây commit? | Giải thích |
|---|---|---|
| `response.setStatus(201)` | Chưa | Chỉ thay status dự kiến; chưa bắt buộc gửi bytes |
| `response.setHeader(...)` / `addHeader(...)` | Chưa | Thiết lập header trong response chưa commit |
| `response.getWriter()` | Chưa, chỉ vì lấy writer | Có thể khóa lựa chọn character encoding ở thời điểm này |
| `writer.write("abc")` | Không nhất thiết | Có thể giữ trong buffer; nếu đầy, container có thể tự flush và commit |
| `response.getOutputStream().write(...)` | Không nhất thiết | Cùng nguyên tắc buffer và kích thước phản hồi |
| `response.flushBuffer()` | **Có** | Bắt buộc flush buffer; status và headers được commit |
| `writer.flush()` / `outputStream.flush()` | **Có thể làm commit** | Theo hợp đồng flush của response writer/stream, cần coi là điểm gửi dữ liệu |
| Ghi quá dung lượng response buffer | **Có thể tự động commit** | Container có thể flush khi buffer không còn chứa đủ body |
| `response.sendError(...)` | **Có** theo hợp đồng Servlet | Tạo error response và không tiếp tục viết body bằng ứng dụng |
| `response.sendRedirect(...)` | **Có** theo hợp đồng Servlet | Gửi redirect, thiết lập status và `Location` theo API/version |
| Kết thúc request và container hoàn tất phản hồi | Thường có | Nếu chưa được commit trước đó, container sẽ hoàn tất việc gửi response |
| `ResponseEntity.status(...).body(...)` | Không phải commit tức thời | Chỉ mô tả kết quả; ghi/flush body diễn ra trong quá trình xử lý return value |

**Không suy luận commit chỉ bằng số byte đã gọi `write()`**. Kích thước buffer thực tế, serializer, servlet container, filter wrapper và cách streaming có thể làm thay đổi điểm commit.

## 5. Giới hạn thay đổi status và header sau commit

Các API và hậu quả cần nhớ:

| API | Trước commit | Sau commit |
|---|---|---|
| `setStatus(int)` | Thay status của response hiện tại | Không thể thay status đã gửi; lệnh đặt status muộn không có tác dụng |
| `setHeader(name, value)` | Ghi đè các giá trị của header có cùng tên | Không thể sửa header đã gửi; lệnh đặt header muộn không có tác dụng |
| `addHeader(name, value)` | Bổ sung giá trị header | Không thể bổ sung header vào phần đã commit |
| `setContentType(...)` | Cấu hình type trước khi viết, có các ràng buộc về writer/encoding | Không sửa được header `Content-Type` đã gửi |
| `setCharacterEncoding(...)` | Có hiệu lực trước khi response commit và trước khi lấy writer | Thường không có hiệu lực nếu writer đã được lấy, ngay cả khi chưa commit |
| `addCookie(cookie)` | Thêm cookie để phát thành `Set-Cookie` | Không thể phát lại header đã được commit |
| `sendError(status)` | Có thể thay bằng error response, xóa buffer theo hợp đồng | Ném `IllegalStateException` nếu response đã commit |
| `sendRedirect(uri)` | Có thể tạo redirect response | Ném `IllegalStateException` nếu response đã commit |
| `resetBuffer()` | Xóa body đang buffer, giữ status và headers | Ném `IllegalStateException` |
| `reset()` | Xóa buffer, status, headers và reset trạng thái writer/stream theo hợp đồng | Ném `IllegalStateException` |

Điều cần phân biệt là **thay trạng thái response dự kiến** và **phát thông tin ra wire**. Ví dụ `setStatus(404)` trước commit chỉ đổi mã đang chờ gửi; không đồng nghĩa Servlet container tự tạo error page. Nếu muốn container xử lý error response theo cơ chế `sendError` hoặc Spring Boot `/error`, hành vi khác với việc đơn thuần gọi `setStatus`.

### 5.1. `resetBuffer()` khác `reset()`

Giả sử status = 201, header `X-Request-Id` đã được đặt, body `"part A"` vẫn trong buffer và response chưa commit:

~~~java
response.setStatus(201);
response.setHeader("X-Request-Id", "r-42");
response.getWriter().write("part A");

response.resetBuffer(); // xóa body chưa gửi
response.getWriter().write("part B");
// status 201 và X-Request-Id được giữ
~~~

Lệnh `resetBuffer()` không xóa status/header. Trong khi đó `reset()` xóa cả body, status, headers và trạng thái chọn writer/output stream. Sau `reset()`, nếu trước đó đã lấy writer, không nên tiếp tục dùng reference writer cũ; dùng lại theo hợp đồng của Servlet API. Cả hai đều không hợp lệ khi `isCommitted()` đã true.

### 5.2. Chỉnh buffer size

`response.setBufferSize(n)` yêu cầu container cung cấp response buffer ít nhất với kích thước mong muốn; container có thể chọn kích thước lớn hơn. Theo Servlet API, gọi nó sau khi nội dung đã được viết vào response (hoặc sau commit) có thể ném `IllegalStateException`.

Tăng buffer đôi khi trì hoãn commit đối với body vừa phải, nhưng **không phải chiến lược sửa lỗi đúng đắn**. Với file lớn hoặc streaming, cuối cùng vẫn phải commit và gửi từng phần. Nên đảm bảo validate và xác định status trước khi stream, thay vì trông chờ mọi dữ liệu luôn vừa buffer.

## 6. Thời điểm thích hợp trong controller

### 6.1. Chọn status/header ngay trong ResponseEntity

Dùng `ResponseEntity` để nhất quán status, headers và body:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderDto> create(@RequestBody CreateOrder input) {
    OrderDto created = service.create(input);
    URI location = URI.create("/orders/" + created.id());

    return ResponseEntity.created(location)
            .header("Cache-Control", "no-store")
            .body(created);
}
~~~

Đoạn code chỉ minh họa trong một controller đã có `OrderDto`, `CreateOrder` và `service`. Nó trả 201, header `Location` và body sau khi tạo tài nguyên. Các thành phần được cung cấp cho Spring MVC **trước khi** converter bắt đầu ghi body.

Dùng `@ResponseStatus` cho status tĩnh và `ResponseEntity` khi status/headers phụ thuộc kết quả nghiệp vụ. Nếu cần custom header bảo mật, cache, CORS hoặc correlation ID, thiết lập trong filter hoặc response handler thích hợp trước khi ghi nội dung.

### 6.2. Cần tránh thiết lập header sau khi đã ghi body

Đoạn sau có rủi ro:

~~~java
response.getWriter().write(bigPayload);
response.setHeader("X-Trace-Id", traceId);
~~~

Nếu `bigPayload` tràn buffer hoặc writer bị flush, header có thể bị bỏ qua vì response đã commit. Đặt `setHeader` trước khi gọi `write`, `flush` hay đưa body ra converter.

### 6.3. Khi đã viết trực tiếp vào HttpServletResponse

Nếu handler viết vào `HttpServletResponse` và trả `void`, ứng dụng tự quản lý status, headers và body. Không được vừa ghi response bằng `getWriter()` vừa kỳ vọng một `ResponseEntity` được xử lý sau đó sẽ thay được status đã commit. Chọn một cơ chế nhất quán cho mỗi endpoint.

## 7. Thời điểm trong Filter, Interceptor, Advice

Đây là nơi thường phát sinh lỗi vì không phải callback nào cũng chạy trước khi body được gửi.

| Vị trí | Thời điểm trong luồng đồng bộ thông thường | Có an toàn để thêm status/header? |
|---|---|---|
| `Filter.doFilter` **trước** `chain.doFilter` | Trước DispatcherServlet và controller | Thường là điểm phù hợp cho header chung |
| `Filter.doFilter` **sau** `chain.doFilter` | Sau khi downstream đã xử lý; response có thể commit | Không nên dựa vào đó để thêm header bắt buộc |
| `HandlerInterceptor.preHandle` | Trước controller | Có thể thiết lập header trước việc ghi body |
| `HandlerInterceptor.postHandle` | Sau handler; có thể sau xử lý `@ResponseBody`, trước view rendering trong nhiều trường hợp | Không bảo đảm response chưa commit |
| `HandlerInterceptor.afterCompletion` | Cuối xử lý request, phục vụ cleanup/metrics | Thường đã quá muộn để sửa status/header |
| `ResponseBodyAdvice.beforeBodyWrite` | Trước converter viết body ở đường xử lý tương ứng | Phù hợp thay body/header nếu chưa commit; không thay thế chọn status nghiệp vụ từ đầu |
| `@ExceptionHandler` / `@RestControllerAdvice` | Khi Spring MVC giải quyết exception trong phạm vi DispatcherServlet | Có thể tạo error response nếu chưa commit |
| `StreamingResponseBody`, `SseEmitter` | Nội dung tiếp tục được gửi sau khi handler trả về | Có thể commit từ lúc stream bắt đầu; không sửa header muộn |

Ví dụ filter có ý định thêm correlation header:

~~~java
@Component
class CorrelationHeaderFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Correlation-Id", "demo-req");
        chain.doFilter(request, response);
    }
}
~~~

Đây là fragment trong dự án Spring Boot Servlet có imports `jakarta.servlet.*`, `jakarta.servlet.http.*`, `org.springframework.stereotype.Component` và `org.springframework.web.filter.OncePerRequestFilter`.

Không thêm header bắt buộc vào `finally` sau `chain.doFilter`, bởi controller hoặc view có thể đã flush. Với Servlet async dispatch, filter và interceptor có thể được gọi lại theo quy tắc riêng; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` tham gia khi request chuyển sang chế độ async. Việc các callback có chạy lại còn phụ thuộc registration và dispatcher type, nên phải kiểm thử trên runtime đang dùng.

## 8. Khi exception xảy ra trước commit

Ví dụ service ném `OrderNotFoundException` trước khi response viết body, một `@ExceptionHandler` có thể xây dựng response 404/Problem Details:

~~~java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(OrderNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }
}
~~~

Đoạn trên minh họa và cần exception/imports trong project tương ứng. Spring MVC dùng các `HandlerExceptionResolver` để tìm cách xử lý exception. Nếu response chưa commit, framework có thể đặt status/header khác và serialize một body lỗi thống nhất. Một số lỗi Servlet còn được container chuyển đến cơ chế error page của Spring Boot.

Tuy nhiên, không phải mọi exception được ném từ **filter ở ngoài DispatcherServlet** đều tự động được xử lý bởi `@RestControllerAdvice`. Chúng có thể đi qua filter/security/Servlet container error path khác. Hãy chọn đúng tầng chịu trách nhiệm xử lý lỗi.

## 9. Khi exception xảy ra sau commit

Giả sử server đã gửi HTTP 200 và phần đầu của một tệp hoặc JSON:

~~~text
HTTP/1.1 200 OK
Content-Type: application/json

{"items":[{"id":1},
~~~

Sau đó serializer hoặc service streaming ném lỗi. HTTP status và headers đã được gửi. Lúc này:
- Không thể chuyển 200 thành 500 hoặc 400 để phản ánh lỗi.
- Không thể thay một JSON response đang dang dở bằng body Problem Details hoàn chỉnh.
- Nếu gọi `sendError(500)` hoặc `reset()`, Servlet API có thể ném `IllegalStateException`.
- `@ExceptionHandler` không thể đảo ngược dữ liệu đã gửi; Spring MVC có thể log rằng response đã commit hoặc kết thúc stream/kết nối.
- Client có thể nhận body bị cắt giữa chừng; nếu còn framing hợp lệ, client cần cơ chế kiểm tra tính hoàn chỉnh của nội dung.

**Giải pháp:** kiểm tra điều kiện và xác định status trước khi bắt đầu stream; giới hạn lỗi có thể dự đoán; xử lý sự cố giữa stream bằng cơ chế phù hợp với giao thức hoặc đóng kết nối và ghi log. Không cố “trả JSON lỗi mới” sau khi một phần JSON đã rời server.

Với Server-Sent Events (SSE), ứng dụng có thể quy ước một event lỗi nghiệp vụ khi stream còn hoạt động, nhưng **status HTTP ban đầu vẫn giữ nguyên**. Đây là lỗi ở cấp nội dung/giao thức ứng dụng, không phải thay status của response đã commit.

## 10. Streaming, async và trả file

Spring MVC có nhiều hình thức gửi nội dung theo thời gian:
- `StreamingResponseBody`: callback ghi vào `OutputStream`, hữu ích với file hoặc dữ liệu lớn.
- `ResponseBodyEmitter`: phát nhiều đối tượng theo từng đợt.
- `SseEmitter`: hỗ trợ SSE, gửi sự kiện qua kết nối sống lâu.
- `Callable` hoặc `DeferredResult`: cho phép công việc xử lý request hoàn tất bất đồng bộ, rồi Spring MVC thực hiện dispatch để hoàn thiện response.

Trong các kiểu streaming, **thời điểm thực sự commit phụ thuộc lần ghi/flush đầu, buffer và container**. Không được suy luận chỉ từ thời điểm controller tạo ra `SseEmitter` hoặc `StreamingResponseBody`. Cần đặt status, content type, download filename, cache/security headers **trước khi** phát dữ liệu đầu tiên.

Ví dụ minh họa return type của controller (fragment):

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<SseEmitter> events() {
    SseEmitter emitter = new SseEmitter();
    // Đưa emitter cho thành phần quản lý streaming gửi dữ liệu về sau.
    return ResponseEntity.ok()
            .header("Cache-Control", "no-cache")
            .body(emitter);
}
~~~

Đoạn này chưa tự phát events và chưa hoàn tất cơ chế quản lý emitter; mục đích là minh họa đặt status/header trước khi stream. Trong code chạy thật phải tổ chức việc gửi event, timeout, completion/error callback và giải phóng tài nguyên.

Khi gửi file bằng `StreamingResponseBody`, hãy quyết định 404/403/416, `Content-Disposition`, `Content-Type` và phạm vi byte trước khi mở stream. Nếu nguồn dữ liệu bất ngờ hỏng giữa chừng, cách xử lý là đánh dấu kết quả truyền thất bại và giải phóng tài nguyên, không thay status sau khi dữ liệu đã gửi.

## 11. Ví dụ chạy được với Spring Boot 3.x, Java 17+

Ví dụ sau cho thấy hai đường đi:
1. Handler chọn status/header trước khi Spring MVC ghi body.
2. Handler gọi `flushBuffer()` và quan sát rằng các lần sửa status/header tiếp theo **không đổi response đã commit**.
3. Exception trước khi viết body vẫn có thể được ánh xạ sang status 400.

### 11.1. Chuẩn bị project

Tạo Spring Boot 3.x project Java 17+ với dependency `spring-boot-starter-web` (Servlet/Tomcat). Với Maven có thể dùng `pom.xml` đầy đủ sau:

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
    <artifactId>response-commit-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Đặt file Java tại `src/main/java/example/commit/ResponseCommitDemoApplication.java`:

~~~java
package example.commit;

import java.io.IOException;
import java.io.PrintWriter;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResponseCommitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseCommitDemoApplication.class, args);
    }
}

@RestController
class CommitController {

    @GetMapping(value = "/normal", produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> normal() {
        return ResponseEntity.ok()
                .header("X-Stage", "before-body")
                .body("ok\n");
    }

    @GetMapping(value = "/flushed", produces = MediaType.TEXT_PLAIN_VALUE)
    void flushed(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.setHeader("X-Stage", "before-flush");

        PrintWriter writer = response.getWriter();
        writer.write("first chunk\n");

        response.flushBuffer(); // status/headers đã commit
        boolean committed = response.isCommitted();

        // CHỈ ĐỂ MINH HỌA: hai lệnh sau không sửa phần đã gửi.
        response.setStatus(HttpServletResponse.SC_CONFLICT);
        response.setHeader("X-Stage", "after-flush");

        writer.write("committed=" + committed + "\n");
    }

    @GetMapping("/early-error")
    String earlyError() {
        throw new IllegalArgumentException("bad input");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> onBadInput(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .header("X-Error-Source", "exception-handler")
                .body(Map.of("error", exception.getMessage()));
    }
}
~~~

Hai lệnh sửa status/header sau `flushBuffer()` trong `/flushed` chỉ nhằm chứng minh giới hạn Servlet; không sao chép pattern đó vào endpoint production.

### 11.2. Chạy và quan sát

Yêu cầu JDK 17+, Maven và cổng 8080 rảnh. Tại thư mục project:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/normal
curl -i http://localhost:8080/flushed
curl -i http://localhost:8080/early-error
~~~

Các phần kết quả quan trọng (thứ tự header, `Date`, `Connection`, `Content-Length` và cơ chế chunking phụ thuộc container):

| Endpoint | HTTP status thực | Header cần chú ý | Body dự kiến |
|---|---|---|---|
| `/normal` | 200 | `X-Stage: before-body` | `ok` và newline |
| `/flushed` | 200 | `X-Stage: before-flush` | Hai dòng `first chunk` và `committed=true` |
| `/early-error` | 400 | `X-Error-Source: exception-handler` | JSON `{"error":"bad input"}` |

Giải thích:
- `/normal` chọn response trong `ResponseEntity` trước khi converter ghi body.
- `/flushed` buộc commit bằng `flushBuffer()`; `isCommitted()` trả true. Lệnh đặt 409 và header `after-flush` sau đó không thay phần HTTP đã gửi.
- `/early-error` ném exception trước khi viết response, nên local `@ExceptionHandler` tạo status 400 và JSON lỗi.

Không cần đoán thời điểm bộ đệm tự đầy vì ví dụ gọi `flushBuffer()` rõ ràng. Kết quả của phần header/body được kiểm tra bằng HTTP client thực, không dựa vào log controller.

## 12. Kiểm thử response commit

### 12.1. Đơn vị kiểm thử với MockMvc

Khi kiểm thử Spring MVC, khẳng định status và header lẫn body:

~~~java
mockMvc.perform(get("/normal"))
        .andExpect(status().isOk())
        .andExpect(header().string("X-Stage", "before-body"))
        .andExpect(content().string("ok\n"));

mockMvc.perform(get("/early-error"))
        .andExpect(status().isBadRequest())
        .andExpect(header().string(
                "X-Error-Source", "exception-handler"))
        .andExpect(jsonPath("$.error").value("bad input"));
~~~

Đây là **fragment trong lớp test đã cấu hình `MockMvc`**, cần các import static từ `MockMvcRequestBuilders` và `MockMvcResultMatchers`. MockMvc hữu ích để kiểm hợp đồng controller, nhưng dùng mock servlet response, **không thay thế** integration test với embedded container nếu cần xác minh cổng, buffer, flush và dữ liệu thực qua mạng.

### 12.2. Các tình huống kiểm tra nên có

1. **Status success:** tạo tài nguyên trả 201/Location hoặc GET trả 200 kèm cache header đúng.
2. **Validation fail trước ghi body:** có thể trả 400/422 theo hợp đồng lỗi của API.
3. **Exception trong service trước commit:** `@ExceptionHandler` sinh status/body lỗi ổn định.
4. **Writer.flush hoặc flushBuffer:** kiểm tra `isCommitted()` và header muộn không thay được.
5. **Body lớn vượt buffer:** đảm bảo ứng dụng không còn cố đặt status/header từ callback muộn.
6. **Streaming ném lỗi sau chunk đầu:** client có thể nhận response dang dở; log, metric và cleanup chính xác.
7. **Filter/interceptor:** header bắt buộc xuất hiện ngay cả khi controller tự streaming.
8. **Async dispatch:** chú ý filter mapping, timeout, error dispatch và lifecycle callbacks.
9. **Reverse proxy/CDN:** kiểm tra header từ ứng dụng lẫn header bị thêm/sửa ở gateway; cần phân biệt nơi commit.
10. **Client hủy request:** coi IOException khi ghi mạng là tình huống kết nối bị đóng và giải phóng resource phù hợp.

## 13. Gỡ lỗi khi “đã set status/header nhưng client không thấy”

Quy trình rà soát:

1. Ghi nhận status/header mà client thực nhận bằng `curl -i` hoặc trace HTTP. Trên HTTP/2 dùng công cụ có khả năng xem headers và `:status`.
2. Tìm toàn bộ lời gọi `response.flushBuffer()`, `PrintWriter.flush()`, `ServletOutputStream.flush()`, `sendError`, `sendRedirect`, `getWriter` và các đoạn stream lớn.
3. Kiểm tra thứ tự thực tế trong filter, interceptor, `ResponseBodyAdvice` và controller; đặc biệt code đặt header **sau** `chain.doFilter`.
4. Kiểm tra status được xác định ở đâu: `ResponseEntity`, `@ResponseStatus`, exception resolver, security entry point hay container error handling.
5. Log `response.isCommitted()` ngay tại nhánh đang cố sửa response, nhưng không xem việc kiểm tra này là cơ chế sửa chữa trạng thái đã gửi.
6. Nếu body đang stream, kiểm tra độ lớn response, lần flush đầu và đoạn tạo output bị lỗi.
7. Kiểm tra cách proxy hoặc load balancer thay response header sau ứng dụng. Header bị mất ở proxy không nhất thiết do code Spring MVC.
8. Nếu là SSE hoặc download lớn, thiết kế một định dạng kết thúc stream/tín hiệu lỗi cấp nội dung để client nhận biết sự cố.

Thí dụ, filter có `response.setHeader("X-Audit", "done")` trong khối `finally` **sau** `chain.doFilter`. Khi controller trả một file lớn và đã flush, header sẽ không xuất hiện. Chuyển việc thiết lập header đến trước `chain.doFilter` thường giải quyết vấn đề mà không cần can thiệp vào buffer.

**Lưu ý bảo mật:** không log session cookies, access token hoặc dữ liệu nhạy cảm để debug commit; correlation/request ID và thời điểm commit thường đã đủ hữu ích.

## 14. Các sai lầm thường gặp

1. **“Controller return nghĩa là đã commit.”** Không nhất thiết; còn xử lý return value, converter, view và buffer.
2. **“Gọi writer.write một lần chắc chắn đã commit.”** Chưa chắc; có thể vẫn trong buffer.
3. **“Chưa gửi hết body thì còn đổi status được.”** Sai: chỉ cần status/headers đã commit là không đổi được.
4. **“setStatus(500) sau flushBuffer sẽ trả 500.”** Sai: client đã có status trước đó.
5. **“Có @ControllerAdvice thì lỗi nào cũng thành JSON chuẩn.”** Không thể thay status/body đã commit; lỗi ở filter ngoài DispatcherServlet còn có đường xử lý khác.
6. **“Tăng buffer vô hạn giải quyết lỗi.”** Không: streaming, payload lớn và memory/latency vẫn là vấn đề.
7. **“resetBuffer có thể dùng sau commit.”** Sai: Servlet API ném IllegalStateException.
8. **“setHeader ở filter finally luôn có hiệu lực.”** Sai: downstream có thể đã flush.
9. **“ResponseBodyAdvice chắc chắn sửa được header.”** Chỉ khi response chưa commit ở thời điểm callback.
10. **“Có thể đổi JSON giữa chừng thành Problem Details.”** Không an toàn khi đã gửi phần body trước.
11. **“Mọi Spring MVC async handler commit ngay khi return.”** Thời điểm commit phụ thuộc body writer, flush, buffer và lifecycle async.
12. **“Đọc server.port trong Environment là cách kiểm tra commit.”** Đây là thông số cổng; nó không phản ánh trạng thái từng HTTP response.

## 15. Checklist thiết kế endpoint và middleware

- [ ] Status thành công/thất bại được xác định trước khi ghi dữ liệu.
- [ ] Header `Content-Type`, cache, CORS, security, cookie và correlation ID được thiết lập đủ sớm.
- [ ] Nếu dùng `ResponseEntity`, status/headers/body thống nhất với nghiệp vụ và không ghi response thủ công trước đó.
- [ ] Filter thêm header trước `chain.doFilter` khi header đó bắt buộc phải xuất hiện.
- [ ] Không dùng `HandlerInterceptor.afterCompletion` để thay status/header.
- [ ] Hiểu rõ thời điểm flush và các giới hạn của response buffer.
- [ ] Không gọi `reset()`, `resetBuffer()`, `sendError()` hoặc `sendRedirect()` trên response đã commit.
- [ ] Lỗi trước commit được map bằng `@ExceptionHandler` hoặc cơ chế error handling phù hợp.
- [ ] Lỗi sau commit trong streaming có phương án log, cleanup và thông báo cấp nội dung nếu giao thức cho phép.
- [ ] Đã kiểm thử bằng MockMvc và HTTP request thực với embedded container khi cần.
- [ ] Không lộ dữ liệu nhạy cảm qua header/body/log khi xử lý exception.

## 16. Ghi nhớ

**Điểm quyết định là lúc Servlet container commit status và headers, không phải thời điểm controller trả về.** Sau commit, status/header đã gửi không thể sửa; chỉ còn khả năng tiếp tục body hoặc xử lý kết nối/lỗi ở cấp thấp hơn. Trong Spring MVC, hãy chọn status và header ở controller/ResponseEntity hoặc filter trước khi viết body, kiểm tra những đường streaming và exception, và dùng `isCommitted()` để chẩn đoán khi phải xử lý response thủ công.

## Tài liệu tham khảo

- Jakarta Servlet 6.0 API — ServletResponse (flushBuffer, reset, resetBuffer, isCommitted): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse
- Jakarta Servlet 6.0 API — HttpServletResponse (sendError, sendRedirect, status, headers): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponse
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Spring MVC @ResponseBody and HttpMessageConverter: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
