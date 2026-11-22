# SessionAuthenticationStrategy trong cơ chế xác thực tích hợp và tùy chỉnh

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài giải thích vai trò, vị trí gọi và thứ tự xử lý của `SessionAuthenticationStrategy` khi đăng nhập thành công; so sánh luồng form login tích hợp sẵn với một authentication filter do ứng dụng tự viết; sau đó cấu hình, kiểm thử session fixation, giới hạn số phiên, lưu `SecurityContext`, CSRF và phân biệt stateful/stateless. Ví dụ Spring bên dưới là mã của **một dự án Spring Boot**, không phải một chương trình chỉ có thể chạy bằng `javac`; mục cuối có ví dụ Java 17 độc lập với stdout cụ thể.

## 1. SessionAuthenticationStrategy giải quyết vấn đề gì?

Sau khi người dùng cung cấp credential hợp lệ, việc tạo một `Authentication` đã xác thực mới chỉ trả lời câu hỏi *ai vừa được xác thực?*. Ứng dụng web dùng **HTTP session** còn phải quyết định:

- Có nên tiếp tục cho tài khoản này mở phiên mới khi đã đạt giới hạn số phiên đồng thời?
- Có phải thay đổi **session ID** để chống session fixation?
- Có cần đăng ký phiên mới vào bộ quản lý phiên để áp dụng concurrent-session policy?
- Có phải xóa/đổi trạng thái token liên quan tới quá trình xác thực, ví dụ CSRF token cũ?
- Nếu một chiến lược từ chối đăng nhập, ứng dụng có được lưu `SecurityContext` hoặc trả success redirect nữa không?

`org.springframework.security.web.authentication.session.SessionAuthenticationStrategy` là hợp đồng để thực thi **các công việc gắn với sự kiện xác thực thành công và session**, thường trước khi authentication success handler gửi response.

Chữ ký API tối giản:

~~~java
public interface SessionAuthenticationStrategy {
    void onAuthentication(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response)
            throws SessionAuthenticationException;
}
~~~

Đây là **chữ ký rút gọn của thư viện**, không phải interface cần tạo lại. `SessionAuthenticationException` là một loại `AuthenticationException`, vì vậy sự từ chối của strategy có thể dẫn về **authentication failure flow** thay vì trả về phiên đã đăng nhập.

**Điều không đúng:** “UserDetailsService hoặc AuthenticationProvider tự động đăng ký session.” Hai thành phần đó xác minh danh tính/credential; quản lý session là trách nhiệm khác.

## 2. Nhận diện đúng các thành phần trong hệ thống

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| `AuthenticationProvider` | Kiểm tra credential và tạo authentication đã xác thực. | Không sở hữu cookie phiên. |
| `AuthenticationManager`, thường `ProviderManager` | Chọn provider và điều phối việc xác thực. | Không phải `SecurityContextRepository`. |
| `SessionAuthenticationStrategy` | Áp dụng policy khi **có authentication thành công**: số phiên, fixation, đăng ký, token lifecycle. | Không phải bộ lưu principal qua request. |
| `SecurityContextHolder` | Cho code hiện tại truy cập context; mặc định liên hệ với thread đang xử lý. | Không phải DB/session persistence. |
| `SecurityContextRepository` | Tải và lưu `SecurityContext` qua các request, tùy session policy. | Không tự gọi session strategy khi credential được xác minh. |
| `RequestCache` / `SavedRequest` | Nhớ yêu cầu trước khi đăng nhập để phục vụ điều hướng. | Không kiểm soát số phiên đăng nhập. |
| `AuthenticationSuccessHandler` | Quyết định response/redirect sau login. | Không thay thế session fixation protection. |
| `SessionRegistry` | Theo dõi session và principal để quản lý concurrency. | Không phải servlet container session store. |
| `HttpSessionEventPublisher` | Phát sự kiện tạo/hủy/thay đổi session từ servlet container cho Spring Security listeners. | Không tự xác minh credential. |

**Đặt câu hỏi đúng tầng:** “Sau POST /login được đổi session ID chưa?” thuộc session strategy; “GET /me request sau có còn principal?” thuộc repository/session cookie; “POST /login có đúng mật khẩu không?” thuộc provider; “GET /admin có được phép không?” thuộc authorization.

## 3. Thời điểm strategy được gọi trong form login tích hợp

Đối với cấu hình **Servlet form login** thường gặp, `UsernamePasswordAuthenticationFilter` kế thừa `AbstractAuthenticationProcessingFilter`. Trình tự khái quát của filter này là:

~~~text
POST /login + CSRF token hợp lệ
        |
        v
CsrfFilter (kiểm tra request trước login filter)
        |
        v
UsernamePasswordAuthenticationFilter
  |  attemptAuthentication(request, response)
  |     -> AuthenticationManager.authenticate(...)
  |     -> AuthenticationProvider xác minh credential
  |     -> trả Authentication đã xác thực
  |
  |  sessionAuthenticationStrategy.onAuthentication(
  |      authResult, request, response)
  |     -> policy số phiên / session ID / registration / CSRF
  |     -> có thể ném SessionAuthenticationException
  |
  |  successfulAuthentication(...)
  |     -> tạo/đặt SecurityContext
  |     -> lưu theo SecurityContextRepository
  |     -> remember-me, events, success handler tùy cấu hình
  v
302 Location theo success handler (hoặc response thành công khác)
~~~

Nếu `attemptAuthentication` ném `AuthenticationException` vì sai mật khẩu, **strategy không được gọi để đăng ký phiên mới**. Nếu strategy ném `SessionAuthenticationException`, luồng authentication phải được xử lý như thất bại; không gửi success redirect và không được lưu một context authenticated mới.

Cần phân biệt **authentication request** với các request sử dụng phiên đã có:

~~~text
Lần 1: POST /login -> credential đúng -> gọi strategy -> ghi context
Lần 2: GET /profile -> nạp context đã lưu -> KHÔNG phải login mới
Lần 3: GET /orders  -> nạp context đã lưu -> KHÔNG gọi strategy lại
~~~

Gọi session strategy ở **mỗi request** thay vì chỉ khi có authentication mới có thể làm xoay session ID liên tục, đăng ký lặp, gây logout bất thường và phá tính đúng của concurrent-session policy.

### Spring Security 6 và SessionManagementFilter

Ở các mô hình cũ, tài liệu/ứng dụng có thể dựa vào `SessionManagementFilter` để **phát hiện context vừa thay đổi** và gọi `SessionAuthenticationStrategy`. Với cách tiếp cận mặc định của Spring Security 6, **authentication mechanism chịu trách nhiệm gọi strategy** khi có một lần xác thực mới; không nên giả định `SessionManagementFilter` mặc nhiên nằm trong chain và làm hộ custom filter.

Điều này rất quan trọng khi bạn tự làm filter:

~~~text
CUSTOM FILTER SAI:
  manager.authenticate(requestToken)
  SecurityContextHolder.getContext().setAuthentication(result)
  chain.doFilter(...)
  [quên gọi SessionAuthenticationStrategy]
  [quên lưu SecurityContext]
  -> session fixation/concurrency/CSRF hoặc persistence có thể sai
~~~

Spring Security 6 cũng thiên về **explicit save** qua `SecurityContextHolderFilter` và `SecurityContextRepository` theo cấu hình. Chỉ đặt result vào `SecurityContextHolder` **không bảo đảm** request sau sẽ khôi phục được authentication. Với filter tùy chỉnh, hoặc dùng lớp filter chuẩn đã hỗ trợ việc gọi strategy và lưu context, hoặc triển khai cả hai công đoạn rõ ràng.

## 4. Các SessionAuthenticationStrategy thường dùng

### 4.1. `ChangeSessionIdAuthenticationStrategy`

Chiến lược này đổi ID của session hiện có thông qua cơ chế `HttpServletRequest.changeSessionId()`, thích hợp với Servlet API hiện đại. Mục tiêu là chống **session fixation**: kẻ tấn công không được tiếp tục dùng một session ID đã biết trước khi nạn nhân đăng nhập.

~~~text
Trước login:
  Cookie JSESSIONID=preLoginId
  Session chứa dữ liệu trước đăng nhập

Sau login thành công:
  Cookie JSESSIONID=postLoginId
  preLoginId != postLoginId
  Các session attributes phù hợp có thể được giữ
~~~

Đổi session ID **không phải** đặt `JSESSIONID` trực tiếp từ chuỗi người dùng gửi, cũng không phải đổi username. `changeSessionId()` cần session hiện có; chiến lược chỉ đổi ID của session khi đã có session theo cơ chế đó, không nên kỳ vọng mọi lần login đều tạo một session mới nếu app được cấu hình không tạo session.

Các lựa chọn liên quan trong cấu hình Spring Security có thể gồm:

- `sessionFixation().changeSessionId()`: thay ID với Servlet container hỗ trợ.
- `sessionFixation().migrateSession()`: tạo phiên mới và chuyển thuộc tính phiên khi phù hợp.
- `sessionFixation().newSession()`: tạo phiên mới với chính sách không chuyển những thuộc tính ứng dụng cũ theo cơ chế tương ứng.
- `sessionFixation().none()`: tắt bảo vệ fixation; **không khuyến nghị** chỉ để sửa một test đang thất bại.

Chiến lược mặc định và chi tiết chuyển thuộc tính có thể tùy Servlet API/phiên bản/cấu hình; **kiểm thử cookie/session thực tế** thay vì chỉ dựa trên tên API.

### 4.2. `ConcurrentSessionControlAuthenticationStrategy`

Chiến lược này đối chiếu số phiên hiện có của principal qua `SessionRegistry` rồi quyết định có cho authentication mới tiếp tục hay không. Có hai chính sách khác nhau:

- **Từ chối login mới khi đạt giới hạn:** cấu hình `setExceptionIfMaximumExceeded(true)`, ném `SessionAuthenticationException`. Phiên cũ vẫn là phiên được cho phép.
- **Cho login mới và đánh dấu phiên cũ hết hiệu lực:** cấu hình `setExceptionIfMaximumExceeded(false)`. Lúc này cần bảo đảm các request tiếp theo của phiên đã bị đánh dấu được chặn/invalidate thông qua cơ chế đồng bộ và kiểm soát session phù hợp, thường là `ConcurrentSessionFilter` hoặc cấu hình `maximumSessions(...)` của Spring Security.

Hai lựa chọn mang ý nghĩa UX/bảo mật khác nhau. Đừng tự suy ra “maxSessions(1)” luôn ngắt phiên cũ hay luôn từ chối login mới; phải biết rõ `maxSessionsPreventsLogin(...)` hoặc thuộc tính `exceptionIfMaximumExceeded` đang dùng.

`SessionRegistry` dùng **principal** để xác định các phiên. Nếu ứng dụng dùng custom `UserDetails` nhưng `equals()/hashCode()` của principal không ổn định, cùng một người dùng qua hai lần login có thể bị coi là hai principal khác nhau, khiến kiểm soát concurrency sai. Đây là lỗi dễ bị bỏ sót khi “session registry hoạt động nhưng người dùng vẫn tạo nhiều phiên”.

### 4.3. `RegisterSessionAuthenticationStrategy`

Sau khi policy cho phép, chiến lược đăng ký `principal + session ID` vào `SessionRegistry`. Nó không tự kiểm chứng password, không tự cấp authorities và cũng không thay cho việc lưu `SecurityContext`.

Vì đăng ký phải diễn ra **sau** việc đổi session ID, thứ tự có ý nghĩa:

~~~text
1) ConcurrentSessionControlAuthenticationStrategy
   -> kiểm tra có cho phép tạo phiên mới?

2) ChangeSessionIdAuthenticationStrategy
   -> đổi session ID sau đăng nhập nếu cần

3) RegisterSessionAuthenticationStrategy
   -> lưu principal và ID mới vào SessionRegistry
~~~

Nếu đảo `RegisterSessionAuthenticationStrategy` lên trước bước đổi ID, registry có thể ghi ID không đúng với session thực tế. Nếu kiểm tra concurrency sau khi đã đăng ký, bạn có thể tự tăng số phiên rồi đánh giá sai policy. Đây là lý do nên dùng `CompositeSessionAuthenticationStrategy` khi kết hợp nhiều tác vụ có thứ tự.

### 4.4. `CsrfAuthenticationStrategy`

Đây là chiến lược liên quan vòng đời **CSRF token** khi người dùng xác thực, nhằm tránh sử dụng tiếp token cũ không phù hợp qua ranh giới authentication. Nó hoạt động kết hợp với `CsrfTokenRepository` và `CsrfFilter`, **không** thay thế việc kiểm tra token trên POST.

Với form login dùng cookie/session:

- POST `/login` thường **phải có CSRF token hợp lệ** trước khi auth filter xử lý.
- Sau một lần authentication thành công, token cũ có thể bị xóa/đổi theo cấu hình; form tiếp theo cần lấy token mới.
- Không tắt CSRF chỉ để tạo session test dễ hơn.
- Nếu tự ghép composite/override strategy, hãy kiểm tra **CSRF lifecycle** và cấu hình repository tương ứng, tránh vô ý bỏ sót cơ chế của framework.

### 4.5. `NullAuthenticatedSessionStrategy`

Chiến lược này không thực hiện công việc session khi authentication thành công. Nó có thể phù hợp cho cơ chế **stateless** được thiết kế cẩn thận, nhưng **không phải** cách sửa lỗi cho form login đang cần session fixation và giới hạn phiên.

Nếu endpoint xác thực bằng Bearer JWT trên mỗi request, thường không có thao tác “đăng nhập thành công rồi lưu session web” như form login. JWT validation/authorization là một flow khác; không gọi concurrency registry mỗi lần decode token như thể user vừa tạo session mới.

## 5. Vì sao thứ tự xử lý và nơi đặt strategy là quan trọng?

Giả sử giới hạn một phiên cho mỗi principal; chiến lược được sắp:

~~~text
CONCURRENCY CHECK
       |
       | cho phép
       v
SESSION ID ROTATION
       |
       v
SESSION REGISTRY UPDATE
       |
       v
CSRF TOKEN LIFECYCLE
       |
       v
SECURITY CONTEXT SAVE
       |
       v
SUCCESS RESPONSE
~~~

Nếu strategy đầu tiên từ chối vì đã có một phiên khác, các bước còn lại không được chạy như thể đăng nhập thành công. Với `CompositeSessionAuthenticationStrategy`, các delegate chạy theo thứ tự danh sách; exception sẽ làm gián đoạn luồng tương ứng.

Hai điểm không được đánh đồng:

1. **Register session vào registry** chỉ giúp theo dõi concurrency, nó không đồng nghĩa `SecurityContext` đã được lưu để request kế tiếp nhận lại principal.
2. **Ghi SecurityContext vào session** chỉ làm principal được nạp lại; nếu quên các strategy bảo vệ, hệ thống vẫn có thể dễ mắc session fixation hoặc bỏ qua giới hạn đăng nhập.

**Session fixation protection không phải session expiration.** Đổi session ID trong cùng một phiên sau login khác với đánh dấu phiên của một user đã đăng nhập trước đó là expired. Với ứng dụng cho login mới thay phiên cũ, cần cả đánh dấu/session filter và cơ chế sự kiện session phù hợp.

## 6. Ví dụ 1 — Form login tích hợp sẵn, chỉ dùng cấu hình

Khi không cần custom authentication filter, cách ngắn gọn là cấu hình policy của Spring Security thay vì tự tạo các delegate.

~~~java
package com.example.sessionlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FormLoginPolicyExample {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(true));

        return http.build();
    }
}
~~~

**Đoạn này minh họa policy cho form login**, không được đặt đồng thời với full `SecurityConfig` ở mục 8 trong cùng ứng dụng demo vì sẽ tạo hai chain chồng lấn. Chọn **một** cấu hình phù hợp.

Với `.maximumSessions(1).maxSessionsPreventsLogin(true)`, user có một phiên đang hoạt động sẽ bị từ chối tạo phiên thứ hai; nếu session đã hủy thì registry cần được cập nhật để tránh coi phiên cũ vẫn còn hoạt động. Với Spring Boot/Servlet, thường cần đăng ký `HttpSessionEventPublisher` như mục 8. Nếu chọn `maxSessionsPreventsLogin(false)`, login mới có thể đánh dấu phiên cũ hết hiệu lực; cần test request từ phiên cũ bị xử lý đúng.

Điểm quan trọng: cấu hình fluent này cho phép Spring Security ghép các strategy cần thiết vào **authentication mechanism tích hợp sẵn**. Đối với custom filter do ứng dụng tự viết, việc khai báo policy tương tự chưa chắc đảm bảo filter mới đã gọi đúng strategy.

## 7. Ví dụ 2 — Cùng một SessionAuthenticationStrategy cho form và custom filter

Bài toán demo: ứng dụng có **hai endpoint đăng nhập username/password** để dễ so sánh:

- `POST /login`: cơ chế form login tích hợp của Spring Security.
- `POST /partner-login`: filter tùy chỉnh dùng `AbstractAuthenticationProcessingFilter`.
- Cả hai dùng **cùng** `AuthenticationManager` và **cùng** `SessionAuthenticationStrategy`.
- Cả hai lưu vào **cùng** `SecurityContextRepository`.
- Policy là **tối đa một session trên một principal, từ chối login thứ hai**, đổi session ID sau đăng nhập, ghi registry và quản lý token CSRF.

Demo cố tình dùng lại username/password để quan sát khác biệt về **filter**. Trong ứng dụng thật, nếu vẫn là form login thông thường, ưu tiên `UsernamePasswordAuthenticationFilter` có sẵn thay vì viết lại. Với OTP, magic link, API-key exchange hoặc credential đặc thù, custom filter và provider sẽ có logic riêng, nhưng trách nhiệm gọi strategy vẫn tương tự.

### 7.1. Dependencies cần có

Tạo một dự án Spring Boot 3.x trên Java 17 với:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (scope test)
- `spring-security-test` (scope test)

Các tệp Java đặt trong package `com.example.sessionlesson`. Không cần JDBC trong demo; `InMemoryUserDetailsManager` cung cấp user học tập. **Không dùng password hard-code trong production**.

### 7.2. Custom filter — `PartnerLoginFilter.java`

~~~java
package com.example.sessionlesson;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class PartnerLoginFilter
        extends AbstractAuthenticationProcessingFilter {

    public PartnerLoginFilter(
            org.springframework.security.authentication.AuthenticationManager manager) {
        super(new AntPathRequestMatcher("/partner-login", "POST"), manager);
    }

    @Override
    public Authentication attemptAuthentication(
            HttpServletRequest request, HttpServletResponse response)
            throws AuthenticationException, IOException {

        String username = request.getParameter("username");
        String password = request.getParameter("password");

        // Chỉ kiểm tra hình thức/cỡ đầu vào tại HTTP boundary.
        // Không tự xác nhận password trong filter.
        if (username == null || username.isBlank()
                || username.length() > 128
                || password == null || password.length() > 1024) {
            throw new BadCredentialsException("Invalid credentials");
        }

        UsernamePasswordAuthenticationToken submitted =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        return getAuthenticationManager().authenticate(submitted);
    }
}
~~~

**Giải thích:**

1. `AbstractAuthenticationProcessingFilter` chứa cơ chế gọi `SessionAuthenticationStrategy` khi `attemptAuthentication` trả về kết quả thành công, rồi mới đi tới `successfulAuthentication`. Ta không tự gọi nó hai lần.
2. `UsernamePasswordAuthenticationToken.unauthenticated(...)` tạo request token **chưa xác thực**. Không dùng constructor authenticated/token có authorities do client tự cấp.
3. Filter giới hạn input; nó **không** so password. Phần xác minh password thuộc `DaoAuthenticationProvider` trong manager.
4. Không dùng `trim()` trên password vì có thể làm thay đổi chính xác secret do user chọn. Nếu chuẩn hóa username, phải thiết kế nhất quán với kho user.
5. `AntPathRequestMatcher` được dùng để minh họa trong Spring Security 6.x; API matcher có thể bị deprecated ở phiên bản 6.x mới. Khi nâng lên bản major mới, dùng matcher/API còn được hỗ trợ, giữ nguyên ràng buộc **POST /partner-login**.
6. **Không gắn `@Component` hoặc `@Bean` cho filter này** nếu đã trực tiếp đưa nó vào `HttpSecurity`. Tránh việc Spring Boot tự đăng ký một servlet filter thứ hai ngoài security chain.

**Quan trọng:** filter tùy chỉnh không tự có `SecurityContextRepository` và `SessionAuthenticationStrategy` giống filter do configurer chuẩn dựng. Ta phải **truyền chúng vào filter qua setter** trong cấu hình chain ở dưới.

### 7.3. Full cấu hình — `SecurityConfig.java`

~~~java
package com.example.sessionlesson;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.ConcurrentSessionControlAuthenticationStrategy;
import org.springframework.security.web.authentication.session.RegisterSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.session.HttpSessionEventPublisher;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("student")
                .password(encoder.encode("local-example-only"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            SessionRegistry registry, CsrfTokenRepository csrfTokens) {

        var concurrency =
                new ConcurrentSessionControlAuthenticationStrategy(registry);
        concurrency.setMaximumSessions(1);
        concurrency.setExceptionIfMaximumExceeded(true);

        var fixation = new ChangeSessionIdAuthenticationStrategy();
        var registration =
                new RegisterSessionAuthenticationStrategy(registry);
        var csrf = new CsrfAuthenticationStrategy(csrfTokens);

        return new CompositeSessionAuthenticationStrategy(
                List.of(concurrency, fixation, registration, csrf));
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationManager manager,
            SessionAuthenticationStrategy sessionStrategy,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfTokens) throws Exception {

        // Spring Security formLogin filter và custom filter dùng cùng
        // AuthenticationManager, session policy và context repository.
        http.authenticationManager(manager);

        http
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .sessionManagement(session -> session
                .sessionAuthenticationStrategy(sessionStrategy))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/partner-login").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll());

        PartnerLoginFilter partner = new PartnerLoginFilter(manager);
        partner.setSessionAuthenticationStrategy(sessionStrategy);
        partner.setSecurityContextRepository(contextRepository);
        partner.setAuthenticationSuccessHandler(
                new SimpleUrlAuthenticationSuccessHandler("/private"));
        partner.setAuthenticationFailureHandler(
                new SimpleUrlAuthenticationFailureHandler("/login?error"));

        http.addFilterBefore(
                partner, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

### Phân tích cấu hình một cách chính xác

- `sessionAuthenticationStrategy(...)` là **cùng một instance** được đưa cho form-login chain và custom `PartnerLoginFilter`; cả hai cơ chế đăng nhập áp dụng policy tương đương.
- Thứ tự composite là **concurrency → fixation → registration → CSRF lifecycle**. Concurrency bị từ chối thì các phần sau không được coi như đã thành công.
- Trong demo, `exceptionIfMaximumExceeded=true` làm login thứ hai bị chặn. Nó không dựa vào cơ chế “cho login mới rồi expire session cũ”, vì vậy không cần tự giả định đăng ký strategy sẽ tự thêm mọi filter xử lý phiên hết hạn.
- `HttpSessionEventPublisher` giúp các sự kiện hết hạn/hủy session được phát để registry có cơ hội dọn entries; nếu không, registry dễ giữ session đã chết và người dùng bị từ chối login không đúng kỳ vọng. Trong hệ thống phân tán, cần hạ tầng theo dõi phiên phù hợp, không mặc định `SessionRegistryImpl` trong một JVM đã đủ.
- `CsrfTokenRepository` là bean riêng để csrf filter và `CsrfAuthenticationStrategy` tham chiếu **cùng chính sách lưu token**. Khi override các cấu hình session/CSRF ở ứng dụng thật, kiểm tra tránh bỏ thiếu hoặc cấu hình lặp vô tình.
- `SecurityContextRepository` được khai báo rõ ràng và dùng chung, giúp request sau nạp principal từ session. `RequestAttributeSecurityContextRepository` hỗ trợ context trong cùng request qua các dispatch, `HttpSessionSecurityContextRepository` hỗ trợ lưu qua session.
- `PartnerLoginFilter` là **object tạo bởi `new`**, không bị Boot đăng ký ngoài `FilterChainProxy`.
- `.formLogin(...defaultSuccessUrl("/private", true))` chỉ quyết định redirect sau authentication. Nó không phải strategy về số phiên hoặc fixation.
- Lớp `DaoAuthenticationProvider` có thể có thay đổi constructor/deprecation tùy phiên bản 6.x cụ thể. Mẫu dùng constructor rỗng + setter phù hợp nhiều bản Spring Security 6; nếu đang dùng bản mới hơn có API được khuyến nghị khác, cập nhật theo version đang chạy mà không thay đổi semantics.
- `local-example-only` là password học tập, không sử dụng trong bất kỳ tài khoản thực nào.

**Lưu ý về chính sách composite:** Khi Spring Security tự cấu hình form login/CSRF/concurrency, framework cũng có thể ghép các strategy tương ứng. Việc ta **đưa explicit session strategy** vào đây nhằm làm rõ cùng một policy cho custom filter, không có nghĩa nên sao chép nguyên config này vào một ứng dụng đã có nhiều chain/manager/strategy. Cần đọc cấu hình chain thực, xác minh CSRF token rotation và tránh chiến lược bị gọi hai lần bởi code tùy biến.

### 7.4. Controller — `DemoController.java`

~~~java
package com.example.sessionlesson;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/private")
    public String privateEndpoint(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

### 7.5. Main class — `SessionLessonApplication.java`

~~~java
package com.example.sessionlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLessonApplication.class, args);
    }
}
~~~

### 7.6. Diễn tiến đăng nhập thành công

~~~text
Browser có pre-login HttpSession id=S1
  |
  +-- POST /login hoặc POST /partner-login, CSRF token đúng
  |
  v
Credential được DaoAuthenticationProvider xác minh
  |
  v
CompositeSessionAuthenticationStrategy
  1. Concurrent control: user chưa có session -> cho phép
  2. Change session ID: S1 -> S2
  3. Register: principal=student, sessionId=S2
  4. CSRF lifecycle: token cũ được xử lý theo policy
  |
  v
successfulAuthentication:
  SecurityContext.authentication = authenticated student
  SecurityContextRepository.saveContext(...)
  |
  v
302 Location: /private
  |
  v
GET /private + session S2
  -> Repository load context
  -> Authentication.getName() == "student"
  -> 200, body "student"
~~~

Điểm cần quan sát ở log/test không phải giá trị ID cụ thể, mà là quan hệ **S1 khác S2** nếu phiên trước login đã tồn tại và policy đổi session ID đã được áp dụng. Khi browser cập nhật cookie `JSESSIONID` theo response, request kế tiếp sử dụng phiên tương ứng.

### 7.7. Diễn tiến khi tài khoản đã có một phiên

~~~text
Tab/thiết bị A:
  POST /login đúng -> registered session A

Thiết bị B:
  POST /partner-login đúng credential
    -> concurrency strategy thấy principal đã đạt maxSessions=1
    -> ném SessionAuthenticationException
    -> authentication failure handler
    -> không được cấp phiên đăng nhập thứ hai

Phiên A vẫn được phép hoạt động.
~~~

**Không nhầm password đúng với login hoàn toàn thành công.** `AuthenticationProvider` đã kiểm tra password đúng, nhưng strategy vẫn có thể bác một lần xác thực vì policy phiên. Đây là lý do strategy được gọi **giữa authentication result và success handler**.

## 8. Kiểm thử MockMvc: form login và custom filter

Trong dự án có `spring-security-test`, dùng `MockMvc` để chạy **Servlet SecurityFilterChain** thực thay vì chỉ gọi một method mock. Các test sau giả định chính xác các class và cấu hình ở mục 7.

Tạo `src/test/java/com/example/sessionlesson/SessionStrategyIntegrationTest.java`:

~~~java
package com.example.sessionlesson;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionStrategyIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void builtinFormLoginRotatesIdAndSavesSecurityContext()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"));

        assertNotEquals(before, session.getId());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void customFilterAlsoRotatesIdAndPersistsContext()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/partner-login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"));

        assertNotEquals(before, session.getId());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void secondSessionIsRejectedWhenLimitReached()
            throws Exception {
        MockHttpSession first = new MockHttpSession();
        MockHttpSession second = new MockHttpSession();
        String secondBefore = second.getId();

        mvc.perform(post("/login")
                    .session(first)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(authenticated().withUsername("student"));

        mvc.perform(post("/partner-login")
                    .session(second)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertEquals(secondBefore, second.getId());

        mvc.perform(get("/private").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void invalidPasswordDoesNotRotateSessionOrSaveAuthentication()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/partner-login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertEquals(before, session.getId());
    }

    @Test
    void loginWithoutCsrfIsDeniedBeforeAuthentication()
            throws Exception {
        mvc.perform(post("/partner-login")
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Vì sao cần `@DirtiesContext` ở test demo?** Registry theo dõi các phiên theo principal; nếu các test dùng chung application context, đăng nhập ở test trước có thể để lại dữ liệu registry và khiến test sau bị từ chối không ổn định. Dùng context riêng sau mỗi test ở đây nhằm ưu tiên tính độc lập, dù làm suite chạy chậm hơn. Một dự án lớn có thể thay bằng cách quản lý/dọn session fixture cẩn thận.

**Điều các assert thật sự đo:**

- `authenticated()`: Spring Security đã tạo result hợp lệ trong request.
- `assertNotEquals(before, session.getId())`: session đã có trước login đổi ID (nếu mock request/container hỗ trợ `changeSessionId()` theo cấu hình demo).
- `GET /private` trong cùng session: `SecurityContext` đã được lưu và tải lại; nếu chỉ set holder mà không save repository, kiểm thử này dễ phát hiện lỗi.
- Test hai session: strategy **từ chối login mới** theo policy; session cũ vẫn truy cập được.
- Sai password: không đi qua nhánh session authentication success; ID không bị đổi vì kết quả provider không hợp lệ.
- Thiếu CSRF: request bị chặn trước authentication; đây **không** phải một bài test xác thực session strategy.

Lưu ý MockMvc là môi trường giả lập servlet request/session. Trên deploy thực, cần test HTTP/browser với cookie `JSESSIONID`, Spring Session (nếu dùng), container và reverse proxy đang chạy. Không khẳng định test giả lập đo đủ việc domain/path/SameSite/Secure của cookie trong production.

### 8.1. Tách kiểm thử strategy khỏi HTTP filter

Ngoài test tích hợp, một bộ unit test có thể gọi trực tiếp `onAuthentication(...)` với `MockHttpServletRequest`, `MockHttpServletResponse`, `SessionRegistryImpl` và một `Authentication` đã xác thực giả lập để kiểm tra thứ tự delegate, gọi đăng ký, nhánh exception. Nhưng test trực tiếp này **không chứng minh** custom filter có thực sự gọi strategy, vì vậy không thay thế integration test.

### 8.2. Cách test strategy bị gọi đúng một lần

Khi phát triển filter đặc thù, có thể dùng test double của `SessionAuthenticationStrategy` ghi số lượt gọi; tích hợp trong custom filter và gửi POST login hợp lệ. Kỳ vọng:

~~~text
POST login credential đúng  -> onAuthentication = 1
POST login credential sai   -> onAuthentication = 0
GET /private từ session cũ -> onAuthentication = 0
~~~

Tránh vừa gọi thủ công trong `attemptAuthentication`, vừa để `AbstractAuthenticationProcessingFilter` gọi thêm lần nữa, vì số lần có thể thành 2. Nếu dùng `AuthenticationFilter` hoặc custom implementation không kế thừa `AbstractAuthenticationProcessingFilter`, cần xem API/lifecycle của **đúng filter** bạn đang dùng để xác định điểm gọi.

## 9. Ví dụ Java 17 độc lập: mô phỏng thứ tự và chặn login

Để nhìn rõ vì sao thứ tự delegate và exception quan trọng mà không phụ thuộc Spring, tạo `SessionStrategyOrderDemo.java`. Mã này **mô phỏng policy**, không tự gọi servlet session hay Spring API.

~~~java
import java.util.HashSet;
import java.util.Set;

public final class SessionStrategyOrderDemo {

    private final Set<String> activeUsers = new HashSet<>();

    boolean login(String user, boolean credentialValid) {
        if (!credentialValid) {
            System.out.println("DENIED: credentials");
            return false;
        }
        if (activeUsers.contains(user)) {
            System.out.println("DENIED: concurrent session");
            return false;
        }

        System.out.println("STEP 1: concurrency allowed");
        System.out.println("STEP 2: change session id");
        activeUsers.add(user);
        System.out.println("STEP 3: register session");
        return true;
    }

    public static void main(String[] args) {
        SessionStrategyOrderDemo policy = new SessionStrategyOrderDemo();

        System.out.println("first=" + policy.login("student", true));
        System.out.println("second=" + policy.login("student", true));
        System.out.println("bad=" + policy.login("other", false));
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac SessionStrategyOrderDemo.java
java SessionStrategyOrderDemo
~~~

Stdout **chính xác**:

~~~text
STEP 1: concurrency allowed
STEP 2: change session id
STEP 3: register session
first=true
DENIED: concurrent session
second=false
DENIED: credentials
bad=false
~~~

Chương trình mô phỏng hai sự kiện quan trọng: credential sai **không** đi đến strategy, còn credential đúng vẫn có thể bị **concurrency policy từ chối** trước khi đổi session ID hoặc đăng ký phiên. Các thông điệp `change session id` chỉ là dòng in mô phỏng, **không** tạo HTTP session thật. Để kiểm tra `HttpSession.changeSessionId()` thực tế, phải dùng Servlet/Spring Security test hoặc chạy trên server.

## 10. Nếu không kế thừa AbstractAuthenticationProcessingFilter thì sao?

Có dự án tự viết một `OncePerRequestFilter` rồi trực tiếp gọi `AuthenticationManager.authenticate(...)`. Khi đó hãy cân nhắc dùng authentication filter sẵn có thay vì tự quản toàn bộ lifecycle. Nếu vẫn cần, trình tự **mang tính mô tả** sau phải được bảo đảm:

~~~text
1. Chỉ match đúng request kích hoạt đăng nhập mới.
2. Parse input và tạo Authentication token CHƯA xác thực.
3. manager.authenticate(requestToken).
4. Nếu thành công:
     sessionStrategy.onAuthentication(authResult, request, response);
     tạo SecurityContext mới chứa authResult;
     SecurityContextHolder.setContext(context);
     SecurityContextRepository.saveContext(context, request, response);
     successHandler.onAuthenticationSuccess(...).
5. Nếu sai credential hoặc strategy từ chối:
     dọn context thuộc request;
     failureHandler.onAuthenticationFailure(...);
     KHÔNG lưu authenticated result.
6. Dọn context thích hợp khi kết thúc request/dispatch.
~~~

Đây là **thuật toán giải thích**, không phải mã có thể copy thẳng: cần xử lý `AuthenticationException`, CSRF, remember-me, events, lỗi IO, response commit, async dispatch, session fixation, session creation policy và thứ tự filter. Lựa chọn `AbstractAuthenticationProcessingFilter` giúp tránh tự làm lại nhiều logic nguy hiểm.

**Tránh lỗi thứ tự:**

~~~java
// PHẢN VÍ DỤ: sai thứ tự, không đưa vào production.
Authentication result = manager.authenticate(requestToken);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
repository.saveContext(context, request, response);
strategy.onAuthentication(result, request, response);
~~~

Nếu strategy cuối cùng từ chối vì vượt số phiên, `SecurityContext` đã được lưu **trước khi policy thông qua**. Rủi ro là trạng thái authentication mới lọt vào session hoặc response đã được chuẩn bị. Hãy gọi strategy **trước** bước lưu kết quả xác thực.

### Phân biệt việc gọi một lần với việc gọi cùng instance

Một ứng dụng có form login tích hợp và custom filter cần đồng thời bảo đảm:

1. **Cơ chế nào cần gọi?** Mỗi khi có authentication *mới*, không phải mỗi request.
2. **Gọi strategy nào?** Cả hai phải tuân theo chính sách số phiên/fixation/CSRF tương thích.
3. **Có bị gọi trùng?** Không vừa override trong filter rồi gọi thêm ở `AuthenticationSuccessHandler`.
4. **Repository nào lưu context?** Nếu các cơ chế dùng repository khác nhau mà không có chủ đích, login thành công nhưng request kế tiếp bị mất authentication.
5. **Principal được so như thế nào?** Registry cùng user phải có identity ổn định qua hai cơ chế.

## 11. Vấn đề session fixation và cookie bảo mật

Session fixation không chỉ là việc “đổi một chuỗi ngẫu nhiên”. Một policy hoàn chỉnh còn liên quan:

- HTTPS cho form login và toàn bộ traffic authenticated.
- Cookie `Secure` trên HTTPS và `HttpOnly` khi phù hợp.
- `SameSite` theo threat model và cách frontend/backend giao tiếp; không chọn giá trị chỉ để “login hoạt động” mà bỏ CSRF.
- Session timeout, logout invalidation, idle timeout và renew policy.
- Không đưa session ID trong URL hoặc log; ưu tiên cookie thay URL rewriting.
- Kiểm soát session storage, session replication, proxy stickiness khi deploy nhiều node.
- Ngăn session ID cũ tiếp tục được sử dụng sau khi đổi; test cả old cookie và new cookie ở deployment thực.

**Đổi session ID sau login không tự tạo MFA, không tự hạn chế quyền và không bảo đảm toàn bộ session bị thu hồi khi account bị disable.** Đó là các policy khác, có thể cần quản lý phiên chủ động hoặc kiểm tra trạng thái account.

### Session mới được tạo lúc nào?

Một request trước login có thể đã tạo session vì CSRF token, request cache, view state hoặc một component khác. Vì vậy “chưa đăng nhập” **không đồng nghĩa** “chưa tồn tại `HttpSession`”. Session fixation protection đặc biệt có ý nghĩa tại thời điểm nâng mức tin cậy từ anonymous sang authenticated.

Ngược lại, nếu không có session trước login và chính sách cho phép tạo session sau login, hành vi có thể tạo session mới thay vì “đổi ID cũ”; test cần phân biệt hai trường hợp. Đừng viết assert `oldId != newId` khi `oldId` chưa hề tồn tại.

## 12. Concurrent sessions: những quyết định nghiệp vụ phải làm rõ

### Từ chối phiên mới hay đá phiên cũ?

| Chính sách | Trải nghiệm | Hệ quả triển khai |
| --- | --- | --- |
| Ngăn login mới | User cần logout phiên trước hoặc chờ session hết hạn. | Strategy có thể ném `SessionAuthenticationException`; registry phải dọn khi session hủy. |
| Cho login mới, hết hạn phiên cũ | User tại thiết bị mới được vào, thiết bị trước bị ngắt ở request tiếp theo. | Cần đánh dấu session cũ và bảo đảm filter/repository xử lý expired session đúng. |
| Cho nhiều phiên | Dễ dùng nhiều thiết bị. | Cần policy number/expiry/revocation và audit riêng. |

Bài demo chọn **ngăn login mới**. Nếu nghiệp vụ yêu cầu “đăng nhập ở thiết bị mới tự đăng xuất thiết bị cũ”, không chỉ đổi một boolean rồi coi xong; phải kiểm tra filter điều khiển phiên hết hạn, logout handling và session event tracking trên các node.

### Logout, timeout và registry cleanup

`SessionRegistryImpl` theo dõi session trong bộ nhớ của một ứng dụng. Khi session timeout hoặc bị invalidate, cần có sự kiện để xoá thông tin tương ứng. `HttpSessionEventPublisher` là một cách đưa servlet session lifecycle events vào Spring Security. Trong môi trường cluster, dùng hạ tầng phù hợp như Spring Session hoặc registry chia sẻ và kiểm tra tính nhất quán; một registry in-memory ở từng node không bảo đảm giới hạn phiên trên toàn cluster.

**Cảnh báo principal:** Một số implementation custom principal so sánh bằng object identity thay vì user ID có thể gây sai quy tắc “một phiên cho một tài khoản”. Nếu custom `UserDetails`, nên định nghĩa `equals/hashCode` ổn định theo định danh có ngữ nghĩa và scope tenant phù hợp, không đưa password hash thay đổi vào equality.

### Khi authentication lại trong cùng session

Một user có thể thực hiện reauthentication/switch identity trong session hiện có. Policy có thể cần xử lý cùng session ID một cách đặc biệt, ngăn một session bị đếm nhiều lần hoặc thay đổi principal sai. Không giả định mọi form POST hợp lệ có nghĩa một phiên **mới**. Kiểm tra semantics của `SessionRegistry` và session strategy đối với tình huống re-login/step-up authentication.

## 13. Stateful và stateless không dùng cùng giả định

### Stateful form login

- Trình duyệt giữ `JSESSIONID`.
- `SecurityContextRepository` hỗ trợ lưu/khôi phục context giữa request, thường dùng HTTP session.
- Session fixation protection và concurrent session control có ý nghĩa.
- CSRF cần xem xét vì browser tự gắn cookie.
- Logout thường invalidate session và xoá context; có thể dọn token/cookie phù hợp.

### Stateless bearer token hoặc API key

- Client gửi credential/tokens trên **mỗi request**.
- Server không cần tạo session chỉ để ghi principal sau mỗi request.
- Dùng `SessionCreationPolicy.STATELESS` và repository/context strategy tương thích.
- Không dùng `ConcurrentSessionControlAuthenticationStrategy` để tăng bộ đếm mỗi khi API key được kiểm tra.
- Session fixation không áp dụng trực tiếp cho một request không tạo/duy trì HTTP session; bảo mật token bao gồm expiry, revocation, replay, signature/secret verification và audience/scope policy.

Ví dụ một mảnh cấu hình riêng cho API stateless:

~~~java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(
            org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

**Đây chỉ là mảnh cấu hình**, không đủ để thực hiện bearer authentication nếu chưa có provider/filter phù hợp, và không nên thêm thẳng vào form-login chain đang dùng session. Nếu thiết kế JWT resource server, cần `oauth2ResourceServer(...)` và decoder/validator theo chuẩn; không tự tạo principal chỉ dựa trên regex của token.

## 14. Khi nào strategy thất bại và xử lý ra sao?

`SessionAuthenticationStrategy` có thể từ chối sau khi credential đã được xác minh, ví dụ:

- Đã đạt giới hạn session và policy ngăn đăng nhập mới.
- Session state không còn phù hợp để áp dụng fixation/registration.
- Session registry backend lỗi, trạng thái không nhất quán hoặc không đáp ứng yêu cầu policy.
- Một chiến lược custom kiểm tra thêm điều kiện an ninh của phiên hiện tại.

Trong những trường hợp đó:

1. Không coi “password đúng” là đủ để trả authenticated response.
2. Không ghi một `SecurityContext` đã xác thực mới **trước** khi policy session thành công.
3. Dùng failure handler/entry point phù hợp, trả thông báo an toàn; không lộ session ID của người khác.
4. Ghi event/metric nội bộ không chứa cookie, password, token hoặc hash.
5. Xác định UX: cho user biết cần logout phiên khác, cung cấp cơ chế quản lý thiết bị hoặc phục hồi đáng tin cậy nếu nghiệp vụ cần.
6. Không chuyển exception thành `200 OK`/login success chỉ để giảm lỗi.

**Không nên tự bắt mọi exception rồi bỏ qua**:

~~~java
// PHẢN VÍ DỤ: điều này bỏ qua ràng buộc số phiên.
try {
    sessionStrategy.onAuthentication(auth, request, response);
} catch (Exception ignored) {
    successHandler.onAuthenticationSuccess(request, response, auth);
}
~~~

Nguy cơ ở đây là cơ chế bảo vệ bị fail-open. Lỗi bảo mật của strategy phải được xử lý an toàn và giám sát thích hợp.

## 15. Các lỗi phổ biến khi tích hợp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| Login tùy chỉnh đúng password nhưng request sau mất login | Custom filter chỉ đặt `SecurityContextHolder`, không lưu `SecurityContextRepository`. | Test GET bảo vệ với cùng session sau login. |
| Không đổi session ID sau custom login | Filter chưa được gắn/gọi `SessionAuthenticationStrategy`. | Test session có trước login, so ID trước/sau. |
| Form login giới hạn 1 phiên nhưng custom login không giới hạn | Hai filter dùng strategy khác nhau hoặc custom bỏ qua strategy. | Kiểm tra injection và test hai luồng chéo nhau. |
| Đăng nhập sai vẫn đổi session ID | Strategy bị gọi trước khi xác minh credential hoặc trên mọi request. | Spy số lần onAuthentication theo nhánh success/failure. |
| Registry đếm sai principal | Custom principal thiếu equality/hashCode ổn định. | Kiểm tra identity qua hai login cùng user. |
| User logout rồi vẫn bị báo đạt giới hạn | Registry chưa nhận sự kiện hủy phiên. | Kiểm tra listener `HttpSessionEventPublisher` và session store. |
| Login mới đáng ra đá phiên cũ nhưng phiên cũ vẫn dùng được | Chỉ đánh dấu registry, thiếu xử lý request phiên expired. | Kiểm tra `ConcurrentSessionFilter`/concurrency config. |
| CSRF 403 ở POST login | Không gửi CSRF token hợp lệ, test thực tế chưa đi tới auth filter. | Dùng `.with(csrf())` trong MockMvc và kiểm tra frontend. |
| Sau login token CSRF cũ hoạt động sai kỳ vọng | Composite custom bỏ `CsrfAuthenticationStrategy` hoặc repository không khớp. | Test token lifecycle qua đăng nhập. |
| Session ID thay liên tục trên mọi GET | Gọi strategy ở mỗi request thay vì mỗi lần authenticate. | Test one-time invocation, kiểm tra filter placement. |
| Chạy stateless nhưng thấy tạo session | Component khác tạo session, request cache hoặc form login còn bật, repository không phù hợp. | Profile session creation và chain matchers. |
| Ở 2 node giới hạn số phiên không đúng | `SessionRegistryImpl` chỉ theo dõi trong một JVM. | Dùng session backend/registry shared và test cluster. |
| Một filter chạy 2 lần trong request | Vừa thêm filter vào security chain vừa để Boot auto-register servlet filter bean. | Tránh `@Component` cho filter custom đã thêm bằng `addFilterBefore`. |
| Role đúng nhưng vào trang protected vẫn 403 | Session persistence có, nhưng authorization policy không cấp quyền. | Phân biệt authenticated principal và GrantedAuthority. |

## 16. Checklist cho code review và QA

- [ ] Đề bài xác định rõ đây là **Servlet stateful login** hay **stateless token request**.
- [ ] Có một nơi phù hợp gọi `SessionAuthenticationStrategy` khi authentication mới thành công.
- [ ] Không gọi strategy trước credential verification, không gọi lại mỗi request, không gọi trùng trong success handler.
- [ ] Composite strategy có thứ tự **concurrency → fixation → registration**; CSRF lifecycle được xử lý theo chính sách.
- [ ] Nếu giới hạn số phiên, có `SessionRegistry` và session lifecycle events/registry implementation phù hợp.
- [ ] Chính sách rõ ràng: từ chối phiên mới hay expire phiên cũ, test đúng nhánh.
- [ ] Session ID được thay sau authentication đúng khi phiên trước login tồn tại.
- [ ] Strategy từ chối thì không lưu authenticated context hoặc tạo login success.
- [ ] Custom filter dùng cùng/ tương thích `SessionAuthenticationStrategy` và `SecurityContextRepository` với flow tích hợp.
- [ ] `SecurityContextRepository.saveContext` thực hiện ở đúng điểm cho custom mechanism.
- [ ] CSRF test vẫn có ý nghĩa; không tắt CSRF để né lỗi login form.
- [ ] Test GET protected sau POST login với cùng session, để chứng minh persistence.
- [ ] Test hai session từ browser/thiết bị khác nhau và session expiration/logout cleanup.
- [ ] SecurityContext không bị giữ sai qua thread/request/async dispatch.
- [ ] Cookie `Secure`, `HttpOnly`, `SameSite`, HTTPS, timeout và reverse proxy được cấu hình đúng threat model.
- [ ] Khi deploy nhiều node, concurrency policy không chỉ dựa vào registry cục bộ.
- [ ] Không để password, session ID, CSRF token hoặc cookie xuất hiện trong log/metrics.

## 17. Câu hỏi tự ôn tập

**Q1. `AuthenticationProvider` đã trả về authenticated result thì có chắc login thành công không?** Chưa chắc. `SessionAuthenticationStrategy` còn có thể từ chối vì policy phiên; success handler chỉ được chạy sau khi các bước bắt buộc hoàn tất.

**Q2. Khác nhau giữa `SessionAuthenticationStrategy` và `SecurityContextRepository`?** Strategy chạy quanh **sự kiện xác thực mới** để áp dụng chính sách phiên; repository **tải/lưu context** qua các request. Cần cả hai trong flow stateful phù hợp.

**Q3. Vì sao đổi session ID phải trước bước đăng ký phiên?** Để registry lưu ID cuối cùng được dùng sau login, tránh ghi ID pre-login.

**Q4. Có nên gọi `onAuthentication` mỗi lần `GET /profile` không?** Không. Một GET dùng session đã xác thực không phải một lần đăng nhập mới.

**Q5. Vì sao custom filter trong Spring Security 6 dễ quên policy phiên?** Không thể mặc nhiên dựa vào `SessionManagementFilter` gọi hộ; custom authentication mechanism phải gắn/gọi strategy tương ứng với lifecycle của nó.

**Q6. Nếu login mới phải bị từ chối khi đã có một phiên, nên chọn gì?** Concurrent session strategy với max=1 và policy `exceptionIfMaximumExceeded=true`; theo dõi session cleanup qua registry. Với configurer, `maxSessionsPreventsLogin(true)` biểu đạt mục tiêu tương ứng.

**Q7. `SessionRegistryImpl` đủ để giới hạn phiên trên mọi node của cluster không?** Không. Nó theo dõi trong bộ nhớ một JVM; cần giải pháp session/registry phân tán hoặc hạ tầng đồng bộ phù hợp.

**Q8. Đổi session ID sau đăng nhập có làm sai mật khẩu tự động đúng không?** Không. Strategy phải chạy **sau** xác thực thành công, không làm nhiệm vụ kiểm tra password.

**Q9. Với API JWT stateless có nên đăng ký một session mới mỗi request không?** Không. Stateless token validation không mang ngữ nghĩa tạo phiên web trên mỗi request; sử dụng policy token riêng.

**Q10. Test tích hợp cần nhìn những tín hiệu nào?** Login đúng/CSRF đúng, session ID sau khác trước nếu đã có session, `SecurityContext` tồn tại ở request sau, login thứ hai bị từ chối đúng policy, login sai không đổi ID và không lưu context.

**Kết luận:** `SessionAuthenticationStrategy` là điểm nối giữa **authentication vừa thành công** và **chính sách phiên HTTP**. Với các cơ chế chuẩn của Spring Security, dùng configurer để framework áp dụng đúng flow; với cơ chế tùy chỉnh, phải tích hợp strategy và context repository một cách **có chủ ý, đúng thứ tự, đúng một lần**, sau đó kiểm thử cả trạng thái session lẫn hành vi bảo mật.
