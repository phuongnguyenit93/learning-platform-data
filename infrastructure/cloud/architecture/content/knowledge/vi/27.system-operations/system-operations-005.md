# Quản lý hạn ngạch dịch vụ và kế hoạch tăng dung lượng

## 1. Vì sao quota và capacity là hai vấn đề vận hành khác nhau?

Một ứng dụng cloud có thể được thiết kế để scale ngang, nhưng vẫn không thể mở rộng khi một giới hạn bên ngoài chặn việc tạo thêm tài nguyên. Ví dụ, autoscaler muốn thêm VM nhưng subscription đã chạm quota vCPU; Kubernetes muốn tạo pod nhưng node pool hết IP; service cần mở thêm connection nhưng database giới hạn số connection; workload muốn gửi message nhưng broker hoặc account đạt throughput quota.

**Service quota** là giới hạn do cloud provider hoặc dịch vụ đặt ra cho một account, region, resource hay operation. **Capacity** là năng lực thực tế của hệ thống để xử lý workload trong điều kiện đã định: request/giây, concurrent operations, throughput, storage, memory, connection pool và các ràng buộc khác.

Quota có thể cao hơn hoặc thấp hơn capacity an toàn của ứng dụng. Tăng quota không tự động làm hệ thống xử lý được nhiều request hơn; ngược lại, capacity test tốt trong môi trường hiện tại không bảo đảm production có quota đủ để scale.

Trong module **CLOUD_ARCHITECTURE**, quản lý quota và kế hoạch capacity phải nối yêu cầu nghiệp vụ với compute, network, storage, scaling và vận hành. Thiết kế cần trả lời: nhu cầu hiện tại là bao nhiêu, sẽ tăng thế nào, giới hạn nào sẽ chạm trước, cần dự phòng bao nhiêu và nếu một failure domain mất thì còn đủ capacity phục vụ tải quan trọng không?

Sau bài này, bạn có thể:

- Phân biệt service quota, hard limit, soft limit, rate limit và capacity.
- Lập inventory quota và dependency theo account, region, service và resource.
- Dự báo workload từ demand driver và đặc tính traffic.
- Tính capacity, headroom, safety margin và bottleneck theo từng tầng.
- Thiết kế autoscaling, admission control, queueing và graceful degradation.
- Lập kế hoạch tăng quota, chuẩn bị bằng chứng và theo dõi request.
- Kiểm thử peak load, burst, failover và noisy neighbor.
- Đánh giá chi phí, reliability, security và vận hành theo Well-Architected.

## 2. Phân biệt quota, limit và capacity

### 2.1. Các loại giới hạn thường gặp

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service quota | Ngưỡng provider áp cho account/region/resource | Tổng vCPU được phép dùng trong một region |
| Hard limit | Ngưỡng không thể vượt bằng cách tiếp tục gửi request | Số object hoặc connection tối đa của tier |
| Soft limit | Ngưỡng có thể điều chỉnh qua support/request hoặc thay đổi plan | Quota vCPU mặc định của account |
| Rate limit | Số request/operation trong một đơn vị thời gian | API cho phép 1.000 request/phút |
| Concurrency limit | Số operation chạy đồng thời | Tối đa 200 database connections |
| Capacity | Throughput/volume hệ thống thực sự xử lý được theo SLO | 4.000 booking requests/giây ở p95 dưới 300 ms |
| Allocation | Phần capacity/quota đã dành cho một workload hoặc tenant | 30% worker slots dành cho payment |
| Headroom | Capacity còn dư so với nhu cầu dự kiến hoặc tải hiện tại | 25% CPU capacity chưa sử dụng |

Tên gọi và semantics khác nhau giữa provider. Cần tra đúng dịch vụ, account scope, region scope, loại quota và cách quota được tính.

### 2.2. Ví dụ quota không đồng nghĩa throughput

BookingCloud có quota 500 vCPU trong region. Cluster hiện dùng 100 vCPU và có thể scale tới 300 vCPU theo autoscaler. Database hiện chịu được 2.000 transaction/giây trước khi p99 vượt SLO.

Tăng quota từ 500 lên 1.000 vCPU không làm database tự xử lý được 4.000 transaction/giây. Nếu bottleneck là database, thêm application pod chỉ tăng connection và queue, khiến độ trễ tệ hơn.

### 2.3. Quota theo scope

Quota có thể áp dụng ở nhiều scope:

- Organization/organization unit.
- Account, subscription hoặc project.
- Region hoặc availability zone.
- Service hoặc API.
- Resource type, instance family hoặc SKU.
- Per-tenant hoặc per-user limit trong ứng dụng.
- Per-operation, per-minute hoặc concurrent request.

Một resource có thể bị chặn bởi nhiều quota cùng lúc. Ví dụ tạo VM cần quota vCPU, số instance, IP, disk, NIC, regional capacity và permission. Kiểm tra một quota riêng lẻ không chứng minh deploy sẽ thành công.

## 3. Lập quota inventory

Không thể quản lý thứ không được ghi nhận. Tạo inventory cho từng dịch vụ và dependency quan trọng.

### 3.1. Trường dữ liệu cần lưu

| Trường | Mục đích |
|---|---|
| Provider/service | Cloud provider và service liên quan |
| Account/project/subscription | Scope quota |
| Region/zone | Phạm vi địa lý/failure domain |
| Quota name/ID | Định danh đúng giới hạn |
| Current limit | Mức giới hạn hiện tại |
| Current usage | Mức sử dụng hiện tại |
| Peak usage | Mức dùng cao nhất trong cửa sổ quan sát |
| Unit/reset window | vCPU, request/min, GB, connections, tokens... |
| Increase path | Console/API/support request/plan change |
| Lead time | Thời gian cần để quota tăng có hiệu lực |
| Owner | Nhóm chịu trách nhiệm |
| Critical date | Ngày dự kiến vượt ngưỡng |
| Dependency | Resource/workload bị ảnh hưởng nếu chạm limit |

Không lưu con số quota dưới dạng một ghi chú không có timestamp. Provider có thể đổi default quota hoặc cách tính; inventory phải ghi thời điểm xác minh và nguồn.

### 3.2. Quota dependency map

~~~mermaid
flowchart TB
    SCALE["Autoscaler requests more nodes"] --> VM["Compute quota"]
    VM --> CPU["Regional vCPU quota"]
    VM --> IP["Subnet IP availability"]
    VM --> DISK["Disk / volume quota"]
    VM --> NIC["NIC / network quota"]
    CPU --> DEPLOY["Workload capacity"]
    IP --> DEPLOY
    DISK --> DEPLOY
    NIC --> DEPLOY
    DEPLOY --> DB["Database connection / throughput"]
    DEPLOY --> MQ["Broker throughput / partitions"]
    DEPLOY --> LB["Load balancer / target quota"]
~~~

Scale-out có thể cần đồng thời compute, IP, disk, NIC, load balancer target, database connection và queue capacity. Inventory nên ghi quan hệ này để tránh chỉ phát hiện quota ngay lúc deploy.

### 3.3. Cách thu thập quota

- Dùng cloud quota APIs, service quota dashboards hoặc account inventory khi provider hỗ trợ.
- Đối chiếu IaC để biết resource tối đa theo thiết kế.
- Đọc billing/usage và monitoring để biết consumption thực.
- Xác minh thủ công những quota không có API hoặc có semantics đặc thù.
- Gắn owner và ngày review cho quota critical.
- Tạo automated check định kỳ và trước release lớn.

Không giả định giá trị mặc định trong tài liệu là quota thật của account hiện tại. Quota được cấp có thể phụ thuộc lịch sử sử dụng, vùng, tier, contract và approval.

## 4. Demand modeling: nhu cầu đến từ đâu?

Capacity planning bắt đầu bằng cách định lượng nhu cầu nghiệp vụ, sau đó chuyển thành tài nguyên kỹ thuật.

### 4.1. Demand drivers

Với BookingCloud, demand drivers gồm:

- Số khách hàng active và tenant mới.
- Số người dùng đồng thời.
- Request rate theo giờ/ngày/mùa.
- Tỷ lệ đọc/ghi và số bước mỗi workflow.
- Tỷ lệ cache hit, queue fan-out và retry.
- Batch export, reporting và import jobs.
- Kích thước payload, file upload và retention.
- Tăng trưởng dữ liệu mỗi ngày/tháng.
- Marketing campaign, seasonal peak hoặc event.

Không chỉ dùng trung bình ngày. Một workload có peak gấp 8 lần average có thể cần plan hoàn toàn khác.

### 4.2. Phân biệt steady, peak và burst

| Kiểu tải | Đặc điểm | Cách chuẩn bị |
|---|---|---|
| Steady-state | Nhu cầu nền ổn định | Baseline capacity và utilization target |
| Peak | Tăng theo giờ/ngày/mùa có thể dự báo | Pre-scale, reservation/quota headroom |
| Burst | Tăng rất nhanh trong thời gian ngắn | Buffer, admission control, burst capacity |
| Growth trend | Nhu cầu tăng theo tháng/quý | Forecast và capacity roadmap |
| Failure load | Tải dồn khi dependency/zone khác mất | N+1/failover capacity và load shedding |

Burst scaling không tức thời nếu provisioning VM, node hoặc database mất vài phút. Cần dự báo và pre-scale khi có sự kiện đã biết.

### 4.3. Workload profile

Mỗi workload nên có profile:

~~~yaml
workload: booking-api
criticality: tier-1
traffic:
  average_rps: 1200
  peak_rps: 4200
  burst_rps: 6000
  peak_duration_minutes: 20
mix:
  read_percent: 70
  write_percent: 30
latency_objective:
  p95_ms: 300
  p99_ms: 800
availability_target: "99.9%"
growth:
  monthly_percent: 8
  planning_horizon_months: 12
~~~

Đây là dữ liệu minh họa. Profile thực tế cần lấy từ access telemetry, business forecast, load test và các event sắp diễn ra. Không dùng average RPS để suy ra peak nếu không có phân phối thời gian.

## 5. Chuyển demand thành capacity

### 5.1. Throughput và thời gian xử lý

Một ước lượng cơ bản dựa trên Little's Law:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request/operation trung bình đang nằm trong hệ thống.
- \(\lambda\) là throughput trung bình (request/giây).
- \(W\) là thời gian trung bình một request nằm trong hệ thống (giây).

Nếu service xử lý 1.000 request/giây và thời gian trung bình trong hệ thống là 0,2 giây, số request in-flight trung bình xấp xỉ 200.

Đây là quan hệ trung bình trong điều kiện ổn định; không dùng trực tiếp p99 để thay W nếu chưa hiểu phân phối và queueing. Khi utilization tiến gần 100%, latency có thể tăng phi tuyến vì hàng đợi và contention.

### 5.2. Capacity per instance

Nếu một instance đã benchmark chịu được 250 RPS ở SLO mục tiêu, để phục vụ 4.200 RPS với utilization target 65%:

\[
N = \left\lceil \frac{4200}{250 \times 0.65} \right\rceil = 26
\]

Kết quả 26 instance là ước lượng ban đầu, chưa bao gồm N+1, failure zone, rolling deployment, skew, background tasks và quota constraints. Nếu mất một zone, số instance còn lại vẫn cần đủ capacity cho tải được cam kết.

### 5.3. Capacity chain và bottleneck

Một request đi qua nhiều tầng. Throughput end-to-end không vượt bottleneck nhỏ nhất:

~~~text
API gateway capacity       = 8,000 RPS
Booking service capacity   = 6,000 RPS
Inventory service capacity = 4,500 RPS
Database capacity          = 3,000 RPS
Payment provider quota     = 1,500 RPS

End-to-end throughput for payment flow <= 1,500 RPS
~~~

Nếu booking không phải request nào cũng thanh toán ngay, cần tách flow và tỷ lệ gọi provider. Không lấy quota Payment làm giới hạn cho toàn bộ GET catalog; nhưng phải tính tổng số authorize/capture theo business mix.

### 5.4. Utilization target và headroom

Không nên plan ở 95–100% utilization trong điều kiện bình thường. Hệ thống cần headroom để hấp thụ burst, failover, rolling deployment, noisy neighbor và sai số dự báo.

Ví dụ:

| Resource | Capacity usable | Target utilization | Planning headroom |
|---|---:|---:|---:|
| Application CPU | 1.000 vCPU | 65% | 35% |
| Database connections | 800 | 60% | 40% |
| Queue consumer slots | 500 | 70% | 30% |
| Storage throughput | 20.000 IOPS | 70% | 30% |

Các target chỉ mang tính minh họa. Database connection pool có thể cần giới hạn thấp hơn; CPU target phụ thuộc latency sensitivity và scaling speed.

## 6. N+1, zone failure và capacity dự phòng

Capacity plan phải nói rõ hệ thống còn phục vụ mức tải nào khi một failure domain mất.

### 6.1. Ví dụ multi-zone

Giả sử ba zone chia đều 30 instance, mỗi zone 10 instance. Nếu tổng demand là 4.500 RPS và mỗi instance chịu 200 RPS tại SLO mục tiêu, capacity thường trực là 6.000 RPS.

Nếu mất một zone, 20 instance còn lại có capacity 4.000 RPS, thấp hơn demand 4.500 RPS. Thiết kế này không đạt mục tiêu full-traffic N+1. Có thể:

- Chạy thêm baseline instance ở mỗi zone.
- Đặt autoscaling/quota reserve đủ để thay capacity mất.
- Giảm load theo priority khi failover.
- Định nghĩa SLO degraded mode rõ ràng.

### 6.2. Quota reserve cho failover

Quota tăng thêm cần có ở region/zone đích, không chỉ region chính. Nếu DR region chưa từng được scale tới mức production, failover có thể thất bại khi tạo VM/IP/database replica do quota chưa đủ.

Kiểm tra:

- vCPU và instance family.
- IP/subnet address space.
- Load balancer/listener/target.
- Database replica/storage/IOPS.
- NAT gateway, private endpoint và network throughput.
- KMS/API quota và secret access.
- Queue partitions/throughput và worker capacity.

### 6.3. Degraded-mode capacity

Không phải workload nào cũng phải giữ 100% tính năng khi mất một zone. Có thể ưu tiên:

1. Authentication, booking status và thao tác hủy quan trọng.
2. Booking mới với inventory có thể xác nhận an toàn.
3. Payment status/reconciliation.
4. Notification retry và report batch có thể trì hoãn.
5. Recommendation, analytics refresh hoặc chức năng phụ có thể tắt tạm.

Priority phải dựa trên business impact và safety invariant, không chỉ theo chi phí compute.

## 7. Autoscaling và capacity control

Autoscaling điều chỉnh resource theo demand hoặc metric, nhưng không thay thế quota planning.

### 7.1. Các tín hiệu scale

- CPU/memory utilization.
- Request rate và latency.
- Active/in-flight requests.
- Queue depth và oldest message age.
- Worker utilization và processing time.
- Database pool wait, storage IOPS/throughput.
- Custom business metric như booking create backlog.

CPU thấp không có nghĩa service còn capacity nếu đang chờ database hoặc provider. Queue age/latency có thể là tín hiệu scale worker tốt hơn CPU.

### 7.2. Horizontal và vertical scaling

| Kiểu | Mô tả | Giới hạn |
|---|---|---|
| Horizontal scaling | Tăng/giảm số instance/pod/worker | Cần quota, IP, scheduler và khả năng phân phối tải |
| Vertical scaling | Tăng CPU/RAM/IOPS của instance | Có trần SKU, có thể cần restart/downtime, tạo single-node dependency |
| Scheduled scaling | Tăng capacity trước thời điểm dự báo | Cần forecast; có thể lãng phí nếu tải không xuất hiện |
| Predictive scaling | Dùng pattern/history để scale trước | Phụ thuộc chất lượng data và độ ổn định của pattern |

### 7.3. Scale-out có độ trễ

Provisioning node, pull image, warm cache, attach volume, start JVM hoặc establish connection pool cần thời gian. Scale trigger phải chạy trước khi hệ thống chạm saturation.

Một autoscaler quá nhạy có thể dao động liên tục (flapping). Cần hysteresis, stabilization window, cooldown, min/max replicas và scale-down protection cho workload có state.

### 7.4. Autoscaling và quota

Khi autoscaler đạt max replicas hoặc cloud API trả quota exceeded, cần:

- Alert trước ngưỡng dự kiến.
- Ghi nguyên nhân scale failure rõ ràng.
- Không retry provisioning vô hạn.
- Giữ capacity tối thiểu đang khỏe.
- Giảm admission hoặc shed load có kiểm soát.
- Có quota request workflow và escalation owner.

## 8. Admission control, queueing và fairness

Khi demand vượt capacity, tiếp tục nhận mọi request sẽ làm hệ thống quá tải. **Admission control** quyết định request nào được nhận, hoãn hoặc từ chối.

### 8.1. Bounded queue

Queue hấp thụ burst ngắn và làm phẳng tải, nhưng queue vô hạn chỉ biến overload thành latency, memory và storage exhaustion. Cần giới hạn queue depth, message age, retention và consumer concurrency.

### 8.2. Rate limit và concurrency limit

- Rate limit kiểm soát tốc độ request từ tenant/client/operation.
- Concurrency limit kiểm soát số operation đang chạy.
- Bulkhead tách budget giữa các dependency hoặc loại workload.
- Retry budget giới hạn phần tải phát sinh do retry.

Các cơ chế này phối hợp để một request chậm không chiếm hết pool và một tenant không làm nghẽn toàn hệ thống.

### 8.3. Fairness giữa tenant

Với SaaS đa tenant, quota nên có:

- Per-tenant request budget.
- Concurrent job/export limit.
- Storage/egress budget.
- Priority tier hoặc reserved capacity.
- Fair scheduling/weighted queue.
- Alert và quy trình nâng tier.

Không nên để một tenant có thể tiêu thụ toàn bộ shared capacity chỉ vì họ gửi nhiều request hơn.

### 8.4. Graceful degradation

Khi resource gần giới hạn, giảm chức năng không critical, trì hoãn báo cáo, giảm tần suất refresh, trả 429/503 có Retry-After, hoặc phục vụ stale data chỉ khi business cho phép. Không degrade bằng cách bỏ authorization, bỏ validation hoặc xác nhận booking/payment khi chưa có nguồn có thẩm quyền.

## 9. Forecasting và capacity roadmap

### 9.1. Dự báo theo growth

Nếu demand hiện tại là D0 và tăng đều g mỗi tháng, nhu cầu sau t tháng:

\[
D_t = D_0(1+g)^t
\]

Ví dụ D0=4.000 RPS, growth 8%/tháng, sau 12 tháng:

\[
D_{12} = 4000(1.08)^{12} \approx 10.072 \text{ RPS}
\]

Đây chỉ là mô hình tăng trưởng lũy thừa đơn giản. Thực tế cần phân biệt tăng người dùng, mức sử dụng mỗi user, traffic seasonality, feature adoption và thay đổi kiến trúc.

### 9.2. Scenario planning

Ít nhất nên lập ba kịch bản:

| Kịch bản | Giả định | Dùng để |
|---|---|---|
| Base | Growth/traffic theo kế hoạch | Ngân sách và vận hành thông thường |
| High | Adoption hoặc campaign cao hơn dự kiến | Chuẩn bị peak/quota |
| Stress | Surge, provider outage hoặc zone loss | Reliability và degraded-mode plan |

Forecast phải có assumptions và confidence range. Không dùng một con số chính xác giả tạo cho kế hoạch 12 tháng.

### 9.3. Capacity roadmap

Một roadmap có thể gồm:

- Tuần/tháng hiện tại: baseline workload, quota inventory, load test.
- Trước campaign: request quota, pre-scale, warm cache và kiểm tra provider limit.
- Quý tiếp theo: shard database, thêm region hoặc thay đổi storage tier nếu bottleneck dự kiến.
- Trước renewal/major launch: review growth, reserved capacity, cost và DR test.

Gắn milestone với owner, lead time, acceptance criteria và ngày cần hoàn tất.

## 10. Load testing và capacity validation

Capacity không thể suy ra chỉ từ số vCPU hoặc lời quảng cáo của instance type. Cần benchmark workload gần thực tế.

### 10.1. Các loại test

| Loại test | Mục đích |
|---|---|
| Baseline test | Đo latency/throughput khi tải bình thường |
| Load test | Xác minh target peak trong thời gian dự kiến |
| Stress test | Tìm điểm saturation và failure behavior |
| Spike test | Đo khả năng xử lý burst tăng đột ngột |
| Soak test | Tìm leak, degradation và resource accumulation theo thời gian |
| Failover test | Xác minh capacity khi mất zone/region/dependency |
| Quota test | Kiểm tra scale/deploy khi tiến gần giới hạn account/service |

### 10.2. Thiết kế workload test

- Dùng traffic mix giống production: read/write, payload, tenant distribution và cache hit.
- Mô phỏng concurrency và ramp-up/ramp-down, không chỉ fixed RPS.
- Có think time/user behavior nếu mô phỏng session.
- Dùng dataset đủ lớn để tránh kết quả sai do cache nóng hoặc DB nhỏ.
- Kiểm tra dependency thật hoặc emulator có capacity/latency tương đương.
- Tránh chạy load test vào production nếu không có approval, isolation và guardrails.
- Đo p50/p95/p99, error, resource saturation, queue age và chi phí.

### 10.3. Xác định safe capacity

Safe capacity là mức tải cao nhất vẫn giữ SLO với headroom đã định, không phải mức throughput cực đại trước khi process crash.

Ví dụ test:

| Load | p95 latency | Error rate | Kết luận |
|---:|---:|---:|---|
| 2.000 RPS | 180 ms | 0,02% | Đạt |
| 3.000 RPS | 220 ms | 0,03% | Đạt |
| 4.000 RPS | 280 ms | 0,05% | Đạt sát ngưỡng |
| 4.500 RPS | 620 ms | 0,8% | Không đạt SLO |
| 5.000 RPS | 1.400 ms | 4,2% | Saturation |

Với SLO p95 dưới 300 ms và error dưới 0,1%, safe capacity có thể chọn 4.000 RPS hoặc thấp hơn tùy headroom/failure requirement, dù hệ thống từng đạt một số request ở 4.500 RPS.

## 11. Quản lý yêu cầu tăng quota

Quota increase thường cần thời gian review; một số quota tự động tăng, một số yêu cầu support hoặc điều chỉnh plan. Không chờ tới ngày cần deploy mới mở request.

### 11.1. Chuẩn bị bằng chứng

Một request tốt nên có:

- Tên quota, scope account/region/service và current limit.
- Current usage, peak usage và trend.
- Mức mới đề nghị cùng cách tính.
- Workload/business justification.
- Thời điểm cần quota và lead time.
- Architecture/capacity evidence: load test, scale plan, dependency.
- Security/reliability controls để chứng minh mức tăng có quản trị.
- Owner và contact để trao đổi.

### 11.2. Ước lượng requested quota

Không chỉ xin vừa đủ để deploy. Tính:

~~~text
required_limit =
    peak_planned_usage
  + failover_reserve
  + rollout_reserve
  + growth_buffer
~~~

Không cộng các reserve trùng nhau một cách mù quáng. Ví dụ rolling deployment có thể cần surge capacity chỉ trong vài phút; failover reserve có thể dùng cùng resource pool nếu hai scenario không xảy ra đồng thời theo threat model. Nếu phải chịu cả peak traffic trong khi một zone mất và rollout đang diễn ra, cần tính scenario kết hợp.

### 11.3. Theo dõi trạng thái request

Quản lý quota request như một dependency có deadline:

- Proposed: tính xong nhu cầu, chuẩn bị bằng chứng.
- Submitted: provider đã nhận request.
- In review: chờ thông tin/approval.
- Approved: quota tăng, cần xác minh scope và thời gian hiệu lực.
- Rejected/partial: cập nhật capacity plan hoặc escalation.
- Applied: test scale/deploy thành công trong scope cần thiết.

Approval không đồng nghĩa quota đã có hiệu lực ở mọi region/subscription. Sau khi được duyệt, phải query lại quota và thử một deployment/scale test an toàn.

## 12. Capacity và cost optimization

Capacity cao hơn demand làm tăng chi phí nếu resource chạy thường trực; capacity quá thấp gây lỗi, latency và mất doanh thu. Tối ưu cần dựa trên toàn bộ cost-to-serve.

### 12.1. Các nhóm chi phí

- Compute baseline, autoscaling và standby capacity.
- Database CPU, storage, IOPS, connection/throughput tier.
- Network egress, NAT, private endpoint, load balancer.
- Queue/broker partition, throughput và retention.
- Cache memory và replication.
- Observability ingestion/storage/query.
- Backup, snapshot và DR resource.
- License/support tier hoặc provider minimum commitment.

### 12.2. Reserved và on-demand capacity

Reserved capacity/commitment có thể giảm giá cho steady-state; on-demand/flexible capacity phù hợp burst hoặc demand không chắc chắn. Cần cân nhắc:

- Tính linh hoạt khi thay instance family/region.
- Thời hạn commitment và utilization.
- Khả năng scale trong zone/region.
- Chi phí standby DR.
- Chi phí overprovision so với downtime risk.

### 12.3. Cost per business transaction

Thay vì chỉ theo dõi hóa đơn tổng, có thể tính:

\[
\text{Cost per booking} =
\frac{\text{Infrastructure + platform cost in period}}
{\text{Successful bookings in period}}
\]

Metric này giúp thấy hiệu quả thay đổi cache, query, queue hoặc autoscaling. Tuy nhiên, phải phân bổ shared cost có quy tắc và không giảm chi phí bằng cách hy sinh reliability/security.

## 13. Quota và capacity trong kiến trúc đa vùng

### 13.1. Active-active

Nhiều region cùng nhận traffic. Capacity và quota phải đủ cho phân phối tải bình thường, cross-region shift và một region failure. Nếu failover cần chuyển 100% traffic sang region còn lại, region đó phải có quota và resource sẵn sàng hoặc được cấp nhanh đủ tin cậy.

### 13.2. Active-passive

Region DR có thể chạy footprint nhỏ, nhưng phải biết thời gian scale-up, quota, IP, database restore/replication lag, KMS và endpoint dependencies. Không lấy quota của primary làm bằng chứng DR region đủ năng lực.

### 13.3. Shared quota và regional quota

Một số giới hạn áp ở account toàn cục; một số áp theo region. Cần tránh cộng nhầm quota regional với global hoặc giả định một vùng còn quota thì vùng khác cũng còn.

### 13.4. Dependency bên ngoài

Payment provider, email API, SMS gateway, identity provider và SaaS khác có quota riêng. Chúng có thể giới hạn:

- Requests per second hoặc per minute.
- Concurrent API calls.
- Daily transaction/message cap.
- Burst quota.
- Tenant/account-level quota.
- Sandbox và production quota riêng.

Capacity plan end-to-end phải bao gồm provider quota, retry budget, circuit breaker và degraded-mode behavior.

## 14. Quan sát và cảnh báo quota/capacity

### 14.1. Các metric cần có

| Metric | Ý nghĩa |
|---|---|
| quota_limit | Giá trị giới hạn hiện tại |
| quota_used | Consumption hiện tại |
| quota_utilization | Tỷ lệ dùng so với limit |
| peak_utilization | Peak trong cửa sổ |
| quota_exceeded_count | Số lần operation bị từ chối vì quota |
| scale_request_failed | Số lần autoscaler không thêm được resource |
| desired_vs_ready_capacity | Capacity mong muốn và thực tế sẵn sàng |
| saturation/queue_age | Mức nghẽn và thời gian chờ |
| forecast_to_limit_days | Số ngày dự kiến tới khi chạm quota |
| cost_per_transaction | Hiệu quả cost-to-serve |

Không phải provider nào cũng expose quota usage dưới dạng metric thời gian thực. Có thể cần scheduled inventory query và lưu snapshot vào time-series/database nội bộ.

### 14.2. Ngưỡng cảnh báo

Một mẫu policy:

- 60%: theo dõi xu hướng và xác định growth.
- 75%: alert owner, kiểm tra forecast và headroom.
- 85%: mở/quyết định quota increase nếu lead time dài.
- 95%: escalation và capacity mitigation plan.
- 100%/quota exceeded: incident theo mức độ ảnh hưởng.

Ngưỡng phải theo lead time và tốc độ tăng. Nếu quota tăng 5% mỗi ngày và provider cần 3 tuần xử lý, alert ở 85% đã quá muộn.

### 14.3. Forecast to limit

Ước lượng đơn giản:

\[
\text{Days to limit} =
\frac{\text{limit} - \text{current usage}}
{\text{average daily net increase}}
\]

Chỉ dùng khi growth tương đối ổn định. Với burst/seasonality, dùng forecast theo time series và kịch bản. Alert nên xét cả uncertainty range và request lead time.

## 15. Quy trình capacity review và ownership

Một chu trình định kỳ:

1. Thu thập usage, demand, SLO và forecast.
2. Cập nhật quota inventory và dependency map.
3. Xác định bottleneck theo load test và telemetry.
4. Tính capacity cho base/peak/stress/failover.
5. So sánh với quota hiện tại và lead time.
6. Mở quota request hoặc tối ưu bottleneck.
7. Phê duyệt ngân sách/reservation/dedicated tier.
8. Load test và failover test sau thay đổi.
9. Cập nhật runbook, dashboard và forecast.

### 15.1. RACI ví dụ

| Công việc | Application team | Platform/SRE | FinOps | Security |
|---|---|---|---|---|
| Demand forecast nghiệp vụ | R | C | C | I |
| Quota inventory | C | R | C | I |
| Load/capacity test | R | R | I | C |
| Quota request | C | R | C | I |
| Cost/commitment review | C | C | R | I |
| Risk/access review | C | C | I | R |
| Failover capacity | C | R | C | C |

R = Responsible, C = Consulted, I = Informed. Phân công thực tế tùy tổ chức.

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Quota có owner, inventory, alert, request lead time và runbook? | Quota catalog, forecast, support ticket, scale-failure alert |
| **Security** | Capacity increase có mở thêm quyền, public endpoint hoặc blast radius? | IAM review, network policy, tenant quota, audit |
| **Reliability** | Peak/failover/rolling deploy có đủ quota và headroom? | N+1 model, load test, DR test, dependency quota map |
| **Performance Efficiency** | Bottleneck nằm ở compute, DB, network hay provider? | End-to-end load test, p95/p99, queue/saturation metrics |
| **Cost Optimization** | Headroom/reserve có phù hợp demand và criticality? | Cost forecast, cost per transaction, utilization, commitment review |
| **Sustainability** | Có overprovision, idle capacity hoặc retry/refresh lãng phí? | Idle resource inventory, autoscaling efficiency, utilization trend |

Capacity quá nhỏ làm hệ thống không đáp ứng; capacity quá lớn làm lãng phí. Mục tiêu là đủ capacity cho workload và failure scenario đã cam kết, với mức dự phòng và chi phí được giải thích rõ.

## 17. Bài thực hành: lập kế hoạch quota và capacity cho BookingCloud

BookingCloud đang chạy trong một region với:

- Booking API peak hiện tại 4.000 RPS.
- Một application instance đạt 250 RPS ở SLO mục tiêu.
- Target utilization của application tier là 65%.
- Có 3 availability zones.
- Database chịu 3.000 write transaction/giây trước khi vượt p95 latency objective.
- Payment provider giới hạn 1.500 requests/giây.
- Campaign sau 3 tháng dự kiến làm traffic peak tăng 50%.
- Quota vCPU hiện tại là 400; mức sử dụng peak 240.
- Scale-out cần thêm IP, disk và load balancer target.

Hãy thực hiện:

**Bài 1 — Demand model:** phân biệt average, peak, burst và campaign demand; nêu assumption về traffic mix và read/write.

**Bài 2 — Application capacity:** ước lượng số instance cần cho 4.000 RPS tại 65% utilization; bổ sung N+1 nếu mất một zone.

**Bài 3 — Bottleneck:** đánh giá database và Payment provider; chỉ ra khi nào scale application không giúp tăng end-to-end throughput.

**Bài 4 — Quota inventory:** liệt kê quota phải kiểm tra ngoài vCPU: IP, NIC, disk, LB target, DB, queue, NAT/private endpoint và provider API.

**Bài 5 — Forecast:** tính peak sau campaign và growth buffer; xác định quota cần có trước campaign.

**Bài 6 — Autoscaling/admission:** đề xuất min/max replicas, scale trigger, queue/concurrency budget và degraded mode.

**Bài 7 — Quota increase:** soạn thông tin cần gửi provider, lead time và owner; tính requested limit có rollout/failover reserve.

**Bài 8 — Test plan:** lập load, spike, soak, stress và zone-failover test với tiêu chí SLO.

### Khung phân tích tự kiểm tra

| Câu hỏi | Điều cần chứng minh |
|---|---|
| Bao nhiêu instance cho peak? | Dùng benchmark throughput per instance và utilization target |
| Nếu mất một zone thì sao? | Capacity còn lại vẫn đáp ứng traffic hoặc degraded policy |
| vCPU quota đủ không? | Tính cả baseline, autoscale maximum và rollout surge |
| Database có phải bottleneck? | So sánh write demand với safe DB capacity |
| Payment provider đủ quota? | Tính tỷ lệ booking đi qua payment và provider limit |
| Campaign tăng 50%? | Pre-scale, quota approve và capacity test trước thời điểm |
| Autoscaler bị quota block? | Alert, admission control và fallback/runbook |
| Request quota đã approved? | Query lại limit thực tế và kiểm tra deployment/scale |

## 18. Checklist trước khi chốt capacity plan

- [ ] Có inventory quota theo provider, account, region, service và resource.
- [ ] Có owner, current limit, usage, peak, unit, lead time và increase path.
- [ ] Demand model phân biệt steady, peak, burst, growth và failure load.
- [ ] Capacity dựa trên benchmark ở SLO mục tiêu, không dựa chỉ vào nominal resource.
- [ ] Đã xác định bottleneck end-to-end ở mọi tầng.
- [ ] Có headroom và N+1/failover reserve theo failure scenario.
- [ ] Autoscaling có min/max, stabilization, cooldown và quota-failure handling.
- [ ] Queue/concurrency/rate limits và fairness được định nghĩa.
- [ ] Có degraded mode bảo vệ workflow quan trọng.
- [ ] Forecast có base/high/stress scenario và uncertainty.
- [ ] Quota request mở trước deadline theo lead time.
- [ ] Approval được xác minh trên đúng account/region/scope.
- [ ] Load, stress, spike, soak và failover test đã có kết quả.
- [ ] Dashboard có utilization, forecast-to-limit, scale failure, saturation và cost.
- [ ] Cost/headroom trade-off được review và có owner.

Quản lý quota bảo đảm cloud platform cho phép cấp phát tài nguyên cần thiết; capacity planning bảo đảm tài nguyên đó thực sự xử lý được workload trong giới hạn latency, availability và chi phí. Khi kết hợp inventory, demand forecast, headroom, autoscaling, admission control, load test và quy trình tăng quota có lead time, đội vận hành có thể phát hiện giới hạn trước khi nó trở thành outage và mở rộng hệ thống theo nhu cầu nghiệp vụ có kiểm chứng.
