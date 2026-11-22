# Chuyển đổi SAML sang OIDC tại hệ thống môi giới và trách nhiệm của từng bên

> **Module:** Spring Security – federation. **Nhóm:** OIDC và môi giới. Bài học mô tả mô hình **upstream SAML IdP → Identity Broker → downstream OIDC Relying Party (RP)**. Mỗi chặng có trust boundary, chữ ký, audience, session và trách nhiệm khác nhau. Ví dụ dùng **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x** phía OIDC client; cách cấu hình broker được giải thích bằng mô hình sản phẩm như Keycloak. Việc bật `saml2Login()` và `oauth2Login()` trong cùng Spring Security application **không tự động biến application thành OpenID Provider (OP)**.

## 1. Mục tiêu bài học và kiến thức nền

Sau bài học, người học có thể:

1. Phân biệt các vai trò: **Corporate SAML IdP**, **Broker ở vai SAML SP**, **Broker ở vai OIDC OP/Authorization Server**, **OIDC RP**, và **OAuth2 Resource Server**.
2. Giải thích SAML→OIDC là quy trình **verify upstream identity → account linking → phát hành chứng thực OIDC mới**; không phải “đổi XML thành JSON” hay “đóng gói SAML assertion vào JWT”.
3. Theo dõi luồng OIDC Authorization Code từ RP, chuyển sang SAML AuthnRequest, xác minh SAMLResponse tại broker, phát authorization code, đổi code lấy ID Token và RP xác minh token.
4. Chỉ ra **SAML Issuer và Audience** khác **OIDC iss và aud**; hiểu ai giữ private key nào và ai tin public certificate/JWKS của bên nào.
5. Xây chính sách ánh xạ `NameID`/attributes/`AuthnContext`/`AuthnInstant` thành external identity link, broker user, `sub`, `email`, `email_verified`, `auth_time`, `acr`, `amr` mà không tự nâng độ tin cậy.
6. Hiểu cách `state`, `nonce`, PKCE, `InResponseTo`, `RelayState` và broker sessions bảo vệ các giao dịch riêng biệt.
7. Phân biệt ID Token, Access Token và Refresh Token; kiểm đúng issuer, audience và quyền truy cập API/tenant.
8. Cấu hình một ứng dụng Spring Boot là **OIDC RP** tin broker; chạy ví dụ Java 17 kiểm identity linking và đối chiếu kết quả chính xác.
9. Thiết kế thử nghiệm âm, audit, key rotation, logout, session revocation và onboarding/offboarding IdP/tenant.
10. Giải thích **trách nhiệm của từng bên** khi lỗi login, không trộn SAML trust vào OIDC token validation.

Kiến thức cần có: SAML Web Browser SSO, IdP/SP metadata, `RelyingPartyRegistration`, `SAMLResponse`/`AuthnRequest`/`Assertion`, chữ ký XML; OAuth2 Authorization Code, OIDC Discovery, JWS/JWK; HTTP redirects/POST, TLS, cookies và Spring Security `SecurityFilterChain`.

## 2. Kiến trúc tổng thể: broker đóng hai vai giao thức

Một công ty có Corporate IdP phát **SAML 2.0**, còn Portal hiện đại hỗ trợ **OpenID Connect**. Để Portal không phải tự trở thành SAML SP, ta sử dụng broker.

~~~text
                  Browser của user
                         |
                         | OIDC /authorize
                         v
               Portal Web (OIDC RP)
               client_id = portal-web
                         |
                         v
          +------------------------------------+
          |       Identity Broker              |
          |                                    |
          |  Bên downstream: OIDC OP           |
          |  issuer=https://broker.example.org |
          |  /authorize /token /jwks /userinfo |
          |  client registry, OP session       |
          |  ký ID Token bằng BROKER key       |
          |                                    |
          |  Bên upstream: SAML SP             |
          |  entityID=urn:broker:saml:sp        |
          |  ACS=/saml/acs/corporate           |
          |  tin SAML IdP public certificate   |
          |  nhận + validate SAMLResponse      |
          |                                    |
          |  Identity mapping / Account link   |
          +------------------------------------+
                         |
                         | SAML AuthnRequest
                         v
               Corporate SAML IdP
               - kiểm account/MFA
               - ký SAML Assertion
               - phát NameID/Attributes
~~~

**Broker SP** là “khách hàng SAML” của Corporate IdP. **Broker OP** lại là “nhà cung cấp danh tính OIDC” của Portal. Một thành phần phần mềm có thể đảm nhận cả hai, nhưng **đó là hai trust contracts độc lập**.

### Bảng tên gọi và hướng dữ liệu

| Tên | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Upstream SAML IdP | `https://idp.corp.example.org/saml` | Nguồn xác thực user, phát signed Assertion |
| Broker SAML SP entity ID | `urn:broker:saml:sp` | Đối tượng được phép tiêu thụ SAML assertion |
| Broker ACS | `https://broker.example.org/saml/acs/corporate` | Callback nhận SAMLResponse của upstream IdP |
| Broker OIDC issuer | `https://broker.example.org/realms/workforce` | Giá trị `iss` của OIDC ID Token broker phát |
| Downstream RP | Portal Web | Đăng nhập bằng OIDC code flow, verify broker token |
| OIDC client ID | `portal-web` | Giá trị `aud` mong đợi trong Portal ID Token |
| RP redirect URI | `https://portal.example.org/login/oauth2/code/broker` | Callback mang OIDC authorization code |
| Resource Server | Reports API | Verify **Access Token** dành cho API, không dùng raw SAMLResponse |

Các URL và ID chỉ để minh họa. Trong production phải lấy từ metadata/registration được quản trị phê duyệt.

## 3. Ai chịu trách nhiệm cho bước nào?

| Chủ thể | Nhận thông điệp | Phải kiểm chứng | Sở hữu khóa và dữ liệu |
| --- | --- | --- | --- |
| **Corporate SAML IdP** | SAML AuthnRequest từ broker | SP entityID, ACS, chữ ký request theo policy, session/user/assurance | IdP giữ **SAML signing private key**, ký Response/Assertion và phát stable identifier theo hợp đồng |
| **Broker ở vai SAML SP** | SAMLResponse qua browser | IdP signature, Issuer, Audience broker SP, Destination/Recipient broker ACS, Conditions/time, InResponseTo/replay | Broker tin public signing cert IdP từ metadata; giữ SP signing/decryption private keys nếu cần |
| **Broker identity layer** | Upstream identity đã verified | Entity ID + NameID/format/qualifiers, tenant, account status, external link, claims/assurance policy | Quản lý broker local user ID, account links, session và claim mapper |
| **Broker ở vai OIDC OP** | OIDC /authorize, /token và client request | Registered client, exact redirect URI, code+PKCE, client auth, scopes, consent, session, nonce | Giữ **OIDC token signing private key**, phát ID Token/Access Token, public JWKS |
| **Portal OIDC RP** | Authorization response + broker ID Token | state, token issuer=broker, signature qua broker JWKS, aud=Portal client_id, nonce, expiry và các claims cần thiết | Tạo Portal HTTP session, kiểm user/tenant/roles của Portal |
| **Reports API** | Access Token do client gửi | Token issuer, signature/introspection, audience=API, scopes, expiry, tenant/resource entitlement | Enforce API authorization; không dùng ID Token như access token |

**Quan hệ tin cậy không có tính bắc cầu tự động.** Portal có thể tin broker OP về xác thực, nhưng Portal **không** vì thế được tin mọi SAML IdP mà broker có thể kết nối; broker phải giới hạn upstream providers và làm validation. Và broker tin IdP ký SAML Assertion **không** đồng nghĩa mọi SAML Attribute có thể cấp role admin trong Portal.

### Chữ ký của hai chặng khác nhau

~~~text
Corporate IdP private key
    └─ ký SAML Response/Assertion
        └─ Broker verify với IdP public cert (SAML metadata)

Broker OIDC private signing key
    └─ ký ID Token (JWS)
        └─ Portal verify với Broker public JWKS (OIDC Discovery)

Broker SP signing private key (nếu có)
    └─ ký SAML AuthnRequest gửi IdP
        └─ IdP verify bằng Broker SP public certificate
~~~

**Không bao giờ cấp IdP private signing key cho broker/Portal chỉ để verify SAML.** Broker dùng **public** certificate IdP. Không công khai private broker key trong JWKS; JWKS chỉ có public key material. Một ID Token được broker ký phải ghi **`iss=broker issuer`**, không ghi issuer IdP SAML.

## 4. Luồng end-to-end: OIDC Code Flow và SAML Web Browser SSO

Xem 14 bước, trong đó browser vận chuyển các request/response nhưng **không phải một trust anchor**.

1. User mở `https://portal.example.org/private`, Portal chưa có local session.
2. Portal tạo OIDC authorization request gửi tới Broker OP: `response_type=code`, `client_id=portal-web`, registered `redirect_uri`, `scope=openid profile`, random `state` và `nonce`; PKCE `code_challenge` nếu dùng theo policy. Portal lưu pending request/nonce/code_verifier gắn browser session.
3. Broker kiểm registered OIDC client, exact redirect URI và allowed scopes, xác định đã có OP session phù hợp hay chưa.
4. Nếu chưa có identity, broker chọn một **SAML IdP đã duyệt** bằng tenant/domain/policy. Không nhận arbitrary metadata/IdP URL từ query parameter.
5. Broker (lúc này là SAML SP) tạo `AuthnRequest` với ID duy nhất, SP entityID, ACS và lưu request context trong repository. Ký AuthnRequest nếu IdP yêu cầu.
6. Browser được redirect/POST sang Corporate SAML IdP; IdP xác thực user/MFA, kiểm request và phát SAMLResponse/Assertion ký hợp lệ.
7. Browser POST SAMLResponse vào **Broker ACS**. Broker xác minh chữ ký bằng trusted IdP cert, Issuer, Audience=Broker SP entityID, Recipient/Destination=Broker ACS, thời hạn, SubjectConfirmation, InResponseTo và replay.
8. Broker chỉ lấy NameID/Attributes/AuthnContext **sau validation**; từ đó tra ExternalIdentityLink, policy tenant, disabled user và first-broker-login/account verification.
9. Broker tạo/khôi phục broker-local identity và OP session. Broker lưu thông tin nguồn xác thực/assurance và session mapping theo chính sách, không dùng SAML SessionIndex như OIDC subject.
10. Broker quay lại **giao dịch OIDC đang chờ**, kiểm client/redirect/nonce/PKCE context và phát authorization code một lần.
11. Browser được redirect đến registered Portal `redirect_uri` cùng `code` và `state`.
12. Portal kiểm `state`; backend gửi code, redirect URI, client authentication và PKCE `code_verifier` tới Broker Token Endpoint.
13. Broker kiểm code chưa dùng/TTL/client/redirect/verifier và phát **ID Token mới** có `iss=broker`, `aud=portal-web`, `sub=broker-issued subject`, `iat`/`exp` và `nonce` tương ứng; có thể phát Access/Refresh Tokens theo client policy.
14. Portal xác minh ID Token qua broker Discovery/JWKS, tạo local session; khi gọi API chỉ dùng Access Token được cấp đúng audience/scope cho API và kiểm quyền nghiệp vụ.

~~~text
Browser         Portal (OIDC RP)          Broker (OIDC OP+SAML SP)         SAML IdP
   |                    |                            |                       |
   | GET /private       |                            |                       |
   |------------------->|                            |                       |
   | 302 /authorize?code,state,nonce,PKCE            |                       |
   |<-------------------|                            |                       |
   |------------------------------------------------>|                       |
   |                    |                 AuthnRequest ID=_req1             |
   |                    |                            |---------------------->|
   |<------------------------------------------------------------browser-----|
   |              SAMLResponse signed, InResponseTo=_req1                 |
   |---------------------------------------------------------------> Broker ACS
   |                    |                    validate SAML <---------------|
   |                    |                    map identity / broker session |
   | 302 RP redirect_uri?code=_code1&state=_state1   |                       |
   |<------------------------------------------------|                       |
   |------------------->|                            |                       |
   |                    | POST /token(code,client,verifier)                  |
   |                    |--------------------------->|                       |
   |                    | signed broker ID Token + access token              |
   |                    |<---------------------------|                       |
   |                    | verify issuer/JWKS/aud/nonce/exp                   |
   | 200 /private       |                            |                       |
   |<-------------------|                            |                       |
~~~

Đây là sơ đồ logic, không phải exact HTTP trace của một sản phẩm. Khi broker hoặc IdP đã có session, một vài bước tương tác người dùng có thể được bỏ qua mà vẫn phải giữ security/correlation policy.

### Bảo vệ giao dịch SAML khác OIDC

| Tham số | Ai tạo | Ai kiểm | Dùng để làm gì |
| --- | --- | --- | --- |
| SAML `AuthnRequest/@ID` | Broker SAML SP | Broker so `Response/@InResponseTo` | Gắn SAML Response với giao dịch |
| SAML `RelayState` | Broker SAML SP/binding | Broker | Giữ flow state, không phải OIDC nonce |
| OIDC `state` | Portal OIDC RP | Portal | Chống CSRF/mix-up tại OIDC callback |
| OIDC `nonce` | Portal RP | Portal so với ID Token | Chống token substitution/replay |
| OIDC `code_challenge` | Portal RP | Broker OP khi đổi code | PKCE ràng code với client đã khởi tạo |
| OIDC `code_verifier` | Portal RP | Broker OP tại /token | Chứng minh sở hữu verifier |
| Authorization code | Broker OP | Broker OP tại /token | Grant dùng một lần, gắn client, redirect, TTL |

**Không tự thay SAML InResponseTo bằng OIDC state, và không dùng RelayState làm nonce.** Broker phải quản lý hai pending transactions. Với IdP-initiated SAML SSO không có AuthnRequest, có nguy cơ login CSRF và thiếu OIDC request context; cần quyết định rõ có hỗ trợ unsolicited hay không, không tự phát OIDC token cho một client chưa đăng ký/không có giao dịch hợp lệ.

## 5. Đọc SAML Assertion ở broker

Một phần SAML Response **chỉ để học cú pháp, không có chữ ký nên không được chấp nhận**:

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  Version="2.0" ID="_resp1"
  IssueInstant="2030-01-01T09:58:00Z"
  InResponseTo="_req1"
  Destination="https://broker.example.org/saml/acs/corporate">
  <saml:Issuer>https://idp.corp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assert1" Version="2.0"
                  IssueInstant="2030-01-01T09:58:00Z">
    <saml:Issuer>https://idp.corp.example.org/saml</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format=
        "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        external-person-100
      </saml:NameID>
      <saml:SubjectConfirmation Method=
        "urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_req1"
          Recipient="https://broker.example.org/saml/acs/corporate"
          NotOnOrAfter="2030-01-01T10:03:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-01-01T09:57:00Z"
        NotOnOrAfter="2030-01-01T10:03:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:broker:saml:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
      AuthnInstant="2030-01-01T09:55:00Z"
      SessionIndex="_saml-session1"/>
  </saml:Assertion>
</samlp:Response>
~~~

Mẫu chưa có `ds:Signature` và có thể thiếu các phần tử khác theo profile; **không sử dụng như SAMLResponse thực**. Broker phải có trusted metadata, đúng signer, time, subject, correlation và replay handling.

- **SAML Issuer** = Corporate SAML IdP entity ID.
- **SAML Audience** = Broker SP entity ID, **không phải client_id Portal**.
- **SAML Destination/Recipient** = Broker ACS, **không phải OIDC redirect URI**.
- **SAML InResponseTo** = AuthnRequest broker tạo.
- **NameID** = upstream subject theo IdP, **chưa phải OIDC `sub`**.
- **AuthnInstant** = thời điểm IdP tuyên bố xác thực, có thể dùng để xác định `auth_time` sau khi đã kiểm và map chính sách.
- **SessionIndex** = SAML IdP session linkage cho logout theo profile; không dùng làm broker OIDC subject hoặc session ID.

### SAML XML Signature chưa được xác minh tuyệt đối không được tin

Browser có thể gửi XML bất kỳ. Broker phải verify bằng IdP signing public certificate đã lấy từ **metadata được quản trị phê duyệt**, kiểm đúng signed element được sử dụng, tránh XML Signature Wrapping, issuer spoofing và encrypted-but-unsigned confusion. Giải mã Assertion thành công không có nghĩa chữ ký hợp lệ. Không dùng XML parser tự viết bằng string/regex rồi lập broker session.

## 6. OIDC ID Token do broker phát

Sau khi SAML authentication/identity mapping pass, Broker OP phát token có **issuer, audience, lifetime và chữ ký của chính broker**.

**Chỉ là JSON payload minh họa, không có JWS header/signature, không thể dùng đăng nhập thật:**

~~~json
{
  "iss": "https://broker.example.org/realms/workforce",
  "sub": "broker-pairwise-subject-portal-42",
  "aud": "portal-web",
  "iat": 1893459900,
  "exp": 1893460500,
  "auth_time": 1893459300,
  "nonce": "oidc-nonce-from-portal",
  "acr": "urn:example:assurance:verified",
  "email": "person@example.org",
  "email_verified": true
}
~~~

**Không sao chép nguyên mẫu các giá trị bảo đảm:** `email_verified=true` và `acr` chỉ được phát khi broker policy đã có nguồn và bằng chứng xác thực phù hợp, không phải vì upstream gửi một chuỗi email hoặc IdP được đặt tên “corporate”.

**Giải thích những giá trị bắt buộc/quan trọng:**
- `iss` là **Broker OIDC issuer** từ Discovery và client configuration, không phải SAML IdP entity ID.
- `sub` là subject theo namespace của Broker OP; ổn định, không tái cấp cho người khác, có thể public hoặc pairwise tùy policy.
- `aud` là OIDC `client_id` của Portal; RP phải kiểm chứa `portal-web` và xử lý multi-audience/`azp` đúng OIDC rules.
- `iat` là lúc token được broker phát; `exp` là hạn token. Không phải SAML Assertion expiry.
- `auth_time` là thời điểm user thực sự được xác thực theo bằng chứng/chính sách; không tự dùng “thời điểm broker nhận Response”.
- `nonce` phải trùng nonce từ **OIDC authorization request của Portal** (nếu request có nonce); SAML không phát OIDC nonce thay Portal.
- `email` là profile claim tùy scope/policy; `email_verified` không được tự ý suy từ sự tồn tại của email.
- `acr`/`amr` không có phép đổi tự động 1–1 từ SAML `AuthnContextClassRef`.

### Mã nào ký ID Token?

**Broker OP** ký JWT mới bằng signing private key của broker. Portal verify bằng public key từ `jwks_uri` trong **broker's approved OIDC Discovery**. Một SAML XML Signature có thể vẫn tồn tại trong upstream Response, nhưng không được “truyền tiếp” như chữ ký của JWT; hai chữ ký có phạm vi và đối tượng khác nhau.

### OIDC RP cần kiểm gì?

Theo OIDC Core/Authorization Code:
1. `iss` khớp chính xác issuer broker đã cấu hình, không nhận arbitrary issuers do token tự chỉ.
2. `aud` bao gồm `client_id`; nếu nhiều audiences/`azp`, áp policy OIDC phù hợp.
3. Chữ ký JWS/`alg` bằng key từ JWKS của issuer đã tin; không dùng untrusted `jku`, `x5u` hoặc JWK nhúng để tạo trust mới.
4. `exp` chưa hết hạn, `iat` hợp lý/clock skew phù hợp.
5. `nonce`, nếu gửi, phải được RP so với pending nonce; `state` của authorization response được kiểm riêng.
6. Authorization code exchange phải đúng client, redirect và PKCE verifier; code một lần, TTL ngắn.
7. `acr`, `auth_time`, `amr` nếu RP cần MFA/re-authentication phải được kiểm semantic.
8. Khi dùng UserInfo, `sub` trả từ UserInfo phải phù hợp ID Token `sub` theo OIDC.
9. Sau xác thực, Portal còn phải kiểm account enabled, tenant và quyền resource: một ID Token valid **không tự cấp mọi quyền nghiệp vụ**.

## 7. Chuyển SAML NameID thành broker identity và OIDC sub

Đây thường là lớp logic quan trọng nhất của broker. Hai IdP có thể phát cùng NameID hoặc email. Nếu broker auto-link tài khoản theo email, một identity ở IdP B có thể bị nối nhầm vào account IdP A.

### 7.1. External identity key an toàn

~~~text
ExternalIdentityKey:
    trusted IdP entityID
    + NameID Format
    + NameID qualifiers/context nếu có
    + stable NameID value
         |
         v
  Approved IdentityLink store
    ExternalIdentityKey -> brokerInternalUserId
         |
    User active? Tenant allowed?
    Account link approved?
         |
         v
  Broker local session / subject
         |
  OIDC subject policy (public/pairwise)
         |
    sub issued to OIDC Client
~~~

Không dùng một transient NameID làm durable external identity key nếu không có stable identifier khác được hợp đồng IdP bảo đảm. Email có thể thay đổi hoặc được tái cấp; email **không phải security principal identifier** giữa các IdP. Identity link nên gắn nguồn IdP đáng tin, định danh nguồn, định dạng, tenant/membership và lịch sử approval.

### 7.2. First broker login và account linking

Một quy trình hợp lý:
1. SAML Response đã verified và IdP được phép đăng nhập vào tenant.
2. Tìm external identity link theo **issuer+stable subject**, không theo email đơn lẻ.
3. Nếu đã link: kiểm user enabled/tenant membership và chính sách update attributes rồi tiếp tục.
4. Nếu chưa link: đi vào workflow first broker login có xác minh account, invitation/provisioning/approval hoặc tự tạo account **chỉ theo policy rõ**; không tự nối vào existing account chỉ vì email giống.
5. Nếu phát hiện hai accounts có email trùng: không tự hợp nhất; yêu cầu chứng minh sở hữu/administrator approval.
6. Khi IdP đổi NameID format hoặc user di chuyển tenant: có migration procedure và audit.
7. Khi user bị disabled/offboard: thu hồi broker sessions/refresh tokens/links theo chính sách và đánh giá tokens còn hiệu lực.

Keycloak có First Broker Login, identity provider mappers và account linking; các tính năng này giúp thực hiện policy nhưng không thay security review. Tài liệu Keycloak cảnh báo auto-link existing users theo email trong cấu hình mở có thể dẫn đến takeover.

### 7.3. Pairwise sub

Một broker OP có thể dùng `sub` loại **public** (một user có cùng subject giữa OIDC clients) hoặc **pairwise** (subject thay đổi theo sector/client policy). Pairwise có lợi cho privacy khi Portal và Payroll không cần chia sẻ cùng định danh.

~~~text
Broker internal user: person-101

OIDC Client Portal:
  sub = pairwise-portal-7f0d

OIDC Client Payroll:
  sub = pairwise-payroll-5e31

=> Hai OIDC clients không tự suy ra đây là cùng người.
~~~

Không tự tạo pairwise `sub=SHA256(email)` đơn giản; email đoán được, có thể đổi và không phù hợp ổn định/mức riêng tư. Dùng subject generation policy được OP hỗ trợ và sector identifier được duyệt.

## 8. Claim mapping: không tự nâng độ tin cậy

| SAML upstream đã được kiểm | Có thể ánh xạ sang OIDC | Điều kiện và rủi ro |
| --- | --- | --- |
| `Issuer` của IdP | **Không map vào OIDC `iss`** | OIDC iss bắt buộc là Broker OP issuer; nếu cần nguồn upstream, dùng internal audit/custom claim có kiểm soát |
| `NameID` + format/context | Broker internal identity → OIDC `sub` | Có link ổn định, tránh collision và transient NameID |
| `mail` attribute | `email` | Tối thiểu hóa, client scope/consent và policy nguồn |
| Email đã verify theo hợp đồng đáng tin | `email_verified` | Chỉ true khi có bằng chứng; email tồn tại không đồng nghĩa verified |
| `givenName`/`sn` | `given_name`/`family_name` | Mapper version hóa, normalize thận trọng, không dùng làm identity key |
| `AuthnInstant` | `auth_time` | Đúng thời điểm authenticated theo IdP/broker policy, không phải token issuance time |
| `AuthnContextClassRef` | `acr` | Chỉ khi có bảng mapping mức assurance đã thống nhất |
| Auth method/MFA assertion đáng tin | `amr` | Không tự thêm `otp`/`mfa` nếu upstream không chứng minh |
| `SessionIndex` | Upstream session linkage ở broker | Không tự dùng làm OIDC `sub` hoặc `sid` |
| `AudienceRestriction` | Không map vào OIDC `aud` | SAML audience chỉ Broker SP; OIDC aud là downstream client |
| SAML `NotOnOrAfter` | Không copy cơ học vào OIDC `exp` | Assertion validity khác ID Token lifetime |
| SAML `InResponseTo` | Không map vào OIDC `nonce`/`state` | Hai giao dịch có người tạo và mục đích khác |
| Group/role attributes | Client role claims (nếu được duyệt) | Allowlist theo IdP/tenant; app/API vẫn kiểm authorization |

**Giả mạo assurance:** IdP phát `AuthnContextClassRef=PasswordProtectedTransport` không tự chứng minh MFA. Broker không thể phát `amr=["pwd","otp"]` chỉ vì tên IdP có chữ “MFA”. Nếu RP yêu cầu `max_age` hoặc `prompt=login`, broker phải bảo đảm AuthnInstant/reauthentication policy và khả năng upstream tương ứng; nếu không chứng minh được, không phát claim giả.

### MFA và step-up

Khi RP yêu cầu assurance cao hơn broker session hiện có:
- Kiểm yêu cầu `acr_values` hoặc `claims` (nếu client/broker hỗ trợ) và session age.
- Broker kiểm liệu upstream SAML IdP có thể đáp ứng `ForceAuthn`/`RequestedAuthnContext` với cơ chế được hỗ trợ không.
- Nếu IdP không thể cung cấp bằng chứng tương ứng, broker có thể dùng step-up chính thức của OP hoặc **từ chối**, không tự gắn `acr=high`.
- Cần negative tests cho downgrade (password-only nhưng yêu cầu MFA), replay session cũ và false auth_time.

## 9. OIDC OP phải làm gì ngoài việc ký JWT?

Để phát ID Token đúng, broker OP cần **giao thức OIDC/OAuth đầy đủ**:

| Năng lực | Trách nhiệm |
| --- | --- |
| Discovery `/.well-known/openid-configuration` | Công bố issuer, authorization endpoint, token endpoint, jwks_uri, supported metadata |
| Authorization Endpoint | Client ID, exact redirect URI, code flow, scopes, login session, state/nonce/PKCE request |
| Token Endpoint | Authorization code một lần, TTL/client binding, redirect URI, PKCE verifier, client authentication |
| OP Signing/JWKS | Private signing key an toàn, public JWKS đúng `kid`/alg, rotation |
| Client Registration | Redirect/logout URI allowlist, client secrets/keys, allowed grants/scopes, consent |
| UserInfo (nếu dùng) | Trả claims theo access token/consent, `sub` khớp ID Token |
| OP Session | Theo dõi authenticated broker user, auth_time, reauthentication, logout, session TTL |
| Token Lifecycle | Access/Refresh Token expiry, refresh rotation/revocation, issuer/audience/scope |
| Security Events | Audit, rate limiting, CSRF/replay protection, trust configuration, key compromise handling |

Spring Security `oauth2Login()` chỉ giúp một ứng dụng **đăng nhập qua OIDC OP**; nó **không** tự tạo `/authorize`, `/token` hay `jwks_uri` cho client khác. Nếu tự triển khai OP bằng Spring Authorization Server, phải cấu hình các endpoints và nối identity layer/SAML SP validated authentication vào authorization flow. Nên ưu tiên broker product đã có kiểm toán nếu không có lý do kiến trúc bắt buộc tự xây.

### OIDC issuer và JWKS: không tin token tự dẫn đi lấy khóa

OIDC client của Portal có `issuer-uri` đã được cấu hình và được quản trị phê duyệt. RP có thể dùng OIDC Discovery để lấy `jwks_uri` từ **trusted issuer**. Nó không nên đọc `iss`/`jku` từ JWT của attacker rồi fetch arbitrary host để “thử xem chữ ký có khớp không”. Đó là rủi ro SSRF và key confusion.

**Khóa OP** khác SAML signing key của IdP. IdP rotation ảnh hưởng **broker upstream validation**, còn OP signing/JWKS rotation ảnh hưởng **RP token validation**. Đừng gộp việc quản trị hai lifecycle thành một trạng thái “federation certificate” duy nhất.

## 10. ID Token, Access Token và Refresh Token

OIDC RP dùng **ID Token** để biết user được broker xác thực; OAuth2 Resource Server/API dùng **Access Token** để quyết định request có quyền truy cập tài nguyên không. Refresh Token nếu có cho phép nhận token mới theo scope/session policy.

~~~text
Broker OP
  |
  +-- ID Token: iss=broker, aud=portal-web
  |       -> Portal OIDC RP validates for user login
  |
  +-- Access Token: aud=reports-api, scope=reports.read
  |       -> Reports API validates for data access
  |
  +-- Refresh Token (nếu được phép)
          -> Portal confidential backend giữ bí mật,
             OP kiểm rotation/revocation/session policy
~~~

**Sai:** gửi ID Token `aud=portal-web` làm Bearer Access Token vào `reports-api` vì chữ ký vẫn hợp lệ. API phải từ chối audience/purpose sai. Broker phải định nghĩa resource audience và scopes rõ, RP chỉ gửi đúng token, API enforce quyền trên user/tenant/resource.

### Resource Server Spring Boot ở API riêng

Ví dụ cấu hình **Reports API** (không phải Portal) khi token API là JWT và Spring Boot version hỗ trợ audiences:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://broker.example.org/realms/workforce
          audiences:
            - reports-api
~~~

API còn phải kiểm scopes/authorities và tenant/resource ownership. Nếu access token là opaque, dùng introspection thay JWT decoder. Không phải mọi access token của broker đều là JWT; không tự decode opaque token thành JSON.

## 11. Keycloak Identity Brokering: triển khai từng bên

Một triển khai tham khảo dùng Keycloak như broker. Tên menu, tính năng/option của Admin Console có thể khác theo phiên bản; bám phiên bản tài liệu hệ thống thực tế. Những bước sau là **các quyết định cấu hình**, không phải thao tác được thực hiện ở đây.

### 11.1. Đăng ký upstream SAML IdP

1. Quyết định realm/tenant và broker public HTTPS hostname/issuer.
2. Thêm SAML identity provider vào broker bằng metadata/source được phê duyệt; kiểm entity ID, SingleSignOnService, certificate rollover, bindings.
3. Đăng ký broker như một **SAML SP** ở Corporate IdP: broker SP entity ID, ACS và public signing/encryption certificates nếu yêu cầu.
4. Cấu hình có bắt buộc signed Response/Assertion, ký AuthnRequest, encrypt Assertion và NameID format không.
5. Thử SP-initiated login, kiểm SAML signature, issuer, audience, destination/recipient, time, SubjectConfirmation và InResponseTo/replay.
6. Thiết lập First Broker Login: user creation/linking, duplicate email, tenant membership, account disabled/locked và multi-IdP policy.
7. Tạo mapper claims với allowlist, default deny cho admin roles, account verification; không tự tin `email_verified`.
8. Review SessionIndex/LogoutRequest support, AuthnInstant/AuthnContext assurance mapping và SAML SLO.
9. Có playbook key rotation, IdP outage, user offboarding và incident account linking.

### 11.2. Đăng ký downstream OIDC client

1. Tạo OIDC client `portal-web` là confidential web client nếu backend bảo vệ client secret, hoặc public+PKCE theo kiến trúc riêng.
2. Khai báo **exact redirect URI** `https://portal.example.org/login/oauth2/code/broker` và approved post-logout redirect URIs; không bật wildcard rộng.
3. Bật Authorization Code, client authentication/PKCE policy và allowed scopes (ví dụ `openid`, `profile`).
4. Chỉ cấp claims/roles cần thiết qua mappers/client scopes; không xuất toàn bộ SAML assertion/attributes cho mọi client.
5. Kiểm broker Discovery issuer, JWKS, ID Token `aud=portal-web` và `sub` policy.
6. Kiểm OIDC session timeout, token TTL, refresh rotation/revocation và logout; xác định upstream SAML SLO có được nối vào hay không.
7. Chạy negative tests với wrong redirect, wrong client, unlinked identity, same email across IdPs và MFA/assurance mismatch.

**Điều quan trọng:** Khi client dùng Keycloak OIDC token, client nhìn thấy **Keycloak broker issuer**, không thấy SAML IdP như OP issuer. Keycloak có thể lưu upstream provider alias/identity trong session notes hoặc custom claims theo policy, nhưng đó không thay `iss`.

## 12. Spring Boot 3.5 + Java 17: Portal là OIDC Relying Party

Mẫu dưới đây cho Portal login thông qua broker **đã cấu hình**, dùng Spring Security OAuth2 Client. Nó không xử lý SAML Response; broker thực hiện phần SAML SP. Đây là ứng dụng Maven có thể biên dịch với JDK 17 và dependencies, nhưng cần broker thật và OIDC client đã đăng ký mới login được.

### Cấu trúc

~~~text
oidc-broker-client/
├── pom.xml
└── src/main/
    ├── java/demo/OidcBrokerClientApplication.java
    └── resources/application.yml
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>oidc-broker-client</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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

**Không thêm SAML SP library chỉ vì upstream là SAML.** RP chỉ giao tiếp OIDC với broker. Ngược lại, nếu viết chính broker bằng Spring, nó phải có cả upstream SAML SP + downstream OP/token issuing infrastructure; `oauth2Login` ở Portal không phát ID Token cho các client khác.

### src/main/resources/application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${BROKER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: https://broker.example.org/realms/workforce
~~~

**Ý nghĩa:**

- `spring.security.oauth2.client.provider.broker.issuer-uri` là **issuer cố định của broker OP**, không phải IdP entity ID SAML.
- `client-id=portal-web` được broker đăng ký trước; OIDC ID Token `aud` phải chứa giá trị này.
- `client-secret` đọc từ biến môi trường `BROKER_CLIENT_SECRET`/secret store, không hardcode production secret trong Git hoặc frontend.
- `scope` có `openid` để dùng OIDC; `email`/`profile` chỉ là yêu cầu, không tự bảo đảm broker phải cấp mọi claim.
- `redirect-uri` phải trùng exact client registration ở broker; localhost demo chỉ được dùng khi broker sandbox cho phép.
- `{baseUrl}` phụ thuộc scheme/host qua proxy; public HTTPS deployment cần trusted forwarded headers, tránh Host-header poisoning.
- State/nonce có nhiệm vụ riêng trong OIDC login; **PKCE khuyến nghị và cần kiểm thực tế trong request/token exchange**, đặc biệt với public client. Đối với confidential client không nên mặc định mọi version framework luôn tự bật PKCE; cấu hình và integration test theo broker policy.

### src/main/java/demo/OidcBrokerClientApplication.java

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcBrokerClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcBrokerClientApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/")
        String home() {
            return "Open /me for OIDC login through the broker";
        }

        @GetMapping("/me")
        Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
            return Map.of(
                    "issuer", user.getIdToken().getIssuer().toString(),
                    "subject", user.getSubject(),
                    "audiences", user.getIdToken().getAudience(),
                    "authenticated", true);
        }
    }
}
~~~

**Code làm gì:** `oauth2Login` kích hoạt OIDC Authorization Code login. Spring Security client thực hiện callback/code exchange/ID Token validation theo cấu hình. `OidcUser` chỉ xuất hiện sau authentication thành công. Endpoint `/me` chỉ in **broker issuer, broker-issued subject và audience**, không chạm SAMLResponse hay private keys IdP. Trong production, tránh trả external subject/claims không cần thiết, và bổ sung authorization/tenant checks ở API/service.

### Chạy

Sau khi đặt biến môi trường secret do sandbox cấp, thay broker issuer bằng hệ thống thật và cấu hình OIDC client/redirect tương ứng:

~~~bash
mvn spring-boot:run
~~~

`GET http://localhost:8080/` trả chính xác:

~~~text
Open /me for OIDC login through the broker
~~~

`GET /me` khi chưa login sẽ redirect tới broker OIDC Authorization Endpoint. Nếu broker có upstream SAML IdP và user thực hiện flow hợp lệ, response JSON có **dạng**:

~~~json
{
  "issuer": "https://broker.example.org/realms/workforce",
  "subject": "broker-issued-subject",
  "audiences": ["portal-web"],
  "authenticated": true
}
~~~

Đây là **output minh họa**, không phải stdout cố định: `subject`/`audiences` thực tế tùy token. Một broker/IdP URL ví dụ chưa được kết nối không làm login thành công. Kiểm `issuer` là broker, **không phải** SAML IdP; đây là cách xác nhận ứng dụng đang đúng vai trò RP.

### Khi triển khai PKCE

Kiểm broker OIDC client policy yêu cầu PKCE, OIDC authorization request có `code_challenge`/`code_challenge_method=S256`, token request có `code_verifier` phù hợp và replay/wrong verifier bị từ chối. Với Spring Security 6.5 có extension point `DefaultOAuth2AuthorizationRequestResolver`/PKCE customizer nếu ứng dụng cần cấu hình thêm; xác minh bằng integration tests theo phiên bản dùng, không viết lại token exchange.

## 13. Java 17 độc lập: kiểm mapping IdentityLink

Chương trình sau chạy trực tiếp bằng Java 17, minh họa broker **không tự gộp hai SAML identities có cùng NameID/email**. Hai boolean biểu diễn kết quả validation đã có từ thư viện/protocol; **không phải input tin cậy từ HTTP**. Chương trình không tạo JWT, không parse SAML, không thay OpenSAML validator.

**Tệp BrokerIdentityLinkDemo.java:**

~~~java
import java.util.Map;

public class BrokerIdentityLinkDemo {

    record ExternalIdentity(String trustedIssuer,
                            String nameIdFormat,
                            String nameIdValue) {}

    private static final Map<ExternalIdentity, String> APPROVED_LINKS =
            Map.of(
                new ExternalIdentity(
                        "https://idp-a.example.org/saml",
                        "persistent", "alex"), "broker-user-101",
                new ExternalIdentity(
                        "https://idp-b.example.org/saml",
                        "persistent", "alex"), "broker-user-202"
            );

    static String resolve(ExternalIdentity identity,
                          boolean samlValidated,
                          boolean requestCorrelated) {
        if (!samlValidated || !requestCorrelated) {
            return "DENY_UNVERIFIED";
        }
        String user = APPROVED_LINKS.get(identity);
        return user == null ? "DENY_UNLINKED" : user;
    }

    public static void main(String[] args) {
        ExternalIdentity a = new ExternalIdentity(
                "https://idp-a.example.org/saml", "persistent", "alex");
        ExternalIdentity b = new ExternalIdentity(
                "https://idp-b.example.org/saml", "persistent", "alex");
        ExternalIdentity unknown = new ExternalIdentity(
                "https://idp-c.example.org/saml", "persistent", "alex");

        System.out.println("a=" + resolve(a, true, true));
        System.out.println("b=" + resolve(b, true, true));
        System.out.println("unknown=" + resolve(unknown, true, true));
        System.out.println("badSignature=" + resolve(a, false, true));
        System.out.println("badCorrelation=" + resolve(a, true, false));
    }
}
~~~

Chạy:

~~~bash
javac BrokerIdentityLinkDemo.java
java BrokerIdentityLinkDemo
~~~

**Stdout chính xác:**

~~~text
a=broker-user-101
b=broker-user-202
unknown=DENY_UNLINKED
badSignature=DENY_UNVERIFIED
badCorrelation=DENY_UNVERIFIED
~~~

Hai IdPs phát cùng `NameID=alex` nhưng broker external key khác issuer nên dùng **hai internal IDs khác nhau**. Nếu user chưa có link, `DENY_UNLINKED` thay vì “tìm bằng email”. Nếu chữ ký/`InResponseTo` không hợp lệ, phải từ chối trước mapping. Production cần bổ sung NameID qualifiers, tenant/user status, subject longevity, link approval/assurance và OIDC pairwise subject generation.

## 14. Multi-tenant và nguồn đăng nhập được phê duyệt

Một broker phục vụ Acme/Payroll/Beta có thể kết nối nhiều upstream SAML IdPs và downstream OIDC clients. Đừng biến tenant domain hoặc query string thành IdP metadata URL tùy ý.

~~~text
(approved tenant, approved IdP alias)
            |
       configuration registry
            |
      trusted SAML IdP metadata/cert
            |
    SAML validation + IdentityLink
            |
       broker user + tenant
            |
    OIDC client registry + scopes
            |
         ID Token / Access Token
~~~

**Pre-auth:** tenant/IdP picker chỉ cho chọn alias từ allowlist đã duyệt; không lấy `?idp=https://attacker.example/metadata` để fetch. Kiểm ownership của custom domain, reverse-proxy Host/SNI, forwarded headers và egress SSRF controls.

**During auth:** SAML Response nhận tại broker ACS phải phù hợp đúng SAML registration IdP, SP entity ID, audience, recipient, time và request correlation. OIDC auth request phải có đúng client ID, redirect URI, code/state/nonce/PKCE.

**Post-auth:** identity link và tenant membership xác định người dùng được quyền ở tenant nào. Một `iss=broker` hợp lệ có thể được cùng nhiều RP tin, nhưng **không tự cấp toàn bộ tenant roles**. Khi RP gọi tài nguyên Beta bằng token/identity của Acme, API phải enforce tenant/data ownership.

## 15. Vòng đời phiên và logout qua ba tầng

Có ít nhất ba session khác nhau:

~~~text
SAML IdP session:
    IdP biết user được xác thực, có thể có SessionIndex

Broker OP session:
    Broker biết external identity đã verified, lưu liên kết
    SAML source, broker user, auth_time và policy

Portal RP session:
    Portal có browser cookie và SecurityContext sau ID Token validation
~~~

**Local logout ở Portal** chỉ xóa Portal session. **OIDC logout qua broker** có thể đóng broker OP session nếu RP-initiated logout được hỗ trợ; nhưng **không tự bảo đảm Corporate SAML IdP đã SLO**. Nếu broker kết nối upstream SAML Single Logout, cần IdP `SingleLogoutService`, signed LogoutRequest/Response, NameID/SessionIndex mapping và xử lý partial/failure. Ngược lại, upstream IdP-initiated SLO chưa chắc tự thông báo mọi RP sessions downstream.

### Khác biệt token/session TTL

- `SAML Conditions/NotOnOrAfter` kiểm assertion có thể được broker dùng **ở thời điểm authentication**; nó không bắt buộc bằng ID Token `exp`.
- `OIDC ID Token exp` giới hạn token, nhưng session HTTP Portal có lifetime riêng.
- `Access Token exp`/`scope` giới hạn gọi API; token API có thể còn hiệu lực khi browser logout.
- `Refresh Token` nếu phát có lifecycle, rotation và revocation riêng; phải bảo vệ như credential.
- `auth_time` phải phản ánh authentication đáng tin, không reset tùy tiện khi broker làm token refresh.
- Khi upstream user bị disabled, broker/Portal phải có policy session revocation/reauthentication; không chờ SAML assertion “hết hạn” rồi mặc định user đã bị chặn ở mọi nơi.

### UX tránh hứa sai

Thông báo “Đã đăng xuất khỏi Portal” là local state. “Đã gửi yêu cầu kết thúc phiên liên kết” là bước broker/IdP coordination. “Đã đăng xuất khỏi mọi thiết bị và ứng dụng” chỉ được nói khi có biện pháp phù hợp và bằng chứng thực, không từ một SAML LogoutResponse đơn lẻ.

## 16. Kiểm thử bảo mật theo từng trust boundary

| Test case | Mô phỏng trong sandbox | Kết quả đúng |
| --- | --- | --- |
| Happy path | SAML IdP A ký Response đúng; broker phát OIDC code/token cho Portal | Login Portal thành công nếu mọi policy pass |
| SAML wrong signer | XML tự ký bằng key attacker | Broker không nhận |
| SAML wrong Issuer | IdP B phát Response cho registration A | Broker từ chối |
| SAML wrong Audience | Assertion ký hợp lệ nhưng dành SP khác | Broker từ chối |
| SAML wrong Destination/Recipient | Response dành ACS khác | Broker từ chối |
| SAML `InResponseTo` mismatch | Response của AuthnRequest khác | Broker từ chối |
| SAML replay/expiry | Sử dụng lại Response/hết hạn | Broker từ chối |
| IdP-initiated unsolicited | Response không có pending request khi policy cấm | Không tự cấp OIDC token |
| External identity chưa link | NameID mới, email trùng | First broker login verify hoặc deny, không auto-link |
| Hai IdPs cùng NameID/email | IdP A/B cùng alex@example.org | Không gộp account tự động |
| User disabled/tenant denied | SAML valid nhưng internal broker account locked | Không mint token/cấp quyền |
| MFA downgrade | SAML chỉ password nhưng RP yêu cầu MFA | Không tự phát `acr=mfa` |
| OIDC redirect không đăng ký | Client gửi redirect URI của attacker | Broker reject |
| OIDC wrong client secret | /token authentication sai | Broker reject |
| OIDC PKCE mismatch | Code verifier không khớp challenge | Broker reject |
| OIDC authorization code reuse | Đổi code lần 2 | Broker reject |
| OIDC `state` mismatch | RP nhận callback khác pending request | RP reject |
| OIDC `nonce` mismatch | Broker ID Token nonce sai | RP reject |
| OIDC `iss` wrong | Token do issuer không được cấu hình phát | RP reject |
| OIDC `aud` wrong | Token aud=payroll-web đưa vào Portal | RP reject |
| OIDC invalid `kid`/`alg` | JWT ký bằng khóa/alg lạ | RP reject, không tải arbitrary JWK URL |
| OIDC expired token | `exp` đã qua | RP reject |
| UserInfo `sub` mismatch | UserInfo sub khác ID Token | RP reject |
| Wrong token purpose | Dùng ID Token aud=portal-web gọi Reports API | API reject |
| Access Token wrong scope | Reports token thiếu `reports.read` | API deny/403 |
| Access Token wrong audience | Token dành Payroll API gọi Reports API | API reject |
| Cross-tenant resource | User Acme xem Beta data | 403/deny ở API/service |
| JWKS rotation | Broker chuyển signing key trong overlap | RP refresh key theo policy |
| SAML cert rotation | IdP dùng public signing cert mới đã phê duyệt | Broker xác minh đúng |
| Broker outage | OIDC /token unavailable | Fail an toàn, retry/circuit breaker đúng |
| SLO PartialLogout | Một SP liên kết không logout được | Không khẳng định global logout |
| Upstream user offboard | Broker có refresh token/session cũ | Revoke/short TTL/reauth theo policy |

**Kỹ thuật kiểm thử đúng:** Nếu sửa SAML XML hoặc JWT payload **sau khi ký**, chữ ký hỏng. Lỗi đó chưa chứng minh Audience validator hoạt động. Để test audience, dùng IdP/broker sandbox phát **thông điệp ký hợp lệ nhưng dành client/SP khác**. Không dùng private keys production hay raw assertions của người dùng thật trong lab.

### Bốn cấp kiểm thử

1. **Pure Java unit test** cho mapping như `BrokerIdentityLinkDemo`, identity collision và fail-closed.
2. **SAML integration** Broker SP ↔ IdP sandbox: Issuer/Audience/Recipient/`InResponseTo`/signatures, Attributes và AuthnContext.
3. **OIDC integration** Portal RP ↔ Broker OP: Discovery, JWKS, Code/PKCE, state/nonce, ID Token, subject/assurance.
4. **Browser/E2E/API**: cookie SameSite, TLS/proxy, tenant resource checks, logout, refresh-token revocation, metadata/key rotation và cluster/session failover.

## 17. Lỗi phổ biến và troubleshooting

| Triệu chứng | Lớp nghi vấn | Hướng xử lý |
| --- | --- | --- |
| SAML login thất bại tại broker | IdP signing key, issuer, ACS, audience, time | Kiểm broker SP registration và metadata IdP |
| SAML pass nhưng broker không phát OIDC token | IdentityLink/tenant/first login policy, OP session | Xem broker link/consent/error, không gán theo email |
| Portal redirect sang sai IdP | Broker identity provider selection/tenant hint | Allowlisted IdP aliases, kiểm default flow |
| Portal báo invalid issuer | Config `issuer-uri` không trùng OIDC `iss` | Đối chiếu Discovery của broker |
| Portal báo invalid audience | OIDC ID Token `aud` không chứa `portal-web` | Kiểm client registration/issuer token |
| Unknown `kid` | OP JWKS rotation/cache chưa đồng bộ | Kiểm JWKS endpoint/key overlap |
| Login callback state mismatch | RP browser session/CSRF/context | Cookie, proxy, browser tabs, OAuth2 AuthorizationRequestRepository |
| Nonce mismatch | ID Token không gắn authorization request | Kiểm broker nonce issuance và RP pending state |
| `invalid_grant` | Code expired/reused, redirect hoặc PKCE mismatch | Kiểm code/token request/clock |
| Login OIDC pass nhưng API 401 | Access Token issuer/audience/signature | Đối chiếu API token validation, không dùng ID Token |
| API 403 | Scope/tenant/resource permission | Identity link, role mapping và authorization policy |
| MFA claim không đúng | `AuthnContext`→`acr/amr` mapping | Bỏ nâng assurance không có bằng chứng |
| User login bằng IdP khác bị gộp account | Auto-link email nguy hiểm | Tắt policy, incident/revoke/relink có approval |
| Logout xong lại SSO | IdP/broker session vẫn còn | Phân biệt RP logout, OP logout và SAML SLO |
| SSO lỗi chỉ một node | Session repository/key/metadata cache không đồng bộ | Shared state, NTP, consistent releases |
| Metadata URL bị chặn | Egress/TLS/cert/SSRF policy | Dùng nguồn phê duyệt, không tắt policy |

**Thứ tự điều tra:** OIDC client/redirect/state → Broker upstream IdP selection → SAML response validation → IdentityLink/tenant/assurance → Broker OP code/token issuance → RP ID Token verification → API access token/authorization. Tách các lớp giúp tránh “sửa SAML” khi lỗi thực tế là OIDC client secret, hoặc “tắt JWT audience check” khi ID Token bị phát cho sai client.

## 18. Vận hành, key rotation, audit và sự cố

### Key rotation độc lập

**IdP SAML signing rotation:** IdP công bố/chuyển public cert mới theo kênh metadata đã phê duyệt; broker bổ sung verification certificate mới với overlap và kiểm issuer/certificate. Không chấp nhận public key từ SAMLResponse lạ tự khai.

**Broker SAML SP signing/decryption rotation:** broker phối hợp public SP certificate với IdP; decryption key có thể cần giữ bản cũ để giải mã ciphertext đang bay.

**Broker OIDC signing/JWKS rotation:** broker thêm public JWK mới, ký bằng key mới có `kid` đúng, giữ public key cũ đủ để RP verify token chưa hết hạn theo policy. Nếu private OP signing key bị lộ, cần incident response, rotate nhanh, revoke sessions/refresh tokens theo phạm vi.

**OIDC client secret rotation:** Portal và broker cập nhật credentials theo policy, secret manager/managed identity; không để secret trong frontend, logs hay Git.

### Audit mà không lộ dữ liệu

Nên ghi: upstream IdP alias, broker SAML registration ID, OIDC client ID, correlation trace ID, outcome, status/error category, policy version, key version và latency. Không in raw SAMLResponse, XML Attribute chứa PII, NameID, Authorization Code, JWT, Access/Refresh Token, client secret, private keys hoặc session cookies trong logs/traces. Dùng identities giả cho sandbox.

### Incident ví dụ: sai identity link

Nếu broker vô tình link IdP B user vào account IdP A do email trùng:
1. Disable/rollback auto-link mapper, chặn login nguy hiểm và thu hồi broker/Portal sessions liên quan.
2. Xác định accounts/tenants/client tokens đã bị ảnh hưởng, revoke refresh tokens và đánh giá Access Token TTL.
3. Kiểm evidence của SAML signing/Issuer; phân biệt lỗi cryptographic verification với lỗi business identity mapping.
4. Rebuild external identity links dựa trên issuer+stable identifier có approval; không auto-link lại qua email.
5. Thêm regression tests “same email two issuers” và review audit/privileges.
6. Phối hợp với IdP, RP/API owners và security responders theo incident process.

## 19. Checklist trước go-live

- [ ] Broker SAML SP entity ID, ACS, trusted IdP metadata/signing cert đúng đối tác.
- [ ] Upstream SAML validation đầy đủ (signature, issuer, audience, recipient/destination, time, correlation/replay).
- [ ] Không dùng arbitrary IdP metadata URL hoặc signers từ input của user.
- [ ] IdentityLink không dựa duy nhất email/NameID raw; first login/disabled account/tenant policy rõ.
- [ ] Broker OP issuer ổn định, Discovery và JWKS chỉ công bố public keys, signing private keys bảo vệ.
- [ ] OIDC client có exact redirect URI, code flow, client authentication và PKCE/state/nonce policy.
- [ ] OIDC ID Token `iss=broker`, `aud=client_id`, broker-issued `sub`; claims chỉ phát theo scope/policy.
- [ ] RP verify issuer/JWKS/aud/nonce/exp, không chấp nhận arbitrary issuer/JWK URL.
- [ ] API validate **Access Token audience/scope**; không dùng ID Token như API credential.
- [ ] Mỗi client/tenant có quyền riêng, không mặc định “đã login là admin”.
- [ ] AuthnContext/`auth_time`/`acr/amr` mapping có bằng chứng; reauth/MFA downgrade test pass.
- [ ] IdP session, broker session, RP session, refresh-token revocation và SLO được mô tả trung thực.
- [ ] Key rotation, failover, audit/secret handling và security incident runbook đã được thử.
- [ ] Negative tests issuer/aud/signature/redirect/nonce/PKCE/linking/tenant pass.

## 20. Bài tập và câu hỏi tự đánh giá

**Bài 1 – xác định hai trust boundaries.** Vẽ SAML IdP → Broker SAML SP → Broker OIDC OP → Portal. Ghi ai ký và ai verify ở mỗi chặng. Nêu vì sao Portal không cần IdP SAML signing public certificate để verify ID Token broker.

**Bài 2 – so sánh audiences.** IdP SAML phát Assertion có Audience `urn:broker:saml:sp`. Broker phát ID Token có aud `portal-web`. Giải thích vì sao cả hai đúng mà không cần bằng nhau.

**Bài 3 – Java 17.** Chạy `BrokerIdentityLinkDemo.java` và đối chiếu 5 dòng stdout. Đổi IdP issuer/NameID format, dự đoán việc link nào bị từ chối. Giải thích giới hạn boolean demo so với actual signature verification.

**Bài 4 – Spring Boot.** Dùng broker sandbox có OIDC client và upstream SAML IdP, chạy `OidcBrokerClientApplication`. Kiểm `/me` hiển thị broker issuer, không phải SAML IdP issuer. Thử cấu hình sai client_id hoặc redirect URI và phân tích lỗi.

**Bài 5 – account linking.** Hai IdPs cùng phát email `alex@example.org` nhưng NameID/issuer khác. Thiết kế workflow First Broker Login không tự liên kết bằng email; nêu điều kiện cần approval.

**Bài 6 – PKCE/state/nonce.** Chỉ rõ RP tạo gì và broker kiểm gì. Thử wrong code_verifier, state hoặc nonce trong sandbox; giải thích từng bên chịu trách nhiệm reject.

**Bài 7 – assurance.** IdP phát PasswordProtectedTransport, RP yêu cầu MFA. Broker có được phát `acr=mfa` không? Trình bày step-up/reauth hoặc deny khi thiếu bằng chứng.

**Bài 8 – API.** Dùng ID Token `aud=portal-web` gọi Reports API `aud=reports-api`. Giải thích vì sao API phải reject, dù token có chữ ký broker hợp lệ.

**Bài 9 – logout.** User logout Portal nhưng broker/IdP sessions còn. Vẽ ba session và mô tả OIDC RP-initiated logout, broker OP session, upstream SAML SLO và tình huống PartialLogout.

**Bài 10 – incident.** Nếu broker đã mint token từ SAML Assertion chưa được kiểm đầy đủ, phân chia trách nhiệm IdP, broker, RP, API và nêu steps containment/revoke/rotate/regression test.

**Tiêu chí đạt:** Người học mô tả rõ chuỗi **SAML validation → controlled external identity linking → OIDC OP code/token issuance → OIDC RP ID Token validation → API authorization**, giải thích chính xác các issuer/audience/key owners và có thể chạy demo Java 17/Spring Boot với IdP/broker sandbox.

## 21. Tài liệu tham khảo chính thức

- OpenID Connect Core 1.0 – ID Token, claims, validation, auth_time, subject types: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0 – OP issuer, token endpoint, jwks_uri: https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
- Spring Security 6.5 – OAuth2/OIDC Client: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html
- Spring Security – OAuth2 Login Core/ClientRegistration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 Response validation: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
- Spring Boot 3.5 – OAuth2 Client/Resource Server: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Authorization Server – OIDC OP configuration model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Keycloak Server Administration Guide – SAML Identity Providers, Brokering, First Login/account linking: https://www.keycloak.org/docs/26.8.0/server_admin/
- OASIS SAML 2.0 Core – Issuer/Audience/Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
