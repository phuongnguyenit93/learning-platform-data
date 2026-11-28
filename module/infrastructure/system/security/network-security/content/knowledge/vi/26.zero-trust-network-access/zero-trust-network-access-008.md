# Context-aware policy theo người dùng và workload

> **Chương:** Zero Trust Network Access  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, TLS/mTLS, API gateway, Kubernetes và bảo mật hạ tầng cloud.  
> **Trọng tâm:** Thiết kế và thực thi chính sách truy cập theo **danh tính người dùng**, **danh tính workload**, **tình trạng thiết bị**, **độ nhạy tài nguyên**, **ngữ cảnh phiên**, **mức rủi ro** và **thời gian**, với đánh giá tín hiệu đáng tin, giới hạn quyền và điều chỉnh khi ngữ cảnh thay đổi.

## 1. Context-aware policy trong Zero Trust là gì?

Một mô hình kiểm soát mạng truyền thống có thể coi người dùng "đã vào VPN" hoặc máy có IP nội bộ là đáng tin để truy cập hàng loạt hệ thống. Trong cloud, hybrid work và microservices, điều này không còn đủ: laptop có thể mất bản vá, credential có thể bị đánh cắp, một workload bị xâm nhập có thể đứng cùng subnet với dịch vụ nhạy cảm, và một IP có thể thuộc hàng nghìn người qua NAT.

**Context-aware policy** là chính sách đưa ra quyết định **cho phép, từ chối hoặc yêu cầu điều kiện bổ sung** bằng nhiều tín hiệu được xác minh tại thời điểm truy cập và, khi có khả năng, trong suốt vòng đời phiên. Một quyết định không chỉ hỏi *ai đang gọi*, mà còn hỏi:

- **Chủ thể nào?** Người dùng đã xác thực, service account, workload SPIFFE ID, đối tác, automation?
- **Tác vụ nào?** Đọc báo cáo, sửa cấu hình firewall, gọi API thanh toán, truy vấn dữ liệu?
- **Tài nguyên nào?** API cụ thể, ứng dụng nội bộ, database, namespace hay đối tượng tenant?
- **Thiết bị và workload ở trạng thái nào?** Managed, posture hợp lệ, image/provenance phù hợp, phiên chứng thư còn hiệu lực?
- **Điều kiện hiện tại?** MFA còn mới, ca trực, thiết bị vừa phát hiện nguy cơ, zone/connector, mức risk, thay đổi quyền?
- **Quyền nào là tối thiểu?** Read-only, endpoint cụ thể, port và thời hạn xác định.
- **Có thể tiếp tục được không?** Khi phiên đổi risk, posture stale hoặc quyền bị thu hồi, enforcement point có đánh giá lại và cắt phiên được không?

**Zero Trust** không có nghĩa "không bao giờ tin ai" mà là **không mặc định tin một principal chỉ vì vị trí trong mạng**. Mỗi quyền truy cập phải được xác thực và ủy quyền theo đúng ngữ cảnh, với giới hạn rõ ràng. Mô hình kiến trúc Zero Trust được mô tả trong **NIST SP 800-207**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **context-aware policy, RBAC, ABAC, PBAC, network allowlist, ZTNA và VPN**.
2. Chỉ ra vai trò của **Policy Enforcement Point (PEP), Policy Decision Point (PDP), Policy Engine và Policy Administrator**, cũng như các nguồn thông tin thuộc tính.
3. Kết hợp chính xác **user identity + workload identity + device posture + resource/action + risk + signal freshness**.
4. Phân biệt **tín hiệu đã xác minh** với IP, HTTP header và claims do client tự khai.
5. Thiết kế **least-privilege access** cho ứng dụng web, API, SSH/RDP, database, partner và service-to-service.
6. Áp dụng **step-up MFA, JIT, short-lived credentials, continuous/periodic re-evaluation và revocation** đúng giới hạn kỹ thuật.
7. Viết **policy-as-code minh họa**, hợp đồng decision JSON và truy vấn kiểm tra có cấu trúc.
8. Xây ma trận **ALLOW / DENY / STEP_UP / REVOKE** và xử lý sự cố khi ngữ cảnh bị mất hoặc sai.
9. Kết hợp **ZTNA với TLS/mTLS, CNI NetworkPolicy, firewall, DNS, WAF, IAM và SIEM** mà không mở đường bypass.

## 2. Ba nguyên tắc Zero Trust chi phối quyết định

Theo cách diễn đạt của NIST SP 800-207, Zero Trust nhấn mạnh ba nguyên tắc vận hành sau:

| Nguyên tắc | Trong context-aware policy | Ví dụ |
|---|---|---|
| **Verify explicitly** | Xác minh identity, thiết bị, trust domain, resource và signal provenance | Không tin "device_compliant=true" do browser tự gửi |
| **Least-privilege access** | Cấp phạm vi thao tác, ứng dụng và thời gian tối thiểu | Kế toán chỉ đọc /finance/report trong ca làm việc |
| **Assume breach** | Thiết kế ngăn lateral movement, giám sát và có thể thu hồi | Laptop được cấp quyền bị EDR báo compromise → chặn phiên nhạy cảm |

**Không có một sản phẩm duy nhất tự biến hệ thống thành Zero Trust.** Một ZTNA gateway có thể bảo vệ truy cập nhân viên từ xa, nhưng **quyền của backend, workload mTLS, DNS, route, cloud IAM và data store** vẫn phải được kiểm soát.

### 2.1. Tại sao "đã đăng nhập" không phải quyết định cuối?

Một user có thể đăng nhập khi thiết bị hợp lệ, nhưng 15 phút sau EDR phát hiện malware, quản trị viên thu hồi role hoặc API chuyển vào chế độ maintenance. Chính sách cần định nghĩa **khi nào lấy lại tín hiệu**, cách xử lý phiên hiện có và có cần **step-up** hay không.

### 2.2. Vì sao "ở trong văn phòng" không đồng nghĩa an toàn?

Kết nối qua office VLAN, VPN hoặc VPC private chỉ nói về **network reachability**. Một máy nhiễm mã độc trong LAN vẫn phải chịu **identity, device, action và resource authorization** như máy ở nơi khác.

## 3. Kiến trúc tham chiếu: từ yêu cầu tới quyết định

~~~mermaid
flowchart TB
    U[Human user + Managed or BYOD device] --> C[ZTNA client / Browser]
    C --> PEP[PEP: ZTNA Gateway / Proxy]
    W[Workload / CI / ServiceAccount] --> M[Service Mesh / API Gateway PEP]
    PEP --> PDP[PDP / Policy Engine]
    M --> PDP
    IDP[IdP / SSO / MFA / Roles] -. Verified user claims .-> PIP[PIP / Context Providers]
    UEM[MDM / EDR / Device inventory] -. Posture / managed state .-> PIP
    WI[Workload Identity / SPIFFE / Cloud IAM] -. Verified workload claims .-> PIP
    RES[Resource catalog / data classification] -. Resource and action .-> PIP
    RIS[Risk engine / threat intelligence] -. Risk and anomaly signals .-> PIP
    PIP --> PDP
    PDP --> PA[Policy Administrator / Session control]
    PA --> PEP
    PA --> M
    PEP --> A[Private application]
    M --> B[Internal API / Sensitive service]
    PEP -. Access decisions .-> SIEM[SIEM / Audit / Detection]
    M -. Peer / policy decisions .-> SIEM
    PDP -. Policy version / reason .-> SIEM
~~~

**Giải thích:**

- **PEP (Policy Enforcement Point):** chặn/cho phép traffic hoặc request thực tế. Có thể là identity-aware reverse proxy, ZTNA connector/gateway, API gateway, service mesh proxy, cloud identity-aware service hoặc application middleware.
- **PDP (Policy Decision Point):** điểm trả quyết định dựa trên policy và context; trong kiến trúc NIST, logic **Policy Engine (PE)** tính toán quyết định và **Policy Administrator (PA)** thiết lập/ngắt communication path. Một sản phẩm có thể gộp các chức năng này; sơ đồ chỉ là logic.
- **PIP (Policy Information Point):** khái niệm thường dùng trong hệ thống policy/ABAC để chỉ **nguồn thuộc tính** như IdP, MDM, EDR, asset inventory, risk engine. Đây là cách gọi trong bài, **không phải thực thể bắt buộc tách riêng trong mọi triển khai NIST**.
- **Resource:** đối tượng được bảo vệ. Phạm vi phải nhỏ hơn "cả mạng production" khi có thể.
- **Telemetry:** ghi nhận request, identity đã xác minh, signal age, policy version và kết quả, không lưu credential.

### 3.1. PEP phải nằm trên đường traffic thực

Một policy có thể rất chặt ở PDP nhưng **không có tác dụng nếu client có đường vào trực tiếp tới backend**. Cần đảm bảo app không thể bị truy cập qua **public origin, NodePort, VPN route, secondary LB, private endpoint ngoài policy hoặc service mesh bypass**.

### 3.2. Decision plane không thay data plane

PDP có thể trả **DENY**, nhưng PEP phải thực sự **không forward request, từ chối kết nối hoặc ngắt session**. Cần kiểm tra **cả policy decision và hành vi mạng thực tế**; không đánh giá bảo mật chỉ bằng dashboard quyết định.

## 4. Những tín hiệu ngữ cảnh cần thu thập

| Nhóm thuộc tính | Ví dụ | Nguồn đáng tin | Lưu ý |
|---|---|---|---|
| **Human identity** | User ID, group/role, account status | IdP/IAM đã xác thực | Email hiển thị không nên là khóa định danh duy nhất |
| **Authentication strength** | MFA, phishing-resistant auth, auth_time | IdP claims/protocols có chữ ký | MFA thành công từ hôm qua có thể không đủ cho thao tác nhạy cảm |
| **Session** | Session ID, age, issued_at, revocation state | Auth/session service | Token hợp lệ không bảo đảm quyền chưa đổi |
| **Device** | Managed, compliant, encryption, EDR health | MDM/UEM/EDR đã liên kết device identity | BYOD không mặc định có cùng độ tin cậy với managed |
| **Workload** | SPIFFE ID, Kubernetes ServiceAccount, cloud role | mTLS, identity federation, trusted workload attestation | Không tin X-Service-Name header |
| **Runtime** | Image provenance, attested cluster/namespace, workload posture | Admission/attestation/control plane | Một Pod label có thể bị sửa bởi actor có quyền |
| **Resource** | App ID, route, service owner, classification | Catalog/API router/CMDB | Không lấy "classification" do client khai |
| **Action** | Read, export, delete, admin SSH, API method | Server/router/protocol aware PEP | TCP tunnel không biết ý nghĩa SQL câu lệnh |
| **Network** | Trusted proxy peer, VPN/connector route, zone | PEP/network telemetry | IP/GeoIP chỉ bổ sung, không chứng minh user |
| **Risk** | Sign-in anomaly, EDR alert, account threat level | Risk service có nguồn và thời hạn | Score biến đổi, cần quy định cách xử lý stale/missing |
| **Time** | Request time, change window, shift/on-call | Server clock và workflow approval | Không dùng đồng hồ client tự gửi |
| **Business context** | Tenant, owner, approved ticket, JIT grant | Backend/IAM/ticket system có kiểm chứng | Claim tự khai không phải approval |
| **Policy state** | Policy version, exception expiry, resource ACL | Policy repository/PDP | Tránh cache quyết định sau khi revoke |

### 4.1. Không nên thu mọi tín hiệu chỉ vì có thể

Thu thập đúng **mục đích, mức độ nhạy cảm, retention và quyền xử lý**. Dữ liệu định vị, trạng thái sức khỏe thiết bị và hành vi người dùng có thể nhạy cảm; không biến Zero Trust thành **giám sát không cần thiết**. Nhiều quyết định chỉ cần verified identity, managed-device assertion, application classification và session freshness.

### 4.2. Phân biệt signal và kết luận

**EDR alert=high risk** có thể cần cách ly phiên nhạy cảm; **địa chỉ IP ở một quốc gia** không tự chứng minh user xấu. Dùng tín hiệu rủi ro để **tăng độ chắc chắn**, có false-positive workflow và review nguồn tín hiệu.

## 5. Độ tin cậy của context: provenance, freshness, integrity

Một thuộc tính như **device.compliant=true** chỉ hữu ích nếu PDP biết **ai chứng thực, lúc nào, cho thiết bị nào**.

~~~json
{
  "attribute": "device_posture",
  "value": "compliant",
  "device_id": "managed-device-demo-29",
  "subject_binding": "verified-user-session-17",
  "issuer": "approved-mdm",
  "asserted_at": "2026-11-28T10:00:00Z",
  "expires_at": "2026-11-28T10:05:00Z",
  "verification": "trusted-server-to-server-or-validated-assertion",
  "confidence": "high"
}
~~~

Đây là **schema minh họa**, không phải định dạng MDM nào bắt buộc hỗ trợ. PDP phải xác minh **issuer, binding, timestamp, expiration và tính toàn vẹn**; không lấy một JSON do client gửi làm bằng chứng.

### 5.1. Thuộc tính có thể đúng nhưng đã cũ

- Laptop báo compliant lúc 9:00 nhưng EDR offline lúc 9:05.
- IdP JWT chứa group **finance-admin** nhưng group đã được thu hồi giữa phiên.
- Workload mTLS certificate còn hiệu lực nhưng Pod đã bị quarantine.
- Policy cache còn ALLOW sau khi resource chuyển từ **internal** sang **restricted**.

Cần **maximum age, revalidation trigger, cache TTL và revocation propagation** theo mức độ nhạy cảm. Không định nghĩa "continuous" như lời hứa đánh giá lại mọi packet từng mili giây.

### 5.2. Missing không phải compliant

Nếu PDP không lấy được tín hiệu critical, không được mặc định điền **compliant=true**. Tách các trạng thái:

- **VERIFIED_COMPLIANT:** chứng cứ hợp lệ, chưa hết hạn.
- **VERIFIED_NONCOMPLIANT:** chứng cứ còn mới và không đạt điều kiện.
- **UNKNOWN:** chưa có chứng cứ, không đăng ký hoặc ràng buộc không chắc.
- **STALE:** chứng cứ từng hợp lệ nhưng vượt thời gian được dùng.
- **ERROR:** PIP/MDM/EDR không khả dụng hoặc xác minh chữ ký lỗi.

Quyết định phải có mapping rõ **DENY, STEP_UP, READ_ONLY, REMEDIATION hoặc bounded exception** theo risk. Không cho thiết bị chưa biết thực hiện admin action chỉ vì MDM đang down.

### 5.3. Thuộc tính từ HTTP header là dữ liệu không đáng tin nếu không được bảo vệ

Các giá trị như **X-User, X-Device-Compliance, X-Forwarded-For, X-Workload-ID, X-Risk-Score** có thể do client tự tạo. Chỉ dùng khi **trusted ingress loại bỏ/ghi đè untrusted headers**, truyền qua mTLS hoặc kênh ký/xác thực và backend không thể bị gọi bỏ qua ingress. Xác thực header **nguồn gốc** khác với việc chỉ kiểm tra cú pháp.

## 6. User identity: xác thực danh tính người dùng đáng tin

Trong ZTNA workforce, IdP có thể hỗ trợ **OIDC/SAML, MFA, FIDO2/WebAuthn, device binding và access lifecycle**. PEP/PDP phải phân biệt **user đã xác thực** với các claims không được kiểm chứng.

### 6.1. Những trường user cần thiết

- **Stable subject ID** theo đúng issuer/tenant; display name/email có thể đổi.
- **Account enabled/locked/revoked** hoặc phiên/token đã bị vô hiệu.
- **Group/role/scope** đã được phân quyền cho ứng dụng, không chỉ thuộc nhóm tổ chức chung.
- **Authentication time và method/assurance** theo IdP.
- **MFA freshness/step-up status** cho thao tác rủi ro cao.
- **Delegation/contractor status, owner và expiration** khi liên quan.
- **Current risk** từ nguồn đáng tin, có timestamp và confidence.

### 6.2. Ứng dụng không được tin token dành cho hệ khác

OIDC **ID token** được thiết kế cho client authentication context, trong khi API cần **access token** được cấp cho đúng resource/audience theo profile triển khai. Không chấp nhận token **có chữ ký hợp lệ nhưng issuer/audience/type sai**. Với opaque tokens, gateway/backend có thể dùng introspection; với JWT, cần xác minh signature/claims/algorithm/token profile và cache/revocation policy.

### 6.3. MFA không thay kiểm tra quyền

MFA chứng minh một authentication event mạnh hơn. Nó **không cấp quyền sửa route production** cho người không có role, và không thay phê duyệt change. Truy cập nhạy cảm nên cần **cả quyền, ngữ cảnh, MFA freshness và approval/JIT** theo policy.

### 6.4. Người dùng và phiên quyền thay đổi

Nếu user rời nhóm finance hoặc nghỉ việc, PDP nên xử lý **session validity và group revocation** theo khả năng đồng bộ IdP/event/reauth. JWT còn hạn không tự phản ánh permission được gỡ ngay. Thiết kế **short-lived sessions, token expiry, policy recheck hoặc revocation signal** với mục tiêu độ trễ thu hồi được đo.

## 7. Device context: thiết bị là một tín hiệu, không phải danh tính người dùng

Một máy laptop có thể được quản lý bằng MDM/UEM và giám sát EDR. Các tín hiệu thường được kiểm tra gồm:

| Posture signal | Ý nghĩa | Điều không nên suy ra |
|---|---|---|
| **MDM enrolled/managed** | Thiết bị thuộc tập quản trị được xác minh | Không đảm bảo không có malware |
| **Disk encryption** | Dữ liệu lưu trữ có bảo vệ theo policy | Không ngăn mọi credential theft |
| **OS patch level** | Đạt baseline cập nhật | Không chứng minh không có zero-day |
| **EDR running/healthy** | Agent báo trạng thái hoạt động và telemetry | Không tự là "an toàn tuyệt đối" |
| **Screen lock / secure boot** | Giảm một số rủi ro vật lý/boot | Không thay user AuthN |
| **Device certificate/key** | Có credential gắn với thiết bị | Có thể bị mất/quản lý sai; cần binding |
| **Attestation/TPM support** | Có thể chứng minh một số thuộc tính nền tảng | Khả năng phụ thuộc OS/hardware và implementation |
| **Last check time** | Tín hiệu còn mới bao lâu | Dữ liệu stale không phải compliant |
| **Threat severity** | Cảnh báo high-risk có thể kích quarantine | False positives phải được xử lý |

### 7.1. Liên kết device với đúng session

Một attacker có thể dùng token user trên một thiết bị khác. PDP không thể lấy MDM status của laptop được đăng ký rồi **gán trạng thái compliant đó cho mọi phiên cùng user**. Cần **device/session binding** dựa trên cơ chế được hỗ trợ: device-bound credential, validated posture assertion hoặc trusted agent/PEP context.

### 7.2. BYOD: tránh lựa chọn trắng/đen thiếu kiểm soát

Nếu chính sách cho phép thiết bị cá nhân:

- Có thể cấp **web-only, browser isolation hoặc read-only** cho tài nguyên ít nhạy cảm.
- Tài nguyên restricted có thể yêu cầu **managed device** hoặc giải pháp desktop/app được cách ly phù hợp.
- Không yêu cầu cài agent giám sát vượt nhu cầu đối với ứng dụng không nhạy cảm nếu không có lý do và quy định phù hợp.
- Với dữ liệu nhạy cảm, **watermark/DLP/download restriction** chỉ có hiệu lực nếu application/PEP thực thi, không phải một chuỗi policy tự tạo.

**Device compliant không tự cấp quyền ứng dụng**; một thiết bị tốt vẫn có thể đăng nhập bằng tài khoản không đủ quyền.

## 8. Workload identity: service và automation cũng là chủ thể

Zero Trust không chỉ dành cho người dùng nhân sự. **Service-to-service, CI/CD jobs, Kubernetes Pods, VMs, serverless functions và máy tích hợp đối tác** đều cần identity có thể xác minh.

### 8.1. Các nguồn identity

| Workload platform | Bằng chứng có thể dùng | Rủi ro quan trọng |
|---|---|---|
| Kubernetes ServiceAccount + mesh | SPIFFE ID/X.509-SVID qua mTLS | Pod có quyền chạy dưới cùng SA |
| SPIRE/SPIFFE | Node/workload attestation và SVID | Selector/agent/CA compromise |
| Cloud IAM role/service account | Short-lived identity token/federated credentials | Role trust quá rộng, impersonation |
| CI/CD workload federation | OIDC token của workload, ràng buộc issuer/audience/subject | Repo/branch/environment policy bypass |
| VM identity | Cloud metadata identity, instance attestation, certificate | Metadata token theft/host compromise |
| External partner workload | Client certificate hoặc scoped OAuth client credentials | Key lifecycle/partner trust và rotation |
| Service mesh proxy | Peer mTLS identity từ validated certificate | Traffic bypass mesh hoặc cert hết hạn |

### 8.2. SPIFFE ID là danh tính, X.509-SVID là chứng cứ

~~~text
Ví dụ SPIFFE ID:
spiffe://prod.example.com/ns/payments/sa/settlement

PDP kiểm tra:
- Certificate chain đến đúng trust bundle.
- URI SAN chứa đúng SPIFFE ID.
- Chứng thư còn hiệu lực; bên gọi sở hữu khóa riêng.
- Trust domain và principal nằm trong danh sách cho phép.
- Workload được phép gọi resource/action cụ thể.
~~~

**Không tin X-SPIFFE-ID tự khai trong header**. Workload identity phải được xác minh bởi mTLS/issuer hoặc assertion được bảo vệ. Danh tính này **khác user identity** gắn với request đi qua workload.

### 8.3. Không lấy một workload identity thay mọi application authorization

Service **orders** được mTLS xác thực để gọi **payments** không có nghĩa orders được thanh toán thay mọi user. Ứng dụng vẫn phải kiểm tra **user, tenant, object, amount và business action** theo nghiệp vụ. Chỉ cấp quyền service tối thiểu để giới hạn lateral movement khi một workload bị compromise.

### 8.4. Workload posture khác device posture

Với workload có thể xét **image digest/provenance, admission result, signed deployment, namespace/cluster, runtime attestation, node security state, vulnerability policy và service account mapping**. Đây là tín hiệu phụ trợ, **không tự chứng minh binary hoàn toàn an toàn**; phải lấy từ trusted control plane và gắn với đúng instance/workload.

## 9. Resource context: quyết định quyền cho đúng đối tượng

Một quyết định không chỉ phụ thuộc user và workload mà còn **resource được truy cập**.

Ví dụ phân loại:

| Resource | Mức độ nhạy cảm | Quyền ví dụ |
|---|---|---|
| Portal thông báo nội bộ | Internal | Employee read, token/session hợp lệ |
| Dashboard KPI tổng hợp | Confidential | Team role, device posture cơ bản |
| Báo cáo tài chính chưa công bố | Restricted | Finance role, managed device, MFA mới |
| Hệ quản trị network/cloud IAM | Privileged | JIT approval, phishing-resistant MFA, managed device |
| Payments API | Highly sensitive | Exact workload principal + route + user/tenant auth |
| Data export endpoint | Restricted | Approver/role, data classification, step-up, audit |

### 9.1. Resource identity phải đến từ nơi đáng tin

PEP/API gateway cần resolve **app/route/server/resource ID** từ cấu hình router/catalog, không lấy **resource.classification=internal** do client gửi để được policy nhẹ hơn. Ở backend, object-level authorization vẫn phải kiểm tra tenant/ownership.

### 9.2. Path không tương đương resource authorization

Gateway có thể biết **GET /v1/orders/{id}**, nhưng thường không biết người dùng được đọc **order id cụ thể** nếu không có context từ application. Không thay **BOLA/object-level authorization** bằng một rule ZTNA cho phép chung endpoint orders.

### 9.3. Thay độ nhạy tài nguyên phải kích policy review

Khi một API từ internal trở thành restricted, cache decisions cũ hoặc session đang tồn tại cần được đánh giá lại theo policy. Resource catalog phải có **owner, classification, version và change audit**.

## 10. Network context: hữu ích nhưng không đủ để quyết định

ZTNA có thể dùng network context để xác định **đường truy cập an toàn**, nhưng không được đánh đồng **vị trí mạng với quyền**.

### 10.1. Các tín hiệu network

- **Trusted ingress peer** và verified proxy chain.
- **VPN/connector association**, endpoint zone và routing path đã biết.
- **Device-local/private link** hoặc cloud private endpoint có xác minh.
- **IP reputation/ASN/GeoIP** như một tín hiệu có độ tin cậy hữu hạn.
- **TLS protocol, SNI/hostname** được kiểm tra ở điểm tương ứng.
- **Egress gateway và DNS resolver path** khi app cần bảo vệ đường ra.

### 10.2. Không dùng X-Forwarded-For hoặc GeoIP như bằng chứng nhân thân

Một request từ NAT nhà mạng, VPN hoặc CDN có thể có địa chỉ nguồn khác user. **X-Forwarded-For** có thể bị giả nếu trusted proxy không sanitize. **GeoIP có sai số**, người dùng đi công tác/roaming hợp lệ có thể xuất hiện ở vùng khác. Quyết định nhạy cảm phải ưu tiên **verified identity, device/workload posture và resource scope**.

### 10.3. Một PEP ở network edge không hiểu mọi thao tác

PEP xử lý TCP tới database có thể biết **user, device, destination host/port và thời gian**, nhưng không thấy **SQL query/action** nếu không có integration. Đừng tuyên bố "chỉ cho SELECT" trong policy TCP tunnel khi không có database-aware enforcement. Quyền **SELECT/UPDATE** phải được thực thi bởi DB RBAC/proxy có khả năng tương ứng.

## 11. RBAC, ABAC, PBAC và context-aware policy

| Mô hình | Dữ kiện chính | Ưu điểm | Giới hạn |
|---|---|---|---|
| **RBAC** | User/workload được gán role | Dễ audit và quản trị nhóm quyền | Role thuần túy không phản ánh device/risk |
| **ABAC** | Thuộc tính subject, object, action, environment | Linh hoạt theo ngữ cảnh | Phụ thuộc chất lượng nguồn thuộc tính |
| **PBAC** | Policy logic có nhiều điều kiện/nguồn | Tách authorization logic và quản trị version | Độ phức tạp, policy conflicts, latency |
| **ACL/network allowlist** | Địa chỉ/nhóm/route cụ thể | Hữu ích ở L3/L4, segmentation | Không xác minh human/workload identity |
| **Risk-adaptive access** | Risk engine thay yêu cầu/chặn theo risk | Có thể phản ứng ngữ cảnh thay đổi | False positives, transparency và data governance |

**Context-aware policy** thường được hiện thực qua **RBAC + ABAC/PBAC + session/risk checks**. Các thuật ngữ không bắt buộc là sản phẩm riêng biệt.

### 11.1. Quy tắc từ chối mặc định

Khi một request không khớp allow rule, hoặc thiếu thuộc tính bắt buộc cho thao tác nhạy cảm, ưu tiên **DENY hoặc chuyển sang remediation/step-up** theo thiết kế. **Không coi unknown là ALLOW**.

### 11.2. Giải quyết policy conflicts

Nếu có một rule **ALLOW finance read** và một rule **DENY high-risk device**, phải định nghĩa thứ tự rõ ràng, ví dụ **explicit deny override allow**, sau đó áp constraints bổ sung như JIT và posture. Không mặc định các sản phẩm ZTNA, OPA, cloud IAM và service mesh đều dùng cùng precedence.

### 11.3. Một quyết định có thể có nhiều kết quả

- **ALLOW:** được truy cập một scope và thời hạn xác định.
- **DENY:** không được thực hiện action.
- **STEP_UP:** cần tăng assurance, ví dụ MFA mới; PEP không được forward action cho đến khi hoàn tất.
- **REMEDIATION_ONLY:** chỉ mở đường tới onboarding, MDM update hoặc support workflow đã hạn quyền.
- **READ_ONLY:** chỉ khi gateway/application thực sự phân biệt được read/write.
- **REVOKE/TERMINATE:** khi session đang tồn tại không còn đạt chính sách.

Một số PDP trả về **permit/deny** kèm obligations, còn PEP thực thi STEP_UP/REMEDIATION; mô hình nhiều kết quả này là **hợp đồng kiến trúc minh họa**, không phải API chuẩn duy nhất.

## 12. Policy Decision Point, Policy Enforcement Point và Policy Information Point

### 12.1. Phân vai rõ ràng

| Thành phần | Nhận gì? | Làm gì? | Nếu bị lỗi? |
|---|---|---|---|
| **IdP** | Login/MFA, account/role lifecycle | Xác minh user, cấp assertion/token theo policy | Không tự cho phép dùng token sai audience |
| **Device posture provider** | MDM/EDR/device identity | Trả compliance/risk assertion có timestamp | Unknown/stale cần xử lý theo risk |
| **Workload identity provider** | Attestation, SA/cloud role, CSR | Cấp/validate workload cert/token | Không tin identity string tự khai |
| **Resource catalog** | App owner, route, classification | Xác định resource/action | Không cho client tự đổi classification |
| **PDP/Policy Engine** | Verified subject/context/resource/action | Tính toán ALLOW/DENY và nghĩa vụ | Không chấp nhận blind allow khi context critical thiếu |
| **Policy Administrator** | Decision/session control | Cấp/thu hồi thiết lập communication path | Cần xử lý session còn sống khi revoke |
| **PEP** | Kết nối/API request, decision & obligations | Thực thi tại đường đi | Không cho bypass direct-to-backend |
| **SIEM/Audit** | Decisions, reasons, phiên, context version | Điều tra và detection | Không dùng absence of logs = absence of traffic |

### 12.2. PIP freshness và signed attributes

Khi PDP gọi nhiều provider, phải xử lý **timeout, cache, out-of-order events, revoked sessions, clock skew và conflicting states**. Ví dụ identity đã bị revoke nhưng cache posture vẫn compliant; **user identity invalid phải DENY**, không thể được một thuộc tính tốt khác "cộng điểm" để bù lại.

### 12.3. PEP có thể ở nhiều lớp

Một tổ chức có thể dùng **ZTNA proxy cho nhân viên**, **API gateway cho app**, **service mesh mTLS/AuthorizationPolicy cho workload** và **database RBAC cho truy vấn**. Các PEP này nên chia sẻ **policy intent và log correlation**, nhưng không mặc định một token hoặc một API policy portable cho mọi sản phẩm.

## 13. Hợp đồng yêu cầu và quyết định chính sách

### 13.1. Input do PEP tổng hợp từ các nguồn đã được xác minh

~~~json
{
  "request_id": "req-demo-410",
  "timestamp": "2026-11-28T10:15:00Z",
  "subject": {
    "type": "human",
    "user_id": "user-pseudonymous-42",
    "issuer": "corp-idp",
    "authenticated": true,
    "role": "finance-analyst",
    "auth_time": "2026-11-28T10:10:00Z",
    "mfa_age_seconds": 300,
    "mfa_verified": true
  },
  "device": {
    "id": "device-demo-17",
    "managed": true,
    "posture": "compliant",
    "assertion_issuer": "approved-mdm",
    "assertion_age_seconds": 80,
    "bound_to_session": true
  },
  "workload": {
    "spiffe_id": "spiffe://prod.example.com/ns/ztna/sa/finance-bff",
    "mtls_verified": true,
    "trust_domain": "prod.example.com"
  },
  "resource": {
    "id": "finance-report-api",
    "classification": "restricted",
    "route": "/v1/reports/{id}",
    "action": "read"
  },
  "environment": {
    "risk": "low",
    "network_path": "approved-ztna-connector",
    "current_jit_grant": null
  }
}
~~~

Mọi giá trị là **dữ liệu giả định**. Trong môi trường thật, một raw client JSON chứa các trường này **không tự đáng tin**. PEP/PDP phải xác thực từng assertion và nguồn thuộc tính; **workload.spiffe_id** phải được rút từ verified mTLS peer identity, không nhận từ field do browser gửi.

### 13.2. Output do PDP trả và PEP phải thực thi

~~~json
{
  "decision_id": "dec-demo-813",
  "request_id": "req-demo-410",
  "effect": "ALLOW",
  "policy_id": "finance-reports-context-v4",
  "policy_version": "4.2",
  "reason_codes": [
    "VERIFIED_USER_ROLE",
    "MANAGED_DEVICE_POSTURE_FRESH",
    "AUTHORIZED_WORKLOAD",
    "RESOURCE_ACTION_ALLOWED"
  ],
  "scope": {
    "resource_id": "finance-report-api",
    "allowed_actions": ["read"]
  },
  "obligations": {
    "max_session_seconds": 600,
    "recheck_posture_after_seconds": 120,
    "audit_level": "security"
  },
  "evaluated_at": "2026-11-28T10:15:00Z",
  "valid_until": "2026-11-28T10:17:00Z"
}
~~~

**valid_until và max_session_seconds khác nhau**: một quyết định được cache có thể hết hiệu lực trước khi session kết thúc, buộc re-evaluate. PEP cần **giới hạn scope**, tôn trọng obligations và ghi nhận những rechecks đã thực hiện; một trường trong JSON không có ý nghĩa bảo mật nếu thực tế không được enforce.

### 13.3. Vì sao phải ghi reason_code?

Một status 403 không nói request bị deny vì **role, device stale, MFA cũ, policy update hay workload principal sai**. Reason codes giúp SOC điều tra và kiểm tra tính nhất quán của policy nhưng **không cần phơi toàn bộ logic nội bộ cho Internet client**. Cung cấp thông báo người dùng đủ khắc phục, lưu chi tiết trong security logs có quyền.

## 14. Đánh giá ban đầu, đánh giá lại và tính liên tục của truy cập

Trong Zero Trust, truy cập không chỉ được xét một lần tại login. Tuy nhiên **liên tục** không có nghĩa phải gọi PDP cho mọi gói TCP. Một implementation có thể đánh giá:

1. **Khi thiết lập phiên/connection**, kiểm tra user, device, workload, resource và risk.
2. **Trước mỗi hành động nhạy cảm**, ví dụ data export, đổi firewall hoặc cấp key.
3. **Theo chu kỳ**, ví dụ recheck device posture, session policy và token validity sau một TTL.
4. **Theo sự kiện**, ví dụ EDR đổi high risk, IdP revoke, admin hủy JIT, resource đổi classification.
5. **Khi đổi ngữ cảnh**, như user chuyển device, workload đổi trust domain, request truy cập API khác hoặc resource sensitivity tăng.

### 14.1. Dòng thời gian một phiên

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User / Device
    participant P as ZTNA PEP
    participant D as PDP
    participant S as Signal providers
    participant A as Private App
    U->>P: Login / request restricted report
    P->>S: Fetch verified user + device + risk
    S-->>P: Assertions with freshness/expiry
    P->>D: Evaluate resource/action/context
    D-->>P: ALLOW / scope / TTL / obligations
    P->>A: Forward authorized request
    A-->>P: Application response
    S-->>P: Event: device high risk or session revoked
    P->>D: Re-evaluate affected session
    D-->>P: REVOKE / DENY or remediation
    P-->>U: Stop access according to transport/session semantics
~~~

### 14.2. Những kết nối không thể cắt ngay chỉ bằng đổi policy

- Một **TCP connection** đang mở có thể tồn tại dù policy cache đã hết TTL.
- **SSH/RDP/WebSocket/HTTP2 streams** có thể kéo dài; PEP phải hỗ trợ và cấu hình khả năng ngắt/re-authorize.
- Nếu decision chỉ được kiểm tra khi tạo connection, thay quyền **không tự hủy mọi gói của flow hiện có**.
- Backend có thể đã xử lý request dài chạy trước khi revoke; cần **business transaction and cancellation policy** phù hợp.
- Những yêu cầu đã gửi tới ứng dụng có thể được hoàn tất trước khi sự kiện revoke tới PEP.

**Mỗi loại tài nguyên phải có SLO "revocation-to-enforcement" rõ**, đo trong kiểm thử, không hứa "thu hồi tức thì" nếu implementation chỉ đánh giá tại connect.

### 14.3. Truy cập được cho phép sau step-up có giới hạn

Một step-up MFA mới có thể mở **một action nhạy cảm trong 5 phút**, không nên nâng mọi quyền của user cho toàn bộ mạng trong nhiều giờ. Sau đó PDP/PEP phải hết hạn quyền tạm theo đúng resource/action.

## 15. Điều kiện kép: người dùng và workload đều phải được phép

Trong ứng dụng hiện đại, request thường qua **user → browser → ZTNA → frontend → API gateway → microservice → database**. Có ít nhất hai loại principal:

- **Human subject:** ai đang yêu cầu truy cập dữ liệu/chức năng?
- **Workload subject:** dịch vụ nào thực thi và gọi dịch vụ khác dưới mTLS/cloud identity?

### 15.1. Ví dụ ma trận quyền

| User status | Workload identity | Device context | Resource/action | Kết quả dự kiến |
|---|---|---|---|---|
| Finance role hợp lệ | finance-bff đã mTLS verify | Managed, compliant | Read monthly report | ALLOW theo scope |
| Finance role hợp lệ | debug workload | Managed | Read restricted report | DENY do workload không được ủy quyền |
| Guest không có finance role | finance-bff đã verify | Managed | Read restricted report | DENY do user thiếu quyền |
| Finance role hợp lệ | finance-bff đã verify | Unmanaged | Read restricted report | DENY hoặc remediation theo policy |
| Finance role hợp lệ | finance-bff đã verify | Compliant, MFA cũ | Export restricted report | STEP_UP khi rule hỗ trợ |
| Finance role hợp lệ | finance-bff đã verify | High-risk EDR | Export restricted report | DENY/REVOKE |
| Không có human user, job scheduler | batch-exporter verified | Workload attested | Job nội bộ theo allowlist | ALLOW qua **machine policy riêng** |
| Không có human user, unknown service | Không có identity được xác minh | N/A | Payments API | DENY |

### 15.2. Không áp "human device" cho batch job một cách máy móc

Machine-to-machine jobs **không có laptop của người dùng**. Không nên cho chúng bypass tất cả policy vì thiếu device. Thiết kế **policy branch riêng theo principal type**, đòi **workload attestation, mTLS, CI/Cloud IAM role, signed deployment, resource/action và risk context**.

Ngược lại, **human-initiated workflow** chạy qua batch service có thể yêu cầu cả **delegated human authorization** lẫn **workload authorization** nếu action ảnh hưởng dữ liệu nhạy cảm.

### 15.3. Công thức logic

~~~text
ALLOW_human_request =
    valid_human_identity
AND human_has_resource_action_permission
AND sufficient_authentication_assurance
AND fresh_and_bound_device_posture_if_required
AND risk_within_approved_threshold
AND valid_workload_identity_on_relevant_hops
AND workload_may_call_destination
AND no_explicit_deny
AND PEP_on_real_data_path

ALLOW_machine_request =
    attested_workload_identity
AND correct_trust_domain_and_audience
AND workload_has_exact_resource_action_permission
AND runtime_or_deployment_posture_if_required
AND risk_within_approved_threshold
AND no_explicit_deny
AND enforcement_on_actual_path
~~~

**Công thức chỉ mô tả policy intent**, không phải giao thức chuẩn. Backend vẫn phải kiểm tra object-level authorization mà PEP chưa thấy.

## 16. On-behalf-of (OBO), delegation và nguy cơ confused deputy

Một microservice như **finance-bff** nhận request từ user rồi gọi **report-api**. Report API có thể thấy certificate mTLS của **finance-bff** nhưng không thấy user gốc nếu kiến trúc không truyền delegation context đáng tin.

### 16.1. Confused deputy xảy ra thế nào?

Một app service có quyền đọc dữ liệu lớn có thể bị user thiếu quyền yêu cầu đọc hộ tài nguyên. Nếu backend chỉ kiểm tra *service được phép gọi API* mà không xét *user hiện tại được phép xem tài nguyên nào*, service trở thành **confused deputy**.

~~~mermaid
flowchart LR
    U[Human user A] --> Z[ZTNA PEP / verified identity]
    Z --> F[Finance BFF / workload identity]
    F -->|mTLS + delegated user context| G[Report API]
    G --> P{Human AND workload AND object permission?}
    P -- Yes --> D[Report data]
    P -- No --> X[Deny + audit]
~~~

### 16.2. Truyền delegation context đúng cách

- Dùng **access token có audience cho API đích** hoặc token exchange/OBO flow được IdP hỗ trợ.
- Hạn **scope, audience, lifetime và delegation chain**, không dùng token chung cho mọi backend.
- Xác minh **token type, issuer, signature/introspection, subject, actor và authorization claims** đúng profile.
- Không forward **ID token** như access token nếu API không được thiết kế để chấp nhận.
- Không tin **X-User-ID/X-Tenant-ID** từ request Internet; nếu proxy cung cấp verified headers phải sanitize, có kênh bảo vệ và chặn bypass.
- Không log raw access tokens, refresh tokens hoặc private keys.

### 16.3. Hai phép kiểm tra độc lập

**Report API** cần biết: **(a)** mTLS workload finance-bff có được gọi endpoint này không, và **(b)** user A có được đọc report B/tenant C không? Chỉ một điều kiện **ALLOW** là chưa đủ cho dữ liệu phân quyền theo user.

## 17. Step-up MFA, JIT và policy thời gian

Một số hành động yêu cầu đảm bảo cao hơn session thông thường:

| Hành động | Ngữ cảnh bắt buộc minh họa | Kết quả khi thiếu |
|---|---|---|
| Xem portal thông thường | User active, SSO hợp lệ | LOGIN/DENY |
| Xem báo cáo restricted | Role, device managed/compliant, risk thấp | DENY/REMEDIATION |
| Export dữ liệu nhạy cảm | Điều kiện trên + MFA mới + quota/approval | STEP_UP/DENY |
| SSH bastion quản trị | JIT entitlement, managed device, short-lived SSH cert, PAM audit | DENY |
| Sửa cloud security group | Admin role, change ID, approval, phishing-resistant MFA | DENY |
| Kích hoạt break-glass | Emergency process, approval/monitoring, expiry | Emergency access scoped |
| Job CI triển khai | Protected ref/environment, short-lived workload identity, approved plan | DENY khi trust sai |

**Thời gian là điều kiện**, không phải bằng chứng duy nhất. "Trong giờ hành chính" không đủ cho phép truy cập nếu identity, device hoặc role sai.

### 17.1. JIT không tự thu hồi mọi tác động đã thực hiện

Một admin được quyền sửa firewall trong 10 phút có thể tạo rule còn tồn tại sau khi hết JIT. Cần **expiration của change, reconciliation, policy-as-code, audit và rollback**, không chỉ timeout của role.

### 17.2. Step-up phải gắn với đúng session và action

MFA thực hiện trên **phiên khác, device khác hoặc nhiều giờ trước** không nên được áp như step-up mới nếu policy yêu cầu assurance cho thao tác hiện tại. Cần session/device binding và xác định được **auth_time/assurance**.

## 18. Người dùng thứ ba, nhà thầu và thiết bị BYOD

ZTNA thường được dùng để giảm phạm vi truy cập của nhà thầu/đối tác thay vì cấp VPN vào cả subnet.

### 18.1. Policy dành cho partner

~~~text
Principal: external-contractor-verified
Identity provider: partner federation / guest identity
Account lifecycle: approved sponsor + expiration date
Device: managed-by-partner with supported assertion OR browser isolation
Resource: support-ticket-portal (không phải production VPC)
Actions: view + update own assigned tickets
Session: short-lived, no persistent network routes
Restrictions: no admin APIs, no bulk export, no direct database
Monitoring: access decisions + anomaly detection
~~~

**Đây là thiết kế minh họa**, không phải quyền đã được enforce. App vẫn cần **object ownership** để bảo đảm nhà thầu chỉ thấy tickets được giao.

### 18.2. Cẩn trọng khi dùng posture của đối tác

Một thiết bị được **partner MDM** đánh dấu compliant chỉ đáng tin nếu doanh nghiệp **thỏa thuận trust, xác thực assertion, TTL, identity binding và quy trình incident/revocation**. Không mặc định đối tác có cùng security baseline.

### 18.3. Không cấp whole-network VPN chỉ để truy cập một portal

Với ứng dụng có thể đưa qua web/ZTNA proxy, ưu tiên **per-app access**, không mở route tới database/admin/private DNS tùy tiện. Với giao thức không web, vẫn có thể cần ZTNA TCP connector hoặc giải pháp truy cập đặc thù và kiểm thử thực thi.

## 19. ZTNA so với VPN, NAC, firewall và API gateway

| Công nghệ | Kiểm soát trọng tâm | Vai trò với context-aware policy |
|---|---|---|
| **VPN truyền thống** | Tunnel network giữa client/site và một phạm vi route | Có thể kết hợp identity/device checks; cần hạn route và east-west access |
| **ZTNA** | Truy cập từng application/service theo identity và context | Thu hẹp bề mặt truy cập mạng, PEP kiểm tra policy |
| **NAC / 802.1X** | Thiết bị/identity được vào network segment nào | Bổ sung device/network admission, không thay app AuthZ |
| **Firewall/NSG/SG** | Allow/deny theo IP, port, protocol/zone | Chặn bypass, làm segmentation dưới ZTNA |
| **WAF** | HTTP threat detection/protection ở edge | Bảo vệ input, không thay Identity-Aware Access |
| **API gateway** | Token validation, scopes, quota, routes và logs | PEP phù hợp cho API, cần backend object-level AuthZ |
| **Service mesh mTLS** | Workload-to-workload authentication và policy | Bảo vệ east-west calls, không mặc định có user context |
| **IAM/PAM** | Phân quyền cloud/control-plane, privileged sessions | Phục vụ human/workload entitlement và JIT |
| **EDR/MDM** | Endpoint posture và threat telemetry | PIP cho context, không tự là PEP mạng |
| **DNS security** | Discovery/filtering/validation | Hạn kết nối tới đích xấu, không chứng minh caller được cấp quyền |

### 19.1. ZTNA không làm VPN vô nghĩa

VPN site-to-site, quản trị một số legacy protocols hoặc hybrid connectivity vẫn hữu ích khi được phân đoạn đúng. Vấn đề là **không biến tunnel thành quyền vào toàn mạng**. ZTNA có thể chạy trên hoặc độc lập với một đường private network.

### 19.2. Không dùng ZTNA để bỏ firewall

Nếu backend vẫn có public IP và SG mở, attacker có thể **gọi thẳng backend**, không qua PDP/PEP. Cloud firewall, segmentation, origin protection và application auth vẫn bắt buộc theo threat model.

### 19.3. "Clientless" không mặc định che được mọi API

Browser-based ZTNA thường phù hợp web apps. SSH, RDP, SQL hoặc custom TCP cần **native client/proxy/connector hoặc protocol-aware PEP**. Phải xác nhận sản phẩm hỗ trợ giao thức, session monitoring, identity forwarding và revocation.

## 20. ZTNA cho SSH, RDP và database access

### 20.1. Quản trị SSH

Một kiến trúc có thể dùng **ZTNA client/gateway → bastion hoặc SSH access proxy → managed host** với SSO, MFA mới, JIT role, **short-lived SSH certificates** và host authorization. Không cấp **0.0.0.0/0:22** rồi nghĩ SSO ở portal đã bảo vệ daemon SSH.

### 20.2. Remote desktop

RDP nên đi qua **gateway có authentication, session limits, logging và source controls**; chính sách về clipboard/file transfer/recording nếu cần phải được enforcement point/desktop platform thực thi. Đừng hứa field **disable_copy_paste=true** trong PDP sẽ tự ngăn được Windows clipboard nếu RDP gateway không có tính năng ấy.

### 20.3. Database access

Một TCP proxy cho **db.internal:5432** có thể cho phép chỉ user/role/on-call trong 30 phút, nhưng quyền **SELECT/UPDATE/DELETE** vẫn cần database RBAC và quản lý credentials. Khi có database-aware proxy, có thể áp thêm SQL-specific controls nhưng phải xác minh khả năng sản phẩm.

### 20.4. Long-lived sessions

SSH, RDP, database connection pool và streaming API có thể tồn tại lâu; thiết kế **idle timeout, absolute session age, identity recheck, network path kill switch và credential expiry** phù hợp. Khi revoke user, kiểm thử **phiên đang mở bị chặn trong SLO**.

## 21. ZTNA trên cloud, on-prem và hybrid

~~~mermaid
flowchart LR
    D[Managed laptop / Browser] --> E[ZTNA Edge PEP]
    E --> PDP[PDP + Verified Context]
    E --> C[Outbound Connector in Private Network]
    C --> A[Private App in VPC/VNet]
    C --> B[Legacy On-prem App]
    I[Corporate IdP] -. Identity / MFA .-> PDP
    M[EDR / MDM] -. Device posture .-> PDP
    W[Service Mesh / API Gateway] --> S[Internal Services]
    S -. App AuthZ / mTLS .-> W
~~~

Một số ZTNA architectures dùng **outbound-only connector** từ private network đến nhà cung cấp để giảm nhu cầu inbound firewall rule, nhưng:

- Không phải mọi triển khai có outbound-only architecture.
- Connector phải được xác thực, giới hạn destinations, có HA, logs và patching.
- Backend phải chặn **public/direct routes** nếu dự kiến chỉ PEP được truy cập.
- Policy/app mappings phải tránh **connector trở thành một proxy tới toàn subnet**.
- DNS/route resolution, TLS hostname và private endpoint behavior cần được thử riêng.

### 21.1. Cloud-native identity không tự đồng nhất với ZTNA identity

Một user có quyền truy cập **private portal** qua ZTNA không có quyền chỉnh security group trong cloud. IAM/control-plane role của AWS/Azure/GCP cần policy riêng; nên kết hợp SSO/PAM và log correlation, không cấp network admin vì user đã vào ZTNA.

### 21.2. Multi-region failover và policy consistency

Một gateway edge region A có thể dùng policy version mới nhưng region B còn bản cũ. Logging phải có **PEP ID, region, policy revision, IdP/PIP freshness và deployment time**, đồng thời thử failover để tránh mở quyền do stale caches.

## 22. Zero Trust ở Kubernetes và service mesh

### 22.1. Tách east-west và north-south

- **North-south:** user/partner → ZTNA/API gateway → ingress → app.
- **East-west:** app A → app B, thường dùng workload identity/mTLS và AuthorizationPolicy.
- **Egress:** app → external SaaS/Internet/database, cần egress identity/policy và đôi khi DNS filtering.

Một user đã pass ZTNA tới frontend không có nghĩa mọi Pod trong namespace được quyền gọi mọi service backend. Cần **per-workload identity, NetworkPolicy, service authorization và application user-context**.

### 22.2. Workload identity trong mesh

~~~text
User: finance-analyst  (verified by IdP)
ZTNA frontend: managed device and session context
Frontend workload:
  spiffe://prod.example.com/ns/finance/sa/finance-bff
Report service:
  spiffe://prod.example.com/ns/reporting/sa/report-api

Checks:
  1. User may view restricted finance report?
  2. Frontend workload may call report-api?
  3. Device/session still meets policy?
  4. Report API enforces tenant/object ownership?
  5. Network route is limited to intended paths?
~~~

**mTLS xác thực workload** nhưng không tự xác minh **user**. Cần truyền signed delegated user token hoặc cơ chế tương đương, không dựa vào username header tự khai.

### 22.3. Istio/ambient và enforcement point

Ở Istio sidecar, Envoy thường xử lý L4/L7 phù hợp với policy. Trong **Istio ambient**, **ztunnel** xử lý L4 identity/mTLS, còn **waypoint** cần cho nhiều L7 policies. Một L7 AuthorizationPolicy đặt ở **ztunnel không đọc HTTP** sẽ không thực thi như kỳ vọng. Cần chọn policy target và **ngăn direct-to-workload bypass waypoint** khi L7 protection là yêu cầu.

### 22.4. Namespace không phải access control toàn diện

Kubernetes Namespace giúp quản lý tài nguyên, nhưng **không tự chặn Pod-to-Pod traffic**. CNI NetworkPolicy/mesh policy phải được enforce và test; RBAC giới hạn ai tạo Pod dưới ServiceAccount có quyền cao. Nếu Pod lạ dùng cùng SA, mTLS principal có thể trùng và policy theo principal không phân biệt được.

## 23. Policy re-evaluation, caching và revocation

Một hệ thống 10.000 requests/giây có thể không gọi mọi PIP/IdP theo từng request. **Cache** giúp hiệu năng nhưng tăng độ trễ cập nhật context.

### 23.1. Các cache khác nhau

| Cache | Đối tượng | Rủi ro khi stale |
|---|---|---|
| **IdP token/JWKS** | Chữ ký, issuer key, user claims | Token revoked/group đổi không phản ánh tức thì |
| **Device posture** | Compliant/risk assertion | Device bị compromise nhưng session vẫn ALLOW |
| **Authorization decision** | ALLOW cho resource/action cụ thể | Policy/restriction đổi nhưng PEP tiếp tục dùng |
| **Workload SVID/trust bundle** | Certificate/CA và trust domain | Trust/issuer bị thu hồi nhưng peer còn tin |
| **Resource catalog** | Resource classification/owner | Resource chuyển restricted nhưng còn policy cũ |
| **DNS/route** | Destination/connector | Có thể bypass policy nếu app chuyển đường |
| **Session state** | Active connection/entitlement | Revoke user chưa kết thúc TCP/WebSocket |

### 23.2. Thiết kế khóa cache

Không cache ALLOW chỉ theo **user ID** hoặc **source IP**. Một quyết định phụ thuộc ít nhất **principal, device binding, workload identity, resource, action, policy version và context freshness**; khi bất kỳ yếu tố nào đổi phải invalidate/re-evaluate phù hợp.

### 23.3. TTL phải phù hợp risk

- Portal ít nhạy cảm có thể cho session dài hơn nhưng vẫn cần revoke.
- Privileged/admin actions có thể yêu cầu **fresh MFA và decision TTL ngắn hơn**.
- Certificate short-lived giúp giảm cửa sổ credential compromise nhưng không làm active sessions tự hết ngay.
- Risk events nên kích **event-driven re-evaluation** khi implementation hỗ trợ; không chỉ chờ token expire.

**Không có TTL duy nhất phù hợp tất cả hệ thống.** Đặt **SLO độ trễ revoke**, đo trong staging và thông báo giới hạn rõ với người sở hữu risk.

### 23.4. Shared Signals/CAEP

Một số hệ sinh thái identity hỗ trợ **security-event signals như session revoked, credential change hoặc device risk** để yêu cầu các bên đánh giá lại. Có thể tham khảo **OpenID Shared Signals / CAEP**, nhưng support, schema, subscription/auth và enforcement đều phụ thuộc sản phẩm. **Nhận một event không tự cắt TCP session** nếu PEP không hành động.

## 24. Khi PDP, IdP, MDM hoặc connector bị lỗi

### 24.1. Tách failure of authorization khỏi failure of logging

- **PDP unavailable:** không nên mặc định cho admin/restricted access; có thể từ chối hoặc dùng **bounded previously approved session** theo risk policy.
- **IdP unavailable:** không chấp nhận token chưa xác minh; những session có chứng cứ còn hợp lệ có thể xử lý theo policy explicit.
- **MDM/EDR unavailable:** không tự đánh dấu compliant; dùng **UNKNOWN/STALE** và remediation/deny theo classification.
- **ZTNA connector unavailable:** request có thể thất bại dù ALLOW hợp lệ; đó là availability failure, không phải authz deny.
- **SIEM/log exporter unavailable:** ứng xử phải theo audit criticality, buffer/backpressure/monitoring; **không tự bỏ AuthorizationPolicy** để làm dịch vụ chạy.
- **Risk engine unavailable:** cần mapping và fallback **được duyệt trước**, đặc biệt với admin/exports.

### 24.2. Ma trận degrade modes

| Resource/action | Critical signal mất | Gợi ý hành vi an toàn |
|---|---|---|
| Public status page | Không cần sensitive user/device context | Phục vụ theo public access policy |
| Internal low-risk portal | Risk telemetry tạm unavailable | Có thể tiếp tục session đã duyệt trong TTL ngắn nếu risk owner chấp thuận |
| Restricted report | Device posture stale | DENY hoặc remediation cho đến khi chứng thực mới |
| Admin SSH / cloud network change | MFA/JIT/PDP không xác minh được | DENY; dùng emergency process riêng nếu cần |
| Financial data export | DLP/authorization service unavailable | DENY thay vì cho export không kiểm soát |
| Critical machine-to-machine health path | CA/control plane outage | Bounded behavior theo credential validity/availability plan, không tự tắt mTLS |
| Incident response break-glass | Federation/IdP outage | Quy trình emergency có owner, logging, short-lived scope và hậu kiểm |

**Không gọi fallback cho restricted access là "fail open vì tăng availability" một cách chung chung.** Mỗi ngoại lệ cần owner, risk acceptance, thời hạn và kiểm thử.

### 24.3. Caching và availability không thay bảo mật origin

Một PEP có cache ALLOW tốt đến đâu cũng vô dụng nếu backend public cho phép bypass. Failover sang gateway dự phòng cần **policy consistency, cryptographic identity verification và log coverage**, không chuyển thành "direct app route" bỏ qua access checks.

## 25. Ngăn đường bypass và lateral movement

### 25.1. Các đường bypass phổ biến

| Đường bypass | Tại sao nguy hiểm? | Cách giảm |
|---|---|---|
| **Public origin IP** | Client không qua ZTNA/WAF | Origin firewall, private endpoint, authenticated upstream |
| **Direct LB/NodePort** | Bỏ API gateway/mTLS/waypoint | SG/NSG, admission, NetworkPolicy |
| **Bastion/VPN subnet quá rộng** | User được vào cả mạng thay vì app | Per-app access, segmentation, scoped routes |
| **Untrusted forwarding headers** | Giả user/device/workload claims | Strip/overwrite at ingress, authenticated metadata |
| **Shared service account** | Compromised workload dùng identity được phép | SA separation, admission/RBAC, exact principal |
| **Overbroad trust-domain alias** | Dev/partner được xem như prod | Exact trust domain/principal, scoped federation |
| **Legacy admin endpoint** | Không qua PEP và không có audit | Inventory, disable, limit private JIT |
| **DNS alternate hostname/IPv6** | Hostname khác route hoặc AAAA dẫn đường phụ | DNS and dual-stack origin protection |
| **Service-to-service direct path** | L7 gateway policy bị vượt | mTLS/mesh AuthZ + CNI controls |
| **CI workload role trust quá rộng** | PR branch/attacker có privileged role | OIDC issuer/audience/subject restrictions, protected refs |
| **Orphaned connector/route** | Lưu đường vào sau migration | Cleanup audit, asset owner and expiry |

### 25.2. Không chỉ test đường chính

Một test từ browser qua ZTNA rồi nhận 200 **chỉ chứng minh đường được phép hoạt động**. Phải thử **từ nguồn không có quyền**, qua đường mạng dự phòng, direct origin, alternate DNS name, NodePort, IPv6 và VPN route có sẵn **trong phạm vi lab được cấp phép**.

### 25.3. Threat model STRIDE

- **Spoofing:** giả user assertion, device posture header hoặc SPIFFE principal.
- **Tampering:** sửa policy, PIP signal TTL, cloud connector hoặc allowlist.
- **Repudiation:** thiếu decision ID, actor session, source và policy revision.
- **Information Disclosure:** PEP bypass, overbroad resource grant, user token leakage.
- **Denial of Service:** PDP/connector outage, expired cert, excessive synchronous PIP calls.
- **Elevation of Privilege:** user/CI tự cấp admin, Pod chạy SA đặc quyền, step-up không gắn action.

**Identity-aware control cũng có thể bị vô hiệu bởi lỗ hổng governance**: người có quyền sửa policy hoặc tạo service account có thể mở đường không cần phá mã hóa.

## 26. Policy-as-code: mẫu OPA/Rego cho user + device + workload

Ví dụ minh họa cách diễn đạt một chính sách **read-only** cho tài nguyên restricted. OPA/Rego có thể đóng vai trò **PDP**, nhưng **PEP vẫn phải gọi PDP, xác minh inputs và thực thi kết quả**.

### 26.1. Rego mẫu (ngôn ngữ Rego v1)

~~~rego
package ztna.finance

import rego.v1

default allow := false

allow if {
    input.subject.authenticated == true
    input.subject.type == "human"
    input.subject.role == "finance-analyst"

    input.subject.mfa_verified == true
    input.subject.mfa_age_seconds <= 600

    input.device.managed == true
    input.device.posture == "compliant"
    input.device.bound_to_session == true
    input.device.assertion_age_seconds <= 300

    input.workload.mtls_verified == true
    input.workload.spiffe_id == "spiffe://prod.example.com/ns/ztna/sa/finance-bff"

    input.resource.id == "finance-report-api"
    input.resource.classification == "restricted"
    input.resource.action == "read"

    input.environment.risk == "low"
    input.environment.network_path == "approved-ztna-connector"
}
~~~

**Ý định:** chỉ trả ALLOW nếu **mọi điều kiện bắt buộc đều đúng**. Thuộc tính thiếu thường làm rule không chứng minh được và **default allow=false**. Ví dụ JSON ở mục 13 có cả **auth_time** và **mfa_age_seconds**; trong triển khai phải **chuẩn hóa input schema** và tính mfa_age_seconds bằng server time từ verified authentication timestamp, không tin con số do client gửi.

### 26.2. Các giới hạn quan trọng

- Đoạn mẫu **chưa có RBAC/resource ownership, explicit deny override, exception workflow, device cryptographic attestation hoặc revocation semantics** đầy đủ.
- **MFA age** dù có mặt trong input JSON minh họa phải được PEP/PDP tính từ assertion thời gian xác thực đáng tin; không lấy raw JSON của browser.
- **Workload identity** được rút từ mTLS verified principal; không chỉ kiểm tra một string claim không có bằng chứng.
- **Role finance-analyst** phải xác minh IdP và resource scope; với object-level permissions backend vẫn cần tự kiểm tra.
- Muốn **STEP_UP**, nên trả decision/obligation rõ ràng thay vì đánh đồng mọi không ALLOW là 403.
- Policy engine evaluation chưa thực thi network; phải kiểm tra PEP thực tế và đường bypass.

### 26.3. Một lỗi dễ mắc: ưu tiên điểm rủi ro hơn deny tuyệt đối

Không nên viết logic kiểu "MFA tốt + device tốt nên bỏ qua role thiếu quyền". Các điều kiện **identity valid, permission granted, no explicit deny và correct resource** phải là rào cứng. Risk score chỉ nên hỗ trợ thêm điều kiện/cách xử lý, không bù cho quyền không tồn tại.

## 27. Contract chính sách, ownership và change control

Một policy cần được **version hóa, kiểm tra, phê duyệt và có khả năng rollback**; đừng sửa trực tiếp allowlist production mà không biết policy nào được áp ở gateway nào.

### 27.1. Policy intent ở định dạng YAML minh họa

~~~yaml
# Pseudocode kiến trúc. KHÔNG phải cấu hình native của ZTNA vendor.
policy:
  id: "finance-reports-context-v4"
  version: "4.2"
  owner: "finance-security"
  enforcement: ["ztna-pep", "api-gateway", "report-api"]
  default_action: "DENY"
  scope:
    resource: "finance-report-api"
    actions: ["read"]
  human_requirements:
    identity:
      issuer: "corp-idp"
      role: "finance-analyst"
      active_account: true
    mfa:
      required: true
      max_age_seconds: 600
    device:
      managed: true
      posture: "compliant"
      max_assertion_age_seconds: 300
      session_binding_required: true
  workload_requirements:
    peer_mtls: true
    allowed_principals:
      - "spiffe://prod.example.com/ns/ztna/sa/finance-bff"
    required_trust_domain: "prod.example.com"
  environment_requirements:
    risk_max: "low"
    trusted_entrypoint: "approved-ztna-connector"
  deny_when:
    - "identity_unverified_or_revoked"
    - "critical_context_missing_or_stale"
    - "workload_principal_not_allowed"
    - "resource_or_action_not_allowed"
    - "explicit_security_deny"
  decisions:
    on_expired_mfa: "STEP_UP_IF_OTHER_REQUIREMENTS_PASS"
    on_noncompliant_device: "REMEDIATION_ONLY"
    on_high_risk: "DENY_OR_REVOKE"
  lifecycle:
    authorization_cache_ttl_seconds: 120
    session_absolute_max_seconds: 600
    audit_policy_decision: true
    require_post_deploy_allow_deny_tests: true
~~~

**Lưu ý:** đây là hợp đồng **logic**, không có một DSL portable mà mọi ZTNA provider sẽ thực thi. Phải dịch sang PEP/PDP/IdP/device posture rules cụ thể, đối chiếu semantics như **implicit allow, deny precedence, challenge behavior, session continuity, cache TTL** và kiểm thử production canary.

### 27.2. Một policy thay đổi có nhiều bước kiểm soát

~~~mermaid
flowchart LR
    R[Policy owner đề xuất PR] --> L[Schema validation + lint]
    L --> T[Positive/negative policy tests]
    T --> V[Independent security review]
    V --> D[Deploy to staging]
    D --> C[Canary PEP + PDP]
    C --> M[Compare decisions, latency, user impact]
    M --> P[Controlled production rollout]
    P --> A[Audit, drift detection, rollback readiness]
~~~

### 27.3. Separation of duties

Người **đề xuất rule**, người **phê duyệt ngoại lệ**, identity **triển khai PEP** và người **audit** không nên đều có thể tự gán quyền, tự bypass branch protection và tự tắt logging. Với thay đổi dành cho admin access hoặc kết nối partner/prod, cần owner và approval phù hợp với risk.

### 27.4. Policy shadow mode có ích nhưng không phải enforcement

Một PDP có thể tính **would-deny** trong chế độ monitor trước rollout để đo false positives. Nhưng **monitor-mode decision không được tính là đã block**. Khi báo cáo coverage, tách **policy matched, action planned và actual enforced outcome**.

## 28. Audit và security event log cho context-aware policy

Một security event nên trả lời:

- **Ai?** Verified user principal, workload principal, device reference.
- **Cái gì?** Resource ID và action, không chỉ URL/IP.
- **Điểm thực thi nào?** PEP/gateway/mesh/backend và đường đi.
- **Vì sao?** Policy ID/version, reason code, signals dùng/không dùng.
- **Kết quả?** ALLOW, DENY, STEP_UP, REVOKE, remediation và final disposition.
- **Khi nào?** event_time/ingest_time, session/recheck time.
- **Có thể liên kết không?** decision_id, request_id, trace_id và session ID giả danh được bảo vệ.

### 28.1. JSON sự kiện security mẫu

~~~json
{
  "schema_version": "1.0",
  "event_id": "evt-demo-313",
  "event_time": "2026-11-28T10:16:45.320Z",
  "event_type": "ZTNA_CONTEXT_DENIED",
  "event_source": "ztna-pep",
  "pep_id": "edge-pep-a",
  "region": "region-a",
  "decision_id": "dec-demo-814",
  "session_id": "session-pseudonymous-17",
  "request_id": "req-demo-411",
  "human_subject": "user-pseudonymous-42",
  "device_id": "managed-device-demo-17",
  "workload_principal": "spiffe://prod.example.com/ns/ztna/sa/finance-bff",
  "resource_id": "finance-report-api",
  "action": "export",
  "policy_id": "finance-reports-context-v4",
  "policy_version": "4.2",
  "result": "DENY",
  "final_disposition": "BLOCKED_BY_PEP",
  "reason_codes": ["MFA_NOT_FRESH", "ACTION_NOT_AUTHORIZED"],
  "signals": {
    "identity_verified": true,
    "device_posture": "compliant",
    "device_posture_age_seconds": 80,
    "risk": "low",
    "workload_mtls_verified": true
  }
}
~~~

Đây là **schema minh họa**. Một blocked TCP connection chưa có HTTP request ID/trace ID nên field có thể **null/absent**, không được tạo giá trị giả để lấp chỗ trống. **PEP final disposition** khác decision của PDP nếu enforcement gặp lỗi.

### 28.2. Bảo vệ dữ liệu trong logs

**Không ghi raw JWT, SAML assertion, Authorization header, refresh token, MFA code, private key, device certificate secret, full browser cookies, entire request body hoặc user location chính xác nếu không cần.** IP, user ID, device ID, posture và risk data vẫn có thể là dữ liệu cá nhân; áp retention, RBAC, tenant scope và audit truy vấn.

### 28.3. Decision khác authentication event

Một IdP **login success** có thể không dẫn tới ALLOW resource. Một PEP **DENY** có thể do thiếu quyền dù user đã MFA. Một resource **403 backend** có thể xảy ra sau khi ZTNA ALLOW vì object-level authorization. Log phải có **decision_source** để tránh gộp mọi 403 thành "ZTNA block".

### 28.4. Log pipeline phải có health

Theo dõi **exporter heartbeat, queue depth, dropped events, schema parse errors, ingest lag, retention policy changes và admin access**. **Không có DENY events** không chứng minh các cuộc tấn công đã biến mất nếu event exporter bị tắt.

## 29. Detection engineering và hành vi bất thường

| Detection hypothesis | Nguồn tín hiệu | False positive/giải thích khác |
|---|---|---|
| **Một user bị DENY nhiều resources** | PEP decisions, resource IDs, reason | Role onboarding chưa đồng bộ |
| **MFA step-up failures tăng** | IdP/PEP events, enrollment state | Người dùng đổi thiết bị/phương thức MFA |
| **Device noncompliant ngay sau login** | MDM/EDR timestamp + session | Agent update, sensor lag |
| **High-risk user vẫn có session ALLOW** | Risk event + PEP revocation state | Event trễ hoặc exception được duyệt |
| **Workload principal gọi API ngoài baseline** | Mesh mTLS peer identity + endpoint | Deployment/canary mới chưa cập nhật inventory |
| **CI workload role dùng ở branch lạ** | OIDC federation trust, CI audit | Workflow đổi hợp lệ |
| **Admin privileged access ngoài JIT** | PAM/IAM grant, session audit | Emergency access đã phê duyệt |
| **Policy moved from DENY to ALLOW** | Policy version/change logs | Planned business change |
| **ZTNA direct-origin bypass** | Cloud firewall/network logs, app access events | Health checker/approved emergency path |
| **Stale device posture được reuse** | Assertion age, PDP decision TTL | Posture exporter delay/clock skew |
| **Cross-tenant access after ZTNA allow** | Backend object-level AuthZ logs | Application bug/incorrect delegation |
| **PEP/PDP logging gap** | Heartbeat, expected ingress traffic | Planned collector maintenance |
| **Unmeshed plaintext service calls** | Mesh telemetry + CNI flows | Migration or legacy service exception |
| **Unusual data export from compliant device** | Resource audit, DLP, user and workload | Legitimate month-end bulk export |

### 29.1. Không biến IP thành danh tính cố định

Nhiều người dùng ở cùng VPN exit/NAT IP, còn một người đổi IP khi roaming. Đừng tạo account-compromise alert chỉ vì **IP thay đổi một lần**. Dùng **verified subject/session/device/workload identity, resource/action, risk trajectory và behavior baseline**.

### 29.2. Alert phải thể hiện giả thuyết

~~~json
{
  "alert_id": "alert-demo-900",
  "detector": "session_allowed_after_high_risk_signal",
  "severity": "high",
  "confidence": "requires_timeline_validation",
  "subject": "user-pseudonymous-42",
  "affected_resource": "finance-report-api",
  "risk_signal_event": "risk-demo-81",
  "pep_decision_event": "evt-demo-313",
  "expected_action": "REVOKE_OR_DENY",
  "triage": "Compare risk assertion event time, arrival time, decision TTL and active-session behavior"
}
~~~

Nếu risk event đến muộn, alert có thể chỉ ra **re-evaluation lag**, không tự chứng minh PEP cố tình bỏ qua policy. Cần phân biệt **event_time/ingest_time**, clock skew và policy version.

### 29.3. Nên đo hiệu quả, không chỉ đếm số DENY

Nhiều DENY có thể do **misconfigured role mapping**, trong khi không có DENY có thể do **bypass hoặc logging gap**. Đánh giá thêm coverage, incident containment, false-positive impact và quyền truy cập thực của nguồn không được phép.

## 30. Truy vấn SIEM điều tra quyết định ngữ cảnh

Các truy vấn dưới đây dùng bảng giả định **normalized_ztna_decisions** và **normalized_identity_events**, cú pháp SQL khái niệm. Cần chỉnh theo kho log, quyền truy vấn và schema thật; không truy vấn dữ liệu người khác/tenant khác ngoài phạm vi.

### 30.1. Điều tra một phiên và thay đổi quyết định

~~~sql
SELECT event_time, ingest_time, event_id, decision_id,
       human_subject, workload_principal, resource_id, action,
       policy_version, result, final_disposition, reason_codes
FROM normalized_ztna_decisions
WHERE session_id = 'session-pseudonymous-17'
ORDER BY event_time, event_id;
~~~

### 30.2. Phát hiện device assertion stale

~~~sql
SELECT event_time, device_id, human_subject, resource_id,
       device_posture_age_seconds, result, policy_id
FROM normalized_ztna_decisions
WHERE device_posture_age_seconds > 300
  AND resource_id = 'finance-report-api'
  AND event_time >= TIMESTAMP '2026-11-28 10:00:00'
ORDER BY event_time;
~~~

Một kết quả **ALLOW với stale signal** đáng điều tra nếu policy đòi max_age=300. Tuy nhiên có thể policy/version/signal source khác; đối chiếu **actual policy version và cached decision age** trước kết luận.

### 30.3. Tương quan risk signal và revoke decisions

~~~sql
SELECT i.event_time AS risk_event_time,
       i.subject_id, i.event_type AS risk_event,
       z.event_time AS decision_time, z.result,
       z.policy_version, z.pep_id
FROM normalized_identity_events i
LEFT JOIN normalized_ztna_decisions z
  ON z.human_subject = i.subject_id
 AND z.event_time >= i.event_time
 AND z.event_time < i.event_time + INTERVAL '15' MINUTE
WHERE i.event_type = 'HIGH_RISK_SESSION'
  AND i.event_time >= TIMESTAMP '2026-11-28 10:00:00';
~~~

**Đây không phải bằng chứng tự động:** join chỉ theo user + thời gian có thể ghép nhầm nhiều sessions. Trong production nên liên kết **stable session/device IDs và trusted event correlation**, xử lý event arrival lag và giới hạn retention.

### 30.4. Kiểm tra policy rollout giữa các PEP

~~~sql
SELECT pep_id, region, policy_version, result,
       COUNT(*) AS decision_events
FROM normalized_ztna_decisions
WHERE event_time >= TIMESTAMP '2026-11-28 10:00:00'
GROUP BY pep_id, region, policy_version, result
ORDER BY pep_id, policy_version;
~~~

**COUNT(*) là số event**, không phải số unique users/requests. Một user có thể tạo nhiều decisions và exporter có thể replay records; cần dedup event_id và mẫu số thích hợp.

## 31. Chỉ số SLO và dashboard cho truy cập theo ngữ cảnh

| Nhóm | Metric đề xuất | Lưu ý |
|---|---|---|
| **Coverage** | % protected apps reachable **chỉ qua PEP** | Phải test direct route, không suy từ cấu hình |
| **Identity** | % decisions với user/workload identity verified | Anonymous public access có thể là ngoại lệ đúng |
| **Posture** | % sensitive decisions dùng fresh device/workload signals | Không tính Unknown là compliant |
| **Enforcement** | % PDP DENY được PEP chặn thực sự | Cần kiểm chứng final disposition |
| **Revocation SLO** | Thời gian từ revoke/high-risk signal đến PEP termination | Đo cả long-lived connections |
| **Policy drift** | % PEPs trên đúng policy version | Multi-region failover có thể lệch |
| **Availability** | PEP/PDP/connector health, p95/p99 decision latency | Không đánh đổi unrestricted access để có latency tốt |
| **User impact** | False deny rate, step-up completion, help-desk tickets | Quá nhiều challenge tạo operational friction |
| **Machine identity** | Cert expiring soon, attestation failures, mTLS denied | Expiry và trust domain theo env |
| **Telemetry** | Log ingestion lag, dropped events, missing heartbeat | Không dựa chỉ vào tổng DENY |
| **Privilege** | JIT grant duration, expired-but-active sessions | Session expiry khác resource mutation cleanup |
| **Privacy** | Access audits, retention violations, redaction failures | Security logs cũng là dữ liệu nhạy cảm |

### 31.1. Không đưa user/session ID vào metric labels

**User ID, device ID, IP, request ID, trace ID, token ID** có cardinality cao và có thể gây rò dữ liệu. Dùng labels giới hạn như **resource class, policy ID, reason code, region, PEP version, result**, còn identity cụ thể nằm trong logs với RBAC.

### 31.2. Chia mẫu số đúng

Tỷ lệ **STEP_UP** nên tính trên những requests/operations đủ điều kiện step-up; tỷ lệ revocation success nên dựa trên **các phiên được yêu cầu revoke**, không phải mọi login. Một ZTNA product có thể chỉ instrument web requests, không cover SSH sessions; dashboard phải nói rõ **coverage boundary**.

## 32. Runbook triển khai policy theo user và workload

### Bước 1 — Inventory và phân loại tài nguyên

Liệt kê apps, APIs, admin endpoints, databases, cloud accounts và workloads. Gắn **owner, classification, route/protocol, network path, identity requirements, compliance obligations**, xác định đường public/private/VPN/NodePort và trạng thái TLS.

### Bước 2 — Phân tích threat model và principal

Xác định **human users/roles, contractor/guest, CI automation, Kubernetes SAs/SPIFFE IDs, cloud roles**, cùng các nguy cơ **credential theft, unmanaged device, role escalation, direct origin, gateway bypass, lateral movement và confused deputy**.

### Bước 3 — Định nghĩa sources of truth

Chọn **IdP, MFA/assertion provider, MDM/EDR, workload identity issuer, resource catalog, policy repo, risk engine**. Với mỗi signal phải ghi **issuer, binding, maximum age, failure behavior, owner và audit**.

### Bước 4 — Chọn enforcement points

- ZTNA edge/connector cho human private-app access.
- API gateway để xác minh tokens/scopes và route permissions.
- Mesh mTLS/AuthorizationPolicy cho service-to-service.
- NetworkPolicy/firewall/SG/NSG để chặn direct origin và lateral movement.
- Backend AuthZ cho object/tenant/business action.
- PAM/DB/SSH gateway cho privileged protocols.

### Bước 5 — Thiết kế least-privilege policy

Tạo ma trận **principal → device/workload posture → resource → action → contextual requirements → decision/obligations**. Mặc định DENY khi thuộc tính critical missing/stale. Tách **human policies và nonhuman policies**, không trộn bearer tokens.

### Bước 6 — Policy-as-code và kiểm thử nguồn thuộc tính

Lưu policy trong repo, có schema validation, role review, lint/tests; kiểm tra **untrusted header spoofing, issuer/audience/time, group revocation, MDM age, SPIFFE peer identity**. Đảm bảo decision-id/policy-version xuất ra logs và PEP thực hiện đúng.

### Bước 7 — Staging ALLOW / DENY / STEP_UP / REVOKE

Thử legitimate access, wrong role, wrong workload, unmanaged/stale device, high risk, token revoked, MFA expired và session đang mở. Đo **PEP final behavior**, không chỉ PDP output.

### Bước 8 — Canary và failover

Rollout một app/nhóm users, theo dõi PEP/PDP latency, help-desk impact và application SLI. Test các PEP ở nhiều regions, DNS alternate routes, IPv4/IPv6, connector failover, session cache và direct origin denied.

### Bước 9 — Vận hành liên tục

Theo dõi policy drift, unauthorized allow, privileged grants, device compliance coverage, mTLS cert expiries, risk event propagation, SIEM ingestion và periodic access review. Rút quyền cũ theo employment/contract lifecycle.

### Bước 10 — Recovery và retirement

Có rollback policy change, khôi phục PIP/PDP/connector theo HA plan, emergency access riêng và xóa policy/connector/route cũ khi ứng dụng ngừng sử dụng. Không để **legacy VPN/public origin** thành đường bypass vĩnh viễn.

~~~mermaid
flowchart TD
    A[Resource inventory + classification] --> B[Verified user/workload/device sources]
    B --> C[PEP placement + network bypass inventory]
    C --> D[Least-privilege policy versioned in Git]
    D --> E[Static checks + positive/negative tests]
    E --> F{Correct ALLOW DENY STEP_UP REVOKE?}
    F -- No --> R[Correct PIP/PEP/schema/policy]
    R --> E
    F -- Yes --> G[Canary release]
    G --> H[Monitor latency, signal freshness, revocation SLO]
    H --> I[Review drift, incident lessons, rotate credentials]
~~~

## 33. Runbook xử lý người dùng bị DENY sai

### Tình huống

Một nhân viên Finance có quyền xem báo cáo nhưng nhận **403/Access denied** khi laptop vừa update EDR; người dùng trước đó vẫn truy cập được. Không tự cấp **allow-all** hoặc xóa device posture requirement để giải quyết ticket.

### Giai đoạn 1 — Phân biệt nguồn từ chối

1. Lấy **request/decision ID, timestamp UTC, user pseudonym, device reference, resource/action và PEP** từ log có quyền.
2. Xác định **PEP deny, IdP fail, MDM stale, connector outage hay backend 403**; đừng đổ lỗi ZTNA chỉ vì response là 403.
3. Xem **policy ID/version, signal issuer, assertion age, current role/MFA freshness và risk state**.
4. Kiểm tra request có đi qua **correct gateway** hoặc app direct backend path không.
5. So người dùng khác với cùng app/region/policy; nếu toàn bộ đều lỗi sau rollout, cân nhắc config/issuer outage.

### Giai đoạn 2 — Khắc phục có kiểm soát

| Nguyên nhân xác nhận | Hướng khắc phục |
|---|---|
| MDM posture stale | Yêu cầu device check-in/sync lại từ MDM, không tự tạo compliant assertion |
| EDR high-risk | Security/endpoint triage trước khi mở quyền nhạy cảm |
| MFA đã cũ | Thực hiện step-up theo session/action được yêu cầu |
| Role bị thu hồi đúng | Giữ deny; hướng người dùng tới access request workflow |
| Role mapping sai | Sửa IdP/group mapping có owner và approval |
| Workload certificate sai principal | Sửa service identity/trust, không disable mTLS |
| Policy rollout sai | Rollback policy version hẹp sau approval và negative tests |
| Connector/PEP outage | Khôi phục availability, không mở direct-origin bypass |
| App object-level deny | Điều tra application/tenant permission; ZTNA ALLOW không thay app AuthZ |

### Giai đoạn 3 — Xác minh

Chạy cả **Finance user/device đúng → ALLOW** và **guest hoặc unmanaged device → DENY**, cùng test **export step-up**. Kiểm tra logs **reason_code** không chứa credential/PII quá mức, revocation policy vẫn hoạt động và session TTL được enforce.

### Giai đoạn 4 — Hậu kiểm

Nếu lỗi xuất phát từ device sensor/latency, bổ sung **stale alert, support remediation path, PIP timeout metrics**. Nếu từ policy, bổ sung regression test. Không tạo exception **không có owner/expiry** để "tránh support tickets".

## 34. Runbook ứng phó khi tài khoản hoặc workload bị đánh cắp

### 34.1. Tình huống account session compromise

SOC nhận high-risk sign-in và EDR alert trong khi một phiên ZTNA đang có quyền đọc báo cáo tài chính.

**Bước 1 — Triage:** xác minh identity, device/session binding, timestamps, resource/action, PEP decisions và risk signal provenance; không kết luận chỉ dựa trên GeoIP.

**Bước 2 — Containment:** dùng IdP/PEP hỗ trợ để **revoke sessions/tokens, terminate protected connections, block device và hạn resource-specific permission** theo incident plan. Đánh giá **cache propagation và long-lived SSH/RDP/WebSocket sessions**.

**Bước 3 — Investigation:** xác minh data access/exfiltration evidence từ app logs, DLP, DNS, egress, proxy và cloud audit; "risk high" không tự chứng minh data theft.

**Bước 4 — Recovery:** cấp credential/identity mới có kiểm soát, khắc phục endpoint compromise, đánh giá lỗ hổng MFA/session-binding và test **ALLOW/DENY/revoke**.

### 34.2. Tình huống workload key hoặc CI identity bị lộ

Một CI role hoặc mesh workload có thể bị lạm dụng để gọi API nhạy cảm dưới identity hợp lệ.

- Xác định **SPIFFE ID/cloud role, certificate/credential scope, issuer/trust domain, CI/ref, last issuance và usage records**.
- Hạn quyền resource/route và **ngăn issuance/assume role mới**, cô lập workload/pipeline; không tự xóa bằng chứng.
- Nếu certificate bị lộ, xử lý **rotation/trust and active-session revocation** theo khả năng mesh; **xóa Pod không đảm bảo cert cũ lập tức vô hiệu**.
- Kiểm tra **user delegation**: workload đã bị compromise có thể dùng quyền của mình để yêu cầu dữ liệu ngoài phạm vi user dù mTLS pass.
- Bảo vệ **CI branch/environment, service account assignment, CA/issuer, cloud IAM role trust** và scan quyền thừa.
- Chỉ đổi root CA toàn hệ khi evidence/risk xác nhận cấp độ sự cố đó hoặc incident plan yêu cầu; leaf compromise và issuer compromise có phạm vi khác.

### 34.3. Phản ứng không được tạo đường bypass mới

Không xử lý bằng cách **disable mTLS, mở 0.0.0.0/0 tới backend, tắt device checking hoặc cho phép toàn finance group trong 24 giờ**. Khi cần emergency access, dùng **đường riêng có phê duyệt, giám sát, scope và expiry**, rồi hậu kiểm.

## 35. Mười hai tình huống thực tế

### Tình huống A — User ở VPN được vào toàn bộ subnet

**Triệu chứng:** nhân viên kết nối VPN hợp lệ để dùng portal nhưng có thể thử kết nối trực tiếp database hoặc bastion cùng CIDR.

**Vấn đề:** quyền vào **network segment** bị hiểu là quyền vào **mọi ứng dụng**. Chuyển tài nguyên phù hợp sang **per-app ZTNA**, hạn VPN routes, dùng SG/firewall/NetworkPolicy chặn lateral movement và bắt buộc app/DB authentication. Không chỉ thêm MFA cho VPN rồi giữ toàn subnet mở.

### Tình huống B — User hợp lệ trên thiết bị không quản lý

**Triệu chứng:** finance user có quyền đọc báo cáo nhưng đang dùng máy cá nhân chưa có posture assertion.

**Quyết định:** với tài liệu restricted, **UNKNOWN device không coi là compliant**. Có thể từ chối hoặc chuyển tới **managed-device onboarding/remediation**; dữ liệu internal ít nhạy cảm có thể được phép browser-only theo risk policy riêng. Không làm khách hàng mất quyền vĩnh viễn mà không có quy trình hỗ trợ.

### Tình huống C — MDM báo compliant nhưng user bị EDR đánh dấu high risk

**Triệu chứng:** posture assertion có giá trị **compliant** nhưng risk signal mới báo credential theft/malware.

**Phân tích:** một tín hiệu tốt không được bù trừ **explicit high-risk deny** khi policy coi EDR severity là critical. PDP cần **source timestamps, event propagation, deny precedence và session termination**. Không xóa EDR alert chỉ vì MDM state cũ.

### Tình huống D — Role bị thu hồi giữa phiên

**Triệu chứng:** nhân viên được chuyển bộ phận, group finance bị gỡ nhưng token cũ còn hiệu lực thêm một khoảng.

**Kiểm soát:** thiết kế **token/session TTL, revocation event, entitlement rechecks** theo resource risk. Thử session dài và báo cáo **revoke-to-enforcement SLO**; không tuyên bố revoke tức thì nếu PEP chỉ kiểm tra lúc connect.

### Tình huống E — User Finance hợp lệ, workload debug gọi thay BFF

**Triệu chứng:** user token đúng và thiết bị compliant, nhưng request tới Report API phát từ Pod debug có SPIFFE principal không được phép.

**Quyết định:** **DENY** vì workload principal không khớp. Không cấp phép dựa trên human user **một mình**; bảo vệ route, service-to-service identity và app authorization.

### Tình huống F — Workload orders có mTLS nhưng xuất dữ liệu của user khác

**Triệu chứng:** backend mTLS AuthZ cho orders nhưng orders gọi một endpoint export trả dữ liệu tenant khác.

**Nguyên nhân:** backend chỉ kiểm tra **service identity**, không kiểm tra **delegated human identity và object ownership**. Bổ sung scoped token exchange, tenant/resource authorization và business audit; mTLS không thay BOLA protection.

### Tình huống G — Contractor có thể gọi API admin qua private connector

**Triệu chứng:** user ngoài tổ chức được đăng nhập support portal nhưng connector mapping cho phép địa chỉ IP/port của admin API trên cùng máy.

**Vấn đề:** policy ở PEP áp ở **host/port chung**, không phân biệt ứng dụng/route. Tách connector/resource mapping, dùng app-aware gateway và **backend authorization**. Không cho contractor một TCP tunnel đến toàn host nhạy cảm khi chỉ cần portal.

### Tình huống H — Một gateway dự phòng dùng policy cũ

**Triệu chứng:** region A đã chặn external guest, region B failover vẫn cho vào do cached policy trước khi thay.

**Xử lý:** đồng bộ **policy version, active rule IDs, PIP cache invalidation và rollout health**; test failover cả ALLOW/DENY. Nếu region dự phòng không đáp ứng guardrail, không dùng nó làm đường unrestricted backup.

### Tình huống I — SSH session không bị ngắt sau revocation

**Triệu chứng:** IdP revoke user, các phiên SSH mới bị chặn nhưng một shell đã mở vẫn hoạt động.

**Giải thích:** PEP chỉ kiểm tra lúc tạo tunnel. Cần giải pháp **session monitoring/termination, short session max/idle timeout**, đóng network path theo runbook và đo SLO. Không kỳ vọng JWT expiry tự đóng TCP socket.

### Tình huống J — Mất MDM làm mọi tài khoản bị deny

**Triệu chứng:** posture provider outage khiến toàn bộ người dùng bị từ chối restricted portal.

**Phân tích:** deny có thể là **fail-safe đúng thiết kế**. Xem availability strategy, dùng remediation/short-lived preapproved access nếu risk owner cho phép, không đổi mặc định UNKNOWN→COMPLIANT. Bổ sung HA, cache TTL và cảnh báo provider health.

### Tình huống K — ZTNA cho phép nhưng backend vẫn 403

**Triệu chứng:** PEP ghi ALLOW, backend 403 vì user không sở hữu object.

**Giải thích:** ZTNA xác minh quyền vào **ứng dụng**, backend quyết định **quyền dữ liệu**. Đây có thể là defense in depth đúng, không phải bug policy. Dùng request ID và decision_source để giải thích.

### Tình huống L — Direct origin bypass ZTNA

**Triệu chứng:** app private công bố qua ZTNA nhưng máy chủ còn public LB/NodePort/IPv6 endpoint trực tiếp.

**Giải pháp:** bảo vệ origin bằng private network, security groups, allowed connectors, service mesh/backend AuthZ, quét cấu hình exposure qua **inventory và kiểm thử được phép**. Một rule PDP đúng không thể bảo vệ traffic không đi qua PEP.

## 36. Ma trận 48 kiểm thử ALLOW / DENY / STEP_UP / REVOKE

**Phạm vi:** chỉ chạy trên **môi trường thử nghiệm được cấp phép** với users/devices/workloads/tenants được tạo cho mục đích kiểm thử. Không dùng tài khoản thật của người khác, không brute-force login/MFA, không truy xuất dữ liệu trái phép và không cố gây sự cố production.

| ID | Kịch bản | Quyết định/hành vi mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | User đúng role, SSO hợp lệ | ALLOW internal portal theo scope | IdP + PEP decision |
| **T-02** | User không có role tương ứng | DENY restricted app | Policy reason |
| **T-03** | Account disabled/revoked | DENY phiên mới | IdP/PDP audit |
| **T-04** | ID token dùng như access token sai audience | DENY API | Token validation |
| **T-05** | Token sai issuer/audience/signature trong lab | DENY, không tin claims | IdP/API log |
| **T-06** | User đúng role và device compliant có nguồn tin | ALLOW action read | PIP assertion + PEP |
| **T-07** | Device chưa enroll/UNKNOWN | DENY/REMEDIATION theo classification | Posture decision |
| **T-08** | Device posture assertion stale | Không được coi compliant | Timestamp + reason |
| **T-09** | Device posture assertion do client tự gửi | Không được chấp nhận | PEP trusted signal check |
| **T-10** | Device compliant nhưng binding sang session khác | DENY/rebind theo policy | Device/session binding |
| **T-11** | Disk encryption disabled khi policy yêu cầu | DENY/REMEDIATION | Verified MDM state |
| **T-12** | EDR high-risk trong khi device vẫn compliant | DENY hoặc REVOKE | Risk decision precedence |
| **T-13** | MDM/EDR unavailable | Không mặc định ALLOW | Failure matrix |
| **T-14** | MFA thiếu/không có | STEP_UP hoặc DENY | MFA requirement |
| **T-15** | MFA đã hết freshness | STEP_UP khi action nhạy cảm | Auth time |
| **T-16** | MFA mới gắn đúng session/action | ALLOW nếu mọi điều kiện khác đạt | IdP/PEP logs |
| **T-17** | MFA tốt nhưng role thiếu | DENY, MFA không bù role | Policy rule |
| **T-18** | User đúng role nhưng resource khác scope | DENY | Resource/action mapping |
| **T-19** | Read được phép, export chưa được phép | READ ALLOW, EXPORT DENY/STEP_UP | App/PEP |
| **T-20** | User có quyền app nhưng không sở hữu object | Backend DENY | Application AuthZ |
| **T-21** | Contractor đúng ticket ownership | ALLOW chỉ ticket được giao | Portal object AuthZ |
| **T-22** | Contractor hết hạn sponsorship | DENY | Contract lifecycle |
| **T-23** | BYOD gọi internal low-risk portal | Theo browser-only policy, không mở mạng rộng | PEP scope |
| **T-24** | BYOD vào admin API | DENY | Device classification |
| **T-25** | Verified workload đúng SPIFFE ID | ALLOW exact service/port | mTLS + mesh |
| **T-26** | Workload khác trust domain | DENY nếu chưa federation | Trust check |
| **T-27** | HTTP header tự khai X-Workload-ID | Bỏ qua/strip và dùng peer identity | Gateway headers |
| **T-28** | Workload mTLS hợp lệ nhưng sai ServiceAccount | DENY service operation | Mesh AuthorizationPolicy |
| **T-29** | Workload userless job đúng machine policy | ALLOW qua machine branch | Workload attestation |
| **T-30** | Workload có certificate nhưng issuer CA không tin | DENY mTLS | PKI logs |
| **T-31** | CI từ branch không được duyệt assume deploy role | DENY federation trust | CI + cloud IAM |
| **T-32** | Human request qua BFF nhưng không có delegated user permission | DENY restricted data | Backend + token exchange |
| **T-33** | User A token dùng để xem tenant B | DENY object-level | App audit |
| **T-34** | Session ALLOW bị revoke từ IdP | PEP terminate trong SLO | Session/IdP events |
| **T-35** | Device risk đổi high giữa WebSocket session | Re-evaluate/ngắt theo capability/SLO | Open session evidence |
| **T-36** | SSH đang mở khi entitlement hết hạn | Ngắt/giới hạn theo session policy | SSH gateway audit |
| **T-37** | Decision cache quá TTL | Re-evaluate thay vì tiếp tục ALLOW | PDP cache telemetry |
| **T-38** | Resource classification đổi internal→restricted | Policy mới áp không còn allow cũ | Resource version/PEP |
| **T-39** | Explicit DENY và RBAC ALLOW cùng tồn tại | DENY thắng theo policy semantics | Effective policy test |
| **T-40** | PDP unavailable khi admin SSH | DENY theo failure policy | Availability and decision |
| **T-41** | PEP/connector outage | Availability error, không mở bypass | Connector and firewall |
| **T-42** | Logging exporter outage | Alert telemetry gap, policy vẫn enforce | Exporter health/PEP |
| **T-43** | Public origin direct IP từ lab | Không bypass được ZTNA PEP | Cloud network reachability |
| **T-44** | IPv6/alternate DNS bypass attempt trong lab | Không có đường vào ngoài policy | Dual-stack/DNS test |
| **T-45** | Secondary PEP region dùng policy cũ | Drift detected, không dùng unrestricted failover | Policy revision audit |
| **T-46** | ZTNA ALLOW nhưng DB role chỉ SELECT | DB từ chối UPDATE theo scope | DB RBAC audit |
| **T-47** | Admin JIT grant hết hạn | Quyền mutation tiếp theo bị DENY | IAM/PAM audit |
| **T-48** | Rollback policy sau canary | Legitimate access ALLOW, unauthorized DENY tiếp tục đúng | Regression report |

### 36.1. Mỗi test cần xem ít nhất hai lớp

Ví dụ **debug workload bị timeout** có thể do **NetworkPolicy deny**, không chứng minh mesh policy đã từ chối identity; cần một kiểm thử identity riêng nơi network path được phép. Tương tự **backend 403** có thể từ app, không phải ZTNA.

### 36.2. Test không chỉ là HTTP 200/403

Với **SSH/RDP/TCP**, xem session creation, re-authorization, termination và server-side authorization. Với **mTLS**, xem verified peer certificate/trust domain. Với **device**, kiểm tra assertion issuer/binding/freshness. Với **revocation**, đo thời gian từ event đến phiên thực bị cắt.

### 36.3. Recheck và fake headers

Negative test quan trọng là gửi trong lab **untrusted X-User, X-Device-Posture, X-Workload-ID, X-Forwarded-For** và xác minh PEP bỏ/ghi đè; không mô phỏng nguồn thật bằng cách chỉ điền trường "verified=true" trong JSON mà bỏ validation.

## 37. Những ngộ nhận và phản ví dụ

| Ngộ nhận | Diễn giải đúng |
|---|---|
| **“Vào VPN nghĩa là đáng tin.”** | VPN xác lập đường nối; quyền ứng dụng và device/workload vẫn cần xét. |
| **“Ở trong private VPC là đủ Zero Trust.”** | Vị trí mạng không xác minh user, tenant hay workload. |
| **“ZTNA thay firewall.”** | Firewall/NetworkPolicy ngăn bypass và giới hạn lateral reachability. |
| **“MFA thành công cho phép mọi app.”** | MFA chỉ xác thực; resource/action/role vẫn phải cho phép. |
| **“Role đúng có thể bỏ device compliance.”** | Phụ thuộc policy, với restricted app thường cần cả hai. |
| **“Thiết bị từng compliant nghĩa hiện tại compliant.”** | Phải xét assertion freshness/TTL và event mới. |
| **“MDM đang offline thì coi device tốt.”** | UNKNOWN/STALE phải xử lý theo risk/failure policy. |
| **“X-Device-Compliant:true là bằng chứng.”** | Header tự khai phải được xác minh nguồn/binding hoặc loại bỏ. |
| **“GeoIP nói được người dùng là ai.”** | GeoIP chỉ là tín hiệu có sai số, không phải principal. |
| **“Một IP = một user.”** | NAT/VPN/CDN/roaming phá giả định này. |
| **“SPIFFE ID tự khai là chứng thư.”** | ID chỉ là chuỗi; SVID/cert và proof of key mới là bằng chứng. |
| **“mTLS ALLOW mọi user action.”** | mTLS xác thực workload, backend phải kiểm tra user/tenant/object. |
| **“Workload không có laptop nên bỏ context-aware policy.”** | Có machine policy riêng dựa trên attestation/role/resource. |
| **“User được vào BFF nên BFF được xuất dữ liệu bất kỳ.”** | Phải giới hạn delegation và backend AuthZ để tránh confused deputy. |
| **“Token chữ ký đúng là chắc còn quyền.”** | Quyền có thể bị thu hồi giữa TTL, cần recheck theo risk. |
| **“Continuous evaluation nghĩa gọi PDP mọi packet.”** | Thực tế gồm session/operation checks, timers và event-driven triggers. |
| **“Revoke user sẽ reset tất cả SSH ngay.”** | Cần PEP termination và SLO; TCP session có thể còn sống. |
| **“PDP DENY bảo đảm request bị chặn.”** | Phải có PEP thực thi trên data path thật. |
| **“Policy ALLOW của PEP bằng quyền dữ liệu backend.”** | Object/tenant authorization là lớp riêng. |
| **“Chỉ test đường ZTNA thành công là đủ.”** | Phải test direct origin, NodePort, alternate DNS/IPv6 và negative access. |
| **“Một query SQL được kiểm soát qua ZTNA TCP tunnel.”** | TCP PEP thường không hiểu SQL operations; DB RBAC vẫn cần. |
| **“Risk score cao có thể được bù bằng MFA.”** | Explicit deny/critical control không nên bị bù điểm. |
| **“Bật WAF nghĩa đã có user access control.”** | WAF tập trung HTTP threats, không thay entitlement/context. |
| **“Không có DENY log nghĩa không có xâm nhập.”** | Có thể có logging gap hoặc bypass PEP. |
| **“Policy-as-code tự block mạng.”** | Cần PEP/connector/mesh/backend enforcement. |
| **“Được cấp JIT 10 phút thì thay đổi config tự hết hạn sau 10 phút.”** | Role expiry khác lifecycle của resource đã sửa. |
| **“Một policy set cho mọi cloud/SaaS/mesh không cần test.”** | Semantics, source attributes và session capabilities khác nhau. |
| **“Càng thu nhiều vị trí/hành vi người dùng càng tốt.”** | Cần data minimization, purpose limitation và kiểm soát quyền logs. |

## 38. Checklist thiết kế và vận hành production

- [ ] Có resource inventory, classification, owners và dependency paths cho từng ứng dụng/API.
- [ ] Định nghĩa human principals, workload identities, contractors và automation riêng.
- [ ] IdP dùng stable subject/issuer; token được xác minh signature/introspection/audience/type.
- [ ] Có phương án MFA/step-up mới cho privileged actions và high-risk operations.
- [ ] User entitlement gắn resource/action cụ thể, không chỉ quyền vào VPN/subnet.
- [ ] Device signals đến từ MDM/EDR/attestation tin cậy và ràng buộc đúng session.
- [ ] Policy phân biệt **COMPLIANT/NONCOMPLIANT/UNKNOWN/STALE/ERROR**.
- [ ] Có signal freshness, TTL và re-evaluation events theo risk/asset.
- [ ] BYOD và unmanaged devices có rule riêng, không mặc định được restricted apps.
- [ ] Workload có identity đã kiểm chứng: mTLS SPIFFE/SVID hoặc cloud workload federation.
- [ ] Không nhận workload identity, user role, tenant hoặc device status từ untrusted headers.
- [ ] Kubernetes ServiceAccount/Pod creation và service mesh policy được quản trị bằng RBAC/admission.
- [ ] CA/trust domain, private keys, token issuer và certificate rotation có owner.
- [ ] Exact workload principal và resource/route/port được hạn theo least privilege.
- [ ] Human-initiated service calls có verified delegation context nếu backend cần user rights.
- [ ] Backend thực hiện tenant/object-level authorization; không phụ thuộc duy nhất ZTNA.
- [ ] Risk engine signals có provenance, timestamp, confidence và false-positive workflow.
- [ ] Có explicit deny, missing-critical-context handling và policy conflict resolution.
- [ ] STEP_UP/REMEDIATION/READ_ONLY được PEP/app thực thi thật, không chỉ ghi JSON.
- [ ] ZTNA PEP nằm trên đường ingress thật, backend không có direct-origin bypass.
- [ ] NodePort, public LB, alternate DNS/IPv6, VPN route và unmeshed paths được inventory.
- [ ] Cloud firewall/NSG/SG và CNI NetworkPolicy chặn lateral movement ngoài scope.
- [ ] TLS/mTLS, server hostname/peer validation không bị tắt để chữa lỗi.
- [ ] Legacy SSH/RDP/DB truy cập qua gateway có session limits và protocol-aware controls.
- [ ] Database/app role permissions được kiểm tra riêng với quyền mở TCP connection.
- [ ] Policy resources, action semantics và identity trust được kiểm tra giữa regions.
- [ ] Token/session/decision caches có TTL, invalidation và revocation SLO đo được.
- [ ] Long-lived SSH/RDP/WebSocket sessions được kiểm thử termination khi revoke.
- [ ] PIP/PDP/PEP outages có failure matrix và emergency process được duyệt.
- [ ] Truy cập privileged được cấp JIT/PAM, approval, short session, audit và expiry.
- [ ] JIT resource mutations có cleanup/reconciliation độc lập với session.
- [ ] Policy versioned trong Git, có ownership, CI checks, security reviews và rollback.
- [ ] PEP actions phân biệt **decision từ PDP** với **final disposition thực tế**.
- [ ] Có audit event gồm decision ID, source, policy revision, reason, principal/resource/action.
- [ ] Không log raw tokens, private keys, full query/body nhạy cảm hay vị trí chi tiết thừa.
- [ ] Logs có RBAC, retention, ingress/tenant scope và kiểm tra exporter health.
- [ ] Dashboard đo policy coverage, false DENY, revocation lag, PEP latency, signal freshness.
- [ ] Có detection high-risk allowed session, trust-domain confusion, unauthorized workload call.
- [ ] Positive tests chứng minh người dùng hợp lệ làm việc được sau thay đổi policy.
- [ ] Negative tests chứng minh user/device/workload trái quyền bị chặn.
- [ ] Step-up/Revoke tests chứng minh policy thay đổi có hiệu lực trong thời gian đã cam kết.
- [ ] Đã diễn tập PIP outage, compromise, failover, rollback và emergency access.
- [ ] Quyền truy cập và ngoại lệ của contractor/service account có owner và expiry.
- [ ] Chính sách xử lý dữ liệu thiết bị/người dùng tuân thủ purpose/consent/retention phù hợp.
- [ ] Không chuyển từ thiếu telemetry sang mở truy cập vô điều kiện.
- [ ] Xóa connector/route/legacy VPN access sau migration khi không còn cần.

## 39. Câu hỏi tự kiểm tra

**1. Context-aware policy khác RBAC như thế nào?**  
RBAC chủ yếu dựa trên role; context-aware policy bổ sung device, workload, resource, action, risk, time, signal freshness và các điều kiện khác với nguồn tin cậy.

**2. Vì sao user đã MFA vẫn có thể bị DENY?**  
Vì user có thể thiếu role, device không compliant, workload không được phép, resource nằm ngoài scope hoặc high-risk deny đang có hiệu lực.

**3. PEP khác PDP như thế nào?**  
PDP tính quyết định theo policy/context; PEP thực sự chặn/cho phép luồng trên data path. Không có PEP đúng đường thì PDP DENY không chặn được traffic bypass.

**4. PIP là gì trong bài?**  
Là nguồn thông tin thuộc tính như IdP, MDM/EDR, workload issuer, resource catalog và risk engine; đây là cách tổ chức architecture, không bắt buộc tách thành service riêng ở mọi sản phẩm.

**5. Device.compliant=true có thể do browser gửi được không?**  
Không được tin nguyên bản. Cần assertion đã xác minh nguồn, ràng buộc device/session, kiểm tra timestamp và không hết hạn.

**6. Vì sao UNKNOWN/STALE không được coi là COMPLIANT?**  
Vì thiếu hoặc quá hạn bằng chứng; với restricted resource, phải DENY/remediation hoặc dùng fallback được risk owner phê duyệt.

**7. Workload identity khác human identity thế nào?**  
Workload identity xác minh dịch vụ/process qua SVID/mTLS/cloud role; human identity xác minh người dùng và entitlement. Một request có thể cần cả hai.

**8. mTLS chứng minh điều gì?**  
Peer sở hữu credential hợp lệ được cấp theo trust domain; nó không tự cho quyền thực hiện mọi API operation hoặc đọc mọi dữ liệu user.

**9. Vì sao user token được backend chấp nhận vẫn cần workload authorization?**  
Để ngăn workload không được phép dùng user token hoặc gọi API ngoài luồng; và để giới hạn lateral movement nếu một service bị xâm nhập.

**10. Confused deputy trong microservice là gì?**  
Một service có quyền mạnh thực hiện action cho user thiếu quyền vì backend chỉ kiểm tra service identity mà không xác minh delegation/user-object authorization.

**11. Step-up MFA phải gắn với yếu tố nào?**  
Đúng authenticated subject, session/device và operation/resource; có thời hạn freshness ngắn theo yêu cầu.

**12. Một user bị revoke có bị mất SSH hiện tại lập tức không?**  
Không mặc định. Cần PEP hỗ trợ termination/revalidation và đo revoke-to-enforcement SLO.

**13. Source IP trusted có phải user identity không?**  
Không. NAT/CDN/VPN và roaming khiến IP không đại diện duy nhất cho một người; headers forwarded còn có thể bị spoof.

**14. ZTNA thay được NetworkPolicy/firewall không?**  
Không. Các lớp mạng giúp chặn direct-origin bypass và lateral movement, trong khi ZTNA đưa ra access decision dựa trên identity/context.

**15. Với CI/CD không có device MDM, policy nên làm gì?**  
Dùng machine policy riêng theo workload identity, signed CI federation claims, environment, resource/action và runtime posture nếu cần; không cho phép tự do vì không có laptop.

**16. Điều gì khác nhau giữa ALLOW policy và backend trả 403?**  
ZTNA có thể cho vào ứng dụng, còn backend từ chối resource/tenant action theo business authorization. Hai lớp này độc lập.

**17. Khi PDP không hoạt động, cách phản ứng an toàn là gì?**  
Tuân theo failure matrix theo resource risk, thường DENY admin/restricted actions nếu thiếu kiểm chứng; chỉ dùng exception có owner, TTL và audit.

**18. Vì sao phải lưu policy_version trong security log?**  
Để biết quyết định phát sinh dưới phiên bản nào, phát hiện policy drift giữa PEP/regions và giải thích thay đổi ALLOW/DENY sau rollout.

**19. Làm sao đánh giá revocation?**  
Gửi revoke event/test vào lab, theo dõi lúc PEP nhận, lúc access bị chặn và lúc long-lived session đóng; đo SLO thay vì chỉ nhìn IdP status.

**20. Điều kiện tối thiểu cho Zero Trust context-aware triển khai production?**  
Verified user/workload/device signals có freshness, policy least privilege, PEP trên đường traffic, app-level AuthZ, network anti-bypass, logging/detection, positive/negative/step-up/revoke tests và incident/failure runbooks.

## 40. Tài liệu tham khảo

- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): khái niệm ZTA, subject/resource access, policy engine, administrator, enforcement và continuous evaluation.
- [NIST SP 800-207A — A Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Cloud Environments](https://csrc.nist.gov/pubs/sp/800/207/a/final): identity-based access, microservices và multi-cloud.
- [NIST SP 800-162 — Guide to Attribute Based Access Control](https://csrc.nist.gov/pubs/sp/800/162/final): mô hình ABAC, subject/object/action/environment attributes.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): least privilege, authorization, logging, access control và continuous monitoring.
- [NIST SP 800-63 — Digital Identity Guidelines](https://pages.nist.gov/800-63-4/): identity assurance, authentication và federation; đối chiếu phiên bản hiện hành khi áp dụng.
- [CISA — Zero Trust Maturity Model](https://www.cisa.gov/zero-trust-maturity-model): các trụ identity, devices, networks, applications/workloads và data.
- [Open Policy Agent — Documentation](https://www.openpolicyagent.org/docs/): policy-as-code và Rego evaluation.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): user authentication, ID tokens và claims.
- [OpenID Shared Signals](https://openid.net/wg/sharedsignals/): khái niệm liên thông security/session signals và CAEP.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access tokens, redirects và threat model OAuth.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token handling và threat considerations.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint và semantics.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token status/claims qua authorization server.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegated token exchange và actor context.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS-bound access token và OAuth client authentication.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449): DPoP và proof-of-possession-bound access tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims và audience.
- [W3C Web Authentication (WebAuthn)](https://www.w3.org/TR/webauthn-3/): phương pháp authentication dựa trên public-key credentials.
- [SPIFFE — Workload Identity Overview](https://spiffe.io/docs/latest/spiffe-about/overview/): SPIFFE IDs, SVIDs và trust domains.
- [SPIFFE — Workload API](https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/): cấp identity/trust bundles với workload attestation.
- [Istio — Security Concepts](https://istio.io/latest/docs/concepts/security/): workload identity, mTLS, AuthorizationPolicy và certificate lifecycle.
- [Istio Ambient — L4 Policy](https://istio.io/latest/docs/ambient/usage/l4-policy/): enforcement tại ztunnel và giới hạn L7.
- [Istio Ambient — Waypoint](https://istio.io/latest/docs/ambient/usage/waypoint/): L7 policy routing, waypoint và bypass.
- [Kubernetes — NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): giới hạn network reachability theo Pod/namespace/port.
- [Kubernetes — RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/): kiểm soát principal permissions và ServiceAccount misuse.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, object-level checks.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event design, privacy, security logging và log integrity.

**Ghi nhớ:** **Context-aware policy theo người dùng và workload** là quyết định dựa trên **danh tính đã xác minh**, **resource/action cụ thể**, **device/workload posture có nguồn và độ mới rõ**, **rủi ro phiên** và **thời gian**; **không mặc định tin chỉ vì có VPN, IP nội bộ hay một lần MFA thành công**. Mô hình phải kết hợp **PDP tính quyền, PEP thực thi trên đúng đường traffic, PIP cung cấp thuộc tính đáng tin**, cùng **mTLS/workload identity, application authorization, segmentation, TLS, audit và cơ chế re-evaluation/revocation**. Quyền truy cập an toàn chỉ được chứng minh khi **user/workload hợp lệ được ALLOW, chủ thể trái quyền bị DENY, thao tác nhạy cảm STEP_UP và phiên bị thu hồi thật sự bị REVOKE trong SLO**, kể cả khi failover hoặc có đường mạng phụ.







