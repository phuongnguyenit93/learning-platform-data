# Thực hành viết và rà soát quyết định kiến trúc GCP

Một kiến trúc Google Cloud có thể triển khai thành công nhưng vẫn thiếu câu trả lời quan trọng: **vì sao nhóm chọn thiết kế đó thay vì các phương án khác?** Sau sáu tháng, khi đội ngũ thay người, yêu cầu bảo mật tăng hoặc chi phí vận hành khác dự tính, một sơ đồ chỉ cho biết hệ thống *đang chạy thế nào* chứ không giải thích *vì sao nó được thiết kế như vậy*. Lúc này, quyết định kiến trúc cần được ghi lại như một bằng chứng kỹ thuật có thể xem xét, phản biện và cập nhật.

**Architecture Decision Record (ADR)** là bản ghi ngắn gọn nhưng có cấu trúc, mô tả bối cảnh, yêu cầu, phương án, sự đánh đổi, quyết định được chọn, hệ quả và tiêu chí xác minh. Một ADR không nhằm chứng minh người viết luôn đúng; nó làm rõ những giả định tại thời điểm quyết định, để người đọc có thể đánh giá lại khi hoàn cảnh thay đổi.

Bài học thuộc chương **Thiết kế kiến trúc GCP** trong module **CLOUD_PROVIDERS_GCP**. Module này khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong bài này, chúng ta thực hành **viết một ADR hoàn chỉnh và tổ chức buổi review quyết định** bằng một tình huống Java/Spring thực tế nhưng giả định.

> **Giới hạn phạm vi:** Các con số về lưu lượng, SLO, ngân sách, thời gian khôi phục và điểm số trong bài đều là **giả định đào tạo**, không phải số liệu đo hay cam kết dịch vụ Google Cloud. Trước khi áp dụng production, hãy thay bằng dữ liệu tổ chức, báo giá cập nhật và kết quả thử nghiệm của chính workload.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt ADR với sơ đồ kiến trúc, tài liệu thiết kế chi tiết, RFC và runbook.
- Xác định lúc nào cần viết ADR và cách giữ lịch sử thay đổi quyết định.
- Ghi rõ ràng business context, critical user journey, giả định, ràng buộc cứng và yêu cầu phi chức năng.
- Đánh giá thiết kế theo sáu trụ cột của Google Cloud Well-Architected Framework.
- So sánh Compute Engine, GKE, Cloud Run, App Engine hoặc các phương án dịch vụ khác mà không chọn theo sở thích.
- Dùng ma trận có trọng số đúng cách, kết hợp kiểm tra ràng buộc bắt buộc và bằng chứng thử nghiệm.
- Viết ADR cho một dịch vụ Spring Boot, tổ chức review nhiều vai trò, xử lý phản biện và lập kế hoạch kiểm chứng.
- Xác định khi nào một ADR phải được cập nhật hoặc thay thế bằng ADR mới.

## 1. ADR là gì và khi nào cần dùng?

ADR ghi lại **một quyết định kiến trúc quan trọng** cùng lý do ra quyết định. Ví dụ:

- Chọn Cloud Run services thay vì GKE để phục vụ một API Spring Boot.
- Chọn Cloud SQL HA trong một region và xác định ranh giới RTO/RPO.
- Dùng Pub/Sub để truyền sự kiện bất đồng bộ thay vì gọi HTTP đồng bộ giữa các dịch vụ.
- Chọn private ingress, VPC egress và IAM service-to-service cho một hệ thống nhạy cảm.
- Chia project theo môi trường, chọn shared VPC và tách quyền runtime khỏi deployer.

ADR hữu ích khi có ít nhất hai phương án hợp lý, phương án được chọn có hệ quả dài hạn, hoặc quyết định không thể suy ra trực tiếp từ code. Với thay đổi nhỏ đã có tiêu chuẩn được phê duyệt, một pull request và tài liệu cấu hình có thể đủ; không cần tạo ADR cho từng environment variable.

| Tài liệu | Câu hỏi chính | Nội dung thường có |
|---|---|---|
| ADR | Vì sao chọn phương án này? | Bối cảnh, lựa chọn, quyết định, đánh đổi, hệ quả |
| Design document | Hệ thống sẽ được xây thế nào? | Component, sequence, API/data contract, sơ đồ, migration |
| RFC / Proposal | Có nên chấp thuận đề xuất này? | Vấn đề, ý kiến các bên, phương án đang chờ quyết định |
| Runbook | Khi triển khai/sự cố phải làm gì? | Các bước thao tác, điều kiện kích hoạt, rollback, escalation |
| Threat model | Hệ thống có thể bị tấn công theo cách nào? | Assets, trust boundaries, threat, control, residual risk |
| Terraform/manifest | Trạng thái mong muốn được khai báo ra sao? | Resources, IAM, networks, deployment configuration |

Một ADR có thể liên kết đến các tài liệu còn lại, nhưng không nên sao chép toàn bộ mã nguồn hoặc runbook vào nó. Google Cloud gợi ý lưu ADR dạng Markdown gần codebase liên quan để dễ tìm, review và xem lịch sử thay đổi qua version control.

### 1.1. Vòng đời ADR

Có thể dùng quy ước trạng thái của nhóm:

| Trạng thái | Ý nghĩa |
|---|---|
| Proposed | Đã có đề xuất và bằng chứng ban đầu, chờ phản biện |
| Accepted | Người có thẩm quyền đã chấp thuận phương án cùng điều kiện |
| Rejected | Không chọn phương án; giữ hồ sơ để tránh lặp lại tranh luận |
| Superseded | Quyết định cũ được thay thế bởi ADR mới, có link hai chiều |
| Deprecated | Không còn áp dụng cho thiết kế hiện tại; có thể đang trong giai đoạn chuyển đổi |

Đây là **quy ước quản trị đề xuất**, không phải trạng thái do Google Cloud tự động áp đặt. Một ADR Accepted không đồng nghĩa mọi thành phần đã triển khai xong; ghi thêm trạng thái thực thi trong issue tracker và bằng chứng validation nếu cần.

~~~mermaid
flowchart LR
    A["Vấn đề / thay đổi yêu cầu"] --> B["Proposed ADR"]
    B --> C["Review kỹ thuật, bảo mật, vận hành"]
    C --> D{"Đủ bằng chứng?"}
    D -->|"Chưa"| E["PoC, benchmark, threat model, cost"]
    E --> B
    D -->|"Có"| F{"Được chấp thuận?"}
    F -->|"Không"| G["Rejected + lý do"]
    F -->|"Có"| H["Accepted"]
    H --> I["Triển khai, đo SLO và chi phí"]
    I --> J{"Giả định thay đổi?"}
    J -->|"Không"| I
    J -->|"Có"| K["ADR mới thay thế quyết định cũ"]
    K --> B
~~~

## 2. Cấu trúc tối thiểu của một ADR tốt

Một ADR nên tự trả lời được các câu hỏi sau dù người viết không có mặt:

| Mục | Cần ghi gì? | Dấu hiệu chưa đạt |
|---|---|---|
| ID, tiêu đề | Mã duy nhất và quyết định đang xét | Tiêu đề chung chung như “Architecture” |
| Trạng thái, ngày | Proposed/Accepted..., ngày quyết định và version | Không biết quyết định có còn hiệu lực |
| Chủ sở hữu, reviewers | Người chịu trách nhiệm, team và vai trò phê duyệt | Không ai nhận trách nhiệm |
| Bối cảnh | Vấn đề và tác động đến người dùng | Liệt kê dịch vụ nhưng không nói vấn đề |
| Critical user journey | Luồng nghiệp vụ thiết yếu cần bảo vệ | Chỉ nói “hệ thống phải nhanh” |
| Yêu cầu và NFR | SLO, latency, security, recovery, data residency, cost | Mục tiêu không đo được |
| Giả định và giới hạn | Những điều đã biết/chưa biết và điều kiện không được vi phạm | Chọn trước rồi tìm lý do sau |
| Phương án | Các lựa chọn khả thi, kể cả giữ hiện trạng khi hợp lý | Chỉ có một phương án |
| Đánh giá | Bằng chứng, điểm mạnh/yếu, chi phí, rủi ro | Chấm điểm cảm tính không giải thích |
| Quyết định | Chọn cái gì, ở phạm vi nào và vì sao | “Dùng GCP vì hiện đại” |
| Hệ quả | Trade-off, rủi ro còn lại, việc phải thực hiện | Tuyên bố không có nhược điểm |
| Kiểm chứng | Thử nghiệm, owner, deadline, ngưỡng pass/fail | Không có bước chứng minh |
| Revisit triggers | Khi nào mở lại quyết định | ADR bị xem là đúng mãi mãi |
| Liên kết | Design doc, issue, metrics, IaC, threat model | Không truy vết được bằng chứng |

Nên phân biệt ba loại phát biểu:

- **Fact:** đã kiểm chứng bằng log, benchmark, hợp đồng dịch vụ hoặc tài liệu có phiên bản.
- **Assumption:** dự đoán đang chờ xác minh, ví dụ “lưu lượng tăng gấp ba vào cuối năm”.
- **Decision:** lựa chọn được người có trách nhiệm chấp thuận, ví dụ “chạy API trên Cloud Run trong một region với một Cloud SQL HA instance”.

Không biến assumption thành fact. Nếu chưa có số liệu p95 từ load test, hãy đánh dấu **“chưa đo”** thay vì ghi một con số như đã chứng minh.

## 3. Khung review: sáu trụ cột Well-Architected

Google Cloud Well-Architected Framework hiện tổ chức khuyến nghị quanh **sáu trụ cột**. Khi review ADR, dùng chúng như một bộ câu hỏi kiểm tra, không phải danh sách dịch vụ bắt buộc.

| Trụ cột | Câu hỏi review | Bằng chứng nên có |
|---|---|---|
| Operational excellence | Có chủ vận hành, CI/CD, rollback, observability, incident playbook không? | Owner, release runbook, Cloud Monitoring dashboards |
| Security, privacy, compliance | IAM tối thiểu, trust boundary, bảo vệ dữ liệu và audit có rõ không? | IAM matrix, threat model, encryption và audit plan |
| Reliability | SLO, khả năng chịu lỗi và khôi phục được kiểm chứng chưa? | Error budget, failure drill, backup/restore results |
| Cost optimization | Chi phí theo workload và kịch bản tăng trưởng có được so sánh không? | Estimate, Billing export, budget/alerts, unit cost |
| Performance optimization | Có latency, throughput, quota, bottleneck và load-test plan không? | Load test, p95/p99, CPU/memory, DB connections |
| Sustainability | Thiết kế có tránh lãng phí tài nguyên nhàn rỗi và đo được hiệu quả không? | Autoscaling, right-sizing, resource utilization |

Một ADR không nhất thiết đi sâu như nhau vào cả sáu trụ cột. Tuy nhiên, nếu bỏ qua một trụ cột, người viết nên nêu lý do. Ví dụ, ADR chọn công nghệ queue cần phân tích delivery semantics và reliability sâu hơn chi tiết VM sizing.

### 3.1. Câu hỏi xuyên trụ cột

Các trụ cột có thể xung đột:

- Tăng minimum instances giảm cold start nhưng tăng chi phí và tài nguyên nhàn rỗi.
- Chạy multi-region giúp giảm rủi ro lỗi vùng nhưng tăng networking, dữ liệu đồng bộ và độ phức tạp vận hành.
- Thắt chặt network egress giúp bảo vệ dữ liệu nhưng có thể tăng yêu cầu proxy hoặc cấu hình DNS.
- Giảm số replica tiết kiệm tiền nhưng làm giảm khả năng chịu lỗi và có thể tăng latency.
- Dùng dịch vụ managed giảm toil nhưng thay đổi mức độ kiểm soát runtime và kiểu phụ thuộc nhà cung cấp.

Review tốt không yêu cầu tất cả trụ cột cùng đạt điểm tối đa. Review yêu cầu **lý do chọn mức đánh đổi, cách đo và phương án khi giả định sai**.

## 4. Bài thực hành: lựa chọn hạ tầng cho Orders API

### 4.1. Đề bài giả định

Một công ty có ứng dụng Java 21 / Spring Boot tên **Orders API**. API nhận đơn hàng, lưu trạng thái vào PostgreSQL, phát sự kiện để dịch vụ fulfillment xử lý bất đồng bộ. Công ty hiện có hai kỹ sư backend, một DevOps kiêm nhiệm và chưa có đội vận hành Kubernetes chuyên trách.

Các yêu cầu mẫu:

| ID | Loại | Yêu cầu giả định |
|---|---|---|
| F-01 | Chức năng | Nhận HTTPS POST tạo đơn hàng và GET trạng thái |
| F-02 | Chức năng | Phát sự kiện sau khi đơn được ghi bền vững |
| F-03 | Chức năng | Tách worker xử lý fulfillment khỏi API |
| NFR-01 | Reliability | Mục tiêu availability cho API: **99,9% mỗi tháng** |
| NFR-02 | Performance | p95 latency của POST không quá **300 ms** trong điều kiện tải được định nghĩa |
| NFR-03 | Scalability | 20–150 request/giây bình thường, peak giả định 400 request/giây |
| NFR-04 | Recovery | Mục tiêu RTO tối đa **60 phút**, RPO tối đa **15 phút** cho sự cố được xác định |
| NFR-05 | Security | Không public trực tiếp database; service identities riêng; không dùng khóa service account tĩnh |
| NFR-06 | Data | Dữ liệu đơn hàng và backup phải đáp ứng địa điểm lưu trữ do tổ chức phê duyệt |
| NFR-07 | Cost | Ngân sách vận hành đích **900 USD/tháng** cho runtime API + dữ liệu + đường truyền liên quan |
| NFR-08 | Operations | Deploy nhiều lần/tuần, rollback runtime trong khoảng 10 phút |
| C-01 | Ràng buộc | Team chưa vận hành Kubernetes như nền tảng chuẩn |
| C-02 | Ràng buộc | Phải dùng PostgreSQL tương thích ứng dụng hiện tại |

**Tất cả giá trị là giả định để thực hành.** Một SLO 99,9% tương đương tối đa khoảng 43,2 phút không sẵn sàng trong tháng 30 ngày *nếu đo 24/7 theo định nghĩa SLI đó*; đây là error budget tính học thuật, không phải SLA cam kết của Google Cloud. RTO/RPO trong ADR là mục tiêu vận hành và phải được kiểm tra bằng phương án backup/replication, không tự nhiên được bảo đảm chỉ vì chọn Cloud SQL HA.

### 4.2. Critical user journey và ranh giới hệ thống

Critical user journey (CUJ): khách hàng gửi đơn hàng, nhận xác nhận và có thể tra cứu trạng thái. Đơn không được mất hoặc tạo trùng khi client retry.

~~~mermaid
flowchart LR
    C["Client"] -->|HTTPS + identity| A["Orders API"]
    A -->|Transaction| DB[("Cloud SQL PostgreSQL")]
    A -->|Outbox event| DB
    DB --> O["Outbox publisher"]
    O -->|Publish| P["Pub/Sub topic"]
    P -->|Push / pull| W["Fulfillment worker"]
    W --> DB
    A --> L["Cloud Logging / Monitoring"]
    O --> L
    W --> L
~~~

Sơ đồ mô tả **phương án tham khảo** để xem xét, không phải quyết định được tự động phê duyệt. Nếu thêm đường gửi trực tiếp sự kiện sau khi commit database mà không có outbox hoặc cách khắc phục phù hợp, có thể xuất hiện cửa sổ lỗi “đơn đã lưu nhưng event chưa được phát”. ADR cần ghi rõ lựa chọn về tính nhất quán và khả năng replay.

### 4.3. Phân biệt ràng buộc cứng và ưu tiên

**Ràng buộc cứng (hard gates)** là điều kiện không được vi phạm: dữ liệu phải ở vị trí được phê duyệt; PostgreSQL tương thích; quyền IAM không được mở rộng quá mức; phương án có thể kiểm thử recovery theo mục tiêu.

**Ưu tiên (weighted criteria)** là các yếu tố có thể đánh đổi: giảm công sức vận hành, tối ưu chi phí, giảm cold start, tăng tính di động, tận dụng kỹ năng team.

Một phương án không vượt hard gate phải bị loại hoặc đánh dấu **Conditional** cho đến khi có giải pháp khắc phục. Đừng cho điểm cộng ở mục “chi phí thấp” để bù cho thiếu sót bảo mật bắt buộc.

## 5. Ba phương án cần so sánh

### Phương án A: Cloud Run services + Cloud SQL + Pub/Sub

- Java Spring Boot chạy dưới dạng Cloud Run service; push event đến worker service hoặc dùng worker pool tùy mô hình tiêu thụ.
- PostgreSQL được quản lý bằng Cloud SQL. Kết nối private theo kiến trúc VPC được phê duyệt; identity và secrets được phân quyền riêng.
- API stateless, autoscale theo request; giới hạn max instances và pool kết nối để bảo vệ database.
- Dùng Cloud Build/Cloud Deploy hoặc pipeline được chuẩn hóa để triển khai image digest và traffic split.

**Điểm mạnh:** ít phải quản lý VM/cluster; phù hợp đội nhỏ và API request-driven; dễ tạo revision và phân quyền từng service.

**Đánh đổi:** cold start, concurrency, giới hạn instance/region/quota, database connection pressure; cần thiết kế riêng cho task dài hoặc xử lý liên tục. Cloud Run không tự giải quyết availability của Cloud SQL hay tính nhất quán sự kiện.

### Phương án B: GKE Autopilot + Cloud SQL + Pub/Sub

- API và worker chạy trong Pod; Deployment, Service/Gateway, probes và Horizontal Pod Autoscaler được khai báo theo Kubernetes.
- GKE quản lý node infrastructure trong Autopilot, nhưng nhóm vẫn phải hiểu Kubernetes objects, IAM/RBAC, policy, resource requests và deployment.
- Có thể kết hợp GitOps, service mesh hoặc custom controller khi nhu cầu xuất hiện.

**Điểm mạnh:** hệ sinh thái Kubernetes; phù hợp nhiều microservice cùng dùng platform, hỗ trợ các pattern orchestration chi tiết.

**Đánh đổi:** nhiều công việc thiết kế cluster/workload, networking, policies, resource requests và troubleshooting. Với team chưa có Kubernetes, time-to-operate có thể cao hơn phương án A. Chi phí phải đo theo workloads và yêu cầu cluster, không suy ra chỉ từ số Pod.

### Phương án C: Compute Engine Managed Instance Group + Cloud SQL + Pub/Sub

- Tạo image VM hoặc container trên VM với service process; MIG, load balancing, autohealing và rolling updates.
- Nhóm quản lý guest OS, patching, runtime, VM image, capacity và observability agent.

**Điểm mạnh:** quyền kiểm soát OS và môi trường thực thi cao; phù hợp khi Java legacy có agent, driver hoặc phụ thuộc hệ thống đặc thù.

**Đánh đổi:** trách nhiệm vận hành cao; có thể tốn tài nguyên nền trong giờ ít tải; đội phải tự duy trì OS hardening và rollback template.

### Có cần xem App Engine?

Có thể thêm App Engine Standard/Flexible làm phương án D nếu công ty có ứng dụng hoặc năng lực vận hành App Engine sẵn có. Trong tình huống này, nhóm có thể ghi “không đưa vào shortlist ban đầu do chuẩn artifact OCI và yêu cầu kiến trúc đang hướng tới Cloud Run/GKE”, nhưng phải công khai đây là **quyết định phạm vi**, không tuyên bố App Engine thiếu khả năng chạy Spring Boot. Nếu một reviewer cho thấy App Engine phù hợp hơn, mở rộng shortlist và đánh giá lại.

## 6. Ma trận đánh giá và cách tính điểm

Ma trận chỉ là công cụ hỗ trợ thảo luận. Cần có lý do, dữ liệu và reviewer cho từng điểm; không biến một số điểm tự chọn thành “chứng cứ khoa học”.

| Tiêu chí | Trọng số | A: Cloud Run | B: GKE Autopilot | C: Compute Engine MIG |
|---|---:|---:|---:|---:|
| Công sức vận hành thấp | 25% | 5 | 3 | 2 |
| Chi phí dự kiến | 20% | 4 | 3 | 3 |
| Co giãn theo tải | 15% | 5 | 4 | 3 |
| An ninh và ranh giới cấu hình | 15% | 4 | 4 | 4 |
| Reliability và khả năng phục hồi | 15% | 4 | 4 | 3 |
| Tính di động / kỹ năng lâu dài | 10% | 3 | 5 | 3 |
| **Tổng điểm mẫu** | **100%** | **4,30/5** | **3,65/5** | **2,90/5** |

Công thức điểm theo trọng số:

~~~text
Điểm phương án = Σ (trọng số_i × điểm_i) / 100

Cloud Run:
(25×5 + 20×4 + 15×5 + 15×4 + 15×4 + 10×3) / 100 = 4,30

GKE Autopilot:
(25×3 + 20×3 + 15×4 + 15×4 + 15×4 + 10×5) / 100 = 3,65

Compute Engine MIG:
(25×2 + 20×3 + 15×3 + 15×4 + 15×3 + 10×3) / 100 = 2,90
~~~

**Diễn giải:** A đứng đầu trong giả định team nhỏ và workload HTTP stateless. Nhưng các điểm chi phí, reliability và performance **chưa được đo**. Trước khi chấp thuận, team phải xác minh bằng PoC, load test, pricing estimate và failure drill.

### 6.1. Kiểm tra độ nhạy

Hãy hỏi: nếu trọng số thay đổi, quyết định còn đứng vững không?

Ví dụ, nếu một tổ chức đã có platform team GKE mạnh, chi phí vận hành Kubernetes có thể giảm đáng kể. Nếu có yêu cầu operator hoặc service mesh không tương thích với thiết kế Cloud Run, B có thể vượt hard gate phù hợp hơn. Nếu workload yêu cầu custom kernel/OS, phương án C có thể trở thành duy nhất đáp ứng ràng buộc.

Tính điểm **sau khi** xác minh ràng buộc cứng. Có thể ghi thêm khoảng bất định thay vì một điểm tuyệt đối, ví dụ “chi phí A = 4 ± 1 cho đến khi load test và dự toán networking hoàn tất”.

### 6.2. Bằng chứng cần thu thập

| Giả định | Cách kiểm chứng | Điều kiện cần ghi trong ADR |
|---|---|---|
| Cloud Run đủ throughput | Load test ở concurrency dự kiến, đo p95/p99, 5xx, cold start | Kịch bản tải, region, cấu hình CPU/RAM và kết quả |
| Cloud SQL không bị quá tải | Đo active connections, pool size, CPU, IO, p95 query | Max instances × connections/instance, ngưỡng an toàn |
| SLO đạt | Định nghĩa SLI và đo qua Cloud Monitoring | Cửa sổ đo, numerator/denominator, target |
| RTO/RPO đạt | Thử backup/restore/failover trong staging | RTO/RPO thực tế cho từng failure scenario |
| Ngân sách đáp ứng | Pricing Calculator + quan sát Billing | Assumptions về request, vCPU/GiB, egress, log, DB |
| Security phù hợp | IAM review, threat model, kiểm tra private connectivity | Trust boundaries và bằng chứng cấu hình |

## 7. Mẫu ADR có thể dùng trong repository

Một mẫu nên ngắn, có thể review như code. Đây là khung Markdown; mỗi team điều chỉnh các trường theo quy trình phê duyệt của mình:

~~~markdown
# ADR-NNN: [Quyết định đang xét]

- Status: Proposed
- Date: YYYY-MM-DD
- Owners: [team hoặc vai trò]
- Reviewers: [Architecture, Security, SRE, Finance nếu cần]
- Scope: [service/project/environment]
- Related: [design doc, threat model, issue, benchmark]

## Context
[Business problem và kiến trúc hiện tại]

## Critical user journey
[Luồng nghiệp vụ cần bảo vệ và sự cố người dùng không chấp nhận]

## Functional and non-functional requirements
[SLI/SLO, throughput, latency, data residency, RTO/RPO, ngân sách]

## Assumptions and constraints
[Điều đã biết, chưa biết và hard gates]

## Options considered
[A / B / C, bao gồm ưu nhược điểm và lý do loại]

## Decision
[Phương án, phạm vi, ngày, người chịu trách nhiệm]

## Consequences and risks
[Chi phí, lock-in, toil, rủi ro còn lại, kế hoạch giảm thiểu]

## Validation and rollout
[PoC, ngưỡng pass/fail, owner, rollback]

## Revisit triggers
[Khi tải tăng, luật đổi, SLO trượt, dự toán sai...]

## References
[Link tới nguồn đã xác minh]
~~~

Đặt mỗi ADR một ID ổn định, ví dụ `ADR-013`. Tên file được tổ chức định nghĩa theo quy ước riêng; khi đổi quyết định, tạo ADR mới tham chiếu ADR cũ thay vì xóa lịch sử. Có thể lưu thư mục `docs/adr/` trong repository ứng dụng hoặc một nơi mà các nhóm review có quyền truy cập.

## 8. ADR đã điền: chọn nền tảng cho Orders API

Ví dụ dưới đây **chỉ là hồ sơ của tình huống giả định**, không phải phê duyệt cho một hệ thống có thật.

### ADR-013: Chạy Orders API stateless trên Cloud Run services

**Metadata**

| Trường | Giá trị minh họa |
|---|---|
| Status | **Proposed**, chờ PoC và review chính thức |
| Ngày đề xuất | 2026-11-19 |
| Owner | Nhóm Orders API |
| Reviewer | Platform/DevOps, Security, SRE, Data owner, FinOps |
| Môi trường | Staging trước, production sau khi qua gates |
| Phạm vi | Chọn runtime HTTP API, không bao gồm quyết định dữ liệu độc lập |
| Liên kết | Design doc, load-test report, IAM matrix và pricing sheet (sẽ bổ sung) |

#### Context

Orders API viết bằng Spring Boot, nhận và trả lời HTTP, không dựa vào filesystem cục bộ. Lưu lượng có peak lớn nhưng nhiều giờ tải thấp. Đội phát triển nhỏ, chưa có năng lực Kubernetes chuyên trách. Hệ thống phải lưu đơn hàng bền vững và phát sự kiện theo cách chịu được retry.

#### Hard requirements

- Không ghi dữ liệu cá nhân vào log hoặc container filesystem như kho lưu trữ bền vững.
- PostgreSQL được phê duyệt và dữ liệu/backup theo chính sách vị trí lưu trữ của công ty.
- Runtime identity của API chỉ có quyền cần thiết lên Cloud SQL/Secret Manager và các API liên quan.
- SLO 99,9% và mục tiêu RTO 60 phút, RPO 15 phút phải có phép đo kiểm chứng.
- Phải có chiến lược rollback runtime, backup/restore và xử lý message trùng.

#### Options

- A — Cloud Run + Cloud SQL + Pub/Sub: giảm vận hành, scale theo request, nhưng cần quản lý concurrency/cold start và phối hợp DB.
- B — GKE Autopilot + Cloud SQL + Pub/Sub: giàu Kubernetes capability, nhưng chưa có platform owner phù hợp.
- C — Compute Engine MIG + Cloud SQL + Pub/Sub: kiểm soát OS, nhưng nhiều công việc vá hệ thống và quản lý capacity.

#### Proposed decision

**Chọn A có điều kiện**, dùng Cloud Run service cho Orders API, Cloud SQL PostgreSQL cho state và Pub/Sub cho luồng sự kiện bất đồng bộ. Sự kiện giao dịch dùng outbox hoặc cơ chế tương đương để giảm nguy cơ mất sự kiện giữa database commit và publish. Consumer phải hỗ trợ xử lý lặp; không giả định Pub/Sub mặc định có exactly-once delivery cho mọi cách nhận message.

Đây là đề xuất chưa phải Accepted vì chưa có đầy đủ dữ liệu load test, kết quả restore drill và kiểm tra chi phí. Sau khi qua gates, người có thẩm quyền mới đổi trạng thái thành Accepted.

#### Reference architecture

~~~mermaid
flowchart TD
    subgraph Clients["Bên ngoài trust boundary"]
      U["User / frontend"]
    end
    subgraph GCP["Project ứng dụng - môi trường được phê duyệt"]
      E["HTTPS entry / Auth"]
      R["Cloud Run: Orders API"]
      D[("Cloud SQL PostgreSQL HA")]
      O["Outbox publisher"]
      P["Pub/Sub topic"]
      W["Fulfillment consumer"]
      S["Secret Manager"]
      M["Cloud Logging / Monitoring"]
    end
    U --> E --> R
    R -->|Private connection / IAM| D
    O --> D
    O -->|Publish| P
    P --> W
    W --> D
    R --> S
    R --> M
    O --> M
    W --> M
~~~

Sơ đồ nêu các luồng logic, **không đại diện cấu hình mạng hoàn chỉnh**. Trong design doc phải xác nhận mạng riêng, endpoint, DNS, IAM, firewall, phương thức kết nối Cloud SQL và nơi chạy outbox publisher. Chỉ vẽ mũi tên “private connection” chưa đủ chứng minh kết nối thực sự riêng tư.

#### Consequences

**Tích cực:** đội chỉ triển khai image/revision, không quản lý VM hoặc cluster; có thể scale theo request; phân quyền IAM theo service; hỗ trợ progressive release.

**Bất lợi:** cold start có thể ảnh hưởng p95; max instances và pool connection cần giới hạn; cấu hình mạng/egress có thể làm tăng phí; Cloud Run và Pub/Sub có semantics riêng cần thiết kế; không thể dùng host OS/kernel tùy ý.

**Rủi ro còn lại:** sự cố Cloud SQL region, rollback schema không tương thích, event publish trễ, dữ liệu trùng khi retry, log chứa dữ liệu nhạy cảm, tăng tải nhanh gây cạn database connections.

#### Mitigations

| Rủi ro | Cách giảm thiểu | Owner | Bằng chứng |
|---|---|---|---|
| DB connection exhaustion | Giới hạn Cloud Run max instances, HikariCP pool; load test | Backend + SRE | DB metrics dưới peak |
| Mất event sau commit | Outbox + publisher retry + idempotent consumer | Backend | Failure injection test |
| SLO chưa đạt | Metric/alert/traffic split và runbook | SRE | Kết quả canary và SLI |
| Chậm khôi phục dữ liệu | Backup/PITR theo yêu cầu, restore rehearsal | Data owner | RTO/RPO đo được |
| Rủi ro IAM | Least privilege, Workload Identity, không dùng JSON key | Security | IAM review |
| Chi phí vượt dự toán | Billing budget, quota, right-sizing và review định kỳ | FinOps | Cost report và unit economics |

#### Validation gates

- **Gate 1 — Security:** Security xác nhận service identity, secret, ingress/egress, project boundary, encryption và logging.
- **Gate 2 — Performance:** Load test peak giả định 400 request/giây, đạt p95 mục tiêu theo kịch bản xác định và không làm quá tải DB. Nếu không đạt, thay đổi cấu hình hoặc xem lại phương án.
- **Gate 3 — Reliability:** Thử failover/restore, đo RTO/RPO trong các failure scenarios được chỉ rõ; kiểm tra retry/idempotency.
- **Gate 4 — Operability:** Có SLO, dashboard, alert, runbook, release/rollback rehearsal và nhóm trực.
- **Gate 5 — Cost:** Dự toán ước tính theo kịch bản bình thường và peak không vượt ngân sách đã phê duyệt, tính cả Cloud SQL, network và logging.
- **Gate 6 — Approval:** Architecture owner, Security và Service owner chấp thuận các rủi ro còn lại hoặc yêu cầu sửa đề xuất.

#### Revisit triggers

Mở lại quyết định nếu một trong các điều kiện sau xảy ra:

- Traffic/throughput cao hơn giả định dài hạn hoặc p95 vi phạm mục tiêu liên tiếp.
- Đội ngũ đã có nền tảng GKE dùng chung với chi phí/operational burden thấp hơn.
- Yêu cầu runtime cần host capability Cloud Run không đáp ứng.
- Chính sách region, compliance hoặc connectivity thay đổi.
- Chi phí theo mỗi 1.000 đơn hàng vượt ngưỡng được chấp thuận.
- Sự cố nghiêm trọng cho thấy RTO/RPO hoặc chiến lược event delivery không đạt.

#### Decision record

*Hiện trạng:* Proposed. Owner thu thập bằng chứng Gate 1–5; reviewer ghi nhận nhận xét trong pull request; người có thẩm quyền chỉ đổi sang Accepted sau khi các điều kiện được xử lý hoặc rủi ro được chấp thuận chính thức.

## 9. Tổ chức buổi rà soát quyết định kiến trúc

Không nên để chỉ một người tự viết và tự duyệt ADR cho hệ thống quan trọng. Buổi review cần có người đại diện cho vận hành, dữ liệu, bảo mật và nghiệp vụ liên quan; quy mô tùy mức độ rủi ro.

### 9.1. Chuẩn bị trước review

Người viết gửi trước:

1. ADR Proposed cùng design diagram.
2. Bảng functional/NFR và các hard gates.
3. Ma trận phương án, giả định điểm số và câu hỏi chưa giải quyết.
4. Threat model mức phù hợp với dữ liệu và trust boundaries.
5. Cost estimate theo ít nhất hai kịch bản tải.
6. Kế hoạch PoC, load test, restore drill và rollback.
7. Danh sách rủi ro còn lại, owner và thời điểm quyết định cần được đưa ra.

Không gửi một bộ slide chỉ có tên sản phẩm rồi yêu cầu reviewer phê duyệt. Reviewer cần đủ dữ liệu để bác bỏ một giả định quan trọng.

### 9.2. Lịch review 45 phút

| Thời lượng mẫu | Nội dung | Người phụ trách |
|---|---|---|
| 5 phút | Nêu business problem và CUJ | Product / owner |
| 10 phút | Hard gates, kiến trúc và ba phương án | Author |
| 10 phút | Trade-offs, threat model, reliability, cost | Reviewers |
| 10 phút | Bằng chứng PoC, giả định chưa kiểm chứng, phản biện | SRE / Security / Data |
| 5 phút | Quyết định tạm thời, residual risk, owner | Architecture owner |
| 5 phút | Kế hoạch validation và thời hạn review lại | Facilitator |

Người review cần nêu **vấn đề + tác động + bằng chứng + yêu cầu sửa**, không chỉ trả lời “tôi thích GKE hơn”.

### 9.3. Checklist câu hỏi trong phòng review

**Phạm vi và chất lượng lập luận**

- Quyết định chính được mô tả trong một câu chưa?
- Có ít nhất hai phương án khả thi không?
- Tại sao loại phương án không được chọn?
- Các chỉ số có nguồn đo, giả định và thời điểm rõ ràng không?
- Có bỏ sót tình huống failure hoặc trường hợp lưu lượng tăng đột biến không?

**Security và compliance**

- Dữ liệu nhạy cảm chảy qua các thành phần và trust boundary nào?
- Ai có quyền deploy, ai là runtime identity và ai có quyền đọc secrets?
- Traffic ingress/egress, private connectivity, firewall, audit logs có rõ?
- Data residency áp dụng cho cả data, backup, logs và replica không?
- Các exception về IAM hoặc security policy đã được phê duyệt chưa?

**Reliability và operability**

- SLI/SLO gắn với CUJ nào và đo ở đâu?
- Có single point of failure, retry storm hoặc dependency failure không?
- RTO/RPO thực tế được đo theo failure scenario nào?
- Có on-call owner, alert, runbook, rollback và canary guardrail không?
- Nếu đêm nay database hoặc region lỗi, ai làm gì trước?

**Performance và cost**

- Có benchmark tải đại diện, p95/p99 và max connections?
- Lượng tải peak và growth được giả định từ đâu?
- Chi phí gồm egress, storage, logging, backups, HA và support chưa?
- Điều gì xảy ra nếu traffic gấp ba hoặc giảm 90%?
- Có cách giảm resource nhàn rỗi và đơn giá trên một đơn vị nghiệp vụ không?

## 10. Tiêu chí duyệt, yêu cầu bổ sung và từ chối

Review cần kết thúc bằng một trong các kết quả có thể thực thi:

| Kết quả | Ý nghĩa | Việc tiếp theo |
|---|---|---|
| Accepted | Có đủ bằng chứng và rủi ro được chấp thuận | Chốt ADR, triển khai theo gates |
| Accepted with conditions | Phương án phù hợp nhưng còn điều kiện phải đóng trước release | Ghi owner, deadline, evidence và release block |
| Needs revision | Thiếu dữ liệu hoặc giả định chưa đủ mạnh | Bổ sung PoC/chi phí/threat model rồi review lại |
| Rejected | Không đạt hard gate hoặc phương án kém phù hợp | Ghi lý do, tránh lặp tranh luận không có dữ liệu mới |
| Deferred | Chưa đến thời điểm quyết định | Ghi trigger và thời hạn mở lại |

Nếu tổ chức chỉ dùng trạng thái Proposed/Accepted/Rejected trong ADR, hãy ghi “Accepted with conditions”, “Needs revision” hoặc “Deferred” như **kết quả review** trong issue/PR; không nhất thiết mở rộng state machine.

### 10.1. Cách viết comment review có chất lượng

Ví dụ comment chưa hiệu quả:

> “GKE tốt hơn, dùng GKE đi.”

Comment có thể hành động:

> “ADR chưa chứng minh Cloud Run đáp ứng p95 300 ms ở 400 RPS, đặc biệt khi số connection Cloud SQL tăng theo instances. Đề nghị load test có p95/5xx/DB connections, ghi cấu hình concurrency và max instances, rồi mới Accept.”

Review tốt làm rõ **bằng chứng còn thiếu**, không chỉ thay sở thích cá nhân của tác giả bằng sở thích của reviewer.

## 11. Thực hành kiểm chứng và kiểm soát chi phí

Mục tiêu của lab là hoàn thành ADR và review, **không cần tạo tài nguyên GCP có tính phí** nếu chưa có project thử nghiệm được cấp phép.

### Bước 1: Viết problem statement

Trong hai đến bốn câu, mô tả người dùng, luồng nghiệp vụ, trở ngại hiện tại và quyết định đang cần. Tránh mở đầu bằng “chúng ta phải dùng Cloud Run” vì đó là kết luận trước khi phân tích.

### Bước 2: Liệt kê hard gates và NFR

Lập bảng yêu cầu có mã ID, nguồn yêu cầu, cách đo và mức ưu tiên. Phân biệt “phải” và “mong muốn”. Gắn owner cho các yêu cầu data residency, RTO/RPO và ngân sách.

### Bước 3: Vẽ sơ đồ kiến trúc hiện tại và đề xuất

Đánh dấu network/data trust boundaries và ít nhất ba luồng: request, database transaction và asynchronous event. Kiểm tra cấu trúc chưa có đường kết nối không xác thực hoặc dữ liệu truyền ngoài phạm vi.

### Bước 4: So sánh phương án và tính điểm

Cho tối thiểu ba phương án, công bố thang điểm và trọng số. Kiểm tra tổng trọng số bằng 100%, loại phương án không đáp ứng hard gate trước khi xếp hạng. Ghi lý do cho điểm và các biến số chưa có dữ liệu.

### Bước 5: Lập kế hoạch kiểm chứng

Đối với mỗi giả định quan trọng, ghi **cách kiểm chứng, owner, ngưỡng pass/fail, thời hạn và dữ liệu cần lưu**. Một kết luận “sẽ benchmark sau” không đủ để Accept không điều kiện nếu performance là hard gate.

### Bước 6: Peer review có phản biện

Phân vai người viết, Security, SRE và Finance. Reviewer ghi ít nhất ba câu hỏi có khả năng làm thay đổi quyết định. Author trả lời bằng evidence hoặc công khai rằng chưa biết.

### Bước 7: Chốt kết quả và liên kết bằng chứng

Ghi kết quả review, unresolved risks, owner, deadline, link issue/PR. Không xóa lựa chọn bị loại; giữ lý do loại để người vào sau hiểu lịch sử.

### Bước 8: Thiết lập lịch đánh giá lại

Sau khi hệ thống chạy, đo SLO, cost, incident, capacity và thời gian vận hành. Đặt các **revisit triggers** thay vì mặc định ADR không thay đổi.

## 12. Sử dụng công cụ Google Cloud để thu thập bằng chứng

Khi được cấp quyền vào môi trường kiểm thử, có thể thu thập bằng chứng theo các nhóm sau:

| Cần chứng minh | Nguồn dữ liệu / công cụ |
|---|---|
| SLI/SLO, error rate, p95/p99 | Cloud Monitoring dashboards và metrics từ ứng dụng |
| Request failure, exception | Cloud Logging / Error Reporting |
| Dependency latency | Cloud Trace hoặc instrumented spans |
| Compute/instance capacity | Cloud Run/GKE/Compute Engine metrics và quota |
| Cloud SQL saturation | Cloud SQL metrics, query insights khi phù hợp |
| Chi phí | Cloud Billing reports, export sang BigQuery, Pricing Calculator |
| IAM và service identity | IAM policies, audit logs, service account inventory |
| Deploy/rollback | Cloud Build/Cloud Deploy logs, revision history, Git commit |
| Backup/restore | Kết quả drill có timestamp và dữ liệu xác minh |

Chỉ dùng số liệu đã có quyền thu thập. Không lấy dữ liệu nhạy cảm, secret, thông tin khách hàng hoặc cấu hình private vượt quyền truy cập của người thực hành để đưa vào ADR công khai. Khi cần bằng chứng bảo mật, có thể liên kết đến tài liệu được kiểm soát thay vì sao chép credential hoặc nội dung audit nhạy cảm.

### 12.1. Cách viết một validation record

~~~yaml
check_id: PERF-01
scenario: "400 RPS trong 15 phút, 10% request tạo đơn mới"
environment: "staging, cùng region dự kiến với production"
configuration:
  cloud_run_max_instances: 20
  cloud_run_concurrency: 40
  hikari_maximum_pool_size: 10
pass_criteria:
  p95_latency_ms: 300
  http_5xx_ratio_max: 0.001
  database_connections: "không vượt ngưỡng được DBA phê duyệt"
evidence:
  status: "NOT_RUN"
  dashboard: "link chờ bổ sung"
  load_test_report: "link chờ bổ sung"
owner: "Orders API + SRE"
~~~

Đây là **biên bản dự kiến**, không phải kết quả đã đo. Khi chạy thật, thay `NOT_RUN` bằng trạng thái kiểm chứng theo quy định, ghi cấu hình image, commit SHA, ngày đo, số liệu và link báo cáo. Không lấy một bài load test staging đơn giản để tuyên bố đáp ứng SLO production cho mọi kịch bản failure.

### 12.2. Kiểm tra unit economics

Ngoài tổng chi phí tháng, so sánh chi phí mỗi đơn hàng thành công:

~~~text
Cost per 1.000 successful orders =
  (Chi phí hạ tầng thuộc phạm vi đã định / Số đơn thành công)
  × 1.000
~~~

Cần định nghĩa phạm vi: có tính Cloud SQL, Pub/Sub, egress, Logging và chi phí cluster/VM dùng chung không? Nếu chia chi phí chung cho nhiều ứng dụng, ghi rõ quy tắc phân bổ. Không lấy chi phí Cloud Run đơn lẻ làm tổng chi phí hệ thống.

### 12.3. Budget alert không phải hard spending cap

Cloud Billing Budgets giúp theo dõi và cảnh báo dựa trên ngưỡng, nhưng cảnh báo không tự bảo đảm dừng mọi chi tiêu. Một ADR cần định nghĩa guardrails thực tế như max instances, quota, quyền tạo resource, timeout, retention và quy trình phản ứng khi chi phí tăng. Cân nhắc thời gian trễ của dữ liệu Billing.

## 13. Quản lý rủi ro và kế hoạch rollback

Tài liệu “chúng tôi sẽ rollback nếu có lỗi” chưa đủ. Cần chỉ rõ **khi nào**, **ai**, **rollback cái gì**, **phụ thuộc nào không đảo ngược** và **cách kiểm tra phục hồi**.

| Rủi ro | Khả năng | Tác động | Biện pháp | Người sở hữu |
|---|---|---|---|---|
| Cloud SQL quá tải khi API scale out | Trung bình | Cao | Max instances, pool sizing, load test | Backend + SRE |
| Bản phát hành thay đổi schema không tương thích | Trung bình | Cao | Expand-and-contract, rollback rehearsal | Backend + DBA |
| Pub/Sub redelivery tạo đơn trùng | Trung bình | Cao | Idempotency key, unique constraint/outbox | Backend |
| Chi phí tăng trong mùa cao điểm | Trung bình | Trung bình | Budget alert, capacity limits, cost review | FinOps |
| Quá nhiều quyền IAM ở runtime | Thấp–trung bình | Cao | Least privilege, review và audit | Security |
| Không khôi phục được backup trong RTO | Chưa rõ | Cao | Restore drill và mục tiêu đo được | DBA/SRE |

Các đánh giá khả năng/tác động là **nhãn ví dụ**. Khi làm thật, dùng thang và tiêu chí đánh giá rủi ro của tổ chức; mức “chưa rõ” phải đi kèm hành động điều tra thay vì bị xem là rủi ro thấp.

### Rollback khác recovery

- **Rollback runtime:** chuyển traffic về Cloud Run revision trước hoặc khôi phục phiên bản triển khai trên GKE/MIG.
- **Rollback database:** không thể mặc định khôi phục schema/data về trạng thái trước bằng cách đổi image. Cần thiết kế migration tương thích hoặc kế hoạch phục hồi dữ liệu riêng.
- **Recovery sau mất dữ liệu:** phụ thuộc backup, PITR và khả năng restore đã kiểm chứng.
- **Recovery luồng message:** cần retry, dead-letter, replay, idempotency và một quy trình xử lý trùng.

Từng kiểu rollback/recovery có chủ sở hữu và bài kiểm tra riêng trong ADR hoặc tài liệu liên kết.

## 14. Quản trị ADR trong Git và quy trình thay thế quyết định

Một cấu trúc repository minh họa:

~~~text
orders-api/
├── src/
├── deployment/
│   └── cloud-run/
└── docs/
    └── adr/
        ├── README.md
        ├── 001-use-postgresql.md
        ├── 013-run-orders-api-on-cloud-run.md
        └── 024-supersede-013-for-kubernetes.md
~~~

Đây chỉ là ví dụ cấu trúc; trong bài thực hành này, bạn không cần tạo các file nêu trên.

Quy trình quản trị:

1. Tạo ADR với ID mới ở trạng thái Proposed trong pull request.
2. Gắn owner, reviewers và issue/architecture board tùy quy mô.
3. Review cùng thay đổi code/IaC hoặc trước khi build một thành phần khó đảo ngược.
4. Sau chấp thuận, chuyển Accepted, ghi ngày và điều kiện còn phải kiểm chứng.
5. Khi thay quyết định, tạo ADR mới; gắn ADR cũ là Superseded và liên kết qua lại.
6. Không xóa ADR bị Rejected hoặc Superseded: lịch sử giúp tránh lặp tranh luận mà không có dữ liệu mới.
7. Định kỳ rà soát những ADR có assumptions đã lỗi thời, chẳng hạn chi phí, chính sách region hoặc scale.

Nếu một ADR có nhiều quyết định độc lập, tách chúng. Ví dụ “chọn Cloud Run runtime” và “dùng outbox để bảo toàn sự kiện” nên có thể là hai ADR riêng dù được tham chiếu lẫn nhau. Như vậy khi thay eventing không bắt buộc viết lại toàn bộ hồ sơ chọn runtime.

## 15. Bài tập phản biện: tìm lỗi trong một ADR kém

Đọc đoạn ADR giả định:

~~~markdown
# ADR-X: Dùng GKE vì doanh nghiệp lớn

Status: Accepted

Chúng tôi chọn GKE vì Kubernetes tốt nhất cho microservices.
Ứng dụng cần chạy nhanh, luôn sẵn sàng và phải rẻ.
Không cần so sánh vì GKE là chuẩn công nghiệp.
Bảo mật dùng service account Owner để đỡ lỗi quyền.
Nếu deployment có lỗi, sẽ rollback.
Chi phí ước lượng 100 USD mỗi tháng.
~~~

Thảo luận nhóm: đoạn trên có thể được chấp thuận cho production hay chưa?

**Những điểm cần phản biện:**

1. Không có context và CUJ; không biết ứng dụng nào hay nhu cầu gì.
2. “Tốt nhất”, “nhanh” và “rẻ” không có thang đo hay bằng chứng.
3. Không có phương án khác; không đánh giá Cloud Run hoặc Compute Engine.
4. Không có thông tin cluster mode, region, node/workload requests hoặc network.
5. Cấp Owner cho runtime vi phạm nguyên tắc IAM tối thiểu.
6. Không ghi SLO, error budget, RTO/RPO hoặc chiến lược backup.
7. Chi phí 100 USD thiếu giả định, SKU, thời gian, network và storage.
8. Rollback không có trigger, owner, runbook hoặc xử lý database migration.
9. Không có người phê duyệt, bằng chứng kiểm thử hoặc rủi ro được chấp nhận.
10. Trạng thái Accepted không đáng tin vì không có trace của review/validation.

**Kết quả review phù hợp:** Needs revision hoặc Rejected tùy ràng buộc tổ chức. Reviewer nên yêu cầu tác giả viết lại context/NFR, lập shortlist, kiểm tra security và đưa kế hoạch test thay vì tự chuyển ngay sang Cloud Run.

## 16. Đánh giá chất lượng ADR bằng rubric

Mỗi tiêu chí chấm từ 0 đến 2 điểm:

- **0:** thiếu hoặc mô tả không thể kiểm chứng.
- **1:** có nội dung nhưng thiếu bằng chứng/owner.
- **2:** rõ ràng, có căn cứ hoặc kế hoạch kiểm chứng khả thi.

| Tiêu chí | Điểm tối đa |
|---|---:|
| Problem statement, CUJ và phạm vi | 2 |
| Functional/NFR, assumptions và hard gates | 2 |
| Phương án và lý do loại | 2 |
| Trade-offs theo Well-Architected | 2 |
| Bằng chứng performance/reliability/security | 2 |
| Cost estimate và sensitivity | 2 |
| Quyết định và hệ quả/rủi ro | 2 |
| Validation gates, owner và deadline | 2 |
| Rollback/recovery và vận hành | 2 |
| Revisit triggers, lịch sử và liên kết | 2 |
| **Tổng** | **20** |

Gợi ý sử dụng: 17–20 điểm là ADR rõ ràng để đưa vào vòng review chính thức; 13–16 cần bổ sung; dưới 13 nên biên soạn lại. **Rubric không thay thế hard gates**: một ADR đạt 19 điểm nhưng vi phạm yêu cầu bảo mật bắt buộc vẫn không được Accept.

### Bài tập mở rộng

Hãy thay một giả định của Orders API:

- Team đã có GKE platform và GitOps sẵn, vận hành 50 microservice.
- Nhu cầu chuyển từ HTTP API sang consumer chạy liên tục.
- Bắt buộc chạy native agent có quyền kernel.
- Cần triển khai nhiều region với data residency phức tạp.
- Ngân sách giảm 40% nhưng p95 giữ nguyên.

Với mỗi thay đổi, chỉ ra hard gate mới, cập nhật ít nhất hai ô của ma trận, nêu PoC cần làm và kết luận giữ nguyên hay thay phương án. **Không bắt đầu bằng tên sản phẩm**; bắt đầu bằng thay đổi yêu cầu.

## 17. Checklist nộp bài và chốt review

- [ ] ADR có ID, tiêu đề, trạng thái, ngày, owner và reviewers.
- [ ] Problem statement và CUJ được viết rõ.
- [ ] Có functional requirements, NFR và ràng buộc cứng đo được.
- [ ] Giả định tách khỏi sự kiện đã kiểm chứng.
- [ ] Có từ hai phương án thực sự khả thi và lý do loại phương án.
- [ ] Sơ đồ chỉ rõ thành phần, dữ liệu và trust boundaries.
- [ ] Ma trận có trọng số tổng 100%, kèm giải thích điểm.
- [ ] Security review có IAM, secret, ingress/egress và data protection.
- [ ] Reliability review có SLI/SLO, RTO/RPO, backup và test phương án lỗi.
- [ ] Performance review có p95/p99, concurrency và dependency bottlenecks.
- [ ] Cost review bao gồm dịch vụ phụ trợ và đơn vị chi phí nghiệp vụ.
- [ ] Có kế hoạch rollout, rollback runtime và recovery dữ liệu.
- [ ] Residual risks có owner, cách giảm thiểu và deadline.
- [ ] Chưa có bằng chứng thì ghi rõ NOT_RUN hoặc cần kiểm chứng.
- [ ] Kết quả review thể hiện Accepted/Needs revision/Rejected và điều kiện.
- [ ] ADR lưu cùng codebase hoặc nơi dễ tra cứu, có link tới evidence.
- [ ] Có revisit triggers để mở lại quyết định khi điều kiện thay đổi.

## 18. Tự kiểm tra

1. ADR khác gì với design doc và runbook?
2. Vì sao không nên chỉ dựa trên ma trận điểm số khi chọn nền tảng GCP?
3. Sáu trụ cột Well-Architected là gì, và có phải mọi trụ cột cần điểm tối đa không?
4. Vì sao một SLO 99,9% không tự động bảo đảm bởi việc chọn Cloud Run hay Cloud SQL HA?
5. Tại sao một quyết định “Cloud Run cho API” có thể đúng hôm nay nhưng cần ADR mới sau này?
6. Làm thế nào phân biệt fact, assumption và decision khi đọc một ADR?
7. Vì sao Cloud Billing Budget chỉ là một phần trong đánh giá cost?
8. Trong review, câu hỏi nào giúp kiểm tra “rollback” đã đủ thực thi?
9. Nếu design đáp ứng 5/6 trụ cột nhưng vi phạm ràng buộc data residency, có nên Accept không?
10. Khi nào cần đánh dấu một ADR là Superseded?

**Gợi ý đáp án**

1. ADR ghi lý do và trade-off của một quyết định; design doc mô tả kiến trúc thực thi; runbook hướng dẫn thao tác khi triển khai hoặc xảy ra sự cố.
2. Điểm thường dựa vào giả định và trọng số chủ quan; hard gates và bằng chứng kỹ thuật phải được kiểm tra trước.
3. Operational excellence, security/privacy/compliance, reliability, cost optimization, performance optimization và sustainability. Mục tiêu là hiểu trade-off và lý do ưu tiên, không phải luôn tối đa mọi trụ cột.
4. SLO là mục tiêu đo end-to-end theo CUJ và phụ thuộc toàn bộ hệ thống; HA của một dịch vụ không chứng minh DB recovery, network, code và downstream đều đạt mục tiêu.
5. Kỹ năng team, tải, chi phí, compliance hoặc yêu cầu runtime có thể thay đổi, khiến trade-off cũ không còn hợp lý.
6. Fact có nguồn hoặc phép đo; assumption chưa kiểm chứng; decision là lựa chọn được chấp thuận theo quy trình.
7. Budget alert không tự đặt hard spending cap; cần ước tính, quota, timeout, IAM, right-sizing và xem số liệu Billing.
8. Ai kích hoạt, điều kiện rollback là gì, quay lại phiên bản nào, xử lý schema/data thế nào và kiểm chứng khôi phục ra sao?
9. Không. Phương án không đạt hard gate phải được sửa, được phê duyệt exception hợp lệ hoặc bị loại.
10. Khi ADR mới thay đổi quyết định đã Accepted và cần lưu lịch sử liên kết giữa hai hồ sơ.

## Kết luận

Một ADR có giá trị khi nó **biến một lựa chọn kỹ thuật thành quyết định có thể kiểm chứng, có người chịu trách nhiệm và có khả năng thay đổi khi dữ liệu mới xuất hiện**. Với Google Cloud, cần liên kết phương án runtime, dữ liệu, network và IAM với yêu cầu kinh doanh, SLO, chi phí, vận hành và sự đánh đổi. Điểm số, sơ đồ và tên dịch vụ chỉ là công cụ; điều quan trọng là trình bày đúng bối cảnh, kiểm tra giả định và có kế hoạch xác minh/rà soát sau triển khai.

## Tài liệu tham khảo

- [Google Cloud Architecture Center — Architecture decision records overview](https://docs.cloud.google.com/architecture/architecture-decision-records)
- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework)
- [Well-Architected: Operational excellence](https://docs.cloud.google.com/architecture/framework/operational-excellence)
- [Well-Architected: Security, privacy, and compliance](https://docs.cloud.google.com/architecture/framework/security)
- [Well-Architected: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Well-Architected: Cost optimization](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Well-Architected: Performance optimization](https://docs.cloud.google.com/architecture/framework/performance-optimization)
- [Well-Architected: Sustainability](https://docs.cloud.google.com/architecture/framework/sustainability)
- [Google Cloud Architecture Center — Reference architectures](https://docs.cloud.google.com/architecture)
- [Google Cloud — Billing budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)

