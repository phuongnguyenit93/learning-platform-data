# OAuth2UserService, OidcUserService và ánh xạ danh tính bên ngoài trong Spring Security Servlet

## 1. Vấn đề: tài khoản bên ngoài khác tài khoản nội bộ

Một ứng dụng Spring MVC cho phép người dùng đăng nhập bằng GitHub, một nhà cung cấp OpenID Connect (OIDC) hoặc hệ thống danh tính của doanh nghiệp. Sau khi IdP xác thực người dùng, ứng dụng nhận profile/claims nhưng vẫn cần quyết định **người này tương ứng tài khoản nội bộ nào và được cấp quyền gì**.

Ba phần việc phải tách rõ:

1. **Xác thực bên ngoài:** OAuth2/OIDC login hoàn tất redirect, authorization code exchange, kiểm tra các thông tin cần thiết và lấy profile. Spring Security hỗ trợ các bước giao thức.
2. **Ánh xạ danh tính:** Từ một định danh ổn định được tin cậy của IdP, tìm hoặc tạo **local account ID**. Không gộp tài khoản chỉ theo email hoặc tên.
3. **Phân quyền:** Kiểm tra local account còn hiệu lực, sau đó tải role/permission từ chính sách đáng tin cậy của ứng dụng. Không chuyển một claim bên ngoài tên `admin` thành `ROLE_ADMIN` một cách tự động.

Ví dụ: GitHub trả `id=817263`, `login=hana-dev`; OIDC doanh nghiệp trả `iss=https://login.company.example`, `sub=user-492`. Đây là **hai danh tính bên ngoài**. Chúng có thể thuộc cùng một local account sau quy trình liên kết hợp lệ, nhưng không thể suy ra chỉ vì `email` hoặc `name` giống nhau.

Bài học tập trung vào hai extension point của **Spring Security Servlet**: `OAuth2UserService` và `OidcUserService`, cách chọn khóa external identity, cách xây principal giữ được local ID, và cách kiểm thử logic ánh xạ trong ứng dụng **Java 17+ / Spring Boot 3 / Spring Security 6**.

**Phân biệt phạm vi:** `oauth2Login()` là cơ chế đăng nhập tương tác qua browser để tạo session/principal cho người dùng. Đây không phải cấu hình **OAuth2 Resource Server** đọc bearer token từ mỗi request API; `JwtAuthenticationConverter` của resource server không tự thay thế hai user service của OAuth2 Login.

## 2. Vị trí của user service trong luồng Authorization Code

Một quy trình đăng nhập phổ biến:

~~~text
Browser             Spring Security Servlet                          IdP
   |                           |                                        |
   | GET /oauth2/authorization/{registrationId}                       |
   |-------------------------->|                                        |
   |                           | Xây authorization request, state      |
   |<--------------------------|                                        |
   |==========================> Trang đăng nhập IdP ===================>|
   |<========================== Redirect code + state ================|
   | GET /login/oauth2/code/{registrationId}?code=...&state=...        |
   |-------------------------->|                                        |
   |                           | Kiểm tra state, đổi code lấy token    |
   |                           |--------------------------------------->|
   |                           |<---------------------------------------|
   |                           |                                        |
   |                    +------+-----------------------+                |
   |                    | OAuth2 không dùng OIDC       |                |
   |                    | DefaultOAuth2UserService    | -> OAuth2User   |
   |                    +------------------------------+                |
   |                    | Có OIDC (openid scope)       |                |
   |                    | OidcUserService             | -> OidcUser    |
   |                    +------+-----------------------+                |
   |                           |                                        |
   |                  Custom mapping từ external key                   |
   |                  -> local account + trusted roles                 |
   |                           |                                        |
   |                  Authentication -> SecurityContext                |
   |<--------------------------|                                        |
   | GET /me (kèm session cookie)                                       |
   |-------------------------->|                                        |
   |               Authorization của ứng dụng                          |
~~~

Các filter/processor Spring Security xử lý OAuth2 authorization redirect, callback, state và code exchange. Với OIDC, framework còn kiểm tra ID token theo issuer, audience, chữ ký, thời hạn và các quy tắc OIDC liên quan (bao gồm nonce trong những trường hợp áp dụng). **Custom `OidcUserService` không được dùng để bỏ qua việc xác thực ID token** hoặc tin dữ liệu JSON tự gửi từ browser.

Sau login, `Authentication` thường là `OAuth2AuthenticationToken`; principal được cung cấp qua `Authentication.getPrincipal()` hoặc `@AuthenticationPrincipal`. OAuth2 authorized client, access token/refresh token và lifecycle của chúng được quản lý riêng. Không sử dụng access token hay refresh token làm khóa người dùng nội bộ.

## 3. OAuth2UserService khác OidcUserService như thế nào?

| Tiêu chí | OAuth2UserService | OidcUserService |
| --- | --- | --- |
| Luồng | OAuth2 login không OIDC, ví dụ GitHub | OpenID Connect login, thường nhận biết qua scope `openid` |
| Input | `OAuth2UserRequest` (client registration, access token) | `OidcUserRequest` (client registration, access token, **ID token**) |
| Output | `OAuth2User`: attributes, authorities, name | `OidcUser`: kế thừa OAuth2User, có ID token/claims/UserInfo |
| Service mặc định | `DefaultOAuth2UserService` | `OidcUserService` |
| Khóa danh tính | Provider namespace + stable ID theo contract provider | **Issuer (`iss`) + subject (`sub`)** từ ID token đã xác minh |
| Servlet DSL | `oauth2Login().userInfoEndpoint().userService(...)` | `oauth2Login().userInfoEndpoint().oidcUserService(...)` |

Kiểu generic:

~~~java
OAuth2UserService<OAuth2UserRequest, OAuth2User>
OAuth2UserService<OidcUserRequest, OidcUser>
~~~

`OidcUserService` là class thực thi giao diện generic `OAuth2UserService` với kiểu vào/ra OIDC. Không coi nó là cách thay thế cho mọi OAuth2 provider. Nếu ứng dụng hỗ trợ GitHub và một IdP OIDC, nên cấu hình **cả hai nhánh** đúng loại:

~~~java
// Mảnh cấu hình trong một SecurityFilterChain, chưa phải class độc lập:
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userService(customOAuth2Users)
        .oidcUserService(customOidcUsers)
    )
);
~~~

Đăng nhập OIDC không đổi khi chỉ cấu hình `.userService(...)` là một lỗi dễ gặp: OIDC có service riêng thông qua `.oidcUserService(...)`.

## 4. Attributes, claims, UserInfo và token khác nhau

### 4.1. OAuth2 login không OIDC

`DefaultOAuth2UserService` dùng access token để gọi UserInfo endpoint theo `ClientRegistration` phù hợp. JSON nhận được trở thành `OAuth2User.getAttributes()`. Provider quy định trường định danh; client registration có `userNameAttributeName` để Spring biết thuộc tính dùng làm `getName()`.

Một JSON profile GitHub minh họa:

~~~json
{
  "id": 817263,
  "login": "hana-dev",
  "name": "Hana",
  "email": null,
  "avatar_url": "https://avatars.example.net/profile.png"
}
~~~

Trong ví dụ GitHub, `id` được dùng làm định danh ổn định của tài khoản theo contract; `login`, `name`, `email`, `avatar_url` có thể thay đổi hoặc thiếu. Email riêng tư có thể không có trong UserInfo mặc dù đăng nhập thành công. Provider khác không nhất thiết có key `id` hoặc cùng kiểu dữ liệu; phải viết adapter tương ứng.

`OAuth2User.getAuthorities()` có thể chứa `OAuth2UserAuthority` từ profile và `SCOPE_...` liên quan đến ủy quyền gọi API. Những authority đó **chưa phải** local business role. `SCOPE_email` không đồng nghĩa `ROLE_MEMBER` hoặc `ROLE_ADMIN`.

### 4.2. OIDC login

OIDC thêm **ID token**, thường là JWT với các claim:

~~~json
{
  "iss": "https://login.company.example",
  "sub": "user-492",
  "aud": "web-client-id",
  "iat": 1979996400,
  "exp": 1980000000,
  "name": "Hana",
  "email": "hana@example.org",
  "email_verified": true
}
~~~

Payload này chỉ là **dữ liệu minh họa**, không phải một token đã ký có thể dùng để đăng nhập. Khi framework xác minh ID token hợp lệ theo IdP đáng tin, mới dùng `iss` và `sub` làm external key.

`OidcUser` cung cấp `getIdToken()`, `getUserInfo()`, `getClaims()`, `getSubject()`, `getName()` cùng các accessor chuẩn khác. `OidcUserService` có thể tải UserInfo theo metadata, scope và quy tắc provider; **`getUserInfo()` có thể null**. Ngay cả khi UserInfo thiếu email/tên, một ID token có `iss/sub` hợp lệ vẫn cung cấp định danh OIDC.

- **ID token**: chứng cứ xác thực danh tính OIDC dành cho client đã được xác minh theo protocol.
- **Access token**: để client được cấp quyền gọi API/resource tương ứng; không phải local account ID bền vững.
- **Refresh token**: để xin access token mới theo chính sách provider; không phải thông tin profile và không được trả ra UI.
- **UserInfo**: các claim bổ sung về người dùng, có thể không được trả hoặc khác theo provider.
- **Profile attributes**: dữ liệu hiển thị/đồng bộ; không dùng username/email làm khóa nếu có stable identity key.

Trong một multi-tenant system, xác minh issuer/tenant được phép là điều kiện riêng. Claim `email_verified=true` không tự chứng minh quyền sở hữu **một tài khoản nội bộ đã tồn tại**.

## 5. Thiết kế external identity key và bảng liên kết

Tách identity liên bang khỏi account nội bộ:

~~~text
local_account
    id               UUID / primary key
    status           ACTIVE | SUSPENDED | ...
    authorities      quyền do ứng dụng quản lý

external_identity_link
    provider_key     OIDC issuer hoặc OAuth2 provider namespace
    subject          external stable subject
    local_account_id FK -> local_account.id
    UNIQUE(provider_key, subject)
~~~

Ví dụ:

| provider_key | subject | local_account_id |
| --- | --- | --- |
| `oidc:https://login.a.example` | `user-17` | `L-101` |
| `oidc:https://login.b.example` | `user-17` | `L-209` |
| `oauth2:github` | `817263` | `L-101`, chỉ nếu được link hợp lệ |

Hai OIDC provider có `sub=user-17` **không** chỉ cùng một người. Nếu một GitHub ID và một OIDC identity cùng nối tới `L-101`, phải có quy trình account linking được ủy quyền, **không** tự merge theo email.

**OIDC key chuẩn: `(iss, sub)`.** Lấy `iss` và `sub` từ **ID token đã xác thực**, giữ giá trị chính xác theo contract. Đừng tự lower-case subject, cắt dấu `/` cuối issuer hoặc suy diễn issuer từ domain email. Một số IdP sử dụng **pairwise subject** nên cùng người có thể có `sub` khác giữa nhiều client/sector.

**OAuth2 không OIDC:** namespace phải chỉ ra provider/registration được cấu hình. Với GitHub, `("oauth2:github", id)` là ví dụ. Nếu có nhiều GitHub enterprise domains/tenants hoặc nhiều nguồn nội bộ, namespace cần phân biệt theo trust boundary. Không lấy ngẫu nhiên một key tên `id` của mọi provider rồi bỏ namespace.

**Email không phải khóa an toàn:** email có thể rỗng, thay đổi, tái sử dụng, chưa xác thực hoặc cùng hiển thị tại nhiều IdP. Ngay cả email đã verified cũng không nên tự động liên kết một tài khoản có quyền cao. Liên kết nên yêu cầu một phiên local account hợp lệ và xác nhận lại ở provider mới hoặc quy trình phê duyệt chuyên biệt.

**Provisioning:** khi external key chưa có trong bảng, có thể tạo local account mới nếu hệ thống cho phép self-signup/JIT, hoặc từ chối và yêu cầu mời/phê duyệt nếu ứng dụng chỉ dành cho người đã được cấp quyền. Dùng unique constraint + transaction để xử lý hai login đồng thời; không chỉ `find` rồi `insert` không bảo vệ tranh chấp. Khi local account bị khóa, IdP login thành công **không** được tự kích hoạt lại quyền nội bộ.

## 6. Vai trò nội bộ và identity mapping: ranh giới an toàn

Một pipeline đúng:

~~~text
Provider đã được cấu hình đáng tin
    |
    +--> OAuth2User/OidcUser từ delegate mặc định
    |
    +--> Stable external key
    |      OAuth2: provider-specific id + namespace
    |      OIDC: verified issuer + subject
    |
    +--> ExternalIdentityLinkRepository.find(provider, subject)
    |      hoặc chính sách self-provision có transaction
    |
    +--> LocalAccount(id, status, tenant, roles)
    |
    +--> Từ chối nếu disabled/blocked/tenant không hợp lệ
    |
    +--> Principal giữ được localAccountId và profile
    |
    +--> Local granted authorities -> AuthorizationFilter
~~~

Phân biệt rõ **profile** với **quyền**: `email`, `preferred_username`, `name`, `picture` phục vụ UI; `sub`, `iss` phục vụ khóa. Một claim như `groups=["admins"]` chỉ có thể được map vào local role khi có **hợp đồng tin cậy và chính sách rõ ràng**, bao gồm kiểm tra issuer, audience/tenant, dữ liệu claim và sự đồng ý quản trị. Không map chuỗi `admin` từ profile bất kỳ thành `ROLE_ADMIN`.

`getName()` không phải lúc nào là local account ID: OIDC mặc định thường dựa trên `sub`, còn provider OAuth2 thường dùng attribute được registration cấu hình. Tốt nhất có trường `localAccountId` riêng trong principal hoặc tầng dịch identity rõ ràng. Không đổi `sub` trong ID token và không tạo token giả để ép `getName()` thành local ID.

## 7. Ví dụ chạy được với Java 17, Spring Boot 3.3.5

Ví dụ này nhận đăng nhập GitHub OAuth2 và một IdP OIDC được cấu hình từ môi trường, dùng **delegate service mặc định**, sau đó map external identity sang một local ID. Để tập trung vào cơ chế, local directory dùng `ConcurrentHashMap` và cấp `ROLE_MEMBER` cho mọi identity mới. Đây là **chính sách self-signup chỉ dành cho demo**: khi dùng thật, thay bằng persistent store, trạng thái tài khoản, link được phê duyệt và role tra cứu nội bộ.

Cấu trúc:

~~~text
external-login-demo/
  pom.xml
  src/main/java/example/externallogin/ExternalLoginApplication.java
  src/main/resources/application.yml
  src/test/java/example/externallogin/ExternalLoginApplicationTests.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>external-login-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
~~~

### 7.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope: read:user
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Spring Boot có thông số provider thông dụng cho GitHub. Với `company`, Spring có thể khám phá metadata từ issuer nếu IdP hỗ trợ discovery đúng chuẩn. Cần đăng ký **redirect URI** cho cả hai provider, thông thường ở local:

~~~text
http://localhost:8080/login/oauth2/code/github
http://localhost:8080/login/oauth2/code/company
~~~

Chương trình cần các biến môi trường client ID, client secret và issuer **hợp lệ** để khởi động. Không commit client secret hoặc token vào Git. Nếu reverse proxy ở trước ứng dụng, cần bảo đảm scheme/host/port public đúng để không sinh redirect URI sai. Luồng đăng nhập tương tác cần browser và cấu hình phía IdP; test unit ở mục 8 không cần IdP thật.

### 7.3. Ứng dụng và custom services

**src/main/java/example/externallogin/ExternalLoginApplication.java**

~~~java
package example.externallogin;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExternalLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }

    @Bean
    InMemoryIdentityDirectory directory() {
        return new InMemoryIdentityDirectory();
    }

    @Bean("mappedOAuth2Users")
    OAuth2UserService<OAuth2UserRequest, OAuth2User> mappedOAuth2Users(
            InMemoryIdentityDirectory directory) {
        DefaultOAuth2UserService delegate = new DefaultOAuth2UserService();

        return request -> {
            String registrationId =
                    request.getClientRegistration().getRegistrationId();

            if (!"github".equals(registrationId)) {
                throw invalidIdentity(); // Adapter chỉ cho GitHub
            }

            OAuth2User external = delegate.loadUser(request);
            Object rawId = external.getAttribute("id");
            String subject = rawId == null ? null : rawId.toString();

            String localId = directory.resolve(
                    new ExternalKey("oauth2:github", subject));

            return new LinkedOAuth2User(
                    external, localId, directory.localAuthorities(localId));
        };
    }

    @Bean("mappedOidcUsers")
    OAuth2UserService<OidcUserRequest, OidcUser> mappedOidcUsers(
            InMemoryIdentityDirectory directory) {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser external = delegate.loadUser(request);
            String issuer = request.getIdToken().getClaimAsString("iss");
            String subject = request.getIdToken().getClaimAsString("sub");

            String localId = directory.resolve(
                    new ExternalKey("oidc:" + require(issuer), subject));

            return new LinkedOidcUser(
                    external, localId, directory.localAuthorities(localId));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Qualifier("mappedOAuth2Users")
            OAuth2UserService<OAuth2UserRequest, OAuth2User> oauth2Users,
            @Qualifier("mappedOidcUsers")
            OAuth2UserService<OidcUserRequest, OidcUser> oidcUsers)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/error", "/login",
                                "/oauth2/authorization/**",
                                "/login/oauth2/code/**"
                        ).permitAll()
                        .anyRequest().hasRole("MEMBER"))
                .oauth2Login(oauth2 -> oauth2
                        .userInfoEndpoint(info -> info
                                .userService(oauth2Users)
                                .oidcUserService(oidcUsers)))
                .build();
    }

    static String require(String value) {
        if (value == null || value.isBlank()) {
            throw invalidIdentity();
        }
        return value;
    }

    static OAuth2AuthenticationException invalidIdentity() {
        return new OAuth2AuthenticationException(
                new OAuth2Error("invalid_external_identity"),
                "Missing or unsupported external identity");
    }

    record ExternalKey(String provider, String subject) {}

    static final class InMemoryIdentityDirectory {
        private final Map<ExternalKey, String> links =
                new ConcurrentHashMap<>();

        String resolve(ExternalKey key) {
            require(key.provider());
            require(key.subject());
            return links.computeIfAbsent(
                    key, ignored -> UUID.randomUUID().toString());
        }

        List<GrantedAuthority> localAuthorities(String localId) {
            require(localId);
            return List.of(new SimpleGrantedAuthority("ROLE_MEMBER"));
        }
    }

    interface LinkedPrincipal extends OAuth2User {
        String localAccountId();
    }

    record LinkedOAuth2User(
            OAuth2User external,
            String localAccountId,
            List<GrantedAuthority> localAuthorities
    ) implements LinkedPrincipal {

        @Override
        public Map<String, Object> getAttributes() {
            return external.getAttributes();
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return localAuthorities;
        }

        @Override
        public String getName() {
            return external.getName();
        }
    }

    record LinkedOidcUser(
            OidcUser external,
            String localAccountId,
            List<GrantedAuthority> localAuthorities
    ) implements LinkedPrincipal, OidcUser {

        @Override
        public Map<String, Object> getAttributes() {
            return external.getAttributes();
        }

        @Override
        public Map<String, Object> getClaims() {
            return external.getClaims();
        }

        @Override
        public OidcIdToken getIdToken() {
            return external.getIdToken();
        }

        @Override
        public OidcUserInfo getUserInfo() {
            return external.getUserInfo();
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return localAuthorities;
        }

        @Override
        public String getName() {
            return external.getName();
        }
    }

    @RestController
    static class WhoAmIController {

        @GetMapping("/")
        String home() {
            return "Visit /oauth2/authorization/github or " +
                    "/oauth2/authorization/company to sign in";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            LinkedPrincipal principal =
                    (LinkedPrincipal) authentication.getPrincipal();

            return Map.of(
                    "localAccountId", principal.localAccountId(),
                    "externalPrincipalName", principal.getName(),
                    "roles", principal.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .toList());
        }
    }
}
~~~

**Giải thích các quyết định trong ví dụ:**

- Custom `mappedOAuth2Users` gọi `DefaultOAuth2UserService.loadUser(request)` trước khi map. Custom `mappedOidcUsers` gọi `OidcUserService.loadUser(request)`. Các service giữ logic mặc định về profile/UserInfo và các bước xác thực của framework.
- GitHub identity lấy từ `id` đi kèm namespace `oauth2:github`; adapter từ chối registration OAuth2 khác thay vì đoán nó cũng có trường `id`.
- OIDC identity lấy từ `iss/sub` của **ID token** trong request đã được xác minh, không dựa vào `email` hay `preferred_username`. `require` từ chối giá trị null/rỗng, không âm thầm tạo account có khóa thiếu.
- Hai wrapper cho phép `getName()`/attributes/claims tiếp tục có ngữ nghĩa của provider nhưng thêm `localAccountId()`. Không sửa nội dung ID token, không tạo JWT giả.
- `getAuthorities()` ở wrapper chỉ trả local `ROLE_MEMBER`. Đây là chính sách demo để tránh chuyển ngẫu nhiên `SCOPE_*` hoặc `groups` bên ngoài thành quyền nội bộ. Khi ứng dụng cần dùng scopes cho downstream API, hãy thiết kế sự kết hợp authority **có giới hạn và phân biệt rành mạch**.
- `hasRole("MEMBER")` kiểm tra `ROLE_MEMBER`; real app còn phải kiểm trạng thái local account, tenant và quyền theo tài nguyên. Directory demo tự tạo account mới nên bất kỳ identity được hai provider chấp nhận đều có role MEMBER; điều đó **không** phù hợp với hệ thống chỉ cho người được mời.
- `/me` chỉ in local ID, tên principal và roles để minh họa, **không** tiết lộ access token/refresh token/ID token.

Trong production, thay `InMemoryIdentityDirectory` bằng repository có transaction/unique constraint và các phép tra cứu `findLinkedAccount(issuer, subject)`, `checkAccountStatus`, `loadLocalAuthorities`. Không cấp role dựa trên `String subject="admin"` hoặc tên hiển thị do provider cung cấp.

### 7.4. Chạy với credentials hợp lệ

Trong Bash/Git Bash:

~~~bash
export GITHUB_CLIENT_ID='your-client-id'
export GITHUB_CLIENT_SECRET='your-client-secret'
export OIDC_CLIENT_ID='your-oidc-client-id'
export OIDC_CLIENT_SECRET='your-oidc-client-secret'
export OIDC_ISSUER_URI='https://your-idp.example/issuer'

mvn spring-boot:run
~~~

Đây là **biến môi trường mẫu**: phải thay bằng giá trị thật do IdP cung cấp, đồng thời tạo callback URI đúng ở cả GitHub và OIDC provider. Trên PowerShell dùng `$env:GITHUB_CLIENT_ID='...'` và các biến tương ứng. Máy cần Java 17+ và Maven.

Mở URL sau trong browser để bắt đầu login:

~~~text
http://localhost:8080/oauth2/authorization/github
http://localhost:8080/oauth2/authorization/company
~~~

Sau khi callback thành công, mở `http://localhost:8080/me` bằng **cùng browser session**. Response minh họa (UUID và external name thực tế không cố định):

~~~json
{
  "localAccountId": "f432c5af-9770-48c3-bb5d-18ce8f6b72bd",
  "externalPrincipalName": "817263",
  "roles": ["ROLE_MEMBER"]
}
~~~

Trong một lần chạy JVM, cùng external key cho cùng local ID; đổi issuer hoặc subject tạo local ID khác. Restart demo mất dữ liệu vì directory chỉ nằm trong bộ nhớ. Trong ứng dụng thật, identity link phải sống qua restart và được chia sẻ giữa các instance.

`curl -i http://localhost:8080/me` không mang cookie phiên login có thể bị redirect tới `/login`; đây là hành vi xác thực bình thường, không phải lỗi của identity mapper.

## 8. Kiểm thử ánh xạ với JUnit 5, không cần gọi provider

Dùng test logic directory để xác nhận các bất biến về khóa và role. Test này **không khởi động Spring context**, vì thế không cần client secrets hay OIDC discovery thật để chạy `mvn test`.

**src/test/java/example/externallogin/ExternalLoginApplicationTests.java:**

~~~java
package example.externallogin;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;

import static org.assertj.core.api.Assertions.assertThat;

class ExternalLoginApplicationTests {

    @Test
    void sameExternalKeyMapsToSameLocalAccount() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var a = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "817263");
        var b = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "817263");

        assertThat(directory.resolve(a))
                .isEqualTo(directory.resolve(b));
    }

    @Test
    void identicalSubjectUnderTwoIssuersRemainsSeparate() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var a = new ExternalLoginApplication.ExternalKey(
                "oidc:https://issuer-a.example", "user-17");
        var b = new ExternalLoginApplication.ExternalKey(
                "oidc:https://issuer-b.example", "user-17");

        assertThat(directory.resolve(a))
                .isNotEqualTo(directory.resolve(b));
    }

    @Test
    void externalSubjectNamedAdminDoesNotGrantAdmin() {
        var directory =
                new ExternalLoginApplication.InMemoryIdentityDirectory();

        var external = new ExternalLoginApplication.ExternalKey(
                "oauth2:github", "admin");
        String localId = directory.resolve(external);

        assertThat(directory.localAuthorities(localId).stream()
                .map(GrantedAuthority::getAuthority)
                .toList())
                .containsExactly("ROLE_MEMBER");
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test kiểm: cùng key được resolve nhất quán, cùng `sub` khác issuer không bị gộp, chuỗi external `admin` không tạo quyền admin. Mã ví dụ có dependency JUnit/AssertJ từ `spring-boot-starter-test`; **không** nên kết luận những test này đã kiểm toàn bộ OAuth2/OIDC login.

Để kiểm trực tiếp custom user service, nên tạo delegate giả lập trả `OAuth2User`/`OidcUser` với claim mong đợi và xác minh account lookup, tình huống thiếu ID, suspended account và authority được trả. Để kiểm flow thực, cần IdP thử nghiệm/HTTP mocks, callback, session và error handling. `spring-security-test` có `oauth2Login()` và `oidcLogin()` để tạo principal trong MockMvc; các post-processor này **không tự gọi** `OAuth2UserService`/`OidcUserService` thực tế, nên một test GET 200 với chúng chưa chứng minh mapper đã chạy.

## 9. OAuth2User, OidcUser và cách giữ local identity trong principal

`OAuth2User` khai báo `getAttributes()`, `getAuthorities()`, `getName()`. `OidcUser` mở rộng dữ liệu OIDC với ID token và claims. Có ba cách thường dùng để gắn local identity:

1. **Wrapper principal** như `LinkedOAuth2User`/`LinkedOidcUser` ở ví dụ: giữ nguồn gốc profile/token và bổ sung `localAccountId()`, dễ thấy ở controller.
2. **Tùy biến attributes** ở OAuth2 không OIDC rồi trả một `DefaultOAuth2User` mới: có thể thêm `app_user_id` do server tính, nhưng cẩn thận nếu trùng tên với profile provider và cần giữ nguyên contract của principal.
3. **Tách local lookup service** khỏi principal: các request nhận external `iss/sub` hoặc registration + stable user ID, dùng service tìm local ID, có cache/persistence thích hợp. Đơn giản về principal nhưng có chi phí lookup/caching và cần chính sách session rõ.

Với OIDC, có thể tạo `DefaultOidcUser` với authorities thay đổi nhưng nó chủ yếu chứa ID token/UserInfo và name key; nếu cần local id riêng, wrapper thường dễ thể hiện ý nghĩa hơn việc biến `sub` thành local ID. Không ghi sửa claim chuẩn `sub`/`iss` hoặc thay ID token mới để tiện lập trình.

Trong môi trường serialize HTTP session hoặc distributed session, đối tượng principal custom phải được thiết kế tương thích với chiến lược session serialization, evolution và bảo mật dữ liệu. Ví dụ record giữ `OAuth2User` gốc phục vụ hiểu cơ chế; tùy stack/session store, có thể cần kiểu principal serializable chuyên biệt hoặc lưu tối thiểu local ID và tải lại profile.

## 10. Extension khác: GrantedAuthoritiesMapper và success handler

| Hook | Nên dùng khi | Điều không giải quyết được |
| --- | --- | --- |
| `OAuth2UserService` | Tải profile OAuth2, dùng provider stable id, resolve account | Không tự thay đổi luồng OIDC nếu không cấu hình đúng `oidcUserService` |
| `OidcUserService` | Dùng verified OIDC ID token/UserInfo, resolve `iss/sub` | Không bỏ qua validation issuer/audience/signature |
| `GrantedAuthoritiesMapper` | Biến đổi authorities sau khi user đã tải | Không nhất thiết có đủ ngữ cảnh để tạo/link local account an toàn |
| Authentication success handler | Redirect sau login, audit thành công, xử lý UX | Không nên dùng để bỏ qua lookup/kiểm tra trạng thái account |
| `OAuth2AuthorizedClientService` | Quản lý authorized client và access token dùng gọi API ngoài | Không thay bảng external identity links |
| `Authentication.getPrincipal()` | Truy cập principal phiên đăng nhập | `getName()` không tự động là local account ID |

Ví dụ một **mảnh Java** khi yêu cầu chỉ đổi role và đã có nguồn tin cậy để cấp quyền:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userAuthoritiesMapper(authorities -> {
            // Chỉ là ví dụ cố định; thực tế phải tra quyền nội bộ.
            return java.util.List.of(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("ROLE_MEMBER")
            );
        })
    )
);
~~~

Mapper trên không tạo link `iss/sub` với local ID. Với bài toán ánh xạ danh tính, user service và directory lookup vẫn là trọng tâm. Nếu có nhiều security chain, bảo đảm đúng chain match URL login/callback và có cấu hình `oauth2Login`; một chain khác có thể chặn hoặc thay đổi hành vi.

## 11. Tình huống thực tế cần quyết định rõ

**Đăng nhập OIDC không trả email:** Nếu `iss/sub` hợp lệ, hệ thống vẫn xác định được external identity. Email có thể là thông tin liên hệ bắt buộc theo nghiệp vụ, nhưng không nên chọn email làm fallback ID khi thiếu.

**Email đã verified, trùng với tài khoản admin:** Không tự gán admin hay merge. Chỉ link khi người dùng đã chứng minh quyền sở hữu tài khoản nội bộ hoặc qua quy trình quản trị tin cậy. `email_verified` giúp đánh giá quyền kiểm soát email tại IdP, không bảo đảm quyền sở hữu local account hiện tại.

**Đổi username/avatar:** Chỉ cập nhật thuộc tính hiển thị theo chính sách; giữ stable external key. Profile thuộc về nhà cung cấp, local account ID phải bền vững.

**Đổi issuer hoặc chuyển nhà cung cấp:** `iss/sub` có thể thay đổi. Cần migration/link được xác nhận và audit; không chuyển link theo domain email mà thiếu bằng chứng.

**Nhiều client của cùng IdP:** Một số IdP dùng pairwise subject, nên `sub` không nhất thiết giống nhau giữa các client/sector. Thiết kế khả năng liên kết có kiểm soát.

**Không có UserInfo endpoint:** OIDC có thể dùng ID token để nhận diện nếu đã có claims cần thiết. Đừng dereference `getUserInfo()` mà không kiểm tra null.

**User bị khóa nội bộ:** IdP xác thực thành công không tự mở tài khoản bị suspended. Directory phải từ chối và không cấp local roles.

**Hai login đồng thời cùng external key:** Dùng unique constraint trên `(provider_key, subject)` với transaction và xử lý lỗi duplicate an toàn; in-memory map demo không thay persistence.

**Nhà cung cấp trả groups/roles:** Chỉ map thành quyền nếu hợp đồng IdP và chính sách tenant đáng tin, có kiểm soát thay đổi. Các nhóm có thể dùng làm **input** cho quy tắc nội bộ đã xét duyệt; không nên dùng raw claim làm quyền admin.

**Đăng nhập thành công nhưng POST bị 403:** OAuth2 login dùng session và cookie trong browser; POST/PUT/DELETE vẫn có thể cần CSRF token. CSRF, OAuth2 login và authorization là các cơ chế riêng.

## 12. Debug từng giai đoạn đăng nhập

| Hiện tượng | Kiểm tra |
| --- | --- |
| `/oauth2/authorization/github` không redirect | Client registration, endpoint, selected security filter chain, client ID, cấu hình login |
| Callback lỗi `state` hoặc redirect mismatch | Callback URI, session cookie, reverse proxy forwarded headers, CSRF/state của OAuth2 flow |
| Đổi authorization code lấy token thất bại | Client secret, token endpoint, code validity, PKCE khi cần, network và policy provider |
| OIDC báo ID token invalid | Issuer, audience, JWK/signature, expiration, clock skew, nonce |
| `DefaultOAuth2UserService` không tải được profile | UserInfo URI, access token, scope, HTTP status, contract JSON |
| `OidcUserService` không tìm thấy claims | ID token/UserInfo metadata, điều kiện gọi UserInfo, issuer/sub có hợp lệ |
| Login bị custom service từ chối | Provider namespace, missing stable ID, local link, suspended local user |
| Login xong nhưng `/me` không có local ID | Principal wrapper, cookie/session, custom service có thực sự được cấu hình đúng nhánh |
| Login xong nhưng endpoint trả 403 | Local roles, `hasRole` vs `hasAuthority`, tenant/ownership policy, CSRF ở unsafe methods |
| Local id đổi sau restart | Đang dùng in-memory map; cần persistent identity link DB |

Khi debug, log `registrationId`, issuer đã xác minh, **local account ID hoặc external ID đã được xử lý theo chính sách**, tên bước xử lý và mã lỗi phù hợp. Tránh ghi nguyên access token, refresh token, ID token, authorization code, cookie và profile PII vào log. Một lỗi 403 có thể đến từ authorization, CSRF hoặc policy khác; quan sát đúng request và filter chain.

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao `iss/sub` tốt hơn `sub` đơn lẻ cho OIDC?  
Vì subject chỉ có ý nghĩa trong phạm vi issuer, nhiều issuer có thể phát cùng chuỗi `sub`.

**2.** GitHub `login` đổi nhưng `id` giữ nguyên, có cần tạo local account mới không?  
Không, khi đã map theo namespace GitHub và stable provider user ID.

**3.** Chỉ custom `OAuth2UserService`, đăng nhập OIDC vẫn hiện profile mặc định. Vì sao?  
OIDC dùng nhánh `OidcUserService` trong `userInfoEndpoint`; cần tùy biến đúng nhánh.

**4.** `OidcUser.getUserInfo()` là null, nhưng ID token đã xác minh có `iss/sub`. Có thể tra cứu local link không?  
Có, vì khóa chuẩn OIDC đến từ ID token; UserInfo có thể vắng.

**5.** External claim `"groups": ["admins"]` có tự cho phép `hasRole("ADMIN")` không?  
Không; cần chính sách và nguồn quyền đáng tin, không tự nâng quyền từ profile.

**6.** Email provider đã verified và trùng email tài khoản hiện hữu có đủ để auto-link không?  
Không. Liên kết yêu cầu bằng chứng đã được quy trình chấp nhận và kiểm tra quyền sở hữu local account.

**7.** Test `MockMvc.with(oidcLogin())` thành công có chứng minh `OidcUserService.loadUser` đã gọi không?  
Không; test helper thường đưa principal vào request mà không chạy toàn bộ login redirect/token exchange.

**8.** Tại sao không dùng access token làm local account ID?  
Access token dùng cấp quyền gọi resource, thay đổi theo thời hạn/refresh và không phải khóa danh tính ổn định.

**9.** Hai request cùng provider/subject đăng nhập đồng thời mà tạo hai local account khác nhau. Cách sửa?  
Thiết kế persistent store với unique constraint, transaction và xử lý cạnh tranh; không dùng kiểm tra tồn tại đơn giản rồi insert rời rạc.

## 14. Ghi nhớ và checklist triển khai

- Dùng `OAuth2UserService<OAuth2UserRequest, OAuth2User>` cho OAuth2 login **không OIDC** và `OAuth2UserService<OidcUserRequest, OidcUser>`/ `OidcUserService` cho OIDC; đăng ký đúng với `oauth2Login().userInfoEndpoint()`.
- Delegate về `DefaultOAuth2UserService` hoặc `OidcUserService` để giữ xử lý chuẩn, đừng tự bỏ validation OIDC.
- OAuth2 không OIDC: dùng **provider namespace + stable provider-specific user ID**. OIDC: dùng **verified issuer + subject** từ ID token.
- Ánh xạ sang **local account ID bền vững** với unique external link và quy trình signup/link/unlink có kiểm soát. Email và username phục vụ profile, không tự quyết định account linking.
- Role nội bộ lấy từ chính sách quyền đáng tin; kiểm tra local status và tenant. Không nhầm `SCOPE_` với `ROLE_` hoặc tự nâng quyền từ claim ngoài.
- Giữ principal có thể truy cập local account ID, bảo vệ token và dữ liệu cá nhân, kiểm thử cả missing claims, multi-issuer, disabled users, cạnh tranh, session/callback và tương tác thực với IdP.
- Mẫu `ConcurrentHashMap` chỉ dùng học cơ chế; hệ thống thật dùng database, transaction, audit và bảo vệ account takeover.

**Kết luận:** IdP và Spring Security xác minh **danh tính bên ngoài**; `OAuth2UserService`/`OidcUserService` là điểm mở rộng để ánh xạ danh tính ấy sang **tài khoản và quyền nội bộ** mà ứng dụng kiểm soát.
