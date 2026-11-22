# Principal, credentials và GrantedAuthority trong Authentication

Trong Spring Security, **`Authentication`** đại diện cho thông tin dùng trong một yêu cầu xác thực hoặc kết quả của quá trình xác thực. Bên trong đối tượng này có ba nhóm dữ liệu quan trọng: **`principal`** (chủ thể đang được nhận diện), **`credentials`** (bằng chứng chứng minh danh tính) và **`authorities`** (những quyền hoặc nhãn quyền đã được cấp cho chủ thể). Hiểu đúng mối quan hệ của chúng giúp đọc cấu hình, debug lỗi 401/403 và tránh những sai lầm như coi username là quyền truy cập hoặc ghi log mật khẩu.

Tư duy chính:

- **Principal:** “Ai đang yêu cầu truy cập?”
- **Credentials:** “Có bằng chứng nào để kiểm tra người yêu cầu thực sự là ai?”
- **GrantedAuthority:** “Hệ thống đã cấp những role, scope hoặc permission nào cho chủ thể đó?”
- **Authorization:** “Với các quyền và ngữ cảnh hiện có, chủ thể có được thực hiện hành động này trên tài nguyên cụ thể hay không?”

Bài này sử dụng kiến trúc **Spring Security Servlet / Spring MVC**, ví dụ Spring Boot 3, Spring Security 6 và Java 17+. Các cơ chế như HTTP Basic, form login, JWT và OIDC có thể tạo những kiểu `Authentication` khác nhau nhưng vẫn áp dụng các nguyên tắc trên.

## 1. Authentication nằm ở đâu trong kiến trúc Spring Security?

Ứng dụng Servlet thường đi qua `SecurityFilterChain`. Một security filter lấy thông tin xác thực từ HTTP request, đưa tới `AuthenticationManager`/`AuthenticationProvider` khi cần, nhận một `Authentication` đã được xác minh rồi lưu vào `SecurityContext` theo cơ chế thích hợp. Sau đó các rule authorization sử dụng thông tin đó để quyết định quyền truy cập.

```text
HTTP request
    |
    | Authorization header / login form / session / ...
    v
SecurityFilterChain
    |
    +-- Tạo Authentication yêu cầu xác thực:
    |      principal   = danh tính đang được khai báo
    |      credentials = bằng chứng client đưa ra
    |      authorities = chưa được coi là quyền đã cấp
    |
    v
AuthenticationManager
    |
    v
AuthenticationProvider
    |-- Kiểm tra bằng chứng, trạng thái tài khoản, nguồn tin cậy
    |-- Nạp/ánh xạ GrantedAuthority
    |
    +-- Thất bại -> phản hồi xác thực thất bại
    |
    +-- Thành công -> Authentication đáng tin cậy
                           |
                           v
                      SecurityContext
                           |
                           v
                    Authorization rules
                           |
                           v
                     Controller/Service
```

Đây là mô hình logic: trình tự filter và cách lưu ngữ cảnh khác nhau theo cơ chế. Với session login, context có thể được khôi phục từ phiên; với bearer token, token có thể được kiểm tra lại trên từng request. Một request được cho phép công khai có thể không cần có người dùng đã đăng nhập.

### 1.1. Một interface, hai thời điểm khác nhau

Spring Security có thể dùng `Authentication` làm:

1. **Đầu vào cho AuthenticationManager:** mang danh tính và credentials chưa được xác minh, thường có `isAuthenticated() == false`.
2. **Kết quả xác thực:** mang principal và authorities đã được tạo từ nguồn tin cậy, được dùng trong SecurityContext.

Đây là khác biệt về **mức độ tin cậy**, không chỉ là khác biệt kiểu dữ liệu. Việc client gửi username, password hay danh sách role không có nghĩa những giá trị đó đã được chứng thực.

### 1.2. Các API cần nhớ

| API | Chức năng | Lưu ý |
| --- | --- | --- |
| `getPrincipal()` | Trả đối tượng mô tả danh tính | Kiểu tùy cơ chế: `String`, `UserDetails`, `Jwt`, `OAuth2User`... |
| `getCredentials()` | Trả bằng chứng liên quan việc xác thực | Có thể là password/token; có thể đã bị xóa sau xác thực |
| `getAuthorities()` | Trả `Collection<? extends GrantedAuthority>` | Chỉ chứa quyền đã gắn với Authentication, chưa tự giải quyết ownership |
| `getName()` | Trả tên dạng chuỗi của principal | Không bắt buộc là khóa định danh bất biến trong database |
| `getDetails()` | Thông tin bổ sung gắn với authentication/request | Không phải principal hoặc tập quyền |
| `isAuthenticated()` | Trạng thái của token authentication | Không được thay thế toàn bộ chính sách authn/authz |
| `setAuthenticated(boolean)` | API thay đổi trạng thái ở implementation cho phép | Không tự đánh dấu thành công từ input chưa được kiểm tra |

`Authentication` mở rộng `java.security.Principal`. Các implementation cụ thể có thể xử lý quyền, trạng thái và kiểu dữ liệu khác nhau; không suy ra mọi Authentication đều là username/password.

## 2. Principal: chủ thể đã được nhận diện

### 2.1. Principal không nhất thiết là username

`principal` có thể là người dùng, client, service account hoặc định danh tương đương. Trong luồng username/password phổ biến, principal sau khi xác thực thường là một đối tượng `UserDetails`.

| Cơ chế | Principal thường gặp | Đặc điểm |
| --- | --- | --- |
| Username/password với `DaoAuthenticationProvider` | `UserDetails` | Có username và dữ liệu cần thiết để xác thực |
| HTTP Basic với `UserDetailsService` | `UserDetails` sau login | Basic là cách truyền credentials, không quyết định kiểu principal duy nhất |
| JWT resource server | `Jwt` trong `JwtAuthenticationToken` | Có claims; tên có thể ánh xạ từ `sub` |
| OAuth2/OIDC login | `OAuth2User` / `OidcUser` | Có thuộc tính danh tính từ nhà cung cấp |
| Custom authentication | Identity/domain object của ứng dụng | Do provider/converter đáng tin cậy tạo |
| Anonymous authentication | Dạng đại diện anonymous | Không phải tài khoản đăng nhập thực sự |

Ví dụ:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    Object principal = authentication.getPrincipal();
}
```

Đoạn này minh họa trong ứng dụng Spring Security, cần imports từ Spring Security; không phải chương trình Java độc lập. Trong code phục vụ request public, `authentication` có thể null hoặc đại diện anonymous nên cần xử lý đúng ngữ cảnh.

### 2.2. UserDetails là một kiểu principal phổ biến, không phải kiểu duy nhất

`UserDetails` là interface phổ biến trong xác thực username/password; nó có username, password hash, authorities và các thuộc tính trạng thái tài khoản. Nhưng `Authentication.getPrincipal()` trả `Object`, do đó cast cứng thế này có thể sai:

```java
// Chỉ hợp lệ nếu đã bảo đảm principal thực sự là UserDetails.
UserDetails user = (UserDetails) authentication.getPrincipal();
```

Khi ứng dụng chuyển sang JWT, OIDC hoặc custom authentication, principal có thể là `Jwt` hoặc `OAuth2User`. Hãy dùng `getName()` cho nhu cầu tên đơn giản hoặc thiết kế một adapter thống nhất để lấy **subject ID ổn định** theo cơ chế đã xác minh.

### 2.3. Principal và định danh nghiệp vụ

Một username có thể được đổi tên; email có thể thay đổi; `getName()` có thể bị custom mapper định nghĩa khác. Nếu database dùng `user_id` bất biến, không nên dựa vào username làm khóa sở hữu đơn hàng mà không có ánh xạ xác minh.

Ví dụ muốn đọc `GET /api/orders/100`, service cần xác định **người gọi thật**, tenant và quan hệ với Order 100 từ thông tin đáng tin cậy. Header `X-User-Id: alice` hay body `{"userId":"alice"}` do client gửi không tự được coi là principal đã xác thực.

### 2.4. Lấy principal trong controller

Spring Security cung cấp annotation để đọc Authentication từ context:

```java
@GetMapping("/api/me")
public String me(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication
) {
    return authentication.getName();
}
```

Nếu đã biết cơ chế xác thực tạo `UserDetails`, có thể lấy trực tiếp:

```java
@GetMapping("/api/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

Hai đoạn trên là fragment của Spring controller và cần imports phù hợp. Nếu endpoint cho phép anonymous hoặc cơ chế principal khác, phải bảo vệ đúng kiểu/null và không giả định mọi request có `UserDetails`.

## 3. Credentials: bằng chứng chứng minh danh tính

### 3.1. Credentials có thể là gì?

- Password người dùng nhập trong form login hoặc HTTP Basic.
- Bearer token trong HTTP header `Authorization`.
- Thông tin chứng thực từ certificate hoặc cơ chế xác thực khác.
- Một đối tượng credentials custom mà AuthenticationProvider của ứng dụng hiểu.

Principal trả lời “ai đang được khai báo?”, còn credentials là thứ được **kiểm tra** để tin rằng request đại diện cho danh tính đó. Chỉ biết username hoặc email không đủ để xác minh quyền sở hữu danh tính.

### 3.2. Password plaintext khác password hash

Trong cơ chế username/password phổ biến:

1. Request gửi username và raw password thông qua kênh truyền bảo mật (HTTPS).
2. `UserDetailsService` tìm người dùng tương ứng theo username.
3. `PasswordEncoder.matches(raw, encoded)` kiểm tra raw password với hash đã lưu.
4. Provider kiểm tra các điều kiện cần thiết và tạo Authentication kết quả.
5. Credentials nhạy cảm có thể được xóa khỏi kết quả sau khi xác thực.

Ví dụ:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("demo-password");
boolean matches = encoder.matches("demo-password", storedHash);
```

Đây là đoạn code sử dụng thư viện Spring Security, không biên dịch riêng bằng `javac` nếu không có dependencies/imports. Vì BCrypt có salt, không so sánh `encoder.encode(password).equals(storedHash)`: hai lần hash cùng password thường cho chuỗi khác nhau. Không lưu plaintext và không hardcode password thật.

**Password hash cũng nhạy cảm.** Một `UserDetails` có thể mang hash trong trường password; không ghi nó vào log hoặc đưa vào JSON response.

### 3.3. Credentials thường được xóa sau xác thực

`ProviderManager` có cơ chế xóa credentials khỏi Authentication kết quả khi thích hợp; một số kiểu principal/details hỗ trợ `CredentialsContainer` và `eraseCredentials()`.

Hệ quả:

- `authentication.getCredentials() == null` **không đồng nghĩa** user chưa đăng nhập.
- Không dựa vào `getCredentials()` để lấy lại password trong logic nghiệp vụ.
- Không đảm bảo mọi provider đều trả null: một số cơ chế token/custom có cách lưu credentials khác.
- Việc xóa credentials sau xác thực không biện minh cho ghi log chúng trước đó.
- Cần xem xét đối tượng được cache: nếu nhiều nơi dùng chung `UserDetails`, xóa credentials trên một đối tượng có thể ảnh hưởng bản cache.

Mục tiêu là **giảm thời gian bí mật tồn tại trong bộ nhớ và tránh bị rò rỉ**, không phải thay thế TLS, quản lý secret hoặc chính sách phiên.

### 3.4. Credentials có mặt chưa có nghĩa đã được xác thực

Ví dụ tạo token đầu vào trong Spring Security:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-request"
    );

Authentication result = authenticationManager.authenticate(request);
```

`request` chưa phải kết quả tin cậy; provider phải kiểm tra password và tài khoản. Đoạn code này là fragment trong ứng dụng Spring, không phải một servlet login hoàn chỉnh. Nếu tự viết login flow, phải thiết lập, lưu/khôi phục SecurityContext và áp dụng bảo vệ cần thiết cho đúng cơ chế.

### 3.5. HTTP Basic chỉ là cách chuyển credentials

Header `Authorization: Basic ...` chứa username/password được Base64 encode. Base64 **không phải mã hóa bảo mật**, vì vậy các kết nối thực tế phải dùng HTTPS. HTTP Basic có thể gửi credentials lặp lại trên các request; không được ghi nguyên header vào log hoặc dùng password thật trong tài liệu demo.

## 4. GrantedAuthority: role, scope, permission đã được cấp

### 4.1. GrantedAuthority biểu diễn điều gì?

`GrantedAuthority` là interface có phương thức chính `String getAuthority()`. `SimpleGrantedAuthority` là implementation phổ biến, dùng một chuỗi để thể hiện quyền, ví dụ:

```text
ROLE_USER
ROLE_ADMIN
report:read
invoice:approve
SCOPE_orders.read
```

Trong `Authentication`, `getAuthorities()` trả một `Collection<? extends GrantedAuthority>`. Những quyền này có thể được nạp qua `UserDetailsService`, provider, hoặc ánh xạ token **đã được xác minh**. Không lấy mảng `roles` do client tự gửi trong body rồi gán trực tiếp thành authorities.

### 4.2. Role khác authority cụ thể như thế nào?

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Role | `ROLE_ADMIN` | Nhóm trách nhiệm theo quy ước phân vai |
| Permission/authority | `report:read` | Quyền hành động cụ thể trong ứng dụng |
| OAuth2 scope mapping | `SCOPE_orders.read` | Quyền được converter ánh xạ từ scope của access token |
| Authority custom | `tenant:shop-a:auditor` | Quy ước quyền do ứng dụng định nghĩa, cần nguồn đáng tin cậy |

Trong cấu hình mặc định:

- `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` kiểm tra đúng chuỗi `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` kiểm tra `ADMIN`; nó không tự thêm `ROLE_`.
- `hasAuthority("report:read")` kiểm tra chính xác quyền `report:read`.
- Khi resource server JWT ánh xạ scope theo converter mặc định, scope `orders.read` thường thành `SCOPE_orders.read`.

Tiền tố role có thể tùy chỉnh, vì vậy phải nhất quán giữa dữ liệu, converter và cấu hình authorization. Không nhầm tham số của `hasRole` với chuỗi đã chứa sẵn `ROLE_`.

### 4.3. Authority được cấp cho principal khác với quyền trên từng object

Alice và Bob đều có `ROLE_USER` và `order:read`. Cả hai có thể được vào chức năng đọc đơn, nhưng Alice không được tự động xem đơn của Bob. Một quyết định truy cập phải xét thêm:

```text
authenticated
AND authority("order:read")
AND sameTenant(principal, order)
AND (isOwner(principal, order)
     OR authority("order:read:any"))
AND businessStateAllowsRead(order)
```

Điều kiện tenant, owner và trạng thái thực tế cần dữ liệu từ server. Với hàng nghìn bản ghi, gắn một authority riêng cho mỗi object thường khiến dữ liệu lớn, khó cập nhật và khó thu hồi. Nên dùng authorities cho quyền chung và domain policy cho quyền trên resource cụ thể.

### 4.4. Complex GrantedAuthority

Không phải mọi kiểu authority đều biểu diễn chính xác bằng một chuỗi. Tài liệu Spring Security cho phép một `GrantedAuthority` phức tạp trả `null` từ `getAuthority()` nếu không thể biểu diễn quyền bằng String. Khi đó authorization component phải thực sự hiểu kiểu custom ấy. Với phần lớn ứng dụng, `SimpleGrantedAuthority` và chuỗi quyền rõ ràng là đủ.

### 4.5. Authenticated nhưng không có ROLE_ADMIN

Một `Authentication` đã xác thực hợp lệ vẫn có thể thiếu `ROLE_ADMIN`, `invoice:approve` hoặc scope tương ứng. Do đó:

- **Authentication** xác định danh tính/bằng chứng.
- **GrantedAuthority** mô tả những quyền đã được cấp.
- **AuthorizationManager**, request matcher hoặc method security xác định rule.
- **Domain policy** quyết định thêm trên object/tenant/trạng thái.

User login thành công rồi gọi API admin có thể nhận **403 Forbidden**. User không cung cấp hoặc gửi sai credentials qua HTTP Basic thường nhận **401 Unauthorized**. Form login có thể redirect; CSRF sai cũng có thể dẫn tới 403, nên không thể suy luận thiếu role chỉ từ status code.

## 5. Vòng đời của Authentication: trước và sau xác thực

| Thuộc tính | Trước khi provider chấp nhận | Sau xác thực thành công |
| --- | --- | --- |
| `principal` | Username/danh tính do client khai | Principal đã được xác minh, thường là `UserDetails` trong username/password |
| `credentials` | Password/token đang chờ kiểm tra | Có thể bị xóa hoặc xử lý theo cơ chế |
| `authorities` | Chưa có quyền đáng tin cậy | Role, permission, scope đã được cấp/ánh xạ hợp lệ |
| `authenticated` | Thường là `false` | Thường là `true` |
| `details` | Có thể có thông tin request phụ | Tùy cơ chế, không phải quyền |

Khi xác thực thất bại, không có Authentication kết quả hợp lệ để gắn vào security context như user đã đăng nhập. Việc tự tạo một token có `authenticated=true` từ JSON body hoặc header không thay thế xác minh danh tính.

### 5.1. SecurityContext và SecurityContextHolder

`SecurityContext` chứa Authentication của ngữ cảnh đang xử lý. `SecurityContextHolder` là nơi truy cập context, thường dùng chiến lược theo thread trong Servlet truyền thống. Các thread nền, CompletableFuture hoặc scheduled job không tự nhiên được mang theo identity/permission từ một HTTP request; nếu cần, phải thiết kế cách truyền context hoặc service identity đúng chính sách.

Không viết code giả định `SecurityContextHolder.getContext().getAuthentication()` luôn khác null ở mọi endpoint và mọi thread.

### 5.2. AnonymousAuthenticationToken là trường hợp dễ gây nhầm

Một `AnonymousAuthenticationToken` có thể có `isAuthenticated()==true` về mặt đối tượng. Vì thế biểu thức `authentication != null && authentication.isAuthenticated()` **không phải** cách đầy đủ để xác định user đã login thật.

Khi khai báo policy, ưu tiên `.authenticated()`, `.fullyAuthenticated()` hoặc các cơ chế kiểm tra được Spring Security hỗ trợ. Những rule đó có ngữ nghĩa phân biệt anonymous/remember-me khi phù hợp.

### 5.3. Authorities có thể cũ sau khi role bị đổi

Với phiên đăng nhập hoặc token sống lâu, authorities có thể phản ánh trạng thái tại thời điểm context/token được tạo. Nếu role bị thu hồi, token/phiên đang hoạt động **không mặc nhiên tự cập nhật ngay lập tức**. Hệ thống cần chính sách refresh/revocation, thời hạn token và quyền kiểm tra runtime phù hợp với nghiệp vụ.

## 6. Ví dụ Spring Boot 3 hoàn chỉnh: trả danh tính và authority an toàn

Ví dụ sử dụng **Spring MVC + Spring Security 6**, Java 17+, hai tài khoản demo và HTTP Basic:

- Alice có `ROLE_USER` và `report:read`;
- Admin có `ROLE_USER`, `ROLE_ADMIN` và `report:read`;
- `GET /api/me` trả tên, kiểu principal và danh sách authority, **không trả credentials**;
- `GET /api/reports` cần `report:read`;
- `GET /api/admin` cần role `ADMIN`.

Trong dự án Spring Boot 3 với Gradle plugin và dependency management đã cấu hình, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/authparts/AuthenticationPartsApplication.java`:

```java
package example.authparts;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthenticationPartsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationPartsApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_USER", "ROLE_ADMIN", "report:read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class AuthenticationPartsController {
    record IdentityView(
        String name,
        String principalType,
        boolean authenticated,
        List<String> authorities
    ) {}

    @GetMapping("/api/me")
    IdentityView me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication
    ) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new IdentityView(
            authentication.getName(),
            authentication.getPrincipal().getClass().getSimpleName(),
            authentication.isAuthenticated(),
            authorities
        );
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("message", "report available");
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin allowed");
    }
}
```

Lưu ý:

1. `UserDetailsService` cung cấp user cho cơ chế xác thực username/password. `PasswordEncoder` băm password demo bằng BCrypt.
2. Spring Security kiểm tra credentials; controller không so sánh password và không lấy tên từ header tự khai.
3. Alice có quyền đọc báo cáo nhưng không có role quản trị.
4. `@CurrentSecurityContext` lấy Authentication hiện tại trong Spring Security.
5. Controller không truy cập `getCredentials()` và không serialize nguyên `Authentication`. API thực tế còn cần hạn chế trường được phép hiển thị.
6. Đây là **một tệp Java dùng trong dự án Spring Boot**. Cần Spring Boot Gradle/Maven setup và dependencies; không dùng `javac` thuần nếu thiếu Spring jars. Demo chỉ nên chạy cục bộ; HTTP Basic production cần HTTPS và secret handling thích hợp.

Chạy từ root dự án:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`.

### 6.1. Kiểm tra bằng curl

```bash
# Chưa đăng nhập
curl -i http://localhost:8080/api/me

# Alice đã xác thực
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me

# Có quyền report:read
curl -i -u alice:demo-alice-pass http://localhost:8080/api/reports

# Thiếu ROLE_ADMIN
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin có ROLE_ADMIN
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin

# Sai password
curl -i -u alice:wrong-pass http://localhost:8080/api/me
```

Các kết quả dự kiến theo cấu hình ví dụ:

| Request | HTTP status | Lý do |
| --- | --- | --- |
| Anonymous `GET /api/me` | 401 | HTTP Basic yêu cầu xác thực |
| Alice `GET /api/me` | 200 | Danh tính hợp lệ |
| Alice `GET /api/reports` | 200 | Có `report:read` |
| Alice `GET /api/admin` | 403 | Thiếu `ROLE_ADMIN` |
| Admin `GET /api/admin` | 200 | Có `ROLE_ADMIN` |
| Alice dùng password sai `GET /api/me` | 401 | Credentials bị từ chối |

Response JSON mẫu cho Alice:

```json
{
  "name": "alice",
  "principalType": "User",
  "authenticated": true,
  "authorities": ["ROLE_USER", "report:read"]
}
```

Danh sách authorities được sort trước khi xuất. Thứ tự các trường JSON có thể khác tùy serializer; tên kiểu principal `User` phản ánh `UserDetails` tích hợp trong ví dụ này, **không đảm bảo cho mọi cơ chế**. Không có plaintext password, hash hoặc bearer token trong response.

`curl -u` với password demo tiện để kiểm tra cục bộ; với secret thực, cần chú ý lịch sử shell, process list, chính sách TLS và quản lý thông tin xác thực.

## 7. Đưa GrantedAuthority vào quyết định truy cập

Trong service, có thể đọc authority từ context:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

boolean canReadReport = auth != null
    && auth.getAuthorities().stream()
        .anyMatch(a -> "report:read".equals(a.getAuthority()));
```

Đây là fragment minh họa; với endpoint public/anonymous cần policy đúng thay vì chỉ kiểm tra non-null. Nhiều ứng dụng nên dùng `@PreAuthorize`, `AuthorizationManager` hoặc policy service thống nhất để tránh lặp logic.

Ví dụ method security:

```java
@PreAuthorize("hasRole('ADMIN')")
public void createAdminReport() {
    // Business operation
}

@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long id) {
    return reportPolicy.loadAuthorizedReport(id);
}
```

Các đoạn trên cần service/method thực và `@EnableMethodSecurity`; không phải tệp Java hoàn chỉnh. `hasRole('ADMIN')` mặc định yêu cầu `ROLE_ADMIN`; `hasAuthority('report:read')` tìm đúng chuỗi.

Ngay cả khi method trả qua được bước authority, `reportPolicy` vẫn phải kiểm tra object ID, tenant, owner và trạng thái. **Authentication chứa quyền khái quát, nhưng không tự quyết định mọi quyền trên từng tài nguyên.**

### 7.1. Không tạo Authentication đã được tin cậy từ dữ liệu chưa kiểm tra

Mẫu nguy hiểm:

```java
// Anti-pattern: request roles chưa được xác minh.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        request.username(),
        null,
        request.roles().stream()
            .map(SimpleGrantedAuthority::new)
            .toList()
    );
```

Đoạn này chỉ cho thấy có thể tạo một object có cờ authenticated mà không hề kiểm tra password hay quyền thật. Việc dùng factory method không biến dữ liệu của client thành dữ liệu đáng tin cậy. Chỉ component được thiết kế để xác thực/ánh xạ từ nguồn đáng tin mới được thiết lập principal và authorities tương ứng.

### 7.2. Các quyền khác nhau cho các nguồn khác nhau

- Username/password: authorities thường từ `UserDetailsService` hoặc provider.
- JWT: claims phải được xác minh trước khi ánh xạ ra authorities, đặc biệt issuer, audience, signature, expiry.
- OAuth2 scope: converter xác định quy ước `SCOPE_` và scope nào là hợp lệ.
- Service account: permissions phải đúng phạm vi service, không tự kế thừa quyền admin của người dùng cuối.

Thiết kế cần thống nhất định danh và authority dù có nhiều cơ chế xác thực trong cùng ứng dụng. Một chuỗi `ROLE_ADMIN` tự xuất hiện từ token chưa xác minh không mang giá trị bảo mật.

## 8. Java 17 độc lập: hiểu ba thành phần qua quyết định quyền

Bài tập sau **mô phỏng** principal, credentials và authority bằng Java thuần, không cần Spring. Nó cho thấy có username/password trong object chưa đủ, và user đã xác thực vẫn thiếu quyền nếu không có authority tương ứng.

Tạo tệp `AuthenticationModelDemo.java`:

```java
import java.util.Set;

public class AuthenticationModelDemo {

    record Identity(String id, String name) {}

    record AuthState(
        Identity principal,
        String credentials,
        Set<String> authorities,
        boolean authenticated
    ) {}

    static boolean canReadReport(AuthState state) {
        return state != null
            && state.authenticated()
            && state.principal() != null
            && state.authorities() != null
            && state.authorities().contains("report:read");
    }

    public static void main(String[] args) {
        Identity alice = new Identity("u-100", "alice");

        AuthState incoming = new AuthState(
            alice, "demo-password", Set.of(), false
        );
        AuthState verified = new AuthState(
            alice, null,
            Set.of("ROLE_USER", "report:read"),
            true
        );
        AuthState withoutPermission = new AuthState(
            alice, null,
            Set.of("ROLE_USER"),
            true
        );

        System.out.println("Before authentication: "
            + canReadReport(incoming));
        System.out.println("Verified with authority: "
            + canReadReport(verified));
        System.out.println("Verified without authority: "
            + canReadReport(withoutPermission));
        System.out.println("Credentials cleared: "
            + (verified.credentials() == null));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac AuthenticationModelDemo.java
java AuthenticationModelDemo
```

**Stdout chính xác:**

```text
Before authentication: false
Verified with authority: true
Verified without authority: false
Credentials cleared: true
```

Giải thích:

- `incoming` có principal và password nhưng cờ authenticated chưa thành công, không có quyền đáng tin cậy.
- `verified` có principal và authority `report:read` nên logic mô phỏng cho phép đọc.
- `withoutPermission` cũng đã authenticated nhưng vẫn không qua được kiểm tra `report:read`.
- `credentials` có thể null sau xác thực mà principal và authorities vẫn tồn tại.

**Giới hạn:** `AuthState` chỉ là record để học; bất kỳ code nào cũng có thể tạo `authenticated=true`. Nó không verify password/token, không tạo SecurityContext và **không được dùng làm authentication production**. Trong Spring Security, provider đáng tin cậy mới xác lập Authentication kết quả.

## 9. Những lỗi phổ biến

### 9.1. Đọc isAuthenticated như quy tắc phân quyền duy nhất

`isAuthenticated()` là trạng thái của token; anonymous token có thể mang cờ true. Với endpoint yêu cầu login thật, dùng `authenticated()`, còn endpoint nhạy cảm cần thêm authority và policy trên object.

### 9.2. Nhầm UserDetails với mọi loại principal

Cứng nhắc cast `(UserDetails) authentication.getPrincipal()` sẽ lỗi khi principal là `Jwt` hoặc kiểu custom. Hãy chọn abstraction phù hợp hoặc branch theo cơ chế một cách có kiểm soát.

### 9.3. Ghi log hoặc serialize credentials

Không log raw password, access token, refresh token, Authorization header hay password hash. Chỉ trả các trường an toàn trong DTO. Ngay cả thông tin `getDetails()` cũng cần cân nhắc trước khi đưa ra ngoài.

### 9.4. So sánh role sai tiền tố

Với quy ước mặc định, `hasRole("ADMIN")` tìm `ROLE_ADMIN`. `hasAuthority("ADMIN")` và `hasAuthority("ROLE_ADMIN")` là hai chuỗi khác nhau. Chọn quy ước nhất quán và kiểm thử với user có/không có quyền.

### 9.5. Tin role do client khai

Client có thể tự gửi `roles: ["ROLE_ADMIN"]` hoặc thay JWT chưa được verify. Không dùng chúng để tạo authority; phải kiểm tra nguồn và ánh xạ permission từ dữ liệu đáng tin.

### 9.6. Coi authority là quyền đọc mọi bản ghi

`order:read` không chứng minh user sở hữu order. Cần quyền trên tài nguyên, tenant, owner và các điều kiện nghiệp vụ cụ thể.

### 9.7. Dùng credentials null để suy ra logout

Sau xác thực, credentials có thể được xóa. Quyền truy cập được xác định bởi security context và policy phù hợp, không phải sự hiện diện của password trong memory.

### 9.8. Quên cập nhật authority khi role đổi

Session hoặc token đã phát hành có thể giữ authorities cũ. Cần thiết kế cơ chế thu hồi, thời hạn, refresh và policy kiểm tra runtime theo mức rủi ro.

### 9.9. Lẫn PasswordEncoder với toàn bộ xác thực

`PasswordEncoder` chỉ giúp so sánh password và hash. Nó không tự kiểm tra quyền, owner, account status, MFA hoặc giới hạn brute-force. Các trách nhiệm đó nằm ở provider và các lớp bảo vệ khác.

## 10. Checklist kiểm thử và debug

| Tình huống | Principal | Credentials | Authorities | Kết quả cần thấy |
| --- | --- | --- | --- | --- |
| Đăng nhập đúng | Được xác minh | Hợp lệ | `ROLE_USER` và `report:read` | API private thích hợp chạy |
| Password sai | Không có identity hợp lệ | Sai | Không cấp quyền | HTTP Basic thường 401 |
| Đăng nhập nhưng thiếu admin | Identity hợp lệ | Đã kiểm tra | Không `ROLE_ADMIN` | API admin từ chối, thường 403 |
| User có admin role | Identity hợp lệ | Đã kiểm tra | Có `ROLE_ADMIN` | API admin cho phép |
| Anonymous | Null/anonymous | Không có | Không có quyền nghiệp vụ | Endpoint private từ chối |
| JWT hợp lệ, thiếu scope | Identity từ token đã verify | Token hợp lệ | Thiếu scope yêu cầu | Endpoint theo scope từ chối |
| User đọc order của user khác | Identity hợp lệ | Hợp lệ | Có quyền đọc chung | Object-level policy từ chối |
| Role thay đổi khi session còn sống | Identity cũ có thể còn hợp lệ | Tùy cơ chế | Có thể chưa được cập nhật | Kiểm thử chính sách thu hồi |

Khi gặp HTTP 401/403, lần lượt kiểm tra:

1. Request đi qua đúng `SecurityFilterChain` nào và cơ chế xác thực nào?
2. Principal được thiết lập bởi nguồn nào? Có phải anonymous không?
3. Credentials được provider xác minh ra sao? **Không log giá trị bí mật**.
4. `authentication.getAuthorities()` chứa chính xác chuỗi nào?
5. Rule yêu cầu `hasRole`, `hasAuthority`, `authenticated`, scope hay điều kiện khác?
6. Quyền trên object/owner/tenant có được kiểm tra ở service không?
7. Session/token có giữ authority cũ không?
8. Request POST có bị lớp CSRF từ chối không?

Một response 403 có thể do thiếu role, sai quyền object hoặc CSRF; không kết luận tất cả 403 đều do thiếu GrantedAuthority. Test tốt cần cả đường cho phép lẫn từ chối, và với thao tác thay đổi trạng thái phải kiểm tra không có side effect trái phép.

## 11. Câu hỏi tự kiểm tra

**1.** Username và password đã có trong một Authentication chưa được xác thực. Vì sao không thể tin principal hoặc authorities lúc đó?

**2.** Sau login, `getCredentials()` trả null. Điều đó có đồng nghĩa logout không?

**3.** Alice có `ROLE_USER` và `report:read`. Vì sao Alice không qua `hasRole("ADMIN")`?

**4.** `getPrincipal()`, `getName()` và `getDetails()` khác nhau ra sao?

**5.** Vì sao `hasAuthority("ADMIN")` không hoàn toàn giống `hasRole("ADMIN")`?

**6.** Nếu có `order:read`, người gọi có được đọc mọi Order không?

**7.** Vì sao cast principal thành `UserDetails` có thể sai trong JWT/OIDC?

**8.** Nếu một user bị thu hồi `ROLE_ADMIN`, có nên giả định session đang mở tự cập nhật tức thì không?

**Đáp án gợi ý:**

1. Dữ liệu đang được khai báo, chưa được provider xác minh.
2. Không. Credentials có thể được xóa để giảm rò rỉ; trạng thái login nằm trong cơ chế context/token/session.
3. Vì role admin mặc định cần `ROLE_ADMIN`, Alice chưa được cấp authority đó.
4. Principal là đối tượng identity; name là biểu diễn tên chuỗi; details là thông tin phụ của request/authentication.
5. `hasAuthority` kiểm tra chuỗi chính xác, `hasRole` mặc định thêm tiền tố `ROLE_`.
6. Không. Phải kiểm tra quyền theo object, owner, tenant và ngữ cảnh.
7. Vì principal có thể là `Jwt`, `OAuth2User` hoặc kiểu custom tùy provider.
8. Không. Cần chính sách refresh/revocation/TTL hoặc kiểm tra quyền mới khi thực thi.

### Tài liệu tham khảo chính thức

- [Spring Security: Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security: Authorization Architecture / GrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security: OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
