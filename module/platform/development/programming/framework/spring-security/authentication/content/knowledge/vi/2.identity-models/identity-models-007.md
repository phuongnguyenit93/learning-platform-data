# UsernamePasswordAuthenticationToken trước và sau xác thực

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Mô hình danh tính.

## 1. Vấn đề cần hiểu

Trong Spring Security, cùng một kiểu Java **`UsernamePasswordAuthenticationToken`** có thể mang **hai ý nghĩa rất khác nhau**:

- **Trước xác thực:** một *yêu cầu xác thực* chứa định danh người dùng và credential do client vừa cung cấp. Hệ thống **chưa tin** danh tính đó.
- **Sau xác thực thành công:** một *kết quả xác thực* do thành phần đáng tin tạo ra, chứa principal đã kiểm tra và các quyền đã được cấp. Hệ thống có thể đưa kết quả này vào `SecurityContext` để dùng cho bước phân quyền.

Tên lớp có chữ *Token* nhưng đây **không phải access token JWT/Bearer**, cũng **không phải session ID**. Nó là một implementation của interface **`Authentication`**, đặc biệt thường xuất hiện trong luồng username/password. Hiểu vòng đời của đối tượng này giúp tránh một lỗi bảo mật rất nghiêm trọng: **đánh dấu dữ liệu client chưa được kiểm tra thành người dùng đã đăng nhập**.

~~~text
CLIENT GỬI USERNAME + PASSWORD
            |
            v
UsernamePasswordAuthenticationToken
      isAuthenticated() = false
      principal = username
      credentials = raw password
            |
            v
AuthenticationManager
            |
            v
AuthenticationProvider (ví dụ DaoAuthenticationProvider)
      -> load UserDetails
      -> PasswordEncoder.matches(...)
      -> kiểm tra trạng thái tài khoản
            |
            |-- thất bại --> AuthenticationException
            |
            v
UsernamePasswordAuthenticationToken (kết quả)
      isAuthenticated() = true
      principal = UserDetails hoặc danh tính đã xác minh
      authorities = quyền do hệ thống tin cậy gán
      credentials = thường được xóa sau xác thực
            |
            v
SecurityContext -> authorization của request
~~~

**Điểm quan trọng:** Thông thường đây là **hai đối tượng riêng** được chuyển qua `AuthenticationManager`. Không nên hình dung rằng Spring đơn giản gọi `setAuthenticated(true)` lên token chứa mật khẩu vừa nhận rồi hoàn tất.

## 2. Cấu trúc của một UsernamePasswordAuthenticationToken

`UsernamePasswordAuthenticationToken` thuộc package `org.springframework.security.authentication` và kế thừa `AbstractAuthenticationToken`. Nó triển khai `Authentication`, trong đó có các thành phần:

| Thành phần | Ý nghĩa | Trước xác thực | Sau xác thực thành công |
| --- | --- | --- | --- |
| `getPrincipal()` | Danh tính được khai báo hoặc đã được xác minh | Thường là chuỗi username do client cung cấp | Thường là đối tượng `UserDetails` từ `UserDetailsService`; có thể là kiểu khác |
| `getCredentials()` | Bằng chứng để xác minh danh tính | Thường là raw password vừa nhập | Thường là `null` khi `ProviderManager` xóa credentials mặc định |
| `getAuthorities()` | Các `GrantedAuthority` cho bước phân quyền | Thường rỗng; client không được tự cấp quyền | Vai trò/quyền đáng tin được provider nạp và ánh xạ |
| `isAuthenticated()` | Trạng thái tin cậy của đối tượng xác thực | `false` | `true` khi xác thực thành công |
| `getDetails()` | Metadata tùy theo cơ chế request | Có thể là thông tin request, địa chỉ từ xa, session ID... | Có thể được chuyển tiếp hoặc xử lý lại |
| `getName()` | Tên nhận diện được trích từ principal | Thường là username dạng `String` | Thường vẫn là username dù principal đã đổi kiểu |

**Principal không nhất thiết luôn là `String`.** Cũng không được giả định `getCredentials() == null` đồng nghĩa chưa đăng nhập. Trong một kết quả đã được xác thực, Spring thường chủ động xóa password khỏi token.

**Authorities không phải credential:** `ROLE_READER`, `ROLE_ADMIN` hay permission là thông tin để thực hiện authorization sau AuthN; việc password hợp lệ **không tự tạo** các quyền tùy ý. Quyền phải đến từ nguồn được hệ thống tin cậy.

**Details không phải bằng chứng xác thực thay thế:** Các trường như IP address hoặc session ID chỉ là metadata; phải xét proxy và cấu hình server, và không nên dùng đơn độc để quyết định danh tính hay quyền truy cập.

## 3. Constructor và factory: cách tạo token quyết định trạng thái

Với Spring Security 5.7 trở lên, có thể ưu tiên hai static factory để thể hiện ý định. Constructor cũ vẫn hữu ích khi đọc code:

| Cách tạo | `isAuthenticated()` | Ai nên sử dụng? |
| --- | --- | --- |
| `new UsernamePasswordAuthenticationToken(principal, credentials)` | `false` | Filter/controller tạo **yêu cầu** xác thực |
| `UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)` | `false` | Filter/controller tạo **yêu cầu** xác thực; tên gọi rõ ràng |
| `new UsernamePasswordAuthenticationToken(principal, credentials, authorities)` | `true` | **Chỉ** thành phần đáng tin đã xác minh danh tính, ví dụ provider |
| `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` | `true` | **Chỉ** thành phần đáng tin tạo **kết quả** đã xác thực |

Ví dụ ngắn về API:

~~~java
// Chưa xác thực: dữ liệu người dùng vừa gửi.
UsernamePasswordAuthenticationToken request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", "raw-password-from-login"
        );

// Kết quả đã được kiểm chứng: CHỈ tạo trong mã đáng tin của provider.
// principal đã được xác minh; authorities đến từ hệ thống, không từ client.
UsernamePasswordAuthenticationToken success =
        UsernamePasswordAuthenticationToken.authenticated(
                verifiedPrincipal, null, verifiedAuthorities
        );
~~~

Đoạn trên là **minh họa cách gọi API**, chưa phải một chương trình độc lập: các biến `verifiedPrincipal` và `verifiedAuthorities` phải được lấy từ quá trình xác thực đáng tin. **Không bao giờ** chèn username/role từ HTTP request vào factory `authenticated(...)` để “đăng nhập nhanh”.

**Vì sao không gọi `request.setAuthenticated(true)`?** Trong implementation `UsernamePasswordAuthenticationToken`, thao tác này bị từ chối bằng `IllegalArgumentException`. Hàm có thể nhận `false` để đánh dấu token không còn đáng tin, nhưng đó **không phải quy trình logout**, và không thay thế việc xóa `SecurityContext`/vô hiệu hóa session thích hợp.

**Bẫy constructor ba tham số:** Constructor nhận danh sách authorities lập tức tạo token có `isAuthenticated() = true`. Việc truyền một danh sách rỗng cũng **không biến** nó thành token chưa xác thực. Vì vậy, tuyệt đối không dùng constructor ba tham số để xây request từ dữ liệu client.

## 4. Ai thực hiện việc chuyển đổi trước → sau?

Trong luồng form login của **Spring Security Servlet**, các vai trò được phân tách:

1. **Authentication filter** (chẳng hạn `UsernamePasswordAuthenticationFilter`) đọc thông tin login và tạo một `UsernamePasswordAuthenticationToken` chưa xác thực.
2. **AuthenticationManager** nhận request token. Implementation phổ biến là `ProviderManager`, điều phối một hay nhiều `AuthenticationProvider`.
3. **DaoAuthenticationProvider** hỗ trợ username/password, dùng `UserDetailsService` tìm người dùng đã đăng ký; `PasswordEncoder` so sánh raw password với password hash đã lưu và kiểm tra trạng thái tài khoản.
4. **Nếu hợp lệ**, provider tạo một `Authentication` đã xác thực, thường vẫn có kiểu `UsernamePasswordAuthenticationToken` nhưng principal phong phú hơn và có authorities đáng tin.
5. **ProviderManager** theo mặc định thực hiện xóa thông tin credential nhạy cảm trên kết quả nếu đối tượng triển khai `CredentialsContainer`.
6. **Filter thành công** đưa kết quả xác thực vào `SecurityContextHolder`; cơ chế `SecurityContextRepository`/session xử lý việc lưu cho request tiếp theo nếu cấu hình cần.
7. **Authorization** dựa trên Authentication đã xác thực cùng authorities/chính sách để quyết định endpoint được truy cập hay không.

~~~text
HTTP POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    | request = unauthenticated(username, rawPassword)
    v
AuthenticationManager / ProviderManager
    |
    +--> DaoAuthenticationProvider
              | UserDetailsService.loadUserByUsername(username)
              | PasswordEncoder.matches(rawPassword, storedHash)
              | kiểm tra disabled/locked/expired ...
              v
          tạo trusted Authentication + authorities
    |
    +--> ProviderManager.eraseCredentialsAfterAuthentication (mặc định true)
    v
Authentication result
    |
    +--> SecurityContextHolder cho request hiện tại
    +--> SecurityContextRepository nếu phải lưu sang request sau
    v
AuthorizationManager / SecurityFilterChain
~~~

**Kết quả xác thực không phải bản ghi người dùng:** `UserDetailsService` chịu trách nhiệm tải dữ liệu, `AuthenticationProvider` xác minh credential, còn `Authentication` đại diện danh tính trong ngữ cảnh xử lý bảo mật.

**Thất bại là ngoại lệ, không phải token “false” mới:** Credential sai có thể làm `AuthenticationManager.authenticate(...)` ném `BadCredentialsException`; tài khoản khóa/hết hạn có thể tạo `AuthenticationException` phù hợp. Hệ thống không được đưa request token chưa xác thực vào context như thể đã đăng nhập.

Một request token có `isAuthenticated() = false` trước khi gọi manager là **đúng thiết kế**; không phải lỗi cần sửa bằng setter.

## 5. Demo chạy được: cùng dữ liệu, hai trạng thái khác nhau

Ví dụ sau chạy độc lập như một ứng dụng Java 17+ có Spring Security Core **6.5.11** và Spring Security Crypto. Nó sử dụng `InMemoryUserDetailsManager` để tránh database và tập trung vào vòng đời `UsernamePasswordAuthenticationToken`. Mật khẩu demo chỉ phục vụ học tập.

Tạo cấu trúc thư mục:

~~~text
token-lifecycle/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── TokenLifecycleDemo.java
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.TokenLifecycleDemo'
}
~~~

File **src/main/java/demo/TokenLifecycleDemo.java**:

~~~java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class TokenLifecycleDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails account = User.withUsername("lan")
                .password(encoder.encode("learn-only-password"))
                .roles("READER")
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // 1) Request: chỉ chứa thông tin khai báo của client.
        UsernamePasswordAuthenticationToken request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "learn-only-password"
                );

        System.out.println("before.authenticated=" + request.isAuthenticated());
        System.out.println("before.principal=" + request.getPrincipal());
        System.out.println("before.authoritiesCount=" + request.getAuthorities().size());
        System.out.println("before.credentialsPresent=" + (request.getCredentials() != null));

        // 2) Credential sai: manager ném ngoại lệ, không tạo trusted result.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"
                    )
            );
            System.out.println("badPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("badPassword=BadCredentialsException");
        }

        // 3) Credential đúng: kết quả do provider/manager đáng tin tạo.
        Authentication result = manager.authenticate(request);

        boolean hasReaderRole = result.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));

        System.out.println("after.authenticated=" + result.isAuthenticated());
        System.out.println("after.type=" + result.getClass().getSimpleName());
        System.out.println("after.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("after.name=" + result.getName());
        System.out.println("after.hasReaderRole=" + hasReaderRole);
        System.out.println("after.credentialsErased=" + (result.getCredentials() == null));

        // 4) Manager xóa credentials khỏi KẾT QUẢ, không bảo đảm
        // tự xóa đối tượng request mà caller vẫn còn giữ.
        System.out.println("request.credentialsStillPresent="
                + (request.getCredentials() != null));
    }
}
~~~

Chạy từ thư mục chứa `build.gradle` với JDK 17+ và Gradle đã cài:

~~~bash
gradle -q run
~~~

Hoặc dùng Gradle Wrapper nếu dự án đã có wrapper:

~~~bash
./gradlew -q run
~~~

Trên Windows dùng `gradlew.bat -q run`. **stdout do lớp `TokenLifecycleDemo` phát ra** (không tính thông báo/log riêng của Gradle hoặc thư viện nếu bật):

~~~text
before.authenticated=false
before.principal=lan
before.authoritiesCount=0
before.credentialsPresent=true
badPassword=BadCredentialsException
after.authenticated=true
after.type=UsernamePasswordAuthenticationToken
after.principalIsUserDetails=true
after.name=lan
after.hasReaderRole=true
after.credentialsErased=true
request.credentialsStillPresent=true
~~~

### Vì sao kết quả này có ý nghĩa?

- `before.authenticated=false`: constructor/factory request **không** xác thực người dùng khi chỉ biết chuỗi username và password.
- `before.authoritiesCount=0`: hệ thống chưa gán quyền vì chưa biết credential có đúng hay không.
- `badPassword=BadCredentialsException`: credential sai dẫn tới thất bại, không có đối tượng authenticated trả về.
- `after.authenticated=true`: chỉ sau khi provider xác minh password với hash đã lưu, manager mới trả kết quả đáng tin.
- `after.principalIsUserDetails=true`: principal sau xác thực thường là đối tượng từ `UserDetailsService`, khác với chuỗi username ban đầu.
- `after.hasReaderRole=true`: quyền `ROLE_READER` đến từ account đã lưu, không do HTTP request khai báo.
- `after.credentialsErased=true`: `ProviderManager` mặc định xóa credentials khỏi kết quả. Điều này **không làm mất trạng thái đã xác thực**.
- `request.credentialsStillPresent=true`: đối tượng request vẫn có thể giữ raw password. Không giữ nó lâu hơn cần thiết và tuyệt đối không log nó.

**Lưu ý phiên bản:** API factory `unauthenticated(...)` và `authenticated(...)` có từ Spring Security 5.7. Demo cố định dependency 6.5.11 để giải thích đầu ra nhất quán. Trong ứng dụng Spring Boot hiện có, nên để BOM/dependency management của dự án quản lý các phiên bản Spring thay vì trộn tùy ý.

## 6. Điểm chuyển đổi nằm ở đâu trong code web thực tế?

Trong ứng dụng Spring Security cấu hình **`formLogin(...)`**, phần lớn quy trình trên đã được filter và provider của Spring thực hiện. Người viết controller thông thường **không cần** tự tạo trusted token. Một bản phác thảo luồng logic để đọc code là:

~~~java
// MÃ PHÁC THẢO: các biến đã được cấu hình trong ứng dụng Servlet.
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
        submittedUsername, submittedPassword
);

Authentication result = authenticationManager.authenticate(request);

// Sau khi xác thực, không lấy quyền từ body/request của client.
// Spring Security web filter tiêu chuẩn có các bước quản lý context,
// session strategy, saveContext, success/failure handler tương ứng.
~~~

Đây là mã minh họa, **không phải class Java độc lập**; `submittedUsername`, `submittedPassword` và `authenticationManager` đến từ môi trường web đã cấu hình.

### AuthenticationManager không đồng nghĩa login được lưu qua mọi request

`authenticate(...)` trả về **kết quả xác thực**, nhưng việc gọi hàm đó trong controller tùy chỉnh chưa tự đảm bảo browser được lưu phiên đăng nhập. Với Servlet, cần đặt kết quả vào `SecurityContext` theo vòng đời request và, nếu dùng session, **lưu** qua `SecurityContextRepository` đúng với phiên bản Spring Security đang chạy.

~~~text
authenticationManager.authenticate(request)
    -> authenticated result
    -> SecurityContext.setAuthentication(result)
    -> SecurityContextHolder.setContext(context)
    -> SecurityContextRepository.saveContext(...) khi cần persistence
    -> response và session/cookie do hạ tầng web xử lý
~~~

Trong môi trường thực, luồng login còn có session fixation protection, session strategy, CSRF, success/failure handlers và cơ chế logout. Dùng `formLogin`/các filter có sẵn nếu đáp ứng yêu cầu; đừng bỏ qua các mắt xích đó khi tự viết endpoint.

**Sang request khác:** Spring có thể lấy lại `Authentication` từ `SecurityContextRepository`, ví dụ từ HTTP session. Điều đó không có nghĩa username/password phải được gửi lại hay `DaoAuthenticationProvider` phải chạy lại mỗi lần truy cập URL được bảo vệ.

## 7. Những điều dễ hiểu sai về authenticated, principal và authorities

### `isAuthenticated()` là trạng thái tin cậy, không phải chứng cứ độc lập

Một đối tượng được tạo bằng factory `authenticated(...)` sẽ có cờ `true` ngay lúc tạo. **Cờ không tự chứng minh password đã được kiểm tra**: tính an toàn phụ thuộc việc chỉ có thành phần server đáng tin tạo token dạng đó sau khi xác minh credential.

Một bên client gửi JSON `{"username":"lan","authenticated":true}` không có giá trị bảo mật; đừng bao giờ bind trực tiếp dữ liệu đó thành một `Authentication` tin cậy.

### `isAuthenticated() == true` không đồng nghĩa có mọi quyền

Authorization phải kiểm tra `GrantedAuthority`, role và chính sách theo tài nguyên. Có thể tồn tại token authenticated nhưng không có quyền yêu cầu. Ngoài ra, các implementation Authentication khác (như anonymous) có thể có cách biểu diễn trạng thái riêng; với chính sách web, nên dùng API authorization của Spring, không tự lấy mỗi boolean `isAuthenticated()` làm định nghĩa đầy đủ của “người dùng thực đã đăng nhập”.

### `getPrincipal()` thay đổi kiểu là hành vi bình thường

Trước login, principal thường là chuỗi username. Sau login, principal thường là `UserDetails` hay custom domain principal được provider xác minh. Vì vậy, đoạn như `(String) authentication.getPrincipal()` có thể ném `ClassCastException` sau xác thực. Nếu cần username, `authentication.getName()` thường ổn định hơn; nếu cần dữ liệu khác, kiểm tra kiểu rõ ràng.

### Credentials sau xác thực có thể rỗng nhưng danh tính vẫn hợp lệ

`ProviderManager` mặc định gọi `eraseCredentials()` trên kết quả hỗ trợ `CredentialsContainer` để giảm thời gian tồn tại của bí mật. Phần xóa có thể tác động tới cả `principal`/`details` nếu các đối tượng này cũng triển khai `CredentialsContainer`. Với custom `UserDetails` hoặc cache tham chiếu chung, cần tránh để thao tác xóa vô tình phá dữ liệu dùng để xác thực lần sau.

Không tắt `eraseCredentialsAfterAuthentication` chỉ để tiện debug; thiết kế principal/cache và pipeline thích hợp.

### Không phải mọi cơ chế đều tạo UsernamePasswordAuthenticationToken

Form/password login có thể trả loại token này, nhưng JWT Bearer, OAuth2/OIDC, passkey, remember-me hay X.509 có thể dùng các implementation Authentication khác. Phần quan trọng của **mô hình danh tính** là hợp đồng `Authentication`, `SecurityContext` và ranh giới tin cậy, không phải ép mọi request vào một class.

## 8. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm hoặc sai? | Cách làm đúng |
| --- | --- | --- |
| Tạo token ba tham số trực tiếp từ username và role do client gửi | Lập tức có `isAuthenticated() = true` mà chưa kiểm tra password | Dùng `unauthenticated(...)` rồi `AuthenticationManager.authenticate(...)` |
| Gọi `setAuthenticated(true)` để “đánh dấu đã đăng nhập” | `UsernamePasswordAuthenticationToken` từ chối bằng ngoại lệ; tư duy sai ranh giới tin cậy | Để provider tạo trusted result sau khi xác thực |
| Truyền password hash từ database vào `credentials` của request | Provider thông thường kỳ vọng raw password để `PasswordEncoder.matches`; sai semantics | Nhận raw password từ form qua HTTPS; provider so khớp với stored hash phía server |
| Nghĩ token đã xác thực phải luôn chứa raw password | Giữ bí mật lâu hơn cần thiết, rủi ro lộ log/heap/session | Chấp nhận credential erasure mặc định |
| Dùng token request chưa xác thực làm `SecurityContext` của user | Có thể khiến code khác xử lý sai trạng thái tin cậy | Chỉ lưu authenticated result hợp lệ |
| Gọi manager rồi bỏ qua giá trị trả về | Request token ban đầu vẫn chưa xác thực, hoặc không có quyền | Dùng đúng `Authentication result` trả về |
| Gọi `authenticate(...)` trong controller và nghĩ có session tự động | Thiếu persist context, session strategy hoặc success handlers | Dùng cơ chế login chuẩn hoặc triển khai đủ vòng đời web |
| Lấy `authorities` từ body của client | Client có thể tự cấp `ROLE_ADMIN` | Lấy authorities từ `UserDetailsService`/provider hoặc nguồn tin cậy |
| Ép mọi `principal` về `String` | Sau login thường là `UserDetails` | Dùng `getName()` hoặc kiểm tra instance |
| Bắt mọi lỗi thành “wrong password” | Che giấu sự cố provider, cấu hình hoặc trạng thái account | Xử lý `AuthenticationException` theo loại, thông điệp trả client vẫn an toàn |
| Dùng `setAuthenticated(false)` thay logout | Không thu hồi session, cookie hay token khác | Theo quy trình logout, clear context và invalidate session nếu có |
| Log cả đối tượng token/request/password | Có thể rò credential và dữ liệu cá nhân | Log sự kiện tối thiểu, không log credential |

## 9. Ba tình huống kiểm tra hiểu biết

**Tình huống A.** Client POST `{"username":"lan","password":"wrong-password","roles":["ADMIN"]}`. Server tạo `UsernamePasswordAuthenticationToken.unauthenticated("lan", "wrong-password")` và gọi manager. Kết quả là gì?

**Giải thích:** Provider so khớp password với stored hash và thất bại; không được trả trusted Authentication chỉ vì client đã gắn role. Role trong body không phải nguồn phân quyền đáng tin. Không được lưu token request vào `SecurityContext` như user đã login.

**Tình huống B.** `manager.authenticate(request)` trả về token có `isAuthenticated() = true`, `getPrincipal()` là một `UserDetails` và `getCredentials() == null`. Có phải thiếu password nên login thất bại?

**Giải thích:** Không. Password có thể đã được xác minh và credentials được xóa theo chính sách bảo mật. Dùng authorities của kết quả để phân quyền và quản lý context theo cơ chế web.

**Tình huống C.** Developer viết `new UsernamePasswordAuthenticationToken(username, password, List.of())` và nghĩ “danh sách quyền rỗng nên chắc chắn chưa xác thực”. Kết luận đúng không?

**Giải thích:** Sai. Constructor **ba** tham số tạo token trusted với `isAuthenticated() = true` bất kể list có rỗng hay không. Phải dùng constructor **hai** tham số hoặc factory `unauthenticated(...)` để gửi yêu cầu đến manager.

## 10. Checklist khi đọc hoặc viết mã đăng nhập

1. **Đầu vào từ client** chỉ có username/credential cần thiết; token request phải là **unauthenticated**.
2. **AuthenticationManager/Provider** thực sự kiểm tra credential và trạng thái tài khoản với nguồn dữ liệu đáng tin.
3. **Kết quả trả về** có principal đã xác minh, authorities từ hệ thống và `isAuthenticated() = true` khi thành công.
4. **Credential cleanup** giữ bí mật ngắn hạn; tránh ghi log và hiểu ảnh hưởng của `CredentialsContainer` tới cache.
5. **SecurityContext/session** chỉ được thiết lập và lưu đúng sau khi xác thực, với đầy đủ xử lý session/CSRF khi cần.
6. **Authorization** tiếp tục kiểm tra chính sách quyền trên từng request; kết quả xác thực không cấp quyền tự động.
7. **Lỗi xác thực** không được biến request token thành trusted result hoặc lộ thông tin tài khoản.

## 11. Tham khảo chính thức

- [UsernamePasswordAuthenticationToken – Javadoc Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): constructor hai/ba tham số, static factory, `isAuthenticated()` và credential erasure.
- [Authentication Architecture – Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `AuthenticationManager`, `ProviderManager`.
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService` và `PasswordEncoder` trong luồng username/password.
- [ProviderManager – Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider, ngoại lệ và `eraseCredentialsAfterAuthentication`.
- [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): lưu `SecurityContext` và vòng đời session.

**Ghi nhớ:** **Token chưa xác thực** mô tả *bằng chứng cần kiểm tra*. **Token đã xác thực** mô tả *danh tính được tin sau khi kiểm tra*. Việc chuyển giữa hai trạng thái phải đi qua ranh giới tin cậy của `AuthenticationManager`/`AuthenticationProvider`, rồi mới tới `SecurityContext` và bước phân quyền.
