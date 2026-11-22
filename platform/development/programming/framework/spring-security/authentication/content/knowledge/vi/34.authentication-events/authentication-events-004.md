# Phân biệt sự kiện xác thực thành công với toàn bộ luồng đăng nhập hoàn tất

Trong Spring Security, việc **kiểm tra thông tin xác thực thành công** và việc **người dùng hoàn tất toàn bộ hành trình đăng nhập** là hai mốc khác nhau. Một `AuthenticationSuccessEvent` có thể đã được phát đi khi `AuthenticationManager` trả về một đối tượng `Authentication` hợp lệ, nhưng sau đó hệ thống vẫn có thể gặp lỗi khi xử lý phiên đăng nhập, ghi `SecurityContext`, thực hiện điều hướng, xác thực thêm yếu tố thứ hai, thiết lập cookie hoặc gọi tài nguyên được bảo vệ.

Vì vậy, các câu khẳng định sau **không tương đương**:

- “Password đã được `AuthenticationProvider` kiểm tra đúng.”
- “Spring Security đã phát `AuthenticationSuccessEvent`.”
- “Bộ lọc đăng nhập tương tác đã phát `InteractiveAuthenticationSuccessEvent`.”
- “`AuthenticationSuccessHandler` đã bắt đầu xử lý.”
- “HTTP response đã tạo redirect hoặc trả token cho client.”
- “Trình duyệt đã nhận cookie, theo redirect, gửi request tiếp theo và được phép truy cập tài nguyên.”
- “Người dùng đã đáp ứng đầy đủ chính sách MFA, authorization và bước khởi tạo ứng dụng.”

Bài học thuộc nhóm **Sự kiện xác thực** trong **Spring Security - authentication**, tập trung vào **ngữ nghĩa của sự kiện**, **thứ tự vòng đời Servlet form login**, **mốc nào có thể dùng để audit/metrics**, **các tình huống thành công một phần**, và **cách kiểm thử end-to-end**. Mã minh họa dùng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x (Servlet/MVC)**; những luồng JWT stateless, OAuth2/OIDC, WebFlux hoặc MFA có khác biệt cần nêu rõ.

## 1. Từ “thành công” phải luôn đi kèm *thành công ở bước nào*

Giả sử người dùng yêu cầu trang `/private`:

1. Browser chưa có phiên nên được chuyển đến trang login.
2. Người dùng gửi username/password đến `POST /login`.
3. `AuthenticationManager` kiểm tra đúng thông tin; đây là **authentication success**, nhưng chưa chắc là **login journey complete**.
4. Bộ lọc xử lý session fixation, giới hạn số session, lưu `SecurityContext`, remember-me và success handler.
5. Server trả 302, browser nhận cookie/redirect và mở lại `/private`.
6. Authorization kiểm tra quyền; controller trả 200.
7. Nếu ứng dụng yêu cầu MFA, điều khoản, lựa chọn tenant hay onboarding, các bước đó còn phải được thỏa mãn theo chính sách.

Bảng phân biệt mốc:

| Mốc | Cơ chế / tín hiệu | Điều đã biết | Điều **chưa** biết |
| --- | --- | --- | --- |
| **A — Credential verified** | `AuthenticationManager.authenticate(...)` trả `Authentication` hợp lệ; có thể xuất hiện `AuthenticationSuccessEvent` | Provider chấp nhận lần xác thực cụ thể | Session đã được lưu chưa? MFA? HTTP response? |
| **B — Web authentication prepared** | `SessionAuthenticationStrategy` và `SecurityContextRepository` được thực hiện thành công trong flow có hỗ trợ | Những bước lưu context/session của filter hiện tại đã chạy | Browser nhận cookie chưa? Handler/redirect có lỗi không? |
| **C — Interactive filter success** | `InteractiveAuthenticationSuccessEvent` trong `AbstractAuthenticationProcessingFilter` | Filter tương tác đã đi đến bước phát event | Success handler đã hoàn tất chưa? Browser đã đến trang đích chưa? |
| **D — Login response issued** | `AuthenticationSuccessHandler` thực thi redirect/response thành công | Server cố gắng chuyển khách tới bước tiếp | Client nhận/giữ cookie? Follow redirect? Đủ quyền để truy cập? |
| **E — Protected access observed** | Request tiếp theo có context hợp lệ và tài nguyên trả thành công | Người dùng/agent có quyền cho **request cụ thể này** | Không chứng minh tất cả request tương lai luôn hợp lệ |
| **F — Business login complete** | Tiêu chí do ứng dụng định nghĩa, ví dụ MFA/terms/tenant/session đã hoàn tất | Hành trình của **ứng dụng** đạt điều kiện | Không đồng nghĩa với việc mọi nghiệp vụ sau đó cũng thành công |

Không có một **`LoginCompletedEvent` phổ quát** được Spring Security tự phát cho mọi phương thức đăng nhập và mọi chính sách nghiệp vụ. Nếu hệ thống cần sự kiện “người dùng đã hoàn tất đăng nhập” cho analytics hoặc cấp quyền tính phí, hãy **định nghĩa hợp đồng nghiệp vụ và thời điểm xác nhận**; đừng đổi tên `AuthenticationSuccessEvent` thành “LOGIN_COMPLETED” rồi hiểu sai.

## 2. Hai loại sự kiện thành công trong Spring Security

### 2.1. AuthenticationSuccessEvent

`org.springframework.security.authentication.event.AuthenticationSuccessEvent` là một application event cho biết một lần authentication **thành công ở tầng AuthenticationManager/provider** khi publisher được cấu hình và đường đi đó thực sự phát sự kiện.

Các thành phần liên quan:

- `AuthenticationManager` định nghĩa thao tác `authenticate(Authentication)`.
- `ProviderManager` là implementation phổ biến, ủy quyền lần lượt cho các `AuthenticationProvider`.
- `AuthenticationEventPublisher` là hợp đồng phát event.
- `DefaultAuthenticationEventPublisher` phát `AuthenticationSuccessEvent` khi lần authenticate được chấp nhận và ánh xạ các failure exception sang sự kiện lỗi.
- `@EventListener` trong Spring nhận sự kiện để ghi audit hoặc số liệu.

Ví dụ đoạn trong một class Spring `@Configuration`:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
~~~

Các imports đúng:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
~~~

Trong một ứng dụng Spring Boot cấu hình thông thường, publisher có thể đã được tự tạo qua cơ chế auto-configuration; khai báo bean tường minh như trên giúp ví dụ rõ ràng, nhưng trước khi dùng production hãy kiểm tra bean thực tế để tránh cấu hình trùng.

**Giới hạn:** một `ProviderManager` tự tạo bằng tay nếu không gắn `AuthenticationEventPublisher` có thể dùng publisher mặc định *không phát gì*. Vì thế “không thấy event” **không chứng minh** việc xác thực thất bại; cũng như “thấy event” **không chứng minh** người dùng đã đăng nhập hoàn toàn vào browser.

Một lần gọi `AuthenticationManager.authenticate` từ service/CLI/background job có thể xác thực thành công và phát event, dù **không hề có HTTP request, cookie, SecurityContext lưu trong session hay redirect**. Ngược lại, một cơ chế khác có thể thiết lập Authentication nhưng không phát đúng loại event này vì cấu hình/publisher khác.

### 2.2. InteractiveAuthenticationSuccessEvent

`org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent` là event thuộc nhánh **đăng nhập tương tác**, được `AbstractAuthenticationProcessingFilter` phát trong `successfulAuthentication(...)`. Nó có `getGeneratedBy()` để nhận biết lớp filter sinh event.

Theo Javadoc Spring Security 6.5, sau khi filter có authentication result và thực hiện session strategy:

1. Thiết lập `Authentication` vào `SecurityContextHolder`.
2. Với security context repository được cấu hình phù hợp, lưu `SecurityContext` để có thể phục hồi ở request sau.
3. Thông báo `RememberMeServices.loginSuccess` nếu áp dụng.
4. Phát `InteractiveAuthenticationSuccessEvent`.
5. Gọi `AuthenticationSuccessHandler` thực hiện redirect hoặc HTTP response.

**Hệ quả:** khi lắng nghe `InteractiveAuthenticationSuccessEvent`, bạn **vẫn chưa thể bảo đảm** success handler gửi response thành công, người dùng nhận cookie hoặc được quyền ở trang tiếp theo. Nó chỉ là một mốc trễ hơn trong **flow của filter tương tác cụ thể** so với event của AuthenticationManager.

Quan trọng: `InteractiveAuthenticationSuccessEvent` **không kế thừa** `AuthenticationSuccessEvent`. Javadoc chủ ý để hai lớp là hai loại khác nhau, nhằm tránh event listener cho `AuthenticationSuccessEvent` nhận trùng theo inheritance. Nếu muốn nghe cả hai, đăng ký cả hai listener; **đừng cộng hai event thành hai người dùng đăng nhập**.

### 2.3. AuthenticationSuccessHandler không phải event

`org.springframework.security.web.authentication.AuthenticationSuccessHandler` là một **callback trong xử lý HTTP**, nhận `HttpServletRequest`, `HttpServletResponse` và `Authentication`. Nó thường redirect đến saved request hoặc URL mặc định.

`SavedRequestAwareAuthenticationSuccessHandler` có thể dùng `RequestCache` để về URL mà người dùng truy cập trước login. `SimpleUrlAuthenticationSuccessHandler` có thể redirect tới một URL đã cấu hình.

Sự khác biệt quan trọng:

- `AuthenticationSuccessEvent`: event của **authentication manager**, không phụ thuộc Servlet API.
- `InteractiveAuthenticationSuccessEvent`: event của **interactive filter**.
- `AuthenticationSuccessHandler`: callback **điều khiển HTTP response**; không nên xem “callback được gọi” là bằng chứng browser đã theo redirect.
- Controller của trang đích: xác nhận một request protected cụ thể đã qua authorization, không phát triển khai mặc định một event tên “login completed”.

Nếu bạn thay success handler bằng lambda mà quên gọi handler redirect mặc định, hệ thống có thể đã xác thực thành công nhưng browser không biết đi đâu; thậm chí HTTP response có thể ở trạng thái không phù hợp. Vì thế một success handler tùy chỉnh cần xử lý phần response **đúng và đầy đủ**.

## 3. Thứ tự chuẩn của form login (Servlet) trong Spring Security 6.5

Sơ đồ minh họa **một lần POST /login thông thường** qua `UsernamePasswordAuthenticationFilter` (kế thừa `AbstractAuthenticationProcessingFilter`):

~~~text
Browser                       Spring Security
   │
   ├── GET /private ──────────────► authorization yêu cầu login
   ◄── redirect /login ──────────┤
   │
   ├── POST /login + CSRF ───────► UsernamePasswordAuthenticationFilter
   │                                      │
   │                                      ▼
   │                              AuthenticationManager
   │                                      │
   │                              AuthenticationProvider
   │                                      │ password đúng
   │                                      ▼
   │                          [AuthenticationSuccessEvent]  ── A
   │                                      │
   │                                      ▼
   │                           SessionAuthenticationStrategy
   │                         (fixation, max sessions, policy)
   │                                      │ có thể thất bại
   │                                      ▼
   │                             SecurityContextHolder
   │                                      │
   │                             SecurityContextRepository
   │                                      │ save context
   │                                      ▼
   │                             RememberMeServices (nếu bật)
   │                                      │
   │                     [InteractiveAuthenticationSuccessEvent] ── C
   │                                      │
   │                                      ▼
   │                           AuthenticationSuccessHandler ── D
   ◄── 302 /private + cookie ─────────────┤
   │
   ├── GET /private + cookie ─────► context restored / authorization
   ◄── 200 page content ──────────┤                           ── E
~~~

**Ghi chú về sơ đồ:**

- `AuthenticationSuccessEvent` được phát bởi **publisher** trong nhánh `AuthenticationManager`; nếu publisher không được cấu hình, không thấy event. Đừng giả định mọi `AuthenticationProvider` tùy chỉnh đều dùng cùng publisher.
- `SessionAuthenticationStrategy` được gọi ngay sau kết quả authentication thành công ở `AbstractAuthenticationProcessingFilter` và **có thể từ chối** phiên vì chính sách. Đây là tình huống đặc biệt quan trọng: **A đã thành công nhưng C/D/E chưa xảy ra**.
- `SecurityContextHolder` là context hiện tại, **không phải** cam kết session sẽ tồn tại ở request kế tiếp. Việc lưu/đọc liên request phụ thuộc `SecurityContextRepository`, session policy, cookie và bộ lọc.
- `InteractiveAuthenticationSuccessEvent` được phát **trước** `AuthenticationSuccessHandler` của filter mặc định.
- Sau khi server gửi 302, browser có thể không lưu cookie, không theo redirect, gặp sự cố mạng hoặc bị `AccessDeniedException` ở trang đích. Do đó 302 và 200 cần quan sát riêng.
- Một application event listener mặc định thường chạy **đồng bộ** khi sử dụng publisher/multicaster mặc định, nhưng app có thể cấu hình xử lý async; không dựa vào thứ tự timestamps trong log để suy ra một thứ tự vĩnh viễn cho mọi triển khai.

### 3.1. Nếu SessionAuthenticationStrategy từ chối

Ví dụ ứng dụng giới hạn số phiên đồng thời, sử dụng session fixation protection và session strategy tùy chỉnh. `AuthenticationManager` vừa xác minh đúng username/password; `AuthenticationSuccessEvent` được phát. Nhưng `SessionAuthenticationStrategy` ném `SessionAuthenticationException`, khiến filter đi vào nhánh không thành công, hiển thị lỗi login thay vì success response.

Nên phân loại audit:

~~~text
authentication.check=ACCEPTED
login.session_policy=REJECTED
login.response=FAILURE
login.completed=false
~~~

Bốn dòng trên là **mô hình diễn giải** các mốc, không phải key Spring tự tạo. Nếu chỉ tính count `AuthenticationSuccessEvent` làm số lượt đăng nhập hoàn tất, dashboard sẽ **đếm dư** trong tình huống này.

### 3.2. Nếu success handler bị lỗi

Success handler có thể:

- Cố redirect tới URL sai hoặc URL không được phép.
- Gọi external service gây timeout hoặc ném exception.
- Ghi response hai lần.
- Quên trả 200/302 cho client.
- Dùng saved request hoặc state OAuth2 không còn phù hợp.

Khi event A và C đã xuất hiện, lỗi ở handler D vẫn có thể ngăn người dùng hoàn tất flow. Hơn nữa, **SecurityContext có thể đã được lưu** trước lỗi handler. Nếu chính sách cần rollback hay logout khi handler lỗi, phải thiết kế rõ, không kỳ vọng event sẽ tự thu hồi session.

### 3.3. Nếu người dùng không tới trang đích

HTTP 302 là **chỉ thị cho client**. Browser có thể chặn cookie, cookie không có đúng `SameSite/Secure/Domain/Path`, session repository không chia sẻ giữa replicas hoặc proxy trả lỗi 502. Một request được redirect vẫn có thể:

- Quay lại `/login` vì không phục hồi được `SecurityContext`.
- Nhận HTTP 403 vì thiếu authority.
- Nhận login challenge cho MFA/step-up.
- Nhận 404/500 từ ứng dụng sau khi đã authenticated.
- Người dùng đóng tab trước khi follow redirect.

Vì vậy nếu mục tiêu đo **đăng nhập đến trạng thái có thể sử dụng**, cần quan sát **request protected tiếp theo** hoặc một checkpoint được ứng dụng định nghĩa, không chỉ đếm event cấp provider.

## 4. Sự kiện có phải xác nhận đã đăng nhập khi gọi AuthenticationManager trực tiếp?

Không. Đây là đoạn Java **minh họa đặt trong một service đã inject `AuthenticationManager`**, không phải class độc lập:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword));
~~~

Imports liên quan là `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken` và `org.springframework.security.core.Authentication`.

Nếu provider chấp nhận, `verified.isAuthenticated()` có thể là `true` và một `AuthenticationSuccessEvent` có thể được phát. Tuy nhiên:

- Mã chưa quyết định `SecurityContextHolder` chứa authentication mới hay không.
- Không gọi `SessionAuthenticationStrategy` của một HTTP filter.
- Không lưu `SecurityContext` vào `SecurityContextRepository`.
- Không set cookie, không redirect hoặc trả access token.
- Không kiểm MFA/authorization của tài nguyên tiếp theo.

Nếu tự xây REST login controller mà chỉ gọi `authenticate(...)` rồi trả HTTP 200 “login succeeded”, bạn **chưa xây hoàn chỉnh** cơ chế đăng nhập. Trong Spring Security 6, khi tạo một `SecurityContext` thủ công và muốn phục hồi ở request sau, phải lưu thông qua `SecurityContextRepository.saveContext(context, request, response)` thích hợp; còn phải áp đúng session strategy, CSRF, cookie, session fixation và các chính sách xác thực có liên quan. Đừng copy một mẩu `SecurityContextHolder.setContext(...)` rồi xem là giải pháp đầy đủ.

## 5. Các luồng xác thực khác nhau có “completed” khác nhau

### 5.1. Form login có session

Một tiêu chí khả dụng là:

1. Người dùng hoàn thành credential/MFA theo chính sách.
2. Session/context đã được xử lý và có thể phục hồi.
3. Response login được gửi đúng.
4. Request sau mang cookie phù hợp và được `AuthorizationFilter` chấp nhận ở URL cần truy cập.

Với form login, success handler phụ trách HTTP redirect/forward. Nhưng nó không biết người dùng đã thật sự theo redirect, và một session có thể hết hạn ngay sau đó.

### 5.2. OAuth2 Login / OIDC

Có thể có nhiều mốc: chuyển hướng sang authorization server, nhận authorization code, đổi code lấy token, xác minh OIDC ID token/userinfo, tạo principal local, lưu session, redirect về URL gốc và phân quyền. Một bước **xác minh credentials tại IdP** không chứng minh ứng dụng RP đã hoàn tất callback và tạo phiên.

**Không dùng `AuthenticationSuccessEvent` của một phía như bằng chứng tự động cho toàn bộ hành trình qua nhiều hệ thống.** Các cơ chế filter/publisher khác nhau có thể phát hoặc không phát loại event tương tự; bắt buộc kiểm behavior của version và integration thực tế.

### 5.3. JWT Bearer / API stateless

Resource Server có thể **xác minh Bearer token trên từng request**, tạo `JwtAuthenticationToken` hợp lệ rồi áp authorization. Đây không phải browser login flow có session và redirect. Nếu publisher của authentication manager phát `AuthenticationSuccessEvent`, số event có thể gần **số request** được xác thực, không phải “số lần người dùng đăng nhập”.

Vì vậy:

~~~text
100 lần xác minh Bearer token thành công
       ≠ 100 lần người dùng đăng nhập mới
       ≠ 100 browser sessions
~~~

Không xây analytics “login success count” chỉ từ event này trong một API stateless. Để đo cấp token/login tại authorization server, lấy sự kiện từ đúng OAuth2 grant/authorization flow và xác minh response, không dùng mỗi sự kiện resource server kiểm token.

### 5.4. HTTP Basic, X.509, pre-authentication, remember-me

Những cơ chế này có thể tạo Authentication trên request mà **không có tương tác login form**. Một số đường đi không dùng `AbstractAuthenticationProcessingFilter`, nên **không nhận `InteractiveAuthenticationSuccessEvent` theo cách của form login**. Đừng kết luận “không có interactive event nghĩa là không authenticated”.

### 5.5. MFA và step-up

Nếu policy yêu cầu password + OTP/passkey hoặc một số điều kiện bổ sung, **chấp nhận bước password** chưa đủ. Ngay cả khi `Authentication` hiện tại có `isAuthenticated()=true`, một endpoint vẫn có thể thiếu authority/factor bắt buộc và bị chặn hoặc điều hướng đến bước tiếp theo.

Ví dụ tình huống:

~~~text
Password factor succeeded
    │
    ├─ AuthenticationSuccessEvent (tùy đường đi)
    │
    ▼
MFA challenge required
    │
    ├─ User bỏ dở                 → login business chưa hoàn tất
    ├─ OTP/passkey sai            → login business chưa hoàn tất
    └─ Factor thứ hai hợp lệ
           │
           ▼
  Policy required factors satisfied
           │
           ▼
  Authorized access to intended resource
~~~

Đừng tự suy rằng `AuthenticationSuccessEvent` bảo đảm hai yếu tố đã xong. Nếu dùng tính năng MFA của một phiên bản Spring Security mới, phải kiểm tra authorities và authorization rules của **đúng phiên bản đó**; không copy API của tài liệu 7.x vào project 6.5 nếu chưa xác minh.

## 6. Ví dụ Spring Boot 3.5 / Spring Security 6.5: nghe event và xử lý success handler

Demo Servlet sau phân biệt **ba điểm quan sát**:

- `AuthenticationSuccessEvent`: provider/manager accepted.
- `InteractiveAuthenticationSuccessEvent`: interactive filter báo thành công.
- `AuthenticationSuccessHandler`: handler bắt đầu điều hướng.

Nó **không tự ghi log “LOGIN_COMPLETED”** vì chưa quan sát được request browser sau redirect. Endpoint `/private` minh họa bước tiếp theo. Project dùng Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x và một password thử nghiệm cung cấp qua biến môi trường, không phải bí mật production.

### 6.1. Dependencies

Trong `build.gradle` (Groovy DSL) của project Spring Boot đã quản lý version bằng plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Starter Security kéo những module cần thiết cho form login, ProviderManager và auth events. Không cần OAuth2 starter cho ví dụ login bằng password.

### 6.2. Cấu hình môi trường

Tệp `src/main/resources/application.properties`:

~~~properties
# Test-only secret được người chạy cung cấp ngoài source code.
demo.password=${DEMO_PASSWORD}

# Không bật log request chứa username/password.
spring.mvc.log-request-details=false
logging.level.org.springframework.security=INFO
~~~

Ở local, cung cấp `DEMO_PASSWORD` qua cơ chế quản lý environment/IDE/secret manager phù hợp. Không để mật khẩu thật trong source, bài tập, shell history hoặc CI logs.

### 6.3. Mã Java đầy đủ

Tệp `src/main/java/example/loginstages/LoginStagesApplication.java`:

~~~java
package example.loginstages;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginStagesApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginStagesApplication.class, args);
    }
}

enum LoginMilestone {
    PROVIDER_ACCEPTED,
    INTERACTIVE_FILTER_SUCCEEDED,
    SUCCESS_HANDLER_ENTERED
}

@Component
class LoginJourneyAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoginJourneyAudit.class);

    @EventListener
    public void authenticationAccepted(AuthenticationSuccessEvent ignored) {
        record(LoginMilestone.PROVIDER_ACCEPTED);
    }

    @EventListener
    public void interactiveAccepted(
            InteractiveAuthenticationSuccessEvent ignored) {
        record(LoginMilestone.INTERACTIVE_FILTER_SUCCEEDED);
    }

    void record(LoginMilestone milestone) {
        // Không log password, session ID, JWT, Authentication hoặc token.
        LOG.info("authentication_stage={}", milestone.name());
    }
}

@Configuration(proxyBeanMethods = false)
class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.password}") String rawLabPassword) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode(rawLabPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LoginJourneyAudit audit) throws Exception {

        SimpleUrlAuthenticationSuccessHandler redirect =
                new SimpleUrlAuthenticationSuccessHandler("/private");

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/private").authenticated()
                .anyRequest().permitAll());

        http.formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    audit.record(LoginMilestone.SUCCESS_HANDLER_ENTERED);
                    redirect.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .permitAll());

        // Không tắt CSRF; form login mặc định sử dụng CSRF token.
        return http.build();
    }
}

@RestController
class PrivatePage {
    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        // Endpoint này chứng minh request hiện tại đã qua authorization.
        return "private:" + authentication.getName();
    }
}
~~~

**QA API và ý nghĩa:**

1. `DefaultAuthenticationEventPublisher` nhận `ApplicationEventPublisher`, không phải một `ApplicationEventMulticaster` tự tạo. Nó phát event khi manager tương ứng gọi publisher.
2. `AuthenticationSuccessEvent` và `InteractiveAuthenticationSuccessEvent` thuộc đúng package `org.springframework.security.authentication.event`, là **hai event class khác nhau**.
3. Event listeners ghi **chỉ enum milestone**. Không log `event.getAuthentication()`, principal, credentials, request body, cookie hoặc session ID.
4. `SimpleUrlAuthenticationSuccessHandler("/private")` xử lý redirect thật; lambda wrapper chỉ thêm một điểm quan sát rồi **ủy quyền** cho handler chuẩn, không quên thực thi response.
5. `SecurityFilterChain` cho `/private` yêu cầu authenticated; các endpoint khác công khai để ví dụ đơn giản. Không dùng authorize rules mẫu này cho production có nhiều endpoint nhạy cảm.
6. `InMemoryUserDetailsManager` là tài khoản lab, password từ biến môi trường. Ứng dụng production cần account storage, MFA, rate-limit, HTTPS, session/cookie policy và auth audit có phân quyền.
7. Không tồn tại một lời gọi `audit.record(LOGIN_COMPLETED)` tại success handler: vì redirect được tạo trên server **không chứng minh browser đã đến trang đích**.

**Quy tắc về log:** Spring Security có thể xóa credentials sau authentication, nhưng điều đó không biến `Authentication` thành đối tượng “an toàn để log” trong mọi implementation. Ngay cả `toString()` của custom principal có thể chứa thông tin riêng tư.

### 6.4. Chạy và quan sát

Trong project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows dùng `gradlew.bat bootRun`. Mở trình duyệt `http://localhost:8080/private` khi chưa đăng nhập; Spring Security chuyển tới `/login`. Nhập user lab `student` và mật khẩu lab cung cấp ở `DEMO_PASSWORD`.

Với cấu hình publisher, filter và handler tương ứng, ứng dụng có thể ghi các event dạng:

~~~text
authentication_stage=PROVIDER_ACCEPTED
authentication_stage=INTERACTIVE_FILTER_SUCCEEDED
authentication_stage=SUCCESS_HANDLER_ENTERED
~~~

Ba dòng trên là **thứ tự minh họa của một luồng đồng bộ tiêu chuẩn**, không phải stdout cố định; logger có thể thêm timestamp, thread name. Nếu multicaster được cấu hình async hoặc có nhiều authentication flow, thứ tự và số lượng log cần được hiểu theo correlation ID, không suy từ vị trí dòng trong file.

Browser sau khi nhận redirect mở `/private` và nhận body:

~~~text
private:student
~~~

Nếu user đóng tab trước khi follow redirect hoặc session cookie không được gửi trong request sau, **các event ở server vẫn có thể đã xuất hiện**; body `private:student` sẽ không được nhận trong browser đó.

**Không dùng event listener để gọi trực tiếp external billing, cấp role vĩnh viễn hay đánh dấu giao dịch hoàn tất** ngay khi provider xác thực password đúng. Những hành động nghiệp vụ nhạy cảm phải phụ thuộc đúng trạng thái cuối và có idempotency/transaction theo policy.

## 7. Kiểm thử HTTP thực tế: sự kiện + redirect + phiên ở request sau

Để chứng minh các mốc, nên thử:

1. Request chưa đăng nhập không vào `/private`.
2. Gửi `POST /login` có CSRF và password đúng: provider/filter phát events và handler tạo redirect.
3. Dùng **cùng session** thực hiện một request mới đến `/private`.
4. Đảm bảo controller được truy cập với principal dự kiến; đây là **mốc quan sát sau redirect**, mạnh hơn chỉ kiểm event.
5. Thử password sai, CSRF thiếu, session bị mất và các flow MFA/authorization khác.

### 7.1. Test Spring Boot/JUnit/MockMvc với ApplicationEvents

Tệp `src/test/java/example/loginstages/LoginStagesApplicationTest.java`:

~~~java
package example.loginstages;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.password=lab-password-only-for-tests")
@AutoConfigureMockMvc
@RecordApplicationEvents
class LoginStagesApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents recordedEvents;

    @Test
    void eventsExistButNextRequestIsTheSessionProof()
            throws Exception {

        MvcResult loginResult = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "lab-password-only-for-tests"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();

        // Bằng chứng provider/manager accepted.
        assertTrue(recordedEvents.stream(AuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "student".equals(e.getAuthentication().getName())));

        // Bằng chứng interactive filter đã phát sự kiện.
        assertTrue(recordedEvents.stream(
                        InteractiveAuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "student".equals(e.getAuthentication().getName())));

        // Response redirect chỉ là một cột mốc HTTP.
        // Phải dùng cùng session ở một request khác để kiểm tiếp.
        HttpSession session = loginResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(content().string("private:student"));
    }

    @Test
    void badCredentialsDoNotCompleteLogin()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void missingCsrfDoesNotCompleteLogin()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "lab-password-only-for-tests"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy trong Gradle project:

~~~bash
./gradlew test \
  --tests example.loginstages.LoginStagesApplicationTest
~~~

Kết quả mong đợi: **3 tests pass** khi dependency và cấu hình đúng. Test đầu chứng minh **sự kiện không bị đồng nhất với redirect hoặc session**: nó kiểm từng mốc và cuối cùng truy cập protected endpoint với cùng session.

**Giới hạn của MockMvc:** đây là một test Spring HTTP filter chain với mock servlet request/response, không kiểm chứng browser thực đã lưu Cookie, SameSite/Secure settings ngoài môi trường thật, DNS, reverse proxy, distributed sessions hoặc lỗi mạng. Vì thế vẫn cần E2E browser test ở môi trường tích hợp.

### 7.2. Test bổ sung trong staging

| Test ID | Mô phỏng | Bằng chứng kỳ vọng |
| --- | --- | --- |
| L01 | Password sai | Không có successful authentication, login thất bại |
| L02 | Password đúng, CSRF thiếu | Request bị chặn trước login, không tạo phiên mới hợp lệ |
| L03 | Password đúng, session strategy từ chối vì max sessions | Có thể thấy manager success event nhưng không redirect thành công |
| L04 | Password đúng, success handler ném lỗi có kiểm soát | Event upstream có thể đã phát, client không hoàn tất login |
| L05 | Response 302, browser không nhận/lưu cookie | Request `/private` tiếp theo lại cần login |
| L06 | Response 302, browser có cookie | Request protected tiếp theo nhận Authentication phù hợp |
| L07 | User authenticated nhưng thiếu `ROLE_ADMIN` | Đăng nhập có thể thành công nhưng `/admin` trả 403 |
| L08 | Bắt buộc MFA, password đúng, chưa OTP | Không cấp quyền full-login; tiếp tục bước thứ hai |
| L09 | Bearer API nhận 100 calls cùng access token | Không báo thành 100 người dùng login mới |
| L10 | OAuth2 IdP xác thực user nhưng callback RP lỗi | Không coi RP login đã hoàn tất |
| L11 | Session repository fail hoặc cluster không chia sẻ state | User có thể login response nhưng request sau không authenticated |
| L12 | User mở nhiều tab, redirect bị bỏ dở | Có mốc server nhưng không có browser completion |
| L13 | AuthenticationManager được gọi từ background service | Có thể có AuthenticationSuccessEvent nhưng không có interactive login |
| L14 | Parent ProviderManager và child publisher cùng emit | Phát hiện duplicate events, không đếm như hai login |
| L15 | App multicaster xử lý event async | Không dựa vào log line ordering |
| L16 | Logger audit lỡ in Authentication/credentials | Bị chặn trong code review/canary test |
| L17 | Server gửi redirect tới URL không mong muốn | Không coi là journey success và ngăn open redirect |
| L18 | Login từ tài khoản đã disabled/locked | Không tạo authenticated usable session |
| L19 | MFA thành công nhưng user thiếu quyền resource | Full factor satisfaction không thay role/authorization |
| L20 | Logout/session expiry sau login | Không giả định sự kiện success xưa bảo đảm truy cập hiện tại |

**Điểm QA quan trọng:** mã HTTP và loại event phải được diễn giải theo đúng cơ chế. API bearer có thể trả 401/403, form login có thể redirect 302/303, và một ứng dụng SPA có thể trả JSON; không nên hard-code báo cáo “mọi login đúng đều trả HTTP 200 ngay tại POST /login”.

## 8. Thiết kế audit và metrics không đếm nhầm

### 8.1. Không đặt một biến loginSuccessCount từ AuthenticationSuccessEvent

Một dashboard sai thường làm:

~~~java
@EventListener
public void onSuccess(AuthenticationSuccessEvent event) {
    metrics.increment("login_completed");
}
~~~

Snippet trên **sai về ngữ nghĩa** vì event có thể là xác thực của API/token, trước session strategy hoặc do một service gọi manager trực tiếp. Không gắn tên metric “login_completed” ở đây.

Có thể phân tầng metric:

| Metric hoặc audit event | Nguồn phù hợp | Ngữ nghĩa |
| --- | --- | --- |
| `authentication_attempt_accepted` | Authentication manager publisher | Một lần xác thực được manager chấp nhận |
| `interactive_login_filter_succeeded` | Interactive filter event | Một lần filter tương tác đi tới mốc success event |
| `login_response_issued` | HTTP success handler/response observation | Server đã thực hiện response login theo contract |
| `login_session_usable` | Request protected được phục hồi context | User đã có một phiên có thể dùng cho request đó |
| `mfa_policy_satisfied` | Policy engine/MFA workflow của ứng dụng | Đã đủ yếu tố yêu cầu theo context |
| `login_journey_completed` | **Hợp đồng nghiệp vụ riêng** | Đã đạt những mốc mà sản phẩm định nghĩa là “hoàn tất” |

Tên trên là **mẫu do ứng dụng đặt**, không phải constants/events built-in của Spring Security. Cần đặt trường `stage`, `flow_id` (random, không phải session/token), `outcome` và `method` có allowlist. Hạn chế username/email và PII trong metrics để tránh cardinality, rủi ro riêng tư.

### 8.2. Correlation ID không phải session ID

Trong nhiều bước/redirect, muốn nối các event của một “login journey” cần correlation ID. Lưu ý:

- Không log raw `JSESSIONID`, access/refresh token, password, OTP, authorization code hoặc recovery code.
- Dùng một **random flow ID** do server phát hành; lưu trong session hoặc state có chữ ký/chống giả mạo nếu flow cần qua redirect.
- Không lấy nguyên giá trị `X-Request-ID` từ caller rồi xem là ID đáng tin hoặc in vào log; cần validate/normalize hoặc sinh mới.
- Một flow ID được dùng xuyên request có thể là dữ liệu liên kết hành vi, nên có retention/access policy.
- Đặt role/username/tenant trên flow phải thận trọng về rò PII; audit có thể dùng internal account ID đã phân quyền nhưng metrics công khai không nên chứa.

Nếu có Kafka/queue/event bus, mỗi sự kiện nên có `event_id` riêng để idempotency; `flow_id` dùng correlation, không dùng làm chứng minh xác thực.

### 8.3. Event không phải giao dịch exactly-once

Spring application event không tự bảo đảm:

- Bền vững khi process crash.
- Đúng một lần khi hệ thống retry hoặc có nhiều ProviderManager.
- DB transaction đã commit.
- Consumer downstream đã hoàn thành.
- Browser đã nhận response.

Nếu cần phát sự kiện “account first login completed” làm trigger cấp quyền, cân nhắc mô hình **transactional outbox** hoặc commit trạng thái nghiệp vụ trước rồi xuất sự kiện có idempotency/unique constraint. Không dùng `@Async @EventListener` rồi cho rằng nó đã có retry, durable queue và exactly-once. Mọi tác động business cần xem xét rollback/race riêng.

### 8.4. Nếu listener ném exception thì sao?

Với multicaster đồng bộ mặc định, một `@EventListener` thực hiện I/O và ném unchecked exception có thể ảnh hưởng ngay tới thread xử lý authentication. Nếu chuyển event listener sang async, tác động và ordering thay đổi nhưng độ bền/giám sát lỗi cũng phải được thiết kế. Hãy để listener nhẹ, tránh gọi external API phụ thuộc mạng ngay trên đường đăng nhập. Nếu cần audit bắt buộc, định nghĩa persistence và chính sách failure rõ ràng — không giả định listener log là transaction commit.

## 9. Sự khác nhau giữa Authentication, authorization, session và login UX

### 9.1. Authentication: bạn là ai?

`Authentication` trong Spring Security mang principal, authorities, trạng thái xác thực và tùy implementation có credentials/details. `authentication.isAuthenticated()` thể hiện trạng thái của token/authentication object **theo contract** của implementation, không có nghĩa mọi chính sách ứng dụng đã hoàn tất. Không serialize toàn bộ `Authentication` vào log hay HTTP response.

### 9.2. Authorization: bạn được làm gì?

Sau khi đăng nhập, authorization có thể trả 403 vì người dùng không có `ROLE_ADMIN` hoặc `SCOPE_X`. Việc bị 403 tại `/admin` không nhất thiết làm `AuthenticationSuccessEvent` lúc login trở thành “sai”; nó chỉ cho thấy credential được chấp nhận nhưng user không có quyền thực hiện yêu cầu này.

Ví dụ:

~~~text
Authentication success: user=student, authorities=[ROLE_USER]
GET /profile           → 200
GET /admin              → 403 (thiếu ROLE_ADMIN)
~~~

Các dòng là **mô hình**, không phải kết quả cố định mọi app. Đừng dùng boolean `isAuthenticated()` thay cho `hasRole/hasAuthority` hoặc các rule về MFA.

### 9.3. Session: trạng thái liên request

Trong Spring Security 6.x, `SecurityContextHolderFilter` đọc context từ `SecurityContextRepository`; nếu code tự xác thực ngoài filter thông thường, cần **explicit save** để context được phục hồi ở request sau. Một `SecurityContextHolder.setContext` trong thread hiện tại chưa đủ để tạo durable login state.

Nếu dùng `SessionCreationPolicy.STATELESS`, không nên giả định Spring sẽ sinh phiên cho browser. Nếu dùng `IF_REQUIRED`/default form login, repository session đúng cấu hình có thể phục hồi context. Production còn phải kiểm:

- Session fixation protection.
- Max concurrent sessions/expired sessions.
- Cookie `Secure`, `HttpOnly`, `SameSite`, Domain/Path.
- Reverse proxy HTTPS, stickiness hoặc shared session store khi nhiều replica.
- Timeout/logout/session invalidation.
- Session persistence khi context được cập nhật/đổi quyền.

### 9.4. UX: redirect và người dùng có thật sự vào trang đích?

HTTP 302 được server tạo trước khi browser gửi request tiếp theo. Một hệ thống có thể đo:

- **Login response issued**: server tạo response.
- **Navigation observed**: browser đến route sau login.
- **Protected resource served**: một endpoint trả kết quả được bảo vệ.

Cả ba đều có ý nghĩa riêng. Đối với sản phẩm SPA, response login có thể chứa JSON và client tự điều hướng, nên không thể dùng `AuthenticationSuccessHandler` ở một Spring MVC form login như bằng chứng cho luồng client-side của SPA. Thiết kế telemetry có privacy/consent phù hợp thay vì tự kéo password/cookie vào analytics.

## 10. Các cách triển khai dễ sai

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Coi `AuthenticationSuccessEvent` là “đăng nhập hoàn tất” | Event có thể xảy ra trước session strategy, response và MFA | Đặt tên metric `AUTHENTICATION_ACCEPTED`, định nghĩa completed riêng |
| Cộng `AuthenticationSuccessEvent` + `InteractiveAuthenticationSuccessEvent` | Hai event có thể đến trong cùng một login | Mỗi event là **mốc**, không phải user duy nhất |
| Coi success handler bắt đầu chạy là browser đã đăng nhập | Redirect/cookie có thể thất bại | Kiểm response và request protected tiếp theo |
| Coi 302 là HTTP login lỗi vì không phải 200 | Form login thường redirect | Test đúng theo giao thức form login và UX |
| Chỉ test `AuthenticationManager.authenticate` | Không kiểm session, filter, CSRF, redirect | Thêm MockMvc/E2E |
| Gọi `SecurityContextHolder.setContext` trong controller rồi trả 200 | Không bảo đảm save qua `SecurityContextRepository` | Dùng cơ chế chuẩn hoặc thực hiện flow persistence/session đầy đủ |
| Nhầm `isAuthenticated()` với có đủ role | User có thể thiếu authority/MFA | Áp `AuthorizationManager`/policy |
| Đếm JWT success event như lần browser login | Bearer token có thể được verify mỗi request | Theo dõi grant/login ở đúng hệ thống |
| Cho listener audit ném exception | Có thể làm login hỏng hoặc tạo kết quả từng phần | Listener nhẹ, failure policy rõ, outbox khi cần |
| In toàn `Authentication`/`SecurityContext` vào log | Có thể có credentials/session/PII | Log event enum/outcome và audit ID an toàn |
| Giả định mọi cơ chế đều phát cùng một event | Publisher/filters khác nhau | Kiểm cơ chế/version, có test thực |
| Bỏ `.with(csrf())` khỏi MockMvc POST /login | Request bị CSRF chặn trước authentication | Test có token CSRF hợp lệ |
| “Auth success” nên tự ghi DB last-login ngay | Chưa chắc login/session/required factors hoàn tất | Chọn mốc nghiệp vụ đúng, xử lý idempotency |
| Dùng event để mở URL redirect do caller chỉ định | Dễ open redirect hoặc rò context | Chỉ cho redirect an toàn, chính sách URL phù hợp |
| Coi thiếu interactive event là login thất bại | JWT/basic/pre-auth không nhất thiết dùng interactive filter | Gắn audit theo đường xác thực thực tế |

## 11. Quy trình nghiệm thu và vận hành

### 11.1. Tiêu chí nghiệm thu theo lớp

Trước khi báo một tính năng “login hoàn tất”, QA nên hỏi:

1. **Xác thực:** `AuthenticationManager/AuthenticationProvider` đã chấp nhận người dùng/credential nào?
2. **Chính sách:** MFA, account status, tenant, session limit và các điều kiện bắt buộc đã xong chưa?
3. **Context:** context đã lưu theo cơ chế đúng, có phục hồi qua request sau hay chưa?
4. **Response:** server đã tạo response/redirect/token issuance đúng hợp đồng chưa?
5. **Client:** browser có tiếp tục sử dụng cookie/token, theo redirect đúng, không bị loop?
6. **Authorization:** request protected mong đợi có được phép không?
7. **Audit:** log/metric mô tả đúng stage, không đếm event hai lần và không rò secret?
8. **Failure:** nếu một mốc sau credential success hỏng, đã có trạng thái xử lý/điều tra phù hợp chưa?

### 11.2. Checklist triển khai

- [ ] Phân biệt `AuthenticationSuccessEvent`, `InteractiveAuthenticationSuccessEvent` và `AuthenticationSuccessHandler`.
- [ ] Xác minh đã cấu hình `AuthenticationEventPublisher` nếu cần nghe manager events.
- [ ] Không dùng event ở manager để xác nhận session/MFA/redirect/client completed.
- [ ] Quan sát `SessionAuthenticationStrategy` có thể từ chối sau authentication success.
- [ ] Giữ `SecurityContextRepository` và cơ chế explicit save đúng khi tự viết flow.
- [ ] Test `POST /login` có CSRF, 302 và follow-up request với session/cookie.
- [ ] Test authorization cho tài nguyên đích, không chỉ `Authentication.isAuthenticated()`.
- [ ] Test tình huống session không phục hồi, handler lỗi, MFA bỏ dở, redirect hỏng.
- [ ] Với JWT/OAuth2/API, định nghĩa “login” theo grant/client flow chứ không theo mỗi JWT verification.
- [ ] Metric/audit có event name phân biệt stage; có correlation ID, idempotency và privacy policy.
- [ ] Không log plaintext credential, principal/Authentication đầy đủ, session ID, token hay authorization code.
- [ ] Không coi @EventListener là durable exactly-once message bus.
- [ ] Có E2E browser test/canary trong môi trường staging gần production.

### 11.3. Khi production báo “event success nhưng user vẫn thấy login page”

Lần theo thứ tự:

1. Xác minh `AuthenticationSuccessEvent` đến từ đúng endpoint và đúng flow; không phải token validation của một API khác.
2. Kiểm tra `SessionAuthenticationStrategy`, max sessions và session fixation; event manager có thể đến trước lỗi này.
3. Kiểm tra `InteractiveAuthenticationSuccessEvent` có phát hay không với filter thực tế; đừng mặc định mọi auth mechanism đều dùng filter đó.
4. Kiểm tra `AuthenticationSuccessHandler` đã được gọi và có redirect response hợp lệ chưa; có custom exception/timeout không?
5. Kiểm tra cookie session được browser nhận/gửi lại (Secure, SameSite, domain, HTTPS/proxy).
6. Kiểm tra `SecurityContextRepository`, session store/cluster, explicit save của custom flow.
7. Kiểm tra endpoint sau redirect bị 401, 403 hay 500; phân biệt authentication, authorization và business error.
8. Nếu có MFA/step-up, kiểm tra đủ factor và bước nào bị bỏ dở.
9. Rà soát correlation ID mà không in JSESSIONID/token/password.
10. Kết luận theo mốc cụ thể (“credential accepted”, “context restored”, “resource authorized”), không gán một nhãn mơ hồ “login success”.

## 12. Câu hỏi tự kiểm tra

1. `AuthenticationSuccessEvent` được phát ở tầng nào và cần cấu hình publisher ra sao?
2. Vì sao `ProviderManager.authenticate` trả authenticated không đồng nghĩa đã tạo browser session?
3. `InteractiveAuthenticationSuccessEvent` xuất hiện trước hay sau `AuthenticationSuccessHandler` ở filter mặc định?
4. `InteractiveAuthenticationSuccessEvent` có phải subclass của `AuthenticationSuccessEvent` không?
5. Nếu session strategy từ chối max sessions **sau khi password đúng**, những event/mốc nào có thể đã xuất hiện?
6. Vì sao success handler thực hiện 302 không chứng minh browser đã đến trang đích?
7. Điều gì phải kiểm tra ở request thứ hai để chứng minh SecurityContext đã được phục hồi?
8. Một Resource Server xác minh JWT 100 lần có nên tính 100 login mới không?
9. Nếu MFA bắt buộc, `isAuthenticated()=true` sau password có đủ để báo login hoàn tất không?
10. Nên đặt metric tên gì tại manager event và tại business completion?
11. Event listener chạy đồng bộ và ném exception có thể tác động thế nào đến authentication?
12. Khi cần audit bền vững và không đếm trùng, có nên dựa vào event listener không lưu state hay không?

**Đáp án gợi ý:** (1) AuthenticationManager/AuthenticationEventPublisher, ví dụ DefaultAuthenticationEventPublisher; (2) authenticate chỉ trả kết quả, không save context/response; (3) trước success handler; (4) không; (5) manager event có thể phát nhưng interactive/handler không; (6) redirect chỉ là response của server; (7) cookie/session và request protected được authorize; (8) không; (9) chưa, cần factor policy; (10) AUTHENTICATION_ACCEPTED và LOGIN_JOURNEY_COMPLETED theo hợp đồng; (11) có thể gây lỗi hoặc thay đổi flow; (12) không, cần persistence/outbox/idempotency.

## 13. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — InteractiveAuthenticationSuccessEvent API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/InteractiveAuthenticationSuccessEvent.html)
- [Spring Security 6.5 — AuthenticationSuccessEvent API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/AuthenticationSuccessEvent.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — TestContext Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
