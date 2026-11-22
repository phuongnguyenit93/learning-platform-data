# Thiết kế principal gọn, không lưu mật khẩu hoặc dữ liệu nhạy cảm không cần thiết

## 1. Mục tiêu và vấn đề thực tế

Khi một request đăng nhập được xác thực thành công, Spring Security có thể đưa **Authentication** vào **SecurityContext**. Authentication mang **principal** (danh tính), **credentials** (chứng cứ xác thực), **authorities** (quyền), **details** (dữ liệu phụ) và trạng thái authenticated.

Nếu developer đặt nguyên **UserEntity** vào principal, object có thể mang theo password hash, email, số điện thoại, địa chỉ, thông tin thanh toán, quan hệ JPA và những dữ liệu chỉ dành cho database. Vấn đề xảy ra khi object này bị giữ lâu trong session, cache, heap dump, debug log, exception, JSON response hoặc hệ thống message.

**Nguyên tắc:** Chỉ đưa vào principal những dữ liệu **thật sự cần để định danh người gọi và thực thi chính sách truy cập**. Mật khẩu, password hash và token dùng để xác minh danh tính phải được xử lý tại giai đoạn authentication; không lưu bản sao vào principal của tầng nghiệp vụ.

Phạm vi ví dụ: **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x và Spring MVC/Servlet**. Với JWT/OIDC và WebFlux, principal có kiểu khác; các lưu ý riêng được trình bày phía sau.

Sau bài học, bạn có thể phân biệt các thành phần trong SecurityContext, chọn trường cho principal, viết principal bất biến dùng ID nội bộ, xây một demo xác thực không lưu hash trong principal, tránh serialize dữ liệu nhạy cảm, hiểu xóa credentials, kiểm tra session/cache và thiết kế authorization theo từng tài nguyên.

## 2. Principal là gì, và khác Authentication ra sao?

Trong Java, **java.security.Principal** có getName() để thể hiện danh tính. Trong Spring Security, **Authentication** mở rộng Principal và có getPrincipal(), getCredentials(), getDetails(), getAuthorities(), isAuthenticated().

Thông thường, khi nói “principal của request”, ta muốn nói về giá trị **Authentication.getPrincipal()**.

| Trường | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| Authentication.getPrincipal() | Danh tính của người gửi hoặc người đã được xác thực | Kiểu Object; không mặc nhiên là entity User |
| Authentication.getCredentials() | Password, token hoặc chứng cứ xác thực | Bí mật; tránh lưu lâu và tuyệt đối không log |
| Authentication.getAuthorities() | Quyền đã được cấp từ nguồn tin cậy | Không tin authorities do client tự khai |
| Authentication.getDetails() | Metadata của authentication/request | Có thể chứa IP, session ID hoặc thông tin nhạy cảm |
| Authentication.isAuthenticated() | Trạng thái đã được xác minh theo cơ chế framework | Chỉ provider/manager tin cậy được đánh dấu thành công |
| SecurityContext | Mang Authentication hiện hành | Có thể được lưu qua session hoặc repository |
| UserDetails | Dữ liệu tài khoản phục vụ username/password | Có thể chứa password hash |
| API response DTO | Dữ liệu gửi về client | Phải chọn trường rõ ràng theo quyền được phép |

**UserDetails không đồng nghĩa principal tối giản.** DaoAuthenticationProvider thông thường dùng UserDetailsService để tải UserDetails, kiểm tra mật khẩu và có thể trả UserDetails làm principal. UserDetails có method getPassword() vì nó phục vụ xác minh password. Điều đó không có nghĩa UserDetails nên được trả cho client hoặc log nguyên object.

### 2.1. Trước và sau xác thực

Đầu vào có thể là token chưa xác thực:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

Đây là snippet Java trong một phương thức đã có import; chưa phải chương trình độc lập. Principal là tên do client khai, credentials là password do client gửi, và **isAuthenticated() phải là false**.

Sau khi provider kiểm tra thành công, Authentication mới được coi là đáng tin. Một cấu hình tốt có thể chuyển từ username do client khai sang **ID nội bộ đã xác minh**, đặt credentials=null và cấp authorities theo nguồn dữ liệu tin cậy.

**Tự tạo UsernamePasswordAuthenticationToken authenticated chỉ từ ID client gửi mà không kiểm tra password hoặc token là lỗ hổng xác thực.**

### 2.2. Hash cũng là credential nhạy cảm

Password hash dùng BCrypt, Argon2 hoặc thuật toán tương tự không phải plaintext. Nhưng nếu lộ hash, kẻ tấn công có thể thử đoán mật khẩu ngoại tuyến, tận dụng password yếu hoặc phát hiện cách tái sử dụng password. Vì vậy password hash không phải trường “an toàn để công khai”.

Kho credential có thể cần hash để đối chiếu, còn principal của request **không cần hash** để truy vấn đơn hàng, xem quyền hay ghi nhận ai đang thao tác.

## 3. Chọn dữ liệu tối thiểu cho principal

Principal nên:

1. **Đủ định danh:** Một internal userId/subject ổn định thường là đủ.
2. **Đến từ nguồn đã xác minh:** Không lấy userId hoặc role tùy ý trong request rồi coi là đáng tin.
3. **Bất biến:** Tránh setter làm thay đổi danh tính sau khi authenticate.
4. **Nhỏ và dễ serial hóa khi cần:** Không giữ JPA entity, HttpServletRequest, EntityManager hoặc dependency/service.
5. **Không chứa secret:** Không password, hash, refresh token, access token, API key hoặc session cookie.
6. **Không ôm dữ liệu hiển thị:** Email, display name, avatar, số điện thoại có thể tải từ service khi cần.
7. **Nhất quán quyền:** GrantedAuthority thường nằm trong Authentication; không nhất thiết lặp cả role list trong principal.

### 3.1. Bảng quyết định

| Trường | Mức phù hợp | Lý do |
| --- | --- | --- |
| Internal userId | Thường nên có | Định danh ổn định, tiện kiểm tra ownership |
| Username | Tùy nhu cầu | Có thể đổi và có tính nhận diện cá nhân |
| Tenant ID | Tùy ứng dụng multi-tenant | Cần được xác minh cùng membership |
| Email, phone | Thường không giữ | Dữ liệu cá nhân, không cần trên mọi request |
| Display name | Không cần cho xác thực | Có thể thay đổi; tải khi hiển thị |
| Password plaintext | Tuyệt đối không | Secret trực tiếp |
| Password hash | Không | Giá trị credential nhạy cảm |
| OTP secret, MFA recovery code | Không | Có thể vượt qua bước xác minh |
| Access/refresh token | Không trong custom business principal | Bearer credential cần vòng đời riêng |
| Full JPA UserEntity | Tránh | Dễ lộ dữ liệu và kéo theo object graph |
| Authorities | Thường trong Authentication | Phải lấy từ nguồn đáng tin |
| HttpServletRequest | Không | Không phải dữ liệu danh tính, có vòng đời request |

**UUID không thay thế kiểm tra quyền.** Dù userId khó đoán, người biết ID của người khác vẫn không được đọc tài nguyên của người đó. Authorization cần kiểm tra ownerId/tenantId và quyền nghiệp vụ.

### 3.2. Thiết kế principal với Java record

Một cấu trúc gọn có thể là:

~~~java
public record AppPrincipal(java.util.UUID userId)
        implements java.security.Principal, java.io.Serializable {

    @Override
    public String getName() {
        return userId.toString();
    }
}
~~~

Java 17 record cung cấp component bất biến và các accessors. Cấu trúc này **chỉ có userId**, không có hash/token/PII. Implement Principal giúp Authentication.getName() có thể phản ánh ID thay vì toString của một object tùy biến.

Đây là **snippet về cấu trúc dữ liệu**, chưa phải ứng dụng Spring Boot đầy đủ; phần thực hành bên dưới có file Java chạy trong dự án Boot.

Nếu userId vẫn định danh được một cá nhân, nó có thể được coi là dữ liệu liên kết đến cá nhân. Chỉ trả ID ra API hoặc đưa vào log khi có nhu cầu và chính sách cho phép.

## 4. Phân tách vòng đời password khỏi vòng đời principal

Luồng mong muốn:

~~~text
HTTP request: username + raw password
            |
            v
Authentication filter
            |
            v
AuthenticationManager / ProviderManager
            |
            v
AuthenticationProvider
    |-- UserDetailsService lấy UserDetails và password hash
    |-- PasswordEncoder.matches(raw, hash)
    |-- kiểm tra trạng thái tài khoản, source ID, authorities
            |
            v
Authentication đã xác thực
    |-- principal = AppPrincipal(internal userId)
    |-- credentials = null
    |-- authorities = nguồn tin cậy
            |
            v
SecurityContext của request
            |
            v
Controller -> Service kiểm tra ownerId/role/tenant
            |
            v
Response DTO chỉ chứa trường được phép
~~~

Mật khẩu vẫn có thể tồn tại tạm thời trong Java String, HTTP request hoặc call stack trong quá trình xác thực. Không hứa toàn bộ bí mật lập tức biến mất khỏi heap; mục tiêu chính là **không chủ động đưa chúng vào object lưu dài hạn, log, JSON response, session hoặc message**.

## 5. Ví dụ đầy đủ với principal chỉ chứa UUID

Ví dụ này cố ý tách giai đoạn kiểm tra password khỏi kết quả Authentication để nhìn rõ cách tạo principal tối giản. Nó dùng một AuthenticationProvider minh họa. Trong sản phẩm, **ưu tiên DaoAuthenticationProvider và các cơ chế tích hợp đã được Spring Security cung cấp** nếu yêu cầu authentication thông thường; custom provider cần kiểm thử bảo mật đầy đủ.

### 5.1. Dependencies

Tạo project Spring Boot 3.3.x, Java 17+ bằng Spring Initializr với Gradle Groovy DSL và Gradle Wrapper. Trong **build.gradle** cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là phần dependencies cho một project Boot đã thiết lập plugin, không phải file Gradle độc lập.

### 5.2. File Java hoàn chỉnh

Tạo file **src/main/java/com/example/principal/PrincipalDemoApplication.java**:

~~~java
package com.example.principal;

import java.io.Serializable;
import java.security.Principal;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrincipalDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationProvider compactProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        return new CompactPrincipalProvider(users, encoder);
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationProvider compactProvider) {
        return new ProviderManager(compactProvider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

record CompactPrincipal(UUID userId)
        implements Principal, Serializable {

    @Override
    public String getName() {
        return userId.toString();
    }
}

final class CompactPrincipalProvider implements AuthenticationProvider {

    private static final Map<String, UUID> IDS = Map.of(
        "alice", UUID.fromString("00000000-0000-0000-0000-000000000101"),
        "admin", UUID.fromString("00000000-0000-0000-0000-000000000102")
    );

    private final UserDetailsService users;
    private final PasswordEncoder encoder;
    private final AccountStatusUserDetailsChecker checker =
        new AccountStatusUserDetailsChecker();

    CompactPrincipalProvider(UserDetailsService users,
            PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request.getCredentials() instanceof String password)) {
            throw new BadCredentialsException("Bad credentials");
        }

        UserDetails user;
        try {
            user = users.loadUserByUsername(request.getName());
        } catch (UsernameNotFoundException ex) {
            throw new BadCredentialsException("Bad credentials");
        }

        if (!encoder.matches(password, user.getPassword())) {
            throw new BadCredentialsException("Bad credentials");
        }

        checker.check(user);

        UUID id = IDS.get(user.getUsername());
        if (id == null) {
            throw new BadCredentialsException("Bad credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            new CompactPrincipal(id),
            null,
            user.getAuthorities()
        );
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(tokenType);
    }
}

@RestController
class MeController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    Map<String, Object> me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            CompactPrincipal principal,
            Authentication authentication) {

        var roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "userId", principal.userId().toString(),
            "authenticationName", authentication.getName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **một file Java hoàn chỉnh bên trong project Spring Boot**: public class trùng tên file, record/provider/Controller cùng package, Controller được Spring Boot component scanning phát hiện. Đoạn code dùng Java record, pattern matching cho instanceof và Stream.toList có sẵn từ Java 17.

**Giải thích các bean:**

1. **UserDetailsService** tạo hai user demo với password hash bằng BCrypt và roles USER/ADMIN.
2. **CompactPrincipalProvider** tải user theo username do BasicAuthenticationFilter nhận, dùng PasswordEncoder.matches rồi kiểm tra trạng thái account.
3. Provider chỉ tạo Authentication authenticated khi xác thực đã hợp lệ. Nó lấy ID từ mapping tin cậy trong demo, dùng principal chỉ có UUID và đặt **credentials=null**.
4. **ProviderManager** điều phối provider; **HttpSecurity.authenticationManager** gắn manager cho chuỗi bảo mật.
5. **SecurityFilterChain** cho GET /public public, GET /me cần đăng nhập, GET /admin cần ROLE_ADMIN; URL khác bị denyAll.
6. **@AuthenticationPrincipal** trong Controller lấy đúng kiểu CompactPrincipal từ Authentication; Controller chỉ trả ba trường allowlist.

**Giới hạn demo:** Map IDS và password trong source chỉ phục vụ học tập. Production phải lấy ID từ database/IdP và bảo vệ source credentials. Custom provider còn cần giải quyết timing/user-enumeration, chống brute-force, MFA, event auditing và các vấn đề credential lifecycle. Nếu hệ thống chỉ dùng username/password tiêu chuẩn, hãy dùng DaoAuthenticationProvider đã được kiểm chứng.

### 5.3. Vì sao kết quả không giữ password hoặc hash?

Trong provider:

~~~java
return UsernamePasswordAuthenticationToken.authenticated(
    new CompactPrincipal(id),
    null,
    user.getAuthorities()
);
~~~

**principal** chỉ có userId; **credentials=null**; **authorities** lấy từ UserDetails đáng tin. Object UserDetails chứa hash phục vụ kiểm tra không được đưa vào principal thành công. Ngay cả khi Authentication được lưu trong session, record CompactPrincipal không mang theo hash.

Mỗi byte hash có thể vẫn nằm trong source user store để kiểm tra đăng nhập sau này; việc đó đúng với chức năng credential store. Nhưng hash **không cần được copy vào SecurityContext**. Không khẳng định mọi nơi trong JVM đều đã xóa hash.

### 5.4. Tại sao phải kiểm tra account status?

Checker kiểm tra trạng thái tài khoản theo UserDetails, chẳng hạn disabled/locked/expired. Nếu tự viết provider chỉ so sánh password mà bỏ qua account flags, một user bị vô hiệu hóa vẫn có thể đăng nhập. Đây là lý do custom provider cần review bảo mật và test nhánh thất bại, không chỉ happy path.

Ví dụ trả BadCredentialsException cho username không tồn tại và password sai để không tiết lộ rõ account có tồn tại qua thông báo. Nhưng timing vẫn có thể khác; chống enumeration, rate limiting và telemetry cần được thiết kế riêng cho sản phẩm.

## 6. Chạy ví dụ và đọc kết quả

Chạy trong thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell sử dụng **.\gradlew.bat bootRun**. Giả định server dùng localhost:8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u alice:learn123 http://localhost:8080/me
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Trong PowerShell, dùng **curl.exe** nếu curl là alias. Password hard-code trong các lệnh chỉ dùng ở localhost. HTTP Basic cần HTTPS ở mạng thật; để tránh password nằm trong history, dùng **curl -u alice URL** và nhập password khi được hỏi.

| Request | HTTP status kỳ vọng | Lý do |
| --- | --- | --- |
| GET /public anonymous | **200** | permitAll |
| GET /me anonymous | **401** | Cần authentication |
| GET /me alice + password sai | **401** | Provider từ chối |
| GET /me alice + password đúng | **200** | Authentication có CompactPrincipal |
| GET /admin alice + password đúng | **403** | Thiếu ROLE_ADMIN |
| GET /admin admin + password đúng | **200** | Có ROLE_ADMIN |

Response dự kiến của GET /me với alice:

~~~json
{
  "userId": "00000000-0000-0000-0000-000000000101",
  "authenticationName": "00000000-0000-0000-0000-000000000101",
  "authorities": ["ROLE_USER"]
}
~~~

Thứ tự key JSON có thể khác; hãy kiểm tra giá trị chứ không so sánh text vị trí. Response **không chứa password, password hash, token, email hoặc UserDetails**.

Các status/JSON là **kỳ vọng dựa trên code**, không phải output đã đo bằng việc chạy một build trong tài liệu. Tùy SecurityFilterChain, proxy hoặc exception handling có thể có phản hồi khác.

### 6.1. Test an toàn hơn chỉ tìm chuỗi

Cần kiểm tra **schema response**, loại principal thực tế và các vị trí lưu/log. Một response không chứa chuỗi raw password thử chưa chứng minh an toàn nếu nó chứa hash hoặc dữ liệu nhạy cảm dưới dạng khác.

## 7. Ứng dụng thật có cần tự viết AuthenticationProvider không?

**Không nhất thiết.** Với username/password tiêu chuẩn, Spring Security có **DaoAuthenticationProvider**, UserDetailsService và PasswordEncoder; đây thường là lựa chọn phù hợp hơn việc tự viết logic kiểm tra credential.

Nếu provider chuẩn trả UserDetails làm principal:

- Không trả Authentication hoặc UserDetails từ Controller.
- Dùng @AuthenticationPrincipal để đọc đúng dữ liệu cần và chuyển thành response DTO có allowlist.
- Tách UserDetails khỏi JPA UserEntity đồ sộ.
- Xác định SecurityContext/session thực sự giữ gì và có cần giảm tiếp hay không.
- Khi cần ID nội bộ, ánh xạ username đã xác thực sang ID theo nguồn tin cậy.

Một custom provider tạo principal tối giản như bài demo chỉ nên dùng nếu có nhu cầu rõ và đã kiểm tra đầy đủ tính đúng đắn của xác thực, trạng thái tài khoản, auth events, rollback/revocation và xử lý lỗi.

**Đừng đánh đổi một provider chuẩn đã được kiểm thử để đổi lấy một principal gọn bằng cách bỏ các bước kiểm chứng bắt buộc.**

## 8. CredentialsContainer và ProviderManager có giải quyết toàn bộ vấn đề?

Spring Security có interface **CredentialsContainer** cho phép các object chứa secret thực hiện **eraseCredentials()**. ProviderManager theo mặc định cố xóa credentials của Authentication được trả về sau xác thực nếu nó hỗ trợ interface này.

Điểm cần hiểu:

- Việc xóa chỉ tác động các object được thiết kế tham gia cơ chế đó; không tự làm biến mất bản sao trong request, Java String, thread dump, heap hay log.
- Nếu Authentication.getPrincipal() là một UserDetails hỗ trợ erasure, password bên trong principal có thể bị xóa sau thành công.
- Không dựa vào xóa sau login để hợp thức hóa việc giữ hash trong dữ liệu trả về hoặc trong log.
- Một custom Authentication giữ secret trong trường riêng cần cách xử lý credential rõ; tốt hơn là **không đưa secret vào token thành công**.
- Có thể có rủi ro nếu UserDetails cache cùng tham chiếu với principal bị erasure: password trong cache cũng có thể bị xóa và lần authenticate sau gặp lỗi.

**Cách làm tốt:** Tách nguồn cache credential khỏi object principal và response. Không tùy tiện tắt eraseCredentialsAfterAuthentication chỉ để tránh lỗi cache; trước tiên sửa thiết kế tham chiếu/vòng đời.

## 9. Principal với session, stateless API, JWT và OIDC

### 9.1. Session-based authentication

Khi sử dụng session/cookie, SecurityContext có thể được lưu và khôi phục qua SecurityContextRepository. Principal lớn có thể làm session phình to, tăng dữ liệu lưu ở session store hoặc object serialization, tạo rủi ro khi debug và phụ thuộc vào entity/JPA proxy.

Principal chỉ chứa ID giúp giảm bề mặt thông tin được lưu. Nhưng **không tự bảo đảm session an toàn**; còn cần cookie Secure/HttpOnly/SameSite phù hợp, TLS, session fixation protection, timeout, logout và cơ chế thu hồi phiên.

### 9.2. Stateless authentication

Với API stateless/Bearer token, Authentication có thể được tạo từ đầu theo từng request. Principal gọn vẫn hữu ích để giảm dữ liệu luân chuyển giữa filters, business code và log. Tuy nhiên token và claims có thể vẫn được giữ trong Authentication implementation của cơ chế Resource Server.

**Stateless không có nghĩa secret không cần bảo vệ.** Bearer token bị lộ có thể được sử dụng như credential cho tới khi hết hạn hoặc bị thu hồi.

### 9.3. JWT

Trong OAuth2 Resource Server, Authentication có thể là JwtAuthenticationToken với principal Jwt; Jwt có thể chứa claims và token value. Không nên serialize hoặc log nguyên Jwt/JwtAuthenticationToken.

**JWT có chữ ký thông thường không mã hóa payload.** Claims có thể được giải mã bởi bên sở hữu token. Vì vậy không đưa password/hash, refresh token, bí mật kinh doanh, hồ sơ cá nhân chi tiết hoặc thông tin không cần thiết vào claims. Chỉ sử dụng định danh/authorities từ JWT sau khi xác minh chữ ký, issuer, audience, expiry và các điều kiện áp dụng.

Một service cần principal nội bộ gọn có thể ánh xạ **sub** đã xác minh sang internal userId. Không tự coi chuỗi sub do client tự khai trong header là đáng tin.

### 9.4. OIDC/OAuth2 login

Principal OIDC thường là OidcUser hoặc OAuth2User có attributes/claims, có thể bao gồm email, tên hoặc các token protocol. Những thứ này không mặc nhiên được phép tiết lộ cho mọi Controller hoặc client.

Ánh xạ từ external identity sang internal userId và chỉ sử dụng claims cần thiết. Khi nhiều identity provider cùng dùng, định danh liên kết nên xét **issuer + subject**, vì một chuỗi sub có thể không duy nhất giữa các issuer.

### 9.5. Multi-tenant

Nếu ứng dụng cần tenantId trong principal, chỉ giữ nó sau khi membership/tenant access đã được xác minh. Một header X-Tenant-Id hoặc query parameter do client gửi không chứng minh user thuộc tenant đó. Kiểm tra quyền phải xét kết hợp userId, tenantId, ownerId và hành động nghiệp vụ.

## 10. Không return principal hoặc Authentication nguyên object

Đây là anti-pattern:

~~~java
@GetMapping("/me")
Object unsafe(Authentication authentication) {
    return authentication;
}
~~~

Tùy implementation, Jackson có thể serialize principal, credentials, details, authorities hoặc thuộc tính khác. Đổi version thư viện có thể thay đổi cấu trúc JSON và vô tình lộ thông tin.

Hãy trả **DTO chọn trường**:

~~~java
record MyIdentityDto(String userId) {}

@GetMapping("/me")
MyIdentityDto safe(
        @AuthenticationPrincipal CompactPrincipal principal) {
    return new MyIdentityDto(principal.userId().toString());
}
~~~

Đây là snippet đặt trong Controller, cần import và class record phù hợp; code đầy đủ ở mục 5 đã minh họa chính sách tương tự bằng Map.

Tương tự, không đưa nguyên UserEntity (có passwordHash, phone, address, quan hệ JPA) vào principal. Nếu Controller cần thông tin hồ sơ, gọi service với internal userId để lấy đúng các trường cho phép và kiểm tra quyền.

### 10.1. Log cũng là nơi làm lộ dữ liệu

- Không log raw password, Authorization header, refresh/access token, JWT, cookie hoặc password hash.
- Tránh log cả Authentication, UserDetails, OidcUser, Jwt hoặc JPA UserEntity mà không biết toString của chúng chứa gì.
- Java record mặc định có toString hiển thị mọi component; record chứa secret không tự an toàn.
- Lombok @Data/@ToString có thể sinh toString chứa password/hash.
- MDC/tracing chỉ giữ correlation ID hoặc userId tối thiểu nếu policy cho phép, không phát tán email/phone/token.
- Exception và debug dump cũng cần được kiểm tra, không chỉ API response.

UserId là định danh có thể liên kết tới người thật; chính sách logging vẫn cần giới hạn quyền xem và thời hạn lưu.

## 11. Vai trò và trạng thái account có thể thay đổi

Authentication thường giữ authorities tại thời điểm xác thực. Nếu admin thu hồi role hoặc khóa account, một session cũ có thể tiếp tục sử dụng authorities cũ cho tới khi được refresh, hết hạn hoặc bị thu hồi.

Đó là vấn đề **vòng đời quyền**, độc lập với việc principal có nhỏ hay không. Hãy xác định:

1. Những quyền nào được lưu trong session hoặc token?
2. Khi role thay đổi, khi nào Authentication được tạo mới?
3. Khi account bị khóa hoặc logout toàn bộ thiết bị, các phiên cũ được vô hiệu hóa thế nào?
4. Nếu token có thời gian sống dài, tác động của quyền cũ được giới hạn ra sao?
5. Policy theo ownerId/tenantId có được kiểm tra tại mỗi yêu cầu nhạy cảm không?

Principal có UUID giúp xác định user, nhưng không tự thay dữ liệu authorization hiện hành. Một user có ROLE_USER vẫn phải bị từ chối nếu cố sửa order không thuộc quyền mình.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| Principal giữ UserEntity toàn bộ | Hash/PII, lazy relation lọt sang context/log | Projection ID tối giản |
| Principal giữ plaintext password | Secret tồn tại lâu | Chỉ dùng password lúc authenticate |
| Principal giữ password hash | Credential nhạy cảm bị phát tán | Tách credential store |
| Principal giữ refresh token | Có thể bị lạm dụng để cấp quyền mới | Quản lý token bằng cơ chế riêng |
| UserDetails trả thẳng từ API | Có thể lộ getPassword và account flags | Response DTO allowlist |
| Authentication được return JSON | Serialize details/credentials tùy implementation | Chỉ trả dữ liệu client cần |
| Role lấy từ request body | Tự nâng quyền | Gán authority từ nguồn tin cậy |
| Tự tạo token authenticated không xác minh | Authentication bypass | Provider phải kiểm tra credential |
| Custom provider bỏ account status | User bị khóa vẫn login | Dùng provider chuẩn hoặc status checker |
| Tắt credential erasure để sửa cache | Giữ secret lâu hơn | Tách object/cache |
| Không refresh role sau khi thu hồi | Quyền cũ vẫn còn trong session | TTL, revocation, re-check |
| Đưa JWT đầy đủ vào log | Lộ bearer token/claims | Redaction và log tối thiểu |
| Trả mọi claim OIDC | Rò PII và token metadata | Map đúng các claims cần |
| Dựa vào UUID khó đoán | IDOR/BOLA | Kiểm tra ownerId/permission |
| Principal chứa HttpServletRequest | Lệch lifecycle, khó serialize | Chỉ chứa dữ liệu danh tính |

## 13. Kiểm thử tối thiểu phải có

### 13.1. Thành phần principal

- Kiểm tra CompactPrincipal chỉ có **UUID userId** và getName trả ID.
- Không có field password, passwordHash, token, email, phone hoặc entity User.
- Code business không sửa được ID sau khi authenticate.
- Principal không giữ service hoặc object có state phức tạp.

### 13.2. Giai đoạn xác thực

- Username/password đúng → trả Authentication đã xác thực với CompactPrincipal, credentials=null, role đáng tin.
- Password sai → AuthenticationException, không trả token thành công.
- Username không tồn tại → không xác thực.
- Account disabled/locked/expired → không xác thực.
- Không có cách đưa tự do role/ID trong request để bypass provider.

### 13.3. API và logs

- GET /me chỉ trả schema cho phép, không trả UserDetails hoặc Authentication nguyên object.
- SecurityContext/session/cache không giữ ngoài những dữ liệu đã thiết kế.
- Logs, error responses, tracing không ghi secrets.
- JWT/OIDC path không trả nguyên claims/token.
- Business authorization từ chối truy cập bản ghi thuộc người khác.

Đừng chỉ tìm chuỗi password trong JSON rồi kết luận an toàn: bí mật có thể xuất hiện ở dạng hash, token hoặc object metadata.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Password hash đã được băm thì có nên lưu trong principal không?  
**Đáp:** Không. Hash vẫn là credential nhạy cảm, không cần cho nghiệp vụ sau xác thực.

**Câu 2.** Authentication.getPrincipal() có luôn là UserDetails không?  
**Đáp:** Không. Tùy cơ chế authentication, nó có thể là String, UserDetails, Jwt, OidcUser hoặc custom principal.

**Câu 3.** Tại sao dùng record CompactPrincipal(UUID userId)?  
**Đáp:** Chỉ giữ ID đã xác minh, immutable và tránh mang toàn bộ dữ liệu tài khoản.

**Câu 4.** ProviderManager eraseCredentials có xóa mọi bản sao raw password khỏi JVM không?  
**Đáp:** Không. Nó chỉ áp dụng tới object hỗ trợ hợp đồng xóa; còn request, cache, log, heap cần xem riêng.

**Câu 5.** Vì sao phải gọi PasswordEncoder.matches trước khi tạo Authentication authenticated?  
**Đáp:** Credential phải được kiểm chứng; nếu không client có thể giả mạo danh tính.

**Câu 6.** Tại sao không trả nguyên Authentication từ endpoint /me?  
**Đáp:** Nó có thể chứa details/credentials/principal nhạy cảm và cấu trúc thay đổi qua thư viện.

**Câu 7.** JWT đã được ký có đảm bảo claims là bí mật không?  
**Đáp:** Không. Chữ ký bảo vệ tính toàn vẹn, còn payload JWT thông thường đọc được.

**Câu 8.** UserId UUID có làm kiểm tra ownerId trở nên không cần thiết không?  
**Đáp:** Không. ID không thay authorization.

**Câu 9.** Role USER bị thu hồi trong khi session chưa hết hạn, phải làm gì?  
**Đáp:** Có chính sách refresh/revocation hoặc kiểm tra quyền hiện hành, tránh giữ authorities cũ vô hạn.

**Câu 10.** Tại sao OIDC issuer và subject đều quan trọng?  
**Đáp:** Subject phải được phân biệt theo issuer khi ánh xạ danh tính từ nhiều nhà cung cấp.

## 15. Tài liệu chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authentication API 6.3.4: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/Authentication.html
- Spring Security — CredentialsContainer: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html
- Spring Security — MVC Integration và @AuthenticationPrincipal: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — Username/Password: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
