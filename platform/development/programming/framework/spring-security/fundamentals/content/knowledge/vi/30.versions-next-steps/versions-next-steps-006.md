# Học sâu xác thực, mật khẩu và tích hợp nguồn tài khoản

## 1. Mục tiêu và vị trí trong lộ trình

Sau phần nền tảng Spring Security, bước học sâu này giúp trả lời ba câu hỏi thực tế: **ai đang đăng nhập**, **ứng dụng kiểm tra và lưu thông tin xác thực ra sao**, và **danh tính người dùng đến từ hệ thống nào**. Kết quả cần đạt không chỉ là mở được trang đăng nhập, mà còn hiểu luồng xác thực, lựa chọn cơ chế lưu mật khẩu phù hợp, kết nối nguồn tài khoản và kiểm thử được các trường hợp thất bại.

Phạm vi trọng tâm là **Spring Security cho ứng dụng Servlet/Spring MVC**. Ví dụ chạy bằng **Java 17 và Spring Boot 3.5.x (Spring Security 6.x)**; khi chuyển sang Boot 4/Spring Security 7, cần đọc hướng dẫn migration tương ứng và kiểm tra lại dependency, DSL, hành vi mặc định. Các nguyên tắc như `SecurityFilterChain`, `AuthenticationManager`, `PasswordEncoder`, phân biệt LDAP với OIDC vẫn là kiến thức cốt lõi. Ứng dụng WebFlux/reactive dùng các API và filter chain khác, không được sao chép nguyên cấu hình Servlet.

**Điểm hoàn thành:** tự giải thích được luồng form login và HTTP Basic; biết mã hóa mật khẩu để lưu, xác thực và nâng cấp hash; thay nguồn người dùng in-memory bằng cơ sở dữ liệu; chọn đúng hướng khi tổ chức dùng LDAP hoặc nhà cung cấp danh tính; thiết kế kiểm thử, logging và xử lý lỗi an toàn.

## 2. Xác thực không đồng nghĩa với phân quyền

- **Authentication (xác thực):** kiểm chứng một chủ thể là ai. Ví dụ, tài khoản `learner` cung cấp mật khẩu đúng hoặc một hệ thống IdP phát hành kết quả đăng nhập hợp lệ.
- **Authorization (phân quyền):** sau khi xác thực, quyết định chủ thể ấy có quyền thực hiện thao tác hay không. Người dùng đăng nhập thành công vẫn có thể bị từ chối `/admin`.
- **Principal:** danh tính đang được biểu diễn sau xác thực; với đăng nhập mật khẩu thường là `UserDetails`, với OIDC có thể là `OidcUser`, với resource server JWT thường là `Jwt`.
- **Credentials:** bí mật/bằng chứng dùng cho quá trình xác thực. Mật khẩu thô phải tồn tại trong bộ nhớ càng ngắn càng tốt; không log, lưu session hay trả về API.
- **Authorities/roles:** quyền gắn trên `Authentication`. `hasRole("ADMIN")` thường tương đương kiểm tra authority `ROLE_ADMIN`; `hasAuthority("SCOPE_read")` kiểm tra đúng tên authority, không tự thêm tiền tố.

Một request chưa xác thực có thể nhận **401** (đặc biệt với HTTP Basic/API) hoặc được **302** đến form login (trình duyệt). Request đã xác thực nhưng thiếu quyền thường nhận **403**. Đầu ra thực tế phụ thuộc cơ chế xác thực, content negotiation và cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler`; đừng suy ra mọi request chưa đăng nhập luôn trả cùng một mã.

## 3. Theo dấu luồng xác thực trong Spring Security

Sơ đồ khái niệm cho form login hoặc HTTP Basic:

```text
HTTP request
  -> servlet SecurityFilterChain
  -> bộ lọc đọc thông tin xác thực
  -> Authentication (chưa được xác thực)
  -> AuthenticationManager, thường là ProviderManager
  -> AuthenticationProvider phù hợp
       -> DaoAuthenticationProvider
          -> UserDetailsService tải user, hash, trạng thái, quyền
          -> PasswordEncoder.matches(rawPassword, storedHash)
  -> Authentication (thành công, chứa principal và authorities)
  -> SecurityContext, được SecurityContextHolder giữ trong request
  -> kiểm tra authorization -> controller hoặc 403
```

**Vai trò cần phân biệt:**

| Thành phần | Nhiệm vụ | Sai lầm hay gặp |
|---|---|---|
| `SecurityFilterChain` | Chọn bộ lọc và luật bảo vệ HTTP request | Cho rằng chỉ cần viết controller `/login` là Spring tự bảo vệ toàn bộ ứng dụng |
| `AuthenticationManager` | Nhận yêu cầu xác thực, trả `Authentication` hoặc ném lỗi | Tự gọi manager trong mọi controller dù framework đã có filter phù hợp |
| `ProviderManager` | Điều phối một hoặc nhiều `AuthenticationProvider` | Đăng ký provider chồng chéo, không rõ cái nào xử lý token nào |
| `DaoAuthenticationProvider` | Xác thực username/password bằng user details và encoder | Tự viết so sánh mật khẩu dạng chuỗi |
| `UserDetailsService` | **Tải** người dùng theo username | Nghĩ rằng service này trực tiếp kiểm tra mật khẩu |
| `PasswordEncoder` | `encode` và `matches` mật khẩu một chiều | Dùng MD5/SHA-256 thuần, hoặc so sánh hash bằng `equals` |
| `SecurityContextHolder` | Truy cập ngữ cảnh xác thực hiện tại | Dùng `ThreadLocal` tùy tiện qua async task và tưởng context tự lan truyền |

Với đăng nhập form, Spring thường sử dụng session để duy trì trạng thái giữa các request; với HTTP Basic, client gửi credential ở từng request (chỉ an toàn khi dùng HTTPS). Với bearer token, ứng dụng có thể xác thực từng request mà không dùng session login truyền thống. `SecurityContext` là ngữ cảnh của request hiện tại; việc lưu và tải lại qua request phụ thuộc `SecurityContextRepository` và cơ chế session/token đã cấu hình.

Đường đi khi thất bại: sai mật khẩu, tài khoản disabled/locked/expired, nguồn tài khoản không truy cập được, token không đúng audience/issuer hoặc thiếu authority là **những nguyên nhân khác nhau**, cần phân biệt trong logs/metrics nội bộ nhưng phản hồi cho client phải hạn chế tiết lộ thông tin.

## 4. Mật khẩu: hash, salt, work factor và nâng cấp dần

Mật khẩu dùng để đăng nhập **không lưu ở dạng plaintext và không mã hóa đối xứng để giải mã lại**. Lưu **hash một chiều có salt và thuật toán thích ứng**: bcrypt, PBKDF2, scrypt hoặc Argon2. Thuật toán thích ứng có tham số chi phí (work factor) để làm các cuộc thử mật khẩu hàng loạt tốn tài nguyên hơn. Chọn chi phí bằng benchmark trên hạ tầng thực tế, cân bằng độ trễ và khả năng chống tấn công; không sao chép máy móc một mức cố định cho mọi hệ thống.

Spring Security cung cấp `PasswordEncoder` và `DelegatingPasswordEncoder`:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("study-only-123"); // ví dụ, không ghi ra log
boolean ok = encoder.matches("study-only-123", stored); // true
boolean wrong = encoder.matches("incorrect", stored);  // false
```

Đây là **đoạn minh họa** chạy trong một dự án đã có dependency Spring Security; không phải chương trình Java độc lập. `stored` thường có dạng `{bcrypt}$2a$...`: tiền tố `{id}` giúp `DelegatingPasswordEncoder` chọn bộ kiểm tra tương ứng. Mỗi lần `encode` có thể tạo hash khác nhau vì salt, nên không được lấy `encoder.encode(raw).equals(stored)` để xác thực. Gọi `matches(raw, stored)`.

Quy trình đúng:

1. **Đăng ký:** kiểm tra chính sách mật khẩu và chống abuse; `encode` **một lần** trước khi lưu; ghi hash, không ghi password thô.
2. **Đăng nhập:** tải user, kiểm tra trạng thái, gọi `matches`; nếu thành công mới thiết lập phiên xác thực theo cơ chế phù hợp.
3. **Đổi mật khẩu:** xác thực lại khi cần, kiểm tra mật khẩu cũ, ghi hash mới, cân nhắc thu hồi session/token cũ theo mức rủi ro.
4. **Quên mật khẩu:** gửi token một lần qua kênh đã xác minh, có thời hạn ngắn và chỉ được sử dụng một lần; chỉ lưu dạng băm của reset token nếu lưu trong DB; không gửi mật khẩu cũ.
5. **Nâng cấp hash:** khi đăng nhập thành công, có thể dùng `PasswordEncoder.upgradeEncoding` và tích hợp `UserDetailsPasswordService`/luồng cập nhật phù hợp để ghi hash mới. Cần xử lý đồng thời và không ghi đè một mật khẩu vừa được đổi.
6. **Di chuyển dữ liệu cũ:** phân loại hash đang lưu; prefix `{id}` chỉ khi biết chắc thuật toán thực tế. Thông báo lỗi `There is no PasswordEncoder mapped for the id "null"` thường cho thấy hash thiếu tiền tố phù hợp. Không chữa bằng cách bật `{noop}` cho dữ liệu thật.

**Ghi nhớ:** không dùng `NoOpPasswordEncoder` hoặc `User.withDefaultPasswordEncoder()` cho production; không dùng một hash nhanh như SHA-256 thuần để lưu mật khẩu; không tự tạo salt hoặc thuật toán hash khi thư viện đã hỗ trợ.

## 5. Phòng thí nghiệm Java 17: xác thực bằng tài khoản in-memory

Bài thực hành này cố ý dùng một người dùng demo để quan sát rõ luồng. Không đưa credential demo, endpoint thử nghiệm hoặc `InMemoryUserDetailsManager` nguyên dạng vào production.

Tạo Maven project với cấu trúc:

```text
security-lab/
  pom.xml
  src/main/java/com/example/securitylab/SecurityLabApplication.java
```

**`pom.xml`** — dùng Spring Boot 3.5.0 để có một phiên bản cố định cho ví dụ; bản dựng ứng dụng thực tế phải theo BOM và bản vá bảo mật đang được hỗ trợ.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/securitylab/SecurityLabApplication.java`** — lớp Java 17 đầy đủ, có `main` và các bean cần thiết:

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var learner = User.withUsername("learner")
            .password(encoder.encode("study-only-123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "Hello, " + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "ADMIN";
    }
}
```

**Chạy** ở thư mục `security-lab` khi có JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Mở terminal khác để thử:

```bash
curl -i http://localhost:8080/public
curl -i -u learner:study-only-123 http://localhost:8080/profile
curl -i -u learner:wrong http://localhost:8080/profile
curl -i -u learner:study-only-123 http://localhost:8080/admin
```

Kết quả dự kiến theo thứ tự: **200** với thân `PUBLIC`; **200** với `Hello, learner`; **401** cho HTTP Basic sai mật khẩu; **403** cho người dùng đã xác thực nhưng không có role `ADMIN`. Khi mở `/profile` trên trình duyệt chưa đăng nhập, có thể thấy chuyển hướng đến trang login mặc định. Mật khẩu demo trong mã chỉ để học; production lấy bí mật từ nguồn cấu hình an toàn và thường quản lý người dùng bằng DB/IdP.

**Giải thích:** `UserDetailsService` cung cấp một tài khoản có `ROLE_USER`; `PasswordEncoder` tạo hash tương thích với provider; Spring Security dùng filter và manager để kiểm tra password; `SecurityFilterChain` quyết định `/public` là công khai, `/profile` cần xác thực và `/admin` yêu cầu role khác. Form login giữ phiên trình duyệt; HTTP Basic tiện quan sát bằng curl nhưng client phải gửi credential mỗi lần, nên chỉ dùng qua TLS.

**Cần thử thêm:** thêm user role `ADMIN`; thay `hasRole("ADMIN")` thành `hasAuthority("ROLE_ADMIN")` và giải thích sự tương đương; tạo `POST` rồi quan sát CSRF mặc định thay vì tự động `csrf.disable()`.

## 6. Chuyển từ người dùng demo sang nguồn tài khoản thực

Đừng gom mọi hệ thống danh tính vào một `UserDetailsService`. Nguồn dữ liệu và **giao thức xác thực** quyết định adapter nào phù hợp:

| Nguồn/cơ chế | Tích hợp thường dùng | Nơi kiểm chứng credential | Khi nào chọn |
|---|---|---|---|
| In-memory | `InMemoryUserDetailsManager` | Ứng dụng, qua `PasswordEncoder` | Demo, test, prototype |
| Bảng JDBC chuẩn của Spring | `JdbcUserDetailsManager` | Ứng dụng so mật khẩu với hash từ DB | Schema chuẩn, yêu cầu gọn |
| DB nghiệp vụ/JPA | `UserDetailsService` tùy biến + repository | Ứng dụng so với hash lưu trong bảng user | Đã có schema, role và trạng thái riêng |
| LDAP/Active Directory | LDAP authentication provider, thường là bind | Directory server | Người dùng doanh nghiệp quản lý tập trung |
| Google/Keycloak/Okta/... qua OIDC | `oauth2Login`, `OidcUserService`/mapping khi cần | Identity Provider (IdP) | Đăng nhập liên kết/SSO |
| API nhận access token JWT | OAuth2 Resource Server | API kiểm chữ ký, issuer, expiry, audience của token | Bảo vệ API; **không tự tạo kho password** |

### 6.1. Database: nắm rõ ranh giới giữa domain và Spring Security

Với tài khoản nội bộ, thiết kế bảng tối thiểu thường có `id`, `login` có unique index, `password_hash`, `enabled`, trạng thái khóa/hết hạn, và quan hệ role/permission. Repository chỉ **đọc** bản ghi; adapter `UserDetailsService` chuyển thành `UserDetails`; `DaoAuthenticationProvider` xử lý phần so khớp password.

Ví dụ **đoạn adapter minh họa**, giả định ứng dụng đã tự định nghĩa `AccountRepository`, `Account` với các phương thức thể hiện trong mã:

```java
@Service
public class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository accounts;

    public AccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String login) {
        Account a = accounts.findByLogin(login)
            .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));
        return User.withUsername(a.login())
            .password(a.passwordHash())
            .disabled(!a.enabled())
            .authorities(a.authorities().toArray(String[]::new))
            .build();
    }
}
```

Cần import các type Spring Security/Spring Framework tương ứng; đoạn này **không biên dịch độc lập** vì repository và entity phụ thuộc schema dự án. Quan trọng là `passwordHash()` trả **hash đã lưu**, không encode lại khi tải user. `authorities()` phải trả tên đã được chuẩn hóa, ví dụ `ROLE_USER` hoặc permission riêng; không gán `ROLE_ADMIN` chỉ vì client truyền tham số `role=ADMIN`. Xử lý tên đăng nhập case-sensitivity, khóa tài khoản, cache và việc thu hồi quyền theo chính sách nhất quán.

`JdbcUserDetailsManager` phù hợp khi dùng cấu trúc SQL mặc định/đã cấu hình query thích hợp; nó **không tự biết** schema doanh nghiệp tùy ý. Với JPA, định nghĩa repository và mối quan hệ role sao cho truy cập hiệu quả, tránh lỗi lazy loading ngoài transaction và N+1 query; kiểm tra plan/index khi số lượng account lớn.

### 6.2. LDAP: xác thực bằng bind, không lấy hash từ directory để so

Khi dùng LDAP bind, ứng dụng gửi username/password đến directory thông qua kết nối bảo vệ và directory thực hiện phép xác thực. **LDAP bind không dựa vào `UserDetailsService` để lấy password hash**; đây là khác biệt quan trọng với `DaoAuthenticationProvider`. Học về distinguished name (DN), user search base/filter, group-to-authority mapping, referral, timeouts, LDAPS/StartTLS và bảo vệ mật khẩu của tài khoản service. Nếu LDAP bị gián đoạn, chính sách fallback phải rõ ràng; không được âm thầm chấp nhận đăng nhập từ dữ liệu cache không đủ tin cậy.

### 6.3. SSO/OIDC: danh tính do IdP xác thực

Với Spring Security OAuth2 Client và cấu hình `ClientRegistration`, bật `oauth2Login(withDefaults())`. Trong flow OIDC, ứng dụng chuyển người dùng đến IdP, nhận authorization code, đổi lấy token qua back-channel và xác minh dữ liệu danh tính. **Không thu mật khẩu Google/Keycloak của người dùng vào form nội bộ**. Cấu hình redirect URI chính xác; client secret phải ở secret manager/env được kiểm soát; OIDC cần xác minh `issuer`, `audience` và các điều kiện theo flow, thường dùng claims `iss` + `sub` làm định danh liên kết ổn định.

Phân biệt ba vai trò:

- **OAuth2 Login client:** đăng nhập người dùng vào ứng dụng web; kết quả có thể được lưu trong HTTP session.
- **OAuth2 Resource Server:** kiểm chứng bearer access token khi gọi API; phải xác minh chữ ký, `iss`, `exp`/`nbf` và `aud` thích hợp; scope có thể ánh xạ sang `SCOPE_*`.
- **Authorization Server/IdP:** phát hành token và thực hiện các luồng ủy quyền/xác thực. Thêm `oauth2Login` hoặc `oauth2ResourceServer` vào một ứng dụng **không tự biến ứng dụng thành Authorization Server**.

Nếu phải liên kết tài khoản cục bộ với danh tính ngoài, lưu khóa duy nhất như `(issuer, subject)`; áp dụng chính sách nối tài khoản có xác minh và consent phù hợp. Email có thể thay đổi hoặc chưa được xác minh; **không tự nối hai tài khoản chỉ vì email giống nhau**. Phân biệt **đăng nhập** (authentication), **cấp tài khoản/provisioning**, **đồng bộ hồ sơ** và **cấp quyền ứng dụng**; chúng không phải cùng một thao tác.

### 6.4. Khi có nhiều nguồn tài khoản

Trước khi cấu hình nhiều provider, viết rõ:

1. Username/tenant/realm nào thuộc nguồn nào? Có trùng username hay không?
2. Ai chịu trách nhiệm kiểm chứng credential? Local DB, LDAP hay IdP?
3. Sau khi xác thực, authority nội bộ được tính từ đâu, có cache hay không và hết hạn khi nào?
4. Khi user bị disabled, chuyển bộ phận hoặc bị thu hồi quyền ở nguồn gốc, ứng dụng sẽ phản ánh sau bao lâu?
5. Luồng account linking, logout và thu hồi session/token có được thiết kế riêng cho từng nguồn?

Chỉ thêm custom `AuthenticationProvider` khi giao thức thực sự không khớp những cơ chế Spring Security đã hỗ trợ. Nếu nhiều provider hỗ trợ cùng loại `Authentication`, xác định thứ tự, điều kiện lựa chọn và cách xử lý lỗi để tránh fallback không an toàn.

## 7. Vận hành an toàn và xử lý ca khó

**Bề mặt đăng nhập.** Dùng HTTPS cho toàn bộ trao đổi credential/token; giới hạn tốc độ theo tài khoản và tín hiệu mạng, phát hiện credential stuffing, giữ phản hồi đăng nhập đủ trung tính để giảm user enumeration. Theo dõi tỷ lệ 401, 403, lockout, lỗi IdP/LDAP và latency hash; tránh log mật khẩu, token, cookie, authorization header hoặc hash nhạy cảm.

**Session và CSRF.** Với web dùng cookie/session, giữ CSRF protection cho hành động thay đổi trạng thái, cookie `HttpOnly`, `Secure` và `SameSite` phù hợp, rotation/session-fixation protection và logout rõ ràng. CSRF là vấn đề khác với CORS; **CORS không thay thế xác thực hay CSRF**. Với API bearer token, xác định cách client lưu token, chống XSS, token expiry/refresh/revocation, không tắt CSRF chung chỉ vì có một endpoint API.

**Trạng thái account.** Disabled, locked, expired, credential expired và việc thiếu quyền là các khái niệm riêng. Không trả chi tiết “email tồn tại nhưng disabled” cho phía chưa xác thực; log nội bộ nên dùng mã lý do an toàn. Kiểm thử concurrency khi đổi mật khẩu hoặc thu hồi role.

**Hiệu năng.** Hash thích ứng cố ý tốn CPU/RAM; thiết lập work factor dựa trên benchmark và mức tải thực tế, tránh gọi password verification trên mọi request nếu cơ chế session/token đã thích hợp. Với nguồn DB/LDAP/IdP, cấu hình timeout, pool, circuit-breaker theo kiến trúc và quản lý cache/TTL để tránh quyền cũ.

**Trách nhiệm phân quyền.** `@PreAuthorize`, matcher HTTP và các rule ở service phải nhất quán. Đã xác thực không có nghĩa được quyền xem mọi bản ghi; kiểm tra ownership/tenant ở lớp nghiệp vụ. Test cả truy cập ngang hàng (IDOR) và quyền đổi role.

## 8. Lộ trình thực hành có tiêu chí nghiệm thu

| Giai đoạn | Việc cần làm | Minh chứng đạt |
|---|---|---|
| A. Theo dấu xác thực | Chạy demo; đặt breakpoint ở filter/provider, quan sát `Authentication` trước và sau đăng nhập | Giải thích đúng principal, credentials, authorities, 200/401/403/302 |
| B. Quản trị mật khẩu | Viết register/login/change-password an toàn, hash bằng `DelegatingPasswordEncoder`, thêm bài test sai mật khẩu và hash legacy | DB không có plaintext; `matches` đúng; lỗi hash format có cách xử lý có kiểm soát |
| C. Tích hợp nguồn | Thay in-memory bằng DB thật; sau đó dựng LDAP test server hoặc OIDC sandbox | Đăng nhập thành công/thất bại, disabled, role mapping và nguồn gốc identity đều có test |
| D. Hardening & migration | Bổ sung CSRF/session, rate limit, audit an toàn, token/role revocation, migration hash | Có test tích hợp, checklist giám sát và kế hoạch rollback khi đổi cơ chế xác thực |

Bài tập nên làm theo thứ tự:

1. **In-memory → JDBC/JPA:** tạo 2 tài khoản `reader`/`admin`, lưu hash, ràng buộc unique login; người dùng hợp lệ có quyền đúng, sai mật khẩu không vào được.
2. **Phân quyền theo nghiệp vụ:** `/profile` cho người đã đăng nhập; `/admin` chỉ dành cho `ROLE_ADMIN`; thêm case một user cố truy cập dữ liệu của user khác.
3. **Đổi/reset mật khẩu:** test token hết hạn, tái sử dụng, hash mới và invalidation của session.
4. **Directory hoặc OIDC:** chọn **một** cơ chế ngoài theo yêu cầu thực tế, cấu hình sandbox, map authority và thử khi nguồn bị từ chối/không sẵn sàng.
5. **Kiểm thử tự động:** dùng `spring-security-test` với `@WithMockUser` hoặc MockMvc request post-processors khi kiểm tra authorization; thêm integration test xác thực thật để không chỉ mock kết quả provider. Đối với POST có CSRF, dùng `with(csrf())` trong test hoặc gửi token CSRF hợp lệ từ client.

Tối thiểu cần bao phủ bảng ca kiểm thử:

| Đầu vào | Kết quả mong đợi |
|---|---|
| Anonymous vào tài nguyên bảo vệ | Chuyển login hoặc 401, theo cơ chế đã cấu hình |
| Username/password đúng, account enabled | `Authentication` thành công, gắn đúng authorities |
| Sai password hoặc account không tồn tại | Không đăng nhập; thông báo public không tiết lộ account |
| Disabled/locked/expired | Bị từ chối theo chính sách |
| User thiếu role truy cập admin | 403 sau khi đã xác thực |
| Hash cũ hợp lệ | Được xác thực bằng encoder tương ứng, có lộ trình nâng cấp |
| LDAP/IdP lỗi hoặc token hết hạn/sai issuer/audience | Không cấp phiên/quyền không hợp lệ |
| Đổi mật khẩu/thu hồi quyền/đăng xuất | Hiệu lực session/token/cached authorities phù hợp chính sách |

## 9. Tự kiểm tra hiểu bài

**Vì sao `UserDetailsService` không phải “hàm login”?** Nó chịu trách nhiệm tải user để một provider phù hợp kiểm tra credential và tạo `Authentication`; mô hình LDAP bind và OIDC dùng luồng khác.

**Tại sao hai lần encode cùng một mật khẩu cho ra chuỗi khác nhau?** Thuật toán có salt ngẫu nhiên; dùng `matches` để đối chiếu password thô với hash đã lưu.

**`hasRole("ADMIN")` khác gì `hasAuthority("ADMIN")`?** `hasRole` thường kiểm tra `ROLE_ADMIN`; `hasAuthority` so chính xác chuỗi. Kiểm tra cấu hình prefix và authority mapping trong ứng dụng.

**Khi ứng dụng nhận JWT từ IdP, có phải đang triển khai trang đăng nhập OAuth2?** Không nhất thiết. Resource Server xác minh access token của request API; OAuth2/OIDC Login dùng flow đăng nhập người dùng vào ứng dụng.

**Khi nhân viên bị vô hiệu hóa trên LDAP/IdP, quyền ở ứng dụng biến mất ngay không?** Phụ thuộc session, token lifetime, cache và cơ chế đồng bộ/thu hồi. Cần chính sách và test, không được giả định tự động tức thời.

## 10. Tài liệu chính thức để học tiếp

- [Servlet Authentication Architecture — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Username/Password Authentication, UserDetailsService, JDBC, LDAP — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Password Storage và DelegatingPasswordEncoder — Spring Security](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [LDAP Authentication — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [OAuth2 Login và OIDC — Spring Security](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [OAuth2 Resource Server — Spring Security](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Testing CSRF với MockMvc — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot system requirements và migration](https://docs.spring.io/spring-boot/reference/)

Sau các bài thực hành, người học cần mô tả được **nguồn sự thật của danh tính**, **cách xác thực credential**, **cách cấp và thu hồi authority**, **vòng đời mật khẩu/session/token** và **bằng chứng kiểm thử** cho chính ứng dụng của mình.