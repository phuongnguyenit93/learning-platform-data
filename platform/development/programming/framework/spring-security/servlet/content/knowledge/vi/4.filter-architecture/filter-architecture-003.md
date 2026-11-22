# SecurityFilterChain: điều kiện áp dụng và danh sách bộ lọc trong Spring Security Servlet

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích được **SecurityFilterChain** là gì, một request được chọn vào chain nào, sự khác nhau giữa **điều kiện chọn chain** và **điều kiện phân quyền**, cách quan sát danh sách filter thực tế, cũng như những lỗi cấu hình khiến endpoint không được Spring Security bảo vệ đúng ý định.

Bối cảnh là ứng dụng **Spring MVC/Servlet với Spring Security 6 và Spring Boot 3.x**, sử dụng Java 17 trở lên. Những lớp quan trọng gồm DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, DefaultSecurityFilterChain, HttpSecurity, RequestMatcher và các security filter.

## 1. Vì sao cần SecurityFilterChain?

Servlet container (như Tomcat) xử lý HTTP request qua các Servlet Filter trước khi vào DispatcherServlet/controller. Spring Security cũng bảo vệ request bằng các filter, nhưng các filter bảo mật được tập hợp và điều phối thông qua **FilterChainProxy**.

Có thể hình dung luồng:

~~~text
HTTP request
    |
Servlet container filter chain
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |
    +-- tìm SecurityFilterChain ĐẦU TIÊN có matches(request) == true
    |       |
    |       +-- chạy các security filter của CHAIN ĐƯỢC CHỌN, theo thứ tự
    |               |
    |               +-- xác thực, quản lý SecurityContext, CSRF, phân quyền...
    |                       |
    +-----------------------+--> tiếp tục servlet filter chain --> DispatcherServlet
                                                            --> Controller
~~~

Các ý chính:

- **DelegatingFilterProxy** là cầu nối từ filter do Servlet container quản lý tới bean Spring có tên thường là springSecurityFilterChain.
- Bean đó thường là **FilterChainProxy**, quản lý một danh sách các SecurityFilterChain, mỗi chain có **RequestMatcher** riêng và **danh sách Filter được sắp thứ tự**.
- Một SecurityFilterChain thể hiện “request nào đi vào đây?” cùng “những filter nào áp dụng cho request đó?”. DefaultSecurityFilterChain là cách triển khai quen thuộc.
- Mỗi request đi qua **chain đầu tiên khớp** trong danh sách ưu tiên, không tự động ghép filter của nhiều chain.
- Nếu **không chain nào khớp**, FilterChainProxy không áp dụng các security filter của Spring Security cho request đó. Các filter bảo mật khác ở tầng Servlet container có thể vẫn tồn tại, nhưng bạn đã để lại một vùng không được chính các SecurityFilterChain của Spring Security kiểm soát.
- Một filter nằm trong danh sách chưa chắc thực hiện hành động trên mọi request: ví dụ CsrfFilter thường không yêu cầu token cho GET, còn filter xác thực Basic có thể cho request không mang Authorization đi tiếp để cơ chế ủy quyền quyết định.

Điều này giải thích vì sao cần hiểu cả **phạm vi chain**, **thứ tự các chain** và **thứ tự các filter bên trong mỗi chain**.

## 2. Điều kiện áp dụng: SecurityFilterChain được chọn thế nào?

### 2.1. RequestMatcher của toàn chain

Khi tạo một bean SecurityFilterChain từ HttpSecurity, bạn có thể đặt phạm vi của chain bằng **securityMatcher(...)**:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là **một đoạn cấu hình minh họa đặt trong lớp @Configuration** có import Spring Security tương ứng; ví dụ chương trình đầy đủ ở phần sau. Điều kiện securityMatcher("/api/**") dùng để chọn chain khi request được bộ so khớp đường dẫn của ứng dụng xác định thuộc /api/**. Request ngoài phạm vi này **không đi qua các filter thuộc chain API**.

Nếu không gọi securityMatcher, HttpSecurity mặc định tạo chain nhận **mọi request**. Với nhiều chain, cần xác định thứ tự để chain cụ thể được xét trước chain tổng quát.

RequestMatcher cũng có thể dựa trên phương thức HTTP hoặc các đặc tính của HttpServletRequest, tùy implementation. Khi dùng chuỗi pattern trong Spring Security 6, matcher thực tế có thể phụ thuộc Spring MVC, cách triển khai và cấu hình ứng dụng. Vì thế phải kiểm thử trên URL, servlet mapping và context path thật, đặc biệt với nhiều Servlet hoặc cấu trúc path phức tạp.

### 2.2. First-match wins và @Order

Giả sử có hai bean:

~~~text
@Order(1): securityMatcher("/api/**") -> HTTP Basic API
@Order(2): matcher mặc định mọi request -> Form Login website
~~~

Quy tắc chọn:

| Request | Chain được chọn | Giải thích |
| --- | --- | --- |
| GET /api/status | API, thứ tự 1 | Khớp /api/** trước |
| POST /api/orders | API, thứ tự 1 | Vẫn là API dù method khác |
| GET /dashboard | Web, thứ tự 2 | Không khớp chain API, khớp fallback |
| GET /public/ping | Web, thứ tự 2 | Có thể được permitAll bên trong chain Web |
| GET /not-found | Web, thứ tự 2 | Vẫn đi qua Spring Security; controller có thể trả 404 sau đó |

**Số @Order thấp hơn có độ ưu tiên cao hơn**. Nếu đặt chain có matcher mọi request trước chain API, chain tổng quát sẽ lấy hết request và API chain có thể không bao giờ được chọn. Nếu chỉ khai báo chain /api/** mà không có fallback bao quát các URL khác, URL ngoài /api/** có thể lọt khỏi các security filter của Spring Security.

Không dùng thứ tự bean ngẫu nhiên làm hợp đồng bảo mật. Nên đặt @Order rõ ràng khi có nhiều chain, và thêm một chain cuối phù hợp với chính sách mặc định (thường cần xác thực, chứ không vô tình bỏ qua request).

### 2.3. securityMatcher khác requestMatchers trong authorizeHttpRequests

Đây là hai tầng quyết định:

| Cấu hình | Câu hỏi nó giải quyết | Tác động |
| --- | --- | --- |
| http.securityMatcher("/api/**") | Request có **đi vào SecurityFilterChain này** không? | Chọn toàn bộ danh sách filter |
| authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...)) | Khi request **đã vào chain**, người gọi có đủ quyền không? | Quy tắc authorization |
| authorizeHttpRequests(auth -> auth.anyRequest().denyAll()) | Những request đã vào chain và không có luật trước sẽ bị xử lý ra sao? | Từ chối quyền trong chain hiện tại |

Ví dụ:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll());
~~~

Đây là **mảnh cấu hình**, không phải một chương trình tự chạy. GET /api/reports/42 được xét theo luật scope; POST /api/reports/42 **vẫn đi vào chain API** nhưng bị denyAll. GET /dashboard không đi vào chain này dù authorization có anyRequest. Đừng cho rằng requestMatchers trong authorizeHttpRequests tự tạo hoặc thu hẹp SecurityFilterChain.

Trong một chain, các luật requestMatchers của authorizeHttpRequests được xét theo thứ tự khai báo; đặt luật cụ thể trước luật bao quát và để anyRequest cuối. Tránh nhầm “một request không khớp luật phân quyền cụ thể” với “request không khớp chain”.

### 2.4. permitAll vẫn đi qua chain

Khi dùng:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
~~~

GET /public/ping **vẫn qua những filter của chain đã chọn**, dù AuthorizationFilter có thể cho phép nó đi tiếp. Header bảo mật, các cơ chế quản lý context và filter khác vẫn có thể tác động. Một header Authorization không hợp lệ thậm chí có thể bị filter xác thực từ chối trước khi đi đến luật permitAll, tùy loại authentication được bật.

Ngược lại, dùng WebSecurityCustomizer.ignoring() khiến request bỏ qua Spring Security filter chain, có thể bỏ qua cả những filter bảo mật/hardening cần thiết. Với endpoint công khai thông thường, **permitAll** thường phù hợp hơn; chỉ bỏ qua toàn bộ chain khi thật sự có lý do kiến trúc cụ thể.

## 3. Danh sách filter bên trong mỗi chain

Một chain không có “danh sách filter chuẩn cố định” áp dụng mọi dự án. Spring Security tổng hợp danh sách và thứ tự dựa trên những tính năng bạn bật: formLogin, httpBasic, oauth2ResourceServer, csrf, logout, sessionManagement, exceptionHandling, authorizeHttpRequests và custom filter.

Một số filter thường gặp trong Spring Security Servlet:

| Filter | Vai trò chính |
| --- | --- |
| DisableEncodeUrlFilter | Hạn chế việc ghi session ID vào URL theo cơ chế encoding URL; có thể có trong cấu hình hiện đại |
| WebAsyncManagerIntegrationFilter | Hỗ trợ tích hợp SecurityContext với xử lý bất đồng bộ Spring MVC |
| SecurityContextHolderFilter | Nạp SecurityContext cho phạm vi xử lý và dọn sau request theo cơ chế hiện đại; một cấu hình/phiên bản khác có thể sử dụng SecurityContextPersistenceFilter |
| HeaderWriterFilter | Ghi các HTTP response header bảo mật theo cấu hình |
| CsrfFilter | Kiểm tra CSRF token với các request cần bảo vệ |
| LogoutFilter | Xử lý request logout theo cấu hình, thường trước các filter xác thực form |
| UsernamePasswordAuthenticationFilter | Xử lý POST đăng nhập theo formLogin |
| BasicAuthenticationFilter | Xử lý Authorization: Basic ... khi bật httpBasic |
| BearerTokenAuthenticationFilter | Xử lý Authorization: Bearer ... khi dùng OAuth2 Resource Server |
| RequestCacheAwareFilter | Tích hợp request cache, ví dụ request trước khi chuyển sang login |
| SecurityContextHolderAwareRequestFilter | Bọc Servlet request để các API Servlet nhận biết authentication/security |
| AnonymousAuthenticationFilter | Tạo biểu diễn anonymous khi request chưa có Authentication phù hợp |
| ExceptionTranslationFilter | Chuyển AuthenticationException/AccessDeniedException thành authentication entry point hoặc xử lý access-denied |
| AuthorizationFilter | Kiểm tra quyền truy cập theo AuthorizationManager và các luật authorizeHttpRequests |

Các filter được đăng ký theo thứ tự nội bộ do Spring Security quy định; **đừng dùng thứ tự trong bảng này làm bằng chứng exact cho ứng dụng**. Đặc biệt, không mặc nhiên kết luận mỗi chain chứa tất cả filter trong bảng: chain chỉ bật formLogin có thể không có BasicAuthenticationFilter, chain chỉ Basic thường không có UsernamePasswordAuthenticationFilter, còn BearerTokenAuthenticationFilter cần cấu hình Resource Server.

### 3.1. Phân biệt vai trò những bước thường gây nhầm

**SecurityContextHolderFilter** chủ yếu đưa context sẵn có vào phạm vi xử lý và dọn đi đúng lúc; nó không tự xác thực username/password. **Filter xác thực** như BasicAuthenticationFilter hoặc UsernamePasswordAuthenticationFilter tạo Authentication khi có credential tương ứng và xác thực thành công. **AnonymousAuthenticationFilter** có thể bổ sung Authentication đại diện anonymous nếu chưa được xác thực. **AuthorizationFilter** mới đánh giá luật quyền; sau đó **ExceptionTranslationFilter** hỗ trợ phản hồi 401, redirect login hoặc 403 theo entry point và access-denied handler.

Với form login, filter đăng nhập có thể trả redirect ngay khi xác thực xong, không nhất thiết request login tiếp tục đến controller. Với request bị chặn bởi CSRF hoặc authorization, controller cũng có thể không chạy. Filter có thể chuyển hướng, trả lỗi hoặc kết thúc chuỗi; vì vậy “trong danh sách filter” không đảm bảo tất cả filter và controller được thực thi xong trên mọi request.

### 3.2. Hai loại thứ tự khác nhau

- **Thứ tự SecurityFilterChain**: FilterChainProxy xét chain nào trước, thường do @Order trên bean quy định.
- **Thứ tự Filter trong chain**: Spring Security bố trí các filter theo các vị trí/quan hệ cố định hoặc qua addFilterBefore, addFilterAfter, addFilterAt.

Không khắc phục lỗi chọn sai chain bằng cách di chuyển filter bên trong một chain không hề được chọn. Cũng không khắc phục lỗi chạy filter trước/sau bằng cách thay đổi @Order của một bean chain đã được chọn đúng.

## 4. Ví dụ chạy được: API dùng HTTP Basic, website dùng form login

Ví dụ sau có hai SecurityFilterChain để quan sát sự khác nhau giữa **matching chain** và **các filter được kích hoạt**. Spring Boot 3.x, Java 17+, cần spring-boot-starter-web và spring-boot-starter-security. API mẫu chỉ có GET nhằm tập trung vào matching/authentication; **CSRF không bị tắt**. Với API có thao tác ghi dữ liệu, phải đánh giá CSRF dựa trên credential có thể được browser tự gửi (HTTP Basic có thể được browser cache), không tắt CSRF chỉ vì URL bắt đầu bằng /api/.

Cấu trúc thư mục trong một dự án Spring Boot thông thường:

~~~text
src/main/java/dev/example/chain/
    ChainDemoApplication.java
    ChainSecurityConfig.java
    DemoController.java
~~~

### 4.1. Ứng dụng Spring Boot

Tệp src/main/java/dev/example/chain/ChainDemoApplication.java:

~~~java
package dev.example.chain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainDemoApplication.class, args);
    }
}
~~~

### 4.2. Hai chain, một user demo

Tệp src/main/java/dev/example/chain/ChainSecurityConfig.java:

~~~java
package dev.example.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class ChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/status")
                            .hasRole("USER")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build());
    }
}
~~~

Giải thích từng quyết định:

1. apiChain có @Order(1), được xét trước, chỉ nhận đường dẫn /api/**.
2. API có BasicAuthenticationFilter nhờ httpBasic. SessionCreationPolicy.STATELESS yêu cầu Spring Security không sử dụng HttpSession để lấy/lưu SecurityContext cho chain API. API chỉ cho GET /api/status nếu user có role USER; request API khác bị denyAll.
3. webChain có @Order(2), không đặt securityMatcher nên là **fallback khớp mọi request còn lại**. Chain này bật form login và giữ cách xử lý session mặc định, không tự động nhận BasicAuthenticationFilter chỉ vì API chain dùng Basic.
4. /public/** được permitAll **bên trong fallback**, vẫn chịu các filter của web chain. Mọi URL còn lại cần đăng nhập.
5. UserDetailsService và PasswordEncoder là dữ liệu demo cục bộ. Mật khẩu mẫu đã được mã hóa bằng encoder trước khi lưu in-memory; không dùng credential này ngoài môi trường học.
6. Không có lời gọi csrf.disable(). Nếu thêm POST/PUT/DELETE API với HTTP Basic, request có thể bị CsrfFilter từ chối khi thiếu token; đây là hành vi có chủ đích cần được đánh giá riêng.

Mặc dù cả hai chain có thể dùng chung UserDetailsService, chúng **không chia sẻ một danh sách filter mặc định**. Một request /api/status được xử lý theo API chain; một request /dashboard được xử lý theo web chain.

### 4.3. Controller để nhìn kết quả

Tệp src/main/java/dev/example/chain/DemoController.java:

~~~java
package dev.example.chain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/status")
    public String apiStatus() {
        return "API OK";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "WEB OK";
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "PUBLIC OK";
    }
}
~~~

Với dự án Spring Boot có hai starter nêu trên, chạy ứng dụng bằng wrapper của dự án, ví dụ:

~~~bash
./gradlew bootRun
~~~

Nếu dự án dùng Maven, chạy bằng Maven tương ứng. Không thể chỉ gọi javac trên từng file vì code phụ thuộc thư viện Spring Boot/Spring Security; file Java ở ví dụ được viết để biên dịch **trong project có dependency đúng**.

### 4.4. Request thử nghiệm và kết quả kỳ vọng

Khi chạy local trên http://localhost:8080, dùng terminal:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/status
curl -s -u demo:local-demo-password http://localhost:8080/api/status
curl -i http://localhost:8080/dashboard
curl -i -u demo:local-demo-password http://localhost:8080/api/unknown
~~~

Bảng kỳ vọng cho phiên thử mới, không có cookie đăng nhập trước đó:

| Lệnh/request | Chain | Kết quả dự kiến |
| --- | --- | --- |
| GET /public/ping | Web fallback | HTTP 200, body PUBLIC OK |
| GET /api/status, không Basic | API | HTTP 401, thường có WWW-Authenticate: Basic ... |
| GET /api/status, Basic hợp lệ | API | HTTP 200, body API OK |
| GET /dashboard, chưa có session | Web fallback | Thường HTTP 302 chuyển đến trang đăng nhập |
| GET /api/unknown, Basic hợp lệ | API | HTTP 403 vì anyRequest().denyAll(), chưa tới controller |

Với lệnh thứ ba, stdout body từ curl -s là chính xác chuỗi **API OK** (controller không tự thêm newline). Kết quả cụ thể của header, status hoặc redirect có thể thay đổi nếu dự án có cấu hình khác, proxy hoặc filter bổ sung.

**Lưu ý:** HTTP localhost chỉ để học trên máy cá nhân; trên mạng thực tế dùng HTTPS, không gửi mật khẩu qua kênh HTTP và hạn chế mật khẩu lộ trong shell history. Với browser, thử form login ở /dashboard rồi kiểm tra cookie/session bằng DevTools nhưng không sao chép JSESSIONID thật vào báo cáo. Một session cookie của web chain không tự cấp quyền cho API chain có STATELESS và Basic.

## 5. Cách xem danh sách filter thực tế

Điều muốn kiểm chứng là: **mỗi chain có matcher gì và danh sách filter nào theo thứ tự nào?** Đừng suy diễn list từ việc đặt tên bean hay đọc ví dụ trong tài liệu.

### 5.1. Log ở môi trường phát triển

Có thể bật log cho Spring Security trong application.yml của môi trường dev:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Khi khởi động và gửi request, log thường cung cấp thông tin về chain/filter bảo mật được tạo và quá trình áp dụng filter. Chi tiết thông điệp và mức log phụ thuộc phiên bản Spring Security; không dựa vào một câu log cố định để viết rule vận hành. Chỉ bật TRACE khi cần debug, rồi hạ mức log trở lại. Filter/request log có thể chứa đường dẫn, context hoặc thông tin nhạy cảm; luôn kiểm soát truy cập log và không in Authorization, session ID, token hay mật khẩu.

Trong SecurityFilterChain, các filter sẽ khác nhau giữa hai chain của ví dụ. Chẳng hạn API chain có thể có BasicAuthenticationFilter còn web chain có UsernamePasswordAuthenticationFilter. Các filter chung như HeaderWriterFilter hoặc AuthorizationFilter có thể xuất hiện ở cả hai. Thứ tự chính xác phải đọc từ log/chain của ứng dụng chạy thật.

### 5.2. Kiểm tra cấu hình thành phần

FilterChainProxy cung cấp khả năng truy cập các SecurityFilterChain qua getFilterChains(); từng chain cho biết matcher và filter đã đăng ký. Đây là hướng phù hợp khi cần kiểm chứng bằng mã kiểm thử hoặc công cụ chẩn đoán. Không nhầm danh sách **Filter nằm trong một SecurityFilterChain** với toàn bộ Servlet Filter được container đăng ký bên ngoài FilterChainProxy.

Khi phân tích log, ghép ba dữ kiện: (1) request được xét với path/method nào, (2) matcher chain đầu tiên nào được chọn, (3) filter nào thực thi hoặc từ chối trước controller. Chỉ đọc danh sách filter mà bỏ qua matcher có thể làm bạn debug nhầm chain.

## 6. Chèn custom filter vào đúng chain

Nếu cần thêm một filter để đo thời gian xử lý, gắn correlation ID hoặc kiểm tra dữ liệu kỹ thuật, hãy quyết định **filter đó cần chạy cho request nào** trước. Đặt nó trong apiChain nếu chỉ áp dụng /api/**; không đăng ký toàn bộ ở Servlet container khi yêu cầu chỉ dành cho API.

Ví dụ class Spring Servlet filter đo thời gian, tệp src/main/java/dev/example/chain/ApiTimingFilter.java:

~~~java
package dev.example.chain;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiTimingFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs = (System.nanoTime() - start) / 1_000_000;
            System.out.println(
                    "API " + request.getMethod()
                    + " status=" + response.getStatus()
                    + " durationMs=" + elapsedMs);
        }
    }
}
~~~

Để thêm vào ví dụ apiChain ở trên, import BasicAuthenticationFilter:

~~~java
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
~~~

và trong chuỗi cấu hình apiChain, thêm phương thức sau **trước build()**:

~~~java
.addFilterBefore(new ApiTimingFilter(), BasicAuthenticationFilter.class)
~~~

Hai snippet cuối là **phần cần thêm vào ChainSecurityConfig**, không phải class chạy độc lập. Spring Security đặt filter custom trước vị trí BasicAuthenticationFilter của chain API theo quy tắc sắp xếp nội bộ. Vì matcher của apiChain là /api/**, filter đo thời gian sẽ không được chạy bởi chain này với /dashboard.

Ví dụ sử dụng System.out cho mục đích minh họa; hệ thống thực tế nên dùng logger có cấu trúc, hạn chế thông tin được ghi và tuyệt đối không log secret/token. Nếu biến ApiTimingFilter thành một Servlet Filter bean qua @Component hoặc @Bean và đồng thời chèn vào SecurityFilterChain, Spring Boot có thể tự đăng ký filter ở tầng Servlet container, khiến nó chạy thêm ngoài Spring Security hoặc nhiều lần. Khi cần inject dependency qua bean, phải chủ động vô hiệu hóa servlet registration cho bean filter đó (ví dụ dùng FilterRegistrationBean với setEnabled(false)), rồi đăng ký nó trong security chain phù hợp.

**addFilterBefore/addFilterAfter** chỉ định vị trí filter tương đối. **addFilterAt** không có nghĩa chắc chắn thay thế một filter đã tồn tại ở cùng vị trí; cần đọc API semantics và kiểm tra danh sách thực tế. Mọi custom filter phải gọi chain.doFilter(request, response) nếu muốn request tiếp tục; có thể chủ động chặn nhưng phải có quy tắc rõ ràng.

## 7. Những tình huống lỗi cần nhận biết

### 7.1. Chain bao quát đặt trước chain cụ thể

~~~java
@Order(1) // Sai ý định nếu chain này khớp mọi request
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .build();
}
~~~

Nếu chain trên đứng trước một chain /api/**, FilterChainProxy sẽ chọn webChain cho cả /api/status. HTTP Basic filter chỉ có trong chain API sẽ không xử lý credential như mong đợi. Khắc phục bằng thứ tự @Order hợp lý: chain API chuyên biệt trước, chain fallback sau.

### 7.2. Không có fallback

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
}
~~~

Khi tự khai báo SecurityFilterChain, không được giả định Boot vẫn tự thêm một chain mặc định bảo vệ tất cả URL. Trong trường hợp ví dụ chỉ có chain API, /dashboard và /admin không khớp nó nên có nguy cơ **không được bảo vệ bởi Spring Security**. Hãy tạo fallback có chủ đích và kiểm tra các endpoint không nằm trong /api/**.

### 7.3. Nghĩ permitAll là bỏ qua toàn bộ filter

Cho phép /public/** không có nghĩa là toàn bộ kiểm tra filter được bỏ qua. Một filter nằm trước AuthorizationFilter vẫn có thể tác động hoặc từ chối request. Kiểm tra log và filter chain để hiểu lý do một public endpoint nhận 401/403.

### 7.4. Lấy tên lớp filter làm bằng chứng rằng tính năng đã bật

Tên FilterChainProxy hoặc SecurityFilterChain trong ứng dụng không chứng minh Bearer, Basic hay form login có mặt. Cần nhìn vào cấu hình HttpSecurity và danh sách filter được tạo. Chẳng hạn dùng requestMatchers("/api/**") trong authorizeHttpRequests không tự tạo BasicAuthenticationFilter.

### 7.5. Filter bị chạy hai lần

Một filter vừa được servlet container đăng ký, vừa được thêm bằng addFilterBefore vào SecurityFilterChain có thể chạy ngoài ý muốn. Xác minh phạm vi đăng ký, servlet FilterRegistrationBean và danh sách filter Spring Security. Với OncePerRequestFilter, logic “once per request dispatch” không phải lý do để đăng ký trùng filter ở hai nơi.

### 7.6. Đường dẫn, Servlet mapping và dispatcher type khác tưởng tượng

Đừng chỉ nhìn URL hiện ra trong browser rồi suy ra mọi RequestMatcher chắc chắn khớp. Context path, servletPath, cách MVC matcher được chọn, reverse proxy và các dispatcher type ERROR/FORWARD/ASYNC có thể tác động tới đường đi của request. Khi dùng nhiều Servlet hoặc custom RequestMatcher, viết kiểm thử cho các path thật, các method và cả case biên như /api, /api/, /api/v1/... nếu chúng quan trọng với bảo mật.

### 7.7. 401, 403 hoặc redirect sai kỳ vọng

API HTTP Basic thiếu credential thường trả 401 và WWW-Authenticate; web formLogin chưa đăng nhập thường redirect tới /login. Nếu request đáng lẽ là API mà bị redirect, hãy kiểm tra chain đã được chọn trước khi debug mật khẩu. Request đã xác thực nhưng thiếu quyền thường trả 403; thiếu CSRF token ở phương thức thay đổi dữ liệu cũng có thể trả 403.

### 7.8. Lẫn lộn CORS với chain matching

CORS preflight (OPTIONS) trong API cross-origin có thể được browser gửi không kèm cookie hoặc Authorization như request thật. Một API muốn nhận request cross-origin cần cấu hình CORS phù hợp và sắp xếp xử lý preflight trước các bước authentication có thể chặn nó. Đừng chữa lỗi CORS bằng cách mở toàn bộ /api/** thành permitAll hoặc tắt security không kiểm soát.

## 8. Cách kiểm thử matching và filter list

Khi thay cấu hình chain, lập ma trận request nhỏ nhưng bao quát vùng nhạy cảm:

| Đầu vào | Chain phải được chọn | Điều cần khẳng định |
| --- | --- | --- |
| GET /api/status không Authorization | API | Nhận challenge Basic, không redirect web login |
| GET /api/status có Basic hợp lệ | API | Xác thực qua Basic và được role USER cho phép |
| GET /api/unknown có Basic hợp lệ | API | Bị denyAll; không chạy controller |
| GET /dashboard không session | Web fallback | Chuyển sang form login |
| GET /dashboard có session đăng nhập | Web fallback | Cho truy cập sau authorization |
| GET /public/ping không session | Web fallback | Được permitAll nhưng vẫn đi qua chain |
| GET /unexpected-admin không session | Web fallback | Không bị rơi khỏi Spring Security do thiếu fallback |

Ngoài kiểm tra HTTP status, cần kiểm tra log chain matcher/filter trong môi trường dev hoặc dùng integration test. Khi có Spring Security test dependency, có thể viết MockMvc test với mock user, Basic header và request mong đợi; lưu ý mock user dùng để kiểm tra authorization, **không chứng minh BasicAuthenticationFilter thực sự xác thực HTTP header**. Muốn kiểm thử toàn bộ luồng HTTP Basic, gửi request chứa Basic credential thật trong môi trường test có cấu hình UserDetailsService như ví dụ.

Một nguyên tắc thực tế: khi thêm endpoint mới, kiểm tra **chain nào nhận nó, filter nào thực thi, rồi luật authorization nào quyết định**. Ba câu hỏi này đi theo đúng thứ tự xử lý request và giúp phát hiện cả lỗ hổng ngoài phạm vi chain lẫn lỗi quyền trong chain.

## 9. Tự kiểm tra

1. Nếu có @Order(1) là fallback mọi request và @Order(2) là API /api/**, request /api/status vào chain nào? Vì sao?
2. Vì sao một request /api/orders không được requestMatchers(HttpMethod.GET, "/api/status") cho phép vẫn có thể đi qua BasicAuthenticationFilter của API chain?
3. Sự khác biệt giữa securityMatcher("/api/**") và requestMatchers("/api/**").permitAll() là gì?
4. Vì sao cần phân biệt thứ tự các SecurityFilterChain với thứ tự các filter trong một chain?
5. Khi một API nhận redirect 302 tới /login dù bạn cấu hình httpBasic cho API, cần kiểm tra bước nào đầu tiên?
6. Vì sao dùng ignoring() cho URL công khai có thể bỏ qua những bảo vệ mà permitAll vẫn duy trì?
7. Custom filter vừa là Servlet bean vừa được thêm vào apiChain có thể gây hành vi gì?
8. Làm thế nào chứng minh endpoint /admin không bị bỏ ngoài Spring Security khi đã tạo một SecurityFilterChain chỉ khớp /api/**?

Kết luận kỹ thuật cần ghi nhớ: **FilterChainProxy chọn SecurityFilterChain đầu tiên có matcher khớp request; chain đó quyết định danh sách filter; cuối cùng các filter xác thực, CSRF và phân quyền quyết định request được tiếp tục hay bị chặn.**