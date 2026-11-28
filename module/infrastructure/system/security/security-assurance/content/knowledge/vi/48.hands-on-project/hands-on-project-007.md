# Thực hiện vulnerability cycle: Dự án thực hành quản lý lỗ hổng từ phát hiện đến kiểm chứng đóng

## Mục tiêu học tập và kết quả cần bàn giao

Sau dự án, người học có thể:

1. Thiết lập **vulnerability management cycle** phù hợp mục tiêu của mô-đun **SECURITY_SECURITY_ASSURANCE**: phát hiện điểm yếu, đánh giá rủi ro, đưa ra quyết định xử lý và xây dựng **bằng chứng** rằng security controls được duy trì trong phát triển và vận hành.
2. Xác định scope, asset/identity/service inventory, owner, nguồn dữ liệu và phương pháp discovery; phát hiện những tài sản **không xuất hiện trong công cụ quét**.
3. Chuẩn hóa kết quả quét, đối chiếu nguồn, **deduplicate**, phân loại **confirmed, potential, false positive, duplicate, not applicable** và ghi lại uncertainty.
4. Ưu tiên xử lý theo **tác động nghiệp vụ, mức phơi nhiễm, khả năng khai thác, attack path, bằng chứng exploitation, compensating controls**, thay vì xếp hàng chỉ theo CVSS.
5. Phân biệt **remediation, mitigation, risk acceptance, exception, avoidance** và escalation; lập kế hoạch có owner, deadline và điều kiện chấp nhận.
6. Thực thi thay đổi có kiểm soát, xác minh **effective state**, an toàn chức năng, rollback/forward-fix, monitoring và khả năng điều tra.
7. Retest bằng phương pháp phù hợp, xác nhận bằng chứng, xử lý **reopened finding**, và chỉ đóng khi criterion đạt trong đúng scope.
8. Đo coverage, age, overdue, time-to-remediate, retest pass rate và risk exposure, kèm mẫu số và những giới hạn dữ liệu.
9. Hoàn thiện **register, risk decisions, remediation tickets, evidence index và assurance report** có thể được một reviewer độc lập kiểm tra lại.
10. Thiết kế lịch quét/đánh giá lại sau releases, vulnerability intelligence, asset onboarding, incidents và exceptions, biến bài lab thành **continuous vulnerability assurance**.

**Đầu ra bắt buộc của dự án** là một bộ hồ sơ thực hành về vulnerability cycle, không phải một cuộc tấn công vào hệ thống thật. Bài cung cấp **dữ liệu mô phỏng** và các thao tác an toàn; các lệnh, API và kỹ thuật kiểm tra chỉ được dùng trong môi trường mà bạn sở hữu hoặc có **ủy quyền rõ ràng**.

> **Phạm vi nội dung:** Bài thuộc chương **Dự án thực hành** của dịch vụ **SECURITY_SECURITY_ASSURANCE**. Mục tiêu là đánh giá có bằng chứng rằng hệ thống đáp ứng yêu cầu bảo mật từ risk/controls tới testing, audit và khắc phục. Tên assets, findings, mã yêu cầu, số điểm và SLA dưới đây đều **giả định**; không được dùng như kết luận về CVE, phần mềm, tổ chức hoặc hệ thống có thật.

## 1. Bài toán nghiệp vụ: vì sao cần một vulnerability cycle?

Một báo cáo scanner có thể chứa hàng trăm findings. Scanner phản ánh những gì công cụ quan sát được tại thời điểm quét, nhưng **không tự trả lời**:

- Tài sản nào **đáng ra phải có trong phạm vi** nhưng scanner không nhìn thấy?
- Finding có thực sự áp dụng cho đúng phiên bản/build/đường sử dụng không?
- Điểm yếu có thể bị khai thác qua **đường truy cập thực tế** nào?
- Finding nào ảnh hưởng dữ liệu nhạy cảm hoặc khả năng kinh doanh Critical?
- Patch có gây gián đoạn, mất logs, lỗi khóa mã hóa hoặc phá cơ chế phục hồi không?
- Có controls bù trừ hiệu lực thật hay chỉ được liệt kê?
- Ai chịu trách nhiệm xử lý, ưu tiên và chấp nhận residual risk?
- Một ticket Done có đồng nghĩa lỗ hổng đã được **retest** và biến mất?
- Lỗ hổng đã tồn tại bao lâu, có đoạn thời gian không quan sát được không?
- Khi lỗ hổng tái xuất hiện sau release, hệ thống có mở lại finding đúng không?

**Vulnerability cycle** là quy trình lặp:

**Define scope → Discover → Normalize/validate → Triage/prioritize → Decide treatment → Remediate/mitigate → Verify/retest → Close/report → Monitor/reassess.**

Không nên hiểu vulnerability cycle là “quét → xuất CSV → sửa vài dòng → đánh dấu xanh”. Một chương trình trưởng thành phải có **closed-loop assurance**: mọi quyết định đều liên kết tới nguồn, thời điểm, asset và acceptance criterion.

### 1.1. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Vulnerability** | Điểm yếu có thể ảnh hưởng an toàn nếu bị khai thác trong điều kiện phù hợp. | API authorization thiếu kiểm tra ownership. |
| **Weakness** | Loại sai sót thiết kế/cấu hình/lập trình, có thể được mô tả bằng taxonomy khi phù hợp. | Phân quyền ở UI thay vì server. |
| **Exposure** | Mức tiếp cận thực tế của attack path hoặc đối tượng. | Gateway công khai trên internet; DB chỉ trong mạng hạn chế. |
| **Finding** | Một quan sát cần xác minh, gồm asset, condition, evidence và source. | Scanner cho biết một dependency có phiên bản đáng xem xét. |
| **Confirmed finding** | Điểm yếu được xác minh bằng bằng chứng phù hợp, đúng phạm vi. | Effective route cho phép user A xem order tenant B trong test được phép. |
| **False positive** | Có bằng chứng finding không đúng trong scope được đánh giá. | Vendor đã backport bản vá nhưng scanner chỉ so version string. |
| **Duplicate** | Hai records mô tả cùng một điểm yếu trên cùng affected unit/condition. | Hai scanners cùng phát hiện một gói dễ bị ảnh hưởng. |
| **Risk** | Hậu quả bất định của điểm yếu trong điều kiện nghiệp vụ, threats và controls. | Credential compromise có thể dẫn tới dữ liệu đơn hàng bị lộ. |
| **Remediation** | Xử lý nguyên nhân/điều kiện làm điểm yếu không còn đạt criterion của finding. | Cập nhật dependency và xác minh version/runtime. |
| **Mitigation** | Giảm khả năng/tác động khi chưa loại bỏ điểm yếu. | Hạn chế network, tắt feature, thêm monitoring. |
| **Risk acceptance/exception** | Quyết định có thẩm quyền và điều kiện cho rủi ro còn lại, không biến FAIL thành PASS. | Chấp thuận tạm thời hệ thống legacy có biện pháp bù trừ. |
| **Retest** | Kiểm chứng sau thay đổi đúng asset, version, behavior và acceptance criteria. | Test negative access và config kiểm tra không còn đường bypass. |

### 1.2. Vulnerability cycle và security assurance

Vulnerability management tạo quyết định và hành động. Security assurance đặt câu hỏi **“tại sao ta có thể tin rằng quyết định và hành động ấy đủ?”**

Một finding được “resolved” trên dashboard **không đủ** nếu asset đã biến mất khỏi scanner do agent lỗi. Một bản vá “applied” chưa đủ nếu ứng dụng vẫn dùng binary cũ sau rollout. Một service không còn thấy vulnerability có thể vì scanner mất quyền hoặc nguồn inventory thiếu.

**Cần chứng minh cả vulnerability status lẫn chất lượng của phép đo status ấy.**

## 2. Quy tắc an toàn và phạm vi lab

Dự án sử dụng các assets/findings hư cấu để thực hành **quy trình, mô hình dữ liệu, quyết định rủi ro và kiểm chứng**. Không yêu cầu tạo payload khai thác hoặc quét máy chủ bên ngoài.

### 2.1. Nguyên tắc thực hành

- Chỉ thao tác trên **lab, sandbox hoặc hệ thống được ủy quyền bằng văn bản/quy trình nội bộ**.
- Không dùng scanner gây quá tải đối với production mà chưa có approved change window.
- Không thực hiện credential spraying, truy cập trái quyền, khai thác CVE thật hoặc xuất dữ liệu người dùng nhằm “xác nhận” finding.
- Dùng **synthetic identities, synthetic records, test accounts** và xác minh cấu hình/package khi có thể.
- Không đưa access tokens, credentials, PII hoặc chi tiết khai thác nhạy cảm vào tickets/evidence thông thường.
- Nếu test có thể ảnh hưởng dịch vụ, xác định owner, stop conditions, monitoring và rollback trước.
- Khi có dấu hiệu **compromise hiện tại**, ưu tiên incident response, preserve evidence và escalation, không tự tiếp tục thử nghiệm để tăng điểm lab.

### 2.2. Công cụ tối thiểu

Có thể làm bài chỉ bằng **bảng tính hoặc một file Markdown** cùng dữ liệu ví dụ dưới đây. Trong hệ thống thật, các nguồn dữ liệu thường gồm:

- CMDB/cloud/Kubernetes/identity inventory.
- Vulnerability scanners với scope và run history.
- SCA/SBOM, image/container scanner, IaC/cloud configuration checks.
- Advisory/vendor fix status, threat intelligence và thông tin exploitation có nguồn xác minh.
- Ticketing/change/release system và risk/exception register.
- CI/CD, artifact digest, effective configuration, deployment runtime.
- SIEM/source-health, EDR/agent status và security test results.
- GRC/evidence index và reviewer signoff.

**Công cụ nào có sẵn không quyết định ranh giới risk.** Cần chọn nguồn đáp ứng câu hỏi assurance trước khi chọn cách xuất báo cáo.

## 3. Bối cảnh dự án mô phỏng: OrderBridge

Doanh nghiệp giả định **OrderBridge** cung cấp dịch vụ SaaS quản lý đơn hàng. Hệ thống có API, database, workers, CI/CD, logging, vault và ứng dụng báo cáo legacy.

Các mục tiêu bảo mật:

- **O-C:** Không cho truy cập trái phép dữ liệu khách hàng.
- **O-I:** Bảo vệ tính toàn vẹn đơn hàng, quyền và bản ghi hệ thống.
- **O-A:** Duy trì dịch vụ Critical và khả năng phục hồi.
- **O-D:** Các sự kiện quan trọng được audit/detect và chuyển tới người xử lý.
- **O-G:** Thay đổi, findings, exceptions và remediation có thể truy vết để quản trị.

### 3.1. Kiến trúc phạm vi

~~~mermaid
flowchart LR
    CLIENT["Customer/admin test clients"] --> GW["A01 Public Gateway"]
    GW --> API["A02 Order API"]
    API --> DB["A03 Customer DB"]
    API --> WORK["A04 Worker"]
    WORK --> VENDOR["Analytics SaaS"]
    BUILD["A05 CI Runner"] --> API
    PORTAL["A06 Legacy Reporting"] --> DB
    API --> LOG["A07 Log Collector"]
    GW --> LOG
    ADMIN["A08 Ops endpoint"] --> BUILD
    DB --> VAULT["A09 Backup Vault"]
    DEV["A10 Dev Web"] -. separate environment .-> GW
~~~

Sơ đồ giúp xác định **các đường rủi ro và phụ thuộc**, không phải cấu hình mạng có thể deploy. Dòng chấm chỉ biểu thị liên quan phát triển, **không** ngụ ý dev có quyền truy cập production.

### 3.2. Authoritative asset inventory

| Asset ID | Asset/service | Môi trường | Criticality | Owner | Exposure/data |
|---|---|---|---|---|---|
| **A01** | edge-gateway | Production | Critical | Edge team | Public internet, auth gateway. |
| **A02** | order-api | Production | Critical | Application team | Internal behind gateway, confidential order data. |
| **A03** | customer-db | Production | Critical | Data platform | Private network, confidential data. |
| **A04** | event-worker | Production | High | Application team | Internal queue, SaaS egress. |
| **A05** | ci-runner | Production-support | High | DevSecOps | Build/deploy permissions and tokens. |
| **A06** | legacy-report | Production | High | Business apps | VPN-restricted, report access. |
| **A07** | audit-collector | Production | Critical | Logging/SOC | Security events and detection dependencies. |
| **A08** | ops-laptop-07 | Managed endpoint | Medium | Endpoint team | Administrator workstation. |
| **A09** | backup-vault | Production recovery | Critical | DR/data team | Backup, KMS keys and recovery data. |
| **A10** | dev-web | Development | Low | Web team | Non-production sample data. |

**Tổng inventory ví dụ: 10 assets.** Khác nhau về môi trường không có nghĩa dev bị loại hoàn toàn khỏi vulnerability program: A10 vẫn phải có control/triage theo policy tương ứng, dù có priority thấp hơn.

### 3.3. Đầu ra cần nộp

| Artifact | Mục tiêu | Điều kiện tối thiểu |
|---|---|---|
| **Scope & inventory register** | Chứng minh population và owners. | 10 assets, environment, criticality, source, unknowns. |
| **Raw findings register** | Lưu đúng quan sát ban đầu. | 12 records, source/run/time, affected asset, fingerprint. |
| **Normalized/triaged register** | Xác thực, dedup, loại false positive có bằng chứng. | Mỗi finding có status và rationale. |
| **Risk priority register** | Quyết định thứ tự xử lý. | Business impact, exposure, exploit evidence, reachability, controls. |
| **Treatment & approval records** | Chứng minh rủi ro được xử lý đúng thẩm quyền. | Owner, treatment, SLA, exceptions, monitoring. |
| **Change/remediation plans** | Thực thi có kiểm soát. | Change IDs, implementation, rollback, acceptance. |
| **Retest evidence** | Chứng minh gap được xử lý. | Before/after, effective state, test, source quality, reviewer. |
| **Metrics & assurance report** | Đưa ra kết luận minh bạch. | Numerator/denominator, unknowns, open high risks, limitations. |

Tất cả artifact có thể được thể hiện thành **các bảng và record trong chính tài liệu thực hành của người học**; không bắt buộc tạo hệ thống ticket thật.

## 4. Dữ liệu đầu vào: 12 raw findings

Bảng sau là **dữ liệu hư cấu**, không mô tả CVE có thật. Các mức điểm trong đề chỉ để luyện triage, **không phải CVSS chính thức**.

| Raw ID | Asset | Nguồn giả định | Quan sát ban đầu | Scanner priority | Trạng thái cần xác minh |
|---|---|---|---|---|---|
| **F01** | A01 | image-scan-01 | Thư viện xử lý request cần cập nhật trên public gateway. | Critical | Candidate. |
| **F02** | A02 | app-test-02 | Route đọc order có dấu hiệu thiếu object-level authorization. | Critical | Candidate. |
| **F03** | A03 | cloud-config-01 | Database ingress cho phép subnet rộng hơn thiết kế. | High | Candidate. |
| **F04** | A04 | sca-01 | Transitive dependency nằm trong SBOM nhưng chưa rõ có được thực thi. | High | Candidate. |
| **F05** | A05 | iam-review-01 | CI runner có token với quyền deploy/quản trị quá rộng. | Critical | Candidate. |
| **F06** | A06 | tls-check-01 | Legacy portal cho phép giao thức TLS cũ trái baseline. | Medium | Candidate. |
| **F07** | A07 | package-scan-01 | Audit collector sử dụng build cần cập nhật bảo mật. | High | Candidate. |
| **F08** | A08 | package-scan-02 | Phiên bản package nhìn cũ nhưng có thể được vendor backport fix. | Medium | Candidate. |
| **F09** | A09 | key-policy-01 | Backup vault role có thể dùng key rộng hơn mục đích. | High | Candidate. |
| **F10** | A10 | dev-dep-scan | Thư viện dev-web cũ, dùng trong non-production. | Low | Candidate. |
| **F11** | A01 | image-scan-02 | Cùng component/path và condition với F01. | Critical | Suspected duplicate. |
| **F12** | A07 | config-scan-01 | Dịch vụ admin trong collector có thể có đường xác thực yếu. | High | Candidate. |

Nguồn là tên pipeline minh họa. Một raw report thực cần **scan run ID, thời gian, target, scanner version, plugin/rule ID, proof, error/coverage status và evidence link**, không chỉ chứa bảng này.

### 4.1. Dạng CSV có thể sao chép để làm bài

~~~csv
finding_id,asset_id,source,kind,status
F01,A01,image-scan-01,dependency,CANDIDATE
F02,A02,app-test-02,authorization,CANDIDATE
F03,A03,cloud-config-01,network-config,CANDIDATE
F04,A04,sca-01,transitive-dependency,CANDIDATE
F05,A05,iam-review-01,iam-overprivilege,CANDIDATE
F06,A06,tls-check-01,crypto-config,CANDIDATE
F07,A07,package-scan-01,package,CANDIDATE
F08,A08,package-scan-02,package,CANDIDATE
F09,A09,key-policy-01,key-permission,CANDIDATE
F10,A10,dev-dep-scan,development-dependency,CANDIDATE
F11,A01,image-scan-02,dependency,CANDIDATE
F12,A07,config-scan-01,admin-auth,CANDIDATE
~~~

**Không đổi hoặc xóa raw records sau triage.** Giữ nguyên bản gốc, tạo normalized/assessment records có liên kết, để auditor biết một kết quả bị loại vì lý do nào.

### 4.2. Chuẩn hóa khóa định danh

Một fingerprint cần đủ các yếu tố phù hợp với loại finding:

- Canonical asset ID hoặc stable workload/image identity.
- Package/component hoặc control/rule identifier.
- Vulnerability/condition identifier khi có và đáng tin.
- Package version/build, artifact digest hoặc configuration version.
- Affected service/path/port/resource.
- Exposure context và time window.

Ví dụ hai scanners mô tả cùng thư viện trên cùng image digest A01, cùng đường sử dụng và cùng condition → **có thể dedup**. Nhưng cùng tên package trên **hai tài sản khác nhau** vẫn là hai affected units cần xử lý, dù nguồn sửa có thể là một codebase.

## 5. Sơ đồ chu trình thực hiện

~~~mermaid
flowchart TD
    S0["0. Define scope, policy, owner & inventory"] --> S1["1. Discover + evidence source health"]
    S1 --> S2["2. Normalize, correlate, deduplicate"]
    S2 --> S3["3. Validate: confirmed, potential, FP, N/A"]
    S3 --> S4["4. Contextual risk & priority"]
    S4 --> S5["5. Treatment decision & SLA/approval"]
    S5 --> S6["6. Remediate/mitigate via controlled change"]
    S6 --> S7["7. Verify effective state + retest"]
    S7 --> D{"Criterion met?"}
    D -->|Yes| S8["8. Verified closure + report"]
    D -->|No / incomplete evidence| F["Finding remains open / reopen / escalate"]
    F --> S4
    S8 --> S9["9. Monitor drift, intelligence & new assets"]
    S9 --> S1
~~~

Quá trình **không phải tuyến tính một lần rồi kết thúc**. Mỗi asset mới, patch release, vulnerability advisory, incident, policy change hoặc exception expiry có thể đưa một finding trở lại bước triage hoặc tạo finding mới.

## 6. Pha 0 — Governance, scope và điều kiện kết thúc

### 6.1. Xác định mục tiêu và chính sách

Với dự án này, ta giả định:

- Mọi asset trong 10-item inventory được theo dõi. Một finding có thể áp dụng khác nhau tùy environment.
- Những điểm yếu có **confirmed unauthorized access**, critical exposure hoặc khả năng mất security monitoring có thể là **hard escalation**, không chỉ phụ thuộc điểm scanner.
- Mọi findings có ID, owner, observed time và assessment status.
- Không sửa SLA/hạ severity sau khi quá hạn chỉ để báo cáo đẹp.
- Exceptions là **quyết định risk** có scope, thẩm quyền, thời hạn và controls bù trừ.
- Findings chỉ **VERIFIED_CLOSED** sau retest thích hợp, không chỉ sau ticket Done.
- Những phần không đủ inventory/telemetry/evidence giữ **UNKNOWN hoặc INCONCLUSIVE**, không tính PASS.
- Kỳ đánh giá ví dụ được chốt tại **2026-11-28T00:00:00Z**; mọi thay đổi sau mốc cần version/time riêng.

### 6.2. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm | Đầu ra |
|---|---|---|
| **Asset/service owner** | Xác nhận asset, dependencies, business impact. | Inventory, exposure facts, remediation sponsorship. |
| **Vulnerability analyst** | Intake, dedup, validation, contextual triage. | Normalized finding, risk rationale, uncertainty. |
| **Security architect/AppSec** | Threat/risk analysis, compensating controls và test design. | Attack-path assessment, security acceptance. |
| **Platform/engineering** | Sửa source/config/package, kiểm soát deployment/rollback. | Change record, effective state, functional tests. |
| **SOC/incident response** | Đối chiếu exploitation signals, monitoring và incident triggers. | Event evidence, triage/case, containment khi cần. |
| **Risk owner** | Quyết định risk acceptance trong thẩm quyền. | Signed risk decision, expiry, conditions. |
| **Compliance/legal** | Xác định nghĩa vụ/giới hạn được phép miễn, khi có liên quan. | Applicability/obligation review. |
| **Assurance reviewer** | Kiểm tra evidence, status, retest và closure criteria. | Verdict, limitations, findings. |
| **Program owner/GRC** | Quy trình, metrics, SLA governance và evidence index. | Dashboard, exceptions register, report. |

Có thể kiêm vai khi quy mô nhỏ, nhưng các quyết định trọng yếu cần xem **separation of duties**, độc lập người sửa và người xác minh theo chính sách.

### 6.3. Scope freeze không có nghĩa inventory cố định

Tại mốc T0, ghi 10 assets. Nếu discovery tìm thêm A11 trong production:

1. Ghi A11 như **newly discovered asset** với observed/first-seen times.
2. Xác minh owner, criticality và applicability.
3. Thêm A11 vào **đúng population** ở kỳ tiếp theo hoặc sửa snapshot có audit trail nếu trước đó bỏ sót.
4. Không âm thầm giữ denominator cũ để không giảm coverage.
5. Có finding nếu A11 đã hoạt động lâu mà không được kiểm soát theo policy.

## 7. Pha 1 — Discovery và xác minh độ bao phủ của nguồn

### 7.1. Các lớp nguồn nên có

| Nguồn | Có thể phát hiện | Điểm mù cần kiểm tra |
|---|---|---|
| **Host/endpoint scanner** | Packages/configuration trên máy nó truy cập. | Assets không cài agent, offline, quyền không đủ. |
| **Network-based scan** | Open services/config trên những mạng được phép. | Reachability khác nhau theo mạng, auth/ACL và firewall. |
| **Image/container scan** | Vulnerable packages trong image. | Image không được deploy, backport, runtime context. |
| **SCA/SBOM** | Dependencies trực tiếp/gián tiếp của build. | Package có trong SBOM nhưng code path không chạy, build khác. |
| **SAST/app testing** | Potential weaknesses trong code/behavior. | False positives, không đủ environment/identity scopes. |
| **Cloud/IaC posture** | Network/IAM/storage policy/config drift. | Effective state khác declared state, account/region thiếu. |
| **Threat/advisory intake** | New affected products/conditions và patch guidance. | Version mapping, vendor fixes, false assertions. |
| **Manual design review** | Architecture, trust boundary và business logic risks. | Không thể bao quát nếu thiếu domain knowledge. |

Một nguồn không có findings **không chứng minh không có điểm yếu**, nếu nguồn ấy không nhìn thấy population hoặc scan đã fail.

### 7.2. Chứng minh coverage của scanning

Đặt:

- **A** = số assets trong authoritative inventory thuộc scope.
- **S** = số assets có scan/assessment hợp lệ, còn tươi và đủ privilege/coverage theo contract.
- **Q** = số assets chưa thể kết luận vì scan fail/missing coverage.

\[
\text{Verified assessment coverage}=\frac{|S|}{|A|}\times100\%
\]

\[
\text{Unknown assessment coverage}=\frac{|Q|}{|A|}\times100\%
\]

Nếu trong 10 assets chỉ 8 đã được đánh giá hợp lệ, 2 không có report đáng tin, coverage là **8/10 = 80%** và unknown **2/10 = 20%**; không được báo “0 vulnerabilities trên 2 assets” hoặc tự loại chúng khỏi mẫu số.

Nếu denominator = 0 sau kiểm tra applicability, metric là **N/A**, không tự tính 100%.

### 7.3. Source health và điều kiện từ chối dữ liệu

Một assessment run phải lưu:

- Scan run ID, scanner/plugin/ruleset version và account thực hiện.
- Target list, target reachability, credential privileges và lỗi phát sinh.
- Start/end/event timestamps, timezone, complete/incomplete status.
- Tool outputs và evidence storage/provenance.
- So sánh số assets/discovery trước sau, pagination và asset ID mapping.
- Không gian nào không thể scan (regions, accounts, namespaces, private networks).
- Acceptance/rejection of data source theo monitoring policy.

**Một lần quét thành công 100% đối với 8/10 assets không thể thay thế bằng kết luận 100% asset coverage.**

## 8. Pha 2 — Chuẩn hóa, tương quan và deduplicate

### 8.1. Vì sao raw findings dễ đếm trùng?

Hai scanners có thể:

- Phát hiện cùng package condition nhưng dùng plugin IDs khác.
- Dùng hostname, container name và instance ID khác nhau cho cùng asset.
- Quét cùng image digest ở nhiều deploy instances.
- Ghi lại cùng issue sau mỗi lần quét thành finding mới.
- Trộn cảnh báo ở package tồn tại trong SBOM với điều kiện runtime đã được sửa.

**Deduplicate không phải xóa records**, mà là lập quan hệ **raw finding → canonical finding**.

### 8.2. Quy tắc thực hành

1. Bảo toàn raw IDs và original timestamps.
2. Mapping về canonical asset ID qua authoritative inventory.
3. So sánh **type, package/build, config path, affected component, runtime environment và condition**.
4. Nếu cùng root cause và cùng affected unit, có thể gắn **DUPLICATE_OF**.
5. Nếu khác assets, giữ **affected-instance records** riêng dù chung một remediation change.
6. Nếu chưa chắc, giữ **POTENTIAL_DUPLICATE** và reviewer quyết định.
7. Liên kết các nguồn phát hiện khác nhau để tăng provenance, không đếm chúng như findings độc lập.

Ví dụ **F11 → duplicate_of: F01** vì cùng image/build, same condition và asset A01. Nếu scanner B thực sự phát hiện một **đường runtime khác** chưa được kiểm tra, việc gộp phải được xem lại.

### 8.3. Dữ liệu gợi ý

~~~json
{
  "canonical_finding_id": "VF-001",
  "asset_id": "A01",
  "condition_key": "gateway-request-library-outdated",
  "raw_refs": ["F01", "F11"],
  "dedup_reason": "same asset and artifact digest, same affected component",
  "validation_state": "PENDING_VALIDATION",
  "reviewer": "vulnerability-analyst",
  "evidence_refs": ["EV-F01-IMAGE", "EV-F11-IMAGE"]
}
~~~

JSON chỉ là mẫu. Khi tạo record thật, không dùng reason dedup nếu chưa có image digest/proof tương ứng.

## 9. Pha 3 — Xác thực findings và phản biện kết quả scan

### 9.1. Tình trạng một finding

| Status | Điều kiện | Xử lý |
|---|---|---|
| **CONFIRMED** | Điều kiện phù hợp và có bằng chứng đủ về affected asset/build/path. | Risk triage và treatment. |
| **PENDING_VALIDATION** | Có tín hiệu nhưng thiếu version/reachability/condition/evidence. | Yêu cầu dữ liệu, giữ trong queue, không tự đóng. |
| **FALSE_POSITIVE** | Bằng chứng đáng tin phủ định finding trong phạm vi được xét. | Lưu rationale, reviewer và source; monitor nếu điều kiện đổi. |
| **DUPLICATE** | Trùng canonical finding đã xác định. | Liên kết parent, giữ provenance và affected instances. |
| **NOT_APPLICABLE** | Có căn cứ loại khỏi phạm vi do điều kiện kỹ thuật/yêu cầu cụ thể. | Ghi scope/rationale và trigger xem lại. |
| **CONFIRMED_NOT_REACHABLE** | Weakness có thể tồn tại nhưng chưa thấy attack path trong threat model. | Không tự thành FP; đánh giá residual risk và changes. |
| **NEEDS_SECURITY_REVIEW** | Có business logic, legal/privacy hay attack-path ambiguity. | Escalate SME phù hợp. |

**“Chưa thấy đường khai thác” không đồng nghĩa package đã được vá**. Nếu package vulnerable nhưng đường sử dụng chưa reachable trong phạm vi, có thể giảm priority theo evidence, nhưng không nên tự gán FALSE_POSITIVE.

### 9.2. Các cách xác minh an toàn

- Kiểm tra **effective package version, build release và vendor advisory**.
- Xem manifest/SBOM/image digest so với runtime đã deploy.
- Đánh giá feature/route có được enable và exposure thực tế.
- So khớp cloud/IAM **effective permissions**, không chỉ manifest.
- Kiểm tra config, network policy và authorized reachability theo scope.
- Dùng test accounts và dữ liệu giả để kiểm tra business logic authorization.
- Xác thực vendor backport hoặc patch provenance cho versions nhìn cũ.
- Đối chiếu scanners độc lập và evidence từ control plane.

Không bắt buộc thực hiện khai thác thực tế để xác nhận mọi finding. Với môi trường Critical, **proof về affected build/config và threat applicability** có thể đủ để mở remediation; các test behavior phải có authorization và kế hoạch an toàn.

### 9.3. Hai trường hợp quan trọng trong bộ dữ liệu

**F08 (A08):** Scanner dựa trên upstream version string nên báo package lỗi, nhưng vendor có thể backport bản vá vào downstream build. Cần vendor fix record/changelog, package build ID và effective deployed package. Chỉ khi các bằng chứng này khớp mới phân loại FALSE_POSITIVE cho criterion cụ thể.

**F04 (A04):** SBOM chứa transitive dependency, chưa đủ kết luận code path đang chạy. Cần xác định version/build, đường sử dụng, reachability và vendor fix. Không có bằng chứng chạy không tự làm finding biến mất; để **PENDING_VALIDATION** và review theo risk.

### 9.4. Điều kiện thực hành của dự án

Sau khi xem dữ liệu giả và evidence được cung cấp trong bài, ta dùng kết luận mẫu:

| Raw finding | Kết luận kiểm chứng | Căn cứ giả định |
|---|---|---|
| F01, F02, F03, F05, F06, F07, F09, F10 | **CONFIRMED** | Artifact/config/behavior evidence phù hợp cho tám findings. |
| F04, F12 | **PENDING_VALIDATION** | Chưa đủ reachability/auth/config evidence. |
| F08 | **FALSE_POSITIVE** | Vendor backport và installed build đã được xác minh. |
| F11 | **DUPLICATE_OF F01** | Cùng affected artifact và condition. |

Như vậy **12 raw records** được phân loại: **8 confirmed + 2 pending + 1 false positive + 1 duplicate**.

Không được biến 12 raw findings thành “12 confirmed vulnerabilities”. Ngược lại, **không xem F04/F12 là an toàn** vì chúng chưa được kết luận.

## 10. Pha 4 — Đánh giá rủi ro theo bối cảnh

### 10.1. Vì sao không thể xếp bằng severity từ scanner?

Điểm đánh giá kỹ thuật như CVSS có thể mô tả mức độ nghiêm trọng của **điểm yếu trong bộ giả định nhất định**, nhưng quyết định remediation còn phụ thuộc:

- Asset criticality và business process.
- Dữ liệu nhạy cảm, integrity và availability impact.
- Public/internal exposure và trust boundary.
- Exploitability/reachability trong deployment cụ thể.
- Bằng chứng exploitation từ nguồn phù hợp; tính cấp thiết của tình hình.
- Effective compensating controls, cùng độ tin cậy của tests.
- Privilege needed, khả năng lateral movement.
- Shared dependencies và blast radius.
- Existing incident, customer impact và regulatory/contractual triggers.
- Ability to patch/rollback, release timing và downtime risk.

Một issue trên **CI runner có quyền deploy production** có thể được ưu tiên cao dù không public internet. Một vulnerability trong dependency ở dev có thể cần triage nhưng không nên tự xếp bằng API public Critical.

### 10.2. Triage matrix

| Yếu tố | Câu hỏi | Evidence mẫu |
|---|---|---|
| **Impact** | Tổn thất cụ thể với C/I/A/contract là gì? | BIA, data classification, transaction integrity. |
| **Exposure** | Ai có thể tiếp cận đường lỗi, qua network/identity nào? | Route map, firewall effective config, ingress logs. |
| **Exploit conditions** | Phiên bản, feature và preconditions có đúng không? | Vendor advisory, SBOM/runtime, test method. |
| **Threat activity** | Có cảnh báo khai thác đang diễn ra/ưu tiên thời gian không? | Threat intelligence có timestamp và source. |
| **Control effectiveness** | Segmentation, deny policy, detection/response có test chưa? | Effective state và positive/negative tests. |
| **Uncertainty** | Điều gì chưa xác định và có thể làm priority tăng? | Missing asset data, scan limits, event/source gaps. |
| **Remediation feasibility** | Fix/mitigate thay đổi nghiệp vụ và rollback ra sao? | Change plan, integration tests, backup/DR. |

### 10.3. Priority rules giả định

Trong lab dùng bốn mức **không phải chuẩn chung**:

| Priority | Điều kiện minh họa | Treatment horizon minh họa |
|---|---|---|
| **P0 – Urgent** | Confirmed critical risk, active exploit signal hoặc unauthorized access route. | Contain/escalate ngay; mốc triage/containment 24 giờ trong ví dụ, remediation theo quyết định khẩn. |
| **P1 – High** | High-impact asset/exposure hoặc privilege path với rủi ro đáng kể. | Kế hoạch xử lý, mục tiêu 7 ngày theo policy giả định. |
| **P2 – Medium** | Exposure/impact giới hạn, có controls và evidence phù hợp. | Mục tiêu 30 ngày theo policy giả định. |
| **P3 – Low** | Non-production/low-impact condition đã xác minh. | Mục tiêu 90 ngày theo policy giả định. |

Nếu tồn tại **nghĩa vụ bắt buộc, incident hoặc exploit đang diễn ra**, việc quyết định phải theo governance thực tế; không dựa máy móc vào các mốc trong bảng.

### 10.4. Kết quả triage mẫu cho tám findings confirmed

| Finding | Tác động và phơi nhiễm | Priority ví dụ | Cần làm ngay |
|---|---|---|---|
| **F01** A01 | Internet gateway, dependency lỗi trên đường xử lý request; ảnh hưởng Critical. | **P0** | Giảm exposure, đánh giá containment, patch/change. |
| **F02** A02 | API có confirmed cross-tenant access trong test synthetic. | **P0** | Chặn route/giới hạn tính năng, điều tra tác động và sửa authz. |
| **F03** A03 | Database private nhưng ingress rộng hơn approved network. | **P1** | Thu hẹp effective network rule và kiểm tra dependencies. |
| **F05** A05 | CI credential có quyền production quá rộng. | **P0** | Restrict/revoke credential theo runbook, điều tra access. |
| **F06** A06 | Legacy TLS trong VPN-restricted report portal. | **P2** | Lên kế hoạch nâng cấp, kiểm tra compatibility, kiểm soát bù trừ. |
| **F07** A07 | Security logging dependency chứa lỗi cần cập nhật, patch có thể ảnh hưởng detection. | **P1** | Patch có canary/source-health và detection regression. |
| **F09** A09 | Backup key permissions quá rộng, dữ liệu recovery Critical. | **P1** | Least privilege với kiểm chứng restore/decrypt. |
| **F10** A10 | Dev dependency cũ, data mẫu, chưa thấy đường production. | **P3** | Upgrade theo development lifecycle; monitor phạm vi đổi. |

**P0 không đồng nghĩa đã có xâm nhập thật.** F02 có behavior bị từ chối sai/cho phép sai trong test được phép, cần điều tra xem dữ liệu thật có bị ảnh hưởng. Một nghi vấn incident được xử lý qua IR riêng, không tự khẳng định compromise.

### 10.5. Không “chấm điểm để hợp thức hóa”

Một công thức điểm tổng có thể giúp sắp xếp backlog nhưng chỉ đáng dùng khi:

1. Các thang đo, trọng số và ngưỡng được công bố và phê duyệt trước.
2. Các yếu tố có bằng chứng và xử lý unknown.
3. Không biến score thành **xác suất breach**.
4. Có hard escalation cho data exposure, exploit/active incident và mandatory obligations.
5. Người review có thể thay priority khi có rationale/authority đúng.
6. Chỉ số được xem lại khi scope, threats hoặc controls thay đổi.

Trong lab, **priority matrix định tính** ở trên đủ để quyết định; không cần tạo điểm số giả chính xác.

## 11. Pha 5 — Quyết định treatment và lập remediation plan

### 11.1. Các lựa chọn xử lý

| Treatment | Mục tiêu | Ví dụ | Cần evidence gì? |
|---|---|---|---|
| **Remediate** | Loại bỏ/khắc phục điểm yếu theo criterion. | Nâng package, sửa authorization, thu hẹp IAM. | Version/effective state + behavioral retest. |
| **Mitigate** | Giảm exposure/impact nhưng điểm yếu còn. | Tắt route, network isolation, WAF/IPS phù hợp. | Effective policy, positive/negative tests, monitoring. |
| **Avoid** | Ngừng một hoạt động có rủi ro. | Tắt dịch vụ legacy không còn cần. | Shutdown/decommission evidence và dependency check. |
| **Accept residual risk** | Chấp nhận phần rủi ro trong thẩm quyền. | Đưa exception có hạn cho TLS legacy theo điều kiện. | Risk assessment, DoA, expiry, compensating tests. |
| **Transfer/share** | Phân bổ trách nhiệm tác động theo cơ chế phù hợp. | Hợp đồng/bảo hiểm dịch vụ. | Contract, owner, scope; không thay remediation hoặc nghĩa vụ còn lại. |

**Mitigation không phải Remediation**. Một firewall rule làm giảm exposure của A01 nhưng image vulnerable vẫn còn thì finding không tự chuyển VERIFIED_CLOSED.

### 11.2. Trường thông tin tối thiểu trong ticket

- Finding ID, affected asset, environment, criticality, owner.
- Required condition, actual finding, risk scenario và evidence.
- Date first observed, date confirmed, risk tier và policy/SLA clock.
- Fix target/mitigation path, dependency và impact analysis.
- Change/release ID, implementer, approver và risk owner.
- Acceptance criteria có thể test, reviewer và due date.
- Compensating controls, monitoring, incident triggers.
- Rollback/forward-fix plan và data/secret/key considerations.
- Residual risk, exception ID nếu có, review/expiry.
- Retest result, actual date, source/version và evidence index.

### 11.3. Ticket YAML minh họa

~~~yaml
remediation:
  work_item: "REM-2026-005"
  finding_id: "F05"
  asset_id: "A05"
  owner: "devsecops"
  security_reviewer: "identity-assurance"
  priority: "P0"
  condition: "CI runner token grants excessive production privileges"
  threat_scenario: "Compromise of pipeline credential can modify production resources"
  business_impact: "High blast radius across production deployments"
  observed_at_utc: "2026-11-28T00:00:00Z"
  treatment:
    type: "remediate"
    actions:
      - "Scope service identity to approved deployment actions/resources"
      - "Rotate/revoke old token safely after validating replacement"
      - "Review historical privileged actions and unusual usage"
  preconditions:
    - "Identify all pipeline jobs and consumers of credential"
    - "Prepare safe rollback/alternate deploy method"
  acceptance:
    - "Required deployment operation succeeds with new scoped identity"
    - "Unauthorized production administration is denied"
    - "Old credential no longer grants access"
    - "Audit/detection still records privileged changes"
  change_id: "CHG-2026-005"
  evidence_required:
    - "Effective IAM policy before/after"
    - "Authorized positive/negative test"
    - "Credential revocation audit"
    - "Security telemetry and service health"
  status: "PLANNED"
  retest:
    status: "NOT_RUN"
~~~

Mẫu này **không chứa token** và không tự thực hiện thay đổi. Khi triển khai thật cần xác định kế hoạch đã được duyệt và ai có thẩm quyền truy cập hệ thống.

## 12. Phê duyệt ngoại lệ không phải đóng lỗ hổng

### 12.1. Cách xử lý F06 (legacy TLS)

Giả định portal A06 chỉ có thể nâng TLS sau khi nâng application server. Một requestor xin thêm **14 ngày** để chuẩn bị nâng cấp.

Risk owner phải xem:

1. Baseline nguồn nào yêu cầu protocol tương ứng?
2. Portal chỉ qua VPN? Có đường direct/alternate bypass?
3. Có dữ liệu Confidential hoặc người dùng bên thứ ba liên quan?
4. Liệu controls bù trừ (network, allowlist, monitoring) **đã test**?
5. Có nghĩa vụ hợp đồng/pháp lý không thể tự miễn?
6. Risk residual có nằm trong thẩm quyền và appetite?
7. Có remediation plan, owner, expiry, triggers để revoke?
8. Liệu hoạt động tiếp tục sau expiry sẽ xử lý thế nào?

**Nếu được chấp thuận theo governance giả định**, F06 vẫn là **CONFIRMED_OPEN_WITH_APPROVED_EXCEPTION**, không trở thành VERIFIED_CLOSED. Ghi separate fields:

- **Finding/control status:** OPEN / condition chưa đạt.
- **Risk decision status:** APPROVED_CONDITIONAL hoặc ACTIVE_APPROVED với hiệu lực.
- **Expiry:** timestamp có timezone.
- **Monitoring:** host/network/crypto config, threat signals, review cadence.
- **Exit criteria:** TLS updated và tests/compatibility đạt.

### 12.2. Mẫu quyết định

~~~yaml
exception:
  id: "EXC-F06-2026-01"
  finding_id: "F06"
  asset_id: "A06"
  deviation: "Legacy TLS condition remains pending server upgrade"
  scope: "legacy-report production portal behind approved access boundary"
  risk_assessment: "RISK-F06-01"
  requested_duration_days: 14
  compensating_controls:
    - "Effective VPN/network allowlist tested"
    - "Auth and source-health monitoring enabled"
  authority:
    risk_owner: "legacy-service-risk-owner"
    approval_policy: "local-delegation-of-authority"
  decision:
    status: "PENDING_APPROVAL"
    rationale: null
    approved_at_utc: null
    expires_at_utc: null
  remediation: "Upgrade server and retest TLS config by agreed deadline"
  revocation_triggers:
    - "Exposure changes or bypass detected"
    - "Control failure, incident or expiry"
~~~

**PENDING_APPROVAL là chưa được chấp thuận.** Không tự gán ACTIVE cho template này. Trong phần kết quả dự án, có thể giả định đã được risk owner đúng thẩm quyền duyệt sau khi toàn bộ conditions được xác minh, nhưng đó phải là **một decision version mới**, không sửa lịch sử template rồi xóa bước review.

## 13. Pha 6 — Triển khai remediation qua change/release assurance

### 13.1. Vì sao sửa vulnerability cũng có thể tạo risk mới?

- Nâng thư viện có thể gây lỗi parsing, backward compatibility.
- Thu hẹp IAM có thể làm CI/CD không còn triển khai được.
- Thay ingress DB có thể làm monitoring/backup không truy cập được.
- Patch logging collector có thể đổi schema và tắt detection.
- Rotate/revoke key có thể khiến backups cũ không thể decrypt.
- Fix authz có thể chặn workflow hợp lệ nếu rule quá rộng.
- Nâng TLS có thể làm clients cũ mất kết nối.

Vì vậy remediation cần có **pre-change impact analysis, approval, rollout plan, monitoring, rollback hoặc forward-fix và post-change verification**.

### 13.2. Checklist trước thay đổi

1. Xác định **effective vulnerable state** và phạm vi affected instances.
2. Ghi expected state và source fix advisory/digest/version.
3. Kiểm tra baseline: logs, service SLIs, auth tests, backups và dependencies.
4. Chuẩn bị artifact bất biến hoặc commit được review.
5. Rà soát thay đổi IAM, data flow, privacy, contract và recovery.
6. Có positive/negative/failure tests tương ứng với finding.
7. Chọn canary/batch và điều kiện stop/rollback.
8. Có on-call, owner và phương án incident escalation.
9. Chốt provenance/evidence contract và thử khả năng đọc source logs.
10. Không để remediation ticket tự đóng khi CI job trả SUCCESS.

### 13.3. Trường hợp F07: patch logging collector

Một bản vá trên A07 có thể giải quyết vulnerability nhưng làm mất critical audit events. Bắt buộc test:

- Package version và process thực đã nạp build mới.
- Agent/collector vẫn healthy và có least-privilege permissions.
- Nguồn logs từ A01/A02 và các nguồn Critical khác đủ theo inventory.
- Raw event → normalized fields → detection rule → alert/case.
- Không có backlog, drop, duplicate vượt điều kiện.
- Source-health cảnh báo khi collector hoặc parser lỗi.
- Có fallback/rollback plan không làm mất dữ liệu lịch sử.

**Finding F07 chỉ đóng sau khi xác minh cả vulnerability fixed và khả năng detection/assurance quan trọng không suy giảm.**

## 14. Pha 7 — Retest và kiểm chứng hiệu lực thực tế

### 14.1. Retest không đồng nghĩa quét lại một lần

Một scanner trở về “không thấy” có thể do:

- Credential bị thu hồi hoặc scan target không reachable.
- Package được cập nhật nhưng process chưa restart.
- Container image mới trong registry nhưng pods vẫn chạy digest cũ.
- Network route thay khiến scanner không vào được, vulnerability còn.
- Rule plugin bị disable hoặc scanner khác tiêu chí.
- Asset bị đổi hostname/ID nên không còn match.
- Dữ liệu test không đi đúng authz/data path.
- Source monitoring lỗi làm control gap bị ẩn.

Phải phân biệt **“condition fixed”** và **“not observed because assessment coverage insufficient”**.

### 14.2. Retest contract

Một retest record phải có:

| Trường | Nội dung |
|---|---|
| **Finding ID / version** | Canonical finding, asset, path và rule/criterion. |
| **Before state** | Vấn đề đã xác minh, source/timestamp. |
| **Expected state** | Phiên bản/config/behavior sau fix. |
| **Scope** | Tất cả affected assets, pods, accounts, regions và trust boundaries. |
| **Methods** | Effective package/config check, authorized positive/negative tests, scan. |
| **Evidence quality** | Tool/run/version, permissions, source health, sampling, time. |
| **Function/regression checks** | Các luồng hợp lệ và phụ thuộc quan trọng vẫn hoạt động. |
| **Result** | PASS/FAIL/INCONCLUSIVE/PARTIAL và giới hạn. |
| **Reviewer** | Người có thẩm quyền và review timestamp. |
| **Finding transition** | VERIFIED_CLOSED, OPEN, PENDING_RETEST, REOPENED tùy kết quả. |

### 14.3. Mẫu retest F05

~~~yaml
retest:
  id: "RET-F05-01"
  finding_id: "F05"
  asset_id: "A05"
  deployed_change_id: "CHG-2026-005"
  assessment_at_utc: "2026-11-29T07:00:00Z"
  expected:
    - "Deployment-only identity permission"
    - "Unauthorized admin operation denied"
    - "Revoked token cannot authenticate"
    - "Audit event contains actor, target and outcome"
  observed:
    required_deploy_operation: "PASS"
    admin_denied_negative_test: "PASS"
    old_token_revocation: "PASS"
    audit_delivery_test: "PASS"
  source_health: "VERIFIED"
  population: "All CI runner identities affected by finding F05"
  evidence_refs: ["EV-IAM-501", "EV-NEG-502", "EV-REV-503", "EV-LOG-504"]
  verdict: "SUPPORTED_IN_SCOPE"
  reviewer: "security-assurance"
  finding_transition: "VERIFIED_CLOSED"
~~~

Mẫu này chỉ dùng **giá trị status giả định**. Trong hệ thống thật, các evidence refs phải trỏ tới records tồn tại, còn hiệu lực, đúng scope; nếu không, verdict là INCONCLUSIVE.

### 14.4. Quy tắc đóng, mở lại và exception

- **VERIFIED_CLOSED:** root condition không còn trong scope, test phù hợp đạt, evidence đủ, reviewer xác nhận.
- **OPEN:** finding confirmed còn tồn tại, kể cả khi đã có mitigation hoặc exception.
- **PENDING_RETEST:** fix đã deploy nhưng evidence kiểm chứng chưa có/không đủ.
- **REOPENED:** control/vulnerability xuất hiện lại hoặc retest cho thấy fail sau closure, cần lịch sử rõ.
- **FALSE_POSITIVE_CLOSED:** chỉ khi có proof phủ định finding theo scope, không phải vì deadline.
- **DUPLICATE_LINKED:** không tự tính thành fixed finding; parent/affected instance vẫn được theo dõi.

Một finding có thể bị đánh giá sai ban đầu; reclassification cần **reason và immutable history**, không xóa kết quả cũ khỏi evidence trail.

## 15. Pha 8 — Xác nhận kết quả và báo cáo theo thời gian

### 15.1. Ví dụ trạng thái kết thúc vòng đầu

Giả sử sau một vòng xử lý, nhóm đã:

- Retest đạt **F02**, **F05** và **F07**.
- **F01** được giảm exposure bằng network constraint nhưng package chưa vá.
- **F03** và **F09** vẫn đang lên kế hoạch khắc phục.
- **F06** có decision chấp thuận rủi ro có hạn sau review hợp lệ, condition vẫn tồn tại.
- **F10** đang chờ nâng dependency dev.
- **F04** và **F12** chưa đủ bằng chứng validation.
- **F08** có proof false positive và **F11** được gắn duplicate_of F01.

Bảng trạng thái:

| Finding | Validation | Treatment/closure | Bằng chứng cần hiển thị |
|---|---|---|---|
| F01 | CONFIRMED | OPEN, mitigation đang áp dụng. | Vulnerable build còn, effective network restriction, patch plan. |
| F02 | CONFIRMED | **VERIFIED_CLOSED**. | Authz negative tests, route coverage, release digest. |
| F03 | CONFIRMED | OPEN. | Network effective policy và planned change. |
| F04 | PENDING_VALIDATION | OPEN_TRIAGE. | SBOM/runtime reachability pending. |
| F05 | CONFIRMED | **VERIFIED_CLOSED**. | Least privilege effective state, revoke and tests. |
| F06 | CONFIRMED | OPEN_WITH_EXCEPTION. | DoA decision, expiry, VPN/monitoring test, plan. |
| F07 | CONFIRMED | **VERIFIED_CLOSED**. | Patch/runtime, log canary/detection tests. |
| F08 | FALSE_POSITIVE | CLOSED_AS_FP. | Vendor patch provenance, package build. |
| F09 | CONFIRMED | OPEN. | KMS grants, restore dependency plan. |
| F10 | CONFIRMED | OPEN. | Dev dependency upgrade plan. |
| F11 | DUPLICATE | LINKED_TO_F01. | Parent ID, dedup rationale. |
| F12 | PENDING_VALIDATION | OPEN_TRIAGE. | Admin path and effective auth evidence missing. |

### 15.2. Tính metrics của vòng đầu

Từ **8 findings confirmed**, có **3 verified closed**:

\[
\text{Verified remediation closure rate}
=\frac{3}{8}\times100\% = 37.5\%
\]

Có **5/8 = 62,5% confirmed vẫn open**, gồm F01, F03, F06, F09 và F10. F06 có ngoại lệ không biến nó thành closed.

**12 raw records** không phải mẫu số của remediation closure: 1 duplicate, 1 false positive và 2 pending validation có semantics khác.

Chương trình vẫn phải báo **2 pending validation** riêng; nếu chỉ báo “đã đóng 3 trong 8” mà không nói 2 unknowns, kết luận có thể bị hiểu sai.

### 15.3. Trạng thái xử lý không thay thế risk trend

Việc F02 được fix tốt hơn F10 chưa fix có thể giảm risk nghiêm trọng ngay cả khi tỷ lệ đóng còn thấp. Ngược lại, một dashboard có 90% tickets closed nhưng còn F01 trên internet gateway phải hiển thị **critical residual exposure**.

Một báo cáo hiệu quả nên nêu:

- Critical/high open findings và attack-path impacts.
- Confirmed vs pending vs false positives/duplicates.
- Exposure đã giảm bằng biện pháp nào, có evidence và expiry không.
- Findings đã được retest và những nơi unknown.
- SLA/overdue tính theo ngày và theo risk.
- Quyết định risk owner cần thực hiện, chủ sở hữu và hành động tiếp theo.

## 16. SLA, tuổi finding và cách báo cáo những mốc chưa đạt

### 16.1. Cần định nghĩa nhiều mốc thời gian khác nhau

Một finding có thể có:

- **first_seen_at:** thời điểm nguồn đầu tiên quan sát điều kiện, có thể khác thời điểm bắt đầu tồn tại thực tế.
- **detected_at:** thời điểm vulnerability program nhận dữ liệu.
- **validated_at:** thời điểm được xác minh thành confirmed.
- **triaged_at:** thời điểm priority/risk được quyết định.
- **assigned_at:** thời điểm owner nhận công việc.
- **containment_at:** thời điểm giảm exposure khi rủi ro cần xử lý ngay.
- **fix_deployed_at:** thời điểm thay đổi được áp vào hệ thống.
- **retest_at:** thời điểm reviewer xác minh effective state và criterion.
- **verified_closed_at:** thời điểm finding được đóng có bằng chứng.
- **exception_approved_at / expires_at:** mốc quyết định chấp nhận residual risk.

**SLA clock** phải có nguồn policy và trạng thái được định nghĩa: bắt đầu từ first_seen, validated hay risk-accepted time? Có tạm dừng khi chờ vendor, không có maintenance window hay không? Ai có quyền thay đổi priority/deadline?

Không có một quy tắc thời gian chung cho mọi tổ chức. Trong lab, chọn **confirmed_at** làm mốc giả định của SLA remediation, nhưng vẫn ghi **first_seen_at** để đánh giá thời gian phơi nhiễm trước triage. Với P0, mục tiêu containment được xử lý riêng và nhanh hơn thời hạn full remediation.

### 16.2. Ví dụ tính deadline

Giả sử một P1 được xác nhận lúc **2026-11-28T00:00:00Z**, policy nội bộ giả định cho **7 ngày** để khắc phục:

- Deadline P1: **2026-12-05T00:00:00Z**.
- Deadline P2 nếu 30 ngày: **2026-12-28T00:00:00Z**.
- Deadline P3 nếu 90 ngày: **2027-02-26T00:00:00Z**.
- Với P0, mục tiêu containment **24 giờ** từ cùng mốc: **2026-11-29T00:00:00Z**, nhưng không suy rằng mọi fix hoàn chỉnh đều phải xong đúng thời điểm này nếu policy chia các loại mốc.

Giả sử F05 hoàn tất retest ngày **2026-11-29T07:00:00Z**. Nếu deadline được đặt cho **full remediation 24 giờ**, retest này quá 7 giờ, trừ khi chính sách có điều kiện khác; nếu đó chỉ là deadline **containment**, phải kiểm tra thời điểm kiểm soát tạm được thực thi, **không dùng retest time để suy ra containment**.

### 16.3. Các loại overdue và aging

| Chỉ số | Công thức ý nghĩa | Lưu ý |
|---|---|---|
| **Finding age** | Từ mốc bắt đầu đã công bố tới thời điểm báo cáo/verified close. | Một issue có thể tồn tại trước khi được quan sát. |
| **Time to triage** | validated_at - detected_at. | Không tính các finding chưa có validated_at như 0. |
| **Time to containment** | containment_at - confirmed_at, theo chính sách. | Containment không có nghĩa issue đã fixed. |
| **Time to verified remediation** | verified_closed_at - mốc quy định. | Dùng timestamp của retest/approval, không ticket Done. |
| **Overdue count** | Số confirmed open vượt deadline hợp lệ. | Ngoại lệ không tự xóa finding; vẫn báo risk aging. |
| **High-risk exposure duration** | Khoảng rủi ro còn ảnh hưởng theo các observation/evidence windows. | Không biết thời điểm bắt đầu thì ghi uncertainty. |

### 16.4. Thay priority không phải xóa lịch sử

Nếu F03 từ P1 được đánh giá lại thành P2 sau khi kiểm chứng effective network isolation:

1. Lưu **old priority, new priority, changed_at, reviewer và rationale**.
2. Đính kèm test của controls bù trừ.
3. Xem policy có cho phép chỉnh SLA từ mốc mới không.
4. Báo cáo số ngày issue đã ở trạng thái P1 trước thay đổi.
5. Nếu controls mất hiệu lực, trigger re-triage ngay.

Không chỉnh sửa trường first_seen/confirmed_time hoặc priority history để làm mất overdue cũ.

## 17. Evidence-first: chứng minh từng bước của vulnerability cycle

### 17.1. Evidence không phải chỉ là ảnh scanner

Một hồ sơ tốt cho finding F05 có thể gồm:

| Claim | Phương pháp | Evidence phù hợp |
|---|---|---|
| **Finding existed** | Xem effective IAM permissions của runner. | IAM export có version, principal ID, timestamp, query. |
| **Risk đáng ưu tiên** | Đánh giá deployment scope, business criticality, credential paths. | CI/CD architecture, risk assessment và inventory. |
| **Treatment authorized** | Xác minh change/request và người phê duyệt. | CR, approver/DoA record, risk decision. |
| **Fix deployed** | Xem effective permission của principal đang thực sự được dùng. | Runtime IAM policy/trust, deployment identity mapping. |
| **Control works** | Test hành vi cần quyền và hành vi ngoài quyền. | Positive/negative tests, audit trail, no side effects. |
| **Old credential revoked** | Kiểm tra trạng thái/lifecycle theo cơ chế được ủy quyền. | Revocation event, credential ID metadata, denied auth test. |
| **Detection retained** | Tạo sự kiện có kiểm soát và theo dõi đến case nếu yêu cầu. | Raw audit, rule version, case delivery timestamps. |
| **Closure valid** | Independent reviewer kết luận theo criterion. | Retest result, reviewer decision và evidence index. |

**Một bản vá hoặc policy mới chỉ chứng minh một phần treatment**. Muốn bảo đảm closure, cần actual state và behavior, source health, đúng phạm vi, các assumptions/limitations.

### 17.2. Chuỗi Claim–Argument–Evidence

~~~mermaid
flowchart TD
    G0["G0: Vulnerability cycle quản lý đúng các findings ưu tiên trong scope"]
    S["Strategy: population + correctness + risk + treatment + verified closure"]
    G1["G1: Asset and finding population có thể đối chiếu"]
    G2["G2: Validation/priority phản ánh evidence và risk"]
    G3["G3: Treatment decisions có owner/approval/deadline"]
    G4["G4: Changes/controls đạt tiêu chí và không gây regression trọng yếu"]
    G5["G5: Closure/reopen có retest & history đáng tin"]
    E1["Inventory reconciliation + source/scan health"]
    E2["Raw scans, advisory, runtime proof, risk assessment"]
    E3["Tickets, exceptions, change approvals"]
    E4["Effective state, positive/negative/recovery tests"]
    E5["Retest evidence, reviewer, state transition audit"]
    G0 --> S
    S --> G1
    S --> G2
    S --> G3
    S --> G4
    S --> G5
    G1 --> E1
    G2 --> E2
    G3 --> E3
    G4 --> E4
    G5 --> E5
~~~

**Warrant:** Khi population và nguồn có độ tin cậy phù hợp, findings được phân loại chính xác, risk quyết định treatment đúng thẩm quyền, fixes được thực thi an toàn và kiểm tra lại có bằng chứng, tổ chức có cơ sở khẳng định vulnerability cycle **được thực hiện có kiểm soát trong phạm vi đã xác định**.

Kết luận ấy **không chứng minh không còn lỗ hổng chưa phát hiện** hoặc hệ thống an toàn tuyệt đối.

### 17.3. Defeaters: điều có thể khiến claim bị bác bỏ

- Scanner bỏ một account/region hoặc không có quyền đọc packages.
- Asset ID trùng khiến việc dedup gộp hai tài sản khác nhau.
- Vendor advisory không áp dụng với build đã patch/backport.
- “Unreachable” chỉ đúng từ mạng scanner, còn đường khác vẫn mở.
- Fix hiện diện trong image registry nhưng runtime chưa nạp.
- Negative authz test đi qua UI thay vì endpoint API trực tiếp cần bảo vệ.
- Security logging mất event khi patch collector.
- Approved exception hết hạn nhưng dashboard vẫn coi risk accepted.
- Retest trên staging không giống production trong khi claim là production.
- Ticket được đóng tự động khi scanner không có response.
- Một incident mới thay đổi exploitability nhưng risk priority không được cập nhật.

**Assurance càng mạnh khi chủ động thử tìm những defeaters quan trọng**, không chỉ gom bằng chứng ủng hộ kết luận mong muốn.

## 18. Evidence index và bảo toàn lịch sử

### 18.1. Evidence metadata contract

Mỗi evidence record cần có:

- **Evidence ID**, finding ID, asset/control/requirement ID.
- **Source type:** scanner, cloud API, SBOM, CI artifact, log, ticket, test.
- **Collection method, tool version, rule/query ID** và permissions được sử dụng.
- **Observed_at, collected_at, reviewed_at** với timezone nhất quán.
- **Population và scope:** region, cluster, workload, image digest, principal.
- **Expected vs actual** và test run ID khi là behavioral evidence.
- **Coverage/source-health**, lỗi, sampling, pagination và unknowns.
- **Provenance/integrity**, transformation và khả năng truy vết về raw record.
- **Access classification/retention**, redaction và người được xem.
- **Linked decision, finding status, reviewer, exceptions/retest**.

### 18.2. Cấu trúc evidence package giả định

~~~text
vulnerability-cycle/2026-11-orderbridge/
  scope/
    assets-and-criticality.csv
    source-coverage.md
    policy-and-sla-versions.md
  discovery/
    raw-findings.csv
    scan-run-metadata.md
    scanner-health-and-gaps.csv
  triage/
    canonical-findings.csv
    validation-evidence-index.csv
    contextual-risk-decisions.md
    false-positive-and-duplicate-records.md
  treatment/
    remediation-plan.csv
    change-approvals.md
    risk-exception-register.md
  validation/
    effective-state-before-after.md
    authorized-security-tests.json
    rollback-and-source-health.md
    retest-decisions.csv
  reporting/
    metrics-and-denominators.md
    critical-gaps-and-actions.md
    assurance-claim-and-limitations.md
    reviewer-signoff.md
~~~

Đây là **cấu trúc tham khảo**, không phải yêu cầu tạo các tệp mới trong bài học. Evidence có thể được giữ tại hệ thống GRC/ticket/SIEM và nối bằng links an toàn. **Không copy credentials hoặc raw PII vào repository để làm minh chứng.**

### 18.3. Khi nào evidence cũ không còn hiệu lực?

- Artifact, dependency hoặc runtime version thay.
- Asset chuyển network exposure, region, tenant hoặc business criticality.
- Scanner rule hoặc vendor advisory thay applicability.
- IAM trust/roles/service principal bị đổi.
- Monitoring source/parser bị thay và không còn khả năng đọc lịch sử.
- Mitigation như firewall/allowlist bị tắt hoặc drift.
- Exception hết hạn.
- Risk scenario có exploitation/incident signal mới.

**Thời hạn validity phải theo control và tốc độ thay đổi**, không thể đặt tất cả finding evidence chung một hạn tùy ý.

## 19. Những finding khó: xử lý đúng thay vì ép thành PASS/FAIL

### 19.1. Transitive dependency có trong SBOM nhưng chưa reachable (F04)

Bài tập yêu cầu:

1. Xác định artifact digest và dependency tree.
2. Xem affected version range theo advisory đáng tin.
3. Đối chiếu build/runtime được triển khai, không chỉ lockfile dev.
4. Xem feature/function bị ảnh hưởng có được enable và gọi không.
5. Xem các controls làm giảm attack path và nguồn evidence.
6. Quyết định confirmed/potential/not applicable theo quy tắc.
7. Nếu còn uncertainty có tác động lớn, giữ **PENDING_VALIDATION** và deadline/owner.
8. Nếu patch an toàn và khả thi, có thể chọn remediation sớm ngay khi validation chưa hoàn tất; vẫn ghi rõ lý do.

**Không thể suy từ “không có đường reachable thấy được” sang “không có vulnerability”** nếu kiểm tra chưa đủ hoặc không có instrumentation phù hợp.

### 19.2. Vendor backport (F08)

Một upstream version string có thể nằm trong danh sách vulnerable nhưng downstream vendor đã áp security fix mà không đổi major/minor version theo cách scanner dự kiến.

Để kết luận false positive:

- Vendor documentation xác nhận fix cho **exact package/build**.
- Installed package identity/build thực khớp.
- Runtime đang sử dụng build đó.
- Ngữ cảnh affected code/feature phù hợp với fix.
- Reviewer lưu cả raw scan và rationale.
- Có trigger đánh giá lại khi image/package/base OS đổi.

Nếu thiếu một trong các bằng chứng trọng yếu, status có thể là **PENDING_VALIDATION**, không phải FP chỉ vì người vận hành nói “đã vá rồi”.

### 19.3. Network mitigation có thể bị bypass (F01/F03)

Giảm exposure bằng network rule đòi:

- Effective policy, không chỉ planned change.
- Source/destination scope và precedence.
- Đường alternate như proxy, service mesh, peering, admin routes.
- Authorized allow/deny tests với test fixtures phù hợp.
- Monitoring khi rule drift và alert logic.
- Ảnh hưởng tới chức năng/backup/logging của service.

**Network isolation không đồng nghĩa library đã được patch**, và các kết quả “không reachable từ scanner” không chứng minh tất cả attack paths đều bị chặn.

### 19.4. Backup/KMS permissions (F09)

Nếu cần thu hẹp key permissions:

- Kiểm tra principals có quyền decrypt/wrap/key administration.
- Phân biệt production, recovery và emergency roles.
- Review lịch sử dùng key khi có cơ sở điều tra.
- Lập phương án rollback/forward-fix có tính đến encrypted backups cũ.
- Kiểm tra **effective permission deny** đối với principal ngoài scope.
- Thực hiện authorized restore/decrypt test trong môi trường an toàn.
- Bảo đảm source audit/KMS logs và DR runbook còn hoạt động.
- Chỉ close finding khi least privilege và recovery objectives được chứng minh.

**Fix IAM nhưng làm mất khả năng restore** có thể tạo risk nghiêm trọng hơn finding cũ.

### 19.5. Application authorization bug (F02)

Nếu một test synthetic chứng minh route trả dữ liệu tenant khác:

1. Chặn hoặc giới hạn path theo thẩm quyền nếu có khả năng ảnh hưởng thật.
2. Điều tra **scope của các routes và data classes**, không dừng ở một test ID.
3. Cân nhắc IR khi có dấu hiệu access trái phép thực tế.
4. Sửa server-side object-level authorization với behavior deny đúng.
5. Chạy positive test cho người có quyền và negative test cho cross-tenant.
6. Kiểm tra export, batch, filter, cache hoặc alternate endpoints liên quan.
7. Xác minh audit có actor, target, resource, outcome.
8. Ghi limitation: test scope, identities, tenant fixtures và thời kỳ.
9. Retest sau deploy trên đúng release/region/route và có reviewer.
10. Đóng finding riêng; giữ incident/finding history nếu có hậu quả trước fix.

Không dùng test trái phép trên dữ liệu người dùng thật để tạo minh chứng.

## 20. Bộ test phát hiện lỗi của chính workflow vulnerability cycle

Chất lượng quy trình cần **negative tests**, giống như controls kỹ thuật.

| Test ID | Lỗi cố ý đưa vào dữ liệu lab | Kết quả mong đợi |
|---|---|---|
| **WF-01** | Bỏ A09 khỏi target list nhưng giữ trong authoritative inventory. | Assessment coverage giảm, không báo “0 findings” cho A09. |
| **WF-02** | Nhập F11 như finding độc lập dù trùng F01. | Dedup phát hiện hoặc reviewer tạo linkage. |
| **WF-03** | Đánh dấu F08 là FP mà không có vendor/build evidence. | Không cho verified FP closure. |
| **WF-04** | Đánh dấu F04 false positive chỉ vì chưa thấy reachable path. | Yêu cầu validation/risk review, giữ uncertainty. |
| **WF-05** | Chuyển F05 sang CLOSED sau khi change ticket Done nhưng test chưa chạy. | Workflow chặn, giữ PENDING_RETEST. |
| **WF-06** | F06 exception đã hết hạn nhưng finding được tính closed. | Không tính closure; tạo alert/escalation. |
| **WF-07** | Scanner mất quyền truy cập A01 và không thấy vulnerability. | Assessment status INCONCLUSIVE, không tự close F01. |
| **WF-08** | Fix F07 xong nhưng log canary không tới SIEM. | Không cấp acceptance, tạo/regress finding. |
| **WF-09** | F02 được fix trong region A nhưng region B còn route lỗi. | Không close global finding; ghi affected instance còn OPEN. |
| **WF-10** | Reopen F03 sau policy drift nhưng ghi đè ngày closure cũ. | Giữ transition history và ngày reopen. |
| **WF-11** | Risk analyst không có quyền chấp nhận P0 tự approve exception. | Chặn escalation sai quyền, kiểm tra DoA. |
| **WF-12** | Priority thay nhưng SLA report không giữ version lịch sử. | Data-quality finding, yêu cầu audit trail. |
| **WF-13** | Quét lại chỉ vào A01/A02 vì các tài sản còn lại offline. | Scope metrics hiển thị coverage thiếu, không suy hệ thống sạch. |
| **WF-14** | Dòng từ scanner có asset ID không khớp inventory. | UNKNOWN_ID queue, không tự drop. |
| **WF-15** | Một asset đã decommission nhưng vẫn đang có traffic. | Kiểm tra decommission evidence, chưa tự N/A. |

Các test trên **chỉ thay đổi dữ liệu/fixtures trong lab**. Không cố ý tắt monitoring, cấp quyền trái policy hoặc tạo lỗ hổng trong production.

## 21. Mini-lab xử lý dữ liệu và tính KPI bằng Python

Đoạn mã dưới đây là **ví dụ tự chứa, chỉ phân tích dữ liệu cố định trong bộ nhớ**, không quét mạng, không kết nối dịch vụ và không ghi file. Người học có thể sao chép vào môi trường Python phù hợp nếu muốn kiểm tra các phép tính.

~~~python
from collections import Counter
from csv import DictReader
from io import StringIO

dataset = """
finding_id,asset_id,validation,treatment
F01,A01,CONFIRMED,OPEN
F02,A02,CONFIRMED,VERIFIED_CLOSED
F03,A03,CONFIRMED,OPEN
F04,A04,PENDING_VALIDATION,OPEN_TRIAGE
F05,A05,CONFIRMED,VERIFIED_CLOSED
F06,A06,CONFIRMED,OPEN_WITH_EXCEPTION
F07,A07,CONFIRMED,VERIFIED_CLOSED
F08,A08,FALSE_POSITIVE,CLOSED_AS_FP
F09,A09,CONFIRMED,OPEN
F10,A10,CONFIRMED,OPEN
F11,A01,DUPLICATE,LINKED_TO_F01
F12,A07,PENDING_VALIDATION,OPEN_TRIAGE
""".strip()

rows = list(DictReader(StringIO(dataset)))
validation = Counter(row["validation"] for row in rows)
confirmed = [row for row in rows if row["validation"] == "CONFIRMED"]
verified_closed = [
    row for row in confirmed
    if row["treatment"] == "VERIFIED_CLOSED"
]
confirmed_open = [
    row for row in confirmed
    if row["treatment"] != "VERIFIED_CLOSED"
]
pending = [
    row for row in rows
    if row["validation"] == "PENDING_VALIDATION"
]

assert len(rows) == 12
assert validation == {
    "CONFIRMED": 8,
    "PENDING_VALIDATION": 2,
    "FALSE_POSITIVE": 1,
    "DUPLICATE": 1,
}
assert len(verified_closed) == 3
assert len(confirmed_open) == 5

rate = 100 * len(verified_closed) / len(confirmed)
print(f"Raw records: {len(rows)}")
print(f"Confirmed: {len(confirmed)}")
print(f"Verified closed: {len(verified_closed)}")
print(f"Confirmed open: {len(confirmed_open)}")
print(f"Pending validation: {len(pending)}")
print(f"Verified closure rate: {rate:.1f}%")

# Expected:
# Raw records: 12
# Confirmed: 8
# Verified closed: 3
# Confirmed open: 5
# Pending validation: 2
# Verified closure rate: 37.5%
~~~

### 21.1. Giới hạn của đoạn mã

Mã trên **không** xác minh rằng các trạng thái được khai báo là đúng. Nó chỉ tính một metric từ **dữ liệu giả định đã được triage**.

Một hệ thống thật phải kiểm tra:

- Mỗi row có valid asset/canonical IDs, không bị đếm trùng.
- Kết luận FP, closure và exception có evidence và reviewer.
- Các thời điểm phù hợp với deadline.
- Phân biệt affected instances và canonical finding.
- Populations/scan coverage của các assets chưa có findings.
- Một status “VERIFIED_CLOSED” có thực sự có retest result đúng scope.
- Các record thay đổi qua các snapshot và audit history.

**Việc tính đúng phép chia không chứng minh dữ liệu đầu vào đáng tin.**

### 21.2. Mở rộng bài tập

Hãy thêm vào bộ dữ liệu:

- \`priority\`, \`first_seen_at\`, \`confirmed_at\`, \`due_at\`.
- \`exception_id\`, \`exception_expires_at\`, \`retest_id\`.
- \`source_health\`, \`asset_criticality\` và \`owner\`.

Sau đó tính:

1. Confirmed open P0/P1 counts.
2. Overdue open theo SLA source đã chọn.
3. Count của findings không có owner.
4. Percent verified closed trong **nhóm Critical assets**.
5. Exception expired count.
6. Findings có \`VERIFIED_CLOSED\` nhưng thiếu \`retest_id\` — một data-quality failure.

**Không tự gán missing timestamp = ngày hiện tại**: cần trạng thái UNKNOWN để tránh gian lận độ tuổi.

## 22. Báo cáo executive và dashboard thực hành

### 22.1. Phân tầng thông tin

**Lãnh đạo/risk owner** cần:

- Số confirmed P0/P1 còn OPEN theo business service/criticality.
- Những quyết định phải phê duyệt: dừng tính năng, tài nguyên sửa, risk acceptance.
- Thời gian phơi nhiễm và mitigation có tác dụng/đã test.
- Scan/evidence coverage và unknowns.
- Tình trạng remediation, deadline và sự cố liên quan.

**Engineering/SRE** cần:

- Asset/version/image, finding, fix source, dependencies.
- Change owner, rollout plan, test IDs, rollback.
- Những phần failed/stale, priority và cảnh báo source-health.
- Work queues và acceptance criteria để đóng.

**Auditor/assurance reviewer** cần:

- Policy, phạm vi, scan source và inventory reconciliation.
- Raw findings, canonical/dedup, validation rationale và evidence.
- Risk treatment decisions, approval authority/exception history.
- Effective state, retest, reviewer và status transitions.
- Known limitations, gaps, unresolved findings và source quality.

### 22.2. Dashboard mẫu

~~~text
ORDERBRIDGE — VULNERABILITY CYCLE — TRAINING DATA
Scope baseline T0: 2026-11-28T00:00:00Z
Treatment reporting T1 (giả định): 2026-11-30T00:00:00Z
Population: 10 inventoried assets (scope and freshness to verify)
Raw findings: 12

TRIAGE
  Confirmed:              8
  Pending validation:     2
  False positive:         1
  Duplicate:              1

TREATMENT OUTCOME (confirmed only)
  Verified closed:        3 / 8 = 37.5%
  Still open:             5 / 8 = 62.5%
  Open with exception:    1 / 8 (included among open)
  Open P0:                F01 (mitigated, not fixed)
  Other open:             F03, F06, F09, F10

ASSURANCE LIMITATIONS
  F04, F12 still pending validation
  Scan/source completeness needs independent inventory check
  Historical exposure/incident impact not yet fully evaluated
  Exceptions do not count as verified remediation

ACTION PRIORITIES
  F01: owner=edge-team; critical patch/containment, retest
  F03: owner=data-platform; narrow effective ingress rule
  F09: owner=dr-data; constrain key privileges, restore test
  F06: owner=business-apps; monitor exception expiry and TLS upgrade
  F10: owner=web-team; dev dependency update
~~~

**Trạng thái trên là kịch bản giả định sau một vòng treatment**. T0 là mốc scope/triage, còn T1 là thời điểm kết quả minh họa sau các retest. Khi báo cáo thật, mọi record VERIFIED_CLOSED phải có retest được xác minh **không muộn hơn T1**; nếu thiếu ngày hoặc evidence, giữ PENDING_RETEST/INCONCLUSIVE và không tính closed. Không dùng snapshot T0 để suy ra một fix diễn ra trước T0.

### 22.3. Mẫu executive narrative

> Trong vòng xử lý mô phỏng, 12 raw findings đã được chuẩn hóa thành 8 confirmed, 2 pending validation, 1 false positive và 1 duplicate. Ba trong tám confirmed có retest đủ bằng chứng để đóng; năm vẫn mở, gồm một điểm yếu ưu tiên khẩn tại public gateway hiện mới có mitigation. Một ngoại lệ legacy TLS được quản lý riêng về risk nhưng không tính là remediation. Hai findings chưa đủ validation evidence cần owner và thời hạn xác minh. Không có căn cứ để suy ra toàn bộ 10 assets “sạch vulnerability” vì population/scan quality và các attack paths ngoài kiểm tra còn có giới hạn. Ưu tiên là hoàn tất fix gateway, thu hẹp network/key permissions, theo dõi exception và đánh giá lại evidence sau các changes.

Một báo cáo tốt **nêu trách nhiệm và quyết định tiếp theo**, không chỉ tỷ lệ đã đóng.

## 23. Kết nối vulnerability cycle với các security controls

### 23.1. Control map trong dự án

| Control ID minh họa | Mục tiêu | Điểm liên quan | Evidence |
|---|---|---|---|
| **VM-INV-01** | Assets và exposure trong scope được phát hiện và gán owner. | Pha 0–1; A01–A10. | Authoritative inventory, source reconciliation. |
| **VM-DISC-02** | Scanning/advisory intake hợp lệ và có source health. | Pha 1; F01–F12. | Scan run metadata, scanner errors, coverage. |
| **VM-TRI-03** | Findings được validate/dedup, không xóa FP/unknown vô căn cứ. | Pha 2–4. | Canonical records, vendor/build proof, reviews. |
| **VM-RISK-04** | Priorities xét business impact, exposure và controls. | F01–F10. | Contextual risk matrix, approval. |
| **VM-TREAT-05** | Treatment có owner, deadline, governance và exceptions đúng quyền. | F01/F03/F06/F09. | Tickets, DoA, effective mitigation tests. |
| **VM-RETEST-06** | Closure phải có effective-state/behavioral retest. | F02/F05/F07. | Tests, deployment identity, signoff. |
| **VM-MON-07** | Findings tái xuất hiện/drift được phát hiện đúng lúc. | Mọi affected units. | Recurring checks, change-triggered assessments. |
| **VM-REPORT-08** | Báo cáo có mẫu số/giới hạn và critical open exposures. | Toàn chương trình. | Dashboard, evidence index, management decision. |

### 23.2. Phân biệt control effectiveness

- **VM-DISC-02 được thiết kế:** có quy trình và tool.
- **VM-DISC-02 triển khai:** tool quét một tập assets.
- **VM-DISC-02 vận hành hiệu quả:** tool có scan coverage đủ, intake đúng giờ, phát hiện/triage findings, missing-source alerts và không bỏ lỗ hổng quan trọng trong kỳ được xét.

Không nên gọi vulnerability program “effective” chỉ vì scanner tạo báo cáo hằng ngày.

### 23.3. Tối thiểu một assurance finding ngoài vulnerability

Bên cạnh vulnerabilities đã tìm thấy, có thể xuất hiện các **assurance process findings**:

- Không có owner cho A09.
- Scanner bỏ account mới.
- Audit pipeline không lưu trạng thái trích xuất.
- Exception phê duyệt thiếu quyền.
- Retest metadata không chỉ đúng release artifact.
- SLA dashboard chỉ tính records chưa dedup.
- Source health bị mất nhưng hệ thống tự đóng finding.

Các thiếu sót này ảnh hưởng tới **độ tin cậy của cả vulnerability cycle**, dù không phải CVE riêng.

## 24. Chu kỳ lặp: làm sao để finding không tái xuất hiện?

### 24.1. Các triggers bắt buộc đánh giá lại

1. **New assets/accounts/regions:** onboarding và inventory reconciliation.
2. **New software version/dependency:** SBOM/image/artifact assessment.
3. **New vulnerability advisory hoặc exploitation signal:** đối chiếu affected population.
4. **Critical patch/release:** xác nhận fix, kiểm tra regressions.
5. **IAM/network/key/config changes:** đánh giá risk và drift.
6. **Incident/near miss:** tìm các affected assets và attack paths tương tự.
7. **Exception expiry/revocation:** rủi ro có còn được chấp nhận hợp lệ?
8. **Vendor/integration change:** thay attack surface, data flows hoặc trách nhiệm.
9. **Scanner/source health failure:** đánh dấu unknown, mở data-quality finding.
10. **Decommission/transfer of service:** xác nhận asset thật sự không còn hoạt động, không xóa khỏi scope chỉ vì tool không thấy.

### 24.2. Schedule theo rủi ro

Một chương trình có thể kết hợp:

- **Continuous/event-driven:** vulnerability intelligence, new images, code/IaC releases, new IAM grants.
- **Frequent automated:** inventory reconciliation, scanner health, critical exposure/asset changes.
- **Periodic manual/independent:** risk context review, exception audit, closure sampling, recovery testing.
- **Post-incident:** rà soát design/monitoring và requirements liên quan.

Tần suất phải theo **policy, criticality, tốc độ thay đổi và nguồn điều kiện**; không có một lịch universal áp cho mọi hệ thống.

### 24.3. Avoid “audit-only vulnerability management”

Anti-pattern phổ biến:

- Quét dồn trước audit rồi bỏ phần còn lại của năm.
- Dùng scanner console làm toàn bộ inventory.
- Đóng findings khi scanner không còn thấy asset.
- Tính exception là fix.
- Đếm duplicate findings để khoe nhiều issues đã xử lý.
- Không bao giờ retest trên production effective state.
- Bỏ qua vulnerability của shared CI/CD hoặc backup keys.
- Không ghi trạng thái khẩn cấp khi có exploitation/incident signals.
- Không dùng historical age và source gaps trong báo cáo.

**Vulnerability cycle chỉ khép kín khi có bước tái đánh giá phù hợp rủi ro sau khi remediation và môi trường tiếp tục thay đổi.**

## 25. Kế hoạch thực hành theo sáu mốc

Để làm bài theo nhóm hoặc tự học, chia thành sáu milestone. Mỗi milestone có thể được hoàn thành trên dữ liệu giả trong chính tài liệu làm bài, không cần hệ thống production thật.

### Milestone A — Scope và khám phá

**Đầu vào:** kiến trúc OrderBridge, 10 assets, nguồn quét giả.

**Nhiệm vụ:**

- Xác định business/security objectives.
- Gán criticality, owner, exposure/data class cho A01–A10.
- Lập scanner/source coverage contract.
- Xác định assets có nguy cơ không được phát hiện và phương pháp đối chiếu.
- Chọn các fields tối thiểu của raw evidence.

**Bàn giao:** scope register, inventory matrix và source-health test plan.

**Acceptance:** không có “asset không owner” mà vẫn được coi verified scope; denominator rõ.

### Milestone B — Normalize và validate

**Đầu vào:** F01–F12.

**Nhiệm vụ:**

- Giữ nguyên raw records.
- Tạo canonical keys/duplicates.
- Xác minh F08 vendor backport; F11 duplicate.
- Phân biệt F04/F12 chưa đủ evidence.
- Viết rationale và validation evidence cho từng finding.

**Bàn giao:** normalized finding register và validation decisions.

**Acceptance:** đúng **8 confirmed, 2 pending, 1 FP, 1 duplicate**, có rationale và không tự xóa record.

### Milestone C — Risk và treatment

**Đầu vào:** tám confirmed + business context.

**Nhiệm vụ:**

- Đánh giá priority P0–P3 có source/rationale.
- Phân tích ảnh hưởng của F01/F02/F05/F09.
- Thiết kế remediation/mitigation cho mỗi finding.
- Tạo một exception request cho F06 nhưng không tự kích hoạt khi thiếu approvals.
- Xác định owners, SLA clock và hard escalation.

**Bàn giao:** risk-priority register, treatment plan, exception template.

**Acceptance:** critical/open exposures được ưu tiên; exception không được tính closed.

### Milestone D — Change và retest

**Đầu vào:** dự định fix F02/F05/F07.

**Nhiệm vụ:**

- Viết change plan và blast-radius/rollback analysis.
- Thiết kế positive/negative/security tests cho ba fixes.
- Mô phỏng effective-state evidence và source-health.
- Phân loại kết quả PASS/FAIL/INCONCLUSIVE.
- Đưa vào một failure fixture như F07 patch làm mất detection rồi yêu cầu rollback/fix.

**Bàn giao:** change records, test matrix, retest evidence và reviewer decisions.

**Acceptance:** chỉ F02/F05/F07 được VERIFIED_CLOSED khi evidence đủ.

### Milestone E — Metrics và audit

**Đầu vào:** kết quả sau treatment.

**Nhiệm vụ:**

- Tính confirmed, duplicate, FP, pending và closure rate.
- Tách trạng thái scan coverage và vulnerability coverage.
- Đánh giá time-to-triage, age/SLA theo giả định.
- Viết 1 trang executive report, 1 trang technical handoff.
- Chỉ ra ít nhất ba limitations/defeaters.

**Bàn giao:** metrics, assurance argument, evidence index.

**Acceptance:** phép tính 3/8 = 37,5%, còn 5 confirmed open và 2 pending được giải thích.

### Milestone F — Lặp chu kỳ với thay đổi mới

**Đầu vào:** thêm asset A11 trong inventory, F02 tái xuất hiện sau một change dù đã verified closed ở vòng trước, exception F06 gần hết hạn.

**Nhiệm vụ:**

- Giữ nguyên lịch sử T0, cập nhật population theo mốc T1.
- Tạo reassessment/reopen records cho F02, không ghi đè old closure.
- Trigger exception renewal/risk review cho F06.
- Xác định regression/security tests tự động và manual review tiếp theo.

**Bàn giao:** updated risk/register, change-triggered assessment, next-cycle plan.

**Acceptance:** denominator được version, không có approved exception vô thời hạn, không xóa finding history.

## 26. Rubric chấm bài (100 điểm)

| Hạng mục | Điểm tối đa | Tiêu chí |
|---|---:|---|
| **Scope, inventory và source health** | 15 | Scope rõ, owner/criticality và độ bao phủ nguồn có thể đối chiếu. |
| **Normalize, dedup, traceability** | 15 | Raw history giữ nguyên, IDs/fingerprint hợp lý, F11 không bị đếm trùng. |
| **Validation và false-positive quality** | 15 | F08 có vendor/build evidence, F04/F12 giữ pending đúng lý do. |
| **Contextual risk priority** | 15 | Không chỉ dựa scanner severity, có exposure/impact/unknown. |
| **Treatment, exception và change governance** | 15 | Actions, owner, SLA, DoA, mitigation vs fix, rollback. |
| **Retest, closure và evidence** | 15 | Effective state, authorized tests, source health, reviewer, no premature close. |
| **Metrics, report và continuous cycle** | 10 | Denominator đúng, critical gaps/limitations, triggers và bàn giao. |
| **Tổng** | **100** | Đánh giá cả kỹ năng phân tích và tính minh bạch của bằng chứng. |

### 26.1. Điều kiện không đạt dù nhiều tài liệu

Bài nộp cần được sửa trước khi coi hoàn thành nếu:

- Không có authoritative inventory và denominator.
- Xem pending findings là false positive mà không có evidence.
- Tính F11 duplicate thành một confirmed finding riêng.
- Cho F06 exception là verified closure.
- Đóng F02/F05/F07 không có retest method/source.
- Báo hệ thống “an toàn 100%” từ 3/8 closure.
- Không có owner cho confirmed Critical finding.
- Dùng một test có nguy cơ gây hại ngoài lab/authorization.

**Rubric đo năng lực bảo đảm dựa trên chứng cứ**, không thưởng cho việc tô xanh kết luận thiếu căn cứ.

## 27. Đáp án tham khảo và những điều có thể khác hợp lý

### 27.1. Đáp án định lượng

- **10 assets** trong authoritative inventory giả định.
- **12 raw findings**, trong đó **F11 trùng F01**.
- **8 confirmed:** F01, F02, F03, F05, F06, F07, F09, F10.
- **2 pending:** F04, F12.
- **1 FP:** F08, nếu vendor backport đã xác minh đầy đủ.
- **1 duplicate:** F11.
- **3 verified closed:** F02, F05, F07.
- **5 confirmed open:** F01, F03, F06, F09, F10.
- **1 open with exception:** F06, giả sử approval hợp lệ về authority/time/conditions.
- **Verified remediation closure:** 3/8 = **37,5%**.
- **Confirmed still open:** 5/8 = **62,5%**.
- **Pending validation:** 2/12 raw records, phải báo riêng thay vì gộp fixed.

### 27.2. Đáp án ưu tiên

- **P0:** F01, F02, F05.
- **P1:** F03, F07, F09.
- **P2:** F06.
- **P3:** F10.

Một học viên có thể đề xuất thứ tự khác nếu bổ sung **evidence hợp lý** về attack-path reachability, incident signals, data obligations hoặc compensating controls. **Không được tùy tiện hạ một confirmed unauthorized data access** chỉ vì patch khó triển khai.

### 27.3. Đáp án về trạng thái

- F01: mitigation có thể giảm exposure, finding vẫn **OPEN** tới khi fix/retest.
- F02: verified closed phải có coverage của routes, negative tests và backend results.
- F03: patch network cần effective-state connectivity tests và tránh làm hỏng dependencies.
- F04: pending tới khi có runtime/reachability evidence hoặc quyết định được hỗ trợ.
- F05: verify scoped IAM, old credential revoke, positive/negative permissions và audit.
- F06: exception có hạn và conditions, không phải control PASS.
- F07: verify cả package fix và event-to-case security telemetry.
- F08: FP phải có proof exact backported build/version.
- F09: effective key permission và restore/decrypt regression tests.
- F10: dev dependency still subject to normal remediation process.
- F11: duplicate liên kết F01, raw record vẫn lưu.
- F12: pending, không tự kết luận admin auth an toàn.

### 27.4. Một quyết định khó vẫn có thể hợp lệ

Ví dụ F09 là production backup key policy. Nhóm sửa quyền ngay có thể làm mất decrypt của các backup cũ. Một phương án phù hợp có thể là:

1. Chặn thêm quyền mới và kiểm soát hoạt động bất thường.
2. Xây least-privilege policy trên principals đã inventory.
3. Thử restore/decrypt an toàn theo dữ liệu mô phỏng hoặc exercise được phép.
4. Áp policy có staged rollout/rollback.
5. Retest quyền bị cấm và data recovery.
6. Chỉ đóng finding khi cả **least privilege** lẫn **recovery** đạt.

Điểm quan trọng là **quyết định theo mục tiêu bảo mật tổng thể**, không phải giảm số lượng findings bằng mọi giá.

## 28. Checklist tự kiểm tra trước khi nộp

### 28.1. Phạm vi và discovery

- [ ] Có mục tiêu bảo mật, dữ liệu và hệ thống trong scope.
- [ ] 10 assets có canonical IDs, owner, criticality và environment.
- [ ] Có nguồn inventory độc lập với các scanners.
- [ ] Scan run metadata, source health và unscanned assets được ghi.
- [ ] Các sources có limitation được nêu rõ, không coi silence là không có vulnerability.

### 28.2. Validation và risk

- [ ] 12 raw records còn nguyên liên kết nguồn.
- [ ] F11 duplicate_of F01 với rationale.
- [ ] F08 false positive có vendor build evidence.
- [ ] F04/F12 pending không bị xóa khỏi queue.
- [ ] Risk priority dựa exposure, impact, attack path, controls và uncertainty.
- [ ] Critical findings có owner và hard escalation.
- [ ] Không gọi CVSS/scanner severity là xác suất breach.

### 28.3. Treatment và governance

- [ ] Remediation/mitigation/risk acceptance được phân biệt.
- [ ] Có change ID, effective scope, acceptance criteria và rollback/forward-fix.
- [ ] F06 exception yêu cầu đúng approval, expiry, owner và controls bù trừ.
- [ ] Risk decision không xóa finding hoặc báo compliance PASS.
- [ ] Có incident escalation khi phát hiện dấu hiệu exploitation hay data exposure.
- [ ] Đã xem dependencies logging, IAM, DR và data integrity trước patch.

### 28.4. Retest và assurance

- [ ] F02/F05/F07 có retest trên đúng version, affected unit và criterion.
- [ ] Positive/negative tests đã được lên kế hoạch đúng thẩm quyền.
- [ ] Scanner “không thấy” nhưng source failed không được tính fixed.
- [ ] Evidence có provenance, UTC timestamps, query/tool/test IDs.
- [ ] Có reviewer signoff và history của finding transitions.
- [ ] Finding chỉ đóng khi security regression không còn trong scope đã xét.
- [ ] Các limitations và untested paths được công bố.

### 28.5. Reporting và lặp chu kỳ

- [ ] 8 confirmed, 2 pending, 1 FP và 1 duplicate được phân loại đúng.
- [ ] Closure 3/8 = 37,5% và confirmed open 5/8 = 62,5%.
- [ ] Có Critical open exposures và người chịu trách nhiệm trong executive report.
- [ ] Tách assessment coverage khỏi remediation closure rate.
- [ ] SLA/age có nguồn và thời gian nhất quán.
- [ ] KPI không coi exception là fixed.
- [ ] Có định nghĩa triggers cho new asset, release, advisory, incident và expiry.
- [ ] Có danh sách hành động cho vòng tiếp theo và evidence cần tạo.

## 29. Câu hỏi tự đánh giá

1. Vulnerability cycle khác gì việc chạy vulnerability scanner hằng tháng?
2. Vì sao phải xác định authoritative asset inventory trước khi dùng scanner reports?
3. Một scanner không trả findings cho A09 có thể có những nguyên nhân nào?
4. Phân biệt raw finding, canonical finding và affected instance record.
5. Vì sao F11 nên liên kết F01 mà không bị xóa khỏi raw history?
6. Khi nào một downstream package version trông cũ vẫn có thể không còn affected?
7. F04 trong SBOM nhưng chưa xác nhận runtime reachability nên có trạng thái gì?
8. Vì sao “chưa thấy đường khai thác” khác “đã vá vulnerability”?
9. CVSS/scanner score giúp ích ở đâu và thiếu những yếu tố contextual risk nào?
10. Vì sao credential của CI runner có thể rất rủi ro dù endpoint không public?
11. Khi nào cần chuyển finding sang incident response?
12. Remediation và mitigation khác nhau thế nào trong trường hợp F01?
13. Risk owner có thể biến control FAIL thành PASS bằng cách ký exception không?
14. Một ngoại lệ cần những trường và conditions nào để có thể audit?
15. Vì sao làm rõ rollback plan quan trọng khi sửa F09?
16. Patch logging collector F07 cần retest những khả năng nào ngoài package version?
17. “Ticket Done” khác “VERIFIED_CLOSED” ở điểm nào?
18. Vì sao scanner không thấy issue sau khi mất quyền truy cập là INCONCLUSIVE?
19. Làm sao phân biệt first_seen_at với confirmed_at và thời điểm vulnerability thật sự bắt đầu?
20. Nếu 8 confirmed, 3 verified closed, 2 pending, 1 FP và 1 duplicate, phải báo metrics thế nào?
21. Tại sao một chương trình có closure rate cao vẫn có thể có Critical residual risk?
22. Cần bằng chứng gì để đóng một finding authorization cross-tenant?
23. Source-health của detection/EDR ảnh hưởng ra sao đến assurance verdict?
24. Hãy viết một risk-to-control-to-evidence graph cho F05 hoặc F09.
25. Vì sao cần test negative behavior cho chính workflow quản lý findings?
26. Khi một asset mới phát sinh sau T0, làm sao bảo toàn khả năng so sánh giữa các kỳ?
27. Khi nào phải mở lại một finding và cần giữ những dấu vết lịch sử gì?
28. Vì sao một exception hết hạn là trigger quan trọng dù code không thay?
29. Tạo một executive summary 6 câu nêu rõ gap, unknown, owner và hành động.
30. Hãy chọn một finding bất kỳ và viết đầy đủ hồ sơ từ raw observation tới retest và closure.

## 30. Tổng kết: một vulnerability cycle tốt tạo ra quyết định được chứng minh

Bài thực hành đã đi qua toàn bộ vòng:

1. **Xác định scope và những gì phải được nhìn thấy.**
2. **Thu phát hiện từ các nguồn có kiểm soát chất lượng.**
3. **Giữ raw evidence, chuẩn hóa và phản biện false positives/duplicates.**
4. **Đánh giá rủi ro từ impact, exposure, attack path và control effectiveness.**
5. **Chọn treatment đúng thẩm quyền, có deadline và monitoring.**
6. **Sửa hoặc giảm rủi ro bằng change/release có rollback và business safety.**
7. **Retest effective state và behavior trước khi closure.**
8. **Báo cáo critical gaps, unknowns, SLA và residual risk trung thực.**
9. **Theo dõi new assets, vulnerability intelligence, incidents và drift để lặp vòng tiếp theo.**

**Điểm cốt lõi:** **Thực hiện vulnerability cycle không có nghĩa “quét được bao nhiêu lỗ hổng và đóng bao nhiêu ticket”.** Trong **SECURITY_SECURITY_ASSURANCE**, giá trị của chu trình nằm ở việc biết **tài sản nào cần bảo vệ, phát hiện nào có thật, rủi ro nào ưu tiên, xử lý nào đã được chứng minh hiệu lực và giới hạn bằng chứng nào còn tồn tại**. Chỉ khi từng bước có owner, criterion, source provenance, thẩm quyền, remediation và retest, kết luận về security assurance mới có thể kiểm toán, cải thiện liên tục và hỗ trợ quyết định trong vận hành thật.
