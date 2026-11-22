# Tạo Authentication trong bộ nhớ không tự bảo đảm lưu đăng nhập cho yêu cầu sau

## 1. Vấn đề thường gặp: đăng nhập thành công, tải trang tiếp theo lại thành anonymous

Hãy tưởng tượng ứng dụng Spring Boot có endpoint POST /login. Khi nhận username và password, developer gọi AuthenticationManager.authenticate(...). Provider kiểm tra đúng mật khẩu và trả Authentication đã xác thực. Developer tạo SecurityContext mới, đưa Authentication vào đó và đặt lên SecurityContextHolder:

~~~java
Authentication verified = authenticationManager.authenticate(attempt);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

Trong request hiện hành, code đọc SecurityContextHolder có thể thấy verified và isAuthenticated() là true. Endpoint trả 200 “Đăng nhập thành công”.

Nhưng ngay sau đó, frontend gọi GET /me bằng một HTTP request mới và nhận 401. Đây **không nhất thiết là lỗi của PasswordEncoder, UserDetailsService hoặc AuthenticationManager**. Nguyên nhân có thể đơn giản là ứng dụng chỉ tạo **trạng thái trong bộ nhớ của request hiện tại**, chưa lưu SecurityContext ở nơi request sau có thể tìm lại.

**Luận điểm chính:**

> Authentication thành công khác với việc đặt Authentication vào SecurityContextHolder, và cả hai khác với việc **lưu SecurityContext để truy xuất cho yêu cầu HTTP sau**.

Trong Spring Security Servlet 6.x, custom code muốn duy trì đăng nhập qua request có thể cần gọi **SecurityContextRepository.saveContext(context, request, response)** một cách tường minh. Bên cạnh đó, browser phải giữ và gửi lại session cookie, session chưa hết hạn, security chain phải khôi phục đúng repository và policy không được thiết kế stateless.

Bài sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Các ví dụ chỉ áp dụng cho **Servlet stack** dùng HttpSecurity và HttpServletRequest; với WebFlux, cần ServerHttpSecurity và reactive context. Một demo riêng minh họa **setContext mà không saveContext** đối chiếu với **setContext cộng saveContext**.

### Sau khi học, bạn sẽ

1. Phân biệt Authentication, SecurityContext, SecurityContextHolder, SecurityContextRepository và HttpSession.
2. Giải thích request đầu tiên và request kế tiếp liên hệ với nhau bằng session cookie như thế nào.
3. Hiểu mặc định Spring Security 6 dùng SecurityContextHolderFilter và cơ chế **explicit save**.
4. Phân biệt HttpSessionSecurityContextRepository, RequestAttributeSecurityContextRepository, DelegatingSecurityContextRepository và NullSecurityContextRepository.
5. Dự đoán được vì sao Authentication hiện hành hợp lệ nhưng GET /me tiếp theo lại trả 401.
6. Biết khi nào cần gọi saveContext và vì sao phải làm **trước khi response bị commit**.
7. Phân biệt session-based form login với HTTP Basic và Bearer/JWT stateless.
8. Chạy được ví dụ Java 17 Spring Boot minh họa hai hành vi trái ngược.
9. Viết MockMvc test kiểm tra hai request độc lập, có/không có phiên.
10. Nhận diện lỗi session policy, CSRF, session fixation, logout, cookie, nhiều security chains và async ThreadLocal.

## 2. Năm đối tượng không được đánh đồng

| Khái niệm | Nó là gì? | Phạm vi/vòng đời | Điều nó không tự làm |
| --- | --- | --- | --- |
| **Authentication** | Object đại diện danh tính, authorities, credentials và trạng thái authenticated | Dữ liệu xác thực trong code | Không tự tạo session hoặc cookie |
| **SecurityContext** | Object chứa Authentication hiện hành | Ngữ cảnh bảo mật | Không tự quyết định lưu sang request sau |
| **SecurityContextHolder** | API truy cập context cho luồng xử lý hiện tại | Thường ThreadLocal ở Servlet | Không phải kho đăng nhập dài hạn |
| **SecurityContextRepository** | Cơ chế đọc/lưu context qua boundary request | Request attribute, HttpSession hoặc custom store | Không tự xác minh password |
| **HttpSession + session cookie** | Liên hệ trình duyệt với phiên ở server | Tồn tại giữa các HTTP requests khi được cấu hình | Cookie không tự đồng nghĩa user đã đăng nhập |

### 2.1. Authentication chỉ là kết quả xác minh

AuthenticationManager.authenticate(attempt) hoặc AuthenticationProvider có thể trả Authentication hợp lệ. Kết quả đó là một Java object; nếu chỉ giữ nó ở local variable và trả response 200, request sau không có lý do gì để biết local variable ấy đã từng tồn tại.

Trạng thái **authenticated=true** cũng không nói Authentication đã được đưa vào SecurityContextRepository. Nó chỉ là thông tin về object đã được provider đáng tin xác minh.

### 2.2. SecurityContext và SecurityContextHolder

Trong Java Servlet, SecurityContextHolder mặc định thường dựa vào **ThreadLocal**. Một request được xử lý trong thread A có thể truy cập context của thread A; khi request kết thúc, filter quản lý context sẽ dọn holder để tránh để danh tính cũ rò sang request khác trên thread tái sử dụng.

Do đó:

~~~java
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

chỉ thao tác trên context hiện hành. Ngoài vấn đề persistence, cách mutate context đã tồn tại còn có thể gặp rủi ro dùng chung instance/concurrency trong một số trường hợp. Tài liệu Spring Security khuyên **tạo một SecurityContext mới** rồi đặt Authentication vào đó.

### 2.3. SecurityContextRepository không phải PasswordEncoder

Repository không kiểm tra mật khẩu. Nó nhận context đã được tạo đúng bởi cơ chế xác thực đáng tin, rồi lưu ở nơi có thể đọc lại. Với một ứng dụng session-based, nơi lưu thường là **HttpSession**, được tra lại từ session ID mà client gửi bằng cookie.

Nếu context do code không đáng tin tự tạo với role ADMIN mà không qua authentication, gọi saveContext chỉ **lưu một danh tính giả mạo**. Persistence không thay thế việc xác minh credentials.

### 2.4. Có cookie JSESSIONID chưa chắc đã login

Một HttpSession có thể được tạo để lưu CSRF token, saved request, flash attribute hoặc dữ liệu khác ngay cả khi chưa có Authentication hợp lệ. **Session tồn tại** là một việc; **session chứa SecurityContext authenticated** là việc khác.

Ngược lại, khi dùng JWT/Bearer stateless, một request có thể đã được xác thực thành công mà **không có HttpSession**. Đừng dùng sự xuất hiện hoặc vắng mặt của cookie làm phép kiểm tra authentication duy nhất.

## 3. Hai dòng thời gian: request hiện tại và request kế tiếp

### 3.1. Chỉ setContext, không save

~~~text
Request #1: POST /lab/volatile, username/password hợp lệ
      |
      v
AuthenticationManager.authenticate()
      |
      v
Authentication verified
      |
      v
SecurityContext mới -> setAuthentication(verified)
      |
      v
SecurityContextHolder.setContext(context)
      |
      v
Response 200: authenticatedNow=true
      |
      v
SecurityContextHolderFilter kết thúc request, dọn holder
      |
      |    KHÔNG gọi SecurityContextRepository.saveContext()
      v
Request #2: GET /me, dù cùng client
      |
      v
Repository không có context của login trước
      |
      v
Anonymous/unauthenticated -> HTTP 401 (theo entry point demo)
~~~

Request #1 thành công nhưng **không tạo login session có thể sử dụng ở request #2**. Response 200 chỉ nói yêu cầu hiện tại đã xử lý xong; nó không cam kết server đã lưu danh tính.

### 3.2. setContext và saveContext

~~~text
Request #1: POST /lab/persist, username/password hợp lệ
      |
      v
AuthenticationManager.authenticate()
      |
      v
Authentication verified
      |
      v
Tạo SecurityContext -> setAuthentication(verified)
      |
      v
SecurityContextHolder.setContext(context)
      |
      v
SecurityContextRepository.saveContext(context, request, response)
      |
      v
HttpSession có SecurityContext; response có thể gửi Set-Cookie
      |
      v
Browser lưu cookie và tự gửi lại ở request #2
      |
      v
Request #2: GET /me + Cookie: JSESSIONID=...
      |
      v
SecurityContextHolderFilter đọc repository
      |
      v
SecurityContext với Authentication đã lưu
      |
      v
Authorization authenticated() cho đi tiếp
      |
      v
HTTP 200, user đã xác thực
~~~

Khi client **không gửi cookie** hoặc server không thể tra lại session, GET /me vẫn có thể là 401 dù request login đã gọi saveContext.

### 3.3. Điều kiện đủ cho phiên tiếp tục tồn tại

Với session-based authentication, tối thiểu cần đồng thời:

1. Authentication thực sự được xác minh bởi nguồn tin cậy.
2. Context được đặt vào SecurityContextHolder để request hiện hành sử dụng.
3. Context được lưu vào repository có khả năng duy trì qua HTTP requests.
4. Session/định danh phiên được gửi đến client trước khi response commit.
5. Client lưu và gửi lại đúng session cookie trên request sau.
6. Server vẫn còn session, chưa logout/expire/revoke và đọc đúng repository.
7. Request sau được xử lý qua security chain và session policy cho phép khôi phục context.
8. Authorities hiện hành đủ quyền cho endpoint cần truy cập.

Một mắt xích bị thiếu có thể tạo cảm giác “vừa login xong lại mất login”.

## 4. Spring Security 5 và Spring Security 6: điều đã thay đổi

Tài liệu chính thức mô tả hai cơ chế chính:

- **SecurityContextPersistenceFilter:** có thể tự lưu những thay đổi của SecurityContext trước khi response hoàn tất trong cấu hình sử dụng filter này.
- **SecurityContextHolderFilter:** đọc context từ SecurityContextRepository và đặt vào holder, nhưng **không tự động lưu các thay đổi**. Nếu custom code muốn persistence, nó phải gọi saveContext.

Trong **Spring Security 6 Servlet**, cấu hình mặc định được chuyển sang **SecurityContextHolderFilter với yêu cầu explicit save**. Đây là điểm dễ gây lỗi khi chuyển custom login code viết cho phiên bản cũ sang phiên bản mới.

~~~java
// Chưa đủ để duy trì Authentication cho request tiếp theo.
SecurityContextHolder.setContext(context);

// Cần thêm bước sau nếu chủ ý muốn lưu đăng nhập.
securityContextRepository.saveContext(
    context, httpServletRequest, httpServletResponse
);
~~~

Đoạn này là **snippet có biến context và repository đã được thiết lập**, không phải file Java độc lập. Nó cũng không chứa code xác minh password; context chỉ được lưu **sau khi** AuthenticationManager đã xác thực thành công.

### 4.1. Mặc định và tùy biến

Spring Security 6 hỗ trợ:

~~~java
http.securityContext(security -> security
    .requireExplicitSave(true)
);
~~~

Đây là snippet trong method cấu hình HttpSecurity; Spring Security 6 đã dùng explicit save theo mặc định ở Servlet stack thông thường. Nêu lại cấu hình để làm rõ hành vi, không phải một lời khuyên tùy tiện thay đổi settings.

**Không cấu hình đồng thời SecurityContextHolderFilter và SecurityContextPersistenceFilter** trong một chain với kỳ vọng cả hai cùng vận hành. Nếu migrate từ bản cũ, cần xác định filter nào đang được dùng, repository nào được nạp/lưu và liệu filter login tích hợp có persistence đúng.

### 4.2. Authentication filters tích hợp đã xử lý lifecycle

Khi dùng **formLogin(...)** hoặc một mechanism được Spring Security cung cấp, flow thành công có thể đã gọi session strategy, thiết lập context và save context theo thiết kế của filter. Bạn **không phải tự viết Controller gọi saveContext** cho mọi đăng nhập mặc định.

Vấn đề của bài chủ yếu xuất hiện khi developer **tự gọi AuthenticationManager hoặc tự tạo Authentication trong Controller/Filter** rồi nghĩ rằng Spring Security sẽ tự lưu phiên.

### 4.3. Tại sao explicit save hữu ích?

Nó làm cho thời điểm lưu có chủ đích và dễ hiểu hơn, hạn chế ghi repository không cần thiết và tránh sự mơ hồ khi response commit sớm. Code biết chắc khi nào login thành công và khi nào context phải được ghi vào session/store.

Đổi lại, custom code phải chịu trách nhiệm thực hiện việc đó đúng thời điểm; quên gọi saveContext thì request kế tiếp có thể mất authentication.

## 5. Các loại SecurityContextRepository

### 5.1. HttpSessionSecurityContextRepository

Lưu SecurityContext trong **HttpSession**. Ở ứng dụng browser dùng cookie, client thường giữ cookie session và gửi lại để server tìm session chứa context.

~~~text
Client Cookie: JSESSIONID=abc
            |
            v
Servlet container lấy HttpSession "abc"
            |
            v
HttpSessionSecurityContextRepository.loadDeferredContext(...)
            |
            v
SecurityContext với Authentication đã lưu
~~~

Nếu saveContext cần tạo session mới và policy cho phép, response có thể cần gửi **Set-Cookie**. Phải save trước khi response được commit, nếu không session ID mới có thể không tới client đúng cách.

**Lưu ý:** Một HttpSession có thể tồn tại nhưng repository không chứa Authentication đã xác thực. Session ID cũng có thể bị rotate sau login để chống session fixation.

### 5.2. RequestAttributeSecurityContextRepository

Lưu context như **request attribute** trong một HTTP request, giúp một số Servlet dispatch như ERROR có thể tìm lại context. Nó **không tạo cơ chế đăng nhập qua nhiều HTTP requests**.

Nếu bạn dùng RequestAttributeSecurityContextRepository và gọi saveContext, context có thể sống qua các dispatch thuộc **cùng request**, nhưng request #2 độc lập không khôi phục được nó từ request #1.

Đây là nguồn gốc một lỗi cấu hình hay gặp: developer thấy đã gọi saveContext, nhưng repository chỉ lưu request attribute và không có HttpSession backend.

### 5.3. DelegatingSecurityContextRepository

Trong Spring Security 6 Servlet, repository mặc định thường là **DelegatingSecurityContextRepository** kết hợp:

- **RequestAttributeSecurityContextRepository**
- **HttpSessionSecurityContextRepository**

Delegating repository cố gắng đọc context theo thứ tự delegate và khi save sẽ chuyển việc lưu cho các delegate. Nhờ đó vừa có hỗ trợ cùng request/dispatch, vừa có cơ chế persistence qua session theo policy.

Cấu hình mô tả:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

Đây là snippet trong một method có imports phù hợp. Ví dụ hoàn chỉnh ở phần 7 khai báo cùng repository thành bean để **cả filter và Controller dùng đúng một instance**.

### 5.4. NullSecurityContextRepository

NullSecurityContextRepository không lưu context và không khôi phục nó từ session. Nó phù hợp khi cơ chế xác thực **stateless** được cố ý thiết kế để xác minh lại credentials/token ở mỗi request.

~~~java
SecurityContextRepository repository =
    new NullSecurityContextRepository();
~~~

Nếu ứng dụng dùng NullSecurityContextRepository, gọi saveContext **không tạo session authentication**. Đây không phải bug; nó là lựa chọn kiến trúc. Không trộn NullSecurityContextRepository với yêu cầu “browser đăng nhập một lần rồi dùng session mãi” mà không có cơ chế lưu khác.

### 5.5. Bảng tổng kết

| Repository | Lưu ở đâu? | Request sau còn login? | Dùng trong trường hợp nào? |
| --- | --- | --- | --- |
| HttpSessionSecurityContextRepository | HttpSession | Có, nếu session/cookie/policy hợp lệ | Browser session login |
| RequestAttributeSecurityContextRepository | Servlet request attribute | **Không** qua request độc lập | Hỗ trợ dispatch trong một request |
| DelegatingSecurityContextRepository | Nhiều delegate, thường request attribute + session | Có thể, nếu session delegate lưu thành công | Cấu hình Servlet thông thường |
| NullSecurityContextRepository | Không lưu | **Không** | Stateless authentication |
| Custom SecurityContextRepository | Store tự thiết kế | Tùy triển khai | Distributed session/khả năng đặc thù |

Không xem **saveContext gọi thành công** là bảo đảm session đã lưu nếu repository/config cố tình không lưu qua requests.

## 6. Công thức đúng khi phải xác thực thủ công

Với một custom login mechanism thuộc ứng dụng, luồng cơ bản:

~~~java
// 1. Tạo yêu cầu chưa đáng tin từ input login.
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password
    );

// 2. Provider/manager xác minh credential.
Authentication verified =
    authenticationManager.authenticate(attempt);

// 3. Tạo context mới và đặt Authentication đã xác thực.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// 4. Nếu muốn request sau khôi phục danh tính từ session:
securityContextRepository.saveContext(context, request, response);
~~~

Đây là **snippet trong custom Controller hoặc authentication filter đã có biến/import/bean**, không phải login endpoint hoàn chỉnh để copy vào production.

### 6.1. Không tự bật authenticated=true từ input của client

Không làm:

~~~java
// NGUY HIỂM: không xác minh password/token.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
SecurityContextHolder.getContext().setAuthentication(forged);
~~~

Đoạn này là **anti-pattern minh họa**, tuyệt đối không sử dụng. Attacker có thể gửi username tùy ý, còn code tự cấp ROLE_ADMIN. Việc lưu Authentication forged vào session khiến lỗ hổng nghiêm trọng hơn.

### 6.2. Save trước khi commit response

Nếu response đã được gửi/commit (ví dụ redirect hoặc response body flush), việc tạo session mới và gửi Set-Cookie có thể không hoạt động đúng. Nên gọi saveContext **trong nhánh xác thực thành công, trước khi return/redirect/flush response**.

Không dùng HTTP 200 như chứng cứ context đã được lưu. Hãy kiểm tra session repository và HTTP response có session cookie khi phù hợp.

### 6.3. SessionAuthenticationStrategy và session fixation

**saveContext không thay thế toàn bộ login lifecycle.** Với custom login, cần xem xét **SessionAuthenticationStrategy**, đặc biệt việc đổi session ID sau khi người dùng đăng nhập để phòng session fixation. Spring Security 6 không mặc định chạy SessionManagementFilter để tự phát hiện mọi custom login rồi gọi strategy.

Các authentication mechanisms tích hợp xử lý lifecycle riêng; còn custom login có thể cần gọi strategy:

~~~java
sessionAuthenticationStrategy.onAuthentication(
    verified, request, response
);
securityContextRepository.saveContext(
    context, request, response
);
~~~

Chạy strategy trước save. Đoạn code chưa bao gồm CSRF, remember-me, concurrent sessions, success/failure handlers, MFA hoặc audit; chúng cần được đánh giá nếu triển khai thật.

### 6.4. Không tắt CSRF toàn cục để “sửa lỗi login”

Đối với browser sử dụng session cookie, endpoint thay đổi trạng thái đăng nhập có thể chịu rủi ro **login CSRF**. Đừng tắt CSRF chỉ vì curl POST bị 403; hãy dùng một CSRF token hợp lệ hoặc một kiến trúc xác thực và cookie riêng đã được đánh giá.

Demo bên dưới giữ CSRF mặc định và cho client lấy token tại một endpoint học tập. Nó chưa phải cơ chế đăng nhập production hoàn chỉnh, nhưng không dạy cách bỏ qua CSRF như giải pháp mặc định.

## 7. Thực hành đầy đủ với Spring Boot: một request và nhiều request

Mục tiêu thí nghiệm: cùng một username/password, tạo **hai endpoint POST** khác nhau:

- **POST /lab/volatile:** Xác thực hợp lệ và đặt context vào holder, nhưng cố ý **không gọi saveContext**.
- **POST /lab/persist:** Cùng xác thực hợp lệ, đặt context, gọi session strategy và **saveContext**.
- **GET /me:** Chỉ trả thành công nếu request đang có Authentication không phải anonymous.
- **GET /lab/csrf:** Cấp CSRF token để client trong demo có thể gửi POST hợp lệ mà không cần tắt CSRF.

**Quan trọng:** endpoint volatile cố ý thiếu bước persistence để minh họa lỗi, **không phải mẫu login production**. Endpoint persist cũng là lab rút gọn: chưa bao gồm toàn bộ trách nhiệm identity, rate limiting, MFA, concurrent-session policy, audit, logout và account recovery. Production nên dùng authentication mechanisms tích hợp khi phù hợp.

### 7.1. Tạo project và dependencies

Tạo project Java 17+, Spring Boot 3.x, Gradle Groovy DSL với Gradle Wrapper qua Spring Initializr. Chọn Spring Web, Spring Security, Test. Trong phần dependencies của **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **phần dependencies của một project Boot đã có plugin/BOM**, không phải toàn bộ build.gradle độc lập.

### 7.2. File Java có thể chạy trong project Boot

Tạo file **src/main/java/com/example/contextlab/ContextLabApplication.java**:

~~~java
package com.example.contextlab;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ContextLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextLabApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SessionAuthenticationStrategy sessionStrategy() {
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/public", "/lab/csrf").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/lab/volatile", "/lab/persist").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll()
            )
            // Không tắt CSRF: các lệnh POST cần token.
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .build();
    }
}

@RestController
class LabController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    LabController(AuthenticationManager manager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/lab/csrf")
    ResponseEntity<CsrfView> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfView(
                token.getHeaderName(), token.getToken()));
    }

    @PostMapping("/lab/volatile")
    ResponseEntity<Map<String, Object>> volatileLogin(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        return authenticate(username, password, false,
            request, response);
    }

    @PostMapping("/lab/persist")
    ResponseEntity<Map<String, Object>> persistentLogin(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {
        return authenticate(username, password, true,
            request, response);
    }

    private ResponseEntity<Map<String, Object>> authenticate(
            String username,
            String password,
            boolean persist,
            HttpServletRequest request,
            HttpServletResponse response) {

        final Authentication verified;
        try {
            verified = manager.authenticate(
                UsernamePasswordAuthenticationToken
                    .unauthenticated(username, password)
            );
        } catch (AuthenticationException failure) {
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(Map.of("error", "invalid_credentials"));
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        if (persist) {
            sessionStrategy.onAuthentication(
                verified, request, response);
            repository.saveContext(context, request, response);
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "authenticatedNow",
                SecurityContextHolder.getContext()
                    .getAuthentication().isAuthenticated(),
                "savedForNextRequest", persist
            ));
    }

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}

record CsrfView(String headerName, String token) {}
~~~

**Tính độc lập:** Đây là một file Java hoàn chỉnh **trong project Boot đã tạo**, với public class ContextLabApplication trùng tên file, LabController và record cùng package. Dự án phải có Gradle plugin/starter đúng. Java 17 hỗ trợ record, Map.of và các cú pháp sử dụng trong code.

**Chú ý phiên bản:** Ở Spring Security 6.x thuộc nhóm minh họa, DaoAuthenticationProvider hỗ trợ cách khởi tạo no-arg rồi setUserDetailsService và setPasswordEncoder. Các version mới hơn có thể thay đổi constructor hoặc API; luôn đối chiếu phiên bản thật của project. Không sao chép mẫu lab thành hệ thống production mà chưa rà soát session strategy và các security policies liên quan.

### 7.3. Giải thích các bean

**PasswordEncoder + UserDetailsService:** Tạo một tài khoản alice chỉ cho lab, password được BCrypt hash trước khi đưa vào in-memory user store. Raw password hard-code trong demo chỉ dành cho môi trường local cô lập; không dùng credential này trong deployment thật.

**AuthenticationManager:** ProviderManager gọi DaoAuthenticationProvider để xác minh username/password, từ đó mới trả Authentication đã xác thực. Không tự tạo authenticated token từ input của client.

**SecurityContextRepository:** DelegatingSecurityContextRepository kết hợp RequestAttributeSecurityContextRepository và HttpSessionSecurityContextRepository, giống hướng mặc định Spring Security 6 Servlet. Quan trọng là **filter và LabController inject cùng bean repository**.

**SessionAuthenticationStrategy:** ChangeSessionIdAuthenticationStrategy minh họa bước bảo vệ session fixation khi session có sẵn. Nó không tự thay thế mọi cơ chế session control/MFA; ở một phiên chưa có session, hành vi strategy phụ thuộc context thực tế.

**SecurityFilterChain:** /public, /lab/csrf và hai POST lab được permitAll; /me bắt buộc authenticated. HTTP Basic và formLogin được tắt để **request sau không vô tình được xác thực lại từ Basic header hoặc form login**, khiến ta hiểu nhầm context đã được lưu.

**CSRF:** Bài giữ cơ chế CSRF mặc định. Muốn POST vào hai endpoint, client cần CSRF token hợp lệ. GET /lab/csrf dùng để nhận token cho mục đích thí nghiệm; không phải endpoint triển khai production hoàn chỉnh.

**NullRequestCache:** Tắt saved-request caching trong lab để một HTTP 401 không tạo những side effects session không liên quan, làm kết quả dễ giải thích hơn.

**HttpStatusEntryPoint:** Khi GET /me thiếu authentication, response được cấu hình thành **401**. Nếu không đặt entry point, ứng dụng tùy cơ chế đang bật có thể chuyển hướng hoặc trả một status khác; không xem 401 là hành vi tự động của mọi SecurityFilterChain.

### 7.4. Phân tích hai method đăng nhập

Cả hai route đều gọi chung authenticate(...), nơi thực hiện:

~~~java
Authentication verified = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password
    )
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

Đây là snippet phần chung. Sau đó:

- Với **persist=false**, code trả 200 mà **không gọi repository.saveContext**.
- Với **persist=true**, code gọi sessionStrategy.onAuthentication và **repository.saveContext**, rồi mới trả 200.

Trong response, trường **savedForNextRequest** chỉ cho biết **nhánh code đã yêu cầu lưu**; nó không phải bằng chứng tuyệt đối session sẽ tồn tại mãi hoặc browser có lưu cookie. Phải kiểm tra bằng request sau với session cookie thật.

### 7.5. Vì sao demo không cho phép GET tự tạo login?

Đăng nhập thay đổi trạng thái danh tính và session. Dùng GET /login?username=...&password=... vừa gửi password vào URL dễ bị ghi trong history/log, vừa có nguy cơ login CSRF và không tuân thủ HTTP safe-method semantics.

Vì vậy bài dùng **POST** với form fields và cơ chế CSRF. Đây chỉ là một cơ chế học tập rút gọn; sản phẩm nên ưu tiên formLogin/oauth2Login hoặc các authentication mechanisms được framework hỗ trợ.

## 8. Chạy lab và kiểm tra hai HTTP requests

### 8.1. Chạy Spring Boot

Từ project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell: **.\gradlew.bat bootRun**.

Server mặc định chạy http://localhost:8080. Các lệnh bên dưới **chỉ dùng tài khoản mẫu local và HTTP trên localhost**, không dùng raw password thật trong command history hoặc shell variables dài hạn.

### 8.2. Bước chuẩn bị: CSRF token và cookie jar

Vì server vẫn bật CSRF, cần yêu cầu GET /lab/csrf để có token và cookie session. Ví dụ với curl:

~~~bash
curl -i -c session-demo.txt http://localhost:8080/lab/csrf
~~~

Response JSON có cấu trúc:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "gia-tri-token-duoc-sinh-tai-runtime"
}
~~~

Trường token trong ví dụ là mô tả, **không phải token thật**. Hãy dùng giá trị trả về từ server ở lần chạy của bạn. Cookie jar là file nhạy cảm vì có session ID; bảo vệ quyền đọc và xóa sau lab.

### 8.3. Luồng A: đặt context nhưng không lưu

Dùng cookie jar phiên đã có và token nhận từ /lab/csrf. Thay **CSRF_TOKEN_FROM_RESPONSE** bằng token đúng:

~~~bash
curl -i -b session-demo.txt -c session-demo.txt \
  -H "X-CSRF-TOKEN: CSRF_TOKEN_FROM_RESPONSE" \
  --data-urlencode "username=alice" \
  --data-urlencode "password=learn123" \
  http://localhost:8080/lab/volatile

curl -i -b session-demo.txt http://localhost:8080/me
~~~

Ở POST đầu, response kỳ vọng:

~~~json
{
  "authenticatedNow": true,
  "savedForNextRequest": false
}
~~~

Ngay sau đó, GET /me với **cùng cookie jar** kỳ vọng **401** vì context của login trước chưa được lưu vào session repository. Có session chứa CSRF token không làm GET /me trở thành authenticated.

### 8.4. Luồng B: lưu context vào HttpSession

Tạo cookie jar **mới**, tránh đã có Authentication từ thí nghiệm khác:

~~~bash
curl -i -c session-persist.txt http://localhost:8080/lab/csrf
~~~

Lấy token mới rồi gọi:

~~~bash
curl -i -b session-persist.txt -c session-persist.txt \
  -H "X-CSRF-TOKEN: CSRF_TOKEN_FROM_RESPONSE" \
  --data-urlencode "username=alice" \
  --data-urlencode "password=learn123" \
  http://localhost:8080/lab/persist

curl -i -b session-persist.txt http://localhost:8080/me
~~~

POST trả:

~~~json
{
  "authenticatedNow": true,
  "savedForNextRequest": true
}
~~~

GET /me với cookie jar đã cập nhật sau POST kỳ vọng **200**:

~~~json
{
  "user": "alice"
}
~~~

Nếu trình duyệt/curl **không gửi lại session cookie**, GET /me mới vẫn bị 401, dù server từng lưu context cho một phiên khác.

Sau lab, dừng server và xóa các cookie jar ở môi trường được kiểm soát. Không commit cookie jar, session ID hoặc CSRF token vào Git. Các password trong lệnh trên là giá trị demo công khai, **tuyệt đối không thay bằng password thật trên môi trường chia sẻ** vì arguments có thể xuất hiện trong shell history và process listing.

### 8.5. Bảng kết quả

| Thao tác | Lưu Context? | Session cookie được gửi lại? | GET /me sau đó |
| --- | --- | --- | --- |
| POST /lab/volatile thành công | **Không** | Có thể có cookie do CSRF | **401** |
| POST /lab/persist thành công | **Có** | **Có** | **200** |
| POST /lab/persist thành công | **Có** | **Không** | **401** |
| POST với username/password sai | **Không** | Bất kỳ | **401** ở login; request sau không có login mới |
| POST thiếu/CSRF token sai | Không tới logic login | Bất kỳ | **403** ở POST theo CSRF policy |

Đây là kết quả **dự kiến dựa trên cấu hình demo**, không phải output đã đo trong tài liệu. Nếu browser đã có session authenticated từ lần trước, cần dùng session/cookie jar mới để so sánh công bằng.

### 8.6. Sai CSRF không có nghĩa mật khẩu sai

POST /lab/persist với body đúng nhưng thiếu CSRF token có thể trả 403 **trước khi Controller gọi AuthenticationManager**. Vì vậy không sửa bằng cách đổi PasswordEncoder hoặc tạo Authentication thủ công. Hãy kiểm tra CSRF token và cookie session, rồi mới debug credentials.

## 9. MockMvc: chứng minh bằng hai request độc lập

Dùng **spring-security-test** và **spring-boot-starter-test** đã khai báo ở mục 7. Tạo file **src/test/java/com/example/contextlab/ContextLabApplicationTest.java**:

~~~java
package com.example.contextlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextLabApplicationTest {

    @Autowired MockMvc mvc;

    @Test
    void setContextAloneDoesNotPersistForNextRequest()
            throws Exception {

        MvcResult login = mvc.perform(post("/lab/volatile")
                .with(csrf())
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authenticatedNow").value(true))
            .andExpect(jsonPath("$.savedForNextRequest").value(false))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        MockHttpServletRequestBuilder next = get("/me");
        if (session != null) {
            // Nếu session tồn tại vì CSRF, nó chưa chứa login context.
            next.session(session);
        }

        mvc.perform(next)
            .andExpect(status().isUnauthorized());
    }

    @Test
    void explicitSaveAllowsNextRequestToReadSessionContext()
            throws Exception {

        MvcResult login = mvc.perform(post("/lab/persist")
                .with(csrf())
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authenticatedNow").value(true))
            .andExpect(jsonPath("$.savedForNextRequest").value(true))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        // Không chuyển session cho request mới: không có danh tính.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedContext()
            throws Exception {

        mvc.perform(post("/lab/persist")
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value(
                "invalid_credentials"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfTokenIsRejectedBeforeLogin()
            throws Exception {

        mvc.perform(post("/lab/persist")
                .param("username", "alice")
                .param("password", "learn123"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **file test đầy đủ trong project Boot**. MockMvc không tạo kết nối HTTP thật; session được chuyển giữa requests bằng **MockHttpSession**, mô phỏng browser gửi lại cookie và server tìm session tương ứng.

### 9.1. Tại sao phải dùng hai requests?

Nếu test chỉ gọi POST /lab/volatile và assert response 200, bạn mới chứng minh Authentication có trong request đầu. Bạn **chưa kiểm thử persistence**. Test phải gửi tiếp một request mới tới URL cần authenticated:

- Volatile: request sau cùng session nếu có, vẫn 401.
- Persist: request sau được gắn session, trả 200.
- Persist nhưng không chuyển session, request sau 401.
- Sai password hoặc thiếu CSRF, login không thành công.

Đó là phép kiểm chứng trực tiếp của khái niệm bài học.

### 9.2. Không chỉ assert Set-Cookie

Một response có Set-Cookie không bảo đảm cookie đó trỏ tới session đã lưu Authentication; cookie có thể được tạo cho CSRF, request cache hoặc chức năng khác. Ngược lại, khi login diễn ra trong session đã tồn tại, response có thể không cần tạo session ID mới trong mọi cấu hình.

**Thử GET /me tiếp theo với session/cookie hợp lệ** là kiểm tra có ý nghĩa hơn việc chỉ tìm header Set-Cookie.

### 9.3. Chạy tests

~~~bash
./gradlew test
~~~

PowerShell: **.\gradlew.bat test**.

Kết quả kiểm thử được mô tả là **kỳ vọng từ mã nguồn**, không phải một build đã được chạy trong tài liệu này. Khi áp dụng thật, cần chạy tests trên chính version Spring Boot/Security, servlet container, database, proxy và cấu hình deployment của dự án.

## 10. Form login, HTTP Basic và Bearer token: vì sao khác nhau?

### 10.1. Form login (session-based)

Với formLogin được Spring Security quản lý, flow có thể:

1. Nhận form username/password và CSRF token.
2. Filter gọi AuthenticationManager.
3. Provider xác minh credentials.
4. SessionAuthenticationStrategy xử lý session fixation/concurrency theo cấu hình.
5. Context được đặt và lưu qua repository.
6. Browser nhận/giữ cookie session.
7. Request sau gửi cookie, filter khôi phục context.

Với cơ chế này, framework đã xử lý các bước cần thiết theo cấu hình. Không cần thay bằng custom Controller chỉ để “tự gọi AuthenticationManager”.

### 10.2. HTTP Basic

HTTP Basic gửi Authorization: Basic ở các requests. Cơ chế có thể xác thực lại khi header xuất hiện; nó không có nghĩa một lần Basic thành công nhất thiết tạo một phiên browser login bền vững. Trong hệ thống cấu hình stateless, mỗi request phải có credential phù hợp.

Do đó, nếu bạn thấy GET /me có 200 liên tiếp khi **mỗi request đều mang Authorization header**, đó **không chứng minh HttpSession đã lưu context**.

### 10.3. Bearer/JWT resource server

Với Bearer token, client gửi Authorization: Bearer cho mỗi request. Resource server kiểm tra token, tạo Authentication trong SecurityContext của request, rồi áp authorization. Khi stateless, request sau lại xác thực dựa trên Bearer token được gửi.

Không cố lưu access token hoặc JWT vào HttpSession chỉ để “khắc phục mất login” khi hệ thống được thiết kế stateless. Cần chọn đúng cơ chế cho SPA/mobile/server-rendered web và threat model.

### 10.4. OAuth2/OIDC login

OAuth2/OIDC browser login thường có authorization-code flow, state, callback, session/cookie và các token protocol. Cơ chế lưu xác thực hoặc sử dụng token tùy cấu hình OAuth2 client/resource server. Không áp trực tiếp snippet custom username/password của bài lên OIDC callback.

**Phân biệt:** “Request hiện hành đã có Authentication” là trạng thái framework; “client đã có phương tiện chứng minh danh tính cho request sau” có thể là **session cookie**, **Bearer token** hoặc credentials khác. Hai thứ phải đi đôi theo kiến trúc, không nhất thiết luôn là HttpSession.

## 11. SessionCreationPolicy và sự hiểu nhầm về session

Spring Security cung cấp **SessionCreationPolicy** để điều chỉnh cách Security tạo/sử dụng session. Ý nghĩa khái quát:

| Policy | Ý định | Lưu ý |
| --- | --- | --- |
| **ALWAYS** | Spring Security tạo session | Không đồng nghĩa đã có user authenticated |
| **IF_REQUIRED** | Tạo session khi cần | Thường hợp với session-based login |
| **NEVER** | Spring Security không chủ động tạo session nhưng có thể dùng session đã tồn tại | Không phải tương đương STATELESS |
| **STATELESS** | Spring Security không tạo và không dùng HttpSession để lấy SecurityContext | Authentication theo token/credential mỗi request |

Ví dụ cho API stateless:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Đây là snippet trong SecurityFilterChain, không phải toàn bộ ứng dụng.

### 11.1. IF_REQUIRED có tự save Authentication không?

**Không.** IF_REQUIRED quyết định khả năng tạo session khi cần, nhưng custom code vẫn phải thực hiện bước lưu context theo SecurityContextRepository và explicit-save semantics. Nó không tự đoán Authentication nào vừa được xác thực.

### 11.2. NEVER không bảo đảm không có cookie

NEVER mô tả chính sách của Spring Security; servlet container hoặc phần khác của app vẫn có thể tạo session. Spring Security có thể dùng session đã tồn tại. Nếu muốn thiết kế stateless nghiêm ngặt, cần kiểm tra repository và các cơ chế khác, không chỉ một enum.

### 11.3. STATELESS và saveContext

Với SessionCreationPolicy.STATELESS, Spring Security thường dùng repository không duy trì Authentication qua HttpSession. Một custom Controller gọi saveContext nhưng muốn “browser giữ session login” có thể không đạt kết quả mong đợi. Đừng thay STATELESS bằng ALWAYS bừa bãi nếu API được thiết kế JWT/Bearer; cần lựa chọn đúng kiến trúc.

## 12. Cookies, CORS và reverse proxy

Ngay cả khi saveContext đúng, client vẫn có thể không giữ phiên. Các nguyên nhân thường gặp:

- Cookie không được lưu vì domain/path không khớp.
- Cookie có Secure nhưng app đang thử trên HTTP không phù hợp; trong production Secure cần HTTPS.
- SameSite policy chặn gửi cookie ở ngữ cảnh cross-site.
- Trình duyệt dùng cross-origin fetch nhưng credentials mode không cho gửi cookie.
- Backend cấu hình CORS không cho phép origin/credentials phù hợp.
- Proxy/load balancer sửa hoặc làm mất Set-Cookie hay Cookie.
- Session store trên server A khác server B mà không dùng shared store/sticky session phù hợp.
- Session timeout, logout, invalidation hoặc restart làm mất phiên.
- Cookie chỉ dùng cho subpath khác với URL request sau.

### 12.1. Fetch từ browser

Một ứng dụng frontend gọi API khác origin có thể cần:

~~~javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
~~~

Đây là snippet minh họa, không phải cấu hình CORS hoàn chỉnh. Server vẫn phải trả CORS headers phù hợp và cookie policy cho phép. **credentials: "include" không tự vượt SameSite, Secure, origin policy hoặc browser privacy restrictions.**

Không cấu hình Access-Control-Allow-Origin: * cùng credentials=true; chọn origin được phép cụ thể. Dùng HTTPS ở production và kiểm tra session cookie trong Developer Tools một cách có kiểm soát.

### 12.2. Phân biệt cookie session và token API

Cookie session thường là định danh trỏ tới state ở server. JWT/Bearer token thường mang hoặc tham chiếu tới quyền truy cập và được kiểm tra theo giao thức ở mỗi request. Đừng sử dụng cách giải quyết mất phiên của hệ cookie cho Bearer API nếu nguyên nhân thật là client không gửi Authorization header.

## 13. Logout: xóa context trong RAM thôi cũng chưa đủ

Nếu một login session đã được lưu trong HttpSession, chỉ gọi:

~~~java
SecurityContextHolder.clearContext();
~~~

có thể chỉ xóa context đang được giữ trong request; repository/session vẫn có context đã lưu. Request sau dùng cùng session cookie có thể khôi phục user và “đăng nhập lại”.

Để logout đúng với session-based login, cần:

- Invalidate HttpSession và xóa các session data phù hợp.
- Clear SecurityContextHolder.
- Lưu trạng thái đã clear nếu repository/session policy yêu cầu.
- Dọn cookie hoặc yêu cầu browser không tái sử dụng cookie.
- Thu hồi remember-me/token khi có cơ chế liên quan.
- Xem xét CSRF và logout HTTP method policy.

**Ưu tiên Spring Security logout() tích hợp** vì nó xử lý nhiều bước lifecycle. Nếu custom logout, chỉ clear ThreadLocal không đủ để thu hồi một session đã lưu.

Tương tự, khi user đổi password hoặc bị revoke role, session/token cũ có thể vẫn giữ authorities cũ. Cần chiến lược invalidation/refresh/recheck, không suy ra một Authentication trong RAM tự cập nhật theo database.

## 14. ThreadLocal, @Async và nhiều request đồng thời

### 14.1. SecurityContextHolder không phải biến toàn cục ứng dụng

Trong Servlet, mặc định holder dựa trên ThreadLocal. Dù các request được xử lý bởi cùng thread trong pool ở những thời điểm khác nhau, Spring Security dọn context để tránh user A rò sang user B.

Không làm:

~~~java
// ANTI-PATTERN: giữ state đăng nhập toàn cục.
static Authentication currentUser;
~~~

Một biến static như vậy có thể trộn danh tính của nhiều người dùng đồng thời và hoàn toàn không liên quan tới Session cookie.

### 14.2. Chạy công việc bất đồng bộ

Code tạo thread, dùng CompletableFuture, @Async hoặc executor không mặc nhiên mang SecurityContextHolder từ request hiện hành sang thread mới. Spring Security có các adapter hỗ trợ propagation như DelegatingSecurityContextRunnable và DelegatingSecurityContextExecutor khi có nhu cầu phù hợp.

**Context propagation khác với persistence.** Copy context sang worker thread phục vụ cùng một tác vụ không lưu danh tính cho HTTP request sau. Ngược lại, lưu context vào session không bảo đảm một thread async tự nhìn thấy holder.

Khi truyền context tới worker, phải giới hạn phạm vi và dọn sau tác vụ. Không giữ principal/credentials lâu trong hàng đợi công việc hoặc thread pool.

### 14.3. Tạo context mới tránh sửa instance chia sẻ

Tài liệu Spring Security khuyến nghị tạo một SecurityContext mới với createEmptyContext trước khi setAuthentication, thay vì mutate tùy ý SecurityContext đã tồn tại. Cách này giúp giảm rủi ro state dùng chung giữa các thread hoặc những component đang giữ tham chiếu tới cùng context.

Dù vậy, tạo context mới **vẫn không tự save vào session**. Hai bước giải quyết hai vấn đề khác nhau.

## 15. Các lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân tiềm năng | Cách kiểm tra |
| --- | --- | --- |
| POST login trả 200 nhưng GET /me 401 | Chỉ setContext, quên saveContext | Đọc lại custom login code và repository |
| POST login có Authentication nhưng không có cookie | Session chưa được tạo/lưu hoặc response commit sớm | Kiểm tra saveContext và Set-Cookie |
| Có JSESSIONID nhưng vẫn anonymous | Session chỉ chứa CSRF/saved request, không có context | Kiểm tra session repository |
| Gọi saveContext mà request sau vẫn 401 | Repository chỉ là RequestAttribute/Null, hoặc client không gửi cookie | Xác minh concrete repository và headers |
| IF_REQUIRED nhưng login không giữ | IF_REQUIRED không tự save custom context | Thêm đúng persistence step |
| STATELESS nhưng muốn dùng HttpSession | Kiến trúc mâu thuẫn | Chọn session hoặc token-based design |
| Gửi Bearer token mỗi lần đều 200 | Token được kiểm tra lại, không chứng minh session đã lưu | Test request không mang token |
| Browser nhận 200 nhưng fetch /me 401 | Cross-origin cookie/credentials/CORS/SameSite | Developer Tools và CORS settings |
| Chỉ test một POST nên không phát hiện lỗi | Chưa tạo request thứ hai | MockMvc test hai requests + session |
| Login bằng custom Controller không rotate ID | Bỏ SessionAuthenticationStrategy | Dùng built-in login hoặc strategy phù hợp |
| POST login 403 trước khi vào Controller | CSRF token thiếu/sai | Kiểm tra token + cookie; không tắt CSRF vô cớ |
| GET /me trả 302 tới /login thay vì 401 | Form login entry point đang bật | Phân biệt redirect với Basic/API entry point |
| Logout xong request sau vẫn login | Chỉ clear holder, session còn context | Spring Security logout + session invalidation |
| User bị revoke role nhưng session vẫn cho qua | Authorities cũ trong session | Revocation/refresh/business authorization |
| Hai SecurityFilterChain dùng repository khác | Context lưu ở chain A nhưng chain B không đọc | Kiểm tra matching và repository từng chain |
| Async worker không thấy Authentication | ThreadLocal không tự propagate | Dùng context propagation khi thích hợp |

### 15.1. Đừng cố sửa bằng cách giữ Authentication trong static Map tùy ý

Lưu Authentication theo username vào static Map toàn cục rồi truy cập trong request tiếp theo không tạo một session model an toàn. Bạn phải giải quyết ID phiên khó đoán, binding client, timeout, logout, concurrency, storage và rotation. Spring Security và servlet container đã có cơ chế phù hợp hơn.

### 15.2. Đừng sửa bằng cách luôn đặt authenticated=true

Nếu request sau 401 do không tìm thấy context, chuyển thành authenticated=true mà không kiểm tra credential chỉ tạo authentication bypass. Cần kiểm tra **persistence và cookie**, không bỏ bảo mật.

### 15.3. Đừng ghi raw Authentication ra log để debug

Authentication hoặc principal có thể chứa password hash, details, token hoặc dữ liệu cá nhân. Khi debug, chỉ log event, request correlation ID và các thông tin đã được cho phép; tránh in Authorization/Cookie/Session ID, full SecurityContext hoặc credentials.

## 16. Checklist điều tra theo từng giai đoạn

Khi một user báo “đăng nhập xong request sau bị 401”, đi theo thứ tự:

1. **Xác thực có thành công không?** Kiểm tra AuthenticationManager trả verified hay AuthenticationException.
2. **Có context đúng không?** Custom code tạo context mới và setAuthentication(verified) chưa?
3. **Có lưu không?** saveContext được gọi ở nhánh thành công trước response commit chưa?
4. **Repository nào?** HttpSession, RequestAttribute, Delegating hay Null; có cùng repository giữa filter và Controller không?
5. **Session policy?** IF_REQUIRED/NEVER/STATELESS có phù hợp mong muốn browser-session login không?
6. **Session strategy?** Session fixation, concurrent session policies và login lifecycle có được xử lý không?
7. **Response có Set-Cookie thích hợp không?** Nếu session mới hoặc ID đổi, cookie có đến client không?
8. **Request tiếp theo có gửi Cookie không?** Domain, path, Secure, SameSite, CORS, fetch credentials và proxy?
9. **Session server còn không?** Timeout, restart, load balancer, distributed session store, logout/revocation?
10. **SecurityFilterChain nào được chọn?** Request sau có vào cùng chain/repository hoặc chain được cấu hình tương thích không?
11. **Authn và authz có bị nhầm?** 401/302 có thể là chưa xác thực; 403 có thể do thiếu role hoặc CSRF.
12. **Có vô tình xác thực lại không?** HTTP Basic hoặc Bearer header ở mọi request có thể che lỗi session persistence.
13. **Test với hai request mới:** dùng MockHttpSession hoặc cookie jar riêng, không chỉ assert POST login 200.
14. **Kiểm tra an toàn logs:** Không in credential, Cookie/Authorization hoặc session ID khi điều tra.
15. **Kiểm tra logout và expiry:** Có hành vi đúng sau khi logout hoặc session hết hạn không?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** AuthenticationManager.authenticate trả Authentication đã xác thực có tự tạo session không?  
**Đáp:** Không. Nó xác thực credential và trả kết quả; persistence thuộc cơ chế filter/repository hoặc code được thiết kế để lưu.

**Câu 2.** SecurityContextHolder.setContext(context) có tự bảo đảm GET /me sau login nhận 200 không?  
**Đáp:** Không. Với Spring Security 6 và SecurityContextHolderFilter, custom code cần saveContext nếu muốn lưu qua request.

**Câu 3.** Vì sao người dùng có thể nhận HTTP 200 ở POST /login nhưng 401 ở GET /me?  
**Đáp:** Login xử lý thành công trong request đầu, nhưng context chưa được lưu/khôi phục hoặc client không gửi đúng session cookie.

**Câu 4.** RequestAttributeSecurityContextRepository có giữ login giữa các HTTP requests riêng biệt không?  
**Đáp:** Không. Nó phục vụ các dispatch trong cùng request.

**Câu 5.** HttpSessionSecurityContextRepository lưu context ở đâu?  
**Đáp:** Trong HttpSession; request sau phải có cách xác định đúng session, thường qua cookie.

**Câu 6.** Vì sao JSESSIONID có thể tồn tại mà user vẫn anonymous?  
**Đáp:** Session có thể do CSRF, request cache hoặc chức năng khác tạo mà không có Authentication đã lưu.

**Câu 7.** NullSecurityContextRepository.saveContext có biến client thành session login không?  
**Đáp:** Không. Repository này chủ ý không lưu.

**Câu 8.** IF_REQUIRED có nghĩa custom controller không cần saveContext chứ?  
**Đáp:** Không. Session policy và explicit persistence là hai việc khác nhau.

**Câu 9.** STATELESS có nghĩa request không có Authentication không?  
**Đáp:** Không. Có thể tạo Authentication từ JWT/Bearer ở mỗi request nhưng không lưu vào HttpSession.

**Câu 10.** Vì sao login mechanism cần SessionAuthenticationStrategy?  
**Đáp:** Có thể cần đổi session ID để chống fixation và quản lý các chính sách phiên theo cấu hình. saveContext một mình không thay mọi lifecycle.

**Câu 11.** POST login có password đúng nhưng thiếu CSRF token trả 403 có phải sai password không?  
**Đáp:** Không. CSRF filter có thể từ chối request trước khi gọi Controller hoặc provider.

**Câu 12.** Chỉ kiểm tra Set-Cookie trên response đã đủ chứng minh user đăng nhập bền vững chưa?  
**Đáp:** Chưa. Cookie có thể chỉ dành cho CSRF hoặc các mục đích khác; phải thử request sau với đúng session.

**Câu 13.** Tại sao dùng MockHttpSession trong test persistence?  
**Đáp:** Mô phỏng request sau thuộc cùng phiên, để kiểm tra SecurityContextRepository khôi phục context.

**Câu 14.** Một Bearer API trả 200 liên tiếp với token giống nhau chứng minh context đã lưu session chưa?  
**Đáp:** Không. Có thể request nào cũng xác minh token lại.

**Câu 15.** Nếu chỉ SecurityContextHolder.clearContext() khi logout, điều gì có thể xảy ra?  
**Đáp:** Session repository vẫn giữ context cũ, request sau có thể tải lại danh tính.

**Câu 16.** Có nên tạo token authenticated từ role do client gửi để tránh GET /me 401?  
**Đáp:** Không. Đó là authentication bypass; phải xác minh credentials và sửa lỗi lưu/đọc context.

**Câu 17.** SecurityContextHolder tự đi theo CompletableFuture hoặc @Async không?  
**Đáp:** Không mặc nhiên. Phải dùng cơ chế propagation khi phù hợp; đây cũng không phải session persistence.

## 18. Tài liệu chính thức

- Spring Security — Persisting Authentication (SecurityContextRepository, các filter và explicit save): https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Session Management Migration trong Spring Security 6: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Servlet Architecture, FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Bearer/JWT Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Session Fixation: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
