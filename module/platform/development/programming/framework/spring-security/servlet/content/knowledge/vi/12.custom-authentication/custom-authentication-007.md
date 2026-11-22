# Lưu SecurityContext và áp dụng chiến lược phiên khi đăng nhập bằng JSON trong Spring Security Servlet

## Mục tiêu học tập

Nhiều ứng dụng Spring MVC dùng biểu mẫu POST /login với UsernamePasswordAuthenticationFilter. Khi tự viết endpoint **POST /api/login nhận JSON**, lập trình viên thường gọi AuthenticationManager.authenticate(...) và trả về HTTP 200. Điều đó **chưa đủ** để duy trì phiên đăng nhập qua các request sau.

Một đăng nhập dựa trên **HTTP session cookie** cần ít nhất ba trách nhiệm riêng:

1. Xác thực username/password: AuthenticationManager trả về Authentication đã xác thực.
2. Xử lý chiến lược phiên: SessionAuthenticationStrategy thực thi những chính sách cần thiết tại thời điểm đăng nhập, chẳng hạn đổi session ID để chống session fixation, làm mới CSRF token hoặc kiểm soát số phiên nếu có cấu hình.
3. Lưu SecurityContext: SecurityContextRepository.saveContext(...) làm cho Authentication có thể được nạp lại ở request tương lai. Đặt Authentication vào SecurityContextHolder chỉ giải quyết ngữ cảnh của request/thread hiện tại.

Bài này hướng dẫn cách phân biệt các trách nhiệm, chọn API phù hợp và triển khai một luồng JSON login có cookie-session trong **Spring Security Servlet 6.x / Spring Boot 3.x / Java 17+**.

Sau khi học, bạn có thể:

- Giải thích SecurityContextHolder, SecurityContext, Authentication và SecurityContextRepository phối hợp như thế nào.
- Nắm vì sao Spring Security 6 nhấn mạnh **explicit save** khi sử dụng SecurityContextHolderFilter.
- Dùng một custom AbstractAuthenticationProcessingFilter để nhận JSON và tận dụng lifecycle xác thực chuẩn.
- Cấu hình cùng một SecurityContextRepository cho filter đăng nhập và các request được bảo vệ.
- Gắn CompositeSessionAuthenticationStrategy với ChangeSessionIdAuthenticationStrategy và CsrfAuthenticationStrategy.
- Hiểu tác động của SessionCreationPolicy.IF_REQUIRED so với STATELESS.
- Bật CSRF cho browser sử dụng session cookie và cung cấp GET /csrf để nhận token.
- Viết ứng dụng có thể chạy và kiểm thử bằng MockMvc cho login thành công/thất bại, request tiếp theo, CSRF, logout.
- Chẩn đoán lỗi “login trả 200 nhưng request sau vẫn 401”, session fixation, session cookie, CSRF và nhiều SecurityFilterChain.

**Phạm vi:** ứng dụng Servlet có **đăng nhập bằng JSON nhưng lưu trạng thái ở HttpSession**. Nếu dùng Bearer token/JWT theo thiết kế stateless, cách tiếp cận khác và không nên gượng ép ghi SecurityContext vào session.

## 1. Authentication không đồng nghĩa một phiên đăng nhập bền vững

Giả sử browser gửi:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <token-hợp-lệ>

{"username":"learner","password":"local-pass-123"}
~~~

Giá trị CSRF chỉ là ký hiệu minh họa. Với browser dựa trên session, phải gửi token thực sự do server cấp cùng cookie liên quan.

Một đoạn mã tự viết thường có dạng:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
SecurityContextHolder.getContext().setAuthentication(verified);
return ResponseEntity.ok().build();
~~~

Đây là **đoạn minh họa chưa hoàn chỉnh**, không phải cách triển khai được khuyến nghị. Nó có thể giúp handler nhìn thấy Authentication trong luồng hiện tại, nhưng khi request kết thúc, security context thường bị dọn khỏi thread. Request sau được security filter nạp context từ SecurityContextRepository; nếu chưa có thao tác lưu phù hợp thì nó **không biết** lần đăng nhập trước thành công.

Dữ liệu đăng nhập không nên tồn tại mãi trong một biến static hoặc ThreadLocal do ứng dụng tự quản. Spring Security đã có lifecycle SecurityContext, cơ chế repository và filter xử lý các request liên tiếp.

### Phân biệt các đối tượng

| Đối tượng | Trách nhiệm |
| --- | --- |
| AuthenticationManager | Xác minh yêu cầu authentication và trả Authentication hợp lệ hoặc ném AuthenticationException |
| Authentication | Chủ thể và authorities; một đối tượng đã xác thực thường có isAuthenticated() = true |
| SecurityContext | Container chứa Authentication của một ngữ cảnh bảo mật |
| SecurityContextHolder | API truy cập context cho thread/strategy hiện hành, không phải database lưu phiên |
| SecurityContextRepository | Nạp/lưu context giữa các request, ví dụ bằng HTTP session |
| SecurityContextHolderFilter | Nạp context từ repository cho request và dọn holder; không tự bảo đảm việc lưu thay cho custom code |
| SessionAuthenticationStrategy | Áp dụng chính sách tại thời điểm authentication thành công: session fixation, CSRF, concurrency... |
| SecurityFilterChain / FilterChainProxy | Chọn tập filter phù hợp với từng HTTP request |
| HttpSession | Một cơ chế lưu trạng thái server-side có session ID thông qua cookie như JSESSIONID |

**SecurityContextRepository và SessionAuthenticationStrategy không thay thế cho nhau.** Một repository có thể lưu context nhưng không chạy chính sách session fixation. Một session strategy có thể đổi session ID nhưng không lưu Authentication cho request sau.

## 2. Luồng đầy đủ khi login bằng JSON + cookie-session

~~~text
(1) Browser lấy CSRF token:
    GET /csrf
        |
    CsrfFilter + HttpSessionCsrfTokenRepository
        |
    JSON chứa token, cookie session ban đầu nếu cần

(2) Browser gửi credentials:
    POST /api/login
    Cookie: JSESSIONID=...
    X-CSRF-TOKEN: ...
    Content-Type: application/json
        |
    FilterChainProxy chọn SecurityFilterChain
        |
    CsrfFilter xác minh token
        |
    JSON login filter match chính xác POST /api/login
        |
    AuthenticationManager.authenticate(...)
        |
        +-- lỗi -> unsuccessfulAuthentication -> 401 JSON
        |
        +-- thành công -> SessionAuthenticationStrategy.onAuthentication(...)
                         |
                   đổi session ID nếu có phiên
                   làm mới/invalidate CSRF token theo chính sách
                         |
                   tạo SecurityContext với Authentication
                         |
                   SecurityContextHolder.setContext(context)
                         |
                   SecurityContextRepository.saveContext(context,...)
                         |
                   success handler -> 200 JSON

(3) Request tiếp theo:
    GET /api/me + cookie session mới/hợp lệ
        |
    SecurityContextHolderFilter nạp context từ repository
        |
    AuthorizationFilter yêu cầu authenticated()
        |
    Controller thấy Authentication hiện hành
        |
    response 200; filter dọn holder sau request
~~~

Luồng trên là sơ đồ về **các trách nhiệm**, không cam kết mọi filter trong Spring Security 6 gọi các bước theo cùng thứ tự trong mọi cơ chế. Ví dụ của bài dựa trên AbstractAuthenticationProcessingFilter: framework gọi session strategy sau authenticate thành công và xử lý lưu context trong successfulAuthentication(...), trước khi success handler hoàn tất phản hồi.

### Nếu đăng nhập thất bại?

Không có Authentication thành công để lưu và không chạy chiến lược phiên như ở nhánh thành công. Failure handler trả thông báo chung; không đưa mật khẩu, nguyên nhân chính xác hoặc dữ liệu nhạy cảm vào response. Một lần sai password không nên tự tạo SecurityContext authenticated.

### Nếu thiếu CSRF token?

CSRF filter có thể trả 403 **trước** khi custom JSON login filter nhận request. Đây không phải BadCredentialsException và không có nghĩa AuthenticationManager đã thử mật khẩu. Dùng GET /csrf và header hợp lệ thay vì tắt CSRF một cách tùy tiện.

## 3. Bước một: tạo Authentication đã được manager xác minh

Đường đi phổ biến là UsernamePasswordAuthenticationToken.unauthenticated(...):

~~~java
UsernamePasswordAuthenticationToken requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

Authentication verified =
        authenticationManager.authenticate(requestToken);
~~~

Đây là **đoạn trích**, chưa phải controller/filter đầy đủ. Điều quan trọng là không làm:

~~~java
// Sai ý tưởng: tự đánh dấu authenticated mà chưa qua AuthenticationManager.
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                "learner", null, java.util.List.of());
~~~

Code sai ý tưởng ở trên có thể tạo một token được đánh dấu authenticated dù chưa xác minh credential; tuyệt đối không dùng nó để cấp phiên cho request không tin cậy.

AuthenticationManager (thường ProviderManager + AuthenticationProvider) xác minh mật khẩu qua PasswordEncoder/UserDetailsService hoặc một cơ chế phù hợp. Nếu thành công, đối tượng trả về có principal và authorities theo kết quả đã kiểm tra.

Chỉ sau khi có verified Authentication mới áp dụng session strategy, thiết lập SecurityContext và lưu. Với filter do Spring Security hỗ trợ sẵn, ưu tiên để framework thực hiện sequence này; đừng tự tái tạo nếu không cần.

## 4. Bước hai: SecurityContextRepository là nơi duy trì đăng nhập

### SecurityContextHolder chỉ sống theo request/thread

SecurityContextHolder thường dùng ThreadLocal. Trong Servlet, SecurityContextHolderFilter thiết lập context cho quá trình request và dọn khi kết thúc để tránh rò rỉ context giữa các thread trong pool.

Vì vậy:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

đặt Authentication vào context **hiện hành**, không có nghĩa đã ghi xuống HttpSession. Nếu không lưu, GET /api/me ở request mới có thể vẫn thấy anonymous.

### Lưu bền vững bằng saveContext(...)

SecurityContextRepository có phương thức:

~~~java
void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

Đây là chữ ký khái quát để minh họa contract, không phải một tệp nguồn hoàn chỉnh. Khi có Authentication hợp lệ và repository phù hợp:

~~~java
repository.saveContext(context, request, response);
~~~

Sau đó request tiếp theo (gửi đúng cookie) sẽ có cơ hội nạp context từ cùng repository.

Những implementation cần biết:

| Repository | Cách sử dụng |
| --- | --- |
| HttpSessionSecurityContextRepository | Lưu SecurityContext trong HTTP session, phù hợp login browser có cookie |
| RequestAttributeSecurityContextRepository | Giữ context trong thuộc tính request; hữu ích trong các servlet dispatch thuộc cùng request, **không** cung cấp đăng nhập bền qua nhiều request |
| DelegatingSecurityContextRepository | Kết hợp nhiều repository, thường là request attribute và HttpSession |
| NullSecurityContextRepository | Không lưu context bền vững; phù hợp một số luồng stateless |

Ví dụ dưới đây dùng **DelegatingSecurityContextRepository**, gồm RequestAttributeSecurityContextRepository và HttpSessionSecurityContextRepository, để cùng hỗ trợ context trong request dispatch và lưu bằng session.

### Vì sao Spring Security 6 cần quan tâm explicit save?

Trong kiến trúc Spring Security 6, SecurityContextHolderFilter thường chỉ chịu trách nhiệm **nạp** context và dọn holder, thay vì ngầm phát hiện mọi sửa đổi và tự lưu vào cuối request như một số đường đi legacy qua SecurityContextPersistenceFilter. Vì thế khi tự làm filter xác thực, bạn phải chủ động bảo đảm SecurityContextRepository.saveContext(...) được gọi đúng lúc.

Các filter xác thực chuẩn có thể tự xử lý việc lưu. Với **AbstractAuthenticationProcessingFilter**, cần thiết lập repository cho filter rồi framework sẽ lưu context tại thời điểm successfulAuthentication(...). Đừng giả định một đoạn controller chỉ gọi SecurityContextHolder.setContext(...) có thể duy trì đăng nhập giữa request.

**Quan trọng:** repository gắn vào custom login filter và repository gắn vào security context của HttpSecurity phải nhất quán. Nếu login lưu vào repo A nhưng SecurityContextHolderFilter của request sau nạp repo B thì nhận được kết quả như chưa đăng nhập.

## 5. Bước ba: SessionAuthenticationStrategy bảo vệ phiên khi login

SessionAuthenticationStrategy được gọi **khi một authentication attempt thành công**, không phải trên mọi request đã có session. Nó có thể đại diện cho một hoặc nhiều chính sách:

- **ChangeSessionIdAuthenticationStrategy:** thay session ID của phiên hiện có sau xác thực để giảm nguy cơ session fixation. Nó không thay thế chức năng lưu SecurityContext.
- **CsrfAuthenticationStrategy:** xóa token CSRF cũ sau khi authentication thành công, để client lấy token mới theo cấu hình.
- **ConcurrentSessionControlAuthenticationStrategy:** giới hạn đăng nhập đồng thời theo chính sách; cần SessionRegistry và setup đầy đủ.
- **RegisterSessionAuthenticationStrategy:** đăng ký phiên với SessionRegistry phục vụ kiểm soát session concurrency.
- **CompositeSessionAuthenticationStrategy:** thực thi chuỗi các strategy theo thứ tự rõ ràng.

Spring Security có thể cung cấp các session strategy được lắp ghép bởi configurer chuẩn. Tuy nhiên **một custom filter không mặc nhiên nhận được đầy đủ chiến lược mà bạn kỳ vọng** nếu tự tạo bằng new rồi thêm vào chain. Hãy cấu hình hoặc truyền đúng SessionAuthenticationStrategy cho custom filter.

### Chống session fixation khác việc tạo session mới

Giả sử browser đã có JSESSIONID do tải CSRF token trước khi đăng nhập. Sau login thành công, session fixation strategy có thể đổi **session ID**. Dữ liệu session hợp lệ được duy trì theo cơ chế container, trong khi client cần nhận và gửi cookie cập nhật.

Đừng lưu JSESSIONID cũ rồi tái sử dụng nó trong request sau nếu server đã đổi ID. Browser thông thường nhận cookie Set-Cookie mới; với curl hoặc HTTP client phải duy trì cookie jar.

Session fixation protection **không tự động hạn chế một tài khoản chỉ có một phiên**. Muốn concurrency control, phải gắn đúng chiến lược và SessionRegistry hoặc cơ chế session tracking tương ứng; không thể chỉ gọi changeSessionId rồi tuyên bố đã giới hạn số thiết bị.

### CSRF token nên được làm mới sau xác thực

Với ứng dụng cookie-session, chúng ta chủ động gọi CsrfAuthenticationStrategy sau khi session ID được xử lý. Điều này vô hiệu/loại bỏ token CSRF trước đó khỏi repository theo logic của strategy. Client nên gọi lại GET /csrf sau login khi cần thực hiện POST tiếp theo (ví dụ logout).

Nếu dùng Spring Security session management configurer để tự dựng chiến lược, hãy xác nhận các thành phần CSRF/session/concurrency có được ghép đầy đủ. Nếu chủ động tạo CompositeSessionAuthenticationStrategy như bài này, bạn chịu trách nhiệm cấu hình thứ tự và bổ sung các chính sách tương ứng với yêu cầu ứng dụng.

## 6. SessionCreationPolicy: cookie-session và stateless không phải một

Các chính sách phổ biến:

| Chính sách | Ý nghĩa vận hành |
| --- | --- |
| ALWAYS | Spring Security có thể chủ động tạo HttpSession |
| IF_REQUIRED | Tạo session khi cần theo cơ chế phù hợp; lựa chọn thông dụng cho form/session login |
| NEVER | Spring Security không chủ động tạo session nhưng có thể sử dụng session đã tồn tại |
| STATELESS | Spring Security không tạo hay sử dụng HttpSession để lấy SecurityContext; thiết kế thường yêu cầu xác thực mỗi request qua token/cơ chế khác |

Với đề bài **đăng nhập bằng JSON và lưu SecurityContext vào phiên**, lựa chọn ví dụ là **IF_REQUIRED**, kết hợp HttpSessionSecurityContextRepository. Nếu bạn đồng thời đặt sessionCreationPolicy(STATELESS), đặt NullSecurityContextRepository hoặc bỏ cookie giữa các request, không thể đòi hành vi “POST login xong, GET tiếp theo vẫn authenticated nhờ session”.

### JSON không đồng nghĩa JWT

“Client gửi JSON” chỉ mô tả **định dạng request body**. Nó không quyết định phiên đăng nhập là cookie-session hay Bearer token.

- JSON login + session cookie: server lưu SecurityContext/Authentication và trả cookie session; request tiếp theo gửi cookie, có CSRF protection đối với browser.
- JSON login + JWT: server thường trả access token có chữ ký; client gửi Bearer token ở những request sau; resource server xác minh lại token mà không dùng session để ghi SecurityContext.
- JSON login + opaque token: còn tùy cơ chế token store/introspection.

Bài này chỉ triển khai mô hình **session-cookie**. Không sao chép cơ chế ghi SecurityContext vào HttpSession sang kiến trúc JWT hoàn toàn stateless khi không có chủ đích rõ ràng.

## 7. Dự án thực hành đầy đủ: JSON login có phiên và CSRF

Ta tạo Spring Boot 3.3.5, Spring Security 6.x do Spring Boot quản lý, Java 17, Spring MVC và Jackson. Login chạy qua một custom filter **kế thừa AbstractAuthenticationProcessingFilter**. Chọn superclass này vì nó có sẵn luồng attemptAuthentication → session strategy → successfulAuthentication/unsuccessfulAuthentication và các success/failure handler.

Ứng dụng:

- GET /csrf công khai, cấp token CSRF để browser gửi cùng cookie.
- POST /api/login nhận JSON có username/password và header CSRF, xác thực bằng AuthenticationManager.
- GET /api/me yêu cầu đăng nhập; dựa trên SecurityContext đã lưu trong phiên.
- POST /api/logout xóa phiên và trả HTTP 204; client cần CSRF token mới sau khi đăng nhập.
- GET /api/me trước login trả 401, không redirect sang giao diện HTML.
- Không có formLogin, không bật HTTP Basic và không sử dụng JWT trong demo.

### 7.1. Cấu trúc project

~~~text
json-session-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (nếu dùng Gradle Wrapper)
  src/main/java/dev/example/jsonsession/
    JsonSessionApplication.java
    JsonLoginFilter.java
    SecurityConfig.java
    ApiController.java
  src/test/java/dev/example/jsonsession/
    JsonSessionIntegrationTest.java
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'json-session-demo'
~~~

Tệp build.gradle:

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

Ứng dụng cần một project có Gradle Wrapper tương ứng; nếu khởi tạo qua Spring Initializr, Gradle Wrapper thường được tạo. Nếu không có, dùng Gradle đã cài hoặc tạo wrapper trước. **Không chạy javac trên một file độc lập** vì ví dụ dùng class từ Spring và Jackson ở classpath do build tool quản lý.

### 7.2. Main class

Tệp src/main/java/dev/example/jsonsession/JsonSessionApplication.java:

~~~java
package dev.example.jsonsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonSessionApplication.class, args);
    }
}
~~~

### 7.3. Custom JSON login filter

Tệp src/main/java/dev/example/jsonsession/JsonLoginFilter.java:

~~~java
package dev.example.jsonsession;

import java.io.IOException;
import java.util.Locale;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class JsonLoginFilter extends AbstractAuthenticationProcessingFilter {

    private final ObjectMapper objectMapper;

    public JsonLoginFilter(AuthenticationManager manager, ObjectMapper mapper) {
        super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        this.objectMapper = mapper;
    }

    public record LoginBody(String username, String password) {
    }

    @Override
    public Authentication attemptAuthentication(
            HttpServletRequest request,
            HttpServletResponse response)
            throws AuthenticationException, IOException {

        String contentType = request.getContentType();

        if (contentType == null
                || !contentType.toLowerCase(Locale.ROOT)
                        .startsWith("application/json")) {
            throw new BadCredentialsException("Invalid login request");
        }

        LoginBody body;
        try {
            body = objectMapper.readValue(
                    request.getInputStream(), LoginBody.class);
        } catch (JsonProcessingException invalidJson) {
            throw new BadCredentialsException(
                    "Invalid login request", invalidJson);
        }

        if (body == null
                || body.username() == null
                || body.username().isBlank()
                || body.password() == null) {
            throw new BadCredentialsException("Invalid login request");
        }

        UsernamePasswordAuthenticationToken token =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        body.username(), body.password());

        return getAuthenticationManager().authenticate(token);
    }
}
~~~

Phân tích:

1. **AntPathRequestMatcher("/api/login", "POST")** bảo đảm filter chỉ xử lý POST login. Các endpoint khác đi qua chain bình thường.
2. Jackson ObjectMapper đọc body thành Java record, không cần tự parse bằng string splitting hay regex.
3. Content-Type và field bắt buộc được kiểm tra trước khi authenticate. Ví dụ quy mọi JSON/request sai định dạng vào BadCredentialsException, làm failure handler trả **401 chung**; production có thể phân tách status 400/415 bằng validation riêng nhưng không để lộ credential.
4. UsernamePasswordAuthenticationToken.unauthenticated(...) tạo token **chưa xác thực** để AuthenticationManager kiểm tra, không tự đặt authenticated=true.
5. Filter này **không** tự gán SecurityContextHolder trong attemptAuthentication; superclass sẽ chạy session strategy và lưu context ở nhánh thành công **nếu được cấu hình repository đúng**.
6. Vì JsonLoginFilter được tạo bằng new, nó không tự là một bean được container đăng ký thành Servlet Filter; nó được gắn vào SecurityFilterChain bằng HttpSecurity.addFilterBefore. Điều này tránh một kiểu lỗi đăng ký filter hai lần.

Filter đọc body trong request và không giữ username/password như mutable field dùng chung giữa các thread. Raw password chỉ có đời sống cần thiết để authenticate; không log body hoặc token.

### 7.4. SecurityConfig: ghép cả repository và session strategy

Tệp src/main/java/dev/example/jsonsession/SecurityConfig.java:

~~~java
package dev.example.jsonsession;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("local-pass-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationConfiguration authenticationConfiguration,
            ObjectMapper objectMapper) throws Exception {

        // Manager của cấu hình Spring Security dùng UserDetailsService
        // và PasswordEncoder ở trên. Tránh tự đánh dấu token authenticated.
        AuthenticationManager manager =
                authenticationConfiguration.getAuthenticationManager();

        // Một repository chung để lưu khi login và nạp lại ở request sau.
        SecurityContextRepository contextRepository =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository());

        // Cùng một CSRF repository cho CsrfFilter và chiến lược sau login.
        HttpSessionCsrfTokenRepository csrfRepository =
                new HttpSessionCsrfTokenRepository();

        // Session fixation protection và xóa token CSRF sau login.
        SessionAuthenticationStrategy sessionStrategy =
                new CompositeSessionAuthenticationStrategy(List.of(
                        new ChangeSessionIdAuthenticationStrategy(),
                        new CsrfAuthenticationStrategy(csrfRepository)));

        JsonLoginFilter jsonFilter = new JsonLoginFilter(manager, objectMapper);

        // Hai dòng cốt lõi: custom filter phải được nối cả hai cơ chế.
        jsonFilter.setSessionAuthenticationStrategy(sessionStrategy);
        jsonFilter.setSecurityContextRepository(contextRepository);

        jsonFilter.setAuthenticationSuccessHandler(
                (request, response, authentication) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                            StandardCharsets.UTF_8.name());
                    objectMapper.writeValue(
                            response.getWriter(),
                            Map.of("status", "authenticated"));
                });

        jsonFilter.setAuthenticationFailureHandler(
                (request, response, exception) -> {
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                            StandardCharsets.UTF_8.name());
                    objectMapper.writeValue(
                            response.getWriter(),
                            Map.of("error", "invalid_credentials"));
                });

        http
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .securityContext(security -> security
                        .securityContextRepository(contextRepository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .requestCache(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/login")
                        .permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(
                                (request, response, exception) ->
                                        response.sendError(
                                                HttpServletResponse.SC_UNAUTHORIZED)))
                .logout(logout -> logout
                        .logoutUrl("/api/logout")
                        .logoutSuccessHandler(
                                (request, response, authentication) ->
                                        response.setStatus(
                                                HttpServletResponse.SC_NO_CONTENT)));

        http.addFilterBefore(jsonFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
~~~

Các điểm quan trọng của cấu hình:

**(a) AuthenticationManager:** AuthenticationConfiguration.getAuthenticationManager() dùng cấu hình xác thực được Spring Security lắp ghép cho ứng dụng, ở ví dụ là UserDetailsService in-memory và PasswordEncoder. Khi tự thay AuthenticationManager hoặc AuthenticationProvider, phải đảm bảo manager mới được dùng đúng trong JsonLoginFilter.

**(b) Context repository:** cùng một instance contextRepository được truyền cho **SecurityContextHolderFilter/HttpSecurity** và **JsonLoginFilter**. Khi login thành công, AbstractAuthenticationProcessingFilter lưu kết quả thông qua repository được set; GET /api/me sau đó nạp lại qua security context config. DelegatingSecurityContextRepository hỗ trợ cả request attribute lẫn HTTP session.

**(c) Session strategy:** CompositeSessionAuthenticationStrategy chạy ChangeSessionIdAuthenticationStrategy rồi CsrfAuthenticationStrategy. Hai chính sách này là ví dụ phù hợp cho session-based JSON login; không tự có concurrent-session limit. Nếu ứng dụng bật maximumSessions hoặc SessionRegistry, phải tích hợp đúng các strategy và filter quản lý phiên tương ứng, không chỉ copy composite ngắn này.

**(d) SessionCreationPolicy.IF_REQUIRED:** cho phép tạo và dùng HttpSession khi cần. Đổi thành STATELESS đồng thời mong đợi session login là yêu cầu mâu thuẫn.

**(e) CSRF:** HttpSessionCsrfTokenRepository giữ CSRF token gắn với session. POST /api/login và POST /api/logout phải gửi token hợp lệ. CsrfAuthenticationStrategy loại bỏ token cũ sau thành công, vì vậy client cần lấy mới trước các POST tiếp theo.

**(f) Authorization:** GET /csrf và POST /api/login công khai ở tầng authorization; tất cả endpoint khác cần authentication. permitAll **không** vô hiệu hóa CsrfFilter. POST /api/login vẫn phải có CSRF token vì CSRF là filter riêng.

**(g) HTTP semantics:** 401 được trả bởi entry point khi request cần đăng nhập; POST login thất bại cũng trả 401 thông qua failure handler; CSRF thiếu token thường trả 403 do CsrfFilter; login thành công trả 200 JSON; logout thành công trả 204.

**(h) Filter order:** addFilterBefore(..., UsernamePasswordAuthenticationFilter.class) đặt JSON filter tại vị trí đã biết trong chuỗi, sau CSRF filter trong thứ tự thông dụng. Class UsernamePasswordAuthenticationFilter là mốc thứ tự được Spring Security biết đến ngay cả khi formLogin bị tắt ở chain này. Filter không chạy trong các chain khác nếu ứng dụng có nhiều SecurityFilterChain và filter chỉ gắn vào chain này.

**(i) Request cache:** demo disable requestCache vì API trả JSON 401 thay vì dựa vào saved-request redirect. Trong web app pha trộn HTML, có thể cần chiến lược khác.

**(j) Logout:** cấu hình logout URL riêng cho JSON client, trả 204 thay vì redirect. LogoutFilter xử lý logout, session invalidation và clear SecurityContext theo mặc định. Client phải cập nhật cookie và loại bỏ trạng thái đăng nhập ở UI; không dùng body chứa session ID.

### 7.5. GET /csrf và endpoint được bảo vệ

Tệp src/main/java/dev/example/jsonsession/ApiController.java:

~~~java
package dev.example.jsonsession;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken());
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

Spring MVC có thể nhận CsrfToken từ request được Spring Security gắn vào và đưa vào controller. Gọi getToken() làm token được materialize theo cơ chế deferred token của Spring Security 6. HeaderName trả về cho client tên header cần dùng; với HttpSessionCsrfTokenRepository thường là X-CSRF-TOKEN.

Trong môi trường có XorCsrfTokenRequestAttributeHandler theo mặc định, token được expose cho browser có thể được mask để chống BREACH; hãy gửi **đúng token mà endpoint trả về** qua header, không tự gửi/so sánh token raw đọc từ session nội bộ. Khi thay CSRF repository/handler, kiểm tra lại hợp đồng client-server.

Đường dẫn GET /csrf là một API công khai **có chủ đích** và gắn với session. Không trả về Authentication, JSESSIONID, password hoặc session attribute cho frontend. Đặt giới hạn lưu lượng/caching thích hợp; token không phải thông tin để ghi log.

GET /api/me chỉ cần Authentication do Spring MVC cung cấp; nếu chưa đăng nhập, request đã bị authorizeHttpRequests chặn và entry point trả 401.

### 7.6. Chạy dự án

Trong thư mục có Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell, lệnh tương đương thường là:

~~~powershell
./gradlew.bat test
./gradlew.bat bootRun
~~~

Khi Boot chạy ở localhost:8080 mặc định, có thể thử bằng trình duyệt/công cụ HTTP same-origin. Ví dụ curl cùng cookie jar ở môi trường có jq:

~~~bash
# Bước 1: lấy CSRF token và giữ cookie session ban đầu.
curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq .

# Bước 2: lấy token thành biến (cũng giữ cookie).
TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

# Bước 3: xác thực, nhận/cập nhật cookie sau login.
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -d '{"username":"learner","password":"local-pass-123"}' \
  http://localhost:8080/api/login

# Bước 4: request sau dùng cookie mới.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/me
~~~

Các lệnh ví dụ dành cho shell Bash/POSIX có jq; trên Windows PowerShell, cú pháp biến, line continuation và escape JSON khác. Cookie jar **cookies.txt chứa thông tin phiên**, phải giữ bí mật và xóa an toàn sau khi thử; không commit vào Git.

Kết quả kỳ vọng (chỉ ghi phần quan trọng, không phải toàn bộ HTTP response byte-for-byte):

~~~text
GET /csrf:
  HTTP 200, JSON có headerName và token

POST /api/login (credentials và CSRF hợp lệ):
  HTTP 200
  {"status":"authenticated"}

GET /api/me (gửi cookie phiên đã cập nhật):
  HTTP 200
  {"username":"learner"}

GET /api/me (không gửi cookie hoặc phiên không hợp lệ):
  HTTP 401
~~~

Không hardcode hoặc so sánh trực tiếp giá trị JSESSIONID; container có thể thay đổi session ID sau login, đồng thời header Set-Cookie có thuộc tính HttpOnly, Secure, SameSite hoặc Path tùy cấu hình. Cookie jar cho phép client tự duy trì ID hiện hành.

**Mật khẩu local-pass-123 chỉ dùng cho demo local**, tuyệt đối không dùng trong hệ thống production. Môi trường production cần HTTPS; giới hạn số lần thử đăng nhập và giữ thông tin phiên khỏi log/URL.

### 7.7. Đăng xuất với CSRF mới

Sau khi login thành công, CsrfAuthenticationStrategy có thể xóa token ban đầu. Client nên GET /csrf lần nữa trước khi POST /api/logout:

~~~bash
NEW_TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  -H "X-CSRF-TOKEN: $NEW_TOKEN" \
  http://localhost:8080/api/logout
~~~

Kỳ vọng logout trả 204 No Content. Request GET /api/me với phiên đã logout (nếu cookie/phiên không còn hợp lệ) trở về 401. Ứng dụng thật cần đồng bộ trạng thái phía frontend, không chỉ xóa một biến JavaScript rồi cho rằng server đã logout.

### 7.8. Kiểm thử tích hợp với MockMvc

Tệp src/test/java/dev/example/jsonsession/JsonSessionIntegrationTest.java:

~~~java
package dev.example.jsonsession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonSessionIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void csrfTokenCanBeFetchedWithoutLoggingIn() throws Exception {
        mvc.perform(get("/csrf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
                .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    void protectedEndpointRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jsonLoginPersistsAuthenticationAcrossRequests() throws Exception {
        MvcResult login = mvc.perform(
                        post("/api/login")
                                .with(csrf())
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("""
                                        {
                                          "username": "learner",
                                          "password": "local-pass-123"
                                        }
                                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("authenticated"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void invalidCredentialsDoNotAuthenticate() throws Exception {
        mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "wrong-password"
                                }
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void malformedJsonIsRejectedByFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid-json"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCsrfTokenFailsBeforeJsonAuthentication() throws Exception {
        mvc.perform(post("/api/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "local-pass-123"
                                }
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void jsonLogoutReturnsNoContent() throws Exception {
        MvcResult login = mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "local-pass-123"
                                }
                                """))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }
}
~~~

**Ý nghĩa của test chính:** nhận HTTP 200 ở POST /api/login **chưa đủ**. Test jsonLoginPersistsAuthenticationAcrossRequests lấy HttpSession của request đăng nhập rồi thực hiện **một request GET /api/me khác**; chỉ khi SecurityContext đã được lưu và nạp đúng thì controller mới trả username learner.

Test csrf() của spring-security-test mô phỏng token hợp lệ; nó không tự xác minh vòng đời token/cookie trong browser thực. Đối với frontend production, cần kiểm thử bổ sung qua trình duyệt HTTP thật, phiên trước và sau khi changeSessionId, token mới sau login, CORS và SameSite.

Nếu đổi chính sách response, matcher, CSRF handler, namespace hoặc context path, sửa test theo hợp đồng API của ứng dụng, không xóa assertion để bỏ qua lỗi.

## 8. Nếu tự viết OncePerRequestFilter hoặc controller JSON thì sao?

AbstractAuthenticationProcessingFilter giúp tránh việc tự ghép lifecycle. Nhưng một số dự án dùng custom OncePerRequestFilter, controller @PostMapping hoặc AuthenticationFilter/AuthenticationConverter. Những extension point đó có thể dùng được **nếu bạn thực hiện đầy đủ trách nhiệm**.

Sau khi manager trả Authentication đã được xác minh, logic quan trọng phải tương đương:

~~~java
// Đoạn trích trong một handler/filter đã có request/response,
// manager và sessionStrategy/repository đúng; không phải file độc lập.
Authentication authenticated =
        authenticationManager.authenticate(loginToken);

// 1. Chính sách phiên phải chạy trong nhánh authentication thành công.
sessionStrategy.onAuthentication(
        authenticated, request, response);

// 2. Tạo context mới thay vì sửa object context cũ dùng chung.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// 3. Lưu trước khi response commit để cookie/session cập nhật được.
securityContextRepository.saveContext(
        context, request, response);

// 4. Sau đó mới ghi 200 JSON; không lưu password/token vào body.
~~~

Hàm này là **mẫu trật tự trách nhiệm**, không bảo đảm thay thế toàn bộ logic của một filter authentication framework: code tự viết còn phải xử lý AuthenticationException, clear context khi lỗi, session exception, remember-me nếu bật, event, redirect hoặc response commit, bảo vệ CSRF, correlation/audit và concurrency control.

Nếu dùng @RestController tự authenticate, việc gọi sessionStrategy/repository một cách thủ công như trên có thể cần thiết. **Không nhầm việc response gửi Set-Cookie với việc SecurityContext đã được lưu:** session cookie có thể xuất hiện đơn giản vì CSRF hoặc một tính năng khác đã tạo session trước login.

### Vì sao thứ tự có ý nghĩa?

Gọi saveContext rồi mới chạy session strategy có thể tạo khó khăn về session fixation/cookie, tùy servlet container và repository. Khi dùng AbstractAuthenticationProcessingFilter, trình tự được framework xử lý một cách nhất quán. Nếu tự viết, áp dụng session strategy sau authenticate thành công rồi mới tạo/set/save SecurityContext trước khi phản hồi bị commit.

Nếu SessionAuthenticationStrategy ném SessionAuthenticationException, đây không phải nhánh thành công hoàn tất. Không tiếp tục lưu Authentication và trả 200 như đã đăng nhập. Kiểm tra session validity và trả response đúng theo policy.

### Có thể chỉ gọi request.getSession().setAttribute(...)?

Không nên tự đặt một attribute tùy ý như "username" rồi cho rằng Spring Security sẽ xác nhận user. SecurityContextHolderFilter nạp context theo contract của SecurityContextRepository, với key/quy trình cụ thể. Gọi saveContext(...) đúng repository là API phù hợp và dễ tương thích hơn.

### Có thể trả JSON chứa session ID?

Không. Session ID là bí mật đóng vai trò bearer credential trong mô hình cookie-session. Để browser/container truyền cookie qua Set-Cookie và Cookie theo HTTP, đặt HttpOnly/Secure/SameSite phù hợp; không đưa JSESSIONID vào JSON hoặc URL.

## 9. Nâng cấp session strategy khi có giới hạn phiên đồng thời

Ví dụ dùng ChangeSessionIdAuthenticationStrategy và CsrfAuthenticationStrategy, **chưa bật maximumSessions**. Nếu sản phẩm yêu cầu mỗi user chỉ có một phiên hoặc giới hạn số thiết bị, cần cơ chế concurrency control đầy đủ.

Một chiến lược lắp ghép có thể chứa:

~~~text
Authentication thành công
    |
ConcurrentSessionControlAuthenticationStrategy
    |
ChangeSessionIdAuthenticationStrategy
    |
RegisterSessionAuthenticationStrategy
    |
CsrfAuthenticationStrategy (theo cấu hình yêu cầu)
    |
SecurityContextRepository.saveContext(...)
~~~

Đây là **mô hình ý tưởng**, không phải code có thể copy nguyên để bật concurrency control. Khi sử dụng SessionRegistry, ConcurrentSessionFilter và việc theo dõi session destroyed, thứ tự/registration và cách đánh dấu expired session phải nhất quán.

- ConcurrentSessionControlAuthenticationStrategy cần SessionRegistry phù hợp để kiểm tra session đang hoạt động.
- RegisterSessionAuthenticationStrategy cần đăng ký session mới sau khi chính sách cho phép.
- ConcurrentSessionFilter có thể làm việc với thông tin phiên expired theo cấu hình concurrency.
- SessionRegistryImpl cho ứng dụng single-node khác với bài toán nhiều node. Với nhiều node, cần nền tảng session tracking phù hợp như distributed session store và chính sách nhất quán.
- Nếu custom filter không gọi strategy được cấu hình cho chain, maximumSessions trong DSL có thể **không được áp dụng vào custom JSON login** dù login form chuẩn có hành vi mong đợi.

Một hướng ít lỗi hơn khi dùng session concurrency phức tạp là đóng gói custom filter thành SecurityConfigurer, lấy chiến lược phiên đã được HttpSecurity tạo ở đúng giai đoạn configure, gắn nó vào filter, và viết test cho maximumSessions. Không lấy một shared object ở thời điểm quá sớm rồi mặc định nó đã được lắp đầy đủ.

## 10. CSRF, cookie, CORS và client SPA

### 10.1. Vì sao POST JSON với cookie vẫn phải quan tâm CSRF?

JSON không tự ngăn kẻ tấn công lạm dụng cookie phiên; browser có quy tắc gửi cookie theo origin/SameSite. Nếu cookie được gửi kèm request không mong muốn, ứng dụng dựa trên session có thể gặp CSRF, đặc biệt khi cấu hình CORS/SameSite sai hoặc có endpoint chấp nhận kiểu request dễ tạo từ trang ngoài.

Với login bằng JSON nhưng **dùng cookie để duy trì authentication**, chính sách an toàn thường giữ CSRF protection. Đoạn demo nhận X-CSRF-TOKEN qua header từ token GET /csrf. Không tắt CSRF chỉ vì frontend là SPA hoặc vì muốn gửi request dễ bằng Postman/curl.

### 10.2. Cookie cần thiết nhưng không đủ

Client phải duy trì session cookie hợp lệ và cập nhật sau session fixation protection. Trong frontend fetch cùng origin, thuộc tính credentials mặc định là same-origin; với cross-origin, cần đánh giá credentials: "include", Access-Control-Allow-Credentials và cấu hình CORS thực tế.

**Không dùng Access-Control-Allow-Origin: * với credentialed requests.** Cần whitelist origin được phép, HTTPS và xem xét SameSite/secure cookie. CORS chỉ điều khiển việc browser cho phép frontend đọc/call theo policy, không thay thế authentication, CSRF hoặc session security.

### 10.3. Session store, cluster và load balancer

HttpSession có thể lưu trên memory của một node. Nếu request login vào instance A nhưng request tiếp theo vào B mà không có shared session store hoặc sticky session phù hợp, SecurityContext không được nạp như mong đợi.

Với ứng dụng nhiều node, cần xem xét Spring Session/Redis hoặc hệ thống session distributed được vận hành phù hợp, session serialization, timeout, concurrency và thu hồi phiên. Việc Java code có saveContext(...) không giải quyết vấn đề hạ tầng session replication.

### 10.4. Token CSRF sau khi login

Trong demo, CsrfAuthenticationStrategy vô hiệu token cũ. Client có thể đăng nhập thành công với token A, nhưng cần gọi GET /csrf lấy token B trước khi gửi các POST tiếp theo. Nếu frontend giữ nguyên A, có thể gặp 403 khi logout hoặc sửa dữ liệu dù cookie phiên vẫn hợp lệ. Đây là khác biệt giữa **có authentication hợp lệ** và **request thay đổi trạng thái đã qua CSRF**.

## 11. Những lỗi phổ biến và cách sửa

### Lỗi 1: POST /api/login trả 200 nhưng GET /api/me vẫn 401

**Nguyên nhân thường gặp:** chỉ set SecurityContextHolder mà không saveContext; repository login và repository của SecurityContextHolderFilter không giống nhau; session cookie không được giữ/cập nhật; SessionCreationPolicy.STATELESS; session hết hạn hoặc lưu khác node.

**Sửa:** kiểm tra AuthenticationManager thực sự trả authenticated, saveContext chạy trước response commit, cùng repository được dùng, browser gửi cookie mới, session store có dữ liệu và GET tiếp theo đi vào chain cần thiết.

### Lỗi 2: Tự thay đổi session ID nhưng không lưu Authentication

ChangeSessionIdAuthenticationStrategy xử lý session fixation, **không lưu SecurityContext**. Bạn vẫn phải gọi repository.saveContext (hoặc để AbstractAuthenticationProcessingFilter lưu qua repository đã set).

### Lỗi 3: Chỉ lưu context, bỏ qua session strategy

Có thể trông như login thành công và duy trì được, nhưng thiếu session fixation protection hoặc CSRF rotation theo chính sách. Khi dùng filter authentication tự tạo, phải gắn strategy phù hợp và test.

### Lỗi 4: Dùng NullSecurityContextRepository hoặc STATELESS cho cookie login

NullSecurityContextRepository không lưu cho request khác. STATELESS không dùng HttpSession để nạp SecurityContext. Nếu mục tiêu là cookie-session, chọn chính sách đồng bộ. Nếu chủ đích stateless, client phải gửi token mỗi request và framework phải xác minh token trong đúng filter.

### Lỗi 5: Chưa gửi CSRF token và kết luận sai password

POST /api/login thiếu token thường bị CsrfFilter trả 403 trước khi parser/filter/manager xử lý credentials. Gọi GET /csrf, gửi Cookie và header từ response. Phân biệt status 401 (credential/authentication) và 403 (CSRF/access denied) theo nguồn gốc.

### Lỗi 6: Vừa đăng nhập xong, POST /api/logout lại trả 403

CsrfAuthenticationStrategy làm mới/xóa token sau xác thực; client phải lấy token mới trước request POST tiếp theo. Không vô hiệu tính năng này chỉ để test logout.

### Lỗi 7: Custom filter không chạy vì securityMatcher

FilterChainProxy chọn **SecurityFilterChain đầu tiên khớp** theo @Order. Nếu POST /api/login ở ngoài phạm vi chain có JsonLoginFilter, matcher trong filter dù đúng cũng không giúp. Kiểm tra cả securityMatcher của chain và request matcher của filter. Một chain fallback đủ rộng giúp bảo vệ những URL ngoài chain đặc biệt.

### Lỗi 8: Filter tạo thành @Component và thêm vào chain

Một Filter bean có thể bị Boot auto-register vào Servlet container, rồi lại được đăng ký trong Spring Security chain. Điều này làm filter chạy hai lần hoặc ở sai thứ tự. Trong demo filter được tạo qua new trong SecurityConfig và chỉ thêm vào HttpSecurity, không gắn @Component.

### Lỗi 9: Tạo SecurityContext mới nhưng quên save trước response commit

Khi response đã commit, việc ghi cookie hoặc session dữ liệu có thể gặp vấn đề tùy container/repository. Chạy đầy đủ lifecycle trong filter trước khi success handler gửi JSON/status.

### Lỗi 10: Cho rằng thành công là tự động có concurrency control

Composite ngắn gồm ChangeSessionId và CsrfAuthenticationStrategy chưa giới hạn phiên đồng thời. Cấu hình maximumSessions cần SessionRegistry/concurrent session tracking, strategy tương ứng và integration test. Không suy luận từ HTTP 200.

### Lỗi 11: Xác thực ở controller nhưng tự tạo Authentication authenticated=true

Không bỏ qua AuthenticationManager/Provider để tự cấp quyền từ request JSON. Dữ liệu username/roles do client gửi là không tin cậy. Chỉ gắn Authentication do cơ chế kiểm chứng tin cậy trả về.

### Lỗi 12: Log toàn bộ request JSON, Authorization hoặc cookie

Request login chứa password, CSRF token và cookie. Không log raw body, credential, JSESSIONID, SecurityContext đầy đủ hoặc exception message nhạy cảm. Dùng correlation ID an toàn, outcome và mã lỗi chung.

### Lỗi 13: Không xử lý phiên hết hạn hoặc logout

Authentication đã được lưu không làm session tồn tại vĩnh viễn. Khi hết hạn, browser nhận 401 và cần bắt đầu login mới. Logout cần invalidation và clear context phía server; UI cần xóa trạng thái xác thực hiển thị. Không phát lại cookie cũ như cách “khôi phục” session.

### Lỗi 14: Trả cookie phiên trong JSON hoặc URL

Đừng trả JSESSIONID, session token hoặc secret trong JSON, URL query hay localStorage. Ưu tiên cookie HttpOnly/Secure/SameSite với HTTPS, session expiry và CSRF phù hợp.

## 12. QA và kiểm thử production theo ma trận

| Trường hợp | Kỳ vọng của demo | Điều cần xác minh |
| --- | --- | --- |
| GET /csrf anonymous | 200 + token | Token thuộc đúng session/cookie |
| GET /api/me anonymous | 401 | Không rò dữ liệu người dùng |
| POST /api/login đúng JSON + CSRF | 200 JSON | AuthenticationManager thành công |
| GET /api/me ngay sau login + cookie mới | 200 username | SecurityContext đã lưu và nạp lại |
| GET /api/me sau login, không cookie | 401 | Không nhầm thread context với session |
| POST /api/login sai mật khẩu + CSRF | 401 JSON chung | Không lưu authenticated context |
| POST /api/login JSON hỏng + CSRF | 401 trong demo | Không lộ parser/stack trace |
| POST /api/login thiếu CSRF | 403 | Chặn trước bước authenticate |
| POST /api/logout + CSRF token mới | 204 | Session invalidated/context cleared |
| GET /api/me sau logout | 401 | Không sử dụng được phiên cũ |
| Existing session trước login | Session ID đổi khi phù hợp | Chống session fixation |
| Hai request đồng thời vào app | Mỗi request có context đúng | Không dùng state/thread sai |
| Chuyển qua instance server khác | Vẫn hoạt động nếu shared session | Session replication/distributed store |
| Chain /api/** và chain khác | Đúng chain chứa login filter | securityMatcher, @Order, no bypass |

Khi hệ thống mở rộng, bổ sung test stale CSRF token sau login, session timeout, concurrent login limit, revoked account, cookie SameSite/Secure/HttpOnly, CORS, reverse proxy, session fixation và persistence. Nên có bài kiểm thử cuối đến cuối trong browser để xác minh cookie được browser thực sự gửi/lưu đúng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao AuthenticationManager trả Authentication hợp lệ nhưng GET /api/me vẫn 401?

> Vì kết quả authenticate chỉ tồn tại cho attempt hiện tại. Nếu SecurityContext không được lưu vào SecurityContextRepository được request sau nạp, hoặc browser không gửi cookie đúng, request tiếp theo vẫn anonymous.

**Câu 2.** Gọi SecurityContextHolder.setContext(context) và saveContext(...) có tác dụng giống nhau không?

> Không. setContext đặt context trong thread/strategy hiện hành; saveContext ghi thông tin theo repository để request khác có thể nạp lại. Trong Spring Security 6 custom authentication thường phải lưu rõ ràng.

**Câu 3.** ChangeSessionIdAuthenticationStrategy có tự lưu SecurityContext không?

> Không. Nó giải quyết session fixation bằng thay session ID của phiên hiện có khi phù hợp. Việc lưu Authentication thuộc SecurityContextRepository.

**Câu 4.** Nếu một custom JsonLoginFilter kế thừa AbstractAuthenticationProcessingFilter, ưu điểm chính là gì?

> Nó hỗ trợ lifecycle authentication chuẩn, including attempt, xử lý lỗi/thành công, session strategy và lưu context qua repository khi được cấu hình đúng; tránh phải tự viết lại nhiều bước nhạy cảm.

**Câu 5.** Vì sao cần cùng một repository trong HttpSecurity và JsonLoginFilter?

> Vì login phải ghi vào nơi mà SecurityContextHolderFilter đọc lại cho request kế tiếp. Dùng các repository không tương thích có thể làm mất trạng thái đăng nhập.

**Câu 6.** Nếu dùng POST /api/login với Content-Type application/json, có thể bỏ CSRF không?

> Không kết luận như vậy. JSON chỉ là định dạng dữ liệu; cookie-session browser vẫn cần đánh giá CSRF. Ví dụ có CSRF protection và header X-CSRF-TOKEN.

**Câu 7.** Login đã thành công nhưng POST logout báo 403. Vì sao?

> CsrfAuthenticationStrategy có thể đã xóa token cũ sau login. Client cần gọi GET /csrf lấy token mới cùng phiên hiện tại rồi POST logout.

**Câu 8.** SessionCreationPolicy.STATELESS và HttpSessionSecurityContextRepository có phù hợp với mục tiêu lưu phiên không?

> Không. STATELESS là thiết kế không dựa vào HttpSession để duy trì SecurityContext. Muốn cookie-session nên dùng chính sách cho phép session như IF_REQUIRED.

**Câu 9.** Vì sao chỉ gửi JSON {"username":"admin","roles":["ADMIN"]} không thể tự cấp authority ADMIN?

> Vì dữ liệu client không tin cậy; authority phải được AuthenticationProvider/Manager xác minh hoặc tải từ nguồn server đáng tin.

**Câu 10.** Vì sao có thể đăng nhập tốt trên máy dev nhưng request kế tiếp ở cluster trả 401?

> Nếu session được lưu trong memory node A, request sang node B có thể không thấy session. Cần hạ tầng session phù hợp hoặc routing nhất quán, song song với việc code thực sự saveContext.

**Câu 11.** Khi nào cần thêm ConcurrentSessionControlAuthenticationStrategy?

> Khi policy yêu cầu giới hạn phiên đồng thời và ứng dụng đã có SessionRegistry, session tracking, registration/expiration đầy đủ; nó không được bật chỉ bằng việc đổi session ID.

**Câu 12.** Vì sao không dùng một biến static lưu Authentication sau POST /api/login?

> Vì mọi user/request/thread có thể dùng chung hoặc đọc sai state, dẫn tới rò rỉ danh tính và leo thang quyền. Spring Security cung cấp SecurityContextHolder theo request và repository theo phiên.

## Tổng kết

**Đăng nhập JSON có session phải hoàn thành cả xác thực, xử lý phiên và lưu ngữ cảnh.**

- AuthenticationManager chứng minh credential hợp lệ.
- SessionAuthenticationStrategy áp dụng chính sách bảo vệ phiên ở **đúng thời điểm** (chống fixation, CSRF rotation, concurrency khi được cấu hình).
- SecurityContextHolder đặt Authentication cho xử lý request hiện tại.
- SecurityContextRepository lưu context để những request về sau có thể nạp lại.
- SecurityContextHolderFilter và SecurityFilterChain đảm bảo request tiếp theo dùng đúng repository, với cookie phiên hợp lệ.

Trong Spring Security 6, custom JSON login cần đặc biệt cẩn thận vì **setContext đơn thuần không thay thế saveContext**. Ưu tiên AbstractAuthenticationProcessingFilter hoặc một filter authentication có lifecycle chuẩn để tránh thiếu bước. Nếu tự viết controller/OncePerRequestFilter, phải chủ động ghép các trách nhiệm và kiểm thử từ **POST login tới một GET bảo vệ ở request khác**.