# DaoAuthenticationProvider kết nối UserDetailsService với PasswordEncoder

> **Bối cảnh:** Spring Security cho Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Chủ đề này giải thích **DaoAuthenticationProvider** là cầu nối giữa việc **tìm account** qua `UserDetailsService` và việc **kiểm tra password** qua `PasswordEncoder`. Nội dung đi từ luồng thực thi, hợp đồng các interface, cách cấu hình provider tường minh, ví dụ đầy đủ có thể chạy với Spring Boot, kiểm thử lỗi xác thực đến các vấn đề triển khai thật như trạng thái account, hash migration, cache và nhiều provider.

## 1. Vấn đề cần giải quyết

Ứng dụng quản lý tài khoản có thể lưu các trường sau:

| username | password_hash | enabled | locked | authorities |
| --- | --- | --- | --- | --- |
| alice | BCrypt hash đã lưu | true | false | ROLE_USER, profile:read |
| admin | BCrypt hash đã lưu | true | false | ROLE_ADMIN |
| locked | BCrypt hash đã lưu | true | true | ROLE_USER |
| disabled | BCrypt hash đã lưu | false | false | ROLE_USER |

Client gửi `username` và **raw password** để đăng nhập. Spring Security phải tìm account tương ứng, kiểm tra password, từ chối tài khoản bị khóa/vô hiệu hóa và tạo một danh tính đáng tin cậy nếu thông tin hợp lệ.

Ta có ba vai trò tách biệt:

- **`UserDetailsService`**: tìm account theo username và trả `UserDetails` gồm username, password hash, authorities và trạng thái account.
- **`PasswordEncoder`**: so sánh raw password trong yêu cầu với encoded password/hash đã lưu bằng `matches(raw, encoded)`.
- **`DaoAuthenticationProvider`**: một `AuthenticationProvider` dùng cả hai thành phần trên, kiểm tra trạng thái tài khoản và tạo `Authentication` đã xác thực khi thành công.

**DaoAuthenticationProvider không phải repository.** Nó không tự biết bạn dùng JPA, JDBC, in-memory, LDAP adapter hay HTTP client tới identity service. Nguồn account nằm sau `UserDetailsService`. Nó cũng không tự quyết định một tài liệu cụ thể thuộc quyền sở hữu của ai; kiểm soát quyền ở bước authorization/domain policy.

## 2. Sơ đồ kết nối các thành phần

Với HTTP Basic hoặc form login sử dụng username/password, đường đi thông dụng là:

~~~text
HTTP request
    |
    | username="alice", rawPassword="alice123"
    v
Authentication Filter
    BasicAuthenticationFilter / UsernamePasswordAuthenticationFilter
    |
    | Tạo UsernamePasswordAuthenticationToken
    | principal="alice"; credentials="alice123"
    | authenticated=false
    v
AuthenticationManager (thường ProviderManager)
    |
    | Tìm provider hỗ trợ loại Authentication
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername("alice")
    |           |
    |           +--> AccountRepository/database
    |           +--> UserDetails
    |                 username="alice"
    |                 password="$2a$..." (hash đã lưu)
    |                 authorities=[ROLE_USER, profile:read]
    |                 account flags
    |
    +--> Kiểm tra trạng thái account
    |       enabled / locked / account-expired
    |
    +--> PasswordEncoder.matches("alice123", "$2a$...")
    |
    +--> Kiểm tra credential chưa hết hạn
    |
    v
UsernamePasswordAuthenticationToken đã xác thực
    principal=UserDetails
    authorities=[ROLE_USER, profile:read]
    authenticated=true
    |
    v
Authentication Filter đặt kết quả vào SecurityContext
    |
    v
AuthorizationFilter hoặc method security
    |
    +--> ALLOW / DENY theo quyền và tài nguyên
~~~

**Cần đọc sơ đồ theo trách nhiệm**, không coi nó là lời cam kết thứ tự của tất cả filter hay mọi provider. `DaoAuthenticationProvider` kế thừa logic kiểm tra account của `AbstractUserDetailsAuthenticationProvider`. Bên trong provider, có thể có cơ chế cache UserDetails, kiểm tra trạng thái trước/sau bước so khớp credential và xử lý cập nhật hash tùy cấu hình.

Những điều quan trọng có thể kiểm chứng:

1. Filter tạo **Authentication request** chưa được tin cậy; việc có username trong request **không đồng nghĩa đã đăng nhập**.
2. `ProviderManager` thử các `AuthenticationProvider` phù hợp theo cơ chế của nó. `DaoAuthenticationProvider` là provider cho username/password qua `UserDetailsService`.
3. `UserDetailsService` tải hash và trạng thái; nó **không có tham số raw password**, nên không tự quyết định mật khẩu đúng hay sai.
4. `PasswordEncoder.matches` kiểm tra raw password với hash lưu trữ; không tự giải mã BCrypt.
5. Provider trả `Authentication` kết quả với principal và authorities đã được kiểm tra.
6. Authentication filter mới đưa kết quả vào `SecurityContext`; **authorization** sau đó có thể cho hoặc từ chối request.

## 3. Mỗi thành phần nhận gì và trả gì?

| Thành phần | Input chính | Output | Nếu thất bại |
| --- | --- | --- | --- |
| `UserDetailsService` | `String username` | `UserDetails` | `UsernameNotFoundException` |
| `PasswordEncoder.encode` | Raw password khi tạo/đổi mật khẩu | Encoded password mới | Lỗi encoder hoặc dữ liệu không phù hợp |
| `PasswordEncoder.matches` | Raw password request và encoded hash từ store | `boolean` | false khi credential không khớp; format lỗi có thể gây exception |
| `DaoAuthenticationProvider.authenticate` | `Authentication` hỗ trợ username/password | `Authentication` đã xác thực | `AuthenticationException` phù hợp |
| `ProviderManager.authenticate` | `Authentication` request | Kết quả provider được chọn | AuthenticationException nếu không thành công |
| `AuthorizationManager` | Authentication/context và đối tượng cần bảo vệ | Quyết định quyền | Deny/chuyển xử lý phù hợp |

### 3.1. `UserDetailsService` chỉ làm nhiệm vụ lookup

Contract:

~~~java
// Chữ ký giản lược để học, không phải mã nguồn thư viện.
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

Một implementation cần:

- Tìm **đúng account** từ nguồn được tin cậy.
- Nếu không tồn tại, ném `UsernameNotFoundException`; không trả null và không bịa user mặc định.
- Nếu tồn tại, trả `UserDetails` với **password hash đã lưu**, authorities và bốn cờ trạng thái đúng.
- Không lấy password raw từ request, không tự so khớp password và không tự đánh dấu SecurityContext là đã xác thực.

Điều này giải thích vì sao trong cùng một ứng dụng, `loadUserByUsername("alice")` vẫn có thể trả UserDetails chính xác **kể cả khi client nhập password sai**. Việc từ chối sai password xảy ra sau đó trong `DaoAuthenticationProvider`.

### 3.2. `UserDetails`: dữ liệu bảo mật của account

Các method quan trọng:

~~~java
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isEnabled();
boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
~~~

Chữ ký trên thuộc interface, chỉ là snippet để đọc. Đặc biệt:

- `getPassword()` nên là **encoded hash lưu trong store**, không phải raw password.
- `getAuthorities()` chứa các `GrantedAuthority` đáng tin cậy, ví dụ `ROLE_USER`.
- `isAccountNonLocked() == true` nghĩa là account **không bị khóa**.
- `isCredentialsNonExpired() == false` nghĩa là credential đã hết hạn.
- `isEnabled() == false` nghĩa là account bị vô hiệu hóa.

Tên cờ `isAccountNonLocked` dễ bị ánh xạ ngược với cột DB `locked`. Nếu DB lưu `locked=true`, UserDetails phải thể hiện **account không còn non-locked**.

### 3.3. `PasswordEncoder` so khớp thay cho so sánh String

Contract:

~~~java
// Chữ ký quan trọng, chỉ để học interface.
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
boolean upgradeEncoding(String encodedPassword);
~~~

`encode(raw)` thường dùng **khi tạo hoặc đổi mật khẩu**, trước khi lưu password hash. `matches(raw, encoded)` dùng **khi login**. `upgradeEncoding(...)` là tín hiệu hỗ trợ chiến lược nâng cấp hash, không tự thay đổi database khi gọi.

Với BCrypt, hai lần `encode("alice123")` có thể tạo hash khác nhau vì salt. Vì vậy:

~~~java
// Sai: encode lại rồi so sánh chuỗi mã hóa
encoder.encode(rawPassword).equals(storedHash);

// Đúng: PasswordEncoder tự kiểm tra raw với stored hash
encoder.matches(rawPassword, storedHash);
~~~

Đây là snippet, cần các biến encoder/rawPassword/storedHash trong chương trình thật. **Không giải mã ngược hash để lấy password.**

## 4. DaoAuthenticationProvider làm gì với hai dependency?

`DaoAuthenticationProvider` là implementation cụ thể của `AuthenticationProvider`, được xây dựng trên logic chung của `AbstractUserDetailsAuthenticationProvider`.

Trong Spring Security 6.5, cấu hình tường minh có dạng:

~~~java
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(userDetailsService);

provider.setPasswordEncoder(passwordEncoder);
~~~

Đây là snippet cần hai dependency đã được khai báo. Dùng constructor nhận `UserDetailsService` giúp nêu rõ nguồn account, sau đó gắn đúng `PasswordEncoder` cho định dạng hash lưu trữ. Những constructor hoặc setter cũ cho service đã được deprecated ở dòng API 6.5; khi đọc tutorial cũ nên kiểm tra version đang dùng.

### 4.1. `supports(...)` và ProviderManager

Một `ProviderManager` có thể chứa nhiều provider. Mỗi provider có phương thức `supports(Class<?>)` để cho biết liệu nó có thể xử lý loại Authentication nào.

~~~text
ProviderManager
  |
  +--> DaoAuthenticationProvider
  |      thường xử lý UsernamePasswordAuthenticationToken
  |
  +--> Provider khác
  |      xử lý loại Authentication tương ứng
  |
  +--> Provider khác...
~~~

`supports(...) == true` **không bảo đảm username/password hợp lệ**; nó chỉ có nghĩa provider có thể xem xét loại request này. `authenticate(...)` mới kiểm tra credential. Nếu không provider nào xử lý được, hệ thống có thể báo `ProviderNotFoundException`.

Không tùy tiện thêm provider chỉ vì project có một lớp `UserDetailsService`. Khi có custom AuthenticationManager, nhiều provider hoặc nhiều SecurityFilterChain, phải xác nhận chain đang dùng đúng provider và đúng encoder.

### 4.2. Luồng tìm user

Provider nhận `UsernamePasswordAuthenticationToken` chưa xác thực, lấy username rồi gọi `loadUserByUsername(username)` qua service đã đăng ký. Kết quả được ánh xạ thành UserDetails.

Nếu service ném `UsernameNotFoundException`, `DaoAuthenticationProvider` thông dụng mặc định **che chi tiết không tồn tại username thành lỗi BadCredentials chung**, giúp giảm nguy cơ lộ danh sách account qua response. Tùy cấu hình và handler, HTTP client thường thấy `401` với Basic; không nên trả thông điệp phân biệt “username chưa đăng ký” và “password sai” cho đối tượng không đáng tin cậy.

### 4.3. Kiểm tra trạng thái account

`DaoAuthenticationProvider` còn dùng cơ chế kiểm tra trạng thái của UserDetails qua lớp cha.

| Trạng thái UserDetails | Ý nghĩa khi false | Exception nội bộ thường gặp |
| --- | --- | --- |
| `isEnabled()` | Account disabled | `DisabledException` |
| `isAccountNonLocked()` | Account locked | `LockedException` |
| `isAccountNonExpired()` | Account expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials expired | `CredentialsExpiredException` |

Các lỗi trạng thái này có thể được phát hiện **trước hoặc sau** kiểm tra password tùy loại cờ và provider. Với username/password thông dụng, trạng thái account cơ bản được kiểm tra trước password; credential expiration là một kiểm tra khác. Không nên làm API tiết lộ trạng thái khóa/disabled cho người không được phép xác nhận danh tính.

**Đừng tự bỏ các cờ trạng thái vì login vẫn chạy**: lỗi mapping boolean có thể cho phép account đang khóa tiếp tục xác thực, hoặc làm tất cả account bị từ chối.

### 4.4. Kiểm tra password và tạo kết quả

Sau khi có UserDetails và vượt các kiểm tra cần thiết, provider gọi logic tương đương:

~~~java
boolean passwordCorrect =
    passwordEncoder.matches(
        rawPasswordFromAuthentication,
        userDetails.getPassword()
    );
~~~

Đây là **mô tả bằng snippet**, không phải yêu cầu tự viết vào service. Nếu password không khớp, provider từ chối bằng `BadCredentialsException` theo cơ chế thông dụng.

Nếu hợp lệ, provider tạo **Authentication kết quả** với principal thường là UserDetails đã tải, authorities tương ứng và trạng thái đã xác thực. Không cần controller tự tạo một token `authenticated(...)` từ role client gửi.

### 4.5. Provider và Filter có vai trò khác nhau

`DaoAuthenticationProvider.authenticate(...)` **không tự gửi HTTP 200 hoặc 401** và cũng **không tự lưu SecurityContext như authentication filter**. Filter gọi `AuthenticationManager`, nhận kết quả, rồi thực hiện việc đặt Authentication vào context theo cơ chế Spring Security.

Vì vậy khi debug:
- Service được gọi nhưng controller không chạy: kiểm tra password/flags, exception, filter và authorization.
- Authentication đã thành công nhưng endpoint nhận 403: kiểm tra authorities, rule URL/method, CSRF hoặc domain policy.
- Request dùng JWT Bearer mà service không chạy: có thể request đang vào một provider/chain khác, hoàn toàn không dùng DaoAuthenticationProvider.

## 5. Khi nào provider này phù hợp?

| Loại xác thực | DaoAuthenticationProvider có phải cơ chế mặc định? |
| --- | --- |
| Form login username/password với UserDetailsService | Thường phù hợp |
| HTTP Basic username/password với UserDetailsService | Thường phù hợp |
| OAuth2 Resource Server JWT | **Không**; dùng JwtDecoder/JwtAuthenticationProvider và converter phù hợp |
| Opaque bearer token | **Không mặc định**; dùng introspection và provider tương ứng |
| OAuth2 Login/OpenID Connect | **Không mặc định**; có flow/token/user services riêng |
| API key hoặc magic link tùy biến | Không mặc định; cân nhắc AuthenticationProvider chuyên biệt |
| Spring WebFlux reactive | Không dùng Servlet DaoAuthenticationProvider đồng bộ theo cách trong bài; có API reactive riêng |

Không ép mọi token vào `loadUserByUsername` rồi gọi đó là “xác minh JWT”. Việc xác thực JWT yêu cầu validate chữ ký, issuer/audience, thời hạn và các claim theo thiết kế.

## 6. Demo chạy được: Spring Boot 3, Java 17 và provider tường minh

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, **Spring MVC**, **Java 17+**, **HTTP Basic**. Chúng ta đăng ký `DaoAuthenticationProvider` một cách tường minh để quan sát rõ quan hệ với UserDetailsService và PasswordEncoder.

Hệ thống có bốn account demo:

| Account | Password dùng cho localhost | Authorities | Trạng thái |
| --- | --- | --- | --- |
| alice | alice123 | ROLE_USER, profile:read | Hoạt động |
| admin | admin123 | ROLE_ADMIN, profile:read | Hoạt động |
| locked | locked123 | ROLE_USER | Bị khóa |
| disabled | disabled123 | ROLE_USER | Bị vô hiệu hóa |

**Đây là credential minh họa**, không dùng trong production. Password thật phải được bảo vệ khi tạo/đổi và hash được lưu bền vững. Trong demo, repository giữ account trong bộ nhớ và tạo hash lúc khởi động; service **chỉ đọc hash**.

### 6.1. Dependencies và cấu trúc

Với project Spring Boot 3.x có Gradle plugin, Java 17 và Gradle Wrapper đã được khởi tạo, block dependencies trong **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **phần dependencies** của project, không phải build.gradle hoàn chỉnh độc lập. Các file Java cùng package:

~~~text
src/main/java/com/example/daodemo/
  DaoDemoApplication.java
  Account.java
  DemoAccountRepository.java
  AccountUserDetailsService.java
  SecurityConfig.java
  AccountController.java

src/test/java/com/example/daodemo/
  DaoProviderTest.java
~~~

### 6.2. DaoDemoApplication.java

~~~java
package com.example.daodemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DaoDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoDemoApplication.class, args);
    }
}
~~~

### 6.3. Account.java: model độc lập với Spring Security

~~~java
package com.example.daodemo;

import java.util.Set;

public record Account(
    String username,
    String passwordHash,
    boolean enabled,
    boolean locked,
    Set<String> authorities
) {
}
~~~

`Account` là record thuộc ứng dụng, **không bắt buộc implements UserDetails**. Khi kết nối JPA, record này có thể được thay bằng entity hoặc một domain model, còn service bên dưới sẽ chuyển dữ liệu sang UserDetails.

### 6.4. DemoAccountRepository.java: nguồn hash/flags

~~~java
package com.example.daodemo;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

@Repository
public class DemoAccountRepository {

    private final Map<String, Account> accounts;

    public DemoAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "alice", new Account(
                "alice", encoder.encode("alice123"),
                true, false,
                Set.of("ROLE_USER", "profile:read")
            ),
            "admin", new Account(
                "admin", encoder.encode("admin123"),
                true, false,
                Set.of("ROLE_ADMIN", "profile:read")
            ),
            "locked", new Account(
                "locked", encoder.encode("locked123"),
                true, true,
                Set.of("ROLE_USER")
            ),
            "disabled", new Account(
                "disabled", encoder.encode("disabled123"),
                false, false,
                Set.of("ROLE_USER")
            )
        );
    }

    public Optional<Account> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}
~~~

**Chỗ tạo hash là constructor repository dùng cho demo, không nằm trong `loadUserByUsername`.** Trong ứng dụng thật, sau khi người dùng tạo hoặc đổi mật khẩu, `encode(raw)` sẽ tạo hash được lưu vào database. Khi login, repository đọc hash tồn tại thay vì encode lại.

### 6.5. AccountUserDetailsService.java: adapter cho provider

~~~java
package com.example.daodemo;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final DemoAccountRepository repository;

    public AccountUserDetailsService(DemoAccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (username == null || username.isBlank()) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .build();
    }
}
~~~

Giải thích:

- `@Service` khiến Spring tạo bean implement `UserDetailsService`.
- `loadUserByUsername` nhận **username**, không nhận raw password.
- Không tìm thấy account: ném `UsernameNotFoundException`, không trả null.
- `.password(account.passwordHash())` nhận **hash đã lưu**; không gọi encoder ở đây.
- `.authorities(...)` giữ các chuỗi `ROLE_` và permission theo policy ứng dụng.
- `.disabled(!enabled)` và `.accountLocked(locked)` chuyển đúng chiều cờ từ record.
- Các cờ `accountExpired`/`credentialsExpired` không được lưu trong model demo nên User builder sử dụng giá trị mặc định cho account/credential còn hiệu lực. Production cần ánh xạ đầy đủ nếu dữ liệu có các trạng thái này.

Điểm quan trọng: **Service trả UserDetails không đồng nghĩa password đã đúng**. Chỉ `DaoAuthenticationProvider` mới thực hiện bước kiểm tra này.

### 6.6. SecurityConfig.java: kết nối service, encoder và filter chain

~~~java
package com.example.daodemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DaoAuthenticationProvider daoProvider) throws Exception {

        http
            .authenticationProvider(daoProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

Đây là **kết nối tường minh**:

1. Spring cung cấp bean `PasswordEncoder` dùng BCrypt.
2. `AccountUserDetailsService` là một bean `UserDetailsService`, do `@Service` khai báo.
3. Method `daoAuthenticationProvider(...)` nhận cả hai bean. Provider có **service để tìm user** và **encoder để kiểm tra hash**.
4. `.authenticationProvider(daoProvider)` đăng ký provider cho HttpSecurity của chain demo. Cách này làm rõ provider đang được sử dụng, đặc biệt khi đang học.
5. `httpBasic(...)` bật BasicAuthenticationFilter để client gửi username/password.
6. `/public` public, `/me` cần authenticated, `/admin` cần `ROLE_ADMIN`, endpoint khác bị deny.
7. `STATELESS` trong demo tránh dùng HttpSession để khôi phục SecurityContext cho các request tiếp theo; Basic có thể được xác minh mỗi request. Đây **không phải điều kiện bắt buộc của DaoAuthenticationProvider**.
8. Không vô hiệu hóa CSRF vì tất cả endpoint demo là GET. Khi bổ sung POST/PUT/DELETE, phải thiết kế CSRF dựa trên loại client và credential transport.

**Lưu ý về bean wiring:** Khi ứng dụng chỉ có một UserDetailsService và PasswordEncoder phù hợp, Spring Security có thể tự kết nối provider cho luồng username/password thông dụng. Ví dụ này đăng ký tường minh để quan hệ phụ thuộc rõ ràng. Trong ứng dụng có nhiều provider/chain, phải xác định chúng được gắn vào AuthenticationManager và chain nào, tránh tạo hai cấu hình mâu thuẫn.

### 6.7. AccountController.java: quan sát Authentication kết quả

~~~java
package com.example.daodemo;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + authorities;
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

Controller **không gọi `loadUserByUsername`** và không kiểm tra password lại. Nó nhận Authentication đã được filter/provider xác minh. Không trả nguyên Authentication/UserDetails ra response vì principal có thể chứa password hash và metadata nội bộ.

Với dữ liệu của demo, endpoint `/me` trả tên và authorities ở dạng chuỗi để người học thấy được quyền. Production thường nên trả một public DTO khác và không công khai mọi authority nội bộ nếu client không cần.

### 6.8. Chạy bằng Gradle

Trong root project có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows PowerShell hoặc cmd:
gradlew.bat bootRun
~~~

Dùng terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u locked:locked123 http://localhost:8080/me
curl -i -u disabled:disabled123 http://localhost:8080/me
curl -i -u nobody:somepass http://localhost:8080/me
~~~

Kết quả dự kiến với đúng cấu hình ở trên, không có proxy hoặc custom error handler:

| Request | Status | Lý do hoặc body |
| --- | --- | --- |
| Anonymous GET `/public` | **200** | `public` |
| Anonymous GET `/me` | **401** | Basic entry point yêu cầu credential |
| Alice đúng password GET `/me` | **200** | `alice ROLE_USER,profile:read` |
| Admin đúng password GET `/admin` | **200** | `admin-only` |
| Alice vào `/admin` | **403** | Đã authenticated, thiếu ROLE_ADMIN |
| Alice sai password | **401** | `PasswordEncoder.matches` không chấp nhận |
| Locked đúng password | **401** | Account bị khóa |
| Disabled đúng password | **401** | Account bị vô hiệu hóa |
| Username không tồn tại | **401** | Lookup thất bại, không xác thực được |

Header `WWW-Authenticate` thường xuất hiện ở response HTTP Basic 401. Body của lỗi phụ thuộc entry point/error handling, không nên dựa vào một chuỗi body cố định. Các status này là **HTTP response**, không phải stdout của chương trình Java.

**Bảo mật credential:** Basic dùng Base64 cho username/password, không mã hóa bí mật. Luôn dùng HTTPS ngoài localhost, không hard-code password trong production và tránh đưa password thật vào shell history hoặc log.

## 7. Kiểm thử trực tiếp provider và qua HTTP Basic

Để chứng minh `UserDetailsService` và `PasswordEncoder` có trách nhiệm tách biệt, kiểm thử cả hai tầng:

- **Kiểm thử trực tiếp DaoAuthenticationProvider:** chủ động tạo UsernamePasswordAuthenticationToken, kiểm tra thành công và exception nội bộ.
- **MockMvc qua HTTP Basic:** kiểm tra filter/manager/provider/authorization kết hợp thành HTTP 200/401/403.

Tạo file `src/test/java/com/example/daodemo/DaoProviderTest.java`:

~~~java
package com.example.daodemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DaoProviderTest {

    @Autowired MockMvc mvc;
    @Autowired DaoAuthenticationProvider provider;
    @Autowired UserDetailsService users;
    @Autowired PasswordEncoder encoder;

    @Test
    void serviceLoadsHashButDoesNotCheckRawPassword() {
        UserDetails alice = users.loadUserByUsername("alice");

        assertEquals("alice", alice.getUsername());
        assertFalse(alice.getPassword().equals("alice123"));
        assertTrue(encoder.matches("alice123", alice.getPassword()));
        assertFalse(encoder.matches("wrong", alice.getPassword()));

        assertThrows(UsernameNotFoundException.class,
            () -> users.loadUserByUsername("nobody"));
    }

    @Test
    void providerAcceptsCorrectPasswordAndPopulatesAuthorities() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123"
            );

        assertFalse(request.isAuthenticated());
        assertTrue(request.getAuthorities().isEmpty());

        Authentication result = provider.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
            .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void providerRejectsWrongPasswordAndUnknownUsername() {
        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong"
                )
            ));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "nobody", "somepass"
                )
            ));
    }

    @Test
    void providerRejectsLockedAndDisabledAccounts() {
        assertThrows(LockedException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "locked", "locked123"
                )
            ));

        assertThrows(DisabledException.class,
            () -> provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "disabled", "disabled123"
                )
            ));
    }

    @Test
    void providerManagerErasesCredentialsOnSuccess() {
        ProviderManager manager = new ProviderManager(provider);

        Authentication result = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123"
            )
        );

        assertTrue(result.isAuthenticated());
        assertNull(result.getCredentials());
    }

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointNeedsValidCredentials() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER,profile:read"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void accountFlagsAndUnknownUserResultInUnauthorized() throws Exception {
        mvc.perform(get("/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("disabled", "disabled123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("nobody", "somepass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void loggedInUserMayStillLackAdminRole() throws Exception {
        mvc.perform(get("/admin").with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

### 7.1. Điều gì được kiểm tra?

- `serviceLoadsHashButDoesNotCheckRawPassword`: service trả **hash đã lưu**; `PasswordEncoder` mới kiểm tra raw password. Không tìm thấy username làm service ném UsernameNotFoundException.
- `providerAcceptsCorrectPasswordAndPopulatesAuthorities`: provider tạo Authentication đã xác thực với quyền có nguồn tin cậy.
- `providerRejectsWrongPasswordAndUnknownUsername`: khi gọi trực tiếp provider, sai password và unknown username mặc định đều có thể thành BadCredentialsException. Cần phân biệt exception nội bộ với response công khai.
- `providerRejectsLockedAndDisabledAccounts`: trạng thái của UserDetails có hiệu lực.
- `providerManagerErasesCredentialsOnSuccess`: phân biệt trách nhiệm xóa credential ở `ProviderManager` sau khi provider trả kết quả. **Không dựa vào getCredentials() luôn chứa raw password sau login**.
- HTTP test chứng minh Basic filter và provider kết hợp được, còn rule ADMIN xảy ra ở **authorization**.

**Lưu ý về test trực tiếp provider:** nếu gọi `provider.authenticate` mà không đi qua `ProviderManager`, đừng suy diễn việc xóa credentials giống luồng manager. Test thứ năm cố tình đi qua ProviderManager để kiểm tra ranh giới này.

**Kết quả test trong bài là kỳ vọng theo code.** Muốn tuyên bố build/test chạy thành công phải thực thi Gradle trên dự án thực tế với dependency và version tương ứng.

## 8. AuthenticationProvider, AuthenticationManager và SecurityFilterChain

Có ba cấp cấu hình dễ nhầm:

1. `DaoAuthenticationProvider` xác minh username/password nhờ service/encoder.
2. `ProviderManager` điều phối một hoặc nhiều AuthenticationProvider và trả Authentication kết quả.
3. `SecurityFilterChain` quyết định **filter nào** và **rule phân quyền nào** được áp dụng với request HTTP.

~~~text
SecurityFilterChain
    |
    +--> BasicAuthenticationFilter
    |       |
    |       +--> AuthenticationManager
    |               |
    |               +--> DaoAuthenticationProvider
    |                      +--> UserDetailsService
    |                      +--> PasswordEncoder
    |
    +--> AuthorizationFilter
           |
           +--> authenticated / hasRole / hasAuthority
~~~

**Sẽ là sai nếu chỉ khai báo UserDetailsService rồi giả định mọi request đều dùng provider đó.** Khi có custom manager, nhiều bean service, nhiều chain hoặc OAuth2 Resource Server, các request có thể sử dụng những provider khác nhau.

### 8.1. Khi nào cần khai báo provider bằng bean?

Đối với cấu hình username/password đơn giản, một UserDetailsService cùng PasswordEncoder có thể đủ để Spring Security tự cấu hình cơ chế DAO theo khả năng của framework và điều kiện auto-configuration. Khi cần:

- Đọc rõ provider nào được dùng.
- Thêm custom `UserDetailsPasswordService`.
- Thêm cache/tùy biến được hỗ trợ.
- Kết hợp nhiều AuthenticationProvider.
- Cấu hình riêng từng SecurityFilterChain.
- Đánh giá lỗi authentication hoặc migration phức tạp.

...thì khai báo `DaoAuthenticationProvider` tường minh có thể làm kiến trúc dễ kiểm soát và test hơn.

Không tự đặt một AuthenticationManager tùy biến mà bỏ qua những provider hiện có; việc đó có thể khiến HTTP Basic không hoạt động hoặc khiến provider khác bị bỏ quên.

### 8.2. Phân biệt 401, 403 và lỗi dữ liệu

| Tình huống | Tầng quyết định chính | HTTP thường gặp với Basic |
| --- | --- | --- |
| Không gửi credential vào endpoint protected | Authentication entry point | 401 |
| Username không có | UserDetailsService/Provider | 401 |
| Password sai | PasswordEncoder/Provider | 401 |
| Account disabled/locked | Account status checks/Provider | 401 |
| Password đúng, ROLE_USER truy cập ADMIN | AuthorizationManager | 403 |
| POST không có CSRF token khi bật CSRF | CsrfFilter | 403 |
| URL không có controller | Spring MVC | Có thể 404 sau khi qua security |
| Không có provider hỗ trợ token | ProviderManager | AuthenticationException; HTTP tùy entry point |

HTTP status và body còn phụ thuộc entry point, AccessDeniedHandler, filter chain, exception mapping và client. Không cho rằng mọi lỗi 401 đều do password sai hoặc mọi 403 đều do role.

## 9. PasswordEncoder: BCrypt và DelegatingPasswordEncoder

### 9.1. Băm khi lưu, matches khi xác thực

Với BCrypt:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String storedHash = encoder.encode("alice123");

boolean success = encoder.matches("alice123", storedHash);
boolean failure = encoder.matches("wrong", storedHash);
~~~

Đây là snippet trong chương trình có thư viện Spring Security và import phù hợp. **Giá trị logic dự kiến**: success là true, failure là false. `storedHash` không phải literal cố định vì BCrypt sinh salt.

Không dùng:

~~~java
// Sai: hai lần encode có thể có salt khác nhau.
encoder.encode("alice123").equals(storedHash);
~~~

Một BCrypt hash không phải chuỗi có thể giải mã ngược thành password.

### 9.2. DelegatingPasswordEncoder và prefix

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` thường dùng prefix thuật toán trong stored hash, ví dụ:

~~~text
{bcrypt}$2a$...
{pbkdf2}...
{scrypt}...
~~~

Đây là các **mẫu hình dạng**, không phải hash hợp lệ để copy vào database. Nếu service trả raw BCrypt hash kiểu `$2a$...` mà provider dùng DelegatingPasswordEncoder chờ `{bcrypt}`, quá trình matches có thể lỗi vì thiếu algorithm id. Ngược lại, nếu dữ liệu có prefix `{bcrypt}` mà encoder được chọn là BCryptPasswordEncoder thuần, cũng không nên giả định nó xử lý chuỗi như DelegatingPasswordEncoder.

**Encoder ở provider phải tương thích đúng định dạng hash tồn tại**, không chỉ “cùng tên BCrypt” theo cảm giác. Với migration, phải định nghĩa đường chuyển đổi, test dữ liệu cũ/mới và xử lý account có hash không hợp lệ một cách an toàn.

### 9.3. Vì sao không dùng NoOp hoặc hash nhanh?

Không lưu password plaintext, không dùng `NoOpPasswordEncoder` và không coi MD5/SHA-256 thuần là password storage an toàn. Password hashing nên dùng thuật toán có điều chỉnh chi phí phù hợp (BCrypt, Argon2, scrypt, PBKDF2 theo chính sách và khả năng hệ thống), quản lý salt và kế hoạch nâng cấp khi yêu cầu bảo mật thay đổi.

Tăng cost của BCrypt ảnh hưởng CPU/thời gian login; đánh giá theo tài nguyên và rủi ro brute-force, không chọn work factor tùy tiện. Hash an toàn cũng **không thay rate limiting, cảnh báo credential stuffing, MFA hoặc TLS**.

### 9.4. UserDetailsPasswordService và upgradeEncoding

DaoAuthenticationProvider có khả năng kết hợp `UserDetailsPasswordService` để cập nhật encoded password sau khi xác thực thành công khi encoder báo cần nâng cấp.

Concept:

~~~text
UserDetailsService
    -> tải storedHash cũ
PasswordEncoder.matches(raw, storedHash)
    -> true
PasswordEncoder.upgradeEncoding(storedHash)
    -> có thể true
UserDetailsPasswordService.updatePassword(user, newEncodedPassword)
    -> lưu hash mới theo cơ chế ứng dụng cung cấp
~~~

Đây là **mô hình khái niệm**, không phải khẳng định Spring Security tự sửa database chỉ vì có PasswordEncoder. Phải cung cấp UserDetailsPasswordService và transaction/update logic đúng; tránh race khi password vừa được đổi từ phiên khác. Đừng lưu password raw lại sau quá trình upgrade.

## 10. Đưa DaoAuthenticationProvider vào hệ thống dùng database

Trong production, `UserDetailsService` thường là adapter gọi Spring Data JPA repository.

Ví dụ một repository:

~~~java
// Snippet: cần AccountEntity, imports JpaRepository/Optional
// và Spring Data JPA dependency trong project thật.
public interface AccountJpaRepository
        extends JpaRepository<AccountEntity, Long> {

    Optional<AccountEntity> findByLoginName(String loginName);
}
~~~

Trong service:

~~~java
// Snippet nằm bên trong loadUserByUsername(...).
AccountEntity account = repository.findByLoginName(username)
    .orElseThrow(() ->
        new UsernameNotFoundException("Invalid credentials")
    );

return User.withUsername(account.getLoginName())
    .password(account.getPasswordHash())
    .authorities(resolveAuthorities(account))
    .disabled(!account.isEnabled())
    .accountLocked(account.isLocked())
    .build();
~~~

**resolveAuthorities(account)** là một hàm bạn phải hiện thực để ánh xạ role/permission từ dữ liệu thật. Đoạn trên không phải file hoàn chỉnh: cần entity, transaction strategy, imports, mapping, cấu hình repository và dependency JPA phù hợp.

Các yêu cầu quan trọng với database:

- **Khóa định danh login duy nhất:** tạo unique constraint phù hợp, nhất quán uppercase/lowercase và Unicode normalization theo chính sách. Với multi-tenant, cần cơ chế xác định tenant đáng tin cậy; chỉ tra theo username có thể nhầm user cùng tên ở tenant khác.
- **Hash lưu bền vững:** `UserDetailsService` đọc hash, không tái tạo hash mới trong mỗi lần login.
- **Trạng thái tài khoản:** ánh xạ enabled/locked/account expiration/credential expiration đúng chiều, không bỏ qua thuộc tính chưa có trong entity.
- **Authorities:** tránh N+1 hoặc lazy loading exception khi đọc roles; transaction/read query phải phù hợp. Đảm bảo `ROLE_ADMIN`/`ADMIN` thống nhất với rule.
- **Không leak entity:** UserDetails hoặc principal trả ra có thể chứa password hash. Controller nên trả DTO riêng.
- **Lỗi hạ tầng:** database timeout không đồng nghĩa username/password sai. Có cách logging/auditing nội bộ riêng, không che giấu sự cố database như thành công hoặc tự động chọn guest account.
- **Hiệu năng:** password hashing tốn CPU theo thiết kế; rate-limit và sizing login throughput phải được tính toán.

### 10.1. Account ID và tenant

`loadUserByUsername(String username)` chỉ nhận một chuỗi. Trong hệ thống nhiều tenant, username có thể không unique toàn cục. Cần xây dựng identity model rõ ràng, chẳng hạn username được chuẩn hóa theo tenant đã xác minh hoặc provider tùy chỉnh xử lý tenant context.

Không tin tenant ID do client gửi vào request body rồi truy vấn user tương ứng mà không xác minh phạm vi tenant. Việc một người login được không có nghĩa họ có quyền truy cập mọi tenant/resource.

## 11. Caching UserDetails và xóa credentials

`DaoAuthenticationProvider`/lớp cha có cơ chế `UserCache` và có thể tối ưu một số lần đọc account. Khi cache hoạt động, các kiểm tra credential vẫn phải bảo đảm không chấp nhận password sai chỉ vì account được cache.

Có ba sự thật cần nhớ:

1. **PasswordEncoder.matches phải kiểm tra credential hợp lệ**, kể cả khi UserDetails được lấy từ cache.
2. **ProviderManager** thông dụng xóa credentials nhạy cảm khỏi Authentication kết quả nếu object triển khai `CredentialsContainer`, nhờ thuộc tính `eraseCredentialsAfterAuthentication` mặc định bật.
3. Nếu cache giữ cùng tham chiếu UserDetails với principal trong Authentication, việc xóa password trên principal có thể ảnh hưởng dữ liệu cache. Cần thiết kế copy/invalidation đúng cách.

Đừng mặc định mỗi request chắc chắn đi vào `loadUserByUsername`: session đã đăng nhập hoặc JWT có thể không sử dụng service ở request sau; provider có cache cũng có thể thay đổi số lần truy cập database. Khi quyền/password/account status đổi, cần tính chuyện invalidation session, token và cache.

### 11.1. Provider không tự quản lý session

DaoAuthenticationProvider trả kết quả xác thực. Việc có lưu Authentication vào HttpSession hoặc không là trách nhiệm filter/security context strategy và `SessionCreationPolicy` của SecurityFilterChain. HTTP Basic có thể xác thực trên mỗi request; form login dùng session là một lựa chọn phổ biến.

`STATELESS` **không biến DaoAuthenticationProvider thành JWT provider**. Nếu dự án dùng Bearer JWT, resource server có cơ chế validate token riêng; không nên viết API nhận JWT rồi đưa chuỗi token vào password encoder.

### 11.2. Đổi mật khẩu có làm session cũ bị logout không?

Không mặc định. Session có thể giữ Authentication đã tạo khi login; token đã cấp có thể còn hiệu lực theo lifetime. Nếu nghiệp vụ đòi đổi mật khẩu sẽ thu hồi mọi session/token, phải triển khai invalidation, revocation hoặc revalidation theo thiết kế. Chỉ thay hash trong database chưa đủ để khẳng định mọi request đã đăng nhập sẽ bị chặn tức thì.

## 12. Xử lý lỗi, chống dò tài khoản và brute-force

### 12.1. Không lộ UsernameNotFoundException ra ngoài

Trong cấu hình thông dụng, không tìm thấy username và sai password thường được phản ánh ra client bằng thông tin credential không hợp lệ chung. Đây là biện pháp giúp giảm user enumeration, nhưng thời gian phản hồi, logs và rate-limit vẫn cần được thiết kế để tránh lộ trạng thái tài khoản.

Ví dụ response JSON đăng nhập do ứng dụng tự định nghĩa có thể dùng lỗi chung:

~~~json
{
  "error": "INVALID_CREDENTIALS"
}
~~~

Đây là **mẫu contract**, không phải body mặc định của mọi HTTP Basic response. Nếu dùng HTTP Basic, vẫn cần tuân thủ semantics của `WWW-Authenticate` khi phù hợp.

### 12.2. Khóa account và lỗi trạng thái

Trên API public, cân nhắc chính sách tránh tiết lộ “tên đăng nhập này tồn tại nhưng bị khóa” cho kẻ tấn công. Ở tầng nội bộ, kiểm thử exception riêng như `LockedException`/`DisabledException` có giá trị để chứng minh mapping đúng.

Không dùng dữ liệu `locked=false` hoặc `enabled=true` do client gửi trong request login để thay trạng thái account lưu trong nguồn tin cậy.

### 12.3. Rate limit, password spraying và MFA

PasswordEncoder làm chi phí đoán password offline cao hơn, nhưng không tự hạn chế tấn công online. Áp dụng theo threat model:

- Rate limiting theo principal/IP/device phù hợp, không khóa toàn bộ hệ thống chỉ vì một IP dùng chung.
- Audit các lần thử login thất bại mà không ghi raw password/token.
- Cảnh báo credential stuffing, password spraying và hành vi bất thường.
- MFA hoặc bước xác thực bổ sung cho hệ thống có rủi ro cao.
- Thay đổi password và phiên đăng nhập được xử lý với chính sách revocation rõ ràng.
- Bảo vệ endpoint đăng nhập và nguồn tài khoản khỏi denial-of-service do password hashing có chi phí CPU.

Đừng “chữa” các lỗi 401 bằng cách tắt PasswordEncoder hoặc chuyển sang plaintext password.

## 13. Các lỗi cấu hình hay gặp

### 13.1. Service trả plaintext thay vì hash

Nếu DB lưu password `"alice123"` nhưng provider dùng BCryptPasswordEncoder, `matches` không thể xác thực đúng như khi có BCrypt hash. Phải mã hóa khi lưu và chuyển dữ liệu cũ theo chính sách phù hợp; không dùng NoOp ở production để đối phó.

### 13.2. Service encode lại hash mỗi lần load

Sai:

~~~java
// Sai: account.getPasswordHash() vốn đã là hash.
.password(encoder.encode(account.getPasswordHash()))
~~~

Khi đó provider so khớp raw password với hash của hash, đăng nhập thất bại. Service chỉ cần `.password(account.getPasswordHash())`.

### 13.3. Encoder không cùng format dữ liệu lưu

BCryptPasswordEncoder thuần và DelegatingPasswordEncoder có quy tắc format khác nhau. Stored hash thiếu prefix phù hợp hoặc dùng algorithm id không hỗ trợ có thể làm toàn bộ login thất bại. Kiểm tra dữ liệu thực tế và version encoder.

### 13.4. Quên ánh xạ trạng thái `locked`

Database lưu `locked=true`, nhưng UserDetails phải biểu diễn `isAccountNonLocked=false`. Với `UserBuilder`, gọi `.accountLocked(account.isLocked())`; đừng đảo cờ hai lần.

### 13.5. Nghĩ provider tự quản lý quyền URL

Provider cấp authorities sau authentication, nhưng `.requestMatchers("/admin").hasRole("ADMIN")` là authorization rule của SecurityFilterChain. User có thể authenticated=true nhưng vẫn nhận 403.

### 13.6. Nghĩ tên user là role

Tài khoản username `"admin"` không tự có `ROLE_ADMIN`. Chỉ các GrantedAuthority đáng tin cậy mới đáp ứng `hasRole("ADMIN")` theo prefix mặc định.

### 13.7. Nhầm `getCredentials()` với hash lưu trong DB

Trong authentication request, credentials thường là raw password tạm thời. `UserDetails.getPassword()` mới là hash đã lưu. Sau xác thực, `ProviderManager` có thể xóa credentials; đừng lấy null làm login failure.

### 13.8. Thêm nhiều provider không rõ thứ tự

ProviderManager có thể có nhiều AuthenticationProvider. Khi nhiều provider hỗ trợ cùng token class, kết quả phụ thuộc thứ tự và behavior; có thể gây khó debug hoặc chính sách không mong muốn. Tách provider theo cơ chế xác thực rõ và kiểm thử request thật.

### 13.9. Tự tạo `UsernamePasswordAuthenticationToken.authenticated` từ input

Một token đã đánh dấu trusted không thay credential verification. Đừng nhận `role=ADMIN` từ client rồi tạo authenticated token; phải đưa unauthenticated request qua AuthenticationManager.

### 13.10. Nhầm 401 với 403

Password sai/username không có/locked thường là lỗi authentication và trả 401 khi dùng Basic. Đã login nhưng thiếu ROLE_ADMIN thường là 403. CSRF cũng có thể tạo 403 trước controller. Đọc log và filter chain thay vì sửa bừa service.

### 13.11. UserDetailsService không được gọi

Kiểm tra đúng filter chain, `httpBasic`/`formLogin` có bật không, `AuthenticationManager` và provider nào nhận request, có custom provider đang thay thế không, hoặc client thực tế gửi Bearer JWT thay vì Basic.

### 13.12. Principal chứa cả entity và password hash

Controller không nên trả nguyên UserDetails hoặc Authentication. Tạo DTO nhỏ và dùng account ID khi truy vấn theo owner/tenant.

### 13.13. Chỉ test trường hợp login đúng

Một bài test `200` không chứng minh chính sách bảo mật đúng. Cần thêm sai password, username không có, locked/disabled, thiếu role và request không có credential.

### 13.14. Viết custom AuthenticationProvider khi không cần

Nếu use case đơn giản là username/password + database, `DaoAuthenticationProvider` đã giải quyết cơ chế chuẩn. Tùy biến provider quá mức có thể bỏ sót kiểm tra trạng thái, xóa credentials, chống user enumeration, upgrade hash hoặc event xử lý phù hợp.

## 14. Debug luồng xác thực theo từng chặng

Khi ứng dụng nhận 401/403, kiểm tra có thứ tự:

1. **HTTP request có credential đúng loại?** Basic Authorization header, form login username/password, hay Bearer token?
2. **Request khớp SecurityFilterChain nào?** Có matcher và @Order nào khiến request đi vào chain khác không?
3. **Authentication filter có bật?** `httpBasic`, `formLogin` hoặc resource server config có tương ứng loại credential?
4. **AuthenticationManager có DaoAuthenticationProvider không?** Nếu có nhiều provider, thứ tự và `supports()` ra sao?
5. **Bean UserDetailsService nào được provider dùng?** Có bean mặc định, custom manager hoặc nhiều service gây mơ hồ?
6. **Lookup có trả đúng account?** Username normalized, tenant, account unique và transaction có phù hợp?
7. **Password hash có đúng format?** `$2a$...` hay `{bcrypt}$2a$...` và encoder tương ứng?
8. **PasswordEncoder.matches có được gọi với đúng raw/hash?** Không encode lại hash hoặc so sánh chuỗi trực tiếp.
9. **Bốn trạng thái UserDetails có hợp lệ?** Disabled, locked, accountExpired, credentialsExpired?
10. **Authentication thành công nhưng quyền sai?** Kiểm tra authorities, ROLE_ prefix, endpoint rule và owner/tenant.
11. **Session hoặc JWT cũ vẫn được truy cập?** Chính sách invalidation/revocation/revalidation đã được triển khai chưa?
12. **401/403 do filter khác?** CSRF, CORS preflight, error dispatch và entry point có thể thay đổi kết quả.

Ở môi trường phát triển có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log DEBUG giúp hiểu những chain/filter nào được chọn, nhưng không bảo đảm mọi giá trị nội bộ đều có trong log. **Không log raw password, Authorization header, access token, cookie, password hash hoặc credential bất kỳ**.

### 14.1. Kiểm thử trực tiếp khác với kiểm thử HTTP

- **Direct provider test** cho thấy exception nội bộ và cách provider phối hợp service/encoder.
- **MockMvc HTTP test** cho thấy filter, manager/provider và authorization tạo response thực tế.
- **Service/JPA test** xác nhận lookup, unique identity, mapping trạng thái và quyền theo schema.
- **Security policy test** xác nhận principal đã đăng nhập có đúng quyền trên resource/tenant.

Không lấy một unit test PasswordEncoder.matches thành bằng chứng toàn bộ endpoint đã an toàn.

## 15. Bài tập kiểm tra kiến thức

**Câu 1.** DaoAuthenticationProvider lấy UserDetails từ đâu?

**Đáp án:** Từ UserDetailsService được cấu hình, thường tìm account bằng `loadUserByUsername(username)`.

**Câu 2.** UserDetailsService có nhận raw password để tự xác thực không?

**Đáp án:** Không. Nó nhận username và trả UserDetails chứa encoded password, authorities và trạng thái. DaoAuthenticationProvider dùng PasswordEncoder để kiểm tra credential.

**Câu 3.** Vì sao dùng `encoder.encode(raw).equals(storedHash)` dễ sai với BCrypt?

**Đáp án:** BCrypt dùng salt nên cùng password có thể có hash khác nhau. Dùng `encoder.matches(raw, storedHash)`.

**Câu 4.** Account có password đúng nhưng `isAccountNonLocked()==false` sẽ được đăng nhập không?

**Đáp án:** Không với DaoAuthenticationProvider thông dụng; account bị khóa bị từ chối.

**Câu 5.** Lookup username không có, nên service trả null hay ném exception?

**Đáp án:** Ném `UsernameNotFoundException`. Không tạo account giả hoặc trả null.

**Câu 6.** Tại sao HTTP Basic có thể trả 401 cho cả password sai lẫn username không tồn tại?

**Đáp án:** Xác thực thất bại; provider có cơ chế che chi tiết unknown user bằng lỗi credential chung để hạn chế enumeration. Entry point thể hiện lỗi phù hợp cho client.

**Câu 7.** UserDetails của alice có ROLE_USER, nhưng `/admin` yêu cầu ROLE_ADMIN. DaoAuthenticationProvider có sai không khi `/admin` trả 403?

**Đáp án:** Không. Authentication có thể đúng; authorization từ chối vì thiếu quyền.

**Câu 8.** `new DaoAuthenticationProvider(userDetailsService)` có tự biết password encoder mà database đang dùng không?

**Đáp án:** Không nên đoán. Cấu hình `setPasswordEncoder` tương thích với định dạng stored hash và kiểm thử dữ liệu thật.

**Câu 9.** Nếu DB lưu `locked=true`, builder UserDetails cần nhận giá trị gì?

**Đáp án:** `.accountLocked(true)`, tương ứng UserDetails có `isAccountNonLocked()==false`.

**Câu 10.** Sau login, `Authentication.getCredentials()==null` có nghĩa provider không dùng password?

**Đáp án:** Không. ProviderManager thường xóa credentials sau khi xác thực thành công.

**Câu 11.** Đổi role trong database có khiến authorities trong session/JWT đang cấp cập nhật ngay không?

**Đáp án:** Không mặc định. Cần session/token/cache invalidation hoặc revalidation nếu chính sách yêu cầu hiệu lực tức thì.

**Câu 12.** Resource Server JWT có bắt buộc gọi DaoAuthenticationProvider để xác minh Bearer token không?

**Đáp án:** Không. JWT có provider/decoder và cơ chế xác thực riêng. DaoAuthenticationProvider chủ yếu dành cho username/password.

**Câu 13.** Vì sao direct test `provider.authenticate` và HTTP test MockMvc đều hữu ích?

**Đáp án:** Direct test phân biệt lookup, matches và exception; HTTP test chứng minh filter/manager/provider/authorization tạo status đúng trên request thật.

**Câu 14.** Vì sao một Custom AuthenticationManager có thể làm UserDetailsService không được gọi dù có @Service bean?

**Đáp án:** Request có thể được chuyển cho provider khác hoặc manager chưa đăng ký DaoAuthenticationProvider. Cần kiểm tra wiring và chain được chọn.

**Câu 15.** Nếu chỉ muốn cho phép một user đọc hóa đơn của họ, có thể chỉ dùng authorities `invoice:read` không?

**Đáp án:** Chưa đủ. Còn phải kiểm tra ownership, tenant, trạng thái hóa đơn và những ràng buộc domain.

## 16. Tài liệu tham khảo chính thức

- Spring Security 6.5 — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — **UserDetailsService**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html
- Spring Security — **Username/Password Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — **Password Storage**: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 API — **DaoAuthenticationProvider**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 API — **ProviderManager**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

**Ghi nhớ:** `UserDetailsService` **tìm account và trả hash/quyền/trạng thái**; `PasswordEncoder` **kiểm tra raw password với hash**; `DaoAuthenticationProvider` **phối hợp hai thành phần, kiểm tra account và tạo Authentication đã xác thực**; `ProviderManager` **điều phối provider**; filter **đặt kết quả vào SecurityContext**; authorization **quyết định được phép làm gì**. Hiểu ranh giới ấy giúp thay in-memory repository bằng JPA, nâng cấp hash và debug lỗi login mà không trộn lẫn trách nhiệm.
