# preHandle, postHandle, afterCompletion và điều kiện gọi lại trong Spring MVC

## 1. Mục tiêu và tình huống sử dụng

Một request đi qua Spring MVC có thể được nhiều `HandlerInterceptor` quan sát hoặc can thiệp trước/sau khi controller thực thi. Ba callback thường gặp là:

- `preHandle(request, response, handler)`: trước khi HandlerAdapter gọi handler; trả `true` để cho đi tiếp hoặc `false` để dừng chain.
- `postHandle(request, response, handler, modelAndView)`: sau khi handler thực thi **thành công theo đường xử lý đồng bộ**, trước khi view được render; không phải nơi tin cậy để sửa response JSON đã ghi.
- `afterCompletion(request, response, handler, exception)`: ở giai đoạn hoàn tất dispatch để dọn tài nguyên/ghi telemetry, nhưng **chỉ đối với interceptor có `preHandle` đã hoàn thành và trả `true`**, với ngoại lệ quan trọng của xử lý bất đồng bộ.

Sau bài này, bạn sẽ biết:

1. Vị trí của `HandlerInterceptor` trong `DispatcherServlet` và sự khác biệt với Servlet Filter.
2. Thứ tự callback khi có **nhiều interceptor**, khi trả `false`, controller ném exception, view render lỗi và request bất đồng bộ.
3. Ý nghĩa chính xác của `postHandle`, `ModelAndView` có thể null, `afterCompletion` và tham số `Exception ex`.
4. Khi nào `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` được gọi thay cho hai callback thông thường và khi nào có dispatch lần hai.
5. Viết, đăng ký và kiểm thử hai interceptor bằng **Java 17+, Spring Framework 6.x / Spring Boot 3.x, MockMvc**, cùng các trường hợp response body và error.
6. Tránh sai lầm phổ biến: ngầm dựa vào interceptor để bảo mật, set header quá muộn, dọn `ThreadLocal` không đúng lúc hoặc ghi hai response.

**Phạm vi:** Spring MVC trên Servlet stack, không phải Spring WebFlux. Tên giao diện và ý nghĩa callback áp dụng cho Spring MVC 6.x; với Spring 7/Boot 4, đối chiếu API theo phiên bản đang dùng. Trong ví dụ, hai interceptor được gắn riêng vào đường dẫn `/trace/**`; không mặc định áp dụng lên mọi servlet request.

## 2. Chúng nằm ở đâu trong luồng xử lý?

```text
Client
  |
  v
Servlet container
  |
  v
Servlet Filters (CORS, compression, security, tracing ...)
  |
  v
DispatcherServlet
  |
  +-- HandlerMapping chọn handler
  |      -> HandlerExecutionChain(handler, [Interceptor A, Interceptor B])
  |
  +-- A.preHandle(request, response, handler)
  |      -> true
  +-- B.preHandle(request, response, handler)
  |      -> true
  |
  +-- HandlerAdapter gọi controller/handler
  |
  +-- B.postHandle(...)             \
  +-- A.postHandle(...)              } đường đồng bộ thành công
  |
  +-- render ModelAndView nếu có view
  |
  +-- B.afterCompletion(...)         \
  +-- A.afterCompletion(...)          } cleanup sau dispatch
  |
  v
Servlet Filters sau chain.doFilter -> container -> client
```

**Không đồng nhất Filter với HandlerInterceptor:**

| Vấn đề | Servlet Filter | Spring MVC HandlerInterceptor |
| --- | --- | --- |
| Nằm ở đâu? | Trước/bên ngoài DispatcherServlet theo Servlet filter chain | Sau khi HandlerMapping tìm được handler, bên trong MVC |
| Đối tượng API | `Filter#doFilter`, `FilterChain` | `preHandle`, `postHandle`, `afterCompletion` |
| Có biết handler MVC? | Không mặc định | Nhận `handler`, có thể là `HandlerMethod` |
| Có can thiệp request không được mapping đến controller? | Thường có, tùy URL/dispatcher registration | Chỉ khi request đi tới một HandlerExecutionChain có interceptor |
| Bảo mật sớm cho mọi request? | Spring Security nằm trên filter chain và thích hợp hơn | Không nên làm lớp bảo mật chính |
| Can thiệp sau khi response body JSON được ghi? | Filter có thể bao response bằng wrapper phù hợp, còn phải chú ý commit | `postHandle` thường quá muộn cho `@ResponseBody`/`ResponseEntity` |

Spring Framework khuyến nghị **Spring Security hoặc filter-chain security** hơn là dùng interceptor như rào bảo mật chính, vì mapping của interceptor và security boundary có thể không tương đương. Interceptor phù hợp cho cross-cutting logic **gắn với MVC handler**, như quan sát thời gian, thêm model attributes cho view, kiểm tra điều kiện nghiệp vụ bổ trợ hoặc tracking.

## 3. Ba callback: chữ ký và ý nghĩa

Giao diện `org.springframework.web.servlet.HandlerInterceptor` có các phương thức mặc định:

```java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler) throws Exception;

void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView) throws Exception;

void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex) throws Exception;
```

Đây là **trích yếu chữ ký API**, cần imports Jakarta Servlet, `ModelAndView` và `HandlerInterceptor` trong source thật. Từ Spring Framework hiện đại, các phương thức có default implementations nên chỉ override cái cần dùng. `preHandle` mặc định trả `true`.

### 3.1. preHandle: quyết định có đi tiếp không

`preHandle` chạy sau HandlerMapping chọn `handler`, trước HandlerAdapter gọi nó. `true` nghĩa là MVC được tiếp tục đến interceptor kế hoặc handler. `false` nghĩa là interceptor đã xử lý/chủ động kết thúc response và Spring **không gọi handler**.

```java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {
    if (request.getHeader("X-Feature") == null) {
        response.sendError(400, "Missing X-Feature");
        return false;
    }
    return true;
}
```

Đây là snippet trong lớp triển khai `HandlerInterceptor`. Khi trả `false`, bạn phải đảm bảo response được giải quyết phù hợp: đặt status, body/redirect, `sendError` hoặc một cơ chế khác. **Trả `false` mà không set gì** có thể tạo response rỗng với status mặc định ngoài ý muốn.

Điểm tinh tế: `false` không phải Java exception. `@RestControllerAdvice` không tự nhận một `Exception` chỉ vì interceptor trả false. Với `sendError`, container error handling có thể tiếp tục theo cấu hình, khác với viết trực tiếp body.

### 3.2. postHandle: sau handler thành công, trước view render

`postHandle` nhận `ModelAndView`, có thể thêm metadata cho view nếu model/view còn được xử lý:

```java
@Override
public void postHandle(HttpServletRequest request,
        HttpServletResponse response, Object handler,
        ModelAndView mav) {
    if (mav != null) {
        mav.addObject("renderedBy", "spring-mvc");
    }
}
```

**Với `@ResponseBody`/`ResponseEntity`, HTTP response thường đã được ghi và có thể commit trong HandlerAdapter trước `postHandle`.** Vì thế không nên dùng `postHandle` để “bảo đảm” thêm JSON property, đổi status/header hay ghi error body. Với REST JSON output, dùng `ResponseBodyAdvice` ở đúng giai đoạn serialize, controller/`ResponseEntity` để set status/header, hoặc filter/response wrapper khi có yêu cầu đặc thù.

`mav == null` là trường hợp bình thường khi handler trả response body, tự ghi trực tiếp, return null, hoặc một số loại handler khác; không phải tự động là lỗi.

### 3.3. afterCompletion: cleanup sau toàn bộ xử lý

`afterCompletion` thường chạy sau khi view đã được render xong (nếu có). Mục đích tốt gồm đóng các tài nguyên của chính interceptor, đo latency tổng thể, đánh dấu hoàn thành, dọn thread-local state mà interceptor đã tạo và log thành công/thất bại bằng thông tin đã kiểm soát.

```java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) {

    // Chỉ dọn dữ liệu do interceptor sở hữu.
    // Không cố thay status/body khi response có thể đã commit.
}
```

**Điều kiện chính xác:** chỉ gọi cho interceptor mà `preHandle` **đã hoàn tất thành công và trả `true`** trong chain đó. Interceptor trả `false` không được gọi `afterCompletion` của chính nó; nếu `preHandle` ném trước khi trả true, cũng không được bảo đảm callback của chính nó.

Tham số `ex` không phải “mọi lỗi từng xảy ra”. Exception đã được `HandlerExceptionResolver` xử lý có thể **không xuất hiện** trong `afterCompletion(ex)`. Nếu controller đã trả response 409 một cách bình thường, `ex` có thể null. Đừng dùng `ex == null` để kết luận HTTP status luôn là 2xx; nên xem `response.getStatus()` và tín hiệu ứng dụng.

## 4. Thứ tự khi đăng ký nhiều interceptor

Giả sử đăng ký hai interceptor A rồi B, cùng match URL. Dòng thời gian đồng bộ thành công:

```text
A.pre
B.pre
controller
B.post
A.post
view rendering nếu có
B.after
A.after
```

Quy luật:

- **Trước handler**: `preHandle` theo thứ tự đăng ký A → B.
- **Sau handler**: `postHandle` theo thứ tự đảo B → A.
- **Hoàn tất**: `afterCompletion` cũng theo thứ tự đảo B → A.

Thứ tự này tương tự cấu trúc lồng nhau:

```text
A {
    B {
        handler
    }
}
```

Thứ tự thực tế phụ thuộc vào `HandlerExecutionChain` tạo bởi HandlerMapping, không chỉ danh sách `@Component` trong application context. Spring Boot có thể có interceptors do framework hoặc thư viện tự thêm; khi debug hãy quan sát **interceptor chain thực tế** cho handler.

### 4.1. B trả false

Nếu A trả true, B trả false:

```text
A.pre -> true
B.pre -> false, tự ghi response
A.after
(stop: không chạy controller, B.post, A.post, B.after)
```

Spring gọi `afterCompletion` của các interceptor **đã qua preHandle thành công trước B** theo thứ tự ngược. B không nhận `afterCompletion` của chính nó. Do đó nếu B cấp tài nguyên/đặt ThreadLocal **trước khi quyết định trả false**, B phải tự dọn trong đường `false` hoặc sắp xếp lại thiết kế; không “chờ afterCompletion” để dọn.

### 4.2. A trả false ngay

```text
A.pre -> false
(stop: không chạy B.pre, controller, bất kỳ post/after nào của A/B)
```

A có trách nhiệm gửi response. Vì chưa interceptor nào hoàn thành `preHandle=true`, không có `afterCompletion` từ chain này.

### 4.3. B ném exception trong preHandle

```text
A.pre -> true
B.pre -> throws exception
(thường không có B.after)
A.after có thể chạy trong luồng exception handling của MVC
```

Những interceptor trước đó đã trả true có thể được cleanup khi DispatcherServlet xử lý error; đừng suy rộng rằng callback của B luôn chạy. Nếu B cấp tài nguyên rồi ném trong preHandle, hãy tự đặt cleanup trong `catch/finally` của B hoặc chuyển việc cấp tài nguyên sang một vị trí có cleanup chắc chắn.

### 4.4. B đã trả true, nhưng controller ném exception

```text
A.pre -> true
B.pre -> true
controller -> throws
(no A.post or B.post for failed handler execution)
exception resolvers / @ControllerAdvice
B.after
A.after
```

Thường `postHandle` không được gọi sau khi handler ném exception. `afterCompletion` có thể vẫn chạy vì cả A/B đã trả true. Sau đó nếu MVC advice đã xử lý exception thì `ex` quan sát tại completion có thể null; đừng dựa ex để đo số lỗi nghiệp vụ.

## 5. Bảng tình huống gọi lại: kết luận thực dụng

| Tình huống | preHandle | postHandle | afterCompletion |
| --- | --- | --- | --- |
| Handler đồng bộ thành công, A/B đều true | A → B | B → A | B → A |
| A true, B false | A → B (B chặn) | Không | Chỉ A |
| A false | Chỉ A | Không | Không |
| Handler ném exception, advice xử lý | A → B | Thường không | B → A; `ex` có thể null |
| Handler trả JSON `@ResponseBody` thành công | A → B | B → A, `mav` thường null; body có thể đã ghi | B → A |
| Handler view render thất bại | A → B | Có thể đã chạy trước render | Completion của interceptor đã active; lỗi tùy resolver |
| MVC handler bắt đầu async | A → B lần dispatch đầu | Không ở dispatch đầu | Không ở dispatch đầu; dùng async callback |
| Async hoàn tất và dispatch lại | Thường A → B ở ASYNC dispatch | Khi kết quả được xử lý thích hợp | Khi ASYNC dispatch kết thúc thích hợp |
| Filter từ chối trước DispatcherServlet | Không có chain MVC | Không | Không |
| Không tìm được HandlerExecutionChain áp dụng | Không có interceptor MVC trong chain | Không | Không |

Đừng diễn giải bảng thành luật “mọi 404 đều không chạy interceptor”: trong một số cấu hình, request 404 có thể được một handler khác (chẳng hạn resource handler) match trước khi quyết định không tìm thấy resource, và handler đó có interceptor riêng. Tương tự, exceptions trong mapping trước khi chain được tạo có đường xử lý khác exceptions sau preHandle.

## 6. ModelAndView, view render và REST response

Controller trả view:

```java
@Controller
class PageController {
    @GetMapping("/pages/home")
    String home(Model model) {
        model.addAttribute("title", "Trang chủ");
        return "home";
    }
}
```

Mã trên là **trích đoạn class trong dự án Spring MVC** và chỉ render được khi có template `home` tương ứng. `postHandle` có thể thấy `ModelAndView` và thêm attribute trước khi view render. `afterCompletion` chạy sau khi view được xử lý xong.

Controller REST:

```java
@RestController
class ApiController {
    @GetMapping("/api/health")
    Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
```

Đây là đoạn minh họa, cần imports Java/Spring và project Spring Web. JSON thường được ghi trong HandlerAdapter bởi `HttpMessageConverter`. `postHandle` có thể vẫn chạy, nhưng `ModelAndView` thường null và sửa HTTP body/header lúc đó có thể đã quá muộn.

**Nếu yêu cầu đặt một response header quan trọng**, ưu tiên:

- `ResponseEntity.ok().header("X-...", "...").body(dto)` khi controller sở hữu header.
- `ResponseBodyAdvice` khi cần sửa response body trong quá trình serialize theo policy MVC.
- Servlet Filter khi yêu cầu áp lên cả requests không tới MVC hoặc cần response wrapper ở mức Servlet.
- Không dùng `postHandle` làm biện pháp bảo đảm security header cho mọi trường hợp: view/REST/error và response commit có đường xử lý khác nhau.

## 7. AsyncHandlerInterceptor: khi nào ba callback không đủ?

Khi controller trả `Callable`, `DeferredResult` hoặc kích hoạt xử lý Servlet async do Spring MVC quản lý, **dispatch đầu có thể kết thúc mà kết quả handler chưa sẵn sàng**. Khi ấy DispatcherServlet không gọi `postHandle` và `afterCompletion` trong dispatch đầu như bình thường.

`AsyncHandlerInterceptor` mở rộng `HandlerInterceptor` thêm:

```java
@Override
public void afterConcurrentHandlingStarted(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception {
    // Dọn thread-bound state của dispatch đầu.
}
```

Callback này được gọi **thay cho** `postHandle`/`afterCompletion` trên dispatch đã khởi động async. Nó hữu ích nếu interceptor đã đặt MDC hoặc ThreadLocal trên request thread và phải dọn trước khi trả thread về Servlet container.

Luồng điển hình của một request async (A/B đều true):

```text
REQUEST dispatch:
    A.pre
    B.pre
    controller trả Callable/DeferredResult -> MVC bắt đầu async
    B.afterConcurrentHandlingStarted
    A.afterConcurrentHandlingStarted
    (chưa B.post/A.post, chưa B.after/A.after ở dispatch đầu)

Khi async result hoàn tất:
ASYNC dispatch:
    A.pre
    B.pre
    MVC xử lý giá trị/ngoại lệ async đã có
    B.post
    A.post
    B.after
    A.after
```

Một số chi tiết phụ thuộc adapter, return type, async timeout và thiết lập filter. Với `Callable` ném exception được MVC quản lý, exception có thể được xử lý trên dispatch tiếp theo qua resolvers. **Không đồng nhất một `CompletableFuture` tự spawn ngoài MVC với vòng đời servlet async của controller.**

### 7.1. Timeout hoặc network error có thể không có dispatch hoàn tất

Nếu async request timeout hoặc client disconnect, container có thể không dispatch lại theo con đường bạn trông đợi; khi đó `postHandle`/`afterCompletion` có thể **không được gọi**. Muốn lifecycle callbacks mạnh hơn, Spring cung cấp `WebAsyncManager.registerCallableInterceptor`, `registerDeferredResultInterceptor` và các callbacks của `DeferredResult` như `onTimeout`/`onCompletion`. Dùng đúng cơ chế, kiểm tra version/framework và luôn đảm bảo cleanup thread-specific.

### 7.2. Không dùng ThreadLocal như request-wide storage

Một `ThreadLocal` chỉ gắn với thread hiện tại. Nếu A.pre lưu `System.nanoTime()` vào ThreadLocal trên request thread, đến ASYNC dispatch có thể là thread khác; giá trị không tự xuất hiện. Với thời điểm bắt đầu cần đo qua nhiều dispatch, dùng request attribute hoặc một context được truyền rõ ràng, đồng thời lưu ý request có thể hoàn tất bất thường.

Ví dụ an toàn cho thời điểm:

```java
request.setAttribute("startNanos", System.nanoTime());

// Trong callback cùng request, đọc attribute bằng tên có namespace.
Long started = (Long) request.getAttribute("startNanos");
```

Đây là đoạn minh họa, không phải nguyên chương trình; không dùng tên attribute chung chung trong ứng dụng lớn để tránh va chạm. Nếu dùng MDC, nhớ remove/restore MDC trên từng thread và có callback riêng khi async bắt đầu.

## 8. Ví dụ Java 17+ hoàn chỉnh: hai interceptor A và B

Ví dụ Spring Boot 3.x:

- A và B chỉ được đăng ký cho `/trace/**`.
- Request `/trace/ok`: A.pre, B.pre, controller, B.post, A.post, B.after, A.after.
- Request `/trace/blocked`: B chặn bằng 403, A.after vẫn chạy, B.after không chạy.
- Request `/trace/fail`: controller ném `DemoFailure`, advice trả 409, không gọi postHandle nhưng gọi completion cho cả A/B.
- Request `/trace/async`: trả `Callable<String>`; dispatch đầu gọi `afterConcurrentHandlingStarted`, sau async dispatch chạy callbacks phù hợp.

Dùng Spring Initializr Maven, Java 17+, dependencies `spring-boot-starter-web` và `spring-boot-starter-test`. Dùng package `com.example.demo` cho tất cả lớp. Không cần database.

### 8.1. DemoApplication.java

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

### 8.2. TraceEvents.java

Tệp `src/main/java/com/example/demo/TraceEvents.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.List;

public final class TraceEvents {
    private static final String KEY =
            TraceEvents.class.getName() + ".events";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> of(HttpServletRequest request) {
        Object value = request.getAttribute(KEY);
        if (value instanceof List<?>) {
            return (List<String>) value;
        }
        List<String> events = new ArrayList<>();
        request.setAttribute(KEY, events);
        return events;
    }

    public static void add(HttpServletRequest request, String event) {
        of(request).add(event);
    }
}
```

`TraceEvents` dùng **request attribute** thay vì singleton global list. Nhờ đó mỗi request có trace độc lập, không trộn dữ liệu người dùng. Chỉ phục vụ demo/test với callbacks trên luồng điều phối; trong production, async concurrency/telemetry có thể cần collection thread-safe và framework tracing chính thức. Không ghi các event này vào response như API contract.

### 8.3. TraceInterceptor.java

Tệp `src/main/java/com/example/demo/TraceInterceptor.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements AsyncHandlerInterceptor {
    private final String name;

    public TraceInterceptor(String name) {
        this.name = name;
    }

    @Override
    public boolean preHandle(HttpServletRequest request,
            HttpServletResponse response, Object handler)
            throws Exception {

        TraceEvents.add(request, name + ".pre");

        if ("B".equals(name)
                && request.getRequestURI().endsWith("/trace/blocked")) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("BLOCKED");
            return false;
        }
        return true;
    }

    @Override
    public void postHandle(HttpServletRequest request,
            HttpServletResponse response, Object handler,
            ModelAndView mav) {
        TraceEvents.add(request, name + ".post");
        // REST response body đã có thể ghi: không sửa body/header ở đây.
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
            HttpServletResponse response, Object handler,
            Exception ex) {
        TraceEvents.add(request, name + ".after");
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response, Object handler) {
        TraceEvents.add(request, name + ".concurrent");
    }
}
```

B tự chặn route `/trace/blocked`. Vì B trả false, B **không nhận** `afterCompletion`; demo không cấp tài nguyên riêng nên không cần cleanup khác. Nếu interceptor dùng ThreadLocal trong `preHandle`, nhớ xử lý đường false/throw ngay tại interceptor, không phụ thuộc `afterCompletion` sau đó.

### 8.4. InterceptorConfig.java

Tệp `src/main/java/com/example/demo/InterceptorConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class InterceptorConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor("A"))
                .addPathPatterns("/trace/**");
        registry.addInterceptor(new TraceInterceptor("B"))
                .addPathPatterns("/trace/**");
    }
}
```

A được đăng ký trước B trong cùng `InterceptorRegistry` và cùng match các route demo. Có thể dùng `excludePathPatterns` cho ngoại lệ. Đừng gắn Interceptor global quá rộng mà không kiểm tra các request static resources/error endpoints hoặc framework khác có thể match.

### 8.5. DemoFailure.java

Tệp `src/main/java/com/example/demo/DemoFailure.java`:

```java
package com.example.demo;

public class DemoFailure extends RuntimeException {
    public DemoFailure() {
        super("Simulated controller failure");
    }
}
```

### 8.6. TraceController.java

Tệp `src/main/java/com/example/demo/TraceController.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.concurrent.Callable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {

    @GetMapping("/trace/ok")
    public String ok(HttpServletRequest request) {
        TraceEvents.add(request, "handler");
        return "OK";
    }

    @GetMapping("/trace/blocked")
    public String blocked() {
        return "SHOULD_NOT_RUN";
    }

    @GetMapping("/trace/fail")
    public String fail(HttpServletRequest request) {
        TraceEvents.add(request, "handler");
        throw new DemoFailure();
    }

    @GetMapping("/trace/async")
    public Callable<String> async() {
        return () -> "ASYNC";
    }
}
```

Controller chỉ xử lý những request B cho đi tiếp. `blocked()` cố ý tồn tại để chứng minh handler **được mapping nhưng bị preHandle chặn trước khi gọi**; đây không phải lỗi 404.

### 8.7. TraceAdvice.java

Tệp `src/main/java/com/example/demo/TraceAdvice.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TraceAdvice {

    @ExceptionHandler(DemoFailure.class)
    public ResponseEntity<String> handleDemo(
            DemoFailure ex, HttpServletRequest request) {
        TraceEvents.add(request, "advice");
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("HANDLED");
    }
}
```

Lỗi `DemoFailure` được MVC advice xử lý thành 409. `afterCompletion` vẫn chạy cho interceptor đã trả true, nhưng `postHandle` không được gọi trên đường handler ném exception. Trường `ex` của `afterCompletion` **có thể null** nếu exception đã được xử lý; vì thế không viết test kỳ vọng ex bắt buộc là `DemoFailure`.

### 8.8. Chạy chương trình

Trong dự án có Maven Wrapper từ Initializr:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Dự án mặc định dùng port 8080 trừ khi cấu hình `server.port` khác. Các file cần Spring MVC và Servlet/Jakarta dependencies; không thể `javac TraceInterceptor.java` độc lập ngoài classpath của Maven project.

## 9. curl: status và body

### 9.1. Luồng thành công

```bash
curl -i http://localhost:8080/trace/ok
```

Dự kiến **200 OK**, body:

```text
OK
```

Mặc dù `TraceEvents` thu thập A.pre → B.pre → handler → B.post → A.post → B.after → A.after, client chỉ thấy body `OK`; trace được giữ trong request attribute để test. Spring không tự thêm event list vào HTTP body.

### 9.2. B chặn

```bash
curl -i http://localhost:8080/trace/blocked
```

Dự kiến **403 Forbidden**, body:

```text
BLOCKED
```

Handler `TraceController.blocked` không chạy; B chủ động viết response rồi trả false. Không tự suy ra rằng hệ thống đã kiểm tra quyền thật: đây chỉ là demo short-circuit, không phải kiến trúc security production.

### 9.3. Controller lỗi

```bash
curl -i http://localhost:8080/trace/fail
```

Dự kiến **409 Conflict**, body:

```text
HANDLED
```

`TraceAdvice` đã map exception nghiệp vụ mô phỏng. `postHandle` không chạy cho handler ném; completion của interceptor đã active vẫn được trigger sau MVC error resolution.

### 9.4. Async

```bash
curl -i http://localhost:8080/trace/async
```

Dự kiến **200 OK**, body:

```text
ASYNC
```

Một request HTTP có thể trải qua hai servlet dispatches bên trong, nên log callback/trace có nhiều lần preHandle. Không suy ra từ một lần `curl` rằng callback chỉ chạy một lần.

## 10. MockMvc: kiểm thử thứ tự chính xác

Tạo `src/test/java/com/example/demo/TraceInterceptorTest.java`, dependency `spring-boot-starter-test`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TraceInterceptorTest {

    @Autowired
    MockMvc mvc;

    private static List<String> events(MvcResult result) {
        return TraceEvents.of(result.getRequest());
    }

    @Test
    void successfulHandlerHasReversePostAndCompletion() throws Exception {
        MvcResult result = mvc.perform(get("/trace/ok"))
            .andExpect(status().isOk())
            .andExpect(content().string("OK"))
            .andReturn();

        assertEquals(List.of(
            "A.pre", "B.pre", "handler",
            "B.post", "A.post",
            "B.after", "A.after"
        ), events(result));
    }

    @Test
    void falseShortCircuitsOnlyPreviouslyCompletedInterceptors()
            throws Exception {
        MvcResult result = mvc.perform(get("/trace/blocked"))
            .andExpect(status().isForbidden())
            .andExpect(content().string("BLOCKED"))
            .andReturn();

        assertEquals(List.of("A.pre", "B.pre", "A.after"),
                events(result));
    }

    @Test
    void resolvedControllerExceptionDoesNotCallPostHandle()
            throws Exception {
        MvcResult result = mvc.perform(get("/trace/fail"))
            .andExpect(status().isConflict())
            .andExpect(content().string("HANDLED"))
            .andReturn();

        assertEquals(List.of(
            "A.pre", "B.pre", "handler", "advice",
            "B.after", "A.after"
        ), events(result));
    }

    @Test
    void asyncUsesConcurrentCallbackBeforeRedispatch()
            throws Exception {
        MvcResult first = mvc.perform(get("/trace/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        List<String> before = List.copyOf(events(first));
        assertTrue(before.contains("A.concurrent"));
        assertTrue(before.contains("B.concurrent"));
        assertFalse(before.contains("A.post"));
        assertFalse(before.contains("B.post"));

        MvcResult finalResult = mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(content().string("ASYNC"))
            .andReturn();

        List<String> after = events(finalResult);
        assertTrue(after.contains("A.post"));
        assertTrue(after.contains("B.post"));
        assertTrue(after.contains("A.after"));
        assertTrue(after.contains("B.after"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Trên PowerShell:

```powershell
.\mvnw.cmd test
```

Các test này là **source code mẫu**, không phải tuyên bố đã chạy trong repository cụ thể. Nếu project bật Spring Security, custom interceptors, filters hay exception resolvers khác, cần điều chỉnh setup/expected results. `MockMvc` giả lập servlet request/async MVC, không thay toàn bộ hành vi network/container error page.

### Vì sao trace đặt trên HttpServletRequest?

Nếu sử dụng singleton `List<String>` để ghi event từ nhiều request, các request song song sẽ trộn nhau. Request attribute giữ trace trong phạm vi request và cho MockMvc đọc sau khi dispatch. Trong production, sử dụng metrics/tracing framework có correlation ID và cleanup phù hợp; tránh thêm event list để người dùng truy xuất vô ý.

### Assertion cho controller lỗi nói lên điều gì?

Nó xác nhận:

- Handler đã chạy và ném exception.
- `@RestControllerAdvice` xử lý thành HTTP 409.
- `postHandle` của cả A/B không gọi.
- `afterCompletion` của A/B vẫn gọi vì các `preHandle` đều trả true.

Nếu bỏ `TraceAdvice`, exception có thể thoát qua error resolver/container theo một đường khác, nhưng không tự khiến `postHandle` xuất hiện trở lại.

## 11. Chọn nơi đặt tracing, cleanup và các thông tin response

### 11.1. Metrics/latency

Một interceptor có thể đo thời gian giữa `preHandle` và `afterCompletion` bằng `System.nanoTime()`. Dùng request attribute có namespace:

```java
@Override
public boolean preHandle(HttpServletRequest request,
        HttpServletResponse response, Object handler) {
    request.setAttribute("metrics.startedNanos", System.nanoTime());
    return true;
}

@Override
public void afterCompletion(HttpServletRequest request,
        HttpServletResponse response, Object handler, Exception ex) {
    Long began = (Long) request.getAttribute("metrics.startedNanos");
    if (began != null) {
        long elapsed = System.nanoTime() - began;
        // Gửi elapsed tới metric registry phù hợp.
    }
}
```

Đây là **hai method trích đoạn** trong một interceptor. Với async, `afterCompletion` ở dispatch cuối và request attribute thường tiếp tục tồn tại, nhưng khi timeout/network error có thể không có completion như kỳ vọng; dùng callbacks async riêng. Nếu nhiều interceptor cùng ghi tên attribute, cần key có namespace hoặc dùng đối tượng riêng.

### 11.2. ThreadLocal và MDC

Một interceptor đôi khi `MDC.put("requestId", id)` ở `preHandle` và `MDC.remove` ở `afterCompletion`. Cách này có vấn đề khi:

- `preHandle` trả false → completion của chính interceptor không chạy.
- `preHandle` ném exception trước khi trả true → completion của chính nó không được bảo đảm.
- Async bắt đầu → `afterCompletion` không chạy tại dispatch đầu; phải dọn thread-bound state trong `afterConcurrentHandlingStarted`.
- Luồng xử lý async có thể khác thread ban đầu. Không suy rằng MDC tự truyền qua mọi executor.
- Filter cũng có thể sở hữu MDC; interceptor chỉ nên restore giá trị cũ do mình đã thay, không xóa vô điều kiện context của tầng khác.

Thiết kế an toàn: không mở scope cho đến khi biết được quản lý cleanup; nếu đã mở, phải đóng ở mọi nhánh false/throw và async callback. Với tracing distributed, ưu tiên framework observability dùng propagation chuẩn thay vì tự viết ThreadLocal quá phức tạp.

### 11.3. Response headers

Nếu chỉ cần thêm header trong một `@ResponseBody` handler, set trong controller/`ResponseEntity` hoặc các hooks trước response commit. `postHandle` chạy sau HandlerAdapter nên không chắc có thể sửa header. Spring documentation nhấn mạnh dùng `ResponseBodyAdvice` cho thay đổi body REST ở đúng giai đoạn.

Nếu áp header bảo mật chung như HSTS/CSP, filter hoặc Spring Security header configuration có phạm vi đúng hơn interceptor chỉ match MVC handlers. Nếu muốn set header trước handler, có thể ở preHandle nhưng vẫn phải đảm bảo error branches và non-MVC requests theo policy; interceptor không thay thế filter.

## 12. Exception ở các thời điểm khác nhau

### Handler ném trước khi trả response

`preHandle` đã true → handler ném → `postHandle` không chạy; MVC `HandlerExceptionResolver` cố xử lý; `afterCompletion` thường chạy cho interceptor đã active. Nếu exception được resolver xử lý thì `ex` của completion có thể null. Dùng `response.getStatus()` để quan sát status cuối, không suy theo exception argument duy nhất.

### postHandle tự ném exception

Một interceptor có thể ném ngay ở `postHandle`. MVC có thể đi vào exception handling, và completion vẫn được trigger cho các interceptors đã qua `preHandle=true`. Nhưng response JSON có thể đã commit; exception handler không nhất thiết sửa được body/status. Tránh logic có side effect nguy hiểm trong postHandle.

### View render thất bại

Với template MVC, `postHandle` có thể đã chạy trước render; nếu view render lỗi sau đó, `afterCompletion` có thể được gọi trong luồng cleanup/exception. Không khẳng định `postHandle` chỉ chạy khi toàn bộ response HTML đã thành công: nó chạy sau handler, trước render.

### preHandle false không phải exception

Nếu interceptor trả false mà không ném exception, đó là đường ngắt chủ động. Nó không kích hoạt `@ExceptionHandler` chỉ vì HTTP status được đặt 403. Đừng đồng nhất `setStatus(403)` với `sendError(403)`: cái sau có thể kích hoạt error handling của container khi response chưa committed.

### Filter exception trước DispatcherServlet

Nếu một Filter ném exception trước khi gọi `chain.doFilter`, interceptor MVC chưa chạy; không có `preHandle`/`postHandle`/`afterCompletion` cho request gốc. Container hoặc filter khác quyết định response. `@RestControllerAdvice` cũng không tự xử lý exception ban đầu ngoài vòng đời DispatcherServlet.

## 13. Các bẫy cấu hình và kỹ thuật

1. **Tin rằng `postHandle` luôn chỉnh được JSON:** handler REST đã có thể ghi body trước callback.
2. **Nghĩ `postHandle` luôn nhận ModelAndView:** REST thường null.
3. **Nghĩ interceptor trả false vẫn nhận afterCompletion của chính nó:** sai.
4. **Không tự tạo response khi trả false:** dẫn tới status/body mơ hồ.
5. **Dọn ThreadLocal chỉ trong afterCompletion:** thiếu nhánh false/throw và async start.
6. **Cho rằng `ex != null` là thước đo duy nhất của lỗi:** resolved exceptions có thể cho ex null; status vẫn 4xx/5xx.
7. **Quên thứ tự ngược:** post/after chạy theo thứ tự B → A.
8. **Tự gọi controller sau khi B trả false:** phá short-circuit.
9. **Dùng interceptor làm security chính:** không bao phủ đầy đủ Filter/Servlet/gateway, cần Spring Security.
10. **Gắn interceptors cho `/**` nhưng không kiểm tra handler resource/error:** behavior có thể khó hiểu.
11. **Đồng nhất một HTTP request với một MVC dispatch:** async có thể dispatch lần hai.
12. **Nghĩ async request vẫn chạy post/after ở dispatch đầu:** callback đúng là `afterConcurrentHandlingStarted`.
13. **Không kiểm soát timeout async:** có thể không có dispatch hoàn tất; cần callbacks async chuyên biệt.
14. **Đặt trace trong singleton field:** request song song trộn dữ liệu.
15. **Ghi response cả ở preHandle false và trong controller:** controller không chạy, nhưng code gọi chain lại/hook sai có thể double write.
16. **Không test nhánh error:** happy-path không đủ chứng minh cleanup.
17. **Dùng `@ControllerAdvice` để bắt mọi filter exception:** advice thuộc phạm vi MVC.
18. **Nhầm HTTP status do servlet filter thành exception handler:** một response 403 có thể không chứa Java exception.
19. **Đưa rejected values/headers nhạy cảm vào interceptor log:** nguy cơ lộ PII/token.
20. **Bỏ qua context path trong URL matcher thủ công:** hãy dùng `addPathPatterns` thay vì kiểm tra chuỗi URI tùy tiện khi có thể.
21. **Không xem response committed:** set header/status trong afterCompletion thường quá muộn.
22. **Coi HandlerInterceptor là request lifecycle hook duy nhất:** filter và Servlet async lifecycle cần cơ chế riêng.
23. **Bất biến giả định mọi handler đều là HandlerMethod:** resource handlers cũng có thể match; dùng `instanceof HandlerMethod` nếu cần inspect annotations.
24. **Dùng ThreadLocal cross-thread cho metrics async:** truyền request attribute hoặc context phù hợp.

## 14. Debug callback không chạy như mong đợi

Khi một breakpoint trong `postHandle`/`afterCompletion` không được hit:

1. **Request có vào DispatcherServlet chưa?** Kiểm tra gateway, Servlet Filter, Spring Security, request log.
2. **HandlerMapping có tìm đúng handler không?** Có thể 404 hoặc tài nguyên static được handler khác xử lý.
3. **Interceptor có match pattern không?** Xem `addPathPatterns`/`excludePathPatterns`, context path, matching strategy.
4. **Có interceptor trước nó trả false?** Khi đó interceptor phía sau chưa được gọi.
5. **Chính interceptor đó trả false?** Không mong `afterCompletion` của chính nó.
6. **preHandle có ném exception?** Cleanup của chính interceptor cần nằm ở nhánh lỗi.
7. **Controller có ném exception?** Không kỳ vọng `postHandle` sau handler ném.
8. **Đã bắt đầu MVC async?** Kỳ vọng `afterConcurrentHandlingStarted` ở dispatch đầu, còn post/after trên dispatch cuối nếu có.
9. **Response là @ResponseBody hay view?** `mav` null và response commit thay đổi khả năng sửa dữ liệu.
10. **Exception đã được advice xử lý chưa?** `ex` có thể null dù HTTP status 409/500.
11. **Đã render xong view chưa?** `postHandle` trước rendering; `afterCompletion` sau xử lý.
12. **Có filter/container error handling khác?** Không phải lỗi nào cũng vào MVC interceptor chain.
13. **Có custom HandlerAdapter/HandlerMapping?** Một số ứng dụng có chain khác.
14. **Có virtual thread/async wrapper không?** Không coi callback thread giống nhau; quản lý state an toàn.
15. **Test MockMvc hay HTTP thật?** MockMvc kiểm tra MVC lifecycle, nhưng container async error dispatch/connection reset cần integration test thực.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Đăng ký A trước B, đồng bộ thành công thì thứ tự gọi?

**Đáp án:** A.pre, B.pre, handler, B.post, A.post, B.after, A.after.

**Câu 2.** A.pre trả true nhưng B.pre trả false thì những callback nào tiếp tục?

**Đáp án:** Spring bỏ qua handler và mọi post; gọi A.after, không gọi B.after. B phải tự tạo response hợp lệ và tự dọn tài nguyên nó sở hữu.

**Câu 3.** Nếu A.pre trả false ngay?

**Đáp án:** Không chạy B hay handler; A.after không chạy vì A chưa trả true.

**Câu 4.** Controller ném exception rồi `@RestControllerAdvice` xử lý?

**Đáp án:** postHandle không chạy theo đường handler ném; afterCompletion của các interceptor đã trả true vẫn thường chạy. `ex` có thể null do exception đã được resolver giải quyết.

**Câu 5.** Vì sao `postHandle` không phù hợp để sửa body JSON?

**Đáp án:** `@ResponseBody`/`ResponseEntity` thường đã được serializer/HandlerAdapter ghi trước postHandle, response có thể đã commit. Dùng `ResponseBodyAdvice` hoặc response contract ở controller.

**Câu 6.** Nếu controller trả `Callable`, callback nào thay cho post/after trên dispatch đầu?

**Đáp án:** `AsyncHandlerInterceptor.afterConcurrentHandlingStarted`.

**Câu 7.** Sau async processing thành công có thể xảy ra gì?

**Đáp án:** Container tạo ASYNC dispatch, MVC lại gọi preHandle, postHandle và afterCompletion trong lifecycle xử lý kết quả. Timeout/network error có thể khiến không có dispatch cuối thông thường.

**Câu 8.** `afterCompletion(ex == null)` có bảo đảm response là 200?

**Đáp án:** Không. Có thể là 403 do short-circuit khác hoặc exception đã xử lý thành 409; phải xem response status và ngữ cảnh.

**Câu 9.** Filter từ chối trước DispatcherServlet có làm chạy preHandle không?

**Đáp án:** Không. Request chưa đến MVC HandlerExecutionChain.

**Câu 10.** Một `ThreadLocal` được set trong preHandle nên dọn ở đâu?

**Đáp án:** Cần quản lý mọi nhánh (false/throw, normal completion, async start), và restore giá trị cũ khi cần; chỉ dựa vào afterCompletion là thiếu.

## 16. Checklist thiết kế

- [ ] Interceptor chỉ match những route phù hợp và có purpose rõ.
- [ ] `preHandle=false` có status/body/redirect được tạo có chủ đích.
- [ ] Mọi interceptor sở hữu tài nguyên dọn đúng cả nhánh false/throw.
- [ ] ModelAndView được kiểm tra null trước khi thêm attributes.
- [ ] Không cố sửa JSON body/header ở postHandle sau khi committed.
- [ ] Không coi ex==null là request thành công tuyệt đối.
- [ ] Không dùng interceptor làm security boundary chính.
- [ ] Đã kiểm tra thứ tự đăng ký và thứ tự đảo của post/after.
- [ ] Đã test request bình thường, block, controller exception và async.
- [ ] Với async, có `afterConcurrentHandlingStarted` và kế hoạch timeout cleanup.
- [ ] State theo request không dùng mutable singleton dùng chung.
- [ ] Tracing/logging không lộ token, cookie, PII.
- [ ] Chú ý Servlet Filter và error dispatch không nằm trọn trong interceptor lifecycle.
- [ ] Kiểm thử behavior trên bản Spring MVC thực tế đang dùng.

## 17. Tài liệu tham khảo

- Spring Framework 6.2 — Interception: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — MVC Interceptors config: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
- Spring Framework 6.2 — HandlerInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework 6.2 — AsyncHandlerInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html
- Spring Framework 6.2 — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework 6.2 — ResponseBodyAdvice: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyAdvice.html
- Spring Framework — @ControllerAdvice and error responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Jakarta Servlet Specification — request and async lifecycle: https://jakarta.ee/specifications/servlet/
