# Lựa chọn giao thức theo hạ tầng và giới hạn không thể dùng thay thế tùy ý

## 1. Vì sao không thể chỉ hỏi “giao thức nào hiện đại nhất”?

Trong mô hình **liên kết danh tính** (*identity federation*), tổ chức thường phải kết nối nhiều hệ thống: Active Directory (AD DS), LDAP directory, mạng nội bộ Windows, cổng web Java, ứng dụng SaaS, mobile, API, service-to-service và một hoặc nhiều Identity Provider (IdP). Chọn phương thức xác thực chỉ theo tên giao thức dễ dẫn đến lỗi thiết kế.

Một giải pháp đúng phải bắt đầu từ câu hỏi: **ai cần chứng minh danh tính cho ai, trên kết nối nào, bằng bằng chứng gì, với quyền gì?** Các giao thức có phạm vi và tiền đề khác nhau. Không thể tùy ý thay LDAP bind bằng SAML assertion, thay Kerberos ticket bằng access token, hoặc dùng ID Token như bearer token của một API.

Các khái niệm nền:

- **Identity store/directory:** nơi lưu người dùng, nhóm, thiết bị, thuộc tính và khóa liên kết. Ví dụ AD DS/OpenLDAP; các hệ thống này có thể được truy cập bằng LDAP.
- **Authentication:** chứng minh danh tính của user, thiết bị, client hay workload. Ví dụ Kerberos, WebAuthn, xác thực mật khẩu qua LDAP bind, client certificate mTLS.
- **Federated login/SSO:** một ứng dụng tin kết quả đăng nhập do hệ thống định danh khác phát hành theo quan hệ tin cậy có cấu hình. Ví dụ SAML 2.0 Web SSO và OpenID Connect.
- **Authorization/delegation:** quyền để client gọi một tài nguyên. OAuth 2.0 là khung ủy quyền; API kiểm tra access token/scopes/audience theo chính sách.
- **Provisioning/lifecycle:** tạo, cập nhật, khóa và xóa tài khoản ở hệ thống đích. SCIM là giao thức phổ biến cho mục đích này; nó không tự xác thực đăng nhập.
- **Application principal:** danh tính ứng dụng nhận diện sau xác thực, có thể là mã user nội bộ hoặc service account; từ principal đó mới xác định roles/permissions.

**Quy tắc xuyên suốt:** cùng một người có thể được nhận diện bởi AD, SAML IdP và OIDC Provider, nhưng bằng chứng và cách rút trích danh tính ở ba bên không giống nhau. Chỉ hệ thống **liên kết danh tính có kiểm soát** mới quyết định các danh tính ấy tương ứng cùng một tài khoản ứng dụng.

## 2. Sơ đồ trách nhiệm: từng giao thức giải quyết đoạn nào?

~~~text
        [Nguồn nhân sự / quản trị danh tính]
                       |
               Provisioning: SCIM
                       |
          +------------v-------------+
          |  Directory / AD DS       |
          |  Users, Groups, Devices  |
          +--+----------+------------+
             |          |
         LDAP query   Kerberos / KDC
         & bind          |
             |          v
             |    Windows domain SSO / SPNEGO
             |          |
             +----+-----+                   +-------------------+
                  |                         | IdP / Federation  |
                  |     LDAP/Kerberos       | Gateway/Broker    |
                  +------------------------>|                   |
                                            +----+----------+---+
                                                 |          |
                                            SAML assertion  OIDC ID Token
                                                 |          |
                                       +---------v----------v---+
                                       | Web application / BFF  |
                                       | Spring Security        |
                                       +------------+-----------+
                                                    |
                                          user session / identity
                                                    |
                                       application authorization
                                                    |
                                                 [API]

   [Machine / workload] -- mTLS / OAuth2 client_credentials --> [API]
                                 proof of peer/client
                                     + audience/scope
~~~

Sơ đồ thể hiện các lựa chọn **có thể phối hợp**, không phải tất cả giao thức đều bắt buộc trong một hệ thống. Một IdP có thể xác thực người dùng bằng Kerberos hoặc đọc directory qua LDAP ở phía sau, rồi phát hành OIDC ID Token cho web app. Ứng dụng chỉ cần xử lý OIDC; việc IdP dùng LDAP không biến web app thành LDAP client.

## 3. Bảng chọn nhanh theo mục đích và điều kiện hạ tầng

| Hạ tầng hoặc nhu cầu | Lựa chọn thường phù hợp | Điều kiện cần | Không nên suy diễn |
|---|---|---|---|
| Hệ thống cũ giữ username/password trong directory | **LDAP bind qua TLS** với directory/AD DS | Directory endpoint, quyền search, user DN/filter, LDAPS/StartTLS | LDAP bind không tự tạo browser SSO, MFA hay token API. |
| Máy Windows đã join domain, ứng dụng intranet cần đăng nhập tích hợp | **Kerberos/SPNEGO** hoặc gateway hỗ trợ Windows Integrated Authentication | KDC, SPN, keytab/service principal, DNS/time/browser policy | Kerberos ticket không phải OIDC ID Token hay JWT cho API khác. |
| Đối tác/ứng dụng SaaS enterprise chỉ hỗ trợ SAML | **SAML 2.0 Web SSO** | IdP metadata, SP entity ID, ACS, signing cert, cấu hình trust | SAML assertion không phải OAuth2 access token sử dụng tùy ý cho REST API. |
| Web app mới cần SSO với IdP cloud | **OIDC Authorization Code** (PKCE theo loại client) | OIDC Provider, client registration, redirect URI, HTTPS, discovery/JWK | Chỉ cấp OAuth access token không có nghĩa đã có OIDC login. |
| SPA/mobile đăng nhập bên ngoài | **OIDC Authorization Code + PKCE**, system browser/SDK phù hợp | Public client, redirect scheme/URI hợp lệ, token handling an toàn | Không dùng implicit/password grant như cách thay thế mặc định. |
| REST API được nhiều client gọi | **OAuth2 Resource Server** xác thực JWT access token hoặc introspection opaque token | Issuer/AS đáng tin, audience API, scope, token lifecycle | ID Token cho web login không phải API access token. |
| Backend service gọi backend service | **mTLS**, **OAuth2 client_credentials**, hoặc kết hợp tùy threat model | PKI/workload identity; AS/client authentication; token audience và policy | mTLS chỉ xác thực TLS peer; client_credentials thường không mang danh tính end-user. |
| Đồng bộ tài khoản từ IdP sang SaaS | **SCIM 2.0** + giao thức login riêng | Provisioning API, CRUD, lifecycle, reconciliation | SCIM không phải một phương thức để người dùng đăng nhập. |
| Xác thực mạng Wi-Fi/VPN ở tầng truy cập | **802.1X/EAP, RADIUS** tùy thiết bị/hạ tầng | Network access server, supplicant, AAA server | RADIUS không thay trực tiếp OIDC/SAML Web SSO. |
| Đăng nhập chống phishing bằng security key/passkey | **FIDO2/WebAuthn**, thường tại IdP hoặc ứng dụng | Browser/device/authenticator và server hỗ trợ | WebAuthn là cơ chế xác thực, không tự là giao thức federation giữa mọi ứng dụng. |

Không có “giao thức tốt nhất” tách khỏi kiến trúc. Tổ chức có AD không có nghĩa tất cả web app phải kết nối LDAP; tổ chức dùng OIDC không có nghĩa mọi thiết bị mạng hỗ trợ OIDC trực tiếp.

## 4. LDAP: directory access và xác thực bằng bind

**LDAP** định nghĩa cách client tìm, đọc và (nếu được cấp quyền) sửa entry trong directory, cũng như thao tác **bind** để máy chủ directory xác thực danh tính phiên kết nối. Với Spring Security, mô hình LDAP bind thường là:

1. Người dùng nhập username/password trong giao diện của ứng dụng.
2. Ứng dụng tìm DN của user qua LDAP search hoặc xác định DN theo pattern đã được tổ chức xác nhận.
3. Ứng dụng thử bind với mật khẩu user qua LDAPS/StartTLS.
4. Nếu bind thành công, ứng dụng lấy groups/attributes và tạo Spring `Authentication`.
5. Spring authorization quyết định người dùng được truy cập chức năng nào.

~~~text
Browser ---> Form Login (user + password) ---> Spring Security
                                               |
                                               +-- LDAP search ----> Directory
                                               +-- LDAP bind ------> Directory
                                               |
                                               +-- local user/role mapping
~~~

Điều kiện: ứng dụng phải kết nối trực tiếp được directory và xử lý credential theo một thiết kế được phê duyệt. **Việc cho ứng dụng nhận mật khẩu nhân viên làm tăng bề mặt tiếp xúc với mật khẩu**; cần TLS, không ghi log bí mật, kiểm soát brute-force và giới hạn quyền tài khoản dịch vụ. LDAP bind không biến ứng dụng thành OIDC Relying Party hay SAML Service Provider.

### Không dùng LDAP để “thay” các chức năng sau

- **Browser SSO:** LDAP bind thường kiểm tra mật khẩu mỗi lần ứng dụng yêu cầu; không tự cấp cookie SSO liên ứng dụng hoặc nhận phiên browser đã đăng nhập tại IdP.
- **OAuth2 API access:** LDAP không phát hành access token có audience/scope/expiry để resource server khác xác minh.
- **MFA:** một lần simple bind không mặc nhiên cung cấp policy MFA, step-up hay device compliance. Các cơ chế MFA tích hợp directory là phụ thuộc sản phẩm/hạ tầng, không phải tính năng mặc định của giao thức LDAP.
- **Liên kết tài khoản ổn định:** DN có thể đổi khi người dùng được rename/move OU; cần khóa directory ổn định phù hợp schema (trong AD thường là `objectGUID`) và quy trình account linking.

Mã cấu hình LDAP trong Spring Security có một điểm mở rộng là `LdapBindAuthenticationManagerFactory`; việc sử dụng `spring-security-ldap` không tự bổ sung SAML/OIDC. Với hệ thống cần SSO hiện đại, một kiến trúc thường tốt hơn là **IdP nói chuyện với AD/LDAP**, còn các ứng dụng web nói chuyện với **IdP bằng SAML hoặc OIDC**.

## 5. Kerberos/SPNEGO: SSO dựa vào domain và service principal

**Kerberos** sử dụng ticket do Key Distribution Center (KDC) cấp để client chứng minh danh tính với dịch vụ có service principal. Trong hạ tầng Microsoft AD, KDC thường có mặt trên domain controller. Với browser intranet, **SPNEGO/Negotiate** có thể chuyên chở cơ chế Kerberos trong HTTP để người dùng đã đăng nhập domain có trải nghiệm SSO.

~~~text
Domain-joined workstation
         |
         |  TGT / Kerberos service ticket từ KDC
         v
Browser -- HTTP Negotiate (SPNEGO token) --> Intranet application
                                               |
                                   accept ticket theo SPN/keytab
                                               |
                                    map principal + authorities
~~~

Các điều kiện không thể bỏ qua:

- Client và dịch vụ có thể truy cập domain/KDC phù hợp, đồng hồ đồng bộ, DNS/SPN chính xác.
- Service principal, keytab hoặc cơ chế delegated credential được quản trị an toàn.
- Browser và hệ điều hành có chính sách cho phép Integrated Authentication đến origin tương ứng.
- Proxy, load balancer và hostname phải được thiết kế đúng để ticket cấp cho SPN không bị đưa vào dịch vụ sai.
- Nếu cần constrained delegation hay gọi dịch vụ phía sau bằng danh tính user, phải thiết kế riêng; vé Kerberos đến service A không được tùy tiện sử dụng tại service B.

**Kerberos không đồng nghĩa LDAP.** AD có thể cung cấp cả LDAP và Kerberos; ứng dụng dùng LDAP bind gửi user/password cho directory, còn SPNEGO dựa vào ticket. Spring Security hỗ trợ tích hợp Kerberos qua module phù hợp, nhưng không tự kích hoạt Kerberos chỉ bằng cấu hình `spring-security-ldap`.

Kerberos hữu ích cho mạng nội bộ được quản trị chặt, nhưng khó dùng trực tiếp cho website public và máy cá nhân không join domain. Khi muốn mở SSO ra SaaS/ứng dụng ngoài, thường đặt **IdP/federation gateway** phía trước: người dùng xác thực với IdP bằng Windows Integrated Authentication, còn SaaS nhận **SAML** hoặc **OIDC** từ IdP.

## 6. SAML 2.0: liên kết đăng nhập web với XML assertion

**SAML 2.0 Web Browser SSO** được nhiều doanh nghiệp và ứng dụng SaaS sử dụng. Tại đây, **Identity Provider (IdP)** xác thực user, phát hành **SAML Response/Assertion**; ứng dụng đích là **Service Provider (SP)** kiểm tra theo trust relationship.

~~~text
Browser ---> SP (Spring web app)
     <--- redirect sang IdP kèm AuthnRequest
Browser ---> IdP (đăng nhập/MFA theo chính sách)
     <--- SAMLResponse
Browser ---> SP Assertion Consumer Service (ACS)
             |
             +-- xác minh issuer, chữ ký, conditions, recipient/audience
             +-- ràng buộc request/response, thời gian, chống replay
             +-- ánh xạ NameID / attributes -> internal account
             +-- tạo Spring session + authorities
~~~

Một SAML trust thông thường cần:

- **IdP entity ID**, SSO endpoint và certificate/key hợp lệ để kiểm tra chữ ký.
- **SP entity ID**, **ACS URL** và metadata/registration được IdP chấp nhận.
- Kiểm tra **Issuer**, **AudienceRestriction**, **Recipient/Destination**, thời gian (`NotBefore`, `NotOnOrAfter`) và **InResponseTo** khi phù hợp với flow.
- Chính sách đối với chữ ký, encryption, key rotation, clock skew, RelayState và replay; phải áp dụng theo profile thực tế.
- Chọn **NameID format** hoặc attribute danh tính ổn định. NameID dạng email hoặc transient không thể mặc nhiên là khóa user bất biến.

**SAML assertion không phải OAuth2 access token.** Assertion phục vụ audience/recipient của SP và flow của SAML; ứng dụng không được lấy một assertion cho portal A rồi đưa vào `Authorization: Bearer` của API B mà không có **token exchange/bridge** được thiết kế và phát hành token mới phù hợp.

Spring Security Servlet hỗ trợ `saml2Login()` qua `spring-security-saml2-service-provider`. Cấu hình `RelyingPartyRegistrationRepository` hoặc metadata cho biết SP tin IdP nào. `Saml2AuthenticatedPrincipal` là nguồn principal/attributes sau khi framework kiểm tra SAML, nhưng **ứng dụng vẫn chịu trách nhiệm link account và phân quyền nghiệp vụ**.

Lưu ý: logout SAML hoặc single logout không tự được triển khai đúng chỉ vì login đã hoạt động; phải cấu hình/kiểm thử cùng IdP, session và topology thực tế.

## 7. OpenID Connect: federation cho web/mobile trên OAuth 2.0

**OpenID Connect (OIDC)** bổ sung lớp xác thực người dùng trên OAuth 2.0. Trong **Authorization Code Flow**, ứng dụng (Relying Party/OIDC client) điều hướng browser đến OpenID Provider, nhận authorization code rồi đổi code lấy token theo cấu hình client. `ID Token` là bằng chứng định danh dành cho **OIDC client** nếu được xác minh đầy đủ.

~~~text
Browser -> Application -> OpenID Provider (Authorization endpoint)
               <--------- authorization code (redirect)
Application -> OpenID Provider (Token endpoint, code exchange)
            <- ID Token (+ access token, tùy scope/flow)
Application -> validate ID Token and map (iss, sub)
            -> internal principal/session
~~~

Các ràng buộc chủ chốt:

- Xác minh **chữ ký**, `iss`, `aud` (phải chứa client ID tương ứng), `exp`/thời gian và `nonce` khi flow yêu cầu.
- Xác thực `state`/correlation của authorization response; dùng **PKCE** để chống code interception, nhất là public client như mobile/SPA.
- Khóa liên kết người dùng ổn định theo **cặp `iss + sub`**; không gắn tài khoản chỉ bằng `email`, `name` hoặc `preferred_username` vì các claim này có thể thay đổi hoặc bị dùng lại.
- Bảo vệ redirect URI và secret. Public client không được coi client secret nhúng trong ứng dụng là bí mật.
- Nếu dùng UserInfo, kiểm tra `sub` nhất quán với ID Token theo quy định OIDC.

Với ứng dụng Spring Security Servlet, `oauth2Login()` thuộc tính năng OAuth2 Client; trong luồng có `scope=openid`, Spring sử dụng xử lý OIDC phù hợp. Đây là lựa chọn thuận lợi cho web/app cloud có IdP hỗ trợ OIDC discovery/JWK. Trong mobile nên dùng **system browser**, không thu thập mật khẩu IdP trong WebView hoặc app tùy tiện.

OIDC **không mặc định thay** Kerberos cho mọi Windows service, thay SCIM để provisioning, hay thay OAuth2 Resource Server ở mọi API. Một Spring MVC web app có thể dùng OIDC login và sau đó giữ **HTTP session**; API khác có thể nhận **OAuth2 access token**, là hai mô hình khác nhau dù cùng issuer.

## 8. OAuth 2.0: ủy quyền cho client/API, không phải tên gọi chung của đăng nhập

OAuth 2.0 phân biệt các vai trò: **resource owner**, **client**, **authorization server** và **resource server**. Access token cấp khả năng truy cập tài nguyên theo authorization grant, scope, audience và policy. OAuth 2.0 thuần không định nghĩa cấu trúc thông tin xác thực end-user như OIDC ID Token.

**Không thể lấy `access_token` rồi decode một claim `user` và coi là SSO chuẩn** nếu provider không đưa ra hợp đồng xác thực danh tính được kiểm chứng. API còn phải kiểm tra token được phát hành **cho chính API đó** (audience), bởi issuer được tin, còn hiệu lực, với scope/permissions đúng.

Phân biệt hai tình huống:

| Flow/đối tượng | Chứng cứ nhận | Principal logic |
|---|---|---|
| Browser OIDC login | ID Token cho OIDC client, kết hợp authorization response | Người dùng được IdP xác thực; map sang tài khoản app. |
| API OAuth2 bearer JWT | **Access token** JWT có signature, issuer, audience, expiry, scopes | User **hoặc client**, tùy token/flow; policy API quyết định. |
| API OAuth2 opaque token | Chuỗi opaque, resource server introspect với AS | Principal/attributes từ kết quả introspection đáng tin. |
| Machine-to-machine `client_credentials` | Access token cho client/service | Thường là **client identity**, không mặc định có end-user. |

Spring Security Resource Server có `oauth2ResourceServer().jwt()` để xác thực JWT và `opaqueToken()` để introspection. Cần cấu hình verifier/issuer, audience, loại token, validation tùy issuer và mapper scope/authorities. `JwtAuthenticationConverter` có thể chuyển scope/claim hợp lệ sang `GrantedAuthority`. Không được coi `scope=openid` là `ROLE_ADMIN`.

**API có hai token có chữ ký hợp lệ chưa chắc nhận cả hai.** Một token phát hành với `aud=payroll-api` không được dùng ở `billing-api` chỉ vì `iss` giống nhau. Nếu cần client A gọi API B thay user, phải thiết kế ủy quyền/token exchange đúng chuẩn và trust boundary, không đơn giản chuyển tiếp token khác audience.

## 9. mTLS/X.509: xác thực peer trên kết nối, không tự giải quyết federation end-user

**TLS** mã hóa kênh và xác thực server; **mTLS** còn yêu cầu client trình certificate và chứng minh sở hữu private key trên kết nối TLS. Đây là cơ sở tốt để nhận diện dịch vụ/máy trong mạng nội bộ hoặc service mesh.

Nhưng khi **gateway/proxy kết thúc TLS**, backend thường nhìn thấy **gateway** là TLS peer của kết nối mới. Certificate của người dùng ban đầu không tự chuyển sang backend dưới dạng attribute đã được xác thực.

~~~text
User's client certificate -- mTLS --> Gateway
                                      | verifies original TLS peer
                                      | creates trusted identity assertion
                                      v
                                  Backend
                                      | verifies assertion provenance
                                      | maps internal user/role
                                      v
                                 Business API

Gateway certificate -- mTLS (new connection) --> Backend
      (certificate này xác thực gateway, không đồng nghĩa user gốc)
~~~

Để truyền danh tính user qua gateway, cần một cơ chế **assertion được bảo vệ**: mTLS proxy-backend + đường kết nối bị giới hạn và header được proxy ghi đè, hoặc token/assertion ký và kiểm tra signature, issuer, audience, expiry. Không tin `X-User` hay `X-Client-Cert` do HTTP client tự gửi. Khi cùng ứng dụng có yêu cầu user-level role, mTLS chỉ là **một lớp chứng minh peer**, còn mapping và authorization vẫn do ứng dụng hoặc authorization service thực hiện.

mTLS và OAuth2 có thể **kết hợp**: mTLS xác thực client đến token endpoint và/hoặc ràng buộc access token với certificate theo profile phù hợp, còn token mang scope/audience. Không thể coi việc bật HTTPS client certificate là tự xuất hiện `SCOPE_orders.write` trong Spring Security.

## 10. Những thứ dễ bị nhầm là có thể thay thế

### 10.1. SCIM không thể thay SAML/OIDC

SCIM 2.0 là REST-based protocol cho **provisioning và quản lý Users/Groups**. Một ứng dụng SaaS có thể nhận user từ SCIM vào ngày bắt đầu làm việc, nhưng đến lúc user bấm “Đăng nhập”, vẫn cần **OIDC/SAML/password hoặc cơ chế đăng nhập được chấp thuận**. Ngược lại, SSO thành công không tự có nghĩa tài khoản đã được provision hoặc đã có quyền nghiệp vụ.

### 10.2. WebAuthn/passkey không phải một federation protocol

WebAuthn sử dụng chứng thực dựa trên khóa công khai để đăng nhập tại một **Relying Party/origin**; IdP có thể chọn WebAuthn làm yếu tố xác thực chống phishing. Khi đó app SaaS vẫn nhận SAML/OIDC từ IdP. Một WebAuthn credential của origin A không thể lấy nguyên làm access token cho API B. Giao thức giải quyết lớp **chứng minh danh tính tại điểm đăng nhập**, không định nghĩa liên kết tài khoản liên ứng dụng.

### 10.3. AD DS không đồng nghĩa OIDC Provider

AD DS là directory/domain infrastructure; cung cấp LDAP và Kerberos, nhưng không phải cứ có domain controller là tự có discovery endpoint `/.well-known/openid-configuration` và ID Token cho ứng dụng cloud. Cần IdP/federation service như thành phần chuyên trách, với chính sách trust và cấu hình phù hợp.

### 10.4. JWT là định dạng token, không phải giao thức đăng nhập

Một đối tượng JWT tự tạo với `{"sub":"admin"}` chỉ là chuỗi dữ liệu được mã hóa Base64URL hoặc ký bằng một khóa nào đó. Phải xác minh **issuer, chữ ký, thuật toán, audience, expiry và loại token**. Chỉ biết token là JWT không chứng minh danh tính. Ngược lại, SAML thường dùng XML assertion; OAuth2 opaque token không bắt buộc là JWT.

### 10.5. Reverse proxy gửi header không mặc nhiên tạo SSO

Nếu gateway kết thúc SAML/OIDC và truyền username cho backend, backend phải biết chính xác ai được quyền gửi assertion, header có bị spoofing hay không, việc ký/verify diễn ra ở đâu, account nào được map và khi nào session hết hiệu lực. Một header không có nguồn gốc đã được bảo vệ **không** là bằng chứng thay thế SAML/OIDC.

### 10.6. MFA và yêu cầu mức độ xác thực không nằm trong tên giao thức

Một hệ thống có thể đăng nhập bằng OIDC nhưng người dùng chỉ dùng password; hệ thống khác có thể dùng SAML với MFA mạnh. Mức độ xác thực phụ thuộc policy của IdP và các tín hiệu phù hợp như `acr`/`amr` trong OIDC (khi được định nghĩa, phát hành và xác minh theo hợp đồng) hoặc `AuthnContext` trong SAML. Nếu tác vụ đòi step-up/MFA, phải yêu cầu và kiểm tra mức xác thực đã đạt được; không tự suy ra chỉ từ việc token là OIDC.

## 11. Lựa chọn theo từng kiến trúc thực tế

### Tình huống A: intranet Java dành cho nhân viên đã join AD domain

**Bối cảnh:** máy trạm join domain, KDC/AD hoạt động nội bộ, browser được quản trị, muốn SSO không yêu cầu user nhập lại password.

- Có thể dùng Kerberos/SPNEGO trực tiếp tại service hoặc qua gateway hỗ trợ Windows Integrated Authentication.
- Nếu tổ chức đã có IdP tích hợp AD/Kerberos, web app mới có thể dùng **OIDC** với IdP và vẫn có trải nghiệm SSO nhờ hạ tầng IdP.
- Không chọn LDAP bind chỉ vì dữ liệu user nằm trong AD khi mục tiêu là “đăng nhập không nhập lại mật khẩu”.

**Phụ thuộc cần làm rõ:** SPN, DNS, browser policy, network đến KDC, keytab, proxy và delegation. Nếu người dùng phải truy cập từ thiết bị ngoài domain, OIDC qua IdP có thể phù hợp hơn, nhưng phải được thiết kế với MFA/conditional access.

### Tình huống B: ứng dụng SaaS doanh nghiệp chỉ nhận SAML

**Bối cảnh:** hệ thống HR SaaS cung cấp SAML metadata và ACS, không có OIDC client registration.

- Tổ chức cấu hình SAML IdP, ký/verify assertion, entity ID/ACS, release attributes và NameID ổn định.
- Nội bộ IdP có thể xác thực user qua AD, LDAP hoặc WebAuthn; SaaS không phải hỗ trợ từng cơ chế upstream.
- Nếu IdP của tổ chức chỉ có OIDC, cần một **federation broker** hỗ trợ hai giao thức và phát hành SAML assertion mới có trust hợp lệ với SaaS. Không thể POST ID Token JSON vào ACS để “thay” SAML XML.

### Tình huống C: SPA/mobile mới + API Spring Boot

**Bối cảnh:** app frontend/mobile đăng nhập qua IdP, backend nhận API call.

- Chọn OIDC Authorization Code + PKCE cho đăng nhập; bảo vệ browser/mobile flow và redirect URI.
- API dùng OAuth2 Resource Server để xác thực **access token** có audience đúng API, hoặc dùng BFF/session server-side để không phơi token cho browser tùy kiến trúc.
- ID Token dành cho OIDC client; API không nhận ID Token như access token.
- App phải liên kết `(iss, sub)` vào user nội bộ, kiểm tra account status, tenant và quyền tài nguyên.

Đăng nhập thành công chưa đủ để duyệt hồ sơ: có thể cần `APP_APPROVE`, scope và kiểm tra record-level ownership.

### Tình huống D: API-to-API giữa các workload trong Kubernetes

**Bối cảnh:** service `billing` gọi `inventory`, không có tương tác người dùng.

- mTLS xác thực workload peer, phù hợp service mesh/PKI nếu tổ chức có nền tảng cấp/rotate certificate.
- Hoặc OAuth2 `client_credentials` lấy access token với audience/scope dành cho `inventory`.
- Có thể kết hợp mTLS và token để vừa bảo vệ kênh vừa có authorization context rõ ràng.
- Không map `client_id=billing` thành một human user `lan`; nếu cần user delegation phải có luồng ủy quyền khác.

**Kết quả mong muốn:** authorization trên service identity, ví dụ `INVENTORY_READ`; mTLS thành công không tự cấp quyền cập nhật tất cả tồn kho.

### Tình huống E: app cũ chỉ hỗ trợ LDAP/password, doanh nghiệp muốn MFA/SSO

**Bối cảnh:** ứng dụng không thể nâng cấp ngay, yêu cầu tài khoản mật khẩu LDAP.

- Không giả định thêm MFA chỉ bằng đổi URL `ldap://` thành `ldaps://`; LDAPS mã hóa đường truyền.
- Tùy sản phẩm, có thể tích hợp identity gateway/proxy/pre-auth hoặc nâng cấp app để dùng OIDC/SAML. Cần chặn đường login cũ bỏ qua gateway nếu triển khai proxy.
- Có thể triển khai lộ trình dual-run và dần ngừng direct password bind sau khi kiểm tra chức năng, account linking và rollback.

**Không nên:** tạo header `X-Authenticated-User` tùy tiện rồi tin đó là OIDC hoặc gọi một HTTPS API bằng Kerberos ticket của service khác.

## 12. Ví dụ Spring Security: mỗi giao thức ở đúng vai trò

Trong Spring Security **Servlet**, các DSL sau thể hiện các vai trò **khác nhau**, không phải một cấu hình duy nhất bật mọi giao thức. Các đoạn dưới đây cần dependency và client/IdP/resource-server registration phù hợp, chưa phải ứng dụng độc lập.

### 12.1. Ứng dụng browser SSO qua OIDC

Dependencies thường dùng với Spring Boot (Gradle, version do Boot quản lý):

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
~~~

~~~java
@Bean
SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Cần khai báo `spring.security.oauth2.client.registration.*` và `provider.*.issuer-uri` cùng redirect URI, client credentials phù hợp. `oauth2Login` thực hiện phiên đăng nhập cho web; **không biến app thành OAuth2 Authorization Server hay REST JWT Resource Server**.

### 12.2. Ứng dụng browser SSO qua SAML 2.0

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-saml2-service-provider")
}
~~~

~~~java
@Bean
SecurityFilterChain samlWebSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Cần cấu hình `RelyingPartyRegistrationRepository`, IdP metadata/certificate, SP entity ID và ACS. Spring Boot có hỗ trợ property `spring.security.saml2.relyingparty.registration.*`. Không trỏ thuộc tính OIDC `issuer-uri` vào SAML metadata rồi kỳ vọng framework tự chuyển giao thức.

### 12.3. REST API nhận OAuth2 JWT access token

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Ngoài issuer/JWK validation mặc định, hãy kiểm tra **audience, token purpose và scope** phù hợp với API. Với opaque token phải cấu hình introspection và sử dụng `opaqueToken`. Không dùng `oauth2Login` thay cho bộ kiểm tra bearer token của API.

**Cảnh báo cấu trúc ví dụ:** ba method `SecurityFilterChain` ở trên được minh họa **độc lập cho ba ứng dụng/biến thể**. Không copy cả ba vào một app mà để `anyRequest()` match mọi URL: Spring Security chọn filter chain đầu tiên khớp, gây route login/ACS/API không được xử lý như mong đợi. Nếu một app cần đồng thời web SSO và API, thiết kế nhiều chain với `securityMatcher`, `@Order`, exception handling và route callback riêng, kiểm thử thứ tự đầy đủ.

### 12.4. LDAP bind trong ứng dụng password-based

Trong ứng dụng yêu cầu direct username/password, LDAP authentication dùng `spring-security-ldap` và một context source; có thể cấu hình `LdapBindAuthenticationManagerFactory` để search DN rồi bind. Đây là **username/password authentication provider**, không phải token verifier cho OIDC/SAML. Không nên bổ sung mã LDAP vào từng controller.

### 12.5. Kerberos và X.509

Kerberos/SPNEGO cần thành phần tích hợp riêng, SPN/keytab và KDC; X.509 cần TLS container/proxy trust policy và mapping principal sau khi certificate đã được xác thực ở đúng boundary. Spring Security có cơ chế X.509/pre-auth và tích hợp Kerberos thích hợp, nhưng không tự cấp certificate, quản lý CA, tạo keytab hay cấu hình domain. Khi TLS kết thúc ở proxy, backend không tự có client certificate gốc.

## 13. Cách liên kết các danh tính khác giao thức vào cùng tài khoản ứng dụng

Giao thức ngoài quyết định **bằng chứng và namespace định danh**; ứng dụng cần một bảng ánh xạ riêng.

Ví dụ cùng một nhân viên Lan:

| Nguồn | Định danh ngoài có thể dùng | Điều kiện trước khi liên kết |
|---|---|---|
| OIDC | Cặp `iss + sub` trong ID Token được xác minh | Client ID/audience đúng, issuer tin cậy, kiểm tra link duy nhất. |
| SAML | `IdP entity ID` + persistent `NameID`/qualifiers hoặc attribute định danh có hợp đồng | Assertion hợp lệ, NameID format/issuer/profile và chính sách ổn định rõ. |
| Kerberos | Principal gồm account/service principal + realm, qua ticket đã xác minh | Kiểm tra realm/trust và principal chuẩn hóa theo policy; tránh trùng giữa realm. |
| LDAP/AD | ID đối tượng ổn định của directory như `objectGUID` với namespace directory | Bind/search đáng tin, schema và directory domain/forest được xác định. |
| X.509 | SAN URI/identity kèm trust domain/issuer/profile, hoặc certificate fingerprint nếu cần ràng buộc một chứng thư | Xác thực TLS/provenance, CA policy, rotation/revocation có kế hoạch. |

Ứng dụng có thể có bảng:

~~~text
internal_users
  id       = usr-1042
  tenant   = company-a
  status   = ACTIVE

external_identity_links
  internal_user_id | scheme   | authority                         | subject
  -----------------+----------+-----------------------------------+-------------------
  usr-1042         | OIDC     | https://idp.example/realm/staff  | 4d1f8a
  usr-1042         | SAML     | https://saml.example/idp         | staff-294
  usr-1042         | KERBEROS | CORP.EXAMPLE                     | lan@CORP.EXAMPLE
~~~

**Không coi các chuỗi `staff-294`, `lan` và `4d1f8a` tương đương chỉ bằng cách giống username/email.** Liên kết nhiều nguồn phải dựa trên enrollment có bằng chứng: quản trị viên cấp link, user chủ động xác minh account hiện tại rồi link IdP mới hoặc quy trình migration được duyệt. Tài khoản nội bộ có thể bị khóa độc lập dù IdP vẫn xác thực được.

### Java 17: mô phỏng ranh giới khóa định danh

Chương trình sau **chạy độc lập với JDK 17**, minh họa vì sao cùng chuỗi username/subject ở các giao thức không tự đồng nghĩa cùng người. Nó **không xác minh token, SAML assertion, Kerberos ticket hay certificate**; các giá trị đầu vào giả định đã qua tầng xác thực đúng giao thức.

~~~java
import java.util.Map;

public class ProtocolIdentityLinkDemo {
    record ExternalKey(String protocol, String authority, String subject) {}

    public static void main(String[] args) {
        Map<ExternalKey, String> links = Map.of(
            new ExternalKey("OIDC", "https://idp.example/staff", "lan"),
            "usr-1042",

            new ExternalKey("SAML", "https://saml.example/idp", "staff-294"),
            "usr-1042",

            new ExternalKey("KERBEROS", "CORP.EXAMPLE", "lan"),
            "usr-2099"
        );

        System.out.println("OIDC: " + links.get(
            new ExternalKey("OIDC", "https://idp.example/staff", "lan")));
        System.out.println("SAML: " + links.get(
            new ExternalKey("SAML", "https://saml.example/idp", "staff-294")));
        System.out.println("KERBEROS: " + links.get(
            new ExternalKey("KERBEROS", "CORP.EXAMPLE", "lan")));
        System.out.println("UNKNOWN: " + links.getOrDefault(
            new ExternalKey("OIDC", "https://other.example", "lan"),
            "UNLINKED"));
    }
}
~~~

Lưu tệp `ProtocolIdentityLinkDemo.java`, sau đó chạy:

~~~bash
javac ProtocolIdentityLinkDemo.java
java ProtocolIdentityLinkDemo
~~~

Kết quả stdout chính xác:

~~~text
OIDC: usr-1042
SAML: usr-1042
KERBEROS: usr-2099
UNKNOWN: UNLINKED
~~~

Kết quả cho thấy một cặp OIDC và một cặp SAML **có thể được link có chủ đích** tới cùng user nội bộ, còn chuỗi `lan` trong realm Kerberos khác vẫn trỏ tới account khác. Một issuer khác dùng `sub=lan` thì **không được** tự ghép vào `usr-1042`.

Trong DB production cần khóa duy nhất cho scheme/authority/subject/tenant, audit việc link và unlink, trạng thái account, giải quyết race condition và giới hạn ai có quyền thực hiện linking.

## 14. “Chuyển giao thức” nghĩa là một trust bridge phát hành bằng chứng mới

Khi bên A chỉ hỗ trợ giao thức X còn bên B chỉ hỗ trợ Y, **không chuyển đổi bằng cách đổi extension hoặc copy claim/header**. Phải có broker/IdP đứng giữa:

~~~text
Windows client -- Kerberos ---> IdP/Broker
                                  |
                                  | xác thực upstream
                                  | map user + policy
                                  | ký OIDC ID Token cho đúng client
                                  v
                              OIDC Web App
                                  |
                                  | local account mapping
                                  v
                            Business session/role
~~~

Hoặc:

~~~text
OIDC Client ---> Federation Broker ---> SAML-only SaaS
                     |
                verify OIDC login
                map namespace/user
                issue new SAML assertion
                audience = SaaS SP
                recipient = SaaS ACS
                sign with trusted SAML key
~~~

Các thành phần bắt buộc:

1. **Trust upstream:** broker kiểm tra đúng ticket/token/assertion/certificate đầu vào, không chỉ parse dữ liệu.
2. **Identity correlation:** ánh xạ đúng user, issuer, tenant và account lifecycle; không tự động link qua email.
3. **Issuer mới:** broker ký/phát hành bằng chứng theo giao thức downstream với audience, expiry, subject, signature/key và assurance phù hợp.
4. **Downstream validation:** ứng dụng đích tin **broker với vai trò issuer được cấp quyền**, không lấy token upstream vốn có audience của hệ thống khác.
5. **Audit, revocation và session:** xác định thời điểm quyền bị thu hồi, token/session TTL, cách quản trị logout và sự cố broker.

Broker giảm số tích hợp trực tiếp, nhưng trở thành **một trust boundary quan trọng**. Cần HA, key rotation, scope/claim filtering và chính sách MFA/step-up riêng. Không tuyên bố “đã có SSO đa giao thức” nếu mới chỉ có endpoint phát header tên user.

## 15. Cây quyết định chọn giao thức

Đi theo trình tự này khi bắt đầu dự án:

1. **Chủ thể đăng nhập là ai?**
   - Nhân viên/bên ngoài sử dụng browser/mobile → xem OIDC/SAML.
   - Máy đã join domain và truy cập intranet được quản trị → xem Kerberos/SPNEGO hoặc OIDC qua IdP.
   - Workload/backend → xem mTLS hoặc OAuth2 client credentials.
   - Thiết bị mạng/VPN → xem EAP/RADIUS/AAA phù hợp.
2. **Đối tượng nhận kết quả là gì?**
   - Web app cần session đăng nhập user → OIDC/SAML.
   - API nhận bearer access token → OAuth2 resource server + audience/scope.
   - Directory cần tìm user hoặc kiểm tra password → LDAP.
   - SaaS cần tạo/khóa account → SCIM provisioning.
3. **Hạ tầng hiện có thực sự hỗ trợ endpoint/protocol nào?**
   - AD DS có LDAP/KDC; không mặc định có OIDC.
   - IdP có thể hỗ trợ OIDC, SAML hoặc cả hai; phải kiểm tra metadata, policy và contract.
   - SaaS có thể chỉ hỗ trợ SAML, SCIM hoặc một subset cấu hình.
4. **Trust boundary nằm ở đâu?**
   - TLS kết thúc ở ứng dụng hay reverse proxy?
   - Ai xác minh chữ ký issuer, certificate chain, SPN/KDC?
   - Có gateway/broker không, assertion được bảo vệ thế nào?
5. **Danh tính ổn định và quyền được xử lý tại đâu?**
   - Chọn khóa namespace-đúng-giao-thức, link sang user nội bộ.
   - Xác định nguồn quyền, tenant và thời hạn cache/session.
6. **Yêu cầu bảo mật/vận hành là gì?**
   - MFA/step-up, logout, offboarding nhanh, revocation, failover, offline, key rotation, audit, thiết bị BYOD.
   - Nếu có yêu cầu không đáp ứng được với hạ tầng hiện tại, bổ sung thành phần thích hợp hoặc thay kiến trúc, không suy diễn giao thức có tính năng mà nó không có.

## 16. Kiểm thử để chứng minh các ranh giới không bị lẫn

| Test case | Kết quả mong muốn |
|---|---|
| LDAP bind thành công nhưng user không có quyền phê duyệt | Xác thực thành công, nghiệp vụ bị từ chối vì thiếu authority. |
| Browser không join domain thử SPNEGO | Có đường fallback login được phê duyệt hoặc từ chối rõ; không coi header tự gửi là Kerberos. |
| Kerberos ticket cho service A gửi tới service B | Không được chấp nhận như bằng chứng của service B. |
| SAML Response issuer không khớp metadata hoặc ACS sai | SP từ chối tại xác minh SAML. |
| SAML assertion được copy/replay sau khi đã dùng | Chặn theo profile và replay protection tương ứng. |
| OIDC ID Token hợp lệ cho client A gửi tới client B | Client B từ chối sai audience. |
| ID Token dùng làm bearer để gọi API | API từ chối do sai token purpose/audience. |
| JWT access token hợp lệ cho API A gửi tới API B | API B từ chối sai audience, không chỉ dựa chữ ký. |
| OAuth2 client_credentials token vào endpoint yêu cầu end-user | Không tự gán user; policy từ chối hoặc yêu cầu delegation khác. |
| SCIM tạo user nhưng chưa có login session | Tài khoản tồn tại, không được coi là đã đăng nhập. |
| Token có email trùng user khác | Không link account nếu không có bước chứng minh/consent theo policy. |
| mTLS user certificate tại proxy, backend chỉ thấy proxy certificate | Backend không nhầm proxy thành end-user; yêu cầu assertion được xác minh. |
| Header `X-User: admin` do client tự gửi | Không gán quyền admin hoặc coi đó là federation. |
| IdP group bị xóa nhưng session chưa refresh | Quyền hết hiệu lực theo TTL/revalidation chính sách. |
| OIDC/SAML issuer đổi hoặc migration tenant | Liên kết phải được đối soát, không tự gộp người dùng bằng username. |
| IdP tạm mất kết nối | Hệ thống fail closed hoặc dùng phiên/cache còn hiệu lực theo chính sách, không bật bypass admin. |

Cần kiểm thử ở **đúng lớp**: kiểm tra TLS tại gateway, kiểm tra token tại authentication provider/resource server, kiểm tra liên kết tại identity mapping, kiểm tra tài nguyên ở authorization. Kết quả “request cuối cùng trả 200” không chứng minh từng lớp đều đúng.

## 17. Lỗi thiết kế và cách tránh

**Lỗi 1 — “AD có LDAP, vậy web app mới cứ dùng LDAP.”** Nếu mục tiêu là SSO cho cả nhân viên nội bộ và đối tác bên ngoài, LDAP direct bind buộc app nhận password, không tự có federation/MFA theo chuẩn web. Có thể để IdP dùng AD upstream và web app nói OIDC/SAML.

**Lỗi 2 — “SAML/OIDC chỉ khác JSON với XML.”** Khác vai trò, profile, signature, audience, session, redirect/binding, response validation và metadata. Chuyển protocol cần issuer/broker mới.

**Lỗi 3 — “API chấp nhận mọi token của IdP.”** Token phải có audience, type, scope, issuer phù hợp **API cụ thể**; sai mục đích dù chữ ký đúng vẫn phải từ chối.

**Lỗi 4 — “Mọi certificate hợp lệ đều là nhân viên hợp lệ.”** CA trust chỉ là một điều kiện; certificate của workload khác người dùng, còn phải mapping account/roles. mTLS với gateway xác thực gateway, không chứng minh end-user gốc.

**Lỗi 5 — “SCIM provisioning đồng nghĩa SSO.”** SCIM tạo/sửa tài khoản; login phải có giao thức/cơ chế khác. Provisioning không phải Authentication.

**Lỗi 6 — “Có MFA vì dùng giao thức hiện đại.”** Cần chính sách IdP và kiểm tra assurance/step-up, không suy từ tên OIDC/SAML.

**Lỗi 7 — “Cứ lấy email làm khóa chung giữa giao thức.”** Email đổi hoặc được tái sử dụng, claim có thể khác issuer. Dùng định danh ổn định theo namespace và quá trình linking được phê duyệt.

**Lỗi 8 — “Backend tin proxy header vì tên header có Verified.”** Nếu backend có thể bị truy cập trực tiếp, header spoofing dẫn đến account takeover. Cần đóng đường bypass, xác minh proxy/trust assertion và chống header duplication.

**Lỗi 9 — “Bật hết `saml2Login`, `oauth2Login`, `httpBasic`, `formLogin` và `jwt` là linh hoạt.”** Nhiều cơ chế xác thực cùng endpoint có thể gây downgrade, credential exposure, chain ordering và hành vi fallback sai. Phải định nghĩa route nào dùng cơ chế nào, có fallback hay không, và kiểm thử threat model.

**Lỗi 10 — “Ứng dụng luôn có thể tự gọi API bằng danh tính user.”** SPNEGO delegation, OAuth2 delegated access, service account và mTLS workload identity là những quy tắc riêng; không tự suy diễn user delegation từ một session hoặc ticket đã được xác thực.

## 18. Checklist quyết định kiến trúc và vận hành

Trước khi chốt giải pháp, nên ghi rõ:

| Câu hỏi | Cần điền thực tế |
|---|---|
| Ai xác thực user/workload? | IdP, KDC, directory, TLS terminator, app hay gateway nào? |
| Hệ thống nào là issuer đáng tin? | OIDC issuer URL, SAML entity ID, Kerberos realm, directory namespace, CA trust domain. |
| Ứng dụng là vai trò gì? | OIDC client, SAML SP, OAuth2 Resource Server, LDAP client, Kerberos service, mTLS server. |
| Giao thức/endpoint được hỗ trợ? | Discovery, JWK, SAML metadata/ACS, LDAP DN/search, SPN/KDC, certificate profile. |
| Dữ liệu định danh ổn định? | `iss+sub`, persistent SAML identifier, directory object ID, realm principal, cert SAN. |
| Quyền nội bộ đến từ đâu? | Group mapping đã phê duyệt, policy service, DB, scope/audience đúng app, row-level rules. |
| MFA/assurance được thực thi ở đâu? | IdP/KDC/app, cách yêu cầu và kiểm tra mức xác thực tại hành động nhạy cảm. |
| Provision/offboarding thế nào? | SCIM/HRIS/event, account disabled, revocation, session invalidation. |
| Biên mạng/ủy nhiệm là gì? | TLS endpoint, gateway provenance, proxy header contract, mTLS identity, delegation/token exchange. |
| Vòng đời vận hành? | Key rotation, metadata refresh, token TTL, clock skew, audit, multi-tenant, failover, rollback. |

Nếu một hàng của bảng còn “không rõ” thì chưa đủ căn cứ để gọi hai giao thức tương đương. Chỉ thay đổi giao thức khi có **phương án di chuyển danh tính, quyền, trust, UX và vận hành** được kiểm tra end-to-end.

## 19. Tổng kết

Một tổ chức có thể cùng lúc sử dụng LDAP cho directory, Kerberos cho intranet Windows, SAML cho SaaS cũ, OIDC cho web/mobile, OAuth2 access token cho API, mTLS cho workload và SCIM cho provisioning. Điều này bình thường vì các giao thức giải quyết **các trách nhiệm khác nhau**.

Mô hình đáng tin cậy là: **chọn giao thức theo chủ thể và hạ tầng → xác minh bằng chứng ở đúng trust boundary → chuẩn hóa định danh có namespace → liên kết đến principal nội bộ → cấp quyền theo policy ứng dụng → quản lý session/token và vòng đời tài khoản**. Khi cần nối hai giao thức, một IdP/federation broker phải phát hành bằng chứng mới đúng audience và hợp đồng trust, không thay thế bằng việc đổi tên token hoặc truyền chuỗi username.

## Tài liệu tham khảo

- [Spring Security — Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/): các cơ chế xác thực theo vai trò ứng dụng, gồm OAuth2 Login, SAML2, X.509 và pre-authentication.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): LDAP bind/search trong password-based authentication.
- [Spring Security — Kerberos/SPNEGO](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): tích hợp Kerberos và SPNEGO khi dùng hệ thống domain phù hợp.
- [Spring Security — SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/IdP, RelyingPartyRegistration, assertion validation và ACS.
- [Spring Security — OAuth2 Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/): vai trò OAuth2 Client, Resource Server và Authorization Server.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification, access token và ánh xạ authorities.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): ID Token, claim `iss/sub` và giới hạn tính duy nhất của các thuộc tính như email.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): mô hình resource owner/client/authorization server/resource server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT cho API.
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): provisioning và quản lý Users/Groups giữa các miền.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705): OAuth2 mTLS client authentication và certificate-bound tokens.
