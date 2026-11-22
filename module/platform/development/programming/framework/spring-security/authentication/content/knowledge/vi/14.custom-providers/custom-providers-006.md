# Phân biệt trả null, ném AuthenticationException và lỗi hệ thống

## 1. Bài toán: một Provider tùy chỉnh phải đưa ra quyết định gì?

Trong Spring Security Servlet, một `AuthenticationManager` (thường là `ProviderManager`) nhận một đối tượng `Authentication` chưa được chứng thực và chuyển nó qua các `AuthenticationProvider` phù hợp. Mỗi provider có thể xác thực bằng nguồn khác nhau: tài khoản nội bộ, tenant riêng, directory, hoặc loại credential chuyên biệt. Provider tùy chỉnh cần phân biệt rõ **không thể xử lý request**, **đã xử lý nhưng xác thực thất bại**, **xác thực thành công**, và **không thể đưa ra kết luận vì hệ thống gặp lỗi**.

Hợp đồng của `AuthenticationProvider` có hai phương thức chính:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

| Tình huống trong provider | Phải làm gì? | Thông điệp gửi cho `ProviderManager` |
| --- | --- | --- |
| Đã kiểm tra đúng credential, tài khoản hợp lệ | Trả về một `Authentication` đã xác thực, có principal/authorities | **Thành công:** dừng tìm provider khác. |
| Provider không chịu trách nhiệm xử lý credential cụ thể này | Trả về `null` | **Không kết luận:** thử provider kế tiếp hỗ trợ loại token. |
| Credential thuộc provider này nhưng sai | Ném `BadCredentialsException` hoặc subclass `AuthenticationException` phù hợp | **Thất bại xác thực:** manager ghi nhận lỗi; có thể thử provider sau tùy loại exception. |
| Tài khoản được xác định là bị khóa/vô hiệu hóa | Ném `LockedException` / `DisabledException` (thuộc `AccountStatusException`) | **Dừng ngay** theo xử lý đặc biệt của `ProviderManager`. |
| Hệ thống xác thực nội bộ bị lỗi, không thể kết luận đúng/sai | Ném một `AuthenticationServiceException` phù hợp, thường `InternalAuthenticationServiceException` cho lỗi nội bộ | **Lỗi hạ tầng:** không biến thành “sai mật khẩu” hoặc `null`; `InternalAuthenticationServiceException` dừng chain ngay. |
| Loại `Authentication` không được provider hỗ trợ ngay từ đầu | `supports(...)` trả `false` | Provider đó bị bỏ qua, không gọi `authenticate(...)`. |

**Quy tắc quan trọng nhất:** `null` không có nghĩa “mật khẩu sai”, và một lỗi kết nối database không phải “không hỗ trợ loại token”. Mỗi quyết định có hậu quả khác nhau đối với fallback, log, response cho client và an toàn bảo mật.

## 2. ProviderManager xét danh sách provider như thế nào?

Giả sử manager chứa provider A, B, C theo thứ tự, và đã nhận một `UsernamePasswordAuthenticationToken`:

~~~text
AuthenticationManager.authenticate(request)
              |
              v
         ProviderManager
              |
              v
        Provider A supports?
          |             |
         NO            YES
          |             |
          |        A.authenticate(...)
          |           |      |        |
          |         null  success   exception
          |           |      |        |
          |           |    RETURN    | 
          |           |              +-- AccountStatusException /
          |           |              |   InternalAuthenticationServiceException
          |           |              |       → THROW ngay
          |           |              |
          |           |              +-- AuthenticationException khác
          |           |                    → ghi nhận, xét B
          |           v
        Provider B ...
              |
         Có kết quả không?
          |          |
         YES        NO
          |          |
       RETURN     Xét parent nếu có;
                  nếu vẫn thất bại, ném
                  exception phù hợp
~~~

Các điểm cần đọc đúng:

1. `supports(Class<?>)` chỉ là bộ lọc **loại đối tượng Authentication**. Trả `true` có nghĩa provider có thể xét sâu; không bảo đảm mọi instance của class đó đều thuộc phạm vi xử lý. Sau `supports(true)`, `authenticate(...)` **vẫn có thể trả `null`**.
2. Một kết quả `Authentication` **khác `null`** khiến `ProviderManager` ngừng hỏi các provider sau. Vì vậy provider không được trả lại token chưa xác thực để giả vờ “không xử lý”.
3. Một exception xác thực thông thường, ví dụ `BadCredentialsException`, **không nhất thiết kết thúc ngay toàn bộ manager**. `ProviderManager` có thể thử các provider kế tiếp. Nếu provider sau thành công, kết quả thành công đó thay thế lỗi cũ.
4. Nếu không provider nào thành công, exception xác thực thích hợp cuối cùng được ném; nếu không provider nào xử lý được token và không có exception, manager ném `ProviderNotFoundException`.
5. `AccountStatusException` và `InternalAuthenticationServiceException` được `ProviderManager` xử lý đặc biệt bằng cách dừng ngay, không tiếp tục provider sau.
6. Nếu cấu hình `parent AuthenticationManager`, parent có thể được hỏi khi các provider hiện tại chưa trả kết quả. Không dựa vào parent như cơ chế sửa lỗi cấu hình thiếu provider.

Các hành vi này thuộc **`ProviderManager` của Spring Security**, không nên suy rộng cho mọi implementation tùy chỉnh của interface `AuthenticationManager`. Thứ tự provider và loại exception ảnh hưởng trực tiếp tới kết quả cuối.

## 3. Khi nào trả về null?

`return null` có nghĩa: **“Tôi là provider có thể kiểm tra lớp token này, nhưng request cụ thể không thuộc phạm vi tôi chịu trách nhiệm; hãy để provider khác thử.”**

Ví dụ hệ thống cho phép hai miền tài khoản khác nhau cùng dùng `UsernamePasswordAuthenticationToken`:

- Tài khoản có username bắt đầu `tenant:` do `TenantAuthenticationProvider` chịu trách nhiệm.
- Tài khoản có username bắt đầu `local:` do `LocalAuthenticationProvider` chịu trách nhiệm.

Cả hai provider có thể `supports(UsernamePasswordAuthenticationToken.class) == true`. Nhưng khi nhận `local:bob`, provider Tenant phải trả `null` vì yêu cầu ấy thuộc provider Local. Điều này khác hoàn toàn với trường hợp `tenant:alice` gửi sai password: provider Tenant **đã nhận đúng trách nhiệm**, nên phải ném `BadCredentialsException`.

~~~java
@Override
public Authentication authenticate(Authentication authentication)
        throws AuthenticationException {

    String username = authentication.getName();

    if (!username.startsWith("tenant:")) {
        return null; // Không phải miền tài khoản của provider này.
    }

    // Từ đây, provider chịu trách nhiệm xác thực tài khoản tenant.
    if (!isValidTenantCredential(authentication)) {
        throw new BadCredentialsException("Invalid credentials");
    }

    return createAuthenticatedResult(authentication);
}
~~~

**Đoạn trên là pseudocode Java về ý tưởng**, vì `isValidTenantCredential` và `createAuthenticatedResult` chưa được định nghĩa. Ví dụ chạy được đầy đủ ở mục 7 bên dưới.

Không dùng `null` cho các trường hợp này:

- Username **thuộc provider** nhưng không tìm thấy trong database của provider ấy. Không tìm thấy user thuộc miền quản lý thường phải là một thất bại xác thực (tránh dùng `null` để đưa request đến provider yếu hơn).
- Password sai, token hết hạn, chữ ký sai, credential bị thu hồi: đã kiểm tra và xác định thất bại.
- Database chết, LDAP timeout, kho khóa không truy cập được: đây là lỗi không thể xác minh, phải biểu diễn thành lỗi hệ thống.
- Tài khoản bị khóa hoặc vô hiệu hóa: đây là lỗi trạng thái tài khoản, không phải tín hiệu để fallback.

Nếu các provider có **chồng lấn vùng username/credential**, cần thiết kế luật sở hữu credential rõ ràng. Trả `null` một cách tùy tiện có thể làm một credential bị từ chối ở provider mạnh lại được chấp nhận ở provider yếu.

## 4. Khi nào ném AuthenticationException?

`AuthenticationException` là lớp gốc của các lỗi **trong quá trình xác thực**. Đây là *unchecked exception* (`RuntimeException`), nhưng khai báo `throws AuthenticationException` trong phương thức giúp làm rõ hợp đồng.

Một số subclass hay gặp:

| Loại exception | Khi nào phù hợp? | Ý nghĩa |
| --- | --- | --- |
| `BadCredentialsException` | Username/password hoặc credential khác không hợp lệ | Request đã được đánh giá và không vượt qua xác thực. |
| `UsernameNotFoundException` | Hệ thống biết tài khoản không tồn tại | Thông tin nội bộ về tra cứu; nên tránh lộ ra client. |
| `DisabledException` | Tài khoản bị vô hiệu hóa | Lỗi trạng thái tài khoản; manager dừng ngay. |
| `LockedException` | Tài khoản bị khóa | Lỗi trạng thái tài khoản; manager dừng ngay. |
| `AccountExpiredException` | Tài khoản hết hạn | Lỗi trạng thái tài khoản; manager dừng ngay. |
| `CredentialsExpiredException` | Credential hết hạn | Một `AccountStatusException`; manager dừng ngay. |
| `ProviderNotFoundException` | Không provider thích hợp nào đưa ra kết quả | Thường là vấn đề wiring/loại token; do manager quyết định. |
| `AuthenticationServiceException` | Hệ thống xác thực không thể xử lý request | Không phải bằng chứng credential sai. |
| `InternalAuthenticationServiceException` | Hệ thống xác thực nội bộ thất bại | Subclass của `AuthenticationServiceException`; manager dừng chain ngay. |

**Điểm dễ nhầm:** `BadCredentialsException` là một `AuthenticationException`, nhưng trong `ProviderManager` nó thường được ghi nhận và cho các provider sau cơ hội xử lý. Không được nói “cứ ném `AuthenticationException` là manager dừng ngay”. Loại exception cụ thể mới quyết định có ngoại lệ dừng sớm hay không.

### 4.1. Sai thông tin đăng nhập

Khi provider chịu trách nhiệm với tài khoản, credential sai có thể báo:

~~~java
if (!passwordEncoder.matches(rawPassword, user.getPasswordHash())) {
    throw new BadCredentialsException("Invalid credentials");
}
~~~

Đoạn code phụ thuộc `user` và `passwordEncoder` đã được định nghĩa ở hệ thống thực tế; nó mô tả nơi kiểm tra password hash. Không nên phân biệt response public giữa “username không tồn tại” và “password sai” để tránh giúp kẻ tấn công liệt kê tài khoản. `DaoAuthenticationProvider` / `AbstractUserDetailsAuthenticationProvider` mặc định có tùy chọn `hideUserNotFoundExceptions` theo hướng che sự khác biệt đó.

### 4.2. Trạng thái tài khoản

Nếu tài khoản bị khóa hoặc vô hiệu hóa:

~~~java
if (user.isLocked()) {
    throw new LockedException("Account is locked");
}
if (!user.isEnabled()) {
    throw new DisabledException("Account is disabled");
}
~~~

Đây cũng chỉ là đoạn logic minh họa dựa trên đối tượng `user` của ứng dụng. Với `ProviderManager` thông thường, các lỗi kế thừa `AccountStatusException` làm manager **ngừng thử provider khác**, vì fallback sang nguồn yếu hơn có thể làm vô hiệu hóa chính sách khóa tài khoản.

### 4.3. Lỗi xác thực khác không nhất thiết ngăn fallback

Giả sử provider A và B cùng hỗ trợ token:

~~~text
A.authenticate(...) → BadCredentialsException
B.authenticate(...) → Authentication thành công
ProviderManager    → trả kết quả của B
~~~

Đây là hành vi có chủ ý của `ProviderManager`, **nhưng không có nghĩa bạn nên cho phép fallback sau mật khẩu sai trong cùng một miền tài khoản**. Khi nhiều provider xác thực cùng danh tính, có thể vô tình tạo đường vòng qua chính sách bảo vệ tài khoản. Nên định tuyến rõ loại token, tenant, hoặc nguồn credential trước khi xác thực và kiểm thử thật thứ tự provider.

## 5. Lỗi hệ thống: xác thực chưa thể kết luận đúng/sai

Lỗi hệ thống là khi provider **không thể hoàn thành việc kiểm tra**, ví dụ:

- Kho user nội bộ bị lỗi kết nối, repository ném exception hoặc không đọc được dữ liệu bắt buộc.
- Thành phần kiểm tra chữ ký không tải được key hợp lệ vì lỗi hạ tầng.
- Dependency xử lý credential bị lỗi cấu hình, timeout hoặc không có sẵn.
- Dữ liệu backend trả về không đúng contract và không thể xác thực một cách an toàn.

Trong các tình huống này, **không nên trả `null`** (có thể vô tình chuyển sang provider khác) và **không nên đổi tất cả thành `BadCredentialsException`** (che giấu sự cố và có thể làm báo động sai về mật khẩu).

### 5.1. AuthenticationServiceException và InternalAuthenticationServiceException

`AuthenticationServiceException` kế thừa `AuthenticationException` và mô tả hệ thống xác thực không thể xử lý yêu cầu do sự cố. `InternalAuthenticationServiceException` kế thừa `AuthenticationServiceException`, nhấn mạnh lỗi ở thành phần nội bộ do ứng dụng kiểm soát. Theo contract của Spring Security, hai loại này **không đồng nhất về cách `ProviderManager` tiếp tục chain**:

- `InternalAuthenticationServiceException`: `ProviderManager` bắt riêng và ném ngay, không thử provider kế tiếp.
- `AuthenticationServiceException` thông thường: được bắt trong nhánh `AuthenticationException` chung, do đó manager **có thể tiếp tục provider khác**. Không giả định mọi “service exception” đều dừng sớm.

Ví dụ mô tả cách giữ nguyên nguyên nhân gốc:

~~~java
try {
    return loadAccountFromInternalStore(username);
} catch (RepositoryUnavailableException ex) {
    throw new InternalAuthenticationServiceException(
        "Internal credential store is unavailable", ex);
}
~~~

Đây là **đoạn minh họa**, vì hai phương thức/lớp dữ liệu `loadAccountFromInternalStore` và `RepositoryUnavailableException` là tên giả định trong hệ thống cụ thể.

**Cảnh báo phân loại:** không tự động gán mọi sự cố ở nhà cung cấp bên ngoài thành `InternalAuthenticationServiceException`. Tài liệu Spring Security phân biệt lỗi nội bộ và lỗi của hệ thống bên ngoài. Hãy chọn loại exception phù hợp hợp đồng tích hợp; đồng thời thiết kế cách **fail closed**, cảnh báo vận hành và quy tắc fallback rõ ràng. Nếu một exception hạ tầng được cho phép đi tiếp qua provider khác, phải bảo đảm đó là chính sách đã chủ ý và không vượt qua kiểm soát bảo mật.

### 5.2. Runtime exception ngoài AuthenticationException thì sao?

Ví dụ code provider có lỗi lập trình:

~~~java
throw new IllegalStateException("Broken provider configuration");
~~~

`IllegalStateException` không kế thừa `AuthenticationException`. `ProviderManager` không tự coi mọi `RuntimeException` là “sai mật khẩu” để chuyển sang provider tiếp theo. Lỗi có thể nổi lên thành lỗi ứng dụng và đi qua exception handling khác, không bảo đảm có HTTP status nào nếu chưa xem filter/controller.

Đừng viết `catch (Exception ex) { return null; }` hoặc `catch (RuntimeException ex) { throw new BadCredentialsException(...); }` để che mọi lỗi: cách này đánh mất nguyên nhân, khiến xử lý fallback sai và làm khó vận hành. Bắt ngoại lệ **tại ranh giới tích hợp xác định**, giữ cause và log dữ liệu đã được che.

### 5.3. HTTP status không phải do AuthenticationProvider tự quyết định

Provider trả một đối tượng `Authentication` hoặc ném exception; nó **không tự sở hữu mã HTTP response**. Thành phần gọi như authentication filter, `AuthenticationEntryPoint`, `AuthenticationFailureHandler` hoặc controller JSON mới quyết định status/redirect/body.

Một chính sách API minh họa:

| Kết quả | Response thường phù hợp với API | Ghi chú |
| --- | --- | --- |
| Credential sai / không được xác thực | `401 Unauthorized` | Thông điệp chung; không tiết lộ user/password cụ thể. |
| Đã xác thực nhưng không đủ quyền endpoint | `403 Forbidden` | Đây là **authorization**, thường qua `AccessDeniedHandler`, khác `AuthenticationException`. |
| Hệ thống xác thực bị gián đoạn | `503 Service Unavailable` hoặc status lỗi vận hành phù hợp | **Không tự động** có 503 nếu không cấu hình error mapping. |
| Login thành công | HTTP `200` hoặc phản hồi thành công của giao thức | Nếu dùng session cần lưu `SecurityContext` đúng cách. |

**Không khẳng định** Spring Security mặc định map `InternalAuthenticationServiceException` thành 503. Với filter/controller không tùy chỉnh, cách xử lý và response có thể là 401 hoặc trang login lỗi. Nếu API cần phân biệt gián đoạn hạ tầng, phải cấu hình failure handler / entry point hoặc lớp controller chủ động.

## 6. Bảng quyết định nhanh theo tình huống

| Trường hợp | `supports` | `authenticate` | Provider tiếp theo được thử? |
| --- | --- | --- | --- |
| Provider chỉ hỗ trợ token OTP, request là username/password | `false` | Không gọi | Có. |
| Provider hỗ trợ class username/password nhưng request thuộc nguồn login khác | `true` | `return null` | Có. |
| Password sai ở nguồn mà provider sở hữu | `true` | `BadCredentialsException` | Có thể, theo logic `ProviderManager`. |
| Username thuộc nguồn đó nhưng không tồn tại | `true` | Thường `BadCredentialsException` hoặc xử lý che `UsernameNotFoundException` | Có thể; phải tránh fallback sai thiết kế. |
| Tài khoản đã bị khóa | `true` | `LockedException` | **Không**, dừng ngay. |
| Tài khoản vô hiệu hóa | `true` | `DisabledException` | **Không**, dừng ngay. |
| Store nội bộ gặp lỗi không thể xử lý | `true` | `InternalAuthenticationServiceException` | **Không**, dừng ngay. |
| Service exception thông thường | `true` | `AuthenticationServiceException` | **Có thể**, không mặc định dừng ngay. |
| Credential đúng, provider tạo authenticated result | `true` | Trả đối tượng `Authentication` khác `null` | **Không**, hoàn tất. |
| Mọi provider bỏ qua class token / trả null | `false` hoặc `null` | Không có kết quả | Manager ném `ProviderNotFoundException` nếu không có exception/parent thành công. |

Bảng này mô tả `ProviderManager` trong Spring Security 6.x; manager tự viết có thể thực hiện logic khác. `supports(true)` chưa nói gì về việc credentials có đúng hay sai.

## 7. Ví dụ Java 17+ chạy bằng JUnit 5: kiểm chứng từng nhánh

Ví dụ sau tập trung vào **hợp đồng provider**, không cần chạy servlet container. Ta dùng hai provider:

- `TenantProvider` chịu trách nhiệm với username bắt đầu `tenant:`; sẽ trả `null` cho namespace khác.
- `LocalProvider` chịu trách nhiệm với username bắt đầu `local:`; sẽ trả `null` cho namespace khác.

Cả hai hỗ trợ `UsernamePasswordAuthenticationToken`, có password BCrypt demo, và được lắp vào một `ProviderManager` theo thứ tự. Các test kiểm tra chính xác provider nào được gọi và exception nào xuất hiện. Điều này tránh suy đoán từ HTTP status trước khi hiểu manager.

### 7.1. Dependency và vị trí file

Trong dự án Gradle đã cấu hình Spring Boot 3.x / JDK 17+ và JUnit Platform:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây chỉ là **đoạn `build.gradle`**, không phải file build hoàn chỉnh. Có thể đưa test vào một dự án Boot đã có plugin/dependency management; các version Spring Security/JUnit được Boot BOM quản lý.

Đặt file tại:

~~~text
src/test/java/com/example/security/ProviderSemanticsTest.java
~~~

### 7.2. Code test hoàn chỉnh

~~~java
package com.example.security;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProviderSemanticsTest {

    // Chỉ tạo tài khoản giả để minh họa. BCrypt hash khác nhau giữa các lần chạy.
    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);
    private final String demoHash = encoder.encode("demo-pass");

    private ProviderManager manager(List<String> calls) {
        return new ProviderManager(List.of(
            new TenantProvider(calls, encoder, demoHash),
            new LocalProvider(calls, encoder, demoHash)
        ));
    }

    private static Authentication request(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    private static Authentication success(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static final class TenantProvider implements AuthenticationProvider {
        private final List<String> calls;
        private final PasswordEncoder encoder;
        private final String hash;

        TenantProvider(List<String> calls, PasswordEncoder encoder, String hash) {
            this.calls = calls;
            this.encoder = encoder;
            this.hash = hash;
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication auth)
                throws AuthenticationException {
            calls.add("TENANT");

            String username = auth.getName();
            if (!username.startsWith("tenant:")) {
                return null; // Không thuộc namespace này.
            }

            if ("tenant:disabled".equals(username)) {
                throw new DisabledException("Account disabled");
            }
            if ("tenant:outage".equals(username)) {
                throw new InternalAuthenticationServiceException(
                    "Internal account store is unavailable",
                    new IllegalStateException("Simulated storage outage")
                );
            }

            boolean known = "tenant:alice".equals(username);
            boolean valid = known && encoder.matches(
                String.valueOf(auth.getCredentials()), hash);
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return success(username);
        }
    }

    private static final class LocalProvider implements AuthenticationProvider {
        private final List<String> calls;
        private final PasswordEncoder encoder;
        private final String hash;

        LocalProvider(List<String> calls, PasswordEncoder encoder, String hash) {
            this.calls = calls;
            this.encoder = encoder;
            this.hash = hash;
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication auth)
                throws AuthenticationException {
            calls.add("LOCAL");

            String username = auth.getName();
            if (!username.startsWith("local:")) {
                return null;
            }

            boolean known = "local:bob".equals(username);
            boolean valid = known && encoder.matches(
                String.valueOf(auth.getCredentials()), hash);
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return success(username);
        }
    }

    @Test
    void nullAllowsNextProviderToAuthenticate() {
        List<String> calls = new ArrayList<>();
        Authentication result = manager(calls).authenticate(
            request("local:bob", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals("local:bob", result.getName());
        assertEquals(List.of("TENANT", "LOCAL"), calls);
    }

    @Test
    void successfulProviderStopsTheChain() {
        List<String> calls = new ArrayList<>();
        Authentication result = manager(calls).authenticate(
            request("tenant:alice", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void badCredentialsIsRetainedWhenNoLaterProviderSucceeds() {
        List<String> calls = new ArrayList<>();
        assertThrows(BadCredentialsException.class, () ->
            manager(calls).authenticate(
                request("tenant:alice", "wrong-pass")));

        // Manager còn hỏi LOCAL; LOCAL trả null.
        assertEquals(List.of("TENANT", "LOCAL"), calls);
    }

    @Test
    void accountStatusFailureStopsImmediately() {
        List<String> calls = new ArrayList<>();
        assertThrows(DisabledException.class, () ->
            manager(calls).authenticate(
                request("tenant:disabled", "demo-pass")));

        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void internalServiceFailureStopsImmediately() {
        List<String> calls = new ArrayList<>();
        InternalAuthenticationServiceException error = assertThrows(
            InternalAuthenticationServiceException.class,
            () -> manager(calls).authenticate(
                request("tenant:outage", "demo-pass")));

        assertInstanceOf(IllegalStateException.class, error.getCause());
        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void unsupportedTokenTypeHasNoProvider() {
        List<String> calls = new ArrayList<>();
        assertThrows(ProviderNotFoundException.class, () ->
            manager(calls).authenticate(
                new TestingAuthenticationToken("alice", "token")));

        assertTrue(calls.isEmpty());
    }

    @Test
    void laterSuccessCanOverrideEarlierBadCredentials() {
        List<String> calls = new ArrayList<>();

        AuthenticationProvider rejects = new AuthenticationProvider() {
            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
            }

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add("REJECT");
                throw new BadCredentialsException("First provider rejects");
            }
        };

        AuthenticationProvider succeeds = new AuthenticationProvider() {
            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
            }

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add("ACCEPT");
                return success(auth.getName());
            }
        };

        Authentication result = new ProviderManager(
            List.of(rejects, succeeds)).authenticate(
                request("demo", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals(List.of("REJECT", "ACCEPT"), calls);
    }
}
~~~

Test cuối **cố ý làm provider thứ hai chấp nhận request** chỉ để phơi bày hợp đồng `ProviderManager`: thành công của provider sau có thể thay thế `BadCredentialsException` do provider trước ném. **Không đưa provider “chấp nhận mọi request” này vào ứng dụng thật.** Trong production, mọi provider phải thực sự xác minh credential, khóa tài khoản và phạm vi namespace trước khi tạo authenticated result.

Password demo được băm bằng BCrypt; phương thức `matches` xác minh bằng hash, không lưu Base64 hoặc so sánh trực tiếp password với plaintext trong ứng dụng thật. Trong bài test, hash tự tạo mỗi lần chạy nên khác chuỗi nhưng kết quả `matches` đúng ổn định.

### 7.3. Chạy và giải thích kết quả

Trong thư mục dự án:

~~~bash
./gradlew test --tests com.example.security.ProviderSemanticsTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.security.ProviderSemanticsTest
~~~

Khi đủ dependency/plugin và các test pass, Gradle báo `BUILD SUCCESSFUL` (có thể kèm các log khác tùy cấu hình). Đoạn test dùng assertion nên không dựa vào console stdout cố định.

Từng phép thử tương ứng với một nhánh:

| Test | Diễn biến trong ProviderManager | Kết quả |
| --- | --- | --- |
| `nullAllowsNextProviderToAuthenticate` | TENANT trả null → LOCAL đúng | Xác thực thành công cho `local:bob`. |
| `successfulProviderStopsTheChain` | TENANT thành công | LOCAL không được gọi. |
| `badCredentialsIsRetainedWhenNoLaterProviderSucceeds` | TENANT ném BadCredentials → LOCAL trả null | Ném BadCredentials. |
| `accountStatusFailureStopsImmediately` | TENANT ném DisabledException | LOCAL không được gọi. |
| `internalServiceFailureStopsImmediately` | TENANT ném InternalAuthenticationServiceException | LOCAL không được gọi, giữ cause gốc. |
| `unsupportedTokenTypeHasNoProvider` | Cả hai `supports` trả false | ProviderNotFoundException. |
| `laterSuccessCanOverrideEarlierBadCredentials` | REJECT ném BadCredentials → ACCEPT thành công | Manager trả kết quả ACCEPT. |

Nhìn vào **thứ tự provider được gọi** là cách phân biệt `return null`, exception thông thường và exception dừng sớm. Nếu ứng dụng của bạn có nhiều `AuthenticationManager`/filter chain, bảo đảm test khởi tạo đúng manager chứa đúng danh sách provider và thứ tự của request thực tế.

## 8. Kết nối với đăng nhập HTTP hoặc JSON login

Trong Spring Security Servlet, filter (ví dụ `UsernamePasswordAuthenticationFilter` hoặc `BasicAuthenticationFilter`) gọi `AuthenticationManager`. AuthenticationManager gọi các provider. Khi provider thất bại, filter/login handler xử lý exception theo cơ chế đã cấu hình.

~~~text
POST /login hoặc /api/login
      |
      v
AuthenticationFilter / Controller
      |
      v
AuthenticationManager
      |
      +--> Provider A
      |      +-- null → Provider B
      |      +-- Authentication → success flow
      |      +-- AuthenticationException → failure flow
      |
      v
Kết quả thành công / ngoại lệ
      |
      +--> Login thành công: cập nhật SecurityContext,
      |    session/token theo thiết kế
      |
      +--> Login thất bại: FailureHandler/EntryPoint
           hoặc controller quyết định HTTP status/body
~~~

### 8.1. API JSON trả lỗi rõ nhưng không rò thông tin

Đây là **đoạn xử lý controller minh họa**, không phải file Java độc lập. Mục tiêu là biểu diễn thứ tự phân loại exception:

~~~java
try {
    Authentication authenticated = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            request.username(), request.password()));
    // Lưu SecurityContext/session hay phát hành token theo kiến trúc.
    return ResponseEntity.ok(toLoginResponse(authenticated));
}
catch (AuthenticationServiceException ex) {
    // Server log có request ID; che credential và thông tin nhạy cảm.
    log.error("Authentication backend unavailable", ex);
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(Map.of("error", "authentication_temporarily_unavailable"));
}
catch (AuthenticationException ex) {
    return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
        .body(Map.of("error", "invalid_credentials"));
}
~~~

Các biến `authenticationManager`, `request`, `log` và hàm `toLoginResponse` phải được khai báo trong ứng dụng. `AuthenticationServiceException` phải đứng **trước** `AuthenticationException` vì nó là subclass. Không trả `ex.getMessage()` cho browser: thông điệp exception có thể lộ chi tiết backend, tên hệ thống hoặc trạng thái tài khoản.

Một API có thể chọn 503 khi dịch vụ xác thực không sẵn sàng, nhưng đó là **quyết định của ứng dụng**; Spring Security không tự cam kết mọi service failure thành 503. Nếu xử lý qua filter, dùng `AuthenticationFailureHandler` / `AuthenticationEntryPoint` tương ứng thay vì giả định controller sẽ bắt được exception.

### 8.2. 401 và 403 là hai giai đoạn khác nhau

- `401 Unauthorized` (trong ngữ cảnh HTTP authentication) thường là chưa xác thực thành công. Sai credential, thiếu credential hoặc không có provider phù hợp có thể kết thúc ở nhánh này, tùy filter và handler.
- `403 Forbidden` thường là đã xác thực nhưng bị chặn bởi chính sách quyền, hoặc request bị filter khác chặn như CSRF. `AccessDeniedException` là luồng authorization, **không phải cứ `AuthenticationProvider` ném exception là 403**.
- Lỗi hệ thống ở backend có thể phải được báo qua 503 hoặc cơ chế vận hành riêng; không được gắn nhãn “password sai” một cách giả tạo.

Vì vậy khi debug, hãy kiểm tra **exception thực tế tại provider** và provider nào đã chạy, rồi mới phân tích response HTTP.

## 9. Các bẫy triển khai provider tùy chỉnh

### Bẫy 1 — Trả null vì user không tìm thấy trong nguồn mình sở hữu

Một provider xác thực toàn bộ username `tenant:*` trả `null` nếu `tenant:alice` không tồn tại. Provider phía sau có thể chấp nhận cùng username bằng cơ chế yếu hơn. Hãy phân biệt **namespace không thuộc tôi** với **user thuộc tôi nhưng không hợp lệ**. Trường hợp thứ hai thường ném `BadCredentialsException`; ở ngoài API, tránh lộ danh tính tài khoản có tồn tại.

### Bẫy 2 — Đổi lỗi database thành BadCredentialsException

Nếu connection pool cạn, truy vấn database timeout hoặc repository chưa sẵn sàng, không thể kết luận user sai mật khẩu. Đổi hết thành `BadCredentialsException` khiến client retry sai cách, số liệu xác thực thất bại bị nhiễu, việc điều tra outage khó khăn và có thể kích hoạt cơ chế khóa tài khoản không đúng nguyên nhân. Bảo toàn cause và ghi nhận lỗi vận hành an toàn.

### Bẫy 3 — Bắt mọi exception rồi trả null

~~~java
try {
    return doAuthenticate(authentication);
} catch (Exception ignored) {
    return null; // SAI: che cả sai mật khẩu, khóa tài khoản, outage.
}
~~~

Code minh họa này chỉ để chỉ ra **anti-pattern**: tùy loại exception, manager có thể fallback bất ngờ. Bắt từng nhóm lỗi có chủ đích thay vì dập mọi lỗi.

### Bẫy 4 — Nghĩ ném BadCredentialsException luôn dừng mọi provider

`ProviderManager` có thể thử tiếp và cho phép provider sau thành công. Nếu cần ngăn bypass giữa các miền tài khoản, thiết kế token type, routing hoặc manager riêng biệt. Dừng toàn bộ bằng exception kiểu “account locked” giả cũng sai vì làm lệch semantics; giải quyết vấn đề ownership/fallback ở kiến trúc.

### Bẫy 5 — Trả về token chưa xác thực thay vì null

~~~java
return UsernamePasswordAuthenticationToken.unauthenticated(
    authentication.getPrincipal(),
    authentication.getCredentials()
);
~~~

Code này không tạo authenticated result, nhưng **khác `return null`**: manager nhận một object non-null nên sẽ ngừng xét provider khác. Không coi đây là cách chuẩn để báo “tôi không hỗ trợ request”. Khi thành công, trả token đã xác thực có principal và authorities phù hợp; khi không xử lý, trả null.

### Bẫy 6 — Sai logic supports()

Ví dụ không nên có `supports` luôn true cho mọi loại `Authentication` rồi ép kiểu mù quáng sang `UsernamePasswordAuthenticationToken`. Điều đó có thể tạo `ClassCastException` thay vì thông điệp xác thực có ý nghĩa.

~~~java
@Override
public boolean supports(Class<?> tokenType) {
    return UsernamePasswordAuthenticationToken.class
        .isAssignableFrom(tokenType);
}
~~~

Nếu cần hỗ trợ một loại token custom, tạo class riêng kế thừa `AbstractAuthenticationToken` và cung cấp provider tương ứng. Đừng dùng `supports` để xét username/password; nó chỉ nhận `Class<?>`, không có credential instance.

### Bẫy 7 — Không kiểm tra trạng thái tài khoản trước khi cấp quyền

Xác thực password đúng nhưng user bị khóa vẫn phải bị từ chối. Đặt kiểm tra enabled/locked/expired và password hash ở ranh giới thích hợp. Nếu dùng `DaoAuthenticationProvider` với `UserDetailsService`, nhiều kiểm tra trạng thái đã có sẵn; không tự viết lại toàn bộ nếu không cần.

### Bẫy 8 — Trả principal/authorities không đáng tin

Khi provider trả về `Authentication` đã xác thực, các authority phải đến từ dữ liệu server đã xác minh. Không lấy danh sách role từ JSON login hoặc từ token do client tự khai rồi gắn vào authenticated result. Không dùng `authenticated(...)` trước khi hoàn thành toàn bộ kiểm tra mật khẩu, trạng thái tài khoản, chữ ký hoặc yếu tố xác thực.

### Bẫy 9 — Giữ credential hoặc log bí mật

`ProviderManager` mặc định xóa credential khỏi kết quả khi đối tượng implement `CredentialsContainer` (hành vi có thể cấu hình). Tuy vậy, provider không nên đưa raw password vào log, exception message, telemetry hoặc principal lưu lâu. Nên dùng `PasswordEncoder.matches(...)` và trả credential `null` khi có thể. Việc erase credentials không thay cho quản lý secret đúng cách.

### Bẫy 10 — Thấy 401 rồi không kiểm tra ProviderNotFoundException

`ProviderNotFoundException` có thể do thiếu provider hoặc truyền loại token sai với `supports`; đây thường là lỗi wiring/luồng xác thực cần sửa, không nhất thiết là user nhập sai password. Ghi nhận loại exception trong log nội bộ có kiểm soát và kiểm tra token class cùng danh sách provider.

## 10. Checklist QA khi bổ sung AuthenticationProvider

Một provider tùy chỉnh nên có test chứng minh:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Provider hỗ trợ đúng loại token? | `supports` true/false với các class cụ thể. |
| Request thuộc nguồn khác? | `authenticate` trả null, provider sau được gọi. |
| Credential sai ở nguồn mình sở hữu? | `BadCredentialsException` hoặc lỗi xác thực tương ứng. |
| Tài khoản khóa/hết hạn? | `AccountStatusException` phù hợp; không fallback. |
| Kho xác thực nội bộ hỏng? | `InternalAuthenticationServiceException` giữ nguyên cause; không fallback. |
| Không provider nào xử lý token? | `ProviderNotFoundException` từ manager. |
| Provider sau có thể thắng lỗi trước? | Test chứng minh cơ chế, rồi đánh giá nguy cơ bypass chính sách. |
| Xác thực thành công? | `isAuthenticated()==true`, principal và authorities từ server; provider sau không được gọi. |
| Endpoint/handler phản hồi đúng? | Kiểm thử riêng 401/403/503 và không lộ credential, user enumeration, stack trace. |
| Hệ thống sản xuất bảo vệ được lỗi phụ thuộc? | Có timeout, rate limit, logging đã che secret, cảnh báo outage và không retry vô hạn. |

Khi đọc log, ưu tiên thông tin như loại `Authentication`, tên provider, mã lỗi nội bộ, thời gian và request correlation ID. **Không log giá trị `getCredentials()`, header `Authorization`, password hash hoặc token thật.**

## 11. Ghi nhớ

- **`return null`** = provider **không nhận trách nhiệm xử lý instance**; manager có thể tiếp tục provider khác.
- **`throw BadCredentialsException`** = provider đã kiểm tra và từ chối credential; `ProviderManager` **vẫn có thể thử provider sau** và chấp nhận kết quả thành công sau đó.
- **`throw AccountStatusException`** (ví dụ `LockedException`, `DisabledException`) = trạng thái tài khoản không hợp lệ, **dừng chain ngay**.
- **`throw InternalAuthenticationServiceException`** = sự cố xác thực nội bộ, **dừng chain ngay**. `AuthenticationServiceException` chung có thể tiếp tục theo nhánh exception thông thường.
- **`return authenticated Authentication`** = xác thực thành công, dừng chain; principal/role phải do server kiểm chứng.
- **Lỗi hệ thống khác credential sai**. Chọn exception và HTTP mapping đúng ý nghĩa, giữ nguyên cause, bảo vệ log và tránh fallback sang cơ chế yếu hơn khi hạ tầng đang gặp lỗi.

### Tài liệu tham khảo

- Spring Security Reference — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 API — AuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security 6.5 API — ProviderManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 API — AuthenticationServiceException: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationServiceException.html
- Spring Security 6.5 API — InternalAuthenticationServiceException: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/InternalAuthenticationServiceException.html
- Spring Security 6.5 API — AbstractUserDetailsAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
