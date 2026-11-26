# AuthenticationProvider với thông tin xác thực hợp lệ và không hợp lệ

## 1. Bối cảnh và mục tiêu

Trong Spring Security, việc một yêu cầu HTTP có được phép truy cập tài nguyên hay không bắt đầu bằng câu hỏi: **thông tin xác thực do phía gọi cung cấp có chứng minh được danh tính không?** Trách nhiệm kiểm tra đó thuộc về cơ chế *authentication*. Sau khi danh tính được xác thực, cơ chế *authorization* mới quyết định người dùng có đủ quyền thực hiện hành động cụ thể hay không.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mục tiêu là kiểm thử hành vi thật của `AuthenticationProvider` với cả dữ liệu hợp lệ lẫn không hợp lệ, rồi nối kết kết quả với kiểm thử HTTP bằng `spring-security-test`. Đây là cách phát hiện lỗi mật khẩu, trạng thái tài khoản hoặc chọn provider trước khi chúng biểu hiện thành mã HTTP `401` hoặc `403`.

Sau bài học, bạn có thể:

- Giải thích vai trò của `AuthenticationProvider`, `AuthenticationManager` và `ProviderManager`.
- Tạo thông tin xác thực chưa được tin cậy, kiểm chứng kết quả thành công và các ngoại lệ thất bại.
- Phân biệt sai mật khẩu, người dùng không tồn tại và tài khoản bị vô hiệu hóa.
- Dùng `PasswordEncoder` thật trong kiểm thử thành phần, tránh việc mock làm mất thao tác so khớp mật khẩu.
- Chọn đúng tầng kiểm thử khi cần xác minh việc xử lý HTTP, phân quyền, JWT/OAuth2/OIDC hoặc ứng dụng Reactive.

## 2. AuthenticationProvider thực sự làm gì?

Giao diện `org.springframework.security.authentication.AuthenticationProvider` có hai phương thức quan trọng:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

| Thành phần | Trách nhiệm | Điều cần kiểm thử |
| --- | --- | --- |
| `Authentication` đầu vào | Chứa danh tính và bằng chứng do bên gọi đưa đến, chẳng hạn tên người dùng và mật khẩu | Đầu vào phải là token **chưa xác thực** |
| `supports(Class<?>)` | Cho biết provider có xử lý loại `Authentication` đó hay không | Token phù hợp được chấp nhận; token không phù hợp bị bỏ qua khi chọn provider |
| `authenticate(...)` | Kiểm tra thông tin đăng nhập; trả về `Authentication` thành công hoặc báo thất bại | Danh tính, cờ `authenticated`, quyền và loại ngoại lệ |
| `ProviderManager` | Lần lượt gọi các provider phù hợp; quản lý kết quả xác thực | Có provider xử lý hay không; xóa thông tin bí mật khỏi kết quả theo cấu hình mặc định |
| `SecurityContext` | Giữ đối tượng `Authentication` của ngữ cảnh bảo mật hiện tại | Luồng filter hoặc cơ chế test context thiết lập và sử dụng đúng danh tính |

`DaoAuthenticationProvider` là một triển khai thường gặp cho đăng nhập tên người dùng/mật khẩu. Nó sử dụng `UserDetailsService` để tìm người dùng và `PasswordEncoder.matches(rawPassword, encodedPassword)` để đối chiếu mật khẩu thô với mật khẩu đã mã hóa một chiều. Mật khẩu được mã hóa bằng BCrypt có muối ngẫu nhiên; không so sánh hai chuỗi BCrypt do `encode(...)` sinh ra để kết luận mật khẩu đúng hay sai.

Luồng thường thấy trong ứng dụng Servlet:

~~~mermaid
flowchart TD
    A["Yêu cầu HTTP kèm thông tin đăng nhập"] --> B["Security filter tạo Authentication chưa xác thực"]
    B --> C["AuthenticationManager / ProviderManager"]
    C --> D{"Provider hỗ trợ loại token?"}
    D -- "Không" --> E["Thử provider phù hợp tiếp theo"]
    D -- "Có" --> F["DaoAuthenticationProvider"]
    F --> G["UserDetailsService tải người dùng"]
    G --> H{"Trạng thái tài khoản hợp lệ?"}
    H -- "Không" --> X["Ném AuthenticationException"]
    H -- "Có" --> I{"PasswordEncoder.matches?"}
    I -- "Không" --> X
    I -- "Có" --> J["Trả về Authentication đã xác thực và authorities"]
    J --> K["Thiết lập SecurityContext; tiếp tục phân quyền"]
    X --> L["Filter xử lý thất bại xác thực"]
~~~

Sơ đồ minh họa trường hợp sử dụng `DaoAuthenticationProvider`; xử lý người dùng không tồn tại có nhánh riêng và Spring Security mặc định che giấu loại lỗi này. Nếu dùng JWT, OAuth2 hoặc cơ chế xác thực khác, provider và bằng chứng cần kiểm tra cũng khác.

### Xác thực khác phân quyền

Một tài khoản `lan` với vai trò `READER` có thể xác thực thành công nhưng bị từ chối truy cập `/api/admin` nếu endpoint yêu cầu `ADMIN`. Trong trường hợp phổ biến với HTTP Basic:

- Tên người dùng/mật khẩu sai: **401 Unauthorized** — yêu cầu chưa xác thực thành công.
- Đăng nhập đúng nhưng không đủ quyền: **403 Forbidden** — đã xác thực, nhưng không được phép truy cập.

Mã HTTP cuối cùng còn phụ thuộc vào cấu hình `AuthenticationEntryPoint`, `AccessDeniedHandler` và kiểu đăng nhập. Ví dụ, form login có thể chuyển hướng thay vì trả về `401` trực tiếp. `AuthenticationProvider` tự nó không tạo mã trạng thái HTTP.

## 3. Ma trận kiểm thử thành phần

Trước khi viết code, xác định hành vi mong đợi cho từng điều kiện:

| Đầu vào/trạng thái | Kết quả mong đợi khi dùng DaoAuthenticationProvider |
| --- | --- |
| Người dùng tồn tại, đang hoạt động, mật khẩu đúng | Trả về `Authentication` khác `null` với `isAuthenticated() == true` và quyền của người dùng |
| Người dùng tồn tại, mật khẩu sai | Ném `BadCredentialsException` |
| Người dùng không tồn tại | Mặc định ném `BadCredentialsException` để hạn chế làm lộ sự tồn tại của tài khoản |
| Tài khoản bị vô hiệu hóa | Ném `DisabledException` |
| Tài khoản bị khóa | Ném `LockedException` |
| Tài khoản hết hạn | Ném `AccountExpiredException` |
| Thông tin xác thực của tài khoản hết hạn | Ném `CredentialsExpiredException` |
| Loại `Authentication` không được provider hỗ trợ | `supports(...)` trả về `false`; `ProviderManager` tìm provider khác, hoặc thất bại nếu không có provider nào xử lý |

Các kiểm tra trạng thái tài khoản được thực hiện trước bước đối chiếu mật khẩu trong `DaoAuthenticationProvider`. Vì thế với tài khoản bị vô hiệu hóa, hãy dùng mật khẩu đúng khi kiểm tra `DisabledException` để ca kiểm thử tập trung vào một nguyên nhân.

Đối với một số triển khai `AuthenticationProvider` tùy chỉnh, `authenticate(...)` có thể trả về `null` để một provider khác thử tiếp. Không xem đó là dấu hiệu xác thực thành công.

## 4. Thiết lập kiểm thử với provider thật

Ví dụ dưới đây dùng **JUnit Jupiter**, **AssertJ** và các lớp Spring Security Core. Không cần khởi động toàn bộ Spring Boot context: chính `DaoAuthenticationProvider`, `InMemoryUserDetailsManager` và `BCryptPasswordEncoder` sẽ thực hiện xác thực thực sự.

Với ứng dụng Spring Boot, các dependency thường dùng gồm `spring-boot-starter-security` (chức năng bảo mật), `spring-boot-starter-test` (JUnit/AssertJ) và `spring-security-test` (tiện ích MockMvc/WebTestClient và annotation mô phỏng người dùng). Hai dependency phục vụ test cần phạm vi `test`; mã kiểm thử provider trực tiếp chỉ sử dụng lớp từ Security Core và các thư viện assertion.

~~~java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DaoAuthenticationProviderComponentTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();

    private final UserDetailsService users = new InMemoryUserDetailsManager(
            User.withUsername("lan")
                    .password(encoder.encode("correct-password"))
                    .roles("READER")
                    .build(),
            User.withUsername("disabled")
                    .password(encoder.encode("correct-password"))
                    .roles("READER")
                    .disabled(true)
                    .build()
    );

    private final DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);

    @BeforeEach
    void setUp() {
        provider.setPasswordEncoder(encoder);
    }

    private Authentication authenticate(String username, String password) {
        return provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));
    }

    @Test
    void validCredentialsProduceAuthenticatedPrincipalAndAuthorities() {
        Authentication result = authenticate("lan", "correct-password");

        assertThat(result).isNotNull();
        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_READER");
    }

    @Test
    void wrongPasswordIsRejected() {
        assertThatThrownBy(() -> authenticate("lan", "wrong-password"))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void unknownUsernameDoesNotRevealUserExistenceByDefault() {
        assertThatThrownBy(() -> authenticate("unknown", "correct-password"))
                .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void disabledAccountIsRejectedEvenWithCorrectPassword() {
        assertThatThrownBy(() -> authenticate("disabled", "correct-password"))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void providerOnlySupportsUsernamePasswordAuthentication() {
        assertThat(provider.supports(UsernamePasswordAuthenticationToken.class))
                .isTrue();
        assertThat(provider.supports(AnonymousAuthenticationToken.class))
                .isFalse();
    }

    @Test
    void providerManagerErasesCredentialsAfterSuccessByDefault() {
        ProviderManager manager = new ProviderManager(List.of(provider));

        Authentication result = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "correct-password"));

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getCredentials()).isNull();
    }
}
~~~

**Vì sao ví dụ này thực sự kiểm tra xác thực?**

1. `UsernamePasswordAuthenticationToken.unauthenticated(...)` biểu diễn dữ liệu chưa được tin cậy. Không tạo token đã xác thực bằng constructor chứa danh sách quyền rồi dùng nó để chứng minh mật khẩu hợp lệ.
2. `InMemoryUserDetailsManager` cung cấp người dùng có mật khẩu BCrypt thật; `DaoAuthenticationProvider` tự gọi bộ mã hóa để kiểm tra.
3. Kiểm tra `isAuthenticated()` và `authorities` giúp phát hiện trường hợp provider trả kết quả sai dù không ném ngoại lệ.
4. Kiểm tra **loại ngoại lệ** giúp phân biệt vi phạm mật khẩu với trạng thái tài khoản. Không phụ thuộc vào nguyên văn thông báo lỗi, vì thông báo có thể thay đổi.
5. Ca `ProviderManager` kiểm tra việc xóa credentials trên kết quả trả về theo mặc định. Gọi `provider.authenticate(...)` trực tiếp và gọi qua `ProviderManager` là hai tầng khác nhau; không mặc định yêu cầu provider trực tiếp đã xóa credentials.

> **Lưu ý về phiên bản:** Ví dụ dùng constructor `new DaoAuthenticationProvider(UserDetailsService)` trong các phiên bản Spring Security hiện đại. Nếu dự án sử dụng bản cũ hơn với API khởi tạo khác, điều chỉnh phần khởi tạo theo phiên bản đang dùng; ý nghĩa của các ca kiểm thử không thay đổi.

## 5. Kiểm chứng thông qua HTTP bằng spring-security-test

Kiểm thử thành phần ở trên chứng minh cơ chế so khớp mật khẩu và xử lý trạng thái tài khoản. Nó **chưa chứng minh** rằng request đi qua đúng filter, endpoint đã được bảo vệ hay ứng dụng trả mã HTTP phù hợp.

Với ứng dụng **Servlet** dùng Spring MVC, có thể sử dụng `MockMvc` kết hợp `spring-security-test`. Ví dụ dưới đây giả định ứng dụng đã cấu hình:

- HTTP Basic với một `SecurityFilterChain` đang hoạt động.
- `/api/profile` là endpoint tồn tại và yêu cầu người dùng đã xác thực.
- `/api/admin` yêu cầu vai trò `ADMIN`.
- `UserDetailsService`/`PasswordEncoder` trong test nhận tài khoản `lan`, mật khẩu `correct-password`, vai trò `READER`.

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
class AuthenticationHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validBasicCredentialsAllowAuthenticatedEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "correct-password")))
                .andExpect(status().isOk());
    }

    @Test
    void wrongBasicCredentialsReturn401() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin")
                        .with(httpBasic("lan", "correct-password")))
                .andExpect(status().isForbidden());
    }
}
~~~

Ở đây `httpBasic(...)` tạo header `Authorization: Basic ...` cho request. Header được xử lý qua chuỗi filter bảo mật của ứng dụng; provider được cấu hình sẽ kiểm tra mật khẩu. Vì vậy bài test có thể phát hiện cả lỗi tích hợp. Để kiểm tra vai trò của `AuthenticationProvider` thật, phải bảo đảm test context có cấu hình provider dự kiến và không thay thế nó bằng một cơ chế xác thực giả lập.

Nếu chỉ dùng `@WebMvcTest`, cần cung cấp các bean/cấu hình bảo mật liên quan một cách chủ ý; nếu thiếu, test slice có thể không mô phỏng cùng luồng xác thực như ứng dụng đầy đủ. Kiểm thử trên còn phụ thuộc endpoint và cấu hình HTTP Basic nêu trên, nên cần điều chỉnh cho dự án cụ thể.

### Phân biệt với @WithMockUser

`@WithMockUser(username = "lan", roles = "READER")` đặt một `Authentication` giả lập vào `SecurityContext` để kiểm tra logic phân quyền. Nó **không** kiểm tra rằng `UserDetailsService` tìm được `lan`, `PasswordEncoder` đối chiếu mật khẩu đúng hay `DaoAuthenticationProvider` chấp nhận đăng nhập.

Do đó:

| Mục tiêu | Phương pháp phù hợp |
| --- | --- |
| Kiểm tra mật khẩu đúng/sai và tài khoản bị khóa/vô hiệu hóa | Gọi `DaoAuthenticationProvider` thật |
| Kiểm tra request HTTP Basic đi qua filter và trả `401/403` | `MockMvc` + `httpBasic(...)` + cấu hình security thực |
| Kiểm tra endpoint có cho phép vai trò `ADMIN` không mà không quan tâm mật khẩu | `MockMvc` + `@WithMockUser` hoặc `user(...)` |
| Kiểm tra JWT được giải mã, chữ ký/issuer/audience hợp lệ | Kiểm thử decoder và filter/resource server thực theo cấu hình |
| Kiểm tra tài nguyên với JWT giả lập | `jwt()` trong `spring-security-test`; thích hợp cho phân quyền nhưng bỏ qua bước xác minh token thật |

## 6. Với Reactive, JWT, OAuth2 và OIDC thì sao?

Phạm vi mô-đun bao gồm cả Servlet và Reactive, nên cần xác định đúng ranh giới API:

- **Spring MVC/Servlet:** `AuthenticationProvider` và `ProviderManager` xử lý mô hình xác thực đồng bộ. `MockMvc` giúp kiểm chứng HTTP và filter chain.
- **Spring WebFlux/Reactive:** cơ chế tương ứng thường dựa trên `ReactiveAuthenticationManager`, ví dụ `UserDetailsRepositoryReactiveAuthenticationManager` với `ReactiveUserDetailsService`. Dùng `WebTestClient` để kiểm thử HTTP Reactive; không đem `DaoAuthenticationProvider` gắn trực tiếp vào pipeline Reactive rồi giả định nó là cùng một contract.
- **JWT bearer token:** bằng chứng đầu vào là bearer token; cần kiểm tra `JwtDecoder`, các validator liên quan và resource server nếu mục đích là kiểm chứng xác thực JWT thật. Các request postprocessor như `jwt()` tạo sẵn người dùng/token cho kiểm thử phân quyền, không chứng minh chữ ký JWT đã được xác minh.
- **OAuth2 Login/OIDC:** luồng có redirect, callback, phiên đăng nhập và xử lý thông tin từ nhà cung cấp định danh. Tiện ích giả lập `oauth2Login()`/`oidcLogin()` phù hợp khi mục đích là kiểm thử logic phía ứng dụng sau khi người dùng đã đăng nhập; kiểm thử toàn bộ giao thức cần cấu hình và lớp kiểm thử khác.

Ví dụ, trong WebFlux dùng HTTP Basic, kiểm thử thất bại ở tầng HTTP có thể viết như sau **khi ứng dụng đã cấu hình Reactive Security và endpoint tương ứng**:

~~~java
webTestClient.get()
        .uri("/api/profile")
        .headers(headers -> headers.setBasicAuth("lan", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đoạn trên là phương thức bên trong bài test đã được cấp một `WebTestClient` gắn với ứng dụng; không phải kiểm thử trực tiếp `DaoAuthenticationProvider`.

## 7. Những lỗi thường gặp khi kiểm thử

**Dùng @WithMockUser để kết luận chức năng đăng nhập hoạt động.** Bài test có thể xanh ngay cả khi mật khẩu hay provider cấu hình sai. Hãy bổ sung một bài test gọi provider thật và một bài HTTP đi qua filter đăng nhập thực tế.

**Tạo Authentication đã xác thực ngay từ đầu.** Constructor `UsernamePasswordAuthenticationToken(principal, credentials, authorities)` biểu thị token đã tin cậy. Đối với kiểm thử đăng nhập bằng mật khẩu, hãy tạo token chưa xác thực và để provider quyết định kết quả.

**So sánh BCrypt hash theo chuỗi hoặc mock PasswordEncoder luôn trả true.** Hai lần băm cùng mật khẩu có thể tạo ra chuỗi khác nhau. Dùng `matches(...)` thông qua provider thật, với dữ liệu test được mã hóa một chiều.

**Coi mọi thất bại là 403.** Mật khẩu sai thường dẫn đến `401` khi sử dụng HTTP Basic, còn người dùng đã xác thực nhưng thiếu vai trò thường nhận `403`. Với form login, thất bại xác thực có thể chuyển hướng; cần xác nhận kiểu entry point trước khi đặt assertion.

**Chỉ kiểm tra ngoại lệ nhưng không kiểm tra quyền.** Provider có thể xác thực đúng người dùng nhưng trả về authorities sai. Với case thành công, luôn kiểm tra tên principal và quyền quan trọng.

**Khẳng định người dùng không tồn tại phải ném UsernameNotFoundException.** Với `DaoAuthenticationProvider`, `hideUserNotFoundExceptions` mặc định được bật, khiến người dùng không tồn tại và mật khẩu sai đều biểu hiện thành `BadCredentialsException`. Không đặt yêu cầu tiết lộ người dùng có tồn tại hay không chỉ để làm test dễ viết hơn.

**Bỏ qua bảo mật ở tầng HTTP.** Một bài test provider xanh không chứng minh endpoint được bảo vệ; một bài HTTP `POST/PUT/DELETE` trả `403` cũng có thể do CSRF chứ không hẳn do thiếu quyền. Khi kiểm thử thay đổi trạng thái trên Servlet, xem xét token CSRF theo chính sách của ứng dụng, chẳng hạn dùng `csrf()` trong `spring-security-test`.

**Đưa bí mật thật vào dữ liệu test hay log.** Chỉ dùng tài khoản và mật khẩu giả lập; không in header Basic, token thật hoặc mật khẩu vào thông báo assertion và nhật ký.

## 8. Bài thực hành mở rộng

Từ bài test thành phần ở mục 4, hãy bổ sung một tài khoản bị khóa `locked` bằng `User.withUsername(...).accountLocked(true)`, sau đó khẳng định `LockedException` xuất hiện kể cả khi mật khẩu được cung cấp là đúng. Tiếp theo, thêm endpoint chỉ cho `ADMIN` và viết bài MockMvc xác minh `lan` nhận `403`. Cuối cùng, thử thay `httpBasic(...)` bằng `@WithMockUser` rồi giải thích vì sao bài test sau không thể phát hiện mật khẩu sai.

Khi hoàn thành, bộ kiểm thử cần bảo vệ ba điểm độc lập: **xác thực thực sự thành công hoặc thất bại đúng cách; người dùng nhận đúng authorities; HTTP filter và quy tắc truy cập phản hồi đúng hành vi người dùng**. Đây là nền tảng để tiếp tục kiểm thử các hình thức xác thực phức tạp hơn trong Spring Security.
