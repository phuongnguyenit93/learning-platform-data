# Luồng yêu cầu từ trình duyệt đến bộ lọc bảo mật, MVC và tầng nghiệp vụ

## 1. Mục tiêu và bức tranh tổng thể

Trong ứng dụng **Spring Boot dùng Servlet stack** (ví dụ Spring MVC trên Tomcat), một HTTP request không đi thẳng từ trình duyệt vào `@RestController`. Servlet container đưa request qua các `Filter` đã đăng ký; Spring Security thường tham gia ở đây, **trước** khi `DispatcherServlet` chọn controller. Sau khi request vượt qua bước bảo mật ở cấp HTTP, mã MVC và tầng nghiệp vụ mới xử lý yêu cầu. Cơ chế kiểm soát quyền ở cấp phương thức hoặc dữ liệu có thể tiếp tục chạy **bên trong tầng nghiệp vụ**.

Ví dụ xuyên suốt: trình duyệt hoặc HTTP client gọi `GET /orders/42`. Hệ thống cần phân biệt: ai đang gọi, họ có được gọi đường dẫn này không, và họ có quyền xem **đơn hàng 42 cụ thể** hay không.

~~~text
Trình duyệt / HTTP client
    |  HTTPS request: method, path, headers, cookies, body
    v
Reverse proxy / TLS termination (nếu có)
    |
    v
Servlet container (Tomcat/Jetty; tạo HttpServletRequest/Response)
    |
    v
Các Servlet Filter, trong đó thường có:
  DelegatingFilterProxy("springSecurityFilterChain")
    -> FilterChainProxy
       -> SecurityFilterChain phù hợp với request
          -> các Spring Security filter
    |
    | request được phép đi tiếp
    v
DispatcherServlet (Spring MVC)
    -> HandlerMapping / HandlerAdapter
    -> Controller (parse input, validate, gọi service)
    -> Service (nghiệp vụ, kiểm tra quyền trên tài nguyên)
    -> Repository / database / hệ thống ngoài
    |
    v
HTTP response quay ngược qua MVC, Servlet filters và container
    |
    v
Trình duyệt / HTTP client
~~~

**Phân biệt phạm vi:** tài liệu này mô tả Spring Security trên **Servlet stack** (`SecurityFilterChain`, `HttpSecurity`, `HttpServletRequest`). Với Spring WebFlux, pipeline là `WebFilter`/`SecurityWebFilterChain` và xử lý reactive, không áp dụng nguyên xi các lớp Servlet ở trên.

## 2. Ai chịu trách nhiệm ở từng lớp?

| Thành phần | Vai trò khi xử lý request | Không nên hiểu nhầm |
| --- | --- | --- |
| Trình duyệt/client | Gửi URL, method, cookie phiên, header `Authorization`, body | Cookie có mặt không tự chứng minh người dùng đã xác thực |
| Servlet container | Nhận HTTP, tạo đối tượng Servlet request/response, chạy chuỗi filter | Container không tự áp dụng toàn bộ quy tắc Spring Security |
| `DelegatingFilterProxy` | Là cầu nối từ cơ chế Servlet Filter đến Spring bean `springSecurityFilterChain` | Đây không phải nơi định nghĩa từng quyền truy cập |
| `FilterChainProxy` | Chọn Spring Security `SecurityFilterChain` phù hợp và điều phối filter bảo mật | Một request không mặc định chạy **mọi** chain |
| Authentication filters/provider | Đọc credentials phù hợp, xác minh danh tính, thiết lập `Authentication` | Có authentication không có nghĩa được truy cập mọi tài nguyên |
| `AuthorizationFilter` | Kiểm tra quyền truy cập HTTP theo `authorizeHttpRequests` | Không tự bảo đảm quyền sở hữu từng bản ghi |
| `ExceptionTranslationFilter` | Chuyển ngoại lệ bảo mật từ phần downstream thành phản hồi 401/403 hoặc chuyển hướng đăng nhập thích hợp | Không phải filter thực hiện xác thực hay tự ra quyết định cấp quyền |
| `DispatcherServlet` + controller | Chọn handler, binding/validation, gọi service, tạo response | Controller không phải điểm bảo vệ duy nhất |
| Service/repository | Thực hiện nghiệp vụ, kiểm tra quy tắc theo tài nguyên, đọc/ghi dữ liệu | Đã qua security filter chưa đủ để bỏ kiểm tra ownership |

Servlet `Filter` và Spring MVC `HandlerInterceptor` là hai cơ chế khác nhau. Interceptor chạy trong quá trình MVC dispatch, sau khi request đã qua các filter ở phía trước; vì vậy authentication/authorization HTTP nên đặt ở Spring Security filter chain, còn các quy tắc nghiệp vụ nên được bảo vệ tại service.

## 3. Theo dấu request: từ trình duyệt đến controller

### Bước 1 — Client tạo HTTP request

Một request chứa method (`GET`, `POST`...), path (`/orders/42`), headers, body nếu có, và có thể có cookie hoặc header thông tin xác thực. Dùng **HTTPS** để bảo vệ thông tin trên đường truyền. Với session-based login, trình duyệt thường gửi cookie mang **session ID**, còn trạng thái đăng nhập nằm ở phía server. Với bearer token, client gửi `Authorization: Bearer <token>` và server xác minh token theo cấu hình. HTTP Basic gửi thông tin đăng nhập được mã hóa Base64, **không phải mã hóa bảo mật**; chỉ sử dụng qua HTTPS.

Reverse proxy có thể xử lý TLS và chuyển request về ứng dụng. Khi đọc địa chỉ client hoặc scheme từ `Forwarded`/`X-Forwarded-*`, chỉ tin header do proxy đáng tin cậy kiểm soát; không dựa vào giá trị client tự khai để quyết định quyền.

### Bước 2 — Servlet container gọi Filter trước MVC

Container chọn các Servlet filter tương ứng với URL và dispatcher type. Trong cấu hình Spring Boot/Spring Security thông dụng có `DelegatingFilterProxy` trỏ đến bean tên `springSecurityFilterChain`. Bean này thường là `FilterChainProxy`, bên trong quản lý một hoặc nhiều `SecurityFilterChain`.

Tên dễ nhầm:

- **Servlet filter chain:** chuỗi filter do container quản lý, có thể bao gồm logging, encoding và `DelegatingFilterProxy`.
- **Spring Security filter chain:** các security filter bên trong `FilterChainProxy`.
- **`SecurityFilterChain`:** cấu hình một chuỗi security filter áp dụng cho tập request cụ thể.

Một request có thể đi qua nhiều Servlet filter, nhưng `FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp** theo thứ tự. Nếu dùng nhiều chain, `securityMatcher(...)` xác định phạm vi chọn chain; `requestMatchers(...)` trong `authorizeHttpRequests` quy định quyền **bên trong chain đã chọn**. Thiếu chain bao phủ một URL có thể khiến URL đó không được Spring Security bảo vệ.

### Bước 3 — Các security filter làm việc

Thứ tự filter thực tế tùy cấu hình và cơ chế đăng nhập. Những vai trò thường gặp trong Spring Security 6 gồm:

1. **Security context:** `SecurityContextHolderFilter` tải hoặc chuẩn bị `SecurityContext` theo `SecurityContextRepository`. `SecurityContextHolder` cho phép code trong request tra cứu `Authentication` hiện hành. Ở Spring Security 6, không được giả định mọi thay đổi context sẽ tự động được lưu: cơ chế đăng nhập phù hợp cần lưu context khi muốn duy trì trạng thái.
2. **HTTP security headers, CORS, CSRF:** khi được cấu hình, các filter liên quan xử lý header bảo vệ, CORS và CSRF. CSRF đặc biệt quan trọng với request thay đổi trạng thái khi trình duyệt tự động gửi credentials như cookie phiên.
3. **Authentication:** tùy ứng dụng, `UsernamePasswordAuthenticationFilter` xử lý form login, `BasicAuthenticationFilter` xử lý HTTP Basic, `BearerTokenAuthenticationFilter` xử lý bearer token. Không phải tất cả đều có mặt trong mọi ứng dụng.
4. **Anonymous authentication:** khi chưa có danh tính xác thực, `AnonymousAuthenticationFilter` có thể đặt một đối tượng authentication ẩn danh. Vì vậy chỉ kiểm tra `getAuthentication() != null` là **không đủ** để kết luận người dùng đã đăng nhập.
5. **Authorization:** `AuthorizationFilter` áp dụng quy tắc như `permitAll()`, `authenticated()`, `hasRole(...)`. Nó có thể từ chối request trước khi MVC được gọi.
6. **Exception translation:** `ExceptionTranslationFilter` xử lý các `AuthenticationException` hoặc `AccessDeniedException` phát sinh trong phần filter/downstream mà nó bao quanh, qua `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`.

Đây là **các vai trò**, không phải sơ đồ thứ tự chính xác cho mọi cấu hình. Chẳng hạn `ExceptionTranslationFilter` cần nằm phía trước `AuthorizationFilter` theo chiều gọi để bắt ngoại lệ do authorization phía sau ném ra.

Authentication thường có luồng riêng:

~~~text
Authentication filter đọc credentials
   -> AuthenticationManager (thường ProviderManager)
   -> AuthenticationProvider thích hợp
      -> UserDetailsService + PasswordEncoder (ví dụ user/password)
      hoặc JwtDecoder / token validation (ví dụ JWT)
   -> Authentication hợp lệ + authorities
   -> SecurityContextHolder giữ Authentication cho request
   -> cơ chế phù hợp lưu SecurityContext nếu cần duy trì login
~~~

`principal` là danh tính (thường là username/user object); `authorities` là các quyền (ví dụ `ROLE_USER`). Với `hasRole("ADMIN")`, quy ước mặc định tương đương tìm authority `ROLE_ADMIN`; không nên tự thêm tiền tố `ROLE_` hai lần vào `hasRole`.

### Bước 4 — Quyết định cho request đi tiếp hay chặn

Cần tách ba câu hỏi:

1. **Authentication:** client là ai? Credentials có hợp lệ không?
2. **HTTP authorization:** danh tính đó có được vào `/orders/**` không?
3. **Resource/business authorization:** người này có được đọc **order ID 42** hay không?

Nếu chính sách HTTP yêu cầu `authenticated()` mà request chưa được xác thực, Spring Security thường gọi entry point: với API dùng HTTP Basic/bearer là **401 Unauthorized**; với form login trên web có thể là **302 redirect** đến trang login. Nếu user đã xác thực nhưng thiếu quyền, phản hồi thường là **403 Forbidden**. Chi tiết phụ thuộc authentication entry point và access denied handler được cấu hình.

Nếu authentication/authorization thất bại ở filter, **controller và service không chạy**. Với một request thành công ở lớp filter, lời gọi tiếp tục đến Servlet/MVC; điều đó **không bảo đảm** controller có mapping tương ứng, request hợp lệ, hay user sở hữu bản ghi được yêu cầu.

### Bước 5 — DispatcherServlet chuyển request vào MVC

`DispatcherServlet` là front controller của Spring MVC. Nó dùng `HandlerMapping` tìm handler phù hợp với path/method; `HandlerAdapter` gọi controller cùng các resolver cho `@PathVariable`, `@RequestParam`, `@RequestBody`, validation... Nếu không có mapping, kết quả thường là 404 (tùy cấu hình và các filter có thể đã chặn trước đó).

Ví dụ:

~~~java
@GetMapping("/orders/{id}")
public String getOrder(@PathVariable long id) {
    return orderService.findOrderForCurrentUser(id);
}
~~~

Controller ở đây nhận ID và **giao việc cho service**. Không nên tin các trường như `userId` do client gửi chỉ vì request đã qua `authenticated()`.

### Bước 6 — Service thực hiện nghiệp vụ và kiểm tra quyền trên dữ liệu

Ở service, một phương thức có thể được bảo vệ bằng Spring Method Security (ví dụ `@PreAuthorize` khi có `@EnableMethodSecurity`). Ngoài kiểm tra role, phải bảo đảm quy tắc sở hữu hoặc phạm vi truy cập trên **đúng tài nguyên**. Ví dụ một user xác thực thành công vẫn không được lấy `/orders/42` nếu order đó thuộc user khác.

Một hướng phòng lỗi IDOR/BOLA là ràng buộc query theo user/tenant hiện hành, ví dụ về ý tưởng: `findByIdAndOwnerId(orderId, currentUserId)`, hoặc kiểm tra ownership rõ ràng trước khi trả dữ liệu. Đối với method security dùng proxy, lời gọi **qua Spring bean/proxy** mới được chặn như kỳ vọng; tự gọi phương thức có annotation bên trong cùng instance (self-invocation) thường bỏ qua proxy.

Tầng repository truy xuất dữ liệu; `@Transactional` quản lý giao dịch nếu có, **không tự thay thế quy tắc phân quyền**. Lỗi input, dữ liệu không tồn tại, lỗi nghiệp vụ hoặc lỗi cơ sở dữ liệu có thể trở thành các mã HTTP khác nhau tùy cách controller/exception handler chuyển đổi.

### Bước 7 — Trả response theo chiều ngược lại

Controller/MVC ghi HTTP status, headers và body; servlet filter kết thúc theo thứ tự gọi ngược lại, có thể bổ sung headers, lưu hoặc dọn context theo cơ chế tương ứng, rồi container gửi response. Với luồng thông thường, context bảo mật gắn với xử lý request được dọn sau khi request kết thúc, tránh rò danh tính sang request khác trên thread tái sử dụng.

Các trường hợp async/error dispatch có thể đi qua các dispatcher type và filter khác nhau theo cấu hình. Khi debug một request được forward, lỗi 404/500, hoặc xử lý bất đồng bộ, cần xác định **dispatcher type** và không mặc định filter chỉ chạy đúng một lần.

## 4. Ví dụ hoàn chỉnh: Spring Boot 3.x / Spring Security 6.x

Ví dụ sau dùng Java 17+, Spring MVC, HTTP Basic và user lưu trong bộ nhớ **chỉ để quan sát đường đi**. Nó minh họa rõ ranh giới: filter quyết định đã đăng nhập hay chưa; service kiểm tra order cụ thể thuộc user nào. Chỉ dùng credential `{noop}` trong demo nội bộ; ứng dụng thật cần password hashing, database/identity provider và HTTPS.

Cấu trúc:

~~~text
security-flow/
├── pom.xml
└── src/main/java/com/example/flow/
    ├── SecurityFlowApplication.java
    ├── SecurityConfig.java
    ├── OrderController.java
    └── OrderService.java
~~~

**`pom.xml`**

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
    <artifactId>security-flow</artifactId>
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

**`SecurityFlowApplication.java`**

~~~java
package com.example.flow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }
}
~~~

**`SecurityConfig.java`**

~~~java
package com.example.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password("{noop}pass").roles("USER").build(),
            User.withUsername("bob").password("{noop}pass").roles("USER").build()
        );
    }
}
~~~

`authorizeHttpRequests` bảo vệ đường dẫn trước MVC. `permitAll()` cho phép vào endpoint công khai nhưng request vẫn có thể đi qua Spring Security filter chain. `authenticated()` xác nhận có danh tính đăng nhập; không kiểm tra ownership của order. `anyRequest().denyAll()` đóng những đường dẫn chưa khai báo. Cấu hình vẫn **giữ CSRF mặc định**; các endpoint minh họa đều chỉ dùng GET. Không nên suy từ ví dụ này rằng mọi API dùng Basic đều được tắt CSRF, đặc biệt khi trình duyệt có thể tự gửi credentials.

**`OrderController.java`**

~~~java
package com.example.flow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "OK public";
    }

    @GetMapping("/orders/{id}")
    String order(@PathVariable long id) {
        return orderService.findOrderForCurrentUser(id);
    }
}
~~~

**`OrderService.java`**

~~~java
package com.example.flow;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class OrderService {

    @PreAuthorize("isAuthenticated()")
    public String findOrderForCurrentUser(long id) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        // Giả lập dữ liệu: chỉ có order 42, thuộc alice.
        if (id != 42) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }
        if (!"alice".equals(authentication.getName())) {
            throw new AccessDeniedException("Not the order owner");
        }
        return "Order 42 belongs to alice";
    }
}
~~~

`@EnableMethodSecurity` bật cơ chế chặn `@PreAuthorize` khi controller gọi bean service qua Spring proxy. Check trong service là bản demo để dễ quan sát; hệ thống thật nên xác định chủ sở hữu từ database và principal tin cậy, có chính sách ẩn thông tin tồn tại tài nguyên khi phù hợp.

Chạy trong thư mục có `pom.xml` (cần JDK 17+ và Maven, tải dependency lần đầu cần mạng):

~~~bash
mvn spring-boot:run
~~~

Kiểm tra từng trường hợp bằng `curl`; để chỉ lấy status code (không phụ thuộc header động), dùng:

~~~bash
curl -s http://localhost:8080/public
# OK public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/orders/42
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u alice:pass http://localhost:8080/orders/42
# 200

curl -s -u alice:pass http://localhost:8080/orders/42
# Order 42 belongs to alice

curl -s -o /dev/null -w '%{http_code}\n' -u bob:pass http://localhost:8080/orders/42
# 403

curl -s -o /dev/null -w '%{http_code}\n' -u alice:pass http://localhost:8080/orders/999
# 404
~~~

Các dòng bắt đầu bằng `#` ở đây là **kết quả dự kiến**/chú thích cho từng lệnh, không phải output được đo từ môi trường hiện tại. Với Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần. Server mặc định lắng nghe cổng 8080 nếu cấu hình chưa thay đổi.

### Đọc đường đi ở 5 tình huống

| Request | Filter bảo mật | MVC/service | Kết quả dự kiến |
| --- | --- | --- | --- |
| `GET /public` không credentials | `permitAll` | Controller trả chuỗi | 200 |
| `GET /orders/42` không credentials | Yêu cầu authenticated; entry point Basic xử lý | Không vào controller | 401 |
| `GET /orders/42` với alice | Xác thực Basic thành công; `authenticated` đạt | Controller → service; owner là alice | 200 |
| `GET /orders/42` với bob | Authenticated nên **qua được** policy đường dẫn | Service phát hiện không phải owner, ném `AccessDeniedException` | 403 |
| `GET /orders/999` với alice | Xác thực và policy đường dẫn đều đạt | Service không tìm thấy order | 404 |

Lưu ý trường hợp bob: nếu chỉ kiểm tra `.authenticated()`, ứng dụng sẽ không chặn quyền trên order. Đây là lý do cần phân biệt **HTTP authorization** với **quyền trên đối tượng nghiệp vụ**.

## 5. Những điểm dễ nhầm trong ứng dụng thật

### 401, 403, 404 và 400/500 đến từ các lớp khác nhau

- **401 Unauthorized:** request chưa được xác thực hợp lệ cho một tài nguyên yêu cầu đăng nhập; thường có `WWW-Authenticate` trong API dùng HTTP Basic/bearer.
- **403 Forbidden:** user đã xác thực nhưng thiếu quyền; cũng có thể do CSRF token sai/thiếu trên request cần CSRF.
- **404 Not Found:** sau khi request vượt được bảo vệ thích hợp, MVC không có mapping hoặc tầng dữ liệu không tìm thấy; tùy thiết kế có thể trả 404 để tránh tiết lộ tài nguyên tồn tại.
- **400 Bad Request:** sai định dạng input, binding, validation... thường do MVC xử lý khi request đã đi đủ xa.
- **500 Internal Server Error:** lỗi chưa được xử lý thích hợp; không nên biến mọi lỗi service thành 401/403.

Không thể suy ra lớp lỗi **chỉ từ status code**, vì ứng dụng có thể cấu hình entry point, error handler và exception mapping riêng. Hãy kết hợp status với log, dispatcher type và trace thực tế.

### CORS và CSRF không thay thế authentication/authorization

**CORS** là chính sách trình duyệt cho phép JavaScript từ origin nào đọc response; một preflight `OPTIONS` thường không chứa credentials. Khi dùng CORS, cần cấu hình xử lý preflight đúng thứ tự so với auth (ví dụ `http.cors(...)` kèm cấu hình CORS thích hợp). CORS **không** biến endpoint thành được bảo vệ và không chặn client không phải trình duyệt.

**CSRF** bảo vệ các request có khả năng thay đổi trạng thái trước hành động ngoài ý muốn khi trình duyệt tự mang theo credentials. Với session/cookie, thường giữ bảo vệ CSRF cho POST/PUT/PATCH/DELETE. Một API sử dụng bearer token chỉ được client chủ động gắn vào header và không dùng credentials tự gửi có thể có mô hình CSRF khác, nhưng phải xem xét đầy đủ cơ chế xác thực trước khi tắt. GET chỉ nên đọc dữ liệu, không gây thay đổi trạng thái.

### Session, bearer token và “đã đăng nhập”

- **Session-based:** cookie thường chỉ mang ID; server dùng `HttpSession`/`SecurityContextRepository` để liên kết request với trạng thái đăng nhập khi cấu hình phù hợp.
- **Bearer token:** filter xác minh token trên mỗi request theo cấu hình; không nên mặc định token phải gắn với HTTP session.
- **Basic authentication:** request mang credentials; `Authorization: Basic ...` không tự trở thành session login.
- **Anonymous:** có thể có `Authentication` kiểu anonymous trong context. Muốn yêu cầu user thật, dùng `authenticated()`/method security phù hợp thay vì kiểm tra chỉ khác null.

Một lớp authorization HTTP không bảo đảm các quyền ở cấp owner, tenant hoặc phạm vi dữ liệu. Ngược lại, `@PreAuthorize` tại service không thay thế các quy tắc HTTP cho endpoint cần chặn từ đầu.

### `permitAll` khác với bỏ qua security chain

`requestMatchers("/public").permitAll()` vẫn để request đi qua security chain, nên những filter và security headers thích hợp có thể còn hoạt động. Cấu hình `web.ignoring()` bỏ qua toàn bộ Spring Security filter chain cho request khớp; dùng thiếu cân nhắc sẽ làm mất các bảo vệ cấp filter. Với endpoint công khai thông thường, ưu tiên `permitAll`.

### Khi có nhiều SecurityFilterChain

`@Order` quyết định thứ tự các chain, và `securityMatcher` xác định request có thuộc một chain hay không. Chain khớp đầu tiên được chọn; quy tắc bên trong chain không được lấy từ chain khác. Khi tạo chain riêng cho `/api/**`, cần xem request nào không khớp bất kỳ chain và có chain dự phòng bao phủ phần còn lại hay không.

## 6. Cách debug một request đi sai đường

1. **Xác định request thật:** method, path, query, origin, có cookie/`Authorization` hay không; tuyệt đối không ghi nguyên password/token vào log.
2. **Kiểm tra phản hồi:** status, `WWW-Authenticate`, `Location` (redirect), CORS headers, CSRF-related errors. Nếu là 401/403, xác định cơ chế nào đã từ chối.
3. **Kiểm tra chain khớp:** nếu nhiều `SecurityFilterChain`, xem `securityMatcher` và thứ tự `@Order`. Nhớ phân biệt `securityMatcher` với `requestMatchers`.
4. **Theo dấu identity:** kiểm tra authentication provider/filter có chạy không, principal/authorities là gì; không xem sự hiện diện của anonymous là login thành công.
5. **Nếu đã qua filter:** kiểm tra MVC mapping, binding/validation, `@PreAuthorize` và quyền owner/tenant trong service; kiểm tra dữ liệu thực tế.
6. **Quan sát log có kiểm soát:** trong môi trường phát triển, có thể cấu hình `logging.level.org.springframework.security=DEBUG` để thấy thông tin chain/ủy quyền. Không bật log nhạy cảm bừa bãi trên production, không in secrets/cookies đầy đủ.

Một dấu hiệu phân tách hữu ích: nếu controller không được gọi, kiểm tra filter/chain và mapping trước. Nếu controller được gọi nhưng service từ chối, kiểm tra method security hoặc quy tắc dữ liệu. Tuy nhiên lỗi MVC mapping, CORS, CSRF hay exception handler vẫn có thể khiến quan sát ban đầu phức tạp hơn, nên dựa vào trace chứ không suy đoán tuyệt đối.

## 7. Tự kiểm tra hiểu biết

**Hỏi:** User đã xác thực và vượt qua `.requestMatchers("/orders/**").authenticated()` thì có xem được mọi order không?

**Đáp:** Không. Quy tắc này chỉ yêu cầu đã đăng nhập ở cấp HTTP; service/repository vẫn cần kiểm tra user có quyền trên order được hỏi.

**Hỏi:** Vì sao `GET /orders/42` không credentials có thể trả 401 mà không log vào controller?

**Đáp:** Security filter chain xử lý trước `DispatcherServlet`; `AuthorizationFilter` từ chối request cần authentication, `ExceptionTranslationFilter` dẫn đến Basic authentication entry point.

**Hỏi:** `HandlerInterceptor` của Spring MVC có tương đương Spring Security filter không?

**Đáp:** Không. MVC interceptor chạy trong quá trình dispatch của MVC; security filter có thể chặn request ở lớp Servlet trước khi bất kỳ controller nào chạy.

**Nhớ đường đi:** **Client → Servlet filters → Spring Security authentication/HTTP authorization → DispatcherServlet/MVC → service + quyền theo dữ liệu → repository → response**. Mỗi lớp giải quyết một trách nhiệm riêng; kết quả cuối chỉ an toàn khi các lớp cùng thực hiện đúng chính sách.