# Phân biệt ngoại lệ trong controller với lỗi ở Filter hoặc Servlet container

## 1. Bài toán: cùng HTTP 500 nhưng có thể đi qua ba cơ chế khác nhau

Trong một ứng dụng Spring MVC chạy trên Servlet stack, request không đi thẳng vào `@RestController`. Servlet container (Tomcat, Jetty hoặc Undertow tùy cấu hình), một chuỗi `Filter`, `DispatcherServlet`, HandlerMapping, HandlerAdapter và controller có các vùng chịu trách nhiệm khác nhau. Khi lỗi xảy ra, **nơi lỗi phát sinh và đường đi của request** quyết định thành phần nào có cơ hội xử lý.

Mục tiêu bài học:

- Vẽ được luồng `client → Servlet container → FilterChain → DispatcherServlet → controller` và luồng phản hồi quay lại.
- Phân biệt ngoại lệ ném **bên trong MVC dispatch**, ngoại lệ ném **trước/sau `chain.doFilter` trong Filter**, và lỗi do **Servlet container** tự phát hiện.
- Hiểu phạm vi `@ExceptionHandler`, `@RestControllerAdvice`, `HandlerExceptionResolver`, `ResponseEntityExceptionHandler`, `/error`, `ErrorController`.
- Phân biệt `response.setStatus`, `response.sendError`, ném exception, `forward` và `ERROR dispatch`; không đánh đồng mọi status 4xx/5xx với Java exception.
- Giải thích ngoại lệ Spring Security, thứ tự Filter, `DispatcherType`, lỗi response đã commit và lỗi xử lý async.
- Tự dựng ví dụ Java 17+, Spring Boot 3.x/Spring Framework 6.x, kiểm thử MockMvc và HTTP thực, đồng thời biết giới hạn của từng loại test.

**Phạm vi:** Spring MVC trên Jakarta Servlet stack. Spring WebFlux dùng WebFilter/WebExceptionHandler và cơ chế khác; nội dung này không áp dụng nguyên xi cho WebFlux.

## 2. Sơ đồ đường đi của request và ba “biên giới”

```text
Client
  |
  v
HTTP connector / Servlet container
  |   - parse request line, headers
  |   - giới hạn request, chọn Servlet/filter mapping
  v
Servlet Filter A  ----> có thể chặn request / trả response / throw
  |
  v
Servlet Filter B  ----> có thể chặn request / trả response / throw
  |
  v
Spring Security FilterChainProxy (nếu bật)
  |   - authentication, authorization, CSRF, ...
  v
DispatcherServlet
  |   HandlerMapping -> HandlerAdapter -> Controller
  |                 \-> HandlerInterceptor
  |   HandlerExceptionResolver chain khi MVC dispatch lỗi
  v
Controller -> Service -> Repository
  |
  v
HttpMessageConverter / view rendering
  |
  +---- Response đi ngược qua filters về container/client

Nếu exception/status không được xử lý tại lớp hiện tại:
  -> Servlet container error handling / ERROR dispatch
  -> endpoint /error của Spring Boot (nếu đã cấu hình và match)
  -> HTML/JSON/error body hoặc container fallback tùy ứng dụng
```

Sơ đồ đơn giản hóa: filter ngoài security và filter bên trong `SecurityFilterChain` không nhất thiết xuất hiện theo một thứ tự cố định giống hình; thứ tự đăng ký và matching mới quyết định. `HandlerInterceptor` nằm **bên trong** vòng đời `DispatcherServlet`, còn Servlet `Filter` nằm **bên ngoài** vòng đời xử lý MVC thông thường.

### Ba trường hợp cần nhận diện

1. **MVC exception:** `@GetMapping` gọi service rồi ném `OrderBlockedException`. Nó nảy sinh khi `DispatcherServlet` đang điều phối handler; Spring MVC có thể chọn `@ExceptionHandler`/`@RestControllerAdvice`.
2. **Filter exception:** một custom Servlet Filter ném `ServletException` trước khi gọi `chain.doFilter`. MVC chưa nhận request, nên `@RestControllerAdvice` **không tự động bắt được ngoại lệ ban đầu**.
3. **Container-level error:** Tomcat từ chối request không hợp lệ, giới hạn kích thước, timeout/connection lỗi hoặc Servlet dispatch thất bại; một số sự cố xảy ra **trước khi có Servlet request/filter**. Không có bảo đảm chúng đi qua controller hay Spring MVC advice.

**Nguyên tắc chẩn đoán:** HTTP status chỉ cho biết kết quả giao thức; nó không chứng minh đã có Java exception, cũng không xác định lớp tạo response. Ví dụ 403 có thể do Spring Security, filter tự `sendError`, controller chủ động trả 403 hoặc gateway ở phía trước.

## 3. Ngoại lệ bên trong DispatcherServlet: HandlerExceptionResolver

Trong một MVC dispatch, `DispatcherServlet` phối hợp các bộ giải quyết ngoại lệ (`HandlerExceptionResolver`). Khi exception trong quá trình mapping/handling/rendering được xử lý qua đường MVC thích hợp, một resolver có thể tạo response, error view hoặc báo không xử lý được.

Các resolver phổ biến:

| Cơ chế | Vai trò | Ghi chú |
| --- | --- | --- |
| `ExceptionHandlerExceptionResolver` | Tìm `@ExceptionHandler` trong controller hoặc `@ControllerAdvice` / `@RestControllerAdvice` | Thường dùng để định dạng lỗi JSON |
| `ResponseStatusExceptionResolver` | Xử lý `@ResponseStatus` hoặc `ResponseStatusException` và cơ chế `ErrorResponse` liên quan | Status và error handling tùy phiên bản |
| `DefaultHandlerExceptionResolver` | Ánh xạ các exception Spring MVC phổ biến sang status HTTP | Ví dụ sai method, media type, input |
| `ResponseEntityExceptionHandler` | Lớp cơ sở tiện lợi cho `@ControllerAdvice` để tùy chỉnh các lỗi MVC chuẩn | Không phải Servlet Filter toàn cục |

Đây là **chuỗi các resolver**, có độ ưu tiên và khả năng thay thế/tùy chỉnh. Một resolver có thể trả `null` để nhường cho resolver tiếp theo, trả `ModelAndView` hoặc báo ngoại lệ đã được xử lý.

Ví dụ controller ném business exception:

```java
@GetMapping("/orders/{id}")
public OrderResponse read(@PathVariable long id) {
    if (id == 13) {
        throw new OrderBlockedException("Order blocked");
    }
    return new OrderResponse(id, "READY");
}
```

Đoạn này thuộc controller minh họa, không phải tệp Java độc lập. `@RestControllerAdvice` có `@ExceptionHandler(OrderBlockedException.class)` có thể trả JSON lỗi và `409 Conflict` cho lỗi này. Service cũng có thể ném exception và vẫn được advice xử lý **nếu exception lan tới MVC dispatch mà chưa bị xử lý ở nơi khác**.

Không nên nói advice chỉ bắt `throw` trực tiếp trong method controller: exception phát sinh ở service, argument resolution, interceptor hoặc phần xử lý MVC thích hợp cũng có thể được các resolver xử lý. Ranh giới chính là **MVC dispatch và việc exception thực sự đi qua resolver chain**, không đơn thuần là tên package hay file Java.

## 4. Ngoại lệ ở Filter: lý do advice không tự động bắt

Servlet API chạy các `Filter` được đăng ký trên một URL và `DispatcherType` phù hợp. Filter có thể:

- Kiểm tra request rồi **gọi** `chain.doFilter(request, response)` để chuyển tiếp.
- Kiểm tra và **không gọi chain**; tự trả status/body, chuyển hướng hoặc từ chối.
- Ném `IOException`, `ServletException` hoặc unchecked exception trong xử lý trước/sau chain.
- Bọc request/response, đặt header, ghi metrics, giải nén, kiểm tra rate limit hoặc authentication.

Ví dụ:

```java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {
    if (request.getRequestURI().endsWith("/blocked")) {
        throw new ServletException("Failure in outer filter");
    }
    chain.doFilter(request, response);
}
```

Đây là **minh họa** trong subclass `OncePerRequestFilter` đã có imports; không tự biên dịch một mình. Nếu exception bị ném **trước `chain.doFilter`**, `DispatcherServlet` chưa được gọi và `@RestControllerAdvice` không nằm trên call stack để xử lý exception đó. Nếu exception nảy sinh **sau khi `chain.doFilter` trả về**, code đang chạy trở lại trong Filter và cũng nằm ngoài MVC dispatch.

Đặc biệt: filter có thể bắt ngoại lệ từ `chain.doFilter` bằng `try/catch`. Nhưng controller exceptions thường đã được MVC resolver xử lý trước khi quay lại filter. Vì vậy **filter không chắc nhìn thấy mọi ngoại lệ controller**, và advice không chắc thấy mọi ngoại lệ filter.

`OncePerRequestFilter` giúp kiểm soát thực thi trong những kiểu dispatch theo hợp đồng của lớp, nhưng **không đồng nghĩa chỉ chạy một lần trong toàn bộ đời sống request** với mọi tổ hợp thread/async/error dispatcher. Kiểm tra cách đăng ký và các hook `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()` nếu có dispatch lại.

### Không “đẩy” exception vào controller bằng cách gọi chain lần nữa

Sau khi filter gặp lỗi, việc gọi `chain.doFilter` thêm lần nữa có thể chạy lại handler, gây tác dụng phụ hoặc ghi response hai lần. Nếu muốn xử lý filter error thành API JSON, hãy chọn một trong các cách sau **một cách có chủ đích**:

1. Cho filter dùng một **error writer** riêng biết đúng HTTP status/body.
2. Từ filter gọi `HandlerExceptionResolver.resolveException(...)` mà Spring MVC cung cấp **một cách chủ động**; cách này cần kiểm soát resolver, `handler=null`, nội dung exception và response chưa commit.
3. Sử dụng `response.sendError(...)` để kích hoạt **container error handling** (nếu có mapping), sau đó để `/error`/container xây response.
4. Đối với authentication/authorization, để **Spring Security** xử lý qua `AuthenticationEntryPoint` và `AccessDeniedHandler` đúng vị trí.

Các hướng trên phục vụ mục đích khác nhau. Đừng thêm một `catch (Exception e)` trong mọi filter rồi tự trả 200 hay nuốt lỗi, và đừng gọi `@RestControllerAdvice` như một Java utility class: nó là thành phần có vòng đời và ngữ cảnh của Spring MVC.

## 5. setStatus, sendError, throw và response đã commit

Ba hành động có semantics khác nhau:

### 5.1. `response.setStatus(503)`

Đặt mã status cho response; **không tự bảo đảm** có container error dispatch. Ứng dụng có thể tiếp tục ghi JSON/body của riêng mình, hoặc hoàn tất response rỗng. Chỉ status 503 chưa chứng tỏ Java exception đã xảy ra.

### 5.2. `response.sendError(503, "reason")`

Theo Servlet API, đây là tín hiệu gửi error status cho container để thực hiện error handling tương ứng, nếu response chưa committed. Với Spring Boot servlet app có default error mapping, sau `sendError` server thật thường dùng cơ chế error page và có thể chuyển tới `/error` dưới dạng `DispatcherType.ERROR`. Nội dung/body phụ thuộc container, Boot, content negotiation và cấu hình bảo mật.

Đừng mặc định `sendError` luôn cho ra một JSON duy nhất trên Tomcat/Jetty/MockMvc, và đừng gọi `sendError` sau khi đã ghi/commit response.

### 5.3. `throw new ServletException(...)`

Ném exception lên thành phần gọi `Filter` hoặc Servlet. Nếu không ai xử lý, container có thể xử lý error page, ghi lỗi và trả 500. Nhưng ngoại lệ có thể bị filter khác/interceptor/container xử lý trước; không có bảo đảm Spring MVC advice sẽ được gọi.

### 5.4. Response committed

Response có thể được **commit** khi flush buffer, gửi header/body, stream dữ liệu hoặc vượt buffer. Sau đó status/header thường không còn có thể thay đổi như trước. `sendError` trên response đã commit có thể ném `IllegalStateException`; cố ghi lỗi JSON sau khi gửi một phần body có thể tạo response lỗi hoặc cắt kết nối.

Ví dụ anti-pattern:

```java
response.getWriter().write("partial data");
response.flushBuffer();
response.sendError(500, "failure"); // có thể IllegalStateException
```

Đây là đoạn minh họa trong Servlet/Filter method; **không** dùng production. Với streaming (`StreamingResponseBody`, `SseEmitter`, servlet output stream), nếu thất bại giữa chừng thường không còn cơ hội thay thành JSON lỗi chuẩn. Thiết kế protocol phát sự kiện/error riêng hoặc đóng stream và log, cùng telemetry phù hợp.

## 6. ERROR dispatch và endpoint /error của Spring Boot

Servlet container có thể ánh xạ lỗi tới một error page/resource. Khi error handling **dispatch** đến error page, request hiện tại có `DispatcherType.ERROR` và có thể mang các Servlet request attributes mô tả lỗi gốc.

Các thuộc tính thường dùng:

| Attribute | Nội dung |
| --- | --- |
| `jakarta.servlet.error.status_code` | HTTP status khởi phát error dispatch |
| `jakarta.servlet.error.request_uri` | URI của request ban đầu |
| `jakarta.servlet.error.exception` | Exception gây lỗi, nếu có |
| `jakarta.servlet.error.message` | Thông điệp lỗi khi có |
| `jakarta.servlet.error.servlet_name` | Servlet gốc khi có |

Các attribute là cơ chế **container error dispatch**. Chúng không bắt buộc xuất hiện ở mọi response 4xx/5xx — chẳng hạn controller trả `ResponseEntity.status(404)` trực tiếp và không có error dispatch.

Trong Spring Boot Servlet MVC, auto-configuration thường cung cấp endpoint `/error`, `BasicErrorController` và `ErrorAttributes` để tạo HTML hoặc machine-readable error response cho những tình huống đi qua error handling path. Nó không có nghĩa **mọi** exception đã nảy sinh từ `@Controller` sẽ đến `/error`: nếu `@ExceptionHandler`/resolver đã xử lý và ghi response, không cần một error dispatch khác.

Một đường đi điển hình:

```text
REQUEST dispatcher
  -> Filter
  -> response.sendError(503) hoặc unresolved exception
  -> container xử lý error-page mapping

ERROR dispatcher (nếu cấu hình và còn xử lý được)
  -> các Filter áp dụng cho ERROR (có thể khác REQUEST)
  -> DispatcherServlet
  -> /error (Boot BasicErrorController nếu được đăng ký)
  -> error response
```

Spring Boot có `ErrorPageFilter` cho một số trường hợp triển khai WAR với Servlet container bên ngoài, nhưng **không nhầm nó với mọi application filter** hay mặc định cơ chế mà mọi ứng dụng embedded Tomcat phải đi qua. Cách cụ thể phải xem hình thức deployment.

Trong Spring Boot 3, tên thuộc tính Servlet dùng namespace `jakarta.servlet.*`, không phải `javax.servlet.*` của dự án Boot 2 cũ.

## 7. Filter khi ERROR dispatch: tránh xử lý lặp

`DispatcherType` trong Jakarta Servlet có các giá trị `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`. Container chọn filter dựa trên mapping và dispatcher types đã đăng ký.

Nếu một filter kiểm tra authentication/logging cho `REQUEST` và được đăng ký cả `ERROR`, nó có thể chạy lần thứ hai trên error dispatch. Tình huống thường thấy:

- Original request `/api/payments` bị từ chối trước MVC.
- Container tạo `ERROR` dispatch tới `/error`.
- Authentication filter lại chặn `/error` hoặc custom filter lại ném exception.
- Client thấy 403/500 khác hẳn lỗi ban đầu; log có thể bị ghi hai lần hoặc vòng lặp error handling.

Cần quyết định rõ:

1. Filter nào áp dụng `REQUEST`? Filter nào cần `ASYNC` hoặc `ERROR`?
2. Với `OncePerRequestFilter`, override `shouldNotFilterErrorDispatch()`/`shouldNotFilterAsyncDispatch()` phù hợp với mục đích và thiết kế bảo mật.
3. Nếu error endpoint phải phục vụ cho request bị từ chối, cần cấu hình security authorization phù hợp; không mở các endpoint nhạy cảm ngoài phạm vi.
4. Khi đặt trace/correlation ID, sử dụng request attribute hoặc context truyền tiếp thích hợp qua các dispatch; tránh tạo ID mới cho cùng một request một cách vô tình.

**Không nên cho mọi filter chạy ERROR bằng mặc định**. Đồng thời không loại bỏ mọi security check trên ERROR dispatch nếu nó có thể dẫn đến lộ lỗi nội bộ. Chọn theo hợp đồng và kiểm thử end-to-end.

## 8. Spring Security: exception thuộc filter chain riêng

Spring Security Servlet dựa trên `FilterChainProxy` và các security filters. Hai luồng lỗi trọng yếu:

- **Authentication failure / người gọi chưa xác thực:** `AuthenticationEntryPoint` thường khởi động cơ chế yêu cầu đăng nhập hoặc trả 401. Tùy cơ chế có thể redirect, Basic challenge hoặc JSON; không mặc định mọi ứng dụng trả JSON 401.
- **Authenticated nhưng không có quyền:** `AccessDeniedHandler` thường trả 403.
- `ExceptionTranslationFilter` dịch `AuthenticationException` và `AccessDeniedException` từ phần thích hợp của **security filter chain phía sau nó** thành hành vi HTTP tương ứng.

Không được kết luận rằng `@ExceptionHandler(AuthenticationException.class)` trong controller advice sẽ xử lý tất cả lỗi Spring Security: nhiều lỗi xảy ra **trước MVC dispatch**. Ngược lại, một business exception trong controller có thể do advice xử lý mà `ExceptionTranslationFilter` không tham gia.

Đặc biệt:

- `ExceptionTranslationFilter` không bắt tùy ý mọi lỗi `RuntimeException`; nó dành cho nhóm exception authentication/authorization và các đường xử lý hỗ trợ.
- Không mọi Filter trong `SecurityFilterChain` đều chạy **sau** `ExceptionTranslationFilter`. Thứ tự quan trọng. Authentication filter phía trước có thể tự gọi failure handler; dùng architecture/debug logs để xác định thực tế.
- `CsrfFilter` có thể chặn POST trước khi controller; response 403 khi thiếu CSRF token không phải lỗi từ `@Valid @RequestBody`.
- CORS preflight `OPTIONS` có thể bị chặn ở security/filter khi cấu hình sai; không suy ra controller không hỗ trợ OPTIONS.
- Những exception từ method security trong controller/service có thể đi qua cơ chế riêng tùy proxy/advice/MVC và vị trí gọi. Chẩn đoán bằng **stack trace**, filter order và resolved exception; đừng gắn mọi AccessDeniedException với một công đoạn duy nhất.
- Nếu API định nghĩa cấu trúc lỗi JSON đồng nhất, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` (hoặc error writer chuyên dụng) theo contract, đồng thời giữ header liên quan authentication theo chuẩn.

## 9. Xây ví dụ Java 17+ để quan sát ba nguồn lỗi

Ứng dụng demo minh họa cụ thể:

- `GET /demo/ok` → controller trả 200.
- `GET /demo/controller-fail` → controller ném `DemoBusinessException`, `@RestControllerAdvice` bắt và trả JSON `409`.
- `GET /demo/filter-send-error` → Filter **không gọi MVC**, dùng `sendError(503)`; container error handling có thể xử lý `/error`.
- `GET /demo/filter-throw` → Filter ném `ServletException` **trước DispatcherServlet**; advice không bắt trực tiếp lỗi gốc; container có thể trả 500 khi xử lý HTTP thực.
- `GET /demo/missing` → URL không có mapping chuyên biệt, thường 404, không nhất thiết có business exception.

Dùng dự án Maven Spring Boot **3.x + Spring Web**, Java 17+ và starter test. Trên Boot 3, import Servlet từ `jakarta.servlet.*`. Đặt các lớp sau cùng package `com.example.demo`.

### 9.1. Lớp khởi động

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.2. Exception nghiệp vụ

Tệp `src/main/java/com/example/demo/DemoBusinessException.java`:

```java
package com.example.demo;

public class DemoBusinessException extends RuntimeException {
    public DemoBusinessException(String message) {
        super(message);
    }
}
```

Đây là lỗi dùng riêng cho demo, không phải tên exception chuẩn của Spring. Trong ứng dụng thật, không nên quyết định status HTTP chỉ bằng việc mọi exception đều là `RuntimeException`; cần mã lỗi nghiệp vụ cụ thể.

### 9.3. Controller và DTO trả về

Tệp `src/main/java/com/example/demo/DemoController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/demo/ok")
    public Result ok() {
        return new Result("OK");
    }

    @GetMapping("/demo/controller-fail")
    public Result controllerFail() {
        throw new DemoBusinessException("Order cannot be changed");
    }

    @GetMapping("/demo/filter-send-error")
    public Result filterSendError() {
        // Nếu Filter chặn đúng, method này không được gọi.
        return new Result("SHOULD_NOT_REACH_CONTROLLER");
    }

    @GetMapping("/demo/filter-throw")
    public Result filterThrow() {
        // Nếu Filter ném lỗi trước chain, method này không được gọi.
        return new Result("SHOULD_NOT_REACH_CONTROLLER");
    }

    public record Result(String state) {}
}
```

### 9.4. @RestControllerAdvice cho lỗi MVC

Tệp `src/main/java/com/example/demo/DemoExceptionAdvice.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DemoExceptionAdvice {

    @ExceptionHandler(DemoBusinessException.class)
    public ResponseEntity<ApiError> onBusinessError(
            DemoBusinessException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ORDER_BLOCKED",
                ex.getMessage(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    public record ApiError(
            String code,
            String message,
            String path) {}
}
```

Với `/demo/controller-fail`, response JSON thể hiện cấu trúc `ApiError` và status `409 Conflict`. Không làm `@ExceptionHandler(Exception.class)` bắt tất cả lỗi mà tự động trả 400/409; việc đó che lỗi lập trình nghiêm trọng và làm mất đúng semantics 500.

Trong ứng dụng thật, `ex.getMessage()` có thể chứa dữ liệu nội bộ hoặc thông tin người dùng; chỉ sử dụng thông điệp đã được thiết kế an toàn công khai. Ở demo, chuỗi exception cố định do code đặt, không lấy từ stack trace hay SQL.

### 9.5. Filter nằm trước DispatcherServlet

Tệp `src/main/java/com/example/demo/DemoBoundaryFilter.java`:

```java
package com.example.demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DemoBoundaryFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI()
                .substring(request.getContextPath().length());

        if ("/demo/filter-send-error".equals(path)) {
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Simulated failure in servlet filter");
            return;
        }

        if ("/demo/filter-throw".equals(path)) {
            throw new ServletException("Failure before MVC dispatcher");
        }

        chain.doFilter(request, response);
    }
}
```

Giải thích:

- `@Component` đăng ký một Servlet Filter bean trong Spring Boot, `@Order` đặt thứ tự. Ứng dụng thật có security/filter khác; thứ tự chính xác cần xem các registration.
- Cả hai nhánh lỗi xảy ra **trước** `chain.doFilter`, nên controller không chạy.
- Với `sendError`, Filter không ném exception; container thực có thể kích hoạt error dispatch tới `/error`.
- Với `throw`, exception thoát Filter; MVC resolver không được gọi cho lỗi gốc.
- `substring(contextPath.length())` phù hợp cho demo đơn giản; với nhiều servlet mapping/forwarded path, nên dùng API/matcher path chính xác thay vì so khớp chuỗi tùy ý.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` dùng để làm ví dụ sớm trong chain, **không phải khuyến nghị áp dụng vô điều kiện** cho authentication hoặc logging filter production.
- `OncePerRequestFilter` mặc định có cơ chế quyết định bỏ qua async/error dispatch; app container/test có thể có các dispatcher registrations khác nhau.

## 10. Thử bằng curl trên Servlet container thực

Chạy Maven Wrapper từ dự án Boot:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Các file Java ở trên cần Spring Boot Web trên classpath; không thể `javac DemoController.java` độc lập khi thiếu dependency. Cổng mặc định là 8080 nếu `server.port` chưa đổi.

### 10.1. Controller thành công

```bash
curl -i http://localhost:8080/demo/ok
```

Dự kiến 200 với body JSON:

```json
{"state":"OK"}
```

### 10.2. Controller exception được advice xử lý

```bash
curl -i http://localhost:8080/demo/controller-fail
```

Dự kiến `409 Conflict` và JSON tương đương:

```json
{
  "code": "ORDER_BLOCKED",
  "message": "Order cannot be changed",
  "path": "/demo/controller-fail"
}
```

Tên/trật tự field do Jackson serialize có thể khác; hãy so sánh giá trị thay vì byte-for-byte. Đây là đường lỗi MVC được `DemoExceptionAdvice` xử lý trực tiếp; thông thường không cần container `ERROR` dispatch.

### 10.3. Filter sendError

```bash
curl -i http://localhost:8080/demo/filter-send-error
```

Dự kiến **HTTP 503 Service Unavailable** do Filter phát. Body có thể là JSON Boot `/error`, HTML hoặc response rỗng tùy cấu hình/Accept. Đừng kỳ vọng body `ORDER_BLOCKED` của `DemoExceptionAdvice`: advice không xử lý tình huống gốc này. Khi container khởi tạo error dispatch, có thể đọc `jakarta.servlet.error.status_code` và `jakarta.servlet.error.request_uri` trong handler error.

### 10.4. Filter throw

```bash
curl -i http://localhost:8080/demo/filter-throw
```

Với cấu hình container mặc định, exception không xử lý thường dẫn tới **HTTP 500 Internal Server Error**; body do container hoặc Boot error handling cung cấp, nếu còn khả năng tạo response. Không cam kết mọi deployment sẽ có cùng error body và log. Nếu một Filter khác bắt `ServletException` thì kết quả có thể khác.

### 10.5. Không có route

```bash
curl -i http://localhost:8080/demo/missing
```

Thường 404, có thể do MVC/resource handler/Boot error pathway tạo ra. **Không suy ra** rằng 404 luôn do `DemoBusinessException` hoặc controller advice gây ra. Nếu reverse proxy can thiệp, 404 có thể xảy ra trước khi request vào Spring app.

## 11. Kiểm thử MockMvc: mức độ mô phỏng có giới hạn

MockMvc chạy Spring MVC và các filters được đăng ký với môi trường test, nhưng **không tương đương mọi cơ chế error dispatch của một Servlet container đang lắng nghe cổng HTTP thực**. Đặc biệt, nếu Filter gọi `sendError`, MockMvc có thể xác nhận status nhưng **không tự dispatch tới Boot `/error` giống Tomcat**. Exception ném từ Filter có thể được đẩy ra thẳng cho test thay vì được container chuyển thành HTTP 500.

Tạo `src/test/java/com/example/demo/DemoBoundaryTest.java` với dependency `spring-boot-starter-test`:

```java
package com.example.demo;

import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerBusinessExceptionGoesThroughAdvice() throws Exception {
        mvc.perform(get("/demo/controller-fail"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("ORDER_BLOCKED"));
    }

    @Test
    void filterCanEndRequestBeforeMvc() throws Exception {
        mvc.perform(get("/demo/filter-send-error"))
                .andExpect(status().isServiceUnavailable());
        // MockMvc không nhất thiết tự chạy container /error dispatch.
    }

    @Test
    void rawFilterExceptionEscapesMockMvcDispatch() {
        assertThrows(ServletException.class,
                () -> mvc.perform(get("/demo/filter-throw")));
        // Nếu một filter khác/custom exception handler đã bao lỗi,
        // hãy chỉnh assertion theo cấu hình thực tế.
    }

    @Test
    void normalRequestStillReachesController() throws Exception {
        mvc.perform(get("/demo/ok"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("OK"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

Kiểm thử trên là **mã nguồn mẫu dự kiến chạy với Boot 3.x/Web/Test mặc định**, không phải báo cáo rằng đã thực thi ở máy của bạn. Nếu app dùng Spring Security, custom filter registration, phương thức async hoặc thay đổi converter, kiểm thử phải thích nghi.

### Khi cần chứng minh container error dispatch

Dùng bài test tích hợp **HTTP thực** với `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và client HTTP (ví dụ `TestRestTemplate` trong Boot 3 hoặc Java `HttpClient`), hoặc chạy ứng dụng thật rồi dùng `curl`. Điều này giúp thấy:

- Status cuối cùng sau `sendError` hoặc unresolved Filter exception.
- Response body/media type do `/error` tạo ra.
- `ERROR` dispatch và filter registration thực tế.
- Sự khác biệt giữa app embedded và WAR trên container bên ngoài.

Không dựa một bài test MockMvc đơn lẻ để khẳng định quá trình container forwarding/error page là đúng trên production.

## 12. Có nên tự gọi HandlerExceptionResolver trong Filter?

Đôi khi API muốn mọi lỗi filter trả cùng JSON với MVC. Filter có thể **inject** bean `HandlerExceptionResolver` của MVC và gọi rõ ràng:

```java
// Minh họa bên trong custom Filter với resolver đã inject.
try {
    chain.doFilter(request, response);
} catch (DomainRejectedException ex) {
    resolver.resolveException(request, response, null, ex);
}
```

Đây là **đoạn mô tả pattern**, không phải tệp độc lập. Chỉ hợp lý khi:

1. `resolver` là bean phù hợp (thường cần chỉ định `@Qualifier("handlerExceptionResolver")` nếu có nhiều bean).
2. Error type thực sự cần cơ chế MVC, đã có handler tương thích, và handler có thể hoạt động khi `handler=null`.
3. Response **chưa commit**, không có body bị ghi một phần.
4. Đã kiểm tra kết quả `resolveException` có được giải quyết hay không; trả `null` có nghĩa vẫn chưa xử lý, không được âm thầm nuốt exception.
5. Đã kiểm soát không trùng log, không lộ nguyên exception và không nuốt lỗi security/hệ thống.

Một số `@ExceptionHandler` phụ thuộc vào controller cụ thể nên không xử lý được khi `handler=null`; advice toàn cục phù hợp hơn. Cách này tạo coupling từ Filter sang MVC, nên cân nhắc lại việc xử lý ngay ở security layer, dùng writer dùng chung hoặc dựa vào container `/error`.

**Cảnh báo:** Không bọc mọi `Exception` từ toàn bộ `chain.doFilter` và gọi resolver lần hai vô điều kiện: MVC có thể đã xử lý lỗi, response có thể committed, và việc ghi tiếp sẽ làm hỏng output. Ví dụ chỉ nêu cách tích hợp khi đã chủ động thiết kế.

## 13. Quan sát log và dấu vết request

Một response 500 đơn độc chưa đủ để biết nguồn. Khi debug:

1. Xác nhận request có tới app chưa bằng gateway/access log.
2. Tìm correlation/request ID qua ingress, Filter, `DispatcherServlet`, controller và error dispatch.
3. Ghi log **đúng nơi bắt lỗi**: filter log lỗi của nó; business exception handler log theo severity thích hợp; container log unresolved exception.
4. So sánh `request.getDispatcherType()`: `REQUEST`, `ERROR` hay `ASYNC`.
5. Trong `ERROR` dispatch, xem `jakarta.servlet.error.request_uri`, `jakarta.servlet.error.status_code` và exception (nếu có).
6. Xem response có committed chưa trước khi cố thay status/body.
7. Xem filter registration và order; `@Order` của filter bean, `FilterRegistrationBean` và security chain đều có thể ảnh hưởng.
8. Xem stack trace cẩn thận: Filter/Servlet container/MVC resolver xuất hiện ở đâu? Spring controller method có được gọi không?
9. Nếu response 401/403, xem authentication entry point/denied handler/CSRF; không vội sửa controller advice.
10. Dùng một request test tái hiện rồi thay đổi **một yếu tố mỗi lần** (Accept, credentials, URL, body size, dispatcher type).
11. Kiểm tra error body đến từ `/error`, `@RestControllerAdvice`, gateway hay reverse proxy.
12. Tránh log token, cookie, Authorization header hoặc nguyên request body chỉ để debug exception.

Có thể tạm bật logging phù hợp trong môi trường test để xem MVC handler mapping, security filter chain và controller advice, rồi hạ log level trước production. Thông điệp lỗi công khai nên dùng code ổn định và thông tin an toàn; stack trace để server-side logging.

## 14. Bảng so sánh phân loại trách nhiệm

| Nguồn lỗi | Đã tới DispatcherServlet? | @RestControllerAdvice bắt gốc theo mặc định? | Thành phần thường quyết định response |
| --- | --- | --- | --- |
| Controller/service ném exception trong MVC dispatch | Có | **Có thể**, nếu handler phù hợp | HandlerExceptionResolver, advice, hoặc fallback |
| Sai JSON trong `@RequestBody` | Có (ở argument resolution) | **Có thể**, qua handler cho exception MVC | Resolver/advice, thường 400 |
| Sai HTTP method/Accept/media type trong MVC mapping | Có nếu tới MVC | **Có thể**, tùy handler/resolver | MVC resolver, 405/406/415 thường gặp |
| Custom Filter ném trước `chain.doFilter` | Chưa | **Không tự động** | Filter khác, container error handling |
| Custom Filter `sendError` rồi dừng chain | Chưa | **Không tự động** | Servlet container và `/error` nếu có |
| Custom Filter ném sau khi downstream trả | Downstream có thể đã hoàn tất | **Không tự động** | Filter/container; chú ý committed |
| Spring Security authentication/authorization chặn trước MVC | Thường chưa | **Không tự động** | EntryPoint/AccessDeniedHandler/filter |
| Container từ chối malformed HTTP request trước Servlet | Không | Không | Container/gateway |
| Container timeout/connection reset hoặc lỗi ghi response | Tùy thời điểm | Không chắc; thường không còn body có thể đổi | Container/network |
| Async task ném sau khi request thread rời | Tùy cách async được quản lý | **Tùy cơ chế async** | MVC async dispatch resolver hoặc container |

Đừng dùng bảng như một tuyên bố rằng advice chỉ xử lý exception phát sinh ngay trong method controller. Resolver chain hoạt động trong vòng đời `DispatcherServlet` và có thể giải quyết một số lỗi do mapping, argument binding, rendering hoặc interceptor.

## 15. Lỗi async và deferred processing

Spring MVC hỗ trợ return types như `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>` và streaming. Khi `Callable` do Spring MVC quản lý ném exception, framework có thể dispatch lại vào servlet với kết quả lỗi và sử dụng MVC exception handling; đây **khác** một thread tự spawn bên ngoài quản lý lifecycle của request.

Đừng giả định `@RestControllerAdvice` bắt mọi exception của `CompletableFuture.runAsync` tự chạy, callback ngoài request hay message listener. Một task độc lập có thể thất bại sau khi request đã hoàn tất; cần xử lý bằng future completion, executor error handling và telemetry riêng.

Các lưu ý:

- Cấu hình Servlet Filter theo `ASYNC` dispatch nếu cần bảo toàn tracing/security logic, nhưng tránh xử lý lặp ngoài ý muốn.
- Khi response đã commit và đang stream, exception handler thường không thể đổi nội dung thành ProblemDetail mới.
- Khi timeout async, Spring MVC có cơ chế timeout/interceptor/exception riêng; status có thể khác theo cấu hình.
- Không gửi một response mới từ background thread sau khi container đã đóng request.
- MockMvc async test có thể cần `asyncDispatch` để kiểm tra lần dispatch tiếp theo; chỉ gọi `mvc.perform(...)` lần đầu không bao phủ toàn bộ lifecycle.

## 16. Thiết kế error contract: đồng nhất nhưng vẫn đúng tầng

API thực tế có thể muốn cùng một format lỗi cho MVC, Security và container:

```json
{
  "code": "REQUEST_REJECTED",
  "message": "Request cannot be processed",
  "traceId": "2e1d8f..."
}
```

**Định dạng giống nhau không có nghĩa một handler bắt mọi nguồn lỗi.** Có thể dùng:

- **MVC layer:** `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler` cho validation, conversion, service/business exception; có thể dùng `ProblemDetail`.
- **Security layer:** `AuthenticationEntryPoint`/`AccessDeniedHandler` cho 401/403. Chú ý WWW-Authenticate khi dùng Basic/Bearer theo hợp đồng.
- **Filter layer:** error writer chuyên dụng hoặc xử lý có chủ đích, không viết response hai lần.
- **Container/error path:** cấu hình Boot `ErrorAttributes`/`ErrorController` hoặc server error pages để có fallback an toàn.

Một writer dùng chung có thể giúp giữ `code`, `message`, `traceId` nhất quán, nhưng hãy truyền rõ status và không để tầng business tự quyết định Servlet API. Không biến lỗi 500 thành 400, không coi 401/403 là 500, không lộ raw exception/stack trace ra client.

Với Spring 6+, `ProblemDetail` giúp thể hiện các thuộc tính chuẩn `type`, `title`, `status`, `detail`, `instance` và extension fields. RFC 9457 là chuẩn Problem Details hiện đại. Nếu chọn dạng này, đảm bảo HTTP status ngoài response khớp nội dung `status` và content type phù hợp `application/problem+json` khi ghi JSON. Error page của container/Boot không tự động đồng nhất với mọi ProblemDetail do MVC tạo ra.

## 17. Các bẫy thường gặp

1. **“@RestControllerAdvice bắt mọi lỗi web”:** Sai. Nó là cơ chế MVC; filter/container có thể lỗi trước hoặc sau dispatch.
2. **“Mọi 500 đều là exception controller”:** Sai. Container, filter, gateway, async hoặc serializer cũng có thể gây 500.
3. **“Chỉ cần Filter ném ResponseStatusException là thành JSON giống MVC”:** Không mặc định. Exception ném trước DispatcherServlet không tự vào MVC resolver chain.
4. **“sendError và setStatus giống nhau”:** Không. sendError liên quan Servlet error mechanism, setStatus chỉ đặt mã.
5. **“status 404 luôn do exception”:** Không. Có thể response có status mà không có exception.
6. **“Một Filter chạy đúng một lần mỗi HTTP request trong mọi dispatch”:** Không nên giả định. Kiểm tra REQUEST/ERROR/ASYNC và behavior của OncePerRequestFilter.
7. **“MockMvc thể hiện y hệt container error page”:** Không. MockMvc không thay thế test HTTP thực cho ERROR dispatch.
8. **“Có ExceptionTranslationFilter thì mọi RuntimeException thành 401/403”:** Không. Nó tập trung vào authentication/authorization exceptions trong security chain.
9. **“Lỗi JSON syntax là 500 do Jackson”:** Sai trong đa số API MVC thông thường; input không đọc được thường 400 khi framework xử lý.
10. **“HandlerExceptionResolver luôn trả JSON”:** Không. Có resolver tạo view, đặt status, hoặc nhường cho resolver/container khác.
11. **“Ghi body trước rồi catch lỗi trả JSON mới”:** Không an toàn khi response đã commit.
12. **“Filter có thể gọi chain lại để controller xử lý exception”:** Dễ double execution/double write; không làm vậy.
13. **“Thiết lập /error nghĩa là lỗi MVC đã xử lý vẫn chạy /error”:** Không nhất thiết; cần phân biệt MVC resolver xử lý và container error dispatch.
14. **“Tắt bảo mật với mọi ERROR dispatch là vô hại”:** Cần đánh giá rò rỉ thông tin và policy; chỉ cấu hình đúng phạm vi.
15. **“Log mọi request body để tìm nguyên nhân”:** Có thể lộ PII/token; log có chọn lọc và ẩn dữ liệu nhạy cảm.
16. **“Tăng thứ tự filter cao nhất luôn đúng”:** Filter order phụ thuộc mục tiêu; cấu hình sai khiến security, CORS, request wrappers và tracing không làm việc mong muốn.
17. **“ResponseEntity.status(500) chứng tỏ container đã gặp exception”:** Không. Controller có thể chủ động trả status.
18. **“@ExceptionHandler(Exception.class) trả 200 để client không lỗi”:** Phá HTTP semantics và observability; phải phân loại status đúng.

## 18. Quy trình điều tra thực tế

Khi nhận log “500 Internal Server Error” hoặc client nói error body không giống chuẩn:

1. **Xem request đã vào container chưa** bằng access log và tracing từ gateway. Nếu không, xử lý ở ingress/network trước.
2. **Xem filter có chạy không:** thêm log an toàn có correlation id ở đầu một Filter chuyên observability, không log token/body.
3. **Xem DispatcherServlet có chọn handler không:** bật log mapping phù hợp, hoặc quan sát `HandlerMapping.BEST_MATCHING_HANDLER_ATTRIBUTE` khi cần và còn request context.
4. **Xem controller/service có được gọi không:** một breakpoint/log ở entrypoint không đủ để kết luận lỗi binding/argument conversion vì chúng xảy ra trước khi method chạy.
5. **Xem exception resolver có chạy không:** log các MVC resolver/advice; nếu exception từ Filter trước chain, thông thường không.
6. **Xem `getDispatcherType()` là REQUEST hay ERROR:** cùng URL có thể xuất hiện hai dispatch trong một lỗi.
7. **Xem response đã commit chưa:** nếu đã commit, lỗi body/status có thể không sửa được.
8. **Xem Security exception handling:** với 401/403, phân tích filter order, exception translation, entrypoint/denied handler, CSRF và CORS.
9. **Xem fallback /error:** Boot ErrorAttributes và container error page có thể quyết định body cuối.
10. **Kiểm tra hai kiểu test:** MockMvc để kiểm chứng MVC advice/filter interaction, HTTP server thật để kiểm tra Servlet ERROR dispatch.
11. **Kiểm tra cấu hình deployment:** embedded Tomcat/Jetty so với WAR ngoài container; có thể khác registration/error page.
12. **Chốt root cause theo ranh giới:** sửa ở lớp thực sự sở hữu lỗi — validation trong MVC, authentication ở security, filter-specific error handling hoặc giới hạn/container configs.

Ghi nhớ: **nơi exception xảy ra**, **ai có thể nhìn thấy nó**, **ai viết response cuối** là ba câu hỏi riêng. Việc phân tách ba câu hỏi giúp tránh viết một `@RestControllerAdvice` cực rộng nhưng vẫn bỏ sót lỗi Filter và container.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một `@RestController` ném `DemoBusinessException` và advice có `@ExceptionHandler` phù hợp. Ai xử lý?

**Đáp án:** Thông thường `ExceptionHandlerExceptionResolver` của MVC gọi advice để tạo response. Controller method đã được gọi.

**Câu 2.** Custom Filter ném `ServletException` trước khi gọi `chain.doFilter`. Advice có tự bắt không?

**Đáp án:** Không. `DispatcherServlet` chưa xử lý request, nên lỗi gốc không tự tới resolver của MVC. Filter khác hoặc Servlet container có thể xử lý.

**Câu 3.** Filter gọi `response.sendError(503)` và return. Response có luôn giống JSON của advice không?

**Đáp án:** Không. Error handling của container/Boot `/error` tùy cấu hình quyết định, và không có guarantee về body.

**Câu 4.** Tại sao `mvc.perform` đôi khi ném trực tiếp exception Filter trong test, còn gọi HTTP qua Tomcat trả 500?

**Đáp án:** MockMvc mô phỏng MVC/filter nhưng không hoàn toàn thực thi cơ chế Servlet container error page/ERROR dispatch. HTTP server thực xử lý lỗi chưa bắt từ Servlet/Filter.

**Câu 5.** Status 403 trước controller có chắc là `@Valid` thất bại không?

**Đáp án:** Không. Nó thường liên quan security/CSRF/authorization/filter/gateway. Validation input điển hình gây 400, không tự động 403.

**Câu 6.** Status `200 OK` có thể đi kèm một Java exception đã bị xử lý không?

**Đáp án:** Có nếu custom handler viết sai status hoặc cố tình trả 200; nhưng đó thường là thiết kế API kém. Không dùng 200 cho lỗi nghiệp vụ cần được biểu diễn bằng status lỗi thích hợp.

**Câu 7.** Vì sao `response.sendError` sau `flushBuffer()` là nguy hiểm?

**Đáp án:** Response đã committed; không còn an toàn để đổi status/body, có thể gây `IllegalStateException` hoặc mất kết nối.

**Câu 8.** Khi nào ERROR dispatch có thể kích hoạt Filter lần nữa?

**Đáp án:** Nếu container dispatch tới error page và filter được đăng ký cho `DispatcherType.ERROR`, trừ khi logic Filter bỏ qua dispatch phù hợp.

**Câu 9.** `ExceptionTranslationFilter` dùng để chuyển mọi `RuntimeException` thành 401?

**Đáp án:** Không. Nó xử lý chủ yếu `AuthenticationException` và `AccessDeniedException` từ vị trí phù hợp trong Spring Security chain.

**Câu 10.** Nếu muốn API có lỗi đồng nhất ở cả controller, security và filter, có nên chỉ viết một `@RestControllerAdvice` không?

**Đáp án:** Không đủ. Cần thiết kế các điểm tạo response phù hợp ở MVC, Spring Security, filter và container fallback, thống nhất error schema và status.

## 20. Tài liệu tham khảo

- Spring Framework — MVC exception resolver chain và container error page: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework 6.2 — Controller Advice: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework — Error Responses và ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Security — Servlet FilterChainProxy và ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Exception Handling: https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter
- Spring Boot — Servlet Web Error Handling: https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.error-handling
- Spring Boot — ErrorAttributes API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/error/ErrorAttributes.html
- Spring Boot — ErrorPageFilter API (WAR/non-embedded): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/ErrorPageFilter.html
- Jakarta Servlet specification và DispatcherType: https://jakarta.ee/specifications/servlet/
- Jakarta Servlet 6.0 DispatcherType API: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype
- RFC 9457 — HTTP API Problem Details: https://www.rfc-editor.org/rfc/rfc9457.html
