# Rightsizing, lịch bật tắt và tự động thu hồi tài nguyên

## 1. Vì sao cần quản lý vòng đời và kích thước tài nguyên?

Cloud cho phép tạo compute, database, disk, network, cache và nhiều dịch vụ theo nhu cầu. Sự linh hoạt này cũng tạo ra lãng phí: tài nguyên được cấp lớn hơn workload cần, tiếp tục chạy ngoài giờ sử dụng, hoặc bị bỏ lại sau thử nghiệm mà không còn owner. Resource nhàn rỗi vẫn có thể phát sinh chi phí compute, storage, IP, backup, license, data transfer và observability.

**Rightsizing** là điều chỉnh cấu hình tài nguyên sao cho phù hợp với workload và yêu cầu chất lượng dịch vụ. **Scheduling** là lập lịch bật, tắt, scale hoặc chuyển workload theo thời gian sử dụng đã biết. **Auto-reclamation** là quy trình tự động phát hiện và thu hồi tài nguyên hết hạn hoặc không còn cần thiết theo chính sách.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc được thiết kế từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Tối ưu chi phí không chỉ là giảm kích thước máy. Nó phải bảo toàn SLO, bảo vệ dữ liệu, duy trì khả năng phục hồi và hạn chế tác động môi trường từ tài nguyên không cần thiết.

Sau bài này, bạn có thể phân tích utilization, saturation, latency và demand trước khi rightsizing; chọn compute/storage/database size theo workload; thiết kế lịch bật/tắt theo environment, timezone, ngày nghỉ và ngoại lệ; xác định resource nào có thể tắt và state nào cần giữ; áp dụng tag, owner, TTL, budget và auto-reclamation; phát hiện orphan/idle resources; tích hợp cleanup với IaC, CI/CD, approval, backup và audit; đánh giá cost, reliability, security và sustainability theo Well-Architected.

## 2. Phân biệt ba biện pháp tối ưu

| Biện pháp | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Rightsizing** | Resource có đang quá lớn/quá nhỏ so với workload không? | VM 16 vCPU thường chỉ dùng 10% CPU và ít RAM |
| **Scheduling** | Resource cần hoạt động vào thời điểm nào? | Dev environment chỉ cần chạy trong giờ làm việc |
| **Auto-reclamation** | Resource nào đã hết mục đích sử dụng và có thể thu hồi? | Preview environment của PR đã đóng từ ba ngày trước |

Ba biện pháp bổ sung nhau. Rightsizing giảm chi phí khi workload chạy; scheduling giảm thời gian chạy không cần thiết; reclamation dọn resource không còn owner hoặc purpose. Chúng phải dựa trên inventory, telemetry, lifecycle metadata và policy rõ ràng.

## 3. Bắt đầu bằng inventory và cost attribution

### 3.1. Biết mình đang có gì

Trước khi giảm size hoặc tắt resource, lập inventory theo provider/account/project/subscription và region; resource type, SKU/size, quantity và lifecycle state; service, environment, owner, cost center và purpose; created time, last modified, last activity và expiry; dependency gồm network, disk, database, key, backup, DNS và workload; data classification, retention và deletion protection; monthly cost, peak usage và utilization window.

Một resource thiếu tag không nhất thiết là vô dụng; nó có thể là foundation hoặc tài nguyên do provider quản lý. Cần điều tra ownership trước khi thu hồi.

### 3.2. Tagging tối thiểu

~~~yaml
service: booking-platform
environment: dev
owner: booking-team
cost_center: product-engineering
purpose: feature-preview
created_by: ci-preview-pipeline
created_at: "2026-11-18T09:00:00Z"
expires_at: "2026-11-19T09:00:00Z"
data_class: synthetic
lifecycle: ephemeral
~~~

Đây là cấu trúc minh họa; dùng tag key theo convention của tổ chức/provider. Không đưa secret, token hoặc PII vào tag. expires_at là tín hiệu lifecycle, không phải lệnh xóa tự động nếu resource có protection hoặc dependency chưa được kiểm tra.

### 3.3. Cost attribution

Gắn cost với service/team/environment để tránh chỉ nhìn hóa đơn tổng. Shared resource như network, cluster, observability hoặc database có thể được phân bổ theo usage, reserved capacity hoặc một quy tắc thống nhất.

Theo dõi cost theo service, environment, account và region; resource family và pricing dimension; giờ hoạt động/không hoạt động; successful request, booking hoặc transaction; idle spend, unattached storage và orphan spend. Shared cost cần phương pháp phân bổ minh bạch để tránh tối ưu sai nơi.

## 4. Rightsizing dựa trên workload và SLO

### 4.1. Không dùng CPU trung bình làm tiêu chí duy nhất

Một instance có CPU trung bình 15% vẫn có thể cần giữ size hiện tại nếu memory gần giới hạn hoặc có memory spike theo batch; p99 tăng mạnh khi CPU vượt ngưỡng; workload cần burst nhanh trước khi autoscaler kịp scale; một thread/core đơn lẻ bị bão hòa dù tổng CPU thấp; disk IOPS, network throughput hoặc connection pool là bottleneck; instance đang giữ cache nóng hoặc state khó chuyển.

Ngược lại, CPU thấp nhiều tháng cũng không đủ chứng minh có thể giảm size nếu chưa xét peak, seasonality, failover và release surge.

### 4.2. Bộ metric cần xem

| Resource | Metric quan trọng | Điều cần lưu ý |
|---|---|---|
| VM/container CPU | Average, p95, peak, throttling, run queue | CPU thấp có thể che single-core saturation |
| Memory | Working set, RSS, cache, swap, OOM | Cần headroom cho spike và runtime behavior |
| Disk | IOPS, throughput, latency, queue depth, free space | Storage nhỏ hơn có thể làm tăng latency |
| Network | Throughput, packet drops, connection count | Instance SKU có giới hạn network khác nhau |
| Database | CPU, memory, connections, IOPS, locks, replication lag | Instance size chỉ là một phần capacity |
| Cache | Memory utilization, eviction, hit rate, hot keys | Giảm RAM có thể gây eviction và origin load |
| Queue/worker | Backlog, oldest age, processing time, concurrency | Scale quá thấp tạo backlog kéo dài |
| Load balancer | Active connections, target health, request rate | Target/connection quotas có thể là bottleneck |

### 4.3. Dùng percentile và cửa sổ đủ dài

Thu thập dữ liệu bao phủ chu kỳ ngày/tuần và giờ cao điểm; batch jobs và báo cáo định kỳ; campaign, seasonal peak hoặc kỳ thanh toán; rolling deployment và autoscaling events; failover hoặc maintenance windows nếu có dữ liệu.

Xem p50/p95/p99, maximum có ngữ cảnh và thời gian vượt ngưỡng. Không giảm size chỉ dựa một ngày cuối tuần có traffic thấp.

### 4.4. Capacity headroom

Giả sử một service cần 3.000 request/giây ở giờ cao điểm. Một instance cỡ hiện tại chịu 300 RPS tại SLO, target utilization 65%:

\[
N = \left\lceil \frac{3000}{300 \times 0.65} \right\rceil = 16
\]

Đây là số instance ước lượng ban đầu. Cần cộng N+1, zone failure, rolling deployment, traffic skew, startup/warm-up time và quota. Rightsizing từng instance nhỏ hơn có thể làm số lượng instance cần tăng; tổng cost không nhất thiết giảm.

### 4.5. Quy trình rightsizing compute

1. Xác định service, owner, SLO và resource profile.
2. Đo utilization, saturation, latency và throughput.
3. Xác định bottleneck: CPU, memory, I/O, network hay dependency.
4. Chọn candidate SKU nhỏ hơn/lớn hơn hoặc compute family khác.
5. Benchmark bằng workload tương đương production.
6. Tính tổng cost: số instance × price + network/storage/license.
7. Deploy canary hoặc một nhóm nhỏ.
8. Theo dõi latency, error, throttling và autoscaling.
9. Mở rộng rollout hoặc rollback.

Không thực hiện hàng loạt trên mọi workload chỉ từ một ngưỡng CPU chung.

## 5. Rightsizing container và autoscaling

### 5.1. CPU/memory requests và limits

Với Kubernetes, cần phân biệt requests và limits:

- Request ảnh hưởng scheduler placement và resource reservation.
- Limit đặt trần runtime; CPU có thể bị throttle khi vượt limit.
- Memory vượt limit thường có thể dẫn tới OOM kill.

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "1500m"
    memory: "1536Mi"
~~~

Giá trị chỉ là ví dụ. Set request quá thấp có thể overcommit node và gây contention; set quá cao làm cluster không xếp đủ pod và tạo lãng phí. Limit quá thấp gây throttling/OOM; không có limit cũng có thể khiến một container ảnh hưởng workload khác tùy chính sách cluster.

### 5.2. Dùng VPA/HPA và recommendation

- HPA có thể scale replica theo CPU, memory hoặc custom/external metric.
- VPA có thể đề xuất hoặc điều chỉnh requests/limits tùy mode và trạng thái workload.
- Cluster autoscaler/node autoscaler bổ sung node khi pod không schedule được.
- Rightsizing recommendation của provider thường dựa history; cần xác minh peak và business event.

HPA không tự giải quyết node quota, IP exhaustion hoặc database bottleneck. VPA thay đổi pod resource có thể gây restart/eviction tùy mode; kiểm tra tác động và PodDisruptionBudget.

### 5.3. Autoscaling không thay thế baseline planning

Giữ min replicas đủ cho traffic nền và minimum availability; warm cache/JIT và startup latency; một AZ/replica failure theo mục tiêu; rolling update; background work critical.

Nếu scale từ zero mất vài phút mà user cần phản hồi dưới một giây, scale-to-zero không phù hợp cho path đó.

## 6. Rightsizing database, storage và network

### 6.1. Database

Xem CPU, memory và buffer/cache hit; connection pool và query concurrency; IOPS, throughput, storage latency; slow query, lock wait, vacuum/compaction; replication lag và backup window; growth rate, index size và free storage.

Giảm database tier có thể làm latency tăng, connection queue dài và backup/replication không theo kịp. Thử trên staging bằng dataset và write mix tương đương; kiểm tra cả failover và restore.

### 6.2. Storage

Phân biệt storage capacity với performance tier. Disk còn nhiều dung lượng nhưng IOPS quá thấp vẫn có thể là bottleneck. Ngược lại, volume lớn nhưng không có dữ liệu/owner có thể là chi phí lãng phí.

Cơ hội gồm resize/retire volume không attach sau khi xác minh; chuyển dữ liệu lạnh sang tier phù hợp; lifecycle cho snapshot và object versions theo retention; dọn multipart uploads và temporary files; compression/deduplication khi semantics cho phép.

Không xóa snapshot, backup hoặc object chỉ dựa trên last access nếu policy retention/legal hold yêu cầu giữ.

### 6.3. Network và managed service

Kiểm tra NAT gateway, load balancer, private endpoint, cross-zone traffic, reserved public IP và data transfer. Một NAT hoặc load balancer có cost theo giờ và theo bytes; chỉ tắt khi chắc chắn không còn dependency.

Với managed service, giảm tier có thể tác động quota, feature, failover hoặc SLA. So sánh cả tính năng và support tier thay vì chỉ so giá.

## 7. Lịch bật/tắt theo môi trường và workload

Scheduling phù hợp workload có thời gian sử dụng dự đoán được. Nó giảm chi phí compute/resource theo giờ khi không cần chạy.

### 7.1. Environment phù hợp

| Environment/workload | Scheduling phù hợp? | Điều kiện |
|---|---|---|
| Developer sandbox | Rất phù hợp | Có owner, thông báo trước và state được lưu |
| PR preview | Phù hợp | TTL, synthetic data, cleanup khi PR đóng |
| Integration test | Phù hợp | Có startup orchestration và test window |
| Staging | Có điều kiện | Không làm gián đoạn release, demo hoặc test ngoài giờ |
| Training/demo | Phù hợp | Có lịch session và fallback owner |
| Production API | Thường không tắt theo lịch đơn giản | Phải giữ SLO; dùng autoscaling/scale-to-zero chỉ khi kiến trúc hỗ trợ |
| Production batch worker | Có thể schedule | Queue backlog, deadline và replay được kiểm soát |
| DR standby | Không tắt tùy tiện | Cần đáp ứng RTO/RPO và quota/capacity |

### 7.2. Lịch theo timezone

Một lịch cần chỉ rõ timezone (ví dụ Asia/Ho_Chi_Minh hoặc UTC); ngày làm việc, cuối tuần và ngày nghỉ; mốc start/stop và thời gian warm-up/drain; ngày lễ hoặc campaign ngoại lệ; owner có quyền override; điều kiện không được stop như active deployment hoặc critical test.

Lưu timestamp tuyệt đối có timezone, tránh diễn giải giờ local không rõ khi daylight saving hoặc người vận hành ở nhiều khu vực.

### 7.3. Ví dụ lịch dev

~~~yaml
environment: dev
timezone: Asia/Ho_Chi_Minh
schedule:
  weekdays:
    start: "08:00"
    stop: "20:00"
  weekends:
    mode: stopped
exceptions:
  - date: "2026-11-20"
    mode: running
    reason: "Release rehearsal"
    owner: "booking-team"
resource_policy:
  keep_database_storage: true
  stop_compute: true
  ttl_days: 14
~~~

Đây là policy minh họa. Scheduler thực tế phải xử lý holiday calendar, exception expiry và trạng thái deployment; database storage được giữ không có nghĩa database instance có thể stop trong mọi engine hoặc tier.

### 7.4. Start sequence và stop sequence

Khi bật:

1. Xác minh quota và dependency.
2. Bật network/private endpoint hoặc managed dependency nếu có lifecycle riêng.
3. Khởi động database/cache cần thiết.
4. Khởi động compute/worker.
5. Warm-up, health check và synthetic test.
6. Mở ingress hoặc thông báo environment ready.

Khi tắt:

1. Ngừng nhận job/request mới.
2. Drain connection và xử lý/đẩy lại job còn pending.
3. Chờ deployment/test hoàn tất hoặc chuyển state sang safe checkpoint.
4. Flush dữ liệu cần giữ, backup khi policy yêu cầu.
5. Stop compute/worker.
6. Stop managed service có hỗ trợ và an toàn.
7. Xác minh ingress, schedule và trạng thái.

Không tắt database trước khi worker/application drain xong; thứ tự sai có thể làm hỏng transaction hoặc tạo backlog.

## 8. Tự động thu hồi tài nguyên theo TTL

### 8.1. TTL và ownership

Resource ephemeral nên có owner/team; environment/PR/job ID; purpose; created-at và expires-at; data classification; lifecycle class; protected/shared flag; cleanup policy.

TTL là thời hạn kiểm tra lại mục đích và quyền sở hữu, không phải lệnh xóa mù quáng. Khi hết hạn, automation kiểm tra dependency, active usage, protection và policy trước khi xóa.

### 8.2. Vòng đời auto-reclamation

~~~mermaid
flowchart TD
    NEW["Resource created with owner + TTL"] --> TRACK["Inventory / lifecycle registry"]
    TRACK --> WARN["Expiry notification"]
    WARN --> CHECK{"Owner extends or resource active?"}
    CHECK -->|"Yes, approved"| EXTEND["Extend TTL with reason"]
    EXTEND --> TRACK
    CHECK -->|"No"| GUARD{"Protected / shared / data-bearing?"}
    GUARD -->|"Yes"| REVIEW["Manual review / backup / approval"]
    REVIEW -->|"Retain"| TRACK
    REVIEW -->|"Approved delete"| CLEAN["Cleanup workflow"]
    GUARD -->|"No"| CLEAN
    CLEAN --> VERIFY["Verify removal and dependencies"]
    VERIFY --> REPORT["Record result / audit"]
~~~

### 8.3. Expiry notification

Thông báo trước khi hết hạn giúp owner gia hạn có chủ đích. Ví dụ gửi cảnh báo 24 giờ trước expiry, lần nữa 1 giờ trước nếu resource giá trị lớn. Extension cần reason, owner và maximum extension; tránh resource tạm bị gia hạn vô hạn mà không review.

### 8.4. Orphan detection

Orphan có thể gồm VM/node không còn workload; disk/volume không attach; snapshot quá hạn hoặc không còn owner; public IP/load balancer không còn target; NAT/private endpoint/route không còn consumer; bucket/object prefix của PR đã đóng; secret/certificate/service account của workload đã xóa; DNS record trỏ tới endpoint không còn tồn tại; queue/topic/subscription hoặc log group không còn producer/consumer.

Một resource không hoạt động chưa chắc là orphan; backup, standby, reserved IP hoặc DR resource có thể cần tồn tại. Kết hợp inventory, tag, dependency graph, flow logs, IaC state và owner confirmation.

## 9. Quy trình thu hồi an toàn

### 9.1. Phân loại trước khi xóa

| Nhóm resource | Ví dụ | Cách xử lý |
|---|---|---|
| Ephemeral compute | Preview VM, test runner | Có thể xóa sau TTL và drain |
| Temporary storage | Synthetic DB/schema, test object | Backup/retain theo test policy rồi xóa |
| Persistent data | Production DB, object, backup | Không thu hồi bởi generic cleanup |
| Shared foundation | VPC, cluster, KMS, DNS zone | Owner và lifecycle riêng |
| Security identity | Role, key, certificate | Revoke sau khi xác minh consumer/dependency |
| Billing/network attachment | IP, endpoint, NAT, LB | Kiểm tra route/consumer và cost trước khi release |

### 9.2. Dry-run và approval

Cleanup workflow nên tạo deletion plan trước: resource nào được đề xuất xóa; lý do; dependency bị ảnh hưởng; có data, backup, legal hold hoặc protection không; cost saving ước tính; có thể rollback/recreate không.

Với resource có state hoặc data, yêu cầu approval/backup theo policy. Resource giá trị thấp, ephemeral và synthetic có thể dùng auto-approval nếu guardrail được kiểm thử đầy đủ.

### 9.3. Quy trình teardown

1. Xác định resource ID, environment và owner.
2. Đối chiếu lifecycle registry, IaC state và cloud inventory.
3. Kiểm tra last activity, active connection, queue/job và deployment.
4. Kiểm tra data classification, backup, retention, legal hold và deletion protection.
5. Drain workload và đóng ingress.
6. Thu hồi credential/permission theo thứ tự an toàn.
7. Xóa resource theo dependency order.
8. Kiểm tra resource liên quan và orphan còn lại.
9. Xác minh chi phí/usage dừng phát sinh.
10. Ghi audit report, giữ lại resource ngoại lệ cùng owner/reason.

### 9.4. Idempotency và partial failure

Cleanup có thể bị gián đoạn giữa chừng. Chạy lại phải nhận diện resource đã xóa và tiếp tục từ trạng thái hiện tại, không tạo lại tài nguyên hoặc xóa nhầm dependency.

Mỗi bước nên có stable resource ID; operation status và timestamp; retry bounded cho lỗi transient; error classification như not found, permission denied, dependency in use, retention lock, quota/API throttling; manual review khi trạng thái mơ hồ.

Không coi lệnh destroy trả exit code 0 là bằng chứng duy nhất; cần inventory verification sau đó.

## 10. Tích hợp lifecycle với Infrastructure as Code

### 10.1. IaC là nguồn định nghĩa, inventory là quan sát trạng thái

IaC quản lý desired state và dependency. Cloud inventory phản ánh resource thực tế; lifecycle registry biết owner/expiry; cost system biết chi phí; telemetry biết activity. Kết hợp các nguồn này để xác định candidate.

Một resource không có trong IaC state chưa chắc được xóa; có thể là resource provider-managed hoặc shared. Một resource có trong state cũng chưa chắc còn cần thiết; cần owner review và change plan.

### 10.2. Ephemeral environment

~~~text
PR opened
  -> create isolated stack
  -> attach owner, PR ID, TTL and budget tags
  -> deploy immutable application image
  -> run tests
PR closed or TTL expired
  -> verify PR/environment mapping
  -> generate destroy plan
  -> apply scoped cleanup
  -> verify no orphan
  -> record cleanup result
~~~

### 10.3. Tránh destroy nhầm production

- Role cleanup chỉ được quản lý account/project/environment dành cho ephemeral.
- Tách state/backend hoặc workspace và credentials theo environment.
- Từ chối resource thiếu environment tag hoặc tag không hợp lệ.
- Block protected/shared resource theo policy.
- Kiểm tra account ID, region và resource ARN trước destroy.
- Yêu cầu approval cho data-bearing resource.
- Có test negative: preview cleanup không thể truy cập production.

Không dựa duy nhất vào tên resource có chứa chữ dev hoặc test; dùng identity/scope và metadata được xác minh.

## 11. Rightsizing và scheduling cho production

### 11.1. Ưu tiên scale thay vì tắt

Production API thường cần đáp ứng SLO liên tục. Có thể giảm cost bằng autoscaling replica/node theo demand; scale down worker không có backlog; scheduled scale-up trước peak dự báo; scale-to-zero cho function/serverless hoặc worker nếu startup latency và queue semantics chấp nhận; tắt chức năng phụ hoặc batch trong giờ peak để ưu tiên traffic critical.

Không tắt toàn bộ production stack theo lịch nếu không có business downtime window rõ ràng và failover plan.

### 11.2. Worker theo lịch và queue

Một worker batch có thể chỉ chạy ban đêm, nhưng queue vẫn cần retention, retry và DLQ. Trước khi tắt, stop poll/accept message mới; drain message đang xử lý; commit checkpoint/offset đúng semantics; để message chưa xử lý còn trong queue; xác nhận visibility timeout không hết khi worker vẫn chạy.

Khi bật lại, scale theo backlog/oldest age, không chỉ theo lịch cố định.

### 11.3. Rightsizing và N+1

Không giảm từng replica đến mức mất khả năng phục vụ khi một instance/zone fail. Tổng capacity sau tối ưu vẫn phải đáp ứng:

\[
\text{Remaining capacity after failure} \geq
\text{Required critical workload}
\]

Nếu không đủ, cần thêm baseline, reserve hoặc xác định degraded mode được business chấp thuận.

## 12. Hiệu quả chi phí và tác động bền vững

### 12.1. Cost saving có thể đo

\[
\text{Gross saving} =
(\text{Old hourly cost} - \text{New hourly cost})
\times \text{Hours}
\]

Với scheduling:

\[
\text{Scheduled saving} =
\text{Hourly cost}
\times \text{Hours stopped}
\]

Net saving cần trừ chi phí phụ: tăng storage/backup, startup compute, automation, data transfer, reserved commitment không sử dụng và support operation.

### 12.2. Unit economics

Theo dõi cost per successful booking; cost per active tenant; cost per million API requests; cost per GB stored/processed; idle compute spend; unattached storage cost; cleanup coverage và orphan spend.

Cost per unit phải dùng denominator ổn định và business outcome đúng; không giảm chi phí bằng cách làm giảm chất lượng hoặc bỏ qua request thất bại.

### 12.3. Sustainability

Ít tài nguyên nhàn rỗi có thể giảm điện năng và footprint của compute/storage/network, nhưng mức tác động phụ thuộc data center/provider, energy mix, utilization và cách phân bổ. Theo dõi resource utilization, idle hours, storage retention, data transfer và compute efficiency thay vì đưa ra con số carbon không có dữ liệu.

Giảm overprovision và dữ liệu dư thừa thường có lợi cả cost lẫn sustainability. Tuy nhiên, giữ headroom cần thiết cho reliability vẫn là một phần của thiết kế tốt; không ép utilization lên 100% để tối ưu một metric chi phí.

## 13. Quyền, ngoại lệ và guardrail

### 13.1. Resource protected

Những resource thường cần protection gồm production database và storage chứa dữ liệu; backup vault, snapshots theo retention và legal hold; KMS key/certificate authority; shared VPC/VNet, transit gateway, DNS zone; identity provider và logging/audit pipeline; DR standby resource được yêu cầu giữ nóng.

Protection phải có owner, lý do và quy trình gỡ bỏ rõ; không dùng protection vô thời hạn để che resource không được quản lý.

### 13.2. Exception có thời hạn

~~~yaml
resource_id: staging-db-01
exception:
  type: keep-running
  reason: "Performance rehearsal"
  owner: platform-team
  approved_by: release-manager
  starts_at: "2026-11-18T18:00:00+07:00"
  expires_at: "2026-11-19T02:00:00+07:00"
~~~

Exception cần scope cụ thể, thời gian hết hạn, owner và approval. Sau expiry, policy trở lại bình thường trừ khi được gia hạn có lý do.

### 13.3. Least privilege cho automation

Cleanup/scheduler identity chỉ cần đọc inventory, tags và lifecycle metadata; stop/start hoặc delete đúng resource types/scope được phép; không đọc dữ liệu nghiệp vụ nếu không cần; không xóa backup/KMS/shared foundation; ghi audit và cleanup result.

Tách quyền stop khỏi delete; delete resource data-bearing nên có approval mạnh hơn. Không dùng account administrator credential chung cho cron job.

## 14. Dashboard, alert và runbook

### 14.1. Dashboard

| Nhóm | Chỉ số |
|---|---|
| Utilization | CPU/memory/IOPS/network p50/p95/peak |
| SLO | Latency, error, availability sau rightsizing |
| Idle | Giờ compute không hoạt động, instance zero traffic |
| Orphan | Unattached disk/IP/LB/endpoint/resource không owner |
| Lifecycle | Resource theo TTL, expired, extension và cleanup state |
| Scheduling | Start/stop success, skipped, exception và drift |
| Cost | Cost by service/env/owner, idle spend, net saving |
| Automation | Cleanup errors, retries, deletion blocked, orphan age |

### 14.2. Alert

- Resource sắp hết TTL nhưng chưa có owner confirmation.
- Cleanup bị permission denied hoặc dependency in use.
- Resource quá hạn vẫn chạy quá grace period.
- Production resource bị gắn nhầm ephemeral tag.
- Rightsizing làm p95/p99 hoặc error rate vượt SLO.
- Autoscaler không scale được vì quota.
- Schedule stop thất bại hoặc start không sẵn sàng đúng giờ.
- Orphan cost tăng liên tục.

### 14.3. Runbook

Runbook cần hướng dẫn kiểm tra account/region/resource ID và owner; xác định workload/dependency đang sử dụng; kiểm tra data classification, backup và retention; kiểm tra lifecycle state, protection và exception; quyết định stop, resize, detach, snapshot, retain hoặc delete; xác minh SLO sau rightsizing/schedule; xác minh resource, endpoint, credential và billing sau cleanup.

## 15. Bài thực hành: tối ưu môi trường BookingCloud

BookingCloud có:

- 20 VM dev chạy 24/7 nhưng nhóm chỉ làm việc từ 08:00 đến 20:00 các ngày trong tuần.
- Một staging database luôn chạy dù chỉ dùng cho release rehearsal hai lần mỗi tuần.
- Một số VM có CPU p95 dưới 15%, nhưng memory p95 khoảng 82%.
- 30 volume không attach; một phần là snapshot staging, một phần chưa rõ owner.
- Hàng chục preview environment có PR đã đóng nhưng vẫn tồn tại.
- Production API có autoscaling và phải giữ SLO 99,9%.

Hãy thực hiện:

**Bài 1 — Inventory:** phân loại resource theo owner, environment, data class, cost và dependency.

**Bài 2 — Rightsizing:** phân tích CPU/memory/IOPS/latency; xác định VM nào có thể giảm size và VM nào cần giữ hoặc tăng memory.

**Bài 3 — Schedule:** tạo lịch cho dev VM theo Asia/Ho_Chi_Minh; xử lý ngày nghỉ, release rehearsal, active session và warm-up.

**Bài 4 — Database:** thiết kế staging DB start/stop; xác minh engine hỗ trợ, backup/restore, connection drain và startup time.

**Bài 5 — Reclamation:** xây TTL/owner/expiry cho preview environment; tạo quy trình nhắc owner, dry-run, approval và cleanup.

**Bài 6 — Orphan:** phân loại 30 volume unattached; chỉ thu hồi volume có owner/state xác minh và retention cho phép.

**Bài 7 — Production guardrail:** chứng minh scheduler không tắt production API, database, backup hoặc DR standby.

**Bài 8 — Cost/sustainability:** tính gross/net saving, utilization trước/sau, cost per booking và giờ idle giảm.

**Bài 9 — Test:** mô phỏng cleanup partial failure, resource tag sai, expiry extension và SLO degradation sau rightsizing.

### Khung kết quả tự kiểm tra

| Hiện trạng | Cần chứng minh |
|---|---|
| Dev VM chạy 24/7 | Schedule giảm giờ chạy nhưng không cắt mất session/dirty state |
| Staging DB ít dùng | Stop/start an toàn, restore và release rehearsal đạt yêu cầu |
| CPU thấp, memory cao | Rightsize theo resource bottleneck chứ không chỉ CPU |
| Volume không attach | Xác minh owner, snapshot/retention và khả năng restore trước delete |
| Preview PR đã đóng | Cleanup đúng stack, không đụng shared foundation |
| Production autoscaling | Giữ min capacity và N+1/SLO; không schedule shutdown tùy tiện |

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu lifecycle policy, schedule và cleanup? Có runbook/rollback? | Inventory, owner tags, automation logs, cleanup report, review cadence |
| **Security** | Automation có least privilege? Resource/data nào protected? | Scoped identity, approval, audit, secret handling và negative tests |
| **Reliability** | Rightsizing/scheduling có phá SLO, DR hoặc làm mất state? | Load test, N+1 headroom, drain/checkpoint, backup/restore/failover test |
| **Performance Efficiency** | Resource có phù hợp bottleneck và peak demand? | Utilization percentiles, saturation, p95/p99 và benchmark |
| **Cost Optimization** | Idle spend, overprovision và orphan cost có giảm thực? | Cost attribution, net saving, unit economics và utilization trend |
| **Sustainability** | Compute/storage/network dư thừa có được giảm mà vẫn giữ reliability? | Idle hours, resource efficiency, retention, data transfer và energy metrics nếu có |

Quyết định tối ưu cần dựa trên bằng chứng và có thể đảo ngược. Một rightsizing tốt có thể giảm cost nhưng phải chứng minh SLO vẫn đạt; một lịch tắt tốt phải chứng minh state được drain và môi trường sẵn sàng lại đúng giờ; một cleanup tốt phải chứng minh đúng resource đã được thu hồi và dữ liệu cần giữ vẫn còn nguyên.

## 17. Checklist trước khi bật automation

- [ ] Resource inventory có owner, service, environment, purpose và cost attribution.
- [ ] Rightsizing sử dụng utilization/saturation percentiles và workload seasonality.
- [ ] Đã benchmark candidate size và kiểm tra SLO trước rollout.
- [ ] Có headroom cho peak, rolling deploy và failure domain.
- [ ] CPU, memory, disk, network, database và queue được xem xét riêng.
- [ ] Schedule khai báo timezone, weekdays, holidays, warm-up và owner override.
- [ ] Stop sequence drain workload, xử lý job và bảo toàn state.
- [ ] Production/DR/shared/data resource được bảo vệ khỏi generic scheduler.
- [ ] Ephemeral resource có TTL, expiry notification và extension policy.
- [ ] Auto-reclamation có dry-run, dependency check, protection và approval theo risk.
- [ ] Cleanup identity least privilege; account/region/resource scope được xác minh.
- [ ] Partial failure, retry và idempotency đã được thiết kế.
- [ ] Orphan detection kết hợp inventory, IaC, dependency và owner confirmation.
- [ ] Backup, retention, legal hold và encryption key lifecycle được tôn trọng.
- [ ] Post-cleanup verification xác nhận resource, endpoint và cost đã dừng.
- [ ] Dashboard/alert theo dõi SLO, idle spend, orphan age, schedule và cleanup failures.
- [ ] Có rollback, runbook và review ngoại lệ theo thời hạn.

Rightsizing điều chỉnh lượng tài nguyên cần thiết khi workload hoạt động; scheduling điều chỉnh thời gian hoạt động; auto-reclamation kết thúc vòng đời tài nguyên không còn mục đích. Khi ba cơ chế dựa trên inventory, telemetry, owner, TTL và guardrail có thể kiểm chứng, tổ chức giảm được lãng phí mà vẫn bảo toàn SLO, dữ liệu, bảo mật và khả năng phục hồi của kiến trúc cloud.
