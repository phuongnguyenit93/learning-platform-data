# Kết nối UserDetailsService, AuthenticationProvider và nguồn tài khoản

> **Chương:** Đăng nhập người dùng  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Giới hạn ví dụ:** Servlet stack của Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.x. Khi dùng Spring Security 7.x/Boot 4.x, cần đối chiếu các API và starter của đúng phiên bản.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt trách nhiệm của `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager`, `PasswordEncoder` và nguồn dữ liệu tài khoản.
2. Giải thích luồng Spring Security xác minh username/password và lưu trạng thái đăng nhập của **Resource Owner** trước khi Authorization Server tiếp tục luồng OAuth 2.0/OIDC.
3. Kết nối một bảng tài khoản riêng bằng Spring Data JPA, chuyển dữ liệu nghiệp vụ thành `UserDetails` và cấu hình `DaoAuthenticationProvider` đúng cách.
4. Biết khi nào chọn `JdbcUserDetailsManager`, `UserDetailsService` tùy biến hoặc một `AuthenticationProvider` khác.
5. Thiết kế mật khẩu, trạng thái khóa tài khoản, authorities, session và thông báo lỗi an toàn.
6. Kiểm thử cả việc đọc tài khoản, kiểm tra mật khẩu, xử lý request đăng nhập và tác động tới `/oauth2/authorize`.

Bài tập trung vào **xác thực người dùng cuối ở Authorization Server**. Đăng ký OAuth2 Client, xác thực client secret, cấp authorization code và phát token là các phần khác của giao thức; không được nhầm chúng với việc tra thông tin user trong database.

## 2. Vì sao Authorization Server cần một nguồn tài khoản?

Một Authorization Server có thể nhận request:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-web&scope=openid%20booking.read&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&state=example-state&code_challenge=example-challenge&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

Request trên chỉ minh họa hình dạng yêu cầu; `state` và `code_challenge` phải được tạo hợp lệ và an toàn trong ứng dụng thật. Nếu Resource Owner chưa đăng nhập, AS thường chuyển trình duyệt tới trang login. Khi người dùng gửi username/password, hệ thống phải trả lời những câu hỏi:

- Username được tìm trong nguồn dữ liệu nào?
- Mật khẩu nhập vào có khớp **hash đã lưu** hay không?
- Tài khoản đang bị vô hiệu hóa, khóa hay hết hạn?
- Tài khoản có những authority/role nào?
- Khi xác thực thành công, Spring Security sẽ ghi nhận principal và duy trì phiên trình duyệt ra sao?

Đó là nơi `UserDetailsService`, `DaoAuthenticationProvider`, `PasswordEncoder` và kho tài khoản phối hợp.

### 2.1. Các vai trò trong chuỗi xác thực

| Thành phần | Trách nhiệm | Không nên giao cho thành phần này |
| --- | --- | --- |
| **Nguồn tài khoản** | Lưu username, password hash, trạng thái, authorities và dữ liệu liên quan | Phát OAuth2 access token trực tiếp |
| **`UserDetailsService`** | Tra một tài khoản theo username và trả `UserDetails` | Tự so sánh raw password với hash, cấp OAuth2 token |
| **`PasswordEncoder`** | Mã hóa một chiều mật khẩu mới và xác minh mật khẩu nhập | Quản lý session hoặc scope OAuth2 |
| **`AuthenticationProvider`** | Xác minh một loại `Authentication`; ở đây là username/password | Quản lý toàn bộ client registration của OAuth2 |
| **`AuthenticationManager`** | Điều phối các provider có thể xử lý yêu cầu xác thực | Bắt buộc phải tự viết lại cho mọi ứng dụng |
| **`SecurityContext`** | Giữ `Authentication` đã xác thực của request | Là kho lưu OAuth2 authorization code/token |
| **`RegisteredClientRepository`** | Lưu cấu hình OAuth2 Client, grant, redirect URI, scope, client authentication | Tra user đăng nhập theo username |
| **`OAuth2AuthorizationService`** | Lưu trạng thái grant và token của OAuth2 | Thay thế `UserDetailsService` |

Đặc biệt, từ “client authentication” trong OAuth 2.0 nói về **ứng dụng** gọi token endpoint; “user authentication” trong bài này nói về **người dùng** đăng nhập. Chúng có thể xuất hiện trong cùng hệ thống Spring Security nhưng không có cùng principal, credential hay provider.

## 3. Luồng Username/Password từ form login đến database

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng (Resource Owner)
    participant B as Browser
    participant F as UsernamePasswordAuthenticationFilter
    participant M as AuthenticationManager
    participant P as DaoAuthenticationProvider
    participant D as UserDetailsService
    participant DB as Account Repository / Database
    participant E as PasswordEncoder
    participant S as SecurityContext / Session

    U->>B: Nhập username và password
    B->>F: POST /login + CSRF token
    F->>M: UsernamePasswordAuthenticationToken chưa xác thực
    M->>P: authenticate(...)
    P->>D: loadUserByUsername(username)
    D->>DB: Tìm tài khoản, quyền và trạng thái
    DB-->>D: Account + password hash + authorities
    D-->>P: UserDetails
    P->>P: Kiểm tra enabled / locked / expiry
    P->>E: matches(rawPassword, passwordHash)
    E-->>P: true hoặc false
    alt Hợp lệ
        P-->>M: Authentication đã xác thực
        M-->>F: Authentication
        F->>S: Lưu SecurityContext theo cơ chế login
        F-->>B: Redirect tiếp tới request đã lưu
    else Không hợp lệ
        P-->>F: AuthenticationException
        F-->>B: Chuyển tới trang báo login thất bại
    end
~~~

Sơ đồ diễn tả logic thường gặp của `DaoAuthenticationProvider`, không khẳng định chính xác thứ tự mọi kiểm tra hoặc tên hàm nội bộ ở mọi phiên bản. Spring Security có thể thực hiện kiểm tra trạng thái tài khoản trước/sau khi đối chiếu credential và có cơ chế ẩn thông tin tài khoản không tồn tại.

### 3.1. Phân biệt hai dạng `UsernamePasswordAuthenticationToken`

Trước khi xác thực:

~~~java
Authentication request = UsernamePasswordAuthenticationToken
    .unauthenticated("lan", "submitted-password");
~~~

Đây chỉ là **yêu cầu xác thực**, chưa phải bằng chứng hợp lệ. Filter gửi nó tới `AuthenticationManager` để tìm provider hỗ trợ. `DaoAuthenticationProvider` tải `UserDetails` rồi gọi `PasswordEncoder.matches(...)`.

Sau khi thành công, provider tạo một `Authentication` được xác thực có principal và authorities; kết quả được gắn vào `SecurityContext`. Thông tin credential nhạy cảm thường được xóa sau xác thực theo cấu hình/framework.

**Không tự gọi** `UsernamePasswordAuthenticationToken.authenticated(...)` từ controller chỉ vì tìm thấy một tài khoản. Làm như vậy có thể bỏ qua kiểm tra password, trạng thái account và chính sách provider.

### 3.2. ProviderManager quyết định provider nào xử lý

`AuthenticationManager` là hợp đồng giao diện. `ProviderManager` là một implementation phổ biến, duyệt các `AuthenticationProvider` được cấu hình và chọn provider hỗ trợ kiểu `Authentication` tương ứng qua `supports(...)`.

Ví dụ:

- `DaoAuthenticationProvider` phù hợp với yêu cầu username/password.
- Provider LDAP hoặc provider tùy biến có thể xác minh một loại credential khác.
- Các provider đặc thù OAuth2 Client tại token endpoint của Spring Authorization Server xử lý **client authentication**, không phải mật khẩu đăng nhập của Resource Owner.
- Một ứng dụng có thể có nhiều provider, nhưng cần kiểm soát thứ tự và loại request mỗi provider xử lý.

## 4. Chọn nguồn tài khoản phù hợp

| Nguồn tài khoản | Khi nào phù hợp | Điểm phải lưu ý |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | Demo, test hoặc spike nhanh | Không phù hợp làm kho user production dùng lâu dài |
| `JdbcUserDetailsManager` | Hệ đơn giản dùng schema mặc định hoặc SQL có thể tùy chỉnh | Cần bảng user/authority đúng schema hoặc câu query được cấu hình |
| `UserDetailsService` tự viết + Spring Data JPA | Có bảng account riêng, trạng thái và vai trò nghiệp vụ | Mapping entity, transaction, unique username, migrations, khóa tài khoản |
| `UserDetailsService` tự viết + JDBC/MyBatis | Muốn kiểm soát SQL hoặc không dùng JPA | Phải tự truy vấn an toàn và ánh xạ dữ liệu sang `UserDetails` |
| LDAP/Active Directory | Tài khoản và xác thực được tổ chức quản lý tập trung | Có thể dùng provider LDAP trực tiếp; không nhất thiết dùng `DaoAuthenticationProvider` với DB password hash |
| Đăng nhập qua IdP ngoài (OIDC/SAML) | Ủy quyền xác thực người dùng cho nhà cung cấp danh tính | Cần cấu hình cơ chế federation như `oauth2Login()` hoặc giải pháp phù hợp; không dùng username/password nội bộ nếu không cần |

Bài triển khai cụ thể theo phương án **Spring Data JPA** vì dễ thấy ranh giới giữa nguồn dữ liệu nghiệp vụ và Spring Security. Phần JDBC có ví dụ thay thế ở mục 9.

## 5. Thiết kế dữ liệu tài khoản trước khi viết code

Một schema tham khảo có hai bảng:

~~~sql
-- PostgreSQL: minh họa schema cho user authentication.
CREATE TABLE auth_account (
    id UUID PRIMARY KEY,
    username VARCHAR(160) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE auth_account_authority (
    account_id UUID NOT NULL REFERENCES auth_account(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, authority)
);
~~~

Trong triển khai thực tế nên bổ sung các trường và bảng phục vụ chính sách như audit, thay đổi password, thông tin chứng thực đa yếu tố, lịch sử đăng nhập, sự kiện khóa tài khoản, tenant hoặc tài khoản đã xóa. Không nhất thiết đưa tất cả vào một bảng.

### 5.1. Khóa định danh và chuẩn hóa username

- `id`: định danh kỹ thuật ổn định, không thay đổi khi người dùng đổi username/email.
- `username`: khóa tra cứu đăng nhập; cần chính sách chuẩn hóa thống nhất khi tạo và đăng nhập.
- `password_hash`: chỉ chứa kết quả đã hash bằng thuật toán được hỗ trợ, tuyệt đối không lưu raw password.
- `enabled`: tài khoản có được phép đăng nhập hay không.
- `locked`: tài khoản bị khóa theo chính sách quản trị hoặc phản ứng sự cố.
- `authority`: quyền mức cao của tài khoản, ví dụ `ROLE_USER` hoặc `ROLE_SUPPORT`.

Có thể dùng email làm username nhưng phải quyết định rõ có phân biệt chữ hoa/chữ thường không, cách normalizing, collation, uniqueness và cách xác minh quyền sở hữu email. Không tùy tiện gọi `toLowerCase()` với mọi trường định danh khi chưa có chính sách.

### 5.2. Authority và quyền nghiệp vụ khác nhau

`ROLE_USER` cho biết user thuộc vai trò thông thường; `ROLE_SUPPORT` có thể biểu thị nhân viên hỗ trợ. Không suy từ role đó rằng user được xem mọi đơn hàng/booking. Resource Server vẫn phải kiểm tra **quyền trên đối tượng**, scope của access token, tenant và chính sách nghiệp vụ.

Thêm `ROLE_ADMIN` vào user đăng nhập **không tự động** tạo scope `booking.read` cho mọi OAuth2 Client. Scope cấp cho client và quyền người dùng được quản lý ở những nơi khác nhau; AS có thể tổng hợp theo chính sách khi cấp token.

## 6. Kết nối nguồn tài khoản bằng Spring Data JPA

Phần này là **các mảnh code cùng một ví dụ**, dành cho dự án Spring Boot đã có Web, Security, Data JPA, driver database và migration tool phù hợp. Import thông dụng được nêu theo nhóm; IDE có thể thêm import từ `jakarta.persistence.*`, `org.springframework.data.*` và `org.springframework.security.*`.

### 6.1. Ánh xạ entity `AuthAccount`

~~~java
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "auth_account")
public class AuthAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true, length = 160)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled = true;

    @Column(nullable = false)
    private boolean locked = false;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "auth_account_authority",
        joinColumns = @JoinColumn(name = "account_id"))
    @Column(name = "authority", nullable = false, length = 100)
    private Set<String> authorities = new HashSet<>();

    protected AuthAccount() {
        // JPA
    }

    public UUID getId() { return id; }
    public String getUsername() { return username; }
    public String getPasswordHash() { return passwordHash; }
    public boolean isEnabled() { return enabled; }
    public boolean isLocked() { return locked; }
    public Set<String> getAuthorities() { return authorities; }
}
~~~

Các setter/factory dành cho quy trình tạo tài khoản được lược bớt. Khi xây dựng service đăng ký user, cần chủ động thiết kế việc tạo tài khoản thay vì mở setter tùy ý và để mọi API tự thay đổi password hash/role.

### 6.2. Repository chỉ đọc dữ liệu cần xác thực

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuthAccountRepository
        extends JpaRepository<AuthAccount, UUID> {

    @EntityGraph(attributePaths = "authorities")
    Optional<AuthAccount> findByUsername(String username);
}
~~~

`@EntityGraph` ở đây yêu cầu tải authorities cùng tài khoản, tránh lỗi lazy loading khi đã thoát transaction. Với hệ thống phức tạp, có thể chọn projection/query tối ưu riêng; điều quan trọng là dữ liệu `UserDetails` phải được ánh xạ đầy đủ trong ranh giới transaction và không cần truy vấn bí mật ngoài ý muốn.

Ở lớp database, cần unique constraint cho username. Nếu cho phép tìm case-insensitive, không chỉ viết `findByUsernameIgnoreCase`: phải đảm bảo **cùng quy tắc uniqueness** khi insert để tránh hai tài khoản cùng tên theo góc nhìn người đăng nhập.

### 6.3. Viết `UserDetailsService` chuyển dữ liệu DB sang Spring Security

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AuthAccountRepository accounts;

    public DatabaseUserDetailsService(AuthAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AuthAccount account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Không tìm thấy tài khoản"));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .authorities(account.getAuthorities().toArray(String[]::new))
            .build();
    }
}
~~~

Những điểm cần hiểu:

1. `loadUserByUsername` chỉ tìm **một** tài khoản; nó không nhận raw password làm tham số.
2. `getPasswordHash()` trả mật khẩu **đã hash**, để provider kiểm tra bằng `PasswordEncoder`.
3. `.disabled(!enabled)` và `.accountLocked(locked)` đưa trạng thái tài khoản vào `UserDetails`.
4. `.authorities(...)` dùng các chuỗi đã lưu. Nếu DB lưu `ROLE_USER` thì nó giữ nguyên `ROLE_USER`; phương thức `roles("USER")` lại tự thêm tiền tố `ROLE_`. Tránh trộn hai cách một cách vô ý.
5. `@Transactional(readOnly = true)` giúp quản lý truy vấn JPA trong một transaction đọc.
6. Không dùng exception message chi tiết này để trả thẳng về UI, vì UI có thể làm lộ tài khoản tồn tại hay không.

Nếu nguồn account chứa trạng thái hết hạn tài khoản/mật khẩu, có thể mở rộng bằng một `UserDetails` tùy biến hoặc ánh xạ các cờ tương ứng trong builder. Với quyền gắn tenant/organization, cần mô hình hóa rõ nơi tenant được chọn và xác minh, không gán quyền của mọi tenant vào một principal chung.

### 6.4. Chọn `PasswordEncoder`

Spring Security hỗ trợ `DelegatingPasswordEncoder` để lưu định danh thuật toán trong hash, ví dụ `{bcrypt}...`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Ví dụ tạo hash khi đăng ký/đổi mật khẩu:

~~~java
String passwordHash = passwordEncoder.encode(rawPasswordFromUser);

// Khi đăng nhập, DaoAuthenticationProvider sẽ tự gọi
// passwordEncoder.matches(submittedPassword, passwordHash).
~~~

**Đừng tự so sánh hash bằng `equals` hoặc mã hóa raw password lần nữa rồi so sánh hai chuỗi**: các thuật toán hash có salt nên kết quả encode hai lần thường khác nhau. Hãy dùng `matches(raw, encoded)`.

Với `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, hash mới thường mang prefix định danh `{bcrypt}`. Nếu dữ liệu cũ chỉ lưu chuỗi BCrypt `$2a$...` không có prefix, cần thiết kế **migrating/compatibility policy** có kiểm soát. Không bật một fallback chấp nhận plaintext hoặc dùng `NoOpPasswordEncoder` trên hệ production.

Việc chọn cost của BCrypt/Argon2 phải theo hiệu năng máy chủ và mục tiêu bảo mật. Tăng cost tùy tiện có thể gây quá tải khi nhận nhiều request login; phải có rate limit, timeout và capacity test. Đừng log raw password, hash hoặc kết quả so khớp từng trường hợp vào application logs.

### 6.5. Kết nối `DaoAuthenticationProvider`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class UserAuthenticationConfig {

    @Bean
    AuthenticationProvider userAuthenticationProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }
}
~~~

`DaoAuthenticationProvider` tải user qua `UserDetailsService`, kiểm tra trạng thái user và dùng `PasswordEncoder` để xác minh credential. Provider này hỗ trợ loại yêu cầu username/password. Trong code Spring Security 6.x có những overload hoặc builder cấu hình khác; ví dụ trên được trình bày theo API nhận `UserDetailsService` ở constructor. Khi nâng Spring Security major, phải đối chiếu lại constructor/DSL thay vì mặc nhiên copy nguyên.

**Điểm quyết định:** chỉ đăng ký bean `PasswordEncoder` hoặc `UserDetailsService` không có nghĩa bạn đã kiểm tra được toàn bộ login flow. Cần bảo đảm filter chain đăng nhập sử dụng provider và cấu hình form login đúng nơi.

## 7. Kết nối provider với filter chain đăng nhập

Một AS chạy Spring Authorization Server thường tách **filter chain cho các endpoint OAuth2/OIDC** và **filter chain web dành cho đăng nhập người dùng**.

### 7.1. Sơ đồ chọn chain

~~~mermaid
flowchart TD
    A["HTTP request đến Spring Boot AS"]
    B{"Khớp endpoint OAuth2/OIDC<br/>của Authorization Server?"}
    C["AS SecurityFilterChain<br/>@Order(1)"]
    D["Application/Login SecurityFilterChain<br/>@Order(2)"]
    E{"User đã đăng nhập?"}
    L["Redirect tới /login<br/>nếu request cần tương tác"]
    T["OAuth2 handlers xử lý<br/>grant/client/token"]
    F["UsernamePasswordAuthenticationFilter"]
    P["DaoAuthenticationProvider"]
    DB[("Nguồn tài khoản")]
    S["SecurityContext + session"]

    A --> B
    B -->|"Có"| C
    B -->|"Không"| D
    C --> E
    E -->|"Chưa, đang authorize"| L
    E -->|"Đã có / endpoint khác"| T
    L --> D
    D -->|"POST /login"| F
    F --> P
    P --> DB
    P --> S
    S --> T
~~~

`GET /login` là request mới của browser, thường được xử lý bởi application/login chain. Token endpoint có cơ chế xác thực **OAuth2 Client** riêng; `DaoAuthenticationProvider` không dùng để kiểm tra `client_secret` tại token endpoint.

### 7.2. Cấu hình ví dụ hai chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration
public class SecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain loginSecurity(
            HttpSecurity http,
            AuthenticationProvider userAuthenticationProvider)
            throws Exception {

        http
            .authenticationProvider(userAuthenticationProvider)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Điều kiện để code trên chạy trong một Authorization Server đầy đủ:

- Dự án đã có dependency Spring Authorization Server phù hợp, Spring Web/Security và cấu hình build.
- AS có `RegisteredClientRepository`, `OAuth2AuthorizationService`, khóa/JWK, issuer settings và các bean cần thiết tùy endpoint.
- Nếu bật `oidc(...)`, phải có các thành phần hỗ trợ OIDC như `JwtDecoder` theo yêu cầu của version.
- Đăng nhập người dùng có bean `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder` hợp lệ; nếu cấu hình nhiều provider, tránh bean ambiguity khi injection.
- `GET /login` và `POST /login` được xử lý qua form login. Cấu hình `formLogin(Customizer.withDefaults())` có thể cung cấp login page mặc định, phù hợp cho môi trường học tập.
- Nếu có REST API riêng, nên thiết kế chain với Bearer token phù hợp thay vì để API trả HTML login.

**Không đem một `@Order(1)` chain `anyRequest()` tổng quát lên trước AS matcher**: nó có thể chiếm hết OAuth2/OIDC endpoints. Thứ tự và `securityMatcher` phải được kiểm thử.

### 7.3. Sau login, điều gì xảy ra với OAuth2 authorization request?

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant AS as Authorization Server
    participant LOGIN as Form Login / Provider
    participant DB as Account Store
    participant C as OAuth2 Client

    C-->>B: Redirect /oauth2/authorize
    B->>AS: Request authorize khi chưa login
    AS-->>B: Redirect /login
    U->>B: Nhập username/password
    B->>LOGIN: POST /login (CSRF token hợp lệ)
    LOGIN->>DB: UserDetailsService tìm user
    DB-->>LOGIN: Hash + account flags + authorities
    LOGIN->>LOGIN: PasswordEncoder.matches + kiểm tra account
    LOGIN-->>B: Session authenticated + redirect request đã lưu
    B->>AS: Tiếp tục /oauth2/authorize với session
    AS->>AS: Kiểm tra client, scope, consent
    AS-->>B: Redirect callback với authorization code
    B->>C: Client nhận authorization code
    C->>AS: POST /oauth2/token + client auth + code/verifier
    AS-->>C: Access token / ID token nếu hợp lệ
~~~

`SavedRequest` và request cache có thể giúp browser quay về authorization request sau login; chính sách session/cookie cần được cấu hình phù hợp. Thông tin đăng nhập Resource Owner được sử dụng tại authorization endpoint, **không chuyển thẳng mật khẩu người dùng cho Client**.

## 8. Lưu SecurityContext và phiên đăng nhập đúng cách

### 8.1. Phân biệt authentication theo request và trạng thái grant

- `SecurityContextHolder.getContext().getAuthentication()` trong request login/authorization có thể chứa principal của Resource Owner.
- `HttpSession` hoặc `SecurityContextRepository` phù hợp giúp user đã đăng nhập tiếp tục luồng qua redirect.
- `OAuth2AuthorizationService` lưu trạng thái authorization code/token để Client đổi code ở request khác.
- Token endpoint sử dụng client authentication theo OAuth2. Không dựa vào ThreadLocal của request login đã kết thúc.

Nếu tự viết authentication filter/controller (thay vì dùng form login có sẵn), với cơ chế explicit-save của Spring Security 6, cần lưu `SecurityContext` thông qua `SecurityContextRepository.saveContext(...)` khi muốn duy trì đăng nhập sang request tiếp theo. Chỉ gọi `SecurityContextHolder.setContext(...)` không tự đảm bảo session được lưu.

### 8.2. CSRF và cookie

Form login dựa vào session/cookie nên phải xử lý CSRF. Với `MockMvc` hoặc HTML form custom, cần gửi CSRF token theo cơ chế Spring Security đã cấu hình. Đừng tắt CSRF toàn cục chỉ để request `POST /login` chạy.

Trong production, dùng HTTPS, cookie `Secure` và `HttpOnly`, kiểm tra chính sách `SameSite` phù hợp các redirect cross-site, chống session fixation, giới hạn session lifetime và xử lý load balancer/reverse proxy đáng tin cậy. Với nhiều AS instance, session và lưu authorization/consent cần kiến trúc chia sẻ/phân tán phù hợp nếu không dùng sticky session.

## 9. Phương án khác: JdbcUserDetailsManager

Nếu nguồn tài khoản đơn giản và phù hợp schema Spring Security, không cần tự viết JPA entity. `JdbcUserDetailsManager` triển khai cả `UserDetailsService` và những thao tác quản lý user theo cấu hình.

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.JdbcUserDetailsManager;

@Bean
UserDetailsService jdbcUserDetailsService(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
~~~

Theo cách dùng mặc định, cần chuẩn bị các bảng `users` và `authorities` đúng schema Spring Security hoặc cấu hình lại SQL query thông qua API `JdbcDaoImpl`/`JdbcUserDetailsManager` khi có schema riêng.

Ví dụ tối giản về ý tưởng schema tương thích với các truy vấn mặc định (kiểm tra lại DDL theo database dialect/phiên bản Spring):

~~~sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(50) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username)
);

CREATE UNIQUE INDEX ix_auth_username
    ON authorities(username, authority);
~~~

Không khai báo **đồng thời** bean `DatabaseUserDetailsService` từ ví dụ JPA và bean `jdbcUserDetailsService` ở ví dụ này trừ khi chủ động cấu hình qualifier/provider lựa chọn. Nếu cả hai tồn tại, việc inject `UserDetailsService` đơn giản có thể mơ hồ hoặc hệ thống dùng không đúng nguồn tài khoản.

### 9.1. Khi schema công ty đã khác mặc định

Có hai lựa chọn:

1. Dùng `JdbcUserDetailsManager` và tùy biến SQL để đọc đúng tài khoản/authorities.
2. Viết `UserDetailsService` riêng với Spring Data JPA/JDBC để ánh xạ trạng thái và quyền đặc thù.

Không sửa database của hệ khác theo schema `users`/`authorities` chỉ để vừa với ví dụ nếu có ràng buộc nghiệp vụ, transaction hoặc migration khác.

## 10. Xác thực người dùng ngoài database nội bộ

### 10.1. LDAP hoặc Active Directory

Với LDAP, Spring Security có những cơ chế xác thực trực tiếp bằng LDAP, ví dụ bind authentication. Khi đó mật khẩu có thể được xác minh bởi directory server; **`DaoAuthenticationProvider` và local password hash có thể không phải con đường phù hợp**.

Bạn vẫn cần giải quyết ánh xạ authorities/groups, trạng thái tài khoản, timeout/HA của directory, phân quyền ứng dụng và cách lưu user principal sau xác thực.

### 10.2. Đăng nhập qua OpenID Connect Provider khác

Authorization Server của hệ thống có thể để người dùng đăng nhập qua một IdP bên ngoài bằng `oauth2Login()`, rồi dùng kết quả xác thực làm phiên Resource Owner để tiếp tục cấp quyền cho OAuth2 Clients của **AS nội bộ**.

Ở luồng này:

- AS nội bộ đóng vai **OIDC Client/Relying Party** khi kết nối IdP ngoài.
- Đồng thời, AS nội bộ vẫn đóng vai **Authorization Server/OpenID Provider** với các Client của chính nó.
- Principal từ `oauth2Login()` thường là `OidcUser`, không phải `UserDetails` lấy từ `DaoAuthenticationProvider`.
- Phải thiết kế ánh xạ `issuer + sub` của IdP ngoài tới tài khoản nội bộ và quyền của người dùng; không xem email là định danh bất biến.

Không sử dụng grant Resource Owner Password Credentials để né yêu cầu cấu hình đăng nhập trong hệ thống hiện đại. Luồng Authorization Code + PKCE hoặc federation tương ứng thường phù hợp hơn.

## 11. Các trạng thái tài khoản và cách xử lý an toàn

`UserDetails` cung cấp các cờ:

| Thuộc tính | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được phép dùng để xác thực | Ánh xạ từ `enabled` |
| `isAccountNonLocked()` | Tài khoản không bị khóa | Đảo ngược từ `locked` |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | `User` builder giữ mặc định nếu không chỉnh |
| `isCredentialsNonExpired()` | Thông tin xác thực chưa hết hạn | `User` builder giữ mặc định nếu không chỉnh |
| `getAuthorities()` | Quyền mức cao tại thời điểm tải user | Từ `auth_account_authority` |

Spring Security có thể dùng các exception như `BadCredentialsException`, `DisabledException`, `LockedException`, `AccountExpiredException` hoặc `CredentialsExpiredException` trong quá trình xác thực. **Không nhất thiết hiển thị chính xác lý do** ở public login page, vì điều đó có thể giúp kẻ tấn công suy ra user có tồn tại hay bị khóa hay không.

### 11.1. Account lockout không tự động xuất hiện khi có cờ `locked`

Ánh xạ `locked` chỉ giúp provider từ chối user **đã bị đánh dấu khóa**. Nó không tự đếm số lần đăng nhập sai hay quyết định khi nào khóa.

Một chính sách đầy đủ có thể gồm:

- Rate limiting theo IP, tài khoản và tín hiệu rủi ro; tránh cho phép kẻ xấu khóa hàng loạt người dùng bằng request giả.
- Ghi nhận thất bại/sự kiện bảo mật ở kho dữ liệu an toàn, có chính sách làm sạch và thời hạn.
- Khóa tạm thời hoặc challenge bổ sung theo risk score, kèm quy trình mở khóa hợp lệ.
- Hỗ trợ MFA cho tài khoản nhạy cảm hoặc nghiệp vụ đòi hỏi.
- Giới hạn enumeration qua response, latency và nội dung thông báo lỗi.
- Cơ chế thu hồi session và token hoặc kiểm tra trạng thái account khi người dùng bị khóa sau khi đã đăng nhập.

**Khóa user trong database không nhất thiết hủy mọi session đang hoạt động hoặc JWT đã cấp.** Nếu có yêu cầu khóa tức thì, phải thiết kế quản lý session và chính sách xác minh token tại AS/RS tương ứng.

### 11.2. UserDetails cache và quyền thay đổi giữa chừng

Một số triển khai/provider dùng cache `UserDetails` để giảm tải database. Nếu cache giữ trạng thái `enabled`, `locked` hoặc `authorities` quá lâu, thông tin trong login tiếp theo có thể bị cũ. Phải xác định TTL/invalidation khi đổi mật khẩu, khóa tài khoản hoặc điều chỉnh quyền.

Session hiện hữu cũng có thể chứa `Authentication` với authorities từ lúc đăng nhập. Việc đổi role trong DB **không mặc nhiên** cập nhật mọi session đang sống; chọn cơ chế đánh giá quyền hoặc session invalidation phù hợp yêu cầu hệ thống.

## 12. Luồng tạo tài khoản và đổi mật khẩu

Không cho phía client gửi sẵn password hash rồi tin đó là kết quả chính thức. Tài khoản phải được tạo/đổi mật khẩu trong một service có authorization và validation phù hợp.

~~~mermaid
flowchart TD
    A["Request tạo tài khoản hoặc đổi mật khẩu"]
    B["Kiểm tra quyền, danh tính và dữ liệu đầu vào"]
    C["Chuẩn hóa username theo chính sách"]
    D["Đánh giá yêu cầu mật khẩu + rate limit"]
    E["PasswordEncoder.encode(rawPassword)"]
    F["Lưu password hash trong DB qua transaction"]
    G["Audit sự kiện; cân nhắc thu hồi session/token"]
    H["Không trả raw password/hash trong API/log"]

    A --> B --> C --> D --> E --> F --> G --> H
~~~

Ví dụ một phương thức hash trong application service:

~~~java
public String hashNewPassword(
        String rawPassword,
        PasswordEncoder passwordEncoder) {

    // Policy mật khẩu, xác thực người đổi mật khẩu, audit và
    // kiểm soát tốc độ phải được xử lý ở service nghiệp vụ.
    return passwordEncoder.encode(rawPassword);
}
~~~

Đoạn mã chỉ minh họa cách gọi `encode()`, **không phải endpoint đổi mật khẩu hoàn chỉnh**. Một hệ thống production phải kiểm tra quyền người đổi mật khẩu, xác minh credential hiện tại hoặc bước xác minh mạnh phù hợp, thực hiện giao dịch và cân nhắc thu hồi session/token.

## 13. Kiểm thử từng lớp kết nối

### 13.1. Unit test của `UserDetailsService`

Với mock repository, kiểm tra:

| Input | Kỳ vọng |
| --- | --- |
| Username tồn tại, account enabled, không locked | Trả đúng `UserDetails`, hash và authorities |
| Username không tồn tại | Ném `UsernameNotFoundException` |
| Account disabled | Trả `UserDetails.isEnabled() == false` |
| Account locked | Trả `isAccountNonLocked() == false` |
| DB trả nhiều authorities | Không làm mất hoặc thêm sai tiền tố `ROLE_` |
| Đổi quyền sau khi cache hoạt động | Cache/invalidation tuân thủ chính sách |
| Username khác hoa/thường | Hành vi khớp quy tắc unique/normalization |

`UserDetailsService` test không cần gọi password encoder, vì service này chỉ ánh xạ thông tin.

### 13.2. Kiểm thử `DaoAuthenticationProvider`

Dùng tài khoản fixture có hash được tạo từ cùng `PasswordEncoder` dùng trong provider:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("strong-password-for-test");

// Trong test, UserDetailsService trả UserDetails
// có password = storedHash và account được bật.

Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan", "strong-password-for-test");

Authentication result = provider.authenticate(request);

assertThat(result.isAuthenticated()).isTrue();
assertThat(result.getName()).isEqualTo("lan");
~~~

Đây là **đoạn lõi trong unit test**, giả định `provider` đã được tạo và `UserDetailsService` fixture trả user `lan` với hash tương ứng. Không tạo thử một tài khoản test với mật khẩu hardcode ở môi trường production.

Các ca cần bổ sung: password sai, user không tồn tại, account disabled, locked, hash định dạng không hỗ trợ và backend DB unavailable. Kiểm tra exception/response theo contract, nhưng không phơi thông tin nhạy cảm ra HTML/log.

### 13.3. MockMvc kiểm thử form login

Với `spring-security-test`, ví dụ đăng nhập sai:

~~~java
@Test
void invalidPasswordDoesNotAuthenticate() throws Exception {
    mockMvc.perform(post("/login")
            .param("username", "lan")
            .param("password", "wrong-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/login?error"));
}
~~~

Test đăng nhập thành công:

~~~java
@Test
void validPasswordAuthenticatesUser() throws Exception {
    mockMvc.perform(post("/login")
            .param("username", "lan")
            .param("password", "correct-test-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection())
        .andExpect(authenticated().withUsername("lan"));
}
~~~

Điều kiện: fixture đã lưu user `lan` có hash của `correct-test-password`, provider thực sự dùng repository/encoder của ứng dụng, form login mặc định đang bật, `MockMvc` kết nối Spring Security và static imports của `csrf()`/`authenticated()` đã được bổ sung.

Các test có `@WithMockUser` thuận tiện cho **authorization rules**, nhưng thường bỏ qua `UserDetailsService` và `PasswordEncoder` thực tế. Vì vậy không lấy test `@WithMockUser` làm bằng chứng kiểm tra mật khẩu đã đúng.

### 13.4. Kiểm thử tích hợp với Authorization Server

Sau khi test login riêng, thử lại luồng Authorization Code + PKCE:

1. Client hợp lệ chuyển browser đến `/oauth2/authorize`, Resource Owner chưa đăng nhập.
2. AS chuyển sang `/login`; form có CSRF token hợp lệ.
3. Người dùng nhập credential đúng; provider tải account thật và xác minh password hash.
4. Browser có session hợp lệ, quay lại authorization request ban đầu.
5. AS kiểm tra client/redirect URI/scope/consent và phát authorization code theo chính sách.
6. Client backend đổi code bằng `code_verifier` và phương thức xác thực client đã đăng ký.
7. AS cấp token; Resource Server chỉ chấp nhận access token hợp lệ và kiểm tra quyền nghiệp vụ.

Các ca âm cần có: disabled/locked user, user không tồn tại, password sai, CSRF thiếu, cookie không được giữ qua redirect, client redirect URI sai và PKCE verifier sai. Không nên ép test tất cả bằng MockMvc trong một method quá lớn; có thể tách test nguồn tài khoản, test login/session và test giao thức end-to-end.

## 14. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Login trả `BadCredentialsException` dù password nhập đúng | Hash thiếu `{bcrypt}` khi dùng delegating encoder, dữ liệu test sai, dùng encoder khác khi tạo hash | Kiểm tra `PasswordEncoder`, cách lưu hash, policy migration |
| `No AuthenticationProvider found` cho username/password | Provider không đăng ký đúng chain/manager | Kiểm tra `AuthenticationProvider` bean, `supports()`, filter chain |
| `NoUniqueBeanDefinitionException` với `UserDetailsService` | Có nhiều bean user service/JDBC/in-memory | Chọn đúng provider/qualifier, loại bỏ cấu hình thử nghiệm |
| User tồn tại nhưng `LazyInitializationException` | Authorities bị đọc ngoài transaction | Fetch authorities trong transaction, dùng `@EntityGraph` hoặc query phù hợp |
| GET login redirect vòng lặp | `/login` bị yêu cầu đăng nhập, matcher chain sai | Cho phép truy cập trang login, kiểm tra `@Order`/`securityMatcher` |
| POST login trả 403 | Thiếu/sai CSRF, sai session cookie hoặc chain | Sửa CSRF token/form/session; không tắt CSRF toàn cục |
| Login thành công nhưng `/oauth2/authorize` vẫn anonymous | Context không được lưu/khôi phục, cookie sai, chain stateless | Kiểm tra `SecurityContextRepository`, session và proxy |
| User bị khóa nhưng session cũ vẫn dùng được | Khóa DB không hủy session/token đã cấp | Thực thi session invalidation/revocation/check trạng thái theo policy |
| Client Credentials không gọi được token endpoint do user service | Nhầm client authentication với user login | Xác minh `RegisteredClientRepository`, client secret, token endpoint providers |
| Login chậm, DB quá tải | Query authorities N+1, hash cost quá cao, thiếu rate limit | Tối ưu query, benchmark encoder và kiểm soát tốc độ |
| Một user đăng nhập nhưng authorities sai | Mapping sai `roles()`/`authorities()` hoặc lấy role từ tenant khác | Quy định tiền tố và tenant context rõ ràng |
| Không tìm thấy user vì chữ hoa/thường | Normalization và unique constraint không nhất quán | Thống nhất chính sách username từ lúc tạo đến lúc lookup |

### 14.1. Hướng dẫn đọc log khi xác thực thất bại

Theo dõi theo trình tự:

1. Request vào đúng `SecurityFilterChain` chưa? Filter `UsernamePasswordAuthenticationFilter` có xử lý `POST /login` không?
2. `AuthenticationManager` đã chọn provider hỗ trợ request chưa?
3. `UserDetailsService` có tìm đúng account không? DB có lỗi/timeout hoặc authorities lazy loading không?
4. Account có `enabled`/`locked` đúng?
5. Hash có algorithm prefix/format khớp `PasswordEncoder`?
6. Session và `SecurityContext` có được lưu đúng sau thành công?
7. Request OAuth2 được tiếp tục và kiểm tra client/grant/consent đúng chưa?

**Không log** `password`, `password_hash`, client secret, access token, authorization code hay toàn bộ `Authentication`. Log có thể dùng request ID, loại provider, kết quả thành công/thất bại, mã lỗi tổng quát, account ID đã được che định danh và thời gian xử lý tùy chính sách riêng tư.

## 15. Bảo mật và vận hành tài khoản

Một hệ thống production cần có kiểm soát ngoài việc “đăng nhập đúng password”:

- **Mật khẩu:** hash hiện đại có salt, policy độ dài/phức tạp hoặc chống mật khẩu rò rỉ theo yêu cầu, cơ chế đổi/reset an toàn.
- **Chống tấn công login:** rate limit, monitoring, phản ứng brute force/credential stuffing, cảnh báo bất thường.
- **MFA/step-up:** cân nhắc cho hành động nhạy cảm; không giả định `DaoAuthenticationProvider` mặc định đã có MFA.
- **Trạng thái user:** disabled/locked/expired, sự kiện thay đổi quyền và chính sách đối với session/token đã cấp.
- **Quyền hạn:** phân biệt user authorities với OAuth2 scopes/client permissions và object-level authorization ở Resource Server.
- **Hạ tầng DB:** secrets từ secret manager, TLS/connection policy, backup, migration, HA, chỉ cấp SQL privileges cần thiết.
- **Dữ liệu nhạy cảm:** không đưa password hash vào JSON trả API, không để chúng xuất hiện trong log/tracing, không lưu raw password.
- **Audit:** ghi login success/failure, khóa/mở khóa, password reset, credential compromise bằng dữ liệu cần thiết và retention policy.
- **Scale:** load-test tốc độ truy vấn account, cost của hash, timeout, pool kết nối, các trường hợp directory/DB outage.
- **Đồng nhất môi trường:** development/test/staging/production dùng cấu hình mật khẩu/hash tương thích và migration được kiểm soát; không seed tài khoản admin mặc định bằng password công khai.

### 15.1. Checklist triển khai

- [ ] Chọn nguồn user cụ thể: JPA, JDBC, LDAP hoặc IdP ngoài.
- [ ] Username có unique constraint và chính sách chuẩn hóa rõ ràng.
- [ ] Password lưu dưới dạng hash phù hợp với `PasswordEncoder`, không có plaintext.
- [ ] `UserDetailsService` trả đúng principal, password hash, flags và authorities.
- [ ] `DaoAuthenticationProvider` được đăng ký đúng vào login chain nếu dùng username/password.
- [ ] Authorization Server endpoint chain và application/form-login chain có matcher/thứ tự đúng.
- [ ] `GET /login` công khai khi cần, `POST /login` có CSRF protection.
- [ ] Session và `SecurityContextRepository` hoạt động qua redirect.
- [ ] Client authentication/token endpoint độc lập với user login và được kiểm thử.
- [ ] Có rate limit, audit, lockout/disabled policy và quy trình khôi phục account.
- [ ] Có test password sai, disabled, locked, lazy authorities, DB outage, login/session và Authorization Code + PKCE.
- [ ] Không lộ password hash, raw password, cookie, code hoặc token trong log/API.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `UserDetailsService` không có phương thức `checkPassword(String, String)`?

**Đáp án:** Hợp đồng của nó là **tải user** theo username. `DaoAuthenticationProvider` kết hợp dữ liệu đó với `PasswordEncoder` để so khớp credential và quyết định authentication.

**Câu 2.** `RegisteredClientRepository` có thay được `UserDetailsService` không?

**Đáp án:** Không. `RegisteredClientRepository` quản lý ứng dụng OAuth2 Client, grant, secret và redirect URI. `UserDetailsService` quản lý việc tải tài khoản người dùng đăng nhập.

**Câu 3.** Vì sao lưu hash BCrypt trực tiếp nhưng không có `{bcrypt}` có thể gây lỗi khi dùng `DelegatingPasswordEncoder`?

**Đáp án:** Delegating encoder dựa vào prefix để biết thuật toán kiểm tra. Dữ liệu cũ cần có chính sách migration/fallback được kiểm soát.

**Câu 4.** User bị set `locked = true`, có cần code tự so raw password và từ chối không?

**Đáp án:** Nếu `UserDetailsService` ánh xạ đúng `isAccountNonLocked = false` và dùng `DaoAuthenticationProvider`, provider sẽ áp dụng kiểm tra trạng thái phù hợp. Việc tự khóa khi login sai nhiều lần vẫn là chính sách bổ sung cần triển khai.

**Câu 5.** Vì sao `@WithMockUser` không đủ để chứng minh database user/password kết nối đúng?

**Đáp án:** Nó tạo sẵn Authentication cho test, thường bỏ qua đường `UserDetailsService → DaoAuthenticationProvider → PasswordEncoder`. Cần test provider, repository và form login thực.

**Câu 6.** Nếu API được gọi bằng Client Credentials, có thể lấy user login bằng `UserDetailsService` từ token endpoint không?

**Đáp án:** Không nên. Client Credentials xác thực **client**, thường không có Resource Owner tương tác. AS kiểm tra client trong `RegisteredClientRepository` và xử lý grant bằng các provider phù hợp.

**Câu 7.** Sau khi user login đúng ở AS, API có thể bỏ qua scope và kiểm tra quyền trên dữ liệu không?

**Đáp án:** Không. Đăng nhập user là authentication. Resource Server vẫn phải kiểm tra access token, issuer, audience, scope và quyền nghiệp vụ trên dữ liệu.

## 17. Tóm tắt và tài liệu tham khảo

Chuỗi tích hợp phổ biến là **nguồn tài khoản → `UserDetailsService` → `DaoAuthenticationProvider` + `PasswordEncoder` → `AuthenticationManager` → `SecurityContext`**. Chuỗi này phục vụ **Resource Owner login** trong Authorization Server. Khi user đã đăng nhập, AS mới tiếp tục xử lý OAuth2 authorization, consent, authorization code và token theo chính sách; các bản ghi `OAuth2Authorization` và `RegisteredClient` vẫn có vòng đời riêng.

Tài liệu chính thức để đối chiếu API đúng với phiên bản triển khai:

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)

Bài này đưa ra các khối code mẫu cho thiết kế và thực hành. Để đưa vào production, cần ghép chúng vào dự án có cấu hình dependency, migrations, client registration, OIDC keys/issuer, session, account lifecycle và kiểm thử phù hợp.

