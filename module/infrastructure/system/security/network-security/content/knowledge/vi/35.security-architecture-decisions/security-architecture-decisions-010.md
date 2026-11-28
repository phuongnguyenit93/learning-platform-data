# Khi nào cần custom network control

## 1. Vấn đề cốt lõi: có nên tự xây một lớp kiểm soát mạng?

**Custom network control** là một cơ chế kiểm soát lưu lượng, quyền kết nối hoặc chính sách mạng được **thiết kế hay mở rộng riêng** để giải quyết yêu cầu mà các tính năng sẵn có không đáp ứng đầy đủ. Nó có thể đơn giản như một bộ điều khiển cập nhật chính sách từ danh mục workload đáng tin cậy, hoặc phức tạp như một plugin gateway, một policy decision service hay một thành phần thực thi trong data plane.

Trong chương **Quyết định kiến trúc bảo mật mạng** của mô-đun **SECURITY_NETWORK_SECURITY**, câu hỏi không chỉ là "có viết được code không?", mà là:

> **Rủi ro nào chưa được một kiểm soát đã được hỗ trợ đáp ứng, tại trust boundary nào, và liệu giá trị của việc tùy biến có lớn hơn toàn bộ chi phí, lỗi tiềm ẩn và nghĩa vụ vận hành mà nó tạo ra không?**

Chẳng hạn, một firewall đã hỗ trợ giới hạn kết nối theo subnet và port. Nếu yêu cầu là "vùng GUEST không được truy cập database", rất có thể chỉ cần chính sách phân đoạn chuẩn. Nhưng nếu yêu cầu là "chỉ workload đang có danh tính dịch vụ được xác minh, với quyền nghiệp vụ còn hiệu lực, mới được gọi một API nhạy cảm; chính sách thay đổi theo trạng thái giao dịch", một ACL L3/L4 có thể không đủ. Khi đó cần đánh giá **authorization tại ứng dụng/API gateway**, policy engine, service identity, hoặc mở rộng tính năng chuẩn trước khi quyết định viết một thành phần tùy biến.

**Kết luận định hướng:** *mặc định dùng cơ chế chuẩn, được hỗ trợ và có thể kiểm chứng*. Chỉ custom khi có khoảng trống được chứng minh, có phương án triển khai an toàn và tổ chức đủ năng lực sở hữu nó lâu dài.

### Mục tiêu học tập

- Phân biệt cấu hình đặc thù, policy-as-code, extension/plugin và tự xây một enforcement component.
- Xác định những tiêu chí cho thấy nên hoặc **không nên** custom.
- Phân tích trust boundary, vị trí thực thi, identity, data/control/management plane và đường dự phòng.
- Đánh giá bảo mật, hiệu năng, khả dụng, tính quan sát, phụ thuộc và chi phí vòng đời.
- Thiết kế acceptance test, canary, rollback, xử lý thất bại và quy trình quản trị thay đổi.
- Viết quyết định kiến trúc (ADR) có lý do, phương án thay thế và điều kiện xem xét lại.

## 2. Phân biệt "custom" ở các mức độ khác nhau

Không phải mọi policy riêng của doanh nghiệp đều là **custom network control** theo nghĩa cần phát triển phần mềm mới.

| Mức độ | Cách làm | Ví dụ | Gánh nặng vận hành |
| --- | --- | --- | --- |
| **0 — Cấu hình chuẩn** | Dùng khả năng nhà cung cấp hỗ trợ | Firewall ACL, security group, NetworkPolicy, VPN policy | Thấp hơn nếu policy đơn giản và có quản trị tốt |
| **1 — Policy-as-code** | Sinh, review và triển khai cấu hình chuẩn từ dữ liệu đáng tin | Terraform/IaC, GitOps, rule templates, kiểm thử cấu hình | Có logic tự động hóa nhưng vẫn dùng data plane được hỗ trợ |
| **2 — Tích hợp với policy/identity có sẵn** | Dùng API/hook/authorization service được hỗ trợ | Gateway gọi external authorization, NAC lấy nhóm thiết bị từ IdP | Cần quản lý latency, availability, cache và version |
| **3 — Plugin hoặc extension** | Viết module trong điểm thực thi có giao diện hỗ trợ | Proxy filter, WAF rule extension, service-mesh policy extension | Cần kiểm soát tương thích, cô lập lỗi và quy trình release |
| **4 — Custom controller/orchestrator** | Tạo và phân phối policy đến các PEP chuẩn | Controller tổng hợp asset identity rồi cập nhật rule qua API | Có nguy cơ sai logic phân phối và cấp quá quyền |
| **5 — Tự xây enforcement/data plane** | Tự viết proxy, packet filter, eBPF program hoặc gateway riêng | Lọc packet hoặc thực thi stateful policy tùy biến | Cao nhất: correctness, throughput, bypass, kernel/runtime, HA |

Mức càng cao càng đòi hỏi nhiều kỹ thuật kiểm chứng, đặc biệt với **parser mạng, connection state, concurrency, memory safety, policy conflicts, protocol changes và failover**. Không nên nhảy từ yêu cầu hơi khác chuẩn lên tự viết firewall hoặc proxy mới.

### 2.1. Ba đối tượng thường bị nhầm lẫn

1. **Custom policy:** quy tắc riêng chạy trên engine đã có; không thay cơ chế xử lý packet.
2. **Custom policy controller:** phần mềm quyết định và phân phối quy tắc, nhưng enforcement vẫn do firewall/gateway/CNI chuẩn đảm nhận.
3. **Custom enforcement:** phần mềm trực tiếp cho phép, từ chối, định tuyến hoặc biến đổi traffic. Đây là phạm vi cần đánh giá an toàn và vận hành nghiêm ngặt nhất.

Ví dụ một controller đồng bộ danh mục máy được cấp quyền thành security group có thể là giải pháp tùy biến **control plane**, trong khi cơ chế lọc traffic vẫn là **cloud security group**. Nó không tương đương việc tự viết packet filter trong kernel.

## 3. Trước khi chọn công cụ, xác định trust boundary và yêu cầu

Giả sử kiến trúc gồm các vùng:

~~~mermaid
flowchart LR
    E[Internet / người dùng] --> G[WAF / API gateway]
    G --> A[Order service]
    A --> P[Payment service]
    P --> D[(Payment database)]
    C[Contractor VPN] --> F[Firewall phân đoạn]
    F --> A
    I[IdP / Workload identity] -. Cấp danh tính .-> G
    I -. Cấp danh tính .-> A
    I -. Cấp danh tính .-> P
    M[Management plane] -. Quản lý policy .-> G
    M -. Quản lý policy .-> F
~~~

Các boundary cần mô tả trước khi quyết định custom:

| Ranh giới | Câu hỏi | Kiểm soát gốc nên xem xét |
| --- | --- | --- |
| Internet → Gateway | Ai gọi API, cần chặn loại request nào? | TLS, identity, WAF/gateway policy, rate limit |
| Gateway → Application | Header/identity nào được tin, có thể bypass gateway không? | Backend auth, network allowlist, mTLS, trusted proxy |
| Order → Payment | Workload nào được gọi hành động nào? | mTLS/workload identity và application authorization |
| Payment → Database | Chỉ service nào có quyền đọc/ghi bảng dữ liệu nào? | Network segmentation và DB least privilege |
| Contractor → APP | Người dùng VPN được vào subnet và port nào? | Identity-aware access, ACL, device posture |
| Operator → Management | Ai được sửa rule, secret hoặc certificate? | PAM, MFA, scoped IAM, audit, approval |

**Nếu yêu cầu có thể biểu đạt đủ bằng các điểm kiểm soát đã có, chưa có căn cứ để custom.** Ngược lại, nếu đang có một khoảng trống như policy theo quyền nghiệp vụ mà firewall L3/L4 không thể hiểu, hãy đặt enforcement đúng tại API/application hoặc một gateway có khả năng đọc và xác minh ngữ cảnh đó.

### 3.1. Cần xác định đúng loại quyết định

- **L3/L4 reachability:** có được mở kết nối giữa zone/IP/port không?
- **Identity-based access:** người dùng, workload hay thiết bị nào được gọi?
- **L7 action authorization:** được gọi route/method và thao tác trên đối tượng nào?
- **Content inspection:** request hoặc dữ liệu nào cần được phát hiện/giới hạn?
- **Egress/data boundary:** dữ liệu nào được phép đi tới external service?
- **Availability policy:** giới hạn tải, quota hoặc chống lạm dụng ở lớp nào?

Một policy cho phép TCP/443 không thể thay thế quyết định một user có được xem hóa đơn của người khác hay không. **Custom L3 firewall không giải quyết được lỗ hổng authorization ở tầng ứng dụng.**

## 4. Những điều kiện có thể biện minh cho custom network control

Custom là lựa chọn đáng cân nhắc khi **nhiều điều kiện sau cùng đúng**, không chỉ vì một yêu cầu thuận tiện:

| Điều kiện | Bằng chứng nên có | Ví dụ phù hợp |
| --- | --- | --- |
| **Capability gap thật** | Đã khảo sát tính năng chuẩn, API và plugin hiện có; có thử nghiệm chứng minh thiếu | Engine chỉ kiểm soát IP trong khi yêu cầu policy theo workload identity đã xác minh |
| **Rủi ro quan trọng** | Có threat model, tài sản nghiệp vụ và tác động nếu không kiểm soát | Kết nối tới hệ thống thanh toán có yêu cầu chi tiết hơn policy mặc định |
| **Ngữ cảnh tại boundary đặc thù** | Nêu rõ PEP cần dữ liệu gì và nguồn dữ liệu có tin cậy không | Rule theo mTLS principal cùng trạng thái quyền do IdP cung cấp |
| **Không thể giải quyết ở lớp phù hợp bằng cấu hình** | Đã kiểm tra ứng dụng, IAM, gateway, firewall, CNI và chính sách hỗ trợ | Luồng độc quyền của thiết bị không hỗ trợ policy cần thiết |
| **Yêu cầu tuân thủ/kiểm toán rõ** | Đối chiếu kiểm soát với nghĩa vụ và test acceptance | Cần audit và deny theo thuộc tính đã xác minh |
| **Tổ chức đủ năng lực xây và vận hành** | Có owner, reviewers, CI/CD, on-call, support/rollback | Đội platform chịu trách nhiệm 24/7 cho policy service |
| **Có thể thử nghiệm an toàn** | Lab, staging, canary, traffic replay, fault injection và dữ liệu đại diện | Test quyền và mạng trước khi production |
| **Lợi ích dài hạn có thể đo** | So tổng chi phí, rủi ro còn lại, thời gian đáp ứng và cải tiến | Một controller thay cấu hình thủ công dễ lỗi trên nhiều account |

**Ví dụ hợp lý:** một doanh nghiệp quản lý hàng nghìn workload ngắn hạn, có inventory được xác minh và cần sinh policy egress theo danh tính dịch vụ. Có thể xây controller cập nhật policy qua API nhà cung cấp, **nếu** engine chuẩn không cung cấp một cơ chế identity-based tương đương đáp ứng yêu cầu. Cần quản lý độ trễ cập nhật, lỗi đồng bộ và quyền của controller.

**Ví dụ không hợp lý:** tự viết packet filter để chỉ chặn inbound TCP/22 từ mạng GUEST trong khi firewall hiện tại đã có ACL hỗ trợ và kiểm thử được.

## 5. Những trường hợp nên tránh tự phát triển

| Dấu hiệu | Vì sao là cảnh báo |
| --- | --- |
| “Chỉ cần thêm tính năng cho nhanh” nhưng không có threat model | Không biết rủi ro mới do code gây ra có lớn hơn lợi ích không |
| Cơ chế chuẩn đã đáp ứng tốt | Tạo trùng lặp và thêm hệ thống phải vá/giám sát |
| Muốn bỏ qua xác thực hoặc giám sát vì performance | Đánh đổi bảo mật cốt lõi để tối ưu một triệu chứng |
| Không có người trực/owner sau phát hành | Lỗi data plane hoặc chứng chỉ hết hạn không có ai chịu trách nhiệm |
| Không thể thử failure modes | Dễ gây outage diện rộng khi policy service/KMS/IdP mất |
| Không xác định rõ traffic đi qua điểm thực thi | Có thể tạo security theater, traffic khác bypass control |
| Chỉ hỗ trợ IPv4/TCP trong khi hệ thống có IPv6, UDP/QUIC hoặc tunnel | Tạo một đường bypass kiến trúc |
| Phụ thuộc API/private hook không được hỗ trợ | Nâng cấp vendor có thể phá hoạt động bất ngờ |
| Cần xử lý dữ liệu rất nhạy cảm mà chưa có mô hình privacy/key management | Control mới có thể thành nơi tập trung credential và payload |
| Không có phương án migrate/rollback | Dễ bị khóa vào công nghệ nội bộ hoặc làm gián đoạn khôi phục |

Chính sách “tất cả traffic đi qua một proxy do đội tự viết” thường đáng nghi nếu proxy thiếu HA, quan sát, kiểm thử TLS, protocol handling, capacity và xử lý incident. Có thể dùng gateway đã được hỗ trợ, chỉ mở rộng tại **hook cần thiết**, thay vì viết lại toàn bộ kết nối.

## 6. Cây quyết định: từ yêu cầu đến cách thực thi

~~~mermaid
flowchart TD
    A[Viết rõ trust boundary và policy cần bảo vệ] --> B{Có cơ chế chuẩn hỗ trợ?}
    B -->|Có| C[Dùng cấu hình chuẩn / IaC và test]
    B -->|Không hoặc chưa đủ| D{Có kiểm soát ở lớp khác phù hợp hơn?}
    D -->|Có| E[Chuyển enforcement đến ứng dụng, IAM hoặc gateway]
    D -->|Không| F{Có API/extension được hỗ trợ?}
    F -->|Có| G[Tích hợp hoặc viết plugin nhỏ]
    F -->|Không| H{Rủi ro quan trọng và tổ chức đủ năng lực?}
    H -->|Không| I[Đổi thiết kế / nâng cấp sản phẩm / chấp nhận rủi ro có phê duyệt]
    H -->|Có| J[Đánh giá custom controller hoặc enforcement]
    J --> K{Có test, observability, HA và rollback?}
    K -->|Không| I
    K -->|Có| L[PoC cô lập, review và ADR trước production]
    C --> M[Đo hiệu quả và rà soát lại]
    E --> M
    G --> M
    L --> M
~~~

Sơ đồ là hướng dẫn ra quyết định, không phải thuật toán tự động. Có trường hợp doanh nghiệp phải thay đổi yêu cầu hoặc chọn sản phẩm khác vì **custom quá rủi ro**; đây là kết quả kiến trúc hợp lệ.

## 7. Phân biệt policy decision với policy enforcement

Một custom control nên làm rõ ba vai trò:

1. **Policy administration point (PAP):** nơi định nghĩa, review, phê duyệt và xuất bản chính sách.
2. **Policy decision point (PDP):** nơi đánh giá dữ kiện và quyết định allow/deny/limit theo policy.
3. **Policy enforcement point (PEP):** nơi thực thi quyết định trên request/flow.

~~~mermaid
flowchart LR
    O[Owner / GitOps / Approval] --> PAP[Policy administration]
    PAP -->|Versioned policy| PDP[Policy decision service]
    ID[Identity / Inventory] -->|Trusted context| PDP
    S[Client / Workload] --> PEP[Gateway / Firewall / CNI]
    PEP -->|Decision request| PDP
    PDP -->|Allow / Deny + TTL| PEP
    PEP --> D[Đích được bảo vệ]
    PEP -. Decision audit .-> L[SIEM / Logs]
    PDP -. Policy + reason audit .-> L
~~~

**Vấn đề phải trả lời:**

- PEP biết được **danh tính đáng tin** từ đâu? IP do caller tự khai hay thông tin đã được xác thực bằng mTLS/token/sidecar?
- PDP có đủ dữ kiện để ra quyết định hay cần quyền truy cập tới dữ liệu nhạy cảm khác?
- Policy nào được cache, trong bao lâu, và cache có bị stale khi thu hồi quyền không?
- Ai có quyền đổi policy, source-of-truth và cách phân phối version là gì?
- Nếu PDP, IdP, mạng quản trị hoặc đồng hồ gặp lỗi, PEP hành xử thế nào?
- Có cách bypass PEP bằng direct-to-origin, alternate route, IPv6, internal service VIP hay failover không?

**Không tin những header do client tự gửi** như identity khi proxy chưa xác thực và chuẩn hóa chúng. Nếu quyền truy cập phụ thuộc principal, bảo đảm đó là principal được xác minh tại enforcement point, không chỉ string xuất hiện trong request.

### 7.1. Đặt việc ra quyết định vào đúng lớp

Một firewall packet-level có thể nhìn IP/port, không mặc định nhìn thấy user, HTTP method hoặc token trong TLS. Một gateway giải mã HTTPS có thể nhìn request nhưng không có quyền định tuyến L3 trên toàn VPC. Một application có thể biết transaction owner nhưng không quan sát tất cả traffic không đi qua nó. **Không thiết kế policy dựa trên dữ liệu mà PEP thực tế không thể chứng minh.**

## 8. Lựa chọn chỗ đặt custom control

| Vị trí | Phù hợp cho | Giới hạn và nguy cơ |
| --- | --- | --- |
| Firewall/ACL engine có plugin | L3/L4 reachability, NAT, một số policy stateful | Khó diễn giải nội dung ứng dụng mã hóa, compatibility với appliance |
| Gateway / reverse proxy | HTTP route, request rate, token validation, external authz | Chỉ thấy traffic qua gateway; bypass direct origin |
| Service mesh / sidecar | Workload identity, service-to-service policy | Sidecar coverage, certificate lifecycle, ambient/dataplane semantics |
| CNI/eBPF/network policy | Pod/workload reachability, network identity ở một số nền tảng | Kernel/CNI compatibility, statefulness, verifier/runtime và debugging |
| Application authorization | Permission theo đối tượng/đơn hàng, business action | Không thay được chặn traffic ngoài ứng dụng |
| Cloud IAM/policy automation | Resource/config permissions và cập nhật policy theo inventory | Control plane lạm quyền, eventual consistency, IAM blast radius |
| Egress proxy / DNS policy | Hạn chế đích ra ngoài, protocol-aware outbound khi phù hợp | Domain/IP biến đổi, DoH/DoT, TLS, bypass bằng đường khác |
| NAC / Wi-Fi controller | Onboarding thiết bị, role/zone theo identity | Không thay thế per-request authz hoặc microsegmentation |

Ở một số môi trường, **native feature đã bao phủ đúng điểm thực thi**; viết plugin mới chỉ làm tăng sự phức tạp. Ở môi trường khác, cùng một policy cần nhiều PEP (edge gateway và CNI), khi đó phải bảo đảm version, semantics và quyền thực thi nhất quán.

### 8.1. Không bỏ quên đường đi và đường về

Request có thể qua CDN/WAF rồi đến reverse proxy, service mesh và backend; mỗi chặng có TLS/TCP session riêng. Return path có thể khác do ECMP, policy routing, NAT hoặc VPN failover. Một control stateful ở một interface có thể **không thấy cả hai chiều**. Thiết kế kiểm soát phải mô hình hóa:

~~~text
Nguồn → [Boundary/PEP A] → NAT/VPN → [PEP B] → Proxy → Dịch vụ
Nguồn ← [Return PEP ? ] ← NAT/VPN ← [Return path] ← Dịch vụ
~~~

Một cơ chế áp rule ở edge chưa chắc bảo vệ kết nối nội bộ giữa các pod hoặc đường direct-to-origin. Kiểm tra route, bypass và những điểm kết thúc TLS trước khi tuyên bố control bao phủ toàn bộ luồng.

## 9. Threat modeling riêng cho custom control

Viết một kiểm soát mới nghĩa là tổ chức đồng thời đưa thêm **một thành phần được tin cậy** và **một bề mặt tấn công** vào kiến trúc.

| Nhóm rủi ro | Tình huống | Biện pháp cần thiết |
| --- | --- | --- |
| **Identity spoofing** | Caller tự gửi header nói mình là admin | PEP lấy principal từ xác thực tin cậy, loại header không tin |
| **Authorization bypass** | Rule dùng match quá rộng, thiếu deny cuối | Test negative cases, least privilege, deny semantics |
| **Parser/protocol ambiguity** | Proxy và backend diễn giải request khác nhau | Dùng parser được hỗ trợ, kiểm tra normalization/canonicalization |
| **Policy conflict** | Nhiều rule chồng lấn, precedence không rõ | Định nghĩa thứ tự/semantics, static checks, review |
| **Policy tampering** | Controller hoặc CI/CD có quyền sửa policy không kiểm soát | Signed/approved policy, RBAC, audit, separation of duties |
| **Stale identity/cache** | Quyền đã thu hồi nhưng quyết định allow còn hiệu lực | TTL, invalidation, revocation test, explicit expiry |
| **DoS/resource exhaustion** | Mỗi request gọi PDP chậm hoặc log quá nhiều | Cache đúng chỗ, quota, backpressure, bounded resource |
| **Availability failure** | PDP/IdP/KMS down, PEP bị kẹt | Documented fail mode, HA, circuit breaker, recovery drill |
| **Protocol bypass** | Control chỉ kiểm tra IPv4/TCP, bỏ UDP/QUIC hoặc IPv6 | Coverage matrix và default policy ở đường không hỗ trợ |
| **Observability gap** | Không biết rule nào cho phép/deny | Decision ID, policy version, principal, reason code |
| **Sensitive data leakage** | PDP/log lưu token, payload, địa chỉ nội bộ | Data minimization, redact, encryption, retention |
| **Update/rollback errors** | Partial rollout tạo policy khác nhau giữa nodes | Version pin, canary, staged rollout, consistency checks |
| **Supply chain risk** | Plugin/dependency bị xâm nhập | SBOM, dependency review, signed artifacts, update process |

Không nên viết data-plane code nếu đội không đủ năng lực kiểm soát **memory/resource safety, concurrency, malformed traffic và failover**. Lỗ hổng trong custom firewall/proxy có thể tạo rủi ro lớn hơn lỗ hổng mà nó được xây để chặn.

## 10. Yêu cầu kỹ thuật tối thiểu cho thiết kế

Trước khi phát triển, tạo một đặc tả có thể kiểm thử:

### 10.1. Functional requirements

- **Decision inputs:** nguồn dữ liệu danh tính, tài sản, zone, resource và context.
- **Decision outputs:** allow/deny/limit và reason code; nếu có route/transform phải ghi rõ.
- **Policy semantics:** default, precedence, expiry, override, conflict và exception.
- **Scope:** IPv4/IPv6, TCP/UDP, TLS/QUIC, east-west/north-south, management traffic.
- **Identity verification:** client principal, workload identity, token/cert validation và replay handling nếu phù hợp.
- **Bypass protection:** không có đường truy cập không qua PEP hoặc có PEP tương đương.
- **Audit:** mỗi quyết định nhạy cảm phải có reference truy vết và policy version.

### 10.2. Non-functional requirements

| Thuộc tính | Câu hỏi bắt buộc |
| --- | --- |
| Latency | Cho phép thêm bao nhiêu p95/p99 ở request path? |
| Throughput | Bao nhiêu request/giây, flow/giây, packet/giây và concurrent sessions? |
| Availability | SLA/SLO, behavior khi dependency hỏng, HA/failover ra sao? |
| Scalability | Khi workload tăng gấp nhiều lần, PEP/PDP có scale phù hợp không? |
| Security | Ai được thay policy, đọc log, giải mã traffic, cấp token? |
| Correctness | Policy mới/tổ hợp rule được kiểm thử bằng những case nào? |
| Rollback | Có quay lại bản chính sách trước nhanh và an toàn không? |
| Upgrade | Plugin có tương thích vendor/CNI/kernel/mesh version mới không? |
| Maintainability | Có owner/on-call, runbook, observability, dependency lifecycle không? |
| Compliance/privacy | Thu dữ liệu nào, retention, masking và audit thế nào? |

Đặt **ngân sách latency và resource** dựa trên baseline thực tế, không đoán. Ví dụ quyết định external authz phải có timeout rõ: nếu đợi vô hạn sẽ làm nghẽn request path; nếu cache quá lâu có thể bỏ qua thu hồi quyền.

## 11. Một ví dụ policy tùy biến nhưng không tự viết firewall

Giả sử doanh nghiệp muốn chỉ cho phép **workload có identity hợp lệ và trạng thái cấp quyền còn hạn** gọi một service thanh toán. Firewall L3/L4 không biết quyền nghiệp vụ, nhưng gateway hiện tại hỗ trợ external authorization.

Thiết kế có thể:

1. Ở **network boundary**, security group hoặc NetworkPolicy chỉ cho phép gateway → payment-service.
2. Ở **identity boundary**, gateway xác thực mTLS principal hoặc token theo nguồn tin cậy.
3. Ở **application boundary**, external authz service kiểm tra quyền gọi hành động dựa trên subject/resource/action.
4. Payment-service **vẫn** xác minh authorization theo logic nghiệp vụ cần thiết, không tin một header tự khai.
5. Decisions được ghi theo request ID, policy version và reason code.

Ví dụ định dạng policy **khái niệm, không phải cấu hình của một nhà cung cấp cụ thể**:

~~~yaml
policy_id: payment-api-authorize-v1
boundary: gateway-to-payment
default_effect: deny
rules:
  - effect: allow
    subject:
      workload_identity: order-service
    resource:
      api: payment-service
      action: create-payment-intent
    conditions:
      token_audience: payment-service
      authorization_status: active
      authorization_max_age_seconds: 60
audit:
  include:
    - request_id
    - verified_principal
    - policy_version
    - decision
    - reason_code
  exclude:
    - raw_access_token
    - sensitive_payload
~~~

**Điểm quan trọng:** ví dụ chỉ mô tả yêu cầu. Để triển khai thật phải xác định schema do PDP hỗ trợ, phương thức xác thực principal, cách xác minh trạng thái authorization, đồng hồ đáng tin, timeout, cache và điểm enforcement. Nếu **authorization_status** do client tự gửi mà gateway không kiểm chứng, rule này **không bảo vệ được gì**.

### 11.1. Vì sao không dùng một IP allowlist thay thế?

Workload có thể thay pod/instance/IP trong quá trình autoscaling; nhiều workload có thể dùng chung NAT hoặc gateway. IP allowlist hữu ích để **giảm reachability**, nhưng không thay thế chứng thực danh tính và quyền thực hiện một hành động nghiệp vụ. Một thiết kế đúng thường kết hợp network policy chuẩn với authentication/authorization ở tầng thích hợp.

## 12. Policy lifecycle: không chỉ viết rule, mà còn quản trị thay đổi

Một custom control phải có vòng đời từ yêu cầu đến hết hạn:

~~~mermaid
flowchart TD
    A[Business owner khai báo yêu cầu] --> B[Threat model + policy spec]
    B --> C[Review bởi security và service owner]
    C --> D[Static validation và unit tests]
    D --> E[Integration test với PEP/PDP thật]
    E --> F[Canary + monitoring + stop conditions]
    F --> G{Đạt acceptance và không tác động bất thường?}
    G -->|Không| H[Rollback và điều tra]
    G -->|Có| I[Rollout có kiểm soát]
    I --> J[Observability, drift detection, recertification]
    J --> K[Thay đổi / thu hồi / hết hạn exception]
    K --> B
~~~

### 12.1. Source of truth và policy delivery

Quy tắc nên có **version**, owner, mục đích, ngày review và link đến change/ADR. Nếu phân phối policy qua API tới firewall, cloud security group hoặc mesh, phải kiểm chứng **desired state** khớp **effective state**. Không cho rằng Git commit thành công nghĩa là tất cả PEP đã nhận và áp chính sách.

Cần kiểm tra version skew, eventual consistency, cache stale và một số node còn bản cũ. Với policy bảo vệ dữ liệu nhạy cảm, cân nhắc giữ quyền truy cập tối thiểu khi không thể chứng minh phiên bản policy an toàn đang hoạt động.

### 12.2. Exception có thời hạn

Một ngoại lệ tạm thời như “cho phép service X gọi endpoint Y trong lúc migration” phải có:

- Owner chịu trách nhiệm.
- Lý do nghiệp vụ, nguồn/đích/chức năng chính xác.
- Mốc hết hạn và điều kiện tự thu hồi hoặc review.
- Bằng chứng phê duyệt và theo dõi usage.
- Kết quả kiểm chứng sau khi gỡ exception.

Không dùng “any-to-any trong một tuần” để giải quyết thiếu inventory, vì cách này dễ trở thành policy thường trực ngoài ý muốn.

## 13. Fail-open, fail-closed và đường phục hồi

Khi custom policy service hoặc dependency bị lỗi, phải có hành vi **được quyết định trước**, khác nhau theo loại luồng và mức rủi ro.

| Boundary | Ví dụ khi PDP không phản hồi | Hành vi cần cân nhắc |
| --- | --- | --- |
| Giao dịch tài chính nhạy cảm | Authorization không xác minh được | Thường từ chối hành động nhạy cảm, có cơ chế xử lý nghiệp vụ lỗi |
| Public static content | Rate-limit decision chậm | Có thể phục vụ từ cache/giới hạn an toàn tùy yêu cầu |
| Quản trị đặc quyền | PAM/IdP không khả dụng | Không mở quyền tự do; dùng break-glass có kiểm soát, audit và review |
| Telemetry-only detection | Sensor/SIEM mất kết nối | Không nhất thiết chặn traffic; cảnh báo mất khả năng quan sát |
| Emergency connectivity | Control lỗi khi đang ứng cứu | Đường quản trị tách biệt, giới hạn và có quy trình phê duyệt |

**Fail-closed** có thể tăng bảo vệ dữ liệu nhưng làm giảm availability; **fail-open** duy trì dịch vụ nhưng có thể bỏ qua kiểm soát. Không dùng một chính sách fail mode chung cho mọi route, mọi service và mọi dữ liệu.

### 13.1. Các bài test thất bại cần thực hiện

- PDP timeout hoặc trả HTTP lỗi.
- IdP/KMS/certificate service mất kết nối, certificate hết hạn.
- Policy repository có version sai, một node chưa nhận bản mới.
- DNS thay đổi, route/VPN failover, network partition.
- PEP restart giữa các connection đang mở.
- Cache có quyết định allow đã hết hiệu lực.
- Log collector unavailable nhưng PEP vẫn đang quyết định.
- Rollback trong lúc traffic tăng cao.

Kiểm tra riêng **người dùng hợp lệ**, **request không được phép**, **request không rõ danh tính**, và tác động lên hệ thống lân cận. Không diễn tập phá vỡ production ngoài phạm vi được phê duyệt.

## 14. Kiểm thử correctness, bảo mật, hiệu năng và resilience

| Loại kiểm thử | Câu hỏi xác minh | Ví dụ acceptance |
| --- | --- | --- |
| **Policy unit test** | Rule allow/deny/conflict hoạt động theo specification? | Principal không thuộc allowlist luôn bị deny |
| **Identity test** | Không thể dùng header/token tự khai để lấy quyền? | Spoofed identity không được chấp nhận |
| **Boundary bypass test** | Có đường network/host/IPv6/alternate route ngoài PEP? | Không có direct access được phép tới protected origin |
| **State/revocation test** | Thu hồi quyền có hiệu lực trong giới hạn định trước? | Cached allow hết hạn và không tự động gia hạn |
| **Protocol compatibility** | TCP, UDP, IPv6, HTTP/2, QUIC, TLS được xử lý đúng? | Chỉ giao thức hỗ trợ mới có đường được phê duyệt |
| **Input robustness** | Dữ liệu thiếu/malformed xử lý như thế nào? | Không crash, không cho phép mặc định |
| **Performance** | p95/p99 latency và throughput đạt SLO? | Theo baseline dưới tải đại diện |
| **Load and soak** | Memory/session state có ổn định trong thời gian dài? | Không tăng memory vô hạn, có backpressure |
| **Failure injection** | Khi PDP, IdP, KMS down, fail mode đúng? | Không tạo bypass và hành vi đã tài liệu hóa |
| **HA/failover** | Khi một PEP/node lỗi, chính sách còn nhất quán? | Failover không làm mở đường không phép |
| **Policy rollout** | Canary và rollback có hoạt động? | Tác động ngoài dự kiến bị phát hiện và đảo phiên |
| **Observability** | Có thể truy ra decision cùng policy version? | Audit đủ reason code, không lộ token |
| **Upgrade compatibility** | Vendor/mesh/CNI/kernel update có làm thay đổi semantics? | Bộ test hồi quy đi qua trước upgrade |

### 14.1. Không kiểm thử mỗi happy path

Một điều kiện allow đúng có thể che một lỗi nghiêm trọng trong negative path. Ví dụ:

| Nguồn | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Order-service đúng identity | Token hợp lệ, action được phép | Allow |
| Order-service đúng identity | Token hết hạn | Deny |
| Workload khác | Tự gửi header nói mình là order-service | Deny |
| Anonymous client | Gọi payment API nhạy cảm | Deny |
| Order-service đúng identity | Action chưa được cấp quyền | Deny |
| Order-service đúng identity | PDP unavailable | Hành vi fail mode theo ADR, không tự mở quyền |
| Source IPv6 hoặc đường direct-to-origin | Không qua PEP đã thiết kế | Không có bypass |
| PEP đang rollback | Đang có traffic hợp lệ và không hợp lệ | Đảm bảo policy version và kiểm soát phù hợp |

Đừng đánh giá custom control bằng chỉ số “đa số request trả 200”. Cần đo **true/false allow và true/false deny** theo test set có nhãn đúng, đồng thời ghi rõ cái gì nằm ngoài phạm vi.

## 15. Observability và điều tra sự cố

Một custom control mà không giải thích được **vì sao nó cho phép hoặc từ chối** sẽ khó vận hành và khó kiểm toán.

### 15.1. Audit fields nên có

| Trường | Mục đích |
| --- | --- |
| event_time_utc | So timeline với firewall, app, SIEM |
| request/flow/decision ID | Liên hệ log qua các lớp |
| verified principal | Chủ thể được xác thực bằng nguồn tin cậy |
| resource/action | Điều được yêu cầu, đã chuẩn hóa |
| policy ID và version | Tìm đúng rule đã áp |
| decision/reason code | Allow/deny/limit và lý do |
| enforcement point | Gateway/node/zone đã ra quyết định |
| dependency health | PDP/IdP/cache có hoạt động bình thường? |
| latency và timeout | Phân biệt deny do policy với lỗi hệ thống |
| deployment/config version | Đối chiếu kết quả trước/sau rollout |

**Không log raw bearer token, password, private key hay full sensitive payload** chỉ để debug. Cân bằng data minimization với khả năng audit; log cần phân quyền, retention và bảo vệ integrity.

### 15.2. Chỉ số vận hành

- Request rate, allow/deny rates theo policy và asset role.
- PDP/PEP latency p50/p95/p99, timeout, fallback/fail mode counters.
- Authentication failure và policy conflict counts.
- Cache hit/miss, cache age, revocation delay.
- Policy version distribution và drift giữa nodes/regions.
- CPU, memory, connection/session state, packet drops nếu ở data plane.
- Mất event/telemetry và độ trễ ingest vào SIEM.
- Tỷ lệ test positive/negative thành công sau mỗi release.

Cần giới hạn cardinality của metrics, tránh gắn raw user IDs, tokens hay request IDs làm label trong hệ thống quan sát. Chi tiết từng quyết định nên nằm ở log/traces có bảo vệ, không phải metric label không kiểm soát.

## 16. Case study: có nên tự viết egress control cho workload cloud?

### 16.1. Bối cảnh

Doanh nghiệp vận hành vài trăm microservices trải trên nhiều cloud account, mỗi service có danh tính workload riêng. Một nhóm cần bảo vệ dữ liệu khách hàng bằng quy tắc: **workload chỉ được kết nối các external service đã phê duyệt**. Danh sách destination thay đổi theo vòng đời sản phẩm và một số đích dùng CDN với IP động.

Yêu cầu:

1. Cho phép egress có chủ đích, hạn chế kết nối không rõ owner.
2. Policy dựa trên **workload identity/service ownership**, không chỉ static pod IP.
3. Có audit theo asset/service và policy version.
4. Không chặn DNS, telemetry hoặc hoạt động khôi phục hợp lệ.
5. Có HA, canary, rollback và đáp ứng latency/throughput mục tiêu.

### 16.2. So sánh phương án

| Phương án | Lợi thế | Rủi ro/giới hạn | Kết luận sơ bộ |
| --- | --- | --- | --- |
| **A. Native cloud egress firewall/security group** | Được hỗ trợ, tích hợp quản trị, ít code tùy biến | Có thể thiếu identity/hostname semantics cần thiết; phụ thuộc nền tảng | Thử nghiệm đầu tiên |
| **B. Egress gateway/proxy có chính sách sẵn có** | Cho phép kiểm soát theo giao thức/host, tập trung logging | Phải tránh bypass và kiểm tra DNS/CDN, TLS/QUIC, HA | Ưu tiên nếu đáp ứng yêu cầu |
| **C. Controller sinh rule từ inventory/identity** | Tự động hóa policy lifecycle nhưng giữ native enforcement | Mapping identity→network, eventual consistency, lạm quyền control plane | Chỉ cân nhắc nếu A/B thiếu yêu cầu cụ thể |
| **D. Tự viết eBPF packet filter hoặc proxy mới** | Khả năng kiểm soát riêng tối đa | Correctness, protocol state, kernel/runtime, security review, support rất lớn | Chỉ cân nhắc cuối cùng sau bằng chứng rõ |

### 16.3. Quyết định mẫu

Qua PoC, giả sử proxy/gateway chuẩn hỗ trợ identity và policy egress cần thiết. Nhóm chọn **B kết hợp native segmentation ở A**, không tự viết data-plane component. Chỉ phát triển **controller nhỏ nếu thực sự cần** đồng bộ ownership/inventory vào policy API được hỗ trợ; controller phải tách quyền ghi policy, có review, audit và rollback.

**Điều kiện xem xét lại:** khi gateway không đáp ứng yêu cầu được kiểm chứng (ví dụ protocol đặc thù cần enforcement mà các API/extension được hỗ trợ không thể xử lý), nhóm mới viết ADR riêng cho custom component, phân tích toàn bộ rủi ro, đặc biệt đối với bypass, throughput, certificate lifecycle và failover.

### 16.4. Acceptance tests của ví dụ

| Test | Luồng | Kết quả mong muốn |
| --- | --- | --- |
| E01 | Workload hợp lệ → external API đã phê duyệt | Cho phép, audit đúng workload identity |
| E02 | Workload hợp lệ → destination ngoài danh mục | Từ chối theo policy |
| E03 | Workload khác mạo danh qua header tự khai | Không cấp quyền bằng header đó |
| E04 | Pod restart, IP đổi nhưng identity giữ nguyên | Policy vẫn áp đúng workload |
| E05 | CDN đổi địa chỉ theo DNS | Quy tắc không dựa trên mapping stale không kiểm soát |
| E06 | Không có proxy path hoặc IPv6/UDP flow | Không tồn tại đường bypass được phép ngoài thiết kế |
| E07 | Gateway/PDP outage | Fail mode và phục hồi theo ADR |
| E08 | Rollout policy mới và rollback | Không vô tình mở đích ngoài danh mục |
| E09 | Có traffic hợp lệ cần DNS/NTP/telemetry | Không bị chặn ngoài ý định |

## 17. Architecture Decision Record: ghi lại quyết định custom hay không

Một ADR phải thể hiện **vì sao** custom được hoặc không được chọn, không chỉ nêu tên thư viện hay công cụ.

~~~markdown
# ADR-EXAMPLE-010: Kiểm soát egress theo workload identity

Trạng thái: Proposed
Owner: Platform Security / Network Security
Ngày: 2026-11-28

## Bối cảnh
- Workload đa môi trường có IP thay đổi động.
- Cần giới hạn egress theo dịch vụ có owner và đích được phê duyệt.
- Data boundary: workload -> external destinations.

## Yêu cầu
- Policy thực thi tại nơi mọi egress liên quan đi qua.
- Xác định được workload identity đáng tin.
- Default deny ở đường nhạy cảm, có ngoại lệ thời hạn rõ ràng.
- Audit theo decision, policy version; bảo vệ thông tin nhạy cảm.
- Có HA, policy rollback, tests về IPv4/IPv6, TCP/UDP và DNS.

## Các phương án
- A: Native cloud firewall/security group.
- B: Gateway/proxy được hỗ trợ.
- C: Custom controller sinh native policy.
- D: Custom eBPF/packet-filter data plane.

## Quyết định đề xuất
- Dùng A + B vì PoC đáp ứng chức năng và test.
- Chưa phát triển D; C chỉ mở rộng khi có khoảng trống automation rõ.

## Trade-offs
- Phụ thuộc gateway, DNS và identity lifecycle.
- Có chi phí vận hành và độ trễ bổ sung.
- Cần giám sát bypass và policy drift.

## Kiểm chứng
- Test E01..E09.
- So sánh latency/throughput với baseline có cùng traffic.
- Kiểm tra rollback, failover và mất identity provider.

## Rà soát lại
- Khi có workload/protocol mới, cloud region mới hoặc đổi enforcement.
- Khi PoC chứng minh gateway không đáp ứng yêu cầu.
~~~

Tài liệu chỉ là **mẫu**, chưa phải quyết định được phê duyệt. Nếu chọn custom thật, ADR cần có người chịu trách nhiệm bảo trì, giới hạn tác động khi lỗi và kế hoạch thoát khỏi giải pháp.

## 18. Runbook triển khai và vận hành sau khi chọn custom

### Giai đoạn 1 — Discovery

Phân loại tài sản/luồng, xác định boundary, route, identity và data classification. Xây **expected allow/deny matrix**, ghi rõ ngoài phạm vi và owner. Lập baseline hiệu năng, sự cố và tần suất thay policy.

### Giai đoạn 2 — Design

Tách policy administration/decision/enforcement; xác minh dữ liệu nào có thật tại PEP; thiết kế semantics, default, exception, revocation, fail mode, audit, quyền quản trị và kế hoạch phiên bản.

### Giai đoạn 3 — Proof of Concept

Làm PoC trong lab/staging với cả traffic hợp lệ và trái phép. Kiểm tra IPv6, UDP/QUIC, NAT, proxy path, service identity, gateway outage, policy rollback, latency và logging. Không dùng dữ liệu khách hàng thật khi không cần.

### Giai đoạn 4 — Review và hardening

Thực hiện threat modeling, code review, dependency/security review, kiểm thử parser/input, load, resilience và HA; bảo vệ secrets, build pipeline, artifacts, admin API và signed policy deployment.

### Giai đoạn 5 — Release an toàn

Chạy canary trên một nhóm tài sản được chọn; giám sát deny/allow anomalies, error rate, resource pressure và log integrity; có stop conditions rõ. Tăng phạm vi theo change approval và kiểm tra lại policy effective tại mọi điểm thực thi.

### Giai đoạn 6 — Vận hành lâu dài

Cập nhật runbook, on-call, SLO, certificate/secret rotation, vulnerability patching, policy recertification, backup và restore test. Rà soát exception hết hạn và drift định kỳ; lặp lại acceptance tests mỗi khi thay dependency hoặc topology.

### Giai đoạn 7 — Thay thế hoặc loại bỏ

Khi vendor/native feature đáp ứng tốt hơn, lập kế hoạch migrate và sunset custom. Đo nguy cơ “hai policy engines cùng thực thi” trong giai đoạn chuyển đổi, đảm bảo không có khoảng thời gian cả hai cùng cho phép ngoài dự kiến hoặc cùng chặn dịch vụ hợp lệ.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chọn eBPF/custom proxy vì công nghệ mới hấp dẫn | Chi phí kỹ thuật và rủi ro vượt nhu cầu | Xác minh gap của native feature trước |
| Đặt PEP không nằm trên tất cả các đường liên quan | Có thể bypass bằng đường khác | DFD, traffic map, IPv6, failover và direct-origin tests |
| Dùng source IP hoặc X-Forwarded-For như identity được chứng minh | Spoofing, NAT/shared IP, truy cập sai quyền | Xác minh identity ở trust boundary và chuẩn hóa header |
| Mặc định mTLS đủ authorization | Workload hợp lệ vẫn có thể lạm dụng API | Resource/action-level authz và least privilege |
| Một policy engine giữ toàn bộ quyền admin cloud | Khi bị chiếm gây blast radius lớn | Tách role, scoped permissions và approval |
| Cache allow vô hạn | Quyền đã thu hồi vẫn còn hiệu lực | TTL, invalidation và revocation tests |
| Fail-open trên mọi route | Outage làm toàn bộ control mất tác dụng | Quyết định fail mode theo data/risk class |
| Fail-closed mọi luồng không có recovery plan | Một IdP outage có thể cắt toàn bộ dịch vụ | HA, dependency resilience, break-glass có kiểm soát |
| Không quản lý policy version giữa PEP nodes | Kết quả allow/deny bất nhất | Version pin, rollout status và drift alert |
| Lẫn control plane với data plane | Đánh giá sai coverage hoặc quyền | Sơ đồ quyết định/chuyển tiếp riêng |
| Chỉ test allow | Lỗ hổng bypass không được phát hiện | Negative tests và malicious input cases |
| Không test IPv6/QUIC/UDP | Đường mới không đi qua filter TCP/IPv4 | Protocol/address-family coverage matrix |
| Log token hoặc full request body | Tạo kho dữ liệu nhạy cảm mới | Data minimization, redact và restricted audit |
| Không có owner/on-call | Sự cố production kéo dài | Runbook, SLO, rotation và support contract |
| Không có tiêu chí sunset | Custom tồn tại vĩnh viễn và không được vá | ADR review và migration plan |

## 20. Checklist quyết định có cần custom network control

- [ ] Đã xác định **rủi ro nghiệp vụ, tài sản, data classification và trust boundary**.
- [ ] Đã viết chính sách bằng ngôn ngữ **ai – làm gì – với tài nguyên nào – điều kiện nào**.
- [ ] Đã xác minh PEP cần xử lý L3/L4, identity, L7 action hay dữ liệu.
- [ ] Đã kiểm tra cấu hình chuẩn, IAM/application authz, native cloud/CNI, policy-as-code và plugin được hỗ trợ.
- [ ] Có **bằng chứng capability gap**, không dựa trên cảm giác công cụ hiện tại bất tiện.
- [ ] Đã phân biệt custom policy, controller, plugin và tự viết data-plane enforcement.
- [ ] Đã so chi phí dài hạn, support, performance, license/vendor constraints và chi phí chuyển đổi.
- [ ] Đã vẽ forward, return, failover paths cùng NAT, proxy, TLS, VPN, IPv4/IPv6 và UDP/QUIC liên quan.
- [ ] Identity và policy inputs được xác minh từ nguồn tin cậy, không dựa vào header tự khai.
- [ ] Đã mô tả PAP/PDP/PEP, policy precedence, default, expiry và quyền đổi policy.
- [ ] Đã threat-model spoofing, bypass, parser ambiguity, privilege escalation, stale cache, DoS và supply chain.
- [ ] Đã có fail-open/fail-closed theo mức rủi ro, HA, rollback và emergency recovery.
- [ ] Đã xác định SLO và đo latency p95/p99, throughput, resource budgets theo baseline.
- [ ] Có positive, negative, revocation, protocol, outage và failover acceptance tests.
- [ ] Có canary, stop conditions, change control, policy version, audit và telemetry coverage.
- [ ] Có owner/on-call, code/security review, CI/CD, dependency updates và kế hoạch giữ bí mật.
- [ ] Có ADR ghi lựa chọn, phương án bị loại, trade-offs, rủi ro còn lại và ngày review.
- [ ] Có tiêu chí khi nào **quay lại native control hoặc sunset** giải pháp tùy biến.

**Kết luận:** chỉ nên xây **custom network control** khi đã xác định rõ trust boundary và một khoảng trống bảo vệ có ý nghĩa mà cấu hình hoặc thành phần được hỗ trợ không giải quyết được, đồng thời có đủ năng lực kiểm thử, vận hành và khôi phục an toàn. Phương án tốt thường là **dùng enforcement đã được hỗ trợ với policy và tích hợp tối thiểu cần thiết**, thay vì tạo một data plane mới. Quyết định kiến trúc cần được chứng minh bằng test, audit và đo rủi ro thực, không bằng số lượng mã nguồn hoặc độ phức tạp công nghệ.
