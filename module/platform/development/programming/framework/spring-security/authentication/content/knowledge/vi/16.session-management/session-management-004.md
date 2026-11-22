# SessionAuthenticationStrategy và trách nhiệm của cơ chế đăng nhập trong Spring Security

## 1. Vì sao cần hiểu SessionAuthenticationStrategy?

Một người dùng gửi username/password và nhận HTTP 200 sau đăng nhập **chưa đủ** để kết luận quy trình quản lý phiên an toàn. Nếu cơ chế đăng nhập được tùy biến, ứng dụng còn phải xác định:

- Session ID cũ có cần thay đổi để chống **session fixation** không?
- Một tài khoản được phép có bao nhiêu session đang hoạt động?
- Có cần ghi session mới vào `SessionRegistry` để phục vụ giới hạn đăng nhập đồng thời không?
- CSRF token đã cấp trước đăng nhập có cần bị làm mới khi danh tính thay đổi không?
- `SecurityContext` sau xác thực có được lưu để những request tiếp theo nhận ra người dùng không?
- Điều gì xảy ra khi một chiến lược session từ chối cho đăng nhập tiếp tục?

Trong Spring Security Servlet, giao diện `SessionAuthenticationStrategy` là điểm mở rộng cho các hành vi liên quan đến `HttpSession` **tại thời điểm một xác thực mới thành công**.

~~~java
public interface SessionAuthenticationStrategy {
    void onAuthentication(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response
    ) throws SessionAuthenticationException;
}
~~~

Ba tham số của `onAuthentication` gồm kết quả `Authentication` đã được xác minh, servlet request và response. Chiến lược **không có nhiệm vụ tự xác minh mật khẩu**, cũng **không tự quyết định người dùng có quyền vào URL**. Đó là trách nhiệm của `AuthenticationManager`/`AuthenticationProvider` và hệ thống authorization.

**Điểm đặc biệt của Spring Security 6:** `SessionManagementFilter` không nằm trong cấu hình mặc định như trước. Vì vậy **cơ chế đăng nhập** (authentication mechanism) thường chịu trách nhiệm gọi `SessionAuthenticationStrategy` khi có xác thực mới. Nếu viết filter/controller đăng nhập tùy chỉnh, không được trông đợi một filter khác sẽ tự phát hiện xác thực và làm hộ tất cả công việc session.

Phạm vi bài này: **Java 17+, Spring Boot 3.x / Spring Security 6.x, ứng dụng Servlet**; tập trung vào lúc đăng nhập thành công, không nhầm với quản lý session tổng quát của servlet container hoặc reactive WebFlux.

## 2. Phân tách chính xác các trách nhiệm

| Thành phần | Trách nhiệm | Không tự làm |
| --- | --- | --- |
| `AuthenticationFilter`, `UsernamePasswordAuthenticationFilter` hoặc filter tự viết | Đọc request đăng nhập, tạo token chưa xác thực, gọi manager, xử lý kết quả | Không tự quyết định mọi chính sách quyền nghiệp vụ |
| `AuthenticationManager` / `AuthenticationProvider` | Xác minh credentials, trả `Authentication` đã xác thực hoặc ném lỗi | Không tự ghi context vào HTTP session chỉ vì trả auth thành công |
| `SessionAuthenticationStrategy` | Tại thời điểm xác thực mới: session fixation, concurrency, CSRF token lifecycle, hành vi liên quan `HttpSession` | Không thay thế lưu `SecurityContext` |
| `SecurityContextHolder` | Giữ `Authentication` trong `SecurityContext` của request/thread đang xử lý | Không bảo đảm request sau có cùng context |
| `SecurityContextRepository` | Lưu/đọc `SecurityContext`, ví dụ qua `HttpSession` | Không tự thay session ID hay quản lý giới hạn phiên |
| `AuthenticationSuccessHandler` | Tạo HTTP response sau khi xác thực thành công | Không tự bảo đảm strategy/repository đã được gọi nếu filter custom quên cấu hình |
| `AuthenticationFailureHandler` | Trả phản hồi cho lỗi xác thực hoặc lỗi session được filter bắt theo hợp đồng | Không thay thế `AuthenticationEntryPoint` đối với request chưa đăng nhập |
| Servlet container | Cấp/quản lý `HttpSession`, cookie `JSESSIONID`, `changeSessionId()` | Không tự quyết định role/permission của Spring Security |
| `AuthorizationFilter` / method security | Quyết định request/method có đủ quyền hay không | Không chịu trách nhiệm đăng nhập hay xoay session ID |

Một luồng đăng nhập có session đầy đủ:

~~~text
POST /login
    |
    v
Authentication Filter
    |
    +-- Tạo Authentication.unauthenticated(...)
    |
    v
AuthenticationManager / Provider
    |
    +-- thất bại -> FailureHandler, không gọi session success strategy
    |
    +-- thành công -> Authentication đã được xác minh
                         |
                         v
             SessionAuthenticationStrategy
               | chống session fixation
               | kiểm tra/đăng ký phiên đồng thời
               | làm mới CSRF token khi thích hợp
                         |
               +-- từ chối phiên -> SessionAuthenticationException
               |                         |
               |                         v
               |                    FailureHandler
               |
               v
       SecurityContextHolder + SecurityContextRepository
                         |
                         v
              AuthenticationSuccessHandler
                         |
                         v
                HTTP response + cookie
                         |
            Request tiếp theo gửi cookie
                         |
                         v
          SecurityContextRepository tải context
                         |
                         v
                   Authorization
~~~

**Thứ tự rất quan trọng:** khi chiến lược phiên từ chối đăng nhập, không nên lưu một context đã đăng nhập hay gửi thông báo thành công. Với `AbstractAuthenticationProcessingFilter`, framework có hook phù hợp để chạy strategy sau `attemptAuthentication` trả kết quả và trước `successfulAuthentication`.

## 3. Hợp đồng của SessionAuthenticationStrategy trong Spring Security 6

`SessionAuthenticationStrategy#onAuthentication` nhận kết quả `Authentication` và có thể:

1. Giữ nguyên request/session nếu không cần thay đổi.
2. Xoay session ID hoặc migrate session khi đăng nhập thành công.
3. Kiểm tra chính sách số phiên của người dùng, từ chối nếu vượt ngưỡng theo policy.
4. Đăng ký phiên vừa xác thực vào `SessionRegistry`.
5. Làm mất hiệu lực CSRF token cũ để đòi token mới sau khi thay danh tính.
6. Ném `SessionAuthenticationException` khi không cho phép tiếp tục xác thực trong session hiện tại.

Không nên gọi chiến lược này trên **mọi request đã xác thực**; nó được thiết kế cho **sự kiện xác thực mới**. Nếu không, việc quay vòng session ID hoặc xóa CSRF token trên mỗi request có thể khiến ứng dụng hoạt động sai và tăng tải.

### Vì sao Spring Security 6 thay đổi cách gọi?

Trong cấu hình phổ biến của Spring Security 5, `SessionManagementFilter` có thể phát hiện một authentication mới bằng cách so sánh `SecurityContextHolder` và `SecurityContextRepository`, rồi gọi session strategy. Cách đó thường cần đọc session mỗi request. Trong Spring Security 6, cơ chế đăng nhập được kỳ vọng gọi strategy **trực tiếp khi vừa xác thực**, giảm việc kiểm tra session không cần thiết trên những request không đăng nhập.

Tài liệu chính thức của Spring Security 6 nói rõ một số tùy chọn thuộc `sessionManagement` DSL trước đây không còn hiệu lực theo cách cũ, ví dụ gắn chiến lược qua `sessionAuthenticationStrategy` tại `SessionManagementFilter`. Với custom authentication filter, hãy dùng hook đúng của filter đó hoặc gọi `onAuthentication` đúng thời điểm trong luồng mà bạn tự sở hữu.

Không kết luận rằng “đã bật `http.sessionManagement(...)` thì tất cả filter custom đều tự nhận cùng strategy”. Cần biết filter cụ thể có gọi nó hay không.

## 4. Những implementation quan trọng

### 4.1. ChangeSessionIdAuthenticationStrategy

`ChangeSessionIdAuthenticationStrategy` sử dụng `HttpServletRequest.changeSessionId()` (Servlet 3.1+) để thay ID phiên hiện có, giữ lại các thuộc tính session phù hợp. Đây là biện pháp ngăn **session fixation**: một kẻ tấn công tìm cách khiến nạn nhân dùng trước một session ID biết sẵn, rồi nạn nhân đăng nhập mà ID không thay đổi.

~~~text
Trước đăng nhập:
  Session ID = S1, chưa authenticated

Sau xác thực thành công:
  Session ID = S2, authentication gắn với phiên S2
  S1 không tiếp tục được dùng làm session của người đã đăng nhập
~~~

Nếu **không có session trước đó**, chiến lược thường không có ID cũ để thay; sau khi đăng nhập, `HttpSessionSecurityContextRepository` có thể tạo session mới khi lưu context. Vì vậy test session fixation phải **chủ động tạo phiên trước login** và so sánh ID trước/sau.

Các lựa chọn khác:
- `SessionFixationProtectionStrategy` có thể invalidation/migrate sang một session mới và chuyển các thuộc tính theo policy.
- Cấu hình mặc định của Spring Security trên servlet container hiện đại thường dùng `changeSessionId`.
- Tắt session fixation protection chỉ vì ứng dụng test không giữ được cookie là cách xử lý không an toàn. Hãy kiểm tra HTTPS, session cookie, proxy và client giữ cookie đúng cách.

### 4.2. ConcurrentSessionControlAuthenticationStrategy

`ConcurrentSessionControlAuthenticationStrategy` sử dụng `SessionRegistry` để kiểm tra số session đang hoạt động của principal, ví dụ tối đa một hoặc hai phiên. Theo chính sách, nó có thể từ chối phiên mới (ném `SessionAuthenticationException`) hoặc đánh dấu phiên cũ hết hiệu lực để phiên mới được phép.

~~~text
User A có 1 session đang hoạt động
Policy maximumSessions=1
  ├── exceptionIfMaximumExceeded=true
  │      -> từ chối login thứ hai
  └── exceptionIfMaximumExceeded=false
         -> cho login mới, phiên cũ được đánh dấu hết hiệu lực
~~~

Đánh dấu hết hiệu lực trong `SessionRegistry` chưa đồng nghĩa servlet container đã lập tức hủy session cookie. Cần thành phần như `ConcurrentSessionFilter` để xử lý request của phiên bị hết hạn và cơ chế dọn dẹp registry. Nếu thiếu `HttpSessionEventPublisher` hoặc cơ chế theo dõi session destroy tương đương, registry có thể giữ phiên “ma”, dẫn đến giới hạn sai.

**Đây là chính sách tùy chọn.** Không phải mọi ứng dụng đều nên giới hạn một phiên vì trình duyệt, thiết bị và account chia sẻ có nhu cầu khác nhau. Quyết định nghiệp vụ, cách nhận diện principal và `SessionRegistry` nhất quán là phần quan trọng của thiết kế.

### 4.3. RegisterSessionAuthenticationStrategy

`RegisterSessionAuthenticationStrategy` đăng ký principal và session ID hiện tại vào `SessionRegistry` **sau khi** đã thông qua kiểm soát đồng thời và bảo vệ session fixation. Nếu đăng ký trước lúc thay ID, registry có thể lưu sai ID hoặc phải sửa thêm.

Thứ tự chiến lược phù hợp khi cần concurrency:

~~~text
ConcurrentSessionControlAuthenticationStrategy
                ↓
ChangeSessionIdAuthenticationStrategy
                ↓
RegisterSessionAuthenticationStrategy
                ↓
CsrfAuthenticationStrategy (nếu dùng)
~~~

`CompositeSessionAuthenticationStrategy` có thể chạy các delegate này theo đúng thứ tự, dừng nếu một delegate ném exception.

### 4.4. CsrfAuthenticationStrategy

`CsrfAuthenticationStrategy` xóa token CSRF hiện tại qua `CsrfTokenRepository` khi xác thực thành công, làm token trước đăng nhập không còn là token được duy trì cho phiên đã xác thực. Điều này cần thiết khi ứng dụng dựa trên **HTTP session cookie** và bảo vệ form/HTTP methods thay đổi dữ liệu bằng CSRF.

Trong flow có CSRF:
1. Client lấy CSRF token trước login.
2. POST login kèm cookie và CSRF token hợp lệ.
3. Authentication thành công, session strategy xóa CSRF token cũ.
4. Client cần lấy token mới trước POST/PUT/PATCH/DELETE tiếp theo (tùy cách render và xử lý token của ứng dụng).

Không dùng `csrf.disable()` làm cách “sửa lỗi 403” khi một request đăng nhập custom thiếu CSRF token. Hãy trả hoặc render token đúng giao thức và gửi nó từ frontend.

### 4.5. CompositeSessionAuthenticationStrategy

`CompositeSessionAuthenticationStrategy` là cách phối hợp nhiều chính sách session mà không tự viết một lớp gọi từng strategy. Nó duyệt các delegate theo thứ tự khai báo:

~~~java
SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        new ChangeSessionIdAuthenticationStrategy(),
        new CsrfAuthenticationStrategy(csrfRepository)
    ));
~~~

Đoạn này **chỉ là mẫu cấu hình**: cần imports, `csrfRepository` và một filter đăng nhập. Nếu strategy đầu ném `SessionAuthenticationException`, strategy sau không chạy; filter phải đưa lỗi vào nhánh failure thích hợp.

### 4.6. NullAuthenticatedSessionStrategy

`NullAuthenticatedSessionStrategy` không thực hiện công việc session khi xác thực. Nó có thể phù hợp với cơ chế xác thực **hoàn toàn stateless**, nhưng **không** tự làm hệ thống stateless: phải cấu hình `SessionCreationPolicy.STATELESS`, repository không dùng session, bearer token được xác minh lại trên từng request, CSRF theo threat model và không có cơ chế xác thực bằng cookie vô tình kích hoạt session.

Không dùng null strategy như “cách tắt lỗi session fixation” trong ứng dụng cookie/session.

## 5. Tích hợp với từng cơ chế đăng nhập: ai phải gọi strategy?

### 5.1. Form login chuẩn

Khi cấu hình `http.formLogin(...)` thông thường, Spring Security tự tạo và cấu hình `UsernamePasswordAuthenticationFilter` và các thành phần liên quan. Trong cơ chế chuẩn này, framework tích hợp chiến lược session như session fixation và các policy mà cấu hình cho phép. Người viết ứng dụng thường không cần gọi `onAuthentication` bằng tay.

~~~java
http.formLogin(form -> form
    .defaultSuccessUrl("/home", true)
    .permitAll()
);
~~~

Đây là **đoạn cấu hình**, không phải chương trình độc lập. Nếu ứng dụng dùng form login chuẩn và cần giới hạn concurrent sessions, hãy ưu tiên cấu hình `sessionManagement` DSL chính thức thay vì tự tạo nhiều `SessionRegistry` không liên quan.

### 5.2. Filter kế thừa AbstractAuthenticationProcessingFilter

Đây là cơ chế demo. Sau khi `attemptAuthentication` trả `Authentication` thành công, filter gọi `SessionAuthenticationStrategy` đã được gắn bằng `setSessionAuthenticationStrategy`; sau đó nó tạo/lưu context và gọi success handler.

~~~java
customFilter.setSessionAuthenticationStrategy(
    compositeSessionStrategy);
customFilter.setSecurityContextRepository(
    securityContextRepository);
~~~

Đây là hai cấu hình **khác nhau, bổ sung cho nhau**. Một cái xử lý session lifecycle; một cái xử lý context persistence.

### 5.3. AuthenticationFilter + AuthenticationConverter

`AuthenticationFilter` phù hợp khi muốn tách bước đọc `HttpServletRequest` thành `AuthenticationConverter`. Tuy nhiên, không được giả định rằng mọi filter có cùng setter và lifecycle. Trong Spring Security 6, `AuthenticationFilter` có `setSecurityContextRepository`; cơ chế session authentication phải được thiết kế rõ, chẳng hạn sử dụng một success handler có trách nhiệm gọi chiến lược session phù hợp **trước khi phản hồi thành công** theo đúng API/lifecycle filter, hoặc chọn một cơ chế đã hỗ trợ hook tương ứng. Nếu thêm logic session trong handler, hãy đảm bảo không gửi 200 trước khi strategy có cơ hội từ chối đăng nhập và xem xét lúc context đã được lưu.

Đối với ứng dụng cần nhiều chính sách session hoặc session fixation nghiêm ngặt, `AbstractAuthenticationProcessingFilter` có hook trực tiếp thường dễ kiểm tra hơn.

### 5.4. Controller tự viết gọi AuthenticationManager

Một endpoint `@PostMapping("/login")` có thể parse JSON với `@RequestBody` rồi gọi `AuthenticationManager`. Nhưng nếu nó không dùng filter đăng nhập chuẩn, ứng dụng phải tự xử lý đầy đủ:
- Kiểm tra CSRF theo cơ chế cookie/session.
- Xác thực và nhận `Authentication`.
- Gọi session strategy đúng thời điểm.
- Tạo `SecurityContext` và lưu qua `SecurityContextRepository`.
- Xử lý `AuthenticationException` và `SessionAuthenticationException` trước khi trả kết quả thành công.
- Không cho phép client tự quyết định principal/roles.

Không chỉ gọi `SecurityContextHolder.getContext().setAuthentication(result)` rồi tin rằng request sau đã đăng nhập: có thể chưa có repository nào lưu context.

### 5.5. OAuth2/OIDC, SAML, remember-me và pre-auth

Các cơ chế sẵn có do Spring Security cấu hình có filter và lifecycle riêng. Không tự chèn một `SessionAuthenticationStrategy` toàn cục chạy trên mọi callback chỉ vì callback xác thực thành công; cần hiểu filter tương ứng, cookie, state, nonce và security context. Khi tùy biến sâu hoặc tự viết cơ chế xác thực, kiểm tra hook/session policy và việc lưu context của cơ chế đó.

Một remember-me authentication được khôi phục từ cookie ở request tiếp theo không giống một đăng nhập tương tác mới bằng form. Không nên vô cớ xoay session ID trên mọi request nhớ đăng nhập.

### 5.6. Resource Server JWT và API stateless

Nếu API dùng bearer JWT gửi **trên từng request** và chính sách là stateless, không có “đăng nhập bằng session” để áp dụng session fixation/concurrent-session control của Servlet. Resource server xác minh token và dựng context cho request hiện tại; session strategy dành cho form cookie thường không liên quan.

Không dùng `SessionAuthenticationStrategy` để điều khiển số JWT còn hoạt động nếu access token không gắn với `HttpSession`; thay bằng TTL, refresh token, rotation, revocation/introspection hoặc token issuance policy.

## 6. Ví dụ hoàn chỉnh Java 17: custom login có session strategy rõ ràng

Để thấy tác dụng của từng bước mà không phụ thuộc hạ tầng IdP, ví dụ dùng **form-urlencoded login qua endpoint custom** `POST /api/login` với username/password trong body. `AuthenticationManager` sử dụng `DaoAuthenticationProvider` và BCrypt. Filter được viết có chủ đích để minh họa việc **tự gắn SessionAuthenticationStrategy**; trong dự án thực nếu form login chuẩn đáp ứng yêu cầu, hãy dùng `formLogin` có sẵn.

Ứng dụng có:
- `GET /api/csrf`: lấy token CSRF và tạo session trước đăng nhập.
- `POST /api/login`: xác thực username/password, thay session ID, làm mới CSRF token và lưu `SecurityContext`.
- `GET /api/me`: tài nguyên chỉ người đã đăng nhập truy cập được.
- Failure handler trả JSON 401; chưa đăng nhập đi vào protected endpoint cũng trả 401 qua entry point.

### 6.1. Cấu trúc và Maven

~~~text
session-strategy-demo/
├── pom.xml
└── src/
    ├── main/java/demo/session/SessionStrategyApplication.java
    └── test/java/demo/session/SessionStrategyApplicationTests.java
~~~

File `pom.xml` dùng **Java 17**, Spring Boot 3.5.7 (quản lý Spring Security 6.5.x):

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
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>session-strategy-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

Khi đưa vào sản phẩm, dùng phiên bản Spring Boot được nhóm duy trì và cập nhật bản vá tương thích. Phiên bản ở đây được cố định để người học có một cấu hình tham chiếu nhất quán.

### 6.2. File Java triển khai

Tạo `src/main/java/demo/session/SessionStrategyApplication.java`:

~~~java
package demo.session;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStrategyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Chỉ dùng để học. Production dùng user store/IdP thích hợp.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        CsrfTokenRepository csrfRepository =
            new HttpSessionCsrfTokenRepository();

        // Chính sách được gọi sau khi credential đã xác minh,
        // trước khi lưu SecurityContext / trả success response.
        SessionAuthenticationStrategy sessionStrategy =
            new CompositeSessionAuthenticationStrategy(
                List.of(
                    new ChangeSessionIdAuthenticationStrategy(),
                    new CsrfAuthenticationStrategy(csrfRepository)
                )
            );

        // Filter này được tạo cục bộ trong SecurityFilterChain,
        // không đăng ký một servlet filter độc lập chạy lần thứ hai.
        ExampleLoginFilter loginFilter = new ExampleLoginFilter(manager);

        loginFilter.setSessionAuthenticationStrategy(sessionStrategy);
        loginFilter.setSecurityContextRepository(contextRepository);

        loginFilter.setAuthenticationSuccessHandler(
            (request, response, authentication) -> {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.getWriter().write(
                    "{\"status\":\"authenticated\"}"
                );
            }
        );

        loginFilter.setAuthenticationFailureHandler(
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.getWriter().write(
                    "{\"error\":\"login_failed\"}"
                );
            }
        );

        http
            .authenticationManager(manager)
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(errors -> errors.authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Chỉ chèn vào Spring Security chain tại vị trí login.
            .addFilterAt(
                loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    static final class ExampleLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        ExampleLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String username = request.getParameter("username");
            String password = request.getParameter("password");
            if (username == null || username.isBlank()
                    || password == null || password.isEmpty()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return getAuthenticationManager().authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password
                )
            );
        }
    }

    @RestController
    static final class Api {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter cung cấp CsrfToken dưới request attribute.
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName()
            );
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            );
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

### 6.3. Vì sao phải cấu hình đủ ba việc?

**Việc 1 — Xác thực:** `ExampleLoginFilter` nhận POST, tạo `UsernamePasswordAuthenticationToken.unauthenticated`, gọi manager. `DaoAuthenticationProvider` dùng `UserDetailsService` + BCrypt để kiểm tra password. Trước thời điểm này không có cơ sở để gắn session với người dùng đã xác thực.

**Việc 2 — Chiến lược phiên:** `loginFilter.setSessionAuthenticationStrategy(sessionStrategy)` nối filter với `ChangeSessionIdAuthenticationStrategy` và `CsrfAuthenticationStrategy`. Vì filter kế thừa `AbstractAuthenticationProcessingFilter`, framework gọi strategy sau khi `attemptAuthentication` thành công. Nếu strategy ném lỗi, request đi vào nhánh thất bại thay vì trả success.

**Việc 3 — Lưu và tải context:** `loginFilter.setSecurityContextRepository(contextRepository)` lưu kết quả khi login thành công; `http.securityContext(...).securityContextRepository(contextRepository)` cung cấp cách đọc lại context ở request tiếp theo. Một `SecurityContextHolder` chỉ sống trong request hiện tại sẽ không đủ nếu không có persistence.

Không phải cứ thay session ID là người dùng đã được đăng nhập. Cũng không phải cứ lưu context là session ID tự động được xoay. Cần cả ba phần theo thiết kế stateful.

### 6.4. Tại sao dùng cùng CSRF repository?

`CsrfFilter` kiểm tra token POST dựa vào `HttpSessionCsrfTokenRepository`. `CsrfAuthenticationStrategy` phải xóa token từ **cùng kiểu kho/cấu hình** để CSRF lifecycle nhất quán. Nếu một nơi dùng cookie repository còn nơi kia dùng session repository, có thể xảy ra tình trạng token không được làm mới như mong đợi.

Ví dụ này cố ý dùng session repository và endpoint `GET /api/csrf` đơn giản để quan sát rõ hành vi. Trong SPA dùng cookie CSRF và JavaScript, có thể cần `CookieCsrfTokenRepository` cùng `CsrfTokenRequestHandler` phù hợp với chính sách SPA. Không chuyển ví dụ này sang production bằng cách sao chép thiết kế CSRF mà chưa kiểm tra frontend, CORS và cookie policy.

## 7. Chạy thử HTTP và quan sát session

Trong thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Chương trình dùng nhiều dependency Spring/Jakarta nên **không biên dịch độc lập bằng `javac`** nếu không dựng classpath. Maven xử lý dependency và lệnh chạy ứng dụng.

### 7.1. Tạo session trước khi đăng nhập

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Response có thể mang `Set-Cookie: JSESSIONID=...` và JSON:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<token-thuc-te>"}
~~~

Giữ cookie và token thật. Không lấy chuỗi placeholder và gửi nguyên văn. Ở bước này session đã tồn tại nhưng chưa chứa người dùng được xác thực.

### 7.2. Gửi yêu cầu đăng nhập

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'X-CSRF-TOKEN: <token-thuc-te>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  http://localhost:8080/api/login
~~~

Khi thông tin đúng, kỳ vọng `200 OK`:

~~~json
{"status":"authenticated"}
~~~

Lưu ý cookie phiên có thể thay đổi sau đăng nhập. Chính client phải nhận `Set-Cookie` mới và tiếp tục gửi cookie mới. Dùng lại ID cũ hoặc bỏ cookie sẽ không chứng minh login thành công được lưu cho request sau.

### 7.3. Gọi tài nguyên sau đăng nhập

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng:

~~~json
{"username":"student"}
~~~

Thử mật khẩu sai với CSRF token hợp lệ sẽ dẫn tới `401 Unauthorized` với body `{"error":"login_failed"}`. POST thiếu token CSRF thường bị `CsrfFilter` từ chối bằng `403 Forbidden` trước khi đến `ExampleLoginFilter`.

Sau khi đăng nhập thành công, hãy gọi lại `GET /api/csrf` với cookie mới để nhận token hợp lệ cho các POST tiếp theo. Nếu đã thiết kế chuyển đổi session ID, test nên kiểm tra session ID thực sự khác trước chứ không chỉ kiểm tra JSON 200.

## 8. Kiểm thử tích hợp đúng trách nhiệm của cơ chế đăng nhập

Một bài test chỉ gọi `AuthenticationManager.authenticate(...)` và thấy password hợp lệ **không chứng minh** session fixation protection hoặc context persistence đã chạy. Cần kiểm tra qua filter chain.

Tạo file `src/test/java/demo/session/SessionStrategyApplicationTests.java`:

~~~java
package demo.session;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStrategyApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRotatesExistingSessionAndPersistsContext()
            throws Exception {

        // Tạo một session chưa đăng nhập bằng endpoint CSRF.
        MvcResult before = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) before.getRequest().getSession(false);
        assertNotNull(session);
        String previousId = session.getId();

        String csrfToken = JsonPath.read(
            before.getResponse().getContentAsString(), "$.token");

        MvcResult login = mvc.perform(post("/api/login")
                .session(session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("X-CSRF-TOKEN", csrfToken)
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);
        assertNotEquals(previousId, afterLogin.getId());

        // Một request MỚI phải đọc lại user từ SecurityContextRepository.
        mvc.perform(get("/api/me").session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void badCredentialsUseFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "incorrect"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void missingCredentialsUseFailureHandler() throws Exception {
        mvc.perform(post("/api/login").with(csrf()))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void missingCsrfIsDeniedBeforeLoginFilter() throws Exception {
        mvc.perform(post("/api/login")
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedEndpointRequiresSessionAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfEndpointReturnsHeaderNameAndToken() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng khi project được dựng đúng:** 6 test qua, không có failure/error. Đây là mã kiểm thử được cung cấp để người học thực thi; không phải khẳng định rằng test đã chạy trong môi trường của người học.

Khi dùng Spring Security Test, `.with(csrf())` giúp giả lập POST hợp lệ. Nhưng để kiểm tra session fixation có ý nghĩa, test đầu tiên dùng **CSRF token và session thật trong cùng luồng MockMvc**, rồi quan sát `changeSessionId()` có đổi ID hay không. Chỉ test “login thành công trả 200” sẽ không phát hiện filter quên gọi session strategy.

Nếu muốn kiểm tra CSRF token rotation, cần xác minh token thực sự lưu trong `CsrfTokenRepository` trước/sau login; lưu ý Spring Security có thể trả **token đã mask** ra HTML/API, nên chỉ so sánh chuỗi hiển thị ở hai request đôi khi không chứng minh backing token đã bị xóa. Hãy bổ sung test repository-level hoặc kiểm tra token cũ bị từ chối sau khi request mới nhận token theo policy đã chọn.

## 9. Trường hợp có giới hạn session đồng thời

Giả sử sản phẩm yêu cầu **một session đang hoạt động cho mỗi tài khoản**. Chỉ thêm `ChangeSessionIdAuthenticationStrategy` chưa đủ; nó chỉ chống fixation, không đếm phiên.

Một cấu hình **minh họa ý tưởng** (chưa phải toàn bộ cấu hình concurrency chạy độc lập) có thể là:

~~~java
SessionRegistry sessionRegistry = new SessionRegistryImpl();

ConcurrentSessionControlAuthenticationStrategy concurrency =
    new ConcurrentSessionControlAuthenticationStrategy(sessionRegistry);
concurrency.setMaximumSessions(1);
concurrency.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        concurrency,
        new ChangeSessionIdAuthenticationStrategy(),
        new RegisterSessionAuthenticationStrategy(sessionRegistry),
        new CsrfAuthenticationStrategy(csrfRepository)
    ));

loginFilter.setSessionAuthenticationStrategy(strategy);
~~~

Các imports liên quan:

~~~java
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.authentication.session.ConcurrentSessionControlAuthenticationStrategy;
import org.springframework.security.web.authentication.session.RegisterSessionAuthenticationStrategy;
~~~

**Những việc bổ sung bắt buộc cân nhắc trong production:**
- Dùng **cùng `SessionRegistry`** cho chiến lược kiểm tra, đăng ký và bộ lọc xử lý phiên hết hạn.
- Cấu hình `ConcurrentSessionFilter` hoặc cơ chế xử lý session expired tương đương; nếu dùng DSL chuẩn, xem cách framework tự cấu hình.
- Đăng ký `HttpSessionEventPublisher` hoặc một listener phù hợp để registry được cập nhật khi session bị destroy.
- Nếu hệ thống chạy nhiều instance, `SessionRegistryImpl` trong RAM mỗi node không đủ để áp dụng giới hạn toàn cluster; dùng cơ chế lưu và kiểm soát phiên phân tán tương thích.
- Xác định `principal.equals/hashCode` ổn định. Hai đối tượng principal của cùng user nhưng không bằng nhau theo `equals` có thể làm bộ đếm phiên sai.
- Khi từ chối vì vượt giới hạn, trả lỗi từ failure handler rõ ràng nhưng không rò thông tin session/thiết bị người dùng khác.
- Đảm bảo hủy phiên sau logout và khi account bị khóa; test cả session hết hạn do timeout.

Thứ tự đề xuất có lý do: kiểm tra concurrency **trước khi tạo/đổi session không cần thiết**, đổi ID để chống fixation, đăng ký ID sau cùng vào registry, rồi xử lý CSRF lifecycle.

## 10. Vì sao không nên tự gọi SessionAuthenticationStrategy hai lần?

Lỗi thường xảy ra khi developer cấu hình chiến lược ở filter *và* gọi thêm trong success handler:

~~~java
// Không làm cả hai trong cùng luồng thành công.
loginFilter.setSessionAuthenticationStrategy(strategy);

loginFilter.setAuthenticationSuccessHandler((req, res, auth) -> {
    strategy.onAuthentication(auth, req, res); // Gọi lần thứ hai!
    res.setStatus(200);
});
~~~

Việc chạy lặp có thể gây:
- Session ID đổi lần hai; cookie/session được quan sát khó hiểu.
- CSRF token tiếp tục bị xoá hoặc bị thay không đúng thời điểm.
- Bộ đếm/registry concurrency được cập nhật hơn một lần hoặc có lỗi điều kiện cạnh tranh.
- Test hoạt động “thỉnh thoảng đúng” tùy thứ tự filter/handler.

**Quy tắc:** xác định rõ **một điểm duy nhất** sở hữu lời gọi `onAuthentication` trong mỗi luồng xác thực mới. Với `AbstractAuthenticationProcessingFilter`, điểm đó thường là hook `setSessionAuthenticationStrategy`. Success handler chỉ chuẩn bị phản hồi sau khi auth/strategy/context hoàn tất.

Không gọi strategy trong `UserDetailsService` hoặc `AuthenticationProvider` vì các lớp này không sở hữu servlet request/response và có thể được dùng ở ngữ cảnh không HTTP.

## 11. Phân biệt SessionAuthenticationException và lỗi mật khẩu

Mặc dù cả hai có thể dẫn tới failure handler, **nguyên nhân và hành động vận hành khác nhau**:

| Tình huống | Nơi phát sinh | Ý nghĩa |
| --- | --- | --- |
| Password sai | `AuthenticationProvider` / `AuthenticationManager` | Không xác thực được danh tính |
| Provider không hỗ trợ token | `ProviderManager` | Sai routing/đăng ký cơ chế xác thực |
| Vượt giới hạn số phiên | `ConcurrentSessionControlAuthenticationStrategy` | Credential có thể đúng, nhưng policy không cho session mới |
| Token CSRF sai/thiếu | `CsrfFilter` | Request thay đổi trạng thái không qua CSRF validation |
| Request tới tài nguyên bảo vệ không có session | `AuthenticationEntryPoint` | Cần xác thực |
| Có session nhưng thiếu authority | Authorization / `AccessDeniedHandler` | Xác thực có rồi nhưng quyền chưa đủ |

Trong API public, có thể giữ thông báo đơn giản như `login_failed` để tránh tiết lộ trạng thái nhạy cảm. Nhưng log nội bộ nên phân biệt sự kiện “bad credentials” và “session limit exceeded” với **mã lỗi an toàn**, không ghi password, CSRF token hoặc session ID đầy đủ.

`SessionAuthenticationException` là một `AuthenticationException` nên `AbstractAuthenticationProcessingFilter` có thể đưa nó vào nhánh xử lý lỗi xác thực thay vì success handler. Nếu tự viết controller/filter, phải bắt và chuyển exception trước khi gửi response thành công; không lưu context trước khi chiến lược phiên từ chối.

## 12. Sai lầm thường gặp và cách sửa

| Sai lầm | Triệu chứng | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `manager.authenticate` rồi trả HTTP 200 | Request sau có thể 401, session fixation chưa được xử lý | Chạy strategy đúng lúc và lưu context |
| Cho rằng `SessionManagementFilter` luôn gọi strategy | Custom login quên session fixation/concurrency | Trong Spring Security 6, authentication mechanism tự chịu trách nhiệm gọi |
| Dùng `http.sessionManagement().sessionAuthenticationStrategy(...)` như cấu hình cũ | Không áp dụng cho filter custom, hoặc bị từ chối | Cấu hình ở hook authentication mechanism cụ thể |
| Chỉ cấu hình `SecurityContextRepository` | Login được nhớ nhưng session ID cũ không được xoay | Bổ sung session fixation strategy |
| Chỉ cấu hình `ChangeSessionIdAuthenticationStrategy` | Xoay ID nhưng request tiếp theo mất auth | Cấu hình lưu/tải `SecurityContext` |
| Dùng `NullAuthenticatedSessionStrategy` cho ứng dụng cookie để né lỗi | Bỏ qua bảo vệ session cần thiết | Chọn policy session đúng và sửa nguyên nhân |
| Gọi `onAuthentication` trên mọi request đã authenticated | Session ID/CSRF bị reset liên tục | Chỉ gọi khi hoàn tất xác thực mới |
| Gọi strategy ở filter và success handler | Xử lý session lặp | Chọn một điểm gọi duy nhất |
| Đặt `RegisterSessionAuthenticationStrategy` trước fixation | Registry có ID phiên chưa đúng | Kiểm tra concurrency → đổi ID → đăng ký session |
| Dùng `ConcurrentSessionControlAuthenticationStrategy` không có registry lifecycle | Phiên cũ không được dọn và đếm sai | Cấu hình registry, filter kiểm tra phiên, session destroy event |
| Dùng một registry RAM trên nhiều instance mà mong chính sách global | Vượt giới hạn giữa các node | Session store/registry phân tán tương thích |
| Coi token CSRF từ trước login dùng mãi được | Request POST sau login 403 | Refresh token khi đăng nhập thành công |
| `csrf.disable()` chỉ vì frontend gửi JSON | Mở bề mặt CSRF khi dùng cookie | Giữ CSRF và gửi token đúng |
| Dựa vào bearer JWT nhưng mong dùng `SessionRegistry` để đếm token | Không có phiên Servlet tương ứng | Dùng cơ chế token issuance/revocation |
| Test login trả 200, không test cookie/session ID | Bỏ sót fixation và context persistence | Tạo session trước, so ID và GET protected resource sau |
| Đăng ký custom filter làm Servlet bean rồi thêm vào SecurityFilterChain | Filter có thể chạy hai lần | Đăng ký một lần ở vị trí đã xác định |
| Dùng `JSESSIONID` qua URL rewriting | Có thể rò session ID trong URL/log/link | Ưu tiên cookie và chính sách servlet phù hợp |
| Dùng HTTP để bảo vệ session cookie đăng nhập | Nguy cơ đánh cắp session | HTTPS xuyên suốt, cookie Secure/HttpOnly/SameSite hợp lý |

## 13. Những câu hỏi về thiết kế thực tế

### Nếu không có session trước khi login?

Khi request POST login không mang session hợp lệ, `ChangeSessionIdAuthenticationStrategy` có thể không có session cũ để thay. `HttpSessionSecurityContextRepository` có thể tạo session mới để lưu authentication nếu chính sách cho phép. Đây không phải failure của session fixation: không tồn tại một ID cũ để kẻ tấn công giữ lại. Muốn xác nhận ID đổi, test phải chủ động tạo session trước login.

### Có thể vừa dùng form login session vừa dùng JWT stateless trong cùng ứng dụng?

Có. Nhưng nên tổ chức thành các `SecurityFilterChain` phù hợp theo endpoint, ví dụ `/web/**` dùng session và CSRF, `/api/**` dùng bearer token stateless; kiểm tra thứ tự `securityMatcher` và repo/CSRF/entry point. Không áp dụng chung một stateful session strategy vào bearer requests rồi tin rằng đã kiểm soát vòng đời token.

### Khi session hết hạn, SessionAuthenticationStrategy có chạy lại?

Không. Nó thường chạy **tại sự kiện xác thực mới**. Request tới URL bảo vệ với cookie session đã hết hạn sẽ bị xử lý như chưa xác thực; nếu yêu cầu đăng nhập lại và thành công, session strategy mới chạy trong lượt xác thực đó. Các `InvalidSessionStrategy` và `SessionInformationExpiredStrategy` phục vụ tình huống riêng liên quan session không hợp lệ hoặc hết hạn do concurrency.

### Session ID đổi có khiến tất cả session attributes bị mất?

`ChangeSessionIdAuthenticationStrategy` sử dụng API `changeSessionId()` trên cùng session và thông thường giữ thuộc tính. Chiến lược invalidate/migrate khác có thể có policy chuyển thuộc tính riêng. Đừng dựa vào giả định “migrate tất cả” nếu ứng dụng lưu dữ liệu nhạy cảm trong session; quyết định rõ thuộc tính nào nên tồn tại sau login.

### Tại sao giới hạn concurrency vẫn không hoạt động dù có strategy?

Có thể thiếu `RegisterSessionAuthenticationStrategy`, `SessionRegistry` thực sự dùng, `ConcurrentSessionFilter`, session destroy notifications, cấu hình principal equality hoặc shared store trên nhiều instance. Nếu dùng DSL chuẩn, kiểm tra nó đã gắn vào **đúng authentication filter**; với filter tự viết, đừng chỉ nhìn dòng `maximumSessions(1)`.

### Có nên cho SessionAuthenticationStrategy tự tạo quyền?

Không. Nó nhận `Authentication` đã thành công để quyết định session-related actions. Quyền phải được nạp/chuẩn hóa bởi hệ thống xác thực/authorization thích hợp trước đó. Việc gọi `onAuthentication` không cấp `ROLE_ADMIN`, không kiểm chứng password và không thay thế `hasAuthority`.

## 14. Checklist kiểm thử trước khi đưa lên production

- [ ] Xác định mọi luồng xác thực (form, custom login, OAuth2, SAML, remember-me, API token), và ai gọi session strategy ở từng luồng.
- [ ] Filter custom chỉ nhận đúng path/method, tạo token chưa xác thực và gọi đúng manager.
- [ ] Chiến lược session chạy **sau** xác thực credential thành công và **trước** response success.
- [ ] Không gọi `onAuthentication` lặp từ hai thành phần khác nhau.
- [ ] Nếu dùng cookie/session, có bảo vệ session fixation; tạo session trước login để test ID đổi.
- [ ] Nếu có concurrency, cấu hình cùng registry, thứ tự control/fixation/register, cleanup và xử lý session expired.
- [ ] Nếu có CSRF, dùng cùng `CsrfTokenRepository` giữa filter và strategy; token cũ được làm mới đúng policy.
- [ ] `SecurityContextRepository` được cấu hình lưu ở login và đọc ở request tiếp theo.
- [ ] Khi login sai hoặc strategy từ chối, không lưu authenticated context và không trả status 200.
- [ ] Test phân biệt 401 do login sai, 401 do unauthenticated resource, 403 do CSRF/authorization và lỗi session limit.
- [ ] Thiết lập HTTPS, cookie flags, session TTL, logout, invalidation, trusted proxies và an toàn redirect.
- [ ] Với deployment đa instance, bảo đảm session/registry có chiến lược phân tán và refresh/invalidation.
- [ ] Với JWT stateless, xác minh token mỗi request và không mặc nhiên tạo HTTP session.
- [ ] Có metrics/log an toàn về login thành công/thất bại, rotation và policy session, không log secrets.

## 15. Câu hỏi tự kiểm tra

1. `SessionAuthenticationStrategy` có phải thành phần đối chiếu mật khẩu không? Vì sao?
2. Spring Security 6 thay đổi điều gì về vai trò mặc định của `SessionManagementFilter`?
3. Tại sao custom login filter cần biết **lúc nào** gọi `onAuthentication`?
4. Khác biệt giữa `SecurityContextRepository` và `ChangeSessionIdAuthenticationStrategy` là gì?
5. Vì sao test session fixation cần có session trước khi gửi POST login?
6. Nếu có `maximumSessions=1`, tại sao phải có cả control, registration, expired-session handling và cleanup?
7. Điều gì xảy ra nếu một strategy trong `CompositeSessionAuthenticationStrategy` ném `SessionAuthenticationException`?
8. Với cookie session, vì sao cần CSRF token mới sau đăng nhập thành công?
9. Khi nào `NullAuthenticatedSessionStrategy` có thể là một lựa chọn phù hợp, và nó có tự biến ứng dụng thành stateless không?
10. Làm sao phân biệt lỗi login do credential, lỗi session limit và request tới protected endpoint chưa có session?
11. Vì sao một success handler trả 200 không đủ đảm bảo context đã được lưu?
12. Nếu một ứng dụng có cả web form và JWT bearer, có nên dùng một session strategy giống nhau cho mọi request không?

## 16. Tài liệu tham khảo

1. Spring Security 6.5 — Authentication Persistence and Session Management (mốc thay đổi Spring Security 6, session fixation): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
2. Spring Security 6.5 API — `SessionAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html
3. Spring Security 6.5 API — `CompositeSessionAuthenticationStrategy` và thứ tự delegate: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html
4. Spring Security 6.5 API — `AbstractAuthenticationProcessingFilter` (success lifecycle, session strategy, repository): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
5. Spring Security 6.5 — Concurrent Sessions Control: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_concurrent_sessions
6. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
7. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
8. Spring Security 6.5 API — `ChangeSessionIdAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html
9. Spring Security 6.5 API — `CsrfAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html

**Nguyên tắc cần nhớ:** `SessionAuthenticationStrategy` là một bước của **sự kiện đăng nhập mới**, và trong Spring Security 6, **cơ chế xác thực phải đảm bảo nó được gọi đúng lúc**. Khi dùng session cookie, hãy nối đầy đủ xác thực credential, quản lý phiên, lưu `SecurityContext` và xử lý response; đừng nhầm các trách nhiệm này thành một thao tác duy nhất.