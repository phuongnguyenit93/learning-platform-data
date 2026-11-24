# Access token lifecycle trong IAM: phát hành, sử dụng, hết hạn và thu hồi

**Access token lifecycle (vòng đời access token)** là toàn bộ quá trình từ khi **Authorization Server (AS)** quyết định cấp một access token cho client, đến khi token được **Resource Server (RS)** nhận, xác minh và sử dụng trong quyết định truy cập, rồi **hết hạn hoặc bị từ chối/thu hồi** theo chính sách. Bài toán không chỉ là tạo ra một chuỗi ký số có thời hạn: tổ chức còn phải bảo đảm token đúng **chủ thể, client, audience, scope, thời gian, tenant và trạng thái quyền hiện hành**, đặc biệt sau khi nhân viên chuyển vai trò hoặc nghỉ việc.

Bài **“Access token lifecycle”** thuộc chương **Token và credential** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu quản lý danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo account, cấp quyền, thay đổi role, rà soát và thu hồi; kết hợp **IdP, SSO, SCIM, RBAC/ABAC, service accounts, kiểm toán** và giảm quyền truy cập tồn dư. Trong bài này, mỗi sự kiện JML đều được xem xét dưới góc độ **access token đã phát trước sự kiện** và **access token được cấp sau sự kiện**.

**Tình huống dẫn nhập:** Một nhân viên có quyền duyệt thanh toán nhận access token lúc 08:55, token hết hạn 09:25. Đúng 09:00, HRIS ghi sự kiện **Mover** và IGA gỡ quyền Approver. Nếu API chỉ kiểm chữ ký, audience và thời hạn của JWT, token cũ có thể vẫn gọi chức năng duyệt đến 09:25. Việc xóa nhóm ở IdP hoặc hoàn tất SCIM PATCH chưa đủ để chứng minh quyền đã mất. Cần hiểu **token lifetime, cơ chế chặn sớm, chính sách ở RS/PEP và bằng chứng truy cập thực tế**.

## 1. Access token là gì và không phải là gì?

Trong OAuth 2.0, **access token** là credential mà client dùng để truy cập **protected resource** tại Resource Server trong phạm vi mà hệ thống ủy quyền cho phép. Token có thể là chuỗi **opaque** cần được kiểm tra qua AS/introspection hoặc có định dạng tự chứa như **JWT** để RS có thể xác minh cục bộ theo hợp đồng tin cậy.

| Khái niệm | Chức năng | Điều không nên suy ra |
| --- | --- | --- |
| **Access token** | Mang bằng chứng cho client gọi API trong phạm vi được ủy quyền. | Token hợp lệ cho phép mọi object/action. |
| **Refresh token** | Credential mà client đủ điều kiện dùng với AS để yêu cầu access token mới. | Token dùng trực tiếp để gọi Resource Server. |
| **OIDC ID token** | Xác nhận sự kiện xác thực người dùng cho OIDC client theo protocol. | Credential gọi API thay access token. |
| **SSO/IdP session** | Phiên đăng nhập giúp người dùng xác thực hoặc khởi tạo luồng cấp quyền mới. | Khi session bị đóng, mọi access token đã phát đều vô hiệu ngay. |
| **Application/client credential** | Xác thực confidential client hoặc workload với AS/STS. | Chính credential này là access token của API. |
| **Entitlement/role/grant** | Quyền của subject/client tại IAM hoặc ứng dụng. | Mọi token đã phát luôn phản ánh quyền mới nhất. |
| **API key / PAT** | Credential đặc thù của target/API; có thể tồn tại ngoài OAuth. | Tự tuân theo chu kỳ thu hồi của OAuth access token. |

**Access token không nhất thiết chứa danh tính người dùng.** Trong **client credentials**, token có thể đại diện cho ứng dụng/workload mà không có người dùng hiện diện. Trong luồng **delegated**, token liên quan cả client, resource owner/người dùng và phạm vi ủy quyền theo AS/RS contract. Không áp đặt một cấu trúc claims chung cho tất cả nhà cung cấp.

### Phân biệt validity và authorization

- **Token validity**: token có phải credential được issuer tin cậy phát hành, còn thời hạn, đúng đối tượng nhận, đúng loại và có chứng cứ xác thực cần thiết không?
- **Token authorization**: subject/client **hiện tại** có quyền thực hiện action cụ thể trên resource/tenant/context này hay không?
- **Enforcement**: API, batch worker và các đường ghi dữ liệu có thật sự chặn request khi một trong hai kiểm tra không đạt không?

Token **valid** không tự động đồng nghĩa với action được **ALLOW**. Đây là ranh giới căn bản cần giữ suốt vòng đời token.

## 2. Những thành phần tham gia vòng đời token

~~~mermaid
flowchart LR
    HR["HRIS / JML"] --> IGA["IGA: desired access, roles, expiry"]
    IGA --> IDP["IdP / Directory"]
    IGA --> POL["Policy / Entitlements"]
    U["User hoặc workload"] --> C["OAuth Client"]
    C --> AS["Authorization Server"]
    IDP --> AS
    POL --> AS
    AS --> TOK["Access token + metadata"]
    TOK --> C
    C --> RS["Resource Server / API"]
    RS --> V["Token verification"]
    RS --> PEP["PEP + domain authorization"]
    POL --> PEP
    PEP --> DATA["Protected resource"]
    RS --> AUD["Audit / Monitoring"]
    AS --> AUD
~~~

| Thành phần | Vai trò trong lifecycle | Bằng chứng cần đối soát |
| --- | --- | --- |
| **Resource owner/user** | Đăng nhập hoặc cho phép ủy quyền khi flow yêu cầu. | Stable subject ID, trạng thái JML, grant/consent. |
| **Client** | Xin token và trình token đúng RS. | Client ID, client type, phương thức xác thực, redirect/PKCE hoặc workload trust. |
| **Authorization Server** | Xác minh các điều kiện cấp token, scope/grant, phát hành, hỗ trợ refresh/revocation/introspection tùy thiết kế. | Issuer, policy/grant version, token events, credential trust. |
| **Resource Server** | Nhận credential và xác định action có được phép hay không. | Audience, validity, tenant/resource, PEP outcome. |
| **Identity Provider / HRIS** | Cung cấp danh tính, trạng thái nhân sự và sự kiện xác thực. | Subject mapping, effectiveAt, status/revision. |
| **IGA / RBAC / ABAC** | Quản lý desired privileges, policy và thay đổi quyền. | Granted vs effective, conditions, SoD, TTL. |
| **Gateway/API worker** | Điểm vào hoặc đường xử lý phụ. | Coverage của tất cả endpoints/bulk/async paths. |
| **Audit/SIEM** | Ghi nhận token issuance, usage, reject, revocation và anomalies. | Timestamp, correlation, issuer, client, policy version, không chứa token thô. |

### Tách identity của các thành phần

**User identity**, **OAuth client identity**, **workload identity** và **target resource/account ID** có thể khác nhau. Một backend gọi API thay user phải truyền đúng **ủy nhiệm hợp lệ**; một batch chạy app-only không nên bị ghi nhầm là hành động của nhân viên sở hữu job.

## 3. Các trạng thái của một access token

Để vận hành, có thể hình dung token đi qua những trạng thái logic sau; đây là **mô hình mô tả**, không phải state machine chuẩn áp đặt bởi OAuth:

~~~mermaid
stateDiagram-v2
    [*] --> NOT_ISSUED
    NOT_ISSUED --> ISSUED: AS chấp thuận grant và tạo token
    ISSUED --> ACCEPTABLE: Trong hạn + đúng các điều kiện kiểm
    ISSUED --> EXPIRED: Thời hạn qua
    ACCEPTABLE --> ACCEPTABLE: Request hợp lệ, authorization ALLOW
    ACCEPTABLE --> REJECTED: Sai scope/resource/tenant hoặc bị chặn
    ACCEPTABLE --> EXPIRED: exp tới hạn
    ACCEPTABLE --> REVOKED_OR_BLOCKED: Token/grant/subject bị vô hiệu theo cơ chế áp dụng
    REJECTED --> ACCEPTABLE: Nếu chỉ request cụ thể bị DENY, token còn hợp lệ cho action khác
    REVOKED_OR_BLOCKED --> [*]
    EXPIRED --> [*]
~~~

### Không nhầm REJECTED với REVOKED

Một request bị **403 Forbidden** vì token thiếu scope không làm token biến mất; client có thể vẫn gọi thành công một endpoint khác có scope phù hợp. Ngược lại, token được **revoke theo chính sách** cần bị từ chối tại những RS bắt buộc theo khả năng và SLA đã định, chứ không chỉ bị chặn một action.

### Token không có “lifecycle state” thống nhất toàn hệ thống

Một JWT tự chứa đã phát có thể **không có bản ghi phiên riêng** tại từng RS. AS có thể đã vô hiệu refresh grant nhưng RS vẫn xác minh JWT cũ bằng khóa công khai và chấp nhận cho tới expiry. Đừng suy luận rằng AS đã hiển thị “revoked” là mọi node/edge cache đã ngừng ALLOW.

## 4. Issuance: điều gì phải đạt trước khi cấp access token?

Cấp token là một **quyết định bảo mật**, không phải hành động tạo chuỗi ngẫu nhiên tùy ý. Các kiểm tra phụ thuộc vào OAuth grant type, client class và policy triển khai.

1. **Client được xác định** và đã đăng ký hoặc được tin cậy theo AS.
2. **Client authentication hoặc proof** phù hợp loại client: confidential client secret, mTLS, private_key_jwt, workload federation, hoặc bảo vệ khác của public client.
3. **Grant flow hợp lệ**: authorization code + PKCE cho luồng người dùng phù hợp, client credentials cho app-only khi được cho phép, token exchange nếu có contract.
4. **Subject/grant còn đủ điều kiện**: status HRIS/IdP, hợp đồng, suspended, consent, approved entitlement và restrictions.
5. **Audience/resource được chọn đúng** cho API đích, không tự cho token đa mục đích.
6. **Scopes/app roles được kiểm** theo client grant, user permissions và policy; không tin chuỗi scope do client xin là đã được duyệt.
7. **Thời hạn** được đặt theo risk, token type và khả năng thu hồi; không tự coi TTL ngắn là đã thay thế authorization.
8. **Metadata phát hành**: issuer, thời gian, token ID/reference nếu áp dụng, client/subject và audit event đủ để điều tra.
9. **Sender constraint** nếu policy yêu cầu; token có thể bị ràng buộc với certificate hoặc proof-of-possession key.
10. **Không trả credential vào log, URL hoặc điểm lưu trữ không cần thiết**.

### Hai mô hình issuance phổ biến

| Flow | Đối tượng | Lưu ý lifecycle |
| --- | --- | --- |
| **Authorization Code + PKCE** | Ứng dụng có người dùng tương tác. | Xác thực user, redirect/PKCE, consent/grants, access token và có thể refresh token; cookie phiên không đồng nghĩa access token. |
| **Client Credentials** | Confidential client/workload không cần user tương tác. | Quyền app-only, client authentication/trust, thường không cần refresh token; phải quản lý workload principal và credential riêng. |

Các flows khác chỉ được dùng khi phù hợp chuẩn/AS contract. **Không dùng Resource Owner Password Credentials như phương án mặc định cho job/app mới**, không biến username/password nhân viên thành credential của automation.

## 5. Ví dụ sequence từ đăng nhập tới API

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant C as Ứng dụng client
    participant AS as IdP / Authorization Server
    participant RS as Finance API / Resource Server
    participant P as Current policy + resource state
    U->>C: Truy cập chức năng Finance
    C->>AS: Authorization request (PKCE, redirect, scopes...)
    AS->>U: Xác thực và yêu cầu consent nếu cần
    U-->>AS: Hoàn tất xác thực
    AS-->>C: Authorization code
    C->>AS: Đổi code + PKCE verifier
    AS-->>C: Access token (+ refresh token nếu được cấp)
    C->>RS: Request kèm access token
    RS->>RS: Validate token/issuer/audience/expiry
    RS->>P: Check actor, tenant, action, resource, JML/SoD
    P-->>RS: ALLOW hoặc DENY
    RS-->>C: Dữ liệu hoặc lỗi phù hợp
~~~

**Lưu ý quan trọng:** sơ đồ giản lược thành phần browser/client và bảo vệ redirect; không mô tả token được trao qua URL query. Trong một ứng dụng có backend-for-frontend, token có thể được giữ server-side thay vì trình duyệt. Chọn thiết kế theo threat model, không lấy sơ đồ làm hướng dẫn lưu token ở JavaScript tùy tiện.

## 6. Access token ở dạng JWT và opaque

| Tiêu chí | JWT tự chứa | Opaque/reference token |
| --- | --- | --- |
| **Dữ liệu nhìn thấy** | Claims trong payload có thể được giải mã Base64URL, thường **không được mã hóa**. | Không cần có ý nghĩa với client/RS ngoài verifier. |
| **Kiểm chứng RS** | Kiểm chữ ký/JWKS, issuer, audience, time, token type, claims. | Thường introspect với AS hoặc kiểm theo hệ thống riêng. |
| **Latency** | Có thể xác minh offline nhanh. | Có thể phát sinh gọi mạng hoặc cache kết quả introspection. |
| **Thu hồi sớm** | Cần cơ chế bổ sung nếu không chờ expiry. | AS có thể báo inactive, nhưng phụ thuộc caching và propagation. |
| **Rủi ro** | Claim stale, key/cache drift, lộ dữ liệu payload, token replay. | AS availability, cache stale, bí mật token bị lộ. |
| **Phù hợp** | API cần high throughput/offline verification có TTL/controls phù hợp. | Cần kiểm soát trạng thái trung tâm hoặc ẩn claims khỏi client. |

**Không có quy tắc “JWT luôn tốt hơn opaque” hoặc ngược lại.** Lựa chọn dựa trên risk, latency, SLA thu hồi, khả năng AS/RS, privacy và operation. JWT có thể là **bearer token**; một chữ ký số không làm token tự trở thành sender-constrained.

## 7. Các claims quan trọng và cách diễn giải

Ví dụ token JWT mang thông tin tối thiểu (chỉ minh họa cấu trúc, **không phải token hợp lệ hoặc claim set chuẩn cho mọi issuer**):

~~~json
{
  "iss": "https://idp.example.internal",
  "sub": "person-4821",
  "aud": "finance-api",
  "client_id": "finance-web-client",
  "scope": "invoice.read payment.approve",
  "iat": 1795400000,
  "nbf": 1795400000,
  "exp": 1795400900,
  "jti": "token-demo-001"
}
~~~

| Claim/thuộc tính | Ý nghĩa điển hình | Kiểm soát cần lưu ý |
| --- | --- | --- |
| **iss** | Issuer token. | Match chính xác issuer trust configuration, không tin tự động. |
| **sub** | Subject của token theo contract. | Có thể là user hoặc application; không mặc định email, không tự diễn giải mọi provider giống nhau. |
| **aud** | Audience hoặc tập audiences. | Token phải dành cho RS hiện tại; tránh token confusion. |
| **client_id / azp / appid** | Client/authorized party theo profile/provider. | Chọn claim theo issuer contract, không sao chép vendor mappings tùy ý. |
| **scope / scp / roles** | Phạm vi hoặc vai trò được AS gán theo profile. | Cần quyền theo action/resource/tenant ở RS, không coi toàn bộ policy đã nằm trong token. |
| **iat** | Thời điểm phát hành. | Hỗ trợ phân tích tuổi token; không đủ một mình để xác minh hiện hành. |
| **nbf** | Không được chấp nhận trước mốc thời gian. | Kiểm với sai số đồng hồ có giới hạn. |
| **exp** | Thời điểm hết hạn. | Không nhận token sau expiry, không hứa thu hồi sớm nếu chưa có cơ chế. |
| **jti** | ID token khi issuer cung cấp. | Hữu ích với denylist/replay detection; không phải mọi token có jti. |
| **cnf** | Có thể mô tả ràng buộc proof-of-possession. | RS phải xác minh proof/certificate thực, không chỉ đọc claim. |

**Chỉ parse JWT rồi đọc claims là không đủ.** RS phải xác minh cryptographic integrity, loại token, issuer/audience và policy; tuyệt đối không tin chuỗi JWT từ nguồn khác chỉ vì nội dung nhìn hợp lý.

## 8. Thời hạn: exp, nbf, TTL và lệch đồng hồ

Một token có thể được phát lúc **issuedAt** và hết hạn ở **exp**. **TTL** là khoảng thời gian token có thể được chấp nhận theo thời hạn, không phải tổng thời gian một entitlement của user còn hợp lệ.

~~~text
08:55     Access token được phát cho Payment Approver
09:00     Mover có hiệu lực, quyền Approver bị gỡ trong IGA
09:00+    Token cũ vẫn còn exp=09:25
09:25     Token hết hạn về mặt thời gian
~~~

### Bài toán “stale authorization window”

Nếu RS chỉ kiểm chữ ký và exp, khoảng **09:00–09:25** là một **cửa sổ quyền có thể tồn dư** (giả sử token vẫn có claim/quyền được RS sử dụng). Nếu có current-state authorization hoặc token revocation được RS tôn trọng, quyền có thể bị chặn trước 09:25.

### Các nguyên tắc TTL

- **Ngắn hơn** thường giảm thời gian bearer token bị lộ có thể sử dụng, nhưng làm tăng số lần cấp token và phụ thuộc AS.
- **Dài hơn** giảm nhu cầu refresh nhưng làm tăng risk khi quyền thay đổi hoặc token bị lộ.
- Chọn TTL theo **risk/sensitivity, client type, năng lực refresh/reissue, RS revocation model, availability** và SLA JML.
- Có **clock skew tolerance có giới hạn**; không cộng một khoảng “grace” quá lớn làm mất tác dụng exp.
- Kiểm nbf, exp, thời điểm phát hành theo profile, timezone/clock đồng bộ; không lấy đồng hồ client làm nguồn policy.
- **Token hết hạn không tự dọn server-side grant** và không chứng minh refresh token đã bị vô hiệu.

### Ví dụ tính khả năng thu hồi (chỉ để phân tích)

Nếu access token có TTL 15 phút và RS không có khả năng từ chối trước hạn, một token phát **ngay trước mốc thu hồi** có thể vẫn dùng gần 15 phút. Đây không phải bảo đảm mọi token đều sống đủ 15 phút: điều đó còn tùy chính sách thực thi, mạng, session/grant và target. Cần **đo thực tế ở RS**, không dựa vào lời hứa từ config.


## 9. Lưu trữ và chuyển access token từ client tới API

Access token thường là **credential nhạy cảm**. Với bearer token, ai chiếm được token hợp lệ có thể dùng nó trong giới hạn token và các bảo vệ bổ sung, nên cần giới hạn khả năng đọc, sao chép và truyền token.

### Các biện pháp cần phân theo loại client

| Loại client | Hướng xử lý | Rủi ro đặc trưng |
| --- | --- | --- |
| **Backend confidential client** | Giữ token ở server, bảo vệ process/secrets, gửi tới target qua TLS, cache có phân vùng. | SSRF, log/trace lộ Authorization header, dùng nhầm token giữa tenants. |
| **Browser SPA/public client** | Authorization Code + PKCE, token storage dựa trên threat model; cân nhắc BFF/server-side session. | XSS, extension độc hại, token nằm trong browser context, CSRF khi dùng cookie. |
| **Native/mobile public client** | PKCE, cơ chế lưu trữ do OS hỗ trợ, redirect URI an toàn, hạn chế token exposure. | Device compromise, backup/clipboard/log leaks, app impersonation. |
| **CLI** | Token cache bảo vệ theo OS permissions, expiry, revoke khi sign-out. | Shared workstation, terminal history, diagnostic output. |
| **Batch/workload** | Managed/federated identity, token ngắn hạn, workload-bound storage, không hard-code. | Container image/log/process memory, broad trust bindings. |

**Không có lời khuyên “luôn lưu access token trong localStorage” hoặc “cookie luôn tuyệt đối an toàn”**. Cookie có thể giảm quyền đọc token của JavaScript nếu HttpOnly, nhưng cần bảo vệ CSRF/SameSite, session fixation và chính sách của backend; localStorage chịu rủi ro XSS và lifetime. Lựa chọn theo topology, threat model và khả năng bảo vệ client.

### Quy tắc truyền token

- Truyền access token qua **TLS**; đối với bearer tokens thường sử dụng **Authorization: Bearer** theo contract API.
- **Không gửi token trong URL query** vì dễ lộ qua logs, browser history, referrer và monitoring.
- Không ghi nguyên bearer token vào **application logs, reverse-proxy logs, traces, crash reports, error telemetry hoặc ticket**.
- Chỉ gửi token tới **allowed target origins**; thận trọng với HTTP redirects và các client tự động forward Authorization header.
- Tránh truyền token cho một downstream API có **audience khác**; dùng luồng nhận token mới/token exchange hợp lệ nếu cần.
- Khi response là 401/403, không tự fallback sang **shared admin credential** để “khắc phục”.

## 10. Resource Server xác minh access token như thế nào?

Cách xác minh khác nhau giữa **JWT tự chứa** và **opaque token**, nhưng kết quả cuối phải là **principal và authorization context đáng tin**.

### Quy trình kiểm JWT

~~~mermaid
flowchart TD
    A["API nhận token qua kênh được phép"] --> B{"Đúng token type/syntax/size?"}
    B -->|Không| N["Reject 401 / invalid credential"]
    B -->|Có| C["Issuer trust + allowed signature algorithms"]
    C --> D["Verify signature/JWKS & key validity"]
    D --> E["Check exp, nbf, audience, issuer, token profile"]
    E --> F{"Cryptographic & protocol checks PASS?"}
    F -->|Không| N
    F -->|Có| G["Resolve client/subject from verified claims"]
    G --> H["Check current role/ABAC/SoD/tenant/resource"]
    H --> I{"Action authorized?"}
    I -->|Không| J["DENY 403/404 theo API contract"]
    I -->|Có| K["ALLOW and audit authorized action"]
~~~

**Thứ tự trong sơ đồ mang tính khái niệm**, framework có thể sắp xếp các kiểm tra khác; điều bắt buộc là tất cả ràng buộc liên quan phải đạt **trước side effects**.

1. **Chỉ chấp nhận đúng token type** của endpoint; đừng nhận OIDC ID token thay access token.
2. **Issuer allowlist** theo configuration đáng tin; không tự chấp nhận bất kỳ issuer URL từ token.
3. **Chữ ký và khóa**: xác minh thuật toán đã cho phép, khóa đúng issuer; không tin header JWT tùy tiện quyết định remote key URL hoặc algorithm.
4. **Audience** khớp chính API; kiểm thêm client/authorized party nếu policy quy định.
5. **Time claims** gồm exp, nbf, các điều kiện khác của profile, với clock skew giới hạn.
6. **Claim semantics** theo issuer contract; sub có thể đại diện cho human hoặc app, roles/scopes có profile khác nhau.
7. **Grant/current-state checks** khi cần đáp ứng SLA thu hồi trước khi token hết hạn.
8. **Business authorization** theo subject, action, tenant, resource, workflow state và SoD.
9. **No unauthorized effects** khi từ chối, kể cả async jobs, exports hoặc queued tasks.
10. **Audit lý do** và policy version mà không lưu token thô.

### Với opaque token

RS có thể gọi **introspection endpoint** (nếu được AS cung cấp) để kiểm token active và metadata. RS phải **xác thực kênh introspection**, giới hạn target/issuer và không nhận kết quả từ endpoint tùy ý. **Cache introspection** làm tăng hiệu năng nhưng có thể tạo cửa sổ thu hồi chậm; TTL cache phải được tính vào SLA của các quyền nhạy cảm.

### 401 và 403

Theo API contract, **401 Unauthorized** thường cho token không hợp lệ/thiếu authentication; **403 Forbidden** cho token hợp lệ nhưng không đủ quyền. Một số API có thể dùng 404 để giảm lộ tài nguyên. Không được suy tính **một mã HTTP duy nhất** đã chứng minh policy, đặc biệt khi API 503 hoặc route không tới PEP.

## 11. Refresh token: credential riêng và lifecycle riêng

**Refresh token (RT)** cho phép client đủ điều kiện yêu cầu access token mới mà không cần lặp toàn bộ luồng xác thực. Không phải mọi client đều nhận refresh token; **client credentials** thường xin access token mới qua client authentication mà không cần RT.

### Refresh lifecycle tiêu biểu

~~~mermaid
sequenceDiagram
    participant C as Client đủ điều kiện
    participant AS as Authorization Server
    participant DB as Token / Grant Store
    participant RS as Resource Server
    C->>AS: Authorization flow hợp lệ
    AS->>DB: Lưu grant và refresh-token family metadata
    AS-->>C: Access token AT1 (+ refresh token RT1)
    C->>RS: Request dùng AT1
    RS-->>C: ALLOW/DENY theo token + policy
    C->>AS: Xin AT2 bằng RT1 khi phù hợp
    AS->>DB: Kiểm grant, client, RT validity/reuse
    DB-->>AS: Active / revoked / compromised
    AS-->>C: AT2 (+ RT2 nếu rotation được áp)
~~~

### Biện pháp với refresh token

- **Refresh token là credential nhạy cảm**, không đặt vào URL/log; bảo vệ theo client type.
- **Public clients** cần áp dụng biện pháp phù hợp với Security BCP như **refresh token rotation hoặc sender-constraining**, tùy AS/client contract.
- Với rotation, khi RT1 được dùng và thay bởi RT2, **RT1 không được dùng lại như refresh token hợp lệ** theo thiết kế; reuse có thể kích hoạt cơ chế phát hiện rủi ro và vô hiệu token family/grant.
- **Cần thiết kế race conditions**: hai request refresh đồng thời hoặc network retry không được khiến hệ thống tự động chấp nhận replay hoặc làm hỏng trải nghiệm hợp lệ không kiểm soát.
- Có thể áp **absolute expiry, idle timeout, session reauthentication, device/client binding** theo policy; không giả định RT tồn tại vô hạn.
- **Thu hồi refresh token không tự động vô hiệu access token đã phát** nếu RS vẫn chấp nhận AT cũ.
- Khi Mover/Leaver, phải kiểm cả **khả năng phát token mới** lẫn **quyền từ token cũ**.

### Reuse và token theft

Nếu RT rotation phát hiện sử dụng lại token đã bị thay, AS có thể **revoke refresh token family** và yêu cầu authentication mới; nhưng phát hiện này không tự xác định bên nào là attacker và không bảo đảm các AT hiện có bị RS chặn. Cần telemetry, incident response và kiểm token access đã cấp theo risk.

## 12. Làm mới access token, reauthentication và refresh không đồng nghĩa nhau

Khi access token gần hết hạn, client có thể:

1. **Refresh**, nếu được cấp RT và client có flow hợp lệ.
2. **Yêu cầu access token mới** qua client credentials/workload federation, khi không có RT.
3. **Thực hiện authorization flow mới**, có thể tái dùng SSO session hoặc yêu cầu reauthentication/step-up theo policy.
4. **Từ chối hoặc yêu cầu người dùng xác thực lại** nếu grant hoặc session không còn đủ điều kiện.

| Sự kiện | Điều cần kiểm | Không đồng nghĩa |
| --- | --- | --- |
| Access token expired | API từ chối token quá hạn; client có thể xin mới nếu còn grant. | User đã logout khỏi SSO. |
| Refresh success | AS đã quyết định grant/refresh hợp lệ tại thời điểm refresh. | Mọi action ở API đều ALLOW. |
| Refresh failed | Grant RT bị revoke/expired, client invalid hoặc lỗi AS. | API chắc chắn đã chặn AT cũ. |
| Reauthentication | Người dùng xác minh lại theo chính sách. | Các permissions cũ được cấp lại mà không cần kiểm IAM. |
| Step-up MFA | Nâng assurance cho action nhạy cảm nếu được định nghĩa. | SoD, tenant/resource checks được bỏ qua. |

### Client retry hợp lý

Nếu API trả lỗi invalid/expired token, client **không nên refresh vô hạn**; cần xử lý một lần có kiểm soát, tránh tạo thác request khi AS lỗi và giữ user/session state nhất quán. Khi nhận 403 do thiếu quyền, tự refresh liên tục **không làm entitlement xuất hiện** và gây tải thừa.

## 13. Thu hồi access token: các cơ chế khác nhau

**Revocation** có thể liên quan **một token, một refresh token, một authorization grant, một client credential, hoặc cả subject/client**. Mỗi mô hình có phạm vi khác nhau; cần nói rõ thứ gì thực sự bị vô hiệu ở đâu.

| Biện pháp | Điểm mạnh | Giới hạn/điều cần chứng minh |
| --- | --- | --- |
| **TTL ngắn** | Giới hạn tuổi token không bị kiểm trạng thái. | Không chặn ngay khi Mover/Leaver, rò rỉ hay khóa bị lộ. |
| **OAuth token revocation endpoint** | Client/AS có cơ chế revoke theo hợp đồng, thường liên quan RT/AT. | Khả năng thực tế phụ thuộc token type, AS/RS và propagation. |
| **Token introspection** | RS kiểm trạng thái token gần thời điểm request. | AS availability, network latency, cache stale, kiểm đa RS. |
| **JWT jti denylist** | Có thể chặn token cụ thể trước expiry. | Cần jti, shared/state store, TTL, propagation và vận hành đúng. |
| **Subject/client entitlement version** | Chặn token cũ khi policy version/account state đổi. | RS phải kiểm online/cache hoặc policy information point đáng tin. |
| **Central authorization tại PEP** | Chặn action hiện không còn quyền dù token valid. | Tất cả đường thực thi phải gọi PEP; policy/cache phải đủ mới. |
| **Sender-constrained token** | Hạn chế reuse token bị sao chép nếu attacker thiếu key/cert. | Không tự thu hồi token hay ngăn client/runtime hợp lệ bị chiếm. |
| **AS signing key rotation** | Thay khóa ký phục vụ quản trị key. | Không nên coi đây là cơ chế revoke riêng lẻ; có thể làm ảnh hưởng mọi token dùng khóa cũ. |
| **Gateway deny/containment** | Chặn request trong sự cố với policy tại edge. | Không chặn các đường bypass gateway nếu tồn tại. |

### OAuth revocation endpoint

RFC 7009 định nghĩa cơ chế **token revocation** với semantics và khả năng hỗ trợ riêng. Client có thể gửi token cần revoke tới AS qua endpoint bảo vệ; nhưng **không suy rằng một lần gọi thành công sẽ làm mọi JWT đã phát bị từ chối tức thì ở mọi RS**. Cần hiểu access/refresh token type, token family, RS caching và kiến trúc bên cung cấp.

### So sánh revocation với introspection

- **Revocation**: thay đổi trạng thái một credential/grant tại nơi có thẩm quyền.
- **Introspection**: RS **hỏi trạng thái** token hoặc metadata, không phải lệnh thu hồi.
- **Verification**: kiểm request tại RS sau khi thay đổi; đây mới là bằng chứng enforcement.

**Chỉ có yêu cầu revoke thành công là chưa đủ.** Khi quyết định kết thúc quyền, phải đo **thời điểm required RS thực sự DENY** theo policy và SLA.

## 14. Logout, session termination, SSO và access token

Một hệ thống có thể tồn tại đồng thời:

- **IdP/SSO session** của user.
- **Ứng dụng web session** tại Service Provider/Relying Party.
- **OAuth authorization grant** của client.
- **Refresh token** trong cache/kho lưu được bảo vệ.
- **Access token** đã phát cho một hay nhiều RS.
- **Local API keys/PATs** ngoài luồng OAuth.
- **Workload/service account credentials** khác.

### Logout không đồng nghĩa token revocation

~~~mermaid
flowchart TD
    L["User logout ở web app"] --> S["Ứng dụng xóa local session/cookie"]
    L --> I["Có thể yêu cầu IdP session logout"]
    L --> R["Có thể revoke refresh grant/token theo flow"]
    S --> A["Access token đã phát cho RS"]
    I --> A
    R --> A
    A --> Q{"RS có hỗ trợ thu hồi sớm/current-state?"}
    Q -->|Có| D["Token có thể bị DENY trước exp"]
    Q -->|Không| E["Token có thể còn hợp lệ đến exp"]
~~~

Mũi tên chỉ **những quan hệ cần xem xét**, không khẳng định xóa cookie tác động trực tiếp tới token. OIDC logout có nhiều cơ chế và khả năng hỗ trợ khác nhau; SSO sign-out, RP sign-out và API access token revocation phải được thiết kế riêng.

### IdP disable và SCIM deprovision

- **Disable user ở IdP** thường giúp ngăn authentication/issuance mới tùy policy.
- **SCIM PATCH active=false** hoặc gỡ group thường thay đổi account/group ở ứng dụng đích; **không phải chuẩn revoke JWT/refresh token toàn cục**.
- **Application-local role/session/ACL** có thể tồn tại ngoài những gì SCIM đồng bộ.
- Nếu target tiếp tục cho phép API với AT cũ, cần current-state check/revocation/TTL mitigation tại target.
- Khi Leaver, **không đóng deprovisioning chỉ dựa vào IdP/SCIM acknowledgment**.

## 15. JML tác động thế nào đến access token lifecycle?

| Sự kiện | Yêu cầu về token mới | Yêu cầu về token cũ | Bằng chứng cuối |
| --- | --- | --- | --- |
| **Joiner trước effectiveAt** | Không cấp quyền nghiệp vụ trước khi đủ điều kiện. | Pre-provisioned account không được dùng token để truy cập. | API DENY trước start date và ALLOW đúng scope sau activation. |
| **Joiner activation** | Cấp token theo role/tenant đã duyệt. | Không tự khôi phục grants cũ từ một account trùng email. | Positive/negative probes tại RS. |
| **Mover đổi role** | Token mới không chứa quyền cũ trái policy. | Token cũ mang permission cũ phải được chặn theo SLA. | DENY action cũ, ALLOW action mới, SoD không conflict. |
| **Suspension/security hold** | Ngừng cấp token mới trái hold. | Chặn token/phiên hiện hành theo incident policy. | PEP DENY và audit timing. |
| **Leaver** | Không cấp grant/token mới cho subject đã kết thúc. | Access/refresh tokens, sessions, local PATs được xử lý theo thiết kế. | Verified DENY tại các target bắt buộc. |
| **Rehire** | Xác minh identity link, role và approval mới. | Không tự dùng lại token/quyền lịch sử. | Current entitlement checks và không regrant. |
| **Contract expiry** | Client/user không tiếp tục được cấp quyền sau expiry. | Grants/tokens/keys trong phạm vi hợp đồng được thu hồi. | RS/target deny theo SLA. |

### Mover và rủi ro SoD

Nhân viên chuyển từ **Payment Creator** sang **Payment Approver** có thể giữ token chứa Creator claim phát trước Mover. Nếu hệ thống cấp Approver mới mà chưa chặn Creator cũ, có thể tạo **cửa sổ xung đột SoD**. Một chính sách nghiêm ngặt có thể yêu cầu **revoke-before-grant** hoặc chặn activation quyền mới tới khi RS xác minh hành động cũ không còn được phép.

**Tuy nhiên**, ngay cả khi quyền Creator đã bị gỡ, **transaction-level SoD** vẫn phải từ chối nhân viên duyệt giao dịch mà họ từng tạo. Lịch sử actor/resource không biến mất chỉ vì thay role/token.

### Không dựa vào email để xác định subject

JML cần dùng **stable subject ID**, target account mappings đã xác minh và event revision/effectiveAt. Email đổi hoặc được tái dùng có thể khiến hệ thống revoke nhầm token hoặc cấp lại quyền cũ cho người khác.

## 16. Service identity và client credentials trong token lifecycle

Với **machine-to-machine**, chủ thể hưởng quyền có thể là **service principal** thay vì người dùng. Những rủi ro đáng chú ý:

1. **App registration** tồn tại nhưng không có owner hoặc inventory.
2. Một client secret/certificate được chia sẻ giữa staging và production.
3. **Client Credentials Grant** được phép nhận token cho nhiều tenant hoặc API quá rộng.
4. Workload federation tin wildcard repository/namespace/issuer ngoài phạm vi.
5. Job bị xóa nhưng **client grants, trust mappings, local API keys** vẫn hoạt động.
6. Principal có quyền **assumeRole/impersonate** một service mạnh hơn.
7. Một người có quyền sửa CI/CD pipeline và dùng workload identity để vượt SoD.
8. Credential đã bị rotate nhưng access tokens phát từ nó còn hạn.

### Vòng đời ứng dụng tương ứng JML

| Giai đoạn | Điều phải làm |
| --- | --- |
| **App Joiner/onboarding** | Tạo principal, owner, trust, grants/TTL, positive/negative tests. |
| **App Mover/change** | Đổi repo/cluster/owner/tenant/scope; reapprove và gỡ trust/grants cũ. |
| **App Leaver/decommission** | Ngừng workload, revoke clients/keys/trust/grants và verify API DENY. |
| **Human owner Mover/Leaver** | Chuyển ownership, thu hồi quyền cũ trên vault/repo/CI/CD, đánh giá rotation; không xóa bừa service còn hợp lệ. |

**Client ID không phải bí mật**, và token mang client identity không tự cấp mọi quyền. Resource Server phải kiểm scope/app role **và resource-level policy**.

## 17. Sender-constrained tokens: giảm nguy cơ bearer token bị sao chép

Một bearer access token bị sao chép có thể được sử dụng ở nơi khác nếu các điều kiện RS cho phép. **Sender-constrained** token gắn việc sử dụng token với một bằng chứng người gọi sở hữu khóa/certificate.

| Cơ chế | Ý tưởng | Điểm cần kiểm |
| --- | --- | --- |
| **mTLS-bound access token** | Token liên kết với certificate/key phía client. | RS kiểm certificate trình ở kết nối và binding trong token/introspection theo profile. |
| **DPoP** | Client chứng minh sở hữu private key qua proof cho request. | RS kiểm signature proof, htm/htu, thời gian, jti/replay, key binding và access-token hash theo profile. |
| **Bearer token + TLS** | Bảo mật kênh truyền, nhưng token không tự ràng buộc với sender. | Tránh lộ token ở endpoints, logs, browser và service intermediaries. |

### Hiểu đúng khả năng phòng vệ

- Sender-constrained token **có thể giảm khả năng replay một token bị đánh cắp đơn lẻ** nếu attacker không sở hữu key.
- Không chặn mọi trường hợp **runtime/client đã bị compromise**, nơi attacker có thể khiến client ký proof hoặc sử dụng credential tại chỗ.
- Không thay thế **audience, scope, object authorization, SoD hoặc expiry/revocation**.
- Với proxy/load balancer terminate TLS, phải bảo đảm **binding và trusted forwarding** phù hợp; không tin HTTP header do client tự khai là chứng cứ mTLS.
- DPoP proof có thể yêu cầu **replay protection và nonce** theo deployment; key rotation của DPoP client cũng phải được thiết kế.

Đây là cơ chế bổ trợ cho threat model, không phải khẳng định mọi token trong hệ thống đều sender-constrained.


## 18. Token exchange, OBO và token lifecycle qua nhiều API

Trong hệ thống nhiều tầng, một backend có thể nhận token dành cho **API A** rồi cần gọi **API B**. **Không chuyển tiếp nguyên bearer access token của API A sang B** khi audience không dành cho B, và không dùng app-only credential rộng để vô tình vượt quyền người dùng.

### Hai mô hình rõ ràng

| Mô hình | Chủ thể được ủy quyền | Điều cần giữ đúng |
| --- | --- | --- |
| **Delegated/OBO** | Backend thực hiện thay người dùng theo grant được AS cho phép. | User identity, client identity, audience B, scopes, consent và resource policy tại B. |
| **Application-only** | Backend hành động bằng quyền của chính ứng dụng. | Application principal, tenant/resource access, chức năng nào được phép chạy không cần user. |

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as API A / Backend
    participant AS as Authorization Server
    participant B as API B
    U->>A: Request với token dành cho API A
    A->>A: Xác minh token và quyền user ở tài nguyên A
    A->>AS: Token exchange / OBO cho API B nếu hỗ trợ
    AS->>AS: Validate trust, grant, subject, audience B
    AS-->>A: Token mới dành cho API B
    A->>B: Request dùng token audience B
    B->>B: Verify token + user/client/resource authorization
    B-->>A: ALLOW hoặc DENY
~~~

**Token exchange** (ví dụ RFC 8693 khi có hỗ trợ) có chính sách về nguồn token, loại token mới và subject/actor. Không suy rằng bất kỳ JWT nào cũng có thể đổi lấy quyền lớn hơn ở API khác. AS phải ngăn **privilege amplification** và bảo toàn actor/ủy nhiệm cần thiết.

### Token cache trong microservices

- Cache theo **subject/client, audience, scopes, tenant/context** cần thiết; không dùng token user A cho user B.
- Tôn trọng **exp và refresh restrictions**; không cache vô hạn.
- Không gửi token tới external logs/traces hoặc fan-out cho dịch vụ không thuộc audience.
- Nếu fan-out dùng nhiều APIs, lấy tokens đúng audience và chỉ các permissions từng API cần.
- Nếu quyền user thay đổi, cache không được làm sống lại quyền cũ ngoài SLA mà RS/policy hỗ trợ.

## 19. Signing key rotation, JWKS và sự cố khóa ký

Một JWT access token thường được ký bằng khóa mà RS có thể kiểm chứng qua **bộ khóa tin cậy/JWKS** của issuer. Vòng đời khóa ký **khác vòng đời token hoặc grant**.

### Rotation thông thường

~~~mermaid
flowchart TD
    A["Issuer chuẩn bị signing key mới"] --> B["Phân phối public key/JWKS theo chính sách"]
    B --> C["RS làm mới trusted key set"]
    C --> D["Issuer bắt đầu ký token bằng key mới"]
    D --> E["RS xác minh token cũ và mới theo overlap policy"]
    E --> F["Chờ token cũ hết hạn hoặc hoàn tất migration"]
    F --> G["Gỡ key cũ khi an toàn và được phê duyệt"]
    G --> H["Audit key/version và kiểm không có unexpected acceptance"]
~~~

| Sự kiện | Rủi ro | Biện pháp |
| --- | --- | --- |
| RS chưa biết public key mới. | Token mới hợp lệ bị từ chối, lỗi hàng loạt. | JWKS refresh/caching và controlled rollout. |
| Gỡ key cũ quá sớm. | Token cũ còn hạn bị từ chối ngoài ý muốn. | Overlap theo issuance/expiry và risk policy. |
| Giữ key cũ quá lâu sau compromise. | Attacker có thể tạo token được kiểm hợp lệ nếu private key lộ. | Incident containment, emergency key revocation, revoke/deny tokens chịu ảnh hưởng. |
| RS chấp nhận algorithm tùy client khai. | Token giả mạo/algorithm confusion. | Allowlist algorithms và trusted key selection. |
| Lấy JWKS URL tùy theo token header. | SSRF/remote-key substitution. | Issuer metadata từ trust config, không dereference URL không tin cậy. |
| Key ID trùng giữa issuers. | Chọn nhầm key hoặc trust domain. | Phân biệt theo issuer + key ID và cấu hình validation. |

### Không dùng key rotation như revocation cá thể

**Đổi signing key** có thể ảnh hưởng đồng loạt token ký bằng key cũ. Nếu chỉ một user Leaver, đây thường **không phải phương pháp phù hợp** để revoke token của người đó. Dùng current-state/denylist/introspection theo kiến trúc. Khi **private signing key bị compromise**, kế hoạch khẩn khác hẳn rotation thường kỳ và có thể cần chặn token diện rộng.

## 20. Multi-tenant, scope, RBAC/ABAC và nguyên tắc quyền hiệu lực

Một access token có thể chứng minh client được cấp **invoice.read**, nhưng **đọc hóa đơn nào** vẫn phụ thuộc tenant, ownership, status, classification, business purpose, scope ở endpoint và chính sách SoD.

### Ví dụ quyết định

~~~text
Authentication:
  token signature / introspection = valid
  issuer = trusted
  audience = finance-api
  exp/nbf = valid

Authorization:
  action = invoice.read
  required app scope = invoice.read
  subject active = true
  token tenant context = tenant-vn (nếu token có và được tin cậy)
  requested invoice tenant = tenant-vn
  invoice classification allowed = true
  current policy/entitlement permits = true
  no applicable deny rule = true

Result: ALLOW only when ALL mandatory checks pass.
~~~

### Quy tắc đa tenant

- **Tenant từ path/header** do client chọn không đủ chứng minh quyền: backend phải kiểm tenant của object/resource và principal/grant.
- Một access token có thể dành cho nhiều audiences/tenants theo thiết kế, nhưng điều đó **làm tăng độ phức tạp và blast radius**; ưu tiên audience/scope hẹp theo risk.
- **Role hierarchy**, nested groups và app-local direct ACL có thể làm permissions khác với claim trong token.
- Với **ABAC động** như job status, legal hold, approval limit, manager hoặc device posture, chỉ dựa vào claim cũ có thể đưa ra quyết định sai.
- **SoD transaction-level** phải kiểm người tạo và người duyệt cùng nghiệp vụ, kể cả sau khi token được refresh.
- Scope ghi trong token có thể là **điều kiện cần**, nhưng không phải lúc nào là **điều kiện đủ** cho action.

### Positive control lẫn negative probe

Một test chính xác phải xác nhận **user được phép đọc invoice A vẫn ALLOW**, trong khi **invoice B ngoài tenant bị DENY**. Nếu API đang down và cả hai đều lỗi 503, không được kết luận authorization thành công.

## 21. Mô hình xử lý quyền hiện hành ở Resource Server

Tổ chức có thể cần chọn cách cân bằng **latency, availability và revocation SLA**:

| Thiết kế | Cách vận hành | Bất lợi |
| --- | --- | --- |
| **Offline JWT + claim-only RBAC** | RS kiểm token cục bộ, role lấy từ claims. | Entitlement/JML có thể stale đến exp. |
| **JWT + current-state PDP/PIP** | Token xác thực principal; RS hỏi policy/current rights theo request. | Phụ thuộc availability/caching của policy data. |
| **Opaque + introspection mỗi request** | RS hỏi AS trạng thái token. | Latency, tải AS, network failure. |
| **Opaque + cached introspection** | Giảm tải bằng cache TTL. | Cửa sổ stale lớn hơn khi token bị revoke. |
| **JWT + denylist/epoch** | Chặn token/subject trước expiry nếu RS có state tin cậy. | Distribution, cache invalidation, correctness phức tạp. |
| **Gateway-centric enforcement** | Gateway kiểm token/permission trước khi vào app. | Những đường bypass gateway hoặc domain actions bên trong app phải được bảo vệ riêng. |
| **Hybrid** | JWT validity local, privileged actions online check, low-risk actions TTL ngắn. | Nhiều chính sách; cần công bố rõ scope và coverage. |

### Khi PDP/PIP/AS không truy cập được

Với action nhạy cảm, **không chuyển sang ALLOW mặc định khi không kiểm được điều kiện bắt buộc**. Quyết định có thể là **DENY/INDETERMINATE và fail-safe**; phân biệt lỗi hạ tầng với access denied trong API contract và monitoring. Nếu policy chấp nhận **bounded stale cache** cho nghiệp vụ cụ thể, phải xác định thời hạn, dữ liệu được cache, risk acceptance và kiểm SLA, không tạo fallback ngầm.

### Cache invalidation và correctness

Nếu quyền được revoke lúc 09:00 nhưng RS cache subject entitlement đến 09:10, token dù valid/invalid theo thời gian không phải nguyên nhân duy nhất của residual access. **SLA thu hồi phải tính cả propagation, token TTL, cache TTL và coverage của PEP**.

## 22. Rủi ro token bị đánh cắp và ứng cứu sự cố

Một access token hợp lệ có thể bị lộ qua browser XSS, CI logs, proxy traces, memory dump, compromised workload, URL hoặc clipboard. Phản ứng phải xét **loại token, audience, TTL, client binding và các RS có thể chấp nhận nó**.

### Playbook khung

1. **Xác định phạm vi**: token/credential type, issuer, subject/client, audiences, scopes, tenants, time window và resource sensitivity.
2. **Containment**: revoke token/grant/refresh family nếu hỗ trợ, chặn access tại RS, vô hiệu credential lộ, giới hạn network theo incident policy.
3. **Đánh giá token đang lưu hành**: có JWT offline, opaque introspection, caching, sender-constraint hay không.
4. **Ngăn cấp mới trái phép**: thay/revoke client secret, refresh grant, user session hoặc trust binding đúng đối tượng.
5. **Truy tìm sử dụng bất thường** qua token issuance IDs, API actions, source/holder evidence mà không đổ token vào log.
6. **Review quyền và SoD**: đã có grant mới, impersonation, export, rule modifications hoặc persistence khác không?
7. **Khôi phục**: credential và token mới đúng scope, owner approval, positive/negative tests.
8. **Xác minh chặn token cũ** tại các RS bắt buộc theo SLA.
9. **Post-incident**: giảm TTL, sender constraints, logging hygiene và client hardening nếu phù hợp.

**Không giả định rotation client secret lập tức giết mọi access token đã phát**, hay invalidate JWKS key cá thể khi chỉ lộ một bearer token. Chọn biện pháp theo threat model, phạm vi lộ và khả năng thực tế của AS/RS.

## 23. Audit access token mà không rò rỉ credential

Các mốc cần ghi ở control plane và data plane:

| Event | Metadata gợi ý | Tuyệt đối tránh |
| --- | --- | --- |
| TOKEN_ISSUED | Issuer, token reference/jti nếu có, client, subject ref, audience, scopes, expiry, decision time. | Raw bearer token/refresh token. |
| TOKEN_REFRESHED | Client, grant family ref, rotation status, policy version, outcome. | Refresh token value. |
| TOKEN_REVOKE_REQUESTED | Requestor/authority, target grant/token reference, reason. | Credential gửi kèm API request. |
| TOKEN_REVOKE_APPLIED | AS/store state, revision, appliedAt. | Tuyên bố mọi RS đã DENY nếu chưa probe. |
| API_TOKEN_REJECTED | RS, reason code, issuer/client ref (khi an toàn), timestamp. | Full Authorization header. |
| API_ACTION_DENIED | Principal, action, tenant/resource ref, policy version, no side effect. | PII đầy đủ hoặc token. |
| API_ACTION_ALLOWED | Principal, resource class, correlation, decision/action outcome. | Data payload nhạy cảm không cần. |
| TOKEN_ACCESS_VERIFIED_DENIED | Required RS, tested action, probe evidence, verifiedAt. | Nhầm 503/outage với valid DENY. |
| KEY_ROTATED | Key ID, issuer, validity windows, rollout state. | Private signing key. |
| JML_EFFECTIVE | Stable subject, lifecycle revision/effectiveAt, revoked permission set. | Hồ sơ nhân sự vượt mục đích kiểm toán. |

### Ví dụ sự kiện audit

~~~yaml
eventType: API_AUTHORIZATION_DECISION
correlationRef: req-20261123-042
resourceServerRef: finance-api
tokenRef: jti-demo-001
issuerRef: corporate-idp
clientRef: finance-web-client
subjectRef: person-4821
action: payment.approve
resourceRef: payment-2026-880
tenantRef: tenant-vn
policyVersion: finance-authz-v6
decision: DENY
reasonCode: SOD_SELF_APPROVAL
observedAt: "2026-11-23T03:00:01Z"
sideEffectsCommitted: false
tokenValueLogged: false
~~~

**YAML chỉ là schema minh họa**. Token ID/subject references vẫn có thể liên quan dữ liệu cá nhân và cần access control, retention, encryption theo chính sách. Nếu không có jti, dùng **protected reference/correlation** phù hợp, không bịa ID token.

## 24. Các chỉ số cần đo về access token lifecycle

| Chỉ số | Mục đích | Cạm bẫy |
| --- | --- | --- |
| **Issued tokens by client/flow** | Thấy tăng đột biến hoặc grants hiếm gặp. | Nhiều issuance không mặc nhiên là abuse. |
| **Access token TTL distribution** | Kiểm mức rủi ro của token được phát. | TTL cấu hình khác TTL thực tế nếu có nhiều AS/flows. |
| **Refresh reuse detections** | Phát hiện RT rotation anomalies. | Có thể do race/bug, cần điều tra. |
| **Invalid issuer/audience rejects** | Tìm token confusion và cấu hình sai. | Nhiều reject có thể do rollout sai. |
| **Key/JWKS validation failures** | Đánh giá key rotation propagation. | Không tự tắt validation để giảm lỗi. |
| **Token revocation propagation** | Đo từ revoke effectiveAt tới RS DENY. | Không chỉ đo AS revoke API latency. |
| **JML residual access** | Quyền còn được sử dụng sau Mover/Leaver. | Phải xét target PEP, session và policy cache. |
| **Unverified RS/endpoint coverage** | Biết nơi chưa kiểm được sự chặn token. | Không quan sát thấy lỗi không có nghĩa an toàn. |
| **401/403 by reason** | Phân biệt expiry, invalid token, insufficient scope, ABAC deny. | Status code đơn lẻ không phải policy outcome. |
| **False denial/business impact** | Token/grant hợp lệ bị từ chối sai do policy/key drift. | Bảo mật không đạt nếu chặn toàn bộ nghiệp vụ. |
| **Refresh token lifetime/rotation coverage** | Giảm RT tồn tại lâu và misuse. | Token family revoke khác với access-token invalidate. |
| **Sender-constrained token adoption** | Kiểm controls chống replay theo risk tier. | Tỉ lệ cao không chứng minh RS đã validate proof đúng. |

### Một công thức quan trọng

\[
\text{RevocationLatency} =
t_{\text{verified DENY at last required RS}}
-
t_{\text{revoke effectiveAt}}
\]

Nếu còn một RS chưa kiểm, **không được báo hoàn tất cho toàn scope**. Cần tách **verified subset, outstanding/unverified targets và deadline/SLA**.

## 25. Bộ policy YAML minh họa cho token lifecycle

~~~yaml
policyId: finance-token-lifecycle
version: 6
issuerRef: corporate-authorization-server
resourceServer: finance-api
acceptedAudiences: [finance-api]
acceptedTokenTypes: [oauth-access-token]
authentication:
  acceptedMechanisms: [validated-jwt, trusted-introspection]
  allowedAlgorithmsManagedByIssuerPolicy: true
  rejectUnknownIssuer: true
  rejectExpiredOrNotYetValid: true
authorization:
  requireCurrentSubjectStatusForCriticalActions: true
  requireTenantResourceCheck: true
  requireSoDForPaymentApproval: true
  denyWhenCriticalAttributesUnknown: true
delegated:
  requireUserAndClientContext: true
applicationOnly:
  requireApprovedServicePrincipal: true
  forbidUsingIdTokenAsAccessToken: true
revocation:
  targetSlaByRisk:
    critical: configured-by-risk-owner
    standard: configured-by-risk-owner
  recordVerifiedTargetEvidence: true
audit:
  logRawTokens: false
  logGrantAndPolicyVersion: true
  recordClientSubjectAndTargetRefs: true
~~~

Đây là **pseudo-policy**, không phải cấu hình YAML có thể copy vào Spring Security, Keycloak, Microsoft Entra, Okta hoặc một IdP cụ thể. Giá trị TTL/SLA phải được tổ chức và platform xác nhận, tránh bịa “chuẩn bắt buộc”. Các rule cần có **business/data owner, IAM owner và tests**; khi thay đổi scope/role/issuer cần version và phê duyệt tương ứng.


## 26. Java pseudocode: tách token validation và business authorization

**Không tự viết parser JWT để sản xuất.** Dùng Resource Server framework đã hỗ trợ issuer discovery/JWKS hoặc token introspection theo contract, với trusted configuration, algorithms, expiration và audience validators. Ứng dụng chỉ nên nhận một đối tượng **đã được xác minh bởi tầng authentication**.

### Ví dụ kiểm quyền thanh toán

~~~java
import java.time.Instant;
import java.util.Set;

// Chỉ tạo từ middleware/token verifier đáng tin.
// KHÔNG tạo từ claims chưa xác minh hoặc HTTP headers tùy ý.
record VerifiedAccessToken(
    String issuer,
    String audience,
    String subjectId,
    String clientId,
    Set<String> scopes,
    Instant expiresAt,
    boolean delegatedUser,
    boolean verified
) {}

record Payment(
    String id,
    String tenantId,
    String createdBySubjectId,
    String lastMaterialEditorSubjectId,
    String state
) {}

record CurrentSubjectAccess(
    String subjectId,
    String tenantId,
    boolean active,
    boolean canApprovePayment,
    boolean securityHold
) {}

final class PaymentAuthorization {
    boolean canApprove(
            VerifiedAccessToken token,
            Payment payment,
            CurrentSubjectAccess current,
            Instant now) {

        if (token == null || payment == null || current == null) {
            return false;
        }

        if (!token.verified()
                || !token.delegatedUser()
                || !"finance-api".equals(token.audience())
                || token.expiresAt() == null
                || !now.isBefore(token.expiresAt())) {
            return false;
        }

        if (token.scopes() == null
                || !token.scopes().contains("payment.approve")) {
            return false;
        }

        if (!current.active() || current.securityHold()
                || !current.canApprovePayment()
                || !token.subjectId().equals(current.subjectId())
                || !current.tenantId().equals(payment.tenantId())) {
            return false;
        }

        // Transaction-level SoD: role mới không cho tự duyệt
        // payment đã tạo hoặc từng chỉnh sửa trọng yếu.
        if (token.subjectId().equals(payment.createdBySubjectId())
                || token.subjectId().equals(
                    payment.lastMaterialEditorSubjectId())) {
            return false;
        }

        return "PENDING_APPROVAL".equals(payment.state());
    }
}
~~~

### Ranh giới quan trọng của ví dụ

- Tầng **JWT/opaque verifier** phải kiểm **issuer, signature/introspection, audience, algorithm, nbf/exp, token type** trước khi tạo VerifiedAccessToken. Trường verified chỉ là **ký hiệu của kết quả framework**, không phải field từ request.
- **CurrentSubjectAccess** phải đến từ **PDP/PIP/IGA hoặc nguồn quyền hiện hành đáng tin**, có cơ chế consistency/TTL theo SLA; không lấy từ JSON body.
- Quy tắc SoD phải dùng **actor history và payment state của backend**, không dùng client-supplied createdBy.
- Đối với payment nhạy cảm, cần kiểm trong **transaction/optimistic locking** hoặc cơ chế nhất quán phù hợp để tránh TOCTOU.
- **App-only** có thể đi qua policy khác; code cố ý chỉ cho delegated user và **không kết luận app-only token không bao giờ hợp lệ cho các nghiệp vụ khác**.
- Chưa mô tả **approval limit, step-up freshness, transaction state history, risk-based exception và audit**; hệ thống thực phải mở rộng theo policy.
- Token có thể chứa scope nhưng entitlement đã bị gỡ sau issuance; hàm **kiểm current.canApprovePayment()** nhằm minh họa cách chặn quyền cũ trước exp.

### Test oracle tối thiểu

~~~java
// Pseudocode minh họa test, không phải class JUnit có thể chạy ngay.
assertTrue(canApprove(
    tokenOf("person-a", "payment.approve"),
    paymentCreatedBy("person-b"),
    currentEntitlementOf("person-a", "APPROVER_ACTIVE")));

assertFalse(canApprove(
    tokenOf("person-a", "payment.approve"),
    paymentCreatedBy("person-a"),
    currentEntitlementOf("person-a", "APPROVER_ACTIVE")));

assertFalse(canApprove(
    tokenOf("person-a", "payment.approve"),
    paymentCreatedBy("person-b"),
    currentEntitlementOf("person-a", "MOVED_WITHOUT_APPROVER")));
~~~

Bộ test production phải có cả **HTTP/API integration** và **no-side-effect checks**. Một hàm policy đúng không đảm bảo background consumer, bulk endpoint hoặc legacy API cũng đã gọi nó.

## 27. Java pseudocode: xử lý sự kiện revoke quyền theo JML

Một sự kiện HRIS/IGA chỉ có ý nghĩa khi nó được **dịch thành thay đổi quyền và enforcement** tại những hệ thống bắt buộc.

~~~java
record LifecycleEvent(
    String subjectId,
    String lifecycleState,
    String eventRevision,
    Instant effectiveAt
) {}

record RevocationEvidence(
    String resourceServer,
    String action,
    String status,
    Instant verifiedAt,
    String evidenceRef
) {}

final class LifecycleTokenRemediator {
    void onLifecycleChange(LifecycleEvent event) {
        // Kiểm chữ ký/provenance sự kiện ở integration boundary.
        // Không tin event thiếu stable subjectId/revision/effectiveAt.
        if (!eventStore.isNewerThanCommittedState(event)) {
            return;  // Ngăn event đến trễ tái cấp quyền.
        }

        CurrentPolicyState desired =
            identityPolicy.computeCurrentState(event.subjectId());

        // Nếu CRITICAL: kích hoạt containment tại PEP/gateway
        // trước khi các connector bất đồng bộ hoàn thành.
        riskController.applyRequiredImmediateBlocks(desired);

        entitlementController.applyDesiredRightsIdempotently(
            event.subjectId(), desired, event.eventRevision());

        tokenAuthority.revokeApplicableRefreshGrants(
            event.subjectId(), desired);

        // Nếu thiết kế có denylist/epoch/introspection:
        tokenStatePublisher.publishRevocationState(
            event.subjectId(), desired.policyVersion());

        for (RequiredTarget target : coverageCatalog.targetsFor(desired)) {
            RevocationEvidence proof =
                verifier.readbackAndProbeTarget(target, desired);

            if (!"VERIFIED_DENY".equals(proof.status())) {
                remediationQueue.openOrUpdateIncident(
                    event.subjectId(), target, proof.status());
            }
        }

        audit.recordEventAndCoverage(event, desired);
    }
}
~~~

### Không phải “revoke tất cả token” trên một lệnh giả định

Các phương thức chỉ mô tả **ý định kiến trúc**. Một AS có thể có API khác nhau để revoke refresh grants, disable account, introspect access tokens hoặc publish policy epoch. Cần xây **adapter theo provider capabilities**; không giả định OAuth revocation endpoint hỗ trợ mọi trường hợp.

### Ba mốc cần đo

~~~text
effectiveAt    : Khi quyền cần ngừng hiệu lực theo policy/JML.
appliedAt      : Khi AS/IGA/connector ghi nhận thay đổi.
verifiedAt     : Khi từng RS/PEP thực sự từ chối action bị thu hồi.
~~~

Nếu **một RS critical còn ALLOW**, trạng thái không thể là VERIFIED cho toàn bộ revoke scope, dù các connector khác đã trả success.

## 28. Quy trình kiểm chứng thu hồi token theo tình huống thực

### Luồng điển hình

~~~mermaid
sequenceDiagram
    participant HR as HRIS / Lifecycle Source
    participant IGA as IGA / Entitlements
    participant AS as Authorization Server
    participant RS as Resource Servers
    participant AUD as Evidence
    HR->>IGA: Mover/Leaver effectiveAt + revision
    IGA->>IGA: Recompute desired rights + SoD gates
    IGA->>AS: Disable issuance / revoke RT-grant as applicable
    IGA->>RS: Publish current-state deny / revoke event where supported
    IGA->>RS: Reconcile resource/app roles
    RS-->>IGA: Config/readback acknowledgement
    IGA->>RS: Authorized negative probe with prior principal/token
    RS-->>IGA: Policy DENY / stale ALLOW / outage / unknown
    IGA->>AUD: Target-by-target evidence & timestamps
~~~

### Bảng hành động theo kết quả

| Quan sát | Ý nghĩa | Xử lý |
| --- | --- | --- |
| Token cũ trả **401 invalid/expired** từ RS đang hoạt động. | Một đường token bị từ chối theo contract. | Ghi evidence; xét còn đường khác không. |
| Token cũ hợp lệ nhưng action trả **403 policy DENY**. | RS chặn hành động theo current policy. | Kiểm no side effects, tenant/scope, coverage. |
| Token cũ còn **ALLOW** action đã thu hồi. | Quyền tồn dư thực tế. | Contain, sửa role/cache/PEP, mở remediation/incident. |
| Probe trả **503/timeout**. | Không xác minh được authorization; target không sẵn sàng. | UNVERIFIED, retry khi target hoạt động, không tính PASS. |
| SCIM gỡ role nhưng direct ACL còn. | Target có nguồn grant khác. | Thu hồi đúng nguồn, chạy probe lại. |
| Refresh token bị revoke nhưng AT cũ còn ALLOW. | New issuance bị giới hạn; old-token window chưa đóng. | Kiểm RS denylist/introspection/TTL và SLA. |
| Không có cách thử token đã phát vì không lưu token thô. | Thiếu trực tiếp một loại test. | Dùng test principal/controlled token issuance, policy state evidence, không thu thập token production tùy tiện. |

### Không dùng token thật của người dùng làm fixture

Negative probes phải dùng **principal/tài nguyên thử được cấp phép**, có kiểm soát dữ liệu và không ảnh hưởng tài chính/khách hàng. Nếu cần đánh giá quyền của production account, chọn cách **read-only safe probing** hoặc evidence bổ sung được phê duyệt; không sao chép session/bearer token của nhân viên ra ngoài hệ thống.

## 29. Case study: Mover đổi từ Creator sang Approver

### Bối cảnh

Nhân viên **Mai** có quyền **Payment Creator** ở Finance Portal đến 09:00. Trước Mover, token **AT-OLD** được cấp lúc 08:55, exp 09:25, scope bao gồm payment.create. Tại 09:00, HRIS đổi vai trò và IGA chuyển Mai sang Payment Approver. Chính sách SoD yêu cầu **không có overlap Creator + Approver trong cùng tenant** và **không self-approve payment từng tạo**.

### Timeline và hệ quả

| Mốc | Sự kiện | Rủi ro / kiểm soát |
| --- | --- | --- |
| **08:55** | AT-OLD được cấp với Creator scope. | Token sẽ còn thời hạn sau Mover nếu không chặn sớm. |
| **09:00** | HRIS Mover effectiveAt. | Desired state yêu cầu Creator DENY. |
| **09:01** | IGA gỡ group Creator và cập nhật role. | Không chứng minh RS đã bỏ quyền cũ. |
| **09:02** | AS không còn cấp Creator token mới. | AT-OLD vẫn có thể được RS chấp nhận. |
| **09:03** | Gateway/RS áp current-state/epoch/revocation policy. | Mục tiêu chặn payment.create trước exp. |
| **09:04** | Token cũ payment.create được thử hợp lệ trong phạm vi test. | Phải DENY và không tạo payment mới. |
| **09:05** | Approver được activate sau các SoD gates. | Có thể ALLOW duyệt payment của người khác. |
| **09:06** | Mai cố duyệt payment đã tạo trước Mover. | DENY bằng transaction-level SoD. |
| **09:25** | AT-OLD hết hạn tự nhiên. | Không thay thế nhu cầu đã chặn ở 09:03. |

Đây là **kịch bản minh họa**, không phải SLA bắt buộc; nếu công nghệ không hỗ trợ chặn trước exp, policy phải giải quyết bằng TTL, activation sequencing, PEP checks hoặc risk acceptance đúng thẩm quyền.

### Những phép thử quan trọng

1. **payment.create bằng AT-OLD**: DENY sau mốc bắt buộc và không ghi dữ liệu.
2. **payment.approve bằng AT-NEW** trên payment của người khác: ALLOW nếu đủ điều kiện.
3. **payment.approve bằng AT-NEW** trên payment do Mai từng tạo: DENY dù Mai không còn Creator role.
4. **Cross-tenant**: Mai không được dùng token role VN cho tenant SG.
5. **Access request concurrency**: Mover event cũ đến trễ không tái cấp Creator.
6. **Token refresh**: Mai không thể lấy Creator token mới bằng RT/grant đã thay đổi.
7. **Positive control**: endpoint Finance API hoạt động bình thường, denial không phải do outage.
8. **Audit**: giữ event revision, policy version, deny evidence và thời điểm verifiedAt.

### Quyết định cuối

Trạng thái Mover **không hoàn tất ở góc độ authorization** nếu một RS/bulk endpoint vẫn thực thi payment.create bằng token/phiên cũ. Cần đánh dấu REMEDIATION và theo dõi cửa sổ quyền tồn dư.

## 30. Case study: Leaver, SSO session, refresh token và ứng dụng SaaS

### Bối cảnh

Nhân viên **An** sử dụng ứng dụng web qua SSO, đồng thời có Finance API delegated tokens và một **SaaS personal access token (PAT)** được tạo riêng. HRIS ghi Leaver effectiveAt **17:00**.

### Bảng kiểm theo từng loại credential

| Đường truy cập | Việc cần làm | Điểm dễ bị bỏ sót |
| --- | --- | --- |
| IdP user | Disable/authentication policy khi Leaver có hiệu lực. | SSO session và offline AT đã phát có thể vẫn tồn tại. |
| Web app session | Terminate theo app/SSO logout integration và policy. | Cookie/SP session khác với AS session. |
| Refresh grant | Revoke/disable để chặn issuance mới. | Không tự kill access JWT cũ. |
| Finance API AT | RS deny theo current state hoặc cơ chế đã thiết kế. | Token còn exp và role claim cũ. |
| SaaS SCIM account | Disable/gỡ groups và readback. | Direct local roles/ACL không nhất thiết theo SCIM. |
| SaaS PAT | Thu hồi riêng ở SaaS target. | PAT có thể không dùng OAuth AS. |
| Workload secrets từng được An quản lý | Chuyển owner/revoke quyền cá nhân, đánh giá key rotation. | Không xóa nhầm service đang hoạt động hợp lệ. |

### Timeline mẫu

~~~text
17:00  Leaver effectiveAt (HRIS).
17:01  IdP account disabled, new issuance blocked as policy.
17:02  Refresh token grants revoked.
17:04  Finance API checks current state; old AT denied.
17:06  SaaS SCIM account disabled; target readback.
17:10  Existing SaaS PAT still calls reports.export successfully.
17:14  PAT revoked separately; target probe DENY.
17:16  All required targets verified, evidence signed off.
~~~

Nếu policy SLA là 10 phút, **17:16 là hoàn tất muộn**, không được ghi “deprovision completed 17:01”. Nếu PAT chưa kiểm được, kết luận phải **UNVERIFIED/PARTIAL**, không áp nhãn an toàn.

## 31. Case study: service principal lộ credential trong CI log

Một batch job sử dụng client credentials để xin token cho **invoice.summary.read**. Secret của service principal bị in ra CI log lúc 10:30. Đội vận hành rotate client secret lúc 10:35, nhưng một access token lấy lúc 10:29 có exp 11:00.

### Những điều phải xử lý

- **Thu hồi credential cũ** để ngăn token issuance mới từ secret lộ.
- **Xác định app grants/scopes/audiences** có thể bị lạm dụng; chặn theo incident policy.
- Với RS chấp nhận JWT offline, đánh giá **token đã phát trước rotation** và cách chặn sớm hoặc TTL tối đa còn lại.
- Kiểm tài khoản workload/runner có bị chiếm và các credential khác có thể đã lộ không.
- Xem log API vì **invoice.summary.read** có thể được gọi rất nhiều lần và rò dữ liệu dù chỉ có một scope.
- Giữ application owner, incident owner và bằng chứng; không đưa secret gốc vào ticket.
- Nếu thay credential làm job không chạy, khôi phục bằng **credential mới hẹp và bảo vệ tốt**, không fallback admin account dùng chung.

**Đổi secret không đồng nghĩa xoay signing key AS và không tự revoke mọi JWT**. Ba đối tượng **client secret, AS signing key, access token** có vòng đời khác nhau.


## 32. Ma trận kiểm thử access token lifecycle

Các test nên dùng **test users, service principals và tài nguyên giả** được cấp phép, không lấy token/refresh token thật của nhân viên làm fixture. Mỗi negative test cần **positive control** để tránh coi outage là enforcement.

| ID | Trường hợp | Kết quả kỳ vọng |
| --- | --- | --- |
| AT01 | Client hợp lệ xin token với grant/scope được duyệt. | AS cấp token đúng audience/TTL; API ALLOW action đúng. |
| AT02 | Client ID công khai nhưng không có client authentication/trust hợp lệ. | AS không cấp token cho confidential client. |
| AT03 | Authorization code bị dùng với PKCE verifier sai. | AS từ chối token exchange. |
| AT04 | Redirect URI không hợp lệ trong luồng authorization code. | Không hoàn tất cấp token theo redirect không đăng ký. |
| AT05 | Client xin scope ngoài approved grant. | AS từ chối hoặc giới hạn theo policy, không mặc nhiên cấp. |
| AT06 | JWT bị sửa payload mà không ký lại. | RS từ chối signature/integrity. |
| AT07 | JWT dùng issuer không nằm trong trust config. | RS từ chối. |
| AT08 | JWT header gợi ý algorithm none/trái allowlist. | RS từ chối. |
| AT09 | JWT có kid/JWKS URL do attacker điều khiển. | Verifier không chọn remote key không tin cậy. |
| AT10 | Token có audience của CRM gửi tới Finance API. | RS từ chối sai audience. |
| AT11 | Token hết exp. | RS từ chối theo expiry policy. |
| AT12 | Token có nbf ở tương lai vượt clock skew cho phép. | RS từ chối. |
| AT13 | Token là OIDC ID token nhưng client gửi tới protected API. | RS từ chối sai token type/purpose. |
| AT14 | Opaque token không tồn tại hoặc introspection active=false. | RS từ chối. |
| AT15 | Introspection AS timeout cho action Critical. | Không ALLOW mặc định; trạng thái lỗi được phân loại. |
| AT16 | RS dùng stale introspection cache sau revoke. | Residual window được phát hiện, SLA không bị khai thấp. |
| AT17 | Access token có scope read, gọi endpoint export. | DENY trước side effect. |
| AT18 | Access token có đúng scope nhưng user truy cập tài nguyên tenant khác. | DENY object/tenant authorization. |
| AT19 | Role Approver có claim đúng, nhưng HRIS Mover đã gỡ effective entitlement. | RS current-state check DENY theo SLA. |
| AT20 | User Mover có token cũ Creator và role mới Approver. | SSD/activation/transaction SoD ngăn overlap trái policy. |
| AT21 | User sau Mover cố duyệt giao dịch do mình từng tạo. | DENY transaction-level SoD. |
| AT22 | Leaver có access token còn hạn. | RS deny theo cơ chế và SLA đã thiết kế; không dựa chỉ vào exp. |
| AT23 | IdP user disabled nhưng SP local session vẫn gọi API. | Phát hiện đường còn quyền; chưa VERIFIED. |
| AT24 | SCIM active=false nhưng local ACL/role vẫn cho ALLOW. | Ghi residual access, remediation. |
| AT25 | SSO logout nhưng JWT cũ còn ALLOW trong RS offline. | Chỉ báo chênh lệch rõ, không báo logout=global revoke. |
| AT26 | RT revoked, client thử refresh lấy AT mới. | AS từ chối grant mới theo policy. |
| AT27 | RT revoked nhưng AT đã phát còn hạn. | RS behavior được kiểm riêng; không suy AT tự chết. |
| AT28 | Refresh token rotation: RT1 được dùng lại sau RT2. | Reuse detection/response theo AS security policy. |
| AT29 | Hai refresh requests chạy đồng thời. | Race handled theo contract; không âm thầm cho replay không kiểm soát. |
| AT30 | Client không có refresh grant, thử refresh token endpoint. | AS từ chối. |
| AT31 | Client credentials app-only không có user context nhưng endpoint yêu cầu delegated user. | DENY. |
| AT32 | App-only token có quyền reports.read, cố dùng dữ liệu user ngoài quyền của caller. | Backend chặn confused deputy nếu request do user kích hoạt. |
| AT33 | API A token chuyển nguyên sang API B. | API B từ chối sai audience; dùng exchange hợp lệ nếu cần. |
| AT34 | OBO request cố xin scope rộng hơn user/client đã được duyệt. | AS không tăng quyền trái policy. |
| AT35 | Client staging có token/trust xin production API. | DENY env/tenant/trust mismatch. |
| AT36 | DPoP-bound token gửi thiếu DPoP proof. | RS từ chối nếu binding được yêu cầu. |
| AT37 | DPoP proof sai method/URI hoặc replay trùng jti. | RS từ chối theo profile/replay policy. |
| AT38 | mTLS-bound token dùng với certificate khác. | RS từ chối binding mismatch. |
| AT39 | RS nhận bearer token từ proxy mà chỉ tin header mTLS do client tự khai. | Test phát hiện bypass, không công nhận sender constraint. |
| AT40 | AS ký token mới với key mới, RS chưa refresh JWKS. | Detect false deny/propagation; không tắt verify. |
| AT41 | Public key cũ được gỡ trước khi tokens ký bằng key cũ hết hạn. | Deployment test phát hiện gián đoạn và sửa rollout policy. |
| AT42 | Private signing key bị lộ. | Kế hoạch emergency key/token containment, kiểm RS reject token bị ảnh hưởng. |
| AT43 | Một token bị denylist nhưng RS node thứ hai chưa nhận event. | Chưa VERIFIED toàn scope, cảnh báo propagation. |
| AT44 | Token có scope hợp lệ nhưng DB/object state không cho phép action. | ABAC/domain policy DENY. |
| AT45 | API trả 403 nhưng background worker vẫn tạo export file. | FAIL no-side-effect, sửa worker PEP. |
| AT46 | API trả 503 trong negative token probe. | UNVERIFIED, không tính DENY policy. |
| AT47 | Token invalid nhưng parser vẫn gọi business method trước verification. | Test FAIL, chặn side effects trước security gate. |
| AT48 | Event Mover cũ đến sau Leaver và tái cấp token/grant. | Revision/idempotency/current-state ngăn regrant. |
| AT49 | Rehire trùng email với tài khoản cũ. | Stable subject link được xác minh, không dùng lại grant/token lịch sử. |
| AT50 | Sau decommission service, local PAT ở SaaS còn dùng được. | Residual finding, không VERIFIED. |
| AT51 | Token hợp lệ gọi đúng tenant/action nhưng subject thiếu mandatory attribute. | Fail-safe theo policy, không default ALLOW. |
| AT52 | Access token xuất hiện trong HTTP query hoặc structured logs. | Test privacy/secret hygiene FAIL. |
| AT53 | Client nhận 403 rồi tự refresh liên tục. | Retry control ngăn vòng lặp/thác request. |
| AT54 | Resource Server cache token theo subject nhưng không theo tenant/audience. | Detect token confusion/cross-user isolation bug. |
| AT55 | Một RS chưa có introspection/denylist/current-state proof. | Hiển thị UNVERIFIED coverage gap và owner. |
| AT56 | Logout ở một thiết bị và refresh token trên thiết bị khác. | Trạng thái phụ thuộc policy device/global logout; test đúng contract. |
| AT57 | Token bearer được sao chép, dùng từ runtime khác. | Sender-constraint/risk policy chặn nếu đã áp; nếu không ghi residual risk. |
| AT58 | Business role bị thu hồi, API read-only hợp lệ vẫn cần ALLOW. | Không chặn nhầm mọi action do scope/policy broad deny. |
| AT59 | Network partition làm một RS nhận revoke event muộn. | Reconciliation/latency evidence và SLA breach nếu quá hạn. |
| AT60 | Revoke request succeeded nhưng token cũ vẫn được RS chấp nhận action Critical. | Không đánh dấu COMPLETED/VERIFIED. |

### Tổ chức test theo nhiều lớp

| Lớp | Nhóm test chủ đạo |
| --- | --- |
| **AS/unit** | Grant/consent/scope, PKCE, client auth, refresh rotation, token issuance. |
| **JWT/introspection** | Signature, issuer/audience, token type, exp/nbf, cache, JWKS. |
| **Authorization/PEP** | Tenant, object, RBAC/ABAC, SoD, missing attributes, no side effects. |
| **End-to-end JML** | Joiner effectiveAt, Mover token cũ, Leaver, rehire, contractor expiry. |
| **Workload** | App-only client, federation trust, env/tenant segregation, decommission. |
| **Failure/fault** | AS/PDP unavailable, event delay, cache stale, JWKS rotation, retry. |
| **Audit/privacy** | Correlation, verifiedAt, credential redaction, target coverage. |

### Phép thử phải có expected outcome độc lập

Test oracle lấy từ **approved IAM/business policy, verified subject state và resource owner rules**, không chỉ copy code production để tính kỳ vọng. Với một negative case, phải kiểm **đúng đường API**, đúng principal/target/tenant, và **không có unauthorized write, file, queue message hoặc downstream side effect**.

## 33. Những sai lầm phổ biến trong quản lý access token

| Sai lầm | Vì sao nguy hiểm | Khắc phục |
| --- | --- | --- |
| Coi access token giống refresh token hoặc ID token. | Sai flow/token purpose; mở đường token confusion. | Phân biệt credential type và audience. |
| Tin JWT vì giải mã được payload. | Cho phép claims giả mạo. | Chữ ký, thuật toán, issuer, audience và token type. |
| Chấp nhận bất kỳ JWKS/kid/alg do token chỉ định. | Có thể chọn sai trust key/algorithm. | Trusted issuer configuration và key allowlist. |
| Không kiểm audience. | API B nhận token dành cho API A. | RS audience validation bắt buộc. |
| Coi scope là quyền trên mọi object. | BOLA/cross-tenant exposure. | Resource-level authorization và ABAC. |
| Coi token còn hạn là user còn ACTIVE. | Mover/Leaver token tồn dư. | Current-state PEP/denylist/introspection theo SLA. |
| Coi logout IdP giết mọi JWT. | Phiên và token có vòng đời khác nhau. | Thiết kế token/RS revocation riêng. |
| Coi SCIM PATCH là global token revoke. | Local roles, sessions, PATs còn hoạt động. | Target readback và probe thực tế. |
| Coi revoke refresh token giết access token. | AT tự chứa đã phát có thể vẫn ALLOW. | RS enforcement/TTL/current-state checks. |
| Chỉ chọn TTL dài để giảm tải AS. | Cửa sổ credential lộ và quyền cũ kéo dài. | Risk-based TTL và metrics. |
| Coi TTL rất ngắn là đủ thay RBAC/SoD. | Token vẫn có thể dùng sai resource trong thời hạn. | Business authorization mỗi request. |
| Gửi token qua URL. | Lộ qua browser history, referrer, log. | Authorization header + TLS. |
| Ghi token trong logs/traces. | Log trở thành kho credential. | Redaction, safe references và retention. |
| Cache token không tách audience/user/tenant. | Dùng token sai người hoặc API. | Cache keys và isolation rõ. |
| Refresh token không rotate/bind phù hợp. | RT bị sao chép có thể lấy AT mới liên tục. | Rotation/sender-constraint và anomaly handling. |
| RT reuse được coi chắc chắn attacker. | Có thể có race/retry của client hợp lệ. | Incident review có context, policy xử lý nhất quán. |
| AS key rotation được xem như revoke user đơn lẻ. | Ảnh hưởng tất cả token ký bằng key. | Targeted revoke/current-state checks. |
| Không test async/bulk endpoints. | Request bị DENY nhưng job nền vẫn ghi dữ liệu. | PEP toàn đường, no-side-effect tests. |
| Chỉ đo HTTP 200 của revoke API. | Không biết RS node nào còn ALLOW. | Verified DENY evidence per required RS. |
| Dùng HTTP 503 làm proof thu hồi. | Outage bị nhầm policy DENY. | Positive control và đúng reason code. |
| App-only token thay quyền của user. | Confused deputy, bypass user permission. | Delegation/OBO đúng flow hoặc resource checks. |
| Không đánh giá service principal Leaver. | Grants/trust còn sau decommission. | Workload owner + access inventory + lifecycle. |
| Bỏ qua principal có quyền assume/impersonate. | User có thể lấy token quyền cao dù role trực tiếp thấp. | Trust graph/privilege path review. |
| Không có coverage của RS/cache nodes. | “Revoked” trong một app nhưng còn ALLOW nơi khác. | Coverage map, revalidation và SLA. |

## 34. Checklist triển khai access token lifecycle

1. **Token purpose rõ:** access, refresh, ID token, client credential và PAT/API key được phân biệt.
2. **Issuer/trust configuration:** AS có owner, issuer, token profile, signing keys và rotation policy rõ.
3. **Client registration:** client type, grants, redirect URIs, PKCE, authentication hoặc workload trust được xác minh.
4. **Audience/resource binding:** mỗi token chỉ dùng đúng Resource Server(s) được duyệt.
5. **Approved scopes:** AS không tự cấp scope cao hơn grant/client/resource policy.
6. **Short-lived theo risk:** TTL/nbf/exp và clock skew có lý do, không mặc định càng dài càng tốt.
7. **Token storage/transit:** TLS, BFF/secure storage theo threat model, không URL/log/redirect leak.
8. **RS verification:** chữ ký/introspection, issuer, algorithm, token type, audience, time và trusted claims.
9. **Business authorization:** RBAC/ABAC theo action, resource, tenant, state và data classification.
10. **SoD:** chặn self-approval và xung đột quyền dù token valid.
11. **Refresh lifecycle:** issuance chỉ khi phù hợp, RT rotation/binding, expiry, reuse detection và revocation.
12. **Session separation:** SSO/IdP session, app session, RT, AT và PAT có chính sách rõ.
13. **Early revocation:** chọn mechanisms thực tế và tính cache/propagation/coverage vào SLA.
14. **DPoP/mTLS khi cần:** RS validate sender proof, không chỉ có cnf claim.
15. **JWKS/key rotation:** controlled overlap, emergency response cho key compromise và trust key validation.
16. **Delegation/OBO:** API A không forward token sai audience sang B; tránh confused deputy.
17. **JML Joiner:** pre-hire không access trước effectiveAt; activation đúng scope và identity mapping.
18. **JML Mover:** revoke old rights và token behavior trước khi quyền mới gây SoD overlap.
19. **JML Leaver:** disable issuance, refresh grants, sessions, access tokens và app-local credentials theo scope.
20. **Service account:** client credentials/federation, owner, trust, environment, rotation và decommission.
21. **Stable identity:** subject ID và target principal mappings; không dựa email đơn lẻ.
22. **Runtime/endpoint coverage:** gateway, API, bulk/export, background workers và local SaaS đều có kiểm soát.
23. **Failure behavior:** AS/PDP outage/cache errors không mở allow mặc định cho action nhạy cảm.
24. **Idempotency/event ordering:** JML event cũ không regrant, revoke workflow retry an toàn.
25. **Target readback:** SCIM/IGA/app roles và grant status được xác minh, không chỉ command success.
26. **Positive/negative probes:** ALLOW nghiệp vụ đúng, DENY out-of-scope và không có side effects.
27. **Time evidence:** effectiveAt, appliedAt, verifiedAt khác nhau; đo latency đúng target.
28. **Audit:** subject/client/issuer/RS, policy version và reason, không có raw credentials.
29. **Incident readiness:** playbook token theft, signing-key compromise, client-secret exposure, RS stale caches.
30. **Review/closure:** chưa có bằng chứng cho một RS critical thì trạng thái phải là PARTIAL/UNVERIFIED.

**Điều kiện nghiệm thu:** một hệ thống token tốt vừa **cấp và sử dụng token hợp lệ đúng quyền**, vừa **chặn token không còn đủ điều kiện trong cửa sổ chấp nhận được có kiểm chứng**. Chỉ “JWT parse thành công” hoặc “IAM đã gỡ group” không đủ.


## 35. Câu hỏi tự kiểm tra

**Câu 1.** Access token khác refresh token như thế nào?

**Trả lời:** Access token dành cho **Resource Server** để truy cập protected APIs trong phạm vi được phép. Refresh token là credential dùng với **Authorization Server** để xin access token mới khi grant/client còn đủ điều kiện; không gửi refresh token trực tiếp tới protected API.

**Câu 2.** JWT access token khác opaque token ở đâu?

**Trả lời:** JWT có thể chứa claims mà RS kiểm chữ ký/issuer/audience/time cục bộ; opaque token thường cần AS/introspection hoặc cơ chế kiểm tra riêng. JWT offline giảm mạng nhưng khó chặn trước exp nếu không có state bổ sung; opaque phụ thuộc introspection/caching và availability. Cả hai vẫn cần resource authorization.

**Câu 3.** Vì sao một JWT có chữ ký hợp lệ vẫn có thể phải bị DENY?

**Trả lời:** Chữ ký chỉ là một phần của validation. Token có thể sai issuer/audience/type, hết hạn, không đủ scope hoặc subject đã Leaver/Mover. Resource Server phải kiểm quyền hiện hành, tenant, object, business state và SoD.

**Câu 4.** Khi user logout ở IdP, access token đã phát có lập tức bị mọi API từ chối không?

**Trả lời:** Không mặc định. IdP session, ứng dụng web session, refresh grant và access tokens có vòng đời khác nhau. Một JWT offline có thể còn được RS chấp nhận đến exp nếu không có cơ chế thu hồi/current-state bổ sung.

**Câu 5.** Gỡ group của Mover qua SCIM có đủ để chặn role cũ không?

**Trả lời:** Chưa chắc. SCIM có thể cập nhật account/group nhưng token cũ, application-local role, ACL hoặc cache vẫn ALLOW. Phải xác minh tại các target/PEP bắt buộc theo SLA.

**Câu 6.** Vì sao access token TTL ngắn không thay thế authorization?

**Trả lời:** Một token 5 phút vẫn có thể được sử dụng sai resource/tenant hoặc thực hiện hành động SoD cấm trong 5 phút đó. RS luôn phải kiểm action/resource và các điều kiện hiện hành cần thiết.

**Câu 7.** Revoke refresh token có thể ngăn những gì?

**Trả lời:** Nó có thể chặn client lấy **access token mới bằng refresh grant đó**, tùy AS contract. Nó không tự chứng minh access token cũ bị mọi RS từ chối ngay; cần cơ chế và bằng chứng riêng cho access tokens.

**Câu 8.** Token revocation và introspection khác nhau thế nào?

**Trả lời:** Revocation làm thay đổi trạng thái token/grant ở hệ thống có thẩm quyền. Introspection cho RS truy vấn trạng thái/metadata token. Introspection cache có thể trễ, nên không được coi AS revoke success là RS verified deny.

**Câu 9.** DPoP hoặc mTLS-bound token giải quyết vấn đề gì?

**Trả lời:** Chúng ràng buộc việc dùng token với key/certificate của client, giúp giảm khả năng reuse khi chỉ token bị sao chép. Không thay scope, audience, RBAC/ABAC, expiry hoặc chống mọi trường hợp runtime bị chiếm.

**Câu 10.** API A có nên chuyển access token đã nhận thẳng cho API B không?

**Trả lời:** Không khi token dành cho audience A. Nếu nghiệp vụ cần B, dùng token audience B qua flow được AS/RS cho phép như OBO/token exchange hoặc app-only hợp lệ; kiểm user/client/resource policy để tránh confused deputy.

**Câu 11.** Điều gì xảy ra nếu JWT signing key được quay vòng?

**Trả lời:** Issuer có thể bắt đầu ký bằng key mới; RS cần nhận trusted public key mới/JWKS. Overlap key cũ phải phù hợp token TTL và risk. Xoay signing key không phải cách revoke từng user, còn compromised signing key cần incident response đặc biệt.

**Câu 12.** Vì sao token chứa claim payment.approve chưa bảo đảm được duyệt một payment?

**Trả lời:** Payment có thể thuộc tenant khác, đã hoàn tất, vượt hạn mức hoặc do chính actor tạo. RS phải kiểm current access và transaction-level SoD, không chỉ claim scope/role.

**Câu 13.** Phải làm gì khi AS/introspection không hoạt động?

**Trả lời:** Không tự động ALLOW quyền nhạy cảm khi thiếu kiểm tra bắt buộc. Dùng fail-safe/INDETERMINATE và alert theo risk policy; nếu có bounded cache thì phải có TTL và risk acceptance rõ ràng.

**Câu 14.** Vì sao không dùng email làm khóa thu hồi mọi token?

**Trả lời:** Email có thể đổi/tái sử dụng và tồn tại nhiều tenants. Cần stable subject ID và mapping trust với app account/client/tenant để không revoke nhầm hoặc regrant quyền cũ.

**Câu 15.** API trả HTTP 503 khi thử token cũ sau Leaver. Có đủ bằng chứng revoke chưa?

**Trả lời:** Không. 503 thường là lỗi khả dụng; phải có positive control và chứng cứ quyết định authentication/authorization DENY ở RS hoạt động. Không được tính outage là policy PASS.

**Câu 16.** Nếu một Leaver còn PAT trên SaaS ngoài OAuth, xử lý ra sao?

**Trả lời:** PAT có vòng đời riêng tại SaaS. Cần inventory, revoke/disable ở target, readback và negative probe, không suy PAT đã chết khi IdP logout hoặc SCIM gỡ account.

**Câu 17.** Khi service principal bị lộ client secret, rotate secret có đủ không?

**Trả lời:** Chưa. Cần tìm access tokens đã phát từ secret cũ, đánh giá RS có chặn sớm không, kiểm grants/audiences, token issuance anomalies, runtime compromise và xử lý theo incident SLA.

**Câu 18.** Tại sao một event Leaver đã chạy thành công ở IAM vẫn có thể là FAIL bảo mật?

**Trả lời:** IAM/AS có thể đã update nhưng một RS node, cache, local session hoặc API worker vẫn ALLOW với token cũ. Thành công phải đo qua **required target readback và verified DENY**, không qua status xử lý event đơn thuần.

**Câu 19.** Khi nào phải dùng current-state authorization thay cho claim-only token?

**Trả lời:** Khi business risk và SLA đòi chặn quyền trước exp hoặc kiểm điều kiện động (JML, SoD, tenant, resource status). Có thể dùng online PDP/PIP, introspection, policy epoch/denylist hoặc mô hình hybrid phù hợp hệ thống.

**Câu 20.** Những thông tin gì cần audit để chứng minh thu hồi đã hoàn tất?

**Trả lời:** Stable subject/client refs, issuer, RS/target, entitlement/policy version, effectiveAt, appliedAt, verifiedAt, outcome/probe evidence, reason code, coverage gaps, owner và SLA. Không ghi raw bearer/refresh token hay client secret.

## 36. Đọc thêm: những đặc tả và câu hỏi cần tra cứu khi triển khai

Các tài liệu sau hữu ích để đối chiếu **profile và khả năng thực tế của AS/RS đang sử dụng**; không phải tất cả đều cần triển khai trong một hệ thống:

| Chủ đề | Tài liệu/đặc tả để tra cứu | Cần xác nhận với platform |
| --- | --- | --- |
| OAuth 2.0, bearer token | **RFC 6749, RFC 6750** và các cập nhật/khuyến nghị bảo mật liên quan. | Grant types, token placement, client authentication, scopes. |
| OAuth Security Best Current Practice | **RFC 9700**. | Các luồng và biện pháp mới được AS hỗ trợ, đặc biệt public client/RT. |
| PKCE | **RFC 7636**. | Code challenge/verifier enforcement trong authorization code flow. |
| Token revocation | **RFC 7009**. | Hỗ trợ revoke RT/AT, semantics và propagation tới RS. |
| Token introspection | **RFC 7662**. | Active response, client auth, cache TTL và SLA. |
| JWT và JWT security | **RFC 7519**, **RFC 8725**. | Allowed algorithms, issuer/audience/token type, key provenance. |
| JWT access token profile | **RFC 9068**. | Claim names/semantics nếu issuer và RS dùng profile này. |
| OAuth token exchange | **RFC 8693**. | Subject/actor delegation, audience/scope và policy tại AS. |
| OAuth mTLS | **RFC 8705**. | Certificate-bound token và validation tại TLS termination. |
| DPoP | **RFC 9449**. | Proof verification, htm/htu, jti/replay, key binding. |
| OIDC | **OpenID Connect Core** và logout specs khi áp dụng. | ID token versus AT, SSO session và logout integration. |
| SCIM | **RFC 7643/7644**. | User/group provisioning, không nhầm với global OAuth token revoke. |

**Các con số TTL, grace period, refresh lifetime và SLA cần dựa trên mô hình rủi ro, nghĩa vụ vận hành và platform capabilities thực tế**, không lấy một giá trị chung áp cho mọi loại token. Những thay đổi standards/provider-specific cần được kiểm chứng với tài liệu chính thức của hệ thống triển khai.

---

**Ghi nhớ:** **Access token lifecycle không kết thúc khi Authorization Server cấp token hoặc khi IAM ghi “revoked”.** Từ issuance, phân phối, lưu trữ, validation, refresh/reissue, đến expiry/revocation và incident response, hệ thống phải quản lý **issuer, client, subject, audience, token type, scope, thời hạn và policy tại Resource Server**. Với **Joiner–Mover–Leaver**, điểm quyết định là **token cũ có còn cho truy cập trái quyền hiện hành hay không**. Kết hợp **IdP/SSO, SCIM, RBAC/ABAC, workload identity, SoD, session/token controls, audit và readback tại PEP** để người còn quyền hợp lệ tiếp tục làm việc, còn **quyền tồn dư sau thay đổi vai trò hoặc nghỉ việc thực sự bị chặn với bằng chứng và SLA minh bạch**.
