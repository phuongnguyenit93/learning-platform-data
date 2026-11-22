# Spring Security trong ứng dụng Servlet: phạm vi và các vấn đề cần giải quyết

## 1. Bài học này giải đáp điều gì?

Trong một ứng dụng Java chạy trên **Servlet stack** (ví dụ Spring Boot dùng Spring MVC và Tomcat), mỗi HTTP request có thể đi tới controller, service và dữ liệu. Nếu không có lớp bảo vệ, ứng dụng khó trả lời nhất quán các câu hỏi: *Ai đang gọi? Họ được phép làm gì? Danh tính đó được duy trì ra sao giữa các request? Làm thế nào chặn một request độc hại trước khi nghiệp vụ chạy?*

**Spring Security** là framework bảo mật tích hợp vào Spring, cung cấp các cơ chế xác thực (authentication), phân quyền (authorization) và các lớp phòng vệ web phổ biến. Với Servlet, điểm tích hợp quan trọng nhất là **chuỗi Servlet Filter** bao quanh quá trình xử lý request. Spring Security không tự động biến mọi ứng dụng thành an toàn tuyệt đối: chính sách phân quyền, thiết kế dữ liệu, bảo vệ bí mật, cấu hình hạ tầng và kiểm thử vẫn là trách nhiệm của ứng dụng.

Sau bài này, bạn cần có thể:

- Phân biệt xác thực, phân quyền và bảo vệ HTTP request; xác định phần việc của Spring Security so với Servlet container và business layer.
- Giải thích được đường đi của request qua `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain` tới Spring MVC.
- Nhận diện các vấn đề thường gặp: endpoint công khai/riêng tư, quyền theo vai trò, phiên đăng nhập, CSRF, CORS, xử lý 401/403 và cấu hình nhiều filter chain.
- Thiết lập một chính sách bảo vệ tối thiểu cho ứng dụng Spring Boot Servlet, đồng thời hiểu những giới hạn của ví dụ.

## 2. Phạm vi của Spring Security trên Servlet stack

Servlet container (Tomcat, Jetty...) tiếp nhận kết nối HTTP, thực thi Servlet Filter và điều phối tới servlet, thường là `DispatcherServlet` của Spring MVC. Spring Security đăng ký một filter cầu nối với container; các filter bảo mật sẽ xử lý request **trước khi** request đi tới controller theo đường đi thông thường. Vì vậy, một chính sách có thể áp dụng đồng đều cho nhiều endpoint mà không cần viết lại logic xác thực trong từng controller.

Những trách nhiệm điển hình:

| Vấn đề | Spring Security hỗ trợ | Ứng dụng vẫn phải quyết định |
| --- | --- | --- |
| **Authentication**: ai đang gửi request? | Cơ chế đăng nhập, HTTP Basic, tích hợp bearer token, `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext` | Nguồn danh tính, chính sách tài khoản, vòng đời thông tin xác thực |
| **Authorization**: người đó được phép làm gì? | Quy tắc request theo đường dẫn/phương thức, vai trò/quyền, method security khi bật | Quyền thực tế theo nghiệp vụ, sở hữu tài nguyên, tenant, tránh truy cập chéo dữ liệu |
| **Session và security context** | Đọc/ghi/ngữ cảnh xác thực theo từng request, hỗ trợ session, session fixation protection cho các luồng thích hợp | Chọn session, token, thời hạn, đăng xuất, thu hồi và chính sách lưu trữ |
| **Bảo vệ HTTP** | CSRF protection, security headers, hỗ trợ CORS integration, xử lý request bị từ chối | Cấu hình đúng theo frontend/API, TLS, cookie, reverse proxy, rate limiting |
| **Lỗi bảo mật** | Chuyển lỗi xác thực/phân quyền thành challenge, redirect hoặc HTTP 401/403 tùy cấu hình | Định dạng lỗi API, thông báo an toàn, quan sát và audit |

**Ranh giới quan trọng:** Spring Security không thay thế HTTPS/TLS, firewall/WAF, kiểm tra đầu vào, parameterized SQL, output encoding chống XSS, chính sách CORS chính xác, quản lý secret, chống brute-force/rate limit, kiểm toán phân quyền đối tượng hay vá lỗ hổng thư viện. Các biện pháp đó phải phối hợp với framework.

Servlet security và WebFlux security cũng là **hai mô hình khác nhau**. Phần này bàn về `HttpSecurity`, `SecurityFilterChain`, `SecurityContextHolder` và Servlet Filter; không áp dụng nguyên xi cho `ServerHttpSecurity`/`SecurityWebFilterChain` của reactive stack.

## 3. Spring Security đứng ở đâu trong luồng request?

Đường đi khái quát:

```text
HTTP client
    |
Servlet container (Tomcat/Jetty)
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |
    +-- chọn SecurityFilterChain đầu tiên khớp request
           |
           +-- các security filters theo thứ tự do framework quản lý
           |      (context, CSRF, authentication, exception,
           |       authorization... tùy cấu hình)
           |
           +-- tiếp tục Servlet filter chain
                    |
               DispatcherServlet (Spring MVC)
                    |
               Controller -> Service -> Data
```

- **`DelegatingFilterProxy`**: một `javax/jakarta.servlet.Filter` bridge được đăng ký ở servlet container; nó tìm Spring bean có tên thường là `springSecurityFilterChain` và chuyển xử lý tới bean đó. Trên Spring Framework 6/Spring Boot 3, Servlet API dùng namespace `jakarta.servlet`.
- **`FilterChainProxy`**: Spring bean trung tâm chứa một hoặc nhiều `SecurityFilterChain`. Nó chọn **chain đầu tiên có matcher phù hợp** với request. Vì vậy, thứ tự của các chain quan trọng khi cấu hình nhiều chính sách.
- **`SecurityFilterChain`**: danh sách security filter cho một nhóm request. Mỗi filter làm phần việc riêng, chẳng hạn tải security context, xử lý cơ chế xác thực, CSRF, chuyển exception và kiểm tra quyền. Danh sách và thứ tự cụ thể tùy cấu hình/phiên bản; không nên tự giả định mọi request đều đi qua cùng một tập filter.
- **Spring MVC/controller**: chỉ chạy khi request đi tiếp qua lớp bảo mật. Tuy nhiên, nghiệp vụ vẫn phải tự kiểm tra quyền ở mức dữ liệu khi quy tắc URL không đủ diễn đạt.

Các filter của Spring Security là **Servlet Filter**, không phải Spring MVC `HandlerInterceptor`. Vì filter nằm ở lớp HTTP thấp hơn, nó có thể xử lý cả những request chưa được ánh xạ tới controller. Việc dùng `permitAll()` cho một route chỉ bỏ yêu cầu *authorization* tương ứng; request vẫn có thể đi qua các filter bảo mật khác.

### Một chu kỳ xác thực và phân quyền

1. Request đến, framework thiết lập hoặc khôi phục `SecurityContext` theo cách cấu hình.
2. Nếu request mang thông tin xác thực và cơ chế tương ứng được bật, filter xác thực yêu cầu `AuthenticationManager`/`AuthenticationProvider` xác minh thông tin. Kết quả thành công là một `Authentication` đã được xác thực, chứa principal và authorities.
3. Với ứng dụng lưu trạng thái, context có thể được lưu vào kho thích hợp (thường liên quan HTTP session); với API bearer token, xác thực thường được thiết lập từ token cho từng request. Không mặc định hai mô hình có cùng hành vi.
4. Khi tới điểm kiểm tra quyền, Spring Security xét `Authentication` và chính sách `AuthorizationManager` để cho qua hoặc từ chối.
5. Khi kết thúc request, framework dọn security context khỏi ngữ cảnh xử lý thread theo cơ chế của nó để tránh rò rỉ danh tính sang request khác.

`SecurityContextHolder` mặc định sử dụng chiến lược gắn với thread trong mô hình Servlet. Khi tự chuyển việc sang thread khác hoặc xử lý bất đồng bộ, **không** giả định context tự đi theo; cần cơ chế truyền ngữ cảnh được Spring Security hỗ trợ hoặc thiết kế tách biệt rõ ràng.

## 4. Sáu nhóm vấn đề cốt lõi và cách suy nghĩ đúng

### 4.1. Ai đang gọi? — Authentication

Một request **chưa xác thực** thường có ngữ cảnh anonymous hoặc chưa có principal được tin cậy. Một request **đã xác thực** chứa `Authentication` được cơ chế phù hợp chấp nhận. Xác thực có thể dựa trên form login + session, HTTP Basic, bearer token, SSO/OAuth2 Login hoặc cơ chế tùy biến; chọn cái nào phụ thuộc loại client và mô hình tin cậy.

Ví dụ, với HTTP Basic, client gửi username/password đã mã hóa Base64 trong `Authorization` header **mỗi lần request**. Base64 không phải mã hóa bảo mật; luôn cần HTTPS ở môi trường thật. Với form login, ứng dụng thường xác thực một lần rồi lưu trạng thái phiên; cookie session trở thành dữ liệu nhạy cảm cần bảo vệ.

Mật khẩu phải được lưu dưới dạng **hash thích hợp có salt và chi phí tính toán** (ví dụ BCrypt hoặc cơ chế encoder tương đương), không lưu plaintext và không tự sáng tạo thuật toán băm. Spring Security cung cấp `PasswordEncoder`; nó không thay việc xác định chính sách đăng ký, khóa tài khoản, MFA hay vòng đời credential.

### 4.2. Được làm gì? — Authorization

Đăng nhập thành công **không** đồng nghĩa có quyền xem hoặc sửa mọi dữ liệu. Phân quyền có nhiều mức:

- **Request level**: `GET /public` mở; `GET /profile` cần đăng nhập; `/admin/**` cần quyền quản trị.
- **Method level**: `@PreAuthorize` có thể bảo vệ service method sau khi bật `@EnableMethodSecurity`. Annotation không tự hoạt động chỉ vì có starter security.
- **Object/tenant level**: người dùng A chỉ xem được hóa đơn của A; kiểm tra này thường cần truy vấn/điều kiện domain cụ thể, chẳng hạn `invoice.ownerId == currentUserId`. `hasRole("USER")` không giải quyết được quyền sở hữu dữ liệu.

Một `GrantedAuthority` là chuỗi quyền thực tế. Theo quy ước mặc định, `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`; `hasAuthority("invoice:read")` so khớp authority chính xác đó. Role và permission không nên bị trộn chỉ vì cách đặt tên giống nhau.

**Chính sách mặc định hợp lý:** cho phép công khai đúng các route được chỉ định, yêu cầu xác thực/phân quyền cho phần còn lại, và có quy tắc cuối rõ ràng. Nếu nhiều chain tùy biến mà không có chain nào khớp một request, request đó có thể không được Spring Security bảo vệ: đây là lỗi cấu hình đáng kiểm tra.

### 4.3. Giữ danh tính ra sao? — Session, token và logout

- **Session-based web app**: server lưu trạng thái gắn với session ID; browser gửi cookie session. Cần cookie `Secure`, `HttpOnly`, `SameSite` phù hợp, TLS, session timeout và xử lý session fixation. Session fixation protection không thay thế việc bảo vệ cookie.
- **Stateless API**: client thường gửi bearer token mỗi request; server kiểm tra token thay vì tin vào session login của browser. Phải kiểm tra issuer, audience, signature, expiry và các ràng buộc phù hợp với định dạng token/cơ chế xác thực. Không coi một JWT tự giải mã là đã được xác thực.
- **Logout**: xóa session có hiệu quả với phiên server, nhưng không đồng nghĩa mọi access token đã phát hành đều bị thu hồi. Chiến lược thu hồi phụ thuộc kiểu token và hệ thống danh tính.

`SecurityContextHolder` là cách code đang chạy truy cập thông tin bảo mật hiện thời; bản thân nó **không** phải cơ sở dữ liệu người dùng hay kho session vĩnh viễn.

### 4.4. Request do browser gửi có thực sự được người dùng chủ ý? — CSRF

CSRF (Cross-Site Request Forgery) xảy ra khi browser tự kèm credential như session cookie vào một request do trang khác kích hoạt. Nếu server chỉ dựa vào cookie để chấp nhận thao tác thay đổi dữ liệu, kẻ tấn công có thể lợi dụng phiên của nạn nhân.

Spring Security **bật CSRF protection theo mặc định** trong cấu hình web thông thường, nhất là hữu ích với browser dùng session/cookie. Các request không an toàn (`POST`, `PUT`, `PATCH`, `DELETE`...) cần CSRF token hợp lệ khi thuộc phạm vi bảo vệ. Một endpoint được `permitAll()` vẫn có thể bị CSRF filter kiểm tra.

Chỉ cân nhắc tắt hoặc bỏ qua CSRF **theo phạm vi đã phân tích** cho API không dựa vào credential mà browser tự đính kèm (ví dụ API chỉ chấp nhận bearer token trong `Authorization` header và không dùng session cookie). Không dùng `csrf.disable()` như cách chữa lỗi 403 thiếu token ở form/browser.

### 4.5. Browser khác origin có được gọi API? — CORS

**CORS** là cơ chế browser kiểm tra quyền JavaScript của một origin truy cập response từ origin khác. Nó **không phải** phân quyền người dùng và không ngăn các client ngoài browser gửi HTTP request. Preflight `OPTIONS` thường không kèm cookie phiên; nếu security chặn preflight trước khi CORS được xử lý, giao diện có thể báo lỗi dù endpoint hợp lệ.

Cấu hình danh sách origin, methods, headers và `allowCredentials` theo client thực tế; tích hợp CORS đúng chỗ trong Spring Security/Spring MVC. Không bật wildcard origin bừa bãi, đặc biệt khi cho phép credential. CSRF và CORS giải quyết **hai loại rủi ro khác nhau**.

### 4.6. Request thất bại trả về gì? — 401, 403 và security headers

- **401 Unauthorized**: request thiếu/thất bại thông tin xác thực; API thường trả 401 kèm authentication challenge nếu phù hợp, còn form login có thể **redirect tới trang đăng nhập**. Không quy mọi trường hợp chưa login thành chính xác một status nếu ứng dụng cấu hình redirect.
- **403 Forbidden**: danh tính đã xác thực nhưng thiếu quyền, hoặc request bị chính sách khác từ chối (ví dụ CSRF token không hợp lệ). Vì thế 403 **không tự chứng minh** rằng lỗi là role.
- **Security headers**: Spring Security có thể thiết lập các header bảo vệ mặc định, chẳng hạn `X-Content-Type-Options: nosniff` và chính sách chống nhúng trang theo cấu hình; **Content-Security-Policy không được tự thêm đầy đủ cho mọi ứng dụng**. Xác định CSP, HSTS và các header khác theo kiến trúc HTTPS/frontend của hệ thống.

`ExceptionTranslationFilter` phối hợp với `AuthenticationEntryPoint` và `AccessDeniedHandler` để xử lý các tình huống xác thực/phân quyền thất bại khi exception đi qua cơ chế bảo mật. Không nhầm lẫn ngoại lệ bảo mật ở filter với exception handler nghiệp vụ ở MVC.

## 5. Ví dụ tối thiểu: bảo vệ ba endpoint của Spring MVC

Giả sử tạo dự án **Spring Boot 3.x, Java 17+** dùng Servlet (starter web) và Spring Security. Trong `build.gradle` của một dự án Spring Boot đã được cấu hình plugin/dependency management, cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/security/SecurityDemoApplication.java`. Ví dụ cố ý chỉ dùng HTTP **GET** để tập trung vào authentication/authorization; CSRF protection vẫn giữ nguyên mặc định và chưa cần form xử lý token.

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}

@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public ok";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin ok";
    }
}
```

Các lớp `WebSecurityConfig` và `DemoController` là package-private, có thể cùng nằm trong tệp với một lớp `public SecurityDemoApplication`. Tệp trên là mã Java biên dịch được khi dự án có hai Spring Boot starter và plugin build phù hợp. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` mặc định mã hóa mật khẩu mới bằng thuật toán thích hợp (thường BCrypt qua tiền tố định danh); không tự lưu plaintext dù ví dụ dùng credential cố định.

Chạy dự án ở môi trường thực hành, chẳng hạn `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Khi ứng dụng đang chạy trên cổng mặc định 8080, thử:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:demo-pass http://localhost:8080/profile
curl -i -u learner:demo-pass http://localhost:8080/admin
curl -i -u admin:demo-admin http://localhost:8080/admin
```

Kỳ vọng cho các request GET (status và nội dung quan trọng, bỏ qua các header biến thiên):

| Request | Status | Nội dung/diễn giải |
| --- | --- | --- |
| `GET /public` không credential | **200** | `public ok`; `permitAll` cho phép anonymous |
| `GET /profile` không credential | **401** | HTTP Basic yêu cầu xác thực; không chạy controller |
| `GET /profile` với `learner` | **200** | `hello learner` |
| `GET /admin` với `learner` | **403** | Đã xác thực nhưng thiếu `ROLE_ADMIN` |
| `GET /admin` với `admin` | **200** | `admin ok` |

Ở đây `hasRole("ADMIN")` khớp với `ROLE_ADMIN` được tạo bởi `.roles("ADMIN")`. `anyRequest().denyAll()` thể hiện cách chặn mọi route ngoài chính sách demo; một ứng dụng thật có thể thay bằng `authenticated()` nếu đó là chính sách đã quyết định. Chỉ có **một** `SecurityFilterChain`, nên chưa gặp bài toán thứ tự chain.

**Giới hạn ví dụ:** username/password hard-code và in-memory chỉ dành cho máy học tập; không triển khai ra Internet. HTTP Basic phải chạy qua HTTPS ở hệ thống thật. Ví dụ không xử lý quyền sở hữu tài nguyên, tích hợp database, OAuth2/OIDC, audit, rate limiting hay frontend dùng cookie. Khi thêm POST/PUT/DELETE từ browser, phải thiết kế CSRF token/cookie tương ứng thay vì tắt bảo vệ tùy tiện.

## 6. Từ ví dụ tới ứng dụng thực tế: các câu hỏi thiết kế

Trước khi thêm một filter hoặc một annotation, hãy trả lời theo thứ tự:

1. **Client nào gửi request?** Browser render trang server, SPA dùng cookie, ứng dụng di động hay machine-to-machine? Đáp án ảnh hưởng tới session, Basic, bearer token, CSRF và CORS.
2. **Định danh nằm ở đâu?** Cơ sở dữ liệu nội bộ, identity provider, OIDC login hay resource server xác minh access token? Ai là bên phát hành, ai là bên xác minh, ai thu hồi credential?
3. **Ranh giới tài nguyên là gì?** Chỉ tách public/user/admin hay còn owner/organization/tenant? Quy tắc URL chỉ là tuyến đầu, không thay kiểm tra tại service/data.
4. **Mặc định cho request không được mô tả?** Chặn toàn bộ, yêu cầu đăng nhập hay cho phép vì có căn cứ rõ? Có nhiều `SecurityFilterChain` thì chain nào khớp, thứ tự ra sao, có khoảng trống nào không?
5. **Lỗi và theo dõi?** API trả 401/403 có cấu trúc ổn định, không tiết lộ thông tin mật; log/audit phân biệt đăng nhập thất bại, không đủ quyền và CSRF, tránh ghi password/token nguyên văn.
6. **Làm sao kiểm chứng?** Kiểm thử cả anonymous, user thường, admin, truy cập chéo tài nguyên, HTTP method khác, CSRF, preflight CORS và các route bị bỏ sót. Đừng chỉ thử happy path đã đăng nhập.

Một ví dụ phân tầng: `GET /orders/123` có thể yêu cầu `authenticated()` ở tầng HTTP; nhưng service vẫn cần xác nhận order 123 thuộc user/tenant hiện tại. Không được suy rằng có `ROLE_USER` thì quyền đọc mọi order là hợp lệ.

## 7. Lỗi thường gặp và cách sửa tư duy

| Lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Coi authentication là authorization | Biết danh tính chưa đủ kết luận được phép truy cập tài nguyên | Xác định quyền ở request, service và mức đối tượng |
| Chỉ kiểm tra quyền trong controller | Dễ bỏ sót endpoint mới và tái sử dụng service không được bảo vệ | Dùng cấu hình request rõ ràng; kiểm tra nghiệp vụ tại nơi có dữ liệu |
| Thêm `permitAll` rồi cho rằng route bỏ qua mọi bảo vệ | Filter khác, bao gồm CSRF, vẫn chạy | Hiểu từng lớp filter và HTTP method |
| Tắt CSRF vì `POST` nhận 403 | Có thể làm cookie-based app dễ bị CSRF | Thiết lập CSRF token đúng; chỉ loại trừ khi đã chứng minh không dùng credential browser tự gửi |
| Nghĩ CORS là giải pháp phân quyền hoặc chống CSRF | CORS là cơ chế kiểm soát đọc cross-origin của browser | Dùng CORS, CSRF, authentication và authorization đúng vai trò |
| Thêm nhiều chain nhưng matcher/order chồng lấn | Chain đầu tiên khớp thắng; có thể áp sai policy hoặc bỏ trống coverage | Kiểm tra `securityMatcher`, `@Order` và chain cuối, thử từng URL |
| Tin `SecurityContextHolder` tự đi qua mọi thread | Ngữ cảnh mặc định gắn với thread | Dùng cơ chế propagation phù hợp, tránh giữ principal trong global state |
| Dùng Basic trên HTTP thường hoặc lưu password plaintext | Credential có thể bị lộ | Bắt buộc TLS và dùng `PasswordEncoder` |
| Trả mọi lỗi bảo mật thành 403 | Che khuất khác biệt chưa xác thực/thiếu quyền/CSRF | Phân loại và kiểm tra status, handler và audit thực tế |
| Tin rằng framework thay kiểm tra owner/tenant | Vai trò chung không phản ánh quyền trên bản ghi cụ thể | Kiểm tra ownership/tenant khi truy xuất và cập nhật dữ liệu |

## 8. Tự kiểm tra kiến thức

1. Tại sao Servlet Filter thích hợp để bảo vệ request trước Spring MVC, và `FilterChainProxy` khác `SecurityFilterChain` thế nào?
2. Với user đã đăng nhập nhưng xem đơn hàng thuộc người khác, chỉ thêm `.authenticated()` có đủ không? Kiểm tra còn thiếu nằm ở đâu?
3. Tại sao `POST /public` có thể bị 403 dù endpoint đã dùng `permitAll()`?
4. Hai request giống nhau nhưng một request không có credential, request còn lại là user thiếu vai trò: kết quả HTTP thường khác nhau thế nào?
5. Khi thêm chain riêng cho `/api/**`, bạn phải kiểm tra matcher, thứ tự và chain dự phòng ra sao để không vô tình để hở request?

**Điểm cần nắm:** Trong ứng dụng Servlet, Spring Security đặt một hệ thống xác thực, phân quyền và bảo vệ HTTP trên luồng Servlet Filter. Framework cung cấp cơ chế; tính đúng đắn phụ thuộc vào việc chọn chính sách cho client, tài nguyên, trạng thái đăng nhập và từng loại request của chính ứng dụng.
