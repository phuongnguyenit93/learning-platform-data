# Phân biệt xác thực, phân quyền và bảo vệ trước các kiểu tấn công trong Spring Security Reactive

## 1. Bức tranh tổng quan

Trong ứng dụng Spring WebFlux, bảo mật cần trả lời ba câu hỏi khác nhau:

1. **Authentication (xác thực):** Ai đang gửi yêu cầu? Hệ thống có đủ bằng chứng để tin danh tính đó không?
2. **Authorization (phân quyền/kiểm soát truy cập):** Danh tính đã xác thực được thực hiện hành động nào trên tài nguyên nào?
3. **Protection against attacks (phòng chống tấn công):** Những yêu cầu và dữ liệu có thể bị lợi dụng ra sao, kể cả khi người dùng đã đăng nhập hoặc endpoint cho phép truy cập?

Ví dụ: người dùng đăng nhập thành công, có quyền xem đơn hàng, nhưng vẫn không được xem đơn hàng của người khác; đồng thời API phải chống giả mạo yêu cầu qua trình duyệt, lộ token, XSS, nhập liệu độc hại và lạm dụng tài nguyên. Ba lớp này bổ sung cho nhau, không thể thay thế nhau.

| Góc nhìn | Authentication | Authorization | Bảo vệ trước tấn công |
| --- | --- | --- | --- |
| Câu hỏi | “Bạn là ai?” | “Bạn được phép làm gì với đối tượng này?” | “Yêu cầu/hệ thống có thể bị khai thác như thế nào?” |
| Đầu vào | Mật khẩu, phiên, bearer token, chứng chỉ… | Principal, quyền, vai trò, tài nguyên, ngữ cảnh nghiệp vụ | Kiểu yêu cầu, cookie/token, header, origin, payload, lưu lượng |
| Kết quả | Danh tính và trạng thái xác thực | Cho phép hoặc từ chối thao tác | Chặn, giới hạn, giảm tác động của mối đe dọa |
| Thành phần tiêu biểu | ReactiveAuthenticationManager, ReactiveUserDetailsService, Authentication | authorizeExchange, AuthorizationManager, @PreAuthorize | CSRF, CORS, security headers, TLS, mã hóa mật khẩu, validation, rate limiting |
| Sai lầm điển hình | Tin username do client tự gửi | Chỉ kiểm tra “đã đăng nhập” | Nghĩ rằng có Spring Security là tự động miễn nhiễm mọi cuộc tấn công |

**Nhớ nhanh:** xác thực chứng minh danh tính; phân quyền quyết định phạm vi thao tác; phòng vệ kiểm soát các đường tấn công vào toàn bộ luồng xử lý.

## 2. Spring Security hoạt động trong ứng dụng reactive

Spring WebFlux vận hành trên Reactor (Mono/Flux) và mô hình xử lý bất đồng bộ. Trong stack này, Spring Security đặt các **WebFilter** vào **SecurityWebFilterChain** để xử lý request trước khi gọi handler:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |-- Kiểm tra/khôi phục SecurityContext, xử lý credential
    |-- Authentication: tạo Authentication đã được xác thực
    |-- Authorization: áp dụng quy tắc truy cập URL
    |-- Các cơ chế phòng vệ: CSRF, header, xử lý ngoại lệ...
    v
Controller WebFlux -> Service (có thể có method security) -> Data
    |
    v
HTTP response
~~~

Đây là sơ đồ khái niệm; thứ tự WebFilter cụ thể do Spring Security cấu hình và có thể khác giữa cơ chế HTTP Basic, session hay OAuth2 Resource Server.

- **Authentication** chứa principal, danh sách GrantedAuthority và thông tin trạng thái xác thực. Các giá trị này phải do cơ chế bảo mật tin cậy tạo/kiểm tra, không lấy trực tiếp từ tham số tự khai của client.
- **SecurityContext** chứa Authentication tương ứng request. Với reactive, truy xuất/ngầm truyền ngữ cảnh chủ yếu qua **Reactor Context**; không được dựa vào ThreadLocal hoặc giả định mỗi request chỉ chạy trên một thread.
- **ReactiveSecurityContextHolder.getContext()** trả về Mono<SecurityContext>, hữu ích khi cần thông tin người dùng trong một pipeline reactive.
- **SecurityWebFilterChain** bảo vệ các HTTP exchange; **reactive method security** bảo vệ các phương thức service được gọi qua Spring proxy. Quy tắc nghiệp vụ và kiểm tra quyền trên từng bản ghi vẫn cần đặt ở tầng thích hợp.

Một endpoint được đặt permitAll chỉ có nghĩa không bắt buộc đăng nhập tại quy tắc truy cập đó; nó không đồng nghĩa với việc bỏ qua mọi WebFilter, mọi HTTP security header hoặc kiểm tra đầu vào.

## 3. Authentication: xác định ai đang gọi

Các cơ chế phổ biến:

| Cơ chế | Dữ liệu xác thực | Thường phù hợp | Điều cần chú ý |
| --- | --- | --- | --- |
| HTTP Basic | Authorization: Basic… (username/password được mã hóa Base64, không phải mã hóa bảo mật) | Demo, tích hợp nội bộ được bảo vệ bằng HTTPS | Chỉ dùng qua TLS; trình duyệt có thể tự gửi lại thông tin đăng nhập |
| Form login + session | Credential ban đầu rồi cookie phiên | Ứng dụng web phục vụ trình duyệt | Cookie, CSRF, phiên, logout, session timeout |
| OAuth2 Resource Server + JWT | Authorization: Bearer… | API nhận access token từ hệ thống phát hành tin cậy | Kiểm tra chữ ký, issuer, audience, thời hạn; ánh xạ scope/quyền |
| Opaque bearer token | Token được introspect với authorization server | API cần trạng thái/thu hồi token ở phía server | Kết nối introspection, cache và xử lý khi dịch vụ xác thực lỗi |

Đăng nhập thành công không tự tạo quyền admin. Ngược lại, client tự gửi header “role=ADMIN” cũng không phải bằng chứng quyền admin.

**Mật khẩu:** lưu password hash bằng thuật toán thích hợp như bcrypt, Argon2 hoặc PBKDF2 với cấu hình đủ mạnh; không lưu mật khẩu rõ, không tự hash bằng SHA-256 đơn thuần. PasswordEncoder chịu trách nhiệm encode và matches. Dữ liệu xác thực thử nghiệm trong bộ nhớ không phải cách quản lý danh tính cho production.

**Token:** JWT chỉ là định dạng. API phải xác minh chữ ký và các claim cần thiết; việc giải mã chuỗi JWT để đọc sub mà không kiểm tra tính hợp lệ không phải xác thực. Access token cần thời hạn ngắn, truyền qua HTTPS, hạn chế ghi vào log; cần xét cách thu hồi/giảm tác hại khi bị lộ.

## 4. Authorization: quyết định người dùng được phép làm gì

Có ba mức kiểm soát hay kết hợp với nhau:

1. **Theo URL và HTTP method:** ví dụ GET /public/ping cho phép mọi người; GET /admin/report chỉ dành cho ROLE_ADMIN.
2. **Theo phương thức nghiệp vụ:** bảo vệ service bằng @EnableReactiveMethodSecurity và @PreAuthorize, để một service không bị bỏ qua chính sách khi được gọi từ đường khác.
3. **Theo đối tượng cụ thể:** khi đọc đơn hàng 42, còn phải kiểm tra quyền sở hữu/tenant của chính đơn hàng 42. Có quyền đọc đơn hàng nói chung không mặc nhiên được đọc mọi đơn hàng.

Phân biệt tên quyền trong Spring Security:

- **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN** theo quy ước mặc định.
- **hasAuthority("orders:read")** kiểm tra đúng authority **orders:read**, không tự thêm tiền tố.
- Với JWT Resource Server và cách ánh xạ mặc định, scope có thể xuất hiện dưới authority dạng **SCOPE_orders.read**. Claim bên trong token không tự động có cùng ý nghĩa với vai trò ứng dụng; phải hiểu rõ bộ chuyển đổi quyền đang dùng.

Hãy đặt matcher cụ thể trước matcher bao quát, cuối cùng là **anyExchange().authenticated()** hoặc **denyAll()** tùy nhu cầu. Có chính sách mặc định rõ ràng sẽ giảm rủi ro endpoint mới vô tình lộ.

**Ví dụ lỗi phân quyền đối tượng (IDOR/BOLA):** người dùng A có quyền gọi GET /orders/42 nhưng đơn 42 thuộc người dùng B. Chỉ dùng authenticated() hoặc hasAuthority("orders:read") tại URL chưa đủ. Service/repository nên lấy dữ liệu trong phạm vi tenant/owner được phép rồi mới trả kết quả; có thể trả 403 hoặc 404 tùy chính sách không tiết lộ sự tồn tại tài nguyên. Không dùng ID gửi từ client để tự suy ra quyền sở hữu.

## 5. Demo chạy được: Spring Boot WebFlux + HTTP Basic + phân quyền theo vai trò

Demo sử dụng **Java 17+**, Spring Boot **3.3.5**, Spring Security cho WebFlux, hai tài khoản trong bộ nhớ. Mục đích là quan sát rõ 200/401/403 trên các HTTP GET, không triển khai đăng nhập thực tế hay một API ghi dữ liệu.

Cấu trúc tệp:

~~~text
reactive-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/reactiveauth/ReactiveSecurityDemoApplication.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'reactive-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

**src/main/java/com/example/reactiveauth/ReactiveSecurityDemoApplication.java**

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "hello " + context.getAuthentication().getName());
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Chạy:** cần JDK 17+ và Gradle tương thích với Spring Boot 3.3; tại thư mục dự án chạy:

~~~bash
gradle bootRun
~~~

Trong terminal khác, thử lần lượt:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -u reader:reader-pass http://localhost:8080/me
# hello reader

curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/admin/report
# admin-report
~~~

Giải thích kết quả:

| Request | Authentication | Authorization | Kết quả |
| --- | --- | --- | --- |
| GET /public/ping không credential | Không bắt buộc | permitAll | 200, pong |
| GET /me không credential | Không xác thực | Cần authenticated | 401 |
| GET /me bằng reader | Đúng mật khẩu | Đã xác thực | 200, hello reader |
| GET /admin/report bằng reader | Đã xác thực | Thiếu ROLE_ADMIN | 403 |
| GET /admin/report bằng admin | Đã xác thực | Có ROLE_ADMIN | 200, admin-report |

Với HTTP Basic, **401** thường kèm WWW-Authenticate để yêu cầu credential; **403** nghĩa danh tính đã được chấp nhận nhưng không có quyền. Nếu ứng dụng cấu hình form login, request trình duyệt chưa xác thực có thể được chuyển tới trang đăng nhập thay cho JSON/401: còn tùy entry point.

Code trên **giữ cấu hình CSRF mặc định** và chỉ cung cấp GET đọc dữ liệu. Không suy diễn rằng HTTP Basic làm CSRF tự hết: trình duyệt có thể tự gửi credential Basic được lưu. Hai mật khẩu demo phải thay bằng kho danh tính và quản lý bí mật phù hợp nếu chuyển sang môi trường thực tế.

## 6. Method security và quyền trên từng đối tượng

Trong hệ reactive, có thể bật method security rồi bảo vệ một phương thức của Spring bean:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfig {
}

@Service
class AdminReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readReport() {
        return Mono.just("admin-report");
    }
}
~~~

Đây là **đoạn minh họa độc lập** cho tầng service; không cần thêm vào demo để thử năm request ở trên. Lời gọi phải đi qua Spring bean/proxy để annotation được áp dụng; gọi nội bộ bằng this.method() có thể bỏ qua cơ chế proxy. Các phương thức được bảo vệ theo reactive method security nên trả về publisher phù hợp (Mono/Flux).

@PreAuthorize có thể kiểm tra vai trò/quyền, nhưng khi dữ liệu phụ thuộc chủ sở hữu, hãy xác thực cả điều kiện nghiệp vụ. Ví dụ truy vấn cơ sở dữ liệu theo cả orderId và tenantId từ danh tính đã được kiểm chứng. Không tin tenantId chỉ vì client gửi trong URL hoặc body.

## 7. Phòng chống những kiểu tấn công thường gặp

| Mối đe dọa | Kịch bản | Biện pháp chính | Điều Spring Security không tự làm thay |
| --- | --- | --- | --- |
| **CSRF** | Website khác khiến trình duyệt đã đăng nhập gửi POST/DELETE bằng cookie hoặc credential tự đính kèm | CSRF token cho các thao tác thay đổi trạng thái; SameSite là lớp bổ sung; thiết kế API theo cơ chế xác thực thực tế | Không quyết định mọi trường hợp có thể tắt CSRF chỉ dựa trên chữ “REST” |
| **XSS** | Nội dung không tin cậy được đưa vào HTML/script | Escape theo ngữ cảnh tại nơi hiển thị, tránh HTML/script không an toàn, CSP phù hợp | Không tự sanitize mọi dữ liệu mà ứng dụng render |
| **Credential stuffing/brute force** | Dò mật khẩu từ danh sách bị lộ hoặc thử lặp lại | Rate limit, giám sát, khóa mềm/cảnh báo có kiểm soát, MFA, mật khẩu băm mạnh | Không tự triển khai giới hạn số lần login chỉ vì bật HTTP Basic |
| **Lộ token/session** | Token bị đọc từ log, XSS, storage hoặc đường truyền | HTTPS, không log secret, TTL hợp lý, cookie HttpOnly/Secure nếu dùng cookie, quản lý thu hồi | Không tự thu hồi JWT đã lộ nếu chưa có thiết kế phù hợp |
| **IDOR/BOLA** | Thay ID trong URL để đọc dữ liệu người khác | Kiểm tra owner/tenant và quyền ở tầng dữ liệu/nghiệp vụ | Không tự suy ra quyền sở hữu từ authenticated() |
| **SQL/NoSQL injection** | Input bị ghép thành câu truy vấn | Bind parameter, API truy vấn an toàn, ràng buộc input | Không thay cho cách xây dựng query an toàn |
| **SSRF/path traversal** | Dữ liệu người dùng điều khiển URL nội bộ hoặc đường dẫn tệp | Allowlist đích, giới hạn mạng, chuẩn hóa và kiểm tra path | Không tự bảo vệ mọi thao tác HTTP client/file I/O |
| **DoS/lạm dụng tài nguyên** | Gửi lượng lớn request/payload hoặc tác vụ tốn CPU | Gateway rate limit, timeout, giới hạn kích thước, backpressure, quota, monitoring | Không tự cung cấp chính sách hạn ngạch nghiệp vụ đầy đủ |

### 7.1 CSRF: cookie/session khác bearer header

CSRF khai thác việc trình duyệt **tự động gắn credential** vào request tới website đích. Nếu dùng session cookie hoặc HTTP Basic mà browser tự gửi, các endpoint thay đổi trạng thái cần chiến lược CSRF phù hợp. Spring Security WebFlux bật CSRF protection theo mặc định; với POST/PUT/PATCH/DELETE được bảo vệ, client phải gửi token CSRF hợp lệ theo cơ chế cấu hình.

Với API **thật sự stateless**, chỉ nhận bearer token đặt thủ công trong Authorization header, không dựa vào cookie/credential tự gửi, có thể cân nhắc tắt CSRF **cho chuỗi bảo mật API đó**. Quyết định phải dựa trên credential thực sự được browser gửi và cách ứng dụng được sử dụng; không bật/tắt toàn cục theo thói quen. Nếu dùng cookie chứa JWT, nguy cơ CSRF vẫn có thể tồn tại.

### 7.2 CORS: kiểm soát đọc cross-origin của trình duyệt, không cấp quyền API

CORS xác định origin trình duyệt nào được thực hiện và đọc phản hồi cross-origin theo chính sách máy chủ. CORS **không** thay thế authentication/authorization: curl, mobile app hoặc server khác không bị cơ chế CORS của trình duyệt ràng buộc. Khi dùng Spring Security với CORS, xử lý preflight OPTIONS ở đúng vị trí để request preflight không bị từ chối chỉ vì chưa có thông tin đăng nhập; cấu hình origin/method/header cụ thể cho giao diện đã được tin cậy. Tránh cho phép origin bất kỳ đồng thời gửi credential.

### 7.3 XSS, security headers và HTTPS

- Encode/escape output theo ngữ cảnh HTML, thuộc tính, URL hoặc JavaScript; không đưa dữ liệu người dùng vào HTML động bằng API không an toàn.
- Cân nhắc Content-Security-Policy phù hợp với trang web; kiểm tra cấu hình header security thực tế của ứng dụng. Header giúp giảm rủi ro nhưng không thay kiểm tra dữ liệu.
- Sử dụng HTTPS cho đăng nhập và API; bật HSTS khi toàn bộ đường truy cập đã sẵn sàng HTTPS.
- Với session cookie, cân nhắc Secure, HttpOnly, SameSite, tuổi thọ session, xử lý logout và cố định phiên. HttpOnly giảm việc JavaScript đọc cookie nhưng không ngăn trình duyệt gửi cookie khi bị lợi dụng; SameSite không thay hoàn toàn CSRF token.

### 7.4 Riêng với lập trình reactive

Không dùng block() để lấy SecurityContext trong WebFlux handler hay WebFilter; thao tác blocking có thể làm nghẽn event-loop. Giữ pipeline Mono/Flux và truy cập ngữ cảnh bằng ReactiveSecurityContextHolder. Khi chuyển qua luồng async hoặc tích hợp thư viện khác, cần kiểm tra cách truyền Reactor Context thay vì mặc nhiên dùng SecurityContextHolder dạng ThreadLocal của servlet stack.

Làm việc với tài nguyên cần kiểm soát quyền ở thời điểm sử dụng; đừng chỉ kiểm tra một lần tại gateway rồi tin mọi đầu vào và mọi service phía sau. Việc đáp ứng backpressure, giới hạn đồng thời và timeout thuộc thiết kế vận hành bổ sung, không phải bảo đảm mặc định của authorizeExchange.

## 8. Áp dụng vào API thực tế

Xét GET /api/orders/42:

1. **Transport/protocol:** kết nối HTTPS; giới hạn kích thước request và các header cần thiết.
2. **Authentication:** xác minh session hoặc bearer token; không hợp lệ/không có mà endpoint yêu cầu đăng nhập thì trả 401 (hoặc luồng login tương ứng).
3. **URL authorization:** yêu cầu scope/quyền đọc đơn hàng; danh tính không đủ quyền thì từ chối, thường là 403.
4. **Object authorization:** tìm đơn 42 trong tenant/owner mà danh tính có quyền xem; chặn truy cập chéo người dùng.
5. **Data safety:** truy vấn tham số hóa, phản hồi đúng dữ liệu được phép, escape khi giao diện hiển thị.
6. **Abuse protection:** rate limit theo nguồn/danh tính, timeout, telemetry và cơ chế phát hiện bất thường.

Một hệ thống có thể xác thực đúng và phân quyền URL đúng mà vẫn bị BOLA. Nó cũng có thể kiểm soát owner đúng nhưng vẫn bị XSS hoặc lộ token nếu không xử lý dữ liệu/credential an toàn.

## 9. Những nhầm lẫn cần tránh

- **“Đã login thì gọi được mọi API.”** Sai: authenticated() không thay thế hasRole, hasAuthority hay quyền theo bản ghi.
- **“Role và authority là hai danh sách hoàn toàn độc lập.”** Sai theo mặc định: role được biểu diễn bằng GrantedAuthority có tiền tố ROLE_.
- **“CORS chặn mọi client lạ.”** Sai: đó là cơ chế trình duyệt; backend vẫn phải kiểm tra quyền.
- **“JWT giải mã được thì đáng tin.”** Sai: phải xác minh chữ ký, issuer, audience, thời hạn và các điều kiện ứng dụng.
- **“REST API luôn tắt CSRF.”** Sai: xét cách browser gửi credential, nhất là cookie và HTTP Basic.
- **“Spring Security tự chặn SQL injection, XSS, BOLA, brute force.”** Sai: phải bổ sung kiểm soát tương ứng ở tầng giao diện, dữ liệu, nghiệp vụ và hạ tầng.
- **“WebFlux dùng cùng cách lưu SecurityContext trong ThreadLocal như servlet.”** Sai: ưu tiên ngữ cảnh Reactor và API reactive.
- **“Đổi một URL thành permitAll có nghĩa mọi kiểm soát bảo mật bị vô hiệu.”** Sai: nhiều filter và cơ chế an toàn khác vẫn có thể áp dụng.

## 10. Tự kiểm tra kiến thức

1. Người dùng reader gọi /admin/report và nhận 403 trong demo. Họ đã vượt qua bước nào, thất bại ở bước nào?
2. Một API cho phép người dùng đọc /orders/{id} khi đã xác thực, nhưng ai cũng đổi được id để xem của người khác. Đây là lỗi xác thực hay lỗi phân quyền đối tượng?
3. Vì sao CORS không thể thay thế hasAuthority ở backend?
4. Vì sao tắt CSRF vì “API dùng JSON” là lập luận chưa đủ?
5. Nếu chuyển từ HTTP Basic sang bearer JWT, những phép kiểm tra token và những biện pháp chống lộ token nào cần bổ sung?
6. Trong Mono/Flux, vì sao ReactiveSecurityContextHolder phù hợp hơn việc tự đọc ThreadLocal của luồng hiện tại?

**Đáp án gợi ý:** (1) xác thực thành công, thiếu ROLE_ADMIN; (2) BOLA/IDOR, cần kiểm tra owner/tenant; (3) client ngoài trình duyệt không bị CORS ràng buộc; (4) nguy cơ phụ thuộc credential tự gửi; (5) chữ ký, issuer, audience, exp, phân quyền scope, HTTPS và hạn chế lộ/thu hồi token; (6) thực thi reactive có thể đổi thread, còn Reactor Context mang thông tin theo pipeline.

**Kết luận:** Trong Spring Security Reactive, hãy thiết kế tuần tự **xác thực danh tính → phân quyền URL/method/đối tượng → phòng vệ xuyên suốt dữ liệu, trình duyệt và hạ tầng**. Ba nhóm kiểm soát giải quyết những câu hỏi khác nhau và đều cần được kiểm thử trên chính luồng request của ứng dụng.