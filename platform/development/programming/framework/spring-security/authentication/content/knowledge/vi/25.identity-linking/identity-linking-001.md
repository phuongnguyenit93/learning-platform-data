# SSO và quan hệ giữa danh tính ngoài với phiên ứng dụng

## 1. Ba đối tượng dễ bị nhầm trong Single Sign-On

**Single Sign-On (SSO)** cho phép người dùng đăng nhập tại một nhà cung cấp danh tính (Identity Provider, **IdP**) rồi truy cập nhiều ứng dụng đã liên kết tin cậy mà không phải nhập lại mật khẩu tại từng ứng dụng. SSO **không có nghĩa** mọi ứng dụng chia sẻ một đối tượng Java `SecurityContext`, một cookie `JSESSIONID` hoặc một phiên HTTP chung.

Khi phát triển ứng dụng Spring Security, cần phân biệt:

1. **Danh tính ngoài (external identity)**: bản ghi người dùng do IdP xác nhận, ví dụ OIDC `iss=https://login.example.org/realms/staff` và `sub=00u-742`; trong SAML có thể dựa trên tổ hợp issuer/entity ID và định danh NameID được bảo đảm ổn định theo chính sách.
2. **Tài khoản ứng dụng (local account)**: khóa nội bộ do ứng dụng sở hữu, ví dụ `accountId=usr-1042`, có trạng thái, dữ liệu nghiệp vụ, tenant và các `GrantedAuthority`/quyền hiện hành.
3. **Phiên ứng dụng (application session)**: trạng thái đăng nhập cho **một ứng dụng** sau khi IdP đã xác thực; trong Spring MVC/Servlet thường chứa `SecurityContext` thông qua `HttpSession` và được tham chiếu từ cookie của ứng dụng.

Ví dụ:

```text
    Browser               IdP (login.example.org)             App A
       |                          |                               |
       | GET /reports            |                               |
       |-------------------------------------------------------->|
       |                     redirect /authorize                 |
       |<--------------------------------------------------------|
       | đăng nhập, nhận SSO cookie trên domain IdP              |
       |------------------------->|                               |
       |<-------------------------| redirect code về App A        |
       |-------------------------------------------------------->|
       |                          |<---- code exchange --------->|
       |                          |        validate ID Token     |
       |                          |                               |
       |                          |    (iss, sub) -> local account|
       |                          |    -> Authentication         |
       |                          |    -> app session             |
       |<-------------------------------------------Set-Cookie App A|
       |                          |                               |
       | GET /reports + app cookie                                |
       |-------------------------------------------------------->|
       |                       App A đọc SecurityContext từ session
       |<--------------------------------------------------------|
```

Đăng nhập IdP diễn ra ở một trust domain, còn phiên ứng dụng tồn tại ở trust domain khác. **Chức năng liên kết danh tính** là bước chuyển danh tính do IdP xác nhận sang account nội bộ mà ứng dụng cho phép sử dụng.

## 2. Phân biệt IdP session, application session và OAuth/OIDC token

| Đối tượng | Chủ sở hữu | Được dùng để | Thời hạn và phạm vi |
| --- | --- | --- | --- |
| **IdP SSO session** | IdP | Nhớ người dùng đã đăng nhập tại IdP để hỗ trợ SSO cho các ứng dụng tin cậy | Theo cookie/chính sách phiên của IdP |
| **App A session** | App A | Nhớ `Authentication` cho các request đến App A | Theo cookie App A, session store, idle/absolute timeout |
| **App B session** | App B | Nhớ `Authentication` cho App B | Độc lập App A, dù dùng cùng IdP |
| **OIDC ID Token** | IdP ký/phát hành, RP kiểm chứng | Chứng minh authentication event và danh tính (`iss`, `sub`, `aud`, ...) đối với RP | Hết hạn tại `exp`; không tự đồng nghĩa với app session |
| **OAuth 2.0 Access Token** | Authorization Server cấp | Cho client gọi resource server theo scope/audience/chính sách | Thời hạn token và chính sách resource server |
| **Refresh Token (nếu cấp)** | Authorization Server cấp | Xin access token mới theo grant/policy | Có thể luân chuyển/thu hồi; không thay `JSESSIONID` |

Tại thời điểm `t0`, người dùng đăng nhập App A bằng OIDC. IdP xác nhận user và App A mở `HttpSession`. Ở `t1`, ID Token hết hạn sau thời gian được cấu hình nhưng **App A có thể vẫn đang có session hợp lệ**: mỗi request tới App A chưa chắc xác thực lại ID Token với IdP. Ở `t2`, app session hết hạn nhưng IdP session vẫn hoạt động; App A redirect đến IdP và IdP có thể xác thực lại rất nhanh, khiến người dùng cảm thấy “chưa hề bị đăng xuất”.

**Hệ quả:** hết hạn ID Token, hết hạn access token, logout tại IdP, logout tại app và khóa tài khoản nội bộ là **các sự kiện khác nhau**; phải thiết kế chính sách đồng bộ chúng khi cần.

Cookie phiên của App A thường chỉ chứa một session ID; Spring Security **không mặc nhiên gửi ID Token hay password trong cookie app**. Token được lưu như thế nào phụ thuộc `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService` và cấu hình thực tế. Cookie của IdP thuộc origin/domain của IdP, trình duyệt không cung cấp nó cho ứng dụng một cách tùy tiện.

## 3. OIDC là ví dụ điển hình của SSO cho ứng dụng Spring

Spring Security hỗ trợ đăng nhập browser qua **OAuth 2.0 Authorization Code flow**, và sử dụng OIDC khi client yêu cầu scope `openid`.

Các bước cơ bản:

1. Client truy cập đường cần đăng nhập, Spring Security chuyển đến `/oauth2/authorization/{registrationId}`.
2. Ứng dụng tạo authorization request, gắn `state` (và nonce đối với OIDC khi áp dụng), quản lý liên kết request/response; có thể sử dụng PKCE theo client/chính sách.
3. IdP xác thực người dùng bằng phiên SSO sẵn có hoặc yêu cầu login/MFA, sau đó redirect về `/login/oauth2/code/{registrationId}` cùng authorization code.
4. Spring Security trao đổi code với token endpoint, xác minh ID Token (`iss`, `aud`, signature, `exp`, các ràng buộc liên quan), đồng bộ `state`/`nonce` theo thư viện và cấu hình.
5. `OidcUserService` tạo `OidcUser` từ ID Token và UserInfo (khi được gọi), rồi ứng dụng tra khóa danh tính ngoài để xác định **local account**.
6. Từ local account, ứng dụng nạp roles/permissions thành `GrantedAuthority`, hoàn tất `Authentication` và lưu `SecurityContext` theo cơ chế persistence đã cấu hình.
7. Browser nhận cookie session của **ứng dụng**. Các request tiếp theo thường dùng session này; không phải lặp lại OIDC authorization code flow cho mọi HTTP request.

### Các vai trò trong Spring Security Servlet

| Thành phần | Trách nhiệm |
| --- | --- |
| `ClientRegistration` / `ClientRegistrationRepository` | Cấu hình IdP, client ID, issuer URI, redirect URI, scopes |
| `OAuth2AuthorizationRequestRedirectFilter` | Chuyển hướng đến authorization endpoint, lưu trạng thái yêu cầu |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback và hoàn tất login |
| `OidcUserService` | Nạp thông tin principal OIDC và là điểm mở rộng để tìm local account |
| `OAuth2UserService<OidcUserRequest, OidcUser>` | Hợp đồng tùy biến xử lý OIDC user |
| `OAuth2AuthenticationToken` | `Authentication` trong ứng dụng sau OAuth2/OIDC login |
| `SecurityContextRepository` | Lưu/nạp `SecurityContext` cho request sau |
| `HttpSessionSecurityContextRepository` | Implementation session-backed phổ biến trong Servlet |
| `OAuth2AuthorizedClientService`/`OAuth2AuthorizedClientRepository` | Quản lý authorized client/token phục vụ API call, khác `SecurityContextRepository` |

Ứng dụng dùng Spring WebFlux có API tương ứng như `ServerHttpSecurity`, `ReactiveSecurityContextHolder` và `ServerSecurityContextRepository`. Đoạn Spring Boot code ở mục 7 là **Spring MVC/Servlet**, vì vậy không cắm `HttpSecurity` vào cấu hình WebFlux.

## 4. Khóa liên kết danh tính: OIDC (issuer, subject) -> localAccountId

Với OpenID Connect, cặp **`(iss, sub)`** của ID Token đã được **kiểm chứng** là định danh ổn định để một Relying Party nhận biết người dùng tại một issuer. **Không dùng riêng email, username, preferred_username hoặc tên hiển thị làm khóa liên kết tự động.**

Ví dụ bảng `external_identity_link`:

| issuer | subject | local_account_id | trạng thái |
| --- | --- | --- | --- |
| `https://login.company.org/realms/staff` | `sub-1001` | `usr-42` | ACTIVE |
| `https://login.partner.org/tenant-a` | `sub-88` | `usr-42` | ACTIVE, đã xác minh liên kết |
| `https://login.company.org/realms/staff` | `sub-1002` | `usr-51` | ACTIVE |

Bảng `local_account` riêng:

| id | enabled | quyền ứng dụng |
| --- | --- | --- |
| `usr-42` | true | `REPORT_READ`, `ROLE_USER` |
| `usr-51` | false | không cho đăng nhập dù IdP vừa xác thực |

Các quy tắc bắt buộc:

- Ràng buộc **unique** cho cặp `(issuer, subject)` trong phạm vi quản lý và với trạng thái ACTIVE theo mô hình dữ liệu; một external identity active không được tự động trỏ đến hai tài khoản khác nhau.
- Trước khi tra mapping, chỉ nhận ID Token do thư viện OIDC **đã xác minh** cho đúng client, issuer và audience. Không cho client gửi hai chuỗi `issuer`, `subject` qua JSON rồi coi là kết quả đăng nhập.
- Lưu local account ID ổn định; khi IdP thay email, display name hoặc tên đăng nhập, quan hệ vẫn giữ nguyên.
- Xử lý **pairwise subject**: cùng người dùng có thể nhận các `sub` khác nhau cho các RP/sector khác nhau. Không tự kết luận `sub` khác nhau là hai người khác, cũng không ép gom hai identity dựa vào email; nếu cần gom, yêu cầu quy trình liên kết được phép.
- Không tự đổi `sub` theo chữ thường/chữ hoa, xóa ký tự đặc biệt hoặc chuẩn hóa issuer tùy tiện; các chuỗi có tính định danh và có quy tắc riêng.
- Nhiều tenant/issuer có thể sử dụng cùng `sub`, nên **`sub` riêng lẻ không đủ**.
- Ở SAML, khóa tương ứng thường dựa trên issuer Entity ID + NameID có định dạng/qualifier thích hợp hoặc immutable attribute được IdP quản trị; **transient NameID** không phải khóa gắn tài khoản dài hạn.

### Đầu vào IdP chỉ chứng minh định danh, không chứng minh account nội bộ còn hợp lệ

IdP có thể trả `email_verified=true`; claim này không tự chứng minh rằng một tài khoản local bất kỳ có cùng email thuộc người đang đăng nhập. Email có thể bị tái sử dụng, được IdP ở trust domain khác xác minh theo cách khác, hoặc thay đổi khi nhân sự chuyển bộ phận.

**Ánh xạ thành công** cần cả hai điều kiện:

1. Identity ngoài đã xác thực có liên kết hợp lệ tới một local account.
2. Local account tại thời điểm áp dụng chính sách vẫn được phép sử dụng, đúng tenant và có các quyền hợp lệ.

## 5. SSO authentication, account linking và authorization là ba bước khác nhau

| Bước | Đầu vào tin cậy | Kết quả | Một lỗi thường gặp |
| --- | --- | --- | --- |
| **SSO authentication** | Response OIDC/SAML đã kiểm chứng từ IdP | External identity | Tự parse JWT không kiểm tra issuer/audience/chữ ký |
| **Account linking/resolution** | `(iss, sub)` + registry do ứng dụng quản lý | `localAccountId` | Gộp tài khoản theo email giống nhau |
| **Authorization** | Account hiện hành, role/permission của ứng dụng, tài nguyên | `GrantedAuthority` + quyết định cho phép/từ chối | Biến scope hoặc claim bất kỳ thành `ROLE_ADMIN` |

Trong Spring Security, nếu controller cần biết ai đăng nhập, `Authentication.getPrincipal()` thường chứa `OidcUser` với claim OIDC. Nếu nghiệp vụ cần ID của local account, ứng dụng nên có **một dịch vụ ánh xạ đáng tin** hoặc custom principal chứa `localAccountId` bên cạnh external identity. **Không đổi ý nghĩa `sub` của OIDC thành ID nội bộ**: đó là claim do IdP phát hành. Có thể giữ OIDC principal để dùng khi logout/kiểm tra claim và lưu local account ID theo cấu trúc riêng.

`GrantedAuthority` thường được nạp từ account/permission store nội bộ; claims từ IdP có thể góp phần tính quyền **chỉ khi có whitelist/policy và trust contract rõ ràng**. `SCOPE_profile` hoặc `SCOPE_email` biểu diễn scope được cấp cho OAuth client, không đồng nghĩa quyền quản trị dữ liệu của ứng dụng.

## 6. Ví dụ Java 17 chạy độc lập: external identity -> local account -> app session

Bài tập dưới đây mô phỏng **bước sau khi một IdP đã xác thực**, tức input `ExternalIdentity` được coi là đã xác minh. Chương trình thuần Java không tạo ID Token, không kiểm chứng chữ ký, không triển khai HTTP/cookie/session thật. Nhờ đó ta quan sát chính xác hợp đồng ánh xạ mà không cần tài khoản IdP.

Tạo file `SsoIdentitySessionDemo.java`:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SsoIdentitySessionDemo {

    // Tổ hợp issuer + subject (đã qua OIDC validation).
    record ExternalIdentity(String issuer, String subject) {
        ExternalIdentity {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException("Invalid external identity");
            }
        }
    }

    record LocalAccount(
            String id,
            boolean enabled,
            Set<String> permissions) {}

    // Chỉ mô phỏng session. Không chứa password hay ID Token.
    record AppSession(
            String id,
            String localAccountId,
            List<String> grantedAuthorities) {}

    static final class ApplicationLoginService {
        private final Map<ExternalIdentity, String> links;
        private final Map<String, LocalAccount> accounts;
        private final Map<String, AppSession> sessions = new HashMap<>();
        private int nextSessionNumber = 0;

        ApplicationLoginService(
                Map<ExternalIdentity, String> links,
                Map<String, LocalAccount> accounts) {
            this.links = Map.copyOf(links);
            this.accounts = Map.copyOf(accounts);
        }

        AppSession afterOidcAuthentication(ExternalIdentity identity) {
            // Trong hệ thống thật, identity CHỈ được tạo từ
            // ID Token đã xác minh, không nhận trực tiếp từ HTTP body.
            String accountId = links.get(identity);
            if (accountId == null) {
                throw new SecurityException("Identity is not linked to an active account");
            }
            LocalAccount account = accounts.get(accountId);
            if (account == null || !account.enabled()) {
                throw new SecurityException("Identity is not linked to an active account");
            }

            // Lấy quyền từ account, không suy role từ email/subject.
            List<String> authorities = account.permissions().stream()
                    .sorted()
                    .toList();

            AppSession session = new AppSession(
                    "app-session-" + (++nextSessionNumber),
                    account.id(),
                    authorities);
            sessions.put(session.id(), session);
            return session;
        }

        boolean isLocallyLoggedIn(String appSessionId) {
            return sessions.containsKey(appSessionId);
        }

        void localLogout(String appSessionId) {
            sessions.remove(appSessionId);
        }
    }

    public static void main(String[] args) {
        ExternalIdentity userAtIdp = new ExternalIdentity(
                "https://login.example.org/realm",
                "subject-1001");

        ApplicationLoginService app = new ApplicationLoginService(
                Map.of(userAtIdp, "usr-42"),
                Map.of("usr-42", new LocalAccount(
                        "usr-42",
                        true,
                        Set.of("REPORT_READ", "ROLE_USER"))));

        AppSession session = app.afterOidcAuthentication(userAtIdp);
        System.out.println("localAccount=" + session.localAccountId());
        System.out.println("authorities=" + session.grantedAuthorities());
        System.out.println("appLoggedIn=" + app.isLocallyLoggedIn(session.id()));

        // Cùng sub nhưng issuer khác phải là danh tính khác.
        boolean rejected = false;
        try {
            app.afterOidcAuthentication(new ExternalIdentity(
                    "https://another-idp.example.org/realm",
                    "subject-1001"));
        } catch (SecurityException e) {
            rejected = true;
        }
        System.out.println("otherIssuerRejected=" + rejected);

        app.localLogout(session.id());
        System.out.println("appLoggedInAfterLogout="
                + app.isLocallyLoggedIn(session.id()));
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac SsoIdentitySessionDemo.java
java SsoIdentitySessionDemo
```

Stdout chính xác:

```text
localAccount=usr-42
authorities=[REPORT_READ, ROLE_USER]
appLoggedIn=true
otherIssuerRejected=true
appLoggedInAfterLogout=false
```

### Giải thích những điều ví dụ cố ý mô hình hóa

- `ExternalIdentity` chỉ có `issuer` và `subject`; cùng `sub` nhưng issuer khác sẽ **không** tự đăng nhập vào local account.
- Map `links` bảo toàn quyết định liên kết đã được duyệt; map `accounts` chứa trạng thái và quyền hiện hành của user. Không tạo local account ngầm từ email.
- `AppSession` tách khỏi đối tượng `ExternalIdentity`. Mô phỏng logout local chỉ xóa app session, **không đụng tới IdP SSO session**.
- Sắp xếp authorities giúp output xác định; đây là quyền của ứng dụng, không phải danh sách scope của ID Token.
- `HashMap` và counter chỉ phù hợp demo một process/không đồng thời. Production phải dùng session mechanism của framework, token/cookie chống giả mạo, store phân tán khi cần, kiểm soát concurrency và transaction cho bảng liên kết.
- `permissions` được snapshot khi mở session; nếu quyền thay đổi sau đó, ví dụ này không tự refresh. Đây chính là lý do hệ thống cần session TTL/revalidation/invalidation theo chính sách.
- Bất kỳ ai cũng có thể tự tạo `ExternalIdentity` trong đoạn demo. Trong hệ thống thật chỉ code **sau validator OIDC** được phép tạo input đó.

## 7. Áp dụng vào Spring Boot 3.x / Spring Security 6.x (Servlet)

Phần này minh họa điểm tích hợp thật với OIDC, bảo toàn `iss`/`sub` và nạp quyền từ tài khoản local. Cần IdP OIDC có thật, client đã đăng ký đúng redirect URI, và dịch vụ `AccountLinkService` được triển khai bằng kho dữ liệu nội bộ.

### 7.1. Dependencies và cấu hình client

Dự án Spring Boot 3.x (Java 17+) cần ít nhất:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Ví dụ `application.yml`, thay issuer và biến môi trường bằng giá trị đã đăng ký:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://login.example.org/realm

server:
  servlet:
    session:
      timeout: 30m
  forward-headers-strategy: framework
```

- `openid` chọn luồng OIDC; `issuer-uri` dùng discovery/validator tương ứng. Issuer là **giá trị định danh cần so khớp chính xác**, không phải nhãn tùy tiện thay đổi ở runtime.
- `/oauth2/authorization/corporate` bắt đầu login; callback là `/login/oauth2/code/corporate`.
- Secret lấy từ cấu hình bảo vệ; không lưu hard-code vào repository.
- `server.servlet.session.timeout` minh họa idle timeout của app session; không đặt thời hạn IdP session hay thời hạn ID Token.
- `forward-headers-strategy` chỉ dùng khi có reverse proxy đáng tin, đã dọn/kiểm soát các forwarded headers và bảo đảm external scheme/host đúng. Không cho client tùy ý ghi các header ảnh hưởng redirect URL.

### 7.2. Tùy biến OidcUserService để nạp GrantedAuthority theo account local

Trong một ứng dụng có bean `AccountLinkService` (giao diện trong ví dụ) và implementation backed-by-DB, đặt file `src/main/java/demo/security/OidcSecurityConfig.java`:

```java
package demo.security;

import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {

    // Ứng dụng phải cung cấp bean implementation, ví dụ repository/DB.
    public interface AccountLinkService {
        LocalAccount findActiveAccount(String issuer, String subject);
    }

    public record LocalAccount(String id, Set<String> permissions) {}

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**").permitAll()
                        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .userInfoEndpoint(info -> info
                                .oidcUserService(linkedOidcUserService)))
                .build();
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService(
            AccountLinkService links) {

        OidcUserService standardOidcUserService = new OidcUserService();

        return userRequest -> {
            // Spring Security xử lý OIDC trước khi delegate trả OidcUser.
            OidcUser external = standardOidcUserService.loadUser(userRequest);

            String issuer = external.getIdToken().getIssuer().toString();
            String subject = external.getSubject();

            LocalAccount account = links.findActiveAccount(issuer, subject);
            if (account == null) {
                throw new UsernameNotFoundException(
                        "No enabled local account for verified external identity");
            }

            // Map quyền từ account local theo policy, không tự suy từ email.
            Set<GrantedAuthority> localAuthorities =
                    account.permissions().stream()
                            .<GrantedAuthority>map(SimpleGrantedAuthority::new)
                            .collect(java.util.stream.Collectors.toUnmodifiableSet());

            // Giữ token/claims OIDC để Spring Security vẫn biết identity IdP.
            return new DefaultOidcUser(
                    localAuthorities,
                    external.getIdToken(),
                    external.getUserInfo());
        };
    }
}
```

**Phạm vi ví dụ:** class có thể biên dịch với dependencies đúng phiên bản, nhưng để ứng dụng **khởi động và đăng nhập** phải có bean triển khai `AccountLinkService`, entry có thật trong DB, client registration và IdP hoạt động. `AccountLinkService.findActiveAccount` phải truy vấn trong phạm vi tenant/trust domain đúng, reject mapping trùng/mơ hồ, kiểm tra account disabled/locked và ném lỗi xác thực thích hợp khi không có kết quả. Trong production cần chuẩn hóa và map lỗi nghiệp vụ thành `AuthenticationException` phù hợp.

`DefaultOidcUser` ở đây vẫn nhận **OIDC subject** làm tên principal; `account.id()` không bị giả làm `sub`. Muốn controller dùng `localAccountId`, có thể tạo custom principal chứa cả hai ID hoặc tra service theo cặp (`iss`, `sub`) trong tầng ứng dụng. Duy trì liên kết account trong một thành phần có trách nhiệm rõ, tránh mỗi controller tự suy account từ `email`.

**Ghi chú về `GrantedAuthority`:** ví dụ thay authorities bằng quyền nội bộ nhằm minh họa policy của một ứng dụng. Nếu cần thêm authority chuẩn OIDC hoặc scope cho các chức năng khác, hãy thiết kế tập quyền kết hợp có kiểm soát và test kỹ. Đừng mặc định scope `SCOPE_email` cho phép đọc toàn bộ hồ sơ nội bộ.

### 7.3. SecurityContext và session sau callback

Với cấu hình login session-based thông thường trên Servlet, Spring Security lưu `Authentication` vào `SecurityContext` và dùng `SecurityContextRepository` để persistence giữa các request. `HttpSessionSecurityContextRepository` là implementation phổ biến. Cách lưu authentication trong framework không đồng nghĩa bộ dữ liệu `AccountLinkService` được đồng bộ sang phiên IdP; đó là dữ liệu ứng dụng.

**Không tự làm**:

```java
// Sai về kỳ vọng persistence: chỉ set ThreadLocal chưa đảm bảo
// session của request kế tiếp sẽ có Authentication mới.
SecurityContextHolder.getContext().setAuthentication(authentication);
```

Đoạn minh họa trên chỉ có ý nghĩa trong một request/thread. Khi viết filter hoặc controller đăng nhập riêng ở Spring Security 6.x, cần lưu `SecurityContext` thông qua `SecurityContextRepository.saveContext(context, request, response)` theo cấu hình. Với `oauth2Login` mặc định, framework thực hiện quá trình persistence cần thiết; không chèn thêm việc set context tùy tiện.

### 7.4. Vì sao quyền có thể cũ trong phiên?

Hầu hết ứng dụng lưu `Authentication` kèm authorities tại thời điểm đăng nhập vào session. Nếu admin thu hồi `REPORT_READ` trong DB sau đó, request sử dụng session cũ có thể vẫn thấy snapshot quyền cũ cho đến khi hệ thống refresh/revalidate hoặc invalidates session.

Các chiến lược thường dùng:

- Thời hạn phiên ngắn và re-authentication khi cần.
- Invalidate sessions liên quan khi account bị khóa, unlink hoặc có sự kiện giảm quyền.
- Khi authorization quan trọng, đối chiếu account/permission hiện hành hoặc dùng phiên bản quyền (`permissionsVersion`) để phát hiện snapshot cũ.
- Đối với API stateless, xác thực token ở mỗi request theo chính sách resource server; token revocation/TTL và dữ liệu quyền vẫn cần được thiết kế.

## 8. Quy trình linking tài khoản an toàn

### 8.1. Đăng nhập lần đầu: JIT provisioning hoặc từ chối

Nếu (`iss`, `sub`) chưa tồn tại:

1. **Invite/enterprise-managed provisioning**: chỉ tạo account khi người dùng thuộc nhóm/tenant đã được quản trị cấp quyền hoặc có invitation hợp lệ.
2. **Just-in-time provisioning (JIT)**: có thể tạo account tự động nếu chính sách sản phẩm cho phép, nhưng cần kiểm tra issuer, tenant, email policy, quyền mặc định tối thiểu và yêu cầu consent.
3. **Không có policy provisioning**: từ chối đăng nhập hoặc chuyển sang quy trình đăng ký được bảo vệ.

Trong cả ba cách, không nên âm thầm ghép external identity mới vào account cũ vì cùng email, kể cả email đã verified. Nếu sản phẩm hỗ trợ account recovery/linking, hãy thiết kế bước chứng minh quyền sở hữu account hiện tại và yếu tố xác thực mới.

### 8.2. Liên kết IdP B vào một local account hiện có

Quy trình đề xuất:

1. User đang đăng nhập **bằng account nội bộ đã xác định**; với hành động nhạy cảm, yêu cầu step-up/MFA hoặc xác thực lại gần đây.
2. User chọn “Liên kết tài khoản IdP B”. Ứng dụng khởi tạo flow OIDC riêng với `state`/`nonce` an toàn và redirect URI đúng.
3. Sau callback đã kiểm chứng, lấy (`issB`, `subB`) từ identity B.
4. Kiểm tra unique: identity B chưa thuộc account khác; nếu có, không âm thầm đổi chủ sở hữu.
5. Ghi liên kết `(issB, subB) -> localAccountId` trong transaction, có unique constraint, audit actor + thời điểm + phương thức xác minh.
6. Thông báo kết quả, không biến việc liên kết thành thay accountId của session hiện tại; nếu cần re-authenticate/switch account, dùng flow riêng.

Nhiều request link đồng thời có thể tranh chấp. **Unique constraint tại DB và transaction** là lớp bảo vệ bắt buộc; chỉ kiểm tra `if (find == null) insert` ở Java không đủ chống race condition.

### 8.3. Unlink và chuyển account

- Không cho unlink phương thức đăng nhập duy nhất nếu người dùng sẽ mất khả năng truy cập mà chưa có phương án recovery được kiểm chứng.
- Nếu external identity B đang liên kết local account X, không tự chuyển nó sang Y khi email/Y có thay đổi; cần quy trình được ủy quyền và log.
- Nếu issuer đổi do migration, không thay `iss` bằng phép string replace trong DB; chuẩn bị kế hoạch mapping/validation và rollback có kiểm tra.
- Sau unlink, xử lý **các app session hiện hữu** đã được xác thực qua identity đó theo policy; xóa link trong DB không tự làm phiên đã được mở biến mất.
- Nếu người dùng có hai local account cần merge, bảo vệ quyền sở hữu tài nguyên, dữ liệu và quyền; đây là tác vụ nghiệp vụ riêng, không chỉ thêm một dòng vào bảng liên kết.

## 9. Vòng đời phiên: logout, timeout, thay đổi account

### Bảng tình huống

| Sự kiện | IdP SSO session | App A session | App B session |
| --- | --- | --- | --- |
| Người dùng login App A bằng OIDC | Có thể vừa tạo/có sẵn | Được tạo hoặc cập nhật | Không nhất thiết tồn tại |
| Người dùng chuyển App B (cùng IdP) | Có thể tái sử dụng để SSO | Vẫn còn | Có thể tạo mới sau redirect |
| App A idle timeout | Có thể vẫn còn | Hết hạn | Có thể vẫn còn |
| App A local logout | Thường vẫn còn | Bị hủy/xóa authentication | Thường vẫn còn |
| User logout tại IdP | Bị xóa theo IdP | **Không bảo đảm tự bị hủy** | **Không bảo đảm tự bị hủy** |
| Account bị admin vô hiệu hóa | Tùy IdP | Cần revalidation/invalidation theo ứng dụng | Cần chính sách tương tự |
| OIDC back-channel logout đúng chuẩn, triển khai đầy đủ | IdP phát logout event | RP liên quan có thể hủy session tương ứng | RP khác tùy triển khai/support |

### Ba dạng logout trong OIDC

**Local logout:** Spring Security xử lý `POST /logout` theo cấu hình thường dùng; hủy `HttpSession`/clear `SecurityContext` và dữ liệu authentication tại RP. Nó không tự động xóa phiên SSO ở IdP, nên login lại có thể diễn ra ngay bằng IdP cookie cũ.

**RP-initiated logout:** ứng dụng chủ động redirect tới `end_session_endpoint` của IdP (nếu IdP hỗ trợ) kèm tham số thích hợp, với chính sách post-logout redirect đã đăng ký. Trong Spring Security Servlet có `OidcClientInitiatedLogoutSuccessHandler`. Đây là một flow logout thêm vào local logout; provider có thể có chính sách hủy phiên khác nhau.

Ví dụ **đoạn cấu hình bổ sung** bên trong class `@Configuration` (cần inject `ClientRegistrationRepository`; không phải chương trình Java độc lập):

```java
@Bean
OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    var handler = new OidcClientInitiatedLogoutSuccessHandler(registrations);
    handler.setPostLogoutRedirectUri("{baseUrl}/");
    return handler;
}

// Trong SecurityFilterChain, sau .oauth2Login(...):
// .logout(logout -> logout.logoutSuccessHandler(oidcLogoutSuccessHandler))
```

**Back-channel logout:** IdP gửi logout notification đã ký/được xác minh đến RP, giúp RP kết thúc session tương ứng nếu phiên bản Spring Security, IdP và ứng dụng đều hỗ trợ. Đối chiếu issuer, audience, `sid`/`sub` và session registry đúng với spec. Không tự viết endpoint `/logout` nhận `userId` không xác minh từ Internet rồi hủy mọi session.

**Quan trọng:** “Logout khỏi mọi ứng dụng” là yêu cầu đa hệ thống; không thể bảo đảm chỉ bằng `session.invalidate()` của App A. Phải có hợp đồng giữa IdP, từng RP và cơ chế revocation/session registry/notification tương thích.

### Session fixation, CSRF và cookie

- Spring Security Servlet có cơ chế **session fixation protection** khi authentication thành công (thường đổi session ID trên container tương thích). Không tự tái sử dụng một session ID do client quyết định.
- Giữ `Secure`, `HttpOnly` và `SameSite` phù hợp cho session cookie; dùng HTTPS và cấu hình domain/path chặt chẽ. Tránh nhúng ID Token hay refresh token vào cookie dạng không được bảo vệ.
- Giữ CSRF protection với các thao tác thay đổi trạng thái trong ứng dụng session-based, gồm logout, account linking, unlink; callback OAuth/OIDC cần `state`, `nonce` và các cơ chế protocol tương ứng.
- Nếu triển khai nhiều instance, dùng session store chung nếu cần; không nhầm IdP SSO session với shared Spring Session.
- Kiểm tra cả **idle timeout** và **absolute lifetime**; phiên không nên được gia hạn vô hạn chỉ vì browser liên tục gửi request.
- Với hành động nhạy cảm (chuyển tiền, đổi MFA, chuyển ownership), xét yêu cầu re-authentication/step-up riêng; một app session vừa được SSO không tự chứng minh “người dùng vừa nhập mật khẩu”.

## 10. SSO với OAuth2/OIDC, SAML và API bearer token khác nhau ở đâu?

| Luồng | Chứng cứ nhận diện | Quan hệ tới phiên ứng dụng |
| --- | --- | --- |
| OIDC browser login | ID Token từ issuer đã kiểm chứng; `iss` + `sub` | RP thường mở session browser; account linking do ứng dụng quản lý |
| SAML 2.0 SSO browser | SAML Response/Assertion đã kiểm chứng signature, audience, recipient, thời hạn và InResponseTo theo profile | Service Provider cũng có phiên local riêng; logout phải có cơ chế SAML SLO nếu cần |
| OAuth2 resource server Bearer JWT | Access token hợp lệ đối với resource server (issuer, audience, signature, exp, scopes) | Mỗi request tự mang token; **không có app session browser mặc định** |
| OAuth2 opaque token | Introspection/policy AS trả active token và principal | Thường stateless ở RP; cache/revocation theo cấu hình |
| LDAP/AD username-password login | Bind hoặc password verification theo provider | Ứng dụng có thể mở session local; LDAP không tự đồng nghĩa SSO browser |

OIDC được xây trên OAuth2 nhưng bổ sung giao thức xác thực người dùng; **OAuth2 access token một mình không phải ID Token** và không nên dùng để tự dựng account link kiểu OIDC khi chưa có hợp đồng danh tính rõ.

Ở Resource Server, `JwtAuthenticationConverter` hoặc authority mapping phục vụ quyền API, không tự thực hiện browser login với IdP SSO cookie. Ngược lại `oauth2Login` là cơ chế interactive browser login, không nên tùy tiện dùng thay cho Bearer API authentication.

## 11. Lỗi thực tế và cách chẩn đoán

**(1) Một email đăng nhập hai IdP rồi bị gộp nhầm account.** Phép nối dùng `email` thay vì (`iss`, `sub`). Kiểm tra bảng identity link, unique constraint và quy trình chứng minh sở hữu account trước khi link.

**(2) Đăng nhập SSO thành công nhưng request sau vẫn anonymous.** Kiểm tra callback đúng, cookie của ứng dụng được browser gửi lại, session store có dữ liệu không, domain/path/SameSite/HTTPS/reverse proxy, và `SecurityContextRepository` có lưu authentication đúng cơ chế Spring Security 6.x không.

**(3) Logout App A rồi bấm Login lại không thấy màn hình IdP.** Đó có thể là IdP SSO session vẫn còn. Nếu sản phẩm muốn sign-out IdP, thiết kế RP-initiated logout; nếu muốn buộc nhập lại credential cho tác vụ nhạy cảm, dùng yêu cầu xác thực lại theo OIDC và policy của IdP.

**(4) Logout tại IdP nhưng App A vẫn truy cập được.** App A đã mở session local. Muốn đồng bộ cần back-channel/front-channel logout phù hợp hoặc cơ chế session invalidation/revalidation riêng. Không giả định mọi RP nhận logout event tự động.

**(5) ID Token hết hạn mà người dùng vẫn vào được App A.** App session có thời gian sống riêng. Muốn buộc kiểm tra liên tục, thiết kế session max age/revalidation. Không xem `idToken.exp` là timer mặc định xóa `HttpSession`.

**(6) Admin xóa quyền trong IAM nhưng session cũ vẫn có `ROLE_ADMIN`.** Các `GrantedAuthority` được snapshot khi login. Invalidate session theo sự kiện đổi quyền hoặc kiểm tra quyền hiện hành ở điểm quyết định.

**(7) User được phép login IdP nhưng bị từ chối ở app.** Có thể external identity chưa được link, local account disabled hoặc thiếu permission. Phân biệt authentication của IdP với account provisioning và authorization của ứng dụng.

**(8) `preferred_username` hoặc `email` đổi rồi sinh account mới.** Key lookup không ổn định. Chuyển sang (`iss`, `sub`) OIDC; dữ liệu email/name chỉ dùng như metadata có thể cập nhật.

**(9) Account B đang đăng nhập được dùng để link IdP mới vào Account A.** Quy trình linking không bảo vệ session hiện tại và CSRF/nonce, hoặc thiếu bước re-authentication. Xác minh quyền của account đang đăng nhập, giữ state chống login-CSRF và chống chuyển chủ identity ngoài.

**(10) Ứng dụng dùng nhiều OIDC clients hoặc tenant rồi xảy ra nhầm quyền.** Không chỉ dựa vào `sub` hay tên client; kiểm tra chính xác issuer, subject, tenant và client context; mapping role ở trust boundary phù hợp.

**(11) Tạo account chỉ vì IdP trả `email_verified=true`.** Verified email là thông tin từ một issuer, không tự chứng minh đủ quyền sở hữu local account hoặc invitation. Áp dụng JIT provisioning policy riêng.

**(12) Tạo session trên mỗi API Bearer request rồi gây session sprawl.** Chọn chính xác cơ chế browser `oauth2Login` và API `oauth2ResourceServer`; thiết kế `SessionCreationPolicy.STATELESS` cho API khi cần, không ép mọi auth mechanism vào một filter chain.

**(13) App session cookie rò rỉ hoặc bị cố định.** Xem lại HTTPS, Secure/HttpOnly/SameSite, session fixation, session ID rotation và logout; không lưu session ID qua URL hoặc log công khai.

**(14) Logout back-channel hủy nhầm nhiều phiên.** Endpoint không kiểm chứng logout token và issuer/audience/`sid`/`sub`. Dùng framework theo spec, registry phiên có tương quan chính xác và test multi-tenant.

**(15) Dùng access token từ App A để gọi API của App B mà không kiểm tra audience.** Access token được cấp cho resource/audience cụ thể. App B chỉ tin token dành đúng cho B và policy tương ứng; **cùng IdP không đồng nghĩa mọi token được dùng xuyên dịch vụ**.

**(16) Dữ liệu OIDC bị ghi vào log.** Không log ID Token, access/refresh token, cookies, authorization code, nonce/state hoặc hồ sơ cá nhân toàn bộ. Audit nên ghi timestamp, issuer/ID đã che hoặc hashed phù hợp, local account, sự kiện và kết quả.

## 12. Ma trận kiểm thử cần có

| Trường hợp | Kỳ vọng |
| --- | --- |
| OIDC token hợp lệ, (`iss`, `sub`) có link active | Đăng nhập thành local account đúng |
| Cùng `sub` nhưng issuer khác | Không liên kết nhầm account |
| Email trùng nhưng `sub` khác | Không tự gộp local account |
| `iss`/`aud`/signature/`nonce` không hợp lệ | Từ chối trong OIDC validation, chưa tạo app session |
| Link chưa có và JIT bị tắt | Từ chối hoặc vào flow đăng ký an toàn |
| Local account disabled | Từ chối dù IdP xác thực thành công |
| User có 2 external identities được link hợp lệ | Cả hai login vào cùng localAccountId |
| Hai request link cùng một external identity sang hai account | Một thắng theo transaction/unique constraint, request còn lại bị từ chối |
| Login App A rồi vào App B | App B có session riêng; IdP có thể dùng SSO để tránh password prompt |
| Logout App A | App A mất session; IdP/App B phụ thuộc flow logout riêng |
| IdP logout, không có back-channel | Không giả định local session bị xóa; đánh giá policy thực tế |
| Back-channel logout hợp lệ | RP liên quan hủy session đúng theo `sid`/`sub` và client |
| App session timeout, IdP SSO cookie còn hạn | Login lại có thể nhanh mà không hiện form IdP |
| Thu hồi permission trong local account | Không còn quyền sau thời gian revalidation đã định |
| Cookie bị mất / hostname thay đổi / reverse proxy sai | Callback/session phải được chẩn đoán chính xác, không bypass kiểm tra state |
| Cross-site POST /logout hoặc /link | CSRF protection và các kiểm tra authentication chống thao tác trái phép |

Để test end-to-end, dùng IdP thử nghiệm hỗ trợ OIDC thật, đồng hồ đồng bộ, trình duyệt lưu hai loại cookie và ít nhất hai RP. Unit test mapping chỉ chứng minh quy tắc (`iss`, `sub`) -> account; **không thay thế** test validation của ID Token, session cookie, login-CSRF, logout hoặc permission change.

## 13. Checklist triển khai một hệ thống SSO + local session

1. Định nghĩa **nguồn sự thật**: IdP sở hữu sự kiện xác thực và `(iss, sub)`, ứng dụng sở hữu `localAccountId`/quyền/phiên.
2. Kiểm chứng OIDC/SAML bằng thư viện hỗ trợ chuẩn, cho đúng issuer, audience, client registration và redirect URI.
3. Thiết kế bảng link có unique constraint cho external identity, tenant scope, trạng thái và audit.
4. Quy định JIT provisioning, linking và unlinking; không đồng nhất tài khoản bằng email.
5. Cấu hình persistence của `Authentication` trong `SecurityContextRepository`; chọn cookie/session lifetime và session store phù hợp.
6. Nạp `GrantedAuthority` từ account/policy; chọn cách invalidate session khi đổi quyền hoặc khóa user.
7. Xác định rõ **local logout**, **IdP logout**, **global logout** và các cơ chế tương ứng mà IdP/RP thật sự hỗ trợ.
8. Đảm bảo CSRF/state/nonce, HTTPS, session fixation protection và cookie attributes; hạn chế token/PII trong log.
9. Kiểm thử ít nhất hai IdP và hai ứng dụng khi triển khai multi-provider SSO; kiểm tra đổi email, đổi `sub` pairwise, đổi tenant và logout chéo.
10. Xác định quy trình xử lý mất account IdP, gỡ liên kết, hồi phục truy cập và migration mà không trao quyền sai cho account khác.

### Tài liệu tham khảo chính thức

- OpenID Connect Core 1.0, `iss`/`sub` và Claim Stability: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 Login Core Configuration (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration (authority và OIDC user service): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — Logout Support: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — OIDC Logout: https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/login/logout.html

**Ý chính để nhớ:** SSO giúp IdP xác thực danh tính ngoài; ứng dụng phải liên kết danh tính đó với local account có kiểm soát, cấp quyền theo chính sách của mình và quản lý phiên đăng nhập riêng. Không thể coi SSO cookie, ID Token, access token, account link và `HttpSession` là cùng một thực thể.
