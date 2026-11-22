# Đăng nhập OIDC trong một kiến trúc liên kết danh tính

**OpenID Connect (OIDC)** là lớp xác thực danh tính xây trên **OAuth 2.0**. Trong kiến trúc liên kết (*federation*), ứng dụng không trực tiếp yêu cầu mật khẩu của người dùng mà chuyển họ đến một **OpenID Provider (OP)** đáng tin; OP xác thực người dùng, nhận quyết định chia sẻ thông tin và phát hành **ID Token** để ứng dụng **Relying Party (RP)** biết chủ thể đã được xác thực. Khi có **identity broker**, broker có thể đóng vai **RP đối với IdP upstream** và **OP đối với ứng dụng downstream**, nối nhiều nguồn danh tính (OIDC, SAML 2.0, LDAP/AD qua adapter) thành một giao diện đăng nhập thống nhất.

Đề bài cần được hiểu ở **hai tầng**: (1) cách một ứng dụng Java/Spring Security thực hiện **OIDC login** đúng giao thức; (2) cách tổ chức đặt ứng dụng đó trong hệ thống **federation và identity brokering** sao cho trust boundary, định danh, phiên và quyền không bị lẫn lộn.

**Thông điệp chính:** OIDC xác minh *danh tính được OP công bố*; ứng dụng vẫn phải quyết định **có cho vào ứng dụng không** và **được làm gì**. **ID Token** không phải access token cho mọi API; **token do broker phát hành** không phải là một bản sao của token hay SAML assertion từ IdP upstream.

## 1. Khi nào dùng OIDC trong kiến trúc liên kết?

Ví dụ một tổ chức có:

- Ứng dụng `portal.example.org` viết bằng **Spring Boot/Spring Security**.
- Nhà cung cấp danh tính nhân viên dùng SAML 2.0; nhà cung cấp khách hàng hỗ trợ OIDC; doanh nghiệp đối tác có IdP riêng.
- Một broker `https://login.example.org/realms/enterprise` đứng giữa, lựa chọn IdP theo tenant/home realm, kiểm tra kết quả upstream, tạo local/broker identity, áp dụng chính sách và phát hành **OIDC ID Token cho portal**.
- API nội bộ dùng access token có audience riêng, không sử dụng ID Token làm bearer token.

Một kiến trúc khái niệm:

~~~text
                 +----------------------+
                 |       Browser        |
                 +----------+-----------+
                            |
                       mở /reports
                            v
                 +----------------------+
                 |   Portal (Spring)    |
                 |   OIDC RP / Client   |
                 +----------+-----------+
                            |
                  OIDC Authorization Code
                            |
                            v
                 +----------------------+
                 |    Identity Broker   |
                 |  OP đối với Portal   |
                 |  RP/SP đối với IdP   |
                 +---+----------+-------+
                     |          |
         upstream SAML|          |upstream OIDC
                     v          v
              +-----------+ +-----------+
              | IdP nhân  | | IdP đối   |
              | viên      | | tác       |
              +-----------+ +-----------+

Portal chỉ xác minh token của Broker theo issuer / JWKS broker.
Broker tự xác minh các thông điệp và điều kiện IdP upstream.
~~~

**Không phải mọi triển khai OIDC đều cần broker**: nếu ứng dụng chỉ tích hợp một OP, có thể đăng ký OIDC client trực tiếp với OP đó. Broker đáng giá khi nhiều IdP, chính sách tập trung, discovery theo tổ chức, MFA/policy tập trung, đồng bộ account hoặc muốn ứng dụng downstream chỉ phải tích hợp một issuer.

### 1.1. Những vai trò cần phân biệt

| Thuật ngữ | Vai trò theo giao thức | Trong ví dụ |
| --- | --- | --- |
| **End-User** | Con người được xác thực. | Người dùng portal. |
| **Relying Party (RP)** | Ứng dụng OIDC nhận và xác minh ID Token. | Spring Boot portal. |
| **OAuth 2.0 Client** | Client yêu cầu authorization code/token. | Cũng là portal ở chặng downstream. |
| **OpenID Provider (OP)** | Máy chủ xác thực, phát hành ID Token. | Identity broker đối với portal. |
| **Authorization Server (AS)** | Phát hành authorization code và token theo OAuth. | Broker ở chặng downstream. |
| **Resource Server** | API xác minh access token cho tài nguyên. | Reporting API tách biệt. |
| **Identity Broker** | Trung gian xác thực với IdP upstream, phát hành danh tính downstream. | Broker enterprise. |
| **Upstream IdP** | Hệ thống gốc xác thực người dùng với broker. | SAML IdP hoặc một OP khác. |
| **OIDC Client Registration** | Cấu hình `client_id`, redirect URI, scope, provider/issuer, credentials. | `portal-web` tại broker. |

Một thành phần có thể đóng **hai vai** ở hai trust relationship khác nhau. Broker là **client/RP hoặc SAML SP** khi nói chuyện upstream, nhưng là **OP/AS** khi nói chuyện với portal. Đừng lấy quy tắc xác minh token của portal để thay quy tắc xử lý SAML assertion ở broker.

## 2. OIDC bổ sung gì so với OAuth 2.0?

OAuth 2.0 chủ yếu là **ủy quyền truy cập tài nguyên**: client nhận access token với scopes/audience/chính sách. OIDC bổ sung **xác thực người dùng**, chuẩn hóa **ID Token**, các claims và discovery/userinfo/logout liên quan.

| Thông điệp/token | Dùng để làm gì? | Bên nhận tin cậy | Lưu ý |
| --- | --- | --- | --- |
| **Authorization Code** | Giá trị dùng một lần để client đổi token ở token endpoint. | Client + Authorization Server qua giao dịch đúng. | Thời hạn ngắn, ràng buộc redirect URI/client và PKCE. |
| **ID Token** (OIDC) | Khẳng định một subject đã được OP xác thực cho **RP/client** này. | RP có `client_id` nằm trong `aud`. | Phải xác minh issuer, audience, signature, time, nonce khi dùng. |
| **Access Token** (OAuth 2.0) | Cho phép gọi resource server tương ứng. | Resource server/API theo audience/scope. | Không mặc nhiên chứng minh login cho RP. |
| **Refresh Token** (nếu được cấp) | Dùng để xin access token mới theo chính sách. | Client và token endpoint của AS. | Cần bảo mật nghiêm ngặt/rotation, không đưa ra browser tùy tiện. |
| **`state`** | Correlate OAuth authorization response với request, chống CSRF ở redirect. | Client kiểm tra với state đã lưu. | Không phải JWT, không dùng làm email/role. |
| **`nonce`** | Ràng buộc ID Token với authentication request, giảm replay/substitution. | RP kiểm tra `nonce` trong token khi đã gửi. | Khác `state`; không thay PKCE. |
| **PKCE `code_verifier`** | Bí mật một lần cho token exchange; AS kiểm tra khớp `code_challenge`. | Client lưu đến lúc đổi code; AS xác minh. | Ngăn code interception/injection trong phạm vi protocol. |

**ID Token không phải vật thay thế cho API authorization.** Một resource server không nên chấp nhận ID Token của portal làm access token chỉ vì nó cũng là JWT có chữ ký. `aud` của ID Token là **OIDC client**, còn access token dành cho **API audience** và chịu chính sách khác. OAuth access token có thể là JWT hoặc opaque string: ứng dụng không thể mặc định decode mọi access token bằng cách cắt dấu chấm.

## 3. Authorization Code Flow với PKCE: đường đi chuẩn cho web login

Hiện đại hóa: ưu tiên **Authorization Code Flow** kết hợp **PKCE (S256)**, giao tiếp HTTPS và redirect URI đăng ký chính xác. Tránh thiết kế mới dựa vào **Implicit Flow** đưa token trực tiếp qua browser URL fragment. Với server-side Spring Boot, client có thể là confidential client dùng client secret/private key authentication; **PKCE vẫn là lớp bảo vệ bổ sung**, không đồng nghĩa bỏ xác thực client nếu OP yêu cầu.

~~~text
Browser                    RP / Spring Boot               OP / Broker
  |                               |                              |
  | GET /private                  |                              |
  |------------------------------>|                              |
  |                               | tạo state, nonce, verifier   |
  |                               | tính PKCE challenge S256     |
  |<------------------------------|                              |
  | 302 /authorize?...state=...&code_challenge=...                |
  |------------------------------------------------------------->|
  |                               |                         xác thực
  |                               |                        IdP upstream
  |<-------------------------------------------------------------|
  | 302 https://portal.example.org/login/oauth2/code/broker
  |                  ?code=...&state=...
  |------------------------------>|                              |
  |                               | so state, tìm request gốc    |
  |                               |                              |
  |                               | POST /token (code + verifier)|
  |                               |----------------------------->|
  |                               |<-----------------------------|
  |                               | id_token, access_token      |
  |                               |                              |
  |                               | Verify ID Token              |
  |                               | iss/aud/signature/time/nonce |
  |                               | bind issuer+sub => account   |
  |                               | SecurityContext / session    |
  |<------------------------------|                              |
  | 302 /private                 |                               |
~~~

Luồng chi tiết:

1. Người dùng yêu cầu tài nguyên được bảo vệ ở RP.
2. Spring Security kích hoạt `/oauth2/authorization/broker` (theo registrationId), tạo `OAuth2AuthorizationRequest`, `state` khó đoán; khi dùng PKCE tạo `code_verifier` và `code_challenge=S256(verifier)`; tạo `nonce` nếu sử dụng.
3. RP chuyển browser đến **authorization endpoint của OP**, kèm `response_type=code`, `client_id`, `redirect_uri`, `scope` chứa `openid`, state, PKCE challenge và các tham số OIDC phù hợp.
4. Broker chọn IdP upstream, xác thực/nhận kết quả và quyết định phát hành code cho RP. **Portal không trực tiếp thấy SAMLResponse/upstream credential** nếu broker làm đúng vai trò.
5. Browser quay về **redirect URI của RP** với `code` và `state`; code không phải danh tính và không được tự dùng làm session.
6. Spring kiểm tra giao dịch qua authorization request repository, `state` và registration; backend RP gửi code cùng `code_verifier` đến token endpoint.
7. OP xác thực client/challenge, code, redirect URI và phát hành ID Token, access token (cùng refresh token nếu chính sách cấp).
8. RP xác minh ID Token, lấy `iss`+`sub`, tra account và chính sách nội bộ, dựng `Authentication`/authorities, lưu `SecurityContext`/session.
9. Những request tiếp theo có thể dùng cookie session RP; access token được lưu server-side nếu RP cần gọi API thay người dùng.

**OIDC login không đơn thuần là redirect sang trang OP rồi nhận JSON có email.** Token exchange và xác minh ở phía server/khách hàng an toàn mới làm cho danh tính có căn cứ.

### 3.1. HTTP ví dụ ở các chặng

Yêu cầu đăng nhập tại portal:

~~~http
GET /oauth2/authorization/broker HTTP/1.1
Host: portal.example.org
~~~

Một authorization request minh họa (line wrap chỉ để đọc):

~~~text
GET https://login.example.org/realms/enterprise/protocol/openid-connect/auth
  ?response_type=code
  &client_id=portal-web
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
  &scope=openid%20profile%20email
  &state=<cryptographically-random-state>
  &nonce=<cryptographically-random-nonce>
  &code_challenge=<base64url-sha256-verifier>
  &code_challenge_method=S256
~~~

Các chuỗi trong ngoặc nhọn là **ký hiệu minh họa**, không phải dữ liệu có thể sử dụng thật. Authorization endpoint cụ thể phải đến từ metadata OP; đường dẫn trên chỉ giả định một OP có cấu trúc đường dẫn tương tự.

Callback browser:

~~~http
GET /login/oauth2/code/broker?code=<one-time-code>&state=<returned-state> HTTP/1.1
Host: portal.example.org
Cookie: JSESSIONID=<browser-session-cookie>
~~~

RP đối chiếu state/binding **trước khi** dùng authorization code. Token request là **server-to-server**; không đưa client secret vào trang HTML hay JavaScript của browser. Nếu có lỗi `error=access_denied`/login_failed, ứng dụng phải xử lý failure path, không cố giả định có ID Token.

### 3.2. Cái nào do browser truyền, cái nào do backend lưu?

Browser có thể nhìn thấy **authorization request**, code và state trong navigation; vì thế cần TLS, redirect URI chính xác, chống referrer/token leak, một lần sử dụng code, PKCE và session binding. Backend giữ **authorization request gốc**, nonce, code verifier và client credentials/tokens nhạy cảm theo chính sách server-side; không để `code_verifier`/client secret lẫn vào query URL hay log công khai.

Nếu hai tab cùng login, mỗi authorization transaction cần **state/nonce/verifier độc lập**, tương quan đúng với browser session. Không lưu một “last login state” chung khiến callback tab A dùng verifier tab B. Việc session fixation protection xoay cookie sau login cũng cần được kiểm thử.

## 4. Discovery: RP biết tin endpoint và khóa của OP như thế nào?

OpenID Connect Discovery dùng **issuer URL** để lấy metadata. Ví dụ issuer giả định:

~~~text
https://login.example.org/realms/enterprise
~~~

Một discovery document có cấu trúc tương tự:

~~~json
{
  "issuer": "https://login.example.org/realms/enterprise",
  "authorization_endpoint": "https://login.example.org/realms/enterprise/authorize",
  "token_endpoint": "https://login.example.org/realms/enterprise/token",
  "jwks_uri": "https://login.example.org/realms/enterprise/jwks",
  "userinfo_endpoint": "https://login.example.org/realms/enterprise/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Đây là **JSON minh họa metadata**, không phải endpoint OP đang hoạt động. Tùy sản phẩm, well-known discovery path có quy tắc khác khi issuer chứa path; nên để thư viện Discovery của Spring Security xử lý đúng chuẩn, không tự nối chuỗi tùy tiện rồi đoán endpoint.

RP phải kiểm tra **metadata.issuer khớp chính xác issuer đã cấu hình và `iss` trong ID Token**. `jwks_uri` cung cấp khóa xác minh công khai; khi OP rotate signing key, RP cần cache/refresh JWKS phù hợp nhưng **không tự tải khóa từ URL tùy ý do token/header của attacker cung cấp**. Không đặt `issuer-uri` từ một query parameter do browser tự gửi: có thể gây SSRF/IdP mix-up.

Discovery giúp cấu hình endpoint, nhưng **không tự xác thực một token bất kỳ** nếu issuer, audience, signature hay transaction state không qua kiểm tra.

## 5. ID Token: nội dung và cách xác minh

ID Token thường là **JWT có chữ ký** do OP phát cho RP. Một payload *minh họa*:

~~~json
{
  "iss": "https://login.example.org/realms/enterprise",
  "sub": "pairwise-6f13a8",
  "aud": "portal-web",
  "exp": 1794024000,
  "iat": 1794023700,
  "auth_time": 1794023600,
  "nonce": "random-value-bound-to-this-login",
  "acr": "urn:example:assurance:level2",
  "amr": ["pwd", "mfa"],
  "email": "member@example.org",
  "email_verified": true
}
~~~

Dữ liệu JSON này **không phải token có chữ ký**, các timestamp chỉ là số ví dụ; không thể dán vào API để đăng nhập. RP **không được** tin claims từ một payload JWT tự giải mã mà chưa qua bộ xác minh toàn bộ.

### 5.1. Những claim quan trọng

| Claim | Ý nghĩa | Kiểm tra/áp dụng |
| --- | --- | --- |
| **`iss`** | OP phát hành token. | **Khớp chính xác** issuer đã cấu hình/discovery. |
| **`sub`** | Định danh subject trong phạm vi issuer. | Kết hợp **`iss` + `sub`** làm khóa identity binding; không dùng email làm khóa duy nhất. |
| **`aud`** | Audience của ID Token. | Phải chứa **`client_id` của RP**; xử lý nhiều audience và `azp` theo chuẩn. |
| **`exp`** | Hết hạn token. | Không dùng token khi hết hạn; cho phép clock skew nhỏ có kiểm soát. |
| **`iat`** | Thời điểm phát hành. | Kiểm tra hợp lý, giới hạn độ cũ theo chính sách ứng dụng. |
| **`nonce`** | Liên hệ ID Token với authentication request. | Nếu gửi nonce thì phải nhận và so **đúng nonce đã lưu**; dùng state/nonce riêng mỗi giao dịch. |
| **`auth_time`** | Thời điểm xác thực người dùng tại OP. | Quan trọng cho `max_age`/reauth/step-up. |
| **`acr`** | Mức/ngữ cảnh xác thực. | Chỉ dùng khi OP và RP có hợp đồng về assurance; không tự suy từ string. |
| **`amr`** | Phương thức xác thực đã dùng. | Chỉ một phần dữ liệu assurance, không tự đồng nghĩa “MFA đủ cho mọi giao dịch”. |
| **`email`, `email_verified`** | Thông tin liên lạc. | Không thay `iss+sub`, và “verified” phụ thuộc chính sách tin OP. |
| **`azp`** | Authorized party trong các trường hợp liên quan. | Đối chiếu client theo quy tắc OIDC khi xuất hiện/được yêu cầu. |
| **`sid`** (khi có) | Định danh phiên OP cho một số giao thức logout. | Khác `sub`, cookie RP và access token; không phải luôn có. |

**Xác minh kỹ thuật phải bao gồm** signature/thuật toán được phép/JWKS của **đúng OP**, issuer, audience, time, nonce và các điều kiện/claims khác do ứng dụng yêu cầu. Tránh JWT algorithm confusion, `alg=none` không phù hợp, `kid` dùng như đường dẫn filesystem/URL và bỏ kiểm tra `azp` khi có nhiều audience.

Trong Authorization Code Flow, **OIDC Core cho nonce là tùy chọn ở một số trường hợp** nhưng **nếu đã gửi nonce thì phải xác minh**. Không nói nonce luôn bắt buộc ở mọi response type; cũng không vì nonce tùy chọn mà loại bỏ CSRF state và PKCE. Một số server/framework chọn gửi nonce thường xuyên để tăng ràng buộc.

### 5.2. UserInfo không thay ID Token

`userinfo_endpoint` là resource endpoint của OP. RP có thể gọi nó bằng **access token** để lấy profile đã được người dùng/OP đồng ý chia sẻ. Khi sử dụng UserInfo, **`sub` trong UserInfo phải khớp `sub` của ID Token**, nếu không phải từ chối kết quả UserInfo để tránh token substitution. Không dùng UserInfo email/name làm chứng cứ nhận diện khác ID Token.

Các claim profile có thể thay đổi theo thời gian; nếu `email` đổi thì local account binding theo `iss+sub` vẫn không bị nhầm. Một ứng dụng không cần UserInfo thì có thể dựa vào ID Token cho thông tin xác thực và claims cần thiết; tránh gọi endpoint ngoài không cần thiết trong đường đăng nhập.

### 5.3. Subject identifier: public và pairwise

OIDC có thể cấp **public subject** (cùng `sub` cho nhiều client theo issuer) hoặc **pairwise subject** (khác `sub` giữa các client/sector identifiers, để giảm correlation không mong muốn). Nếu portal và một ứng dụng khác nhận hai `sub` khác nhau từ cùng OP, đó có thể là thiết kế pairwise **đúng chuẩn**, không phải lỗi đăng nhập.

Vì vậy đừng giả định `sub` là mã nhân sự toàn doanh nghiệp hoặc có thể dùng để join trực tiếp nhiều ứng dụng. Nếu cần liên kết các tài khoản, dùng quy trình account linking được kiểm soát tại broker/IAM với consent/policy phù hợp, không tự merge theo email.

## 6. Ranh giới trust của identity broker

Một broker nối upstream và downstream bằng **hai giao dịch độc lập**, không phải chỉ một HTTP proxy chuyển tiếp token.

~~~text
           Trust relationship U                  Trust relationship D
  Upstream IdP <---- OIDC/SAML ----> Broker <---- OIDC ----> Portal
  - issuer U                        - RP/SP     - issuer B     - client portal
  - keys/certs U                    - policy    - keys B      - JWKS broker
  - subject U                       - mapping   - subject B   - aud portal
  - authn context U                            - own ID Token
~~~

**Ở phía upstream:**

- Nếu upstream là **SAML 2.0**: broker đóng vai SAML SP, nhận assertion ở ACS, kiểm tra chữ ký IdP, issuer, audience (dành **broker SP**), conditions, subject confirmation, `InResponseTo` và replay.
- Nếu upstream là **OIDC**: broker đóng vai OIDC RP, chạy Authorization Code, kiểm tra ID Token `iss/aud/exp/nonce` và các quy tắc OIDC khác.
- Nếu upstream có LDAP/AD hoặc custom auth: broker chịu trách nhiệm xác thực qua adapter theo chính sách; không vì adapter nói “thành công” mà portal phải tự tin tất cả claims.

**Ở phía downstream:**

- Broker tạo **OIDC authorization code/token của chính mình**, sử dụng **issuer của broker**.
- ID Token downstream có `aud=client_id` của portal và `sub` mà broker cấp cho portal, có thể là pairwise; không nhất thiết giống NameID SAML hay subject upstream.
- Portal xác minh **chữ ký/JWKS broker** và issuer broker; portal **không cần và thường không có** private key/metadata của mọi IdP upstream.

### 6.1. Vì sao không forward upstream ID Token nguyên vẹn?

Giả sử OP upstream phát ID Token:

~~~text
iss = https://idp.partner.example
aud = broker-upstream-client
sub = upstream-user-77
~~~

Portal downstream đã đăng ký với broker lại kỳ vọng:

~~~text
iss = https://login.example.org/realms/enterprise
aud = portal-web
sub = broker-subject-981
~~~

Nếu broker đưa nguyên token upstream cho portal, **issuer/audience của token không đúng trust relationship downstream**. Một portal chấp nhận nó sau khi bỏ `iss`/`aud` validation là thiết kế nguy hiểm, dễ thành **token substitution / confused deputy**. Broker phải phát hành token của chính mình theo giao dịch downstream hoặc dùng cơ chế **token exchange được đặc tả và triển khai chính thức**, không tự thay claim rồi giữ chữ ký cũ.

**Không được “biến SAML assertion thành JWT” bằng cách Base64 decode và copy NameID vào `sub`**. Đó là bỏ qua chữ ký SAML và ngữ nghĩa điều kiện. Broker phải xác minh SAML trước, map vào identity nội bộ của broker rồi phát hành token OIDC mới phù hợp với chính sách downstream.

### 6.2. Identity mapping ở broker và ứng dụng

Một mapping có thể là:

~~~text
upstream_identity_binding
  upstream_type    = SAML
  upstream_issuer  = urn:example:idp:employees
  upstream_subject = immutable-nameid-789
  broker_user_id   = broker-user-24

downstream_identity_binding
  broker_issuer    = https://login.example.org/realms/enterprise
  broker_subject   = pairwise-6f13a8
  client_id        = portal-web
  app_user_id      = user-42
  tenant           = tenant-acme
~~~

Các bản ghi liên kết phải được tạo và duy trì qua quy trình an toàn. `email`/display name không đủ để tự hợp nhất danh tính upstream/downstream, đặc biệt khi IdP có khả năng tái sử dụng email hoặc một tổ chức có nhiều tenant trùng tên.

**Không nhầm nội bộ broker user ID với `sub` public downstream**: broker có thể chọn subject pairwise. Portal chỉ có thể dựa vào `iss+sub` được phát và xác minh cùng chính sách liên kết, không suy ra nguồn upstream từ subject string.

### 6.3. Broker có thể nâng, giữ hay hạ assurance?

`acr`, `amr`, thời điểm `auth_time` và các yêu cầu `max_age`/step-up phải được diễn giải dựa trên **hợp đồng tin cậy**. Nếu upstream SAML xác thực bằng mật khẩu nhưng downstream yêu cầu MFA, broker **không được tự gắn `amr=["mfa"]` chỉ vì người dùng có tài khoản doanh nghiệp**. Broker có thể bắt step-up xác thực ở upstream hoặc tự thực hiện thêm bước nếu đúng policy, sau đó phát hành claims phản ánh sự thật.

Ngược lại, RP không nên coi `acr` string chưa được thỏa thuận là đủ quyền phê duyệt khoản thanh toán. **Authentication assurance không đồng nghĩa application authorization**.

## 7. Chọn IdP upstream trong môi trường nhiều tổ chức

Một hệ thống federation thường phải làm **home realm discovery (HRD)**: người dùng chọn tổ chức, nhập domain gợi ý hoặc truy cập tenant-specific login URL, rồi broker quyết định IdP.

Ví dụ:

~~~text
portal.example.org/tenant/acme
    -> OIDC login tới broker (client=portal-web)
    -> broker xác định tenant=acme theo config/transaction
    -> broker chuyển tới SAML IdP-A

portal.example.org/tenant/partner
    -> OIDC login tới cùng broker
    -> broker chọn upstream OIDC IdP-B
~~~

**Nguồn tin cậy cho routing** phải là cấu hình tenant/idp allowlist và transaction state đã bảo vệ; không dùng một issuer URL tùy ý do browser cung cấp để tự gọi discovery. `login_hint`, `domain_hint`, email suffix hoặc query param chỉ nên là **gợi ý**, không là bằng chứng tenant/issuer/role.

Khi callback về, broker phải ràng buộc response upstream với **đúng IdP đã chọn cho giao dịch**, sau đó phát hành token downstream gắn đúng tenant/subject. Ở RP, `state`, nonce, registrationId và policy tenant cũng phải khớp request đã khởi tạo. Điều này giảm nguy cơ **IdP mix-up**, account confusion và cross-tenant data access.

### 7.1. Nhiều registration OIDC ở portal thì sao?

Spring Security hỗ trợ nhiều `ClientRegistration`, mỗi cái có `registrationId`, `client-id`, issuer/OP riêng. Ví dụ `broker-employees` và `broker-partners`. Đừng dùng `registrationId` như là bằng chứng rằng token nhận về đúng IdP: **`iss` và chữ ký của token** vẫn phải khớp registration. Nếu broker là issuer duy nhất và tự route upstream, portal có thể chỉ cần một registration; đây thường là lợi ích của môi giới danh tính.

## 8. Java/Spring Boot: đăng ký một OIDC client

Ví dụ dự án **Spring Boot Servlet, Java 17+**, với Maven hoặc Gradle management phù hợp, dùng các dependency:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Đây là **đoạn `dependencies` trong dự án Gradle đã cấu hình plugin/repository/version management**, không phải file build.gradle hoàn chỉnh. Spring Security sẽ dùng **OAuth2 Client** và **OIDC login**; không cần `spring-security-saml2-service-provider` nếu **portal chỉ biết OIDC broker**. SAML service provider library cần ở phía **broker** nếu broker tự nhận SAML upstream và chức năng đó được triển khai bằng Spring Security.

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: https://login.example.org/realms/enterprise
~~~

Đây là **mẫu cấu hình** với OP và `client-id` giả định. Ứng dụng chạy thật cần OP issuer/discovery hoạt động, client được đăng ký, **client secret lấy từ secret manager/environment** và redirect URI chính xác tại OP. Không commit secret vào repository. Nếu OP hỗ trợ/đòi PKCE cho confidential clients, cấu hình yêu cầu PKCE bằng API `ClientRegistration.ClientSettings.requireProofKey` đúng phiên bản và kiểm tra authorization request có `code_challenge_method=S256`; **đừng mặc định mọi confidential client được Spring bật PKCE mà không kiểm chứng**. Public client không có client secret có thiết lập khác và không phù hợp với giả định bảo mật confidential server-side.

Trong cấu hình này, trường `scope` chứa **`openid`** là điểm phân biệt OIDC với OAuth login thuần. Khi có scope `openid`, Spring Security sử dụng các thành phần OIDC như `OidcUserService`; nếu bỏ `openid`, không thể coi response là OIDC login chỉ vì provider có chữ “identity”.

### 8.1. SecurityFilterChain

Tệp `src/main/java/example/portal/SecurityConfig.java`:

~~~java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasAuthority("app:admin")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Khi đúng dependency/registration được cung cấp, Spring Security sử dụng endpoints thường gặp:

| Endpoint tại RP | Mục đích |
| --- | --- |
| **`GET /oauth2/authorization/broker`** | Bắt đầu login, chuẩn bị authorization request/state và redirect tới OP. |
| **`GET /login/oauth2/code/broker`** | Nhận callback code/state và thực hiện token exchange/xác minh. |
| `GET /login` | Trang đăng nhập mặc định hoặc trang tùy biến dẫn tới OP theo cấu hình. |
| `POST /logout` | Local logout khi được bật với CSRF/session policy phù hợp; **không tự đảm bảo OP/upstream logout**. |

Tên endpoint mặc định có thể được tùy biến bằng DSL. **`/login/oauth2/code/broker` không phải ACS SAML `/login/saml2/sso/{registrationId}`**; hai protocol có thông điệp, filter và cách validate khác nhau.

Mã SecurityConfig **chưa triển khai local admission gate hoặc role mapping**. Nó minh họa kích hoạt OIDC login và một số authorization rules; nếu ứng dụng cần khóa account hoặc entitlement riêng, phải bổ sung logic ở điểm mở rộng thích hợp.

### 8.2. Đọc principal OIDC đã được xác minh

Tệp `src/main/java/example/portal/WhoAmIController.java`:

~~~java
package example.portal;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser principal) {

        String issuer = principal.getIdToken().getClaimAsString("iss");
        String subject = principal.getSubject();

        return Map.of("issuer", issuer, "subject", subject);
    }
}
~~~

Trong ứng dụng đã đăng nhập qua OIDC và bảo vệ `/me`, Spring cung cấp một `OidcUser` chứa ID Token/claims đã đi qua quá trình xử lý của `oauth2Login`. Ở đây **chỉ hiển thị issuer/subject để học**, không trả nguyên ID Token hay access token ra client. Endpoint này không phải một dịch vụ cấp quyền admin; mục đích là kiểm tra cặp danh tính.

Đừng cho controller nhận `issuer` và `subject` do client POST lên rồi coi chúng là principal đã xác minh; phải lấy từ `Authentication` server-side. Mã là một phần của dự án Spring, không thể `javac` chỉ bằng Java SE nếu thiếu thư viện.

### 8.3. PKCE ở Spring Security

Với **public client**, Spring Security có logic dùng PKCE khi client không có secret và `client-authentication-method=none` theo cấu hình phù hợp. Với **confidential client**, có thể bật PKCE rõ qua `ClientRegistration.ClientSettings.requireProofKey(true)` (API/cách xây registration tùy phiên bản). Cần kiểm tra OP có hỗ trợ `S256` và request thực tế có `code_challenge`; đừng cho rằng `client_secret` thay PKCE hoặc rằng `scope=openid` tự kích hoạt PKCE trong mọi phiên bản.

Spring Security giữ `OAuth2AuthorizationRequest` và các thuộc tính liên quan qua `AuthorizationRequestRepository` (thường dựa `HttpSession`), dùng để đối chiếu `state`, redirect và PKCE verifier. Khi triển khai nhiều instance, cần session/repository dùng chung hoặc routing nhất quán; không xóa `state`/PKCE để “sửa” lỗi callback của nhiều tab.

## 9. Local account, quyền và JIT provisioning sau OIDC login

Một ID Token được xác minh **không cấp mọi quyền sử dụng portal**. Ứng dụng có thể có account bị khóa, chưa được cấp tài khoản, chưa được gán role hay không thuộc tenant.

### 9.1. Ánh xạ `iss` + `sub` tới local account

~~~text
Verified OIDC identity:
    issuer  = https://login.example.org/realms/enterprise
    subject = pairwise-6f13a8

Federated identity binding:
    (issuer, subject) -> local_user_id = user-42

Local account:
    status    = ACTIVE
    tenant_id = tenant-acme
    roles     = [REPORT_VIEWER]
~~~

**Không dùng email làm khóa duy nhất**; email có thể đổi, tái sử dụng hoặc không được OP xác minh theo chính sách mà RP kỳ vọng. Khi broker thay issuer hoặc chuyển từ public `sub` sang pairwise `sub`, cần quy trình re-link có kiểm soát; không tự hợp nhất chỉ vì email giống nhau.

### 9.2. Khi nào cho vào SP?

| Local status/policy | OIDC ID Token hợp lệ? | Quyết định của portal |
| --- | --- | --- |
| `ACTIVE`, đã cấp quyền vào ứng dụng | Có | Thiết lập session với authorities đã được duyệt. |
| `LOCKED` hoặc `DISABLED` | Có | Từ chối login ứng dụng; không lấy “OP thành công” để mở khóa. |
| `PENDING_APPROVAL` | Có | Không cấp quyền nghiệp vụ; có thể hiển thị trang chờ duyệt giới hạn. |
| Không có local account, JIT tắt | Có | Từ chối theo mặc định. |
| Không có account, JIT bật đúng policy | Có | Chỉ tạo/tìm account theo issuer+sub, unique constraint, least privilege, tránh tái tạo account đã bị khóa. |
| Account ACTIVE nhưng thiếu `reports:read` | Có | Có thể cho login, nhưng API báo cáo trả 403. |
| Không thuộc tenant được yêu cầu | Có | Không cấp quyền tenant đó. |
| DB trạng thái/entitlement không khả dụng | Có | **Fail closed** cho điều kiện cấp quyền bắt buộc. |

Trong Spring Security, điểm mở rộng `oauth2Login(oauth2 -> oauth2.userInfoEndpoint(userInfo -> userInfo.oidcUserService(...)))` cho phép chạy một `OAuth2UserService<OidcUserRequest, OidcUser>`: có thể ủy quyền cho `OidcUserService` mặc định rồi áp dụng **local account admission**, ánh xạ authorities và trả về `OidcUser` thích hợp hoặc ném `OAuth2AuthenticationException` khi bị từ chối. Phải bảo toàn xác minh ID Token của framework và giữ `iss/sub` gốc; không tạo một principal giả từ `email` để bỏ qua trust.

Cần phân biệt **ID Token claims** với **approved app entitlements**. `groups` có thể là đầu vào nếu có hợp đồng mapping và trust, nhưng local deny/lock phải thắng, và `ROLE_USER` mặc định không tự cho phép xem mọi tài nguyên. Các API nhiều tenant còn cần **resource ownership và tenant checks** sau login.

### 9.3. Java 17 runnable: danh tính OIDC và chính sách cục bộ

Ví dụ độc lập bên dưới giả định ID Token **đã được xác minh bên ngoài**; nó mô tả account binding bằng `iss+sub`, quyết định deny và quyền theo tenant. Không parse JWT hay thay thế OIDC validator.

Tệp **`OidcIdentityPolicyDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;

public class OidcIdentityPolicyDemo {

    record IdentityKey(String issuer, String subject) {}
    record Account(String localUserId, String tenantId,
                   boolean enabled, Set<String> permissions) {}

    static String authorize(
            IdentityKey verifiedIdentity,
            String requestedTenant,
            String permission,
            Map<IdentityKey, Account> bindings) {

        Account account = bindings.get(verifiedIdentity);
        if (account == null) {
            return "NO_BINDING";
        }
        if (!account.enabled()) {
            return "ACCOUNT_BLOCKED";
        }
        if (!account.tenantId().equals(requestedTenant)) {
            return "TENANT_DENIED";
        }
        if (!account.permissions().contains(permission)) {
            return "PERMISSION_DENIED";
        }
        return "ALLOW:" + account.localUserId();
    }

    public static void main(String[] args) {
        String broker = "https://login.example.org/realms/enterprise";
        IdentityKey alice = new IdentityKey(broker, "pairwise-A");
        IdentityKey bob = new IdentityKey(broker, "pairwise-B");

        Map<IdentityKey, Account> bindings = Map.of(
                alice, new Account("user-42", "tenant-acme", true,
                                   Set.of("reports:read")),
                bob, new Account("user-57", "tenant-acme", false,
                                 Set.of("reports:read"))
        );

        System.out.println(authorize(
                alice, "tenant-acme", "reports:read", bindings));
        System.out.println(authorize(
                bob, "tenant-acme", "reports:read", bindings));
        System.out.println(authorize(
                alice, "tenant-acme", "reports:write", bindings));
        System.out.println(authorize(
                alice, "tenant-other", "reports:read", bindings));
        System.out.println(authorize(
                new IdentityKey("https://idp.other.example", "pairwise-A"),
                "tenant-acme", "reports:read", bindings));
    }
}
~~~

Chạy với Java 17:

~~~bash
javac OidcIdentityPolicyDemo.java
java OidcIdentityPolicyDemo
~~~

**Stdout chính xác:**

~~~text
ALLOW:user-42
ACCOUNT_BLOCKED
PERMISSION_DENIED
TENANT_DENIED
NO_BINDING
~~~

Dòng cuối chứng minh cùng một chuỗi `sub=pairwise-A` nhưng **khác issuer** không được tự nhận là cùng local account. Các dòng giữa minh họa token hợp lệ không phá khóa local account và không cấp thêm quyền. Mã không có JWT parsing, PKCE, nonce, session, đồng bộ DB hay thu hồi token: đó là trách nhiệm của các tầng khác. `verifiedIdentity` không được lấy từ header/JSON do browser gửi.

## 10. Resource server: dùng access token, không dùng ID Token

Giả sử portal gọi `reports-api.example.org` sau login:

~~~text
Browser -- session cookie --> Portal (OIDC RP)
                                  |
                             Access Token
                                  |
                                  v
                         Reports API (Resource Server)
                         - validate issuer
                         - validate audience=reports-api
                         - validate signature/expiry
                         - enforce scope + tenant + resource
~~~

Trong một **Spring Security Resource Server** tách biệt, có thể cấu hình với `spring-boot-starter-oauth2-resource-server` và:

~~~java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(org.springframework.security.config.Customizer.withDefaults()));
~~~

Đây là **mảnh cấu hình thuộc một `HttpSecurity` method**, không phải class độc lập. Cần cấu hình JWT decoder/issuer và **audience validator tùy token contract**, không chỉ bật JWT signature validation rồi suy ra API audience/tenant luôn đúng. Access token của broker phải có audience/scope dành cho API; nếu broker không cấp API token đúng audience, cần OAuth flow/token exchange theo chuẩn và chính sách, **không lấy ID Token của portal gửi vào API**.

### 10.1. Thận trọng với token exchange và downstream propagation

Identity brokering để xác thực **khác** việc gọi API “on behalf of” người dùng. Broker có thể phát ID Token cho portal và access token cho một API cụ thể; hoặc portal cần xin thêm token được cấp bởi AS có trust với API. Việc đưa nguyên access token upstream vào downstream API thường sai vì **audience, issuer, scope và consent** không giống nhau. Chỉ thực hiện token exchange/delegation khi có giao thức, trust policy và API support rõ.

**Không ghi access token/refresh token vào localStorage hoặc log nếu dùng server-side BFF**. Mô hình backend-for-frontend lưu token nhạy cảm server-side, còn browser chỉ giữ cookie session HttpOnly/Secure phù hợp, giảm bề mặt lộ token qua XSS. Cần chống CSRF đối với các request thay đổi trạng thái bằng session cookie.

## 11. Phiên đăng nhập và logout trong federation

Có ít nhất **ba vòng đời phiên** khác nhau:

| Phiên | Sở hữu bởi | Hết hạn/đăng xuất ảnh hưởng |
| --- | --- | --- |
| Browser `HttpSession`/SecurityContext của RP | Portal | Truy cập portal với cookie đó. |
| Phiên OIDC tại Broker OP | Identity broker | Khả năng SSO sang nhiều ứng dụng RP downstream. |
| Phiên đăng nhập tại IdP upstream | IdP SAML/OIDC | Khả năng broker tái xác thực hoặc SSO sang dịch vụ khác. |

**Logout portal không tự logout IdP upstream.** Nếu chỉ xóa `JSESSIONID`, browser có thể mở lại portal, được chuyển tới broker và **đăng nhập lại không cần gõ mật khẩu** vì OP/upstream session vẫn sống.

### 11.1. Local logout và RP-initiated logout

- **Local logout:** invalidates RP session/cookie và `SecurityContext`; không đảm bảo OP hoặc upstream mất phiên.
- **OIDC RP-initiated logout:** nếu OP hỗ trợ, RP chuyển browser đến **end-session endpoint** qua cơ chế `id_token_hint` và post-logout redirect URI đã đăng ký/allowlist theo profile/OP.
- **Broker-to-upstream logout:** broker có thể gọi quy trình riêng với IdP SAML/OIDC, nhưng không phải mọi upstream đều hỗ trợ hoặc đồng ý; cần chính sách fan-out và trạng thái partial.
- **Front-channel/back-channel logout:** tùy khả năng OP/RP và ứng dụng; phải xác minh các logout messages/tokens theo đặc tả, quản lý session theo `sid`/`iss`/`sub` đúng phạm vi. **Không tự cho rằng bật `oauth2Login` đã bật tất cả loại logout**.
- **JWT access token đã phát:** local logout không tự hủy JWT stateless ở API. Cần TTL, revocation/introspection/session version hoặc cơ chế tương ứng.

Trong **Spring Security Servlet**, có `OidcClientInitiatedLogoutSuccessHandler` để hỗ trợ RP-initiated logout khi OP công bố metadata cần thiết; không nhầm với class **reactive** `OidcClientInitiatedServerLogoutSuccessHandler`. Cấu hình phải tương thích version, registration và post-logout URI. Không tự lấy `post_logout_redirect_uri` từ query param không kiểm soát vì open redirect.

### 11.2. Thời hạn token khác thời hạn phiên

ID Token có `exp` nghĩa là token không còn được RP chấp nhận khi thực hiện **xác thực token mới**. Điều đó **không tự đồng nghĩa** RP HTTP session phải kết thúc ngay cùng giây `exp`; session management của ứng dụng là chính sách riêng. Tương tự, refresh token/OP session còn sống không tự cấp phép truy cập API nếu account đã bị khóa tại portal. Khi cần thu hồi quyền nhanh, kiểm tra local status, session revocation và API authorization hiện hành.

## 12. Bảo mật giao dịch OIDC: checklist threat-by-threat

| Rủi ro | Biện pháp cốt lõi |
| --- | --- |
| **Login CSRF** | Kiểm tra `state` chống sửa đổi, liên hệ transaction với browser session; không chấp nhận callback không có request gốc. |
| **Authorization code interception/injection** | **PKCE S256**, redirect URI exact-match, client authentication phù hợp, code TTL ngắn/một lần. |
| **ID Token substitution/replay** | Signature/issuer/audience/time/nonce validation và transaction binding. |
| **Mix-up giữa hai OP/IdP** | Pin issuer/registration vào transaction, so metadata `issuer` và token `iss` chính xác. |
| **JWT algorithm confusion** | Allowlist signature algorithms, dùng đúng JWKS OP, không tin `alg=none`, không tự tải `jku` từ JWT header. |
| **SSRF qua discovery** | Issuer/endpoint do operator quản trị, HTTPS và egress policy; không theo URL do user tự khai. |
| **Open redirect** | Redirect URI đăng ký chính xác; post-login return route nội bộ/allowlist và session-bound state. |
| **Token leakage qua browser/log** | Không nhét access/refresh token vào URL, logs, referrer; dùng cookie HttpOnly/Secure cho server session. |
| **CSRF trên API session** | Không tắt CSRF toàn ứng dụng chỉ vì dùng OIDC; thiết kế cookie và chống CSRF cho state-changing requests. |
| **Cross-tenant data leak** | Dùng issuer/sub mapping và tenant entitlement, kiểm tra ownership/resource ở backend. |
| **Account auto-provision bypass** | JIT có policy, unique binding, lịch sử khóa, tenant approval, least privilege. |
| **Key rotation/compromise** | Cache JWKS với refresh/monitoring, xử lý khóa bị thu hồi; không “bỏ signature check” khi rotation. |
| **Proxy/hostname mismatch** | Cấu hình trusted forwarded headers, HTTPS public base URL và callback chính xác. |
| **Multi-node session loss** | Shared HttpSession/authorization request store hoặc routing an toàn; không xóa state/nonce để sửa lỗi. |
| **UserInfo subject mismatch** | Kiểm tra `userinfo.sub == id_token.sub`; không map user theo email của response khác. |

**Không “đơn giản hóa” OIDC bằng cách chuyển phần xác minh JWT vào JavaScript ở frontend rồi backend tin header `X-User`**. Backend cần danh tính đã được framework xác thực hoặc một token hợp lệ cho đúng audience và trust context. Bảo mật ứng dụng vẫn yêu cầu CSRF/XSS/session controls, HTTPS, least privilege và audit.

## 13. Troubleshooting theo ranh giới và lỗi thực tế

| Hiện tượng | Vị trí thường lỗi | Cách chẩn đoán |
| --- | --- | --- |
| Bấm Login nhưng 404 ở `/oauth2/authorization/broker`. | RegistrationId không tồn tại, `oauth2Login` không được bật, filter chain khác. | Kiểm tra dependency, registration `broker`, chain và login endpoint. |
| Redirect URI mismatch ở OP. | URI đăng ký khác URI runtime của portal. | So `{baseUrl}/login/oauth2/code/broker`, scheme/host/port và proxy. |
| `invalid_client` khi đổi code. | Client secret/authentication method sai hoặc client không được đăng ký. | Kiểm tra secret manager/registration và OP logs; không lộ secret. |
| `invalid_grant` ở token endpoint. | Code hết hạn/đã dùng, PKCE verifier sai, redirect URI không khớp. | Correlation ID, code TTL, verifier per-transaction và đồng hồ. |
| State không khớp hoặc missing authorization request. | Cookie session mất, SameSite, nhiều tab hoặc load balancer sang node khác. | Kiểm tra callback cookie, session store, state repository. |
| Issuer validation fails. | Metadata `issuer` khác `iss` của ID Token hoặc chọn sai OP. | So đúng exact HTTPS issuer, tenant, discovery và registration. |
| Audience validation fails. | ID Token dành client khác (broker/upstream) hoặc client-id sai. | So `aud` và `client_id`; **không bỏ audience validation**. |
| Signature/JWKS error. | Signing key rotation, JWKS cache stale, `kid` không khớp, thuật toán sai. | Kiểm tra OP metadata/JWKS tin cậy, refresh policy, thời gian rotation. |
| UserInfo trả user khác. | Access token dùng nhầm hoặc OP trả `sub` không trùng. | Kiểm tra `UserInfo.sub` so ID Token; từ chối mismatch. |
| IdP upstream login thành công nhưng portal không vào được. | Broker mapping/policy, downstream OIDC callback, account admission. | Xác định chặng nào báo lỗi, không coi upstream success bằng downstream success. |
| Đăng nhập xong nhưng 403 tính năng. | Local role/tenant/permission không đủ. | Kiểm tra authorization, approved entitlements; không “đổi ID Token” để sửa quyền. |
| Account có email đúng nhưng vào nhầm local user. | Mapping theo email thay vì `iss+sub`. | Sửa identity binding và quy trình migration, audit việc merge. |
| Logout xong lập tức tự login lại. | Chỉ local logout, OP/upstream session còn hiệu lực. | Phân biệt local, RP-initiated và broker/upstream logout. |
| API trả 401 dù portal đã login. | Access token không có hoặc không dành API audience, API yêu cầu scope khác. | Kiểm tra `aud`/`scope` của **access token** và resource server config. |
| Hai tenant chọn nhầm IdP. | Home realm routing dựa URL/email hint không ràng buộc transaction. | Kiểm tra HRD allowlist, issuer và tenant binding. |

**Thứ tự debug hợp lý:** (1) URL/registration/OP discovery → (2) `state` và session cookie → (3) PKCE/client/token exchange → (4) ID Token signature/issuer/audience/time/nonce → (5) broker identity mapping → (6) local admission → (7) Spring session/authorization → (8) API token audience/resource permission. Log **mã lỗi và correlation**, không log token/cookie/secrets.

## 14. Bộ test cần có trước khi đưa vào production

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| OIDC code flow với OP test tin cậy, `state`/PKCE/nonce đúng. | Login thành công và tạo local Authentication theo policy. |
| Callback state thuộc browser khác. | Từ chối; không login CSRF. |
| Callback dùng code cũ đã đổi token. | Token endpoint từ chối; không đăng nhập lần hai. |
| PKCE `code_verifier` sai hoặc thiếu khi challenge yêu cầu. | Token exchange bị từ chối. |
| ID Token `iss` khác metadata/registration. | Từ chối. |
| `aud` không chứa portal client ID. | Từ chối dù signature đúng. |
| ID Token hết hạn/chưa hợp lệ theo policy. | Từ chối. |
| ID Token `nonce` không khớp với request đã gửi. | Từ chối. |
| ID Token ký bởi key ngoài OP JWKS đáng tin. | Từ chối. |
| OP rotate JWKS signing key đúng chuẩn. | Đảm bảo cập nhật trust theo chính sách, không fail-open. |
| UserInfo `sub` khác ID Token `sub`. | Từ chối dùng dữ liệu UserInfo. |
| Hai OP cùng email nhưng `iss+sub` khác. | Không tự merge local account. |
| Broker dùng upstream SAML và downstream OIDC. | Broker xác minh SAML, portal chỉ chấp nhận token issuer broker/audience portal. |
| Portal nhận trực tiếp ID Token upstream có `aud=broker-client`. | Từ chối. |
| Account local bị LOCKED nhưng broker OIDC hợp lệ. | Không cấp quyền ứng dụng. |
| User ACTIVE nhưng không có entitlement báo cáo. | Từ chối resource, thường 403. |
| Token API audience không đúng. | Resource Server từ chối, không dùng ID Token thay thế. |
| Nhiều tab login cùng phiên, response về ngược thứ tự. | State/nonce/PKCE mỗi giao dịch độc lập; không lẫn danh tính. |
| Callback tới node khác so với node bắt đầu. | Shared state đúng hoặc fail closed; không bỏ state. |
| Broker mất upstream session nhưng portal còn local session. | Hành vi đúng TTL/logout/re-auth policy, không suy ra phiên nào đã bị hủy. |
| Local logout khi OP session còn. | Ứng dụng biết giới hạn, không báo toàn federation đã logout. |
| Redirect URI hay post-logout URL là external host chưa đăng ký. | Từ chối, không open redirect. |
| IdP upstream gửi assurance yếu nhưng portal yêu cầu MFA. | Broker không gắn claims giả; yêu cầu step-up hoặc deny. |

Kiểm thử cần dùng **OP/IdP test hợp lệ và token có chữ ký kiểm soát**. Một unit test chỉ parse payload JWT không chứng minh xác thực OIDC đúng. Phải bao gồm browser thực (cookies/SameSite), reverse proxy, token endpoint, tài khoản và authorization API.

## 15. Những hiểu lầm cần tránh

1. **“OAuth2 = OIDC.”** Không; OIDC là lớp identity trên OAuth 2.0 với ID Token và các quy tắc xác minh danh tính.
2. **“Access Token chứng minh người dùng đăng nhập vào portal.”** Không nên dùng access token cho RP login khi thiết kế OIDC; cần ID Token và luồng OIDC.
3. **“ID Token có thể gọi bất kỳ API.”** Sai: ID Token có audience là RP, API dùng access token dành chính resource server.
4. **“JWT decode ra email là đủ.”** Sai: phải xác minh signature/issuer/audience/expiration/nonce.
5. **“Email là định danh ổn định, duy nhất.”** Sai: dùng `iss+sub` làm khóa chuẩn.
6. **“`sub` luôn giống nhau giữa mọi client và IdP.”** Sai: có public/pairwise subject và issuer scope.
7. **“Broker chỉ forward ID Token upstream cho portal.”** Sai: trust/issuer/audience ở hai chặng khác nhau; broker phát hành token downstream của mình.
8. **“Broker tin SAML NameID mà không xác minh assertion.”** Sai: broker phải xác minh chữ ký/conditions/subject confirmation/replay.
9. **“Client secret nghĩa là không cần PKCE.”** Không phải; PKCE nên được bật/kiểm chứng cho Authorization Code Flow theo chính sách.
10. **“`state`, `nonce`, PKCE là một thứ.”** Sai: chúng bảo vệ các rủi ro và các bước khác nhau.
11. **“Lấy issuer URL từ form của người dùng rồi tự discovery.”** Nguy hiểm: SSRF/mix-up, phải dùng OP allowlist/config.
12. **“IdP group admin thì portal luôn cho admin.”** Sai: quyền application/tenant cần mapping đã phê duyệt và local policy.
13. **“Login qua broker thì portal không cần authorization.”** Sai: tenant/ownership/business policy vẫn là trách nhiệm RP/API.
14. **“Local logout xóa mọi OP/upstream session.”** Sai: có các phiên riêng và cơ chế logout/partial.
15. **“`oauth2Login` tự động là OAuth2 Resource Server.”** Sai: client login và API JWT verification là hai vai trò khác.
16. **“JWKS rotation lỗi thì tạm bỏ kiểm tra chữ ký.”** Sai: cần xử lý key lifecycle an toàn, không fail-open.
17. **“OIDC thành công thì JIT tạo user ACTIVE vô điều kiện.”** Sai: cần local admission, approval, status và chống bypass account đã khóa.
18. **“SAML và OIDC dùng cùng callback URL.”** Sai: ACS SAML nhận `SAMLResponse`, OIDC callback nhận authorization code/state.

## 16. Checklist triển khai kiến trúc liên kết

1. RP có **trust relationship OIDC cụ thể** với broker/OP, đúng `issuer-uri`, `client_id`, redirect URI và scope `openid` không?
2. Có dùng Authorization Code + PKCE S256, TLS, state per transaction và nonce khi cần không?
3. ID Token có được kiểm tra **issuer, signature/JWKS, aud/azp, exp/iat, nonce** theo profile không?
4. Nếu dùng UserInfo, `sub` có được so với ID Token không?
5. Có định danh local bằng **`iss+sub`**, không bằng email/role tự khai không?
6. Nếu broker nhận SAML upstream, có kiểm tra SAML signature, audience, conditions, subject confirmation/`InResponseTo` và replay không?
7. Broker có **tự phát hành** ID Token downstream đúng `iss`, `aud`, subject và chính sách assurance không?
8. Có chính sách HRD/tenant mapping và chống IdP mix-up, không dùng issuer URL do user cung cấp không?
9. Có JIT/account admission/entitlement policy, thu hồi quyền và deny precedence không?
10. API có nhận **access token dành riêng cho audience**, không nhận ID Token của portal không?
11. Proxy, callback URI, cookie SameSite/Secure và session store có được kiểm thử ở deployment thật không?
12. Có policy local logout, RP-initiated logout, OP/upstream logout và token revocation riêng không?
13. Có chạy thử nhiều tab, IdP lỗi, broker outage, token key rotation, refresh token expiry và database failures không?
14. Có log/audit theo correlation ID, không lưu token, cookie, secret và PII thô không?

## 17. Tự kiểm tra kiến thức

1. **OIDC khác OAuth 2.0 ở đâu?** — OIDC chuẩn hóa xác thực người dùng qua **ID Token** và các yêu cầu về claims/issuer/client.
2. **Hai vai của broker là gì?** — **RP/SP** khi tin upstream và **OP/AS** khi phát hành downstream.
3. **Token nào dùng để đăng nhập RP?** — **ID Token** đã xác minh cùng giao dịch OIDC.
4. **Token nào dùng để gọi protected API?** — **Access Token** hợp lệ cho audience/scope của API.
5. **Khóa nhận diện ổn định của OIDC là gì?** — Cặp **`iss` + `sub`**; không phải email.
6. **Vì sao `aud` phải chứa `client_id` của portal?** — Vì token chỉ có giá trị xác thực cho đúng RP được chỉ định.
7. **`state`, `nonce`, PKCE làm gì?** — State bảo vệ correlation/CSRF, nonce gắn ID Token với authentication request, PKCE ràng buộc đổi authorization code với client đã khởi tạo.
8. **Có được gửi ID Token upstream trực tiếp cho downstream RP không?** — Không trong mô hình broker thông thường; issuer/audience và trust khác.
9. **SAML NameID có nhất thiết bằng OIDC `sub` do broker phát không?** — Không; broker có identity mapping/pairwise subject.
10. **Bật `oauth2Login` là đã kiểm tra local account LOCKED và tenant permission chưa?** — Chưa; phải nối admission/authorization riêng.
11. **ID Token hết hạn là mọi RP HttpSession lập tức biến mất?** — Không tự động; chính sách session độc lập.
12. **Logout portal có đảm bảo upstream IdP logout không?** — Không; cần logout orchestration và khả năng giao thức riêng.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authorization Code Flow, ID Token Validation, UserInfo, Subject Types](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — issuer, metadata, JWKS](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OAuth 2.0 PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html)
- [Spring Security — OAuth2/OIDC Servlet Login Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security — Advanced OAuth2 Login, OidcUserService và UserInfo](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — Client Authorization Grants / PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
