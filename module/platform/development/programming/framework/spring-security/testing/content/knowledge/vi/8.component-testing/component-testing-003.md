# UserDetailsService với tài khoản tồn tại, thiếu hoặc bị vô hiệu hóa

## 1. Bối cảnh và mục tiêu

Một chức năng đăng nhập bằng tên người dùng và mật khẩu thường có ít nhất ba trường hợp cần phân biệt:

1. **Tài khoản tồn tại, đang hoạt động:** hệ thống tải đúng người dùng để kiểm tra mật khẩu và quyền.
2. **Tài khoản không tồn tại:** hệ thống không tìm thấy người dùng và phải từ chối xác thực mà không làm lộ thông tin nhạy cảm.
3. **Tài khoản bị vô hiệu hóa:** dữ liệu tài khoản vẫn tồn tại nhưng người dùng không được phép đăng nhập.

Trong Spring Security, `UserDetailsService` chịu trách nhiệm **tra cứu thông tin người dùng**. Nó không phải thành phần trực tiếp so khớp mật khẩu hoặc đưa ra mã HTTP. Sự phân biệt này giúp viết kiểm thử đúng tầng và phát hiện chính xác nguyên nhân khi đăng nhập thất bại.

Bài thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Phạm vi mô-đun là kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và các cơ chế JWT/OAuth2/OIDC giả lập. Trong bài này, trọng tâm là tra cứu tài khoản qua `UserDetailsService`, kết hợp kiểm thử xác thực thật bằng `DaoAuthenticationProvider` và sau đó liên hệ với HTTP.

Sau bài học, bạn sẽ biết cách:

- Kiểm thử `loadUserByUsername(...)` cho tài khoản tồn tại, không tồn tại và bị vô hiệu hóa.
- Phân biệt `UsernameNotFoundException` ở tầng tra cứu với `BadCredentialsException` ở tầng xác thực.
- Giải thích vì sao tài khoản bị vô hiệu hóa vẫn có thể được `UserDetailsService` trả về nhưng bị `DaoAuthenticationProvider` từ chối.
- Sử dụng JUnit 5, Mockito và AssertJ để kiểm thử một `UserDetailsService` tùy chỉnh mà không cần cơ sở dữ liệu thật.
- Dùng `InMemoryUserDetailsManager` và `PasswordEncoder` thật để xác minh luồng đăng nhập, sau đó kiểm tra phản hồi HTTP trong `MockMvc` hoặc `WebTestClient`.

## 2. Ranh giới trách nhiệm của UserDetailsService

Giao diện `org.springframework.security.core.userdetails.UserDetailsService` có một phương thức:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

Khi thành công, phương thức trả về `UserDetails` mô tả tài khoản đã tìm thấy. Những thông tin liên quan đến bảo mật bao gồm:

| Thuộc tính/phương thức | Ý nghĩa | Điều nên kiểm thử |
| --- | --- | --- |
| `getUsername()` | Tên đăng nhập của tài khoản | Đúng bản ghi được tải |
| `getPassword()` | Mật khẩu đã mã hóa một chiều, nếu dùng xác thực mật khẩu | Đọc đúng hash đã lưu; không trả mật khẩu thô |
| `getAuthorities()` | Danh sách quyền `GrantedAuthority` | Quyền/role không bị thiếu, thừa hoặc map sai |
| `isEnabled()` | Tài khoản có được bật hay không | Tài khoản bị vô hiệu hóa trả `false` |
| `isAccountNonLocked()` | Tài khoản có bị khóa hay không | Tài khoản bị khóa trả `false` |
| `isAccountNonExpired()` | Tài khoản có còn hiệu lực hay không | Trả đúng trạng thái hết hạn tài khoản |
| `isCredentialsNonExpired()` | Thông tin xác thực có còn hiệu lực hay không | Phản ánh đúng trạng thái hết hạn credentials |

Đầu vào `username` là khóa dùng để tra cứu, không phải bằng chứng xác thực thành công. Riêng `UserDetailsService` **không nhận mật khẩu thô làm tham số**, vì vậy nó không thể kết luận mật khẩu người dùng nhập là đúng hay sai.

### Luồng xác thực username/password

~~~mermaid
flowchart TD
    A["Yêu cầu đăng nhập: username + password"] --> B["Filter tạo UsernamePasswordAuthenticationToken chưa xác thực"]
    B --> C["AuthenticationManager / ProviderManager"]
    C --> D["DaoAuthenticationProvider"]
    D --> E["UserDetailsService.loadUserByUsername(username)"]
    E --> F{"Có tài khoản?"}
    F -- "Không" --> G["Ném UsernameNotFoundException"]
    G --> H["Thông thường che giấu thành BadCredentialsException"]
    F -- "Có" --> I["Trả UserDetails kèm trạng thái tài khoản"]
    I --> J{"enabled, unlocked, non-expired?"}
    J -- "Không" --> K["Ném ngoại lệ trạng thái, ví dụ DisabledException"]
    J -- "Có" --> L{"PasswordEncoder.matches?"}
    L -- "Không" --> H
    L -- "Có" --> M["Trả Authentication đã xác thực với authorities"]
    M --> N["Filter và SecurityContext tiếp tục xử lý HTTP"]
~~~

Đây là luồng điển hình của `DaoAuthenticationProvider` cho ứng dụng Servlet. Sơ đồ minh họa các kiểm tra trạng thái chính; bước kiểm tra credentials hết hạn cũng có thể làm xác thực thất bại. Những ứng dụng dùng provider tùy chỉnh hoặc cơ chế xác thực khác có thể có đường xử lý riêng.

**Điểm dễ nhầm:** `UserDetailsService` nên trả về `UserDetails` cho tài khoản bị vô hiệu hóa, trong đó `isEnabled() == false`. Nó không cần tự ném `DisabledException`; việc từ chối theo trạng thái tài khoản thường do `DaoAuthenticationProvider` thực hiện sau khi tải người dùng.

## 3. Ma trận hành vi mong đợi

Một kịch bản cần được quan sát ở hai tầng khác nhau: **tra cứu tài khoản** và **xác thực thông tin đăng nhập**.

| Kịch bản | Khi gọi trực tiếp UserDetailsService | Khi đăng nhập qua DaoAuthenticationProvider |
| --- | --- | --- |
| `lan` tồn tại, bật, mật khẩu đúng | Trả `UserDetails` có `isEnabled() == true` và authorities đúng | Trả `Authentication` đã xác thực |
| `lan` tồn tại, bật, mật khẩu sai | Vẫn trả `UserDetails`; tầng tra cứu không kiểm tra mật khẩu | Ném `BadCredentialsException` |
| `unknown` không tồn tại | Ném `UsernameNotFoundException` | Theo mặc định ném `BadCredentialsException` |
| `disabled` tồn tại nhưng bị vô hiệu hóa | Trả `UserDetails` với `isEnabled() == false` | Ném `DisabledException` |
| Tài khoản bị khóa | Trả `UserDetails` với `isAccountNonLocked() == false` | Ném `LockedException` |
| Tài khoản hết hạn | Trả `UserDetails` với `isAccountNonExpired() == false` | Ném `AccountExpiredException` |

`DaoAuthenticationProvider` mặc định bật `hideUserNotFoundExceptions`, nên thông báo lỗi từ người dùng không tồn tại được che giấu thành `BadCredentialsException`. Mục đích là tránh đưa ra tín hiệu dễ phân biệt giữa "tên người dùng không tồn tại" và "mật khẩu sai". Cần nhớ các tín hiệu khác, như thời gian đáp ứng hoặc nội dung phản hồi HTTP, cũng phải được xem xét khi thiết kế chức năng đăng nhập.

## 4. Ví dụ UserDetailsService tùy chỉnh

Giả sử bảng tài khoản chứa tên đăng nhập, mật khẩu đã băm, trạng thái `enabled`, trạng thái `locked` và danh sách authority. Thành phần sau đọc bản ghi từ một repository rồi chuyển thành `UserDetails`.

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

record AccountRecord(
        String username,
        String passwordHash,
        boolean enabled,
        boolean locked,
        List<String> authorities) {
}

interface AccountRepository {
    Optional<AccountRecord> findByUsername(String username);
}

@Service
class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord account = repository.findByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .authorities(account.authorities().toArray(String[]::new))
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .build();
    }
}
~~~

Đây là một ví dụ Java đơn giản hóa: trong ứng dụng thật cần có triển khai `AccountRepository` và nơi lưu các bản ghi tương ứng. `authorities` là các chuỗi quyền đã được xác thực ở nguồn dữ liệu, chẳng hạn `ROLE_READER`; không nên lấy quyền trực tiếp từ đầu vào đăng nhập. `passwordHash` phải được lưu bằng bộ mã hóa mật khẩu phù hợp với `PasswordEncoder` của ứng dụng, không phải mật khẩu thô.

Với tên đăng nhập `lan` có `enabled=true`, phương thức trả về `UserDetails` đã nạp đúng dữ liệu. Với `unknown`, repository trả `Optional.empty()` và service ném `UsernameNotFoundException`. Với `disabled` có `enabled=false`, service vẫn trả một `UserDetails` hợp lệ về mặt dữ liệu nhưng đánh dấu tài khoản không được phép xác thực.

**Không viết logic kiểm tra mật khẩu hoặc ghi SecurityContext trong service này.** Những trách nhiệm đó thuộc về các thành phần khác trong chuỗi bảo mật.

## 5. Kiểm thử ba trạng thái bằng JUnit 5, Mockito và AssertJ

Ở tầng component, ta có thể mock repository để kiểm tra chính xác việc chuyển từ dữ liệu lưu trữ sang `UserDetails`. Nhờ đó các ca test chạy độc lập với database, HTTP filter và trạng thái session.

Ví dụ sau dùng chính các lớp `AccountRecord`, `AccountRepository` và `AccountUserDetailsService` ở mục 4; đặt lớp test trong cùng package để sử dụng các kiểu có phạm vi package-private.

~~~java
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AccountUserDetailsServiceTest {

    private AccountRepository repository;
    private UserDetailsService service;

    @BeforeEach
    void setUp() {
        repository = mock(AccountRepository.class);
        service = new AccountUserDetailsService(repository);
    }

    @Test
    void existingEnabledAccountReturnsUserDetailsWithCorrectAuthorities() {
        when(repository.findByUsername("lan")).thenReturn(Optional.of(
                new AccountRecord(
                        "lan", "stored-hash", true, false,
                        List.of("ROLE_READER"))));

        UserDetails result = service.loadUserByUsername("lan");

        assertThat(result.getUsername()).isEqualTo("lan");
        assertThat(result.getPassword()).isEqualTo("stored-hash");
        assertThat(result.isEnabled()).isTrue();
        assertThat(result.isAccountNonLocked()).isTrue();
        assertThat(result.getAuthorities())
                .extracting(authority -> authority.getAuthority())
                .containsExactly("ROLE_READER");
        verify(repository).findByUsername("lan");
    }

    @Test
    void missingAccountThrowsUsernameNotFoundException() {
        when(repository.findByUsername("unknown"))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.loadUserByUsername("unknown"))
                .isInstanceOf(UsernameNotFoundException.class);

        verify(repository).findByUsername("unknown");
    }

    @Test
    void disabledAccountIsLoadedWithEnabledFlagFalse() {
        when(repository.findByUsername("disabled")).thenReturn(Optional.of(
                new AccountRecord(
                        "disabled", "stored-hash", false, false,
                        List.of("ROLE_READER"))));

        UserDetails result = service.loadUserByUsername("disabled");

        assertThat(result.getUsername()).isEqualTo("disabled");
        assertThat(result.isEnabled()).isFalse();
        assertThat(result.isAccountNonLocked()).isTrue();
        verify(repository).findByUsername("disabled");
    }
}
~~~

### Vì sao các assertion này có giá trị?

**Tài khoản tồn tại:** Chỉ khẳng định `result != null` là chưa đủ. Một service có thể trả đúng username nhưng sai password hash, đánh dấu nhầm `enabled` hoặc gán thừa quyền. Test kiểm tra cả danh tính, dữ liệu phục vụ xác thực và authorities.

**Tài khoản không tồn tại:** Service phải phát tín hiệu rõ ràng bằng `UsernameNotFoundException`. Không nên trả `null` hay tự tạo một người dùng mặc định để lấp chỗ trống, vì các hành vi đó có thể làm lệch chuỗi xác thực.

**Tài khoản bị vô hiệu hóa:** Ca kiểm thử khẳng định service **vẫn tải tài khoản** và giữ đúng cờ `enabled=false`. Nếu test mong service trực tiếp ném `DisabledException`, nó đang gộp trách nhiệm tra cứu với trách nhiệm kiểm tra trạng thái ở provider.

Chuỗi `"stored-hash"` ở đây là dữ liệu giả nhằm kiểm tra ánh xạ trường, không dùng để xác thực mật khẩu. Bài test này **không chứng minh** BCrypt, `PasswordEncoder.matches(...)` hoặc HTTP login hoạt động.

## 6. Kiểm chứng từ UserDetailsService đến DaoAuthenticationProvider

Tầng tiếp theo sử dụng `UserDetailsService` trong một provider thật. `InMemoryUserDetailsManager` là triển khai tiện lợi cho mục đích này vì không phụ thuộc database, nhưng vẫn cho phép `DaoAuthenticationProvider` đọc người dùng, kiểm tra trạng thái và so khớp mật khẩu BCrypt.

Các dependency thường dùng trong dự án Spring Boot gồm `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`; hai dependency cuối thường có scope `test`. Mã kiểm thử dưới đây dùng JUnit/AssertJ và Spring Security Core, không cần khởi động Spring Boot context.

~~~java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AccountAuthenticationComponentTest {

    private ProviderManager manager;

    @BeforeEach
    void setUp() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("correct-password"))
                        .roles("READER")
                        .build(),
                User.withUsername("disabled")
                        .password(encoder.encode("correct-password"))
                        .roles("READER")
                        .disabled(true)
                        .build());

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        manager = new ProviderManager(List.of(provider));
    }

    private Authentication login(String username, String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));
    }

    @Test
    void enabledUserWithCorrectPasswordCanAuthenticate() {
        Authentication result = login("lan", "correct-password");

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getAuthorities())
                .extracting(authority -> authority.getAuthority())
                .containsExactly("ROLE_READER");
    }

    @Test
    void unknownUserIsRejectedAsBadCredentialsByDefault() {
        assertThatThrownBy(
                () -> login("unknown", "correct-password"))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void disabledUserIsRejectedEvenWithCorrectPassword() {
        assertThatThrownBy(
                () -> login("disabled", "correct-password"))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void existingUserWithIncorrectPasswordIsRejected() {
        assertThatThrownBy(
                () -> login("lan", "wrong-password"))
                .isInstanceOf(BadCredentialsException.class);
    }
}
~~~

`UsernamePasswordAuthenticationToken.unauthenticated(...)` biểu diễn dữ liệu đăng nhập chưa được tin cậy. `ProviderManager` gọi `DaoAuthenticationProvider`, provider dùng `UserDetailsService` và `PasswordEncoder` để xác thực.

Điểm cần phân biệt giữa hai tầng:

- Với `service.loadUserByUsername("unknown")`, hợp đồng `UserDetailsService` yêu cầu ném `UsernameNotFoundException`.
- Với `manager.authenticate(...)` cho username đó, `DaoAuthenticationProvider` mặc định che giấu trường hợp không tồn tại bằng `BadCredentialsException`.
- Với `service.loadUserByUsername("disabled")`, dữ liệu người dùng vẫn được trả về và `isEnabled()` là `false`.
- Với `manager.authenticate(...)` cho tài khoản đó, bước kiểm tra trạng thái từ chối yêu cầu bằng `DisabledException`, ngay cả khi mật khẩu đúng.

> **Lưu ý phiên bản:** Ví dụ dùng constructor `DaoAuthenticationProvider(UserDetailsService)` của các phiên bản Spring Security hiện đại. Nếu dự án dùng phiên bản cũ hơn, phần khởi tạo provider có thể cần điều chỉnh theo API hiện có; các hợp đồng kiểm thử chính vẫn giữ nguyên.

## 7. Kiểm thử hành vi HTTP với spring-security-test

Kiểm thử thành phần ở các mục trên đã kiểm tra phần tra cứu người dùng và xác thực mật khẩu. Nhưng nó **chưa** đảm bảo một endpoint thực sự chạy qua chuỗi filter bảo mật hoặc trả đúng HTTP status.

Với ứng dụng Servlet đã cấu hình HTTP Basic, `MockMvc` giúp đưa request qua bộ lọc bảo mật. Giả sử có endpoint `/api/me` yêu cầu đăng nhập, `SecurityFilterChain` bật HTTP Basic và test context cấu hình cùng các tài khoản trong ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountHttpSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void existingUserCanAccessProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/me")
                        .with(httpBasic("lan", "correct-password")))
                .andExpect(status().isOk());
    }

    @Test
    void unknownUserCannotAuthenticate() throws Exception {
        mockMvc.perform(get("/api/me")
                        .with(httpBasic("unknown", "correct-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledUserCannotAuthenticate() throws Exception {
        mockMvc.perform(get("/api/me")
                        .with(httpBasic("disabled", "correct-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là **mẫu tích hợp**, cần cung cấp endpoint, test users và cấu hình security đúng như giả định. Với HTTP Basic thông thường, người dùng không tồn tại và tài khoản bị vô hiệu hóa đều không được xác thực nên có thể cùng nhận `401 Unauthorized`. Không nên suy luận loại ngoại lệ nội bộ chỉ từ HTTP status; muốn kiểm tra chính xác `DisabledException` hãy dùng test provider ở mục 6.

Với form login, `AuthenticationEntryPoint` hoặc `AuthenticationFailureHandler` tùy chỉnh, ứng dụng có thể chuyển hướng hoặc trả cấu trúc lỗi khác. Kiểm thử cần dựa trên hợp đồng HTTP thực tế. Nếu endpoint trả `403 Forbidden` khi đã xác thực nhưng thiếu quyền, đó là bài kiểm tra *authorization*, không phải bài kiểm tra `UserDetailsService`.

### @WithMockUser, @WithUserDetails và SecurityContext

| Công cụ | Hành vi | Kiểm tra được điều gì? |
| --- | --- | --- |
| `@WithMockUser(username = "lan", roles = "READER")` | Tạo `Authentication` giả lập trong `SecurityContext` | Phân quyền khi đã có principal/authority; **không gọi UserDetailsService để tìm tài khoản** |
| `@WithUserDetails("lan")` | Dùng bean `UserDetailsService` của test context để tải người dùng và tạo `SecurityContext` | Có thể phát hiện tên người dùng không được service tìm thấy; **không kiểm tra mật khẩu qua provider** |
| `httpBasic("lan", "correct-password")` | Gửi header HTTP Basic để filter xử lý | Có thể kiểm tra cả `AuthenticationManager` và provider thực **nếu test context cấu hình đúng** |

`@WithUserDetails` có thể tải một tài khoản `disabled` và đặt `Authentication` vào test `SecurityContext` mà không đi qua bước kiểm tra `isEnabled()` của `DaoAuthenticationProvider`. Vì vậy test dùng annotation này không đủ để khẳng định tài khoản bị vô hiệu hóa không đăng nhập được. Muốn chứng minh quy tắc chặn đăng nhập, hãy đi qua provider hoặc filter thật.

## 8. Giới hạn với Reactive, JWT, OAuth2 và OIDC

Trong **Spring WebFlux**, hợp đồng tương ứng cho việc tải người dùng là `ReactiveUserDetailsService`, dùng `Mono<UserDetails>` thay vì trả trực tiếp `UserDetails`. Một triển khai `ReactiveUserDetailsService` thường phát ra dữ liệu người dùng khi có tài khoản và `Mono.empty()` khi không tìm thấy; các bước xác thực tiếp theo do cơ chế Reactive đảm nhận. Không dùng `DaoAuthenticationProvider` của Servlet như thể nó là `ReactiveAuthenticationManager`.

Với một ứng dụng Reactive có cấu hình HTTP Basic và endpoint `/api/me` yêu cầu đăng nhập, kiểm thử ở tầng HTTP bằng `WebTestClient` có thể viết:

~~~java
webTestClient.get()
        .uri("/api/me")
        .headers(headers ->
                headers.setBasicAuth("disabled", "correct-password"))
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đây là đoạn nằm trong một test đã có `webTestClient` liên kết với ứng dụng và người dùng `disabled` đã được cấu hình. Khi kiểm thử Reactive, cần phân biệt test `ReactiveUserDetailsService`, test `ReactiveAuthenticationManager` và test filter HTTP, tương tự cách phân tầng trong Servlet.

Với **JWT**, việc xác thực token trong resource server thường dựa trên `JwtDecoder` và các validator, không dùng `UserDetailsService` truyền thống như luồng username/password (trừ khi ứng dụng chủ động bổ sung bước tra cứu tài khoản). Tiện ích `jwt()` trong `spring-security-test` mô phỏng người dùng/token cho kiểm thử phân quyền; nó không xác minh chữ ký JWT thật. Với **OAuth2 Login/OIDC**, `oauth2Login()` và `oidcLogin()` cũng tạo ngữ cảnh đã đăng nhập để kiểm tra hành vi ứng dụng; không chứng minh luồng redirect, callback hay xác thực từ nhà cung cấp danh tính hoạt động đầy đủ.

## 9. Những lỗi thường gặp khi triển khai và kiểm thử

**Nhầm tra cứu với xác thực.** Một test `loadUserByUsername("lan")` thành công chỉ chứng minh tìm được thông tin tài khoản. Nó không chứng minh mật khẩu đúng, provider chấp nhận hay HTTP filter cho phép truy cập.

**Ném DisabledException ngay trong UserDetailsService.** Điều này trộn lẫn trách nhiệm dữ liệu với trách nhiệm xác thực. Với `DaoAuthenticationProvider` thông thường, nên chuyển đúng trạng thái qua `UserDetails.isEnabled()` để provider quyết định.

**Trả null khi không có tài khoản.** Hợp đồng của `UserDetailsService` dùng `UsernameNotFoundException`. Trả `null` khiến lỗi khó dự đoán, có thể bị diễn giải thành lỗi hệ thống thay vì người dùng không tồn tại.

**Mong provider luôn ném UsernameNotFoundException.** `DaoAuthenticationProvider` mặc định che giấu ngoại lệ này thành `BadCredentialsException`. Khi kiểm thử, hãy đặt assertion phù hợp với tầng đang gọi và cấu hình `hideUserNotFoundExceptions` thực tế.

**Giữ password dưới dạng văn bản thô trong UserDetails.** `getPassword()` dành cho password hash tương thích với `PasswordEncoder`. Dữ liệu test dùng chuỗi giả chỉ phù hợp khi kiểm tra ánh xạ service; để test xác thực thật nên dùng hash do `PasswordEncoder` tạo ra.

**Thiếu kiểm tra authority hoặc trạng thái tài khoản.** Một service có thể trả đúng username nhưng sai role hoặc `enabled`. Hãy kiểm tra các thuộc tính này ngay tại tầng dữ liệu, trước khi kiểm tra endpoint yêu cầu quyền.

**Dùng @WithMockUser để khẳng định đã chặn tài khoản disabled.** Annotation này không tra cứu tài khoản và không kiểm tra trạng thái. Thay bằng kiểm thử provider thật hoặc request HTTP thực sự đi qua cơ chế đăng nhập.

**Thông báo lỗi để lộ danh sách tài khoản.** Không nên trả ra cho người dùng cuối thông tin phân biệt “username không tồn tại” và “mật khẩu sai” nếu điều đó không cần thiết. Cần kiểm tra thông báo, mã lỗi và dữ liệu log theo chính sách bảo mật của ứng dụng.

**Không xét tenant hoặc trạng thái bị thay đổi.** Ở ứng dụng nhiều tenant, một username có thể chỉ duy nhất trong từng tenant; service phải tìm đúng phạm vi. Nếu dùng cache cho `UserDetails`, cần đảm bảo thay đổi trạng thái vô hiệu hóa được phản ánh kịp thời; tài khoản vừa bị khóa không nên được tiếp tục xác thực bằng dữ liệu cache cũ.

## 10. Bài thực hành củng cố

1. Bổ sung tài khoản `locked` trong `AccountRepository` giả lập. Kiểm tra `loadUserByUsername("locked")` trả `isAccountNonLocked() == false`, sau đó dùng provider thật để xác minh `LockedException`.
2. Thay `"stored-hash"` trong kiểm thử provider bằng `BCryptPasswordEncoder.encode("correct-password")` và xác minh cả mật khẩu đúng lẫn sai. Giải thích tại sao so sánh hai chuỗi BCrypt do `encode(...)` tạo ra không phải cách kiểm tra mật khẩu.
3. Thêm endpoint chỉ cho vai trò `ADMIN`; kiểm tra tài khoản `lan` có `ROLE_READER` được xác thực nhưng nhận `403` khi gọi endpoint này.
4. Viết hai bài test HTTP cho `unknown` và `disabled` bằng `httpBasic(...)`. Giải thích vì sao cả hai có thể trả `401` dù ngoại lệ nội bộ của provider khác nhau.
5. Thử dùng `@WithUserDetails("disabled")` trong test phân quyền. Nêu rõ vì sao test đó không thể thay thế ca kiểm thử từ chối đăng nhập ở tầng provider.

Khi kiểm thử `UserDetailsService`, hãy giữ ba câu hỏi riêng biệt: **có tải đúng bản ghi không, trạng thái và quyền có được ánh xạ đúng không, và khi dùng dữ liệu đó để xác thực thì hệ thống có cho phép hoặc từ chối đúng không?** Trả lời từng câu hỏi ở đúng tầng sẽ giúp bộ kiểm thử phát hiện lỗi rõ ràng và bảo vệ hành vi đăng nhập thực tế.
