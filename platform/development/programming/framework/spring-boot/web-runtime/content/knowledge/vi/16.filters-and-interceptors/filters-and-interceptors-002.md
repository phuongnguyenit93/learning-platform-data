# FilterRegistrationBean, thứ tự bộ lọc và phạm vi URL trong Spring Boot

## 1. Bối cảnh và mục tiêu

Trong ứng dụng Spring Boot **Servlet/Spring MVC**, HTTP request đi qua một chuỗi `jakarta.servlet.Filter` do Servlet container quản lý trước khi đến `DispatcherServlet`. Filter có thể kiểm tra hoặc thay đổi request/response, ngắt request sớm, bổ sung header hoặc ghi số liệu. Việc triển khai đúng `doFilter` **chưa đủ**: nếu đăng ký sai, filter có thể chạy trên mọi URL, có thứ tự bất lợi so với encoding/security, hoặc bị gọi nhiều lần.

`FilterRegistrationBean` giải quyết trực tiếp ba câu hỏi:

1. **Phạm vi:** filter có chạy tại `/api/ping`, `/public/ping`, `/error`, hay các servlet khác?
2. **Thứ tự:** khi hai filter cùng match một request, filter nào chạy trước và filter nào chạy sau?
3. **Loại dispatch và vòng đời:** filter xử lý `REQUEST`, `ASYNC`, `ERROR` nào và có bị tự động đăng ký trùng không?

Sau bài này, bạn có thể dùng `addUrlPatterns("/api/*")`, `setOrder(...)`, `setDispatcherTypes(...)`, tránh nhầm `/api/*` của Servlet với `/api/**` của Spring MVC, phân biệt Filter với Interceptor/Spring Security và kiểm chứng trên embedded HTTP server thật.

Ví dụ dùng **Spring Boot 3.5.16 + Java 17+ + Spring MVC** với embedded Tomcat. Các ví dụ là một ứng dụng Maven hoàn chỉnh và bộ test `@SpringBootTest(RANDOM_PORT)`. Spring Boot 3.5.16 là bản OSS cuối của nhánh 3.5; production nên dùng dòng được hỗ trợ và được vá bảo mật.

## 2. Servlet Filter nằm ở đâu?

~~~text
HTTP client
    |
    v
Servlet container (Tomcat, Jetty, Undertow)
    |
    +-- Filter A: before
    |      |
    |      +-- Filter B: before
    |      |      |
    |      |      +-- DispatcherServlet
    |      |              |
    |      |              +-- HandlerMapping
    |      |              +-- MVC HandlerInterceptor.preHandle
    |      |              +-- Controller
    |      |              +-- MVC afterCompletion
    |      |
    |      +-- Filter B: after
    |
    +-- Filter A: after
    |
    v
HTTP response
~~~

Servlet `Filter` khai báo `doFilter`. Ví dụ:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Logic trước những filter/Servlet nằm phía sau.
    chain.doFilter(request, response);
    // Logic sau khi downstream hoàn thành bình thường.
}
~~~

Đoạn trên là **method minh họa**, cần interface, imports và class để biên dịch. Các điểm thiết yếu:

- `chain.doFilter` chuyển request đến filter kế tiếp hoặc servlet; nếu không gọi thì logic phía sau bị chặn. Filter có thể chủ động trả lỗi, nhưng phải xử lý status/body hợp lý.
- Với hai filter lồng nhau, logic trước `chain.doFilter` chạy theo thứ tự A→B; logic sau `chain.doFilter` chạy B→A nếu downstream hoàn tất bình thường.
- Nếu downstream ném exception, đoạn code phía sau `chain.doFilter` không tự chạy; dùng `try/finally` khi cần cleanup.
- Filter có thể được gọi với request không match controller, static resources hay error dispatch, **nếu** URL mapping và dispatcher type phù hợp.
- Filter có thể wrap `ServletRequest`/`ServletResponse`, nhưng phải đảm bảo encoding, input stream và async lifecycle.

### Filter khác HandlerInterceptor và WebFilter

| Thành phần | Tầng chạy | Matching và thứ tự | Sử dụng điển hình |
|---|---|---|---|
| Servlet `Filter` | Servlet container, trước `DispatcherServlet` | Servlet URL/servlet-name/dispatcher mapping; registration order | Header, request wrapper, cross-cutting xử lý trước MVC |
| MVC `HandlerInterceptor` | Spring MVC handler chain | `InterceptorRegistration` path patterns/order | Logic gắn với MVC handler |
| Spring Security servlet filter | `FilterChainProxy` bên trong Servlet filter chain | Security `RequestMatcher`, `HttpSecurity` filter order | Authentication, authorization, CSRF |
| WebFlux `WebFilter` | Reactive WebFlux | `WebFilterChain`, `Ordered` | Reactive filters; **không** dùng FilterRegistrationBean |

Không dùng Servlet `FilterRegistrationBean` để đăng ký `org.springframework.web.server.WebFilter` của WebFlux; đây là hai stack khác nhau. `HandlerInterceptor` cũng không thay thế toàn bộ tác dụng của Servlet filter lên servlet khác hoặc raw body.

## 3. Ba cách đăng ký filter và khi nào chọn FilterRegistrationBean

### 3.1. Chỉ tạo Spring bean Filter

~~~java
@Bean
Filter myFilter() {
    return new MyFilter();
}
~~~

Đây là **method minh họa** cần class `MyFilter` và cấu hình Spring. Trong embedded Servlet application, Spring Boot tự phát hiện `Filter` beans và đăng ký chúng vào container. Nếu không giới hạn mapping, filter thường được map `/*`: mọi request path trong context.

Lợi điểm: đơn giản. Nhược điểm: dễ áp dụng quá rộng khi filter chỉ nên xử lý `/api/*`. Tên bean `apiFilter` **không tự tạo** URL scope.

### 3.2. FilterRegistrationBean

Trong Boot 3.5:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
~~~

`FilterRegistrationBean<T extends Filter>` là `ServletContextInitializer` và `Ordered`. Nó đóng vai trò adapter giữa Filter instance và Servlet registration.

| API | Mục đích |
|---|---|
| `new FilterRegistrationBean<>(filter)` | Chọn Filter instance |
| `setFilter(filter)` | Thiết lập instance sau khi dùng constructor rỗng |
| `setName("name")` | Tên Servlet filter registration |
| `addUrlPatterns("/api/*")` | Giới hạn URL theo Servlet specification |
| `setUrlPatterns(collection)` | Đặt URL pattern collection |
| `addServletNames("name")` | Liên kết với servlet theo tên |
| `setOrder(10)` | Thứ tự registration |
| `setDispatcherTypes(REQUEST)` | Loại Servlet dispatch được xử lý |
| `setAsyncSupported(true)` | Filter registration hỗ trợ async |
| `setMatchAfter(true)` | Vị trí mapping so với declared mappings |
| `setEnabled(false)` | Tắt Servlet registration cho filter |
| `addInitParameter("k","v")` | Cung cấp init parameter |

Nếu không có URL/servlet mapping, filter mặc định được gắn `/*` theo javadoc. Do đó `addUrlPatterns` rất quan trọng khi không muốn tác động toàn ứng dụng.

Ví dụ một method cấu hình:

~~~java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration() {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(new MyFilter());
    bean.setName("myApiFilter");
    bean.addUrlPatterns("/api/*");
    bean.setOrder(50);
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
~~~

Đây là code **minh họa**, cần imports `jakarta.servlet.DispatcherType`, `FilterRegistrationBean`, Spring `@Bean` và class `MyFilter`. Bài demo ở mục 8 cung cấp các file đầy đủ.

### 3.3. Các annotation đăng ký khác

- `@Component` trên Filter biến nó thành Spring bean; Boot có thể tự đăng ký theo quy ước.
- `@WebFilter` thuộc Servlet API; trong embedded app, `@ServletComponentScan` có thể được dùng để scan Servlet components.
- `@FilterRegistration` của Spring Boot 3.5 là cách annotation-based thay `FilterRegistrationBean`, hỗ trợ thuộc tính như order, URL patterns và dispatcher types.
- Không phối hợp nhiều con đường đăng ký cùng một Filter mà chưa kiểm tra chúng có tạo **hai registrations** hay không.

Dùng `FilterRegistrationBean` khi cần review URL scope/order rõ ràng bằng code.

## 4. URL patterns của Servlet không phải Spring MVC patterns

`addUrlPatterns(...)` tuân theo **Servlet specification**, không hiểu Ant-style `**` hay PathPatternParser của Spring MVC.

| Servlet URL pattern | Diễn giải | Ví dụ |
|---|---|---|
| `/*` | Mọi path trong web app context | `/api/a`, `/public/a` |
| `/api/*` | Path prefix `/api` và các nhánh sau | `/api/ping`, `/api/v1/ping` |
| `/health` | Exact path | `/health` |
| `*.json` | Extension mapping | Path đích có phần mở rộng .json |
| `/` | Default Servlet mapping, semantics riêng | Không coi là tương đương tổng quát với `/*` |
| `/api/**` | **Không phải prefix pattern chuẩn của Servlet** | Không dùng cho `addUrlPatterns` |

Dùng:

~~~java
registration.addUrlPatterns("/api/*");
~~~

không dùng:

~~~java
// Sai kỳ vọng: Servlet không có ngữ nghĩa "**" của Spring MVC.
registration.addUrlPatterns("/api/**");
~~~

Container có thể từ chối pattern không hợp lệ hoặc không diễn giải như mong đợi. Không xây quy tắc security trên pattern không chuẩn.

### Nhiều patterns, exact path, không có exclude

Có thể thêm nhiều prefix:

~~~java
registration.addUrlPatterns("/api/*", "/internal/*");
~~~

Hoặc exact paths:

~~~java
registration.addUrlPatterns("/auth/login", "/auth/logout");
~~~

Không có toán tử phủ định `!/api/public/*` để loại trừ nhánh con. Với một Filter muốn bỏ qua một path đã match ở container, có thể dùng `OncePerRequestFilter.shouldNotFilter`; tuy vậy nếu đó là ranh giới bảo mật hãy dùng Spring Security matchers, không tự tin vào `startsWith` thủ công.

### Context path

Nếu:

~~~properties
server.servlet.context-path=/shop
~~~

HTTP URL bên ngoài có thể là `/shop/api/ping`, nhưng Servlet filter mapping trong application context vẫn viết `/api/*`. `request.getRequestURI()` thường bao gồm context path, còn filter mapping hoạt động tương đối với application context. Đừng vô tình thêm `/shop` vào `addUrlPatterns`.

### HTTP method và query string

Pattern xét path, không xét `?page=2` hay GET/POST. GET `/api/ping` và POST `/api/orders` đều có thể đi qua `/api/*` nếu dispatcher type khớp. Nếu muốn filter chỉ làm tác vụ trên POST, kiểm tra `HttpServletRequest.getMethod()` trong filter, hoặc chọn mechanism khác đúng tầng.

### Theo tên servlet

`FilterRegistrationBean` còn hỗ trợ servlet name mapping. Điều này hữu ích khi app có nhiều servlet; filter chỉ áp dụng cho servlet được chỉ định. Không đánh đồng Servlet name với tên MVC controller hoặc tên bean service.

## 5. Thứ tự filters: setOrder nhỏ chạy trước

Filter A và B đều match cùng một request:

~~~java
firstRegistration.setOrder(10);
secondRegistration.setOrder(20);
~~~

Khi Boot sắp các registrations do Boot quản lý, order nhỏ có ưu tiên cao hơn. Luồng điển hình:

~~~text
Request -> FIRST before -> SECOND before -> Controller
Response <- FIRST after  <- SECOND after  <- Controller
~~~

Để diễn đạt chính xác chiều về: controller trả về cho SECOND trước, SECOND trả về cho FIRST; mã sau `chain.doFilter` của SECOND chạy trước mã sau `chain.doFilter` của FIRST.

**Những lưu ý quan trọng:**

1. Khi thứ tự quan trọng, dùng số order khác nhau, không dựa vào tên bean hoặc thứ tự khai báo methods.
2. `@Order` trên **class Filter** hoặc `Ordered` trên filter bean có thể tham gia ordering khi Boot tự đăng ký. Nhưng tài liệu Boot nêu rõ **`@Order` đặt trên `@Bean` method tạo Filter không dùng để cấu hình Servlet filter order**.
3. Khi không kiểm soát class Filter, dùng `FilterRegistrationBean.setOrder(...)`.
4. `setMatchAfter(true)` ảnh hưởng việc đưa mapping sau những declared filter mappings của `ServletContext`; nó **không thay cho** số `setOrder`.
5. Một ứng dụng có Servlet filter đến từ Boot, third-party, WAR container, Security proxy và `web.xml`; không lấy hai con số order làm bảo đảm toàn bộ thứ tự global. Quan sát startup và kiểm thử runtime.

### Filter wrapper và character encoding

Spring Boot cảnh báo không cho filter đọc request body chạy quá sớm ở `Ordered.HIGHEST_PRECEDENCE` vì có thể trước khi thiết lập character encoding. Khi wrap request, hướng dẫn Boot đề cập:

~~~java
OrderedFilter.REQUEST_WRAPPER_FILTER_MAX_ORDER
~~~

Wrapper filter cần order nhỏ hơn hoặc bằng giá trị hằng này khi phù hợp. Không đặt mọi custom filter ở `HIGHEST_PRECEDENCE` để “chắc chắn chạy đầu tiên”: điều đó có thể làm lỗi encoding, CORS, security hoặc xử lý body.

Trong demo, FIRST/SECOND không wrap hoặc đọc body; order 10/20 chỉ để minh họa thứ tự **giữa chúng**.

## 6. DispatcherType và async lifecycle

Servlet có các dispatcher types:

| DispatcherType | Ý nghĩa |
|---|---|
| `REQUEST` | Request ban đầu từ HTTP client |
| `FORWARD` | Forward bằng RequestDispatcher |
| `INCLUDE` | Include nội dung servlet khác |
| `ASYNC` | Async redispatch, có thể ở thread khác |
| `ERROR` | Servlet error dispatch tới error page/servlet |

Chọn REQUEST:

~~~java
registration.setDispatcherTypes(DispatcherType.REQUEST);
~~~

Muốn thêm ERROR:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ERROR);
~~~

Điều quan trọng: **dispatcher type và URL mapping phải đều match**. Khi error dispatch đến `/error`, một filter chỉ có URL `/api/*` có thể **không chạy** ở ERROR dispatch, dù có bật `DispatcherType.ERROR`. Phải kiểm tra dispatch target/Servlet container thực tế.

Theo tài liệu Boot 3.5, registration không chỉ định dispatcher type thông thường dùng mặc định `REQUEST`, phù hợp Servlet specification.

### setAsyncSupported không tự thêm DispatcherType.ASYNC

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(DispatcherType.REQUEST);
~~~

`asyncSupported(true)` chỉ nói registration hỗ trợ async. Nó không tự yêu cầu thực thi ở `ASYNC` dispatch. Muốn tham gia redispatch, đăng ký `ASYNC` và thiết kế filter có thread safety, MDC/tracing cleanup, không ghi response hai lần.

### OncePerRequestFilter

`org.springframework.web.filter.OncePerRequestFilter` hỗ trợ kiểm soát thực thi qua request attribute. Nhưng không được hiểu tên class theo nghĩa toàn bộ HTTP request **chỉ có một lần duy nhất** trong mọi trường hợp:

- REQUEST/ASYNC/ERROR có thể xảy ra ở các thời điểm hoặc threads khác nhau.
- `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` điều chỉnh hành vi trong các loại dispatch.
- `setDispatcherTypes` tại registration vẫn là điều kiện của Servlet container.
- `shouldNotFilter(HttpServletRequest)` cho phép bỏ qua logic với request đã được đăng ký phạm vi rộng.
- Nếu filter bị đưa vào hai chain độc lập, `OncePerRequestFilter` không thay thế việc sửa duplicate registration.

Đoạn minh họa subclass:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;
}
~~~

Hai method trên **chưa phải class độc lập**; khi muốn chạy ở ASYNC/ERROR, cần chỉnh lại cả registration và implementation, rồi test lifecycle.

## 7. Double registration, SecurityFilterChain và khởi tạo sớm

### 7.1. Đừng đăng ký filter một cách vô thức ở nhiều nơi

Ví dụ `@Component` Filter có thể được Boot auto-register vào Servlet container. Nếu bạn cũng thêm cùng filter vào Spring Security `HttpSecurity`, hoặc dùng `@WebFilter` và Servlet component scanning, filter có thể thực thi nhiều lần hoặc ở phạm vi sai.

Một `FilterRegistrationBean` gắn với đúng filter bean có thể được Boot dùng để điều khiển auto-registration tương ứng. Tuy nhiên nó không tự xóa mọi registration từ bên thứ ba hoặc Servlet container. Khi debug phải liệt kê toàn bộ nguồn.

Bài demo tạo `new TraceFilter(...)` **trực tiếp trong registration bean**, không đánh dấu TraceFilter là `@Component` hay `@WebFilter`, tránh đường đăng ký riêng.

### 7.2. Hai tầng ordering với Spring Security

~~~text
Servlet FilterChain
    |
    +-- Custom Servlet FilterRegistrationBean
    |
    +-- DelegatingFilterProxy ("springSecurityFilterChain")
           |
           +-- FilterChainProxy
                   |
                   +-- SecurityFilterChain được chọn theo RequestMatcher
                            |
                            +-- authentication filters
                            +-- authorization filters
                            +-- CSRF và các filters liên quan
    |
    v
DispatcherServlet
~~~

`FilterRegistrationBean.setOrder` tác động đến registration ở **Servlet container**. `HttpSecurity.addFilterBefore`, `addFilterAfter`, `addFilterAt` tác động đến **bên trong SecurityFilterChain**. Một số thứ tự của Spring Security do framework xác định; đừng suy luận order 10 của Servlet Filter là “sau AuthenticationFilter” nếu chưa kiểm tra chain thực tế.

Nếu custom filter cần authenticated principal, thường nên đặt đúng vị trí **trong SecurityFilterChain**. Nếu custom Servlet Filter chạy trước security, `SecurityContext` có thể chưa có principal. Không dùng FilterRegistrationBean URL mapping thay authorization policy.

### 7.3. Tắt Servlet registration khi filter chỉ dành cho Security chain

Với một filter `@Bean` chỉ được dùng bên trong Spring Security, có thể tắt đăng ký container như sau:

~~~java
@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {
    FilterRegistrationBean<MySecurityFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
~~~

Đây là đoạn minh họa, chưa gồm `MySecurityFilter` và cấu hình Spring Security. `setEnabled(false)` không xóa bean filter; nó chỉ vô hiệu registration tương ứng ở Servlet container. Filter vẫn có thể được `HttpSecurity` quản lý trong security chain.

### 7.4. Filter initialization rất sớm

Servlet filters được đăng ký sớm khi container khởi động. Inject trực tiếp DataSource/JPA repository/service với constructor có side effects có thể gây khởi tạo quá sớm và startup failure. Boot khuyên cân nhắc lazy lookup hoặc `DelegatingFilterProxyRegistrationBean` cho những filter cần cộng tác với nhiều Spring beans. Không chạy database migration hoặc gọi network ngay trong filter constructor.

## 8. Dự án thực hành đầy đủ: hai filter, thứ tự và URL scope

Project sử dụng một `TraceFilter` có thể tạo nhiều instances. Hai registration được đặt:

- FIRST: `setOrder(10)`, URL `/api/*`, dispatcher `REQUEST`.
- SECOND: `setOrder(20)`, cùng URL `/api/*`, dispatcher `REQUEST`.

Controller có ba routes:

| Route | Kỳ vọng body | Kỳ vọng header X-Filter-Trace |
|---|---|---|
| `/api/ping` | `api:FIRST>SECOND` | `FIRST>SECOND` |
| `/api/v1/ping` | `nested:FIRST>SECOND` | `FIRST>SECOND` |
| `/public/ping` | `public:none` | Header vắng mặt |

Header demo là chứng cứ thứ tự thực thi, **không dùng** nó làm security token hoặc request ID đáng tin trong production.

### 8.1. Cấu trúc file

~~~text
servlet-filter-demo/
  pom.xml
  src/main/java/com/example/filterdemo/
    FilterDemoApplication.java
    TraceFilter.java
    FilterConfiguration.java
    PingController.java
  src/test/java/com/example/filterdemo/
    FilterRegistrationIntegrationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Spring Boot parent quản lý Tomcat/Jakarta Servlet/JUnit dependency versions tương thích. Không thêm Spring Security vào demo vì cần quan sát Servlet registration thuần; tích hợp thực tế phải kiểm tra thêm Security chain.

### 8.3. Main class

File `src/main/java/com/example/filterdemo/FilterDemoApplication.java`:

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### 8.4. TraceFilter.java

File `src/main/java/com/example/filterdemo/TraceFilter.java`:

~~~java
package com.example.filterdemo;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class TraceFilter implements Filter {
    private final String marker;

    public TraceFilter(String marker) {
        this.marker = marker;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;

        Object previous = httpRequest.getAttribute("filter.trace");
        String trace = previous == null
                ? marker
                : previous + ">" + marker;

        httpRequest.setAttribute("filter.trace", trace);
        httpResponse.setHeader("X-Filter-Trace", trace);

        chain.doFilter(request, response);
    }
}
~~~

Khi FIRST chạy, request attribute `filter.trace` trở thành `FIRST`; khi SECOND chạy, nó thành `FIRST>SECOND`. Field `marker` immutable, dữ liệu request được lưu trong **request attribute**, không trong mutable field của singleton Filter. Vì demo chạy trong Servlet HTTP app, cast sang HTTP request/response hợp lệ.

### 8.5. FilterConfiguration.java

File `src/main/java/com/example/filterdemo/FilterConfiguration.java`:

~~~java
package com.example.filterdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FilterConfiguration {

    @Bean
    FilterRegistrationBean<TraceFilter> firstTraceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter("FIRST"));

        registration.setName("firstTraceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setOrder(10);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        return registration;
    }

    @Bean
    FilterRegistrationBean<TraceFilter> secondTraceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter("SECOND"));

        registration.setName("secondTraceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setOrder(20);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        return registration;
    }
}
~~~

Hai `TraceFilter` instances có registration name khác nhau. Chúng không phải `@Component` và không có Spring bean `TraceFilter` riêng. Khi request match `/api/*` và `REQUEST`, FIRST có order 10 chạy trước SECOND order 20. Nếu bỏ `addUrlPatterns` thì phạm vi có thể mở thành `/*`.

### 8.6. PingController.java

File `src/main/java/com/example/filterdemo/PingController.java`:

~~~java
package com.example.filterdemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public String api(HttpServletRequest request) {
        return "api:" + trace(request);
    }

    @GetMapping("/api/v1/ping")
    public String nested(HttpServletRequest request) {
        return "nested:" + trace(request);
    }

    @GetMapping("/public/ping")
    public String publicPing(HttpServletRequest request) {
        return "public:" + trace(request);
    }

    private static String trace(HttpServletRequest request) {
        Object value = request.getAttribute("filter.trace");
        return value == null ? "none" : value.toString();
    }
}
~~~

Cả ba endpoints đều là Spring MVC routes. Controller `/public/ping` không nhận attribute vì Servlet container **không** gọi filters được map chỉ cho `/api/*`.

### 8.7. Chạy và kiểm tra bằng curl

Yêu cầu Java 17+ và Maven. Tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Khi ứng dụng đã lắng nghe port 8080, thử:

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/v1/ping
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng status **200** cho cả ba; body và header như bảng đầu mục 8. `curl -i` in cả headers và body. Phần body String không kèm newline tự động; không coi hình thức xuống dòng của terminal là behavior của controller.

### 8.8. Test trên embedded server thật — Java 17 compatible

**Vì sao không chỉ MockMvc?** `MockMvc` kiểm thử Spring MVC pipeline nhưng không phải container thật. Việc auto-discovery filters trong test có thể khác URL registration/dispatcher semantics ở embedded Tomcat. Dùng `@SpringBootTest(RANDOM_PORT)` với HTTP request thật để xác minh filter order/scope.

File `src/test/java/com/example/filterdemo/FilterRegistrationIntegrationTest.java`:

~~~java
package com.example.filterdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterRegistrationIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void apiFiltersRunInOrder() throws Exception {
        HttpResponse<String> result = get("/api/ping");

        assertEquals(200, result.statusCode());
        assertEquals("api:FIRST>SECOND", result.body());
        assertEquals("FIRST>SECOND",
                result.headers()
                        .firstValue("X-Filter-Trace").orElse(""));
    }

    @Test
    void servletPrefixPatternMatchesNestedApiPath() throws Exception {
        HttpResponse<String> result = get("/api/v1/ping");

        assertEquals(200, result.statusCode());
        assertEquals("nested:FIRST>SECOND", result.body());
        assertEquals("FIRST>SECOND",
                result.headers()
                        .firstValue("X-Filter-Trace").orElse(""));
    }

    @Test
    void publicUrlIsOutsideRegisteredFilterScope() throws Exception {
        HttpResponse<String> result = get("/public/ping");

        assertEquals(200, result.statusCode());
        assertEquals("public:none", result.body());
        assertTrue(result.headers()
                .firstValue("X-Filter-Trace").isEmpty());
    }

    @Test
    void embeddedServerAllocatedPort() {
        assertTrue(port > 0);
    }
}
~~~

Code này **tương thích Java 17**: `HttpClient.newHttpClient()` không bị đặt trong try-with-resources; ở JDK 17, `HttpClient` chưa có hợp đồng `AutoCloseable`. Mọi test HTTP gửi đến port được `@LocalServerPort` cung cấp, không giả định cổng cố định 8080.

Chạy:

~~~bash
mvn test
~~~

Khi có Maven Wrapper, dùng `./mvnw test` (Windows: `mvnw.cmd test`). Các test đã nêu kết quả kỳ vọng từ mã ví dụ; thực tế vẫn cần chạy trên build environment của dự án để xác nhận dependencies và network.

## 9. Một số nhu cầu mở rộng

### 9.1. Chỉ một số endpoints

~~~java
registration.addUrlPatterns("/auth/login", "/auth/logout");
~~~

Đây là exact Servlet paths. Nó không tự giới hạn HTTP method, không định nghĩa syntax `{id}` như Spring MVC và không thay authentication.

### 9.2. Bỏ qua một đường con trong /api

Có thể map rộng `/api/*`, rồi trong subclass `OncePerRequestFilter`:

~~~java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    String path = request.getServletPath();
    return path.equals("/api/public")
            || path.startsWith("/api/public/");
}
~~~

Đây là trích đoạn, không phải một phần của demo `TraceFilter`. Bỏ qua bằng một `startsWith` thủ công chỉ phù hợp khi hiểu path normalization và servlet mapping. Nếu chức năng liên quan authorization, dùng Spring Security matcher.

### 9.3. Lọc riêng HTTP method

Bên trong một `doFilter` đã có `HttpServletRequest httpRequest`:

~~~java
if (!"POST".equals(httpRequest.getMethod())) {
    chain.doFilter(request, response);
    return;
}
~~~

Container vẫn gọi filter trên GET match URL; đoạn code chỉ chủ động bỏ qua nghiệp vụ cho GET.

### 9.4. FILTER cho ERROR hoặc ASYNC

Khi cần chạy trên `ERROR`, thêm dispatcher type nhưng phải kiểm tra error target path. Với `ASYNC`, phải xem cả `asyncSupported`, `DispatcherType.ASYNC`, `OncePerRequestFilter.shouldNotFilterAsyncDispatch` và việc cleanup/thread-local contexts. Đừng cộng đôi metrics vì một request có thể trải qua nhiều dispatches.

## 10. Debug trên hệ thống thật

Trong test/local `application.properties`, có thể bật:

~~~properties
logging.level.web=debug
~~~

Spring Boot sẽ ghi thông tin các Servlet filters được đăng ký (order, URL patterns) ở startup. Khi có lỗi, kiểm tra theo thứ tự:

1. Filter được đăng ký bằng đường nào? Bean, FilterRegistrationBean, @WebFilter, @FilterRegistration hay Spring Security?
2. Có bản đăng ký `/*` không mong muốn không?
3. `/api/*` có được dùng thay `/api/**` không?
4. Đã xét context path, servlet mapping, reverse proxy rewrites chưa?
5. Thứ tự order có trùng hoặc va chạm với encoding/security filters không?
6. Có async/error redispatch hay không? Dispatcher types gì?
7. Filter có bị Spring Security chain và container đều gọi không?
8. Request body đã bị đọc trước khi MVC/Jackson xử lý không?
9. Filter có ghi log secret hay thông tin cá nhân không?
10. Integration tests trên server thật đã bao phủ URL trong và ngoài scope chưa?

Debug logging có thể làm lộ credential/body/query; chỉ bật phù hợp môi trường và không ghi raw Authorization header, cookies hay passwords.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Filter chạy cả public URLs | Filter bean mặc định auto-mapped `/*` | Chỉ định `/api/*` với registration phù hợp |
| Filter không match nested API | Dùng exact path hoặc `/api/**` | Dùng Servlet prefix `/api/*` |
| Filter chạy hai lần | Servlet registration + Security chain hoặc Servlet component scan | Loại đường đăng ký thừa, `setEnabled(false)` khi chỉ dùng Security chain |
| `@Order` không thay đổi filter order | Đặt annotation ở method `@Bean` | Dùng `FilterRegistrationBean.setOrder` |
| Order không ổn định | Các filter trùng order hoặc registration khác can thiệp | Dùng order khác nhau và integration test |
| ERROR dispatch không chạy filter | Chưa chọn `ERROR` hoặc URL error không match | Kiểm tra cả dispatcher type và path |
| Async redispatch không chạy | Chỉ có `REQUEST` hoặc OncePerRequestFilter bỏ qua | Cấu hình cả dispatcher và filter implementation |
| Security principal chưa xuất hiện | Filter chạy trước authentication | Đưa filter vào Security chain đúng vị trí |
| HTTP 500 sau request wrapper | Body bị đọc sớm hoặc encoding sai | Dùng wrapper chuẩn, kiểm tra stream/order |
| Filter gây startup chậm | Inject dependency nặng quá sớm | Lazy lookup/DelegatingFilterProxyRegistrationBean |
| MockMvc pass nhưng runtime sai | Test bypass Servlet container registration semantics | Test `RANDOM_PORT` qua HTTP |
| Rò token trong log | Filter ghi toàn request/header | Allowlist logging và redact |

## 12. Checklist review code

- **Scope:** mọi URL pattern là cú pháp Servlet hợp lệ, và có test cho path lồng nhau, path không match?
- **Order:** nếu thứ tự quan trọng, filter registrations có order rõ, không trùng?
- **Lifecycle:** có vô tình `@Component` + registration hoặc thêm vào Security chain hai lần?
- **Dispatch:** đã chỉ định REQUEST/ERROR/ASYNC theo nhu cầu thực và có test?
- **Security:** filter chạy trước/sau authentication đúng ý? Không dùng URL mapping như authorization rule duy nhất?
- **Encoding:** filter đọc/wrap body có chạy sau khi xác định encoding phù hợp?
- **Thread safety:** filter không giữ thông tin request trong mutable singleton field?
- **Error handling:** khi chặn request, status/body/header có đúng và chain không bị gọi ngoài ý muốn?
- **Logging:** không phơi token, password, request body hoặc PII?
- **Testing:** có kiểm thử server thật, không chỉ MockMvc?
- **Version:** với Spring Boot 4.x, đã đối chiếu starter, module và API javadoc của chính version đó?

**Kết luận:** `FilterRegistrationBean` không chỉ đơn giản “bật một filter”. Nó xác định **bộ lọc nào**, **chạy trên phạm vi URL/servlet nào**, **theo thứ tự nào** và **trong dispatch nào**. Phân biệt chính xác Servlet URL pattern `/api/*` với Spring MVC `/api/**`, tách Servlet order khỏi Spring Security order, tránh đăng ký trùng và viết integration tests trên container thật là các nguyên tắc quan trọng nhất.

## Tài liệu tham khảo

- Spring Boot 3.5.16 — Servlet Web Applications, registering filters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5.16 — Embedded Web Servers, registering filters and dispatcher types: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5.16 API — FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
- Spring Boot 3.5.16 API — AbstractFilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/AbstractFilterRegistrationBean.html
- Spring Boot 3.5.16 API — RegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/RegistrationBean.html
- Spring Boot 3.5.16 API — FilterRegistration annotation: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistration.html
- Spring Framework 6.2 — OncePerRequestFilter: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — Spring MVC interceptors: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html
- Spring Security — Servlet Architecture, DelegatingFilterProxy and FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot 3.5.16 release and OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
