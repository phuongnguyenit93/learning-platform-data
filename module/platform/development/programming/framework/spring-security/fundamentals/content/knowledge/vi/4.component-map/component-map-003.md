# UserDetails và UserDetailsService trong xác thực bằng tài khoản

> **Bối cảnh:** Spring Security Servlet/Spring MVC, Java 17+ và Spring Boot 3.x. Bài này giải thích **UserDetails** và **UserDetailsService** trong xác thực username/password: cách đọc account từ nguồn dữ liệu, đối chiếu mật khẩu, kiểm tra trạng thái, xây dựng danh tính và kiểm thử luồng. Ví dụ dùng HTTP Basic để quan sát từng request nhưng cùng cơ chế tải tài khoản còn được sử dụng với form login khi cấu hình DaoAuthenticationProvider.

## 1. Vấn đề: Spring Security không tự biết database tài khoản của bạn

Giả sử ứng dụng có các cột **username**, **password_hash**, **enabled**, **locked** và quan hệ với bảng **roles**. Khi client gửi username/password, Spring Security cần biết:

1. **Tên đăng nhập đó tồn tại không?** Tài khoản được lưu ở database, LDAP, kho nội bộ hay một nguồn khác?
2. **Mật khẩu đã lưu là gì?** Đó phải là encoded password/hash dùng để xác minh, không phải plaintext.
3. **Tài khoản có đang được phép đăng nhập?** Có bị khóa, vô hiệu hóa hoặc hết hạn không?
4. **Người dùng có những quyền nào?** Ví dụ **ROLE_USER**, **ROLE_ADMIN**, **report:read**.
5. **Kết quả xác thực được dùng ở đâu?** Sau khi hợp lệ, Authentication được đưa vào SecurityContext để kiểm tra quyền trên request.

Spring Security định nghĩa hai interface cho việc cung cấp thông tin account:

- **UserDetails:** mô tả dữ liệu account theo cấu trúc Spring Security hiểu, gồm username, password hash, authorities và bốn trạng thái.
- **UserDetailsService:** có trách nhiệm **tải UserDetails theo username**.

**UserDetailsService không xác thực mật khẩu.** Nó chỉ tải dữ liệu. **DaoAuthenticationProvider** mới làm việc với **PasswordEncoder** để so khớp credential và kiểm tra trạng thái, sau đó tạo **Authentication** khi thành công. **AuthorizationManager** hoặc method security quyết định quyền truy cập tiếp theo.

| Thành phần | Vai trò | Không đảm nhiệm |
| --- | --- | --- |
| UserDetailsService | Tìm account theo username, trả UserDetails | So khớp raw password, cấp access token |
| UserDetails | Mang password hash, quyền, trạng thái tài khoản | Quản lý CRUD user hay session |
| DaoAuthenticationProvider | Dùng UserDetailsService và PasswordEncoder để xác thực username/password | Quyết định ai được xem từng tài liệu |
| PasswordEncoder | Băm password khi lưu, kiểm tra raw password với hash | Giải mã BCrypt để lấy password cũ |
| AuthenticationManager | Điều phối authentication đến provider hỗ trợ | Truy vấn database account trực tiếp |
| Authentication | Kết quả chứa principal, authorities, trạng thái xác thực | Một bản ghi user entity mặc định |
| SecurityContextHolder | Cho mã xử lý truy cập context hiện tại | Mặc định luôn lưu context qua phiên |
| AuthorizationManager | Quyết định allow/deny theo policy | Xác minh mật khẩu |

## 2. Nhìn đúng luồng HTTP request

Ví dụ client gọi **GET /me** kèm HTTP Basic:

~~~text
Client -> Authorization: Basic <encoded-username-password>
    |
    v
BasicAuthenticationFilter
    |
    | tạo UsernamePasswordAuthenticationToken chưa xác thực
    v
AuthenticationManager / ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |           |
    |           +--> repository / database / directory
    |           |
    |           +--> UserDetails
    |                   - username
    |                   - password hash
    |                   - GrantedAuthority
    |                   - account status flags
    |
    +--> PasswordEncoder.matches(rawPassword, storedHash)
    |
    +--> account / credential status checks
    |
    v
Authentication đã xác thực
    |
    v
SecurityContextHolder
    |
    v
AuthorizationFilter -> Controller / Service -> HTTP response
~~~

**Cần phân biệt hai điểm:**

- **Tải được account không có nghĩa đã xác thực:** UserDetailsService có thể tìm thấy alice dù client gửi mật khẩu sai. Provider sẽ từ chối ở bước so khớp mật khẩu.
- **Đã xác thực không có nghĩa được truy cập mọi thứ:** alice có thể đã đăng nhập với ROLE_USER, nhưng URL yêu cầu ROLE_ADMIN vẫn có thể nhận **403**.

Những thành phần cụ thể và thứ tự một số filter tùy cấu hình. HTTP Basic sử dụng **BasicAuthenticationFilter**; form login thường dùng **UsernamePasswordAuthenticationFilter**; Bearer JWT resource server sử dụng provider/decoder khác, không mặc định gọi UserDetailsService.

## 3. Hợp đồng UserDetails: bảy điều quan trọng

Các chữ ký chính của **org.springframework.security.core.userdetails.UserDetails**:

~~~java
// Trích các phương thức để học; không phải toàn bộ interface.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isEnabled();
boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
~~~

Đây là chữ ký minh họa, **không phải chương trình Java độc lập**.

### 3.1. Username

**getUsername()** trả tên dùng nhận diện account khi xác thực. Trong ứng dụng thực, username có thể là login ID hoặc email, nhưng cần chính sách chuẩn hóa nhất quán. Nếu có nhiều tenant, phải xác định username unique trong tenant hay toàn hệ thống; không truy vấn tùy tiện account có tên trùng của tenant khác.

Trong principal của nghiệp vụ, nên cân nhắc dùng **accountId ổn định** để truy vấn dữ liệu thay cho username có thể đổi.

### 3.2. Password

**getPassword()** trả **encoded password đã lưu**. Ví dụ với BCrypt, giá trị chứa salt và hash, không thể lấy lại raw password.

Provider sẽ thực hiện logic tương đương:

~~~java
boolean valid = passwordEncoder.matches(
    rawPasswordFromRequest,
    userDetails.getPassword()
);
~~~

Đây là **snippet trong cơ chế xác thực**, không phải lớp Java hoàn chỉnh. Không dùng **raw.equals(storedHash)**, không tự mã hóa lại hash mỗi khi gọi UserDetailsService, và không tự viết hàm giải mã BCrypt.

### 3.3. GrantedAuthority

**getAuthorities()** có thể chứa:

~~~text
ROLE_USER
ROLE_ADMIN
profile:read
invoice:approve
~~~

Trong cấu hình mặc định:

- **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN**.
- **hasAuthority("ROLE_ADMIN")** cũng kiểm tra chuỗi **ROLE_ADMIN**.
- **hasAuthority("profile:read")** kiểm tra chính xác **profile:read**.
- Builder **roles("USER")** tự gắn tiền tố **ROLE_**; builder **authorities("ROLE_USER")** giữ nguyên chuỗi cung cấp.

Quyền đã được chuẩn hóa ở một chỗ sẽ tránh lỗi **ROLE_ROLE_ADMIN**, hoặc database chỉ có **ADMIN** nhưng rule lại đòi **ROLE_ADMIN**. Vai trò trong UserDetails nói lên loại quyền; quyền sở hữu **một resource cụ thể** còn cần chính sách domain phù hợp.

### 3.4. Bốn trạng thái account

| Phương thức | Trả true có nghĩa là | Trả false có nghĩa là |
| --- | --- | --- |
| **isEnabled()** | Được phép dùng account | Account bị vô hiệu hóa |
| **isAccountNonExpired()** | Account chưa hết hạn | Account đã hết hạn |
| **isAccountNonLocked()** | Account không bị khóa | Account đã bị khóa |
| **isCredentialsNonExpired()** | Credential chưa hết hạn | Credential đã hết hạn |

Chú ý tên dạng phủ định kép: **isAccountNonLocked() == true** nghĩa là **không bị khóa**. Nếu database có cột **locked**, mapping phải là **accountNonLocked = !locked**. Với builder Spring Security, phương thức **accountLocked(locked)** nhận cờ ở chiều ngược lại.

**DaoAuthenticationProvider** kiểm tra những trạng thái này trong quy trình username/password thông dụng. Một custom provider có thể triển khai logic khác; cần kiểm thử thực tế khi chính sách khóa account quan trọng.

### 3.5. UserDetails có phải entity database?

Không bắt buộc. Spring Security có sẵn class **org.springframework.security.core.userdetails.User** implements UserDetails. Bạn có thể đọc **AccountEntity** từ JPA rồi chuyển thành **User.withUsername(...).password(...).authorities(...).build()**.

Không nên mặc định trả nguyên entity làm principal: entity có thể chứa thông tin riêng tư, quan hệ lazy, đối tượng mutable và password hash. Nếu cần accountId/tenantId trong principal, có thể xây dựng một custom UserDetails **nhỏ, có mục đích rõ**, hoặc adapter CurrentUser riêng. Không serialize nguyên UserDetails làm body JSON của endpoint.

## 4. Hợp đồng UserDetailsService và UsernameNotFoundException

Interface:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

Đây là phần chữ ký để đọc, không phải file Java độc lập.

**loadUserByUsername(username)** cần:

1. Tra đúng nguồn dữ liệu và đúng phạm vi định danh.
2. Nếu account tồn tại, trả UserDetails có password hash, authorities và trạng thái đúng.
3. Nếu không tìm thấy, **ném UsernameNotFoundException**; không trả null, không bịa account mặc định.
4. Không tự gán SecurityContextHolder, không tự “đăng nhập” người dùng và không kiểm tra raw password vì method không có raw password trong contract.

Lỗi **UsernameNotFoundException** là chi tiết của tầng xác thực. Trong **DaoAuthenticationProvider**, lỗi không tìm thấy username mặc định thường được che thành lỗi credential chung nhằm hạn chế dò user. Đừng biến sự khác nhau giữa “username không tồn tại” và “password sai” thành thông báo công khai dễ bị khai thác.

**UserDetailsService không phải API đăng ký tài khoản hoặc đổi mật khẩu.** Tạo user, khóa user, cấp quyền, đặt lại mật khẩu, MFA, kiểm tra email, thu hồi session/token thuộc những nghiệp vụ và thành phần khác. **UserDetailsManager** là interface khác có thêm một số tác vụ quản lý user, không đồng nghĩa với đầy đủ hệ thống IAM.

## 5. Demo đầy đủ: Spring Boot 3, Java 17+ và HTTP Basic

Để thấy rõ cả user hợp lệ, sai mật khẩu, thiếu quyền, bị khóa và bị vô hiệu hóa, xây dựng một ứng dụng Spring Boot nhỏ với một repository tài khoản trong bộ nhớ. Cách tổ chức này giữ nguyên được khi thay repository bằng Spring Data JPA.

Các tài khoản demo:

| User | Mật khẩu dùng tại localhost | Authorities | Trạng thái |
| --- | --- | --- | --- |
| alice | alice123 | ROLE_USER, profile:read | Hoạt động |
| admin | admin123 | ROLE_ADMIN, profile:read | Hoạt động |
| locked | locked123 | ROLE_USER | Bị khóa |
| disabled | disabled123 | ROLE_USER | Bị vô hiệu hóa |

Mật khẩu cố định chỉ dùng trong bài thực hành. Production cần quản lý credential/secret, bảo vệ brute-force và dùng TLS.

### 5.1. Dependencies và package

Tạo một dự án **Spring Boot 3.x + Java 17+** với Gradle Wrapper, thêm vào **build.gradle** hiện hữu (plugin và dependency management của Spring Boot đã được khai báo):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo các file theo cấu trúc:

~~~text
src/main/java/com/example/accountauth/
  AccountAuthApplication.java
  DemoAccount.java
  DemoAccountRepository.java
  AccountUserDetailsService.java
  SecurityConfig.java
  AccountController.java

src/test/java/com/example/accountauth/
  AccountAuthTest.java
~~~

### 5.2. AccountAuthApplication.java

~~~java
package com.example.accountauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountAuthApplication.class, args);
    }
}
~~~

### 5.3. DemoAccount.java: mô hình riêng của ứng dụng

~~~java
package com.example.accountauth;

import java.util.Set;

public record DemoAccount(
    String username,
    String passwordHash,
    boolean enabled,
    boolean accountNonExpired,
    boolean accountNonLocked,
    boolean credentialsNonExpired,
    Set<String> authorities
) {
}
~~~

DemoAccount **không implements UserDetails**. Tách model dữ liệu và abstraction bảo mật giúp không ràng buộc cả domain vào Spring Security. Trong ứng dụng thật, model account có thể thêm ID, tenant, timestamps, nhiều trạng thái và quan hệ quyền.

### 5.4. DemoAccountRepository.java: nguồn account

~~~java
package com.example.accountauth;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

@Repository
public class DemoAccountRepository {

    private final Map<String, DemoAccount> accounts;

    public DemoAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice", new DemoAccount(
                "alice", encoder.encode("alice123"),
                true, true, true, true,
                Set.of("ROLE_USER", "profile:read")
            ),
            "admin", new DemoAccount(
                "admin", encoder.encode("admin123"),
                true, true, true, true,
                Set.of("ROLE_ADMIN", "profile:read")
            ),
            "locked", new DemoAccount(
                "locked", encoder.encode("locked123"),
                true, true, false, true,
                Set.of("ROLE_USER")
            ),
            "disabled", new DemoAccount(
                "disabled", encoder.encode("disabled123"),
                false, true, true, true,
                Set.of("ROLE_USER")
            )
        );
    }

    public Optional<DemoAccount> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
~~~

Ở demo này, **encoder.encode(...)** chỉ được gọi khi khởi tạo repository in-memory. Với database thật, **password hash đã được lưu** lúc người dùng tạo/đổi mật khẩu; truy vấn repository chỉ đọc hash. BCrypt có salt nên cùng raw password có thể sinh chuỗi hash khác nhau giữa các lần chạy, đó là hành vi bình thường.

### 5.5. AccountUserDetailsService.java: chuyển account thành UserDetails

~~~java
package com.example.accountauth;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final DemoAccountRepository accounts;

    public AccountUserDetailsService(DemoAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        if (username == null || username.isBlank()) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        DemoAccount account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountExpired(!account.accountNonExpired())
            .accountLocked(!account.accountNonLocked())
            .credentialsExpired(!account.credentialsNonExpired())
            .build();
    }
}
~~~

Giải thích:

- **@Service** đăng ký một UserDetailsService bean cho Spring Security.
- **findByUsername(...)** chỉ tải dữ liệu, không có raw password từ request.
- **orElseThrow(...)** bảo đảm service không trả null cho username không có.
- **password(...)** nhận **hash đã lưu**, không băm lại hash.
- **authorities(...)** nhận chính xác chuỗi quyền đã quyết định ở application.
- **disabled(...)**, **accountExpired(...)**, **accountLocked(...)** và **credentialsExpired(...)** phản ánh trạng thái đúng với dấu phủ định khi cần.
- **User.withUsername(...)** tạo UserDetails của thư viện Spring Security. Việc trả UserDetails **chưa đánh dấu login thành công**.

### 5.6. SecurityConfig.java: Basic và PasswordEncoder

~~~java
package com.example.accountauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

Với **một UserDetailsService bean** và **PasswordEncoder** trong cấu hình username/password thông thường, Spring Security có thể thiết lập **DaoAuthenticationProvider** phù hợp để provider dùng service/encoder. Khi ứng dụng có nhiều UserDetailsService, custom AuthenticationProvider hoặc AuthenticationManager riêng, phải cấu hình cụ thể và xác minh provider được chọn; không giả định Spring sẽ tự đoán đúng ý.

**SessionCreationPolicy.STATELESS** giúp ví dụ không dùng HttpSession để đọc/lưu SecurityContext cho request kế tiếp. HTTP Basic được xác thực dựa trên header mỗi request; UserDetailsService vẫn hoạt động với các cơ chế form login/session nếu cấu hình phù hợp. Đây không phải yêu cầu của UserDetailsService.

Trong thực tế, cấu hình security còn cần xét CSRF, CORS, error dispatch, health check và các endpoint khác; demo chỉ dùng GET để học xác thực.

### 5.7. AccountController.java

~~~java
package com.example.accountauth;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + authorities;
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

Controller **không cần tự gọi UserDetailsService**. Nó nhận Authentication đã tạo sau xác thực. Trong demo, principal thường là UserDetails trả về từ service; với JWT, OAuth2 login hoặc cơ chế khác, principal có thể là kiểu khác, vì vậy đừng cast mọi principal thành UserDetails.

### 5.8. Chạy và kiểm tra phản hồi

Từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Gửi request từ terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u locked:locked123 http://localhost:8080/me
curl -i -u disabled:disabled123 http://localhost:8080/me
curl -i -u nobody:password http://localhost:8080/me
~~~

Với ứng dụng demo chạy độc lập, kết quả **dự kiến**:

| Request | Status | Body khi thành công hoặc giải thích |
| --- | --- | --- |
| Anonymous → GET /public | **200** | **public** |
| Anonymous → GET /me | **401** | Chưa cung cấp credential hợp lệ |
| alice + password đúng → GET /me | **200** | **alice ROLE_USER,profile:read** |
| alice → GET /admin | **403** | Xác thực hợp lệ, thiếu ROLE_ADMIN |
| admin → GET /admin | **200** | **admin-only** |
| alice + password sai → GET /me | **401** | PasswordEncoder từ chối |
| locked + password đúng → GET /me | **401** | Tài khoản bị khóa |
| disabled + password đúng → GET /me | **401** | Tài khoản bị vô hiệu hóa |
| nobody → GET /me | **401** | Không tồn tại tài khoản |

**401** với HTTP Basic thường có header **WWW-Authenticate** yêu cầu xác thực. **403** ở đây cho account đã xác thực nhưng thiếu quyền. Body và chi tiết lỗi không có định dạng cố định nếu không cấu hình explicit exception handler. HTTP response hiển thị bởi **curl -i**, không phải stdout của Java app.

Không sử dụng password demo trong production. **Basic mã hóa credential bằng Base64, không mã hóa bảo mật**: bắt buộc dùng HTTPS/TLS trên mạng và tránh đưa password thật vào command history, log hay source code.

## 6. Kiểm thử bằng MockMvc: thành công, sai credential, khóa và thiếu quyền

Tạo file **src/test/java/com/example/accountauth/AccountAuthTest.java**:

~~~java
package com.example.accountauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountAuthTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void aliceAuthenticatesWithCorrectPassword() throws Exception {
        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER,profile:read"));
    }

    @Test
    void missingAndWrongPasswordAreRejected() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUsernameIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("nobody", "password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAndDisabledAccountsCannotAuthenticate() throws Exception {
        mvc.perform(get("/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("disabled", "disabled123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedDoesNotMeanAuthorized() throws Exception {
        mvc.perform(get("/admin").with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Các test đi qua **HTTP Basic filter → AuthenticationManager → DaoAuthenticationProvider → UserDetailsService → PasswordEncoder** rồi authorization. **httpBasic(...)** trong Spring Security Test tạo header credential cho request, không tự gán một principal đã đăng nhập để bỏ qua bước kiểm tra mật khẩu. Các trường hợp âm quan trọng gồm sai password, username không tồn tại, account locked/disabled và quyền không đủ.

## 7. Chuyển từ in-memory sang Spring Data JPA

Với database thực, bạn vẫn giữ interface **UserDetailsService**. Chỉ thay phần nguồn dữ liệu bằng một repository, sau đó chuyển **AccountEntity** thành UserDetails.

Ví dụ một repository JPA (snippet cần entity và imports phù hợp):

~~~java
public interface AccountJpaRepository
        extends JpaRepository<AccountEntity, Long> {

    Optional<AccountEntity> findByLoginName(String loginName);
}
~~~

Trong một adapter có thể đọc và chuyển dữ liệu như sau (snippet **không độc lập**, cần định nghĩa entity, repository và hàm resolveAuthorities):

~~~java
AccountEntity account = repository.findByLoginName(username)
    .orElseThrow(() ->
        new UsernameNotFoundException("Invalid credentials")
    );

return User.withUsername(account.getLoginName())
    .password(account.getPasswordHash())
    .authorities(resolveAuthorities(account))
    .disabled(!account.isEnabled())
    .accountLocked(account.isLocked())
    .build();
~~~

**resolveAuthorities(...)** là hàm bạn phải tự triển khai để chuyển role/permission từ schema của ứng dụng. Nếu dữ liệu có cờ account-expired/credentials-expired, cần chuyển đủ các trạng thái đó; nếu không có thì phải xác định chính sách mặc định một cách rõ ràng.

Cần quan tâm thêm các vấn đề sau:

- **Unique identity:** username/email unique theo quy tắc đã định; với multi-tenant, có thể phải unique theo cặp **tenant_id + normalized_username**. UserDetailsService chỉ nhận một chuỗi username, nên phải thiết kế cách xác định tenant đáng tin cậy hoặc sử dụng provider phù hợp.
- **Password storage:** database lưu hash từ BCrypt/Argon2 hoặc encoder phù hợp. Không lưu raw password, không hash lại trong loadUserByUsername.
- **Quan hệ role/permission:** tránh lazy-loading lỗi ngoài transaction hoặc truy vấn N+1; chọn query/fetch phù hợp cho việc đọc account.
- **Account status:** khóa/vô hiệu hóa/hết hạn phải được ánh xạ nhất quán, kiểm thử riêng.
- **Quyền động:** thay role trong DB không tự thay Authentication đã lưu trong session hoặc access token đã cấp; cần cache invalidation, session invalidation hoặc token revocation/revalidation theo chính sách.
- **Dữ liệu nhạy cảm:** không trả entity hoặc UserDetails trực tiếp qua JSON; dùng public DTO có các trường được phép.
- **Account ID:** sử dụng ID ổn định khi kiểm tra ownership/tenant, không hoàn toàn dựa vào username có thể đổi.

## 8. PasswordEncoder: các điều thường bị hiểu sai

### 8.1. Hash của cùng một password không nhất thiết giống nhau

BCrypt sử dụng salt, nên hai lần mã hóa password có thể tạo hai hash khác nhau. Khi kiểm tra hãy dùng **matches(raw, storedHash)**, không dùng **encode(raw).equals(storedHash)**.

Một ví dụ Java 17 **độc lập không dùng thư viện** để quan sát rằng raw password không bằng chuỗi đại diện cho hash (ví dụ này **không làm nhiệm vụ xác thực thật**):

**PasswordEqualityDemo.java**

~~~java
public class PasswordEqualityDemo {
    public static void main(String[] args) {
        String raw = "alice123";
        String stored = "a-password-hash-not-raw-password";

        System.out.println(raw.equals(stored));
    }
}
~~~

Chạy:

~~~bash
javac PasswordEqualityDemo.java
java PasswordEqualityDemo
~~~

Stdout chính xác:

~~~text
false
~~~

Dùng **PasswordEncoder** của Spring Security cho kiểm tra thực tế. Ví dụ độc lập chỉ cho thấy **so sánh trực tiếp raw string với hash string không phải là password verification**.

### 8.2. BCrypt và DelegatingPasswordEncoder

- **BCryptPasswordEncoder** dùng thuật toán BCrypt với salt/work factor, phù hợp demo.
- **PasswordEncoderFactories.createDelegatingPasswordEncoder()** có thể hỗ trợ nhiều encoder qua prefix trên stored password, ví dụ **{bcrypt}...**. Nếu đổi sang DelegatingPasswordEncoder, schema/migration phải bảo đảm hash có format phù hợp; prefix không đúng có thể dẫn đến lỗi xác thực.
- Không dùng **NoOpPasswordEncoder**, hash nhanh như MD5/SHA-256 thuần hoặc plaintext để lưu mật khẩu production.
- Password encoder có thể hỗ trợ chính sách cập nhật hash qua **UserDetailsPasswordService** khi được provider cấu hình đúng; khai báo PasswordEncoder thôi không có nghĩa tự động cập nhật tất cả hash trong DB.

Không đặt **matches(...)** trong UserDetailsService; interface này không có raw password và không phải AuthenticationProvider.

## 9. Cache, session và token có liên quan nhưng không đồng nhất

Một UserDetailsService được gọi khi provider cần nạp account, nhưng **không thể khẳng định mọi request đã đăng nhập sẽ luôn gọi lại service**:

- HTTP Basic trong cấu hình phổ biến có thể xác thực từng request, nhưng provider/các thành phần có thể có cache.
- Form login có thể tạo Authentication rồi lưu trong session, các request sau khôi phục SecurityContext mà không cần kiểm tra password lại.
- JWT Resource Server thường xác minh JWT và chuyển claims thành Authentication; nó không mặc định gọi UserDetailsService.
- Opaque token thường qua introspection/lookup; cơ chế này cũng không mặc định dùng UserDetailsService.
- Khi đã cấp session hoặc token, việc đổi mật khẩu, khóa account hay thay role trong database không nhất thiết chặn mọi phiên/token cũ tức thì.

Do đó, nếu nghiệp vụ yêu cầu **khóa tài khoản có hiệu lực ngay**, cần thiết kế session invalidation, token revocation/revalidation và chính sách cache. Chỉ sửa implementation **loadUserByUsername(...)** không giải quyết toàn bộ vòng đời đăng nhập.

**Spring WebFlux reactive** sử dụng **ReactiveUserDetailsService**, là interface khác với UserDetailsService đồng bộ của Servlet. Không thực hiện truy vấn database blocking trực tiếp trên event loop trong một ứng dụng reactive.

## 10. Lỗi thường gặp và cách xử lý

### 10.1. “Không thấy UserDetailsService được gọi”

Hãy kiểm tra chuỗi chính xác:

~~~text
HTTP request
  -> SecurityFilterChain có khớp không?
  -> Filter xác thực nào đang bật?
  -> AuthenticationManager/Provider được chọn?
  -> Provider có dùng DaoAuthenticationProvider?
  -> DaoAuthenticationProvider dùng bean UserDetailsService nào?
  -> Repository truy vấn đúng username/tenant không?
~~~

Nếu ứng dụng chỉ cấu hình Bearer JWT thì không nên chờ **loadUserByUsername** chạy. Nếu có nhiều bean **UserDetailsService** hoặc AuthenticationManager tùy biến, phải kiểm tra cách chúng được kết nối thực tế.

### 10.2. “Đăng nhập đúng mật khẩu vẫn 401”

Kiểm tra encoder và định dạng stored hash, username normalization, cờ disabled/locked/expired, credential từ client, user lookup và các exception khi truy vấn. Nếu dùng DelegatingPasswordEncoder nhưng dữ liệu không có prefix phù hợp, hoặc nếu cột **locked** bị mapping ngược, request có thể bị từ chối dù raw password đúng.

### 10.3. “Đăng nhập thành công nhưng vẫn 403”

Lúc này authentication có thể đã thành công. Kiểm tra **ROLE_** prefix, danh sách authorities, rule theo URL/method, ownership/tenant và các bảo vệ khác như CSRF. Không tự đổi UserDetailsService thành cơ chế “luôn cho phép” để sửa 403.

### 10.4. “Trả null để coi như anonymous”

Sai hợp đồng. **loadUserByUsername** phải trả UserDetails hoặc ném UsernameNotFoundException. Anonymous authentication được xử lý bởi các cơ chế/filter phù hợp, không phải một account giả từ database lookup.

### 10.5. “Trả nguyên AccountEntity làm API response”

Có thể làm lộ password hash hoặc dữ liệu nội bộ, gây vòng serialize hoặc lazy-loading exception. Trả DTO công khai và chỉ gồm thông tin cần cho client. Với principal tùy biến, tránh mang thông tin nhạy cảm và không cast tùy tiện principal của OAuth2/JWT thành entity.

### 10.6. “Có UserDetailsService là tự có endpoint đăng ký”

Interface chỉ tải user cho authentication. Đăng ký/đổi mật khẩu/khóa/cấp quyền là nghiệp vụ phải triển khai, xác thực và audit riêng.

### 10.7. “Một lần login thì mọi quyền cập nhật tức thì”

Session/JWT/cache có vòng đời riêng. Với account bị thu hồi quyền, thiết kế strategy cho session, token và thông tin phân quyền đã cấp. Kiểm thử tình huống **đang đăng nhập rồi mới khóa account**.

### 10.8. “Càng nhiều thông tin trong principal càng tốt”

Chỉ giữ dữ liệu cần thiết cho authorization và nhận diện. Principal có thể được giữ qua session, in ra log hoặc xuất hiện trong exception; hạn chế dữ liệu nhạy cảm trong nó.

### 10.9. “Bỏ qua giới hạn số lần thử vì password đã hash”

Hash password bảo vệ dữ liệu lưu trữ nhưng không tự chống credential stuffing và brute-force online. Cần rate limiting, tài khoản khóa theo chính sách hợp lý, giám sát, MFA khi cần và thông báo lỗi không giúp dò username.

## 11. Cách debug có hệ thống

Bật log Spring Security ở môi trường phát triển nếu cần:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi debug, kiểm tra lần lượt: request tới chain nào; header Basic/form login có đúng không; provider nào thực hiện; lookup username có trả account không; hash có đúng encoder không; bốn status flags; authorities; authorization rule. **Không log raw password, Authorization header, token hoặc password hash**.

Nếu test thất bại, phân biệt:
- **401**: chưa xác thực thành công hoặc credential không được chấp nhận theo entry point.
- **403**: request thường đã có Authentication nhưng thiếu quyền, hoặc có filter khác như CSRF từ chối.
- **302**: form login có thể redirect tới trang login thay vì HTTP Basic challenge.

Các status tùy cấu hình AuthenticationEntryPoint/AccessDeniedHandler, chain và loại client; không suy diễn nguyên nhân chỉ từ con số.

## 12. Tự kiểm tra kiến thức

**Câu 1.** UserDetailsService có nhận mật khẩu người dùng nhập vào không?

**Đáp án:** Không. Interface chỉ nhận username, trả UserDetails chứa hash và quyền. DaoAuthenticationProvider với PasswordEncoder kiểm tra raw password.

**Câu 2.** Tìm thấy alice trong database nhưng password request sai. Service có phải ném UsernameNotFoundException không?

**Đáp án:** Không. Dữ liệu alice tồn tại nên service trả UserDetails; provider sau đó từ chối password.

**Câu 3.** Database có cờ **locked=true**. **isAccountNonLocked()** cần trả gì?

**Đáp án:** **false**. Builder Spring Security có thể dùng **accountLocked(true)**.

**Câu 4.** Vì sao account có authority **ADMIN** có thể nhận 403 với **hasRole("ADMIN")**?

**Đáp án:** Với tiền tố mặc định, hasRole("ADMIN") yêu cầu chuỗi **ROLE_ADMIN**.

**Câu 5.** Nếu username không có, loadUserByUsername nên làm gì?

**Đáp án:** Ném **UsernameNotFoundException**, không trả null hoặc user giả.

**Câu 6.** Có thể dùng UserDetailsService để xác thực mọi JWT Bearer không?

**Đáp án:** Không mặc định. JWT Resource Server có cơ chế decoder/provider riêng; chỉ tích hợp tra account nếu thiết kế đòi hỏi.

**Câu 7.** Tại sao password hash BCrypt mới tạo không bằng hash cũ của cùng password?

**Đáp án:** BCrypt dùng salt; so sánh cần **matches(raw, storedHash)**.

**Câu 8.** Đăng nhập thành công bằng ROLE_USER có đồng nghĩa được đọc mọi tài liệu không?

**Đáp án:** Không. Cần authorization theo action, resource, ownership và tenant.

**Câu 9.** Khóa tài khoản trong DB có tự vô hiệu hóa JWT/session đã cấp không?

**Đáp án:** Không luôn. Cần chiến lược thu hồi, tái kiểm tra hoặc giới hạn lifetime phù hợp.

**Câu 10.** Spring Security lấy Authentication từ UserDetailsService vào lúc nào?

**Đáp án:** UserDetailsService trả **dữ liệu**; sau khi provider kiểm tra credential và trạng thái, kết quả Authentication mới được tạo và đặt vào SecurityContext theo flow xác thực.

## Tài liệu tham khảo chính thức

- Spring Security — **UserDetailsService**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — **Password Storage**: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security API — **UserDetails**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html

**Ghi nhớ:** **UserDetailsService tìm account; UserDetails mang hash, trạng thái và quyền; DaoAuthenticationProvider dùng PasswordEncoder để xác minh password; Authentication ghi nhận danh tính hợp lệ; authorization quyết định request đó có được phép thực hiện hay không.** Giữ rõ ranh giới này giúp chuyển nguồn tài khoản từ in-memory sang database mà không trộn lẫn các trách nhiệm bảo mật.
