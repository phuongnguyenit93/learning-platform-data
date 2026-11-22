# Quan sát một lượt xác thực từ đầu vào đến Authentication kết quả

> **Ngữ cảnh:** Spring Security — authentication, nhóm **Bộ máy xác thực**. Mục tiêu của bài là theo dõi **một yêu cầu cụ thể** từ credential đến `Authentication` cuối cùng, xác định thành phần nào đã kiểm tra bằng chứng, kết quả được đặt ở đâu và chuyện gì xảy ra khi credential sai. Ví dụ chính dùng Spring Boot 3.3.x / Spring Security 6.3.x (Servlet) và Java 17+. Phần mã được thiết kế để chạy trong một dự án demo riêng.

## 1. Bạn cần quan sát được điều gì?

Sau bài học, bạn sẽ:

1. Nhận diện đường đi **HTTP request → SecurityFilterChain → authentication filter → AuthenticationManager → AuthenticationProvider → kết quả Authentication → SecurityContext → authorization**.
2. Phân biệt **`Authentication` đầu vào chưa xác thực** với **`Authentication` kết quả đã được provider xác minh**.
3. Biết nên quan sát gì ở các mốc: kiểu token, cờ `isAuthenticated`, principal, authorities, loại lỗi, trạng thái context và mã HTTP; biết điều gì tuyệt đối không được log.
4. Chạy một ứng dụng Spring Boot có **provider ghi trace an toàn** và test được các kết quả HTTP 200, 401, 403.
5. Hiểu vì sao một request có thể không đi qua provider, vì sao provider thành công không có nghĩa endpoint cho phép truy cập, và vì sao `AuthenticationManager` không phải là thành phần lưu `SecurityContext`.
6. Áp dụng cùng phương pháp quan sát cho form login, JWT bearer, remember-me hoặc cấu hình nhiều `SecurityFilterChain` mà không suy đoán sai loại token.

**Câu hỏi xuyên suốt:** “Trong request này, Spring Security đã nhận **bằng chứng gì**, **ai kiểm chứng bằng chứng**, và kết quả **`Authentication` nào** thực sự được ứng dụng sử dụng?”

## 2. Phân định dữ liệu đầu vào và kết quả đáng tin

`Authentication` là một interface đảm nhiệm **hai vai trò**:

- **Đầu vào của quá trình xác thực:** chứa principal/credential do client đưa tới hoặc do filter trích từ request. Thường chưa được xác thực, `isAuthenticated() == false`.
- **Kết quả của quá trình xác thực:** được cơ chế đáng tin tạo ra sau khi kiểm bằng chứng; chứa principal đã xác minh, authorities và cờ đã xác thực. Kết quả có thể được filter đưa vào `SecurityContextHolder` để mã phía sau sử dụng.

Hai đối tượng có thể cùng lớp Java, ví dụ `UsernamePasswordAuthenticationToken`, nhưng khác **nguồn gốc, ý nghĩa và trạng thái**. Đừng vì kiểu Java giống nhau mà coi request đầu vào là kết quả tin cậy.

| Dữ liệu/thuộc tính | Đầu vào trước khi kiểm | Kết quả sau khi kiểm |
| --- | --- | --- |
| `Authentication` type | Thường `UsernamePasswordAuthenticationToken` của filter HTTP Basic/form login | Có thể vẫn là `UsernamePasswordAuthenticationToken` |
| `principal` | Thường là chuỗi username lấy từ credential | Thường là `UserDetails` do nguồn tin cậy trả về |
| `credentials` | Mật khẩu hoặc token cần được kiểm | Có thể đã bị xóa, tùy provider/manager |
| `isAuthenticated()` | Thường `false` | `true` khi provider trả kết quả thành công đáng tin |
| `authorities` | Không được tin role do client tự khai | Ánh xạ từ tài khoản hoặc token đã được xác minh |
| Quyền truy cập API | Chưa được quyết định | Vẫn phải qua authorization và kiểm tài nguyên/tenant |

**Phân biệt bốn mốc:** nhận dữ liệu ≠ xác minh bằng chứng ≠ đặt kết quả vào `SecurityContext` ≠ cấp phép thao tác. Việc nhìn thấy `isAuthenticated() == true` không tự xác nhận code của bạn đã kiểm password/JWT đúng cách; cần biết **ai tạo ra trạng thái true**.

## 3. Một luồng HTTP Basic cụ thể: từ request đến controller

Ta dùng một API Servlet đơn giản:

- `GET /api/me`: người gọi phải được xác thực.
- `GET /api/reports`: người gọi phải có authority `reports.read`.
- Hai tài khoản demo: `linh` có `reports.read` và `khach` không có authority ấy.
- HTTP Basic được bật; request mang `Authorization: Basic ...` trên HTTPS trong hệ thống thực.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant F as Spring Security FilterChain
    participant B as BasicAuthenticationFilter
    participant M as ProviderManager
    participant P as DaoAuthenticationProvider
    participant U as UserDetailsService + PasswordEncoder
    participant S as SecurityContextHolder
    participant A as Authorization + Controller
    C->>F: GET /api/me, Authorization: Basic ...
    F->>B: Đưa request qua HTTP Basic filter
    B->>B: Tạo Authentication chưa xác thực
    B->>M: authenticate(request)
    M->>P: supports(type), authenticate(request)
    P->>U: Tra UserDetails + kiểm mật khẩu
    alt Mật khẩu hợp lệ, tài khoản được phép đăng nhập
        U-->>P: Xác minh thành công
        P-->>M: Authentication đã xác thực + authorities
        M->>M: Xóa credentials khỏi kết quả nếu hỗ trợ
        M-->>B: Authentication kết quả
        B->>S: Đặt Authentication vào SecurityContext
        B->>A: Cho request tiếp tục
        A->>A: Kiểm quyền endpoint
        A-->>C: 200 hoặc 403 nếu thiếu quyền
    else Credential không hợp lệ
        U-->>P: Không khớp
        P-->>M: AuthenticationException
        M-->>B: AuthenticationException
        B-->>C: HTTP 401 thông qua AuthenticationEntryPoint
    end
~~~

### Giải thích từng checkpoint

**Checkpoint 0 — HTTP request thật.** Browser, curl hoặc một ứng dụng gửi request. Header Basic là một credential được truyền đi; chuỗi Base64 trong Basic **không phải mã hóa**, vì thế dùng HTTPS khi triển khai thực tế. Khi theo dõi, chỉ ghi “header có mặt hay không”, scheme và request ID; không in raw header hoặc mật khẩu.

**Checkpoint 1 — Chọn filter chain.** `FilterChainProxy` xét các `SecurityFilterChain` và chọn chain phù hợp. Cấu hình nhiều chain phải kiểm cả `securityMatcher`, thứ tự chain và URL; chain không khớp sẽ không chạy các filter của nó. Đây là **thứ tự filter**, khác với **thứ tự authentication provider**.

**Checkpoint 2 — Lấy credential và tạo input token.** `BasicAuthenticationFilter` nhận Basic header; tạo yêu cầu `UsernamePasswordAuthenticationToken` với username/password chưa được tin. Ở điểm này, việc nhìn thấy `principal="linh"` chỉ chứng minh client **khai** username ấy.

**Checkpoint 3 — Chuyển cho manager.** Filter gọi `AuthenticationManager.authenticate(input)`. `ProviderManager` duyệt danh sách `AuthenticationProvider` theo thứ tự; hỏi `supports(input.getClass())` rồi gọi `authenticate` trên provider hỗ trợ. Một số provider có thể trả `null`/ném lỗi; kết quả cuối phụ thuộc chính sách duyệt và ngoại lệ. Không giả định manager tự kiểm mật khẩu.

**Checkpoint 4 — Provider kiểm bằng chứng.** `DaoAuthenticationProvider` đọc `UserDetails` từ `UserDetailsService`, dùng `PasswordEncoder` so sánh password được cung cấp với hash đã lưu và kiểm trạng thái account theo cơ chế Spring Security. Chỉ provider mới có cơ sở trả kết quả thành công.

**Checkpoint 5 — Tạo Authentication kết quả.** Khi xác thực thành công, provider trả một `Authentication` có principal và authorities đáng tin. Với luồng username/password mặc định thường là `UsernamePasswordAuthenticationToken` đã xác thực; principal thường thuộc `UserDetails`. `ProviderManager` mặc định gọi `eraseCredentials()` trên kết quả nếu nó hỗ trợ `CredentialsContainer`, nên password có thể không còn đọc được ở controller.

**Checkpoint 6 — Đưa kết quả vào context.** Filter/cơ chế gọi manager nhận kết quả rồi thiết lập `SecurityContextHolder` trong ngữ cảnh request. **`ProviderManager` không tự đặt kết quả vào `SecurityContextHolder`.** Việc lưu qua nhiều request tùy `SecurityContextRepository`, session và chính sách stateless/stateful; không tự suy diễn từ một cờ true.

**Checkpoint 7 — Kiểm quyền.** `AuthorizationFilter` và/hoặc method security xác định có được gọi tài nguyên hay không. `Authentication` thành công nhưng thiếu `reports.read` vẫn có thể bị **403**. Khi request thiếu credential hợp lệ, endpoint bảo vệ bằng HTTP Basic thường trả **401**.

**Checkpoint 8 — Kết thúc request.** Context được quản lý/giải phóng theo vòng đời của filter. Không dựa vào thread-local `SecurityContextHolder` của một thread khác hoặc sau khi request đã kết thúc để phán đoán principal của request vừa chạy.

## 4. Thực hành: ứng dụng Spring Boot có trace ở ranh giới provider

Ví dụ này dùng **provider chuẩn `DaoAuthenticationProvider` để thực sự kiểm mật khẩu**, sau đó bọc nó bằng một `AuthenticationProvider` chỉ ghi các thuộc tính quan sát **không nhạy cảm**. Bản bọc **không tự xác thực**, không sửa kết quả và không tự cấp quyền; nó giúp phân biệt đầu vào, đầu ra và lỗi khi `ProviderManager` gọi provider.

Cấu trúc project:

~~~text
authentication-trace-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authtrace/
    │   ├── AuthenticationTraceApplication.java
    │   ├── SecurityConfiguration.java
    │   └── IdentityController.java
    └── test/java/example/authtrace/
        └── AuthenticationTraceTest.java
~~~

Các tài khoản và mật khẩu cố định ở đây **chỉ phục vụ học trên máy cục bộ**. Không dùng tài khoản mẫu, mật khẩu nhúng trong mã nguồn hoặc HTTP Basic không có TLS trong môi trường thật.

### 4.1. Gradle và Java 17

`settings.gradle`:

~~~groovy
rootProject.name = 'authentication-trace-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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

Spring Boot quản lý các phiên bản Spring Framework và Spring Security tương thích thông qua dependency management. Không cần ghi một phiên bản Spring Security Core khác lên dependency để tránh lệch thư viện.

### 4.2. Điểm vào chương trình

`src/main/java/example/authtrace/AuthenticationTraceApplication.java`:

~~~java
package example.authtrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationTraceApplication.class, args);
    }
}
~~~

### 4.3. Cấu hình provider thật và trace an toàn

`src/main/java/example/authtrace/SecurityConfiguration.java`:

~~~java
package example.authtrace;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demoPass!"))
                .authorities("reports.read")
                .build();

        UserDetails khach = User.withUsername("khach")
                .password(encoder.encode("demoPass!"))
                .authorities("profile.read")
                .build();

        return new InMemoryUserDetailsManager(linh, khach);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        // Provider chuẩn: tra cứu UserDetails, kiểm hash và account status.
        DaoAuthenticationProvider delegate =
                new DaoAuthenticationProvider(encoder);
        delegate.setUserDetailsService(users);

        AuthenticationProvider observingProvider =
                new AuthenticationProvider() {

            @Override
            public boolean supports(Class<?> tokenType) {
                boolean supported = delegate.supports(tokenType);
                log.info("auth.provider.supports type={} supported={}",
                        tokenType.getSimpleName(), supported);
                return supported;
            }

            @Override
            public Authentication authenticate(Authentication input)
                    throws AuthenticationException {

                // Không log principal, password, header hoặc toàn bộ token.
                log.info("auth.provider.input type={} authenticated={}",
                        input.getClass().getSimpleName(),
                        input.isAuthenticated());

                try {
                    Authentication output = delegate.authenticate(input);

                    // Provider có thể trả null để không đưa ra quyết định.
                    if (output == null) {
                        log.info("auth.provider.abstain");
                        return null;
                    }

                    log.info("auth.provider.success type={} authenticated={} authorities={}",
                            output.getClass().getSimpleName(),
                            output.isAuthenticated(),
                            output.getAuthorities().size());
                    return output;
                }
                catch (AuthenticationException failure) {
                    log.info("auth.provider.failure exception={}",
                            failure.getClass().getSimpleName());
                    throw failure;
                }
            }
        };

        // Danh sách chỉ có một provider có trace, tránh việc fallback
        // không chủ ý sang một nhà cung cấp danh tính khác.
        return new ProviderManager(List.of(observingProvider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {

        http.authenticationManager(authenticationManager)
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(requests -> requests
                    .requestMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("reports.read")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Vai trò từng đoạn:**

- `InMemoryUserDetailsManager` chứa tài khoản demo. Spring Security dùng `BCryptPasswordEncoder` để kiểm mật khẩu đưa tới, không so sánh password dạng bản rõ với nhau.
- `DaoAuthenticationProvider` chịu trách nhiệm xác thực thật; decorator `observingProvider` chỉ log **kiểu token, trạng thái, số authority và loại exception**. Nó giữ nguyên `Authentication` và exception của delegate.
- `ProviderManager` được cấu hình tường minh với một provider đã bọc. Nhờ `http.authenticationManager(authenticationManager)`, filter chain sử dụng đúng manager được tạo trong ứng dụng này.
- `httpBasic(...)` kích hoạt `BasicAuthenticationFilter` để xử lý Basic credentials.
- `SessionCreationPolicy.STATELESS` giúp demo không dựa vào `HttpSession` để nhớ một lần login trước. Với mỗi HTTP request có Basic header, quá trình xác thực lại được thực hiện. Không suy diễn mô hình này cho ứng dụng dùng form login hoặc OIDC session.
- Mọi endpoint khác bị chặn bởi `denyAll()`. Demo chỉ có các thao tác GET; nếu thêm API thay đổi dữ liệu, cần xem xét CSRF và kiến trúc client/session thay vì sao chép cấu hình một cách máy móc.

**Mấu chốt về wrapper:** Decorator không được biến một request không hợp lệ thành thành công. Nó luôn gọi `delegate.authenticate(input)`, trả nguyên kết quả hoặc ném lại nguyên `AuthenticationException`. Dùng provider tự chế chỉ để “log” rồi trả token `authenticated(...)` mà không kiểm credential sẽ làm sai mục đích bảo mật.

### 4.4. Controller đọc Authentication kết quả

`src/main/java/example/authtrace/IdentityController.java`:

~~~java
package example.authtrace;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "authenticationType",
                        authentication.getClass().getSimpleName(),
                "principalType",
                        authentication.getPrincipal().getClass().getSimpleName(),
                "authenticated", authentication.isAuthenticated(),
                "credentialsPresent",
                        authentication.getCredentials() != null,
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "REPORT_OK";
    }
}
~~~

`Authentication authentication` ở controller là **kết quả được Spring Security đưa vào request context**, sau các bước xác thực trước đó. Với HTTP Basic thành công trong demo, nó thường là `UsernamePasswordAuthenticationToken`, principal là `UserDetails` (`User`), `authenticated=true`, authority lấy từ kho tài khoản.

`credentialsPresent=false` là kết quả được kỳ vọng vì `ProviderManager` mặc định xóa credentials sau thành công nếu token hỗ trợ. **Điều này không có nghĩa credential đầu vào rỗng**: password đã có trong request trước khi provider kiểm tra.

Controller ví dụ cố tình trả một vài **metadata học tập**. Trong ứng dụng thật, không mặc định công khai class token, toàn bộ authorities hay thông tin vận hành khác cho mọi client. Chỉ trả những trường API thực sự cần.

## 5. Kiểm thử từ HTTP input đến kết quả và quyết định quyền

Dùng `MockMvc` với filter Spring Security thật để kiểm tra nhiều nhánh mà không cần mở cổng HTTP. Dữ liệu demo đã khai báo tại `SecurityConfiguration`.

`src/test/java/example/authtrace/AuthenticationTraceTest.java`:

~~~java
package example.authtrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationTraceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("linh", "not-the-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctPasswordProducesVerifiedAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("linh", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("linh"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authenticationType")
                        .value("UsernamePasswordAuthenticationToken"))
                .andExpect(jsonPath("$.principalType").value("User"))
                .andExpect(jsonPath("$.credentialsPresent").value(false))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("reports.read"));
    }

    @Test
    void verifiedUserWithoutAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("khach", "demoPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void verifiedUserWithAuthorityMayReadReport() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("linh", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT_OK"));
    }
}
~~~

**Vì sao đây là kiểm thử xác thực có giá trị?** `httpBasic(...)` gắn Basic credentials lên HTTP test request. Filter của Spring Security, manager đã khai báo, provider và password encoder đều tham gia. Nhờ vậy test không chỉ tự cài một principal giả trong `SecurityContext` để bỏ qua giai đoạn credential.

Ngược lại, `@WithMockUser` và `SecurityMockMvcRequestPostProcessors.user(...)` phù hợp cho test **authorization** độc lập nhưng không chứng minh mật khẩu đã được kiểm. Có thể dùng cả hai loại test, miễn phân biệt mục tiêu.

### 5.1. Chạy bằng Gradle

Tại thư mục project, với JDK 17+ và Gradle tương thích hoặc Gradle Wrapper:

~~~bash
gradle test
gradle bootRun
~~~

Nếu đã có wrapper, dùng `./gradlew test` và `./gradlew bootRun`. Trên Windows PowerShell dùng `.\gradlew.bat test` và `.\gradlew.bat bootRun`. Không phải tự chạy `javac` cho từng lớp Spring Boot vì Gradle quản lý classpath và phiên bản dependency.

Ở terminal khác, thử các request:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u "linh:not-the-password" http://localhost:8080/api/me
curl -i -u "linh:demoPass!" http://localhost:8080/api/me
curl -i -u "khach:demoPass!" http://localhost:8080/api/reports
curl -i -u "linh:demoPass!" http://localhost:8080/api/reports
~~~

Mật khẩu ở các lệnh trên là **credential demo công khai cho localhost**. Trong hệ thống thật, không đặt secret thật trong command line, terminal history, log, chat hoặc tài liệu; dùng công cụ có cơ chế nhập/lưu secret an toàn và TLS.

### 5.2. Điều gì xuất hiện trên HTTP?

| Request | Provider có thể được gọi? | Kết quả xác thực | HTTP mong đợi |
| --- | --- | --- | --- |
| `GET /api/me`, không Basic header | Thường không, vì thiếu input Basic credentials | Không có user authenticated hợp lệ cho endpoint | **401 Unauthorized** |
| `GET /api/me`, Linh + password sai | Có; provider kiểm và ném `BadCredentialsException` | Không tạo kết quả xác thực thành công | **401 Unauthorized** |
| `GET /api/me`, Linh + password đúng | Có; provider xác thực thành công | `Authentication` có name `linh`, `authenticated=true`, authority `reports.read` | **200 OK** |
| `GET /api/reports`, Khách + password đúng | Có; provider xác thực thành công | Đã xác thực nhưng chỉ có `profile.read` | **403 Forbidden** |
| `GET /api/reports`, Linh + password đúng | Có; provider xác thực thành công | Có `reports.read` | **200 OK**, body `REPORT_OK` |

Với request Linh hợp lệ ở `/api/me`, body JSON có **các giá trị sau**; thứ tự field do JSON serializer quyết định, không nhất thiết giống thứ tự trình bày:

~~~json
{
  "name": "linh",
  "authenticationType": "UsernamePasswordAuthenticationToken",
  "principalType": "User",
  "authenticated": true,
  "credentialsPresent": false,
  "authorities": ["reports.read"]
}
~~~

Đây là output từ **`Authentication` kết quả** ở controller. Input ban đầu của Basic filter có thể có mật khẩu nhưng không đáng tin; nội dung credential đã được kiểm bởi provider trước khi hệ thống đưa result vào context.

### 5.3. Trace an toàn tại provider trông ra sao?

Decorator dùng `Logger.info` nên có thể thấy các dòng có ý nghĩa như sau (bỏ timestamp/thread/logger prefix vì chúng thay đổi theo môi trường):

~~~text
auth.provider.supports type=UsernamePasswordAuthenticationToken supported=true
auth.provider.input type=UsernamePasswordAuthenticationToken authenticated=false
auth.provider.success type=UsernamePasswordAuthenticationToken authenticated=true authorities=1
~~~

Trường hợp password sai, phần cuối sẽ thay bằng:

~~~text
auth.provider.failure exception=BadCredentialsException
~~~

**Lưu ý chính xác:** Đây là **các dòng tiêu biểu** rút từ một lượt request, không phải bản ghi toàn bộ startup log và không hứa số lần log cố định khi nhiều request hoặc các thành phần khác cùng gọi manager. Với request thiếu Basic header, có thể **không có provider trace**, vì authentication filter chưa gửi credential đi xác minh.

Log trace **không in** password, chuỗi Basic Base64, Bearer token, object `Authentication.toString()`, raw principal hoặc toàn bộ claims JWT. Những giá trị có thể chứa dữ liệu cá nhân, credential hoặc chi tiết nhạy cảm.

## 6. Soi ba dạng Authentication tại các thời điểm khác nhau

Để hiểu được một lượt xác thực, nên biết **đang đứng ở mốc nào**:

| Mốc | Ai giữ object? | Kiểu/Trạng thái | Ý nghĩa |
| --- | --- | --- | --- |
| Client gửi HTTP | `HttpServletRequest` chứa header | Chưa phải `Authentication` được chứng thực | Bằng chứng do caller cung cấp, chưa tin |
| Filter tạo input token | `BasicAuthenticationFilter` | `UsernamePasswordAuthenticationToken` chưa xác thực, `isAuthenticated=false` | Yêu cầu xác thực cần provider kiểm |
| Provider nhận input | `DaoAuthenticationProvider` | Cùng request type, đã truy cập UserDetails/encoder | Bằng chứng đang được kiểm |
| Provider trả success | Provider → Manager | Token kết quả `isAuthenticated=true`, principal và authorities đáng tin | Kết quả xác thực trước bước quản lý credentials |
| Manager trả success | `ProviderManager` → Filter | `Authentication` cuối; credentials có thể đã được xóa | Sẵn sàng để dùng trong security context |
| Filter thiết lập context | `SecurityContextHolder` | Chứa kết quả đã xác thực | Các filter/controller phía sau có thể sử dụng |
| Authorization | `AuthorizationFilter` / method security | Kiểm policies dựa trên Authentication | Quyết định được thao tác hay không |
| Controller | `Authentication` injection hoặc `@CurrentSecurityContext` | Xem principal, authorities, loại token, trạng thái | Quan sát kết quả đã được hệ thống chấp nhận |

**Thắc mắc phổ biến:** “`isAuthenticated=true` nghĩa là mật khẩu đã được kiểm ngay tại nơi đọc cờ?” Không. Nó chỉ phản ánh trạng thái đối tượng tại điểm đọc. Ta phải bảo đảm đường đi filter/manager/provider tin cậy thực sự đã kiểm credential. Không tự tạo token `authenticated(...)` từ client input rồi dùng cờ true như bằng chứng.

### 6.1. Thử mô phỏng ranh giới Manager riêng

Đây là **đoạn tích hợp** sử dụng `AuthenticationManager` đã cấu hình ở ví dụ, không phải tệp độc lập:

~~~java
Authentication input =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", passwordFromTrustedTestFixture);

Authentication result = authenticationManager.authenticate(input);

System.out.println(input.isAuthenticated());  // false
System.out.println(result.isAuthenticated());  // true
~~~

Biến `passwordFromTrustedTestFixture` là credential test do fixture kiểm soát; đoạn này minh họa API, **không hướng dẫn tạo endpoint nhận mật khẩu client rồi tự đặt result vào context**. Kết quả true chỉ xảy ra nếu provider kiểm thành công; nếu sai mật khẩu, `authenticate(...)` ném exception nên không chạy tới dòng in true.

**Tách manager khỏi filter:** khi gọi manager trực tiếp ở một Java service/test, manager **không tự đặt result vào `SecurityContextHolder`**. Trong ứng dụng web, filter hoặc thành phần bao ngoài phải quản lý context/phiên đúng cách. Đây là khác biệt giúp chẩn đoán “authenticate() thành công nhưng controller vẫn không thấy user”.

## 7. Khi quá trình thất bại: phân biệt nguyên nhân và nơi phát sinh

Một response 401 không tự cho biết lỗi xảy ra ở checkpoint nào. Hãy truy dấu **request ID → filter chain → có input credential hay không → provider đã chạy không → class exception → entry point**.

### 7.1. Không có credential

Với `/api/me` yêu cầu authenticated, không có Basic header thì `BasicAuthenticationFilter` có thể không gọi manager. Anonymous support có thể tạo `AnonymousAuthenticationToken` để biểu diễn khách vãng lai trong context; token này không có nghĩa đã có người dùng đăng nhập. Authorization từ chối, `ExceptionTranslationFilter` yêu cầu authentication entry point, dẫn tới 401 cho HTTP Basic.

**Không có provider log** trong trường hợp này là điều hợp lý, chứ không tự chứng minh provider lỗi hoặc filter chain không chạy.

### 7.2. Có credential nhưng sai

Basic filter tạo token đầu vào, manager chuyển tới provider, `PasswordEncoder` không xác nhận được mật khẩu, provider ném `BadCredentialsException` (thông điệp cụ thể có thể bị ẩn để tránh lộ user tồn tại). Với cấu hình Basic, failure được chuyển thành 401 qua authentication entry point. Không có `Authentication` thành công để đưa tới controller.

Nếu hệ thống có nhiều provider, `ProviderManager` có thể thử provider khác sau một số `AuthenticationException` thông thường; không mặc định “provider đầu từ chối là dừng ngay”. Ngược lại, `AccountStatusException` và `InternalAuthenticationServiceException` có hành vi dừng sớm. Do đó nếu debug hệ thống nhiều provider, phải biết **danh sách và thứ tự** thật.

### 7.3. Xác thực thành công nhưng thiếu quyền

Request `khach` đúng mật khẩu sẽ cho provider.success và context có principal đã xác thực. Tuy nhiên authority trong kết quả là `profile.read`; `/api/reports` yêu cầu `reports.read`. Tầng authorization từ chối bằng 403.

**401 và 403 là kết quả tại tầng HTTP**, có thể thay đổi với cấu hình form login/entry point hoặc custom handlers. `AuthenticationManager` tự nó trả Java object hoặc ném `AuthenticationException`; nó không viết HTTP response.

### 7.4. Provider lỗi hệ thống hoặc token không được hỗ trợ

`InternalAuthenticationServiceException` có thể phản ánh sự cố nguồn người dùng; `ProviderNotFoundException` có thể xuất hiện khi không provider nào xử lý được loại `Authentication`. Log loại exception và trace chọn provider; đừng in mật khẩu hoặc full stack trace vào response của client.

Những lỗi đó không thể sửa bằng cách đổi `isAuthenticated` thành true. Phải sửa nguyên nhân: cấu hình manager/provider, nguồn user, key/JWK, policy, network hoặc dữ liệu identity.

## 8. Quan sát một lượt bằng log mà không làm lộ bí mật

**Mục tiêu logging:** biết *mốc nào đã chạy*, *loại cơ chế nào xử lý request*, *kết quả gì* và *request nào tương ứng*. Không cần giữ lại credential.

### 8.1. Trường nên và không nên log

| Nên ghi (có chọn lọc) | Không nên ghi |
| --- | --- |
| Request/correlation ID, HTTP method và route template (không cần query nhạy cảm) | Raw `Authorization`, Basic Base64, bearer token |
| Authentication class, provider class, tên filter ở môi trường dev | Password dạng bản rõ hoặc hash password |
| `isAuthenticated` trước/sau ở điểm phù hợp | `Authentication.toString()` hoặc toàn bộ principal/UserDetails theo thói quen |
| Trạng thái `supports`, success/failure/abstain | Full JWT, cookie session, `refresh_token`, client secret |
| Exception class và mã lỗi nội bộ ít nhạy cảm | Stack trace/claim nhạy cảm trả cho client |
| Số lượng authority hoặc mã policy cần audit | Toàn bộ profile/PII người dùng nếu không cần thiết |

Log `Authentication` có thể vô tình làm lộ `details`, dữ liệu credential hoặc thông tin nhận diện. Ví dụ đã chọn log ít trường hơn cần thiết cho debug sản phẩm chính thức để giữ sự riêng tư. Có thể thêm pseudonymous subject ID ở audit có quy tắc lưu trữ và quyền truy cập phù hợp, tránh in email, token hoặc mật khẩu.

### 8.2. DEBUG của framework dùng khi nào?

Ở môi trường local, có thể bật tạm:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Cấu hình này hỗ trợ quan sát chain và các quyết định security ở mức tổng quan. Khi cần xem kỹ hơn, chỉ bật trace ở phạm vi hẹp và môi trường test với dữ liệu giả; không coi TRACE toàn package là cấu hình production mặc định. Nội dung log thay đổi theo phiên bản framework và filter chain thực tế. Khi kết thúc chẩn đoán, khôi phục log level theo chính sách vận hành.

### 8.3. Test bằng request ID

Một cách thực tế: client gửi `X-Correlation-Id` đã được chuẩn hóa ở gateway hoặc ứng dụng; filter logging an toàn đưa cùng ID vào MDC; provider log một loại kết quả; access log ghi HTTP status. Từ đó nối được:

~~~text
request-id=R-17  route=/api/me  basic-present=true
request-id=R-17  provider=DaoAuthenticationProvider  outcome=SUCCESS
request-id=R-17  auth-type=UsernamePasswordAuthenticationToken
request-id=R-17  authorization=ALLOWED  http-status=200
~~~

Các dòng trên là **định dạng mô tả để thiết kế observability**, **không phải output mặc định** của ứng dụng ở mục 4: code demo chỉ log bên trong provider, còn request ID và authorization outcome cần một lớp observability riêng. Không chấp nhận bất kỳ request header tùy ý làm ID hệ thống mà chưa giới hạn chiều dài và ký tự; tránh log injection.

## 9. Ba kiểu luồng khác và cách quan sát đúng

### 9.1. Form login: tạo phiên, không chỉ trả kết quả

Với `UsernamePasswordAuthenticationFilter`, input thường là `UsernamePasswordAuthenticationToken` nhận từ form login. Khi thành công, filter/cơ chế Spring Security xử lý security context, thành công/thất bại và session theo cấu hình. Browser thường nhận cookie phiên hoặc được chuyển hướng; không nhất thiết có controller JSON trả `Authentication` như demo Basic.

Nếu dùng session stateful, một request sau có thể **không gọi lại provider** vì `SecurityContext` được tải từ session/repository. Không có provider trace ở request thứ hai **không đồng nghĩa user chưa từng đăng nhập**. Cần quan sát session ID an toàn, vòng đời security context và chính sách đăng xuất/thu hồi phiên.

### 9.2. Bearer JWT: xác minh token, không đối chiếu mật khẩu

`BearerTokenAuthenticationFilter` trích bearer token và chuyển request kiểu phù hợp cho authentication manager. Với JWT, `JwtAuthenticationProvider` sử dụng decoder/validator để kiểm chữ ký, issuer, thời hạn và các điều kiện khác, như audience khi cấu hình. `Authentication` kết quả thường là `JwtAuthenticationToken`, principal thường là `Jwt`; authorities có thể được ánh xạ từ scopes theo quy tắc framework hoặc converter tùy chỉnh.

Không in raw JWT hoặc lấy claim từ một JWT chưa xác minh rồi gán vào `Authentication` kết quả. `JwtAuthenticationToken.isAuthenticated=true` phải là **kết quả** sau bước xác minh, không phải dữ liệu client tự gửi.

### 9.3. OIDC login và identity provider

Với OIDC, trình duyệt đi qua redirect/authorization-code flow, ứng dụng kiểm dữ liệu phản hồi IdP và token theo cơ chế tương ứng rồi tạo authentication principal thích hợp, thường là `OidcUser`. Có thể xuất hiện token/manager/provider khác hẳn username/password.

Khi debug hãy hỏi: “Đây là bước redirect? callback? token exchange? tạo local session? hay request API sau khi đăng nhập?” Một request có thể chỉ phục hồi session thay vì xác thực lại OIDC từ đầu. Không dùng cùng một giả định `Authentication.getPrincipal() instanceof UserDetails` cho mọi cơ chế.

## 10. Câu hỏi chẩn đoán theo đúng thứ tự

Khi một endpoint có vấn đề xác thực, trả lời lần lượt:

1. **Request thực sự đi tới endpoint/filter chain nào?** Có proxy, path rewriting hoặc nhiều `SecurityFilterChain` không?
2. **Client gửi credential theo cơ chế nào?** Basic, Bearer, cookie hay form? Có đúng header/format không? Tuyệt đối không paste token thật để hỏi debug.
3. **Filter nào tạo yêu cầu `Authentication`?** Input class là gì, `isAuthenticated` trước manager là gì?
4. **Manager nào được filter gọi?** Có `ProviderManager`, bao nhiêu provider, parent manager nào?
5. **Provider nào `supports` request type?** Nó có thực sự được gọi không? Provider có trả `null`, result hay ném exception?
6. **Bằng chứng được kiểm như thế nào?** `PasswordEncoder`, token signature + issuer/audience, introspection, session, mTLS?
7. **Result trước/sau manager ra sao?** Principal class, authenticated flag, số authorities, credentials còn hay đã xóa?
8. **Ai thiết lập và lưu `SecurityContext`?** Dùng stateless, session hay custom repository? Request sau có dùng lại context không?
9. **Authorization có cho phép thao tác không?** Thiếu authority hay thiếu quyền trên tenant/tài nguyên cụ thể?
10. **HTTP response do thành phần nào tạo?** AuthenticationEntryPoint, access denied handler, failure handler hay controller?

Khi chỉ thấy HTTP 401/403, phải truy ngược các mốc thực tế để kết luận. Khi chỉ thấy `isAuthenticated=true`, phải xem **nguồn kết quả**, **context nào đang được dùng**, và **quyền cần kiểm**.

## 11. Anti-pattern và cách tránh

| Anti-pattern | Vì sao sai | Cách thay thế |
| --- | --- | --- |
| In `Authorization`/password để “xem request đầu vào” | Lộ credential có thể bị tái sử dụng | Chỉ log sự hiện diện và scheme; thử credential giả |
| Dựng token `authenticated(...)` từ JSON client để “test thành công” | Bỏ qua kiểm bằng chứng, sinh lỗ hổng giả mạo | Gọi manager/provider có kiểm credential, hoặc dùng test helper **chỉ** trong test authorization |
| Chỉ đọc `isAuthenticated()` rồi kết luận mật khẩu đúng | Cờ thuộc object, phụ thuộc ai tạo và có anonymous/remember-me | Truy vết filter → manager → provider → result |
| Quan sát controller khi request đã bị filter từ chối | Controller chưa hề chạy | Dùng trace ở filter/provider và exception handler |
| Kết luận không có provider log là Security không hoạt động | Có thể request không mang credential, dùng session hoặc không khớp filter | Xác minh chain, credential và session context |
| Gọi manager trực tiếp rồi mặc định result đã ở `SecurityContextHolder` | Manager không tự lưu context | Để filter quản lý hoặc thiết lập repository/context bằng cơ chế đã thiết kế |
| Đồng nhất 401 với 403 | Xác thực và phân quyền là hai quyết định khác nhau | Phân biệt thiếu/sai credential với thiếu quyền |
| Đọc principal luôn bằng cast `UserDetails` | JWT/OIDC/anonymous có principal type khác | Kiểm token type và hợp đồng của cơ chế |
| Bật DEBUG/TRACE vĩnh viễn trong production | Rủi ro rò rỉ và tăng chi phí logs | Log có kiểm soát, chỉ phát thông tin cần thiết, thu hồi debug khi xong |
| Dùng `@WithMockUser` rồi cho rằng đã test password | Bỏ qua filter/provider thực | Thêm test HTTP Basic/Bearer qua đường xác thực thực tế |
| Đặt toàn bộ nghiệp vụ vào authentication provider | Trộn kiểm chứng danh tính và chính sách tài nguyên | Provider xác thực; authorization/service kiểm quyền cụ thể |

## 12. Bài tập tự kiểm tra

**Tình huống 1.** Request có Basic header nhưng password sai. Provider log xuất hiện, controller không được gọi. Tại sao?

**Đáp án:** Filter đã tạo input `Authentication`; provider kiểm và ném `AuthenticationException`; filter/entry point xử lý lỗi trước khi request đi vào controller. Không có authentication result hợp lệ.

**Tình huống 2.** Request `khach` có password đúng, provider log success, nhưng `GET /api/reports` trả 403. Có mâu thuẫn không?

**Đáp án:** Không. Xác thực thành công xác định được chủ thể và authorities; bước authorization còn phải kiểm `reports.read`. `khach` chỉ có `profile.read`.

**Tình huống 3.** Sau login bằng form, request thứ hai không có provider log nhưng vẫn có principal. Đó chắc chắn là lỗi?

**Đáp án:** Không. Một session/repository hợp lệ có thể phục hồi `SecurityContext` đã xác thực ở request trước. Cần xem mô hình session và chính sách hiệu lực/thu hồi, không suy luận chỉ từ số lần provider chạy.

**Tình huống 4.** Trong `/api/me`, `getCredentials() == null`. Có nghĩa client không gửi mật khẩu?

**Đáp án:** Không. `ProviderManager` mặc định xóa credentials khỏi `Authentication` result nếu hỗ trợ; mật khẩu đã được kiểm trước đó.

**Tình huống 5.** Developer ghi toàn bộ `Authentication.toString()` vào log để điều tra 401. Có an toàn không?

**Đáp án:** Không bảo đảm. Các class khác nhau có thể chứa details/claim/PII khác nhau. Log tối thiểu kiểu, trạng thái, mã lỗi và request ID an toàn; không ghi raw credentials/token.

**Tình huống 6.** Một test chỉ gọi `manager.authenticate(...)` thành công nhưng không thấy user trong `SecurityContextHolder`. Vì sao?

**Đáp án:** `AuthenticationManager` trả kết quả; **caller/filter** chịu trách nhiệm đặt nó vào context. Một test trực tiếp manager không thực hiện tự động các bước của filter chain.

**Tình huống 7.** API dùng JWT, nhưng code quan sát ép principal sang `UserDetails` và bị `ClassCastException`. Sửa thế nào?

**Đáp án:** Dựa vào loại `Authentication` thực tế của cơ chế JWT, ví dụ `JwtAuthenticationToken` và `Jwt` khi dùng Resource Server. Thiết kế adapter chuyển thành một principal nghiệp vụ thống nhất nếu cần; không ép kiểu dựa trên giả định username/password.

**Tình huống 8.** Lỗi HTTP 401 xuất hiện, provider không được gọi. Ba giả thuyết cần kiểm đầu tiên?

**Đáp án:** Credential không có/không đúng scheme, request đi qua một filter chain khác, hoặc request đang sử dụng cơ chế (session, bearer, form) không đi qua provider đã instrument. Hãy xác minh request và chain trước khi thay code provider.

## 13. Những điều phải nhớ

Một lượt xác thực có **đầu vào chưa tin**, **bước kiểm chứng đáng tin**, **`Authentication` kết quả**, **lưu trữ theo ngữ cảnh request**, và **quyết định phân quyền**. Bài học thực sự nằm ở việc nối được các bước bằng dấu vết có kiểm soát:

~~~text
Credential trên HTTP request
  -> authentication filter tạo Authentication request (chưa xác thực)
  -> AuthenticationManager / ProviderManager
  -> AuthenticationProvider + nguồn kiểm bằng chứng
  -> Authentication result (đã xác thực hoặc exception)
  -> filter đặt SecurityContext cho request thành công
  -> authorization áp dụng authorities và policy tài nguyên
  -> controller hoặc HTTP 401/403
~~~

**Khi thấy `Authentication` kết quả, hãy hỏi**: Ai kiểm credential? Token class nào? Principal đến từ đâu? Authorities đến từ nguồn nào? Ai đưa result vào context? Endpoint còn kiểm quyền gì? Đó là cách quan sát một lượt xác thực có thể giải thích và kiểm chứng được.

### Tài liệu chính thức

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — SecurityContextHolder and SecurityContext: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder
- Spring Security — Request Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
