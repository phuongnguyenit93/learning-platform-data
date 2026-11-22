# Sự kiện xác thực thành công, thất bại và điểm mở rộng xử lý trong Spring Security Servlet

## Mục tiêu

Trong Spring Security Servlet, một lần xác thực có thể đi qua AuthenticationFilter hoặc UsernamePasswordAuthenticationFilter, AuthenticationManager, AuthenticationProvider, SecurityContext và cuối cùng là HTTP response. Ngoài việc trả về một Authentication hợp lệ hay ném AuthenticationException, hệ thống còn có các **sự kiện xác thực (authentication events)** và **điểm mở rộng (extension points)** để ghi nhật ký, đo lường, điều hướng người dùng hoặc phản hồi lỗi.

Sau bài học, bạn có thể:

1. Theo dõi đường đi của xác thực thành công và thất bại trong cơ chế form login sử dụng Spring Security 6.
2. Phân biệt AuthenticationSuccessEvent, các sự kiện con của AbstractAuthenticationFailureEvent và InteractiveAuthenticationSuccessEvent.
3. Hiểu vai trò của AuthenticationEventPublisher/DefaultAuthenticationEventPublisher so với AuthenticationSuccessHandler/AuthenticationFailureHandler.
4. Đăng ký listener bằng @EventListener hoặc ApplicationListener và chọn đúng nơi xử lý HTTP response.
5. Viết ví dụ Spring Boot + Java 17 có form login, listener audit, success/failure handler, kiểm thử MockMvc với CSRF.
6. Phân biệt lỗi **xác thực** (authentication), lỗi **phân quyền** (authorization), lỗi CSRF và những trường hợp không phát ra sự kiện bạn mong chờ.
7. Thiết kế logging, telemetry và xử lý mở rộng không làm lộ credential hoặc ảnh hưởng quá trình đăng nhập.

Phạm vi: ứng dụng Spring Boot 3.x, Spring Security 6.x trên **Servlet stack** (Spring MVC), Java 17 trở lên. Các ví dụ dùng SecurityFilterChain/HttpSecurity hiện đại; không dùng cấu hình WebSecurityConfigurerAdapter đã bị loại bỏ và không áp dụng trực tiếp cho WebFlux.

## 1. Authentication thành công/thất bại được định nghĩa ở đâu?

Spring Security gọi **authentication** là việc xác minh danh tính hoặc thông tin xác thực. Một Authentication trong SecurityContext đại diện cho người dùng/chủ thể mà security framework đã tiếp nhận. **Authorization** là bước sau đó: quyết định chủ thể đã xác thực có được làm một hành động hay truy cập endpoint không.

Ví dụ:

- Đúng tên đăng nhập và mật khẩu trong POST /login: quá trình xác thực thành công.
- Sai mật khẩu trong POST /login: xác thực thất bại, thường gắn với BadCredentialsException.
- Người đã đăng nhập, thiếu vai trò ADMIN khi gọi /admin: xác thực có thể đã thành công, nhưng **phân quyền thất bại**. Đây không nhất thiết là AuthenticationFailureEvent.
- POST /login thiếu CSRF token khi CSRF protection được bật: request có thể bị CsrfFilter chặn **trước** khi AuthenticationManager được gọi. Đây không phải thất bại mật khẩu và không nhất thiết phát sinh sự kiện thất bại xác thực.
- GET /private khi chưa đăng nhập: có thể chuyển hướng đến /login mà chưa có một lần nỗ lực xác thực bằng credentials nào.

Vì vậy không lấy mọi HTTP 401/403/302 làm số lượng authentication failure. Sự kiện có nghĩa cụ thể ở tầng nơi nó được phát.

## 2. Sơ đồ luồng cho form login

Với cấu hình formLogin và UsernamePasswordAuthenticationFilter, một luồng điển hình:

~~~text
Trình duyệt: POST /login (username, password, CSRF token)
    |
Servlet container / FilterChainProxy / SecurityFilterChain
    |
CsrfFilter: kiểm tra token nếu phương thức yêu cầu
    |
UsernamePasswordAuthenticationFilter: đọc credentials
    |
AuthenticationManager (thường ProviderManager)
    |
AuthenticationProvider (ví dụ DaoAuthenticationProvider)
    |                                |
    | THÀNH CÔNG                     | THẤT BẠI
    v                                v
Authentication hợp lệ             AuthenticationException
    |                                |
AuthenticationEventPublisher      AuthenticationEventPublisher
    |                                |
AuthenticationSuccessEvent (*)    AuthenticationFailure...Event (*)
    |                                |
Filter hoàn tất các bước            unsuccessfulAuthentication(...)
thành công theo cấu hình              |
    |                             AuthenticationFailureHandler
SecurityContext / session, v.v.       |
    |                             HTTP 401 hoặc redirect /login?error
AuthenticationSuccessHandler          |
    |                             Không vào controller đích
HTTP 200 hoặc redirect
~~~

Dấu (*) nhấn mạnh sự kiện phụ thuộc **AuthenticationManager/AuthenticationEventPublisher thực tế** và cấu hình. Không được giả định mọi loại AuthenticationManager, provider hoặc custom filter đều phát cùng loại sự kiện. Ví dụ mô tả đường đi phổ biến qua ProviderManager với publisher được cấu hình.

Thứ tự chi tiết của session strategy, SecurityContextRepository, Remember-Me, interactive event và handler phụ thuộc filter/cấu hình hiện tại. Điểm cần nhớ: **event được phát ở tầng authentication**, còn **handler quyết định phản hồi cho lần login bằng HTTP**. Việc ghi log trong event listener không phải là bước tạo SecurityContext hoặc tự đăng nhập cho người dùng.

### Một bảng đối chiếu nhanh

| Thành phần | Nhận gì? | Dùng khi nào? | Trách nhiệm |
| --- | --- | --- | --- |
| AuthenticationProvider | Yêu cầu Authentication được AuthenticationManager giao | Mỗi lần provider tham gia xác thực | Kiểm tra credential, trả Authentication hoặc ném AuthenticationException |
| AuthenticationEventPublisher | Kết quả thành công/thất bại do manager truyền tới | Khi publisher được gọi | Phát sự kiện ứng dụng |
| AuthenticationSuccessEvent | Authentication thành công | Khi publisher phát sự kiện tương ứng | Quan sát kết quả xác thực ở tầng manager |
| AbstractAuthenticationFailureEvent | Authentication và AuthenticationException | Khi publisher ánh xạ lỗi tới event | Quan sát lỗi xác thực |
| AuthenticationSuccessHandler | HttpServletRequest, HttpServletResponse, Authentication | Khi filter đăng nhập gọi handler sau thành công | Chọn redirect, status, response body |
| AuthenticationFailureHandler | HttpServletRequest, HttpServletResponse, AuthenticationException | Khi filter đăng nhập gọi handler sau lỗi | Trả status, redirect hoặc thông báo lỗi an toàn |
| AuthenticationEntryPoint | Request, response, lý do cần authentication | Khi truy cập tài nguyên cần đăng nhập/challenge | Bắt đầu quá trình đăng nhập hoặc trả challenge |
| AccessDeniedHandler | Request/response và AccessDeniedException | Khi chủ thể không đủ quyền | Phản hồi access denied, thường 403 |

Các thành phần giải quyết **các câu hỏi khác nhau**. Event không phải HTTP handler; HTTP handler không tự trở thành event listener.

## 3. Những sự kiện xác thực nên biết

### 3.1. AuthenticationSuccessEvent

AuthenticationSuccessEvent thuộc nhóm sự kiện từ AuthenticationEventPublisher. Nó chứa Authentication vừa được manager chấp nhận. Listener có thể lấy loại Authentication, tập authority hoặc một định danh nội bộ phù hợp chính sách bảo mật.

**Không dùng event để gửi mật khẩu, raw token hay chi tiết principal vào log**. Authentication có thể chứa credentials hoặc details do provider/filter tạo. Với một số cơ chế, Authentication đã được xóa credentials khi event đến, nhưng không nên phụ thuộc giả định đó để an toàn.

Một lần đăng nhập thành công có thể có thêm các sự kiện riêng từ filter hoặc ứng dụng. Không đếm mọi sự kiện chứa chữ Success như cùng một phép đo người dùng đăng nhập.

### 3.2. InteractiveAuthenticationSuccessEvent

Ở luồng xác thực tương tác, AbstractAuthenticationProcessingFilter có thể phát InteractiveAuthenticationSuccessEvent khi filter hoàn tất quá trình xác thực thành công. Đây là sự kiện **khác loại** với AuthenticationSuccessEvent, phản ánh ngữ cảnh của filter đăng nhập chứ không chỉ kết quả của AuthenticationManager.

Với form login phổ biến, listener ứng dụng có thể quan sát cả AuthenticationSuccessEvent và InteractiveAuthenticationSuccessEvent cho cùng một hành động. **Đếm hai sự kiện là hai lần đăng nhập** sẽ tạo dữ liệu sai. Hãy xác định định nghĩa metric: số lần manager xác thực thành công, số form login hoàn tất, hay số phiên người dùng đang hoạt động.

### 3.3. AbstractAuthenticationFailureEvent và các subtype

AbstractAuthenticationFailureEvent là superclass cho các sự kiện thất bại xác thực. Các subtype thường gặp gồm:

- AuthenticationFailureBadCredentialsEvent: credential không hợp lệ.
- AuthenticationFailureDisabledEvent: tài khoản bị đánh dấu disabled theo logic provider.
- AuthenticationFailureLockedEvent: tài khoản bị locked.
- AuthenticationFailureExpiredEvent: tài khoản hết hạn.
- AuthenticationFailureCredentialsExpiredEvent: credentials hết hạn.
- AuthenticationFailureServiceExceptionEvent: lỗi liên quan dịch vụ xác thực, tùy exception mapping.

Đừng dùng subtype để hiển thị thông báo cụ thể cho người dùng cuối kiểu “tài khoản tồn tại nhưng bị khóa” nếu điều này tạo rủi ro dò tài khoản. Với người dùng công khai, thông báo chung có thể phù hợp; log nội bộ vẫn cần bảo vệ.

Không phải mọi AuthenticationException đều chắc chắn có subtype event: DefaultAuthenticationEventPublisher ánh xạ các **kiểu exception cụ thể**. Những exception tùy biến hoặc subclass có thể cần cấu hình additional exception mappings để nhận sự kiện mong muốn. Không tự giả định rằng chỉ cần kế thừa BadCredentialsException là publisher luôn ánh xạ đúng như lớp cha.

### 3.4. Sự kiện authorization, logout và session khác authentication events

AuthorizationDeniedEvent (khi được bật qua publisher tương ứng) liên quan **phân quyền**. LogoutSuccessEvent liên quan **logout** trong cấu hình phù hợp. SessionDestroyedEvent hoặc event của HttpSession liên quan **vòng đời phiên**. Chúng không đồng nghĩa AuthenticationSuccessEvent/AuthenticationFailureEvent.

Nếu bạn cần audit hành vi được cho phép/từ chối ở API, nghiên cứu AuthorizationEventPublisher hoặc integration với authorization; nếu cần theo dõi logout, dùng logout event/handler phù hợp. Không ép tất cả vào form login success/failure handler.

## 4. AuthenticationEventPublisher và cơ chế phát sự kiện

Giao diện AuthenticationEventPublisher đại diện cho chức năng phát kết quả xác thực:

~~~java
// Phác họa các phương thức có ý nghĩa để đọc API,
// không phải một file nguồn Spring Security đầy đủ.
void publishAuthenticationSuccess(Authentication authentication);
void publishAuthenticationFailure(
        AuthenticationException exception,
        Authentication authentication);
~~~

ProviderManager có thể gọi publisher đã cấu hình khi biết kết quả authentication. DefaultAuthenticationEventPublisher là implementation phổ biến, chuyển kết quả thành sự kiện Spring ApplicationEventPublisher.

Trong ứng dụng Spring Boot thông thường, auto-configuration có thể cung cấp DefaultAuthenticationEventPublisher nếu chưa có bean phù hợp. Để minh họa rõ dependency và tránh dựa vào sự mặc định bị thay đổi, phần ví dụ sẽ **khai báo bean AuthenticationEventPublisher**:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher events) {
    return new DefaultAuthenticationEventPublisher(events);
}
~~~

Đây là snippet nằm trong lớp @Configuration với đầy đủ import ở phần chương trình mẫu, không phải chương trình Java độc lập.

Quan trọng:

1. Có bean publisher chưa chứng minh **mọi AuthenticationManager trong hệ thống** đều sử dụng nó. Với AuthenticationManager/ProviderManager do bạn tự tạo thủ công, hãy kiểm tra có gọi setAuthenticationEventPublisher(...) cho manager đó hoặc có kết nối publisher qua cấu hình hợp lệ.
2. ProviderManager có thể gồm nhiều AuthenticationProvider; chỉ các lần authenticate thực sự đi qua manager có publisher mới được phát tương ứng.
3. DefaultAuthenticationEventPublisher phát dựa trên mapping exception, không suy ra loại event chỉ từ HTTP status cuối cùng.
4. Nếu listener ném runtime exception trong quá trình công bố event đồng bộ, xử lý xác thực có thể bị ảnh hưởng. Listener audit nên nhanh, an toàn, có cơ chế chịu lỗi.
5. Đừng dùng event listener làm **điểm chặn bắt buộc trước xác thực** (chẳng hạn rate limiting bắt buộc). Quy tắc chặn phải nằm trong gateway/filter/provider hoặc cơ chế thích hợp trước khi chấp nhận Authentication.

### Event listener có chạy bất đồng bộ không?

Theo cơ chế application event phổ biến của Spring, listener chạy đồng bộ theo publisher mặc định, trừ khi ứng dụng cấu hình một cơ chế multicaster/async phù hợp. @EventListener không tự làm cho method chạy trên thread khác. Với @Async cần hỗ trợ async được bật và phải hiểu ngữ cảnh bảo mật, transaction, retry, thứ tự sự kiện và backpressure.

Hãy tách thông tin audit không bắt buộc sang queue/outbox khi yêu cầu tính tin cậy cao; tránh gọi hệ thống bên ngoài có độ trễ lớn trong listener đồng bộ của đăng nhập.

## 5. AuthenticationSuccessHandler và AuthenticationFailureHandler

Hai interface này quyết định điều gì xảy ra **ở lớp HTTP** sau khi một cơ chế đăng nhập dựa trên filter đã nhận kết quả xác thực.

### 5.1. Success handler

AuthenticationSuccessHandler nhận request, response và Authentication đã được chấp nhận. Các cách xử lý thường gặp:

- Chuyển người dùng về URL trước đó hoặc trang mặc định (saved request/redirect).
- Trả response JSON hoặc body ngắn nếu frontend cần API-style login.
- Gắn một header không nhạy cảm để frontend nhận biết trạng thái.
- Thực hiện nghiệp vụ nhẹ sau login, nhưng không dùng để quyết định lại authentication.

Form login mặc định thường có chiến lược redirect như SavedRequestAwareAuthenticationSuccessHandler. Khi tự viết handler trả 200, bạn **đã thay đổi hợp đồng điều hướng**. Hãy chọn cách phù hợp với giao diện ứng dụng.

### 5.2. Failure handler

AuthenticationFailureHandler nhận AuthenticationException và quyết định response khi filter xác thực thất bại:

- Form HTML: redirect về trang login kèm trạng thái lỗi chung.
- JSON/SPA login: trả 401 và mã lỗi an toàn, không in stack trace.
- Ghi metric có nhãn low-cardinality, không in password/token vào logs.

Nếu dùng SimpleUrlAuthenticationFailureHandler, bạn có thể cấu hình URL lỗi; nếu viết custom failure handler, cần tự xử lý status/body/redirect.

**Không mọi 401 đều qua formLogin.failureHandler.** HTTP Basic dùng entry point khi cần challenge; Bearer Token và OAuth2 Resource Server có cơ chế lọc và entry point riêng; request chưa xác thực nhưng chỉ gọi một tài nguyên bảo vệ thường không phải nỗ lực form login.

### 5.3. Entry point, access denied và handler không thể dùng thay nhau

| Hiện tượng | Ví dụ | Điểm xử lý thường gặp |
| --- | --- | --- |
| POST /login đúng mật khẩu | User xác thực thành công | AuthenticationSuccessHandler của form login; có thể có authentication success events |
| POST /login sai mật khẩu | BadCredentialsException | AuthenticationFailureHandler của form login; có thể có failure event |
| GET /private chưa đăng nhập | Không có authentication hợp lệ | AuthenticationEntryPoint → redirect/challenge |
| GET /admin đã login nhưng thiếu quyền | AccessDeniedException | AccessDeniedHandler, thường HTTP 403 |
| POST /login thiếu CSRF token | CsrfFilter từ chối | CSRF/access-denied handling, không mặc nhiên là AuthenticationFailureHandler |
| GET /api cần Basic không có header | Chưa có Basic credentials để xử lý | BasicAuthenticationEntryPoint/exception translation, thường 401 và WWW-Authenticate |
| Request Bearer token không hợp lệ | Bearer token extraction/validation thất bại | Cấu hình resource server và BearerTokenAuthenticationEntryPoint, tùy filter |

Đặt đúng hook giúp bạn tránh việc đẩy logic sai chỗ, tạo redirect không mong đợi hoặc bỏ qua CSRF/authorization.

## 6. Ví dụ Spring Boot 3.x + Spring Security 6.x + Java 17

Bài thực hành tạo login HTML/form, nhưng **success handler trả 200 + body LOGIN_OK**, failure handler trả **401 + body LOGIN_FAILED** để dễ test. Cấu hình mặc định vẫn bảo vệ CSRF và dùng session khi cần. App có listener để ghi nhận AuthenticationSuccessEvent và AbstractAuthenticationFailureEvent bằng log tối giản.

### 6.1. Tạo dự án

Dự án Gradle Groovy DSL có thể có cấu trúc:

~~~text
auth-events-demo/
  settings.gradle
  build.gradle
  gradlew, gradlew.bat (nếu sinh bằng Gradle wrapper)
  src/main/java/dev/example/authevents/
    AuthEventsApplication.java
    SecurityConfig.java
    AuthAuditListener.java
    PagesController.java
  src/test/java/dev/example/authevents/
    AuthenticationFlowTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'auth-events-demo'
~~~

build.gradle (ví dụ phiên bản Spring Boot 3.3.5 và Java 17; nếu dự án đã có cấu hình khác, dùng bộ version/dependency tương thích do dự án quản lý):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các file Java sau phải đặt đúng đường dẫn, package, tên class như mô tả. Có thể dùng một dự án khởi tạo từ Spring Initializr với hai starter web/security và Gradle wrapper, sau đó thay thế nguồn bằng mã bên dưới. Vì sử dụng các thư viện Spring, không chạy riêng bằng javac trên file Java không có classpath; chạy qua Gradle/Maven của dự án.

### 6.2. Entry point

Tệp src/main/java/dev/example/authevents/AuthEventsApplication.java:

~~~java
package dev.example.authevents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthEventsApplication.class, args);
    }
}
~~~

### 6.3. Cấu hình xác thực, event publisher và HTTP handlers

Tệp src/main/java/dev/example/authevents/SecurityConfig.java:

~~~java
package dev.example.authevents;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new DefaultAuthenticationEventPublisher(springEvents);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("learn-pass-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationSuccessHandler formSuccessHandler() {
        return (request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("LOGIN_OK");
        };
    }

    @Bean
    AuthenticationFailureHandler formFailureHandler() {
        return (request, response, exception) -> {
            response.setStatus(401);
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("LOGIN_FAILED");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationSuccessHandler formSuccessHandler,
            AuthenticationFailureHandler formFailureHandler)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .successHandler(formSuccessHandler)
                        .failureHandler(formFailureHandler)
                        .permitAll())
                .build();
    }
}
~~~

Điểm cần quan sát:

- UserDetailsService minh họa chỉ có một user learner, password được mã hóa bởi PasswordEncoder thích hợp; không lưu mật khẩu plaintext trong cấu hình hệ thống thật.
- @Bean AuthenticationEventPublisher tạo publisher từ ApplicationEventPublisher. Khi dùng manager do Spring Security cấu hình theo cách thông thường, publisher này là thành phần có thể được kết nối vào vòng đời xác thực; với manager tự tạo, phải kiểm tra wiring.
- formLogin tạo đường xử lý POST /login và trang GET /login mặc định nếu chưa chỉ định custom login page.
- formSuccessHandler và formFailureHandler viết HTTP status/body, **không phải listener**. Đổi sang redirect trong ứng dụng web truyền thống nếu UI mong đợi.
- Không disable CSRF. POST /login từ trình duyệt cần CSRF token do security framework hỗ trợ; MockMvc test bên dưới gửi token một cách rõ ràng.
- Role USER trong UserDetailsService được biểu diễn bằng authority ROLE_USER. Đừng dùng prefix này nhầm với việc kiểm tra hasAuthority và hasRole.

Trong ứng dụng thật, không tự đưa thông báo “sai user” so với “sai password” ra response. Body LOGIN_FAILED ở đây cố tình thống nhất cho các lỗi login để giảm nguy cơ dò tài khoản.

### 6.4. Listener cho hai nhóm event

Tệp src/main/java/dev/example/authevents/AuthAuditListener.java:

~~~java
package dev.example.authevents;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class AuthAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AuthAuditListener.class);

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        log.info("auth result=success type={}",
                event.getAuthentication().getClass().getSimpleName());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        log.warn("auth result=failure exceptionType={}",
                event.getException().getClass().getSimpleName());
    }
}
~~~

Cách code hoạt động:

- @Component làm listener thành bean Spring. @EventListener đăng ký method tiếp nhận event đúng kiểu.
- Method onFailure nhận superclass AbstractAuthenticationFailureEvent, nên bao gồm các subtype được publisher phát ra, chẳng hạn AuthenticationFailureBadCredentialsEvent.
- Chỉ log class name/loại kết quả. Không đọc, serialise hoặc ghi log authentication.getCredentials(), password trong HTTP request, Authorization header, token, session ID hay exception message chứa dữ liệu nhạy cảm.
- Với authentication thành công, log không kết luận đã tạo session hoặc đã chuyển đến controller; đó là các bước khác của flow.
- Listener nên nhỏ và không ném exception vì ghi telemetry không được làm hỏng login. Nếu ghi audit vào storage có thể lỗi, thiết kế hàng đợi/transaction/outbox hoặc chính sách fail-open/fail-closed rõ ràng tùy yêu cầu pháp lý.

Nếu thay listener bằng ApplicationListener<AuthenticationSuccessEvent>, bạn cần implement onApplicationEvent(event); hai cách đều nghe event nhưng không cần đồng thời đăng ký hai listener với cùng mục đích vì có thể tạo bản ghi trùng.

### 6.5. Controller để test resource protection

Tệp src/main/java/dev/example/authevents/PagesController.java:

~~~java
package dev.example.authevents;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @GetMapping("/private")
    public String privatePage() {
        return "PRIVATE_OK";
    }
}
~~~

GET /public/ping được permitAll; GET /private cần authentication. Phân quyền truy cập trang là trách nhiệm của authorizeHttpRequests, không phải AuthAuditListener.

### 6.6. Kiểm thử MockMvc có CSRF token

Tệp src/test/java/dev/example/authevents/AuthenticationFlowTest.java:

~~~java
package dev.example.authevents;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicUrlIsAvailable() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void privateUrlRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void correctPasswordCallsSuccessHandlerAndSavesLogin() throws Exception {
        MvcResult login = mvc.perform(post("/login").with(csrf())
                        .param("username", "learner")
                        .param("password", "learn-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("LOGIN_OK"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE_OK"));
    }

    @Test
    void wrongPasswordCallsFailureHandler() throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "learner")
                        .param("password", "wrong-pass"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().string("LOGIN_FAILED"));
    }

    @Test
    void missingCsrfTokenIsNotPasswordFailure() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "learner")
                        .param("password", "learn-pass-123"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy project đã có Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Với Windows PowerShell, thường dùng ./gradlew.bat test và ./gradlew.bat bootRun. Lệnh gradlew chỉ có khi wrapper hiện diện; nếu tự tạo project Gradle chưa có wrapper, cần cài Gradle hoặc sinh wrapper trước.

Kỳ vọng tất cả test pass với cấu hình đã nêu. Bài học chính trong từng test:

1. GET public trả 200, không có lần authenticate mật khẩu nào.
2. GET private khi chưa có session redirect, không mặc định phát BadCredentialsEvent.
3. POST /login đúng credential và có CSRF token trả LOGIN_OK; session của request được dùng để gọi private thành công.
4. POST /login sai credential nhưng CSRF hợp lệ trả LOGIN_FAILED và 401.
5. POST /login không có CSRF token bị 403 trước bước kiểm tra password.

**Những test trên chứng minh HTTP behavior và session, không tự động chứng minh event listener đã được gọi.** Để kiểm tra event, thêm integration test riêng có một listener thử nghiệm hoặc ApplicationEventPublisher probe đếm đúng loại event theo từng attempt; tránh dùng cả AuthenticationSuccessEvent và InteractiveAuthenticationSuccessEvent như một metric duy nhất. Có thể kiểm chứng đơn giản hơn bằng log auth result=success/failure trong môi trường phát triển, nhưng không biến log thành kiểm định duy nhất của production.

### 6.7. Thử bằng trình duyệt và curl

Khi ứng dụng chạy local, thử:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private
~~~

Các kết quả điển hình là HTTP 200 với PUBLIC_OK cho endpoint public, và 302 redirect đến /login cho GET private khi chưa có phiên đăng nhập.

Để thử login thủ công, mở http://localhost:8080/login trong **trình duyệt**, nhập learner / learn-pass-123. Trang login mặc định của Spring Security cung cấp CSRF token ẩn nếu cơ chế form login/CSRF đang bật. Handler tùy biến trả body LOGIN_OK thay vì redirect.

Không gửi POST /login bằng curl -d username=... -d password=... mà quên CSRF rồi kết luận authentication fail vì nhận 403. Khi test HTTP thủ công, cần lấy và gửi CSRF token và session cookie tương ứng. Trong kiểm thử tự động, .with(csrf()) của spring-security-test là cách trực tiếp, rõ ràng hơn.

Chỉ dùng mật khẩu mẫu trong ứng dụng local. Trong môi trường thật cần TLS/HTTPS và quản lý secret an toàn.

## 7. Quan sát sự kiện thực tế và ý nghĩa dữ liệu

Với cấu hình mặc định thường dùng của Spring Security qua ProviderManager:

- Khi login form đúng credentials, publisher có thể phát AuthenticationSuccessEvent; listener onSuccess ghi log dạng auth result=success type=UsernamePasswordAuthenticationToken.
- Filter dành cho form login cũng có thể phát InteractiveAuthenticationSuccessEvent. Listener ở ví dụ **không nhận** loại này, nên không đếm trùng.
- Khi sai password, provider/manager tạo AuthenticationException, publisher thường ánh xạ BadCredentialsException thành AuthenticationFailureBadCredentialsEvent; listener onFailure nhận do kế thừa AbstractAuthenticationFailureEvent.
- Khi request bị CSRF chặn trước khi vào UsernamePasswordAuthenticationFilter, không có authentication attempt đi qua manager, vì vậy không kỳ vọng sự kiện bad credentials.
- Khi user đăng nhập nhưng truy cập URL không đủ quyền, authorization từ chối request; đừng chờ form failure handler.

Đây là kết quả **kỳ vọng của cấu hình mẫu**, không phải cam kết mọi Spring Security app phát cùng số lần event. Số lượng event thay đổi theo số lần authenticate, manager, filter, token strategy, session persistence, xử lý lỗi và publisher đã nối. Quan sát code/config/runtime test của ứng dụng thật trước khi quyết định phân tích bảo mật.

### Vì sao event listener đôi khi không chạy?

Các nguyên nhân điển hình:

1. Không có AuthenticationEventPublisher được nối vào AuthenticationManager sử dụng thực tế, đặc biệt khi tự tạo custom manager.
2. Một custom filter tự đặt Authentication trong SecurityContext mà không gọi manager/publisher.
3. Authentication thất bại trước bước gọi manager (CSRF, request parsing, filter không match URL, v.v.).
4. Exception không nằm trong mapping mà DefaultAuthenticationEventPublisher biết để phát subtype failure event.
5. Listener không phải Spring bean hoặc method @EventListener có signature/kiểu event không khớp.
6. Có nhiều ApplicationContext, listener ở context khác publisher hoặc cấu hình event multicaster riêng.
7. Bạn đang nghe AuthenticationSuccessEvent nhưng luồng chỉ phát event khác, hoặc đang kỳ vọng event xảy ra mỗi HTTP request dù đó chỉ là quá trình tái sử dụng session.

Cách debug: xác minh chính xác SecurityFilterChain được chọn; xem filter đăng nhập có match POST /login không; xác minh provider/manager nào thực thi; kiểm tra bean AuthenticationEventPublisher; thêm test/probe listener và xem exception type. Tránh bật TRACE logging dài hạn hoặc in thông tin nhạy cảm.

## 8. Mở rộng failure event cho exception tùy biến

DefaultAuthenticationEventPublisher sử dụng một tập quy tắc ánh xạ từ loại AuthenticationException sang loại AbstractAuthenticationFailureEvent. Nếu bạn viết custom AuthenticationProvider ném một AuthenticationException mới, listener đang nghe AbstractAuthenticationFailureEvent có thể không nhận gì nếu publisher không có mapping.

Khi thật sự cần, có thể cấu hình **additional exception mappings** qua API của DefaultAuthenticationEventPublisher cho phiên bản Spring Security đang chạy. Ý tưởng là map một kiểu AuthenticationException cụ thể sang một subtype AuthenticationFailureEvent phù hợp, đồng thời xác định hành vi fallback khi chưa có mapping. Không nên dựa vào việc Java subclass luôn được tự động chọn theo ánh xạ của superclass.

Đối với giám sát thất bại, bạn cũng có thể giữ listener ở superclass AbstractAuthenticationFailureEvent để đón nhiều loại event đã được phát mà không phải viết từng listener subtype. Điều này **không khắc phục** việc publisher không phát event ngay từ đầu.

Một quy tắc triển khai thực tế: nếu custom provider trả failure với thông tin nhạy cảm, event chỉ nên mang thông tin tối thiểu cần audit. Listener tuyệt đối tránh ghi thông báo exception nguyên bản ra log công khai hoặc response.

## 9. Điểm mở rộng nên chọn theo từng nhu cầu

| Nhu cầu thực tế | Điểm mở rộng ưu tiên | Lưu ý |
| --- | --- | --- |
| Kiểm tra username/password từ data source riêng | UserDetailsService, AuthenticationProvider | Đừng dùng success handler để xác thực lại |
| Thêm quy tắc chặn trước đăng nhập hoặc rate limiting | Gateway / filter trước auth / AuthenticationProvider | Event sau failure không phải điểm chặn đúng lúc |
| Đưa user về URL đã truy cập trước login | AuthenticationSuccessHandler có xử lý saved request | Mặc định form login đã có chiến lược redirect phù hợp |
| API login cần JSON 200/401 rõ ràng | SuccessHandler / FailureHandler của filter login tương ứng | Không vô tình vô hiệu CSRF nếu browser dùng cookie |
| Ghi audit xác thực thành công/thất bại | AuthenticationEventPublisher + ApplicationEvent listener | Dữ liệu an toàn, idempotent và có chính sách lưu trữ |
| Gửi metric về số lần đăng nhập thành công | Xác định rõ event nào đại diện một login | Basic và các token flow có đặc tính khác form login |
| Tùy chỉnh response khi user chưa đăng nhập vào protected URL | AuthenticationEntryPoint | Không phải failure handler của POST /login |
| Tùy chỉnh phản hồi khi user đã login nhưng thiếu quyền | AccessDeniedHandler / AuthorizationManager | Không phải BadCredentialsEvent |
| Phản ứng với logout | LogoutSuccessHandler và logout event thích hợp | Không nhầm với authentication failure |
| Cần sự kiện authorization | AuthorizationEventPublisher hoặc listener phù hợp | Độc lập với AuthenticationEventPublisher |
| Cần quan sát các bước nhiều filter trước/sau xác thực | Custom OncePerRequestFilter với vị trí rõ | Phải xét SecurityFilterChain, @Order và CSRF |

Điểm mở rộng ở tầng thấp hơn thường mạnh hơn nhưng dễ làm sai flow. Hãy bắt đầu từ nhu cầu nghiệp vụ và chọn API có trách nhiệm sát nhất.

### Custom AuthenticationProvider và event không phải cùng việc

AuthenticationProvider.validateCredentials(...) (tùy implementation) trả Authentication thành công hoặc ném AuthenticationException. Publisher được AuthenticationManager kết nối sẽ phát event tương ứng nếu cấu hình thích hợp. Provider không cần tự phát event trong trường hợp dùng Publisher tiêu chuẩn; tự phát cùng loại lần nữa có thể gây trùng audit.

Nếu bạn tự thay hoàn toàn AuthenticationManager, phải quyết định quy tắc gọi AuthenticationEventPublisher rõ ràng. Việc thêm listener mà không có publisher ở luồng custom là một lỗi quan sát thường gặp.

## 10. Bảo mật và vận hành: những lỗi dễ mắc

### 10.1. Ghi thông tin xác thực trong event log

Không log mật khẩu, credential, Authorization header, JWT, CSRF token, cookie, JSESSIONID hoặc đối tượng Authentication nguyên vẹn qua toString() mà chưa kiểm soát. Ngay cả exception message có thể chứa chi tiết hệ thống nội bộ. Dùng loại event, loại exception, request correlation ID an toàn, timestamp và chỉ định danh đã được che theo chính sách dữ liệu.

### 10.2. Trả lời sai thông tin, tạo user enumeration

Failure handler không nên phân biệt công khai “không có user”, “sai password”, “user bị khóa” nếu ứng dụng không có cơ chế chống dò thích hợp. Response chung và timing không tiết lộ là lựa chọn an toàn phổ biến. Audit nội bộ có thể giữ thông tin chi tiết hơn với phân quyền và thời gian lưu phù hợp.

### 10.3. Đồng nhất HTTP 403 với đăng nhập sai

403 do CSRF hoặc thiếu quyền không chắc là authentication failure; HTTP 401 do entry point cũng chưa chắc ứng với event từ manager. Thiết kế dashboard tách metric theo nguồn gốc: login attempt, authentication result, authorization denial, CSRF rejection, entry point challenge.

### 10.4. Listener đồng bộ quá chậm hoặc ném exception

Event listener thường chạy trong đường xử lý đang xác thực; truy vấn API/DB ngoài dài có thể tăng latency và gây lỗi đăng nhập. Ghi audit bền vững qua queue/outbox, retry giới hạn, timeout và chính sách xử lý khi downstream hỏng. Listener không nên làm thay đổi authentication result chỉ vì telemetry lỗi ngoài ý muốn.

### 10.5. Đếm trùng success event

AuthenticationSuccessEvent, InteractiveAuthenticationSuccessEvent, session created và HTTP 200 đều có ý nghĩa khác nhau. Dùng định nghĩa metric rõ ràng và correlation ID khi cần đối chiếu; tránh tổng hợp các dòng log thành “tổng số người login” mà không có de-duplication.

### 10.6. Đặt xử lý điều hướng trong listener

Một listener có AuthenticationSuccessEvent không phải nơi gửi redirect tới trình duyệt: nó không có hợp đồng HttpServletResponse của AuthenticationSuccessHandler. Muốn điều hướng/JSON phải dùng handler của filter tương ứng.

### 10.7. Áp dụng handler của form login sang HTTP Basic/Bearer

Mỗi kiểu xác thực có filter và error flow riêng. Với Basic, việc xác thực có thể xảy ra lặp lại trên nhiều request có Authorization header; với Bearer, token validation và entry point là trọng tâm. Không giả định cấu hình formLogin.successHandler áp dụng cho BasicAuthenticationFilter hoặc BearerTokenAuthenticationFilter.

### 10.8. Vô tình tắt CSRF để test login

Nếu browser sử dụng session cookie, giữ biện pháp chống CSRF phù hợp; Spring Security bảo vệ POST /login theo mặc định. Test với csrf() để mô phỏng form chuẩn. Tắt CSRF tùy tiện để POST /login dễ chạy sẽ làm giảm an toàn của ứng dụng.

### 10.9. Thao tác SecurityContext ở listener

Listener được thiết kế để quan sát kết quả, không nên trực tiếp tạo/tự sửa SecurityContext hoặc phụ thuộc thread-local context khi chạy async. Với trường hợp authentication hợp lệ cần được lưu, để filter/framework dùng đúng SecurityContextRepository/session strategy. Trong async processing phải hiểu context propagation và isolation.

### 10.10. Gửi email hoặc ghi audit “chắc chắn một lần” từ event không bền vững

ApplicationEvent mặc định không phải message queue bền vững. Restart/crash hoặc lỗi ghi có thể làm mất hoặc nhân bản thông báo. Nếu event có hệ quả pháp lý hoặc thanh toán, thiết kế giao dịch/outbox/idempotency rõ ràng; không hứa exactly-once chỉ vì nhận AuthenticationSuccessEvent.

## 11. Kiểm thử chuyên sâu cho event và extension point

Bộ test hành vi trong phần 6 mới bao quát status/session. Với ứng dụng production, bổ sung ba nhóm kiểm thử:

**Nhóm A — Event đúng loại**

- Đăng ký một listener/probe trong test context để thu thập AuthenticationSuccessEvent, AbstractAuthenticationFailureEvent với dữ liệu tối thiểu.
- Gửi một POST /login thành công có csrf(); khẳng định event success được phát bởi AuthenticationManager thực tế.
- Gửi một POST sai password có csrf(); xác minh failure event phù hợp.
- Gửi POST thiếu CSRF và kiểm tra không nhầm nó với BadCredentialsEvent.
- Khi đổi AuthenticationManager/Provider, thực hiện lại test vì producer event có thể đổi.

**Nhóm B — Handler HTTP**

- SuccessHandler trả đúng status/redirect/body theo hợp đồng.
- FailureHandler không làm lộ account existence, stack trace hay exception message nhạy cảm.
- Request protected không login đi vào AuthenticationEntryPoint.
- Request user thiếu quyền đi vào AccessDeniedHandler, không báo là login failed.

**Nhóm C — Tính ổn định và phạm vi**

- Nếu có nhiều SecurityFilterChain, xác minh đúng login processing URL rơi vào đúng chain.
- Trong test concurrent, xác minh listener không dùng mutable state gây race condition.
- Thử listener telemetry bị lỗi/timeout theo thiết kế fault tolerance.
- Với OAuth2/Basic/Bearer, viết test riêng cho đúng filter/entry point thay vì tái sử dụng mù các assertion của form login.

Log kỳ vọng có thể dạng:

~~~text
auth result=success type=UsernamePasswordAuthenticationToken
auth result=failure exceptionType=BadCredentialsException
~~~

Đây là **dạng log minh họa**, không phải stdout byte-for-byte của chạy Gradle: logger có thể thêm timestamp, thread, level; sự kiện thực tế còn tùy provider/publisher. Không dùng log mô tả làm bằng chứng nếu chưa test đúng manager.

## 12. Tình huống tự luyện và đáp án giải thích

**Tình huống 1.** POST /login sai mật khẩu, đã có CSRF hợp lệ, trả 401 qua formFailureHandler. Listener nhận AbstractAuthenticationFailureEvent có vai trò gì?

> Listener quan sát sự kiện publisher phát, chẳng hạn BadCredentialsEvent. Handler quyết định HTTP response. Hai việc tách rời: thay đổi status trong handler không có nghĩa là thêm/sửa authentication event.

**Tình huống 2.** GET /private trả 302 chuyển tới /login khi chưa có cookie. Có nên tăng metric “sai mật khẩu” không?

> Không. Đây là yêu cầu truy cập tài nguyên cần xác thực; AuthenticationEntryPoint bắt đầu login, chưa có credential nào bị xác minh sai.

**Tình huống 3.** POST /login thiếu CSRF, nhận 403. Vì sao onFailure không in log?

> Request có thể bị CsrfFilter từ chối trước khi UsernamePasswordAuthenticationFilter/AuthenticationManager xử lý credentials; do đó không có authentication failure event từ manager.

**Tình huống 4.** Đã viết class implements ApplicationListener<AuthenticationSuccessEvent> nhưng không có log. Những gì cần kiểm tra?

> Class có là Spring bean không, AuthenticationManager có publisher không, login có thật sự đi qua manager hay một custom flow khác, event được publish là class nào, ApplicationContext nào chứa listener và event multicaster được cấu hình ra sao.

**Tình huống 5.** Một lần login hiển thị hai success events. Có hai phiên không?

> Không thể kết luận. Có thể là AuthenticationSuccessEvent và InteractiveAuthenticationSuccessEvent của cùng một flow. Muốn biết số phiên cần theo dõi session lifecycle riêng.

**Tình huống 6.** Muốn sau login đưa user về URL ban đầu. Nên chỉnh AuthenticationEventPublisher không?

> Không. Dùng AuthenticationSuccessHandler phù hợp, ví dụ handler hỗ trợ saved request. Publisher phục vụ phát event cho quan sát.

**Tình huống 7.** API dùng Bearer token trả 401 nhưng formFailureHandler không chạy. Có lỗi Spring Security không?

> Không nhất thiết. Bearer token có filter, AuthenticationEntryPoint và flow xử lý lỗi riêng. Cần debug SecurityFilterChain và cơ chế token authentication đã cấu hình.

**Tình huống 8.** Custom provider ném custom AuthenticationException; người dùng nhận lỗi nhưng không có failure event. Có cách nào?

> Kiểm tra manager có publisher, exception mapping của DefaultAuthenticationEventPublisher, và cân nhắc additional exception mappings theo API phiên bản đang dùng; không sửa HTTP failure handler để giả lập event.

## Tổng kết

Trong Spring Security Servlet có ba điểm quan sát/xử lý quan trọng mà bạn phải **tách rời**:

1. **AuthenticationManager/AuthenticationProvider** xác định kết quả xác thực; AuthenticationEventPublisher (khi được cấu hình và sử dụng) phát AuthenticationSuccessEvent hoặc các failure event.
2. **AuthenticationSuccessHandler/AuthenticationFailureHandler** xử lý phản hồi HTTP của **cơ chế đăng nhập tương ứng**, ví dụ form login. Chúng khác AuthenticationEntryPoint và AccessDeniedHandler.
3. **@EventListener/ApplicationListener** tiếp nhận sự kiện nhằm audit, telemetry và tác vụ phụ, không thay thế bảo vệ CSRF, authorization hoặc việc lưu SecurityContext.

Với mỗi yêu cầu, hãy hỏi: **xác thực đã được gọi chưa, manager nào thực thi, event nào được publish, filter/handler nào quyết định response?** Kiểm thử các lớp đó riêng biệt và tuyệt đối không để cơ chế quan sát tạo lộ thông tin hoặc làm đăng nhập mất an toàn.