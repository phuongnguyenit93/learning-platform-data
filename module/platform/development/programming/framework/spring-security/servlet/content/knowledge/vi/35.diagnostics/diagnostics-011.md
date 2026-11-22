# Bộ lọc chạy hai lần, thứ tự sai và ngoại lệ không tới thành phần xử lý — Spring Security Servlet

## 1. Ba nhóm triệu chứng cần phân biệt

Trong Spring MVC sử dụng Spring Security Servlet, một request HTTP đi qua các Servlet Filter của container, DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain và cuối cùng mới tới DispatcherServlet/controller. Khi thêm một filter tùy biến, lỗi thường nằm ở **đăng ký**, **thứ tự**, hoặc **ranh giới xử lý ngoại lệ**.

Những triệu chứng điển hình:

- Filter ghi hai log cho một thao tác nhưng không rõ có phải hai lần thực thi thật hay không.
- Logic kiểm tra JWT/cookie chạy ở servlet container và lại chạy bên trong Spring Security chain.
- Filter muốn đọc Authentication nhưng SecurityContext chưa có principal.
- Filter tạo Authentication quá muộn, sau khi authorization đã từ chối.
- Filter ném AuthenticationException nhưng không tới ExceptionTranslationFilter.
- @RestControllerAdvice bắt được lỗi từ controller nhưng không bắt được lỗi từ filter.
- Một chain có cấu hình đúng nhưng URL thực tế đi vào chain khác.
- Một request được dispatch lại dưới DispatcherType.ERROR hoặc ASYNC.

Mục tiêu bài là xây tư duy chẩn đoán từng lớp, sửa những nguyên nhân thực sự gây lặp/sai thứ tự, định tuyến exception tới đúng handler, đồng thời có ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x và MockMvc. Đây là **Servlet stack**, không phải WebFlux WebFilter.

## 2. Sơ đồ: Servlet Filter chain khác Spring Security Filter chain

~~~text
HTTP request
   |
   v
Servlet container
   |
   +--> Servlet Filter A
   |
   +--> DelegatingFilterProxy("springSecurityFilterChain")
   |          |
   |          v
   |       FilterChainProxy
   |          |
   |          +--> Chọn SecurityFilterChain ĐẦU TIÊN match request
   |          |
   |          +--> SecurityContext-related filters
   |          +--> CSRF/Authentication filters
   |          +--> ExceptionTranslationFilter
   |          +--> AuthorizationFilter
   |          |
   |          v
   |       Quay về Servlet chain
   |
   +--> Servlet Filter B
   |
   v
DispatcherServlet
   |
   +--> MVC HandlerMapping/HandlerAdapter
   +--> Controller/Service
   +--> HandlerExceptionResolver/@ControllerAdvice
~~~

**Servlet filters** có thể được đăng ký bởi container bằng FilterRegistrationBean, @WebFilter, Servlet initializer hoặc Spring Boot auto-registration của Filter bean. **Security filters** được quản lý bên trong FilterChainProxy thông qua cấu hình HttpSecurity hoặc addFilterBefore/addFilterAfter/addFilterAt.

Spring Security có thể có **nhiều SecurityFilterChain**, nhưng FilterChainProxy lựa chọn **chain đầu tiên** có request matcher phù hợp. Nó không cộng dồn toàn bộ filters của tất cả các chain match request.

Do đó cần hỏi: một filter thuộc container chain, security chain hay cả hai? Một @Order áp dụng cho chain selection hay container registration? Một exception xảy ra trước hay sau DispatcherServlet?

## 3. “Hai lần” là hai lần gì?

Đừng suy luận chỉ từ số dòng log. Có nhiều kịch bản:

1. Filter log trước và sau filterChain.doFilter, tạo **hai log cho một invocation**.
2. Client gửi OPTIONS preflight rồi POST, hoặc HTTP client retry.
3. Servlet container dispatch request tới ERROR sau một exception.
4. Một async servlet request có thêm ASYNC dispatch.
5. Hai instance filter khác nhau được tạo bằng hai @Bean/new.
6. Một Filter bean auto-register với container và cũng được addFilterBefore vào security chain.
7. Một filter thường (không phải OncePerRequestFilter) có hai registrations.
8. Code filter gọi filterChain.doFilter hai lần hoặc vừa sendError vừa tiếp tục chain.

Ghi nhận các trường chẩn đoán an toàn:

~~~text
requestId
dispatcherType = REQUEST / ERROR / ASYNC / ...
filterClass
filterInstanceIdentity
invocationStage
selectedChain
httpMethod
outcomeCode
~~~

Không log Authorization header, Cookie, Bearer token, raw query hoặc body để chứng minh filter chạy bao nhiêu lần.

**Định nghĩa cần phân biệt:** lời gọi Filter.doFilter, lời gọi OncePerRequestFilter.doFilterInternal, một servlet dispatch và một network request không nhất thiết cùng số lượng.

## 4. @Component Filter cộng với addFilterBefore: nguyên nhân phổ biến

Một cấu hình đáng nghi:

~~~java
@Component
public class CustomTokenFilter extends OncePerRequestFilter {
    // ... doFilterInternal(...)
}
~~~

Rồi trong SecurityConfig:

~~~java
http.addFilterBefore(
    customTokenFilter,
    UsernamePasswordAuthenticationFilter.class
);
~~~

Ở Spring Boot Servlet, một bean kiểu jakarta.servlet.Filter **có thể tự được đăng ký** ở servlet container. Đồng thời addFilterBefore đưa filter vào Spring Security chain. Nếu không chủ động kiểm soát, cùng filter có thể xuất hiện ở hai cấp đăng ký.

Cần hiểu kỹ:

- Nếu cùng một instance của OncePerRequestFilter bị gọi **lồng nhau trong một dispatch**, already-filtered attribute có thể khiến doFilterInternal chỉ chạy một lần.
- Hai instance khác nhau, tên filter khác nhau hoặc các dispatch khác nhau có thể có hành vi khác.
- Dù chỉ một lần doFilterInternal, việc nó chạy ở **vị trí container** thay vì trong security chain cũng có thể làm sai SecurityContext hoặc exception handling.
- Một filter chỉ triển khai Filter thông thường không tự có cơ chế already-filtered.

Do đó không nên tuyên bố cứ @Component + addFilterBefore thì chắc chắn doFilterInternal chạy hai lần. Hãy kiểm tra filter registration, instance identity và dispatcher type.

### 4.1. Cách sửa A: filter chỉ được tạo trong SecurityFilterChain

Nếu filter không cần là một bean Filter:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        )
        .addFilterBefore(
            new DiagnosticFilter(),
            UsernamePasswordAuthenticationFilter.class
        )
        .build();
}
~~~

Đây là method minh họa, cần class DiagnosticFilter và imports. Instance new DiagnosticFilter được tạo trong chain, không phải Spring Filter bean để Boot auto-register vào container. Nếu cần service/counter, truyền dependency qua constructor; ví dụ hoàn chỉnh ở phần 12.

### 4.2. Cách sửa B: giữ Filter bean nhưng tắt servlet registration

~~~java
@Bean
FilterRegistrationBean<CustomTokenFilter> disableContainerFilter(
        CustomTokenFilter filter) {

    FilterRegistrationBean<CustomTokenFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}
~~~

Đây là method minh họa cần import org.springframework.boot.web.servlet.FilterRegistrationBean và CustomTokenFilter bean phù hợp. Bean filter vẫn có thể được addFilterBefore vào security chain; disabled registration chỉ nhắm vào việc đăng ký filter với servlet container.

Hãy kiểm tra runtime để chắc chắn không có một registration khác hoặc filter instance thứ hai. Không dùng cách này để vô hiệu hóa các filter hạ tầng ngoài phạm vi.

## 5. OncePerRequestFilter không có nghĩa “duy nhất một lần vĩnh viễn”

OncePerRequestFilter sử dụng request attribute (thường mang hậu tố .FILTERED) để phát hiện filter đã xử lý trong một số ngữ cảnh dispatch. Nhưng một request có thể tham gia các dispatch khác nhau.

| DispatcherType | Tình huống | Điều cần xem |
| --- | --- | --- |
| REQUEST | Yêu cầu ban đầu | Bộ lọc và request mapping |
| ERROR | Container xử lý lỗi | Error dispatch mapping và shouldNotFilterErrorDispatch |
| ASYNC | Async servlet xử lý tiếp | Async dispatch mapping và shouldNotFilterAsyncDispatch |
| FORWARD | Servlet forward nội bộ | Registration mappings, filter instance |
| INCLUDE | Include nội bộ | Registration mappings và ngữ cảnh |

Các hook của OncePerRequestFilter:

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

Hai method này là fragment bên trong subclass. Mặc định của OncePerRequestFilter thường bỏ qua async/error dispatch; ứng dụng có thể override. Các method không sửa double registration, chỉ điều khiển điều kiện filter có chạy theo dispatch hay không.

Các câu hỏi thêm: shouldNotFilter(request) có bỏ route này không? getAlreadyFilteredAttributeName có tạo tên khác giữa các instance không? FilterRegistrationBean có map đúng dispatcher types không?

## 6. Có ba loại thứ tự

**Thứ tự Servlet Filter:** thứ tự đăng ký container (FilterRegistrationBean order, Servlet mappings hoặc @Order theo cơ chế auto-registration phù hợp).

**Thứ tự SecurityFilterChain:** @Order trên SecurityFilterChain bean điều khiển thứ tự FilterChainProxy thử request matcher. Thường **chỉ một chain đầu tiên match** được dùng.

**Thứ tự filter trong một SecurityFilterChain:** HttpSecurity DSL hoặc addFilterBefore/addFilterAfter/addFilterAt điều khiển vị trí tương đối của các filter.

Đặt @Order trên custom Servlet Filter bean không phải cách chuẩn để di chuyển nó trong nội bộ Spring Security chain. Đổi @Order của SecurityFilterChain cũng không làm custom filter tự chuyển vị trí so với ExceptionTranslationFilter.

Ví dụ hai chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().denyAll()
        )
        .build();
}
~~~

Đây là hai method minh họa; muốn bảo vệ API thật cần thêm authentication mechanism. Một request /api/orders khớp chain có @Order(1) không tự chạy thêm filter từ fallback chain.

## 7. securityMatcher khác requestMatchers

Hai DSL có phạm vi khác nhau:

- http.securityMatcher("/api/**") quyết định **cả SecurityFilterChain** có được áp dụng cho request hay không.
- authorizeHttpRequests(...requestMatchers("/api/admin/**").hasRole("ADMIN")) quyết định rule authorization **bên trong chain đã được chọn**.

Nếu chain chỉ match /api/** thì rule /admin/** trong chain đó không áp dụng cho /admin/home. Khi một filter không chạy trên URL mong muốn, kiểm tra matcher trước khi sửa vị trí filter.

Một catch-all chain @Order(1) có thể chiếm request trước chain chuyên biệt @Order(2). Hãy sắp xếp chain chuyên biệt trước và fallback có chính sách rõ, không để URL nhạy cảm lọt ngoài chain.

## 8. Vị trí filter tương quan SecurityContext và authorization

Một sơ đồ chức năng tổng quát:

~~~text
SecurityContext management
       |
       v
CSRF / security-related filters
       |
       v
Authentication filters (Basic / form / Bearer ...)
       |
       v
Anonymous/context/request-cache-related filters
       |
       v
ExceptionTranslationFilter
       |
       v
AuthorizationFilter
       |
       v
DispatcherServlet / Controller
~~~

Đây không phải thứ tự cố định cho mọi phiên bản, mà là cách định hướng trách nhiệm.

Nếu filter đọc Authentication quá sớm, có thể chỉ thấy null/anonymous. Nếu filter tạo Authentication quá muộn, AuthorizationFilter có thể đã từ chối. Nếu filter ném AuthenticationException **trước ExceptionTranslationFilter**, ETF không thể tự bắt một exception xảy ra ở upstream trước khi nó bắt đầu bọc downstream.

Nếu filter gọi response.sendError hoặc ghi body rồi vẫn gọi filterChain.doFilter, downstream có thể cố sửa một response đã commit. Nếu filter gọi chain.doFilter hai lần, side effects có thể xảy ra hai lần.

Thứ tự phải được chọn theo chức năng. Với JWT Resource Server, nên dùng cấu hình oauth2ResourceServer và authentication filter do framework cung cấp thay vì tự viết token parser thiếu kiểm tra signature, issuer, audience hoặc expiry.

## 9. ExceptionTranslationFilter không phải handler của mọi lỗi

ExceptionTranslationFilter (ETF) tập trung chuyển AuthenticationException và AccessDeniedException từ phần downstream mà nó bọc thành hành vi security phù hợp.

- AuthenticationEntryPoint bắt đầu authentication, thường 401 cho HTTP API hoặc redirect tới login page theo cấu hình.
- AccessDeniedHandler xử lý thiếu quyền của người dùng đã xác thực, thường 403.
- Với request anonymous, một AccessDeniedException có thể được chuyển tới entry point chứ không đơn giản luôn là 403.
- ETF không mặc nhiên chuyển RuntimeException, IOException hoặc lỗi lập trình khác thành 401/403.

Sơ đồ phạm vi:

~~~text
Upstream custom authentication filter
    |
    +--> throws AuthenticationException (ETF chưa được gọi)
    |    => ETF downstream không bắt ngược được
    |
    v
ExceptionTranslationFilter
    |
    +--> try: downstreamFilterChain.doFilter(...)
    |
    +--> catch AuthenticationException / AccessDeniedException
    |
    v
AuthorizationFilter và các downstream filters
~~~

Các authentication filters chuẩn thường có FailureHandler/EntryPoint do chính chúng quản lý. Khi custom filter chạy trước ETF, cần thiết kế xử lý lỗi trong component của nó hoặc dùng built-in authentication framework.

## 10. Java 17 runnable: ranh giới try/catch

Đoạn sau là chương trình JDK thuần **mô phỏng call stack**, không phải code nội bộ Spring Security.

File FilterBoundaryDemo.java:

~~~java
public class FilterBoundaryDemo {

    interface Chain {
        void run();
    }

    static void upstream(boolean fail, Chain next) {
        if (fail) {
            throw new IllegalStateException("UPSTREAM");
        }
        next.run();
    }

    static void translate(Chain downstream) {
        System.out.println("translator:enter");

        try {
            downstream.run();
        } catch (IllegalStateException ex) {
            System.out.println(
                "translator:caught=" + ex.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE_DOWNSTREAM");

        upstream(false, () ->
            translate(() -> {
                throw new IllegalStateException("DOWNSTREAM");
            })
        );

        System.out.println("CASE_UPSTREAM");
        try {
            upstream(true, () ->
                translate(() -> System.out.println("never"))
            );
        } catch (IllegalStateException ex) {
            System.out.println("outer:caught=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FilterBoundaryDemo.java
java FilterBoundaryDemo
~~~

Stdout chính xác:

~~~text
CASE_DOWNSTREAM
translator:enter
translator:caught=DOWNSTREAM
CASE_UPSTREAM
outer:caught=UPSTREAM
~~~

Ở CASE_DOWNSTREAM, exception được ném trong lời gọi mà translate bao quanh nên translator bắt được. Ở CASE_UPSTREAM, lỗi xuất hiện trước khi translate được gọi, chỉ catch phía ngoài nhận nó. Đây là ý nghĩa của việc ExceptionTranslationFilter không bắt exception ném ở filter đứng trước nó.

## 11. @ControllerAdvice không tự bắt lỗi trong Servlet Filter

@RestControllerAdvice và @ExceptionHandler là cơ chế của Spring MVC, đi qua DispatcherServlet và HandlerExceptionResolver. Một Servlet filter có thể ném exception **trước khi request tới DispatcherServlet**.

~~~text
Servlet Filter throws RuntimeException
    |
    +--> DispatcherServlet chưa xử lý request
         @ControllerAdvice thường không thấy lỗi

Servlet Filter cho request đi tiếp
    |
    v
DispatcherServlet -> Controller throws RuntimeException
    |
    v
HandlerExceptionResolver / @ControllerAdvice có thể xử lý
~~~

Đừng dựa vào exception type giống nhau để kết luận cả hai được xử lý như nhau.

Phân loại:

| Lỗi | Nơi xử lý thích hợp |
| --- | --- |
| Authentication failure trong authentication filter | AuthenticationFailureHandler hoặc AuthenticationEntryPoint |
| Authorization failure downstream ETF | ExceptionTranslationFilter / AccessDeniedHandler |
| RequestRejectedException do HttpFirewall | RequestRejectedHandler của FilterChainProxy |
| Missing/invalid CSRF token | Cơ chế access-denied handling của CsrfFilter |
| Exception trong controller | HandlerExceptionResolver / @ControllerAdvice |
| RuntimeException ở Servlet filter bên ngoài MVC | Filter/container error handling hoặc adapter riêng được thiết kế rõ |

Có thể chủ động gọi HandlerExceptionResolver từ một filter nếu ứng dụng chủ ý làm vậy và đã kiểm thử; nó không tự xảy ra và không phải giải pháp chung cho mọi security exception.

## 12. Demo Spring Boot: DiagnosticFilter chỉ nằm trong security chain

Dự án Java 17+ Spring Boot 3.x cần các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đặt các class trong package demo.filterdiagnostics, dự án có Spring Boot plugin/BOM phù hợp và Gradle wrapper.

### 12.1. Main class

File FilterDiagnosticsApplication.java:

~~~java
package demo.filterdiagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDiagnosticsApplication.class, args);
    }
}
~~~

### 12.2. Counter bean

File ProbeCounter.java:

~~~java
package demo.filterdiagnostics;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProbeCounter {

    private final AtomicInteger count = new AtomicInteger();

    public void mark() {
        count.incrementAndGet();
    }

    public int get() {
        return count.get();
    }

    public void reset() {
        count.set(0);
    }
}
~~~

Counter là minh họa test tuần tự. Khi nhiều requests chạy đồng thời trên production, counter toàn cục không chứng minh riêng số lần của một request; cần correlation/metrics theo context phù hợp.

### 12.3. DiagnosticFilter không là Spring bean

File DiagnosticFilter.java:

~~~java
package demo.filterdiagnostics;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class DiagnosticFilter extends OncePerRequestFilter {

    private final ProbeCounter counter;

    public DiagnosticFilter(ProbeCounter counter) {
        this.counter = counter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        counter.mark();

        // Không log Authorization/Cookie hoặc raw query để debug.
        filterChain.doFilter(request, response);
    }
}
~~~

Không đặt @Component, @WebFilter hay FilterRegistrationBean cho DiagnosticFilter trong demo. Nó sẽ được new bên trong SecurityFilterChain và không trở thành bean Filter để Boot auto-register. Filter chỉ gọi chain.doFilter **một lần**.

### 12.4. SecurityConfig: hai chains

File SecurityConfig.java:

~~~java
package demo.filterdiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            ProbeCounter counter) throws Exception {

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll()
            )
            .addFilterBefore(
                new DiagnosticFilter(counter),
                UsernamePasswordAuthenticationFilter.class
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll()
            )
            .build();
    }
}
~~~

/api/ping match chain @Order(1) và chạy DiagnosticFilter; /status vào fallback chain và không có DiagnosticFilter. permitAll chỉ phục vụ demo việc chọn chain và đếm filter, **không phải policy production**.

### 12.5. Controller

File ProbeController.java:

~~~java
package demo.filterdiagnostics;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/status")
    public String status() {
        return "ok";
    }
}
~~~

### 12.6. Test MockMvc có assertions về số lần filter chạy

File src/test/java/demo/filterdiagnostics/DiagnosticFilterIntegrationTest.java:

~~~java
package demo.filterdiagnostics;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticFilterIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProbeCounter counter;

    @BeforeEach
    void resetCount() {
        counter.reset();
    }

    @Test
    void apiRequestInvokesFilterOnce() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));

        assertEquals(1, counter.get());
    }

    @Test
    void fallbackRequestDoesNotInvokeApiFilter() throws Exception {
        mvc.perform(get("/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        assertEquals(0, counter.get());
    }
}
~~~

Chạy với Gradle wrapper:

~~~bash
./gradlew test --tests demo.filterdiagnostics.DiagnosticFilterIntegrationTest
~~~

Trong cấu hình mẫu, kỳ vọng hai tests pass; không khẳng định stdout Gradle cố định. Test này chỉ đo các GET bình thường trên MockMvc, không phải bằng chứng rằng mọi ERROR/ASYNC dispatch và production proxy đều có cùng invocation count.

## 13. Nếu filter cần là Spring bean

Khi custom filter cần inject service, có thể tạo một bean rồi **tắt servlet registration**:

~~~java
@Bean
MyTokenFilter myTokenFilter(MyDependency dependency) {
    return new MyTokenFilter(dependency);
}

@Bean
FilterRegistrationBean<MyTokenFilter> filterRegistration(
        MyTokenFilter filter) {

    FilterRegistrationBean<MyTokenFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain chain(
        HttpSecurity http,
        MyTokenFilter filter) throws Exception {

    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated()
        )
        .addFilterBefore(
            filter,
            UsernamePasswordAuthenticationFilter.class
        )
        .build();
}
~~~

Đây là các fragments cần types MyTokenFilter/MyDependency, imports và authentication configuration, không phải chương trình tự chạy. Mục tiêu: bean có thể được inject vào security chain nhưng không cần được đăng ký thành Servlet filter ngoài FilterChainProxy.

Không cố sửa lỗi bằng cách tự tạo static boolean đã chạy: state dùng chung giữa các requests có thể gây race condition và làm bỏ qua authentication của người dùng khác.

## 14. Custom authentication filter xử lý lỗi thế nào?

Custom authentication filter ở upstream của ExceptionTranslationFilter cần có failure handling phù hợp; khi dùng SecurityFilterChain, ưu tiên built-in authentication filters của Spring Security.

Pseudocode Java fragment sau mô tả cách **bắt chỉ lỗi ở bước authentication**, không bắt nhầm lỗi downstream:

~~~java
Authentication authenticated;

try {
    authenticated =
        authenticationManager.authenticate(inputAuthentication);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    entryPoint.commence(request, response, ex);
    return;
}

SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

filterChain.doFilter(request, response);
~~~

Đoạn này đặt trong filter đã có authenticationManager, inputAuthentication, entryPoint, request, response và filterChain được cấu hình. Nó **không phải JWT verifier đầy đủ**. Không tự viết provider chấp nhận token chưa được kiểm tra chữ ký, issuer, audience và expiry.

Không đặt cả filterChain.doFilter trong try/catch AuthenticationException một cách vô ý, vì có thể bắt cả lỗi downstream không do custom filter sở hữu. Sau entryPoint.commence phải return, không tiếp tục chain khi response đã được xử lý.

## 15. Vì sao exception không đến handler như dự kiến?

Danh sách nguyên nhân cần kiểm tra:

1. Filter ném lỗi **trước ETF**, nên ETF không bọc được.
2. Exception là generic RuntimeException hoặc IOException, ngoài nhóm ETF xử lý.
3. Filter bắt/nuốt exception rồi ghi status riêng.
4. Filter gửi response 401/403 nhưng vẫn gọi downstream, gây committed response.
5. Lỗi xảy ra ở Servlet Filter nằm ngoài FilterChainProxy.
6. HttpFirewall reject request trước khi chain bắt đầu, cần RequestRejectedHandler.
7. DispatcherServlet chưa chạy, nên @ControllerAdvice không tham gia.
8. Chọn sai SecurityFilterChain vì matcher hoặc @Order.
9. Filter gọi chain.doFilter hai lần hoặc không gọi ở nhánh bắt buộc.
10. Exception ở ERROR/ASYNC dispatch với filter mapping khác request ban đầu.

Mã HTTP 401/403/500 chỉ là triệu chứng; cần kiểm tra **component nào thực sự tạo phản hồi**. Với CSRF, CsrfFilter có cơ chế xử lý AccessDenied riêng và có thể trả 403 trước ETF. Với request anonymous bị AccessDeniedException downstream, entry point có thể được gọi; 403 không luôn là kết quả duy nhất.

## 16. Debug chain có kiểm soát

Ở môi trường kiểm thử, có thể tạm bật:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security=DEBUG
~~~

Không bật TRACE/DEBUG rộng trên production mà chưa kiểm toán những gì bị ghi vào log, đặc biệt token, Cookie, principal và path/query. Chỉ log request ID do server tạo, dispatcher type, filter class, event code và selected chain nếu cần.

Những điểm breakpoint thường hữu ích:

- DelegatingFilterProxy.doFilter: xem servlet registration.
- FilterChainProxy.doFilter: xem matcher và chain đã chọn.
- OncePerRequestFilter.doFilter/doFilterInternal: xem attribute chống lặp.
- ExceptionTranslationFilter.doFilter: xác định try/catch boundary.
- AuthorizationFilter.doFilter: xem quyết định access.
- AuthenticationEntryPoint.commence / AccessDeniedHandler.handle.
- DispatcherServlet.doDispatch và HandlerExceptionResolver.
- HttpFirewall/RequestRejectedHandler nếu request bị reject từ đầu.

Với MockMvc, kiểm tra có bị gắn springSecurityFilterChain thủ công **thêm một lượt** ngoài auto-configuration hay không. Không dùng test setup khác production để suy luận sai nguyên nhân.

## 17. Ma trận kiểm thử hồi quy

| Ca | Kỳ vọng |
| --- | --- |
| GET /api/ping | DiagnosticFilter doFilterInternal một lần |
| GET /status | DiagnosticFilter không chạy |
| Hai chains cùng matcher | Chain đầu tiên theo @Order được chọn |
| Filter bean + addFilterBefore | Phát hiện container registration thừa |
| Filter không là bean | Chỉ nằm trong security chain |
| REQUEST sang ERROR dispatch | Phân biệt dispatcher types, không kết luận hai network requests |
| Async dispatch | Theo shouldNotFilterAsyncDispatch và mappings |
| Controller throws | @ControllerAdvice xử lý nếu resolver phù hợp |
| Upstream Filter throws | Không mặc định tới MVC advice |
| AuthenticationException upstream ETF | Authentication failure handler/entry point phù hợp |
| AccessDeniedException downstream ETF | ETF chuyển đến entry point hoặc denied handler |
| RequestRejectedException | RequestRejectedHandler theo cấu hình |
| Filter sendError rồi return | Không gọi controller |
| Filter gọi doFilter hai lần | Test phát hiện downstream chạy lặp |

Không chỉ assert status; hãy xác minh filter nào chạy, handler nào xử lý và dữ liệu nghiệp vụ có side effect hay không.

## 18. Sai lầm phổ biến

**Đăng ký hai nơi mà không nhận ra:** @Component Filter có thể được container auto-register, addFilterBefore lại đưa vào security chain.

**Nhầm OncePerRequestFilter:** không bảo đảm đúng một lần trong mọi dispatcher hoặc mọi instance.

**Nhầm order:** @Order trên SecurityFilterChain khác vị trí nội bộ filter và khác container Filter order.

**Nhầm matcher:** securityMatcher quyết định chain; requestMatchers bên trong chain quyết định authorization.

**Lỗi try/catch:** ETF chỉ bắt downstream exception đúng loại, không bắt lỗi upstream.

**Nhầm ControllerAdvice:** MVC handler không tự bao mọi filter.

**Sai response flow:** sendError/entryPoint rồi vẫn call doFilter hoặc gọi doFilter hai lần.

**Bắt mọi lỗi thành 401:** che lỗi lập trình/IO thành lỗi authentication, làm debug khó hơn.

**Debug bằng token:** ghi Authorization/Cookie/JWT để thấy filter chạy khiến hệ thống lộ credential.

## 19. Checklist chẩn đoán hiệu quả

- [ ] Xác định có một hay nhiều HTTP requests; có retry/preflight không.
- [ ] Xem dispatcher type REQUEST, ERROR, ASYNC hoặc FORWARD.
- [ ] Xác định Servlet Filter bean/instance và registrations.
- [ ] Kiểm tra @Component, @WebFilter, FilterRegistrationBean, addFilterBefore.
- [ ] Kiểm tra once-filter attribute, shouldNotFilter và dispatcher mappings.
- [ ] Xác định SecurityFilterChain nào được chọn theo @Order/securityMatcher.
- [ ] Kiểm tra vị trí filter so với SecurityContext, authentication, ETF, AuthorizationFilter.
- [ ] Xác định exception class và nơi ném thực tế.
- [ ] Dùng đúng AuthenticationEntryPoint, AccessDeniedHandler, RequestRejectedHandler hoặc MVC advice.
- [ ] Không gọi filterChain.doFilter sau khi đã phản hồi và return.
- [ ] Kiểm thử số lần chạy và handler thực, không chỉ HTTP status.
- [ ] Chỉ log metadata chẩn đoán an toàn và tắt TRACE sau điều tra.

## 20. Câu hỏi ôn tập và kết luận

**Câu 1.** Vì sao một Filter bean vừa được addFilterBefore có thể gây thứ tự xử lý sai?

Vì một bean Filter có thể được Servlet container đăng ký tự động, bên cạnh việc tham gia Spring Security chain. Hai cấp đăng ký có vị trí khác nhau.

**Câu 2.** ETF có bắt exception ném trong filter phía trước nó không?

Không mặc nhiên. ETF chỉ bao quanh downstream chain của nó; upstream filter cần failure handling phù hợp.

**Câu 3.** @ControllerAdvice bắt mọi Servlet filter exception không?

Không. Nó thuộc cơ chế MVC và có thể chưa được kích hoạt khi exception phát sinh trước DispatcherServlet.

**Câu 4.** Hai dòng log có chứng minh filter chạy hai lần không?

Không. Cần phân biệt log trước/sau, network requests, dispatch types, filter instances và số lần doFilterInternal.

**Câu 5.** Đổi @Order SecurityFilterChain có thay thứ tự filter nội bộ không?

Không. Nó thay thứ tự chain được xét, không thay vị trí filter bên trong chain.

**Kết luận:** Để chẩn đoán bộ lọc chạy hai lần, sai thứ tự hay ngoại lệ không tới đúng handler, hãy tách **Servlet registration**, **SecurityFilterChain selection**, **filter order**, **dispatcher lifecycle** và **exception catch boundary**. Thiết kế custom filters có đúng một đường đăng ký, gọi downstream chain một lần, dùng authentication/authorization/error handler đúng trách nhiệm và kiểm thử bằng MockMvc với số lần gọi rõ ràng.
