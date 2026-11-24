# Session revocation – thu hồi phiên trong quản lý vòng đời danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Định nghĩa **session revocation** và phân biệt **thu hồi phiên** với logout, timeout, khóa tài khoản, thu hồi access token, refresh token, cookie và credential.
- Mô tả các lớp phiên trong **trình duyệt, ứng dụng, IdP/SSO, API, OAuth 2.0/OIDC, SAML, PAM, remote desktop, database và service-to-service**.
- Phân tích các cơ chế **server-side session invalidation, OAuth token revocation (RFC 7009), token introspection (RFC 7662), JWT denylist/session version, refresh-token rotation, OIDC logout** và khả năng/giới hạn của từng cơ chế.
- Thiết kế thu hồi **một phiên, toàn bộ phiên một identity, theo thiết bị, theo tenant, theo client, theo yếu tố rủi ro** và kiểm chứng hiệu lực ở từng tài nguyên.
- Áp dụng quy trình thu hồi theo **Joiner–Mover–Leaver**, sự cố chiếm tài khoản, reset credential, security block, chấm dứt hợp đồng và thay đổi quyền đặc quyền.
- Giải thích vì sao **IdP disabled, SCIM deactivation, JWT expired, RBAC role removed, logout** không phải lúc nào cũng đồng nghĩa tất cả đường truy cập đã bị chặn ngay.
- Thiết kế **PDP/PEP, revocation events, race-condition guards, cache/propagation controls, audit, reconciliation và SLA** để giảm quyền truy cập tồn dư.
- Áp dụng ví dụ **Java/Spring Security**, tình huống thực tế, checklist và bộ kiểm thử âm tính cho những trường hợp khó.

## 1. Session revocation là gì?

**Session revocation (thu hồi phiên)** là quá trình **làm mất hiệu lực quyền sử dụng một phiên hoặc trạng thái xác thực/ủy quyền đang tồn tại**, để các yêu cầu hoặc hành động tiếp theo không còn được chấp nhận trong phạm vi phải thu hồi.

Một phiên thường được tạo sau khi một identity chứng minh thông tin xác thực; hệ thống có thể lưu session ở server, phát session cookie, cấp access token hoặc gắn trạng thái ở IdP, API hay hệ thống đích. Khi cần chấm dứt quyền trước thời hạn tự hết hạn, tổ chức phải có **cơ chế thu hồi phù hợp với từng lớp**.

Ví dụ: một nhà thầu bị chấm dứt hợp đồng lúc 18:00. HRIS phát sự kiện **Leaver**, IdP disable account lúc 18:01, nhưng người đó vẫn có:

- Một phiên SaaS đã đăng nhập trước đó.
- Access token API JWT còn hạn 10 phút.
- Refresh token trên thiết bị di động.
- Phiên VPN và SSH đến máy chủ.
- Role ERP được cấp trực tiếp ngoài nhóm SSO.

**Disable IdP chỉ là một phần của offboarding.** Session revocation phải xét nơi có thể **tiếp tục thực thi quyền**, cùng khả năng làm mất hiệu lực các đường truy cập đó.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, bài học thuộc chương **Session management** và liên kết quản trị theo **Joiner–Mover–Leaver** với **HRIS/identity proofing, IdP, SSO, OAuth/OIDC, SAML, SCIM, RBAC/ABAC, PAM, tài khoản dịch vụ, kiểm toán và đối soát quyền tồn dư**.

### 1.1. Mục tiêu thực tế của thu hồi

Thay vì chỉ đặt một cờ `revoked=true`, cần trả lời:

1. **Thu hồi điều gì?** Browser session, refresh token, API access token, IdP session, PAM session hay credential?
2. **Của ai?** Human identity, service principal, device, account ở target hay delegated actor?
3. **Ở đâu?** Issuer, relying party, resource server, SaaS, gateway, database, VPN, cloud console hay máy chủ?
4. **Khi nào có hiệu lực?** Ngay lập tức, sau propagation, sau cache TTL hoặc khi token hết hạn?
5. **Bằng chứng nào xác nhận?** State tại issuer, kết quả tại PEP và thử lại thao tác trên target?
6. **Có còn đường khác?** Token đã phát, active TCP connection, refresh-token family, local role hoặc login trực tiếp?

**Thu hồi thành công là một khẳng định về hiệu lực truy cập theo phạm vi**, không chỉ là HTTP 200 từ một API điều khiển.

## 2. Session, token, cookie, credential và entitlement khác nhau

| Khái niệm | Chức năng | Ví dụ | Thu hồi tương ứng |
| --- | --- | --- | --- |
| **IdP session** | Ghi nhớ trạng thái đăng nhập tại nhà cung cấp danh tính | Trình duyệt đã SSO vào IdP | Hủy phiên IdP, phối hợp logout các ứng dụng |
| **Application session** | Ghi nhớ đăng nhập ở ứng dụng | Session lưu Redis/DB | Xóa/vô hiệu session server, kiểm session middleware |
| **Session cookie** | Mang session ID hoặc trạng thái bảo vệ | Cookie `HttpOnly`, `Secure` | Xóa ở trình duyệt và vô hiệu server state/khóa phù hợp |
| **OAuth access token** | Cho phép gọi resource API theo audience/scope | JWT hoặc opaque token | Revocation/introspection/denylist/TTL tùy kiến trúc |
| **OAuth refresh token** | Xin access token mới | Token được giữ trong ứng dụng | Revoke grant/family, kiểm rotation và replay |
| **OIDC ID token** | Mang thông tin xác thực người dùng cho client | Claims từ OIDC issuer | Không dùng thay access token; xử lý session/logout riêng |
| **Credential** | Bằng chứng đăng nhập/khóa | Password, passkey, client secret, private key | Rotate/revoke credential và kiểm các phiên đã phát |
| **Entitlement** | Quyền có thể thực thi | `invoice.approve`, `cloud.admin` | Gỡ role/group/grant, kiểm PEP và cache |
| **Transport connection** | Kết nối mạng hoặc remote session | SSH, RDP, VPN, WebSocket | Cắt kết nối/terminate process, kiểm credential |
| **PAM/JIT activation** | Quyền đặc biệt có thời hạn | DB admin 30 phút | Revoke elevation và phiên đang chạy |

### 2.1. Logout là một trường hợp của thu hồi, không phải mọi thu hồi

**Logout** thường do chính người dùng thực hiện để kết thúc một phiên. **Revocation** có thể xuất phát từ security, HRIS, IAM admin, policy hoặc sự kiện rủi ro mà người dùng không hề tương tác.

Ví dụ khi user bấm Logout ở một ứng dụng OIDC:

- Cookie ứng dụng có thể bị xóa.
- IdP session có thể vẫn còn.
- Access token đã cấp cho API khác có thể vẫn hoạt động.
- Thiết bị khác có thể còn phiên.
- Một SSH session độc lập không bị ảnh hưởng.

Vì vậy **“Đã logout” không đồng nghĩa “mọi phiên đã bị thu hồi”**.

### 2.2. Token khác session

Một JWT tự chứa có thể được resource server chấp nhận chỉ dựa trên chữ ký, issuer, audience, thời hạn và quyền. Nếu server **không hỏi trạng thái hiện hành**, việc issuer đặt session `REVOKED` không nhất thiết chặn JWT đó trước `exp`.

Ngược lại, một session ID tham chiếu tới state server có thể bị vô hiệu nhanh hơn nếu mọi request đều kiểm source of truth; nhưng nhiều replica/cache hoặc đường bypass vẫn có thể tạo độ trễ.

## 3. Vì sao session revocation là bài toán nhiều lớp?

Một người dùng có thể đi qua:

~~~mermaid
flowchart LR
    U["User / Device"] --> B["Browser cookie"]
    B --> APP["Application session"]
    APP --> IDP["IdP / SSO session"]
    APP --> API["API access token"]
    API --> PEP["Resource API / PEP"]
    IDP --> SAAS["Federated SaaS session"]
    U --> VPN["VPN session"]
    VPN --> SSH["SSH / DB / PAM session"]
    IGA["IAM / JML / Security event"] --> REV["Revocation orchestration"]
    REV --> IDP
    REV --> APP
    REV --> PEP
    REV --> SAAS
    REV --> VPN
    REV --> SSH
    REV --> AUD["Audit / Reconciliation"]
~~~

Đây là sơ đồ logic; không phải mỗi ứng dụng đều dùng tất cả các loại phiên. Có môi trường phát access token từ IdP trực tiếp cho frontend, có môi trường dùng **backend-for-frontend (BFF)** giữ token phía server, hoặc dùng opaque session ở API gateway.

### 3.1. Không có một nút toàn năng “revoke everything”

Một API của IdP có thể thu hồi **refresh tokens của IdP** nhưng không trực tiếp đóng **SaaS local session**. SCIM có thể disable user trong SaaS mà không chấm dứt kết nối SSH. PAM có thể đóng shell nhưng không xóa một API key do user tạo trước đó.

Thiết kế cần **ma trận loại phiên × hệ thống đích × cơ chế hỗ trợ × thời gian hiệu lực × cách xác minh**, không hứa thu hồi tức thì ở nơi nền tảng không hỗ trợ.

### 3.2. Trust boundary quan trọng

- **Identity source:** HRIS và identity registry nêu tình trạng chủ thể.
- **Authentication issuer:** IdP/Authorization Server nắm sessions, grants và tokens do mình phát.
- **Relying party/client:** ứng dụng dùng kết quả SSO và có session riêng.
- **Resource server/PEP:** API quyết định chấp nhận request tại thời điểm thực thi.
- **Target authorization:** SaaS, database, cloud role hoặc local ACL.
- **Runtime connections:** VPN, RDP, SSH, WebSocket, gRPC streams.
- **Audit/reconciliation:** xác minh điều mong muốn so với quyền thực tế.

Thu hồi bền vững đòi hỏi kiểm **cả nguồn phát chứng thực và điểm thực thi**.

## 4. Các kích hoạt thu hồi phiên

| Sự kiện | Phạm vi nên cân nhắc | Yêu cầu bổ sung |
| --- | --- | --- |
| **User logout** | Phiên hiện tại | Xóa cookie, vô hiệu state; phối hợp IdP tùy ngữ cảnh |
| **Sign out all devices** | Các session của cùng subject/client | Phân loại thiết bị, app, refresh families |
| **Password reset** | Có thể cần đóng sessions cũ theo risk | Không tự suy ra mọi token/SSO bị revoke |
| **Credential compromise** | Toàn bộ sessions và token liên quan | Containment, incident, credential rotation |
| **MFA reset/recovery** | Các phiên có assurance cũ | Step-up/re-auth, rà recovery methods |
| **Security block** | Các đường truy cập bị policy cấm | Chặn ở PEP/gateway và revoke token |
| **Joiner canceled** | Account/phiên preboarding đã mở | Hủy pending grants, active sessions |
| **Mover** | Phiên/quyền gắn role, group, tenant cũ | Recompute entitlements, deny permissions mới |
| **Leaver** | Các phiên thuộc relationship kết thúc | IdP, SaaS, PAM, VPN, service delegation |
| **Temporary elevation expiry** | Phiên PAM/JIT và role cao | Chặn tác vụ đặc quyền đang tiếp diễn |
| **Device lost/compromised** | Phiên và token gắn device | Revoke credential, account/device binding |
| **App/client retired** | Client sessions và grants | Remove client registration, refresh families |
| **Owner-driven revoke** | Entitlement cụ thể hoặc resource | Role removal + session/claim refresh |
| **Mass incident** | Nhóm người dùng/tenant hoặc key | Bulk revocation có guard và availability plan |

### 4.1. Quyền được thu hồi do Mover có thể khác toàn bộ phiên

Một người chuyển từ Sales sang Finance vẫn là nhân viên ACTIVE. Tổ chức có thể chỉ cần chặn quyền Sales và làm mới các phiên có claim cũ, **không nhất thiết hủy mọi phiên của mọi ứng dụng**.

Ngược lại, khi có nghi vấn **session hijacking**, biện pháp phù hợp có thể là thu hồi rộng hơn, buộc reauthentication và kiểm recovery factors.

### 4.2. Phạm vi dựa trên rủi ro

Phải chọn đúng **minimum effective scope**, tránh làm gián đoạn tất cả nhân viên do một sự cố của một thiết bị; nhưng cũng tránh scope quá hẹp làm attacker vẫn sử dụng được refresh token trên thiết bị khác.

## 5. Mô hình dữ liệu phiên và danh tính

Một session record đáng tin nên gắn với **identity ID bền vững**, nguồn cấp session và các ranh giới liên quan.

| Trường | Ví dụ | Vai trò |
| --- | --- | --- |
| **sessionId** | `sid-80f1` | Khóa định danh một phiên ở một issuer/application |
| **issuerId** | `corporate-idp` | Nguồn chịu trách nhiệm |
| **subjectIdentityId** | `person-1042` | Danh tính trong registry |
| **subjectIssuerAndSub** | `iss + sub` | Liên kết danh tính federation không phụ thuộc email |
| **relationshipId** | `employment-A-1042` | Cơ sở quyền theo JML |
| **clientId** | `finance-portal` | Ứng dụng/khách hàng sử dụng |
| **tenantId** | `tenant-a` | Phạm vi tenant |
| **deviceRef** | `managed-laptop-77` | Ràng buộc thiết bị nếu có |
| **authTime** | Timestamp | Lần authentication gốc |
| **assuranceContext** | `acr/amr` hoặc profile | Có thể cần step-up |
| **issuedAt/lastSeenAt** | Timestamp | Giám sát freshness |
| **absoluteExpiry** | Timestamp | Giới hạn thời gian tuyệt đối |
| **idleExpiry** | Timestamp | Giới hạn thời gian không hoạt động |
| **revokedAt** | Timestamp hoặc null | Thời điểm phát quyết định thu hồi |
| **revokeReason** | `LEAVER`, `SECURITY` | Nguyên nhân |
| **revocationVersion** | Số tăng đơn điệu | Chống token/session cũ |
| **policyRevision** | `session-policy-v6` | Kiểm tra quy tắc áp dụng |

Các trường là **schema minh họa**, không phải một bộ claim tiêu chuẩn áp cho tất cả sản phẩm. `sessionId` ở application có thể khác IdP `sid`, và không nên coi hai giá trị này đồng nhất nếu không có mapping được xác minh.

### 5.1. Session thuộc người hay thuộc relationship?

Một người có thể có nhiều quan hệ: nhân viên chính thức và hợp đồng tư vấn, hoặc quyền ở hai pháp nhân. Khi quan hệ A kết thúc, hệ thống nên biết phiên/quyền nào dựa trên A.

Nếu session thiếu `relationshipId`, phải dùng **provenance của role/access grants** để đánh giá. Không tự xóa mọi quyền của quan hệ B mà không kiểm căn cứ.

### 5.2. Session ID là bí mật hay không?

**Session ID được dùng làm bearer credential** thì phải được bảo vệ như bí mật: không log raw, không đưa vào URL hoặc telemetry. Audit có thể dùng **non-authenticating reference, hash phù hợp hoặc correlation ID riêng**; tránh khiến log trở thành nơi có thể chiếm phiên.

## 6. Vòng đời session và trạng thái thu hồi

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> ACTIVE: Authentication and policy PASS
    ACTIVE --> IDLE_EXPIRED: Idle deadline reached
    ACTIVE --> ABSOLUTE_EXPIRED: Max lifetime reached
    ACTIVE --> REVOKE_REQUESTED: Logout / JML / incident
    REVOKE_REQUESTED --> REVOKING: Dispatch to affected systems
    REVOKING --> REVOKED: Local invalidation confirmed
    REVOKING --> PARTIAL: Some targets unavailable
    PARTIAL --> REVOKING: Controlled retry
    REVOKED --> VERIFIED_DENIED: PEP/target denies use
    IDLE_EXPIRED --> VERIFIED_DENIED: PEP respects expiry
    ABSOLUTE_EXPIRED --> VERIFIED_DENIED: PEP respects expiry
    VERIFIED_DENIED --> [*]
~~~

Đây là state machine **giáo dục**. Trong một hệ stateless, không có session object tương ứng ở mỗi API; thay bằng grant state/`jti` denylist, epoch hoặc policy kiểm trạng thái hiện hành.

### 6.1. Những bất biến quan trọng

- `REVOKE_REQUESTED` **không đồng nghĩa** `VERIFIED_DENIED`.
- Một `REVOKED` session không được hoạt động lại vì retry hoặc replication lag.
- Reauthentication phải tạo **trạng thái mới**, không “gỡ” quyết định security block cũ khi policy vẫn DENY.
- Event cũ không được ghi đè revocation mới hơn; cần version/effectiveAt.
- Một session của tenant-a không bị nhầm với session cùng ID ở tenant-b.
- Target **UNKNOWN** không được đánh dấu `SUCCESS` chỉ vì API revocation timeout.
- User Leaver không được nhận phiên mới sau effective time qua một đường JIT khác.
- Acknowledgment từ issuer khác với hiệu lực từ mọi resource server.

### 6.2. Quyết định, gửi lệnh, áp dụng và xác minh

~~~text
Decision:       revoke because LEAVER
Dispatch:       event sent to IdP and SaaS
Applied:        IdP session invalidated
Target result:  SaaS app session still ACTIVE
Effective:      SaaS API still PERMIT
Conclusion:     PARTIAL / RESIDUAL_ACCESS
~~~

Không nên chỉ có một trường Boolean `success` cho toàn bộ quy trình nhiều hệ thống.

## 7. Server-side session invalidation

Một ứng dụng giữ session state trên server (DB/Redis/session store) có thể chặn session bằng cách xóa hoặc đánh dấu record **không còn hợp lệ**.

### 7.1. Luồng cơ bản

~~~text
Browser -> App: Cookie sessionId = sid-80f1
App -> Session store: lookup(sid-80f1)
Session store -> App: ACTIVE, identity=person-1042
App -> PEP: Check current authorization
PEP -> Browser: PERMIT

Security revokes sid-80f1:
  Session store: mark REVOKED / delete
  Subsequent lookup: INVALID
  App: respond 401/redirect to login as appropriate
~~~

### 7.2. Xóa cookie và vô hiệu server state là hai việc

Gửi `Set-Cookie` với thời hạn hết hiệu lực giúp browser xóa cookie nhưng **không vô hiệu hóa bản sao cookie bị đánh cắp** nếu server vẫn chấp nhận sessionId.

Ngược lại, vô hiệu hóa session ở server khiến cookie còn trên máy người dùng **không còn giá trị xác thực**. Trong thực tế nên làm cả hai đối với logout bình thường.

### 7.3. Session store phân tán

Với ứng dụng nhiều replica:

- Tất cả replica phải nhìn thấy **cùng trạng thái revocation**, hoặc cache có cơ chế invalidation.
- Redis/DB replication lag có thể gây cửa sổ chấp nhận session cũ.
- Không để một instance lưu state riêng rồi không nhận lệnh revoke từ instance khác.
- Tránh lỗi **session fixation** khi đăng nhập lại hoặc nâng assurance: rotate session identifier theo policy.
- Thiết lập TTL, idle timeout và absolute timeout nhất quán.
- Khi session store unavailable, endpoint nhạy cảm không được tự tạo “authenticated session” từ cookie chưa xác minh.

### 7.4. Xóa tại một node chưa phải thu hồi toàn hệ

Một API `invalidate(sessionId)` gọi thành công ở server A nhưng request tiếp theo tới B vẫn được PERMIT là **revocation propagation failure**. Test phải gửi request qua nhiều instance, region hoặc gateway để phát hiện.

## 8. JWT access token: vì sao khó thu hồi tức thì?

**JWT access token** thường là token có chữ ký, chứa claims như `iss`, `aud`, `sub`, `iat`, `nbf`, `exp` và scopes. Một resource server có thể xác minh token **offline** mà không hỏi issuer ở mỗi request.

### 8.1. Ví dụ JWT payload minh họa

~~~json
{
  "iss": "https://id.example.invalid",
  "sub": "person-1042",
  "aud": "finance-api",
  "iat": 1795431600,
  "exp": 1795432500,
  "scope": "invoice.read",
  "sid": "idp-session-80f1",
  "jti": "token-9a12",
  "tenant": "tenant-a"
}
~~~

Đây là JSON minh họa **claims**, không phải token có chữ ký. Tên và sự hiện diện của `sid`, `jti`, `tenant` phụ thuộc issuer/token profile. Không tự giả định mọi JWT đều có các claim này.

### 8.2. Kịch bản thu hồi không hiệu lực ngay

~~~text
09:00  JWT được phát, exp = 09:15
09:02  Security khóa user và revoke refresh token
09:03  Resource API chỉ verify JWT signature + exp
09:04  API vẫn có thể PERMIT bằng JWT cũ
09:15  JWT hết hạn và mới bị từ chối vì exp
~~~

**Thu hồi refresh token ngăn việc lấy token mới**, nhưng không mặc nhiên khiến mọi access token JWT đã phát bị resource server từ chối tức thì.

### 8.3. Các chiến lược giảm cửa sổ tồn dư

| Cơ chế | Lợi ích | Đánh đổi |
| --- | --- | --- |
| **Short-lived access token** | Giới hạn thời gian token bị lộ còn dùng được | Không bảo đảm thu hồi tức thì |
| **`jti` denylist** | Chặn token cụ thể trước `exp` | Cần store/cache và propagation |
| **Session/grant epoch** | Chặn toàn bộ token cũ của một session/identity | Cần online hoặc cache lookup tại PEP |
| **Introspection/reference token** | Kiểm active status tập trung | Tăng phụ thuộc issuer và latency |
| **Gateway/PDP current-state check** | Chặn khi lifecycle/role/security block đổi | Thêm availability/caching considerations |
| **Key rotation emergency** | Có thể làm nhiều token ký bằng key cũ không hợp lệ | Blast radius lớn; không phải công cụ logout thông thường |
| **Sender-constrained token** | Giảm replay token bị đánh cắp ở nơi khác | Không thay thu hồi khi process/key bị chiếm |

### 8.4. Lựa chọn theo yêu cầu bảo mật

API đọc dữ liệu công khai có thể chấp nhận TTL ngắn với mức rủi ro phù hợp. API quản trị tài chính hoặc cấp quyền IAM có thể cần **kiểm active session/grant/security block gần thời gian thực** hoặc token có khả năng introspect.

Thiết kế phải công bố **mức độ bảo đảm**: “thu hồi trong vài giây khi control plane hoạt động”, “tối đa bằng token TTL” hoặc “không bảo đảm đóng phiên đã tồn tại”. Không hứa điều nền tảng chưa kiểm chứng.

## 9. Opaque access token và OAuth introspection

**Opaque token** thường là chuỗi không mang claims tự đọc được; resource server cần hỏi issuer hoặc service nội bộ đáng tin xem token còn hợp lệ hay không.

**RFC 7662** mô tả giao diện **OAuth 2.0 Token Introspection** để tài nguyên được phép kiểm trạng thái/metadata của token.

### 9.1. Mô hình

~~~text
API receives opaque access token
  -> authenticated call to introspection endpoint
  -> token active? audience? scope? subject? client?
  -> local resource/tenant authorization
  -> PERMIT or DENY
~~~

### 9.2. Ví dụ phản hồi minh họa

~~~json
{
  "active": true,
  "scope": "invoice.read",
  "client_id": "finance-portal",
  "sub": "person-1042",
  "aud": "finance-api",
  "exp": 1795432500
}
~~~

Các trường thực tế phụ thuộc authorization server và profile. **`active=true` vẫn chưa đủ để PERMIT** nếu token sai audience, không có scope, subject bị security block hoặc object thuộc tenant khác.

### 9.3. Cache introspection có thể làm chậm thu hồi

Nếu API cache `active=true` trong 5 phút, issuer revoke token ngay nhưng resource vẫn có thể tin cache cũ trong cửa sổ đó. Cần giới hạn TTL theo rủi ro, phát invalidation events hoặc kiểm trạng thái tức thời cho hành động đặc biệt nhạy cảm.

Khi introspection endpoint không thể truy cập, **không mặc định `active=true`**. Xử lý `INDETERMINATE` theo policy/fail-safe và có runbook nếu availability cực kỳ quan trọng.

## 10. OAuth 2.0 token revocation – RFC 7009

**RFC 7009** định nghĩa cơ chế client gửi token đến **revocation endpoint** của authorization server để yêu cầu làm mất hiệu lực token. Cơ chế thường được dùng với **refresh token** và có thể áp với access token tùy nhà cung cấp.

### 10.1. Ví dụ request mang tính mô hình

~~~http
POST /oauth2/revoke HTTP/1.1
Host: id.example.invalid
Content-Type: application/x-www-form-urlencoded

token=<token-value>&token_type_hint=refresh_token
~~~

Trong hệ thực tế:

- Request phải đi qua **HTTPS**.
- Client authentication/authorization với endpoint phải tuân theo cấu hình issuer.
- Không log token thô, kể cả ví dụ đã thay bằng placeholder.
- `token_type_hint` là **gợi ý**, không phải chứng cứ loại token; server tự quyết.
- Response không nên được hiểu là bằng chứng mọi target đã ngừng PERMIT.

### 10.2. Ngữ nghĩa trả lời cần hiểu đúng

Một endpoint revocation có thể trả **HTTP 200** cả khi token đã vô hiệu hoặc không tồn tại, nhằm tránh lộ thông tin token. Vì vậy client không nên dựa vào “200 nghĩa token vừa được tìm thấy và đã xóa”.

Việc revoke refresh token có thể kéo theo các access token cùng grant **nếu issuer hỗ trợ và thực hiện**; không mặc định mọi nhà cung cấp đều revoke cascade như nhau. Ngược lại revoke một access token không bắt buộc tự làm mất hiệu lực mọi refresh token liên quan.

**Muốn thu hồi thực tế phải kiểm capability và hiệu lực ở resource server.**

### 10.3. Revocation không phải user logout toàn cục

Một ứng dụng OAuth revoke token riêng của client không nhất thiết xóa:

- Phiên đăng nhập SSO ở IdP.
- Cookie của một relying party khác.
- Phiên PAM/RDP/SSH.
- Credential service account độc lập.
- Access token khác được phát cho client/thiết bị khác.

Cần định nghĩa scope của lệnh rõ ràng: **token, grant, token family, user session hay all sessions**.

## 11. Refresh-token rotation, family và replay

**Refresh token** cho phép ứng dụng xin access token mới. Một số issuer dùng **refresh-token rotation**: mỗi lần đổi token, refresh token cũ bị thay bằng token mới; việc tái sử dụng token cũ có thể là tín hiệu bị đánh cắp.

### 11.1. Ví dụ token family

~~~text
Client login:
  refresh token R1 -> issue access token A1

Normal refresh:
  R1 exchanged -> R1 invalidated -> R2 issued + A2

Later:
  R1 unexpectedly used again
  -> possible replay or client concurrency defect
  -> policy may revoke token family/grant and require reauth
~~~

**Phản ứng khi phát hiện replay** tùy issuer và cấu hình: có nơi revoke family, có nơi thông báo rủi ro, có nơi cần cơ chế bổ sung. Phải kiểm hành vi thực tế.

### 11.2. Hai luồng refresh đồng thời

Một browser app có thể gửi hai refresh requests dùng cùng R1 do concurrency, khiến một yêu cầu bị coi là replay. Cần đồng bộ refresh phía client/BFF, sử dụng SDK phù hợp và xử lý lỗi reauthentication; không vô hiệu bảo vệ replay chỉ để tránh lỗi ngẫu nhiên.

### 11.3. Thu hồi một thiết bị hay toàn bộ gia đình token?

Nếu một điện thoại bị mất, nên revoke **refresh family/grant của thiết bị đó** nếu issuer phân biệt được. Với dấu hiệu credential compromise toàn account, có thể cần thu hồi tất cả grants/sessions và bắt buộc reauthentication.

Không nên đoán rằng `revoke(R2)` tự phủ cả `R1` hoặc mọi access token; phải xác minh hệ thống quản lý family/rotation và session mapping.

### 11.4. Session trên mobile/desktop khác browser

Ứng dụng native có thể dùng refresh token trong OS-protected storage, không có browser cookie tương ứng. Xóa phiên web **không tự revoke token native**. Hệ thống cần inventory client/device/grant và endpoint phù hợp.

## 12. OIDC logout: RP-initiated, front-channel, back-channel

**OpenID Connect (OIDC)** có những cơ chế logout để các **Relying Parties (RP)** và **OpenID Provider (OP)** phối hợp chấm dứt session. Mỗi phương thức có điều kiện triển khai và giới hạn riêng.

### 12.1. RP-initiated logout

Một RP có thể yêu cầu OP kết thúc phiên đăng nhập OIDC qua **end-session endpoint** nếu nhà cung cấp hỗ trợ. Điều này không bảo đảm mọi resource server đã thu hồi access token hoặc mọi ứng dụng đã xóa local session.

### 12.2. Front-channel logout

Logout có thể được truyền qua **trình duyệt** tới các RP; cơ chế này nhạy với cookie policies, chặn third-party cookies, tab không còn mở, network outage và hành vi browser.

### 12.3. Back-channel logout

OP có thể gửi **logout token** qua kênh server-to-server tới RP đã đăng ký để thông báo session/subject cần kết thúc. RP phải **xác minh issuer, audience, chữ ký, loại event, thời hạn, `sid`/`sub` theo profile** và làm mất hiệu lực **local RP session** có mapping tương ứng.

Không nhầm **OIDC back-channel logout token** với **OAuth access token**, và không dùng logout token như bằng chứng được phép gọi API nghiệp vụ.

### 12.4. Sơ đồ minh họa

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant RP1 as App A / RP
    participant OP as IdP / OP
    participant RP2 as App B / RP
    participant API as Resource API

    U->>RP1: Logout / security event
    RP1->>RP1: Invalidate local session
    RP1->>OP: End-session request if supported
    OP->>OP: End OP session
    OP->>RP2: Back-channel logout notification if configured
    RP2->>RP2: Verify token; invalidate matching RP session
    Note over OP,API: API token revocation is a separate concern
    RP2->>API: Old access token may still be presented
    API-->>RP2: DENY only if token/policy no longer valid
~~~

### 12.5. Tại sao OIDC logout không đủ một mình?

- RP khác có thể không hỗ trợ logout profile.
- Thông báo có thể thất bại hoặc xử lý trễ.
- Session ở ứng dụng có thể không map được `sid`.
- Resource API có thể tự xác minh JWT offline.
- Native app có thể có refresh family riêng.
- Session PAM/VPN ngoài OIDC không được kết nối.

Nên kết hợp logout với **grant/token revocation, policy enforcement và reconciliation** khi cần chặn toàn bộ truy cập.

## 13. SAML SSO và Single Logout (SLO)

Trong **SAML**, người dùng đăng nhập qua IdP và Service Provider (SP) có thể tạo local session. **SAML Single Logout (SLO)** giúp phối hợp logout khi các bên hỗ trợ đúng cấu hình.

### 13.1. Những giới hạn cần nhớ

- Một SP có thể không hỗ trợ SLO hoặc chỉ hỗ trợ một binding.
- Việc thông báo có thể thất bại khi một SP offline.
- Session ở SP có thể tiếp tục nếu SP không thực hiện logout.
- Một số ứng dụng tạo API tokens, local accounts hoặc cookies độc lập.
- SAML assertion từng phát **không phải một cơ chế điều khiển mọi session sau đăng nhập**.

### 13.2. SessionIndex và liên kết danh tính

SAML có thể dùng thông tin phiên như **SessionIndex** trong ngữ cảnh SLO, nhưng cần ánh xạ đúng với SP local sessions và đối tượng được xác minh. Không dùng email làm khóa duy nhất nếu identity có thể đổi hoặc trùng giữa tenant.

### 13.3. Cần thử từng SaaS

Không đánh dấu `SAML_SLO_SUPPORTED` chỉ vì IdP có nút logout. Cần kiểm ứng dụng đích thực sự đóng local session và chặn request tiếp theo trong từng tình huống: SP online, SP offline, stale cookies, nhiều browser, nhiều sessions.

## 14. Session revocation trong ứng dụng SaaS và SCIM

**SCIM (System for Cross-domain Identity Management)** có thể dùng để provision, cập nhật, disable user/group tại SaaS theo khả năng provider.

### 14.1. Disable account không tự chấm dứt session

Một SaaS có thể hỗ trợ `active=false` cho user account, nhưng:

- Phiên browser đã phát có thể vẫn hoạt động đến khi SaaS kiểm lại trạng thái.
- Local access/refresh tokens có thể có thời hạn riêng.
- Mobile app session có thể được quản lý khác web.
- API keys do user tạo có thể còn.
- Bên SaaS có thể có độ trễ sync hoặc queue.

Vì vậy cần bảng capability **SCIM disable + session termination API + revoke API keys + observed login tests**, không chỉ một thao tác provisioning.

### 14.2. Đọc lại trạng thái

Sau khi gọi SCIM/API:

1. Kiểm phản hồi và correlation ID.
2. Đọc lại account status/group/roles ở target.
3. Kiểm session termination API nếu có.
4. Kiểm token/API key và đường login đã cấp.
5. Thử hành động đã từng PERMIT ở target theo phương pháp kiểm soát an toàn.
6. Đánh dấu **VERIFIED_DENIED** hoặc **PARTIAL/UNKNOWN** kèm owner.

### 14.3. SaaS không có API terminate session

Khi target không hỗ trợ thu hồi phiên theo yêu cầu, phải có **risk acceptance, TTL/timeout cấu hình, conditional access/inbound controls, escalation với vendor, kế hoạch bù kiểm soát**. Không tuyên bố thu hồi tức thì chỉ vì admin UI đã disable account.

## 15. Session revocation và RBAC/ABAC/PBAC

Thu hồi một **entitlement** và thu hồi một **session** là hai việc liên quan nhưng không đồng nhất.

### 15.1. RBAC role claim stale

Người dùng chuyển từ Sales sang Finance. IdP group đã gỡ `SalesAdmin`, nhưng JWT phát trước đó vẫn chứa group cũ. Nếu API chỉ kiểm `roles` từ JWT đến `exp`, quyền Sales có thể tồn dư.

Giải pháp có thể gồm:

- Rút sessions/tokens liên quan.
- Kiểm entitlement hiện hành ở PEP.
- Dùng short-lived token hoặc phiên bản role/entitlement.
- Gắn deny rule tới old resource/role ngay khi Mover effective.
- Chờ propagation nhưng đánh dấu rủi ro tồn dư rõ.

### 15.2. ABAC: kiểm bối cảnh hiện hành

~~~text
PERMIT invoice.approve WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.relationshipId == permission.relationshipId
    AND subject.tenantId == invoice.tenantId
    AND session.isActive
    AND NOT session.securityRevoked
    AND subject.hasCurrentEntitlement("invoice.approve")
    AND session.assuranceSatisfiesPolicy
    AND NOT sod.conflicts(subject, invoice)
ELSE DENY
~~~

Đây là mã giả. Các thuộc tính phải đến từ **nguồn đã xác minh**, không từ headers/JSON do caller tự khai.

### 15.3. PBAC và thay đổi policy

Policy có thể chuyển từ yêu cầu MFA thông thường sang step-up bắt buộc. Một session cũ có assurance thấp có thể cần **step-up/reauth**, không nhất thiết phải revoke toàn bộ session; nhưng nếu có dấu hiệu compromise có thể cần chấm dứt.

### 15.4. Session termination không xóa entitlement

Nếu user logout nhưng role `Admin` vẫn được cấp, lần đăng nhập sau vẫn có role đó. Để **chấm dứt quyền vĩnh viễn**, phải gỡ entitlement/role hoặc thay policy ngoài việc thu hồi session.

## 16. Thu hồi phiên trong Joiner lifecycle

**Joiner** là sự kiện một người bắt đầu quan hệ làm việc. Account và preboarding session có thể tồn tại trước `effectiveAt`, nhưng quyền nhạy cảm không nên có hiệu lực trước thời điểm được phép.

### 16.1. Joiner hợp lệ

1. HRIS xác nhận identity/relationship/effectiveAt.
2. Identity proofing và IdP tạo credential/session theo scope onboarding.
3. IGA xác định quyền preboarding khác quyền production.
4. Khi bắt đầu làm việc, hệ cấp quyền production theo approval/eligibility.
5. PEP kiểm session/entitlement hiện hành và policy thời điểm sử dụng.

### 16.2. Joiner bị hủy

Nếu ứng viên không nhận việc:

- Hủy pending grants và disable account tương ứng.
- Thu hồi preboarding IdP/application sessions.
- Revoke refresh grants/token issuance theo capability.
- Chặn production JIT/provisioning task cũ.
- Gỡ tài khoản SaaS đã tạo và kiểm local sessions.
- Reconcile mọi đường truy cập, giữ audit theo retention.

### 16.3. Rehire không tự khôi phục session cũ

Khi một người được tuyển lại, họ có thể có identityId liên kết với trước đây nhưng **relationship mới**. Không được tái sử dụng refresh grants, device sessions và quyền từng được cấp cho quan hệ cũ mà chưa kiểm policy hiện hành.

## 17. Thu hồi phiên trong Mover lifecycle

**Mover** thay đổi department, manager, job, project, pháp nhân hoặc trách nhiệm. Rủi ro chính là **privilege creep và stale sessions**.

### 17.1. Ví dụ

~~~text
09:00  User đang có JWT nhóm SalesAdmin, exp = 10:00
09:15  HRIS ghi Mover sang Finance
09:16  IGA gỡ SalesAdmin, cấp FinanceReader theo approval
09:17  IdP group claim được cập nhật
09:18  Sales API tiếp tục tin JWT SalesAdmin đã phát
~~~

Hệ thống cần chặn access cũ tại PEP hoặc revoke/expire session/token theo thời hạn bảo đảm đã định.

### 17.2. Thu hồi theo quyền thay vì logout mọi nơi

Một số use case chỉ cần **revoke sessions có quyền Sales đặc thù** và khiến người dùng lấy token mới cho Finance. Với quyền đặc biệt nguy hiểm, nên buộc reauthentication hoặc chặn ngay old entitlement.

### 17.3. Manager đổi không đồng nghĩa mọi session phải đóng

Thay manager có thể ảnh hưởng approval/SoD chứ không trực tiếp ảnh hưởng login. Cần đánh giá **căn cứ quyền**, không suy rằng mọi Mover phải logout toàn doanh nghiệp.

### 17.4. Mover giữa tenant/pháp nhân

Nếu một identity chuyển từ tenant-a sang tenant-b, token hoặc session được phát trong tenant-a không được dùng để thao tác ở tenant-b. Cần revoke old grants và kiểm isolation ở resource. Đừng tái dùng `sub` hoặc email làm bằng chứng liên thông hai tenant khi chưa có identity linking đáng tin.

## 18. Thu hồi phiên trong Leaver lifecycle

**Leaver** là tình huống điển hình cần **chặn nhiều đường truy cập cùng lúc**, không chỉ từ chối login mới.

~~~mermaid
flowchart TD
    HR["HRIS: Leaver event + effectiveAt"] --> IGA["IGA: compute affected identity and grants"]
    IGA --> IDP["Disable IdP and revoke OP sessions / grants"]
    IGA --> RP["Revoke RP/local application sessions"]
    IGA --> SCIM["SCIM/API: disable and remove target roles"]
    IGA --> PAM["Terminate PAM/JIT/SSH/VPN sessions"]
    IGA --> DEV["Revoke device/native refresh families"]
    IDP --> REC["Reconciliation"]
    RP --> REC
    SCIM --> REC
    PAM --> REC
    DEV --> REC
    REC --> Q{"All required paths effectively denied?"}
    Q -->|"No / unknown"| EX["Exception, owner, containment and retry"]
    Q -->|"Evidence PASS"| DONE["Leaver session closure verified"]
    EX --> REC
~~~

### 18.1. Trình tự ưu tiên

Ở quyền nhạy cảm, cần ưu tiên **đường kiểm soát có thể chặn thực thi ngay**: security block tại PEP/gateway, revoke active sessions/grants, chấm dứt privileged connections. Các bước SCIM/account cleanup và verification diễn ra có kiểm soát; không nhất thiết chờ lần lượt nếu có thể chạy song song an toàn.

### 18.2. Leaver event đến trễ

Nếu HRIS báo Leaver lúc 18:10 nhưng `effectiveAt=18:00`, hệ thống phải kiểm các sessions/grants và actions trong khoảng 18:00–18:10, ghi incident/exception nếu cần. Đồng hồ của các hệ phải có timezone và semantics rõ.

### 18.3. Thu hồi không dừng ở IDP

- SaaS local session cần termination theo capability.
- VPN/RDP/SSH có thể còn kết nối đang hoạt động.
- Refresh token native app có thể còn hạn.
- Cloud console/API keys, account local và delegated tokens có thể độc lập.
- JIT elevation có thể còn thời hạn dù tài khoản nhân sự Leaver.
- Robot/service identities từng dùng credential người cũ cần review riêng.

### 18.4. Đa quan hệ

Nếu một người nghỉ hợp đồng với tổ chức A nhưng vẫn là đối tác hợp lệ của tổ chức B, phải xác định **entitlement/session nào dựa trên relationship A**, chặn theo policy và không vô ý xóa quyền chính đáng của B. Tuy nhiên khi có security compromise toàn identity, phạm vi có thể phải mở rộng.

## 19. PAM/JIT, SSH, RDP, VPN và phiên đặc quyền

Phiên đặc quyền có thể cho phép sửa production, đọc secret hoặc thay chính sách IAM. Thu hồi ở tầng IdP **không nhất thiết cắt phiên đặc quyền đã hình thành**.

### 19.1. Các loại phiên cần quản lý

| Loại | Nơi kiểm soát | Rủi ro khi chỉ thu hồi IdP |
| --- | --- | --- |
| **PAM broker session** | Gateway/proxy/session manager | Phiên đã kết nối vẫn còn |
| **JIT/PIM activation** | Hệ cấp quyền tạm | Elevation vẫn ACTIVE theo TTL riêng |
| **SSH session** | Server/process và key/account | Shell đang mở vẫn chạy |
| **RDP/remote desktop** | Remote host/session service | Kết nối chưa bị logoff |
| **VPN session** | VPN gateway/network access controller | Tunnel vẫn cho truy cập mạng |
| **Database session** | DB session manager | Transaction hoặc connection pool còn |
| **Cloud console session** | Cloud IAM/session service | Console/token riêng có thể còn |
| **Kubernetes admin context** | API token/certificate/RBAC | Client còn credential dù người dùng logout |
| **Long-running job** | Scheduler/worker/host | Task đã khởi chạy có thể tiếp tục |

### 19.2. Tắt JIT không đồng nghĩa shell dừng

Ví dụ một DBA kích hoạt quyền production 30 phút và mở SSH/DB session. Sau 30 phút, JIT grant hết hạn nhưng **process đã tạo vẫn có thể tiếp tục** tùy nền tảng. Cần quyết định:

- **Terminate** active connections khi grant hết hạn.
- **Reauthorize** các hành động mới tại PEP.
- **Revoke credential** và key/token cấp riêng cho phiên.
- Kiểm **background jobs, scheduled tasks, forwarded ports/tunnels** do phiên tạo.
- Ghi audit và xác minh không còn quyền hiệu lực.

### 19.3. Session recording khác session termination

PAM recording cung cấp bằng chứng, nhưng **không tự cắt kết nối**. Phải có cơ chế điều khiển phiên tại broker/target hoặc runbook khẩn cấp.

### 19.4. Khó khăn của lệnh đang chạy

Nếu một lệnh sửa dữ liệu đã commit trước thời điểm thu hồi, session revocation **không hoàn tác** thay đổi đó. Khi cần bảo đảm nghiệp vụ, phải thêm **authorization tại bước commit, transaction control, compensation và audit**, thay vì hứa thu hồi có thể đảo ngược quá khứ.

## 20. WebSocket, gRPC streams và long-lived connections

Nhiều ứng dụng chỉ kiểm access token **lúc bắt đầu kết nối**. Nếu quyền bị thu hồi sau đó, kết nối đang mở có thể tiếp tục truyền dữ liệu.

### 20.1. Ví dụ WebSocket

~~~text
10:00  User mở WebSocket bằng token hợp lệ.
10:05  Security thu hồi session.
10:06  Server vẫn giữ WebSocket, không recheck quyền.
10:07  Kênh tiếp tục gửi dữ liệu nhạy cảm.
~~~

### 20.2. Kiểm soát khả thi

- Gắn connection với **identityId, sessionId/grant, tenant, policy revision**.
- Khi có revocation event, chủ động **đóng connection** tương ứng.
- Với luồng nhạy cảm, kiểm lại authorization ở **message/action boundary**.
- Giới hạn thời hạn tối đa và yêu cầu reauthentication/reconnect phù hợp.
- Recheck quyền khi subscription/resource scope thay đổi.
- Kiểm các connections trải qua **gateway, load balancer, region, replica**.
- Không chỉ đóng UI nhưng để data stream tiếp tục phía sau.

### 20.3. gRPC streaming và message consumers

gRPC có thể có long-lived stream. Một connection đã xác thực peer bằng mTLS từ đầu không tự hết quyền khi trust/role thay đổi. Nên dùng cơ chế **stream cancellation, reauthorization checkpoint và credential rotation**, đặc biệt với privileged streams.

Đối với queue consumer, **message handler** có thể chạy sau khi quyền user/delegation đã bị thu hồi. Cần phân biệt job nhân danh người dùng và job chính thức của hệ thống, rồi kiểm current state tại thời điểm xử lý.

## 21. Service accounts, workload identities và robot sessions

Không phải mọi session thuộc một nhân viên. **Service-to-service, service account, robot/RPA và CI/CD workload** có thể có OAuth grants, access tokens, certificates, cloud sessions hoặc kết nối database.

### 21.1. Vòng đời non-human principal

Một workload có thể:

1. Đăng ký principal với owner/purpose.
2. Nhận credential qua cloud identity, mTLS, SPIFFE hoặc OAuth.
3. Gọi API/target nhiều lần.
4. Thay owner, scope, environment hoặc credential.
5. Bị security block hoặc project retire.
6. Revoke trust/client credential/role/token và kiểm phiên kết nối còn tồn dư.

**Không chỉ xóa container hoặc dừng robot job rồi xem identity đã bị thu hồi.** Client registration, certificates, DB accounts, access tokens và cloud IAM grants có thể còn.

### 21.2. Owner Leaver

Một người quản lý service account Leaver không có nghĩa dịch vụ production phải dừng ngay. Cần:

- Gỡ quyền người cũ trên IdP, PAM, vault, CI/CD và cloud IAM.
- Chuyển ownership và alert contacts.
- Rà secret người cũ từng biết hoặc mint.
- Rotate/rekey theo rủi ro, không làm đứt dịch vụ không có kế hoạch.
- Kiểm active OAuth grants, client certificates và long-running sessions.
- Đối soát workload principal với resource owner approval hiện hành.

### 21.3. Attended robot và delegated user session

Một attended robot dùng user context có thể mất quyền khi user Leaver hoặc session bị revoke. Một unattended robot dùng **identity độc lập** vẫn có thể tiếp tục nếu business purpose/owner hợp lệ; nhưng nó không được giữ **delegated refresh token của người đã nghỉ** để thực hiện hành động thay user.

### 21.4. JWT client credentials cũng có cửa sổ tồn dư

Thu hồi client secret thường chặn việc phát **token mới**, nhưng access token đã phát cho service có thể vẫn được API chấp nhận đến khi `exp` hoặc có deny mechanism. Với quyền cao, cần **current-state enforcement** và bounded token lifetime.

## 22. Thu hồi session theo thiết bị và theo client

Người dùng có thể đăng nhập trên laptop, điện thoại và nhiều browser. Một nút “Sign out all devices” phải có phạm vi được định nghĩa rõ.

### 22.1. Các mức thu hồi

| Scope | Hành động mong muốn | Cảnh báo |
| --- | --- | --- |
| **Current session** | Kết thúc browser/app session hiện tại | Không tự thu hồi thiết bị khác |
| **Device session** | Revoke grants/session gắn một thiết bị | Thiết bị chưa được liên kết đầy đủ |
| **Client/application** | Revoke sessions/grants của một client | RP/SaaS local session có thể độc lập |
| **User all sessions** | Invalidate tất cả sessions/grants quản lý được | Có hệ ngoài không hỗ trợ |
| **Tenant-scoped** | Chặn sessions phát sinh từ tenant cụ thể | Không làm mất các relationship hợp lệ khác |
| **Privilege-scoped** | Chặn elevation/role nhạy cảm | Các session read-only có thể tiếp tục nếu được phép |
| **Security incident** | Revoke rộng, buộc reauth và credential review | Cần account recovery path an toàn |

### 22.2. Liên kết thiết bị phải đáng tin

Không dùng duy nhất `User-Agent`, IP hoặc tên thiết bị do client tự khai để xác định grant. Khi nền tảng hỗ trợ, dùng **device ID/registration, client ID, session ID và proof** có liên kết đáng tin; vẫn ghi rõ giới hạn attribution.

### 22.3. “Đăng xuất tất cả” cần hiển thị trung thực

Nếu một số ứng dụng SaaS không có API kết thúc phiên, sản phẩm không nên thông báo “đã đăng xuất khỏi mọi ứng dụng trên mọi thiết bị” chỉ vì IdP thu hồi grants. Nên thông báo **đã gửi yêu cầu, phần nào hoàn tất, phần nào đang xử lý/không hỗ trợ**.

## 23. Security events, CAEP/RISC và distributed revocation

Trong hệ phân tán, một thay đổi lifecycle cần lan tới nhiều **IdP, RP, resource server, gateway và SaaS**.

### 23.1. Event-driven approach

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HRIS / Security
    participant I as IGA / Revocation coordinator
    participant EV as Trusted event channel
    participant IDP as IdP / OAuth server
    participant API as API gateway / PEP
    participant SaaS as SaaS connector
    participant AUD as Audit / Reconciliation

    H->>I: Leaver / security block + identityRef
    I->>I: Validate authority, scope, effectiveAt
    I->>EV: Revocation command/event (versioned)
    EV->>IDP: Revoke session/grants
    EV->>API: Invalidate active-session/epoch caches
    EV->>SaaS: Disable/terminate target access
    IDP-->>AUD: Applied outcome
    API-->>AUD: Enforcement outcome
    SaaS-->>AUD: Applied / unknown
    AUD->>I: Desired vs observed/effective status
    I->>EV: Controlled retry / escalation if incomplete
~~~

### 23.2. Sự kiện phải được xác thực

Một message dạng `revokeAll(person-1042)` có thể gây tác động lớn. Receiver phải xác minh:

- **Event source/issuer** và authorization của hệ phát.
- **Event signature/authenticity** hoặc kênh bảo vệ phù hợp.
- Subject mapping, tenant, relationship và intended scope.
- Event ID, version, timestamp/effectiveAt.
- Replay/duplicate suppression.
- Status mới nhất trước khi thay đổi.
- Audit/correlation để truy hồi.

Không nhận event unsigned từ một queue công khai rồi revoke hoặc grant theo nội dung.

### 23.3. CAEP và RISC

Các họ **Continuous Access Evaluation Protocol (CAEP)** và **Risk and Incident Sharing and Coordination (RISC)** trong hệ sinh thái **Shared Signals Framework** cung cấp cách trao đổi tín hiệu về trạng thái truy cập/rủi ro giữa các hệ nếu triển khai hỗ trợ.

**Chúng không tự biến mọi token thành revocable tức thì**. Receiver cần hiểu event, map identity/session, áp policy và kiểm hiệu lực. Phải xem vendor hỗ trợ tín hiệu nào và SLA ra sao; không giả định tất cả SaaS đều triển khai CAEP/RISC.

### 23.4. Idempotency và ordering

Một event cũ có thể đến sau event mới:

~~~text
v11: User ACTIVE / session S1 created
v12: User BLOCKED / revoke S1
v13: User recovered / new session S2 created

Late delivery of v11 or v12 must not re-enable S1.
New session S2 must be checked against current policy.
~~~

Nên dùng **monotonic revocation epoch/state version** và kiểm transaction/state; không chỉ so timestamp theo đồng hồ không đồng bộ.

## 24. Thiết kế Revocation API có bằng chứng theo target

Một API điều phối thu hồi nên trả **tracking reference** và trạng thái từng hệ, không giả vờ gọi một endpoint là đã thu hồi mọi nơi.

### 24.1. Request contract minh họa

~~~json
{
  "revocationRequestId": "rev-8842",
  "subjectIdentityId": "person-1042",
  "relationshipId": "employment-A-1042",
  "scope": {
    "mode": "ALL_SESSIONS_FOR_RELATIONSHIP",
    "tenantId": "tenant-a"
  },
  "reason": "LEAVER",
  "effectiveAt": "2026-11-23T18:00:00+07:00",
  "sourceEventRef": "hris-leaver-1881",
  "expectedIdentityVersion": 42
}
~~~

JSON chỉ là mẫu thiết kế. Không tin dữ liệu actor/scope do một caller không có thẩm quyền tự cung cấp. Các trường phải được kiểm tại server.

### 24.2. Response trạng thái minh họa

~~~json
{
  "revocationRequestId": "rev-8842",
  "accepted": true,
  "targetOutcomes": [
    {
      "system": "corporate-idp",
      "status": "APPLIED",
      "verifiedAt": "2026-11-23T18:00:05+07:00"
    },
    {
      "system": "finance-saas",
      "status": "PENDING",
      "verifiedAt": null
    },
    {
      "system": "vpn-gateway",
      "status": "UNKNOWN",
      "verifiedAt": null
    }
  ],
  "overallStatus": "PARTIAL"
}
~~~

`accepted=true` chỉ xác nhận hệ nhận yêu cầu xử lý; **không đồng nghĩa toàn bộ target đã deny**. Tên trạng thái là mô hình minh họa, không phải API chuẩn của một sản phẩm.

### 24.3. State per target

| Trạng thái | Ý nghĩa |
| --- | --- |
| **PENDING** | Chưa xử lý hoặc đang chờ |
| **SENT** | Gửi yêu cầu, chưa có kết quả xác minh |
| **APPLIED** | Target báo đã thay đổi local session/grant |
| **VERIFIED_DENIED** | Có bằng chứng access bị chặn đúng scope |
| **UNKNOWN** | Không đọc/kiểm được trạng thái |
| **PARTIAL** | Chỉ một số phiên/đích đã xử lý |
| **FAILED** | Xử lý thất bại cần remediation |
| **NOT_SUPPORTED** | Target không hỗ trợ hành động cụ thể |
| **EXCEPTION_ACCEPTED** | Rủi ro được chấp thuận bởi thẩm quyền, có hạn xử lý |

Không tự đổi **NOT_SUPPORTED** hoặc **UNKNOWN** thành **VERIFIED_DENIED** để hoàn thành SLA.

## 25. Java/Spring Security: hủy phiên server-side

Trong ứng dụng Java dùng `HttpSession`, logout thường cần **invalidate local session** và xóa security context/cookie phù hợp.

### 25.1. Ví dụ minh họa cho phiên hiện tại

~~~java
// Mẫu minh họa cho ứng dụng servlet stateful.
// Chưa bao gồm đầy đủ CSRF, logout handler, OIDC hoặc distributed storage.
@PostMapping("/session/logout")
public ResponseEntity<Void> logout(
        HttpServletRequest request,
        HttpServletResponse response) {

    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }

    SecurityContextHolder.clearContext();

    Cookie expired = new Cookie("JSESSIONID", "");
    expired.setMaxAge(0);
    expired.setHttpOnly(true);
    expired.setSecure(true);
    expired.setPath("/");
    response.addCookie(expired);

    return ResponseEntity.noContent().build();
}
~~~

**Lưu ý kỹ thuật:**

- Spring Security có logout handlers/cấu hình riêng; trong hệ thực tế nên dùng **mechanism được framework hỗ trợ** thay vì tự xây lại.
- Cookie xóa đúng nếu **name/path/domain** khớp cookie ban đầu; mẫu trên cố ý đơn giản.
- Phải bảo vệ logout/mutation endpoint trước CSRF theo mô hình browser, và cấu hình `SameSite`, `Secure`, `HttpOnly` phù hợp.
- Đoạn code **chỉ thu hồi session tại ứng dụng hiện tại**, không hủy JWT của API khác, OP session, mobile sessions hay cloud token.
- Nếu ứng dụng stateless với JWT, `HttpSession.invalidate()` không phải cơ chế revoke access token.

### 25.2. Thu hồi tất cả sessions khi dùng Spring Session

Với ứng dụng phân tán có **Spring Session** và store chung, có thể dùng repository hỗ trợ tra session theo principal để xóa các sessions được tìm thấy.

~~~java
// PSEUDOCODE: cấu trúc hướng dẫn; type tùy Spring Session version/store.
void revokeSessionsForPrincipal(
        String principalName,
        AuthorizedRevocationRequest request) {

    requireRevocationAuthority(request, principalName);

    Map<String, Session> sessions =
        indexedSessionRepository.findByPrincipalName(principalName);

    for (String sessionId : sessions.keySet()) {
        indexedSessionRepository.deleteById(sessionId);
        audit.recordLocalSessionInvalidation(
            request.id(), principalName, sessionId
        );
    }
}
~~~

Những điều cần kiểm:

- Repository thực sự có **principal index** và quản lý sessions đang hoạt động.
- Dùng principal identity đã được liên kết bền vững; tránh username/email tái sử dụng.
- Có thể xuất hiện session mới giữa lúc list và delete; phải có **session version/deny guard** để không bỏ sót khi security block.
- Không gửi raw sessionId vào audit nếu nó là credential; dùng tham chiếu an toàn.
- Những instance khác phải quan sát invalidation đúng thời hạn.
- Thử cả request đã bắt đầu trước lệnh revoke và request sau revoke.

### 25.3. Logout endpoint khác admin revoke endpoint

User tự logout cần quyền trên **session của chính mình**. Security admin có thể revoke phiên người khác theo policy. Không mở một API `DELETE /sessions/{id}` cho bất kỳ user đã đăng nhập nào mà không kiểm **subject, tenant, owner và role**.

## 26. Java/Spring Security: kiểm JWT sau khi bị thu hồi

Spring Security Resource Server có thể xác minh JWT signature/issuer/expiry; để hỗ trợ thu hồi sớm cần thêm cơ chế **revocation-aware** tại đúng trust boundary.

### 26.1. Validator minh họa

~~~java
// PSEUDOCODE tích hợp với JwtDecoder; không phải app độc lập.
// Cần cấu hình chữ ký/issuer/audience và các checks mặc định riêng.
final class RevocationAwareJwtValidator
        implements OAuth2TokenValidator<Jwt> {

    private final SessionRevocationStore revocationStore;

    RevocationAwareJwtValidator(
            SessionRevocationStore revocationStore) {
        this.revocationStore = revocationStore;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tokenId = jwt.getId();

        if (revocationStore.isTokenRevoked(
                issuer, subject, tokenId)) {
            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Access token revoked",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        }

        return OAuth2TokenValidatorResult.success();
    }
}
~~~

Đoạn mã chỉ minh họa **một điểm hook**, cần thêm issuer/subject null handling, session epoch, `aud`, scope, tenant và fail-safe khi store không khả dụng. Cần kết hợp validator với **các kiểm tra JWT tiêu chuẩn**; không thay signature/expiry validation bằng lệnh `isTokenRevoked()`.

### 26.2. Quy tắc thiết kế denylist

- Khóa lookup nên gồm **issuer, token ID hoặc session/grant ID**, và scope thích hợp; `jti` có thể không tồn tại.
- Chỉ lưu **thông tin cần thiết** đến khi token chắc chắn hết hiệu lực theo expiration/leeway.
- Nếu revoke cả user, dùng **revocation epoch/sessionVersion** để tránh liệt kê hàng triệu token.
- Nếu dùng cache, cần cơ chế invalidation và bounded staleness.
- Khi store unavailable, xử lý theo risk; không mặc định trạng thái **NOT_REVOKED**.
- Với token sender-constrained, vẫn phải kiểm client proof/certificate binding theo profile.

### 26.3. Đừng đọc token rồi tự trả 200

Một API chỉ `JwtDecoder.decode()` mà bỏ qua authorization cho `resource/action/tenant` vẫn có thể cấp quyền sai dù revocation hoạt động tốt. Phải kiểm **AuthN + active session/token + AuthZ**.

## 27. Pseudocode coordinator: thu hồi nhiều hệ thống

~~~text
revokeAccess(authoritativeEvent):
    validate source, signature, tenant, relationship, version
    identity = identityRegistry.resolve(authoritativeEvent.subject)

    require caller has authority to initiate this scope

    action = revocationStore.createIdempotentCommand(
        requestId = authoritativeEvent.id,
        identity = identity,
        scope = authoritativeEvent.scope,
        reason = authoritativeEvent.reason,
        effectiveAt = authoritativeEvent.effectiveAt
    )

    stateGuard.raiseRevocationEpoch(identity, action.scope)
    denyPolicy.applyImmediateBlockWhereSupported(identity, action.scope)

    for target in targetRegistry.sessionsFor(identity, action.scope):
        enqueueOutbox(
            action.id, target.id,
            operation = target.supportedRevocationMethod
        )

    for targetResult in asyncResults:
        record applied status and observed state
        if target still permits:
            open residual-access exception with owner

    close only when required targets VERIFIED_DENIED
        or scoped exceptions are transparently recorded
~~~

**Đây là mã giả kiến trúc.** Hành động nâng revocation epoch và tạo outbox cần transaction/consistency thích hợp. Đối với Leaver, hệ thống phải ngăn **cấp mới bởi task cũ**, không chỉ xử lý các phiên hiện có.

### 27.1. Race condition phổ biến

~~~text
18:00:00  Security revoke sessions for user A
18:00:01  IGA queries existing sessions
18:00:02  Old login task creates a new session
18:00:03  IGA deletes only sessions from snapshot
18:00:04  New session survives although A is blocked
~~~

Cần **policy gate trên việc tạo phiên mới**, kiểm identity status/current revocation epoch và transaction ordering thích hợp. “Delete every session in current list” chưa đủ.

### 27.2. Idempotent retries

Một outbox message có thể được giao ít nhất một lần và lặp. `revoke(session)` cần xử lý an toàn khi session đã không còn. Nhưng **idempotency không cho phép event cũ hạ thấp security state**. Dùng version và compare-and-set/monotonic guard khi thích hợp.

### 27.3. Hai loại thành công khác nhau

- **Control plane:** đã gửi lệnh revoke và issuer đánh dấu.
- **Data plane:** PEP/target thực tế từ chối request/token/session.

Cần ghi cả hai, đặc biệt khi resource server dùng cache/JWT offline.

## 28. Reauthentication, step-up và session revocation

Không phải mọi tình huống cần revoke toàn bộ session. Có trường hợp đủ dùng **step-up authentication** hoặc reauthentication với assurance cao hơn.

### 28.1. Khi nào step-up hợp lý?

- User chuyển sang thao tác rủi ro cao.
- Phiên quá lâu kể từ lần MFA gần nhất.
- Device posture hoặc network risk thay đổi, nhưng chưa có bằng chứng compromise.
- Approval một giao dịch đặc quyền cần authentication freshness.
- Policy mới đòi factor chống phishing cho một action.

### 28.2. Khi nào revoke phù hợp hơn?

- Session/cookie/token bị nghi đánh cắp.
- Identity bị block hoặc Leaver.
- Grant/role cũ không còn hợp lệ.
- Recovery factor bị chiếm.
- Device mất kiểm soát.
- Sự kiện logout toàn bộ sessions có chủ đích.

### 28.3. Step-up không xóa session đã bị chiếm

Buộc MFA trên action đặc quyền có thể hạn chế rủi ro, nhưng một session bị đánh cắp có thể vẫn truy cập những endpoint **không yêu cầu step-up**. Nếu security incident nghiêm trọng, cần revoke session/token và xem xét credential recovery, không chỉ đòi user nhập thêm OTP.

### 28.4. Auth time, assurance và role freshness

Trong OIDC, có thể dùng `auth_time`, `acr`, `amr`, `max_age`/cơ chế tương ứng tùy provider để đánh giá freshness. **Một ID token chứa `auth_time` không tự thu hồi access token**. Từng PEP phải kiểm security state/assurance như policy yêu cầu.

## 29. Caching, thời gian và propagation guarantees

Một lý do lớn khiến thu hồi không tức thì là **cache** ở issuer, gateway, application, CDN, authorization engine, DB connection pool và các replica.

### 29.1. Cửa sổ tồn dư

Một cách mô hình hóa:

~~~text
Issued access token lifetime: 15 min
PDP entitlement cache TTL:    2 min
SCIM propagation delay:       variable
SaaS session invalidation:    provider-dependent
Active SSH session:           until terminated or disconnects

Không thể suy ra "revoke complete in 2 min"
chỉ từ một TTL trong các thành phần.
~~~

Nếu PEP chỉ kiểm token `exp`, rủi ro tồn dư có thể gần bằng **remaining token lifetime**. Nếu một SSH session không có session termination, thời gian tồn dư có thể **không bị chặn bởi token TTL**.

### 29.2. Bounded staleness

Hệ thống nên xác định **mức độ trễ tối đa chấp nhận được** theo action risk, chứ không chỉ đặt TTL tùy ý:

- Quyền thấp rủi ro có thể chấp nhận cache ngắn.
- `role.grant`, `payment.approve`, export PII hoặc production admin có thể cần state check gần real-time.
- PEP phải nhận invalidation event hoặc tra nguồn tin cậy cho hành động đặc biệt nhạy cảm.
- Khi event channel lỗi, cần fallback polling/readback và exception reporting.

### 29.3. Clock skew

Các trường `exp`, `nbf`, `iat`, `auth_time`, `effectiveAt`, `revokedAt` cần timezone/đồng hồ đáng tin. Leeway kiểm token phải **nhỏ, có chủ đích**; không mở khoảng chấp nhận quá lớn để che clock drift nghiêm trọng.

### 29.4. Consistency không giống availability

Thêm online token introspection giảm thời gian chấp nhận token đã revoke, nhưng có thể làm resource server phụ thuộc issuer availability. Cần thiết kế fail-safe, capacity, timeout, circuit breaker và runbook outage thay vì chọn “fail open” một cách vô điều kiện.

## 30. Audit trail, privacy và incident evidence

Một lần thu hồi cần đủ chứng cứ để xác định **nguyên nhân, phạm vi, người thực hiện, quyết định, từng target và thời điểm quyền thực tế bị chặn**.

### 30.1. Event minh họa

~~~json
{
  "eventType": "SESSION_REVOCATION_REQUESTED",
  "revocationRequestId": "rev-8842",
  "sourceEventRef": "hris-leaver-1881",
  "reasonCode": "LEAVER",
  "subjectIdentityId": "person-1042",
  "relationshipId": "employment-A-1042",
  "tenantId": "tenant-a",
  "scope": "ALL_SESSIONS_FOR_RELATIONSHIP",
  "initiatorType": "TRUSTED_LIFECYCLE_WORKFLOW",
  "actorIdentityRef": "iam-lifecycle-processor",
  "effectiveAt": "2026-11-23T18:00:00+07:00",
  "acceptedAt": "2026-11-23T18:00:02+07:00",
  "identityVersion": 42,
  "policyRevision": "session-revocation-v5"
}
~~~

### 30.2. Target outcome minh họa

~~~json
{
  "eventType": "SESSION_REVOCATION_TARGET_OUTCOME",
  "revocationRequestId": "rev-8842",
  "targetSystemId": "finance-saas",
  "targetSessionRef": "non-secret-session-reference",
  "operation": "TERMINATE_SESSION",
  "result": "VERIFIED_DENIED",
  "lastAllowedObservedAt": "2026-11-23T17:59:40+07:00",
  "firstDeniedObservedAt": "2026-11-23T18:00:08+07:00",
  "verificationMethod": "SAFE_AUTHZ_PROBE",
  "verifiedAt": "2026-11-23T18:00:09+07:00",
  "evidenceRef": "audit-evidence-7721"
}
~~~

Dữ liệu là mẫu, không phải schema chuẩn. **Không tự đặt `VERIFIED_DENIED` khi chưa có phép đo hoặc bằng chứng được xác nhận**.

### 30.3. Dữ liệu cần tránh trong log

- Raw session cookie/session ID có thể dùng xác thực.
- Access/refresh tokens, password, OTP, private key.
- Full ID token hoặc signed assertions nếu có thể bị tái sử dụng hoặc gây lộ PII.
- Dữ liệu nghiệp vụ/khách hàng không cần để chứng minh revocation.
- Device fingerprint quá chi tiết không có căn cứ privacy.

Nên dùng **correlation IDs không có khả năng xác thực**, reference tới kho evidence và kiểm soát retention/quyền xem.

### 30.4. Dữ liệu quan trọng cho điều tra

Một câu hỏi điều tra: “Có request nào PERMIT sau Leaver effectiveAt không?”. Cần tương quan **HRIS event time, issuer revoke, PEP decision, API/target action outcome, clock skew, log ingestion delay và session identity**. Chỉ xem một dòng `user.disabled=true` không đủ.

## 31. Reconciliation và chứng minh quyền không còn hiệu lực

**Reconciliation** so **desired session/access state** từ IAM/JML với **observed session/token/role state**, đồng thời kiểm **effective authorization** nơi có thể.

### 31.1. Ma trận đối soát

| Desired state | Observed/effective state | Kết luận |
| --- | --- | --- |
| Session S1 revoked | S1 bị PEP DENY | **MATCH / VERIFIED_DENIED** |
| IdP session revoked | SaaS local session còn ACTIVE | **RESIDUAL_SESSION** |
| Refresh grant revoked | Access JWT cũ vẫn PERMIT | **TOKEN_RESIDUAL** |
| User Leaver | VPN tunnel vẫn kết nối | **NETWORK_SESSION_RESIDUAL** |
| PAM elevation expired | SSH session vẫn có quyền admin | **PRIVILEGED_RESIDUAL** |
| Mover gỡ SalesAdmin | Old token vẫn có quyền Sales | **ROLE_CLAIM_STALENESS** |
| Device revoked | Một native client còn refresh family | **DEVICE_GRANT_GAP** |
| User blocked | Login mới vẫn tạo được session | **SESSION_CREATION_BYPASS** |
| SCIM disable acknowledged | SaaS API cho request tiếp theo | **TARGET_ENFORCEMENT_GAP** |
| Target không trả state | Không biết còn quyền hay không | **UNKNOWN**, không tự ghi PASS |
| Service decommissioned | Client credential vẫn mint token | **ORPHANED_GRANT** |

### 31.2. Nguồn cần đối chiếu

- **HRIS/Identity Registry:** relationship, lifecycle status, effectiveAt.
- **IdP/Authorization Server:** OP sessions, client grants, token families, revocation/epoch.
- **Application session stores:** cookie-backed sessions và local grants.
- **SCIM/Target management API:** account/group/role/active state.
- **API gateway/PDP/PEP:** quyết định chấp nhận token, quyền hiện hành.
- **PAM/VPN/OS/DB:** active sessions, open connections, jobs/tunnels.
- **Cloud IAM/workload registry:** role sessions, clients, keys và token issuance.
- **SIEM/Audit:** correlation, target actions và exceptions.

### 31.3. “Phép thử thu hồi” phải an toàn

Để xác minh một session đã bị chặn, nên dùng **kiểm tra không phá dữ liệu**, ví dụ call read-only API hoặc test endpoint phù hợp, với kiểm soát và quyền được cho phép. Không thực hiện một giao dịch nguy hiểm chỉ để chứng minh token cũ vẫn có hiệu lực.

Một phép thử 401/403 cần phân biệt **token invalid, API down, network error hoặc quyền tài nguyên bị từ chối vì lý do khác**. Bằng chứng phải đúng với khẳng định.

### 31.4. Hoàn tất khi nào?

Một workflow có thể kết thúc với **VERIFIED_DENIED cho tất cả target bắt buộc**, hoặc trạng thái **PARTIAL** với exception có owner/SLA nếu nền tảng không cho phép xác minh toàn bộ. Không nên ghi `SUCCESS` nếu security team còn biết một phiên RDP đang mở.

## 32. Incident response: token/session bị chiếm

### 32.1. Dấu hiệu

- Token xuất hiện trong log, repository hoặc bên ngoài nơi được phép.
- Session hoạt động ở vị trí/thiết bị lạ.
- Refresh-token reuse phát hiện bởi issuer.
- Đồng thời sử dụng một phiên ở các vùng không hợp lý.
- API request bất thường với role nhạy cảm.
- Người dùng báo thiết bị mất hoặc login không do mình thực hiện.
- Session tiếp tục thực thi sau security block/Leaver.
- Xảy ra nhiều token issuance mới dù đã revoke một grant.

### 32.2. Quy trình xử lý

1. Xác định identity, issuer, client, target, tenant và token/session scope.
2. Mở incident, lưu bằng chứng ở mức không lộ secret.
3. Áp **deny/security block** tại PEP/gateway nơi cần và khả thi.
4. Revoke sessions, refresh families và access tokens/grants theo threat model.
5. Chấm dứt các phiên PAM/VPN/SSH hoặc privileged sessions liên quan.
6. Rà MFA recovery methods, credential/password, device trust và delegated grants.
7. Kiểm activity từ thời điểm nghi compromise: action, data access, role grants và persistence.
8. Rotate/rekey credentials liên quan, bảo vệ token issuance mới.
9. Reconcile mọi target, kiểm token cũ bị từ chối và không còn đường bypass.
10. Khôi phục account/session hợp lệ theo policy và đóng incident sau review.

### 32.3. Không “re-enable” quá sớm

Sau khi revoke vì compromise, cho phép reauthentication với password cũ, MFA factor đã bị chiếm hoặc thiết bị chưa xử lý có thể khiến attacker tạo session mới ngay. Khôi phục phải gắn với **identity proofing/recovery và cập nhật trust** khi rủi ro yêu cầu.

## 33. Case study: Leaver trong hệ SSO + SaaS + API

Một tổ chức dùng HRIS, IdP OIDC, portal có session cookie, ERP SaaS có SCIM và API gateway dùng JWT.

### 33.1. Trước Leaver

~~~text
Identity: person-1042
Employment relationship: employment-A-1042
IdP browser session: ACTIVE
Portal session: ACTIVE
ERP SaaS local session: ACTIVE
Refresh grant on mobile: ACTIVE
Finance API JWT: exp in 20 minutes
VPN: connected
~~~

### 33.2. Leaver effective lúc 18:00

1. HRIS phát event và IGA xác minh identity/relationship.
2. IGA ghi revocation command versioned, nâng security/epoch guard nếu hệ hỗ trợ.
3. IdP disable login mới và revoke sessions/grants theo capability.
4. Portal xóa các local sessions của subject.
5. SaaS connector disable user, yêu cầu terminate sessions bằng API riêng nếu có.
6. Finance API gateway/PEP chặn JWT cũ thông qua current-state check/denylist.
7. VPN disconnect và kiểm không còn tunnel.
8. Audit ghi outcomes từng target; reconciliation thử các đường có rủi ro cao.
9. Một ERP local session vẫn ACTIVE → `RESIDUAL_SESSION`, security mở exception và xử lý.
10. Chỉ khi target từ chối quyền cần chặn hoặc có exception minh bạch mới kết thúc vận hành đúng quy trình.

### 33.3. Sai lầm phổ biến

Tổ chức báo “Offboarding hoàn tất” chỉ vì IdP disabled và SCIM trả 200, trong khi portal, VPN và ERP vẫn có phiên đang mở. Đây là **độ lệch giữa control-plane completion và effective access**.

## 34. Case study: Mover và JWT role claim cũ

**An** chuyển từ Sales sang Finance lúc 09:15. Access token JWT trước đó có role `SalesAdmin` và hết hạn lúc 10:00.

### 34.1. Không có revocation-aware PEP

API chỉ kiểm chữ ký và `exp`; từ 09:15–10:00 An có thể tiếp tục thực hiện `sales.discount.approve` dù role đã bị gỡ ở IAM.

### 34.2. Có revocation-aware PEP

IGA nâng `entitlementVersion` hoặc cập nhật deny policy; Sales API kiểm version/current entitlement tại thao tác nhạy cảm. Token cũ bị từ chối hoặc yêu cầu reauthentication.

### 34.3. Đánh đổi

Kiểm dữ liệu hiện hành có chi phí network/cache/availability. Nếu tổ chức chấp nhận cửa sổ tối đa 5 phút, phải **đo thực tế và tài liệu hóa**; nếu hành động cấp quyền đặc quyền đòi chặn tức thời, không thể chỉ dùng JWT offline TTL 45 phút.

## 35. Ma trận kiểm thử session revocation

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Logout current session | Cookie application hiện tại | Cookie/session bị vô hiệu; request tiếp theo bị từ chối |
| Stolen cookie reused | Server session đã revoked | Không còn được chấp nhận |
| Logout một thiết bị | Thiết bị khác có grant riêng | Chỉ phạm vi chính xác bị chặn |
| Logout all devices | Nhiều clients/devices | Các sessions/grants trong scope được xử lý |
| IdP logout | RP khác vẫn có local session | Phát hiện khoảng trống, không báo all revoked |
| OIDC back-channel | Logout token hợp lệ | RP invalidates matching local session |
| Forged logout token | Issuer/audience/signature sai | Reject, audit |
| Front-channel bị browser chặn | RP không nhận logout | Phân loại PARTIAL |
| SAML SLO target offline | SP session còn | Không tuyên bố SLO complete |
| OAuth revocation 200 | Token không tồn tại | Không suy token từng active |
| Refresh revoked | JWT cũ còn hạn | Resource deny theo cơ chế đã thiết kế hoặc ghi window |
| Refresh token replay | R1 dùng lại sau rotation | Phát hiện/response theo policy |
| Two refresh requests race | Cùng token bị gửi đồng thời | SDK/concurrency handling, không disable detection |
| JWT wrong issuer | Ký bởi issuer khác | Reject |
| JWT wrong audience | Token API-A dùng API-B | Reject |
| JWT expired | `exp` quá hạn | Reject |
| JWT `jti` denied | Token đã revoked | Reject tại PEP |
| Revocation store unavailable | Không xác định trạng thái | Fail-safe theo risk |
| Cached introspection `active=true` | Token vừa revoked | TTL/invalidation theo policy, đo staleness |
| Leaver effectiveAt | Login task cũ xử lý muộn | Không tạo session mới |
| Mover role change | Token role cũ vẫn còn | Không PERMIT action đã thu hồi |
| Owner-driven revoke | Entitlement bị gỡ | Session/resource không còn action tương ứng |
| SCIM disable success | SaaS local session còn | RESIDUAL_SESSION |
| PAM JIT expiry | SSH session còn mở | Terminate/revalidate theo policy |
| VPN revoke | Tunnel đã connected | Ngắt và verify |
| WebSocket connection | Session revoked giữa stream | Close/revalidate message |
| DB pooled connection | Credential revoked | Chặn use/reconnect theo target capability |
| Service account retired | OAuth client token còn dùng | Detect/revoke/expire và kiểm API |
| Robot uses old delegated user token | User Leaver | Không được thực hiện task trái quyền |
| Revoke twice | Duplicate event | Idempotent, audit không lặp side effects |
| Old event arrives late | Version cũ | Không hồi sinh session/permissions |
| Cross-tenant same username | Relationship khác | Chỉ revoke scope hợp lệ hoặc mở rộng theo incident policy |
| Bulk revoke wrong target | Client không có thẩm quyền | DENY |
| Revoked token behind alternate gateway | Backend bypass main PEP | Chặn đồng nhất |
| API unavailable during verification | Không chứng minh được deny | UNKNOWN, exception |
| Key rotation | JWKS cache cũ | Bounded rollout và trust validation |
| Session ID in logs | Log chứa cookie khả dụng | Test thất bại, redaction |
| Retest after reauthentication | Security block vẫn còn | Không mở session mới |
| Access denied due to network failure | Không kiểm chứng token | Không tự ghi VERIFIED_DENIED |

### 35.1. Test end-to-end

~~~text
Authoritative event / user logout
  -> Revocation authority and scope validated
  -> Session/grant/identity version updated
  -> Commands delivered to IdP, RP, SaaS, API and PAM
  -> Revocation effects visible at all relevant PEPs
  -> Old session/token/connection denied or terminated
  -> No stale task can create unauthorized new session
  -> Evidence and residual exceptions recorded
~~~

Một test chỉ nhận HTTP 200 từ endpoint revoke **không đủ**; cần kiểm quyền thực thi ở target và những cửa sổ chấp nhận token cũ.

## 36. KPI và giám sát

| KPI | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Revocation request-to-apply latency** | Từ quyết định tới khi các target báo đã áp | Khác effective denial |
| **Revocation-to-effective-denial latency** | Từ event tới request cũ bị từ chối | Chỉ số quan trọng theo risk |
| **Residual sessions after Leaver** | Phiên còn sau effectiveAt | Phân loại theo IdP/SaaS/PAM |
| **JWT stale-token acceptance** | Token đã revoke vẫn PERMIT | Đo theo token TTL/PEP |
| **Refresh-family compromise response time** | Từ replay alert tới containment | Không chỉ revoke một token |
| **SSO logout propagation coverage** | RP hỗ trợ và thực thi logout | Không coi SLO là toàn năng |
| **SCIM deactivation effectiveness** | Disable + session/role outcome | Không chỉ đếm 200 |
| **Session creation after block** | Login mới dù subject bị block | PEP/issuer guard |
| **Long-lived privileged session count** | PAM/SSH/VPN chưa đóng sau revoke | Cần runtime termination |
| **Revocation event delivery lag** | Độ trễ queue/cache/region | Theo failure domain |
| **UNKNOWN / unsupported targets** | Không xác minh được | Có owner và SLA |
| **Audit correlation completeness** | Có subject, target, decision, outcome | Không ghi secret |
| **Revocation retry success** | Lỗi tạm được remediation | Đừng che persistent failure |
| **Cross-tenant scope errors** | Thu hồi nhầm hoặc bỏ sót tenant | Kiểm identity mapping |
| **Access-recertification triggered revokes** | Quyền bị rút sau review | Kiểm hiệu lực thực |
| **False-positive global logout rate** | Phạm vi thu hồi quá rộng gây outage | Cần giảm tác động không cần |

Không có một SLA chung áp cho tất cả hệ. Tổ chức phải xác định **ngưỡng thời gian theo mức rủi ro, khả năng nền tảng và sự kiện JML**, rồi đo bằng evidence thực.

## 37. Checklist triển khai và vận hành

| Câu hỏi | Bằng chứng |
| --- | --- |
| Đã inventory IdP, RP, SaaS, PAM, VPN, API sessions? | Session/target matrix |
| Phân biệt app cookie, IdP session, access và refresh tokens? | Architecture và token inventory |
| Có xác định logout/revoke scope theo user/device/client/tenant? | API contracts |
| Có identity linking bằng issuer+subject, relationship? | Identity registry |
| Có kiểm authority của actor yêu cầu revoke? | Authorization tests |
| Có bảo vệ endpoint revoke trước CSRF/caller spoof? | Backend PEP |
| Có theo dõi session/credential trên nhiều browser/thiết bị? | Grant/session registry |
| Có session store phân tán và invalidation nhất quán? | Multi-node tests |
| Có TTL/idle/absolute timeout phù hợp? | Config và expiry tests |
| JWT có cơ chế revoke sớm cho quyền nhạy cảm? | Denylist/epoch/current-state check |
| API xác minh issuer, audience, signature, exp và scope? | JWT/introspection tests |
| Có xác định behavior của RFC 7009 revocation ở issuer? | Provider capability tests |
| Có xử lý refresh-token family/replay? | Rotation tests |
| Có đo introspection caching staleness? | Test results và TTL policy |
| OIDC RP/back-channel logout có được xác minh? | RP logout evidence |
| SAML SP thực sự hỗ trợ SLO hay không? | SaaS capability matrix |
| SCIM disable có kèm session termination khi cần? | Target readback |
| Có xử lý PAM/JIT/SSH/RDP/VPN active sessions? | Runtime termination tests |
| WebSocket/gRPC streams có bị cắt khi revoke? | Streaming tests |
| Non-human principal có revoke trust/token/keys riêng? | Workload inventory |
| Joiner canceled có hủy preboarding sessions? | JML integration tests |
| Mover có chặn old role/tenant claims? | Resource-level authorization tests |
| Leaver có chặn login task cũ tạo session mới? | Version/race tests |
| Có event source validation và idempotency? | Message signing/version guard |
| Có phân biệt SENT, APPLIED, VERIFIED_DENIED, UNKNOWN? | State machine/audit schema |
| Có thu hồi theo risk mà không logout bừa mọi user? | Scoped policy |
| Có phương án khi issuer/PDP/SCIM unavailable? | Fail-safe runbook |
| Có kiểm session/cookie/token sau password/MFA reset? | Recovery tests |
| Có bảo vệ raw tokens/session IDs khỏi log? | Privacy controls |
| Có reconcile desired/observed/effective access? | Evidence dashboard |
| Có kiểm session revocation xuyên multi-region? | Propagation tests |
| Có SLA, owner và escalation cho residual access? | Incident/remediation tracking |

## 38. Những nhầm lẫn thường gặp

1. **“Logout đồng nghĩa thu hồi mọi phiên trên mọi thiết bị.”** Scope phụ thuộc ứng dụng và cơ chế hỗ trợ.
2. **“Disable user tại IdP là mọi JWT API vô hiệu ngay.”** JWT có thể được kiểm offline đến `exp`.
3. **“SCIM `active=false` là SaaS session bị terminate.”** Hai khả năng không đồng nhất.
4. **“Xóa cookie ở browser đủ chặn bản sao cookie bị đánh cắp.”** Server phải vô hiệu session state.
5. **“Revoke refresh token làm mọi access token cũ chết ngay.”** Phụ thuộc issuer và resource PEP.
6. **“OAuth RFC 7009 trả 200 chứng minh mọi phiên đã đóng.”** Không có ngữ nghĩa đó.
7. **“OIDC logout cũng là OAuth access-token revocation.”** Hai cơ chế khác nhau.
8. **“SAML SLO bắt buộc hoạt động với mọi SP.”** Hỗ trợ vendor/cấu hình có thể khác.
9. **“JWT signature đúng là quyền vẫn hợp lệ.”** Cần kiểm audience, revocation và current authorization.
10. **“Access token ngắn hạn bảo đảm revoke tức thì.”** Token còn hạn có thể tiếp tục dùng.
11. **“Thu hồi JIT grant sẽ tự tắt SSH/RDP session.”** Cần session termination/reauthorization.
12. **“PAM recording tự chặn hành động.”** Recording là evidence, không phải PEP.
13. **“Session bị revoke thì lệnh đã commit được hoàn tác.”** Phải có compensation nghiệp vụ riêng.
14. **“User Mover phải logout tất cả ứng dụng.”** Phụ thuộc quyền và risk; có thể revoke có mục tiêu.
15. **“Leaver chỉ cần đợi token TTL.”** Quyền nhạy cảm có thể cần chặn ngay.
16. **“Refresh-token rotation không gặp race.”** Concurrency cần được quản lý.
17. **“Cache `active=true` không ảnh hưởng tốc độ thu hồi.”** Có thể tạo staleness.
18. **“Có CAEP/RISC là mọi SaaS đều revoke thời gian thực.”** Receiver phải hỗ trợ và thực thi.
19. **“Một event được gửi là target đã nhận và áp dụng.”** Cần delivery/outcome/readback.
20. **“Session ID chỉ là metadata nên có thể log raw.”** Thường là bearer credential nhạy cảm.
21. **“Đóng browser là WebSocket/nghiệp vụ nền chắc đã dừng.”** Active streams/jobs có thể còn.
22. **“Service principal không có human session nên không cần revoke.”** Có token, cert, grants và connections.
23. **“`jti` denylist là đủ cho mọi token.”** Token có thể thiếu jti, có nhiều issuer và bypass caches.
24. **“Khóa người dùng xong thì task queue cũ không thể tạo session.”** Cần gate theo current state.
25. **“TARGET UNKNOWN có thể coi SUCCESS nếu không có lỗi.”** Không có bằng chứng thì chưa verified.
26. **“Đổi signing key là cách tốt nhất logout một user.”** Tác động rộng và phức tạp.
27. **“Bất kỳ 401 nào cũng chứng minh token đã revoke.”** Có thể do network/config/endpoint khác.
28. **“Reauthentication tự xóa security incident.”** Recovery phải theo thẩm quyền và trust mới.
29. **“Thu hồi entitlement giống thu hồi session.”** Mỗi lớp có trạng thái và hiệu lực riêng.
30. **“Có dashboard 100% dispatched nghĩa mọi quyền đã hết.”** Cần kiểm effective access.

## 39. Câu hỏi tự đánh giá

1. Session revocation khác logout, session expiration và entitlement removal ở điểm nào?
2. Vì sao một người có nhiều phiên ở IdP, RP, SaaS, VPN và PAM?
3. Phân biệt cookie-backed session, JWT access token và refresh token.
4. Vì sao xóa cookie không đủ chặn stolen session cookie?
5. JWT ký hợp lệ có thể vẫn PERMIT sau IdP revoke trong trường hợp nào?
6. Kể ít nhất ba chiến lược thu hồi JWT trước `exp` và đánh đổi.
7. RFC 7009 và RFC 7662 phục vụ các mục tiêu khác nhau thế nào?
8. Tại sao revocation endpoint có thể trả 200 khi token không tồn tại?
9. Revoke refresh token có luôn làm access token hiện tại hết hiệu lực không?
10. Refresh-token rotation phát hiện replay theo cách nào?
11. RP-initiated logout, front-channel và back-channel OIDC khác gì?
12. Vì sao logout token OIDC không phải access token?
13. SAML SLO có hạn chế gì khi một SP offline?
14. Vì sao SCIM disable user chưa chứng minh SaaS session đã bị chặn?
15. Trong Mover, làm sao xử lý JWT vẫn mang role cũ?
16. Trong Leaver, vì sao cần chặn login task cũ tạo session mới?
17. Một employee có hai relationship: làm sao thu hồi đúng tenant/role?
18. PAM JIT grant hết hạn nhưng SSH session còn mở: xử lý thế nào?
19. WebSocket đã authenticate có cần kiểm revocation sau khi kết nối không?
20. Vì sao stop service pod không tự revoke OAuth client credential?
21. Thế nào là control-plane APPLIED và data-plane VERIFIED_DENIED?
22. Làm sao thiết kế idempotency và versioning cho revocation event đến sai thứ tự?
23. Khi introspection unavailable, “fail open” có những rủi ro nào?
24. Trong Spring Security stateful, `HttpSession.invalidate()` xử lý những gì và không xử lý gì?
25. Trong Spring Security JWT Resource Server, cần thêm gì để revoke JWT sớm?
26. Audit event cần những trường nào để điều tra một request PERMIT sau Leaver?
27. Phân biệt desired, observed và effective session state trong reconciliation.
28. Nêu ba negative tests quan trọng cho SSO logout, token cache và PAM.
29. Vì sao không được log raw session ID hoặc token?
30. Những KPI nào phản ánh hiệu lực thu hồi hơn là số lệnh gửi đi?

## 40. Ghi nhớ

**Session revocation** là quá trình **vô hiệu hóa khả năng tiếp tục sử dụng một phiên hoặc trạng thái truy cập đã được cấp**, theo **đúng identity, client, thiết bị, tenant, quan hệ làm việc, quyền và thời điểm**. Phải phân biệt **logout, hủy server session, revoke OAuth grants/refresh tokens, chặn JWT access token, OIDC/SAML logout, gỡ RBAC entitlements và terminate PAM/SSH/VPN/streaming connections**. Không cơ chế đơn lẻ nào mặc nhiên kiểm soát toàn bộ những đường truy cập này.

Trong IAM **Joiner–Mover–Leaver**, **HRIS/identity registry** xác định căn cứ vòng đời, **IdP/SSO** kiểm login/grants, **SCIM/API** quản lý một phần account/role, **RBAC/ABAC/PBAC và PEP** quyết định thao tác có còn được phép, còn **PAM, event-driven revocation, audit và reconciliation** giúp chặn và kiểm chứng những quyền tồn dư. **Disable account không đồng nghĩa mọi session đã đóng; revoke refresh token không bảo đảm mọi JWT cũ ngừng hoạt động; gửi lệnh không chứng minh resource thực sự DENY.** Thiết kế đúng phải có **phạm vi và thẩm quyền rõ, chống race/replay, đồng bộ cache, xử lý phiên đang mở, giới hạn cửa sổ tồn dư, bằng chứng VERIFIED_DENIED và trách nhiệm xử lý mọi ngoại lệ**.
