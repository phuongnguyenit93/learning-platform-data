# Trả Authentication kết quả với principal và quyền đã được xác minh

> Phạm vi: **Spring Security - authentication → Provider tùy chỉnh** (Servlet, Spring Boot 3.x / Spring Security 6.x, Java 17+). Trọng tâm là hợp đồng của `AuthenticationProvider.authenticate(...)` khi **xác thực thành công**: phải trả một đối tượng `Authentication` đáng tin cậy, có `principal` xác định từ dữ liệu server và `GrantedAuthority` đã được xác minh. Bài cũng kiểm tra trường hợp thất bại để không vô tình biến dữ liệu do client khai báo thành danh tính/quyền hợp lệ.

## 1. Vì sao giá trị trả về của AuthenticationProvider là ranh giới bảo mật?

Khi client gửi biểu mẫu tên đăng nhập và mật khẩu, `UsernamePasswordAuthenticationFilter` tạo yêu cầu xác thực có thể biểu diễn bằng:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "alice-pass");
```

Đây **chưa phải danh tính đáng tin cậy**. `request.isAuthenticated()` là `false`; username/password trong request chỉ là thông tin phía client đưa ra. Một provider tùy chỉnh phải chứng minh thông tin đăng nhập, kiểm tra trạng thái tài khoản và đọc quyền từ nguồn do server kiểm soát **trước khi** trả token được xác thực.

Một kết quả thành công cần thỏa tất cả các điều kiện:

| Thuộc tính | Đầu vào chưa tin cậy | Kết quả sau xác minh |
| --- | --- | --- |
| `isAuthenticated()` | `false` | `true`, nhưng **chỉ sau khi** bằng chứng đã được kiểm tra |
| `getPrincipal()` | Thường chỉ là username do client cung cấp | `VerifiedPrincipal`/`UserDetails` từ tài khoản đã được tìm và xác minh |
| `getCredentials()` | Mật khẩu thuần nhận từ request | `null` hoặc credential đã xóa; không đưa mật khẩu vào context/session |
| `getAuthorities()` | Không được tin các vai trò/quyền do client tự gửi | `GrantedAuthority` dựng từ roles/permissions server đã xác minh |
| `getName()` | Tên client khai báo | Danh tính nhất quán với principal đã được xác minh |
| `getDetails()` | Có thể gồm IP/session/request metadata | Thông tin phụ trợ, **không** dùng để chứng minh quyền |

**Nguyên tắc:** `isAuthenticated = true` là một khẳng định bảo mật. Ai tạo ra `Authentication` ở trạng thái này phải chịu trách nhiệm cho bằng chứng xác thực và quyền được cấp. Không được coi cờ true là thao tác "đánh dấu đã kiểm tra" nếu chưa thực sự kiểm tra.

Các kiểu `Authentication` có thể khác nhau tùy cơ chế (username/password, certificate, OAuth2...). Ở bài này, đầu vào là `UsernamePasswordAuthenticationToken` và provider trả cùng kiểu token với principal/authorities đã được xác minh.

## 2. Luồng xác thực và trách nhiệm từng thành phần

```text
Browser
  |
  | POST /login: username=alice, password=alice-pass, CSRF token
  v
UsernamePasswordAuthenticationFilter
  | tạo UsernamePasswordAuthenticationToken.unauthenticated(...)
  v
AuthenticationManager (thường là ProviderManager)
  | chọn AuthenticationProvider có supports(...) phù hợp
  v
AccountAuthenticationProvider.authenticate(request)
  | 1. Đọc username + credential
  | 2. Tra tài khoản từ nguồn server (id, passwordHash, trạng thái, roles)
  | 3. PasswordEncoder.matches(rawPassword, storedPasswordHash)
  | 4. Kiểm tra account enabled/locked/expired theo chính sách
  | 5. Dựng VerifiedPrincipal không chứa mật khẩu
  | 6. Dựng ROLE_USER/ROLE_ADMIN từ roles được lưu trên server
  '-- 7. Trả UsernamePasswordAuthenticationToken.authenticated(...)
  v
AuthenticationManager
  | nhận Authentication đã xác thực
  v
UsernamePasswordAuthenticationFilter success flow
  | áp dụng session strategy, đặt SecurityContext, lưu qua repository
  '-- success handler (redirect/response)
  v
GET /me, GET /admin ở request tiếp theo
  | authorization đọc Authentication.getAuthorities()
  '-- ALLOW/DENY theo quyền đã xác minh
```

**Phân biệt rõ trách nhiệm:**

- `AuthenticationProvider` kiểm tra bằng chứng và tạo kết quả `Authentication` đáng tin cậy. Provider tự thân **không** chịu trách nhiệm đặt `SecurityContextHolder` hay gửi cookie/session.
- `AuthenticationManager` điều phối provider. `ProviderManager` có thể hỏi nhiều provider; không phải request nào cũng thuộc về cùng một provider.
- Filter/cơ chế đăng nhập thành công nhận kết quả, thiết lập `SecurityContext` và thực hiện lưu theo cấu hình. Nếu tự viết controller login riêng thì cần tự tích hợp `SecurityContextRepository.saveContext(...)` và session strategy thích hợp.
- `AuthorizationManager` về sau sử dụng authorities của `Authentication` để quyết định cho phép truy cập. Authentication thành công không có nghĩa người dùng có mọi quyền.

### Ba kết quả hợp lệ của authenticate(...)

| Kết quả | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Trả `Authentication` đã xác thực | Provider đã chứng minh danh tính và cấp quyền từ nguồn tin cậy | Mật khẩu đúng, account enabled |
| Ném `AuthenticationException` | Đã xử lý nhưng bằng chứng không hợp lệ, hoặc trạng thái tài khoản không cho phép đăng nhập | `BadCredentialsException`, `DisabledException`, `LockedException` |
| Trả `null` | Provider **không xử lý được dạng yêu cầu này** và muốn nhường provider tiếp theo | Một token thuộc loại cơ chế khác |

Không trả `null` để biểu diễn “sai mật khẩu” trong provider có trách nhiệm xác thực username/password: nếu còn provider khác, manager có thể thử tiếp. Không trả một token `isAuthenticated=false` như kết quả “thành công nửa vời”. Với nhiều provider, một số loại lỗi có thể dẫn tới thử provider kế tiếp; vì vậy thiết kế chuỗi provider và chính sách ưu tiên là vấn đề riêng cần kiểm tra.

## 3. Principal và GrantedAuthority lấy từ đâu?

**Principal** là danh tính thực thể đã xác thực. Trong một ứng dụng, principal có thể là `UserDetails` hoặc kiểu domain riêng. Ví dụ dưới dùng một Java `record` bất biến chỉ chứa **account ID** và **username** đã đối chiếu với bản ghi server.

**Authority** là quyền đã cấp. `SimpleGrantedAuthority("ROLE_USER")` là một đối tượng quyền; nó không tự kiểm tra password. Trong cấu hình chuẩn, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` (tiền tố mặc định `ROLE_`); còn `hasAuthority("invoice:read")` kiểm tra chính xác chuỗi `invoice:read`. Hai cách diễn đạt có ngữ nghĩa khác nhau.

Ví dụ:

| Bản ghi server sau xác thực | Authority tạo ra | Kiểm tra tương ứng |
| --- | --- | --- |
| `roles = ["USER"]` | `ROLE_USER` | `hasRole("USER")` |
| `roles = ["USER", "ADMIN"]` | `ROLE_USER`, `ROLE_ADMIN` | `hasRole("ADMIN")` |
| `permissions = ["invoice:read"]` | `invoice:read` | `hasAuthority("invoice:read")` |

**Tuyệt đối không lấy quyền từ request** như `role=ADMIN`, header `X-Role: ADMIN`, JSON field `permissions` hay `authentication.getAuthorities()` của token đầu vào chưa đáng tin. Nếu hệ thống có cơ chế quyền ngoài (LDAP, IdP, IAM), provider phải xác minh tính toàn vẹn/nguồn phát và ánh xạ quyền theo policy server trước khi đưa vào kết quả.

Tránh gán principal trực tiếp bằng một entity chứa `passwordHash`/secret hoặc object mutable có thể thay đổi quyền sau xác thực. Việc dùng principal nhỏ, bất biến giúp giảm khả năng rò rỉ dữ liệu, đặc biệt khi `Authentication` được giữ trong session hoặc đưa vào log/debug.

## 4. Ví dụ Spring Boot 3 / Java 17+ đầy đủ

Ví dụ dùng form login chuẩn để thấy rõ `UsernamePasswordAuthenticationFilter → AuthenticationManager → custom provider`. Kho tài khoản in-memory chỉ là dữ liệu thực hành; có thể thay bằng repository/database/identity service của ứng dụng mà không đổi hợp đồng trả `Authentication`.

Trong ứng dụng Spring Boot 3.x đã có Gradle plugin, khai báo:

```groovy
// build.gradle - đặt trong dependencies của ứng dụng Spring Boot
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tất cả tệp Java sau dùng package `example.providerresult`.

### 4.1. Khởi động ứng dụng

**`src/main/java/example/providerresult/ProviderResultApplication.java`**

```java
package example.providerresult;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProviderResultApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProviderResultApplication.class, args);
    }
}
```

### 4.2. Kho tài khoản và dữ liệu có thẩm quyền

**`src/main/java/example/providerresult/AccountDirectory.java`**

```java
package example.providerresult;

import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

record AccountRecord(
        String id,
        String username,
        String passwordHash,
        boolean enabled,
        Set<String> roles) {
}

interface AccountDirectory {
    Optional<AccountRecord> findByUsername(String username);
}

final class InMemoryAccountDirectory implements AccountDirectory {
    private final Map<String, AccountRecord> accounts;

    InMemoryAccountDirectory(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice",
            new AccountRecord(
                "acct-101", "alice",
                encoder.encode("alice-pass"), true, Set.of("USER")),
            "admin",
            new AccountRecord(
                "acct-102", "admin",
                encoder.encode("admin-pass"), true,
                Set.of("USER", "ADMIN")),
            "disabled",
            new AccountRecord(
                "acct-103", "disabled",
                encoder.encode("disabled-pass"), false, Set.of("USER"))
        );
    }

    @Override
    public Optional<AccountRecord> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
```

Dữ liệu demo có ba account: `alice` chỉ có vai trò USER; `admin` có USER + ADMIN; `disabled` bị vô hiệu hóa. Mật khẩu băm bằng `PasswordEncoder`, không lưu plaintext vào bản ghi. Trong hệ thống thật, thay kho in-memory bằng repository tin cậy; đặt quy tắc chuẩn hóa username rõ ràng, kiểm tra account locked/expired khi có chính sách tương ứng, không trả passwordHash ra phía client.

### 4.3. Principal đã xác minh, không chứa password

**`src/main/java/example/providerresult/VerifiedPrincipal.java`**

```java
package example.providerresult;

import java.security.Principal;

public record VerifiedPrincipal(
        String accountId,
        String username) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

`VerifiedPrincipal` chứa ID ổn định và username từ `AccountRecord` mà server đã tra cứu. `getName()` nhất quán với `Authentication.getName()`. Không chứa raw password, password hash, CSRF token, session ID hoặc role claim do request tự gửi.

### 4.4. Custom AuthenticationProvider

**`src/main/java/example/providerresult/AccountAuthenticationProvider.java`**

```java
package example.providerresult;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Comparator;
import java.util.List;

public final class AccountAuthenticationProvider
        implements AuthenticationProvider {

    private final AccountDirectory directory;
    private final PasswordEncoder encoder;

    public AccountAuthenticationProvider(
            AccountDirectory directory,
            PasswordEncoder encoder) {
        this.directory = directory;
        this.encoder = encoder;
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return null; // Provider này không hỗ trợ loại token khác.
        }

        String username = request.getName();
        Object credential = request.getCredentials();
        String rawPassword = credential instanceof String value ? value : null;

        if (username == null || username.isBlank()
                || rawPassword == null || rawPassword.isEmpty()) {
            throw new BadCredentialsException("Invalid credentials");
        }

        AccountRecord account = directory.findByUsername(username)
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid credentials"));

        // Kiểm tra mật khẩu trên passwordHash do server lưu.
        // KHÔNG so sánh hai chuỗi plaintext hoặc tự viết thuật toán hash.
        if (!encoder.matches(rawPassword, account.passwordHash())) {
            throw new BadCredentialsException("Invalid credentials");
        }

        if (!account.enabled()) {
            throw new DisabledException("Account disabled");
        }

        // Chỉ sử dụng danh sách role lấy từ bản ghi server đã xác minh.
        List<SimpleGrantedAuthority> verifiedAuthorities =
            account.roles().stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .sorted(Comparator.comparing(
                    SimpleGrantedAuthority::getAuthority))
                .toList();

        VerifiedPrincipal principal = new VerifiedPrincipal(
            account.id(), account.username());

        // Factory ba tham số tạo token isAuthenticated() == true.
        // Chỉ được gọi SAU khi xác minh credential/trạng thái/quyền.
        return UsernamePasswordAuthenticationToken.authenticated(
            principal,
            null, // Không giữ rawPassword trong kết quả.
            verifiedAuthorities);
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }
}
```

**Giải thích từng lựa chọn:**

1. `supports(...)` chỉ công bố loại request có thể xử lý. `authenticate(...)` vẫn phòng vệ với token khác bằng cách trả `null`. Provider chỉ chứng minh username/password, không nhận mọi loại `Authentication` một cách mù quáng.
2. `request.getName()` và `request.getCredentials()` là dữ liệu đầu vào. Provider dùng chúng để **tìm và kiểm tra** account, không coi chúng là kết quả đáng tin ngay từ đầu.
3. `PasswordEncoder.matches(raw, hash)` kiểm tra mật khẩu, tránh so sánh plaintext hoặc tính lại BCrypt hash rồi so sánh chuỗi. BCrypt có salt nên hai lần `encode(...)` thường tạo hash khác nhau cho cùng password.
4. `account.enabled()` được kiểm tra trước khi tạo token xác thực. Ví dụ có một trạng thái enabled; production thường còn locked, account expired, credential expired, MFA/step-up và các quyết định chính sách khác.
5. `verifiedAuthorities` sinh từ `account.roles()` phía server. Không copy `request.getAuthorities()`; không nhận quyền được khai báo trong form/cookie/header.
6. `VerifiedPrincipal` dùng ID/username của `account` đã tìm được, không chỉ echo username do người dùng gõ. Mật khẩu và passwordHash không trở thành thuộc tính của principal.
7. Factory `UsernamePasswordAuthenticationToken.authenticated(principal, null, authorities)` trả token đã xác thực. Giá trị `null` ở credentials tránh giữ raw password trong kết quả. `ProviderManager` còn có cơ chế xóa credentials sau xác thực, nhưng nên tránh đưa dữ liệu bí mật vào principal ngay từ đầu.
8. Ví dụ cố ý không sao chép `request.getDetails()`. Nếu cần IP, session ID hoặc metadata cho audit, hãy đánh giá nguồn và mức độ nhạy cảm; `details` là metadata phụ trợ, không phải bằng chứng cấp quyền.

**Lưu ý về xác minh tài khoản không tồn tại:** ví dụ ném cùng thông báo `Invalid credentials` khi username không tồn tại hoặc password sai. Trong production, chênh lệch thời gian giữa hai nhánh có thể làm lộ việc username có tồn tại; hãy cân nhắc dummy password hash verification, rate limiting, monitoring và chính sách chống enumeration. Không phơi bày nguyên nhân nội bộ qua response login.

### 4.5. Đăng ký provider vào SecurityFilterChain

**`src/main/java/example/providerresult/SecurityConfig.java`**

```java
package example.providerresult;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountDirectory accountDirectory(PasswordEncoder encoder) {
        return new InMemoryAccountDirectory(encoder);
    }

    @Bean
    AccountAuthenticationProvider accountAuthenticationProvider(
            AccountDirectory accounts, PasswordEncoder encoder) {
        return new AccountAuthenticationProvider(accounts, encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountAuthenticationProvider provider)
            throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll());

        // CSRF được giữ mặc định cho form login dùng session cookie.
        return http.build();
    }
}
```

`http.authenticationProvider(provider)` đưa custom provider vào luồng của chain này. `formLogin(...)` dùng cơ chế filter, session strategy, context persistence và success/failure handlers của Spring Security; provider chỉ trả đối tượng xác thực. Trong ứng dụng có nhiều provider/chain, phải kiểm tra thứ tự và phạm vi registration để không vô tình tạo cơ chế xác thực khác với ý định.

**`src/main/java/example/providerresult/IdentityController.java`**

```java
package example.providerresult;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        VerifiedPrincipal user =
            (VerifiedPrincipal) authentication.getPrincipal();
        return user.accountId() + ":" + user.getName();
    }

    @GetMapping("/admin")
    String adminArea() {
        return "admin-area";
    }
}
```

Sau khi login thành công với `alice`, `GET /me` trả:

```text
acct-101:alice
```

`GET /admin` trả `403` cho `alice`, nhưng thành công với tài khoản `admin` vì chỉ `admin` có authority `ROLE_ADMIN` đã được xác minh. Login sai password không được nhận một token "ít quyền": đó là **xác thực thất bại**.

## 5. Kiểm thử: vừa kiểm tra object trả về, vừa kiểm tra đường đi HTTP

Test trực tiếp `AuthenticationProvider` kiểm tra đúng hợp đồng trả `Authentication`. Test tích hợp `MockMvc` xác minh rằng form login tiêu thụ kết quả này và authorization thực sự dùng đúng quyền.

**`src/test/java/example/providerresult/AccountAuthenticationProviderTest.java`**

```java
package example.providerresult;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import jakarta.servlet.http.HttpSession;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AccountAuthenticationProviderTest {

    @Autowired
    AccountAuthenticationProvider provider;

    @Autowired
    MockMvc mvc;

    private static Set<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void successReturnsVerifiedPrincipalAndServerAuthorities() {
        Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice-pass");

        assertFalse(input.isAuthenticated());

        Authentication result = provider.authenticate(input);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertInstanceOf(VerifiedPrincipal.class, result.getPrincipal());
        VerifiedPrincipal principal = (VerifiedPrincipal) result.getPrincipal();
        assertEquals("acct-101", principal.accountId());
        assertEquals("alice", principal.username());
        assertEquals("alice", result.getName());
        assertNull(result.getCredentials());
        assertEquals(Set.of("ROLE_USER"), authorities(result));
    }

    @Test
    void rejectsWrongPasswordAndUnknownAccount() {
        assertThrows(BadCredentialsException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong")));

        assertThrows(BadCredentialsException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "no-such-user", "any-password")));
    }

    @Test
    void disabledAccountDoesNotReceiveAuthenticatedResult() {
        assertThrows(DisabledException.class, () ->
            provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "disabled", "disabled-pass")));
    }

    @Test
    void inboundClaimedAuthorityIsNotTrusted() {
        // Cố tình tạo token giả mạo CHỈ trong unit test.
        // Ứng dụng không được chấp nhận token này từ request.
        Authentication forged = new UsernamePasswordAuthenticationToken(
            "alice", "alice-pass",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

        Authentication result = provider.authenticate(forged);

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals(Set.of("ROLE_USER"), authorities(result));
        assertFalse(authorities(result).contains("ROLE_ADMIN"));
    }

    @Test
    void supportsOnlyUsernamePasswordTokens() {
        assertTrue(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(
            AnonymousAuthenticationToken.class));
    }

    @Test
    void formLoginPersistsTrustedPrincipalAndRejectsAdminAccess()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession rawSession = login.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("acct-101:alice"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void verifiedAdminRolePermitsAdminResource() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "admin")
                .param("password", "admin-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("admin"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-area"));
    }

    @Test
    void csrfStillAppliesToFormLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy từ thư mục ứng dụng ví dụ có Gradle wrapper:

```bash
./gradlew test --tests example.providerresult.AccountAuthenticationProviderTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Test suite trên có **8 phương thức `@Test`**. Nếu cấu hình và môi trường đúng, tất cả đều phải pass; đây là hành vi được thiết kế trong ví dụ, **không phải kết quả đã thực thi**.

### Tại sao cần cả hai loại test?

- Unit-style test gọi `provider.authenticate(...)` kiểm tra **object trả về**: `isAuthenticated()`, kiểu principal, ID/name, credentials `null`, authority chính xác. Nó không cần thực hiện HTTP request.
- Negative test bảo đảm sai mật khẩu, account không tồn tại, account disabled không thể nhận token xác thực. Test tạo token "giả mạo quyền" chỉ là tình huống unit test để kiểm chứng provider **không sao chép** quyền đầu vào.
- MockMvc test thực hiện `POST /login` với mật khẩu và CSRF token, rồi dùng session vừa được tạo để gọi `GET /me` và `GET /admin`. Việc `alice` bị `403` ở `/admin` còn `admin` nhận `200` chứng minh authorization nhận đúng authority sau authentication.
- `authenticated().withUsername(...)` là matcher quan sát kết quả login thật. **Không dùng `@WithMockUser` để chứng minh luồng provider**, vì tiện ích này đưa user giả vào SecurityContext và bỏ qua bước provider xác minh credential.

### Ranh giới của các kiểm thử trên

Đây là ví dụ trong Spring MVC + Spring Security, không mô phỏng đầy đủ session store phân tán, cookie browser thật, reverse proxy hoặc luồng MFA. MockMvc test cho thấy hành vi Spring Security ở server giả lập; cần kiểm thử HTTP end-to-end khi triển khai. Khi dùng repository/database thực, bổ sung test rằng roles vừa thay đổi trong nguồn có thẩm quyền được áp dụng theo chính sách (reauthentication, refresh hoặc thu hồi session).

## 6. Các lỗi nghiêm trọng khi tạo Authentication kết quả

| Sai lầm | Vì sao nguy hiểm hoặc không đúng | Cách làm |
| --- | --- | --- |
| `return UsernamePasswordAuthenticationToken.authenticated(request.getPrincipal(), request.getCredentials(), request.getAuthorities());` ngay khi nhận request | “Hợp thức hóa” username, password và quyền chưa xác minh | Chỉ tạo token authenticated **sau** khi đối chiếu credential và quyền server |
| Tự đặt `isAuthenticated=true` chỉ vì tìm thấy username | Biết username tồn tại không chứng minh người gửi là chủ tài khoản | Kiểm tra password/MFA/chính sách xác thực trước |
| Copy `ROLE_ADMIN` từ JSON, header hoặc inbound token | Client tự nâng quyền | Lấy roles/permissions từ database/IdP đáng tin, áp policy cấp quyền |
| Dùng `UsernamePasswordAuthenticationToken.unauthenticated(...)` làm kết quả thành công | Token vẫn là yêu cầu chưa xác thực; filter/authorization không thể coi là login hoàn thành | Dùng factory `authenticated(...)` sau xác minh |
| Trả một entity chứa `passwordHash` làm principal | Có thể giữ bí mật trong SecurityContext/session/log | Tạo principal tối giản, bất biến, không chứa credential |
| Trả raw password trong `getCredentials()` | Credential có thể bị giữ trong bộ nhớ, session hoặc log | Đặt `null` trong token thành công, dùng khả năng erase credential thích hợp |
| Trả `null` khi password sai | ProviderManager có thể thử provider khác; nhầm “không hỗ trợ” với “sai bằng chứng” | Ném `BadCredentialsException` cho thất bại mà provider đã xử lý |
| Ném `BadCredentialsException` cho mọi loại token | Chặn các cơ chế khác dù provider không có trách nhiệm | `supports(...)` chính xác; trả `null` khi loại token ngoài phạm vi |
| Gán mọi account vào `ROLE_ADMIN` để làm đơn giản demo | Authorization không còn kiểm tra đúng phân quyền | Mapping authority từ dữ liệu đã được xác minh và test `403`/`200` |
| Dùng `hasRole("ROLE_ADMIN")` như chuỗi đã có prefix | Mặc định `hasRole("ADMIN")` tự gắn `ROLE_` và có thể gây nhầm/lỗi cấu hình | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Trong provider tự ghi `SecurityContextHolder` rồi nghĩ đã persist | Provider có thể bị gọi ngoài luồng HTTP; context chỉ gắn với request/thread | Để login mechanism làm; custom controller phải gọi saveContext đúng cách |
| Ghi raw password, hash, session ID vào debug logs | Lộ credential, có nguy cơ chiếm tài khoản/session | Log audit tối thiểu, không chứa secrets; redaction ở log/tracing |

### Có cần giữ request details trong Authentication trả về?

Trong một số flow, `request.getDetails()` chứa `WebAuthenticationDetails` như địa chỉ remote và session ID. Nếu chính sách cần nó cho audit, có thể cân nhắc `result.setDetails(request.getDetails())` với type `UsernamePasswordAuthenticationToken`. Nhưng **details không được dùng làm authority hay principal**, và không nên vô tình đưa session ID, credential hoặc thông tin nhạy cảm vào log. Ví dụ cố ý bỏ qua để nhấn mạnh principal và quyền đã được xác minh.

### Đổi quyền sau khi đăng nhập thì sao?

`Authentication.getAuthorities()` là một snapshot quyền tại thời điểm tạo token. Nếu quyền của người dùng thay đổi trong database sau login, session đang hoạt động có thể vẫn giữ quyền cũ. Điều đó **không** chứng minh provider đã sai tại thời điểm login; ứng dụng cần cơ chế rõ ràng để refresh, reauthenticate, thu hồi session hoặc kiểm tra quyền động tại thời điểm truy cập. Không âm thầm dùng quyền từ client để “cập nhật”.

### Password hash và dấu hiệu timing

`PasswordEncoder.matches(raw, encoded)` là API kiểm tra password trong Spring Security. Không so sánh raw password với stored hash bằng `equals`; không gọi `encoder.encode(raw).equals(storedHash)` với BCrypt vì hash có salt. Với username không tồn tại, ví dụ trả cùng thông điệp `Invalid credentials` nhưng chưa cân bằng thời gian xử lý; hệ thống thật cần đánh giá rủi ro account enumeration, dummy hash verification và rate limiting.

## 7. Cách quan sát khi chạy ứng dụng

Với ứng dụng local đã chạy trên `http://localhost:8080`, mở `/login` trong trình duyệt. Nhập `alice` / `alice-pass` rồi truy cập `/me`. Kết quả là `acct-101:alice`; truy cập `/admin` bị từ chối. Đăng xuất, đăng nhập bằng `admin` / `admin-pass` rồi vào `/admin`, kết quả là `admin-area`.

Trong DevTools Network, lưu ý không thu thập hoặc chia sẻ password, CSRF token và session cookie thật. Trên production luôn dùng HTTPS và cấu hình cookie/session bảo mật; demo localhost chỉ giúp quan sát logic provider.

Cách đọc log/debug an toàn khi cần khảo sát:

```text
Before: UsernamePasswordAuthenticationToken
        authenticated=false
        principal="alice" (user input)
        authorities=[]
After:  UsernamePasswordAuthenticationToken
        authenticated=true
        principal=VerifiedPrincipal(accountId=acct-101, username=alice)
        credentials=null
        authorities=[ROLE_USER]
```

Đây là **mẫu diễn giải trạng thái**, không phải stdout/log tự động được in bởi mã ví dụ. Không in actual request token có credentials; dùng các assert trong test để kiểm chứng.

## 8. Checklist tự đánh giá

- [ ] `supports(...)` chỉ nhận loại `Authentication` mà provider thực sự xử lý.
- [ ] Bản ghi account được lấy từ nguồn do server kiểm soát; không chỉ tin username do client gửi.
- [ ] Credential được xác minh bằng API thích hợp (`PasswordEncoder.matches` trong ví dụ).
- [ ] Trạng thái account được kiểm tra trước khi tạo token xác thực.
- [ ] `Authentication` trả về có `isAuthenticated() == true` **chỉ khi** xác minh thành công.
- [ ] `principal` chứa danh tính đúng bản ghi được kiểm tra; không chứa password/hash.
- [ ] `getCredentials() == null` sau khi xác thực thành công trong ví dụ.
- [ ] `getAuthorities()` chỉ chứa authority được ánh xạ từ nguồn tin cậy, dùng prefix đúng quy tắc.
- [ ] Sai password, account không tồn tại hoặc bị disabled không trả token thành công.
- [ ] Token đầu vào có claim quyền giả mạo không thể ảnh hưởng authorities kết quả.
- [ ] Form login thực sự đi qua provider; request sau được authorize theo quyền đã kiểm chứng.
- [ ] Đã phân biệt trách nhiệm `AuthenticationProvider` với `SecurityContextHolder`, `SecurityContextRepository` và session persistence.
- [ ] Đã kiểm thử các trường hợp 403/200 theo quyền, và giữ CSRF cho form login stateful.

### Tài liệu gốc để đối chiếu

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — Authorization Architecture / GrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
