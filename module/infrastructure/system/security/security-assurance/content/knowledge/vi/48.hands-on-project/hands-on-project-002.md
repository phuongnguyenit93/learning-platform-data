# Dự án thực hành: Xây control framework có bằng chứng cho hệ thống số

**Control framework** là hệ thống có cấu trúc để chuyển **mục tiêu bảo mật, yêu cầu, rủi ro và nghĩa vụ** thành những **security controls có chủ sở hữu, phạm vi, cách triển khai, tiêu chí kiểm chứng, bằng chứng và cơ chế giám sát**. Một danh sách “bật MFA”, “mã hóa dữ liệu” hoặc “đã quét lỗ hổng” chưa phải control framework đủ khả năng security assurance, bởi chưa biết điều kiện nào phải đạt, ở đâu, ai chịu trách nhiệm và bằng chứng có tin cậy hay không.

Bài học thuộc chương **Dự án thực hành**, module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu của module là xây dựng cách đánh giá **có bằng chứng** hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, security requirements và controls tới kiểm thử, audit, xử lý findings và continuous assurance trong phát triển/vận hành. Vì vậy, dự án yêu cầu người học **thực sự thiết kế và kiểm chứng một framework thu nhỏ** thay vì chỉ tổng hợp định nghĩa hoặc sao chép bảng kiểm từ tiêu chuẩn.

Dự án sử dụng **một doanh nghiệp và hệ thống hoàn toàn giả định**. Các control IDs, tài sản, ngày tháng, kết quả test, KPI và số liệu đều là dữ liệu học tập; không thể được dùng như chứng cứ hệ thống thật. Các framework tham chiếu như NIST CSF, ISO/IEC 27001/27002, CIS Controls và OWASP ASVS chỉ được dùng ở **mức định hướng phân nhóm và đối chiếu có kiểm tra**, không được tuyên bố đạt chứng nhận hoặc coverage đầy đủ vì có tên trong bảng mapping.

> **Đề bài chính:** Trong vai Security Assurance Engineer, hãy xây dựng một **minimum viable control framework** cho nền tảng dịch vụ đặt hàng–thanh toán giả định, có đủ traceability **risk → requirement → control → assertion → test → evidence → verdict → finding/remediation → reporting**. Sản phẩm cuối phải cho phép một người đánh giá độc lập tái lập hoặc kiểm tra hợp lý những kết luận quan trọng.

## 1. Kết quả học tập và năng lực cần chứng minh

Sau dự án, người học phải có khả năng:

1. Xác định **phạm vi hệ thống, tài sản, dữ liệu, ranh giới tin cậy, các bên phụ thuộc và mục tiêu nghiệp vụ**.
2. Phân tích rủi ro theo threat scenarios và business impact, tránh thiết kế controls theo cảm tính.
3. Chuyển policy/security requirements thành **control objectives** và **assertions có thể kiểm**.
4. Xây control library có taxonomy, ID ổn định, owner, applicability, implementation, test, evidence, status và review triggers.
5. Thiết lập **baseline tối thiểu** cho IAM, data protection, application, infrastructure, software supply chain, logging/detection, incident response, backup/DR và third-party.
6. Phân biệt **control design, implementation, effective state, operating effectiveness**, bằng chứng ở từng lớp và kết luận có giới hạn.
7. Thiết kế positive/negative test, population, sample, frequency và evidence quality.
8. Gắn framework vào quy trình CI/CD, IaC, change/release, operations và audit.
9. Tổ chức ownership/RACI, separation of duties và risk-based exception có hạn.
10. Lập gap/finding register, chọn remediation priority, retest và verified closure.
11. Đo verified control coverage, evidence freshness và exceptions bằng KPI có mẫu số độc lập.
12. Trình bày **assurance case** và executive report phản ánh cả PASS, FAIL, INCONCLUSIVE và NOT_TESTED.

**Phân biệt quan trọng:** xây control framework không phải “copy 100 controls cho đủ”; mục tiêu là **một tập controls tối thiểu nhưng liên quan, không trùng vô ích, có thể vận hành và kiểm chứng**. Phần mở rộng sang nhiều domains chỉ thực hiện sau khi nền tảng traceability hoạt động.

## 2. Tình huống dự án giả định: nền tảng OrderFlow

### 2.1. Bối cảnh tổ chức

Doanh nghiệp giả định **OrderFlow** cung cấp ứng dụng đặt hàng và thanh toán cho nhiều nhà bán hàng. Nền tảng xử lý đơn hàng, thông tin liên lạc của khách, địa chỉ giao hàng và **token tham chiếu giao dịch** từ nhà cung cấp thanh toán. Giả định hệ thống **không lưu số thẻ đầy đủ hoặc CVV**; người học vẫn phải đánh giá các nghĩa vụ thanh toán/riêng tư trên thực tế trước khi tuyên bố phạm vi tuân thủ.

Business objectives được giả định:

- Khách hàng chỉ thấy đơn hàng của mình; nhà bán hàng chỉ thấy dữ liệu trong tenant được cấp.
- Đơn hàng và trạng thái thanh toán phải **đúng, không bị nhân đôi hoặc xóa trái phép**.
- Những API quan trọng phải có availability và khả năng phục hồi đã được phê duyệt.
- Thao tác đặc quyền và thay đổi dữ liệu nhạy cảm có đủ log để điều tra.
- CI/CD không được triển khai artifact không được phép hoặc policy trái baseline.
- Vendor, cloud và recovery dependencies được quản lý có trách nhiệm.
- Những quyết định không đạt control phải có owner, risk acceptance hợp lệ và hạn xử lý.

### 2.2. Giới hạn và giả định

Dự án học tập giả định **hai môi trường production và pre-production**, một cloud provider, một Kubernetes cluster chính, một vùng recovery tách biệt và một bên xử lý thanh toán. Không yêu cầu triển khai trên cloud thật; có thể chứng minh framework bằng **synthetic data, test harness, mô phỏng config, evidence samples và kết quả diễn tập có chú thích**.

Không sử dụng secrets hoặc dữ liệu khách hàng thật. Không quét, khai thác, kiểm thử xâm nhập hoặc thử quyền trên các hệ thống không do mình sở hữu/không được ủy quyền. Với hoạt động rủi ro cao như fault injection, restore, quyền IAM hoặc network change, dùng **sandbox có giới hạn** và phương pháp được phê duyệt.

### 2.3. Danh mục tài sản ban đầu

| Asset ID | Thành phần | Dữ liệu/quyền | Môi trường | Owner giả định |
|---|---|---|---|---|
| **AS-01** | Public API Gateway | Internet ingress, access tokens | Production | Platform Team |
| **AS-02** | Order API | Order, tenant identifiers, authz | Production | Order Team |
| **AS-03** | Payment Worker | Payment tokens/references, queue processing | Production | Payment Team |
| **AS-04** | Managed Database | Orders, customer contacts, payment status | Production | Data Platform |
| **AS-05** | Message Broker | Order/payment events, DLQ | Production | Platform Team |
| **AS-06** | IdP và IAM | Users, roles, privileged identities | Shared | Identity Team |
| **AS-07** | KMS/Secrets Manager | Encryption keys, service secrets | Shared | Security Platform |
| **AS-08** | Kubernetes/Container Registry | Image digests, service accounts, policies | Production | Platform Team |
| **AS-09** | CI/CD Pipeline | Build credentials, artifact promotion | Shared | Developer Platform |
| **AS-10** | Central SIEM/Logging | Security/audit events, alert routes | Shared | SOC |
| **AS-11** | Backup/DR Environment | Encrypted backups, recovery IAM, restore | Recovery | Resilience Team |
| **AS-12** | Payment Provider | Payment processing API/webhooks | External | Vendor Owner |
| **AS-13** | Admin Portal | Privileged support operations | Production | Operations |
| **AS-14** | Infrastructure-as-Code repository | Cloud/IAM/network desired state | Shared | Platform Team |

Danh mục này **chưa phải toàn bộ population**. Người học phải chủ động kiểm tra những điểm thiếu như batch jobs, third-party support accounts, DNS/certificates, staging data, local admin, recovery keys và logging sources.

### 2.4. Sơ đồ kiến trúc và trust boundaries

~~~mermaid
flowchart LR
    U["Customer / Merchant"] --> EDGE["AS-01 API Gateway"]
    EDGE --> ORDER["AS-02 Order API"]
    ORDER --> DB["AS-04 Database"]
    ORDER --> BUS["AS-05 Message Broker"]
    BUS --> PAY["AS-03 Payment Worker"]
    PAY --> PSP["AS-12 Payment Provider"]
    IDP["AS-06 IdP/IAM"] --> ORDER
    IDP --> ADMIN["AS-13 Admin Portal"]
    KMS["AS-07 KMS/Secrets"] --> DB
    KMS --> PAY
    CI["AS-09 CI/CD"] --> K8S["AS-08 K8s/Registry"]
    K8S --> ORDER
    K8S --> PAY
    ORDER --> SIEM["AS-10 SIEM"]
    ADMIN --> SIEM
    DB --> BACKUP["AS-11 Backup/DR"]
    KMS --> BACKUP
~~~

Sơ đồ là dữ liệu đề bài, **không phải bằng chứng rằng các mạng/permissions thực sự được cô lập**. Người học cần đặt trust boundaries: Internet→Gateway, user/tenant→API, workload→DB/KMS, CI→runtime, production→recovery và customer→vendor.

### 2.5. Business Impact Analysis sơ bộ

| Business service | Criticality giả định | Hậu quả chính | Recovery objective giả định |
|---|---|---|---|
| Đặt hàng | High | Mất giao dịch, truy cập sai tenant | RTO 2 giờ, RPO 15 phút |
| Xác nhận thanh toán | Critical | Sai tiền, duplicate charge, gián đoạn | RTO 1 giờ, RPO 5 phút |
| Hỗ trợ quản trị | High | Privilege misuse, sai dữ liệu | RTO 4 giờ, log required |
| Audit/detection | High | Mất khả năng quan sát/forensics | Required event classes không mất im lặng |
| Export/reporting | Medium | Lộ dữ liệu, lỗi aggregate | Có thể tạm dừng theo approved degraded mode |

Tất cả mục tiêu là **giả định học tập**. Trong hệ thống thật, BIA và risk owner phải phê duyệt; RTO/RPO không thể tự suy ra từ bảng kỹ thuật.

## 3. Hồ sơ đầu bài và các phát hiện có sẵn

Bạn nhận được 12 quan sát ban đầu từ nhóm giả định:

| Finding ID | Quan sát | Evidence tình huống | Chưa thể kết luận |
|---|---|---|---|
| **F-01** | Một local admin path không qua SSO/MFA | Controlled login test cho test principal | Có access path khác? |
| **F-02** | Role Payment Worker có wildcard read secrets | IAM policy export | Effective grant và blast radius đầy đủ? |
| **F-03** | Object authorization chỉ được test happy-path | Test suite inventory | Có cross-tenant vulnerability thật hay chưa |
| **F-04** | Một DB backup job báo SUCCESS | Job log | Restore, KMS decrypt, RTO/RPO đạt không |
| **F-05** | Audit event của admin portal thiếu actor field | Sample SIEM event | Các event classes/period khác |
| **F-06** | Container image dùng mutable tag | Deployment manifest | Digest đang chạy và provenance |
| **F-07** | Một cloud account mới chưa có trong scan inventory | Asset diff | Các controls ở account có đạt không |
| **F-08** | Vendor support token không có expiry | Access grant | Quyền thực tế, offboarding, monitoring |
| **F-09** | Một critical detection rule bị suppress | Rule config export | False negatives và bypass impact |
| **F-10** | Recovery account được chia sẻ KMS key | Key policy diff | Least privilege, decrypt test |
| **F-11** | Pipeline có emergency override không ghi decision ID | Workflow config | Có artifact nào đã dùng override? |
| **F-12** | Policy của network allowlist được thay bằng console | Cloud audit event | IaC drift và effective ingress |

**Nguyên tắc đánh giá:** Một quan sát như “chưa có negative authz test” là **evidence gap/NOT_TESTED**, không tự khẳng định ứng dụng đang có lỗ hổng cross-tenant. Một backup SUCCESS chưa chứng minh restore readiness. Một config export có wildcard không tự chứng minh hoạt động lạm dụng đã xảy ra.

## 4. Sản phẩm bàn giao của dự án

Không cần tạo 12 tệp vật lý trong bài học này; đây là **bộ artifacts cần học viên chuẩn bị**, có thể trình bày trong workspace/portfolio của họ:

| Artifact ID | Tên sản phẩm | Yêu cầu tối thiểu để được đánh giá |
|---|---|---|
| **D-01** | Scope & asset register | In-scope/out-of-scope, owners, data classification, dependencies |
| **D-02** | Risk & threat register | Scenarios, affected assets, likelihood/impact rationale, owner |
| **D-03** | Requirements & obligations register | Mục tiêu, requirement ID, nguồn, applicability, phiên bản |
| **D-04** | Control library | Stable control IDs, objectives, statements, ownership, scope |
| **D-05** | Requirement–risk–control mapping | Có traceability cả hai chiều và gap detection |
| **D-06** | Control assurance test catalog | Assertion, method, expected result, negative tests, sampling |
| **D-07** | Evidence register | Evidence ID, source, collected time, scope, integrity, limitations |
| **D-08** | Evaluation matrix | PASS/FAIL/INCONCLUSIVE/NOT_TESTED/NOT_APPLICABLE theo unit |
| **D-09** | Findings & remediation backlog | Condition, risk, owner, priority, deadline, retest và closure |
| **D-10** | Exceptions & risk decisions | Approved scope, reason, compensating controls, expiry, triggers |
| **D-11** | KPI & assurance report | Mẫu số độc lập, verified coverage, gaps, trend, critical decisions |
| **D-12** | Governance & change integration | RACI, control lifecycle, review cadence, CI/CD/DR triggers |

**Tiêu chí hoàn thành cốt lõi:** một assessor có thể chọn bất kỳ control critical nào và lần ngược được **tại sao cần**, **nơi áp dụng**, **cách thử**, **bằng chứng hiện hành**, **kết luận**, và **hành động khi không đạt**.

## 5. Kế hoạch thực hiện theo giai đoạn

Dự án gợi ý **sáu giai đoạn**, không bắt buộc theo số ngày cố định. Người học có thể hoàn thành trên dữ liệu giả định trước khi tích hợp công cụ thật.

| Giai đoạn | Công việc | Sản phẩm | Exit criteria |
|---|---|---|---|
| **P1 — Context** | Scope, asset/data/service owners, trust boundaries, BIA | D-01 | Không bỏ sót critical services trong đề bài |
| **P2 — Risks & requirements** | Threat modeling, risk register, obligations, applicability | D-02, D-03 | Mỗi high-risk scenario có requirement |
| **P3 — Control design** | Taxonomy, controls, ownership, traceability | D-04, D-05, D-12 | Critical risks có control decision và owner |
| **P4 — Assurance design** | Assertions, tests, evidence contracts và sampling | D-06, D-07 | Mỗi critical control có cách xác minh |
| **P5 — Evaluate & remediate** | Chạy mô phỏng tests, verdicts, findings, exceptions | D-08, D-09, D-10 | Không đánh PASS nếu thiếu evidence |
| **P6 — Report & improve** | KPI, assurance case, demo, governance review | D-11, updated D-12 | Báo cáo nêu PASS, FAIL, unknown và next actions |

### 5.1. Phân chia vai trò trong nhóm thực hành

Nếu có nhóm 4–6 học viên, có thể phân vai: **business/risk owner**, **security framework designer**, **engineering/control owner**, **assessor/test lead**, **GRC/evidence coordinator** và **SOC/DR reviewer**. Phải tổ chức peer review để người viết một control không tự cho PASS nếu test yêu cầu đánh giá độc lập.

Nếu làm cá nhân, hãy mô phỏng các vai bằng **decision log và review checklist**, đồng thời ghi rõ hạn chế do không có independent assessor thực sự.

### 5.2. Quy tắc quản lý tiến độ

- Ghi mọi giả định và nguồn dữ liệu, không bịa evidence.
- Phiên bản hóa các registers và control changes.
- Cấm đánh PASS cho yêu cầu chưa được test.
- Khi scope đổi, cập nhật risk/mapping/tests trước khi tuyên bố coverage.
- Giữ kết quả FAIL trong lịch sử sau khi retest PASS.
- Học viên được tạo evidence **synthetic** nhưng phải gắn nhãn rõ.
- Kết luận chỉ áp dụng cho phạm vi của môi trường mô phỏng đã xét.

## 6. Phân biệt control framework với checklist, policy và tiêu chuẩn

| Thành phần | Định nghĩa | Ví dụ | Điều còn thiếu nếu dùng riêng |
|---|---|---|---|
| **Security objective** | Kết quả bảo vệ cần đạt | Không có truy cập đơn hàng vượt tenant | Chưa quy định phải làm gì/cách chứng minh |
| **Policy** | Quy tắc quản trị áp dụng | Mọi admin path production cần MFA | Chưa xác minh các đường đăng nhập thực |
| **Standard/baseline** | Yêu cầu kỹ thuật tối thiểu | Workloads không dùng excessive privileges | Chưa có asset/test/evidence |
| **Control** | Biện pháp tổ chức/kỹ thuật thực hiện objective | Enforcement object-level authz tại API | Chưa chứng minh hoạt động |
| **Procedure/runbook** | Cách thực hiện nhất quán | Cấp role, quay khóa, xử lý alert | Có thể không chạy đúng |
| **Control assertion** | Điều kiện đo được, đúng scope | Role support không xem tenant khác | Cần test/evidence |
| **Test method** | Cách xác minh assertion | Negative authz call với test identities | Một test có thể thiếu coverage |
| **Evidence** | Kết quả/artefact có provenance | Authz test log, IAM effective export | Phải đánh giá sufficiency/freshness |
| **Assurance verdict** | Kết luận về assertion trong scope | PASS_WITH_SCOPE, FAIL, INCONCLUSIVE | Không tự chứng minh ngoài phạm vi |
| **Control framework** | Toàn bộ vòng đời, mối liên hệ và governance | Library + mapping + test + evidence + owner + remediation | Cần được vận hành và cập nhật |

### 6.1. Sử dụng framework tham chiếu đúng cách

Có thể tham khảo các hệ thống phổ biến ở **cấp mục tiêu và nhóm controls**:

- **NIST Cybersecurity Framework:** khung quản trị kết quả an ninh mạng cấp tổ chức, hỗ trợ xác định mục tiêu và hiện trạng.
- **ISO/IEC 27001/27002:** tham chiếu quản lý an toàn thông tin và danh mục controls; phải xác định phiên bản, scope và applicability nếu làm mapping chính thức.
- **CIS Controls:** danh mục safeguards kỹ thuật/quản trị để xây baseline thực thi.
- **OWASP ASVS:** tham chiếu yêu cầu xác minh security cho ứng dụng/web APIs.
- **Cloud provider shared-responsibility model:** định nghĩa phần provider làm và phần khách hàng vẫn phải cấu hình/kiểm chứng.
- **Yêu cầu nội bộ/hợp đồng:** BIA, data protection, customer commitments và chính sách được phê duyệt.

**Mapping không phải chứng nhận.** Một hàng gắn “NIST/ISO/CIS” chưa chứng minh tổ chức đáp ứng yêu cầu; cần đúng phiên bản, điều khoản, scope, implementation và evidence. Không phát minh điều khoản chuẩn, không khẳng định thuộc diện PCI/GDPR hay nghĩa vụ nào khi chưa biết thực tế.

### 6.2. Chọn mức chi tiết

**Quá thô:** “Bảo vệ dữ liệu”, không test được.

**Quá nhỏ:** mỗi checkbox hoặc mỗi endpoint tạo một control ID khác nhau, gây khó quản lý và trùng.

**Phù hợp:** control statement gắn một objective/decision rõ, có thể áp cho population nhiều units; cụ thể hóa ở cấp **assertions/test cases** cho từng service/identity/data boundary. Ví dụ control AUTHZ-01 là “Enforce object-level tenant isolation” áp cho Order API và Admin Portal; test cases có nhiều role/resource paths.

## 7. Xác định ranh giới phạm vi và applicability

### 7.1. Lập in-scope/out-of-scope

**In-scope giả định:** AS-01 đến AS-14, data flows trong sơ đồ, cloud account production, recovery account, admin/privileged paths, build–deploy pipeline, vendor payment integration và logging.

**Out-of-scope cần ghi có căn cứ:** hệ thống không thuộc doanh nghiệp trong sandbox ngoài API boundary, thiết bị cá nhân của người học, network của vendor không được ủy quyền đánh giá. Dù ngoài scope kỹ thuật, **external dependencies vẫn có thể tạo requirements/controls về hợp đồng và shared responsibility**.

### 7.2. Phạm vi theo nhiều chiều

| Dimension | Câu hỏi | Ví dụ |
|---|---|---|
| **Business** | Dịch vụ nào chịu trách nhiệm? | Order service, payment settlement |
| **Technical** | Account, cluster, workload, IAM principal nào? | Prod K8s, recovery account |
| **Data** | Data classification và lifecycle? | Contacts, order records, payment references |
| **Identity** | Human/workload/vendor/break-glass paths? | Support role, payment worker |
| **Temporal** | Kỳ kiểm và mốc cấu hình? | Review window, deploy version |
| **Control** | Requirement nào áp dụng? | MFA chỉ cho required privileged paths |
| **Third-party** | Vendor chịu phần nào? | PSP xử lý payment, merchant vẫn bảo vệ API keys |
| **Geographical** | Region/replication và nghĩa vụ dữ liệu? | Primary + recovery regions |
| **Lifecycle** | New/active/retired assets? | Ephemeral pods và background jobs |

### 7.3. Bài thực hành P1

Từ AS-01..AS-14 hãy tạo ít nhất **một bảng asset × data × trust boundary × owner**, bổ sung ít nhất **5 loại tài sản hoặc đường truy cập còn thiếu**. Ví dụ cần kiểm tra: local admin, service-to-service auth, backup decrypt, vendor support, new cloud account, DNS/TLS và dynamic workload inventories.

**Kết quả yêu cầu:** người đánh giá có thể xác minh vì sao một control được áp cho asset A nhưng không áp cho asset B. Nếu chưa đủ dữ liệu, ghi **APPLICABILITY_PENDING**, không tự loại asset khỏi denominator.

## 8. Mô hình hóa rủi ro và yêu cầu bảo mật

### 8.1. Threat model theo kịch bản thay vì checklist

Đặt câu hỏi theo **assets, entry points, attacker goals, trust boundaries và hậu quả**:

- Một user đã xác thực có thể đọc order của tenant khác?
- Payment Worker nếu bị chiếm quyền có thể lấy tất cả secrets?
- Một commit không được duyệt có thể đưa image vào production?
- Một rule logging bị tắt làm SOC không thấy privileged changes?
- Nếu backup encrypt bằng KMS key mới, recovery account có decrypt được?
- Vendor token nếu không hết hạn có thể truy cập dữ liệu lâu hơn hợp đồng?
- Nếu cluster bị compromise, attacker có thể xóa cả backup recovery?
- Một incident có thể bị ẩn do asset không nằm trong scanner inventory?

### 8.2. Risk register mẫu

| Risk ID | Scenario | Affected assets | Tác động chính | Priority sơ bộ |
|---|---|---|---|---|
| **R-01** | Cross-tenant object access | AS-02, AS-13, AS-04 | Confidentiality | High |
| **R-02** | Excessive workload secret access | AS-03, AS-07 | Confidentiality/integrity | High |
| **R-03** | Privileged path bypasses MFA | AS-06, AS-13 | Privilege compromise | High |
| **R-04** | Untrusted artifact deployment | AS-09, AS-08 | Integrity/supply-chain | High |
| **R-05** | Audit source/parser gap | AS-10, AS-13 | Detection/forensics | High |
| **R-06** | Backup cannot restore/decrypt | AS-11, AS-07, AS-04 | Availability/integrity | Critical for payment |
| **R-07** | Vendor token persists after support | AS-12, AS-03 | Third-party access | High |
| **R-08** | Cloud account outside inventory | AS-14 và cloud scope | Unknown control coverage | Needs validation |
| **R-09** | Network/IaC drift | AS-01, AS-14 | Exposure/trust boundary | High |
| **R-10** | Duplicate/incorrect payment event | AS-03, AS-05, AS-12 | Integrity/business | Critical |
| **R-11** | Vulnerability not remediated | AS-02, AS-08 | Exploit exposure | Context-dependent |
| **R-12** | Security exceptions never expire | AS-06, AS-10, AS-14 | Control governance debt | High |

Đây là **scenarios giả định**, không phải kết luận hệ thống thật đang bị tấn công. Risk rating sơ bộ phải được hiệu chỉnh bằng **likelihood evidence, exposure, controls và BIA**, không chỉ theo severity scan.

### 8.3. Risk scoring không thay thế critical gates

Nếu buộc dùng risk scoring cho workshop, có thể dùng thang **Impact 1–5 × Likelihood 1–5** làm **công cụ thảo luận**, không gọi là xác suất hay thuật toán tiêu chuẩn. Ví dụ R-01 có impact 5, likelihood 3 thì risk indicator = 15/25 theo thang tự định. Cần ghi giả định và control confidence.

Các **critical gates** không được che bằng trung bình: active exploitation, confirmed privileged boundary failure, dữ liệu nhạy cảm bị truy cập trái phép, mất required logging hoặc phục hồi không đáp ứng objective phải được escalated theo policy, dù score thông thường chưa cao.

### 8.4. Security requirements register

| Requirement ID | Mục tiêu/tiêu chí | Loại nguồn | Liên kết rủi ro |
|---|---|---|---|
| **REQ-IAM-01** | Privileged access phải được kiểm soát và MFA ở required paths | Internal policy | R-03 |
| **REQ-AUTHZ-01** | Không cho truy cập object ngoài tenant/assignment | Security requirement | R-01 |
| **REQ-SECRETS-01** | Workloads chỉ truy cập secrets cần thiết | Least-privilege baseline | R-02 |
| **REQ-BUILD-01** | Only authorized, verifiable artifacts deploy production | Release policy | R-04 |
| **REQ-LOG-01** | Required security events có actor, action, resource, outcome | Audit objective | R-05 |
| **REQ-DR-01** | Restore đúng RTO/RPO và dữ liệu nhất quán trong scenario được duyệt | BIA/recovery plan | R-06 |
| **REQ-VENDOR-01** | Vendor access có scope, approval và expiry | Third-party policy | R-07 |
| **REQ-INV-01** | Critical assets/control population được kiểm kê | Asset baseline | R-08 |
| **REQ-NET-01** | Public ingress và network changes qua approved baseline | Cloud policy | R-09 |
| **REQ-DATA-01** | Không nhân đôi/mất trạng thái thanh toán ngoài tolerance đã duyệt | Business integrity | R-10 |
| **REQ-VULN-01** | Lỗ hổng được triage theo rủi ro và retest sau fix | Vulnerability policy | R-11 |
| **REQ-EXC-01** | Exception có authority, scope, finite expiry và review | Risk governance | R-12 |

Mỗi requirement cần lưu **source reference, version, applicability, owner và testable criterion**. Không có dữ liệu applicability cho một nghĩa vụ bên ngoài thì ghi **NEEDS_APPLICABILITY_REVIEW**, không tự khẳng định tổ chức tuân thủ hay không.

### 8.5. Bài thực hành P2

Học viên chọn **ba risk scenarios high/critical**, viết mỗi scenario theo cấu trúc:

> Khi [threat actor hoặc failure] đi qua [entry point/trust boundary], có thể gây [tác động CIA/nghiệp vụ] cho [assets/data]. Điều kiện kiểm soát cần đạt là [requirement], và sẽ được xác minh bằng [test/evidence].

Một threat scenario tốt không chỉ ghi “hack hệ thống”. Phải thể hiện **điểm tin cậy bị vượt, điều kiện cần và hậu quả**.

## 9. Thiết kế control taxonomy và mã định danh

### 9.1. Nguyên tắc đặt ID

Một cấu trúc có thể sử dụng:

- **GOV-xx:** governance, ownership, policy, exception.
- **AST-xx:** asset inventory và control applicability.
- **IAM-xx:** identities, authentication, privilege, credentials.
- **APP-xx:** application/API authorization và logic.
- **DAT-xx:** data protection, encryption, integrity, privacy.
- **INF-xx:** cloud/network/runtime configuration.
- **BLD-xx:** CI/CD, supply chain, artifact trust.
- **LOG-xx:** logging, monitoring, detection.
- **IR-xx:** incident response.
- **RES-xx:** backup/DR, recovery readiness.
- **TPR-xx:** third-party/vendor.
- **VUL-xx:** vulnerability/remediation lifecycle.

Không gắn environment vào **control definition ID** nếu cùng control áp dụng nhiều assets. Thay vào đó tạo **control unit ID** theo control × asset × environment hoặc một scope predicate được quản lý. Ví dụ **IAM-01** là control logic, còn **CU-IAM-01-AS13-PROD** là một instance phải kiểm.

### 9.2. Phân lớp control

| Dimension | Các giá trị gợi ý | Ý nghĩa |
|---|---|---|
| **Type** | Preventive / Detective / Corrective / Recovery / Governance | Vai trò trong risk scenario |
| **Implementation** | Technical / Process / People / Contract | Cách triển khai |
| **Execution** | Automated / Manual / Hybrid | Cách control chạy |
| **Frequency** | Continuous / Per deploy / Daily / Quarterly / Per incident | Khi nào cần có evidence |
| **Scope** | Organization / Cloud account / Service / Workload / Identity / Data class | Population áp dụng |
| **Assurance layer** | Design / Implemented / Effective / Operating | Loại claim đang kiểm |
| **Criticality** | Critical / High / Standard | Review và gating depth |
| **Evidence confidence** | High / Medium / Low / Unknown | Độ chắc của kết quả |
| **Verdict** | PASS / FAIL / INCONCLUSIVE / NOT_TESTED / NOT_APPLICABLE | Kết luận theo scope/time |

Một control có thể là **preventive và detective** trong những khía cạnh khác nhau; không nên ép mọi property thành một giá trị nếu làm mất thông tin. Phân loại phải phục vụ quyết định testing và governance.

### 9.3. Nguyên tắc không trùng lặp

Nếu hai controls có cùng objective và assertion, xem xét hợp nhất definition nhưng giữ các test scopes riêng. Ngược lại, **logging source coverage** và **detection rule effectiveness** không nên bị gộp chỉ vì cùng thuộc nhóm LOG, bởi một collector có thể healthy trong khi rule bị suppress.

### 9.4. Traceability graph

~~~mermaid
flowchart LR
    R["R-01 Risk scenario"] --> Q["REQ-AUTHZ-01"]
    Q --> C["APP-01 Tenant isolation control"]
    C --> U1["CU-APP-01-AS02-PROD"]
    C --> U2["CU-APP-01-AS13-PROD"]
    U1 --> T["T-APP-01 Negative access test"]
    T --> E["EV-APP-01 Test evidence"]
    E --> V["FAIL / PASS / UNKNOWN verdict"]
    V --> F["Finding / remediation / retest"]
    F --> RP["Assurance reporting"]
~~~

Nếu risk không nối tới requirement/control, đó là **risk treatment gap**. Nếu control không có test/evidence, đó là **assurance gap**. Nếu một required asset không có control unit, đó là **population gap**.

## 10. Viết control statement, assertion và acceptance criteria

### 10.1. Mẫu control card

Một control card tối thiểu cần:

- **control_id, title, objective, risk_refs, requirement_refs**.
- **statement:** hành vi hoặc tình trạng cần được thiết lập.
- **scope_rule:** khi nào áp dụng, ngoại lệ applicability hợp lệ.
- **owner_role, implementer_role, assessor_role, approver_role**.
- **control_type, criticality, execution_frequency**.
- **implementation_guidance:** cách triển khai có thể thay đổi nhưng không làm mất objective.
- **assertions:** điều kiện kiểm được.
- **test_method, positive/negative_cases, expected_result**.
- **evidence_contract:** source, timestamp, trust, retention và coverage.
- **response_on_fail, remediation and exception rules**.
- **review_triggers:** khi data/architecture/threat/source đổi.
- **version/last_review/next_review**.

### 10.2. Từ câu mơ hồ thành assertion đo được

| Câu mơ hồ | Control statement có ích | Assertion/test có thể đánh giá |
|---|---|---|
| “Mã hóa dữ liệu.” | Sensitive data trong scope phải có encryption phù hợp | Kiểm KMS/DB/storage effective settings và decrypt tests |
| “Có MFA.” | Required privileged interactive paths enforce MFA | Negative bypass test trên inventory privileged paths |
| “Log đầy đủ.” | Required security events giữ actor/action/resource/outcome và đến SIEM | Synthetic event source→collector→index→alert |
| “CI an toàn.” | Production chỉ triển khai artifacts từ approved pipeline | Verify digest/provenance và admission/reject test |
| “Backup ổn.” | Service khôi phục theo BIA và security objectives | Controlled restore, data reconciliation, RTO/RPO |
| “Đã sửa CVE.” | Runtime units không còn condition bị ảnh hưởng | Installed/runtime version/path retest, affected inventory |
| “Vendor được đánh giá.” | Vendor access và data flows nằm trong approved scope | Token grants/expiry, contract control review |
| “Không quá quyền.” | Actions/resources ngoài business need bị deny | Effective IAM permissions + negative tests |

### 10.3. Ví dụ control card đầy đủ bằng YAML

~~~yaml
control_id: "APP-01"
version: "1.0"
title: "Enforce tenant-level object authorization"
objective: "Prevent cross-tenant access to order resources"
requirement_refs: ["REQ-AUTHZ-01"]
risk_refs: ["R-01"]
scope:
  assets: ["AS-02", "AS-13"]
  environments: ["production"]
  applicability_rule: "All API paths accessing tenant-scoped objects"
type: ["preventive", "detective"]
criticality: "critical"
ownership:
  accountable_role: "order-service-owner"
  implementer_role: "application-engineering"
  assessor_role: "security-assurance"
statement: >
  The service must enforce server-side authorization for each
  tenant-scoped resource, independent of client-supplied tenant IDs.
assertions:
  - id: "APP-01-A1"
    condition: "Authorized tenant user can access only assigned resources"
    method: "approved-positive-and-negative-authz-tests"
    required_result: "PASS"
  - id: "APP-01-A2"
    condition: "Cross-tenant list, detail and export paths are denied"
    method: "role-object-path-matrix-test"
    required_result: "PASS"
  - id: "APP-01-A3"
    condition: "Denied access generates required audit event"
    method: "synthetic-event-to-siem-test"
    required_result: "PASS"
evidence_contract:
  required:
    - "Artifact identity and deployed environment"
    - "Test identity/role and resource matrix"
    - "Positive and negative result with timestamps"
    - "Audit event reference"
  freshness: "after-material-code-or-role-change"
  store: "restricted-evidence-repository"
on_failure:
  priority_rule: "evaluate-critical-authz-boundary"
  immediate_action: "stop-promotion-or-limit-exposure-as-approved"
  retest_required: true
review_triggers:
  - "new-tenant-API"
  - "role-model-change"
  - "authorization-library-upgrade"
~~~

YAML là **mẫu khái niệm**, không phải schema chạy sẵn của một sản phẩm. Control card **chưa phải bằng chứng** đã đạt. Nó chỉ mô tả **cách chứng minh** cần có.

### 10.4. Bài thực hành P3

Viết tối thiểu **12 control cards** đại diện các domain quan trọng; ít nhất 4 controls phải có đủ assertions, negative tests, scope và evidence contract. Với payment integrity và DR nên có **kiểm dữ liệu/khả năng phục hồi**, không chỉ config scan.

## 11. Control library tham khảo để người học phát triển

Bảng sau là **bộ control candidates minh họa**, không phải minimum compliance baseline bắt buộc cho mọi tổ chức. Học viên phải kiểm applicability và làm rõ acceptance criteria theo bối cảnh. Những tên control có thể được điều chỉnh, nhưng **ID phải ổn định và có versioning**.

### 11.1. Governance, inventory và identity

| Control ID | Control statement theo mục tiêu | Scope tham khảo | Test/assertion then chốt | Owner |
|---|---|---|---|---|
| **GOV-01** | Required controls có owner, evidence và review cycle | Toàn hệ thống | Control definitions có authority, role và kiểm soát thay đổi | Security/GRC |
| **GOV-02** | Security exception phải có scope, approver, finite expiry và compensating controls | GRC, pipeline, IAM, SOC | Không còn ACTIVE exception thiếu expiry hoặc approver | Risk Owner |
| **AST-01** | Critical assets, identities và data paths được kiểm kê đầy đủ | Cloud, K8s, IAM, vendors | Reconcile inventory với cloud/runtime APIs, unknown riêng | Platform |
| **AST-02** | Required control population được cập nhật khi asset phát sinh/retire | CI/CD, cloud account events | New cloud account đưa vào baseline và test trong hạn | Platform/GRC |
| **IAM-01** | Required privileged interactive paths enforce MFA | AS-06, AS-13 | Positive/negative authn tests trên privileged paths | Identity |
| **IAM-02** | Workload identities dùng least privilege và secrets theo scope | AS-02, AS-03, AS-07 | Deny actions/resources ngoài business requirements | Identity/Platform |
| **IAM-03** | Temporary/vendor privileges có approval, expiry, revoke và audit | AS-06, AS-12, AS-13 | Expired token bị từ chối và không còn session ngoài phép | Identity/Vendor Owner |

**Gợi ý:** IAM-01 và IAM-03 có điểm chung về access, nhưng **một bên là authentication assurance**, bên còn lại là lifecycle và third-party authorization; cần assertions và test riêng.

### 11.2. Application, data và payment integrity

| Control ID | Control statement | Scope | Test/assertion then chốt | Owner |
|---|---|---|---|---|
| **APP-01** | Server-side tenant/object authorization được enforce cho mọi in-scope API path | AS-02, AS-13 | Negative cross-tenant matrix + positive expected access | Application |
| **APP-02** | APIs nhạy cảm có validation, abuse throttling và safe error handling | AS-01, AS-02 | Boundary/abuse tests và sensitive error leakage checks | Application |
| **APP-03** | Changes tới access-sensitive code có security regression tests | API, libraries, release | Negative authz tests chạy trên approved artifact | Application/Security |
| **DAT-01** | Sensitive data được bảo vệ at-rest và in-transit theo yêu cầu | AS-04, AS-05, AS-11 | Effective TLS/storage encryption + key access verification | Data/Security Platform |
| **DAT-02** | Data export, retention và deletion nằm trong approved lifecycle | APIs, backups, vendor | Export scope, retention lifecycle, deletion/restore checks | Data Owner |
| **DAT-03** | Order/payment state transitions bảo toàn integrity, chống duplicate và loss | AS-02..AS-05, AS-12 | Replay/idempotency/reconciliation với business invariants | Payment/Data |
| **DAT-04** | KMS access và key lifecycle đảm bảo decrypt/restore đúng quyền | AS-07, AS-11 | Test decrypt bằng recovery identity, deny unauthorized access | Security Platform |

Một control **DAT-03** thường cần test ở **ứng dụng, broker, database và provider boundary**. Một cấu hình queue “exactly-once enabled” không đủ chứng minh không có duplicate financial side effects.

### 11.3. Infrastructure, supply chain và vulnerability management

| Control ID | Control statement | Scope | Test/assertion then chốt | Owner |
|---|---|---|---|---|
| **INF-01** | Public ingress và egress chỉ đúng approved network policy | AS-01, AS-08, AS-14 | Effective routes/ACL và negative reachability tests | Platform |
| **INF-02** | Kubernetes workloads thực thi required runtime isolation baseline | AS-08 | Pod effective spec/admission policies và deny test | Platform |
| **INF-03** | IaC/config drift và out-of-band changes được nhận biết | AS-14, cloud accounts | Reconcile runtime state vs source, alert trên drift | Platform |
| **BLD-01** | Production chỉ chạy artifacts từ approved build path | AS-09, AS-08 | Verify deployed image digest/provenance, reject untrusted artifact | Developer Platform |
| **BLD-02** | Deployment approvers và CI identities không tự bypass critical gates | AS-09 | Protected environment permission/negative deploy tests | Developer Platform |
| **BLD-03** | Dependency/image vulnerability findings được phát hiện và gắn affected deployments | Registry/runtime | SCA/image scan + actual digest population mapping | Security/Platform |
| **VUL-01** | Confirmed security findings được ưu tiên theo rủi ro và có owner/deadline | Findings toàn chương trình | Sample finding lifecycle và policy triggers | Security/Risk |
| **VUL-02** | Fix phải được retest trên affected runtime trước verified closure | Runtime assets | Post-fix positive/negative/security regression + inventory | Assurance |

### 11.4. Logging, detection, incident response, recovery và third-party

| Control ID | Control statement | Scope | Test/assertion then chốt | Owner |
|---|---|---|---|---|
| **LOG-01** | Required audit events có actor/action/resource/outcome và tới central store | AS-02, AS-06, AS-10, AS-13 | Synthetic event nguồn→collector→SIEM với required fields | SOC/Platform |
| **LOG-02** | Required detection scenarios tạo alert đúng scope/routing | AS-10 | Controlled positive/negative detector tests và suppression checks | SOC |
| **LOG-03** | Thiếu required log source được phát hiện | AS-10 và source inventory | Source silence/heartbeat + missing-source alert | SOC |
| **IR-01** | Incident response playbook có người trực, quyền, evidence và test | SOC, Service, IR | Tabletop và controlled incident scenario | IR |
| **RES-01** | Backup có thể restore với dữ liệu nhất quán và security gates | AS-04, AS-07, AS-11 | Restore rehearsal, KMS decrypt, data reconciliation | Resilience/Data |
| **RES-02** | DR plan đạt BIA recovery objectives trong scenario kiểm | Order/Payment Recovery | Timed recovery và RTO/RPO/functional/security acceptance | Resilience |
| **RES-03** | Release/rollback plan không tái tạo security gap hoặc phá data state | Change/Release | Compatibility tests, artifact trust, rollback rehearsal | Release/Platform |
| **TPR-01** | Vendor access/data-flow được kiểm và offboard theo scope | AS-12, support identities | Contract scope, token rights, expiry/revoke, logging | Vendor Owner |
| **TPR-02** | Shared responsibility và third-party evidence được đánh giá đúng phạm vi/kỳ | Cloud/PSP | Review scope, exceptions, customer-side controls | Vendor/GRC |

Tổng cộng **31 control candidates** trong ví dụ. Dự án minimum viable framework **không bắt buộc triển khai hết 31 ngay**; học viên phải ưu tiên các controls được chọn theo mục tiêu và rủi ro, nhưng phải ghi rõ **những yêu cầu và rủi ro chưa được bao phủ**, không lén coi out-of-scope là PASS.

### 11.5. Một số control-to-risk mappings minh họa

| Risk | Primary/mitigating controls | Evidence trọng yếu |
|---|---|---|
| **R-01 Cross-tenant access** | APP-01, APP-03, LOG-01 | Negative authz matrix, audit events |
| **R-02 Excess secrets** | IAM-02, DAT-04, LOG-01 | Effective IAM deny tests, KMS audit |
| **R-03 Admin MFA bypass** | IAM-01, IAM-03, GOV-02 | Privileged path inventory, MFA bypass tests |
| **R-04 Artifact trust** | BLD-01, BLD-02, VUL-02 | Deployed digest/provenance, admission test |
| **R-05 Logging blind spot** | LOG-01, LOG-02, LOG-03 | Synthetic source→alert and silence tests |
| **R-06 Restore failure** | DAT-04, RES-01, RES-02 | KMS decrypt, restore data, RTO/RPO |
| **R-07 Vendor token** | IAM-03, TPR-01 | Token expiry/revocation, scope review |
| **R-08 Inventory omission** | AST-01, AST-02 | Runtime inventory and enrollment coverage |
| **R-09 Cloud drift** | INF-01, INF-03 | Effective ingress, drift alerts |
| **R-10 Duplicate payment** | DAT-03, LOG-01, IR-01 | Replay/idempotency + reconciliation |
| **R-11 Unfixed vulnerabilities** | BLD-03, VUL-01, VUL-02 | Affected deployments, policy, retest |
| **R-12 Permanent exceptions** | GOV-02, IAM-03, INF-03 | Exception register, expiry and effective-state checks |

Một risk có thể cần **nhiều controls ở các lớp phòng ngừa, phát hiện và phục hồi**; không nên cho rằng một control đơn lẻ luôn xử lý đủ risk.

## 12. Tạo Control Assurance Matrix (CAM)

### 12.1. Tại sao cần control unit?

Một control definition như **LOG-01** có thể áp dụng cho bốn nguồn: Gateway, Order API, Admin Portal và IAM. Nếu chỉ lưu trạng thái LOG-01 = PASS dựa trên một log source, những nguồn khác bị che. Cần biểu diễn **control instance/unit** theo affected population.

Ví dụ:

| Control unit ID | Control | Asset | Expected unit | Assessor | Status |
|---|---|---|---|---|---|
| CU-LOG01-AS01-PROD | LOG-01 | API Gateway | Required event classes | SOC | NOT_TESTED |
| CU-LOG01-AS02-PROD | LOG-01 | Order API | Order access events | SOC | PASS_WITH_SCOPE |
| CU-LOG01-AS13-PROD | LOG-01 | Admin Portal | Privileged admin events | SOC | FAIL |
| CU-LOG01-AS06-PROD | LOG-01 | IAM | Privilege change events | SOC | INCONCLUSIVE |
| CU-APP01-AS02-PROD | APP-01 | Order API | Tenant access boundary | App Security | NOT_TESTED |
| CU-RES01-AS04-PROD | RES-01 | Database | Recoverable data/keys | Resilience | INCONCLUSIVE |
| CU-BLD01-AS08-PROD | BLD-01 | K8s workloads | Approved deployed image | Platform | NEEDS_VALIDATION |

Trong **verdict taxonomy cuối**, nên dùng PASS/FAIL/INCONCLUSIVE/NOT_TESTED/NOT_APPLICABLE; **NEEDS_VALIDATION** có thể là workflow trạng thái triage riêng. Nếu một unit cần kết luận lúc báo cáo, ánh xạ NEEDS_VALIDATION sang **INCONCLUSIVE** hoặc **NOT_TESTED** theo việc có test chưa đủ dữ liệu hay chưa, không coi đó là PASS.

### 12.2. Tách applicability khỏi effectiveness

Với một control unit cần ghi hai câu hỏi:

1. **Applicable?** Có thuộc phạm vi requirement/control không? Nếu NOT_APPLICABLE, chứng minh bằng asset/data/architecture evidence và approval phù hợp.
2. **Effective?** Nếu applicable, control assertion đạt trong kỳ và scope đã kiểm không?

Ví dụ một service không có đường privileged interactive access có thể **NOT_APPLICABLE** với control về MFA cho human admin paths, nhưng IAM của workload vẫn phải được kiểm theo control khác. Không dùng N/A vì “scanner không thấy user”.

### 12.3. Ma trận assessment

| Assessment ID | Unit | Assertion | Evidence | Verdict | Follow-up |
|---|---|---|---|---|---|
| A-001 | CU-APP01-AS02-PROD | APP-01-A2 | EV-001 | NOT_TESTED | Lập negative test matrix |
| A-002 | CU-IAM01-AS13-PROD | IAM-01-A1 | EV-002 | FAIL | F-01: sửa local MFA |
| A-003 | CU-IAM02-AS03-PROD | IAM-02-A1 | EV-003 | FAIL | F-02: giảm wildcard |
| A-004 | CU-LOG01-AS13-PROD | LOG-01-A1 | EV-004 | FAIL | F-05: actor field |
| A-005 | CU-RES01-AS04-PROD | RES-01-A1 | EV-005 | INCONCLUSIVE | Restore rehearsal |
| A-006 | CU-BLD01-AS08-PROD | BLD-01-A1 | EV-006 | INCONCLUSIVE | Pin digest + provenance |
| A-007 | CU-TPR01-AS12-PROD | TPR-01-A1 | EV-007 | FAIL | F-08: vendor token expiry |

Bảng là dữ liệu **giả định**. Nên có **assessment_time, evaluator, assertion_version, evidence provenance, scope và limitations** trong hồ sơ thật.

## 13. Thiết kế assertion-driven test catalog

### 13.1. Cấu trúc một test case

Một test spec nên có:

- **test_id và version**.
- **control_id, assertion_id, requirement_id**.
- **affected control population/units**.
- **preconditions và môi trường**.
- **test identities/test data** được ủy quyền.
- **positive test** chứng minh hành vi hợp lệ.
- **negative test** chứng minh hành vi trái quyền/điều kiện bị chặn.
- **expected results** rõ điều kiện PASS/FAIL.
- **observed results** kèm timestamps/IDs.
- **scope, sampling method và limitations**.
- **safety/rollback safeguards**, nhất là khi test production.
- **evidence references và reviewer role**.

Không phải control nào cũng có positive/negative test theo cùng cấu trúc: governance control có thể dùng evidence review, population reconciliation và interview được đối chiếu; DR control cần restore exercise, thời gian, data integrity và security acceptance.

### 13.2. Test matrix cho tenant isolation

| Test ID | Actor | Resource | Operation | Expected |
|---|---|---|---|---|
| T-AUTHZ-01 | Customer tenant A | Order owned A | GET | ALLOW |
| T-AUTHZ-02 | Customer tenant A | Order owned B | GET | DENY |
| T-AUTHZ-03 | Customer tenant A | Order owned B | UPDATE | DENY |
| T-AUTHZ-04 | Merchant tenant A | Orders tenant A per assignment | LIST | ALLOW restricted |
| T-AUTHZ-05 | Merchant tenant A | Orders tenant B | EXPORT | DENY |
| T-AUTHZ-06 | Support with approved ticket scope | Authorized order | GET | ALLOW within scope/time |
| T-AUTHZ-07 | Support after approval expiry | Formerly approved order | GET | DENY |
| T-AUTHZ-08 | Unauthenticated caller | Any private order | GET | DENY |

Điều kiện **DENY** cần xác minh ở server-side policy và result, không chỉ UI. Test bổ sung cho list/detail/export/cache/batch jobs, privilege transitions và stale sessions.

### 13.3. Test matrix cho privileged IAM

| Test ID | Scenario | Expected condition |
|---|---|---|
| T-IAM-01 | Human admin qua IdP | Required MFA enforced |
| T-IAM-02 | Local admin path nếu được phép | Có control/approved exception; không bypass không quản lý |
| T-IAM-03 | Payment Worker đọc secret của chính service | Allow theo business need |
| T-IAM-04 | Payment Worker đọc secret ngoài scope | Deny |
| T-IAM-05 | Vendor token quá hạn | Deny và có revoke evidence |
| T-IAM-06 | Break-glass use | Có audit/owner/expiry và kiểm sau kỳ |
| T-IAM-07 | Grant wildcard từ IaC change | Policy gate phát hiện và xử lý theo authority |
| T-IAM-08 | Change privileged role | Audit event có actor/action/resource/outcome |

### 13.4. Test matrix cho backup/DR

| Test ID | Scenario | PASS khi |
|---|---|---|
| T-RES-01 | Backup catalog và snapshot freshness | Required backup object còn theo policy, retention đúng |
| T-RES-02 | Restore bằng recovery identity | KMS decrypt và data load thành công với least privilege |
| T-RES-03 | App boot sau restore | Service thực thi core workflows |
| T-RES-04 | Data integrity | Business invariants/reconciliation đạt |
| T-RES-05 | Recovery time | Measured RTO từ disruption đến accepted recovery đạt mục tiêu |
| T-RES-06 | Recovery point | Last consistent recovery point đáp ứng RPO |
| T-RES-07 | Audit after failover | Required events và alerts đi đúng luồng |
| T-RES-08 | Unauthorized recovery principal | Deny secret/backup decrypt |
| T-RES-09 | Compromised primary credentials | Recovery domain vẫn có boundary đúng theo scenario |
| T-RES-10 | Failback | State/role/data không lệch ngoài tolerance đã duyệt |

Các tests liên quan fault/DR phải chạy trên môi trường an toàn được phép và có go/no-go. **Backup job SUCCESS không được tính như Restore PASS.**

### 13.5. Ví dụ test spec YAML

~~~yaml
test_id: "T-APP-01-002"
version: "1.0"
control_id: "APP-01"
assertion_id: "APP-01-A2"
scope:
  service: "Order API"
  environment: "pre-production"
  tenant_test_ids: ["tenant-A", "tenant-B"]
preconditions:
  - "Both tenants have synthetic orders"
  - "Token scopes are known and timebound"
steps:
  - "Authenticate as tenant-A user"
  - "Request tenant-B order detail through approved API"
  - "Check response and relevant audit event"
expected:
  authorization: "DENY"
  data_exposure: "NONE"
  audit_event: "ORDER_ACCESS_DENIED"
safety:
  - "Do not use real customer data"
  - "Run against approved test environment only"
evidence:
  required:
    - "Test run identity and timestamp"
    - "API version/deployed artifact"
    - "Request/response metadata without sensitive content"
    - "Audit event ID"
verdict_rule:
  pass: "Denied with no cross-tenant data exposure and audit observed"
  fail: "Cross-tenant access or required audit condition fails"
  inconclusive: "Cannot verify environment/identity/log source"
~~~

Khi thực hiện thực tế, phải liên kết evidence với source run và hash/metadata phù hợp, không chỉ điền trường expected.

## 14. Evidence architecture và evidence contract

### 14.1. Những yêu cầu đối với evidence

Evidence hữu dụng phải:

1. **Relevant:** gắn đúng assertion, risk, asset và kỳ.
2. **Sufficient:** bao phủ đủ population và kịch bản theo test plan.
3. **Reliable:** source/method có độ tin cậy, identity và quyền hợp lệ.
4. **Fresh:** thu sau thay đổi material hoặc trong review period.
5. **Reproducible/auditable:** có thể kiểm phiên bản và cách sinh.
6. **Protected:** ACL, integrity, retention và audit access phù hợp.
7. **Limited:** ghi rõ assumptions và cases chưa kiểm.
8. **Privacy-aware:** không đưa secrets hoặc customer content thô vào dashboard rộng.
9. **Comparable:** metric versions và verdict taxonomy nhất quán.
10. **Traceable:** evidence ID nối control unit và assessment ID.

### 14.2. Dữ liệu bằng chứng đi qua những lớp nào?

~~~mermaid
flowchart TD
    SRC["Source: cloud, IAM, CI, SIEM, tests, DR"] --> COL["Collector / approved test harness"]
    COL --> NORM["Normalization + provenance metadata"]
    NORM --> QC{"Quality checks"}
    QC -- "Missing / stale / wrong scope" --> GAP["Evidence gap / INCONCLUSIVE"]
    QC -- "Valid" --> REPO["Restricted evidence register/store"]
    REPO --> ASS["Assertion evaluation per control unit"]
    ASS --> VER{"PASS / FAIL / unknown"}
    VER --> F["Finding / exception / remediation"]
    VER --> R["KPI + assurance report"]
    GAP --> F
    F --> RET["Retest with new evidence"]
    RET --> ASS
~~~

Một evidence store bảo vệ file không tự chứng minh nội dung source đầy đủ. Cần quality checks như **last-seen event, missing assets, time skew, duplicate events, parser field loss, version mismatch và source silence**.

### 14.3. Ví dụ evidence manifest

~~~yaml
evidence_id: "EV-LOG-2026-021"
assessment_id: "A-LOG-2026-011"
control_unit_id: "CU-LOG01-AS13-PROD"
assertion_id: "LOG-01-A1"
source:
  system: "synthetic-admin-portal"
  source_event_id: "evt-test-0042"
  collector: "approved-log-test-harness"
collected_at: "2026-11-28T09:00:00Z"
artifact:
  location: "restricted-assurance-store/EV-LOG-2026-021"
  format: "event-trace"
  integrity_reference: "stored-with-authorized-evidence-controls"
scope:
  environment: "training-simulation"
  event_class: "ADMIN_PERMISSION_CHANGE"
test:
  version: "log-e2e-v1"
  source_event_generated: true
  siem_event_seen: true
  actor_field_present: false
  alert_observed: false
result: "FAIL"
review:
  reviewer_role: "security-assurance"
  confidence: "HIGH_WITHIN_TEST_SCOPE"
limitations:
  - "Only synthetic event for one event class"
  - "No claim about production tenant data"
~~~

Ở ví dụ này, log đã tới SIEM nhưng thiếu actor field, nên assertion về **event fidelity** là FAIL; không nên báo logging PASS dựa vào việc có dòng log.

### 14.4. Chất lượng evidence và bằng chứng giả định

Trong workshop:

- Học viên có thể tự tạo event IDs, test inputs và YAML reports.
- Phải gắn nhãn **SYNTHETIC / TRAINING_ONLY**.
- Không giả vờ đây là log lấy từ production.
- Đừng ghi literal passwords, private keys hoặc thanh toán thật.
- Không tạo kết luận “certified” hoặc “audit passed” từ dữ liệu mô phỏng.
- Nếu một bài test chưa chạy, tạo **test plan** và ghi **NOT_TESTED**, không tự thêm kết quả PASS.

### 14.5. Mẫu evidence quality score phi tiêu chuẩn

Để thảo luận, có thể đánh giá **five checks**: source authenticity, scope match, freshness, population completeness và method suitability. Nếu thiếu bất kỳ thành phần critical nào thì verdict **INCONCLUSIVE** ngay cả khi file tồn tại. Một numeric evidence score có thể hỗ trợ triage nhưng **không phải một xác suất tính đúng của control**; không dùng để biến evidence thiếu thành PASS.

## 15. Quy tắc assurance verdict và coverage

### 15.1. Taxonomy chuẩn hóa trong dự án

| Verdict | Điều kiện | Báo cáo |
|---|---|---|
| **PASS_WITH_SCOPE** | Required assertions được test và đạt trong scope/time đã ghi | PASS và limitations, không suy rộng |
| **FAIL** | Có bằng chứng assertion không đạt | Finding, risk và corrective action |
| **INCONCLUSIVE** | Evidence không đủ, sai source, stale, scope mismatch hoặc conflict | Evidence gap, cần điều tra/retest |
| **NOT_TESTED** | Unit applicable nhưng chưa kiểm | Chưa được xác minh, không PASS |
| **NOT_APPLICABLE** | Applicability được đánh giá hợp lệ và có evidence | Loại khỏi applicable denominator theo policy |
| **ACCEPTED_RISK** | Governance disposition có thẩm quyền và hạn | **Không phải control verdict**; giữ verdict gốc |

Ví dụ một exception MFA được phê duyệt: primary control **FAIL**, risk disposition **ACCEPTED_RISK**, exception expiry còn hiệu lực. Không gộp làm PASS.

### 15.2. Tính coverage đúng population

Giả định có **50 applicable control units** do inventory độc lập xác định:

- 32 units PASS.
- 7 units FAIL.
- 6 units INCONCLUSIVE.
- 5 units NOT_TESTED.

\[
\text{Verified Control Coverage}=\frac{32}{50}\times100\% =64\%
\]

Nếu 3/7 FAIL được chấp nhận rủi ro có hạn, coverage vẫn **64%**, không được báo 70% đã đạt. Có thể báo thêm **3 applicable gaps currently risk-accepted**, nhưng điều đó khác câu hỏi controls có effective hay không.

### 15.3. N/A và coverage reporting

Giả sử inventory ghi 55 candidate units, 5 được đánh **NOT_APPLICABLE** có evidence, còn 50 applicable. Denominator cho **verified applicable coverage** là 50; đồng thời nên báo **5 N/A decisions** với scope/rationale, để assessor có thể kiểm việc giảm mẫu số có hợp lệ không.

Nếu chưa biết applicability của 4 assets, không nên tự loại chúng thành N/A. Có thể dùng **candidate population coverage** và **applicability completeness** song song để lộ unknowns.

### 15.4. Aggregate verdict khi control có nhiều units

Với control LOG-01 áp cho 4 critical sources:

| Source | Verdict |
|---|---|
| Order API | PASS |
| Admin Portal | FAIL |
| IAM | INCONCLUSIVE |
| API Gateway | NOT_TESTED |

Không báo **LOG-01 PASS**. Có thể ghi **control overall = NOT_FULLY_VERIFIED** và chi tiết 1 PASS, 1 FAIL, 1 INCONCLUSIVE, 1 NOT_TESTED, với **critical FAIL highlighted**.

Một điểm trung bình không được che critical source failure. Cần có **aggregation rule được phê duyệt** và giải thích control objective có yêu cầu tất cả source hay một threshold nào.

## 16. Gắn control framework vào CI/CD, IaC và runtime

### 16.1. Ba lớp kiểm

**Design-time:** security requirements, threat modeling, architecture review, control applicability, security testing strategy.

**Build/release-time:** SCA, image scanning, code tests, IaC policy checks, artifact trust/provenance, branch/approval protections.

**Runtime/operational:** effective IAM/ingress, deployed digest, synthetic logging/detection, backup restore, vendor access, drift monitoring, incident response.

Một rule ở build time có thể không còn phản ánh runtime nếu có console changes, mutable tags, expired secrets, skipped scans hoặc chưa onboard assets.

### 16.2. Mapping controls vào release gates

| Release gate | Controls | Evidence |
|---|---|---|
| **G-IDENTITY** | IAM-01, IAM-02, IAM-03 | Effective policy, negative access cases, account coverage |
| **G-APP** | APP-01, APP-02, APP-03 | Authz matrix, API regression, abuse-case test |
| **G-BUILD** | BLD-01, BLD-02, BLD-03 | Provenance/digest, pipeline approval, scan |
| **G-NETWORK** | INF-01, INF-02, INF-03 | IaC plan, admission deny test, runtime state |
| **G-DATA** | DAT-01, DAT-02, DAT-03 | Encryption, tenant boundaries, transaction tests |
| **G-LOG** | LOG-01, LOG-02, LOG-03 | Event fidelity, alert route, source silence |
| **G-RECOVERY** | DAT-04, RES-01, RES-02, RES-03 | KMS/restore, data reconciliation, rollback readiness |
| **G-GOVERNANCE** | GOV-01, GOV-02, VUL-01, VUL-02 | Control owners, exceptions, remediation/retest |
| **G-THIRDPARTY** | TPR-01, TPR-02 | Vendor scope, tokens/expiry, shared-responsibility review |

Nếu một release không tác động một control, có thể kế thừa evidence phù hợp **chỉ nếu không có material change** và kỳ hiệu lực còn phù hợp. Không đánh lại mọi thứ máy móc, nhưng cũng không tự coi controls unaffected nếu release làm đổi underlying dependency.

### 16.3. Pipeline pseudocode

~~~yaml
security_assurance_pipeline:
  context:
    required:
      - release_id
      - approved_artifact_digest
      - service_owner
      - affected_control_units
      - assessment_period
  pre_deploy:
    - gate: "G-APP"
      tests: ["tenant-negative-authorization", "API-security-regression"]
    - gate: "G-BUILD"
      tests: ["artifact-provenance", "image-policy"]
    - gate: "G-NETWORK"
      tests: ["IaC-policy", "ingress-effective-plan"]
    - gate: "G-GOVERNANCE"
      tests: ["exception-validity", "critical-finding-approval"]
  post_deploy:
    - gate: "G-IDENTITY"
      tests: ["effective-workload-IAM"]
    - gate: "G-LOG"
      tests: ["synthetic-source-to-alert"]
    - gate: "G-RECOVERY"
      tests: ["recovery-impact-check-when-relevant"]
  decision:
    critical_fail: "BLOCK_OR_ESCALATE_UNDER_APPROVED_POLICY"
    critical_inconclusive: "HOLD_OR_REQUIRE_EXPLICIT_DECISION"
    pass: "ALLOW_WITH_SCOPE_AND_POSTDEPLOY_VERIFICATION"
  evidence:
    preserve_versions: true
    source_of_truth: "restricted-evidence-register"
~~~

Đây là **pseudocode định hướng**, không phải GitHub Actions/GitLab/Jenkins runnable. Khi chuyển sang công cụ thật phải thiết lập quyền, secret handling, policy semantics, protected environments và bảo đảm **artifact được review đúng artifact deploy**.

### 16.4. Đừng biến automation thành self-approval

Một requester không nên có thể tắt security tests, đổi evidence refs, sửa policy gate và tự deploy production ngoài guardrails. Với critical controls cần bảo vệ:

- Branch/environment protections.
- Trusted CI runners và least-privilege tokens.
- Định danh chính xác workflow/config version.
- Evidence provenance/trust.
- Independent review hoặc approved automation policy.
- Audit trail cho emergency override.
- Runtime drift/unauthorized change monitoring.

Một pipeline “xanh” khi các checks bị tắt là **compliance theater**, không phải assurance.

## 17. Gap analysis và remediation planning

### 17.1. Phân biệt bốn loại gap

- **Design gap:** requirement không có control hoặc control không bảo vệ threat scenario.
- **Implementation gap:** control đã định nghĩa nhưng chưa triển khai/tắt/misconfigured.
- **Operating gap:** control có triển khai nhưng không hoạt động đúng hoặc không bền vững.
- **Evidence gap:** có thể control đang hoạt động nhưng thiếu bằng chứng đủ tin cậy để kết luận.

Ví dụ **F-03 chỉ có happy-path authz test** là evidence/design-of-test gap, **không tự xác nhận cross-tenant access đang xảy ra**. Một trường actor thiếu trong event được quan sát là implementation/operating gap trong scope đã test.

### 17.2. Tạo finding record có căn cứ

~~~yaml
finding_id: "F-05"
control_id: "LOG-01"
control_unit_id: "CU-LOG01-AS13-PROD"
criterion: "Required admin events contain actor/action/resource/outcome"
condition: "Observed synthetic admin change event lacks actor field"
source_evidence_refs: ["EV-LOG-2026-021"]
confidence: "HIGH_WITHIN_TEST_SCOPE"
scope:
  service: "Admin Portal"
  environment: "training-simulation"
  event_class: "ADMIN_PERMISSION_CHANGE"
risk:
  scenario: "Delayed detection and weak attribution of privileged changes"
  severity: "HIGH_FOR_WORKSHOP"
owner_role: "SOC-and-admin-platform"
immediate_action: "Investigate parser and original event field mapping"
remediation:
  action: "Correct event schema and parser; add synthetic regression"
  due_at: "2026-12-08T00:00:00Z"
retest:
  expected: "Required fields observed end-to-end, alert routing verified"
  evidence_required: ["source-event", "collector-event", "indexed-event"]
state: "OPEN"
~~~

Dữ liệu chỉ là tình huống mẫu. Một finding có thể ở **OPEN**, dù remediation được deploy, cho đến khi retest/closure phù hợp.

### 17.3. Ưu tiên remediation dựa trên rủi ro

Không chỉ dùng CVSS severity hoặc tuổi ticket. Đánh giá:

1. Có active exploitation/incident hoặc critical gate failure không?
2. Business/security impact và data/privilege scope?
3. Internet exposure, exploitability và attack path?
4. Compensating control đã được kiểm hiệu lực?
5. Applicable deadlines và obligations?
6. Lợi ích của root-cause fix, affected population?
7. Rủi ro thay đổi, rollback và dependency?
8. Mức bất định cần validation trước khi quyết định?

Với những findings chưa có evidence đủ, tạo **time-boxed validation task**; không tự gán low risk.

### 17.4. Remediation roadmap minh họa

| Workstream | Risk/finding | Immediate action | Permanent correction | Retest |
|---|---|---|---|---|
| Privileged access | F-01 | Hạn chế local admin theo policy | Enforce MFA/JIT, review all paths | Negative bypass + audit |
| Secrets least privilege | F-02 | Giảm wildcard scope có kiểm soát | Service identity design/IaC | Effective deny tests |
| API tenant boundary | F-03 | Không promotion khi coverage thiếu ở critical path | Authz matrix và regression gate | Positive/negative tests |
| Data recovery | F-04 | Review BIA và recovery exposure | Restore rehearsal với KMS đúng role | RTO/RPO, integrity/security |
| Logging | F-05 | Khôi phục actor field hoặc alternate audit path | Parser/schema fix + synthetic tests | Source→SIEM/alert |
| Artifact trust | F-06 | Xác minh digest hiện tại | Immutable references, admission gate | Deployed digest/provenance |
| Asset inventory | F-07 | Thu onboard inventory source | Cloud account enrollment automation | Required control population |
| Vendor access | F-08 | Giảm token scope và monitor | Expiring tokens/JIT/vendor offboard | Token revocation/deny |
| Detection | F-09 | Kiểm impact của suppression | Tune rule + expiry & regression tests | Detection positive/negative |
| Recovery keys | F-10 | Kiểm key access scope | Rework KMS recovery policy | Decrypt restore and deny |
| Pipeline override | F-11 | Truy override history và artifact | Governed emergency gate + audit | Policy negative test |
| Network drift | F-12 | Xác định effective ingress | Reconcile console changes into IaC | Runtime config/route test |

Roadmap thực tế phải có owners, due dates, risk acceptance nếu cho phép, dependencies, cost/effort và milestones. Bảng trên là **gợi ý action**, không chứng minh bất kỳ fix nào đã được thực hiện.

## 18. Quản lý risk exceptions có hạn

### 18.1. Ngoại lệ không đổi FAIL thành PASS

Một control như IAM-01 có thể không đạt vì legacy admin. Một risk owner có thể cho phép dùng tạm trong phạm vi nhỏ nếu chính sách cho phép và có controls bù trừ. Nhưng phải ghi:

- **Primary control verdict:** FAIL.
- **Exception decision:** APPROVED_ACTIVE trong scope/thời hạn, không phải control PASS.
- **Compensating controls:** có tests, evidence và giám sát riêng.
- **Residual risk:** rationale, authority và review triggers.
- **Remediation:** owner, milestones, deadline và retest.
- **Expiry:** finite timestamp, không tự động renew.
- **Closure:** primary control PASS và bypass đã được thu hồi/verify.

### 18.2. Exception record ví dụ

~~~yaml
exception_id: "EX-IAM-2026-003"
linked_finding: "F-01"
control_id: "IAM-01"
scope:
  asset: "AS-13"
  environment: "production"
  principal: "temporary-admin-example"
reason: "Legacy admin integration pending migration"
risk:
  impact: "HIGH"
  residual_risk: "HIGH_WITH_RESTRICTED_ACCESS"
compensating_controls:
  - id: "network-restriction"
    evidence_ref: "EV-MIT-001"
    verdict: "PASS_WITH_SCOPE"
  - id: "privileged-session-audit"
    evidence_ref: "EV-MIT-002"
    verdict: "PASS_WITH_SCOPE"
approval:
  status: "PENDING"
  approver_role: "authorized-risk-owner"
  effective_from: null
  expires_at: null
remediation:
  owner_role: "identity-platform"
  plan: "Migrate to supported MFA path"
  due_at: "2026-12-12T00:00:00Z"
status: "NOT_ACTIVE_NOT_AUTHORIZED"
~~~

Mẫu cố ý **chưa được approve**. Một bản ghi thiếu expiry và approval không được vận hành như ngoại lệ hợp lệ; học viên phải mô phỏng phê duyệt mới có finite dates hoặc chỉ ghi PENDING. Không bịa chữ ký của risk owner.

### 18.3. Theo dõi drift và renewal

Review sớm khi:

- Asset chuyển environment hoặc nhận dữ liệu nhạy cảm hơn.
- Privilege hoặc attack surface tăng.
- Vendor/patch/threat intelligence đổi.
- Compensating test FAIL hoặc monitoring mất.
- Expiry đến gần và remediation trễ.
- Owner không còn thẩm quyền.
- Applicable contract/regulation hoặc risk appetite đổi.

Renewal là **risk assessment mới có version**, không phải tự thay expires_at của decision cũ.

## 19. Governance: control owner, assessor và separation of duties

### 19.1. RACI minh họa

R = Responsible (thực hiện); A = Accountable (chịu trách nhiệm cuối); C = Consulted; I = Informed.

| Hoạt động | Business/Risk | Engineering/Platform | Security Assurance | SOC/IR/DR | GRC |
|---|---|---|---|---|---|
| Xác định objective, risk appetite | **A** | C | R | C | C |
| Kiểm kê asset, data, owner | C | **A/R** | C | C | R |
| Xây control library | C | R | **A/R** | C | R |
| Implement IAM/API/CI/cloud controls | I | **A/R** | C | C | I |
| Implement detection/IR/DR controls | I | R | C | **A/R** | I |
| Thiết kế evidence/test methods | C | R | **A/R** | R | C |
| Vận hành test và thu evidence | I | R | **A/R** theo control | R | C |
| Xử lý remediation | **A** cho business impact | **R** | C | C | I |
| Phê duyệt risk acceptance | **A/R** theo authority | C | C | C | C |
| Đóng control finding sau retest | I | C | **A/R** theo quy định | C | C |
| Báo cáo coverage/audit trail | C | C | R | C | **A/R** |

Bảng minh họa cách phân vai. Với critical controls, người triển khai có thể cung cấp evidence nhưng **không mặc định tự cho PASS rồi tự duyệt closure/exception**. Tổ chức nhỏ có thể cần peer-review và automated guardrails, ghi rõ giới hạn về tính độc lập.

### 19.2. Control ownership không chỉ là một email

Mỗi owner assignment cần:

- Role và người/nhóm đại diện còn hiện hành.
- Backup owner khi người chính vắng mặt.
- Quyền thay config, quyền test và quyền phê duyệt.
- Dịch vụ và security requirements thuộc trách nhiệm.
- Khi owner rời nhóm, hệ thống phát review trigger.
- Sự khác nhau giữa **control owner** và **risk acceptance authority**.
- Kênh escalation khi control FAIL hoặc thiếu evidence.
- Mốc review và SLA phản ứng với critical findings.

Nếu bảng controls có owner nhưng nhân sự không còn chịu trách nhiệm, đó là **governance gap** và phải được đưa vào audit finding.

### 19.3. Shared responsibility

Ví dụ:

- Cloud provider bảo vệ lớp cơ sở thuộc trách nhiệm provider, nhưng tổ chức vẫn phải cấu hình IAM, network, keys hoặc logging theo shared-responsibility.
- Vendor payment processor vận hành một phần xử lý thanh toán, nhưng ứng dụng OrderFlow vẫn chịu trách nhiệm xác minh token usage, idempotency, tenant boundaries và webhook authentication của mình.
- SOC có thể sở hữu rule detection nhưng application team phải phát audit event có ngữ nghĩa đúng; thiếu một mắt xích thì **end-to-end control có thể FAIL**.
- KMS platform có thể quản key, nhưng resilience team phải test restore với đúng recovery identity.

Đừng dùng “vendor được chứng nhận” hay “cloud managed” như một verdict PASS cho controls thuộc trách nhiệm khách hàng.

### 19.4. Change control cho framework

Một control cũng có version và cần review khi:

- Control objective hoặc applicability thay đổi.
- New business data/use case được thêm.
- Một detection parser đổi field semantics.
- Test method/scanner version đổi.
- Evidence source bị di chuyển hoặc không còn đáng tin.
- Regulatory/contract requirement được xác minh là thay đổi.
- Threat modeling phát hiện attack path mới.
- Exception được duyệt, hết hạn hoặc thu hồi.
- Asset/platform được decommission hoặc migrate.
- Remediation làm đổi kiểm soát bù trừ.

**Không xóa/ghi đè assessment cũ khi sửa framework**; cần giữ decision và evidence history để biết control thực sự cải thiện hay chỉ đổi tiêu chí.

## 20. KPI và kiểm tra độ bao phủ của framework

### 20.1. Các nhóm chỉ số

| KPI/KCI | Câu hỏi cần trả lời | Denominator cần giữ |
|---|---|---|
| **Inventory completeness** | Bao nhiêu critical assets được inventory? | Independent discovered/expected critical assets |
| **Requirement mapping coverage** | Bao nhiêu applicable requirements có treatment/control? | All applicable requirements, không chỉ đã map |
| **Control ownership coverage** | Bao nhiêu required controls/units có active owner? | All required units |
| **Control test coverage** | Bao nhiêu applicable units đã được test trong kỳ? | All applicable units |
| **Verified control coverage** | Bao nhiêu applicable units thực sự PASS? | All applicable units |
| **Critical assertion pass** | Có critical controls FAIL/unknown không? | Critical required assertions |
| **Evidence freshness** | Bằng chứng có còn đúng kỳ và after-change? | Evidence-required units |
| **Source health/quality** | Mất scanner/log/cloud sources có được phát hiện? | Required sources |
| **Remediation verified closure** | Bao nhiêu findings được sửa và retest? | Findings thuộc cohort, không chỉ tickets đóng |
| **Risk acceptance validity** | Ngoại lệ có authority, scope, expiry và mitigation? | Active/candidate exceptions và bypasses |
| **Review timeliness** | Control owners xem lại đúng hạn? | Controls đến hạn review |
| **DR rehearsal effectiveness** | Những recovery scenarios bắt buộc có PASS? | Required scenario units |
| **Unauthorized config drift** | Actual cloud/IaC khác approved baseline? | All in-scope resources/scope |
| **Control recurrence** | Lỗi cũ tái phát cùng root cause? | Verified closures/cohort có thể theo dõi |

Không cần tính mọi chỉ số từ ngày đầu. Nên bắt đầu bằng **applicability, ownership, test, evidence và verified coverage**, sau đó bổ sung operational metrics khi pipeline có đủ data quality.

### 20.2. Bộ số liệu KPI giả định

Một đợt đánh giá lập inventory được **55 candidate control units**:

- 5 được đánh N/A với evidence và approval hợp lệ.
- 50 applicable units.
- 32 PASS.
- 7 FAIL.
- 6 INCONCLUSIVE.
- 5 NOT_TESTED.

Tính:

\[
\text{Applicable controls} = 55-5=50
\]

\[
\text{Verified coverage}=\frac{32}{50}\times100\%=64\%
\]

\[
\text{Tested with verdict}=\frac{32+7}{50}\times100\%=78\%
\]

Trong ví dụ này, **6 INCONCLUSIVE** không được coi là test có verdict cuối; nếu tổ chức định nghĩa "test attempted", có thể báo riêng 45/50 nhưng cần định nghĩa nhất quán.

Giả định tiếp 3/7 FAIL có risk acceptance còn hiệu lực; vẫn giữ **7 FAIL** và **64% PASS**. Có thể báo risk disposition: **3 of 7 failures accepted under valid conditions**, không dùng thành “compliance 70%”.

### 20.3. Critical fail không được che bằng average

Nếu tổng 90% controls PASS nhưng **IAM-01 critical FAIL** trên một đường admin hoặc **RES-01 critical FAIL** ở database thanh toán, executive report phải nổi bật sự kiện này. Một **risk-weighted score** có thể bổ sung, nhưng không nên loại/ẩn FAIL khi có critical gate.

### 20.4. Thiết kế dashboard đúng đối tượng

**Engineering:** failing assertion, affected asset, change/version, remediation owner.

**SOC/IR:** log source coverage, detector efficacy, alert gaps và incident impact.

**GRC/Assurance:** control mapping, evidence quality, expired exceptions, review deadlines, remediation verified state.

**Business/Risk owner:** top critical risks, residual exposure, required decisions, cost/availability tradeoff.

**Audit:** requirement/control/evidence/decision chain, timestamps, sample population và independence.

Dashboard phải có khả năng drill down **metric → unit → assertion → evidence → verdict → finding → retest**.

## 21. Mẫu Security Assurance Report có giới hạn

### 21.1. Bố cục báo cáo cuối kỳ

Một bản báo cáo nên có:

1. **Executive conclusion** với scope và confidence, không tuyên bố an toàn tuyệt đối.
2. **Scope/period**: services, environments, data và exclusions.
3. **Methodology**: test methods, selection criteria, sampling, evidence sources.
4. **Control population**: candidate, applicable, N/A, unknown applicability.
5. **Results**: PASS/FAIL/INCONCLUSIVE/NOT_TESTED theo control units.
6. **Critical findings** và mức tác động.
7. **Residual risks/exception decisions** đúng thẩm quyền và expiry.
8. **Remediation backlog** với owner, deadline, mitigation và retest.
9. **Source/evidence quality** và giới hạn có thể ảnh hưởng conclusion.
10. **Changes since last assessment**: new assets, controls và versions.
11. **Actions/decisions required** của lãnh đạo/risk owners.
12. **Appendices**: control library, traceability, test và evidence manifest.

### 21.2. Báo cáo minh họa

> **Scope:** một bài đánh giá mô phỏng cho OrderFlow, gồm 50 applicable control units theo inventory giả định. Đây không phải hệ thống thật.
>
> **Overall:** 32 PASS (64%), 7 FAIL, 6 INCONCLUSIVE, 5 NOT_TESTED. 5 N/A units có evidence riêng ngoài mẫu số applicable.
>
> **Critical concerns:** một privileged path thiếu MFA, evidence restore chưa đủ để kết luận BIA recovery readiness và log admin thiếu actor field trong test scope. Những điều kiện này không được che bởi tổng tỷ lệ PASS.
>
> **Risk disposition:** ba FAIL được giả định có valid conditional acceptance; chúng **vẫn là FAIL** ở control effectiveness. Các ngoại lệ khác phải được xem là pending nếu thiếu approval/expiry.
>
> **Limitations:** dữ liệu synthetic, chưa có production evidence thật, nhiều test chỉ áp dụng pre-production, scanner/source inventory có known gaps.
>
> **Recommended action:** ưu tiên hoàn thiện privileged IAM và logging, diễn tập DR với recovery identity, đối soát cloud account missing, triển khai retest và cập nhật control mapping sau fixes.

### 21.3. Không được tuyên bố vượt evidence

Không viết:

- “OrderFlow đạt ISO/IEC 27001” khi đây chỉ là một workshop.
- “Payment service hoàn toàn an toàn” từ một phần controls.
- “Không có breach” vì SIEM không ghi alert.
- “100% compliant” sau khi loại unknown khỏi mẫu số.
- “DR đạt RTO” từ backup job SUCCESS.
- “Controls có hiệu lực liên tục” từ một snapshot config duy nhất.

Nên viết **“verified within assessed scope and period”**, kèm evidence, unmet conditions và limitations.

### 21.4. Assurance case kiểu claim–argument–evidence

~~~mermaid
flowchart TD
    GOAL["Claim: Order API enforces tenant isolation in assessed scope"]
    ARG["Argument: Each in-scope route applies server-side object authorization"]
    P1["Evidence: authorized tenant access test"]
    P2["Evidence: cross-tenant denial tests"]
    P3["Evidence: audit event trace"]
    LIM["Limitation: untested batch/export route"]
    GOAL --> ARG
    ARG --> P1
    ARG --> P2
    ARG --> P3
    ARG --> LIM
~~~

Nếu export route chưa kiểm, claim cần **thu hẹp phạm vi** hoặc verdict INCONCLUSIVE cho toàn objective nếu export là required path. Assurance case làm rõ **lý do kết luận và giới hạn**, không phải công cụ trang trí báo cáo.

## 22. Walkthrough: từ finding tới control, test và closure

### 22.1. Chọn finding F-05 (audit event thiếu actor)

**Bước 1 — Condition:** SIEM sample của Admin Portal có event ADMIN_PERMISSION_CHANGE nhưng thiếu actor field.

**Bước 2 — Risk:** R-05, việc điều tra thay đổi đặc quyền có thể thiếu attribution; các đường hành động critical có thể không được phát hiện đầy đủ.

**Bước 3 — Requirement:** REQ-LOG-01 bắt buộc security events có actor/action/resource/outcome.

**Bước 4 — Control:** LOG-01; control unit **CU-LOG01-AS13-PROD**.

**Bước 5 — Assertion:** synthetic privileged change event phải giữ actor field từ source qua collector đến SIEM; required detector/alert route nếu nằm trong control objective.

**Bước 6 — Test plan:** tạo event an toàn với test principal, truy ID ở source, collector và index; kiểm parser mapping, lag, duplicates và alert route.

**Bước 7 — Evidence:** EV-LOG-2026-021 có actor_field_present=false trong môi trường mô phỏng.

**Bước 8 — Verdict:** FAIL trong test scope; không suy ra mọi log mọi kỳ đều mất actor.

**Bước 9 — Remediation:** sửa source schema/parser, bổ sung synthetic regression test và alert cho field-missing/source-silence, gán SOC/Platform owner.

**Bước 10 — Retest:** sinh event mới, đối soát đầy đủ field, alert, timestamps và affected source inventory.

**Bước 11 — Closure:** chỉ CLOSED_VERIFIED khi required assertions PASS trong scope mới; vẫn giữ kết quả FAIL cũ trong history.

### 22.2. Ví dụ trạng thái trước/sau

| Thuộc tính | Trước remediation | Sau fix được triển khai | Sau retest PASS |
|---|---|---|---|
| Condition | Thiếu actor | Parser sửa | Actor/source-to-SIEM xác minh |
| Evidence | EV-LOG-021 FAIL | Deployment diff, chưa đủ | EV-LOG-022 PASS + trace |
| Finding | OPEN | FIX_IMPLEMENTED | CLOSED_VERIFIED |
| Control verdict | FAIL | Chưa tự chuyển PASS | PASS_WITH_SCOPE |
| Assurance report | Known critical gap | Pending verification | Improvement cùng history/limitations |

Một release ticket **Done** ở cột giữa không đủ để cập nhật control verdict.

### 22.3. Ví dụ khó hơn: F-04 (backup SUCCESS, restore unknown)

**Điều biết:** backup job hoàn tất; object tồn tại.

**Điều chưa biết:** decrypt với recovery role, service startup, data integrity, RTO/RPO và logging sau restore.

**Đánh giá:** condition “restore failure” **chưa được xác nhận**; verdict cho RES-01 **INCONCLUSIVE hoặc NOT_TESTED** tùy method đã thực hiện. Không gọi FAIL chỉ vì thiếu exercise, trừ khi criterion là “restore exercise bắt buộc đã được thực hiện” và evidence chứng minh việc đó chưa xảy ra.

**Action:** chọn recovery scenario đã phê duyệt, tạo synthetic data, thử backup/restore với đúng KMS/IAM permissions, ghi T0/Tservice/Tdata, expected vs actual, business/security gates.

**Kết luận:** Chỉ sau representative restore mới có thể khẳng định control đạt/không đạt trong scenario đã kiểm.

## 23. Case study A: Framework đẹp nhưng bỏ sót cloud account

### 23.1. Tình huống

Nhóm gửi báo cáo **95% controls PASS**, nhưng asset inventory chỉ gồm tài khoản cloud trong IaC. Một cloud account mới được tạo thủ công cho thử nghiệm vendor đã có dữ liệu production và service roles; tài khoản này không được onboard scanner, SIEM và backup.

### 23.2. Sai ở đâu?

- **Population defect:** mẫu số thiếu required assets.
- **Scope/applicability defect:** service mới thay đổi data/control boundaries.
- **Evidence defect:** không có evidence, không phải PASS.
- **Governance defect:** account creation không kích hoạt control onboarding.
- **Reporting defect:** 95% chỉ áp cho known assets, không đại diện toàn production.

### 23.3. Hành động

1. Inventory reconcile từ cloud organization/account enumeration độc lập.
2. Xác nhận owner/data classification và in-scope requirements.
3. Tạo control units mới cho IAM, INF, LOG, DAT, RES, VUL, TPR.
4. Đánh NOT_TESTED/INCONCLUSIVE cho những units chưa có evidence.
5. Ưu tiên containment nếu phát hiện public/privileged boundary đã mở.
6. Thực hiện baseline onboarding và synthetic checks.
7. Điều chỉnh KPI kỳ hiện tại hoặc làm restatement với version và lý do.
8. Thêm guardrail create-account → mandatory baseline/control enrollment.
9. Không sửa lịch sử dashboard thành “trước đây đã PASS”.
10. Dùng post-change review để ngăn account mới bị bỏ sót.

**Bài học:** tính đầy đủ của **population** phải được kiểm độc lập; không thể đánh giá framework chỉ từ số controls mà tool đang nhìn thấy.

## 24. Case study B: Đã accept risk nhưng control vẫn FAIL

### 24.1. Tình huống

Admin Portal có local login không enforce MFA. Risk owner ký một ngoại lệ 14 ngày để vendor hoàn tất migration, có network isolation và session logging đã test. Dashboard GRC cộng exception vào PASS nên hiển thị IAM 100% compliant.

### 24.2. Đánh giá đúng

| Thành phần | Kết quả |
|---|---|
| Primary IAM-01 | **FAIL** trong scope local admin |
| Compensating network control | PASS_WITH_SCOPE nếu đã test đúng path |
| Session monitoring | PASS_WITH_SCOPE nếu event/alert test đạt |
| Risk decision | APPROVED_ACTIVE 14 ngày nếu authority, dates, scope đúng |
| Residual risk | Vẫn tồn tại, phải đánh giá theo service criticality |
| Compliance conclusion | Tùy applicability/obligation; không tự biến thành PASS |
| Remediation | Chưa hoàn tất; cần owner, milestone và retest |
| Reporting | Control FAIL + valid timebound risk acceptance, tách hai chiều |

### 24.3. Sau expiry

Nếu migration vẫn chưa xong và vendor access còn hoạt động:

- Expiry decision không còn hợp lệ.
- Cần review/escalation theo policy và runtime restriction có guardrails.
- Không được auto-renew qua im lặng hoặc backdate.
- Nếu muốn approval mới, risk owner phải xem current scope, threat và mitigation evidence.
- Khi sửa MFA, gỡ bypass và retest các privileged paths trước verified closure.

**Bài học:** risk acceptance là một **governance decision**, không phải bằng chứng implementation effectiveness. Nếu dashboard trộn hai khái niệm, framework mất giá trị assurance.

## 25. Case study C: Backup “thành công” nhưng khôi phục thất bại

### 25.1. Tình huống

Database của dịch vụ Payment có backup object hằng ngày. Sau một key rotation, recovery account chỉ có quyền KMS K1, còn dữ liệu mới mã hóa bằng K2. Bài diễn tập restore không giải mã được dữ liệu mới.

### 25.2. Chuỗi assurance

| Bước | Kết quả |
|---|---|
| Requirement | REQ-DR-01: service recovery theo BIA |
| Risk | R-06: backup không khôi phục được |
| Control | RES-01, DAT-04, RES-02 |
| Backup job | PASS theo job criterion |
| Restore decrypt | **FAIL** trong exercise |
| Business recovery | Không đạt vì data unavailable |
| Security gate | KMS least privilege/restore path cần sửa |
| Finding | Owner Security Platform + Resilience |
| Remediation | KMS grants phù hợp, backup/key lifecycle và restore retest |
| Closure | Đo full RTO/RPO, integrity, IAM/logging trước VERIFIED |

### 25.3. Tránh chữa vội bằng wildcard

Không mở toàn bộ KMS keys cho recovery role chỉ để test PASS. Cần cấp **tối thiểu quyền trên đúng key/data/cross-account path**, xác minh deny test cho unauthorized principals và giữ audit logs. Khi retest đạt, bổ sung release/change gate cho key rotation và DR.

**Bài học:** một control về backup và một control về khả năng phục hồi phải có assertion khác nhau. Backup object còn không chứng minh dữ liệu khôi phục được.

## 26. Bài thực hành tổng hợp: hoàn thiện bộ hồ sơ từ đầu tới cuối

### 26.1. Đề bài giao cho học viên

Với tình huống OrderFlow, hãy chuẩn bị một buổi đánh giá framework như thể bạn trình bày trước hội đồng security assurance. Hội đồng cần có khả năng **truy một claim bất kỳ xuống test và bằng chứng**, đồng thời thấy những kiểm soát chưa đạt.

**Phần A — Context và rủi ro**

1. Xác định in-scope/out-of-scope và những giả định cần xác minh.
2. Liệt kê ít nhất **14 assets đã cho và 5 tài sản/đường truy cập bổ sung**.
3. Vẽ một trust boundary/architecture diagram có Internet, tenant, workload, privileged administration, vendor và recovery domains.
4. Viết 12 risk records, trong đó mỗi risk có impact rationale và owner giả định.
5. Xếp 3 risk cần ưu tiên theo threat/exposure/business impact, ghi các dữ liệu thiếu không thể suy đoán.
6. Ghi ít nhất 12 security requirements có nguồn và applicability.

**Phần B — Thiết kế framework**

7. Chọn và chi tiết hóa **tối thiểu 12 controls** từ các domain khác nhau.
8. Viết **ít nhất 4 control cards đầy đủ**, mỗi card có assertions, unit population, owner, test methods, evidence, frequency và review triggers.
9. Mapping **risk → requirement → control → assertion**, bảo đảm không có high/critical risk không có treatment decision.
10. Tạo control units cho ít nhất **hai controls được áp trên nhiều assets**.
11. Ghi RACI và mô tả cách tách vai trò implementer với assessor/risk approver.
12. Định nghĩa cách version control library khi requirement hoặc scope thay đổi.

**Phần C — Assurance tests/evidence**

13. Tạo **10–15 test cases** gồm ít nhất 5 negative tests.
14. Chuẩn bị evidence manifest, chỉ ra những evidence là **synthetic**.
15. Với dữ liệu F-01..F-12, gán verdict ban đầu theo đúng điều đã chứng minh.
16. Đối soát population từ giả định cloud/service inventory; không loại AS-07/AS-11 chỉ vì scanner không quét chúng.
17. Chọn một control có nhiều units và chứng minh tại sao control overall không PASS khi một unit FAIL hoặc unknown.
18. Thử dựng end-to-end path cho LOG-01, phân biệt collector health với event fidelity.
19. Thử dựng recovery test spec cho RES-01, phân biệt backup job với restore.
20. Tạo một evidence gap record và mô tả thủ tục xác minh tiếp.

**Phần D — Quyết định, khắc phục và báo cáo**

21. Mở ít nhất **4 remediation records** có owner, priority, action, retest và deadline giả định.
22. Tạo một exception request nhưng để **PENDING** nếu không có mô phỏng approval hợp lệ; giải thích finite expiry và compensating tests.
23. Tính KPI với dataset 55/5/50/32/7/6/5; không cộng accepted risk vào PASS.
24. Viết executive summary 250–400 từ, tập trung **risk và decisions required**, không chỉ % coverage.
25. Lập một assurance case cho APP-01 hoặc RES-01 với claim/argument/evidence/limitations.
26. Dựng change trigger: giả định một cloud account mới xuất hiện, xác định controls/units/evidence phải bổ sung.
27. Đề xuất 5 preventive improvements đưa vào CI/CD, IdP, cloud account onboarding, SIEM và DR.
28. Tạo **điều kiện đóng dự án** và danh sách unresolved risks minh bạch.

### 26.2. Sản phẩm demo nên thể hiện luồng thực tế

Người trình bày chọn hai tình huống để demo:

**Demo 1 — APP-01:** từ REQ-AUTHZ-01 → APP-01 card → test case T-AUTHZ-02 (tenant A không được đọc order B) → synthetic request/response → verdict → remediation plan khi test FAIL → retest.

**Demo 2 — RES-01:** từ REQ-DR-01 → RES-01 → recover account/KMS/backup dependency → test restore/decrypt → đo business/security acceptance → PASS/FAIL/unknown theo scope → findings.

Đối với mỗi demo, một reviewer độc lập được quyền yêu cầu: **“Đầu ra nào chứng minh claim, trong môi trường nào và thử lúc nào?”**. Nếu học viên chỉ trả lời “scanner báo xanh” hoặc “đã tick checklist”, demo chưa đạt.

### 26.3. Các câu hỏi khó mà hội đồng có thể hỏi

- Nếu một service không xuất hiện trong CMDB nhưng đang chạy trên cloud, làm sao framework phát hiện và bổ sung?
- Ai phê duyệt risk exception và làm sao biết người đó vẫn có thẩm quyền?
- Evidence test staging có thể dùng cho production trong điều kiện nào?
- Vì sao không dùng điểm trung bình để che IAM/DR critical FAIL?
- Khi scanner biến mất, control có tự chuyển PASS không?
- Vendor SOC report có bao phủ API integration vừa thêm hay không?
- Nếu policy baseline đổi, có phải sửa lại kết quả PASS của kỳ trước?
- Khi một control unit không có evidence do collector lỗi, status nào phù hợp?
- Có nên tự khóa KMS key khi exception expiry nếu khóa phục vụ DR?
- Một fix đã merge nhưng production image digest còn cũ; finding đã đóng chưa?
- Ở đâu lưu proof rằng dữ liệu không bị duplicate sau payment event replay?
- Tại sao recovery time cần tính đến khi **business và security acceptance** đạt?

Câu trả lời đạt phải có **phương pháp, điều kiện, evidence và giới hạn** chứ không chỉ nhắc định nghĩa.

## 27. Câu hỏi tự kiểm tra và hướng giải

**Câu 1.** Chỉ có danh sách 100 security controls từ một tài liệu tham chiếu, đã được coi là control framework đủ assurance chưa?

**Đáp án gợi ý:** Chưa. Thiếu applicability, owner, risk/requirements mapping, tests, evidence, scope, verdict, findings và lifecycle.

**Câu 2.** Một control PASS trên AS-02 nhưng NOT_TESTED trên AS-13. Có được ghi overall PASS cho APP-01 nếu cả hai thuộc population required?

**Đáp án:** Không. Cần aggregate theo tiêu chí và trình bày từng unit; chưa chứng minh full scope.

**Câu 3.** Một vulnerability scanner không thấy account mới. Điều đó chứng minh account đã sạch lỗ hổng không?

**Đáp án:** Không. Đây là inventory/source coverage gap; cần reconcile accounts và bổ sung kiểm soát trước khi kết luận.

**Câu 4.** Một negative authz test ở staging FAIL. Có được kết luận production đã lộ dữ liệu khách hàng không?

**Đáp án:** Không tự động. Có bằng chứng control defect trong staging test, cần xác minh production deployment/path và incident evidence riêng.

**Câu 5.** Backup job SUCCESS, không có restore test. RES-01 có PASS không?

**Đáp án:** Không. Restore có thể bị chặn bởi KMS, quyền, corruption, compatibility hoặc thiếu dữ liệu. Chọn NOT_TESTED/INCONCLUSIVE theo criterion và evidence.

**Câu 6.** Một control được triển khai bằng IaC nhưng runtime policy bị manual override. Dùng bằng chứng nào?

**Đáp án:** IaC giúp chứng minh intended state; cần effective-state export, access/deny tests và drift trail để kiểm runtime.

**Câu 7.** Một owner bấm “accept risk” cho IAM-01 FAIL; có thể đưa nó vào 32 units PASS thành 33 không?

**Đáp án:** Không. Risk disposition riêng với primary control verdict; verified coverage không đổi.

**Câu 8.** Tại sao cần test negative, ngoài test workflow thành công?

**Đáp án:** Nhiều security objectives yêu cầu **hành vi không được phép phải bị chặn**. Happy-path chỉ chứng minh chức năng hợp lệ.

**Câu 9.** Nếu control library dùng IDs ngắn gọn nhưng mỗi lần review đổi lại tất cả IDs, hậu quả gì?

**Đáp án:** Traceability/history bị đứt; findings, evidence và metrics không so sánh được. Giữ stable IDs và versioning.

**Câu 10.** Một test log cho thấy security event tới SIEM nhưng thiếu actor field. LOG-01 PASS không?

**Đáp án:** Không nếu actor là required field; cần sửa source/parser và retest, báo FAIL trong scope đã kiểm.

**Câu 11.** Vendor có báo cáo kiểm toán độc lập. Có thể coi mọi third-party controls PASS?

**Đáp án:** Không. Phải xem report scope, period, exceptions, subservices và controls thuộc trách nhiệm khách hàng, đặc biệt integration mới.

**Câu 12.** Có 55 candidate units, 5 N/A hợp lệ, còn 50 applicable gồm 32 PASS, 7 FAIL, 6 INCONCLUSIVE và 5 NOT_TESTED. Coverage?

**Đáp án:** Verified coverage = 32/50 = **64%**; thử có verdict cuối là 39/50 = **78%** nếu metric định nghĩa như mục 20.

**Câu 13.** Một control card mô tả đúng nhưng evidence đã quá hạn sau key rotation. Verdict?

**Đáp án:** Cần reassessment; có thể INCONCLUSIVE cho claim hiện tại nếu evidence không còn đại diện. Không giữ PASS vô hạn.

**Câu 14.** Vì sao không nên nhân bản hàng trăm controls từ một tiêu chuẩn khi chưa biết hệ thống?

**Đáp án:** Dễ tạo controls trùng, thiếu relevance, không có owner/test, coverage sai và tốn công. Phải dựa trên objectives, risk, applicability và obligations.

**Câu 15.** Sau retest, finding F-05 PASS ở một event class. Có được kết luận mọi logging/detection controls đã hiệu quả trong cả quý?

**Đáp án:** Không. Giới hạn theo event class, source, period và methods; cần ongoing tests và source coverage cho operating effectiveness.

**Câu 16.** Nếu hệ thống mới xử lý dữ liệu nhạy cảm hơn, có cần thay risk/control/test?

**Đáp án:** Có. Data class/criticality là material change, cần risk, applicability, controls, evidence và exception review.

## 28. Rubric chấm dự án 100 điểm

| Tiêu chí | Điểm tối đa | Dấu hiệu đạt chất lượng |
|---|---:|---|
| **1. Scope & asset population** | 12 | In/out scope, owner, data, trust boundaries, missing sources |
| **2. Risk & requirement analysis** | 14 | 12 scenarios, nguồn yêu cầu, applicability, priority rationale |
| **3. Control library design** | 16 | Ít nhất 12 controls, 4 cards đầy đủ, stable IDs, taxonomy |
| **4. Traceability completeness** | 10 | Risk↔requirement↔control↔assertion↔unit nối đúng |
| **5. Test design & negative scenarios** | 12 | Test matrix đủ scope, positive/negative, criteria và safety |
| **6. Evidence quality & verdicts** | 12 | Provenance, confidence, freshness, FAIL/unknown trung thực |
| **7. Gap/remediation & exceptions** | 8 | Owners, priority, due/retest, timebound risk decision |
| **8. Governance & CI/operations** | 6 | RACI, changes, drift, SoD, ownership lifecycle |
| **9. Metrics & reporting** | 6 | Independent denominator, KPI, critical gaps và limitations |
| **10. Presentation & reproducibility** | 4 | Reviewer lần theo một claim xuống evidence và rerun test plan |
| **Tổng** | **100** | Đánh giá cả nội dung lẫn tính kiểm chứng |

### 28.1. Điều kiện không thể được bù bằng điểm cao ở phần khác

Ngay cả khi tổng điểm tốt, dự án **chưa thể coi mô phỏng assurance đạt** nếu:

- Báo cáo tuyên bố toàn hệ thống PASS từ một vài test không đại diện.
- Tự bịa production evidence mà không ghi synthetic.
- Cộng ACCEPTED_RISK vào control PASS.
- Loại missing assets/unknown khỏi mẫu số mà không có applicability evidence.
- Đánh restore PASS chỉ từ backup job log.
- Ghi “đạt chứng nhận/tuân thủ pháp luật” không có cơ sở.
- Thực hiện thử nghiệm xâm nhập hoặc fault injection ngoài quyền cho phép.
- Không thể truy được một critical control từ requirement đến test/evidence.

Những lỗi này làm sai bản chất **evidence-based assurance**, không phải thiếu định dạng tài liệu.

### 28.2. Mức đánh giá gợi ý

- **90–100:** Framework nhất quán, demo có thể kiểm, biết giới hạn và cải tiến có căn cứ.
- **75–89:** Đạt nền tảng, còn một số gaps về coverage/evidence chưa critical.
- **60–74:** Control library có cấu trúc nhưng test/ownership/traceability chưa ổn.
- **Dưới 60:** Danh sách kiểm soát hình thức, thiếu risk/evidence/rationale.

Thang điểm này là **rubric cho lớp học**, không phải maturity assessment quốc tế hay chứng nhận chuyên nghiệp.

## 29. Thực hiện dự án khi không có hệ thống cloud thật

### 29.1. Lab tối thiểu với dữ liệu synthetic

Có thể làm hoàn toàn offline hoặc bằng tài liệu mô phỏng:

1. Vẽ asset/service/trust-boundary diagram.
2. Tạo bảng risk/requirements/controls trong định dạng Markdown/YAML/CSV tùy môi trường học.
3. Đặt 2 tenants A/B và đơn hàng giả định.
4. Xây vài test records thể hiện allow/deny outcomes đã định nghĩa.
5. Mô phỏng IAM policy với một wildcard và một policy hạn quyền.
6. Tạo synthetic log events, một sample thiếu actor.
7. Tạo một image digest record và mô phỏng deploy mismatch.
8. Tạo backup job log và restore rehearsal result riêng.
9. Ghi những điểm chưa thử **NOT_TESTED**, không bịa PASS.
10. Tạo findings/exception pending và báo cáo coverage bằng số liệu giả định.

Nếu có Java/Spring test harness trong môi trường hợp lệ, có thể minh họa object authorization bằng unit/integration tests với dữ liệu giả. Không cần dùng dữ liệu thật hoặc gọi API công khai.

### 29.2. Data fixtures mẫu

~~~yaml
training_only: true
tenants:
  - id: "tenant-A"
    synthetic_orders: ["A-001", "A-002"]
  - id: "tenant-B"
    synthetic_orders: ["B-001"]
identities:
  - id: "customer-A"
    role: "customer"
    tenant: "tenant-A"
  - id: "customer-B"
    role: "customer"
    tenant: "tenant-B"
  - id: "support-A"
    role: "support"
    tenant_scope: ["tenant-A"]
expected_authz:
  - actor: "customer-A"
    resource: "A-001"
    action: "read"
    outcome: "allow"
  - actor: "customer-A"
    resource: "B-001"
    action: "read"
    outcome: "deny"
  - actor: "support-A"
    resource: "B-001"
    action: "export"
    outcome: "deny"
~~~

Fixture này giúp viết test plans và contract tests. **Không được gọi các kết quả expected là observed evidence** nếu chưa chạy một test harness thật. Có thể mô phỏng observed result dưới nhãn TRAINING_SIMULATION, ghi rõ công cụ và cách tạo.

### 29.3. Mô phỏng incident/DR an toàn

Để luyện assurance, không cần phá database thật. Có thể tạo một **restore exercise report synthetic** ghi:

- Input backup snapshot giả định.
- Recovery identity và key policy sample.
- Điều kiện fail KMS decrypt được mô phỏng.
- Expected/observed business recovery times.
- Data integrity assertion và limitations.
- Finding/owner/retest plan.

Nếu có môi trường lab do học viên sở hữu, có thể làm restore trên bản dữ liệu tổng hợp đã được phép; không bắt buộc phải triển khai hạ tầng production.

## 30. Những sai lầm phổ biến và cách phát hiện trong review

| Anti-pattern | Triệu chứng | Cách sửa trong dự án |
|---|---|---|
| **Checkbox framework** | Nhiều controls nhưng không có assertions/evidence | Mỗi control critical phải có test và owner |
| **Framework-first không có risk** | Sao chép standards nhưng thiếu threat scenarios | Bắt đầu từ assets, BIA và applicability |
| **Control ID không ổn định** | Mỗi lần export đổi ID | Stable IDs + versioning và linked references |
| **Trùng lặp không rõ ownership** | Nhiều team cùng đánh một control khác nhau | Chọn accountable owner, giữ unit-specific implementers |
| **Scope không rõ** | “MFA PASS” mà không nêu privileged paths | Applicability predicate và inventory completeness |
| **Nguồn evidence không đáng tin** | Screenshot không biết kỳ, environment, actor | Provenance, timestamp, source/test metadata |
| **Scanner green = security green** | Tool không quét một account mới | Inventory reconciliation và missing-source alert |
| **Positive-only testing** | Chỉ check API 200 | Negative abuse/authz paths |
| **Backup = DR** | Backup có object nhưng không restore | RTO/RPO, decrypt, data/business tests |
| **Accepted risk = PASS** | Dashboard cộng exception vào control coverage | Risk disposition và effectiveness riêng |
| **Missing test = N/A** | Bỏ units thiếu scanner ra khỏi mẫu số | NOT_TESTED/INCONCLUSIVE và validation |
| **No change integration** | Control PASS năm ngoái dùng cho release mới | Review triggers, evidence freshness |
| **Ticket Done = verified closed** | Fix merge, runtime chưa deploy | Retest actual affected population |
| **Evidence hoarding** | Lưu quá nhiều dữ liệu nhạy cảm | Data minimization, ACL, retention |
| **Không phân loại critical gates** | 95% PASS che đường admin đang mở | Highlight critical FAIL và risk owner decision |
| **Không kiểm bù trừ** | WAF rule enabled được coi effective | Controlled negative/positive tests, bypass analysis |
| **Owner trên giấy** | Control owner đã nghỉ việc | Ownership reconciliation và escalation |
| **Không có CAPA** | Cùng IAM drift lặp nhiều lần | Fix provisioning/IaC root cause |
| **Tuyên bố chứng nhận** | Có mapping standards nên gọi compliant | Chỉ kết luận đúng scope/kỳ và requirements |
| **KPI bị gaming** | Loại FAIL/unknown khỏi denominator | Required population độc lập và audit trail |

## 31. Checklist nghiệm thu framework trước khi báo cáo

### 31.1. Context và requirements

- [ ] Project charter có mục tiêu, giả định, service owners, constraints và safety.
- [ ] Inventory bao phủ cloud/IAM/runtime/data/CI/SIEM/DR/vendor trong scope.
- [ ] Có data classification, trust boundaries và business criticality/BIA.
- [ ] Các assets/paths chưa rõ được ghi UNKNOWN, không tự N/A.
- [ ] Risk register có credible scenarios, impact và evidence assumptions.
- [ ] Security requirements có sources, versions, applicability và owners.
- [ ] High/critical risks có treatment/control mapping hoặc risk decision minh bạch.
- [ ] Không suy ra chứng nhận/obligation áp dụng chỉ từ tên một standard.

### 31.2. Control framework và assurance design

- [ ] Có taxonomy, stable IDs, versioning và owner.
- [ ] Control statements mô tả behavior/condition có thể kiểm, không chỉ khẩu hiệu.
- [ ] Mỗi critical control có assertions và test method thích hợp.
- [ ] Control applicability/units có population và scope.
- [ ] Test catalog có positive/negative cases khi phù hợp.
- [ ] Test method có safety, preconditions, expected/observed results.
- [ ] Evidence contract có nguồn, timestamp, artifact version, quality, retention và limitations.
- [ ] Có separation of duties hoặc ghi rõ giới hạn review độc lập.
- [ ] Có mapping risk→requirement→control→assertion→evidence.
- [ ] Có CI/CD, IaC, change/release và runtime triggers phù hợp.
- [ ] Không lấy build-time scanner PASS thay cho runtime effective-state evidence.
- [ ] Third-party/shared-responsibility controls có owner và scope rõ.
- [ ] Backup/DR có restore exercise, không chỉ backup job status.

### 31.3. Kết quả, remediation và governance

- [ ] Verdict taxonomy PASS/FAIL/INCONCLUSIVE/NOT_TESTED/N/A được áp dụng nhất quán.
- [ ] Một test synthetic không được ghi thành production evidence.
- [ ] Evidence FAIL/INCONCLUSIVE không bị chỉnh thành PASS vì có exception.
- [ ] Mẫu số coverage lấy từ required applicable units, có kiểm N/A.
- [ ] Critical FAIL/unknown được nổi bật thay vì che bằng mean.
- [ ] Findings có criterion, condition, evidence, risk, owner, action và retest.
- [ ] Remediation priority xét threat/exposure/impact/control confidence.
- [ ] Risk exception có authority, scope, finite expiry, mitigation evidence và review trigger.
- [ ] No unauthorized runtime bypass bị coi là approved hồi tố.
- [ ] FIX_IMPLEMENTED được tách khỏi CLOSED_VERIFIED.
- [ ] Root cause/preventive action có owner và kiểm regression khi cần.
- [ ] Assessment history/versioned decisions được giữ, không sửa lịch sử.
- [ ] Data privacy và secrets được bảo vệ trong evidence artifacts.

### 31.4. Báo cáo và demo

- [ ] Báo cáo có executive conclusion, scope, methodology, results, limitations.
- [ ] Có thể chọn một critical control và drill down đến test/evidence.
- [ ] KPI có unit, denominator, period và data source.
- [ ] Accepted risk không được cộng vào verified control PASS.
- [ ] Missing sources/asset population được báo rõ.
- [ ] Có danh sách top critical risks và required decisions.
- [ ] Có rollback/restore/incident handling path khi gặp critical gap.
- [ ] Có plan cập nhật framework khi assets, threat, requirements và policies đổi.
- [ ] Demo dùng dữ liệu synthetic/authorized, không khai thác hệ thống không có quyền.
- [ ] Assessor có thể xem lại evidence, phương pháp và lý do của mỗi kết luận.

## 32. Mở rộng dự án sang continuous assurance

Khi minimum viable framework hoạt động, hãy mở rộng theo rủi ro thay vì chỉ tăng số lượng controls:

### 32.1. Tự động hóa population và evidence health

- Cloud account/workload discovery theo nguồn tin cậy.
- Đối soát asset owner và mandatory controls khi tạo mới.
- Phát hiện source silence, scanner coverage gaps và stale evidence.
- Event-driven reassessment khi IAM/keys/network/API/data flows đổi.
- Pin evidence vào exact artifact/runtime version.
- Theo dõi expired exceptions và unapproved bypasses.
- Kiểm CI/CD policy bypass và emergency review.
- Dựng dashboard có **truy vết nguồn**, không chỉ điểm số tổng.

### 32.2. Assurance theo chu kỳ phát triển

~~~mermaid
flowchart LR
    RISK["Risk + changing context"] --> REQ["Requirements / obligations"]
    REQ --> LIB["Versioned control library"]
    LIB --> BUILD["Design / build / release gates"]
    BUILD --> RUN["Runtime assertions and evidence"]
    RUN --> VER["Verdict and uncertainty"]
    VER --> FIND["Finding / exception / remediation"]
    FIND --> TEST["Retest and preventive action"]
    TEST --> LIB
    RUN --> REPORT["Risk + assurance reporting"]
    REPORT --> RISK
~~~

Mỗi vòng phải ghi những gì mới:

- Assets và data flows thay đổi.
- Risks hoặc threat intelligence mới.
- Baseline/control version được sửa.
- Test coverage và evidence quality tăng/giảm.
- Findings mới, recurring root causes và exceptions hết hạn.
- Điều gì được chứng minh đạt, điều gì vẫn chưa xác minh.

### 32.3. Phân biệt framework maturity với assurance result

Một framework có quy trình trưởng thành có thể **phát hiện nhiều FAIL hơn** vì coverage tốt hơn; điều đó không nhất thiết là an ninh xấu đi. Cần đánh giá cùng lúc:

- **Framework capability:** có inventory, owners, automation, evidence lineage, QA.
- **Control effectiveness:** trong population hiện tại, assertions đạt/không đạt.
- **Risk disposition:** residual risks, acceptance, mitigation và remediation.
- **Assurance confidence:** bằng chứng đủ đại diện và đúng kỳ tới đâu.

Không đồng nhất **số findings ít** với **security posture tốt**; có thể do scanner bị mất nguồn.

## Kết luận

**Xây control framework** là xây một cơ chế vận hành kết nối **rủi ro và yêu cầu với controls có thể kiểm chứng**. Một thư viện 31 control candidates chỉ là nguyên liệu. Giá trị thật đến từ việc xác định đúng assets và data, phân loại applicability, giao owner, viết assertion/test, thu evidence tin cậy, báo verdict trung thực và xử lý những sai lệch đến verified closure.

Trong module **SECURITY_SECURITY_ASSURANCE**, kết quả của dự án phải tạo được chuỗi truy vết **business/security objective → threat scenario → requirement → control → affected unit → test → evidence → PASS/FAIL/INCONCLUSIVE/NOT_TESTED → finding/exception → remediation → retest → assurance reporting**. Nếu người học có thể lấy bất kỳ critical claim nào, chỉ ra được bằng chứng nào hỗ trợ nó, bằng chứng nào chưa có, ai chịu trách nhiệm và khi nào đánh giá lại, thì họ đã nắm được nền tảng của **continuous security assurance** — thay vì chỉ sở hữu một danh sách controls trông đầy đủ trên giấy.





