# Tích hợp OAuth2 Login và ánh xạ người dùng OIDC vào quyền nội bộ trong Spring Security Reactive

## 1. Mục tiêu và bối cảnh

Trong ứng dụng **Spring WebFlux**, đăng nhập bằng OpenID Connect (OIDC) giúp người dùng xác thực với Identity Provider (IdP), còn **phân quyền nội bộ** quyết định họ được làm gì trong ứng dụng. Hai bước này cần được kết nối đúng: đăng nhập thành công không mặc nhiên có quyền quản trị; claim bên ngoài không mặc nhiên là role nội bộ.

Sau bài này, bạn có thể:

- Cấu hình OAuth2 Login/OIDC theo **Authorization Code** trong Spring Boot WebFlux.
- Phân biệt **ID Token**, **Access Token**, **OAuth2 scope**, **OIDC claims**, **GrantedAuthority** và **role nội bộ**.
- Dùng danh tính ổn định **(issuer, subject)** của OIDC để tìm user/membership và role trong hệ thống.
- Ánh xạ quyền **bất đồng bộ** qua `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` và `OidcReactiveOAuth2UserService`.
- Áp dụng `hasRole`, `hasAuthority` cho route và reactive method; tránh nâng quyền qua email, groups hoặc claims không được phê duyệt.
- Kiểm thử mapper bằng JUnit và kiểm thử quyền WebFlux bằng `WebTestClient` + `mockOidcLogin()`, đồng thời biết các phần cần kiểm thử đăng nhập thật.

**Ngữ cảnh:** module Spring Security - reactive, chủ đề **Thực hành tổng hợp**. Ví dụ sử dụng Java 17+, Spring Boot 3.x / Spring Security 6.x, `Mono` và `SecurityWebFilterChain`. `HttpSecurity`, `SecurityFilterChain`, `OidcUserService` đồng bộ và `MockMvc` thuộc **Servlet**; không dùng nhầm cho WebFlux.

## 2. Đăng nhập OIDC khác phân quyền ứng dụng như thế nào?

**OAuth 2.0** là khuôn khổ ủy quyền. **OpenID Connect 1.0** thêm lớp xác thực người dùng, trong đó có ID Token và các quy tắc validation. Spring Security OAuth2 Login dùng Authorization Code flow; scope `openid` kích hoạt xử lý OIDC.

| Khái niệm | Nguồn | Tác dụng | Không nên suy diễn |
| --- | --- | --- | --- |
| `authorization_code` | Redirect callback sau IdP login | Đổi mã một lần để lấy token ở token endpoint | Không phải access token hay session người dùng |
| **ID Token** (JWT) | IdP, dành cho OAuth client | Chứng minh sự kiện xác thực và chứa claims như `iss`, `sub`, `aud`, `exp` | Không phải token mặc định để gọi protected API |
| **Access Token** | IdP/Authorization Server | Ủy quyền gọi API được cấp scope | Có scope chưa chắc có role nội bộ |
| `scope=openid profile email` | OAuth client yêu cầu IdP | Quyền/khả năng nhận thông tin định danh | Không tương đương `ROLE_ADMIN` |
| `sub` | ID Token đã được xác thực | Định danh subject tại issuer tương ứng | Không phải email, không bảo đảm duy nhất toàn Internet |
| `email`, `email_verified` | ID Token/UserInfo tùy provider | Thông tin liên hệ; verified xác nhận chính sách email của IdP | Không chứng minh được cấp vai trò nội bộ |
| `groups`, `roles` claim tùy IdP | Claim do provider cấu hình riêng | Có thể là đầu vào mapping nếu chính sách tin cậy rõ ràng | Không phải OIDC claim role tiêu chuẩn hoặc mặc định tạo `ROLE_*` |
| `GrantedAuthority` | Spring Security | Chuỗi quyền hệ thống dùng để kiểm tra | Không nhất thiết bằng nội dung nguyên văn claims |
| `ROLE_ADMIN` | Chính sách ứng dụng | `hasRole("ADMIN")` kiểm tra authority này | Không tự xuất hiện vì OIDC login thành công |

Trong WebFlux, đăng nhập OIDC thành công thường tạo `OAuth2AuthenticationToken` có principal kiểu `OidcUser`. Authorities mặc định có thể chứa quyền như **OIDC_USER** và **SCOPE_...**; role nội bộ cần cấu hình map rõ. `OAuth2AuthenticationToken.getAuthorities()` được dùng cho quyết định `hasRole/hasAuthority`.

Phải phân biệt **OAuth2 Login** (người dùng tương tác qua trình duyệt, đăng nhập rồi duy trì session) với **OAuth2 Resource Server** (API nhận Bearer token ở mỗi request). Dù cả hai liên quan OAuth2/OIDC, chúng có entry point, principal, token và mô hình authorization khác nhau.

## 3. Luồng OIDC Login trong ứng dụng WebFlux

~~~text
Trình duyệt                  Ứng dụng WebFlux                IdP
    | GET /oauth2/authorization/corp   |                         |
    |--------------------------------->|                         |
    |                                  | sinh OAuth2 request      |
    |                                  | state, redirect URI      |
    | 302 tới authorization endpoint   |                         |
    |<---------------------------------|                         |
    |------------------------------ authorization/login -------->|
    |                                  |                         |
    | callback ?code=...&state=...      |<------------------------|
    |--------------------------------->|                         |
    |                                  | đổi code tại token endpoint
    |                                  | nhận và kiểm tra ID Token|
    |                                  | load OIDC user/UserInfo  |
    |                                  | lấy (iss, sub)           |
    |                                  | tra role nội bộ (reactive)
    |                                  | tạo authorities           |
    | session/cookie + redirect        |                         |
    |<---------------------------------|                         |
    | GET /admin/dashboard             |                         |
    |--------------------------------->| hasRole("ADMIN")        |
    |           200 / 403              |                         |
    |<---------------------------------|                         |
~~~

Cụ thể:

1. User chọn đăng nhập tại **`/oauth2/authorization/{registrationId}`**, ví dụ `/oauth2/authorization/corp`.
2. Spring tạo authorization request và liên kết `state` với phiên trình duyệt để đối chiếu callback; trong cấu hình OIDC thích hợp có các yêu cầu liên quan nonce. Với public client hoặc cấu hình yêu cầu PKCE, bảo đảm triển khai đúng **PKCE** theo loại client.
3. IdP xác thực user, chuyển trình duyệt về **`/login/oauth2/code/{registrationId}`** với code và state. Endpoint này là callback mặc định, phải khớp redirect URI đã đăng ký bên IdP.
4. Spring OAuth2 client trao đổi code, xác thực các thông số/token theo cơ chế provider/OIDC, tạo `OidcUser`. Bảo vệ issuer, audience, signature, thời gian token, state/nonce bằng cơ chế thư viện chính thức; không tự parse ID Token rồi tin nội dung.
5. **Sau khi OIDC identity đã xác thực**, ứng dụng ánh xạ `(iss, sub)` đến tài khoản và quyền nội bộ. Tập authority được gắn vào Authentication khi login hoàn tất.
6. SecurityWebFilterChain và/hoặc reactive method security dùng quyền hiện có để cho qua hoặc từ chối endpoint.

**Với browser login**, request chưa đăng nhập vào tài nguyên protected thường được **redirect 302** tới login page; user đã đăng nhập nhưng thiếu quyền thường nhận **403**. Với Bearer API tách riêng, thiếu token thường là **401**. Không ép kết quả của hai chế độ thành cùng một ma trận mà quên kiểm tra entry point đang cấu hình.

## 4. Thiết kế mô hình danh tính và role trước khi viết code

Hãy có ít nhất hai vùng dữ liệu khác nhau:

- **Danh tính liên kết OIDC:** `issuer`, `subject`, `internal_user_id`, `status`, thông tin hồ sơ đã kiểm soát.
- **Quyền nội bộ:** `internal_user_id`, `tenant_id` nếu đa tenant, `role_code`, `enabled`, phiên bản hoặc thời gian thay đổi.

Ví dụ ý tưởng bảng:

~~~text
app_user
  id              UUID / bigint
  oidc_issuer     VARCHAR (NOT NULL)
  oidc_subject    VARCHAR (NOT NULL)
  status          ACTIVE | DISABLED
  UNIQUE(oidc_issuer, oidc_subject)

app_user_role
  app_user_id
  tenant_id       (nếu hệ thống đa tenant)
  role_code       USER | AUDITOR | ADMIN
  enabled
~~~

**Khóa liên kết nên là `(iss, sub)`**. Tại hai issuer khác nhau, cùng `sub` có thể trỏ đến hai user khác nhau. Email có thể đổi, bị tái cấp hoặc không có; không ghép tự động hai tài khoản chỉ vì email giống nhau. Với một số cấu hình pairwise subject, `sub` có thể khác nhau giữa các OAuth client; khi liên kết nhiều client phải tuân theo chính sách account linking rõ ràng.

**Quyền nguồn tin cậy:** trong bài thực hành, **cơ sở dữ liệu/role service nội bộ** là nơi quyết định ai có `USER`, `AUDITOR`, `ADMIN`. Claim `groups` từ IdP có thể dùng khi doanh nghiệp đã xác định issuer tin cậy, group ID cụ thể, allowlist map và quy trình thu hồi quyền. Không map kiểu `ROLE_` + mọi chuỗi group do bên ngoài trả về; group ngoài IdP và role nội bộ có thể có ý nghĩa rất khác.

Quy tắc tối thiểu:

1. **Deny by default:** OIDC user mới/không có membership không nhận ADMIN hoặc bất kỳ role có quyền nhạy cảm nào.
2. **Explicit allowlist:** chỉ mã role được ứng dụng công nhận mới chuyển thành `ROLE_*`.
3. **Fail closed:** lookup role lỗi không được âm thầm `onErrorReturn(Set.of("ADMIN"))` hoặc cho phép truy cập. Ứng dụng phải quyết định rõ lỗi login hay chỉ quyền rỗng; với permission service unavailable, login failure an toàn hơn tự nâng quyền.
4. **Tenant isolation:** không chỉ kiểm tra `hasRole("ADMIN")` nếu role có phạm vi tenant; phải kiểm tra tenant/resource trong nghiệp vụ.
5. **Lựa chọn thời điểm cập nhật:** mapping khi login tạo một snapshot quyền trong session, chưa chắc phản ánh revoke tức thì ở các request tiếp theo.

## 5. Cấu hình Spring Boot 3.x + WebFlux OAuth2 Login

### 5.1. Phụ thuộc

Một dự án Gradle đã có plugin Spring Boot và dependency management cần các dependency sau (đây là **phần build.gradle**, không phải file độc lập):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

test {
    useJUnitPlatform()
}
~~~

Với role lookup bằng PostgreSQL reactive, triển khai thực tế có thể thêm `spring-boot-starter-data-r2dbc` và driver; ví dụ chính tách role service thành interface để không trộn cấu hình login với cách truy vấn DB.

### 5.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.test/realms/training
~~~

Đây là **cấu hình mẫu**, cần thay `issuer-uri` bằng URL thực được IdP công bố, đồng thời tạo OAuth client và đăng ký đúng redirect URI tại IdP. `OIDC_CLIENT_SECRET` là biến môi trường/secret manager, **không commit** vào Git hoặc ghi lên frontend. Mẫu giả định một **confidential server-side client**; client công khai có chính sách PKCE, client authentication khác.

`issuer-uri` cho phép Spring/Boot khám phá OIDC metadata và endpoint theo khả năng IdP. Cần mạng và cấu hình TLS hợp lệ. Khi chạy sau reverse proxy, bảo đảm `baseUrl`/scheme/host phản ánh **HTTPS URL công khai** từ proxy đáng tin cậy; không cho mọi client tự đặt forwarded headers rồi tạo redirect tùy ý. Redirect callback phải khớp cả scheme, host, path và registrationId.

Ở môi trường development có thể cần tài khoản IdP test, callback URL cục bộ và HTTPS/tunnel theo quy tắc provider. Không dùng IdP thật cho unit test thuần mapping.

## 6. Ví dụ triển khai: OIDC identity → role nội bộ → WebFlux authorization

Ví dụ này gồm lớp khởi động, security config, role service và controller. Các lớp nằm trong package `demo.oidc`. Role service dùng dữ liệu **minh họa cố định** để có thể thấy cơ chế; production phải thay bằng DB/API thực với rule provisioning/revocation.

### 6.1. Điểm khởi động

Tệp `src/main/java/demo/oidc/OidcRoleDemoApplication.java`:

~~~java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcRoleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcRoleDemoApplication.class, args);
    }
}
~~~

### 6.2. Interface tra quyền theo issuer + subject

Tệp `src/main/java/demo/oidc/InternalRoleService.java`:

~~~java
package demo.oidc;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface InternalRoleService {

    // Bắt buộc emit một Set (có thể rỗng), hoặc onError khi lookup lỗi.
    // Không được trả Mono.empty() để "giả thành công".
    Mono<Set<String>> rolesFor(String issuer, String subject);
}
~~~

Tệp `src/main/java/demo/oidc/DemoInternalRoleService.java`:

~~~java
package demo.oidc;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DemoInternalRoleService implements InternalRoleService {

    private record UserKey(String issuer, String subject) {
    }

    // Fixture có chủ đích; KHÔNG dùng làm role storage thật.
    private static final Map<UserKey, Set<String>> ROLES = Map.of(
        new UserKey(
            "https://idp.example.test/realms/training", "alice-sub"),
            Set.of("USER", "ADMIN"),
        new UserKey(
            "https://idp.example.test/realms/training", "bob-sub"),
            Set.of("USER")
    );

    @Override
    public Mono<Set<String>> rolesFor(String issuer, String subject) {
        return Mono.just(ROLES.getOrDefault(
            new UserKey(issuer, subject), Set.of()));
    }
}
~~~

Ví dụ giả định IdP test phát hành ID Token có đúng `sub` đã gắn trong fixture. Với IdP thật, subject thường không thể tùy chọn theo ý người viết; hãy **đồng bộ bản ghi liên kết user** từ IdP đã xác thực và gán role qua quy trình quản trị, không dựa vào email hoặc đoán sub. Tài khoản chưa được cấp quyền nhận tập role rỗng.

### 6.3. SecurityWebFilterChain và OIDC reactive user service

Tệp `src/main/java/demo/oidc/OidcSecurityConfig.java`:

~~~java
package demo.oidc;

import java.util.Collection;
import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo
        .OidcReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo
        .ReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo
        .OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user
        .DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user
        .OidcUser;
import org.springframework.security.oauth2.core.oidc.user
        .OidcUserAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class OidcSecurityConfig {

    private static final Set<String> KNOWN_ROLES =
            Set.of("USER", "AUDITOR", "ADMIN");

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .pathMatchers("/reports/**").hasAnyRole("USER", "ADMIN")
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveOAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            InternalRoleService roleService) {

        OidcReactiveOAuth2UserService delegate =
                new OidcReactiveOAuth2UserService();

        return request -> delegate.loadUser(request)
            .flatMap(user -> {
                // Chỉ sử dụng sau khi OIDC token đã được validate.
                String issuer = user.getIdToken().getIssuer().toString();
                String subject = user.getIdToken().getSubject();

                return roleService.rolesFor(issuer, subject)
                    .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                            "Role service returned empty publisher")))
                    .map(roles -> (OidcUser) new DefaultOidcUser(
                        mapAuthorities(user.getAuthorities(), roles),
                        user.getIdToken(),
                        user.getUserInfo()));
            });
    }

    // Package-private để có thể unit-test logic ánh xạ.
    static Set<GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> providerAuthorities,
            Set<String> internalRoles) {

        Set<GrantedAuthority> result = new HashSet<>();

        // Giữ identity OIDC và OAuth scopes; bỏ mọi ROLE_* bên ngoài.
        // ROLE nội bộ chỉ được lấy từ role service tin cậy.
        for (GrantedAuthority authority : providerAuthorities) {
            String name = authority.getAuthority();
            if (authority instanceof OidcUserAuthority
                    || (name != null && name.startsWith("SCOPE_"))) {
                result.add(authority);
            }
        }

        for (String role : internalRoles) {
            if (KNOWN_ROLES.contains(role)) {
                result.add(new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return Set.copyOf(result);
    }
}
~~~

**Cách hoạt động từng đoạn:**

1. `.oauth2Login(Customizer.withDefaults())` bật flow đăng nhập browser/OIDC cho WebFlux. Bean `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` là điểm mở rộng để thay đổi user sau khi OIDC login; cách đăng ký bean này được tài liệu Spring Security Reactive hỗ trợ.
2. `delegate.loadUser(request)` xử lý OIDC user mặc định rồi mới `.flatMap(...)` tra role. Đây là **reactive** lookup; không `.block()` trong request/login flow.
3. `user.getIdToken().getIssuer()` và `.getSubject()` xác định liên kết. Không dùng email làm khóa tài khoản.
4. `roleService.rolesFor(...)` phải trả Mono phát ra **một Set**, hoặc onError. Lỗi lookup được giữ là lỗi đăng nhập, không fallback cấp quyền. `switchIfEmpty` chặn implementation trả `Mono.empty()`.
5. `mapAuthorities(...)` chỉ giữ OIDC identity authority và `SCOPE_...` từ nguồn provider, **loại bỏ ROLE_... đến từ provider**. Chỉ ba role nội bộ trong allowlist mới sinh ra `ROLE_USER`, `ROLE_AUDITOR`, `ROLE_ADMIN`.
6. `new DefaultOidcUser(...)` tạo principal mới vẫn mang ID Token và UserInfo gốc đã được load, nhưng có authorities phù hợp ứng dụng. Spring dùng các authorities này trong Authentication sau login.
7. `.hasRole("ADMIN")` kiểm tra **ROLE_ADMIN**, còn `.hasAuthority("SCOPE_reports.read")` kiểm tra đúng chuỗi SCOPE_reports.read; `hasRole("ROLE_ADMIN")` là sai cách dùng thông thường vì prefix đã được áp dụng.

Nếu provider yêu cầu name attribute khác `sub`, Spring có constructor `DefaultOidcUser(authorities, idToken, userInfo, userNameAttributeName)`; chỉ chọn thuộc tính đã được IdP xác thực và có mặt trong claims. Ví dụ này giữ mặc định là `sub`, tương thích khóa liên kết.

**Ranh giới bảo mật:** đoạn mapping không cấp role dựa trên raw claim `"roles"` hoặc `"groups"`. Nếu doanh nghiệp muốn IdP groups trực tiếp cấp role, chỉ ánh xạ **group ID đã được cho phép** từ issuer tin cậy và có cơ chế kiểm thử/revoke. Người dùng không được tự ghi dữ liệu `groups` qua request header/body để quyết định quyền.

### 6.4. Controller nhận principal sau khi login

Tệp `src/main/java/demo/oidc/DemoController.java`:

~~~java
package demo.oidc;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Login: /oauth2/authorization/corp");
    }

    @GetMapping("/me")
    public Mono<String> me(@AuthenticationPrincipal OidcUser user) {
        // Chỉ tiết lộ sub của chính user đang đăng nhập.
        return Mono.just("subject=" + user.getIdToken().getSubject());
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @GetMapping("/admin/dashboard")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
~~~

`@AuthenticationPrincipal OidcUser` là kiểu đúng cho OIDC Login. Một đường HTTP Resource Server kiểm tra JWT Bearer token có thể tạo `JwtAuthenticationToken`, không nhất thiết có `OidcUser`; đừng ép cùng controller giả định hai kiểu principal nếu chưa thiết kế cơ chế thống nhất.

Với client IdP thực, đăng ký callback hợp lệ và `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` đã cấp, chạy:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Đi tới `/`, sau đó `/oauth2/authorization/corp` để bắt đầu login. Nếu IdP trả identity có `issuer`/`subject` khớp Alice trong fixture: `/me` trả `subject=alice-sub`; `/reports` trả `reports-ok`; `/admin/dashboard` trả `admin-ok`. Nếu khớp Bob: `/reports` thành công nhưng `/admin/dashboard` trả HTTP 403. Nếu role service không tìm thấy user, không có ROLE_USER/ROLE_ADMIN, nên các endpoint cần role bị 403. Đây là **kết quả theo điều kiện của fixture và cấu hình IdP**, không phải stdout của Java hay lời hứa rằng URL provider minh họa đang hoạt động.

## 7. Tra role thực bằng kho dữ liệu reactive

Trong production, thay DemoInternalRoleService bằng service repository/API thực. Nếu dùng Spring Data R2DBC, mẫu truy vấn (chỉ là **mảnh triển khai**, cần schema và dependency thực):

~~~java
public Mono<Set<String>> rolesFor(String issuer, String subject) {
    return databaseClient.sql("""
            SELECT r.role_code
            FROM app_user u
            JOIN app_user_role r ON r.app_user_id = u.id
            WHERE u.oidc_issuer = :issuer
              AND u.oidc_subject = :subject
              AND u.status = 'ACTIVE'
              AND r.enabled = TRUE
            """)
        .bind("issuer", issuer)
        .bind("subject", subject)
        .map((row, meta) -> row.get("role_code", String.class))
        .all()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
}
~~~

`databaseClient` là `org.springframework.r2dbc.core.DatabaseClient` đã được inject; còn cần `spring-boot-starter-data-r2dbc`, driver DB, bảng/constraint và migrations phù hợp. Tham số SQL được **bind**, không nối chuỗi đầu vào để tạo SQL. `collect(...)` với 0 bản ghi emit `Set.of()` rỗng; lỗi kết nối sẽ là `onError`, không bị biến thành quyền cho phép.

Nếu hệ thống đa tenant, ví dụ trên **chưa đủ** để cấp `ROLE_ADMIN` theo tenant: thêm tenant vào khóa lookup, tham số và chính sách; validate tenant do request chỉ định bằng membership thực của user. Khi role là tenant-scoped, cân nhắc authority dạng `PERM_REPORT_APPROVE` kết hợp check tenant/resource, hoặc dùng `ReactiveAuthorizationManager` với quyết định kiểm tra trực tiếp. Không sao chép role ADMIN của tenant A thành quyền admin toàn ứng dụng.

### Cấp tài khoản lần đầu

Quyết định rõ chiến lược:

- **Pre-provisioning**: chỉ user đã được gán role nội bộ mới có quyền; OIDC login mới có thể tạo profile rỗng nhưng không cho truy cập nghiệp vụ.
- **Just-in-time provisioning**: sau khi xác thực `(iss,sub)`, tạo tài khoản nội bộ với quyền tối thiểu được phê duyệt. Dùng unique constraint và xử lý đăng nhập đồng thời để tránh tạo user trùng.
- **Invite/linking flow**: chỉ link người dùng sau lời mời hay xác nhận ngoài băng. Không tự link bằng `email` vì trùng email hoặc `email_verified=true` không đồng nghĩa cùng quyền hiện tại.

Nếu account bị disabled, role service phải từ chối login hoặc trả không role theo chính sách; hạn chế lộ sự tồn tại của account qua thông điệp lỗi bên ngoài.

## 8. Vai trò của GrantedAuthoritiesMapper và cách chọn điểm mở rộng

Spring Security Reactive cung cấp hai cách phổ biến:

| Chiến lược | Loại API | Khi dùng | Giới hạn |
| --- | --- | --- | --- |
| `GrantedAuthoritiesMapper` bean | Synchronous mapping từ `Collection<GrantedAuthority>` | Role được suy ra từ claims đã có, allowlist đơn giản, không cần I/O | Không phù hợp gọi DB/HTTP reactive từ chính mapper |
| `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` bean | Reactive Mono, có request và token/user | Cần tra membership/role từ DB/HTTP và dựng OidcUser mới | Phải giữ lỗi và semantics logout/session đúng |
| Resource Server converter | JWT/Opaque token → Authentication | API Bearer token, không phải browser OIDC Login | Không thay thế login OIDC session |

Ví dụ **mảnh mã** cho mapper dựa trên một IdP group đã duyệt:

~~~java
@Bean
GrantedAuthoritiesMapper userAuthoritiesMapper() {
    return input -> {
        Set<GrantedAuthority> result = new HashSet<>();
        for (GrantedAuthority authority : input) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object groups = oidc.getIdToken()
                    .getClaims().get("groups");

                if (groups instanceof java.util.Collection<?> values
                        && values.contains("corp-report-admins")) {
                    result.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                }
            }
        }
        return result;
    };
}
~~~

Đây là **phương án thay thế** cho role mapping DB ở ví dụ chính, không nên copy đồng thời mà không xác định quyền ưu tiên. `groups` là **claim tùy IdP**, chỉ dùng nếu issuer/client đã được tin cậy và cấu hình phát hành claim đó đã được quản lý. Trong mapper thật nên giữ authority cần thiết (`OIDC_USER`, SCOPE_...) nếu policy dùng tới; snippet cố ý chỉ nhấn mạnh allowlist group ID. Không dùng `map(group -> "ROLE_" + group)` vô điều kiện.

Nếu cần mapping từ claims nằm ở UserInfo, lưu ý ID Token và UserInfo không nhất thiết có cùng claims. Spring `OidcUserAuthority` cung cấp ID Token và UserInfo, còn `OidcUser` cũng có các getter tương ứng. Khi có khả năng UserInfo khác subject, áp dụng đối chiếu subject/issuer và trust contract của OIDC provider; không nối thông tin của hai subject khác nhau.

## 9. Kiểm thử đơn vị logic mapper bằng JUnit 5

Tệp `src/test/java/demo/oidc/OidcRoleMappingTest.java`:

~~~java
package demo.oidc;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcRoleMappingTest {

    @Test
    void discardsExternalRoleAndUsesOnlyApprovedLocalRole() {
        List<GrantedAuthority> external = List.of(
            new SimpleGrantedAuthority("ROLE_ADMIN"),
            new SimpleGrantedAuthority("SCOPE_openid"),
            new SimpleGrantedAuthority("EXTERNAL_POWER"));

        Set<GrantedAuthority> mapped =
            OidcSecurityConfig.mapAuthorities(external,
                Set.of("USER", "SUPER_ADMIN"));

        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("ROLE_USER")));
        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("SCOPE_openid")));

        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("ROLE_ADMIN")));
        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("ROLE_SUPER_ADMIN")));
        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("EXTERNAL_POWER")));
    }

    @Test
    void missingInternalMembershipGivesNoInternalRole() {
        Set<GrantedAuthority> mapped =
            OidcSecurityConfig.mapAuthorities(
                List.of(new SimpleGrantedAuthority("SCOPE_profile")),
                Set.of());

        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("SCOPE_profile")));
        assertFalse(mapped.stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(name -> name.startsWith("ROLE_")));
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.oidc.OidcRoleMappingTest
~~~

Hai test xác nhận **quyền bên ngoài không tự biến thành role nội bộ** và user không có membership không nhận role. Không cần IdP hay network cho test mapping thuần này. Code không in stdout định trước; JUnit báo PASS/FAIL.

## 10. Kiểm thử luật authorization WebFlux với mockOidcLogin()

`SecurityMockServerConfigurers.mockOidcLogin()` mô phỏng một OIDC principal/Authentication khi request được xử lý. Nó rất hữu ích để test `hasRole`, `@AuthenticationPrincipal` và controller, nhưng **không đi qua authorization-code redirect, token exchange, ID Token signature validation hay user service ánh xạ role thật**.

Tệp `src/test/java/demo/oidc/OidcAuthorizationTest.java` minh họa kiểm tra luật trên WebFlux context độc lập với IdP:

~~~java
package demo.oidc;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.EnableWebFlux;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OidcAuthorizationTest.TestConfig.class)
class OidcAuthorizationTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void oidcPrincipalWithoutInternalAdminRoleIsForbidden() {
        client.mutateWith(mockOidcLogin()
                .authorities(new SimpleGrantedAuthority("SCOPE_read")))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void untrustedRolesClaimIsNotEnoughForAuthorization() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token.claim(
                    "roles", java.util.List.of("ADMIN"))))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void explicitInternalAdminAuthorityIsAcceptedByRule() {
        client.mutateWith(mockOidcLogin()
                .authorities(new SimpleGrantedAuthority("ROLE_ADMIN")))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void principalSubjectComesFromOidcIdToken() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token.claim("sub", "alice-sub")))
            .get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice-sub");
    }

    @Configuration
    @EnableWebFlux
    @EnableWebFluxSecurity
    static class TestConfig {

        @Bean
        SecurityWebFilterChain rules(ServerHttpSecurity http) {
            return http.authorizeExchange(ex -> ex
                    .pathMatchers("/admin/dashboard").hasRole("ADMIN")
                    .pathMatchers("/me").authenticated()
                    .anyExchange().denyAll())
                .build();
        }

        @Bean
        TestEndpoints testEndpoints() {
            return new TestEndpoints();
        }
    }

    @RestController
    static class TestEndpoints {

        @GetMapping("/admin/dashboard")
        public Mono<String> admin() {
            return Mono.just("admin-ok");
        }

        @GetMapping("/me")
        public Mono<String> me(@AuthenticationPrincipal OidcUser user) {
            return Mono.just(user.getIdToken().getSubject());
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.oidc.OidcAuthorizationTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests demo.oidc.OidcAuthorizationTest
~~~

**Kết quả dự kiến:** 4 test PASS nếu dependencies và WebFlux test context đúng như ví dụ. Những test này kiểm tra rằng claim `"roles": ["ADMIN"]` chưa được mapper xử lý **không tự trở thành ROLE_ADMIN**, còn authority `ROLE_ADMIN` được cấp trực tiếp trong mock cho phép đi qua luật. Test thứ tư kiểm tra `OidcUser` trong controller nhận `sub` đã cung cấp.

Đây là test **authorization rule**, không kiểm tra `OidcReactiveOAuth2UserService` của phần 6 được gọi. Muốn test mapping thật, cần test riêng service với dependency giả hoặc integration test có OIDC provider mô phỏng.

## 11. Kiểm thử end-to-end: những gì mock không thể chứng minh

### Các tầng test cần phân biệt

| Tầng | Công cụ | Kiểm tra |
| --- | --- | --- |
| Mapping thuần | JUnit, gọi hàm mapAuthorities | Role ngoài bị bỏ, role nội bộ đúng whitelist |
| Quyền WebFlux | WebTestClient + mockOidcLogin | 200/403 theo authorities, principal được truyền vào handler |
| Reactive user service | Fake/mock role service, OAuth2 user service delegate test double | `(iss,sub)` lookup đúng, error được giữ, new DefaultOidcUser giữ token/UserInfo |
| OAuth2/OIDC login flow | IdP test (ví dụ môi trường Keycloak test / mock server theo protocol) | state/nonce, redirect, token exchange, ID Token validation, UserInfo, session cookie |
| Production security behavior | Môi trường staging có IdP thật và DB quyền kiểm thử | Logout, cập nhật role, tenant isolation, proxy HTTPS, observability |

Các ca quan trọng:

1. **Login thành công, user nội bộ có USER:** `/reports` được phép; `/admin/dashboard` bị 403.
2. **Login thành công, user nội bộ có ADMIN:** `/admin/dashboard` được phép.
3. **Login thành công nhưng chưa được cấp quyền:** trang cá nhân có thể hiển thị (nếu policy cho phép), nhưng trang dữ liệu nhạy cảm bị 403.
4. **IdP group claim cố ý đặt ADMIN:** không vượt qua nếu internal role service không cấp ROLE_ADMIN.
5. **Role lookup DB/HTTP timeout:** login thất bại theo chính sách, không tự cấp USER/ADMIN; log chỉ metadata an toàn.
6. **Sai issuer hoặc subject:** không map sang tài khoản của issuer khác hoặc email tương tự.
7. **Account disabled hoặc membership thu hồi:** áp dụng chính sách revoke, session invalidation/revalidation.
8. **Hai tenant:** ADMIN của tenant A không có quyền quản trị tenant B.
9. **State mismatch/redirect giả, token sai chữ ký/audience/expiry:** bị từ chối theo OIDC validation, không bypass bằng mock.
10. **Nhiều login đồng thời lần đầu:** không tạo trùng liên kết user/role, không phát sinh role mặc định sai.

Nếu ứng dụng có `@PreAuthorize("hasRole('ADMIN')")`, cần `@EnableReactiveMethodSecurity`, gọi method qua bean/proxy và trả về Mono/Flux để context được truyền đúng. Test thêm cả route-level và method-level; filter cho phép chưa chắc resource-level permission đã được kiểm tra.

### Cách gắn role service vào test

Với test dịch vụ, bạn có thể giả role lookup trả `Mono.just(Set.of("USER"))` cho `(iss,sub)` đã biết và `Mono.error(new RuntimeException(...))` cho lỗi hạ tầng. Hãy kiểm tra service **không** dùng `.onErrorReturn(...)` để nâng quyền. Với OIDC delegate cần test double hoặc IdP test theo flow, vì mặc định `OidcReactiveOAuth2UserService` có thể gọi UserInfo HTTP.

Chú ý không dùng `mockOidcLogin().authorities(ROLE_ADMIN)` để kết luận hệ thống đã map role từ DB: test này chỉ cấp sẵn quyền, bỏ qua bản thân mapper.

## 12. Phiên đăng nhập, thay đổi role và thu hồi quyền

Một điểm quan trọng: mapping tại **thời điểm login** tạo authorities cho Authentication. Trong ứng dụng sử dụng **web session**, quyền đó có thể tồn tại cho đến khi session được cập nhật, hủy hoặc user đăng nhập lại.

~~~text
t0  Alice login: DB roles = USER, ADMIN → session có ROLE_ADMIN
t1  Quản trị viên thu hồi ADMIN trong DB
t2  Alice dùng session cũ: Authentication có thể vẫn còn ROLE_ADMIN
t3  Chỉ sau cơ chế session invalidation/recheck thì quyền mới bị hạ
~~~

Để đáp ứng yêu cầu thu hồi nhanh:

- Xác định SLA **role freshness** và thời hạn session; cân nhắc hủy session sau thay đổi quyền hoặc cơ chế push invalidation.
- Đối với thao tác nhạy cảm, đánh giá quyền tại **thời điểm thao tác** bằng DB/policy service authoritative, không chỉ dựa vào `hasRole` snapshot ở login.
- Gắn version quyền vào user/session và so sánh với DB/cache có TTL ngắn theo chính sách, tránh thêm lookup tốn kém cho mọi request khi không cần.
- Phân biệt **local logout** (xóa session ở ứng dụng) với **OIDC RP-initiated logout** ở IdP và revoke OAuth authorized client/token. Logout local không tự đảm bảo mọi IdP SSO session bị đóng.
- Khi scale nhiều instance, lưu session an toàn (theo kiến trúc) và đồng bộ invalidation; không dựa vào cache cục bộ của một node nếu yêu cầu revoke toàn cụm.

Không nhầm role nội bộ với `scope` của OAuth access token: role mới trong DB chưa làm ID Token cũ biến đổi, còn login mới chưa chắc hủy session tại các ứng dụng khác.

## 13. Bảo vệ login flow và thông tin nhận dạng

- Dùng HTTPS, redirect URIs được đăng ký chính xác và cấu hình reverse proxy đáng tin cậy.
- Để Spring Security xử lý **state, nonce, ID Token signature, issuer, audience, token lifetime**. Không bypass validator hoặc chấp nhận `alg=none` trong production.
- Không hiển thị/ghi log raw authorization code, ID Token, access token, refresh token, client secret, session cookie hay claims nhạy cảm.
- Duy trì **CSRF protection** cho giao dịch browser dựa trên session/cookie, đặc biệt các phương thức thay đổi trạng thái. Không tắt CSRF chỉ để OAuth login "chạy được".
- Tách endpoint web login (cookie session) khỏi Bearer API khi cả hai chế độ tồn tại; phân vùng bằng `SecurityWebFilterChain` và matcher rõ ràng nếu cần.
- Nếu tải user mapping qua `WebClient`, chỉ gửi access token đến endpoint **đã tin cậy** cần token đó; không gửi ID Token tùy tiện đến API hoặc URL do request người dùng cung cấp.
- Hạn chế quyền OAuth client đăng ký với IdP; giữ client secret trong secret manager; tránh sử dụng access token có scope quá rộng.
- Không nhận vai trò từ tham số `?role=ADMIN`, header client tùy ý hoặc từ `email` trực tiếp.
- Thông tin hồ sơ như email/displayName là **dữ liệu cần bảo vệ**, không phải khóa authorization. `email_verified` chỉ nói về việc xác minh email theo chính sách provider, không đảm bảo membership hay role nội bộ.
- Với multi-tenant, kiểm tra `tenant_id` từ membership/ACL authoritative chứ không chỉ dựa vào request path hay claim tự khai báo.

## 14. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `/oauth2/authorization/corp` lỗi | Chưa có registration hoặc cấu hình issuer/client sai | Kiểm tra provider metadata, client registration và secret |
| Callback báo redirect mismatch | URI sau proxy khác URI đã đăng ký | Cấu hình HTTPS public base URL, forwarded headers đáng tin cậy |
| Đăng nhập được nhưng `/admin` luôn 403 | `OIDC_USER`/`SCOPE_...` không tương đương `ROLE_ADMIN` | Kiểm tra role service và authority `ROLE_ADMIN` |
| Có claim `"roles":["ADMIN"]` mà vẫn 403 | Spring không tự map claim tùy chỉnh thành role nội bộ | Viết allowlist mapping hoặc role lookup nội bộ |
| User từ issuer B nhận quyền của issuer A | Chỉ lookup bằng `sub` hoặc email | Khóa theo `(iss, sub)` và xác minh provider |
| Một người bị revoke nhưng vẫn vào được | Authentication lưu role snapshot trong session cũ | Invalidate/revalidate theo yêu cầu freshness |
| DB phân quyền downtime gây login lỗi | Mapping service fail closed | Quan sát lỗi, circuit breaker/retry có giới hạn nếu đọc an toàn; không fallback ALLOW |
| Role mapper luôn "chạy" nhưng quyền không khớp | Trộn `GrantedAuthoritiesMapper` và `ReactiveOAuth2UserService` với policy khác | Chọn một nguồn authority rõ ràng, kiểm tra Authentication sau login |
| `block()` khiến WebFlux chậm hoặc treo | Gọi lookup blocking trên event loop | Dùng R2DBC/WebClient reactive hoặc offload blocking đúng cách |
| Test mockOidcLogin pass nhưng login thật fail | Test bypass redirect/token validation/user service | Thêm integration test IdP thực hoặc protocol test server |
| Dùng `HttpSecurity`/`MockMvc` trong WebFlux | Lẫn Servlet stack | Chuyển sang `ServerHttpSecurity` và `WebTestClient` |

Không dùng `hasRole("ROLE_ADMIN")` trong cấu hình mặc định; `hasRole("ADMIN")` đã kiểm tra tiền tố ROLE_. Nếu custom authority không có tiền tố, dùng `hasAuthority("EXACT_CODE")` thay vì đoán.

## 15. Tự kiểm tra kiến thức

1. **OIDC login thành công có cấp quyền ADMIN tự động không?** Không. Login xác thực danh tính; role nội bộ phải được cấp bởi chính sách phù hợp.
2. **Vì sao nên dùng `(iss, sub)` thay cho email?** Subject chỉ có nghĩa trong phạm vi issuer; email không ổn định, có thể thay đổi/tái cấp và không đại diện membership.
3. **`hasRole("ADMIN")` so khớp gì?** `ROLE_ADMIN` trong GrantedAuthorities mặc định.
4. **Khi nào dùng `GrantedAuthoritiesMapper` và khi nào dùng `ReactiveOAuth2UserService`?** Mapper cho logic đồng bộ từ claims/authorities; service khi cần userRequest, UserInfo và I/O reactive tra role.
5. **Nếu DB roles không tìm thấy user mới, có nên mặc định ADMIN để tránh bị chặn không?** Tuyệt đối không. Quyền rỗng hoặc chặn login theo chính sách.
6. **`mockOidcLogin().authorities(ROLE_ADMIN)` có test truy vấn DB nội bộ không?** Không; nó cấp sẵn authority và bỏ qua user service thật.
7. **Quyền ADMIN bị revoke trong DB có tự biến mất khỏi session đang hoạt động ngay không?** Không đảm bảo; cần cơ chế invalidation/revalidation.
8. **Có thể dùng ID Token làm access token để gọi API bất kỳ không?** Không. ID Token phục vụ xác thực OAuth client và có audience/semantics riêng; API phải kiểm tra access token phù hợp.
9. **Vì sao claim `groups` không nên map tự do thành `ROLE_*`?** Tên và trust contract là IdP-specific; chỉ group được phê duyệt mới nên tương ứng quyền nội bộ.
10. **Tại sao một web endpoint chưa đăng nhập có thể trả 302 thay vì 401?** OAuth2 browser login dùng authentication entry point redirect; Bearer API có entry point khác.

## 16. Tài liệu chính thức

- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced Configuration (authority mapping và OIDC user service): https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — Reactive OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Security — Reactive OAuth2 Testing (`mockOidcLogin`): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

Cơ chế chính cần nhớ: **IdP xác thực danh tính → application liên kết bằng issuer + subject → role service cấp quyền nội bộ → Spring Security áp dụng authorities**. Thử nghiệm authorization bằng mock và thử nghiệm OIDC flow bằng IdP là hai tầng kiểm thử bổ sung cho nhau.