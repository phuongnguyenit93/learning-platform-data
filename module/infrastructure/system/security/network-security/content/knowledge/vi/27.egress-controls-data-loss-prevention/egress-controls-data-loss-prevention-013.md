# Ngoại lệ egress có thời hạn và người phê duyệt

> **Chương:** Kiểm soát egress và chống thất thoát dữ liệu  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Thiết kế phòng vệ mạng từ phân đoạn, firewall, VPN, IDS/IPS, DNS, cloud đến phân tích lưu lượng và ngăn thất thoát dữ liệu.  
> **Trọng tâm:** Quản trị **ngoại lệ truy cập mạng đi ra (egress exception)** như quyền tạm thời có **người yêu cầu, người sở hữu, người phê duyệt độc lập, phạm vi chính xác, lý do nghiệp vụ, thời hạn, cơ chế thu hồi và bằng chứng kiểm toán**. Một ticket hết hạn **không chứng minh** firewall/proxy/cloud rule đã bị gỡ.

## 1. Tại sao cần ngoại lệ egress có thời hạn?

Chính sách egress giới hạn nơi workload, máy trạm và hệ thống có thể gửi traffic **ra khỏi một trust boundary**: từ Pod production đến SaaS, từ VM đến Internet, từ ứng dụng đến API đối tác hoặc từ network nội bộ đến vùng dữ liệu khác.

Một tổ chức áp dụng **default-deny hoặc default-restrict** vẫn có nhu cầu ngoại lệ hợp lệ:

- Ứng dụng thử kết nối **webhook/API đối tác** trong migration.
- SRE cần endpoint hỗ trợ nhà cung cấp trong cửa sổ khắc phục sự cố.
- Hệ thống tải **bản vá và artifact đã xác minh** từ repository chưa có trong allowlist.
- Một nhóm cần xuất bộ dữ liệu **đã ẩn danh, được data owner duyệt** sang hệ phân tích.
- Kịch bản chuyển đổi cần song song endpoint cũ và mới trong thời gian ngắn.
- Một automation triển khai phải kết nối tạm tới API cloud/SaaS mới.

Nếu phản ứng bằng luật **allow-any-to-Internet**, mở toàn VPC hoặc cấp vĩnh viễn, tổ chức để lại **đường thoát dữ liệu** có thể bị lạm dụng sau khi công việc kết thúc.

**Ngoại lệ egress có thời hạn** là thay đổi được phê duyệt, cho phép **đúng nguồn → đích → giao thức → dữ liệu → mục đích** trong **cửa sổ nhỏ nhất**, kèm tự thu hồi và kiểm tra thực tế. Một request không có destination rõ, không có approver hợp lệ hoặc không có expiry là **chưa đủ điều kiện triển khai**.

### Mục tiêu học tập

Người học có thể:

1. Phân biệt baseline, temporary exception, renewal và emergency break-glass.
2. Định nghĩa yêu cầu gồm source identity, destination, protocol, data class, owner, approver, TTL và rollback.
3. Thiết kế phân quyền phê duyệt, tránh **tự yêu cầu–tự duyệt–tự triển khai**.
4. Nhận diện giới hạn của **IP/CIDR, FQDN, DNS, SNI, TLS, QUIC, NAT và IPv6**.
5. Hiểu **effective expiry**, auto-revoke, cache, long-lived connections và fail-safe.
6. Áp ngoại lệ qua **firewall, secure web gateway, egress proxy, cloud firewall và Kubernetes/CNI**.
7. Kết hợp DLP để giới hạn nội dung được gửi, không nhầm network ALLOW với quyền xuất dữ liệu.
8. Ghi audit và phát hiện ngoại lệ quá hạn, quá rộng hoặc bị lạm dụng.
9. Kiểm thử **ALLOW đúng phạm vi, DENY ngoài phạm vi, EXPIRE, REVOKE và rollback**.
10. Thực hiện runbook cho cấp quyền, gia hạn, sự cố và chứng minh đóng đường mạng.

**Nguyên tắc:** ngoại lệ tốt có **đích xác định, phạm vi tối thiểu, người duyệt độc lập, hạn cuối bắt buộc và bằng chứng đã đóng thật**.

## 2. Thuật ngữ và ba lớp kiểm soát

| Thuật ngữ | Ý nghĩa | Không nên nhầm |
|---|---|---|
| **Egress** | Traffic đi ra khỏi trust boundary | Mọi traffic HTTPS đều an toàn |
| **DLP** | Data Loss Prevention: phát hiện/ngăn dữ liệu rò rỉ | Firewall L3/L4 tự hiểu dữ liệu mã hóa |
| **Baseline** | Policy vận hành thông thường đã phê duyệt | Ngoại lệ cá biệt |
| **Exception** | Quyền lệch baseline có giới hạn | Quyền vĩnh viễn |
| **Requestor** | Người/đội yêu cầu | Approver |
| **Business/data owner** | Chịu trách nhiệm ứng dụng/dữ liệu | Người có quyền sửa firewall |
| **Approver** | Người chấp nhận ngoại lệ theo thẩm quyền | Một chuỗi tùy ý trong YAML |
| **PEP** | Policy Enforcement Point: nơi rule thực sự chặn/cho kết nối | Ticket/PR là ý định |
| **TTL/Expiry** | Khoảng sống và mốc hết hiệu lực | Hết hạn ticket nhưng rule vẫn mở |
| **SoD** | Separation of Duties, tách vai trò | Hai checkbox cùng người bấm |
| **FQDN** | Tên miền đầy đủ | IP tĩnh hoặc danh tính TLS |
| **SNAT** | NAT thay source IP | Danh tính user/workload |
| **Drift** | Trạng thái thực tế lệch policy được duyệt | Một thay đổi luôn là tấn công |
| **Kill switch** | Cơ chế ngắt quyền/flow khẩn cấp | Chỉ đóng phiếu yêu cầu |

Ba lớp cần tách:

1. **Network authorization:** source nào đến IP/port/host qua firewall, gateway, proxy?
2. **Application authorization:** caller được POST endpoint/API/tenant nào?
3. **Data authorization/DLP:** nội dung, phân loại, lượng dữ liệu và mục đích gửi có được phép không?

Network ALLOW **không** tự cho quyền gửi hồ sơ khách hàng, access token, private keys hay dữ liệu restricted.

## 3. Kiến trúc ngoại lệ được phê duyệt

~~~mermaid
flowchart LR
    A[Người dùng / Workload] --> F[Host / CNI / Cloud firewall]
    F --> G[Egress gateway / Secure web proxy]
    G --> D{Destination / TLS / DLP checks}
    D -- ALLOW --> E[Đích đã phê duyệt]
    D -- DENY --> X[Block + security event]
    R[Request + owner + independent approval + TTL] --> P[Policy controller / IaC]
    P --> F
    P --> G
    F -. Flow data .-> S[SIEM + Audit]
    G -. Proxy / DLP events .-> S
    P -. Approval / Apply / Revoke .-> S
~~~

**Ticket** không phải policy enforcement. Pipeline phải biến thay đổi được duyệt thành rule cụ thể; firewall/CNI giới hạn đường mạng, proxy có thể xét tên miền/L7 và DLP kiểm soát nội dung theo năng lực. SIEM là nơi quan sát, không phải nơi chặn.

Chỉ có proxy có thể bị bypass qua **direct IP, IPv6, alternate ports hoặc QUIC**. Chỉ có L3 firewall có thể không biết **HTTP endpoint, SaaS tenant hay dữ liệu trong TLS**. Phối hợp hai lớp khi mức rủi ro yêu cầu.

## 4. Threat model ngoại lệ egress

| Mối đe dọa | Ví dụ | Kiểm soát |
|---|---|---|
| **Destination rộng** | Cho toàn CIDR/cloud provider thay một API | Exact host/service + policy tests |
| **Source rộng** | Mọi production Pods cùng được export | Workload identity, CNI/segmentation |
| **Ngoại lệ vĩnh viễn** | Migration xong nhưng rule còn | Auto-expiry + actual deny verification |
| **Phê duyệt giả** | Requester tự khai approved=true | Trusted workflow và identity-bound approval |
| **Xung đột vai trò** | Requester sửa CI/approve role của mình | SoD, independent review |
| **DNS drift** | FQDN chuyển IP khác hoặc CNAME ngoài chuẩn | Resolver, TLS identity, proxy |
| **HTTPS exfiltration** | Gửi secrets qua POST 443 | DLP, L7/app policy, quotas |
| **DNS tunneling** | Dữ liệu đi trong query DNS | Approved resolver, DNS policy/telemetry |
| **Alternate protocol** | QUIC UDP 443 thay TCP HTTPS | Protocol-specific allowlist |
| **IPv6 bypass** | IPv4 deny nhưng IPv6 không giới hạn | Dual-stack rule parity |
| **Wildcard SaaS** | *.vendor.example chứa dịch vụ không cần | Exact host/account/tenant mapping |
| **Long-lived flow** | Socket còn mở sau khi rule hết hạn | Session/conntrack handling + SLO |
| **Emergency abuse** | Break-glass thành đường vĩnh viễn | Very short TTL, paging và post-review |
| **Mất audit** | Tắt proxy logs trước data transfer | Separate log IAM, alerts |
| **Compromised legitimate source** | Attacker dùng chính workload được allow | DLP, anomaly detection, per-action auth |
| **Policy pipeline compromise** | Thay digest/approval trong CI | Signed evidence, branch protection |

**Traffic tăng bất thường không mặc định chứng minh exfiltration.** Phân biệt khả năng phơi lộ, nỗ lực truyền, transfer thực tế và **loss of sensitive data** có bằng chứng.

## 5. Baseline, ngoại lệ, gia hạn và emergency

| Loại | Mục đích | Phê duyệt | Thời hạn | Theo dõi |
|---|---|---|---|---|
| **Baseline allow** | Nhu cầu dài hạn theo thiết kế | Architecture/security owner | Periodic review | IaC/config compliance |
| **Temporary exception** | Support, migration, thử nghiệm | Approver đúng risk | **Hạn tuyệt đối** | Auto-revoke + verify |
| **Renewal** | Công việc chưa hoàn thành | **Re-approval** đúng scope | Mốc mới có giới hạn | New version/audit |
| **Break-glass** | Sự cố nghiêm trọng, cần quyết định nhanh | Emergency authority + post-review | **Rất ngắn** | Alert và kill switch |
| **Baseline policy change** | Nhu cầu đã ổn định | Security architecture/data governance | Không dùng exception TTL | Review định kỳ |

Không kéo dài ngoại lệ vô hạn bằng auto-renew; nếu ngoại lệ lặp nhiều lần, cần xem **thay đổi kiến trúc chính thức** hoặc thiết kế controlled egress chuẩn. Emergency vẫn có owner, audit, hết hạn và hậu kiểm.

## 6. Mô hình dữ liệu ngoại lệ đủ để kiểm soát

| Field | Ví dụ tài liệu | Điều cần xác minh |
|---|---|---|
| **exception_id** | EGX-EXAMPLE-0042 | Duy nhất, không phải bằng chứng approval |
| **requester** | app-engineer | Identity đã xác thực |
| **business_owner** | reporting-owner | Nhu cầu nghiệp vụ |
| **data_owner** | customer-data-steward | Loại dữ liệu được chuyển |
| **approver** | network-security-reviewer | Thẩm quyền và độc lập |
| **source** | Namespace analytics, SA export-job | Không mở toàn cluster |
| **destination** | ingest.partner.example | Host/trust được xác minh |
| **protocol** | TLS/TCP 443 | Không ngầm mở UDP 443 |
| **operation** | POST /v1/batches | Cần L7-capable PEP để enforce |
| **data_class** | Aggregated/anonymized | DLP và ứng dụng kiểm chứng |
| **volume_budget** | 50 MiB tổng | Chỉ hiệu lực khi PEP đếm được |
| **effective_from** | 2026-11-28T10:00:00Z | UTC/server clock |
| **expires_at** | 2026-11-28T12:00:00Z | Đóng đúng hạn |
| **change_ref** | CHG-EXAMPLE-42 | Ticket liên kết approval |
| **policy_digest** | SHA-256 của canonical policy | Áp đúng bản được duyệt |
| **revocation_owner** | netsec-oncall | Xử lý auto-revoke failure |
| **risk_class** | R3/high | Approver, TTL cap và kiểm soát bổ sung |

Giá trị minh họa **không phải cấu hình native** của một vendor. Trường **HTTP method, DLP classification, content size và tenant** chỉ có ý nghĩa nếu tồn tại proxy/app/DLP thực sự enforce; SG và NetworkPolicy thuần L3/L4 không hiểu chúng.

### 6.1. Mục đích nghiệp vụ không phải quyền

Câu "cần kết nối SaaS để demo" là justification, không phải machine-verifiable permission. Một rule **0.0.0.0/0 TCP any** không trở nên an toàn nhờ ticket có mô tả chi tiết.

## 7. Nguyên tắc tối thiểu hóa phạm vi

1. **Source:** verified workload/ServiceAccount/VM identity/user group; không mặc định cả prod CIDR.
2. **Destination:** exact FQDN/service endpoint, certificate identity, SaaS account/tenant hoặc IP/CIDR đã duyệt.
3. **Protocol/port:** chỉ giao thức thực sự cần, ví dụ TCP/443, không tự thêm UDP.
4. **L7 operation:** method/path/service/method nếu gateway có năng lực enforce.
5. **Data:** classification, masking, DLP inspection, volume/rate và transfer destination policy.
6. **Time:** activation window, hard expiry, session termination SLO.
7. **Environment:** dev/staging/prod, cluster/account/VPC, region và cloud route.
8. **Evidence:** logging, tests, owner, change ID và revalidation.

**Yêu cầu yếu:** mở HTTPS ra toàn Internet cho mọi production servers trong một tuần.

**Yêu cầu tốt hơn:** chỉ ServiceAccount **export-job** ở namespace analytics gọi **ingest.partner.example:443**, gửi đúng endpoint ingestion của đối tác trong **2 giờ**, dữ liệu đã ẩn danh, owner/data owner/security approval, có quota và log; tất cả đường direct Internet khác bị deny.

Không khẳng định yêu cầu đã được enforce cho đến khi PEP/cloud/CNI và DLP **được cấu hình và test**.

## 8. Người yêu cầu, phê duyệt và triển khai

| Vai trò | Request | Đánh giá dữ liệu | Risk approval | Apply | Revoke/verify |
|---|---|---|---|---|---|
| **App/SRE requester** | Có | Cung cấp context | Không tự duyệt | Không trực tiếp ở prod | Hỗ trợ test |
| **Business owner** | Chịu trách nhiệm nhu cầu | Phối hợp | Duyệt business need | Không | Xác nhận hoàn tất |
| **Data owner/DPO** | Có thể tư vấn | Đánh giá classification | Duyệt transfer nhạy cảm | Không | Review data impact |
| **Network security approver** | Xem request | DLP/network risk | Độc lập duyệt deviation | Không tự hợp thức hóa | Review evidence |
| **Protected CI/deployer** | Không tự quyết định mục đích | Không | Không | Apply approved digest | Auto-revoke |
| **SOC/on-call** | Theo incident | Theo dõi | Emergency theo thẩm quyền | Qua trusted mechanism | Monitor/contain |
| **Independent auditor** | Không | Không | Không | Không | Verify logs/state |

**SoD thực chất** đòi người đề xuất không đồng thời có thể sửa workflow approval, tự approve policy, thay protected CI và xóa audit. Trong nhóm nhỏ, nếu không thể tách mọi vai trò, phải có **compensating controls**: second-person review, short TTL, alert và hậu kiểm độc lập.

### 8.1. Kiểm tra thẩm quyền của approver

- Có quyền duyệt **production egress** hay chỉ dev?
- Có được duyệt loại dữ liệu đang chuyển không?
- Quyền approval còn hiệu lực tại **thời điểm duyệt/áp dụng**?
- Có xung đột lợi ích hoặc chính là requestor?
- Approval gắn đúng **scope, digest và expires_at**?
- Với dữ liệu restricted có cần **data owner + security** độc lập?
- Approval đã bị thu hồi giữa plan và apply chưa?

## 9. Ma trận rủi ro và tuyến phê duyệt

| Risk | Ví dụ | Người duyệt (minh họa) | TTL tối đa (minh họa) |
|---|---|---|---|
| **R1 thấp** | Dev tải patch từ mirror tin cậy | Dev owner + kiểm soát tự động | 4 giờ |
| **R2 trung bình** | Staging gọi vendor sandbox API | App owner + NetSec | 2 giờ |
| **R3 cao** | Production gửi batch dữ liệu tổng hợp | App owner + Data owner + NetSec | 60 phút |
| **R4 rất cao** | Dữ liệu restricted, đích không kiểm chứng, bypass DLP | Formal risk review; có thể từ chối | Không tự cấp |
| **Emergency** | Hỗ trợ nhà cung cấp để phục hồi outage | Incident commander + Security on-call | 15–30 phút |

Đây là **ma trận đào tạo, không phải thời hạn chuẩn**. Tổ chức thiết lập dựa trên risk appetite, dữ liệu và khả năng auto-revoke. Không chia một yêu cầu quá rộng thành nhiều ticket nhỏ để lách limit.

### 9.1. Rủi ro phụ thuộc cả nguồn và dữ liệu

Mở HTTPS đến domain phổ biến không hẳn thấp rủi ro nếu **source là DB backup production chứa PII**. Cùng domain từ máy build staging tải artifact đã được xác minh có risk profile khác.

## 10. Phê duyệt phải gắn bản thay đổi chính xác

Approver duyệt **source A → destination B cổng 443 trong 60 phút**. Nếu requester đổi destination thành wildcard hoặc kéo dài thêm 1 ngày, **approval cũ phải vô hiệu** đối với bản mới.

~~~mermaid
flowchart TD
    R[Authenticated Request] --> V[Validate source/dest/data/risk/expiry]
    V --> H[Canonical policy payload + digest]
    H --> A{Independent approval for exact digest?}
    A -- No --> X[Reject / revise request]
    A -- Yes --> C[Protected deployment role]
    C --> P{Digest + approver entitlement still valid?}
    P -- No --> X
    P -- Yes --> E[Apply scoped rule]
    E --> T[Expiry scheduler + monitoring]
    T --> K[Revoke + actual deny verification]
~~~

### 10.1. Chat comment không phải approval nguồn sự thật

Một comment "OK" có thể hỗ trợ giao tiếp, nhưng authorization phải từ **trusted workflow** với verified approver identity, quyền, timestamp và signed/tamper-evident policy digest. Không chấp nhận field **approved: true** do requester tự đưa vào YAML.

### 10.2. CI permissions là đường nâng quyền

Người không có quyền cloud firewall nhưng có quyền sửa CI workflow hoặc assume **egress-policy-deployer role** có thể mở đường egress gián tiếp. Bảo vệ **repo approvals, protected environments, OIDC trust conditions, CI config, role assignments và audit**.

## 11. Xung đột phê duyệt và thay đổi sau khi duyệt

| Trường hợp | Phản ứng đúng |
|---|---|
| Requester cũng là app owner | Security approver độc lập cho change |
| Security approver có quyền deploy | Independent second review/compensating control |
| Emergency do on-call tự yêu cầu | Predefined break-glass + post-incident review |
| Data owner duyệt data nhưng không duyệt network | Bổ sung NetSec approval |
| Vendor tự xác nhận "được gửi dữ liệu" | Internal data/business owner vẫn cần duyệt |
| Policy đã bị sửa sau approval | Re-approve digest/contents |
| Approver bị thu hồi role | Ngừng dùng cho approval mới; đánh giá rule về hiệu lực approval cũ |
| Không có approver trực | Escalation, không fail-open mặc định |
| Wildcard domain được duyệt khi chỉ cần 1 host | Thu hẹp hoặc formal exception review |
| Vendor cần gia hạn liên tục | Review kiến trúc và reapproval, không auto-extend |

## 12. Thời hạn: created, approved, activated, expired, closed

Một exception lifecycle nên ghi riêng:

- **created_at:** request được ghi nhận.
- **approved_at:** approval được ký hợp lệ.
- **effective_from:** mốc sớm nhất cho phép.
- **activated_at:** PEP đã apply thành công.
- **expires_at:** mốc UTC tuyệt đối chặn **kết nối mới** được cấp bởi exception.
- **revoked_at:** hệ thống quyết định thu hồi sớm/hết hạn.
- **enforced_closed_at:** **data plane đã được kiểm chứng** không còn quyền ngoại lệ.
- **purged_at:** dọn các rule/list entry/cache liên quan.

~~~text
allow_new_flow(t) =
    exact_scope_approved
AND t >= effective_from
AND t < expires_at
AND not_revoked
AND current_source_dest_protocol_match
AND no_explicit_deny
AND enforcement_point_on_actual_path
~~~

**Không phải mọi firewall hỗ trợ expiry tự động.** Định nghĩa này phải được hiện thực bằng **controller/scheduler, rule update, propagation và tests**.

### 12.1. Hết hạn phê duyệt và hết hạn phiên deploy là hai thứ khác nhau

Một JIT deploy role hết hạn lúc 10:45 **không tự xóa** rule firewall mà role đã tạo. Ngược lại exception expires lúc 11:00 yêu cầu **rule thực thi hết quyền** theo cơ chế riêng. Nếu controller dùng deadline tổng hợp, có thể chọn **min(exception_expiry, approval_expiry, policy_limit)** nhưng phải rõ phần nào là ràng buộc business, phần nào ảnh hưởng active network state.

### 12.2. UTC, timezone và đồng hồ đáng tin

Dùng ISO 8601 có **Z hoặc offset rõ**; đồng bộ NTP, theo dõi clock skew, không lưu "cuối giờ chiều" hay giờ địa phương thiếu offset. Scheduler đo **expiry-to-deny delay**, không chỉ thấy ticket đóng đúng giờ.

### 12.3. Không đổi timezone để kéo dài

Mốc **2026-11-28T11:00:00Z** là một instant bất biến. UI có thể hiển thị theo timezone người dùng, nhưng controller phải so sánh canonical time, tránh sai lệch khi khu vực đổi giờ hoặc admin ở nơi khác.

## 13. Vòng đời ngoại lệ và trạng thái hệ thống

Một ngoại lệ không nên chỉ có hai trạng thái **Open/Closed**. Dùng state machine rõ ràng giúp phân biệt phê duyệt với enforcement thực:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED
    SUBMITTED --> REJECTED: Risk/Scope không đạt
    SUBMITTED --> APPROVED: Verified independent approval
    APPROVED --> SCHEDULED: Window chưa đến
    APPROVED --> APPLYING: Effective time đã đến
    SCHEDULED --> APPLYING
    APPLYING --> ACTIVE: PEP apply + positive/negative checks
    APPLYING --> FAILED: Apply/validation error
    ACTIVE --> REVOKING: Expiry hoặc revoked early
    ACTIVE --> RENEWAL_PENDING: Gia hạn có yêu cầu mới
    RENEWAL_PENDING --> REVOKING: Hết thời hạn cũ
    RENEWAL_PENDING --> ACTIVE: Approval mới đúng policy, update thành công
    REVOKING --> CLOSED_VERIFIED: PEP deny verified
    REVOKING --> REVOCATION_FAILED: Rule/flow vẫn còn allow
    REVOCATION_FAILED --> REVOKING: Retry + escalation
    FAILED --> REVOKING: Cleanup partial apply
    REJECTED --> [*]
    CLOSED_VERIFIED --> [*]
~~~

### 13.1. APPROVED không đồng nghĩa ACTIVE

Approver có thể duyệt lúc 09:00 để policy chỉ chạy **10:00–11:00**. Controller phải chặn apply quá sớm, kiểm tra **approval chưa bị thu hồi**, source/destination không đổi và hạn tối đa không bị vượt.

### 13.2. ACTIVE đòi dữ liệu xác minh

Có rule mới trong config chưa chắc đã được **PEP load, route traffic qua đúng PEP, proxy nhận đúng policy version, CNI propagate hay cloud LB/firewall cập nhật**. ACTIVE là trạng thái có evidence deployment và checks tương ứng; nếu kiểm thử không khả dụng, ghi **ACTIVE_UNVERIFIED** hoặc trạng thái lỗi riêng theo thiết kế chứ không tuyên bố PASS.

### 13.3. CLOSED_VERIFIED đòi chứng minh DENY

Một ticket chuyển Closed nhưng rule vẫn active chỉ là **administrative closure**. Trạng thái **CLOSED_VERIFIED** cần tối thiểu: policy không còn allow theo ngoại lệ, data-plane negative test/telemetry phù hợp và những bypass/long-lived flows đã được xử lý theo SLO.

## 14. Quyền hết hạn và kết nối còn đang tồn tại

Các firewall stateful/proxies theo dõi connection/session. **Xóa allow rule thường ngăn flow mới, nhưng không phải mọi implementation sẽ cắt flow đã được thiết lập**.

### 14.1. Phân biệt ba hành vi

| Điều kiện | Có thể xảy ra | Cần xác minh |
|---|---|---|
| **New TCP connection sau expiry** | Bị chặn nếu policy đã gỡ và không có allow rule khác | Test new connection từ source test |
| **Existing TCP/TLS connection** | Có thể tiếp tục theo conntrack/session state | PEP session controls, flow logs |
| **Long-lived HTTP/2, gRPC, WebSocket** | Nhiều requests mới trên một connection cũ | Stream/request-level policy hay connection kill |
| **DNS cache** | Client vẫn giữ IP đã resolve | Domain/IP policy và resolver telemetry |
| **Async jobs/transfer** | Lệnh export bắt đầu trước expiry tiếp tục gửi | Application cancel, data transfer budget |
| **Proxy connection pool** | Reuse connection sau hết hạn | Proxy per-request/stream recheck |
| **NAT session** | Established entry tồn tại sau rule removal | Stateful firewall/NAT TTL, active session purge khi hỗ trợ |

### 14.2. Viết SLO chính xác

Ví dụ policy:

~~~text
At expires_at:
- New network flows must be denied within 60 seconds.
- Existing egress sessions must be terminated within 180 seconds
  where the enforcement point supports active-session deletion.
- Data export application jobs must stop or be reconciled
  within the business-approved incident/change workflow.
- If targets are not met: alert P1/P2 according to data risk,
  isolate source, and mark REVOCATION_FAILED.
~~~

**Đây là mục tiêu minh họa**. Một PEP không hỗ trợ ngắt active flow không thể được cam kết giả là ngắt trong 180 giây; cần đổi architecture hoặc bảo vệ bằng **app-level operation authorization và short session lifetime**, cùng fallback ngắt route/source theo risk.

### 14.3. Expiry không phải kết thúc data permission ngay trên mọi tầng

Một job bắt đầu xuất dữ liệu trước expiry có thể tiếp tục chạy ngoài deadline nếu backend không kiểm tra lại authorization. Phải quyết định rõ **"chặn transfer mới" vs "buộc dừng transfer đang chạy"** ở cả gateway và ứng dụng.

## 15. Gia hạn, thay đổi scope và thu hồi sớm

### 15.1. Gia hạn là approval mới

Không chấp nhận "thêm 2 giờ" bằng cách sửa expiry trong database không tạo audit. Yêu cầu:

1. **Current exception ID** và lý do chưa hoàn tất.
2. **Dữ liệu/đích/source thực tế** đã sử dụng; có phát sinh khác rủi ro không?
3. **Duration mới**, TTL tối đa và tổng thời gian exception tồn tại.
4. **Approver còn thẩm quyền** và không xung đột.
5. **Policy digest mới**, approval và deployment revision mới.
6. **Cửa sổ liên tục hay có gap**: phải thiết kế downtime/approval timing, không bỏ qua hạn cũ.
7. **Bằng chứng test sau update** và đồng bộ scheduler.

### 15.2. Không tự gia hạn chỉ vì có traffic

Nếu đến sát expiry vẫn đang có data transfer, đó là một tín hiệu vận hành cần **cảnh báo owner**; không được dùng **traffic continuing** để tự kéo dài quyền. Nếu dữ liệu nhạy cảm/đích đã thay đổi, cần risk review đầy đủ.

### 15.3. Thu hồi sớm

Nếu business owner nói công việc xong, data owner rút chấp thuận, SOC phát hiện exfiltration hoặc source workload bị compromise, policy phải hỗ trợ **REVOKE trước expires_at**. Hệ thống không được coi expiry tương lai là lý do trì hoãn containment.

### 15.4. Một sửa đổi đáng kể cần ticket/version khác

Thay source từ Pod A sang toàn namespace, đổi destination từ một host sang wildcard, đổi data class hoặc thêm UDP 443 là **scope change**, không phải "metadata update". Phải **revalidate + reapprove + deploy**.

## 16. Workflow triển khai ngoại lệ theo rủi ro

~~~mermaid
flowchart TD
    R[Requester cung cấp business need] --> C[Check schema + source/dest/data/TTL]
    C --> A{Risk R1/R2/R3/R4?}
    A -->|R4 không kiểm soát| D[DENY và đề xuất phương án an toàn]
    A -->|Có thể xem xét| E[App/Data/NetSec owners review]
    E --> P{Approval đủ thẩm quyền, đúng digest?}
    P -- No --> D
    P -- Yes --> I[Protected IaC deployment]
    I --> V{PEP apply + test ALLOW/DENY thành công?}
    V -- No --> B[Rollback partial change + alert]
    V -- Yes --> L[ACTIVE + TTL scheduler + log/bytes monitoring]
    L --> T{Expiry hoặc early revoke?}
    T -- No --> L
    T -- Yes --> X[Remove allow, flush sessions nếu cần]
    X --> F{New flows DENY, old flows resolved?}
    F -- No --> K[REVOCATION_FAILED, incident escalation]
    F -- Yes --> Z[CLOSED_VERIFIED + audit]
~~~

### 16.1. Giới hạn quyền của automation

Deployer identity chỉ nên tạo/sửa **approved exception resources** ở scope được cấp, không thể tự gán IAM admin, sửa log retention hay mở firewall mọi nơi. Khi APIs chỉ hỗ trợ wildcard resource, phải dùng **account/project isolation, policy broker/guardrail và review** thay vì nghĩ một tên role "egress-deployer" đủ bảo vệ.

### 16.2. Điều kiện triển khai

- Plan artifact/hệ rule khớp **approval digest và môi trường**.
- Nguồn, đích, protocol, IPv4/IPv6 và NAT/proxy path đã đối chiếu.
- Có **auto-revoke mechanism** đang hoạt động; scheduler/permissions không bị missing.
- Có alert khi expiry sắp đến và khi revoke thất bại.
- Có **rollback, negative tests, owner/approver/contact và change window**.

## 17. Hợp đồng ngoại lệ YAML minh họa

~~~yaml
# PSEUDOCODE. KHÔNG áp trực tiếp cho Kubernetes, AWS, Azure, GCP.
api_version: "training.example/v1"
kind: "TimeBoundEgressException"
metadata:
  exception_id: "EGX-EXAMPLE-0042"
  change_id: "CHG-EXAMPLE-42"
  environment: "production"
  revision: 3
  owner: "analytics-platform"
spec:
  business_reason: "Export anonymized batch to an approved partner sandbox"
  risk_class: "R3"
  source:
    cluster: "prod-cluster-a"
    namespace: "analytics"
    workload_service_account: "export-job"
    cloud_account_scope: "prod-analytics"
  destination:
    fqdn: "ingest.partner.example"
    tls_server_identity: "ingest.partner.example"
    allowed_ips: []   # Resolver/controller phải kiểm tra provider support
    tenant_or_account: "approved-vendor-sandbox"
  transport:
    protocol: "TCP"
    destination_port: 443
    application_protocol: "HTTPS"
    allow_quic_udp_443: false
  application:
    methods: ["POST"]
    paths: ["/v1/batches"]
  data:
    classification: "anonymized-aggregates"
    pii_allowed: false
    secret_material_allowed: false
    max_total_mib: 50
  window:
    not_before: "2026-11-28T10:00:00Z"
    expires_at: "2026-11-28T12:00:00Z"
    maximum_duration_minutes: 120
  approval:
    workflow_record: "approval-example-109"
    required_roles:
      - "business-owner"
      - "data-owner"
      - "network-security"
    policy_digest_sha256: "EXAMPLE_DIGEST_REPLACE_WITH_REAL_VALUE"
    verified_outside_client_payload: true
  deployment:
    egress_gateway: "shared-egress-proxy-prod"
    direct_to_internet_blocked: true
    disable_traffic_logging: false
  revocation:
    schedule_before_activation: true
    deny_new_flows_after_expiry: true
    active_session_handling: "terminate_when_supported"
    verify_and_alert_on_failure: true
~~~

**Mẫu này là hợp đồng logic, không phải CustomResourceDefinition đã có controller.** Không đưa vào cluster và kỳ vọng tự enforce. Field **data.max_total_mib** hoặc **application.paths** chỉ có hiệu lực nếu proxy/DLP thực sự đếm và phân tích được nội dung; và **policy_digest_sha256** phải được tính, ký/đối chiếu bởi workflow đáng tin, không lấy chuỗi tự khai của requester.

### 17.1. Tách approval record khỏi YAML do requester chỉnh

Request chứa **approval reference**, còn kết quả phê duyệt phải được xác minh từ workflow **bên ngoài vùng requester có thể tự sửa**. Không dùng **verified_outside_client_payload: true** tự khai trong tài liệu làm bằng chứng; nó chỉ nhắc controller rằng phải làm bước kiểm chứng đó.

### 17.2. Chống rò thông tin qua manifest/ticket

Manifest có thể chứa thông tin topology, endpoint vendor, nhãn dữ liệu và lịch trực. Bảo vệ quyền đọc repo/ticket, không lưu API key, cookie, customer records hoặc sample payload chứa dữ liệu thật vào policy.

## 18. Thuật toán validate và quyết định trước apply

Controller phải từ chối request thiếu thẩm quyền, hủy/chỉnh sau duyệt hoặc vượt ranh giới dữ liệu, kể cả khi YAML parse thành công.

~~~text
function validate(exception, trustedContext):
  require exact supported schema version
  require immutable exception ID and version
  require authenticated requester and current business owner
  require approved source inventory and verified workload identity
  require destination and protocol supported by enforcement platform
  require data owner confirmation for restricted transfer
  require valid not_before < expires_at
  require allowed duration <= risk_class maximum
  require trusted approval records with independent approvers
  require approver entitlement valid for request scope
  require canonical policy digest matches approved digest
  require policy has no unapproved wildcard / broad CIDR
  require valid firewall/proxy/DLP path and logging obligations
  require auto-revocation scheduled and monitoring active
  require no explicit security deny, incident quarantine, or revoked approval
  return ACCEPT_FOR_DEPLOYMENT

function onExpiry(exception):
  idempotently mark REVOKING
  remove exact exception-owned rule/reference from PEPs
  handle existing sessions according to required closure SLO
  verify effective policy plus safe negative connectivity tests
  if verified: mark CLOSED_VERIFIED
  else: mark REVOCATION_FAILED; alert security owner; retry/escalate
~~~

**Đây là pseudocode, không phải một controller hoàn chỉnh.** Khi triển khai cần thêm **concurrency control, atomicity/compensation, leader election, persistent queues, signature verification, idempotency, retry/backoff, rollout versioning và audit integrity**.

### 18.1. Không chỉ dựa vào một cron job

Nếu scheduler chết lúc expiry, rule có thể tồn tại vô thời hạn. Dùng **durable job queue, watchdog kiểm tra overdue exceptions, reconciliation loop so desired vs actual và độc lập alert**. Với policy engine hỗ trợ **native expiration** theo thời gian đáng tin, có thể giảm rủi ro nhưng vẫn phải chứng minh effective enforcement.

### 18.2. Race conditions

- Request hết hạn đúng lúc deployment bắt đầu → **không apply** policy mới.
- Một approval bị thu hồi sau plan → kiểm tra lại **ngay trước mutation**.
- Gia hạn và revoke đồng thời → chọn **revision/sequence number**, không để revoke cũ xóa ngoại lệ mới hoặc renew cũ ghi đè deny.
- Apply một phần đến nhiều PEPs → rollback/compensate, không báo ACTIVE toàn hệ.
- Controller chạy lại sau crash → xử lý **idempotent** bằng exception ID + revision.
- Một PEP vùng B offline → không im lặng đánh dấu đã đóng tất cả.

## 19. Ví dụ policy-as-code với OPA/Rego

Rego có thể dùng để **kiểm tra điều kiện phê duyệt trước deploy**. Nó không tự thêm hoặc xóa rule mạng; CI/controller cần dùng kết quả và phải xác minh nguồn input.

~~~rego
package egress.exception

import rego.v1

default allow := false

allow if {
    input.request.environment == "production"
    input.request.source_namespace == "analytics"
    input.request.source_service_account == "export-job"

    input.request.destination_host == "ingest.partner.example"
    input.request.destination_port == 443
    input.request.transport == "TCP"

    input.request.data_classification == "anonymized-aggregates"
    input.request.requires_dlp == true

    input.approval.verified_by_trusted_workflow == true
    input.approval.independent_approvers == true
    input.approval.policy_digest == input.request.policy_digest
    input.approval.risk_class == "R3"

    input.server_time_ns >= input.request.not_before_ns
    input.server_time_ns < input.request.expires_at_ns
    input.request.duration_minutes <= 120

    input.enforcement.egress_gateway_healthy == true
    input.enforcement.direct_internet_blocked == true
    input.enforcement.revocation_job_registered == true
    input.enforcement.audit_pipeline_healthy == true
}
~~~

**Đây là policy đào tạo**, với các trường normalized số/thời gian được tính và xác minh **server-side**. Requester không được tự đưa **verified_by_trusted_workflow=true, direct_internet_blocked=true hoặc server_time_ns** rồi coi là sự thật. OPA trả boolean **allow**, còn việc **grant/revoke** cần pipeline và controller thực thi.

### 19.1. Những gì policy này chưa kiểm tra hết

- Signature/provenance của approval và approver entitlement được kiểm tra ở thành phần ngoài.
- Policy không tự resolve DNS, kiểm tra TLS SAN, DLP payload hay status connection.
- Một **ALLOW từ Rego không có nghĩa cloud firewall đã mở**, cũng không chứng minh data transfer được phép.
- Khi có explicit deny khác hoặc risk state thay đổi, cần reconciliation và ràng buộc policy precedence.
- Không nên gọi OPA rule với input raw client untrusted.

## 20. GitOps và IaC: phê duyệt trước thay đổi mạng

Một quy trình có thể dùng GitOps/CI với protected branches:

1. Requester nộp **structured exception spec**, ticket, owner và duration.
2. Validator kiểm tra schema, CIDR, destination, risk, TTL cap và DLP applicability.
3. Code reviewer/data owner/security approver **duyệt đúng digest**.
4. Protected pipeline lấy short-lived deployment identity, **kiểm tra approval ngay trước apply**.
5. Tạo các rule có **tag/metadata exception_id, owner, expiry, policy_version** khi PEP hỗ trợ.
6. Reconciler lên lịch auto-expiry độc lập với việc CI còn hoạt động.
7. Kiểm thử ALLOW/DENY có phép, ghi audit/flow logs và giám sát lệch cấu hình.
8. Hết hạn: xóa/quay lại baseline, verify new flows deny và xử lý active flows.
9. Post-review nếu gia hạn/emergency và dọn orphaned resources.

### 20.1. IaC plan không tự chứng minh end-to-end enforcement

Một Terraform/OpenTofu/CloudFormation/Bicep plan có thể cho thấy **SG rule và firewall config thay đổi**, nhưng không chứng minh **route luôn đi qua egress proxy, DNS có policy, DLP đang hoạt động hoặc bypass đã bị chặn**. Cần kiểm thử thực ở data plane.

### 20.2. State và bí mật

IaC state/plan/logs có thể chứa topology và dữ liệu nhạy cảm. Áp **encrypted storage, RBAC, locking, short-lived CI credentials và audit**; không nhúng vendor credentials hoặc payload thực vào manifest.

## 21. Lớp firewall L3/L4 và egress proxy L7

| Cơ chế | Có thể enforce | Không tự enforce |
|---|---|---|
| **Cloud SG/NSG/firewall L3/L4** | Source/destination IP, port, protocol, zone theo implementation | HTTP URL, tenant, nội dung TLS |
| **Secure web gateway / HTTP proxy** | Host/URL/method/certificate/categorization theo sản phẩm | Mọi non-HTTP protocol và mọi traffic bypass |
| **Egress gateway/service mesh** | Workload identity, destination/service access và TLS policies theo implementation | User object permission và toàn bộ encrypted payload |
| **DLP engine** | Phân loại/regex/fingerprint/sensitive patterns theo coverage | Không bảo đảm thấy dữ liệu nếu end-to-end encryption không được kiểm tra |
| **Application/API control** | User/tenant, data export action, content schema | Không ngăn tất cả direct network paths ngoài kiến trúc |
| **DNS policy** | Resolver/đích truy vấn, domain categories | Không tự chặn kết nối trực tiếp IP hoặc encrypted DNS ngoài kiểm soát |
| **Endpoint EDR/DLP** | Hoạt động process/file/agent được hỗ trợ | Không bảo đảm mọi headless server/container có agent |

### 21.1. Không mở cả port 443 chỉ vì traffic được mã hóa

HTTPS che payload khỏi nhiều firewall mạng; attacker vẫn có thể upload file nhạy cảm qua POST tới một host đã cho phép. DLP và app authorization phải kiểm soát **loại dữ liệu, tài khoản đích, API operation và volume** nếu use case đòi hỏi.

### 21.2. Nếu cần inspect TLS

**TLS interception/decryption** có thể cung cấp DLP visibility nhưng tạo rủi ro về **private key/trust, dữ liệu cá nhân, latency, certificate pinning, mTLS và pháp lý**. Chỉ thực hiện theo policy được phê duyệt, có exclusions và bảo vệ log; không mặc định bật giải mã cho mọi ứng dụng hoặc hạ cấp TLS để quan sát.

### 21.3. Không chỉ có TCP

Ứng dụng có thể dùng **UDP/443 QUIC, DNS over HTTPS, raw TCP, SFTP, cloud storage SDK hoặc message queue**. Một ngoại lệ TCP/443 không mặc nhiên cấp UDP/443; ngược lại chặn TCP có thể không chặn traffic qua UDP nếu firewall còn allow. Kiểm kê ứng dụng giao thức thực tế.

## 22. Kubernetes egress exception và giới hạn NetworkPolicy

**Kubernetes NetworkPolicy chuẩn** hỗ trợ selectors, IP blocks, protocol/port theo CNI. Nó **không có field chuẩn để đặt expires_at, approver, FQDN allowlist, HTTP path hay DLP content rule**.

~~~yaml
# VÍ DỤ LAB: chỉ cho Pod app=export-job gửi TCP 443
# tới dải IP tài liệu TEST-NET 192.0.2.0/24.
# Không áp dụng CIDR này cho vendor thật.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: temp-egress-via-approved-test-network
  namespace: analytics
spec:
  podSelector:
    matchLabels:
      app: export-job
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 192.0.2.0/24
      ports:
        - protocol: TCP
          port: 443
~~~

**Đây chưa phải một time-bound exception production.** Nó không chọn ServiceAccount trực tiếp theo NetworkPolicy chuẩn; chọn bằng **Pod labels** có thể bị lạm dụng nếu actor có quyền chỉnh labels. Nó không có automatic expiry, FQDN, DLP, HTTPS method hay TLS validation. Thêm external approval controller và CNI/egress gateway có khả năng tương ứng.

### 22.1. NetworkPolicy chuẩn không mặc định chặn mọi egress

Nếu không có egress isolation cho Pod, tạo một allow policy hẹp **không tự deny tất cả những đường khác**. Cần **default-deny egress** được CNI enforce cộng với explicit allow theo workload, cùng NetworkPolicy khác có thể additively ALLOW. Phải kiểm tra effective policy của từng Pod và đường hostNetwork/node.

### 22.2. CNI extensions khác NetworkPolicy chuẩn

Một số CNI hỗ trợ **FQDN policies, service-aware selectors, GlobalNetworkPolicy hoặc L7 policy**. Đây là **extension vendor-specific**, cần biết version, DNS TTL handling, policy selector semantics, dataplane và ability to revoke active flows. Không copy một CRD từ Cilium/Calico sang cluster khác rồi kỳ vọng được enforce.

### 22.3. Source workload identity và Pod labels

Nếu ngoại lệ dành cho **ServiceAccount export-job**, đừng coi label **app=export-job** là chứng cứ cryptographic identity. Kết hợp **admission, namespace RBAC, serviceAccountName restrictions, workload mTLS, CNI selectors theo hỗ trợ và proxy identity**.

### 22.4. DNS của Pod cần đường riêng

Default-deny egress có thể cắt **CoreDNS/NodeLocal DNSCache**. Policy DNS nên cho đúng resolver (TCP/UDP 53) theo topology, không cho toàn Internet DNS. Cẩn trọng khi dùng FQDN policies: resolver bị bypass hoặc DNS response được tạo giả có thể ảnh hưởng enforcement nếu CNI/proxy chưa ràng buộc.

## 23. Cloud egress và IAM của tài nguyên điều khiển

Cloud controls có nhiều lớp tùy AWS/Azure/Google Cloud/implementation:

| Lớp | Ví dụ | Cần hạn chế gì? |
|---|---|---|
| **VPC/VNet route** | Default route → NAT, firewall, transit | Không bypass central inspection |
| **Security group/NSG** | L4 outbound allow/deny trong scope | Source/port/destination quá rộng |
| **Cloud network firewall** | L3/L4, domain/application rules tùy product | Domain/IPv6/protocol semantics |
| **NAT gateway/egress IP** | Source IP cố định cho đối tác | Egress IP không là workload identity |
| **Proxy/secure web gateway** | HTTP domain/method/DLP | Bypass/direct egress |
| **Cloud IAM/RBAC** | Ai được sửa firewall, route, SG/NSG | Tự mở rule hoặc tắt logs |
| **Cloud audit/flow logs** | API mutations và traffic metadata | Sai lầm nghĩ audit API bằng packet log |
| **Private endpoint** | Gọi cloud service qua đường riêng | Service IAM, endpoint policy, DNS và resource access |

### 23.1. AWS

- Security group egress có thể giới hạn destination theo IP/CIDR, security group hoặc prefix list trong những trường hợp hỗ trợ; **không phải HTTP FQDN allowlist**.
- Nếu cần domain-aware filtering, xem **AWS Network Firewall, DNS Firewall hoặc proxy** theo chức năng thực và version.
- Kiểm tra **VPC route tables, NAT, IPv6 egress-only Internet gateway, VPC endpoints, Transit Gateway** để tránh route không đi qua inspection.
- CloudTrail/Config giúp biết ai sửa policy, **VPC Flow Logs** giúp xem flow metadata; không thay DLP content inspection.
- Kiểm soát IAM actions sửa SG/route/firewall, role assumption và CI permissions để không tự mở ngoại lệ.

### 23.2. Azure

- **Azure Firewall** có application/network rule mechanisms theo loại traffic; **NSG** chủ yếu là L3/L4, không tự hiểu HTTP method hoặc DLP payload.
- Review UDR/route, NAT, private endpoint, application gateway/proxy và DNS khi cần hạn FQDN.
- Đảm bảo role Azure RBAC **Network Contributor/Owner** không được cấp quá rộng cho requester chỉ cần một exception.
- Azure Activity Log ghi control-plane changes; flow/network logs cần nguồn telemetry phù hợp và cập nhật theo dịch vụ hiện hành.

### 23.3. Google Cloud

- Cloud VPC firewall rules và các khả năng domain/FQDN filtering phụ thuộc dịch vụ/phiên bản. Không mặc định một firewall rule truyền thống hỗ trợ FQDN, TLS inspection hoặc expiry.
- Kiểm tra **Cloud NAT, routes, Private Google Access, private service connectivity, firewall policies và DNS**, tránh traffic đi ra qua đường không giám sát.
- GCP IAM bindings cho network resources và service accounts phải ngăn requester tự sửa policy hoặc impersonate deploy identity.
- **Cloud Audit Logs, VPC Flow Logs** phục vụ các câu hỏi khác nhau; đánh giá product-specific coverage.

### 23.4. Không copy policy syntax giữa clouds

AWS SCP, Azure Policy/RBAC và GCP Org Policy có semantics khác nhau; **guardrail không tự là permission allow**, và không phải action nào hỗ trợ resource-level condition. Thiết kế theo **security intent và test hiệu lực**, rồi dịch đúng provider.

## 24. FQDN, DNS, SNI, TLS và destination identity

**FQDN allowlist** thường hữu ích hơn CIDR rất rộng khi cần API của một đối tác, nhưng có nhiều giới hạn cần hiểu.

### 24.1. Những tên khác nhau xuất hiện trong một kết nối

| Trường | Ví dụ | Ai kiểm soát/quan sát? |
|---|---|---|
| DNS QNAME | ingest.partner.example | Resolver/client; cần trusted DNS path |
| DNS answer | 203.0.113.10 | Resolver/CDN; IP có thể đổi |
| TCP destination | 203.0.113.10:443 | Firewall L3/L4 nhìn thấy |
| TLS SNI | ingest.partner.example | ClientHello nếu còn quan sát được; có trường hợp ECH |
| Certificate SAN | ingest.partner.example | TLS peer validation; interception tùy design |
| HTTP Host / :authority | ingest.partner.example | L7 proxy khi có visibility |
| HTTP path | /v1/batches | L7 proxy/app, không hiện ở L3 firewall |
| SaaS tenant/account | vendor-sandbox-account | App/API/provider authorization |

**Không mặc định chúng đều trùng nhau.** Redirect, CDN, CNAME, IP shared hosting, HTTP proxy và TLS termination tạo khác biệt.

### 24.2. DNS record và CDN có thể thay IP

Nếu một rule chỉ ghi IP hiện tại và bỏ qua DNS TTL/capacity của vendor, một ngày sau vendor đổi IP làm ứng dụng lỗi. Nếu mở toàn CIDR chứa mọi tenants để tránh lỗi, có thể tạo đường data exfiltration không mong muốn. Giải pháp là **proxy domain/service-aware**, kiểm tra **TLS server identity và account/tenant**, hoặc cơ chế dynamic IP allowlist có nguồn và TTL được quản trị.

### 24.3. Chặn spoofing và alternate resolver

Một attacker có thể gọi direct IP, dùng **DoH/DoT hoặc resolver khác** nếu outbound DNS không được kiểm soát. Với hệ thống áp FQDN policy dựa DNS, phải bảo vệ **trusted resolver path, CNI integration và fallback semantics**; không chỉ có DNS allowlist đẹp trên dashboard.

### 24.4. SNI không tương đương hostname verification

**SNI** là giá trị do client khai trong TLS handshake, không phải bằng chứng destination đáng tin. Trong một số TLS thiết kế, **ECH** che thông tin SNI trong outer ClientHello; proxy truyền thống không được dựa vào khả năng đọc SNI mọi lúc. Thực thi destination identity phải xét **TLS certificate/server name, proxy authorization và data path** theo sản phẩm, không chỉ chữ SNI nhìn thấy.

### 24.5. IP ranges trong ví dụ

Các dải **192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24** là TEST-NET dùng cho tài liệu. Không sử dụng làm địa chỉ vendor thật. Nếu môi trường dual-stack, kiểm tra cả **IPv4 và IPv6**, DNS A/AAAA, ::/0 và đường egress tương ứng.

## 25. SaaS, cloud storage và các đích đòi danh tính ứng dụng

Một SaaS thường dùng domain/CDN hoặc public cloud IP chung với nhiều tenants. **Cho phép TCP 443 tới domain của nhà cung cấp không đảm bảo dữ liệu được gửi vào đúng tài khoản/tenant của doanh nghiệp**.

### 25.1. Bốn phép xác minh độc lập

1. **Network destination:** traffic có đi đến đúng dịch vụ/IP, qua PEP được kiểm soát không?
2. **TLS server identity:** hostname/certificate có được kiểm chứng? Có redirect sang host khác không?
3. **SaaS account/tenant:** API token/SSO role có bị giới hạn vào tenant được duyệt hay có thể gửi vào tài khoản cá nhân?
4. **Data and operation:** loại dữ liệu, object/bucket, HTTP method và quota có được phê duyệt không?

Ví dụ một exception cho **storage.cloud.example** phải phân biệt **bucket của tổ chức** với **bucket do cá nhân sở hữu**. Điều này cần **cloud IAM/bucket policies, service-specific endpoint policy, DLP hoặc API gateway**, không thể bảo đảm chỉ bằng danh sách hostname.

### 25.2. Redirect và chuỗi domain

Một API có thể trả redirect sang CDN/object storage. Không mặc định **cho phép toàn bộ wildcard** chỉ vì API ban đầu trả 302. Rà soát **hostnames, certificate chain, redirect destinations, data sent to each hop**, rồi phê duyệt từng domain hoặc sử dụng proxy có khả năng theo dõi redirect an toàn.

### 25.3. Artifact download khác data upload

Nhu cầu **GET bản vá đã ký** khác với **POST/PUT dữ liệu production**. Nếu proxy kiểm tra được HTTP method, có thể chỉ cho GET/HEAD tới mirror; nếu không, buộc phải dùng **repository mirror nội bộ**, artifact signing/provenance và outbound controls khác thay vì ghi trong ticket "GET-only" mà PEP không hiểu.

## 26. DLP là rào thứ hai, không phải phần ghi chú

Một exception có thể hợp lệ ở mức network nhưng **không hợp lệ ở mức dữ liệu**. Ví dụ dịch vụ export-job được phép kết nối vendor qua HTTPS nhưng vẫn phải từ chối upload **customer SSN, API keys, database backups hoặc source code bí mật** nếu chúng nằm ngoài data classification được phê duyệt.

### 26.1. Phân loại dữ liệu trước ngoại lệ

| Data class minh họa | Ví dụ | Điều kiện egress |
|---|---|---|
| **Public** | Dữ liệu quảng cáo công khai | Resource/network policy thông thường |
| **Internal** | Telemetry tổng hợp không nhạy cảm | Business owner và destination hợp lệ |
| **Confidential** | Chiến lược kinh doanh, source code nội bộ | Security review, encryption, destination trust |
| **Restricted/regulated** | PII, hồ sơ tài chính, secrets, backups | Data owner approval, DLP, purpose/retention controls |
| **De-identified aggregate** | Số liệu tổng hợp đã đánh giá rủi ro tái nhận diện | Verified anonymization + bounded transfer |

**Tên nhãn không tự chứng minh dữ liệu an toàn.** Cần tiêu chuẩn phân loại/ẩn danh và evidence thực; dữ liệu được hash/pseudonymize vẫn có thể có rủi ro tái nhận diện.

### 26.2. Các kỹ thuật DLP có thể kết hợp

- **Content inspection/classification** ở điểm có quyền xem plaintext hoặc dữ liệu trước mã hóa.
- **Exact data matching/fingerprinting** theo khả năng sản phẩm, với quy trình bảo vệ dữ liệu mẫu.
- **Secrets detection** cho tokens/keys và patterns, giảm false positives.
- **File type/size, upload method, destination account/tenant**.
- **Redaction/masking/anonymization** trước khi truyền; xác minh bằng automated tests.
- **Object-storage IAM, bucket policies, encryption, retention/expiry**.
- **Quota/rate budgets** để phát hiện khối lượng chuyển bất thường, không coi đó là bảo đảm không exfil.
- **App-level export authorization** cho user, tenant, object, purpose.

### 26.3. DLP bypass bởi mã hóa và protocol

Một L3 firewall không thể kiểm tra nội dung HTTPS; một HTTP proxy không nhất thiết giải mã được **mTLS, certificate-pinned clients, gRPC, QUIC hoặc custom encryption**. Nếu inspection không khả thi, thay đổi thiết kế: **app-side DLP trước upload**, data pipeline riêng, approved storage destination, token/account scoping hoặc yêu cầu đường kết nối phù hợp.

**Không yêu cầu hạ cấp TLS hoặc bỏ certificate validation để "cho DLP thấy dữ liệu".** Mọi TLS interception phải được quản trị về privacy, crypto trust, pháp lý và security operations.

### 26.4. DLP exception khác egress exception

Đôi khi network baseline đã cho phép SaaS nhưng DLP chặn upload **restricted data**. Nếu cần ngoại lệ DLP, đó là **quyết định riêng** cần data owner, purpose, classification, legal basis và controls; không tự mở DLP chỉ vì network exception đã được duyệt.

## 27. Security event log, tính toàn vẹn và tương quan

Ngoại lệ được kiểm soát chỉ khi có thể trả lời:

- **Ai yêu cầu và ai duyệt?** Verified requester/approvers với quyền tại thời điểm duyệt.
- **Đã duyệt bản nào?** Policy hash, version, source, destination, protocol, data class, window.
- **Ai apply?** Deployer identity, pipeline run, controller event và API audit.
- **Traffic nào thực đi qua?** Source principal, flow bytes, destination, host/TLS information nếu có, result và DLP decision.
- **Khi nào hết hạn?** Timestamps tạo, duyệt, apply, expire, revoke và verified close.
- **Có drift hoặc bypass?** Actual route/firewall/proxy state, nonexception allow policies và negative tests.

### 27.1. Schema sự kiện ngoại lệ minh họa

~~~json
{
  "schema_version": "1.0",
  "event_type": "EGRESS_EXCEPTION_ENFORCEMENT",
  "event_time": "2026-11-28T12:00:15.120Z",
  "ingest_time": "2026-11-28T12:00:17.350Z",
  "exception_id": "EGX-EXAMPLE-0042",
  "change_id": "CHG-EXAMPLE-42",
  "policy_revision": 3,
  "policy_digest": "sha256:example-not-a-real-digest",
  "environment": "production",
  "source_identity": "spiffe://prod.example/ns/analytics/sa/export-job",
  "destination": "ingest.partner.example",
  "destination_port": 443,
  "transport_protocol": "TCP",
  "approved_by": ["business-owner-1", "data-owner-2", "netsec-3"],
  "expires_at": "2026-11-28T12:00:00Z",
  "controller_action": "REVOKE",
  "pep_id": "egress-gateway-prod-a",
  "enforcement_revision": "egress-config-r17",
  "verified_new_flow_result": "DENY",
  "existing_session_status": "REMEDIATION_IN_PROGRESS",
  "closure_status": "PENDING_ACTIVE_SESSION_CHECK",
  "reason_codes": ["TIME_WINDOW_EXPIRED"]
}
~~~

**Schema minh họa**, không phải log native của một cloud/proxy. Với một sự kiện đóng, đừng ghi **closure_status=CLOSED_VERIFIED** khi active flows còn chưa kiểm tra. Dùng trạng thái và nguồn bằng chứng riêng.

### 27.2. Event time khác ingest time

Một cảnh báo đến trễ không có nghĩa policy bị vi phạm sau expiry; cần so **thời điểm phát sinh flow/decision, thời điểm controller revoke, thời điểm PEP nhận revision và thời điểm log được ingest**. Có thể có clock skew và asynchronous queues. Timeline cần ghi uncertainty.

### 27.3. Không ghi secrets và payload nhạy cảm

Không export **access token, cookie, TLS private key, API key, request body/customer records, full URL query có secret** sang SIEM chỉ để audit egress. Dùng **metadata, classification, bytes, fingerprint được phép lưu, exception ID và policy decision** theo retention/RBAC.

### 27.4. Bảo vệ log sink

Network deployer không nên có quyền **DeleteAuditLog, StopLogging hoặc đổi retention/sink** ngoài policy. Tách IAM/log pipeline, central archive và alert khi collector không hoạt động. **Không có traffic log không chứng minh không có transfer**.

## 28. Detection engineering cho ngoại lệ có hạn

| Detection hypothesis | Tín hiệu | Cần phân biệt |
|---|---|---|
| **Ngoại lệ ACTIVE sau expiry** | expires_at đã qua, actual rule còn allow | Clock/propagation delay được đo |
| **Rule rộng hơn approval** | Actual CIDR/port khác policy digest | IaC drift hoặc emergency đã duyệt |
| **Self-approval/role conflict** | requester=approver/deployer cùng quyền | Compensating control nếu có |
| **Renewal không phê duyệt** | expires_at đổi mà approval revision không đổi | Admin hotfix được review? |
| **Bypass direct-to-Internet** | Flow ra NAT/direct ngoài egress proxy | Health checks hoặc đường legacy |
| **DLP block trên exception** | Proxy ALLOW nhưng DLP DENY sensitive upload | False positive hoặc dữ liệu không thuộc scope |
| **Data volume vượt budget** | Bytes/requests > approved envelope | Retry hoặc response payload tăng |
| **Destination ngoài allowlist** | TLS host/IP/CNAME/redirect khác baseline | Vendor endpoint đổi hợp lệ |
| **DNS queries lạ** | Domain entropy/volume tăng từ source | Legit telemetry/update agent |
| **QUIC hoặc IPv6 bypass** | UDP 443/AAAA path ngoài rule | Legit client upgrade chưa được duyệt |
| **Source identity drift** | Một SA/Pod ngoài scope dùng exception | Shared labels/role compromise |
| **Approver entitlement không hợp lệ** | Approval từ account không có role | Workflow bug hoặc role lifecycle |
| **Controller expiry job missing** | ACTIVE mà không có schedule/watchdog | Provisioning race hoặc scheduler outage |
| **Logging gap during exception** | Ingest lag/heartbeat missing | Collector maintenance |
| **Repeated emergency exceptions** | Nhiều break-glass cho cùng source/dest | Baseline design/operational debt |
| **Connection persists after revoke** | Established flow còn bytes sau expiry | Conntrack handling / active job |

### 28.1. Đếm ngoại lệ không đủ đo rủi ro

Một đội có 50 ngoại lệ **R1 dev 15 phút** có thể ít rủi ro hơn một ngoại lệ **R4 production all destinations**. Dashboard nên phân nhóm theo **risk class, source sensitivity, egress destination, classification và aggregate exposure time**.

### 28.2. Không suy ý đồ tấn công từ một sự kiện

Những bản ghi **DLP BLOCK, high DNS entropy, unexpected vendor IP** có thể do automation/redirect/retries hợp lệ. Hãy dùng ticket, approver, change window, app logs, proxy/flow logs để phân biệt, và ghi **confidence/known limitations** trong alert.

## 29. Kiểm tra chỉ đọc: Kubernetes, AWS, Azure, Google Cloud

Ví dụ chỉ phục vụ **diagnostics theo quyền được cấp**, không sửa resource. Không chạy thử access tới đích thật nếu không được phép. Một số lệnh list có thể phơi bày topology hoặc tags nên cần bảo vệ output.

### 29.1. Kubernetes / CNI

~~~bash
kubectl config current-context
kubectl get namespaces
kubectl get networkpolicies --all-namespaces
kubectl get networkpolicy temp-egress-via-approved-test-network \
  -n analytics -o yaml
kubectl get pods -n analytics -l app=export-job -o wide
kubectl get serviceaccounts -n analytics

# Kiểm tra quyền K8s hiện tại; không tạo policy.
kubectl auth can-i get networkpolicies -n analytics
kubectl auth can-i patch networkpolicies -n analytics
~~~

**Giới hạn:** object NetworkPolicy tồn tại không bảo đảm CNI đang thực thi, và có thể có **policy khác additively ALLOW**; CNI-specific FQDN/global rules cũng cần kiểm tra theo product/version.

### 29.2. AWS CLI

~~~bash
aws sts get-caller-identity
aws ec2 describe-security-groups --region us-east-1
aws ec2 describe-route-tables --region us-east-1
aws ec2 describe-vpc-endpoints --region us-east-1
aws ec2 describe-flow-logs --region us-east-1

# Read-only CloudTrail Event History; phạm vi/timestamps có giới hạn.
aws cloudtrail lookup-events --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AuthorizeSecurityGroupEgress
~~~

**Giới hạn:** AWS Describe API thường chỉ show **configured state**, không chứng minh tất cả paths/flows hoặc DLP content. CloudTrail lookup có phạm vi event type/region/time nhất định, không thay org-wide audit store.

### 29.3. Azure CLI

~~~bash
az account show
az network nsg list --resource-group example-network-rg
az network route-table list --resource-group example-network-rg
az network firewall list --resource-group example-network-rg
az monitor activity-log list --max-events 20
~~~

Thay resource group bằng phạm vi đã được cấp; **không gán Network Contributor hoặc mở NSG outbound** để sửa lỗi thiếu quyền đọc.

### 29.4. Google Cloud CLI

~~~bash
gcloud config get-value project
gcloud auth list
gcloud compute firewall-rules list --project=example-project-id
gcloud compute routes list --project=example-project-id
gcloud logging read \
  'logName:"cloudaudit.googleapis.com%2Factivity"' \
  --project=example-project-id --limit=20
~~~

**Giới hạn:** firewall/route list không thể hiện toàn bộ effective organization/folder-level policies hoặc TLS inspection. Kiểm tra hierarchy, DNS, NAT, service accounts và cloud audit khi thật sự cần.

### 29.5. Những phép xác minh cần traffic có chủ đích

Để chứng minh **ALLOW trước expiry, DENY sau expiry**, có thể dùng một **canary Pod/VM và test endpoint** do tổ chức quản lý, với script health test giới hạn số requests và không chứa dữ liệu nhạy cảm. Việc gửi traffic vẫn phải nằm trong change/test plan. Không chạy **port scans, brute force, uploads chứa dữ liệu thật** hoặc tạo firewall mutations ngoài scope để "thử".

## 30. Chỉ số đo lường, SLO và dashboard

| Chỉ số | Cách đo | Mục tiêu thực chất |
|---|---|---|
| **Time-bounded coverage** | % ACTIVE exceptions có expires_at + job revoke | Không tồn tại ngoại lệ mồ côi |
| **Approval integrity** | % exceptions gắn đúng approver/digest | Chống self-approval |
| **Scope compliance** | Actual source/dest/protocol so approved intent | Không có rule rộng hơn |
| **Activation delay** | approved/effective_from → actual active verified | Biết readiness và downtime |
| **Expiry-to-deny latency** | expires_at → verified deny of new flows | Đóng đúng giờ |
| **Active-session termination lag** | revoke → không còn active bytes/flows theo SLO | Không để transfer kéo dài |
| **Reconciliation error rate** | Failed/pending/partial PEP updates | Controller reliability |
| **Overdue ACTIVE exceptions** | exceptions past expiry yet still enforce allow | Alert ưu tiên |
| **Renewal rate** | Tỷ lệ và số lần gia hạn | Phát hiện baseline design debt |
| **Emergency exception rate** | Break-glass theo risk/team | Review lạm dụng |
| **DLP override frequency** | DLP exception theo data class | Không giấu dữ liệu nhạy cảm |
| **Data volume per exception** | Transfer bytes/approved budget | Điều tra chuyển dữ liệu vượt dự kiến |
| **Bypass coverage** | % protected sources bị block direct egress | Đo defense in depth |
| **Telemetry integrity** | Producer heartbeat, lag, dropped events | Không hiểu nhầm "không log" |
| **Operational impact** | False deny, SLI, support tickets | Không phá nhu cầu hợp lệ |

### 30.1. Tránh labels cardinality cao

Không đặt **exception_id, user_id, request_id, destination full URL hay token** làm label metric ở quy mô lớn khi không cần; dùng dimension như **risk class, environment, enforcement system, result**, còn đối tượng cụ thể nằm trong log có quyền truy cập.

### 30.2. SLO phải nói rõ điều kiện đo

"100% ngoại lệ hết hạn đúng giờ" không rõ liệu tính **ticket Closed** hay **đường mạng deny**. SLO nên đo **actual PEP effective state** và active-flow handling. Nếu test data-plane không chạy được ở mỗi lần hết hạn, ghi **coverage và confidence**, không tô thành PASS.

## 31. Review truy cập và loại bỏ ngoại lệ cũ

Một chương trình ngoại lệ tốt phải đánh giá cả **nợ kỹ thuật**:

- Exception nào được gia hạn nhiều lần và vì sao?
- Rule nào có **expired ticket nhưng vẫn có flow**?
- Destination nào được mở không còn ứng dụng nào dùng?
- Ai là approver/deployer, vai trò đó còn hợp lệ?
- Đối tác đã đổi hostname, cloud account, tenant hoặc certificate trust chưa?
- Application có thể dùng **vendor private link/approved SaaS connector** thay Internet egress trực tiếp không?
- Data transfer thật có nằm trong scope DLP đã chấp thuận?
- Có **duplicate/multiple allow paths** khiến xóa một rule không đóng được traffic không?
- Có exception nào nên **đưa vào baseline** sau architecture review thay vì gia hạn?
- Log retention, tags/owners và expiry alerts còn hoạt động không?

### 31.1. Không tự xóa mọi rule cũ mà không có change awareness

Một exception tồn tại sau expiry là **vi phạm cần xử lý**, nhưng việc xóa bừa giữa sự cố có thể ảnh hưởng production. Giải pháp đúng là **xác minh ownership, kiểm tra alternative allow paths, áp deny/rollback an toàn, ghi incident và hậu kiểm**; không để tình trạng chờ xem kéo dài vô thời hạn.

## 32. Runbook cấp ngoại lệ egress thông thường

### Bước 1 — Nêu nhu cầu và dữ liệu

Requester ghi **business outcome, app/owner, source identity, destination, protocol/port, dữ liệu, volume, access window, rollback**. Giải thích vì sao baseline không đáp ứng và tại sao không dùng **repository mirror, proxy hoặc sanctioned data transfer** hiện có.

### Bước 2 — Inventory trust path

Vẽ **source → CNI/host firewall → cloud route/NAT → egress proxy/firewall → DNS/TLS → vendor API**, xác định nơi enforce **source, host, method và DLP**. Rà IPv4/IPv6, QUIC, private endpoints, VPN và direct-to-origin bypass.

### Bước 3 — Đánh giá risk và approval

Xếp risk class dựa trên data classification, source criticality, destination trust, scope và duration. Xác minh approvers có quyền, độc lập và approval gắn đúng **canonical policy digest**.

### Bước 4 — Kiểm tra capability và rollback

Xác minh PEP có thể chặn **đúng destination/HTTP action** không, có thể terminate active flows theo SLO không, controller/expiry scheduler đang healthy không và có **negative tests**. Nếu thiếu khả năng enforcement quan trọng, **đề xuất thiết kế khác hoặc từ chối**, không tuyên bố allowlist đã an toàn.

### Bước 5 — Triển khai qua identity được bảo vệ

Protected pipeline triển khai đúng bản duyệt, gắn **exception ID, expiry, owner, policy revision**; lập lịch revoke trước khi active. Không cấp requester quyền firewall admin rộng.

### Bước 6 — Verify ACTIVE bằng positive/negative tests

Cho canary workload đúng scope gọi test endpoint được phép, xác minh traffic đi qua gateway/DLP; cho source ngoài allowlist hoặc destination ngoài phạm vi bị DENY. Bảo đảm không có đường direct IPv6/NodePort/NAT bypass.

### Bước 7 — Theo dõi trong thời gian mở

Monitor bytes, DLP decisions, unexpected destination, source identity drift, logging health, expiry sắp tới và owner acknowledgement. Nếu có dấu hiệu exfiltration, **early revoke** theo incident plan.

### Bước 8 — Đóng đúng hạn

Controller gỡ/revoke rule, xử lý active flows, kiểm chứng **new connections DENY** và các PEP/regions hết quyền; ghi timestamp thực. Nếu thất bại: **REVOCATION_FAILED**, alert SOC/NetSec và escalation.

### Bước 9 — Hậu kiểm

Lưu evidence đầy đủ, đánh giá data exposure, nguyên nhân gia hạn hoặc phát sinh drift; cleanup orphaned DNS/firewall/prefix lists/CI permissions có liên quan.

~~~mermaid
flowchart TD
    A[Request + source/dest/data + TTL] --> B[Risk + independent approval]
    B --> C[Policy digest + capability checks]
    C --> D[Deploy via protected CI]
    D --> E[ALLOW right path / DENY wrong path]
    E --> F[Monitor quota + DLP + expiry]
    F --> G[Auto revoke at deadline]
    G --> H{Data-plane deny and active flows resolved?}
    H -- Yes --> I[CLOSED_VERIFIED + evidence]
    H -- No --> J[REVOCATION_FAILED + escalation]
~~~

## 33. Runbook auto-expiry, renew và chứng minh đã đóng

### 33.1. Trước deadline

1. Controller tạo job revoke có **persistent ID/revision** ngay khi ngoại lệ được ACTIVE.
2. Có **watchdog độc lập** phát hiện exception ACTIVE quá expiry.
3. Owner được cảnh báo trước hạn nếu job cần kéo dài; **không auto-renew**.
4. Nếu muốn gia hạn, tạo approval/version mới **trước khi deadline**, theo risk; không sửa trực tiếp expires_at.
5. Giữ hệ thống sẵn sàng nếu job revoke bị retry, không tạo duplicate rules.

### 33.2. Tại deadline

1. Kiểm tra wall-clock UTC đáng tin, trạng thái **revoked/expired** và current revision.
2. Remove/disable **đúng rule exception-owned** ở tất cả relevant PEPs, không xóa baseline allow khác.
3. Xử lý active sessions/NAT/connection pools theo SLO và vendor capability.
4. Kiểm tra policy effective sau propagation.
5. Chạy safe negative test trên test source; nếu có allow path khác, ghi **result không chứng minh exception được đóng** và điều tra duplicate rules.
6. Kiểm tra data transfer jobs đang chạy và application-level permission.
7. Chuyển CLOSED_VERIFIED chỉ khi đầy đủ evidence.

### 33.3. Nếu revoke thất bại

- Tạo **REVOCATION_FAILED** với exception ID và PEPs affected, không báo thành công.
- Retry có backoff và **idempotent resource identifiers**; tránh xóa nhầm rule sau khi đã gia hạn có approval mới.
- Cảnh báo on-call/SOC, đánh giá impact/exposure.
- Có thể dùng **higher-level deny control, isolate source/gateway hoặc đóng relevant route** trong khuôn khổ incident change, ưu tiên biện pháp hẹp.
- Kiểm tra logging còn nguyên, lưu timeline/error codes.
- Đóng incident khi **actual data-plane access đã bị chặn** theo yêu cầu và được người phụ trách xác minh.

### 33.4. Khi có policy khác cũng allow

Nếu rule exception bị xóa nhưng baseline đã cho traffic tới destination, negative test vẫn ALLOW. Không thể báo "exception closed = data path blocked" nếu policy khác cho phép. Tách hai câu hỏi: **(a) exception grant đã được thu hồi? (b) đường không được phép còn accessible không?** Kiểm tra **effective policy** để kết luận đúng intent.

## 34. Runbook emergency và sự cố rò dữ liệu qua ngoại lệ

### 34.1. Emergency opening

Một incident nghiêm trọng cần vendor support kết nối outbound tạm thời:

- Incident commander mô tả **incident ID, source cụ thể, vendor destination, reason, expected payload, max duration**.
- Security on-call xác nhận risk và approve qua đường **break-glass đã định sẵn**, có audit độc lập.
- Automation mở policy **ngắn nhất có thể**, log đầy đủ và tạo job auto-revoke trước apply.
- Không mở **all destinations/protocols** khi chỉ cần vendor endpoint 443.
- Đánh dấu **emergency**, gửi alert tới SOC, chuẩn bị kill switch và post-review.
- Khi khôi phục, thu hồi và xác minh active flows; review liệu emergency cần chuyển thành baseline sanctioned connector hay không.

### 34.2. Sự cố nghi ngoại lệ bị dùng để exfiltration

**Tín hiệu:** DLP cảnh báo sensitive upload/bytes vượt budget khi exception production vẫn ACTIVE.

**Bước 1 — Xác nhận:** thu thập exception ID, approver, policy version, source principal, destination, DLP reason, flow timestamps, bytes và app operation. Phân biệt **blocked transfer** với **confirmed delivered bytes**.

**Bước 2 — Containment:** theo incident risk, **early revoke** bằng policy controller; hạn source route/egress gateway, chặn destination rõ ràng, ngăn credentials bị lạm dụng. Tránh xóa audit artifacts hoặc phá mọi production routes khi chưa cần.

**Bước 3 — Scope:** tìm **IPv4/IPv6, alternate host, QUIC, DNS, NAT, cloud storage account, mirror hostname và VPN route**; phân biệt traffic đã đi qua proxy và direct paths.

**Bước 4 — Data impact:** data owner/DLP đánh giá **đã gửi loại dữ liệu gì, tới tài khoản nào, số lượng, có được xác minh nhận hay không**. Network byte counters không tự chứng minh payload nhạy cảm.

**Bước 5 — Root cause:** kiểm tra request/approval, SoD, CI role/branch protection, FQDN/TLS mapping, controller TTL, policy drift và logging gaps.

**Bước 6 — Recovery:** khôi phục business flows theo exception mới nếu thật cần và đủ approvals; sửa architecture, tăng tests/detection, rotate compromised credentials theo scope, cập nhật runbook.

### 34.3. Không dùng emergency để né DLP

Nếu vendor support yêu cầu upload full customer DB, nên xem **số lượng/nhạy cảm dữ liệu, contract, data owner, legal/privacy obligations** và tìm phương án **mask/anonymize/sample** thay vì vô hiệu toàn bộ DLP. Emergency có thể rút ngắn approval workflow, **không loại bỏ trách nhiệm đối với dữ liệu**.

## 35. Mười hai tình huống thực tế

### A — Được duyệt một hostname nhưng firewall mở cả Internet

**Tình huống:** requester được duyệt TCP 443 đến **ingest.partner.example**, còn CI áp rule **0.0.0.0/0 TCP 443** để tránh lỗi DNS.

**Rủi ro:** workload có thể kết nối tới mọi endpoint HTTPS, kể cả dịch vụ lưu trữ cá nhân hoặc máy chủ không liên quan. **Destination CIDR 0.0.0.0/0 không tương đương FQDN allowlist**.

**Xử lý:** rollback rule quá rộng, kiểm tra vì sao provider không thể enforce FQDN, triển khai proxy domain-aware hoặc vendor endpoint design phù hợp, test direct-IP/IPv6 bypass; không gọi change là approved nếu digest/scope khác.

### B — Ticket Closed nhưng flow vẫn gửi bytes

**Tình huống:** rule egress đã bị gỡ lúc 12:00, song HTTP/2 connection tồn tại và tiếp tục gửi request sau 12:05.

**Nguyên nhân:** firewall stateful hoặc proxy connection pool không buộc đóng session đang tồn tại; ticket closure thiếu data-plane verification.

**Xử lý:** thiết kế **active session termination**, app job cutoff hoặc short-lived outbound connections theo PEP capability, đo **expiry-to-last-byte** thay vì chỉ timestamp xóa rule.

### C — Người yêu cầu tự duyệt qua quyền sửa workflow

**Tình huống:** một engineer không phải approver nhưng sửa GitHub/CI protected workflow để chèn field approved và deploy dưới role production.

**Nguyên nhân:** approval logic không nằm ngoài vùng requester có thể điều khiển; SoD chỉ tồn tại trên giấy.

**Xử lý:** gắn approval với trusted identity/role, canonical policy digest, bảo vệ repo/workflow/admin grants, kiểm tra vai trò ngay trước apply và audit thay đổi control plane.

### D — DNS của SaaS chuyển sang CDN IP mới

**Tình huống:** ngoại lệ IP allowlist chạy tốt hôm đầu nhưng vendor đổi CDN endpoint sau vài giờ, ứng dụng timeout.

**Rủi ro:** đội vận hành mở toàn dải cloud CIDR để chữa lỗi, vô tình tăng data exfiltration surface.

**Xử lý:** dùng **provider-backed FQDN policy hoặc trusted egress proxy** khi có khả năng, verify TLS identity, redirect behavior, DNS TTL và vendor-published destinations. Không tự coi SNI là certificate identity.

### E — Workload Pod dùng label để mạo danh source

**Tình huống:** NetworkPolicy cho Pod **app=export-job** đi ra; một team khác có quyền tạo Pod trong cùng namespace và gắn đúng label.

**Nguyên nhân:** label là thuộc tính Kubernetes có thể sửa bởi actor có quyền, không phải cryptographic identity.

**Xử lý:** bảo vệ namespace/RBAC/admission, kiểm tra ServiceAccount/workload identity ở egress gateway, dùng CNI selector rõ, tách namespace và test source trái quyền.

### F — Egress TCP 443 được phép, dữ liệu restricted bị upload

**Tình huống:** ứng dụng export authorized kết nối partner qua HTTPS nhưng gửi customer PII thay dữ liệu aggregate.

**Nguyên nhân:** network policy chỉ nhìn host/port; DLP/app export kiểm tra không có hoặc bị vô hiệu.

**Xử lý:** phối hợp data owner, xác minh content classification, masking/tenant/resource authorization, xét data impact, ngăn upload ngoài scope và điều tra xem có delivery thực.

### G — DLP báo blocked upload nhưng proxy vẫn ghi ALLOW connection

**Tình huống:** firewall cho TCP connection, proxy DLP chặn HTTP POST nhạy cảm.

**Diễn giải:** **ALLOW network** và **DENY data operation** không mâu thuẫn. Log phải ghi decision_source, HTTP operation và final disposition; chưa thể kết luận dữ liệu đã đến vendor.

### H — Exception chỉ áp IPv4, client dùng IPv6

**Tình huống:** egress proxy rule hạn host IPv4 nhưng node/pod vẫn có IPv6 route trực tiếp và firewall chưa kiểm soát **::/0**.

**Rủi ro:** traffic bypass PEP dù dashboard ngoại lệ báo chỉ allow một domain.

**Xử lý:** rà DNS AAAA, cloud IPv6 egress, Node route, CNI and host policy, IPv6 proxy coverage; test cả dual-stack sau revoke.

### I — Gia hạn trong lúc revoke job đang chạy

**Tình huống:** requester được phê duyệt gia hạn lúc 11:59 nhưng scheduler 12:00 đã bắt đầu xóa rule revision cũ.

**Nguyên nhân:** concurrent updates không có revision lock/atomic state transition, khiến rule bị xóa nhầm hoặc tiếp tục được allow ngoài approval.

**Xử lý:** controller dùng **exception ID + immutable revision, compare-and-swap, idempotent reconcile**, ghi rõ new approval effectivity và test state cuối trên tất cả PEPs.

### J — Cloud storage cùng domain nhưng sai bucket/tenant

**Tình huống:** outbound allow tới hostname dịch vụ lưu trữ cloud dùng chung; app token có thể PUT tới bucket ngoài doanh nghiệp.

**Nguyên nhân:** FQDN chỉ xác định service platform, không xác định customer account/tenant hoặc object.

**Xử lý:** hạn **cloud IAM, endpoint/resource policy, application credentials, bucket/account identity**, dùng DLP/app export controls; không chỉ mở đúng hostname.

### K — Emergency exception được gia hạn mãi

**Tình huống:** mỗi tuần có break-glass 30 phút đến cùng vendor API, với lý do "hỗ trợ production".

**Vấn đề:** đây có thể là nhu cầu thường xuyên bị quản lý như tình huống khẩn cấp, làm suy yếu review và tạo nợ kỹ thuật.

**Xử lý:** đo frequency, tổng thời gian mở, review threat model; đưa vào sanctioned connector/baseline thay vì evergreen emergency. Rà approver và evidence mỗi lần.

### L — Scheduler không hoạt động, rule vẫn ACTIVE sau expiry

**Tình huống:** outage của job scheduler khiến 23 ngoại lệ đã hết hạn không bị remove. Ticket workflow vẫn đánh Closed.

**Xử lý:** watchdog độc lập báo **overdue ACTIVE**, incident triage theo data risk, dùng controlled deny/reconciliation, kiểm chứng active sessions và các đường bypass; phục hồi durable scheduler và đo SLO. Không ghi "đã đóng" cho đến khi **enforced_closed_at** có bằng chứng.

## 36. Ma trận 48 kiểm thử ALLOW / DENY / EXPIRE / REVOKE

Các test sử dụng **source/endpoint lab được tổ chức cấp phép**, không tạo exfiltration thật, không gửi dữ liệu khách hàng, không quét public ranges và không thay firewall production ngoài change plan.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Request có requester, business owner, source, destination | ACCEPT_FOR_REVIEW | Schema validation |
| **T-02** | Thiếu expires_at | DENY request | Validation error |
| **T-03** | effective_from sau expires_at | DENY request | Time validation |
| **T-04** | TTL vượt risk maximum | DENY/escalation | Risk policy decision |
| **T-05** | Timestamp thiếu UTC/offset | DENY hoặc chuẩn hóa có kiểm chứng | Canonical time |
| **T-06** | Requester chính là approver khi SoD bắt buộc | DENY/review độc lập | Workflow audit |
| **T-07** | Approver không có quyền prod | DENY | Entitlement snapshot |
| **T-08** | Data restricted thiếu data owner approval | DENY | Data approval status |
| **T-09** | Approval cho digest khác policy apply | DENY deployment | Canonical digest check |
| **T-10** | Approval bị thu hồi trước apply | DENY deployment | Workflow state |
| **T-11** | Requester sửa destination sau approval | Reapproval required | Version/revision |
| **T-12** | Request chứa wildcard không được duyệt | DENY | Policy-as-code result |
| **T-13** | Source ServiceAccount đúng | ALLOW trong window | Identity/flow test |
| **T-14** | Pod khác namespace/source identity | DENY | CNI/proxy decision |
| **T-15** | Pod giả label nhưng sai workload principal | DENY ở identity-aware PEP | mTLS/identity log |
| **T-16** | Destination hostname đúng và TLS identity hợp lệ | ALLOW theo scope | Proxy/TLS log |
| **T-17** | Direct-IP tới host khác cùng cloud IP range | DENY | Effective route/proxy test |
| **T-18** | Vendor redirect tới hostname ngoài allowlist | DENY hoặc re-review | HTTP redirect log |
| **T-19** | TLS certificate/SAN không match approved host | DENY | TLS verification |
| **T-20** | TCP 443 ALLOW nhưng UDP 443/QUIC | DENY ngoài policy | Firewall/flow telemetry |
| **T-21** | IPv4 source/destination hợp lệ | ALLOW theo đúng rule | IPv4 flow test |
| **T-22** | IPv6 route ngoài policy | DENY | IPv6/AAAA test |
| **T-23** | DNS đi qua resolver không được duyệt | DENY/alert | DNS policy log |
| **T-24** | External DoH/DoT bypass path | DENY nếu ngoài policy | Proxy/firewall test |
| **T-25** | HTTP POST /v1/batches đúng endpoint | ALLOW ở L7-capable PEP | Proxy route log |
| **T-26** | HTTP POST /admin hoặc upload khác method | DENY nếu policy ràng buộc L7 | HTTP decision |
| **T-27** | Dữ liệu đã anonymize thuộc approved class | ALLOW theo DLP criteria | DLP/app event |
| **T-28** | Test payload nhạy cảm giả lập ngoài class | DENY bởi DLP | DLP alert, không dùng PII thật |
| **T-29** | Transfer bytes vượt approved quota | DENY/throttle/alert theo capability | Gateway usage counter |
| **T-30** | SaaS tenant đúng tài khoản doanh nghiệp | ALLOW khi authz hợp lệ | SaaS/API policy |
| **T-31** | Cùng domain nhưng bucket/tenant khác | DENY bởi app/service policy | Cloud audit |
| **T-32** | Trước effective_from | DENY | Time bound test |
| **T-33** | Trong effective window và approved scope | ALLOW | PEP + flow log |
| **T-34** | Sau expires_at với new connection | DENY trong SLO | Negative canary |
| **T-35** | Existing connection tại expiry | Chặn/terminate theo documented SLO | Session/byte telemetry |
| **T-36** | Export job đã start trước expiry | Stop/reconcile theo data policy | Application job audit |
| **T-37** | Early revoke bởi security owner | New traffic DENY | Revoke decision + PEP |
| **T-38** | Approval bị thu hồi giữa window | Controller revoke theo policy | Workflow + audit |
| **T-39** | Gia hạn với approval mới và scope không đổi | New revision đúng hạn | Policy digest/session |
| **T-40** | Gia hạn không có reapproval | DENY | Controller validation |
| **T-41** | Concurrent renew và scheduled revoke | Correct effective version; no stale allow | CAS/idempotency logs |
| **T-42** | Expiry scheduler crash | Watchdog alert và reconcile | Overdue detection |
| **T-43** | PEP một region offline lúc revoke | REVOCATION_FAILED và escalation | Per-PEP state |
| **T-44** | Có một duplicate baseline rule cùng cho phép | Không báo data path DENY khi còn open | Effective-policy test |
| **T-45** | Pipeline deploy identity mất quyền tắt logs | Logging remains protected | IAM simulation/audit |
| **T-46** | Direct NAT/VPN route bypass egress proxy | DENY theo segmentation controls | Route/flow canary |
| **T-47** | Emergency exception hết hạn | Revoke + alert + post-review | Incident and close evidence |
| **T-48** | Rollback policy sau thử nghiệm | Legitimate baseline ALLOW, exceptional path DENY | Regression tests |

### 36.1. Test ALLOW và DENY khác nhau

Một **ALLOW trong window** chứng minh use case có đường làm việc; **DENY đúng source khác, destination khác và sau expiry** chứng minh ngoại lệ không vượt phạm vi. Cả hai cần được đo ở **effective PEP**, không chỉ test policy syntax.

### 36.2. Không nhầm revoke decision với kill active flows

Sự kiện **Controller REVOKE** chưa chứng minh active TCP session đã chấm dứt. Test T-35/T-36 phải lấy **session counts, NAT/conntrack state khi được phép, proxy bytes, job progress và app audit** trong phạm vi SLO. Nếu PEP không hỗ trợ kill flow, ghi hạn chế và tăng lớp app-level expiration.

### 36.3. Negative tests không phá production

Tạo **canary source + synthetic non-sensitive payloads** trong môi trường lab, dùng endpoint thuộc tổ chức/partner sandbox được cho phép. Nếu không thể thử trên production, sử dụng **static policy simulation, provider-native analyzer, staging regression và review data-plane evidence**; không tự gửi dữ liệu ra đích thật để chứng minh firewall deny.

## 37. Những ngộ nhận và cách hiểu đúng

| Ngộ nhận | Giải thích đúng |
|---|---|
| **“Có ticket Approved nghĩa là traffic đã được kiểm soát.”** | Ticket là ý định; PEP cần áp và được test thực. |
| **“Chỉ cần ghi expiry trong comment firewall.”** | Comment không có enforcement; cần scheduler/native expiration. |
| **“Ticket Closed nghĩa rule đã gỡ.”** | Phải có actual config và data-plane verification. |
| **“Xóa rule là mọi TCP session bị ngắt.”** | Stateful conntrack/proxy có thể giữ session cũ. |
| **“Quyền IAM deploy hết hạn thì firewall tự đóng.”** | Session IAM và network rule có lifecycle khác nhau. |
| **“Người yêu cầu có thể tự ký approved=true.”** | Cần trusted workflow và approver independent. |
| **“Một comment OK là approval có ràng buộc.”** | Cần identity, role, policy digest, scope và timestamp. |
| **“Gia hạn chỉ cần sửa expires_at.”** | Gia hạn là policy revision có reapproval. |
| **“MFA mạnh đủ hợp thức hóa ngoại lệ.”** | Authn không thay quyền/risk/data owner approval. |
| **“Wildcard domain luôn an toàn hơn CIDR.”** | Wildcard có thể chứa endpoints không liên quan; cần danh tính đích. |
| **“FQDN luôn là IP cố định.”** | DNS/CDN có thể đổi IP, CNAME, IPv4/IPv6. |
| **“SNI là bằng chứng hostname hợp lệ.”** | SNI do client khai; cần TLS/server identity và trust. |
| **“Cho TCP 443 là chỉ cho HTTPS GET.”** | L4 firewall không biết HTTP method; còn POST, gRPC, TLS ứng dụng khác. |
| **“Chặn TCP 443 cũng chặn QUIC.”** | QUIC dùng UDP/443; cần policy giao thức riêng. |
| **“IPv4 egress deny đủ cho dual-stack.”** | IPv6 route/AAAA/::/0 cần enforcement. |
| **“Kubernetes NetworkPolicy có expires_at native.”** | NetworkPolicy chuẩn không hỗ trợ TTL/FQDN/L7 data DLP. |
| **“Một allow NetworkPolicy tự deny mọi egress khác.”** | Egress isolation và các policies additive phải được xét. |
| **“Pod label là workload identity mật mã.”** | Label có thể đổi; cần RBAC/admission và verified identity. |
| **“AWS Security Group rule cho HTTPS host bằng FQDN.”** | SG không phải L7 FQDN proxy; cần cơ chế đúng capability. |
| **“SaaS domain cho thấy đúng company tenant.”** | Cùng host có thể nhiều tài khoản/bucket; IAM/app controls cần thiết. |
| **“HTTPS có TLS thì không thể exfiltrate.”** | TLS bảo vệ kênh, cũng có thể che upload trái phép. |
| **“DLP không còn cần khi egress domain approved.”** | Data class, operation và tenant vẫn cần kiểm soát. |
| **“TLS decryption luôn là giải pháp DLP tốt nhất.”** | Có rủi ro privacy, mTLS, pinning và trust; cân nhắc app-side controls. |
| **“Không có flow log nghĩa không có traffic.”** | Collector/producer có thể lỗi hoặc traffic bypass logging. |
| **“DLP BLOCK nghĩa dữ liệu chắc chắn đã bị lấy.”** | Blocked upload khác confirmed delivered transfer. |
| **“Không có WAN egress traffic nghĩa không có leak.”** | Có thể leak qua SaaS API, private endpoints, partner VPN, DNS channels. |
| **“Một ngoại lệ nhỏ không cần owner.”** | Owner/approval/expiry là cơ sở trách nhiệm và cleanup. |
| **“Emergency không cần audit.”** | Càng khẩn cấp càng cần TTL, alert và post-review. |
| **“Đóng một rule bảo đảm đường đó không còn reachable.”** | Có thể còn duplicate rule, alternate route/PEP hoặc baseline allow. |
| **“Mọi provider xử lý expiry/FQDN giống nhau.”** | Phải tra khả năng từng product và test effective behavior. |

## 38. Checklist vận hành và phê duyệt ngoại lệ

- [ ] Có business reason rõ và phương án thay thế baseline được đánh giá.
- [ ] Có unique exception ID, requester, business owner và contact của on-call.
- [ ] Source được giới hạn theo workload/user/namespace/account, không chỉ broad CIDR.
- [ ] Destination cụ thể, được kiểm chứng FQDN/TLS identity/account hoặc CIDR theo khả năng.
- [ ] Protocol, port và IPv4/IPv6 được xác định; không ngầm thêm QUIC/UDP.
- [ ] Có data classification, purpose, privacy/data owner approval nếu cần.
- [ ] HTTP method/path/tenant restriction có PEP thật sự enforce nếu ghi trong policy.
- [ ] Data upload quota/bytes/rate limit có implementation và evidence nếu được yêu cầu.
- [ ] Risk class và TTL tối đa được chọn theo sensitivity.
- [ ] effective_from/expires_at có timezone/UTC và server clock rõ.
- [ ] Approver đã xác thực danh tính, quyền thẩm định và không có SoD conflict.
- [ ] Approval gắn đúng canonical policy payload, digest và revision.
- [ ] Đổi source/destination/data/duration bắt buộc reapproval.
- [ ] Protected CI workflow không cho requester tự sửa policy/admission/deployer role.
- [ ] Service/workload identity được xác minh; labels và Pod SA được bảo vệ RBAC/admission.
- [ ] DNS resolver, CDN/CNAME và vendor IP changes có giải pháp phù hợp.
- [ ] TLS server certificate/hostname được xác minh, không dùng SNI tự khai làm bằng chứng duy nhất.
- [ ] Không bỏ sót IPv6/::/0, direct Internet, partner VPN, alternate DNS/DoH và private endpoints.
- [ ] Firewall/CNI/proxy/egress gateway bảo vệ đủ các đường vào/ra, không có bypass.
- [ ] Native NetworkPolicy/CNI/cloud policy semantics đã được kiểm tra theo product/version.
- [ ] Egress traffic tới third-party SaaS được hạn account/tenant/object bằng IAM/app nếu có.
- [ ] DLP enforcement được kiểm tra với synthetic test data, không dùng PII thật.
- [ ] Không làm yếu TLS verification chỉ để inspect nội dung.
- [ ] Không cấp ngoại lệ khi DLP critical đang offline nếu risk policy yêu cầu deny.
- [ ] Auto-revocation job đã được tạo trước hoặc đồng thời với apply.
- [ ] Scheduler có durable state/watchdog/reconciliation, hoạt động khi worker restart.
- [ ] Có exception ID/owner/expiry trong PEP resource metadata nếu hỗ trợ.
- [ ] Plan đã được duyệt chính là policy được apply, không thay âm thầm sau approval.
- [ ] ACTIVE chỉ sau khi PEP/config và positive/negative tests đạt.
- [ ] Có monitoring bytes, DLP rejects, source/destination drift, logging gaps.
- [ ] Owner nhận cảnh báo sắp hết hạn; không tự động gia hạn dựa trên traffic.
- [ ] Early revoke có API/quy trình và thẩm quyền rõ.
- [ ] Expiry chặn new flows trong SLO được phê duyệt.
- [ ] Active TCP/HTTP2/QUIC/gRPC connections được xử lý theo SLO và capability.
- [ ] Có negative canary test sau expiry; không dùng scan ngoài phạm vi.
- [ ] Nếu còn duplicate allow policy, điều tra effective policy thay vì đánh dấu đã deny.
- [ ] Multi-region/multi-PEP revoke failures được alert/escalate, không im lặng.
- [ ] Rule cleanup idempotent, không xóa baseline khác hoặc revision mới.
- [ ] Có trạng thái REVOCATION_FAILED và runbook khôi phục.
- [ ] Cloud IAM/CI role không được tắt security audit, sửa approval hoặc tự nâng quyền.
- [ ] Security events lưu actor, approver, digest, source/dest, timestamps, policy revision, final state.
- [ ] Log có redaction, RBAC, retention và integrity; không chứa token/payload nhạy cảm.
- [ ] Dashboard đo expired-active, revoke lag, repeated renewals và high-risk exceptions.
- [ ] Emergency có incident ID, approver/alert, TTL rất ngắn, audit và post-review.
- [ ] Hợp đồng vendor/SaaS, data retention và transfer permissions được review khi cần.
- [ ] Exception lặp lại liên tục được chuyển sang architecture/baseline review.
- [ ] Khi decommission, rà orphaned firewall rules, proxy policies, DNS entries và IAM rights.
- [ ] Không đánh đồng trạng thái ticket Closed với CLOSED_VERIFIED trên data plane.

## 39. Câu hỏi tự kiểm tra

**1. Ngoại lệ egress có thời hạn khác policy baseline như thế nào?**  
Ngoại lệ lệch baseline cho một nhu cầu, nguồn, đích, dữ liệu và cửa sổ thời gian xác định, có approver và auto-revoke; baseline là quyền lâu dài được quản trị theo architecture review.

**2. Vì sao chỉ có expires_at trong ticket chưa đủ?**  
Vì firewall/proxy/CNI không tự đọc ticket. Cần controller/native expiry, xử lý active flows và kiểm chứng effective deny tại PEP.

**3. Tại sao requester không nên tự phê duyệt?**  
Vì người yêu cầu có động cơ hoàn thành công việc; SoD giúp có người độc lập đánh giá risk, data classification, scope và hậu quả.

**4. Approval phải gắn với những gì?**  
Identity/entitlement của approver, source/destination/protocol/data class, exact policy digest/version, window và timestamp. Mọi thay đổi ý nghĩa cần reapproval.

**5. Nếu deploy role JIT hết hạn, rule đã tạo có tự biến mất không?**  
Không. Quyền gọi API của deployer và lifecycle network rule là hai thứ khác; auto-revocation phải được thiết kế riêng.

**6. DNS/FQDN allowlist có bảo đảm data chỉ đến vendor account được duyệt không?**  
Không. Host có thể chứa nhiều tenants/buckets; cần cloud IAM, SaaS account scoping và app/DLP authorization.

**7. Vì sao SNI không đủ chứng minh destination?**  
SNI là thông tin do client gửi, có thể bị che hoặc không khớp HTTP Host; cần kiểm tra TLS server identity, route, trusted proxy và enforcement capability.

**8. Làm sao xử lý CDN vendor đổi IP?**  
Dùng domain-aware proxy hoặc cơ chế dynamic destination do provider hỗ trợ, kiểm tra DNS/TLS identity và test; không mở toàn cloud CIDR chỉ để chữa timeout.

**9. Vì sao NetworkPolicy chuẩn không tự tạo time-bound egress?**  
Nó không có field chuẩn cho expires_at/FQDN/HTTP path/DLP; cần controller, CNI extensions hoặc egress gateway tương ứng.

**10. Vì sao label app=export-job chưa là identity đáng tin?**  
Người có quyền sửa Pod labels có thể dùng cùng selector. Cần RBAC/admission và workload identity được xác minh.

**11. Một proxy HTTPS có nhìn được nội dung DLP không?**  
Tùy architecture, TLS termination/inspection và protocol; không mặc định proxy nhìn được tất cả payload và không được hạ TLS tùy tiện.

**12. Quyền kết nối network có đồng nghĩa được gửi PII không?**  
Không. Application/Data owner và DLP controls phải độc lập cho phép loại dữ liệu và hành động xuất.

**13. Vì sao xóa rule firewall chưa chắc làm TCP session đang hoạt động dừng?**  
Conntrack/stateful session và proxy connection pools có thể giữ trạng thái; cần kiểm tra termination behavior và ứng dụng.

**14. Gia hạn hợp lệ cần gì?**  
Yêu cầu mới, reason, scope/expiry mới, approver còn quyền, policy revision/digest mới, test và lịch revoke cập nhật.

**15. Nếu scheduler gặp lỗi và 20 rule quá hạn, nên làm gì?**  
Watchdog phát hiện, đánh dấu REVOCATION_FAILED, alert NetSec/SOC, reconcile hoặc áp deny có kiểm soát, xác minh data plane và lưu incident evidence.

**16. Làm sao phân biệt DLP BLOCK với data leak?**  
DLP BLOCK nghĩa một hành động bị từ chối ở lớp DLP; cần thêm evidence về delivered bytes, application logs và data payload để kết luận mất dữ liệu.

**17. Policy ALLOW trên one PEP có nghĩa hết path đều ALLOW hoặc DENY đúng không?**  
Không. Có thể có duplicate rule, alternate NAT/VPN, IPv6 hoặc bypass; phải inventory và test effective path.

**18. Trường hợp emergency có cần phê duyệt và expiry?**  
Có. Workflow có thể rút ngắn theo risk nhưng vẫn cần incident authority, scope, TTL, log, cảnh báo và hậu kiểm.

**19. SLO nên đo thời điểm nào khi đóng exception?**  
Ngoài thời điểm ticket đóng, cần đo **expires_at → new-flow deny**, **revoked_at → active-flow termination** và trạng thái tất cả PEPs.

**20. Khi một ngoại lệ được gia hạn liên tục, quyết định bền vững là gì?**  
Review liệu business need đã ổn định; thiết kế sanctioned gateway/private connection hoặc cập nhật baseline theo security/data approval, không perpetually renew.

## 40. Tài liệu tham khảo

- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): access control, information flow enforcement, least privilege, configuration change control, audit và monitoring.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): identity, per-resource authorization và policy enforcement.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): thu thập/bảo vệ logs phục vụ điều tra.
- [CIS Controls v8](https://www.cisecurity.org/controls/v8): account, secure configuration, data protection và network monitoring.
- [MITRE ATT&CK — Exfiltration Over Web Service (T1567)](https://attack.mitre.org/techniques/T1567/): rủi ro truyền dữ liệu qua SaaS/web services hợp pháp.
- [MITRE ATT&CK — Exfiltration Over Alternative Protocol (T1048)](https://attack.mitre.org/techniques/T1048/): kênh exfiltration qua giao thức khác.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): kiểm tra destination, DNS, allowlist và ngăn server-side requests tới đích không được duyệt.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ credentials và hạn chế rò secrets.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): audit event design, log injection và sensitive-data minimization.
- [Open Policy Agent — Documentation](https://www.openpolicyagent.org/docs): policy-as-code/Rego cho kiểm tra điều kiện cấp ngoại lệ.
- [Kubernetes — NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): các khả năng và giới hạn egress policy chuẩn.
- [Kubernetes — RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/): kiểm soát quyền tạo/patch resources và ServiceAccount.
- [AWS Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html): outbound rules và phạm vi filter ở VPC.
- [AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html): kiểm soát lưu lượng mạng và khả năng lọc theo service.
- [AWS VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html): quan sát metadata flows.
- [Microsoft Learn — Azure Firewall](https://learn.microsoft.com/en-us/azure/firewall/overview): network/application policy và giám sát.
- [Microsoft Learn — Azure Network Security Groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview): L3/L4 filtering.
- [Google Cloud — VPC Firewall Rules](https://cloud.google.com/firewall/docs/firewalls): các lớp firewall và scope.
- [Google Cloud — VPC Flow Logs](https://cloud.google.com/vpc/docs/using-flow-logs): network flow telemetry.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): bảo mật kênh TLS và giới hạn traffic visibility.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method/path/host và ứng dụng policy đúng lớp.
- [RFC 5737 — IPv4 Address Blocks Reserved for Documentation](https://www.rfc-editor.org/rfc/rfc5737): địa chỉ TEST-NET được dùng trong ví dụ.
- [RFC 4193 — Unique Local IPv6 Unicast Addresses](https://www.rfc-editor.org/rfc/rfc4193): hiểu IPv6 private/local addressing khi thiết kế mạng.

**Ghi nhớ:** **Ngoại lệ egress có thời hạn và người phê duyệt** phải là một quyền **có nguồn, đích, protocol, dữ liệu, cửa sổ thời gian và thẩm quyền cụ thể**, được ràng buộc bằng **approval đáng tin, digest/version, SoD và policy enforcement thực tế**. Đừng coi **ticket Approved** là traffic đã được phép đúng cách, hoặc **ticket Closed** là đã chặn traffic. Thiết kế đúng cần **auto-revoke bền vững, kiểm chứng chặn kết nối mới, xử lý sessions còn sống, DLP, không có đường bypass, logging, detection và incident runbook**, đồng thời giảm nhu cầu ngoại lệ lặp lại bằng kiến trúc egress chuẩn.




