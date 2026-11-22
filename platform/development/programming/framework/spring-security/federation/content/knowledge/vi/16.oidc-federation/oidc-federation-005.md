# Ánh xạ OidcUser và Saml2AuthenticatedPrincipal vào mô hình danh tính chung

> **Chủ đề:** Spring Security – federation. **Nhóm:** OIDC và môi giới. Bài học giải thích cách một ứng dụng Java/Spring Security nhận người dùng từ **OpenID Connect (OIDC)** và **SAML 2.0**, chuẩn hóa các thông tin đã xác thực về **mô hình danh tính chung**, gắn chúng với tài khoản nội bộ mà không nhầm issuer/tenant, và ánh xạ quyền một cách có kiểm soát. Có ví dụ Servlet Spring Security 6.x, 7.x và chương trình Java 17 độc lập.

## 1. Tại sao phải chuẩn hóa hai loại principal?

Một ứng dụng có thể cần hỗ trợ đồng thời:

- **OIDC login:** người dùng chọn một OpenID Provider (OP) và Spring Security xác thực bằng OIDC Authorization Code Flow; principal thường là `OidcUser`.
- **SAML 2.0 login:** người dùng được chuyển sang Identity Provider (IdP), nhận SAML Response ở Assertion Consumer Service (ACS); Spring Security xác thực và tạo `Saml2Authentication`, trong bản 6.x thường có principal `Saml2AuthenticatedPrincipal`.
- **Broker/identity federation:** một nhà môi giới danh tính đứng giữa các giao thức, ví dụ phía upstream nhận SAML và phía ứng dụng downstream lại cung cấp OIDC. Lúc này application có thể chỉ thấy `OidcUser` từ broker chứ không thấy SAML Assertion gốc.
- **Multi-tenant:** mỗi tenant chọn IdP/OP khác, hoặc cùng một IdP/OP có nhiều realm/issuer, claims và chính sách.

Tầng business không nên phải viết hai nhánh if/else theo protocol cho mọi thao tác. Những thao tác như “tìm tài khoản”, “hiển thị tên”, “kiểm quyền xem báo cáo” hay “đọc tenant” nên hoạt động trên **một identity view nội bộ**. Nhưng identity view không được làm mất những thông tin an ninh quyết định **nguồn của danh tính**.

**Kết luận ngay:** Có thể **chuẩn hóa cách sử dụng**, không được **đánh đồng bằng chứng danh tính**. Hai người cùng email từ hai nhà cung cấp khác nhau **không tự là cùng một tài khoản**. Cần giữ issuer + subject và ngữ cảnh tenant/registration, đồng thời tách **external identity**, **local account** và **authorities**.

## 2. Ba tầng kiến trúc cần phân biệt

~~~text
                  Nguồn xác thực được tin cậy
                /                            \
          OIDC Provider                    SAML IdP
          ID Token/UserInfo                Response/Assertion
                |                            |
                v                            v
          Spring oauth2Login()         Spring saml2Login()
          OAuth2AuthenticationToken    Saml2Authentication
          principal: OidcUser           6.x: Saml2AuthenticatedPrincipal
                                       7.x: assertion accessor
                \                            /
                 \                          /
                  v                        v
                   Validated identity adapter
                      (protocol-aware)
                              |
                              v
                   ExternalIdentityKey
                 tenant + issuer + subject
                 (+ SAML NameID semantics)
                              |
                              v
                   Explicit account link
                     / local user ID
                              |
                              v
                  CommonIdentity / UserContext
                 localUserId, tenant, display,
                 permissions, auth provenance
                              |
                              v
                  Business authorization
                resource-level tenant checks
~~~

Có ba sản phẩm dữ liệu khác nhau:

1. **Bằng chứng nguồn (protocol-specific):** OIDC ID Token/claims hoặc SAML Assertion/NameID/AttributeStatement. Chúng có hình dạng và security validation khác nhau.
2. **Khóa danh tính liên kết (external identity key):** định danh **đã qua xác thực** trong một miền issuer, có namespace rõ ràng; dùng để tìm mapping tới local account.
3. **Tài khoản và phiên ứng dụng (CommonIdentity):** `localUserId` do ứng dụng quản lý, tenant, trạng thái tài khoản, quyền được cấp và trường hiển thị. Đây là thứ tầng business nên dùng.

**Không nên** đưa raw `OidcUser` hay `Saml2AuthenticatedPrincipal` vào mọi service rồi tự giải thích `email`/`groups` ở từng nơi. Điều đó gây logic phân quyền khác nhau giữa controllers và khó đổi IdP/broker.

## 3. OIDC và SAML có định danh gốc khác nhau

| Trường hợp | OIDC | SAML 2.0 |
|---|---|---|
| Bằng chứng định danh | ID Token được OP phát hành và xác minh | Assertion từ IdP trong SAML Response được xác minh |
| Issuer gốc | `iss` trong ID Token | `saml:Issuer` của Assertion/IdP theo registration |
| Subject gốc | `sub` trong ID Token | `saml:NameID`, gồm giá trị và ngữ nghĩa Format/qualifiers |
| Khóa liên kết an toàn cơ bản | **Cặp `(iss, sub)`** | **Issuer IdP + NameID theo hợp đồng (Format/qualifiers) + scope RP/tenant cần thiết** |
| Định danh có thể được pairwise không? | Có: `sub` có thể khác giữa clients/sectors | Có: persistent NameID có thể scoped riêng cho một SP |
| Attribute/claim map | `Map<String,Object>` | `Map<String,List<Object>>` trong API principal/accessor |
| Email | `email` + `email_verified` (nếu có) | Email thường là một Attribute, không có một chuẩn `email_verified` phổ quát tương đương |
| Display name | `name`, `given_name`... | `displayName`, `givenName`... tùy IdP attribute contract |
| Nhóm/role | Không có claim `groups` bắt buộc ở OIDC Core | Không có Attribute tên `groups` bắt buộc trong SAML |
| Phiên IdP | `sid` nếu provider hỗ trợ, `auth_time`... | `AuthnStatement.SessionIndex` và các điều kiện SAML |
| Session local | Spring Security session/Authentication | Spring Security session/Authentication |
| Logout liên kết | OIDC RP-initiated logout/back-channel tùy hỗ trợ | SAML Single Logout (SLO) tùy hỗ trợ |

**OIDC Core §5.7:** `iss` và `sub` cùng nhau là cặp nhận diện ổn định của end-user trong phạm vi issuer; `email` và `preferred_username` **không được tin là khóa duy nhất/không thay đổi**. Pairwise subject thậm chí có thể khác giữa hai client của cùng một OP.

**SAML:** `NameID` không mặc nhiên bền vững. `transient NameID` có thể thay đổi theo phiên; `persistent NameID` mới phù hợp để xây account binding khi IdP và SP đã thỏa thuận format/namespace. `NameQualifier`, `SPNameQualifier` và những trường NameID khác có thể ảnh hưởng ngữ nghĩa; nếu framework adapter chỉ thấy giá trị `getName()`, phải dựa vào **hợp đồng và validation cấp federation** trước khi tuyên bố đó là khóa ổn định.

## 4. OidcUser trong Spring Security thực sự chứa gì?

`org.springframework.security.oauth2.core.oidc.user.OidcUser` kế thừa `OAuth2User` và các interfaces claim accessors. Trong một OIDC login thành công, nó có thể cung cấp:

| API | Nội dung | Lưu ý |
|---|---|---|
| `getIdToken()` | `OidcIdToken` chứa claims của ID Token | Không xuất raw token ra client/log |
| `getUserInfo()` | `OidcUserInfo` nếu có | Có thể `null` |
| `getClaims()` | Map claims hợp nhất từ ID Token + UserInfo nếu có | Có thể có xung đột/thiếu claim; chính sách phải rõ |
| `getSubject()` | `sub` | Chỉ ổn định trong phạm vi `iss` |
| `getIssuer()` | URL của `iss` | Dùng chuỗi issuer đã xác minh, không đoán qua email domain |
| `getEmail()` | Claim `email` nếu có | Không mặc nhiên unique |
| `getEmailVerified()` | Boolean `email_verified` nếu có | Có thể null; không đồng nghĩa user có quyền |
| `getFullName()` | Claim `name` nếu có | Display only, có thể thay đổi |
| `getPreferredUsername()` | Claim `preferred_username` nếu có | Không dùng làm primary subject key |
| `getAuthorities()` | GrantedAuthority từ OIDC client login và mapper nếu có | Không tự tương đương groups của SAML |
| `getName()` | Tên principal do implementation cấu hình | Không nên thay `(iss,sub)` trong khóa liên kết |

Một kiểu Authentication thường gặp là `OAuth2AuthenticationToken`. Lấy `getAuthorizedClientRegistrationId()` để biết **OAuth2 ClientRegistration** nào tham gia login; đó là khóa cấu hình Spring, không phải `iss` và không phải tenant ID.

### 4.1. Ví dụ ID Token claims sau validation

~~~json
{
  "iss": "https://oidc.example.org/realms/workforce",
  "sub": "account-9d7e",
  "aud": "portal-client",
  "exp": 1790000000,
  "iat": 1789996400,
  "email": "reader@example.org",
  "email_verified": true,
  "name": "Report Reader",
  "preferred_username": "reader"
}
~~~

Đây là **JSON minh họa**, không phải một JWT có chữ ký. Thời gian ví dụ không được dùng làm cơ sở kiểm hiệu lực thực. Một ID Token production còn có chữ ký/JWS và các kiểm tra từ OIDC Core. Khi ánh xạ **không tự parse JSON từ browser**; chỉ nhận `OidcUser` từ Authentication đã xác thực qua Spring Security.

### 4.2. Kiểm ID Token trước khi nhận claims

Các kiểm tra cơ bản trong OIDC Authorization Code Flow gồm:

- Chữ ký/thuật toán từ JWKS hoặc key được pin theo OP trust.
- `iss` khớp **issuer metadata của provider đã đăng ký**.
- `aud` chứa client ID tương ứng; kiểm `azp` theo quy tắc profile khi cần.
- `exp`, `iat` và các thời gian hợp lệ trong clock skew được phép.
- `nonce` được kiểm khi request có dùng nonce; OAuth2 `state`/redirect URI cần ràng buộc với phiên/browser.
- Nếu dùng UserInfo, `sub` ở UserInfo phải **khớp chính xác** `sub` trong ID Token.
- HTTPS cho discovery/JWKS/UserInfo/token endpoints, client secrets an toàn.
- Không thay trusted provider issuer/JWKS URI bằng URL tự do do user gửi (tránh SSRF/trust substitution).

OIDC login của Spring Security mặc định thực hiện các bước xác thực thích hợp theo cấu hình provider; tầng mapper **không viết lại JWT verification**. Tuy nhiên tích hợp custom decoder/user-service không được bỏ các bước trên.

## 5. Saml2AuthenticatedPrincipal trong Spring Security 6.x

Trong các ứng dụng Spring Security **6.x**, một SAML login thành công thường tạo `Saml2Authentication` với principal kiểu `Saml2AuthenticatedPrincipal`, có implementation phổ biến là `DefaultSaml2AuthenticatedPrincipal`.

Các getter cần biết:

| Getter 6.x | Ý nghĩa |
|---|---|
| `getName()` | Tên principal, mặc định thường lấy NameID của Assertion đã được xác minh |
| `getAttributes()` | `Map<String,List<Object>>` chứa các SAML attributes |
| `getAttribute("groups")` | Danh sách mọi giá trị của attribute, có thể null |
| `getFirstAttribute("mail")` | Một giá trị đầu tiên, có thể null |
| `getRelyingPartyRegistrationId()` | Khóa registration SP ↔ IdP đang dùng |
| `getSessionIndexes()` | Các session indexes liên quan SAML AuthnStatement |

Khác với OIDC map `String → Object`, SAML `getAttributes()` là `String → List<Object>` vì một `saml:Attribute` có thể chứa **nhiều AttributeValue**. Một claim `groups` có thể gồm `reader` và `finance`, trong khi email có thể một giá trị. Không ép mọi SAML value thành String hoặc dùng `getFirstAttribute` cho groups rồi bỏ các giá trị còn lại.

### 5.1. Ví dụ SAML Assertion đã được thư viện xác minh

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion_123">
  <saml:Issuer>https://saml.example.org/entity</saml:Issuer>
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
      employee-4fa1
    </saml:NameID>
  </saml:Subject>
  <saml:AttributeStatement>
    <saml:Attribute Name="mail">
      <saml:AttributeValue>reader@example.org</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="displayName">
      <saml:AttributeValue>Report Reader</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="groups">
      <saml:AttributeValue>report-readers</saml:AttributeValue>
      <saml:AttributeValue>finance</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
~~~

Đây là **fragment XML để minh họa**, thiếu đầy đủ signed Response/Assertion, Conditions, Audience, Recipient và những phần tử giao thức; **không phải SAMLResponse hợp lệ**. Khi dùng thực, Spring Security/OpenSAML phải xác minh chữ ký/tin cậy, Issuer, Destination/Recipient, NotBefore/NotOnOrAfter, SubjectConfirmation, Audience và InResponseTo/replay.

**Đặc biệt:** Việc trong fragment có `mail=reader@example.org` không bảo đảm người này sở hữu email; SAML không có `email_verified` tiêu chuẩn cho tất cả IdPs. Chỉ đưa email vào field display/contact khi hợp đồng IdP cho phép, không dùng làm khóa auto-link.

### 5.2. Phân biệt SAML AuthenticationToken và Authentication

- `Saml2AuthenticationToken` đại diện SAMLResponse mới nhận từ browser, **chưa được xác thực**; tuyệt đối không đọc NameID/role để cấp session từ token này.
- `Saml2Authentication` là Authentication sau provider xác thực thành công; chứa principal, authorities và có thể raw XML qua `getSaml2Response()`.
- Chỉ map identity ở **sau** provider validation; không tự Base64-decode raw SAMLResponse trong controller để lấy claims.
- `getSaml2Response()` có thể chứa PII và thông tin phiên; không log hoặc trả thẳng API.

## 6. Spring Security 7.x: không mặc định cast principal sang Saml2AuthenticatedPrincipal

Điểm khác biệt phiên bản quan trọng:

**Trong Spring Security 7.x**, `Saml2AuthenticatedPrincipal` và `DefaultSaml2AuthenticatedPrincipal` đã được đánh dấu **deprecated**. Framework tách chi tiết Assertion khỏi principal để hỗ trợ custom principal và Single Logout.

Đường truy cập được tài liệu khuyến nghị:

~~~text
Authentication
  └── Saml2AssertionAuthentication
        ├── getPrincipal()     = principal do ứng dụng/framework chọn
        ├── getName()          = Spring principal name (có thể tùy biến)
        ├── getRelyingPartyRegistrationId()
        └── getCredentials()
              └── Saml2ResponseAssertionAccessor
                    ├── getNameId()
                    ├── getAttributes()
                    ├── getAttribute(name)
                    ├── getFirstAttribute(name)
                    ├── getSessionIndexes()
                    └── getResponseValue() [NHẠY CẢM]
~~~

- `Saml2AssertionAuthentication` là subclass của `Saml2Authentication`.
- `getCredentials()` của subclass trên trả `Saml2ResponseAssertionAccessor`, **không phải mật khẩu**.
- `getNameId()` là NameID gốc được accessor cung cấp; `getName()` của Authentication có thể là local account name sau custom converter, **không nhất thiết trùng**.
- `getRelyingPartyRegistrationId()` nằm trên `Saml2AssertionAuthentication`.
- `getResponseValue()` là dữ liệu Response XML; **không đưa ra browser/log**.
- Nếu ứng dụng tự custom `ResponseAuthenticationConverter` để trả legacy `Saml2Authentication`, code chỉ nhận `Saml2AssertionAuthentication` cần policy rõ: từ chối, hoặc dùng adapter dành riêng cho 6.x.

**Điều không thay đổi:** Spring Security vẫn phải xác minh SAML signature/conditions trước khi trả Authentication. Đừng biến vấn đề API migration thành lý do bypass validation hoặc tự parse Assertion từ request.

### 6.1. So sánh API 6.x và 7.x

| Mục đích | SAML 6.x phổ biến | SAML 7.x mặc định |
|---|---|---|
| Authentication | `Saml2Authentication` | `Saml2AssertionAuthentication` |
| Đọc NameID | `Saml2AuthenticatedPrincipal.getName()` | `Saml2ResponseAssertionAccessor.getNameId()` |
| Đọc attributes | `principal.getAttributes()` | `auth.getCredentials().getAttributes()` |
| Lấy first attribute | `principal.getFirstAttribute(name)` | `accessor.getFirstAttribute(name)` |
| Registration ID | `principal.getRelyingPartyRegistrationId()` | `auth.getRelyingPartyRegistrationId()` |
| SessionIndexes | `principal.getSessionIndexes()` | `accessor.getSessionIndexes()` |
| Hỗ trợ custom principal | Cần chú ý session/SLO dependency | Assertion accessor tách riêng, thuận tiện hơn |
| Đọc IdP Issuer | Chọn từ trusted RelyingPartyRegistration | Chọn từ trusted RelyingPartyRegistration |
| OIDC user | `OidcUser` | `OidcUser` (vẫn cùng họ API) |

**Không khẳng định** `OidcUser` và `Saml2AuthenticatedPrincipal` implement cùng một interface có phương thức lấy issuer và attributes giống nhau. Có thể dùng `AuthenticatedPrincipal.getName()` chung nhưng **không đủ** làm identity key an toàn.

## 7. Định nghĩa mô hình danh tính chung: điều gì bắt buộc phải giữ?

Một mô hình hữu ích có thể tách thành:

### 7.1. ExternalIdentityKey – nguồn danh tính

| Field | Ý nghĩa | Bắt buộc? |
|---|---|---|
| `protocol` | OIDC hay SAML | Có |
| `issuer` | Issuer đã được xác minh của OP/IdP | Có |
| `subject` | OIDC `sub` hoặc SAML NameID theo contract | Có |
| `tenantId` | Tenant được ứng dụng xác định từ registration/trust context | Có nếu hệ thống đa tenant |
| `nameIdFormat` | Format của SAML NameID (không áp dụng cho OIDC) | Có khi ảnh hưởng identity semantics |
| `nameQualifier/spNameQualifier` | Các qualifiers định danh SAML nếu IdP dùng | Theo contract |
| `registrationId` | Khóa cấu hình Spring, phục vụ audit/routing | Nên giữ nhưng không thay issuer |
| `sourceClientId` | OIDC ClientRegistration/client ID nếu cần quản trị pairwise sub | Theo contract |

Với OIDC, **cặp `(iss,sub)`** là khóa theo tiêu chuẩn để nhận diện end-user; thêm tenantId và registrationId như **phạm vi ứng dụng** để tránh cross-tenant linking ngoài ý muốn, không vì OIDC bắt buộc phải thêm vào subject key.

Với SAML, NameID có định dạng/qualifiers khác nhau, vì thế chỉ `(issuer,getName())` có thể **chưa đủ** nếu đổi SP, NameID Format hoặc NameQualifier. Nên định nghĩa khóa bền vững theo **một hợp đồng NameID cụ thể**, và **từ chối tự động liên kết** nếu format là transient hay chưa có bảo đảm ổn định.

### 7.2. CommonIdentity – danh tính ứng dụng sau account linking

Có thể thiết kế model:

~~~text
CommonIdentity
  localUserId       : UUID/String (được ứng dụng phát)
  tenantId          : String (phạm vi dữ liệu)
  displayName       : String (cho UI; không unique)
  primaryEmail      : String? (thông tin liên lạc)
  emailProof        : VERIFIED_OIDC | CONTRACTUAL_SAML | UNVERIFIED | NONE
  accountStatus     : ACTIVE | LOCKED | DISABLED
  loginSource       : OIDC | SAML
  loginRegistration : String
  authorities       : Set<String> (từ policy nội bộ)
  authContext       : metadata an toàn, không chứa raw token
~~~

Đây là **mô hình domain đề xuất**, không phải class Spring Security cung cấp sẵn. `localUserId` chỉ xuất hiện **sau khi** `ExternalIdentityKey` được đối chiếu với bảng liên kết/tài khoản nội bộ. Tầng business dùng `localUserId + tenantId` làm danh tính chứ không tin email/NameID như ID toàn cục.

### 7.3. AccountLink – bảng liên kết nhiều giao thức

~~~text
ExternalIdentityLink
  tenantId
  providerType     [OIDC / SAML]
  issuer
  subject
  nameIdFormat
  qualifiers
  registrationId
  localUserId
  verifiedAt
  provenance
  linkMethod       [ADMIN_APPROVED / REAUTHENTICATED_USER]
  enabled
~~~

**Ràng buộc database:** Unique key phải gồm namespace identity cần thiết. Bảng link không nên có unique trên `email`, vì email có thể trùng, thay đổi hoặc tái sử dụng. Tài khoản nội bộ có thể có **hai bản ghi liên kết**: một OIDC identity và một SAML identity chỉ khi đã qua xác minh/phê duyệt.

### 7.4. Hai người cùng email có phải cùng một user?

Không mặc định. Ví dụ:

- OIDC `iss=https://oidc-a.example.org`, `sub=100`, `email=reader@example.org`.
- SAML `Issuer=https://saml-b.example.org`, `NameID=other-100`, `mail=reader@example.org`.

Hai identity khác nhau có thể có cùng email. Một bên có thể do attacker kiểm soát email ở thời điểm đăng ký, một bên là tài khoản doanh nghiệp khác. **Tự động merge** có thể tạo **account takeover**. Email chỉ là tín hiệu cho quy trình **account linking có chứng minh quyền sở hữu và/hoặc phê duyệt**, không phải unique key.

## 8. Quy trình chuẩn hóa từng nguồn (không bỏ validation)

### 8.1. OIDC pipeline

~~~text
Browser -> OAuth2 Authorization Code (+ state/PKCE/nonce theo profile)
        -> OP/Token endpoint
        -> Spring Security OAuth2/OIDC authentication
        -> ID Token signature/iss/aud/exp/nonce validation
        -> UserInfo sub == ID Token sub (nếu dùng)
        -> OAuth2AuthenticationToken + OidcUser
        -> OIDC IdentityAdapter
        -> ExternalIdentityKey(protocol=OIDC, issuer=iss, subject=sub)
        -> AccountLink lookup / secure provisioning
        -> CommonIdentity
~~~

**Không đưa:** raw ID Token, refresh token, access token vào CommonIdentity DTO hoặc log. Chúng có lifecycle, audience và phạm vi sử dụng riêng.

### 8.2. SAML pipeline

~~~text
Browser -> SAML SSO / AuthnRequest / IdP
        -> HTTP POST SAMLResponse at ACS
        -> Spring Security OpenSAML provider
        -> Verify signature + issuer/trust + audience/recipient
           + conditions/time + InResponseTo/replay
        -> Saml2Authentication (6.x) / Saml2AssertionAuthentication (7.x)
        -> SAML IdentityAdapter
        -> ExternalIdentityKey(protocol=SAML,
           issuer=configured IdP issuer, subject=NameID)
        -> AccountLink lookup / secure provisioning
        -> CommonIdentity
~~~

SAML attribute `groups`/`role` là dữ liệu được **bên IdP ký** và qua validation, nhưng vẫn cần **mapping policy**. Không lấy giá trị `ROLE_ADMIN` từ XML do browser gửi trước khi verify; cũng không tin bất kỳ IdP nào có authority cấp quyền nội bộ tùy ý.

### 8.3. Không chuẩn hóa bằng cách đọc thẳng HTTP body

**Anti-pattern:**

~~~java
// KHÔNG AN TOÀN: tên/role từ browser input chưa qua IdP trust.
String email = request.getParameter("email");
String issuer = request.getParameter("issuer");
// Không tạo CommonIdentity hay GrantedAuthority từ các giá trị này.
~~~

Một anti-pattern khác là tự Base64-decode `SAMLResponse`, dùng XPath tìm `NameID` và groups, rồi tạo local session mà không qua OpenSAML. Tương tự, tự decode payload JWT bằng Base64 mà không verify signature/issuer/audience/nonce rồi gọi đó là OIDC login.

**Chỉ adapter dữ liệu từ Authentication thành công**, có type đúng và đã qua framework validation. Nếu ứng dụng có custom converters/provider, cần integration test chứng minh vẫn giữ đủ validation.

## 9. Java 17 độc lập: định danh khác giao thức và account linking minh bạch

Đây là chương trình **Java 17+ chạy độc lập**, minh họa một local account có thể liên kết **hai danh tính bên ngoài khác nhau** sau khi bên sở hữu ứng dụng phê duyệt. Nó **không** kiểm OIDC/SAML cryptography; các external keys giả định đã được hệ thống IdP/OP xác thực.

Tệp `IdentityLinkDemo.java`:

~~~java
import java.util.Map;
import java.util.Objects;

public class IdentityLinkDemo {

    enum Protocol { OIDC, SAML }

    record ExternalKey(
            Protocol protocol,
            String tenant,
            String issuer,
            String subject,
            String subjectFormat) {

        ExternalKey {
            Objects.requireNonNull(protocol);
            require(tenant);
            require(issuer);
            require(subject);
            Objects.requireNonNull(subjectFormat);
        }

        static void require(String value) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("missing identity field");
            }
        }
    }

    public static void main(String[] args) {
        ExternalKey oidc = new ExternalKey(
                Protocol.OIDC, "team-a",
                "https://oidc.example.org", "sub-123", "");

        ExternalKey saml = new ExternalKey(
                Protocol.SAML, "team-a",
                "https://saml.example.org/entity", "employee-77",
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent");

        ExternalKey otherIssuer = new ExternalKey(
                Protocol.OIDC, "team-a",
                "https://other.example.org", "sub-123", "");

        Map<ExternalKey, String> approvedLinks = Map.of(
                oidc, "local-user-001",
                saml, "local-user-001");

        System.out.println("OIDC local=" + approvedLinks.get(oidc));
        System.out.println("SAML local=" + approvedLinks.get(saml));
        System.out.println("Other issuer=" + approvedLinks.get(otherIssuer));
        System.out.println("Keys equal=" + oidc.equals(saml));
    }
}
~~~

Chạy:

~~~bash
javac IdentityLinkDemo.java
java IdentityLinkDemo
~~~

Stdout chính xác:

~~~text
OIDC local=local-user-001
SAML local=local-user-001
Other issuer=null
Keys equal=false
~~~

**Giải thích:**
1. Hai keys khác nhau **không tự merge**, nhưng bảng `approvedLinks` chủ động ánh xạ cả hai về cùng local account sau quy trình được phê duyệt.
2. Cùng subject text `sub-123` nhưng **issuer khác** không khớp map.
3. OIDC và SAML có khác protocol/issuer/subject semantics, nên `oidc.equals(saml)` là false.
4. Email không nằm trong unique key. Đó là quyết định có chủ đích.
5. Java `record` cung cấp equality/hashCode theo field; trong production phải lưu dữ liệu có integrity/uniqueness constraints ở database và ngăn cập nhật link trái phép.

**Giới hạn an ninh:** Chương trình không xác minh ID Token/SAML Assertion, không kiểm tenant ownership, NameID qualifiers, session, role hoặc bằng chứng user đã phê duyệt link. Nó là minh họa **sau authentication** chứ không phải một bộ đăng nhập.

## 10. Java Spring Security 7.x: adapter OIDC và SAML thành snapshot thống nhất

Mẫu này sử dụng **Spring Security 7.x Servlet** để tách dữ liệu từ `OAuth2AuthenticationToken/OidcUser` và `Saml2AssertionAuthentication/Saml2ResponseAssertionAccessor`. Nó tạo một **external snapshot đã phân loại**, không tự tìm hay cấp local account.

Tệp `src/main/java/com/example/federation/ExternalIdentityAdapter.java`:

~~~java
package com.example.federation;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;

public final class ExternalIdentityAdapter {

    private ExternalIdentityAdapter() {
    }

    public record ProviderPolicy(
            String protocol, String tenantId, String expectedIssuer) {
    }

    public record Snapshot(
            String protocol,
            String tenantId,
            String registrationId,
            String issuer,
            String subject,
            String displayName,
            String emailCandidate,
            boolean emailVerifiedByProtocol) {
    }

    // Demo policy: phải được đồng bộ với ClientRegistration và
    // RelyingPartyRegistration đã được admin phê duyệt.
    private static final Map<String, ProviderPolicy> POLICIES = Map.of(
            "work-oidc", new ProviderPolicy(
                    "OIDC", "team-a",
                    "https://oidc.example.org/realms/workforce"),
            "work-saml", new ProviderPolicy(
                    "SAML", "team-a",
                    "https://saml.example.org/entity"));

    public static Snapshot extract(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new IllegalArgumentException("authentication required");
        }

        if (authentication instanceof OAuth2AuthenticationToken oauth
                && oauth.getPrincipal() instanceof OidcUser oidc) {
            String registrationId = oauth.getAuthorizedClientRegistrationId();
            ProviderPolicy policy = policy(registrationId, "OIDC");

            String issuer = Objects.requireNonNull(
                    oidc.getIssuer(), "OIDC issuer required").toString();
            if (!policy.expectedIssuer().equals(issuer)) {
                throw new IllegalArgumentException("unexpected OIDC issuer");
            }

            String subject = require(oidc.getSubject(), "OIDC sub");
            return new Snapshot(
                    "OIDC", policy.tenantId(), registrationId,
                    issuer, subject, oidc.getFullName(),
                    oidc.getEmail(),
                    Boolean.TRUE.equals(oidc.getEmailVerified()));
        }

        if (authentication instanceof Saml2AssertionAuthentication saml) {
            String registrationId = saml.getRelyingPartyRegistrationId();
            ProviderPolicy policy = policy(registrationId, "SAML");

            // Spring SAML provider đã xác thực issuer đối với
            // đúng RelyingPartyRegistration. Tên issuer lấy từ
            // SERVER POLICY, không đọc một query parameter.
            Saml2ResponseAssertionAccessor accessor = saml.getCredentials();
            String subject = require(accessor.getNameId(), "SAML NameID");
            Map<String, List<Object>> attrs = accessor.getAttributes();

            return new Snapshot(
                    "SAML", policy.tenantId(), registrationId,
                    policy.expectedIssuer(), subject,
                    firstString(attrs, "displayName"),
                    firstString(attrs, "mail"),
                    false);
        }

        throw new IllegalArgumentException("unsupported auth mechanism");
    }

    private static ProviderPolicy policy(
            String registrationId, String expectedProtocol) {
        ProviderPolicy result = POLICIES.get(registrationId);
        if (result == null || !expectedProtocol.equals(result.protocol())) {
            throw new IllegalArgumentException("unknown federation registration");
        }
        return result;
    }

    private static String require(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("missing " + field);
        }
        return value;
    }

    private static String firstString(
            Map<String, List<Object>> values, String name) {
        List<Object> items = values.get(name);
        if (items == null || items.size() != 1) {
            return null;
        }
        Object first = items.get(0);
        return first instanceof String str && !str.isBlank() ? str : null;
    }
}
~~~

### 10.1. Vì sao code viết như vậy?

1. **Chỉ nhận Authentication đã xác thực**, kiểm type trước khi cast. Với ứng dụng có anonymous/form-login/other auth, adapter **từ chối** thay vì tự map mơ hồ.
2. **OIDC:** lấy `getIssuer()` và `getSubject()` từ `OidcUser`; kiểm issuer trùng policy đăng ký để phòng lỗi cấu hình. `getAuthorizedClientRegistrationId()` chỉ là key tới client config, không thay `iss`.
3. **SAML 7.x:** lấy NameID từ `Saml2AssertionAuthentication.getCredentials().getNameId()`. IdP issuer được lấy từ **mapping server-side đã khớp với registration đã được provider xác thực**, không đọc chuỗi từ form/browser.
4. **Các attributes:** `getAttributes()` map list, vì vậy `firstString` chỉ chấp nhận đúng một String. Với group arrays, cần helper khác duyệt list.
5. **Email:** OIDC có cờ `email_verified`; SAML demo đặt `emailVerifiedByProtocol=false` do không có cờ chuẩn tương đương. Muốn nâng mức proof cho SAML email phải có **IdP contract** ngoài giao thức, không tự xem nó verified.
6. **Không cấp quyền:** Snapshot là dữ liệu nguồn đã được phân loại. Nó **không phải local account** và không tự tạo `GrantedAuthority`.
7. **Không đưa raw tokens:** Code không lấy `getIdToken().getTokenValue()` hay `getResponseValue()`. Đó là bảo vệ privacy và ngăn token leakage.
8. **Cẩn trọng về IdP issuer:** Spring SAML validator được giả định đã giữ nguyên; nếu custom provider bỏ issuer/signature checks thì mẫu không an toàn. Khi chạy production, policy catalog nên được sinh/đối chiếu từ một **federation registry authoritative** cùng với registration repository thay vì hai file cấu hình dễ trôi lệch.
9. **NameID Format:** API accessor được dùng ở đây không cung cấp đầy đủ format/qualifiers trong snapshot. Code này **chưa đủ để tự động account-linking bền vững** nếu không có hợp đồng NameID persistent được kiểm ở IdP/SP.
10. **Spring dependencies:** Tệp Java cần Spring Security 7.x, Servlet app và dependency SAML2 SP/OAuth2 Client. Nó không chạy với `javac` đơn độc.

### 10.2. Từ snapshot đến local account là bước riêng

Một service business có thể làm:

~~~text
Snapshot (validated, protocol-aware)
   |
   | Build ExternalIdentityKey theo federation policy
   v
AccountLinkRepository.findExact(key)
   |
   +-- link đã duyệt -> load localUserId -> kiểm account ACTIVE
   |
   +-- chưa có link -> deny hoặc đưa vào provisioning/approval
   |
   +-- ambiguous/disabled -> deny
   |
   v
CommonIdentity(localUserId, tenantId, rolesFromApplication)
~~~

**Lưu ý:** Ví dụ Spring 7 ở trên không tự ghi database, không khẳng định email verified đồng nghĩa link allowed. Account-linking nên là một hành động **độc lập, được phê duyệt/được người dùng chứng minh quyền sở hữu cả hai identities**, có audit và khả năng unlink an toàn.

## 11. Nếu dự án vẫn dùng Spring Security 6.x

Ở 6.x, phần OIDC của adapter có thể giữ cách xử lý `OAuth2AuthenticationToken/OidcUser` tương tự, nhưng SAML cần nhánh dành cho `Saml2AuthenticatedPrincipal`. Ví dụ **method fragment** (đưa vào một class có imports tương ứng):

~~~java
if (authentication instanceof Saml2Authentication saml
        && saml.getPrincipal() instanceof Saml2AuthenticatedPrincipal p) {
    String registrationId = p.getRelyingPartyRegistrationId();
    String nameId = p.getName();
    List<?> groups = p.getAttribute("groups");
    Object mail = p.getFirstAttribute("mail");

    // Chỉ dùng registrationId sau khi Authentication đã qua
    // SAML provider; tra IdP issuer từ trusted registration.
    // Không liên kết local account chỉ bằng mail.
}
~~~

Đối tượng `Saml2AuthenticatedPrincipal` có thể có nhiều giá trị Attribute, và principal có thể là implementation custom; `instanceof` giúp tránh `ClassCastException`. Đây là **fragment minh họa**, không phải class compile độc lập và không được dùng nguyên cho Spring Security 7.x default flow.

### 11.1. Đường nâng cấp 6 → 7

- Tìm mọi `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` và cast trực tiếp.
- Kiểm loại Authentication mặc định trong integration test sau upgrade.
- Với Spring 7, ưu tiên `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor`.
- Kiểm các custom ResponseAuthenticationConverter có trả `Saml2Authentication` legacy không.
- Đảm bảo SAML Single Logout vẫn có NameID/SessionIndex khi custom principal không implement legacy SAML interface.
- Không thay bằng parser XML tự viết để lấy fields bị chuyển vị trí.
- Giữ unit/integration tests cho adapter, issuer/tenant identity key, authorities và logout.

**Đặc biệt:** Interface `Saml2AuthenticatedPrincipal` là **deprecated ở 7.x**, chưa đồng nghĩa class ngay lập tức không tồn tại; đây là tín hiệu nên chuyển API. `Saml2Authentication` vẫn là class liên quan, với `Saml2AssertionAuthentication` là một subclass trong 7.x.

## 12. Cấu hình Spring Security nhận cả OIDC và SAML

Ứng dụng **Servlet** có thể bật hai entrypoints. Ví dụ class Java đầy đủ mức ứng dụng:

Tệp `src/main/java/com/example/federation/FederationApplication.java`:

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FederationApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String index() {
        return "Federation demo";
    }

    @GetMapping("/private")
    String protectedPage() {
        return "Authenticated";
    }
}
~~~

Đây là class Spring Boot có imports đầy đủ, nhưng **không thể chạy bằng `javac` thuần**. Cần Spring Boot Web/MVC, Security, OAuth2 Client và SAML2 Service Provider, cùng OP/IdP thực đã cấu hình. `oauth2Login()` và `saml2Login()` là **hai cơ chế login**, không tự bật account linking hoặc cùng kiểu Authentication.

### 12.1. Maven dependencies

Trong phần `<dependencies>` của pom.xml Spring Boot có BOM hoặc parent:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Tệp Maven này chỉ là **dependencies fragment**, không phải pom.xml độc lập. Spring Security SAML2 có thể phụ thuộc kho OpenSAML đặc thù theo version/BOM. Không copy Maven/Java của Spring Security 7 vào một project còn 6.x khi chưa kiểm tính tương thích.

### 12.2. Hai registration có mục đích riêng

Trong Spring Boot, OIDC client dùng nhánh `spring.security.oauth2.client.registration` còn SAML RP dùng `spring.security.saml2.relyingparty.registration`.

Ví dụ minh họa cấu hình **không chứa secret**, secrets phải được cung cấp qua quản trị môi trường/secret store trước khi chạy:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          work-oidc:
            provider: workforce-op
            client-id: portal-client
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          workforce-op:
            issuer-uri: "https://oidc.example.org/realms/workforce"
    saml2:
      relyingparty:
        registration:
          work-saml:
            entity-id: "https://portal.example.org/saml/sp"
            acs:
              location: "https://portal.example.org/login/saml2/sso/work-saml"
            assertingparty:
              metadata-uri: "https://saml.example.org/metadata"
~~~

Với OIDC confidential client thực tế, cấu hình `client-secret` phải được cấp từ secret manager/environment và chính sách client authentication phù hợp; YAML trên **chưa đủ** để kết nối confidential provider, chỉ thể hiện cấu trúc. Với SAML, IdP phải đăng ký SP entityID/ACS và signing certificates; metadata URL phải đáng tin. Đây không phải các endpoint mẫu có thể chạy ngay từ internet.

**Hai loại registration khác nhau:**
- OIDC `work-oidc` thuộc `ClientRegistrationRepository`, issuer OP kiểm theo ID Token.
- SAML `work-saml` thuộc `RelyingPartyRegistrationRepository`, issuer IdP kiểm theo SAML Response/Assertion.
- Không cố dùng chung cùng `registrationId` làm issuer hay localUserId.
- Nếu có nhiều tenants, client/RP registration ID còn phải gắn vào tenant context đã được xác minh.

### 12.3. Mở URL đăng nhập có chủ đích

Thông thường:
- OIDC: `/oauth2/authorization/{registrationId}`.
- SAML: `/saml2/authenticate/{registrationId}`.

Ứng dụng có thể tạo login picker xác định tenant/allowed providers trước khi redirect. Không cho người dùng thay query parameter để ép app chọn IdP/OP không thuộc tenant; khi callback, giữ state/request correlation và kiểm issuer/tenant scope lại.

## 13. Mô hình broker: khi phía trên là SAML, phía dưới là OIDC

Một **identity broker** có thể đóng hai vai trò cùng lúc:

~~~text
Upstream enterprise SAML IdP
      |
      | SAML Response / Assertion
      v
  Identity broker
      | - Validate SAML signature/conditions/trust
      | - Match upstream NameID to broker identity
      | - Map attributes by approved rules
      | - Create broker SSO session
      | - Issue NEW OIDC ID Token as broker issuer
      v
Downstream Spring application
      | oauth2Login()
      v
  OidcUser
    iss = broker issuer
    sub = broker subject
~~~

**Một bước chuyển giao thức không có nghĩa** ứng dụng nhận được một `Saml2AuthenticatedPrincipal`. Nếu broker phía downstream phát OIDC, Spring app **chỉ thấy OIDC Authentication/OidcUser**, trừ khi broker có custom claims về upstream identity.

### 13.1. Danh tính ở hai tầng khác nhau

| Tầng | Nguồn/issuer | Subject |
|---|---|---|
| SAML upstream | Enterprise IdP issuer | NameID theo hợp đồng SAML |
| Broker account | Broker internal identity store | Broker local subject |
| OIDC downstream | **Broker OIDC issuer** | Broker `sub`, có thể pairwise theo client |

Ứng dụng downstream nên xác thực **`(broker iss, broker sub)`** là danh tính trực tiếp của nó. Nếu muốn biết nguồn upstream, broker có thể phát claim provenance theo hợp đồng, nhưng không được tự coi `upstream_issuer`/`upstream_nameid` trong claim là cùng loại bằng chứng với SAML Assertion gốc khi app **không trực tiếp xác minh SAML**.

### 13.2. Broker không phải token converter “đổi định dạng”

Một anti-pattern là:
- Decode SAML Response.
- Chép `NameID` sang OIDC `sub`.
- Chép `email`, `groups` và tự ký JWT bất kỳ.
- Yêu cầu downstream tin mà không có issuer registry/trust/claims policy.

Một broker đúng nghĩa phải:
1. Đóng vai trò SP đối với upstream SAML; kiểm signed Response/Assertion và SAML conditions.
2. Liên kết upstream subject với broker account qua key ổn định/approved linking.
3. Áp policy mapping claims/roles (không chuyển nguyên mọi group thành quyền downstream).
4. Đóng vai trò OIDC Provider với issuer/JWKS/audience/ID Token riêng và các kiểm tra OIDC chuẩn.
5. Quản lý session và logout ở cả hai phía, với giới hạn propagation được tài liệu hóa.
6. Có audit và quyền unlink/account lifecycle rõ ràng.

**Tách hai nguồn sự thật:** Enterprise IdP xác nhận upstream subject; broker xác nhận cho downstream app **broker subject**. Downstream app không thể suy ra upstream NameID bằng phép đổi chuỗi trừ khi broker có contract và có cơ chế xác thực provenance.

## 14. Claim mapping: giữ ý nghĩa chứ không chỉ giữ tên

### 14.1. Bảng mapping gợi ý

| Common field | OIDC source | SAML source | Quy tắc |
|---|---|---|---|
| `protocol` | `OIDC` | `SAML` | Giữ provenance rõ |
| `issuer` | ID Token `iss` | Trusted IdP issuer trong RP registration | Không lấy từ email/URL client gửi |
| `subject` | ID Token `sub` | Validated NameID | Không coi là global ID |
| `registrationId` | `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` | SAML RP registration ID | Dùng audit/routing |
| `tenantId` | Lookup từ trusted OIDC registration | Lookup từ trusted SAML registration | Không tin `tenant` tự khai trong claim nếu chưa có policy |
| `displayName` | `name` hoặc nickname được phép | `displayName`/`givenName` theo contract | Chỉ UI; không unique |
| `emailCandidate` | `email` | `mail`/URI claim theo IdP contract | Có thể thiếu, thay đổi |
| `emailProof` | `email_verified=true` nếu OP đủ trust | Contract riêng, không có tiêu chuẩn chung | Không dùng email làm unique key |
| `groups` | Provider-specific claim | Multi-value SAML attribute | Validate type + issuer/tenant mapping |
| `authorities` | Spring/OIDC mapper và app policy | Spring/SAML converter và app policy | Kết quả local policy |
| `authTime` | `auth_time` nếu có | `AuthnInstant` nếu có | Khác thời điểm tạo session |
| `sessionHandle` | `sid` nếu có | SessionIndex theo AuthnStatement | Phục vụ logout, không dùng làm user ID |
| `localUserId` | Không có từ OP mặc định | Không có từ IdP mặc định | Do internal account linking cấp |

### 14.2. Kiểu dữ liệu cũng khác

OIDC:
- `getClaims()` là `Map<String,Object>`.
- Một `groups` provider-specific có thể là `List<String>`, `String`, hoặc cấu trúc JSON phức tạp.
- `getEmailVerified()` là Boolean/null.
- `getUserInfo()` có thể vắng mặt.

SAML:
- `getAttributes()` là `Map<String,List<Object>>`.
- Có thể nhiều AttributeValue, không phải chỉ một `String`.
- Tên attribute có thể là URI claim như `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress` thay vì `mail`.
- NameID Format/qualifiers quyết định identity semantics ngoài text.
- `SessionIndexes` là danh sách, không phải local HttpSession.

**Sai lầm thường gặp:** serialize SAML map thành một JSON object rồi lấy giá trị đầu ở mọi attribute; nếu groups có hai giá trị sẽ mất role, còn nếu email có hai giá trị sẽ chọn một giá trị tùy tiện. Khi field dự kiến single-value, **reject ambiguous** theo contract; khi field multi-value, đọc tất cả và validate type.

### 14.3. Bảng minh họa trước – sau

Trước chuẩn hóa:

~~~text
OIDC:
  iss=https://oidc.example.org
  sub=user-A1
  email=reader@example.org
  email_verified=true
  roles=["finance-readers"]

SAML:
  Issuer=https://saml.example.org/entity
  NameID=persistent-user-9
  mail=["reader@example.org"]
  groups=["finance-readers", "operations"]
~~~

Sau adapter và approved account linking:

~~~text
CommonIdentity:
  localUserId=local-user-001
  tenantId=team-a
  displayName=Report Reader
  authorities=["ROLE_REPORT_VIEW"]
  linked identities:
    - protocol=OIDC, issuer=https://oidc.example.org, subject=user-A1
    - protocol=SAML, issuer=https://saml.example.org/entity,
      subject=persistent-user-9, nameIdFormat=persistent
~~~

Đây là **ví dụ kết quả nghiệp vụ**, không chứng minh hai nguồn ở trên phải merge vì cùng email. Dòng `local-user-001` chỉ xuất hiện sau một **linking workflow đã được phê duyệt**.

## 15. Ánh xạ groups/roles sang GrantedAuthority

Một ứng dụng có thể dùng `@PreAuthorize`, `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_REPORT_VIEW")`. Những biểu thức đó kiểm **`GrantedAuthority` của Spring Security**, **không tự đọc** `OidcUser.getClaims().get("groups")` hay SAML `AttributeStatement`.

### 15.1. Mô hình mapping đúng

~~~text
Trusted IdP/OP + validated claim/group
                 |
                 v
    Tenant/provider-specific allowlist
                 |
                 v
       Internal business entitlement
                 |
                 v
       GrantedAuthority instances
                 |
                 v
      Controller/Service authorization
~~~

Ví dụ policy:

| Protocol | Issuer scope | Source claim/group | Authority cấp |
|---|---|---|---|
| OIDC | Corporate OP | `report-readers` | `ROLE_REPORT_VIEW` |
| SAML | Corporate IdP | `report-readers` | `ROLE_REPORT_VIEW` |
| OIDC | External partner OP | `report-readers` | Không cấp nếu tenant không cho |
| SAML | Bất kỳ IdP lạ | `ROLE_ADMIN` | **Không cấp** |
| Bất kỳ | User account disabled | Bất kỳ claim | **Không cấp** |

Không copy toàn bộ SAML group names sang authorities và cũng không prefix mọi OIDC `roles` bằng `ROLE_`. Phải có allowlist theo issuer, tenant và business policy. Một IdP có thể xác thực danh tính nhưng **không có quyền định đoạt toàn bộ quyền nghiệp vụ**.

### 15.2. Tách authentication và authorization

- **Authentication:** chứng minh user đến từ OP/IdP nào, qua điều kiện gì.
- **Identity mapping:** chọn external key, tìm local account, chống trùng user.
- **Authorization:** kiểm tài khoản active, membership tenant, roles, resource ownership và contextual policy.

Với login thành công nhưng local account chưa được phê duyệt, ứng dụng có thể **từ chối cấp tài nguyên** hoặc hướng tới workflow onboarding, chứ không phải tự cấp `ROLE_USER` kèm quyền của tenant. Trong multi-tenant, request chứa `/tenants/beta/reports` vẫn cần so tenant từ authenticated CommonIdentity và quyền với resource beta.

### 15.3. Spring Security extension points

**OIDC:** tài liệu Spring Security hỗ trợ `GrantedAuthoritiesMapper` và delegation-based `OidcUserService`. Dùng `OidcUserAuthority`, claims từ ID Token/UserInfo và context `OidcUserRequest` để ánh xạ sau xác thực. Nếu cần registrationId, tenant hoặc API bổ sung, delegation-based `OidcUserService` thường phù hợp hơn một mapper chỉ nhìn authorities.

**SAML:** có thể tùy biến `ResponseAuthenticationConverter` của OpenSAML provider sau khi các Response/Assertion đã qua xác minh, bổ sung authorities vào Authentication. Với Spring Security 7, duy trì `Saml2AssertionAuthentication` cùng `Saml2ResponseAssertionAccessor` để giữ SLO. Không thay provider bằng converter tự parse raw SAMLResponse.

**Điểm chung:** Nếu chỉ mapping trong controller để hiển thị rồi vẫn giữ Authentication authorities mặc định, `hasAuthority("ROLE_REPORT_VIEW")` trong SecurityFilterChain **chưa tự nhận** quyền đó. Muốn Spring authorization dựa role nội bộ, phải gắn authorities vào Authentication theo extension point được version hỗ trợ hoặc thiết kế một `AuthorizationManager`/service policy dùng CommonIdentity đáng tin.

## 16. Java 17 độc lập: policy cấp quyền không dựa email

Tệp `AuthorityPolicyDemo.java` chạy độc lập, mô phỏng một allowlist issuer/tenant:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class AuthorityPolicyDemo {

    record Provider(String tenant, String issuer) {
    }

    static Set<String> authorities(
            Provider provider, List<String> upstreamGroups) {

        Map<Provider, Map<String, String>> approved = Map.of(
                new Provider("team-a", "https://oidc.example.org"),
                Map.of("report-readers", "ROLE_REPORT_VIEW"),
                new Provider("team-a", "https://saml.example.org/entity"),
                Map.of("report-readers", "ROLE_REPORT_VIEW"));

        Map<String, String> mapping = approved.get(provider);
        if (mapping == null || upstreamGroups == null) {
            return Set.of();
        }

        Set<String> result = new TreeSet<>();
        for (String group : upstreamGroups) {
            String authority = mapping.get(group);
            if (authority != null) {
                result.add(authority);
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        Provider trusted = new Provider(
                "team-a", "https://oidc.example.org");
        Provider untrusted = new Provider(
                "team-b", "https://oidc.example.org");

        List<String> groups = List.of(
                "report-readers", "ROLE_ADMIN");

        System.out.println("trusted view=" +
                authorities(trusted, groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("untrusted view=" +
                authorities(untrusted, groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("admin=" +
                authorities(trusted, groups).contains("ROLE_ADMIN"));
    }
}
~~~

Chạy:

~~~bash
javac AuthorityPolicyDemo.java
java AuthorityPolicyDemo
~~~

Stdout chính xác:

~~~text
trusted view=true
untrusted view=false
admin=false
~~~

Giải thích:
1. Cùng một group nhưng chỉ issuer+tenant được duyệt mới cấp `ROLE_REPORT_VIEW`.
2. Provider thuộc team-b không được map theo team-a.
3. Chuỗi `ROLE_ADMIN` trong upstream groups không tự cấp quyền admin.
4. Dùng `TreeSet` để gom trùng rồi `Set.copyOf`, kết quả immutability nhưng bài tập chỉ hỏi membership.
5. Mẫu **không kiểm SAML/OIDC signatures**, chỉ là allowlist logic sau authentication. Production cần account status, tenant membership, resource scopes và API tích hợp thực tế.

## 17. Làm sao liên kết cùng một người qua OIDC và SAML?

### 17.1. Không tự động link theo email

Các mối nguy:

- User tại IdP A có email bằng user ở IdP B nhưng không phải cùng người.
- Email có thể được tái sử dụng sau khi nhân viên nghỉ việc.
- Một IdP cho phép user đổi email chưa xác minh, trong khi app tin claim.
- OIDC `email_verified=true` xác nhận kiểm soát email theo thời điểm và trust framework của OP, **không cấp quyền chiếm local account**.
- SAML attribute `email`/`mail` không có cờ verify tiêu chuẩn chung.
- Broker có thể phát một email từ nguồn upstream khác và account ở downstream không biết provenance.

**Do đó:** Email chỉ được dùng để **gợi ý** một đề nghị linking cho người dùng/administrator xem xét, không tự thực thi merge.

### 17.2. Quy trình linking an toàn hơn

1. Người dùng đã đăng nhập vào **local account hiện hữu** qua phương thức đáng tin.
2. Người dùng chủ động yêu cầu liên kết một provider/registration mới.
3. Ứng dụng buộc **reauthenticate** ở external provider mới, có state/nonce/CSRF/binding tương ứng.
4. Spring Security nhận Authentication đã xác minh và adapter xây external key mới.
5. Ứng dụng xác nhận external key chưa liên kết với local account khác, tenant/issuer được phép.
6. Với linking nhạy cảm, yêu cầu step-up MFA hoặc phê duyệt quản trị theo risk level.
7. Trong transaction, tạo unique constraint trên external key, ghi audit provenance/verifiedAt; chống race khi hai requests cùng link.
8. Nếu linking thất bại hoặc key đã bị dùng, **không** thay owner cũ và không tự tạo một account mới dưới cùng email.
9. Cung cấp unlink có xác nhận, nhưng không cho user tự xóa phương thức đăng nhập cuối cùng nếu sẽ khóa tài khoản ngoài ý muốn.
10. Khi IdP/OP chuyển đổi issuer/subject scheme, dùng **migration plan và administrative mapping có audit**, không nối đại theo email.

### 17.3. JIT provisioning khác account linking

**Just-in-Time (JIT) provisioning** tạo local account khi một external identity được xác minh lần đầu. **Account linking** nối external identity mới vào một **local account đã tồn tại**. Hai thao tác khác nhau.

JIT chỉ nên xảy ra khi:
- issuer/tenant/client đã được cho phép;
- subject ổn định và không trùng;
- IdP/OP có entitlement cho phép app;
- không va chạm với local account/định danh khác;
- các bước phê duyệt/lifecycle của tổ chức cho phép.

Không dùng cùng email để quyết định “đó là account cũ rồi” trong JIT.

## 18. So sánh định danh trong ba hệ thống thực tế

### 18.1. Cùng nhân viên, đăng nhập trực tiếp bằng OIDC

~~~text
OP Corporate:
  iss=https://oidc.example.org/realms/company
  sub=9e4a-uuid
  email=reader@example.org

Spring app:
  OAuth2AuthenticationToken
  OidcUser
  ExternalKey=(OIDC, team-a, iss, sub)
  Local account mapping -> local-user-001
~~~

### 18.2. Cùng nhân viên, đăng nhập trực tiếp bằng SAML

~~~text
IdP Corporate:
  Issuer=https://saml.example.org/entity
  NameID=persistent-employee-77
  NameID Format=persistent
  mail=[reader@example.org]

Spring app:
  Saml2Authentication / Saml2AssertionAuthentication
  ExternalKey=(SAML, team-a, Issuer, NameID, Format)
  Approved account link -> local-user-001
~~~

Ở đây hai external keys **khác nhau** dù cùng local account. App chỉ biết chúng đại diện cùng người **nếu** linking được chứng minh và phê duyệt.

### 18.3. Cùng nhân viên, SAML upstream qua OIDC broker

~~~text
Corporate SAML IdP:
  NameID=persistent-employee-77
       |
       v
Broker account:
  broker-user-567
       |
       v
OIDC ID Token to Spring:
  iss=https://broker.example.org/realms/workforce
  sub=broker-sub-567
  email=reader@example.org
       |
       v
Spring:
  OidcUser (KHÔNG phải Saml2AuthenticatedPrincipal)
  ExternalKey=(OIDC, team-a, broker issuer, broker-sub-567)
~~~

**Mấu chốt:** Nếu app chỉ có OIDC trust với broker, downstream external key là của **broker**, không mặc nhiên là issuer SAML upstream. Broker chịu trách nhiệm verify/bind upstream identity; app có thể kiểm provenance claim nếu có hợp đồng, nhưng không thay thế upstream validation mà app chưa thực hiện.

## 19. Session, logout và bảo toàn danh tính trong quá trình môi giới

Bên cạnh danh tính, hai giao thức có **phiên và logout semantics khác nhau**:

| Vấn đề | OIDC | SAML |
|---|---|---|
| Phiên trình duyệt app | Spring Security session | Spring Security session |
| Phiên nhà cung cấp | OP SSO session | IdP SSO session |
| Session identifier | `sid` nếu có, token/cookie OP | SessionIndex nếu IdP phát |
| Logout protocol | OIDC RP-initiated/back-channel/front-channel theo support | SAML Single Logout tùy binding/support |
| Access token | Có thể có, cần revocation/lifecycle riêng | Không phải thành phần login SAML thông thường |
| Local logout | Chỉ hủy app session nếu không phát logout liên kết | Chỉ hủy app session nếu không phát SLO |
| Federation logout qua broker | Cần bridge/session mapping đúng | Cần bridge/session mapping đúng |

**Không đồng bộ nhầm:** SAML SessionIndex không phải OIDC `sid` và cả hai không phải `JSESSIONID` của app. Khi người dùng logout khỏi Spring app, không mặc định broker đã logout upstream IdP hoặc ngược lại. Nếu yêu cầu “logout every connected app”, phải thiết kế explicit coordination, hỗ trợ protocol và kiểm PartialLogout/timeout.

Trong mô hình chung, có thể giữ một **auth provenance reference** phục vụ audit và session revocation, nhưng **không lưu raw ID Token, refresh token, SAMLResponse** trong DTO trả client.

## 20. Kiểm soát dữ liệu cá nhân và logging

OidcUser và SAML principal/accessor có thể chứa:

- NameID/sub và issuer.
- Email, tên, phòng ban, nhóm, mã nhân viên.
- ID Token/claims và UserInfo.
- SAML attributes hoặc raw SAMLResponse.
- Session identifiers, authentication time.
- Hints về tenant và roles.

**Nguyên tắc tối thiểu hóa:**
- Chỉ mang vào CommonIdentity các field business thật sự dùng.
- Không trả toàn bộ `getClaims()` hoặc `getAttributes()` trong API `/me`.
- Không log `getIdToken().getTokenValue()`, refresh token, `Saml2Authentication.getSaml2Response()` hoặc `Saml2ResponseAssertionAccessor.getResponseValue()`.
- Mã hóa hoặc hash/hạn chế truy cập ở audit store cho subject IDs nếu threat model yêu cầu, nhưng vẫn giữ key ổn định cho lookup.
- Tách **displayName** khỏi subject key, và email contact khỏi authorization.
- Không dùng raw groups để cho phép client tự khởi tạo authorities.
- Khi cần investigate, log registration ID, protocol, outcome, trusted issuer ID/tenant và correlation hash theo policy thay vì token payload.

**Đừng để class toString() tự in secrets**: một object chứa raw claims hoặc JWT nếu được log nguyên có thể rò rỉ PII. Thiết kế DTO riêng cho API.

## 21. Unit tests cho adapter và account-linking

### 21.1. Dữ liệu OIDC

| Test | Dữ liệu | Kỳ vọng |
|---|---|---|
| O1 | Authenticated OidcUser với issuer và sub hợp lệ | Snapshot đúng OIDC issuer/sub/registration |
| O2 | getIssuer khác expectedIssuer | **Từ chối** |
| O3 | sub null/trống | **Từ chối** |
| O4 | email_verified absent/false | emailProof không phải verified |
| O5 | email_verified true nhưng external key khác | **Không auto link** chỉ bởi email |
| O6 | UserInfo.sub khác IDToken.sub | OIDC validation phải reject trước adapter |
| O7 | cùng sub, issuer khác | hai ExternalIdentityKeys khác nhau |
| O8 | pairwise sub đổi theo OIDC client | không merge tùy ý; linking policy riêng |
| O9 | role claim là String thay vì List | Reject/normalize theo provider-specific contract, không cast bừa |
| O10 | OIDC non-user Authentication hoặc anonymous | Adapter không nhận |

### 21.2. Dữ liệu SAML

| Test | Dữ liệu | Kỳ vọng |
|---|---|---|
| S1 | 6.x Saml2AuthenticatedPrincipal NameID + attributes | Trích đúng issuer từ registration và NameID |
| S2 | 7.x Saml2AssertionAuthentication + accessor | Trích đúng NameID/registration, không cast principal legacy |
| S3 | NameID transient cho persistent account link | **Từ chối auto link** |
| S4 | NameID null/trống | **Từ chối** |
| S5 | SAML attribute `groups` nhiều values | Giữ đầy đủ, validate từng Object |
| S6 | Email attribute thiếu | Không crash, không coi user invalid nếu email optional |
| S7 | Email attribute có hai values khi contract yêu cầu một | Reject ambiguous hoặc không đưa vào contact |
| S8 | Signed Assertion sai issuer/audience | Spring SAML provider reject trước adapter |
| S9 | Saml2AuthenticationToken chưa validate | Không được map |
| S10 | Same NameID text, IdP issuer khác | Hai external keys khác nhau |
| S11 | Custom principal Spring 7 | Assertion accessor vẫn cung cấp NameID/session details |
| S12 | Role admin từ IdP không có entitlement | Không cấp ROLE_ADMIN |

### 21.3. Account mapping và tenant

| Test | Kịch bản | Kỳ vọng |
|---|---|---|
| A1 | Hai external keys được owner phê duyệt link | Cùng localUserId |
| A2 | Hai keys cùng email, chưa approved | Hai identities khác, không merge |
| A3 | External key đã thuộc user X, user Y cố link | Từ chối conflict |
| A4 | Tenant disabled/account locked | Không cấp phiên có quyền business |
| A5 | Tenant A key truy cập resource tenant B | 403/deny |
| A6 | Cùng group name từ OP không được trust | Không map role |
| A7 | IdP cert/JWKS rotation | Chỉ nhận khóa trusted mới, không bypass signature |
| A8 | Concurrent link race | Unique constraint/transaction ngăn duplicate ownership |
| A9 | User unlinks login cuối cùng | Policy ngăn mất quyền truy cập ngoài ý muốn |
| A10 | Reused email sau offboarding | Không chiếm local account cũ |

Unit tests chỉ mô phỏng adapter. Cần **integration tests thật** với OIDC OP/test IdP và SAML signed fixtures cho signature, issuer/audience/time/correlation.

## 22. Integration tests với Spring Security và broker

### 22.1. OIDC

1. Authorization Code Flow có state/nonce/redirect URI đúng.
2. ID Token do trusted issuer ký và audience chứa client ID.
3. `sub`, `iss` được đọc từ ID Token đã xác minh.
4. UserInfo optional; nếu có, `sub` khớp ID Token.
5. ClientRegistration khác issuer không được chấp nhận.
6. `email_verified` chỉ dùng làm tín hiệu proof có giới hạn, không vượt qua account-link approval.
7. Resource Server JWT (nếu app có API) có issuer/audience checks **riêng** cho access token, không dùng ID Token làm API bearer token.

### 22.2. SAML

1. Response/Assertion signature hợp lệ với IdP verification cert của RP registration.
2. `Issuer`, `AudienceRestriction`, `Recipient/Destination`, time, `InResponseTo` đúng.
3. Assertion dùng tạo principal **đúng node được ký**; chống XML Signature Wrapping.
4. 6.x and 7.x adapters đều được test trên version tương ứng.
5. Multi-value attributes/group mappings không bị cắt còn một giá trị.
6. SAML NameID Format persistent/qualifiers phù hợp contract cho account binding.
7. IdP-initiated unsolicited response theo policy riêng; không bỏ correlation của SP-initiated.
8. Mất session/clock/cookie làm SSO fail an toàn, không nhận Response nhầm tenant.
9. SAML Single Logout cần NameID/SessionIndex và không được phá vì custom principal.

### 22.3. Broker SAML → OIDC

1. Broker verify upstream SAML và link đúng upstream subject.
2. Broker phát ID Token **mới** với `iss` là broker, `sub` là broker subject.
3. Downstream Spring chỉ map theo broker issuer/sub.
4. Broker chuyển upstream groups thành downstream claims qua allowlist đúng tenant.
5. Nếu upstream email đổi, downstream local account không bị đổi subject key tùy tiện.
6. Nếu broker có nhiều upstream IdPs, không trộn identities có cùng email.
7. Logout upstream/downstream được thử riêng, gồm timeout, session still alive và revocation policy.
8. Tenant-level provisioning/offboarding/disabled accounts nhất quán giữa các phía.

## 23. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `ClassCastException` khi cast `OidcUser` sang `Saml2AuthenticatedPrincipal` | Hai loại principal khác nhau | Dùng adapter có type checks và protocol branches |
| `ClassCastException` với Saml2AuthenticatedPrincipal sau upgrade 7.x | Principal mặc định đã thay đổi | Dùng `Saml2AssertionAuthentication.getCredentials()` và accessor |
| OIDC login OK nhưng account mapping thiếu | Lấy `getName()` thay `(iss,sub)` hoặc registration không mapping | Kiểm OIDC subject/issuer sau validation, provider registry |
| SAML login OK nhưng account mapping thiếu | NameID Format/issuer khác DB key, transient ID | Thống nhất persistent NameID contract, migrate an toàn |
| Cùng email nhưng app tạo hai accounts | Hai external keys khác nhau | Đây có thể đúng; dùng linking workflow có approval |
| Hai user bị merge nhầm | Tự auto-link theo email | Dừng auto-link, điều tra provenance/rollback mapping |
| UserInfo trả claim khác ID Token | UserInfo sub mismatch, provider issue | Reject mismatch; kiểm OP provider |
| OIDC email_verified null | Claim không phát hoặc chưa xác minh | Không mặc định thành true |
| SAML groups hiển thị thiếu | Dùng getFirstAttribute thay vì getAttribute | Đọc tất cả values, validate type |
| OIDC groups là JSON array nhưng cast String | Provider-specific schema khác | Converter đúng contract và typed validation |
| SAML attribute mail không có | IdP dùng URI claim khác | Thống nhất AttributeStatement mapping contract |
| `hasRole("ADMIN")` fail dù claim admin có | Authentication authorities chưa map | Thêm mapper theo issuer/tenant; không tự tin claim |
| Login có `ROLE_USER` nhưng truy cập tenant B | Resource authorization thiếu tenant check | Enforce tenant scope ở service/data layer |
| Broker upstream SAML nhưng app thấy OidcUser | App nhận OIDC downstream từ broker | Đúng kiến trúc; map broker iss/sub |
| Broker issuer đổi sau migration | Downstream identity key không khớp | Cần issuer/key migration với admin approval |
| OIDC pairwise sub khác ở client mới | Sector/client thay đổi | Làm account linking theo proof, không merge email |
| SAML SLO fail với custom principal | Framework không còn NameID/SessionIndex | Dùng assertion accessor/version-appropriate converter |
| Group/role mới không cập nhật ở session | Authorities snapshot lúc login, cache/session còn cũ | Reauthentication/session revocation/permission refresh policy |
| Log lộ raw ID Token/SAMLResponse | Logging object toString/raw claims | Mask/minimize, rotate secrets khi lộ và audit |
| App vừa OIDC vừa SAML nhưng default login picker lộn tenant | EntryPoint/callback không được scope theo registration | Trusted tenant picker, path/host allowlist, issuer checks |

## 24. Checklist code review và triển khai

- [ ] Định nghĩa rõ OIDC vs SAML, direct login vs brokered login.
- [ ] Chỉ dùng claims/attributes từ **Authentication đã xác thực** do Spring provider tạo.
- [ ] OIDC external key giữ **iss+sub**, không thay bằng email/getName tùy biến.
- [ ] SAML external key giữ **IdP issuer + NameID với semantics Format/qualifiers**; không dùng transient ID cho long-lived linking.
- [ ] Có tenant/registration scope và provider policy riêng cho từng IdP/OP.
- [ ] AccountLink uniqueness/approval/audit có kiểm soát; không auto-merge theo email.
- [ ] email_verified OIDC được hiểu đúng, nullable, không tự cấp quyền.
- [ ] SAML AttributeStatement được xử lý dạng multi-value Map<String,List<Object>>.
- [ ] OIDC claims được kiểm kiểu, UserInfo sub khớp ID Token sub.
- [ ] Spring Security 6.x SAML đọc Saml2AuthenticatedPrincipal đúng API.
- [ ] Spring Security 7.x SAML dùng Saml2AssertionAuthentication/Saml2ResponseAssertionAccessor, không cast cứng legacy principal.
- [ ] Không expose raw ID Token, access/refresh token, raw SAMLResponse, SessionIndex hoặc private keys trong JSON/log.
- [ ] Nhóm/role được map theo provider+issuer+tenant allowlist, không tin raw upstream role.
- [ ] Spring Authorization chỉ dùng GrantedAuthority/local permissions đã được mapping đúng giai đoạn.
- [ ] Business resource authorization vẫn kiểm tenant/data ownership.
- [ ] Broker phát OIDC issuer/sub riêng; upstream SAML issuer/NameID chỉ là provenance theo contract nếu downstream không tự verify.
- [ ] OIDC/SAML logout/revocation có lifecycle riêng, không assume propagation qua broker.
- [ ] Có tests identity collisions, email reuse, pairwise sub, SAML transient NameID, multi-tenant role mix-up.
- [ ] OIDC JWT signature/issuer/audience/state/nonce, SAML signature/issuer/audience/recipient/time/replay được test với IdP thật.
- [ ] Đã kiểm version Spring Security/Spring Boot/OpenSAML/OAuth2 client và migration 6.x→7.x.

## 25. Câu hỏi ôn tập

1. **OidcUser và Saml2AuthenticatedPrincipal có phải cùng một kiểu không?** Không, chúng đại diện hai giao thức và API claims khác nhau.
2. **OIDC account key nên lấy gì?** Cặp `(iss,sub)` từ ID Token đã xác minh, cộng tenant policy trong ứng dụng.
3. **Tại sao OIDC email không làm user ID?** Không bảo đảm unique/ổn định; OpenID Connect Core nhấn mạnh chỉ cặp issuer+subject có bảo đảm đó.
4. **email_verified=true có đủ tự liên kết local account cũ không?** Không; nó chỉ là một tín hiệu xác minh email theo OP trust, không chứng minh quyền với local account.
5. **SAML NameID có luôn ổn định không?** Không; transient NameID không phù hợp cho liên kết dài hạn.
6. **Vì sao cần NameID Format/qualifiers?** Cùng NameID text có thể có ngữ nghĩa/scope khác nhau.
7. **Trong Spring Security 6.x đọc SAML attributes từ đâu?** `Saml2AuthenticatedPrincipal.getAttributes/getAttribute` sau xác thực.
8. **Trong Spring Security 7.x nên đọc SAML attributes từ đâu?** `Saml2AssertionAuthentication.getCredentials().getAttributes()` qua `Saml2ResponseAssertionAccessor`.
9. **SAML getAttribute("groups") trả kiểu gì?** Danh sách giá trị; không bảo đảm mọi phần tử là String.
10. **OIDC getClaims có chứa UserInfo không?** Có thể tổng hợp ID Token + UserInfo, nhưng UserInfo có thể null.
11. **Tại sao broker SAML → OIDC trả OidcUser downstream?** Vì broker phát một OIDC ID Token mới và đóng vai trò OP.
12. **Issuer dùng làm key ở downstream broker là issuer nào?** **Broker OIDC issuer** nếu app không trực tiếp dùng upstream SAML.
13. **SAML group report-readers có tự là ROLE_REPORT_VIEW không?** Không. Cần tenant/provider allowlist và mapper.
14. **Tại sao custom principal nguy hiểm với SAML 7 migration?** Code legacy cast principal có thể sai; cần dùng assertion accessor và test SLO.
15. **Trong Java Spring 7 code adapter có tự tạo localUserId không?** Không. Snapshot chỉ là dữ liệu nguồn; cần AccountLinkRepository và account status checks.
16. **Có thể dùng claim tenant từ browser để chọn quyền không?** Không; tenant cần trusted registration/routing và authorization.
17. **Nếu UserInfo.sub khác ID Token.sub thì sao?** Phải từ chối dùng UserInfo đó theo OIDC Core.
18. **Nếu hai người cùng email nhưng issuer khác, hệ thống nên làm gì?** Giữ external identities riêng; chỉ link khi có proof/approval.
19. **Logout local của ứng dụng có kết thúc broker/IdP sessions không?** Không mặc định, cần logout protocol/coordination riêng.
20. **Đâu là phân biệt quan trọng nhất?** Chuẩn hóa shape cho business, nhưng **không xóa issuer/subject/tenant provenance và trust boundaries**.

## 26. Nguồn tài liệu chính thức

- **OpenID Connect Core 1.0**, đặc biệt §5.3.2 UserInfo subject matching, §5.7 Claim Stability & Uniqueness, §8 Pairwise Subject: https://openid.net/specs/openid-connect-core-1_0.html
- **Spring Security OidcUser JavaDoc** (getClaims, getIdToken, getUserInfo, getSubject/getIssuer): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- **Spring Security OIDC OAuth2 Login Core**, ClientRegistration and issuer-uri: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- **Spring Security OAuth2 Login Advanced**, GrantedAuthoritiesMapper/OidcUserService: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- **Spring Security SAML2 Login Overview**, signatures/principal: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security Authenticating SAML2 Responses**, custom converter/authority mapping: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Security SAML 2.0 Migration to 7**, Saml2ResponseAssertionAccessor & deprecated Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- **Spring Security Saml2AssertionAuthentication JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
- **Spring Security Saml2ResponseAssertionAccessor JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
- **OASIS SAML 2.0 Core**, NameID Format, qualifiers, assertion/conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OWASP SAML Security Cheat Sheet**, issuer/trust/XML signature/conditions: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- **Spring Security Authorization**, authorities vs domain access: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

**Tổng kết:** `OidcUser` và `Saml2AuthenticatedPrincipal` có thể được ánh xạ về **một CommonIdentity** để business không phụ thuộc protocol, nhưng không được bỏ nguồn chứng thực. **OIDC dùng `(iss,sub)`; SAML dùng trusted IdP issuer cùng NameID theo Format/qualifiers/tenant contract.** Tài khoản nội bộ và quyền chỉ hình thành qua **explicit account linking/provisioning và authorization policy**, không chỉ vì email hoặc group text trùng nhau. Với Spring Security 7.x, thay cách đọc SAML legacy principal bằng `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor` để không nhầm phiên bản.
