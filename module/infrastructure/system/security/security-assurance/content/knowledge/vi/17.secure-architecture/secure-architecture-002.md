# Defense in depth – Kiến trúc phòng thủ nhiều lớp và cách kiểm chứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **defense in depth (phòng thủ nhiều lớp)** và phân biệt với việc chỉ thêm nhiều sản phẩm bảo mật hoặc nhân bản cùng một control.
- Xây dựng kiến trúc bảo vệ dựa trên **tài sản, mục tiêu bảo mật, threat scenarios, trust boundaries và các đường tấn công**.
- Phân bổ controls theo lớp: governance, supply chain, identity, network, application, data, runtime, detection/response và recovery.
- Đánh giá **độc lập, độ bao phủ, điểm lỗi chung (common-cause failure), đường bypass và blast radius** giữa các lớp.
- Thiết kế mô hình cho hệ thống Java/Spring Boot đa tenant với API gateway, service identity, database, queue, object storage và cloud IAM.
- Chuyển kiến trúc thành **security requirements, control mapping, positive/negative tests, runtime evidence và audit findings**.
- Đánh giá hiệu lực tổng thể bằng chuỗi **risk → objective → architecture → control → test → evidence → remediation/retest**, duy trì assurance khi hệ thống thay đổi.

## 1. Defense in depth là gì?

**Defense in depth** là cách thiết kế bảo mật bằng cách bố trí **nhiều lớp kiểm soát có vai trò bổ sung nhau** để giảm khả năng một lỗi đơn lẻ dẫn tới sự cố nghiêm trọng. Nếu một lớp bị vượt qua, lớp tiếp theo vẫn có thể ngăn hành động trái phép, giới hạn phạm vi thiệt hại, phát hiện hành vi hoặc hỗ trợ khôi phục.

Ví dụ, một API tài chính không chỉ dựa vào firewall. Kiến trúc có thể kết hợp:

- Chỉ cho phép deployment từ pipeline được kiểm soát.
- Xác thực danh tính user và workload.
- Giới hạn kết nối mạng tới API và database.
- Kiểm tra quyền theo **actor, action, resource và tenant** trong ứng dụng.
- Cấp quyền database/object storage tối thiểu.
- Mã hóa dữ liệu khi truyền và khi lưu theo yêu cầu.
- Ghi nhận hành động nhạy cảm và phát hiện truy cập bất thường.
- Có quy trình cô lập, thu hồi credential, phục hồi và điều tra.

Nếu attacker vượt qua lớp network, authorization trong ứng dụng và quyền IAM vẫn phải giới hạn dữ liệu có thể truy cập. Nếu một credential bị đánh cắp, phát hiện và thu hồi cần giúp giảm thời gian phơi lộ. Nếu production bị phá hoại, backup/restore và kế hoạch khôi phục giúp giảm hậu quả.

Trong module **SECURITY_SECURITY_ASSURANCE**, defense in depth là **một quyết định kiến trúc cần được chứng minh bằng bằng chứng**. Không đủ để vẽ sơ đồ có nhiều hộp security; cần nêu lớp nào xử lý kịch bản nào, mỗi lớp phụ thuộc vào đâu, cách kiểm tra khi một lớp thất bại và giới hạn nào còn tồn tại.

### Một định nghĩa vận hành

Một thiết kế defense in depth tốt trả lời được:

1. **Điều gì cần bảo vệ?** Tài sản, dữ liệu, identity, dịch vụ và hoạt động nghiệp vụ.
2. **Ai hoặc điều gì có thể gây hại?** Actor bên ngoài, insider, workload bị chiếm, lỗi cấu hình, nhà cung cấp, pipeline hoặc sự cố vận hành.
3. **Các lớp kiểm soát đặt ở đâu?** Theo trust boundary và đường đi của hành động.
4. **Nếu lớp đầu tiên thất bại thì điều gì tiếp tục bảo vệ?** Lớp độc lập nào có thể ngăn hoặc giới hạn tác động?
5. **Làm sao biết lớp đó vẫn hoạt động?** Test, telemetry, review, evidence và kiểm tra drift.
6. **Khi nhiều lớp cùng thất bại thì sao?** Detection, response, containment, recovery và residual-risk decision.

**Defense in depth không có nghĩa “càng nhiều công cụ càng an toàn”.** Một firewall, WAF và network ACL có thể cùng dựa trên một tập rule sai hoặc cùng bị sửa bởi một tài khoản quản trị. Nhiều control trùng lặp nhưng có cùng điểm lỗi không tạo ra nhiều lớp bảo vệ độc lập.

## 2. Từ threat scenario tới kiến trúc nhiều lớp

Không bắt đầu bằng danh sách sản phẩm. Bắt đầu bằng **risk scenario** cụ thể.

Ví dụ: user tenant A truy cập báo cáo tài chính tenant B.

- **Asset:** báo cáo, dữ liệu giao dịch và danh tính khách hàng.
- **Actor:** user tenant A hoặc attacker chiếm phiên của user.
- **Entry point:** public API, export endpoint, queue job hoặc URL tải file.
- **Weakness:** API chỉ kiểm tra user đã đăng nhập; không kiểm tra quyền trên report cụ thể.
- **Attack path:** đổi report ID → API trả dữ liệu tenant B → worker tạo file → object storage cung cấp URL tải.
- **Impact:** lộ dữ liệu, vi phạm nghĩa vụ bảo vệ và mất niềm tin khách hàng.
- **Control objectives:** ngăn truy cập sai tenant, giới hạn quyền worker, giới hạn file download, phát hiện hành vi bất thường và điều tra được.

Từ đó mới chọn lớp kiểm soát:

| Lớp | Câu hỏi đối với scenario | Ví dụ control |
| --- | --- | --- |
| Identity | Caller là ai, token/phiên có đáng tin? | OIDC, MFA theo risk, workload identity |
| Network | Đường gọi nào được phép tồn tại? | Ingress policy, private service path, egress controls |
| Application | Actor có quyền trên report cụ thể không? | Object-level authorization, tenant ownership |
| Data/storage | Worker chỉ đọc/ghi tài nguyên nào? | Scoped IAM, bucket policy, object isolation |
| Runtime | Hành vi export bất thường có bị phát hiện? | Rate/volume detection, audit event |
| Response/recovery | Nếu đã lộ dữ liệu, giới hạn và xử lý thế nào? | Token revoke, containment, incident response, recovery |

### Threat model nên thể hiện đường tấn công, không chỉ thành phần

~~~mermaid
flowchart TD
    A["Attacker chiếm phiên user tenant A"] --> B["Public API / Gateway"]
    B --> C["API chỉ kiểm tra authenticated"]
    C --> D["Thiếu object-level / tenant authorization"]
    D --> E["Export job được tạo"]
    E --> F["Worker có quyền storage quá rộng"]
    F --> G["File tenant B được tạo"]
    G --> H["URL tải / object storage"]
    H --> I["Dữ liệu bị tiết lộ"]
    C -. "Detection?" .-> J["Security monitoring"]
    F -. "Scoped IAM?" .-> K["Data boundary"]
~~~

Sơ đồ cho thấy hai lớp có thể chặn đường tấn công **trước khi xảy ra hậu quả**: authorization ở API và IAM/resource policy ở worker/storage. Monitoring có thể phát hiện, nhưng nếu chỉ alert sau khi file đã tải thì đó là lớp **detective**, không thay preventive control.

## 3. Các lớp phòng thủ thường gặp

Không có một sơ đồ lớp cố định cho mọi kiến trúc. Các lớp sau là khung tham khảo để tổ chức controls theo mục tiêu và trust boundary.

### 3.1. Governance, risk và security requirements

Lớp quản trị đặt ra **mục tiêu, trách nhiệm và điều kiện chấp nhận**:
- Security policy, architecture principles và control standards.
- Asset/data inventory, classification và risk assessment.
- Threat modeling và security review trước thay đổi trọng yếu.
- Risk owner, control owner, approver và người đánh giá độc lập khi cần.
- Exception có scope, rationale, expiry, compensating controls và residual risk.
- Assurance plan: control nào cần test, evidence ở đâu, tần suất/trigger và điều kiện PASS/FAIL.

Nếu policy chỉ nằm trong tài liệu nhưng không được chuyển thành yêu cầu, CI gate, cấu hình runtime hoặc hoạt động review, lớp quản trị **chưa chứng minh hiệu lực vận hành**.

### 3.2. Supply chain và build/deployment

Bảo vệ nguồn gốc phần mềm trước khi workload đi vào production:
- Source control, branch protection và code review.
- Dependency/SCA, SAST, secret scanning và kiểm tra artifact.
- Build provenance, artifact digest và quy trình ký/xác minh nếu được áp dụng.
- Tách quyền build, approve và deploy; hạn chế runner có quyền production.
- IaC/config review, policy-as-code và admission controls.
- Kiểm tra image/runtime config và phát hiện drift.

Một ứng dụng có authorization tốt nhưng được deploy từ artifact bị thay đổi hoặc pipeline bị chiếm vẫn có thể bị vô hiệu hóa. Ngược lại, image đã ký không chứng minh ứng dụng phân quyền đúng.

### 3.3. Identity và access control

Kiểm soát ai được bắt đầu hành động:
- User authentication, session lifecycle và MFA theo risk/policy.
- Service/workload identity, mTLS/OIDC, issuer/audience validation.
- Least privilege, role/attribute/resource policies và separation of duties.
- JIT/break-glass access có hạn và audit.
- Joiner–mover–leaver, access review, credential rotation/revocation.
- Không tin identity/role/tenant header tự khai từ client.

Identity mạnh là nền tảng, nhưng **authenticated ≠ authorized**. Một user đăng nhập hợp lệ vẫn không được đọc report của tenant khác.

### 3.4. Network và communication

Giới hạn đường đi của traffic và peer:
- Ingress/egress policy, firewall/security group, segmentation.
- TLS/mTLS và xác minh peer certificate/hostname.
- Private endpoints, service mesh policy và bảo vệ management plane.
- DNS, proxy, route, direct IP và bypass path inventory.
- Rate limiting/network abuse controls theo threat model.
- Quản trị egress tới vendor và metadata services.

Network segmentation giảm số đường có thể tiếp cận, nhưng không thay authorization trong ứng dụng hoặc IAM ở tài nguyên. Nếu một workload hợp lệ bị chiếm, nó vẫn có thể lạm dụng mọi quyền mạng và dữ liệu mà nó được cấp.

### 3.5. Application và API

Kiểm soát hành động nghiệp vụ:
- Input validation, schema constraints và safe parsing.
- Authentication và authorization theo resource/action/tenant.
- Server-side business rules, workflow approval và SoD.
- CSRF/CORS/session protections theo loại client.
- Rate limit, anti-automation, idempotency và replay controls khi phù hợp.
- Secure error handling, output encoding và tránh lộ thông tin.
- Secure defaults, deny-by-default và test negative paths.

WAF có thể chặn một số request độc hại, nhưng không hiểu đầy đủ **ai sở hữu report cụ thể**. Object-level authorization phải nằm ở nơi có đủ business context.

### 3.6. Data và cryptography

Bảo vệ dữ liệu ở mọi trạng thái:
- Data minimization và purpose limitation.
- Encryption in transit/at rest và key lifecycle.
- Field-level protection, tokenization/pseudonymization khi phù hợp.
- Database authorization, row/tenant scoping và storage policy.
- Retention, deletion, backup/restore và copy inventory.
- Data export/download controls, signed URL TTL và audit.

Encryption không sửa được quyền đọc quá rộng; access control không loại bỏ dữ liệu thừa trong log; backup có mã hóa vẫn cần quyền và vòng đời riêng.

### 3.7. Runtime, detection và observability

Phát hiện khi preventive controls không đủ:
- Audit events cho thao tác nhạy cảm.
- Runtime telemetry, EDR/container/cloud activity monitoring.
- Detection rules cho hành vi bất thường, privilege escalation và data exfiltration.
- Alert routing, on-call, health monitoring và synthetic tests.
- Integrity/coverage của log pipeline; cảnh báo khi nguồn ngừng gửi.
- Incident response, evidence preservation và containment.

**Không có alert không có nghĩa không có sự cố.** Có thể detector không nhận event, rule bị tắt hoặc log source đã mất. Phải kiểm thử cả đường phát hiện từ nguồn tới người nhận.

### 3.8. Resilience, recovery và continuity

Giảm hậu quả và phục hồi khi prevention/detection thất bại:
- Backup tách quyền, bất biến hoặc có biện pháp chống sửa/xóa theo risk.
- Restore testing, RTO/RPO và DR exercises.
- Redundancy, failover và capacity management.
- Incident playbooks, credential/key rotation và isolation.
- Data integrity checks và reconciliation sau restore.
- Lessons learned, remediation và retest.

Backup job xanh không chứng minh có thể phục hồi đúng; cần test restore và xác minh ứng dụng/dữ liệu sau phục hồi.

## 4. Một lớp tốt cần có thuộc tính gì?

Một control chỉ tạo thêm giá trị nếu nó **xử lý một phần rủi ro xác định**, có thể vận hành và có cách chứng minh.

| Thuộc tính | Câu hỏi đánh giá | Ví dụ |
| --- | --- | --- |
| **Coverage** | Control bao phủ asset, endpoint, actor, region và mode nào? | Mọi export route và worker được inventory |
| **Effectiveness** | Control có ngăn/phát hiện hành động trong scenario không? | Tenant B bị từ chối ở API và storage |
| **Independence** | Có dùng cùng identity, policy, admin hoặc nguồn dữ liệu với lớp khác không? | Database deny policy độc lập với role ở UI |
| **Failure behavior** | Khi control không hoạt động thì hệ thống fail-open hay fail-closed? | Không xác minh được token thì từ chối API nhạy cảm |
| **Bypass resistance** | Có direct route, alternate port, legacy API hoặc service account khác không? | Không truy cập backend qua IP trực tiếp |
| **Observability** | Có biết control bị tắt, lỗi hoặc thiếu coverage? | Alert khi policy agent không đồng bộ |
| **Recoverability** | Có thể khôi phục control sau compromise/outage? | Rotate credential, restore policy và retest |
| **Evidence quality** | Evidence có gắn đúng version, environment, scope, time? | Runtime snapshot + negative test + deployment ID |
| **Ownership** | Ai duy trì, ai review, ai chấp nhận residual risk? | Control owner và risk owner rõ |

### Độc lập không có nghĩa không được dùng chung nền tảng

Một hệ thống có thể dùng chung IdP, logging platform hoặc cloud control plane; điều đó không tự làm kiến trúc sai. Nhưng cần nhận diện **common-cause failure**: nếu cùng một admin account có thể sửa IdP, tắt monitoring và thay IAM policy, ba lớp có thể sụp đổ cùng lúc.

Các câu hỏi quan trọng:
- Lớp thứ hai có xác minh từ nguồn độc lập không?
- Quyền thay control có được tách khỏi quyền sử dụng control?
- Có thể phát hiện nếu control plane bị thay đổi?
- Có phương án khi IdP, CA, KMS hoặc SIEM không khả dụng/bị chiếm?
- Backup/evidence có nằm trong cùng miền quản trị có thể bị attacker xóa không?

## 5. Defense in depth và các khái niệm gần nhau

| Khái niệm | Trọng tâm | Quan hệ |
| --- | --- | --- |
| **Defense in depth** | Nhiều lớp kiểm soát bổ sung qua attack path | Cách tổ chức kiến trúc tổng thể |
| **Least privilege** | Giảm quyền của từng principal xuống mức cần | Giới hạn hậu quả khi một identity bị chiếm |
| **Zero Trust** | Không mặc định tin cậy chỉ vì vị trí mạng; xác minh theo context/policy | Có thể là nguyên tắc thiết kế các lớp identity/network/app |
| **Network segmentation** | Chia vùng và giới hạn kết nối | Một lớp trong defense in depth |
| **Fail-safe defaults** | Mặc định từ chối khi không đủ điều kiện | Thuộc tính của từng control |
| **Separation of duties** | Phân tách quyền có thể xung đột | Giảm nguy cơ lạm dụng hoặc sai sót tập trung |
| **Resilience** | Duy trì/khôi phục dịch vụ trước và sau sự cố | Bổ sung lớp recovery/continuity |
| **Security monitoring** | Quan sát và phát hiện hành vi | Lớp detective, không thay prevention |
| **Redundancy** | Có nhiều instance/đường dự phòng | Tăng availability, không tự tạo security independence |

**Nhiều lớp không đồng nghĩa Zero Trust**, và Zero Trust không phải một sản phẩm. Có thể áp dụng cả hai tư duy: xác minh identity/context ở mỗi boundary và bố trí controls bổ sung để giảm hậu quả khi một quyết định xác thực hoặc phân quyền sai.

## 6. Thiết kế kiến trúc nhiều lớp cho Java/Spring Boot đa tenant

### 6.1. Kiến trúc minh họa

Một nền tảng báo cáo tài chính có browser client, API gateway, Spring Boot services, queue, worker, PostgreSQL, object storage và SIEM.

~~~mermaid
flowchart TB
    subgraph Edge["Lớp edge / public"]
      CLIENT["Browser / Mobile"]
      WAF["WAF / Rate limit"]
      GW["API Gateway / OIDC"]
      CLIENT --> WAF --> GW
    end
    subgraph App["Lớp ứng dụng"]
      API["Spring Boot report-api"]
      POLICY["Authorization / Tenant policy"]
      JOB["Job service"]
      GW --> API
      API --> POLICY
      POLICY --> JOB
    end
    subgraph Async["Lớp bất đồng bộ"]
      Q["Message Broker"]
      WORKER["export-worker"]
      JOB --> Q --> WORKER
    end
    subgraph Data["Lớp dữ liệu"]
      DB[("PostgreSQL")]
      STORE[("Object Storage")]
      WORKER --> DB
      WORKER --> STORE
      API --> DB
    end
    subgraph Platform["Lớp nền tảng và vận hành"]
      IAM["IAM / Workload identity"]
      KMS["KMS / Key management"]
      OBS["Logs / Detection / SIEM"]
      BACKUP[("Backup / DR")]
    end
    IAM -. "Principal / policy" .-> API
    IAM -. "Principal / policy" .-> WORKER
    KMS -. "Key policy" .-> DB
    KMS -. "Key policy" .-> STORE
    DB --> BACKUP
    STORE --> BACKUP
    API --> OBS
    WORKER --> OBS
    GW --> OBS
~~~

Sơ đồ là kiến trúc logic. Khi triển khai, cần vẽ riêng **trust boundaries**, điểm TLS termination, luồng secret/token, quyền quản trị và data flows; các đường chấm không phải bằng chứng đã cấu hình đúng.

### 6.2. Bảy lớp xử lý scenario cross-tenant

| Lớp | Control | Nếu lớp trước thất bại thì sao? |
| --- | --- | --- |
| Edge | WAF/rate limiting, chặn route không cần thiết | Request độc hại có thể tới API nhưng còn authentication/authorization |
| Identity | OIDC token validation, session protection, workload identity | User bị chiếm vẫn bị giới hạn bởi object policy và data scope |
| Network | Gateway-only ingress, private service path, egress restrictions | Direct path khó tiếp cận; nếu vào được app vẫn phải kiểm tra quyền |
| Application | Resource/tenant authorization, job ownership, DTO allowlist | Nếu role mapping lỗi, data/IAM scope vẫn hạn chế blast radius |
| Data | DB row/tenant scope, scoped IAM, bucket policy | Worker compromise không được đọc mọi bucket |
| Detection | Audit export, volume anomaly, source health | Hành động lọt qua preventive control có thể được phát hiện |
| Response/recovery | Revoke token, disable job, isolate worker, investigate, restore | Giảm thời gian/thiệt hại và hỗ trợ xử lý sau sự cố |

Lưu ý: lớp WAF không phải bảo đảm nếu attacker dùng API hợp lệ. Lớp data policy không thể thay thế authorization nghiệp vụ; nó là một giới hạn bổ sung ở boundary dữ liệu. Monitoring không ngăn được dữ liệu đã bị tải trước khi alert, nên phải đo thời gian phát hiện và phản ứng.

### 6.3. Threat model theo asset và principal

| Principal | Tài nguyên | Hành động được phép | Hành động phải từ chối |
| --- | --- | --- | --- |
| Customer tenant A | Report thuộc tenant A | Read/export theo role | Read/export report tenant B |
| Support agent | Case được phân công | Xem field cần cho case | Export toàn bộ customer database |
| report-api workload | Job API, database trong scope | Tạo job đã authorize, đọc metadata cần thiết | Tự tạo job cho tenant không được phép |
| export-worker | Queue job, bucket prefix đã cấp | Tạo file của job được xác minh | Đọc bucket/tenant ngoài scope |
| CI runner | Registry/build/test | Build artifact và publish theo policy | Sửa production IAM/trust không qua approval |
| Break-glass operator | Tài nguyên khẩn cấp trong phạm vi | Hành động theo incident approval | Dùng quyền thường trực không audit |

Bảng này phải được chuyển thành **IAM/application policies và test**, không chỉ nằm trong tài liệu kiến trúc.

## 7. Mỗi lớp cần có security requirements đo được

Một câu “có nhiều lớp bảo mật” không thể audit. Hãy định nghĩa các yêu cầu gắn với hành động, scope và expected result.

| Requirement ID | Yêu cầu minh họa | Lớp | Bằng chứng/kiểm tra |
| --- | --- | --- | --- |
| **DID-REQ-01** | Tất cả public routes nhạy cảm yêu cầu identity được xác minh theo policy | Edge/Identity | Route inventory, invalid-token tests |
| **DID-REQ-02** | Mọi thao tác dữ liệu kiểm tra resource ownership và tenant ở server | Application | Cross-tenant negative tests |
| **DID-REQ-03** | Backend không thể truy cập trực tiếp qua route ngoài boundary được duyệt | Network | Direct-IP/alternate-port tests |
| **DID-REQ-04** | Service/workload chỉ có quyền IAM cho action/resource cần thiết | Identity/Data | Effective permission snapshot, deny tests |
| **DID-REQ-05** | CI/build identity không thể tự cấp quyền production ngoài quy trình | Supply chain | CI IAM tests, approval/audit records |
| **DID-REQ-06** | Sensitive traffic được bảo vệ trên các hop thuộc scope | Network/Data | TLS/mTLS handshake và wrong-cert tests |
| **DID-REQ-07** | Data export chỉ tạo population/cột đã được authorize | Application/Data | Export contract + object scope tests |
| **DID-REQ-08** | Security events được ghi và phát hiện; mất nguồn phải được cảnh báo | Detection | Synthetic event và collector health tests |
| **DID-REQ-09** | Backup/restore được kiểm chứng và tách quyền khỏi production khi cần | Recovery | Restore exercise, access review |
| **DID-REQ-10** | Exception có owner, rationale, expiry, control bù trừ và review | Governance | Exception register, expiry alert |
| **DID-REQ-11** | Thay đổi trust boundary, identity, data flow hoặc control kích hoạt review | Governance/CI | PR, threat-model update, retest |
| **DID-REQ-12** | Evidence gắn đúng build, config, runtime, scope và thời điểm | Assurance | Evidence register, deployment and reviewer refs |

Các ID trên là **mẫu cho bài học**, không phải control ID của một chuẩn bên ngoài. Tổ chức cần map vào framework/standard và phiên bản thực tế được áp dụng.

## 8. Bản đồ coverage: lớp nào bảo vệ tài sản nào?

Defense in depth không chỉ là liệt kê lớp. Cần biết một asset hoặc attack path đang được bảo vệ bởi những control nào và còn khoảng trống gì.

| Asset / mục tiêu | Preventive controls | Detective controls | Recovery / corrective controls |
| --- | --- | --- | --- |
| User identity/session | OIDC/MFA/session policy | Login anomaly, session misuse alerts | Revoke sessions, reset credential, investigate |
| Report/customer data | Object authZ, DB scope, encryption, export policy | Unusual reads/downloads, audit trail | Restrict access, incident response, data recovery |
| Workload identity | Short-lived credential, issuer trust, IAM least privilege | Token/role change monitoring | Rotate/revoke identity, redeploy workload |
| CI/CD pipeline | Branch protection, build/deploy separation, artifact checks | Change/audit events, anomalous deploy | Disable runner/token, rollback, rebuild trusted artifact |
| Network/service path | Segmentation, TLS/mTLS, gateway policy | Flow monitoring, config drift | Isolate segment, restore trusted route/config |
| Keys/secrets | KMS/secret manager, access separation | Key use anomaly, expiry alerts | Rotate/revoke, re-encrypt where needed |
| Logs/evidence | Append/access controls, source integrity | Pipeline health, deletion/tamper alerts | Restore evidence copy, incident investigation |
| Backup/DR | Separate credentials, immutable/isolated copies where appropriate | Backup/restore monitoring | Restore test, reconcile, rotate secrets |

Một asset có thể có nhiều controls nhưng vẫn có **single point of failure**. Ví dụ data, logs và backup đều nằm trong cùng cloud account và cùng một admin role; attacker có quyền admin đó có thể đọc data, xóa logs và xóa backup. Cần xem miền quản trị và cách tách quyền, không chỉ đếm số lớp.

## 9. Kiểm tra tính độc lập và common-cause failure

### 9.1. Ví dụ ba lớp nhưng một điểm lỗi

Một tổ chức triển khai:
- WAF rule chặn request nguy hiểm.
- API gateway policy chặn cùng loại request.
- Application filter chặn cùng loại request.

Nhưng cả ba policy đều được cập nhật bởi **một pipeline dùng chung credential admin**, và pipeline đó không có review độc lập. Nếu pipeline bị chiếm hoặc credential bị lộ, attacker có thể sửa cả ba lớp. Có ba control nhưng chỉ một miền lỗi.

### 9.2. Ma trận phụ thuộc

| Thành phần dùng chung | Lớp bị ảnh hưởng | Câu hỏi cần kiểm chứng |
| --- | --- | --- |
| IdP/issuer | User auth, workload auth, admin access | Nếu issuer bị chiếm hoặc ngừng hoạt động, lớp nào còn bảo vệ? |
| Cloud admin role | Network, IAM, KMS, storage, logging | Có tách quyền thay đổi và quyền sử dụng không? |
| CI/CD signing/deploy key | Artifact, deployment, policy rollout | Ai có thể build, ký và deploy? |
| DNS/PKI/CA | TLS, service identity, egress | Root/issuer compromise có ảnh hưởng bao nhiêu workload? |
| Log pipeline | Detection, audit, incident evidence | Mất nguồn có được phát hiện độc lập? |
| Backup account | Recovery, evidence preservation | Production admin có thể xóa cả bản backup không? |
| Shared secrets | Nhiều service và môi trường | Một credential lộ có thể mở những boundary nào? |
| Configuration repository | WAF, ingress, mesh, application policy | Có approval, signed history và runtime drift detection? |

### 9.3. Cách đánh giá độ độc lập

1. Vẽ quyền **create/change/disable** từng control, không chỉ quyền sử dụng.
2. Xác định shared identity, key, issuer, admin plane, network và configuration source.
3. Giả định một thành phần bị compromise; xem những lớp nào bị vô hiệu hóa cùng lúc.
4. Kiểm tra detection có **nguồn độc lập hoặc integrity protection** đủ để phát hiện việc tắt control.
5. Xác minh backup/evidence không cùng quyền xóa với hệ thống đang bảo vệ.
6. Ghi các common-cause risks vào threat model và có biện pháp/acceptance rõ.

Không cần tạo một hạ tầng độc lập hoàn toàn cho mọi control. Mức tách biệt phải theo **mức độ nghiêm trọng, khả năng tấn công, cost và yêu cầu continuity**. Nhưng nếu tuyên bố một lớp là fallback khi lớp kia lỗi, phải chứng minh fallback không phụ thuộc chính điểm lỗi đó.

## 10. Fail-open, fail-closed và degradation an toàn

Khi một lớp bảo mật không khả dụng, hệ thống phải có hành vi được thiết kế trước.

| Control/điều kiện lỗi | Fail-open nguy hiểm | Hướng xử lý an toàn theo risk |
| --- | --- | --- |
| Token/issuer validation không sẵn sàng | Chấp nhận request không xác minh | Từ chối thao tác nhạy cảm hoặc dùng cơ chế fallback đã được thẩm định |
| Authorization service timeout | Cho phép để giữ availability | Deny cho action nhạy cảm; có fallback được giới hạn nếu thiết kế cho phép |
| WAF/edge policy lỗi | Mở trực tiếp backend không kiểm soát | Failover sang cấu hình tương đương, không bỏ trust boundary |
| KMS/secret manager lỗi | Dùng key tĩnh hardcode | Dừng/queue thao tác an toàn, phục hồi dịch vụ secret |
| Audit/log pipeline lỗi | Bỏ qua mọi audit event | Buffer bền vững, cảnh báo source loss, áp dụng policy cho hành động quan trọng |
| Rate limiter lỗi | Cho phép không giới hạn | Giới hạn bảo thủ hoặc degradation phù hợp nghiệp vụ |
| Policy/config sync lỗi | Tiếp tục dùng policy cũ không biết trạng thái | Theo dõi age/version, từ chối thay đổi nhạy cảm hoặc hành động theo risk plan |

**Fail-closed không phải lúc nào cũng là câu trả lời duy nhất.** Một hệ thống y tế hoặc điều khiển an toàn có thể cần chế độ degraded operation được thiết kế kỹ. Điều quan trọng là nêu rõ **hành động nào bị chặn, hành động nào được phép, ai phê duyệt và rủi ro gì còn lại**; không để một timeout vô tình biến thành bypass.

### Graceful degradation cần có giới hạn

Ví dụ khi SIEM tạm thời không nhận log:
- Ứng dụng có thể buffer event vào store bền vững trong giới hạn dung lượng.
- Có alert từ health monitor độc lập khi collector không nhận dữ liệu.
- Thao tác cực kỳ nhạy cảm có thể bị giới hạn hoặc tạm dừng nếu policy yêu cầu.
- Khi khôi phục, đối soát sequence/time window và xác định gap.
- Ghi finding nếu mất evidence vượt ngưỡng; không coi “dịch vụ vẫn chạy” là security control đạt.

## 11. Phân biệt preventive, detective và corrective controls

Ba nhóm này có vai trò khác nhau trong defense in depth:

| Nhóm | Mục tiêu | Ví dụ | Chỉ số cần xem |
| --- | --- | --- | --- |
| **Preventive** | Ngăn hành động sai trước khi gây hậu quả | MFA, authorization, IAM deny, TLS policy, schema validation | Bypass attempts, denied requests, coverage |
| **Detective** | Phát hiện hành động hoặc sai lệch đã xảy ra/đang xảy ra | SIEM alerts, EDR, IAM drift, anomaly detection | Detection latency, source coverage, false negatives |
| **Corrective/recovery** | Giảm thiệt hại và khôi phục trạng thái đáng tin | Revoke, isolate, patch, restore, rotate key | Time to contain/recover, retest success, residual risk |

Một chương trình cần phối hợp cả ba. Tuy nhiên, không nên dùng detective control để hợp thức hóa một preventive control bắt buộc đang thiếu. Ví dụ alert khi có cross-tenant read không thay authorization phải ngăn cross-tenant read.

### Đánh giá độ trễ

- **Time to prevent:** hành động bị chặn tại điểm nào?
- **Time to detect:** từ sự kiện tới alert có thể sử dụng?
- **Time to respond/contain:** từ alert tới khi quyền/đường bị vô hiệu?
- **Time to recover:** tới khi hệ thống hoạt động với trạng thái được kiểm chứng?
- **Evidence gap:** khoảng thời gian nào không thể xác nhận do log/monitoring mất nguồn?

Các mốc cần được xác định theo risk scenario và SLA nội bộ; không dùng một con số mặc định cho mọi sự cố.

## 12. Defense in depth trong kiến trúc Java/Spring Boot

### 12.1. Authentication và authorization ở nhiều lớp

Gateway có thể xác minh JWT cơ bản, nhưng ứng dụng vẫn cần kiểm tra **issuer, audience, scope và quyền đối tượng** theo mô hình. Service-to-service có thể dùng mTLS hoặc workload token; database/storage phải có IAM policy độc lập.

Ví dụ policy ứng dụng giả định:

~~~java
import java.util.Objects;
import java.util.Set;

public final class ReportAccessPolicy {
    public record Actor(
            String principalId,
            String tenantId,
            Set<String> authorities) {}

    public record Report(
            String reportId,
            String tenantId,
            String ownerId,
            String classification) {}

    public boolean mayRead(Actor actor, Report report) {
        Objects.requireNonNull(actor, "actor");
        Objects.requireNonNull(report, "report");

        if (actor.principalId() == null || actor.tenantId() == null) {
            return false;
        }
        if (!actor.tenantId().equals(report.tenantId())) {
            return false;
        }
        return actor.authorities().contains("REPORT_READ")
                && ("INTERNAL".equals(report.classification())
                    || "CONFIDENTIAL".equals(report.classification()));
    }
}
~~~

Đây chỉ là ví dụ **policy minh họa**, không phải rule hoàn chỉnh cho mọi data class. Thực tế cần xác định owner, support access, delegated authority, deny rules và policy cho từng classification. Giá trị actor phải đến từ authenticated context; không lấy từ header hoặc request body tự khai.

### 12.2. Unit tests cho lớp application

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import org.junit.jupiter.api.Test;

class ReportAccessPolicyTest {
    private final ReportAccessPolicy policy = new ReportAccessPolicy();

    @Test
    void sameTenantWithReadAuthorityCanReadAllowedClass() {
        var actor = new ReportAccessPolicy.Actor(
                "user-A", "tenant-A", Set.of("REPORT_READ"));
        var report = new ReportAccessPolicy.Report(
                "r-01", "tenant-A", "user-A", "CONFIDENTIAL");

        assertTrue(policy.mayRead(actor, report));
    }

    @Test
    void crossTenantAccessIsDenied() {
        var actor = new ReportAccessPolicy.Actor(
                "user-A", "tenant-A", Set.of("REPORT_READ"));
        var report = new ReportAccessPolicy.Report(
                "r-02", "tenant-B", "user-B", "CONFIDENTIAL");

        assertFalse(policy.mayRead(actor, report));
    }

    @Test
    void missingAuthorityIsDenied() {
        var actor = new ReportAccessPolicy.Actor(
                "user-A", "tenant-A", Set.of("REPORT_EXPORT"));
        var report = new ReportAccessPolicy.Report(
                "r-01", "tenant-A", "user-A", "INTERNAL");

        assertFalse(policy.mayRead(actor, report));
    }

    @Test
    void missingTenantContextIsDenied() {
        var actor = new ReportAccessPolicy.Actor(
                "user-A", null, Set.of("REPORT_READ"));
        var report = new ReportAccessPolicy.Report(
                "r-01", "tenant-A", "user-A", "INTERNAL");

        assertFalse(policy.mayRead(actor, report));
    }
}
~~~

Unit tests xác minh logic hàm với dữ liệu giả định. Chúng **không chứng minh** token được xác thực, database filter đúng, controller không có đường bypass hoặc worker/storage không có quyền rộng. Cần integration/negative tests ở các boundary khác.

### 12.3. Tách response DTO và data access

Không trả JPA Entity nguyên vẹn nếu endpoint chỉ cần status. Có thể dùng projection để giới hạn dữ liệu được đọc và DTO để giới hạn trường được trả; nhưng vẫn phải kiểm tra tenant/resource authorization ở server.

~~~java
public record ReportSummary(
        String reportId,
        String status,
        java.time.Instant updatedAt) {}
~~~

Query minh họa:

~~~sql
SELECT r.id, r.status, r.updated_at
FROM reports r
WHERE r.id = :reportId
  AND r.tenant_id = :trustedTenantId;
~~~

`trustedTenantId` phải được xác định từ authenticated principal và policy server-side, không lấy trực tiếp từ client. Projection giúp giảm dữ liệu xử lý nhưng **không thay access control** và không tự bao phủ query khác.

### 12.4. Data layer như một lớp giới hạn blast radius

Nếu application policy có lỗi, database/cloud IAM vẫn nên giới hạn:
- DB service identity chỉ truy cập schema/table cần thiết.
- Worker chỉ đọc/ghi bucket/prefix được giao.
- KMS key policy tách quyền sử dụng và quản trị khi cần.
- Export URL có TTL và scope; file có lifecycle.
- Backup có quyền và account boundary riêng phù hợp risk.
- Không để application credential có quyền admin toàn bộ database/cloud account.

Đây là lớp **containment**, không phải lời đảm bảo ứng dụng có thể bỏ authorization. Database policy thường không biết đầy đủ quyền nghiệp vụ của user cuối, nên hai lớp bổ sung nhau.

## 13. Supply chain và runtime: lớp bảo vệ trước khi ứng dụng chạy

Một ứng dụng bảo mật có thể bị phá bởi artifact không đáng tin hoặc deployment identity quá mạnh.

### Chuỗi kiểm soát

~~~mermaid
flowchart LR
    SRC["Source / PR"] --> REVIEW["Code review"]
    REVIEW --> CI["CI: SAST / SCA / secret scan"]
    CI --> BUILD["Build artifact"]
    BUILD --> PROV["Digest / provenance / signing"]
    PROV --> GATE["Deploy approval / admission"]
    GATE --> RUN["Runtime workload"]
    RUN --> MON["Runtime monitoring"]
~~~

### Các câu hỏi cần đánh giá

- Ai có quyền merge code, sửa workflow và cấp runner credentials?
- CI runner có thể tự sửa IAM/production deployment policy không?
- Artifact digest đang chạy có khớp artifact đã kiểm tra không?
- Admission/runtime có xác minh image provenance theo policy không?
- Workload được gán ServiceAccount/role nào, có quyền nào?
- Secret/credential được cấp thế nào và có bị ghi vào logs không?
- Thay đổi config ngoài pipeline có được phát hiện?
- Khi pipeline hoặc signing key bị compromise, có thể dừng deploy và khôi phục nguồn tin cậy không?

**Code review và artifact signing là hai control khác nhau.** Signature có thể chứng minh artifact được ký bằng key được tin, nhưng không tự chứng minh code an toàn. SAST/SCA có thể phát hiện một số vấn đề nhưng không chứng minh runtime configuration và authorization đúng.

## 14. Kiểm thử defense in depth bằng failure injection có kiểm soát

Một kiến trúc nhiều lớp chỉ được kiểm chứng khi biết **hành vi lúc một lớp lỗi hoặc bị bypass**. Không nhất thiết tạo sự cố thật trên production; có thể dùng test environment hoặc controlled exercise được phê duyệt.

### Các kịch bản kiểm thử

| Test ID | Tình huống | Expected behavior |
| --- | --- | --- |
| **DID-T01** | Token thiếu/sai chữ ký/sai issuer | Edge hoặc resource server từ chối |
| **DID-T02** | User tenant A đổi report ID sang tenant B | Application authorization từ chối, không trả dữ liệu |
| **DID-T03** | Bỏ qua gateway, gọi backend direct IP/port | Network boundary chặn hoặc backend yêu cầu xác thực tương đương |
| **DID-T04** | Application policy test bị giả lập lỗi cho phép | Data/IAM scope vẫn giới hạn resource ngoài phạm vi |
| **DID-T05** | Worker thử đọc bucket/tenant không được cấp | IAM/resource policy từ chối |
| **DID-T06** | WAF/edge service không khả dụng | Failover theo policy, không mở direct backend ngoài kiểm soát |
| **DID-T07** | Identity/authorization service timeout | Hành động nhạy cảm không tự fail-open trái policy |
| **DID-T08** | Log collector ngừng nhận event | Source-health alert hoặc buffer/escalation hoạt động |
| **DID-T09** | Workload bị giả lập credential compromise | Revoke/rotate/isolate và detection theo runbook |
| **DID-T10** | CI runner dùng identity test thử sửa production IAM | Bị từ chối và có audit event |
| **DID-T11** | Thay image/config ngoài pipeline | Admission/drift detection phát hiện hoặc chặn theo policy |
| **DID-T12** | Export vượt volume/tenant đã duyệt | Rate/volume policy hoặc authorization chặn; alert phù hợp |
| **DID-T13** | Backup restore trong môi trường thử | Restore được kiểm chứng, quyền và dữ liệu được reconcile |
| **DID-T14** | Một lớp policy bị tắt trong test có kiểm soát | Lớp bổ sung vẫn ngăn/giới hạn scenario hoặc finding được ghi |
| **DID-T15** | IdP/CA/KMS common-cause dependency lỗi | Degraded mode đúng thiết kế; không âm thầm bỏ xác thực/bảo vệ |
| **DID-T16** | Synthetic security event đi qua nguồn → collector → alert recipient | Event được nhận đúng và độ trễ/coverage được ghi |
| **DID-T17** | Direct object URL cũ sau khi user bị revoke | URL hết hạn/không còn quyền theo policy được kiểm chứng |
| **DID-T18** | Database/queue TLS hoặc certificate verification lỗi | Client từ chối kết nối không hợp lệ, không plaintext fallback |
| **DID-T19** | Admin break-glass sử dụng ngoài quy trình | Bị chặn hoặc tạo alert/review theo policy |
| **DID-T20** | Evidence source thiếu quyền hoặc mất coverage | Assessment INCONCLUSIVE/FAIL theo tiêu chí, không tự PASS |

### Không phá control trên production để chứng minh

Failure injection phải có **scope, approval, rollback, người quan sát, điều kiện dừng và dữ liệu test** phù hợp. Không tự tắt WAF, revoke key thật hoặc xóa backup production chỉ để kiểm tra. Có thể dùng:
- Fault injection trong staging hoặc test account.
- Mock service/chaos test với quyền và tài sản không thật.
- Negative tests qua API với identity được tạo cho kiểm thử.
- Tabletop exercise và review runbook cho kịch bản chưa thể mô phỏng an toàn.
- Read-only verification trên production để đối chiếu cấu hình/route.

Nếu một kịch bản chưa thể test, ghi rõ **INCONCLUSIVE/untested**, nêu phương pháp đánh giá thay thế và residual risk. Không biến một tabletop thành bằng chứng runtime đã chặn attack path.

## 15. Assurance case: chứng minh các lớp bổ sung nhau

### Ví dụ cho RISK-DID-01

| Mắt xích | Nội dung |
| --- | --- |
| **Risk** | User tenant A hoặc session bị chiếm đọc report tenant B. |
| **Objective** | Bảo vệ confidentiality và giới hạn blast radius của account/workload. |
| **Architecture** | Gateway → Spring Boot API → authorization policy → DB; worker riêng và bucket scope riêng. |
| **Requirements** | Token validation, object authorization, network boundary, IAM least privilege, export audit. |
| **Controls** | OIDC, gateway policy, app policy, DB tenant scope, IAM, monitoring và incident response. |
| **Tests** | Wrong token, cross-tenant, direct route, bucket deny, log/alert, revoke/retest. |
| **Evidence** | Source/build/deployment, runtime config, IAM snapshot, test reports, synthetic event. |
| **Finding** | Worker role wildcard hoặc API route bypass nếu được phát hiện. |
| **Remediation** | Thu hẹp policy, đóng route, deploy và negative retest. |
| **Residual risk** | Những region/vendor/legacy path chưa test hoặc phụ thuộc shared IdP. |

### Mẫu YAML evidence register

Các giá trị trong dấu `<...>` là placeholder, **không phải kết quả đã kiểm tra**:

~~~yaml
assessment_id: DID-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
service: report-platform
environment: production
risk_ids:
  - RISK-DID-01
  - RISK-DID-02
objective_ids:
  - OBJ-CONFIDENTIALITY
  - OBJ-INTEGRITY
  - OBJ-ACCOUNTABILITY
requirement_ids:
  - DID-REQ-01
  - DID-REQ-02
  - DID-REQ-03
  - DID-REQ-04
  - DID-REQ-08
architecture:
  diagram_ref: "<APPROVED_DFD_VERSION>"
  trust_boundaries: ["public-edge", "service-network", "data-plane", "admin-plane"]
  shared_dependencies: ["<IDP>", "<PKI>", "<LOGGING>", "<CLOUD_CONTROL_PLANE>"]
  known_bypass_paths: "<INVENTORY_OR_NONE_WITH_EVIDENCE>"
controls:
  - control_id: CTRL-IDENTITY
    owner: "<OWNER>"
    policy_ref: "<EFFECTIVE_POLICY_VERSION>"
  - control_id: CTRL-APP-AUTHZ
    owner: "<OWNER>"
    policy_ref: "<APPLICATION_POLICY_VERSION>"
  - control_id: CTRL-DATA-IAM
    owner: "<OWNER>"
    policy_ref: "<EFFECTIVE_IAM_SNAPSHOT>"
  - control_id: CTRL-DETECTION
    owner: "<OWNER>"
    policy_ref: "<DETECTION_RULE_VERSION>"
implementation:
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<IMAGE_DIGEST>"
  deployment_id: "<RUNTIME_DEPLOYMENT_ID>"
  config_snapshot_ref: "<ACTUAL_CONFIG>"
verification:
  assessment_time: "<ISO_8601_UTC>"
  test_refs:
    - "<CROSS_TENANT_NEGATIVE_TEST>"
    - "<DIRECT_ROUTE_BYPASS_TEST>"
    - "<IAM_DENY_TEST>"
    - "<SYNTHETIC_ALERT_TEST>"
  failure_scenarios: ["<CONTROL_FAILURE_EXERCISE>"]
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
findings: ["<FINDING_IDS_IF_ANY>"]
exceptions: ["<APPROVED_EXCEPTION_IDS_IF_ANY>"]
residual_risk: "<REVIEWED_RISK_RATIONALE>"
limitations: "<UNTESTED_PATHS_REGIONS_VENDORS_OR_DEPENDENCIES>"
reassessment_triggers:
  - "New trust boundary, endpoint, service or data flow"
  - "Identity, IAM, network, key or CI/CD policy change"
  - "Security incident, drift, finding or exception expiry"
~~~

Không lưu secret, raw token, private key hoặc full customer record vào evidence. Evidence cần **source, scope, version, timestamp, integrity, owner và access controls**. Nếu sơ đồ không phản ánh runtime, đánh dấu limitation và bổ sung hiện vật actual-state.

### Design, implementation và operating effectiveness

| Lớp đánh giá | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| **Design effectiveness** | Các lớp có xử lý risk scenario và failure mode không? | Threat model, DFD, policy, architecture review |
| **Implementation** | Controls có trong code/IaC/build và đã được phê duyệt? | PR, CI results, IaC, artifact digest |
| **Operating effectiveness** | Runtime có áp dụng, bao phủ và không bypass? | Actual IAM/routes/config, negative tests, telemetry |
| **Recovery effectiveness** | Khi preventive/detective controls thất bại có thể khôi phục? | Restore/incident exercises, key rotation, retest |

**Một control PASS không kéo theo toàn kiến trúc PASS.** Ví dụ TLS, WAF và MFA đều hoạt động nhưng object authorization vẫn lỗi; claim confidentiality cho dữ liệu đa tenant vẫn FAIL.

## 16. Đánh giá hiệu quả và tránh đếm control hình thức

### 16.1. Coverage không chỉ là số lượng

Có thể dùng các chỉ số:
- % critical assets có owner, threat model và control mapping.
- % attack paths có preventive + detective + response/recovery coverage.
- % public/internal endpoints được inventory và có negative tests.
- % workload identities có least-privilege evidence.
- Số direct/bypass routes chưa xử lý.
- Số common-cause dependencies chưa có fallback/detection.
- Detection latency, containment time, recovery time và retest success.
- Số finding/exception quá hạn theo criticality.
- Evidence freshness và source completeness.

Không diễn giải **“có 5 lớp”** là “mạnh hơn 3 lớp”. Một lớp identity có policy chặt, resource authorization đúng và quyền dữ liệu tối thiểu có thể giá trị hơn nhiều thiết bị chồng lặp.

### 16.2. Defense in depth có thể thất bại theo cách nào?

| Anti-pattern | Vì sao nhiều lớp vẫn không bảo vệ? | Cách đánh giá |
| --- | --- | --- |
| Tất cả policy dùng chung admin credential | Một credential có thể tắt mọi lớp | Privilege map, admin-plane tests |
| Mọi lớp dựa cùng IdP/issuer không có fallback | Compromise/outage chung ảnh hưởng toàn bộ | Common-cause analysis, degraded-mode exercise |
| WAF và app cùng tin header client | Attacker giả danh và vượt cả hai | Negative header spoofing tests |
| Database chỉ tin network private | Workload bị chiếm có thể đọc dữ liệu quá rộng | Effective IAM/DB grants, deny tests |
| SIEM mất nguồn nhưng dashboard xanh | Detective layer không quan sát | Synthetic event và source health |
| Backup chung account/role với production | Attacker có thể xóa cả dữ liệu và recovery copy | Permission separation, restore exercise |
| Nhiều control cùng kiểm tra cùng một thuộc tính sai | Sai dữ liệu đầu vào làm tất cả quyết định sai | Independent source/completeness validation |
| Ngoại lệ vô thời hạn | Lớp yếu trở thành đường chính lâu dài | Expiry, owner, review và compensating tests |
| Chỉ test happy path | Không phát hiện bypass/failure mode | Negative/fault tests |
| Evidence chỉ là screenshot cấu hình | Không chứng minh runtime hoặc coverage | Deployment-bound runtime evidence |

### 16.3. Chất lượng của evidence

Evidence có giá trị khi:
- Gắn với **asset/service/environment/version/time**.
- Nguồn được xác định và có completeness/health.
- Phương pháp test có expected result và record thực tế.
- Có người review và limitation.
- Không bị tạo/sửa/xóa dễ dàng bởi cùng actor có thể tấn công control.
- Được lưu theo access/retention phù hợp.
- Có thể đối chiếu với finding/remediation/retest.

Một ảnh dashboard xanh là một mẩu dữ liệu, không phải assurance case.

## 17. Finding, remediation và retest theo nhiều lớp

Khi phát hiện một lớp thất bại, không chỉ sửa đúng component đó. Cần đánh giá **đường tấn công và các lớp liên quan**, xem lỗi có lặp lại ở nơi khác không.

### Ví dụ: worker có quyền đọc mọi bucket

1. **Xác nhận finding:** lấy effective IAM policy, identity mapping, bucket list và workload đang chạy.
2. **Xác định blast radius:** loại dữ liệu, tenant, khả năng đọc/ghi/xóa, các service khác dùng chung role.
3. **Triage incident:** nếu có dấu hiệu bị khai thác, phối hợp incident response và bảo toàn evidence.
4. **Sửa preventive control:** role riêng, giới hạn actions/resources, job-level authorization.
5. **Kiểm tra network/identity:** worker có thể gọi storage trực tiếp ngoài API? Ai có thể gán role?
6. **Kiểm tra detective control:** event truy cập bucket có được nhận và alert không? Source có đầy đủ?
7. **Kiểm tra recovery:** file/dữ liệu đã lộ hoặc bị sửa có cần khôi phục? Credential/key nào phải rotate?
8. **Deploy và retest:** allowed bucket pass, other bucket deny, cross-tenant job deny, runtime policy đúng digest.
9. **Review common cause:** CI/admin có thể tự nới IAM trở lại? Có drift alert?
10. **Đóng finding:** chỉ khi acceptance criteria và evidence đáp ứng, limitation/residual risk được phê duyệt.

### Tách các quyết định

- **Remediation complete:** thay đổi đã được triển khai.
- **Retest passed:** kiểm thử sau sửa đạt tiêu chí trong phạm vi.
- **Finding closed:** reviewer xác nhận tiêu chí đóng và evidence.
- **Residual risk accepted:** risk owner chấp nhận phần rủi ro còn lại theo thẩm quyền.

Một ticket “Done” không tự chứng minh bốn kết luận trên.

## 18. Trách nhiệm trong chương trình defense in depth

| Vai trò | Trách nhiệm | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Business/System Owner** | Xác định critical assets, impact, mục tiêu bảo vệ và risk appetite | Asset inventory, impact analysis, risk decisions |
| **Solution Architect** | Xây DFD, trust boundaries, defense layers, dependency/common-cause map | Architecture decision record, threat model |
| **Security Architect/AppSec** | Xác định security requirements, review design, kiểm tra attack paths | Threat model, control mapping, security review |
| **Developer/Tech Lead** | Triển khai app controls, safe defaults, test và sửa lỗi | Source/PR, unit/integration tests |
| **Platform/Network/SRE** | IAM, ingress/egress, mesh, KMS, logging, backup và runtime health | Config snapshots, access policy, monitoring |
| **SOC/Incident Response** | Detection, triage, containment, forensic evidence và lessons learned | Alert tests, incident timeline, runbook |
| **GRC/Control Owner** | Duy trì control register, cadence, exception và evidence | Control register, assessment, exception record |
| **Risk Owner** | Phê duyệt treatment/exception và residual risk trong quyền hạn | Risk acceptance, expiry, action plan |
| **Assessor/Audit** | Đánh giá design/operating effectiveness và retest độc lập khi cần | Assessment report, findings, review trail |

Một nhóm có thể kiêm nhiều vai trò, nhưng phải rõ **ai chịu trách nhiệm cuối cùng** cho control và ai có thẩm quyền chấp nhận rủi ro. Người triển khai không nên tự duyệt exception của chính control đó nếu yêu cầu độc lập áp dụng.

## 19. Case study: nền tảng báo cáo tài chính đa tenant

### Bối cảnh

Một nền tảng Java/Spring Boot có:
- Browser và mobile clients gọi API gateway.
- `report-api` xử lý user requests và tạo export jobs.
- Message broker phân phối job.
- `export-worker` đọc PostgreSQL và ghi file vào object storage.
- Workload identity federation cấp cloud credentials.
- SIEM nhận audit events.
- Backup/DR ở cloud account khác.
- CI/CD build và deploy các services.

### Phát hiện ban đầu

1. Gateway xác thực JWT nhưng một endpoint cũ chỉ kiểm tra user đã đăng nhập.
2. `report-api` tin `tenantId` từ request header.
3. Worker dùng một cloud role chung có quyền đọc mọi bucket.
4. Broker có listener plaintext trong network nội bộ.
5. CI runner có quyền sửa ServiceAccount binding production.
6. Log collector ngừng nhận audit event từ worker nhưng dashboard chỉ hiển thị số finding.
7. Backup và production dùng chung admin role có thể xóa cả hai.

### Mapping attack path và lớp

| Finding | Lớp thiếu/yếu | Biện pháp bổ sung | Retest |
| --- | --- | --- | --- |
| Endpoint cũ thiếu object authZ | Application | Server-side tenant/resource policy, remove/guard legacy route | Cross-tenant negative test |
| Tin tenant header | Identity/Application | Derive trusted tenant context từ principal/relationship | Spoof header test |
| Worker IAM wildcard | Data/Identity | Role riêng theo worker và bucket/prefix | Allowed/denied storage tests |
| Broker plaintext | Network | TLS/mTLS và peer verification cho producer/consumer | Plaintext listener và wrong-cert tests |
| CI runner sửa SA production | Supply chain/Governance | Tách build/deploy privilege, approval/admission | CI identity denied-change test |
| Collector mất nguồn | Detection | Source-health alert, synthetic event end-to-end | Event → collector → alert test |
| Backup chung admin | Recovery/Governance | Separate backup admin boundary, immutable/isolated copies phù hợp | Permission review và restore exercise |

### Assurance case sau remediation

Không viết “đã triển khai defense in depth”. Thay vào đó, claim phải giới hạn rõ:

> Trong phạm vi các luồng user report-read/export và worker storage của production deployment đã đánh giá, token và caller được xác minh; API từ chối truy cập chéo tenant; worker chỉ có quyền trên bucket/prefix theo job được duyệt; producer/consumer sử dụng TLS theo baseline; CI test identity không thể thay production binding; mất nguồn audit event được phát hiện; backup admin được tách khỏi quyền production theo policy. Các đường legacy/vendor/region chưa kiểm tra được ghi riêng.

Claim này chỉ đạt nếu có **runtime evidence và retest** cho từng điều được nêu. Việc một nhóm hoàn tất ticket cấu hình không tự tạo ra bằng chứng cho toàn bộ câu.

## 20. Bài tập thực hành

**Tình huống:** một hệ thống thương mại điện tử chạy Spring Boot có API gateway, order service, payment service, queue, worker, PostgreSQL, object storage, SIEM và backup. Nhóm review thấy:

- API gateway có WAF và OIDC, nhưng backend vẫn có direct port.
- Application kiểm tra role nhưng không kiểm tra ownership của order.
- Payment service và order service dùng chung database account.
- Worker có quyền đọc tất cả object storage.
- Service-to-service traffic dùng TLS ở ingress nhưng chưa có inventory các hop nội bộ.
- SIEM không cảnh báo khi collector ngừng nhận logs.
- CI runner có quyền sửa production network/IAM policy.
- Backup có mã hóa nhưng dùng cùng cloud admin role với production.
- Có break-glass admin không expiry và không review sau sử dụng.

### Yêu cầu

1. Vẽ DFD, đánh dấu trust boundaries, entry points, admin plane, data plane và TLS termination.
2. Viết ít nhất **năm risk scenarios** theo asset, actor, attack path, weakness và impact.
3. Chia các controls hiện có vào preventive, detective, corrective/recovery; chỉ ra lớp bị thiếu.
4. Thiết kế kiến trúc nhiều lớp cho **order ownership**, **payment isolation**, **worker storage scope** và **backup protection**.
5. Xác định ít nhất **năm common-cause failures**, gồm shared database account, CI admin, logging, IdP và backup.
6. Viết ít nhất **tám negative/failure tests**, gồm direct-port bypass, cross-order, worker bucket deny, missing logs, CI privilege, break-glass expiry và restore.
7. Tạo 5–8 security requirements có owner, acceptance criteria và evidence.
8. Lập evidence register cho một claim cụ thể, có version, deployment, runtime config, test results, reviewer và limitations.
9. Đề xuất finding/remediation/retest cho hai vấn đề critical nhất.
10. Giải thích vì sao “đã có WAF + OIDC + TLS + encryption at rest” vẫn chưa đủ để chấm PASS.

### Gợi ý hướng giải

| Phát hiện | Hướng xử lý | Evidence |
| --- | --- | --- |
| Direct backend port | Chặn route hoặc áp dụng authN/authZ tương đương; test từ network zones | Route inventory, bypass test |
| Role không kiểm tra ownership | Object-level policy theo order/tenant | Cross-order negative tests |
| Shared DB account | Identity/DB grants riêng theo service, giảm quyền | Effective DB grants, denied query tests |
| Worker storage wildcard | Scoped role theo bucket/prefix/job | IAM snapshot, positive/negative access |
| Thiếu internal TLS inventory | Vẽ từng hop và kiểm chứng runtime | DFD, handshake, wrong-cert tests |
| SIEM mất nguồn | Source health và synthetic event path | Collector health/alert test |
| CI admin quá rộng | Tách build, approval và deploy; policy guard | CI IAM negative test, audit |
| Backup chung admin | Tách role/account và kiểm tra restore | Permission evidence, restore exercise |
| Break-glass không expiry | JIT/time-bound, approval và post-use review | Expiry/revoke test, review record |

### Câu hỏi nâng cao

Một tổ chức có WAF, API gateway, mTLS service mesh, database encryption và SIEM. Tất cả cùng được cấu hình qua một cloud admin role; attacker chiếm được role đó và có thể tắt WAF, thay trust policy, đọc key, sửa IAM và xóa log.

**Kiến trúc có bao nhiêu lớp bảo vệ độc lập?** Cần bổ sung những ranh giới quản trị, audit source, backup và cơ chế phục hồi nào? Bằng chứng nào cho thấy một admin compromise không thể xóa toàn bộ khả năng phát hiện và khôi phục?

**Định hướng:** đếm sản phẩm không phản ánh tính độc lập. Phải lập dependency/common-cause map, tách đặc quyền, bảo vệ audit/backup bằng boundary khác phù hợp, phát hiện thay đổi control plane và thử runbook phục hồi. Không có một cấu hình duy nhất thay cho threat model và kiểm chứng.

## 21. Những sai lầm thường gặp

| Ngộ nhận | Vì sao nguy hiểm? | Thực hành phù hợp |
| --- | --- | --- |
| “Càng nhiều công cụ bảo mật càng tốt.” | Nhiều công cụ có thể cùng lỗi, trùng coverage hoặc tăng phức tạp | Chọn control theo attack path và giá trị bổ sung |
| “WAF đã chặn SQL injection nên không cần parameterized query.” | WAF không thay coding control và có thể bị bypass | Defense at edge + safe query + tests |
| “User đã login thì có thể đọc mọi record.” | Authentication không thay object/tenant authorization | Check principal/action/resource/context |
| “Mạng private nghĩa là tin cậy.” | Workload/insider bị chiếm vẫn có thể di chuyển ngang | Segmentation, identity, service authZ |
| “mTLS nghĩa là service được quyền gọi mọi API.” | Peer authentication khác business authorization | Map identity tới action/resource |
| “Database encryption bảo vệ mọi trường hợp lộ dữ liệu.” | App/DB user có thể đọc plaintext khi xử lý | Least privilege, minimization, access tests |
| “SIEM không có alert nghĩa là không có sự cố.” | Có thể mất nguồn, rule hoặc người nhận | Synthetic events, source health, detection test |
| “Backup job xanh nghĩa là khôi phục được.” | Có thể backup lỗi logic, thiếu key hoặc không restore được | Restore exercise và data reconciliation |
| “Ba lớp dùng chung admin vẫn độc lập.” | Một credential có thể tắt cả ba | Common-cause analysis và privilege separation |
| “Private subnet thay được TLS.” | Không xác minh peer và không bảo vệ mọi trust boundary | TLS/mTLS theo threat model và yêu cầu |
| “Fail-open giữ availability là luôn đúng.” | Có thể biến outage thành bypass bảo mật | Risk-based degraded mode, explicit policy |
| “Fail-closed luôn an toàn.” | Có thể gây mất chức năng quan trọng hoặc nguy hiểm nghiệp vụ | Thiết kế fail-safe theo tác vụ và safety needs |
| “Một test happy path đủ chứng minh kiến trúc.” | Không kiểm tra bypass và failure mode | Negative/fault tests, coverage map |
| “Một control PASS kéo cả kiến trúc PASS.” | Lớp khác có thể thất bại hoặc thiếu evidence | Kết luận theo requirement/claim riêng |
| “Exception được duyệt tức lỗi đã sửa.” | Risk acceptance không đổi trạng thái kỹ thuật | Theo dõi residual risk và expiry riêng |
| “Đã deploy cấu hình nên finding có thể đóng.” | Runtime có thể drift hoặc chưa dùng config mới | Actual-state verification và retest |
| “Sơ đồ kiến trúc phản ánh production.” | Có thể thiếu route cũ, region, admin path và vendor | Reconcile DFD với asset/route/runtime inventory |
| “Không tìm thấy bypass nghĩa là không có bypass.” | Scanner/test có thể thiếu coverage | Ghi source health, test scope và INCONCLUSIVE nếu cần |

## Ghi nhớ

- **Defense in depth** là nhiều lớp kiểm soát **bổ sung và có khả năng giới hạn hậu quả khi lớp khác thất bại**, được bố trí theo risk scenario và trust boundary.
- Một lớp chỉ có giá trị khi có **coverage, effectiveness, ownership, failure behavior, bypass resistance và evidence**; số lượng sản phẩm không phản ánh độ an toàn.
- Phải phân biệt **preventive, detective và corrective/recovery**; phát hiện sau sự cố không thay một control cần ngăn hành động ngay từ đầu.
- Kiểm tra **common-cause failure**: identity, admin, CI/CD, CA/KMS, configuration, logging và backup có thể là điểm lỗi chung làm nhiều lớp cùng sụp đổ.
- Trong Java/Spring Boot, gateway/WAF, workload identity, application authorization, database/IAM, TLS, logging, incident response và recovery phải phối hợp nhưng được đánh giá theo từng mục tiêu.
- Security assurance cần **positive/negative/failure tests** ở các boundary, gắn với đúng artifact, deployment, runtime config, environment, timestamp và reviewer.
- **PASS một control không đồng nghĩa PASS toàn kiến trúc**; thiếu coverage phải ghi INCONCLUSIVE/limitation, findings cần remediation và retest.
- Kiến trúc phải được đánh giá lại khi thêm service/route/data flow, đổi IAM/network/CI, thay trust boundary, phát hiện drift hoặc xảy ra incident.
