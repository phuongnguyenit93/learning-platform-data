# Các kiểu điều phối Servlet: REQUEST, FORWARD, INCLUDE, ERROR và ASYNC

> **Ngữ cảnh:** Spring Security trên nền Servlet (Jakarta Servlet, Java 17+). Một HTTP request từ trình duyệt có thể được Servlet container đưa qua nhiều lượt **dispatch** trong cùng một vòng đời xử lý. Hiểu `DispatcherType` giúp phân tích luồng servlet, viết filter đúng và tránh lỗi phân quyền khi forward, xử lý lỗi hoặc xử lý bất đồng bộ.

## 1. Dispatch là gì và khác HTTP request mới thế nào?

Khi client gửi `GET /demo`, container chọn servlet hoặc tài nguyên thích hợp và tạo lượt xử lý có `request.getDispatcherType() == DispatcherType.REQUEST`. Trong lúc xử lý, ứng dụng có thể chuyển tiếp nội bộ (`forward`), chèn nội dung (`include`), đi vào trang lỗi (`error dispatch`), hoặc tiếp tục xử lý bất đồng bộ (`async dispatch`).

`jakarta.servlet.DispatcherType` có **đúng năm giá trị**: `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR` và `ASYNC`. Đây là **loại lượt điều phối hiện tại**, không phải HTTP method, HTTP status, loại thread, hay một URL.

```text
Client --HTTP--> [REQUEST /entry]
                    |-- RequestDispatcher.forward(...) --> [FORWARD /target]
                    |-- RequestDispatcher.include(...) --> [INCLUDE /fragment] --> quay về /entry
                    |-- lỗi/sendError + error page ------> [ERROR /error-page]
                    |-- startAsync + AsyncContext.dispatch(...) --> [ASYNC /resumed]
```

Các nhánh trên minh họa **những khả năng**, không có nghĩa request nào cũng đi qua đủ năm loại. `forward` và `include` là điều phối **bên trong server**, không phát sinh lệnh HTTP mới từ client. `response.sendRedirect(...)` thì khác: server trả trạng thái chuyển hướng (thường 302) với header `Location` để **client gửi request mới**; lượt request mới thường có loại `REQUEST`.

Để quan sát thực tế, đọc trực tiếp trong servlet/filter:

```java
DispatcherType type = request.getDispatcherType();
System.out.println(type); // Ví dụ: REQUEST, FORWARD, INCLUDE, ERROR hoặc ASYNC
```

## 2. Phân biệt năm loại dispatch

| Loại | Khi nào xuất hiện | Đặc điểm quyết định |
| --- | --- | --- |
| `REQUEST` | Container tiếp nhận một request HTTP thông thường và chuyển đến servlet đầu tiên. | Điểm vào của request; loại mặc định khi ánh xạ servlet filter không khai báo dispatcher type. |
| `FORWARD` | Code gọi `RequestDispatcher.forward(request, response)`. | Container chuyển quyền tạo response cho đích nội bộ, với cùng request/response về mặt logic; forward phải diễn ra trước khi response đã commit. |
| `INCLUDE` | Code gọi `RequestDispatcher.include(request, response)`. | Tài nguyên đích bổ sung nội dung vào response của caller rồi trả điều khiển về caller; đích include không được quyết định status/header của response. |
| `ERROR` | Container điều phối đến error page đã cấu hình sau lỗi/ngoại lệ hoặc `sendError` phù hợp. | Có các thuộc tính `jakarta.servlet.error.*`; chỉ trả status lỗi hoặc tự bắt exception chưa chắc tạo ERROR dispatch. |
| `ASYNC` | `AsyncContext.dispatch(...)` tiếp tục request sau khi đã `startAsync()`. | Là lượt chạy lại qua pipeline trên dispatch bất đồng bộ; `startAsync()` riêng nó **chưa** biến lượt hiện tại thành ASYNC. |

### 2.1. REQUEST — lượt vào ban đầu

Ví dụ: client gửi `GET /orders/42`. Servlet nhận request ở lượt đầu sẽ thấy `DispatcherType.REQUEST`. Container chọn mapping servlet và filter tương ứng theo URL và dispatcher type.

Một filter khai báo `@WebFilter(urlPatterns = "/*")` mà **không chỉ rõ** `dispatcherTypes` chỉ được ánh xạ cho `REQUEST` theo quy tắc Servlet. Vì vậy cùng request sau đó forward hoặc dispatch lỗi có thể đi qua servlet khác mà filter đó không được gọi lại. Không nên suy ra rằng mọi filter chạy trong mọi lượt điều phối.

### 2.2. FORWARD — chuyển xử lý sang tài nguyên nội bộ

```java
request.setAttribute("orderId", 42L);
request.getRequestDispatcher("/internal/order-view")
       .forward(request, response);
return; // Hạn chế ghi thêm nội dung sau forward.
```

Container kích hoạt đích `/internal/order-view` ở lượt `FORWARD`. Các request attribute do caller đặt vẫn truy cập được. Khi forward từ một request thông thường, API cung cấp thuộc tính lưu thông tin đường dẫn gốc, chẳng hạn:

```java
Object originalUri =
    request.getAttribute(RequestDispatcher.FORWARD_REQUEST_URI);
```

Trong servlet đích, các accessor đường dẫn như `getRequestURI()` thường phản ánh **đích forward**, còn thuộc tính `FORWARD_REQUEST_URI` chứa URI ban đầu của lượt điều phối forward đầu tiên. Khi forward xảy ra trước commit, container dọn phần response body đang được buffer để đích tạo response; nếu response đã commit, `forward(...)` có thể ném `IllegalStateException`.

**Khi sử dụng:** chuyển từ controller/servlet trung gian tới tài nguyên server-side cần kết xuất nội dung. Tránh dùng forward để giả lập redirect trong trình duyệt: URL hiển thị trên client không tự đổi sang URL đích forward.

### 2.3. INCLUDE — chèn một phần kết quả vào response hiện tại

```java
response.getWriter().print("Trước|");
request.getRequestDispatcher("/parts/header").include(request, response);
response.getWriter().print("|Sau");
```

Giả sử `/parts/header` ghi `Header` thì body cuối là `Trước|Header|Sau`. Caller tiếp tục chạy sau `include(...)`. Servlet được include có thể ghi vào body, nhưng việc cố thay HTTP status hoặc response header của nó không được dùng để quyết định response của caller.

**Khác với forward:** trong một lượt `INCLUDE`, nhiều accessor đường dẫn trên request vẫn phản ánh resource **đang include**, tức caller; đường dẫn resource được include được cung cấp qua các thuộc tính `jakarta.servlet.include.*`, ví dụ:

```java
Object includedUri =
    request.getAttribute(RequestDispatcher.INCLUDE_REQUEST_URI);
```

Do đó, không nên chỉ nhìn `request.getRequestURI()` rồi kết luận servlet hiện tại được client gọi trực tiếp. Ví dụ thực hành bên dưới ghi log URI của include bằng thuộc tính riêng.

### 2.4. ERROR — lượt xử lý trang lỗi của container

Khi servlet gọi `response.sendError(500)` hoặc ngoại lệ chưa được xử lý dẫn đến cơ chế error page, container **có thể** dispatch đến tài nguyên đã đăng ký xử lý lỗi. Trong servlet đích:

```java
Object code = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
Object source = request.getAttribute(RequestDispatcher.ERROR_REQUEST_URI);
Object exception = request.getAttribute(RequestDispatcher.ERROR_EXCEPTION);
DispatcherType type = request.getDispatcherType(); // ERROR
```

Ví dụ code là `500` và source là URL gây lỗi. Các thuộc tính khác có thể gồm `ERROR_MESSAGE`, `ERROR_EXCEPTION_TYPE` và `ERROR_SERVLET_NAME`. Không phải thuộc tính nào cũng có giá trị trong mọi trường hợp: `sendError` không nhất thiết có exception; một exception có thể được framework xử lý thành response thông thường trước khi container dispatch lỗi.

**Phân biệt:** `response.setStatus(500)` chỉ đặt status, tự nó không yêu cầu container chuyển tới error page. Một controller bắt ngoại lệ và trả JSON lỗi ngay trên cùng lượt cũng có thể vẫn là `REQUEST`. Framework như Spring Boot thường có error endpoint; không được giả định mọi lỗi đều trở thành `ERROR`.

Khi filter được ánh xạ cho `ERROR`, nó có thể chạy lại cho request lỗi. Tùy container và thời điểm lỗi, error dispatch có thể xen vào khi filter chain cũ còn đang chạy. Vì vậy code filter nên an toàn khi có re-entry; đừng dựa vào thứ tự log như một hợp đồng tuyệt đối.

### 2.5. ASYNC — tiếp tục xử lý sau khi nhả request thread ban đầu

Một servlet có thể yêu cầu xử lý bất đồng bộ:

```java
AsyncContext async = request.startAsync();
async.start(() -> {
    // Thực hiện công việc rồi yêu cầu servlet container dispatch trở lại.
    async.dispatch("/result");
});
```

Điều kiện: servlet và tất cả filter tham gia đoạn request cần hỗ trợ async phù hợp (`asyncSupported=true`); nếu không, `startAsync()` có thể ném `IllegalStateException`. Với ví dụ trên, lượt ban đầu vẫn là `REQUEST`; khi container thực thi dispatch tới `/result`, lượt đó là `ASYNC`. Sau lượt dispatch, container hoàn tất response nếu không có chu kỳ async mới; trong hướng xử lý khác có thể gọi `async.complete()` mà **không** dispatch.

Không được đánh đồng `ASYNC` với việc đơn thuần tạo một thread, gọi `CompletableFuture`, hay ghi dữ liệu vào response từ callback. Chỉ lượt điều phối từ `AsyncContext.dispatch(...)` mới mang `DispatcherType.ASYNC`. Phải xử lý timeout, exception, và quy tắc không sử dụng request/response sau khi vòng đời async hoàn tất.

Ở ứng dụng Spring MVC, cơ chế async với `Callable`, `DeferredResult` hoặc các API phù hợp có thể dẫn tới redispatch. Lịch thread và số lần chạy filter phụ thuộc cách đăng ký filter và cơ chế async cụ thể; không mặc định request chỉ đi qua một thread.

## 3. Filter được gọi ở những dispatch nào?

Có **hai điều kiện riêng** để filter được container gọi trong một lượt:

1. URL/servlet mapping của filter khớp tài nguyên của lượt điều phối đó.
2. `DispatcherType` hiện tại nằm trong những dispatcher types được filter đăng ký.

Chẳng hạn:

```java
@WebFilter(
    urlPatterns = "/*",
    dispatcherTypes = {
        DispatcherType.REQUEST,
        DispatcherType.FORWARD,
        DispatcherType.INCLUDE,
        DispatcherType.ERROR,
        DispatcherType.ASYNC
    },
    asyncSupported = true
)
public class TraceFilter implements Filter {
    @Override
    public void doFilter(ServletRequest rawRequest,
                         ServletResponse rawResponse,
                         FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest req = (HttpServletRequest) rawRequest;
        System.out.println(req.getDispatcherType());
        chain.doFilter(rawRequest, rawResponse);
    }
}
```

Đây là **đoạn minh họa của một filter**, cần chạy trong ứng dụng Servlet với các import Jakarta Servlet và cơ chế đăng ký `@WebFilter` thích hợp. Trong Spring Boot, một lựa chọn khác là `FilterRegistrationBean` với `setDispatcherTypes(...)`, như ví dụ runnable ở phần 5. Đăng ký `asyncSupported=true` là điều kiện hỗ trợ vòng đời async, **không** thay thế `DispatcherType.ASYNC` trong mapping.

Nếu chỉ cần kiểm tra yêu cầu HTTP đầu tiên, đăng ký `REQUEST` có thể đủ. Nếu cần trace từng lần forward, include, lỗi và async dispatch, phải chọn dispatcher types tương ứng. Mở rộng mapping sẽ khiến logic filter chạy thêm, vì vậy các tác vụ có tác dụng phụ (ghi audit, trừ quota, thay đổi dữ liệu, tính phí) phải có quy tắc rõ ràng để tránh thực hiện lặp trên cùng một request.

**Lưu ý:** Một filter thường có thể được gọi nhiều lần theo các dispatch khác nhau; số lần gọi không tương đương số HTTP requests từ client. Nên log cả loại dispatch, URI, định danh request và thread khi chẩn đoán.

## 4. Liên hệ Spring Security trên Servlet stack

Spring Security xử lý HTTP thông qua filter chain, thường được đưa vào container qua `DelegatingFilterProxy` và `FilterChainProxy`. Ở đây có **hai lớp cấu hình khác nhau**:

- **Đăng ký filter trong Servlet container:** quyết định proxy được gọi ở các lượt `REQUEST`, `ERROR`, `ASYNC`, `FORWARD`, `INCLUDE` nào. Với Spring Boot, có thể điều chỉnh qua `spring.security.filter.dispatcher-types` nếu thực sự cần, sau khi xác minh cấu hình theo phiên bản đang dùng.
- **Quy tắc phân quyền bên trong Spring Security:** `authorizeHttpRequests` có thể xét dispatcher type bằng `dispatcherTypeMatchers(...)`, nhưng chỉ khi request **đã đi vào** Spring Security filter chain.

Ví dụ cấu hình theo Java/Spring Security 6:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(
                    DispatcherType.FORWARD, DispatcherType.ERROR
            ).permitAll()
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .build();
}
```

Đoạn trên chỉ là **cách viết rule mẫu**, không phải một chính sách mặc định cho mọi dự án. Cho phép `FORWARD`/`ERROR` thường giúp một trang lỗi hoặc view nội bộ hoạt động sau khi request gốc đã qua bảo vệ; nhưng phải kiểm tra tính hợp lệ của đường vào ban đầu, quyền truy cập dữ liệu ở đích, và nguy cơ forward từ endpoint công khai sang tài nguyên nhạy cảm. Không nên cho phép toàn bộ `ASYNC` hoặc `INCLUDE` chỉ để dập lỗi 403 mà chưa phân tích luồng và policy.

Một số điểm dễ bỏ sót:

- `OncePerRequestFilter` có cơ chế đánh dấu tránh chạy trùng trong một đoạn xử lý, nhưng **không nên hiểu** là tuyệt đối một lần cho toàn bộ cuộc đời HTTP request. Mặc định lớp này thường bỏ qua async/error dispatch qua `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`; subclass có thể điều chỉnh, và nested error dispatch có đường xử lý riêng.
- `SecurityContextHolder` mặc định gắn với thread. Tự tạo executor/thread trong xử lý async không có nghĩa security context tự động được truyền sang; dùng cơ chế tích hợp của Spring Security hoặc các wrapper `DelegatingSecurityContext...` phù hợp với thiết kế ứng dụng.
- Đảm bảo bộ lọc logging/tracing và security dùng dispatcher mapping phù hợp mục đích, tránh tưởng rằng thiếu log `FORWARD` nghĩa là server không hề forward.
- Với Spring Boot và Spring Security, chính sách truy cập và dispatcher type của **filter container** là hai chỗ độc lập cần được kiểm tra; thứ tự `requestMatchers` và `dispatcherTypeMatchers` trong authorization cũng ảnh hưởng kết quả.

## 5. Ví dụ Java 17 + Spring Boot 3: tự quan sát cả năm loại

Ví dụ nhỏ sau dùng **Jakarta Servlet** trực tiếp trong Spring Boot Servlet stack, đồng thời khai báo một `SecurityFilterChain`. Mục đích là quan sát dispatcher types bằng một trace filter được đăng ký rõ ràng cho cả năm loại. Không cần servlet container ngoài: Spring Boot dùng container nhúng. Các URI `/demo/**` chỉ được mở công khai cho bài thực hành.

Tạo cấu trúc:

```text
dispatch-demo/
├── pom.xml
└── src/main/java/example/dispatch/DispatchDemoApplication.java
```

**`pom.xml`** (Java 17, Spring Boot 3.3.5):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dispatch-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

**`src/main/java/example/dispatch/DispatchDemoApplication.java`**:

```java
package example.dispatch;

import jakarta.servlet.AsyncContext;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.ErrorPage;
import org.springframework.boot.web.server.ErrorPageRegistrar;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import java.io.IOException;
import java.util.EnumSet;

@SpringBootApplication
public class DispatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                        DispatcherType.FORWARD, DispatcherType.ERROR)
                    .permitAll()
                .requestMatchers("/demo/**").permitAll()
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    FilterRegistrationBean<Filter> traceFilter() {
        Filter trace = (rawRequest, rawResponse, chain) -> {
            HttpServletRequest req = (HttpServletRequest) rawRequest;
            Object includeUri =
                    req.getAttribute(RequestDispatcher.INCLUDE_REQUEST_URI);
            String target = req.getDispatcherType() == DispatcherType.INCLUDE
                    && includeUri != null
                    ? includeUri.toString()
                    : req.getRequestURI();
            System.out.println("TRACE " + req.getDispatcherType()
                    + " " + target);
            chain.doFilter(rawRequest, rawResponse);
        };

        FilterRegistrationBean<Filter> registration =
                new FilterRegistrationBean<>(trace);
        registration.addUrlPatterns("/*");
        registration.setDispatcherTypes(
                EnumSet.allOf(DispatcherType.class));
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ServletRegistrationBean<EntryServlet> entryServlet() {
        ServletRegistrationBean<EntryServlet> registration =
                new ServletRegistrationBean<>(new EntryServlet(),
                        "/demo/request", "/demo/forward",
                        "/demo/include", "/demo/error", "/demo/async");
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ServletRegistrationBean<FragmentServlet> fragmentServlet() {
        return new ServletRegistrationBean<>(
                new FragmentServlet(), "/demo/fragment");
    }

    @Bean
    ServletRegistrationBean<ErrorServlet> errorServlet() {
        return new ServletRegistrationBean<>(
                new ErrorServlet(), "/demo/error-page");
    }

    @Bean
    ServletRegistrationBean<ResultServlet> resultServlet() {
        ServletRegistrationBean<ResultServlet> registration =
                new ServletRegistrationBean<>(
                        new ResultServlet(), "/demo/resumed");
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ErrorPageRegistrar demoErrorPage() {
        return registry -> registry.addErrorPages(
                new ErrorPage(HttpStatus.INTERNAL_SERVER_ERROR,
                              "/demo/error-page"));
    }

    public static class EntryServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws ServletException, IOException {
            response.setCharacterEncoding("UTF-8");
            response.setContentType("text/plain");
            switch (request.getServletPath()) {
                case "/demo/request" ->
                        response.getWriter().print("request");
                case "/demo/forward" ->
                        request.getRequestDispatcher("/demo/fragment")
                               .forward(request, response);
                case "/demo/include" -> {
                    response.getWriter().print("before|");
                    request.getRequestDispatcher("/demo/fragment")
                           .include(request, response);
                    response.getWriter().print("|after");
                }
                case "/demo/error" ->
                        response.sendError(500, "demo error");
                case "/demo/async" -> {
                    AsyncContext async = request.startAsync();
                    async.start(() ->
                            async.dispatch("/demo/resumed"));
                }
                default -> response.sendError(404);
            }
        }
    }

    public static class FragmentServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print("fragment");
        }
    }

    public static class ErrorServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            Object status = request.getAttribute(
                    RequestDispatcher.ERROR_STATUS_CODE);
            response.getWriter().print("error:" + status);
        }
    }

    public static class ResultServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print("resumed");
        }
    }
}
```

Chạy trong thư mục `dispatch-demo` (đã cài JDK 17+ và Maven):

```bash
mvn spring-boot:run
```

Ở terminal khác, gọi từng endpoint:

```bash
curl -i http://localhost:8080/demo/request
curl -i http://localhost:8080/demo/forward
curl -i http://localhost:8080/demo/include
curl -i http://localhost:8080/demo/error
curl -i http://localhost:8080/demo/async
```

**Kết quả HTTP cần quan sát** (bỏ qua các header mặc định vì có thể thay đổi theo môi trường):

| URI | HTTP status | Response body |
| --- | --- | --- |
| `/demo/request` | 200 | `request` |
| `/demo/forward` | 200 | `fragment` |
| `/demo/include` | 200 | <code>before&#124;fragment&#124;after</code> |
| `/demo/error` | 500 | `error:500` |
| `/demo/async` | 200 | `resumed` |

Với trace filter ở trên, mỗi lệnh độc lập thường tạo những dòng tương ứng sau (thứ tự chính xác giữa các thread và filter khác còn tùy môi trường):

```text
GET /demo/request:  TRACE REQUEST /demo/request
GET /demo/forward:  TRACE REQUEST /demo/forward
                    TRACE FORWARD /demo/fragment
GET /demo/include:  TRACE REQUEST /demo/include
                    TRACE INCLUDE /demo/fragment
GET /demo/error:    TRACE REQUEST /demo/error
                    TRACE ERROR /demo/error-page
GET /demo/async:    TRACE REQUEST /demo/async
                    TRACE ASYNC /demo/resumed
```

Đây là **trace mong đợi của filter minh họa**, không phải cam kết mọi filter khác hoặc mọi Spring Security filter sẽ chạy đúng số lần tương tự. `INCLUDE` được ghi bằng `INCLUDE_REQUEST_URI`; nếu in `getRequestURI()` trực tiếp trong lượt include, giá trị có thể vẫn là URI caller. Trong ứng dụng thực, cấu hình error page, bộ lọc khác và container có thể làm log có thêm hoạt động hoặc khác thứ tự.

**Vì sao ví dụ có ba servlet phụ?** `FragmentServlet` được tách khỏi `EntryServlet` để xử lý include/forward không phụ thuộc vào `getServletPath()`. Trong include, accessor đường dẫn có thể vẫn phản ánh caller; dùng chung một servlet rồi switch theo `getServletPath()` dễ chọn nhầm nhánh và include đệ quy. `ErrorServlet` đọc `ERROR_STATUS_CODE`, còn `ResultServlet` là đích riêng của async redispatch.

## 6. Lỗi thường gặp và cách kiểm tra

1. **Nhầm `forward` với redirect.** URL client giữ nguyên sau forward; nếu muốn client điều hướng sang URL khác, dùng redirect và tính đây là request HTTP mới.
2. **Cho rằng `getRequestURI()` luôn là tài nguyên hiện đang chạy.** Với `INCLUDE`, đọc `RequestDispatcher.INCLUDE_REQUEST_URI`; với `FORWARD`, xét thêm `FORWARD_REQUEST_URI` để phân biệt URI gốc.
3. **Cho rằng mọi HTTP 500 đều là `ERROR`.** Kiểm tra có error dispatch từ container hay framework đã trực tiếp ghi response lỗi trong `REQUEST`.
4. **Mặc định filter chạy lại trên forward/error/async.** Đọc dispatcher mapping của filter và kiểm tra log ở từng lượt; mặc định Servlet filter chỉ map `REQUEST` nếu không chỉ rõ.
5. **Nhầm `startAsync()` với `ASYNC` dispatch.** Chỉ khi `AsyncContext.dispatch(...)` tái điều phối mới có lượt `ASYNC`; cần hỗ trợ async ở servlet/filter liên quan.
6. **Dùng dữ liệu bảo mật dựa vào `ThreadLocal` trong thread async mới.** Kiểm tra ngữ cảnh security/tracing thực sự có được truyền theo cơ chế hỗ trợ hay chưa.
7. **Thực thi side effect nhiều lần vì filter bị gọi trên nhiều dispatch.** Tách bước xác thực, trace và các hành động chỉ nên xảy ra một lần theo mục tiêu nghiệp vụ; idempotency phải được thiết kế rõ.
8. **Cấp `permitAll()` cho toàn bộ dispatch nội bộ theo phản xạ.** Xác định nguồn request có được bảo vệ hay không và quyền thực tế ở endpoint đích; kiểm tra cấu hình filter đăng ký với container trước khi kết luận authorization rule có tác dụng.

Khi debug, hãy ghi tối thiểu `getDispatcherType()`, request URI, các thuộc tính `forward/include/error` liên quan, định danh request, thread, status/exception và dispatcher mapping của filter đang quan sát. Đối chiếu các lần dispatch theo **cùng một yêu cầu client** để biết filter có chạy lại không và vì sao.

## 7. Tự kiểm tra kiến thức

- Client gọi `/a`, `/a` forward tới `/b`: lượt chạy tại `/b` là gì? **`FORWARD`**; client không tự tạo request mới.
- `/a` include `/fragment` rồi ghi tiếp body: servlet `/fragment` có thể đổi HTTP status của response ngoài không? **Không**, nội dung được chèn và caller tiếp tục.
- Controller tự trả JSON với status 500 trong lượt xử lý ban đầu: `getDispatcherType()` chắc chắn là `ERROR` không? **Không**; thường vẫn `REQUEST` nếu không có error dispatch.
- `startAsync()` rồi một task chạy trên executor: có mặc nhiên có `ASYNC` dispatch không? **Không**; phải có `AsyncContext.dispatch(...)` nếu muốn một lượt dispatch ASYNC.
- Filter được map chỉ cho `REQUEST` có quan sát mọi lần forward và error không? **Không**; cần dispatcher mappings tương ứng.
- `dispatcherTypeMatchers(ERROR).permitAll()` có bảo đảm Spring Security filter được gọi ở mọi `ERROR` dispatch không? **Không**; còn phụ thuộc registration của security filter tại Servlet container.

**Ghi nhớ:** `DispatcherType` mô tả **lượt điều phối hiện tại**; `Filter` được chạy dựa trên **cả mapping lẫn dispatcher type**; Spring Security phải được xét ở **cả registration trong container và authorization trong filter chain**.