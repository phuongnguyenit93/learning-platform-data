# Đối chiếu edition, giấy phép, dịch vụ và chi phí theo phạm vi sử dụng

Một nhóm Java chuẩn bị chọn cơ sở dữ liệu NoSQL cho nền tảng quản lý đặt phòng. Họ thử hai sản phẩm: một engine có bản Community tải về miễn phí và một dịch vụ managed tính tiền theo request. Demo với 10.000 documents đều chạy tốt. Nhóm kết luận bản Community “không tốn phí” nên sẽ rẻ hơn, còn managed “không cần vận hành” nên chỉ cần xem giá mỗi triệu requests. Sáu tháng sau, hệ thống cần audit theo tenant, sao lưu point-in-time, triển khai nhiều vùng, hỗ trợ trực sự cố, tìm kiếm theo chỉ mục mới và lưu dữ liệu tại khu vực được phép. Một số tính năng đòi edition khác; chi phí máy, người vận hành, băng thông, chỉ mục và khôi phục tăng; đồng thời nhóm mới phát hiện giấy phép bản nguồn không cho phép sử dụng theo cách họ định cung cấp dịch vụ mà không tuân thủ thêm điều kiện.

Vấn đề không nằm ở việc “NoSQL nào tốt nhất” mà ở chỗ **cùng một tên sản phẩm có thể có nhiều edition, loại giấy phép, gói dịch vụ và đơn vị tính phí**, và ý nghĩa của chúng thay đổi theo **phạm vi sử dụng cụ thể**.

Bài học thuộc chương **Đánh giá và lựa chọn** của module **Database No SQL**. Mục tiêu là biết xây dựng một bảng so sánh đủ chính xác để quyết định giữa engine tự vận hành, bản thương mại, dịch vụ managed hoặc mô hình kết hợp; tránh nhầm phần mềm “không có phí giấy phép” với hệ thống “không có chi phí”; kiểm tra nghĩa vụ giấy phép trước khi triển khai; và tính **total cost of ownership (TCO)** bằng workload, capacity, yêu cầu nghiệp vụ và rủi ro vận hành thực tế.

> **Nguyên tắc:** So sánh luôn phải gắn với **tên sản phẩm + phiên bản + edition + cách triển khai + khu vực + gói dịch vụ + phạm vi sử dụng + thời điểm báo giá**. Không lấy một logo, một trang giá hay cụm từ “open source” để suy tất cả những thứ đó.

## 1. Bốn câu hỏi phải tách biệt

| Trục đánh giá | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Edition** | Bản nào có tính năng và giới hạn nào? | Community, Enterprise, Developer, cloud tier |
| **Giấy phép** | Ta được làm gì với phần mềm và phải tuân thủ gì? | Apache/MIT, GPL/AGPL, SSPL, BSL, commercial |
| **Dịch vụ** | Ai vận hành, hỗ trợ, backup, upgrade, xử lý sự cố? | Self-managed, managed, support contract |
| **Chi phí** | Trả tiền cho đơn vị nào và bao nhiêu trong workload thật? | Node/core, request/RU, GB-month, backup, egress |

### 1.1. Edition không đồng nghĩa giấy phép

Một bản Community có thể có license ràng buộc riêng; một bản Enterprise có thể dùng commercial agreement; dịch vụ managed có thể vận hành engine đó mà khách hàng chỉ giao kết **service agreement**, không nhận quyền phân phối binary.

### 1.2. “Miễn phí tải về” không đồng nghĩa “mã nguồn mở”

Có phần mềm được xem mã nguồn nhưng giới hạn kiểu sử dụng, cung cấp dịch vụ hoặc phân phối. Phải đọc license và xác nhận có thỏa định nghĩa open source được công nhận hay không, thay vì chỉ dựa ngôn ngữ marketing.

### 1.3. “Managed” không đồng nghĩa không còn trách nhiệm vận hành

Nhà cung cấp có thể chịu trách nhiệm phần host, patching và replica repair; đội ứng dụng vẫn phải chọn key/index/consistency, giám sát chi phí, thiết kế backup/restore, quản lý dữ liệu và bảo vệ quyền truy cập.

### 1.4. Giá phần mềm là một phần nhỏ của TCO

Self-managed có thể không có licensing fee nhưng vẫn cần machines, storage, network, backups, monitoring, security, on-call và kỹ năng chuyên môn. Managed tính phí dịch vụ nhưng có thể giảm đáng kể công sức này.

## 2. Phạm vi sử dụng là điểm khởi đầu

Trước khi so giá, mô tả một cách triển khai:

~~~yaml
useCase: "multi-tenant-booking"
environment: "production"
deployment: "managed-or-self-hosted"
region: "<approved-location>"
workload:
  peakReadRequestsPerSecond: "<measured>"
  peakWriteRequestsPerSecond: "<measured>"
  queryPatterns: ["lookup", "tenant-time-range", "conditional-reservation"]
  documentSizeDistribution: "<p50-p95-p99>"
data:
  logicalSize: "<GB>"
  yearlyGrowth: "<percent>"
  retention: "<months>"
requirements:
  availabilitySLO: "<target>"
  recoveryPointObjective: "<target>"
  recoveryTimeObjective: "<target>"
  tenantIsolation: "required"
  audit: "required"
  dataResidency: "<allowed regions>"
  supportHours: "<coverage>"
distribution:
  deliverSoftwareToCustomers: false
  offerDatabaseAsAServiceToThirdParties: false
~~~

### 2.1. Dùng cho ứng dụng nội bộ

Một công ty chạy NoSQL phía sau ứng dụng nội bộ có thể có nghĩa vụ giấy phép khác công ty phát hành appliance chứa binary database hoặc bán dịch vụ database cho khách hàng. Phải diễn tả **hành vi thực** chứ không chỉ tên hệ thống.

### 2.2. Bán SaaS dùng database làm thành phần

SaaS lưu dữ liệu cho một ứng dụng nghiệp vụ không tự động giống một dịch vụ bán chính bản thân chức năng database. Tuy nhiên, với một số giấy phép theo network/service, ranh giới này rất quan trọng và cần pháp chế rà soát.

### 2.3. Nhúng engine trong sản phẩm phân phối

Đưa database binary, image hoặc thư viện vào thiết bị/app khách hàng nhận có thể kích hoạt điều khoản phân phối, notice và cung cấp source. Không suy điều kiện từ trường hợp chỉ chạy trên server nội bộ.

### 2.4. Dùng cho demo, giáo dục và production

Developer/free tier có thể hạn chế quy mô, tính năng hoặc mục đích dùng. Một POC chạy hợp lệ trong trial không chứng minh quyền dùng tương tự ở production.

### 2.5. Dữ liệu nhạy cảm và residency

Giá rẻ không còn là lựa chọn nếu storage/backup/telemetry chuyển dữ liệu ra khu vực bị cấm hoặc không có control cần cho hợp đồng.

## 3. Lập bản đồ các lựa chọn triển khai

~~~mermaid
flowchart TD
    APP["Java service với workload và SLO"] --> CHOICE{"Kiểu triển khai?"}
    CHOICE --> SELF["Self-managed cluster"]
    CHOICE --> ENT["Commercial/Enterprise self-managed"]
    CHOICE --> MNG["Managed NoSQL service"]
    CHOICE --> MIX["Hybrid / cloud marketplace"]
    SELF --> OPS["Tự chịu patch, backup, on-call, capacity"]
    ENT --> OPS2["Tự vận hành + contract hỗ trợ/tính năng"]
    MNG --> OPS3["Chia sẻ trách nhiệm với provider"]
    MIX --> OPS4["Cần xác nhận licensing và bên chịu trách nhiệm"]
~~~

### 3.1. Self-managed

Nhóm sở hữu việc cài đặt, cấu hình, nâng cấp, kiểm quorum/replica, sao lưu, giám sát, phân quyền, tối ưu hiệu năng và khôi phục. Có quyền kiểm soát sâu hơn nhưng cần người và quy trình.

### 3.2. Commercial/Enterprise tự vận hành

Có thể thêm tính năng, bảo mật, tích hợp, compliance, support hoặc quyền sử dụng thương mại. **Không mặc định** mọi Enterprise đều gồm mọi add-on; kiểm hợp đồng và phạm vi support.

### 3.3. Managed service

Provider quản lý một phần hạ tầng, bảo trì và service plane; khách hàng chịu trách nhiệm schema, data quality, IAM, workload, bill và application resilience. Đọc shared-responsibility model cụ thể.

### 3.4. Marketplace và third-party managed

Một vendor bán database qua cloud marketplace có thể có hai tầng điều khoản: phần mềm/vendor và cloud infrastructure/billing. Ai gửi invoice, ai trực sự cố và ai cấp license cần được xác định.

## 4. “Edition” thường khác nhau ở đâu?

| Khía cạnh | Câu hỏi kiểm tra |
|---|---|
| Engine core | CRUD, query, indexing, consistency giống nhau không? |
| High availability | Replication, election, multi-AZ có điều kiện gì? |
| Scalability | Sharding/partitioning/online rebalance có được hỗ trợ? |
| Backup | Scheduled backup, PITR, restore scope, retention? |
| Security | SSO, LDAP/OIDC, encryption, KMS/BYOK, audit? |
| Monitoring | Metrics, query profiler, event logs, tracing? |
| Data governance | Data residency, legal hold, retention, encryption controls? |
| Integrations | Connectors, CDC, search/vector/analytics có gói riêng? |
| Operations | Rolling upgrade, automation, control plane, IaC? |
| Support | Response time, support hours, severity, escalation? |
| Limits | Storage, node, cores, requests, tenants, index count? |
| SLA | Service credits, eligible tiers, exclusions, obligations? |

### 4.1. Feature matrix có thể phụ thuộc version

Một tính năng trước đây chỉ Enterprise có thể được chuyển sang Community, managed-only hoặc plugin riêng ở phiên bản khác. Luôn ghi **exact edition/version** và ngày xác nhận nguồn.

### 4.2. “Có tính năng” chưa nói “được dùng như yêu cầu”

PITR có thể chỉ hỗ trợ retention window hữu hạn; audit logs có thể thiếu trường cần cho tenant-level compliance; vector search có giới hạn index hoặc region. Cần kiểm cả **scope, quotas và recovery semantics**.

### 4.3. Driver SDK và server khác nhau

Java driver có thể dùng license khác engine server, support matrix khác và feature flags riêng. Một driver miễn phí không có nghĩa server feature hay vendor support miễn phí.

### 4.4. Các bản thử nghiệm/trial

Không dùng ngưỡng miễn phí và credits tạm thời làm “chi phí production vĩnh viễn”; đánh giá hậu quả khi credits hết hoặc trial không được gia hạn.

## 5. Phân biệt open source, source-available và commercial

### 5.1. Open-source license được công nhận

Các giấy phép permissive như Apache License 2.0, MIT hoặc BSD có quyền và nghĩa vụ cụ thể; GPL/AGPL là họ copyleft. Việc có mã nguồn công khai chưa tự nói phần mềm nằm ở nhóm nào.

### 5.2. Source-available

Một dự án có mã nguồn xem được nhưng dùng giấy phép giới hạn hình thức cung cấp dịch vụ hoặc mục đích thương mại. Không gọi đó là OSI-open-source chỉ vì có Git repository.

### 5.3. Commercial license

Quyền dùng, số cores/nodes, loại môi trường, audit, indemnity, support và quyền phân phối có thể đến từ hợp đồng trả phí. Giấy phép này có thể cùng tồn tại với một lựa chọn open-source khác.

### 5.4. Dual/multi licensing

Nhà cung cấp có thể cho lựa chọn giấy phép khác nhau theo phiên bản, loại phân phối hoặc hợp đồng. Đừng trộn quyền từ một license với binary thuộc một license khác.

### 5.5. Trademark và branding là chủ đề riêng

Ngay cả khi được fork và phân phối source theo license, quyền dùng tên, logo hoặc chứng nhận thương hiệu có thể chịu quy định riêng.

## 6. Một bảng so sánh họ giấy phép

| Họ giấy phép | Mục đích thường thấy | Cần xác minh đặc biệt |
|---|---|---|
| MIT/BSD/Apache-2.0 | Permissive OSS | Notices, attribution, license copy, patent terms |
| GPL | Copyleft | Distribution/conveying, corresponding source, linking/derivative boundaries |
| AGPL | Network copyleft | Nghĩa vụ với người tương tác qua mạng theo bản license/modified program |
| SSPL | Source-available service-related | Nghĩa vụ nếu cung cấp phần mềm như dịch vụ theo điều khoản cụ thể |
| BSL/Business Source License | Source-available, use grants và chuyển đổi sau thời gian | Additional use grant, restrictions, change date/license |
| Elastic License/other custom | Điều khoản do vendor quy định | Managed service/restrictions, re-distribution, field-of-use |
| Commercial EULA/subscription | Quyền theo hợp đồng | Cores/nodes/tenants, deployment, audit, support, termination |

**Lưu ý:** Đây là mô tả định hướng để đặt câu hỏi, không phải bản diễn giải đầy đủ hay tư vấn pháp lý. Tác động thực phụ thuộc văn bản license đúng version, cách sử dụng và luật áp dụng; chuyển legal counsel xem khi có rủi ro phân phối hoặc cung cấp dịch vụ.

### 6.1. Apache 2.0 không có nghĩa không có nghĩa vụ

Một bản phân phối có thể cần giữ license text, notices và tuân các điều kiện liên quan. “Miễn phí” không phải “không phải làm gì”.

### 6.2. GPL và AGPL không thể gộp một quy tắc

Network access, việc modified program là gì, loại phân phối và source availability phải kiểm theo license cụ thể. Không suy mọi ứng dụng Java dùng driver sẽ buộc public toàn bộ mã ứng dụng.

### 6.3. SSPL không giống Apache hay GPL

SSPL là giấy phép source-available có nghĩa vụ liên quan cung cấp chương trình như dịch vụ theo nội dung license; không được tự xếp nó vào danh sách OSI-approved.

### 6.4. BSL có additional use grant

Cùng tên “BSL” không bảo đảm giống quyền sử dụng; phải đọc grant/restriction và change license/date của chính project/version.

### 6.5. “Free for production” cần bằng chứng

Một edition có thể cho chạy production trong một số điều kiện, nhưng feature/plugin/support/sublicensing lại khác. Không suy quyền pháp lý từ việc server khởi động thành công.

## 7. Giấy phép thay đổi theo phiên bản và thành phần

Một sản phẩm qua nhiều năm có thể dùng các license khác nhau theo version hoặc chuyển một phần chức năng sang plugin.

### 7.1. Ghi artifact cụ thể

Một hồ sơ cần: engine name, version, distribution artifact/container digest, edition, license file, source repository tag, driver version, plugins và cách deploy.

### 7.2. Không lấy license của driver thay server

Java driver có thể là Apache-licensed trong khi server cùng thương hiệu chịu SSPL/commercial; hai quyền khác nhau.

### 7.3. Plugins/connectors riêng

Connector JDBC, Kafka CDC, authentication plugin, vector extension hay admin UI có thể do tổ chức khác phát hành với license và support lifecycle khác.

### 7.4. Container image cũng cần audit

Base OS, OpenSSL, runtime Java và utilities trong image mang license/security obligations riêng; kiểm Software Bill of Materials (SBOM) nếu chính sách yêu cầu.

### 7.5. Lập bằng chứng theo ngày

Lưu link điều khoản chính thức, checksum/license text và ngày rà soát. Đặc biệt quan trọng khi quyết định mua kéo dài qua một lần vendor thay điều khoản.

## 8. Checklist xác định nghĩa vụ sử dụng

| Câu hỏi | Vì sao quan trọng? |
|---|---|
| Chạy nội bộ hay phân phối? | Nghĩa vụ source/notices có thể thay |
| Có sửa engine hoặc build fork không? | Modified work/source obligations |
| Có nhúng binary trong sản phẩm khách hàng không? | Distribution rights |
| Có cung cấp database API như dịch vụ không? | Một số service-related restrictions |
| Có đưa copy cho đối tác không? | Conveying/sublicensing |
| Có marketplace/hosting bên thứ ba không? | Phân định service operator |
| Có nhiều phiên bản engine cùng chạy không? | License scope/version mixing |
| Có plugins thương mại không? | Feature license/compliance |
| Có license audit hoặc telemetry không? | Nghĩa vụ hợp đồng |
| Có quy định chuyển đổi license trong tương lai không? | Long-term upgrade path |

### 8.1. Viết “use description” cho legal thay vì hỏi chung

Ví dụ: “Công ty chạy engine X trên cloud riêng để lưu booking cho SaaS; người dùng chỉ truy cập booking API, không được truy cập database API; công ty không phân phối binary; có dùng connector Y.” Như vậy legal có đủ dữ liệu để đối chiếu.

### 8.2. Những điều không nên tự kết luận

Không dùng quy tắc kiểu “SaaS luôn miễn copyleft” hay “mọi AGPL dùng qua mạng bắt buộc public cả app”. Đây là vấn đề pháp lý/technical integration cần xem license và kiến trúc cụ thể.

### 8.3. Chuyển phiên bản có thể tạo lại nghĩa vụ

Major upgrade hoặc đổi distribution channel có thể đổi license/feature. Thêm license-review vào quy trình dependency upgrade, không chỉ lúc dự án khởi đầu.

## 9. Phân biệt license với service terms và SLA

Một managed database thường được khách hàng sử dụng theo **điều khoản dịch vụ, data processing/security terms và bảng giá**. Quyền dùng code engine có thể không phải quyền khách hàng trực tiếp được cấp.

### 9.1. License phần mềm

Quy định việc sao chép, sửa, phân phối, chạy hoặc cung cấp một chương trình tùy điều khoản.

### 9.2. Service agreement

Quy định dịch vụ nhà cung cấp vận hành: billing, support, data handling, service limitation, termination, responsibilities.

### 9.3. SLA

Quy định chỉ tiêu availability của **dịch vụ đủ điều kiện**, cách đo, thời gian báo sự cố, exclusions và remedy/service credits. Nó không mặc định là cam kết application end-to-end SLO.

### 9.4. Support contract

Quy định response times, giờ hỗ trợ, severity, escalation và upgrade help. Response time không đồng nghĩa fix time hoặc restoration time.

### 9.5. DPA/privacy

Quy định dữ liệu cá nhân, subprocessors, region, incident notification, retention và nghĩa vụ khi chấm dứt; không thể thay bằng tên edition.

## 10. Shared-responsibility matrix

| Công việc | Self-managed | Managed (điển hình; phải xác nhận) |
|---|---|---|
| Cài đặt DB engine | Khách hàng | Provider |
| Patching OS/DB | Khách hàng | Provider thường chịu phần service |
| Thiết kế key/index/schema | Khách hàng | Khách hàng |
| Backup/PITR configuration | Khách hàng | Chia trách nhiệm |
| Restore test nghiệp vụ | Khách hàng | Khách hàng, provider hỗ trợ tùy gói |
| IAM và tenant authorization | Khách hàng | Khách hàng |
| Network/KMS policy | Khách hàng | Chia trách nhiệm |
| Capacity/query optimization | Khách hàng | Khách hàng, có thể có advisors |
| Infra monitoring và node replacement | Khách hàng | Provider thường chịu phần service |
| App SLO/RPO/RTO | Khách hàng | Khách hàng phải thiết kế và kiểm chứng |
| Billing/quota/egress | Khách hàng | Khách hàng |
| Incident escalation | Tự trực + vendor nếu có | Khách hàng + provider theo support |

### 10.1. “Managed backup enabled” chưa bằng “restore ready”

Database có thể backup tự động nhưng application chưa restore test indexes, credentials, event offsets hoặc payment reconciliation.

### 10.2. Quản trị viên ứng dụng vẫn có thể xóa nhầm

Managed service không ngăn mọi destructive query; retention, PITR, least privilege và backup separation phải được thiết kế.

### 10.3. Cần kiểm quyền truy cập dữ liệu của provider

Audit, data residency, KMS ownership, support access và subprocessor arrangements là phần của evaluation.

## 11. Tạo ma trận edition theo yêu cầu thay vì theo marketing

Một cách làm: mỗi requirement là một dòng, mỗi **candidate/edition/version** là một cột.

| Requirement | Community self-managed | Enterprise self-managed | Managed tier A | Managed tier B |
|---|---|---|---|---|
| CRUD/query correctness | VERIFY | VERIFY | VERIFY | VERIFY |
| Multi-AZ recovery | VERIFY | VERIFY | VERIFY | VERIFY |
| PITR theo RPO | VERIFY | VERIFY | VERIFY | VERIFY |
| Encryption + customer key | VERIFY | VERIFY | VERIFY | VERIFY |
| Audit per tenant/admin | VERIFY | VERIFY | VERIFY | VERIFY |
| Auth federation | VERIFY | VERIFY | VERIFY | VERIFY |
| CDC với yêu cầu latency | VERIFY | VERIFY | VERIFY | VERIFY |
| Index build online | VERIFY | VERIFY | VERIFY | VERIFY |
| Quota/cost controls | VERIFY | VERIFY | VERIFY | VERIFY |
| Data residency | VERIFY | VERIFY | VERIFY | VERIFY |
| Support coverage | VERIFY | VERIFY | VERIFY | VERIFY |
| License matches use | VERIFY | VERIFY | VERIFY | VERIFY |

`VERIFY` không phải gợi ý rằng mọi bản đều hỗ trợ. Điền `YES / NO / CONDITIONAL / UNKNOWN`, kèm **nguồn + date + plan limit**. Không lấy một dấu check không nguồn làm căn cứ mua.

### 11.1. Hard gate không được chấm điểm bù

Nếu policy yêu cầu dữ liệu chỉ ở khu vực A mà candidate chỉ có dịch vụ ở B, không lấy throughput cao hoặc giá rẻ để “bù điểm”.

### 11.2. Conditional phải ghi điều kiện

Ví dụ `PITR: yes, only under tier X and window Y` hoặc `SSO: requires add-on Z`. Điều kiện trở thành chi phí hoặc rủi ro.

### 11.3. Edition feature và deployment feature khác nhau

Một tính năng có trong Enterprise binary nhưng không khả dụng ở managed tier đang xét, hoặc ngược lại. Hỏi chính xác SKU/region.

## 12. Phân loại nhu cầu thành must-have và optional

### 12.1. Must-have

Business invariants, correctness, residency, encryption requirements, legal license permission, recovery objectives, scalability floor và khả năng có support theo chính sách.

### 12.2. Should-have

Một query optimization, console tự động, dashboard, scheduled scaling hoặc backup interface nâng cao có thể chấp nhận giải pháp khác.

### 12.3. Nice-to-have

Hệ sinh thái plugin, UI đẹp, hệ thống gợi ý index hoặc API đa mô hình hữu ích nhưng không nên quyết định thay các gates.

### 12.4. Phân biệt “có thể tự xây” với “không cần”

Không có audit console có thể tự xây audit logs nhưng effort/security review có thể quá cao. “Workaround available” phải được tính vào TCO và risk.

## 13. Workload profile: không so bảng giá khi chưa biết tải

Các thông số cần thu:

| Đại lượng | Ví dụ câu hỏi |
|---|---|
| Read/write per second | Trung bình, p95 theo phút, peak 1–5 phút? |
| Request size | 1 KB, 4 KB hay 200 KB mỗi item? |
| Query shape | Key lookup hay scan, range, join app-side, vector? |
| Consistency | Strong, eventual, transactional, conditional write? |
| Tenant skew | Một whale tenant chiếm bao nhiêu traffic? |
| Data growth | GB/ngày, delete/TTL, retention? |
| Indexes | Số indexes, index bytes, write amplification? |
| Regions | Một region, multi-AZ, multi-region, active-active? |
| Availability | N−1 headroom, failover, peak capacity? |
| Events | CDC, Streams, connectors, Kafka, outbox? |
| Backup | Snapshot frequency, PITR, immutable/offsite, drills? |
| Network | Cross-AZ/region transfer và client egress? |
| Operations | Support, monitoring, security, engineer hours? |

### 13.1. Đừng dùng mỗi số documents

50 triệu documents 2 KB với key lookups khác 50 triệu documents 100 KB truy vấn range, khác hẳn 50 triệu documents bị update nhiều lần/giây.

### 13.2. Tải peak là yếu tố mua capacity

Self-managed có thể cần provision theo peak + headroom, trong khi managed theo request có thể tính phí theo tải thực. Nhưng managed cũng có throttling, quotas, min capacity và burst rules.

### 13.3. Hot partition làm chi phí phi tuyến

Tăng tổng provisioned capacity không luôn làm một hot logical key xử lý nhiều writes hơn. Có thể cần data model redesign, transaction serialization hoặc sharding.

### 13.4. Read unit không bằng HTTP request

Một `GET` có thể đọc nhiều items/pages, strong vs eventual có hệ số khác, item size làm tăng đơn vị billable. Phải tính **billable units**, không chỉ request count.

## 14. Đơn vị tính phí thường gặp

| Mô hình | Meter thường thấy | Cạm bẫy |
|---|---|---|
| Node/instance-hours | Giờ chạy theo size máy | N−1 capacity, idle cost, HA |
| vCPU/core subscription | Cores hoặc node entitlement | Hyperthread, cluster scope, minima |
| Provisioned throughput | RCU/WCU/RU/s hay capacity units | Peak provisioning, autoscale thresholds |
| On-demand requests | Million read/write units/operations | Item size, consistency, multi-item queries |
| Storage | GB-month logical/billed | Index, replicas, WAL, compression |
| Backup/PITR | GB-month, snapshot retention | History window, restore charge |
| Network | GB egress/cross-region/AZ | Replication, CDC, read clients |
| Index/search | Index GB, provisioned compute, query units | Write amplification, separate SKU |
| Security | KMS/API requests, audit logs, private networking | Per-key/request/GB overhead |
| Support | % spend, subscription, per-account minimum | Support tier và coverage |
| Observability | Log ingestion/storage, metrics cardinality, traces | High-cardinality tags, retention |
| Restore/migration | Retrieval, compute-hours, egress, expert labor | Disaster recovery costs |

### 14.1. Nhóm fixed và variable

Fixed/minimum fees tồn tại dù workload nhỏ; variable meters tăng theo usage. Hai ứng dụng có cùng average RPS nhưng burst khác nhau có thể trả chi phí rất khác.

### 14.2. Free tier và discount

Credits/trial, committed-use discount và negotiated private pricing cần được phân biệt với public list price; forecast gồm ngày hết hạn và minimum spend.

### 14.3. Không nhân replication tùy tiện

Một dịch vụ có thể tính storage theo logical/billed data đã gồm replicas; hệ khác thu tiền theo node volumes. Chỉ nhân replica factor khi **pricing model thực yêu cầu**, tránh tính hai lần.

## 15. Ước lượng dữ liệu lưu theo kích thước và tăng trưởng

Một mô hình vật lý cho self-managed:

\[
S_{\text{logical}} = N_{\text{documents}}\times S_{\text{avg document}}.
\]

Một ước lượng tổng:

\[
S_{\text{physical}} \approx
S_{\text{logical}}\times R\times C
 + S_{\text{indexes}}
 + S_{\text{logs/temp}}
 + S_{\text{backup staging}},
\]

với \(R\) là replication factor được tính nếu lưu các copies vật lý, còn \(C\) biểu diễn các hiệu ứng nén/metadata/overhead trong một mô hình minh họa. Đừng gộp hệ số một cách ngầm định; phải đo compression ratio và index footprint thực.

### 15.1. Ví dụ documents

50 triệu documents, trung bình 2 KB (decimal) là khoảng 100 GB dữ liệu logic trước indexes, replica và overhead. Đây chỉ là estimate; JSON size/serialization/index entries cần đo.

### 15.2. Retention không giống growth rate

Nếu 1 triệu records/ngày nhưng TTL 30 ngày và xóa đúng, storage có thể ổn định quanh working retention window; nếu legal hold giữ lâu, growth khác.

### 15.3. Index bytes

Index có thể chiếm phần đáng kể storage, đặc biệt với nhiều composite/multikey indexes. Không chỉ tính primary data.

### 15.4. Compaction/headroom

LSM engines thường cần free space để rewrite files; snapshot/backup hard links có thể giữ old blocks. Đầy disk gây rủi ro lớn hơn hóa đơn tăng.

### 15.5. Capacity runway

Forecast cả hiện tại, 6, 12, 24 và 36 tháng cùng kịch bản growth cao và thời gian scale/migrate.

## 16. Tính read/write units có ý thức

Một service có thể tính đơn vị theo số lần đọc/ghi **đã quy đổi** bởi kích thước, consistency mode và API.

~~~text
Logical HTTP request:
    GET /orders?tenant=T1&month=2026-11

Database work:
    query 8 partitions
    read multiple pages/documents
    maybe use secondary index
    return one HTTP response
~~~

### 16.1. Một request có thể tốn nhiều units

Một query rộng trả nhiều documents hoặc scan nhiều data có chi phí lớn hơn point lookup. Đừng lấy endpoint QPS nhân giá đơn vị “GET” nếu billing meter là read units.

### 16.2. Strong vs eventual read

Một số dịch vụ có quy đổi request khác nhau theo consistency. Dùng bảng quy đổi chính thức của SKU/region, không dùng hệ số giống nhau cho mọi NoSQL.

### 16.3. Transactional writes

Conditional/transaction writes có thể chịu cost khác writes thường. Tính theo API mix thực, không chỉ đếm số business commands.

### 16.4. Index maintenance

Thêm index có thể giúp read units giảm nhưng tăng write/storage units; tính tổng theo workload.

### 16.5. Retry storms

429/timeout có thể tạo nhiều attempts, tăng billable work hoặc capacity provisioning. Cần retry budgets và đo client/SKD behavior.

## 17. Sao lưu, PITR và khôi phục phải nằm trong báo giá

### 17.1. Backup frequency và retention

Giữ 7 ngày PITR khác 90 ngày restore history; long-tail monthly snapshots có dung lượng và quy tắc retention riêng.

### 17.2. Offsite/immutable copies

Một backup ngoài region/account để chịu lỗi lớn có thể phát sinh storage, transfer, KMS, retrieval và phí API riêng.

### 17.3. Restore drill

Để kiểm RTO phải thật sự download/restore, dựng cluster tạm, tính toán và kiểm dữ liệu. Thêm chi phí diễn tập định kỳ vào forecast.

### 17.4. Recovery không phải lúc nào miễn phí

Một số tiers có restore operations/egress/retrieval fees. Nếu bảo vệ được data nhưng khôi phục 10 TB mất ba ngày, có thể không đáp ứng nhu cầu dù giá backup thấp.

### 17.5. Giấy phép cho DR site

Với commercial self-hosted subscription, quyền chạy standby/DR cluster có thể được tính khác production. Hỏi rõ entitlement cho passive/active DR.

## 18. Network là một thành phần chi phí dễ bị quên

| Traffic | Nguồn phát sinh |
|---|---|
| Client egress | API/service trả dữ liệu ra ngoài mạng/provider |
| Cross-AZ | Application và DB, replicas hoặc cross-zone coordination |
| Cross-region | Replication, CDC, backup copy, disaster recovery |
| Migration | Export/import sang engine hoặc account khác |
| Analytics/search | Copy data sang warehouse, search, stream processor |
| Monitoring | Export logs/metrics/traces tới observability service |

### 18.1. Architecture placement quyết định chi phí

App ở region A nhưng DB ở region B có thể tạo cả latency và phí transfer trong từng request, kể cả DB instance rẻ.

### 18.2. Egress khi rời nhà cung cấp

Exit/migration có thể phải đọc xuất toàn bộ data, transfer sang dịch vụ khác rồi chạy dual writes. Đây là chi phí tương lai phải tính, không chỉ monthly steady-state.

### 18.3. Phân biệt network traffic và billable traffic

Không phải mọi bytes gửi trong nội bộ đều bị thu cùng giá. Phải đọc tier pricing, loại endpoint, zone, private link và negotiated terms.

## 19. Security và compliance có thể làm thay đổi edition

### 19.1. Identity federation

Doanh nghiệp có thể yêu cầu SSO/OIDC/SAML/LDAP hoặc integration với IAM; kiểm authn/authz ở cấp DB lẫn management console.

### 19.2. Audit logs

Cần biết edition nào log được data access/admin actions, thời gian retention và khả năng export theo tenant mà không làm lộ PII không cần thiết.

### 19.3. Customer-managed keys

Một compliance policy có thể yêu cầu BYOK/CMK, rotation, key residency, backup encryption và separation of duties. KMS operations có chi phí và support constraints.

### 19.4. Network isolation

Private endpoint, VPC/VNet peering, allow-list, TLS/mTLS, egress restrictions có thể là tính năng theo tier hoặc chi phí network riêng.

### 19.5. Residency và subprocessors

Dữ liệu production, backups, support snapshots và telemetry có thể có địa điểm xử lý khác nhau. Hỏi rõ để không mua nhầm một dịch vụ “có region phù hợp” nhưng luồng phụ trợ không phù hợp.

## 20. Support và availability: đọc đúng cam kết

### 20.1. Support response khác resolution

“Phản hồi severity 1 trong 1 giờ” không bảo đảm khắc phục trong 1 giờ. Hãy hỏi escalation, RTO thực hiện và incident communication.

### 20.2. SLA không là SLO của ứng dụng

Database availability 99,9% không có nghĩa booking API đạt 99,9% khi còn network, SDK, auth, app và downstream providers.

### 20.3. Multi-region thường là một kiến trúc riêng

Cần phân biệt active-active, active-passive, async replication, conflict resolution, failover và data residency. Giá multi-region không chỉ bằng “nhân đôi node”.

### 20.4. RPO và durability

Nếu service chỉ bảo đảm async cross-region replication, failover có thể mất một số acknowledged writes theo failure model. Đừng mua dựa trên SLA uptime mà chưa xem dữ liệu.

### 20.5. Exit và support khi chấm dứt

Hỏi về data export format, window được đọc sau termination, hỗ trợ migration và xóa dữ liệu/backup.

## 21. TCO: ba nhóm chi phí chính

~~~text
TCO = Direct platform spend
    + People and operations
    + Risk, migration and lifecycle
~~~

### 21.1. Direct spend

Compute, storage, network, backup, support subscription, license, managed service units, monitoring, keys.

### 21.2. People and operations

DBA/SRE on-call, incident response, tuning, schema/index review, backup drills, upgrades, security assessment và capacity planning.

### 21.3. Risk and lifecycle

Migration downtime/cost, compliance audit, capacity buffer, DR failure exposure, vendor lock-in/exit, re-platforming và long-term support.

### 21.4. Không định giá mất dữ liệu như một dòng hóa đơn bình thường

Risk-adjusted cost có ích khi ra quyết định, nhưng mất acknowledged writes hoặc vi phạm residency có thể là hard gate, không được bù bằng một chi phí kỳ vọng nhỏ.

## 22. Mô hình self-managed

\[
C_{\text{self/month}}=
C_{\text{nodes}}+C_{\text{disks}}+C_{\text{network}}
+C_{\text{backup}}+C_{\text{observability}}
+C_{\text{license/support}}+C_{\text{labor}}.
\]

Một ví dụ **giả định hoàn toàn**, đơn vị USD/tháng:

| Thành phần | Giả định | Chi phí |
|---|---|---:|
| 3 nodes | 450 USD/node-tháng | 1.350 |
| Disk cho nodes | 3 × 500 GB × 0,08 | 120 |
| Backup repository | 700 GB × 0,025 | 17,50 |
| Network | 300 GB × 0,10 | 30 |
| Monitoring/logs | Gói cố định giả định | 100 |
| Nhân sự vận hành | 30 giờ × 60 USD | 1.800 |
| Commercial support | Gói giả định | 400 |
| **Tổng giả định** | | **3.817,50** |

### 22.1. Đây không phải giá thực của vendor

Các con số chỉ minh họa công thức. Ở thị trường thật, node size, disk tier, network, DR, license và lương thay đổi; phải lấy báo giá chính thức.

### 22.2. Chi phí nhân sự không thể bằng 0 nếu có SRE

Một DBA làm 30 giờ/tháng không “miễn phí” dù là nhân viên nội bộ. So managed vs self-managed phải tính opportunity cost và 24/7 escalation.

### 22.3. 3 nodes có đủ HA không?

Ví dụ chưa chứng minh replica factor, N−1 capacity, multi-AZ, disk headroom hay peak throughput; phải benchmark trước khi dùng số để so.

### 22.4. DR và test environment

Nếu tổ chức cần staging, DR standby, load-test cluster hoặc active-active, phải cộng thêm; bảng trên chưa bao trọn các hệ đó.

## 23. Mô hình managed usage-based

\[
C_{\text{managed/month}}=
C_{\text{readUnits}}+C_{\text{writeUnits}}
+C_{\text{storage}}+C_{\text{index}}
+C_{\text{backup}}+C_{\text{egress}}
+C_{\text{security}}+C_{\text{support}}+C_{\text{monitoring}}.
\]

Một ví dụ **giả định**, không đại diện giá hoặc công thức billing của bất kỳ nhà cung cấp nào:

| Meter | Khối lượng mỗi tháng | Đơn giá minh họa | Thành tiền |
|---|---:|---:|---:|
| Read units | 600 triệu units | 0,25 USD/triệu | 150 |
| Write units | 60 triệu units | 1,20 USD/triệu | 72 |
| Data storage | 500 GB-month | 0,20 USD/GB-month | 100 |
| Index storage | 120 GB-month | 0,20 USD/GB-month | 24 |
| Backup/PITR storage | 500 GB-month | 0,08 USD/GB-month | 40 |
| Egress | 300 GB | 0,10 USD/GB | 30 |
| Monitoring/logs | Fixed giả định | | 50 |
| Support | Fixed giả định | | 200 |
| **Tổng giả định** | | | **666 USD/tháng** |

### 23.1. Không được diễn giải 600 triệu HTTP GETs

Ở bảng này 600 triệu **billable read units** đã được quy đổi từ workload. Nếu một query tốn 20 units, số HTTP requests sẽ ít hơn nhiều.

### 23.2. Tránh đếm index hai lần

Bảng coi 500 GB data và 120 GB index **không chồng nhau**. Nếu dịch vụ tính index trong cùng storage meter, sửa mô hình để không double charge.

### 23.3. Không mặc định 666 USD rẻ hơn 3.817,50 USD

Hai bảng chưa chứng minh cung cấp cùng throughput, p99, replication, region count, compliance, recovery objectives và on-call model. So sánh phải chuẩn hóa **cùng service-level outcome**.

### 23.4. High-traffic query shape có thể đảo kết quả

Một range scan nhiều units hoặc hot partition bị throttling có thể khiến phương án usage-based đắt, chậm hoặc đòi redesign. Đo units trên POC có dataset thật.

## 24. Đánh giá số liệu theo ba kịch bản

| Kịch bản | Workload | Những khoản nên kiểm |
|---|---|---|
| **Low/base** | 30–50% forecast, ít burst | Minimum fees, idle nodes, free tier hết hạn |
| **Expected** | Forecast theo seasonality | Units, write amplification, growth |
| **Peak/stress** | 2–5× trong campaign/sự cố | Autoscale, throttling, hot keys, overprovision |
| **DR/failover** | Mất node/region, rebuild | Egress, restore compute, temporary double capacity |
| **Migration/exit** | Backfill + dual running | Double billing, data export, engineering effort |

### 24.1. Expected average chưa đủ cho node sizing

Self-managed provision theo peak + failure headroom; managed provisioned throughput có thể cũng phải giữ capacity cao trước khi autoscale.

### 24.2. Peak chỉ kéo dài 10 phút vẫn có rủi ro

Autoscale delay có thể gây throttling trong burst; evaluate SLA ở chính peak window, không chỉ hóa đơn tháng.

### 24.3. Growth compound

Nếu data tăng 40%/năm, sau ba năm storage/index/backup/network có thể tăng nhiều lần. TCO 3 năm phải model growth và hardware refresh/upgrade.

### 24.4. Worst-case hợp lý khác vô hạn

Không cần mua capacity cho mọi điều phi thực tế, nhưng cần buffer và phương án xử lý khi vượt dự báo.

## 25. Chi phí theo thời gian: 12, 24, 36 tháng

Một quyết định được ký hôm nay có thể được vận hành ba năm:

\[
TCO_{36m}=
C_{\text{one-time migration}}
+\sum_{m=1}^{36} C_m
+C_{\text{planned upgrades}}
+C_{\text{exit reserve}}.
\]

### 25.1. Không nhân monthly cost hiện tại ×36 khi data tăng

Forecast cần data growth, query growth, pricing tiers, support escalation, headcount và SLA changes.

### 25.2. One-time migration

Chuyển dữ liệu, dual run, CDC, schema conversion, training, load test và downtime risk có thể làm lựa chọn “rẻ mỗi tháng” tốn hơn trong năm đầu.

### 25.3. NPV khi tài chính cần

Có thể quy dòng tiền về hiện tại với discount rate do finance quy định; không tùy tiện dùng một tỷ lệ rồi gọi đó là business case chính thức.

### 25.4. Rủi ro tăng giá

Subscription price, cloud rate card và volume discount có thể thay; chạy sensitivity analysis ±20–50% hoặc theo terms hợp đồng, không khẳng định giá hiện tại cố định.

## 26. Java: mô hình tính chi phí có đơn vị rõ ràng

Ví dụ Java 17+ nhận **đơn vị đã chuẩn hóa** và các giá giả định; không tính lại request units từ API calls:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record MonthlyUsage(
    BigDecimal millionReadUnits,
    BigDecimal millionWriteUnits,
    BigDecimal dataGbMonth,
    BigDecimal indexGbMonth,
    BigDecimal backupGbMonth,
    BigDecimal egressGb
) {
    public MonthlyUsage {
        for (BigDecimal v : new BigDecimal[] {
                millionReadUnits, millionWriteUnits, dataGbMonth,
                indexGbMonth, backupGbMonth, egressGb }) {
            Objects.requireNonNull(v);
            if (v.signum() < 0) {
                throw new IllegalArgumentException("negative usage");
            }
        }
    }
}

public record UnitRates(
    BigDecimal readPerMillion,
    BigDecimal writePerMillion,
    BigDecimal dataPerGbMonth,
    BigDecimal indexPerGbMonth,
    BigDecimal backupPerGbMonth,
    BigDecimal egressPerGb,
    BigDecimal monthlySupport,
    BigDecimal monthlyMonitoring
) {}

public final class MonthlyCost {
    private MonthlyCost() {}

    public static BigDecimal estimate(
            MonthlyUsage u, UnitRates r) {
        return u.millionReadUnits().multiply(r.readPerMillion())
            .add(u.millionWriteUnits().multiply(r.writePerMillion()))
            .add(u.dataGbMonth().multiply(r.dataPerGbMonth()))
            .add(u.indexGbMonth().multiply(r.indexPerGbMonth()))
            .add(u.backupGbMonth().multiply(r.backupPerGbMonth()))
            .add(u.egressGb().multiply(r.egressPerGb()))
            .add(r.monthlySupport())
            .add(r.monthlyMonitoring());
    }
}
~~~

### 26.1. Model là một phần của total cost, không phải bảng giá vendor

Chưa có tiered rates, capacity minimum, storage replication metering, RU conversion, taxes, discounts, restore retrieval hay currency conversions. Không đưa nó vào billing thực mà chưa hiệu chỉnh.

### 26.2. Dùng `BigDecimal` cho tiền

Tránh sai số nhị phân của `double` trong phép tính tiền, nhưng vẫn cần định nghĩa currency, scale, rounding policy và effective dates.

### 26.3. Model units phải được đặt tên

600 nghĩa 600 triệu units, không phải 600 requests. Đổi từ 1.000.000 units sang một billable unit của vendor có thể làm chi phí sai cả triệu lần.

### 26.4. Thêm validation cho rates

Trong implementation production, phải từ chối null/negative rates, kiểm SKU/region/price version và gắn source link; ví dụ tập trung vào phép tính.

## 27. JUnit: cố định tính toán giả định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

final class MonthlyCostTest {
    private static BigDecimal d(String value) {
        return new BigDecimal(value);
    }

    @Test
    void estimatesIllustrativeMonthlySpend() {
        MonthlyUsage usage = new MonthlyUsage(
            d("600"), d("60"), d("500"),
            d("120"), d("500"), d("300"));
        UnitRates rates = new UnitRates(
            d("0.25"), d("1.20"), d("0.20"),
            d("0.20"), d("0.08"), d("0.10"),
            d("200"), d("50"));

        BigDecimal total = MonthlyCost.estimate(usage, rates);
        assertEquals(0, total.compareTo(d("666.00")));
    }
}
~~~

### 27.1. Một test đúng số học không xác nhận giá thị trường

Nó chứng minh công thức tính ra con số mong muốn, không chứng minh rates của DynamoDB, Cosmos DB, MongoDB Atlas hay service nào.

### 27.2. Thêm tests cho corner cases

Zero traffic nhưng có minimum/support, storage growth, negative usage, index size included trong base, peak autoscale, cross-region charges và 3-year accumulation.

### 27.3. Regression test cho cost model

Giữ golden scenarios và diff khi finance/vendor đổi rate card; ghi rõ phiên bản dữ liệu, không sửa rate values mà không review.

## 28. Sensitivity analysis quan trọng hơn một số tổng

Thay đổi một vài biến:

~~~text
Baseline assumption:
    600 million read units/month
    60 million write units/month
    500 GB data

Scenario A:
    Read units × 2 due to new query fan-out

Scenario B:
    Storage × 2 due to longer retention/index growth

Scenario C:
    Multi-region replication + backup offsite

Scenario D:
    Peak burst requires 3× provisioned capacity
~~~

### 28.1. Query design có thể quyết định hóa đơn

Một endpoint `listOrders` chạm 32 partitions thay vì 1 có thể làm read units tăng rất mạnh; chọn database mà chưa thiết kế data model là bỏ qua biến quan trọng.

### 28.2. SLA thay đổi kiến trúc

Một availability SLO cao hơn có thể buộc thêm AZ/region, standby capacity, support, backup và DR drills. Chi phí không thể so ngang với một single-node dev instance.

### 28.3. Lock-in có thể làm exit cost phi tuyến

Dùng APIs đặc thù, custom indexes, change streams, transaction semantics hoặc service-specific query language làm migration đắt hơn nhiều so với tiền egress.

## 29. POC phải là “proof of performance and cost”

Một POC đúng phạm vi cần đo:

~~~text
Seed representative data and indexes
    -> Run realistic API workload
    -> Collect operation-level billed units/cost
    -> Measure p95/p99, throughput, errors
    -> Simulate failover, restore and backup
    -> Measure admin effort and automation
    -> Reconcile cost estimate with provider invoice/usage metrics
~~~

### 29.1. Không chỉ thử CRUD hello world

Một driver `insertOne` thành công không chứng minh tenant queries, conditional reservation, online index build, CDC hoặc cross-region restore.

### 29.2. Dữ liệu đủ đại diện

Đo hot tenants, document sizes, TTL/tombstones, index selectivity, growth, read/write mix và peak. POC 1.000 records dễ che partition skew.

### 29.3. Đo operation-level cost

Với managed, ghi consumed RU/read/write units, scanned vs returned, cross-partition query cost. Với self-managed, đo CPU/IO/byte/op và headroom.

### 29.4. Hãy thử thao tác vận hành thực

Thêm node, index build, failover, restore test và cutover service; vì đó là nơi nhiều edition/managed-tier differences bộc lộ.

### 29.5. Đừng tối ưu POC quá mức

Một đội chuyên gia chỉnh config nhiều tuần có thể đạt benchmark tuyệt vời nhưng production không có nhân lực duy trì. Ghi effort và các tunings cần thiết.

## 30. Bảng đối chiếu nhóm sản phẩm: đọc theo hướng dẫn, không phải báo giá

| Nhóm ví dụ | Edition/license cần xác minh | Dịch vụ/cách triển khai cần đối chiếu |
|---|---|---|
| MongoDB | Community Server, Enterprise, thành phần/driver theo version | Self-managed, Atlas và các tiers |
| Apache Cassandra | Distro Apache/third-party/commercial feature/support | Self-managed, vendor-managed Cassandra-compatible |
| ScyllaDB | OSS/source-available/commercial terms tùy version/distribution | Self-managed/Cloud services |
| Redis | License thay đổi theo releases/distributions; module support | Self-managed, enterprise, managed compatible services |
| OpenSearch | Apache-licensed distro và plugins; kiểm exact artifacts | Self-managed, managed OpenSearch service |
| Elasticsearch | Multi-license/source and distribution terms theo version | Self-managed Elastic tiers/cloud |
| Couchbase | Community/Enterprise/Capella terms | Self-managed, managed service |
| DynamoDB | Managed service terms, không chỉ engine binary license | On-demand/provisioned, global tables, backup |
| Cosmos DB | Managed service terms và API/consistency tiers | Provisioned/serverless/autoscale theo khả năng |
| Firestore | Managed service terms, billing/query/listener units | Native/Datastore modes theo ứng dụng |

### 30.1. Bảng này không khẳng định giá, license hay feature hiện tại

Những lĩnh vực đó thay đổi theo release, region và hợp đồng. Đây là danh sách **câu hỏi cần kiểm**; hồ sơ quyết định phải trỏ tới bản chính thức được xác nhận tại thời điểm mua.

### 30.2. Compatible API không đồng nghĩa equivalent behavior

Hai dịch vụ nhận CQL/Redis API hoặc MongoDB-like driver chưa chắc giống transaction isolation, CDC, TTL, consistency, indexes, quotas hoặc license.

### 30.3. Engine tự host và managed cùng thương hiệu khác sản phẩm thương mại

Trình quản lý backup, networking, metrics, support, data residency và storage metering có thể khác rất nhiều.

## 31. MongoDB: phân biệt Community, Enterprise và Atlas

### 31.1. License của Community Server

Các release MongoDB Community Server thuộc những giai đoạn khác nhau có thể có license khác; các release nguồn hiện đại từ giai đoạn chuyển năm 2018 thường dùng **Server Side Public License (SSPL)** cho server code. Không suy từ các release rất cũ hoặc license của Java driver. Kiểm exact source/binary version và vendor licensing page trước khi chấp thuận.

### 31.2. Enterprise và subscription

MongoDB Enterprise/Enterprise Advanced thường là lựa chọn commercial với entitlement/support/features được định nghĩa trong hợp đồng. Cần kiểm cluster/node licensing scope, security/audit/backup tools và upgrade rights.

### 31.3. Atlas là service

Atlas có service tiers, cluster/serverless hoặc usage/capacity pricing theo cấu hình; backup, data transfer, support, Search và các tính năng bổ sung có thể tạo meters riêng. Không lấy Community licensing để suy hợp đồng Atlas.

### 31.4. Workload

Đo index storage, writes with write concern, read fan-out trên sharded cluster, replica placement, PITR và cross-region network; query nhanh sau index có thể đổi write cost.

### 31.5. Decision gate

Nếu dự định cung cấp database functionality cho khách hàng qua dịch vụ, cần legal review của exact license/contract. Nếu chỉ dùng Atlas làm backend của app, cần kiểm service terms, SLA, billing và residency.

## 32. Cassandra và hệ sinh thái tương thích CQL

### 32.1. Apache Cassandra

Apache Cassandra là dự án Apache Software Foundation với giấy phép Apache License 2.0 ở các distribution chính thức; vẫn cần xem third-party dependencies, notices và distro artifact cụ thể.

### 32.2. TCO self-managed

Thường phải vận hành replica topology, compaction, repair, tombstones, schema changes, backup/restore, CDC và capacity. “Không có license fee” không xóa các hoạt động ấy.

### 32.3. Vendor distribution/managed

Một bản được bán kèm support, enhanced tooling hoặc managed CQL service có thể có feature/license/operational model khác Apache Cassandra gốc.

### 32.4. Compatible CQL không đảm bảo exit miễn phí

Storage internals, LWT/transaction semantics, CDC, drivers, backups và performance tuning có thể khác. Cần thử migration và API contract.

### 32.5. Performance/cost

Với write-heavy, tính replication, compaction amplification, repair bandwidth, tombstone overhead, cluster headroom và cross-AZ traffic.

## 33. DynamoDB: mua dịch vụ, không mua “edition server”

### 33.1. Mô hình service

DynamoDB là AWS-managed NoSQL; quyết định thương mại thường tập trung vào capacity mode, table/index features, transactions, backup/PITR, Streams, global tables và account/region.

### 33.2. Units

Chi phí phụ thuộc read/write capacity units hay request units được quy đổi theo API/size/consistency/transaction, index/storage/backups và replication. Kiểm công thức billing chính thức của vùng và mode đang xét.

### 33.3. Hot partition

Một partition key nóng có thể throttle dù tổng provisioned capacity còn; phải benchmark partition distribution, không suy từ hóa đơn tổng.

### 33.4. GSI

Thêm Global Secondary Index có thể tăng storage/write maintenance; GSI cũng có read consistency constraints. Giá rẻ cho point reads không chứng minh query nhiều indexes rẻ.

### 33.5. Cross-region

Global tables/replication cần hiểu conflict, RPO, data residency và replicated writes billing; không chỉ thêm “region B” vào sơ đồ.

## 34. Cosmos DB for NoSQL: RU là phần của thiết kế dữ liệu

### 34.1. Provisioned, autoscale và serverless

Các lựa chọn capacity/billing phụ thuộc loại account, region và capabilities đang được hỗ trợ. Phải kiểm nơi nào có tính năng cần và các mức tối thiểu.

### 34.2. Request charge

RU cho point read khác cross-partition query hoặc transaction batch; partition key, indexing policy, document size và consistency có thể ảnh hưởng mạnh.

### 34.3. Indexing policy

Index mặc định hay tùy chỉnh có tradeoff read convenience vs write RU/storage. POC phải dùng indexing policy dự kiến production.

### 34.4. Multi-region

Thêm regions/read/write routing thay SLA/availability và chi phí; cần kiểm consistency levels và conflict-resolution semantics.

### 34.5. Backup/recovery

Periodic/continuous backup modes, restore constraints và vùng lưu phải được xác minh theo account type/version; không suy rằng mọi configuration có cùng PITR.

## 35. Redis: định giá theo vai trò cache hay source

### 35.1. License cần xác minh theo phiên bản

Redis và các distributions/forks có lịch sử thay đổi license. Khi quyết định self-host/redistribution/managed service, ghi exact engine version, vendor và điều khoản; không dùng tài liệu license của bản cũ áp cho bản mới.

### 35.2. Redis là cache

Nếu có authoritative DB khác, failure của Redis có thể được rebuild; TCO chủ yếu RAM, replicas, persistence tùy nhu cầu, eviction, failover và refill pressure.

### 35.3. Redis là nguồn dữ liệu có giá trị

Nếu chỉ có dữ liệu trong Redis, phải tính AOF/RDB persistence, backup, restore, write loss contract, replication durability và monitoring như một database nguồn.

### 35.4. Hot keys và Cluster

Mua thêm RAM/nodes chưa chắc giải quyết một hot slot hoặc một counter. Benchmark key distribution, hash tags và multi-key command constraints.

### 35.5. Managed compatible service

Không mặc định mọi Redis-compatible managed service hỗ trợ scripts, modules, RESP versions, persistence, cluster topology hay licensing y hệt.

## 36. OpenSearch và Elasticsearch: phân biệt project, license và tính năng

### 36.1. OpenSearch

OpenSearch là dự án có distribution mã nguồn theo Apache License 2.0; nhưng plugins/vendor distributions và managed service terms phải kiểm riêng.

### 36.2. Elasticsearch

Elasticsearch có lịch sử các lựa chọn licensing khác nhau theo phiên bản/source distributions, gồm giấy phép do vendor quản lý và các lựa chọn khác. Không kết luận một câu về license áp cho mọi artifact/release; đối chiếu bản cụ thể từ nguồn chính thức.

### 36.3. Search/vector/analytics features

Index/search, security, connectors, alerting, ML/vector có thể khác theo edition, service và resource tier. Các tính năng mới đôi khi có phí compute riêng.

### 36.4. Chi phí

Shard count, replica factor, segment merge, storage tiers, memory, indexing throughput, query cache và snapshot repository/egress đều ảnh hưởng TCO.

### 36.5. Có nên dùng search làm nguồn chính?

Nếu một ứng dụng dùng search projection có thể rebuild từ NoSQL authoritative source, requirements backup/consistency khác việc dùng search index làm hệ thống ghi duy nhất.

## 37. Couchbase và ScyllaDB: kiểm đúng distribution

### 37.1. Couchbase

Community, Enterprise và Capella là các lựa chọn phải được đối chiếu theo exact version/contract, bao gồm query/index, HA, backup, RBAC, support và licensing. Không suy toàn bộ feature từ tên “Couchbase”.

### 37.2. ScyllaDB

Các distribution/licensing/service offerings có thể thay qua thời gian và theo version; cần đối chiếu terms của bản đang triển khai. CQL compatibility không phải toàn bộ feature/operations compatibility.

### 37.3. Thử migration thực

Trong POC, chạy workload read/write, LWT/CAS, compaction, CDC, backup/restore và metrics; đặc biệt quan trọng nếu đổi từ Cassandra sang một CQL-compatible service.

### 37.4. Hỏi về support scope

Sự cố do driver/OS/Kubernetes/connector có được xử lý trong support contract không? Vendor chịu phần nào của distributed deployment?

## 38. Firestore và cloud-native document services

### 38.1. Service-only evaluation

Firestore là managed document database; nhu cầu so edition thường chuyển thành mode, APIs, regions, billing meters và service feature constraints.

### 38.2. Đơn vị phí

Reads/writes/deletes, index storage, query/listener behavior, backups và network có thể ảnh hưởng; số user truy cập app chưa đủ tính bill.

### 38.3. Transaction semantics

Client SDK có thể retry transaction callbacks; POC phải kiểm external side effects không chạy trùng và chi phí contention.

### 38.4. Lock-in

Security rules, indexes, query language và offline client sync có thể làm migration khỏi dịch vụ có effort lớn. Đưa exit plan vào quyết định.

## 39. Bảng RFI/RFP để hỏi vendor

| Nhóm | Câu hỏi gửi vendor |
|---|---|
| Product identity | Exact SKU, edition, release, engine/service version? |
| Legal | License text, permitted internal/SaaS/redistribution use? |
| Support | 24/7? Severity levels, response/escalation? |
| Feature | Audit, SSO, encryption, KMS, CDC, PITR, indexing? |
| Limits | Transactions, max item size, quotas, partition limits? |
| Availability | HA architecture, failover, uptime SLA/exclusions? |
| Durability | ACK semantics, RPO by failure scenario? |
| Region | Allowed regions, backup locations, subprocessors? |
| Pricing | Meters, minima, overages, autoscale, egress, discounts? |
| Backup | Retention, cross-account/region, restore billing? |
| Migration | Import/export, CDC, schema transform, downtime/egress? |
| Exit | Formats, time window, deletion proof, termination process? |
| Audit | Security reports, SOC/ISO where applicable, responsibilities? |
| Roadmap | EOL policy, support duration, upgrade compatibility? |

### 39.1. Yêu cầu xác nhận bằng tài liệu

Không dựa vào demo hoặc lời hứa sales “có thể làm được”; yêu cầu SKU-specific document/contract, limitations và giá kèm effective date.

### 39.2. Unknown không là “Yes”

Một capability chưa xác nhận cần POC, điều khoản hoặc risk owner. Không tự điền khả năng dựa vào sản phẩm cùng họ.

### 39.3. Hỏi về tăng giá

Price change notice, committed spend, renewal, minimum contract term, annual uplift và termination rights ảnh hưởng TCO nhiều năm.

## 40. Chấm điểm lựa chọn: hard gates trước weighted scores

Quy trình:

~~~text
Candidates
  -> HARD GATES:
       legal use permitted?
       data residency?
       correctness/transaction semantics?
       RPO/RTO and compliance feasible?
       minimum support/availability?
  -> POC / measured constraints
  -> Weighted scores for survivors
  -> 3-year TCO and risk review
  -> Decision memo with tradeoffs
~~~

### 40.1. Hard gate không thể được bù

Một candidate không có quyền license phù hợp hoặc không đáp ứng tenant isolation phải loại/đổi phương án, không nên đạt điểm trung bình cao nhờ rẻ.

### 40.2. Weighted criteria

Ví dụ (tổng 100%): business fit 25%, performance 20%, operations 15%, security/compliance 15%, TCO 15%, portability 10%. Đây là trọng số minh họa; điều chỉnh theo mục tiêu tổ chức.

### 40.3. Điểm phải có nguồn

Một điểm 5/5 cho “sẵn sàng vận hành” phải được hỗ trợ bởi POC, runbook, support contract hoặc quan sát có thể lặp lại.

### 40.4. Sensitivity của trọng số

Nếu đổi trọng số TCO 15→30% khiến “người thắng” thay đổi, trình bày điều đó cho decision maker; không giấu độ nhạy.

## 41. Ví dụ ma trận quyết định có điều kiện

Ba phương án giả định:

| Tiêu chí | OSS self-managed | Commercial self-managed | Managed |
|---|---|---|---|
| Quyền dùng phù hợp | Legal review | Contract review | Service terms review |
| Tính năng Enterprise | Có thể thiếu/cần plugin | Có thể có, kiểm SKU | Theo tier |
| Hạ tầng vận hành | Đội nội bộ | Đội nội bộ | Provider một phần |
| Capacity scaling | Tự orchestrate | Tự orchestrate | API/service limits |
| TCO low load | Có min node + labor | Có min node + license | Có thể có min/usage |
| TCO high load | Phụ thuộc efficiency | Phụ thuộc efficiency + license | Phụ thuộc unit rate/quotas |
| Custom tuning | Thường sâu hơn | Thường sâu hơn | Có thể bị giới hạn |
| DR controls | Tự thiết kế/kiểm | Tự + support | Service features + customer runbooks |
| Exit | Có thể kiểm data file/API | License/contract constraints | Export/egress/API lock-in |

### 41.1. Không mặc định managed tốt hơn

Managed hấp dẫn khi team nhỏ, yêu cầu time-to-market và operations complexity cao; nhưng phí usage lớn hoặc constraints về dữ liệu/latency có thể làm tự vận hành phù hợp hơn.

### 41.2. Không mặc định self-managed rẻ hơn

Nếu cần 24/7, multi-region, backup drills, security hardening và đội DBA, chi phí vận hành có thể lớn hơn subscription.

### 41.3. Hybrid có thể hợp lý

Ví dụ: NoSQL authoritative managed, Redis cache self-managed hoặc ngược lại. Nhưng mỗi hệ tăng integration/ops và failure modes; không chọn hybrid chỉ để tối ưu một bảng giá.

## 42. Vendor lock-in và quyền rời đi

### 42.1. Data format

Có thể export full records, metadata, indexes, TTL, event positions và auth mappings ra format mở không? Có rate limits và cost?

### 42.2. Query semantics

Document query/indexing, consistency, transaction, CDC và partition keys có thể khác dù cả hai gọi là NoSQL.

### 42.3. Dual run khi migration

Để giữ writes, thường cần backfill + change capture + reconciliation + cutover. Trong thời gian ấy phải trả tiền cả hai nền tảng và băng thông.

### 42.4. Operator skills

Đội đã quen một system hoặc cloud SDK có thể cần đào tạo khi đổi; đó là chi phí thật và rủi ro incident.

### 42.5. Thử “exit drill”

POC nên export một data sample đủ lớn, restore sang nơi khác, verify ID/version/TTL/invariant; đừng chờ tới ngày hợp đồng kết thúc.

## 43. Security & contract risk register

| Rủi ro | Tín hiệu | Đối sách |
|---|---|---|
| License mismatch | Service offering chưa được rà soát | Legal check exact version/use |
| Feature missing | SSO/PITR chỉ tier cao | SKU proof, budget upgrade |
| Price uncertainty | Rời trial, request units chưa đo | POC cost telemetry, scenarios |
| Hidden egress | Cross-region egress lớn | Placement và budget transfer |
| Compliance gap | Backups ngoài vùng được phép | Residency mapping và contractual proof |
| Vendor exit | Proprietary CDC/query semantics | Export drill, migration reserve |
| Availability mismatch | SLA excludes topology/maintenance | App SLO, DR test |
| Support gap | Không có 24/7 severity 1 | Support tier hoặc internal on-call |
| Budget overrun | Autoscale tăng không giới hạn | Alerts, quotas, safeguards |
| Capacity bottleneck | Hot partitions dù cluster idle | Data model test, per-key metrics |
| Data loss | Async replication bị coi như zero RPO | Durability contract và failure drills |

### 43.1. Risk owner là bắt buộc

Mỗi `UNKNOWN` hoặc conditional feature phải có người theo dõi, deadline, workaround và tiêu chí quyết định.

### 43.2. Không biến mọi rủi ro thành giá tiền

Vi phạm điều khoản pháp lý hoặc data residency có thể không chấp nhận được dù chi phí thấp; xử lý bằng hard gate.

## 44. Quy trình lựa chọn theo các bước

1. **Thu use case**: loại workload, data size, peak, query/consistency, tenant, residency, RPO/RTO.
2. **Loại phương án không phù hợp**: correctness, security, legal licensing, region, support gates.
3. **Định danh candidate**: product/version/edition/SKU/deployment/service terms.
4. **Lập feature/limits matrix**: `YES/NO/CONDITIONAL/UNKNOWN` kèm bằng chứng.
5. **Lập workload model**: reads/writes converted units, hot keys, storage, indexes, CDC, backup.
6. **Lập cost model**: direct spend, staff/ops, DR, network, support, migration và growth.
7. **Thử POC**: cùng dataset và API workload, p99, throughput, fault/restore, billable units.
8. **Đối chiếu pháp chế và security**: licensing, DPA, IAM, audit, data residency và termination.
9. **Thử sensitivity**: low/base/peak/DR/exit, 12–36 tháng, rate changes.
10. **Viết quyết định**: lựa chọn, lý do, tradeoffs, unknowns, approval, fallback và review date.

### 44.1. Đừng đảo thứ tự

Nếu chọn phương án vì giá quảng cáo rồi mới tìm hiểu consistency/edition/license, có thể phải re-platform ngay trước production.

### 44.2. Khi không có đủ dữ liệu

Ghi “chưa xác minh”, không ước lượng giả như một fact. Có thể dùng conditional recommendation kèm tiêu chí kiểm trước khi ký.

### 44.3. Đặt lịch đánh giá lại

Giá, license, edition features, workload và quy định có thể đổi. Một quyết định đúng hôm nay không có nghĩa giữ nguyên vô thời hạn.

## 45. Mẫu decision memo ngắn

~~~markdown
# Database selection decision

## Use scope
- Workload:
- Data/regions:
- Consistency and RPO/RTO:
- Internal/SaaS/redistribution:

## Candidates
| Product | Version | Edition/SKU | Deployment |
|---|---|---|---|
| Candidate A | ... | ... | ... |
| Candidate B | ... | ... | ... |

## Hard gates
| Gate | A | B | Evidence |
|---|---|---|---|
| License/use | ... | ... | official terms |
| Residency | ... | ... | region/DPA |
| Recovery | ... | ... | restore POC |
| Correctness | ... | ... | tests |

## Measured POC
- Dataset and load profile:
- p99/errors:
- Billable units/cost:
- Backup/restore result:

## Three-year TCO
- Base/peak/DR/exit assumptions:
- Cost ranges and sensitivity:
- Operational staffing:

## Decision
- Selected option:
- Tradeoffs and non-goals:
- Remaining risks and owners:
- Conditions before production:
~~~

### 45.1. Evidence là một phần của quyết định

Link tới terms, POC results, rate card date, invoices, support statement và security review để người mới có thể hiểu vì sao chọn phương án ấy.

### 45.2. Không dùng memo thay hợp đồng

Legal review và signed agreements là nguồn quyền sử dụng, không phải một câu “licensed” trong tài liệu kiến trúc.

## 46. Bài toán tổng hợp: nền tảng đặt phòng nhiều tenant

Giả sử hệ dùng Java Spring và cần:

~~~text
Tenants:
    2,000 small tenants
    4 enterprise tenants with burst traffic

Data:
    50 million Order/Reservation documents
    average logical 2 KB per document
    40% annual growth

Queries:
    get booking by ID
    list bookings by tenant and month
    conditional reserve one slot

Requirements:
    approved region only
    strict tenant isolation
    PITR and tested restore
    24/7 incident path
    no duplicate booking under retries
~~~

### 46.1. License hard gate

Nếu dịch vụ cung cấp chỉ booking API thì mô tả rõ, không tự gọi là database-as-a-service; nếu sau này cung cấp API cho khách hàng truy vấn trực tiếp database, phải rà soát license/service agreement lại.

### 46.2. Edition hard gate

Kiểm SSO/audit/backup/KMS/region và transaction/conditional-write limits tại exact tier. Nếu Community cần tự làm audit, tính effort/risks vào phương án.

### 46.3. Cost

Tính data+index bytes, billable read/write units, 2–3 regions nếu cần, backup/PITR, offsite, support và engineer hours. Đừng dùng 50 triệu × 2 KB làm toàn bộ bill.

### 46.4. Workload spike

Whale tenants có thể tạo hot partition; POC phải dùng skew, không chỉ uniform random IDs. Capacity theo burst và N−1.

### 46.5. Correctness

No double booking là hard gate; một storage option giá thấp nhưng không hỗ trợ invariant trong architecture dự kiến phải bị loại hoặc phải có authority layer riêng được kiểm.

## 47. Những sai lầm phổ biến

### “Community là miễn phí hoàn toàn”

Không có license fee không xóa infrastructure, staff, security, backups và incident cost.

### “Source code công khai là open source”

Không chắc; phải xem license có quyền sử dụng thực tế gì và nó có được công nhận OSS không.

### “Tất cả phiên bản cùng sản phẩm có một license”

Không chắc, đặc biệt khi dự án thay điều khoản hoặc multi-license.

### “Driver Apache license nghĩa server Apache license”

Sai; mỗi artifact có license riêng.

### “Managed service có quyền pháp lý giống tự host Community”

Không; khách hàng thường giao kết service terms và entitlement khác.

### “Chỉ cần so giá mỗi triệu requests”

Không: billable units phụ thuộc item size, consistency, scan, indexes và transaction.

### “Storage GB là kích thước JSON trên disk”

Không: replication, index, metadata, compression và provider billing khác nhau.

### “Managed không cần SRE”

Sai: app SLO, key/index design, IAM, backup drills, incident response và cost ownership vẫn cần.

### “Cứ có SLA 99,9% là ứng dụng đạt 99,9%”

Không: còn app, network, auth, downstream và exclusions.

### “PITR bật là xong”

Không: retention window, restore API, DR site và reconciliation phải được kiểm.

### “Có multi-region là RPO bằng 0”

Không nếu replication async/conflict model và failover semantics cho phép mất acknowledged writes.

### “GSI/index chỉ làm reads rẻ hơn”

Không: index storage/write maintenance và query plan là tradeoff.

### “Một test 10.000 records đủ dự báo 1 TB”

Không: partition skew, compaction, cache và read amplification khác.

### “Dùng giá tháng đầu ×36 là TCO ba năm”

Không khi growth, support, pricing, DR và migration costs thay đổi.

### “Giá niêm yết luôn là giá phải trả”

Không: tax, discount, region, private pricing, minimum spend và currency có thể khác.

### “Compatible API nghĩa migrate không mất công”

Không: consistency, transactions, CDC, index, TTL và ops semantics có thể khác.

### “Một candidate vi phạm residency vẫn có thể thắng nhờ điểm giá”

Không: residency/license/correctness là hard gates, không phải điểm cộng trừ tùy ý.

## 48. Checklist ký duyệt lựa chọn NoSQL

1. Đã viết rõ **workload và phạm vi sử dụng** chưa?
2. Đã phân biệt nội bộ, SaaS backend, DB-as-a-service và binary redistribution chưa?
3. Đã ghi exact product/version/edition/SKU/deployment chưa?
4. Đã lấy license chính thức đúng artifact/version chưa?
5. Đã kiểm open-source vs source-available vs commercial đúng chưa?
6. Đã có legal review khi cung cấp dịch vụ/phân phối/modified source chưa?
7. Đã kiểm driver, plugin, connector và container licenses chưa?
8. Đã xác minh quyền dùng cho staging, production và DR chưa?
9. Đã có feature matrix theo phiên bản với nguồn và ngày chưa?
10. Có hard gates cho correctness, residency và security chưa?
11. Đã kiểm SSO, audit, KMS, encryption, network isolation chưa?
12. Đã kiểm PITR/backup/restore scope theo tier chưa?
13. Đã kiểm support severity và SLA exclusions chưa?
14. Đã biết shared responsibility của managed service chưa?
15. Đã thu read/write rate, item sizes và query patterns thực chưa?
16. Đã xác định consistency/transaction semantics của từng operation chưa?
17. Đã tính billable units thay vì chỉ đếm HTTP requests chưa?
18. Đã tính index, CDC, backup, network và monitoring chưa?
19. Đã tránh đếm storage/replicas hai lần chưa?
20. Đã tính N−1, peak burst, autoscale limits và hot partitions chưa?
21. Đã định giá nhân sự on-call/tuning/upgrade cho self-managed chưa?
22. Đã dự báo storage/workload growth 12–36 tháng chưa?
23. Đã thử sensitivity low/expected/peak/DR/exit chưa?
24. Đã kiểm cost alerts, quota, budget owner và negotiated discounts chưa?
25. Đã chạy POC với dataset representative và p99/errors chưa?
26. Đã đo usage/cost từ service metrics hoặc invoice sample chưa?
27. Đã chạy failover và restore drill trong POC chưa?
28. Đã đánh giá API compatibility và exit/migration plan chưa?
29. Đã lưu evidence của vendor/SKU/price effective date chưa?
30. Đã có decision memo, risk owners và lịch review lại chưa?

## 49. Bài tập thực hành

### Bài 1 — Tách bốn trục

Cho một quảng cáo “Database X Enterprise managed, secure, 99.99% SLA, free trial”, hãy tách những điều thuộc edition, license, service và price. Thông tin nào chưa được chứng minh?

### Bài 2 — Community vs free

Một công ty tải Community binary không mất phí. Liệt kê ít nhất tám khoản TCO không phải license fee.

### Bài 3 — Open source vs source-available

Tại sao có mã nguồn công khai chưa đủ để khẳng định software là OSI open source? Nêu những câu hỏi cần đặt với một SSPL/BSL/custom-license project.

### Bài 4 — SaaS backend

Ứng dụng booking dùng database nội bộ, clients chỉ gọi booking API. Hãy viết use-description cho legal và giải thích vì sao không được tự kết luận đó chắc chắn giống DB-as-a-service.

### Bài 5 — Distribution

Một công ty nhúng NoSQL binary vào appliance giao cho khách hàng. Những nghĩa vụ/giấy phép cần kiểm khác việc chạy trên server riêng là gì?

### Bài 6 — Version

Hai phiên bản khác nhau của cùng sản phẩm có thể chịu licenses khác nhau. Thiết kế hồ sơ artifact/version/license evidence để kiểm upgrade.

### Bài 7 — Driver license

Java driver mang Apache-2.0, server mang license khác. Tại sao không thể suy license của server từ driver?

### Bài 8 — Feature matrix

Lập matrix cho Community, Enterprise, Managed Basic và Managed Advanced với PITR, SSO, audit, BYOK, CDC, multi-region và support.

### Bài 9 — Hard gate

Candidate A giá thấp nhưng backup nằm ngoài vùng dữ liệu được phép. Candidate B đắt hơn nhưng đúng residency. Bạn có dùng weighted score để cho A thắng không? Vì sao?

### Bài 10 — SLA

DB có SLA availability 99,9% nhưng API auth thường xuyên lỗi. Phân biệt database SLA và application SLO; đề xuất phép đo.

### Bài 11 — Support

Hợp đồng ghi “sev1 response within 30 minutes”. Có nghĩa outage được sửa trong 30 phút không? Cần hỏi vendor thêm gì?

### Bài 12 — Storage

50 triệu documents ×2 KB tương đương bao nhiêu GB decimal logic? Nêu các khoản phải tính thêm cho self-managed 3 replicas.

### Bài 13 — Read units

Một API gọi một range query trả 100 documents, một API khác đọc một item. Vì sao một triệu HTTP requests không đồng nghĩa một triệu billable read units?

### Bài 14 — Transaction cost

Thêm conditional writes và transactional batches vào workload. Bạn sẽ kiểm pricing/API semantics nào trước khi estimate?

### Bài 15 — Index tradeoff

Index mới giảm query units 40% nhưng tăng write costs và index storage. Lập phép so TCO sau thay đổi.

### Bài 16 — Managed example

Tính lại bảng 600 triệu read units, 60 triệu write units, 500 GB data, 120 GB index, 500 GB backup, 300 GB egress và hai fixed fees; giải thích 666 USD chỉ là số giả định.

### Bài 17 — Self-managed example

Tính node, disks, backups, network, monitoring, support và 30 giờ nhân sự; vì sao không thể kết luận self-managed đắt hơn managed nếu chưa đo cùng SLA/workload?

### Bài 18 — Growth

Data 500 GB tăng 40%/năm. Ước lượng data storage sau ba năm với tăng trưởng lũy kế, rồi xem effect lên index/backup.

### Bài 19 — Peak load

Traffic trung bình 3.000 RPS nhưng peak 15.000 RPS trong 15 phút. So provisioned capacity, on-demand/serverless và khả năng autoscale.

### Bài 20 — Hot tenant

Một tenant chiếm 70% writes trên một partition. Vì sao chỉ tăng provisioned capacity không chắc giải quyết được throttling?

### Bài 21 — Multi-region

Đề xuất kiến trúc HA theo ba AZ so với multi-region; so effects lên RPO/RTO, networking, data residency và price.

### Bài 22 — Backup

Giữ PITR 7 ngày, snapshot weekly 12 tuần và một bản immutable offsite. Liệt kê storage, transfer, key, restore-drill và support cost.

### Bài 23 — License của DR

Một commercial database chạy primary tại A và standby tại B. Hỏi vendor những gì về active/passive DR license entitlement và support?

### Bài 24 — DynamoDB

Thiết kế phép đo cho read/write units, hot keys, GSI, PITR và global replication, không sử dụng host-level disk metrics.

### Bài 25 — Cosmos DB

Lập POC về partition key, RU charges, consistency, indexing policy và autoscale. Chọn dữ liệu skew đủ để đo hot partitions.

### Bài 26 — MongoDB

Đối chiếu self-managed Community, commercial Enterprise và Atlas theo license/use, audit/backup/support, query/index và TCO.

### Bài 27 — Cassandra

Apache Cassandra không mất commercial engine license fee ở distribution phù hợp. Ước lượng chi phí repair, compaction, disk headroom, backup và 24/7 on-call.

### Bài 28 — Redis

So Redis như cache có thể rebuild với Redis như nguồn state nghiệp vụ. Những thay đổi nào về durability, backup và cost?

### Bài 29 — OpenSearch/Elasticsearch

So source license của một distribution/version cụ thể, managed service terms, security/vector features và index storage costs; vì sao không được so chung theo logo?

### Bài 30 — Provider lock-in

Để chuyển database managed sau ba năm, cần export/CDC, dual run, schema translation, egress và engineer hours. Lập một exit-cost plan.

### Bài 31 — Price change

Giá usage-based tăng 25% năm thứ hai, doanh nghiệp được giảm 15% theo committed spend. Thiết kế scenario model có effective dates.

### Bài 32 — Security

Một edition không hỗ trợ audit theo yêu cầu. Team đề xuất tự xây. Đánh giá license, effort, integrity, security và support implications.

### Bài 33 — POC

Thiết kế POC có 10 triệu synthetic documents, hot tenants, point reads, conditional writes, index build, backup restore và đo billable units.

### Bài 34 — Chấm điểm

Tạo weighted matrix với business fit 25%, performance 20%, operations 15%, security 15%, TCO 15%, portability 10%. Thử đổi TCO weight và nêu rủi ro kết quả thay đổi.

### Bài 35 — Báo cáo lựa chọn

Viết decision memo cho một Java booking service: scope, candidate editions, license risks, hard gates, measured benchmark, TCO 36 tháng, support/DR requirements, exit plan, owners và điều kiện đưa lên production.

---

**Kết luận:** **Đối chiếu edition, giấy phép, dịch vụ và chi phí theo phạm vi sử dụng** là một bài toán kiến trúc, pháp lý và tài chính kết hợp. Edition quyết định tính năng/giới hạn, giấy phép quyết định quyền sử dụng và nghĩa vụ, dịch vụ quyết định phân chia trách nhiệm vận hành, còn tổng chi phí phụ thuộc **quy mô dữ liệu, read/write units, query shape, indexes, replication, backup, network, support, con người và tăng trưởng**. Không dùng tên thương hiệu hay “Community miễn phí” để suy quyền hoặc chi phí; không dùng giá niêm yết để suy SLO. Hãy đặt **hard gates** cho licensing, correctness, data residency và recovery, rồi dùng **feature matrix theo phiên bản, POC tải đại diện, TCO nhiều kịch bản và kế hoạch exit** để lựa chọn có thể kiểm chứng. Một quyết định NoSQL tốt là quyết định phù hợp **workload và quyền sử dụng thật**, vận hành được qua sự cố và có chi phí/rủi ro chấp nhận được trong toàn vòng đời.
