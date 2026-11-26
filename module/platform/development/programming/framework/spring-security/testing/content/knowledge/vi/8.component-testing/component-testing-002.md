# AuthenticationManager và cơ chế chọn provider phù hợp

## 1. Bối cảnh: một ứng dụng có thể có nhiều cách đăng nhập

Giả sử một hệ thống Spring Security chấp nhận tên người dùng/mật khẩu cho nhân viên, khóa API cho dịch vụ nội bộ và bearer token cho API công khai. Mỗi loại thông tin xác thực có cách kiểm chứng riêng. Thành phần nhận yêu cầu xác thực cần **chuyển thông tin đó đến cơ chế phù hợp**, rồi đưa ra kết quả chung cho phần còn lại của ứng dụng.

Trong Spring Security theo mô hình Servlet, hợp đồng trung tâm là `AuthenticationManager`. Triển khai phổ biến `ProviderManager` điều phối danh sách `AuthenticationProvider` theo thứ tự đã đăng ký. Hiểu rõ việc chọn provider rất quan trọng khi kiểm thử các trường hợp đăng nhập hợp lệ, không hợp lệ, tài khoản bị vô hiệu hóa và cấu hình nhiều cơ chế bảo mật.

Bài thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Bên cạnh kiểm thử điều phối ở mức Java, bài còn liên hệ đến `spring-security-test`, `MockMvc` và `WebTestClient` để kiểm chứng luồng HTTP, `SecurityContext` và phân quyền trong ứng dụng Servlet hoặc Reactive. Các tiện ích giả lập `@WithMockUser`, JWT/OAuth2/OIDC sẽ được phân biệt với kiểm thử xác thực thực sự.

Sau khi học, bạn có thể:

- Phân biệt vai trò của `AuthenticationManager`, `ProviderManager` và `AuthenticationProvider`.
- Giải thích cách `supports(...)`, thứ tự provider, giá trị trả về `null` và các loại ngoại lệ quyết định luồng xử lý.
- Viết kiểm thử chứng minh provider không hỗ trợ sẽ không được gọi; provider sau có thể được thử khi provider trước từ chối.
- Kiểm chứng hành vi ngoại lệ, parent manager và kết quả đã xác thực.
- Nhận biết giới hạn của kiểm thử dùng mock và chọn thêm kiểm thử HTTP hoặc provider thực khi cần.

## 2. Vai trò của AuthenticationManager

`AuthenticationManager` định nghĩa một phương thức:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

Đầu vào `Authentication` chứa principal và credentials do bên gọi cung cấp; trong đăng nhập mật khẩu, đó thường là `UsernamePasswordAuthenticationToken` **chưa xác thực**. Kết quả thành công là một đối tượng `Authentication` đã xác thực với principal và authorities phù hợp. Nếu không xác thực được, phương thức ném `AuthenticationException`.

`AuthenticationManager` là **hợp đồng**, không buộc mọi ứng dụng phải dùng một cách xác thực cụ thể. `ProviderManager` là triển khai điều phối một danh sách provider theo thứ tự. Mỗi `AuthenticationProvider` có hai thao tác quan trọng:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
~~~

| Thành phần | Công việc | Điểm cần kiểm chứng |
| --- | --- | --- |
| `AuthenticationManager` | Nhận yêu cầu xác thực và trả kết quả/ngoại lệ | Luồng xác thực tổng thể có kết quả đúng |
| `ProviderManager` | Duyệt danh sách provider, xử lý kết quả và tùy chọn parent | Đúng provider được gọi, đúng thứ tự, dừng/tiếp tục đúng điều kiện |
| `AuthenticationProvider` | Chấp nhận một hay nhiều loại token và kiểm tra bằng chứng | `supports(...)` và logic `authenticate(...)` thực hiện đúng |
| `Authentication` | Biểu diễn thông tin xác thực đầu vào và kết quả | Principal, credentials, authorities, `isAuthenticated()` |
| `SecurityContext` | Lưu `Authentication` của ngữ cảnh bảo mật hiện tại | Có được thiết lập qua filter hoặc thành phần chủ động quản lý context |

**Điểm ranh giới:** Gọi `authenticationManager.authenticate(...)` trực tiếp không tự động đặt kết quả vào `SecurityContextHolder` và không tự sinh HTTP status. Trong một request web, các security filter phối hợp thực hiện những bước này theo cấu hình.

## 3. ProviderManager chọn provider như thế nào?

`ProviderManager` xét từng provider theo **thứ tự trong danh sách**. Với token đầu vào, nó gọi `supports(authentication.getClass())`. Chỉ những provider trả về `true` mới được gọi `authenticate(authentication)`.

Kết quả từ một provider có thể là thành công, `null` để nhường provider kế tiếp, hoặc ngoại lệ. Luồng cốt lõi:

~~~mermaid
flowchart TD
    A["ProviderManager.authenticate(token)"] --> B{"Còn provider trong danh sách?"}
    B -- "Có" --> C{"supports(token.getClass())?"}
    C -- "Không" --> B
    C -- "Có" --> D["provider.authenticate(token)"]
    D -- "Trả Authentication" --> E["Hoàn tất: xóa credentials theo cấu hình, trả kết quả"]
    D -- "Trả null" --> B
    D -- "AuthenticationException thông thường" --> F["Ghi nhớ lỗi; xét provider tiếp theo"]
    F --> B
    D -- "AccountStatusException hoặc InternalAuthenticationServiceException" --> G["Dừng và ném ngoại lệ"]
    B -- "Không" --> H{"Có parent AuthenticationManager?"}
    H -- "Có" --> I["Thử parent"]
    I -- "Thành công" --> E
    I -- "Thất bại" --> J["Ném ngoại lệ phù hợp"]
    H -- "Không" --> J
~~~

Sơ đồ mô tả các nhánh chính của `ProviderManager`; hành vi ghi nhớ/chọn ngoại lệ cuối cùng phụ thuộc vào kết quả các provider và parent cụ thể.

### 3.1. supports(...) chọn theo loại token

Ví dụ thường gặp:

- `DaoAuthenticationProvider` hỗ trợ `UsernamePasswordAuthenticationToken` để kiểm tra username/password bằng `UserDetailsService` và `PasswordEncoder`.
- Một provider tùy chỉnh có thể chỉ hỗ trợ `ApiKeyAuthenticationToken` do ứng dụng định nghĩa.
- Provider xử lý bearer token và các cơ chế OAuth2 có những loại token hoặc hợp đồng riêng, tùy cấu hình.

Nếu provider khai báo `supports(...) == false`, `ProviderManager` sẽ **bỏ qua** `authenticate(...)` của provider ấy. Việc hỗ trợ token không bảo đảm xác thực thành công: provider còn phải kiểm tra credentials, trạng thái tài khoản và những điều kiện nghiệp vụ cần thiết.

Không dùng `supports(...)` để kiểm tra tên người dùng, mật khẩu hoặc role; nó được thiết kế để quyết định provider có khả năng xử lý **loại Authentication** hay không. Nếu hai provider cùng hỗ trợ một lớp token, cả hai có thể lần lượt được thử.

### 3.2. Ý nghĩa của null, thành công và ngoại lệ

| Kết quả của provider đang xét | Hành vi điển hình của ProviderManager |
| --- | --- |
| `supports(...) == false` | Không gọi `authenticate(...)`; thử provider kế tiếp |
| `authenticate(...)` trả `null` | Provider không đưa ra kết quả; thử provider kế tiếp |
| `authenticate(...)` trả một `Authentication` thành công | Dừng duyệt; trả kết quả, thường xóa credentials nhạy cảm |
| Ném `BadCredentialsException` hoặc `AuthenticationException` thông thường | Ghi nhận lỗi; có thể thử provider kế tiếp |
| Ném `AccountStatusException`, ví dụ `DisabledException` hoặc `LockedException` | Dừng ngay; không thử provider sau |
| Ném `InternalAuthenticationServiceException` | Dừng ngay; không tiếp tục thử provider sau |
| Không provider nào xử lý và không có parent | Ném `ProviderNotFoundException` |
| Không provider nào thành công nhưng có parent | Có thể chuyển đến parent; kết quả/ngoại lệ của parent ảnh hưởng đến kết quả cuối |

**Hệ quả bảo mật cần nhớ:** `BadCredentialsException` từ một provider **không mặc nhiên ngăn** provider kế tiếp xác thực thành công nếu provider ấy cũng hỗ trợ token đầu vào. Vì vậy các provider dùng cùng loại token cần được cấu hình và kiểm thử cẩn thận; đừng giả định “sai mật khẩu ở provider đầu” là điều kiện kết thúc toàn bộ chuỗi.

### 3.3. Thứ tự provider và parent

Ví dụ minh họa đăng ký hai provider:

~~~java
AuthenticationManager manager = new ProviderManager(
        List.of(apiKeyProvider, daoAuthenticationProvider));
~~~

Đoạn trên giả định hai biến provider đã được khởi tạo. Nếu `apiKeyProvider` chỉ hỗ trợ token khóa API, nó bị bỏ qua đối với `UsernamePasswordAuthenticationToken` và `daoAuthenticationProvider` xử lý. Nếu cả hai hỗ trợ cùng loại token, **thứ tự và hành vi trả về/ngoại lệ** trở thành một phần của kết quả.

`ProviderManager` cũng có thể nhận một `AuthenticationManager` cha. Parent cung cấp một tầng xử lý bổ sung khi chuỗi provider hiện tại chưa xác thực thành công. Khi kiểm thử nhiều chuỗi bảo mật hoặc nhiều cấu hình xác thực, cần xét cả parent; chỉ kiểm tra danh sách provider cục bộ có thể bỏ sót đường xác thực cuối.

## 4. Kiểm thử cơ chế chọn provider bằng JUnit 5 và Mockito

Mục tiêu đầu tiên là cô lập **quy tắc điều phối của ProviderManager**. Mockito giúp quan sát chính xác provider nào được gọi, không cần phụ thuộc CSDL, BCrypt hay endpoint HTTP. Ví dụ dưới đây sử dụng Spring Security Core, JUnit Jupiter, AssertJ và Mockito (được cung cấp trong nhiều dự án qua `spring-boot-starter-test`).

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ProviderManagerRoutingTest {

    private static Authentication request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", "test-password");
    }

    private static Authentication success(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                "temporary-credential",
                AuthorityUtils.createAuthorityList("ROLE_READER"));
    }

    @Test
    void skipsProviderThatDoesNotSupportTokenType() {
        AuthenticationProvider apiKey = mock(AuthenticationProvider.class);
        AuthenticationProvider password = mock(AuthenticationProvider.class);

        when(apiKey.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(false);
        when(password.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(password.authenticate(any(Authentication.class)))
                .thenReturn(success("lan"));

        AuthenticationManager manager =
                new ProviderManager(List.of(apiKey, password));

        Authentication result = manager.authenticate(request());

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getCredentials()).isNull();
        verify(apiKey, never()).authenticate(any(Authentication.class));
        verify(password).authenticate(any(Authentication.class));
    }

    @Test
    void triesNextSupportingProviderWhenPreviousReturnsNull() {
        AuthenticationProvider first = mock(AuthenticationProvider.class);
        AuthenticationProvider second = mock(AuthenticationProvider.class);

        when(first.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(second.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(first.authenticate(any(Authentication.class))).thenReturn(null);
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(success("lan"));

        Authentication result =
                new ProviderManager(List.of(first, second)).authenticate(request());

        assertThat(result.isAuthenticated()).isTrue();
        verify(first).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void ordinaryBadCredentialsExceptionDoesNotAlwaysStopChain() {
        AuthenticationProvider first = mock(AuthenticationProvider.class);
        AuthenticationProvider second = mock(AuthenticationProvider.class);

        when(first.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(second.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("rejected by first"));
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(success("lan"));

        Authentication result =
                new ProviderManager(List.of(first, second)).authenticate(request());

        assertThat(result.isAuthenticated()).isTrue();
        verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void disabledAccountStopsProviderChainImmediately() {
        AuthenticationProvider first = mock(AuthenticationProvider.class);
        AuthenticationProvider second = mock(AuthenticationProvider.class);

        when(first.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(second.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new DisabledException("account is disabled"));

        ProviderManager manager = new ProviderManager(List.of(first, second));

        assertThatThrownBy(() -> manager.authenticate(request()))
                .isInstanceOf(DisabledException.class);
        verify(second, never()).authenticate(any(Authentication.class));
    }

    @Test
    void failsWhenNoProviderCanHandleTokenAndThereIsNoParent() {
        AuthenticationProvider apiKey = mock(AuthenticationProvider.class);
        when(apiKey.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(false);

        ProviderManager manager = new ProviderManager(List.of(apiKey));

        assertThatThrownBy(() -> manager.authenticate(request()))
                .isInstanceOf(ProviderNotFoundException.class);
        verify(apiKey, never()).authenticate(any(Authentication.class));
    }

    @Test
    void delegatesToParentWhenLocalProvidersCannotAuthenticate() {
        AuthenticationProvider apiKey = mock(AuthenticationProvider.class);
        when(apiKey.supports(UsernamePasswordAuthenticationToken.class))
                .thenReturn(false);

        AuthenticationManager parent = authentication -> success("from-parent");
        ProviderManager manager =
                new ProviderManager(List.of(apiKey), parent);

        Authentication result = manager.authenticate(request());

        assertThat(result.getName()).isEqualTo("from-parent");
        assertThat(result.isAuthenticated()).isTrue();
        verify(apiKey, never()).authenticate(any(Authentication.class));
    }
}
~~~

### Đọc kết quả đúng cách

Các test trên chứng minh cơ chế **chọn và thử provider** của `ProviderManager`:

1. Provider không hỗ trợ loại token bị bỏ qua; khi provider sau thành công, manager trả lại principal đã xác thực.
2. Giá trị `null` khiến chuỗi tiếp tục; các ngoại lệ xác thực thông thường, như `BadCredentialsException`, cũng có thể cho phép provider tiếp theo thử.
3. Lỗi trạng thái tài khoản `DisabledException` khiến chuỗi dừng, giúp tránh việc một provider khác bỏ qua tình trạng bị vô hiệu hóa.
4. Nếu không có provider hỗ trợ, manager báo `ProviderNotFoundException`, trừ khi parent xử lý.
5. Với cấu hình mặc định, `ProviderManager` yêu cầu kết quả triển khai `CredentialsContainer` xóa credentials sau khi thành công. Trong test đầu, `UsernamePasswordAuthenticationToken` bị xóa giá trị credentials, nên `getCredentials()` là `null`.

Ở đây các provider bị **mock**, vì thế bài test không xác minh mật khẩu thực hoặc kết nối dịch vụ định danh. Không dùng kết quả của nó để khẳng định `DaoAuthenticationProvider` có thể đọc người dùng hay xử lý mật khẩu BCrypt đúng.

## 5. Thêm một kiểm thử tích hợp provider thật

Để kiểm chứng một nhánh xác thực bằng tên người dùng/mật khẩu, có thể sử dụng `DaoAuthenticationProvider` thật, `InMemoryUserDetailsManager` và `BCryptPasswordEncoder`. Ví dụ tiếp theo độc lập với lớp test ở mục 4:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
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

class ProviderManagerWithDaoTest {

    @Test
    void managerAcceptsCorrectPasswordAndRejectsWrongPassword() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("correct-password"))
                        .roles("READER")
                        .build());

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        ProviderManager manager = new ProviderManager(List.of(dao));

        Authentication valid = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "correct-password"));

        assertThat(valid.isAuthenticated()).isTrue();
        assertThat(valid.getName()).isEqualTo("lan");
        assertThat(valid.getAuthorities())
                .extracting(authority -> authority.getAuthority())
                .contains("ROLE_READER");

        assertThatThrownBy(() -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "wrong-password")))
                .isInstanceOf(BadCredentialsException.class);
    }
}
~~~

Ví dụ dùng constructor `DaoAuthenticationProvider(UserDetailsService)` dành cho các phiên bản Spring Security hiện đại. Nếu dự án dùng phiên bản cũ hơn với API khởi tạo khác, điều chỉnh phần thiết lập provider theo phiên bản đó.

Điểm khác biệt so với Mockito: test này gọi `UserDetailsService`, kiểm tra password hash bằng `PasswordEncoder.matches(...)` và tạo `Authentication` đã xác thực qua provider thực. Nó vẫn **chưa xác minh** việc filter, endpoint hay quyền HTTP được cấu hình chính xác.

## 6. Liên hệ với kiểm thử HTTP bằng spring-security-test

Trong ứng dụng Servlet, filter xử lý đăng nhập (ví dụ `BasicAuthenticationFilter`) tạo một `Authentication` chưa xác thực rồi gọi `AuthenticationManager` đã cấu hình. Nếu xác thực thành công, kết quả được dùng trong `SecurityContext` để tiếp tục xử lý yêu cầu và kiểm tra quyền. Nếu thất bại, filter và entry point quyết định phản hồi HTTP.

Với ứng dụng Spring Boot đã có `SecurityFilterChain` dùng HTTP Basic, tài khoản `lan` / `correct-password`, endpoint `/api/profile` yêu cầu đăng nhập và `/api/admin` yêu cầu `ADMIN`, có thể viết kiểm thử như sau:

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
class AuthenticationManagerHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validCredentialsCanAccessProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("lan", "correct-password")))
                .andExpect(status().isOk());
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
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

Đây là **mẫu test phụ thuộc vào cấu hình ứng dụng**: cần cung cấp endpoint thật và đảm bảo `UserDetailsService`/`AuthenticationManager` trong test context trỏ đúng provider dự kiến. Mã `401` với credential sai và `403` với thiếu quyền tương ứng với cấu hình HTTP Basic thông thường; nếu dùng form login, API key hoặc entry point tùy chỉnh, hãy điều chỉnh assertion theo phản hồi thiết kế.

`httpBasic(...)` gửi header Basic đến filter để kiểm tra thông tin đăng nhập. Trái lại, `@WithMockUser` và request postprocessor `user(...)` thường tạo sẵn một `Authentication` trong `SecurityContext`. Chúng hữu ích để kiểm tra phân quyền nhưng **không chứng minh** `AuthenticationManager` đã chọn provider hay kiểm tra credentials thật.

| Điều muốn xác nhận | Tầng kiểm thử phù hợp |
| --- | --- |
| Provider nào được xét, provider nào bị bỏ qua và khi nào dừng chuỗi | JUnit + Mockito trên `ProviderManager` |
| Mật khẩu đúng/sai được kiểm tra thực sự | `ProviderManager` + `DaoAuthenticationProvider` + encoder thật |
| Yêu cầu HTTP đi qua bộ lọc, xác thực, phân quyền rồi trả kết quả | `MockMvc` với cấu hình Spring Security thực |
| Controller chỉ cho phép người đã có vai trò phù hợp | `MockMvc` với `@WithMockUser` hoặc `user(...)` |
| JWT được xác minh chữ ký, issuer, audience | Kiểm thử `JwtDecoder`/validator và resource server thật |
| Endpoint từ chối/cho phép một người dùng có JWT giả lập | `jwt()` trong `spring-security-test`; bước giải mã JWT thật được bỏ qua |

## 7. Cơ chế tương ứng trong Reactive và OAuth2/OIDC

**Spring WebFlux** dùng giao diện `ReactiveAuthenticationManager` với hợp đồng phản hồi `Mono<Authentication>` thay cho `AuthenticationManager` đồng bộ. Khi có nhiều cách xác thực, triển khai điều phối Reactive như `DelegatingReactiveAuthenticationManager` có thể được sử dụng; cách biểu diễn kết quả của Reactor và hành vi khi một manager không xác thực được cần được kiểm tra theo hợp đồng Reactive, không suy diễn toàn bộ logic `ProviderManager` sang WebFlux.

Với `WebTestClient` gắn vào ứng dụng Reactive có bật HTTP Basic, có thể kiểm chứng thông tin sai ở tầng HTTP:

~~~java
webTestClient.get()
        .uri("/api/profile")
        .headers(headers -> headers.setBasicAuth("lan", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đoạn trên là phần thân của test đã có `webTestClient` được cấu hình; endpoint và cơ chế HTTP Basic cần tồn tại trong ứng dụng. Để giả lập người dùng trong WebFlux, `spring-security-test` còn hỗ trợ các tiện ích phù hợp với `WebTestClient`, nhưng kết quả giả lập cũng không kiểm chứng xác thực mật khẩu thật.

Với **JWT bearer token**, việc filter chuyển token cho các thành phần xác thực trong resource server khác với luồng username/password. Kiểm thử chỉ dùng `jwt()` trong `spring-security-test` giả lập principal và authorities, nên không đủ chứng minh chữ ký hoặc các claim được validator kiểm tra chính xác. Với **OAuth2 Login/OIDC**, các tiện ích `oauth2Login()` và `oidcLogin()` giúp đặt ngữ cảnh người dùng sau đăng nhập; kiểm chứng redirect, callback, trao đổi mã và token thực tế phải sử dụng một tầng kiểm thử khác.

## 8. Lỗi thường gặp và cách nhận diện

**Lẫn lộn supports với authenticate.** `supports(...)` chỉ cho biết provider có khả năng xử lý **loại token**. Không kiểm tra credentials hay phân quyền tại đó. Test nên xác nhận provider không hỗ trợ **không bị gọi**.

**Cho rằng bất kỳ AuthenticationException nào cũng dừng chuỗi.** `ProviderManager` có thể tiếp tục sau `BadCredentialsException` và dừng ngay sau `AccountStatusException` hoặc `InternalAuthenticationServiceException`. Cần có cả test “tiếp tục” lẫn “dừng”.

**Hai provider cùng hỗ trợ token nhưng chấp nhận credentials theo quy tắc khác nhau.** Đăng ký provider sai thứ tự hoặc có provider chấp nhận quá rộng có thể khiến yêu cầu không được kiểm chứng như dự kiến. Hãy kiểm tra thứ tự, khả năng xử lý và toàn bộ các nhánh có thể trả thành công.

**Bỏ qua parent manager.** Một test chỉ nhìn vào danh sách provider con có thể kết luận nhầm “không có provider nào xử lý”, trong khi parent vẫn xác thực thành công. Kiểm thử cần mô tả rõ có/không có parent.

**Dùng token đã xác thực làm đầu vào kiểm tra đăng nhập.** `UsernamePasswordAuthenticationToken.authenticated(...)` phù hợp để mock kết quả provider trong test routing, nhưng trong test kiểm tra mật khẩu thật phải dùng `unauthenticated(...)` để provider xác thực đầu vào chưa được tin cậy.

**Tưởng gọi AuthenticationManager sẽ tự đăng nhập người dùng vào session.** Việc đặt `SecurityContext`, lưu context hoặc tạo session do các thành phần khác đảm nhiệm trong luồng ứng dụng. Kiểm thử trực tiếp manager không chứng minh các hành vi đó.

**Đặt assertion HTTP không khớp cấu hình.** Sai credentials với HTTP Basic thường nhận `401`; đã xác thực nhưng thiếu role thường nhận `403`. Form login có thể chuyển hướng; HTTP POST thất bại `403` cũng có thể do CSRF. Hãy xác định đúng tầng lỗi trước khi kết luận provider có vấn đề.

## 9. Bài thực hành

1. Mở rộng `ProviderManagerRoutingTest` bằng một ca provider đầu tiên ném `BadCredentialsException` và provider sau trả về `null`. Giải thích vì sao không có kết quả xác thực thành công và ngoại lệ nào được báo khi hết chuỗi.
2. Thêm provider đầu tiên ném `LockedException`; kiểm tra provider thứ hai không được gọi, dù nó có thể xác thực token đầu vào.
3. Tạo một provider tùy chỉnh cho loại `Authentication` riêng (ví dụ API key) và ghép với `DaoAuthenticationProvider`. Thử cả hai loại token, sau đó đảo thứ tự để quan sát khi nào thứ tự có ảnh hưởng thực tế.
4. Kiểm thử một endpoint thật bằng `MockMvc` và `httpBasic(...)`, rồi thay bằng `@WithMockUser`. Giải thích bằng chứng nào về `AuthenticationManager` mà test thứ hai không cung cấp.

Một bộ kiểm thử tốt sẽ kiểm chứng **đường đi của token**, **điều kiện thành công/thất bại của provider**, và **tác động lên phản hồi HTTP** ở những tầng phù hợp. Với cách đó, thay đổi cấu hình Spring Security hay thêm cơ chế xác thực mới ít có khả năng âm thầm mở ra đường đăng nhập ngoài dự kiến.
