# Xác thực, phân quyền và bảo vệ trước tấn công: ba trách nhiệm liên quan

Trong ứng dụng **Spring Security trên Servlet stack**, bảo mật một HTTP request thường cần ba quyết định độc lập nhưng phối hợp với nhau:

1. **Xác thực (authentication):** ai đang gửi request, và bằng chứng danh tính có hợp lệ không?
2. **Phân quyền (authorization):** danh tính đó có được thực hiện hành động trên tài nguyên cụ thể không?
3. **Bảo vệ trước tấn công (exploit protection):** ngay cả request có danh tính và quyền hợp lệ, nó có đang lợi dụng một cơ chế dễ bị tấn công như CSRF, nhúng trang, phiên đăng nhập hoặc dữ liệu đầu vào độc hại không?

Ba lớp này không thay thế nhau. Đăng nhập thành công không có nghĩa được đọc mọi dữ liệu; được cấp quyền không có nghĩa request đã vượt qua kiểm tra CSRF; bật CSRF không thể sửa lỗi cấp quyền đọc dữ liệu của người khác.

## 1. Phân biệt ba trách nhiệm

| Lớp | Câu hỏi chính | Thông tin đầu vào thường dùng | Quyết định/ví dụ |
| --- | --- | --- | --- |
| Authentication | “Bạn là ai?” | Username/password, session, HTTP Basic, bearer token, chứng chỉ… | Xây dựng đối tượng Authentication đại diện danh tính; xác thực sai thì từ chối |
| Authorization | “Bạn được làm gì với tài nguyên này?” | Authentication, authorities/roles, HTTP method, URL, chủ sở hữu và ngữ cảnh nghiệp vụ | USER đọc hồ sơ của mình; ADMIN được vào trang quản trị; người không có quyền bị từ chối |
| Exploit protection | “Request này có vi phạm cơ chế bảo vệ chống khai thác không?” | HTTP method, CSRF token, cookie/session, headers, origin, cấu trúc URL… | Chặn POST thiếu CSRF token trong ứng dụng dùng cookie; giảm rủi ro clickjacking, xử lý request bất thường |

Một người dùng tên Lan có thể:
- Xác thực thành công bằng session cookie.
- Được phép xem đơn hàng của chính mình nhưng bị từ chối khi yêu cầu đơn hàng của Minh.
- Bị từ chối POST thay đổi địa chỉ nếu request thiếu CSRF token hợp lệ, dù Lan đã đăng nhập và có quyền sửa địa chỉ.

**Nguyên tắc:** kiểm tra danh tính, quyền truy cập và biện pháp chống khai thác ở vị trí phù hợp; kết quả thành công của lớp trước không tự động cho qua lớp sau.

## 2. Request đi qua Spring Security như thế nào?

Với Spring MVC/Servlet, ứng dụng web chạy qua chuỗi Servlet Filter trước khi tới DispatcherServlet và controller. Sơ đồ khái niệm:

~~~text
Client HTTP request
    |
Servlet container
    |
DelegatingFilterProxy (springSecurityFilterChain)
    |
FilterChainProxy -> chọn SecurityFilterChain khớp request
    |
    +-- Nạp/ngữ cảnh bảo mật (SecurityContextHolderFilter)
    +-- Các filter liên quan CORS, CSRF, security headers... nếu đã cấu hình
    +-- Filter xác thực phù hợp (Basic, form login, bearer token...)
    +-- Xử lý anonymous, ngoại lệ bảo mật
    +-- AuthorizationFilter kiểm tra rule truy cập
    |
DispatcherServlet -> Controller -> Service -> tài nguyên
~~~

Đây là **sơ đồ trách nhiệm**, không phải thứ tự chính xác của toàn bộ filter trong mọi cấu hình. Những filter hiện diện và thứ tự cụ thể phụ thuộc Spring Security version, cấu hình và cơ chế xác thực. Có thể bật DEBUG cho org.springframework.security hoặc xem filter chain lúc khởi động để tìm chuỗi thực tế.

Các thành phần cần hiểu:

- **DelegatingFilterProxy** nối Servlet container với bean Spring Security; **FilterChainProxy** quản lý các SecurityFilterChain. Nếu có nhiều chain, chain **đầu tiên khớp** request được chọn. Quy tắc securityMatcher quyết định chain áp dụng; requestMatchers trong authorizeHttpRequests quyết định quyền *bên trong* chain.
- **SecurityContextHolder** cung cấp SecurityContext cho luồng xử lý hiện tại; context chứa Authentication nếu có. SecurityContextHolderFilter là một phần của cơ chế đọc/ngữ cảnh hiện đại, còn cách lưu context giữa request phụ thuộc SecurityContextRepository và cách xác thực.
- **Authentication** chứa principal (danh tính), credentials khi phù hợp và GrantedAuthority (quyền). Với username/password, AuthenticationManager thường ủy quyền AuthenticationProvider kiểm tra credentials; với bearer token, cơ chế xác thực/giải mã token có đường đi riêng.
- **AnonymousAuthenticationFilter** có thể đặt một anonymous Authentication cho request chưa đăng nhập. Đây không phải danh tính người dùng đã xác thực để vượt qua rule authenticated().
- **AuthorizationFilter** thực thi quyết định của AuthorizationManager đối với request theo rule đã khai báo. Ngoài URL, kiểm soát quyền ở method/service thường cần thiết để chống truy cập chéo tài nguyên.
- **ExceptionTranslationFilter** chuyển các ngoại lệ bảo mật phát sinh ở phía sau nó thành hành vi HTTP thích hợp qua AuthenticationEntryPoint hoặc AccessDeniedHandler. CSRF filter và các thành phần khác cũng có đường từ chối request riêng; đừng giả định mọi lỗi đều đi qua cùng một filter.

Không nên suy ra “đã vào controller” chỉ từ việc request có cookie hoặc header Authorization: request có thể bị từ chối trước controller, ở service, hoặc bởi biện pháp chống khai thác.

## 3. Authentication: chứng minh danh tính

Một flow username/password điển hình:

1. Client đưa credentials vào cơ chế đăng nhập được cấu hình (form hoặc HTTP Basic).
2. Filter nhận credentials, yêu cầu AuthenticationManager/AuthenticationProvider xác minh với UserDetailsService, PasswordEncoder hoặc hệ thống danh tính.
3. Nếu thành công, Spring Security có Authentication với principal và authorities; SecurityContext được sử dụng cho các kiểm tra tiếp theo.
4. Cơ chế lưu/truy xuất danh tính ở request tiếp theo khác nhau: browser session có thể dùng cookie phiên; REST resource server thường xác thực bearer token ở từng request.

Cần phân biệt:

- **HTTP Basic:** mỗi request có thể gửi Authorization: Basic ...; chuỗi base64 chỉ là cách mã hóa biểu diễn, **không phải mã hóa bảo mật**. Bắt buộc dùng HTTPS.
- **Session login:** trình duyệt thường tự gửi cookie cho request phù hợp. Việc gửi cookie tự động làm cho CSRF đặc biệt quan trọng đối với thao tác thay đổi trạng thái.
- **Bearer token/JWT:** server xác minh chữ ký, hạn dùng, issuer/audience/scope theo cấu hình; token hợp lệ chỉ chứng minh những điều token và hệ thống tin cậy cho phép, không mặc nhiên cho quyền vào mọi tài nguyên.
- **Mật khẩu:** production dùng PasswordEncoder phù hợp như BCrypt/Argon2 với chính sách quản lý khóa và tài khoản; không lưu plaintext hay dùng {noop} ngoài ví dụ học tập.

Xác thực thất bại thường dẫn tới **401 Unauthorized** và lời thách thức xác thực (ví dụ WWW-Authenticate với HTTP Basic). Tên trạng thái hơi dễ gây nhầm: 401 chủ yếu báo cần thông tin xác thực hợp lệ.

## 4. Authorization: quyết định quyền truy cập

Sau khi đã có ngữ cảnh danh tính, cần phân quyền theo cả **chức năng** và **dữ liệu**:

- Request-level: cho phép GET /api/public không đăng nhập; yêu cầu authenticated() cho /api/profile; yêu cầu hasRole("ADMIN") cho /api/admin.
- Method-level: kiểm tra quy tắc trên service bằng @PreAuthorize khi bật @EnableMethodSecurity. Nơi đặt annotation phải là lời gọi được Spring AOP xử lý; tự gọi method trong cùng bean có thể bỏ qua proxy.
- Object-level: người có role USER vẫn chỉ được xem hóa đơn của chính họ hoặc hóa đơn thuộc tổ chức được phép. Chỉ kiểm tra role ở URL là chưa đủ để chặn **IDOR/BOLA** (thay ID trong đường dẫn).

**Authority và role:** roles("ADMIN") trong cấu hình người dùng thông thường tạo authority ROLE_ADMIN; hasRole("ADMIN") kiểm tra tiền tố ROLE_ theo mặc định. Ngược lại, hasAuthority("invoice:read") kiểm tra đúng chuỗi quyền đã cấp. Đừng lẫn role với chuỗi authority tùy biến.

Nguyên tắc thiết kế:

1. **Deny by default:** endpoint không khai báo rõ quyền thì từ chối; không để endpoint mới vô tình public.
2. **Least privilege:** chỉ cấp đúng quyền cần thiết, trên đúng phạm vi dữ liệu.
3. **Server-side enforcement:** ẩn nút ở UI chỉ cải thiện giao diện, không phải biện pháp phân quyền.
4. **Rule ordering:** rule đặc hiệu nên đặt trước rule rộng trong authorizeHttpRequests vì bộ quy tắc được đánh giá theo thứ tự.
5. **Kiểm tra ở tầng nghiệp vụ:** xác minh chủ sở hữu/tenant/trạng thái giao dịch ngay khi thực hiện hành động, kể cả đã kiểm tra URL.

**403 Forbidden** là kết quả thường gặp khi danh tính đã hợp lệ nhưng không có quyền. Với người chưa xác thực, Spring Security có thể chọn 401 và yêu cầu đăng nhập trước; mã thực tế còn phụ thuộc entry point và handler đã cấu hình.

## 5. Exploit protection: thêm rào chắn cho request “có vẻ hợp lệ”

Spring Security cung cấp nhiều cơ chế, nhưng không phải mọi dạng tấn công đều được khắc phục tự động.

| Rủi ro | Cơ chế phù hợp | Điều cần tránh hiểu nhầm |
| --- | --- | --- |
| **CSRF**: website khác kích hoạt request thay đổi dữ liệu dưới phiên browser của nạn nhân | CSRF token được ràng buộc/kiểm chứng trong flow có credential tự gửi (như cookie session) | Đã login hoặc có role EDITOR không ngăn CSRF; CORS cũng không thay CSRF |
| **Clickjacking**: kẻ tấn công nhúng trang vào frame để đánh lừa thao tác | Header chống framing (X-Frame-Options hoặc CSP frame-ancestors) | Header chỉ là một lớp; xem chính sách nhúng thực tế |
| **XSS**: dữ liệu không tin cậy bị diễn giải thành script | Output encoding đúng ngữ cảnh, template escaping, CSP được cấu hình chủ động, kiểm soát đầu vào | Authentication và authorizeHttpRequests không tự làm sạch HTML hay sửa XSS |
| **Session abuse/fixation** | Quản lý session, cookie Secure/HttpOnly/SameSite thích hợp, session fixation protection, giới hạn thời gian | Cookie flags không thể thay phân quyền hay CSRF token |
| **Request URL bất thường** | HttpFirewall và chuẩn hóa/kiểm soát request trong filter chain | Firewall không thay input validation hoặc kiểm tra nghiệp vụ |
| **Brute force, lạm dụng API, SQL injection, SSRF** | Rate limiting/MFA/monitoring, truy vấn tham số hóa, validate URL/egress và các lớp hệ thống | Không có chuyện thêm spring-boot-starter-security là tất cả tự an toàn |

**CSRF trong Servlet:** các HTTP method được xem là “safe” (GET, HEAD, OPTIONS, TRACE theo mặc định của CSRF matcher) không bị yêu cầu CSRF token; POST, PUT, PATCH, DELETE thường được kiểm tra. Vì vậy, **không được đặt thao tác thay đổi trạng thái vào GET**. Token phải được truyền bằng cách được server hỗ trợ (form field hoặc request header theo cấu hình). Spring Security bật CSRF protection mặc định cho cách cấu hình web thông thường; cần kiểm tra cấu hình thực tế.

**CORS không phải authorization:** CORS quy định browser có được đọc/gửi một số cross-origin request theo chính sách hay không. API client không chạy trong browser có thể gửi request trực tiếp; vì thế không dùng CORS để quyết định ai được sửa hoặc xem dữ liệu. Nếu tích hợp CORS với Spring Security, phải xử lý preflight đúng cách và tránh tự chặn OPTIONS trước khi kiểm tra origin.

**Security headers:** Spring Security cung cấp các security headers mặc định có ích, nhưng **không tự thêm CSP tổng quát** vì chính sách CSP phải phù hợp tài nguyên của ứng dụng. HSTS có ý nghĩa khi truy cập qua HTTPS. Kiểm tra header thực tế bằng trình duyệt/curl và cấu hình cụ thể.

**Khi nào mới cân nhắc tắt CSRF?** Một API thực sự stateless, chỉ nhận bearer token được client chủ động đưa vào Authorization header và **không dùng cookie/credential tự đính kèm bởi browser**, có thể không cần cơ chế CSRF truyền thống. Đó là quyết định theo threat model của từng security chain; đừng tắt CSRF toàn cục chỉ vì endpoint trả JSON, dùng HTTP Basic hoặc gọi là “REST API”.

## 6. Ví dụ chạy được: Spring Boot 3.3.x, Spring Security 6, Java 17+

Ví dụ minh họa ba trách nhiệm trong cùng một ứng dụng Servlet. Dùng Maven và JDK 17 trở lên; tổ chức file như sau:

~~~text
three-responsibilities/
├── pom.xml
└── src/main/java/com/example/security/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>three-responsibilities</artifactId>
    <version>1.0.0</version>

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
~~~

**src/main/java/com/example/security/DemoApplication.java**

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/security/SecurityConfig.java**

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
            .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
            .requestMatchers(HttpMethod.POST, "/api/changes").authenticated()
            .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        http.formLogin(AbstractHttpConfigurer::disable);

        // Không gọi csrf().disable(): CSRF vẫn bật theo mặc định.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Chỉ dùng {noop} cho bài học; production phải dùng PasswordEncoder an toàn.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

**src/main/java/com/example/security/DemoController.java**

~~~java
package com.example.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-only");
    }

    @PostMapping("/changes")
    public Map<String, String> change() {
        return Map.of("status", "changed");
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Kiểm chứng bằng terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:reader-pass http://localhost:8080/api/profile
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/api/changes
~~~

| Request | HTTP status dự kiến | Điều được kiểm chứng |
| --- | --- | --- |
| GET /api/public, không credentials | **200**; JSON {"message":"public"} | permitAll cho endpoint công khai |
| GET /api/profile, không credentials | **401** | Thiếu xác thực; HTTP Basic entry point thách thức client |
| GET /api/profile, reader hợp lệ | **200**; JSON {"user":"reader"} | Danh tính reader đã xác thực |
| GET /api/admin, reader hợp lệ | **403** | Đã xác thực nhưng không có ROLE_ADMIN |
| GET /api/admin, admin hợp lệ | **200**; JSON {"message":"admin-only"} | Xác thực và phân quyền đều đạt |
| POST /api/changes, reader hợp lệ, không CSRF token | **403** | Có danh tính và được cấp quyền URL nhưng thiếu kiểm tra chống CSRF |

Dòng POST minh họa một **request bị từ chối trước khi logic change() thực hiện**, nên JSON {"status":"changed"} không được trả về. Mã 403 ở đây do CSRF protection, không phải vì reader thiếu role. Các header, body lỗi và log chi tiết có thể khác theo cấu hình; bảng chỉ cam kết những status/JSON liên quan đến ví dụ.

Ví dụ dùng HTTP Basic và tài khoản trong bộ nhớ để quan sát rõ ràng. Nó **không phải cấu hình production**: hãy thay {noop} bằng password hashing, dùng HTTPS, quản lý danh tính tập trung, rate limit/audit, kiểm tra CSRF theo cơ chế browser thực tế, và chỉ cấu hình stateless khi có yêu cầu xác thực cụ thể.

## 7. Hai lỗi thiết kế dễ nhầm khi ghép ba lớp

**Tình huống A — Lộ đơn hàng qua URL**

- Alice đăng nhập thành công, GET /orders/100 trả đơn của Alice.
- Alice thử GET /orders/101 là đơn của Bob. Nếu server chỉ kiểm tra authenticated(), request vẫn có thể qua cổng URL.
- Phải kiểm tra đối tượng đơn 101 thuộc Alice hoặc Alice có quyền theo nghiệp vụ trước khi trả dữ liệu. Trả 403 (hoặc 404 theo chính sách tránh tiết lộ tồn tại tài nguyên) khi không hợp lệ.

Kết luận: authentication đúng chưa chứng minh quyền sở hữu **từng đối tượng**.

**Tình huống B — Request đổi email từ website độc hại**

- Alice có session cookie và quyền cập nhật email.
- Một trang khác dụ browser gửi POST đến ứng dụng bằng cookie của Alice.
- Nếu ứng dụng chấp nhận credential tự gửi nhưng không kiểm tra CSRF token, action có thể bị thực hiện mà Alice không chủ ý. CSRF protection từ chối request không có token hợp lệ.

Kết luận: authorization đúng chưa chứng minh **ý định của người dùng** đối với request thay đổi trạng thái.

**Tình huống C — Nhập dữ liệu có script**

- User được phép cập nhật mô tả hồ sơ, nhưng dữ liệu chứa HTML/script.
- Xác thực + phân quyền chỉ trả lời “ai được sửa”, không bảo đảm dữ liệu an toàn khi hiển thị.
- Cần escape/output encoding đúng HTML/JavaScript context, tránh dựng HTML không kiểm soát và cân nhắc CSP phù hợp.

Kết luận: exploit protection có nhiều biện pháp ngoài CSRF; phải chọn đúng rủi ro và ngữ cảnh.

## 8. Chọn cơ chế bảo mật theo mô hình client

| Mô hình | Authentication | Authorization | Bảo vệ cần chú trọng |
| --- | --- | --- | --- |
| Web MVC sử dụng cookie session | Login và session | Route/method/object-level | CSRF token, cookie flags, session fixation, headers, XSS |
| API gọi bằng HTTP Basic | Username/password trên từng request | Route/method/object-level | HTTPS, giới hạn đăng nhập, CSRF nếu browser tự gửi credentials, không lộ Basic credentials |
| Resource Server nhận bearer token trong Authorization header | OAuth2 resource server/JWT hoặc opaque token theo cấu hình | Authorities/scopes, owner/tenant, audience | Xác minh issuer/audience/expiry, quản lý token, CORS đúng nhu cầu; đánh giá CSRF theo cách client giữ/gửi credential |

Một ứng dụng có thể dùng **nhiều SecurityFilterChain** cho browser và API, mỗi chain có matcher và chính sách phù hợp. Khi làm vậy, xác minh tất cả đường dẫn được bảo vệ bởi một chain mong muốn; khai báo securityMatcher quá hẹp có thể để endpoint ngoài mọi chain bảo vệ nếu không có fallback.

## 9. Chẩn đoán khi thấy 401 hoặc 403

Thay vì tắt bảo vệ để “cho chạy được”, lần lượt hỏi:

1. Request có đi vào đúng SecurityFilterChain không? Kiểm tra matcher, HTTP method và log filter chain.
2. Credentials có thật sự được gửi và hợp lệ không? Xác định cơ chế Basic/session/bearer; kiểm tra SecurityContext/Authentication và authorities sau xác thực (không log password/token).
3. URL rule nào khớp đầu tiên? hasRole("ADMIN") đòi ROLE_ADMIN, còn hasAuthority("ADMIN") đòi chính chuỗi ADMIN.
4. Có kiểm tra method/object-level trong service không? Đã chặn đọc/sửa đối tượng ngoài quyền của user chưa?
5. Request thay đổi trạng thái có thiếu hoặc sai CSRF token không? Browser có gửi cookie tự động không?
6. CORS preflight, headers, firewall hoặc error handler có ảnh hưởng không? 403 từ CSRF và 403 từ thiếu quyền cần được phân biệt bằng log và cấu hình thực tế.
7. Khi trả 200, dữ liệu và side effect có đúng giới hạn cho phép không? Thành công HTTP không bảo đảm không lộ dữ liệu.

Khi điều tra, bật DEBUG có chọn lọc trong môi trường phát triển và **không in credentials, Authorization header hay CSRF token vào log**.

## 10. Checklist thiết kế một endpoint nhạy cảm

Ví dụ POST /accounts/{id}/transfer:

- **Authentication:** xác minh người yêu cầu qua session hoặc token đã chọn; không tin userId do client tự khai là danh tính.
- **Authorization:** xác minh người đó có quyền chuyển tiền từ account id; kiểm tra tổ chức/chủ sở hữu, trạng thái tài khoản và giới hạn giao dịch ở service.
- **Exploit protection:** với cookie session, kiểm tra CSRF; xác thực input, giới hạn tần suất, audit, chống replay/idempotency theo yêu cầu nghiệp vụ; dùng HTTPS và security headers phù hợp.
- **Kiểm thử:** chưa đăng nhập; sai quyền; sai chủ tài khoản; thiếu CSRF token; token hợp lệ; input lỗi; các request lặp. Xác nhận trạng thái dữ liệu thực tế sau khi bị từ chối, không chỉ nhìn status HTTP.

## 11. Câu hỏi tự kiểm tra

1. Nếu một user đã đăng nhập thành công nhưng truy cập hóa đơn của người khác, lớp nào phải từ chối? **Authorization ở mức đối tượng/dữ liệu.**
2. Nếu user có quyền cập nhật hồ sơ nhưng browser gửi POST thiếu CSRF token, lớp nào có thể từ chối? **Exploit protection/CSRF.**
3. Nếu API chỉ cho browser origin A qua CORS, người dùng từ curl có thể gửi request không? **Có**; CORS không phải server-side authorization.
4. Tại sao không nên tắt CSRF toàn ứng dụng chỉ vì dùng JSON? **Vì trình duyệt vẫn có thể tự gửi cookie hoặc credentials; rủi ro phụ thuộc cơ chế xác thực và cách client gửi credential.**
5. Role ADMIN có tự cho phép xem mọi dữ liệu tenant khác không? **Không**; kiểm tra phạm vi và điều kiện nghiệp vụ vẫn cần thiết.

**Điểm cần nhớ:** Spring Security trên Servlet giải quyết các vấn đề ở nhiều lớp. Xác thực đưa ra danh tính đáng tin; phân quyền áp chính sách hành động/tài nguyên; exploit protection ngăn các cách khai thác xảy ra ngay cả khi danh tính và quyền có vẻ hợp lệ. Một hệ thống an toàn phải thiết kế và kiểm chứng đủ cả ba, cùng với kiểm soát đầu vào, mã hóa, giám sát và quy tắc nghiệp vụ phù hợp.
