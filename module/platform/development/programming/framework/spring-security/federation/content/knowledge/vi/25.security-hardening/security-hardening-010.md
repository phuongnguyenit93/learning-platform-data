# Bảo vệ callback, khóa, keytab và endpoint quản trị cấu hình đối tác

## 1. Vấn đề và mục tiêu gia cố

Một ứng dụng **Spring Security - federation** có thể phục vụ đăng nhập thông qua nhiều đối tác: OIDC OpenID Provider, SAML Identity Provider (IdP), CAS Server, Kerberos realm/KDC hoặc một reverse proxy đã xác thực người dùng. Các kết nối này dựa trên ba nhóm tài sản nhạy cảm:

1. **Callback endpoints**: nơi trình duyệt hoặc một server đối tác đưa authorization code, SAMLResponse, CAS ticket, proxy-granting ticket hoặc logout notification về ứng dụng.
2. **Khóa và credentials**: OIDC client secret, private key ký/decrypt của SAML Service Provider, IdP verification certificate, JWKS, Kerberos keytab, TLS private key và các bearer tickets.
3. **Endpoint quản trị cấu hình đối tác**: thay issuer, IdP entityID, cert, token/JWKS/metadata URL, redirect/ACS, SPN/keytab secret reference, group-to-role mappings hoặc chính sách cho từng tenant.

Một lỗi ở callback có thể gây login CSRF, replay, token substitution, account takeover hoặc session confusion. Một keytab/private key bị lộ có thể phá ranh giới chứng thực dịch vụ. Một API quản trị cho phép thay verification certificate hoặc issuer trái phép có thể khiến ứng dụng **tin một IdP do attacker kiểm soát** dù bản thân thư viện xác minh chữ ký hoạt động chính xác.

**Mục tiêu:** phân biệt từng loại callback và credential, thiết kế kiểm tra trust theo giao thức, cất giữ/xoay khóa an toàn, chặn SSRF từ metadata, kiểm soát RBAC/MFA/CSRF/dual approval đối với API cấu hình, triển khai Spring Security theo phạm vi và kiểm thử các trường hợp nguy hiểm bằng ví dụ Java 17.

> **Nguyên tắc cốt lõi:** callback có thể **truy cập được trước khi người dùng có local Authentication**, nhưng phải được **protocol validator** xác minh. Ngược lại, **endpoint sửa cấu hình danh tính** phải là management plane được bảo vệ bằng xác thực và phân quyền quản trị, không có lý do gì public chỉ vì callback là public.

## 2. Mô hình đe dọa và trust boundary

~~~text
Internet / Browser / Untrusted requests
         |
         +--> OAuth2/OIDC callback with code + state
         +--> SAML ACS with SAMLResponse + RelayState
         +--> CAS ST callback with ticket
         |
         v
 Spring Security authentication filters
   - resolve approved ClientRegistration / RelyingPartyRegistration
   - check state/PKCE/nonce or SAML signature/conditions
   - check issuer, audience, recipient, replay, expiry
   - create Authentication only after validation
         |
         v
       Local authorization / business APIs

 CAS Server -- trusted back-channel --> PGT receptor / SLO callback

 Admin / automation -- RBAC + MFA + approval --> Partner Config API
                                |
                                v
                  Immutable DRAFT, validation
                  Metadata fetch sandbox / trust review
                  Separate APPROVAL / ACTIVE versions
                                |
                                v
                 Approved config read by login filters

 Secret store/KMS -- scoped workload identity --> keytab/private keys
~~~

| Điểm vào / tài sản | Nguồn tin cậy chính | Rủi ro quan trọng |
| --- | --- | --- |
| OIDC redirect callback | ClientRegistration + state/nonce/PKCE + verified tokens | Code injection, mix-up, open redirect, login CSRF. |
| SAML2 Assertion Consumer Service | RelyingPartyRegistration + IdP certificate + OpenSAML validation | XML signature wrapping, unsigned assertion, replay, audience mismatch. |
| CAS service ticket callback | CAS Server ticket validation + service binding | Ticket replay, login từ ST của dịch vụ khác. |
| CAS PGT receptor | CAS Server back-channel + inbound trust + IOU correlation | Forged PGT callback, credential leak trong URL. |
| CAS Single Logout | CAS SLO transport trust + SessionIndex→local session | Forged logout hoặc xóa nhầm phiên. |
| Kerberos acceptor | KDC/realm/SPN + keytab + GSS validation | Keytab leak, SPN/KVNO mismatch, downgrade. |
| SAML SP private key | KMS/HSM/keystore được quản trị | Giả danh SP, decrypt thông tin dành cho SP. |
| IdP certificate / OIDC JWKS | Approved issuer metadata, pinned/trusted keys | Chấp nhận cert/key của issuer giả. |
| Partner admin API | Admin identity, least privilege, step-up, dual control | Thay trust anchor, issuer hoặc role mapping tùy ý. |
| Metadata URL fetcher | Approved destinations + egress sandbox + signature review | SSRF, DNS rebinding, XML XXE, auto-trust malicious keys. |

**Không đồng nhất network trust và identity trust.** TLS tới metadata endpoint xác nhận kết nối với host theo hệ thống CA, nhưng không tự cho phép host đó trở thành IdP; signed SAMLResponse đúng cert nhưng thiếu audience cũng không phải ticket dành cho ứng dụng; một admin đã login không mặc nhiên có quyền thay cert của đối tác khác.

## 3. Kiểm kê endpoint và quyền trước khi gia cố

Các URL dưới đây là mặc định/phổ biến với Spring Security Servlet; cấu hình thực tế có thể đổi theo phiên bản và context path.

| Loại | Endpoint ví dụ | Caller | Bảo vệ cần thiết |
| --- | --- | --- | --- |
| OIDC initiation | `/oauth2/authorization/{registrationId}` | Browser | Resolved client registration, tạo state/PKCE/nonce. |
| OIDC callback | `/login/oauth2/code/{registrationId}` | Browser redirect | State/issuer/token checks; không raw code login. |
| SAML initiation | `/saml2/authenticate/{registrationId}` | Browser | Tạo AuthnRequest, lưu correlation. |
| SAML ACS | `/login/saml2/sso/{registrationId}` | Browser HTTP POST | XML signature, conditions, issuer, recipient, replay. |
| SAML metadata public | `/saml2/metadata/{registrationId}` | IdP/browser | Có thể GET public, **chỉ xuất public key/cert**, không có quyền chỉnh. |
| SAML SLO | `/logout/saml2/sso` và variants | Browser/IdP | SAML logout protocol, signature/trust/correlation. |
| CAS ST callback | `/login/cas` | Browser | Validate ST ở CAS Server cho đúng service. |
| CAS PGT receptor | `/login/cas/proxyreceptor` | CAS Server | Inbound machine trust, HTTPS, lưu IOU→PGT. |
| CAS SLO | Endpoint cấu hình cho service | CAS Server hoặc browser theo mode | Back-channel source trust, đúng ST→session. |
| Partner management | `/internal/federation/partners/**` | Admin/automation | MFA, RBAC, tenant, CSRF, two-person approval, audit. |

**Callback khác admin:** người dùng lần đầu login chưa có Spring session nên không thể đòi role admin ở ACS/OIDC callback, nhưng các filter xác thực chuyên dụng phải chạy. Endpoint `/internal/federation/partners/**` phải chặn anonymous và mọi actor thiếu quyền dù họ có tài khoản thông thường.

Khi đổi callback URL phải đồng bộ **Spring registration**, allowlist ở IdP/Authorization Server, reverse proxy public scheme/host, cookie/session correlation và monitoring. Không dùng wildcard redirect URI để “đỡ phải sửa cấu hình”.

## 4. OIDC/OAuth2 callback: state, nonce, PKCE và issuer

### 4.1. Luồng đúng

~~~text
Browser GET /oauth2/authorization/corp
    -> OAuth2AuthorizationRequestRedirectFilter
    -> known ClientRegistration("corp")
    -> generate transaction-specific state, PKCE, OIDC nonce
    -> redirect to trusted authorization endpoint

Authorization Server returns browser redirect:
  GET /login/oauth2/code/corp?code=...&state=...

OAuth2LoginAuthenticationFilter:
    -> load matching authorization request
    -> verify state/correlation and selected provider
    -> exchange code with correct token endpoint + verifier
    -> verify ID Token issuer/audience/signature/expiry/nonce
    -> map verified principal to local account/authorities
    -> create Spring Security Authentication/session
~~~

**`code` không phải chứng cứ đăng nhập đứng một mình.** Nó cần được đổi tại đúng token endpoint của Authorization Server đã chọn trong transaction ban đầu. Cũng không được nhận query `issuer=https://other.example` rồi dùng URL đó tự quyết định issuer/token endpoint/JWKS.

### 4.2. Tách chức năng các biện pháp

| Cơ chế | Điều cần giữ |
| --- | --- |
| `state` | Gắn callback với login transaction/browser, chống login CSRF và nhầm luồng. |
| OIDC `nonce` | Gắn ID Token với authentication request, chống token replay/misbinding trong profile OIDC. |
| PKCE `code_challenge`/`code_verifier` | Chống authorization code injection/theft không có verifier. |
| `iss` / AS mix-up defense | Token/response đúng issuer được phê duyệt, không chuyển provider theo input attacker. |
| `aud`, expiry, signature, alg | Token đúng RP/client và được xác minh bởi approved issuer key. |
| Registered redirect URI | Exact match theo OAuth Security BCP; không có open redirect. |
| Authorization request repository | Tồn tại state/nonce/PKCE transaction context đến callback, kể cả khi multi-node. |

Theo RFC 9700, **public clients bắt buộc PKCE**, confidential clients được khuyến nghị dùng PKCE; client phải chống CSRF trong authorization response, với các cơ chế được tiêu chuẩn cho phép. Không tùy tiện bỏ state/nonce khi chuyển sang multi-provider. **OIDC nonce/PKCE/state có thể hỗ trợ các mục tiêu giao nhau nhưng không là các chuỗi “giống nhau dùng thay được”**.

### 4.3. Multi-IdP và mix-up

Ví dụ:

~~~text
corp issuer:    https://login.corp.example
partner issuer: https://login.partner.example

User bắt đầu login với corp.
Attacker đưa response/code của partner vào callback corp.

Bắt buộc:
  - callback gắn đúng authorization request ban đầu
  - issuer/token endpoint không bị đổi theo query
  - ID Token iss/aud đúng expected registration
  - code/PKCE chỉ dùng trong transaction phù hợp
~~~

Nếu hỗ trợ nhiều Authorization Servers, triển khai **mix-up countermeasure** theo RFC 9700: issuer indication từ response/ID Token/JARM hoặc redirect URI phân biệt khi profile cho phép; không dựa vào một `registrationId` do browser tự sửa để đổi trust.

### 4.4. SameSite, CSRF, redirect và logs

- Browser callback mặc định thường là top-level **GET**; `SameSite=Lax` có thể phù hợp để cookie chứa authorization request đi cùng, tùy browser và cấu hình.
- Với callback **form_post**, SameSite/cross-site cookie khác; phải test cookie policy thực tế.
- Callback OIDC không có CSRF form token truyền thống nhưng có state/nonce/PKCE/correlation theo protocol; **không tắt CSRF toàn ứng dụng**.
- Admin POST dùng browser cookies phải còn CSRF token/Origin checks.
- Không chuyển browser sau login tới `returnUrl`/`next` tùy ý. Ưu tiên đường dẫn nội bộ đã kiểm tra hoặc allowlist đích cụ thể.
- Không ghi raw `code`, `state`, ID/access/refresh tokens, browser cookies trong reverse proxy/APM/application logs.
- Không để attacker kiểm soát callback base URI, Host/X-Forwarded-* headers mà app dùng dựng redirect URI nếu proxy chưa thiết lập trusted forwarded-header boundary.

**Spring Security `oauth2Login().redirectionEndpoint().baseUri(...)` chỉ sửa matcher URL**; muốn tùy biến phải bảo đảm `ClientRegistration.redirectUri` cũng khớp và IdP đã register đúng redirect URI.

## 5. SAML2 ACS: chữ ký XML, audience, correlation và replay

SAML Web SSO thường đưa response qua trình duyệt:

~~~http
POST /login/saml2/sso/partner-a HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<opaque-encoded-xml>&RelayState=<opaque-state>
~~~

Browser **không phải nguồn tin cậy** chỉ vì nó đang POST vào đúng ACS. Spring Security sử dụng `Saml2WebSsoAuthenticationFilter` và OpenSAML authentication provider để nhận/validate theo `RelyingPartyRegistration` đã được duyệt. **Không tự tạo Authentication từ `NameID` hoặc XML parse được**.

### 5.1. Checklist xác thực SAML Response

| Kiểm tra | Vì sao bắt buộc? |
| --- | --- |
| Signed response/assertion | Chỉ chấp nhận cấu trúc XML có chữ ký đúng phạm vi theo profile/trust. |
| Trusted IdP signing certificate | Chữ ký đúng nhưng public key không trusted vẫn không tạo identity. |
| Issuer / asserting party | Phải khớp IdP entityID trong registration được phê duyệt. |
| Destination / Recipient / ACS | Assertion phải được gửi đúng SP endpoint/destination. |
| AudienceRestriction / SP entityID | Token dành đúng relying party, không dùng assertion app khác. |
| InResponseTo/SubjectConfirmation | Gắn assertion với AuthnRequest nếu SP-initiated flow yêu cầu. |
| Conditions: NotBefore, NotOnOrAfter | Không chấp nhận ngoài cửa sổ thời gian + skew được cấu hình. |
| Replay cache | Một Assertion ID/Response ID theo policy không được cấp login hai lần. |
| RelayState policy | Không đổi thành open redirect hay tùy ý khôi phục URL bên ngoài. |
| Parser/size hardening | Chống XXE, entity expansion, XML wrapping và DoS. |

**Chỉ có HTTPS không thể thay signature**, vì browser có thể gửi bất kỳ SAMLResponse qua một TLS connection hợp lệ. Không tắt yêu cầu audience/subject confirmation/in-response-to để tránh lỗi integration.

### 5.2. Ký khác mã hóa

- **IdP signing private key**: thuộc IdP, ký assertion/response.
- **IdP verification certificate**: SP giữ public cert đã được phê duyệt để xác minh chữ ký từ IdP.
- **SP signing private key**: SP dùng để ký AuthnRequest/LogoutRequest khi profile yêu cầu.
- **SP decryption private key**: SP dùng để giải mã EncryptedAssertion/EncryptedAttribute được mã hóa cho SP.
- **SP encryption public cert**: IdP dùng để mã hóa dữ liệu dành SP.
- **TLS private key**: bảo vệ HTTPS, không mặc nhiên đồng nhất với signing/decryption key.

Một SAML assertion có thể **được mã hóa nhưng chưa có chữ ký đáng tin**; mã hóa không tự chứng minh issuer. Ngược lại, response được ký đúng nhưng khai `AudienceRestriction` dành cho app khác cũng phải bị từ chối. Tùy trường hợp, thứ tự signature verification/decryption trong OpenSAML rất quan trọng; đừng thay decrypter tùy tiện mà bỏ validation.

### 5.3. ACS POST và ngoại lệ CSRF

IdP POST không có form CSRF token của RP nên hệ thống có thể cần **CSRF ignore ở đúng SAML ACS endpoint** theo tích hợp Spring Security. Đó không phải `csrf.disable()` toàn web app. Phải đảm bảo:
- ACS đi qua đầy đủ Spring Security filters và OpenSAML validators.
- Matcher CSRF exemption đúng path/method, không bao trùm `/internal/federation/**`.
- Các action quản trị vẫn đòi CSRF/Origin, MFA và RBAC.
- SAML SLO có profile riêng; không coi mọi POST XML dưới `/login/**` đều hợp lệ.

### 5.4. Metadata trust không tự phát sinh từ HTTPS fetch

Metadata IdP thường chứa entityID, SSO/SLO endpoints, verification certs và bindings. Lưu ý Spring `OpenSaml5AssertingPartyMetadataRepository` có thể dùng **verificationCredentials** để kiểm tra metadata XML signature; **khi không cấu hình verification credentials, repository này không thực hiện metadata signature validation** theo tài liệu.

Do đó:
- Bootstrap IdP entityID/trust anchor qua phê duyệt đối tác.
- Nếu có signed metadata, xác minh với **approved metadata signing cert** đã tin.
- Nếu không, dùng fingerprint/out-of-band approval và staged key rotation.
- Không “tự chấp nhận cert mới” chỉ vì nội dung vừa tải từ một URL HTTPS.
- Metadata URL là đầu vào cần chống SSRF/XXE, kể cả khi người nhập có role admin.

## 6. CAS: ba callback khác mục đích

### 6.1. Browser mang Service Ticket

~~~text
Browser -> GET /login/cas?ticket=ST-...
Portal -> CAS /serviceValidate or /proxyValidate
CAS Server verifies ticket against exact service URL
Portal accepts principal only on successful validation
~~~

ST là **one-time, service-bound ticket**. Không login chỉ vì request có query `ticket`, không dùng ST cho service khác, không replay ST sau validation. Spring `CasAuthenticationFilter` và provider/validator theo phiên bản xử lý cơ chế này. CAS server URL và `ServiceProperties.service` phải nhất quán qua reverse proxy.

### 6.2. Proxy-granting ticket receptor

Khi CAS Proxy được bật, CAS Server có thể gửi HTTPS GET:

~~~http
GET /login/cas/proxyreceptor?pgtId=PGT-opaque&pgtIou=PGTIOU-opaque HTTP/1.1
Host: portal.example.org
~~~

- `pgtId` là **bearer credential**, phải giữ bí mật.
- `pgtIou` là khóa tương quan; CAS ticket validation response trả IOU, **không trả PGT thật** trong callback flow chuẩn.
- Receptor lưu IOU→PGT, sau đó validator tra đúng IOU để gắn PGT với principal đã xác thực; **không dùng username/latest timestamp** để ghép.
- Callback là server-to-server, **không có browser JSESSIONID**.
- CAS Server kiểm tra HTTPS certificate của receptor khi gửi PGT, nhưng **receptor phải bảo vệ inbound trust riêng** bằng mTLS/allowlisted gateway/network controls tương ứng.
- Receptor chỉ ACK sau khi lưu thành công vào store chung khi nhiều nodes; nếu store timeout, không phát 200 “giả thành công”.
- Redact `pgtId`, `pgtIou`, `pgt` khỏi query logs ở gateway, APM và backend.

### 6.3. CAS Single Logout

CAS có thể gửi `logoutRequest` để hủy phiên ứng dụng. Trong CAS SLO, `SessionIndex` thường liên hệ service ticket ID dùng để tìm HttpSession local, **không dùng username để xóa mọi phiên**.

Không suy từ hình thức XML dùng SAML namespace rằng CAS logoutRequest là SAML 2.0 signed SLO message. Cần trust transport/source phù hợp CAS, `SingleSignOutFilter`/session mapping đúng phiên bản, idempotency và protection chống forged callbacks. Khi callback đến trễ/thất lạc, app session có thể còn sống; SLO là **best effort**, cần TTL/revocation/audit.

## 7. Kho khóa và credential: phân quyền rõ vai trò

| Credential | Ai được giữ bí mật? | Cần bảo vệ thế nào? |
| --- | --- | --- |
| OIDC client secret | OAuth RP và Authorization Server | Secret manager, rotate/revoke, không đưa frontend. |
| private_key_jwt client-auth private key | OAuth Client | KMS/HSM, signed auth, publish approved public key. |
| OIDC issuer JWT signing private key | Authorization Server | Không chia sẻ private key cho RP; RP dùng trusted public JWKS. |
| SAML SP signing private key | SP | KMS/keystore, non-exportable khi phù hợp, role tách biệt. |
| SAML SP decryption private key | SP | Lưu đủ thời hạn cần giải mã in-flight encrypted assertions khi rotation. |
| SAML IdP verification certificate | Public cert được SP trust | Pin/approve theo entityID và signing role; không auto trust. |
| HTTPS TLS private key | Ingress/service endpoint | Certificate chain/hostname, rotation riêng, không mặc định dùng cùng SAML key. |
| Kerberos keytab | Kerberos acceptor có SPN | Read-only secret mount, file ACL, KVNO/enctype/realm. |
| CAS PGT/ST/PT | CAS và parties tương ứng | Bearer secret, TTL/one-time semantics, log redaction. |
| Keystore/KMS access credentials | Approved workloads | Scoped workload identity, audit secret read/use/rotation. |

**Public JWKS hoặc SAML metadata có thể chứa public key/certificate để verify/encrypt. Không được chứa private key, JWK private members, keytab hay client secrets.**

### 7.1. Thực hành secret management

1. Dùng **workload identity**, không chia sẻ một service-account secret cho mọi pods.
2. Cấp quyền theo environment/tenant/partner/key purpose; chỉ SP cần decryption key mới có quyền đọc.
3. Dùng KMS/HSM và secret vault có audit lifecycle: tạo, dùng, rotate, revoke, expire.
4. Không commit keytab/private key vào Git, CI artifact, Kubernetes ConfigMap, Docker image layer, bug report hoặc tài liệu.
5. Secrets trong environment variables có thể lộ qua logs/process diagnostics; ưu tiên phương thức cung cấp do nền tảng bảo vệ và quản lý runtime memory.
6. Khi mount file secret, đặt owner/group/mode nhỏ nhất, read-only và container least privilege; bảo vệ backup và crash dumps.
7. Không cho actuator `/env`, `/configprops`, heap dumps, debug pages hoặc admin config download tiết lộ credentials.
8. Không log raw `Authorization`, `Cookie`, SAMLResponse, OIDC codes/tokens, CAS tickets, PGT, keytab hoặc PEM private keys.
9. Thiết lập owner, expiration dates, rotation windows, peer change notifications và emergency revocation playbook.

**Kubernetes Secret base64 không tự là an toàn**: cần RBAC, etcd encryption, kubelet/pod access control, secret backup retention và service identity policy.

## 8. Xoay khóa SAML, JWKS và client credentials

### 8.1. Mỗi chiều có thời điểm chuyển khác nhau

- **IdP ký, SP verify**: IdP công bố/public cert mới trước khi ký bằng private key mới; SP chấp nhận tập **approved** certs trong khoảng overlap; sau đó retire cert cũ đúng thời hạn hoặc revoke ngay nếu compromise.
- **SP ký, IdP verify**: SP công bố public signing cert mới, đối tác cập nhật trust, rồi SP chuyển sang private key mới. Không chuyển ký trước khi đối tác sẵn sàng.
- **IdP encrypt, SP decrypt**: SP publish encryption public cert mới, đồng thời có thể cần giữ old decrypt private key có kiểm soát để xử lý assertions đang in flight.
- **OIDC/JWT signing**: AS publish public JWK mới trong trusted JWKS, dùng key ID/algorithm phù hợp rồi mới ký bằng key mới; RP refresh cache theo policy, giữ old verify key đủ cho tokens còn hiệu lực trừ compromise.
- **OIDC client secret**: rotate ở Authorization Server + RP runtime secret store, có overlap nếu provider hỗ trợ, tránh downtime và revoke secret cũ sớm khi hoàn tất.

### 8.2. Một lịch rotation an toàn

~~~text
Inventory active partner version and cryptographic key roles
  -> Generate new key (KMS/HSM or approved key service)
  -> Publish public verification/encryption material
  -> Confirm counterpart readiness and trusted metadata
  -> Stage new config as immutable DRAFT
  -> Independent reviewer checks issuer/cert/fingerprint/expiry
  -> Run partner integration test + canary
  -> Atomically activate new version
  -> Monitor issuer/signature/JWKS/KVNO failures
  -> Retire old key after the agreed overlap
  -> Audit and update incident response records
~~~

Cửa sổ overlap phụ thuộc assertion/token lifetime, clock skew, cache refresh, callback in-flight và contract. **Không cố giữ compromised old key để giữ availability.** Khi nghi lộ phải đánh giá emergency disable/revocation, kể cả gây gián đoạn.

### 8.3. OIDC JWKS và JWT alg confusion

- `kid` **chỉ là selector** trong keys thuộc **issuer/JWKS endpoint đã approved**. Một `kid` mới không làm key trở nên trusted.
- `alg` phải thuộc allowlist theo issuer/client, không cho thuật toán `none` hoặc HS/RS confusion trái profile.
- Không fetch `jku`/`x5u` lấy từ JWT header tùy ý để tự chọn key.
- Bảo vệ HTTPS/DNS của JWKS endpoint, giới hạn response size, timeouts, cache failure.
- Token phải được xác minh issuer/audience/expiry và các claims theo giao thức; **signature đúng chưa đủ** nếu token dành app khác.

## 9. Kerberos keytab: SPN, KVNO, file permissions và multi-node

Với HTTP Negotiate, một web service thường dùng:

~~~text
Public URL:   https://portal.example.org
Kerberos SPN: HTTP/portal.example.org@CORP.EXAMPLE.ORG
Keytab:       /etc/security/keytabs/portal-http.keytab
~~~

**`HTTP/` là Kerberos service class, không có nghĩa chấp nhận HTTP cleartext.** Người dùng nên dùng HTTPS để bảo vệ cookies và token exchange. Kerberos service ticket cho public host phải được accept bằng key tương ứng trong keytab của service.

### 9.1. Quy tắc keytab

- SPN phải gắn **đúng service account**, không duplicate SPNs hoặc alias sai.
- Keytab chứa secret dài hạn; không publish/download qua admin UI hoặc tài liệu.
- Mount read-only, chặn anonymous pod/host access, quản lý filesystem ACL và container privileges.
- Kiểm tra **Key Version Number (KVNO)**, encryption types và realm khi rotate account password/key.
- Nhiều pods cùng accept `HTTP/portal.example.org` cần keys đúng với tickets mới trong rollout; test từng node và failover.
- Không đưa keytab vào Git, container image, trace, stdout hoặc startup debug logs.
- Clock skew/KDC DNS/realm trust phải theo Kerberos policy; không disable GSS validation vì lỗi KVNO.
- Khi keytab nghi lộ, rotate service-account key qua KDC/AD, phát keytab mới, revoke old key, đánh giá impact tới sessions.
- Nếu proxy terminate Kerberos rồi gắn principal header, Spring phải bảo vệ trusted gateway/strip spoofed headers; mô hình này **khác** việc Spring tự xác minh GSS ticket.

### 9.2. Các lỗi vận hành

| Dấu hiệu | Nghi vấn | Cần kiểm tra |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` | Keytab sai SPN/account/KVNO, duplicate SPN. | KDC registry, service account và key material version. |
| `KRB_AP_ERR_SKEW` | Đồng hồ lệch. | NTP KDC/client/server, không tắt time checks. |
| Service principal unknown | KDC không có `HTTP/public-fqdn`. | DNS canonicalization, SPN registration. |
| Pod A login được, B lỗi | Keytab rollout lệch version/credential. | Secret mounts, KVNO/enctype và rollout policy. |
| Browser không gửi `Authorization: Negotiate` | Browser trust/SSO policy chưa cho phép. | Domain/KDC/TGT, URL allowlist, không bật Basic tùy tiện. |
| NTLM được accept dù policy Kerberos-only | SPNEGO fallback chưa bị hạn chế. | Kiểm tra mechanism được GSS chọn và OS policy. |

## 10. Mặt phẳng quản trị cấu hình đối tác: bảo mật cao hơn user login

Admin config endpoint có thể tác động tới:
- OIDC issuer, client ID, redirect URI, authorization/token/JWKS URLs, client secret reference.
- SAML IdP entityID, ACS/SLO URL, verification certs, metadata source, signing/decryption keys.
- CAS Server URL, service identifier, PGT receptor URL, logout delivery.
- Kerberos realm/SPN/keytab references.
- Attribute/claims mapping, trusted groups/roles, default authorities và tenant memberships.

**Ai có quyền đổi trust anchor hoặc map external group thành local admin có thể kiểm soát việc xác thực và phân quyền của rất nhiều người dùng.** Vì vậy một role “người quản trị nội dung” thông thường không được sở hữu quyền này.

### 10.1. Tách quyền theo thao tác

| Quyền | Hành động |
| --- | --- |
| `federation:read` | Xem partner status/metadata đã che secret, audits, expiry; không được xem private key/keytab. |
| `federation:propose` | Tạo immutable config draft. |
| `federation:validate` | Chạy validators/metadata fetch sandbox và integration tests. |
| `federation:approve` | Independent approval sau kiểm tra issuer/cert/tenant. |
| `federation:activate` | Kích hoạt config version đã approved. |
| `federation:rotate-secret` | Gọi quy trình KMS/vault được ủy quyền; không tải raw key. |
| `federation:emergency-disable` | Thu hồi trust relationship khi compromise. |

Không chỉ kiểm tra HTTP `hasRole('ADMIN')`: service layer phải kiểm tra **tenant ownership, draft version, presenter/reviewer khác nhau, fresh MFA/step-up và đúng scope của thao tác**. Approver không được tự duyệt draft do mình tạo nếu chính sách yêu cầu dual control.

### 10.2. State machine cấu hình

~~~text
DRAFT
  | schema, URL, issuer, cert, algorithm, risk validation
  v
VALIDATED
  | independent reviewer + fresh MFA + change ticket
  v
APPROVED
  | compare-and-swap version + canary + atomic publish
  v
ACTIVE
  |
  +-- ROLLBACK to an earlier approved and still-secure version
  +-- EMERGENCY DISABLE when compromise is suspected
~~~

Không để request JSON tự chứa `status=APPROVED`, `approvedBy=security-team` hoặc `isAdmin=true` rồi ghi DB. Approval phải là một action có **xác thực thật**, có time/actor/policy checks và audit.

### 10.3. Quản trị nhiều nodes và giao dịch login đang diễn ra

Cấu hình phải có version immutable. Khi một login transaction OIDC/SAML bắt đầu ở version 6 rồi admin activate version 7:
- Lưu transaction context của đăng nhập ban đầu.
- Không lấy một JWKS/issuer “mới nhất” để kiểm tra callback cũ nếu không thuộc policy approved overlap.
- Không trộn issuer cũ, token endpoint mới và cert mới trong một registration không nhất quán.
- Atomic publish hoặc versioned cache invalidation cho pods.
- Optimistic lock/expectedVersion khi nhiều người activate đồng thời.
- Rollback **nguyên config version**, không ghi đè lẻ từng field.
- Không rollback về compromised key/issuer chỉ để giảm lỗi đăng nhập.

## 11. Metadata fetcher: SSRF và XML XXE

Admin có thể nhập một metadata URL tưởng như vô hại:

~~~text
https://idp.partner.example/metadata
~~~

Nhưng server sau đó trở thành HTTP client truy cập URL này. Nếu không bảo vệ, URL có thể trỏ tới private services, Kubernetes APIs hoặc cloud instance metadata. Kể cả hostname ban đầu hợp lệ, **DNS rebinding hoặc HTTP redirect** có thể đưa request đến địa chỉ nội bộ.

### 11.1. Các trường hợp phải chặn

- Loopback `127.0.0.1`, `::1`, localhost aliases.
- Link-local/cloud metadata như `169.254.169.254`.
- Private IPv4/IPv6, Kubernetes cluster DNS/service, nội bộ mạng quản trị.
- URL có userinfo, encoded host, scheme/port không cho phép, redirects tới internal IP.
- DNS A/AAAA thay đổi giữa check và actual connect.
- Response cực lớn/chậm, quá nhiều redirects, recursive metadata, lạm dụng parsing.
- XML DOCTYPE/external entities/XXE, DTD/network fetch, entity expansion.
- Metadata signed bằng cert **chưa approved** hoặc declaring issuer khác expected entityID.

### 11.2. Biện pháp phòng vệ nhiều lớp

1. Prefer exact **approved partner hostname/metadata path** hơn generic “admin có thể nhập URL bất kỳ”.
2. Chỉ cho HTTPS, verify TLS chain/hostname; cấm userinfo và các URL forms bất thường.
3. Resolve/check tất cả IPs ngay tại connect, chặn private/loopback/link-local/metadata IP cho cả IPv4/IPv6.
4. Chống DNS rebinding bằng connector/egress proxy hoặc IP pinning cùng connection policy; **không chỉ DNS check một lần rồi HTTP client lookup lại**.
5. Không tự follow redirects; nếu bắt buộc, phải kiểm tra lại mọi hop và vẫn chỉ trong approved destinations.
6. Egress firewall/service mesh policy chỉ cho host/service cần, chặn internal/cloud metadata.
7. Giới hạn read/connect timeouts, response size, XML depth, concurrent fetches.
8. XML parser hardening: disable DTD/external entity, không tải external schemas, chống XXE.
9. Sau khi fetch: verify expected issuer/entityID, metadata signature nếu profile có approved signer, cert fingerprints/validity và allowable algorithms/bindings.
10. Không tự activate cert mới chỉ vì metadata hợp lệ về mặt XML hoặc tải qua HTTPS; cần staged approval/trust bootstrap.
11. Audit URL ref và metadata content hash, không log raw secret.

**Kiểm tra URI host trong Java một lần chỉ là lớp preliminary.** Khi làm production, cần một dedicated metadata-fetch service có **egress deny-by-default**, DNS/connect/redirect checks và tài liệu trust activation riêng.

### 11.3. Trust bootstrap cho signed metadata

Spring Security có hỗ trợ metadata signature verification khi cung cấp verification credentials đúng cho `OpenSaml5AssertingPartyMetadataRepository`. Nếu không có approved metadata signing keys, không có cơ sở chứng minh “metadata này được đối tác đã được trust ký”.

Một quy trình bootstrapping tốt:
1. Xác nhận đối tác bằng kênh hợp đồng/được duyệt.
2. Kiểm tra entityID, TLS endpoint và approved trust fingerprint.
3. Lưu trust anchor/fingerprint trong registry versioned.
4. Mỗi lần refresh metadata đối chiếu signer, expiry, issuer và change policy.
5. Nếu cert đổi ngoài lịch, giữ config approved cũ hoặc fail closed, cảnh báo review.
6. Chỉ sau approval mới đưa verification credentials vào active Spring registration.

## 12. Mẫu Spring Security tách admin plane và callback plane

Mẫu Spring Boot Servlet sau chỉ bảo vệ **API quản trị**; **không** cài đặt OAuth2/SAML/CAS callbacks, KMS, metadata fetcher hay MFA trong cùng đoạn code.

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FederationAdminSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/internal/federation/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/internal/federation/**")
                    .hasAuthority("federation:read")
                .requestMatchers(
                    HttpMethod.POST, "/internal/federation/**")
                    .hasAuthority("federation:manage")
                .requestMatchers(
                    HttpMethod.DELETE, "/internal/federation/**")
                    .denyAll()
                .anyRequest().denyAll());
        // CSRF is NOT disabled; browser sessions must remain protected.
        // Admin authentication and fresh-MFA checks live elsewhere.
        return http.build();
    }
}
~~~

Đây là **mảnh cấu hình** cần Spring Security/Servlet dependencies; không phải ứng dụng Java SE tự chạy. Một ứng dụng thực phải có:
- Chain khác cho OIDC/SAML/CAS login/callbacks với `ClientRegistrationRepository` hoặc `RelyingPartyRegistrationRepository` đã approved; thứ tự/matchers không được chồng lấn sai.
- Admin Authentication (enterprise OIDC hoặc machine mTLS), independent step-up policy.
- Method/service authorization, tenant scoping, 2-person approval và version compare-and-swap.
- CSRF protection trên admin browser POST, CORS allowlist, rate limiting, request size limit.
- Strict metadata fetch/egress service, secrets manager và audit không lộ data.
- Mã nguồn Spring Security/API cần được đối chiếu version đang dùng (6/7, Jakarta Servlet).

**Không dùng `web.ignoring()` để loại callback khỏi toàn bộ SecurityFilterChain.** Tùy protocol, `permitAll` ở callback có thể cho filter xử lý trước khi có local Authentication; callback vẫn cần validators. Không thêm `csrf.disable()` toàn app chỉ vì SAML ACS dùng POST.

### 12.1. Lớp policy bắt buộc ngoài HTTP matcher

~~~text
propose(actor, tenant, draft):
  require actor has federation:propose for tenant
  require verified login and fresh MFA for risk-level
  validate schema and metadata target, no raw private key
  persist immutable DRAFT + expected active version

approve(reviewer, draft):
  require reviewer has federation:approve for tenant
  require reviewer != proposer
  require metadata issuer/key material verified
  record signed approval decision and timestamp

activate(operator, draft):
  require operator has federation:activate for tenant
  require APPROVED + healthy canary
  require expectedVersion == currentVersion
  atomically publish entire config, KMS key references only
  audit before/after version and rollback pointer
~~~

**Không cho người dùng đổi issuer/JWKS/cert bằng query parameter từ callback**, và không để một service account quá quyền vừa tạo vừa phê duyệt vừa activate nếu chính sách yêu cầu separation of duties.

## 13. Cấu hình đối tác qua một bản nháp versioned

Ví dụ thiết kế nội bộ (không phải cấu hình Spring thực tế):

~~~json
{
  "partnerId": "partner-a",
  "tenantId": "finance-vn",
  "protocol": "SAML2",
  "idpEntityId": "https://idp.partner.example/saml",
  "metadataUrl": "https://idp.partner.example/metadata",
  "metadataSignerRef": "kms://trust/partner-a-metadata",
  "verificationCertRefs": [
    "secrets://partner-a/saml-verification-current"
  ],
  "allowUnsignedAssertions": false,
  "requireAudienceRestriction": true,
  "requireRequestCorrelation": true,
  "allowUnsolicitedSso": false,
  "replayStoreRef": "internal-replay-store",
  "spSigningKeyRef": "kms://sp/finance-vn/signing",
  "status": "DRAFT",
  "version": 7,
  "changeRequestRef": "chg-2026-1107"
}
~~~

Các `kms://` và `secrets://` trong JSON là **references tượng trưng**, không phải secret hay URL thực. API không được chấp nhận chính `status` trong JSON như authority của người gửi: trạng thái DRAFT/APPROVED/ACTIVE là do business workflow quyết định. Không cho upload PEM private key qua JSON endpoint thông thường; nếu cần import thực, dùng một quy trình chuyên biệt được kiểm soát.

## 14. Runtime hardening, logs và audit

### 14.1. Hệ thống nhiều node

- Chia sẻ/đồng bộ session state, OIDC authorization request state, SAML replay cache và CAS PGT IOU storage theo consistency requirements.
- Atomic consume với TTL phù hợp; không để Node A accept SAML assertion rồi Node B accept lại do cache local.
- Pin hoặc resolve đúng partner config version được approved; không xử lý callback bằng tổ hợp issuer cũ/JWKS mới.
- NTP cho SAML Conditions, OIDC exp/iat và Kerberos skew.
- Multi-node keytab/decryption key rollout đồng nhất theo key rotation plan.
- Nếu store/revocation service lỗi, không fail-open chỉ vì làm tăng login success rate.
- Reverse proxy giữ đúng Host/scheme/ACS/redirect URI, chỉ trust forwarded headers từ proxy được cấu hình.
- Public callback paths có rate limiting, request size limits và safe error responses; admin routes có network-level controls.

### 14.2. Không log credentials trong bất kỳ tầng nào

Cần redact:
- OAuth `code`/`state`/`id_token`/`access_token`/`refresh_token`.
- SAML `SAMLResponse`/`RelayState` khi nhạy cảm và XML attributes có PII.
- CAS `ticket`/`pgtId`/`pgtIou`/`pgt` trong URLs.
- `Authorization`, `Cookie`, `Set-Cookie` và Kerberos `Negotiate` tokens.
- PEM private keys, keystore passwords, keytab, JWK private members.
- API admin config JSON nếu nó mang secret reference policies.
- Credentials trong debug exception, JVM heap dumps, CI logs và backups.

Thay bằng correlation IDs hoặc HMAC references (với audit secret riêng), và reason codes như `SAML_AUDIENCE_MISMATCH`, `OIDC_STATE_MISMATCH`, `METADATA_FETCH_BLOCKED`.

### 14.3. Metrics hữu ích

~~~text
federation_callback_received_total{protocol,partner}
federation_callback_rejected_total{protocol,reason}
federation_oidc_state_mismatch_total{partner}
federation_saml_signature_invalid_total{partner}
federation_saml_replay_rejected_total{partner}
federation_cas_pgt_callback_failed_total{service}
federation_key_rotation_failed_total{partner,key_role}
federation_secret_expiry_days{partner,key_role}
federation_admin_change_total{action,outcome}
federation_metadata_fetch_blocked_total{reason}
federation_active_config_version{partner}
~~~

Đừng dùng raw user identifiers, tickets, JWT, IPs hoặc unbounded input làm metric labels (high cardinality và rò data). Alert khi signature fail tăng sau cert rotation, khi admin config activation không có approval hoặc metadata fetch cố truy cập internal network.

### 14.4. Audit event

~~~text
event=FEDERATION_PARTNER_ACTIVATION
time_utc=2026-11-07T09:00:00Z
partner_ref=partner-a
tenant_ref=finance-vn
from_version=6
to_version=7
proposer_ref=ops-17
reviewer_ref=security-42
mfa_step_up_validated=true
trust_material_reviewed=true
metadata_hash_ref=sha256:...
decision=ACTIVATE
result=SUCCESS
correlation_id=change-17
~~~

Đây là audit schema minh họa; hệ thống cần bảo vệ audit khỏi xóa/sửa trái phép, quyền xem theo policy, data minimization và retention. **Audit không thay biện pháp ngăn chặn.**

## 15. Kế hoạch ứng phó khi khóa hoặc trust bị compromise

### 15.1. IdP signing certificate mới bất thường

1. Kiểm tra signed metadata và fingerprint qua kênh đã approved, không tự tin URL mới.
2. Stage version; giữ current trusted certs nếu chưa compromised và policy cho phép.
3. Cùng đối tác xác nhận rotation timeline và overlapping verification window.
4. Dùng canary SAML actual login, wrong audience và replay tests.
5. Nếu cert bị lộ/đổi trái phép, **revoke trust** chứ không chỉ bổ sung cert mới vào allowlist.
6. Báo cáo các logins/account changes có thể đã bị ảnh hưởng.

### 15.2. OIDC client secret rò rỉ

- Thu hồi/rotate tại Authorization Server, thay reference trong secret store và deploy.
- Tìm leak trong Git, pipeline logs, CI artifacts, config snapshots, tickets.
- Xem bất thường token endpoint/refresh token usage và giới hạn overlap.
- Việc đổi client secret không tự vô hiệu hóa mọi access token đã phát: cần token/session revocation theo architecture.
- Thêm policy ngăn secrets vào logs/source sau sự cố.

### 15.3. Kerberos keytab rò rỉ

- Cô lập workload/host, xác định SPN, account và environment bị ảnh hưởng.
- Rotate service account key tại KDC/AD, cập nhật keytab/KVNO cho pods.
- Theo dõi SPN mismatch và failover, không “rollback” keytab đã compromise.
- Đánh giá active web sessions và Kerberos tickets theo thời hạn/quy tắc revoke.
- Thu hồi bản keytab trong image/log/backups theo incident playbook.

### 15.4. API quản trị bị chiếm quyền

- Freeze/disable đối tác bị thay đổi và khóa admin credentials/automation tokens liên quan.
- So diff các trường issuer, metadata URL, verification certs, JWT algorithms, role mappings, ACS/redirect endpoints.
- Chỉ rollback sang **approved, uncompromised** version, hoặc fail closed nếu không có.
- Đối chiếu audit actor/reviewer/step-up/canary; điều tra tài khoản, permissions và sessions tạo trong thời gian compromise.
- Rà soát SSRF/secret reads từ backend egress và error logs.

## 16. Java 17 runnable: mô phỏng callback trust và dual approval

Chương trình độc lập dưới đây không dùng Spring hay network. Nó mô phỏng **điều kiện an ninh đã được verifier thật xác nhận** và logic quản trị config. **Không** được đưa những boolean `signatureVerified`, `issuerTrusted`, `stepUpVerified` từ request JSON vào production.

Tệp **`FederationBoundaryDemo.java`**:

~~~java
import java.net.URI;

public final class FederationBoundaryDemo {

    record Callback(
        String protocol,
        boolean issuerTrusted,
        boolean correlationValid,
        boolean cryptoValid,
        boolean audienceValid,
        boolean replaySeen) {}

    static String verifyCallback(Callback c) {
        if (!c.issuerTrusted()) return "DENY_ISSUER";
        if (!c.correlationValid()) return "DENY_CORRELATION";
        if (!c.cryptoValid()) return "DENY_CRYPTO";
        if (!c.audienceValid()) return "DENY_AUDIENCE";
        if (c.replaySeen()) return "DENY_REPLAY";
        return "ACCEPT_" + c.protocol();
    }

    record Change(
        boolean operatorAuthorized,
        boolean recentMfaVerified,
        String proposer,
        String reviewer,
        String metadataUrl,
        boolean trustReviewed) {}

    // Demonstration of preliminary URI policy, NOT SSRF protection.
    static boolean approvedMetadataUrl(String value) {
        try {
            URI uri = URI.create(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                && "idp.partner.example".equalsIgnoreCase(uri.getHost())
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getPort() == -1
                && "/metadata".equals(uri.getRawPath());
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    static String review(Change change) {
        if (!change.operatorAuthorized()) return "DENY_ADMIN_RBAC";
        if (!change.recentMfaVerified()) return "DENY_STEP_UP";
        if (change.proposer().equals(change.reviewer()))
            return "DENY_SELF_APPROVAL";
        if (!approvedMetadataUrl(change.metadataUrl()))
            return "DENY_METADATA_URL";
        if (!change.trustReviewed()) return "DENY_KEY_REVIEW";
        return "APPROVED_DRAFT";
    }

    static final class ConfigRegistry {
        private long version = 1;

        synchronized String activate(long expectedVersion, String approval) {
            if (version != expectedVersion) return "DENY_VERSION_CONFLICT";
            if (!"APPROVED_DRAFT".equals(approval))
                return "DENY_UNAPPROVED";
            version++;
            return "ACTIVE_VERSION_" + version;
        }

        synchronized long version() { return version; }
    }

    public static void main(String[] args) {
        System.out.println("OIDC_OK=" + verifyCallback(
            new Callback("OIDC", true, true, true, true, false)));
        System.out.println("OIDC_STATE=" + verifyCallback(
            new Callback("OIDC", true, false, true, true, false)));
        System.out.println("SAML_SIGNATURE=" + verifyCallback(
            new Callback("SAML", true, true, false, true, false)));
        System.out.println("SAML_REPLAY=" + verifyCallback(
            new Callback("SAML", true, true, true, true, true)));
        System.out.println("CAS_UNTRUSTED=" + verifyCallback(
            new Callback("CAS", false, true, true, true, false)));

        Change approved = new Change(true, true, "ops-a", "security-b",
            "https://idp.partner.example/metadata", true);

        System.out.println("NO_MFA=" + review(new Change(
            true, false, "ops-a", "security-b",
            "https://idp.partner.example/metadata", true)));
        System.out.println("SELF_REVIEW=" + review(new Change(
            true, true, "ops-a", "ops-a",
            "https://idp.partner.example/metadata", true)));
        System.out.println("BAD_URL=" + review(new Change(
            true, true, "ops-a", "security-b",
            "http://127.0.0.1/metadata", true)));
        System.out.println("BAD_KEY=" + review(new Change(
            true, true, "ops-a", "security-b",
            "https://idp.partner.example/metadata", false)));

        String result = review(approved);
        System.out.println("REVIEW=" + result);
        ConfigRegistry registry = new ConfigRegistry();
        System.out.println("ACTIVATE=" + registry.activate(1, result));
        System.out.println("STALE=" + registry.activate(1, result));
        System.out.println("VERSION=" + registry.version());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FederationBoundaryDemo.java
java FederationBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
OIDC_OK=ACCEPT_OIDC
OIDC_STATE=DENY_CORRELATION
SAML_SIGNATURE=DENY_CRYPTO
SAML_REPLAY=DENY_REPLAY
CAS_UNTRUSTED=DENY_ISSUER
NO_MFA=DENY_STEP_UP
SELF_REVIEW=DENY_SELF_APPROVAL
BAD_URL=DENY_METADATA_URL
BAD_KEY=DENY_KEY_REVIEW
REVIEW=APPROVED_DRAFT
ACTIVATE=ACTIVE_VERSION_2
STALE=DENY_VERSION_CONFLICT
VERSION=2
~~~

Giải thích: request thiếu issuer trust, state correlation, cryptographic proof hoặc chống replay không được xác thực; cấu hình thiếu MFA/độc lập phê duyệt/metadata URI cho phép hoặc key review không thể approve; config version chỉ tăng sau approval và request activation thứ hai bằng expectedVersion cũ bị từ chối.

**Giới hạn:** demo không xác minh JWT/SAML/CAS/Kerberos thật, không có TLS/mTLS, signed metadata, DNS/SSRF, database, MFA service hoặc multi-node transactions. Boolean fields chỉ là kết quả mô phỏng từ verifier. Hàm `approvedMetadataUrl` không tự chống DNS rebinding/redirect/private IP, production phải bảo vệ network egress/HTTP client và trust material. `synchronized` chỉ đúng trong một JVM, production cần DB version lock/CAS và atomic publish. Reason `DENY_ISSUER` cho CAS mô phỏng source trust chung; callback CAS thực dựa vào kênh CAS Server-to-server, không phải OIDC issuer claim.

## 17. Ma trận kiểm thử bảo mật

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| OIDC | Callback thiếu/sai state. | Không login. |
| OIDC | Authorization code của issuer A gửi vào flow issuer B. | Reject mix-up. |
| OIDC | ID Token sai signature/issuer/audience/expiry/nonce. | Reject, không tạo local session. |
| OIDC | Code replay hoặc PKCE verifier sai. | Reject. |
| OIDC | Open redirect qua `next=https://evil.example`. | Không redirect credentials ra domain lạ. |
| SAML | Unsigned/modified SAMLResponse. | Reject. |
| SAML | Wrong AudienceRestriction/Destination/Recipient. | Reject. |
| SAML | Replay assertion trên hai pods. | Atomic shared replay store reject. |
| SAML | Missing InResponseTo khi policy yêu cầu. | Reject. |
| SAML | Malicious RelayState open redirect. | Reject/allow only safe destination. |
| SAML | XML có DOCTYPE/XXE/oversized body. | Reject an toàn, resource limits. |
| SAML | Metadata có cert mới chưa approved. | Chỉ stage, không auto-trust. |
| CAS | ST dùng cho wrong service hoặc đã validate. | Reject. |
| CAS PGT | Fake receptor callback từ browser. | Blocked by trust boundary. |
| CAS PGT | Node A nhận PGT, Node B validate ST. | Shared IOU→PGT mapping đúng. |
| CAS SLO | Forged logoutRequest dùng username của nạn nhân. | Không hủy theo username. |
| Kerberos | Wrong SPN/KVNO/enctype. | GSS fail, không accept identity. |
| Kerberos | Keytab lộ trong image/CI log. | Security QA FAIL, rotate/revoke. |
| Keys | SAML private key bị publish trong metadata. | Security QA FAIL. |
| JWKS | JWT `kid`/`alg` ngoài approved keys/policy. | Reject. |
| Management | Viewer gọi POST activate. | 403/deny. |
| Management | Người đề xuất tự approve. | Deny dual control. |
| Management | Actor thiếu fresh MFA. | Deny high-risk change. |
| Management | Admin thay issuer/cert của tenant khác. | Deny tenant ownership. |
| Management | Metadata URL là loopback/link-local/private. | Egress/URL checks block. |
| Management | DNS rebinding hoặc redirect tới internal IP. | Block, không kết nối internal. |
| Management | Concurrent activate dựa version cũ. | Revision conflict, không partial publish. |
| Management | Rollback sang compromised config. | Deny/disable, không re-enable key xấu. |
| Management | Admin CSRF POST không token. | Reject, dù SAML ACS có exception riêng. |
| Secrets | Vault unavailable. | Fail safely; không hardcoded fallback. |
| Logging | Gateway logs chứa `pgtId`/OIDC code. | QA FAIL, redact + incident review. |
| Runtime | Callback giữa key rotation/multi-node. | Chỉ approved trust versions, session correlation nhất quán. |

Các test ở bảng phải chạy **trên staging** với test IdP/KDC, private network, credential giả và rollback plan. **Happy-path login success không chứng minh hardening.**

## 18. Troubleshooting theo triệu chứng

| Dấu hiệu | Root cause | Hướng điều tra |
| --- | --- | --- |
| OIDC callback bị state mismatch sau scale-out. | State/session cookie không đồng bộ, SameSite/ingress sai. | Authorization request repository, cookie, proxy. |
| OIDC login fail sau đổi issuer. | Không khớp client registration/issuer/JWKS. | Config version, issuer/audience, không bỏ checks. |
| SAML ACS POST 403. | CSRF matcher hoặc route/WAF sai. | Narrow ACS exemption, giữ OpenSAML filters. |
| SAML signature fail sau rotation. | Cert chưa approved/các nodes chưa refresh. | Check trust anchor, overlap, issuer, cache. |
| SAML replay qua node khác được nhận. | Cache replay local. | Shared atomic replay store/TTL. |
| CAS PGT IOU lookup miss. | Receptor unreachable, store không shared, ACK trước persist. | TLS, inbound trust, mapping store. |
| CAS SLO logout nhầm thiết bị. | Xóa theo username thay vì ticket→session. | Sửa session correlation. |
| Kerberos lỗi `KRB_AP_ERR_MODIFIED`. | SPN/account/KVNO/keytab mismatch. | AD/KDC, keytab distribution/rotation. |
| User vẫn vào sau IdP logout. | Local session/API token sống riêng. | Revocation/session TTL, không nhầm login với logout. |
| Admin có thể tự duyệt config. | Chỉ check ROLE_ADMIN, thiếu dual control. | Approval state machine, reviewer identity. |
| Metadata fetch chạy tới cloud metadata. | SSRF redirects/DNS bypass. | Egress isolation, no redirects, IP checks. |
| IdP metadata tự đổi signing cert. | Auto-trust không có signer/approval. | Disable auto activation, pin trust material. |
| Secret xuất hiện trong actuator hoặc log. | Runtime/ingress redaction thiếu. | Containment, rotation, remove exposure. |
| Hai pods xác minh SAML khác nhau. | Config trust version/rotation không đồng bộ. | Versioned registry, canary, atomic publish. |
| Rollback làm login chạy lại nhưng key cũ đã lộ. | Rollback insecure. | Emergency disable, issue safe new key. |

**Đọc logs qua reason codes, không thông qua raw tokens.** Bắt đầu từ callback matcher → protocol verification → issuer/cert/JWKS/key version → state/replay cache → config active version → local account authorization; với admin plane còn xem MFA, RBAC, approval, egress và audit.

## 19. Sai lầm thường gặp

1. **“Callback là public nên bỏ hết Spring Security.”** Sai: chưa cần local Authentication nhưng phải qua protocol verifier.
2. **“SAML POST là server IdP gọi trực tiếp.”** Thường browser POST, chữ ký/trust mới chứng minh nguồn.
3. **“HTTPS đủ thay chữ ký SAML.”** Sai: TLS client→SP không xác minh XML issuer.
4. **“OIDC code có nghĩa người dùng đã login.”** Sai: còn state/PKCE/token validation.
5. **“`registrationId` trong callback được chọn issuer tùy ý.”** Sai: chỉ tra registration đã duyệt.
6. **“JWT `kid` có thể tự tải JWKS từ URL trong token.”** Sai: phải dùng approved issuer/JWKS.
7. **“IdP public cert có thể thay bằng private key của SP.”** Sai: khác chủ sở hữu/vai trò.
8. **“SAML encrypted assertion không cần signature.”** Sai: encryption không là identity proof.
9. **“CAS PGT receptor có browser session.”** Sai: thường là CAS Server-to-server callback.
10. **“Chữ ký trong CAS SLO giống SAML2 SLO.”** Không mặc định, tùy protocol/trust.
11. **“Đổi TLS cert nghĩa là đổi SAML signing cert.”** Sai nếu là hai key roles riêng.
12. **“Keytab chỉ là một username.”** Sai: chứa long-term service secret keys.
13. **“K8s Secret dùng Base64 nên private key đã an toàn.”** Sai: còn etcd/RBAC/mount/backup.
14. **“Admin đã đăng nhập nên được phép tự thêm issuer.”** Sai: cần scope, MFA, approval.
15. **“SAML metadata qua HTTPS tự đáng tin.”** Sai: trust bootstrap/signer/approval.
16. **“Chặn URL localhost là đủ chống SSRF.”** Sai: DNS rebinding, redirect, private IPv6 và egress.
17. **“ACS CSRF exempt thì admin POST cũng exempt.”** Sai: khác trust boundary.
18. **“Đổi cert xong xóa old ngay là an toàn.”** Có thể làm fail in-flight tokens; cần overlap trừ compromise.
19. **“Rollback compromised key để phục hồi login.”** Sai: phải revoke, không re-enable.
20. **“HTTP 200 callback chứng minh local Authentication/Logout đúng.”** Sai: cần readback/state verification.
21. **“Một pod có replay cache là đủ multi-node.”** Sai nếu node khác không chia sẻ state.
22. **“Có ROLE_ADMIN thì quyền thay role mapping không cần xét tenant.”** Sai: tenant scope/dual control.
23. **“Có secret manager thì logs mặc định không thể lộ token.”** Sai: ingress/APM/application có thể ghi raw payload.
24. **“Có ký JWT đúng nhưng sai audience vẫn cho login.”** Sai: validation phải kiểm tra toàn bộ token semantics.

## 20. Checklist nghiệm thu

1. Liệt kê tất cả OIDC/SAML/CAS callbacks, methods, hostnames, proxy routes và service registrations.
2. OIDC có state, nonce, PKCE, exact redirect/issuer/audience/signature/expiry và mix-up defenses.
3. SAML có trusted signing cert, issuer/destination/recipient/audience/Conditions/SubjectConfirmation/InResponseTo/replay.
4. SAML ACS POST đi qua OpenSAML provider; CSRF exemption hẹp, không mở admin plane.
5. CAS ST callback validate service binding/one-time; PGT receptor inbound trust, IOU store và log redaction.
6. CAS SLO có source trust và đúng ticket→local session mapping.
7. OIDC client secrets, SAML SP signing/decryption keys, TLS keys và Kerberos keytab ở secret management có RBAC.
8. JWKS `kid/alg` chỉ chọn approved issuer keys, không auto trust arbitrary `jku`.
9. Kerberos SPN, keytab KVNO/enctype/realm được test qua nhiều nodes.
10. Public metadata chỉ export public material; admin edit APIs không public và không leak secrets.
11. Admin có RBAC theo tenant, MFA step-up, dual approval, CSRF, method restrictions và audit.
12. Metadata fetcher chống SSRF/DNS rebinding/redirect/IPv4/IPv6 private, XXE, DoS và trust swap.
13. Config là versioned immutable, atomic activate/rollback, không re-enable compromised material.
14. Rotation có overlap được duyệt, canary/login tests và emergency revoke plan.
15. Runtime state/replay/nonce/PGT mapping nhất quán và fail closed khi store lỗi.
16. Ingress/APM/logging đều redact credential, không chỉ application logs.
17. Audit secret reads, key rotation, config review/activation, rejected callbacks và tenant ownership.
18. QA adversarial test đúng ranh giới và incident exercise định kỳ.

## 21. Tự kiểm tra kiến thức

1. **Callback OIDC có thể không cần local session trước, vậy tại sao vẫn an toàn?** — Vì Spring xác minh state/PKCE/nonce/issuer/token rồi mới tạo Authentication.
2. **Điều gì xác thực SAMLResponse?** — Trusted IdP XML signature và các điều kiện issuer/audience/recipient/time/correlation.
3. **Metadata HTTPS có tự được xem là trust anchor không?** — Không; phải có approved signer/cert hoặc kênh xác minh và phê duyệt.
4. **`pgtId` và `pgtIou` trong CAS khác nhau thế nào?** — PGT là credential; IOU là khóa nối callback với trusted validation response.
5. **Vì sao CAS PGT receptor cần inbound trust?** — TLS certificate của receptor dùng cho CAS gửi PGT không tự chứng minh ai đang gọi receptor.
6. **Keytab dùng để làm gì?** — Chứa Kerberos service keys để accept tickets cho SPN/realm đúng.
7. **TLS key và SAML SP signing private key có phải một?** — Không bắt buộc, nên quản trị vai trò riêng.
8. **JWKS `kid` có tạo trust mới không?** — Không; chỉ chọn key từ trusted issuer keys.
9. **Tại sao cần dual approval cho đổi issuer?** — Vì đổi issuer/cert là đổi chính trust boundary, có thể dẫn tới chiếm tài khoản.
10. **Host allowlist ngăn mọi SSRF?** — Không; phải kiểm soát DNS, redirects, egress, private IPs.
11. **Admin POST được exempt CSRF giống SAML ACS?** — Không; admin dùng browser session và cần CSRF.
12. **Vì sao rollback compromised key nguy hiểm?** — Nó tái kích hoạt một bí mật/trust anchor đã không an toàn.
13. **Sau rotate signing key, có thể xóa old verification key ngay không?** — Tùy token/assertion lifetime, overlap và compromise risk.
14. **Một replay cache trong một pod đủ không?** — Không nếu callbacks có thể đến node khác.
15. **Điều kiện nghiệm thu nào chứng minh gia cố tốt?** — Callback giả/wrong issuer/replay/SSRF/admin self-approve/secret exposure đều bị từ chối, cùng happy-path login.

## Tài liệu tham khảo

- [Spring Security — OAuth2 Login Advanced Configuration, Redirection Endpoint](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Authorization Grants and PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0 — Issuer, Audience, Nonce and ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — SAML2 Login Overview, ACS/OpenSAML Validation](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML2 Response Authentication and Decryption](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Metadata Signature Verification](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — Servlet CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Authorizing HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security Kerberos — Project Source](https://github.com/spring-projects/spring-security-kerberos)
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SSRF_Prevention_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [RFC 4120 — Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120.html)
