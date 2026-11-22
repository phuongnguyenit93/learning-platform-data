# Áp dụng trụ cột độ tin cậy của Azure Well-Architected Framework

Một hệ thống đặt hàng trên Microsoft Azure có thể chạy bình thường hàng tháng nhưng vẫn mất doanh thu chỉ vì một lần lỗi cơ sở dữ liệu, hỏng cấu hình DNS, dịch vụ phụ thuộc bị chậm hoặc đợt triển khai mới khiến toàn bộ API trả HTTP 500. Mua thêm máy chủ không tự giải quyết được những tình huống đó: nếu tất cả replicas cùng kết nối một cơ sở dữ liệu không có phương án phục hồi, hệ thống vẫn có **điểm lỗi chung**; nếu không có quy trình quản lý thay đổi, một thao tác cấu hình sai có thể làm cả hai vùng triển khai ngừng hoạt động.

**Trụ cột Reliability (độ tin cậy)** của **Azure Well-Architected Framework (WAF)** hướng dẫn xây dựng workload có khả năng **duy trì chức năng được cam kết, chịu lỗi, phát hiện suy giảm, phục hồi và vận hành an toàn** theo nhu cầu thực tế của tổ chức. Đây không phải tính năng có thể “bật” một lần trong Azure Portal mà là một **quy trình thiết kế và kiểm chứng xuyên suốt vòng đời** từ yêu cầu kinh doanh, kiến trúc, code, hạ tầng đến diễn tập sự cố.

Bài **“Áp dụng trụ cột độ tin cậy của Azure Well-Architected Framework”** thuộc chương **Độ tin cậy và khôi phục thảm họa**, trong module **CLOUD_PROVIDERS_AZURE**. Bài nối kiến thức Azure subscription, resource group, Microsoft Entra ID, mạng ảo, dịch vụ tính toán, lưu trữ, dữ liệu và messaging với triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng Azure.

Sau bài học, bạn có thể:

- Giải thích các **nguyên tắc thiết kế Reliability**, phạm vi và quan hệ với bốn trụ cột WAF còn lại.
- Biến yêu cầu kinh doanh thành **business-critical user flows**, SLI/SLO, error budget, **RTO** và **RPO** đo được.
- Nhận diện **fault domains** và common-mode failures bằng dependency mapping, failure-mode analysis và đánh giá điểm lỗi đơn.
- Lựa chọn **redundancy, Availability Zones, multi-region, active-passive/active-active**, phân biệt failover dịch vụ với phục hồi ứng dụng.
- Thiết kế ứng dụng **chịu lỗi phụ thuộc** bằng timeout, bounded retry, backoff/jitter, circuit breaker, bulkhead, idempotency, queue và degraded mode.
- Phối hợp độ tin cậy cho **App Service, Azure Container Apps, AKS, Azure Front Door, Azure SQL, PostgreSQL, Storage, Cosmos DB, Service Bus và Key Vault**.
- Định nghĩa **backup, restore, PITR, geo-recovery, dữ liệu nhất quán, runbook và diễn tập DR** theo mục tiêu đã cam kết.
- Tổ chức **monitoring, alerting, incident response, change management, game days** và cải tiến từ postmortem.
- Cân đối **chi phí, độ phức tạp, khả năng phục hồi và hiệu năng** thay vì tối đa hóa số vùng một cách máy móc.

> **Phạm vi học tập:** Các sơ đồ, mục tiêu SLO, cấu hình và lệnh là ví dụ được giả định cho **workload lab**, không phải cấu hình áp dụng cho mọi dịch vụ/region. Tính năng zone redundancy, geo-replication, backup retention, failover, SLA và cách tính phí phụ thuộc Azure service tier, SKU, region và thời điểm. Khi áp dụng thật, xác minh tài liệu/support matrix/giá/SLA hiện hành và diễn tập trên tài nguyên được phê duyệt. Không thao tác trên Azure production trong quá trình biên soạn bài.

## 1. Reliability là gì và khác Availability như thế nào?

**Availability (khả dụng)** thường biểu diễn mức độ dịch vụ sẵn sàng cho yêu cầu trong một khoảng thời gian. **Reliability (độ tin cậy)** rộng hơn: hệ thống có tiếp tục tạo ra **kết quả nghiệp vụ đúng** khi các thành phần suy giảm, có phục hồi đúng thời hạn, giữ dữ liệu trong giới hạn tổn thất cho phép, và vận hành được trong những điều kiện không bình thường hay không.

Một API trả HTTP 200 từ cache nhưng phát hành đơn hàng trùng, mất dữ liệu hoặc không gửi được giao dịch thanh toán **không đáng tin cậy** dù dashboard availability hiển thị màu xanh.

| Thuật ngữ | Câu hỏi cần trả lời | Đơn vị/biểu hiện |
|---|---|---|
| **Availability** | Dịch vụ có phục vụ requests được không? | % thời gian/yêu cầu thành công |
| **Reliability** | Workload có giữ chức năng đúng, chịu lỗi và phục hồi được không? | SLO, RTO/RPO, data correctness, resilience tests |
| **Durability** | Dữ liệu được ghi có còn tồn tại sau lỗi không? | Xác suất/tính bền vững bản ghi, backup/replication |
| **Resilience** | Hệ thống chịu tác động lỗi và tiếp tục phục vụ ở mức chấp nhận được không? | Fault tolerance, isolation, graceful degradation |
| **Recoverability** | Sau gián đoạn, hệ thống khôi phục chức năng/dữ liệu nhanh đến đâu? | RTO/RPO, restore test evidence |
| **Disaster recovery** | Khi fault domain lớn hỏng, làm sao khôi phục workload ở nơi/đường khác? | Runbook, secondary region, backups và failover |
| **Security** | Workload có chống truy cập/phá hoại trái phép không? | IAM, encryption, change approval, incident containment |

**Một số ranh giới thiết yếu:**

- **HA không thay backup:** replicated data có thể nhân bản ngay việc xóa nhầm hoặc dữ liệu hỏng.
- **Backup không thay HA:** restore có thể tốn hàng giờ, không đáp ứng mục tiêu gần như không gián đoạn.
- **Multi-region không thay DR plan:** cần chuyển ingress, data leadership, dependencies, rollback và diễn tập.
- **SLA của một dịch vụ Azure không phải SLO của toàn ứng dụng:** end-to-end user flow có thể thất bại dù từng thành phần vẫn đáp ứng SLA riêng.
- **Giám sát không tự làm hệ thống khỏe:** alert chỉ là bằng chứng để vận hành nếu không có hành động khôi phục phù hợp.

### 1.1. Reliability trong năm trụ cột Azure WAF

| Trụ cột | Liên quan đến bài này |
|---|---|
| **Reliability** | Khả năng chống lỗi và hồi phục có kiểm chứng |
| **Security** | Identity, secrets, network và kiểm soát thay đổi để hạn chế sự cố do tấn công/sai cấu hình |
| **Cost Optimization** | Chi phí redundancy, backup, replicas, replication, drills và standby |
| **Operational Excellence** | Observability, runbooks, CI/CD, tự động hóa, incident response và postmortem |
| **Performance Efficiency** | Headroom, scale, latency, throttling và backpressure khi gặp peak/load |

Các trụ cột có **trade-off**: multi-region giúp tăng khả năng phục hồi nhưng tăng độ phức tạp, dữ liệu bất đồng bộ và chi phí; tắt toàn bộ logs để tiết kiệm có thể làm mất khả năng chẩn đoán lỗi.

### 1.2. Điều gì được đo: user flow trước, resource sau

~~~mermaid
flowchart LR
    USER[Khách đặt hàng] --> API[API tạo đơn]
    API --> SQL[(Azure SQL Database)]
    API --> SB[Azure Service Bus]
    SB --> WORKER[Worker xử lý thanh toán]
    WORKER --> PAY[Payment provider]
    API -. Trace / metrics .-> OBS[Azure Monitor / App Insights]
    SQL -. Health / logs .-> OBS
    SB -. Queue lag / dead letters .-> OBS
~~~

Nếu SQL đã nhận commit, Service Bus publish thất bại và client retry, bài toán reliability là **tính nhất quán đơn hàng và idempotency**, không chỉ tăng số lượng API pods. Hệ thống cần xác định khi nào một đơn được xem là đã chấp nhận và có thể tái dựng/cứu các bước sau.

## 2. Năm nguyên tắc thiết kế cốt lõi của Reliability

Azure WAF diễn giải Reliability theo các hướng thiết kế liên quan nhau. Trong bài, ta sử dụng năm nhóm tư duy để đánh giá kiến trúc:

1. **Design for business requirements** — bắt đầu từ tác động kinh doanh, mục tiêu chức năng, ưu tiên luồng quan trọng, SLO/RTO/RPO.
2. **Design for resilience** — giả định lỗi sẽ xảy ra, tạo redundancy, isolation, graceful degradation và kiểm soát lỗi lan truyền.
3. **Design for recovery** — có phương án phục hồi dữ liệu và dịch vụ, failover/failback, thử nghiệm RTO/RPO.
4. **Design for operations** — giám sát, cảnh báo, runbook, triển khai an toàn, response và cải tiến liên tục.
5. **Keep it simple** — giảm components, dependencies, modes và thủ tục mà đội vận hành không thể thực sự kiểm soát.

### 2.1. Áp dụng vào một workload thực tế

| Nguyên tắc | Thiết kế/hoạt động cụ thể | Evidence phải có |
|---|---|---|
| Business requirements | Luồng checkout 99,9% SLO, RPO 5 phút giả định | Business owner phê duyệt và metric definition |
| Resilience | API nhiều replicas/zone, timeout và queue isolation | Fault-injection/load-test results |
| Recovery | SQL PITR, regional failover, traffic switching, runbook | Restore/failover drill và thời gian đo |
| Operations | Synthetic checks, metrics, on-call, change rollout/canary | Alert history, incident records, SLO dashboard |
| Simplicity | Bỏ dependency đồng bộ không cần ở đường checkout | Dependency diagram và change review |

**Không áp dụng cả năm bằng cách tick checklist trên giấy.** Phải liên hệ từng quyết định với user flow, failure mode và bằng chứng kiểm thử; một kiến trúc phức tạp nhưng không có runbook không đáng tin hơn kiến trúc đơn giản có phục hồi rõ ràng.

### 2.2. Tránh anti-pattern “mọi thứ phải HA”

Không nhất thiết mọi component của một ứng dụng đều cần multi-region. Có thể:

- Checkout/đơn hàng: SLO/RTO/RPO cao.
- Báo cáo doanh thu theo ngày: chấp nhận cập nhật chậm, batch retry.
- Email marketing: không nhất thiết khôi phục trong 5 phút.
- Website giới thiệu: cached static content có thể hoạt động độc lập.

Ưu tiên **critical flows và data integrity** thay vì chi tiền đồng đều. Một replica cho job import có thể chấp nhận nếu có checkpoint/replay và deadline phù hợp; trái lại một API thanh toán với single regional DB là rủi ro lớn nếu yêu cầu business đòi regional recovery.

## 3. Từ business impact đến user journeys quan trọng

### 3.1. Business Impact Analysis (BIA)

Một BIA hiệu quả trả lời:

- Nếu chức năng dừng **5 phút, 1 giờ, 1 ngày** thì có tác động gì?
- Sự cố làm **mất giao dịch, chậm giao dịch, lộ dữ liệu hay sai tiền**?
- Có thời điểm cao điểm/campaign hoặc ràng buộc thanh toán/pháp lý không?
- Luồng nào có **dependency đồng bộ** với provider bên ngoài?
- Ai có quyền tuyên bố incident và quyết định degrade/DR?
- Có khách hàng/ngành/khu vực nào đòi SLO khác nhau?

Ví dụ phân cấp:

| User flow | Business criticality | Sự cố chấp nhận | Điều không được phép |
|---|---|---|---|
| **Tạo đơn hàng** | Rất cao | Tạm chờ, trả trạng thái pending có kiểm soát | Đơn trùng/mất đã cam kết |
| **Tra cứu đơn** | Cao | Đọc bản copy gần mới trong giới hạn | Trả trạng thái sai mà không đánh dấu |
| **Thanh toán** | Rất cao | Queue/retry có idempotency | Charge trùng, mất chứng từ |
| **Email thông báo** | Trung bình | Trễ vài phút/giờ, replay | Làm checkout fail đồng bộ |
| **Báo cáo BI** | Thấp hơn | Dữ liệu trễ theo batch | Làm DB OLTP cạn kết nối |

### 3.2. Dependency map bắt buộc có phần con người

~~~mermaid
flowchart TD
    U[User flow: Checkout] --> EDGE[DNS + Azure Front Door / ingress]
    EDGE --> APP[App Service / Container Apps / AKS]
    APP --> SQL[(Order database)]
    APP --> KV[Key Vault / identity]
    APP --> MQ[Service Bus]
    MQ --> W[Order worker]
    W --> EXT[Payment external API]
    APP --> OBS[Telemetry / alerts]
    SQL --> BK[Backup + secondary data strategy]
    TEAM[On-call / IAM / DBA / Network teams] -. Response and approvals .-> APP
    TEAM -. Recovery .-> BK
~~~

Ngoài Azure resources, phải vẽ cả **DNS provider, certificate issuer, identity, deploy pipeline, external payment provider, on-call roster và người có quyền restore**. Một DR runbook phụ thuộc vào một admin duy nhất đang nghỉ phép là failure mode thực sự.

### 3.3. Phân loại trạng thái dữ liệu

| Loại dữ liệu | Ví dụ | Độ bền/khả năng phục hồi cần thiết |
|---|---|---|
| Source of truth | Đơn hàng, thanh toán, ledger | Consistency, backups/restore, audit |
| Transactional derived | Inventory reservation | Idempotent updates, reconciliation |
| Replayable stream | Service Bus messages/outbox | At-least-once handling, DLQ và replay |
| Cache | Redis session/read models | TTL/invalidation, rebuild/backing store |
| Ephemeral | Scratch files, pod local disk | Không được xem là durable |
| Telemetry/audit | Logs, traces, Activity Log | Retention/access theo incident/compliance |

**RPO=0** cho một luồng không tự bảo đảm bởi việc chọn “geo-redundant storage” nếu giữa source DB, queue và external payment còn các bước chưa được commit nhất quán. Phải định nghĩa **điểm xác nhận giao dịch (commit/acknowledge)** và cơ chế phục hồi từ từng loại state.

## 4. SLI, SLO, SLA và error budget

### 4.1. Ba khái niệm dễ nhầm

**SLI (Service Level Indicator):** chỉ số đo trải nghiệm dịch vụ, ví dụ tỷ lệ checkout requests được chấp nhận và ghi đơn chính xác.

**SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một cửa sổ, ví dụ 99,9% yêu cầu hợp lệ thành công trong 30 ngày rolling.

**SLA (Service Level Agreement):** cam kết hợp đồng/điều khoản với khách hàng hoặc nhà cung cấp; Azure SLA thường xác định availability cho **một dịch vụ và configuration cụ thể**, không tự là end-to-end SLA của ứng dụng.

### 4.2. Định nghĩa SLI tốt

Ví dụ:

\[
\mathrm{CheckoutSuccessRate}
=
\frac{\text{số request hợp lệ tạo đơn thành công}}
{\text{tổng số request hợp lệ muốn tạo đơn}}.
\]

Phải quy định:

- **Numerator:** có tính HTTP 202 accepted vào queue là thành công không, và làm sao xác minh eventual fulfillment?
- **Denominator:** loại trừ client 4xx do nhập sai hay không, xử lý timeout/cancel thế nào?
- **Scope:** production, region, customer segment, operation?
- **Window:** rolling 28 ngày, calendar month hay mỗi ngày?
- **Latency:** một request thành công sau 2 phút có đạt SLO checkout không?
- **Correctness:** chống duplicate, đúng số tiền/đơn/địa chỉ?

Nếu API trả 202 để che khi backend queue bị tắc 24 giờ, **HTTP success SLI sẽ đánh lừa đội vận hành**. Nên có thêm SLI *order completion within 10 minutes*, queue lag và reconciliation.

### 4.3. Availability error budget

Với SLO 99,9% trên **30 ngày liên tục**, budget lý thuyết cho thời gian không đáp ứng mục tiêu (giả định đo theo thời gian đồng đều):

\[
30\times24\times60\times(1-0{,}999)
=43{,}2\text{ phút}.
\]

| Mục tiêu SLO 30 ngày | Error budget tính theo thời gian* |
|---|---:|
| 99,0% | 7 giờ 12 phút |
| 99,5% | 3 giờ 36 phút |
| 99,9% | 43 phút 12 giây |
| 99,95% | 21 phút 36 giây |
| 99,99% | 4 phút 19,2 giây |

\*Bảng giả định **time-based availability, 30 ngày chính xác**. Với request-based SLI, error budget là **số requests lỗi cho phép**, không thể đổi trực tiếp thành phút khi traffic biến thiên.

### 4.4. Dùng error budget để ra quyết định

Một cách vận hành:

~~~text
If recent burn rate is high:
  freeze risky releases
  prioritize resiliency fixes
  tighten rollout approvals and test recovery

If SLO is comfortably met:
  continue controlled feature delivery
  still review high-impact failure modes and DR readiness
~~~

Error budget **không phải giấy phép bỏ mặc khách hàng trong 43 phút**; nó là công cụ cân bằng tốc độ thay đổi và rủi ro. Một sự cố mất dữ liệu có thể không được “bù” bằng 99,99% uptime.

### 4.5. SLO tree cho một ứng dụng

~~~text
Business objective: 99.9% valid checkout within 2 seconds
  ├─ Front-end endpoint availability
  ├─ API success and p95/p99 latency
  ├─ Order DB commit and data integrity
  ├─ Queue accepted and consumer lag
  ├─ External payment provider success/reconciliation
  └─ Dependency auth and network connectivity
~~~

Không đặt tất cả resource CPU alerts làm SLO. CPU cao có thể là **signal để điều tra**, còn SLO phải mô tả kết quả người dùng/kinh doanh.

## 5. RTO, RPO và mục tiêu khôi phục

**Recovery Time Objective (RTO):** khoảng thời gian tối đa business chấp nhận để **khôi phục chức năng** sau sự cố được định nghĩa.

**Recovery Point Objective (RPO):** khoảng mất mát dữ liệu tối đa business chấp nhận, thường biểu diễn độ cũ của điểm khôi phục so với thời điểm xảy ra sự cố.

### 5.1. Trục thời gian

~~~text
Last recoverable consistent point       Failure              Recovery
            |                              |                     |
            v                              v                     v
------------+------------------------------+---------------------+---
            <-------- RPO window ---------><------ RTO -------->
~~~

RTO thường tính từ mốc kích hoạt sự cố theo định nghĩa của tổ chức, nên cần tính cả **phát hiện, quyết định failover, provision/restore, khởi động, DNS/traffic chuyển hướng và xác minh nghiệp vụ**. Nếu chỉ đo thời gian chạy lệnh restore mà bỏ 45 phút chờ on-call, RTO đã bị tính sai.

### 5.2. Ví dụ mục tiêu theo workflow

| Workflow | RTO giả định | RPO giả định | Kiến trúc cần xem |
|---|---:|---:|---|
| Checkout | 30 phút | 5 phút | Multi-zone + geo recovery, outbox, replay |
| Tra cứu đơn | 1 giờ | 15 phút | Read replica/cache rebuild |
| Email notification | 8 giờ | 1 giờ | Durable queue, replay và rate limiting |
| Báo cáo nội bộ | 24 giờ | 24 giờ | Batch restore/recompute |
| Audit/legal ledger | Theo chính sách nghiêm ngặt | Có thể yêu cầu gần 0 | Dữ liệu nhất quán, kiểm soát chứng từ |

**Các số trên chỉ để học cách thiết kế**, không phải SLA Azure hoặc recommendation mặc định. RPO gần 0 có thể đòi kiến trúc commit đồng bộ có latency/cost tradeoff; replication bất đồng bộ thường có nguy cơ mất các writes chưa đến secondary khi failover.

### 5.3. Tại sao RTO và RPO không phải cùng một metric?

Hệ thống có thể restore DB về bản backup cách đây 1 phút (**RPO ≈1 phút**) nhưng cần 6 giờ để deploy lại app/network/IAM (**RTO ≈6 giờ**). Ngược lại, frontend chuyển sang region B trong 2 phút (**RTO tốt**) nhưng database secondary trễ 30 phút (**RPO xấu**).

### 5.4. Chọn recovery pattern từ mục tiêu

| Mẫu | RTO thường | RPO thường | Tổn phí/giới hạn |
|---|---|---|---|
| Rebuild from code + daily backup | Dài | Có thể nhiều giờ | Rẻ nhưng không phù hợp critical write flows |
| Automated PITR backup | Trung bình, phải đo | Theo backup/log chain và service | Restore instance/database mới, cutover cần plan |
| Warm standby regional | Ngắn hơn khi diễn tập tốt | Theo async replication lag | Trả phí standby/data replication |
| Active-active read + single writer | Ngắn cho reads | Writes vẫn phụ thuộc leader/failover | Routing/consistency complexity |
| Multi-region multi-write | Có thể thấp cho regional failover | Phụ thuộc consistency/conflict model | Conflict resolution, latency, thiết kế khó |

**Đừng viết “RPO=0 và RTO=0” trên slide rồi coi đó là kiến trúc.** Cần xác định mọi stateful dependency và chứng minh được bằng test; một external payment gateway không có idempotency có thể phá tính đúng dù data replication nhanh.

## 6. Fault domains và failure-mode analysis

Độ tin cậy bắt đầu bằng câu hỏi: **thành phần nào có thể hỏng, phạm vi ảnh hưởng đến đâu, tín hiệu nào phát hiện được và điều gì có thể tự phục hồi?**

### 6.1. Các lớp lỗi cần mô phỏng

| Fault domain | Ví dụ | Cách phòng ngừa và phục hồi |
|---|---|---|
| **Process/instance** | JVM crash, OOM, VM reboot | Multi-instance, health probe, restart/replacement |
| **Host/rack** | Host lỗi, storage path lỗi | Managed service/multiple replicas, platform healing |
| **Availability Zone** | Mất điện/mạng phạm vi zone | Zone redundancy được SKU/region hỗ trợ |
| **Region** | Regional service outage | Multi-region plan, geo replication, traffic failover |
| **Control plane** | Deployment API không dùng được | Preprovision, hạn chế phụ thuộc deploy lúc incident |
| **Identity/secrets** | Entra/Key Vault/network policy lỗi | Caching có hạn, circuit breaker, break-glass có kiểm soát |
| **Dependency** | SQL timeout, Service Bus throttling | Timeout, queue, isolation, backpressure |
| **Data** | Xóa nhầm, logical corruption, ransomware | Backup/PITR, immutable copies, restore rehearsal |
| **Configuration** | DNS, NSG, certificate, role sai | IaC/PR review, canary, rollback config |
| **Human/process** | On-call vắng, runbook lỗi thời | Ownership, drills, approvals |
| **External provider** | Payment/SMS API down | Idempotency, fallback, async process |

**Một Availability Zone chỉ tách một số rủi ro hạ tầng.** Nếu cả ba zones cùng chạy code bị lỗi hoặc cùng phụ thuộc vào secret/DB connection string sai, lỗi vẫn lan khắp workload.

### 6.2. FMEA: Failure Mode and Effects Analysis

| Thành phần | Failure mode | Tác động user flow | Detection | Phòng ngừa/giảm thiểu | Recovery owner |
|---|---|---|---|---|---|
| API | Replicas hết bộ nhớ | Checkout 5xx | Error rate + OOM/restarts | Memory sizing, HPA, load testing | App/SRE |
| Azure SQL | Primary unavailable | Cannot commit order | DB errors/health | HA tier, failover strategy | DBA/platform |
| Service Bus | Send throttled | Order completion trì hoãn | Send errors, queue lag | Backoff, outbox, retry budget | App/platform |
| Key Vault | Role/grant bị sửa | Secret lookup lỗi | Key Vault audit + API failure | IaC review, least privilege | IAM/SRE |
| DNS/Front Door | Route sai region | Traffic sai đích | Synthetic multi-region probes | Config review, staged rollout | Network/SRE |
| Schema migration | Drop cột sớm | Old/new versions lỗi | Error spikes, migration logs | Expand/contract | DBA/release |

Đánh giá từng mode theo **severity, likelihood, detectability, recovery difficulty**. Có thể dùng Risk Priority Number để sắp thứ tự tương đối, nhưng không để điểm số thấp che một rủi ro **mất dữ liệu/tiền có hậu quả rất lớn**.

### 6.3. Common-mode failures

~~~text
App deployed in zones 1, 2, 3
All three zones depend on one Key Vault config / DB writer
One bad RBAC or DNS change → every zone affected
~~~

Tương tự, một pipeline có quyền sửa mọi regions, Azure Firewall rule chung hoặc một DNS zone bị xóa có thể khiến multi-zone/multi-region ngừng cùng lúc. Dependency map phải bao gồm **shared services và con người**, không chỉ VM/pod placement.

### 6.4. Sản phẩm của FMEA

Với mỗi rủi ro nghiêm trọng, tạo bản ghi có: **failure mode, SLI bị ảnh hưởng, owner, mitigation, alert, recovery runbook, rollback conditions, thử nghiệm gần nhất và rủi ro còn lại**. Định kỳ review sau architecture changes, incidents và thay đổi nhà cung cấp.

### 6.5. Dependency availability math chỉ mang tính mô hình

Nếu ba **dependencies nối tiếp, bắt buộc và độc lập** mỗi cái availability 99,9% trong cùng khoảng:

\[
0{,}999^3\approx 0{,}997003,
\]

tức khoảng **99,7003%** trong mô hình đơn giản. Lỗi thực thường **tương quan** và hệ thống có thể dùng cache/fallback/async. **Không nhân Azure SLA rồi gọi kết quả là SLO đã đo được**. Hãy dùng phép tính để đặt câu hỏi dependency nào thật sự cần nằm trên đường đồng bộ của người dùng.

## 7. Reliability architecture: bỏ single point of failure

### 7.1. Từ đơn điểm sang chịu lỗi

~~~mermaid
flowchart LR
    subgraph BAD[Single-point architecture]
      U1[Users] --> ONE[One API instance]
      ONE --> ONEDB[(One DB primary)]
    end
    subgraph BETTER[Zone-aware architecture with recovery]
      U2[Users] --> LB[Ingress / health-based routing]
      LB --> API1[API zone A]
      LB --> API2[API zone B]
      LB --> API3[API zone C]
      API1 --> DB[(Managed database with verified HA)]
      API2 --> DB
      API3 --> DB
      DB -. Backup / regional recovery .-> REC[Recoverable state]
    end
~~~

Sơ đồ **không** hứa DB tự có zone redundancy vì API chạy ba zones. Cần xác minh **từng database tier**, cấu hình, failover time và tính nhất quán.

### 7.2. Redundancy có ba phần

1. **Compute redundancy:** nhiều instances/pods/sites để chịu lỗi một node.
2. **Data redundancy:** replicas/zone-geo copies phù hợp durability, consistency và failover.
3. **Recovery/control redundancy:** DNS/routing, backups, scripts, identities, quyền vận hành và người ra quyết định.

Có compute redundancy nhưng thiếu data/recovery redundancy thì workflow ghi dữ liệu vẫn có điểm lỗi chung.

### 7.3. Không khuếch đại bottleneck bằng autoscaling

30 API replicas × Hikari pool 30 connections có thể tạo **900 potential DB connections**. Nếu database không có connection budget đó, tăng replicas làm hệ thống **tăng lỗi**. Sizing cần capacity headroom, pool limits, load shedding, retry budgets, admission control và load test.

### 7.4. Bulkhead và tách chức năng phụ

~~~mermaid
flowchart LR
    CLIENT[Checkout request] --> CORE[Order API]
    CORE --> DB[(Order database)]
    CORE --> OUTBOX[(Transactional outbox)]
    OUTBOX --> BUS[Service Bus]
    BUS --> EMAIL[Notification worker]
    BUS --> ANALYTICS[Reporting worker]
~~~

Nếu email/SMS lỗi, checkout vẫn có thể thành công khi email là chức năng phụ. **Bulkhead** là chia executor pool, concurrency limit, resource quota hay workload riêng để lỗi một phụ thuộc không hút sạch threads của các luồng khác. **Outbox** duy trì event sau commit DB, nhưng delivery có thể at-least-once: consumer vẫn phải idempotent.

### 7.5. Simplicity và operational burden

Mỗi service mới có DNS, credentials, capacity, monitoring, runtime/version và runbook. Không thêm API gateway, service mesh, cache, queue hoặc database phụ nếu chúng không xử lý failure mode cụ thể. Multi-region active-active khi đội vận hành chưa kiểm soát conflict resolution có thể **kém tin cậy hơn** active-passive đơn giản đã được diễn tập.

## 8. Availability Zones: khi nào đủ, khi nào chưa đủ?

**Availability Zone (AZ)** là miền lỗi vật lý tách biệt trong một Azure region được hỗ trợ. **Không phải mọi Azure region, service hoặc SKU** đều hỗ trợ zones hoặc cùng dạng phân bố/HA.

### 8.1. Zonal vs zone-redundant

| Mô hình | Ý nghĩa | Rủi ro |
|---|---|---|
| **Zonal resource** | Chọn zone cụ thể khi provision | Một zone vẫn có thể là điểm lỗi đơn |
| **Multi-zonal replicas** | Nhiều app replicas trong nhiều zones | Ingress, placement, shared state |
| **Zone-redundant managed service** | Azure quản redundancy giữa zones theo tier | Availability/feature/latency/failover theo service |
| **Regional service không cấu hình zones** | Provider xử lý theo product design | Không mặc định có AZ SLA |

**Một VM ở zone 1 không tự nhân sang zone 2.** Một Azure Storage ZRS không tự cung cấp secondary region. Với App Service, Container Apps, SQL, PostgreSQL, AKS, phải kiểm tra SKU/region/replica prerequisites.

### 8.2. Zone outage test

~~~text
Region A:
  Zone 1: API replica A (failed)
  Zone 2: API replica B (healthy)
  Zone 3: API replica C (healthy)

Ingress routes only to healthy instances.
DB, queue and identity dependencies remain usable.
Expected: critical user flow remains within SLO.
~~~

Sau khi mất zone 1, capacity 2 zones còn lại có đủ chịu toàn bộ traffic không? Nếu mỗi zone chạy sát trần, mất một zone sẽ gây failure cascade. Thiết kế **N+1/N+K headroom** theo load và fault model, không định mức cố định “một replica là đủ”.

### 8.3. Checklist theo dịch vụ

| Dịch vụ | Điều phải xác minh |
|---|---|
| **VM/VMSS** | Zone placement, Load Balancer/probes, disk support |
| **App Service** | Plan tier, region, zone redundancy setting, instance minimum |
| **Container Apps** | Managed environment SKU/region support và cấu hình zone redundancy |
| **AKS** | Node pools, topology spread, PDB, ingress, stateful dependencies |
| **Azure SQL** | Service tier/region zone redundancy, failover behavior |
| **PostgreSQL Flexible Server** | Zone-redundant HA/standby, expected failover |
| **Storage** | LRS vs ZRS vs GRS/GZRS và read access to secondary |
| **Service Bus** | Namespace tier, data availability, disaster recovery features |

### 8.4. Cách kiểm tra

1. Ghi resource type/SKU/region/replica count.
2. Kiểm tra document/support matrix **đúng thời điểm**.
3. Xác minh placement/thực tế active replica và network routing.
4. Xác định shared dependencies xuyên zones.
5. Diễn tập lỗi trong staging bằng cách an toàn.
6. Đo end-to-end user SLI, p95 và failover time.

Không hardcode zone number universal: các **logical zone identifiers** có thể được ánh xạ vật lý khác giữa subscriptions; regional support cũng thay đổi.

## 9. Multi-region resilience: active-passive và active-active

Một region outage vượt phạm vi chịu lỗi Availability Zones. Multi-region có thể giúp, nhưng **không có nghĩa Azure tự failover toàn bộ workload chỉ vì bạn chọn paired regions**.

### 9.1. Active-passive (warm standby)

~~~mermaid
flowchart TB
    USERS[Global users] --> FD[Azure Front Door / global router]
    FD -->|Primary healthy| R1[Region A application]
    FD -. Failover after decision .-> R2[Region B standby]
    R1 --> D1[(Primary database A)]
    D1 -->|Async geo replication if supported| D2[(Secondary DB B)]
    R2 --> D2
    MON[Incident command] -. routing/DB promotion .-> FD
~~~

Region B phải có **runnable infrastructure, identities, certificates, images, DNS, networking, quotas và data recovery path**; một Bicep template chưa deploy chưa phải warm standby. Front Door health routing và database failover là **hai hoạt động riêng**: không chuyển write traffic sang B trước khi database secondary được promote an toàn và consistency/replay semantics đã rõ.

### 9.2. Active-active

~~~mermaid
flowchart TB
    U[Users] --> EDGE[Global router]
    EDGE --> A[Region A active app]
    EDGE --> B[Region B active app]
    A --> STATE[Single-writer or supported multi-write data]
    B --> STATE
    STATE --> CONS[Consistency/conflicts/lag]
~~~

Hai application regions active **không đồng nghĩa database multi-write**. Nếu DB chỉ có writer tại A, requests tại B có thể phải ghi xuyên vùng. Với multi-write (ví dụ một cấu hình Azure Cosmos DB hỗ trợ), phải xác định consistency level, conflict resolution, ordering và idempotency.

### 9.3. Azure region pairs không thay DR plan

- Không phải mọi Azure region đều có paired region theo mô hình truyền thống.
- Paired region không tự tạo replicas cho app, DB, secrets hay container images.
- Services khác nhau có geo replication/failover semantics và region support khác nhau.
- Chọn B dựa trên data residency, SKU availability, quotas, capacity, mạng, identity và vận hành, không theo “pair” một cách máy móc.
- Không suy rằng Azure region pairing bảo đảm một ứng dụng có RTO cụ thể.

### 9.4. Chọn secondary region

| Tiêu chí | Câu hỏi |
|---|---|
| Data residency | Có được replicate dữ liệu/logs qua region B? |
| Failure independence | Có shared dependency giữa A/B? |
| Service support | App/AKS/SQL/ACR tier cần có ở B? |
| Capacity | Đã có quotas và khả năng scale khi A mất? |
| Network | Private Endpoints/DNS/NSG/Firewall/VPN đủ? |
| Identity | Entra/Key Vault/certificates/roles đủ? |
| Data | Sync/async, writer promotion, RPO/conflicts? |
| Cost | Standby compute, storage replication, network egress? |
| Operations | Ai tuyên bố DR, có runbook và diễn tập? |

### 9.5. Failback là release riêng

Sau khi A hồi phục, **không tự chuyển traffic lại**: xác định authoritative writer, kiểm tra divergent data, re-seed A từ source of truth B qua quy trình dịch vụ hỗ trợ, thiết lập replication/recovery posture, test consistency, rồi cutback có approval và rollback plan. Tránh **split-brain**, khi A/B cùng nhận writes nhưng không có multi-write conflict model.

## 10. Điểm vào: DNS, Front Door và load balancing

| Dịch vụ | Thích hợp | Giới hạn |
|---|---|---|
| **Azure Front Door** | Global HTTP/HTTPS routing, origin health, WAF | Health probe, reroute timing, TLS và config |
| **Traffic Manager** | DNS-based steering | DNS TTL/resolver/client cache |
| **Application Gateway** | Regional layer 7/WAF | Zone config, listener cert, backend probes |
| **Azure Load Balancer** | Regional layer 4 TCP/UDP | Zone/SKU/probe/outbound rules |
| **AKS ingress** | Cluster routing | Controller redundancy, DNS/TLS/service endpoints |

**Front Door không tự sao chép dữ liệu hoặc promote Azure SQL secondary.** DNS-based failover không hứa mọi clients đổi endpoint trong vài giây.

### 10.1. Health probes

~~~text
BAD /health:
  Always returns HTTP 200 if process is alive.

BETTER /ready:
  Checks critical readiness with bounded timeouts.
  Does not perform payment writes or heavy DB queries.

LIVENESS:
  Checks local process responsiveness.
  Does not restart every pod on a transient remote DB outage.
~~~

Nếu liveness phụ thuộc SQL, DB outage 30 giây có thể làm mọi pods restart đồng loạt và tạo reconnection storm. Nếu readiness luôn 200, ingress vẫn route vào instance không thể checkout. Phân biệt liveness/readiness/startup và synthetic user-flow probes.

### 10.2. RTO của routing

\[
T_{\mathrm{failover}}\approx T_{\mathrm{detect}}+
T_{\mathrm{decision}}+T_{\mathrm{reroute}}+
T_{\mathrm{backend\ ready}}+T_{\mathrm{validate}}.
\]

Đây là **mô hình ước lượng**, không phải công thức Azure SLA; stages có thể chồng lấn. Health interval/threshold, control/data plane và DNS caching đều ảnh hưởng.

### 10.3. Drill routing

~~~text
1. Baseline user-flow SLI and primary region.
2. Simulate approved endpoint degradation in staging.
3. Verify health-based routing detects failure.
4. Verify traffic reaches secondary.
5. Verify data and identity readiness.
6. Stop test; check duplicate/missing orders.
7. Measure RTO/RPO.
8. Verify safe failback and restored redundancy.
~~~

Không tự gây outage production bằng việc tắt DNS/NSG/Key Vault/DB khi chưa có fault-injection scope và approvals.

## 11. Compute: App Service, Container Apps, AKS và VM

### 11.1. App Service

- Chọn plan/SKU/region có availability và **zone redundancy** khi mục tiêu đòi hỏi.
- Chạy nhiều instances nếu hỗ trợ; autoscale với headroom và load tests.
- Dùng deployment slots/canary khi phù hợp; review slot-specific settings, app configuration và connections trước swap.
- Phân biệt App Service **VNet Integration outbound** và Private Endpoint inbound; tất cả instances cần reach database/Key Vault.
- Tách durable state khỏi local ephemeral files và in-memory sessions.
- Health checks, warm-up, multi-region apps + global routing khi RTO cần.

**Slot swap không undo database migrations hoặc data writes.** Không copy production connection string vào staging slot nếu có nguy cơ tác động dữ liệu thật.

### 11.2. Azure Container Apps

- Cấu hình min/max replicas và cold-start tradeoff, tránh scale-to-zero cho latency-critical flows.
- Readiness/liveness/startup probes, graceful shutdown, concurrency limits.
- Single/multiple revision modes, traffic split/rollback khi áp dụng.
- Zone-redundant managed environment nếu SKU/region hỗ trợ và được cấu hình lúc provision.
- Runtime image pull identity, ACR networking, DNS, secrets phải hoạt động.
- Autoscaling theo HTTP/KEDA queue phải đi cùng DB/queue connection budgets.
- Jobs phải có idempotency, checkpoint và bounded retries.

Ví dụ:

~~~text
Normal:  6 replicas × 10 DB connections = up to 60.
Peak:   40 replicas × 10 DB connections = up to 400.
If DB budget is 100, blindly autoscaling API may worsen outage.
~~~

Đây là số **connections tiềm năng**, không khẳng định mọi connection đều đang mở. Capacity/connection budgets phải được đo thực.

### 11.3. AKS

| Lớp | Biện pháp |
|---|---|
| Control plane | SLA/tier phù hợp, không phụ thuộc API server cho serving path |
| Nodes | Node pools trải zones, autoscaler và spare capacity |
| Pods | Replicas/topology spread/anti-affinity |
| Disruptions | PodDisruptionBudget, drain safety, maintenance |
| Runtime | Liveness/readiness/startup probes, graceful termination |
| Scaling | HPA/KEDA, rate limits, backpressure và database budget |
| Network | Ingress controller replicas, DNS/CNI/NetworkPolicy |
| State | PV/CSI zone binding, app-aware backups and DB strategy |
| Upgrade | Surge/node image rotation/API version compatibility |
| DR | Cluster/registry/GitOps/IaC/data restore in recovery region |

**PDB thường điều tiết voluntary evictions, không chữa host/zone outage**. Ba replicas trên cùng node vẫn là một fault domain; cần kiểm tra actual pod placement. Với stateful PVC, replica scheduling có thể bị giới hạn bởi zone-bound volume.

### 11.4. VM/VMSS

VM workloads cần zone placement/VMSS, LB probes, golden image, OS patch/Update Manager, disks/backup, replacement automation, zone quotas và không lưu nguồn dữ liệu duy nhất trên temporary local disk. Một VM có managed disk **không tự là HA** nếu không có thành phần thay thế/failover.

### 11.5. Đừng để serving plane phụ thuộc pipeline

GitHub Actions hoặc Azure Resource Manager tạm lỗi không nên làm app đang chạy phải ngừng xử lý request vì mỗi request phụ thuộc deploy API. Nhưng scale/recovery cũng có thể cần control plane, nên đặt capacity reserve/preprovision phù hợp RTO và kiểm tra quyền/quota trước sự cố.

## 12. Dữ liệu quan hệ: Azure SQL Database và PostgreSQL Flexible Server

Một ứng dụng stateless nhiều replicas vẫn phụ thuộc vào **database correctness và recovery**. Thiết kế database reliability gồm ba câu hỏi khác nhau: **primary HA**, **backup/point-in-time restore**, **khôi phục khi cả region hỏng**.

### 12.1. Azure SQL Database: ba lớp phục hồi

| Khả năng | Mục đích | Lưu ý |
|---|---|---|
| **Built-in high availability** | Platform xử lý nhiều lỗi compute/storage theo service tier | Không hứa zero downtime; driver/retry phải chịu transient disconnect |
| **Zone redundancy** | Giảm tác động zone outage nếu tier/region hỗ trợ và cấu hình đúng | Xem performance/failover behavior và SKU |
| **Automated backups/PITR** | Khôi phục về thời điểm trước delete/logical corruption | Restore thường tạo DB mới, cần cutover và đo RTO/RPO |
| **Geo replication/auto-failover groups** | Thử thiết kế DR region theo feature hỗ trợ | Thường async, có replication lag/data-loss tradeoff |
| **Long-term retention** | Backup lâu hơn theo compliance | Không thay hot standby/HA |

**Failover group** của Azure SQL có thể cung cấp listener/traffic switching cho những database được cấu hình đúng, nhưng không tự phục hồi **application, Key Vault, Front Door, VNets, secrets hoặc message queues**. Đánh giá phạm vi và hành vi failover group theo service/version cụ thể.

### 12.2. PostgreSQL Flexible Server

Kiến trúc reliability thường xem:

- **High availability** theo tier/region, có thể chọn same-zone hoặc zone-redundant standby khi hỗ trợ; đánh giá RTO/replica mechanics thực.
- Automated backups/PITR với retention được cấu hình và test restore.
- Replication/read replicas/geo read replica/failover khả dụng theo region, service generation và feature.
- WAL/replication lag và giới hạn transaction consistency.
- DNS/connection string/roles/extensions/network khi server được khôi phục.
- Connection pooling và retry/idempotency khi failover đóng existing sessions.

**PostgreSQL read replica không mặc nhiên trở thành writable primary trong mọi failure mode**, không bảo đảm zero data loss nếu replication async. Phải kiểm tra **planned/unplanned promotion**, feature support, role changes và application cutover.

### 12.3. RTO/RPO phải đo từ application

Ví dụ:

~~~text
09:00 DB primary failure begins
09:02 Platform/monitor detects failure
09:04 Database failover or restore operation starts
09:10 New writer ready
09:12 Application connections refresh and health checks pass
09:15 Checkout success SLI returns to expected range
~~~

RTO theo định nghĩa “checkout recovered” là khoảng **15 phút**, không phải chỉ 6 phút DB promotion. Nếu point restore là 08:55, RPO tính theo dữ liệu đã được xác nhận có thể tới **5 phút**, phải kiểm tra thực tế transaction logs và durable commits.

### 12.4. SQL client resiliency

- Đặt **connection timeout, command timeout** và request deadline có ngân sách.
- Hikari/JDBC pool phải loại bỏ stale connections khi failover; không giữ password/token hết hạn.
- Retry chỉ errors transient đã phân loại (connection reset, throttling, deadlock/serialization) và có giới hạn.
- Không tự retry bất kỳ exception nào của `@Transactional`: transaction outcome sau lost response có thể **không xác định**.
- Dùng **business idempotency key**, unique constraint và reconciliation khi ghi đơn/tiền.
- Với failover group listener, kiểm tra DNS/driver behavior và reconnect semantics.
- Nếu dùng Spring Data/JPA, `@Transactional` không làm hai database/queues thành một atomic transaction.

### 12.5. Migrations và rollback

~~~text
Phase 1: Add new nullable/compatible schema fields.
Phase 2: Deploy v2 while v1 still works.
Phase 3: Backfill and validate data.
Phase 4: Migrate readers/writers to new representation.
Phase 5: Remove old columns only after rollback window.
~~~

Rollback app image **không rollback DDL và dữ liệu đã ghi**. Diễn tập release với database phiên bản cũ/mới, locks và long-running transactions. Với critical data, migration có DDL principal riêng và backup/recovery checkpoint được phê duyệt.

### 12.6. Checklist database

| Kiểm tra | Bằng chứng |
|---|---|
| Tier/region HA phù hợp | Config và vendor support |
| Zone/geo recovery support | Failover target, replica status |
| PITR/backup retention | Backup policy và restore rehearsal |
| Encryption/keys/IAM | Entra/DB roles và key availability |
| Application reconnect | Transient error test và pool metrics |
| Recovery correctness | Unique orders, balances, no double-charge |
| Observability | CPU/IO/locks/failed connections/replication lag |
| Runbook | Who promotes, changes DNS/listener, validates |

## 13. Azure Storage và Cosmos DB: durability không đồng nhất availability

### 13.1. Storage replication

| Replication model | Ý nghĩa tổng quát | Không mặc nhiên có |
|---|---|---|
| **LRS** | Copies trong một region theo mô hình local | Zone/geo durability |
| **ZRS** | Copies giữa zones trong region khi hỗ trợ | Secondary region access |
| **GRS** | Geo replication đến secondary region theo feature | Automatic app failover, zero RPO |
| **RA-GRS** | GRS + khả năng đọc secondary theo hỗ trợ | Writable secondary, synchronous replication |
| **GZRS** | ZRS primary và geo-copy secondary theo model | Không cần failover khi region outage |
| **RA-GZRS** | GZRS + read-access secondary theo hỗ trợ | Zero-lag replicated reads |

**Tên replication không phải lời đảm bảo RPO=0.** Geo replication thường **asynchronous**; khi primary region hỏng trước khi write đến secondary có thể mất dữ liệu chưa replicate. Nghiên cứu **last sync time, account failover policies, access mode, DNS/endpoint behavior và supported account type**.

### 13.2. Account failover và ứng dụng

Quy trình phải xét:

- App có upload idempotent và content checksum không?
- Retry writes sau timeout có tạo blob trùng/overwrite không?
- Chuyển vùng có khiến client SDK/DNS/endpoint thay đổi và phải reconnect không?
- SAS tokens/Entra permissions/keys/private endpoints có hợp lệ ở vùng phục hồi không?
- Blob metadata/index/lifecycle/immutability có được giữ theo kỳ vọng feature không?
- Người dùng đọc secondary có chấp nhận stale data không?

Không thực hiện **unplanned Storage account failover** trên production chỉ để test, vì có thể ảnh hưởng durability/replication state và business operations. Tạo storage account lab riêng.

### 13.3. Soft delete, versioning, immutability và backup

Để giảm rủi ro **logical deletion/corruption**:

- Blob soft delete/versioning/snapshots theo tính năng/account type được hỗ trợ.
- Container soft delete hoặc blob version restore theo chính sách.
- Object replication/backup khi phù hợp với RPO/RTO.
- Immutable blob (WORM) khi compliance cần chống sửa/xóa.
- Tách data-plane least-privilege và backup/restoration roles.

**Một replica khác có thể đồng bộ ngay lệnh xóa nhầm**; cần versioning/backup/immutability độc lập. Retention chính sách có chi phí và không thể tùy tiện xóa dữ liệu immutable trước hạn.

### 13.4. Azure Cosmos DB: consistency và nhiều regions

Cosmos DB có thể hỗ trợ distribution/multi-region, consistency configurations và automatic failover theo account/API/capabilities. Cần hiểu:

| Yếu tố | Câu hỏi reliability |
|---|---|
| **Single write region** | Nếu writer region unavailable, cơ chế promote và lag? |
| **Multi-write** | Conflict resolution và idempotency khi cùng item được sửa ở hai regions? |
| **Consistency level** | Strong/bounded staleness/session/consistent prefix/eventual theo API/region setup và business contract? |
| **Partitioning** | Hot logical partition gây throttling dù tổng RU đủ? |
| **RUs** | 429/throttling có được SDK retry an toàn trong deadline? |
| **Backup** | Continuous/periodic backups, restore điểm thời gian theo mode/region support? |
| **Change feed** | Consumer checkpoint/replay/idempotency khi failover? |

**Multi-region database không tự bảo đảm không có conflict**. Nếu hai nơi cùng trừ tồn kho, phải định nghĩa ứng xử với đồng thời, version/ETag, invariants và reconciliation. Đừng bật eventual consistency cho sổ cái thanh toán chỉ vì latency thấp mà chưa đánh giá correctness.

### 13.5. Storage và Cosmos DB health phải đo từ app

- Upload/download/cosmos query SLI theo operation và tenant.
- p95/p99 latency, 429/503, RU/throughput, retry attempts.
- Replication lag/last sync, effective consistency, stale reads.
- Data corruption detection bằng checksums/business invariants.
- Failover rehearsal và restoration correctness.

Một dashboard storage availability có thể xanh trong khi ứng dụng dùng wrong endpoint/container permissions; SLO người dùng mới là trọng tâm.

## 14. Service Bus, Event Hubs và background workers

### 14.1. Tại sao queue tăng reliability?

Queue giúp **giảm coupling theo thời gian**: producer có thể chấp nhận request và lưu intent durable khi consumer ngừng tạm thời. Nhưng queue không làm workflow tự đúng nếu:

- Producer commit DB rồi publish thất bại, message bị thiếu.
- Consumer xử lý thành công rồi ack mất, message được giao lại.
- Một message độc hại lặp mãi làm consumer không tiến.
- Backlog vượt retention/TTL hoặc quota.
- Region DR không có mapping message state/namespace.

### 14.2. At-least-once và idempotent consumer

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Order DB + Outbox
    participant P as Outbox publisher
    participant BUS as Service Bus
    participant C as Consumer
    API->>DB: Commit order + outbox event atomically
    P->>DB: Read pending event
    P->>BUS: Send message with stable eventId
    BUS-->>C: Deliver message
    C->>C: Check idempotency / process
    C->>BUS: Complete message
    Note over BUS,C: Delivery or completion may be retried
~~~

Một consumer nên lưu **processed message/event IDs** hoặc enforce business unique keys ở authoritative store. Không coi Service Bus duplicate detection là **giải pháp duy nhất** chống lặp nghiệp vụ: nó có window/configuration/namespace-specific limitations, và ack/retry sau side effects cần xử lý riêng.

### 14.3. Service Bus recovery: phân biệt geo-DR và geo-replication

Tùy tier và tính năng hiện hành, Service Bus có những cơ chế **metadata disaster recovery alias** hoặc **geo-replication** với phạm vi dữ liệu khác nhau. **Không được đánh đồng metadata replication với sao chép nội dung messages đang nằm trong queue**.

Một quy trình DR phải hỏi:

1. Namespace thứ hai đã provision ở region khác chưa?
2. Geo capability của tier đó replicate **metadata hay cả message data**?
3. Failover alias/connection strings/managed identities thay đổi thế nào?
4. Những messages **unsettled/in-flight/dead-letter** ở nguồn có thể mất hoặc cần replay không?
5. Producers/consumers đã có outbox/checkpoint/idempotency?
6. Test message ordering, sessions, TTL, scheduled messages và DLQ theo topology thực?

Nếu requirement là “không mất một đơn đã accepted”, thiết kế **database outbox hoặc durable source of truth** đủ để tái phát những messages không đến secondary; không dựa vào tên “Geo Disaster Recovery” như lời hứa replicate mọi messages.

### 14.4. Event Hubs semantics

Event Hubs là event streaming platform, consumers đọc partitions theo offsets, có retention/replay. Reliability cần:

- Producer retry with stable IDs/partition keys theo use case.
- Checkpoints và consumer group offsets.
- Consumer idempotency vì processing có thể lặp sau crash.
- Throughput/partition count/headroom, consumer lag và throttling alarms.
- Retention đủ cho outage; archive/reprocessing khi cần.
- DR namespace/replication feature và data-loss semantics phải được kiểm tra.

Event Hubs **không phải transactional queue luôn giữ messages cho đến lúc xử lý xong**; retention có giới hạn. Không xóa checkpoint để “repair” production nếu sẽ gây replay lớn hoặc lặp downstream writes.

### 14.5. Backpressure và dead-letter queue

~~~text
Incoming: 1,000 messages/min
Consumer: 500 messages/min
Backlog growth: ~500 messages/min
After 60 minutes: ~30,000 additional pending messages
~~~

Nếu chỉ scale producer mà không scale consumers/dependencies, reliability giảm. Theo dõi **queue age of oldest message**, DLQ count, active consumers, processing latency, retry count; có policy xử lý poison messages thay vì vô hạn abandon/retry.

### 14.6. Redis/cache: vẫn phải có source of truth

Redis/managed cache giúp giảm latency và load, nhưng phải quyết định:

- Cache miss/fail có làm checkout ngừng hay fallback sang DB?
- TTL, invalidation, thundering herd và cache stampede mitigation?
- Chế độ HA/replication/persistence của Redis tier?
- Session state ở cache có yêu cầu durable state không?
- Khi cache trống sau failover, DB đủ capacity phục vụ re-warm không?

Không sử dụng cache như nguồn authoritative duy nhất cho đơn hàng/ledger. Với cache phụ, graceful degradation có thể trả data cũ **có nhãn/giới hạn** hoặc tạm giảm chức năng tùy business correctness.

## 15. Identity, Key Vault, mạng và cấu hình: những SPOF bị bỏ quên

### 15.1. Azure Resource Manager vs data plane

Một ứng dụng nên được thiết kế để tiếp tục phục vụ requests từ **data plane hiện có** khi management/control plane tạm không khả dụng. Tuy nhiên thao tác scale, deploy, thay network/keys và recovery có thể cần control plane; cần **preprovision/standby headroom và runbook** để không biến một management outage thành sự cố người dùng.

### 15.2. Microsoft Entra/managed identity

Managed identity tránh lưu password dài hạn, nhưng application vẫn cần:

- Token acquisition/retry/cache phù hợp SDK/driver.
- Quyền data-plane DB/Key Vault/Storage và Azure RBAC đúng scope.
- Không gọi login/token endpoint trên **mọi request** nếu SDK có caching an toàn.
- Không cache token quá hạn hoặc dùng token sai audience khi failover.
- DR region có identity/role assignments/tenant policies đã được kiểm thử.
- Break-glass identities được quản lý bảo mật, không dựa vào một người.

**Azure RBAC Contributor không tự cấp quyền SQL SELECT**, và managed identity tồn tại không tự mở network path. Mất identity hoặc sửa RBAC sai có thể làm cả multi-zone workload hỏng đồng loạt.

### 15.3. Key Vault secrets và certificates

- Tránh app phải đọc Key Vault đồng bộ **trong từng HTTP request**.
- Dùng SDK/managed integration và caching/rotation được hỗ trợ, có expiry và revocation policy.
- Xác định secret expiration, certificate rotation và Key Vault access/network policy.
- Nếu Key Vault unavailable, quyết định application tiếp tục bao lâu với cached secret **mà vẫn bảo đảm security**.
- Region B phải có secret/cert/keys và permitted principals theo mô hình replication/DR được chọn.
- Không sao chép client secrets thủ công vào GitHub hoặc container images.

**Security và reliability có thể xung đột**: cache credential lâu tăng khả năng chạy khi Entra/Key Vault outage nhưng tăng rủi ro dùng credential bị thu hồi. Phải chọn TTL/rotation theo threat model, không mặc định “cache mãi”.

### 15.4. Private Endpoints và DNS

Một App Service ở region B có thể chạy khỏe nhưng không kết nối Azure SQL vì:

- Chỉ có Private Endpoint ở region A/VNet A.
- Private DNS zone link/forwarding không được thiết lập cho B.
- NSG/UDR/Firewall không cho outbound TCP/TLS.
- FQDN được đổi thành private IP gây TLS hostname mismatch.
- Entra principal/DB role khác ở secondary.

**Một health endpoint trả 200 tại region B chưa chứng minh DB writer/queue/Key Vault path đã hoạt động**. Diễn tập **end-to-end transaction test** trong staging với credentials và network giống production.

### 15.5. IaC và drift management

Dùng Bicep/Terraform/ARM để version:

- Network/DNS/Private Endpoints/routing.
- Zone/multi-region deployment settings.
- Identity/federation/role assignments.
- Databases, backup/HA/geo configurations.
- Diagnostic settings, alerts, runbooks và outputs.
- Secrets **references** thay vì secret literal trong source/state.

Tuy nhiên **IaC cũng là nguồn common-mode failure**: một merge sai có thể thay toàn bộ regions. Tách stages, hạn chế quyền, review what-if/plan, policy gates, có rollback và state backup. Đừng dùng `terraform destroy` hoặc `az group delete` để sửa drift khi chưa phân tích dependencies.

## 16. Thiết kế ứng dụng chịu lỗi: timeout, retry, circuit breaker, bulkhead

Reliability không chỉ là hạ tầng có replicas. **Application code phải quyết định điều gì xảy ra khi một dependency chậm, trả 429/503, mất kết nối hoặc hồi phục sau gián đoạn**.

### 16.1. Deadline trước, retries sau

Giả sử checkout có p95 latency SLO **2 giây**. Nếu HTTP call đến inventory timeout 10 giây và SDK tự retry ba lần, một request đã vượt deadline trước khi ứng dụng trả lời.

~~~text
Client overall deadline:      2,000 ms
API work and serialization:     250 ms
DB transaction budget:          500 ms
Dependency budget:              750 ms
Network/margin:                 500 ms
~~~

Đây là **phân bổ giả định**, không phải default Azure SDK. Khi caller còn 250 ms, downstream không được tự dùng 5 giây. Truyền **deadline/cancellation** hợp lý; đặt connect timeout, read timeout, request timeout và retry budget phù hợp với SLO.

### 16.2. Exponential backoff + jitter

~~~text
Attempt 1 failed with transient 503.
Wait: small randomized backoff.
Attempt 2 if deadline still allows.
Wait: larger randomized backoff.
Attempt 3 only if policy permits and idempotent.
Otherwise fail fast / enqueue / degrade.
~~~

**Không retry vô hạn**: khi 10.000 clients cùng retry lập tức, dependency vừa phục hồi có thể bị đánh gục lần hai. Jitter giúp phân tán tải. SDK Azure thường có retry policy mặc định; tránh **nested retries** ở SDK + service + gateway + frontend khiến số requests bùng nổ theo cấp số nhân.

### 16.3. Retry matrix

| Lỗi | Retry? | Điều kiện |
|---|---|---|
| HTTP 429/rate limit | Có thể | Backoff/`Retry-After` nếu khả dụng, quota và deadline |
| HTTP 503/transient network reset | Có thể | Bounded attempts, operation idempotent |
| HTTP 401/403 | Thường không như transient data error | Kiểm tra token/permissions/policy; không spam auth |
| HTTP 400/validation | Không | Sửa input |
| SQL deadlock/serialization conflict | Có thể retry **whole transaction** | Isolation/policy và idempotency |
| Unique key conflict | Không retry mù | Kiểm tra business idempotency |
| Timeout sau ghi có thể đã commit | Chỉ khi có idempotency/reconciliation | Outcome không chắc |
| Event Bus message redelivery | Xử lý lại an toàn | Stable event ID/processed IDs |

### 16.4. Circuit breaker

Khi service thanh toán lỗi 90%, thay vì mỗi request chờ timeout 5 giây:

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error threshold reached
    Open --> HalfOpen: Cooldown elapsed
    HalfOpen --> Closed: Limited probes healthy
    HalfOpen --> Open: Probe fails
~~~

**Closed:** requests bình thường. **Open:** fail-fast/return degraded response, bảo vệ tài nguyên. **Half-open:** thử lượng nhỏ để xem dependency đã phục hồi. Circuit breaker thresholds phải gắn với **sample size**, latency, loại lỗi và thời gian; breaker không tự trả lời nghiệp vụ “đã thanh toán hay chưa”.

### 16.5. Bulkhead

~~~text
Orders API:
  Max concurrent payment calls: 30
  Max concurrent catalog lookups: 100
  Bounded DB pool: 20

If payment hangs:
  payment calls are limited;
  catalog reads still have dedicated capacity.
~~~

Đây là **các ngưỡng minh họa**. Tách thread pools/concurrency semaphores/queue workloads giúp ngăn starvation. Nếu vẫn dùng chung một database pool 20 cho mọi thứ, bulkhead ứng dụng chưa hoàn chỉnh.

### 16.6. Graceful degradation và fail-safe

| Chức năng | Khi dependency lỗi | Điều kiện chấp nhận |
|---|---|---|
| Product recommendations | Bỏ recommendation panel | Không ảnh hưởng tạo đơn |
| Email confirmation | Queue/retry sau | Đơn vẫn lưu và có thể truy cập |
| Catalog read | Cache data gần mới có TTL | UI ghi rõ độ cũ nếu ảnh hưởng quyết định |
| Inventory reservation | Từ chối/đặt pending khi không xác nhận được | Không oversell |
| Payment authorization | Không thông báo thành công khi chưa có chứng cứ | Không double-charge |
| Audit logging bắt buộc | Tùy compliance có thể chặn operation | Không “fail open” trái chính sách |

**Fail open vs fail closed** phải dựa trên nghiệp vụ/bảo mật. Cache gợi ý sản phẩm có thể trả stale; auth decisions/thanh toán không nên giả định thành công chỉ vì provider tạm mất.

### 16.7. Bounded retries bằng Java: minh họa

Ví dụ Java thuần cho **HTTP GET idempotent**, không dùng cho POST tạo thanh toán:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

class ResilientCatalogClient {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .build();

    String readCatalog(URI uri) throws Exception {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(700))
                    .GET().build();
                HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200) {
                    return response.body();
                }
                if (response.statusCode() != 429
                    && response.statusCode() != 503) {
                    throw new IllegalStateException(
                        "Non-retryable status " + response.statusCode());
                }
            } catch (IOException e) {
                if (attempt == maxAttempts) throw e;
            }
            if (attempt == maxAttempts) break;
            long jitterMs = ThreadLocalRandom.current()
                .nextLong(25, 125);
            Thread.sleep((1L << (attempt - 1)) * 100L + jitterMs);
        }
        throw new IllegalStateException("Catalog temporarily unavailable");
    }
}
~~~

**Đây là ví dụ cơ chế chứ chưa phải production-grade client:** có nguy cơ vượt **overall 2-second deadline** do các attempts + sleep, không đọc `Retry-After`, chưa hỗ trợ circuit breaker/telemetry/cancellation và không coi mọi `IOException` đều transient. Khi triển khai thật, ưu tiên Azure SDK/Resilience4j/Spring Retry (phiên bản hỗ trợ) với deadline được thực thi, classifications và test. Tuyệt đối không copy mẫu này cho endpoint ghi không có idempotency.

## 17. Idempotency, transactions, outbox và data correctness

### 17.1. Tại sao timeout sau commit nguy hiểm?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant DB as SQL Database
    C->>API: POST /orders (idempotencyKey K)
    API->>DB: INSERT order with unique K
    DB-->>API: Commit OK
    Note over API,C: Network response lost
    C->>API: Retry POST /orders (same K)
    API->>DB: Look up K
    DB-->>API: Existing order
    API-->>C: Return same order ID, not a new order
~~~

Nếu không có idempotency key, client retry sau timeout có thể tạo **hai đơn**. “HTTP 500” hoặc mất socket không cho biết transaction có commit hay không.

### 17.2. Database uniqueness là guardrail cuối

Ví dụ DDL logic:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

Đây là **DDL minh họa portable về ý tưởng**, chưa xử lý identity IDs/time/currency/SQL dialect cụ thể và **không dùng để tạo bảng production**. Service phải kiểm tra cùng key có **cùng payload/business intent**; một key dùng lại với payload khác nên báo conflict chứ không âm thầm trả đơn sai.

### 17.3. Transactional outbox

~~~text
Transaction:
  INSERT orders(...)
  INSERT outbox(eventId, orderId, payload, state='PENDING')
COMMIT

Publisher:
  Read pending outbox
  Send event to Service Bus
  Mark published (may repeat)

Consumer:
  Deduplicate by eventId or business invariant
  Apply side effect once
  Complete message after successful processing
~~~

Producer có thể send message thành công nhưng crash trước khi mark outbox published; event sẽ gửi lại. Vì vậy **outbox thường có at-least-once delivery**, không bảo đảm exactly once xuyên DB và broker nếu thiếu thêm invariant/idempotency.

### 17.4. Payment provider và reconciliation

Một thanh toán ngoài Azure cần:

- Stable merchant/order idempotency key nếu provider hỗ trợ.
- Tra cứu trạng thái payment trước khi retry sau timeout.
- Webhook processing với signature validation + dedup.
- Periodic reconciliation giữa provider ledger và order DB.
- Manual exception queue/operational playbook.

**Không retry charge** mù khi API trả timeout, vì giao dịch có thể đã được provider chấp nhận.

### 17.5. Data schema evolution trong failover

Trong active-passive, secondary có thể chạy cùng/khác app version lúc failover. Đừng phục hồi region B từ container image cũ không tương thích với DB schema mới. Tách infra deployment và schema rollout, dùng **forward/backward-compatible migrations**, test failover sau release và định kỳ verify standby image/digest.

## 18. Observability: từ Azure Monitor đến SLO dashboard

### 18.1. Các nguồn telemetry

| Nguồn | Ví dụ | Cách dùng |
|---|---|---|
| **Application Insights/OpenTelemetry** | HTTP requests, exception traces, dependency spans | User flow latency, errors, correlation |
| **Azure Monitor platform metrics** | DB CPU/IO, App instances, queue length | Capacity/availability signals |
| **Diagnostic settings/resource logs** | Key Vault audit, DB errors, App Service logs | Điều tra chi tiết/forensics |
| **Azure Activity Log** | Thay role, NSG, configuration, deployment | Control-plane change correlation |
| **Synthetic probes** | Checkout thử với synthetic data từ nhiều locations | End-to-end availability |
| **Business events** | Orders accepted, charged, reconciled | Độ đúng của nghiệp vụ |
| **DR/backup evidence** | Restore success, last sync, lag | Recoverability readiness |

**“Logs không có lỗi” không tương đương service khỏe.** Nếu diagnostic setting bị xóa hoặc ingestion hỏng, dashboard log errors sẽ trống trong khi khách hàng vẫn gặp lỗi.

### 18.2. SLI dashboard không chỉ CPU

Một dashboard Reliability nên cho thấy:

~~~text
Checkout success SLI (request and business-based)
Checkout latency p50/p95/p99
Remaining error budget + burn rate
API 5xx and timeouts by region/version
DB connection failures/locks/CPU/IO/replication lag
Queue age, DLQ, retries and consumer processing lag
Key Vault/Entra failures and network reachability
Synthetic checks per region
Active region/writer/image digest
Last successful restore/DR drill and measured RTO/RPO
~~~

### 18.3. KQL ví dụ: request-based availability

Nếu workload instrument Application Insights đến workspace có bảng `AppRequests` và columns như minh họa:

~~~kusto
AppRequests
| where TimeGenerated > ago(24h)
| where Name has "POST /orders"
| summarize
    Total=count(),
    Succeeded=countif(Success == true)
    by bin(TimeGenerated, 5m)
| extend SuccessRatePercent =
    iff(Total == 0, real(null), 100.0 * Succeeded / Total)
| order by TimeGenerated asc
~~~

**Không áp nguyên query cho mọi workspace**: bảng/cột ở workspace-based/classic App Insights có thể khác. `Success` của HTTP không đo data correctness; nếu API trả 202 nhưng xử lý queue fail, cần **business event completion SLI** riêng.

### 18.4. KQL ví dụ: Azure Activity Log sau incident

Nếu subscription đã export Activity Log vào `AzureActivity`:

~~~kusto
AzureActivity
| where TimeGenerated > ago(6h)
| project TimeGenerated, Caller, OperationNameValue,
          ActivityStatusValue, ResourceGroup, _ResourceId
| order by TimeGenerated desc
~~~

Kết hợp thay đổi code/configuration và thời điểm SLI suy giảm, nhưng **tương quan thời gian không tự chứng minh quan hệ nhân quả**. Cần xác nhận failure mode qua logs/traces và reproduction.

### 18.5. Error-budget burn-rate alert

Thay vì chỉ báo khi error rate vượt 1% trong 1 phút, đánh giá:

- **Fast burn:** SLO budget cạn nhanh trong cửa sổ ngắn; page on-call.
- **Slow burn:** budget cạn dần nhiều giờ/ngày; tạo ticket hoặc cảnh báo mức thấp hơn.
- **Traffic volume:** 1 lỗi trong 2 requests không giống 10.000 lỗi trong 1 triệu requests.
- **Monitoring gaps:** metric missing phải được phát hiện thay vì coi như “0 lỗi”.

Đặt multi-window, multi-burn-rate thresholds theo SLO và độ ồn thực; không dùng công thức copy-paste cho mọi service mà chưa thử historical false positives.

### 18.6. Azure Service Health và Resource Health

**Azure Service Health** cung cấp tín hiệu về incidents/maintenance/advisories ảnh hưởng dịch vụ Azure theo vùng/scope. **Resource Health** cho biết trạng thái một số tài nguyên từ góc nhìn platform. Cả hai hữu ích nhưng không thay end-to-end SLI: service health xanh trong khi app bị lỗi do deployment, hoặc platform incident không phản ánh mọi đường mạng/app dependencies của bạn.

Runbook cần phân biệt **Azure service event**, **resource degradation**, **application bug**, **data inconsistency** và **security incident** trước khi quyết định failover.

## 19. Incident response, on-call và thay đổi có kiểm soát

### 19.1. Incident lifecycle

~~~mermaid
flowchart LR
    ALERT[SLI/health alert] --> TRIAGE[Confirm scope and severity]
    TRIAGE --> COMMAND[Incident commander + owners]
    COMMAND --> MITIGATE[Contain / degrade / failover if justified]
    MITIGATE --> VERIFY[Validate critical flows and data]
    VERIFY --> POST[Postmortem and corrective actions]
    POST --> TEST[Update drills, SLO and runbooks]
~~~

**Không cần chờ tìm ra root cause hoàn toàn mới giảm tác động:** chuyển traffic, rate-limit hoặc tắt tính năng phụ có thể là mitigation tốt nếu có safety checks. Nhưng thao tác nguy hiểm như failover DB writer hay thay identity policy cần người được ủy quyền và ảnh hưởng dữ liệu phải được cân nhắc.

### 19.2. Runbook chuẩn cần gì?

- Trigger: biểu hiện và SLO threshold nào kích hoạt?
- Preconditions: scope/subscription/resource IDs/region/identity.
- Decision tree: lỗi regional, DB, mạng, code hay provider ngoài?
- Risk: data loss window, downtime, split-brain, compliance.
- Steps: ai bấm, lệnh nào, approval nào, điểm dừng/rollback.
- Verification: real traffic + synthetic tests + data integrity checks.
- Escalation: DBA/IAM/network/Azure support, người đại diện business.
- Communication: incident updates, stakeholder/customer status.
- Evidence: UTC timestamps, dashboard links, logs, last successful restore.
- Post-incident: action items với owner/deadline và diễn tập lại.

### 19.3. Không tự động failover khi chỉ một probe lỗi

Một lần HTTP 500 do một origin không nhất thiết region outage. Automated failover thiếu hysteresis có thể tạo **flapping** hai regions và nguy cơ dữ liệu divergence. Dùng nhiều signals: synthetic multi-location, regional health, DB writer/lag, queue, retry rate, readiness và có logic quorum/timeout phù hợp.

### 19.4. Change management là một phần Reliability

Pipeline build/deploy:

~~~text
PR → tests + security checks → staging → canary →
health/business SLO gates → production traffic ramp →
monitor → rollback/forward-fix
~~~

Đổi network/identity/DB schema cũng phải qua review/what-if/canary với blast radius giới hạn. **Rollback app image không rollback mọi side effects**. Nếu feature flag là biện pháp giảm thiểu, đảm bảo flag service không trở thành dependency bắt buộc cho mọi request và có default an toàn.

### 19.5. Postmortem không đổ lỗi cá nhân

Postmortem nên ghi: impact SLO/data, timeline UTC, contributing factors, detection gaps, mitigations worked/failed, recovery metrics và corrective actions được ưu tiên. Mục tiêu là **cải thiện hệ thống**, không tìm “ai đã bấm nhầm”; đồng thời vẫn cần accountability và change controls phù hợp.

## 20. Backup, restore, regional failover và Disaster Recovery Plan

**Disaster Recovery (DR)** là khả năng **phục hồi user flow và dữ liệu** sau một thảm họa vượt phạm vi tự chữa của thành phần. DR plan phải xuất phát từ business flow, không chỉ liệt kê backup files.

### 20.1. Ba kịch bản DR khác nhau

| Sự cố | HA hoặc replica đủ không? | Phục hồi thích hợp |
|---|---|---|
| Một VM/pod chết | Có thể, nếu replicas và health routing đúng | Auto replace/rollout |
| Primary DB node hỏng | Có thể theo tier/HA setting | Platform failover + reconnect và verify |
| Toàn Availability Zone hỏng | Có thể với zone redundancy | Zone-tolerant routing/capacity |
| Cả region unavailable | Thường cần DR design riêng | Secondary region/data promotion/cutover |
| Application xóa nhầm bảng | Replica có thể đã nhận lệnh xóa | PITR/backup/logical recovery, reconciliation |
| Ransomware/credential compromise | Replica có thể cùng bị xâm phạm | Protected immutable backups, incident containment |
| DNS/identity config bị sai toàn cầu | Multi-region có thể cùng hỏng | Config rollback/break-glass/cross-team response |

**Rủi ro mất dữ liệu logic** và **hỏng hạ tầng** cần recovery patterns khác nhau. Không giả định geo replica thay backup độc lập.

### 20.2. Recovery inventory: tất cả thành phần cần phục hồi

~~~text
Global entry:
  DNS, Front Door / Traffic Manager, certificates, WAF policies

Compute:
  App Service / Container Apps / AKS / VM images and configuration

State:
  Azure SQL/PostgreSQL, Storage, Cosmos DB, queues, outbox, cache

Identity and secrets:
  Managed identities, Entra roles, Key Vault, certificates, access policies

Networking:
  VNets, Private Endpoints, Private DNS, NSGs, UDRs, Azure Firewall

Observability:
  Log Analytics, telemetry, SLO alerts, incident communications

Delivery:
  IaC state, artifact image digests, release versions, runbooks
~~~

Nếu thiếu **service configuration, DNS, RBAC hoặc container images**, DB được restore vẫn chưa tạo thành một ứng dụng có thể phục vụ người dùng.

### 20.3. DR runbook có điều kiện rõ

1. **Declare:** incident commander xác nhận scope, severity, ảnh hưởng khách hàng và điều kiện failover.

2. **Freeze risky writes/deployments:** tạm dừng operations có thể gây divergence theo policy, giữ log/forensic evidence.

3. **Determine data authority:** region nào là writer, last replication timestamp, giao dịch nào đã acknowledged?

4. **Recover data:** promote replica hoặc restore backup theo phương thức supported; ghi recovery point.

5. **Validate dependencies:** secrets, identities, TLS, Private DNS, Service Bus namespaces, Storage access, app configs.

6. **Start/reconfigure workloads:** scale secondary compute/consumers, bảo đảm image/digest đúng.

7. **Switch traffic:** Front Door/global router/DNS theo chính sách sau khi DB B sẵn sàng.

8. **Verify:** synthetic checkout, idempotency, order totals, queue lag, health/latency, telemetry.

9. **Communicate:** thông báo trạng thái, RPO/RTO actual, tính năng bị degraded, ownership.

10. **Stabilize/plan failback:** hồi phục redundancy, re-seed former primary, đánh giá data repair.

Các bước trên là **khung**, không phải lệnh failover tự động trên Azure. Mỗi dịch vụ cần runbook chi tiết với **resource IDs, commands, preconditions, approvals và rollback** đã được thử trong lab.

### 20.4. Backup health cần điều gì?

- Backup gần nhất thành công và retention phù hợp.
- Backup scope bao phủ tất cả databases/containers/critical configuration.
- Có điểm restore **thực sự đọc được và nhất quán** ở cấp ứng dụng.
- Có bản backup không dễ bị xóa/chỉnh bởi cùng principal production.
- Có quyền và đường mạng để chạy restore vào environment riêng.
- Encryption keys/certificates/KV permissions còn khả dụng sau disaster.
- **Restore time được đo** trên dataset kích thước thực tế.
- Có data validation/query sample/checksum trước cutover.

**Không nhầm “backup job status succeeded” với “đã phục hồi được dữ liệu chính xác”**. Restore rehearsal là kiểm tra khả năng khôi phục, không chỉ kiểm tra bản sao tồn tại.

### 20.5. PITR không hoàn tác tất cả side effects

Nếu restore DB về 10:00 nhưng đã gửi payment và Service Bus event lúc 10:03:

~~~text
10:00 DB restore point
10:01 Order accepted
10:02 Payment charged externally
10:03 Email sent / downstream message processed
10:04 Incident
10:15 DB restored to 10:00
~~~

Sau restore, DB có thể “không biết” về payment đã charge. **Cần reconciliation** dựa trên payment provider ledger, event/outbox logs, audit trails; không đơn giản replay mọi event nếu có nguy cơ double-charge.

### 20.6. RPO/RTO đo trên toàn workflow

~~~text
Failure start UTC:               09:00
Incident detected UTC:           09:03
Failover approved UTC:           09:07
DB secondary writable UTC:       09:15
App/network fully ready UTC:     09:19
Checkout SLI recovered UTC:      09:22

Measured RTO: 22 minutes
Last confirmed recoverable order: 08:58
Potential RPO: 2 minutes, subject to reconciliation
~~~

Mẫu đo cần lưu bằng chứng. Nếu RTO mục tiêu là 15 phút thì runbook **FAILED** dù “database phục hồi thành công”, và phải có kế hoạch giảm detection/approval/cutover/validation time.

### 20.7. DR protection và bảo mật

DR site cần giữ Security posture:

- Không bật public database/firewall rộng để hồi phục nhanh nếu vi phạm policy.
- Không cấp Owner subscription cho người dùng chung.
- Không phục hồi dữ liệu nhạy cảm sang region/tenant không hợp lệ.
- Không để backups chứa cleartext secrets hoặc key material không quản lý.
- Không cho phép failover tự động khi có thể **split-brain** hoặc conflict data chưa xử lý.
- Có emergency privilege vừa đủ với audit và time bound.

## 21. Reliability testing: chaos engineering và game days

### 21.1. Tại sao phải phá thử có kiểm soát?

Một kiến trúc có đủ replicas/backup trên sơ đồ vẫn có thể hỏng khi thực tế:

- Autoscaler chưa kịp tăng capacity.
- DB client giữ stale connections quá lâu.
- Readiness probe vẫn xanh dù DB writer không khả dụng.
- Front Door route nhanh nhưng Key Vault/DNS ở region B lỗi.
- Secondary SQL replica lag quá mức RPO.
- On-call không có quyền promote/restore.
- Runbook chứa tên resource cũ.

**Fault injection có kiểm soát** giúp phát hiện các failure modes trước khi customer gặp chúng. Bắt đầu bằng kiểm thử nhỏ ở lab/staging, tăng phạm vi theo mức trưởng thành.

### 21.2. Hypothesis-first game day

~~~text
Hypothesis:
  "When one API pod fails in staging, checkout success remains ≥99.9%
   and p95 latency stays below the approved threshold."

Baseline:
  synthetic order requests, DB/queue metrics, pod placement

Injection:
  safely terminate one chosen staging replica

Observe:
  retries, load balancer routing, latency, errors, autoscaler response

Abort:
  stop if error budget/latency threshold exceeded

Verify:
  no lost/duplicated synthetic orders, system fully healthy
~~~

Không chạy experiment chỉ có “tắt server xem chuyện gì xảy ra”. Phải có **mục tiêu, baseline, owner, blast radius, safety stop và cleanup**.

### 21.3. Test cases theo cấp trưởng thành

| Mức | Fault injection an toàn | Điều xác nhận |
|---|---|---|
| 1 | Một pod/instance staging bị kill | Redundancy và readiness |
| 2 | Một dependency giả lập latency/503 | Timeout, retry, circuit breaker |
| 3 | DB staging connection tạm gián đoạn | Pool refresh, transaction outcome |
| 4 | Queue consumer staging dừng | Backpressure, DLQ, replay |
| 5 | Thử mất một zone trong môi trường được phép | Placement và headroom |
| 6 | Diễn tập traffic failover staging region | Global ingress/secondary readiness |
| 7 | Restore database backup vào môi trường biệt lập | PITR accuracy + RTO |
| 8 | Game day DR toàn workflow (approved) | Incident command, RPO/RTO và reconciliation |

### 21.4. Azure Chaos Studio và các công cụ khác

Azure Chaos Studio có thể hỗ trợ một số **fault actions/experiments** với supported targets và quyền cần thiết. Nhưng **không phải mọi Azure resource đều hỗ trợ cùng fault types**, và Fault injection là **thao tác có tác động thực** nếu chạy vào production. Ngoài Chaos Studio, có thể dùng test doubles/proxies, Kubernetes fault tools hoặc scripts an toàn trong môi trường lab.

Phải kiểm tra target/SKU/agent/permissions/regions, blast radius và recovery trước khi chạy. **Không dùng Chaos Studio để gây mất toàn bộ regional database hoặc xóa tài nguyên production nhằm chứng minh SLO.**

### 21.5. Injection vs rehearsal

- **Injection:** tạo lỗi có kiểm soát (latency, kill replica, throttle).
- **Rehearsal:** diễn tập người/quy trình (declaration, bridge, DB restore, failback).
- **Load test:** xác minh throughput/headroom và overload behavior.
- **Restore test:** chứng minh backup recovery.
- **Security response drill:** tình huống mất key/compromised principal, không truy cập trái phép thật.

Một game day tốt kết hợp **kỹ thuật và quy trình**, đo thời gian con người ra quyết định và xác minh data correctness.

### 21.6. Kết quả phải trở thành action items

Sau mỗi drill, ghi:

~~~text
Experiment ID:
  reliability-lab-zone-failure-001

Scope and owners:
  staging orders-api / SRE + DBA

Expected:
  Checkout p95 below objective; no lost orders

Observed:
  transient 5xx, reconnect time, database queue lag

RTO/RPO:
  measured vs objectives, include detection and validation

Findings:
  source of common-mode failure, operational gap

Actions:
  code/config/IaC/runbook changes with owner and deadline

Evidence:
  metrics/traces/checksums and approved change ticket
~~~

Đừng coi game day đạt chỉ vì hệ thống “đã lên lại”. Nếu sau thử nghiệm có messages tồn đọng hoặc outbox chưa publish, cần đo **drain time và reconcile** trước khi kết thúc.

## 22. FinOps của Reliability: trả tiền cho mục tiêu, không trả tiền cho sự phức tạp

### 22.1. Các lớp chi phí dự phòng

| Thành phần | Chi phí có thể tăng khi nâng reliability |
|---|---|
| Multi-zone compute | Replicas/instances, load balancers, cross-zone paths |
| Multi-region compute | Warm/hot standby, cluster/plan tối thiểu ở secondary |
| Data replication | Geo copies, standby databases, extra storage/IO |
| Backups | Retention, immutable copies, restore drills, egress |
| Global entry | Front Door/Traffic Manager, WAF, probes, traffic |
| Messaging | Premium tier, redundancy features, throughput units |
| Monitoring | Logs/metrics retention, synthetic tests, on-call tooling |
| Networking | Private Endpoints, NAT, VPN/ExpressRoute, firewall |
| Operations | Game days, incident response, change review, training |
| Security | Key management/role separation và bảo vệ backup |

**Chi phí thực phụ thuộc region, SKU, reservations, data usage và pricing tại thời điểm triển khai.** Không suy từ bảng này một giá Azure chính xác; dùng Azure Pricing Calculator/Cost Management và kiểm tra service-specific pricing.

### 22.2. Tính chi phí theo Business Impact

Một quyết định tốt so sánh:

~~~text
Cost of additional zone/region redundancy
  VS
Expected business impact of downtime/data loss
  + compliance penalties
  + reputational impact
  + operational recovery cost
~~~

Không có nghĩa mọi workload phải trả chi phí của multi-region active-active. Nếu báo cáo BI chấp nhận trễ 24 giờ, **batch restore** có thể phù hợp hơn warm standby suốt năm.

### 22.3. Hai kiến trúc minh họa

| Tiêu chí | Zone-redundant single region | Multi-region active-passive |
|---|---|---|
| Chống lỗi một zone | Có thể tốt nếu mọi components hỗ trợ | Primary vẫn cần zone design |
| Chống region outage | Không đủ | Có đường khôi phục khi chuẩn bị đầy đủ |
| Data RPO | Theo HA/backup | Theo replication/backup lag |
| RTO | Có thể thấp cho instance/zone | Phụ thuộc promote/cutover/secondary capacity |
| Cost | Thường thấp hơn | Standby/replication/network/operations cao hơn |
| Complexity | Thấp hơn | Nhiều identities/DR states/rollback scenarios |

### 22.4. Budget alerts không phải hard cap

Azure budget alerts giúp phát hiện cost tăng, không tự ngắt tài nguyên khi vượt budget. **Không đặt automation xóa production DB/secondary cluster khi chi phí vượt ngưỡng**. Thay vào đó: tìm resource mồ côi, tuning replicas, pool, logging, retention, scale/standby theo SLO và có owner phê duyệt.

### 22.5. Tối ưu reliability bằng giảm tải

Trước khi mua DB tier lớn hơn:

- Fix missing indexes và N+1 queries.
- Shorten transactions, tune Hikari pool × replicas.
- Cache read-only/noncritical data đúng TTL.
- Chuyển notification/reporting ra async queue.
- Thêm backpressure và request admission control.
- Giảm logging trùng và debug data không cần.
- Chỉ scale compute theo bottleneck đã đo.

**Tối ưu hiệu năng và đơn giản hóa kiến trúc có thể tăng reliability lẫn giảm chi phí.** Nhưng không cắt backup retention hoặc HA quan trọng để đạt mục tiêu chi phí ngắn hạn.

### 22.6. Quyết định có ghi nhận

Mỗi quyết định reliability nên có:

~~~text
Decision: warm standby in secondary Azure region
Business flow: checkout
Targets: RTO 30m, RPO 5m (illustrative)
Alternatives: backups only, multi-zone, active-active
Evidence: drill logs, load tests, replication lag
Costs: compute, storage, monitoring, drills
Risks: async data loss, split-brain, operator delay
Owner/review: platform + DBA + business / quarterly
~~~

Đây là **Architecture Decision Record (ADR) khung**, không phải quyết định thực cho bất kỳ hệ thống cụ thể nào. Sau khi business SLO đổi, phải đánh giá lại chi phí và thiết kế.

## 23. Case study: hệ thống đặt hàng có RTO 30 phút và RPO 5 phút

### 23.1. Bài toán

Một doanh nghiệp thương mại điện tử triển khai:

~~~text
Global edge:        Azure Front Door
Frontend/API:       Spring Boot on Azure Container Apps
Order data:         Azure SQL Database
Messaging:          Azure Service Bus + outbox
Object storage:     Azure Blob Storage
Secrets:            Azure Key Vault / managed identity
Telemetry:          Application Insights + Azure Monitor
IaC/CI:             Bicep/Terraform and GitHub Actions OIDC
DR region:          approved secondary Azure region
~~~

**Mục tiêu ví dụ** do business owner giả định:

| User flow | SLO | RTO | RPO |
|---|---|---:|---:|
| Checkout accepted đúng | 99,9% trong 30 ngày | 30 phút | 5 phút |
| Xem trạng thái đơn | 99,5% | 1 giờ | 15 phút |
| Xử lý email | Hoàn tất trong 4 giờ | 8 giờ | 1 giờ |
| Báo cáo BI | Có dữ liệu ngày trước | 24 giờ | 24 giờ |

Không phải các giá trị này đều nằm trong SLA của Azure. Chúng là mục tiêu **workload** cần được thiết kế và chứng minh, và business có thể yêu cầu **không chấp nhận mất payment evidence** dù RPO orders 5 phút.

### 23.2. Thiết kế high-level

~~~mermaid
flowchart TB
    USERS[Customers] --> FD[Azure Front Door]
    FD -->|Primary traffic| APPA[Region A Container Apps multi-zone]
    FD -. DR traffic .-> APPB[Region B warm standby]
    APPA --> SQLA[(Azure SQL A writer)]
    SQLA -->|Geo data replication if supported| SQLB[(Azure SQL B secondary)]
    APPB --> SQLB
    APPA --> OA[(Order outbox A)]
    OA --> SB[Service Bus / worker with idempotency]
    SB --> PAY[Payment provider]
    APPA --> KVA[Key Vault + MI A]
    APPB --> KVB[Key Vault + MI B]
    OBS[App Insights + Azure Monitor] -. monitor .-> APPA
    OBS -. monitor .-> APPB
    OBS -. monitor .-> SQLA
    OWNER[Incident command + DBA + SRE] -. control .-> FD
    OWNER -. promote safely .-> SQLB
~~~

**Hình là kiến trúc giả định, không tự bảo đảm Azure SQL secondary đang writable**. Cũng cần thiết kế Blob Storage/Service Bus regional recovery; nếu dữ liệu đơn hàng đã chuyển B nhưng queue vẫn chỉ ở A, nhiều worker workflows có thể bị mất/replay sai.

### 23.3. Failure-mode review

| Lỗi | Dự kiến ảnh hưởng | Countermeasure | Verification |
|---|---|---|---|
| Một Container App replica chết | Latency ngắn/tăng retries | Replicas và readiness routing | Kill 1 replica staging |
| Zone A hỏng | Capacity mất 1/3 | Zone redundancy/headroom | Safe zone test |
| Azure SQL primary failover | JDBC reset/timeout | Driver reconnect, bounded retry | SQL failover staging |
| Service Bus publish lỗi | Outbox pending tăng | Retry publisher/replay | Stop consumer / simulate 503 |
| Payment provider mất | Order pending, không double charge | Idempotency/reconciliation | Provider sandbox outage |
| Region A outage | Primary unavailable | Warm B, DB promotion, traffic switch | DR game day |
| Operator xóa bảng | Dữ liệu bị xóa logic | PITR protected backup | Restore test in isolated env |
| DNS/Key Vault config lỗi | Cả vùng/regions có thể lỗi | IaC, region-specific validation, rollback | Config negative test lab |

### 23.4. Failure timeline và RTO thực

~~~text
09:00 Region A cannot serve requests.
09:02 External synthetic probes fail in 2+ locations.
09:05 Incident commander declares regional incident.
09:09 DBA reviews last replication point, approves promotion.
09:14 Azure SQL secondary available as primary.
09:17 Region B app/Key Vault/private networking checked.
09:20 Front Door routes production traffic to Region B.
09:24 Checkout synthetic and real SLI recover.
09:28 Outbox/queue reconciliation initiated.
~~~

Theo ví dụ, user-flow **RTO = 24 phút**, đáp ứng mục tiêu 30 phút. Nhưng RPO vẫn **phải đo dữ liệu giao dịch thực**, không suy từ thời gian DB promotion. Nếu last committed/replicated order tại B chỉ tới 08:54, possible data gap 6 phút **vượt mục tiêu RPO 5 phút** mặc dù RTO đạt.

### 23.5. Data reconciliation sau failover

Xác định:

- Order IDs đã acknowledged ở A nhưng không có ở B.
- Payments external đã charge nhưng order record ở B thiếu.
- Outbox events đã publish nhưng DB restore quay lại trạng thái pending.
- Service Bus messages đang in-flight, DLQ, duplicates.
- File/blob attachments chưa replicate sang B.
- Cách khôi phục đúng: replay từ authoritative evidence, tránh double-write.

Một bảng reconciliation mẫu:

| Order ID | Client đã nhận success? | Payment state | DB B record? | Hành động |
|---|---|---|---|---|
| O-100 | Yes | Charged | Yes | OK |
| O-101 | Yes | Charged | No | Investigate and reconstruct with audit |
| O-102 | Unknown | Not charged | No | Safe idempotent retry |
| O-103 | Yes | Pending | Yes | Resume worker from outbox |

**Các rows là dữ liệu synthetic**, không phải giao dịch thật. Hành động rebuild cần business rules, approvals và audit; không tự chèn ledger records từ log không xác thực.

### 23.6. Failback B → A

Khi A hồi phục:

1. Xác định B là current authoritative writer.
2. Recreate data replication từ B về A theo Azure SQL features được hỗ trợ.
3. Đảm bảo identity/Key Vault/Service Bus/Blob/config ở A không cũ.
4. Kiểm tra canary traffic không gây split-brain.
5. Chỉ cutback sau approval, dưới giám sát SLO và reconciliation.
6. Xác minh standby DR posture mới được dựng lại.

### 23.7. Kết quả kiến trúc không được bỏ qua

Multi-region mang lại đường phục hồi nhưng có **RPO tradeoff do async replication**. Checkout phải dùng idempotency/outbox. Vùng B phải có đủ **compute, network, DB, credentials, queues, artifacts và on-call**, không chỉ một empty Azure subscription. Ngưỡng RTO/RPO được xem là **đạt khi drill thực chứng minh**, không phải khi tài liệu thiết kế hoàn tất.

## 24. Công cụ Azure và lệnh kiểm kê chỉ đọc

Các lệnh dưới đây chỉ để **kiểm tra cấu hình trên tài nguyên đã được cấp quyền**, không tạo resource, promote database, failover hay xóa dữ liệu. Chạy từ terminal lab có Azure CLI và quyền Reader/Monitoring Reader phù hợp; thay placeholders bằng resource IDs được phê duyệt.

### 24.1. Xác nhận tenant/subscription và inventory

~~~bash
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table
~~~

Đừng nhận diện production/lab chỉ dựa trên tên `dev` hoặc `test`; một resource group có thể chứa thành phần dùng chung.

### 24.2. Kiểm tra App Service/Container Apps

~~~bash
az webapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-webapp-name>" \
  --query "{id:id,state:state,location:location,hostNames:hostNames}" \
  -o json

az containerapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  --query "{id:id,location:location,latestRevision:properties.latestRevisionName}" \
  -o json

az containerapp revision list \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  -o table
~~~

Latest revision **không mặc nhiên nhận 100% traffic** trong multiple revision mode; phải kiểm tra ingress/weights/health thực. Lệnh phụ thuộc Azure CLI/Container Apps extension tương ứng.

### 24.3. Kiểm tra Azure SQL và PostgreSQL

~~~bash
az sql db show \
  --resource-group "<approved-rg>" \
  --server "<approved-sql-logical-server>" \
  --name "<approved-db-name>" \
  --query "{id:id,name:name,location:location,status:status}" \
  -o json

az postgres flexible-server show \
  --resource-group "<approved-rg>" \
  --name "<approved-pg-server-name>" \
  --query "{id:id,location:location,state:state,highAvailability:highAvailability}" \
  -o json
~~~

**Metadata show không chứng minh backup restore được**. Cần xem HA/backup/replica/failover details từ đúng service API/version và thực hiện restore rehearsal ở isolated environment. Không chạy `az sql failover-group failover` hoặc PostgreSQL promotion commands trên production trong bài học.

### 24.4. Kiểm tra Storage account và Service Bus

~~~bash
az storage account show \
  --resource-group "<approved-rg>" \
  --name "<approved-storage-account>" \
  --query "{id:id,location:location,sku:sku.name,kind:kind}" \
  -o json

az servicebus namespace show \
  --resource-group "<approved-rg>" \
  --name "<approved-servicebus-namespace>" \
  --query "{id:id,location:location,sku:sku.name}" \
  -o json
~~~

SKU `ZRS`/`GZRS` và Service Bus tier là đầu vào đánh giá, **chưa chứng minh đã diễn tập DR/data-loss semantics**. Không chạy Storage account failover để “kiểm tra” nếu thiếu risk approval.

### 24.5. Khám phá metrics rồi xem data

~~~bash
APP_ID="<approved-resource-id>"

az monitor metrics list-definitions \
  --resource "$APP_ID" \
  --output table

# Khi đã chọn metric name được liệt kê:
az monitor metrics list \
  --resource "$APP_ID" \
  --metric "<supported-metric-name>" \
  --interval PT5M \
  --output json
~~~

Metric names/aggregation/dimensions khác nhau theo resource provider; chọn từ **list-definitions**. Không giả định một query `CpuPercentage` có trên mọi resource.

### 24.6. Đọc Activity Log

~~~bash
az monitor activity-log list \
  --resource-group "<approved-rg>" \
  --offset 1d \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value}" \
  -o table
~~~

Activity Log ghi **control-plane events**, không phải đầy đủ request traces/DB queries. Dùng Azure Monitor/Application Insights/diagnostic settings nếu muốn kết hợp runtime evidence.

### 24.7. Read-only không có nghĩa không lộ thông tin

Một số `az resource show` hoặc `list` có thể trả metadata nhạy cảm (hostnames, IDs, configuration references). Hãy giới hạn `--query`, tránh in tokens/secrets/connection strings trong shared terminal logs, không đưa output production lên tài liệu học công khai.

## 25. Lab có hướng dẫn: áp dụng Reliability cho một ứng dụng Azure

**Lab này không được chạy trên production khi chưa có approval.** Có thể làm theo hai mức:

- **Lab A — kiến trúc và kiểm tra chỉ đọc:** không cần tạo hay sửa resource.
- **Lab B — diễn tập thực tế:** chỉ trong **subscription/resource group và data synthetic riêng** được cấp phép.

### 25.1. Bước 1: xác định user flow và business contract

Chọn ứng dụng giả định `orders-api`:

~~~yaml
workload: orders-api
environment: staging
businessOwner: ecommerce-operations

criticalFlows:
  checkout:
    successSlo30dPercent: 99.9
    latencyP95TargetMs: 2000
    rtoMinutes: 30
    rpoMinutes: 5
    sourceOfTruth: azure-sql-orders
  orderStatusRead:
    successSlo30dPercent: 99.5
    rtoMinutes: 60
    rpoMinutes: 15
  emailConfirmation:
    completionTargetMinutes: 240
    rtoMinutes: 480
    rpoMinutes: 60

notes:
  - Example only; obtain real business approval
  - Define denominator, synthetic checks and data correctness
~~~

**Đây là một ví dụ tài liệu mục tiêu**, không phải schema Azure ARM/Bicep hay YAML cấu hình có thể áp trực tiếp bằng `kubectl apply`. Owner và SLO phải được business chấp thuận, có định nghĩa chính xác numerator/denominator.

### 25.2. Bước 2: vẽ dependency graph

Dùng sơ đồ phần 3 hoặc tự vẽ:

~~~text
Client → Front Door → API → Azure SQL
                           ↓
                          Outbox → Service Bus → Worker → Payment
                           ↓
                          Blob Storage / Key Vault / Identity

CI/CD and IaC → provision / update
Azure Monitor → telemetry and alerts
On-call/DBA/IAM → incident decisions and recovery
~~~

Đánh dấu **critical synchronous dependencies** và những dịch vụ có thể chờ bất đồng bộ. Tìm một SPOF và một common-mode failure có thể ảnh hưởng nhiều zones/regions.

### 25.3. Bước 3: lập FMEA

Chọn ít nhất **5 failure modes**:

1. Một API replica crash.
2. Azure SQL failover/connection reset.
3. Service Bus send timeout hoặc consumer backlog.
4. Key Vault RBAC/config đổi sai.
5. Một zone/region unavailable.

Với mỗi mode, ghi user impact, detection, bounded mitigation, recovery owner, có ảnh hưởng dữ liệu hay không, và test case chứng minh.

### 25.4. Bước 4: inventory Azure chỉ đọc

Nếu có subscription lab:

~~~bash
az account show --query "{name:name,id:id}" -o table

az resource list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,type:type,location:location}" \
  -o table
~~~

Không cần đọc mã nguồn dự án khác hay thay tài nguyên trong lúc thực hiện bài học lý thuyết. Nếu không có Azure, dùng tên tài nguyên giả trong sơ đồ.

### 25.5. Bước 5: xác minh zone/multi-region choices

Điền bảng:

| Thành phần | Zone config | Region/DR config | RTO/RPO risk |
|---|---|---|---|
| Ingress | Global routing đã có health policy? | Secondary origin sẵn? | Routing không đồng bộ với DB promotion |
| API | Nhiều replicas qua zones? | Warm/active region B? | Capacity/cold start |
| Azure SQL | HA/zone supported/active? | Replica/backup/failover group? | Async lag/restore time |
| Service Bus | Tier/HA behavior? | Secondary namespace/data recovery? | Missing in-flight messages |
| Storage | LRS/ZRS/GRS/GZRS? | Last sync/account failover? | Potential data loss |
| Key Vault | Access/identity/region? | Secret/key recovery? | Common-mode access failure |
| Monitoring | Multi-location synthetic? | Alerts vẫn hoạt động khi A outage? | Blind spots |

Nếu một hàng chưa có bằng chứng, ghi **UNKNOWN / TO VALIDATE**, không tự điền “zone redundant” vì resource là managed service.

### 25.6. Bước 6: thiết kế bounded retry

Giả định GET catalog read-only, thử:

~~~text
First attempt times out after 500 ms.
Retry once after random backoff.
If second attempt fails or deadline nearly exhausted:
  return a controlled degraded response
  and emit a metric/trace.
~~~

Đánh giá **retry storm** khi 1.000 clients cùng retry. Với POST payment, giải thích vì sao cần stable idempotency key/ledger reconciliation.

### 25.7. Bước 7: game day không phá hoại

Trong staging:

1. Xác nhận owner, approval, scope và abort conditions.
2. Bật synthetic traffic có dữ liệu giả.
3. Ghi baseline SLI, p95, queue lag, DB connection counts.
4. Simulate một dependency trả HTTP 503/latency bằng **test double**, không thay production DNS/network.
5. Xem timeout, circuit breaker, retry budget, API response.
6. Stop injection; xác minh service hồi phục, không backlog/duplicate transactions.
7. Ghi actual duration và corrective actions.

Nếu muốn zone/DB failover thật, cần **lab resources riêng** và service-specific procedure đã được DBA/SRE phê duyệt. Không chạy trên production chỉ để “đạt bài”.

### 25.8. Bước 8: restore rehearsal

Thay vì xóa DB để test:

~~~text
1. Identify authorized isolated database and backup point.
2. Request restore to a NEW test database/server.
3. Measure restore duration.
4. Validate schema, row counts, key business invariants.
5. Check permissions, application connectivity, TLS, DNS.
6. Check consistency with synthetic outbox/payment records.
7. Record RPO/RTO evidence.
8. Clean up only lab restore resources after approval.
~~~

**Restore phải tạo môi trường không phá dữ liệu nguồn**. Nếu người học không có quyền/backup, mô phỏng runbook và ghi blocker, không tự xin Owner hoặc thay môi trường thật.

### 25.9. Bước 9: tính error budget và capacity

Giả sử SLO 99,9% cho 30 ngày và thời gian downtime đo 17 phút:

\[
\mathrm{ErrorBudgetRemaining}
=43{,}2-17=26{,}2\text{ phút}
\]

Chỉ hợp lệ cho **time-based availability 30 ngày** trong ví dụ. Với request-based SLO, phải tính số yêu cầu lỗi trên tổng yêu cầu, và các khoảng traffic cao có trọng số lớn hơn.

Nếu có 24 API replicas, mỗi replica pool tối đa 15 DB connections:

\[
24\times15=360\text{ potential DB connections}.
\]

Đề xuất pool/replica/capacity plan không vượt connection budget và vẫn có headroom cho failover/reconnect storm.

### 25.10. Bước 10: tiêu chí đạt

| Kết quả | Bằng chứng |
|---|---|
| Business SLO/RTO/RPO | Có owner và measurement definitions |
| Dependency map | Ghi cả identity/network/data/people |
| FMEA | Ít nhất 5 lỗi, mitigation và owner |
| Zone/region strategy | Phân biệt zone vs geo và supported tiers |
| Retry/idempotency | Bounded attempts, no double-charge |
| Data recovery | PITR/backup vs geo replica, restore plan |
| Drill | Safe hypothesis/baseline/injection/abort/results |
| Observability | User SLI + dependency metrics + synthetic checks |
| FinOps | Cost/redundancy tradeoff và budget owner |
| Operational | Incident runbook, failback và corrective actions |

## 26. Bài tập tổng hợp và đáp án định hướng

### 26.1. Câu hỏi kiểm tra

1. Reliability khác availability, durability và recoverability như thế nào?
2. Nêu năm nguyên tắc thiết kế Reliability và ví dụ cho từng nguyên tắc.
3. Tại sao có nhiều API replicas vẫn có single point of failure?
4. Phân biệt Service Level Indicator, Objective và Agreement.
5. Một SLO 99,9% trong 30 ngày có budget time-based bao lâu?
6. Vì sao request-based SLI không luôn đổi được thành phút downtime?
7. RTO khác RPO như thế nào? Cho ví dụ mỗi cái tốt nhưng cái kia kém.
8. Business Impact Analysis cần những câu hỏi gì?
9. FMEA giúp gì cho thiết kế, có thay được game day không?
10. Phân biệt lỗi process, Availability Zone, region và control plane.
11. Một Key Vault/RBAC chung cho ba zones là failure mode gì?
12. Zonal resource khác zone-redundant resource như thế nào?
13. Tại sao N+1 capacity cần xét khi mất một zone?
14. Active-passive khác active-active? Có cần two-writer database không?
15. Paired Azure regions có tự bảo đảm failover toàn bộ ứng dụng không?
16. Tại sao routing Front Door và SQL failover phải được phối hợp?
17. Traffic Manager DNS failover bị ảnh hưởng bởi yếu tố nào?
18. Liveness probe khác readiness và synthetic user-flow probe?
19. Với AKS, PodDisruptionBudget ngăn được mọi zone outage không?
20. Chọn App Service zone-redundant plan đã bảo đảm database HA chưa?
21. Azure SQL PITR khác failover group/geo replica thế nào?
22. PostgreSQL Flexible Server read replica có tự writable khi source down không?
23. Phân biệt LRS, ZRS, GRS/GZRS và các biến thể read access.
24. Vì sao geo replicated data vẫn có thể mất bản ghi được ghi gần thời điểm sự cố?
25. Cosmos DB multi-write cần conflict/consistency policy nào?
26. Phân biệt Service Bus metadata DR và message data replication.
27. Vì sao queue cần idempotent consumer và outbox?
28. Tại sao Cache Redis không nên là nguồn đơn hàng duy nhất?
29. Bounded retry, exponential backoff/jitter, circuit breaker và bulkhead khác nhau?
30. Khi nào fail open/fail closed là an toàn?
31. Tại sao HTTP 200 không đủ chứng minh dữ liệu đơn hàng đúng?
32. Tại sao timeout sau DB commit vẫn có thể dẫn đến duplicate orders?
33. Nếu 30 replicas × 30 connections, connection budget là bao nhiêu?
34. Khi mất Entra/Key Vault, cache token mãi có rủi ro gì?
35. Vì sao Private Endpoint của region A không tự bảo đảm runtime region B kết nối được DB?
36. Tại sao IaC có thể tạo common-mode failure ở multi-region?
37. SLI/SLO dashboard cần có gì ngoài CPU?
38. Làm sao phân biệt Azure Service Health, Resource Health và app health?
39. Một runbook regional failover tối thiểu gồm những bước nào?
40. Vì sao cần failback runbook riêng sau khi region cũ hồi phục?
41. Tại sao PITR restore không tự đảo ngược payment bên ngoài?
42. Fault injection cần hypothesis/abort/owner như thế nào?
43. Làm sao chứng minh measured RTO/RPO đã đạt?
44. Khi nào multi-region standby là không đáng chi phí?
45. Thiết kế một kiến trúc checkout an toàn trước lỗi region mà không double-charge.

### 26.2. Đáp án mẫu

**Câu 2:** Business requirements, resilience, recovery, operations và simplicity. Ví dụ: checkout SLO 99,9%; zone replicas+backpressure; PITR/DR drill; Azure Monitor/on-call/runbook; tách email khỏi đường đồng bộ checkout.

**Câu 5:** `30 × 24 × 60 × 0,001 = 43,2 phút` error budget cho time-based availability 30 ngày.

**Câu 7:** RTO là thời gian khôi phục service; RPO là độ cũ/mất mát dữ liệu chấp nhận được. DB restore về 1 phút trước sự cố nhưng mất 6 giờ khởi động ứng dụng có RPO gần 1 phút và RTO 6 giờ.

**Câu 12:** Zonal resource nằm tại một zone được chọn; zone-redundant service được thiết kế sao chép/khả dụng giữa zones khi SKU/region hỗ trợ. Zonal một zone vẫn có zone SPOF.

**Câu 15:** Không. Paired regions không tự replicate app, DB, Key Vault hoặc Private DNS. Phải thiết kế app/data/routing/failover/DR riêng.

**Câu 21:** PITR phục hồi dữ liệu từ backup/logs đến một điểm trước lỗi và thường phải restore/cutover. Failover group/geo replica giải quyết regional availability/failover theo feature và có thể có replication lag. Cả hai đều cần app verification.

**Câu 24:** Geo replication bất đồng bộ chưa chuyển xong writes gần đây sang secondary; failover có thể mất dữ liệu vượt RPO nếu không theo dõi lag/last sync.

**Câu 26:** Một số cơ chế Service Bus geo-DR tập trung vào **namespace metadata**, không replicate message payload. Cơ chế geo-replication khác có phạm vi hỗ trợ riêng. Phải kiểm tra tier/feature và dùng outbox/replay.

**Câu 29:** Timeout chặn chờ vô hạn; retry thử lại transient lỗi với budget; jitter tránh request storm; circuit breaker fail-fast khi dependency hỏng; bulkhead tách capacity để lỗi không lan.

**Câu 32:** DB có thể đã commit nhưng HTTP response mất; client retry tạo bản ghi mới nếu không dùng idempotency key/unique constraint.

**Câu 33:** `30 × 30 = 900 potential connections`, cần đối chiếu DB tier/limit và reconnect headroom.

**Câu 41:** Payment external đã charge không bị undo khi SQL DB được restore về timestamp trước đó. Phải reconcile với payment provider ledger, tránh double-charge.

**Câu 43:** Ghi UTC timestamps của failure/detection/traffic & data restore, kiểm tra last recoverable consistent transaction và chạy business correctness checks. RTO đo đến lúc user SLI hồi phục, RPO đo theo dữ liệu, không chỉ status backup.

### 26.3. Rubric đánh giá

| Tiêu chí | Điều kiện đạt |
|---|---|
| Business requirements | Định nghĩa SLI/SLO/error budget/RTO/RPO có owner |
| Fault model | Phân biệt process/zone/region/data/config/common-mode |
| Architecture | Redundancy và simplicity đúng theo mục tiêu |
| Azure choices | Zone/geo features theo SKU/region, không phỏng đoán |
| Data correctness | Idempotency, outbox, backup/geo/PITR consistency |
| Resilience code | Timeout/retry/circuit/bulkhead/degraded mode |
| Operations | Monitoring, alert, incident command, failback |
| Testing | Restore/game day RTO/RPO evidence có safety |
| FinOps | Cost-risk tradeoff và không cắt recovery critical |

## 27. Checklist triển khai Reliability trước production

### 27.1. Business requirements

- [ ] Các **critical user flows** được xác định theo doanh thu/data/compliance.
- [ ] SLI có numerator, denominator, latency definition, phạm vi và measurement window.
- [ ] SLO có business owner, error budget/burn-rate policy.
- [ ] RTO/RPO phù hợp từng flow và trạng thái dữ liệu, không chỉ resource.
- [ ] SLA Azure services được đọc theo **SKU/configuration**, không hiểu là SLA end-to-end.
- [ ] Chức năng phụ có degraded mode hợp pháp, không làm thất bại checkout.

### 27.2. Failure mode và kiến trúc

- [ ] Dependency map gồm cả identity, DNS, network, CI/CD, external services và con người.
- [ ] FMEA có severity/detection/recovery owner, common-mode failure.
- [ ] Không có single-instance/single-zone SPOF trái mục tiêu đã duyệt.
- [ ] Zone redundancy được xác nhận theo region/SKU/instance count.
- [ ] Multi-region topology/quotas/capacity được phê duyệt nếu region RTO cần.
- [ ] Front Door/Traffic Manager routing có health policy đúng và test.
- [ ] Không chuyển write traffic sang secondary khi chưa có authoritative writer.
- [ ] Staging/prod, DR region, cloud dependencies không dùng chung secrets hoặc control scope vô hạn.

### 27.3. State và data integrity

- [ ] Azure SQL/PostgreSQL HA/backup/PITR/geo features được xác minh và test.
- [ ] Azure Storage replication model, last sync, backup/versioning được review.
- [ ] Cosmos DB consistency/conflict policy phù hợp data invariants.
- [ ] Service Bus/Event Hubs recovery scope **message data vs metadata** được hiểu đúng.
- [ ] Outbox/idempotency/duplicate handling bảo vệ order/payment flows.
- [ ] Redis/cache không là authoritative durable store nếu business không cho phép.
- [ ] Keys/secrets/certificates/roles của secondary region có thể hoạt động.
- [ ] Backup protection/retention/immutable copies và test restore có bằng chứng.
- [ ] Database/schema rollout và rollback tương thích với multi-version apps.

### 27.4. Runtime resilience

- [ ] Multiple instances/replicas và headroom chịu mất zone/host.
- [ ] Liveness, readiness, startup, synthetic probes có mục đích riêng.
- [ ] Timeout/connect/query deadlines được thống nhất với request SLO.
- [ ] Retry transient errors có giới hạn, jitter và respect `Retry-After` khi phù hợp.
- [ ] Circuit breaker/bulkhead/admission control được test với dependency degraded.
- [ ] Autoscaling không làm SQL/Service Bus/Key Vault cạn capacity.
- [ ] Graceful shutdown, draining, in-flight request handling rõ.
- [ ] API/pipeline trả trạng thái pending/uncertain trung thực, không báo thành công giả.

### 27.5. Security và network

- [ ] Least privilege cho deployment/runtime/migration/DR identities, có break-glass.
- [ ] DR region có private networking, DNS, TLS, route và firewall rules hợp lệ.
- [ ] Secrets và tokens không nằm trong IaC source/JAR/image/logs.
- [ ] Key Vault và encryption key recovery được phê duyệt, data residency hợp lệ.
- [ ] Resource locks/backup access phù hợp không cản restore được ủy quyền.
- [ ] Activity Log/diagnostic settings lưu cấu hình thay đổi và audit theo policy.

### 27.6. Vận hành và monitoring

- [ ] User SLI/synthetic checks đặt ở nhiều locations, có alert burn-rate.
- [ ] Database replication lag/connection failures/CPU/IO/locks, queue age/DLQ được theo dõi.
- [ ] Đã có on-call/incident commander, escalation, communication templates.
- [ ] Runbooks có **exact resource IDs, approvals, safe abort, rollback** và owner.
- [ ] DR recovery path được diễn tập với data synthetic/isolated restore.
- [ ] RTO/RPO đo cả detection, failover, reroute và business verification.
- [ ] Có failback plan, tránh split-brain và divergence.
- [ ] CI/CD IaC/DB migrations qua tests/canary và bảo vệ blast radius.
- [ ] Postmortem có corrective actions và được xác minh lại bằng drill.

### 27.7. Cost và governance

- [ ] Replicas/regions/backups/monitoring costs được ước lượng theo region/tier.
- [ ] DR standby có owner và lịch review cost-risk.
- [ ] Budget alerts được cấu hình, không tự xóa production để giảm phí.
- [ ] Backup/geo retention tuân thủ compliance và phục hồi business state.
- [ ] Kiến trúc không phức tạp vượt năng lực vận hành của team.
- [ ] ADR/Well-Architected review được cập nhật khi business/SLO thay đổi.

## 28. Dọn dẹp lab và thao tác an toàn

**Reliability drills thường có blast radius lớn**. Một lệnh failover hay delete nhầm trên production không phải là lỗi lab nhỏ: có thể mất dữ liệu, gây split-brain, ngừng serving và kích hoạt compliance incident.

### 28.1. Những thao tác tuyệt đối không tự thực hiện

- **Không** tự failover Azure SQL/PostgreSQL/Storage production để “thử RTO”.
- **Không** tự drop database/table, xóa outbox hoặc queue messages thật.
- **Không** tắt toàn bộ Key Vault/Entra RBAC/network/DNS để mô phỏng outage.
- **Không** tắt từng production zone bằng cách xóa NSG/VMSS/AKS node pools tùy tiện.
- **Không** thực hiện `terraform destroy`/`az group delete` trên resource group shared.
- **Không** tạo payment thật, gửi email/SMS thật hoặc charge thẻ thật trong synthetic test.
- **Không** cấp Owner toàn subscription hay xóa log/backup retention để chữa lỗi quyền.
- **Không** đổi lưu lượng production sang DR region thiếu data authority/approval.

### 28.2. Quy trình cleanup an toàn

1. Xác nhận đúng **subscription, resource group, resource ID, environment và owner**.
2. Xác định resource nào thuộc lab riêng, resource nào shared/production.
3. Lưu metric/drill/RTO/RPO evidence đã được phép và tài liệu cần retention.
4. Chờ synthetic events/queues/outbox drain và data reconciliation.
5. Thu hồi lab-only principals/network exceptions/secrets theo IAM approval.
6. Chỉ xóa **staging/restore test resources** khi không còn dùng và có backup/retention phù hợp.
7. Không xóa previous app revision/image khi còn trong rollback window.
8. Kiểm tra Front Door/Traffic Manager routes, DB primary/replica topology sau drill.
9. Xác minh DR standby posture trở lại trạng thái sẵn sàng.
10. Review Cost Management để không còn lab resources mồ côi.
11. Ghi post-lab changes, owners và tình trạng bảo mật/availability.

### 28.3. Lệnh delete/failover minh họa đều nguy hiểm

~~~bash
# DANGER — COMMENTED EXAMPLES. DO NOT EXECUTE AS A LAB STEP.

# Deleting an entire resource group may delete production dependencies.
# az group delete --name "<some-resource-group>" --yes

# Storage account failover changes account replication/active region state.
# az storage account failover --name "<some-storage-account>" ...

# Database promotion/failover is a production change, not an observation.
# <database-specific failover command omitted intentionally>
~~~

**Muốn chứng minh restore được**, dùng **isolated database restore target**. Muốn chứng minh timeout/circuit breaker, dùng **mock dependency hoặc lab network fault**. Muốn chứng minh traffic failover, dùng **staging endpoints/data** và pre-agreed abort conditions.

### 28.4. Bàn giao sau bài lab

| Hạng mục | Evidence cần có |
|---|---|
| Target scope | Subscription/RG/resource IDs đúng |
| Business SLO | Definition và owner |
| Drill | Hypothesis, timestamps, expected vs actual |
| RTO/RPO | Được đo, có reconciliation plan nếu fail |
| Data | Synthetic records không mất/lặp ngoài dự kiến |
| Runtime | App/queues/DB back to expected healthy topology |
| IAM/network | Không còn temporary broad permissions |
| Backups | Restore points và retention theo policy |
| Monitoring | Alerts/metrics/diagnostic settings hoạt động |
| Costs | Lab-only resources được kiểm kê |
| Actions | Findings/corrective actions có người chịu trách nhiệm |

## 29. Tài liệu tham khảo và tổng kết

### 29.1. Tài liệu nên đọc đúng thời điểm triển khai

- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — các trụ cột, design methodology và workload review.
- [Reliability pillar](https://learn.microsoft.com/azure/well-architected/reliability/) — hướng dẫn Reliability về yêu cầu, chịu lỗi, khôi phục và vận hành.
- [Azure Architecture Center](https://learn.microsoft.com/azure/architecture/) — reference architectures, resilient design patterns.
- [Azure Availability Zones](https://learn.microsoft.com/azure/reliability/availability-zones-overview) — fault domains, zone support và thiết kế.
- [Azure regions and geographies](https://learn.microsoft.com/azure/reliability/regions-overview) — vùng, pairs và lưu ý về lựa chọn region.
- [Azure SQL Database reliability](https://learn.microsoft.com/azure/azure-sql/database/high-availability-sla) — availability theo service tier và các giới hạn.
- [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR, retention và restore.
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — HA, backups và geo options.
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/GZRS và data durability.
- [Azure Cosmos DB high availability](https://learn.microsoft.com/azure/cosmos-db/high-availability) — multi-region/consistency capabilities.
- [Azure Service Bus resilience and disaster recovery](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-geo-dr) — kiểm tra metadata DR/geo capabilities.
- [Azure Front Door](https://learn.microsoft.com/azure/frontdoor/) — global routing, health probes và WAF.
- [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/) — platform metrics, logs, alerts và Application Insights.
- [Azure Service Health](https://learn.microsoft.com/azure/service-health/overview) — incidents/service advisories.
- [Azure Chaos Studio](https://learn.microsoft.com/azure/chaos-studio/) — controlled failure experiments khi target hỗ trợ.
- [Azure Backup](https://learn.microsoft.com/azure/backup/) — backup policies và restore.
- [Azure Site Recovery](https://learn.microsoft.com/azure/site-recovery/) — recovery workloads/VMs trong use cases được hỗ trợ.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước lượng chi phí theo region/tier.

**Kiểm tra cập nhật:** Azure service tier, availability zones, regional replication, disaster recovery features, backup retention, failover mechanisms, API names và SLA có thể thay đổi theo service/version/region. Khi triển khai production, xác minh documentation/support matrix và pricing tại thời điểm áp dụng; những số liệu/kiến trúc trong bài là **giả định học tập**, không phải bảo đảm của Microsoft hay tư vấn compliance cho mọi tổ chức.

### 29.2. Mười bốn điều cốt lõi

1. **Reliability không đồng nghĩa uptime đơn lẻ:** phải giữ chức năng và data correctness, chịu lỗi và phục hồi.
2. **Bắt đầu bằng business flows**, không bắt đầu bằng mua ba regions.
3. **SLI/SLO/SLA khác nhau**; error budget chỉ có nghĩa khi định nghĩa measurement rõ.
4. **RTO là thời gian khôi phục chức năng; RPO là giới hạn dữ liệu có thể mất.**
5. **FMEA/common-mode analysis** phải bao gồm network, identity, data, external providers và people.
6. **Availability Zones** giảm một số lỗi trong region khi SKU/region support, không chống region outage.
7. **Multi-region** cần traffic routing, database writer/replication, quotas, identity, secrets và DR runbook.
8. **HA không thay backup; geo replica không thay PITR** khi data bị xóa/corrupt.
9. **Azure SQL/PostgreSQL/Storage/Cosmos/Service Bus có semantics khôi phục khác nhau**, không suy từ tên tính năng.
10. **Retry phải bounded và idempotent**, phối hợp deadline, jitter, circuit breaker và bulkhead.
11. **Outbox/queue và reconciliation** cần thiết khi ứng dụng có DB transaction + broker/payment provider.
12. **Monitoring theo user SLI và business correctness**, không chỉ CPU, health process hoặc Azure Activity Log.
13. **Recovery có giá trị khi được diễn tập**: đo end-to-end RTO/RPO, kiểm tra data và có failback.
14. **Giữ kiến trúc đủ đơn giản và đúng chi phí**, có owner, runbook, approvals và corrective actions.

### 29.3. Kết luận

Áp dụng **trụ cột độ tin cậy của Azure Well-Architected Framework** không phải bật một tùy chọn HA rồi xem nhiệm vụ hoàn tất. Một workload đáng tin cậy cần **mục tiêu nghiệp vụ đo được, phân tích lỗi và phụ thuộc chung, redundancy phù hợp từ instance đến zone/region, dữ liệu có khả năng khôi phục đúng, code biết chịu lỗi, người vận hành có observability và runbook, diễn tập chứng minh RTO/RPO, cùng quyết định chi phí và bảo mật được đánh giá liên tục**. Khi những yếu tố này có bằng chứng và owner rõ ràng, độ tin cậy mới là **năng lực vận hành có thể kiểm chứng**, không chỉ là lời hứa trong sơ đồ kiến trúc.
