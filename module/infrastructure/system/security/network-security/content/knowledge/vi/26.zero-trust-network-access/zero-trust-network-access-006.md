# Continuous verification và thay đổi mức tin cậy trong Zero Trust Network Access

## 1. Vì sao quyết định cấp quyền ban đầu chưa đủ?

Một nhân viên đăng nhập ứng dụng quản trị Production lúc 09:00 bằng **phương thức xác thực mạnh**, trên một laptop đang đáp ứng yêu cầu bảo mật. Nếu đến 09:20 laptop bị đánh dấu nhiễm mã độc, phiên đăng nhập bị nghi chiếm đoạt hoặc vai trò quản trị của nhân viên bị thu hồi, quyết định **ALLOW lúc 09:00** không nên mặc nhiên giữ hiệu lực đến hết ngày. Đây là vấn đề trọng tâm của **continuous verification** trong **Zero Trust Network Access (ZTNA)**: **tính tin cậy là đánh giá có điều kiện, gắn với tài nguyên và thời điểm, không phải trạng thái được cấp một lần rồi giữ vĩnh viễn**.

Trong module **SECURITY_NETWORK_SECURITY**, nội dung này kết nối **phân đoạn mạng, firewall, VPN, IDS/IPS, TLS/mTLS, DNS, bảo mật mạng cloud, threat modeling và giám sát lưu lượng**. ZTNA giúp tổ chức cấp quyền tới **ứng dụng hoặc dịch vụ cụ thể** theo **danh tính, trạng thái thiết bị, ngữ cảnh kết nối, rủi ro phiên và chính sách tài nguyên**, thay vì coi toàn bộ người dùng đã vào mạng riêng là đáng tin. Tuy nhiên ZTNA **không thay thế** authorization ở ứng dụng, quản lý lỗ hổng, network segmentation hoặc quy trình ứng phó.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **verify explicitly, least privilege, assume breach** và ý nghĩa của **continuous/adaptive verification**.
2. Phân biệt **identity authentication, device posture, session assurance, resource authorization, network trust và risk signals**.
3. Vẽ kiến trúc **Policy Decision Point (PDP), Policy Enforcement Point (PEP), identity/device/risk signals** và đường kết nối.
4. Thiết kế các trạng thái **ALLOW, STEP_UP, RESTRICT, QUARANTINE, REVOKE/DENY** cùng điều kiện chuyển trạng thái.
5. Hiểu **event-driven re-evaluation, periodic checks, token/session lifetime, cache và propagation delay**.
6. Nhận diện giới hạn khi **thu hồi quyền giữa phiên TCP, WebSocket, gRPC stream, VPN tunnel hoặc HTTP/2 connection**.
7. Kết hợp **MFA, endpoint detection, MDM, IAM, app authorization, microsegmentation, SIEM** theo ranh giới tin cậy.
8. Viết chính sách minh họa, thực hành **mô phỏng offline**, lập ma trận kiểm thử và runbook thay đổi mức tin cậy.

## 2. Zero trust không đồng nghĩa “không tin ai”

**Zero trust** không phủ nhận mọi danh tính hay cấm tất cả kết nối. Nó yêu cầu **không cấp mức tin cậy mặc định chỉ vì nguồn ở một subnet nội bộ, kết nối qua VPN hoặc đã đăng nhập trước đó**. Quyền truy cập được quyết định theo **policy cho đối tượng/tài nguyên cụ thể**, sau đó **được giám sát và đánh giá lại** khi các điều kiện có thể thay đổi.

Ba ý tưởng quan trọng thường được nhắc tới từ kiến trúc zero trust:

| Nguyên tắc | Ý nghĩa vận hành | Ví dụ |
| --- | --- | --- |
| **Verify explicitly** | Kiểm chứng identity, device, context và policy tại những điểm ra quyết định | Token hợp lệ nhưng device noncompliant vẫn không vào Prod admin |
| **Least privilege** | Chỉ cấp tài nguyên, phương thức và thời gian cần thiết | Hỗ trợ viên được xem ticket, không được đọc secrets hoặc vào DB |
| **Assume breach** | Thiết kế giới hạn lateral movement, đo lường và thu hồi quyền | Khi account bị đánh cắp, PEP có thể cắt quyền nhạy cảm ngay khi có tín hiệu |

**Continuous verification** không nhất thiết có nghĩa chạy **MFA ở mọi packet** hoặc kiểm tra tất cả cảm biến mỗi millisecond. Nó là **chiến lược đánh giá lại quyết định trong suốt vòng đời truy cập**, kết hợp các trigger khi có sự kiện, kiểm tra định kỳ, giới hạn TTL và chốt chính sách tại các PEP có khả năng thực thi.

### 2.1. Hai câu hỏi không thể đánh đồng

**“Người dùng có phải Alice?”** là bài toán xác thực danh tính. **“Alice hiện có được xuất dữ liệu khách hàng từ ứng dụng X trên thiết bị Y không?”** là quyết định authorization theo **vai trò, tài nguyên, hành động, session context và mức assurance hiện tại**. Identity đúng không đảm bảo action được phép.

### 2.2. Tin cậy không phải một số duy nhất

Một người dùng có thể:

- Được phép mở **knowledge base công khai của công ty** từ thiết bị không quản lý.
- Được phép truy cập **CRM đọc dữ liệu ít nhạy cảm** sau xác thực phù hợp.
- Chỉ được phép **đổi cấu hình Prod** sau MFA mạnh, device compliant và quyền JIT được phê duyệt.
- Bị **DENY khi truy xuất database secrets**, dù vừa qua MFA, vì không có entitlement.

Vì vậy **mức tin cậy phụ thuộc vào action và tài nguyên**, không nên gán “Alice trust=90 nên được vào mọi hệ thống”. Một tín hiệu rủi ro thấp **không được tự tạo quyền** không có trong IAM/app RBAC.

## 3. Từ kiểm tra tại login tới xác minh liên tục

Trong mô hình đánh giá chỉ lúc đăng nhập, hệ thống xác thực khi mở phiên, phát cookie hoặc access token rồi dựa vào thời gian hết hạn. Trong ZTNA, quyền có thể được **thẩm định lại** khi nhận tín hiệu quan trọng hoặc đến mốc cần kiểm tra.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User / Device
    participant P as ZTNA PEP
    participant D as Policy Decision Point
    participant S as IdP / MDM / EDR / Risk Signals
    participant A as Protected Application
    U->>P: Request app/resource
    P->>D: Request decision + identity/device/resource context
    D->>S: Fetch/validate signals or cached assertions
    S-->>D: Identity, posture, risk, entitlement, freshness
    D-->>P: ALLOW with scope, TTL and obligations
    P->>A: Forward authorized connection/request
    S-->>D: New event: device quarantined / role revoked
    D-->>P: New decision: RESTRICT or REVOKE
    P-->>U: Stop new access / terminate affected session if supported
~~~

**Sơ đồ logic:** Không phải mọi ZTNA sản phẩm đều có kênh push quyết định tới PEP. Một số cần **PEP polling/introspection**, ngắn TTL hoặc **kiểm tra lại ở request tiếp theo**. Khi hệ thống nhận event, việc revoke có hiệu lực **sau độ trễ thực tế** của collector, policy engine, caches và enforcement. Phải đo độ trễ này.

### 3.1. Các mức tần suất

| Kiểu đánh giá | Trigger | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **At session establishment** | Đăng nhập/khởi tạo tunnel/connection | Bắt đầu theo điều kiện đúng | Không thấy rủi ro xuất hiện sau đó |
| **Per request/operation** | Mỗi HTTP request, RPC hoặc thao tác quan trọng | Kiểm tra entitlement, context và operation | Tăng latency/tải PDP; app/PEP phải thấy L7 |
| **Event-driven** | Account disabled, posture fail, token abuse, risk alert | Phản ứng nhanh với thay đổi | Event delivery/correlation có thể lỗi hoặc chậm |
| **Periodic reevaluation** | Timer, policy TTL, heartbeat | Giới hạn cửa sổ stale khi mất event | Có khoảng trống giữa hai lần kiểm tra |
| **Adaptive/step-up** | Hành động nhạy cảm hoặc risk tăng | Chỉ tăng friction khi cần | Có thể bị prompt fatigue, gây gián đoạn |
| **Reevaluation at refresh** | Token/cookie/certificate renewal | Dễ gắn với lifecycle credential | Phiên cũ có thể dùng tới expiry nếu không có push/revoke |

**Đánh giá lại** và **cưỡng chế lại** là hai bước khác nhau. Một PDP có thể tính ra DENY lúc 09:10 nhưng nếu PEP không nhận hoặc không cắt kết nối, quyền thực tế có thể còn đến 09:20.

## 4. Thuật ngữ nền tảng để tránh quyết định sai

| Khái niệm | Định nghĩa trong bài | Không nên đánh đồng |
| --- | --- | --- |
| **Subject / principal** | Người dùng, workload hoặc service identity đang xin quyền | Địa chỉ IP/NAT của kết nối |
| **Resource** | Ứng dụng, API, dữ liệu, route hoặc operation được bảo vệ | Toàn bộ subnet/VPN mặc định |
| **Entitlement** | Quyền có thể được cấp theo IAM/RBAC/ABAC/role | Điểm rủi ro hoặc device health |
| **Authentication assurance** | Mức độ tin cậy về chứng minh identity ở một thời điểm | Cứ MFA là có quyền administrator |
| **Device posture** | Trạng thái bảo mật từ MDM/EDR/attestation và timestamp | Sở hữu thiết bị hoặc nhận dạng MAC |
| **Session** | Quan hệ đăng nhập/ủy quyền và các credentials liên quan | Một TCP connection duy nhất |
| **Policy Decision Point (PDP)** | Thành phần đánh giá và quyết định policy | Luôn nằm trên data path của mọi packet |
| **Policy Enforcement Point (PEP)** | Thành phần chấp hành quyết định, có thể cấp/chặn/ngắt | Tự biết mọi nguy cơ nếu không có tín hiệu |
| **Risk engine** | Tổng hợp signal để hỗ trợ quyết định | Nguồn duy nhất tạo entitlement |
| **Continuous verification** | Đánh giá lại khi context thay đổi/đến mốc policy | Bắt buộc reauthenticate mọi giây |
| **Revocation** | Làm quyền/credential/session không còn được chấp nhận ở PEP/verifier | Chỉ xóa cookie ở trình duyệt |
| **Quarantine** | Đưa thiết bị/identity vào phạm vi mạng/quyền hạn chế | Luôn cắt toàn bộ kết nối cần để khắc phục |
| **Step-up** | Yêu cầu assurance mạnh hơn hoặc xác nhận mới | Tự tăng quyền của user |

### 4.1. Subject, environment và session phải có định danh rõ

Ví dụ:

~~~text
subject: alice@example.org (identity đã được IdP xác thực)
device_id: managed-device-042
device_posture: compliant (event_time + attestation provenance)
app: prod-admin.example.org
requested_action: update_network_policy
session_id: ztna-session-example-1001
auth_method: phishing-resistant MFA
last_strong_auth: 2026-11-28T08:00:00Z
policy_revision: ztna-prod-v17
decision: STEP_UP
~~~

**Đây là dữ liệu minh họa, không phải log từ một sản phẩm cụ thể.** Email, device identifiers và IP nguồn có thể là dữ liệu cá nhân; lưu trữ/truy cập theo chính sách bảo mật và riêng tư.

## 5. Kiến trúc: PEP, PDP, policy administration và các nguồn tín hiệu

Một kiến trúc tham chiếu theo tinh thần **Zero Trust Architecture** có các chức năng: **điểm quyết định policy, thành phần quản trị/cấu hình policy và điểm thực thi**. NIST SP 800-207 thường thảo luận **Policy Engine, Policy Administrator và Policy Enforcement Point**; sản phẩm ZTNA thực tế có thể gộp những vai trò này vào một gateway/agent/controller.

~~~mermaid
flowchart TB
    USER["User + endpoint / workload"] --> PEP["ZTNA connector / gateway / agent PEP"]
    PEP -->|"Authorized traffic"| APP["Protected app / API"]
    PEP -. "Access request + context" .-> PDP["Policy Engine / PDP"]
    PDP -. "Decision + obligations + TTL" .-> PA["Policy Administration / distribution"]
    PA -. "Enforcement update" .-> PEP
    IDP["IdP: MFA, account/session status"] --> PDP
    MDM["MDM/EDR: managed, posture, detections"] --> PDP
    IAM["Entitlement / Resource sensitivity / JIT role"] --> PDP
    SIEM["SIEM/UEBA and security alerts"] --> PDP
    APP -. "App/resource audit + business auth" .-> SIEM
~~~

**Sơ đồ mô tả luồng chức năng, không phải giao thức duy nhất.** Một PEP có thể quyết định từ policy cache, gọi PDP từ xa hoặc nhận sự kiện; Policy Administrator có thể phát session token, cấu hình tunnel, service identity hoặc route. Điều quan trọng là biết **ai được quyền cấp quyết định, ai thực thi tại traffic path và khi nào quyền thay đổi thực sự có hiệu lực**.

### 5.1. Các PEP có khả năng khác nhau

| PEP | Có thể thực thi | Không thể tự suy ra |
| --- | --- | --- |
| **ZTNA reverse proxy/L7 gateway** | HTTP host/path, auth cookie/token, per-request checks, block requests | Nội dung encrypted app-to-app TLS passthrough, quyền object nếu không tích hợp app |
| **ZTNA TCP broker** | Access tới application host:port, kết nối, tunnel expiry | Method HTTP hoặc user ownership của object |
| **Endpoint agent** | Device identity/posture, route/tunnel control, traffic steering | User được phép sửa dữ liệu nào trong API |
| **Cloud/network firewall** | Source/dest IP, ports, zones, một số identity integrations | Session/user entitlement chi tiết nếu không tích hợp |
| **Service mesh proxy** | Workload mTLS, L4/L7 rules nếu nhìn protocol | Authentication của end user và business object access mặc định |
| **Application authorization** | User, tenant, action, resource, transaction semantics | Tất cả bypass ở network ingress nếu app không bao phủ |

**Một policy chỉ có hiệu lực đối với traffic thực sự đi qua điểm thực thi.** Nếu ứng dụng còn lộ qua public IP/NodePort/alternate hostname, việc đặt chính sách mạnh tại một ZTNA gateway không bảo vệ đường bypass. Cần **firewall, private ingress, DNS/routing design và backend identity validation**.

### 5.2. Continuous verification cần cả control plane và data plane

PDP nhận device compromised alert nhưng **proxy chưa cập nhật** là một khoảng trống. Agent ngắt tunnel nhưng browser vẫn có **cloud access token riêng** là một khoảng trống khác. Do đó mỗi use case phải gắn:

1. **Signal xuất phát ở đâu** và độ mới có thể xác minh?
2. **Policy nào chịu ảnh hưởng**, chỉ app/resource nào?
3. **PEP/verifier nào phải cập nhật**?
4. **New requests, existing connections, cached tokens** sẽ bị xử lý như thế nào?
5. **Có bằng chứng** việc chặn đã có hiệu lực trong SLA không?

## 6. Các loại tín hiệu để đánh giá lại mức tin cậy

Continuous verification dựa trên nhiều **tín hiệu có độ tin cậy, độ mới và giới hạn riêng**. Nếu một hệ thống chỉ nhận IP hoặc user-agent rồi coi là bằng chứng thiết bị an toàn, nó có thể đưa ra quyết định sai dù policy được đặt tên là “zero trust”.

| Nhóm tín hiệu | Ví dụ | Điểm phải kiểm chứng | Ngộ nhận phổ biến |
| --- | --- | --- | --- |
| **User identity** | Account enabled, risk, authentication method, recent MFA | Issuer, signature/attestation, event time, session binding | Login thành công nghĩa là mọi hành động được phép |
| **Device identity** | Device enrollment, certificate, hardware-backed key | Binding với endpoint thật, thời gian, lifecycle | Chỉ có hostname/MAC là thiết bị được quản lý |
| **Device posture** | EDR healthy, disk encryption, screen lock, OS patch, MDM compliance | Độ mới, integrity, sensor gaps và chính sách phù hợp | Một check “compliant” vĩnh viễn |
| **Session context** | Session age, refresh failures, token replay, risky sign-in | Session ID và event provenance, tránh false correlation | HTTP cookie còn hạn là rủi ro không đổi |
| **Network context** | ASN, geo, IP reputation, VPN/Tor/egress proxy, private/public path | NAT/proxy/roaming, địa điểm không đồng nhất | IP nội bộ hoặc quốc gia quen thuộc là trusted |
| **Behavioral signals** | Impossible travel, atypical bulk export, new device pattern | Baseline, permissions, app semantics, false positives | Tất cả anomalies là compromise |
| **Workload signals** | mTLS identity, cluster, ServiceAccount, image posture, runtime alert | Issuer/trust domain, Pod UID, RBAC/IAM và runtime provenance | Pod cùng namespace nên đáng tin như nhau |
| **Resource context** | Data sensitivity, admin API, time-limited entitlement | Application resource classification, owner, requested action | Quyền đọc CRM đồng nghĩa quyền xuất dữ liệu |
| **Threat intelligence** | Known malicious indicators, active compromise alert | Nguồn, tuổi dữ liệu, confidence, shared IPs | Một IP trên blocklist chứng minh user độc hại |
| **Operational status** | PDP/MDM/EDR unreachable, event queue lag | Freshness SLO, last-known data, failure mode | Thiếu tín hiệu nghĩa là mọi thứ bình thường |

### 6.1. Phân biệt sự kiện và trạng thái

**Sự kiện:** MDM gửi “device lost” lúc 10:05; IdP gửi “account disabled” lúc 10:07. **Trạng thái:** PEP xem “account enabled = false” lúc 10:08 khi user cố gọi API. Event có thể **bị trễ, lặp hoặc đến sai thứ tự**. Một trạng thái tổng hợp cần **event ID, nguồn, observed/effective timestamp, version/sequence và thời gian hết hiệu lực** nếu có.

~~~json
{
  "event_id": "example-evt-100",
  "source": "endpoint-security",
  "event_time": "2026-11-28T03:05:00Z",
  "received_time": "2026-11-28T03:05:20Z",
  "subject_id": "device-042",
  "type": "device_posture_changed",
  "posture": "noncompliant",
  "assurance": "verified_sensor",
  "signal_schema": "example-v1"
}
~~~

**Không dùng message body tự khai như sự kiện có thẩm quyền.** Kênh IdP/MDM/EDR→PDP cần authentication, authorization, integrity protection, replay protection và kiểm soát nguồn tin. Với webhooks, kiểm tra chữ ký/timestamp/sequence theo đặc tả vendor; không mặc định một HTTP POST từ một IP được allowlist là trusted.

### 6.2. Missing, stale và negative là ba trạng thái khác nhau

| Kết quả posture | Ý nghĩa | Policy khả thi cho tài nguyên nhạy cảm |
| --- | --- | --- |
| **Compliant, fresh** | Có dữ liệu đủ mới chứng minh điều kiện | ALLOW nếu các điều kiện khác đạt |
| **Noncompliant, fresh** | Có bằng chứng vi phạm điều kiện | RESTRICT/QUARANTINE/DENY tùy mức |
| **Unknown** | Chưa có dữ liệu hoặc không thể kết luận | STEP_UP/RESTRICT/DENY theo data sensitivity |
| **Stale** | Dữ liệu cũ hơn freshness TTL | Recheck; giới hạn truy cập cho tới khi có kết quả |
| **Conflicting** | Nguồn dữ liệu bất nhất | Áp ưu tiên rõ, điều tra signal integrity |
| **Sensor unavailable** | Hệ thống endpoint/MDM/EDR không trả lời | Failure policy phụ thuộc tài nguyên và rủi ro |

**Không biến unknown thành compliant** để giảm 403, cũng không tự biến một check lỗi thành “device compromised” khi chỉ biết sensor offline. Mỗi tình huống cần **policy riêng, telemetry và user remediation path**.

## 7. Xác minh trạng thái thiết bị: quản lý khác sở hữu

Một thiết bị được đăng ký trong MDM chưa chắc luôn **được vá, có EDR hoạt động, ổ đĩa mã hóa hoặc không bị malware**. Device posture là **bằng chứng có thời hạn**, được điều chỉnh bởi chính sách và khả năng quan sát của hệ điều hành.

### 7.1. Các mức posture có thể dùng

| Kiểm soát | Dữ liệu cần | Giới hạn |
| --- | --- | --- |
| Enrollment/management | Device ID, tenant, quản lý còn hiệu lực | Không chứng minh runtime không bị chiếm |
| OS/build health | Version/patch state, allowlist được cập nhật | Update rollout có thể có ngoại lệ hợp lệ |
| Endpoint protection | EDR running, detection severity, isolation/quarantine | EDR offline có thể do lỗi sensor/network |
| Disk encryption | Mã hóa thiết bị và key management | Không ngăn attacker thao tác trong session đã mở |
| Hardware identity | TPM/Secure Enclave-backed certificate khi hỗ trợ | Attestation đúng vẫn không bảo đảm app không bị RCE |
| Firewall/host posture | Local firewall, risky configuration | Không thay cloud firewall/segment policies |
| Session/device binding | Token ràng buộc thiết bị hoặc sender proof khi hỗ trợ | Không phải mọi OAuth token là device-bound |

### 7.2. BYOD và khách hàng bên ngoài

Không nên yêu cầu một nhà thầu trên thiết bị cá nhân **cài agent giám sát toàn bộ** nếu yêu cầu kinh doanh chỉ cần đọc tài liệu ít nhạy cảm. Có thể chọn **browser isolation, web-only access, download restriction, MFA step-up hoặc thiết bị VDI**, với chính sách bảo vệ riêng tư minh bạch.

**Device posture là kiểm soát, không phải giấy phép thu thập vô hạn.** Chỉ thu tín hiệu cần thiết, đặt retention và access controls, không dùng vị trí chính xác, lịch sử duyệt web hoặc nội dung cá nhân ngoài mục đích đã xác định.

### 7.3. Khi posture chuyển noncompliant

Một phản ứng hợp lý phụ thuộc mức độ:

1. **Minor patch overdue**: cảnh báo và hạn chế action nhạy cảm, cho phép self-remediation.
2. **EDR mất heartbeat**: đánh dấu unknown/stale, yêu cầu refresh hoặc hạn chế nhạy cảm.
3. **Verified malware detection**: quarantine, revoke quyền nhạy cảm, phối hợp SOC/IR.
4. **Device lost/stolen**: vô hiệu hóa device trust/session và revoke credentials liên quan.
5. **Device compliant again**: kiểm tra attestation mới, account status và entitlement; **không tự restore admin grant** nếu grant đã bị thu hồi.

**Không có một ánh xạ một-một bắt buộc** từ posture tới DENY. Data classification, contractual availability, offline support và false-positive cost phải được định nghĩa từ trước.

## 8. Identity assurance, MFA step-up và quyền truy cập tạm thời

ZTNA thường sử dụng **single sign-on (SSO)** và **MFA**, nhưng mức assurance của một phiên có thể thay đổi theo **tuổi xác thực**, phương thức MFA, rủi ro đăng nhập và thay đổi account.

### 8.1. Khi nào cần step-up?

- Truy cập trang bình thường của CRM sau một thời gian không hoạt động.
- Thực hiện **bulk export** dữ liệu khách hàng hoặc tải bí mật.
- Thay đổi **firewall, security group, IAM role hoặc ZTNA policy**.
- Bắt đầu **Privileged Access Management / Just-in-Time (JIT)** session.
- Đăng nhập từ thiết bị mới, risk signal bất thường hoặc recovery flow.

**Step-up** chỉ giúp chứng minh lại danh tính/độ bảo đảm, không cấp thêm entitlement trái policy. Người dùng không có quyền xóa Prod database sẽ vẫn nhận **DENY sau MFA**.

### 8.2. Chọn phương thức xác thực mạnh

Với hành động nhạy cảm, ưu tiên **phishing-resistant authentication** khi khả dụng, ví dụ **FIDO2/WebAuthn/passkey đúng chính sách**. SMS OTP hoặc push prompt có thể có rủi ro **SIM swap, social engineering hoặc MFA fatigue**; một challenge được chấp nhận không tự loại bỏ account compromise.

### 8.3. Tránh MFA prompt fatigue

Nếu risk engine gửi sự kiện lặp mỗi vài giây, liên tục yêu cầu MFA có thể làm người dùng **chấp nhận tùy tiện** hoặc khiến hệ thống không sử dụng được. Nên có **rate limits, risk smoothing/hysteresis, device-bound assurance, freshness window và escalation theo loại hành động**; high-confidence compromise cần **revoke** thay vì chỉ gửi thêm prompt.

### 8.4. JIT/JEA khác continuous trust

**Just-in-Time (JIT)** giới hạn *khi nào* quyền nâng cao được cấp; **Just Enough Administration (JEA)** giới hạn *những thao tác* được phép. Continuous verification kiểm tra điều kiện trong suốt khoảng cấp quyền, nhưng **không biến TTL=1 giờ thành quyền làm tất cả trong 1 giờ**. Resource server/PEP vẫn cần kiểm tra action và object permissions.

## 9. Risk-based decisions: không lấy một điểm số làm chân lý

Nhiều tổ chức sử dụng **risk scoring** để hỗ trợ policy. Ví dụ minh họa một quy tắc chấm điểm:

~~~text
Baseline risk = 0
Verified device malware = +90
Device posture stale = +30
Unusual new country = +20
Fresh phishing-resistant MFA = -20
Critical admin operation = raises required assurance,
                           NOT a grant of entitlement
~~~

Các số này **chỉ là ví dụ dạy học**, không đại diện cho tiêu chuẩn, ngưỡng phát hiện hay điểm số của vendor. Thực tế phải đánh giá **chất lượng tín hiệu, nguồn, false positives, thay đổi ngữ cảnh và độ nhạy tài nguyên**. Không thể kết luận “score < 30 là chắc chắn an toàn”.

### 9.1. Quyền tối thiểu và risk là hai điều kiện độc lập

Một policy nên kiểm tra:

\[
\text{ALLOW} = \text{Entitled} \land \text{Authenticated} \land \text{PolicyConditionsSatisfied}
\]

Nếu **Entitled=false**, điểm rủi ro thấp hoặc MFA thành công **không thể đảo thành ALLOW**. Nếu Entitled=true nhưng posture bị đánh dấu compromised, quyền đó có thể bị **tạm giới hạn**.

### 9.2. Tính bất định và các nguồn false positives

| Tín hiệu | False positive có thể gặp | Cách xử lý |
| --- | --- | --- |
| Impossible travel | VPN/CGNAT, chuyển region CDN, corporate egress | Kiểm chứng source/session và known proxies |
| New device | Device replacement, browser profile mới | Enrollment/identity proof, no automatic privilege grant |
| EDR offline | Sensor crash, network outage | Policy unknown + remediation, không tự gọi malware |
| Bulk download | Monthly payroll/backup, data export có ticket | Business ownership, action-level risk, approval |
| Repeated denied requests | SDK retry bug, expired credential, automation sai | Correlate identity, error semantics và client release |
| Risk alert từ vendor | Delayed detection hoặc stale indicator | Event time/freshness, confidence, triage |

**Không dùng địa chỉ IP hoặc quốc gia làm chứng cứ xác thực identity.** IP reputation có thể hỗ trợ risk, nhưng một IP cloud/VPN/shared có nhiều người dùng và có thể thay đổi chủ theo thời gian.

### 9.3. Hạn chế tính toán và auditability

Nếu dùng mô hình ML/UEBA, cần có **explainability, versioned policy/model, test fairness/false positives, manual review cho tác động lớn**, rollback và data retention phù hợp. Không nên tạo một black-box điểm rủi ro rồi chặn mọi nhân viên mà không có **remediation, appeal và owner**.

## 10. Thiết kế trạng thái tin cậy theo tài nguyên

Một **state machine** giúp đội bảo mật diễn đạt chính sách rõ, không trộn những hành động khác nhau thành một cờ “trusted/untrusted”.

~~~mermaid
stateDiagram-v2
    [*] --> EVALUATING
    EVALUATING --> ALLOW: Identity + entitlement + fresh posture đủ
    EVALUATING --> STEP_UP: Assurance thiếu nhưng có thể bổ sung
    EVALUATING --> RESTRICT: Posture unknown / stale, chỉ low-risk
    EVALUATING --> DENY: Không có quyền hoặc risk không chấp nhận
    ALLOW --> STEP_UP: Hành động nhạy cảm / auth freshness thấp
    ALLOW --> RESTRICT: Posture yếu hoặc signal stale
    ALLOW --> QUARANTINE: Verified endpoint compromise
    ALLOW --> REVOKED: Account disabled / session theft
    STEP_UP --> ALLOW: Strong proof + policy vẫn đạt
    STEP_UP --> DENY: Proof failure / không có quyền
    RESTRICT --> EVALUATING: Signal mới + verify
    QUARANTINE --> EVALUATING: Remediated + attested + approved
    REVOKED --> EVALUATING: New auth/session & explicit regrant
    DENY --> EVALUATING: New request/context; entitlement vẫn bắt buộc
~~~

**Đây là mô hình học thuật, không phải một giao thức ZTNA tiêu chuẩn.** Một sản phẩm có thể dùng **grant, challenge, session suspension, policy deny** hoặc các từ khác. Quan trọng là biết **quyết định nào chặn new request, quyết định nào chặn active session và điều kiện nào cho phép khôi phục**.

### 10.1. Hành động tương ứng

| Decision | Ý nghĩa ở mức truy cập | Hành động của PEP/app |
| --- | --- | --- |
| **ALLOW** | Điều kiện được đáp ứng cho action/resource hiện tại | Cấp phiên/quyền có TTL và scope, tiếp tục giám sát |
| **STEP_UP** | Thiếu assurance để làm action nhạy cảm | Thách thức xác thực mới, không thực hiện action trước khi hoàn tất |
| **RESTRICT** | Chỉ cho phép low-risk hoặc read-only subset | Chặn bulk export/admin writes, có thể cho phép remediation portal |
| **QUARANTINE** | Device/workload được coi là rủi ro cao | Ngắt đường tới resources nhạy cảm, chỉ cho phép remediation có giới hạn |
| **REVOKE** | Session/credential grant không còn được chấp nhận | Invalidate session/deny token/cắt active connection nếu hỗ trợ |
| **DENY** | Không đáp ứng điều kiện hoặc không có entitlement | Từ chối request, không route tới app nhạy cảm |

### 10.2. Quy tắc ưu tiên

**Account disabled, explicit deny, compromised identity và thiếu entitlement** thường phải ưu tiên hơn **risk score thấp hoặc successful MFA cũ**. Không để một sự kiện “device compliant” đến muộn **ghi đè** sự kiện “device quarantined” mới hơn; đánh giá theo **time/sequence/version** và chính sách xung đột.

### 10.3. Chống flapping bằng hysteresis

Nếu posture lúc compliant lúc unknown do mất mạng, policy thay đổi **ALLOW→DENY→ALLOW** liên tục có thể khiến users đăng nhập lại liên tục hoặc đóng/mở tunnel. Cần:

- **Debounce/window** cho tín hiệu yếu/không chắc chắn; không trì hoãn high-confidence compromise.
- **Grace period có giới hạn** cho dịch vụ ít nhạy cảm khi sensor gián đoạn.
- **Ngưỡng vào/ra khác nhau** (hysteresis) nếu dùng risk score và policy cho phép.
- **Minimum action TTL** đối với quarantine và yêu cầu remediation rõ trước khi khôi phục.
- **State transition audit** để biết ai/điều gì làm thay đổi quyền, tránh vòng lặp tự động.

### 10.4. Risk giảm không tự tăng entitlement

Khi thiết bị trở lại compliant và user hoàn thành MFA, hệ thống chỉ có thể **đánh giá lại những quyền đã được cấp và còn hiệu lực**, không tự tái cấp JIT role cũ sau khi owner đã revoke. Đặc biệt với Production admin, cần **fresh approval** nếu entitlement đã hết hạn.

## 11. Signal pipeline và tốc độ phản ứng thực tế

Khi thiết bị bị nhiễm mã độc, có ít nhất **năm khoảng trễ** giữa sự kiện và việc phiên bị cắt:

~~~mermaid
flowchart LR
    E["Sự kiện tại thiết bị"] --> S["Sensor/EDR phát hiện"]
    S --> B["Bus/API nhận tín hiệu"]
    B --> D["PDP đánh giá lại"]
    D --> P["PEP nhận quyết định"]
    P --> A["Connection/request bị chặn"]
~~~

Một cách tính độ trễ quan sát:

\[
T_{\mathrm{effective}} =
T_{\mathrm{detect}} +
T_{\mathrm{deliver}} +
T_{\mathrm{decide}} +
T_{\mathrm{propagate}} +
T_{\mathrm{enforce}}
\]

Đây là **mô hình cộng thời gian lý tưởng hóa**, không tự đại diện cho hệ phân tán có xử lý song song, timeouts, cache hoặc retries. Khi đo thực tế cần **UTC event timestamp, trustworthy monotonic/sequence data khi có, clock synchronization và điểm xác nhận enforcement**.

### 11.1. Freshness TTL là giới hạn tuổi dữ liệu, không phải session lifetime

**Posture TTL = 5 phút** nghĩa là một quyết định không nên dựa trên dữ liệu posture cũ hơn 5 phút, nếu không có quy tắc ngoại lệ. Nó **không đồng nghĩa session phải hết sau 5 phút**, cũng không có nghĩa EDR chắc phát hiện compromise trong 5 phút.

Các TTL khác nhau:

| TTL/timeout | Đối tượng | Vấn đề khi cấu hình sai |
| --- | --- | --- |
| Posture freshness | MDM/EDR assertion | Chấp nhận thông tin quá cũ hoặc false deny do delay |
| PDP decision cache | Kết quả ALLOW/RESTRICT/DENY theo context | ALLOW kéo dài sau khi revoke; deny cache gây ngừng sử dụng |
| Access token expiration | Bearer token, JWT, opaque token | Quá dài tăng lạm dụng; quá ngắn thiếu refresh gây 401 |
| Refresh token/session | Identity session và khả năng cấp access token mới | Refresh path bị lạm dụng; logout chưa chặn token cũ |
| TCP/TLS idle timeout | Kết nối transport | Long-lived session tồn tại sau app permission change |
| JIT admin grant TTL | Quyền đặc biệt có hạn | Hết hạn nhưng proxy/backend không thực thi lại |
| Event deduplication window | Chống phát sự kiện trùng | Có thể bỏ nhầm event mới nếu key không đúng |

### 11.2. Event integrity, replay và out-of-order

Một tín hiệu “đã an toàn” từ 09:00 có thể đến sau tín hiệu “phát hiện malware” lúc 09:02. Nếu policy engine xử lý theo **thứ tự nhận** mà không xét event time/sequence, nó có thể cho phép truy cập trở lại.

Phòng vệ:

1. Kênh **authenticated + integrity protected** giữa nguồn và PDP.
2. **Event ID/idempotency key, source sequence hoặc version** nếu nguồn hỗ trợ.
3. Xác nhận **event_time vs received_time**, ngưỡng độ trễ, clock-skew tolerance.
4. Cơ chế **merge/precedence** khi hai nguồn không đồng ý; high-confidence incident flag không bị xóa bởi low-confidence heartbeat.
5. **Audit mọi transition** và cảnh báo những update bị drop hoặc không thể map identity.
6. Kiểm tra **chất lượng dữ liệu** khi vendor API outage, không tin “no alerts” là device healthy.

### 11.3. Xác minh có hiệu lực

Nếu IdP disable Alice lúc 10:00, có thể query:

~~~text
IdP event:           account_disabled 10:00:00Z
PDP decision:        REVOKE 10:00:01Z
PEP policy ACK:      10:00:04Z
Active tunnel end:   10:00:06Z
Next API request:    DENY 10:00:07Z
Backend audit:       no authorized access after cutoff
~~~

**Các mốc là ví dụ**, không phải SLA chuẩn. **PEP ACK không tự chứng minh backend từ chối mọi token còn hợp lệ**; phải kiểm tra tại resource/app nếu token có thể được sử dụng qua đường khác.

## 12. Phiên HTTP, TCP, WebSocket và gRPC: thu hồi giữa kết nối khó đến đâu?

Khái niệm **session** của ZTNA có thể liên quan một **identity grant**, trong khi tầng mạng có **TCP/TLS connection**, HTTP có **cookie/token**, gRPC có **stream**, ứng dụng có **business session**. Chúng có những điểm cắt khác nhau.

| Loại giao tiếp | Điểm dễ đánh giá lại | Rủi ro khi cấp quyền thay đổi |
| --- | --- | --- |
| HTTP/1.1 request-response | Mỗi request tại reverse proxy/app | Keep-alive còn mở, cookie/token cache còn hợp lệ |
| HTTP/2 | Theo request/stream ở L7 PEP | Một TCP connection chứa nhiều requests/streams |
| gRPC unary | Trước mỗi RPC theo method/identity | Deadline, status, call retries và credential metadata |
| gRPC streaming | Lúc stream open, refresh/recheck nếu implementation hỗ trợ | Stream dài vẫn truyền dữ liệu sau khi role bị revoke |
| WebSocket | Lúc handshake và thông điệp nếu app hỗ trợ | Upgrade xong proxy không nhất thiết parse/auth mỗi message |
| Raw TCP | Lúc mở connection, periodic agent/PEP recheck | Không thể thu hồi operation-level nếu chỉ thấy L4 |
| SSH/RDP qua ZTNA | Khi connect và theo session policy | Quyền thao tác trong OS phụ thuộc host/AD/PAM riêng |
| VPN/IPsec tunnel | Lúc tạo tunnel và security policy update | Existing flows có thể còn trong tunnel nếu không ngắt/enforce |

### 12.1. Chặn new requests khác đóng active sessions

Khi role bị revoke:

- **PEP deny new connections:** không cho mở socket mới tới app.
- **PEP deny new HTTP requests:** có thể từ chối request tiếp theo trên connection vẫn mở.
- **PEP disconnect existing tunnel:** buộc TCP/TLS/transport đóng theo implementation.
- **Application revoke session:** ngừng chấp nhận cookie/token hoặc business operations.
- **Resource server policy revoke:** từ chối object action ngay cả khi kết nối vẫn tồn tại.

**Không phải PEP L4 nào cũng có khả năng chặn một gRPC method trong stream đang mở**. Nếu yêu cầu business là **“ngừng xuất dữ liệu trong 10 giây khi account bị disable”**, phải thiết kế **app-level subscription checks, streaming revocation hooks hoặc session termination** với test có đo.

### 12.2. Kết nối dài và reauthentication

Một RDP/SSH/DB session đã được thiết lập có thể tiếp tục chạy sau IdP logout nếu ứng dụng/host không gắn với chính sách thu hồi. Với những phiên nhạy cảm:

1. Giới hạn **max session age / idle timeout / JIT TTL**.
2. Gắn session với **user, device, resource và entitlement scope**.
3. Thiết lập **event-driven disconnect** khi device quarantine/account disabled.
4. Nếu cần, app kiểm tra lại **quyền từng thao tác nhạy cảm**, không chỉ tại TCP connect.
5. Kiểm tra **reconnect** sau disconnect; không tự cấp quyền lại từ stale cookie.

### 12.3. Bảo toàn dữ liệu khi thu hồi

Cắt một TCP session có thể làm **transaction chưa hoàn tất, file upload bị dở, lock chưa giải phóng hoặc client tự retry**. Một số incident yêu cầu ngắt ngay; với rủi ro thấp có thể **graceful drain trong thời hạn ngắn, cấm new writes** và ghi lại quyết định. Với **verified account compromise**, không giữ quyền ghi Prod chỉ để tránh một lỗi ứng dụng; chọn **security-first response** đã được phê duyệt.

## 13. Token, cookie, certificate và giới hạn của “logout”

Continuous verification thường gặp vấn đề: **IdP đã revoke session nhưng API vẫn nhận token cũ**. Nguyên nhân có thể là **JWT self-contained còn hạn, verifier cache, kết nối đã được xác thực sẵn hoặc backend không hỏi lại PDP**.

### 13.1. Access token và refresh token

- **Access token** thường chứng minh authorization tại resource server trong khoảng thời gian/điều kiện nhất định. Với **JWT tự chứa**, API có thể chỉ kiểm tra chữ ký, issuer/audience/expiry và scope tại chỗ.
- **Refresh token** giúp client xin access token mới. Thu hồi refresh token có thể **ngăn cấp mới** nhưng không mặc định làm access token đã cấp **vô hiệu ngay**.
- **Opaque access token** có thể được introspect tại authorization server, nhưng caches và network availability ảnh hưởng độ mới.
- **Session cookie** ở gateway/app có vòng đời riêng và có thể cho phép cấp token mới nếu không cùng bị vô hiệu hóa.

### 13.2. Những cơ chế hỗ trợ continuous revocation

| Cơ chế | Ý tưởng | Giới hạn |
| --- | --- | --- |
| Short-lived access token | Giảm cửa sổ chấp nhận sau revoke | Refresh/session vẫn cần kiểm soát |
| Token introspection | Resource/PEP hỏi server trạng thái token | Cache, latency, IdP outage, rate limits |
| Server-side session store | PEP/app kiểm tra grant đang active | Phải nhất quán giữa replicas/regions |
| Revocation list/version | Resource so jti/session/grant version | Kích thước list, propagation, retention |
| Policy event push | IdP/PDP thông báo PEP/resource server | Subscriber ACK, event loss/out-of-order, disconnect |
| CAE/claims challenge khi hỗ trợ | Resource/client phối hợp kiểm tra sự kiện và yêu cầu challenge/refresh | Phụ thuộc hệ sinh thái, không mặc định cho mọi ứng dụng |
| Certificate/identity revoke | Thay peer trust/identity, deny at authorization | Active TLS sessions và verifier cache có thể còn tồn tại |

**Continuous Access Evaluation (CAE)** là cơ chế được một số hệ sinh thái identity/resource ứng dụng hỗ trợ để phản ứng nhanh hơn với sự kiện như account disable hoặc session risk; **không phải mọi OAuth 2.0 token, JWT hoặc ZTNA gateway đều mặc định có CAE**. Cần kiểm tra **client, resource server, IdP và event support**.

### 13.3. Kiểm tra issuer/audience/subject và device/session binding

Một token hợp lệ về chữ ký vẫn có thể:

- **Audience sai:** token cho service A không nên được service B chấp nhận.
- **Tenant/subject sai:** token của một user không chứng minh người đó được gọi API của tenant khác.
- **Scope thiếu:** authentication không đủ quyền admin/export.
- **Replay từ thiết bị khác:** bearer token bị copy có thể dùng ở nơi khác nếu không có sender-constrained mechanism.
- **Stale grant:** token còn hạn nhưng role đã bị xóa, cần policy chọn cách kiểm tra lại.

Các cơ chế như **mTLS-bound tokens hoặc proof-of-possession/DPoP khi được triển khai đúng** có thể hạn chế sử dụng token bị copy khỏi holder, nhưng **không tự chống được process compromise** có khả năng sử dụng key/đặc quyền ngay trên thiết bị. Sender constraint và continuous policy là **các lớp phòng vệ bổ sung**, không thay cho authorization.

### 13.4. Không rotate key ký JWT bừa bãi

Khi một account cần revoke, **rotate global signing key** có thể làm ảnh hưởng **mọi token** và gây outage lớn. Ưu tiên **revoke đúng session/principal/grant, short TTL, verifier policy hoặc supported revocation mechanism**. Chỉ xử lý issuer signing key theo quy trình CA/IdP key compromise khi có bằng chứng liên quan.

## 14. Network context: IP, VPN, DNS, location và trust boundary

Một tổ chức chuyển từ VPN truyền thống sang ZTNA thường giảm **network-level implicit trust** và cấp truy cập theo app; tuy nhiên **VPN, ZTNA, firewalls và private network segmentation** có thể cùng tồn tại.

### 14.1. IP nội bộ không phải identity

IP 10.10.1.25 có thể thuộc Pod/VM/endpoint hôm nay, nhưng được dùng lại ngày mai. IP công khai có thể là NAT của hàng nghìn users. Vì vậy:

- **Không cấp quyền Production admin chỉ vì source thuộc CIDR văn phòng**.
- Không coi **VPN connected** đồng nghĩa device compliant hoặc user authorized.
- Dùng **cryptographic user/workload identity** và xác định network origin như một signal hỗ trợ.
- Join flow logs với **historical asset/device identity** theo thời điểm, không tra IP hiện tại rồi gán ngược.

### 14.2. DNS và đường bypass

ZTNA gateway có thể bảo vệ **admin.example.org**, nhưng backend vẫn có **public IP, alternate hostname, direct private address hoặc IPv6 listener**. Kẻ tấn công/ứng dụng có thể đi thẳng tới origin nếu network ACL cho phép. **Ẩn DNS không phải access control**; muốn ZTNA có hiệu lực phải **giới hạn origin chỉ nhận từ PEP/trusted network và xác thực request ở backend** theo thiết kế.

### 14.3. Location và “impossible travel”

Geo IP là **ước lượng vị trí của egress/network provider**, không phải vị trí vật lý chắc chắn của người dùng. Một user di chuyển giữa mạng mobile và VPN toàn cầu có thể sinh hai quốc gia trong vài phút. Dùng risk **kết hợp session correlation, device binding, known proxies và login pattern** thay vì cắt toàn bộ session trên một geo alert đơn lẻ.

### 14.4. ZTNA so với network VPN

| Thuộc tính | Network-level VPN điển hình | Application-specific ZTNA |
| --- | --- | --- |
| Đơn vị cấp quyền | Thường IP/subnet, routes, tunnels + ACL | Application/resource/identity/policy |
| Định danh | VPN authentication và có thể posture/role | User/device/workload plus per-resource context |
| Continuous check | Có thể bổ sung qua NAC/IdP/agent; không mặc định | Mục tiêu thiết kế, phụ thuộc giải pháp thực |
| Lateral movement | Rủi ro nếu VPN cấp broad network reachability | Giảm nếu PEP+origin access chặt |
| Protocol support | Nhiều protocol qua IP layer | Tùy sản phẩm, có thể web app/TCP client/broker |
| Long-lived sessions | Tunnel/connection có thể tồn tại lâu | Vẫn cần revocation/disconnect và app checks |
| Failure mode | VPN gateways/IKE/route failures | PDP/PEP/IdP/posture/event integration failures |

**Không nên khẳng định VPN luôn không an toàn hoặc ZTNA luôn vượt trội.** VPN có thể được thiết kế mạnh với per-app access, MFA, posture và microsegmentation; ZTNA cấu hình sai vẫn có thể cấp **wildcard application access** hoặc để origin bypass.

## 15. Service-to-service continuous verification

Không chỉ người dùng cuối: **workloads trong Kubernetes/cloud** cũng có thể thay đổi mức tin cậy. Một Pod đang có mTLS certificate nhưng bị phát hiện chạy image dễ bị khai thác hoặc được cấp IAM role quá rộng có thể cần **giảm quyền kết nối**.

### 15.1. Các tín hiệu cho workload

- Kubernetes **ServiceAccount / SPIFFE ID / trust domain** và trạng thái certificate.
- Image digest, signature/attestation theo supply-chain policy; không dùng image tag mutable làm bằng chứng mạnh.
- Runtime security alert, node/Pod quarantine, admission policy violation.
- Cloud IAM permissions, workload federation trust, resource policy changes.
- NetworkPolicy/CNI flow anomaly, service mesh **mTLS peer ID**, gRPC method authorization.
- App/API entitlement và dữ liệu/tenant mà workload truy cập.

### 15.2. Đường enforcement trong service mesh

~~~mermaid
flowchart LR
    O["Orders Pod / mTLS identity"] --> SP["Orders sidecar"]
    SP --> DP["Payments sidecar PEP"]
    DP --> A["Payments API"]
    R["Runtime/cluster security signals"] --> D["Workload PDP"]
    D -. "Authorize/restrict peer identity" .-> DP
    A -. "Business resource authZ" .-> A
~~~

Khi **workload identity bị revoke**, inbound mesh PEP có thể từ chối các new connections/requests theo năng lực. Nhưng **mTLS peer authentication** chỉ chứng minh danh tính của proxy/workload; để kiểm soát **orders được phép tạo payment nào**, app vẫn phải có **object/tenant-level authorization**.

### 15.3. Rotation và scope của mTLS identity

Thay workload certificate có thể làm **new TLS handshakes** sử dụng key mới nhưng **active connections** vẫn tồn tại. Nếu peer identity bị compromise, cần **server-side deny policy, session draining/termination và certificate lifecycle controls** phù hợp, không chỉ xóa Pod hoặc đợi cert hết hạn.

### 15.4. Policy change propagation

Mesh control plane phát policy mới chưa chứng minh mọi proxy đã nhận. Kiểm tra **effective proxy configuration, config ACK/NACK, peer authZ decisions và CNI flow logs** theo cluster/region; test **ALLOW đúng service và DENY non-authorized workload**. Một proxy stale không nên giữ đường critical admin lâu hơn giới hạn risk được phê duyệt.

## 16. Thiết kế chính sách có thứ tự ưu tiên, phạm vi và trạng thái

Các hệ thống ZTNA cần thể hiện **deny precedence, entitlement, device assurance, action sensitivity, freshness và obligations**. Ví dụ dưới đây là **policy-as-data giả lập** để đọc hiểu, **không phải manifest của vendor hoặc code có thể triển khai trực tiếp**.

~~~yaml
policy_id: ztna-prod-admin-example
version: 17
resource:
  app: prod-admin
  actions: [view, change_policy, export_config]
required_subject:
  authenticated: true
  entitlement: prod-admin-jit
  allowed_tenants: [company-prod]
hard_denies:
  - account_disabled
  - session_revoked
  - verified_identity_compromise
  - revoked_jit_grant
required_signals:
  device_management: managed
  device_posture_freshness_seconds: 300
  endpoint_security: healthy
conditional_rules:
  - action: view
    min_assurance: normal
    on_unknown_posture: restrict_to_remediation
  - action: change_policy
    min_assurance: fresh_phishing_resistant_mfa
    on_unknown_posture: deny
  - action: export_config
    min_assurance: fresh_phishing_resistant_mfa
    require_approved_purpose: true
    on_unknown_posture: deny
session_controls:
  authorization_cache_max_seconds: 60
  max_privileged_session_seconds: 900
  event_driven_revocation: required_when_supported
  active_connection_termination: require_validation
default_decision: DENY
~~~

### 16.1. Vì sao thứ tự quan trọng?

Một đánh giá đúng có thể đi qua:

1. **Xác minh nguồn yêu cầu**, user/device/session identifiers đã được chứng thực; nếu không, DENY/redirect auth có kiểm soát.
2. **Hard deny:** account disabled, token revoked, confirmed compromise, không có entitlement/JIT grant.
3. **Resource/action classification:** view hay write/export? Prod hay staging?
4. **Signal validity:** posture/IdP/risk event có đủ mới và đáng tin?
5. **Assurance:** step-up cho action nhạy cảm nếu đủ điều kiện.
6. **Result:** ALLOW với scope+TTL, RESTRICT, STEP_UP hoặc DENY.
7. **PEP obligations:** session disconnect, new request check, audit, safe user messaging.

Một service chỉ có quyền **READ** không được nhận **WRITE** chỉ vì số điểm rủi ro thấp. Một user đang được **quarantine** không được chuyển sang ALLOW chỉ vì challenge MFA thành công nếu malware chưa được xử lý.

### 16.2. Policy-as-code và testing

Mọi thay đổi policy quan trọng cần **version control, reviewer, test fixtures, preview impact, canary, rollback và audit**. Đối chiếu **intended policy** với **effective enforcement**: cấu hình ở PDP là một mặt, kết nối ở PEP/backend mới là sự thật. Phải thử cả **permitted actions** và **forbidden actions** trên những entry points, regions và IP families phù hợp.

### 16.3. Justification không nên là “điểm cao/thấp”

Audit record nên nêu **policy ID/revision, resource/action, decision, signal type/time/freshness, subject pseudonymous ID và PEP ID**, không cần lưu mật khẩu hay raw bearer token. Người vận hành phải có khả năng trả lời **vì sao Alice bị RESTRICT lúc 10:05** mà không công bố dữ liệu nhạy cảm hoặc mô hình nội bộ vượt nhu cầu.

## 17. Failure modes: IdP/EDR/PDP/PEP không sẵn sàng thì xử lý ra sao?

**Continuous verification phụ thuộc vào tín hiệu và đường thực thi.** Khi một nguồn bị lỗi, cách quyết định ảnh hưởng trực tiếp tới **availability, an toàn thông tin và quyền truy cập hợp lệ**. Không có câu trả lời “fail-open” hoặc “fail-closed” thống nhất cho mọi ứng dụng.

| Sự cố | Rủi ro | Chính sách cần xác định trước |
| --- | --- | --- |
| **IdP unavailable** | Không thể xác thực/refresh, session cũ vẫn còn | Existing sessions có được grace không, tài nguyên nào phải DENY |
| **MDM/EDR stale** | Không biết device posture mới nhất | Posture TTL, low-risk access, restricted remediation |
| **Risk event pipeline lag** | Quyết định không theo kịp compromise | Alert freshness, max stale window, fallback PEP |
| **PDP down** | Không có quyết định mới | Cache TTL, last-known policy, critical resources fail closed |
| **PEP disconnected from PDP** | Old grant có thể kéo dài | Max local decision TTL, disconnect/deny behavior |
| **Policy push rejected** | Một vùng giữ policy cũ | Config ACK/NACK, policy version health, drift alarms |
| **Certificate/issuer rotation issue** | Auth handshake hoặc token verification lỗi | Trust overlap, key distribution, safe rollback |
| **Identity mapping failure** | User/device/session không ghép được | Unknown/deny cho sensitive actions, ticket và remediation |
| **False positive malware alert** | Chặn nhầm nhân viên và gây gián đoạn | Triage, appeal, measured restore và audit |
| **Clock skew** | Token/not-before/freshness bị xử lý sai | NTP, UTC audit, bounded skew tolerance |
| **Cross-region replication lag** | Một PEP đã revoke, PEP khác vẫn allow | Global/session version, region propagation SLA, failover tests |

### 17.1. Đặt mức failure policy theo tài nguyên

Một cách thiết kế:

- **Public/low sensitivity app:** có thể tiếp tục hỗ trợ user ít nhạy cảm với session TTL ngắn khi sensor unavailable, có audit.
- **Internal HR/CRM:** cho phép **view-only** theo dữ liệu còn đủ mới, chặn export/write nếu device posture unknown.
- **Production admin, secrets, payment approvals:** khi thiếu signal bắt buộc hoặc PDP không thể quyết định, **DENY hoặc giới hạn đã phê duyệt**, không tự dùng last-known ALLOW vô hạn.
- **Remediation portal:** có thể cho phép thiết bị bị quarantine truy cập **tài nguyên vá lỗi/đổi mật khẩu/đăng ký lại MFA** rất hẹp.

Không biến các ví dụ này thành policy bắt buộc cho mọi tổ chức; cần căn cứ **data classification, yêu cầu pháp lý, business continuity, break-glass controls và khả năng kỹ thuật của PEP**.

### 17.2. Break-glass là ngoại lệ có kiểm toán, không phải cửa hậu vĩnh viễn

Tài khoản hoặc workflow **break-glass** phục vụ khôi phục khi hệ thống identity/ZTNA gặp sự cố cần **strong authentication, tài khoản/thiết bị được bảo vệ, dual approval khi phù hợp, time-boxing, logging và post-use review**. Không cho toàn bộ staff quyền VPN broad hoặc bỏ MFA vì một vendor API bị gián đoạn.

### 17.3. Fail-closed vẫn cần UX/remediation

Một user bị DENY vì posture unknown cần biết **hành động khả thi tiếp theo**: cập nhật EDR, kết nối VPN/MDM theo quy trình, xác minh thiết bị, liên hệ hỗ trợ. Error message không nên lộ chi tiết **risk engine logic, credential claims hoặc mạng nội bộ** nhưng đủ để giảm ticket và tránh vòng lặp đăng nhập.

## 18. Threat modeling continuous verification

Một thiết kế zero trust có thể bị tấn công không chỉ ở app mà còn ở **nguồn sự kiện, đường truyền tín hiệu, bộ máy quyết định và enforcement**.

### 18.1. Ma trận rủi ro

| Threat | Điểm yếu | Tác động | Biện pháp |
| --- | --- | --- | --- |
| **Stolen bearer token** | Token không ràng buộc sender/device và TTL dài | Session hijack, data access | Sender-constrained token khi phù hợp, short TTL, anomaly detection, revoke |
| **Device posture spoofing** | Tin header/client claim do endpoint tự gửi | Cho unmanaged/compromised device vào app | Signed/attested MDM/EDR signals, trustworthy device binding |
| **Stale ALLOW after disable** | PDP/PEP cache quá lâu, thiếu event propagation | Access còn tồn tại sau thu hồi | Bound cache TTL, session version, revocation test |
| **Event replay/out-of-order** | Không validate event ID/sequence/time | Một compliant event cũ ghi đè quarantine | Integrity, anti-replay, event precedence |
| **PDP privilege/config tampering** | Admin rộng, policy không review | Global allow hoặc bypass nhóm nhạy cảm | RBAC/JIT/MFA, code review, audit, tamper alert |
| **PEP/origin bypass** | Backend public direct IP/alternate path | Truy cập không qua ZTNA policy | Network segmentation, origin allowlist, backend auth |
| **Policy downgrade on outage** | Tự chuyển fail-open khi risk engine lỗi | Toàn mạng critical exposed | Risk-based failure matrix, approve exceptions |
| **Signal-source compromise** | Event connector bị lộ key hoặc quyền gửi event | Giả quarantine/allow, denial of access | Authenticated connectors, least-privilege event scopes, monitoring |
| **Mis-scoped JIT grant** | Rule cấp admin cho wildcard apps | Lateral movement | Grant theo resource/action, expiry và review |
| **Geo-based false block** | Tin IP location là nơi ở thật | Availability impact, user lockout | Context correlation và appeal/remediation |
| **Race condition** | Role bị revoke trong lúc export đang chạy | Data tiếp tục xuất | Resource-level check, cancellation/stream termination |
| **Cached JWT still valid** | API chỉ kiểm tra signature+exp | Revoked account vẫn access | Introspection/session version/push revocation, short TTL |
| **Session fixation/replay** | Session ID không rotate/bind theo auth | Chiếm quyền phiên | Secure session lifecycle, rotation, sender binding |
| **Telemetry leakage** | Log raw token, device personal data, geolocation | Rò secrets và vi phạm privacy | Redaction, minimization, retention/RBAC |
| **Overzealous automatic revoke** | Rule confidence thấp gây hàng loạt false positives | DoS tự gây cho doanh nghiệp | Rate limits, review, staged containment |
| **Compromised workload identity** | mTLS cert/STS credential còn dùng được | East-west access ngoài ý định | Server-side deny, mesh authZ, credential rotation và app auth |

### 18.2. DFD và STRIDE

~~~mermaid
flowchart LR
    DEV["User device / Agent"] --> GW["ZTNA PEP / Broker"]
    GW --> APP["Protected app/resource"]
    EDR["MDM/EDR sensor"] --> BUS["Signal channel"]
    IDP["Identity provider"] --> BUS
    BUS --> PDP["PDP / Policy Engine"]
    PDP --> GW
    AUD["Audit/SIEM"] -. "Correlated evidence" .-> PDP
    GW -. "Access decisions" .-> AUD
    APP -. "Resource use" .-> AUD
~~~

Các câu hỏi STRIDE:

- **Spoofing:** Ai có thể giả device ID, user session, webhook hoặc policy sender?
- **Tampering:** Ai có thể đổi resource labels, posture values, policy YAML, PEP cache?
- **Repudiation:** Có audit đủ để chứng minh thời điểm đã chặn và ai cấp JIT không?
- **Information disclosure:** Tracing/logs có chứa identity token, IP private, device telemetry và PII không?
- **Denial of service:** Mất MDM/risk event có khiến toàn công ty bị lockout? Step-up loop?
- **Elevation of privilege:** Một dấu “compliant” có bị dùng để cấp quyền admin khi thiếu entitlement?

### 18.3. Bảo vệ decision integrity

PDP output có thể chứa **decision, resource/action scope, TTL, obligations, policy version và session binding**. PEP phải xác thực quyết định đến từ nguồn có thẩm quyền, không cho client gửi header kiểu **X-ZTNA-Allow: true** rồi coi đó là grant. Nếu dùng signed decision token, cần **issuer/audience/replay/expiry** phù hợp; nếu dùng API channel phải bảo vệ **mutual authentication và cache correctness**.

## 19. Quan sát thay đổi trust: event, decision và enforcement

Một chương trình continuous verification có chất lượng cần phân biệt **tín hiệu được ghi nhận**, **quyết định được ban hành**, **policy được PEP nhận** và **resource đã từ chối request**.

### 19.1. Telemetry nên có

| Nguồn | Trường/metric đáng quan tâm | Không mặc nhiên có |
| --- | --- | --- |
| IdP | Auth method, MFA freshness, account disabled, session revoked | Mọi API resource đã ngừng chấp nhận token |
| MDM/EDR | Device ID, posture, event_time, sensor heartbeat, confidence | App permission hoặc tenant ownership |
| PDP/policy engine | Decision ID, rule/revision, resource/action, signal freshness, reason category | Existing tunnel đã bị đóng |
| PEP/gateway/agent | Enforcement state, token/session binding, disconnect time, decision ACK | App đã hủy mọi background task |
| Resource/app | API action, user/tenant authorization, object outcome, HTTP/gRPC status | Thiết bị thực sự healthy chỉ từ request |
| Network/firewall/flow | Connection path, source/dest, volume, deny at network point | JWT nào hoặc operation nào ở L7 |
| SIEM/UEBA | Correlated alerts, incident severity, analyst adjudication | Bằng chứng định danh nếu chỉ có IP |

### 19.2. Mẫu audit event chuẩn hóa

~~~json
{
  "time_utc": "2026-11-28T03:06:00Z",
  "decision_id": "decision-example-205",
  "subject_pseudonym": "user-pseudonym-42",
  "device_id": "managed-device-042",
  "session_id": "session-example-1001",
  "resource": "prod-admin",
  "action": "change_policy",
  "previous_decision": "ALLOW",
  "new_decision": "REVOKE",
  "reason_category": "verified_device_compromise",
  "signal_age_seconds": 12,
  "policy_revision": "ztna-prod-v17",
  "pdp_id": "pdp-region-a",
  "pep_id": "pep-region-a-2",
  "pep_acknowledged": true,
  "enforcement_verified": false
}
~~~

**Đây là schema mô phỏng.** Trường **enforcement_verified=false** nhắc rằng **PEP ACK chưa là bằng chứng mọi request đã bị chặn**. Sau khi thực hiện một phép thử hoặc đối chiếu logs, có thể bổ sung một **enforcement event** riêng; không sửa bản ghi gốc để che độ trễ.

### 19.3. Mốc đo quan trọng

| Metric/SLO ứng viên | Định nghĩa |
| --- | --- |
| **Time to detect** | Từ security event thực đến lúc nguồn/sensor xác nhận |
| **Signal delivery lag** | Từ event_time đến PDP nhận được |
| **Decision latency** | Thời gian PDP ra quyết định đối với một context |
| **Policy propagation lag** | Từ quyết định đến khi PEP áp dụng |
| **Effective revocation latency** | Từ trigger đủ tin cậy đến khi resource/PEP thật sự từ chối access |
| **Stale ALLOW count** | Số lần một grant cũ được dùng sau cutoff theo policy |
| **Unknown/stale posture rate** | Tỷ lệ quyết định thiếu signal đủ mới |
| **False restrictive decision rate** | Trường hợp chặn nhầm được xác minh qua review |
| **Step-up completion and abandonment** | Chất lượng UX và MFA fatigue |
| **Sensitive action unauthorized success** | Sự cố nghiêm trọng khi forbidden action được chấp nhận |

**Không đặt các con số SLA tùy tiện**: lựa chọn phải phụ thuộc data sensitivity, issuer/PEP capabilities, network regions và yêu cầu tuân thủ; đo thực tế bằng permitted tests.

### 19.4. Tránh rò dữ liệu nhạy cảm trong telemetry

Không ghi **raw bearer tokens, session cookies, private keys, toàn bộ device inventory, full HTTP body, GPS location hoặc nội dung EDR nhạy cảm** nếu không cần và không được phép. Dùng **pseudonymous identifiers, event type, authorized principal metadata, policy revision** với retention và quyền truy cập chặt. Một request ID do client cấp không tự bảo đảm tính toàn vẹn; ingress nên normalize theo chính sách.

## 20. Hiệu năng, chi phí và độ tin cậy của continuous checks

Nếu mỗi HTTP request đều gọi PDP từ xa qua mạng, việc kiểm tra có thể tạo **latency và điểm lỗi mới**. Ngược lại, nếu cache ALLOW quá dài, compromised sessions được hưởng quyền quá lâu. Đây là đánh đổi giữa **freshness, tính sẵn sàng và cost**.

### 20.1. Các chiến lược giảm tải

- **Local policy evaluation** tại PEP với signed/validated context khi phù hợp.
- Cache decisions có **key đủ resource/action/user/device/session/policy revision**, không dùng một cờ “user trusted”.
- **Short decision TTL** cho sensitive actions và khác nhau theo resource risk.
- **Event invalidation** để xóa cache khi role/device/session bị thu hồi.
- **Batch/context prefetch** nhưng không sử dụng dữ liệu quá cũ.
- **Step-up only for sensitive operations**, tránh reauth mỗi packet.
- Theo dõi **p95/p99 PDP latency, queue depth, cache hit/miss, event lag và IdP rate limits**.

### 20.2. Cache key là ranh giới bảo mật

Một ví dụ **cache key không đủ**:

~~~text
cache_key = user_id
cache_value = ALLOW
~~~

Khi Alice được ALLOW đọc tài liệu thường, kết quả ấy không thể được tái sử dụng để cho **Alice export Production secrets**. Key logic ít nhất phải xét **principal, device/session binding, resource, action, entitlement/policy revision, signal freshness** và những điều kiện context quan trọng. Không cần lưu raw token trong cache key hoặc log.

### 20.3. Tính toán cửa sổ revoke

Một phiên có thể còn được dùng sau khi account disabled vì:

~~~text
Signal delivery: 15 giây
PDP decision:    1 giây
PEP propagation: 4 giây
API JWT cache:   120 giây nếu không có invalidation
Active stream:   không giới hạn nếu app không hỗ trợ disconnect
~~~

Đây là số liệu **giả định** để nêu vấn đề. Nếu **active stream không có termination/recheck**, thời gian revoke thực tế **không được giới hạn chỉ bằng tổng TTL của PDP**. Mục tiêu thiết kế là **bound mọi đường còn quyền** và có bài test chứng minh.

### 20.4. Capacity của PDP/PEP

Với hệ thống hàng trăm nghìn sessions, một sự kiện **IdP policy change** có thể buộc re-evaluate số lượng lớn người dùng, gây **thundering herd**. Cần **rate limiting, queueing, priority, backpressure, jitter, regional sharding và emergency deny paths**. Không giảm bảo mật bằng cách cho mọi request qua khi PDP quá tải; cấu hình **failure policy theo tài nguyên**, kiểm thử load và khả năng phục hồi.

### 20.5. SLO availability phải đi cùng security SLO

Chỉ đo **login success** có thể khiến chính sách trông tốt khi nó đang cho quá nhiều quyền. Chỉ đo **DENY rate** có thể gây ảo giác an toàn khi hợp lệ bị chặn hàng loạt. Báo cáo vận hành nên gồm:

- **Hợp lệ:** người có quyền trên thiết bị đúng trạng thái truy cập được app trong SLO.
- **Trái quyền:** người sai quyền, device compromised, revoked session bị chặn.
- **Độ trễ:** thay đổi trust có hiệu lực trong khung được phê duyệt.
- **Chất lượng:** false positives, lost events, stale signals, break-glass use và support impact.

## 21. Case study A: thiết bị bị cách ly giữa phiên quản trị Production

**Bối cảnh giả định:** Một SRE đăng nhập cổng quản trị Prod bằng passkey lúc 09:00 UTC, thiết bị managed và EDR báo compliant. Một phiên web và một phiên SSH qua ZTNA broker đang mở. Lúc 09:24, EDR xác nhận hoạt động mã độc và gửi **quarantine signal**.

### 21.1. Timeline cần xây dựng

| Thời điểm (UTC, giả định) | Sự kiện | Điều phải xác minh |
| --- | --- | --- |
| 09:00:00 | User MFA thành công, device compliant | IdP, device assurance, JIT grant và resource entitlement |
| 09:00:02 | PEP cho phép Prod-admin/SSH | Session scope, timeout, device binding, PEP ID |
| 09:24:00 | EDR phát hiện compromise | Nguồn, confidence, device ID, event time |
| 09:24:06 | PDP nhận event | Delivery lag, mapping đúng user/device/session |
| 09:24:07 | PDP quyết định QUARANTINE | Decision ID, policy version, affected resources |
| 09:24:10 | Gateway/agent xác nhận policy update | ACK chưa bảo đảm SSH đã đóng |
| 09:24:12 | Browser bị chặn request mới | 403/deny theo chính sách; app logs |
| 09:24:15 | SSH tunnel/session bị kết thúc | Broker/host logs, session termination |
| 09:24:18 | Endpoint chỉ còn truy cập remediation | Không còn đường vào DB/secrets hoặc VPN bypass |

### 21.2. Các chỗ dễ bỏ sót

1. Browser request mới bị DENY nhưng **terminal SSH vẫn đang mở**.
2. ZTNA tunnel bị ngắt nhưng **API token đã copy** còn được resource server chấp nhận.
3. User bị quarantine trên laptop, nhưng một **service account admin** của user vẫn giữ quyền ở cloud console.
4. PEP tại region A đã áp policy, **DR region B** còn ALLOW do replication delay.
5. **IPv6/direct origin** hoặc private IP bypass gateway vẫn tới resource.
6. Khi EDR báo “compliant” lại sau restart, **JIT grant** đã bị thu hồi không được tự phục hồi.

### 21.3. Ứng phó hợp lý

**Ưu tiên cô lập rủi ro có chứng cứ**: disable/quarantine device identity, revoke affected sessions, chặn new requests, terminate long-lived admin connections nếu hỗ trợ, kiểm tra API/app entitlement và cloud credentials riêng. Đồng thời bảo toàn **EDR, ZTNA, IdP, bastion, cloud audit và application logs** theo quy trình incident.

Phục hồi sau remediation cần **trusted device attestation mới, user authentication theo yêu cầu, entitlement/JIT approval mới nếu đã revoke**, không chỉ clear cờ EDR.

**Bài học:** “ZTNA đã cập nhật policy” không tương đương “mọi đường sử dụng quyền đã chấm dứt”. **Effective revocation** phải được kiểm thử trên **new requests và active connections**, gồm cả credential ngoài broker.

## 22. Case study B: IdP disable account nhưng API JWT vẫn trả 200

**Bối cảnh giả định:** Một tài khoản đối tác bị vô hiệu hóa vì nghi compromise lúc 10:00 UTC. IdP phát event account disabled và gateway ZTNA chặn đăng nhập mới. Tuy nhiên API backend dùng **self-contained JWT access token** còn hạn 30 phút và chỉ kiểm tra **signature, iss, aud, exp**, không kiểm tra session revoked hoặc entitlement change. Requests qua một **đường API trực tiếp** vẫn trả 200.

### 22.1. Hai đường ra quyết định

~~~mermaid
flowchart LR
    C["Client có token cũ"] --> G["ZTNA Gateway: disabled -> DENY"]
    C -. "Direct API route / missing PEP" .-> A["API resource server"]
    A --> V["Verify JWT signature/expiry only"]
    V -->|"Token vẫn còn hạn"| D["Data access có thể tiếp tục"]
    I["IdP disabled event"] --> P["PDP"]
    P --> G
    P -. "No revocation integration" .-> A
~~~

### 22.2. Tìm nguyên nhân

| Bằng chứng | Ý nghĩa |
| --- | --- |
| IdP account disabled event | Identity provider đã cập nhật trạng thái |
| Gateway decision DENY | Một PEP đã chặn đúng |
| API logs 200 sau 10:00 | Có access tiếp tục, cần xác định đường đi và quyền |
| Access token exp sau 10:00 | Resource server có thể coi token còn hợp lệ |
| Missing token introspection/session-version check | Thiếu kiểm tra revocation ở resource |
| Direct API hostname/IP còn public | Origin/gateway bypass |
| Application object auth logs | Tài nguyên nào đã được đọc/sửa thực sự |

### 22.3. Khắc phục hệ thống

1. Đóng **direct origin bypass** ở network boundary và yêu cầu backend xác thực identity/authorization theo chính sách.
2. Thiết kế **revocation path tới resource server**: session/grant version, introspection, denylist hoặc event-driven update tùy nền tảng.
3. Giảm **access-token lifetime** nơi thích hợp, đồng thời quản lý refresh tokens và caches.
4. Đo **stale-ALLOW duration** tại cả gateway và API qua test được phép.
5. Không global rotate **IdP signing key** cho một user chỉ để tắt token cũ nếu có cơ chế scope hẹp an toàn.
6. Điều tra các data access sau cutoff, xác minh **user/tenant/object-level authorization** và tác động.

**Bài học:** Identity event, policy decision và token acceptance là **ba lớp khác nhau**. Continuous verification không đầy đủ nếu **resource server** vẫn bỏ qua revocation của phiên.

## 23. Case study C: hệ thống MDM mất kết nối gây khóa nhầm

**Bối cảnh giả định:** Sau một sự cố dịch vụ MDM, dữ liệu compliance của thiết bị không cập nhật. Risk engine phân loại tất cả devices **unknown** thành **compromised**, khiến nhiều nhân viên bị chặn ứng dụng nội bộ. Đội hỗ trợ muốn tắt mọi posture checks để khắc phục ngay.

### 23.1. Phân tích tín hiệu đúng

| Quan sát | Diễn giải phù hợp |
| --- | --- |
| Heartbeat MDM không cập nhật | Signal stale/unknown, chưa chứng minh malware |
| IdP hoạt động bình thường | Identity authentication vẫn có thể kiểm tra độc lập |
| Không có EDR detection mới | Không chứng minh endpoints an toàn; có thể pipeline mất |
| User login thành công nhưng bị DENY | Policy posture/failure mode có thể gây gián đoạn |
| Active admin sessions vẫn tồn tại | Có thể là cached ALLOW cần kiểm tra |

### 23.2. Phương án có kiểm soát

1. Mở **data-quality/availability incident** cho MDM pipeline, xác định phạm vi/regions/tenant.
2. Xác định **stale signal TTL** đang áp và rule đã ép unknown thành compromised; không sửa trực tiếp Prod policy mà không có change control.
3. Với **low sensitivity apps**, cân nhắc **restricted mode/short grace** nếu được security owner phê duyệt, theo dõi telemetry và thời hạn.
4. Với **Production admin/secrets**, tiếp tục yêu cầu fresh posture hoặc dùng **break-glass được kiểm soát**, không fail-open toàn bộ.
5. Sửa API/integration/IAM hoặc queue pipeline, kiểm tra **event freshness**, out-of-order và missing status.
6. Restore quyền khi có **signal mới đáng tin + entitlement còn hợp lệ**; không tự phát admin grant.
7. Postmortem: policy unknown/stale/compromised phải tách rõ, có **synthetic health checks và false-positive SLO**.

**Bài học:** Continuous verification phải phân biệt **thiếu bằng chứng** với **bằng chứng xấu**. Một phản ứng bảo mật sai có thể tạo **doanh nghiệp tự DoS** và kích thích người vận hành bỏ kiểm soát.

## 24. Case study D: service mesh chưa áp kịp quyết định thu hồi workload

**Bối cảnh giả định:** Service **orders** dùng mTLS để gọi **payments**, rồi runtime security báo một Pod Orders bị compromise. Security team cập nhật policy từ ALLOW sang DENY theo **workload principal**. Một số Payments sidecars nhận policy mới ngay, nhưng một subset ở region dự phòng vẫn chạy **effective config revision** cũ.

### 24.1. Tại sao điều này quan trọng?

**Valid mTLS certificate** xác thực Orders không phải bằng chứng Pod chưa bị chiếm. Khi principal bị revoke, **authorization policy tại bên nhận** phải đổi đủ nhanh; nếu inbound proxy còn cho phép do cache/xDS staleness, attacker có thể tiếp tục dùng danh tính hợp lệ.

### 24.2. Quy trình

1. Đối chiếu **runtime event → PDP decision → mesh control config → effective inbound policies** trên từng cluster/region.
2. Xác định **Pod UID, ServiceAccount/SPIFFE ID, namespace, certificate serial và cluster**; không chặn nhầm mọi Orders replicas nếu chỉ một compromised Pod có thể tách identity.
3. Tạm thời **quarantine network/pod/node** theo incident plan, đồng thời thực thi **server-side deny**.
4. Xác minh **new RPCs bị DENY**, existing gRPC streams được cắt/recheck theo yêu cầu.
5. Kiểm tra **certificate rotation, STS credentials, Kubernetes RBAC/IAM và application resource access** ngoài mTLS.
6. Khi phục hồi, chỉ cho workload từ **known-good deployment, attestation/identity và policy version** quay lại.

**Bài học:** Trong hệ phân tán, **policy consistency và effective denial** là phần của continuous trust. Một rollout policy “thành công” ở control plane chưa đủ khi data plane có thể không đồng nhất.

## 25. Lab Python offline: mô phỏng mức tin cậy thay đổi theo sự kiện

Bài lab này **không mở socket, không gọi IdP/MDM/EDR/PDP/PEP, không đọc JWT, không ghi tệp và không thay chính sách thật**. Toàn bộ identity, events và timestamps là **dữ liệu tổng hợp**, dùng Python để hiểu **thứ tự ưu tiên, freshness, hard deny, step-up và quarantine**.

### 25.1. Quy tắc của mô hình

1. **Account disabled hoặc session revoked** thắng mọi điều kiện khác → **REVOKE**.
2. Không authenticated hoặc **không có entitlement** cho action → **DENY**, dù posture tốt.
3. Với admin write, nếu chưa có JIT grant → **DENY**.
4. Sự kiện **COMPROMISED** còn hiệu lực → **QUARANTINE**, không bị một heartbeat COMPLIANT bình thường tự xóa.
5. Muốn thoát quarantine phải có sự kiện **CLEARED từ nguồn incident-response có thẩm quyền**, sau đó có posture COMPLIANT mới.
6. Posture thiếu/quá **300 giây** → **RESTRICT** với action xem thông tin thấp hơn, **DENY** với admin write.
7. Admin write có quyền và posture tốt nhưng **strong authentication quá 300 giây** → **STEP_UP**.
8. Nếu đủ điều kiện → **ALLOW** theo action; không ngầm mở thêm các quyền khác.

**Các mốc và trạng thái là giả định cho lab, không phải ngưỡng bắt buộc theo NIST hay sản phẩm ZTNA.** Trong hệ thống thực, một **verified malware signal** có thể buộc revoke khẩn theo chính sách và không được cho phép recovery dựa vào một event không được xác thực.

### 25.2. Source Python 3.10+ không có tác động ngoại vi

~~~python
from dataclasses import dataclass, replace
from datetime import datetime, timezone


def utc(text: str) -> datetime:
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("UTC offset required")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Signal:
    time: datetime
    kind: str
    source: str


@dataclass(frozen=True)
class Context:
    now: datetime
    action: str
    authenticated: bool
    account_enabled: bool
    session_revoked: bool
    entitled_actions: tuple[str, ...]
    jit_grant_active: bool
    last_strong_auth: datetime | None
    signals: tuple[Signal, ...]


SENSITIVE_ACTIONS = {"change_policy", "export_config"}
POSTURE_TTL_SECONDS = 300
MFA_TTL_SECONDS = 300


def effective_posture(ctx: Context) -> str:
    """Signal precedence demo; does NOT verify sensor authenticity."""
    events = [s for s in ctx.signals if s.time <= ctx.now]
    compromises = [s.time for s in events if s.kind == "COMPROMISED"]
    clearances = [
        s.time for s in events
        if s.kind == "CLEARED" and s.source == "SECURITY_IR"
    ]

    # Security incident requires explicit authorized clearance;
    # ordinary COMPLIANT heartbeats cannot erase a compromise.
    if compromises:
        last_compromise = max(compromises)
        later_clearances = [
            t for t in clearances if t >= last_compromise
        ]
        if not later_clearances:
            return "COMPROMISED"
        valid_from = max(later_clearances)
    else:
        valid_from = datetime.min.replace(tzinfo=timezone.utc)

    compliant = [
        s.time for s in events
        if s.kind == "COMPLIANT" and s.time >= valid_from
    ]
    if not compliant:
        return "UNKNOWN"

    age = (ctx.now - max(compliant)).total_seconds()
    return "COMPLIANT" if age <= POSTURE_TTL_SECONDS else "STALE"


def decide(ctx: Context) -> tuple[str, str]:
    if not ctx.account_enabled or ctx.session_revoked:
        return ("REVOKE", "Account or session explicitly disabled")

    if not ctx.authenticated:
        return ("DENY", "Unauthenticated")

    if ctx.action not in ctx.entitled_actions:
        return ("DENY", "Missing resource/action entitlement")

    if ctx.action in SENSITIVE_ACTIONS and not ctx.jit_grant_active:
        return ("DENY", "JIT grant missing")

    posture = effective_posture(ctx)
    if posture == "COMPROMISED":
        return ("QUARANTINE", "Verified device compromise")

    if posture != "COMPLIANT":
        if ctx.action == "view":
            return ("RESTRICT", "Fresh posture unavailable")
        return ("DENY", "Sensitive action needs fresh posture")

    if ctx.action in SENSITIVE_ACTIONS:
        if ctx.last_strong_auth is None:
            return ("STEP_UP", "Fresh strong authentication needed")
        auth_age = (ctx.now - ctx.last_strong_auth).total_seconds()
        if auth_age < 0 or auth_age > MFA_TTL_SECONDS:
            return ("STEP_UP", "Strong authentication too old")

    return ("ALLOW", "Entitlement and current checks satisfied")


signals = (
    Signal(utc("2026-11-28T09:58:00Z"), "COMPLIANT", "EDR"),
    Signal(utc("2026-11-28T10:05:00Z"), "COMPROMISED", "EDR"),
    # Late low-trust heartbeat: must NOT clear incident.
    Signal(utc("2026-11-28T10:06:00Z"), "COMPLIANT", "MDM"),
    Signal(utc("2026-11-28T10:12:00Z"), "CLEARED", "SECURITY_IR"),
    Signal(utc("2026-11-28T10:13:00Z"), "COMPLIANT", "EDR"),
)

base = Context(
    now=utc("2026-11-28T10:00:00Z"),
    action="view",
    authenticated=True,
    account_enabled=True,
    session_revoked=False,
    entitled_actions=("view", "change_policy"),
    jit_grant_active=True,
    last_strong_auth=utc("2026-11-28T09:50:00Z"),
    signals=signals,
)

cases = [
    ("before", base),
    ("admin_step_up", replace(base, action="change_policy")),
    ("compromised", replace(base, now=utc("2026-11-28T10:06:30Z"))),
    ("cleared", replace(base, now=utc("2026-11-28T10:14:00Z"))),
    ("no_entitlement", replace(base, entitled_actions=())),
    ("revoked", replace(base, session_revoked=True)),
    ("no_signals", replace(base, signals=())),
]

for name, context in cases:
    print(name, decide(context)[0])

assert decide(cases[0][1])[0] == "ALLOW"
assert decide(cases[1][1])[0] == "STEP_UP"
assert decide(cases[2][1])[0] == "QUARANTINE"
assert decide(cases[3][1])[0] == "ALLOW"
assert decide(cases[4][1])[0] == "DENY"
assert decide(cases[5][1])[0] == "REVOKE"
assert decide(cases[6][1])[0] == "RESTRICT"
~~~

Kết quả dự kiến:

~~~text
before ALLOW
admin_step_up STEP_UP
compromised QUARANTINE
cleared ALLOW
no_entitlement DENY
revoked REVOKE
no_signals RESTRICT
~~~

### 25.3. Điều lab cố tình không mô phỏng

- **Authentication/attestation thật:** Các cờ authenticated, source và device ID được coi đã xác minh, nhưng code không kiểm tra JWT, FIDO2, EDR signature hoặc posture attestation.
- **Event delivery thực:** Code dùng event time, không có nhận trễ/out-of-order ingestion và không có dedup/replay ở bus.
- **PDP/PEP distribution:** Hàm trả decision, nhưng không tạo session grant, policy push, disconnect tunnel hay 403 ở ứng dụng.
- **Network bypass:** Không có DNS, NAT, VPN, IPv6, direct origin, multi-PEP region hoặc firewall.
- **Quyền resource cụ thể:** Entitlement tuple là mô hình giản lược, không xử lý tenant/object ownership, delegation và admin approval thật.
- **Phục hồi thiết bị:** SECURITY_IR chỉ là tên nhãn được trust trong demo; hệ thống thật cần người/cơ chế có thẩm quyền với audit và attestation.
- **Active transactions:** Không mô phỏng tạm dừng export, rollback transaction hay stream termination.

**Lưu ý thiết kế:** Trong code, tại 10:14 UTC, trạng thái được phục hồi thành ALLOW cho action view vì có **CLEARED và COMPLIANT mới**. Không có nghĩa một **JIT grant đã được revoke trong incident** cũng được tái cấp tự động. Thực tế cần event/grant state bổ sung; mọi quyền elevated phải có phê duyệt còn hợp lệ.

### 25.4. Bài tập mở rộng

1. Thêm **source credibility** và chữ ký/claim validation logic giả lập; chỉ nguồn được phê duyệt mới có thể gỡ QUARANTINE.
2. Thêm **received_at, event_id, sequence** để xử lý duplicated và out-of-order events.
3. Thêm **PDP decision TTL, PEP local cache TTL**, tính effective revoke time theo các giới hạn giả định.
4. Thêm **long-lived gRPC stream** chỉ bị cắt khi PEP nhận event; phân biệt new request DENY với active stream vẫn mở.
5. Thêm **risk score** cho tín hiệu không phải hard deny, có smoothing/hysteresis và test false positives.
6. Phân biệt **unknown vs stale vs sensor unavailable** và policy cho low/high sensitivity resource.
7. Thêm **JIT grant expiry và resource scope**, xác minh step-up không tự tạo entitlement.
8. Thêm **cross-region PEP versions** và test policy update thiếu ACK làm rủi ro truy cập còn tồn tại.
9. Thiết kế event **user revoked** thắng mọi posture update, kể cả event đến trễ.
10. Thêm log **decision_id, policy_rev, signal_freshness, PEP ACK và enforcement check** mà không ghi raw token.

## 26. Runbook: một signal làm thay đổi mức tin cậy

### 26.1. Quy trình xử lý bình thường

~~~mermaid
flowchart TD
    A["Security / posture / IAM event"] --> B["Verify source, signature, event time and identity mapping"]
    B --> C{"High confidence hard deny?"}
    C -- "Có" --> D["REVOKE/QUARANTINE affected identity/session"]
    C -- "Không" --> E["Evaluate policy resource/action and signal freshness"]
    E --> F["ALLOW, STEP_UP, RESTRICT, DENY"]
    D --> G["Propagate to PEP and resource servers"]
    F --> G
    G --> H["Validate new requests and active sessions"]
    H --> I["Correlate audit + monitor SLO and false positives"]
    I --> J["Remediation / re-evaluate only when conditions met"]
~~~

1. **Nhận sự kiện:** kiểm tra owner/source, identity/device/session mapping, timestamp, confidence, integrity.
2. **Phân loại tác động:** Critical app/operation, resource sensitivity, user population, môi trường Prod/Dev.
3. **Chọn quyết định:** Hard DENY/QUARANTINE theo chính sách; với risk vừa, STEP_UP hoặc RESTRICT.
4. **Chỉ rõ enforcement:** Gateway/agent, app token verifier, mesh proxy, VPN broker và network policy nào liên quan?
5. **Đo hiệu lực:** PEP decision ACK, test new request, active session disconnect, API resource server reject.
6. **Theo dõi rủi ro còn lại:** Token JWT chưa hết hạn, tunnel/stream còn mở, region chưa hội tụ, stale signal.
7. **Phục hồi đúng quyền:** User/device mới được xác minh; JIT/entitlement được xét lại độc lập.
8. **Ghi audit:** Ticket/incident ID, policy revision, actor/approver, UTC timeline, evidence, rollback/remaining gaps.

### 26.2. Runbook cho sự cố nhạy cảm

Khi có **verified account compromise** hoặc thiết bị bị xác nhận nhiễm mã độc:

- **Cô lập/thu hồi nhanh**: account/session/device grant/PEP routes/credential verifier theo scope có chứng cứ.
- **Không bắt user chỉ làm MFA** rồi giữ nguyên quyền khi endpoint vẫn bị chiếm.
- Kiểm tra **API tokens, cloud sessions, browser cookies, SSH/RDP, VPN, service accounts** đã tách vòng đời.
- Correlate **IdP, EDR, PEP, SIEM, firewall/flow, application và cloud audit**; tìm các request đã hoàn thành sau cutoff.
- Nếu có exfiltration hay truy cập dữ liệu nhạy cảm, phối hợp **data owner/privacy/legal/incident commander** theo policy.
- **Phục hồi từ thiết bị/phiên đáng tin**, không dùng credentials nghi bị lộ, và kiểm tra ALLOW/DENY.

### 26.3. Runbook khi chặn nhầm hàng loạt

1. Tạo **incident về availability/data quality**, xác nhận một vendor/signal source đang lỗi.
2. Không đổi mọi devices thành compliant; giữ trạng thái **unknown/stale** và xác định ứng dụng nào bị ảnh hưởng.
3. Áp **policy đã được phê duyệt**: low-risk có thể limited grace, high-risk vẫn DENY, break-glass có audit.
4. Khôi phục event bus/API, xử lý lag, stale caches, rejected policy updates.
5. Đo false-positive count, login/step-up success, business SLI và security denies.
6. Chấm dứt exception đúng hạn, xác minh các restrictions và postmortem.

### 26.4. Change record

~~~text
CHANGE/INCIDENT ID / UTC WINDOW:
SUBJECT/DEVICE/SESSION (pseudonymous IDs; NO TOKENS):
RESOURCE, ACTION, ENVIRONMENT, OWNER:
BEFORE: entitlement, assurance, posture, PDP decision, PEP state:
SIGNAL: source, timestamp, freshness, confidence, schema/event ID:
POLICY: revision, rule, override/break-glass status:
AFTER: ALLOW / STEP_UP / RESTRICT / QUARANTINE / REVOKE / DENY:
ENFORCEMENT: PEP IDs, app verifier, active stream/tunnel status:
EVIDENCE: IdP, MDM/EDR, gateway, app, network, audit logs:
REVOCATION EFFECTIVE TIME and REMAINING WINDOW:
USER REMEDIATION and BUSINESS SLI:
APPROVAL, CANARY/ROLLBACK, POSTMORTEM:
~~~

### 26.5. Rollback với security-first constraints

Không được gọi **khôi phục ALLOW cho compromised identity** là rollback an toàn chỉ vì giúp hết outage. Rollback nên là **đưa logic/policy về bản đã được phê duyệt không tái mở lỗ hổng**, hoặc fix forward để khôi phục nguồn signal/PEP, dùng **break-glass scope hẹp** nếu bắt buộc và được duyệt.

## 27. Ma trận kiểm thử continuous verification và mức tin cậy

Các test bên dưới chỉ thực hiện trên **lab, staging hoặc tài sản/hệ thống thuộc phạm vi được cấp quyền**. Không thử credential theft, scan/bypass hoặc gây gián đoạn trên hệ thống bên thứ ba. Các ca **revoke, network disconnect, account disable, compromised-device simulation, DR failover** phải có owner, approval, rollback và người giám sát SLO.

| Test ID | Tình huống | Kết quả và bằng chứng mong đợi |
| --- | --- | --- |
| ZT-01 | User có entitlement, device compliant, auth còn fresh | **ALLOW** đúng app và action; session scope/TTL chính xác |
| ZT-02 | User xác thực được nhưng không có entitlement | **DENY** dù posture và MFA tốt |
| ZT-03 | User có quyền view nhưng không có quyền write | View ALLOW, write DENY ở PEP/app |
| ZT-04 | Quản trị Prod yêu cầu quyền JIT mới | Chỉ ALLOW khi grant được phê duyệt, chưa hết hạn |
| ZT-05 | JIT grant hết hạn khi đang mở portal | New admin action DENY; existing session xử lý theo policy |
| ZT-06 | MFA đủ mạnh nhưng quá cũ cho hành động nhạy cảm | STEP_UP, không thực hiện action trước challenge |
| ZT-07 | Step-up thành công nhưng thiếu quyền export | Vẫn DENY vì entitlement không thay đổi |
| ZT-08 | Device fresh compliant rồi chuyển noncompliant | Quyết định RESTRICT/DENY theo resource risk, transition có audit |
| ZT-09 | Verified malware trong phiên đang mở | QUARANTINE/REVOKE; PEP chặn new requests và active sessions theo plan |
| ZT-10 | Device status unknown do chưa enrollment | Không ép unknown thành compliant; remediation path rõ |
| ZT-11 | EDR heartbeat quá freshness TTL | Stale signal dẫn tới recheck/restrict theo chính sách |
| ZT-12 | MDM/EDR unavailable trong lab | Low/high sensitivity failure policy khác nhau, không fail-open tất cả |
| ZT-13 | Event COMPLIANT cũ đến sau malware alert | Không ghi đè QUARANTINE trái policy |
| ZT-14 | Duplicate event/replay trong event bus | Idempotency/sequence và audit không tạo flapping |
| ZT-15 | Event source chưa xác thực | Không được cập nhật device/account trust |
| ZT-16 | Device được IR clearance + posture tốt trở lại | Chỉ re-evaluate khi có attestation và approval phù hợp |
| ZT-17 | Incident clearance nhưng entitlement đã revoked | Không tự phục hồi quyền admin/JIT |
| ZT-18 | IdP account disabled trong session | REVOKE thắng cache ALLOW và strong MFA trước đó |
| ZT-19 | Refresh token revoked nhưng JWT cũ còn hạn | Xác định cửa sổ còn accept; resource enforcement theo thiết kế |
| ZT-20 | Opaque token introspection với cache stale | Deny hiệu lực trong TTL/SLO, test cache invalidation |
| ZT-21 | CAE/resource/client hỗ trợ event revoke | Event được propagate và resource thực từ chối theo khả năng |
| ZT-22 | API direct origin bypass ZTNA gateway | **DENY** bằng network/backend auth; không thể dùng token cũ |
| ZT-23 | IPv4 và IPv6 backend ingress | Cùng policy, không mở listener khác ngoài ý định |
| ZT-24 | VPN tunnel broad route vs ZTNA app scope | App-only permission không mở DB/subnet lateral access |
| ZT-25 | WebSocket active khi user bị revoked | New handshake DENY, active stream bị cắt hoặc app-level deny theo design |
| ZT-26 | gRPC stream dài sau role change | Stream termination/recheck đáp ứng security window |
| ZT-27 | HTTP/2 connection còn mở nhiều RPCs | New sensitive RPC DENY dù connection được reuse |
| ZT-28 | SSH/RDP session qua ZTNA broker | Disconnect verified, reconnect không dùng stale session |
| ZT-29 | API object của tenant khác với token hợp lệ | App object-level authorization DENY |
| ZT-30 | Thiết bị được quản lý nhưng source IP mới | Không tự block chỉ vì IP; correlate device/session và risk |
| ZT-31 | Impossible travel do corporate proxy/VPN | Triage false positive, không auto-revoke thiếu chứng cứ |
| ZT-32 | High-confidence malicious signal có chữ ký | Ưu tiên hard deny, không chờ risk score threshold |
| ZT-33 | PDP unavailable | Local PEP cache/failure policy theo resource, alert và TTL rõ |
| ZT-34 | PEP disconnected khỏi PDP lâu hơn TTL | Không giữ critical ALLOW vô hạn |
| ZT-35 | Policy push NACK/không hội tụ ở một region | Drift alert, affected sessions và failover được xử lý |
| ZT-36 | ZTNA config updated nhưng API vẫn accept token | Enforcement test phát hiện mismatch giữa PDP và resource |
| ZT-37 | Cloud workload ServiceAccount đổi role | Mesh/IAM/app policy re-evaluate; unauthorized RPC bị chặn |
| ZT-38 | Workload mTLS certificate bị compromise trong tabletop | Deny principal, rotation và active connections được rà soát |
| ZT-39 | Sensor outage gây hàng loạt false deny | Data-quality incident, limited grace đã duyệt, high-risk DENY |
| ZT-40 | Login/MFA challenge lặp nhanh | Có chống MFA fatigue, retry/backoff và UX phù hợp |
| ZT-41 | Cache key chỉ theo user, không theo resource/action | Test bắt lỗi privilege bleed; fix key và invalidate |
| ZT-42 | Signed decision có wrong issuer/audience/expiry | PEP từ chối, không tin client-provided ALLOW headers |
| ZT-43 | Token cố dùng từ device khác | Sender-binding/replay detection nếu hệ thống hỗ trợ |
| ZT-44 | Unknown risk signal trên low sensitivity app | RESTRICT/remediation đúng scope, không mở elevated actions |
| ZT-45 | Quarantine device cần patch | Chỉ cho phép approved remediation endpoints, DB/admin DENY |
| ZT-46 | Một workload mới scale Pod nhưng SA identity tương tự | Quyền vẫn least-privilege, không cấp cloud admin tự động |
| ZT-47 | DR failover/quên policy ở region dự phòng | Mọi PEP ở DR có effective policy và peer trust phù hợp |
| ZT-48 | Trace/log chứa synthetic auth token marker | Redaction qua IdP, gateway, app, SIEM/ticket, không lưu raw token |
| ZT-49 | Bulk export trong session view được phép | Step-up/approval/app authZ trước export, monitor result |
| ZT-50 | Device lost và user đổi mật khẩu | Kiểm tra tất cả cookies/tokens/tunnels, không giả định password reset revoke mọi thứ |
| ZT-51 | Kết thúc một exception break-glass | Quyền hết hạn, audit được giữ, policy mặc định phục hồi |
| ZT-52 | Security rollout rollback | Không tái mở compromised session/allow-any gateway |
| ZT-53 | PEP báo ACK nhưng active RDP còn mở | Enforcement validation phát hiện và kích hoạt disconnect/remediation |
| ZT-54 | Rule liên tục ALLOW/DENY do sensor flapping | Hysteresis/debounce cho low confidence, incident hard deny vẫn nhanh |
| ZT-55 | Event pipeline mất dữ liệu/lag tăng | Quality alert, quyết định không dựa vào “không alert” là an toàn |
| ZT-56 | User compliant lại nhưng JIT grant hết hiệu lực | Quyền admin không tự hồi sinh, JIT approval mới cần thiết |

### 27.1. Mẫu hồ sơ test

~~~text
TEST / CHANGE ID:
ENVIRONMENT / REGION / RESOURCE / ACTION:
SUBJECT / DEVICE / WORKLOAD / SESSION pseudonymous IDs:
IDP / MDM / EDR / IAM / RISK SIGNALS:
Event time UTC / received time / freshness / confidence:
PDP policy revision / decision ID / intended decision:
PEP IDs / applied version / cache TTL / ACK time:
Network/transport: HTTP, gRPC stream, SSH, VPN, TLS:
Resource app authorization / entitlement / JIT status:
Expected new request outcome:
Expected existing session/stream outcome:
Actual DENY/ALLOW and effective time evidence:
Security SLO / business SLI / false positive impact:
Rollback/owner/approval/remediation/remaining gaps:
~~~

### 27.2. Không đếm một test login là “continuous verified”

Ít nhất phải có:

1. **Initial ALLOW** khi identity, device và action hợp lệ.
2. **Mid-session trust decrease** với tín hiệu đã xác minh.
3. **Enforcement ở PEP và resource** trên new request lẫn active session nếu yêu cầu.
4. **Recovery** khi có bằng chứng mới và entitlement hợp lệ; không phục hồi grant đã revoke.
5. **Failure mode** khi PDP/sensor/network unavailable.
6. **Multi-region/IPv4/IPv6/origin bypass** regression khi topology có những đường này.

**Những test đạt ở staging chưa chứng minh Production đã được bảo vệ**: cần effective configuration readback, telemetry, account/resource inventory và post-change checks phù hợp.

## 28. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Zero trust nghĩa là không tin bất kỳ ai nên không thể làm việc.” | Quyền được cấp có điều kiện, giới hạn và được kiểm chứng lại. |
| “Continuous verification nghĩa là MFA từng packet.” | Thường kết hợp event-driven, TTL, periodic và per-operation checks. |
| “Đăng nhập thành công nghĩa là mọi thao tác trong session hợp lệ.” | Entitlement, resource/action, posture và assurance có thể thay đổi. |
| “Một người có trust score cao thì được quyền admin.” | Risk score không tạo entitlement hay JIT approval. |
| “MFA xong thì device bị malware vẫn trusted.” | Identity proof không thay endpoint security posture. |
| “Device MDM-enrolled nghĩa là luôn compliant.” | Enrollment khác runtime posture; signal cần freshness. |
| “EDR không gửi alert thì thiết bị chắc an toàn.” | Sensor có thể unavailable/stale hoặc bỏ sót detections. |
| “Unknown, stale và compromised là giống nhau.” | Bằng chứng thiếu khác bằng chứng compromise; policy phải tách. |
| “Tín hiệu đến sau là tín hiệu mới hơn.” | Event time/sequence có thể khác received time; chống out-of-order. |
| “Một heartbeat compliant tự xóa malware quarantine.” | Cần clearance có thẩm quyền và posture mới sau remediation. |
| “Một địa chỉ IP công ty là chứng nhận device identity.” | NAT, VPN, IP reuse khiến network origin không chứng minh identity. |
| “Impossible travel chắc là account bị chiếm.” | Corporate VPN, proxy và geo IP có thể gây false positives. |
| “Policy engine đã DENY thì backend không thể trả 200.” | PEP không áp kịp, token cache hoặc direct origin bypass có thể tồn tại. |
| “PEP ACK chứng minh mọi session đã bị ngắt.” | ACK chưa chắc đồng nghĩa active stream/tunnel đã bị terminate. |
| “Logout/xóa cookie làm mọi access token đã cấp vô hiệu.” | JWT self-contained hoặc API session khác có thể còn hạn. |
| “Thu hồi refresh token làm access token cũ hết hạn ngay.” | Access token có lifecycle riêng, cần resource-side revocation khi cần. |
| “JWT signature hợp lệ nghĩa là user đang được phép.” | Issuer/audience/expiry chưa đủ cho resource/tenant entitlement hiện tại. |
| “Short-lived tokens giải quyết mọi rủi ro.” | Cửa sổ TTL còn có và attacker có thể lấy token mới khi process bị chiếm. |
| “CAE tự hoạt động với mọi OAuth/JWT clients.” | Chỉ hiệu lực với identity/resource/client hỗ trợ và cấu hình đúng. |
| “Ràng buộc token với device ngăn compromise trên chính device.” | Process bị chiếm có thể sử dụng credentials tại holder. |
| “Đổi password tức thì cắt SSH, WebSocket và gRPC.” | Long-lived sessions cần disconnect/recheck riêng. |
| “Một TCP connection chỉ có một request.” | HTTP/2 multiplexing/gRPC streams có thể có nhiều operations. |
| “Một ZTNA gateway đủ bảo vệ mọi network route.” | Direct origin, IPv6, private ingress hoặc alternate path có thể bypass. |
| “ZTNA luôn loại bỏ nhu cầu firewall/VPN/IDS.” | ZTNA bổ sung identity-based controls, network security vẫn cần. |
| “VPN luôn không an toàn, ZTNA luôn an toàn.” | Cả hai phụ thuộc thiết kế, policy, segmentation và enforcement. |
| “Step-up MFA làm user có thêm quyền.” | Assurance tăng, entitlement vẫn phải được cấp riêng. |
| “JIT hết hạn nhưng đã kết nối nên được tiếp tục write.” | Session/app authorization phải kiểm soát expiry theo policy. |
| “Có mTLS là mọi workload cùng CA được gọi nhau.” | Cần identity authorization và app-level resource checks. |
| “Risk engine outage thì mở toàn bộ app để đảm bảo uptime.” | Failure policy theo resource; critical actions có thể fail closed. |
| “Fail closed đồng nghĩa không cần remediation UX.” | Cần thông báo an toàn và đường khắc phục được giới hạn. |
| “False positive không nguy hiểm vì chỉ chặn.” | Có thể gây gián đoạn lớn, MFA fatigue và bỏ kiểm soát. |
| “Đổi ZTNA policy ở control plane là mọi PEP đã đổi.” | Phải đo propagation, effective config và long-lived sessions. |
| “Một request DENY ở IPv4 chứng minh IPv6 cũng bị chặn.” | Phải kiểm tra mọi ingress/IP family/region có hỗ trợ. |
| “Log càng nhiều token/PII thì điều tra càng chính xác.” | Raw secrets làm tăng lộ lọt; nên log metadata bảo vệ. |
| “Risk giảm nghĩa là mọi quyền cũ được khôi phục.” | Revoked entitlement/JIT grant cần cấp lại hợp lệ. |

## 29. Câu hỏi ôn tập và bài tập kiến trúc

1. **Continuous verification khác xác thực một lần ở đâu?** Đánh giá quyền lại khi context thay đổi/đến mốc policy, không mặc định ALLOW mãi.
2. **Verify explicitly có đồng nghĩa MFA mọi request?** Không, tùy action, risk, signal freshness và enforcement capacity.
3. **PDP và PEP khác nhau ra sao?** PDP quyết định theo policy/context, PEP thực thi trên luồng truy cập.
4. **Tại sao PEP ACK không đủ?** Có thể active tunnel/token/resource server vẫn chấp nhận quyền cũ.
5. **Account authenticated nhưng không có entitlement thì sao?** DENY, bất kể điểm rủi ro thấp.
6. **Device compliant từ 2 giờ trước có còn tin được không?** Phụ thuộc TTL/freshness, không mặc định.
7. **Unknown posture khác compromised thế nào?** Thiếu bằng chứng khác có bằng chứng xấu.
8. **Sự kiện COMPLIANT đến trễ có thể làm gì sai?** Ghi đè quarantine nếu xử lý theo received order mà không có precedence.
9. **Step-up có tự cấp role mới không?** Không, chỉ tăng assurance; quyền cấp qua IAM/JIT riêng.
10. **Làm sao tránh MFA fatigue?** Chỉ step-up khi cần, chống duplicate prompts, freshness window, hard deny khi confirmed compromise.
11. **Tại sao geo IP không đủ chứng minh impossible travel?** VPN/proxy/CGNAT khiến egress ở vị trí khác.
12. **Risk score có thay application authorization?** Không, object/tenant/function permissions cần kiểm tra riêng.
13. **Vì sao logout không nhất thiết vô hiệu access JWT?** Self-contained token được API chấp nhận đến expiry hoặc policy check mới.
14. **Introspection cache có rủi ro gì?** Resource có thể dùng decision cũ sau revoke.
15. **CAE dùng trong mọi API không?** Không, cần client/IdP/resource hỗ trợ và triển khai đúng.
16. **Một gRPC stream đang mở được xử lý khi user revoked thế nào?** Cần app/PEP stream termination hoặc recheck theo security window.
17. **Có nên giữ SSH active nếu account bị disable?** Phụ thuộc chính sách nhưng admin sensitive thường phải chặn/ngắt, có kiểm chứng.
18. **Vì sao direct origin nguy hiểm?** Bypass ZTNA gateway, WAF/identity policy không được áp trên đường đó.
19. **Vì sao network segmentation vẫn cần?** Giới hạn route/bypass/lateral movement, đặc biệt khi credentials bị lộ.
20. **Workload identity bị compromise có thể tiếp tục dùng mTLS không?** Có nếu verifier/PEP chưa deny hoặc active connection chưa cắt.
21. **Policy freshness TTL khác token TTL như thế nào?** Một cái là tuổi dữ liệu, cái kia là thời gian token có hiệu lực.
22. **Hysteresis giải quyết gì?** Tránh state flapping với tín hiệu yếu; không được trì hoãn hard deny nghiêm trọng.
23. **Khi PDP unavailable, nên fail open hay closed?** Thiết kế theo sensitivity, approved failure mode và duration giới hạn.
24. **Khôi phục device compliant có tự hoàn JIT role không?** Không nếu role đã thu hồi/hết hạn.
25. **Quan sát nào cần để đo effective revocation?** Trigger, PDP decision, PEP state, app verifier reject, active session status.
26. **Làm sao xử lý false positive MDM outage?** Unknown/stale policy, remediation, limited grace cho low-risk, không mở critical.
27. **Một trust decision cache key phải xét gì?** Principal, device/session, resource, action, policy revision và context quan trọng.
28. **Tại sao một JWT có aud hợp lệ chưa đủ?** Còn scope, grant state, user/tenant/resource entitlement và device/session policy.

### Bài tập tổng hợp

Một công ty có **public web CRM**, ứng dụng **Production Admin** qua ZTNA, **SSH/RDP** cho nhóm SRE, các microservices chạy trên Kubernetes, API dùng **OAuth JWT access tokens** và nhân viên từ mạng gia đình/VPN. MDM/EDR phát posture alerts, IdP phát account revocation; hệ thống có **hai regions**, IPv4/IPv6 và service mesh.

Hãy thực hiện:

1. Vẽ **data flow** từ user/device → PEP → app, cùng IdP/MDM/EDR → PDP → enforcement.
2. Phân loại **tài nguyên/hành động** CRM view, CRM export, Prod policy edit và SSH admin; xác định entitlement.
3. Chọn **tín hiệu cần thiết**, nguồn tin, TTL/freshness và false positive risk cho mỗi action.
4. Thiết kế **policy decisions ALLOW/STEP_UP/RESTRICT/QUARANTINE/REVOKE/DENY** với hard-deny precedence.
5. Định nghĩa **event sequence** cho compromised device mid-session và cách chặn WebSocket/gRPC/SSH active.
6. Vạch **revocation path** tới API resource server đang dùng JWT còn hạn và các điều kiện token refresh.
7. Thiết kế **failure policy** khi MDM, IdP, PDP và network mất khả dụng, riêng theo sensitivity.
8. Xác định **direct-origin/IPv6/DR/VPN bypass** và network segmentation cần thiết.
9. Thiết kế **workload trust re-evaluation** cho ServiceAccount/mTLS identity khi runtime alert xuất hiện.
10. Lập dashboard **signal lag, decision, propagation, active session disconnection, false positives, security violations, business SLI**.
11. Viết ít nhất **15 test ALLOW/DENY** có step-up, revoke, stale posture, multi-region, token cache và regrant.
12. Viết **incident/runbook**, chỉ rõ ai phê duyệt cách ly và cách phục hồi không tái cấp quyền đã thu hồi.

**Tiêu chí chấm:** Một kiến trúc tốt không chỉ có **một sơ đồ kiểm tra tại login**, mà còn mô tả **tín hiệu thay đổi lúc nào, ai quyết định, PEP/resource nào thật sự chặn, độ trễ bao nhiêu và cách phục hồi sau đánh giá lại**; chứng minh **truy cập hợp lệ hoạt động và đường trái quyền bị DENY**.

## 30. Checklist triển khai và kiểm tra continuous verification

- [ ] Đã xác định **subject/user/workload, device, session, resource và action** riêng biệt?
- [ ] Mỗi tài nguyên có **sensitivity classification, entitlement owner và permission scope**?
- [ ] Có policy rõ **verify explicitly, least privilege, assume breach** ở những trust boundaries cần thiết?
- [ ] Biết PDP/Policy Engine, Policy Administrator và **mọi PEP thực sự trên request path**?
- [ ] Đã kiểm tra đường **direct origin, alternate hostname, private IP, IPv4/IPv6 và DR region**?
- [ ] Đã inventory **IdP, MDM, EDR, risk signals, IAM/JIT, app authorization và network logs**?
- [ ] Nguồn tín hiệu được **authentication/integrity/anti-replay**, có ID/sequence/schema version?
- [ ] **Event time, received time, freshness TTL, clock skew và out-of-order** được xử lý?
- [ ] Phân biệt **compliant, noncompliant, stale, unknown, sensor unavailable và compromised**?
- [ ] Hard deny như **account disabled, revoked session, missing entitlement** được ưu tiên?
- [ ] Chính sách **ALLOW, STEP_UP, RESTRICT, QUARANTINE, REVOKE, DENY** có nghĩa vận hành rõ?
- [ ] MFA step-up chỉ yêu cầu khi cần, tránh **MFA fatigue** và không tự tạo entitlement?
- [ ] Có ràng buộc **fresh phishing-resistant auth** cho hành động Prod nhạy cảm theo policy?
- [ ] JIT/JEA grants có owner, scope, expiry và **không tự khôi phục sau revoke**?
- [ ] Posture/device signals không bị tin chỉ vì IP nội bộ, tên host hoặc client headers tự khai?
- [ ] Đã xét privacy/consent/retention cho thiết bị BYOD và device telemetry?
- [ ] Decision cache key có **resource/action/session/device/policy revision**, không chỉ user ID?
- [ ] Decision TTL, token TTL, posture TTL và session lifetime được **phân biệt và kiểm thử**?
- [ ] Có **event-driven invalidation** cho cached grants, đồng thời periodic recheck khi event mất?
- [ ] API dùng JWT/opaque tokens có **resource-side revoke/introspection/session check** phù hợp?
- [ ] Không giả định logout/refresh revoke làm mọi access token đã cấp hết hiệu lực ngay?
- [ ] Existing **SSH/RDP/WebSocket/gRPC/TCP sessions** có disconnect/recheck plan rõ?
- [ ] App tiếp tục kiểm tra **user/tenant/object-level authorization** ở các action nhạy cảm?
- [ ] mTLS/ServiceAccount/workload identities được giới hạn scope và kiểm tra peer authZ ở service mesh?
- [ ] ZTNA/VPN/cloud network vẫn có **firewall/NetworkPolicy/segmentation** chống lateral movement?
- [ ] Có **risk-score quality, false positive review, hysteresis và confidence categories**?
- [ ] Sensor/PDP/PEP/IdP unavailable có **failure policy theo data sensitivity**, không wildcard allow?
- [ ] Có break-glass **time-boxed, strong auth, owner/approver và full audit**?
- [ ] Control-plane policy changes đã **readback effective PEP policy** ở mọi regions?
- [ ] Theo dõi **event lag, policy propagation, cache staleness, PEP ACK và enforcement latency**?
- [ ] Có kiểm thử **new requests, active sessions, token reuse và resource backend rejection** sau revoke?
- [ ] Có test **ALLOW hợp lệ và DENY sai identity/device/resource/action** khi policy cập nhật?
- [ ] Logs chứa **policy ID/revision, principal pseudonym, source type và UTC**, không chứa raw tokens/PII không cần?
- [ ] Có thủ tục bảo toàn evidence, incident coordination, user remediation và safe rollback?
- [ ] Có kế hoạch sau remediation: **device trust mới + entitlement recheck + new authentication** phù hợp?
- [ ] Đã kiểm tra **false-positive impact, availability/business SLO và emergency-revocation security SLO**?

**Kết luận:** **Continuous verification trong ZTNA** là khả năng **đánh giá và thực thi lại điều kiện truy cập khi danh tính, thiết bị, phiên, quyền và rủi ro thay đổi**, không phải một lời hứa rằng mọi packet đều được kiểm tra bằng MFA. Một thiết kế thành công cần xác định **nguồn tín hiệu đáng tin, thời hạn hiệu lực, policy theo resource/action, PDP/PEP có khả năng chặn thật, cơ chế thu hồi token/phiên dài và độ trễ hội tụ giữa các hệ thống**. Mức tin cậy giảm phải dẫn tới **STEP_UP, RESTRICT, QUARANTINE hoặc REVOKE/DENY theo rủi ro**, còn khi điều kiện được khôi phục chỉ cấp lại **quyền vẫn hợp lệ**. Chỉ khi chứng minh được **truy cập hợp lệ tiếp tục hoạt động, quyền trái phép bị chặn ở mọi đường và quyết định thay đổi có hiệu lực trong thời gian kiểm soát**, continuous verification mới thực sự góp phần bảo vệ mạng theo zero trust.
