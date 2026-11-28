# Xác minh identity trước mỗi phiên truy cập trong Zero Trust Network Access

Một nhân viên làm việc từ xa cần truy cập hệ thống quản lý đơn hàng nội bộ. Trong mô hình mạng truyền thống, khi laptop kết nối VPN thành công, thiết bị có thể có đường mạng tới nhiều subnet hoặc máy chủ nội bộ, dù người đó chỉ cần sử dụng một ứng dụng. Giả sử sau khi vào VPN, một token của ứng dụng bị đánh cắp hoặc laptop chuyển từ trạng thái an toàn sang không tuân thủ chính sách. **Quyền truy cập đã cấp trước đó nên tiếp tục bao lâu và ai có quyền thu hồi?**

**Zero Trust Network Access (ZTNA)** giải quyết một phần bài toán này bằng cách thiết kế quyền truy cập **dựa vào danh tính, thiết bị, ngữ cảnh và tài nguyên cụ thể**, thay vì coi việc xuất hiện trong một mạng "nội bộ" là bằng chứng đáng tin. Trước khi thiết lập **một phiên truy cập được bảo vệ**, hệ thống cần xác minh danh tính chủ thể, đánh giá điều kiện chính sách và chỉ mở đường cần thiết tới ứng dụng đích. Trong phiên, chính sách có thể được đánh giá lại theo thời gian hoặc sự kiện khi hệ thống hỗ trợ.

Bài thuộc chương **Zero Trust Network Access** của module **SECURITY_NETWORK_SECURITY**: nắm các lớp phòng vệ mạng từ phân đoạn, firewall, VPN, IDS/IPS và xác thực kết nối đến bảo vệ DNS, mạng không dây và hạ tầng đám mây; biết phân tích lưu lượng, mô hình hóa mối đe dọa, giám sát xâm nhập và xây dựng kiến trúc mạng an toàn. Trọng tâm bài này là **xác minh identity trước mỗi phiên truy cập** và mối quan hệ giữa *authentication*, *authorization*, *session establishment*, *continuous assessment* và *revocation*.

> **Nguyên tắc:** **Không cấp phiên truy cập tới tài nguyên chỉ vì một thiết bị đã nằm trong mạng công ty, có IP VPN, hoặc từng đăng nhập thành công.** Cần có quyết định dựa trên danh tính được xác minh, quyền được phép tại thời điểm xét và điều kiện bảo mật của phiên. **“Never trust, always verify” không đồng nghĩa nhập lại mật khẩu hoặc MFA cho từng TCP packet.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **identity trước phiên** trong ZTNA và phân biệt **authentication, authorization, session management**.
2. Phân biệt **identity người dùng, thiết bị, workload và ứng dụng**; xác định nguồn chứng cứ tin cậy của từng loại.
3. Mô tả kiến trúc **Identity Provider (IdP), Policy Decision Point (PDP), Policy Enforcement Point (PEP), Policy Administrator** và tài nguyên cần bảo vệ.
4. Trình bày cơ chế **SSO, OIDC/OAuth 2.0, SAML, MFA/passkeys, device posture**, cùng giới hạn khi sử dụng.
5. Giải thích **đánh giá trước cấp phiên, đánh giá lại trong phiên, timeout, renew, revoke và step-up authentication**.
6. Phân tích cách chặn **session hijacking, token replay, giả mạo header, lạm dụng máy tin cậy, truy cập sai tenant**.
7. Thiết kế policy theo **principal + resource + action + posture + context**, không dựa duy nhất vào mạng hoặc địa chỉ IP.
8. Phân biệt ZTNA với VPN, network segmentation, API gateway, mTLS, service mesh và application authorization.
9. Lập phép thử positive/negative, telemetry, runbook và quy trình chuyển đổi an toàn.

## 2. “Trước mỗi phiên truy cập” có nghĩa chính xác là gì?

Từ **phiên (session)** có nhiều nghĩa trong networking và identity, vì thế cần thống nhất ngữ cảnh:

| Khái niệm | Đối tượng/quy mô | Điều gì được xác minh? |
|---|---|---|
| **TCP connection** | Một kết nối transport đến IP:port | Bắt tay TCP không tự xác thực danh tính người dùng |
| **TLS session/connection** | Kết nối bảo vệ bằng TLS, có thể có resumption | Danh tính server; đôi khi client nếu mTLS |
| **IdP login/SSO session** | Lần đăng nhập với nhà cung cấp danh tính | Chứng cứ xác thực người dùng, MFA, phiên IdP |
| **ZTNA access session** | Quyền đi từ một subject tới tài nguyên ứng dụng theo policy | Identity, entitlement, device/context và quyết định allow/deny |
| **Application session** | Cookie/token và trạng thái nghiệp vụ tại ứng dụng | Quyền user, phiên ứng dụng, CSRF/session controls |
| **HTTP API request** | Từng lời gọi API | Token/credential, scope và resource authorization theo thiết kế |

**“Xác minh trước mỗi phiên truy cập”** thường có nghĩa: **trước khi PEP cho phép thiết lập một phiên truy cập tới tài nguyên bảo vệ, phải có quyết định policy dựa trên identity và ngữ cảnh đủ mới**. Tùy hệ thống, phiên ZTNA có thể kéo dài qua nhiều HTTP requests hoặc kết nối TCP; không nhất thiết cần yêu cầu user làm MFA cho mỗi request.

Ví dụ:

- Nhân viên đã đăng nhập IdP lúc 09:00 với MFA; lúc 09:10 mở ứng dụng quản trị nhạy cảm. ZTNA vẫn cần **xem xét quyền vào ứng dụng đó** và freshness của xác thực, không mặc định cho qua vì SSO còn hiệu lực.
- Lúc 09:20, máy bị phát hiện không còn tuân thủ chính sách. Tùy khả năng tích hợp của ZTNA, hệ thống có thể **từ chối phiên mới**, yêu cầu xác minh bổ sung hoặc **thu hồi phiên đang hoạt động**.
- Lúc 09:25, nhân viên xin truy cập một ứng dụng khác. Cần **quyết định truy cập riêng cho tài nguyên thứ hai**, không suy từ phiên đầu tiên rằng người đó được vào mọi hệ thống.

### 2.1. Ba điều kiện khác nhau

1. **Authentication (AuthN):** chứng minh chủ thể đang yêu cầu là ai hoặc sở hữu credential của ai.
2. **Authorization (AuthZ):** chủ thể đó **được làm gì với tài nguyên nào** tại thời điểm này.
3. **Session enforcement:** cách cho phép, giới hạn thời lượng, giám sát, gia hạn và **cắt quyền** khi hết điều kiện.

Một IdP trả kết quả **“user đã đăng nhập”** không đồng nghĩa ứng dụng tài chính đã phê duyệt **“được chuyển tiền từ tài khoản khách hàng X”**. ZTNA và ứng dụng phải phân tách hai quyết định.

## 3. Vì sao “nằm trong mạng nội bộ” không đủ tin cậy?

Mô hình cấp quyền theo vị trí mạng có một số hạn chế:

- Một thiết bị nội bộ bị malware có thể sử dụng các đường mạng đang mở.
- Laptop có VPN IP hợp lệ vẫn có thể do người dùng sai quyền hoặc token bị đánh cắp điều khiển.
- NAT, proxy, VDI, cloud workloads và mạng hybrid khiến **IP không gắn ổn định với danh tính người dùng**.
- Một nhóm nhà thầu chỉ cần truy cập một API nhưng VPN có thể cho route tới cả subnet.
- Người dùng thay đổi vai trò, nghỉ việc hoặc hết hợp đồng; ACL theo IP khó thu hồi quyền theo identity.
- Phiên đăng nhập cũ có thể tồn tại sau khi posture thay đổi nếu không kiểm tra/revoke.

~~~mermaid
flowchart LR
    subgraph OLD["Mô hình tin cậy quá rộng"]
      V["User + VPN"] --> N["Mạng nội bộ"]
      N --> A["Ứng dụng A"]
      N --> B["Ứng dụng B"]
      N --> C["Admin subnet"]
    end
    subgraph NEW["Ý định ZTNA"]
      U["User / device"] --> P["Identity + policy enforcement"]
      P -->|"Chỉ route đã duyệt"| APP["Ứng dụng được phép"]
      P -.->|"Không tự cấp quyền"| OTH["Ứng dụng khác"]
    end
~~~

Sơ đồ mô tả **mục tiêu phân quyền**, không khẳng định mọi VPN đều mở mạng rộng hoặc mọi ZTNA sản phẩm đều mặc định an toàn. VPN có thể được kết hợp segmentation, MFA và per-app policies; ZTNA cũng có thể bị cấu hình allow-all.

## 4. Các đối tượng identity trong một phiên

Không nên gom toàn bộ danh tính vào một trường `username`.

| Identity / bằng chứng | Câu hỏi | Nguồn chứng cứ có thể dùng | Giới hạn |
|---|---|---|---|
| **User identity** | Người thực hiện yêu cầu là ai? | IdP/SSO, directory, MFA/passkey | Tài khoản hợp lệ vẫn có thể bị chiếm quyền |
| **Device identity** | Thiết bị nào kết nối? | MDM enrollment, device certificate, TPM-bound key | Cert máy không chứng minh user đang thao tác hợp lệ |
| **Device posture** | Thiết bị có tuân thủ yêu cầu hiện tại? | EDR/MDM signals, OS patch, disk encryption | Tín hiệu có thể trễ, thiếu hoặc bị giả nếu nguồn không tin cậy |
| **Workload identity** | Service/process nào tạo kết nối? | ServiceAccount, mTLS certificate, SPIFFE ID | Credential của workload vẫn có thể bị lạm dụng |
| **Application identity** | Tài nguyên đích nào đang được gọi? | App catalog, service ID, FQDN, certificate | FQDN/IP không tự chứng minh app owner |
| **Session identity** | Đây có phải phiên đã cấp và còn hợp lệ? | Signed/opaque session, policy version, device binding | Token/phiên có thể bị đánh cắp nếu lưu và quản lý sai |
| **Risk context** | Có tín hiệu bất thường hay cần step-up? | Account alerts, impossible travel, posture drift, network signals | Risk score là chỉ báo, không phải identity |

Một quyết định truy cập an toàn thường dựa vào **nhiều yếu tố có nguồn gốc được xác minh**. Ngược lại, việc một client tự gửi `X-Device-Compliant: true` hoặc `X-Employee: admin` **không phải** bằng chứng đáng tin.

### 4.1. Identity khác location

- **IP doanh nghiệp** là thuộc tính của một điểm mạng; có thể chia sẻ bởi nhiều user và thay đổi qua NAT.
- **Username** có thể là claim chưa được xác minh nếu chỉ lấy từ HTTP header.
- **JWT** có thể mang các claims đã được ký, nhưng phải xác thực issuer, audience, signature, validity và ngữ cảnh sử dụng; nó không tự chứng minh thiết bị an toàn.
- **Client certificate** chứng minh bên kết nối sở hữu private key tương ứng trong cơ chế handshake; quyền truy cập vẫn cần chính sách.

### 4.2. Identity của nhà thầu và tài khoản đặc quyền

Nhà thầu có thể cần truy cập một ứng dụng trong thời gian hợp đồng, còn nhân viên vận hành có thể cần truy cập SSH/RDP/DB trong ca trực. Hai trường hợp nên dùng **policy riêng** về resource, role, xác thực tăng cường, posture và thời gian phiên.

**Không biến “đã có corporate account” thành allow mọi internal apps**. Quyền nên gắn với vai trò/nhiệm vụ và được rà soát khi joiner–mover–leaver xảy ra.

## 5. Kiến trúc ZTNA: PDP, PEP, IdP và ứng dụng

Một kiến trúc tham chiếu thường phân tách **thành phần quyết định** và **thành phần thực thi** chính sách. Có thể đối chiếu mô hình Policy Engine/Policy Administrator/Policy Enforcement Point trong cách tiếp cận Zero Trust.

~~~mermaid
flowchart LR
    USER["User + managed device"] --> CLIENT["Browser / ZTNA client"]
    CLIENT --> PEP["Policy Enforcement Point / connector / gateway"]
    PEP -->|"Chỉ phiên đã cấp"| APP["Private application"]
    PEP -.->|"Access decision"| PDP["Policy Decision Point"]
    PDP -.-> IDP["IdP / SSO / MFA"]
    PDP -.-> MDM["MDM / EDR posture signals"]
    PDP -.-> ENT["App entitlement / roles"]
    PDP -.-> RISK["Risk / session context"]
    PDP -.->|"Grant / deny / re-evaluate"| PEP
    APP -.-> AUTH["Application AuthN/AuthZ / audit"]
~~~

### 5.1. Trách nhiệm từng thành phần

| Thành phần | Trách nhiệm chính | Nếu bị compromise |
|---|---|---|
| **IdP** | Xác thực người dùng, điều kiện đăng nhập, session IdP | Có thể làm sai nguồn sự thật về identity |
| **PDP / policy engine** | Tổng hợp identity, entitlement, context để ra allow/deny/step-up | Có thể cấp quyền sai cho nhiều ứng dụng |
| **Policy administrator / session broker** | Thiết lập/thu hồi đường truy cập theo quyết định (tùy sản phẩm) | Có thể tạo phiên ngoài policy nếu quyền rộng |
| **PEP / gateway / connector / agent** | Chặn trước khi truy cập, chỉ cho luồng đã cấp, giám sát và terminate khi cần | Có thể bypass policy hoặc trở thành đường vào origin |
| **Device posture provider** | Đưa tín hiệu trạng thái thiết bị | Có thể cấp quyết định sai khi signal bị giả/stale |
| **Application** | Xác thực/ủy quyền nghiệp vụ và dữ liệu | Lỗi object-level AuthZ dù ZTNA đúng |
| **Audit/telemetry** | Ghi chính sách, quyết định, phiên, sự kiện thu hồi | Khó điều tra và phát hiện lạm dụng nếu thiếu |

**PEP phải nằm trên đường thực tới tài nguyên cần bảo vệ**. Một policy tồn tại trên dashboard nhưng người dùng vẫn có thể truy cập trực tiếp origin IP/FQDN qua firewall/peering khác là **bypass**.

### 5.2. Control plane và data plane không đồng nhất

Tùy nhà cung cấp:

- User có thể đăng nhập qua cloud identity service.
- Một PEP/connector nội bộ chuyển data traffic tới ứng dụng.
- PDP/console có thể nằm ở hệ thống cloud hoặc cụm do doanh nghiệp vận hành.
- Phiên có thể sử dụng reverse proxy HTTPS, tunnel đến private app hoặc client/agent cho TCP ứng dụng.

Không suy rằng **mọi data packet** đều đi qua PDP hoặc cloud control plane. PEP thường **thực thi quyết định đã được cấp** tại data plane, với khả năng kiểm tra lại theo policy.

## 6. Vòng đời một phiên truy cập theo ZTNA

Một phiên điển hình có thể trải qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Authenticated: Kiểm chứng user/device/workload
    Requested --> Denied: Identity không hợp lệ
    Authenticated --> Evaluated: PDP đánh giá entitlement/context
    Evaluated --> Denied: Không thỏa policy
    Evaluated --> StepUp: Cần MFA/phê duyệt bổ sung
    StepUp --> Evaluated: Xác thực bổ sung thành công
    StepUp --> Denied: Thất bại / timeout
    Evaluated --> Granted: Quyết định allow
    Granted --> Active: PEP thiết lập access session
    Active --> Reevaluate: TTL / sự kiện / posture thay đổi
    Reevaluate --> Active: Vẫn thỏa policy
    Reevaluate --> Restricted: Điều kiện xấu đi
    Reevaluate --> Revoked: Hết quyền / nguy cơ cao
    Active --> Expired: Hết phiên hoặc inactivity
    Restricted --> Revoked: Policy yêu cầu cắt quyền
    Revoked --> [*]
    Denied --> [*]
    Expired --> [*]
~~~

Đây là **mô hình khái niệm**, không phải state machine bắt buộc trong mọi sản phẩm. Một số ZTNA không có trạng thái `Restricted` hay cơ chế thu hồi ngay TCP sessions đã mở; một số chỉ cập nhật policy khi reconnect hoặc token hết hạn. **Năng lực thực tế phải được thử**.

### 6.1. Pha A — Request và authentication

Người dùng chọn ứng dụng `orders-admin.example.test` trong portal, browser hoặc client. Hệ thống cần xác minh có một principal hợp lệ:

1. Chọn IdP/trust federation được công ty phê duyệt.
2. Kiểm tra hình thức chứng thực (password + MFA, passkey/FIDO2 hoặc phương án đáp ứng chính sách).
3. Kiểm tra trạng thái account: active, locked, disabled, quyền truy cập ứng dụng.
4. Kiểm tra session IdP còn đủ mới, có cần step-up/reauthentication không.
5. Kiểm chứng device identity/posture khi policy yêu cầu, tránh tin claim client tự khai.

Các kiểm tra có thể sử dụng **SSO session còn hiệu lực** thay vì bắt nhập lại mật khẩu. Điều quan trọng là **bằng chứng authentication được chấp nhận có độ tin cậy và độ mới phù hợp** với ứng dụng được truy cập.

### 6.2. Pha B — Authorization và context

PDP xét tối thiểu:

- Principal `user:employee-123` đã xác thực.
- Group/role/entitlement cho tài nguyên `orders-admin`.
- Action được yêu cầu: mở ứng dụng, SSH tới host, gọi API hay mở console.
- Thiết bị thuộc nhóm managed/được chứng thực hay BYOD; EDR và mã hóa đĩa khi được yêu cầu.
- Tín hiệu risk: đăng nhập bất thường, thiết bị không compliant, phiên IdP hết hạn.
- Điều kiện thời gian/location nếu chính sách có căn cứ; **không dựa duy nhất IP geolocation** để xác minh danh tính.

Kết quả có thể là **Allow**, **Deny** hoặc **Step-up/Require remediation**, theo mô hình sản phẩm.

### 6.3. Pha C — PEP thiết lập access session

Chỉ khi policy cho phép, PEP cấp **đường tới tài nguyên đã được phê duyệt**, với các thuộc tính:

| Thuộc tính phiên | Mục đích |
|---|---|
| Session ID ngẫu nhiên/không đoán được | Ghép log, quản lý thời lượng; không dùng session ID có tính dự đoán |
| User/service principal đã xác thực | Biết ai được cấp phiên |
| Device binding/posture reference nếu hỗ trợ | Ràng buộc hoặc kiểm tra ngữ cảnh thiết bị |
| Resource/application ID | Chỉ mở đúng tài nguyên |
| Authorization scopes/actions | Quyền tối thiểu, tránh mở toàn subnet |
| Issued time, expiry, idle timeout | Giới hạn độ dài |
| Risk level/assurance | Quy định yêu cầu MFA/reauth hoặc policy riêng |
| Policy version/decision ID | Truy vết tại sao phiên được cấp |
| Revocation handle khi hỗ trợ | Khóa/đóng phiên khi điều kiện thay đổi |

**Không đồng nghĩa PEP tự thay thế ứng dụng AuthZ.** Với một API đọc đơn hàng, ZTNA cho phép vào `orders-api` nhưng backend vẫn phải kiểm tra user được phép đọc **đơn hàng cụ thể** nào.

### 6.4. Pha D — Theo dõi, đánh giá lại và thu hồi

Các tín hiệu cần re-evaluate có thể là:

- Phiên IdP quá cũ so với mức assurance của ứng dụng.
- Token/access grant đến thời điểm hết hạn.
- MDM/EDR báo thiết bị không còn compliant hoặc mất kết nối lâu.
- User bị khóa, đổi nhóm, rời tổ chức hoặc tài khoản bị nghi bị chiếm.
- Đổi vị trí/network bất thường kèm những yếu tố rủi ro khác.
- Access pattern cho thấy khai thác quyền, trích xuất dữ liệu bất thường.
- Thay policy ứng dụng, chỉ cho phép vào một môi trường/tenant khác.

Tùy hỗ trợ của hệ thống, kết quả có thể là yêu cầu MFA mới, giới hạn quyền, từ chối tạo phiên mới, **đóng phiên đang mở** hoặc chờ đến kỳ đánh giá tiếp theo. Không hứa **real-time revocation** nếu PEP không nhận sự kiện/không có khả năng chấm dứt kết nối.

## 7. “Verify explicitly” không phải “authenticate every packet”

Phải phân biệt **frequency** và **granularity** của các quyết định:

| Thời điểm | Việc nên đánh giá | Ví dụ thực thi |
|---|---|---|
| Khi login IdP | User authentication, MFA, sign-in risk | Passkey, conditional access |
| Khi mở ứng dụng mới | Per-resource entitlement và session assurance | PDP allow/deny trước PEP |
| Khi truy cập chức năng nhạy cảm | Step-up và application-level AuthZ | MFA cho thay đổi tài khoản, phê duyệt giao dịch |
| Mỗi request API | Token validity, scopes, tenant/object quyền | Gateway + backend AuthZ |
| Khi phiên cần renew | TTL, posture, account state, authorization | Token refresh + policy re-evaluation |
| Khi có sự kiện risk | Revoke/restrict nếu nền tảng hỗ trợ | Account disable, EDR noncompliance, CAE-like event |
| Khi logout hoặc hết hạn | Session invalidation và cleanup | Đóng session, thu hồi credential theo khả năng |

**Nhiều tầng có thể cùng xác minh** mà vẫn không bắt user tương tác lặp đi lặp lại. Ví dụ browser có cookie SSO HttpOnly/Secure, PDP có decision cache ngắn hạn và API có token validity/authorization; các cơ chế đó phục vụ những quyết định **khác nhau**.

### 7.1. Độ mới của xác thực (authentication freshness)

Một phiên đăng nhập từ hôm qua **không nhất thiết đủ** cho thao tác quản trị đặc quyền hôm nay. Policy có thể yêu cầu:

- MFA/passkey gần đây trong một khoảng thời gian xác định.
- Identity assurance level phù hợp.
- Thiết bị có chứng cứ compliance còn hạn.
- Session phải tái xác minh khi truy cập tài nguyên rủi ro cao.

Thời hạn không nên là một con số “chuẩn ZTNA” áp cho mọi ứng dụng. Chọn theo **phân loại dữ liệu, rủi ro, khả năng IdP/PEP, yêu cầu pháp lý và usability** rồi thử trong thực tế.

### 7.2. Chặn lại toàn bộ phiên khi mất kết nối IdP?

Nếu IdP/PDP tạm thời unavailable, hệ thống phải có **degraded-mode/failure policy**:

- Không cấp **phiên mới** nếu không thể xác minh identity/policy theo yêu cầu.
- Phiên đã có có thể tiếp tục trong **TTL/cached decision được thiết kế**, nếu được phê duyệt cho resource đó.
- Các tài nguyên đặc quyền có thể chọn **fail-closed** nghiêm hơn.
- Không dùng lý do availability để mặc định bypass PEP và mở direct origin.

**Fail closed cần xét đúng bối cảnh**: nếu mọi access bị chặn khi IdP outage, ứng dụng quan trọng có thể mất khả dụng. Thiết kế policy phải ghi rõ **đánh đổi bảo mật–khả dụng**, phương án break-glass đã được quản trị và điều kiện kết thúc ngoại lệ.

## 8. Identity Provider, SSO, OIDC và MFA

### 8.1. IdP cung cấp danh tính nhưng ZTNA quyết định truy cập tài nguyên

IdP giúp xác thực user, quản lý nhóm, MFA và phát các assertions/tokens cho client ứng dụng hoặc gateway. Nhưng **membership/claim không tự cấp mọi quyền**: PDP hoặc application phải ánh xạ đúng group/role đến **resource/action**.

Một IdP có thể phục vụ nhiều ứng dụng. Một user có SSO session hợp lệ vẫn bị từ chối vào database console nếu không có entitlement hoặc posture không đạt yêu cầu.

### 8.2. OIDC, OAuth 2.0 và SAML đóng vai trò nào?

| Cơ chế | Vai trò phù hợp | Điểm dễ nhầm |
|---|---|---|
| **OpenID Connect (OIDC)** | Identity layer trên OAuth 2.0, hỗ trợ login và ID token | **ID token không mặc định là access token cho mọi API** |
| **OAuth 2.0** | Ủy quyền cho client dùng access tokens tới resource server | Token phải được API kiểm tra issuer/audience/scope, không chỉ xem có chuỗi token |
| **SAML 2.0** | Federation/SSO bằng signed assertions trong nhiều enterprise apps | Assertion có lifetime, audience, recipient và signature cần kiểm tra |
| **WebAuthn/FIDO2 passkeys** | Xác thực người dùng mạnh, có khả năng chống phishing tốt khi triển khai đúng | Không thay per-resource authorization hoặc device posture |
| **MFA qua push/OTP** | Tăng chứng cứ người dùng sở hữu yếu tố bổ sung | Có rủi ro phishing, MFA fatigue, adversary-in-the-middle tùy phương án |
| **mTLS client certificates** | Xác thực endpoint/workload/device ở kênh TLS | Không chứng minh user đang được phép thao tác một tài nguyên nghiệp vụ |

**OIDC/OAuth 2.0 không “mã hóa đường mạng”**; HTTPS/TLS vẫn cần cho transport và token. **SAML không phải cách xác thực trực tiếp mỗi TCP connection**. ZTNA products có thể dùng các giao thức đó ở lớp identity rồi cấp session/tunnel riêng.

### 8.3. OIDC Authorization Code + PKCE ở client có browser

Một flow minh họa:

~~~mermaid
sequenceDiagram
    participant U as User / browser
    participant C as Client / ZTNA gateway
    participant IDP as OIDC IdP
    participant POL as PDP
    participant APP as Protected app
    U->>C: Mở ứng dụng được bảo vệ
    C-->>U: Redirect sang IdP (state, PKCE, nonce khi áp dụng)
    U->>IDP: Login / MFA theo policy
    IDP-->>C: Authorization code qua redirect hợp lệ
    C->>IDP: Code exchange + PKCE verifier (và client auth nếu cần)
    IDP-->>C: Tokens/claims theo quyền được cấp
    C->>POL: Validated identity + device/context + resource
    POL-->>C: Allow/Deny/Step-up
    opt Allow
        C->>APP: Chỉ truy cập app được cấp
        APP-->>U: Response sau app AuthN/AuthZ
    end
~~~

Đây là **sơ đồ khái niệm**, không phải cấu hình OAuth/OIDC hoàn chỉnh. Khi triển khai thực:

- Xác thực **authorization code**, `state` để chống CSRF/login response confusion, PKCE và `nonce` khi OIDC flow yêu cầu.
- Kiểm tra ID token **signature, issuer (`iss`), audience (`aud`), expiration (`exp`), nonce và các claim cần thiết** theo OIDC.
- Với access token, resource server phải kiểm tra **token dành cho chính nó**, scope/permissions, expiry và trạng thái được chấp nhận; JWT hoặc opaque token có quy trình xác minh khác nhau.
- Không gửi access token vào URL query hoặc log và không coi raw `email` claim không có validation là danh tính đáng tin.
- Chọn redirect URIs cố định/được allowlist; tránh open redirects, token leakage và client secret trong ứng dụng public.

### 8.4. MFA chống phishing và rủi ro session hijack

MFA giảm nguy cơ account takeover nhưng **không luôn ngăn được token/cookie bị đánh cắp sau khi đăng nhập**. Adversary-in-the-middle có thể đánh cắp session artifacts khi phương án xác thực và app session handling yếu.

Các lớp phòng vệ bổ sung:

- Ưu tiên **phishing-resistant MFA** cho quyền nhạy cảm khi triển khai hỗ trợ.
- Giới hạn lifetime, kiểm tra session assurance và step-up với hành động nhạy cảm.
- Dùng cookie `Secure`, `HttpOnly`, `SameSite` phù hợp cho browser sessions; chống CSRF khi cần.
- Hạn chế token exposure, script injection, XSS, thông tin trình duyệt và local storage.
- Cân nhắc **proof-of-possession/device-bound** token hoặc mTLS-bound tokens nếu hệ sinh thái hỗ trợ và có cơ chế bảo vệ private key.
- Giám sát anomalous use và cho phép revoke sessions/tokens theo khả năng của nền tảng.

## 9. Device posture: tín hiệu bổ sung, không phải danh tính tự khai

Các tiêu chí posture thường có thể bao gồm:

| Tín hiệu | Mục tiêu | Giới hạn cần nhớ |
|---|---|---|
| Thiết bị enrolled vào MDM | Biết thiết bị được quản lý | Không có nghĩa user hiện tại đã được xác thực |
| EDR healthy / recent check-in | Giảm rủi ro endpoint bị chiếm quyền | Telemetry có thể trễ hoặc offline |
| Disk encryption enabled | Giảm lộ dữ liệu khi mất máy | Không chứng minh không có malware |
| OS patch level | Giảm rủi ro lỗ hổng đã biết | Không chứng minh không có zero-day |
| Screen lock / device key | Hạn chế sử dụng khi bỏ máy | Không thay user MFA khi cần |
| Device certificate / TPM key | Chứng minh possession của identity thiết bị | Nếu attacker điều khiển thiết bị, có thể vẫn dùng credentials tại chỗ |
| Jailbreak/root detection | Tín hiệu rủi ro đối với mobile client | Có khả năng bị bypass; không tin vô điều kiện |
| Managed browser / application | Hạn chế token/data exposure | Chỉ bảo vệ những đường thật đi qua browser/app được quản lý |

**Không tin posture do HTTP client gửi qua header tùy ý.** PDP nên lấy signal từ nguồn **đã xác thực và có integrity**, kèm thời điểm ghi nhận, trạng thái và độ tin cậy.

### 9.1. Thiết bị không quản lý (BYOD)

Một chính sách có thể cho BYOD truy cập **ứng dụng rủi ro thấp qua browser isolation/remote desktop hoặc session hạn chế**, nhưng không cho kết nối trực tiếp vào database hoặc môi trường production. Đây là **quyết định rủi ro tùy tổ chức**, không phải mọi ZTNA đều bắt buộc cài agent/MDM trên mọi thiết bị.

Nếu BYOD không thể cung cấp posture đáng tin, policy có thể yêu cầu **step-up, read-only access, session recording, data loss controls hoặc deny**, tùy dữ liệu và công cụ hỗ trợ.

### 9.2. Posture thay đổi trong phiên

Ví dụ MDM ghi nhận laptop từ "compliant" sang "non-compliant". Để phản ứng đúng:

1. Hệ thống phải **nhận được tín hiệu thay đổi** với độ trễ chấp nhận được.
2. PDP áp chính sách vào **session/resource đang liên quan**.
3. PEP thực thi **đóng phiên, giảm quyền hoặc yêu cầu reauth** theo khả năng.
4. Có **audit** về thời điểm đánh giá lại, hành vi áp dụng và user impact.

Một giải pháp chỉ kiểm tra posture **ở login** rồi bỏ qua 8 tiếng tiếp theo không nên được mô tả là "continuous verification" trọn vẹn.

## 10. Độ chính xác của policy: từ network access đến ứng dụng cụ thể

### 10.1. Mô hình policy có thể kiểm toán

Mỗi chính sách cần xác định rõ ít nhất năm nhóm dữ liệu:

~~~text
Policy decision = f(
  subject identity,
  target resource,
  requested action / session type,
  device and workload security posture,
  time/risk/assurance context
)

Kết quả:
  Allow + giới hạn cụ thể
  Deny + reason/category
  Step-up / Remediate + yêu cầu bổ sung
~~~

Không dùng công thức để suy rằng hệ thống có một **risk score chính xác tuyệt đối**. Mọi nguồn signal có độ tin cậy, độ mới và khả năng lỗi khác nhau; quyết định cần có policy version và owner.

### 10.2. Ví dụ policy matrix theo ứng dụng

| Principal | Resource | Điều kiện bổ sung | Quyết định dự kiến |
|---|---|---|---|
| Nhân viên kinh doanh | Orders portal | MFA phù hợp, account active | Allow đúng portal và quyền app |
| Nhân viên kinh doanh | DB production | Dù đã SSO/MFA | Deny nếu không có entitlement DB |
| DBA trực ca | DB production | Managed device, step-up, JIT approval | Allow phiên hạn chế thời gian/protocol |
| Nhà thầu | Dev wiki | Đang trong thời hạn hợp đồng, MFA | Allow ứng dụng đã duyệt |
| Nhà thầu | Admin console production | Không có quyền production | Deny |
| Workload `orders-api` | Payments API | Service identity được xác thực, scope phù hợp | Allow service-to-service theo policy |
| BYOD không có posture | Console chứa dữ liệu nhạy cảm | Không đạt posture | Deny hoặc dùng cách truy cập thay thế được phê duyệt |
| User đã bị disable | Mọi phiên mới | Account revoked | Deny; xử lý phiên đang hoạt động theo runbook |

**Mỗi dòng là một yêu cầu chính sách, không tự là cấu hình hệ thống.** Ứng dụng phải có object-level authorization ngay cả khi ZTNA cho user vào portal.

## 11. Một ví dụ end-to-end: cấp phiên truy cập quản trị

Giả sử nhân viên vận hành cần truy cập `admin.ops.example.test` qua HTTPS, còn SSH/RDP được mở theo kênh riêng. Hệ thống có:

- IdP liên kết directory với MFA/passkey.
- MDM/EDR cấp posture đã xác minh của thiết bị quản trị.
- PDP đánh giá quyền `production-admin`, sự kiện risk và yêu cầu JIT.
- PEP/gateway có đường riêng tới ứng dụng/host trong vùng quản trị.
- Ứng dụng tiếp tục kiểm tra vai trò, tài nguyên và audit.

### 11.1. Luồng quyết định

~~~mermaid
flowchart TD
    R["Yêu cầu phiên tới admin.ops.example.test"] --> A{"Identity được IdP xác minh?"}
    A -->|"Không"| DENY["Deny + audit"]
    A -->|"Có"| ENT{"Có entitlement/role cho resource này?"}
    ENT -->|"Không"| DENY
    ENT -->|"Có"| POS{"Device posture đạt yêu cầu?"}
    POS -->|"Không"| FIX["Remediation hoặc deny theo policy"]
    POS -->|"Có"| RISK{"Auth assurance / risk đạt mức?"}
    RISK -->|"Không"| MFA["Step-up MFA / JIT approval"]
    MFA --> RISK
    RISK -->|"Có"| G["PDP cấp session grant giới hạn"]
    G --> PEP["PEP cho đúng ứng dụng/protocol và giám sát"]
    PEP --> APP["Application AuthZ + audit"]
    APP --> RE["Đánh giá lại khi TTL / risk / revocation event"]
    RE -->|"Không còn quyền"| CLOSE["Cắt phiên / deny renew"]
~~~

Ở mỗi bước cần xác định **đâu là dữ liệu gốc được tin**. Ví dụ quyền production admin phải đến từ identity governance/PAM/approval đáng tin, không từ query parameter `role=admin` do người dùng tự gửi.

### 11.2. “Thành công” nghĩa là gì?

Không chỉ vì HTTP 200:

1. Gateway **không mở origin trực tiếp** trước khi có policy grant.
2. Session có **user principal, resource ID, device context và expiry** rõ.
3. Access path từ nguồn không được phép bị chặn **tại đúng PEP**.
4. Một principal hợp lệ nhưng sai role bị **deny**.
5. Tài khoản bị disable hoặc phiên hết hạn không thể tiếp tục tạo/renew quyền trái chính sách.
6. Ứng dụng vẫn từ chối hành động trái quyền dù phiên ZTNA hợp lệ.
7. Logs ghi đúng actor và quyết định, không ghi secrets/session tokens.

## 12. ZTNA khác VPN truyền thống thế nào?

| Trục so sánh | VPN theo mạng (cấu hình truyền thống) | ZTNA theo ứng dụng/session |
|---|---|---|
| Đối tượng mở quyền | Thường là tunnel/network routes/subnets | Một ứng dụng/service/resource theo policy |
| Tín hiệu trust | VPN auth, device cert, network ACL nếu có | Identity, entitlement, device/context, risk, session |
| Blast radius khi user bị chiếm | Phụ thuộc segmentation; có thể rộng khi route toàn subnet | Có thể hẹp hơn nếu per-app access và origin thật sự bị khóa |
| Xác minh trước truy cập | Trước VPN tunnel; ứng dụng có thể kiểm tra tiếp | Trước mỗi access session tới protected resource |
| Đánh giá lại | Tùy VPN/vendor và IAM tích hợp | Mục tiêu là continuous/adaptive, nhưng phải xác minh khả năng thực tế |
| Legacy protocols | Thường truyền IP/TCP/UDP rộng | Tùy vendor/client/connector hỗ trợ HTTP/TCP/SSH/RDP |
| App AuthZ | Vẫn phải có | Vẫn phải có |
| Monitoring | VPN sessions, firewall flows, app logs | Identity/resource/session decisions + network/app logs |

**VPN không tự là insecure**, và **ZTNA không tự là Zero Trust** nếu cấu hình:

- Cho mọi user toàn bộ application catalog.
- Không xác minh nguồn danh tính và device posture.
- Không cắt direct origin access.
- Không có least privilege hoặc app AuthZ.
- Không đánh giá lại khi role/account bị thu hồi.

ZTNA có thể dùng **VPN, overlay, mutual TLS hoặc tunnel** làm lớp transport bên dưới; điểm khác biệt nằm ở **quyết định quyền truy cập theo identity và resource**, không đơn thuần loại cổng hay giao thức.

## 13. Session tokens, cookie và khả năng thu hồi

**Điểm yếu sau authentication** là các session artifacts. Hệ thống có thể xác minh người dùng rất tốt lúc đầu nhưng vẫn bị session hijacking nếu token/cookie bị lộ và có thể tái sử dụng ở thiết bị khác.

### 13.1. Bearer token và proof-of-possession

| Loại credential | Cách chứng minh | Rủi ro / giới hạn |
|---|---|---|
| **Bearer access token** | Ai có token hợp lệ có thể sử dụng theo phạm vi token | Bị đánh cắp có thể replay cho tới khi token hết hạn/được revoke theo cơ chế |
| **Opaque session ID** | Server/gateway tra session state được lưu | Phải bảo vệ ID, kiểm tra expiration và revoke ở server |
| **Signed JWT access token** | Resource server kiểm tra signature/claims | Tự chứa thông tin; revoke tức thì không tự có nếu không thêm cơ chế |
| **mTLS-bound access token** | Token có ràng buộc với client certificate/key theo profile | Phải verify token binding và certificate ở resource server đúng cách |
| **DPoP-bound token** | Client chứng minh possession của key bằng DPoP proof cho request theo profile | Chống một số kiểu replay nhưng không cứu client bị compromise, cần kiểm tra proof và replay |
| **Browser cookie session** | Browser gửi cookie, server/gateway xác định phiên | Cần Secure/HttpOnly/SameSite, CSRF/XSS/session fixation protections |

**Không khẳng định có một token binding chuẩn duy nhất dùng cho mọi ZTNA product**. mTLS-bound tokens và DPoP có use cases/protocol requirements riêng; phải đánh giá client support, key protection, session resumption và giới hạn khi tích hợp.

### 13.2. JWT validation đúng không chỉ là giải mã Base64

Một gateway/resource server nhận JWT cần kiểm tra:

- Chữ ký theo **thuật toán được allowlist** và khóa từ issuer đáng tin; không chấp nhận `alg=none`.
- `iss`, `aud`, `exp`, `nbf` và claim policy theo giao thức.
- `kid`/JWKS lookup và key rotation an toàn; không lấy public key từ URL bất kỳ do token chỉ định.
- Quyền `scope`/`roles` có áp cho **đúng resource/action** không.
- Nếu token có `cnf` hoặc ràng buộc proof-of-possession, kiểm tra **bằng chứng possession thực tế**.
- Revocation/session state hoặc risk signal nếu kiến trúc yêu cầu từ chối sớm hơn `exp`.

**Đọc payload JWT** không phải hành động xác minh chữ ký. Một API chỉ decode claims rồi tin `role=admin` là lỗi authentication/authorization.

### 13.3. Revocation có thể chậm hơn kỳ vọng

Giả sử account bị disable lúc 14:05, nhưng API sử dụng JWT tự kiểm tra với thời hạn còn 30 phút. Nếu không có cơ chế nhận revoke event, introspection hoặc session denylist phù hợp, API có thể chấp nhận token cho tới khi hết hạn.

| Cơ chế | Ưu điểm | Điểm cần quản lý |
|---|---|---|
| Access token ngắn hạn | Giới hạn thời gian hữu ích khi token lộ | Phải có refresh/reauth an toàn |
| Server-side opaque session | Có thể thu hồi bằng session store | Cần HA, consistency, cache invalidation |
| Token introspection | Resource server có thể hỏi trạng thái hiện hành | Thêm dependency và cần timeout/cache policy |
| Revocation events / CAE-like integration | Có thể đẩy tín hiệu account/risk tới PEP | Không đảm bảo mọi app/connection lập tức ngắt nếu không tích hợp |
| Gateway terminate session | Cắt đường PEP tới app theo scope | Direct origin path hoặc phiên ngoài PEP có thể vẫn tồn tại |
| Credential/key rotation | Giới hạn reuse của credential bị lộ | Đòi hỏi rollout, handling active sessions và incident response |

**Mỗi phiên** phải có mô hình expiration/re-evaluation rõ. Khi nói "revoke ngay", cần xác minh bằng test thực: **đang mở WebSocket, SSH, RDP hoặc phiên DB dài hạn có thật sự bị đóng trong độ trễ mục tiêu không?**

### 13.4. Browser sessions: một số sai lầm thường gặp

Không:

- Đưa session ID/token vào URL query, Referer hoặc client logs.
- Coi một cookie còn tồn tại là đủ chứng minh account vẫn active.
- Dùng client-provided user/device headers như principal tin cậy.
- Tự động nâng quyền chỉ vì URL `/admin` hay vì request xuất phát từ IP doanh nghiệp.
- Cho refresh tokens tồn tại vô hạn không có rotation/reuse detection khi bối cảnh cần.

Nên thực thi **session regeneration** sau thay đổi mức xác thực, logout/timeout rõ, cookie attributes an toàn, CSRF protections phù hợp, app AuthZ từng request và những phương án tránh token xuất hiện trong các kênh không tin cậy.

## 14. Per-app access và bảo vệ origin: không chỉ là chính sách trên portal

Một nguy cơ nghiêm trọng là **đường truy cập bypass PEP**:

~~~mermaid
flowchart LR
    U["Untrusted client"] -->|"Identity & posture"| PEP["ZTNA gateway / PEP"]
    PEP -->|"Allow sau PDP decision"| APP["Private application"]
    U -.->|"Direct IP / old VPN route"| ORI["Origin listener"]
    ORI --> APP
    FW["Firewall / private ingress"] -.->|"Phải DENY bypass"| ORI
~~~

Nếu app còn một public IP/FQDN hoặc peering route mà caller có thể dùng để đi thẳng tới origin không qua PEP, việc PDP từ chối truy cập qua portal **không đủ**. Vì vậy:

1. Cần **private ingress/connector** hoặc firewall giới hạn origin chỉ nhận traffic từ nguồn/tunnel xác thực phù hợp.
2. Phân biệt **người dùng ↔ PEP** và **PEP ↔ origin**: cả hai hop phải bảo vệ TLS/identity theo thiết kế.
3. Không tự động trust mọi `X-Forwarded-User` từ client; origin chỉ tin **headers được PEP ghi đè qua kênh đã xác minh**, hoặc xác thực tokens/assertions theo thiết kế.
4. Các đường VPN legacy, DNS split-horizon, IPv6, direct LoadBalancer, admin SSH/RDP và cloud private endpoints phải được kiểm kê.
5. Kiểm thử **PEP deny nhưng origin vẫn reachable trực tiếp** là một negative test quan trọng.

### 14.1. DNS, SNI và TLS peer identity

ZTNA thường dựa vào hostname ứng dụng. Phải đảm bảo:

- DNS trả đích phù hợp từ **đúng mạng nguồn**; phân biệt resolver corporate, browser DoH, split DNS và public DNS.
- TLS certificate của **endpoint thực client gặp** hợp lệ cho hostname; không tắt certificate/hostname verification.
- Connector/gateway khi kết nối origin cũng xác thực server identity, không chỉ tin địa chỉ private IP.
- Nếu TLS kết thúc ở PEP, ứng dụng phía sau cần kênh **PEP → app** được bảo vệ và có metadata identity đáng tin.
- Nếu dùng passthrough/tunnel, policy ở lớp nào **thấy được HTTP request/user claims** cần được xác định rõ.

**Identity không thể thay TLS**, và private DNS/IP không tự chứng minh app chính là tài nguyên được người dùng yêu cầu.

### 14.2. SSH, RDP và non-HTTP applications

Không phải phiên ZTNA nào cũng là browser HTTPS. Với SSH/RDP/database client:

- PEP cần hỗ trợ **protocol và session establishment** tương ứng, có thể qua agent/tunnel hoặc bastion.
- Quyết định identity/posture có thể cấp quyền **một host/service:port**, không phải toàn bộ dải IP.
- SSH host key hoặc server certificate và RDP server authentication vẫn phải được xác minh.
- Account/role trên đích vẫn có quyền riêng; ZTNA allow không tự tạo tài khoản DB/SSH đúng quyền.
- Session recording/command restrictions, JIT/PAM hoặc step-up có thể được dùng với tài nguyên đặc quyền khi sản phẩm hỗ trợ.
- Thu hồi access **mới** và ngắt **phiên TCP lâu dài đã lập** là hai bài toán khác nhau; cả hai phải được thử.

### 14.3. Service-to-service identity không dùng MFA người dùng

Một backend microservice gọi một API khác không có người ngồi trước màn hình để nhập OTP. Trong trường hợp workload-to-workload:

- Dùng service account/workload identity/certificates và credential issuance/rotation.
- Có thể dùng mTLS (ví dụ service mesh/SPIFFE-related patterns) để xác minh peer.
- PDP/PEP hoặc service authorization engine đánh giá `workload principal → target service/action`.
- Không lưu static admin API key vô hạn vào image chỉ để "đăng nhập" mỗi phiên.
- Quyền dữ liệu của ứng dụng vẫn phải được kiểm tra độc lập.

Nguyên tắc **verify identity trước access** áp cho cả workload, nhưng **phương thức chứng thực phù hợp đối tượng** khác với user MFA.

## 15. Decision caching và hiệu năng: cân bằng với tính cập nhật

Nếu PDP phải gọi IdP, MDM, entitlement store và risk service **cho từng HTTP request** mà không có caching, độ trễ và phụ thuộc có thể rất cao. ZTNA có thể dùng session grants hoặc cached decisions trong thời hạn giới hạn.

| Chiến lược | Lợi ích | Rủi ro |
|---|---|---|
| Quyết định mới tại mỗi lần mở app | Rõ ràng theo resource, hạn chế trust mặc định | Có overhead auth/policy |
| Cached decision TTL ngắn | Giảm latency và tải PDP | Quyền thay đổi có thể chưa phản ánh ngay |
| PDP checks trên từng API request | Phản ứng nhanh hơn cho action rủi ro | Phụ thuộc availability và performance; không cần cho mọi action |
| Push revoke events | Giảm latency thu hồi nếu PEP nhận và enforce | Delivery/ordering/offline gaps |
| Session reauth theo rủi ro | Tập trung MFA khi cần | Risk signals có false positives/false negatives |
| Break-glass session | Duy trì vận hành trong khẩn cấp | Cần approval, scope nhỏ, TTL ngắn, audit đặc biệt |

### 15.1. Phiên dài và phiên ngắn đều có tradeoff

- **Phiên quá dài**: khi user đổi vai trò, rời tổ chức hoặc device compromise, quyền có thể còn hiệu lực lâu.
- **Phiên quá ngắn**: nhân viên phải tái kết nối liên tục; outage IdP/PDP có thể làm ngừng nghiệp vụ.
- **MFA nhắc quá thường xuyên**: tạo mệt mỏi, tăng khả năng người dùng phớt lờ prompt hoặc dùng cách làm yếu bảo mật.
- **Cache không có invalidate/revoke**: chính sách tưởng cập nhật ngay nhưng active sessions vẫn còn.

Không có một thông số TTL/MFA frequency phù hợp mọi tài nguyên. Dùng **risk tier**, UX/SLO, regulatory requirements và test độ trễ revoke thực tế.

### 15.2. Access session khác session ứng dụng

Một ZTNA access grant có thể hết hạn trong khi application vẫn còn cookie. Nếu PEP đóng đường, app session **không tự bị invalidate**, và ngược lại: app logout có thể không chấm dứt quyền mở tunnel. Cần policy nhất quán:

1. Khi logout, gateway và ứng dụng có cần revoke riêng không?
2. Khi user disable, những thành phần nào nhận sự kiện?
3. Khi app cookie bị đánh cắp, PEP có khả năng chặn request từ device không hợp lệ không?
4. Nếu ZTNA session còn hiệu lực, backend có thực thi authorization **mỗi request** không?

**Không suy hai session stores khác nhau chia sẻ revocation semantics chỉ vì cùng dùng IdP SSO.**

## 16. Telemetry: chứng minh một phiên đã được xác minh

Một bảng access log chỉ có `sourceIP` và `destinationIP` thường **không đủ** để xác minh ZTNA. Tối thiểu nên có:

| Nhóm | Trường gợi ý | Công dụng |
|---|---|---|
| **Identity** | Principal ID đã xác minh, auth method/assurance, IdP tenant | Phân biệt ai được cấp |
| **Device** | Device ID pseudonymous, posture status + timestamp | Kiểm tra device context |
| **Resource** | App/resource ID, protocol, hostname, approved port | Xác minh per-app scope |
| **Decision** | Allow/Deny/Step-up, reason category, policy ID/version | Giải thích quyết định |
| **Session** | Session ID không chứa bí mật, start/expiry/end reason | Correlate lifecycle |
| **Revocation** | Event type, event time, decision time, enforcement time | Đo độ trễ revoke thực |
| **Network** | Trusted peer/source, PEP/connector ID, origin path | Phát hiện bypass hoặc sai connector |
| **Application** | User role/tenant, API AuthZ result, request ID | Phân biệt gateway allow và app allow |
| **Risk** | Risk category/score đã chuẩn hóa, signal freshness | Điều tra step-up, posture drift |
| **Operations** | Policy deploy version, approver, change ticket | Truy vết policy drift |

### 16.1. Không ghi những gì?

- Raw passwords, passkeys/private keys, MFA one-time codes.
- OIDC authorization codes, ID/access/refresh tokens, session cookies.
- PII/device fingerprint chi tiết không cần thiết.
- Full request/response bodies chứa dữ liệu thanh toán, hồ sơ người dùng hoặc secrets.

Audit cần hạn chế quyền đọc, encryption at rest, retention và mục đích sử dụng theo quy định. Nếu cần điều tra lạm dụng, dùng **correlation ID và quyết định policy** thay vì lưu bearer tokens.

### 16.2. Đo độ trễ từ phát hiện đến enforce

Để đánh giá tuyên bố “continuous verification”, đo:

~~~text
T0: Thiết bị bị đánh dấu non-compliant ở EDR/MDM.
T1: PDP nhận được tín hiệu (hoặc lấy lại khi re-check).
T2: PDP ra quyết định mới (deny/restrict/re-auth).
T3: PEP áp policy và chặn/đóng access session.
T4: App xác nhận không có request ngoài quyền được phục vụ.

Độ trễ thực tế liên quan:
  T1 - T0: signal propagation
  T2 - T1: policy evaluation
  T3 - T2: enforcement / revocation
  T4 - T3: application session consistency
~~~

Không đo các mốc này trong thực tế thì không nên cam kết **thu hồi ngay lập tức**.

## 17. Threat modeling: 22 tình huống rủi ro

| ID | Nguy cơ | Kịch bản | Kiểm soát / bằng chứng |
|---|---|---|---|
| Z01 | **Tin network location** | Có VPN IP thì vào mọi app | Per-resource PDP/PEP, deny direct origin |
| Z02 | **SSO login bị coi là app authorization** | User có IdP account vào admin app | Entitlement/role checks cho từng tài nguyên |
| Z03 | **Token/cookie replay** | Attacker dùng session artifact đã lộ | Token storage, TTL, PoP binding nếu hỗ trợ, revoke |
| Z04 | **MFA phishing/fatigue** | User chấp nhận push lạ hoặc bị phishing OTP | Phishing-resistant MFA, risk signals và awareness |
| Z05 | **Device posture giả mạo** | Client gửi `X-Compliant: true` | Trusted MDM/EDR attestation, không tin headers |
| Z06 | **Device compliance quá cũ** | Máy mất EDR nhưng phiên vẫn kéo dài | Signal freshness, re-evaluation, expiry |
| Z07 | **Sai audience/issuer token** | Access token của app khác được chấp nhận | Issuer/audience/signature/scope validation |
| Z08 | **JWT đã bị revoke nhưng vẫn accepted** | Local verification chỉ xét signature/`exp` | Short TTL, introspection/revoke events |
| Z09 | **PEP bypass qua origin** | App còn public listener/direct VPN route | Firewall/private ingress, direct-path negative tests |
| Z10 | **Quyền theo nhóm quá rộng** | Nhân viên mới có toàn bộ app catalog | Least privilege, access review, JIT/PAM |
| Z11 | **Role change chưa cập nhật phiên** | User đổi phòng ban nhưng grant cũ còn | Entitlement sync, renewal/revoke policy |
| Z12 | **SSO/MFA nhưng app BOLA** | User được vào API và xem data tenant khác | Object-level application AuthZ |
| Z13 | **PEP tin client headers** | Request có `X-User: admin` vượt policy | Strip/overwrite headers, token verification |
| Z14 | **PDP/IdP outage xử lý fail-open** | Mất identity source rồi bypass auth | Approved degraded-mode, fail-closed với high-risk |
| Z15 | **Session không thực sự bị cắt** | Disable account nhưng SSH/RDP còn mở | Active-session revocation tests, connection termination |
| Z16 | **Rủi ro tích lũy từ service accounts** | Workload identity dùng token admin lâu dài | Short-lived workload identities, scoped permissions |
| Z17 | **Thiết bị hợp lệ nhưng bị malware** | EDR compliant ở T0, process bị compromise ở T1 | Endpoint protection, posture updates, app AuthZ, anomaly detection |
| Z18 | **DNS/TLS identity confusion** | PEP chuyển tới sai origin hoặc cert không được verify | Trusted DNS, TLS peer validation, app catalog mapping |
| Z19 | **ZTNA connector quyền quá lớn** | Một connector tiếp cận mọi subnet/tenant | Network segmentation, connector-specific allowlist |
| Z20 | **Multi-tenant app mapping sai** | Một identity vào app/tenant khác | Per-tenant resource IDs, app AuthZ, tests |
| Z21 | **Log lộ credential/session data** | Audit chứa raw cookie/token | Redaction, retention, RBAC, secret scanning |
| Z22 | **Policy drift/exception quên thu hồi** | Break-glass grant sống vô hạn | Config version, expiry, approvals, audit and cleanup |

### 17.1. Đặt ưu tiên theo blast radius

Một **người dùng có token bị đánh cắp** có thể bị giới hạn bởi scope của token, session expiry và device binding nếu được thực thi. Một **PDP/PEP admin bị chiếm quyền** có thể thay policy cho nhiều users/resources, tạo blast radius lớn hơn. Một **origin bypass** có thể làm vô hiệu cả hệ thống policy dù IdP vẫn hoạt động bình thường.

Ưu tiên bảo vệ **control plane và đường bắt buộc qua PEP**, đồng thời giới hạn identity/role và kiểm tra quyền của ứng dụng.

### 17.2. Ba câu hỏi khi mô hình hóa mỗi mối đe dọa

1. Đối thủ kiểm soát gì: **network, user credential, browser cookie, device, workload hay policy management**?
2. Quyết định allow xảy ra ở **IdP, PDP, PEP, gateway hay backend application**? Có đường bypass không?
3. Bằng chứng nào chứng minh **trước phiên**, **trong phiên** và **sau revoke** chính sách đã được áp?

Trả lời theo đường đi thực, không chỉ liệt kê tên sản phẩm như “ZTNA + MFA + EDR”.

## 18. Giám sát phiên và xử lý sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Cách khoanh vùng |
|---|---|---|
| User đăng nhập SSO thành công nhưng không vào app | Thiếu entitlement, PDP deny, posture không đạt | IdP event + PDP decision reason |
| Laptop compliant nhưng bị yêu cầu step-up | Resource risk tier, auth freshness hoặc risk signal | Policy ID, assurance, action yêu cầu |
| Gateway allow nhưng app trả 403 | Application authorization/tenant role | App logs, verified identity propagation |
| App đã bị đóng public path nhưng một client vẫn vào | Đường bypass khác, IPv6, VPN/peering cũ | Origin firewall/routing, source-specific tests |
| Mất IdP khiến user không vào được | Session renewal, IdP/PDP fail-closed, cache expiry | IdP health, decision cache, grant TTL |
| User đã bị disable nhưng SSH còn kết nối | Active-session termination chưa hoạt động | PEP revoke event, TCP session state |
| API báo invalid token | Issuer/audience/key rotation/expiry/clock skew | Token validation reason, JWKS/IdP config |
| Login loop liên tục | Redirect URI, SSO cookie, state/nonce, browser policy | OIDC logs, cookie/site rules |
| MFA prompts tăng bất thường | Password spray/MFA fatigue, reauth TTL quá ngắn | IdP risk, policy change, user reports |
| Chỉ BYOD gặp lỗi | Posture policy/agent requirements hoặc browser support | Device class, compliance decision |
| Chỉ một region truy cập app lỗi | Connector/backend/DNS/TLS certificate khác | PEP ID, region, certificate/route |
| Log không xác định ai đã được allow | Forwarded headers thiếu trust, audit config | Identity headers, token checks, PEP logs |
| Trang web vào được nhưng thao tác nhạy cảm fail | App-level step-up/transaction AuthZ | App decision logs |

### 18.1. Runbook revoke user hoặc credential bị lộ

1. Xác nhận principal/credential/session nào bị ảnh hưởng và phạm vi ứng dụng.
2. Khóa/giới hạn account theo quy trình IdP/IAM, thu hồi grants/tokens nơi nền tảng hỗ trợ.
3. Yêu cầu PDP/PEP **re-evaluate hoặc terminate active sessions**, không chỉ deny logins mới.
4. Kiểm tra mọi đường **direct origin/VPN/remote admin sessions** nằm ngoài ZTNA.
5. Rotate compromised tokens/certificates/keys; kiểm tra dấu hiệu lạm dụng ở ứng dụng và dữ liệu.
6. Ghi timeline từ **detection → policy decision → enforcement → backend denial**.
7. Khôi phục bằng quyền tối thiểu sau xác thực mới, kiểm tra thiết bị và kết thúc security incident.

**Không đăng xuất người dùng khỏi một ứng dụng rồi coi là đã thu hồi mọi phiên ZTNA, IdP và TCP/RDP khác.** Phải đối chiếu lifecycle từng hệ thống.

## 19. Policy-as-code minh họa: chỉ cấp đúng phiên cần thiết

Một doanh nghiệp có thể ghi lại yêu cầu bằng **mô hình chính sách độc lập sản phẩm** trước khi dịch thành cú pháp ZTNA vendor, IdP Conditional Access, gateway, PAM và ứng dụng.

~~~yaml
# PSEUDO-POLICY dành cho review thiết kế.
# KHÔNG phải schema triển khai được của một nhà cung cấp ZTNA.
protectedResource:
  id: orders-admin
  hostname: admin.ops.example.test
  protocol: HTTPS
  environment: production
  sensitivity: high

accessPolicy:
  defaultDecision: DENY
  subjects:
    allowedRoles:
      - oncall-operations
  authentication:
    trustedIssuer: corporate-idp
    requirePhishingResistantMfa: true
    requireRecentAuthentication: true
  device:
    requireManagedDevice: true
    requireTrustedDeviceIdentity: true
    requireFreshCompliantPosture: true
  context:
    denyDisabledAccounts: true
    stepUpOnElevatedRisk: true
    requireTimeBoundApprovalForPrivilegedActions: true
  session:
    scope: this-resource-only
    expiresAt: configured-by-risk-owner
    idleTimeout: configured-by-risk-owner
    evaluateOnNewSession: true
    reevaluateOnRiskOrPolicyChange: true
    terminateOnRevokeWhenSupported: true
  enforcement:
    requirePePOnEveryApprovedPath: true
    denyDirectOriginAccess: true
    verifyOriginTlsHostname: true
    stripUntrustedIdentityHeaders: true
  application:
    requireUserAndObjectAuthorization: true
    auditPrivilegedActions: true
  operations:
    logDecisionWithoutSecrets: true
    owner: security-platform
    exceptionRequiresApprovalAndExpiry: true
~~~

**Đọc đúng:**

- `requireRecentAuthentication: true` cần một **định nghĩa độ mới** cụ thể cho resource đó, không thể dùng nguyên boolean trên hệ thống thật.
- `requireManagedDevice` là lựa chọn chính sách với **tài nguyên nhạy cảm**; không phải mọi người dùng BYOD đều phải bị chặn mọi ứng dụng.
- `terminateOnRevokeWhenSupported` là **yêu cầu kiểm thử capability** của gateway/agent; không bảo đảm tự có.
- `expiresAt: configured-by-risk-owner` là placeholder cố ý để nhắc phải có TTL được phê duyệt. Không copy YAML này vào production.
- `denyDirectOriginAccess` phải được **firewall/route/connector policy hiện thực hóa**, không chỉ cấu hình trong portal.
- `requireUserAndObjectAuthorization` là yêu cầu với backend, không phải chức năng ZTNA tự áp cho từng bản ghi dữ liệu.

### 19.1. Ví dụ quyết định không chứa secret

~~~json
{
  "request": {
    "subject": "user-pseudonym-42",
    "resource": "orders-admin",
    "action": "open-access-session",
    "device": "managed-device-pseudonym-07"
  },
  "evidence": {
    "idpAuthenticated": true,
    "mfaAssurance": "phishing-resistant",
    "devicePosture": "compliant-and-fresh",
    "resourceEntitlement": true,
    "riskLevel": "normal"
  },
  "decision": {
    "result": "ALLOW",
    "scope": "orders-admin-only",
    "policyVersion": "reviewed-policy-v3",
    "sessionLifetime": "per-approved-policy"
  }
}
~~~

Đây là **dữ liệu minh họa**, không phải audit log thật. Không lưu raw access tokens, MFA proofs, device private keys hoặc session bearer IDs trong bản ghi quyết định.

### 19.2. Quyết định thiếu dữ liệu nên xử lý thế nào?

| Thiếu tín hiệu | Tài nguyên ít nhạy cảm | Tài nguyên đặc quyền |
|---|---|---|
| Không có device posture mới | Có thể yêu cầu remediation hoặc phiên giới hạn theo policy | Thường deny/require managed device theo rủi ro |
| IdP tạm không phản hồi | Session có TTL còn hợp lệ có thể tiếp tục theo phê duyệt | Không cấp grant mới nếu không xác minh được |
| Không có entitlement | Deny | Deny |
| Chưa xác minh origin certificate | Không tạo đường nguy hiểm, báo lỗi cấu hình | Fail closed và cảnh báo |
| Risk service trễ | Dùng chính sách xử lý signal freshness rõ | Không xem dữ liệu cũ là tình trạng tốt vô thời hạn |

Không có quy tắc một cỡ áp cho mọi tổ chức, nhưng **thiếu bằng chứng không được âm thầm biến thành allow mặc định** ở tài nguyên nhạy cảm.

## 20. Ma trận kiểm thử identity và session

Các trường hợp sau dùng **tài khoản, thiết bị và ứng dụng lab đã được chủ sở hữu cho phép**. Không thực hiện trên user production không có đồng ý hoặc cố tình chiếm đoạt session của người khác.

| ID | Tình huống | Kết quả mong muốn | Chứng cứ |
|---|---|---|---|
| P01 | User active, role đúng, MFA/posture đạt → orders portal | Cấp session vào đúng resource | IdP + PDP/PEP log, policy version |
| N01 | User không được xác thực | Không tạo session tới protected app | AuthN deny, không có access grant |
| N02 | User có SSO nhưng không có entitlement app | Deny theo resource | PDP deny reason, role mapping |
| N03 | User có entitlement nhưng tài khoản disabled | Không cấp phiên mới | IdP/account state và PEP result |
| N04 | User có role đúng nhưng posture không compliant | Deny/require remediation theo policy | MDM signal freshness + PDP action |
| P02 | User cần step-up và hoàn thành MFA hợp lệ | Chỉ cấp phiên sau step-up | Assurance/time evidence |
| N05 | Step-up bị hủy/hết hạn | Không cấp phiên | Session state + deny |
| N06 | BYOD vào production admin | Deny nếu policy yêu cầu managed device | Device class/posture decision |
| P03 | Nhà thầu còn hợp đồng → wiki được cấp | Allow riêng wiki | Contractor entitlement + grant |
| N07 | Nhà thầu đã được vào wiki thử vào DB production | Deny resource khác | Resource-scoped policy |
| N08 | User A được portal nhưng đọc order của user B | **Application AuthZ deny** | API/resource/tenant authorization |
| N09 | Client tự gửi `X-User: admin` hoặc `X-Compliant: true` | Không nâng identity/quyền | PEP sanitization, authenticated principal |
| P04 | Phiên hợp lệ trong TTL và risk bình thường | Duy trì theo policy, không ép login mỗi packet | Session lifecycle telemetry |
| N10 | Phiên đã hết TTL/inactivity | Reauth/deny renewal theo policy | Expiry decision, PEP enforcement |
| N11 | User bị disable khi đang có phiên WebSocket/SSH | Ngắt hoặc giới hạn trong độ trễ đã thiết kế | T0–T4 event-to-enforcement timeline |
| N12 | Posture chuyển sang non-compliant giữa phiên | Reevaluate và deny/restrict/step-up | MDM event, PDP decision, PEP action |
| N13 | Bearer token của app A gửi tới app B | Bị từ chối do `aud`/scope không đúng | Token validation reason |
| N14 | JWT không hợp lệ signature/issuer/expiry | Bị từ chối | Resource server validation |
| N15 | Token bị revoke khi còn thời hạn `exp` | Bị từ chối theo capability/latency đã cam kết | Introspection/events/denylist checks |
| P05 | mTLS/service identity hợp lệ → API được phép | Allowed service session | Peer certificate/identity, policy |
| N16 | Workload khác cùng trust domain nhưng không entitlement | Deny dù có certificate hợp lệ | Service AuthZ result |
| N17 | Client bypass PEP bằng origin FQDN/IP/old VPN route | Bị firewall/private ingress chặn | Origin/network deny + app health control |
| P06 | PEP kết nối origin hợp lệ với TLS peer validation | Kết nối thành công | Correct SNI/SAN/chain and connector path |
| N18 | Origin cung cấp certificate sai hostname | TLS bị từ chối, không `verify=false` | TLS peer verification error |
| N19 | IdP/PDP outage trong lab | Không cấp quyền mới trái policy; handling session cũ đúng TTL | Outage test + session metrics |
| P07 | Break-glass được phê duyệt | Chỉ resource/time/action đã duyệt | JIT approval, special audit |
| N20 | Break-glass hết hạn | Quyền được rút, không còn direct path | Revocation and gateway logs |
| P08 | User đăng xuất đúng | App/IdP/ZTNA session end theo policy thực tế | Separate session-store checks |
| N21 | Token/session data trong proxy logs | Không để lộ raw secrets | Redaction review |
| N22 | Tenant A truy cập portal của tenant B | Deny ngoài phạm vi entitlement | PDP + app tenant check |
| P09 | Policy canary thay đổi một resource | Quyền đúng không bị ảnh hưởng vùng khác | Decision IDs, config version, SLO |
| N23 | Device mất kết nối MDM quá lâu | Xử lý signal freshness theo policy | Posture age + decision |
| N24 | Một PEP khác vùng có policy cũ | Phát hiện drift và không mở đường trái policy | Gateway version / effective policy |

**Tính đúng của test phụ thuộc điểm kiểm tra.** Ví dụ:

- HTTP `403` của **ứng dụng** không chứng minh PEP đã chặn phiên.
- Timeout tới origin tắt không chứng minh firewall chặn direct access.
- Login MFA thành công không chứng minh tenant/resource authorization đã đúng.
- API token có signature hợp lệ không chứng minh token **dành cho API đó**.
- Việc account disable không cho login mới không chứng minh **phiên TCP cũ đã bị ngắt**.

### 20.1. Cách chứng minh negative test

Một negative test đáng tin phải có:

1. **Source đã biết:** user/device/workload test identity cụ thể, không dùng token của người khác.
2. **Destination khỏe mạnh:** một principal hợp lệ vào được cùng app từ đường hợp lệ.
3. **Policy rõ:** resource/action nào đáng lẽ deny, rule/decision ID nào chịu trách nhiệm.
4. **Quan sát tại enforcement point:** PEP/IdP/backend/firewall ghi đúng lý do; không chỉ nhìn timeout.
5. **Bằng chứng absence of bypass:** kiểm tra những đường ngoài PEP có liên quan theo phạm vi được phép.

## 21. Quan sát và xác minh cấu hình bằng thao tác an toàn

Lệnh quan sát chỉ nên chạy **trên endpoint và môi trường được phép**. Những ví dụ bên dưới không thay firewall, revoke account, ghi token hay mở cổng quản trị.

### 21.1. Quan sát DNS và route tại máy khách Windows

~~~powershell
# Chỉ đọc: xem interface, DNS và route.
Get-NetIPConfiguration
Get-DnsClientServerAddress
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric

# Địa chỉ ví dụ dùng TLD .test; chỉ có kết quả nếu lab cấu hình DNS.
Resolve-DnsName -Name "admin.ops.example.test" -Type A
Resolve-DnsName -Name "admin.ops.example.test" -Type AAAA
~~~

**Giới hạn:** DNS/route không chứng minh user đã được xác minh hoặc PEP đã thực thi AuthZ. Một DNS resolver có thể trả private IP cho ứng dụng mà **kết nối vẫn bị PEP/firewall từ chối**, hoặc app có một origin path khác cần kiểm soát.

### 21.2. Quan sát DNS/route ở Linux

~~~bash
# Chỉ đọc: địa chỉ, route và resolver đang được sử dụng.
ip -br address
ip -4 route show
ip -6 route show
ip rule show

# Có thể không trả kết quả nếu lab chưa có record.
getent ahostsv4 admin.ops.example.test
getent ahostsv6 admin.ops.example.test

# Chỉ khi hệ thống có systemd-resolved:
resolvectl status
~~~

Quan sát từ **máy khách thật đang cần truy cập** thay vì suy đường đi từ laptop của administrator; các VPN split-tunnel, per-process proxy, DNS-over-HTTPS và client agent có thể tạo sự khác biệt.

### 21.3. Kiểm tra TLS của endpoint lab

~~~bash
# Chỉ dùng với TLS server lab đã được phép kiểm tra và CA lab tin cậy.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername admin.ops.example.test \
  -verify_hostname admin.ops.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -brief
~~~

Lệnh này chỉ kiểm tra **TLS peer identity tại endpoint tương ứng trong lab**; nó **không thực thi PDP, MFA, Device Posture hoặc API authorization**. Một kết quả TLS PASS không chứng minh ZTNA session được cấp đúng.

Không dùng `openssl`, `curl -k` hoặc cấu hình `verify=false` để làm yếu TLS validation trong lúc debug.

### 21.4. Những bằng chứng cần đọc ở hệ thống ZTNA

Tùy nhà cung cấp và quyền được cấp, ưu tiên **read-only audit/console/API reports** cho:

- IdP sign-in event: principal, authentication assurance, time, risk signals.
- PDP effective policy: resource ID, decision và phiên bản rule.
- PEP session table: session state, start/expiry, enforcement outcome, connector ID.
- Device provider: device compliance assertion + timestamp.
- Application: AuthN/AuthZ user/resource log và service response.
- Network: origin firewall/connector flow và direct-path negative result.

Không cố suy một lệnh CLI chung cho tất cả ZTNA vendors: **cấu trúc policy, tên trạng thái và audit APIs khác nhau**. Lưu evidence theo checklist riêng của sản phẩm và tránh truy xuất raw credentials.

## 22. Lộ trình triển khai xác minh identity trước phiên

### Bước 1 — Xác định tài sản và rủi ro

Lập inventory ứng dụng nội bộ, HTTPS apps, SSH/RDP hosts, database consoles, cloud services, admin paths và các giao thức legacy. Phân loại mức nhạy cảm, chủ sở hữu, users, devices, dependencies và nhu cầu availability. Không bắt đầu từ thao tác mở portal cho mọi user.

### Bước 2 — Vẽ đường mạng và tìm lối đi tắt

Đánh dấu DNS, IP, VPN, firewall, load balancer, cloud private endpoint, ZTNA connector, PEP và backend. Tìm đường trực tiếp tới origin, IPv6, legacy VPN routes, peering/Internet fallback và app-specific proxies. Quyết định **điểm bắt buộc thực thi PEP**.

### Bước 3 — Chuẩn hóa danh tính và entitlement

Kết nối IdP/SSO, account lifecycle, groups/roles, MFA/passkeys, contractor status, service accounts, cloud identities và policies JIT/PAM. Review các group quá rộng và tài khoản dùng chung. Bảo đảm entitlement gắn **đúng resource/action**.

### Bước 4 — Thiết kế posture và signal freshness

Xác định ai có nguồn attestation tin cậy, MDM/EDR check-in interval, điều kiện cho managed/BYOD, xử lý signal missing/offline và thời hạn hiệu lực. Không dùng client-provided header làm kết luận compliance.

### Bước 5 — Viết policy theo tài nguyên

Mỗi rule ghi rõ `subject → resource → action`, authentication strength, posture, risk signals, TTL, idle timeout, step-up, revoke behavior và owner. Default deny khi không có entitlement; tránh allow cả mạng/subnet cho nhu cầu một ứng dụng.

### Bước 6 — Khóa direct-origin access

Tạo private ingress/connector, giới hạn firewall/route, TLS verify và identity propagation; kiểm tra backend không tin raw headers. Không đổi DNS sang private IP rồi tưởng đã chặn public access: phải test **public direct path** từ nguồn không được phép.

### Bước 7 — Pilot và test cả quyền lẫn phiên đang mở

Chọn nhóm users/devices, một app rủi ro thấp và một app có yêu cầu cao. Test MFA, role deny, posture fail, user disabled, session expiry, active WebSocket/SSH revoke, IdP outage, API AuthZ, direct origin, IPv4/IPv6 và nhiều PEP regions. Ghi **T0–T4** để đo revocation.

### Bước 8 — Rollout tăng dần và giám sát

Đo sign-in success, step-up rate, policy deny reasons, p95 login/access latency, user complaints, backend 403/5xx, connector health và những phiên còn ngoài ZTNA. Sửa policy hẹp đúng nguyên nhân thay vì bật allow-all.

### Bước 9 — Chuẩn bị break-glass và sự cố

Các tài khoản/đường emergency access phải được **phê duyệt, kiểm toán, scope tối thiểu và hết hạn tự động**. Có runbook khi IdP/PEP/MDM down, user bị compromise, token bị lộ, connector bị chiếm quyền hoặc app bị direct-origin exposure.

### Bước 10 — Rà soát liên tục

Khi user đổi vai trò, app đổi hostname/IP, thêm nhà thầu, thêm cloud region, đổi token TTL hoặc thay IdP, phải cập nhật policy/trust mapping, session handling, negative tests và telemetry. Remove những exceptions đã hết mục đích.

## 23. Bài tập tình huống: đăng nhập hợp lệ nhưng phiên truy cập vẫn sai

**Bối cảnh giả định:** doanh nghiệp có hai ứng dụng:

- `orders.portal.example.test`: cổng xem đơn hàng cho nhân viên kinh doanh.
- `admin.ops.example.test`: quản trị production, yêu cầu managed laptop và xác thực mạnh.

Nhân viên Alice đăng nhập IdP bằng MFA lúc 09:00. Lúc 09:05 Alice vào Orders Portal. Lúc 09:30 laptop bị MDM đánh dấu `non-compliant`, nhưng Alice vẫn có cookie SSO hợp lệ đến 17:00. Lúc 09:40 Alice mở Admin Console và nhận được HTTP 200. Đồng thời một nhà thầu không có quyền admin vẫn kết nối được tới origin qua route VPN cũ, bỏ qua ZTNA.

### 23.1. Phân tích theo từng bước

| Sự kiện | Quyết định đáng lẽ cần kiểm chứng | Điều đang thiếu |
|---|---|---|
| Alice đăng nhập IdP 09:00 | AuthN/MFA thành công | Chưa cấp mọi app entitlement |
| Alice mở Orders Portal 09:05 | PDP kiểm tra quyền vào app và session grant | Cần app AuthZ theo order/tenant |
| Laptop non-compliant 09:30 | MDM event → PDP → PEP re-evaluation | Có thể thiếu signal propagation/revoke |
| Alice vào Admin Console 09:40 | Resource-specific auth freshness, posture, entitlement/JIT | Login SSO cũ không đủ chứng minh compliance |
| Nhà thầu đi VPN route cũ | Origin firewall phải chặn bypass PEP | PEP không nằm trên mọi đường tới app |

### 23.2. Câu hỏi

1. Vì sao **SSO session còn hạn** không đồng nghĩa Alice được phép vào Admin Console?
2. Phân biệt **AuthN**, **ZTNA per-resource AuthZ** và **application transaction AuthZ** ở ví dụ.
3. Nếu MDM event đến muộn, hệ thống có thể làm gì để giảm rủi ro?
4. HTTP 200 chứng minh PEP và device posture đều đã chấp thuận hay chưa?
5. Nếu Alice có phiên SSH đang mở vào production trước lúc non-compliant, cần test thêm gì?
6. Làm thế nào ngăn nhà thầu gọi trực tiếp origin qua VPN route cũ?
7. Tại sao chỉ chuyển DNS sang private IP chưa phải biện pháp chặn public/direct access?
8. Đề xuất ít nhất bốn negative tests và ba positive tests, có bằng chứng cụ thể.
9. Nếu IdP outage, xử lý phiên Admin Console cũ và cấp phiên mới theo policy nào?
10. Khi một user rời tổ chức, quyền nào cần revoke ở **IdP, PDP/PEP, ứng dụng và tài khoản host/DB**?

### 23.3. Gợi ý lời giải

- Cần **resource-specific policy** cho Admin Console: role admin/JIT, auth assurance đủ mới, managed device compliance và risk context; không suy từ một cookie SSO cũ.
- MDM compliance signal cần có timestamp/freshness và trigger re-evaluation; nếu thiếu signal, áp chính sách degraded state thay vì "assume compliant forever".
- HTTP 200 có thể là trang login, một phản hồi gateway, cache hoặc ứng dụng; không tự chứng minh **ai được allow vì sao**.
- SSH/RDP/WebSocket là long-lived sessions: cần test actual connection termination, không chỉ deny reconnect.
- Origin network chỉ được nhận kết nối từ connector/gateway được phê duyệt và phải có TLS/identity phù hợp; kiểm tra legacy VPN route, IPv6 và mọi listener.
- App AuthZ vẫn phải kiểm tra quyền trên từng đơn hàng hoặc hành động quản trị; ZTNA chỉ hạn chế đường vào đúng resource.
- Với IdP outage, không mở quyền mới trái policy; xử lý cached sessions dựa TTL và security tier, có runbook break-glass và audit.
- Positive: nhân viên có quyền xem đúng Orders Portal; DBA được cấp JIT vào console từ managed laptop; ứng dụng hợp lệ truy cập tài nguyên cần thiết. Negative: nhà thầu qua VPN bypass bị deny; Alice non-compliant bị step-up/deny theo chính sách; user đã disable không renew; user của tenant khác bị app deny.

## 24. Checklist xác minh identity trước mỗi phiên truy cập

- [ ] Có inventory các ứng dụng, service, SSH/RDP/DB endpoints, độ nhạy dữ liệu và chủ sở hữu.
- [ ] Phân biệt IdP login session, ZTNA access session, application session, TLS session và TCP connection.
- [ ] Không hiểu "xác minh mỗi phiên" thành MFA mỗi packet hoặc mặc định MFA cho từng HTTP request.
- [ ] Có nguồn danh tính IdP/workload đáng tin, kiểm tra account active và lifecycle.
- [ ] Có xác thực mạnh phù hợp mức rủi ro (ưu tiên phishing-resistant MFA ở tài nguyên nhạy cảm).
- [ ] Cấu hình OIDC/SAML/OAuth đúng: issuer, audience, signature, expiration, scopes, redirects và token handling.
- [ ] Không dùng ID token sai mục đích thay access token hoặc tin JWT chỉ vì decode được payload.
- [ ] Bảo vệ bearer tokens, cookies, refresh tokens, session IDs và client private keys.
- [ ] Khi cần token binding/PoP, kiểm tra cả chứng cứ possession và support của client/resource server.
- [ ] Quyền per-resource/per-action được đánh giá riêng trước cấp phiên, không chỉ dựa VPN IP/SSO login.
- [ ] Policy áp least privilege cho user, nhà thầu, tài khoản đặc quyền và workload identities.
- [ ] Device posture lấy từ MDM/EDR/attestation đáng tin, có timestamp/freshness và handling missing signals.
- [ ] Có chính sách BYOD riêng, không mặc định cấp production admin access từ unmanaged device.
- [ ] PDP/PEP/connector được bảo vệ bằng IAM/RBAC, TLS, audit, HA và change approvals.
- [ ] PEP nằm trên mọi đường được phép tới protected app; origin IP/VPN/IPv6/public bypass bị chặn.
- [ ] Origin certificate/hostname được xác minh đúng; không bỏ TLS verification khi đổi routing.
- [ ] PEP không tin headers user/role/device tự gửi; app chỉ chấp nhận identity assertion được xác thực.
- [ ] Session có TTL, idle timeout, resource scope, risk/assurance và policy version rõ.
- [ ] Có chính sách re-evaluation khi renew, privilege change, risk/posture drift và IdP revoke events.
- [ ] Đã kiểm thử revoke **phiên đang mở** (WebSocket/SSH/RDP/DB khi phù hợp), không chỉ new logins.
- [ ] Đã đo độ trễ từ signal → PDP decision → PEP enforcement → backend denial.
- [ ] Không hứa real-time revocation nếu gateway, token validation hoặc application session không hỗ trợ.
- [ ] Ứng dụng tiếp tục user/tenant/object authorization theo mỗi hành động cần bảo vệ.
- [ ] Có positive/negative tests theo account, role, device, origin bypass, token audience và session lifecycle.
- [ ] Logs có identity/resource/decision/policy/session correlation nhưng không lộ token/cookie/PII.
- [ ] Có degraded-mode policy rõ khi IdP, PDP, posture source hoặc connector unavailable.
- [ ] Break-glass/JIT privileges có approval, scope nhỏ, TTL, audit và tự kết thúc.
- [ ] Rollout theo canary, có rollback không mở lại toàn bộ subnet hoặc bỏ MFA/verification.
- [ ] Rà soát entitlement, app catalog, device posture, policy drift và exceptions định kỳ.

**Ghi nhớ:** **Xác minh identity trước mỗi phiên truy cập** nghĩa là **không cấp đường đến một tài nguyên chỉ vì một chủ thể đã đăng nhập hoặc nằm trong mạng được tin trước đó**. ZTNA cần quyết định theo **identity đã xác minh, entitlement cho đúng tài nguyên, posture/ngữ cảnh đủ mới và policy có hiệu lực tại thời điểm cấp quyền**; tiếp tục quản lý **thời lượng, đánh giá lại và thu hồi** khi điều kiện thay đổi. Các lớp **TLS, firewall, segmentation, IAM, application authorization và audit** vẫn thiết yếu. Một phiên được cấp đúng lúc ban đầu nhưng không thể kiểm soát sau khi account, thiết bị hay rủi ro thay đổi **chưa đáp ứng mục tiêu Zero Trust một cách đầy đủ**.
