# Cấu hình oauth2Login với nhà cung cấp danh tính bên ngoài trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm:** Đăng nhập OAuth2/OIDC  
> **Đầu ra:** Hiểu luồng đăng nhập OpenID Connect (OIDC) qua một Identity Provider (IdP) bên ngoài, cấu hình `oauth2Login` trong WebFlux, bảo vệ callback và WebSession, kiểm tra hành vi bằng WebTestClient, và biết khi nào cần OAuth2 Resource Server thay vì OAuth2 Login.

## 1. Bài toán và kết quả mong đợi

Ứng dụng WebFlux chạy tại `http://localhost:8080` cần cho người dùng “Đăng nhập bằng Google” hoặc một IdP khác như Keycloak, Okta, Microsoft Entra ID. User nhập password tại **IdP**, không đưa password IdP cho application. Sau khi IdP xác thực, application có một phiên đăng nhập nội bộ và cho phép xem endpoint riêng tư.

Một vòng đăng nhập cần có:

1. Browser mở `GET /api/me` khi chưa đăng nhập → bị chuyển tới login flow.
2. Người dùng chọn IdP tại `/login` hoặc mở `/oauth2/authorization/google`.
3. Spring Security tạo OAuth2 Authorization Request có `client_id`, `scope`, `redirect_uri`, `state` và các tham số bảo vệ cần thiết.
4. Browser được redirect đến Authorization Server; IdP đăng nhập/consent.
5. Browser trở về callback `/login/oauth2/code/google` với authorization code và state.
6. Server xác thực request tương quan, trao authorization code lấy tokens, kiểm chứng OIDC ID Token và nhận principal.
7. Spring Security ghi trạng thái đăng nhập vào session của application.
8. Request sau mang session cookie và nhận user subject, không phải gửi lại password IdP.

**OAuth2 và OIDC không giống nhau.** OAuth 2.0 là framework ủy quyền; OpenID Connect bổ sung **xác thực end-user**, ID Token và các quy tắc kiểm chứng. Muốn “đăng nhập” với external provider nên chọn hỗ trợ OIDC và yêu cầu scope `openid`. Một OAuth2 access token ngẫu nhiên không tự có nghĩa là “chứng minh người dùng đã đăng nhập”.

## 2. Các vai trò liên quan

| Vai trò | Chủ thể trong bài | Trách nhiệm |
| --- | --- | --- |
| End-user / Resource owner | Người dùng browser | Chọn nhà cung cấp và xác thực |
| OAuth2 Client / OIDC Relying Party | Spring WebFlux application | Tạo authorization request, xử lý callback, trao code, lưu phiên |
| Authorization Server / OpenID Provider | Google hoặc IdP doanh nghiệp | Xác minh danh tính, phát code/ID Token/access token |
| Resource Server | API nhận Bearer token | Kiểm tra issuer/audience/signature/scope của access token |
| Browser | User agent | Theo redirects, mang cookie local |

`oauth2Login()` thuộc **OAuth2 Client**, dùng cho browser login vào application. `oauth2ResourceServer().jwt()` thuộc **Resource Server**, dùng khi mỗi API request gửi Bearer JWT. Hai cơ chế có thể tồn tại trong một hệ thống nhiều security chains, nhưng cấu hình và threat model khác nhau.

Ở mô hình bài lab, browser đăng nhập qua IdP, sau đó gửi cookie **của application** đến `/api/me`. Nó không tự gửi ID Token hoặc Bearer access token mỗi request. Không biến local session thành stateless bằng cách gắn `oauth2Login()`.

## 3. Thuật ngữ cấu hình phải nắm

| Tên | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `registrationId` | `google` | ID một `ClientRegistration` |
| `client-id` | ID ở IdP console | Định danh ứng dụng client |
| `client-secret` | Secret ở IdP console | Bí mật của confidential client; chỉ giữ server-side |
| `authorization-uri` | URL tại IdP | Browser đến đăng nhập và consent |
| `token-uri` | URL tại IdP | Backend trao authorization code |
| `issuer-uri` | Issuer chính xác của IdP | Discovery/trust boundary và validation |
| `jwk-set-uri` | Endpoint IdP | Public keys xác minh chữ ký token |
| `redirect-uri` | `{baseUrl}/login/oauth2/code/{registrationId}` | Callback đã đăng ký tại IdP |
| `scope` | `openid,profile,email` | Những quyền/claims được yêu cầu |
| `state` | Giá trị random mỗi login | Gắn callback với authorization request ban đầu |
| `nonce` | Random OIDC | Ràng buộc ID Token và authentication request |
| `PKCE` | Code verifier/challenge | Hạn chế đánh cắp/replay authorization code |
| `ID Token` | Signed JWT theo OIDC | Xác thực end-user **đối với client** |
| `Access Token` | Opaque/JWT tùy provider | Gọi protected API, không thay ID Token |
| `Refresh Token` | Có thể có | Xin access token mới theo chính sách IdP |

Không lưu hoặc trả client secret, authorization code, ID Token, access token, refresh token ra endpoint công khai hoặc vào log. Không sử dụng ID Token làm Bearer token tới một API chỉ định cho access token.

## 4. Authorization Code + OIDC: toàn bộ luồng

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Spring WebFlux Client
    participant P as External OIDC Provider
    B->>A: GET /api/me
    A-->>B: 302 /login
    B->>A: GET /oauth2/authorization/google
    A->>A: Generate request, state, nonce/PKCE nếu cấu hình
    A-->>B: 302 tới IdP authorization endpoint
    B->>P: GET /authorize?client_id&redirect_uri&scope&state...
    P->>B: Login + consent
    B->>P: Xác thực tại nhà cung cấp
    P-->>B: 302 callback?code=...&state=...
    B->>A: GET /login/oauth2/code/google
    A->>A: Verify state + registration
    A->>P: Backend token request (code + client auth + PKCE nếu dùng)
    P-->>A: Tokens, gồm id_token đối với OIDC
    A->>A: Verify ID Token, load OIDC principal
    A->>A: Save SecurityContext / WebSession
    A-->>B: Redirect sau login + session cookie
    B->>A: GET /api/me + session cookie
    A-->>B: 200 JSON subject
~~~

Điểm khác biệt quan trọng:

- Authorization code là credential **ngắn hạn và một lần dùng**, ràng buộc với client, redirect URI và các bảo vệ yêu cầu.
- `state` chống trộn callback của các login attempts (login CSRF/mix-up); `nonce` liên kết ID Token với OIDC authentication request; PKCE dùng `code_challenge` và `code_verifier` chống đánh cắp code. Không dùng thay thế qua lại.
- Backend, không phải JavaScript frontend, giữ client secret của confidential web client và thực hiện token exchange.
- Khi có `openid`, ID Token phải được kiểm chứng chữ ký, issuer, audience, expiry và các OIDC checks phù hợp. Không tự nhận callback `code` rồi tin query parameter là đã có user.
- Sau login, server-side OAuth2 client có thể lưu Authentication trong WebSession. Browser chỉ cần cookie local cho request tiếp theo; local cookie không phải JWT.

## 5. Chuẩn bị client tại nhà cung cấp

Tại console của Google/IdP:

1. Tạo OAuth2/OIDC client thuộc loại **Web application/confidential client** nếu backend có thể giữ secret.
2. Lấy `client-id` và `client-secret`. Secret phải ở server environment/secret manager, không commit Git, không gửi frontend.
3. Đăng ký authorized redirect URI chính xác. Với registration `google` ở local: `http://localhost:8080/login/oauth2/code/google`.
4. Cấu hình Authorization Code grant, scope `openid` và chỉ thêm `profile`/`email` nếu cần.
5. Nếu provider có consent screen, test users, tenant restrictions hoặc logout allowlist, hoàn tất chúng theo provider documentation.
6. Lấy issuer/metadata/JWKS chính xác; với Google Spring Boot có provider defaults nên lab không cần khai báo các endpoints thủ công.
7. Chuẩn bị **HTTPS public URL** và redirect cho production; local HTTP chỉ dùng localhost.
8. Phân biệt redirect URI của backend với CORS allowed origin của một SPA. Hai cấu hình không thay thế nhau.

Nếu app chạy sau reverse proxy, IdP phải biết **URL public mà browser nhìn thấy**, không phải URL pod/internal service. Không dùng wildcard callback hoặc open redirect để “sửa nhanh” mismatch.

## 6. Project Java 17+ / Maven

Dùng Spring Boot `3.3.13` cho lab Spring Security 6.x. Nhánh 3.3 đã kết thúc hỗ trợ OSS, dự án production mới phải chọn phiên bản còn được hỗ trợ và kiểm tra API cụ thể. Cấu trúc:

~~~text
reactive-external-oidc-login/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/oidc/
    │   │   ├── OidcApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/example/oidc/
        └── OidcLoginTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-external-oidc-login</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

`spring-boot-starter-oauth2-client` là dependency của `oauth2Login`, không phải `spring-boot-starter-oauth2-resource-server`. Không thêm `spring-boot-starter-web` (Servlet) vì lab chạy WebFlux.

### 6.2. OidcApplication.java

~~~java
package example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcApplication.class, args);
    }
}
~~~

### 6.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${OIDC_CLIENT_ID:replace-me}
            client-secret: ${OIDC_CLIENT_SECRET:replace-me}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
~~~

Khi có registration tên `google`, Spring Boot sử dụng provider defaults cho Google. Hai giá trị `replace-me` là **placeholder chỉ cho test/khởi động**: phải đặt `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` thật mới login được tại Google.

**Không đưa secret thật vào YAML được commit, README, CI logs hoặc JavaScript.** Khi muốn xác thực người dùng tại provider khác, phải dùng ClientRegistration/provider settings phù hợp, không copy thông số Google sang IdP không tương thích.

## 7. WebFlux SecurityWebFilterChain và oauth2Login

File `src/main/java/example/oidc/SecurityConfig.java`:

~~~java
package example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.POST, "/api/notes").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

Giải thích:

- `@EnableWebFluxSecurity` kích hoạt reactive HTTP security.
- `authorizeExchange` cho phép homepage/login; `/api/me` và POST `/api/notes` yêu cầu authenticated user.
- `oauth2Login(Customizer.withDefaults())` cấu hình OAuth2 Client Authorization Code login, dựa vào `ReactiveClientRegistrationRepository` từ Boot properties.
- `logout(Customizer.withDefaults())` dùng local logout filter.
- Spring Security WebFlux **bật CSRF mặc định**. Vì browser dùng session cookie, không tắt CSRF cho POST chỉ vì IdP bên ngoài.
- `anyExchange().denyAll()` từ chối các routes ngoài hợp đồng. Các OAuth2 login endpoints là routes do Spring Security filters xử lý, không phải controllers tự định nghĩa.
- Không bật HTTP Basic hoặc form password login thay thế nếu kiến trúc yêu cầu chỉ đăng nhập qua IdP.

**Không nhầm API Servlet:** `HttpSecurity`/`SecurityFilterChain`/`HttpSession` thuộc Servlet; ở đây dùng `ServerHttpSecurity`/`SecurityWebFilterChain`/`WebSession`.

## 8. Controller trả subject OIDC, không lộ token

File `src/main/java/example/oidc/ProfileController.java`:

~~~java
package example.oidc;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record NoteInput(String text) {}

@RestController
public class ProfileController {

    @GetMapping("/")
    public Mono<Map<String, String>> publicPage() {
        return Mono.just(Map.of(
            "message", "Visit /login or /oauth2/authorization/google"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @PostMapping("/api/notes")
    public Mono<Map<String, String>> save(
            @RequestBody Mono<NoteInput> input) {
        return input.map(note -> Map.of(
            "accepted", note.text()));
    }
}
~~~

`@AuthenticationPrincipal OidcUser` phù hợp khi registration dùng OIDC scope `openid`; nếu provider chỉ cung cấp OAuth2 UserInfo, principal có thể là `OAuth2User` chứ không có ID Token. Lab này **cố ý chọn OIDC**.

Với user thật, JSON trả dạng:

~~~json
{"subject":"provider-assigned-subject"}
~~~

Giá trị này do IdP cấp, không có một subject chung cố định. Không trả ID Token, access token, refresh token hay secret cho client chỉ để hiển thị profile. Nếu lưu user nội bộ, hãy dùng khóa `(issuer, sub)` hoặc mapping sang user ID bất biến, không dùng email làm primary key.

POST notes chỉ echo dữ liệu **để test login/CSRF**, không ghi DB. Khi tạo app thật, service vẫn phải kiểm tra owner/tenant, validation, audit và transaction.

## 9. URL mặc định và quy trình chạy với Google

| Thành phần | URL/địa chỉ | Vai trò |
| --- | --- | --- |
| Login page | `/login` | Trang login do Spring Security sinh khi phù hợp |
| Bắt đầu OAuth2 | `/oauth2/authorization/google` | Tạo request, state; redirect tới IdP |
| Authorization endpoint | Tại Google | User đăng nhập/consent |
| Callback | `/login/oauth2/code/google` | Xử lý code và state |
| Token endpoint | Tại Google | Backend trao code lấy token |
| JWKS/UserInfo | Tại IdP | Validate token, lấy claims khi cần |
| Profile local | `/api/me` | Dùng local Authentication từ session |
| Logout local | `POST /logout` với CSRF | Kết thúc local session theo cấu hình |

Tại Google OAuth client configuration, đăng ký chính xác:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Ví dụ cấu hình biến môi trường với **Bash**:

~~~bash
export OIDC_CLIENT_ID="id-issued-by-provider"
export OIDC_CLIENT_SECRET="secret-issued-by-provider"
mvn spring-boot:run
~~~

Với **PowerShell**:

~~~powershell
$env:OIDC_CLIENT_ID = "id-issued-by-provider"
$env:OIDC_CLIENT_SECRET = "secret-issued-by-provider"
mvn spring-boot:run
~~~

Các giá trị là placeholder, phải thay bằng credential thật và quản lý an toàn. Mở `http://localhost:8080/login` để chọn Google, hoặc mở thẳng `http://localhost:8080/oauth2/authorization/google`.

Sau login/consent, browser quay về callback rồi vào app. Truy cập `/api/me` bằng **cùng browser session** để thấy JSON subject. Nếu dùng private window/cookie rỗng, đó là người chưa đăng nhập và sẽ vào login flow.

**Không dùng curl như bằng chứng hoàn thành toàn bộ OAuth2 login.** `curl -i http://localhost:8080/oauth2/authorization/google` chỉ quan sát redirect đầu tiên, không thực hiện browser login/consent, session, callback và JWKS validation.

## 10. Thực tế tại IdP: provider mặc định và custom issuer

Spring Boot có provider defaults cho các nhà cung cấp thông dụng như Google. Với một IdP OIDC doanh nghiệp, dùng **registration khác**, ví dụ `enterprise`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise:
            provider: enterprise
            client-id: ${ENTERPRISE_CLIENT_ID}
            client-secret: ${ENTERPRISE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          enterprise:
            issuer-uri: ${ENTERPRISE_ISSUER_URI}
~~~

Đây là **YAML thay thế**, không dán chồng vào project Google trừ khi muốn hỗ trợ nhiều IdP. `issuer-uri` phải đúng issuer do IdP công bố. Spring Boot có thể dùng OIDC discovery để tìm authorization/token/JWKS/UserInfo endpoints.

**Lưu ý:** Với custom issuer, metadata discovery có thể cần network ở thời điểm tạo ClientRegistration/startup. Nếu IdP không truy cập được hoặc issuer URI sai, app có thể không khởi động hoặc login không hoạt động. Không dùng URI giả rồi tắt signature validation để vượt lỗi.

Nếu IdP không hỗ trợ discovery, Spring Boot có properties `provider.enterprise.authorization-uri`, `token-uri`, `jwk-set-uri`, `user-info-uri`, `user-name-attribute`. Khi điền tay, phải đảm bảo TLS, issuer, endpoint URLs và token validation nhất quán với cấu hình nhà cung cấp.

### 10.1. Scope đúng nhu cầu

- `openid`: yêu cầu OpenID Connect login và ID Token.
- `profile`: tên/ảnh/profile claims nếu IdP cho phép.
- `email`: email claims nếu provider cấp; cần xét `email_verified`.
- `offline_access`: chỉ xin nếu thực sự cần refresh/offline access, theo IdP policy.
- Scopes của API IdP: chỉ xin mức tối thiểu; nút login không nên mặc nhiên xin quyền đọc dữ liệu Drive/mail.

**Không đánh đồng scope với role.** Một user xác thực thành công và có `openid` không tự được cấp `ROLE_ADMIN` trong ứng dụng.

## 11. Định danh người dùng và liên kết tài khoản nội bộ

ID Token OIDC chứa các claims như `iss`, `sub`, `aud`, `iat`, `exp`, và `nonce` nếu dùng. Spring Security OIDC xử lý ID Token validation và xây `OidcUser`.

Định danh bền vững nên là:

~~~text
Application user ID (UUID)
    ↔ verified identity: issuer + subject
    ↔ app-specific roles/tenant/permissions
~~~

Hai ID Tokens có cùng `sub` nhưng khác `iss` **không chứng minh cùng một người**. Email có thể đổi, được tái cấp, không xác minh hoặc xuất hiện trên nhiều providers; không tự gộp account khi email giống nhau.

Ví dụ cấu trúc database:

~~~sql
CREATE TABLE user_identities (
    id UUID PRIMARY KEY,
    application_user_id UUID NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    CONSTRAINT uq_identity UNIQUE (issuer, subject)
);
~~~

Trước khi liên kết thêm một external identity với account đang có, phải xác minh người dùng sở hữu identity hiện tại **và** identity mới. Nếu không, một email chưa verified từ provider khác có thể dẫn tới account takeover.

**Mapping authority:** Spring có thể tạo `OIDC_USER` và authorities từ scopes. Quyền nghiệp vụ phải do policy nội bộ hoặc trusted provider groups cấp rõ ràng. Nếu group/tenant thay đổi, session/token cũ có thể chứa quyền stale; cần thời hạn session, refresh/revalidation hoặc revocation phù hợp.

## 12. Ví dụ tùy chọn: mapping groups sang role ứng dụng

Một IdP có thể ký claim `groups` trong ID Token. Nếu đây là claim đáng tin cậy và nhóm `app-readers` được doanh nghiệp quản lý, có thể thêm bean `GrantedAuthoritiesMapper` để chuyển sang `ROLE_APP_READER`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Bean
GrantedAuthoritiesMapper appRoles() {
    return authorities -> {
        Set<GrantedAuthority> mapped = new HashSet<>(authorities);
        for (GrantedAuthority auth : authorities) {
            if (auth instanceof OidcUserAuthority oidc) {
                List<String> groups =
                    oidc.getIdToken().getClaimAsStringList("groups");
                if (groups != null && groups.contains("app-readers")) {
                    mapped.add(new SimpleGrantedAuthority(
                        "ROLE_APP_READER"));
                }
            }
        }
        return mapped;
    };
}
~~~

Đây là **snippet bổ sung**, cần đặt trong một Spring `@Configuration`. Nó không thuộc ba class runnable của lab. Không tùy tiện cấp role nếu `groups` không có trong trusted ID Token; một số IdP cấp groups qua UserInfo hoặc API riêng và cần `ReactiveOAuth2UserService` để tra cứu.

Nếu role/tenant đến từ DB, nên dùng kiểm tra reactive service/domain trên quyền hiện hành; mapper đồng bộ không phải nơi gọi JDBC blocking trong event-loop. `hasRole("APP_READER")` tìm `ROLE_APP_READER`, còn `hasAuthority(...)` so khớp chuỗi đầy đủ.

## 13. WebSession sau login và đời sống của token

Trong WebFlux, Spring Security có thể lưu `SecurityContext` trong `WebSession` qua `WebSessionServerSecurityContextRepository`. Browser thường giữ cookie phiên tên `SESSION`; giá trị cookie là **session ID**, không phải ID Token hoặc access token.

Phân biệt ba loại storage:

| Storage | Nội dung | Vòng đời |
| --- | --- | --- |
| Authorization request repository | State và request đang chờ callback | Tạm thời giữa start/callback |
| SecurityContext + WebSession | User đã login vào application | Đến logout/timeout/invalidation |
| Authorized client repository/service | Access/refresh tokens cho downstream API | Theo token expiry/refresh/revocation policy |

`ReactiveSecurityContextHolder` cho phép đọc Authentication trong Reactor Context **của request đang xử lý**. Không dùng Servlet `SecurityContextHolder` ThreadLocal rồi giả định code reactive luôn chạy cùng một thread.

Trong hệ thống nhiều nodes, authorization request + session store phải sẵn cho callback ngay cả khi redirect về node khác. Có thể dùng Spring Session/Redis hoặc routing affinity đúng cách. Đừng tự cho rằng “external login” làm ứng dụng không còn session state.

Cookie production cần HTTPS, `Secure`, `HttpOnly`, `SameSite`, timeout, rotation/session fixation protection và logout invalidation. Token trong authorized client store phải được bảo vệ; không gửi raw token cho frontend chỉ để lấy profile.

## 14. CSRF cho session, login và logout

OAuth2 `state` và Spring Web CSRF token **khác nhau**. State bảo vệ tương quan OAuth2 authorization callback, còn CSRF token bảo vệ thao tác POST/PUT/PATCH/DELETE của ứng dụng khi browser tự gửi session cookie. OIDC `nonce` liên kết ID Token với authentication request.

Spring Security WebFlux bật CSRF protection mặc định. Trong lab, POST `/api/notes` với người đã xác thực **nhưng không có CSRF token** phải bị chặn 403; với CSRF token hợp lệ, request mới đến controller. Đây là lý do không nên thêm `csrf().disable()` chỉ vì app dùng OIDC.

Local logout thường dùng `POST /logout` với CSRF, không biến thành GET link tùy ý để né token. Với SPA, cần cung cấp CSRF token qua server-rendered form/meta hoặc endpoint an toàn; token phải khớp session hiện tại và có thể cần lấy lại sau login/logout. CORS allowlist không thay CSRF vì browser có thể gây cross-site request có tác dụng phụ ngay cả khi attacker không đọc được response.

## 15. Redirect URI và reverse proxy

Giá trị default:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ local:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Đằng sau ingress, browser có thể gọi `https://app.example.com` trong khi backend thấy `http://service:8080`. Nếu `{baseUrl}` được tính theo URL nội bộ, IdP có thể trả lỗi `redirect_uri_mismatch`.

Cần cấu hình forwarded headers/trusted proxy boundary đúng để Spring nhìn thấy public scheme/host/port; tuyệt đối không tin trực tiếp `X-Forwarded-Host` giả mạo từ internet. Ở provider console đăng ký callback **chính xác**, không dùng wildcard để lách lỗi.

Nếu tùy biến callback thành `/login/oauth2/callback/{registrationId}`, phải đổi đồng thời:
1. `oauth2Login().authenticationMatcher(...)` trong ServerHttpSecurity.
2. `ClientRegistration.redirectUri`.
3. Allowed redirect URI trong IdP console.

Sau login, một success redirect dựa trên tham số như `next` phải được kiểm soát allowlist nội bộ; không chấp nhận open redirect tới website lạ.

## 16. Logout local và OIDC logout

| Kiểu logout | Làm được gì? | Không đảm bảo |
| --- | --- | --- |
| Xóa cookie client | Browser ngừng gửi session ID | Server session cũ có thể chưa bị invalidate |
| Local POST logout | Xóa local SecurityContext/session theo config | Không tự logout khỏi IdP SSO |
| RP-Initiated OIDC Logout | Redirect tới provider end-session endpoint nếu hỗ trợ | Không nhất thiết revoke tất cả access tokens |
| Back-channel logout | Provider báo application kết thúc session qua giao thức hỗ trợ | Cần session registry/mapping tương ứng |
| Refresh token revocation | Ngăn lấy access token mới | Access token đã phát có thể còn valid tới expiry |

**Local logout không đồng nghĩa global SSO logout.** Sau local logout, nếu browser vẫn có session tại IdP, người dùng mở OAuth2 login lần nữa có thể tự được xác thực. Đây là hành vi SSO, không nhất thiết là lỗi của logout local.

Nếu IdP công bố end-session metadata và hỗ trợ client-initiated logout, Spring Reactive có `OidcClientInitiatedServerLogoutSuccessHandler`. Ví dụ **chỉ là chain thay thế**; không copy thêm bean song song vào project lab nếu chưa tách matcher:

~~~java
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;

@Bean
SecurityWebFilterChain oidcLogoutChain(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository clients) {
    var handler = new OidcClientInitiatedServerLogoutSuccessHandler(clients);
    handler.setPostLogoutRedirectUri("{baseUrl}");

    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(handler))
        .build();
}
~~~

Provider phải hỗ trợ logout endpoint và allowlisted post-logout redirect URL. Back-channel logout có thể cần registry/session cookie name chính xác; đừng tự giả định mọi IdP hỗ trợ hoặc mọi phiên bản WebFlux có defaults giống nhau.

## 17. WebTestClient: kiểm thử không cần IdP thật

`spring-security-test` cung cấp `mockOidcLogin()` để inject một OIDC principal cho request test; nó **không** xác minh chữ ký thật, issuer, audience, token endpoint hoặc callback. Các tests dưới đây chứng minh redirect khởi tạo flow, HTTP authorization và CSRF, không chứng minh toàn bộ OIDC handshake cryptographically.

File `src/test/java/example/oidc/OidcLoginTest.java`:

~~~java
package example.oidc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OidcLoginTest {
    @Autowired WebTestClient client;

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").exists();
    }

    @Test
    void anonymousBrowserMustLogin() {
        client.get().uri("/api/me").exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void authorizationStartHasStateAndProviderRedirect() {
        EntityExchangeResult<byte[]> result =
            client.get().uri("/oauth2/authorization/google")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        String location = result.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.startsWith("https://accounts.google.com/"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("openid"));
    }

    @Test
    void mockOidcUserCanReadSubjectButNotTokens() {
        client.mutateWith(mockOidcLogin().idToken(token ->
                token.claim("sub", "external-sub-123")))
            .get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("external-sub-123")
            .jsonPath("$.access_token").doesNotExist()
            .jsonPath("$.id_token").doesNotExist();
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() {
        client.mutateWith(mockOidcLogin())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithCsrfSucceeds() {
        client.mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hello"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("hello");
    }

    @Test
    void unexpectedRouteDenied() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/api/admin/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Lưu ý về test status:** Browser flow của oauth2Login thường redirect anonymous tới `/login`; API thuần Bearer thường trả 401. 403 trong POST có thể là CSRF hoặc authorization. Không biến mọi response thành 200/401 chỉ để “test xanh”.

Mock OIDC user chỉ chứng minh lớp ứng dụng nhận Authentication đã được tạo, không thể thay kiểm thử nhà cung cấp thật. Để test full code exchange/ID Token validation offline, cần mock IdP hỗ trợ metadata, authorize, token, JWKS và userInfo đúng giao thức; đừng disable signature verification.

## 18. Lệnh chạy, kỳ vọng và kiểm tra từng bước

Ở thư mục `pom.xml`:

~~~bash
mvn clean test
~~~

Kỳ vọng **7 JUnit methods** trong `OidcLoginTest` PASS với test config và Google provider defaults, không cần secret Google thật cho mock security tests. stdout Maven tùy version và môi trường, không có giá trị subject cố định.

Để login thật:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra trong browser:
1. `GET /login` có link đăng nhập.
2. Link đưa tới `/oauth2/authorization/google`.
3. `Location` redirect trỏ tới Google, có `client_id`, `state`, `redirect_uri`, `scope`.
4. Sau IdP login, callback không trả `redirect_uri_mismatch`/`invalid_client`.
5. Browser lưu cookie application; `/api/me` cho subject.
6. Request không cookie trong private browser phải được yêu cầu đăng nhập.
7. POST `/api/notes` thiếu CSRF bị chặn, có token hợp lệ mới được xử lý.

Quan sát redirect ban đầu bằng curl chỉ là smoke test:

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/google"
~~~

Đừng paste `Location` từ callback có authorization code vào issue tracker/log. Browser DevTools/IdP audit có thể hỗ trợ chẩn đoán, nhưng phải che secret/token/cookie.

## 19. Các lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có login link | ClientRegistration không nạp, custom page sai | Xem registration ID, `/login` và repository |
| `/oauth2/authorization/google` không redirect | Sai registrationId, resolver/security chain | Kiểm tra chính xác đường dẫn |
| `redirect_uri_mismatch` | Callback IdP khác app baseUrl | Đối chiếu scheme/host/port/path và proxy |
| `invalid_client` | Sai client ID/secret/authentication method | Kiểm tra IdP console/secret rotation |
| Callback state mismatch | Session/state bị mất, đổi browser/node/cookie | Cookie policy, shared session, state correlation |
| Token thiếu ID Token | Thiếu `openid` hoặc provider chỉ OAuth2 | Dùng OIDC provider và scope phù hợp |
| ID Token không hợp lệ | Sai issuer/aud/exp/nonce/signature/JWKS | Kiểm tra metadata, clock, trust roots |
| Vào callback xong vẫn anonymous | SecurityContext/session cookie không lưu/tải | WebSession, auth success và Set-Cookie |
| POST trả 403 | CSRF hoặc thiếu quyền | Kiểm tra CSRF token, role/scope riêng |
| User được gán nhầm account | Ghép theo email thay `(iss,sub)` | Rà soát identity linking |
| Logout xong vẫn đăng nhập IdP | Local logout không xóa SSO session | Xem RP-Initiated/Back-channel logout |
| Đổi role ở IdP mà app chưa thay | Session/claims cũ | Session invalidation/refresh/revalidation |
| Token downstream bị API từ chối | Sai audience/scope, hết hạn | Authorized client token policy |
| Lộ secret qua log | Log request/token hoặc config | Redaction, secret manager, hạn chế quyền |

**Thứ tự debug:** config ClientRegistration → authorization redirect → state/session → callback/redirect URI → token exchange → ID Token verification → SecurityContext/WebSession → cookie → role/CSRF/business authorization. Không sửa bằng cách mở toàn bộ redirect URIs, tắt OIDC validation hoặc vô hiệu hóa CSRF.

## 20. PKCE, state, nonce và các ranh giới tin cậy

- **State:** random theo login attempt, callback phải khớp authorization request đang chờ. Không hardcode hay nhận từ input người dùng tùy ý.
- **Nonce:** OIDC dùng để liên kết ID Token và request khi áp dụng; không dùng username/email làm nonce.
- **PKCE:** client tạo `code_verifier` ngẫu nhiên, gửi `code_challenge` rồi trình verifier khi trao code; giảm nguy cơ dùng code bị đánh cắp.
- **PKCE default:** Spring hỗ trợ PKCE cho public client với cấu hình `client-authentication-method: none` và secret rỗng, hoặc khi client settings yêu cầu proof key. **Không tự khẳng định confidential client trong lab luôn được bật PKCE mặc định**; nếu policy yêu cầu, cấu hình và test `code_challenge`.
- **Issuer:** chỉ tin IdP trong allowlist; không nhận issuer URI tùy ý từ HTTP parameter rồi thực hiện discovery (nguy cơ SSRF/trust confusion).
- **ID Token:** xác minh signature, issuer, audience, timestamp và nonce theo OIDC; không chấp nhận `alg=none`.
- **Redirect:** allowed redirect URL phải chính xác; `next` sau login phải bị giới hạn để không thành open redirect.
- **Credential:** không log access/refresh token, client secret, code hoặc session ID; production dùng HTTPS, cookie flags và secret rotation.

## 21. Liên kết với API, SPA và BFF

| Mô hình | Browser/client mang gì đến backend? | Cấu hình |
| --- | --- | --- |
| Server-side WebFlux OIDC Login | Cookie session ứng dụng | `oauth2Login`, CSRF, WebSession |
| SPA trực tiếp gọi API bằng JWT | Authorization Bearer token | OAuth2 Code + PKCE ở client; backend `oauth2ResourceServer().jwt()` |
| Backend-for-Frontend (BFF) | Browser → cookie BFF, BFF → Bearer downstream | `oauth2Login` tại BFF, authorized client manager/store |
| Service-to-service | Access token máy/ủy quyền phù hợp | OAuth2 Client Credentials + Resource Server, không user login session |

Không copy raw ID Token vào localStorage chỉ để “dùng làm access token”. Không có quyền object-level chỉ vì user authenticated; các API nghiệp vụ vẫn kiểm tra owner/tenant. Nếu BFF gọi downstream thay user, nó cần `ServerOAuth2AuthorizedClientRepository` và quản lý token an toàn, truyền **access token đúng audience/scope**, không truyền ID Token bừa bãi.

## 22. Bài tập và checklist

**A — chuẩn bị nhà cung cấp:** Tạo Web application client tại IdP, cấu hình callback chính xác, thử login thật qua browser. Không ghi token/secret vào báo cáo.

**B — sửa lỗi redirect:** Giả lập callback dùng sai scheme/port; so sánh `redirect_uri` của authorization redirect với allowlist IdP; cấu hình proxy trusted.

**C — kiểm tra state:** Bắt đầu login ở browser A, cố dùng callback ở browser B không có session. Giải thích lý do phải từ chối.

**D — phân biệt OIDC/Resource Server:** Xây bảng request từ browser local session và API Bearer; xác định service dùng `oauth2Login` hay `oauth2ResourceServer`.

**E — mockOidcLogin:** Test anonymous redirect; mock subject; test CSRF thiếu/đủ; giải thích vì sao mock không xác minh ID Token thật.

**F — identity linking:** Thiết kế unique constraint `(issuer,sub)` và lưu application user ID; thử hai providers có cùng email nhưng không auto-link.

**G — role mapping:** Thêm trusted group `app-readers` vào IdP test; bảo đảm thiếu claim không được cấp role.

**H — OIDC logout:** So sánh local POST logout, RP-Initiated Logout và back-channel; đánh giá IdP có hỗ trợ end-session metadata hay không.

**I — PKCE:** Bật policy require PKCE với IdP hỗ trợ, quan sát `code_challenge` và quy tắc lưu code_verifier.

**Checklist:**
- [ ] Hiểu OAuth2 Login vs OIDC vs Resource Server.
- [ ] Khai báo đúng ClientRegistration/registrationId/client ID/secret/scopes.
- [ ] Callback URI khớp tuyệt đối tại ứng dụng và IdP.
- [ ] Sử dụng ServerHttpSecurity.oauth2Login trong WebFlux.
- [ ] Không tự xử lý code/state bằng controller tùy tiện.
- [ ] Validate ID Token và không dùng token sai audience.
- [ ] Dùng `issuer + sub` để liên kết user, không tin email làm primary key.
- [ ] Giữ CSRF cho browser session, POST và logout.
- [ ] Biết state/nonce/PKCE khác nhau.
- [ ] Có test anonymous, redirect provider, mock OIDC và CSRF.
- [ ] Biết mock test khác end-to-end login thật.
- [ ] Có chiến lược cookie/security/session/secret rotation/logout theo production.

## 23. Câu hỏi tự kiểm tra

1. Một application dùng `oauth2Login()` đóng vai OAuth2 Client hay Resource Server?
2. URL nào bắt đầu login và callback URL mặc định khi registrationId là google?
3. Vì sao backend có thể login qua IdP mà không nhìn thấy password IdP?
4. ID Token dùng cho mục đích nào, vì sao không dùng nó làm access token tùy tiện?
5. Vì sao state và CSRF token của ứng dụng khác nhiệm vụ?
6. Nonce liên quan ID Token ra sao? PKCE giải quyết nguy cơ gì?
7. Vì sao client secret cần giữ server-side và không đưa vào frontend?
8. Vì sao account identity nên dùng `issuer + sub` thay vì email?
9. Role ứng dụng có tự sinh khi user đăng nhập Google thành công không?
10. `mockOidcLogin()` có xác thực chữ ký và audience thật không?
11. Logout local có tự xóa phiên IdP SSO không?
12. Khi proxy đổi host/port, `{baseUrl}` sai ảnh hưởng gì tới callback?
13. Trong một app có WebSession, vì sao POST vẫn cần CSRF?
14. Khi nào dùng BFF/session, khi nào API bearer và Resource Server?
15. Nếu provider metadata không thể truy cập, custom issuer discovery có thể gây lỗi nào?

## 24. Tài liệu tham khảo

- [Spring Security — OAuth2 Login WebFlux (Core)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): cấu hình client/redirect/Google và `oauth2Login`.
- [Spring Security — OAuth2 Login WebFlux (Advanced)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html): authorization resolver, custom callback, user authorities, ID Token verification.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): local/RP-Initiated/back-channel logout.
- [Spring Security — OAuth2 Grant Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): Code Grant và PKCE.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()`.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF trên session/login/logout.
- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): registration/provider configuration.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, claims và validation.
- [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): OAuth 2.0 Authorization Framework.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): PKCE.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth2/OIDC risks và best practices.

**Kết luận:** Trong Spring Security Reactive, `oauth2Login` là cơ chế **OAuth2 Client** kết nối tới IdP bên ngoài. Cần cấu hình `ClientRegistration` chính xác, bảo vệ authorization code/state/nonce/PKCE, kiểm chứng ID Token và lưu session ứng dụng an toàn. ID Token, access token và session cookie có mục đích khác nhau. Cuối cùng, tách tests của OAuth2 redirects/HTTP security khỏi full integration với IdP để tránh nhầm một mock principal với login đã được xác minh thật.