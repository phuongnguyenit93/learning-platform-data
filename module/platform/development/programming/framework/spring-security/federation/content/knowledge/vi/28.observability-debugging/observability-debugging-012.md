# Thu thập nhật ký kiểm toán đăng nhập, đăng xuất và thay đổi đối tác trong Spring Security Federation

## 1. Mục tiêu và ngữ cảnh

Trong hệ thống **Spring Security - federation**, ứng dụng có thể nhận danh tính từ nhiều **Identity Provider (IdP)** qua **OpenID Connect (OIDC)**, **SAML 2.0** hoặc **CAS**. Khi sự cố xảy ra, câu hỏi không chỉ là “HTTP trả 200 hay 302?” mà còn là:

- Người dùng nào, qua **đối tác định danh nào**, đã đăng nhập thành công hoặc thất bại?
- Lỗi nằm ở xác thực, chữ ký/issuer, dữ liệu thuộc tính, mapping quyền, MFA hay chính sách ứng dụng?
- Một thao tác đăng xuất đã **chỉ xóa session ở ứng dụng**, đã **khởi tạo Single Logout (SLO)**, hay đã **được IdP xác nhận**?
- Ai đã thay đổi metadata, EntityID, issuer, certificate, ACS/redirect URI, client registration, role mapper hoặc SLO endpoint của **đối tác federation**? Thay đổi nào được phê duyệt, áp dụng trên node nào, có rollback không?
- Có thể dựng lại timeline phục vụ điều tra mà **không lưu raw token, CAS ticket, SAMLResponse, session cookie hoặc private key** không?

Bài thuộc nhóm **Quan sát và gỡ lỗi**. “**Đối tác**” ở đây là đối tác kỹ thuật trong quan hệ federation như **IdP/Asserting Party, SAML Service Provider, OIDC client/provider, CAS server/service** hoặc đối tác B2B có cấu hình tin cậy; không phải người dùng cuối hay một giao dịch mua hàng.

**Kết quả học tập:** xây dựng taxonomy sự kiện chuẩn; kết hợp đúng Spring Security events và protocol handlers; ghi nhận cả local logout lẫn SAML/OIDC/CAS global logout; giám sát thay đổi trust configuration; vận hành pipeline audit bền vững, có kiểm soát quyền và retention; kiểm chứng bằng **Java 17 chạy độc lập**, ví dụ Spring configuration và ma trận test end-to-end.

> **Nguyên tắc xuyên suốt:** audit event phải trả lời **khi nào – ở đâu – ai – đã làm gì – kết quả gì – dưới ngữ cảnh tin cậy nào**. Nhưng dữ liệu kiểm toán **không được biến thành một kho credential, assertion XML hoặc thông tin cá nhân thô**.

## 2. Audit trail khác access log, debug log và metrics

| Loại | Mục tiêu chính | Ví dụ | Có đủ cho điều tra federation? |
| --- | --- | --- | --- |
| **HTTP access log** | Method, route, response code, latency | `POST /login/saml2/sso/corp 302` | **Không**: 302 có thể là thành công hoặc redirect lỗi |
| **Application debug log** | Chi tiết hoạt động cho dev | “Resolver chọn registration X” | Có thể giúp điều tra, nhưng không nhất thiết đầy đủ/bền |
| **Security audit event** | Bằng chứng hành động an ninh và thay đổi quyền/trust | `LOGIN_DENIED / INVALID_SIGNATURE` | **Có**, nếu schema, completeness và integrity được thiết kế đúng |
| **Trace/span** | Luồng phân tán, độ trễ | trace ID, span giữa SP và IdP | Chỉ là correlation; không tự là audit record |
| **Metric** | Xu hướng, alert, SLO vận hành | `login_failure_total{protocol="SAML2"}` | Không đủ để quy trách nhiệm từng thay đổi |
| **Configuration change record** | Ai thay đối tác nào, thay gì, trước/sau, approval, thời điểm effective | `PARTNER_SIGNING_CERT_ACTIVATED` | Bắt buộc khi điều tra trust changes |
| **IdP-side audit** | Authentication/MFA/SSO session và issuance ở IdP | `MFA_CHALLENGE_PASSED` | SP không thể thay thế; phải correlates an toàn |

**Không suy từ HTTP 200 là “đăng nhập thành công”.** Khi ứng dụng chưa tạo Spring `Authentication` nhưng IdP đã hoàn tất xác thực, kết quả ở hai hệ thống khác nhau. Tương tự, một người dùng click nút “Đăng xuất” không chứng minh tất cả IdP sessions và ứng dụng khác đã bị hủy.

### Audit trail cần có tính bất biến tương đối

Một log in-memory hoặc file ứng dụng dễ bị rotate/mất khi pod khởi động lại. Với mục tiêu kiểm toán bảo mật, cần thiết kế:

1. **Append-only**: bổ sung event mới thay vì âm thầm sửa/xóa event cũ.
2. **Truy nguồn**: có `event_id`, `event_time`, `service`, `environment`, `partner_key`, `correlation_id`.
3. **Integrity**: hạn chế thao tác sửa/xóa, audit access và có thể dùng WORM/object lock, checksum/hash chain hoặc SIEM integrity controls khi phù hợp.
4. **Durability**: không chỉ lưu trong RAM của một pod; dùng durable repository hoặc broker/collector.
5. **Controlled access**: security auditor có thể truy vấn, developer/support chỉ xem trường cần thiết.
6. **Retention hợp lý**: có policy lưu/xóa/điều tra pháp lý, không kéo dài vô hạn chỉ vì “có thể hữu ích”.
7. **Timezone UTC** và schema version để phân tích qua nhiều hệ thống.

Chữ ký của một SAMLResponse không thay thế integrity của **audit storage**: SAML signing xác thực thông điệp SAML, còn audit evidence phải được bảo vệ **sau khi sự kiện được ghi**.

## 3. Taxonomy sự kiện: đừng chỉ có LOGIN và LOGOUT

Nên định nghĩa **event_type** rõ ràng và giới hạn bằng enum/schema, tránh một string tự do:

| Event type gợi ý | Khi phát sinh | Kết quả/ý nghĩa |
| --- | --- | --- |
| `LOGIN_STARTED` | SP khởi tạo federation flow | Mới bắt đầu, **chưa authenticated** |
| `LOGIN_CALLBACK_RECEIVED` | Callback/ACS nhận request | Chỉ là nhận dữ liệu, chưa verified |
| `LOGIN_AUTHENTICATED` | Spring provider đã xác thực và tạo Authentication hợp lệ | Đã qua protocol validation và cơ chế account mapping tương ứng |
| `LOGIN_REJECTED` | Provider/filter từ chối login | Authentication thất bại; reason phân loại an toàn |
| `LOGIN_POLICY_DENIED` | Danh tính hợp lệ nhưng local business/tenant policy từ chối | Phân biệt authenticated với authorized |
| `LOGIN_SESSION_ESTABLISHED` | HTTP session/SSO principal đã sẵn sàng | Có application session cụ thể nếu app dùng session |
| `SESSION_EXPIRED` | Session hết hạn/invalidated theo backend hoặc container | **Không mặc định là người dùng chủ động logout** |
| `LOGOUT_REQUESTED` | User/IdP/API yêu cầu logout | Chưa chứng minh cleanup hoặc SLO đã hoàn tất |
| `LOGOUT_LOCAL_COMPLETED` | Ứng dụng đã xóa security context/session theo thiết kế | Chỉ xác nhận **local logout** |
| `LOGOUT_SLO_DISPATCHED` | SP phát logout request tới IdP hoặc ngược lại | Đã gửi/đang xử lý, chưa biết partner chấp nhận |
| `LOGOUT_SLO_CONFIRMED` | Nhận và validate response/ack theo protocol | Chỉ xác nhận phạm vi tương quan đã được chứng minh |
| `LOGOUT_SLO_REJECTED` | Sai chữ ký, issuer, state, destination, correlation... | Không khẳng định remote sessions đã bị hủy |
| `PARTNER_CONFIG_PROPOSED` | Có yêu cầu đổi federation partner | Chưa approved/effective |
| `PARTNER_CONFIG_APPROVED` | Reviewer có quyền đã phê duyệt | Chưa chứng minh hệ thống đã apply |
| `PARTNER_CONFIG_ACTIVATED` | Cấu hình/metadata version mới được áp dụng | Effective trên phạm vi node/realm được chỉ rõ |
| `PARTNER_CONFIG_ROLLED_BACK` | Phục hồi config version cũ | Ghi bản cũ và mới rõ ràng |
| `PARTNER_CERT_ROTATED` | Thay public cert/verification hoặc encryption key reference | Phải ghi key use, fingerprint và trạng thái |
| `PARTNER_DISABLED` | Vô hiệu hóa quan hệ tin cậy | Không đồng nghĩa tất cả sessions/token cũ đã thu hồi |
| `AUDIT_DELIVERY_FAILED` | Pipeline không thể ghi/đẩy audit | Cảnh báo vận hành, không bỏ qua âm thầm |

Tên là **hợp đồng đề xuất cho hệ thống**, không phải tất cả là events có sẵn trong Spring Security. **Spring phát một số authentication/logout events**, nhưng **thay đổi cấu hình đối tác, SLO confirm và nhiều protocol stages phải được ứng dụng/IdP/platform chủ động instrument**.

### Event status phải gắn với phase

Một quy tắc hữu ích:

~~~text
phase=PROTOCOL_CALLBACK, result=RECEIVED
  != phase=AUTHENTICATION, result=SUCCESS
  != phase=LOCAL_SESSION, result=ESTABLISHED
  != phase=BUSINESS_AUTHORIZATION, result=ALLOW

phase=LOGOUT_REQUEST, result=ACCEPTED
  != phase=LOCAL_SESSION, result=CLEARED
  != phase=REMOTE_SLO, result=CONFIRMED
~~~

Nếu gộp mọi thứ thành `LOGIN_SUCCESS` ngay khi nhận HTTP POST `SAMLResponse`, kẻ tấn công chỉ cần gửi invalid XML đã tạo ra “đăng nhập thành công” giả. Ghi security outcome **sau** kiểm chứng ở đúng tầng.

## 4. Sơ đồ các nguồn sự kiện và đường thu thập

~~~mermaid
flowchart TD
    B[Browser] --> S[Spring Security SP / RP]
    S --> IDP[IdP / CAS / Partner]
    IDP --> IA[IdP audit stream]
    S --> AE[Authentication events]
    S --> LE[Logout / SLO handlers]
    S --> CE[Partner config change service]
    AE --> EN[Approved audit event schema]
    LE --> EN
    CE --> OB[Transactional outbox]
    OB --> EN
    IA --> SIEM[Central SIEM / durable event store]
    EN --> SIEM
    SIEM --> C[Correlate / alert / investigate]
~~~

**Ranh giới nguồn:** IdP biết authentication/MFA thực sự ở IdP; SP biết callback validation và local session; CAS biết ticket issue/redeem; config service biết ai duyệt và áp dụng partner metadata. **Một nguồn log không thể chứng minh sự kiện ngoài phạm vi quan sát của nó.**

**Sơ đồ không hàm ý** ứng dụng luôn gửi logs trực tiếp đến SIEM đồng bộ trên request thread. Với critical config changes có thể cần durable local outbox; với login khối lượng lớn cần cân nhắc latency, backpressure và rủi ro mất audit.

## 5. Đăng nhập qua OIDC: audit những gì?

OIDC Authorization Code flow thường có:

~~~text
1. GET /oauth2/authorization/{registrationId}
   -> LOGIN_STARTED (optional; not success)

2. Browser redirects to IdP, IdP authenticates/MFA
   -> IdP-side MFA/login events

3. GET /login/oauth2/code/{registrationId}?code=...&state=...
   -> callback RECEIVED only (not yet successful)

4. Spring validates state, exchanges code over HTTPS,
   validates ID Token signature, issuer, audience, expiry/nonce
   -> LOGIN_AUTHENTICATED or LOGIN_REJECTED

5. App maps (verified iss, sub) -> local user/tenant/roles
   -> LOGIN_POLICY_DENIED or local session ready

6. Browser redirected to clean app URL
   -> report current session and authorization normally
~~~

**Audit fields hữu ích**:
- `protocol=OIDC`, `partner_key=corp_oidc` hoặc registration ID đã cấu hình.
- `stage=ID_TOKEN_VALIDATION`, `reason=INVALID_ISSUER`, `NONCE_MISMATCH`, `CODE_EXCHANGE_FAILED`... dùng **mã lỗi chuẩn hóa**.
- `subject_ref` là local ID hoặc pseudonymous stable reference sau validation; không cần log raw `sub`/`email`.
- `issuer_ref` hoặc partner config revision, không dùng issuer URL do request chưa verify làm trusted identity.
- `client_key` nếu một service có nhiều OAuth clients (tên ID đã được quản trị phê duyệt).
- `session_ref` là random audit reference riêng nếu thật cần, **không dùng raw session cookie**.
- `trace_id`/`interaction_id` độc lập với OAuth `state`.

**Không ghi**:
- `code`, `state`, `nonce`, `code_verifier`, `client_secret`, access/refresh/ID token.
- Full callback URL/query string, Authorization/Cookie/Set-Cookie headers.
- Raw ID Token claims JSON có PII.
- Token endpoint response body hoặc HTTP client wire logs.

**Chống mix-up:** nếu 2 IdPs có cùng username hoặc realm, ghi đúng `partner_key` của **validated registration**, không lấy `registrationId` từ untrusted path rồi coi đó là kết quả đã xác thực. Nếu valid token nhưng local role/tenant deny, ghi hai sự kiện/2 stages rõ, không biến thành “OIDC authentication failed” sai nghĩa.

## 6. Đăng nhập SAML2: audit validation và mapping tách biệt

Với SAML HTTP POST tại `/login/saml2/sso/{registrationId}`, browser gửi `SAMLResponse`; Spring Security/OpenSAML giải mã (nếu encrypt), kiểm signature/issuer/destination/recipient/audience/time/replay và xây authenticated principal.

Đề xuất:

| Stage | Reason code gợi ý | Ý nghĩa |
| --- | --- | --- |
| `ACS_RECEIVED` | `CALLBACK_RECEIVED` | Request tới SP, chưa trusted |
| `RESPONSE_SIGNATURE` | `SIGNATURE_INVALID` | Không xác minh được signature |
| `ASSERTION_DECRYPTION` | `DECRYPTION_FAILED` | Không giải mã bằng SP decryption credential |
| `ASSERTION_ISSUER` | `ISSUER_MISMATCH` | Issuer không thuộc partner đã đăng ký |
| `ASSERTION_CONDITIONS` | `ASSERTION_EXPIRED` / `ASSERTION_NOT_YET_VALID` | Điều kiện thời gian sai |
| `SUBJECT_CONFIRMATION` | `RECIPIENT_INVALID` / `IN_RESPONSE_TO_INVALID` | Bearer/correlation không đúng |
| `AUDIENCE` | `AUDIENCE_MISMATCH` | Assertion không dành cho SP |
| `REPLAY` | `ASSERTION_REPLAY` | Assertion/response ID đã dùng theo policy |
| `ATTRIBUTE_MAPPING` | `REQUIRED_ATTRIBUTE_MISSING` | Signed assertion hợp lệ nhưng business input thiếu |
| `LOCAL_AUTHORIZATION` | `TENANT_DENIED` / `APP_ROLE_MISSING` | Identity hợp lệ, thiếu quyền resource |

**Không khẳng định các mã trên là exception class có sẵn**; đó là taxonomy để map lỗi provider vào audit schema. Không dump XML khi debug một reason; dùng exception type/mapped code an toàn, `registrationId` trusted, response timing và correlation.

**SAML NameID/Assertion ID có thể là PII/correlation secret**: log raw values chỉ khi được security/privacy phê duyệt và có retention controls. Nếu cần liên kết, dùng **local user key** được mapping sau validation, hoặc pseudonymization được quản trị. Không dùng raw SAMLResponse làm bằng chứng trong central log.

**Login authenticated ≠ authorized:** nếu IdP gửi `groups=["Domain Admins"]` nhưng app Reports không cho group này xem tài liệu, ghi `LOGIN_AUTHENTICATED` rồi `LOGIN_POLICY_DENIED`. Không cấp app ROLE_ADMIN chỉ vì IdP group tên “Domain Admins”.

## 7. CAS: audit ticket validation chứ không audit chỉ bằng callback URL

Trong CAS classic, `Service Ticket (ST)` thường đi qua query parameter `ticket=ST-...` ở service callback (Spring Security `/login/cas` nếu dùng default filter). Ứng dụng phải xác minh ticket qua CAS server và ràng buộc `service`/proxy chain theo policy.

~~~text
CAS Server:
  user login, TGT/session and ST issue events

Browser:
  /login/cas?ticket=ST-EXAMPLE
  (NOT a successful authentication event)

Spring CAS validation:
  validate ticket and service
  result -> LOGIN_AUTHENTICATED or LOGIN_REJECTED
~~~

Chỉ log `protocol=CAS`, partner key, result/reason, stage và independent audit ID. **Không log full `/login/cas?ticket=...`**, CAS ST, Proxy Ticket (PT), Proxy-Granting Ticket (PGT), TGT hoặc validation response chứa PII. CAS ticket thường one-time; `CAS_TICKET_REPLAY` là một reason riêng với `CAS_TICKET_EXPIRED` và `SERVICE_MISMATCH`.

CAS logout có thể chỉ xóa local session hoặc phối hợp logout với CAS server và các services theo cơ chế/version. **Không tạo một `SLO_CONFIRMED` event chỉ vì người dùng click nút Logout**.

## 8. Đăng xuất: có nhiều mức hoàn thành

Ba câu “đã đăng xuất” không tương đương:

1. **Ứng dụng đã xóa session/security context** — local logout.
2. **SP đã gửi LogoutRequest hoặc redirect đến IdP** — đang khởi tạo federation logout.
3. **IdP đã gửi response hợp lệ hoặc back-channel action được kiểm chứng** — một phần SLO được xác nhận theo giao thức và phạm vi thực tế.

Các trạng thái riêng có thể là:

~~~text
LOGOUT_REQUESTED
  -> LOGOUT_LOCAL_COMPLETED
  -> LOGOUT_SLO_DISPATCHED
  -> LOGOUT_SLO_CONFIRMED | LOGOUT_SLO_REJECTED | LOGOUT_SLO_TIMEOUT
~~~

Không phải mọi flow đi qua tất cả mũi tên. Ví dụ **IdP-initiated SAML SLO** bắt đầu từ validated inbound LogoutRequest; OIDC back-channel do IdP gửi có thể trực tiếp thu hồi session của RP mà không có browser redirect.

### Local logout theo Spring Security

Spring Security có `LogoutFilter` và `LogoutHandler`; thường xóa `SecurityContext`, invalidate `HttpSession`, clear CSRF/RememberMe tùy cấu hình. Theo tài liệu Spring Security, default logout flow có thể phát **`LogoutSuccessEvent`** nhờ `LogoutSuccessEventPublishingLogoutHandler`.

**Audit đúng:** `LOGOUT_LOCAL_COMPLETED` chỉ sau khi cleanup trong ứng dụng được thực hiện, không phải khi nhận HTTP `GET /logout` hiển thị confirmation page. Với CSRF enabled, một `POST /logout` có token hợp lệ thường là hành động thực hiện logout.

### OIDC RP-initiated logout

`OidcClientInitiatedLogoutSuccessHandler` có thể redirect tới `end_session_endpoint` trong discovery metadata của OIDC Provider. Audit:

- `LOGOUT_LOCAL_COMPLETED` nếu session RP đã invalidated.
- `LOGOUT_SLO_DISPATCHED` khi tạo response/redirect tới OP.
- **Không tự coi redirect gửi đi là IdP đã hủy session**.
- Nếu có callback/confirmation, ghi `LOGOUT_SLO_CONFIRMED` **chỉ khi** contract thật sự chứng minh điều đó; một browser redirect không bảo đảm các RP khác đều logout.
- Nếu người dùng đóng browser giữa chừng, có thể chỉ local logout.

### OIDC Back-Channel Logout

Spring Security có thể hỗ trợ `oidcLogout(...).backChannel(...)`, endpoint default `/logout/connect/back-channel/{registrationId}` trong tài liệu tương ứng. OP gửi **Logout Token**; RP xác minh signature/claims và ràng buộc với session theo `sid` hoặc `sub`/audience.

Audit phải phân biệt:

~~~text
BACK_CHANNEL_LOGOUT_RECEIVED (untrusted until validation)
BACK_CHANNEL_LOGOUT_VALIDATED
LOCAL_SESSIONS_INVALIDATED (actual count, if known safely)
BACK_CHANNEL_LOGOUT_REJECTED (signature/audience/issuer/replay)
~~~

Không log raw Logout Token hoặc `sid`/`sub` nhạy cảm. **Không coi inbound HTTP 200 là chắc chắn mọi client/session đã bị thu hồi**; cần record phản hồi của đúng implementation và policy. Spring OIDC support có version-specific requirements về session registry/cookie name; kiểm docs của version đang chạy.

### SAML2 Single Logout

Spring Security hỗ trợ **RP-initiated** và **AP/IdP-initiated** SAML SLO tùy metadata/cấu hình:

- RP-initiated: application local logout → phát `saml2:LogoutRequest` ký → IdP xử lý → SP nhận `saml2:LogoutResponse` và validate.
- IdP-initiated: SP nhận `saml2:LogoutRequest`, **validate signature/issuer/destination** → invalidate local session → phát `saml2:LogoutResponse`.
- Thường có endpoint `/logout/saml2/slo` theo tài liệu, và riêng local `POST /logout` tùy DSL configuration.

**Audit nên nằm đúng bước:** nhận request chưa là logout success; chỉ sau valid signature/replay/correlation mới coi là yêu cầu đáng tin; local session cleanup mới ghi local completed; SLO confirmed chỉ khi nhận và validate response theo contract. Nếu IdP không trả response hoặc logout chỉ một phần trong mạng lưới, không báo `GLOBAL_LOGOUT_COMPLETED` vô điều kiện.

### CAS Single Logout

CAS server có thể gửi back-channel/front-channel logout notifications tùy protocol và deployment. Cần ghi `CAS_LOGOUT_MESSAGE_RECEIVED`, validation/correlation outcome, local sessions invalidated; **không dùng raw LogoutRequest/XML/tickets làm event body**. Việc Spring session listener có được gọi tùy CAS client/filter và session store, phải test thực.

## 9. Ma trận audit đăng xuất: tránh “thành công giả”

| Tình huống | Sự kiện nên có | Không được kết luận |
| --- | --- | --- |
| User mở `GET /logout` confirmation | `LOGOUT_PAGE_VIEWED` (nếu cần) | Chưa local logout |
| User `POST /logout` và session bị hủy | `LOGOUT_LOCAL_COMPLETED` | IdP/global sessions đều đã hủy |
| RP redirect sang OIDC end_session_endpoint | `LOGOUT_SLO_DISPATCHED` | OP chắc chắn đã revoke mọi session |
| OP gửi back-channel Logout Token sai ký | `LOGOUT_SLO_REJECTED` | Session phải bị xóa vì request chưa trusted |
| Valid OIDC Logout Token, match 1 session | `LOGOUT_SLO_CONFIRMED`/`LOCAL_SESSIONS_INVALIDATED` | Các client khác đã logout |
| SAML LogoutRequest hợp lệ từ IdP | `LOGOUT_REQUEST_VALIDATED`, sau cleanup `LOGOUT_LOCAL_COMPLETED` | Không log success trước validation |
| SAML LogoutResponse valid sau RP request | `LOGOUT_SLO_CONFIRMED` theo scope | Không chứng minh toàn bộ hệ thống downstream đã logout |
| SAML LogoutResponse invalid/unmatched | `LOGOUT_SLO_REJECTED` | Không lấy HTTP response status làm proof |
| CAS ticket đã hết hạn | `LOGIN_REJECTED` nếu login ticket validation | Không nhầm với logout |
| Session timeout tự động | `SESSION_EXPIRED` | Không thể quy cho user chủ động logout |
| Browser đóng tab | Không nhất thiết có server-side event | Không tự sinh logout event |
| IdP session revoked, SP cache còn | `IDP_SESSION_REVOKED` phía IdP và sự kiện ở SP khi thực thu hồi | Không giả định rollback quyền ngay |

Để tránh lẫn lộn, event nên có `origin=USER|IDP|SYSTEM|ADMIN` và `logout_scope=LOCAL|RP_INITIATED|IDP_INITIATED|BACK_CHANNEL`. Chỉ đặt `origin=IDP` khi đã xác minh nguồn theo protocol; trước validation, đó là **untrusted callback**.

## 10. Đối tác federation là một trust relationship có vòng đời

Thay đổi đối tác có thể mở một trust boundary mới hoặc làm mất an toàn cho tất cả users. Ví dụ:

- Tạo/disable/enable một `RelyingPartyRegistration` SAML cho đối tác.
- Đổi **SAML EntityID**, Assertion Consumer Service, Single Logout Service URL, `NameIDFormat` hoặc attribute mapping.
- Nhập metadata IdP mới và **verification signing certificate**; quay vòng old/new cert.
- Đổi **SP signing/decryption credential reference**, không chép private key.
- Đổi OIDC `issuer-uri`, `client-id`, `client-secret reference`, registered redirect URIs, logout URI, scopes hoặc JWKS trust configuration.
- Đổi CAS server URL, `service` binding, proxy callback, trusted proxies.
- Đổi mapping group/role/tenant, automatic account linking và MFA assurance contract.
- Đổi allowed authentication protocols, decryption/signature requirements, `clockSkew` và session TTL.
- Đổi partner owner, contact, approval/quorum, trạng thái active/suspended/retired.
- Thay metadata refresh schedule, cache TTL, allowlist nguồn và tự động rollover chính sách.

**Có tác động an ninh cao:** thay đổi issuer/cert/redirect URI có thể cho phép attacker IdP giả phát tokens, chuyển browser sang origin ngoài ý muốn, thay key xác minh hoặc cấp role rộng. Vì vậy cần audit trail **trước–sau–phê duyệt–triển khai–rollback**, không chỉ một dòng “config updated”.

### Phân biệt thay đổi do người và thay đổi tự động

| Loại | Ví dụ | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Manual admin action | Admin thay metadata URL | `actor_ref` của admin + approval |
| API automation | GitOps pipeline deploy partner revision | Workload/service principal, commit/change ID |
| Metadata refresh | Scheduled job tải IdP metadata | Source service/system; xem trust/policy |
| Key rotation | IdP công bố cert mới | Partner revision, certificate fingerprints, overlap |
| Emergency disable | Security tắt compromised partner | Operator, incident ID, reason, expedited approval |
| Rollback | Khôi phục old verified config | Actor/approver, from/to revision, observed outcome |

**Không gán actor là một user dựa trên HTTP `X-User` header chưa được trusted proxy xác minh**. Actor phải đến từ **authenticated management identity** (admin SSO/session) hoặc workload identity được ký/kiểm. Với automation, ghi cả `service_actor` lẫn change ticket/commit reference được xác minh, không giả sử nó là một con người.

## 11. Vòng đời partner change và các mốc phải có audit

~~~mermaid
sequenceDiagram
    participant A as Admin / Automation
    participant M as Partner Admin Service
    participant R as Reviewer
    participant D as Config DB / outbox
    participant N as Spring nodes
    A->>M: Propose config revision v4
    M->>D: Append PARTNER_CONFIG_PROPOSED
    R->>M: Approve reviewed change
    M->>D: Append PARTNER_CONFIG_APPROVED
    M->>M: Validate issuer, cert, URLs, policy and schema
    M->>D: Commit revision v4 and audit outbox atomically
    D-->>N: Refresh approved revision
    N->>D: Record PARTNER_CONFIG_ACTIVATED / node version
    opt Health/trust check fails
        A->>M: Request rollback
        M->>D: Record rollback to v3 + reason
    end
~~~

Một bảng audit có thể chứa:

~~~text
change_id=chg_402
partner_key=corp_saml
old_revision=rev_3
new_revision=rev_4
changed_field=signing_cert_fingerprint
old_value_reference=fp_sha256_OLD (public cert fingerprint only)
new_value_reference=fp_sha256_NEW
actor_ref=admin_7
approver_ref=reviewer_2
approval_ticket=SEC_1042
status=ACTIVATED
effective_nodes=[sp_1,sp_2]
event_time=2026-11-07T03:00:00Z
~~~

**Ví dụ này không phải SHA-256 fingerprint thật.** Trong hệ thống thật nên lưu giá trị fingerprint đúng format/bytes của **public certificate** đã review; không lưu private key, client secret, raw metadata chứa thông tin không cần thiết hoặc toàn bộ diff JSON tùy ý.

### Đổi khóa xác minh có hai sự kiện riêng

- **IdP công bố khóa mới trong metadata/JWKS** (`PARTNER_METADATA_OBSERVED`): nguồn bên ngoài, chưa chắc đã được tin/approved.
- **RP/SP thực sự kích hoạt trust vào khóa mới** (`PARTNER_TRUST_ACTIVATED`): một quyết định bảo mật đã apply, cần audit với from/to version.

Chỉ thấy metadata mới không đồng nghĩa tất cả Spring nodes đã sử dụng nó. Với metadata cache, startup snapshots hoặc cluster replication, có thể cần event per node hoặc deployment digest để chứng minh **effective revision**.

### Tách signing, encryption, client secret

- IdP **signing verification certificate** là public trust anchor phía SP.
- SP **decryption private key** là secret của SP, IdP chỉ cần public encryption certificate.
- OIDC `client-secret` là credential phải quản lý bằng secret vault và chỉ log **secret reference/version** không log giá trị hoặc hash unsalted.
- CAS shared secrets/service registrations (nếu deployment dùng) phải tuân thủ cùng nguyên tắc.
- Khi đổi một loại key, **không gọi chung “certificate rotated”** nếu không nêu `key_use=SIGNATURE_VERIFY|ENCRYPTION|SP_SIGN|CLIENT_AUTH`.

Một diff được phép chứa **fingerprint, EntityID, URL đã chuẩn hóa và được duyệt, boolean policy, version, allowed scopes**. Đối với URLs chứa query/callback state hoặc thông tin nhạy cảm, không ghi raw unreviewed URL; chọn field classification và sanitizer riêng.

## 12. Schema sự kiện kiểm toán khuyến nghị

Một audit record có trường cố định:

| Field | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `schema_version` | Phiên bản contract audit | Bắt buộc, backward compatibility |
| `event_id` | ID duy nhất, chống duplicate khi retry | Sinh server-side; không dùng ticket/token |
| `event_time` | Thời điểm sự kiện diễn ra | ISO 8601 UTC/`Instant` |
| `ingest_time` | Thời điểm collector nhận | Cho biết độ trễ pipeline |
| `service` / `environment` / `instance` | Nơi ghi nhận | Enumerated/approved values |
| `event_type` | Taxonomy hữu hạn | Enum; không nhập từ query |
| `protocol` | `OIDC`/`SAML2`/`CAS`/`LOCAL` | Enum |
| `stage` | `REQUEST`/`VALIDATION`/`SESSION`/`CONFIG_APPLY` | Enum |
| `outcome` | `SUCCESS`/`DENIED`/`PENDING`/`ERROR` | Không suy từ HTTP status |
| `reason_code` | Loại lỗi cụ thể không lộ dữ liệu | Enum allowlist |
| `partner_key` | Mã đối tác nội bộ | Chỉ trusted registration/config |
| `partner_revision` | Config snapshot đã dùng | Bắt buộc nếu cần tái lập lỗi cert/issuer |
| `actor_ref` / `subject_ref` | Tham chiếu identity đã xác minh/pseudonym | Không raw credential hoặc PII thừa |
| `origin` | `USER`/`IDP`/`ADMIN`/`AUTOMATION`/`SYSTEM` | Phải xác định mức trust |
| `interaction_id` / `trace_id` | Correlate nhiều events cùng flow | ID độc lập với state/nonce/ticket |
| `change_id` / `old_revision` / `new_revision` | Partner change lifecycle | Chỉ xuất hiện ở config events |
| `changed_fields` | Các field names đã thay | Allowlist, không raw arbitrary JSON |
| `approval_ref` | Tham chiếu ticket/approver | Chống giả mạo, có retention |
| `logout_scope` | Local/RP-initiated/IdP-initiated/back-channel | Không gán remote confirmed nếu chưa có proof |

### Ví dụ JSON đăng nhập thành công

~~~json
{
  "schema_version": 1,
  "event_id": "evt_a740",
  "event_time": "2026-11-07T03:00:00Z",
  "service": "reports-sp",
  "environment": "prod",
  "instance": "sp_02",
  "event_type": "LOGIN_AUTHENTICATED",
  "protocol": "SAML2",
  "stage": "ASSERTION_VALIDATED",
  "outcome": "SUCCESS",
  "reason_code": "NONE",
  "partner_key": "corp_saml",
  "partner_revision": "rev_4",
  "subject_ref": "local_u_041",
  "interaction_id": "int_804"
}
~~~

### Ví dụ JSON thay đổi cấu hình đối tác

~~~json
{
  "schema_version": 1,
  "event_id": "evt_b122",
  "event_time": "2026-11-07T03:05:00Z",
  "service": "partner-admin",
  "environment": "prod",
  "event_type": "PARTNER_CONFIG_ACTIVATED",
  "protocol": "SAML2",
  "stage": "CONFIG_APPLY",
  "outcome": "SUCCESS",
  "reason_code": "NONE",
  "partner_key": "corp_saml",
  "change_id": "chg_402",
  "old_revision": "rev_3",
  "new_revision": "rev_4",
  "changed_fields": ["signing_cert_fingerprint", "metadata_url"],
  "actor_ref": "admin_7",
  "approver_ref": "reviewer_2",
  "interaction_id": "int_806"
}
~~~

**Ví dụ dữ liệu giả**, không phải bản ghi người dùng thực. JSON schema phải có event-time source/clock semantics và field validators. Một event từ pre-authenticated filter không có trusted subject thì `subject_ref` phải null/absent, **không lấy HTTP parameter `username` làm verified actor**.

## 13. Quy tắc nhạy cảm: tuyệt đối không log trực tiếp

| Loại dữ liệu | Vì sao không log thô? | Thay thế |
| --- | --- | --- |
| `SAMLResponse`, decoded XML, Assertion, NameID | Chứa danh tính, thuộc tính và assertion dùng trong login | Registration ID, error code, pseudonymous subject sau verify |
| CAS Service Ticket/Proxy Ticket/PGT | Credential ngắn hạn hoặc delegated rights | `event_id` mới và protocol stage |
| OAuth authorization code, `state`, `nonce`, PKCE verifier | Dữ liệu correlation/credential trong front-channel | Independent interaction ID |
| Access/Refresh/ID Token, Logout Token | Bearer credential, claims nhạy cảm | Token type, validated issuer reference, safe reason |
| `Authorization`/`Cookie`/`Set-Cookie` | Credential/session hijacking | Không capture; log route/status |
| Client secret, SP private decryption/signing key | Trust boundary breach | Secret reference/version và public certificate fingerprint |
| Password/LDAP bind credential | Credential theft | Authentication outcome/validation stage |
| Full HTTP URL/query/headers/body | Có thể chứa `ticket`/`code`/`SAMLResponse`/PII | Route template/registered endpoint ID |
| Raw `Authentication`/`principal` `toString()` | Có thể chứa credentials, attributes, SAML XML | Explicit approved fields |
| Untrusted error message/stack local variables | Token/URL/log injection/PII | Mapped error enum + bounded safe context |

OWASP Logging Cheat Sheet khuyên loại bỏ hoặc bảo vệ session IDs, access tokens, passwords, encryption keys và sensitive personal data. **Log injection** cũng là rủi ro: user có thể chèn CR/LF hoặc control characters vào username/partner display name rồi tạo “dòng audit giả”. Dùng **JSON structured logging, schema validation, output escaping, length bounds và input classification** thay vì nối raw values vào text.

**Không tự dùng SHA-256(email) để tạo pseudonym rồi coi đã ẩn danh tuyệt đối**: email thường có không gian đoán được và có thể bị dictionary attack. Khi thật sự cần stable pseudonym, cân nhắc **HMAC với key được quản lý**, domain separation/rotation policy và quyền đọc audit; hoặc local opaque user ID được phép sử dụng.

## 14. Correlation ID: đừng lấy credential làm trace ID

Một login qua OIDC có nhiều identifiers:
- Browser request ID từ reverse proxy.
- OAuth `state` và OIDC `nonce`.
- IdP event ID/SSO session ID.
- Spring trace/span ID.
- Local session ID.
- Audit `interaction_id`.

**Không đồng nhất chúng.** Đặc biệt `state`, CAS ticket, JWT `jti` hoặc raw SAML Assertion ID không nên tự trở thành public correlation ID trong logs. Một giải pháp:

~~~text
trace_id (OpenTelemetry) = generated trusted observability identifier
interaction_id = independent random application flow id
event_id = unique identifier for each audit event
partner_key = internal configured registration ID
user_ref = local opaque identity key only AFTER authentication
~~~

Nếu cần liên kết IdP/SP, thiết kế **mapping có giới hạn và bảo vệ** giữa IdP event ID/transaction reference với SP interaction ID; không đem bearer ticket/token qua các log pipelines.

### Clock và ordering

Mỗi event nên có `event_time` (thời điểm xảy ra), `ingest_time` (collector nhận), `instance` và (nếu có) `sequence` hoặc monotonic ordering trong cùng producer. Log đa node có thể bị lệch giờ hoặc gửi trễ. **Không coi thứ tự ingest là thứ tự sự kiện tuyệt đối**.

Ghi timestamps ISO 8601 UTC; giám sát NTP/chrony node offset và độ trễ audit pipeline. Khi sự cố xảy ra, timeline phải phân biệt **IdP authenticated** trước **SP validated callback**, ngay cả khi event nhận ở SIEM bị đảo thứ tự.

## 15. Spring Security: Authentication events có sẵn

Tài liệu Spring Security Servlet **Authentication Events** nêu `AuthenticationSuccessEvent` và `AbstractAuthenticationFailureEvent`, phát thông qua `AuthenticationEventPublisher`; mẫu `DefaultAuthenticationEventPublisher` có thể nối với Spring `ApplicationEventPublisher`:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationAuditWiring {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new DefaultAuthenticationEventPublisher(
                applicationEventPublisher);
    }
}
~~~

Đây là **Spring project fragment**, cần Spring dependencies và security configuration thực tế; không chạy bằng `javac` thuần. Có thể lắng nghe:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.LogoutSuccessEvent;

@Component
public class FederationAuthenticationAuditListener {

    private final SecurityAuditSink sink;

    public FederationAuthenticationAuditListener(SecurityAuditSink sink) {
        this.sink = sink;
    }

    @EventListener
    public void onAuthenticationSuccess(AuthenticationSuccessEvent event) {
        sink.record("LOGIN_AUTHENTICATED", "SUCCESS", "NONE");
    }

    @EventListener
    public void onAuthenticationFailure(AbstractAuthenticationFailureEvent event) {
        sink.record("LOGIN_REJECTED", "DENIED",
                mapToAllowedReasonCode(event.getException()));
    }

    @EventListener
    public void onLogoutSuccess(LogoutSuccessEvent event) {
        sink.record("LOGOUT_LOCAL_COMPLETED", "SUCCESS", "NONE");
    }

    private String mapToAllowedReasonCode(Exception error) {
        // Only return allowlisted reason enums; never log error.getMessage().
        return error.getClass().getSimpleName().equals("BadCredentialsException")
                ? "BAD_CREDENTIALS" : "AUTHENTICATION_FAILED";
    }
}
~~~

Ở fragment này, **`SecurityAuditSink` là interface do ứng dụng phải tự triển khai**; đây **không phải class chuẩn của Spring**. Việc mapping exception bằng tên class chỉ là minh họa; production nên dùng typed whitelist trên các exception classes được phê duyệt để không làm rò implementation details.

**Lưu ý cực quan trọng về tính đầy đủ:**

- `AuthenticationEventPublisher` chủ yếu gắn với `AuthenticationManager`/`ProviderManager`; **không bảo đảm mọi login OIDC/SAML/CAS, request pre-auth, redirect và all SLO paths đều tự phát đúng cùng một event** theo mọi config.
- `DefaultAuthenticationEventPublisher` có mappings cho nhiều exception types nhưng theo docs nó dùng **exact exception class match**, subclasses và custom exceptions có thể cần mappings bổ sung hoặc catch-all.
- `LogoutSuccessEvent` gắn với logout processing của Spring; **không tự chứng minh OIDC/SAML global logout đã xác nhận**.
- Authentication success/failure **khác** authorization denied. Cần instrument 403/resource access decision riêng (có privacy policy và sampling/cost strategy).

Với web federation, hãy **thử thực tế** các success/failure handlers của `oauth2Login(...)`, `saml2Login(...)`, CAS filter/provider và logout handlers. Nếu publisher không bao phủ một stage, instrument một **authentication success/failure handler hoặc provider-specific hook** phù hợp, tránh ghi duplicate hoặc “thành công trước validation”.

## 16. Authentication success/failure handlers: tránh phá flow mặc định

Servlet AuthenticationSuccessHandler/AuthenticationFailureHandler có thể bổ sung audit quanh login browser. Nhưng nếu thay handler trong `oauth2Login` hoặc `saml2Login`, bạn cũng có thể vô tình **bỏ hành vi SavedRequestAwareAuthenticationSuccessHandler, session strategy hoặc redirect hợp lệ**.

Một pattern an toàn là **delegate**:

~~~java
// Spring Security integration fragment; not standalone Java.
AuthenticationSuccessHandler savedRequestHandler =
        new SavedRequestAwareAuthenticationSuccessHandler();

AuthenticationSuccessHandler auditedSuccess =
        (request, response, authentication) -> {
            auditSink.recordVerifiedLogin(authentication, request);
            savedRequestHandler.onAuthenticationSuccess(
                    request, response, authentication);
        };

// .oauth2Login(oauth -> oauth.successHandler(auditedSuccess))
// or a protocol-specific success handler with same delegation rules.
~~~

Tuy nhiên nếu `auditSink` throw exception, hành vi login có thể thay đổi; phải có failure policy rõ. **Không** tự log raw `authentication.getCredentials()`, `getDetails()` hoặc `request.getParameterMap()`. Ghi identity **sau** provider validation, và dùng registration/issuer từ verified security context.

**Đếm một login một lần:** nếu vừa lắng nghe `AuthenticationSuccessEvent` vừa cài success handler, có thể có **hai audit records cho cùng flow**. Quy định một event là canonical cho `LOGIN_AUTHENTICATED`, hoặc dùng distinct phases và `event_id`/`interaction_id` để dedup/aggregate.

## 17. Spring Boot Actuator auditing

Spring Boot Actuator có framework auditing qua `AuditEventRepository`. Theo tài liệu Boot:

- Có thể cung cấp bean `AuditEventRepository` để bật tính năng audit.
- Mặc định với Spring Security, auditing cung cấp một số sự kiện **authentication success/failure và access denied**.
- `InMemoryAuditEventRepository` chỉ tiện cho **development**, không phù hợp làm durable production audit.
- Có thể tạo custom `AuditEventRepository` và phát `AuditApplicationEvent` cho business/config changes.
- Muốn tùy biến security event mapping có `AbstractAuthenticationAuditListener` và `AbstractAuthorizationAuditListener`.

Ví dụ minh họa ghi một **custom audit event** khi partner config được duyệt:

~~~java
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.stereotype.Service;

@Service
public class PartnerAuditService {
    private final AuditEventRepository auditRepository;

    public PartnerAuditService(AuditEventRepository repository) {
        this.auditRepository = repository;
    }

    public void recordApprovedChange(
            String adminReference,
            String partnerKey,
            String revision) {
        AuditEvent event = new AuditEvent(
                adminReference,
                "PARTNER_CONFIG_APPROVED",
                Map.of("partnerKey", partnerKey,
                       "newRevision", revision));
        auditRepository.add(event);
    }
}
~~~

Đoạn trên **cần Spring Boot Actuator dependency** và là fragment, không chứa logic duyệt thay đổi hay transactional consistency. `adminReference`, `partnerKey` và `revision` phải là identifiers đã được xác minh/allowlisted; không truyền raw HTTP params hoặc raw metadata vào `Map`. Không lưu secret value/diff trong audit event.

**Lưu ý:** Actuator auditing, Spring Security application events và custom SIEM event sink **không đồng nhất hoàn toàn**; có thể dùng một hoặc kết hợp, nhưng tránh duplicate. Việc expose endpoint `/actuator/auditevents` (nếu có trong version) phải được giới hạn và kiểm; không công khai event data cho Internet.

## 18. Audit đối tác phải gắn với transaction/config revision

Đối với thay đổi trust configuration, chỉ gọi `auditRepository.add` **sau commit** có thể dẫn đến:

~~~text
DB config commit SUCCESS
Audit insert FAIL
=> partner trust changed, but no durable audit evidence
~~~

Chỉ ghi audit trước khi commit cũng có rủi ro:

~~~text
Audit insert SUCCESS
DB config rollback
=> audit claims ACTIVATED though trust never changed
~~~

**Transactional outbox** là một pattern:

1. Begin transaction trên configuration database.
2. Validate permissions/approval/expected revision.
3. Persist new partner config revision.
4. Persist **outbox audit event** với `event_id`/`old_revision`/`new_revision` trong cùng transaction.
5. Commit hoặc rollback **cả hai**.
6. Async worker gửi outbox event tới broker/SIEM; retry với backoff.
7. Consumers deduplicate theo `event_id` (at-least-once delivery).
8. Monitor outbox backlog/age, ingest errors và reconciliation.

Ví dụ pseudocode:

~~~text
@Transactional
activatePartnerChange(changeId, expectedOldRevision):
    requireAuthenticatedActor()
    requireApprovedChange(changeId)
    requireFourEyesIfRequired()
    old = partnerStore.loadForUpdate(partnerKey)
    assert old.revision == expectedOldRevision
    new = validateNewConfigAndCreateRevision(old, changeId)
    partnerStore.save(new)
    outboxStore.append(
        eventId = randomUnique(),
        type = PARTNER_CONFIG_ACTIVATED,
        actorRef = trustedActor,
        partnerKey = new.partnerKey,
        oldRevision = old.revision,
        newRevision = new.revision,
        changedFields = auditedAllowlist,
        occurredAt = serverUtcNow)
    COMMIT
~~~

**Đây là pseudocode, không phải Spring bean đầy đủ**. DB transaction không tự bao gồm IdP metadata server, Kubernetes rollout hoặc remote SIEM; cần **hai loại event**: “revision committed” và “effective on node(s)” và có trạng thái pending/failed/rolled back.

### Không hứa exactly-once

Broker/collector thường có **at-least-once**; retry có thể tạo duplicate. Giữ `event_id` ổn định trên retry, idempotency/dedup tại sink và consumer; audit events cần append-only nhưng duplicate transport phải được giải thích. Không tạo event_id mới sau mỗi retry nếu đó vẫn là cùng logical event.

### Nếu audit sink bị lỗi phải làm gì?

Không có đáp án chung:
- Với **thay đổi cấu hình trust trọng yếu**, fail closed hoặc yêu cầu durable local outbox trước commit có thể là policy đúng.
- Với **login runtime**, đợi remote SIEM đồng bộ có thể gây outage; có thể ghi vào durable local buffer/queue với health alerts/backpressure và retention đã định.
- Nếu **không thể lưu tối thiểu một security event** theo yêu cầu quản trị, có thể cần ngăn high-risk operation hoặc kích hoạt degraded-mode policy.
- Không âm thầm catch mọi lỗi rồi tiếp tục và vẫn báo “audit complete”.
- Không log raw credentials để “bù” cho SIEM mất kết nối.

Cần định nghĩa RPO/RTO, maximum lost events, retry, dead-letter policy và xử lý incident khi mất audit pipeline.

## 19. Audit log injection và field classification

Một message như:

~~~text
INFO login rejected user=guest
SUCCESS user=admin    <-- injected newline by attacker
~~~

có thể xuất hiện nếu log đưa raw `username`/`partner displayName` chứa CR/LF vào text. Để phòng:

1. Dùng **JSON structured logger/encoder** có escaping.
2. **Giới hạn độ dài, ký tự và nguồn tin cậy** của mỗi field.
3. Audit enum cho `event_type`, `stage`, `outcome`, `reason_code`.
4. User/partner identifiers lấy từ internal canonical IDs thay vì request body.
5. Không cho untrusted input điều khiển message template hoặc JSON keys.
6. Trước SIEM, bỏ hoặc sanitize mọi sensitive HTTP attributes (headers, query, body).
7. Dùng field schema validation và loại event lỗi schema với cảnh báo an toàn; không làm mất toàn bộ event nếu chỉ một field không hợp lệ.
8. Test CR, LF, Unicode control characters, log delimiter, huge string, UTF-8 encoding, JSON escaping và id injection.
9. Bảo vệ collection endpoint bằng mTLS/workload identity và rate limits, không cho Internet POST audit giả.
10. Ghi nhận source authenticity và phân biệt untrusted callback với trusted event.

**Parameterized SLF4J logging không tự xử lý toàn bộ CRLF log injection** nếu encoder in nguyên giá trị chuỗi có newline. OWASP khuyến nghị structured output cùng canonicalization/validation phù hợp.

## 20. Java 17 tự chạy: một audit event chỉ chứa field được phép

Chương trình dưới đây chỉ dùng **JDK 17**, không có Spring/IdP/network. Nó chứng minh cách xây một **mô hình audit có event enums và field allowlist**, cách phân biệt success login/local logout/partner change và cách chặn input chứa newline. Code **không tự đăng nhập OIDC/SAML, không xác minh tickets, không gửi SIEM**; chỉ mô phỏng lớp chuẩn hóa dữ liệu sau khi application đã có trust context.

Tạo file **`FederationAuditDemo.java`**:

~~~java
import java.time.Instant;
import java.util.List;

public class FederationAuditDemo {

    enum EventType {
        LOGIN_AUTHENTICATED, LOGIN_REJECTED,
        LOGOUT_LOCAL_COMPLETED, PARTNER_CONFIG_ACTIVATED
    }

    enum Outcome { SUCCESS, DENIED }

    record AuditEvent(
            Instant time,
            EventType type,
            String partnerKey,
            String actorRef,
            Outcome outcome,
            String correlationId,
            String changedField) {}

    static String safeId(String text) {
        if (text == null ||
                !text.matches("[A-Za-z0-9_-]{1,32}")) {
            return "REDACTED";
        }
        return text;
    }

    static String safeChangedField(String field) {
        return switch (field) {
            case "signing_cert_fingerprint",
                 "metadata_url",
                 "client_id",
                 "role_mapper" -> field;
            default -> "NONE";
        };
    }

    static String render(AuditEvent event) {
        return event.time() + " " + event.type()
                + " partner=" + safeId(event.partnerKey())
                + " actor=" + safeId(event.actorRef())
                + " outcome=" + event.outcome()
                + " corr=" + safeId(event.correlationId())
                + " changed=" + safeChangedField(
                    event.changedField());
    }

    public static void main(String[] args) {
        Instant start = Instant.parse(
                "2026-11-07T03:00:00Z");

        List<AuditEvent> events = List.of(
                new AuditEvent(start,
                    EventType.LOGIN_AUTHENTICATED,
                    "corp_oidc", "user_42",
                    Outcome.SUCCESS, "int_100", "none"),

                new AuditEvent(start.plusSeconds(60),
                    EventType.LOGOUT_LOCAL_COMPLETED,
                    "corp_oidc", "user_42",
                    Outcome.SUCCESS, "int_101", "none"),

                new AuditEvent(start.plusSeconds(120),
                    EventType.PARTNER_CONFIG_ACTIVATED,
                    "corp_saml", "admin_7",
                    Outcome.SUCCESS, "chg_402",
                    "signing_cert_fingerprint"),

                new AuditEvent(start.plusSeconds(180),
                    EventType.LOGIN_REJECTED,
                    "evil\nLOGIN_AUTHENTICATED", "guest\nadmin",
                    Outcome.DENIED, "int_102", "none")
        );

        StringBuilder log = new StringBuilder();
        for (AuditEvent event : events) {
            String line = render(event);
            log.append(line).append('\n');
            System.out.println(line);
        }

        // Fake secrets simulate data present elsewhere in a request.
        String sampleToken = "FAKE-ACCESS-TOKEN-NEVER-LOG";
        String sampleTicket = "ST-FAKE-TICKET-NEVER-LOG";

        boolean noSecrets =
                !log.toString().contains(sampleToken)
                && !log.toString().contains(sampleTicket);

        System.out.println("No credentials in audit: "
                + noSecrets);

        System.out.println("CRLF input rejected: "
                + log.toString().contains(
                    "partner=REDACTED actor=REDACTED"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FederationAuditDemo.java
java FederationAuditDemo
~~~

**Stdout chính xác:**

~~~text
2026-11-07T03:00:00Z LOGIN_AUTHENTICATED partner=corp_oidc actor=user_42 outcome=SUCCESS corr=int_100 changed=NONE
2026-11-07T03:01:00Z LOGOUT_LOCAL_COMPLETED partner=corp_oidc actor=user_42 outcome=SUCCESS corr=int_101 changed=NONE
2026-11-07T03:02:00Z PARTNER_CONFIG_ACTIVATED partner=corp_saml actor=admin_7 outcome=SUCCESS corr=chg_402 changed=signing_cert_fingerprint
2026-11-07T03:03:00Z LOGIN_REJECTED partner=REDACTED actor=REDACTED outcome=DENIED corr=int_102 changed=NONE
No credentials in audit: true
CRLF input rejected: true
~~~

### Giải thích code

- `Instant` giúp audit logs có timestamp UTC ổn định cho cùng một input.
- `EventType` và `Outcome` là enum; caller không thể tự chèn chuỗi `event_type` tùy tiện trong record type.
- `safeId` chỉ cho ký tự ID dạng `[A-Za-z0-9_-]`, tối đa 32; dữ liệu không đúng chuẩn bị thay bằng **REDACTED** thay vì được in dưới dạng nhiều dòng.
- `safeChangedField` chỉ cho phép **tên các field** được phê duyệt; không ghi giá trị secret, diff thô, PEM hoặc certificate body.
- `LOGOUT_LOCAL_COMPLETED` không bị đổi tên thành global logout.
- `PARTNER_CONFIG_ACTIVATED` ghi tên trường thay đổi **signing_cert_fingerprint**, không có private key.
- Hai fake credentials được tạo trong demo nhưng **không được đưa vào AuditEvent**. Kết quả `No credentials in audit: true` chỉ chứng minh hàm render trong ví dụ này không in hai chuỗi giả, **không chứng minh access logs/APM của hệ thống thật đã sạch**.
- `CRLF input rejected: true` chứng minh malicious partner/actor string đã bị loại theo regex.
- Trong production, **không dựa chỉ vào regex**: phải có schema, source identity verification, JSON serialization, persistence, access control, dedup và reconciliation.

**Đối với ứng dụng thật:** luôn tạo `actor_ref` từ SecurityContext **đã xác minh**, `partner_key` từ approved registration/config, `correlation_id` do server tạo. Nếu client gửi `actorRef=user_42` trong HTTP parameter, dù pass regex **vẫn không được coi là trusted actor**.

## 21. Ma trận kiểm thử toàn tuyến

| ID | Tình huống | Kết quả audit mong đợi |
| --- | --- | --- |
| L01 | OIDC login đúng chữ ký/issuer, session lập | `LOGIN_AUTHENTICATED` và stage session nếu có |
| L02 | OIDC callback chỉ nhận code chưa exchange | **Không** phát login success trước verify |
| L03 | OIDC invalid state/nonce | `LOGIN_REJECTED`, bounded error code |
| L04 | OIDC token `iss` khác IdP | Reject và partner context không được giả tin |
| L05 | SAML signature invalid | `LOGIN_REJECTED`/`SIGNATURE_INVALID`; không raw assertion |
| L06 | SAML decrypt wrong key | `DECRYPTION_FAILED`, không authenticated |
| L07 | SAML expired/NotBefore | Reason stage time; không in full XML |
| L08 | SAML Assertion valid nhưng thiếu required tenant | `LOGIN_POLICY_DENIED` hoặc explicit attribute-contract stage |
| L09 | SAML group Domain Admins không approved app role | Không tạo ROLE_ADMIN, audit deny nếu truy cập role protected |
| L10 | CAS valid ST, service đúng | Login authenticated sau ticket validation |
| L11 | CAS ST replay | `LOGIN_REJECTED`/`TICKET_REPLAY` |
| L12 | CAS ST nằm trong query | Ingress/APM/app audit **không** chứa raw ticket |
| L13 | User A/B cùng username ở hai IdPs | Audit phân biệt trusted partner/issuer namespace |
| L14 | MFA thất bại ở IdP, SP không nhận callback | IdP audit failure; SP không tạo login success |
| L15 | LDAP/AD account disabled phía IdP | Login rejected theo observed policy, không log password |
| L16 | Spring auth thành công nhưng endpoint 403 | Tách authenticate success và authorization deny |
| L17 | Login bị retry/redirect nhiều lần | Không tạo login success trùng không kiểm soát |
| O01 | GET /logout chỉ hiển thị confirmation | Không phát local logout completed |
| O02 | POST /logout, session invalidated | `LOGOUT_LOCAL_COMPLETED` |
| O03 | OIDC RP initiated redirect tới OP | `LOGOUT_SLO_DISPATCHED`, chưa confirmed |
| O04 | OIDC back-channel Logout Token invalid | `LOGOUT_SLO_REJECTED`, không hủy tùy tiện |
| O05 | OIDC back-channel valid, matching sid/sub | Audit session revocation thực sự theo scope |
| O06 | SAML SP-initiated SLO valid response | `LOGOUT_SLO_CONFIRMED` theo correlation |
| O07 | SAML IdP-initiated bad signature | Reject; session action chỉ theo policy được kiểm |
| O08 | SAML valid IdP-initiated logout | Local session cleared, signed response theo flow |
| O09 | CAS back-channel message tới sai service | Reject/ignore theo validator, không confirmed |
| O10 | Session timeout | `SESSION_EXPIRED`, không `USER_LOGOUT` |
| O11 | Browser đóng tab | Không tự sinh giả local logout |
| O12 | IdP logout chỉ một SP | Không tuyên bố tất cả apps đã logout |
| P01 | Admin đề nghị thêm IdP mới | `PARTNER_CONFIG_PROPOSED` |
| P02 | Reviewer phê duyệt | `PARTNER_CONFIG_APPROVED` + approver ref |
| P03 | Approval missing, attempt enable partner | Operation denied + change audit |
| P04 | Rotate IdP signing public cert | Old/new public fingerprint refs + key use |
| P05 | Đổi SP private decryption key | Ghi secret reference/version **không ghi bytes** |
| P06 | Đổi OIDC redirect URI ra domain lạ | Validation/approval deny |
| P07 | Role mapper thay thành admin rộng | Audit diff field name/approval, alert high severity |
| P08 | Metadata download mới nhưng chưa activated | `OBSERVED` khác `ACTIVATED` |
| P09 | Revision DB commit nhưng SIEM down | Outbox tồn tại và retry, không mất event |
| P10 | Deploy v4 tới node A nhưng node B còn v3 | Effective revision per-node detectable |
| P11 | Rollback v4→v3 | `PARTNER_CONFIG_ROLLED_BACK` và links |
| P12 | Admin cố xóa/sửa event cũ | Permission deny + audit access violation |
| S01 | Raw `Authorization`/`Cookie`/`SAMLResponse` trong HTTP input | Không có trong output audit, WAF/APM/logs |
| S02 | Username/partner CRLF injection | Structured escaping/allowlist, không tạo fake events |
| S03 | Very long error text | Truncated/omitted, event vẫn ghi reason code |
| S04 | Duplicate delivery do retry | Same event_id, consumer dedup |
| S05 | SIEM/collector outage | Alert, buffered delivery theo declared durability |
| S06 | Clock skew của IdP/SP nodes | UTC/instance metadata cho điều tra, không phán đoán sai |
| S07 | Actor source bị spoof từ X-User header | Không gán trusted actor |
| S08 | Audit endpoint bị mở public | Endpoint protected, access control tested |
| S09 | Retention hết kỳ | Dữ liệu xóa/archived theo policy, preserve legal hold |
| S10 | Incident cần truy vấn theo change ID | Có liên kết change–approval–deploy–auth failures |

**Đạt test chỉ khi kiểm cả nguồn phát và sink thực**, không chỉ mock một phương thức `auditSink.record(...)`. Với callback URLs chứa code/ticket, kiểm reverse proxy/WAF/APM riêng; với SAML POST kiểm HTTP body capture. Test không dùng production tokens, signing keys hoặc email thật.

## 22. Kịch bản điều tra: login bỗng thất bại sau thay IdP signing certificate

Ví dụ giả định:

~~~text
03:00  PARTNER_CONFIG_APPROVED change=chg_402 rev_3->rev_4
03:02  PARTNER_CONFIG_ACTIVATED node=sp_1 revision=rev_4
03:03  PARTNER_CONFIG_ACTIVATED node=sp_2 revision=rev_3 (stale)
03:04  LOGIN_REJECTED node=sp_2 reason=SIGNATURE_INVALID
03:05  LOGIN_AUTHENTICATED node=sp_1 revision=rev_4
~~~

Trong điều tra:

1. Xác nhận event timestamp UTC, clock sync và event ingestion lag.
2. Truy vấn `partner_key`, `change_id`, `new_revision`, `instance`.
3. So **trust anchor public certificate fingerprints** đã reviewed, không in PEM/private keys.
4. Kiểm metadata refresh/failover và immutable config snapshot trên từng pod.
5. Kiểm issuer/EntityID/audience/ACS không đổi ngoài dự kiến.
6. Nếu cần rollback, lập `PARTNER_CONFIG_ROLLED_BACK` với actor/approval/incident.
7. Kiểm login success/failure sau rollout bằng synthetic test identity.
8. Không “sửa nhanh” bằng tắt signature validation; đó là thay đổi security nghiêm trọng cần được audit và thường phải từ chối.

**Một access log HTTP 302 không thể giải thích nguyên nhân.** Cặp `partner_revision + instance` trong audit record mới cho thấy fail chỉ ở node chưa update.

## 23. Kịch bản điều tra: user nói đã logout nhưng API vẫn dùng được

Timeline có thể là:

~~~text
10:00  LOGOUT_REQUESTED origin=USER
10:00  LOGOUT_LOCAL_COMPLETED app=reports-sp
10:00  LOGOUT_SLO_DISPATCHED protocol=OIDC
10:01  No verified OP confirmation observed
10:02  API request accepted using existing Access Token (not yet expired)
~~~

**Không kết luận ngay logout implementation lỗi**: Browser session của Spring, IdP SSO session và **Access Token của API** có lifetimes/revocation khác nhau. Hãy hỏi:

- Local session bị invalidated chưa?
- OP end_session request có thực sự hoàn thành không?
- Back-channel logout có được cấu hình/validate và match session không?
- API kiểm JWT offline tới `exp` hay introspection/revocation?
- User có refresh token hoặc client khác không?
- Security policy yêu cầu access bị ngắt ngay hay trong SLA xác định?
- Có mismatch `sid`/`sub`/audience khiến logout notification không match local session?

**Audit phải ghi phạm vi và kết quả được chứng minh**, không gán `GLOBAL_LOGOUT_COMPLETED` chỉ vì browser chuyển đến trang “Đã đăng xuất”.

## 24. Phát hiện bất thường và cảnh báo

Có thể định nghĩa alert dựa trên series:

| Rule | Tín hiệu | Cẩn trọng |
| --- | --- | --- |
| Tăng `LOGIN_REJECTED` do `SIGNATURE_INVALID` sau config change | Sai cert hoặc tấn công giả IdP | Correlate approved rev/deploy; không log assertion |
| Nhiều `LOGIN_REJECTED` cùng partner | Provider outage, abuse hoặc claims issue | Rate-limit alert/sampling; không lộ username |
| Failed logins lặp trên một actorRef | Credential attack hoặc account lockout | Với pre-auth failures có thể chưa có verified actor |
| SAML replay detection tăng | Replay attempts hoặc duplicate POST | Kiểm replay store/network retry |
| `LOGOUT_SLO_DISPATCHED` nhiều nhưng không confirmed | IdP SLO lỗi/callback blocked | Có flow không kỳ vọng confirmation |
| Metadata signing fingerprint thay đổi đột ngột | Cert rotation hoặc compromise | So approved metadata/certificate pinning |
| Partner issuer/redirect URI đổi ngoài change window | Unauthorized trust change | Escalate security |
| Partner config activated trên một subset nodes | Rollout drift/metadata cache | Compare effective revision per instance |
| Audit queue backlog/age tăng | SIEM/broker outage | Durability, retry, DLQ/alert |
| Audit volume giảm bất thường về 0 | Event source bị vô hiệu hoặc pipeline hỏng | Canary synthetic event |
| Actor và approver trùng trong high-risk change | Vi phạm four-eyes policy | Review approval/trust source |
| Repeated emergency rollback | Config quality/trust instability | Change review và automated tests |

**Không tạo metric labels theo raw user ID/email/token**; tránh high cardinality và privacy disclosure. Aggregate theo event_type/partner_key/stage/reason_code/environment, rồi drill-down audit store có phân quyền khi cần.

## 25. Chất lượng, retention và quyền truy cập audit

Để audit dùng được trong điều tra lâu dài:

- **Integrity**: event append-only, hạn chế update/delete, bất kỳ admin sửa access policy cũng phải audit.
- **Availability**: collector/queue/DB HA, retry, idempotency và backlog monitoring.
- **Confidentiality**: encryption in transit/at rest, RBAC/ABAC cho truy vấn, limit exports, redact PII.
- **Retention**: chính sách phù hợp nghĩa vụ pháp lý/tổ chức; không mặc định giữ vĩnh viễn.
- **Subject access/privacy**: truy vấn/xóa theo quy định áp dụng, có legal hold khi hợp lệ, không làm giả lịch sử.
- **Clock**: UTC `Instant`, time source tin cậy, ingestion timestamp và node ID.
- **Schema evolution**: `schema_version`, backwards-compatible field changes; không đổi ý nghĩa event mà giữ cùng type/version.
- **Security of auditing**: audit agent, SIEM API token và storage credentials được rotation, không xuất hiện trong audit content.
- **Operational resilience**: bounded queue, backpressure, DLQ, dead-letter access reviews, disk-full alerts.
- **Change provenance**: source system, actor/authenticated workload, approval ticket, config commit digest, effective revision.
- **Privacy by design**: không cần IP/device fingerprint/geo location nếu use case không yêu cầu; nếu cần, phân loại như personal data và có retention/access rõ.

Nếu event bị redacted một field, nên **ghi một reason code rằng một field đã bị loại**, không cố giữ raw value bị loại trong hidden payload “để debug sau”.

## 26. Những anti-pattern phải tránh

### A. Chỉ dựa vào HTTP 200/302 để đếm login thành công

302 có thể là redirect tới trang lỗi, retry hoặc login start; chỉ count sau Spring authentication success/verified session.

### B. Ghi nguyên request URL hoặc `Authentication.toString()`

Callback có thể mang CAS ST/OIDC code/state/SAMLResponse, principal có thể chứa attributes/PII. Dùng approved fields và correlation ID riêng.

### C. Coi `LogoutSuccessEvent` là chứng minh global SLO

Sự kiện Spring logout thường phản ánh **local logout**; remote IdP/SP sessions cần observation/validation riêng.

### D. Chỉ ghi “updated partner” không old/new revision

Không thể truy ra cert, issuer, role mapper nào đã gây lỗi. Ghi field names, revision/fingerprint references, actor, approval và effective nodes, không secrets.

### E. Dùng in-memory audit repository trên production

Pod restart/rollout mất evidence và không bảo đảm retention. Spring Boot khuyến cáo `InMemoryAuditEventRepository` cho development; production dùng durable implementation.

### F. Bắt mọi audit exception rồi coi vẫn thành công

Mất audit pipeline có thể bỏ qua sự kiện quan trọng. Có durable queue/outbox, health alerts và failure policy theo risk.

### G. Một event per handler tạo duplicate đếm login

`AuthenticationEventPublisher`, success handlers và Boot audit có thể cùng nhìn một flow. Thiết kế canonical sources, `event_id` và dedup.

### H. Đưa raw user input vào SIEM như trusted event

CRLF/log injection, actor spoofing và unauthorized partner metadata đều phải phân loại/validate; **không cho HTTP parameter quyết định trusted actor**.

### I. Dùng token hoặc `state` làm correlation ID

Đây là dữ liệu nhạy cảm. Generate independent random IDs, không chuyển credentials qua observability.

### J. Chỉ ghi config proposal mà không ghi revision activated

Approval chưa chắc deploy. Một node có thể dùng config cũ; audit cần effective revision/rollback event.

### K. Ghi secret diff hoặc certificate private key

Chỉ ghi **tên field, public certificate fingerprint, secret reference/version**, không raw secret/PEM, hashed low-entropy client secret hay raw Assertion.

## 27. Checklist bàn giao vận hành

- [ ] Có event taxonomy riêng cho login start, callback, authentication success/failure và authorization denied.
- [ ] Phân biệt IdP-side authentication và Spring-side validated login.
- [ ] OIDC code/state, SAMLResponse, CAS ticket không lọt ingress/app/APM/SIEM logs.
- [ ] Chỉ tạo trusted actor/subject sau authentication hoặc management workload verification.
- [ ] Có partner registration key, config revision, environment, service/instance, event time UTC và interaction ID.
- [ ] `AuthenticationEventPublisher`/Spring events được dùng đúng; mappings custom exceptions đã test.
- [ ] Spring Boot Actuator audit có durable repository cho production, không chỉ InMemoryAuditEventRepository.
- [ ] Không đếm duplicate khi vừa có event listener vừa có success handler.
- [ ] Local logout, SAML SLO, OIDC RP/back-channel logout và CAS logout được audit theo stages riêng.
- [ ] Không đánh dấu remote/global logout completed nếu không có evidence được validate.
- [ ] Session timeout không bị đếm như user-initiated logout.
- [ ] Partner config proposed/approved/activated/rollback đều có audit records.
- [ ] Thay trust anchor/cert/issuer/redirect URI/role mapper là high-risk change có approval/audit.
- [ ] Có old/new revision và changed-field allowlist; không raw secrets/private keys.
- [ ] Phân biệt metadata observed và trusted revision activated.
- [ ] Effective config revision được xác minh per node/tenant khi cần.
- [ ] Partner config và audit outbox lưu atomically trong DB transaction.
- [ ] SIEM retries idempotent theo event_id, có backlog/dead-letter monitoring.
- [ ] Structured JSON logging, output escaping và CRLF/oversized-input tests.
- [ ] Không dùng raw HTTP header/query/params làm actor hoặc event type.
- [ ] Audit endpoint và dữ liệu có RBAC, encryption, retention, legal hold phù hợp.
- [ ] Logs và metrics không chứa raw user identifiers/PII ngoài use case cho phép.
- [ ] Kiểm 401/403, wrong issuer/signature, replay, failed SLO và change rollback E2E.
- [ ] Có synthetic canary event để phát hiện audit pipeline im lặng.
- [ ] Có runbook điều tra theo partner/revision/instance/correlation ID.
- [ ] Đã thử incident response nếu một secret bị lộ vào logs, gồm revoke/purge/notify khi cần.

## 28. Tài liệu chính thức và nguồn tham khảo

1. [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): `AuthenticationEventPublisher`, `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent`, exception mappings.
2. [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, `LogoutHandler`, `LogoutSuccessEvent`, default local logout và customization.
3. [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, `OidcClientInitiatedLogoutSuccessHandler` và OIDC back-channel.
4. [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/IdP initiated logout, `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter`, signatures và status.
5. [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): verified OIDC/OAuth2 client authentication stages.
6. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML response validation, subject và trust configuration.
7. [Spring Security — CAS Authentication Filter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS ticket handling và service validation.
8. [Spring Boot Actuator — Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): `AuditEventRepository`, security audit, custom `AuditApplicationEvent`, InMemoryAuditEventRepository development only.
9. [Spring Security — LogoutSuccessEvent Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/LogoutSuccessEvent.html): event phản ánh logout.
10. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event attributes, data minimization, protection, log injection, integrity/retention.
11. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session IDs, logout và lifecycle.
12. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): validate issuer/signature/audience, prevent replay.
13. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token leakage, redirect/client security, modern OAuth threat model.
14. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): OIDC logout request/OP endpoint contract.
15. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token validation, session correlation.
16. [OASIS SAML2 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): SAML Web SSO/Single Logout profile semantics.
17. [Oracle Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): audit event times in UTC.
18. [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): trace/log correlation concepts, avoid credential attributes.

**Kết luận:** Nhật ký kiểm toán federation không phải một tập hợp raw HTTP logs. Nó là **chuỗi sự kiện có nguồn đáng tin, trạng thái rõ và bảo vệ dữ liệu**: đăng nhập sau protocol validation, đăng xuất với phạm vi local/SLO đúng thực tế, và thay đổi đối tác theo **proposed → approved → activated → rollback** cùng trust-config revisions. Tận dụng Spring Security authentication/logout events và Spring Boot auditing, nhưng chủ động instrument các bước SAML/OIDC/CAS, config changes và tính bền vững của pipeline. Với **allowlisted structured fields, append-only durable storage, outbox/retries, UTC correlation, secrets minimization và E2E negative tests**, đội vận hành có thể điều tra được “ai làm gì, khi nào, với đối tác nào và cấu hình nào” mà không tạo thêm một điểm rò rỉ token/private key.