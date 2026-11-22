# Tùy chỉnh claims theo client, grant type, principal và tenant

> **Chương: Token và claims.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài tập trung vào cách thêm claims có kiểm soát dựa trên **client đã đăng ký**, **grant type đang thực hiện**, **principal đã xác thực** và **tenant đã được xác minh**; đồng thời phân biệt claims của access token, ID Token và UserInfo.

## 1. Vì sao cần tùy chỉnh claims?

Một access token thường cần mang đủ thông tin để Resource Server hiểu token được cấp cho ai, bởi client nào, trong ngữ cảnh nào và được phép làm gì. Spring Authorization Server đã tạo các claims chuẩn theo giao thức và token format. Tuy nhiên, ứng dụng thực tế có thể cần thêm dữ liệu như:

- Loại chủ thể: người dùng hay service account.
- Client đã yêu cầu và được cấp token.
- Grant type được dùng để cấp token.
- Tenant mà người dùng/service đang hoạt động trong giao dịch này.
- Phiên bản policy hoặc quyền để Resource Server hỗ trợ kiểm tra.
- Actor/delegation context khi một service hành động thay mặt người dùng.

Ví dụ:

- **Authorization Server:** `https://login.example.vn`.
- **Web client:** `portal-web`, đăng nhập người dùng qua Authorization Code + PKCE.
- **Machine client:** `billing-job`, lấy token bằng Client Credentials.
- **Tenant:** `tenant-a` hoặc `tenant-b`, mỗi tenant có dữ liệu đơn hàng riêng.
- **Resource Server:** `https://api.example.vn`, xác minh token và giới hạn truy cập theo audience, scope, subject và tenant.

Hai token có thể cùng được phát bởi một issuer nhưng mang ngữ cảnh khác nhau:

| Tình huống | Danh tính chính | Claim tùy chỉnh có thể hữu ích |
|---|---|---|
| Người dùng đăng nhập qua `portal-web` | End user | `tenant_id` đã xác minh, subject type, thông tin assurance nếu có |
| Service dùng Client Credentials | Client/service account | `client_id`, service identity, tenant gắn với service |
| Người dùng refresh token | Chủ thể của authorization gốc | Giữ đúng subject/tenant của authorization gốc; không coi refresh là đăng nhập mới |
| Token Exchange | Subject và actor đã được xác minh | `act`, delegation context, audience và scope theo policy |

**Tùy chỉnh claims là bước tạo nội dung token, không phải bước cấp quyền.** Trước khi customizer chạy, Authorization Server phải xác thực client, grant, subject, scope, consent và policy. Không dùng token customizer để biến một request không hợp lệ thành request được phép.

## 2. Claim là gì và nằm ở đâu?

Claim là một cặp tên/giá trị trong payload của JWT hoặc trong dữ liệu token/introspection tương ứng. Ví dụ payload access token JWT minh họa:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read",
  "iat": 1794825600,
  "exp": 1794825900,
  "https://claims.example.vn/tenant_id": "tenant-a",
  "https://claims.example.vn/subject_type": "user"
}
~~~

Đây là JSON minh họa, **không phải JWT đã ký**. Một số claim như `iss`, `sub`, `aud`, `iat` và `exp` là claim chuẩn; `client_id` được dùng trong JWT Access Token Profile. Hai claim có tên URI là private claim do tổ chức định nghĩa để giảm nguy cơ trùng tên.

### 2.1. Các nhóm claim cần phân biệt

| Nhóm | Ví dụ | Ai quyết định? |
|---|---|---|
| **JWT registered claims** | `iss`, `sub`, `aud`, `exp`, `iat`, `jti` | Giao thức và Authorization Server |
| **OAuth access token claims** | `client_id`, `scope`, `cnf` | Authorization Server, theo profile và cơ chế sender-constraining |
| **OIDC ID Token claims** | `nonce`, `auth_time`, `acr`, `amr` | OpenID Provider dựa trên giao dịch và bằng chứng xác thực |
| **Private/application claims** | `tenant_id`, `subject_type`, policy version | Chính sách nội bộ đã được kiểm chứng |
| **Delegation claims** | `act`, `may_act` theo profile | Authorization Server dựa trên quan hệ ủy quyền đã xác minh |

Không đặt mọi dữ liệu vào cùng một token. Access token dành cho Resource Server; ID Token dành cho OIDC Relying Party; UserInfo là endpoint trả thông tin người dùng theo scope/authorization. Một claim hữu ích cho API không nhất thiết nên xuất hiện trong ID Token.

### 2.2. Claim name và quy tắc đặt tên

RFC 7519 phân biệt registered claim names, public claim names và private claim names. Khi định nghĩa claim riêng:

- Ưu tiên tên có namespace do tổ chức kiểm soát, ví dụ `https://claims.example.vn/tenant_id`.
- Giữ tên, kiểu dữ liệu và ý nghĩa ổn định giữa các phiên bản.
- Không dùng tên dễ đụng với claim chuẩn như `iss`, `sub`, `aud`, `exp`, `iat`, `nonce` hoặc `scope`.
- Không đặt claim chứa password, client secret, private key, refresh token, dữ liệu thanh toán hoặc thông tin cá nhân không cần thiết.
- Tài liệu hóa claim là string, number, boolean hay array; Resource Server phải validate kiểu dữ liệu, không ép kiểu tùy tiện.
- Tránh đổi ý nghĩa claim mà không version hóa; token cũ có thể còn hiệu lực sau khi code mới đã triển khai.

Tên URI trong payload là **tên claim**, không có nghĩa Resource Server phải gọi URL đó. Đây là namespace chống va chạm, không phải endpoint tra cứu.

## 3. Những ngữ cảnh Spring Authorization Server cung cấp

Spring Authorization Server cung cấp `OAuth2TokenCustomizer<T>` để tùy chỉnh token context trước khi token được encode/phát hành. Khi dùng JWT generator, điểm mở rộng thường dùng là:

~~~java
OAuth2TokenCustomizer<JwtEncodingContext>
~~~

`JwtEncodingContext` cung cấp ngữ cảnh đáng tin cậy do Authorization Server tạo, bao gồm các thông tin quan trọng:

| API | Ý nghĩa | Cách dùng an toàn |
|---|---|---|
| `getRegisteredClient()` | Client đã được tìm thấy và xác thực theo luồng hiện tại | Chọn policy theo `clientId`/đăng ký, không lấy client từ query |
| `getAuthorizationGrantType()` | Grant type đang được xử lý | Phân nhánh logic token theo grant |
| `getPrincipal()` | Authentication gắn với grant/token generation | Dùng sau khi xác định principal là user hay client |
| `getAuthorization()` | Authorization record liên quan nếu có | Đọc subject, authorization attributes và ngữ cảnh đã lưu |
| `getAuthorizedScopes()` | Các scope được authorize cho token context | Không thay bằng danh sách scope tự lấy từ request |
| `getTokenType()` | Loại token đang được tạo, ví dụ access token hoặc ID Token | Không đưa claim access token sang ID Token một cách vô điều kiện |
| `getClaims()` | Builder cho JWT claims | Chỉ thêm claim sau khi policy đã xác minh |
| `getAuthorizationGrant()` | Authentication object của grant hiện tại | Dùng khi cần dữ liệu grant-specific, nhưng vẫn kiểm tra kiểu và trust boundary |

Một customizer nên đọc thông tin từ context đã được xác thực và các service policy đáng tin. **Không** đọc trực tiếp HTTP request trong customizer để lấy `tenant_id`, `role`, `audience` hay `scope` rồi đưa vào token.

### 3.1. Luồng tạo token và vị trí customizer

~~~mermaid
flowchart TD
    Request["Token request"] --> Auth["Xác thực client"]
    Auth --> Grant["Kiểm tra grant, code/refresh token và principal"]
    Grant --> Policy["Kiểm tra scope, consent, audience, tenant và authorization"]
    Policy -->|Từ chối| Deny["OAuth2 error, không phát token"]
    Policy -->|Hợp lệ| Context["Tạo OAuth2TokenContext"]
    Context --> Generator["OAuth2TokenGenerator"]
    Generator --> Customizer["OAuth2TokenCustomizer<JwtEncodingContext>"]
    Customizer --> Sign["Ký JWT bằng khóa của Authorization Server"]
    Sign --> Store["Lưu authorization/token state"]
    Store --> Response["Trả token response"]
~~~

Vị trí customizer nằm trong quá trình tạo token. Nó có thể thêm claims, nhưng không nên là nơi duy nhất xác định client có được truy cập tenant hay scope hay không. Việc authorization phải được quyết định trước đó; Resource Server tiếp tục kiểm tra token và policy API.

## 4. Phân biệt access token, ID Token, UserInfo và opaque token

### 4.1. Access token JWT

Access token JWT được Resource Server dùng để xác minh quyền truy cập. Những claim có thể hữu ích:

- `iss`: issuer của Authorization Server.
- `sub`: subject của token theo profile phát hành.
- `aud`: Resource Server hoặc resource được token dành cho.
- `client_id`: client đã yêu cầu token.
- `scope`: phạm vi được cấp.
- `tenant_id`: tenant đã được xác minh và gắn với authorization.
- `act`: actor/delegation context nếu profile và use case yêu cầu.

Không thêm thông tin hồ sơ người dùng dài dòng vào access token chỉ để API khỏi tra cứu. Token có thể xuất hiện trong nhiều service, trace và thiết bị; càng ít dữ liệu thì tác động khi lộ token càng thấp.

### 4.2. OIDC ID Token

ID Token chứng minh kết quả xác thực người dùng cho RP. Các claim như `iss`, `sub`, `aud`, `exp`, `iat` và `nonce` có ngữ nghĩa giao thức. `auth_time` phải phản ánh thời điểm active authentication thực tế khi được yêu cầu; không đặt bằng thời điểm token vừa được ký. `acr`/`amr` phải dựa trên mức/phương thức xác thực đã thực hiện, không tự gán để làm hài lòng client.

Chỉ thêm custom claim vào ID Token khi RP thực sự cần và policy OIDC cho phép. Thông tin hồ sơ có thể phù hợp hơn với UserInfo endpoint, nơi server kiểm tra access token và scope trước khi trả claims.

### 4.3. UserInfo

UserInfo là OIDC endpoint trả claims về end user. Đây là một bề mặt khác với ID Token customizer. Khi cần tùy chỉnh claims UserInfo, sử dụng extension point của OIDC UserInfo endpoint (ví dụ mapper/handler tương ứng phiên bản) để:

- Kiểm tra access token và scope đã cấp.
- Chỉ trả thuộc tính người dùng được scope cho phép.
- Không tiết lộ tenant/profile của người khác.
- Giữ nhất quán `sub` với subject trong ID Token.
- Không dùng UserInfo để mở rộng quyền API hoặc thay Resource Server authorization.

### 4.4. Opaque access token

`OAuth2TokenCustomizer<JwtEncodingContext>` chỉ áp dụng khi token được tạo theo JWT encoding path. Nếu access token là **opaque/reference token**, Resource Server không đọc được JWT payload từ chuỗi token. Tùy biến claims cần đi theo token claims context/generator và cơ chế introspection tương ứng, ví dụ `OAuth2TokenClaimsContext` cho `OAuth2AccessTokenGenerator` trong Spring Authorization Server.

Không cấu hình JWT customizer rồi kỳ vọng claims xuất hiện trong mọi token format. Cần xác định rõ token generator nào đang được dùng và cách Resource Server nhận thông tin (JWT local validation hay introspection).

### 4.5. Refresh token

Refresh token thông thường là credential riêng, không phải access token JWT chứa business claims. Khi refresh, access token mới có thể được tạo lại; claims phải được tính từ authorization/principal/policy hiện hành và ngữ cảnh gốc đã lưu. Không mặc định mọi refresh là một lần đăng nhập mới hoặc cập nhật `auth_time`.

## 5. Tùy chỉnh claims theo client

Mỗi client có mục đích và mức tin cậy khác nhau. `portal-web` có thể cần claim tenant cho API đơn hàng, trong khi `billing-job` chỉ cần service identity. Không nên đưa cùng một tập claims vào mọi client.

### 5.1. Dùng RegisteredClient đã được xác thực

Ví dụ cấu hình hai client:

| Client | Grant type | Claims cần thiết theo policy |
|---|---|---|
| `portal-web` | Authorization Code, Refresh Token | `tenant_id` đã xác minh; subject type là user |
| `billing-job` | Client Credentials | Service identity; tenant gắn với client nếu được cấp; không giả mạo user |

Client identity nên lấy từ `context.getRegisteredClient().getClientId()`. Không dùng `client_name` hoặc logo hiển thị làm định danh bảo mật; các metadata hiển thị có thể thay đổi và không phải credential.

### 5.2. Chính sách claims do server quản lý

Có thể định nghĩa policy riêng:

~~~java
interface ClientClaimPolicy {
    boolean includeTenantClaim(String clientId);

    boolean includeGrantTypeClaim(String clientId);

    boolean includeSubjectTypeClaim(String clientId);
}
~~~

Implementation có thể lấy policy từ cấu hình quản trị hoặc registry nội bộ. Chỉ quản trị viên/automation được phép thay đổi policy; client không được tự gửi một tham số như `include_tenant=true` để bật claim. Với hệ thống lớn, policy nên có version, audit và cache invalidation.

### 5.3. Claim theo client không đồng nghĩa cấp quyền cho client

Nếu policy cho `portal-web` nhận `tenant_id`, điều đó chỉ quyết định claim nào được thêm sau khi tenant đã được xác minh. Nó không cho phép `portal-web` chọn bất kỳ tenant nào. Authorization Server vẫn phải kiểm tra người dùng thuộc tenant, client được phép truy cập tenant và yêu cầu hiện tại gắn đúng authorization.

Tương tự, việc thêm claim `role=admin` không cấp quyền admin hợp lệ. Nếu role được dùng trong authorization, role phải đến từ nguồn phân quyền đáng tin và Resource Server cần kiểm tra theo policy hiện hành.

## 6. Tùy chỉnh claims theo grant type

Grant type mô tả cách token được cấp và giúp xác định loại principal/context. Cần phân nhánh rõ thay vì suy luận tất cả token đều đại diện người dùng.

| Grant type | Chủ thể thường gặp | Điều cần tránh |
|---|---|---|
| `authorization_code` | Người dùng đã xác thực | Không lấy user từ query; không đặt tenant theo browser input chưa kiểm chứng |
| `refresh_token` | Chủ thể/authorization gốc | Không coi refresh là đăng nhập mới; không tự cập nhật `auth_time` |
| `client_credentials` | Confidential client/service account | Không tạo claim user hoặc `sub` người dùng giả |
| `urn:ietf:params:oauth:grant-type:token-exchange` | Subject và có thể actor | Chỉ dùng subject/actor sau khi token đầu vào và delegation policy đã xác minh |
| Device Authorization Grant | Người dùng đã hoàn tất xác thực trên thiết bị khác | Không lấy danh tính từ mã user code; dùng authorization record |
| Custom grant | Theo profile ứng dụng | Phải định nghĩa identity, authorization, claims và negative cases rõ ràng |

### 6.1. Client Credentials là service identity

Với Client Credentials, principal thường đại diện OAuth client đã xác thực, không phải end user. Token có thể chứa `client_id` và một private claim như `subject_type=service` nếu Resource Server cần phân biệt. Không gán `tenant_id` từ tham số tùy ý trong request; tenant phải gắn với cấu hình service hoặc authorization đã được phê duyệt.

### 6.2. Authorization Code và Refresh Token

Với Authorization Code, principal là người dùng sau khi login thành công. Tenant (nếu có) cần được xác định qua membership/directory và gắn với authorization transaction. Khi refresh, hãy dùng tenant đã lưu trong authorization gốc hoặc xác minh lại với nguồn authoritative; không dùng tenant của một request API bất kỳ.

### 6.3. Token Exchange

Với Token Exchange, subject token và actor token có thể mô tả hai thực thể khác nhau. Claims như `sub` và `act` phải được tạo từ subject/actor đã được xác minh và policy delegation. Không dùng một customizer chung để đọc `subject_token` raw từ HTTP request rồi tự decode. Việc xác minh token đầu vào và quyết định exchange thuộc token exchange provider/policy layer.

## 7. Tùy chỉnh claims theo principal và tenant

### 7.1. Principal không phải lúc nào cũng là người dùng

`Authentication.getPrincipal()` có thể đại diện `UserDetails`, một custom principal, OAuth2 client authentication hoặc principal của grant khác. Trước khi đọc thuộc tính, phải xác định grant type và kiểu principal. Không ép mọi principal thành `UserDetails` hoặc coi `getName()` là email.

Nên sử dụng định danh ổn định, ít dữ liệu cá nhân, ví dụ internal subject ID. Email/username có thể thay đổi hoặc được tái sử dụng; không nên là khóa phân quyền lâu dài nếu hệ thống có subject ID ổn định.

### 7.2. Tenant là ngữ cảnh đã được xác minh

Trong multi-tenant system, người dùng có thể là thành viên của nhiều tenant. Tenant được chọn cho một giao dịch phải được kiểm tra:

1. Principal đã xác thực và có subject ổn định.
2. Tenant tồn tại, đang hoạt động và thuộc tổ chức/issuer phù hợp.
3. Principal có membership/role hợp lệ trong tenant đó.
4. Client được phép hoạt động với tenant theo registration/policy.
5. Scope và resource request hợp lệ trong tenant.
6. Tenant được gắn vào authorization record hoặc một context server-side đáng tin để dùng lại khi refresh.

Không lấy `tenant_id` từ query string, header do browser tự đặt, hidden form field hoặc custom claim của token chưa xác minh. Nếu request mang tenant identifier, nó chỉ là **lựa chọn cần kiểm tra**, chưa phải bằng chứng quyền.

### 7.3. Gắn tenant với authorization transaction

Một cách triển khai là lưu tenant đã được xác minh vào authorization attributes khi authorization được tạo. Sau đó customizer đọc attribute từ authorization thay vì lấy từ request hiện tại. Tên attribute và cơ chế persistence là chi tiết ứng dụng; giá trị phải được tạo sau khi kiểm tra membership/client policy và được lưu an toàn qua các lần refresh.

Mô hình khái niệm:

~~~text
Authorization transaction:
  registered_client_id = registration-portal-web
  principal_name       = user-123
  grant_type           = authorization_code
  tenant_id            = tenant-a        # đã được xác minh
  tenant_policy_version= 12
  authorized_scopes    = [orders.read]
~~~

Khi refresh token, Authorization Server dùng authorization record gốc để giữ tenant đúng. Nếu membership đã bị thu hồi hoặc tenant suspended, policy có thể yêu cầu từ chối refresh hoặc hạ quyền; không tiếp tục phát token từ snapshot cũ vô thời hạn.

## 8. Ví dụ OAuth2TokenCustomizer cho JWT access token

Ví dụ sau minh họa một customizer duy nhất xử lý access token JWT. Các interface `ClientClaimPolicy` và `TenantClaimResolver` là service do ứng dụng định nghĩa; chúng phải đọc policy và tenant từ nguồn tin cậy.

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenClaimsConfiguration {

    static final String TENANT_CLAIM =
            "https://claims.example.vn/tenant_id";
    static final String GRANT_TYPE_CLAIM =
            "https://claims.example.vn/grant_type";
    static final String SUBJECT_TYPE_CLAIM =
            "https://claims.example.vn/subject_type";

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
            ClientClaimPolicy claimPolicy,
            TenantClaimResolver tenantClaimResolver) {

        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            String clientId =
                    context.getRegisteredClient().getClientId();
            AuthorizationGrantType grantType =
                    context.getAuthorizationGrantType();

            if (claimPolicy.includeGrantTypeClaim(clientId)) {
                context.getClaims().claim(
                        GRANT_TYPE_CLAIM, grantType.getValue());
            }

            if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(grantType)) {
                if (claimPolicy.includeSubjectTypeClaim(clientId)) {
                    context.getClaims().claim(SUBJECT_TYPE_CLAIM, "service");
                }
                return;
            }

            // Chỉ các grant user đã định nghĩa mới được gắn subject_type=user.
            if (AuthorizationGrantType.AUTHORIZATION_CODE.equals(grantType)
                    || AuthorizationGrantType.REFRESH_TOKEN.equals(grantType)) {
                if (claimPolicy.includeSubjectTypeClaim(clientId)) {
                    context.getClaims().claim(SUBJECT_TYPE_CLAIM, "user");
                }

                if (claimPolicy.includeTenantClaim(clientId)) {
                    Optional<String> tenantId =
                            tenantClaimResolver.resolveValidatedTenant(context);
                    tenantId.ifPresent(value ->
                            context.getClaims().claim(TENANT_CLAIM, value));
                }
            }
            // Token Exchange/custom grant cần policy và resolver riêng.
        };
    }
}
~~~

**Giới hạn và điều kiện của ví dụ:**

- Chỉ chạy cho `OAuth2TokenType.ACCESS_TOKEN`; không tự thêm claims này vào ID Token.
- `ClientClaimPolicy` và `TenantClaimResolver` là abstraction do ứng dụng viết, không phải bean có sẵn của Spring.
- `resolveValidatedTenant(context)` phải ưu tiên authorization attributes đã được xác minh hoặc directory service authoritative. Không được lấy tenant từ HTTP request chưa kiểm tra.
- Với refresh grant, resolver phải đọc tenant của authorization gốc và/hoặc xác minh lại membership; không suy luận tenant từ một request mới.
- Token Exchange và custom grant cần nhánh policy riêng. Không mặc định mọi grant không phải Client Credentials đều là user grant.
- Ví dụ thêm claim grant type để minh họa; chỉ phát hành nếu Resource Server thực sự cần. Grant type có thể lộ thông tin kiến trúc và không phải lúc nào cũng cần trong token.
- Không ghi đè các claim chuẩn như `iss`, `sub`, `aud`, `exp`, `iat`, `scope` hoặc `client_id` chỉ để làm chúng trông theo ý muốn.

### 8.1. Đọc tenant từ authorization đã lưu

Một `TenantClaimResolver` có thể theo mô hình sau (API/attribute key là phần ứng dụng tự định nghĩa):

~~~java
import java.util.Optional;

import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;

interface TenantClaimResolver {
    Optional<String> resolveValidatedTenant(JwtEncodingContext context);
}

final class AuthorizationAttributeTenantResolver
        implements TenantClaimResolver {

    static final String TENANT_ATTRIBUTE = "validated_tenant_id";

    private final TenantDirectory tenantDirectory;

    AuthorizationAttributeTenantResolver(TenantDirectory tenantDirectory) {
        this.tenantDirectory = tenantDirectory;
    }

    @Override
    public Optional<String> resolveValidatedTenant(
            JwtEncodingContext context) {

        OAuth2Authorization authorization = context.getAuthorization();
        if (authorization == null) {
            return Optional.empty();
        }

        Object rawTenant = authorization.getAttribute(TENANT_ATTRIBUTE);
        if (!(rawTenant instanceof String tenantId) || tenantId.isBlank()) {
            return Optional.empty();
        }

        String principalName = authorization.getPrincipalName();
        String clientId = context.getRegisteredClient().getClientId();

        // Re-check trạng thái/membership theo policy hiện tại.
        return tenantDirectory.isAuthorized(principalName, clientId, tenantId)
                ? Optional.of(tenantId)
                : Optional.empty();
    }
}
~~~

`TenantDirectory` là service ứng dụng cần triển khai; phương thức `isAuthorized` phải xác minh subject, client và tenant. Trong production, nếu thiếu tenant là lỗi đối với client/grant bắt buộc tenant, không nên im lặng phát token thiếu claim rồi để API hiểu sai. Hãy kiểm tra điều kiện bắt buộc tenant **trước khi token generation**; customizer không nên là nơi duy nhất quyết định authorization.

Đối với Client Credentials, tenant có thể gắn với client/service registration thay vì user authorization. Hãy dùng một resolver riêng cho service identity, giới hạn tenant mà client được phép đại diện.

## 9. Tùy chỉnh ID Token và phân biệt UserInfo

### 9.1. Chỉ tùy chỉnh ID Token khi đúng mục đích

Nếu cần thêm claim vào ID Token, hãy đặt nhánh xử lý này **trong cùng customizer JWT** ở mục 8, hoặc composition rõ ràng trong cấu hình generator. Ví dụ đoạn xử lý (ghép vào bean hiện có, không khai báo bean cùng generic thứ hai):

~~~java
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;

// Ghép vào OAuth2TokenCustomizer<JwtEncodingContext> hiện có:
if (OidcParameterNames.ID_TOKEN.equals(context.getTokenType().getValue())) {
    if (oidcClaimPolicy.includeDepartment(
            context.getRegisteredClient().getClientId())) {
        oidcUserClaimResolver.resolveDepartment(context)
                .ifPresent(department ->
                        context.getClaims().claim(
                                "https://claims.example.vn/department",
                                department));
    }
    return;
}
~~~

Đây là ví dụ minh họa cho API Spring Authorization Server 1.x. Nếu dự án đã có một bean `OAuth2TokenCustomizer<JwtEncodingContext>`, hãy **hợp nhất logic** hoặc composition có chủ đích theo cách cấu hình generator; không khai báo nhiều customizer cùng generic rồi giả định framework tự động gọi tất cả theo thứ tự mong muốn.

Không dùng customizer để tự đặt `auth_time` thành giờ hiện tại. Không gán `acr`/`amr` nếu chưa có bằng chứng xác thực tương ứng. Claim OIDC chuẩn phải tuân thủ OIDC Core và các chính sách bảo mật của OP.

### 9.2. UserInfo là một contract riêng

Nếu RP cần tên hiển thị, email hoặc department, có thể trả từ UserInfo sau khi xác minh access token và scope. Không cần nhét mọi thuộc tính đó vào ID Token hoặc access token. Dù dữ liệu xuất phát từ cùng user directory, endpoint UserInfo cần:

- Kiểm tra access token và subject.
- Chỉ trả claim được phép theo scope/consent và client policy.
- Bảo đảm `sub` trả về nhất quán với ID Token.
- Giữ tenant isolation.
- Không trả thuộc tính nhạy cảm chỉ vì user directory có dữ liệu.

## 10. Các nguyên tắc không được vi phạm khi tùy chỉnh claims

### 10.1. Không tin request input

| Nguồn dữ liệu | Có thể dùng trực tiếp? | Cách xử lý |
|---|---|---|
| `RegisteredClient` từ token context | Có, sau client authentication | Dùng client ID và server-side policy |
| `getAuthorizedScopes()` | Có, là scope context đã được authorize | Không tự mở rộng |
| Principal đã xác thực | Có, sau khi phân biệt user/client | Lấy subject ổn định; không giả định principal là `UserDetails` |
| Authorization attributes đã được xác minh | Có, nếu persistence/integrity được kiểm soát | Kiểm tra lại membership/policy khi cần |
| Query/header/body `tenant_id` | Không | Chỉ coi là lựa chọn, xác minh membership/client policy rồi lưu context |
| JWT subject token chưa xác minh | Không | Validate signature/issuer/type/expiry/status trước khi dùng claims |
| Client metadata tự khai | Không làm nguồn authorization | Chỉ dùng sau provisioning/approval và escaping |
| Email/username | Không nên làm khóa quyền dài hạn | Dùng subject ID ổn định, chỉ phát PII khi cần |

### 10.2. Không ghi đè claim chuẩn

Các lỗi dễ gây hậu quả:

- Ghi đè `sub` bằng email hoặc tenant ID làm thay đổi danh tính token.
- Ghi đè `aud` từ query parameter khiến token được gửi tới sai Resource Server.
- Tự tạo `scope` từ role chưa được authorization thay vì dùng scopes đã cấp.
- Đặt `exp` dài hơn policy để tránh refresh.
- Đặt `auth_time=iat` khi refresh, làm RP tưởng người dùng vừa xác thực.
- Đặt `acr`/`amr` tùy tiện, làm sai mức bảo đảm xác thực.
- Xóa `cnf` hoặc sender-constraining claim khiến token mất binding.
- Thay `iss` hoặc ký bằng key không tương ứng metadata/JWKS của issuer.

### 10.3. Claims không thay authorization

Nếu access token có `tenant_id=tenant-a` và `scope=orders.read`, Resource Server vẫn phải xác minh:

1. Chữ ký, issuer, thời hạn và audience.
2. Scope được cấp có cho phép endpoint/operation không.
3. Tenant trong token có khớp tenant của resource/request và identity context không.
4. Subject/actor có quyền trên đối tượng dữ liệu cụ thể không.
5. Token chưa bị thu hồi theo cơ chế của hệ thống nếu yêu cầu revocation tức thời.

Không cho client gửi `X-Tenant-Id: tenant-b` rồi API tin header thay claim/policy. Nếu header tenant được dùng để chọn context, phải so sánh với token và authorization của principal.

## 11. Cấu hình JWT access token và opaque token

### 11.1. JWT access token

Nếu muốn token có claims đọc được tại Resource Server, cần dùng access token format self-contained/JWT theo cấu hình. Ví dụ trong RegisteredClient:

~~~java
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .build();
~~~

Tùy phiên bản và default, `SELF_CONTAINED` biểu thị JWT access token; kiểm tra token thực tế và metadata/key. Authorization Server cần JWKSource/encoder phù hợp, public JWKS được công bố để Resource Server xác minh chữ ký. Không đưa private signing key vào Resource Server.

### 11.2. Opaque/reference access token

Nếu dùng `OAuth2TokenFormat.REFERENCE`, token không chứa payload JWT có thể decode ở client/API. Resource Server thường introspect token hoặc tra trạng thái theo cơ chế đã cấu hình. Claims cần được đưa vào introspection/authorization context thông qua generator/service phù hợp; `JwtEncodingContext` customizer không được gọi cho opaque token path.

Chọn JWT hay opaque theo yêu cầu:

| Tiêu chí | JWT/self-contained | Opaque/reference |
|---|---|---|
| Resource Server xác minh | Chữ ký và claims cục bộ | Introspection/lookup |
| Đọc claims | Có thể đọc sau khi xác minh chữ ký | Không decode payload từ token |
| Revocation tức thời | Cần cơ chế bổ sung hoặc TTL ngắn | Có thể kiểm tra trạng thái tập trung |
| Phụ thuộc AS lúc gọi API | Thấp hơn | Cao hơn nếu introspection mỗi request |
| Tùy chỉnh claims | JWT encoding customizer | Token claims context/generator và introspection |
| Rò dữ liệu | Payload có thể đọc được nếu token bị lộ | Token opaque không phơi payload nhưng vẫn là bearer credential |

## 12. Kiểm thử claims theo ma trận client, grant, principal và tenant

Đừng chỉ decode một JWT và thấy claim xuất hiện rồi kết luận đúng. Cần kiểm tra **cả trường hợp được phép lẫn trường hợp phải từ chối**, đồng thời xác minh Resource Server thực thi claims.

| Ca | Client | Grant | Principal/context | Kỳ vọng |
|---|---|---|---|---|
| 1 | `portal-web` | Authorization Code | User thuộc `tenant-a` | Token có tenant đã xác minh, subject là user |
| 2 | `portal-web` | Authorization Code | User thuộc `tenant-b` | Token có đúng `tenant-b`; không dùng tenant cache của A |
| 3 | `billing-job` | Client Credentials | Service account | Claim subject type là service; không có user profile giả |
| 4 | Client không được phép tenant | Client Credentials | Service gắn `tenant-a` | Không cấp claim/authorization sang `tenant-b` |
| 5 | `portal-web` | Refresh Token | Authorization gốc tenant A | Tenant được lấy từ authorization gốc và policy hiện tại |
| 6 | `portal-web` | Refresh Token | Membership tenant A đã bị thu hồi | Từ chối hoặc hạ quyền theo policy; không phát token cũ vô điều kiện |
| 7 | Client A | Authorization Code | Client B gửi request giả | Không lấy client identity từ request body |
| 8 | Client có policy không gồm claim | Authorization Code | User hợp lệ | Claim không được thêm |
| 9 | User chưa có tenant hợp lệ | Authorization Code | Tenant thiếu/sai | Không phát token có tenant giả |
| 10 | User nhiều tenant | Authorization Code | Chọn tenant không thuộc membership | Từ chối trước token generation |
| 11 | `billing-job` | Client Credentials | Principal là client authentication | Không ép principal thành `UserDetails` |
| 12 | Token Exchange | Token Exchange | Subject/actor đã xác minh | Claims phản ánh subject/actor và target policy |
| 13 | Token Exchange | Token Exchange | Actor không được ủy quyền | Từ chối; không thêm claim `act` giả |
| 14 | OIDC client | Authorization Code | Yêu cầu ID Token | Standard claims, nonce, aud và auth_time đúng; custom claims theo policy |
| 15 | Opaque token | Authorization Code | User hợp lệ | Không kỳ vọng JwtEncodingContext customizer chạy |
| 16 | JWT token | Refresh Token | Claims cũ đã thay đổi | Token mới theo policy hiện hành; token cũ vẫn là snapshot tới khi hết hạn |
| 17 | User bị disable | Refresh Token | Authorization cũ còn lưu | Re-check trạng thái user theo policy, không chỉ tin token cũ |
| 18 | Tenant A | Authorization Code | API request chọn tenant B | Resource Server từ chối mismatch |
| 19 | Scope rộng trong registration | Authorization Code | Request chỉ được authorize scope hẹp | Token chỉ chứa scope được cấp, không tự mở rộng |
| 20 | Principal không đúng kiểu | Grant tùy biến | Principal thiếu thuộc tính tenant | Không ClassCastException; fail closed/không thêm claim theo policy |

### 12.1. Unit test cho policy và claim resolver

Một unit test nên kiểm tra policy theo dữ liệu đã xác minh, không cần tạo JWT thật cho mọi ca:

~~~java
@Test
void doesNotResolveTenantFromUntrustedRequestValue() {
    JwtEncodingContext context = contextFor(
            "portal-web",
            AuthorizationGrantType.AUTHORIZATION_CODE,
            "user-123");

    // Authorization không có validated_tenant_id và directory
    // không xác nhận membership.
    Optional<String> tenant =
            tenantClaimResolver.resolveValidatedTenant(context);

    assertTrue(tenant.isEmpty());
}
~~~

`contextFor(...)` là test fixture do dự án viết để tạo `JwtEncodingContext` phù hợp phiên bản. Test cần thêm case có authorization attribute hợp lệ, membership đã thu hồi, client không được tenant và refresh authorization gốc. Không dùng test này để khẳng định token endpoint hoặc JWT signing đã hoạt động.

### 12.2. Integration test trên token endpoint

Với môi trường test, thực hiện luồng đầy đủ:

1. Đăng ký client và user test; xác định tenant membership trong fixture.
2. Gửi authorization request hợp lệ, hoàn tất login/consent và đổi code.
3. Giải mã **sau khi xác minh chữ ký** access token trong test; kiểm tra claim names, types, issuer, audience, scope, tenant và expiry.
4. Gọi Resource Server test bằng token đó; xác nhận đúng tenant được truy cập và tenant khác bị từ chối.
5. Refresh token; kiểm tra claims vẫn gắn đúng authorization gốc, không tự thay `auth_time`.
6. Thu hồi membership/tenant rồi thử refresh/exchange lại; xác nhận policy được thực thi.
7. Dùng Client Credentials; xác nhận token đại diện service, không mang dữ liệu user.
8. Kiểm tra ID Token/UserInfo riêng; không giả định access token customizer áp dụng cho mọi loại token.

### 12.3. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Claim không xuất hiện | Token opaque hoặc customizer không gắn đúng generator/token type | Xác định format và generator, kiểm tra bean |
| Claim xuất hiện trong ID Token nhưng không ở access token | Kiểm tra token type sai hoặc customizer chỉ xử lý ID Token | Phân nhánh riêng từng token type |
| Claim tenant lúc đúng lúc sai | Đọc tenant từ ThreadLocal/request hoặc cache không phân vùng | Dùng authorization context và tenant resolver có key client+subject |
| Client Credentials có user claim | Coi mọi principal là end user | Phân nhánh grant type, service identity riêng |
| Refresh token làm mới `auth_time` | Dùng thời gian hiện tại khi mint token | Lấy thời điểm active authentication gốc đã lưu; không tự cập nhật |
| Scope trong token rộng hơn | Tự ghi scope từ request/registration thay vì authorized scopes | Dùng scope đã authorize; kiểm tra policy trước issuance |
| Resource Server bỏ qua tenant | Chỉ decode claim mà không so với resource context | Thực thi tenant isolation trong authorization |
| Nhiều customizer không chạy như mong muốn | Nhiều bean cùng generic hoặc generator custom | Composition rõ ràng, test thứ tự và wiring |
| Claims thay đổi sau khi user đổi role nhưng token cũ còn hiệu lực | JWT là snapshot tại thời điểm phát | TTL ngắn, revocation/introspection hoặc policy version |
| Opaque token không có custom claim trong introspection | Chỉ cấu hình JwtEncodingContext | Cấu hình token claims context và introspection response |

## 13. Vận hành, quyền riêng tư và vòng đời claims

### 13.1. JWT là snapshot

Claims trong JWT được ký tại thời điểm phát hành. Nếu người dùng bị gỡ khỏi tenant hoặc role thay đổi sau đó, token cũ vẫn có thể chứa claims trước đó đến khi hết hạn, bị thu hồi theo cơ chế bổ sung hoặc Resource Server kiểm tra trạng thái khác. Vì vậy:

- Giữ access token TTL phù hợp mức rủi ro.
- Với quyền thay đổi thường xuyên, dùng policy version hoặc kiểm tra membership live tại API khi cần.
- Xác định rõ thời gian propagation của revocation.
- Không xem custom claim là nguồn dữ liệu realtime.
- Khi tenant/user bị disable, có quy trình xử lý token đã phát.

### 13.2. Giảm thiểu dữ liệu cá nhân

Một claim có thể được đọc bởi mọi bên giữ được bearer token hoặc có quyền giải mã/xác minh token. Chỉ phát dữ liệu cần thiết cho mục tiêu API. Tránh:

- Email, số điện thoại, địa chỉ, ngày sinh nếu API không cần.
- Danh sách toàn bộ group/role lớn.
- Dữ liệu nội bộ như fraud score, ghi chú hỗ trợ, thông tin thanh toán.
- Bí mật vận hành hoặc metadata có thể tiết lộ kiến trúc.
- Dữ liệu tenant khác hoặc thuộc tính không có consent/purpose phù hợp.

Dùng subject ID ổn định, hạn chế PII và có chính sách retention/audit cho claims. Nếu dùng pairwise subject cho OIDC, giữ đúng tính nhất quán theo client/sector và không thay tùy tiện.

### 13.3. Version hóa schema claims

Khi thay đổi kiểu dữ liệu hoặc ý nghĩa, cân nhắc claim schema version:

~~~json
{
  "https://claims.example.vn/claims_version": 2,
  "https://claims.example.vn/tenant_id": "tenant-a",
  "https://claims.example.vn/subject_type": "user"
}
~~~

Resource Server cần hỗ trợ tương thích trong khoảng thời gian token cũ còn sống. Không đổi `tenant_id` từ string sang object mà không version hóa/rollout; API có thể lỗi hoặc bỏ qua authorization.

### 13.4. Audit mà không log token

Có thể ghi audit theo event ID, client ID, grant type, subject reference được bảo vệ, tenant và policy version. Không ghi toàn bộ JWT/access token/refresh token, secret, private key hoặc Authorization header. Metrics không nên dùng raw user ID/email/tenant ID làm label có cardinality cao; chọn nhãn phân loại an toàn.

## 14. Checklist và câu hỏi tự kiểm tra

- [ ] Phân biệt access token, ID Token, UserInfo, refresh token và opaque token.
- [ ] Dùng `OAuth2TokenCustomizer<JwtEncodingContext>` cho JWT encoding path; không kỳ vọng áp dụng cho mọi token format.
- [ ] Claims được chọn dựa trên `RegisteredClient`, grant type, principal và authorization context đã xác minh.
- [ ] Client policy do server quản lý; client không tự bật/tắt claim bằng request parameter.
- [ ] Client Credentials được xử lý như service identity, không giả mạo user.
- [ ] Tenant được xác minh theo principal, client, membership và policy; lưu với authorization transaction để refresh dùng đúng context.
- [ ] Không lấy tenant/role/audience/scope từ query, header hoặc token chưa xác minh.
- [ ] Không ghi đè claims chuẩn như `iss`, `sub`, `aud`, `exp`, `iat`, `scope`, `nonce`, `auth_time` và `cnf`.
- [ ] Không gán `auth_time` mới khi refresh; `acr`/`amr` phản ánh bằng chứng thật.
- [ ] Claims tối thiểu, đúng kiểu, có namespace và schema version khi cần.
- [ ] Resource Server kiểm tra issuer, audience, scope, tenant và quyền trên tài nguyên.
- [ ] Có test cho mỗi client/grant/principal/tenant và negative cases.
- [ ] Đã đánh giá snapshot JWT, TTL, revocation, policy version và thay đổi membership.
- [ ] Không log raw token/PII; audit có retention và quyền truy cập.

**Câu hỏi tự kiểm tra**

1. `OAuth2TokenCustomizer<JwtEncodingContext>` chạy ở giai đoạn nào của token generation?
2. Vì sao một client đã xác thực không được tự quyết định `tenant_id` trong token?
3. Principal trong Client Credentials khác principal trong Authorization Code như thế nào?
4. Khi refresh token, vì sao không được đặt `auth_time=Instant.now()`?
5. Vì sao access token claims, ID Token claims và UserInfo cần chính sách riêng?
6. Customizer JWT có áp dụng cho opaque access token không? Nếu không, cần kiểm tra extension point nào?
7. Nếu JWT mang `tenant_id=tenant-a` nhưng request API chọn tenant-b, Resource Server phải xử lý thế nào?
8. Vì sao thêm `role=admin` vào token không tự chứng minh người dùng được quyền admin?
9. JWT đã phát có phản ánh ngay thay đổi membership/role trong database không?
10. Làm thế nào để kiểm tra customizer không phát claim nhạy cảm cho client không được phép?

## Tài liệu tham khảo

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, token generation và authorization state.
- [Spring Authorization Server — How-to: Customize the JWT](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): sử dụng `OAuth2TokenCustomizer<JwtEncodingContext>` để thêm claims/authorities.
- [Spring Authorization Server — Token Generation](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html#oauth2-token-generator): `OAuth2TokenGenerator`, `JwtGenerator` và token customizer.
- [Spring Authorization Server — OIDC UserInfo Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html#oauth2-oidc-user-info-endpoint): tùy chỉnh claims UserInfo.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered, public và private claim names.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claims liên quan.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo và các claims OIDC.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject, actor và delegation context.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và bảo vệ API.
