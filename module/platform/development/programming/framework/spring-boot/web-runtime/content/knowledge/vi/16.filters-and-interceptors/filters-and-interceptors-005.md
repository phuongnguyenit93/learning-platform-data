# Ordered, @Order và kiểm tra thứ tự thực tế của Filter và Interceptor trong Spring Boot

## Mục tiêu học tập

Khi một ứng dụng Spring Boot có nhiều Filter, HandlerInterceptor, WebFilter hoặc SecurityFilterChain, **thứ tự thực thi** ảnh hưởng trực tiếp tới logging, correlation ID, CORS, authentication, authorization, request wrapping, exception handling và dữ liệu phản hồi. Không đủ để thêm @Order rồi giả định mọi thành phần sẽ chạy theo thứ tự số trên một danh sách duy nhất: Spring MVC, Servlet container, Spring Security và Spring WebFlux có **các chuỗi xử lý khác nhau**.

Bài học giúp bạn:

- Hiểu ý nghĩa của **Ordered**, **@Order**, **PriorityOrdered**, **HIGHEST_PRECEDENCE** và **LOWEST_PRECEDENCE**.
- Phân biệt thứ tự bean/list injection với thứ tự servlet filter registration, MVC interceptor registration và Spring Security filter chain.
- Cấu hình Servlet Filter bằng @Order trên class, Ordered hoặc FilterRegistrationBean.setOrder.
- Dùng InterceptorRegistration.order(int) để sắp xếp HandlerInterceptor.
- Giải thích tại sao request đi vào A → B nhưng phần xử lý sau handler thường chạy B → A.
- Phân biệt @Order trên SecurityFilterChain với thứ tự các filter **bên trong** Spring Security.
- Nhận biết cách @Order/Ordered áp dụng cho WebFilter của Spring WebFlux.
- Kiểm tra **thứ tự thực tế** bằng startup logs, request-scoped traces và integration test với embedded Servlet container.
- Tránh double-registration, sai dispatcher type, xử lý quá sớm và giả định không đúng về async/error dispatch.

Ví dụ runnable chính dùng **Java 17+ và Spring Boot 3.5.x trên Servlet/Spring MVC**. Các phần về Spring WebFlux và Spring Security giải thích riêng để tránh trộn cơ chế.

## 1. Trước tiên: thứ tự số nghĩa là gì?

Spring Framework có interface **org.springframework.core.Ordered**:

~~~java
public interface Ordered {
    int getOrder();
}
~~~

Một implementation chỉ cần trả số nguyên:

~~~java
public final class HighPriorityTask implements Ordered {

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

Annotation **org.springframework.core.annotation.Order** mô tả thứ tự cố định ở class, method hoặc nơi Spring hỗ trợ:

~~~java
@Order(10)
public final class AnotherTask {
}
~~~

Nguyên tắc trong các nơi sử dụng order comparator của Spring:

**Giá trị nhỏ hơn thường được ưu tiên chạy trước.**

| Giá trị | Mức ưu tiên tương đối |
|---|---|
| Ordered.HIGHEST_PRECEDENCE | Integer.MIN_VALUE; ưu tiên rất cao |
| -100 | Trước 0 và 10 |
| 0 | Trước 10 và 100 |
| 10 | Sau 0, trước 20 |
| 20 | Sau 10 |
| Ordered.LOWEST_PRECEDENCE | Integer.MAX_VALUE; ưu tiên thấp |

Không có quy tắc “số 100 được ưu tiên hơn số 10 vì lớn hơn”. Trong cùng một hệ thống được sắp xếp theo ascending order, A=10 và B=20 có nghĩa **A vào trước B**.

### HIGHEST_PRECEDENCE không nên dùng tùy tiện

Đặt filter đọc request body tại Ordered.HIGHEST_PRECEDENCE có thể khiến nó chạy trước phần cấu hình character encoding hoặc những filter nền tảng khác của Boot. Tài liệu Boot khuyến cáo tránh trường hợp đó. Nếu filter wrap request, còn có những ràng buộc order liên quan request wrapper cần xem đúng phiên bản Boot.

Không nên dùng Integer.MIN_VALUE chỉ để “đảm bảo filter mình đầu tiên”. Chọn mức order đủ rõ, kiểm tra các filter cùng ứng dụng và không phá cơ chế có sẵn của framework.

## 2. @Order, Ordered và PriorityOrdered khác nhau

### @Order: metadata cố định

~~~java
@Component
@Order(25)
public class SomeComponent {
    // ...
}
~~~

Spring có thể đọc annotation này khi nó **cần sắp xếp một tập component**. Tuy nhiên một annotation không có nghĩa mọi framework/Servlet container đều tự quan sát metadata đó.

### Ordered: thứ tự do instance quyết định

~~~java
@Component
public class DynamicOrderComponent implements Ordered {

    @Override
    public int getOrder() {
        return 25;
    }
}
~~~

Ordered phù hợp khi thứ tự do constructor/configuration của instance quyết định hoặc framework có hợp đồng trực tiếp làm việc với Ordered. Trong một số bộ comparator của Spring, Ordered trên instance được xét trước metadata annotation của class.

### PriorityOrdered

**PriorityOrdered** mở rộng Ordered. Trong những sorting contract có hỗ trợ nó, các object PriorityOrdered được xử lý như nhóm ưu tiên đặc biệt **trước nhóm chỉ triển khai Ordered**, và các giá trị getOrder() được so sánh trong nhóm tương ứng.

Không phải cứ gắn PriorityOrdered vào bất kỳ Filter nào thì servlet container sẽ tự hiểu: điều quan trọng là **thành phần đăng ký và sort** có dùng contract này hay không.

### Khi có cùng order

Nếu hai interceptor hoặc filter cùng dùng order=10, đừng viết nghiệp vụ phụ thuộc vào việc class A luôn chạy trước B dựa trên component scanning, tên file, alphabet, thứ tự tạo bean hay thứ tự startup. Kết quả có thể bị ảnh hưởng bởi cách đăng ký/collection/traversal và thay đổi khi nâng phiên bản.

Nếu quan hệ A trước B quan trọng, **dùng order khác nhau, có tài liệu và integration test**. Dùng @DependsOn để ép init order không phải là giải pháp tương đương cho runtime filter chain.

## 3. @Order không điều khiển mọi loại thứ tự

Một số khái niệm có tên gần giống nhau:

| Loại thứ tự | Ai quyết định | Cấu hình phù hợp |
|---|---|---|
| Sắp xếp bean trong List<T> khi injection | Spring bean factory / dependency ordering | @Order, Ordered, đôi khi @Priority |
| Khởi tạo singleton bean | Dependency graph, @DependsOn và lifecycle | Không dựa vào @Order |
| Servlet Filter do Boot đăng ký | Servlet filter registration của Boot/container | @Order trên **Filter class**, Ordered, FilterRegistrationBean.setOrder |
| Spring MVC HandlerInterceptor | InterceptorRegistry/HandlerMapping | addInterceptor(...).order(int) |
| Spring Security nhiều SecurityFilterChain | Thứ tự lựa chọn chain + RequestMatcher | @Order trên SecurityFilterChain bean |
| Các Security Filter trong một chain | HttpSecurity/FilterChainProxy | addFilterBefore, addFilterAfter, addFilterAt và built-in order |
| WebFlux WebFilter | Chuỗi WebFilter của WebFlux | @Order trên WebFilter / Ordered |
| @ControllerAdvice precedence | Spring advice resolver | @Order/Ordered tùy contract |
| ResponseBodyAdvice, exception resolvers và các component khác | Từng extension point cụ thể | Xem contract của từng loại |

**Một con số order chỉ có ý nghĩa trong phạm vi chuỗi sắp xếp của nó.** Ví dụ servlet filter order=10 và MVC interceptor order=5 **không** chứng minh interceptor chạy trước filter. Servlet filters nằm ở tầng ngoài DispatcherServlet; HandlerInterceptor ở bên trong Spring MVC.

## 4. Servlet Filter: thứ tự do container registration quyết định

Servlet Filter thuộc **jakarta.servlet.Filter** (Spring Boot 3.x/4.x). Mỗi Filter có doFilter(request, response, chain) và có thể thực thi trước lẫn sau lời gọi chain.doFilter(...).

Mô hình với hai filter A, B:

~~~text
Client
  |
  v
Filter A - before
  |
  v
Filter B - before
  |
  v
DispatcherServlet / Handler
  |
  v
Filter B - after
  |
  v
Filter A - after
  |
  v
Client
~~~

Code minh họa:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    log("A before");
    try {
        chain.doFilter(request, response);
    } finally {
        log("A after");
    }
}
~~~

Đoạn trên là method bên trong một class implements Filter; log là hàm minh họa. try/finally giúp chạy logic cleanup sau chain ngay cả khi chain ném lỗi. Nó **không đảm bảo** response chưa committed hoặc client đã đọc toàn bộ dữ liệu.

### Ba lựa chọn phổ biến để đặt thứ tự Servlet Filter trong Boot

**Cách A: @Order trên chính Filter class**

~~~java
@Component
@Order(10)
public class AuditFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

Đây là class minh họa cần imports jakarta.servlet.* và Spring annotations. Khi Boot tự đăng ký Filter bean theo cơ chế hỗ trợ, metadata @Order **trên class Filter** có thể được Boot dùng để xác định registration order.

**Cách B: implements Ordered**

~~~java
@Component
public class AnotherAuditFilter implements Filter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

Code trên cần imports tương ứng. Thứ tự 10 và 20 có nghĩa AuditFilter được đăng ký để chạy trước AnotherAuditFilter ở cùng một servlet filter chain, giả sử URL patterns và dispatcher types của chúng đều match.

**Cách C: FilterRegistrationBean.setOrder(int)**

Đây là cách rõ ràng nếu muốn kiểm soát order, URL pattern, dispatcher types và enabled state:

~~~java
@Bean
FilterRegistrationBean<Filter> auditRegistration() {
    FilterRegistrationBean<Filter> bean =
        new FilterRegistrationBean<>(new AuditFilter());

    bean.setName("audit");
    bean.addUrlPatterns("/api/*");
    bean.setOrder(10);
    return bean;
}
~~~

Đây là method minh họa. Nếu AuditFilter đã có @Component và được Boot tự đăng ký, đừng tạo thêm registration vô tình dẫn đến hai đường đăng ký; hãy chọn **một** cơ chế đăng ký có chủ đích. Ví dụ runnable ở phần sau tạo Filter trực tiếp trong FilterRegistrationBean và **không** thêm @Component trên Filter.

### Bẫy quan trọng: @Order trên @Bean method tạo Filter

Theo tài liệu Spring Boot, đoạn sau **không phải cách tin cậy để điều khiển Servlet Filter registration order**:

~~~java
@Bean
@Order(10)
Filter auditFilter() {
    return new AuditFilter();
}
~~~

@Order trên @Bean method có thể ảnh hưởng một số cơ chế injection/sort của Spring, nhưng Spring Boot nêu rõ: **không đặt order của Servlet Filter bằng cách chỉ gắn @Order trên bean method**. Nếu không thể sửa Filter class để implements Ordered hoặc gắn @Order trên class, dùng FilterRegistrationBean#setOrder(int), hoặc @FilterRegistration có thuộc tính order trong những version hỗ trợ.

Đây là một trong những lý do quan trọng nhất phải **quan sát thứ tự thực tế**, không chỉ đọc annotation.

## 5. FilterRegistrationBean: order và phạm vi URL/dispatcher type

FilterRegistrationBean của Boot cho phép:

- setOrder(int): order registration.
- addUrlPatterns(...): đường dẫn Servlet filter áp dụng.
- setDispatcherTypes(...): áp dụng với REQUEST, ERROR, ASYNC, FORWARD, INCLUDE theo thiết kế.
- setEnabled(boolean): bật/tắt registration.
- setName(...): tên filter registration.
- asyncSupported và init parameters tùy nhu cầu.

Ví dụ:

~~~java
registration.addUrlPatterns("/api/*");
registration.setDispatcherTypes(DispatcherType.REQUEST);
registration.setOrder(20);
~~~

**URL pattern là quy tắc Servlet**, không phải @GetMapping pattern của Spring MVC. Nếu filter chỉ map /api/* thì request /actuator/health hoặc /login không tự đi qua nó.

Nếu không chỉ rõ dispatcher types, tài liệu Boot cho biết REQUEST là mặc định trong cách đăng ký thông thường. Nhưng một số framework hoặc thư viện có registration riêng cho ERROR/ASYNC, nên không nên suy ra chỉ từ tên class Filter.

### REQUEST, ERROR và ASYNC

Một HTTP request có thể đi qua nhiều dispatcher type:

| DispatcherType | Tình huống |
|---|---|
| REQUEST | HTTP request ban đầu |
| ERROR | Servlet container dispatch nội bộ đến error page, ví dụ /error |
| ASYNC | Tiếp tục xử lý qua Servlet asynchronous dispatch |
| FORWARD | Request được forward nội bộ |
| INCLUDE | Servlet include một resource khác |

Filter được map cho REQUEST và ERROR có thể được gọi trong cả hai lượt, nếu URL mapping và dispatcher type match. **Đếm số lần gọi filter không tương đương đếm số HTTP request từ client.**

Đối với OncePerRequestFilter, tên class không có nghĩa mọi async/error redispatch luôn bị loại bỏ giống nhau. Các hook shouldNotFilterAsyncDispatch/shouldNotFilterErrorDispatch và cách đăng ký dispatcher types vẫn rất quan trọng.

### Filter wrap request và character encoding

Filter wrapper hoặc body-reading filter cần quan tâm thứ tự so với encoding, form-content và security filters. Boot cảnh báo không đặt request-body-reading filter ở HIGHEST_PRECEDENCE; việc đọc toàn body trong filter còn có thể làm controller không đọc được nữa.

Trường hợp cần đọc body rồi cho downstream đọc tiếp phải dùng HttpServletRequestWrapper/caching hoặc cấu trúc phù hợp, có giới hạn bộ nhớ và không log secret. Order không sửa được lỗi tiêu thụ InputStream.

## 6. HandlerInterceptor: một chuỗi khác bên trong Spring MVC

HandlerInterceptor thuộc **org.springframework.web.servlet.HandlerInterceptor**. Nó can thiệp vào vòng đời handler sau khi Servlet filters đã cho request đến DispatcherServlet.

Ba callback phổ biến:

~~~java
boolean preHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler
);

void postHandle(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    ModelAndView modelAndView
);

void afterCompletion(
    HttpServletRequest request,
    HttpServletResponse response,
    Object handler,
    Exception ex
);
~~~

Trong Java code thật, các phương thức có chữ ký/throws phù hợp với Spring Framework version.

- **preHandle**: trước handler. Trả true để đi tiếp; false để dừng handler chain sau khi interceptor đã xử lý response theo hợp đồng.
- **postHandle**: sau HandlerAdapter/handler và trước view rendering đối với luồng thông thường.
- **afterCompletion**: callback cleanup khi request handling hoàn tất, cho các interceptor đã preHandle thành công; có khác biệt với async handling.

### Cách sắp thứ tự được khuyến nghị

Trong Spring Boot MVC:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new FirstInterceptor())
            .addPathPatterns("/api/**")
            .order(10);

        registry.addInterceptor(new SecondInterceptor())
            .addPathPatterns("/api/**")
            .order(20);
    }
}
~~~

Đây là snippet minh họa cần định nghĩa FirstInterceptor/SecondInterceptor và imports, không phải file chạy độc lập. **InterceptorRegistration.order(int)** là điểm điều khiển rõ ràng; thứ tự mặc định là 0 nếu không đặt.

Đừng gắn @Order trên một HandlerInterceptor class rồi kỳ vọng mọi HandlerMapping tự động đưa bean đó vào registry và sắp xếp như Servlet Filter. Phải xác định **cách interceptor được đăng ký**. Khi bạn gọi registry.addInterceptor(...), hãy đặt .order(...) tại registration.

### Thứ tự callback

Với interceptor A=10 và B=20, request đồng bộ bình thường:

~~~text
A.preHandle
B.preHandle
Controller
B.postHandle
A.postHandle
B.afterCompletion
A.afterCompletion
~~~

Callbacks ở chiều trước đi A → B, còn cleanup và post-processing đi theo thứ tự ngược B → A. **Đây là mô hình vòng đời của chuỗi interceptor**, không đồng nghĩa postHandle luôn có quyền sửa response.

Đặc biệt với @ResponseBody/ResponseEntity, Spring Framework lưu ý response có thể được ghi và committed trong HandlerAdapter, **trước postHandle**. Nếu cần thay nội dung/body response, cân nhắc ResponseBodyAdvice; nếu cần thiết lập header chắc chắn trước commit, đặt đúng giai đoạn phù hợp, không đợi afterCompletion.

### preHandle trả false

Giả sử A.preHandle trả true, B.preHandle trả false:

- Controller không chạy.
- Những interceptor chưa thực thi preHandle sẽ không tiếp tục.
- Các cleanup callback được áp dụng theo hợp đồng cho những interceptor đã preHandle thành công.
- Không nên giả định tất cả postHandle/afterCompletion đều chạy như nhánh thành công.

Khi xử lý async, AsyncHandlerInterceptor có hook afterConcurrentHandlingStarted; lifecycle có thể có redispatch. Không dùng một sơ đồ đồng bộ đơn giản để suy ra mọi dòng log của streaming/async endpoint.

## 7. Ghép Servlet filters và MVC interceptors: không so sánh order số giữa hai tầng

Giả sử hai Servlet Filter có order 10, 20 và hai MVC HandlerInterceptor cũng có order 10, 20.

~~~text
HTTP request
     |
     v
Servlet Filter A (order=10): before
     |
     v
Servlet Filter B (order=20): before
     |
     v
DispatcherServlet
     |
     v
MVC Interceptor A (order=10): preHandle
     |
     v
MVC Interceptor B (order=20): preHandle
     |
     v
Controller
     |
     v
MVC Interceptor B: postHandle
MVC Interceptor A: postHandle
MVC Interceptor B: afterCompletion
MVC Interceptor A: afterCompletion
     |
     v
Servlet Filter B: after
Servlet Filter A: after
     |
     v
HTTP client
~~~

Servlet container lựa chọn Filter chain trước DispatcherServlet; Spring MVC chọn HandlerInterceptor chain cho handler bên trong. Vì vậy MVC interceptor order=0 vẫn **không** đứng ngoài Servlet Filter order=1000.

Nếu cần xử lý trước Spring Security và trước routing MVC, cần xem vị trí **Servlet Filter** và **Security Filter Chain**. Nếu logic phụ thuộc HandlerMethod hoặc route annotations, HandlerInterceptor có thể phù hợp nhưng không nên xem là thành phần bảo mật chính.

## 8. Ví dụ runnable: kiểm chứng thứ tự bằng embedded Tomcat

Phần này sử dụng **Spring Boot 3.5.x, Java 17+, spring-boot-starter-web** (MVC Servlet). Không thêm Spring Security hoặc WebFlux vào dự án demo để không làm thứ tự khó kiểm soát. Các URL của demo là **/trace** và **/trace/result/{id}**.

Ý tưởng:

1. Hai Servlet Filter được đăng ký bằng FilterRegistrationBean, order=10 và 20; chỉ áp dụng cho đúng URL /trace.
2. Hai HandlerInterceptor được đăng ký trong WebMvcConfigurer, order=10 và 20; cũng chỉ áp dụng cho /trace.
3. Request-scoped list ghi sự kiện theo đúng thứ tự thực tế.
4. Controller trả một snapshot của các sự kiện đã xảy ra **trước khi tạo response body**.
5. Filter ngoài cùng lưu bản ghi đầy đủ **sau khi tất cả thành phần đã unwind** vào một demo store để truy vấn lại.
6. Test HTTP khởi động server thật và xác nhận cả inbound lẫn reverse callbacks.

Dữ liệu store nằm trong RAM và không có TTL, chỉ dùng để học/test. Không giữ kiểu store này vô hạn trong production; cần expiration, giới hạn số bản ghi và không lưu dữ liệu nhạy cảm.

### 8.1. Tạo project

Từ Spring Initializr chọn Java 17+, Spring Boot 3.5.x và dependencies **Spring Web**, **Spring Boot Test**. Với Maven dự án đã có Spring Boot parent/BOM:

~~~xml
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
~~~

Mỗi public class dưới đây nằm trong một file riêng theo đường dẫn package com.example.ordering.

### 8.2. OrderingApplication.java

File: src/main/java/com/example/ordering/OrderingApplication.java

~~~java
package com.example.ordering;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderingApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderingApplication.class, args);
    }
}
~~~

### 8.3. TraceState.java: lưu sự kiện theo HTTP request

File: src/main/java/com/example/ordering/TraceState.java

~~~java
package com.example.ordering;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceState {

    public static final String ID =
        TraceState.class.getName() + ".id";

    private static final String EVENTS =
        TraceState.class.getName() + ".events";

    private TraceState() {
    }

    @SuppressWarnings("unchecked")
    private static List<String> events(HttpServletRequest request) {
        Object current = request.getAttribute(EVENTS);

        if (current != null) {
            return (List<String>) current;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(EVENTS, created);
        return created;
    }

    public static void add(HttpServletRequest request, String event) {
        events(request).add(event);
    }

    public static List<String> snapshot(HttpServletRequest request) {
        return List.copyOf(events(request));
    }

    public static String id(HttpServletRequest request) {
        return (String) request.getAttribute(ID);
    }
}
~~~

Request attributes giữ state cho **một request đồng bộ**. Demo không sử dụng Servlet async hoặc các thread cùng thay đổi list; với async code cần collection an toàn và lifecycle phù hợp.

### 8.4. TraceStore.java: lưu kết quả sau khi filter hoàn tất

File: src/main/java/com/example/ordering/TraceStore.java

~~~java
package com.example.ordering;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class TraceStore {

    private final ConcurrentHashMap<String, List<String>> traces =
        new ConcurrentHashMap<>();

    public void save(String id, List<String> events) {
        traces.put(id, events);
    }

    public List<String> find(String id) {
        return traces.get(id);
    }
}
~~~

ConcurrentHashMap chỉ đảm bảo thao tác map thread-safe, không biến một hệ thống trace lưu mãi trong RAM thành production-ready. Khi dùng thực tế, cần giới hạn retention và kiểm soát quyền xem trace.

### 8.5. TraceConfiguration.java: hai Filter và hai Interceptor

File: src/main/java/com/example/ordering/TraceConfiguration.java

~~~java
package com.example.ordering;

import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class TraceConfiguration implements WebMvcConfigurer {

    @Bean
    FilterRegistrationBean<Filter> outerFilter(TraceStore store) {
        Filter filter = (request, response, chain) -> {
            HttpServletRequest http =
                (HttpServletRequest) request;

            String id = UUID.randomUUID().toString();
            http.setAttribute(TraceState.ID, id);
            TraceState.add(http, "filter-A.before");

            try {
                chain.doFilter(request, response);
            } finally {
                TraceState.add(http, "filter-A.after");
                store.save(id, TraceState.snapshot(http));
            }
        };

        return registration(filter, "trace-outer", 10);
    }

    @Bean
    FilterRegistrationBean<Filter> innerFilter() {
        Filter filter = (request, response, chain) -> {
            HttpServletRequest http =
                (HttpServletRequest) request;

            TraceState.add(http, "filter-B.before");

            try {
                chain.doFilter(request, response);
            } finally {
                TraceState.add(http, "filter-B.after");
            }
        };

        return registration(filter, "trace-inner", 20);
    }

    private static FilterRegistrationBean<Filter> registration(
            Filter filter, String name, int order) {

        FilterRegistrationBean<Filter> bean =
            new FilterRegistrationBean<>(filter);

        bean.setName(name);
        bean.addUrlPatterns("/trace");
        bean.setDispatcherTypes(DispatcherType.REQUEST);
        bean.setOrder(order);
        return bean;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RecordingInterceptor("A"))
            .addPathPatterns("/trace")
            .order(10);

        registry.addInterceptor(new RecordingInterceptor("B"))
            .addPathPatterns("/trace")
            .order(20);
    }

    private static final class RecordingInterceptor
            implements HandlerInterceptor {

        private final String label;

        RecordingInterceptor(String label) {
            this.label = label;
        }

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {

            TraceState.add(request,
                "interceptor-" + label + ".pre");
            return true;
        }

        @Override
        public void postHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                ModelAndView modelAndView) {

            TraceState.add(request,
                "interceptor-" + label + ".post");
        }

        @Override
        public void afterCompletion(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                Exception exception) {

            TraceState.add(request,
                "interceptor-" + label + ".after");
        }
    }
}
~~~

**Tại sao code này đáng tin hơn chỉ gắn @Order trên method?**

- Filter được tạo trong **FilterRegistrationBean**; chính bean registration đặt order=10/20 và URL mapping.
- Không gắn @Component cho Filter, tránh vô tình có thêm một đường automatic filter registration.
- Hai interceptor có order riêng tại **InterceptorRegistry**, không phụ thuộc @Order trên class.
- Cả filters và interceptors chỉ match /trace; endpoint truy vấn trace sẽ không tạo thêm các sự kiện demo.
- Dispatcher type chỉ REQUEST, nên demo không tính thêm lỗi ERROR dispatch.
- Vì handler dùng HTTP đồng bộ, request-scoped list không bị nhiều async threads ghi cùng lúc.

### 8.6. TraceController.java

File: src/main/java/com/example/ordering/TraceController.java

~~~java
package com.example.ordering;

import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TraceController {

    private final TraceStore store;

    public TraceController(TraceStore store) {
        this.store = store;
    }

    public record TracePayload(
        String id,
        List<String> beforeResponse
    ) {
    }

    @GetMapping("/trace")
    public TracePayload trace(HttpServletRequest request) {
        TraceState.add(request, "controller");

        return new TracePayload(
            TraceState.id(request),
            TraceState.snapshot(request)
        );
    }

    @GetMapping("/trace/result/{id}")
    public List<String> completed(@PathVariable String id) {
        List<String> events = store.find(id);

        if (events == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Trace not yet available"
            );
        }

        return events;
    }
}
~~~

**Vì sao có hai endpoint?**

GET /trace trả snapshot tạo trong controller. Tại thời điểm đó, postHandle, afterCompletion và hai filter finally **chưa chạy xong**, nên body JSON chỉ có các sự kiện inbound.

GET /trace/result/{id} được gọi sau request đầu tiên, đọc snapshot đã được outer Filter lưu ở finally. Vì URL này không nằm trong registration mapping /trace, nó không kích hoạt thêm sự kiện trace.

### 8.7. Chạy bằng Maven

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Giả sử server lắng nghe port mặc định 8080 và không có context path:

~~~bash
curl -sS http://localhost:8080/trace
~~~

Body dự kiến có id UUID khác nhau theo request, và mảng beforeResponse **chính xác theo thứ tự**:

~~~json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "beforeResponse": [
    "filter-A.before",
    "filter-B.before",
    "interceptor-A.pre",
    "interceptor-B.pre",
    "controller"
  ]
}
~~~

id chỉ là minh họa; thực tế UUID được sinh ngẫu nhiên nên khác.

Dùng id thực nhận được để gọi:

~~~bash
curl -sS http://localhost:8080/trace/result/123e4567-e89b-12d3-a456-426614174000
~~~

Kết quả sau khi request /trace hoàn tất:

~~~json
[
  "filter-A.before",
  "filter-B.before",
  "interceptor-A.pre",
  "interceptor-B.pre",
  "controller",
  "interceptor-B.post",
  "interceptor-A.post",
  "interceptor-B.after",
  "interceptor-A.after",
  "filter-B.after",
  "filter-A.after"
]
~~~

Danh sách này minh họa chính xác khác biệt giữa **trước handler** và **unwind sau handler** ở demo đồng bộ. Không coi thứ tự 11 event này là một khẳng định chung cho exception, async processing hoặc mọi hệ thống security/proxy.

### 8.8. Test integration trên embedded Servlet container

MockMvc có thể kiểm tra HandlerInterceptor chain, nhưng nếu mục tiêu là xác minh **Servlet filter registration thực tế**, hãy dùng HTTP integration test với server thật.

File: src/test/java/com/example/ordering/TraceIntegrationTest.java

~~~java
package com.example.ordering;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class TraceIntegrationTest {

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private TraceStore store;

    @Test
    void verifiesRealFilterAndInterceptorOrder() {
        TraceController.TracePayload response = client.getForObject(
            "/trace", TraceController.TracePayload.class
        );

        assertThat(response).isNotNull();
        assertThat(response.id()).isNotBlank();
        assertThat(response.beforeResponse()).containsExactly(
            "filter-A.before",
            "filter-B.before",
            "interceptor-A.pre",
            "interceptor-B.pre",
            "controller"
        );

        await().atMost(Duration.ofSeconds(3))
            .untilAsserted(() ->
                assertThat(store.find(response.id())).containsExactly(
                    "filter-A.before",
                    "filter-B.before",
                    "interceptor-A.pre",
                    "interceptor-B.pre",
                    "controller",
                    "interceptor-B.post",
                    "interceptor-A.post",
                    "interceptor-B.after",
                    "interceptor-A.after",
                    "filter-B.after",
                    "filter-A.after"
                )
            );
    }
}
~~~

TestRestTemplate + AssertJ + Awaitility được cung cấp trong cấu hình test phổ biến của spring-boot-starter-test 3.5.x. Test tạo một request HTTP thật tới embedded container, đọc snapshot và dùng Awaitility để chờ store cập nhật sau khi filter outer cùng các callbacks hoàn tất.

Đừng thay bài test này bằng cách chỉ assert rằng FilterRegistrationBean.getOrder() trả 10/20. Getter chỉ chứng minh **cấu hình dự kiến**, không chứng minh request thực sự đã đi qua filter theo thứ tự đó.

## 9. Đổi order và dự đoán kết quả

Nếu đổi:

~~~java
return registration(filter, "trace-inner", 5);
~~~

cho Filter B, thứ tự inbound sẽ đổi: Filter B được đăng ký trước Filter A. Nhưng **demo hiện tại giả định Filter A sinh trace ID và lưu snapshot ở cuối**. Khi B chạy trước A, Filter B có thể tạo request-scoped events trước khi có trace ID; phần này vẫn ghi được, nhưng snapshot lưu ở finally của A xảy ra **trước** khi B finally thêm sự kiện cuối của B. Vì vậy phải cập nhật logic recorder/test nếu đổi relative order của outer filter.

Đây là bài học sâu hơn: thứ tự filter thay đổi không chỉ thứ tự log mà còn thay đổi **ai bao quanh ai, ai sở hữu lifecycle, thời điểm cleanup và lúc response committed**.

Nếu muốn kiểm tra ảnh hưởng của order, hãy viết test mới cho thứ tự sau thay đổi; không chỉ sửa con số rồi tin kết quả sẽ đúng nguyên trạng.

## 10. Kiểm tra thứ tự Servlet Filter ở startup logs

Spring Boot khuyến nghị bật debug cho logging group web để xem Filter registrations. Trong môi trường phát triển:

~~~properties
logging.level.web=debug
~~~

Hoặc khi chạy:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--logging.level.web=debug
~~~

Các log khởi động có thể liệt kê Filter registrations, order và URL patterns. Tên logger và format dòng log phụ thuộc Boot version và server, nên đừng test bằng một chuỗi log cố định.

Khi có security starter, logging group web **không** cho biết đầy đủ thứ tự internal security filters trong FilterChainProxy. Cần log riêng của Spring Security khi điều tra security chain.

Đối chiếu ba loại bằng chứng:

1. **Registration metadata**: class, URL pattern, order, dispatcher types.
2. **Runtime trace**: filter/handler/interceptor nào thực sự nhận một request.
3. **HTTP outcome**: response status, headers, body và error/async redispatch.

Chỉ xem order field trong một bean không đủ để biết route có match hoặc filter có bị skip do dispatcher type không.

## 11. Spring Security: có hai cấp thứ tự

Nếu ứng dụng có spring-boot-starter-security, thường có một Servlet Filter đại diện cho security integration, sử dụng **DelegatingFilterProxy** và **FilterChainProxy**.

~~~text
Servlet container filter chain
      |
      +-- Application Filter A
      |
      +-- Spring Security DelegatingFilterProxy
      |       |
      |       v
      |    FilterChainProxy
      |       |
      |       +-- chọn SecurityFilterChain đầu tiên match request
      |                |
      |                +-- Security Filter 1
      |                +-- Security Filter 2
      |                +-- Security Filter 3
      |
      +-- Application Filter B
      |
      v
DispatcherServlet / MVC Interceptors
~~~

Có **hai quyết định khác nhau**:

1. Servlet container quyết định vị trí DelegatingFilterProxy trong chuỗi Servlet Filters.
2. Spring Security quyết định chọn **SecurityFilterChain nào** và **các security filters bên trong chain** chạy theo thứ tự nào.

### @Order trên SecurityFilterChain

Ví dụ minh họa về hai chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/api/**");
    // Cấu hình các rule dành riêng cho API.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserSecurity(HttpSecurity http)
        throws Exception {
    // Cấu hình cho request còn lại.
    return http.build();
}
~~~

Các đoạn trên là **khung minh họa**, không phải security configuration an toàn hay project chạy độc lập; cần dependency, imports và authorization rules cụ thể. Thứ tự @Order(1), @Order(2) điều khiển **thứ tự xét các SecurityFilterChain beans**. Spring Security chọn **chain đầu tiên có RequestMatcher phù hợp** và không tiếp tục dùng chain sau chỉ vì nó cũng match.

### Thứ tự filter bên trong một SecurityFilterChain

Spring Security xây dựng internal filter order theo các slot được định nghĩa. Để thêm custom filter đúng vị trí, dùng:

- http.addFilterBefore(customFilter, KnownFilter.class)
- http.addFilterAfter(customFilter, KnownFilter.class)
- http.addFilterAt(customFilter, KnownFilter.class) khi hiểu rõ semantics.

**@Order trên class custom Filter không bảo đảm nó đứng đúng vị trí bên trong FilterChainProxy.** Nếu một custom Filter đồng thời là @Component và được truyền vào HttpSecurity, nó còn có nguy cơ được Boot đăng ký như **Servlet Filter riêng**, gây thực thi ngoài security chain hoặc hai đường registration. Cần tránh bằng thiết kế đăng ký có chủ đích (có thể tắt servlet registration riêng nếu filter chỉ dùng trong security chain).

Không dùng HandlerInterceptor làm security boundary chính. Spring Security xử lý authentication/authorization tại filter chain, thích hợp hơn để bảo vệ request trước MVC routing.

## 12. Spring WebFlux: WebFilter là một hệ thứ tự khác

Spring WebFlux có interface **org.springframework.web.server.WebFilter**:

~~~java
Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
);
~~~

Khác Servlet Filter, WebFilter trả về một **Mono<Void>** mô tả quá trình xử lý reactive; không dùng jakarta.servlet.FilterChain.

Ví dụ:

~~~java
@Component
@Order(10)
public class FirstWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        System.out.println("webfilter-A.before");

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println("webfilter-A.finally:" + signal)
            );
    }
}
~~~

Đây là class minh họa cần imports Reactor/Spring và logger chuẩn khi dùng production. Khi framework subscribe, WebFilter order nhỏ có thể đi trước order lớn trong chuỗi WebFlux WebFilters. Các hook chạy sau chain phụ thuộc completion/error/cancellation; không nên giả định tất cả callback diễn ra trên cùng thread hoặc đồng bộ giống Servlet.

Nếu có hai WebFilters A=10 và B=20:

~~~text
WebFilter A -> WebFilter B -> WebHandler/DispatcherHandler
       \___________________________/
     các publisher kết thúc theo lifecycle
~~~

Một WebFilter có thể short-circuit bằng cách không gọi chain.filter(exchange). Khi đó các WebFilters và handler phía sau không chạy. Thêm một filter có order nhỏ hơn không đảm bảo nó quan sát response cuối cùng như mong đợi nếu chain bị hủy hoặc một filter khác chủ động thay exchange.

Spring WebFlux Security cũng có cơ chế **SecurityWebFilterChain**, với thứ tự chọn chain và vị trí filter nội bộ riêng; không lấy ví dụ Servlet HttpSecurity làm hướng dẫn cho ServerHttpSecurity.

**Không áp dụng Servlet FilterRegistrationBean hoặc MVC InterceptorRegistry cho ứng dụng WebFlux thuần trên Reactor Netty.** Web stack quyết định đúng interface và cơ chế ordering.

## 13. @Order trên WebMvcConfigurer và @ControllerAdvice có ý nghĩa khác

### WebMvcConfigurer

Spring có thể sắp xếp WebMvcConfigurer beans khi lấy các configurers để áp dụng cấu hình. Nhưng một @Order trên class WebMvcConfigurer không tự quy định thứ tự **từng HandlerInterceptor** được đăng ký trong các configurer khác nhau.

Nếu interceptor A cần đi trước B, hãy dùng **InterceptorRegistration.order(int)** ở mỗi registration thay vì phụ thuộc thứ tự configurer beans.

### @ControllerAdvice

Trong các extension points xử lý exception, @Order có thể quyết định advice nào được xét trước nếu có nhiều advice phù hợp. Đây là **thứ tự exception resolution**, không phải Servlet Filter order.

Một @ExceptionHandler trả response thành công còn có thể khiến request không đi qua /error; vì thế một filter chỉ map DispatcherType.ERROR có thể không nhìn thấy các lỗi đã được advice xử lý.

### @Order không phải @Primary

@Primary dùng để chọn một bean ưu tiên khi có nhiều ứng viên dependency cùng kiểu; @Order chủ yếu dùng để **sắp thứ tự collection hoặc pipeline** tại nơi hỗ trợ. Dùng @Order(0) không phải cách thay thế @Primary cho một injection point đơn lẻ.

### @Order không phải @DependsOn

@DependsOn ảnh hưởng init/dependency order; @Order dùng cho những sorter/pipeline có hợp đồng. Đặt @DependsOn("filterA") lên Filter B không chứng minh Filter A sẽ chạy trước B trong mọi request.

## 14. Các tình huống làm trace thực tế khác mong đợi

| Hiện tượng | Nguyên nhân hay gặp | Điều cần kiểm tra |
|---|---|---|
| Filter B vào trước A dù @Order trên @Bean method của A nhỏ hơn | @Bean method annotation không đặt Servlet filter registration order | @Order trên Filter class, Ordered hoặc FilterRegistrationBean.setOrder |
| Interceptor chạy sau filter dù interceptor order nhỏ hơn | Hai tầng ordering độc lập | Filter chain bên ngoài DispatcherServlet |
| MVC interceptor @Order(1) không chạy đầu | Chưa được đăng ký hoặc registry order khác | WebMvcConfigurer.addInterceptors(...).order(1) |
| Một custom security filter chạy hai lần | Vừa auto-registered Servlet Filter vừa thêm vào HttpSecurity | Một cơ chế registration hoặc disabled registration |
| Handler trả response nhưng filter không chạy | URL pattern/dispatcher type không match, filter bị disabled | FilterRegistrationBean pattern/types |
| Log filter xuất hiện hai lượt | REQUEST và ERROR hoặc ASYNC redispatch | DispatcherType và filter mapping |
| preHandle chạy nhưng postHandle không thấy | preHandle khác trả false, exception hoặc async path | HandlerExecutionChain lifecycle và exception |
| header thêm trong postHandle không xuất hiện | @ResponseBody/ResponseEntity đã committed | Đưa header sớm hơn hoặc dùng ResponseBodyAdvice |
| Thay đổi order mà trace full bị thiếu event cuối | Recorder nằm trong filter không còn ngoài cùng | Chuyển recorder sang lifecycle owner đúng hoặc cập nhật test |
| SecurityFilterChain order thay đổi nhưng auth rule vẫn sai | RequestMatcher khác hoặc internal filter order | Security chain selection + internal filters |
| WebFilter doFinally không chạy lúc tưởng | Reactive subscription/cancellation | Reactor signal, scheduler, chain completion |
| Các filter cùng order có thứ tự thay đổi sau upgrade | Dựa trên tie/registration thay vì thứ tự chủ đích | Đặt order duy nhất và thêm integration test |

## 15. Quy trình điều tra thứ tự chạy trong production

1. **Xác định web stack:** MVC Servlet hay WebFlux? Có cả starter MVC/WebFlux không? Boot thường chọn MVC khi cả hai xuất hiện theo cấu hình mặc định.
2. **Liệt kê từng lớp:** Servlet Filters, Spring Security FilterChainProxy, HandlerInterceptors, controller, advice, response writers.
3. **Kiểm tra source of registration:** @Component Filter, @FilterRegistration, FilterRegistrationBean, InterceptorRegistry, SecurityFilterChain hoặc WebFilter bean.
4. **Kiểm tra phạm vi:** URL pattern, servlet path/context path, dispatcher types, security RequestMatcher và WebFlux route.
5. **Kiểm tra order có hiệu lực:** @Order trên đúng class, Ordered.getOrder(), registrationBean.setOrder hoặc registry.order.
6. **Bật log đúng nơi:** logging.level.web=debug cho filter registration; Spring Security DEBUG/TRACE khi cần và được phép.
7. **Gắn correlation ID theo request:** log before/after, dispatcher type, thread, path, filter/interceptor name và elapsed time.
8. **Chạy test HTTP thực:** endpoint vừa có before/after callbacks, xác minh trace thực tế và response.
9. **Chạy nhánh lỗi:** 401, 403, 404, 500, validation errors và /error dispatch để xem thứ tự có đổi không.
10. **Kiểm tra async và streaming nếu có:** không lấy kết quả request đồng bộ làm bảo đảm cho mọi tín hiệu reactive/Servlet async.
11. **Không log dữ liệu nhạy cảm:** tránh password, Authorization, cookie, raw body và thông tin người dùng.
12. **Thêm regression test:** khi thêm security starter, thay container, nâng Spring Boot hoặc đổi filter/interceptor.

### Mẫu log nên có

~~~text
traceId=req-123 dispatcher=REQUEST stage=filter-A.before path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-B.before path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=interceptor-A.pre path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=controller path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=interceptor-A.after path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-B.after path=/api/orders
traceId=req-123 dispatcher=REQUEST stage=filter-A.after path=/api/orders
~~~

Đây là **mẫu định dạng**, không phải log thực nghiệm. Trong ứng dụng có cả interceptor B, các events tương ứng cũng cần xuất hiện. Ghi stage cùng traceId giúp nhóm theo request; không dựa vào thứ tự dòng log toàn cục khi nhiều request xử lý đồng thời.

## 16. Bài tập tự kiểm tra

**Câu 1.** Hai Servlet Filters có order 10 và 20. Trong REQUEST dispatch, cái nào đi vào trước?

**Câu 2.** Khi hai filters dùng try/finally và chain.doFilter, thứ tự finally là gì?

**Câu 3.** @Order(10) trên method @Bean tạo Filter có đủ đặt Servlet Filter registration order không?

**Câu 4.** Muốn đặt order cho HandlerInterceptor khi dùng WebMvcConfigurer thì API nào thích hợp?

**Câu 5.** MVC Interceptor A có order 1 và Servlet Filter B order 100. Có nghĩa A chạy trước B không?

**Câu 6.** PriorityOrdered khác Ordered thông thường ở đâu trong các comparator có hỗ trợ?

**Câu 7.** @Order có bảo đảm các singleton beans khởi tạo theo thứ tự đó không?

**Câu 8.** Filter chỉ map /api/* có chạy trên /actuator/health không, nếu không có registration khác?

**Câu 9.** Tại sao một filter map REQUEST và ERROR có thể có hai lượt gọi cho một request lỗi?

**Câu 10.** @Order trên SecurityFilterChain quyết định thứ tự cái gì? Muốn chèn custom security filter trước một filter chuẩn dùng API nào?

**Câu 11.** Vì sao @ResponseBody/ResponseEntity làm postHandle không phải nơi đáng tin để đặt response header?

**Câu 12.** Làm sao xác nhận thứ tự trên embedded container thay vì chỉ kiểm tra getter getOrder?

**Câu 13.** Thêm Filter class làm @Component rồi addFilterBefore vào HttpSecurity có nguy cơ gì?

**Câu 14.** WebFilter của WebFlux có dùng Servlet FilterRegistrationBean không?

**Câu 15.** Khi hai components có cùng order=10, nên viết code quan trọng phụ thuộc cái nào chạy trước không?

### Đáp án

1. Filter order 10 đi vào trước order 20, nếu cả hai cùng match URL và dispatcher.
2. Filter 20 finally rồi Filter 10 finally trong mô hình nested chain.
3. Không. Boot hướng dẫn dùng @Order trên **Filter class**, implements Ordered hoặc FilterRegistrationBean.setOrder.
4. registry.addInterceptor(interceptor).order(value).
5. Không; Servlet filter chain ở bên ngoài Spring MVC interceptor chain.
6. PriorityOrdered thuộc nhóm ưu tiên đặc biệt, thường được sắp trước Ordered thường theo contract của comparator.
7. Không; thứ tự tạo bean dựa dependency graph/lifecycle, không tự đồng nghĩa @Order.
8. Không, nếu pattern không match và không có mapping khác.
9. Container có thể thực hiện ERROR dispatch nội bộ sau REQUEST; filter registration quyết định những dispatcher types nào được áp dụng.
10. Chọn thứ tự xét các SecurityFilterChain; dùng HttpSecurity.addFilterBefore/After để chèn filter vào chain thích hợp.
11. Body/status/headers có thể đã được ghi trong HandlerAdapter trước postHandle.
12. Dùng @SpringBootTest(RANDOM_PORT), TestRestTemplate hoặc HTTP client thật, ghi request-scoped trace và assert thứ tự event.
13. Double registration hoặc thực thi ở hai chuỗi khác nhau; cần kiểm soát registration.
14. Không. WebFilter dùng reactive WebFilterChain và @Order/Ordered theo WebFlux.
15. Không; đặt order khác nhau và kiểm tra runtime khi quan hệ order là yêu cầu quan trọng.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — Ordered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): giá trị order, các hằng HIGHEST_PRECEDENCE và LOWEST_PRECEDENCE.
- [Spring Framework — @Order Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): metadata ordering và khác biệt singleton startup.
- [Spring Framework — PriorityOrdered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/PriorityOrdered.html): nhóm ưu tiên và Comparator behavior.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Filter registration, @Order trên Filter class, FilterRegistrationBean và startup debug logging.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): đăng ký Filter và DispatcherType.
- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): preHandle/postHandle/afterCompletion và committed response.
- [Spring Framework — InterceptorRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/config/annotation/InterceptorRegistration.html): order(int), default 0 và path patterns.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, SecurityFilterChain selection và addFilterBefore/After.
- [Spring Framework — WebFlux WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): reactive WebFilter chain.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): embedded-server integration tests.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): FilterChain và DispatcherType.
