# ProviderManager và danh sách AuthenticationProvider trong Spring Security

> **Chủ đề:** Spring Security → Authentication → **Bộ máy xác thực**. Bài này giải thích vai trò của `ProviderManager`, cách nó duyệt danh sách `AuthenticationProvider`, ý nghĩa `supports(...)`, `authenticate(...)`, thứ tự provider, trường hợp trả `null` hoặc ném lỗi, parent manager, xóa credentials, phát sự kiện và cách cấu hình/kiểm thử an toàn. Ví dụ Java 17+ sử dụng Spring Security 6.5.x. Nội dung tập trung vào cơ chế **xác thực danh tính**, không thay thế thiết kế phân quyền cho tài nguyên.

## 1. Tại sao cần ProviderManager?

Một ứng dụng có thể nhận nhiều kiểu bằng chứng để xác thực: tên đăng nhập và mật khẩu từ form, API key của một client, bearer token từ bên ngoài, hoặc thông tin đăng nhập qua nhà cung cấp danh tính. Mỗi kiểu thường đòi hỏi cách kiểm tra khác nhau. Bộ lọc HTTP không nên biết mọi quy tắc kiểm tra mật khẩu, khóa API hay token.

Spring Security tách các trách nhiệm:

- **`Authentication`:** đối tượng mô tả yêu cầu xác thực (chưa đáng tin) hoặc kết quả đã xác thực, gồm principal, credentials, authorities và trạng thái.
- **`AuthenticationManager`:** interface với phương thức `authenticate(Authentication)`, đóng vai trò cổng nhận yêu cầu.
- **`ProviderManager`:** implementation phổ biến của `AuthenticationManager`, lần lượt thử các `AuthenticationProvider` đã được cấu hình.
- **`AuthenticationProvider`:** implementation biết cách xác thực một hoặc nhiều kiểu `Authentication`; ví dụ `DaoAuthenticationProvider` xử lý username/password thông qua `UserDetailsService` và `PasswordEncoder`.
- **Filter/cơ chế gọi manager:** như `UsernamePasswordAuthenticationFilter` hoặc filter xử lý HTTP Basic, chuyển request thành `Authentication` rồi gọi manager. Khi thành công, thành phần gọi sẽ gắn kết quả vào `SecurityContext` theo luồng được cấu hình.

Một ứng dụng không nhất thiết chỉ có một `ProviderManager` hoặc chỉ có một `SecurityFilterChain`. Mối liên hệ phải được xác định theo cấu hình thực tế.

```text
HTTP request
    │
    ▼
Spring Security filter phù hợp
    │ tạo Authentication request (chưa xác thực)
    ▼
AuthenticationManager.authenticate(request)
    │
    ▼
ProviderManager
    ├─ Provider #1: supports(request.getClass())?
    │      ├─ không → bỏ qua
    │      ├─ có → authenticate(request)
    │      │          ├─ thành công → trả Authentication, dừng
    │      │          ├─ null → chưa quyết định, thử tiếp
    │      │          └─ AuthenticationException → xem quy tắc xử lý lỗi
    ├─ Provider #2: xét theo thứ tự
    ├─ Provider #3: xét theo thứ tự
    └─ optional parent AuthenticationManager khi chưa có kết quả
    │
    ├─ SUCCESS → Authentication đã xác thực
    └─ FAILURE → AuthenticationException
```

Lưu ý: **`ProviderManager` chỉ lựa chọn và điều phối các provider được trao cho nó**. Việc kiểm tra mật khẩu, token, trạng thái user hay tính đúng đắn của credential nằm ở provider tương ứng.

## 2. Hợp đồng của AuthenticationProvider: supports và authenticate

`AuthenticationProvider` là một interface có hai phương thức cốt lõi:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Mã trên trình bày chữ ký cốt lõi, không phải một class chạy độc lập.

### 2.1. supports(Class<?>) chọn **loại token**, chưa chứng minh credential đúng

`supports(...)` trả `true` nếu provider **có khả năng xem xét** đối tượng `Authentication` thuộc kiểu được truyền vào. Ví dụ provider username/password thường hỗ trợ `UsernamePasswordAuthenticationToken`; provider chuyên xử lý API key sẽ hỗ trợ một loại token khác.

```java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
```

Đây là đoạn method trong một implementation `AuthenticationProvider`. Dùng `isAssignableFrom(...)` hỗ trợ các subtype tương thích; so sánh `==` chỉ phù hợp khi chủ đích là **đúng một class**. Tránh một provider tuyên bố hỗ trợ mọi kiểu token rồi âm thầm xác thực thiếu kiểm soát.

**`supports(...) == true` không có nghĩa credential đúng** và không cam kết `authenticate(...)` sẽ trả kết quả khác `null`. Nó chỉ xác định rằng provider có thể xem xét sâu hơn trong runtime.

### 2.2. authenticate(Authentication) có ba kết quả ý nghĩa

| Kết quả từ provider đã được gọi | Ý nghĩa | ProviderManager làm gì? |
| --- | --- | --- |
| Trả một `Authentication` khác `null` đã xác thực | Provider có kết quả thành công | Dùng kết quả đó, không gọi các provider còn lại trong danh sách |
| Trả `null` | Provider không thể quyết định cho instance cụ thể này | Tiếp tục provider kế tiếp có `supports(...)` phù hợp |
| Ném `AuthenticationException` | Provider xác định một lỗi/thất bại xác thực | Thông thường ghi nhận và có thể tiếp tục; **một số loại lỗi dừng ngay** |

Không nên coi `return null` là cách diễn đạt “mật khẩu sai” một cách tùy tiện. Với credential thuộc **nguồn danh tính mà provider chịu trách nhiệm**, sai credential nên dẫn đến lỗi thích hợp như `BadCredentialsException`. `null` dùng khi provider **thực sự không thể xử lý trường hợp cụ thể** và có provider khác được phép xử lý theo chính sách.

Bản thân `authenticate(...)` không được trả principal được tin cậy chỉ vì request ban đầu tự điền `authenticated=true` hoặc tự khai authorities. Các thuộc tính đáng tin phải do một nguồn xác thực phù hợp kiểm tra/cấp.

## 3. Thứ tự duyệt: hiểu rõ khi có nhiều provider

Giả sử `ProviderManager` nhận danh sách:

```text
0. CorporatePasswordProvider
1. LocalPasswordProvider
2. ApiKeyProvider
```

Với `UsernamePasswordAuthenticationToken`, cả provider 0 và 1 có thể trả `supports(...) == true`, còn provider 2 chỉ nhận custom API-key token nên bị bỏ qua. Với một API-key token, hai provider đầu bị bỏ qua mà không gọi `authenticate(...)`.

Trong một lượt `authenticate(request)`:

1. Manager duyệt theo **thứ tự danh sách đã cấu hình**, không tự sắp xếp theo độ “ưu tiên” của thuật toán.
2. Nếu `supports(request.getClass())` là `false`, provider đó bị bỏ qua.
3. Nếu `supports(...)` là `true`, manager gọi `authenticate(request)`.
4. Nếu provider trả `null`, manager tiếp tục. Nếu trả `Authentication` thành công, manager giữ kết quả và dừng duyệt.
5. Một `AuthenticationException` thường được ghi nhận, nhưng provider kế tiếp vẫn có thể xác thực thành công; kết quả thành công sau đó thay thế lỗi trước đó. Nếu không ai thành công, manager ném lỗi xác thực cuối cùng phù hợp.
6. Nếu một provider ném `AccountStatusException` (chẳng hạn account bị khóa/vô hiệu hóa), manager **dừng ngay** và không thử provider tiếp theo. `InternalAuthenticationServiceException` cũng được xử lý như lỗi nghiêm trọng trong implementation thông dụng và dừng luồng.
7. Nếu không có provider nào trả kết quả, manager có thể thử **parent AuthenticationManager** được cấu hình. Nếu cả đường local và parent đều không xác thực được, request thất bại; khi không có provider phù hợp và không có lỗi khác, thường là `ProviderNotFoundException`.

**Điểm bảo mật thiết yếu:** cấu hình hai provider cùng chấp nhận username/password **có thể tạo đường fallback**. Một provider ném `BadCredentialsException` không tự bảo đảm manager ngừng duyệt; provider khác vẫn có thể cho đăng nhập. Nếu chính sách yêu cầu “tài khoản corporate phải được corporate provider xác thực”, hãy phân tách namespace/loại token hoặc áp dụng chính sách chặn fallback có chủ đích. Không dựa vào thứ tự tình cờ.

### Minh họa ba trường hợp

```text
CASE A: request = local:mai / đúng mật khẩu
  Corporate.supports = true -> Corporate.authenticate = null (không thuộc realm)
  Local.supports     = true -> Local.authenticate = SUCCESS
  ApiKey             = không được thử
  Kết quả            = thành công

CASE B: request = local:mai / sai mật khẩu
  Corporate.supports = true -> Corporate.authenticate = null
  Local.supports     = true -> Local.authenticate = BadCredentialsException
  ApiKey.supports    = false -> bỏ qua
  Parent             = không cấu hình
  Kết quả            = BadCredentialsException

CASE C: request là kiểu token chưa provider nào hỗ trợ
  Corporate.supports = false
  Local.supports     = false
  ApiKey.supports    = false
  Parent             = không cấu hình
  Kết quả            = ProviderNotFoundException
```

**Không nhầm `ProviderNotFoundException` với sai mật khẩu.** Lỗi này thường cho biết kiểu `Authentication` được gửi đến manager chưa có provider phù hợp trong danh sách hiện hành; mật khẩu sai ở provider hỗ trợ username/password thường dẫn đến `BadCredentialsException` hoặc lỗi cụ thể khác.

## 4. Những ngoại lệ quyết định dừng hay tiếp tục

| Trường hợp | Hành vi cần hiểu | Hướng xử lý |
| --- | --- | --- |
| `supports(...) == false` | Không gọi `authenticate(...)` của provider đó | Kiểm tra token class từ filter và provider registration |
| `authenticate(...) == null` | Chưa quyết định; manager xét tiếp | Chỉ trả null khi có chính sách delegation hợp lệ |
| `BadCredentialsException` | Thông thường vẫn có thể xét provider tiếp; nếu không ai thành công, request bị từ chối | Không “fail open” sang provider yếu hơn |
| `UsernameNotFoundException` | Là một loại lỗi xác thực, không có nghĩa user được tạo tự động | Không rò rỉ tồn tại username; chính sách hiển thị lỗi phù hợp |
| `DisabledException`/`LockedException` | Thuộc họ `AccountStatusException`; phải dừng ngay | Không mở đường đăng nhập thay thế cho tài khoản bị khóa |
| `InternalAuthenticationServiceException` | Lỗi bên trong dịch vụ xác thực; implementation `ProviderManager` chuẩn dừng xử lý | Phân biệt outage và mật khẩu sai, xử lý/cảnh báo an toàn |
| Không provider hỗ trợ, không parent xử lý | `ProviderNotFoundException` | Kiểm tra cấu hình provider, subtype token và manager nào đang được gọi |
| Provider trả `Authentication` thành công | Dừng duyệt, trả kết quả sau các bước hậu xử lý | Chỉ provider đáng tin được tạo token đã xác thực |

**Lưu ý với parent:** parent manager là một đường xác thực bổ sung, không mặc định là “phương án dự phòng an toàn”. Trong cấu hình cụ thể, parent có thể được hỏi khi local providers chưa tạo kết quả, kể cả một vài trường hợp local provider đã thất bại; phải kiểm tra ranh giới và chính sách để tránh account thuộc realm này được xác thực nhầm bởi realm khác.

## 5. Ví dụ Java 17+ hoàn chỉnh: ba provider, hai loại token

Ví dụ chạy **không cần Spring Boot web server**. Dùng Spring Security Core, tạo `ProviderManager` theo thứ tự tường minh để quan sát `supports`, `return null`, kết quả thành công, credential sai và token không được hỗ trợ. Code tự chứa tài khoản/password và API key giả cho mục đích học tập; **không dùng phương pháp so sánh literal trong production**.

### 5.1. Cấu trúc project

```text
provider-manager-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ProviderManagerDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'provider-manager-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.ProviderManagerDemo'
}
```

`src/main/java/demo/ProviderManagerDemo.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderManagerDemo {

    public static void main(String[] args) {
        ProviderManager manager = new ProviderManager(List.of(
                new CorporatePasswordProvider(),
                new LocalPasswordProvider(),
                new ApiKeyProvider()
        ));

        System.out.println("-- password --");
        Authentication local = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "local:mai", "local-pass"));
        show(local);

        System.out.println("-- api key --");
        Authentication api = manager.authenticate(
                ApiKeyRequest.unauthenticated("key-123"));
        show(api);

        System.out.println("-- wrong password --");
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "local:mai", "wrong"));
        } catch (BadCredentialsException ex) {
            System.out.println("failure: BadCredentialsException");
        }

        System.out.println("-- unsupported token --");
        try {
            manager.authenticate(
                    new TestingAuthenticationToken("tester", "unused"));
        } catch (ProviderNotFoundException ex) {
            System.out.println("failure: ProviderNotFoundException");
        }
    }

    private static void show(Authentication auth) {
        String authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("result: name=" + auth.getName()
                + ", authenticated=" + auth.isAuthenticated()
                + ", credentials="
                + (auth.getCredentials() == null ? "absent" : "present")
                + ", authorities=" + authorities);
    }

    // Chỉ quản lý tên thuộc realm "corp:".
    static final class CorporatePasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            String username = request.getName();
            if (!username.startsWith("corp:")) {
                System.out.println("corp: abstain");
                return null;
            }
            if (!Objects.equals(request.getCredentials(), "corp-pass")) {
                throw new BadCredentialsException("Invalid credentials");
            }
            System.out.println("corp: accepted");
            return UsernamePasswordAuthenticationToken.authenticated(
                    username, null,
                    List.of(new SimpleGrantedAuthority("ROLE_CORP")));
        }
    }

    // Chỉ quản lý tên thuộc realm "local:".
    static final class LocalPasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            String username = request.getName();
            if (!username.startsWith("local:")) {
                System.out.println("local: abstain");
                return null;
            }
            if (!Objects.equals(request.getCredentials(), "local-pass")) {
                throw new BadCredentialsException("Invalid credentials");
            }
            System.out.println("local: accepted");
            return UsernamePasswordAuthenticationToken.authenticated(
                    username, null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    // Chỉ hỗ trợ ApiKeyRequest, không xử lý username/password.
    static final class ApiKeyProvider implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return ApiKeyRequest.class.isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            if (!Objects.equals(request.getCredentials(), "key-123")) {
                throw new BadCredentialsException("Invalid API key");
            }
            System.out.println("api: accepted");
            return ApiKeyRequest.authenticated("batch-job");
        }
    }

    // Token demo. Constructor private để chỉ factory được tạo trạng thái.
    private static final class ApiKeyRequest extends AbstractAuthenticationToken {
        private final String principal;
        private String credentials;

        private ApiKeyRequest(
                String principal,
                String credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(authenticated);
        }

        static ApiKeyRequest unauthenticated(String key) {
            return new ApiKeyRequest("pending-api", key, List.of(), false);
        }

        static ApiKeyRequest authenticated(String principal) {
            return new ApiKeyRequest(
                    principal, null,
                    List.of(new SimpleGrantedAuthority("ROLE_SERVICE")), true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }
    }
}
```

Từ thư mục chứa `build.gradle`, chạy bằng Gradle tương thích Java 17:

```bash
gradle run
```

Nếu project có Gradle Wrapper, dùng `./gradlew run` (macOS/Linux) hoặc `gradlew.bat run` (Windows). Chỉ phần stdout do chương trình in (không tính dòng build của Gradle) sẽ là:

```text
-- password --
corp: abstain
local: accepted
result: name=local:mai, authenticated=true, credentials=absent, authorities=ROLE_USER
-- api key --
api: accepted
result: name=batch-job, authenticated=true, credentials=absent, authorities=ROLE_SERVICE
-- wrong password --
corp: abstain
failure: BadCredentialsException
-- unsupported token --
failure: ProviderNotFoundException
```

### 5.2. Vì sao output đúng?

- Với username `local:mai`, `CorporatePasswordProvider.supports(...)` trả true vì token thuộc loại username/password; nhưng `authenticate(...)` phát hiện sai realm và trả `null`. `LocalPasswordProvider` tiếp tục, kiểm tra mật khẩu mô phỏng thành công và trả token có `ROLE_USER`.
- Khi local provider trả token khác `null`, manager dừng; `ApiKeyProvider` không được gọi cho request này.
- Với `ApiKeyRequest`, hai provider password đều trả `supports(...) == false`. Manager chỉ gọi `ApiKeyProvider`, kiểm tra API key và trả principal `batch-job`.
- Với password sai, corporate provider bỏ qua đúng namespace; local provider ném `BadCredentialsException`; API key provider không hỗ trợ loại token và không có parent, nên lỗi được trả lại cho caller.
- `TestingAuthenticationToken` là loại token phục vụ test không được ba provider cấu hình hỗ trợ; manager trả `ProviderNotFoundException`.
- Cả hai kết quả thành công đều có credentials `null` vì **provider chủ động không đưa credential vào token kết quả**. Điều này là cách tốt cho custom provider. Ngoài ra `ProviderManager` mặc định có thể gọi `eraseCredentials()` trên kết quả hỗ trợ `CredentialsContainer`; ví dụ này không dùng token chứa raw secret để phụ thuộc vào việc dọn dẹp sau đó.

**Giới hạn quan trọng:** ví dụ cố ý dùng credential cố định để dễ theo dõi luồng điều phối. Với ứng dụng thật, **mật khẩu** cần được kiểm tra bằng `PasswordEncoder` và hash đã lưu qua `DaoAuthenticationProvider`/`UserDetailsService`; **API key** cần lưu dưới dạng an toàn, so sánh phù hợp, kiểm soát thời hạn/thu hồi và không xuất hiện trong log/source code. Mọi đường xác thực phải chạy qua HTTPS.

### 5.3. Tự thay đổi để kiểm chứng chính sách

1. Đảo thứ tự `CorporatePasswordProvider` và `LocalPasswordProvider`. Với namespace tách bạch và các provider trả null đúng chỗ, kết quả thành công không đổi nhưng thứ tự các provider được gọi thay đổi.
2. Đổi request sang `corp:an`/`corp-pass`. Corporate provider tự xác thực, local provider không được gọi; `ROLE_CORP` được cấp.
3. Đổi mật khẩu của request `corp:an` thành sai. Corporate provider báo `BadCredentialsException`; thử phân tích việc một provider có cùng token type đặt sau có thể tiếp tục như thế nào. **Không** sửa code thành fallback chấp nhận mọi password.
4. Tạm xóa `LocalPasswordProvider` khỏi danh sách. Request `local:mai` không có provider nào xác thực được; vì corporate trả null và API key không hỗ trợ, kết quả phù hợp là `ProviderNotFoundException`.
5. Thêm test ghi lại số lần `authenticate(...)` của từng provider để khẳng định provider sau thành công không được gọi; không ghi lại raw credential.

Các thay đổi này chỉ dùng để học cơ chế; không thay đổi quy tắc bảo mật của môi trường production.

## 6. DaoAuthenticationProvider trong hệ thống username/password thực tế

Ở ứng dụng thật, thường **không cần viết lại provider so sánh password**. Với username/password, `DaoAuthenticationProvider` đã cung cấp đường đi được Spring Security hỗ trợ:

```text
UsernamePasswordAuthenticationFilter / BasicAuthenticationFilter
    ↓
UsernamePasswordAuthenticationToken (unauthenticated)
    ↓
ProviderManager
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    ├── kiểm tra disabled / locked / expired theo UserDetails
    └── PasswordEncoder.matches(rawPassword, storedHash)
    ↓
UsernamePasswordAuthenticationToken (authenticated)
    └── principal thường là UserDetails; authorities từ user nguồn
```

Ví dụ cấu hình **chỉ phần AuthenticationManager**, dùng Spring Security 6.5.x; có thể đặt trong một Spring `@Configuration` phù hợp. Đây là snippet cần bổ sung bean imports/configuration, **không phải một file Java độc lập**:

```java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider passwordProvider =
            new DaoAuthenticationProvider(users);
    passwordProvider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(passwordProvider);
}
```

Đây là ví dụ **tự tạo manager rõ ràng**. Khi dùng Spring Boot, SecurityFilterChain/auto-configuration có thể đã xây hoặc lắp AuthenticationManager phù hợp; không nên khai báo thêm bean cùng chức năng chỉ để “có nhiều provider”. Và **đừng mặc định việc tạo một `@Bean AuthenticationProvider` đồng nghĩa mọi filter/manager đều tự động dùng bean đó**: phải kiểm tra cách bean được đăng ký vào manager của đúng filter chain.

### Khi có nhiều cơ chế

Giả sử hệ thống vừa có form login qua tài khoản nội bộ vừa có JWT Resource Server cho API:

- Form login tạo request kiểu `UsernamePasswordAuthenticationToken`, có thể đi đến `DaoAuthenticationProvider`.
- Bearer token từ API thường được xử lý bởi `BearerTokenAuthenticationFilter` và provider/manager tương ứng, chẳng hạn `JwtAuthenticationProvider`.
- Việc một application có hai cơ chế **không tự bảo đảm** chúng dùng chung chính xác một `ProviderManager`. `SecurityFilterChain` và cấu hình `AuthenticationManagerResolver` (nếu có) ảnh hưởng đường xử lý thực tế.

Câu hỏi cần trả lời từ cấu hình: request thuộc filter chain nào, filter nào tạo token gì, manager nào được gọi, provider nào của manager đó `supports(...) == true`, và kết quả sẽ được đưa vào `SecurityContext`/session theo cơ chế nào?

## 7. Parent AuthenticationManager: tái sử dụng có kiểm soát

Một `ProviderManager` có thể trỏ tới **parent `AuthenticationManager`**. Mô hình có ích khi nhiều tập provider riêng cùng dùng một nhóm cơ chế chung:

```text
Web chain A ─> ProviderManager A [A1, A2] ──┐
                                           ├─ parent AuthenticationManager [P1, P2]
Web chain B ─> ProviderManager B [B1] ─────┘
```

Manager con thử provider local trước. Nếu chưa có kết quả hợp lệ và không rơi vào lỗi khiến luồng phải dừng ngay, nó có thể gọi parent. Parent có thể là một `ProviderManager` khác, cũng có danh sách provider riêng. Điều này cho phép chia sẻ provider nhưng làm tăng độ phức tạp của ranh giới xác thực.

**Kiểm soát thiết kế:** parent không được vô tình coi credential bị bác ở realm A là đủ để đăng nhập vào realm B; cần quyết định chính sách phân tuyến. Nếu nhiều manager có cùng event publisher, cần chú ý khả năng phát event trùng khi request đi qua parent. Không giải quyết lỗi xác thực bằng cách thêm parent “chấp nhận cho qua” để làm endpoint hoạt động.

## 8. Sau khi xác thực thành công: credentials và sự kiện

### 8.1. Xóa credentials

`ProviderManager` mặc định bật `eraseCredentialsAfterAuthentication`. Nếu token kết quả triển khai `CredentialsContainer`, manager gọi `eraseCredentials()` sau khi xác thực thành công để giảm thời gian raw password/secret còn trong bộ nhớ hoặc session.

```java
// Tùy chỉnh có chủ đích trong môi trường đặc biệt:
ProviderManager manager = new ProviderManager(providers);
manager.setEraseCredentialsAfterAuthentication(true);
```

Đây là snippet minh họa, cần có biến `providers` chứa danh sách provider. Giá trị `true` đã là mặc định trong `ProviderManager` chuẩn; không cần gọi lại trong cấu hình thông thường. **Không khuyến khích đặt false** để chữa sự cố cache: nếu giữ cùng reference `UserDetails` ở cache và trong result, `eraseCredentials` có thể ảnh hưởng object được cache, khiến lần xác thực sau gặp lỗi. Thiết kế bản sao principal/cache phù hợp và tránh lưu secret trong object chia sẻ là giải pháp an toàn hơn.

Custom token nên trả kết quả không chứa bí mật ngay từ provider, và nếu có state nhạy cảm mutable cần hỗ trợ xóa đúng khi `CredentialsContainer` được gọi. Không giả định Spring Security dọn sạch mọi object, mọi reference hoặc mọi log.

### 8.2. Authentication events

`ProviderManager` có thể dùng `AuthenticationEventPublisher` để phát sự kiện success/failure; ví dụ `DefaultAuthenticationEventPublisher` ánh xạ các ngoại lệ thông dụng thành event. Khi tự tạo một `ProviderManager` bằng code, giá trị mặc định của publisher là implementation **không phát event**; muốn nhận event cần cấu hình publisher thích hợp. Với Spring Boot/HTTP security, cơ chế wiring có thể khác và phải kiểm tra cấu hình đang sử dụng.

Event hữu ích cho audit và theo dõi đăng nhập thất bại, nhưng tuyệt đối không ghi password, bearer token, API key hay object principal chứa bí mật vào log. Khi dùng manager cha/con, cần tránh cấu hình event phát trùng.

## 9. Phân biệt rõ authentication và authorization

`AuthenticationProvider` kiểm tra **bằng chứng danh tính** và tạo `Authentication` hợp lệ kèm authorities. `AuthorizationManager` hoặc các rule `authorizeHttpRequests`/`@PreAuthorize` xét authorities cùng ngữ cảnh để quyết định truy cập.

```text
Authentication request (credential)
      → ProviderManager / AuthenticationProvider
      → Authentication result (principal, authorities)
      → SecurityContext
      → AuthorizationManager quyết định quyền cho hành động cụ thể
```

Không nên đặt luật “user được sửa đơn hàng nào” trong một provider chỉ vì provider đã biết username. Quyền dựa trên tài nguyên, owner hoặc tenant nên được đánh giá ở vị trí authorization phù hợp. Kết quả xác thực thành công **không có nghĩa** được phép mọi endpoint; authorities rỗng vẫn có thể hợp lệ theo cơ chế.

## 10. Kiểm thử và chẩn đoán lỗi theo thứ tự

### Ma trận kiểm thử tối thiểu

| Bài test | Kết quả cần quan sát |
| --- | --- |
| Token type chỉ một provider hỗ trợ | Chỉ provider đó được gọi `authenticate(...)` |
| Hai provider cùng hỗ trợ; provider trước trả `null` | Provider sau được thử |
| Provider trước trả thành công | Provider sau không được gọi |
| Provider trước ném `BadCredentialsException`, provider sau có thể thành công | Cần xác minh chính sách fallback; kết quả tùy danh sách và provider |
| Provider ném `LockedException` hoặc `DisabledException` | Không thử provider sau/parent như đường vòng |
| Không provider hỗ trợ, không parent | `ProviderNotFoundException` |
| Credentials sai tại provider phù hợp và không có provider thành công | Authentication thất bại với `AuthenticationException` thích hợp |
| Parent được cấu hình | Kiểm tra chính xác khi nào parent được gọi và ranh giới danh tính |
| Token thành công có `CredentialsContainer` | Credentials được xóa theo cấu hình; không xuất vào response/log |
| Cấu hình nhiều `SecurityFilterChain` | Request đến đúng chain và manager dự kiến |
| Custom publisher/parent | Event đúng số lần, không lộ dữ liệu bí mật |

### Cách chẩn đoán một login thất bại

1. **Xác minh HTTP route:** request vào đúng `SecurityFilterChain` chưa? Matcher nào chọn chain? Filter nào đọc credential?
2. **Xác minh token type:** filter tạo `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken` hay custom token? Không đoán từ tên endpoint.
3. **Xác minh manager thực tế:** filter sử dụng manager nào? Bean trong application context có thật sự được gắn vào chain đó?
4. **Liệt kê provider theo thứ tự:** mỗi provider `supports(token.getClass())` trả gì? Provider nào đã được gọi?
5. **Xem kết quả từng provider:** `null`, success, hay exception? Nếu exception, thuộc họ nào và có dừng luôn không?
6. **Kiểm tra parent:** có được cấu hình không, đã được hỏi chưa và có nguy cơ fallback ngoài chính sách không?
7. **Sau thành công:** principal/authorities chính xác chưa, context được lưu/khôi phục theo cơ chế gì? Tránh nhầm lỗi authorization 403 thành sai password.
8. **Audit an toàn:** log class/type, bước xử lý, mã lỗi và correlation ID; không log password, API key, access token hoặc raw `Authentication`.

Có thể bật log mức DEBUG cho package Spring Security ở **môi trường phát triển kiểm soát** để theo dõi tuyến xử lý, nhưng cần xem xét dữ liệu được ghi, thời gian giữ và mức độ nhạy cảm. Tắt log chi tiết sau khi phân tích xong, nhất là ở môi trường chứa credential thật.

## 11. Lỗi thiết kế thường gặp

1. **Cho rằng `supports=true` là xác thực thành công.** `supports` chỉ kiểm tra khả năng xử lý theo loại token; credential còn phải được kiểm tra.
2. **Trả `null` khi mật khẩu sai trong provider duy nhất chịu trách nhiệm một realm.** Điều này có thể mở đường cho provider khác; trả lỗi đúng ngữ nghĩa và thiết kế fallback có kiểm soát.
3. **Tin rằng `BadCredentialsException` luôn dừng duyệt.** `ProviderManager` thường có thể thử provider sau; kiểm tra loại exception và kết quả cuối.
4. **Xếp nhiều provider cùng token type mà không kiểm tra thứ tự.** Kết quả và fallback có thể khác ý định, đặc biệt khi source user trùng username.
5. **Không phân biệt `ProviderNotFoundException` với user không tồn tại.** Đây là dấu hiệu manager/provider thiếu khả năng xử lý token hiện tại, không tự chứng minh user sai.
6. **Tự đổi cờ `authenticated` trong controller.** Bỏ qua quá trình kiểm tra credential. Chỉ provider tin cậy được tạo kết quả authenticated.
7. **Dùng một kiểu token cho mọi credential mà không phân ranh giới.** API key và password có ngữ nghĩa/chu kỳ khác; tạo token/logic nhận diện rõ ràng khi thật sự cần.
8. **Tự viết provider kiểm tra password bằng so sánh chuỗi.** Trong production ưu tiên `DaoAuthenticationProvider` + `UserDetailsService` + `PasswordEncoder`, lưu password hash mạnh.
9. **Không xử lý trạng thái locked/disabled như lỗi chặn.** Tránh cấu hình provider kế tiếp “cứu” tài khoản bị khóa.
10. **Bật nhiều manager cha/con mà không kiểm tra event/audit.** Có thể đếm trùng success/failure, mất dấu nguồn xác thực hoặc vòng fallback khó kiểm soát.
11. **Tắt credential erasure để chữa lỗi cache.** Dễ giữ secret lâu không cần thiết; nên sửa thiết kế cache/reference.
12. **Cho rằng đăng ký `@Bean AuthenticationProvider` luôn tự động gắn vào mọi filter.** Cần kiểm tra actual authentication manager của từng filter chain.
13. **Đưa toàn bộ principal hoặc credentials vào response/log.** Principal có thể mang thông tin nội bộ hoặc secret; chỉ xuất DTO được chọn.
14. **Trộn authorization vào provider và cho client tự cấp authorities.** Quyền phải xuất phát từ dữ liệu đã xác minh và được kiểm tra ở đúng tầng.

## 12. Bài tập củng cố

**Bài 1 — Sơ đồ trace:** với danh sách `[A, B, C]`, ghi ra các bước khi A không hỗ trợ, B hỗ trợ nhưng trả `null`, C trả thành công. Nêu rõ provider nào được gọi `authenticate` và khi nào vòng lặp dừng.

**Bài 2 — Cùng token type:** hai provider đều hỗ trợ `UsernamePasswordAuthenticationToken`. Provider đầu ném `BadCredentialsException`, provider sau xác thực thành công. Giải thích vì sao một manager có thể trả thành công và điều kiện bảo mật nào cần được kiểm soát để tránh fallback sai.

**Bài 3 — Account locked:** trong mô hình tương tự, provider đầu ném `LockedException`. Dự đoán kết quả và lý do không được thử provider sau.

**Bài 4 — Parent:** vẽ hai `ProviderManager` có parent dùng chung. Đề xuất một ví dụ hợp lệ (chia sẻ một provider đã được kiểm soát) và một rủi ro (trùng namespace hoặc bypass cơ chế khóa tài khoản). Viết test đảm bảo request không vượt ranh giới.

**Bài 5 — Hệ thống thật:** chọn một ứng dụng dùng username/password và JWT API. Xác định chính xác filter → token class → manager → provider → SecurityContext cho từng loại request; chỉ ra vì sao không nhất thiết là một manager duy nhất.

**Tiêu chí hoàn thành:** giải thích được `supports`, ba kết quả từ `authenticate`, quy tắc chọn provider theo thứ tự, parent manager, `ProviderNotFoundException`, `AccountStatusException`, credential erasure và cách tránh fallback thiếu an toàn. Chạy được demo Java và giải thích từng dòng output mà không cần đọc source của thư viện.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, nhiều provider, parent và erasure.
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): quy tắc duyệt, xử lý exception, event publisher và `eraseCredentialsAfterAuthentication`.
- [Spring Security 6.5 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports` và `authenticate`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): password hashing và `UserDetailsService`.
- [Spring Security 6.5 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html): filter, manager và đăng nhập mật khẩu.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): vai trò của `GrantedAuthority` và `AuthorizationManager` sau bước xác thực.

Các ví dụ cố định ở API Spring Security **6.5.x** để dễ kiểm tra. Nếu dự án dùng Spring Security 7.x hoặc một `AuthenticationManager` custom, hãy đối chiếu Javadoc/source của phiên bản và implementation đó trước khi suy ra quy tắc xử lý ngoại lệ, mặc định bảo mật hoặc cách đăng ký provider.