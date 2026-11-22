# Đánh giá kiến trúc bằng Azure Well-Architected Review

## 1. Vì sao kiến trúc chạy được chưa chắc đã tốt?

Một ứng dụng có thể được triển khai thành công lên Microsoft Azure, trả HTTP 200 và đáp ứng tải thử ban đầu nhưng vẫn có điểm yếu nghiêm trọng: database không có cơ chế khôi phục phù hợp, mọi thành phần phụ thuộc vào một vùng, quyền quản trị quá rộng, việc triển khai phải làm thủ công, chi phí không có người chịu trách nhiệm hoặc hệ thống không chịu được lượng request đột biến. Những vấn đề đó thường chỉ lộ ra khi có sự cố hoặc khi mở rộng quy mô.

Trong chương **Kiến trúc và thực hành tổng hợp** của module `CLOUD_PROVIDERS_AZURE`, bài học này hướng dẫn đánh giá một **workload** trên Azure theo **Azure Well-Architected Framework** và quy trình **Azure Well-Architected Review**. Đây là bài tổng hợp kiến thức từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage, dữ liệu, triển khai, bảo mật, giám sát và kiểm soát chi phí.

**Mục tiêu không phải đạt điểm đẹp trên bảng hỏi**, mà là tìm ra rủi ro kiến trúc thực tế, chứng minh bằng dữ kiện và chọn cải tiến đem lại giá trị lớn nhất so với nỗ lực, chi phí và rủi ro thay đổi.

Sau bài học, bạn có thể:

1. Xác định ranh giới workload, người sở hữu, hành trình quan trọng và các yêu cầu phi chức năng trước buổi đánh giá.
2. Giải thích và áp dụng **năm trụ cột** Azure Well-Architected: Reliability, Security, Cost Optimization, Operational Excellence và Performance Efficiency.
3. Sử dụng quy trình Well-Architected Review để tự đánh giá, ghi giả định, liên kết bằng chứng và kiểm tra các khuyến nghị.
4. Đối chiếu câu trả lời với telemetry, cấu hình, kiểm thử và các công cụ hỗ trợ như Azure Advisor, Azure Monitor, Azure Policy.
5. Lập risk register, ưu tiên remediation và xây roadmap với owner, điều kiện nghiệm thu, cách đo hiệu quả.
6. Thực hiện một bài đánh giá capstone cho ứng dụng nhiều tầng và trình bày các trade-off giữa độ tin cậy, hiệu năng, bảo mật và chi phí.

## 2. Azure Well-Architected Framework và Review là gì?

**Azure Well-Architected Framework (WAF)** là tập hợp các nguyên tắc, hướng dẫn thiết kế và phương pháp đánh giá nhằm cải thiện chất lượng workload trên Azure. **Azure Well-Architected Review** là hình thức tự đánh giá có cấu trúc dựa trên các trụ cột của framework: nhóm trả lời câu hỏi về thiết kế và vận hành workload, xem những khuyến nghị được cung cấp rồi lập kế hoạch cải tiến.

Một số phân biệt quan trọng:

| Thành phần | Dùng để làm gì? | Không nên hiểu nhầm |
| --- | --- | --- |
| **Well-Architected Framework** | Nguyên tắc và cách cân nhắc thiết kế theo năm trụ cột | Không phải một SKU Azure hay dịch vụ tự sửa kiến trúc |
| **Well-Architected Review** | Bộ câu hỏi/đánh giá để phát hiện khoảng trống và nhận khuyến nghị | Không tự xác minh mọi cấu hình, không chứng nhận an toàn hoặc compliance |
| **Azure Advisor** | Đưa ra những đề xuất dựa trên tài nguyên/tín hiệu Azure được hỗ trợ | Không thay thế đánh giá nhu cầu nghiệp vụ và dependency toàn workload |
| **Azure Policy** | Kiểm tra/áp dụng các quy tắc quản trị theo định nghĩa và scope | Resource compliant không đồng nghĩa ứng dụng đáp ứng SLO/RPO |
| **Azure Monitor / Application Insights** | Cung cấp metric, log, trace, alert và bằng chứng vận hành | Không tự kết luận mọi quyết định kiến trúc đều hợp lý |
| **Architecture review của đội** | Kiểm chứng bằng kiến thức hệ thống, quy trình, test và quyết định quản trị | Không nên chỉ dựa vào ý kiến cá nhân hoặc một dashboard |

Câu trả lời trên Well-Architected Review là **self-assessment**: nếu nhóm chọn “đã có disaster recovery” nhưng chưa từng restore backup hoặc thử failover, kết quả đánh giá không chứng minh DR đạt yêu cầu. Mọi khuyến nghị quan trọng cần được liên kết với **bằng chứng hoặc phép thử**.

### 2.1. Vì sao phải đánh giá ở cấp workload?

Workload là một tập hợp thành phần cùng phục vụ một kết quả nghiệp vụ, không nhất thiết trùng với một resource group hoặc subscription. Ví dụ workload `orders` có:

- API trong một resource group ứng dụng.
- Azure SQL hoặc database trong resource group dữ liệu.
- Azure Front Door/ingress và Azure Firewall do nhóm platform quản lý.
- Azure Monitor workspace và Key Vault dùng chung.
- CI/CD, xác thực Microsoft Entra ID, nhà cung cấp thanh toán bên ngoài.

Nếu chỉ xem các VM của API, nhóm sẽ bỏ qua điểm lỗi của database, route, secrets, identity hoặc dịch vụ thanh toán. Vì vậy cần **định nghĩa workload trước khi đánh giá**, rồi xem các subscription/resource group như phạm vi kỹ thuật bên trong kiến trúc.

### 2.2. Khi nào nên thực hiện review?

Thực hiện ít nhất ở những cột mốc có quyết định thiết kế quan trọng:

- Trước khi đưa một hệ thống mới lên production.
- Trước migration lớn hoặc thay đổi kiến trúc từ VM sang PaaS/AKS.
- Sau sự cố nghiêm trọng, lỗi dữ liệu, sự kiện bảo mật hoặc SLO bị vi phạm.
- Khi tải tăng nhanh, chi phí vượt dự báo hoặc workload đổi mức độ quan trọng.
- Theo chu kỳ vận hành dựa trên rủi ro của doanh nghiệp.

Một review có thể dẫn tới quyết định **không thay đổi** nếu các lựa chọn hiện tại có bằng chứng và phù hợp yêu cầu. Mục tiêu là quyết định có chủ đích, không phải áp dụng mọi best practice bằng mọi giá.

## 3. Năm trụ cột của Azure Well-Architected

~~~mermaid
flowchart TB
    W["Workload và mục tiêu nghiệp vụ"] --> R["Reliability"]
    W --> S["Security"]
    W --> C["Cost Optimization"]
    W --> O["Operational Excellence"]
    W --> P["Performance Efficiency"]
    R --> G["Rủi ro, trade-off và kế hoạch cải tiến"]
    S --> G
    C --> G
    O --> G
    P --> G
~~~

| Trụ cột | Câu hỏi cốt lõi | Bằng chứng tiêu biểu |
| --- | --- | --- |
| **Reliability – Độ tin cậy** | Khi thành phần hỏng, dịch vụ có tiếp tục hoặc khôi phục trong mục tiêu? | SLO, health probes, availability zones, backup restore, DR test, RTO/RPO |
| **Security – Bảo mật** | Dữ liệu và quyền truy cập có được bảo vệ xuyên suốt vòng đời? | Threat model, RBAC, identity, secret management, encryption, audit, vulnerability findings |
| **Cost Optimization – Tối ưu chi phí** | Tổ chức có trả đúng mức cho giá trị và mức dùng cần thiết? | Cost Analysis, budget, unit cost, utilization, reserved capacity, ownership |
| **Operational Excellence – Vận hành xuất sắc** | Hệ thống có thể triển khai, quan sát, xử lý sự cố và thay đổi an toàn? | IaC, pipeline, runbook, alert, postmortem, deployment/rollback evidence |
| **Performance Efficiency – Hiệu quả hiệu năng** | Hệ thống đáp ứng tải hiện tại và tương lai với công suất hợp lý? | Load test, p95/p99, throughput, autoscale, quota, bottleneck analysis |

Không có trụ cột nào “thắng” tuyệt đối. Có thể phải **trả thêm chi phí cho vùng dự phòng để đạt Reliability**, hoặc giữ headroom để bảo vệ latency khi một zone gặp sự cố; đó là trade-off hợp lý nếu được đo và chấp thuận.

### 3.1. Reliability: ứng dụng có sống sót khi lỗi xảy ra?

Các câu hỏi mẫu:

1. Có định nghĩa SLI/SLO, RTO/RPO phù hợp ưu tiên nghiệp vụ không?
2. Những lỗi nào được chấp nhận: một process, một VM, một Availability Zone, một region, một dependency bên ngoài?
3. Compute đã phân tán instance đúng vùng/zone khi dịch vụ hỗ trợ chưa? Ingress có chuyển traffic khỏi backend lỗi không?
4. Database, storage và queue có chính sách redundancy/failover phù hợp, được kiểm thử không?
5. Có backup/restore, diễn tập DR, các bước khôi phục dữ liệu và chống lỗi logic/xóa nhầm không?
6. Client có retry hữu hạn, exponential backoff, jitter và idempotency cho giao dịch ghi không?
7. Có năng lực xử lý sau khi mất một zone, hay tất cả instance còn lại sẽ quá tải?

**Ví dụ:** App Service có zone redundancy ở cấu hình hỗ trợ, nhưng database chỉ một điểm phục vụ hoặc DNS ingress trỏ trực tiếp đến một VM. Kết luận “workload đã multi-zone” là **không chính xác ở cấp end-to-end**.

### 3.2. Security: bảo vệ dữ liệu, danh tính và quyền

Các câu hỏi mẫu:

1. Có mô hình phân loại dữ liệu và threat modeling cho các đường tấn công quan trọng?
2. Quyền Entra ID/RBAC có theo least privilege, phân tách production/non-production và có rà soát định kỳ không?
3. Workload dùng Managed Identity hoặc phương án xác thực được quản lý khi có thể, thay cho secret hard-coded?
4. Secrets/keys được quản lý trong Key Vault hoặc cơ chế phù hợp, có rotation, audit và giới hạn truy cập?
5. Network có phân đoạn rõ ràng: public ingress, private endpoints, NSG, firewall, egress và DNS phù hợp?
6. Có TLS/encryption theo dịch vụ, policies, bảo vệ dữ liệu ở trạng thái nghỉ và khi truyền?
7. Có quy trình cập nhật dependency, image scanning, vulnerability management, bảo vệ pipeline và ứng phó sự cố?

**Ví dụ:** Dùng Private Endpoint cho Azure SQL nhưng service principal vẫn có quyền quá rộng và password nằm trong pipeline variable không được bảo vệ. Private networking chỉ giảm một nhóm nguy cơ; nó **không thay thế** bảo vệ danh tính và credential.

### 3.3. Cost Optimization: tổng chi phí có tương xứng giá trị?

Các câu hỏi mẫu:

1. Mỗi workload có owner và phạm vi phân bổ chi phí rõ không?
2. Budget/alerts có đủ để phát hiện chi phí tăng nhanh, và có người hành động?
3. Compute, database, storage, network, monitoring có được rightsizing dựa trên sử dụng thật?
4. Có biết chi phí trên một giao dịch thành công, job hoàn tất hoặc đơn vị nghiệp vụ?
5. Những phần tải nền ổn định có được đánh giá Reservations/Savings Plan dựa trên dữ liệu đủ điều kiện theo giờ?
6. Chi phí dùng chung, chi phí egress, backup/replication và unused commitments đã được tính?
7. Những tối ưu tiết kiệm có ảnh hưởng yêu cầu SLO, RTO/RPO hoặc bảo mật không?

**Ví dụ:** Giảm số replica từ ba xuống một có thể giảm chi phí compute nhưng làm hỏng khả năng chịu lỗi Availability Zone. Một đánh giá tốt sẽ **tính lợi ích tài chính và rủi ro downtime**, không đánh dấu cải tiến chỉ vì bill giảm.

### 3.4. Operational Excellence: có thể vận hành lặp lại và an toàn?

Các câu hỏi mẫu:

1. Hạ tầng có được quản lý bằng Bicep/Terraform/ARM hoặc phương pháp cấu hình có kiểm soát không?
2. CI/CD có review, kiểm thử, staged rollout và rollback được kiểm chứng?
3. Logs, metrics, traces, synthetic tests và alert có gắn với SLI quan trọng?
4. On-call, incident severity, runbook, Azure Support escalation và post-incident review có owner?
5. Có quản lý drift, configuration, quota, certificates, backup và thay đổi quyền?
6. Có kiểm tra hoạt động của environment mới và thực hiện các bài diễn tập game day?
7. Có sử dụng tự động hóa an toàn, idempotent và theo dõi audit trail?

**Ví dụ:** Nhóm tuyên bố “rollback trong 5 phút” nhưng quy trình rollback yêu cầu chuyên gia chỉnh DNS thủ công và chưa được diễn tập. Đây là **giả định chưa kiểm chứng**, không phải một capability đã đạt.

### 3.5. Performance Efficiency: đáp ứng tải với tài nguyên hợp lý

Các câu hỏi mẫu:

1. Có mục tiêu response time p95/p99 và throughput cho hành trình quan trọng?
2. Đã load test theo tải đỉnh, burst và lỗi một zone chưa?
3. Các nghẽn CPU, memory, disk, network, connections, throttling, database queries và cache được đo ra sao?
4. Có autoscale đúng metric, cooldown và capacity floor; quota/số instance có đáp ứng không?
5. Có kiến trúc async/queue, caching hoặc data partition phù hợp?
6. Có kiểm tra hiệu năng liên vùng, độ trễ với downstream và chi phí egress?
7. Khi tăng quy mô, hiệu năng có tăng tương xứng hay một dependency tập trung thành bottleneck?

**Ví dụ:** Tăng VM size có thể cải thiện CPU nhưng không giải quyết database connection pool bị hết hoặc IOPS bị giới hạn. Cần đo **nút thắt thực** trước khi quyết định scale.

## 4. Dữ liệu đầu vào bắt buộc trước buổi review

Không nên mở bảng hỏi ngay khi nhóm chưa thống nhất nhu cầu nghiệp vụ. Một buổi review chất lượng cần một **workload profile**.

### 4.1. Mẫu workload profile

~~~yaml
workload:
  name: orders-prod
  business_owner: "Trưởng nhóm sản phẩm Orders"
  technical_owner: "SRE và Orders Engineering"
  criticality: "Business-critical (giả định)"
  environments:
    - production
    - staging
  primary_region: "<azure-region>"
  subscriptions:
    - "<subscription-id>"
  primary_journeys:
    - "Tạo đơn hàng và xác nhận thanh toán"
    - "Xem trạng thái đơn hàng"
  dependencies:
    - "Azure ingress"
    - "Application compute"
    - "Azure SQL database"
    - "Queue/worker"
    - "Azure Storage"
    - "Microsoft Entra ID / Key Vault"
    - "Payment provider"
  objectives:
    availability_slo: "99.9% mỗi tháng, giả định"
    api_p95_latency: "< 500 ms tại tải thiết kế, giả định"
    rto: "30 phút, giả định"
    rpo: "5 phút cho dữ liệu được phép mất, giả định"
  business_constraints:
    - "Không tạo trùng giao dịch thanh toán"
    - "Dữ liệu cá nhân được bảo vệ"
    - "Chi phí không vượt ngân sách đã duyệt"
~~~

Đây là **mẫu phỏng dựng yêu cầu** để thảo luận, không phải YAML do Azure Well-Architected Review tự nhập hoặc xuất. Thay mục tiêu bằng cam kết do business owner duyệt. Nếu nghiệp vụ không thể chấp nhận mất giao dịch đã xác nhận, **RPO 5 phút** có thể không phù hợp cho luồng đó; cần phân loại dữ liệu và thiết kế đối soát riêng.

### 4.2. Vẽ ranh giới và đường đi quan trọng

~~~mermaid
flowchart LR
    U["Khách hàng"] --> FD["Azure ingress / WAF"]
    FD --> API["Orders API"]
    API --> DB["Azure SQL"]
    API --> Q["Queue"]
    Q --> WK["Worker"]
    WK --> ST["Blob Storage"]
    API --> PAY["External payment provider"]
    API --> KV["Key Vault / Managed Identity"]
    OPS["IaC / CI-CD / On-call"] -.-> API
    OBS["Azure Monitor / App Insights"] -.-> FD
    OBS -.-> API
    OBS -.-> DB
~~~

Sơ đồ này chưa nói thành phần nào thực sự đã zone-redundant hoặc có private endpoint; mọi thuộc tính đó phải được ghi trong **bản triển khai thực tế**. Đánh dấu trust boundary (Internet, VNet, PaaS, third-party), dữ liệu nào đi qua mỗi tuyến, và quyền truy cập ở từng bước.

### 4.3. Danh sách tài liệu và bằng chứng

| Dữ kiện | Chủ sở hữu | Bằng chứng hoặc nơi lấy |
| --- | --- | --- |
| Kiến trúc hiện tại, dependency, traffic flow | Solution architect | Sơ đồ được review, network/data flow |
| SLA/SLO, business criticality, RTO/RPO | Business + SRE | SLO document, test reports |
| Subscription, resource group, region, SKU | Platform | Resource inventory, IaC |
| RBAC, identities, access paths, secrets | Security | Role assignments, identity audit, policy compliance |
| Availability/backup/failover | Platform + DBA | Health probes, backup restore, DR drill |
| Deploy/rollback/runbook | Engineering | CI/CD configuration, incident records |
| Performance, capacity, quota | SRE | Load test, p95/p99, autoscale, service metrics |
| Chi phí, unit economics, budgets | FinOps | Cost Analysis, cost exports, budget alerts |

Thu thập chỉ những dữ liệu cần thiết. **Không** đưa password, client secret, API token, connection string có credential hoặc dữ liệu cá nhân thô vào phiếu đánh giá hay ticket kiến trúc.

## 5. Chuẩn bị phiên Well-Architected Review

Một buổi workshop không cần quá đông nhưng phải có người hiểu sự thật ở các tầng.

| Vai trò | Quyết định/phần xác nhận |
| --- | --- |
| **Business/Product owner** | Mục tiêu nghiệp vụ, mức độ quan trọng, chi phí chấp nhận |
| **Solution architect** | Ranh giới workload, trade-off và khuyến nghị |
| **App/Data owner** | Code, dependency, data correctness, database resilience |
| **Platform/Cloud engineer** | Azure subscriptions, network, IaC, quotas, operations |
| **Security/IAM lead** | Threat model, RBAC, Entra ID, network/security controls |
| **SRE/Operations** | SLO, monitoring, incident, RTO/RPO và diễn tập |
| **FinOps** | Chi phí, hiệu quả, khoản cam kết và ngân sách |

Chỉ định **facilitator** để đi theo tiêu chí và **scribe** để ghi bằng chứng, giả định, tranh luận và hành động. Người phụ trách workload phải có cơ hội sửa câu trả lời nếu bằng chứng cho thấy thực tế khác với mô tả ban đầu.

### 5.1. Phân biệt sự thật, giả định và mục tiêu

Trong mọi câu trả lời, dùng ba trạng thái:

- **Verified:** có bằng chứng cập nhật và có thể liên kết lại.
- **Assumed:** nhóm tin là đúng nhưng chưa có phép kiểm tra hoặc bằng chứng phù hợp.
- **Not implemented / Gap:** chưa có control hoặc kiến trúc tương ứng.

Có thể thêm **Not applicable** nếu câu hỏi thực sự ngoài phạm vi, nhưng phải giải thích. Không chọn “không áp dụng” chỉ để tránh một finding khó.

Ví dụ “Backup enabled” được chứng minh bằng cấu hình backup. “Recovery works within RTO” cần bằng chứng **restore drill và thời gian đo thực tế**; hai câu này không đồng nghĩa.

## 6. Quy trình sử dụng Azure Well-Architected Review

Giao diện và bộ câu hỏi có thể thay đổi theo phiên bản, nhưng phương pháp thực hiện có thể lặp lại:

1. Truy cập trải nghiệm **Azure Well-Architected Review** do Microsoft cung cấp từ tài liệu Azure Well-Architected. Đọc hướng dẫn về scope và chế độ assessment ở thời điểm sử dụng.
2. Tạo hoặc chọn bản đánh giá cho **đúng workload**; đặt tên dễ đối chiếu, chẳng hạn `orders-prod / 2026-11 / baseline`.
3. Chọn những trụ cột/bộ câu hỏi phù hợp và thống nhất phạm vi. Đánh giá đủ **năm trụ cột** khi muốn có cái nhìn tổng thể, hoặc ghi rõ lý do khi tập trung một trụ cột.
4. Trả lời từng câu dựa trên kiến trúc **đang chạy**, không trả lời theo kế hoạch sẽ triển khai quý sau.
5. Ghi **bằng chứng** vào tài liệu làm việc: link dashboard, test run, policy/architecture record, ngày xác minh và owner.
6. Xem recommendations được Review cung cấp; kiểm tra ý nghĩa với workload, mức độ ưu tiên và trade-off thực tế.
7. Xuất/lưu kết quả bằng tính năng mà trải nghiệm Review hiện tại cho phép, hoặc ghi kết quả vào **risk register/decision log** của nhóm nếu cách lưu/xuất khác.
8. Chuyển findings thành backlog cải tiến có owner và tiêu chí nghiệm thu; chọn thời điểm **review lại** sau thay đổi quan trọng.

**Review là đánh giá dựa trên câu trả lời, không có nghĩa công cụ đã quét toàn bộ tài nguyên trong subscription.** Nếu muốn đối chiếu tài nguyên thật, dùng các công cụ kiểm tra khác phù hợp và gắn dữ kiện vào từng finding.

### 6.1. Ví dụ một phiếu trả lời có bằng chứng

| Câu hỏi nội bộ tương ứng | Câu trả lời thực tế | Mức chắc chắn | Bằng chứng | Finding |
| --- | --- | --- | --- | --- |
| “Có SLO?” | Có SLO 99,9% cho endpoint đặt đơn | Verified | Dashboard SLI + tài liệu SLO | Chưa có alert theo error budget |
| “Có phương án chịu lỗi zone?” | API ở nhiều zone; SQL chưa xác minh HA zone | Assumed / Gap | IaC API, thiếu cấu hình DB | Rủi ro lỗi một zone ảnh hưởng ghi đơn |
| “Có DR?” | Backup đang chạy, chưa từng thử restore | Gap | Backup jobs, không có drill report | RTO/RPO chưa kiểm chứng |
| “Tài khoản có least privilege?” | Có role assignments, nhưng operator production có quyền rộng | Verified | RBAC export đã lọc nhạy cảm | Giảm quyền và chia vai trò |
| “Có theo dõi chi phí?” | Có subscription budget, chưa có workload unit cost | Verified + Gap | Cost Analysis và budget config | Thiếu showback theo workload |

Các câu trong bảng là **câu hỏi nội bộ minh họa**, không phải trích nguyên văn của phiên bản Azure Well-Architected Review bất kỳ.

### 6.2. Khi câu trả lời mâu thuẫn với dữ kiện

Giả sử đội ứng dụng nói “mọi tài nguyên đều private”, nhưng resource inventory phát hiện public network access trên storage account. Thay vì đánh dấu đã đạt, cần:

- Ghi chính xác cấu hình, scope và đường truy cập có thể thực sự sử dụng.
- Đánh giá xem network policies, firewall, identity và dữ liệu có tạo rủi ro truy cập không mong muốn không.
- Kiểm tra chủ sở hữu và lý do cấu hình công khai được chọn.
- Tạo finding dựa trên **bằng chứng**, không tự kết luận có lộ dữ liệu nếu chưa xác minh.

Một cấu hình public endpoint có thể được bảo vệ bằng các control khác, nhưng phải là **quyết định có hiểu biết** và phù hợp chính sách.

## 7. Sử dụng công cụ Azure làm bằng chứng bổ trợ

Bộ câu hỏi Review là một phần; Azure cung cấp dữ liệu để kiểm tra cách workload vận hành.

### 7.1. Azure Advisor và Azure Policy

**Azure Advisor** có thể gợi ý cải tiến theo các nhóm phù hợp với tài nguyên được hỗ trợ, ví dụ reliability, security, operational excellence, performance và cost. Dùng khuyến nghị làm tín hiệu điều tra và lập backlog, không áp dụng tự động tất cả.

**Azure Policy** hữu ích để phát hiện resource lệch chuẩn cấu hình của tổ chức (ví dụ một nhóm resource thiếu tag hoặc cấu hình không phù hợp với chính sách). Tuy nhiên:

- Policy compliance chỉ đánh giá các rule được định nghĩa và tài nguyên thuộc scope.
- Policy không chứng minh backup đã restore được hay giao dịch business đã thành công.
- Exemption cần có lý do, owner và thời điểm xem xét lại.

### 7.2. Azure Monitor, Application Insights và Cost Management

- **Azure Monitor**: xác minh availability, saturation, latency, CPU/IOPS, cảnh báo và xu hướng.
- **Application Insights**: request/dependency traces, exception, transaction latency và synthetic availability.
- **Log Analytics**: phân tích KQL theo thời gian và resource, tạo bằng chứng từ logs.
- **Cost Management**: chi phí theo subscription, resource group, tag hoặc workload khi tổ chức có mapping; xem actual/amortized và budget.
- **Resource Health / Service Health**: tín hiệu về trạng thái tài nguyên/dịch vụ Azure được hỗ trợ; không thay thế end-to-end monitoring.
- **Defender for Cloud và các công cụ bảo mật phù hợp**: thêm tín hiệu posture/recommendations, cần kiểm tra quyền và phạm vi tính năng.

Đừng xem “không có alert” là bằng chứng hệ thống đáng tin nếu các alerts chưa từng được cấu hình hoặc chưa kiểm thử.

### 7.3. Kiểm kê read-only bằng Azure CLI

Những lệnh dưới đây **chỉ đọc thông tin**, phải xác nhận subscription, quyền và resource group trong môi trường thực tế:

~~~bash
# Xác nhận đúng tenant/subscription.
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# Kiểm kê các tài nguyên của workload trong resource group đã biết.
az resource list \
  --resource-group rg-orders-prod \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# Xem gợi ý Advisor cho subscription đã chọn, khi có quyền.
az advisor recommendation list -o json
~~~

Một kết quả rỗng ở Advisor không chứng minh workload không có rủi ro. Công cụ chỉ đưa ra các khuyến nghị thuộc tập kiểm tra mà nó hỗ trợ, trên scope và dữ liệu hiện có.

### 7.4. KQL: đo độ sẵn sàng và hiệu năng của API

Khi ứng dụng gửi telemetry tới **workspace-based Application Insights** và có bảng `AppRequests`, ví dụ:

~~~kusto
AppRequests
| where TimeGenerated > ago(7d)
| summarize
    TotalRequests = sum(ItemCount),
    FailedRequests = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
  by AppRoleName, bin(TimeGenerated, 1h)
| extend SuccessRatePercent =
    iff(TotalRequests == 0, real(null),
        100.0 * (TotalRequests - FailedRequests) / TotalRequests)
| order by TimeGenerated asc
~~~

Kiểm tra schema thực tế vì bảng/cột và sampling có thể khác theo cách tích hợp. Nếu log sampling làm p95 hoặc error rate không đại diện, ghi giới hạn này trong review. Việc tổng hợp theo giờ giúp nhận xu hướng nhưng cần phân tích request quan trọng theo endpoint và traffic profile, không chỉ mức trung bình toàn API.

### 7.5. Đối chiếu với phép thử thật

Bất kỳ finding nào về Reliability/Performance cần phép thử phù hợp:

- Load test ở mức tải bình thường, peak và burst.
- Kiểm tra n−1 capacity khi một Availability Zone bị cô lập trong môi trường kiểm soát.
- Restore backup vào môi trường thử và so checksum/transaction state.
- Thử rollback khi release không đạt SLO.
- Thử sign-in, authorization, token và truy cập secret sau thay đổi IAM.
- Đo SLI từ **góc nhìn người dùng** thay vì chỉ theo trạng thái VM/Pod.

Báo cáo phải ghi **ngày, môi trường, phiên bản, dữ liệu kiểm thử và giới hạn phép thử**. Test ở staging tải thấp không tự chứng minh production đủ capacity.

## 8. Ví dụ capstone: khảo sát kiến trúc ứng dụng đặt hàng

Giả sử một doanh nghiệp dùng Azure cho hệ thống `orders-prod`, có 60.000 đơn thành công/tháng và ưu tiên liên tục phục vụ trong giờ cao điểm.

**Kiến trúc ban đầu (giả định):**

- Azure Front Door đưa request tới một Azure App Service plan.
- App Service chỉ có một instance thường trực, chưa xác minh cấu hình zone redundancy.
- Azure SQL Database dùng tier phù hợp tải hiện tại nhưng chưa có tài liệu failover.
- Blob Storage lưu tệp xác nhận đơn hàng; redundancy chưa được ghi trong architecture record.
- Key Vault chứa secret; ứng dụng dùng một connection string có credential ở app setting.
- CI/CD có tự động deploy nhưng rollback phải làm thủ công và chưa thử.
- Application Insights đã tích hợp; chỉ có alert CPU và HTTP 5xx.
- Cost Management có subscription budget; chưa biết cost per successful order.

**Không mặc định** các thành phần này có hoặc thiếu tính năng HA/security nếu chưa kiểm chứng SKU, region và cấu hình. Đánh giá bên dưới lấy ví dụ những giả định cần xác minh.

### 8.1. Mapping rủi ro theo trụ cột

| Trụ cột | Phát hiện giả định | Ảnh hưởng | Bằng chứng/kiểm thử cần |
| --- | --- | --- | --- |
| Reliability | API có một instance và thiếu bài test failover DB | Một lỗi instance/zone có thể gây gián đoạn | Placement, health probe, DR test |
| Security | Credential DB lưu trong app setting; quyền chưa rà soát | Nguy cơ lộ secret và quyền quá rộng | RBAC, config audit, threat model |
| Cost Optimization | Không có cost per order và chi phí shared | Khó so hiệu quả khi tăng tải | Amortized cost, owner mapping, số đơn hợp lệ |
| Operational Excellence | Rollback chưa được diễn tập; alert chưa bám SLO | Phát hiện/khôi phục chậm | CI/CD run logs, game day, on-call runbook |
| Performance Efficiency | Chưa có load test peak và quota review | Rủi ro throttling khi có chiến dịch | Benchmark, p95, connection/DB metrics |

### 8.2. Điều chỉnh kiến trúc theo finding

Một kế hoạch cải tiến khả thi có thể là:

1. Bổ sung replica/zone-aware architecture **nếu dịch vụ, SKU và region hỗ trợ**, đo capacity sau khi mất một zone; xác minh mức sẵn sàng database và storage tương ứng.
2. Rà quyền RBAC, chuyển truy cập Azure PaaS sang Managed Identity khi được hỗ trợ, chuyển secret phù hợp vào Key Vault, áp dụng network restrictions/Private Endpoint theo threat model.
3. Áp dụng IaC có review, staged rollout và rollback plan; tổ chức game day để chứng minh quy trình.
4. Thêm synthetic transactions cho luồng đặt đơn và alert theo error rate/latency thay vì chỉ CPU.
5. Bật báo cáo chi phí trực tiếp + shared, xác định unit cost; theo dõi Reserved/Savings Plan khi tải nền đủ ổn định.
6. Benchmark từ tải bình thường đến peak để điều chỉnh autoscale, database SKU và quota mà không đánh đổi SLO.

Không triển khai các giải pháp này ngay lập tức trên production từ một assessment. Mỗi thay đổi cần **design review, quyền phê duyệt, phương án rollback và kiểm thử**.

## 9. Đánh giá và ưu tiên rủi ro một cách minh bạch

Azure Well-Architected Review cung cấp recommendations theo thiết kế/bộ câu hỏi của Microsoft. Để biến thành backlog, nhóm có thể lập **ma trận ưu tiên nội bộ**. Ma trận này **không phải điểm số chính thức của Microsoft**.

### 9.1. Sổ rủi ro (risk register)

| ID | Trụ cột | Rủi ro | Tác động 1–5 | Khả năng 1–5 | Điểm I×L | Owner |
| --- | --- | --- | ---: | ---: | ---: | --- |
| R-01 | Reliability | Không kiểm chứng failover database | 5 | 3 | 15 | Data/SRE |
| S-01 | Security | Credential ứng dụng có phạm vi truy cập quá rộng | 5 | 3 | 15 | Security/App |
| O-01 | Operational Excellence | Không có rollback đã diễn tập | 4 | 3 | 12 | Engineering |
| P-01 | Performance Efficiency | Chưa kiểm thử peak throughput | 4 | 3 | 12 | SRE |
| C-01 | Cost Optimization | Thiếu phân bổ chi phí theo workload | 3 | 4 | 12 | FinOps |

**Thang 1–5 chỉ là ví dụ quản trị:** 1 = thấp, 5 = cao. Điểm bằng nhau không chứng minh rủi ro tương đương; tính nghiêm trọng của mất dữ liệu, hậu quả pháp lý hoặc an toàn thông tin có thể yêu cầu xử lý trước bất kể tích số. Điểm số không thay thế ý kiến security/business owner hoặc chính sách chấp nhận rủi ro.

Đối với mỗi finding, bổ sung:

- **Evidence:** nguồn, thời gian, phiên bản và mức chắc chắn.
- **Impact:** hành trình và dữ liệu ảnh hưởng, RTO/RPO/SLO liên quan.
- **Mitigation:** phương án, nỗ lực, chi phí, tác động các trụ cột khác.
- **Owner/approver:** ai thực hiện, ai chấp nhận rủi ro tồn đọng.
- **Due date:** theo độ khẩn cấp và lịch thay đổi.
- **Acceptance criteria:** phép thử khách quan xác nhận finding được xử lý.

### 9.2. Ưu tiên theo giá trị và khả năng thực thi

Một hành động có điểm rủi ro cao nhưng khó triển khai vẫn cần biện pháp tạm thời. Ví dụ:

- **Ngắn hạn:** kiểm tra backup restore, tăng alert cho database và ghi runbook thủ công.
- **Trung hạn:** triển khai HA/zone redundancy và diễn tập failover có kiểm soát.
- **Dài hạn:** tách dependency, thiết kế đa region hoặc thay đổi data model nếu RTO/RPO đòi hỏi.

Đừng che rủi ro bằng cách ghi “will fix” rồi xem như đã giải quyết. Tình trạng phải là **open, mitigated, accepted hoặc closed-with-evidence**, có owner rõ ràng.

## 10. Trade-off: không có kiến trúc “tối ưu tuyệt đối”

Một mục tiêu có thể tác động nhiều trụ cột. Ví dụ tăng số replica để giảm nguy cơ outage khiến chi phí tăng và có thể cần điều chỉnh DB connections. Bảng quyết định nên thể hiện cả lợi ích và chi phí.

| Quyết định | Lợi ích dự kiến | Tác dụng phụ | Cách kiểm chứng |
| --- | --- | --- | --- |
| Phân bố compute theo nhiều AZ | Reliability tăng khi một zone lỗi | Chi phí headroom; phụ thuộc dữ liệu/ingress | Diễn tập n−1 tại peak tải |
| Bật private endpoint/giới hạn public access | Giảm bề mặt tấn công | DNS, network và vận hành phức tạp hơn | DNS/TLS/auth synthetic tests |
| Tăng replica + autoscale | Có thêm throughput và độ dư thừa | Chi phí tăng; backend DB có thể nghẽn | Load test và DB metrics |
| Dùng cache | Giảm latency và DB read pressure | Cache invalidation, stale data, cost | Correctness test + p95 + hit ratio |
| Giảm log ingestion | Giảm chi phí monitoring | Có thể mất observability/security data | Định nghĩa log phải giữ, đo alert coverage |
| Mua cam kết compute phù hợp | Có thể giảm giá trên tải ổn định | Underutilization nếu workload đổi | Hourly eligible usage và ROI toàn kỳ |
| Multi-region active/passive | Khả năng phục hồi mất region | Replication, routing, failover và cost phức tạp | DR drill, RTO/RPO, data integrity |

Một **Architecture Decision Record (ADR)** nên ghi quyết định, bối cảnh, các phương án được cân nhắc, trade-off, người phê duyệt và bằng chứng sẽ dùng để kiểm chứng. Review tốt tạo ra những quyết định rõ ràng, không chỉ một danh sách lỗi.

### 10.1. Ví dụ ADR ngắn

~~~markdown
# ADR-007: Tăng khả năng chịu lỗi cho orders API

**Trạng thái:** Proposed
**Bối cảnh:** Một instance hiện tại; mục tiêu RTO 30 phút, SLO 99,9%.
**Các phương án:**
- A: Giữ một instance và backup/restore.
- B: Nhiều replica, phân tán zone khi cấu hình dịch vụ hỗ trợ.
- C: Thiết kế multi-region ngay từ giai đoạn này.

**Quyết định đề xuất:** B cho giai đoạn gần, kiểm tra C theo mục tiêu DR.
**Vì sao:** Hạn chế lỗi instance/zone, mức thay đổi phù hợp kế hoạch.
**Tác động:** Tăng chi phí compute, cần test backend và health probe.
**Điều kiện nghiệm thu:** N-1 load test, SLO, database failover và runbook.
**Owner/approver:** SRE lead / Product owner / Security review.
~~~

Các nội dung ADR đều là **ví dụ**, không phải cam kết rằng lựa chọn B luôn đáp ứng mục tiêu nếu tier/database chưa phù hợp.

## 11. Biến recommendations thành roadmap cải tiến

### 11.1. Tạo bảng backlog hành động

| Priority | Finding | Hành động cụ thể | Owner | Điều kiện nghiệm thu |
| --- | --- | --- | --- | --- |
| P0 | R-01: DR chưa kiểm chứng | Restore database từ backup vào môi trường cách ly, đối soát giao dịch | DBA/SRE | RTO/RPO đo được, dữ liệu hợp lệ |
| P0 | S-01: Secret quá rộng | Rà quyền, chuyển sang identity phù hợp và rotate secret | Security/App | Test quyền tối thiểu, audit log, không lộ secret |
| P1 | O-01: Rollback thủ công | Thêm staged rollout và rollback runbook; diễn tập | DevOps | Test rollback trong phạm vi được duyệt |
| P1 | P-01: Không có peak test | Chạy load test ở peak + lỗi một zone | SRE | Throughput, p95, saturation trong mục tiêu |
| P2 | C-01: Không rõ unit cost | Phân bổ direct/shared cost và tính cost/order | FinOps | Tổng đối soát, owner xác nhận |

Priority là **ví dụ theo giả định**, không có nghĩa mọi tổ chức phải đặt tất cả các finding đó ở đúng mức. Nếu một sự cố bảo mật đang khai thác, quy trình incident có thể ưu tiên khác.

### 11.2. Tính “đã xử lý xong” như thế nào?

Định nghĩa **Definition of Done** theo kết quả:

- IaC được cập nhật, có review và triển khai vào đúng môi trường.
- Các cơ chế mới hoạt động; đã kiểm tra log/config/permissions và test hành trình nghiệp vụ.
- Có metric hoặc phép đo chứng minh mục tiêu tốt hơn.
- Tác động tới trụ cột khác được đánh giá, ví dụ thay đổi dự phòng làm tăng cost.
- Runbook, sơ đồ kiến trúc và owner được cập nhật.
- Finding có link evidence và người chấp nhận đóng.

Một PR merge thành công **không đủ** để đóng finding về Reliability hoặc Security nếu chưa kiểm tra tác động vận hành.

### 11.3. Roadmap ba giai đoạn

~~~mermaid
flowchart LR
    B["Baseline<br/>Review + evidence"] --> Q["Quick wins<br/>Alerts, quyền, backup test"]
    Q --> M["Structural fixes<br/>HA, IaC, scaling, data design"]
    M --> V["Validation<br/>Load test, DR drill, security test"]
    V --> R["Re-review<br/>Cập nhật risk register + roadmap"]
~~~

Có thể chia thành 0–30 ngày, 30–90 ngày và dài hạn **nếu** phù hợp nguồn lực. Không gán thời hạn cứng trước khi biết mức độ nghiêm trọng, phụ thuộc kỹ thuật và lịch thay đổi production.

## 12. Kiểm tra sau thay đổi và giữ đánh giá còn hiệu lực

Một bản Review là ảnh chụp chất lượng kiến trúc ở **một thời điểm**. Nó sẽ lỗi thời khi:

- Ứng dụng chuyển region/SKU, thêm database hoặc đổi ingress.
- Có thay đổi quan trọng về Identity/RBAC, Key Vault hoặc network.
- Tăng trưởng traffic, biến động giờ cao điểm hoặc phát sinh dependency.
- Thay đổi backup/redundancy/DR hoặc kiến trúc triển khai.
- SLO, ngân sách hay trách nhiệm nghiệp vụ thay đổi.

Thiết lập nhịp review theo mức độ quan trọng của workload, và review lại khi có thay đổi kiến trúc lớn hoặc sự cố nghiêm trọng. Tránh “review thường niên để đánh dấu hoàn thành” nhưng không có action item nào được triển khai hoặc kiểm thử.

### 12.1. Bộ kiểm tra nghiệm thu

| Trụ cột | Phép đo trước/sau |
| --- | --- |
| Reliability | SLI availability, n−1 capacity, restore/failover RTO/RPO |
| Security | Quyền tối thiểu, secret exposure, policy findings, identity tests |
| Cost Optimization | Cost per successful order, budget variance, unused capacity |
| Operational Excellence | Change failure rate, recovery time, rollback drill, alert coverage |
| Performance Efficiency | Peak throughput, p95/p99 latency, CPU/IOPS/quota utilization |

Các chỉ số phải có cùng **định nghĩa và nguồn dữ liệu** trước/sau. So p95 với tải thấp trước thay đổi và tải cao sau thay đổi sẽ không đủ để kết luận hiệu năng tốt hơn hoặc tệ hơn.

### 12.2. Rủi ro đã được chấp nhận không phải rủi ro đã biến mất

Có thể một doanh nghiệp chưa đủ ngân sách triển khai multi-region. Nếu RTO/RPO hiện tại vẫn được business owner chấp nhận, ghi:

- Rủi ro tồn tại và phạm vi tác động nếu xảy ra.
- Lý do chưa thực hiện và workaround trong thời gian chờ.
- Người có thẩm quyền chấp nhận rủi ro.
- Mốc xem xét lại hoặc trigger nếu nhu cầu tăng.
- Các biện pháp giám sát và giảm tác động tạm thời.

Không chuyển trạng thái thành **Closed** chỉ vì đã phê duyệt “không làm gì”. Nên thể hiện là **Accepted risk** với điều kiện theo dõi cụ thể.

## 13. Mẫu báo cáo Well-Architected Review

Dùng mẫu sau để lưu kết quả workshop và trao đổi với chủ sở hữu. Đây là **mẫu báo cáo nội bộ**, không giả định là định dạng xuất ra từ công cụ Azure.

~~~markdown
# Well-Architected Review — <workload> — <ngày>

## 1. Thông tin và phạm vi
- Workload, business owner, technical owner:
- Subscription(s), resource group(s), region(s):
- Sơ đồ hệ thống / data flow:
- Hành trình nghiệp vụ quan trọng:
- SLO, RTO, RPO, yêu cầu dữ liệu:
- Phạm vi được xem và những phần ngoài phạm vi:

## 2. Phương pháp
- Người tham gia và ngày đánh giá:
- Phiên/bộ câu hỏi của Azure Well-Architected Review đã dùng:
- Công cụ và phép thử bổ trợ:
- Giới hạn bằng chứng, giả định và mức chắc chắn:

## 3. Tổng quan theo năm trụ cột
| Pillar | Điểm mạnh | Rủi ro | Bằng chứng | Owner |
| --- | --- | --- | --- | --- |
| Reliability | ... | ... | ... | ... |
| Security | ... | ... | ... | ... |
| Cost Optimization | ... | ... | ... | ... |
| Operational Excellence | ... | ... | ... | ... |
| Performance Efficiency | ... | ... | ... | ... |

## 4. Risk register
| ID | Risk/Impact | Likelihood | Priority | Evidence | Owner |
| --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... |

## 5. Quyết định và trade-off
- Các phương án:
- Phương án được chọn và lý do:
- Tác động đến trụ cột khác:
- Người phê duyệt/ngoại lệ:

## 6. Kế hoạch khắc phục
| Action | Owner | Deadline | Dependency | Acceptance test |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

## 7. Xác minh và review lại
- Chỉ số trước/sau:
- Phép thử còn cần thực hiện:
- Rủi ro còn lại và người chấp nhận:
- Trigger/ngày review tiếp theo:
~~~

Không đính kèm secret, connection string, token hoặc bản ghi chứa dữ liệu cá nhân vào báo cáo. Nếu dùng ảnh màn hình/diagnostic log, làm sạch các trường không cần thiết và quản lý quyền truy cập tài liệu.

## 14. Bài thực hành capstone: thực hiện một review có dẫn chứng

**Bối cảnh giả định:** Công ty có hệ thống `orders-prod` trong Azure, chịu trách nhiệm nhận đơn và xử lý thanh toán. Workload sử dụng một Azure subscription ứng dụng, một resource group dữ liệu và các thành phần platform dùng chung. Product owner muốn triển khai chiến dịch lớn trong tháng tới, dự báo tải đỉnh **900 requests/giây**; yêu cầu RTO **30 phút**, SLO availability **99,9%**, p95 latency API dưới **500 ms** ở tải được định nghĩa. Những giá trị này là mục tiêu bài tập, không phải SLA Azure.

### 14.1. Tài liệu đầu vào giả định

| Hạng mục | Trạng thái ban đầu |
| --- | --- |
| Ingress | Azure Front Door, có health probes, nhưng failover chưa diễn tập |
| Compute | API chạy trên một instance chính, autoscale chưa có bằng chứng |
| Data | Azure SQL, có backup được báo là Success; chưa thử restore |
| Security | Key Vault tồn tại, API vẫn có credential DB trong config |
| Operations | CI/CD tự động deploy; rollback phải nhờ một kỹ sư |
| Monitoring | HTTP 5xx alert; thiếu synthetic create-order end-to-end |
| Cost | Chi phí compute/database ổn định, budget subscription có nhưng chưa có cost/order |
| Load testing | Lần kiểm thử gần nhất ở 350 RPS, không có bài peak 900 RPS |

**Yêu cầu:** Không tự động kết luận từ “Backup Success” rằng restore hoạt động, hoặc từ “Front Door có health probes” rằng cả region có thể failover. Hãy chỉ rõ những điểm **đã biết**, **chưa xác minh** và **chưa thực hiện**.

### Nhiệm vụ A — Xác định scope và mục tiêu

Điền workload profile, vẽ sơ đồ app/data/identity/network và xác định hành trình **create-order**. Đánh dấu hệ thống thanh toán ngoài Azure là một external dependency. Đặt tiêu chí kiểm chứng SLO, RTO/RPO và khả năng xử lý sau khi một instance hoặc một zone lỗi.

### Nhiệm vụ B — Thực hiện Well-Architected Review

Với mỗi trụ cột, hoàn thành ít nhất **ba câu hỏi đánh giá** bằng bằng chứng. Nếu chưa có dữ liệu, ghi “Unknown/Needs verification” và thiết kế phép thử, không trả lời “đã có” theo kỳ vọng.

Ví dụ:

- Reliability: backup restore có hoàn tất trong RTO không?
- Security: API có quyền tối thiểu để lấy secret và truy cập dữ liệu không?
- Cost: giá mỗi đơn thành công là bao nhiêu khi tính chi phí dùng chung?
- Operational Excellence: có thể rollback bằng quy trình đã kiểm thử không?
- Performance Efficiency: môi trường còn giữ p95 dưới 500 ms khi lên 900 RPS không?

### Nhiệm vụ C — Gắn công cụ và bằng chứng

Sử dụng dữ liệu giả lập hoặc read-only ở môi trường học để:

1. Kiểm kê resource và configuration theo scope.
2. Tìm khuyến nghị Azure Advisor liên quan, nếu khả dụng.
3. Đọc Azure Monitor/App Insights metrics hoặc dựng bảng SLI mẫu.
4. So sánh budget/cost per successful order bằng số liệu do bài tập cung cấp.
5. Xác nhận mọi phát hiện có **owner, timestamp và phương pháp kiểm thử**.

**Không** cần thay đổi production hoặc mua resource để hoàn thành bài; nếu không có quyền Azure, hãy ghi rõ dữ liệu nào cần yêu cầu từ owner.

### Nhiệm vụ D — Tạo risk register và roadmap

Chọn tối thiểu **năm finding**, ít nhất một finding ở mỗi trụ cột. Với mỗi finding, ghi impact, likelihood, evidence, người phụ trách, priority và acceptance test. Chỉ ra ít nhất **hai trade-off** giữa các trụ cột.

Ví dụ “thêm replica/API và tăng HA” phải kèm kiểm tra giá thành, DB throughput và khả năng phân bố zone; “giảm log ingest” phải kèm đánh giá bảo mật/quan sát.

### Nhiệm vụ E — Trình bày quyết định

Viết báo cáo 1–3 trang theo mẫu mục 13, cùng phụ lục bảng bằng chứng. Trình bày với giả định audience gồm business owner, SRE, security và FinOps. Kết thúc bằng ba quyết định:

1. Việc nào phải làm **trước chiến dịch**?
2. Việc nào có thể làm sau nhưng cần workaround/accepted risk?
3. Kiểm thử nào sẽ xác nhận kiến trúc đã cải thiện?

### 14.2. Rubric tự đánh giá

| Tiêu chí | Đạt khi |
| --- | --- |
| **Scope** | Workload và dependency thực, không chỉ một resource group |
| **Năm trụ cột** | Có câu trả lời và finding cho Reliability, Security, Cost, Operations, Performance |
| **Bằng chứng** | Mỗi claim quan trọng gắn telemetry, cấu hình, test hoặc trạng thái “chưa biết” |
| **Trade-off** | Nêu được tác động chi phí/hiệu năng/bảo mật/độ tin cậy của từng quyết định |
| **Ưu tiên** | Risk register có phương pháp ưu tiên và ngoại lệ được giải thích |
| **Kế hoạch hành động** | Có owner, phương án, deadline và acceptance test |
| **Kiểm chứng** | Nêu rõ metrics và test trước/sau, không kết thúc ở “đã cấu hình” |
| **Giao tiếp** | Báo cáo rõ cho kỹ thuật, tài chính và chủ sở hữu nghiệp vụ |

## 15. Những sai lầm thường gặp

| Sai lầm | Vì sao không đủ | Cách khắc phục |
| --- | --- | --- |
| Chỉ mở Azure Advisor rồi gọi là Well-Architected Review | Advisor không biết mọi yêu cầu nghiệp vụ và dependency | Thực hiện workload assessment theo năm trụ cột |
| Trả lời theo kiến trúc mong muốn trong tương lai | Che khuất rủi ro của production hiện tại | Đánh giá trạng thái as-is; roadmap tách riêng |
| Cho rằng Review tự động kiểm định toàn bộ subscription | Bộ câu hỏi là self-assessment | Đối chiếu bằng monitor, config, test và chuyên gia |
| Xem policy compliant là hệ thống an toàn tuyệt đối | Policy chỉ bao phủ rule/scope đã định | Threat model, IAM review, application security testing |
| Có backup là kết luận đạt Reliability | Backup có thể không restore đúng và kịp | Diễn tập restore, đo RTO/RPO và data integrity |
| Scale compute để xử lý mọi bottleneck | DB/network/queue có thể mới là nút thắt | Load test và dependency tracing |
| Chấm điểm rủi ro đẹp nhưng không có owner | Không có ai sửa hoặc xác minh | Risk register gắn trách nhiệm và deadline |
| Không ghi rủi ro còn lại khi chấp nhận ngoại lệ | Rủi ro bị quên sau một buổi họp | Risk acceptance có người duyệt và trigger review lại |
| Cắt log/backup để tối ưu cost | Có thể làm mất khả năng điều tra/khôi phục | Giữ guardrails về security, retention, RTO/RPO |
| Đóng finding khi PR được merge | Không chứng minh thay đổi đã cải thiện hành vi | Acceptance test và evidence thực tế |
| Review một lần rồi không cập nhật | Workload thay đổi, bảng đánh giá lỗi thời | Review theo chu kỳ và theo change/incident |

## 16. Tóm tắt và nguyên tắc áp dụng

**Azure Well-Architected Review** là cách có cấu trúc để kiểm tra một workload Azure theo **năm trụ cột**: Reliability, Security, Cost Optimization, Operational Excellence và Performance Efficiency. Chất lượng đánh giá phụ thuộc vào phạm vi workload, mục tiêu nghiệp vụ, câu trả lời trung thực và bằng chứng khách quan.

Quy trình nên kết nối thành một vòng lặp:

~~~text
Định nghĩa workload + SLO/RTO/RPO
  -> Thu kiến trúc, telemetry và dữ liệu chi phí
  -> Thực hiện Well-Architected Review
  -> Xác minh findings bằng công cụ và phép thử
  -> Lập risk register và đánh giá trade-off
  -> Ưu tiên action với owner + acceptance criteria
  -> Thực hiện thay đổi có kiểm soát
  -> Đo trước/sau, cập nhật tài liệu và review lại
~~~

Điều quan trọng nhất không phải “workload đạt bao nhiêu điểm”, mà là **những rủi ro quan trọng đã được hiểu và xử lý đến đâu**, thay đổi có cải thiện trải nghiệm người dùng, khả năng phục hồi, bảo mật, hiệu năng và chi phí hay không. Đây là cách kết nối kiến thức kỹ thuật Azure với trách nhiệm kiến trúc và vận hành dài hạn.
