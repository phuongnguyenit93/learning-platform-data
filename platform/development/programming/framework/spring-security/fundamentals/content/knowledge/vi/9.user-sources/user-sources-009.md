# Thay đổi quyền hoặc khóa tài khoản khi người dùng đã có phiên đăng nhập

> **Phạm vi:** Spring Security Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học giải thích vì sao đổi role hoặc `enabled/locked` trong database **không tự động cập nhật `Authentication` đã lưu trong `HttpSession`**, cách thu hồi phiên bằng `SessionRegistry`, vì sao `SessionInformation.expireNow()` có hiệu lực khi request quay lại, những giới hạn với JWT, remember-me, Redis/cluster và cách kiểm thử quyền trước/sau thay đổi. Mã nguồn minh họa dùng form login và session để quan sát vấn đề trực tiếp.

## 1. Bài toán: database đã đổi, trình duyệt vẫn truy cập được?

Alice đăng nhập lúc 09:00. Ứng dụng xác thực password qua `DaoAuthenticationProvider`/`UserDetailsService` và tạo một `Authentication` với `ROLE_ADMIN`. Framework có thể lưu `SecurityContext` chứa Authentication này trong **HttpSession**.

Lúc 09:05, quản trị viên thu hồi role ADMIN của Alice trong database. Nhưng phiên của Alice có thể vẫn chứa:

~~~text
SecurityContext trong HttpSession:
    Authentication.name          = "alice"
    Authentication.authenticated = true
    Authentication.authorities   = ["ROLE_ADMIN"]

Database sau khi bị thay đổi:
    account.username             = "alice"
    account.enabled              = true
    account.roles                = ["ROLE_USER"]
~~~

Nếu endpoint chỉ dùng `.hasRole("ADMIN")` dựa trên `Authentication` hiện tại, request kế tiếp **có thể vẫn được cho phép**, vì quyền cũ còn trong session. Đây là sự khác biệt giữa **nguồn tài khoản lưu bền vững** và **bản chụp trạng thái xác thực** tại thời điểm login.

Tương tự, nếu admin đặt `enabled=false` hay `locked=true` trong database, `DaoAuthenticationProvider` có thể chặn **lần đăng nhập tiếp theo**. Nhưng nó **không mặc định được gọi lại với mọi request** của một session đã xác thực. Phiên cũ có thể tiếp tục hoạt động cho đến khi hết hạn, bị thu hồi hoặc có một cơ chế kiểm tra trạng thái mới.

**Ba nguyên tắc:**

1. **Thay đổi dữ liệu account** không tự đồng nghĩa **thu hồi mọi phiên đã cấp**.
2. `UserDetailsService.loadUserByUsername()` dùng trong quá trình xác thực, không phải một truy vấn quyền tự động theo mọi HTTP request.
3. Muốn thay đổi quyền/khóa account có hiệu lực nhanh, phải quyết định **điểm kiểm tra**, **cơ chế thu hồi**, **độ trễ chấp nhận** và **phạm vi trên nhiều server**.

## 2. Tại sao quyền cũ vẫn còn?

Một luồng form login thường trông như sau:

~~~text
POST /login
   |
   v
UsernamePasswordAuthenticationFilter
   |
   v
AuthenticationManager / DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername("alice")
   +--> PasswordEncoder.matches(raw, storedHash)
   +--> enabled, locked, accountExpired, credentialsExpired
   |
   v
Authentication đã xác thực, chứa authorities tại login
   |
   v
SecurityContext được lưu qua SecurityContextRepository
   |
   v
HttpSession chứa SecurityContext
   |
   | Browser gửi lại session cookie
   v
GET /admin
   |
   v
SecurityContextRepository phục hồi Authentication cũ
   |
   v
AuthorizationFilter: hasRole("ADMIN")?
   |
   +--> Xét authorities trong Authentication đang dùng
   +--> Có ROLE_ADMIN cũ -> có thể ALLOW
~~~

Khi user tiếp tục duyệt trang, Spring Security có thể **phục hồi Authentication từ session**, thay vì thực hiện lại username/password authentication. Các flag `isEnabled`, `isAccountNonLocked` trên bản `UserDetails` cũ cũng không tự đồng bộ với database.

Ở đây có hai loại **state**:

| Nguồn | Chứa dữ liệu gì? | Thường đổi khi nào? |
| --- | --- | --- |
| Database/identity store | Role, permission, account locked/disabled, password hash, `securityVersion` | Khi admin hoặc hệ thống thay đổi account |
| Authentication trong SecurityContext | Principal, GrantedAuthorities, trạng thái xác thực tại thời điểm tạo/khôi phục | Khi login, reauthentication, refresh/replace SecurityContext hoặc thu hồi session |
| Session registry | Các session đang được theo dõi và trạng thái hết hiệu lực | Khi login/logout/session destroyed hoặc có lệnh expire |
| JWT đã phát | Claims, scope, expiry đã được ký tại thời điểm cấp | Payload **không đổi** sau khi token phát; phải hết hạn, revoke hoặc dùng server-side check |

Không nên coi `getAuthorities()` là query live vào role database. Các authority có thể bị stale cho đến khi authentication context được làm mới.

### 2.1. Phân biệt đổi mật khẩu, đổi quyền và khóa account

| Sự kiện | Authentication mới | Session đã đăng nhập | Rủi ro |
| --- | --- | --- | --- |
| Thu hồi ROLE_ADMIN | Lần login mới thường nhận role mới | Có thể còn ROLE_ADMIN cũ | Được phép tiếp tục thao tác quản trị |
| Cấp ROLE_ADMIN | Login mới nhận role mới | Có thể vẫn thiếu ROLE_ADMIN | Người dùng bị từ chối dù DB đã cấp |
| Disable account | Login mới bị từ chối | Có thể còn hoạt động | Tài khoản bị khóa vẫn truy cập |
| Lock vì brute-force | Login mới bị từ chối | Có thể còn hoạt động | Cơ chế khóa bị vô hiệu ở session cũ |
| Đổi/reset password | Password mới có hiệu lực khi xác thực lại | Phiên cũ có thể chưa bị kết thúc | Người có session bị chiếm vẫn truy cập |
| Thu hồi quyền theo tenant/resource | Policy mới trong DB | URL role rule có thể vẫn dựa vào quyền cũ | Rủi ro truy cập dữ liệu sai phạm vi |
| Khóa OAuth2 client | Token mới có thể bị từ chối | Access token đã cấp có thể còn hiệu lực | Phải có token revocation/expiry hoặc kiểm tra live |

**Không phải mọi event đều phải lập tức logout theo cùng một policy.** Đổi tên hiển thị có thể không cần thu hồi phiên; thu hồi quyền quản trị hoặc khóa tài khoản vì bị xâm nhập thường cần hiệu lực nhanh và chặn quyền truy cập còn tồn tại.

## 3. UserDetailsService có giải quyết thay đổi quyền tự động không?

`UserDetailsService` chỉ định nghĩa một nhiệm vụ cốt lõi:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

Khi có form login hoặc HTTP Basic, một provider có thể dùng method này để tải user, encoded password, authorities và trạng thái account. Tuy nhiên, một request đã có `Authentication` được phục hồi từ session có thể **không gọi method đó lần nữa**.

### 3.1. Không dựa vào việc gọi loadUserByUsername mỗi request

Điều dễ bị hiểu sai:

~~~java
@Service
public class MyUserDetailsService implements UserDetailsService {
    @Override
    public UserDetails loadUserByUsername(String username) {
        // Query DB role mới nhất...
    }
}
~~~

Một implementation tốt chỉ bảo đảm **mỗi lần method được gọi, nó trả dữ liệu đúng tại thời điểm query**. Nó không bảo đảm `SecurityContextHolder` tự sửa `getAuthorities()` của mọi phiên đã đăng nhập.

Tương tự, code sau trong Controller có thể đọc role cũ:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

Collection<? extends GrantedAuthority> authorities =
    auth.getAuthorities();
~~~

Đoạn trích chỉ có ý nghĩa khi một request được Spring Security bảo vệ và Authentication có mặt. Đừng tự lấy authorities này rồi coi là nguồn quyền cập nhật liên tục nếu business có yêu cầu thu hồi ngay.

### 3.2. DaoAuthenticationProvider kiểm tra trạng thái lúc xác thực

Các cờ quan trọng của `UserDetails`:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Provider có thể ném `DisabledException`, `LockedException`, `AccountExpiredException` hoặc `CredentialsExpiredException` trong quá trình xác thực. **Các cờ trên bản UserDetails đã được lưu vào phiên không tự đọc lại DB**. Vì vậy một endpoint chỉ dùng `.authenticated()` vẫn có thể chấp nhận Authentication cũ.

## 4. Chọn chiến lược khi quyền/account thay đổi

Có nhiều hướng phù hợp với những yêu cầu khác nhau:

| Chiến lược | Cơ chế | Độ trễ thường gặp | Ưu điểm | Giới hạn |
| --- | --- | --- | --- | --- |
| **Thu hồi các session đang theo dõi** | Mark expired/invalidate trong session system | Khi session gặp request kiểm tra tiếp theo; có thể có thời gian trễ/event propagation | Người dùng buộc login lại, quyền nạp mới | Cần session tracking đầy đủ, cluster-aware |
| **Kiểm tra trạng thái account mỗi request** | Filter/AuthorizationManager đọc account enabled/version | Gần mỗi lần request được bảo vệ | Có thể chặn nhanh cả session cũ | Thêm DB/cache calls; cần fail-closed và cache strategy |
| **Phiên chứa securityVersion** | Lưu version ở login, so với version account | Theo tần suất kiểm tra version | Dễ phát hiện thay đổi quyền/mật khẩu/trạng thái | Cần version store và cơ chế đồng bộ đa node |
| **Short-lived access token** | Token hết hạn nhanh; không tự refresh khi account bị khóa | Theo TTL và clock skew | Giảm cửa sổ dùng token cũ | Không thu hồi tức thì |
| **Token introspection/revocation** | Resource Server hỏi trạng thái token hoặc denylist | Theo check/cache TTL | Có thể thu hồi token tập trung | Tăng phụ thuộc AS/network/cache |
| **Fresh resource-level authorization** | Service tra policy/owner/tenant mới khi xử lý thao tác | Theo thời điểm policy check | Bảo vệ tài nguyên ngay cả khi session roles cũ | Không tự thay session Authentication hoặc logout |
| **Làm mới Authentication chủ động** | Thay SecurityContext bằng principal/roles mới qua cơ chế tin cậy | Khi có refresh/reauth | Giữ phiên user nếu policy cho phép | Phức tạp, có race; không thích hợp nếu cần khóa account ngay |

**Không có một công tắc Spring Security duy nhất thu hồi mọi loại session, JWT, remember-me, OAuth2 client và token của hệ thống phân tán.** Chọn theo authentication mechanism, rủi ro và hạ tầng thực tế.

## 5. SessionRegistry: đánh dấu phiên hết hiệu lực

Spring Security Servlet hỗ trợ **concurrent session management** với `SessionRegistry`, `SessionRegistryImpl`, `SessionInformation` và `ConcurrentSessionFilter`.

Ví dụ các API liên quan:

~~~java
List<Object> principals = sessionRegistry.getAllPrincipals();
List<SessionInformation> infos =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : infos) {
    info.expireNow();
}
~~~

Đây là **snippet** nằm trong service có `sessionRegistry` và `principal` phù hợp. `getAllSessions(principal, false)` lấy những session còn active được registry biết tới, còn `expireNow()` **đánh dấu** `SessionInformation` đã expired.

### 5.1. expireNow() có lập tức xóa HttpSession trên máy khách không?

**Không.** `SessionInformation.expireNow()` đánh dấu một phiên trong **registry**. Khi request tiếp theo dùng session ID đó, `ConcurrentSessionFilter` có thể đọc trạng thái expired, thực hiện logout/invalidation và gọi `SessionInformationExpiredStrategy` để tạo response (ví dụ redirect login).

~~~text
Admin cập nhật role hoặc disable account
    |
    v
AccountStore/DB cập nhật
    |
    v
SessionRegistry: session S1 -> expired=true
    |
    | Session có thể vẫn tồn tại cho đến khi request kế tiếp
    v
Browser gửi Cookie: JSESSIONID=S1
    |
    v
ConcurrentSessionFilter
    |
    +--> S1 expired?
             |
             +--> YES: logout/invalidate và phản hồi expired
             +--> NO: xử lý chain bình thường
~~~

**Hệ quả:** phiên không hoạt động trên trình duyệt vẫn có thể tồn tại đến khi container hết hạn hoặc được xử lý, và một request đã qua điểm kiểm tra trước thời điểm revoke có thể vẫn đang chạy. Đây là **thu hồi theo request boundary**, không phải cơ chế dừng ngay mọi lệnh đang thực thi.

### 5.2. Vai trò của HttpSessionEventPublisher

`SessionRegistryImpl` duy trì mapping principal ↔ session ID và cần nhận biết event session destroyed/expired. Trong Spring Boot, có thể đăng ký:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Khi dùng `maximumSessions(...)` và registry có tracking, listener giúp registry cập nhật đúng vòng đời session. Nếu thiếu event hoặc custom authentication mechanism không đăng ký session, registry có thể giữ dữ liệu stale hoặc bỏ sót phiên.

**SessionRegistryImpl thông thường là in-memory**, phù hợp demo và một node. Khi triển khai nhiều instance cần Spring Session/registry phân tán hoặc một hệ thống revocation tập trung. Registry trên node A không mặc nhiên biết session được tạo trên node B.

### 5.3. maximumSessions(...) không chỉ dùng để chặn login thứ hai

Cấu hình:

~~~java
.sessionManagement(session -> session
    .maximumSessions(5)
    .sessionRegistry(sessionRegistry)
    .expiredUrl("/login?expired")
)
~~~

Bật cơ chế concurrent session control, sử dụng registry đã cung cấp và tạo filter có khả năng nhận biết `SessionInformation` hết hạn. `maximumSessions(5)` là **giới hạn tối đa 5 phiên đồng thời cho một principal**, không phải lệnh “tự logout khi role thay đổi”. Phải gọi expire trong application service khi account security state thay đổi.

`expiredUrl` là ví dụ behavior trình duyệt: khi phiên đã bị đánh dấu expired và browser truy cập lại, nó được chuyển về `/login?expired`. Với REST API có thể thay bằng `SessionInformationExpiredStrategy` trả 401 JSON; hãy kiểm tra UX, cookie behavior và entry point thực tế.

## 6. Ví dụ Spring Boot 3/Java 17: thay đổi role rồi thu hồi phiên

Mục tiêu demo:

1. Alice có `ROLE_USER`, admin có `ROLE_ADMIN`.
2. Sau form login, session giữ `Authentication` với authorities tại thời điểm xác thực.
3. Thay roles của Alice trong repository **không tự cập nhật session cũ**.
4. Một `AccountAdministrationService` thay đổi account và đánh dấu tất cả session đã đăng ký của user là expired.
5. Khi Alice gửi request bằng session cũ, `ConcurrentSessionFilter` xử lý expired session. Khi đăng nhập lại, `UserDetailsService` tải roles mới.
6. Nếu account bị disable, login mới bị từ chối; session cũ được đánh dấu để thu hồi.

Mã nguồn chỉ dùng **in-memory repository/SessionRegistry** cho một JVM, không phải mẫu deployment multi-node. Các thao tác admin được gọi **trực tiếp từ test hoặc service nội bộ**; demo không cung cấp một HTTP endpoint tự do thay role/disable user.

### 6.1. Dependencies và cấu trúc file

Tạo project Spring Boot **3.x**, Java **17+** có Gradle plugin/Wrapper phù hợp. Bổ sung vào `build.gradle` đang có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Block này **không phải toàn bộ build.gradle**; plugin, repositories và version do Spring Boot project cung cấp.

~~~text
src/main/java/com/example/sessionroles/
  SessionRolesApplication.java
  MutableAccountStore.java
  AccountAdministrationService.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/sessionroles/
  SessionRevocationTest.java
~~~

### 6.2. SessionRolesApplication.java

~~~java
package com.example.sessionroles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionRolesApplication.class, args);
    }
}
~~~

### 6.3. MutableAccountStore.java — dữ liệu account và nguồn user

~~~java
package com.example.sessionroles;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class MutableAccountStore implements UserDetailsService {

    private record Account(
        String username,
        String hash,
        boolean enabled,
        Set<String> authorities
    ) {}

    private final ConcurrentMap<String, Account> accounts =
        new ConcurrentHashMap<>();

    public MutableAccountStore(PasswordEncoder encoder) {
        accounts.put("alice", new Account(
            "alice",
            encoder.encode("alice123"),
            true,
            Set.of("ROLE_USER")
        ));
        accounts.put("admin", new Account(
            "admin",
            encoder.encode("admin123"),
            true,
            Set.of("ROLE_ADMIN")
        ));
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.get(username);
        if (account == null) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        return User.withUsername(account.username())
            .password(account.hash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .build();
    }

    public void replaceAuthorities(
            String username, Set<String> authorities) {
        if (authorities == null || authorities.isEmpty()) {
            throw new IllegalArgumentException(
                "Specify at least one authority for this demo"
            );
        }

        Set<String> trustedAuthorities = Set.copyOf(authorities);

        accounts.compute(username, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                previous.username(), previous.hash(),
                previous.enabled(), trustedAuthorities
            );
        });
    }

    public void disable(String username) {
        accounts.compute(username, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                previous.username(), previous.hash(),
                false, previous.authorities()
            );
        });
    }
}
~~~

**Phân tích:**

- In-memory store dùng `ConcurrentHashMap`, không phải database production. Đổi thành JPA/JDBC repository trong ứng dụng thật.
- Password được hash bằng encoder lúc tạo dữ liệu demo; `loadUserByUsername` chỉ trả **hash hiện có**, không encode lại.
- `.disabled(!account.enabled())` chuyển đúng chiều cờ. Account disabled sẽ không được `DaoAuthenticationProvider` xác thực ở **lần login kế tiếp**.
- `replaceAuthorities` tạo account record mới thay vì sửa `UserDetails` nằm sẵn trong session. Session cũ vì thế vẫn chứa authorities ban đầu — giúp minh họa rõ vấn đề.
- `Set.copyOf` bảo đảm record có tập quyền không bị sửa qua tham chiếu nguồn trong ví dụ; **không dùng authority từ request của client không đáng tin cậy**.
- Demo không có trạng thái `locked`; trong database thật, `locked=true` cần ánh xạ sang `UserDetails.isAccountNonLocked()==false`, thường qua builder `.accountLocked(account.locked())`.

### 6.4. SecurityConfig.java — form login, SessionRegistry và ConcurrentSessionFilter

~~~java
package com.example.sessionroles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            MutableAccountStore accounts,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DaoAuthenticationProvider provider,
            SessionRegistry registry) throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .maximumSessions(5)
                .sessionRegistry(registry)
                .expiredUrl("/login?expired")
            );

        return http.build();
    }
}
~~~

**Tại sao cấu hình như vậy?**

1. `DaoAuthenticationProvider` xác minh credential bằng `MutableAccountStore` + BCrypt.
2. `formLogin` tạo luồng **username/password + HttpSession**, dễ quan sát snapshot Authentication.
3. `SessionRegistryImpl` được dùng để theo dõi các phiên được đăng ký.
4. `HttpSessionEventPublisher` chuyển sự kiện session destroyed để registry không giữ session không còn tồn tại.
5. `maximumSessions(5)` bật concurrent session support, trong đó có `ConcurrentSessionFilter` có thể phát hiện session bị `expireNow()`.
6. `sessionRegistry(registry)` bảo đảm service thu hồi và filter dùng cùng registry.
7. `expiredUrl("/login?expired")` điều hướng browser khi gửi request với session bị đánh dấu expired.
8. `.hasRole("ADMIN")` đánh giá authorities **trong Authentication đang được dùng**, không tự query DB.
9. `anyRequest().denyAll()` chặn các endpoint chưa khai báo.

**Lưu ý về lỗi login page:** `formLogin()` cung cấp generated login page qua các security filters. `GET /login` không có controller tự viết; form login filter/page được framework xử lý. Nếu dự án dùng login page custom, phải permit đúng URL và static assets liên quan.

**CSRF vẫn bật.** POST `/login` trong test sẽ dùng Spring Security Test để gửi token CSRF hợp lệ. Không tắt CSRF để cho demo chạy.

### 6.5. AccountAdministrationService.java — đổi quyền/disable và expire phiên

~~~java
package com.example.sessionroles;

import java.util.Set;

import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;

@Service
public class AccountAdministrationService {

    private final MutableAccountStore accounts;
    private final SessionRegistry registry;

    public AccountAdministrationService(
            MutableAccountStore accounts,
            SessionRegistry registry) {
        this.accounts = accounts;
        this.registry = registry;
    }

    public void replaceAuthorities(
            String username, Set<String> authorities) {
        accounts.replaceAuthorities(username, authorities);
        expireSessions(username);
    }

    public void disable(String username) {
        accounts.disable(username);
        expireSessions(username);
    }

    public void expireSessions(String username) {
        for (Object principal : registry.getAllPrincipals()) {
            if (principal instanceof UserDetails user
                    && username.equals(user.getUsername())) {

                for (SessionInformation session :
                        registry.getAllSessions(principal, false)) {
                    session.expireNow();
                }
            }
        }
    }
}
~~~

**Cần phân biệt ba thao tác:**

- `accounts.replaceAuthorities(...)` thay quyền trong nguồn account. Không thay `Authentication` đang lưu trong session.
- `accounts.disable(...)` khiến **login mới** bị từ chối bởi provider thông dụng.
- `expireSessions(...)` tìm **các session đã đăng ký** tương ứng username rồi đánh dấu `expired`. Khi request tiếp theo dùng session ấy, filter sẽ xử lý logout/invalidation.

Phương thức này dựa vào `principal instanceof UserDetails` và username ổn định trong một demo duy nhất. **Sản phẩm thật nên dùng immutable account ID + tenant ID đã xác minh** làm khóa revocation, vì username/email có thể đổi hoặc trùng giữa tenant. Nếu principal là OidcUser/Jwt/custom principal, thay logic nhận diện bằng loại thực tế. `SessionRegistryImpl` dùng `equals/hashCode` trên principal nên custom UserDetails cần implement ổn định.

**Đây là service nội bộ.** Đừng tạo `GET /disable?user=...` công khai. Một admin API thật cần `@PreAuthorize`/HTTP authorization cho thao tác đặc quyền, CSRF nếu browser dùng cookie, validation, audit, concurrency control và xử lý transaction với DB.

### 6.6. DemoController.java

~~~java
package com.example.sessionroles;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + ":" + roles;
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-only";
    }
}
~~~

Sau login ban đầu với Alice, `GET /me` dự kiến trả `alice:ROLE_USER`. Nếu admin cấp Alice ROLE_ADMIN nhưng **không thu hồi session**, bản Authentication cũ có thể vẫn trả `alice:ROLE_USER`; sau khi thu hồi session và Alice login mới, response có thể là `alice:ROLE_ADMIN,ROLE_USER`.

**Không tự trả nguyên Authentication/UserDetails** làm JSON; nó có thể chứa encoded password, authorities và metadata không cần công khai. Chuỗi response của demo chỉ giúp quan sát role.

## 7. MockMvc test: chứng minh quyền cũ, quyền mới và khóa account

Tạo `src/test/java/com/example/sessionroles/SessionRevocationTest.java`:

~~~java
package com.example.sessionroles;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionRevocationTest {

    @Autowired MockMvc mvc;
    @Autowired MutableAccountStore accounts;
    @Autowired AccountAdministrationService adminService;
    @Autowired SessionRegistry registry;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void changingRolesInStoreDoesNotRefreshExistingSession()
            throws Exception {
        MockHttpSession session = login("alice", "alice123");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_USER"));

        accounts.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        // Chưa thu hồi: session giữ Authentication trước đó.
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_USER"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void changingRoleThroughServiceExpiresOldSession()
            throws Exception {
        MockHttpSession oldSession = login("alice", "alice123");

        adminService.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        SessionInformation tracked =
            registry.getSessionInformation(oldSession.getId());

        assertNotNull(tracked);
        assertTrue(tracked.isExpired());

        mvc.perform(get("/me").session(oldSession))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        MockHttpSession newSession = login("alice", "alice123");

        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));

        mvc.perform(get("/me").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_ADMIN,ROLE_USER"));
    }

    @Test
    void disablingAccountExpiresOldSessionAndRejectsNewLogin()
            throws Exception {
        MockHttpSession oldSession = login("alice", "alice123");

        adminService.disable("alice");

        SessionInformation tracked =
            registry.getSessionInformation(oldSession.getId());

        assertNotNull(tracked);
        assertTrue(tracked.isExpired());

        mvc.perform(get("/me").session(oldSession))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void revocationTargetsOnlySpecifiedAccount()
            throws Exception {
        MockHttpSession aliceSession = login("alice", "alice123");
        MockHttpSession adminSession = login("admin", "admin123");

        adminService.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        SessionInformation alice =
            registry.getSessionInformation(aliceSession.getId());

        SessionInformation administrator =
            registry.getSessionInformation(adminSession.getId());

        assertNotNull(alice);
        assertNotNull(administrator);
        assertTrue(alice.isExpired());
        assertFalse(administrator.isExpired());

        mvc.perform(get("/admin").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Chạy test trong root Gradle project:

~~~bash
./gradlew test
# Windows PowerShell/cmd:
gradlew.bat test
~~~

**Cách hiểu bộ test:**

1. `changingRolesInStoreDoesNotRefreshExistingSession`: đổi role chỉ trong nguồn account không làm `Authentication` của phiên cũ tự thay đổi.
2. `changingRoleThroughServiceExpiresOldSession`: service cập nhật quyền và đánh dấu phiên cũ expired; request kế tiếp bị chuyển về login; session mới nhận quyền cập nhật.
3. `disablingAccountExpiresOldSessionAndRejectsNewLogin`: account disabled vừa làm phiên được theo dõi bị expire, vừa khiến login mới thất bại.
4. `revocationTargetsOnlySpecifiedAccount`: không vô tình thu hồi phiên của user khác.
5. `@DirtiesContext` tạo context mới sau mỗi test để thay đổi trong in-memory account store/registry của test trước không ảnh hưởng test sau.
6. `csrf()` được gửi với POST `/login` vì CSRF vẫn bật. Đây là request postprocessor phục vụ kiểm thử, không phải lý do tắt CsrfFilter.

**Kết quả trên là các assertion kỳ vọng của mã ví dụ, không phải báo cáo Gradle đã được chạy ở đây.** Khi dùng Spring Security 7/Boot 4 hoặc cấu hình login page/session strategy riêng, cần đối chiếu API và redirect behavior theo version.

### 7.1. Phản ví dụ: thu hồi role ADMIN nhưng quên expire

Điều này nguy hiểm hơn việc cấp thêm quyền bị chậm.

~~~text
Tại login:
  admin account -> Authentication authorities=[ROLE_ADMIN]

Admin điều chỉnh DB:
  account.authorities=[ROLE_USER]

Không expire old session:
  GET /admin từ session cũ
      -> hasRole("ADMIN") dựa vào Authentication cũ
      -> có thể vẫn ALLOW

Có expire old session và filter nhận thấy expired:
  GET /admin từ session cũ
      -> ConcurrentSessionFilter chặn và kết thúc session
      -> cần login mới với ROLE_USER
      -> /admin không còn được phép
~~~

**Quyền bị thu hồi** cần được xem là security event, không chỉ là một field được chỉnh trong bảng account.

## 8. Khi account bị khóa, phải làm những gì?

Ở mức dữ liệu, khóa account có thể được biểu diễn bằng `enabled=false`, `locked=true` hoặc trạng thái nghiệp vụ riêng. Chọn một policy nhất quán để provider và những đường truy cập khác đều hiểu.

### 8.1. Xử lý login mới

`DaoAuthenticationProvider` thông dụng dùng các cờ `UserDetails`:

| Cờ | Ý nghĩa khi false | Kết quả xác thực thường gặp |
| --- | --- | --- |
| `isEnabled()` | Tài khoản bị vô hiệu hóa | `DisabledException` |
| `isAccountNonLocked()` | Tài khoản bị khóa | `LockedException` |
| `isAccountNonExpired()` | Tài khoản hết hiệu lực | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credential hết hạn | `CredentialsExpiredException` |

Những exception nội bộ có thể được ánh xạ thành lỗi đăng nhập chung cho client, tránh tiết lộ quá nhiều về account. Với form login mặc định thường redirect `/login?error`; với Basic có thể trả 401. HTTP response còn tùy entry point và handler.

### 8.2. Xử lý session đang hoạt động

Với session tracking đúng, có thể expire các phiên gắn với account bị khóa. Tuy nhiên, nếu có phiên không được registry biết, hoặc session nằm ở node khác, lệnh trong demo có thể bỏ sót.

Đối với **khóa tài khoản khẩn cấp do bị xâm nhập**, còn nên:

- Thu hồi refresh tokens/grants phù hợp ở IdP/Authorization Server.
- Revoke server-side sessions trên mọi node/thiết bị.
- Chặn cấp session/token mới trong login/token refresh.
- Kiểm tra các đường truy cập thay thế: remember-me, magic link, API keys, service credentials, OAuth2 login.
- Với endpoint nhạy cảm, kiểm tra trạng thái account/security version ở thời điểm hành động.
- Ghi audit gồm actor, target account, reason, timestamp, correlation ID, số phiên bị ảnh hưởng và kết quả thực thi.

### 8.3. Đổi password có nên logout mọi thiết bị?

Tùy mục đích. Khi user tự đổi password trong phiên an toàn, một số sản phẩm cho phép giữ phiên hiện tại và thu hồi phiên khác; khi password bị reset vì nghi lộ credential, có thể cần thu hồi tất cả. Thiết kế phải có hành vi rõ cho session hiện tại, session khác, refresh token và thiết bị.

Nếu code thu hồi cả session đang gọi thao tác admin, response hoàn tất có thể khác tùy session invalidation timing. Không nên giả định lệnh xóa hết phiên là tức thời và transactional trên mọi hệ thống.

## 9. Phương án securityVersion để kiểm tra phiên cũ

Một hệ thống cần phản ứng nhanh hơn có thể giữ **`securityVersion`** hoặc **`authzVersion`** tăng mỗi lần role/locked/password/tenant policy thay đổi.

~~~text
Tại login:
  Account.securityVersion = 42
  Session.securityVersion = 42

Admin thay quyền:
  Account.securityVersion = 43

Request kế tiếp:
  Read Session.securityVersion = 42
  Read Account.securityVersion = 43
  42 != 43 -> reject / reauthenticate / invalidate
~~~

Điều kiện minh họa:

~~~java
// Snippet có accountId/version từ principal tin cậy và store tin cậy.
boolean sessionStillValid(
        long versionAtLogin, long currentAccountVersion,
        boolean accountEnabled) {

    return accountEnabled
        && versionAtLogin == currentAccountVersion;
}
~~~

Không copy method đó vào demo rồi tin là đủ: cần code **nạp accountId/version đáng tin**, lưu version vào Authentication/session tại login, tích hợp checker vào **mọi đường truy cập được bảo vệ** và tạo response/clear SecurityContext phù hợp.

**Lợi ích:** Có thể phát hiện phiên cũ mà không cần biết session ID, kể cả khi registry bỏ sót. **Chi phí:** phải đọc version store/cached value trên request, giải quyết cache invalidation, outage behavior, race và multi-region propagation.

### 9.1. Nên đặt kiểm tra version ở đâu?

Có thể là một servlet filter phù hợp, custom `AuthorizationManager` được áp cho các endpoint, hoặc service guard trước hành động nhạy cảm. Nhưng phải tránh:

- Đặt guard sau khi business transaction đã thực thi.
- Chỉ kiểm tra version trong `/admin` mà quên endpoints tải dữ liệu khác.
- Đọc account ID từ `request.getParameter("userId")` do client tự chọn.
- Cho phép khi DB/cache version service lỗi mà policy yêu cầu fail-closed.
- Cache trạng thái “enabled=true” quá lâu so với SLA khóa tài khoản.
- Chỉ dựa vào một `isAuthenticated()` boolean, không xét account status/version.
- Mất đồng bộ version khi admin chỉnh roles theo nhiều hệ thống.

Với một tài nguyên nhạy cảm, kiểm tra ở service/repository ngay trước commit có thể giảm khoảng hở giữa kiểm tra lúc bắt đầu request và hành động cuối. Dù vậy vẫn phải xét transaction isolation và race conditions.

### 9.2. Cho phép phiên cũ được cập nhật quyền hay yêu cầu login lại?

Có hai chính sách:

1. **Fail closed và yêu cầu đăng nhập lại:** session version khác current version thì revoke/deny. Đơn giản để hiểu, thích hợp với demotion, lock và thay đổi credentials.
2. **Refresh Authentication từ nguồn tin cậy:** nạp authorities mới và thay SecurityContext trong một flow reauthentication đã được kiểm soát; có thể cho phép nâng quyền mà không buộc user logout, nhưng phải bảo đảm không lấy các quyền chưa xác minh và xử lý concurrency.

**Không chỉ sửa `authentication.getAuthorities()` tại một request rồi tưởng mọi session khác đã được cập nhật.** `Authentication` có thể immutable, principal shared/cached, session replicated và authorization data đã nằm trong token. Khi nâng quyền cao, có thể yêu cầu recent authentication hoặc MFA.

## 10. Token và session: không dùng cùng một cách revoke

### 10.1. Browser HttpSession

Session được lưu ở server hoặc kho phiên phân tán; nếu có session ID và API quản trị phù hợp, hệ thống có thể invalidate. `SessionRegistryImpl` theo dõi phiên trong một JVM; `SessionInformation.expireNow` phụ thuộc request sau qua `ConcurrentSessionFilter`.

### 10.2. HTTP Basic

Request Basic thường mang username/password mỗi lần; provider có thể gọi UserDetailsService và nhìn thấy account bị disable mới. Tuy nhiên **không được suy ra mọi triển khai Basic đều tự kiểm tra database mỗi request**: cache, session policy hoặc filter/manager tùy biến có thể làm khác. Kiểm chứng chain và provider thực tế.

### 10.3. JWT access token không phải HttpSession

JWT đã ký chứa claims không thay đổi sau khi phát. Nếu user bị thu hồi `ROLE_ADMIN` trong database nhưng access token cũ vẫn chứa role/scope ấy, Resource Server chỉ kiểm tra chữ ký, issuer, expiry và claims từ token có thể tiếp tục chấp nhận token cho đến khi hết hạn.

`SessionRegistry.expireNow()` **không tự vô hiệu hóa JWT**. Cần một hoặc kết hợp:
- JWT TTL ngắn và giới hạn refresh.
- Revocation list cho token ID (`jti`) hoặc session/security version theo subject.
- Kiểm tra trạng thái account/permission từ nguồn tin cậy theo tần suất yêu cầu.
- Token introspection hoặc backend-for-frontend/session gateway khi cần revocation tập trung.
- Authorization ở tầng resource luôn kiểm tra ownership/tenant/critical permissions.

JWT tự chứa dễ scale và giảm lookup, nhưng đổi lại **khó thu hồi tức thì nếu API chỉ xác minh offline**. Bảo vệ đúng dựa vào threat model, không đơn giản dùng JWT 24 giờ cho mọi quyền nhạy cảm.

### 10.4. Opaque token/introspection

Một Resource Server sử dụng opaque token introspection có thể hỏi Authorization Server xem token còn `active` và được cấp quyền gì. Tuy nhiên cache introspection và sự cố network có thể tạo độ trễ cho việc thu hồi. Cần có policy rõ khi introspection fail, cache TTL và token bị revoke.

### 10.5. Refresh token và OAuth2 login

Thu hồi access token nhưng **refresh token vẫn còn** có thể cho phép nhận access token mới nếu Authorization Server không kiểm tra trạng thái account hoặc grant. Khi disable account/reset password, cần thu hồi refresh token/grant theo khả năng IdP; một user có nhiều app/device có thể có nhiều token families.

Với OAuth2 Login, phiên ứng dụng có thể vẫn tồn tại sau khi người dùng bị disable ở IdP. Single Logout, back-channel logout hoặc local session invalidation phải được thiết kế phù hợp; không mặc định IdP khóa user là ứng dụng lập tức biết.

### 10.6. Remember-me

Remember-me cookie/token có thể tự tạo Authentication mới ở request sau khi session hết hạn. Nếu khóa account hoặc đổi mật khẩu, phải xác định remember-me mechanism có được vô hiệu hóa và revalidate không. Persistent remember-me tokens có kho lưu/rotation riêng; đừng chỉ expire session rồi cho cookie remember-me phục hồi một phiên mới ngoài ý muốn.

## 11. Multi-node, Spring Session và Registry phân tán

`SessionRegistryImpl` lưu session tracking trong bộ nhớ JVM. Nếu Spring Boot chạy ba node sau load balancer:

~~~text
Browser -> Load Balancer
              |
              +--> node A: registry A
              +--> node B: registry B
              +--> node C: registry C

Admin revoke trên node A
    |
    +--> Registry A biết các session do A theo dõi
    +--> Session được xử lý ở B/C có thể không có trong A
~~~

Ngay cả khi dùng shared session store (Redis/JDBC) để lưu `HttpSession`, registry in-memory **không tự biến thành phân tán**. Cần lựa chọn session registry tương thích với Spring Session, shared revocation store, pub/sub event hoặc một tầng kiểm tra security version dùng chung.

### 11.1. Spring Session

Spring Session hỗ trợ kho phiên tập trung và có integration với Spring Security. Trong trường hợp phù hợp, dùng `SpringSessionBackedSessionRegistry` (theo module/phiên bản) hoặc session repository APIs để liệt kê/thu hồi sessions theo principal đáng tin cậy.

**Không dùng `SessionRegistryImpl` in-memory làm nguồn toàn bộ phiên của cluster** rồi tuyên bố revoke mọi thiết bị. Kiểm tra Redis/JDBC TTL, event expiration, serialization, principal index, namespace và điều kiện xóa phiên từ xa theo phiên bản thư viện.

### 11.2. Race và độ trễ

Những khoảng thời gian quan trọng:

1. Admin update DB thành công nhưng sự kiện revoke chưa được phát.
2. Revoke event đã phát nhưng một node chưa nhận.
3. Browser đã bắt đầu request trước lúc khóa account.
4. Session đã expire nhưng request chưa đến ConcurrentSessionFilter.
5. Cache role/version vẫn giữ giá trị cũ.
6. JWT đã cấp còn sống đến `exp` hoặc đến lúc resource server kiểm tra denylist.

Với hệ thống nhạy cảm, định nghĩa **revocation SLA** (ví dụ phải chặn request mới trong một giới hạn nhất định), đo test thực tế trên nhiều node và bổ sung **guard theo account status/version** cho thao tác trọng yếu.

### 11.3. Transaction và tính nhất quán

Một quy trình production thường cần:

~~~text
Admin gửi yêu cầu thay role/disable
    |
    v
Kiểm tra actor có quyền thực hiện và target hợp lệ
    |
    v
DB transaction:
    - update account roles/status
    - tăng securityVersion
    - lưu audit/outbox event
    |
    v
Commit
    |
    v
Phát sự kiện revocation tới session/token components
    |
    v
Các node/cache cập nhật, session/token bị expire/revoke
    |
    v
Monitor, retry, reconcile cho phiên còn sót
~~~

Nếu update DB và expire registry **không cùng một transaction phân tán**, cần quy trình retry/outbox để sự kiện không mất. Không đổi dữ liệu account thành công rồi mặc định chắc chắn mọi JWT/session ở các vùng đã bị thu hồi.

**Bảo vệ dữ liệu nhạy cảm còn phải xét authorization trong chính request**: một request đã vượt qua filter trước khi revoke có thể vẫn đang xử lý. Với transaction nguy hiểm, guard gần thời điểm commit có thể cần thiết.

## 12. Kiểm tra quyền cập nhật theo từng request

Đôi khi yêu cầu nghiệp vụ là: **thu hồi quyền `invoice:approve` có hiệu lực ngay với giao dịch mới**, nhưng không nhất thiết logout user khỏi toàn ứng dụng. Khi đó có thể tách:

- **Authentication:** session chỉ giữ định danh ổn định của user đã xác thực.
- **Authorization:** mỗi quyết định phê duyệt truy vấn quyền hiện tại theo account/tenant/document hoặc kiểm tra securityVersion.
- **Session revocation:** vẫn dùng cho khóa account, mất credential, xâm nhập hoặc các chính sách buộc reauthentication.

Ví dụ snippet method security:

~~~java
@PreAuthorize(
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
public void approveInvoice(long invoiceId) {
    // Cập nhật hóa đơn trong một service/transaction phù hợp.
}
~~~

Snippet cần `@EnableMethodSecurity` và bean `invoicePolicy` do bạn triển khai. Phương thức `canApprove` phải nhận identity đã xác minh từ Authentication, kiểm tra account còn enabled, permission cập nhật, owner/tenant và trạng thái invoice. Không dùng `invoiceId` và `userId` do client gửi như hai sự thật đã được xác minh.

`@PreAuthorize` kiểm tra trước khi gọi method, nhưng với giao dịch nhạy cảm có thể cần kiểm tra thêm ở domain/DB khi trạng thái thay đổi giữa check và commit. Role snapshot trong session không phải lý do bỏ quyền theo resource.

### 12.1. AuthorizationManager tùy chỉnh

Spring Security cho phép tích hợp `AuthorizationManager<RequestAuthorizationContext>` vào `.authorizeHttpRequests`. Ví dụ ý tưởng:

~~~java
// Snippet: accountPolicy bean phải có implementation thật.
// Không tự coi đoạn này là một filter/bean hoàn chỉnh.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/sensitive/**")
    .access((authentication, context) ->
        new AuthorizationDecision(
            accountPolicy.allowCurrentRequest(
                authentication.get(),
                context.getRequest()
            )
        )
    )
    .anyRequest().authenticated()
);
~~~

Cần đảm bảo policy không tin Authentication anonymous, không bỏ qua status locked/version và xử lý lỗi account store theo cách fail-closed. Spring Security 6.x API cụ thể có thể trả `AuthorizationDecision` hoặc contract tương thích theo version; hãy đối chiếu dependencies của project.

### 12.2. Cache quyền và invalidation

Nếu query role ở DB cho mọi request quá tốn chi phí, có thể cache `accountId → {enabled, securityVersion, permissions}` với TTL ngắn và invalidation event. **Cache cần được thiết kế có điều kiện**: một TTL 30 phút có nghĩa thu hồi quyền có thể chậm tới 30 phút nếu cache không được invalidate.

Định nghĩa nguồn truth, thứ tự update, fallback khi Redis/DB lỗi và những endpoint bắt buộc kiểm tra fresh. Đối với quyền nguy hiểm, không mặc định **fail-open** khi policy service timeout.

## 13. Quan sát hiện trạng và xử lý sự cố

### 13.1. Vì sao user vẫn vào `/admin` sau khi bị thu hồi role?

Kiểm tra lần lượt:

1. Browser còn cookie/session nào? Có nhiều subdomain, nhiều session stores hoặc remember-me cookie không?
2. Request khớp `SecurityFilterChain` nào? Có chain khác `permitAll()` hoặc bỏ qua authorization không?
3. `SecurityContext` được lấy từ session cũ hay được tạo mới? Principal/authorities có đúng loại/nguồn không?
4. DB roles đã commit chưa, cache đã invalidated chưa?
5. Admin update có gọi revocation service và event có đến đủ node không?
6. Session registry có đăng ký đúng principal/session ID không? `maximumSessions` và event publisher đã cấu hình chưa?
7. Request sau revoke có chạy qua `ConcurrentSessionFilter` không?
8. Có JWT/token cũ chứa ROLE_ADMIN hoặc `scope=admin` vẫn chưa hết hạn không?
9. API có thực sự yêu cầu `hasRole("ADMIN")`/resource policy ở đúng endpoint không?
10. Có transaction đang chạy từ trước thời điểm thu hồi không?

**Không giải quyết bằng cách tăng session timeout đơn thuần**: timeout dài có thể làm cửa sổ dùng quyền cũ lâu hơn. Cần revocation/authorization chính xác.

### 13.2. Vì sao user không nhận được quyền vừa cấp?

Đó cũng có thể là session snapshot. Khi role nâng cấp, một lựa chọn an toàn là cho user đăng nhập lại hoặc reauthenticate; với cơ chế refresh authorities, phải bảo đảm cập nhật từ nguồn đáng tin cậy và persist SecurityContext đúng cách. Không cho client tự gửi role hoặc `authenticated=true` để lấy quyền mới.

### 13.3. SessionRegistry trống dù user đang đăng nhập

Các nguyên nhân thường gặp:

- Authentication mechanism tùy biến không gọi session authentication strategy/không register session.
- Ứng dụng dùng `STATELESS`, JWT/Bearer token và không có server-side HttpSession.
- Session registry không được truyền vào chain được dùng thật.
- Có nhiều registry bean/instance hoặc nhiều app nodes.
- Session hết hạn nhưng events/HttpSessionEventPublisher chưa đúng.
- Session được tạo trước khi bật tracking.
- Principal là custom object có equals/hashCode không ổn định.
- Login dùng một chain còn request ở chain khác.
- Test chỉ inject `@WithMockUser` nên không đi qua form login và không tạo session thật được registry biết.

**Một session registry không biết đến session thì không thể thu hồi session ấy.** Cần kiểm thử qua authentication flow thực hoặc thích hợp với deployment.

### 13.4. Session expired nhưng endpoint vẫn có 200

Kiểm tra:
- Request có đúng `JSESSIONID` bị đánh dấu không?
- Có filter `ConcurrentSessionFilter` ở chain đang nhận request không?
- Các request đi vào cùng registry/node hay shared registry chưa?
- Có một token khác trong header được filter xác thực lại và thay Authentication không?
- Có endpoint bypass chain hoặc static resource/CDN không?
- Request bắt đầu trước lệnh expire không?

Không kết luận `expireNow()` có hiệu lực lập tức chỉ từ việc object `SessionInformation.isExpired()` trả true. Phải kiểm tra request thực tế và thời điểm cutoff.

## 14. Trường hợp nào nên bắt buộc logout?

Một ma trận gợi ý để thiết kế policy (không phải chuẩn bắt buộc cho mọi sản phẩm):

| Sự kiện | Khuyến nghị |
| --- | --- |
| Thu hồi role quản trị hoặc permission nhạy cảm | Revoke session/token liên quan, đồng thời kiểm tra quyền live cho thao tác nhạy cảm |
| Account disabled/locked do sự cố bảo mật | Revoke trên mọi node/device, chặn login/refresh, audit |
| Password reset do nghi lộ | Revoke nhiều hoặc tất cả phiên/tokens theo policy, buộc xác thực lại |
| User được cấp quyền mới | Có thể re-login/reauth để lấy quyền mới; tránh tự cấp quyền không kiểm tra |
| Thay tên hiển thị/avatar | Thường không cần logout nếu không ảnh hưởng security identity |
| Đổi email/phone dùng cho recovery | Có thể cần step-up/MFA, audit và revoke theo mức rủi ro |
| Token JWT đã cấp sai scopes | Revoke/denylist hoặc hạ TTL; sửa issuer/claims để không phát lại |
| Service credential bị rò | Rotate/revoke client credentials, access/refresh tokens tương ứng |

Không nên áp dụng “mọi thay đổi account đều logout” nếu gây tác động lớn mà không cần thiết. Điều quan trọng là xác định **security relevant changes** và hiệu lực mong muốn.

## 15. Kiểm thử cần có trong dự án thật

Ngoài test demo, một hệ thống production nên test:

- **Role demotion:** user từng có ADMIN không còn được làm hành động admin trên session cũ sau revocation.
- **Role promotion:** session mới hoặc refresh mechanism nhận role mới; phiên cũ có behavior đúng policy.
- **Disable account:** đang có session và token, sau disable không thể tiếp tục thao tác bảo vệ; login/refresh bị từ chối.
- **Lock và unlock:** kiểm tra trạng thái login và policy xử lý session đã revoke; unlock không tự hồi sinh session đã thu hồi.
- **Đổi password:** password mới dùng được, password cũ bị từ chối; session/token policy nhất quán.
- **Multiple sessions/devices:** revoke tất cả hoặc trừ session hiện tại theo yêu cầu; không thu hồi nhầm account khác.
- **Multiple nodes:** revoke tại node A ảnh hưởng request trên B/C trong revocation SLA.
- **Remember-me:** cookie cũ không được âm thầm tạo lại access trái policy.
- **JWT:** access token đã phát, refresh token, token mới sau thay role, expiry, denylist/introspection.
- **Concurrent requests:** request đang chạy trước khi revoke, transaction commit và authorization guard.
- **Failure modes:** DB/cache/event bus lỗi, registry thiếu dữ liệu, duplicate revocation và retry/outbox.
- **Audit:** actor, target ID, reason, timestamp, số session/token affected, correlation ID và kết quả.

### 15.1. Không dùng mock user để chứng minh session revocation

`@WithMockUser` hay `SecurityMockMvcRequestPostProcessors.user(...)` tự dựng Authentication phục vụ kiểm thử authorization, không đi qua form login/dao provider, không tự register một HttpSession vào SessionRegistry.

Để test session revocation, hãy **đăng nhập qua POST /login với CSRF token và giữ MockHttpSession**, như phần 7. Sau đó đổi dữ liệu account, mark expired rồi gửi request lại với **cùng session ID**.

### 15.2. Đừng chỉ assert session flag

Một test chỉ gọi:

~~~java
SessionInformation info = registry.getSessionInformation(sessionId);
assertTrue(info.isExpired());
~~~

chứng minh registry đã được đánh dấu, nhưng **chưa chứng minh request thực tế không còn truy cập**. Test phần 7 còn gửi `GET /me` bằng session cũ, chờ redirect login. Với API trả JSON, hãy assert 401/error body chính xác theo `SessionInformationExpiredStrategy` đã cấu hình.

### 15.3. HTTP 401, 403 và 302 khác nhau

- `401 Unauthorized` thường dùng khi API cần xác thực hoặc credential thất bại.
- `403 Forbidden` thường là đã xác thực nhưng thiếu quyền, hoặc CSRF từ chối.
- `302`/`3xx` redirect tới login thường gặp với form login hoặc expired session strategy.

Bị lock trong DB không có nghĩa mọi request chắc chắn trả `401`. Với form login, authentication failure thường redirect; với session bị expire có thể redirect `/login?expired`. Hãy phân biệt **lỗi authentication**, **authorization** và **revoked session** trong tests/observability.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Alice có ROLE_ADMIN trong HttpSession; admin thu hồi role trong DB. `.hasRole("ADMIN")` có tự cập nhật theo DB không?

**Đáp:** Không mặc định. Nó thường đánh giá authorities của Authentication hiện tại, có thể vẫn là role cũ.

**Câu 2.** Khóa `enabled=false` có bắt mọi phiên đang mở logout ngay không?

**Đáp:** Không mặc định. Nó ảnh hưởng xác thực mới qua provider; phiên cũ cần revocation hoặc live check.

**Câu 3.** `UserDetailsService.loadUserByUsername` có được gọi ở mọi request trong session không?

**Đáp:** Không bảo đảm. Spring Security có thể phục hồi Authentication đã lưu từ HttpSession.

**Câu 4.** `SessionInformation.expireNow()` có lập tức dừng request đang chạy và xóa cookie ở trình duyệt không?

**Đáp:** Không. Nó mark expired; ConcurrentSessionFilter phát hiện ở request kế tiếp, xử lý logout/invalidation và trả response theo strategy.

**Câu 5.** Vì sao cần HttpSessionEventPublisher trong cấu hình session tracking?

**Đáp:** Để session events như destroy/expire được chuyển tới các thành phần theo dõi, giúp SessionRegistry duy trì thông tin vòng đời đúng.

**Câu 6.** Có phải `maximumSessions(1)` tự revoke user khi DB đổi quyền không?

**Đáp:** Không. Nó kiểm soát concurrent sessions; thay role phải phát sinh hành động revocation riêng nếu muốn.

**Câu 7.** SessionRegistryImpl trên node A có tự tìm được session của node B không?

**Đáp:** Không mặc định. Nó là in-memory registry; cần cơ chế cluster-aware hoặc store/event chung.

**Câu 8.** JWT chứa ROLE_ADMIN đã phát có tự đổi thành ROLE_USER khi DB đổi không?

**Đáp:** Không. Claims đã ký không thay đổi; cần expiry, revocation, introspection, version check hoặc live authorization.

**Câu 9.** Đổi password có tự hủy refresh tokens và remember-me cookies không?

**Đáp:** Không bảo đảm. Cần quản lý các token families, grants/cookies và revocation theo cơ chế thực tế.

**Câu 10.** Có thể chỉ dựa vào `authentication.isAuthenticated()` để biết user chưa bị khóa không?

**Đáp:** Không. Một Authentication cũ có thể báo true dù account DB đã disabled.

**Câu 11.** Dùng securityVersion giải quyết điều gì?

**Đáp:** Nó cho phép so trạng thái bảo mật lúc login với trạng thái hiện tại và từ chối context stale ngay tại điểm kiểm tra, nhưng cần nguồn version tin cậy và cache policy.

**Câu 12.** Nếu role mới được cấp, có nhất thiết phải “sửa object Authentication trong session” không?

**Đáp:** Không. Buộc login lại là một giải pháp rõ ràng; refresh Authentication chỉ nên thực hiện qua cơ chế tin cậy và persist context đúng cách.

**Câu 13.** Với giao dịch quan trọng, chỉ kiểm tra role ở HTTP filter có luôn đủ không?

**Đáp:** Chưa chắc. Cần quyền theo resource/tenant và có thể cần kiểm tra lại gần thời điểm transaction commit để giảm race.

**Câu 14.** Test bằng `@WithMockUser` có đủ chứng minh SessionRegistry revoke đúng không?

**Đáp:** Không. Mock user không đại diện full form-login/session-registration flow; cần test với session thật của MockMvc hoặc integration test.

**Câu 15.** Khi revoke event bị mất trên message broker, nên làm gì?

**Đáp:** Dùng transaction/outbox, retry/reconciliation hoặc live version check và thiết kế fail-closed cho action nhạy cảm.

## 17. Tài liệu tham khảo chính thức

- Spring Security 6.5 — **Authentication Persistence and Session Management**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — **Concurrent Session Control**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **UserDetailsService**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security 6.5 API — **SessionRegistry**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionRegistry.html
- Spring Security 6.5 API — **SessionInformation**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html
- Spring Security 6.5 API — **ConcurrentSessionFilter**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/session/ConcurrentSessionFilter.html
- Spring Session — **Spring Security Integration**: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- Spring Security — **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- OWASP — **Session Management Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Ghi nhớ:** Thay đổi role hoặc khóa account trong nguồn user **không tự thay đổi Authentication đã nằm trong phiên**. Với ứng dụng session, quản lý và thu hồi các session được theo dõi qua SessionRegistry/ConcurrentSessionFilter, hoặc kiểm tra securityVersion/account status trên request. Với JWT và hệ thống nhiều node phải có revocation/validation riêng. **Thu hồi quyền nhạy cảm cần được kiểm chứng bằng request thực tế trên phiên hoặc token cũ**, không chỉ bằng việc DB đã update.
