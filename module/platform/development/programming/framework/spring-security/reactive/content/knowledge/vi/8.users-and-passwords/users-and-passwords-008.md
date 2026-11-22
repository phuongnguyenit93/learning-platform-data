# Tách vai trò, quyền và dữ liệu hồ sơ trong principal

## 1. Vấn đề: đừng biến principal thành “hồ sơ người dùng toàn năng”

Trong Spring Security reactive (Spring WebFlux), đăng nhập bằng tên người dùng và mật khẩu tạo ra một `Authentication` đã xác thực. Đối tượng này chứa `principal` (danh tính), `credentials` (bằng chứng xác thực, thường được xóa sau khi dùng) và `authorities` (các `GrantedAuthority`). Ứng dụng lại còn có nhiều dữ liệu nghiệp vụ: tên hiển thị, email, địa chỉ, avatar, phòng ban, tùy chọn giao diện, trạng thái hợp đồng...

**Không nên gộp tất cả thành một principal rồi truyền đi khắp hệ thống.** Một thiết kế an toàn tách ba nhóm:

1. **Danh tính/đăng nhập:** ai đang đăng nhập, tài khoản có hợp lệ không, kiểm chứng password hash thế nào?
2. **Vai trò và quyền:** principal đã được cấp những quyền nào để Spring Security thực thi authorization?
3. **Dữ liệu hồ sơ:** thông tin nghiệp vụ cần đọc/cập nhật theo từng use case, có kiểm soát người sở hữu và quyền truy cập riêng.

Mục tiêu:
- Phân biệt `Authentication`, `principal`, `UserDetails`, `GrantedAuthority`, role, permission, profile.
- Biết rõ nơi lưu **password hash**, nơi trả **authorities** và nơi tải **profile**.
- Tránh đưa email, địa chỉ hoặc dữ liệu nhạy cảm không cần thiết vào principal/session/JWT.
- Hiểu `hasRole` so với `hasAuthority`, cơ chế `ROLE_` và lỗi ghi đè authorities khi dùng `User.UserBuilder`.
- Viết được ứng dụng Spring Boot WebFlux Java 17+ dùng `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `SecurityWebFilterChain`, Reactor Context và dịch vụ profile riêng.
- Kiểm thử 200/401/403, tránh để lộ password, và phân biệt quyền theo chức năng với quyền truy cập dữ liệu của chính mình.

## 2. Ba lớp dữ liệu nên tách biệt

~~~text
                        HTTP Basic username/password
                                    │
                                    ▼
                    ReactiveAuthenticationManager
                                    │
                     ReactiveUserDetailsService
                                    │
                    Account / Credential store
                   ┌──────────────────────────┐
                   │ accountId, username      │
                   │ passwordHash, enabled... │
                   │ roles + permissions      │
                   └──────────────────────────┘
                                    │
                     Kiểm tra hash, tài khoản...
                                    ▼
                    Authentication (đã xác thực)
                   ┌──────────────────────────┐
                   │ principal: UserDetails   │
                   │ authorities: Granted...  │
                   │ credentials: giảm/xóa    │
                   └──────────────────────────┘
                                    │
                    SecurityContext / Reactor Context
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
        AuthorizationWebFilter                     Controller/Service
        hasRole / hasAuthority                  Lấy identity đã xác minh
                                                        │
                                                        ▼
                                                Profile service
                                                theo accountId
                                                        │
                                                        ▼
                                           Profile DTO đúng nhu cầu
                                           (displayName, email...)
~~~

Các khái niệm:

| Khái niệm | Mục đích | Chứa gì? | Không nên chứa gì? |
| --- | --- | --- | --- |
| **Account record** | Nguồn dữ liệu đăng nhập | ID ổn định, username, password hash, trạng thái khóa tài khoản, quan hệ roles/permissions | Mật khẩu plaintext |
| **`UserDetails`** | Phép chiếu cho username/password authentication | Username, password hash dùng để kiểm tra, enabled/locked, granted authorities | Toàn bộ hồ sơ, lịch sử giao dịch, secrets không cần |
| **`Authentication.principal`** | Biểu diễn danh tính trong request đã xác thực | `UserDetails`, `Jwt` hoặc principal tùy cơ chế | Mọi trường dữ liệu hồ sơ theo thói quen |
| **`Authentication.authorities`** | Quyền được framework dùng để authorize | Các `GrantedAuthority` như `ROLE_USER`, `profile:read` | Danh sách quyền lấy nguyên văn từ payload chưa xác minh |
| **Profile entity/service** | Dữ liệu nghiệp vụ có thể thay đổi | Tên, email liên hệ, avatar, ngôn ngữ, địa chỉ... | Password hash hoặc cấu hình xác thực |
| **HTTP response DTO** | Hợp đồng API public có chủ ý | Chỉ các trường client được phép biết | `Authentication`/`UserDetails` nguyên object |

**Điểm tinh tế:** `UserDetails` chuẩn *có* phương thức `getPassword()` và thường chứa **password hash** để manager so sánh. “Principal tối thiểu” không có nghĩa mọi implementation phải tuyệt đối không giữ hash lúc đang xác thực; nó có nghĩa **chỉ giữ dữ liệu framework thực sự cần, không nhét thêm profile**, và **không xuất principal/UserDetails trực tiếp ra HTTP, log hoặc sự kiện**. Một `Authentication` sau xác thực có thể đã xóa credentials, nhưng không dùng điều đó làm lý do để serialize cả principal.

## 3. `Authentication`, `principal` và `SecurityContext` không phải cùng một đối tượng

`SecurityContext` giữ `Authentication` hiện tại. `Authentication` có các API:

~~~java
Object principal = authentication.getPrincipal();
Object credentials = authentication.getCredentials();
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
String name = authentication.getName();
boolean authenticated = authentication.isAuthenticated();
~~~

Phần code trên minh họa interface, cần biến `Authentication authentication` đã được xác thực. Giải thích:

- `principal` trả lời **“ai?”**; với username/password thường là `UserDetails`, nhưng JWT/OIDC có thể khác.
- `credentials` là bằng chứng (password/token) dùng trong quá trình xác thực; sau thành công có thể là `null`. Không đọc rồi trả nó ra JSON.
- `authorities` là danh sách quyền đã cấp, *không phải* profile.
- `getName()` là cách lấy tên định danh chung qua `java.security.Principal`, nhưng username có thể thay đổi nên không mặc định dùng làm khóa định danh vĩnh viễn.
- `isAuthenticated()` chỉ mô tả trạng thái token; không thay `hasRole`/`hasAuthority`. Anonymous token trong Spring Security có thể có cờ true, nên không viết bảo vệ endpoint chỉ dựa vào cờ này.

Trong reactive WebFlux, context được truyền qua **Reactor Context** của subscription:

~~~java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Đây là publisher chứ không phải getter đồng bộ. Trong handler reactive, không gọi `.block()`, không tự `subscribe()` và không phụ thuộc `SecurityContextHolder` ThreadLocal kiểu Servlet. Hãy tiếp tục bằng `map`/`flatMap`.

## 4. Vai trò (role), quyền chi tiết (permission) và hồ sơ (profile)

### 4.1. Vai trò: phân nhóm trách nhiệm

Role là nhóm quyền ở mức chức năng. Ví dụ:
- `USER`: người dùng thông thường.
- `ADMIN`: người quản trị.
- `AUDITOR`: người xem dữ liệu kiểm toán.

Theo quy ước Spring Security, `hasRole("ADMIN")` thường đối chiếu một `GrantedAuthority` có chuỗi `"ROLE_ADMIN"`. Mỗi vai trò không phải là một đối tượng profile: thay đổi tên hiển thị không khiến người đó thành ADMIN, và trở thành ADMIN không có nghĩa được xem mọi dữ liệu cá nhân của người khác.

### 4.2. Permission: thao tác cụ thể

Permission diễn tả quyền thao tác gắn với tài nguyên/chức năng:

- `profile:read`: được truy cập API đọc profile theo chính sách.
- `profile:write`: có quyền thao tác cập nhật profile khi vượt qua các kiểm tra bổ sung.
- `reports:read`: được gọi API xem báo cáo.
- `users:manage`: được quản lý tài khoản trong phạm vi được cấp.

Trong demo, quyền `profile:read` không tự phát sinh từ `ROLE_USER`: chúng là các authority **độc lập**. Hệ thống thật có thể định nghĩa role→permission ở backend, sau đó expand để tạo `GrantedAuthority`, hoặc kiểm tra permission trong một authorization service. Quan hệ này phải **được backend kiểm soát**, không lấy nguyên quyền từ client.

### 4.3. Profile: dữ liệu nghiệp vụ, không phải quyền

Profile gồm `displayName`, `contactEmail`, `avatarUrl`, `timezone`, `locale`, v.v. Nó có thể đổi mà không yêu cầu người dùng đăng nhập lại. Không nên gán các trường này thành `GrantedAuthority` hoặc đọc chúng từ `Authentication.getCredentials()`.

**Khuyến nghị kiến trúc:** principal chỉ giữ danh tính tối thiểu; profile được tải bởi service riêng **khi endpoint cần**. Ví dụ `GET /api/profile` phải dùng danh tính **đã được xác minh** từ context để tìm account/profile tương ứng; không lấy `username` tùy ý từ query parameter làm chủ sở hữu.

### 4.4. Role, permission và quyền sở hữu dữ liệu là ba thứ khác nhau

`hasAuthority("profile:read")` có thể cho phép truy cập chức năng **đọc profile**, nhưng chưa chắc cho phép đọc profile của **mọi người dùng**. Nếu endpoint là `GET /api/profiles/{accountId}`, vẫn phải kiểm tra `requestedAccountId == authenticatedAccountId` hoặc một quy tắc phân quyền bổ sung, bao gồm tenant và policy phù hợp.

Ví dụ:

| Đối tượng | Role/permission | Có thể làm gì? |
| --- | --- | --- |
| Reader A | `ROLE_USER`, `profile:read` | Đọc profile **của A** sau khi xác định ownership |
| Reader B | `ROLE_USER`, `profile:read` | Không tự nhiên được đọc profile của A |
| Admin | `ROLE_ADMIN`, `profile:read`, `reports:read` | Có thể xem báo cáo, nhưng quyền đọc profile người khác còn tùy policy |
| Guest | Không xác thực | Chỉ vào các endpoint `permitAll` |

Phân quyền chức năng (**RBAC**) và phân quyền theo đối tượng/dữ liệu (**ownership, tenant, ABAC**) bổ sung cho nhau. Đừng hiểu role ADMIN là mặc định bỏ qua mọi điều kiện tenant hoặc bảo mật dữ liệu cá nhân.

## 5. Chuyển role và permission thành `GrantedAuthority`

Spring Security đại diện role lẫn permission bằng `GrantedAuthority`. Kiểu thông dụng là `SimpleGrantedAuthority`:

~~~java
new SimpleGrantedAuthority("ROLE_USER");
new SimpleGrantedAuthority("profile:read");
new SimpleGrantedAuthority("reports:read");
~~~

Các rule:

~~~java
.pathMatchers("/api/admin").hasRole("ADMIN")
.pathMatchers("/api/reports").hasAuthority("reports:read")
.pathMatchers("/api/profile").hasAuthority("profile:read")
~~~

- `hasRole("ADMIN")` sẽ yêu cầu `ROLE_ADMIN` theo quy ước mặc định.
- `hasAuthority("reports:read")` so khớp chuỗi **chính xác**, không tự thêm `ROLE_`.
- `hasRole("ROLE_ADMIN")` không phải kiểu sử dụng thông thường và có thể bị phản đối do trùng prefix, tùy API/phiên bản.
- Trong dự án dùng tiền tố role tùy biến, điều kiện match cần theo đúng cấu hình, không giả định mọi nơi luôn là `ROLE_`.
- Permission như `SCOPE_orders.read` trong resource server có thể đến từ scope JWT/OAuth2 qua converter; không đồng nhất với permission nghiệp vụ `orders:read` nếu chưa thiết kế mapping.

### 5.1. Lỗi rất phổ biến với `User.UserBuilder`

`User.withUsername(...).roles(...)` là cách viết tắt của `authorities(...)` có thêm `ROLE_`. **Nếu gọi `.roles(...)` rồi tiếp tục `.authorities(...)`, builder có thể thay thế tập authority vừa thiết lập chứ không hợp nhất**.

~~~java
// Không nên giả định sẽ có cả ROLE_USER và profile:read:
User.withUsername("reader")
    .password(encodedPassword)
    .roles("USER")
    .authorities("profile:read")
    .build();
~~~

Cách ổn định: tạo **một tập authority hoàn chỉnh**, rồi gọi `authorities(...)` đúng một lần:

~~~java
List<String> granted = new ArrayList<>();
granted.add("ROLE_USER");
granted.add("profile:read");

UserDetails user = User.withUsername("reader")
    .password(encodedPassword)
    .authorities(granted.toArray(String[]::new))
    .build();
~~~

Với ứng dụng thật, cần có nguồn role/permission đáng tin cậy, kiểm soát namespace, tránh trùng và cập nhật chính sách đồng bộ. Không gửi xuống client một API để khách tự chọn authority của mình.

### 5.2. Không phải roles hay permissions nào cũng nên embed lâu dài

Tập quyền có thể thay đổi (bị thu hồi quyền admin, chuyển phòng ban, đóng tài khoản). Khi role/permission được chụp vào session hoặc JWT sống lâu, quyết định authorization có thể dùng dữ liệu **cũ** cho tới khi login lại, token hết hạn hoặc có cơ chế refresh/invalidation.

Giải pháp tùy mô hình:
- Token ngắn hạn, kiểm tra signature/issuer/audience và cơ chế refresh/revocation thích hợp.
- Session invalidation hoặc refresh authorities sau khi đổi quyền.
- Permission service theo request đối với những quyền nhạy cảm/cần dữ liệu mới.
- Version quyền hoặc sự kiện thay đổi policy để invalid cache có kiểm soát.

**Không** đồng bộ toàn bộ profile vào JWT chỉ để frontend đỡ gọi API: payload có thể lộ ra nơi khác, trở nên lỗi thời và khó thu hồi. Nếu cần một số claim cần thiết cho authorization, giới hạn chúng ở dữ liệu thực sự cần và có chính sách cập nhật rõ ràng.

## 6. Kiến trúc tài khoản và hồ sơ riêng biệt

Trong ứng dụng thật, bạn có thể thiết kế bảng/collection theo hướng:

~~~text
accounts:
  id, username, password_hash, enabled, locked, credential_version

account_roles:
  account_id, role_code

account_permissions:
  account_id, permission_code

profiles:
  account_id, display_name, contact_email, avatar_url, locale, ...
~~~

Đây là **mô hình minh họa**, không phải schema bắt buộc. Có thể lưu roles/permissions trong nhiều bảng/identity provider khác nhau; vấn đề là trách nhiệm phải được tách biệt.

Tại thời điểm đăng nhập:
1. Converter/filter lấy username/password do người dùng cung cấp.
2. `ReactiveUserDetailsService` tìm account, cung cấp `UserDetails` với password hash, trạng thái enabled/locked và authorities được hệ thống xác định.
3. `ReactiveAuthenticationManager` so sánh password bằng `PasswordEncoder` và xác minh trạng thái account.
4. `Authentication` đã xác thực được đưa vào `SecurityContext` của request.
5. `SecurityWebFilterChain` dùng authorities để quyết định route có được truy cập không.
6. Chỉ khi handler cần profile, service mới tra profile bằng **account ID lấy từ identity đáng tin cậy**. Trong demo dùng username đã xác minh để tra account ID; production nên dùng immutable ID cùng tenant key nếu có.

Cách này giúp thay email/tên hiển thị không ảnh hưởng đến xác thực, và cập nhật authorities không cần cập nhật bản ghi profile. Ngược lại, thay password không buộc phải sửa bảng profile.

## 7. Ví dụ hoàn chỉnh Java 17+: WebFlux username/password và profile service riêng

Ví dụ sử dụng **Spring Boot 3.3.13**, Spring Security WebFlux do Boot quản lý phiên bản, Java 17+, Gradle 8.x. Đây là phiên bản **để cố định môi trường học và tái lập API**, không phải khuyến nghị dùng bản đã hết vòng hỗ trợ OSS cho production. Khi triển khai thật, hãy dùng dòng Spring Boot đang được hỗ trợ, cập nhật dependency và chạy lại kiểm thử.

Demo có hai tài khoản:
- `reader` / `reader-pass`: `ROLE_USER` + `profile:read`.
- `admin` / `admin-pass`: `ROLE_ADMIN` + `profile:read` + `reports:read`.

Các password chỉ dùng trong local demo. Profile tách hẳn khỏi object principal. Tất cả endpoint demo dùng GET để tránh làm lẫn nội dung với chính sách CSRF cho các thao tác ghi dữ liệu.

### 7.1. Cấu trúc thư mục

~~~text
reactive-principal-separation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PrincipalSeparationApplication.java
    │   ├── DemoAccountStore.java
    │   ├── ProfileView.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── SeparationTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-principal-separation'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dependency management của Boot chọn các phiên bản Spring Security/Reactor tương thích. Không trộn Spring MVC `HttpSecurity` với Spring WebFlux `ServerHttpSecurity` trong ví dụ này.

### 7.2. Lớp khởi chạy

`src/main/java/demo/PrincipalSeparationApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrincipalSeparationApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalSeparationApplication.class, args);
    }
}
~~~

### 7.3. DTO profile: không chứa password hoặc authorities

`src/main/java/demo/ProfileView.java`:

~~~java
package demo;

public record ProfileView(
    String displayName,
    String contactEmail
) {}
~~~

Đây là DTO có mục đích cụ thể cho API `/api/profile`, không phải principal hay authentication token. Email là dữ liệu cá nhân, chỉ được trả cho **chính chủ** theo yêu cầu truy cập trong demo. Ở production cần quản lý consent, ẩn một phần thông tin hoặc lọc theo vai trò và quy định bảo vệ dữ liệu thích hợp.

### 7.4. Store demo tách account khỏi profile

`src/main/java/demo/DemoAccountStore.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class DemoAccountStore {

    // Dữ liệu dành cho authN/authZ, không có displayName/email.
    record AccountRow(
        String id,
        String username,
        String passwordHash,
        Set<String> roles,
        Set<String> permissions
    ) {}

    private final Map<String, AccountRow> accountsByUsername;
    private final Map<String, ProfileView> profilesByAccountId;

    DemoAccountStore(PasswordEncoder encoder) {
        AccountRow reader = new AccountRow(
            "u-100",
            "reader",
            encoder.encode("reader-pass"),
            Set.of("USER"),
            Set.of("profile:read")
        );

        AccountRow admin = new AccountRow(
            "u-200",
            "admin",
            encoder.encode("admin-pass"),
            Set.of("ADMIN"),
            Set.of("profile:read", "reports:read")
        );

        this.accountsByUsername = Map.of(
            reader.username(), reader,
            admin.username(), admin
        );

        // Hồ sơ được lưu riêng theo ID account ổn định.
        this.profilesByAccountId = Map.of(
            "u-100",
            new ProfileView("Người đọc", "reader@example.invalid"),
            "u-200",
            new ProfileView("Người quản trị", "admin@example.invalid")
        );
    }

    Mono<AccountRow> findAccount(String username) {
        return Mono.justOrEmpty(accountsByUsername.get(username));
    }

    Mono<ProfileView> profileForAuthenticatedUsername(String username) {
        return findAccount(username)
            .flatMap(account ->
                Mono.justOrEmpty(profilesByAccountId.get(account.id())));
    }
}
~~~

Từng bộ dữ liệu có trách nhiệm rõ ràng:
- `AccountRow.id` là định danh nội bộ ổn định; quan hệ profile dựa vào ID này.
- `AccountRow.passwordHash` dùng để so sánh mật khẩu khi xác thực, không phải thông tin hiển thị.
- `roles` và `permissions` tách riêng trong dữ liệu domain, chỉ được chuyển thành `GrantedAuthority` khi dựng `UserDetails`.
- `ProfileView` nằm trong store khác về ý nghĩa; demo giữ trong một component cho ngắn gọn, nhưng ứng dụng thực tế nên có **AccountRepository** và **ProfileRepository/Service** tách cấu trúc.
- `Mono.justOrEmpty(...)` chạy ngay với `Map` trong bộ nhớ. Nếu chuyển sang R2DBC/reactive driver, hãy trả trực tiếp publisher từ repository. **Không** đặt JDBC blocking call bên trong `Mono.just(...)` rồi gọi nó trên event loop.

Email `example.invalid` là địa chỉ giả hợp lệ cho mục đích minh họa, không gửi email thật.

### 7.5. Cấu hình `ReactiveUserDetailsService` và bảo mật WebFlux

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(DemoAccountStore store) {
        return username -> store.findAccount(username)
            .map(account -> {
                List<String> authorities = new ArrayList<>();

                // ROLE_ là prefix mặc định của hasRole(...).
                account.roles().stream()
                    .map(role -> "ROLE_" + role)
                    .forEach(authorities::add);

                // Permission giữ nguyên chuỗi, không prefix ROLE_.
                authorities.addAll(account.permissions());

                return User.withUsername(account.username())
                    .password(account.passwordHash())
                    // Gọi authorities đúng một lần với tập hợp đầy đủ.
                    .authorities(authorities.toArray(String[]::new))
                    .build();
            });
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);

        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/reports")
                    .hasAuthority("reports:read")
                .pathMatchers("/api/profile")
                    .hasAuthority("profile:read")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

**Cơ chế chính:**
1. `ReactiveUserDetailsService` là giao diện chuyển username thành `Mono<UserDetails>`. Nó không trả profile; chỉ trả dữ liệu xác thực/authorities cần thiết.
2. `passwordHash` đi vào `UserDetails` để manager dùng `PasswordEncoder.matches(...)` kiểm chứng mật khẩu do client cung cấp. Password được tạo bằng BCrypt trong demo, **không** so sánh plaintext string.
3. Tập authorities gồm cả role (đã thêm `ROLE_`) và permission (chuỗi riêng), không dùng `roles(...).authorities(...)` nối tiếp nhau.
4. `UserDetailsRepositoryReactiveAuthenticationManager` dùng `ReactiveUserDetailsService` và encoder để xác thực Basic. Token `Authentication` thành công được framework đưa vào security context cho request.
5. `SecurityWebFilterChain` chỉ định quyền HTTP. `hasRole` và `hasAuthority` đánh giá tập quyền, không truy cập profile.
6. `httpBasic(...)` cho phép dùng credentials ở header Authorization; `formLogin(...disable())` giúp client API chưa đăng nhập nhìn thấy 401 thay vì redirect trong demo.
7. `anyExchange().denyAll()` không ngầm cho phép endpoint lạ. Trong production, mở các endpoint cần thiết (health, docs...) bằng rule cụ thể trước rule cuối.
8. `@EnableWebFluxSecurity` làm rõ cấu hình reactive. Spring Boot với Security starter thường có auto-configuration tương ứng; annotation không tự cấp quyền nào.

**Giới hạn cần biết:** Hai tài khoản mẫu không có trạng thái disabled/locked. `UserDetails` thực tế còn biểu diễn flags enabled, accountNonLocked, credentialsNonExpired, accountNonExpired. Cần phản ánh chúng theo account record, không chỉ kiểm tra password đúng.

### 7.6. Controller chỉ thấy danh tính và DTO đủ dùng

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record IdentityView(
        String username,
        List<String> authorities
    ) {}

    private final DemoAccountStore store;

    DemoController(DemoAccountStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    // DTO danh tính + quyền; KHÔNG trả nguyên Authentication/UserDetails.
    @GetMapping("/api/me")
    Mono<IdentityView> identity() {
        return currentAuthentication().map(auth -> {
            List<String> granted = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

            return new IdentityView(auth.getName(), granted);
        });
    }

    // Profile chỉ được tải khi người dùng đã qua authorization
    // và theo username ĐÃ XÁC THỰC, không theo ID từ client.
    @GetMapping("/api/profile")
    Mono<ProfileView> myProfile() {
        return currentAuthentication()
            .flatMap(auth ->
                store.profileForAuthenticatedUsername(auth.getName()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    @GetMapping("/api/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin");
    }

    @GetMapping("/api/reports")
    Mono<String> reportsOnly() {
        return Mono.just("reports");
    }

    private Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
    }
}
~~~

**Điểm phân tách quan trọng:**
- `/api/me` trả **IdentityView** chứa tên định danh và danh sách authorities để minh họa. Không trả raw password, password hash, credentials, details hay toàn bộ `UserDetails`.
- `/api/profile` chỉ được truy cập khi có permission `profile:read`. Controller lấy username từ `Authentication` đã được framework xác minh, rồi store tìm **account ID nội bộ** trước khi lấy profile tương ứng.
- `ProfileView` không được “nhét” vào principal. Khi thông tin hồ sơ thay đổi, endpoint có thể đọc bản mới theo chính sách cache.
- `/api/admin` đòi role ADMIN; `/api/reports` đòi permission reports:read. Hai điều kiện không đồng nghĩa nhau.
- `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` trên Reactor Context. Không gọi `block()` trong WebFlux handler; để Spring Security điều phối subscription.
- `switchIfEmpty` trong controller phòng vệ khi không có context/profile; phần lớn request thiếu xác thực bị bảo mật HTTP từ chối trước đó.

**Ranh giới sản phẩm:** Trong ví dụ, endpoint `/api/me` trả authorities để dễ học. Ứng dụng thật không nhất thiết công khai toàn bộ quyền nội bộ; một DTO phục vụ giao diện chỉ nên chứa những capability flags thực sự cần, và frontend không bao giờ là nơi quyết định quyền cuối cùng.

## 8. Kiểm tra bằng HTTP

Chạy trong thư mục `reactive-principal-separation`:

~~~bash
gradle bootRun
~~~

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. JDK 17+, Gradle 8.x và quyền tải dependency qua mạng là các điều kiện ban đầu.

Sau khi server chạy mặc định ở `localhost:8080`, dùng bash/Git Bash:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -u reader:reader-pass http://localhost:8080/api/me
curl -s -u reader:reader-pass http://localhost:8080/api/profile
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/reports
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/reports
curl -s -u reader:wrong -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
~~~

Các mã HTTP của lệnh **1, 2, 5, 6, 7, 8, 9** theo đúng thứ tự:

~~~text
200
401
403
403
200
200
401
~~~

Lệnh 3 trả dữ liệu `IdentityView` dạng sau (thứ tự key JSON có thể thay đổi):

~~~json
{
  "username": "reader",
  "authorities": [
    "ROLE_USER",
    "profile:read"
  ]
}
~~~

Lệnh 4 trả dữ liệu **profile riêng** dạng:

~~~json
{
  "displayName": "Người đọc",
  "contactEmail": "reader@example.invalid"
}
~~~

Điểm kiểm chứng:
- Dữ liệu profile không xuất hiện trong `IdentityView`.
- Password, password hash và raw HTTP Basic credentials không xuất hiện trong cả hai response.
- `reader` đã đăng nhập nhưng thiếu role ADMIN và permission reports:read nên nhận **403** ở hai endpoint nhạy cảm.
- Password sai dẫn tới **401**.
- Admin có `ROLE_ADMIN` và `reports:read`, vì thế hai URL tương ứng được 200.

Trên PowerShell, dùng `curl.exe` nếu `curl` là alias. Một số môi trường Windows cần thay `/dev/null` bằng `NUL`. Với HTTP Basic, sử dụng TLS/HTTPS ngoài môi trường local; thông tin username/password được truyền trong Authorization header, **không phải** mã hóa bí mật bởi Basic.

## 9. Kiểm thử tự động: role, permission và profile phải tách nhau

`src/test/java/demo/SeparationTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SeparationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicIsOpenButIdentityNeedsAuthentication() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerIdentityContainsAuthoritiesButNoProfileOrPassword() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("reader")
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_USER")
            .jsonPath("$.authorities[1]").isEqualTo("profile:read")
            .jsonPath("$.contactEmail").doesNotExist()
            .jsonPath("$.password").doesNotExist()
            .jsonPath("$.passwordHash").doesNotExist();
    }

    @Test
    void readerGetsOnlyTheirOwnProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.displayName").isEqualTo("Người đọc")
            .jsonPath("$.contactEmail")
                .isEqualTo("reader@example.invalid")
            .jsonPath("$.password").doesNotExist()
            .jsonPath("$.passwordHash").doesNotExist();
    }

    @Test
    void ordinaryUserHasNeitherAdminRoleNorReportPermission() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminHasRoleAndExplicitReportPermission() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports");
    }

    @Test
    void incorrectPasswordDoesNotProduceTrustedPrincipal() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc dùng wrapper tương ứng. Kỳ vọng sáu test pass; `gradle test` kết thúc với exit code 0. Log Gradle, thời gian và dòng tổng kết phụ thuộc môi trường, nên không xác định trước chính xác nguyên văn stdout.

Test giúp bắt những lỗ hổng thực tế:
1. **Thiếu authentication** không vào được `/api/me` (401).
2. **Principal/Identity DTO** không rò rỉ hash, mật khẩu, email.
3. **Profile** được tải riêng theo danh tính reader đã xác minh.
4. **Role** và **permission** không bị coi là một thứ.
5. **User thường** không có quyền admin hay xem báo cáo (403).
6. **Mật khẩu sai** không tạo danh tính đáng tin cậy (401).

Các test không kiểm chứng toàn bộ cơ chế ownership cho URL lấy account ID tùy ý, vì demo cố tình không có URL như thế. Nếu thêm `/api/profiles/{id}`, bắt buộc viết test user A cố đọc profile B và đảm bảo policy từ chối.

## 10. Nếu cần custom principal mang accountId bất biến

Ví dụ ở mục 7 dùng `org.springframework.security.core.userdetails.User`; `getName()` trả username. Nó phù hợp cho demo nhưng username có thể thay đổi, làm khóa truy vấn profile kém ổn định.

Trong ứng dụng production, có thể tạo **principal tối thiểu riêng** chỉ chứa ID ổn định, username, tenant ID cần thiết, thông tin tài khoản ở mức tối thiểu. Ví dụ **mô hình minh họa, không thay thế trực tiếp các file runnable ở trên**:

~~~java
public record ActorIdentity(
    String accountId,
    String username,
    String tenantId
) {}
~~~

Sau khi authentication manager đã xác minh password/token, nó có thể xây `Authentication` đã tin cậy với principal loại `ActorIdentity` và authorities do backend xác định. Khi đó service truy vấn profile bằng `accountId`, kiểm tra `tenantId` tại biên truy cập dữ liệu:

~~~java
Authentication trusted =
    UsernamePasswordAuthenticationToken.authenticated(
        new ActorIdentity("u-100", "reader", "tenant-1"),
        null, // Không giữ raw password trong token thành công.
        grantedAuthoritiesFromServer
    );
~~~

**Giải thích ranh giới:** Đoạn trên là minh họa cách **manager tạo authentication sau khi đã kiểm tra bằng chứng**, không được gọi `authenticated(...)` trực tiếp trên dữ liệu request chưa xác minh. `grantedAuthoritiesFromServer` là tập `Collection<? extends GrantedAuthority>` do backend xác định, không phải biến có sẵn trong dự án demo.

Trong custom `UserDetails` dùng cho username/password, có thể cần các phương thức của giao diện `UserDetails` như `getUsername()`, `getPassword()`, `getAuthorities()` và các trạng thái account. `ActorIdentity` đơn thuần là object principal tối thiểu của **kết quả xác thực**, không tự thay thế đầy đủ `UserDetails`. Không làm lẫn mô hình minh họa này với lớp Spring `User` trong project runnable.

### 10.1. Multi-tenant không thể chỉ gắn tenantId vào principal rồi tin tuyệt đối

Nếu một request có path `/tenants/{tenantId}/data`, bạn phải kiểm tra identity đã được xác minh thuộc tenant ấy và policy cấp quyền cho thao tác tương ứng. Tenant ID trong JWT cũng phải đến từ issuer/claim **đã được xác minh**, không lấy từ header `X-Tenant` do client tự nhập rồi tin mặc định.

Role `ADMIN` trong tenant A không suy ra có quyền admin tenant B. Một thiết kế cụ thể có thể gắn grants theo tenant, hoặc dùng authorization service có scope, thay vì một role toàn cục vượt mọi ranh giới.

### 10.2. Phân biệt “danh tính hiển thị” với “danh tính quyết định quyền”

`displayName`, email, ảnh đại diện là dữ liệu hiển thị. `accountId` là khóa ổn định cho quan hệ nghiệp vụ. `getName()` trong authentication có thể là username hoặc subject tùy cơ chế. Chỉ dùng khóa từ **identity provider/account store đã xác minh**, không dùng tên hiển thị làm khóa bảo mật.

## 11. Cập nhật role/permission và profile khi đang đăng nhập

Hai loại cập nhật có vòng đời khác nhau:

**Thay đổi profile** (`displayName`, email liên hệ):
- Service cập nhật record profile và kiểm tra ownership/permission.
- Ứng dụng đọc profile mới tại lần request tiếp theo (tùy cache).
- Không cần thay toàn bộ `Authentication` chỉ vì tên hiển thị đổi; principal vốn không chứa profile.

**Thay đổi role/permission** (thu hồi ADMIN, cấp quyền reports:read):
- Cập nhật nguồn quyền được backend tin cậy.
- Xem xét authentication/session/JWT đã phát trước đó có **authorities snapshot** hay không.
- Thiết kế refresh, token TTL, revocation hoặc live permission check tương ứng với mức độ nhạy cảm.
- Kiểm thử rằng sau khi thu hồi quyền, user không còn truy cập được tài nguyên trong khoảng thời gian policy cho phép.

**Thay đổi password hoặc khóa tài khoản**:
- Hash lại password bằng thuật toán đã cấu hình, không lưu plaintext.
- Cân nhắc vô hiệu hóa session/token hiện hành khi chính sách yêu cầu.
- Không ghi password mới vào profile hay trả password hash cho client.

Ba vòng đời này cần tách riêng để tránh việc một chỉnh sửa hồ sơ vô hại vô tình đẩy quyền mới vào các token đang hoạt động, hoặc việc thu hồi quyền chỉ có hiệu lực khi hồ sơ được cập nhật.

## 12. Tại sao không nên serialize `UserDetails`/`Authentication` ra JSON?

Đôi khi developer viết:

~~~java
@GetMapping("/me")
Mono<Authentication> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
~~~

**Không nên dùng đoạn này làm endpoint thực tế.** Object authentication có thể chứa principal của cơ chế cụ thể, authorities, details, và trong một số giai đoạn hoặc implementation còn chứa credentials hoặc password-related fields. Kết quả JSON thay đổi theo thư viện, dễ tiết lộ trường ngoài ý muốn, tạo coupling API với Spring Security và ảnh hưởng dữ liệu cá nhân.

Thay bằng **DTO allowlist** do bạn kiểm soát: chỉ tên hiển thị/định danh được phép, capability cần client biết, hoặc profile view đúng nhu cầu. Đừng rely vào `@JsonIgnore` đặt rải rác trên các object framework như biện pháp bảo vệ duy nhất; tốt hơn là không đưa object security qua HTTP boundary.

Với logging và telemetry cũng vậy:
- Không log `getCredentials()`, raw token, Authorization header.
- Không log nguyên `principal.toString()` khi chưa biết các trường trong implementation.
- Ghi trace ID, mã lỗi, ID nội bộ đã pseudonymize theo policy, và tên quyền được kiểm soát khi cần quan sát.
- Quy định rõ thời gian lưu log, quyền đọc log và dữ liệu được phép xử lý.

## 13. Lỗi thường gặp, cách nhận biết và khắc phục

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Đưa `displayName`, email, địa chỉ vào `UserDetails` chỉ để mọi service đọc tiện | Rò rỉ PII, principal/session cũ, coupling giữa auth và nghiệp vụ | Giữ principal tối thiểu, tải profile qua service riêng |
| Dùng một DTO chứa cả `passwordHash` và profile rồi trả client | Lộ thông tin xác thực | Dùng DTO response riêng, không expose entity |
| Gọi `.roles("USER").authorities("profile:read")` và tưởng là hợp nhất | Role có thể bị thay thế → 403 không mong muốn | Kết hợp role + permission, gọi `authorities(...)` một lần |
| Đặt `ADMIN` thay vì `ROLE_ADMIN` nhưng dùng `hasRole("ADMIN")` | Không khớp authority theo prefix mặc định | Chuẩn hóa mapping/kiểm tra cấu hình prefix |
| Coi `hasRole("ADMIN")` cho phép mọi thao tác với mọi tenant | Vượt phạm vi dữ liệu | Kiểm tra owner, tenant, resource và permission chi tiết |
| Lấy `accountId` của profile từ query param mà không kiểm ownership | IDOR/BOLA | Dùng ID đã xác thực hoặc kiểm tra quyền rõ ràng trên requested ID |
| Nhận vai trò từ JSON request và tạo `Authentication` đã xác thực | Leo thang đặc quyền | Manager chỉ gán quyền từ nguồn đáng tin sau xác minh |
| Dùng `SecurityContextHolder` ThreadLocal như Servlet trong WebFlux | Có thể sai/rỗng khi đổi thread | `ReactiveSecurityContextHolder` trong Reactor pipeline |
| Gọi `block()` trong reactive handler/repository | Chặn event loop, nguy cơ deadlock/performance | Dùng `Mono`/`Flux` và async repository |
| Giữ authorities cũ vô hạn trong session/JWT | Thu hồi role không kịp hiệu lực | Token TTL, refresh, revocation hoặc kiểm permission tại thời điểm truy cập |
| Tạo permission global không namespace | Trùng tên/nhầm quyền giữa modules | Định nghĩa namespace/tên chuẩn, policy review |
| Xem `isAuthenticated()` là toàn bộ điều kiện truy cập | Có thể phân biệt anonymous/role sai | Dùng authorization của Spring Security và method security |
| Dùng `getName()` như khóa bất biến mặc định | Username đổi làm lookup sai | Dùng accountId ổn định nếu nghiệp vụ yêu cầu |
| “Hồ sơ đọc được” đồng nghĩa “cho phép xem mọi hồ sơ” | Vi phạm dữ liệu cá nhân | Kiểm ownership/tenant/object policy |
| Dùng HTTP Basic qua HTTP trên Internet | Credentials bị lộ trên đường truyền | HTTPS, secure transport, cơ chế auth thích hợp |

### 13.1. Vì sao 401 và 403 khác nhau?

Với cấu hình HTTP Basic demo:
- Không có credentials hoặc password sai → **401 Unauthorized**: chưa xác thực hợp lệ.
- Reader có password đúng nhưng thiếu `ROLE_ADMIN` → **403 Forbidden**: đã xác thực, thiếu quyền.
- Reader vào `/api/profile` → **200 OK**: có `profile:read` và service tải profile riêng của reader.
- Không có API nào được phép nhận password/hash chỉ để hiển thị hồ sơ.

Các status có thể chịu ảnh hưởng của exception handling, login mechanism và filter khác; đó là lý do test theo hợp đồng HTTP thật quan trọng.

### 13.2. `@EnableReactiveMethodSecurity` có thay thế HTTP rules không?

Không. Reactive method security như `@PreAuthorize("hasAuthority('reports:read')")` bảo vệ logic ở mức method khi được bật bằng `@EnableReactiveMethodSecurity` và được gọi qua cơ chế Spring phù hợp. Nó **bổ sung** `SecurityWebFilterChain` chứ không thay logic ownership/tenant của domain. Nếu business service xử lý dữ liệu cực kỳ nhạy cảm, nên đặt kiểm tra gần tài nguyên và kiểm thử ở cả HTTP layer lẫn service layer.

## 14. Bài tập vận dụng

1. **`principal` và `GrantedAuthority` khác nhau?** Principal mô tả danh tính; GrantedAuthority mô tả quyền đã cấp cho authentication.
2. **`ProfileView.contactEmail` có cần nằm trong `UserDetails` để đăng nhập không?** Không. Username/password hash và trạng thái account mới liên quan trực tiếp; email liên hệ nên tải khi cần.
3. **`hasRole("ADMIN")` kiểm tra chuỗi nào theo quy ước mặc định?** `ROLE_ADMIN`.
4. **`hasAuthority("reports:read")` có tự thêm `ROLE_` không?** Không, nó kiểm tra đúng tên authority.
5. **Nếu viết `.roles("USER").authorities("profile:read")`, có chắc còn `ROLE_USER` không?** Không. Một builder có thể thay tập authority; phải hợp nhất trước rồi gọi một lần.
6. **Role ADMIN có tự được xem profile của user khác không?** Không nhất thiết; quyền đó phụ thuộc chính sách tenant/ownership/resource riêng.
7. **API `/api/me` nên trả nguyên `Authentication` không?** Không. Dùng response DTO allowlist để tránh lộ credentials, details, profile ngoài ý muốn.
8. **Khi username đổi, nên dùng tên đó làm khóa bất biến của profile không?** Không. Trong hệ thống thực, ưu tiên accountId ổn định.
9. **Khi thu hồi permission, JWT đã phát có tự cập nhật không?** Không. JWT là snapshot đã phát; cần TTL/revocation/refresh hoặc kiểm chính sách động.
10. **Trong WebFlux đọc user từ đâu?** Từ `ReactiveSecurityContextHolder.getContext()` hoặc cơ chế argument resolver phù hợp, không giả định ThreadLocal Servlet.
11. **Vì sao user reader đọc được profile nhưng không đọc được reports?** Vì được cấp `profile:read` nhưng không có `reports:read`.
12. **Khi password sai mà client gửi role ADMIN trong body, backend được tin role đó không?** Không. Role chỉ do hệ thống xác định sau khi xác minh credentials.
13. **Một authentication thành công có bắt buộc mang email và avatar không?** Không; chỉ cần identity và authorities theo nhu cầu authorization.
14. **Với custom principal, có thể tạo token đã authenticated ngay từ request chưa xác minh không?** Không. Phải xác minh rồi mới tạo principal/authorities đã tin cậy.

## 15. Checklist triển khai production

- [ ] Tài khoản/credential, role/permission và profile có ranh giới lưu trữ và API rõ ràng.
- [ ] Password lưu dưới hash mạnh với encoder phù hợp; không có plaintext password trong logs/DTO.
- [ ] Principal tối thiểu; không tự động copy PII vào session/JWT.
- [ ] Authority đến từ nguồn đáng tin, không từ client-controlled role fields.
- [ ] Role prefix chuẩn hóa; phân biệt `hasRole` và `hasAuthority`.
- [ ] Có unit/integration test cho user thường, admin, quyền chi tiết, denied path.
- [ ] Bảo vệ object ownership, tenant và điều kiện tài nguyên bên cạnh quyền chức năng.
- [ ] Đánh giá quyền sống bao lâu trong session/token và cơ chế thu hồi.
- [ ] API/profile DTO có allowlist trường, không serialize object security.
- [ ] Reactive pipeline không gọi `block()` hay tự `subscribe()` cho identity.
- [ ] Resource/profile read và write tuân thủ quyền tối thiểu, chính sách privacy.
- [ ] Sử dụng HTTPS, dependency được hỗ trợ, rate limit/logging/monitoring phù hợp.

## 16. Tài liệu tham khảo chính thức

- Spring Security — Authentication architecture và các thuộc tính principal/credentials/authorities: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — `User.UserBuilder` / `roles` / `authorities`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security — `ReactiveUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — HTTP authorization trong reactive: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive method security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Boot 3.3 — Build/Gradle reference (phiên bản cố định cho demo): https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html

**Ghi nhớ:** **Principal** đại diện danh tính đã được xác minh; **GrantedAuthority** đại diện role/permission phục vụ authorization; **profile** là dữ liệu nghiệp vụ chỉ đọc khi cần và theo quyền sở hữu; **password hash/credentials** không bao giờ được xuất ra response. Giữ ba ranh giới này rõ ràng giúp Spring Security reactive dễ kiểm thử, giảm lộ dữ liệu và hỗ trợ thay đổi role/profile độc lập.
