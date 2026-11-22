# FilterChainProxy và vai trò điều phối các chuỗi bảo mật

Trong **Spring Security cho ứng dụng Servlet**, `FilterChainProxy` là thành phần trung tâm chọn **một chuỗi bộ lọc bảo mật** (`SecurityFilterChain`) cho từng yêu cầu HTTP, rồi chạy các security filter thuộc chuỗi đã chọn. Đây là điểm nối giữa cơ chế `Filter` của Servlet container và nhiều cấu hình bảo mật của Spring Security.

Bài này giải thích vị trí của `FilterChainProxy`, cách nó chọn chuỗi theo thứ tự, cách bộ lọc thực thi, mối quan hệ với rule phân quyền và cách kiểm chứng bằng ví dụ. Hiểu được cơ chế này sẽ giúp tránh hai lỗi nguy hiểm: cấu hình một chuỗi không bao phủ endpoint cần bảo vệ, hoặc để một chuỗi quá rộng che khuất chuỗi chuyên biệt.

## 1. Bốn thành phần và trách nhiệm khác nhau

| Thành phần | Thuộc tầng nào? | Trách nhiệm chính |
| --- | --- | --- |
| `FilterChain` của Servlet container | Servlet API | Gọi tuần tự các servlet filter đã đăng ký; cuối cùng có thể chuyển yêu cầu đến servlet, chẳng hạn `DispatcherServlet`. |
| `DelegatingFilterProxy` | Spring Web / cầu nối | Là một servlet `Filter` được container gọi, nhưng ủy quyền xử lý cho bean `Filter` trong Spring `ApplicationContext`. |
| `FilterChainProxy` | Spring Security | Giữ danh sách các `SecurityFilterChain`, tìm chuỗi đầu tiên khớp request, điều phối các filter của chuỗi đó và phối hợp với `HttpFirewall`. |
| `SecurityFilterChain` | Spring Security | Định nghĩa matcher của một chuỗi và danh sách security filter sẽ chạy nếu chuỗi được chọn. |

Trong cấu hình Spring Security Servlet thông thường, bean có tên **`springSecurityFilterChain`** là `FilterChainProxy`. `DelegatingFilterProxy` được đăng ký ở phía servlet container và ủy quyền vào bean này. Spring Boot thường thiết lập phần đăng ký giúp ứng dụng khi Spring Security có mặt; ứng dụng Servlet không dùng Boot có thể cần đăng ký `DelegatingFilterProxy` qua cấu hình Servlet/WebApplicationInitializer.

Luồng xử lý khái quát:

~~~text
HTTP request
    |
    v
Servlet container filter chain
    |
    v
DelegatingFilterProxy
    |  tìm và ủy quyền đến bean "springSecurityFilterChain"
    v
FilterChainProxy
    |  HttpFirewall kiểm tra / bọc request
    |  duyệt các SecurityFilterChain theo thứ tự
    |  chọn CHUỖI ĐẦU TIÊN có matches(request) = true
    v
SecurityFilterChain được chọn
    |
    +--> Security filter 1
    +--> Security filter 2
    +--> ...
    +--> AuthorizationFilter (khi cấu hình tương ứng)
    |
    v
Original Servlet FilterChain còn lại
    |
    v
DispatcherServlet / endpoint
~~~

Sơ đồ diễn tả **đường đi thành công**. Một security filter có quyền dừng xử lý, ghi phản hồi, ném exception hoặc chuyển hướng. Khi đó yêu cầu không nhất thiết đi đến controller. Khi không có `SecurityFilterChain` nào khớp, `FilterChainProxy` tiếp tục đến servlet chain gốc mà không áp dụng danh sách security filter của một security chain; không được mặc nhiên xem request đó đã được Spring Security bảo vệ.

## 2. Vì sao cần một FilterChainProxy thay vì đăng ký từng filter?

Nếu mỗi filter xác thực, CSRF, session, exception handling và authorization được đăng ký độc lập vào Servlet container, việc quản lý thứ tự, phụ thuộc lẫn nhau và phạm vi URL rất khó nhất quán. Spring Security tập trung chúng trong `FilterChainProxy`:

1. **Một điểm điều phối:** Servlet container chỉ cần gọi cầu nối Spring Security; Spring quản lý các filter bên trong.
2. **Thứ tự phù hợp:** Các filter liên quan security chạy theo trình tự mà Spring Security xây dựng, chẳng hạn nạp security context trước khi quyết định authorization.
3. **Nhiều chính sách theo phạm vi:** API có thể dùng HTTP Basic và session stateless, trong khi trang web dùng form login và session, mỗi nhóm thuộc một `SecurityFilterChain`.
4. **Kiểm tra/chuẩn hóa yêu cầu:** `HttpFirewall` xử lý các dạng request path đáng ngờ và cung cấp request thích hợp cho quá trình chọn chuỗi.
5. **Tích hợp Spring:** Filter có thể được cấu hình thông qua `HttpSecurity`, dependency injection và các cơ chế khác của Spring.

Vì thế, **không nên tự đăng ký mọi security filter của Spring Security thành servlet filter riêng**. Chúng vốn được điều phối bởi `FilterChainProxy`. Việc một custom filter vừa là bean `@Component` để Spring Boot tự đăng ký ở container, vừa được thêm bằng `http.addFilterBefore(...)` có thể khiến filter chạy hai lần hoặc ở vị trí không mong muốn.

`FilterChainProxy` không thay thế Servlet container, không tự ánh xạ controller và không tự quyết định ai có quyền truy cập endpoint. Nó chọn **chuỗi filter**; quyết định có cho phép một hành động cụ thể thuộc những bộ lọc như `AuthorizationFilter` và các thành phần xác thực.

## 3. Cơ chế chọn SecurityFilterChain: khớp đầu tiên

Mỗi `SecurityFilterChain` có phương thức `matches(HttpServletRequest)` và danh sách filter tương ứng. Xét ba chuỗi đã được sắp xếp:

~~~text
1. apiChain       matcher: /api/**
2. adminChain     matcher: /admin/**
3. fallbackChain  matcher: any request
~~~

Khi request là `GET /api/orders`, `FilterChainProxy`:

1. Kiểm tra matcher của `apiChain` → **true**.
2. Chọn **apiChain** ngay lập tức.
3. Không xét tiếp `adminChain` hay `fallbackChain` để ghép thêm filter.
4. Thực thi các filter của `apiChain` theo thứ tự.

Khi request là `GET /reports`, hai chuỗi đầu không khớp; chuỗi fallback khớp và được chọn. Khi hai matcher chồng lấn, **chỉ chuỗi khớp đầu tiên** được dùng, không chạy hợp nhất các filter từ mọi chuỗi phù hợp.

Có thể xem cơ chế chọn chuỗi theo giả mã:

~~~java
// Giả mã minh họa hành vi chọn chain; không phải mã nguồn nội bộ.
for (SecurityFilterChain candidate : securityFilterChainsInOrder) {
    if (candidate.matches(request)) {
        executeCandidateFilters(candidate, request, originalServletChain);
        return;
    }
}
continueOriginalServletChain(request);
~~~

`executeCandidateFilters` và `continueOriginalServletChain` ở đây chỉ là tên mô tả, **không phải API có thể gọi trực tiếp**. Thực tế `FilterChainProxy` tạo cơ chế chuyển tiếp nội bộ qua danh sách filter, chẳng hạn dạng `VirtualFilterChain`.

### Mô phỏng bằng Java 17 độc lập

Ví dụ sau mô phỏng riêng nguyên tắc "first matching chain wins", có thể biên dịch mà không cần Spring. Hàm `startsWith` chỉ phục vụ mô phỏng; **không dùng logic chuỗi tự viết này để thay thế RequestMatcher trong ứng dụng bảo mật thực tế**.

~~~java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchingChainDemo {
    record Candidate(String name, Predicate<String> matcher) {}

    public static void main(String[] args) {
        List<Candidate> chains = List.of(
                new Candidate("apiChain",
                        path -> path.equals("/api") || path.startsWith("/api/")),
                new Candidate("fallbackChain", path -> true)
        );

        for (String path : List.of(
                "/api/public/ping", "/api/private", "/api2/private", "/dashboard")) {

            String selected = "NO CHAIN";
            for (Candidate chain : chains) {
                if (chain.matcher().test(path)) {
                    selected = chain.name();
                    break;
                }
            }
            System.out.println(path + " -> " + selected);
        }
    }
}
~~~

Lưu mã vào `FirstMatchingChainDemo.java`, chạy:

~~~bash
javac FirstMatchingChainDemo.java
java FirstMatchingChainDemo
~~~

Stdout chính xác:

~~~text
/api/public/ping -> apiChain
/api/private -> apiChain
/api2/private -> fallbackChain
/dashboard -> fallbackChain
~~~

Nếu đưa fallback lên đầu danh sách thì mọi đường dẫn đều chọn fallback, khiến apiChain không bao giờ được chọn. Đây chính là lỗi thứ tự thường gặp khi cấu hình nhiều `SecurityFilterChain`.

## 4. Tạo hai chuỗi bảo mật bằng HttpSecurity

Ví dụ dưới đây áp dụng cho **Spring Boot 3.x, Spring Security 6.x, Jakarta Servlet và Java 17+**; đây là mã đặt trong dự án Spring Boot, không thể chạy chỉ với `javac` nếu thiếu dependency Spring. API sử dụng HTTP Basic và session stateless; trang web có form login.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FilterChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().hasRole("API_USER"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/help").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Hai `HttpSecurity` dẫn đến hai `SecurityFilterChain` độc lập.** `@Order(1)` được xét trước `@Order(2)`. Chain API chỉ có hiệu lực cho đường dẫn phù hợp `/api/**`. Chain web **không gọi `securityMatcher(...)`**, vì vậy mặc định khớp bất kỳ request nào chưa được chain trước chọn, tạo fallback rõ ràng.

Ví dụ URL (giả sử context path rỗng, servlet mapping thông thường và các endpoint tương ứng tồn tại):

| Request | Chain được chọn | Quy tắc trong chain | Hành vi dự kiến nếu chưa xác thực |
| --- | --- | --- | --- |
| `GET /api/public/ping` | `apiChain` | `permitAll()` | Vào endpoint; thường trả `200` nếu controller xử lý thành công. |
| `GET /api/private` | `apiChain` | `hasRole("API_USER")` | HTTP Basic entry point thường trả `401`. |
| `GET /dashboard` | `webChain` | `authenticated()` | Form login thường chuyển hướng `302` đến trang đăng nhập. |
| `GET /help` | `webChain` | `permitAll()` | Vào endpoint công khai. |
| `GET /api2/private` | `webChain` | `authenticated()` | Không thuộc pattern `/api/**`. |

Với `hasRole("API_USER")`, mặc định Spring Security kiểm tra authority `ROLE_API_USER`. Nếu muốn kiểm tra một authority đúng tên, có thể dùng `hasAuthority("...")` với tên phù hợp. Authentication provider và tài khoản người dùng phải được cấu hình cho môi trường thật; Spring Boot có thể cung cấp user mặc định dành cho phát triển khi chưa khai báo authentication thích hợp.

**Điểm quan trọng về mặc định:** Khi ứng dụng tự khai báo một hoặc nhiều bean `SecurityFilterChain`, đừng dựa vào việc Spring Boot sẽ tự bổ sung chain mặc định bảo vệ toàn bộ request. Trong cấu hình thông thường, auto-configuration tạo chain mặc định sẽ nhường cho cấu hình của ứng dụng. Cần tự bảo đảm mọi endpoint cần bảo vệ đều được bao phủ.

### SecurityMatcher và requestMatchers khác nhau thế nào?

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

- `securityMatcher("/api/**")` trả lời: **chuỗi này có được chọn cho request hay không?**
- `requestMatchers("/api/public/**")` và `requestMatchers("/api/admin/**")` trả lời: **trong chuỗi đã chọn, chính sách quyền nào áp dụng?**
- `anyRequest()` là fallback **trong chuỗi ấy**; không làm `SecurityFilterChain` mở rộng phạm vi ra ngoài `/api/**`.

Có hai loại "khớp đầu tiên" riêng biệt: `FilterChainProxy` chọn **SecurityFilterChain đầu tiên** phù hợp; còn `authorizeHttpRequests` áp dụng **quy tắc authorization đầu tiên** phù hợp trong chuỗi đã chọn. Đặt `requestMatchers("/api/**").permitAll()` trước rule `/api/admin/**` sẽ khiến rule admin bị che khuất bên trong cùng chain, dù FilterChainProxy đã chọn đúng chain.

Các matcher có thể xem HTTP method và thông tin request khác, tùy loại `RequestMatcher`. Matcher kiểu MVC, kiểu `PathPattern` và kiểu Ant ở các thế hệ Spring Security khác nhau không có semantics hoàn toàn giống nhau; đặc biệt khi custom servlet path, nên xác định loại matcher và kiểm thử đường dẫn đúng như ứng dụng nhận được.

## 5. Bên trong chuỗi đã chọn: thứ tự filter và chuyển tiếp

Khi `FilterChainProxy` đã chọn một `SecurityFilterChain`, nó gọi lần lượt các security filter của chuỗi thông qua `FilterChain` nội bộ. Mỗi filter có cấu trúc khái quát:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Xử lý trước khi chuyển tiếp.
    chain.doFilter(request, response);
    // Xử lý sau khi filter/servlet tiếp theo quay về.
}
~~~

Đây là **mẫu minh họa phương thức Servlet Filter**, cần các import `jakarta.servlet.*` và lớp triển khai `Filter`. Một filter có thể không gọi `chain.doFilter(...)` nếu nó tự xử lý phản hồi hoặc từ chối request.

Một số bộ lọc thường gặp trong cấu hình Spring Security 6.x (danh sách thực tế thay đổi theo các tính năng bật và version):

| Bộ lọc | Ý nghĩa trong luồng |
| --- | --- |
| `SecurityContextHolderFilter` hoặc cơ chế quản lý context tương ứng | Đặt security context cho request để các thành phần phía sau truy cập thông tin security nhất quán. |
| `CsrfFilter` | Kiểm tra CSRF token ở những request cần bảo vệ CSRF. |
| `UsernamePasswordAuthenticationFilter` | Xử lý form login khi được cấu hình. |
| `BasicAuthenticationFilter` | Đọc thông tin xác thực HTTP Basic khi được cấu hình. |
| `ExceptionTranslationFilter` | Chuyển các `AuthenticationException`/`AccessDeniedException` phát sinh ở những filter phía sau thành quy trình authentication entry point hoặc access denied handler thích hợp. |
| `AuthorizationFilter` | Thực thi quyết định authorization cho request theo cấu hình `authorizeHttpRequests`. |

Bảng là mô tả **vai trò**, không khẳng định mọi filter đều tồn tại trong mọi chain hay thứ tự bảng chính là thứ tự thực thi đầy đủ. Các bộ lọc xác thực, exception handling và authorization phải được đặt theo thứ tự thích hợp do Spring Security cung cấp; không tùy tiện thay thứ tự bằng đăng ký Servlet filter thủ công.

Một filter làm nhiệm vụ kiểm tra thường phải gọi `chain.doFilter(...)` để phần còn lại được chạy. Ngược lại, nếu xác thực thất bại hoặc authorization bị từ chối, một filter có thể kích hoạt entry point/handler, ghi response và dừng quá trình. Do đó:

- `401 Unauthorized` thường có nghĩa request cần thông tin xác thực nhưng chưa được xác thực theo cơ chế phù hợp.
- `403 Forbidden` thường biểu thị yêu cầu đã qua mức xác thực cần thiết nhưng không đủ quyền, hoặc bị từ chối bởi một cơ chế khác như CSRF.
- `302 Found` có thể là redirect đến trang form login; đây là hành vi thường gặp của một chain dùng `formLogin()`.

Không suy ngược **chỉ từ status code** rằng `FilterChainProxy` đã chọn chain nào. Ví dụ `403` có thể do `CsrfFilter` dừng request trước khi rule authorization được thực thi. Cần kết hợp logging và test để xác định nguyên nhân.

### Vì sao permitAll không có nghĩa bỏ qua chain?

Nếu `/api/public/ping` khớp `apiChain` rồi rule `permitAll()`, `FilterChainProxy` **vẫn chạy chuỗi security filter được chọn**. Filter security headers, CSRF, session/context hoặc custom filter vẫn có thể tham gia tùy cấu hình; chỉ quyết định authorization của rule ấy là cho phép.

Ngược lại, `WebSecurityCustomizer` với `web.ignoring().requestMatchers(...)` loại đường dẫn khỏi cơ chế filter bảo mật (thường dành cho tài nguyên thực sự không cần security processing). Không nhầm `ignoring()` với `permitAll()`: đường dẫn bị bỏ qua sẽ không nhận các tính năng security của chain. Đối với endpoint public vẫn cần security headers, thường ưu tiên cấu hình `permitAll()` trong một chain phù hợp.

## 6. HttpFirewall làm gì trước khi chọn chuỗi?

`FilterChainProxy` kết hợp với `HttpFirewall` (mặc định phổ biến là `StrictHttpFirewall`) để kiểm tra và bọc request trước khi chọn chain. Mục đích là tránh các cách biểu diễn đường dẫn bất thường khiến security matcher và MVC/Servlet routing hiểu khác nhau.

Ví dụ đường dẫn có dấu chấm phẩy, segment đáng ngờ hoặc ký tự mã hóa không được phép có thể bị firewall từ chối bằng `RequestRejectedException` trước khi đi đến controller. Những trường hợp cụ thể được từ chối phụ thuộc cấu hình firewall, servlet container và phiên bản Spring Security. Sau quá trình xử lý, các request/response wrapper có thể được dọn dẹp, trả lại trạng thái thích hợp cho các servlet filter còn lại.

Điều cần làm khi request bị chặn: kiểm tra URL gốc, chính sách proxy, log lỗi và quy tắc firewall. **Không vô hiệu hóa hàng loạt kiểm tra firewall chỉ để làm một URL bất thường chạy được**; nếu cần cấu hình ngoại lệ, cần hiểu rõ rủi ro và kiểm thử các đường dẫn tương đương.

## 7. Thêm một custom filter mà không chạy hai lần

Một nhu cầu thực tế là thêm filter đo thời gian/ghi vết cho chain API. Có thể triển khai bằng `OncePerRequestFilter`, sau đó thêm instance của filter vào `HttpSecurity` ở vị trí rõ ràng. Ví dụ sau không dùng `@Component` trên filter để tránh Spring Boot tự đăng ký thêm filter ở cấp servlet container:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiTimingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ApiTimingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMillis =
                    (System.nanoTime() - started) / 1_000_000;
            log.debug("API {} {} completed in {} ms",
                    request.getMethod(),
                    request.getRequestURI(),
                    elapsedMillis);
        }
    }
}
~~~

Chèn filter này vào chain API đã định nghĩa ở mục 4 bằng lời gọi sau **trước `return http.build()`**:

~~~java
http.addFilterBefore(
        new ApiTimingFilter(),
        org.springframework.security.web.access.intercept.AuthorizationFilter.class
);
~~~

Đây là ví dụ chèn trước một filter có vị trí thứ tự đã được Spring Security biết đến. Trong thực tế, vị trí chèn phải được chọn theo thông tin custom filter cần: trước authentication thường chưa có principal; sau authentication có thể dùng context đã xác thực; trước authorization có thể quan sát request trước khi bị chặn. Nếu cấu hình một authentication mechanism khác, cần xác minh các filter và thứ tự thật sự được xây dựng.

**Lưu ý về `OncePerRequestFilter`:** tên gọi đề cập đến bảo đảm trong một lần filter dispatch phù hợp, không có nghĩa một HTTP request về mặt nghiệp vụ chỉ có thể qua filter đúng một lần trong mọi cơ chế async/error dispatch, proxy và đăng ký lặp. Nếu filter là Spring bean do DI quản lý và Boot có thể tự đăng ký nó ở servlet container, hãy cấu hình `FilterRegistrationBean` để vô hiệu hóa đăng ký container cho filter đó khi định dùng riêng trong security chain.

Không ghi Authorization header, bearer token, password, cookie hay dữ liệu bí mật vào log. `getRequestURI()` có thể chứa thông tin nhạy cảm trong path ở một số ứng dụng, nên tùy chính sách log thực tế.

## 8. Kiểm thử chuỗi được chọn

Để ví dụ Spring ở mục 4 có endpoint thực, thêm controller minh họa trong cùng ứng dụng:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/private")
    public String privateApi() {
        return "private";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }

    @GetMapping("/help")
    public String help() {
        return "help";
    }
}
~~~

Trong dự án có `spring-boot-starter-test`, `spring-security-test` và cấu hình MockMvc tích hợp Spring Security, kiểm tra các nhánh hành vi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterChainRoutingTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void firstMatchingChainControlsBehavior() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/private")
                        .with(user("reader").roles("API_USER")))
                .andExpect(status().isOk());

        mockMvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Các assertions dựa trên **chính cấu hình hai chain, controller minh họa, request GET chưa xác thực và MockMvc thực sự có Spring Security filter**. Khi có thêm filter, entry point tùy biến, context path, controller behavior hoặc exception handler, trạng thái có thể khác; cập nhật test theo hợp đồng của ứng dụng. Với yêu cầu `POST/PUT/DELETE`, cần xử lý CSRF đúng cách trong test: API stateless hoặc `permitAll()` không tự vô hiệu hóa `CsrfFilter`.

Có thể thử bằng `curl` sau khi chạy ứng dụng Spring Boot:

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/private
curl -i http://localhost:8080/dashboard
~~~

Ở cấu hình minh họa, request đầu thường `200` với body `pong`; request thứ hai thường `401` (HTTP Basic); request thứ ba thường `302` hướng tới form login. Đây là dự kiến có điều kiện, không phải stdout từ chương trình Java độc lập.

### Đọc log khi chọn sai chain

Khi cần chẩn đoán, bật log ở môi trường phát triển hoặc test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Tùy phiên bản, các dòng log có thể cho thấy request nào được bảo vệ, filter nào được gọi hoặc thông tin authorization. Không viết assertion phụ thuộc câu chữ log nội bộ: thông điệp log có thể thay đổi giữa các phiên bản.

Lần lượt kiểm tra: đường dẫn đến ứng dụng **sau reverse proxy**, servlet context/servlet mapping, HTTP method, loại `RequestMatcher`, thứ tự `SecurityFilterChain`, matcher `securityMatcher`, sau đó mới xem các rule `requestMatchers` trong chain. Khi xảy ra 401/403, kiểm tra cả authentication entry point, exception handling và CSRF.

## 9. Những lỗi cấu hình cần nhận diện

### Lỗi A: Chỉ có chain API, thiếu fallback

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}
~~~

Với cấu hình chỉ có bean ở trên, request `/admin/panel` không khớp `/api/**`; `FilterChainProxy` không áp dụng security filter nào từ chain này. Nếu không còn chain khác, endpoint đó **không được bảo vệ bởi Spring Security filter chain**, dù trong cấu hình có `anyRequest().authenticated()`. Phải thêm fallback phù hợp hoặc thiết kế một chain bảo vệ toàn ứng dụng.

### Lỗi B: Chain rộng đứng trước chain hẹp

~~~java
// Dạng thiết kế sai về thứ tự:
@Order(1)  // chain có matcher any request
@Order(2)  // chain chỉ có matcher /api/**
~~~

Đoạn trên là **giả mã chú thích**, không phải Java class hợp lệ. Chain thứ nhất luôn được chọn; chain API phía sau không có cơ hội chạy. Đặt chain chuyên biệt trước và chain fallback cuối, rồi viết test xác nhận những URL thuộc cả hai phạm vi.

### Lỗi C: Đặt rule quyền của một URL ngoài phạm vi chain

~~~text
securityMatcher("/api/**")
    authorize:
        /admin/** -> hasRole("ADMIN")
        anyRequest -> authenticated()
~~~

Với endpoint `/admin/users` nằm ngoài `/api/**`, rule `/admin/**` trong chain API không có tác dụng vì chain đó chưa bao giờ được chọn. Sửa ở phạm vi chọn chain hoặc bố trí chain khác có rule tương ứng.

### Lỗi D: Tưởng permitAll bỏ qua security filter

`permitAll()` chỉ thay đổi quyết định authorization theo rule đã chọn. Nó không đảm bảo CSRF, custom filter hoặc chính sách HTTP khác ngừng hoạt động. Ví dụ một request `POST` đến URL public có thể vẫn trả `403` vì thiếu CSRF token khi CSRF protection có hiệu lực.

### Lỗi E: Đăng ký cùng custom filter hai nơi

Thêm custom filter vào security chain và đồng thời để Boot auto-register nó là servlet filter độc lập có thể gây xử lý lặp, log lặp hoặc không đúng vị trí mong muốn. Chọn rõ cơ chế đăng ký. Nếu cần filter ở cấp container, hiểu ảnh hưởng của nó đến mọi request, bao gồm request nằm ngoài chain bảo mật.

### Lỗi F: Tự sửa URL hoặc nới firewall để matcher khớp

Nếu matcher không khớp vì context path, servlet mapping, proxy rewrite hoặc URL encoding, hãy xác định **request thực tế** và dùng matcher phù hợp. Tránh tự cắt path, decode tùy tiện hoặc tắt `StrictHttpFirewall` trên diện rộng.

## 10. Bài tập tự kiểm tra

**Bài 1.** Các chain theo thứ tự: `apiChain("/api/**")`, `healthChain("/actuator/health")`, `fallbackChain(any)`. Request `/actuator/health` vào chuỗi nào?

**Đáp án:** `healthChain`. Chain API không khớp, healthChain khớp và dừng việc tìm kiếm, không chạy filter của fallbackChain. Nếu đặt fallbackChain lên đầu, kết quả sẽ thành fallbackChain.

**Bài 2.** Chỉ có `securityMatcher("/api/**")`, bên trong `anyRequest().denyAll()`. Request `/reports` có bị rule `denyAll()` đó chặn không?

**Đáp án:** Không, vì chain không khớp request. `denyAll()` chỉ có hiệu lực trong chain đã được chọn. Nếu không có chain khác, Spring Security không thực thi rule đó cho `/reports`.

**Bài 3.** Request `POST /api/public/orders` khớp `apiChain` có `permitAll()`, nhưng trả `403`. Có thể do đâu?

**Đáp án:** Có thể do CSRF token thiếu hoặc không hợp lệ khi `CsrfFilter` được bật, cũng có thể do filter khác hoặc cấu hình cụ thể. `permitAll()` không loại bỏ toàn bộ security filter, nên kiểm tra filter chain thực tế và log trước khi kết luận matcher sai.

**Bài 4.** Một custom filter được khai báo `@Component` và cũng thêm vào chain qua `addFilterBefore`. Vì sao log có thể xuất hiện hai lần?

**Đáp án:** Spring Boot có thể đăng ký bean Filter trực tiếp với Servlet container, trong khi Spring Security cũng gọi filter đó trong chain của mình. Cần tránh đăng ký lặp hoặc tắt auto-registration ở cấp container nếu chỉ muốn filter nằm trong một security chain.

**Bài 5.** Hai `SecurityFilterChain` đều khớp `/api/private`. Có phải các filter của cả hai chain đều chạy không?

**Đáp án:** Không. `FilterChainProxy` chọn chain đầu tiên khớp theo thứ tự và chỉ chạy danh sách filter của chain đó.

## 11. Checklist khi đọc hoặc thiết kế kiến trúc filter

- Tìm `DelegatingFilterProxy` / bean `springSecurityFilterChain` và biết nó đưa request vào `FilterChainProxy` ở đâu.
- Liệt kê tất cả các bean `SecurityFilterChain` cùng thứ tự `@Order` và `securityMatcher` của từng chain.
- Đảm bảo chain cụ thể đứng trước chain rộng; kiểm tra rõ có fallback bao phủ những endpoint cần bảo vệ.
- Phân biệt **chọn chain** với **chọn rule authorization**; cả hai đều dựa trên thứ tự nhưng ở hai tầng khác nhau.
- Xem từng filter được bật và vị trí của custom filter; không đăng ký trùng giữa Servlet container và Spring Security.
- Kiểm thử URL khớp/không khớp, method, quyền, CSRF, context path, proxy và cơ chế phản hồi 401/403/302.
- Dùng logging có kiểm soát, giữ `HttpFirewall` phù hợp, không suy luận bảo mật chỉ từ một mã trạng thái.

**Ghi nhớ:** `DelegatingFilterProxy` là cầu nối, `FilterChainProxy` là người **chọn và điều phối chuỗi**, `SecurityFilterChain` chứa những filter sẽ được thực thi, còn các filter như `AuthorizationFilter` mới đưa ra quyết định phân quyền theo quy tắc đã cấu hình. Mô hình này giải thích vì sao **thứ tự chain và phạm vi matcher là một phần cốt lõi của an toàn ứng dụng Servlet**.