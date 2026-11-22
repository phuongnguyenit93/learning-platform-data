# Đường đi qua Servlet container, FilterChain và DispatcherServlet trong Spring MVC

Một HTTP request đi vào ứng dụng **Spring Boot dùng Spring MVC** phải đi qua nhiều lớp trước khi tới phương thức `@GetMapping` hoặc `@PostMapping`. Ba thành phần rất dễ bị nhầm lẫn là **Servlet container**, **Servlet FilterChain** và **DispatcherServlet**. Chúng làm việc ở những mức khác nhau:

- **Servlet container** (ví dụ embedded Tomcat, Jetty hoặc Undertow) nhận kết nối, phân tích HTTP, xác định ứng dụng và servlet cần xử lý, quản lý vòng đời request/response và triển khai Jakarta Servlet.
- **FilterChain** là chuỗi `Filter` của Servlet được container chọn cho request. Mỗi filter có thể kiểm tra, biến đổi, cho đi tiếp hoặc chặn request trước khi nó đến servlet; filter cũng có thể xử lý response trên đường quay ra.
- **DispatcherServlet** là **Front Controller** của Spring MVC. Nó tiếp nhận request đã đi qua filter và điều phối `HandlerMapping`, `HandlerAdapter`, controller, cơ chế binding, exception resolver, view hoặc response body.

Hiểu chính xác đường đi này giúp đặt logging, security, CORS, authentication, request validation và exception handling đúng tầng; đồng thời giải thích tại sao một request trả 401 trước controller, 404 trong MVC hoặc 500 sau khi xử lý.

## 1. Sơ đồ tổng thể của request và response

Trong cấu hình Servlet MVC phổ biến, một request tới endpoint `GET /api/hello?name=Lan` đi theo hướng:

~~~text
HTTP client
    |
    v
Socket / HTTP connector của Servlet container
    |
    v
Container chọn web application + Servlet mapping
    |
    v
Filter 1 --> Filter 2 --> ... --> Filter N
    |           |                    |
    |           |    chain.doFilter()
    |           +--------------------+
    v
DispatcherServlet (Spring MVC front controller)
    |
    +--> HandlerMapping: tìm handler + interceptor chain
    |
    +--> HandlerInterceptor.preHandle(...)
    |
    +--> HandlerAdapter: chuẩn bị và gọi controller
    |        +--> resolve argument, binding, validation
    |        +--> Controller / handler method
    |        +--> xử lý return value / HTTP body
    |
    +--> postHandle(...) nếu nhánh xử lý phù hợp
    |
    +--> render view hoặc hoàn thiện response
    |
    +--> afterCompletion(...) khi xử lý kết thúc
    |
    v
Filter N kết thúc --> ... --> Filter 1 kết thúc
    |
    v
Servlet container ghi response ra kết nối
    |
    v
HTTP client
~~~

Sơ đồ biểu diễn đường đi **đồng bộ, thành công, thường gặp**. Thứ tự chi tiết thay đổi khi một filter chủ động chặn, Spring Security từ chối truy cập, controller ném exception, Servlet error dispatch, hoặc request chuyển sang xử lý bất đồng bộ.

**Điểm quan trọng:** URL không nhất thiết phải đi tới một controller. Filter có thể trả response ngay; DispatcherServlet có thể chọn handler phục vụ static resource, xử lý lỗi hoặc kết thúc với 404 nếu không có handler phù hợp.

## 2. Lớp thứ nhất: Servlet container nhận HTTP request

Embedded Tomcat là lựa chọn thông thường của `spring-boot-starter-web`; Jetty hoặc Undertow có thể thay thế khi dependency được cấu hình tương ứng. Cả ba triển khai Servlet runtime và sử dụng mô hình Spring MVC ở lớp phía trên.

Khi HTTP client kết nối, container thực hiện một số bước:

1. Nhận kết nối TCP hoặc TLS tại listener/connector đã cấu hình.
2. Phân tích HTTP method, request target, headers, query string và các phần cần thiết của request body.
3. Xác định virtual host, web application context path và servlet mapping ứng với URL.
4. Tạo/cấp các đối tượng `HttpServletRequest` và `HttpServletResponse` cho luồng xử lý Servlet.
5. Chọn các filter phù hợp theo URL pattern, servlet name và dispatcher type.
6. Gọi filter chain; filter cuối cùng chuyển tiếp tới servlet được ánh xạ.

Spring Boot khởi tạo Servlet container và đăng ký Spring MVC `DispatcherServlet` cho ứng dụng. Trong cấu hình thông thường, DispatcherServlet được map vào `/`, nhưng mapping có thể được tùy chỉnh. Context path `server.servlet.context-path` là tiền tố của toàn ứng dụng, khác với mapping riêng của DispatcherServlet và khác với đường dẫn của controller.

Ví dụ với context path `/shop` và controller mapping `/api/hello`, client thường gọi `/shop/api/hello`. Container nhận biết context path trước khi DispatcherServlet chọn handler.

### 2.1. Kết nối không đồng nghĩa với controller thread

Một kết nối keep-alive có thể phục vụ nhiều HTTP request theo thời gian. Ở Servlet stack truyền thống, request đồng bộ thường sử dụng worker thread của container trong khoảng xử lý, nhưng số socket đang mở không nhất thiết bằng số request đang thực thi.

Một filter hoặc controller giữ thread để chờ SQL/API bên ngoài quá lâu có thể làm cạn worker pool. Vì vậy, các công đoạn trước và trong DispatcherServlet đều ảnh hưởng thời gian phản hồi; giới hạn thread, timeout và connection pool cần được đo cùng nhau.

## 3. Lớp thứ hai: Servlet FilterChain

Một `Filter` triển khai API **Jakarta Servlet**, không phải cơ chế chỉ dành riêng cho Spring MVC. Trong Spring Boot 3.x, package là `jakarta.servlet.*`; ví dụ cũ dùng `javax.servlet.*` của thời Spring Boot 2.x cần được cập nhật khi nâng phiên bản.

Một filter thường có dạng:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
) throws IOException, ServletException {
    // Logic chạy trước servlet
    try {
        chain.doFilter(request, response);
    } finally {
        // Logic chạy khi call stack thoát, kể cả lúc xảy ra exception
    }
}
~~~

Đây là fragment minh họa cấu trúc phương thức trong một class implements Filter; chưa phải chương trình Java độc lập. Phương thức `chain.doFilter(request, response)` chuyển tiếp tới filter kế tiếp hoặc servlet cuối cùng. Nếu filter không gọi phương thức này, request **không tiếp tục** đi qua chain theo đường thông thường.

### 3.1. Filter có thể làm gì?

- Ghi nhận thời gian xử lý, correlation ID hoặc thông tin request ở mức HTTP.
- Kiểm tra header, thực thi các chính sách bảo vệ HTTP và giới hạn kích thước.
- Bọc request/response bằng `HttpServletRequestWrapper` hay `HttpServletResponseWrapper`.
- Thiết lập encoding, kiểm soát một số response header.
- Từ chối request sớm, ví dụ gửi HTTP 400/403 rồi dừng chain.
- Tích hợp Spring Security thông qua các filter được đăng ký với Servlet container.

Filter không tự biết handler method nào sẽ được Spring MVC chọn. Nó chạy trước bước tìm controller của DispatcherServlet và có thể áp dụng cho cả request không được controller xử lý.

### 3.2. Thứ tự các filter ảnh hưởng hành vi

Filter thường được xếp theo thứ tự đăng ký hoặc `FilterRegistrationBean.setOrder(...)` trong ứng dụng Spring Boot. Filter ở đầu chuỗi chạy phần “before” trước, rồi phần “after” khi lời gọi lồng nhau trở về:

~~~text
Filter A: before
  Filter B: before
    DispatcherServlet xử lý
  Filter B: after
Filter A: after
~~~

Nếu Filter A quyết định trả response mà không gọi `chain.doFilter`, Filter B và DispatcherServlet sẽ không được gọi cho lần đi qua chain đó. Bởi vậy, một controller không được gọi **không có nghĩa** request chưa đến server; nó có thể đã bị chặn ở filter.

Khi cấu hình filter, cần xác định:

- URL pattern và servlet mapping cần áp dụng.
- Dispatcher type, chẳng hạn `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`.
- Thứ tự filter so với các filter khác, đặc biệt là security.
- Có cần hoạt động trên các lần async/error dispatch hay không.
- Header/response đã bị commit hay chưa khi filter muốn sửa nội dung.

### 3.3. OncePerRequestFilter

Spring cung cấp `OncePerRequestFilter` như một lớp cơ sở tiện dụng để tránh gọi lại logic filter nhiều lần trong **một lần dispatch** nhất định. Tên lớp không có nghĩa tuyệt đối rằng logic chỉ chạy đúng một lần trong toàn bộ vòng đời bất đồng bộ của mọi request. Hành vi với async và error dispatch còn phụ thuộc cấu hình và các phương thức như `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`.

Đây là lựa chọn thuận tiện cho request logging đơn giản. Không nên tự đọc toàn bộ request body trong filter để log mà không xử lý khả năng stream chỉ được tiêu thụ một lần, giới hạn kích thước và bảo vệ dữ liệu nhạy cảm.

### 3.4. Filter và Spring Security

Với Spring Security ở Servlet stack, container thường gọi một `DelegatingFilterProxy` liên kết tới bean filter chain của Spring Security. `FilterChainProxy` sau đó lựa chọn một `SecurityFilterChain` tương ứng và chạy các security filter theo thứ tự riêng.

Do đó, authentication và authorization có thể kết thúc request **trước khi DispatcherServlet tìm controller**. Một response 401 hoặc 403 từ Spring Security thường không đi qua `@ExceptionHandler` của controller như một exception phát sinh trong handler method.

Không tự chèn filter đăng nhập hoặc phân quyền theo cảm tính: phải kiểm tra thứ tự và tích hợp đúng với Spring Security để tránh thực thi sai tầng, trùng logic hoặc mở lỗ hổng.

## 4. Lớp thứ ba: DispatcherServlet điều phối Spring MVC

`DispatcherServlet` là một Servlet thật được container gọi sau các filter tương ứng. Nó tổ chức quy trình request bằng các chiến lược của Spring MVC, thay vì tự chứa nghiệp vụ của từng endpoint.

Đường đi chính gồm các thành phần:

| Thành phần | Vai trò |
|---|---|
| `DispatcherServlet` | Nhận request từ Servlet API và điều phối toàn bộ quy trình MVC |
| `HandlerMapping` | Xác định handler phù hợp với method, URL và điều kiện mapping; trả về `HandlerExecutionChain` |
| `HandlerExecutionChain` | Gồm handler đã chọn và các `HandlerInterceptor` liên quan |
| `HandlerInterceptor` | Chạy trước/sau handler trong phạm vi MVC |
| `HandlerAdapter` | Biết cách thực thi loại handler đã tìm được |
| `HandlerMethodArgumentResolver` | Chuẩn bị giá trị tham số của controller |
| `HttpMessageConverter` | Đọc request body và ghi response body cho các kiểu nội dung tương ứng |
| `HandlerExceptionResolver` | Cố gắng biến exception trong quá trình MVC thành response có thể xử lý |
| `ViewResolver` và View | Phục vụ kiểu controller cần render view, ví dụ Thymeleaf |

### 4.1. HandlerMapping tìm controller

Giả sử controller:

~~~java
@RestController
@RequestMapping("/api")
class GreetingController {

    @GetMapping("/hello")
    String hello() {
        return "Hello";
    }
}
~~~

Đây là fragment cần các import Spring MVC và class ứng dụng Spring Boot bao quanh. Nếu ứng dụng map Servlet mặc định và không có context path, `GET /api/hello` thường được ánh xạ đến phương thức `hello()` bởi `RequestMappingHandlerMapping`.

HandlerMapping có thể xét thêm HTTP method, `consumes`, `produces`, headers và params. URL đúng nhưng HTTP method sai có thể dẫn đến 405; các điều kiện content type và acceptable media type có thể dẫn đến 415 hoặc 406. Không phải mọi request thất bại đều là 404.

Nếu không tìm được handler phù hợp, Spring MVC có cơ chế xử lý lỗi 404; trong một số cấu hình request có thể khớp với static-resource handler rồi báo resource không tồn tại. Không nên dựa vào một kiểu exception duy nhất cho mọi trường hợp 404.

### 4.2. HandlerAdapter gọi controller

Sau khi HandlerMapping trả handler, DispatcherServlet tìm `HandlerAdapter` hỗ trợ nó. Với controller có annotation, `RequestMappingHandlerAdapter` thường đảm nhiệm việc gọi phương thức.

Trước khi gọi controller, hệ thống có thể:

- Đọc `@PathVariable`, `@RequestParam`, `@RequestHeader`.
- Bind `@ModelAttribute` từ tham số request.
- Dùng `HttpMessageConverter` để đọc JSON thành object Java cho `@RequestBody`.
- Thực hiện validation nếu có `@Valid` hoặc cơ chế validation tương ứng.
- Chuẩn bị `Principal`, `HttpServletRequest`, `HttpServletResponse` hoặc các kiểu tham số hỗ trợ khác.

Nếu JSON sai, tham số thiếu hoặc validation không đạt, exception có thể xuất hiện **trước khi thân controller chạy**. Điều này giải thích tại sao log “bắt đầu controller” không phải lúc nào cũng xuất hiện cho một request đã đi vào DispatcherServlet.

### 4.3. Controller xử lý nghiệp vụ và tạo kết quả

Controller gọi service/repository, sau đó trả `String`, DTO, `ResponseEntity`, `ModelAndView` hoặc kiểu trả về khác.

Với `@RestController`, giá trị trả về thường được xử lý như response body. `HttpMessageConverter` lựa chọn cách mã hóa String, JSON, byte array, v.v. tùy kiểu dữ liệu và negotiation. Với MVC view, Spring MVC giải quyết view name và render view. Hai đường này đều do DispatcherServlet và HandlerAdapter điều phối, nhưng thời điểm ghi response body và render view có khác nhau.

**Lưu ý về thời điểm:** trong controller trả `@ResponseBody`, quá trình ghi body bằng message converter có thể xảy ra trong lúc HandlerAdapter xử lý return value, **trước** callback `postHandle`. Vì vậy, `postHandle` không thích hợp để giả định rằng response chưa được ghi/commit và có thể sửa tùy ý.

## 5. HandlerInterceptor nằm ở đâu so với Filter?

`HandlerInterceptor` thuộc **Spring MVC** và chạy sau khi DispatcherServlet đã chọn handler phù hợp. Đây là lý do interceptor có thể xem handler được chọn, còn Servlet Filter thường không biết controller nào sẽ được gọi.

Ba callback quan trọng:

- **preHandle(request, response, handler)** chạy trước khi HandlerAdapter gọi handler. Trả `true` để tiếp tục; trả `false` để dừng xử lý handler theo nhánh đó.
- **postHandle(request, response, handler, modelAndView)** chạy sau khi handler được thực thi thành công theo luồng đồng bộ thông thường, trước khi render view. Nó có thể không được gọi trong một số nhánh exception hoặc asynchronous.
- **afterCompletion(request, response, handler, exception)** dùng để dọn dẹp khi request đã kết thúc xử lý MVC; chỉ interceptor đã vượt qua preHandle phù hợp mới có callback hoàn tất theo cơ chế của Spring MVC. Với async, hành vi callback có khác và có thể có lần dispatch tiếp theo.

So sánh nhanh:

| Tiêu chí | Servlet Filter | HandlerInterceptor |
|---|---|---|
| Thuộc hệ thống | Jakarta Servlet container | Spring MVC |
| Thời điểm | Trước khi DispatcherServlet xử lý, đồng thời bọc đường response trở ra | Sau khi MVC tìm handler |
| Biết handler/controller? | Không theo API Servlet thông thường | Có tham số handler |
| Áp dụng cho | URL/servlet/dispatcher types được đăng ký, có thể cả request không vào MVC | Request thuộc handler chain của Spring MVC |
| Dừng xử lý | Không gọi `chain.doFilter`; tự tạo response | `preHandle` trả `false`; thường tự tạo response nếu cần |
| Dùng phù hợp | HTTP security filters, request wrapping, correlation/logging ở tầng Servlet | Logic phụ thuộc handler, kiểm tra hoặc theo dõi trong tầng MVC |

Đừng dùng HandlerInterceptor làm hàng rào bảo mật duy nhất cho ứng dụng khi yêu cầu phân quyền trước MVC. Với security, ưu tiên cơ chế Spring Security phù hợp; interceptor hữu ích hơn cho logic liên quan trực tiếp tới MVC handler.

## 6. Ví dụ Java chạy được: theo dõi Filter → Interceptor → Controller

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.x**, **Spring MVC**, embedded Tomcat mặc định từ `spring-boot-starter-web`. Tệp Java có một public class và các class package-private để có thể chạy trong cùng một source file.

Gradle Groovy DSL trong dự án Spring Boot đã cấu hình plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tạo tệp **src/main/java/demo/flow/MvcFlowApplication.java**:

~~~java
package demo.flow;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFlowApplication.class, args);
    }
}

@Component
class RequestTraceFilter extends OncePerRequestFilter {

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"/flow".equals(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        System.out.println("Filter before");
        try {
            filterChain.doFilter(request, response);
        } finally {
            System.out.println("Filter after");
        }
    }
}

@Configuration(proxyBeanMethods = false)
class FlowMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {

            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler
            ) {
                System.out.println("Interceptor pre");
                return true;
            }

            @Override
            public void postHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    ModelAndView modelAndView
            ) {
                System.out.println("Interceptor post");
            }

            @Override
            public void afterCompletion(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    Exception exception
            ) {
                System.out.println("Interceptor afterCompletion");
            }
        }).addPathPatterns("/flow");
    }
}

@RestController
class FlowController {

    @GetMapping("/flow")
    public String flow() {
        System.out.println("Controller");
        return "ok";
    }
}
~~~

Lớp main có cùng tên với tệp; các class còn lại cùng package nên được `@SpringBootApplication` quét. Code sử dụng import `jakarta.servlet.*`, phù hợp với Spring Boot 3.x. `RequestTraceFilter` giới hạn log ở `/flow` để các request khác không làm nhiễu ví dụ; giả định context path mặc định là rỗng.

Khởi động bằng Gradle wrapper của dự án, với main class được phát hiện hoặc cấu hình đúng:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Khi web server đã khởi động, tại terminal khác gọi:

~~~bash
curl -i http://localhost:8080/flow
~~~

Với duy nhất endpoint minh họa, cổng 8080 rảnh, không có Spring Security hoặc custom filter khác chặn request, HTTP response có status **200 OK** và body chính xác:

~~~text
ok
~~~

Ngoài log khởi động Spring Boot, **sáu dòng do mã ví dụ chủ động in ra**, theo thứ tự, là:

~~~text
Filter before
Interceptor pre
Controller
Interceptor post
Interceptor afterCompletion
Filter after
~~~

Giải thích thứ tự:

1. `RequestTraceFilter` được Servlet container gọi trước DispatcherServlet.
2. `filterChain.doFilter` tiếp tục đến Spring MVC.
3. DispatcherServlet tìm `FlowController.flow()`, rồi gọi `preHandle`.
4. Controller in `Controller` và trả chuỗi `ok`.
5. DispatcherServlet hoàn tất nhánh đồng bộ, gọi `postHandle`, sau đó `afterCompletion`.
6. Luồng điều khiển quay về block `finally` của filter và in `Filter after`.

Thử thay `return true` trong `preHandle` thành `return false` **chỉ để hiểu cơ chế trong môi trường thử nghiệm**: controller sẽ bị bỏ qua; nếu interceptor không tự đặt status/body, response có thể không đúng mong đợi của client. Một interceptor chặn request thật phải tạo response có status và thông điệp thích hợp.

## 7. Request body, response body và các lỗi thông thường

Khi request chứa JSON:

~~~text
POST /api/orders
Content-Type: application/json
{"productId":10,"quantity":2}
~~~

Filter có thể kiểm tra header trước, nhưng việc deserialize thành Java object cho `@RequestBody` thường được thực hiện bởi `HttpMessageConverter` trong Spring MVC. Nếu content type không được hỗ trợ, JSON không hợp lệ hoặc validation lỗi, handler có thể chưa được thực thi.

Với response JSON, `@RestController` hoặc `@ResponseBody` thường kích hoạt return-value handler và một JSON message converter (thường Jackson nếu có dependency). Điều này diễn ra **bên trong** lộ trình MVC; Servlet container chịu trách nhiệm truyền bytes qua HTTP connection và quản lý trạng thái response.

Một số vị trí lỗi điển hình:

| Tình huống | Lớp thường xử lý | Dấu hiệu |
|---|---|---|
| Filter chặn header hoặc rate limit | Filter ở Servlet container | Controller không chạy |
| Spring Security từ chối | Security filter chain trước MVC | Thường 401 hoặc 403 theo cấu hình |
| Không có mapping phù hợp | DispatcherServlet / HandlerMapping / resource handler | Thường 404 |
| URL đúng, HTTP method không phù hợp | MVC mapping/exception resolution | Thường 405 |
| Request body JSON hỏng | Argument resolution / HttpMessageConverter | Thường 400 |
| Controller ném exception được xử lý | HandlerExceptionResolver / `@ExceptionHandler` | HTTP status/body theo handler |
| Exception không xử lý được | Container error handling / Spring Boot error dispatch | Thường 500 hoặc lỗi khác tùy trường hợp |

Đừng coi mọi lỗi 4xx hoặc 5xx là do controller ném exception. Điểm phát sinh lỗi quyết định cơ chế có cơ hội xử lý lỗi đó.

## 8. Exception handling và error dispatch

Trong Spring MVC, `HandlerExceptionResolver` có nhiệm vụ tìm cách xử lý exception phát sinh khi xác định hoặc gọi handler. Cơ chế quen thuộc gồm:

- `@ExceptionHandler` đặt trong controller hoặc `@ControllerAdvice`/`@RestControllerAdvice`.
- Các resolver xử lý exception do Spring MVC tự phát sinh, ví dụ method không hỗ trợ hoặc lỗi tham số.
- Cơ chế fallback của Spring Boot/container khi lỗi không được xử lý thành response phù hợp.

**Exception phát sinh trong filter trước khi vào DispatcherServlet không tự được giải quyết bởi `@ControllerAdvice`**. Vì DispatcherServlet chưa nắm quyền điều phối request ở thời điểm đó, xử lý filter error cần cơ chế thuộc filter/security/container hoặc chuyển tiếp có chủ đích với logic được thiết kế riêng.

Khi xảy ra lỗi chưa xử lý, container có thể tạo một lần **ERROR dispatch** tới đường dẫn lỗi (thường `/error` trong Spring Boot). Đây là một lần dispatch khác, nên filter nào được gọi lại phụ thuộc dispatcher type được đăng ký và quy tắc của filter. Không mặc định rằng mọi filter luôn được gọi đúng một lần cho toàn bộ một request.

Một response đã **committed** (headers/body đã được gửi đi) không thể được sửa status hoặc headers tùy ý. Ví dụ, nếu đã stream được một phần response rồi mới lỗi, handler lỗi có thể không tạo được một JSON error body mới hoàn chỉnh. Vì thế, logging hoặc response wrapping cần tính đến thời điểm commit.

### 8.1. Vì sao postHandle có thể không chạy?

Với request đồng bộ thành công, `postHandle` thường được gọi như ví dụ. Khi exception phát sinh trong handler hoặc bước xử lý return value, Spring MVC có thể chuyển ngay tới nhánh exception resolver, nên **không thể dựa vào postHandle như một callback chắc chắn cho mọi request**.

`afterCompletion` hữu ích hơn để dọn dẹp trạng thái gắn với MVC handler theo cơ chế interceptor, nhưng cũng không nên hiểu là được gọi khi bất kỳ filter nào chặn request trước DispatcherServlet. `Filter` dùng `try/finally` quanh `chain.doFilter` khi cần dọn dẹp tài nguyên ở tầng Servlet.

## 9. Xử lý bất đồng bộ (async dispatch) làm luồng khác đi

Spring MVC hỗ trợ những dạng trả về bất đồng bộ như `Callable`, `DeferredResult`, `WebAsyncTask`, và một số kiểu streaming. Khi handler bắt đầu xử lý Servlet async, thread ban đầu có thể quay về container trước khi công việc và response kết thúc.

Một chuỗi đại diện:

~~~text
REQUEST dispatch ban đầu
  FilterChain
    DispatcherServlet
      HandlerInterceptor.preHandle
      Controller bắt đầu tác vụ async
      AsyncHandlerInterceptor.afterConcurrentHandlingStarted (nếu hỗ trợ)
  Thread ban đầu quay về container

Tác vụ async hoàn tất
  Container ASYNC dispatch
    FilterChain nếu đăng ký cho ASYNC
      DispatcherServlet tiếp tục xử lý kết quả
      MVC hoàn thiện response và lifecycle callbacks
~~~

Đây là mô hình khái quát, không phải lời hứa mọi hình thức async đều có chính xác cùng một số lần callback. Tùy kiểu xử lý và cấu hình filter, `postHandle`/`afterCompletion` có thể không chạy ở request thread ban đầu; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` tồn tại cho tình huống này.

Nếu ứng dụng cần correlation ID, MDC hoặc trace context xuyên thread, phải có cơ chế truyền context phù hợp. Chỉ đặt dữ liệu vào `ThreadLocal` của request thread rồi cho rằng một thread khác tự nhìn thấy là không chính xác.

`@Async` gọi một phương thức ở background **không tự đồng nghĩa** với việc HTTP request được xử lý qua Servlet async lifecycle. Cần phân biệt task executor thông thường với cơ chế MVC async return types.

## 10. Filter, Interceptor hay ControllerAdvice?

Chọn điểm mở rộng dựa trên vị trí mong muốn trong pipeline:

- **Filter** cho việc phải diễn ra trước Spring MVC, hoặc có thể áp dụng cho các Servlet và URL khác: request ID, security chain, request wrapping, HTTP policy.
- **HandlerInterceptor** cho việc cần biết handler Spring MVC: thống kê theo controller, điều kiện liên quan handler, ghi thời gian trong pipeline MVC.
- **@ControllerAdvice / @ExceptionHandler** cho xử lý exception phát sinh trong phạm vi Spring MVC: chuẩn hóa status và error body.
- **@RestController / @Controller** cho HTTP endpoint, binding request và gọi nghiệp vụ.
- **Service** cho nghiệp vụ có thể kiểm thử và tái sử dụng, tránh nhồi logic vào filter hoặc interceptor.
- **Servlet container config** cho giới hạn kết nối, thread, TLS, HTTP connector và các thuộc tính runtime của embedded server.

Ví dụ, việc xác thực JWT nên dùng cơ chế Spring Security ở vị trí thích hợp trong security chain; chuẩn hóa `MethodArgumentNotValidException` nên dùng exception handling của MVC; logic kiểm tra quyền nghiệp vụ có thể cần security method authorization và service.

## 11. Cấu hình filter và lỗi đăng ký hai lần

Trong Spring Boot có thể đăng ký một Servlet Filter bằng `@Component` cho bean implements Filter hoặc bằng một `FilterRegistrationBean` có URL patterns, order và dispatcher types cụ thể. Không nên vừa để cùng một filter tự được đăng ký như bean, vừa đăng ký thủ công một instance khác mà không kiểm soát, vì có thể tạo ra hai lần chạy logic cho cùng request.

Ví dụ fragment đăng ký filter theo URL và thứ tự, dùng trong một class `@Configuration` đã có bean `requestTraceFilter`:

~~~java
@Bean
FilterRegistrationBean<RequestTraceFilter> traceRegistration(
        RequestTraceFilter requestTraceFilter
) {
    FilterRegistrationBean<RequestTraceFilter> registration =
            new FilterRegistrationBean<>();
    registration.setFilter(requestTraceFilter);
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
~~~

Đây là **fragment**, cần import `FilterRegistrationBean`, `@Bean` và có class filter tương ứng. Nếu chọn cách đăng ký này, đảm bảo chỉ có một registration chủ đích. Lưu ý filter được chọn qua URL pattern `/api/*` ở tầng Servlet, nên một route MVC khác không trùng pattern sẽ không chạy qua registration đó.

Không đặt order theo giả định “số 10 chắc chắn chạy trước Spring Security”. Hãy kiểm tra các `FilterRegistrationBean`, các filter mặc định của Spring Boot và cấu hình Security thực tế. Thứ tự các security filter **bên trong** `FilterChainProxy` do cơ chế Spring Security quản lý riêng.

## 12. Kiểm thử request lifecycle và chẩn đoán lỗi

### 12.1. Kiểm tra đơn vị ở tầng MVC

`MockMvc` giúp kiểm tra controller mapping, validation, MVC interceptors, exception handling và các filter được đưa vào cấu hình test. Tuy nhiên, MockMvc không phải một TCP server thật. Một test thành công với MockMvc không chứng minh Tomcat connector, TLS, socket timeout hoặc native Servlet dispatch hoạt động giống production.

### 12.2. Kiểm tra qua embedded server thật

Với integration test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpFlowTest {
    // Gọi HTTP đến cổng ngẫu nhiên do test khởi động;
    // dùng TestRestTemplate, RestClient hoặc HTTP client phù hợp.
}
~~~

Đây là fragment mô tả lựa chọn test, chưa phải test class hoàn chỉnh. Khi tích hợp, dùng `@LocalServerPort` hoặc công cụ Spring Boot Test để lấy port thực tế, gọi endpoint qua HTTP và xác nhận filter/controller nhận request.

### 12.3. Dấu hiệu và bước điều tra

**Controller không được gọi:**
1. Xác nhận URL, context path, method và port.
2. Kiểm tra status code và filter/security logs.
3. Kiểm tra filter có gọi `chain.doFilter` không.
4. Kiểm tra HandlerMapping có match request không.

**Controller được gọi nhưng response sai:**
1. Kiểm tra return value handler và message converter.
2. Kiểm tra `produces`/`Accept`/`Content-Type`.
3. Kiểm tra filter có sửa response headers/body khi quay ra không.
4. Kiểm tra exception resolver, response commit và error dispatch.

**Filter hoặc interceptor chạy hai lần:**
1. Kiểm tra bean/registration có bị khai báo lặp.
2. Kiểm tra `REQUEST`, `ASYNC`, `ERROR`, `FORWARD` dispatcher types.
3. Kiểm tra request có async processing hoặc error dispatch không.
4. Kiểm tra rule của `OncePerRequestFilter` và cách đo log.

**Thời gian phản hồi cao nhưng controller nhanh:**
1. Đo thời gian trước khi controller được gọi (filters, security, argument binding).
2. Đo thời gian sau controller (serialization, view rendering, response filters).
3. Kiểm tra thread pool, HTTP connector, request body lớn, DB/client calls và thời gian mạng.
4. Đối chiếu tracing span, metrics và log theo request ID, không chỉ thời gian của một phương thức controller.

Tránh log request body, cookies, Authorization header hoặc thông tin cá nhân ở mức quá chi tiết. Với async hoặc nhiều thread, chỉ in stdout không đủ để kết luận thứ tự đa request; cần request ID, timestamp và trace ID để liên kết đúng dữ liệu.

## 13. Checklist nắm chắc luồng Spring MVC

- Xác định ứng dụng chạy **Servlet web stack**, không nhầm với WebFlux reactive pipeline.
- Phân biệt **container/connector** (nhận HTTP), **FilterChain** (chặn hoặc bao quanh request) và **DispatcherServlet** (điều phối MVC).
- Biết `chain.doFilter` có vai trò chuyển request qua filter kế tiếp tới servlet.
- Hiểu `HandlerMapping` tìm handler, `HandlerAdapter` gọi controller và xử lý binding/return value.
- Biết callback interceptor `preHandle`, `postHandle`, `afterCompletion` và giới hạn trong exception/async.
- Đặt authorization/security đúng trong Spring Security filter chain; không kỳ vọng controller advice bắt mọi filter exception.
- Hiểu JSON deserialize/serialize nằm trong cơ chế argument/return-value handling; controller không phải nơi duy nhất có thể phát sinh lỗi.
- Kiểm tra dispatcher type khi thấy filter chạy lại ở `ASYNC` hoặc `ERROR` dispatch.
- Dùng MockMvc để kiểm tra MVC logic, integration test với embedded server thật để kiểm tra end-to-end.
- Đo cả ba giai đoạn trước controller, trong controller và sau controller khi tối ưu latency.

**Ghi nhớ:** request đi qua Servlet container và các filter được đăng ký **trước khi** tới DispatcherServlet. DispatcherServlet mới chọn handler, gọi các interceptor và controller, rồi hoàn thiện MVC response. Trên đường quay ra, filter tiếp tục thực thi phần code sau `chain.doFilter`. Phân biệt đúng các tầng này là nền tảng để đặt logic HTTP, security, exception handling và quan sát hiệu năng ở vị trí chính xác.