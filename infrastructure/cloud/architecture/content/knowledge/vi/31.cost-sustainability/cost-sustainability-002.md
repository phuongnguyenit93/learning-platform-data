# Chi phí tài nguyên, yêu cầu, lưu trữ, bản sao và truyền dữ liệu

Một kiến trúc cloud có thể đáp ứng latency, availability và security nhưng vẫn vượt ngân sách nếu nhóm chỉ nhìn giá của máy chủ. Chi phí thực tế còn đến từ số request, dung lượng và loại storage, backup/snapshot, replica, cache, log, network egress, cross-zone/cross-region transfer và các dịch vụ được gọi gián tiếp. Khi traffic tăng, một thiết kế tưởng như rẻ ở mức thử nghiệm có thể phát sinh chi phí nhanh hơn doanh thu hoặc giá trị mà workload tạo ra.

Đánh giá chi phí kiến trúc cần bắt đầu từ workload và luồng dữ liệu. **Compute cost** phụ thuộc loại tài nguyên, thời gian chạy và mức sử dụng. **Request cost** có thể tính theo số lần gọi API, thao tác object, query hoặc message. **Storage cost** phụ thuộc dung lượng, class, thời gian lưu và thao tác đọc/ghi. **Replica cost** bao gồm tài nguyên dự phòng, bản sao dữ liệu và khả năng phục hồi. **Data transfer cost** phát sinh khi dữ liệu di chuyển giữa zone, region, provider, internet hoặc dịch vụ khác.

Bài học này thuộc chương **Chi phí và bền vững** của module **CLOUD_ARCHITECTURE**. Mục tiêu là phân tích các nguồn chi phí, xây dựng unit economics, phân bổ chi phí theo workload/tenant, đánh giá đánh đổi của replication và truyền dữ liệu, kiểm soát ngân sách và tối ưu sử dụng tài nguyên mà vẫn đáp ứng SLO, bảo mật và khả năng phục hồi theo tư duy Well-Architected.

## 1. Nhìn chi phí theo luồng workload

Không nên dự toán chỉ bằng cách cộng giá VM hoặc container. Một request tìm kiếm trên Booking API có thể:
1. Đi qua DNS, CDN, WAF, load balancer và API gateway.
2. Chạy trên application compute.
3. Đọc cache hoặc gọi database.
4. Lấy ảnh/metadata từ object storage hoặc CDN.
5. Gọi dịch vụ recommendation hoặc payment bên ngoài.
6. Phát event vào queue, ghi log, trace và metric.
7. Truyền dữ liệu giữa zone hoặc region.

Mỗi bước có thể tạo đơn vị tính tiền khác nhau. Một request HTTP có thể tạo nhiều database query, cache operation, log event và network transfer.

~~~mermaid
flowchart LR
    U["User request"] --> EDGE["CDN / WAF / Gateway"]
    EDGE --> APP["Application compute"]
    APP --> CACHE["Cache"]
    APP --> DB[("Database")]
    APP --> OBJ[("Object storage")]
    APP --> Q[("Queue / events")]
    APP --> EXT["External API"]
    EDGE -.-> NET["Data transfer"]
    APP -.-> OBS["Logs / metrics / traces"]
    DB -.-> REP["Replica / backup"]
    OBJ -.-> REP
~~~

Một cost model cần xác định:
- Workload nào tạo ra chi phí?
- Đơn vị đo là request, transaction, user, tenant, GB, GB-month, compute-hour hay job?
- Tài nguyên nào chạy liên tục, tài nguyên nào chạy theo nhu cầu?
- Dữ liệu được tạo, đọc, nhân bản, truyền và xóa ở đâu?
- Thành phần nào có cost tăng tuyến tính theo traffic, thành phần nào có bậc thang/quota?
- Chi phí nào là shared platform và cần phân bổ theo driver?

## 2. Các nhóm chi phí cloud chính

| Nhóm | Đơn vị tính thường gặp | Ví dụ |
|---|---|---|
| Compute | vCPU-hour, instance-hour, GPU-hour, memory/time | VM, container, serverless execution |
| Request/operation | số request, operation, API call | Object GET/PUT, queue request, database operation |
| Storage | GB-month, IOPS, throughput, request | Block volume, object storage, database storage |
| Database | instance-hour, vCPU, capacity unit, storage, backup | Managed relational/NoSQL |
| Replica/HA | compute + storage + replication | Read replica, standby DB, multi-zone |
| Backup/snapshot | GB-month, snapshot delta, restore operation | Database backup, volume snapshot |
| Network transfer | GB, route, endpoint-hour | Internet egress, cross-zone/region, NAT |
| Observability | ingest GB, indexed GB, retained GB, query compute | Logs, traces, metrics |
| Managed services | request, throughput, provisioned capacity | API gateway, CDN, WAF, stream |
| Support/license | subscription, support tier, feature | Enterprise support, commercial runtime |

Tên metric và cách tính cụ thể phụ thuộc provider, service, region, pricing tier và hợp đồng. Cost model nên gắn với price sheet hoặc pricing calculator hiện hành của nhà cung cấp; đừng hard-code đơn giá vào design document mà không ghi ngày và nguồn.

### 2.1. Fixed, variable và step cost

- **Fixed-like cost:** baseline compute hoặc managed service capacity chạy liên tục dù traffic thấp.
- **Variable cost:** request, data transfer, storage growth hoặc execution tăng theo workload.
- **Step cost:** khi vượt ngưỡng, cần thêm node, shard, throughput tier hoặc license.
- **Commitment cost:** khoản cam kết mua trước/đặt trước, có thể giảm đơn giá nhưng tăng rủi ro trả tiền cho capacity không dùng.
- **Operational cost:** nhân lực trực, quản trị, backup/restore test và incident response; có thể không xuất hiện như một dòng cloud bill nhưng vẫn là chi phí kiến trúc.

Một kiến trúc tối ưu theo giá đơn vị chưa chắc tối ưu tổng chi phí. Ví dụ instance có giá mỗi giờ thấp nhưng cần nhiều instance hơn và nhiều network transfer hơn có thể đắt hơn loại instance lớn.

## 3. Compute cost: máy chạy bao lâu và sử dụng hiệu quả đến đâu?

Compute thường bao gồm VM, container node, serverless execution, batch worker, GPU và managed runtime.

### 3.1. Các yếu tố ảnh hưởng

- Số instance/replica và cấu hình vCPU/RAM/GPU.
- Thời gian chạy và thời gian idle.
- Autoscaling min/max, warm pool và cold start.
- Kiến trúc multi-AZ/multi-region.
- CPU/memory utilization và workload profile.
- Runtime license, OS license, support.
- Disk/network đi kèm instance.
- Giá theo region, architecture và pricing model.

Đơn giản hóa:

\[
Compute\ Cost \approx \sum_i (InstanceHours_i \times Rate_i)
\]

Nếu tính theo serverless, cần thay instance-hours bằng số invocation, thời gian thực thi và memory/CPU allocation theo cách dịch vụ tính phí.

### 3.2. Right-sizing

Right-sizing là chọn cấu hình đủ để đáp ứng SLO và headroom với chi phí hợp lý. Cần đo:
- CPU và memory theo phân vị/tải đỉnh.
- Thời gian queueing và concurrency.
- I/O wait và network throughput.
- Request latency p95/p99.
- Autoscaling events và idle time.
- Capacity khi mất một node hoặc zone.

Không giảm instance size chỉ vì average CPU thấp. Có thể hệ thống cần headroom cho burst hoặc bị bottleneck ở network/IO. Không tăng size chỉ vì CPU cao nếu code có thể profile/tối ưu hoặc traffic có thể scale-out.

### 3.3. Scale-to-zero, schedule và commitment

Workload dev/test, batch hoặc internal tool có thể tắt ngoài giờ hoặc scale-to-zero. Production latency-sensitive thường cần baseline để tránh cold start. Reserved/committed capacity hoặc savings plan có thể giảm giá hiệu dụng khi nhu cầu ổn định, nhưng cần dự báo utilization và hiểu phạm vi áp dụng, thời hạn, payment option và flexibility.

Một cách thực tế là chia workload:
- Baseline ổn định: xem xét commitment sau khi có dữ liệu.
- Variable traffic: autoscaling và on-demand capacity.
- Interruptible batch: cân nhắc spot/preemptible nếu checkpoint/retry an toàn.
- Dev/test: schedule shutdown và tự động cleanup.
- Burst: giữ quota/headroom hoặc queue/load shedding.

## 4. Request cost: mỗi thao tác nhỏ có thể tích lũy

Các dịch vụ managed thường tính theo request/operation hoặc đơn vị xử lý. Ví dụ:
- Object storage GET/PUT/LIST.
- API gateway request.
- Queue publish/receive/delete.
- Stream ingestion/read.
- Serverless invocation.
- CDN request.
- Database read/write capacity hoặc query.
- KMS API call trong một số mô hình.

Nếu một request nghiệp vụ gọi 20 thao tác storage và 5 service API, chi phí trên một user action có thể lớn hơn dự kiến.

### 4.1. Request amplification

Request amplification là hiện tượng một request đầu vào tạo nhiều thao tác ở phía sau:
- Retry khi timeout.
- Fan-out tới nhiều service.
- Polling quá thường xuyên.
- N+1 database query.
- Object LIST lặp đi lặp lại.
- Log/trace emit quá nhiều span/event.
- Cache miss gây đọc lại nguồn.

Theo dõi số thao tác downstream trên mỗi transaction và retry rate. Backoff, batching, pagination, connection reuse, caching hợp lệ và event coalescing có thể giảm số lần gọi.

### 4.2. Ví dụ cost amplification

Một API nhận 1 triệu request/ngày. Mỗi request trung bình:
- 1 API gateway request.
- 4 database queries.
- 2 cache operations.
- 1 object metadata request.
- 3 log events.

Tổng số operation tương ứng lần lượt là 1M, 4M, 2M, 1M và 3M. Đây chưa phải phép quy đổi tiền; mỗi service có đơn giá/đơn vị khác nhau. Nhưng phép đo giúp thấy vì sao chỉ đếm inbound request là chưa đủ.

### 4.3. Cẩn thận với retry

Retry có thể cải thiện reliability nhưng khi dependency chậm, retry đồng loạt có thể nhân tải và chi phí. Cần:
- Retry budget và giới hạn số lần.
- Exponential backoff và jitter.
- Timeout theo deadline end-to-end.
- Idempotency cho thao tác có side effect.
- Circuit breaker/load shedding.
- Theo dõi request gốc và downstream attempt riêng biệt.

## 5. Storage cost: dung lượng, class và vòng đời dữ liệu

Storage cost không chỉ là dung lượng dữ liệu đang dùng. Nó còn gồm tier, số request, retrieval, replication, backup, minimum retention, early deletion fee hoặc data processing tùy dịch vụ.

### 5.1. Phân loại dữ liệu theo access pattern

| Nhóm dữ liệu | Access pattern | Hướng storage thường cân nhắc |
|---|---|---|
| Database transaction nóng | Đọc/ghi thường xuyên, latency thấp | Block/database storage hiệu năng cao |
| Ảnh và tài nguyên public | Đọc nhiều, ít thay đổi | Object storage + CDN |
| Log/telemetry mới | Ghi liên tục, tìm kiếm nhanh | Hot observability/search tier |
| Log/archive cũ | Ít truy cập, cần giữ lâu | Cold/archive object tier |
| Backup | Ghi theo lịch, restore khi có sự cố | Backup tier tách biệt |
| File upload tạm | Vòng đời ngắn, có thể xóa | Temporary object lifecycle |
| Data lake | Dữ liệu lớn, truy vấn theo batch | Object storage, format nén/columnar |

Chọn storage class dựa trên tần suất đọc, thời gian chấp nhận truy xuất, durability, availability, minimum storage duration và retrieval charges. Tier rẻ nhất có thể trở nên đắt khi dữ liệu phải đọc lại thường xuyên hoặc cần restore gấp.

### 5.2. Storage growth

Dự báo storage:

\[
Future\ Storage \approx Current\ Data + (Daily\ Growth \times Retention\ Days)
\]

Đây là mô hình sơ bộ, cần điều chỉnh cho compression, compaction, index, replica, versioning, tombstone, metadata và backup. Với database, index và WAL/log có thể tạo overhead đáng kể so với kích thước record nghiệp vụ.

### 5.3. Retention và lifecycle

Thiết kế lifecycle:
- Xóa dữ liệu tạm sau khi workflow kết thúc.
- Chuyển log/telemetry sang tier rẻ khi ít truy vấn.
- Retain backup theo policy và legal hold.
- Xóa phiên bản object cũ theo retention.
- Compact hoặc partition database/log.
- Xóa cache có TTL phù hợp.
- Kiểm tra orphan object và incomplete multipart upload.

Không rút ngắn retention để giảm bill nếu có yêu cầu pháp lý, điều tra hoặc recovery. Data owner và legal/privacy phải chấp thuận policy phù hợp.

### 5.4. Compression, format và small files

Compression giảm storage và transfer nhưng tốn CPU khi nén/giải nén. File format columnar và partition pruning có thể giảm lượng data scan khi query analytics. Quá nhiều small files làm tăng request/listing/metadata overhead và giảm hiệu quả query; batching/compaction có thể cải thiện.

Đánh giá bằng tổng cost: storage + request + retrieval + compute + network, không chỉ GB-month.

## 6. Replica cost: HA và khả năng đọc mở rộng đều có giá

Replica là bản sao compute, data hoặc service nhằm tăng availability, throughput hoặc recovery. Mỗi replica có thể tạo chi phí trực tiếp và gián tiếp.

Các loại:
- Application replica/pod/VM.
- Database read replica hoặc standby.
- Multi-AZ synchronous replica.
- Cross-region asynchronous replica.
- Cache cluster replica.
- Object replication/version copies.
- Search/index replica/shard.
- Queue/stream replication hoặc cross-region mirror.
- Backup/snapshot copy.

### 6.1. Replica không chỉ tốn storage

Tổng chi phí có thể gồm:
- Compute standby chạy liên tục hoặc tối thiểu.
- Storage bản sao.
- Replication log/throughput.
- Cross-zone/cross-region transfer.
- Snapshot/backup và retention.
- Monitoring và licensing.
- Capacity dự phòng cho lúc failover.
- Kiểm thử, vận hành và đối soát.

### 6.2. Active-active, active-passive và warm standby

| Topology | Cost profile | Lợi ích | Đánh đổi |
|---|---|---|---|
| Active-active | Nhiều region đều chạy capacity phục vụ traffic | Latency địa lý, dùng compute ở nhiều vùng | Replication, consistency, routing và coordination |
| Active-passive nóng | Standby đủ capacity hoặc gần đủ | RTO ngắn, cutover nhanh hơn | Idle capacity cao |
| Warm standby | Region dự phòng chạy thu nhỏ | Cân bằng cost và RTO | Cần scale-up và warm-up khi failover |
| Pilot light | Chỉ thành phần tối thiểu luôn sẵn sàng | Chi phí thường thấp hơn | RTO dài hơn, provisioning trong sự cố |
| Backup/restore | Chủ yếu trả backup/storage | Chi phí bình thường thấp | RTO dài và cần kiểm thử restore |

Không giảm replica chỉ dựa trên utilization bình thường. Khi mất region, traffic có thể dồn sang region còn lại; nếu capacity không đủ, phương án DR không đáp ứng SLO. Phải tính cost của standby cùng mục tiêu RTO/RPO và chi phí outage tránh được.

### 6.3. Read replica và cache

Read replica có thể tăng read throughput nhưng thêm storage/compute, replication lag và network. Cache giảm request tới database nhưng tốn memory/ops và có invalidation. Cần so sánh cost per successful read, correctness và freshness; không mặc định thêm replica luôn rẻ hơn tối ưu query.

## 7. Data transfer: chi phí ẩn giữa các tầng và khu vực

Data transfer thường khó dự toán nếu kiến trúc không vẽ rõ luồng dữ liệu.

Các luồng phổ biến:
- Internet ingress/egress.
- Cross-AZ hoặc cross-zone.
- Cross-region replication.
- VPC/VNet peering hoặc transit network.
- NAT gateway/egress gateway.
- CDN origin fetch và delivery.
- Object storage đến compute hoặc database.
- Log/trace export sang SIEM.
- Third-party API và SaaS transfer.
- Backup copy và restore.

~~~mermaid
flowchart LR
    USER["Internet users"] --> CDN["CDN / edge"]
    CDN --> APP["Region A app"]
    APP --> DB["Region A database"]
    APP --> OBJ["Object storage"]
    APP <-->|"Cross-zone calls"| CACHE["Cache in another zone"]
    DB <-->|"Cross-region replication"| DR["Region B replica"]
    APP --> NAT["NAT / egress"]
    NAT --> EXT["External APIs"]
    APP --> LOG["Central log archive"]
~~~

### 7.1. Egress và locality

Data egress ra internet hoặc sang một provider khác thường có pricing khác ingress. Nếu app và database đặt ở region/zone khác nhau, cross-zone traffic có thể phát sinh theo quy định dịch vụ. Đọc object từ một region khác hoặc gửi log sang region tập trung cũng có thể tạo transfer cost.

Tối ưu:
- Đặt compute gần data theo latency và residency.
- Dùng private connectivity khi có lợi nhưng vẫn kiểm tra phí endpoint/transfer.
- Cache gần người dùng cho nội dung phù hợp.
- Dùng CDN cho static/public content.
- Nén payload khi CPU tradeoff hợp lý.
- Tránh serialize payload lớn hoặc gọi service xuyên region trong critical path.
- Batch export/log thay vì gửi nhiều request nhỏ.
- Chọn replication scope đúng business requirement.

Không tối ưu transfer bằng cách phá bỏ network isolation hoặc data residency. Security và compliance là constraint, không phải cost tùy chọn.

### 7.2. Cross-zone traffic

Đặt nhiều replica trong nhiều AZ tăng resilience nhưng request giữa zone, replication hoặc shared service có thể tạo transfer cost. Cần kiểm tra topology: load balancer cross-zone, database client routing, cache placement, service mesh và replication behavior.

Có thể ưu tiên locality hoặc zone-aware routing để giảm transfer, nhưng không để một zone bị quá tải hoặc làm giảm availability. Đo cost cùng latency và failure behavior.

### 7.3. NAT và egress gateways

NAT gateway, firewall, egress proxy hoặc inspection service có thể tính theo giờ và theo lượng dữ liệu. Một thiết kế mọi workload đều đi qua một NAT tập trung có thể tạo chi phí và bottleneck. Cần:
- Phân biệt traffic đi tới public internet và traffic có private endpoint.
- Kiểm tra destination có thể dùng private service endpoint không.
- Theo dõi bytes và cost theo gateway/route.
- Tránh route log/object download không cần thiết qua đường egress đắt.
- Duy trì security inspection và policy cần thiết.

## 8. Cost allocation: biết chi phí thuộc về ai

Nếu bill chỉ có một dòng “production platform”, team không biết service, tenant hoặc product feature nào đang làm cost tăng. Cần thiết kế cost allocation từ đầu.

### 8.1. Tag/label strategy

Các tag thường hữu ích:
- environment: dev/stage/prod.
- service/product: booking-api/search/payment.
- owner/team.
- cost-center hoặc business-unit.
- application/tenant class.
- data classification.
- criticality/tier.
- managed-by/IaC repository.
- expiration/temporary resource.

Tag không nên chứa PII, secret hoặc dữ liệu nhạy cảm. Dùng naming/schema chuẩn, giá trị hợp lệ và enforcement qua policy. Một số dịch vụ hoặc cost line không hỗ trợ tag hoàn toàn; cần kết hợp account/project/subscription, usage labels, billing export và allocation rules.

### 8.2. Direct cost và shared cost

- **Direct cost:** có thể gắn rõ tới workload, ví dụ VM hoặc bucket riêng.
- **Shared cost:** dùng chung bởi nhiều team, ví dụ network hub, logging platform, DNS, security tooling hoặc cluster shared.

Các cách phân bổ shared cost:
- Theo request/transaction count.
- Theo CPU/memory usage.
- Theo storage consumed.
- Theo bytes transferred.
- Theo số tenant/user.
- Theo reserved capacity hoặc allocation key đã thống nhất.

Phân bổ cần minh bạch. Không nhất thiết phản ánh chính xác marginal cost nhưng phải tạo incentive hợp lý. Ghi rõ phần shared cost chưa phân bổ để tránh làm report tưởng như đầy đủ.

### 8.3. Unit economics

Một số chỉ số:
- Cost per booking completed.
- Cost per search request.
- Cost per 1.000 API calls.
- Cost per GB stored per month.
- Cost per TB scanned.
- Cost per message delivered.
- Cost per active tenant.
- Cost per successful inference/prediction.
- Cost per GB transferred.

Ví dụ:

\[
Cost\ per\ Booking = \frac{Total\ attributable\ platform\ cost}{Completed\ bookings}
\]

Cần xác định numerator gồm những gì (compute, DB, storage, transfer, shared platform, support) và denominator là booking tạo mới hay booking hoàn tất. So sánh theo thời gian hoặc giữa service cần giữ định nghĩa nhất quán.

### 8.4. Không dùng unit cost riêng lẻ làm mục tiêu duy nhất

Cost/request giảm có thể do request lỗi bị tính ít resource hơn hoặc do giảm chất lượng. Theo dõi cost per successful transaction cùng SLO, error rate, support load và business value. Cost optimization phải giữ quality floor.

## 9. Forecast, budget và anomaly detection

FinOps không chỉ đọc hóa đơn sau tháng. Nên có budget/forecast và phát hiện thay đổi bất thường trước khi vượt ngưỡng.

### 9.1. Forecast theo driver

Một forecast có thể dựa trên:
- Request rate và workload mix.
- Số user/tenant hoạt động.
- Dung lượng dữ liệu mới và retention.
- Replica count/backup policy.
- Traffic egress/replication.
- Release mới hoặc chiến dịch dự kiến.
- Price changes, commitment expiry và exchange/currency policy.

Mô hình sơ bộ:

\[
Monthly\ Cost = Compute + Requests + Storage + Replicas + Transfer + Observability + Other
\]

Không cộng các đơn vị vật lý khác nhau trước khi chuyển chúng thành cost theo rate tương ứng. Lưu giả định, nguồn rate và mức độ tin cậy của forecast.

### 9.2. Budget alerts

Budget có thể cấu hình theo:
- Account/project/subscription.
- Service hoặc team/cost center.
- Environment.
- Product/tenant.
- Loại chi phí hoặc usage quantity.

Các mức cảnh báo tham khảo: 50%, 80%, 90%, 100% budget; có thể kết hợp forecasted spend. Đây là chính sách mẫu, không phải ngưỡng bắt buộc. Cần gửi cảnh báo tới owner có khả năng hành động và đính kèm top cost drivers.

### 9.3. Anomaly detection

Tín hiệu bất thường:
- Compute-hour tăng đột ngột.
- Request hoặc retry tăng nhiều lần.
- Storage growth bất thường.
- Data egress tăng.
- Snapshot/backup được tạo hàng loạt.
- Replica count không scale-in.
- Log ingestion/cardinality tăng.
- NAT/endpoint traffic tăng không rõ nguyên nhân.

Điều tra cần liên kết bill với deployment, traffic, incident, new tenant, retention policy và abuse. Không tự động tắt một resource production chỉ vì cost anomaly; dùng owner, severity và playbook có approval.

## 10. Chi phí backup, snapshot và retention

Backup giúp đạt RPO/RTO nhưng tạo storage, API operation, transfer và restore cost. Chi phí phụ thuộc:
- Full/incremental backup.
- Tần suất snapshot.
- Retention period.
- Dữ liệu thay đổi mỗi ngày.
- Cross-region/cross-account copy.
- Snapshot chain và deleted volume behavior.
- Restore performance và temporary capacity.

### 10.1. Backup policy theo data tier

| Data tier | Tầm quan trọng | Chiến lược tham khảo |
|---|---|---|
| Transaction/ledger | Rất cao | Backup + transaction log/PITR + restore drill |
| Booking operational data | Cao | Backup định kỳ, PITR và cross-region copy theo RPO |
| Search index | Trung bình | Có thể rebuild từ source; snapshot nếu rebuild lâu |
| Cache | Thường tái tạo được | Không nhất thiết backup; warm-up plan |
| Static object | Tùy nguồn gốc | Versioning/replication hoặc backup |
| Temporary data | Thấp nếu tái tạo | TTL và cleanup |

Đừng tiết kiệm bằng cách bỏ backup cần thiết. Nhưng cũng không backup cache hoặc data tạm có thể tái tạo ở cùng tần suất như transaction ledger nếu không có lý do.

### 10.2. Restore cost và recovery capacity

Restore có thể cần:
- Compute tạm thời.
- Storage mới.
- Network transfer.
- IOPS/throughput tăng.
- Data reprocessing/replay.
- Nhân lực vận hành và downtime.

Backup giá thấp nhưng restore mất hai ngày có thể không đáp ứng RTO. Cần đo thời gian restore và chi phí ở quy mô thật, không chỉ nhìn bill backup.

## 11. Tối ưu theo workload, không chỉ theo loại tài nguyên

### 11.1. Compute

- Right-size sau khi đo peak và SLO.
- Autoscale theo tín hiệu phù hợp.
- Schedule dev/test và batch.
- Dùng spot/preemptible cho tác vụ có checkpoint/retry.
- Tối ưu code, query và concurrency trước khi tăng instance.
- Chọn architecture CPU/GPU phù hợp benchmark.

### 11.2. Request/operation

- Giảm N+1 query và polling.
- Dùng batch API khi hỗ trợ.
- Hợp nhất event và log tương tự.
- Dùng cache có freshness/invalidation rõ.
- Giảm retry amplification.
- Dùng pagination và filter để tránh scan toàn bộ.

### 11.3. Storage

- Chọn tier theo access pattern.
- Compression/columnar format cho analytics.
- Lifecycle cho object/log/archive.
- Xóa orphan/incomplete upload.
- Partition/compact dữ liệu.
- Giữ retention theo yêu cầu, không theo thói quen.

### 11.4. Replica và transfer

- Chỉ replicate dữ liệu cần cho RPO/RTO.
- Chọn warm standby/pilot light phù hợp criticality.
- Zone-aware routing khi an toàn.
- Đặt compute gần data.
- Dùng CDN cho nội dung phân phối rộng.
- Batch/compact replication khi semantics cho phép.
- Định kỳ kiểm tra replica/backup có thực sự được sử dụng đúng mục đích.

## 12. Giới hạn của cost optimization

Có những cách giảm bill nhưng làm hệ thống tệ hơn:
- Giảm replica khiến failover không đủ capacity.
- Hạ storage tier làm recovery chậm.
- Giảm log retention làm mất khả năng điều tra.
- Bỏ encryption hoặc network inspection để giảm chi phí.
- Tăng cache TTL làm dữ liệu stale và sai nghiệp vụ.
- Dùng instance quá nhỏ khiến latency và error tăng.
- Dùng spot cho workload không thể chịu interruption.
- Tắt backup để giảm storage.
- Hợp nhất mọi service vào một node để tránh phí network nhưng tăng blast radius.

Trước mỗi thay đổi, xác định quality floor:
- SLO availability/latency.
- RTO/RPO.
- Security and compliance controls.
- Data freshness/correctness.
- Capacity khi failover.
- Operational toil và recoverability.

Chỉ công nhận tiết kiệm khi metric chi phí giảm mà các ràng buộc này vẫn đạt.

## 13. Sustainability và hiệu quả sử dụng tài nguyên

Tối ưu chi phí thường hỗ trợ tính bền vững nếu loại bỏ compute idle, dữ liệu dư thừa, truyền tải lãng phí và xử lý trùng lặp. Tuy nhiên, không thể suy ra carbon footprint chỉ từ hóa đơn vì tác động còn phụ thuộc region energy mix, hardware efficiency, utilization và embodied carbon.

Các hướng thực hành:
- Right-size và tắt tài nguyên không dùng.
- Chọn region phù hợp với latency, residency và energy considerations.
- Nén dữ liệu và giảm transfer không cần thiết.
- Dùng lifecycle và data minimization.
- Tăng utilization mà không làm giảm resilience.
- Tái sử dụng resource pool khi isolation cho phép.
- Theo dõi compute-hours, storage growth và data transfer như proxy operational.
- Ưu tiên service/instance có hiệu suất tốt cho workload thực tế khi benchmark cho thấy lợi ích.

Không di chuyển workload tới region xa chỉ vì giá/energy metric tốt hơn nếu điều đó làm tăng latency, transfer, data residency risk hoặc failure complexity.

## 14. Cost governance và ownership

Một chương trình cost governance cần vai trò rõ:
- **Engineering owner:** quản lý workload design, utilization và optimization.
- **Product/business owner:** xác định value, demand forecast và quality tradeoff.
- **FinOps/finance:** billing data, allocation, forecast, budget và commitment.
- **Platform team:** shared service, tagging policy, network và tooling.
- **Security/compliance:** bảo đảm tối ưu không làm yếu control hoặc retention.

Quy trình:
1. Thiết lập account/project structure và tagging.
2. Export billing/usage data định kỳ.
3. Gắn cost với team/service/tenant.
4. Review top cost drivers.
5. Tạo budget và forecast.
6. Phát hiện anomaly.
7. Mở optimization action có owner.
8. Đo savings sau thay đổi và kiểm tra SLO.
9. Review commitment utilization/expiry.
10. Cập nhật architecture decision khi traffic hoặc product thay đổi.

### 14.1. Unit economics theo tenant

Nếu một nền tảng multi-tenant, cần biết tenant nào tạo ra chi phí vượt trội. Có thể phân bổ theo:
- Request count và compute time.
- Storage GB-month.
- Data egress bytes.
- Database query/throughput.
- Background job duration.
- Number of active users hoặc workload class.

Không đo lường tenant bằng cách gắn tenant ID vào mọi metric label nếu cardinality lớn. Có thể dùng billing meter, aggregation job hoặc cost allocation pipeline riêng.

## 15. Ví dụ tính cost model cho Booking API

Giả sử một tháng:
- 100 triệu search request.
- 5 triệu booking transaction.
- Application compute chạy trung bình 20 replica.
- Database có primary và một read replica.
- Object storage giữ 8 TB ảnh và tài liệu.
- 2 TB log hot retention và 20 TB archive.
- Cross-region replication cho database và object quan trọng.
- Egress tới CDN và external payment provider.

Một bảng model sẽ liệt kê quantity và rate:

| Thành phần | Quantity driver | Công thức chi phí minh họa |
|---|---|---|
| API compute | replica-hours × instance rate | compute hours × rate |
| Search API operations | gateway request count | request units × request rate |
| Database | primary + replica hours, storage, I/O | instance + storage + I/O |
| Object storage | GB-month theo class | capacity × class rate |
| Object operations | GET/PUT/LIST count | operation count × rate |
| Logs | ingest GB + retained GB-month | ingest + storage + query |
| Backup | snapshot storage + copy | backup GB-month + transfer |
| Cross-region | replicated GB | transfer GB × rate |
| Internet/CDN | request + egress bytes | request units + delivery bytes |
| Payment integration | API requests/third-party fee | provider-specific rate |

Không thể suy ra bill chính xác nếu chưa có provider, region, service tier, discount, pricing contract và rate hiện hành. Bảng này là khung thu thập dữ liệu để dùng pricing calculator/billing export.

### 15.1. Tìm cơ hội tối ưu

- Nếu search request tăng nhưng database QPS tăng nhanh hơn, kiểm tra N+1 query/cache miss.
- Nếu storage tăng nhanh hơn object uploaded, kiểm tra versioning, duplicate, incomplete upload và retention.
- Nếu egress tăng, phân tích CDN cache hit, cross-region read và log export.
- Nếu replica utilization thấp, đánh giá warm standby/pilot light nhưng giữ RTO/RPO.
- Nếu log bill tăng, kiểm tra cardinality, debug logging, sampling và retention.
- Nếu cost per booking tăng, phân tách fixed baseline với variable cost và xem error/retry rate.

## 16. ADR minh họa — Chọn topology replica cho Booking Platform

> **Bối cảnh:** Booking API cần bảo vệ giao dịch và có mục tiêu khôi phục theo RTO/RPO đã được product owner phê duyệt. Hai region được dự kiến sử dụng; traffic bình thường chủ yếu tập trung ở Region A.
>
> **Phương án A:** Active-active application và database ở cả hai region. Tăng khả năng phục vụ địa lý và dùng compute liên tục, nhưng cần data ownership/multi-writer strategy, replication và conflict handling.
>
> **Phương án B:** Region A active; Region B warm standby với application capacity thu nhỏ và database replica. Khi sự cố, scale B và promote theo runbook.
>
> **Quyết định minh họa:** Chọn B nếu RTO cho phép thời gian scale-up và measured failover test đạt mục tiêu. Không chọn chỉ vì chi phí bình thường thấp.
>
> **Cost model:** Bao gồm standby compute, storage replica, cross-region replication, backup, network egress và game-day capacity.
>
> **Resilience:** Kiểm thử peak traffic khi A mất, xác nhận quota và đủ capacity B. Nếu không đạt, tăng baseline hoặc chuyển topology.
>
> **Security:** KMS/identity/secret có ở cả hai region; replication channel và data residency được kiểm soát.
>
> **Kiểm chứng:** p95/p99, replication lag, RTO/RPO thực tế, cost/month, cost per booking, restore time và data reconciliation.
>
> **Điều kiện xem xét lại:** Traffic phân bố nhiều vùng, RTO rút ngắn hoặc chi phí egress/standby thay đổi đáng kể.

## 17. Bài tập thực hành: tìm chi phí tăng bất thường

Một nền tảng đặt chỗ có bill tăng 45% trong tháng vừa rồi dù số booking chỉ tăng 8%. Báo cáo sơ bộ cho thấy:
- Application compute tăng 10%.
- Object storage tăng 35%.
- Request operations tăng 60%.
- Cross-region transfer tăng gấp đôi.
- Logging ingestion tăng 70%.
- Database read replica utilization thấp.
- Backup storage tăng đều nhưng chưa có restore drill gần đây.

**Yêu cầu:**
1. Lập giả thuyết theo từng cost driver.
2. Xác định metric/usage detail cần lấy để kiểm chứng.
3. Phân biệt fixed, variable và step cost.
4. Tìm request amplification ở object/database/API.
5. Kiểm tra object version, lifecycle, duplicate và incomplete upload.
6. Phân tích cross-region traffic và cache/CDN behavior.
7. Review log volume, cardinality, sampling và retention.
8. Đánh giá có thể giảm replica hay thay đổi topology không theo RTO/RPO.
9. Xây dựng cost per booking và cost per successful search.
10. Đề xuất optimization theo mức lợi ích, rủi ro và owner.

### Hướng giải quyết

- Object storage tăng 35%: kiểm tra byte growth, versioning, multipart upload, duplicate, retention, backup và data replication; đối chiếu số object mới với dung lượng.
- Request operations tăng 60%: phân tích GET/PUT/LIST, retry, polling, N+1 và cache hit; xác định operation trên mỗi transaction.
- Cross-region transfer tăng gấp đôi: kiểm tra routing, replication scope, cross-region read, CDN origin fetch, logging/export và workload placement.
- Logging tăng 70%: tìm source/field/cardinality tăng, debug level, duplicate ingestion và retention; không bỏ log security/audit cần thiết chỉ để giảm bill.
- Read replica utilization thấp: kiểm tra workload routing, failover role, read-after-write và capacity khi primary/zone lỗi trước khi giảm.
- Backup tăng đều: xem retention/version chain và compression nhưng phải giữ RPO; chạy restore drill để xác nhận giá trị backup.
- Tính cost per booking/search cùng SLO và error/retry rate để không tối ưu theo mẫu số sai.
- Xếp action theo savings estimate, effort, risk, time-to-benefit và owner; đo lại sau thay đổi.

### Câu hỏi tự kiểm tra

1. Vì sao một request HTTP có thể tạo nhiều cost-bearing operations?
2. Fixed, variable, step và commitment cost khác nhau thế nào?
3. Storage tier rẻ nhất có thể làm tổng chi phí cao hơn trong trường hợp nào?
4. Replica tạo những loại chi phí nào ngoài compute và storage?
5. Cross-zone và cross-region traffic phát sinh trong những tình huống nào?
6. Vì sao egress và NAT thường khó dự toán nếu thiếu data-flow diagram?
7. Cost allocation tag giúp ai ra quyết định và có giới hạn gì?
8. Cost per booking cần định nghĩa numerator/denominator ra sao?
9. Tại sao không nên giảm log retention hoặc backup chỉ để đạt budget?
10. Làm sao cân bằng warm standby cost với RTO?
11. Retry storm ảnh hưởng request cost và downstream cost như thế nào?
12. Vì sao cost optimization cần xem cả SLO, security và sustainability?

Quản lý chi phí cloud hiệu quả không bắt đầu bằng việc tìm instance rẻ nhất. Nó bắt đầu từ **workload, các thao tác mà workload tạo ra và hành trình dữ liệu qua compute, request, storage, replica và network**. Khi quantity driver, owner và unit economics được đo rõ, nhóm có thể tìm cost amplification, right-size, chọn lifecycle/replication hợp lý và dự báo ngân sách. Mọi khoản tiết kiệm cần được kiểm chứng cùng SLO, RTO/RPO, security và chất lượng nghiệp vụ để kiến trúc vừa hiệu quả vừa bền vững.
