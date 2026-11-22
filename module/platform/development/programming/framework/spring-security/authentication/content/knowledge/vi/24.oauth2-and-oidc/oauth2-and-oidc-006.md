# OAuth2UserService, OidcUserService và tiếp nhận dữ liệu người dùng trong Spring Security

## 1. Mục tiêu

Khi đăng nhập qua GitHub, Google hoặc một OpenID Provider của doanh nghiệp, ứng dụng Spring Security thường cần **lấy dữ liệu người dùng từ hệ thống bên ngoài**, xác định tài khoản nội bộ tương ứng rồi gán quyền truy cập phù hợp. Hai điểm mở rộng quan trọng trong **OAuth2 Login ở Servlet stack** là:

- `OAuth2UserService<OAuth2UserRequest, OAuth2User>`: nạp thông tin người dùng trong luồng đăng nhập OAuth 2.0 không dùng OIDC.
- `OAuth2UserService<OidcUserRequest, OidcUser>`: nạp và điều chỉnh người dùng OpenID Connect (OIDC), thường bằng `OidcUserService`.

Hiểu các lớp này giúp bạn tùy biến dữ liệu profile, liên kết external identity với account nội bộ, từ chối người dùng chưa được cấp quyền và đưa `GrantedAuthority` phù hợp vào `Authentication`. Bài này tập trung vào **đăng nhập tương tác bằng `oauth2Login()`**, không thay thế quy trình kiểm tra Bearer access token của Resource Server.

**Điểm cốt lõi:** `OAuth2UserService` và `OidcUserService` **không tự xác minh mật khẩu người dùng**; chúng được gọi trong quy trình đã trao đổi authorization code/token với nhà cung cấp. Không coi một trường email hoặc tên hiển thị do provider trả về là khóa tài khoản vĩnh viễn.

## 2. Bối cảnh: từ authorization code đến principal của ứng dụng

### 2.1. OAuth 2.0 và OIDC không giống nhau

OAuth 2.0 chủ yếu là **giao thức ủy quyền** cho client lấy token để gọi resource được bảo vệ. Spring Security hỗ trợ đăng nhập qua OAuth 2.0 provider có UserInfo endpoint hoặc API profile. OIDC mở rộng OAuth 2.0 bằng lớp **xác thực danh tính**, bao gồm `ID Token` mang các claim chuẩn.

| Khía cạnh | OAuth2 Login thông thường | OpenID Connect Login |
|---|---|---|
| Client registration | Không có scope `openid` | Có scope `openid` |
| Dịch vụ nạp user mặc định | `DefaultOAuth2UserService` | `OidcUserService` |
| Kiểu request | `OAuth2UserRequest` | `OidcUserRequest` (bao gồm ID Token) |
| Kiểu principal | `OAuth2User` | `OidcUser` (cũng là `OAuth2User`) |
| Nguồn identity/profile | UserInfo hoặc API người dùng của provider | ID Token; UserInfo bổ sung nếu được gọi/trả về |
| Khóa identity gợi ý | Provider/registration + ID ổn định theo provider | **`iss` + `sub`** |
| Trường tên hiển thị | Provider-specific: `login`, `name`, ... | `name`, `preferred_username`, ... |
| Lý do không dùng email làm khóa | Email có thể thiếu, đổi, bị tái sử dụng | Email có thể đổi; OIDC dùng `sub` ổn định trong issuer |

Scope `openid` trong cấu hình client khiến Spring Security chọn thành phần dành cho OIDC (như `OidcUserService`); không thể chuyển một OAuth2 provider thường thành OIDC chỉ bằng cách ép kiểu `OAuth2User`.

### 2.2. Luồng đăng nhập ở mức ứng dụng

~~~text
Browser
   |
   | GET /oauth2/authorization/{registrationId}
   v
Spring Security OAuth2 Authorization Request
   |
   | Redirect tới Authorization Server / OpenID Provider
   | User đăng nhập / đồng ý quyền tại provider
   v
GET /login/oauth2/code/{registrationId}?code=...&state=...
   |
   v
Spring Security: kiểm tra state + đổi code lấy token
   |
   +---------------- OAuth2 thường ----------------+
   |                                               |
   | DefaultOAuth2UserService.loadUser(...)         |
   |   dùng access token gọi UserInfo/API profile    |
   |   → OAuth2User(attributes, authorities)         |
   |                                               |
   +---------------- OIDC --------------------------+
   |                                               |
   | Xử lý và xác minh ID Token theo OIDC            |
   | OidcUserService.loadUser(...)                   |
   |   ID Token (+ UserInfo khi phù hợp)              |
   |   → OidcUser(idToken, userInfo, authorities)     |
   |                                               |
   +------------------+----------------------------+
                      |
                      v
           Custom UserService delegate / mapper
            - tra cứu external identity
            - xác định account nội bộ
            - kiểm tra blocked/disabled
            - nạp quyền ứng dụng
                      |
                      v
          OAuth2AuthenticationToken / SecurityContext
                      |
                      v
         authorizeHttpRequests / controller / session
~~~

`OAuth2LoginAuthenticationFilter` hoàn tất quá trình xây dựng authentication và lưu trạng thái đăng nhập theo cấu hình. Một request đã có session hợp lệ **không nhất thiết gọi lại UserService**: cần thiết kế riêng việc cập nhật quyền, khóa tài khoản nội bộ và phiên cũ.

### 2.3. Ranh giới với Resource Server

- `http.oauth2Login(...)`: ứng dụng là **OAuth2 Client** phục vụ người dùng đăng nhập trình duyệt; có `OAuth2UserService` / `OidcUserService`.
- `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`: ứng dụng xác thực **Bearer access token** gửi tới API; dữ liệu chủ yếu ở `Jwt`, `JwtAuthenticationConverter` hoặc opaque token introspection. Không dùng `OAuth2UserService` để thay thế kiểm tra JWT.
- Một ứng dụng có thể có cả hai, nhưng cần xác định security chain, session, endpoint và token audience riêng.

## 3. `OAuth2UserService`: lấy dữ liệu người dùng của OAuth2 thông thường

Interface chính trong Spring Security:

~~~java
public interface OAuth2UserService<R extends OAuth2UserRequest,
                                   U extends OAuth2User> {
    U loadUser(R userRequest) throws OAuth2AuthenticationException;
}
~~~

Ý nghĩa:
- `OAuth2UserRequest` cho phép lấy `ClientRegistration` và `OAuth2AccessToken` vừa nhận; dùng để biết provider nào đang đăng nhập và token nào có thể gọi endpoint thuộc provider đó.
- `DefaultOAuth2UserService` gọi UserInfo endpoint của provider bằng access token, đọc attributes và trả `OAuth2User`.
- `OAuth2User.getAttributes()` là `Map<String,Object>` có cấu trúc **không đồng nhất** giữa provider. Trường tên, avatar, email, id có thể khác hoặc thiếu.
- `OAuth2User.getName()` dựa trên `userNameAttributeName` của provider (ví dụ `id` đối với GitHub). Đây là định danh do provider trả về, **chưa phải internal user ID**.
- `OAuth2User.getAuthorities()` chứa authorities từ Spring/provider, thường gồm `OAuth2UserAuthority`, `OAUTH2_USER` và scope authorities như `SCOPE_read:user` theo cấu hình/thời điểm. Scope cho phép gọi API không đồng nghĩa với role nghiệp vụ `ROLE_ADMIN`.

**Điều kiện:** Provider không có ID Token phải có cách tin cậy để lấy thông tin và khóa người dùng từ endpoint/API đã cấu hình. Nếu không có thuộc tính name được khai báo đúng hoặc response UserInfo sai định dạng, dịch vụ có thể lỗi xác thực.

### Ví dụ dữ liệu từ một provider không dùng OIDC

~~~json
{
  "id": 123456,
  "login": "alice-dev",
  "name": "Alice Nguyen",
  "email": null,
  "avatar_url": "https://images.example.org/u/123456.png"
}
~~~

Ở đây `id` đáng tin cậy hơn `login` để liên kết account nếu provider cam kết id ổn định. `email=null` hoàn toàn có thể hợp lệ khi provider không công khai email. Không yêu cầu mọi provider phải có `email`.

## 4. `OidcUserService`: kết hợp ID Token và UserInfo đúng ngữ nghĩa

`OidcUserService` triển khai `OAuth2UserService<OidcUserRequest, OidcUser>`. `OidcUserRequest` chứa thông tin client, access token và `OidcIdToken`; `OidcUser` mở rộng `OAuth2User`, có:

- `getIdToken()`: ID Token đã được xử lý/xác minh bởi luồng OIDC trước khi cung cấp cho service.
- `getUserInfo()`: thông tin bổ sung từ UserInfo **nếu có**; có thể không được truy xuất/trả về trong một số luồng/provider.
- `getClaims()` / `getAttributes()`: dữ liệu tổng hợp, có thể gồm `sub`, `name`, `email`, `email_verified`, v.v.
- `getSubject()`: giá trị `sub` của danh tính đã đăng nhập.

**OIDC khóa danh tính bằng cặp `(iss, sub)`**:
- `iss` = issuer của OpenID Provider, ví dụ `https://idp.example.org`.
- `sub` = Subject identifier trong namespace issuer đó.
- `email`, `preferred_username`, `name` là **thông tin profile**, không phải khóa chính vĩnh viễn.

Ví dụ ID Token đã được xác minh:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "user-001",
  "aud": "client-123",
  "exp": 1893456000,
  "iat": 1893452400,
  "name": "Alice Nguyen",
  "email": "alice@example.org",
  "email_verified": true
}
~~~

Số `exp`/`iat` chỉ minh họa dữ liệu token, **không phải token dùng để thử đăng nhập**. Thực tế cần xác thực chữ ký, key, issuer, audience, thời gian, nonce và ràng buộc luồng theo chuẩn; để Spring Security xử lý đầy đủ, không tự tin một JSON chưa kiểm chứng.

### UserInfo có cùng `sub`

OIDC yêu cầu UserInfo Response chứa `sub`. Nếu gọi UserInfo, **`sub` của UserInfo phải bằng `sub` của ID Token** trước khi chấp nhận claims UserInfo, nhằm chống token substitution. `OidcUserService` mặc định đảm nhận xử lý thông thường của Spring; custom service nên delegate trước rồi mới lấy dữ liệu, không tự bỏ qua kiểm tra này.

~~~json
{
  "sub": "user-001",
  "name": "Alice Nguyen",
  "picture": "https://images.example.org/u/user-001.png",
  "locale": "vi"
}
~~~

UserInfo chỉ cung cấp claims tùy theo scopes/consent/provider. **Không giả định `getUserInfo()` luôn khác null**. Nếu có dữ liệu profile từ nhiều nguồn, xác định chính sách chọn nguồn phù hợp; không ghi đè khóa danh tính `iss`/`sub` bằng email hoặc trường hiển thị.

## 5. So sánh và chọn điểm mở rộng

| Nhu cầu | Điểm mở rộng | Ghi chú |
|---|---|---|
| OAuth2 thông thường: lấy UserInfo | `DefaultOAuth2UserService` | Thường đủ với provider phổ biến |
| OAuth2: đổi headers/REST khi gọi UserInfo | `setRequestEntityConverter(...)`, `setRestOperations(...)` | Cấu hình an toàn token/TLS/error handling |
| OAuth2: chỉnh thuộc tính, liên kết account, cấp role | Delegate `OAuth2UserService<OAuth2UserRequest, OAuth2User>` | Trả lại `OAuth2User` hợp lệ |
| OIDC: xử lý profile từ ID Token/UserInfo | Delegate `OidcUserService` | Giữ nguyên `OidcIdToken` và `OidcUserInfo` |
| OIDC: tùy biến cách gọi UserInfo | `OidcUserService.setOauth2UserService(...)` | Truyền một OAuth2UserService làm delegate UserInfo |
| Chỉ map `GrantedAuthority` sau khi load user | `GrantedAuthoritiesMapper` | Nhẹ hơn nếu không cần access token và side effects |
| API nhận Bearer JWT | `JwtAuthenticationConverter` hoặc Resource Server | Không phải OAuth2 Login UserService |

Hai `userService(...)` và `oidcUserService(...)` được cấu hình tại `http.oauth2Login(oauth2 -> oauth2.userInfoEndpoint(...))`. Chúng **không hoán đổi generic type** cho nhau. Một app nhiều provider có thể cấu hình đồng thời hai chiến lược.

## 6. Nhận dữ liệu ngoài và ánh xạ vào domain nội bộ

### 6.1. Chỉ lấy dữ liệu tối thiểu cần thiết

Một bản ghi account có thể có các trường:

| Trường trong hệ thống | Nguồn/chiến lược | Lưu ý |
|---|---|---|
| `user_id` | ID nội bộ do DB phát hành | Độc lập với provider |
| `provider_type` | `oauth2` / `oidc` | Giúp tách namespace |
| `provider_id` | `registrationId` OAuth2 hoặc `iss` OIDC | OIDC ưu tiên issuer đã được xác thực |
| `provider_subject` | Stable user id của OAuth2 provider hoặc `sub` OIDC | Không dùng email |
| `display_name` | Claim `name` / `login` | Có thể thiếu/thay đổi |
| `email` | Provider claims nếu cần | Không tự coi là đã verified |
| `email_verified` | OIDC claim khi có | Không phải chứng cứ quyền sở hữu toàn bộ tài khoản |
| `avatar_url` | `picture` / `avatar_url` | Chỉ hiển thị qua chính sách URL an toàn |
| `account_status` | DB ứng dụng | `active`, `disabled`, `pending` theo business |
| `roles` | RBAC trong ứng dụng | Không suy role từ email/domain hiển thị |

Thiết kế liên kết:

~~~text
external_identity(
  provider_type,
  provider_id,
  provider_subject,
  internal_user_id,
  linked_at,
  last_login_at
)
UNIQUE(provider_type, provider_id, provider_subject)
~~~

Ràng buộc unique và transaction ngăn hai request login đồng thời tạo hai liên kết cho một external identity. Có thể cho một user nội bộ liên kết nhiều provider, nhưng quá trình **link account** phải được chứng thực rõ ràng (ví dụ user đã đăng nhập nội bộ rồi xác minh provider thứ hai).

### 6.2. Pipeline nhận dữ liệu an toàn

1. **Provider authentication hoàn tất**: để Spring xử lý code/token, OIDC ID Token, state và các kiểm tra giao thức.
2. **Delegate load user**: gọi `DefaultOAuth2UserService.loadUser` hoặc `OidcUserService.loadUser` thay vì tự nhận JSON bất kỳ.
3. **Định danh ổn định**: OAuth2 lấy provider-specific stable ID từ `OAuth2User.getName()` theo `userNameAttributeName`; OIDC lấy `iss` + `sub`.
4. **Tra cứu/link account**: tìm external identity theo khóa composite. Chính sách có thể yêu cầu user đã liên kết, hoặc JIT provisioning có điều kiện.
5. **Kiểm tra nội bộ**: account không bị disable/blocked, tenant hợp lệ, account mapping rõ ràng, có quyền vào ứng dụng.
6. **Cập nhật profile có kiểm soát**: chỉ ghi các trường allowlist, bảo vệ dữ liệu do user quản lý; quản lý conflict, missing/null, PII retention.
7. **Tạo authorities**: lấy từ RBAC/roles ứng dụng hoặc nhóm/claim đã kiểm chứng theo mapping đã duyệt.
8. **Trả principal**: tạo `DefaultOAuth2User` hoặc `DefaultOidcUser` mới với authorities phù hợp; Spring hoàn thiện `Authentication`.

### 6.3. Vì sao không link tự động chỉ bằng email?

Ví dụ hai nguồn đều trả `email=alice@example.org`. Điều đó chưa chứng minh chúng là cùng một identity; email có thể bị thay đổi, tái sử dụng, không xác minh, hoặc nằm trong tenant khác. Nếu tự gộp bằng email, người đăng nhập qua provider thứ hai có thể chiếm quyền account nội bộ đã tạo qua provider thứ nhất.

Với OIDC, `email_verified=true` có thể là **một điều kiện** trong quy trình linking do sản phẩm định nghĩa, nhưng không thay thế cơ chế xác nhận liên kết đang được chủ account phê duyệt. Luôn dùng `iss+sub` khi nhận diện một identity OIDC cụ thể.

### 6.4. Phân biệt quyền OAuth2 scope và quyền của ứng dụng

`SCOPE_read:user` nói access token có thể dùng cho quyền truy cập API tương ứng của provider. Nó **không đồng nghĩa** `ROLE_USER`, `ROLE_SUPPORT` hay `ROLE_ADMIN` trong hệ thống.

Ví dụ:
- Provider trả `SCOPE_email`, `SCOPE_profile`.
- App tìm account nội bộ có trạng thái active và role `ROLE_VIEWER`.
- `authorizeHttpRequests(...hasRole("VIEWER"))` kiểm tra **role nội bộ**.
- App không tự suy `ROLE_ADMIN` từ text `admin` trong email hoặc from scope không được design cho authorization nội bộ.

## 7. Ví dụ Spring Boot 3.x + Spring Security 6.x + Java 17

Đây là **ví dụ Maven Spring Boot Servlet** cấu hình hai nhánh OAuth2 thường và OIDC. Nó dùng một allowlist account nhỏ trong bộ nhớ để minh họa **chỉ user đã liên kết mới được đăng nhập**. Các ID/issuer trong allowlist chỉ là dữ liệu minh họa; khi chạy với provider thật phải thay bằng bản ghi đã được liên kết hoặc DB production.

### 7.1. Dependencies

Trong `pom.xml` đã khai báo Spring Boot parent/BOM phù hợp:

~~~xml
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
~~~

`spring-boot-starter-oauth2-client` mang các lớp `OAuth2UserService`, `OidcUserService` và hỗ trợ `oauth2Login`. Không cần tự khai báo `spring-security-oauth2-client` version lệch với BOM.

### 7.2. `application.yml`: một OAuth2 provider và một OIDC provider

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
          corp:
            provider: corp
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: https://idp.example.org
~~~

- `github`: OAuth2 thường; Spring có preset GitHub, `DefaultOAuth2UserService` xử lý UserInfo; principal name mặc định là thuộc tính provider-specific.
- `corp`: OIDC nếu issuer thật hỗ trợ discovery và scope `openid`; Spring cấu hình OIDC UserService.
- `issuer-uri` là issuer **chính xác** nhà cung cấp công bố; không tự đặt URL tùy ý trong hệ thống thật.
- Redirect URI cần được allowlist chính xác trong IdP/provider. App phía sau reverse proxy phải cấu hình base URL/forwarded headers an toàn.
- Credentials đến từ secrets manager/environment. Không đưa `client-secret` thật vào Git hoặc log.

### 7.3. `DemoApplication.java`

File `src/main/java/com/example/login/DemoApplication.java`:

~~~java
package com.example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. `AccountLinkService.java`: ví dụ liên kết tài khoản và cấp role

File `src/main/java/com/example/login/AccountLinkService.java`:

~~~java
package com.example.login;

import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.stereotype.Service;

@Service
public class AccountLinkService {

    // Dữ liệu DEMO. Production dùng DB có unique constraint
    // theo (provider type, provider ID/issuer, stable subject).
    private final Map<ExternalKey, Set<String>> allowed = Map.of(
            new ExternalKey("oauth2:github", "123456"),
                    Set.of("ROLE_VIEWER"),
            new ExternalKey("oidc:https://idp.example.org", "user-001"),
                    Set.of("ROLE_VIEWER")
    );

    public Collection<? extends GrantedAuthority> authoritiesFor(
            String source, String externalSubject) {

        if (source == null || source.isBlank()
                || externalSubject == null || externalSubject.isBlank()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_external_identity"));
        }

        Set<String> roles = allowed.get(
                new ExternalKey(source, externalSubject));

        if (roles == null || roles.isEmpty()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("account_not_linked"));
        }

        return roles.stream()
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toUnmodifiableSet());
    }

    private record ExternalKey(String source, String subject) {
    }
}
~~~

Các ID trong `allowed` là fixture minh họa. Trong thực tế, lớp này:
- tra cứu external identity bằng khóa duy nhất;
- kiểm tra trạng thái account và tenant;
- trả roles/permissions do **ứng dụng quản lý**;
- nếu không có liên kết thì từ chối hoặc thực hiện provisioning theo **chính sách rõ ràng**, không tự ghép email;
- chạy trong transaction khi sửa DB, với unique constraint và xử lý race.

Trả `OAuth2AuthenticationException` giúp luồng login xem đây là lỗi xác thực. Đừng cho frontend thấy thông tin nhạy cảm về account tồn tại/đã bị khóa; log an toàn để vận hành.

### 7.5. `SecurityConfiguration.java`: delegate hai UserService

File `src/main/java/com/example/login/SecurityConfiguration.java`:

~~~java
package com.example.login;

import java.util.LinkedHashSet;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountLinkService links) throws Exception {

        DefaultOAuth2UserService oauth2Delegate =
                new DefaultOAuth2UserService();
        OidcUserService oidcDelegate = new OidcUserService();

        OAuth2UserService<OAuth2UserRequest, OAuth2User> oauth2Users =
                request -> {
                    OAuth2User user = oauth2Delegate.loadUser(request);

                    String registrationId = request
                            .getClientRegistration().getRegistrationId();
                    String externalSubject = user.getName();
                    String nameKey = request.getClientRegistration()
                            .getProviderDetails()
                            .getUserInfoEndpoint()
                            .getUserNameAttributeName();

                    if (nameKey == null || nameKey.isBlank()) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error("missing_name_attribute"));
                    }

                    var authorities =
                            new LinkedHashSet<GrantedAuthority>(
                                    user.getAuthorities());
                    authorities.addAll(links.authoritiesFor(
                            "oauth2:" + registrationId, externalSubject));

                    return new DefaultOAuth2User(
                            authorities, user.getAttributes(), nameKey);
                };

        OAuth2UserService<OidcUserRequest, OidcUser> oidcUsers =
                request -> {
                    OidcUser user = oidcDelegate.loadUser(request);

                    String issuer = Objects.toString(
                            user.getIdToken().getClaims().get("iss"), "");
                    String subject = user.getSubject();

                    if (user.getUserInfo() != null &&
                            !Objects.equals(
                                    subject,
                                    user.getUserInfo()
                                            .getClaims().get("sub"))) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error("userinfo_sub_mismatch"));
                    }

                    var authorities =
                            new LinkedHashSet<GrantedAuthority>(
                                    user.getAuthorities());
                    authorities.addAll(links.authoritiesFor(
                            "oidc:" + issuer, subject));

                    return new DefaultOidcUser(
                            authorities,
                            user.getIdToken(),
                            user.getUserInfo(),
                            "sub");
                };

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().hasRole("VIEWER"))
                .oauth2Login(oauth2 -> oauth2
                        .userInfoEndpoint(userInfo -> userInfo
                                .userService(oauth2Users)
                                .oidcUserService(oidcUsers)))
                .build();
    }
}
~~~

**Phân tích từng điểm:**

1. **Delegate trước:** cả hai hàm `loadUser` mặc định xử lý việc lấy và tạo principal cho provider. Custom code chỉ chạy tiếp khi bước đó thành công; không tự nhận JSON từ browser làm người dùng.
2. **OAuth2 stable name:** lấy `externalSubject=user.getName()`, nhưng phải cấu hình `userNameAttributeName` đúng cho provider. Không áp dụng mặc định này cho mọi API tùy biến mà chưa xem tài liệu.
3. **OIDC identity:** `issuer` lấy từ claim `iss` của ID Token; `subject` là `sub`. Cặp này dùng tra cứu external identity. Việc kiểm tra UserInfo `sub` bảo vệ thêm với trường hợp provider có UserInfo.
4. **Account allowlist:** `links.authoritiesFor(...)` chỉ cấp quyền cho danh tính được liên kết; lỗi thì login fail. Mẫu demo không tự tạo account mới, nên không sinh role cho danh tính chưa biết.
5. **Trả đúng kiểu:** OAuth2 branch trả `DefaultOAuth2User` với attributes/name attribute; OIDC branch trả `DefaultOidcUser` giữ ID Token và UserInfo.
6. **Giữ authorities sẵn có:** `LinkedHashSet` giữ authority hiện có của provider (`OAUTH2_USER`, `OIDC_USER`, `SCOPE_...`) rồi thêm role nội bộ `ROLE_VIEWER`. Không chuyển scope thành role admin.
7. **Authorization:** `hasRole("VIEWER")` kiểm tra `ROLE_VIEWER`; thay bằng rule chi tiết theo route trong ứng dụng thật.
8. **Session/CSRF:** giữ defaults Spring Security cho web login. Nếu thay đổi session, CSRF, cookie, proxy hoặc CORS, phải phân tích riêng theo kiến trúc; không vô hiệu hóa bảo vệ chỉ để làm demo chạy.

Trong demo, `https://idp.example.org` và user ID chỉ minh họa, nên đăng nhập thật phụ thuộc cấu hình IdP và account mapping tương ứng. Đây là **mã nguồn của một dự án Maven**, không chạy riêng bằng một lệnh `javac SecurityConfiguration.java` thiếu dependency.

### 7.6. Endpoint xem principal đã nhận

File `src/main/java/com/example/login/WhoAmIController.java`:

~~~java
package com.example.login;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication auth) {
        return Map.of(
                "principalName", auth.getName(),
                "roleViewer", auth.getAuthorities().stream()
                        .anyMatch(a -> "ROLE_VIEWER"
                                .equals(a.getAuthority())));
    }
}
~~~

Nếu tài khoản đã liên kết đăng nhập thành công, phản hồi có dạng:

~~~json
{
  "principalName": "user-001",
  "roleViewer": true
}
~~~

Với GitHub, `principalName` là ID provider (ví dụ `123456`), còn OIDC là `sub`. Thứ tự key JSON không bảo đảm. Endpoint tránh trả trực tiếp toàn bộ `getAttributes()`, ID Token, access token và claim cá nhân ra client.

Chạy dự án đã khai báo Spring Boot parent/BOM và provider thật bằng `mvn spring-boot:run` hoặc `mvn package` rồi `java -jar target/<ten-jar>.jar`. URL bắt đầu login thường là `/oauth2/authorization/github` hoặc `/oauth2/authorization/corp`; callback mặc định `/login/oauth2/code/{registrationId}`.

## 8. Khi nào tùy biến `DefaultOAuth2UserService` / `OidcUserService`?

### 8.1. Chỉ bổ sung role: cân nhắc `GrantedAuthoritiesMapper`

Nếu chỉ chuyển các authorities đã có thành authorities ứng dụng và không cần gọi thêm API hay cập nhật DB, có thể dùng:

~~~java
.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo -> userInfo
                .userAuthoritiesMapper(authorities -> {
                    // Ví dụ giữ nguyên authorities.
                    return authorities;
                })))
~~~

Đây là **đoạn cấu hình đặt bên trong `HttpSecurity`**, không phải file Java độc lập; cần kiểm tra chính sách mapping trước khi thay `authorities` bằng role khác. `GrantedAuthoritiesMapper` nhận `OAuth2UserAuthority` hoặc `OidcUserAuthority`, nhưng không nhận `OAuth2UserRequest` và access token theo cách UserService nhận; nếu phải gọi protected API để nạp nhóm, delegate UserService thường phù hợp hơn.

### 8.2. Tùy biến request UserInfo cho OAuth2

`DefaultOAuth2UserService` có:
- `setRequestEntityConverter(...)` để thay đổi cách tạo HTTP request tới UserInfo;
- `setRestOperations(...)` để dùng một `RestOperations` đã cấu hình timeout/error handling.

Phải giữ cơ chế gửi bearer access token và tin cậy TLS; không vô tình đưa token vào query string, redirect không tin cậy hoặc log.

### 8.3. Tùy biến cách OIDC gọi UserInfo

Nếu cần thay riêng cách OIDC lấy UserInfo mà vẫn giữ quy trình xác minh ID Token và tạo OIDC principal, sử dụng:

~~~java
DefaultOAuth2UserService userInfoLoader =
        new DefaultOAuth2UserService();

OidcUserService oidcService = new OidcUserService();
oidcService.setOauth2UserService(userInfoLoader);
~~~

Đây là đoạn minh họa các API cần import từ `org.springframework.security.oauth2.client.userinfo` và `...client.oidc.userinfo`. Để hoạt động thực tế phải đăng ký `oidcService` ở `.userInfoEndpoint(...).oidcUserService(oidcService)`. Một `OAuth2UserService` tùy biến được truyền vào `setOauth2UserService` là service để nạp **UserInfo** trong OIDC, không phải thay thế mọi kiểm tra của OIDC login.

## 9. Quy tắc quan trọng khi cập nhật thông tin người dùng

### 9.1. Phân loại trường dữ liệu

- **Identity key:** OIDC `iss+sub`, OAuth2 provider registration + stable provider ID. Thường bất biến với một liên kết; nếu provider thay đổi định danh, áp dụng thủ tục migration/linking được chứng thực.
- **Profile mutable:** `name`, `picture`, `locale`, `nickname`, email. Lưu theo chủ đích, chỉ đồng bộ nếu nguồn được đánh dấu là authoritative và user đồng ý theo chính sách.
- **Trusted authorization data:** roles từ DB ứng dụng, hoặc verified groups/claims theo contract đã phê duyệt. Một chuỗi tùy ý trong response không mặc nhiên được thành `ROLE_ADMIN`.
- **Secrets/tokens:** access token, refresh token, ID Token. Dùng Spring `OAuth2AuthorizedClient` / storage bảo mật khi cần gọi API; không lưu vào cột profile hoặc trả trong JSON thông thường.

### 9.2. JIT provisioning và linking

Có hai chính sách phổ biến:

**Linked-only:** chỉ chấp nhận identity đã được liên kết với user nội bộ. Chống tài khoản tự xuất hiện, phù hợp doanh nghiệp/ứng dụng nội bộ.

**Just-in-time provisioning:** sau khi IdP xác thực, tự tạo internal user nếu thuộc tenant/danh sách tổ chức cho phép. Cần quy tắc chặt về `iss`, `sub`, `email_verified`, người dùng bị cấm, transaction, unique constraint, rate limit, và xử lý race. Không provision `ROLE_ADMIN` theo chuỗi display name/email domain. Nếu IdP trả email chưa verified, không dùng email đó để claim ownership account đã tồn tại.

Khi cập nhật profile, không ghi đè `account_status`, `local_roles`, trường nội bộ user đã tự xác minh hoặc các thuộc tính quan trọng từ nguồn thiếu độ tin cậy. Nếu provider trả `null`, chỉ xóa giá trị lưu khi chính sách thực sự yêu cầu, không xóa vô điều kiện.

### 9.3. Bối cảnh đa tenant

Một identity `sub="user-001"` dưới issuer A không phải cùng người với `sub="user-001"` dưới issuer B. Với tenant nhiều tổ chức, kiểm tra `iss`/tenant chính xác, danh sách issuer được chấp thuận, audit account linking và xử lý đổi tenant theo chính sách. Tránh khóa toàn cục chỉ là `sub`.

### 9.4. Cache, session và quyền hết hiệu lực

`OAuth2UserService` thường chạy ở thời điểm đăng nhập, không chạy lại mỗi lần `GET /me`. Nếu admin khóa account hoặc thu hồi vai trò, phiên đang hoạt động có thể còn authorities cũ. Tùy yêu cầu, áp dụng một hoặc nhiều biện pháp: session invalidation, reauthentication, kiểm tra quyền từ DB ở endpoint nhạy cảm, giới hạn tuổi phiên, hoặc xử lý sự kiện thay đổi quyền. Không giả định cập nhật user trong DB sẽ lập tức làm `Authentication` trong session thay đổi.

## 10. Lỗi phổ biến

1. **Đăng nhập OIDC nhưng cấu hình `.userService(...)` thay vì `.oidcUserService(...)`:** nhánh OIDC không sử dụng mapper OAuth2 thường như dự tính. Kiểm tra scope `openid` và cấu hình đúng cả hai dịch vụ nếu có hai loại provider.
2. **Dùng email làm ID duy nhất:** email đổi/không verified/không unique trên hệ thống nhiều IdP. Dùng `iss+sub` với OIDC, ID provider ổn định với OAuth2.
3. **`DefaultOAuth2User` báo thiếu name attribute:** `userNameAttributeName` không tồn tại trong UserInfo. Kiểm tra provider schema và `spring.security.oauth2.client.provider.*.user-name-attribute`.
4. **OIDC `getUserInfo() == null` gây NPE:** không phải mọi login đều có UserInfo; dùng ID Token làm nguồn identity, kiểm tra null trước khi đọc profile.
5. **`OidcUser` bị biến thành `DefaultOAuth2User`:** làm mất API `getIdToken()`, `getUserInfo()` và ngữ nghĩa OIDC. Khi thay authorities OIDC, tạo `DefaultOidcUser`.
6. **Gán ROLE_ADMIN từ `email`, `preferred_username`, custom header hoặc scope:** thiếu kiểm soát phân quyền; map từ nguồn được xác minh theo chính sách app.
7. **Lỗi 403 sau login:** đăng nhập thành công nhưng `GrantedAuthority` không khớp `hasRole/hasAuthority`; `hasRole("VIEWER")` kiểm tra `ROLE_VIEWER`.
8. **UserInfo trả `sub` khác ID Token:** phải từ chối dùng UserInfo, không tiếp tục gộp claims.
9. **Tự gọi UserInfo bằng token truyền từ browser:** bỏ qua kiểm chứng/đường tin cậy của OAuth2 Login; gọi qua `DefaultOAuth2UserService` hoặc client tin cậy với token Spring quản lý.
10. **JIT provisioning tạo hai account vì race:** cần unique constraint + transaction/idempotency + xử lý trùng lặp.
11. **Dữ liệu profile ghi đè quyền/trạng thái nội bộ:** tách allowlist trường được sync với field domain không thể do IdP profile sửa.
12. **Log toàn bộ `OidcUser`/`Authentication`:** có nguy cơ lộ thông tin cá nhân và claim; redact logs, đừng trả ID Token/access token vào controller.
13. **Tùy biến `RestOperations` phá TLS hoặc lỗi bearer token:** phải giữ security controls và đặt timeout; tránh chuyển token sang URL.
14. **Không có client registration hoặc redirect URI sai:** lỗi có thể xảy ra **trước khi UserService được gọi**; kiểm tra issuer discovery, client credentials, scopes, callback và reverse proxy configuration.
15. **Kỳ vọng update roles tức thời:** `Authentication` có thể được giữ trong session; áp dụng policy refresh/invalidations.
16. **Dùng ví dụ của Servlet cho WebFlux:** WebFlux có `ReactiveOAuth2UserService` và cấu hình `ServerHttpSecurity`; không copy trực tiếp API Servlet.

## 11. Kiểm thử đúng đối tượng

### 11.1. Unit test cho mapping account nội bộ

File `src/test/java/com/example/login/AccountLinkServiceTest.java`:

~~~java
package com.example.login;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import static org.junit.jupiter.api.Assertions.*;

class AccountLinkServiceTest {

    private final AccountLinkService links = new AccountLinkService();

    @Test
    void knownAccountReceivesViewerRole() {
        var roles = links.authoritiesFor("oauth2:github", "123456");
        assertTrue(roles.stream().anyMatch(authority ->
                "ROLE_VIEWER".equals(authority.getAuthority())));
    }

    @Test
    void unknownAccountFailsClosed() {
        assertThrows(OAuth2AuthenticationException.class,
                () -> links.authoritiesFor(
                        "oauth2:github", "unknown-id"));
    }

    @Test
    void sameSubjectAtAnotherIssuerIsNotLinked() {
        assertThrows(OAuth2AuthenticationException.class,
                () -> links.authoritiesFor(
                        "oidc:https://another-idp.example.org",
                        "user-001"));
    }
}
~~~

Với Maven project có đủ dependencies ở phần 7, chạy:

~~~bash
mvn test
~~~

Ba test phải PASS và không có stdout nghiệp vụ cố định; Maven/JUnit in bản tóm tắt tùy phiên bản. Chúng **chỉ kiểm tra logic allowlist**, không chứng minh OAuth2 flow hay xác minh token với IdP thực.

### 11.2. Test UserService và luồng login

| Ca kiểm thử | Dữ liệu/thiết lập | Kỳ vọng |
|---|---|---|
| OAuth2 provider trả stable id hợp lệ đã link | `registrationId`, UserInfo, `getName()` | `OAuth2User` có `ROLE_VIEWER` |
| OAuth2 thiếu name attribute | Sai `user-name-attribute` hoặc thiếu ID | Login fail; không link bằng email thay thế |
| OIDC ID Token `iss+sub` đã link | Valid token, issuer, subject | `OidcUser` giữ ID Token và role nội bộ |
| OIDC không có UserInfo | Chỉ claims ID Token hợp lệ | Không NPE, identity vẫn theo `iss+sub` |
| OIDC UserInfo `sub` mismatch | UserInfo trả subject người khác | Login fail; bỏ claims UserInfo |
| Email bị thay đổi nhưng `iss+sub` không đổi | Profile update của cùng external identity | Không tạo account mới |
| Hai provider trả cùng email | `iss/sub` hoặc stable provider IDs khác | Không tự gộp/link account |
| `email_verified=false` | UserInfo/ID Token có email chưa chứng thực | Không tự claim account khác |
| Account blocked/disabled trong DB | External login hợp lệ nhưng policy nội bộ từ chối | Không tạo session có quyền |
| Provider trả scope `admin` | Scope khác role ứng dụng | Không tự cấp `ROLE_ADMIN` |
| Hai login đồng thời một user mới | JIT provisioning bật | Một link duy nhất, atomic/idempotent |
| Invalid state, ID Token signature, audience, nonce | Stub Authorization Server/IdP | Spring từ chối **trước** khi mapping |
| API của provider timeout/error | Slow/error UserInfo | Login fail có kiểm soát, không dùng profile cũ để bypass |
| Logout, quyền mới bị thu hồi | Session cũ vẫn tồn tại | Theo session revalidation/invalidation policy |

**Ghi chú quan trọng:** `SecurityMockMvcRequestPostProcessors.oauth2Login()` và `oidcLogin()` hữu ích để test authorization sau login, nhưng chúng giả lập principal đăng nhập; **không tự chạy luồng trao đổi code/token và custom UserService**. Muốn kiểm tra việc tải UserInfo/ID Token và delegation, hãy unit test UserService bằng request/delegate giả lập hoặc chạy integration test với một authorization server stub/trusted test IdP.

## 12. Checklist triển khai production

- [ ] Phân biệt rõ OAuth2 Login, OIDC Login và Resource Server, đúng các extension points.
- [ ] Provider registration/issuer và callback URL nằm trong allowlist; dùng HTTPS.
- [ ] Giữ kiểm tra authorization response `state`, ID Token `iss`/`aud`/`exp`/`nonce` và chữ ký bởi thư viện đáng tin cậy.
- [ ] Khi có OIDC UserInfo, `sub` phải trùng `sub` trong ID Token.
- [ ] Identity linking khóa bằng `iss+sub` hoặc stable provider ID, không khóa bằng email/display name.
- [ ] Chỉ lấy scopes/claims thực sự cần; secrets/tokens không xuất hiện trong profile DB/log/frontend.
- [ ] `OidcUser.getUserInfo()` có thể null; kiểm tra thiếu dữ liệu và policy rõ ràng.
- [ ] Account disabled/tenant/roles nội bộ được xử lý fail closed.
- [ ] Account linking/provisioning có unique constraint, transaction và test race.
- [ ] Chỉ đồng bộ profile fields được phép; phân biệt provider-authoritative và user-editable.
- [ ] `DefaultOidcUser` giữ ID Token/UserInfo, `DefaultOAuth2User` giữ attributes/name attribute.
- [ ] Theo dõi lỗi login, timeout/latency UserInfo và mã lỗi an toàn, không rò chi tiết account.
- [ ] Chính sách session, role refresh, reauthentication, CSRF và logout phù hợp ứng dụng.
- [ ] Unit/integration tests bao phủ user tồn tại/không tồn tại, multi-provider, email đổi, UserInfo thiếu/mismatch, role sai và provider outage.

## 13. Ghi nhớ

- `DefaultOAuth2UserService` xử lý user attributes cho **OAuth2 Login thông thường** từ UserInfo/API provider.
- `OidcUserService` xử lý **OIDC Login** với `OidcIdToken` và UserInfo nếu có.
- Custom service **delegate trước**, sau đó map external identity vào account nội bộ, kiểm tra trạng thái và cấp authorities ứng dụng.
- OIDC dùng **`(iss, sub)`**; OAuth2 provider khác dùng **provider namespace + stable external ID**. Email chỉ là thuộc tính profile.
- `SCOPE_...` không tự biến thành `ROLE_...`; quyền nghiệp vụ cần một nguồn được tin cậy.
- Nạp thông tin lúc login không có nghĩa mọi phiên được cập nhật tự động khi trạng thái/roles đổi.

## 14. Tài liệu tham khảo

1. [Spring Security — OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): `ClientRegistration`, các trường provider/UserInfo, callback và cấu hình đăng nhập.
2. [Spring Security — OAuth2 Login: Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): `userService`, `oidcUserService`, delegation và `GrantedAuthoritiesMapper`.
3. [Spring Security — OAuth2 (Servlet) Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html): scope `openid` và phân biệt OIDC với OAuth2.
4. [Spring Security API — OAuth2UserService](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/client/userinfo/OAuth2UserService.html): hợp đồng `loadUser`.
5. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC UserInfo service và delegate.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `sub`, ID Token và xác nhận `sub` của UserInfo trùng ID Token.
7. [Google Identity — OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect): hướng dẫn thực tế không dùng email làm account ID, ưu tiên `sub`.
