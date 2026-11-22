# AuthenticationManager và hợp đồng authenticate trong Spring Security

**`AuthenticationManager`** là giao diện trung tâm định nghĩa cách một yêu cầu xác thực được xử lý trong Spring Security. Phương thức cốt lõi của nó là **`authenticate(Authentication authentication)`**: nhận một đối tượng `Authentication` mang thông tin cần kiểm tra, rồi **trả về một `Authentication` đã được xác thực đầy đủ** nếu thành công hoặc **ném `AuthenticationException`** nếu thất bại.

Phần quan trọng nhất của bài không phải nhớ tên method mà là hiểu **hợp đồng giữa người gửi yêu cầu xác thực, bộ máy xác thực, các provider, kết quả và security context**. Việc gọi `authenticate` thành công tự nó chưa có nghĩa rằng request HTTP sau này đã đăng nhập, đã tạo session, hay đã được phân quyền truy cập tài nguyên.

## 1. Vị trí của AuthenticationManager trong bộ máy xác thực

Trong một ứng dụng Servlet sử dụng Spring Security, các thành phần thường phối hợp như sau:

~~~text
Client gửi request + thông tin xác thực
        |
        v
SecurityFilterChain
        |
        v
Authentication Filter (Basic / form login / bearer / custom...)
        |
        | tạo Authentication yêu cầu, thường chưa authenticated
        v
AuthenticationManager.authenticate(request)
        |
        v
ProviderManager (triển khai thường gặp)
        |
        +--> AuthenticationProvider A: supports? -> xử lý / từ chối
        |
        +--> AuthenticationProvider B: supports? -> xử lý / từ chối
        |
        +--> ... / parent manager nếu được cấu hình
        |
        v
Authentication kết quả đã authenticated
        |
        | filter/handler xác thực quản lý SecurityContext
        v
SecurityContextHolder / SecurityContextRepository nếu cần
        |
        v
AuthorizationManager / method security / nghiệp vụ
~~~

Sơ đồ mô tả **luồng khái niệm**; filter, cơ chế thiết lập context, và cấu hình lưu phiên phụ thuộc cách đăng nhập.

Ba giao diện/đối tượng cần phân biệt:

| Thành phần | Vai trò | Có chịu trách nhiệm gì? |
|---|---|---|
| `AuthenticationManager` | API điều phối một thao tác xác thực | Nhận một `Authentication` request; trả kết quả đã xác thực hoặc ném lỗi |
| `AuthenticationProvider` | Bộ xử lý kiểm tra một loại `Authentication` | Chọn loại token hỗ trợ, kiểm tra bằng chứng, trả kết quả thành công, trả `null` nếu không quyết định được, hoặc ném lỗi |
| `Authentication` | Dữ liệu yêu cầu **và** dữ liệu kết quả | Mang principal, credentials, authorities, details và cờ `authenticated`; đối tượng trước/sau gọi có thể khác nhau |

**Đừng nhầm `AuthenticationManager` với `AuthorizationManager`.** Bộ đầu xử lý *xác thực danh tính* (AuthN), bộ sau hỗ trợ *quyết định có được phép truy cập* (AuthZ). Việc trả về `ROLE_USER` hoặc `orders:read` từ AuthN không có nghĩa mọi request của người đó sẽ được cho phép.

### 1.1. Giao diện thực tế

Rút gọn từ hợp đồng của `org.springframework.security.authentication.AuthenticationManager`:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

Đây là **trích đoạn chữ ký API để học**, không phải một lớp Java độc lập cần tự tạo khi dùng thư viện Spring Security. Điểm đáng chú ý:

- **Tham số:** `Authentication` biểu diễn yêu cầu xác thực. Ví dụ username/password thường dùng `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`.
- **Giá trị trả về:** một `Authentication` đã xác thực, gồm principal và những `GrantedAuthority` đáng tin theo provider.
- **Lỗi:** phương thức ném `AuthenticationException` hoặc subclass nếu yêu cầu không thể được xác thực.
- **Độ tin cậy:** dữ liệu đầu vào chưa xác thực vẫn chỉ là **claim** từ bên yêu cầu, kể cả `principal` hoặc authorities do client tự khai báo.
- **Không có bước phân quyền ngầm:** trả kết quả đã xác thực chỉ cho phép lớp tiếp theo có cơ sở để kiểm tra quyền.

Spring Security dùng một đối tượng triển khai `Authentication` cho cả đầu vào lẫn đầu ra, nhưng chúng có **trạng thái và ngữ nghĩa khác nhau**. Không được đọc danh tính người dùng từ request token chưa kiểm tra rồi coi đó là principal đã được tin cậy.

## 2. Trước và sau khi gọi authenticate

### 2.1. Đối tượng yêu cầu chưa được xác thực

Ví dụ Java với username/password:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "secret-demo");
~~~

Tại thời điểm này, `request.getPrincipal()` thường là chuỗi `"linh"`; `request.getCredentials()` là mật khẩu được gửi; và `request.isAuthenticated()` là `false`. Chưa có bằng chứng nào xác minh rằng người gửi thực sự là “linh”.

Giá trị `credentials` cần được bảo vệ như một bí mật. `getDetails()` có thể chứa metadata request (ví dụ một số chi tiết web), nhưng không phải bằng chứng danh tính đáng tin tự thân. Không ghi nguyên `Authentication` đầu vào vào log: đối tượng có thể chứa credentials.

### 2.2. Kết quả sau xác thực thành công

~~~java
Authentication result = manager.authenticate(request);

boolean ok = result.isAuthenticated();
Object principal = result.getPrincipal();
Collection<? extends GrantedAuthority> grants =
        result.getAuthorities();
~~~

Đây là **đoạn sử dụng API**, giả định có sẵn biến `manager` và imports. `result` có thể là **một object mới**, không phải `request` bị đổi cờ tại chỗ. Với provider username/password, principal có thể đổi từ `String` sang `UserDetails` hoặc principal của ứng dụng; authorities phản ánh các quyền mà provider xác lập.

Sau thành công, không dựa vào việc tự sửa `request.setAuthenticated(true)` để “đăng nhập”. Token mới với danh tính/quyền đã kiểm tra phải do provider/manager đáng tin tạo ra. Nhiều implementation của `Authentication` không cho phép biến token chưa tin cậy thành token đã tin cậy bằng một setter tùy ý.

### 2.3. Thông tin có thể đổi sau xác thực

| Trường | Trước `authenticate` | Sau `authenticate` thành công |
|---|---|---|
| `principal` | Username hoặc credential subject chưa được kiểm chứng | UserDetails, JWT, OIDC principal hoặc custom principal đáng tin |
| `credentials` | Mật khẩu/bằng chứng trình bày | Có thể bị xóa sau khi kiểm tra; không dựa vào việc còn hay không |
| `authorities` | Thường rỗng hoặc chưa đáng tin | Quyền được backend/provider cấp sau xác thực |
| `isAuthenticated()` | Thường là `false` | `true` cho authentication token thành công |
| `details` | Có thể chứa thông tin request | Có thể được giữ/chuyển theo implementation |
| `getName()` | Tên/subject do request đưa ra | Giá trị tên do kết quả và kiểu principal xác định |

Một đối tượng `Authentication` hoàn chỉnh **không buộc chứa mật khẩu còn nguyên**. `AuthenticationManager` trả kết quả đã xác thực; `ProviderManager` mặc định cố xóa credentials ở kết quả nếu đối tượng hỗ trợ `CredentialsContainer`. Hợp đồng API và chính sách xóa dữ liệu bí mật là hai khía cạnh khác nhau.

## 3. Hợp đồng authenticate khi thất bại: exceptions, không tự tạo “success giả”

JavaDoc của `AuthenticationManager` yêu cầu xác thực credential và có các trường hợp quan trọng:

- **`BadCredentialsException`:** thông tin xác thực sai. Hệ thống phải thực sự kiểm tra credential; không được cho phép chỉ vì có username.
- **`DisabledException`:** tài khoản bị vô hiệu hóa và manager có khả năng kiểm tra trạng thái đó.
- **`LockedException`:** tài khoản bị khóa và manager có khả năng kiểm tra trạng thái đó.
- **`AuthenticationException`:** lớp cha cho các lỗi xác thực khác, chẳng hạn token không được hỗ trợ, token hết hạn hoặc dịch vụ xác thực gặp lỗi.

JavaDoc mô tả thứ tự ưu tiên kiểm tra **disabled, locked, rồi credentials** khi các trạng thái đó được phát hiện; mục đích là tránh tiến hành kiểm tra credential cho account đã bị chặn. Từng provider/framework có các kiểm tra trạng thái riêng và thứ tự chi tiết có thể khác nhau khi nhiều cờ cùng bật; không thiết kế hành vi nghiệp vụ dựa trên chuỗi message nội bộ của exception.

Trong ứng dụng web, **exception từ `authenticate` không phải mã HTTP**. Bộ lọc, `AuthenticationEntryPoint`, failure handler hoặc thành phần chuyển đổi lỗi quyết định trả 401, redirect đến trang login, hoặc phản hồi phù hợp giao thức. Những exception cụ thể thường nên được ghi nhận an toàn ở server, còn phản hồi cho người dùng có thể dùng thông báo chung để tránh lộ username/tài khoản có tồn tại.

### 3.1. Không trả `null` từ manager để biểu diễn đăng nhập sai

Một phân biệt dễ nhầm:

- **`AuthenticationManager.authenticate`:** hợp đồng thành công trả `Authentication`, thất bại ném `AuthenticationException`.
- **`AuthenticationProvider.authenticate`:** có thể trả **`null`** khi provider không thể quyết định và muốn cho provider khác xử lý.

Vì vậy, một custom `AuthenticationManager` không nên lấy `null` làm “sai mật khẩu”; còn một custom `AuthenticationProvider` không nên lạm dụng `null` để che giấu việc credential của loại token nó chịu trách nhiệm đã bị xác thực thất bại. Với credential sai mà provider có trách nhiệm kiểm tra, hãy ném ngoại lệ thích hợp.

## 4. ProviderManager: cách triển khai thường gặp

`ProviderManager` là implementation phổ biến của `AuthenticationManager`. Nó giữ một danh sách các `AuthenticationProvider`, lần lượt thử provider cho yêu cầu. Logic hiểu ở mức khái niệm:

~~~text
for mỗi provider theo thứ tự cấu hình:
    if !provider.supports(request.getClass()):
        bỏ qua
    else:
        provider.authenticate(request)
        -> Authentication khác null: thành công, dừng
        -> null: chưa quyết định, thử provider kế tiếp
        -> AuthenticationException: ghi nhận thất bại; có thể thử tiếp
        -> AccountStatusException: dừng sớm, không thử tiếp

nếu chưa có kết quả:
    thử parent AuthenticationManager nếu đã cấu hình
nếu vẫn chưa có kết quả:
    ném lỗi xác thực phù hợp
khi thành công:
    có thể xóa credential khỏi kết quả theo cấu hình
    trả Authentication đã xác thực
~~~

Đây là **giả mã**, không phải Java có thể biên dịch. Mã triển khai có xử lý ngoại lệ, sự kiện và parent cụ thể; hãy xem `ProviderManager` của phiên bản đang sử dụng khi cần phân tích các trường hợp biên.

### 4.1. `supports(Class<?>)` chỉ kiểm tra loại token

Một provider hỗ trợ `UsernamePasswordAuthenticationToken` phải cho biết:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
~~~

Đây là **đoạn minh họa trong một class triển khai `AuthenticationProvider`**, không phải chương trình chạy độc lập. `supports` chỉ cho biết provider *có thể xử lý loại object này*; không chứng minh username/password đúng. Provider khác có thể hỗ trợ một loại token khác như JWT hay mã xác thực một lần.

**Sai lầm nguy hiểm:** viết custom provider `supports(...) == true`, rồi luôn trả về authenticated token mà không kiểm tra mật khẩu/chữ ký/hạn token. Điều đó biến một claim từ client thành danh tính được tin cậy.

### 4.2. Những kết quả có thể gặp khi có nhiều provider

| Provider thứ nhất | Provider tiếp theo | Ý nghĩa ở ProviderManager |
|---|---|---|
| `supports == false` | Có thể hỗ trợ | Provider đầu bị bỏ qua |
| `supports == true` và trả `null` | Có thể đưa ra quyết định | Provider đầu từ chối quyết định |
| Trả một `Authentication` hợp lệ | Không gọi tiếp | Lấy kết quả thành công |
| Ném `BadCredentialsException` | Có thể thành công | ProviderManager có thể tiếp tục; thành công sau đó có thể thay kết quả lỗi trước |
| Ném `DisabledException` / `LockedException` (AccountStatusException) | Không thử tiếp | Thất bại trạng thái tài khoản chặn fallback |
| Không provider nào xử lý, không parent | Không có | Có thể nhận `ProviderNotFoundException` |
| Không provider con nào xác thực, có parent | Parent được hỏi | Parent có thể xác thực theo cấu hình riêng |

**Quan hệ fallback là quyết định bảo mật.** Nếu hai provider đều có thể xác thực một loại username/password, cần làm rõ policy tránh “provider A từ chối mật khẩu, provider B cho qua bằng một phương pháp yếu hơn”. Xử lý `AccountStatusException` như trường hợp chặn là cơ chế riêng, không thay được chính sách chống bypass giữa các provider.

### 4.3. Parent AuthenticationManager

`ProviderManager` có thể có parent `AuthenticationManager`. Mô hình hữu ích khi nhiều `SecurityFilterChain` có chính sách xác thực riêng nhưng chia sẻ một phương thức chung:

~~~text
SecurityFilterChain /admin -> Manager A -> Provider Admin
                           \-> Parent Manager -> Provider chung

SecurityFilterChain /api   -> Manager B -> Provider API
                           \-> Parent Manager -> Provider chung
~~~

Không nên hiểu parent là bắt buộc. Nếu không có provider phù hợp và không có parent, lỗi kiểu `ProviderNotFoundException` là tín hiệu cần kiểm tra cấu hình và loại token yêu cầu. Đừng dùng một provider “always-success” để chữa lỗi không có provider.

### 4.4. Xóa credentials và cache

`ProviderManager` mặc định có `eraseCredentialsAfterAuthentication = true`. Nếu kết quả hỗ trợ `CredentialsContainer`, nó gọi `eraseCredentials()` để giảm thời gian giữ bí mật trong bộ nhớ. Ví dụ username/password, kết quả thường không còn raw password khi được trả cho caller.

Cần lưu ý: principal cũng có thể là `UserDetails` chứa password hash. Một implementation có thể xóa dữ liệu bí mật bên trong principal; nếu provider/cache dùng **cùng instance** cho nhiều request, cache có thể bị ảnh hưởng. Thiết kế cache phải copy dữ liệu thích hợp hoặc bảo đảm credential cần kiểm tra còn sẵn ở nguồn đáng tin. Việc tắt xóa credential bằng `setEraseCredentialsAfterAuthentication(false)` làm tăng rủi ro và không nên là giải pháp mặc định.

### 4.5. Sự kiện xác thực

`ProviderManager` có thể sử dụng `AuthenticationEventPublisher` để phát sự kiện thành công/thất bại. Khi tự tạo một `ProviderManager` độc lập, không nên mặc định rằng sự kiện Spring application sẽ tự được phát đầy đủ: implementation có publisher mặc định không phát sự kiện nếu chưa cấu hình. Ở môi trường có parent manager, cần tránh trùng event nếu cả parent và child cùng phát.

Sự kiện thích hợp cho audit và quan sát, **không phải thay thế** cơ chế chặn brute-force, rate limiting, session management hoặc quyết định xác thực.

## 5. Ví dụ chạy được: gọi authenticate bằng Java 17 và Spring Security 6.3

Ví dụ này cố tình tách khỏi HTTP để bạn nhìn trực tiếp **hợp đồng method**. Ta tự tạo `ProviderManager` chứa `DaoAuthenticationProvider`, nhận ba tình huống account và một loại token không hỗ trợ.

`DaoAuthenticationProvider` sử dụng `UserDetailsService` tải thông tin tài khoản, `PasswordEncoder` kiểm tra mật khẩu và các kiểm tra trạng thái tài khoản tích hợp. `InMemoryUserDetailsManager` chỉ giữ dữ liệu minh họa trong bộ nhớ, không phải database nghiệp vụ.

### 5.1. Cấu trúc dự án

~~~text
auth-manager-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/AuthManagerDemo.java
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'auth-manager-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.7'
    implementation 'org.springframework.security:spring-security-crypto:6.3.7'
}

application {
    mainClass = 'example.AuthManagerDemo'
}
~~~

Dùng phiên bản cố định trong ví dụ để các method như `DaoAuthenticationProvider()` và `setUserDetailsService(...)` khớp với Spring Security 6.3. Ở các phiên bản mới hơn, constructor của `DaoAuthenticationProvider` có thể được khuyến nghị dùng trực tiếp `UserDetailsService`; cần đối chiếu JavaDoc phiên bản dự án. Mẫu chỉ dùng thư viện Spring Security Core/Crypto, không cần server web hoặc Spring Boot.

### 5.2. Mã Java đầy đủ

Tạo `src/main/java/example/AuthManagerDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class AuthManagerDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .build();

        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .disabled(true)
                .build();

        UserDetails an = User.withUsername("an")
                .password(encoder.encode("learn-123"))
                .authorities("notes:read")
                .accountLocked(true)
                .build();

        UserDetailsService users =
                new InMemoryUserDetailsManager(linh, khoa, an);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(List.of(dao));

        attempt(manager, "linh", "learn-123");
        attempt(manager, "linh", "wrong");
        attempt(manager, "khoa", "learn-123");
        attempt(manager, "an", "learn-123");

        try {
            manager.authenticate(
                    new TestingAuthenticationToken("linh", "learn-123"));
        } catch (AuthenticationException ex) {
            System.out.println("unsupported -> "
                    + ex.getClass().getSimpleName());
        }
    }

    private static void attempt(AuthenticationManager manager,
                                String username, String password) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            Authentication result = manager.authenticate(request);
            String authority = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .findFirst()
                    .orElse("(none)");

            System.out.println(username + " -> OK: "
                    + result.getName()
                    + ", authenticated=" + result.isAuthenticated()
                    + ", authority=" + authority
                    + ", credentials=" + result.getCredentials());
        } catch (AuthenticationException ex) {
            System.out.println(username + " -> FAIL: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Tất cả imports và class chính đều nằm trong một tệp. `BadCredentialsException` trong imports không cần dùng trực tiếp vì chương trình bắt lớp cha `AuthenticationException`; có thể bỏ import đó mà hành vi giữ nguyên.

### 5.3. Chạy và giải thích kết quả

Ở thư mục `auth-manager-demo`, dùng Gradle Wrapper nếu đã tạo wrapper, hoặc Gradle cài sẵn tương thích:

~~~bash
./gradlew run
~~~

Trên Windows PowerShell có thể dùng `.\gradlew.bat run` nếu dự án có Gradle Wrapper. Nếu chưa có wrapper nhưng đã cài Gradle, dùng `gradle run`. Đầu ra của riêng chương trình Java:

~~~text
linh -> OK: linh, authenticated=true, authority=notes:read, credentials=null
linh -> FAIL: BadCredentialsException
khoa -> FAIL: DisabledException
an -> FAIL: LockedException
unsupported -> ProviderNotFoundException
~~~

**Giải thích từng dòng:**

1. `linh` và mật khẩu đúng: provider load `UserDetails`, kiểm tra bcrypt, trả authentication đã xác thực và authority `notes:read`; manager xử lý credential erasure nên `getCredentials()` là `null`.
2. `linh` và mật khẩu sai: không trả kết quả thành công; ném `BadCredentialsException`.
3. `khoa` có bản ghi tài khoản nhưng `disabled=true`: ném `DisabledException`, cho thấy tài khoản tồn tại không đồng nghĩa đăng nhập được.
4. `an` có bản ghi nhưng `accountLocked=true`: ném `LockedException`.
5. `TestingAuthenticationToken` không thuộc loại `UsernamePasswordAuthenticationToken` được `DaoAuthenticationProvider` hỗ trợ: không provider nào xử lý, ném `ProviderNotFoundException`.

Trong ví dụ, dùng `BCryptPasswordEncoder` để lưu hash thay vì mật khẩu plaintext. `learn-123` chỉ là mật khẩu minh họa và không được dùng trong môi trường thật. Password encoder tạo salt ngẫu nhiên, nên giá trị hash có thể khác giữa các lần chạy nhưng kết quả xác thực và các dòng stdout trên không thay đổi.

**Tại sao thử `TestingAuthenticationToken` hữu ích?** Nó cho thấy `ProviderManager` không “thử đại” mật khẩu với một provider không hỗ trợ loại token, và lỗi cấu hình/loại token khác với credential sai.

### 5.4. Từ ví dụ sang ứng dụng Spring Boot có HTTP

Ở ứng dụng Servlet, bạn không cần tự gọi `manager.authenticate(...)` trong mọi controller. Những filter như HTTP Basic hoặc form login sẽ tạo token đầu vào, gọi manager theo cấu hình, xử lý thành công/thất bại và phối hợp cập nhật `SecurityContext`.

Một cấu hình **minh họa trong một class `@Configuration`**, giả định đã có các imports và bean `UserDetailsService`, `PasswordEncoder` thích hợp:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http, AuthenticationManager authenticationManager)
        throws Exception {
    return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đoạn trên **không phải chương trình độc lập**; nó là mảnh cấu hình tích hợp vào ứng dụng Spring Boot 3.x dùng `spring-boot-starter-security` và Spring MVC. Tùy cấu hình, Spring Security có thể tạo authentication manager thông qua `AuthenticationConfiguration` và các security configurer; không phải lúc nào bạn cũng cần định nghĩa bean `AuthenticationManager` thủ công. Khi có nhiều `SecurityFilterChain`, manager dùng cho từng chain và manager dùng ở mức toàn cục có thể khác nhau; phải đối chiếu cấu hình thực tế, không đoán từ tên bean.

## 6. Gọi authenticate thủ công: phần việc nào chưa hoàn thành?

Một anti-pattern phổ biến là tạo endpoint `POST /login` và viết:

~~~java
Authentication result = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
return "login success";
~~~

Đây là **đoạn minh họa, không phải controller hoàn chỉnh**. Nó chứng minh credential hợp lệ nhưng **chưa bảo đảm** một request HTTP tiếp theo đã có danh tính.

Vì sao? `AuthenticationManager` không mặc định lưu `Authentication` vào `SecurityContextHolder`, không tạo HTTP session, không phát cookie, không phát JWT, không tự xử lý CSRF/session fixation, và không thực thi toàn bộ chiến lược login/logout.

Nếu bạn tự viết luồng login thay vì dùng bộ lọc và handler tiêu chuẩn, phải chủ động thiết kế các bước thích hợp:

1. Nhận input qua kênh an toàn, giới hạn thử đăng nhập và validation; không log raw password.
2. Tạo `Authentication` chưa xác thực; gọi manager; xử lý `AuthenticationException` đúng cách.
3. Nếu login thành công và ứng dụng dùng session: tạo một `SecurityContext` mới, gắn result, dùng cơ chế session authentication strategy/session fixation protection và `SecurityContextRepository.saveContext(...)` phù hợp để yêu cầu tiếp theo khôi phục được context; xem xét CSRF.
4. Nếu ứng dụng phát access/refresh token: có quy tắc phát, ký, thời hạn, rotation, thu hồi và lưu bảo mật token. Kết quả `authenticate` chưa phải token API mà client có thể gửi ở các request tiếp theo.
5. Nếu thất bại: không thiết lập context thành công; hủy/bỏ context sai, trả phản hồi an toàn và audit sự kiện hợp lý.

Để minh họa phần tạo context ở mức API (chưa bao gồm chiến lược session và persistence):

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);
~~~

Đoạn này **không tự lưu session**; trong cấu hình Spring Security hiện đại, nếu cần giữ context giữa các request phải lưu qua `SecurityContextRepository` phù hợp. Trong ứng dụng thật, ưu tiên cơ chế login/filter chuẩn nếu nó đáp ứng yêu cầu vì nhiều bước bảo mật đã được tích hợp.

### 6.1. Vì sao `authenticate` có thể thành công mà request vẫn bị 403?

Sau khi xác thực, request còn trải qua quy tắc phân quyền. Kết quả `Authentication` có thể chứa `notes:read` nhưng endpoint lại đòi `notes:write`. Khi đó AuthN thành công và AuthZ từ chối. Lỗi thiếu quyền không nên chữa bằng cách sửa authentication provider trả thêm authority mà không có chính sách cấp quyền.

### 6.2. Vì sao không gán một boolean “isLoggedIn” trong database?

`AuthenticationManager` kiểm tra bằng chứng hiện tại, không quản lý trạng thái “đã đăng nhập” vĩnh viễn trên row tài khoản. Phiên/token có vòng đời riêng. Account có thể bị khóa sau login, trong khi session/JWT cũ vẫn tồn tại nếu ứng dụng chưa có cơ chế thu hồi hoặc kiểm tra trạng thái hiện thời. Đó là bài toán vòng đời tài khoản và chiến lược session/token, không phải hợp đồng một lần gọi `authenticate`.

## 7. Khi nào cần tự viết AuthenticationProvider hoặc AuthenticationManager?

Thông thường, **cấu hình provider chuẩn** dễ kiểm tra và ít rủi ro hơn việc tự triển khai bộ máy. Ví dụ:

- Username/password với database: `DaoAuthenticationProvider` + `UserDetailsService` + `PasswordEncoder` hoặc cơ chế tương thích.
- JWT resource server: cơ chế filter/manager/provider dành cho bearer JWT theo resource-server configuration.
- OAuth2 Login/OIDC: các authentication providers và filters tương ứng do Spring Security cung cấp.
- Credential riêng của hệ thống: cân nhắc custom `AuthenticationProvider` với loại token rõ ràng, kiểm tra đầy đủ bằng chứng và status, principal/quyền được phát từ nguồn tin cậy.

Custom `AuthenticationManager` có thể hợp lý khi thật sự cần chiến lược điều phối khác với `ProviderManager`, nhưng phần lớn nhu cầu mở rộng nằm ở provider, token converter, user-details service, authentication success/failure handler hoặc policy quản lý tài khoản.

### 7.1. Hợp đồng tối thiểu cho custom AuthenticationProvider

| Phương thức | Kết quả đúng | Ví dụ |
|---|---|---|
| `supports(type)` | `true` nếu provider có khả năng xử lý kiểu `Authentication` đó | Hỗ trợ token API key, không tự nhận JWT |
| `authenticate(request)` | Trả authenticated token **khi credential hợp lệ** | Đã xác minh API key tồn tại, còn hạn, chưa thu hồi |
| `authenticate(request)` | Ném `AuthenticationException` khi xác thực thất bại | API key bị thu hồi hoặc secret sai |
| `authenticate(request)` | Trả `null` khi không thể ra quyết định và cho phép provider khác thử | Provider chỉ giải quyết một biến thể của token |
| Authenticated result | Principal/authorities từ phía server | Không copy quyền `admin` do client tự khai báo |

Với OTP/MFA, “mật khẩu đúng” có thể chỉ là một **bước** xác thực; không được phát authentication cuối cùng có quyền truy cập đầy đủ khi bước MFA bắt buộc chưa hoàn tất. Hãy dùng authentication flow/state phù hợp thay vì coi mỗi provider thành công là hoàn thành mọi yếu tố.

### 7.2. Lưu ý về lỗi đăng nhập, cache và chống dò tài khoản

- **Không phân biệt username có tồn tại qua API công khai** bằng thông báo/độ trễ bất cẩn. `DaoAuthenticationProvider` mặc định có cơ chế che giấu `UsernameNotFoundException` thành lỗi credential không hợp lệ trong những trường hợp thông thường.
- **Không mở fallback yếu** sau khi provider khác xác nhận thông tin đăng nhập sai. Thứ tự provider ảnh hưởng kết quả.
- **Không giữ credential trong cache quá cần thiết**; tránh in `Authentication` vào log và kiểm soát việc xóa bí mật.
- **Không dùng BCrypt hoặc password hash thường để xác minh chữ ký JWT**: mỗi loại token/bằng chứng có cơ chế xác minh riêng.
- **Không chuyển thẳng `AuthenticationException` thành 200** hoặc trả full stacktrace; tách lỗi vận hành với phản hồi người dùng.
- **Không cho phép “login success” chỉ từ `supports=true`**; provider phải xác minh bí mật, account status và điều kiện liên quan.

## 8. Kiểm thử theo hợp đồng, không chỉ theo màn hình đăng nhập

Một bộ kiểm thử authentication tốt cần bao quát cả đầu vào, kết quả, ngoại lệ và tích hợp ngữ cảnh:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Username/password đúng, account active | `Authentication` thành công, principal và authorities đúng |
| Username đúng, password sai | `BadCredentialsException` hoặc lỗi được chuẩn hóa thích hợp |
| Username không tồn tại | Không rò thông tin chi tiết qua phản hồi công khai |
| Account disabled / locked | Bị từ chối và không vòng qua provider khác |
| Token loại không hỗ trợ | `ProviderNotFoundException` hoặc lỗi cấu hình phù hợp |
| Provider A trả `null`, B hỗ trợ | Provider B có cơ hội xác thực |
| Provider A thành công | Provider B không được gọi |
| Provider A ném `BadCredentialsException`, B cùng loại | Chính sách fallback được đánh giá và thử nghiệm chống bypass |
| Provider ném `AccountStatusException` | Chuỗi provider dừng sớm đúng chính sách |
| Thành công với password | Credential được xóa hoặc không tồn tại trong kết quả trả ra |
| Đổi quyền khi session/token còn hạn | Quyền cũ không tồn tại vượt thời gian chính sách cho phép |
| Tự gọi `authenticate` trong login API | Ngữ cảnh và phiên/token được thiết lập, lưu/thu hồi đúng chiến lược |
| AuthN thành công, thiếu quyền tài nguyên | AuthZ vẫn từ chối |
| Request anonymous / session hết hạn | Không bị coi là authenticated user chỉ vì có object trong context |
| Login chạy đồng thời / lỗi backend identity store | Không cấp authenticated token sai, có log và bảo vệ quá tải phù hợp |

Đặc biệt nên có test chứng minh **không gọi provider không hỗ trợ loại token** và **không dùng lại principal/authorities do phía client tự tạo**. Khi có nhiều provider, test rõ thứ tự và kết quả fallback chứ không chỉ test một người dùng hợp lệ.

## 9. Các câu hỏi tự kiểm tra

**Câu 1.** Gọi `manager.authenticate(request)` thành công có tự thiết lập `SecurityContextHolder` không?  
**Đáp án:** Không. Bên gọi/filter phải quản lý context; lưu session hoặc phát token cần cơ chế riêng.

**Câu 2.** `AuthenticationProvider.supports(type)` trả `true` nghĩa là token đã đúng?  
**Đáp án:** Không. Đó chỉ là khả năng xử lý loại token. `authenticate` của provider mới kiểm tra bằng chứng.

**Câu 3.** Provider có thể trả `null`, còn manager có nên dùng `null` để báo sai mật khẩu?  
**Đáp án:** Provider có thể trả `null` để từ chối quyết định và cho provider khác thử. Hợp đồng manager mô tả thành công bằng kết quả `Authentication`, thất bại bằng `AuthenticationException`.

**Câu 4.** Khi một `ProviderManager` có hai provider cùng hỗ trợ username/password, provider đầu ném `BadCredentialsException`, provider sau có còn cơ hội không?  
**Đáp án:** Có thể còn. ProviderManager có khả năng tiếp tục sau một số lỗi xác thực; cần xét exception cụ thể, thứ tự và policy. Các `AccountStatusException` đặc biệt có thể chặn chuỗi.

**Câu 5.** Vì sao sau `authenticate`, `result.getCredentials()` thường là `null`?  
**Đáp án:** `ProviderManager` mặc định cố xóa credential khỏi kết quả nếu nó hỗ trợ `CredentialsContainer`, giảm nguy cơ bí mật nằm lâu trong bộ nhớ.

**Câu 6.** Username/password đúng, nhưng API trả 403. Đây có phải manager xác thực sai?  
**Đáp án:** Không nhất thiết. Manager có thể xác thực thành công, còn AuthorizationManager hoặc method security từ chối vì thiếu quyền.

**Câu 7.** Có thể giải quyết lỗi `ProviderNotFoundException` bằng cách luôn trả authentication thành công cho mọi token không?  
**Đáp án:** Không. Phải cấu hình provider hỗ trợ đúng loại token và kiểm tra đầy đủ bằng chứng; trả thành công vô điều kiện là lỗ hổng xác thực.

## 10. Ghi nhớ khi áp dụng

1. **`AuthenticationManager.authenticate` là ranh giới xác minh**: request chứa claim/credential chưa tin cậy; kết quả thành công mang principal và authorities đã xác thực.
2. **`ProviderManager` điều phối provider**: `supports` lựa chọn loại token, `authenticate` quyết định; provider trả `null`, trả kết quả hoặc ném lỗi; thứ tự và fallback có ảnh hưởng bảo mật.
3. **Hợp đồng lỗi rõ ràng**: không giả lập authenticated token khi chưa kiểm tra credential; xử lý disabled/locked và lỗi bí mật an toàn, không làm rò thông tin.
4. **Context/session/token thuộc bước tích hợp khác**: gọi manager thành công không mặc nhiên duy trì login trên HTTP request tiếp theo.
5. **AuthN khác AuthZ**: có principal đã xác thực mới là cơ sở kiểm tra quyền; không cấp quyền vô điều kiện từ input phía client.
6. **Xóa credentials và kiểm thử fallback** là một phần thiết kế an toàn của authentication pipeline.

### Tài liệu chính thức

- [`AuthenticationManager` JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/AuthenticationManager.html): chữ ký `authenticate`, giá trị trả về và hợp đồng ngoại lệ.
- [`ProviderManager` JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/ProviderManager.html): thử providers, fallback parent, `AccountStatusException` và xóa credential.
- [Servlet Authentication Architecture — Spring Security Reference](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): quan hệ giữa manager, provider, authentication filter và security context.
- [`DaoAuthenticationProvider` — Spring Security Reference](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): xác thực username/password bằng `UserDetailsService` và `PasswordEncoder`.
