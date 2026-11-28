# Đo lường hiệu quả của Zero Trust: từ mức bao phủ đến giảm rủi ro và trải nghiệm truy cập

Trong chương **Zero Trust Network Access** thuộc module **SECURITY_NETWORK_SECURITY**, hiệu quả của Zero Trust không thể được khẳng định chỉ bằng việc “đã mua sản phẩm ZTNA”, “mọi người đã đăng ký MFA” hoặc “dashboard hiển thị nhiều lượt từ chối”. Một kiến trúc chỉ hiệu quả khi chứng minh được **đúng danh tính, đúng thiết bị và đúng ngữ cảnh được cấp quyền tối thiểu tới đúng tài nguyên**, còn truy cập trái quyền và đường đi vòng kiểm soát bị chặn, đồng thời ứng dụng hợp lệ vẫn đáp ứng yêu cầu nghiệp vụ.

**Zero Trust (ZT)** là phương pháp kiến trúc không mặc định tin cậy chỉ vì một client hoặc workload ở trong mạng nội bộ. **Zero Trust Network Access (ZTNA)** là nhóm giải pháp cung cấp truy cập tài nguyên/ứng dụng theo danh tính, chính sách và ngữ cảnh thay vì cấp mạng phẳng. ZTNA là **một phần của Zero Trust**, không tự thay toàn bộ identity security, endpoint security, data security, logging, segmentation hay ứng dụng.

Ví dụ một tổ chức đạt **99% phiên truy cập thành công qua ZTNA** vẫn có thể nguy hiểm nếu hệ thống lương còn **public admin endpoint**, nhân viên nghỉ việc còn **session cookie dài hạn**, một số máy thiếu EDR vẫn vào được hệ thống tài chính, hoặc legacy VPN còn route cho người dùng tới toàn bộ database subnet. Ngược lại, **tỷ lệ deny tăng** không tự chứng minh cải thiện: có thể do policy sai đang khóa người dùng hợp lệ.

Bài học này thiết kế một **hệ đo lường có thể kiểm chứng** gồm: asset/path coverage, identity assurance, device posture, policy/least-privilege effectiveness, segmentation/bypass testing, session revocation, detection/risk outcomes, SLO/trải nghiệm, dữ liệu telemetry, dashboard, baseline, so sánh trước–sau, tình huống sự cố và kế hoạch cải tiến.

**Sau bài này, bạn có thể:**

- Phân biệt **Zero Trust adoption, control deployment, enforcement effectiveness, security outcomes và business outcomes**.
- Định nghĩa **KPI, KRI, SLI, SLO**, numerator/denominator, nguồn dữ liệu, thời gian đo và độ tin cậy.
- Đo **verified ZTNA coverage, high-risk bypass paths, phishing-resistant MFA coverage, posture freshness, least privilege, access revocation latency**.
- Thiết kế **positive/negative/bypass tests** cho app-scoped access, thiết bị không đạt chuẩn, tài khoản hết quyền, IPv4/IPv6 và VPN legacy.
- Theo dõi **detect/respond, policy drift, telemetry correlation, p95 latency, availability và helpdesk impact**.
- Phân biệt số đo tốt với những chỉ số dễ gây hiểu nhầm; tránh **chọn mẫu sai, survivor bias, giảm alert bằng cách tắt detection hoặc gộp nhóm rủi ro không tương đương**.
- Xây dựng dashboard gắn với **risk owners, corrective actions và kiểm thử độc lập**, thay vì chỉ trưng bày một điểm “ZT Score”.

## 1. Thế nào là Zero Trust hoạt động hiệu quả?

Một resource có thể trải qua bốn trạng thái khác nhau:

~~~text
CONFIGURED
  Ứng dụng đã được khai báo trong hệ thống ZTNA.

DEPLOYED
  Có connector/PEP, identity policy và đường truy cập đã hoạt động.

ENFORCED
  Người dùng phải qua policy decision; các direct/bypass paths
  ngoài thiết kế bị chặn thật ở điểm thực thi có hiệu lực.

EFFECTIVE
  Request hợp lệ chạy thành công; request trái quyền bị chặn đúng,
  phiên bị thu hồi trong SLO; có bằng chứng và mức rủi ro còn lại
  được quản trị, không tạo gián đoạn không chấp nhận được.
~~~

**Configured ≠ enforced**, và **enforced ≠ giảm được bao nhiêu sự cố thực**. Vì vậy cần đo theo bốn lớp:

| Lớp | Câu hỏi | Ví dụ chỉ số |
| --- | --- | --- |
| **Bao phủ** | Bao nhiêu tài nguyên, danh tính, thiết bị và đường vào thuộc phạm vi đã được quản lý? | Verified app/path coverage |
| **Hiệu lực control** | Quyết định allow/deny đúng và không bị đi vòng? | Positive/negative test pass rate, effective revocation latency |
| **Kết quả an ninh** | Exposure và tác động của vụ việc có giảm không? | Verified unauthorized paths, dwell time, compromised-access incidents |
| **Kết quả vận hành** | Truy cập hợp lệ có ổn định, dễ sử dụng và có thể phục hồi không? | Authorized access success, p95 connection latency, incident tickets |

### 1.1. Mục tiêu cần được viết thành điều kiện kiểm thử

Một mục tiêu mơ hồ là: “Chỉ nhóm tài chính được vào payroll”. Phiên bản có thể kiểm thử:

> User thuộc Finance, dùng thiết bị đạt posture còn mới, có phiên SSO/MFA đủ mức bảo đảm và đang trong thời hạn được phép, có thể truy cập Payroll HTTPS qua PEP được phê duyệt. User ngoài Finance, thiết bị không đạt chuẩn, tài khoản đã offboard hoặc phiên hết quyền bị từ chối. Không có đường public/VPN/admin truy cập Payroll ngoài ngoại lệ đã phê duyệt.

Yêu cầu này tạo được test cases cho **identity, device, resource, access path, session, policy decision, app result và revoke**.

### 1.2. Zero Trust là hành trình, không phải trạng thái nhị phân

Đánh giá hiệu quả cần:

- Một **baseline** trước triển khai.
- Mức rủi ro và **tài sản ưu tiên** rõ ràng.
- **Control objectives** và phương án quan sát riêng cho từng mục tiêu.
- **Test có quyền** xác minh policy thực thay vì chỉ kiểm tra cấu hình.
- **Khoảng thời gian đo lặp lại**, ownership và kế hoạch giảm rủi ro còn lại.

Không có “100% Zero Trust” chung cho mọi tổ chức. Những mục tiêu như “p95 revoke trong 5 phút” là **SLO mẫu**, không phải ngưỡng do NIST áp cho mọi hệ thống.

## 2. Mô hình kiến trúc và vị trí đo

Trong mô hình Zero Trust phổ biến, **Policy Decision Point (PDP)** quyết định cấp hoặc từ chối quyền dựa trên identity, posture, risk và resource policy; **Policy Enforcement Point (PEP)** thực hiện/đóng đường truy cập. Các vai trò logic như **Policy Engine/Policy Administrator** có thể tham gia theo implementation.

~~~mermaid
flowchart LR
    U["User / workload"] --> P["PEP: agent, proxy, gateway, connector"]
    P --> A["Ứng dụng / data resource"]
    I["IdP / MFA / identity lifecycle"] --> D["PDP / policy evaluation"]
    E["EDR / MDM / device posture"] --> D
    R["Resource classification / entitlements"] --> D
    D -->|"allow / deny / step-up / revoke"| P
    P -. "session/decision evidence" .-> O["Telemetry / SIEM"]
    D -. "policy inputs & versions" .-> O
    A -. "application audit" .-> O
~~~

Đây là **sơ đồ logic**, không phải kiến trúc bắt buộc của mọi sản phẩm. Một sản phẩm có thể dùng cloud relay/connector, app reverse proxy, endpoint agent, browser isolation hoặc enforcement tích hợp trong ứng dụng. **Đo đúng nơi đang thực thi**, không chỉ đo portal quản trị.

| Lớp | Telemetry | Chứng minh được | Không tự chứng minh |
| --- | --- | --- | --- |
| **IdP/HR/IAM** | User status, group, auth method, MFA, token | Identity lifecycle và xác thực | Packet không đi vòng PEP |
| **MDM/EDR** | Device compliance, EDR health, attestation, timestamps | Device signal có sẵn và trạng thái | PEP thực sự deny khi posture xấu |
| **PDP** | Input context, policy version, decision, reason | Policy ra quyết định nào | PEP có áp decision lên phiên hiện tại không |
| **PEP/ZTNA** | Connect/disconnect, resource, deny/allow, session ID | Phiên đã được PEP xử lý | Legacy VPN/public IP không còn đường vào |
| **Network/firewall/DNS** | Route, source/destination/port, NAT, flow logs | Đường packet và enforcement của mạng | Danh tính user/app nếu thiếu correlation |
| **Application/API** | User session, action, app role, response | Resource/operation thật được dùng | Mọi lần truy cập đều đi qua ZTNA |
| **SOC/IR** | Alert, incident timeline, remediation | Detection và response capability | Alert ít nghĩa là đã an toàn |

### 2.1. Đường ngoài PEP phải có cảm biến độc lập

Một người dùng có thể không đi qua PEP nếu ứng dụng còn:

- Public hostname/public IP.
- **Legacy VPN** hoặc peering/site-to-site route đi trực tiếp vào subnet.
- SSH/RDP/admin URL, backup/maintenance endpoint riêng.
- **IPv6**, secondary interface hoặc private link khác.
- Service-to-service/API token, CI runner hoặc partner connection.

Nếu chỉ xem dashboard ZTNA, những luồng không đi qua ZTNA có thể **hoàn toàn không xuất hiện**. Do đó, network inventory, firewall/flow logs và **negative bypass tests** phải là nguồn đo độc lập.

## 3. Từ rủi ro tới chỉ số: KPI, KRI, SLI và SLO

~~~mermaid
flowchart TD
    T["Threat scenario"] --> O["Control objective"]
    O --> C["Preventive/detective control"]
    C --> M["Metric + numerator/denominator"]
    M --> E["Telemetry + validation tests"]
    E --> A["Decision/remediation owner"]
    A --> T
~~~

- **KPI:** mức đạt mục tiêu chương trình, ví dụ tỷ lệ tài nguyên critical đã được kiểm chứng bảo vệ.
- **KRI:** rủi ro tồn tại, ví dụ số direct access paths ngoài policy vẫn reachable.
- **SLI:** số đo dịch vụ như độ trễ thiết lập ZTNA session hoặc availability.
- **SLO:** mục tiêu cho SLI với phạm vi/thời gian/nhóm người dùng được xác định.
- **Leading indicator:** khả năng kiểm soát có xu hướng phòng ngừa sự cố, ví dụ posture signal freshness.
- **Lagging indicator:** kết quả đã xảy ra, ví dụ confirmed unauthorized access incidents.

Ví dụ:

| Rủi ro | Control objective | Metric/bằng chứng |
| --- | --- | --- |
| Password bị lấy cắp | Truy cập tài nguyên nhạy cảm yêu cầu phishing-resistant MFA | High-assurance access conformance, credential misuse negative tests |
| Laptop thiếu EDR | Thiết bị noncompliant không dùng ứng dụng tài chính | Posture freshness, deny effectiveness, stale sessions |
| Di chuyển ngang | Không có full-subnet reachability trái quyền | Risk-weighted bypass findings, segmentation tests |
| User nghỉ việc | Chặn new access và vô hiệu hóa old sessions | Effective revocation p95, residual session count |
| Privileged role lạm dụng | Chỉ cấp quyền admin khi cần | JIT coverage, standing privileged grants |
| Rò dữ liệu khó điều tra | Correlate user → device → app action | Event traceability, log coverage/freshness |
| ZTNA gây gián đoạn | Truy cập hợp lệ vẫn đúng SLO | Authorized success rate, p95 connect time, helpdesk |

### 3.1. Mỗi KPI phải có bản định nghĩa chính thức

Một bản định nghĩa cần ít nhất:

1. **Tên và mục tiêu rủi ro** được đo.
2. **Population/denominator** và các tiêu chí nằm trong/ngoài phạm vi.
3. **Numerator** có điều kiện pass cụ thể.
4. **Telemetry sources** và data-quality checks.
5. **Time window**, timezone, ingestion delay và event-time logic.
6. **Owner**, SLO/threshold, hành động khi vượt ngưỡng và exception handling.
7. **Segmentation** theo criticality, user type, platform/region.
8. **Caveats**: metric này không chứng minh được điều gì.

Nếu không định nghĩa denominator, một báo cáo “đã chặn 10.000 lần truy cập” thiếu bối cảnh: có thể do một client hỏng tự retry liên tục hoặc do traffic độc hại thật.

## 4. Xây denominator: inventory chính xác mới đo chính xác

Asset inventory nên tổng hợp từ **CMDB, cloud account inventory, DNS, reverse proxy, SaaS registrations, firewall, VPN routes, API gateways, IdP app assignments, Kubernetes/service discovery** và hệ thống được giao cho các owner.

| Population | Đơn vị đo | Nguồn kiểm chứng |
| --- | --- | --- |
| **Private business apps** | Application + entry point | CMDB, DNS, LB, ZTNA resource inventory |
| **Critical applications** | Tài sản có impact/risk tier | Risk register, data classification |
| **Access paths** | Source class → resource → protocol → network path | Firewall/VPN/route inventory và test |
| **Human identities** | Person/IdP principal | HR/Directory, identity lifecycle |
| **Privileged identities** | Standing/JIT admin identity | IAM, PAM, RBAC, ZTNA policies |
| **Workload identities** | Service accounts, API clients, CI/CD roles | IAM/API gateway/mesh/service inventory |
| **Devices** | Corporate, managed BYOD, unmanaged | MDM/EDR, asset inventory |
| **Sessions/decisions** | PEP/app sessions, PDP decisions | Access gateway, IdP, app audit |

### 4.1. Không loại ứng dụng chưa onboard khỏi mẫu số

Nếu chương trình hướng tới **tất cả private applications**, một ứng dụng legacy chưa đưa vào ZTNA phải được tính **chưa đạt**, không xóa khỏi denominator. **Approved exceptions** phải hiển thị riêng cùng owner, compensating controls và expiry date.

### 4.2. Scope thay đổi làm phần trăm thay đổi

~~~text
Tháng A:
  Discovered private apps       100
  Verified ZTNA enforcement     80
  Coverage                      80%

Tháng B:
  Asset discovery phát hiện 40 apps mới
  Discovered private apps       140
  Verified ZTNA enforcement    100
  Coverage                      71,4%
~~~

Số resource đã kiểm chứng **tăng từ 80 lên 100**, dù coverage giảm do inventory tốt hơn. Dashboard phải hiển thị **số lượng tuyệt đối, scope delta, new discoveries, risk tiers và verified percentage**. Không kết luận chương trình xấu đi chỉ từ tỷ lệ trong một population đã đổi.

### 4.3. Resource khác URL

Một ứng dụng có thể có **web interface, REST API, SSH admin, RDP, database port, DR endpoint, IPv6 address, VPN route và SaaS integration**. Một resource ZTNA có thể chỉ bảo vệ web URL mà bỏ trống admin interface.

Vì thế, **path-level coverage** thường đáng tin hơn số “ứng dụng đã khai báo trong portal”. Một path nên có các thuộc tính **source zone, identity class, destination host/service, protocol/port, resource owner và enforcement point**.

## 5. Bộ chỉ số cốt lõi

| Nhóm | Metric | Chiều hướng |
| --- | --- | --- |
| **Coverage** | Verified app/path coverage theo criticality | Tăng |
| **Exposure** | Unauthorized direct/bypass paths còn reachable | Giảm |
| **Identity assurance** | Sensitive attempts đáp ứng phishing-resistant auth policy | Tăng |
| **Device trust** | Decisions có required posture signals còn mới | Tăng |
| **Least privilege** | Excess standing privileges/overbroad role assignments | Giảm |
| **Policy quality** | Positive + negative authorized/unauthorized test pass rates | Cả hai tăng |
| **Session lifecycle** | p50/p95/max effective access revocation latency | Giảm trong risk SLO |
| **Continuous evaluation** | Risk/posture change triggers được re-evaluate đúng | Tăng |
| **Observability** | Access events correlate user, device, resource, decision, action | Tăng |
| **Detection** | Coverage of tested misuse scenarios, MTTD/containment | Tốt hơn với evidence |
| **Availability** | Successful legitimate access, PEP/IdP connector uptime | Tăng |
| **User experience** | p95 session establishment time, helpdesk tickets | Giảm lỗi/độ trễ |
| **Governance** | Policy drift, expired exceptions, risky unreviewed grants | Giảm |
| **Outcomes** | Confirmed unauthorized sensitive actions, blast radius | Giảm, có điều kiện detection đủ |

Không cần ép mọi mục tiêu vào **một điểm tổng**. Nên có dashboard theo **security posture, risk and business service quality**, và drill-down tới từng app/owner/path.

### 5.1. Các nhóm không tương đương cần tách

- Employee, contractor, partner, external vendor.
- Managed laptop, managed BYOD, unmanaged device.
- Human user, privileged admin, service/robot/CI identity.
- Production, non-production, disaster recovery.
- Critical/high/medium/low resource.
- Văn phòng, remote, VPN legacy, cloud workload, third-party.

Đừng để tỷ lệ tốt ở hàng nghìn logins thông thường che **một privileged access path còn mở**.

### 5.2. Ngưỡng là quyết định rủi ro nội bộ

“99,5% authorized login success”, “p95 revocation dưới 5 phút” hoặc “critical path coverage 100%” đều có thể là **mục tiêu ví dụ**, không phải tiêu chuẩn chung. Thực tế cần thỏa thuận giữa security, IAM, SRE, application owner và lãnh đạo rủi ro.

## 6. Verified coverage và cách tính theo trọng số rủi ro

Gọi \(A\) là tập app/entry points thuộc phạm vi, \(E\) là tập đã chứng minh:

- Identity/policy đúng.
- Access hợp lệ qua đúng PEP.
- Đường direct/bypass ngoài policy bị deny.
- Telemetry đủ ghi nhận.

\[
\text{Verified coverage} = \frac{|E|}{|A|} \times 100\%
\]

Ví dụ: **72 trên 90** private applications đã kiểm chứng thực thi đầy đủ, coverage là **80%**. Các ứng dụng chỉ có cấu hình nhưng chưa chạy bypass tests nên đặt vào trạng thái **configured, unverified**.

### 6.1. Risk-weighted coverage

Với mỗi tài nguyên \(i\) có trọng số \(w_i\) theo business impact và exposure:

\[
\text{Risk-weighted coverage} = \frac{\sum_{i \in E} w_i}{\sum_{i \in A} w_i} \times 100\%
\]

| Ứng dụng | Risk weight (minh họa) | Enforcement verified | Đóng góp |
| --- | ---: | --- | ---: |
| Payroll | 5 | Không | 0 |
| CRM | 4 | Có | 4 |
| Reporting | 2 | Có | 2 |
| Internal Wiki | 1 | Có | 1 |
| **Tổng** | **12** | **3/4** | **7** |

**Unweighted coverage = 75%**, nhưng **risk-weighted coverage = 7/12 ≈ 58,3%**. Việc bỏ ngỏ Payroll khiến kết quả có ý nghĩa rủi ro thấp hơn nhiều.

Các trọng số cần được **tài liệu hóa, quản trị và kiểm toán**, tránh đổi trọng số để cải thiện KPI trên giấy.

### 6.2. Path-level coverage

\[
\text{Verified path coverage} = \frac{\text{approved paths có enforcement được test}}{\text{tổng in-scope access paths}} \times 100\%
\]

Một access path gồm **source trust zone/identity type, resource, protocol/port và tuyến mạng**. Kiểm tra cả **public IP, VPN, peering, management interface, IPv6, DR** nếu trong scope.

### 6.3. Metric riêng cho bypass

Theo dõi:

- Số **verified unauthorized reachable paths** và risk tier.
- **Age** và owner của từng bypass finding.
- Tổng số **legacy VPN/public admin routes** chưa có compensating controls.
- Số exceptions **quá hạn** hoặc chưa được phê duyệt.
- Mức **test coverage** cho những đường được đánh giá.

Mục tiêu không phải ít findings do ngừng test, mà là **giảm unauthorized reachability với test coverage không giảm**.

## 7. Đo authentication assurance và MFA thực sự

Phân biệt các trạng thái:

- **MFA enrollment:** người dùng đã đăng ký một factor.
- **MFA enforcement:** policy đòi factor/mức assurance phù hợp ở access thuộc phạm vi.
- **Phishing-resistant MFA:** phương thức có tính chống phishing như WebAuthn/FIDO2/passkeys trong cấu hình bảo đảm phù hợp.
- **Strong-auth coverage:** access attempts nhạy cảm được xử lý đúng theo mức bảo đảm yêu cầu.
- **Credential-replay resistance:** các thử nghiệm có thẩm quyền với danh tính thử hoặc sự cố có evidence.

Một nhân viên đã enroll MFA không có nghĩa **mọi application session, legacy protocol và API token** của họ đều chịu cùng assurance requirement.

### 7.1. Chính xác hóa numerator

\[
\text{Strong-auth policy conformance} =
\frac{\text{eligible decisions được xử lý đúng theo required assurance}}
{\text{tổng eligible decisions cần mức assurance đó}} \times 100\%
\]

Phải phân biệt:

- Legitimate attempt dùng đúng factor và **được allow**.
- Attempt thiếu factor phù hợp và **bị deny/step-up** đúng.
- **Unexpected allow** khi assurance chưa đủ (policy violation).
- **False deny** user hợp lệ do IdP/SDK/device lỗi.

Một dashboard chỉ đếm “số MFA prompts” có thể khuyến khích **prompt fatigue** chứ không nâng chất lượng xác thực.

### 7.2. Những kịch bản kiểm thử

1. Password đúng, nhưng không có phishing-resistant factor cho app high risk.
2. User đang ở session cũ nhưng risk score tăng đáng kể.
3. Contractor vừa hết hạn hợp đồng, thử new login và existing app cookie.
4. Browser/SSO dùng token có audience sai hoặc đã hết hạn.
5. Break-glass identity chỉ được dùng trong emergency window, có approver và audit.

Các test phải dùng **test identities và môi trường được cấp phép**, không đánh cắp tài khoản nhân sự để đo KPI.

## 8. Đo device posture: tính hợp lệ và độ tươi của tín hiệu

Zero Trust có thể đánh giá **thiết bị có được quản lý, trạng thái EDR, mã hóa ổ đĩa, phiên bản OS/patch, chứng chỉ thiết bị và compliance**. Không chỉ cần tín hiệu “healthy”; cần biết **tín hiệu được thu khi nào, còn hợp lệ không và access policy có sử dụng nó hay không**.

### 8.1. Vấn đề stale posture

Giả sử laptop đạt chuẩn lúc **09:00**, nhưng EDR dừng lúc **09:05**. Nếu PEP chỉ kiểm tra posture lúc login và giữ phiên cả ngày, KPI “100% login có compliant device” có thể che một khoảng rủi ro dài.

Theo dõi:

- **Posture signal completeness:** số decisions có đủ tất cả signals bắt buộc.
- **Freshness conformance:** tỷ lệ decisions có signals trong TTL cho phép.
- **Risk event propagation latency:** từ khi EDR/MDM báo xấu đến khi PDP/PEP biết.
- **Reevaluation coverage:** tỷ lệ sessions chịu đánh giá lại khi có trigger.
- **Noncompliant session exposure:** số/duration phiên nhạy cảm vẫn sử dụng được sau khi posture xấu vượt SLO.
- **False posture denial:** số user/device hợp lệ bị deny do agent lỗi, clock skew hoặc stale telemetry.

### 8.2. Công thức

Nếu một posture decision yêu cầu các tín hiệu còn hiệu lực trong TTL:

\[
\text{Freshness conformance} = \frac{\text{decisions có tất cả signal bắt buộc còn mới}}{\text{decisions có yêu cầu posture}} \times 100\%
\]

Nên báo cáo riêng **unknown/stale/not observed**. Không coi “không có sự kiện EDR báo lỗi” là bằng chứng EDR đang chạy tốt.

### 8.3. Posture và privacy

BYOD không nhất thiết có cùng quyền thu thập thông tin như corporate devices. Một tổ chức có thể chọn **browser isolation, hạn chế download, device-bound credential hoặc limited app mode** cho thiết bị unmanaged thay vì thu thập quá nhiều dữ liệu cá nhân. Mỗi nhóm cần **policy và denominator riêng**.

### 8.4. Test scenarios

| Tình huống | Kỳ vọng |
| --- | --- |
| Managed device compliant, signal mới | Allow theo user/resource policy |
| Unmanaged device tới Payroll | Deny hoặc restricted mode đã phê duyệt |
| EDR không healthy khi phiên đang mở | Reevaluate/revoke theo SLO |
| MDM mất liên lạc quá TTL | Không mặc định coi là compliant |
| Device được khắc phục posture | Access phục hồi có kiểm tra, không dùng permanent exception |
| Máy chưa có device identifier duy nhất | Đưa vào unknown và điều tra mapping, không tính “đạt” |

## 9. Đo least privilege và entitlement hygiene

**Least privilege** phải được quan sát theo **quyền thực người dùng có và dùng**, không chỉ theo số policies.

Các nguồn quyền bao gồm **IdP groups, ZTNA resource mappings, PAM, cloud IAM, Kubernetes RBAC, database roles, SaaS apps và API scopes**.

| Metric | Cách hiểu | Hạn chế |
| --- | --- | --- |
| **Standing privileged grants** | Quyền admin tồn tại thường xuyên không dùng JIT | Một ít quyền rất mạnh vẫn rủi ro cao |
| **Overbroad resource access** | User/role thấy nhiều app/subnet ngoài nhiệm vụ | Cần baseline role chính xác |
| **Dormant high-risk grants** | Quyền nhạy cảm không dùng lâu nhưng vẫn active | Break-glass có thể là ngoại lệ hợp lệ |
| **JIT access coverage** | Privileged operations có cấp quyền có thời hạn | JIT không tự bảo vệ API token khác |
| **Privilege expiration success** | Quyền hết hạn bị mất hiệu lực thật | App cookie/network session có thể tồn tại |
| **Excess-access remediation time** | Từ finding đến confirmed removal | Ticket closed không phải revoke verified |
| **Entitlement attestation quality** | Owner xác nhận quyền theo role/business need | Checklist tick hết không đồng nghĩa review đúng |

### 9.1. Effective access khác entitlement trên giấy

Ví dụ user không thuộc nhóm ZTNA cho Finance-App nhưng vẫn có **legacy VPN route + database credential**; quyền thực vẫn cao hơn báo cáo ZTNA. Một program tốt so sánh **declared entitlement, current policy, effective reachability, application authorization và observed sessions**.

### 9.2. Đo quyền theo resource/action

Đối với ứng dụng có dữ liệu quan trọng, nên tách:

~~~text
Resource: Payroll
  Access via ZTNA: web:443
  Identity role: Finance analyst
  App privilege: view own-team reports
  Device: managed, EDR healthy
  Session TTL: theo SLO đã duyệt
  Forbidden: salary admin edit, raw DB TCP, SSH/RDP ngoài JIT
~~~

Một ZTNA allow tới web:443 **không chứng minh** user không thể gọi API quản trị trong chính ứng dụng; phải kiểm tra **app authorization** riêng.

### 9.3. Đừng tối ưu deny rate

\[
\text{Deny rate}=\frac{\text{denied access decisions}}{\text{all access decisions}}
\]

Deny rate cao có thể do tấn công, policy khắt khe hoặc lỗi integration. Deny rate thấp có thể do ít tấn công hoặc **policy quá rộng**. Cần **ground-truth test labels**, reasons và loại trừ noise của retry loops khi diễn giải.

## 10. Đo segmentation, least reachability và chống đi vòng

ZTNA thường chuyển từ “user được vào mạng” sang “user được vào **ứng dụng cụ thể**”. Tuy nhiên VPN cũng có thể đạt least privilege nếu firewall và routing được cấu hình tốt; không gắn nhãn **mọi VPN không an toàn**.

~~~mermaid
flowchart LR
    U["User"] --> Z["ZTNA policy"]
    Z --> A["CRM HTTPS"]
    Z -. "Deny" .-> B["Payroll / DB / SSH"]
    V["Legacy VPN route rộng"] --> S["Private subnet"]
    S --> A
    S -. "Nếu ACL yếu" .-> B
~~~

### 10.1. Positive và negative test pass rates

\[
\text{Positive pass rate}=\frac{\text{valid allow tests thành công đúng điều kiện}}{\text{tổng valid allow tests}} \times 100\%
\]

\[
\text{Negative pass rate}=\frac{\text{unauthorized tests bị deny đúng điểm enforcement}}{\text{tổng unauthorized tests}} \times 100\%
\]

Phải đo **cả hai**. Một hệ thống chặn tất cả lưu lượng có thể đạt 100% negative nhưng 0% positive; không thể coi là triển khai Zero Trust thành công.

### 10.2. Test matrix mẫu

| Nguồn/context | Đích/operation | Quyết định mong đợi | Evidence cần |
| --- | --- | --- | --- |
| Sales + laptop compliant | CRM HTTPS | Allow | PEP allow + app success |
| Sales + laptop compliant | Payroll HTTPS | Deny | PDP/PEP deny + không có bypass |
| Finance + unmanaged device | Payroll HTTPS | Deny/restricted theo policy | Posture reason + actual enforcement |
| Offboarded contractor | Admin portal/session cũ | Deny/revoked | HR event → IdP → PEP → app |
| CI service identity | Production RDP | Deny ngoài JIT/exception | Network + app auth evidence |
| Finance admin trong JIT window | Finance management API | Allow scoped | PAM lease, PEP, app audit |
| Finance admin sau JIT expiry | Same management API | Deny | Effective privilege removal |
| Remote user qua legacy VPN | Payroll private IP | Deny direct | Route/firewall logs, positive ZTNA control |
| Unmanaged client qua IPv6 | Admin URL IPv6 | Deny | IPv6 PEP/firewall evidence |

### 10.3. Timeout không phải bằng chứng policy đúng

Nếu kết nối trái quyền không thành công, nguyên nhân có thể là **DNS lỗi, đích chết, route sai hoặc firewall deny**. Một negative test đúng phải có **deny event/policy ID tại điểm kiểm soát mong muốn**, đồng thời có **positive control** chứng minh app vẫn khỏe.

### 10.4. Lateral movement surface

Các metrics hữu ích:

- Số **high-risk source–destination pairs** còn reachable ngoài policy.
- Số **administrative ports reachable** từ user subnets.
- Risk-weighted **cross-segment unauthorized paths**.
- Số bypass findings tồn tại trên **IPv4/IPv6, legacy VPN, public routes, third-party tunnels**.
- **Evidence coverage** cho từng path đã kiểm chứng (test date, source, protocol, deny point).

Không cố tình phát sinh lateral movement thật trên production để lấy số liệu; dùng **authorized reachability analysis, lab simulations và bounded connectivity tests**.

## 11. Đo session lifecycle và thu hồi quyền end-to-end

Một chương trình ZT cần xem **khả năng thay quyết định theo ngữ cảnh**, chứ không chỉ chấm điểm một lần lúc login. “Continuous verification” không nhất thiết kiểm tra lại toàn bộ policy trên **mỗi packet**; phải xác định **trigger, TTL, loại phiên và expected response**.

### 11.1. Tách bốn mốc thời gian

~~~text
t0: HR/EDR/IdP phát hiện offboarding hoặc posture thành noncompliant
t1: Risk/change event đến hệ PDP/identity lifecycle
t2: PDP/PEP thực thi deny/revoke decision
t3: New và active application access thật không còn usable

End-to-end effective revocation latency = t3 - t0
~~~

Chỉ báo “policy updated” ở **t2** có thể bỏ sót **existing WebSocket, SSH session, app cookie, API token hoặc cache** còn usable sau đó.

### 11.2. Các chỉ số khác nhau

| Chỉ số | Tại sao tách |
| --- | --- |
| **Time to block new login** | Chặn access mới từ danh tính đã revoke |
| **Time to stop existing ZTNA tunnel** | Session đang mở không tiếp tục truyền dữ liệu |
| **Time to invalidate app session** | App cookie/token không còn thực hiện operation |
| **Residual active sessions after SLO** | Đo tail risk từ long-lived sessions |
| **Time to disable privileged JIT access** | Đảm bảo không còn permission sau expiry |
| **Time to propagate device risk** | Đo latency từ EDR/MDM tới PDP/PEP |

### 11.3. Vì sao dùng p95/p99/max

Giả sử 100 phiên được thu hồi: **95 phiên trong 30 giây**, **4 phiên trong 2 phút**, nhưng **1 phiên còn hoạt động 2 giờ** vì app cookie chưa bị vô hiệu hóa. Trung bình không phản ánh đầy đủ **tail risk** cho tài khoản đặc quyền.

Hãy báo cáo **p50, p95, p99, maximum**, phân tầng theo user type/resource, và kiểm tra những trường hợp quá SLO. Không dùng “ticket closed” như proxy cho thời gian đã thực sự mất quyền.

### 11.4. Trigger coverage

Một bảng trigger thường gồm:

- HR offboarding/role transfer.
- MFA/IdP high-risk account event.
- MDM/EDR posture degradation.
- PAM/JIT lease expiry.
- Credential/token compromise và session revoke.
- Resource sensitivity policy change.
- SOC incident containment.

Mỗi trigger cần **event source, path tới PDP/PEP, SLO, test và owner**. Nếu một trigger có event nhưng không có quyền/khả năng terminate app session thì cần ghi **residual risk/compensating controls**.

## 12. Continuous verification: đo quyền sử dụng theo thời gian

Một metric tại **thời điểm login** khác trạng thái an toàn của **toàn bộ phiên**. Các phiên có thể kéo dài hàng giờ trong RDP/SSH, browser hoặc API access.

### 12.1. Chỉ số theo session-time

Ví dụ:

\[
\text{Compliant session-time ratio} = \frac{\text{thời lượng phiên nhạy cảm đáp ứng policy}}{\text{tổng thời lượng phiên nhạy cảm được quan sát}} \times 100\%
\]

Chỉ có thể tính đáng tin nếu biết **session start/end và những thay đổi context** đủ chính xác. Nếu logs mất đoạn, phải báo **unknown/insufficient telemetry**, không mặc định là compliant.

### 12.2. Phân biệt evaluation cadence và event-driven signals

Một hệ có thể:

- Reevaluate khi **token expire**.
- Reevaluate theo **periodic posture refresh**.
- Reevaluate khi có **risk event**.
- Terminate khi **policy/entitlement** thay đổi.
- Yêu cầu step-up khi truy cập **resource/action nhạy cảm**.

**Số lần re-evaluate càng nhiều không phải lúc nào càng tốt** nếu tạo UX không cần thiết, tải lớn hoặc phần lớn re-evaluation không dùng được signal mới. Đo **trigger-handling effectiveness và rủi ro còn lại**, không chỉ lượng policy checks.

### 12.3. Kiểm thử có kiểm soát

Để đo revocation trên môi trường được cấp quyền:

1. Tạo phiên test tới ứng dụng lab đang hoạt động.
2. Ghi **UTC timestamps và correlation ID**.
3. Kích hoạt một **test offboarding / JIT expiry / EDR posture event** đã được ủy quyền.
4. Thử **new connection** và **existing session operation** theo chu kỳ kiểm tra an toàn.
5. Xác định **điểm thời gian cuối cùng access còn usable**, giới hạn bởi sampling interval.
6. Đối chiếu HR/IdP/PDP/PEP/app logs; không tuyên bố precision cao hơn độ phân giải của test.
7. Khôi phục trạng thái test và lưu **evidence + exception** nếu vượt SLO.

Không thử thay posture của thiết bị nhân viên thật hoặc khóa tài khoản vận hành production ngoài change/IR process.

## 13. Đo detection và kết quả an ninh

### 13.1. Incident count là chỉ số dễ gây hiểu nhầm

Số confirmed incidents ít đi **có thể** do phòng ngừa tốt hơn, nhưng cũng có thể do:

- Tấn công thực ít hơn.
- Sensor/log coverage giảm.
- Quy trình phân loại incident thay đổi.
- Nhóm không đủ năng lực triage.
- Tài sản bị bỏ ngoài phạm vi telemetry.

Do đó **incidents per period** phải được đánh giá cùng **detection coverage, population size, threat exposure và confidence level**, không coi con số đơn lẻ chứng minh ZTNA làm giảm incidents bao nhiêu phần trăm.

### 13.2. Đo MTTD và containment time

| Mốc | Ý nghĩa |
| --- | --- |
| **t_event** | Thời điểm hành vi trái quyền bắt đầu hoặc được xác định sớm nhất |
| **t_detect** | Sensor/analyst xác nhận tín hiệu đáng xử lý |
| **t_triage** | Triage xác định phạm vi/độ ưu tiên |
| **t_contain** | Credentials/session/network paths thực bị vô hiệu hóa |
| **t_recover** | Dịch vụ và controls được khôi phục được kiểm chứng |

**MTTD** có thể đo \(t_{\mathrm{detect}}-t_{\mathrm{event}}\), **containment time** đo tới \(t_{\mathrm{contain}}\). Cần giải thích liệu dùng **incident start time** được điều tra hồi tố hay **event log time**, và báo cáo p95 khi đủ mẫu.

### 13.3. Sử dụng scenarios có ground truth

Vì incident hiếm và ground truth khó biết, nên bổ sung **controlled scenario tests**:

- Compromised test identity không có MFA đủ mức.
- Unmanaged device bị deny theo policy.
- Vendor credential vẫn thử kết nối sau offboarding.
- Attempt tới unauthorized internal app.
- Legacy VPN/public path bypass attempt.
- Existing session cố dùng app sau forced revoke.

Với mỗi test, ghi **expected result, detection alert, correlation, policy decision, response time và missed stage**.

### 13.4. Detection precision và recall khi có nhãn

Khi test/incident data có ground-truth labels đáng tin:

\[
\text{Precision} = \frac{TP}{TP+FP}, \qquad
\text{Recall} = \frac{TP}{TP+FN}
\]

Trong đó **TP** là cảnh báo đúng, **FP** là false alarm, **FN** là tình huống đáng cảnh báo đã bị bỏ sót. **Không** tính recall từ số alerts đơn thuần vì những sự kiện **FN không được quan sát** trong production có thể chưa biết; dùng **adversary simulation đã cấp quyền và kiểm thử được gắn nhãn**.

### 13.5. Blast radius và exposure window

Theo dõi:

- Số application/resources mà identity bị chiếm có **effective access** tại thời điểm incident.
- Số sensitive operations có bằng chứng xảy ra trong cửa sổ compromise.
- Thời gian **from credential compromise to loss of access** theo evidence.
- Số downstream resources/service credentials cần rotate.
- Chênh lệch scope giữa **đã được phép theo policy** và **thực sự được dùng**.

Không kết luận “không có exfiltration” chỉ từ việc không thấy log nếu **log coverage kém**.

## 14. Trải nghiệm truy cập và tỷ lệ từ chối nhầm

Một giải pháp khiến người dùng hợp lệ **không thể làm việc** sẽ tạo áp lực bypass policy, VPN ngoại lệ và shadow IT. Vì vậy usability là một phần của hiệu quả Zero Trust.

### 14.1. Authorized access success rate

\[
\text{Legitimate access success} = \frac{\text{eligible authorized requests/sessions hoàn tất thành công}}{\text{eligible authorized requests/sessions đã thử}} \times 100\%
\]

Định nghĩa “authorized” cần dựa trên **test identity/entitlement được xác minh hoặc incident review**, không dùng mọi request được PEP allow làm ground truth; PEP có thể allow sai.

### 14.2. Phân loại lỗi truy cập

| Lỗi | Dấu hiệu | Xử lý |
| --- | --- | --- |
| **True deny** | Identity/device không đủ điều kiện theo policy | Giữ deny, cung cấp thông tin phù hợp cho user |
| **False deny** | User compliant và có quyền nhưng bị chặn | Sửa policy/identity mapping/posture signals |
| **Network failure** | DNS/VPN/ZTNA connector không reachable | SRE/network troubleshooting, không mở Any–Any |
| **Authentication friction** | MFA/SSO lặp, push fatigue | Chọn assurance method, session policy và UX thích hợp |
| **Application failure** | PEP cho truy cập nhưng app 5xx | App/service ownership, không quy tội ZTNA ngay |
| **Client compatibility** | SSH/RDP/UDP/browser/proxy khác nhau | Test supported protocols/device modes |
| **Stale device context** | MDM/EDR sync chậm dẫn tới reject | Sửa telemetry path và TTL policy theo risk |

### 14.3. Helpdesk là sensor, không phải metric toàn diện

Theo dõi tickets theo **root cause**, tickets/1.000 eligible users, mean time to resolve và nhóm dễ bị ảnh hưởng. Ticket volume giảm có thể do **self-service tốt hơn** hoặc **người dùng ngừng báo lỗi**; phải ghép synthetic tests, real-user monitoring và surveys có phương pháp.

### 14.4. Behavioral risks

Quan sát các dấu hiệu áp lực workaround:

- User chuyển sang **personal email/cloud share** vì business app quá khó truy cập.
- Admin yêu cầu **permanent bypass exception** thay vì JIT.
- Team sử dụng **shared accounts** tránh step-up.
- Shadow VPN/SSH tunnels để đi vòng ZTNA.

Phản ứng phù hợp là **sửa UX/policy/availability** và quản trị exceptions, không chỉ tăng tỷ lệ deny.

## 15. SLI/SLO về hiệu năng và khả dụng

### 15.1. Đo từng chặng

~~~text
T_total_access =
  identity/MFA time
  + posture evaluation time
  + PDP decision time
  + gateway/connector establishment time
  + network/TLS handshake time
  + application initial response time
~~~

Đây là cách **phân rã khái niệm**, không nhất thiết các bước đều tuần tự trong mọi sản phẩm. Hệ đo nên ghi **timestamp tại từng chặng khi có thể** và tránh cộng đôi khi các bước xảy ra đồng thời.

### 15.2. Các SLI quan trọng

| SLI | Định nghĩa | Phân khúc |
| --- | --- | --- |
| **Access establishment time** | Từ hành động truy cập đến thời điểm ứng dụng usable | Device, network, user type, app, region |
| **PDP decision latency** | Thời gian đánh giá policy, không tính toàn bộ browser auth nếu tách | Policy complexity, IdP dependencies |
| **Connector/gateway success** | Eligible attempts đi qua thành công | Connector, region, app |
| **PEP availability** | Tỷ lệ thời gian đường truy cập được cung cấp theo service SLO | Zone, provider, disaster recovery |
| **p95/p99 application latency overhead** | Chênh lệch latency do kiến trúc access path dưới cùng điều kiện | Protocol, bandwidth, location |
| **Long-lived session stability** | SSH/RDP/streaming session disconnect không mong muốn | Duration, device, path |
| **MTTR do ZTNA incident** | Từ incident nhận diện đến restoration được xác minh | Root cause, severity |

### 15.3. Percentiles và error budgets

Chỉ dùng latency trung bình có thể che tail. Ví dụ giả định **95% phiên nhanh dưới 1 giây**, nhưng nhóm remote tại một vùng có **p99 > 20 giây** thì tỷ lệ hài lòng và công việc của nhóm đó vẫn bị ảnh hưởng.

Nên có **p50/p95/p99, error budget và SLO theo critical services**, tránh gộp một ứng dụng truy cập hàng triệu lần với admin workflow ít lần nhưng impact cao.

### 15.4. Fail-open không phải luôn là ưu tiên

Khi PEP/IdP mất khả dụng, có thể phát sinh yêu cầu cho truy cập trực tiếp để bảo đảm business continuity. Đây là quyết định **risk/availability trade-off**:

- High-risk sensitive resource có thể cần **fail-closed** và dự phòng ZTNA/IdP.
- Dịch vụ khẩn cấp có thể cần **break-glass path** độc lập được bảo vệ/audit.
- Temporary exceptions phải có **approver, TTL, affected scope và rollback**.

Đừng đánh giá availability “tốt” nếu có được nhờ **tự động mở full network access** khi ZTNA lỗi.

## 16. Đo chi phí, năng suất và lợi ích chương trình

### 16.1. Không quy tất cả savings cho ZTNA

Chi phí và lợi ích có thể gồm:

- Giảm vận hành **VPN concentrators, jump hosts, broad network ACL complexity** khi thật sự loại bỏ được hệ cũ.
- Giảm **thời gian onboarding/offboarding**, cấp quyền JIT và support.
- Giảm time-to-investigate nhờ **identity/session correlation** tốt hơn.
- Tránh **downtime** do policy error, tăng khả năng truy cập remote có kiểm soát.
- License, connector capacity, egress/network costs, integration, telemetry storage và training.

Không tuyên bố ZTNA **ngăn được X đồng tiền thiệt hại** chỉ dựa trên cost của một vụ việc giả định. ROI cần assumptions về xác suất, tác động, bằng chứng, và **sensitivity analysis**.

### 16.2. Một mô hình đánh giá minh bạch

~~~text
Measured annual program costs:
  ZTNA/IdP/EDR incremental license + infrastructure
  Integration and operations staff effort
  Gateway/connector/cloud egress/telemetry costs
  Training + migration + service disruptions

Measured operational benefits:
  Legacy VPN/jump infrastructure actually retired
  Helpdesk time saved (ticket reduction with comparable scope)
  Provisioning/offboarding hours reduced
  Incident triage hours reduced

Estimated risk reduction (separate scenario model):
  Threat scenario probability and impact ranges
  Control efficacy evidence and remaining bypass paths
  Confidence intervals and unmeasured assumptions
~~~

### 16.3. Quan sát trước–sau phải giữ cùng mẫu đo

Nếu số support tickets giảm khi toàn công ty chuyển sang một app mới, không thể quy nguyên nhân toàn bộ cho ZTNA. Nếu số nhân sự tăng 30%, so **raw ticket count** không đủ; có thể dùng tickets/**1.000 users** và phân nhóm ứng dụng/điều kiện tương đương.

Tương tự, **VPN costs giảm** chỉ được tính là lợi ích khi infrastructure/license đã thực sự retired, không phải chỉ còn ít user nhưng hệ cũ vẫn phải duy trì.

## 17. Chất lượng telemetry: điều kiện để tin KPI

Trước khi dựng dashboard cần đo **telemetry coverage**. Kết luận “zero unauthorized access” từ một hệ thống chỉ ghi log cho 60% ứng dụng không tương đương kết luận từ hệ thống có coverage đầy đủ.

### 17.1. Dữ liệu và chủ sở hữu

| Nguồn | Trường tối thiểu | Owner | Giới hạn |
| --- | --- | --- | --- |
| **HR/IdP lifecycle** | Principal, change type, event/effective time | HR/IAM | PII, đồng bộ chậm |
| **IdP/authentication** | User, auth method/assurance, result, session | IAM/SOC | Login không chứng minh network path |
| **MDM/EDR** | Device ID, posture result, signal timestamp | Endpoint security | Missing/stale signals |
| **PDP** | Policy ID/version, decision, reason, context | ZTNA policy owner | Decision không chứng minh enforcement |
| **PEP/ZTNA** | Session, resource, identity, allow/deny/revoke | ZTNA platform | Không thấy direct bypass |
| **Application/API** | User/session, action, business result | App owner | Không chứng minh access qua PEP |
| **Firewall/VPN/NAT** | Source/dest/port, route/action, NAT mapping | Network/SOC | Thiếu user identity nếu không correlate |
| **SIEM/Incident** | Alert ID, confidence, timestamps, containment | SOC/IR | Phụ thuộc detection coverage |
| **Inventory** | Canonical resource ID, owner, criticality, paths | CMDB/Architecture | Tài sản chưa phát hiện |

### 17.2. Event time và ingestion time

Hệ đo cần phân biệt:

- **event_time:** thời điểm offboarding/posture/risk event thực xảy ra.
- **received_time:** lúc hệ thu thập nhận event.
- **processed_time:** lúc PDP/PEP xử lý.
- **effective_revoke_time:** lúc client thật không còn làm thao tác được bảo vệ.

Nếu dùng riêng ingestion time, KPI có thể che độ trễ dữ liệu. Nếu clocks lệch, revocation latency có thể âm. Cần **UTC, clock sync, event IDs và data-quality warnings**.

### 17.3. Completeness, freshness, consistency

| Data quality | Câu hỏi |
| --- | --- |
| **Completeness** | Bao nhiêu PEP events có resource, principal, device, session, decision và policy version? |
| **Freshness** | p95 ingestion lag là bao nhiêu? Alert đến SOC trễ mấy phút? |
| **Consistency** | User/device/resource ID có map nhất quán giữa IdP, PEP, app và firewall? |
| **Uniqueness** | Event có bị duplicate vì retry/collector failover? |
| **Validity** | Decision reason, posture TTL và risk tier có đúng schema không? |
| **Coverage** | Resource/PEP nào không phát log? |

Không được tự điền principal không biết bằng **tài khoản gần nhất sử dụng cùng NAT IP**. Với incomplete logs, báo **unknown**, không mặc định compliant.

### 17.4. Sampling và log gaps

Flow logs có thể sampling/aggregation, nhiều PEP connectors có retention hoặc verbosity khác nhau. Không dùng sampled logs để kết luận **đã đếm chính xác 100% flows** nếu chưa xác nhận sampling model.

**Không thấy deny event** có thể vì sensor sai điểm, log chưa bật hoặc traffic đi ngoài PEP. Hãy tìm **network-independent evidence** cho các đường bypass.

## 18. Data contract để tính metric tái lập

Một schema chuẩn hóa giúp metrics không phụ thuộc hoàn toàn vào tên log riêng của ZTNA vendor:

~~~json
{
  "event_id": "evt-demo-012",
  "event_time": "2026-11-28T05:30:42Z",
  "ingest_time": "2026-11-28T05:30:44Z",
  "environment": "production",
  "source": "ztna-pep",
  "resource_id": "app-payroll",
  "resource_tier": "critical",
  "principal_id": "user-test-17",
  "principal_type": "human",
  "device_id": "device-test-09",
  "device_posture": "compliant",
  "device_signal_age_seconds": 26,
  "auth_assurance": "phishing-resistant",
  "policy_id": "payroll-access-v8",
  "decision_id": "decision-demo-038",
  "decision": "allow",
  "enforcement_point": "ztna-pep-prod-a",
  "session_id": "session-demo-01",
  "source_network_zone": "managed-remote",
  "destination_protocol": "HTTPS",
  "destination_port": 443,
  "correlation_id": "trace-demo-012",
  "test_or_production": "test",
  "data_quality": "complete"
}
~~~

Đây là **schema học tập**, không phải raw log từ một sản phẩm cụ thể. Những nhãn **phishing-resistant**, **compliant**, **complete** chỉ có nghĩa khi phương thức xác thực, posture test và data-quality checks thật sự đáp ứng điều kiện tương ứng.

### 18.1. Chuẩn hóa định danh

~~~text
HR immutable person ID
  -> IdP principal / authentication event
  -> ZTNA principal / PDP decision ID
  -> Device ID / MDM/EDR posture event
  -> PEP session ID
  -> App user/session ID / business action
  -> Network source/NAT flow identifiers
  -> Incident or synthetic test correlation ID
~~~

Email address không luôn là khóa bất biến; có thể bị đổi hoặc tái sử dụng. Cần quản lý identity merges/splits, lifecycle và canonical asset IDs.

### 18.2. Vì sao phải ghi policy version

Một request cùng user/resource có thể hôm qua được allow nhưng hôm nay bị deny vì **group membership, policy version, risk event, posture change hoặc resource sensitivity** thay đổi. Nếu thiếu policy ID/version và context, khó kết luận metric biến động do policy tốt lên hay do lỗi.

### 18.3. Tách synthetic tests khỏi production

Gắn **test ID, source environment, test identity** để không đưa các lần deny synthetic vào thống kê “real attacker attempts”. Nhưng vẫn giữ test evidence cho **control validation**; không xóa test logs khỏi nơi kiểm toán.

## 19. Pipeline và công thức KPI

### 19.1. Chọn windows phù hợp

Ví dụ mỗi metric có thời gian riêng:

~~~text
VERIFIED_CRITICAL_ACCESS_PATH_COVERAGE
  Window: monthly
  Population: critical production access paths, including unonboarded
  Numerator: positive + negative tests with current PEP/policy
  Unknown: unvalidated or missing inventory, reported separately
  Owner: Network + Security Assurance

PRIVILEGED_AUTH_ASSURANCE
  Window: rolling 7 days
  Population: privileged access attempts to protected resources
  Numerator: decisions conforming to high-assurance policy
  Owner: IAM/PAM

EFFECTIVE_REVOCATION_LATENCY
  Window: each offboarding/risk event; report monthly percentiles
  Start: authoritative event effective timestamp
  End: app access no longer usable as verified
  Owner: IAM + ZTNA + app owners
~~~

Không dùng **login event count** làm denominator cho application coverage; ứng dụng ít truy cập sẽ biến mất khỏi tỷ lệ dù rất quan trọng.

### 19.2. Tính coverage qua SQL minh họa

~~~sql
-- PSEUDO-SQL: không chạy trực tiếp trên production.
-- Các bảng đã normalize, kiểm tra tính đúng hạn của test results.
WITH in_scope AS (
    SELECT resource_id, risk_weight
    FROM resource_inventory
    WHERE environment = 'production'
      AND private_access_required = TRUE
),
verified AS (
    SELECT DISTINCT resource_id
    FROM enforcement_validation
    WHERE validation_status = 'PASS'
      AND positive_test_pass = TRUE
      AND negative_bypass_test_pass = TRUE
      AND telemetry_complete = TRUE
      AND validated_at >= DATE '2026-11-01'
)
SELECT
    COUNT(v.resource_id) AS verified_count,
    COUNT(*) AS scope_count,
    100.0 * COUNT(v.resource_id) / NULLIF(COUNT(*),0) AS coverage_pct,
    100.0 * SUM(CASE WHEN v.resource_id IS NOT NULL
                     THEN s.risk_weight ELSE 0 END)
        / NULLIF(SUM(s.risk_weight),0) AS weighted_pct
FROM in_scope s
LEFT JOIN verified v ON v.resource_id = s.resource_id;
~~~

**Giới hạn:** SQL dialect và table design khác nhau; validation phải gắn với **đúng app/path, policy revision, enforcement version và test TTL**. Không giữ trạng thái PASS mãi khi PEP/firewall/routes đổi.

### 19.3. Xử lý duplicates và missing data

Khi tính ratio từ events:

1. Dùng canonical **event_id/session_id/decision_id** tránh đếm retry duplicates.
2. Chọn **event-time window** và cho phép ingest delay có kiểm soát.
3. Phân biệt initial decision, reevaluation decision và repeated reconnect.
4. Báo riêng **unknown/missing**, không loại bỏ làm đẹp tỷ lệ.
5. Tách production traffic khỏi synthetic tests.
6. Kiểm chứng ngẫu nhiên với raw source records đủ quyền và data minimization.

### 19.4. Revocation measurement

~~~text
start = authoritative HR/IdP/EDR risk event effective timestamp
end   = first verified time the affected access can no longer
        perform a protected operation, with positive app control
latency = end - start
~~~

Nếu test hiện trạng mỗi 30 giây, không tuyên bố độ chính xác tới mili giây. Nếu không có cách xác minh app session cũ, kết quả là **unknown / partial measurement**, không gán PASS.

### 19.5. Confidence và uncertainty

Khi dùng test samples để suy từ mẫu ra toàn bộ tổ chức, công khai **selection method, sample size, risk stratification, test independence, confidence limits hoặc uncertainty**. Chạy 20/20 tests đạt chỉ chứng minh **20 kịch bản được chọn đạt trong điều kiện kiểm thử**, không chứng minh “100% Zero Trust security”.

## 20. Dashboard giả định: cách đọc được rủi ro

Các số dưới đây **là ví dụ minh họa**, không phải dữ liệu thực tế.

| Metric | Giá trị giả định | Mục tiêu nội bộ ví dụ | Hành động |
| --- | ---: | --- | --- |
| Private applications verified | **85/100 = 85%** | ≥ 90% | Ưu tiên onboarding + bypass tests |
| Critical applications verified | **18/20 = 90%** | 100% | Xử lý hai critical gaps |
| Unauthorized direct paths reachable | **3** | 0 ngoài exceptions | Chặn/compensate theo risk |
| Privileged strong auth conformance | **97%** | ≥ 99% | Đóng weak fallback |
| Device posture freshness | **93%** | ≥ 98% | Sửa MDM/EDR sync |
| Positive authorized tests | **188/200 = 94%** | ≥ 99% | Giảm false denies |
| Negative unauthorized tests | **196/200 = 98%** | 100% critical | Điều tra 4 failures |
| p95 effective revoke | **7 phút** | ≤ 5 phút | Xem app session invalidation |
| Event correlation completeness | **91%** | ≥ 98% | Sửa canonical IDs |
| p95 access connect time | **2,4 giây** | ≤ 2 giây | Đo IdP/PEP/region |
| Expired policy exceptions | **6** | 0 | Review/rút quyền |

### 20.1. Đừng bị tỷ lệ trung bình đánh lừa

Nếu 4 negative failures đều là **Payroll/admin bypass paths**, metric 98% không phù hợp để đánh giá “đạt”. Gating condition có thể là: **không còn critical unauthorized paths**, bất kể tỷ lệ chung.

### 20.2. Tách ba dashboard trục

- **Protection:** critical path coverage, bypass risks, least-privilege findings, revoke latency.
- **Assurance:** positive/negative tests, log completeness, policy drift, unknown signals.
- **Experience:** eligible access success, latency, availability, support tickets, SLO.

Nếu buộc tổng hợp thành điểm, cần công khai **weights, risk gating rules, exceptions, unknown population và raw metric drill-down**.

## 21. So sánh trước–sau và đánh giá tác động

### 21.1. Before/after không đủ chứng minh nhân quả

Giả sử unauthorized-access incidents giảm 30% sau ZTNA rollout. Đồng thời tổ chức có thể đã **thay EDR, sửa cloud IAM, triển khai network segmentation, nâng cấp SIEM, thay workforce size hoặc chịu ít attack attempts hơn**.

Không thể quy toàn bộ chênh lệch cho ZTNA nếu không kiểm soát/giải thích những yếu tố đó.

### 21.2. Phương pháp so sánh thực dụng

1. Chốt **baseline definitions** trước rollout.
2. Ghi **deployment timeline** theo app/path/user group.
3. Chọn các **cohorts tương đương** về risk, vùng, role và ứng dụng khi có thể.
4. So sánh chỉ số trong từng cohort trước–sau, không chỉ global aggregate.
5. Có thể cân nhắc **difference-in-differences** khi các nhóm rollout khác thời điểm và assumptions như xu hướng song song hợp lý.
6. Ghi **confounders**: MFA, EDR, workforce, firewall, logging/alert changes.
7. Đưa ra **confidence/limitations**, không chỉ một phần trăm đẹp.
8. Ghép với **technical validation** như negative bypass, revoke và identity tests.

### 21.3. Không hạ bảo mật để có A/B test

Không chủ động tắt MFA, mở subnet hay làm lộ admin endpoint chỉ để tạo nhóm đối chứng “sạch”. Ưu tiên **natural rollout, staging tests, historical comparisons và risk-informed models** mà vẫn giữ controls bắt buộc.

### 21.4. Seasonality và population drift

Mức sử dụng payroll cuối tháng, giờ làm theo ca, dịp nghỉ, remote travel và thay đổi employee count đều làm metric biến động. So **raw deny count** qua hai giai đoạn có volume khác nhau không đủ; nên dùng normalized rates cùng phân tầng thích hợp.

Nếu không có baseline/log coverage đáng tin, ghi rõ **“chưa đủ dữ liệu quy kết tác động an ninh cho ZTNA”** thay vì đưa một phần trăm không thể kiểm chứng.

## 22. Quản trị KPI: từ số liệu tới quyết định

Một metric tốt phải dẫn tới **hành động và owner**, không chỉ một đồ thị.

~~~mermaid
flowchart TD
    M["Metric ngoài ngưỡng / critical finding"] --> Q["Verify data quality + scope"]
    Q --> R["Risk tier + assign owner"]
    R --> A["Remediation hoặc temporary approved exception"]
    A --> V["Positive/negative validation tests"]
    V --> C["Close finding với evidence"]
    C --> D["Monitor drift và theo dõi residual risk"]
~~~

### 22.1. Gắn metric với quy trình

| Finding | Chủ sở hữu điển hình | Bước tiếp theo |
| --- | --- | --- |
| Critical app còn đường direct public/VPN | Network + AppSec | Chặn đường bypass, test positive/negative |
| Privileged access thiếu assurance | IAM/PAM | Đóng weak MFA fallback, test step-up |
| Posture signal stale trên nhóm tài chính | EDR/MDM + ZTNA | Sửa pipeline, xác minh freshness + deny |
| p95 revocation vượt SLO | IAM + ZTNA + app team | Đo latency HR→PDP→PEP→app, sửa session invalidation |
| Legitimate access failures tăng | SRE + Identity | Điều tra IdP, gateway, certificate, DNS và policy |
| SIEM correlation giảm | Security data platform | Xác minh canonical IDs và ingestion |
| Policy exceptions quá hạn | Risk owner | Revoke hoặc reapprove có thời hạn |
| Excess privilege trong nhóm vendor | IAM + Application owner | Review contractual access, least privilege |

### 22.2. Exception phải đo riêng

Một ngoại lệ hợp lệ phải có **scope, business owner, risk owner, lý do, compensating controls, expiry, review cadence và rollback**. Không loại mọi ngoại lệ khỏi denominator để tăng KPI; nên có **Exception Debt** (số, tuổi, risk-weight).

### 22.3. Evidence package khi đóng finding

~~~text
Finding ID + risk owner:
Resource identity, criticality, source path:
Expected control objective:
Before policy/config and observed access:
Change ticket, actor, approved revision:
After policy/config + effective route/PEP:
Positive valid-access test and app health:
Negative unauthorized test and enforcement evidence:
Log correlation and policy decision ID:
Residual risk / exception expiry:
Owner sign-off + date:
~~~

Đừng đóng finding chỉ vì người triển khai nói “đã cập nhật policy” khi **không có test thực** hoặc test đi từ sai source zone.

## 23. Case study 1: coverage cao nhưng Payroll còn đường bypass

### 23.1. Bối cảnh giả định

Một tổ chức có **100 ứng dụng private** được inventoried, **95 ứng dụng** đã được đưa vào dashboard ZTNA. Báo cáo ban đầu tuyên bố **95% hoàn thành**, nên lãnh đạo muốn kết thúc dự án.

Trong một validation review, phát hiện:

- 95 ứng dụng đã có **ZTNA resource definitions** nhưng chỉ 82 được kiểm chứng các đường đi thực.
- Một ứng dụng **Payroll** critical đã có ZTNA web access nhưng **admin port còn reachable qua legacy VPN**.
- 5 ứng dụng chưa onboard có **3 resource high risk**.
- Bypass tests chưa từng chạy trên **IPv6**.

### 23.2. Vì sao điểm 95% là sai mục tiêu?

| Chỉ số | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| Configured ZTNA apps | 95/100 = 95% | Chỉ mức khai báo |
| Verified enforced apps | 82/100 = 82% | Có positive/negative evidence theo tiêu chí |
| Critical unverified resources | Có, gồm Payroll | Critical risk chưa được giải quyết |
| Payroll legacy admin bypass | 1 verified path | Một trust boundary có đường đi vòng |
| IPv6 bypass test coverage | Chưa xác minh | Không được ghi nhận là đã chặn |

Không thể tuyên bố 95% “bảo vệ hiệu quả” từ con số configured; phải báo **95% declared, 82% validated** và risk exceptions riêng.

### 23.3. Phản hồi và đo lại

1. Gắn canonical IDs và kiểm kê **web, admin, API, VPN route và IPv6 endpoints** của Payroll.
2. Chạy **positive ZTNA test** từ Finance managed device.
3. Chạy **negative direct access test** từ legacy VPN nguồn được ủy quyền.
4. Đối chiếu **firewall/route logs** xác định traffic bypass thật.
5. Chặn admin direct path hoặc dùng **bastion/JIT path có enforcement** được phê duyệt.
6. Test lại và cập nhật **effective path coverage + outstanding critical risks**.
7. Bổ sung asset discovery và **validation freshness**; không giữ PASS sau thay route.

**Bài học:** ưu tiên **verified critical risk** hơn lượng tài nguyên được nhập vào portal.

## 24. Case study 2: thu hồi tài khoản nhanh nhưng session còn usable

### 24.1. Bối cảnh

HR đánh dấu một nhân viên nghỉ việc lúc **10:00 UTC**. IdP khóa account lúc **10:01**, ZTNA không cho login mới lúc **10:02**. Dashboard báo “access revoked in 2 minutes”. Tuy nhiên một **browser app session cookie** còn được ứng dụng chấp nhận cho tới **11:30**.

### 24.2. Tách bốn bước

~~~text
10:00  HR offboarding effective
10:01  IdP account disabled
10:02  PEP blocks new sessions
11:30  Existing application session finally invalidated

New-login block latency   = 2 phút
End-to-end effective revoke latency = 90 phút
~~~

Các con số là **ví dụ giả định**. Khi thời điểm thực tế chỉ được lấy mẫu, phải báo khoảng đo/uncertainty.

### 24.3. Nguyên nhân có thể

- Application session cookie có **TTL dài** và không nhận logout/revoke event.
- PEP chỉ chặn **new session establishment**, không kill active TCP connection.
- JWT/API token được validate local cho tới expiration.
- Event từ HR/IdP không propagate tới application/session store.
- Có một **secondary direct access path** bypass PEP.

### 24.4. Khắc phục và measurement

1. Định nghĩa SLO riêng cho **new access vs existing access**.
2. Ghi **authoritative t0, t1, t2, t3** từ HR/IdP/PEP/app.
3. Hỗ trợ **session invalidation/back-channel logout/short TTL** theo khả năng ứng dụng.
4. Với privileged workflows, cân nhắc **continuous session control/JIT scopes**.
5. Test existing session sau revoke trên **tài khoản thử**, có positive app control.
6. Thu **p95/max tail latency** theo ứng dụng; không chỉ trung bình.
7. Kiểm tra downstream tokens/credentials nếu incident có dấu hiệu bị xâm phạm.

**Bài học:** “account disabled” không đồng nghĩa **mọi phiên truy cập tới dữ liệu đã vô hiệu hóa**.

## 25. Case study 3: posture policy tạo nhiều false denies

### 25.1. Bối cảnh

Chương trình Zero Trust bổ sung quy tắc “EDR healthy trong 5 phút gần nhất” cho ứng dụng kế toán. Sau rollout:

- Tỷ lệ denied access attempts tăng.
- Helpdesk báo nhiều laptop compliant bị khóa khi roaming.
- Dashboard bảo mật diễn giải deny rate tăng là **“ZTNA chặn tấn công tốt hơn”**.

Điều tra phát hiện **MDM/EDR signal ingestion trễ** trên một số networks; device healthy nhưng PDP chỉ thấy dữ liệu stale.

### 25.2. Đo lại theo nguyên nhân

| Metric | Diễn giải đúng |
| --- | --- |
| **Raw deny count** | Không đủ để biết tấn công hay lỗi policy |
| **Stale signal rate** | Phản ánh chất lượng data/posture freshness |
| **False deny rate ở valid test cohort** | Đo lỗi trải nghiệm hợp lệ |
| **Policy bypass negative tests** | Đo khả năng chặn device thật sự noncompliant |
| **Ingestion lag p95** | Đo pipeline delay từ EDR/MDM đến PDP |
| **Exception requests/age** | Đo áp lực workaround và governance debt |

### 25.3. Hành động

1. Ghi **source signal timestamps** và PDP decision reason.
2. Kiểm tra agent/network/collector sync, clock offset và TTL.
3. Tách **unknown, stale, noncompliant** thay vì gộp cả ba là một.
4. Sửa ingestion bottleneck, làm rõ risk-based failure behavior.
5. Test **compliant positive** và **noncompliant negative** song song.
6. Theo dõi **security pass rate + p95 access latency + false denies**, không hy sinh control một cách thiếu quản trị.

**Bài học:** một control chặt trên giấy nhưng dữ liệu đầu vào kém có thể **tạo gián đoạn mà không tăng an toàn thực**.

## 26. Case study 4: vendor chỉ được cấp app access nhưng VPN legacy còn tồn tại

### 26.1. Bối cảnh giả định

Một nhà thầu được cấp ZTNA quyền tới một **maintenance web app** theo ca làm việc. Phần lớn các phiên đã đi qua PEP đúng. Tuy nhiên hợp đồng cũ từng cấp **VPN account với route tới server subnet** và quyền đó chưa được gỡ.

### 26.2. Những metric dễ bỏ sót

| Metric thường thấy | Vì sao không đủ |
| --- | --- |
| 100% vendor ZTNA sessions MFA | Không đếm VPN sessions ngoài PEP |
| Maintenance app có resource policy | Không chứng minh subnet admin ports không reachable |
| Không có ZTNA denies bất thường | VPN path có thể không xuất hiện trong logs |
| 0 security incidents tháng này | Không chứng minh quyền tồn tại là đúng |

### 26.3. Validation và remediation

1. Tạo **identity/access inventory** hợp nhất ZTNA, VPN, cloud IAM, application credentials.
2. Xác định **đích và nguồn VPN route** đang có hiệu lực.
3. Chạy bounded test **vendor test identity → unauthorized admin port** trong lab/scope được phép.
4. Thu **deny/allow evidence** tại VPN/firewall/host; không dựa chỉ vào ZTNA logs.
5. Thu hồi standing VPN permission nếu không còn cần; nếu business cần ngoại lệ, giới hạn CIDR/port/JIT theo approval.
6. Theo dõi **vendor access-path verified coverage** và **residual legacy grants**.
7. Xác minh user hợp lệ vẫn vào được maintenance app qua PEP sau thay đổi.

**Bài học:** Zero Trust hiệu quả khi **tập đường truy cập thực giảm theo least privilege**, không chỉ khi người dùng bắt đầu dùng một cổng đăng nhập mới.

## 27. Threat-model-driven validation: mỗi rủi ro một test

Thay vì chỉ chọn 10 test dễ chạy, hãy gắn test với những **threat scenarios** của tổ chức.

| Threat | Kiểm thử được ủy quyền | Control evidence | Security outcome |
| --- | --- | --- | --- |
| Credential theft | Test identity có password nhưng thiếu factor mạnh | IdP/PEP deny/step-up | Không vào app nhạy cảm |
| Stolen refresh token/session | Test revoke token và existing session | PDP/PEP/app session invalidation | Mất access trong SLO |
| Rogue/unmanaged device | Device posture fixture thiếu EDR/MDM | Posture reason + deny | Không đạt compliant access |
| Unauthorized lateral movement | User source thử management port không được cấp | Network deny + no direct bypass | Không có reachability ngoài policy |
| Public app exposure | Test app direct hostname/IP từ approved test network | Firewall/direct-path denial | Không bypass ZTNA |
| Legacy VPN fallback | Test từ VPN account/route có quyền | VPN/firewall/PEP evidence | App only scoped access |
| Excess privilege | Test role không có entitlement thử protected action | ZTNA + app authorization deny | Least privilege |
| Offboarding event | HR/IdP test trigger | Revocation timeline | Tất cả required sessions bị vô hiệu |
| PEP/IdP outage | Controlled staging failure | SLO metrics + secure recovery | Không fail-open trái policy |
| Policy drift | IaC test thay broad grant | Review/alert + blocked deployment | Unauthorized change bị phát hiện |
| Device signal loss | Test MDM delayed | Unknown/stale behavior | Không mặc định compliant |
| IPv6/alternate path | Test từ IPv6/secondary route | Dual-stack network deny | Không escape via IPv6 |

### 27.1. Kiểm thử hiệu quả chứ không chỉ kiểm thử connectivity

Một test pass nên ghi:

~~~text
Test ID / threat scenario:
Authorized tester / scope / time window:
Source principal and device attributes:
Source network (office/VPN/remote/IPv6):
Resource ID, protocol/port, app action:
Expected allow/deny and enforcement point:
Observed PDP decision / policy version:
Observed PEP/network/app outcome:
Positive control confirming resource healthy:
Log/flow correlation IDs:
Pass/fail, uncertainty, owner, remediation:
~~~

**Một timeout đơn lẻ không chứng minh security policy**. Cần xác nhận **đúng source/identity và deny tại đúng điểm**, cộng positive control.

### 27.2. Không gây hại trong test

Tuyệt đối không chạy các thao tác gây gián đoạn hay truy cập trái phép trên hệ thống người khác. Với môi trường production, ưu tiên:

- Read-only resource/route/policy inspection.
- Reachability analysis do provider hỗ trợ.
- Test identities đã tạo sẵn, test endpoints không chứa dữ liệu thật.
- Bounded connection checks và valid read operations.
- Staging/tabletop cho failover/compromised token/EDR loss.

Nếu cần thay firewall hoặc revoke thật, dùng **change process, approval, rollback và communication**.

## 28. Phòng tránh “good metrics, bad security”

**Goodhart's law** có thể diễn đạt: khi một thước đo trở thành mục tiêu duy nhất, người ta có thể tối ưu thước đo thay vì kết quả thực. Trong Zero Trust:

| Anti-pattern | Vì sao gây hại | Metric/guardrail thay thế |
| --- | --- | --- |
| Đếm apps trong portal, bỏ qua bypass | Coverage đẹp nhưng direct access vẫn mở | Verified path coverage + bypass findings |
| Đẩy deny rate lên tối đa | Chặn users hợp lệ | Positive + negative test pass rates |
| Giảm alert bằng cách tắt detections | Dashboard yên nhưng không thấy attack | Detection test recall + sensor coverage |
| Chỉ báo latency p50 | Tail users gặp gián đoạn | p95/p99 theo khu vực/resource |
| Đóng ticket khi policy deployed | Session có thể chưa mất quyền | Effective app-level validation |
| Gộp mọi MFA là phishing-resistant | Assurance yếu bị đánh giá quá cao | Auth method-level policy conformance |
| Loại all exceptions khỏi denominator | Residual risk biến mất trên dashboard | Exception risk, age, scope riêng |
| Chỉ đếm human users | Service tokens/CI đường khác chưa được kiểm soát | Human + machine identity coverage |
| Không phân biệt unknown với pass | Missing logs bị coi là compliant | Unknown data-quality percentage |
| Gộp high-risk với low-risk | Một critical gap bị che | Risk-weighted metrics + critical gating |
| Không giữ baseline scope | So sánh trước/sau không có ý nghĩa | Frozen cohort + population changes |
| Chỉ đo IdP revoke | Active app sessions còn usable | End-to-end revoke latency |

Một chương trình trưởng thành phải cho phép dashboard **hiện ra những điều chưa biết hoặc chưa đạt**, không ép mọi ô thành màu xanh.

## 29. Quyền riêng tư, lưu trữ và độ tin cậy của bằng chứng

Zero Trust telemetry có thể chứa **định danh nhân sự, lịch sử truy cập, posture thiết bị, vị trí mạng, hành vi ứng dụng và thông tin sự cố**. Một hệ đo lường chỉ được coi là an toàn nếu chính nó có governance.

### 29.1. Thu thập tối thiểu theo mục tiêu

- Chỉ thu **trường cần thiết** cho security objective, SLI hoặc điều tra có thẩm quyền.
- Không gửi **password, access/refresh token, private key, cookie hoặc raw Authorization header** vào metric events.
- Giữ riêng **business payload/PII** với metadata phục vụ KPI khi có thể.
- Pseudonymize user/device identifiers cho dashboard tổng quan; cho phép re-identification có kiểm soát khi thực sự điều tra.
- Giới hạn người có thể xem **full event-level logs**, đặc biệt dữ liệu của nhân sự và quản trị viên.
- Xác định retention, legal basis, deletion/access requests và data-residency theo quy định áp dụng.

### 29.2. Integrity và tamper-evidence

Nếu những identity có quyền sửa policy đồng thời có quyền xóa log, một incident có thể mất bằng chứng. Cần:

- Tách quyền **PDP/PEP administration** khỏi **SIEM/audit administration** khi khả thi.
- Gửi log tới backend có **write restrictions, retention và integrity controls**.
- Ghi audit cho thay đổi **metric definitions, data pipelines, alert rules và dashboard filters**.
- Theo dõi **log pipeline outage và clock skew** như security incidents khi ảnh hưởng khả năng truy vết.

### 29.3. Không xếp hạng cá nhân bằng dữ liệu chưa được giải thích

Một user có nhiều denied requests có thể đơn giản là **client retry lỗi**, một robot polling hoặc ứng dụng mới chưa được policy cập nhật. Không kết luận cá nhân có hành vi xấu từ deny count, location hay posture alone. Cần **bối cảnh, điều tra hợp lệ và chính sách quyền riêng tư**.

### 29.4. Metric transparency

Mỗi dashboard nên có:

~~~text
Data source / source owner:
Last ingestion time / reporting window:
In-scope population and denominator:
Unknown/missing percentage:
Numerator and exact pass condition:
Aggregation and deduplication rules:
Known sampling biases:
Validation date and owner:
Risk exclusions / approved exceptions:
Change history for metric definition:
~~~

Điều này giúp người đọc biết metric đáng tin đến đâu và tại sao hai kỳ báo cáo khác nhau.

## 30. Lộ trình triển khai hệ đo lường Zero Trust

Không nên chờ đến khi “toàn bộ Zero Trust xong” rồi mới đo; cũng không nên triển khai 50 chỉ số không có owner. Một lộ trình tham khảo có thể chia theo giai đoạn.

### Giai đoạn A — Xác định phạm vi và baseline

1. Chọn **critical business journeys**: Payroll, CRM, source repository, admin plane, dữ liệu khách hàng.
2. Kiểm kê **apps, protocols, identity types, devices, legacy access paths** từ nhiều nguồn.
3. Chọn **risk tier** và owner cho mỗi resource.
4. Chốt control objectives và các metric definitions với denominator chính xác.
5. Xác định **data-quality gaps**: thiếu PEP logs, thiếu MDM freshness, thiếu inventory.
6. Thu baseline **coverage, direct exposure, revoke latency và authorized access SLI**.

### Giai đoạn B — Xây telemetry và xác minh control

1. Chuẩn hóa IDs giữa HR/IdP/PEP/EDR/app/network.
2. Thu **policy version, decision, session ID và event timestamps**.
3. Tạo **positive/negative tests** trên môi trường được phê duyệt.
4. Kiểm tra **public/VPN/IPv4/IPv6/partner access paths** với source phù hợp.
5. Thiết lập dashboard với **coverage, bypass, session lifecycle, UX**.
6. Đánh dấu **unknown** rõ ràng, không biến “thiếu dữ liệu” thành pass.

### Giai đoạn C — Risk-based remediation

1. Ưu tiên **critical unauthorized paths** hơn các metric ít ảnh hưởng.
2. Sửa **IdP/MFA/posture/RBAC/policy** cùng các đường network bypass.
3. Đo **effective revoke**, khắc phục app session/token persistence.
4. Thiết lập **exception register và owner/expiry**.
5. Theo dõi **policy false denies/availability** để không tạo động lực bypass.
6. Tự động kiểm thử và cảnh báo **policy/route/resource drift**.

### Giai đoạn D — Đánh giá tác động và cải tiến liên tục

1. Báo trend có ghi **scope changes và control deployments**.
2. Đánh giá detection/incident outcomes cùng **sensor coverage và threat volume**.
3. So sánh các nhóm tương đồng hoặc rollout cohorts khi có khả năng.
4. Diễn tập **credential compromise, posture failure, revocation và PEP outage** trên môi trường được phép.
5. Rà soát **chi phí vận hành, VPN retirement, helpdesk và latency SLO**.
6. Báo cáo **residual risk, unknowns, exceptions và plan tiếp theo**, không chỉ mức độ hoàn thành.

### 30.1. Ma trận RACI mẫu

| Nhiệm vụ | Responsible | Accountable | Consulted |
| --- | --- | --- | --- |
| Resource inventory và classification | App owner/CMDB team | Enterprise architecture | Security/Risk |
| Identity assurance metrics | IAM/PAM | IAM lead | SOC/App owner |
| Device posture metrics | EDR/MDM team | Endpoint security lead | HR/Privacy |
| PEP/session enforcement evidence | ZTNA/Network platform | Network security lead | SRE/App owner |
| Bypass/path tests | Network + Security Assurance | Security assurance owner | App/network owners |
| Incident metrics and detection | SOC/IR | Security operations lead | IAM/App/Network |
| Authorized UX and SLO | SRE/Service owner | Business service owner | Helpdesk/ZTNA |
| Data governance/retention | Security data platform | Data governance owner | Privacy/Legal |
| Risk acceptance/exception | Risk owner | Business risk accountable | Security/Compliance |

**RACI chỉ là mẫu**. Điều quan trọng là mỗi metric có owner và người chịu trách nhiệm đóng vấn đề.

## 31. Những sai lầm thường gặp khi đo hiệu quả

1. **“Đã bật ZTNA = đã đạt Zero Trust.”** Cần kiểm chứng identity, paths, devices, privileges và outcomes.
2. **“Đếm số ứng dụng trong portal là coverage.”** Chỉ là configured coverage nếu bypass chưa test.
3. **“100% MFA enrollment nghĩa 100% sensitive access có MFA mạnh.”** Phải xét assurance của từng policy/attempt.
4. **“Private IP là resource đã bảo vệ.”** VPN/peering/insider path vẫn có thể reachable.
5. **“Không thấy traffic ở PEP nghĩa không ai dùng resource.”** Có thể có direct access bypass.
6. **“Deny rate cao luôn tốt.”** Có thể khóa user hợp lệ.
7. **“Deny rate thấp chứng minh ít bị tấn công.”** Có thể policy/telemetry yếu.
8. **“Chỉ cần negative tests.”** Chặn tất cả connections cũng có negative pass cao.
9. **“Một timeout chứng minh firewall chặn đúng.”** DNS/app outage có thể tạo timeout.
10. **“Tài khoản bị disable nghĩa mọi existing sessions chết.”** App cookies/API tokens có thể còn usable.
11. **“Revoke KPI đo từ lúc PEP nhận event là đủ.”** Cần HR/EDR t0 và app t3.
12. **“Mọi service cần cùng revoke SLO.”** Critical admin và low-risk session có impacts khác.
13. **“Chỉ đo login posture.”** Device signal có thể trở thành stale trong phiên.
14. **“Unknown device posture = compliant.”** Thiếu signal phải có failure behavior rõ.
15. **“NetworkPolicy/ZTNA thay app authorization.”** User vẫn cần quyền đúng operation/data.
16. **“Số policies càng nhiều càng an toàn.”** Có thể có wildcard/cross-role conflicts.
17. **“Chỉ theo dõi human users.”** CI/robot/service tokens có thể là đường truy cập lớn.
18. **“Không có incidents là đã hiệu quả.”** Có thể thiếu detection hoặc attacker traffic.
19. **“Tắt alert noise để metrics đẹp hơn.”** Làm giảm detection coverage/recall.
20. **“Mọi MFA như nhau.”** Phishing-resistant và fallback yếu có mức bảo đảm khác.
21. **“Một con số trung bình đại diện trải nghiệm.”** Tail latency ở một vùng/người dùng có thể tệ.
22. **“Khi PEP lỗi cứ fail-open ra VPN.”** Có thể phá security boundary.
23. **“Không cần đếm applications mới phát hiện.”** Inventory discovery làm denominator thay đổi.
24. **“Loại ngoại lệ khỏi mẫu số.”** Risk được che khỏi dashboard.
25. **“100% negative test pass nghĩa không có bypass khác.”** Kết luận chỉ đúng tập kịch bản đã thử.
26. **“Alert precision/recall có thể tính từ alerts mà không có ground truth.”** FN không tự lộ ra.
27. **“So sánh trước–sau là bằng chứng nhân quả.”** Cần xét EDR/IAM/network/scope thay đổi.
28. **“Dùng risk score tùy ý vẫn khách quan.”** Weights và assumptions phải được review.
29. **“Log đầy đủ phải gồm cả token và app payload.”** Làm tăng rủi ro bảo mật/riêng tư.
30. **“Dashboard không có dấu đỏ là trạng thái tốt.”** Có thể missing telemetry hoặc không ai test.
31. **“VPN luôn kém ZTNA.”** VPN có thể được segment mạnh; phải kiểm tra effective permissions.
32. **“Tiết kiệm VPN license là lợi ích ngay khi user rời VPN.”** Chỉ tính khi chi phí/hạ tầng thực được cắt.
33. **“Incidents giảm 30% chứng minh chính ZTNA giảm 30% rủi ro.”** Chưa đủ nếu confounders không được xử lý.
34. **“Policy rollout pass một lần đủ vĩnh viễn.”** Route/IdP/PEP/app thay đổi đòi revalidation.
35. **“Những assets không có owner có thể bỏ đo.”** Đây thường là một risk signal ưu tiên làm rõ.

## 32. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Hai tỷ lệ coverage

Tổ chức có 100 private apps. 92 app đã được khai ZTNA, nhưng chỉ 80 app có positive và negative tests, logging đầy đủ. Trong 8 app chưa verified còn một ứng dụng HR nhạy cảm.

**Câu hỏi:** báo cáo số nào đúng? Có thể tuyên bố 92% effective coverage không?

**Gợi ý:** báo **92% configured, 80% verified** theo tiêu chí đề bài; nêu **risk tier của HR** và các assets chưa có evidence. Không gọi 92% là effective.

### Bài 2 — Risk-weighted coverage

Ba applications có weights lần lượt **5, 3, 2**. Chỉ ứng dụng weight 3 và 2 đã fully verified.

**Gợi ý:** unweighted = **2/3 ≈ 66,7%**, weighted = **(3+2)/(5+3+2) = 50%**. Phải ưu tiên app weight 5.

### Bài 3 — Deny rate tăng

ZTNA deny rate tăng từ 2% lên 15% sau khi bật device posture policy. Helpdesk tăng nhiều tickets và EDR reporting delay cao hơn.

**Gợi ý:** tách **true deny, false deny, missing/stale posture**, đo ingestion p95, kiểm thử compliant positive và noncompliant negative. Không tự gắn 15% với tấn công.

### Bài 4 — Thu hồi access sau nghỉ việc

HR event lúc 09:00, IdP khóa lúc 09:01, PEP block new logins lúc 09:03, app session cũ hết hiệu lực lúc 09:45.

**Gợi ý:** block-new latency = **3 phút**; effective revoke latency = **45 phút** theo điều kiện đo. Cần hai SLO khác nhau, xem app cookie/session, API tokens và existing connection kill.

### Bài 5 — Bypass ngoài portal

User đã được deny Payroll trên ZTNA; tuy nhiên user thuộc subnet VPN cũ và thử kết nối trực tiếp private admin port được.

**Gợi ý:** đây là **unauthorized path**. Cần inventory/route/firewall evidence, test positive qua ZTNA và negative direct path, xử lý segmentation/VPN policies, không chỉ sửa ZTNA dashboard.

### Bài 6 — Precision/recall trong simulation

Một test set có **40 hành vi trái quyền được gắn nhãn**, hệ phát hiện **30** và bỏ sót **10**. Đồng thời có **5 alerts trên hoạt động hợp lệ**.

**Gợi ý:** TP = 30, FN = 10, FP = 5. **Recall = 30/40 = 75%**; **precision = 30/(30+5) ≈ 85,7%** trong **test set**, không được tuyên bố production recall cũng như vậy.

### Bài 7 — App latency và vùng mạng

Global p95 connect latency là 1,6 giây, nhưng remote users ở một vùng có p95 9 giây và nhiều retry. Dashboard toàn cục trông đạt SLO.

**Gợi ý:** phân tầng theo **region, identity, device, app, connection type**, đo IdP time, PEP connector, DNS, TLS và app response. SLO toàn cục không thay SLO của các nhóm người dùng trọng yếu.

### Bài 8 — Tính lợi ích

ZTNA đã giảm users còn dùng VPN từ 2.000 xuống 200, nhưng VPN concentrators, license và DR site vẫn phải duy trì.

**Gợi ý:** chưa ghi nhận toàn bộ VPN infrastructure savings là realized benefit. Phân tách **estimated future saving** với **actual cost retired**, tính chi phí ZTNA/EDR/monitoring.

### Bài 9 — Thiết kế dashboard có thể kiểm toán

Hãy xây dựng dashboard cho **Payroll, CRM, Admin Bastion và Source Repository**:

1. Ghi scope/source/path/criticality/owner và inventory confidence.
2. Tính configured vs verified coverage theo resource.
3. Ghi identity assurance, device signal freshness và privileged JIT.
4. Thêm direct/VPN/IPv6 negative tests.
5. Đo revoke t0→t3 gồm existing sessions.
6. Có p95 latency, legitimate success và incident/detection tests.
7. Gắn exceptions và missing telemetry thành cột riêng.
8. Chỉ đóng finding khi có **positive + negative evidence**.

**Gợi ý:** bắt đầu từ **threat/control/objective matrix**, định nghĩa metric contract và data quality trước khi chọn cách vẽ biểu đồ.

### Bài 10 — So sánh rollout

Nhóm A triển khai ZTNA vào tháng 1, nhóm B vào tháng 3. Trong tháng 2, tổ chức cũng bật phishing-resistant MFA cho toàn bộ người dùng. Có thể dùng số incidents tháng 1–3 để kết luận tác động của ZTNA không?

**Gợi ý:** khó quy kết riêng vì **MFA rollout là confounder**, attack volume/telemetry cũng có thể đổi. Có thể so nhóm, trước/sau theo role/risk, kiểm tra parallel trends nếu dùng difference-in-differences và báo uncertainty; kết hợp technical tests chứng minh đúng control.

## 33. Checklist chấp thuận chương trình đo lường

| Câu hỏi | Evidence phải có |
| --- | --- |
| Mỗi KPI có control objective và risk owner? | Metric contract + risk register |
| Denominator lấy từ inventory độc lập với ZTNA vendor? | CMDB/cloud/DNS/VPN/IdP reconciliation |
| Configured và verified coverage được tách? | Config exports + current positive/negative tests |
| High-risk assets được xem riêng? | Risk-weighted coverage + critical gaps |
| Các đường VPN/public/IPv6/management/partner đã được xét? | Access-path inventory + bypass tests |
| IdP/MFA đo theo auth assurance thực? | Auth methods, policy conditions, test results |
| Device posture có freshness/unknown handling? | MDM/EDR timestamps, TTL policy |
| Standing privileges và JIT được kiểm chứng? | IAM/PAM entitlement review |
| Session revoke đo tới app operation thực? | HR→IdP→PDP→PEP→App timeline |
| Positive và negative tests đều có evidence? | Pass/fail + deny point + app health |
| Telemetry có đủ IDs/clock sync/policy version? | Data-quality dashboard, schemas, sampling |
| Logs không chứa tokens/PII quá mức? | Redaction/retention/RBAC review |
| Incident outcomes có detection coverage/confounders? | Simulation results, logs, incident data |
| Authorized access UX và SLO được đo? | p95/p99, success, helpdesk/root cause |
| Cost/ROI phân biệt realized vs estimated? | Actual invoices/costs + assumptions |
| Baseline/population thay đổi đã được ghi? | Time-series metric definitions và cohort notes |
| Exceptions có owner, TTL và review? | Exception register và approvals |
| Dashboard có missing/unknown, không chỉ pass? | Completeness/freshness and critical gating |
| Quyền sửa metric/dashboard được kiểm toán? | Data governance, change logs |
| Mỗi finding có action, owner và revalidation? | Remediation tickets + test evidence |

## 34. Tổng kết

**Đo lường hiệu quả Zero Trust** không phải là đếm số tài khoản bật MFA, số ứng dụng xuất hiện trong dashboard hay số lần ZTNA từ chối. Cần tách **mức bao phủ, hiệu lực điểm thực thi, mức giảm rủi ro, khả năng phát hiện và kết quả vận hành**. Đặc biệt, **configured coverage không tương đương verified enforcement**; một ứng dụng vẫn có thể bị truy cập qua public IP, VPN legacy, IPv6 hoặc session cũ dù người dùng đã được điều hướng tới ZTNA.

Một hệ đo có khả năng kiểm toán phải định nghĩa rõ **population/denominator, numerator, risk tiers, time window, owner, telemetry quality và test conditions**. Các thước đo cần đi cùng nhau: **positive và negative pass rates**, **identity assurance và posture freshness**, **effective revocation t0→t3**, **critical bypass findings**, **detection test coverage**, **authorized access success và p95/p99 latency**. Khi một số liệu giảm/tăng, phải kiểm tra **scope drift, sensor coverage, confounders và false denies** trước khi kết luận tác động.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, Zero Trust có hiệu quả khi kiến trúc không mặc định tin mạng nội bộ, **quyền truy cập thực được thu hẹp theo danh tính/thiết bị/tài nguyên**, đường đi vòng bị chặn ở các điểm thực thi có hiệu lực, hành vi trái quyền bị phát hiện và phiên được thu hồi đúng SLO. Hiệu quả đó cần được chứng minh liên tục bằng **inventory độc lập, effective access tests, logs tại identity–device–PDP–PEP–network–application, dashboard có kiểm soát chất lượng dữ liệu và quy trình remediation có owner** — không chỉ bằng tỷ lệ đẹp trên một màn hình.
