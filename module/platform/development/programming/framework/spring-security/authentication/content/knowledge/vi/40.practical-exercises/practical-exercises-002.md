# Tự triển khai UserDetailsService và ánh xạ quyền từ dữ liệu nghiệp vụ

## 1. Bài toán thực hành và ranh giới trách nhiệm

Một ứng dụng bán hàng Java có bảng `app_user`, vai trò toàn hệ thống (ví dụ `USER`, `SUPPORT`), quyền nghiệp vụ (ví dụ `REPORT_READ`) và vai trò/quyền theo từng tổ chức (tenant). Người dùng phải đăng nhập bằng username/password đang lưu trong database, sau đó chỉ truy cập những chức năng và bản ghi họ thật sự được phép xem.

**Mục tiêu:** viết một `UserDetailsService` của ứng dụng để tải tài khoản và tập quyền từ dữ liệu nghiệp vụ, giao kiểm tra mật khẩu cho `DaoAuthenticationProvider`, đưa quyền vào `GrantedAuthority` đúng ngữ nghĩa và kiểm tra quyền **theo tenant/đối tượng** ngay tại service. Đây là phần **Thực hành tổng hợp** của module **Spring Security - authentication**, không chỉ là hướng dẫn tạo một in-memory user.

Phân biệt bốn nhiệm vụ:

1. **User lookup** — `UserDetailsService.loadUserByUsername(String)` tìm account trong nguồn dữ liệu, trả `UserDetails` có password hash, flags và authorities, hoặc ném `UsernameNotFoundException`. Nó **không tự xác thực mật khẩu**.
2. **Password authentication** — `DaoAuthenticationProvider` lấy `UserDetails`, gọi `PasswordEncoder.matches(raw, hash)` và kiểm tra trạng thái account; trả `Authentication` sau khi hợp lệ.
3. **Global authorization** — `SecurityFilterChain` và `@PreAuthorize` kiểm tra authority/role gắn trên `Authentication`; ví dụ `ROLE_SUPPORT` hoặc `PERM_REPORT_READ`.
4. **Tenant/object authorization** — logic nghiệp vụ xác minh `userId` hiện tại còn membership hợp lệ ở tenant đó và có quyền trên tài nguyên cụ thể. **Không** biến vai trò “admin của tenant A” thành `ROLE_ADMIN` toàn hệ thống.

### Kiến trúc tổng quan

~~~text
POST /login (username, password, CSRF token)
             |
             v
UsernamePasswordAuthenticationFilter
             |
             v
AuthenticationManager / ProviderManager
             |
             v
DaoAuthenticationProvider
       |                 |
       |                 +-- PasswordEncoder.matches(raw, storedHash)
       v
DomainUserDetailsService.loadUserByUsername(username)
       |
       +-- Normalize login consistent with signup
       +-- AccountDataPort / JDBC-JPA database adapter
       +-- AccountSnapshot (id, hash, enabled, locked)
       +-- Global roles and global permissions from DB
       +-- Map to ROLE_... / PERM_...
       |
       v
DomainPrincipal implements UserDetails
             |
        success / failure
             |
       SecurityContext for session
             |
       AuthorizationFilter / @PreAuthorize
             |
       TenantPermissionLookup(userId, tenantId, permission)
             |
       Business query constrained by tenant ID
~~~

Nếu provider trả Authentication đã xác thực, điều đó vẫn **không đủ** để đọc đơn hàng của bất kỳ tenant nào. Cần kết hợp quyền chức năng và quyền truy cập **đúng bản ghi** theo dữ liệu hiện tại.

### Các kết quả người học phải tự chứng minh

- Login đúng password hash thành công; login sai/username không tồn tại bị từ chối mà không lộ account tồn tại.
- Disabled/locked user không đăng nhập, kể cả mật khẩu đúng.
- `hasRole("SUPPORT")` khớp `ROLE_SUPPORT`; `hasAuthority("PERM_REPORT_READ")` khớp đúng chuỗi quyền.
- Không có quyền trong DB thì **không** có authority chỉ vì frontend gửi claim/role.
- Admin của tenant A không được xem dữ liệu tenant B bằng cách đổi `tenantId` trong URL.
- Khi role/membership thay đổi, hệ thống có policy làm mới/từ chối **những session hoặc token đã tạo trước đó**; không mặc định mọi Principal tự cập nhật.
- Test DAO/user service, provider, HTTP filter và business authorization ở **những tầng tương ứng**.

## 2. Hiểu đúng UserDetailsService trong Spring Security

Giao diện của Spring Security có một phương thức chính:

~~~java
package org.springframework.security.core.userdetails;

public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

Đây là **chữ ký rút gọn để giải thích**. `UserDetailsService` không nhận password, OTP, request body hoặc tenantId từ browser. Nó không thay `AuthenticationProvider`. Khi form login qua provider DAO, Spring Security nhận `UsernamePasswordAuthenticationToken` chứa raw password, tải `UserDetails` bằng service rồi dùng encoder kiểm tra.

Các thuộc tính `UserDetails` cần được triển khai có chủ đích:

| Thuộc tính / method | Giá trị và ý nghĩa |
| --- | --- |
| `getUsername()` | Login canonical hoặc định danh đã chọn; ổn định, không tùy tiện dựa email display |
| `getPassword()` | Mật khẩu đã hash/encode (ví dụ `{bcrypt}...`), **không** plaintext |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` gồm global roles/permissions đúng schema |
| `isEnabled()` | User còn được phép đăng nhập không? |
| `isAccountNonLocked()` | `false` khi account bị khóa |
| `isAccountNonExpired()` | Có policy hết hạn account không? |
| `isCredentialsNonExpired()` | Credential hiện còn hiệu lực theo policy không? |

Theo tài liệu Spring Security 6.5, `DaoAuthenticationProvider` dùng `UserDetailsService` và `PasswordEncoder`, rồi kết quả thường giữ `UserDetails` làm principal. Nếu muốn đưa local user ID vào principal, có thể tạo class `UserDetails` riêng. Nếu chỉ cần username và authorities, `org.springframework.security.core.userdetails.User` có thể đủ.

### Không trộn authenticate với lookup

**Sai:** trong `loadUserByUsername`, tự lấy raw password từ `SecurityContextHolder`, so sánh với DB, rồi trả `UserDetails` nếu đúng. Cách đó phá ranh giới provider, gây khó test và thường bỏ qua cơ chế encoder, lockout, audit/credential erasure.

**Đúng:** service chỉ tìm data và ánh xạ sang `UserDetails`. `DaoAuthenticationProvider` thực hiện kiểm tra password; `AuthenticationFailureHandler`/entry point xử lý lỗi công khai, audit logger xử lý reason nội bộ.

### Username normalization và user enumeration

Chọn một quy tắc canonical nhất quán ở **đăng ký, đổi username và đăng nhập**. Ví dụ cho sản phẩm coi email là username: strip khoảng trắng biên và lowercase `Locale.ROOT`, lưu `login_norm` có unique constraint. Nhưng quy tắc Unicode/IDN, case sensitivity và email alias cần được sản phẩm định nghĩa; **không tự đoán hai địa chỉ tương đương** rồi merge account.

Khi lookup không thấy, ném `UsernameNotFoundException`. `DaoAuthenticationProvider` mặc định thường che lỗi unknown user bằng `BadCredentialsException`; vẫn cần kiểm tra HTTP response, response time, rate limiting, dummy password-hash compare nếu phù hợp. Không đưa `username exists` hoặc `account locked` ra API anonymous theo cách hỗ trợ user enumeration.

## 3. Cấu trúc database: dữ liệu thật dẫn tới GrantedAuthority

Ví dụ PostgreSQL rút gọn:

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    login_norm VARCHAR(254) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    security_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE global_user_role (
    user_id UUID NOT NULL REFERENCES app_user(id),
    role_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, role_code)
);

CREATE TABLE global_user_permission (
    user_id UUID NOT NULL REFERENCES app_user(id),
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, permission_code)
);

CREATE TABLE tenant_membership (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE tenant_member_permission (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, permission_code),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_membership (tenant_id, user_id)
);
~~~

Đây là schema **học tập**, chưa có audit, soft-delete, FK tenant, role catalog, permission catalog, migrations hoặc tenant ownership rules. Production cần danh mục role/permission đáng tin, validation khi cấp quyền, least privilege và audit người phê duyệt. Đặc biệt **không nhận mã role/permission trực tiếp từ body request đăng nhập** để tạo authority.

### Hai mức quyền

- **Global role**: `SUPPORT` là vai trò toàn hệ thống và có thể ánh xạ thành `ROLE_SUPPORT`; chỉ cấp bởi quy trình quản trị đáng tin, không từ tenant membership.
- **Global permission**: `REPORT_READ` ánh xạ thành `PERM_REPORT_READ`, so khớp bằng `hasAuthority("PERM_REPORT_READ")`.
- **Tenant permission**: Alice có `INVOICE_READ` trong tenant T1, nhưng không có trong T2. Đây là quan hệ **(userId, tenantId, permission)**, cần kiểm tra tại request/service, không biến thành global `PERM_INVOICE_READ` nếu không có ràng buộc scope.
- **Object ownership**: ngoài membership, truy vấn dữ liệu cũng phải buộc `invoice.tenantId == requestedTenantId` và policy owner/workspace; tránh IDOR.

Ví dụ dữ liệu:

| user | global role | global permission | tenant | tenant permission |
| --- | --- | --- | --- | --- |
| Alice | `USER` | `REPORT_READ` | T1 | `INVOICE_READ` |
| Alice | `USER` | `REPORT_READ` | T2 | *(không có)* |
| Bob | `SUPPORT` | *(không có)* | T2 | `INVOICE_READ` |

Với Alice, authorities toàn hệ thống chỉ có `ROLE_USER` và `PERM_REPORT_READ`. Alice **không** có `ROLE_ADMIN` chỉ vì là quản trị một tenant nào đó. Để xem invoice T1 cần thêm membership ở T1; thay URL sang T2 phải bị từ chối.

### Quy tắc tên authority

`hasRole("SUPPORT")` mặc định kiểm `ROLE_SUPPORT`; **không** truyền `hasRole("ROLE_SUPPORT")` vì DSL đã thêm prefix. `hasAuthority("PERM_REPORT_READ")` so khớp nguyên văn chuỗi `PERM_REPORT_READ`, không tự thêm tiền tố. Chọn quy ước và test thống nhất; tránh đưa mỗi màn hình một kiểu role/authority.

**Authority không phải security boundary tự động cho row-level data.** Ngay cả khi `ROLE_SUPPORT` có quyền vào trang support, service vẫn phải giới hạn dữ liệu người đó được phép xem, có thể cần audit/just-in-time elevation cho truy cập liên tenant.

## 4. Dependency và cấu trúc thực hành

Với Spring Boot 3.x được quản lý phiên bản bằng BOM, một project MVC/session authentication tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không cần `spring-security-oauth2-resource-server` nếu chỉ học **username/password bằng DaoAuthenticationProvider**; JWT/OIDC là flow khác. Đừng tự thêm `spring-boot-starter-webflux` rồi dùng Servlet `HttpSecurity` nếu ứng dụng thật là WebFlux — reactive dùng `ReactiveUserDetailsService` và `SecurityWebFilterChain`.

Cấu trúc minh họa:

~~~text
src/main/java/example/security/
  AccountDataPort.java
  DomainPrincipal.java
  DomainUserDetailsService.java
  JdbcAccountDataAdapter.java
  DomainSecurityConfig.java
  TenantAccess.java
  TenantPermissionLookup.java
src/main/java/example/billing/
  InvoiceService.java
src/test/java/example/security/
  DomainUserDetailsServiceTest.java

src/main/resources/
  application.yml
  db/migration/V1__account_auth.sql
~~~

Các file thuộc namespace `example` chỉ là ví dụ tên package; nếu triển khai thật phải có `@SpringBootApplication` và cấu hình datasource/migration. Những đoạn code dưới đây **có thể biên dịch khi đặt cùng package với các dependencies phù hợp**, nhưng chưa là một ứng dụng hoàn chỉnh độc lập vì cần endpoint/data thực. Riêng mục 9 có một chương trình JDK 17 thuần để chạy không cần Spring.

## 5. Tự triển khai UserDetailsService với AccountDataPort

### 5.1. DTO dữ liệu và abstraction đọc account

Tạo file `src/main/java/example/security/AccountDataPort.java`:

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public interface AccountDataPort {
    Optional<AccountSnapshot> findByCanonicalLogin(String login);

    record AccountSnapshot(
            UUID userId,
            String canonicalLogin,
            String encodedPassword,
            boolean enabled,
            boolean locked,
            Set<String> globalRoles,
            Set<String> globalPermissions) {
    }
}
~~~

Port chỉ trả dữ liệu cần để authenticate và xây global authorities. `encodedPassword` phải là hash ở format encoder chấp nhận; không chứa raw password. Không đưa danh sách mọi tenant membership vào principal để biến chúng thành global authorities.

### 5.2. Principal tùy biến có stable user ID

Tạo file `src/main/java/example/security/DomainPrincipal.java`:

~~~java
package example.security;

import java.io.Serial;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.userdetails.UserDetails;

public final class DomainPrincipal
        implements UserDetails, CredentialsContainer {

    @Serial
    private static final long serialVersionUID = 1L;

    private final UUID userId;
    private final String login;
    private String encodedPassword;
    private final boolean enabled;
    private final boolean nonLocked;
    private final List<GrantedAuthority> authorities;

    public DomainPrincipal(
            UUID userId,
            String login,
            String encodedPassword,
            boolean enabled,
            boolean nonLocked,
            Collection<? extends GrantedAuthority> authorities) {

        this.userId = Objects.requireNonNull(userId);
        this.login = Objects.requireNonNull(login);
        this.encodedPassword =
            Objects.requireNonNull(encodedPassword);
        this.enabled = enabled;
        this.nonLocked = nonLocked;
        this.authorities = List.copyOf(authorities);
    }

    public UUID userId() {
        return userId;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return encodedPassword;
    }

    @Override
    public String getUsername() {
        return login;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;  // Thay nếu sản phẩm có account expiry.
    }

    @Override
    public boolean isAccountNonLocked() {
        return nonLocked;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;  // Thay nếu sản phẩm có credential expiry.
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void eraseCredentials() {
        // ProviderManager thường xóa credential sau authentication
        // thành công; không giữ hash trong session nếu không cần.
        this.encodedPassword = null;
    }

    @Override
    public String toString() {
        // Tránh log cả encodedPassword, authorities, PII.
        return "DomainPrincipal[userId=" + userId + "]";
    }
}
~~~

**Tại sao không dùng `record DomainPrincipal(..., encodedPassword)` đơn giản?** `record.toString()` tự sinh có thể lộ password hash trong log. Class ở trên chủ động che thuộc tính và có `CredentialsContainer.eraseCredentials()`. Không log toàn bộ `Authentication`, không đưa hash/authorities vào session ngoài nhu cầu.

**Lưu ý cache:** principal có phương thức `eraseCredentials()` sẽ đổi `encodedPassword` thành null khi ProviderManager xóa credentials. Không cache/chia sẻ **cùng instance** này làm `UserDetails` cho nhiều lần xác thực; nếu bật `UserCache` tùy chỉnh, phải thiết kế clone/caching riêng để không mất password hash trong lần xác thực tiếp theo. Mặc định `NullUserCache` thường dùng cho DAO. Khi cần tránh lưu hash trong session, có thể dùng principal session tách biệt khỏi credential-bearing user details.

### 5.3. Dịch dữ liệu global role/permission thành authorities

Tạo file `src/main/java/example/security/DomainUserDetailsService.java`:

~~~java
package example.security;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class DomainUserDetailsService
        implements UserDetailsService {

    private final AccountDataPort accounts;

    public DomainUserDetailsService(AccountDataPort accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String rawUsername)
            throws UsernameNotFoundException {

        String login = canonicalize(rawUsername);

        AccountDataPort.AccountSnapshot account =
            accounts.findByCanonicalLogin(login)
                .orElseThrow(() ->
                    new UsernameNotFoundException(
                        "Invalid username or password"));

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>();

        for (String role : account.globalRoles()) {
            authorities.add(new SimpleGrantedAuthority(
                "ROLE_" + validCode(role)));
        }
        for (String permission : account.globalPermissions()) {
            authorities.add(new SimpleGrantedAuthority(
                "PERM_" + validCode(permission)));
        }

        return new DomainPrincipal(
            account.userId(),
            account.canonicalLogin(),
            account.encodedPassword(),
            account.enabled(),
            !account.locked(),
            authorities);
    }

    private static String canonicalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new UsernameNotFoundException(
                "Invalid username or password");
        }

        String login = raw.strip().toLowerCase(Locale.ROOT);
        if (login.length() > 254) {
            throw new UsernameNotFoundException(
                "Invalid username or password");
        }
        return login;
    }

    private static String validCode(String value) {
        if (value == null
                || !value.matches("[A-Z][A-Z0-9_]{0,63}")) {
            // Dữ liệu privilege trong DB sai -> fail closed,
            // không âm thầm cấp quyền tùy chuỗi lỗi.
            throw new IllegalStateException(
                "Invalid configured authority code");
        }
        return value;
    }
}
~~~

Mã ví dụ yêu cầu `AccountDataPort` trả hai tập không-null, đã lọc **global** role/permission ACTIVE từ kho dữ liệu đáng tin. Khi permission catalog có dấu chấm/gạch ngang, điều chỉnh bộ kiểm tra `validCode` theo vocabulary được phê duyệt, **không** bỏ validation chỉ vì DB “nội bộ”. Giới hạn tên login/canonicalization phải thống nhất với nhập dữ liệu và unique index.

**Không tự nhận `AccountDataPort.findByCanonicalLogin` từ dữ liệu frontend.** Nguồn quyền chỉ là kho server kiểm soát. Nếu một request gửi `role=ADMIN` hoặc thay cookie `role`, nó không thể thêm authority vào kết quả service.

### 5.4. Nơi đọc DB thực tế: JdbcTemplate

Ví dụ adapter đọc ba tập dữ liệu ở một thời điểm tương đối nhất quán; tạo `src/main/java/example/security/JdbcAccountDataAdapter.java`:

~~~java
package example.security;

import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public final class JdbcAccountDataAdapter
        implements AccountDataPort {

    private final JdbcTemplate jdbc;

    public JdbcAccountDataAdapter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<AccountSnapshot> findByCanonicalLogin(
            String login) {

        List<AccountSnapshot> rows = jdbc.query(
            """
            SELECT id, login_norm, password_hash, enabled, locked
              FROM app_user
             WHERE login_norm = ?
            """,
            (rs, rowNum) -> {
                UUID userId =
                    UUID.fromString(rs.getString("id"));

                Set<String> roles = new HashSet<>(
                    jdbc.queryForList(
                        """
                        SELECT role_code FROM global_user_role
                         WHERE user_id = ?
                        """,
                        String.class, userId));

                Set<String> permissions = new HashSet<>(
                    jdbc.queryForList(
                        """
                        SELECT permission_code
                          FROM global_user_permission
                         WHERE user_id = ?
                        """,
                        String.class, userId));

                return new AccountSnapshot(
                    userId,
                    rs.getString("login_norm"),
                    rs.getString("password_hash"),
                    rs.getBoolean("enabled"),
                    rs.getBoolean("locked"),
                    Set.copyOf(roles),
                    Set.copyOf(permissions));
            },
            login);

        if (rows.size() > 1) {
            // Unique constraint đáng lẽ ngăn điều này.
            throw new IllegalStateException(
                "Duplicate canonical logins");
        }
        return rows.stream().findFirst();
    }
}
~~~

**Quan trọng:** ví dụ đang gọi hai query trong `RowMapper` để dễ đọc. Nó vẫn có thể chạy ở case **một account**, nhưng style production nên tách việc query account khỏi query role/permission, rồi load tập quyền bằng batch/join thích hợp; nếu dùng cho danh sách nhiều users sẽ biến thành **N+1**. `@Transactional(readOnly=true)` không tự bảo đảm snapshot ở isolation level cao: với nhiều câu SQL, trạng thái role có thể thay giữa các query ở một số hệ quản trị và isolation; nếu policy cần strong consistency, dùng transaction isolation và query strategy được thiết kế rõ.

Dùng parameter binding `?` để tránh SQL injection; không nối `username` vào SQL string. Với PostgreSQL `UUID`, ví dụ `UUID.fromString(rs.getString("id"))` giả định driver trả biểu diễn UUID chuẩn. Dùng migration/index và tenant isolation đúng môi trường.

### 5.5. Không truy vấn quyền quá rộng

Ở thời điểm load UserDetails, chỉ cần **global authorities** và các flags đủ để quyết định login. Nếu user có 2.000 tenant memberships, đừng nhồi tất cả vào Session Principal rồi cho rằng đó là snapshot luôn mới. Với tenant membership, kiểm tra quyền theo `(userId, tenantId, action)` tại service/method boundary, có cache/invalidation riêng và policy rõ.

## 6. PasswordEncoder và DaoAuthenticationProvider thực hiện xác thực

### 6.1. Cấu hình Spring Security Servlet 6.5.x

Tạo file `src/main/java/example/security/DomainSecurityConfig.java`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class DomainSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Mặc định encode mới theo id prefix, thường {bcrypt}.
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationProvider domainAuthenticationProvider(
            DomainUserDetailsService users,
            PasswordEncoder passwords) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(passwords);
        return provider;
    }

    @Bean
    SecurityFilterChain appSecurityFilterChain(
            HttpSecurity http,
            AuthenticationProvider domainAuthenticationProvider)
            throws Exception {

        return http
            .authenticationProvider(domainAuthenticationProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error",
                                 "/public/**").permitAll()
                .requestMatchers("/support/**").hasRole("SUPPORT")
                .requestMatchers("/reports/**")
                    .hasAuthority("PERM_REPORT_READ")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Dùng `new DaoAuthenticationProvider(users)` là constructor được hỗ trợ trong Spring Security 6.5; `DaoAuthenticationProvider()` không tham số đã deprecated. `setPasswordEncoder(...)` chính xác là cách cấu hình encoder. Một bean `AuthenticationProvider` plus khai báo nó trong chain sẽ làm ý định wiring rõ hơn; **nếu app có nhiều security chains/providers/AuthenticationManager**, phải kiểm tra provider nào thật sự nhận request, không tạo trùng provider vô tình.

**Lưu ý security:** không `csrf.disable()` với form login/session cookies chỉ để test pass. POST `/login` cần CSRF theo chính sách mặc định. Với API JSON login riêng, phải có filter/converter và failure handler đúng Content-Type/HTTP status, không coi ví dụ form login là JSON API hoàn chỉnh.

### 6.2. Hash đúng và migrate password

Mật khẩu database phải ở định dạng encoder hỗ trợ, ví dụ:

~~~text
{bcrypt}$2a$10$.....................................................
~~~

Chuỗi chỉ minh họa cấu trúc, **không phải bcrypt hash dùng được**. Không lưu plaintext hay tự SHA-256(password) không salt/chi phí. Với `DelegatingPasswordEncoder`, tiền tố `{id}` cho phép chọn encoder cho hash cũ và tạo hash mới theo encoder hiện hành. Không đưa `{noop}` vào production; `{noop}` chỉ có thể dùng trong **fixture test** và phải được kiểm soát.

Flow đúng:

~~~text
registration / password reset:
  raw password -> PasswordEncoder.encode() -> store hash

login:
  raw password in request
  -> DaoAuthenticationProvider
  -> UserDetailsService loads stored hash
  -> PasswordEncoder.matches(raw, storedHash)
  -> status checks + authenticated principal
~~~

Đừng tự gán quyền administrator chỉ vì user lưu password hash đúng. Authentication không thay authorization.

### 6.3. Account flags và đăng xuất khi thay quyền

`isEnabled()` và `isAccountNonLocked()` giúp `DaoAuthenticationProvider` chặn account ở lần **login mới**. Nhưng nếu account vừa bị khóa hoặc role vừa bị thu hồi, một `Authentication` đã nằm trong `HttpSession` có thể tiếp tục chứa authorities **cũ** nếu app không kiểm tra lại. Phải chọn chiến lược:

- Invalidate sessions qua Spring Session/indexed repository, đồng thời ngăn account bị khóa tạo session mới.
- Hoặc lưu `securityVersion` lúc issue session và so với DB/Redis khi request quan trọng; đổi role/password/locked tăng version và buộc re-auth.
- Với JWT Access Token đã phát, verifier offline không tự cập nhật role/locked; cần TTL ngắn, revoke/denylist/check trạng thái ở mọi Resource Server theo risk budget.
- Với quyền theo tenant, có thể kiểm tra DB live tại service thay vì cache tất cả membership trong principal; vẫn phải cân nhắc cache TTL/consistency.
- Không chỉ xóa role ở DB rồi đảm bảo ngay mọi request cũ bị 403 khi role vẫn nằm trong session.

## 7. Kiểm tra quyền nghiệp vụ theo tenant, tránh IDOR

Một quyền `PERM_INVOICE_READ` toàn cục có thể nguy hiểm: user là kế toán tenant A nhưng URL `/tenants/B/invoices/123` lại được chấp nhận nếu service chỉ gọi `hasAuthority("PERM_INVOICE_READ")`. Quyền thực tế phải là **(localUserId, tenantId, permission, resource scope)**.

### 7.1. Port kiểm tra quyền tenant

Tạo `src/main/java/example/security/TenantPermissionLookup.java`:

~~~java
package example.security;

import java.util.UUID;

public interface TenantPermissionLookup {
    boolean hasActivePermission(
        UUID userId, UUID tenantId, String permission);
}
~~~

Một implementation PostgreSQL dùng bảng ở mục 3:

~~~java
package example.security;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcTenantPermissionLookup
        implements TenantPermissionLookup {

    private final JdbcTemplate jdbc;

    public JdbcTenantPermissionLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean hasActivePermission(
            UUID userId, UUID tenantId, String permission) {

        Boolean found = jdbc.queryForObject(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM tenant_membership m
                  JOIN tenant_member_permission p
                    ON p.tenant_id = m.tenant_id
                   AND p.user_id = m.user_id
                 WHERE m.tenant_id = ?
                   AND m.user_id = ?
                   AND m.status = 'ACTIVE'
                   AND p.permission_code = ?
            )
            """,
            Boolean.class, tenantId, userId, permission);

        return Boolean.TRUE.equals(found);
    }
}
~~~

**Cần kiểm tra thêm:** account hiện không LOCKED/DISABLED theo policy, tenant ACTIVE, role granting history, owner/collaborator relationships, permission catalog và trường hợp database không truy vấn được. Ví dụ SQL fail closed ở tầng boolean khi trả false, nhưng exception/timeout sẽ lan lên; error handler phải phân biệt outage với thiếu quyền để vận hành xử lý, không lặng lẽ “allow”.

### 7.2. Bean service-side authorization

Tạo `src/main/java/example/security/TenantAccess.java`:

~~~java
package example.security;

import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public final class TenantAccess {

    private final TenantPermissionLookup permissions;

    public TenantAccess(TenantPermissionLookup permissions) {
        this.permissions = permissions;
    }

    public boolean canReadInvoice(
            Authentication authentication, UUID tenantId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal()
                     instanceof DomainPrincipal principal)) {
            return false;
        }

        return permissions.hasActivePermission(
            principal.userId(), tenantId, "INVOICE_READ");
    }
}
~~~

Vì `TenantAccess` lấy `userId` từ `DomainPrincipal` đã được authenticate, một browser không thể yêu cầu quyền của Bob chỉ bằng cách gửi `userId=bob`. Tuy nhiên, bean này giả định Authentication là local `DomainPrincipal`; khi app tích hợp OIDC/JWT principal khác, cần ánh xạ đã xác minh về local user ID **trước** khi áp rule, không ép kiểu mù.

### 7.3. Chặn cả endpoint lẫn câu truy vấn

Trong service có `InvoiceRepository` phù hợp, một ví dụ **snippet** (không phải file chạy độc lập) là:

~~~java
@PreAuthorize(
    "@tenantAccess.canReadInvoice(authentication, #tenantId)")
public Invoice readInvoice(UUID tenantId, UUID invoiceId) {
    return invoices.findByIdAndTenantId(invoiceId, tenantId)
        .orElseThrow(NotFoundException::new);
}
~~~

Đây là snippet cần method nằm trên một Spring-managed service bean, `Invoice`, `NotFoundException` và repository do ứng dụng định nghĩa; có thể đặt `@P("tenantId")` hoặc bật `-parameters` để Spring method security nhận đúng tham số `#tenantId`. `@EnableMethodSecurity` đã bật ở cấu hình mục 6. **Không** dựa chỉ vào `@PreAuthorize("hasRole('USER')")` rồi query `findById(invoiceId)` nếu invoice thuộc tenant khác.

Nếu cần kiểm tra quyền chi tiết trên **invoice** (owner, project, sensitivity), query/rule phải xét cả `invoiceId` và quan hệ sở hữu, không chỉ membership tenant. Với tài liệu cross-tenant, dùng `findByIdAndTenantId` giúp ràng buộc phạm vi dữ liệu, nhưng service vẫn phải kiểm tra quyền nghiệp vụ.

### 7.4. Object authorization không được lưu vĩnh viễn trong principal

Một người có thể đổi vai trò khỏi tenant A trong khi vẫn đăng nhập. Nếu authority `TENANT_A_ADMIN` được nhồi vào session và không invalidated, quyền cũ vẫn có thể hoạt động. Với quyền theo tenant/đơn hàng biến động thường xuyên, nên kiểm tra lại từ nguồn được tin (và cache có version/TTL/invalidation theo policy), đồng thời giới hạn transaction boundary để tránh TOCTOU ở các thao tác tài chính.

**Mối nguy time-of-check/time-of-use:** user còn membership khi `canReadInvoice` được gọi nhưng đã bị revoke trước khi service cập nhật dữ liệu. Với write nhạy cảm, có thể cần kiểm tra/khóa lại quyền trong transaction thao tác, hoặc dùng versioned permissions và DB constraints. Không khẳng định một annotation đơn lẻ là kiểm soát atomic toàn bộ giao dịch.

## 8. Test thành phần: từ DB snapshot tới UserDetails và DaoAuthenticationProvider

### 8.1. Unit test UserDetailsService không cần Spring context

Một file `src/test/java/example/security/DomainUserDetailsServiceTest.java` với JUnit 5 (đặt cùng package với các class ở mục 5):

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DomainUserDetailsServiceTest {

    private static final UUID ALICE_ID =
        UUID.fromString("00000000-0000-0000-0000-000000000001");

    private static AccountDataPort fakePort() {
        return login -> {
            if (!"alice@example.test".equals(login)) {
                return Optional.empty();
            }
            return Optional.of(
                new AccountDataPort.AccountSnapshot(
                    ALICE_ID,
                    "alice@example.test",
                    "{noop}demo-password",
                    true,
                    false,
                    Set.of("USER", "SUPPORT"),
                    Set.of("REPORT_READ")));
        };
    }

    @Test
    void loadsCanonicalUserAndMapsAuthorities() {
        var service = new DomainUserDetailsService(fakePort());
        UserDetails user =
            service.loadUserByUsername(" ALICE@EXAMPLE.TEST ");

        assertEquals("alice@example.test", user.getUsername());
        assertTrue(user.isEnabled());
        assertTrue(user.isAccountNonLocked());

        var names = user.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .collect(java.util.stream.Collectors.toSet());

        assertEquals(
            Set.of("ROLE_USER", "ROLE_SUPPORT",
                   "PERM_REPORT_READ"),
            names);
    }

    @Test
    void missingUserDoesNotCreatePrincipal() {
        var service = new DomainUserDetailsService(fakePort());
        assertThrows(UsernameNotFoundException.class,
            () -> service.loadUserByUsername("unknown@example.test"));
    }

    @Test
    void lockedUserProducesNonLockedFalse() {
        AccountDataPort port = login -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                ALICE_ID, login, "{noop}demo-password",
                true, true,
                Set.of("USER"), Set.of()));

        var service = new DomainUserDetailsService(port);
        assertFalse(service.loadUserByUsername(
            "alice@example.test").isAccountNonLocked());
    }

    @Test
    void invalidPrivilegeCodeFailsClosed() {
        AccountDataPort port = login -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                ALICE_ID, login, "{noop}demo-password",
                true, false,
                Set.of("ROLE_ADMIN/unsafe"), Set.of()));

        var service = new DomainUserDetailsService(port);
        assertThrows(IllegalStateException.class,
            () -> service.loadUserByUsername("alice@example.test"));
    }
}
~~~

**Đọc đúng kết quả:** các tests chứng minh mapping và account flags của custom `UserDetailsService`, **không** chứng minh `PasswordEncoder` hay HTTP login, vì `fakePort` trả snapshot có hash fixture. `{noop}` chỉ xuất hiện trong test; không dùng trong production. Test chỉ chạy đúng nếu các class mục 5 nằm cùng package và dependency test có JUnit 5 + Spring Security.

### 8.2. Integration nhẹ với DaoAuthenticationProvider

Snippet sau có thể đặt thành `DomainDaoProviderTest.java` cùng package; dùng encoder thực và hash được tạo ngay trong test:

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DomainDaoProviderTest {

    private DaoAuthenticationProvider provider(
            boolean enabled, boolean locked) {

        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String encoded = encoder.encode("safe-demo-password");

        AccountDataPort port = username -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000001"),
                username, encoded, enabled, locked,
                Set.of("USER"), Set.of("REPORT_READ")));

        var provider = new DaoAuthenticationProvider(
            new DomainUserDetailsService(port));
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Test
    void correctPasswordIsAuthenticated() {
        var result = provider(true, false).authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice@example.test", "safe-demo-password"));

        assertTrue(result.isAuthenticated());
        assertEquals("alice@example.test", result.getName());
    }

    @Test
    void wrongPasswordFails() {
        assertThrows(BadCredentialsException.class,
            () -> provider(true, false).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "wrong-password")));
    }

    @Test
    void disabledAccountFailsEvenWithCorrectPassword() {
        assertThrows(DisabledException.class,
            () -> provider(false, false).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "safe-demo-password")));
    }

    @Test
    void lockedAccountFailsEvenWithCorrectPassword() {
        assertThrows(LockedException.class,
            () -> provider(true, true).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "safe-demo-password")));
    }
}
~~~

Tests này gọi provider **trực tiếp**, nên không kiểm thử `ProviderManager` erasure, SecurityContext persistence, CSRF, filter chain, redirect hay error contract. Không hardcode mã lỗi HTTP dựa trên exception class khi app chọn form login redirect. Nếu cần kiểm tra rằng credentials được xóa khỏi principal sau login thành công, tạo `ProviderManager` thật với provider và kiểm tra authentication returned qua manager; ProviderManager có cơ chế `eraseCredentialsAfterAuthentication` theo cấu hình.

**Hạn chế fixture:** `provider(true,false)` trả snapshot cho mọi login name vì test chỉ kiểm tra password/status; use-case unknown username được test riêng ở `DomainUserDetailsServiceTest`. Trong production, repository luôn tra canonical username thật và có unique index; không sao chép fakePort này vào application.

## 9. Java 17 độc lập: ánh xạ quyền nghiệp vụ và cô lập tenant

Ví dụ sau dùng **JDK 17 thuần**, không phụ thuộc Spring, DB hay test framework. Mục đích minh họa quy tắc domain độc lập: role/permission toàn cục được ánh xạ thành authority, còn quyền từng tenant **được kiểm tra qua tenantId**, không nâng lên role global.

Tạo file `AuthorityMappingDemo.java`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public class AuthorityMappingDemo {

    record Membership(
            String tenantId,
            Set<String> permissions) {
    }

    record Account(
            String userId,
            Set<String> globalRoles,
            Set<String> globalPermissions,
            List<Membership> memberships) {
    }

    static SortedSet<String> globalAuthorities(Account account) {
        SortedSet<String> result = new TreeSet<>();

        for (String role : account.globalRoles()) {
            result.add("ROLE_" + role);
        }
        for (String permission : account.globalPermissions()) {
            result.add("PERM_" + permission);
        }
        return java.util.Collections.unmodifiableSortedSet(result);
    }

    static boolean canReadInvoice(
            Account account, String tenantId) {

        return account.memberships().stream().anyMatch(
            membership ->
                membership.tenantId().equals(tenantId)
                    && membership.permissions()
                        .contains("INVOICE_READ"));
    }

    public static void main(String[] args) {
        Account alice = new Account(
            "alice",
            Set.of("USER"),
            Set.of("REPORT_READ"),
            List.of(
                new Membership("tenant-A",
                    Set.of("INVOICE_READ")),
                new Membership("tenant-B",
                    Set.of("INVOICE_WRITE"))));

        SortedSet<String> authorities =
            globalAuthorities(alice);

        System.out.println("authorities=" + authorities);
        System.out.println("tenantARead="
            + canReadInvoice(alice, "tenant-A"));
        System.out.println("tenantBRead="
            + canReadInvoice(alice, "tenant-B"));
        System.out.println("globalAdmin="
            + authorities.contains("ROLE_ADMIN"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AuthorityMappingDemo.java
java AuthorityMappingDemo
~~~

**Stdout chính xác** (dùng `TreeSet` nên thứ tự cố định):

~~~text
authorities=[PERM_REPORT_READ, ROLE_USER]
tenantARead=true
tenantBRead=false
globalAdmin=false
~~~

Nhìn vào hai kiểm tra `tenantARead=true` và `tenantBRead=false`: Alice có quyền đọc invoice ở A nhưng chỉ có quyền viết ở B. **Đừng diễn giải "có ít nhất một tenant với INVOICE_READ" thành "được đọc invoice ở mọi tenant".** `globalAdmin=false` chứng minh user không được nâng lên quyền toàn hệ thống.

**Giới hạn:** ví dụ không có real authenticated principal, không enforce allowed permission vocabulary, chưa kiểm tra membership ACTIVE, invoice ownership, revoke hay consistency. Các mục 5–7 trình bày cách ghép nó với Spring Security và database đáng tin.

## 10. Test HTTP và quyền đối tượng: điều unit test chưa đủ

### 10.1. Từ mock principal tới login thực

| Mục đích | Cấp độ test | Công cụ phù hợp | Điều **chưa** được chứng minh |
| --- | --- | --- | --- |
| Mapping role/permission từ snapshot | Unit `DomainUserDetailsServiceTest` | Fake AccountDataPort | DB query thật, password validation |
| Password hash, disabled/locked | Provider test | `DaoAuthenticationProvider` + encoder thật | Filter chain, CSRF, session |
| Route /support yêu cầu ROLE_SUPPORT | MockMvc test | `@WithMockUser` hoặc `user(...)` | Custom UserDetailsService đã được gọi |
| POST /login với password thật trong test DB | Integration | MockMvc + SecurityFilterChain + JdbcAccountDataAdapter | External SSO/JWT, multi-node |
| Bảo vệ tenant ID | Service/HTTP integration | `@PreAuthorize` + repository scoped query | Không bao phủ mọi endpoint khác |
| Quyền bị revoke khi đang đăng nhập | Session/token integration | Hai requests, thay DB, check fresh authorization | Chưa bảo đảm nếu không test multi-node |
| Tải tài khoản từ JDBC | Integration database | Testcontainers/Postgres hoặc DB test thật | Tính bảo mật của filter mặc định |
| OAuth/JWT login cùng user ID | Integration riêng | OIDC test IdP, JWT decoder | Không bao gồm password Dao path |

### 10.2. MockMvc form login nên kiểm tra gì?

Đây là **snippet đặt trong test class có `MockMvc mvc`, datasource/fixtures thật và security filter chain**; nó không phải file Java độc lập:

~~~java
// Đã chuẩn bị alice@example.test với hash tạo bởi PasswordEncoder,
// global role USER và permission REPORT_READ.

// Login đúng: status thường là 302 redirect theo formLogin().
mvc.perform(formLogin()
        .user("alice@example.test")
        .password("correct-password"))
   .andExpect(authenticated()
       .withUsername("alice@example.test"));

// Login sai: vẫn phải thất bại, không cấp phiên đã xác thực.
mvc.perform(formLogin()
        .user("alice@example.test")
        .password("wrong-password"))
   .andExpect(unauthenticated());
~~~

Các phương thức này thuộc `spring-security-test`, cần static imports `formLogin` từ `SecurityMockMvcRequestBuilders` và `authenticated/unauthenticated` từ `SecurityMockMvcResultMatchers`, áp dụng Spring Security Test integration cho MockMvc. `formLogin()` mô phỏng post /login với CSRF token phù hợp theo test helper. Kiểm tra thêm redirect/response riêng nếu UX yêu cầu, và đảm bảo test không thay `UserDetailsService` bằng bean mock. Không dùng `@WithMockUser` cho test phải chứng minh JDBC password flow; annotation ấy đã **bỏ qua đăng nhập thật**.

### 10.3. Test IDOR/cross-tenant

Test ít nhất:

1. Alice có `INVOICE_READ` ở tenant A, `GET /tenants/A/invoices/1` được phép nếu invoice thực thuộc A.
2. Alice đổi URI sang tenant B dù cùng invoice ID: phải bị từ chối hoặc không tìm thấy, không lộ dữ liệu.
3. Alice là global `ROLE_USER` nhưng không có membership ở B: không vì role USER mà được phép xem B.
4. Bob được quyền trong B nhưng request vào invoice thuộc A: repository query phải ràng buộc tenant.
5. Session của Alice giữ quyền cũ sau khi membership A bị revoke: theo policy phải buộc request sau từ chối hoặc có documented cache TTL; test phải tái hiện.
6. User bị locked: login mới bị từ chối, và nếu yêu cầu khóa có hiệu lực tức thời thì **session cũ cũng** phải bị từ chối bằng guard/session revoke.
7. Lỗi DB permission lookup: không được biến exception thành `allow=true`.
8. Direct service call không qua HTTP controller: method security/transaction vẫn áp policy; không đặt mọi kiểm tra chỉ ở controller.

**Tránh lỗi cú pháp quyền:** `@WithMockUser(roles="ADMIN")` dựng `ROLE_ADMIN`, còn `@WithMockUser(authorities="PERM_REPORT_READ")` dựng authority nguyên văn. Không trộn hai phương thức mà vô tình làm test luôn pass vì user có quyền quá rộng.

### 10.4. 401 so với 403

- Chưa authenticated đến protected endpoint: API thường trả 401, browser form login có thể redirect tới `/login`.
- Đã authenticated, thiếu `PERM_REPORT_READ` hoặc quyền tenant: thường 403 (hoặc 404 nhằm hạn chế lộ tài nguyên theo policy), **không** trả 401 để client cứ thử login lại.
- Username không tồn tại/password sai: form login có thể redirect tới `/login?error`; REST JSON login tùy failure handler.
- Account bị disable/locked: Spring provider ném `DisabledException`/`LockedException` theo trạng thái; public message nên cân nhắc chống user enumeration, không lộ lý do riêng ở anonymous login.

## 11. Những rủi ro vận hành sau khi triển khai

### 11.1. Thay quyền trong database không đồng nghĩa mọi session cập nhật

Một `Authentication` đã được lưu trong `HttpSession` thường chứa authorities lúc login. Nếu admin xóa `REPORT_READ` trong database sau đó, service `loadUserByUsername` **không chắc chạy lại trên request đã có session**. Để đáp ứng SLA thu hồi quyền:

- Dùng account/authority version trên principal và nguồn trạng thái server, kiểm tra trong request quan trọng;
- invalidate session qua Spring Session hoặc session registry phù hợp; với nhiều node cần store/consistency chung;
- kiểm tra permission tenant live (hoặc cache có TTL/invalidation) thay vì tin snapshot quyền không giới hạn;
- nếu API dùng JWT self-contained, resource server cần kiểm tra denylist/version/status hoặc chấp nhận residual TTL rõ ràng;
- khi thay membership/role, phát event invalidation và kiểm thử với browser B đang logged in.

### 11.2. Hiệu năng và N+1

- Loading DB account+roles+permissions bằng nhiều query chỉ cho một login thường khả thi nhưng phải có index. Đừng thực hiện 1 query cho mỗi authority rồi tạo N+1.
- Nếu user có hàng nghìn tenant, đừng đưa mọi membership vào principal/session, gây bloat/caching stale và khó serialize.
- Cache UserDetails phải có invalidation khi lock, đổi mật khẩu, đổi quyền; đặc biệt chú ý principal đã được `CredentialsContainer.eraseCredentials()`.
- Query `tenant_member_permission` có index theo `(tenant_id, user_id, permission_code)` và membership status.
- Không dùng `SecurityContextHolder` hay blocking JDBC trong pipeline WebFlux event-loop; WebFlux cần reactive authentication design và R2DBC/offload theo policy.
- Khi DB không khả dụng, đừng lặng lẽ trả user giả/role mặc định; classify infrastructure failure, áp availability policy và alert.

### 11.3. Audit, least privilege và boundary

- Ai cấp role/permission? Phải có audit event gồm actor, target user, tenant, mã quyền, nguồn phê duyệt, timestamp và lý do.
- Ai được đổi `global_user_role`? Endpoint này cần step-up và permission riêng, không dựa role lấy từ input.
- Tách `ROLE_SUPPORT` khỏi quyền truy cập dữ liệu khách hàng; support có thể cần just-in-time, read-only, masking và case ID.
- Không log password, encoded hash, session cookie, OTP, access token/refresh token, hoặc toàn bộ `UserDetails`.
- Khi cần support tra cứu user, response lỗi public không tiết lộ account tồn tại hay trạng thái locked bằng code riêng.
- Test tenant mismatch, time-of-check/time-of-use và login session cũ sau revoke, không chỉ happy path.

## 12. Những lỗi phổ biến và cách tránh

1. **Tự `password.equals(rawPassword)` trong UserDetailsService**: sai ranh giới. Provider + PasswordEncoder chịu trách nhiệm kiểm tra.
2. **Ghi plaintext password vào DB**: thay bằng password hash được encode bằng thuật toán được duyệt, có migration strategy.
3. **Không có `{id}` prefix khi dùng DelegatingPasswordEncoder** nhưng lại kỳ vọng matches tự nhận diện hash cũ: phải migrate hoặc cấu hình đúng.
4. **Nhầm role với authority**: `hasRole("SUPPORT")` cần `ROLE_SUPPORT`; `hasAuthority("PERM_REPORT_READ")` cần đúng chuỗi.
5. **Ánh xạ role tenant thành `ROLE_ADMIN` toàn cục**: tạo privilege escalation ngoài tenant.
6. **Cho frontend gửi roles rồi đặt vào Authentication**: bất cứ user nào cũng tự nâng quyền.
7. **Tạo UserDetails bằng email/displayName không canonical**: duplicate accounts, lookup sai và rủi ro identity mapping.
8. **Không có unique constraint trên `login_norm`**: lookup không xác định hoặc nối nhầm account.
9. **Không xử lý locked/disabled flags**: user bị chặn trong DB vẫn login được.
10. **Lạm dụng `@WithMockUser` cho test login DB**: test bypass UserDetailsService và PasswordEncoder thật.
11. **Chỉ kiểm tra `ROLE_USER` rồi trả invoice bằng `findById`**: IDOR/cross-tenant.
12. **Dùng `@PreAuthorize` nhưng quên bật `@EnableMethodSecurity` hoặc method gọi nội bộ không qua Spring proxy**: check có thể không chạy.
13. **Đưa password hash vào `toString()` của record principal**: lộ hash ở logs/traces.
14. **Cache principal có thể bị `eraseCredentials()` làm password hash null**: cache không hợp lệ cho login sau.
15. **Dùng DB role snapshot từ lúc login mãi mãi**: role bị revoke nhưng session vẫn có authority cũ.
16. **Cho `ROLE_SUPPORT` xem dữ liệu mọi tenant mặc định**: thiếu policy least privilege và object-level authorization.
17. **Đổi role mà không bump version/invalidate cache/session**: quyền cũ còn sống trên node khác.
18. **Dùng SQL nối chuỗi username**: SQL injection; hãy dùng parameterized query và constraints.
19. **Biến DB outage thành anonymous user**: che lỗi vận hành và có thể dẫn đến đường fallback không an toàn.
20. **Áp servlet SecurityFilterChain cho WebFlux app**: WebFlux cần ReactiveUserDetailsService/ReactiveAuthenticationManager.
21. **Dùng custom UserDetails để gắn thêm email, token, private info**: principal thường đi vào session/cache/log, phải giảm dữ liệu.
22. **Không test case quyền rỗng/role lạ**: mapper phải fail closed, không tự gán quyền mặc định.

## 13. Checklist hoàn thành bài thực hành

- [ ] Đã thiết kế `app_user` có canonical login unique, password hash, enabled/locked và account ID ổn định.
- [ ] Đã tách global role/permission khỏi tenant membership/permission và resource ownership.
- [ ] `UserDetailsService.loadUserByUsername` chỉ lookup/assemble `UserDetails`, không so raw password.
- [ ] `DaoAuthenticationProvider` được wired với đúng service và `PasswordEncoder`; không có provider khác vô tình bypass.
- [ ] Role/permission đọc từ DB tin cậy, map `ROLE_`/`PERM_` đúng, không nhận từ request body.
- [ ] Custom `DomainPrincipal` không log password hash, hỗ trợ credential erasure và giữ local user ID.
- [ ] Trang/route global dùng `hasRole`/`hasAuthority`; tenant invoice dùng `@PreAuthorize` và repository query scoped.
- [ ] Account locked/disabled và password sai không login; UI không user-enumerate.
- [ ] DB permissions thay đổi có chiến lược session/token invalidation hoặc version/current-state guard.
- [ ] Unit tests cho canonicalization, role mapping, status; provider tests dùng encoder thật.
- [ ] MockMvc integration dùng formLogin đúng, có negative tests cho 401/403/IDOR và CSRF.
- [ ] Có audit grant/revoke, least privilege, safe logging và fail-closed policy khi phụ thuộc security DB lỗi.

**Tóm tắt:** `UserDetailsService` là **cầu nối dữ liệu nghiệp vụ → UserDetails**; `DaoAuthenticationProvider` là nơi xác minh mật khẩu; `GrantedAuthority` chỉ nên phản ánh **global privileges đáng tin** và không thay thế kiểm tra tenant/object quyền thời điểm sử dụng. Thực hành đầy đủ phải có mã nguồn, database constraints, quyền theo scope, test provider/HTTP và cơ chế làm mới quyền khi tài khoản hoặc membership thay đổi.

## 14. Tài liệu chính thức

- Spring Security 6.5 — `UserDetailsService`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html
- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 API — `DaoAuthenticationProvider` constructor và `setPasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — Authorize HTTP Requests, `hasRole` và `hasAuthority`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Password Storage and DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — Testing Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- OWASP — Authorization Cheat Sheet (deny-by-default, object checks): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
