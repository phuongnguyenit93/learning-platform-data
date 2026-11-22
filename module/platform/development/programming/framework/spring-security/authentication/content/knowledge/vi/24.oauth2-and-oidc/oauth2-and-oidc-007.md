# Ánh xạ claims, quyền và định danh bên ngoài sang principal nội bộ

## 1. Bài toán: đăng nhập bằng IdP nhưng ứng dụng vẫn phải biết “người này là ai?”

Trong hệ thống doanh nghiệp, người dùng có thể đăng nhập qua Google Workspace, Microsoft Entra ID, Keycloak hoặc một OpenID Provider khác. Nhà cung cấp danh tính (*Identity Provider*, IdP) xác thực người dùng và phát hành những thông tin như `sub`, `email`, `name`, `groups`, `roles`. Trong khi đó, ứng dụng Java có dữ liệu riêng: mã nhân viên, tài khoản nội bộ, vai trò kế toán, phạm vi đơn vị và trạng thái được phép sử dụng hệ thống.

Hai tầng đó phục vụ các câu hỏi khác nhau:

- **IdP và OIDC:** ai đã đăng nhập thành công tại nhà cung cấp danh tính, bằng định danh nào?
- **Ứng dụng:** tài khoản nội bộ nào tương ứng với danh tính ngoài, tài khoản có bị khóa không, được xem/sửa dữ liệu nào?
- **Spring Security:** biểu diễn kết quả xác thực thành `Authentication`/principal và danh sách `GrantedAuthority` để các quy tắc truy cập áp dụng nhất quán.

Ví dụ: một ID Token hợp lệ chứa `iss=https://login.example-idp.test/realms/company` và `sub=00u8abc`. Ứng dụng ánh xạ cặp này đến `user_id=usr_1042`, rồi nạp các authority `APP_ORDER_READ` và `APP_ORDER_APPROVE` từ chính sách quản lý quyền. Việc token có `email=lan@company.example` hoặc `name=Lan Nguyen` chủ yếu phục vụ hiển thị, không nên là chìa khóa xác định quyền.

~~~text
Browser                    OpenID Provider (IdP)             Spring Boot
   |                                 |                            |
   |-- OIDC authorization request -->|                            |
   |<-- authorization code ----------|                            |
   |-- callback + code ------------------------------------------>|
   |                                 |<-- code exchange ---------|
   |                                 |--- ID Token -------------->|
   |                                 |                            |
   |                                 |    validate OIDC token     |
   |                                 |    extract (issuer, sub)   |
   |                                 |    resolve local user      |
   |                                 |    load active state/roles |
   |                                 |    create Authentication   |
   |<-- application session --------------------------------------|
   |-- /orders/approve ------------------------------------------>|
   |                                 |    authorize per resource  |
~~~

Đây là mô hình **OIDC login dựa trên authorization code**, không phải mô tả chi tiết mọi biến thể OAuth 2.0. Với API nhận bearer access token, bước đầu là resource server xác minh access token, sau đó mới ánh xạ identity và quyền.

## 2. Phân biệt claim, principal, authority, scope và role

| Thuật ngữ | Ý nghĩa | Có thể dùng trực tiếp làm quyền không? |
|---|---|---|
| **Claim** | Một thuộc tính trong ID Token, access token JWT hoặc UserInfo, thí dụ `iss`, `sub`, `email`, `groups`. | Không phải mọi claim đều là quyền; phải hiểu nguồn và ngữ nghĩa. |
| **External identity** | Danh tính do IdP xác nhận, thông thường khóa theo `(issuer, subject)`. | Dùng để liên kết tài khoản; bản thân chưa là quyền nghiệp vụ. |
| **Internal principal** | Biểu diễn chủ thể được ứng dụng công nhận, thí dụ `internalUserId=usr_1042`, `tenantId=t1`. | Là chủ thể để kiểm tra quyền; không tự cấp quyền. |
| **GrantedAuthority** | Quyền mà Spring Security dùng kiểm tra như `APP_ORDER_READ`, `ROLE_ADMIN`, `SCOPE_orders.read`. | Có, khi chính sách ứng dụng chấp nhận authority tương ứng. |
| **OAuth scope** | Phạm vi được ủy quyền cho một OAuth client với resource server, như `orders.read`. | Không tự đồng nghĩa “vai trò nhân viên”; có thể map thành `SCOPE_orders.read` để kiểm tra. |
| **IdP group/role** | Nhóm hoặc role theo mô hình của IdP, thí dụ `engineering`, `erp-admins`. | Chỉ nên cấp quyền sau khi được kiểm chứng và ánh xạ qua policy. |
| **Business permission** | Quyền thực hiện hành động cụ thể trong ứng dụng, như duyệt hóa đơn. | Thường được nạp từ hệ thống chính sách của ứng dụng và giới hạn theo dữ liệu. |

Trong Spring Security, `Authentication.getPrincipal()` là đối tượng mô tả chủ thể, `Authentication.getName()` là tên định danh dùng bởi `Principal`, và `Authentication.getAuthorities()` chứa các `GrantedAuthority`. Phương thức `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`; `hasAuthority("APP_ORDER_APPROVE")` kiểm tra chính xác chuỗi đã định nghĩa. Không được mặc định rằng một claim `"role": "ADMIN"` tự có giá trị như `ROLE_ADMIN`.

**Quan trọng:** OAuth 2.0 là khung ủy quyền, còn OpenID Connect (OIDC) bổ sung lớp xác thực người dùng trên OAuth 2.0. **ID Token** phục vụ OIDC client/Relying Party nhận thông tin đăng nhập; **access token** phục vụ API/resource server. API không nên chấp nhận ID Token chỉ vì nó là JWT có chữ ký hợp lệ. Token phải đúng **loại, issuer, audience, thời hạn và mục đích sử dụng**.

## 3. Chuẩn hóa định danh ngoài: vì sao là `iss + sub`?

Theo OpenID Connect Core, cặp claim **`iss` (issuer) và `sub` (subject)** là căn cứ định danh người dùng được chuẩn bảo đảm trong phạm vi một issuer. Cùng một chuỗi `sub` ở hai IdP khác nhau **không được** mặc nhiên hiểu là một người. Một IdP có thể sử dụng *pairwise subject*, tức các client/sector khác nhau nhận `sub` khác nhau cho cùng một người dùng để hạn chế theo dõi chéo.

Ví dụ:

~~~json
{
  "iss": "https://idp.company.example/realms/staff",
  "sub": "9a2b-user-451",
  "aud": "portal-web",
  "email": "lan@company.example",
  "email_verified": true,
  "name": "Lan Nguyen",
  "preferred_username": "lan.nguyen"
}
~~~

Trong một OIDC ID Token hợp lệ, đây là **các claim đã được IdP phát hành và client kiểm tra theo OIDC**; đoạn JSON một mình **không phải bằng chứng xác thực**. Phải xác minh chữ ký/thuật toán, issuer, audience/client ID, hạn sử dụng, nonce nếu luồng yêu cầu và các điều kiện khác trước khi tin giá trị.

Nên lưu liên kết danh tính theo mô hình:

~~~text
internal_users
  id = usr_1042
  tenant_id = tenant_a
  status = ACTIVE
  display_name = Lan Nguyen

external_identity_links
  issuer = https://idp.company.example/realms/staff
  subject = 9a2b-user-451
  internal_user_id = usr_1042
  linked_at = ...
  link_status = ACTIVE
  last_verified_at = ...
~~~

Một người có thể có **nhiều liên kết ngoài** (ví dụ IdP nhân sự và IdP nhà thầu) nhưng tất cả phải qua quy trình liên kết được phê duyệt. Thiết lập ràng buộc **UNIQUE (issuer, subject)** cho các liên kết đang có hiệu lực và khóa ngoại tới tài khoản nội bộ. Nếu có nhiều tenant, ràng buộc cả tenant/IdP registration và chính sách tin cậy vào dữ liệu, thay vì chỉ nối chuỗi issuer-sub một cách mơ hồ.

### Các claim không phù hợp làm khóa duy nhất

- `email` có thể đổi, bị tái sử dụng, trùng giữa nhiều IdP và **không được OIDC bảo đảm duy nhất**. `email_verified=true` chỉ nói IdP đã có bước xác minh quyền kiểm soát email theo cơ chế của họ tại một thời điểm; **không** chứng minh email là định danh vĩnh viễn hoặc chủ sở hữu luôn còn được phép sử dụng hệ thống.
- `preferred_username`, `name`, `given_name` chủ yếu là dữ liệu mô tả, có thể đổi và không duy nhất.
- `groups`/`roles` là dữ liệu phục vụ đánh giá quyền, thường thay đổi theo cơ cấu tổ chức, không phải khóa danh tính.
- `sub` đơn lẻ không đủ khi có nhiều issuer. Nếu đổi IdP, đổi issuer URL hoặc chuyển tenant, cần chiến lược liên kết/migration với bằng chứng rõ ràng.

### Khi nào được liên kết theo email?

Chỉ trong một **quy trình chứng minh quyền sở hữu tài khoản** được thiết kế: chẳng hạn người dùng đã xác thực tài khoản nội bộ qua phiên hiện có, sau đó chủ động liên kết thêm IdP; hoặc quy trình quản trị được phê duyệt với đối chiếu danh tính đáng tin. Không tự động nối hai tài khoản chỉ vì có email giống nhau, kể cả cùng hiển thị `email_verified=true`. Nếu không tìm thấy liên kết, trạng thái nên là **unlinked/denied** hoặc chuyển qua onboarding rõ ràng, chứ không tùy tiện dùng một tài khoản có sẵn.

## 4. Đầu vào đáng tin cậy: xác minh token trước, ánh xạ claim sau

Một dịch vụ nhận chuỗi JWT từ HTTP header không được chỉ dùng Base64 decode rồi đọc `sub` hoặc `roles`. Dữ liệu ở tầng này vẫn do client gửi, nên phải kiểm tra qua cơ chế của Spring Security trước khi quyết định identity.

### OIDC login (browser)

Client OIDC dùng discovery/client registration và xử lý authorization code. ID Token phải được kiểm chứng theo quy định OIDC: chữ ký, `iss`, `aud`, `exp`, nonce, các ràng buộc liên quan đến client/luồng. Nếu gọi UserInfo Endpoint, cần bảo đảm `sub` trong UserInfo khớp chủ thể của ID Token. Sau bước đó, `OidcUser`/`OidcIdToken` mới là nguồn claims để liên kết với tài khoản.

### OAuth2 resource server (API)

Một API có thể nhận **JWT access token** hoặc **opaque token**. Với JWT, resource server cần xác thực chữ ký bằng khóa đã tin, thuật toán, `iss`, `exp`, `nbf` và **`aud` đúng API**, đồng thời chính sách loại token nếu môi trường có nhiều loại token. Trong Spring Security, cấu hình `issuer-uri` có thể cung cấp issuer/JWK validation mặc định nhưng **không nên giả định audience của API được kiểm tra tự động trong mọi phiên bản/cấu hình**; cần cấu hình rõ validator hoặc property audience phù hợp framework đang dùng.

Với opaque token, resource server dùng token introspection theo hợp đồng IdP để xác nhận token còn hiệu lực và nhận các attribute được phép. Không phải token nào cũng là JWT; đừng cố decode opaque token thành JSON.

**Chỉ sau khi xác thực token**, mapping mới có đủ căn cứ để xử lý claims. Nếu thiếu `iss`, `sub`, audience không hợp lệ, issuer không được tin hoặc token đã hết hạn, phải từ chối từ bước authentication/validation. Không sửa token hay đổi giá trị claims để “lách” kiểm tra.

### Luồng nên thực hiện

~~~text
HTTP request / OAuth2 callback
          │
          ▼
OAuth2 client / Resource Server authentication
  - verify cryptographic signature / introspection
  - validate issuer, audience, time, token purpose
          │
          ▼
Canonical external identity = (trusted issuer, subject)
          │
          ▼
Resolve local account link + tenant + status
          │
          ├── No link / locked / disabled → deny or explicit onboarding
          │
          ▼
Derive internal permissions from trusted policy
          │
          ▼
Create Spring Authentication / internal principal view
          │
          ▼
Enforce resource-level authorization
~~~

## 5. Chính sách ánh xạ quyền: nguồn nào quyết định quyền gì?

Có ít nhất ba chiến lược hợp lệ, tùy mức kiểm soát của ứng dụng:

| Chiến lược | Nguồn quyền | Nên áp dụng khi | Rủi ro cần quản trị |
|---|---|---|---|
| **Quyền nội bộ là nguồn sự thật** | DB/policy service của ứng dụng, IdP chỉ cung cấp danh tính. | Quyền nghiệp vụ quan trọng, cần offboarding/duyệt quyền riêng. | Đồng bộ trạng thái account, cache/tra cứu quyền mỗi request. |
| **Ánh xạ group/role IdP qua allowlist** | Group được cấp bởi issuer đáng tin, chuyển qua bảng mapping hữu hạn. | Tổ chức có group quản trị tập trung, semantics rõ. | Claim group thiếu, trùng tên giữa tenant, nested group, quyền stale. |
| **Kết hợp** | Identity IdP + group signal, nhưng quyết định cuối dựa policy/account nội bộ. | Hệ thống cần RBAC/ABAC cùng quản trị trung tâm. | Phải định nghĩa rõ thứ tự ưu tiên và xung đột. |

Ví dụ bảng mapping được phê duyệt:

| Trusted IdP group | Điều kiện bổ sung | Spring authority nội bộ |
|---|---|---|
| `finance-readers` | Account active; tenant = A | `APP_INVOICE_READ` |
| `finance-approvers` | Account active; thuộc đúng cost center | `APP_INVOICE_APPROVE` |
| `hr-admins` | Kiểm soát bổ sung bởi ứng dụng | `APP_EMPLOYEE_ADMIN` |
| Claim `role=admin` không có trong policy | Không khớp danh sách cho phép | Không cấp quyền đặc biệt |

Không cấp nguyên mọi giá trị `groups` hoặc `roles` thành `ROLE_...` nếu chưa biết issuer, namespace, ngữ nghĩa, quyền truy cập và vòng đời. Tên `admins` ở một tenant không được trở thành admin ở tenant khác. Cũng không nên biến OAuth scope `openid` hoặc `profile` thành quyền nghiệp vụ “xem mọi hồ sơ”.

Spring Security dùng `GrantedAuthority` là chuỗi quyền cuối cùng của request, còn các kiểm tra theo đối tượng thường cần thêm điều kiện nghiệp vụ: `APP_INVOICE_APPROVE` có thể cần **hóa đơn thuộc đơn vị được phân công**, trạng thái cho phép phê duyệt và hạn mức của người dùng. Có thể dùng method security/authorization service để kiểm tra thay vì chỉ dựa `hasAuthority(...)` ở URL.

**Nguyên tắc cập nhật:** claim trong token là snapshot tại thời điểm phát hành. Khi user bị bỏ khỏi group hoặc account bị khóa, token/session đã tồn tại có thể giữ thông tin cũ đến khi hết hạn hoặc hệ thống nạp lại. Cần xác định token TTL, session expiry, quyền revoke, kiểm tra tài khoản nội bộ theo tần suất và hành vi khi IdP/DB tạm thời không sẵn sàng.

## 6. Spring Security: ba kiểu Authentication cần phân biệt

Trong ứng dụng **Servlet, Spring Security 6.x / Spring Boot 3.x**, các cấu hình thường gặp:

1. **`oauth2Login()` với OIDC:** sau đăng nhập trình duyệt, `OAuth2AuthenticationToken` chứa `OidcUser`. `OidcUser.getIdToken()` và `getClaims()` cho phép đọc nguồn OIDC đã xác thực; Spring Security có thể ánh xạ authorities trong user service hoặc `GrantedAuthoritiesMapper`.
2. **`oauth2ResourceServer().jwt()`:** API xác thực JWT access token; mặc định `Authentication.getPrincipal()` là `Jwt` và `getName()` thường là `sub`. `JwtAuthenticationConverter` có thể đổi authorities và tên hiển thị của `Authentication`; nếu cần object principal nội bộ, dùng converter/wrapper phù hợp phiên bản hoặc một internal identity view trong service.
3. **`oauth2ResourceServer().opaqueToken()`:** API introspect opaque token. Thông tin chủ thể và authorities có thể được ánh xạ qua introspector/converter tùy tích hợp, nhưng phải giữ yêu cầu xác thực token và đối chiếu issuer/authorization server.

Các kiểu trên là **những điểm mở rộng khác nhau**. Đoạn cấu hình cho OIDC login không tự chạy cho bearer JWT, và `JwtAuthenticationConverter` không tự tác động đến `OidcUser` tạo bởi `oauth2Login()`. Không lấy code của một luồng để thay cho luồng khác chỉ vì cả hai đều có claim `sub`.

## 7. Ví dụ A: ánh xạ OIDC login thành principal nội bộ

Ví dụ dưới đây minh họa **ý tưởng tích hợp trong một dự án Spring Boot Servlet có Spring Security OAuth2 Client**. Các interface `AccountLinkRepository`, `LocalAccount` là hợp đồng ứng dụng phải tự cài đặt. Đây là mã cấu hình tích hợp, **không phải chương trình `javac` độc lập**.

Dependency điển hình:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
~~~

Cấu hình issuer/client qua Spring Boot (giá trị minh họa, lấy client secret từ secrets manager):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: "configured-outside-source"
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://idp.company.example/realms/staff
~~~

### 7.1. Định nghĩa hợp đồng ánh xạ account

~~~java
public record LocalAccount(
        String id,
        boolean active,
        java.util.Set<String> permissionCodes
) {}

public interface AccountLinkRepository {
    // Chỉ trả user khi issuer+subject liên kết duy nhất, đúng tenant
    java.util.Optional<LocalAccount> findByExternalIdentity(
            String issuer, String subject);
}
~~~

Trong sản phẩm thật, cần định nghĩa tenant từ registration/boundary tin cậy và kiểm soát tính duy nhất của mapping. Không nên dùng email làm khóa cho method này.

### 7.2. OIDC user service và internal principal

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class InternalOidcSecurityConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> internalOidcUserService(
            AccountLinkRepository accounts) {
        var delegate = new OidcUserService();

        return request -> {
            // Spring Security OIDC client đã xác thực ID Token ở bước trước
            OidcUser external = delegate.loadUser(request);
            String issuer = external.getIdToken().getClaimAsString("iss");
            String subject = external.getIdToken().getSubject();

            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_external_identity"));
            }

            LocalAccount local = accounts
                    .findByExternalIdentity(issuer, subject)
                    .filter(LocalAccount::active)
                    .orElseThrow(() -> new OAuth2AuthenticationException(
                            new OAuth2Error("account_not_linked_or_disabled")));

            var granted = new LinkedHashSet<GrantedAuthority>();
            // permissionCodes phải được chọn từ allowlist nội bộ
            for (String permission : local.permissionCodes()) {
                granted.add(new SimpleGrantedAuthority(permission));
            }

            return new InternalOidcPrincipal(
                    external, local.id(), granted);
        };
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> internalOidcUserService)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
                .anyRequest().authenticated());

        http.oauth2Login(login -> login
                .userInfoEndpoint(userInfo ->
                        userInfo.oidcUserService(internalOidcUserService)));

        return http.build();
    }

    public record InternalOidcPrincipal(
            OidcUser external,
            String internalUserId,
            Collection<? extends GrantedAuthority> authorities
    ) implements OidcUser {

        @Override
        public String getName() {
            return internalUserId;
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

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
    }
}
~~~

**Giải thích:** user service gọi `OidcUserService` chuẩn để lấy OIDC user, lấy `iss` và `sub` từ **ID Token đã được framework kiểm tra**, tra cứu account nội bộ, kiểm tra `active`, rồi tạo principal nội bộ có `getName()` là `usr_...` thay vì tên từ IdP. `OidcUser` wrapper vẫn giữ ID Token/UserInfo để các thành phần OIDC khác có thể truy cập khi cần. Mã ví dụ cần file `LocalAccount.java` và `AccountLinkRepository.java` có nội dung ở phần 7.1, cùng implementation repository; các class Java public phải được tổ chức đúng package/file tên.

**Điểm production cần thêm:** kiểm tra tenant IdP/registration cho đúng kết nối, mapping permission codes từ nguồn tin cậy, xử lý timeout khi tra account, chính sách re-check status/session, unit/integration tests và biểu diễn lỗi login phù hợp. `account_not_linked_or_disabled` nên được chuyển thành thông báo tổng quát cho người dùng, không tiết lộ tài khoản cụ thể. Không để repository trả quyền admin dựa trên một request parameter hay claim chưa được phê duyệt.

### 7.3. Truy cập principal trong controller

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    @GetMapping("/me")
    public String me(
            @AuthenticationPrincipal
            InternalOidcSecurityConfig.InternalOidcPrincipal principal) {
        return principal.internalUserId();
    }
}
~~~

Khi external link giải quyết được đến `usr_1042`, GET `/me` trả chuỗi `usr_1042`. Đây là phản hồi minh họa có điều kiện, không có token/login thực trong đoạn code. Tránh trả nguyên `external.getClaims()` cho frontend nếu không cần: token có thể chứa dữ liệu cá nhân và thông tin nội bộ.

### 7.4. Khi chỉ cần đổi authorities mà không cần đổi principal

Nếu yêu cầu chỉ là ánh xạ một nhóm IdP sang các `GrantedAuthority`, `GrantedAuthoritiesMapper` là điểm mở rộng gọn hơn. Mapper nhận `OidcUserAuthority` (bao gồm ID Token/UserInfo) hoặc `OAuth2UserAuthority` cùng các quyền `SCOPE_...`, trả bộ quyền đã ánh xạ. Nhưng mapper **không tự thay danh tính trong `OidcUser.getName()`** và khó lấy thêm external resource nếu thiếu access token trong ngữ cảnh. Khi phải tra account nội bộ và xây principal tùy biến, dùng chiến lược `OAuth2UserService<OidcUserRequest, OidcUser>` như trên.

## 8. Ví dụ B: Resource Server JWT tạo Authentication theo user ID nội bộ

API có thể xác minh access token và dùng `JwtAuthenticationConverter` để cấp `GrantedAuthority`. Nếu muốn `Authentication.getName()` là internal user ID, có thể cung cấp custom converter trả `JwtAuthenticationToken` với tham số `name`; **principal object vẫn là Jwt**, trừ khi triển khai converter/principal wrapper sâu hơn.

Ví dụ tích hợp với Spring Security Resource Server, trong một ứng dụng API khác hoặc một `SecurityFilterChain` riêng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.company.example/realms/staff
~~~

Cấu hình này thiết lập issuer discovery/JWT validation cơ bản trong Spring Security. Cần thêm kiểm tra audience đúng API `orders-api`, thuật toán và các claim nghiệp vụ cần thiết theo chính sách của hệ thống. **Không xem YAML ví dụ là cấu hình bảo mật hoàn chỉnh cho sản phẩm thật.**

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiJwtSecurityConfig {

    @Bean
    Converter<Jwt, ? extends AbstractAuthenticationToken> internalJwtConverter(
            AccountLinkRepository accounts) {
        return jwt -> {
            // Chỉ được gọi sau khi JwtDecoder xác thực token.
            String issuer = jwt.getClaimAsString("iss");
            String subject = jwt.getSubject();

            if (issuer == null || subject == null) {
                throw new org.springframework.security.oauth2.core.OAuth2AuthenticationException(
                    new org.springframework.security.oauth2.core.OAuth2Error(
                        "invalid_external_identity"));
            }

            LocalAccount local = accounts
                    .findByExternalIdentity(issuer, subject)
                    .filter(LocalAccount::active)
                    .orElseThrow(() ->
                        new org.springframework.security.oauth2.core.OAuth2AuthenticationException(
                            new org.springframework.security.oauth2.core.OAuth2Error(
                                "account_not_linked_or_disabled")));

            var authorities = new LinkedHashSet<GrantedAuthority>();
            for (String permission : local.permissionCodes()) {
                authorities.add(new SimpleGrantedAuthority(permission));
            }

            // Trong API: Authentication.getName() là ID nội bộ.
            // Authentication.getPrincipal() ở đây vẫn là Jwt.
            return new JwtAuthenticationToken(jwt, authorities, local.id());
        };
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            Converter<Jwt, ? extends AbstractAuthenticationToken> internalJwtConverter)
            throws Exception {

        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/read")
                    .hasAuthority("APP_ORDER_READ")
                .requestMatchers("/api/orders/approve")
                    .hasAuthority("APP_ORDER_APPROVE")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(jwt ->
                    jwt.jwtAuthenticationConverter(internalJwtConverter)));

        return http.build();
    }
}
~~~

Ví dụ trên dùng cùng `LocalAccount` và `AccountLinkRepository` ở phần trước; đây là cấu hình **Servlet** và cần môi trường IdP/JWKS + DB thực để chạy end-to-end. Thực tế phải bảo đảm `aud` của JWT đúng API đang nhận, access token không bị dùng như ID Token, và issuer thuộc đúng nhóm nhà cung cấp tin cậy; có thể dùng validator của `JwtDecoder` hoặc cấu hình phiên bản tương ứng. Mọi logic cấp quyền phải lấy từ nguồn hợp lệ, tuyệt đối không dùng mã người dùng trong request làm `name`.

### Phân biệt đổi tên và đổi principal object

- `JwtAuthenticationConverter.setPrincipalClaimName(...)` chỉ thay **claim dùng đặt tên** cho Authentication; không tự tra user nội bộ. Không được đặt nó vào một claim `internal_user_id` chưa có hợp đồng tin cậy để rồi tin giá trị.
- Constructor `new JwtAuthenticationToken(jwt, authorities, local.id())` đổi tên `Authentication.getName()` sang ID nội bộ, nhưng `getPrincipal()` vẫn là `Jwt` trong cách dùng này.
- Nếu code nghiệp vụ muốn một object `InternalPrincipal` chứa tenant/status/permissions, có thể đưa vào một abstraction request-scoped đã được xây từ mapping tin cậy, hoặc custom converter/principal phù hợp phiên bản Spring Security. Không ép API và OIDC login phải cùng một kiểu principal Java nếu mô hình bảo mật và lifecycle của hai luồng khác nhau.

## 9. Ví dụ Java 17 độc lập: chứng minh vì sao không link bằng email

Đoạn sau **chạy được bằng JDK 17 thuần**, không dùng Spring hay IdP. Nó chỉ minh họa thuật toán liên kết theo cặp issuer/subject và quyền từ tài khoản nội bộ; **không tự xác minh chữ ký hay thời hạn token**. Đầu vào của hàm phải đến từ tầng authentication đã kiểm chứng trong ứng dụng thật.

~~~java
import java.util.Map;
import java.util.Set;

public class ExternalIdentityMappingDemo {
    record ExternalIdentity(String issuer, String subject, String email) {}
    record LocalUser(String id, boolean active, Set<String> permissions) {}

    public static void main(String[] args) {
        Map<String, LocalUser> links = Map.of(
            "https://idp-a.example|user-17",
            new LocalUser("usr_1042", true, Set.of("APP_ORDER_READ")),

            "https://idp-b.example|user-17",
            new LocalUser("usr_2099", true, Set.of("APP_ORDER_APPROVE"))
        );

        ExternalIdentity a = new ExternalIdentity(
            "https://idp-a.example", "user-17", "lan@example.test");
        ExternalIdentity b = new ExternalIdentity(
            "https://idp-b.example", "user-17", "lan@example.test");

        for (ExternalIdentity external : new ExternalIdentity[] {a, b}) {
            LocalUser local = links.get(
                external.issuer() + "|" + external.subject());
            if (local == null || !local.active()) {
                throw new SecurityException("account denied");
            }
            System.out.println(local.id() + " -> "
                + local.permissions().stream().sorted().toList());
        }
    }
}
~~~

Lưu thành tệp `ExternalIdentityMappingDemo.java` và chạy:

~~~bash
javac ExternalIdentityMappingDemo.java
java ExternalIdentityMappingDemo
~~~

Stdout chính xác:

~~~text
usr_1042 -> [APP_ORDER_READ]
usr_2099 -> [APP_ORDER_APPROVE]
~~~

Hai danh tính có cùng `sub=user-17` và `email=lan@example.test`, nhưng khác issuer nên liên kết với **hai tài khoản khác nhau**. Nếu chỉ dùng email hoặc subject đơn lẻ làm khóa, thuật toán sẽ nhập nhầm hai danh tính. Trong hệ thống thật, lưu khóa gồm các trường riêng trong DB và chuẩn hóa issuer theo client registration, không dùng một chuỗi ghép dấu `|` làm khóa production.

## 10. Thực hành phân tách OAuth scope, IdP group và quyền nghiệp vụ

Giả sử công ty có ba API: đọc đơn hàng, phê duyệt đơn hàng và quản lý người dùng. IdP phát hành access token với một số dữ liệu:

~~~json
{
  "iss": "https://idp.company.example/realms/staff",
  "sub": "external-778",
  "aud": ["orders-api"],
  "scope": "openid profile orders.read",
  "groups": ["sales-team", "approvers"]
}
~~~

Một cách đánh giá phù hợp:

1. Resource server xác thực JWT, kiểm tra `iss`, `aud=orders-api`, thời hạn và các điều kiện token. `openid`/`profile` **không** tự là quyền xem đơn hàng.
2. Đọc `(iss,sub)` để tìm `usr_1042` và tenant tương ứng, kiểm tra active.
3. Nếu `orders.read` là scope được API tin từ issuer cho client này, có thể dùng nó làm `SCOPE_orders.read`; phải kiểm tra semantics, tránh chuyển scope thành quyền không liên quan.
4. Group `approvers` chỉ là input bổ sung. Muốn cấp `APP_ORDER_APPROVE` phải map theo allowlist có tenant, app và nhóm được phép, hoặc theo bảng nội bộ. Không “cộng dồn mọi group” thành admin.
5. Với lệnh phê duyệt, còn kiểm tra đơn hàng có thuộc phạm vi người dùng và ở trạng thái cho phép hay không.

Trong Spring Security resource server JWT, cách mặc định thường biến `scope`/`scp` thành `SCOPE_...`. Nếu issuer dùng claim `authorities`, `roles` hoặc một cấu trúc lồng nhau, có thể dùng `JwtGrantedAuthoritiesConverter` (set tên claim/prefix) hay một custom converter. Nhưng **cấu hình này phải thể hiện mapping đã được phê duyệt**; đừng đọc mọi claim có tên `roles` rồi gán trực tiếp `ROLE_ADMIN` không kiểm tra issuer/tenant.

~~~java
// Ví dụ khi claim "roles" chỉ chứa mã role ĐÃ ĐƯỢC CHO PHÉP
var roles = new org.springframework.security.oauth2.server.resource
    .authentication.JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
~~~

Đoạn cấu hình này **không chạy độc lập** và chỉ minh họa API của converter; với nhiều IdP cần kiểm soát giá trị claim theo chính sách và chỉ gán các quyền được chấp thuận. Trong kiến trúc dùng principal nội bộ, converter ở phần 8 có thể chỉ lấy permissions từ local account, tránh nhập nhằng quyền ngoài.

## 11. Xử lý account lifecycle, provisioning và liên kết nhiều IdP

### 11.1. Người dùng đăng nhập lần đầu nhưng chưa có local account

Chọn một chính sách nhất quán:

- **Invite/provision trước:** quản trị viên cấp account và liên kết `(iss,sub)` trước khi người dùng đăng nhập; thiếu liên kết thì từ chối hoặc hướng dẫn onboarding.
- **JIT provisioning:** chỉ tạo account mới khi issuer/tenant/group đáp ứng điều kiện cho phép và định danh đã được kiểm tra; mặc định quyền tối thiểu, không tự tìm account theo email để ghép.
- **SCIM / đồng bộ HRIS:** hệ thống quản lý nhân sự hoặc dịch vụ provisioning tạo/khóa account theo vòng đời; bước login chỉ xác thực và liên kết với record đã có.

Mỗi chính sách phải có chống tạo trùng khi đăng nhập đồng thời, ràng buộc unique ở DB, idempotency, audit và cơ chế sửa liên kết sai.

### 11.2. Người dùng đổi email, đổi tên hoặc chuyển IdP

Đổi email hoặc name là thay đổi profile, **không thay khóa tài khoản nội bộ** nếu `(iss,sub)` còn như cũ. Khi thay issuer, realm, tenant hoặc subject strategy (ví dụ pairwise), thực hiện migration/liên kết có bằng chứng và xác nhận; không tự nối tài khoản bằng email giống nhau. Có thể lưu nhiều external identity link cho một internal user nếu policy cho phép.

### 11.3. Người dùng bị khóa hoặc thu hồi quyền

Khi account local chuyển `DISABLED`, mapping phải chặn tạo phiên mới. Với session/token đang tồn tại, cần chiến lược revalidation, revoke session, token TTL và cache invalidation; thay đổi IdP group không đảm bảo mọi session cũ tự cập nhật ngay. API có yêu cầu rất cao về thu hồi quyền nên kiểm tra authorization nguồn nội bộ tại thời điểm nhạy cảm, phù hợp hiệu năng và độ sẵn sàng.

### 11.4. Khi IdP không trả group claim

Một số IdP giới hạn kích thước token hoặc cung cấp group qua API riêng. Mất claim group không nên biến thành quyền cao mặc định. Thiết kế chính sách: thiếu nguồn quyền cần thiết thì deny hoặc chỉ cấp quyền nội bộ đã kiểm chứng; nếu phải gọi API nhóm, dùng token/scope thích hợp, timeout và cache có hạn, đồng thời kiểm tra tenant/issuer.

## 12. Threat model: các lỗi ánh xạ danh tính và quyền phổ biến

| Tình huống | Lỗi thiết kế | Hậu quả | Biện pháp |
|---|---|---|---|
| Người A và B có cùng email theo thời gian | Link account theo `email` | Người mới nhận dữ liệu của người cũ | Link bằng `iss+sub` và quy trình chuyển giao được duyệt. |
| Hai IdP có `sub` giống nhau | Dùng `sub` đơn lẻ | Nhập nhầm account giữa IdP | Khóa gồm issuer đã kiểm chứng + subject. |
| API đọc ID Token thay access token | Chỉ xem JWT có chữ ký | Token sai audience/purpose được dùng tại API | Ràng buộc loại token, `aud`, issuer và validator. |
| Ứng dụng nhận `roles=["ADMIN"]` bất kỳ | Map thẳng role claim | Leo thang quyền | Allowlist issuer/tenant/group/policy, ưu tiên nguồn quyền nội bộ. |
| Group chuyển đổi nhưng session lâu hết hạn | Cấp quyền từ snapshot cũ | Giữ quyền đã thu hồi | TTL, refresh/recheck, session invalidation. |
| IdP tạm thời lỗi | “Tạm cho admin để không gián đoạn” | Mở rộng quyền ngoài kiểm soát | Fail closed, có cache TTL và policy rõ ràng. |
| `email_verified=true` | Dùng làm bằng chứng đủ để ghép account | Account takeover khi tái sử dụng email | Xác minh sở hữu local account trước khi link. |
| Nhiều tenant dùng group `admins` | Bỏ qua tenant của issuer | Cross-tenant privilege escalation | Bind issuer/tenant/registration vào mapping và policy. |
| Client tự gửi claim qua HTTP header | Bỏ qua token validation | Giả mạo danh tính | Chỉ nhận claim từ token/assertion đã xác minh. |
| Token có audience khác | Chỉ kiểm tra issuer | Token cấp cho API A bị dùng ở API B | Validate audience và token purpose tại từng API. |
| Tài khoản local bị disabled | Chỉ tin `sub` trong token | Tài khoản vẫn truy cập | Check account status trong authentication + policy cache. |

Một ID Token có `email_verified=true`, hoặc một JWT decode được trên một website công cộng, **không phải** bằng chứng nó hợp lệ với **ứng dụng và đối tượng nhận token hiện tại**.

## 13. Checklist kiểm thử ở tầng identity, claims và quyền

Kiểm thử nên độc lập từng ranh giới, bao gồm cả “happy path” và “deny path”:

| Test case | Kỳ vọng |
|---|---|
| `iss/sub` đúng, account linked và active | Xác thực thành công; principal nội bộ đúng `user_id`; authorities đúng policy. |
| Cùng `sub` ở hai issuer được chấp thuận | Ánh xạ hai identity khác nhau; không lẫn người dùng. |
| Cùng email nhưng khác `iss/sub` | Không tự merge account; cần liên kết chủ động. |
| Email thay đổi, `iss/sub` giữ nguyên | Giữ nguyên internal user; cập nhật profile theo policy. |
| Account linked nhưng disabled | Authentication thất bại hoặc bị chặn trước dữ liệu nghiệp vụ. |
| Không tìm thấy liên kết | Fail closed hoặc đi qua onboarding được thiết kế; không fallback admin. |
| Claim `roles=ADMIN` từ nguồn chưa được phép | Không cấp `ROLE_ADMIN`. |
| Thiếu group claim; account có quyền nội bộ độc lập | Áp dụng chính sách nguồn quyền đã định; không cấp thêm quyền suy đoán. |
| JWT hết hạn, chữ ký sai hoặc `iss` khác | Từ chối tại token validation, trước mapper. |
| JWT hợp lệ nhưng `aud` không phải API | Từ chối, không chuyển token sai đối tượng thành principal. |
| OAuth2 login thành công nhưng quyền không đủ | Người dùng được xác thực nhưng API/method bị 403 theo policy. |
| Group bị xóa trong IdP, session cũ còn | Quyền hết hiệu lực theo TTL/revalidation đã định; không giữ vô hạn. |
| External link đồng thời tạo hai lần | Unique constraint và transaction bảo đảm không có hai user cùng một link. |
| Multi-tenant với role trùng tên | Chỉ gán role cho tenant đúng. |
| Claim lồng nhau/kiểu dữ liệu không đúng | Mapping từ chối hoặc chọn policy mặc định an toàn; không ném lỗi lộ token. |

Với Spring Security có thể dùng MockMvc/Spring Security Test để kiểm tra điều kiện authorization mà không cần IdP cho từng test; bên cạnh đó cần bài test tích hợp thực với IdP giả lập/JWKS/redirect, repository và session lifecycle để chắc chắn `iss+sub` được liên kết như kỳ vọng. Đừng chỉ test rằng `hasRole("ADMIN")` hoạt động rồi bỏ qua kiểm thử **nguồn dữ liệu tạo ra ROLE_ADMIN**.

## 14. Vận hành và quan sát

Nên có audit event có tương quan request/session, ví dụ: thời điểm, trusted issuer ID/registration, subject đã chuẩn hóa (có thể pseudonymize trong log), mã user nội bộ, tenant, kết quả mapping và lý do từ chối ở mức không tiết lộ dữ liệu nhạy cảm. Tránh ghi raw ID Token, access token, refresh token hoặc toàn bộ profile claims vào log.

Theo dõi tỷ lệ login thành công, `account_not_linked`, sai audience, thay đổi group/authority bất thường, lỗi repository/IdP, timeout, cache hit và số phiên còn hiệu lực sau offboarding. Nếu cần đồng bộ nhiều hệ thống, quản trị phiên/revocation tại một cơ chế rõ ràng thay vì kỳ vọng claims trong token luôn là trạng thái thời gian thực.

Khi debug, đi theo thứ tự: **token/response có thực sự được xác thực không → issuer/subject xác định đúng chưa → có linked internal user duy nhất không → account active không → quyền đến từ đâu → resource policy có cho phép không**. Tránh đưa thông báo khác nhau như “email tồn tại” và “tài khoản đang chờ ghép” cho người dùng chưa xác thực nếu điều đó giúp dò danh tính.

## 15. Kết luận kiến trúc

- **IdP** chịu trách nhiệm chứng minh danh tính bên ngoài và phát hành thông tin đã được xác thực theo hợp đồng tin cậy.
- **Identity mapping** gắn khóa ngoài `(iss,sub)` vào **mã user nội bộ bất biến**, qua một bảng liên kết có quyền sở hữu và vòng đời rõ ràng.
- **Authorization** dựa trên authorities/policy mà ứng dụng công nhận, đồng thời xét tenant, trạng thái account và tài nguyên cụ thể.
- **Spring Security** là khung kết nối những tầng đó; `oauth2Login` và `oauth2ResourceServer` có các điểm mở rộng khác nhau, nên phải cấu hình đúng cho luồng được sử dụng.

Khi ranh giới rõ ràng, ứng dụng có thể thay IdP, đổi email, thêm nhà cung cấp đăng nhập hoặc đổi chính sách nhóm mà vẫn giữ `usr_1042` làm identity của dữ liệu nghiệp vụ và kiểm soát quyền nhất quán.

## Tài liệu tham khảo

1. [OpenID Connect Core 1.0 – Subject Identifier và Claim Stability](https://openid.net/specs/openid-connect-core-1_0-final.html): định danh `iss/sub`, ID Token, claim `email_verified` và pairwise subject.
2. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserService` và delegation-based mapping.
3. [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, scope/authorities và kiểm tra token.
4. [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`, `hasAuthority`, phân quyền theo HTTP request.
5. [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): mô hình claims của JWT access token, yêu cầu đối tượng nhận token và mục đích API.
