# Tính dung lượng dự phòng khi mất một miền lỗi

## 1. Vì sao phải tính capacity sau khi mất một miền lỗi?

Một hệ thống có thể đang chạy khỏe khi mọi availability zone (AZ), node hoặc deployment cell đều hoạt động. Nhưng khi một miền lỗi mất kết nối hoặc dừng hoàn toàn, tải của miền đó thường phải chuyển sang phần hạ tầng còn lại. Nếu phần còn lại không đủ compute, database connection, storage throughput, network bandwidth hoặc queue consumer capacity, hệ thống có thể tiếp tục “sống” về mặt hạ tầng nhưng không còn đáp ứng được tải nghiệp vụ.

**Failure domain** là một phạm vi tài nguyên có thể cùng chịu ảnh hưởng bởi một sự cố. Ví dụ: host, rack, AZ, region, deployment cell, cluster hoặc một shared dependency. **Failure-domain capacity planning** xác định tổng năng lực cần bố trí để sau khi mất một failure domain đã chọn, các miền còn lại vẫn phục vụ được workload trong mục tiêu SLO.

Cần phân biệt:

- **Normal capacity:** năng lực cần dùng khi mọi miền hoạt động bình thường.
- **Failover capacity:** năng lực còn lại hoặc có thể cấp phát sau khi một miền lỗi.
- **Headroom:** phần năng lực chưa sử dụng để hấp thụ biến động, burst và sai số dự báo.
- **N+1:** có thêm năng lực tương đương một đơn vị/miền cần thiết để chịu được một lỗi theo giả định đã định nghĩa.
- **N+X:** dự phòng cho X lỗi hoặc X đơn vị capacity; phải ghi rõ X là số node, zone hay lượng tải.
- **Degraded mode:** trạng thái giảm một số chức năng hoặc chất lượng để ưu tiên workload quan trọng sau sự cố.

Trong module **CLOUD_ARCHITECTURE**, chương **Mở rộng hệ thống** xem dự phòng capacity như một phần của độ tin cậy và khả năng mở rộng, gắn với SLO, RTO/RPO, bảo mật, chi phí và khả năng vận hành.

Sau bài học, người học có thể:

1. Xác định failure domain và giả định sự cố cần chịu được.
2. Tính capacity tối thiểu còn lại sau khi mất một hoặc nhiều miền.
3. Phân biệt N+1 về số lượng node với N+1 về năng lực thực tế.
4. Tính thêm headroom cho peak demand, burst, failover và scale-up delay.
5. Đánh giá compute, database, queue, network, storage và dependency capacity đồng thời.
6. Thiết kế degraded mode, traffic shifting, admission control và recovery.
7. Kiểm chứng bằng load test, fault injection và diễn tập failover.

## 2. Bắt đầu từ failure domain và service objective

Không thể tính dự phòng nếu chưa xác định mình muốn chịu được loại lỗi nào. “Mất một miền lỗi” có thể mang ý nghĩa rất khác nhau.

| Failure domain | Ví dụ sự cố | Phạm vi có thể bị ảnh hưởng |
| --- | --- | --- |
| Process/container | Crash, OOM, runtime failure | Một instance hoặc replica |
| Host/node | Máy vật lý hoặc VM dừng | Các workload cùng host |
| Rack/power/network segment | Mất điện hoặc switch | Nhiều host trong cùng vùng vật lý |
| Availability zone | Mất zone hoặc kết nối tới zone | Compute, storage, network và replicas trong zone |
| Region | Region outage hoặc mất đường kết nối | Một vùng địa lý cùng dịch vụ phụ thuộc |
| Deployment cell | Lỗi cấu hình hoặc quá tải cell | Nhóm tenant/workload trong cell |
| Shared dependency | DNS, identity, KMS, control plane, message broker | Có thể ảnh hưởng nhiều zone/region |
| Provider/service control plane | Dịch vụ quản lý không hoạt động | Provisioning, scaling, failover hoặc thay đổi cấu hình |

Một thiết kế chịu được một host failure chưa chắc chịu được một AZ failure. Ba AZ cũng không tự động chịu được region outage nếu tất cả data replication, identity hoặc DNS đều phụ thuộc một region.

### 2.1. Viết failure assumption rõ ràng

Ví dụ một requirement có thể ghi:

- Workload phải chịu được mất hoàn toàn một trong ba AZ.
- Không giả định hai AZ cùng mất đồng thời trong kịch bản chuẩn; kịch bản N+2 được đánh giá riêng.
- Sau khi mất một AZ, hệ thống phải duy trì 100% critical workload và tối thiểu 60% best-effort workload.
- API critical giữ p95 dưới 500 ms và error rate dưới ngưỡng SLO.
- Traffic chuyển hướng trong vòng 60 giây; compute bổ sung có thể khởi tạo trong tối đa 5 phút.
- Không xác nhận booking/payment nếu datastore không đạt consistency requirement.

Đó là requirement có thể kiểm chứng. Câu “hệ thống phải high availability” không đủ để tính capacity.

### 2.2. Phân biệt availability, RTO và RPO

- **Availability/SLO:** tỷ lệ hoặc chất lượng dịch vụ cần duy trì.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể chấp nhận mất, thường quy đổi thành thời gian dữ liệu.
- **Capacity objective:** mức tải hệ thống phải xử lý trong trạng thái bình thường và trạng thái failover.

Có đủ capacity mà failover mất 30 phút vẫn có thể vi phạm RTO. Failover nhanh nhưng replica thiếu dữ liệu vẫn có thể vi phạm RPO. Capacity chỉ là một phần của khả năng phục hồi.

## 3. Định nghĩa N, X và tải cần phục vụ

Trước hết xác định **N là nhu cầu thực**, không nhất thiết là số instance đang chạy. Nên mô tả N bằng đơn vị workload có thể đo:

- request/second theo route hoặc cost unit.
- concurrent requests hoặc active sessions.
- job/second và queue processing throughput.
- CPU cores, memory, IOPS, storage throughput.
- database connections và query units.
- network throughput theo ingress/egress.
- số booking/payment hoặc transaction/second.

**X** cũng cần ghi rõ: X failure domains, X nodes, X replicas hoặc X đơn vị năng lực. Tránh viết “N+1” mà không chỉ ra một đơn vị dự phòng có thể xử lý bao nhiêu tải.

### 3.1. Tải thiết kế không phải trung bình ngày

Dùng workload profile thay vì chỉ lấy average:

- Peak theo giờ/ngày/mùa/sự kiện.
- Burst ngắn và ramp-up rate.
- Tăng trưởng dự báo trong thời gian vòng đời hạ tầng.
- Traffic mix giữa API rẻ và API tốn tài nguyên.
- Retry amplification khi dependency lỗi.
- Job background và batch trùng với peak tương tác.
- Workload mới sau failover, ví dụ status polling hoặc retry từ client.

Nên có ít nhất ba mức:

| Mức tải | Ý nghĩa | Mục đích |
| --- | --- | --- |
| Typical | Tải thường gặp | Tính utilization và cost bình thường |
| Design peak | Peak có xác suất và thời lượng phù hợp | Xác định capacity tối thiểu vận hành |
| Stress/extreme | Burst hoặc sự kiện ngoài dự báo | Xác định degraded mode và overload boundary |

Failover thường xảy ra đúng lúc có vấn đề bên ngoài; vì vậy không nên lấy tải trung bình thấp để chứng minh đủ capacity.

## 4. Công thức cơ bản cho N+1

Giả sử có M failure domains giống nhau, mỗi domain cung cấp capacity C. Mất một domain thì capacity còn lại:

```text
Remaining capacity after one-domain loss = (M - 1) × C
```

Để phần còn lại đáp ứng design demand D và headroom H:

```text
(M - 1) × C >= D × (1 + H)

C >= D × (1 + H) / (M - 1)
```

Trong đó H là headroom tính theo tỷ lệ so với demand. Chọn M=3 AZ, design demand D=900 request cost units/s và headroom H=25%:

```text
C >= 900 × 1.25 / (3 - 1)
C >= 562.5 units/s per AZ

Total provisioned capacity >= 3 × 562.5
                               = 1,687.5 units/s
```

Sau khi một AZ mất, hai AZ còn lại có tổng capacity 1.125 units/s, lớn hơn demand cộng headroom 1.125 units/s. Đây là minh họa số học, chưa tính skew, dependency và capacity không đồng nhất.

### 4.1. Một node dự phòng không đủ nếu node không đủ tải

Với 3 node, mỗi node chạy 400 RPS khi bình thường và tổng nhu cầu là 1.200 RPS. Nếu một node mất, hai node còn lại chỉ xử lý được 800 RPS ở cấu hình hiện tại. Đếm “có ba node” không chứng minh N+1; cần kiểm tra công suất thực tế sau lỗi.

Nếu muốn hai node còn lại xử lý 1.200 RPS với headroom 20%, mỗi node phải có năng lực:

```text
C >= 1,200 × 1.20 / 2
C >= 720 RPS
```

Capacity có thể là CPU, concurrency hoặc throughput giới hạn; RPS chỉ là đại diện nếu request cost tương đối đồng nhất.

## 5. Công thức tổng quát với miền lỗi không đồng nhất

Trong thực tế các AZ hoặc cell có thể khác capacity, và workload có thể được phân bố không đều.

Gọi:

- C_i là capacity usable của domain i.
- D_i là tải đang chạy trên domain i.
- D là tổng demand cần phục vụ.
- L là tập domain bị mất trong kịch bản.
- H là headroom mục tiêu.

Capacity còn lại:

```text
C_remaining(L) = Σ C_i, for all i not in L

Feasibility condition:
C_remaining(L) >= D × (1 + H)
```

Công thức tổng chỉ là điều kiện cần khi có thể phân phối workload tự do. Nếu shard, partition key, session, storage volume hoặc tenant bị khóa vào một domain cụ thể, tổng capacity có thể đủ nhưng một số workload vẫn không chuyển được.

Cần kiểm tra capacity theo từng loại tài nguyên và placement constraint; không được cộng CPU của AZ A với database connection ở AZ B như thể chúng thay thế nhau.

### 5.1. Capacity usable khác capacity danh định

Để tính C_i, loại trừ các phần không thể dùng trong failover:

- Capacity reserved cho OS, sidecar, daemon, monitoring và system services.
- Node/instance đang bảo trì hoặc có lỗi nền.
- Resource limit do quota của account/region.
- Phần capacity không thể route tới do security/network policy.
- CPU/memory bị giới hạn bởi container requests/limits.
- Database connection dành cho admin/maintenance hoặc workload khác.
- Capacity cần để hoàn tất recovery, replication hoặc rebalancing.

Dùng **usable capacity** đo được trong workload đại diện, không dùng tổng vCPU quảng cáo.

## 6. Tính headroom và utilization ceiling

Headroom là khoảng trống có chủ ý để xử lý biến động và sự cố. Không phải toàn bộ resource “đang rảnh” đều có thể dùng an toàn.

Nếu yêu cầu headroom H trên design demand D:

```text
Required capacity = D × (1 + H)
Target utilization = D / Required capacity
                  = 1 / (1 + H)
```

Ví dụ H=25% thì target utilization khoảng 80% của capacity được dự phòng. Nếu dùng khái niệm utilization ceiling U, công thức tương ứng là:

```text
Required capacity >= D / U
```

Cần nhất quán cách định nghĩa. “25% headroom so với demand” không giống “giữ 25% capacity trống”: trường hợp thứ hai có utilization ceiling 75% và required capacity là D/0.75.

### 6.1. Không dùng một utilization ceiling cho mọi resource

CPU 80% có thể chấp nhận trong workload batch, nhưng database connection pool 80% có thể đã nguy hiểm nếu query duration biến động. Network link có thể cần headroom cho burst và replication; storage IOPS có thể có latency tăng mạnh gần saturation.

Đặt ceiling theo metric quyết định SLO:

- CPU: utilization, throttling, run queue.
- Memory: working set, GC, page faults, OOM risk.
- Database: connections, active queries, lock waits, IOPS, replication lag.
- Network: throughput, packet drops, retransmits, connection tracking.
- Queue: age, depth và drain rate.
- Storage: IOPS, throughput, latency và free capacity.

## 7. Tải sau failover có thể cao hơn tải trước failover

Khi một domain mất, hệ thống có thể nhận thêm tải gián tiếp:

- Client retry do timeout hoặc reset connection.
- Load balancer health check và reconnect tạo burst.
- User polling trạng thái giao dịch đang pending.
- Replica cần đồng bộ dữ liệu hoặc rebuild index.
- Cache lạnh làm tăng database reads.
- Traffic được route qua đường mạng dài hơn.
- Một region phải thực hiện thêm authentication, routing hoặc orchestration.
- Queue backlog tích tụ trong thời gian lỗi bắt đầu được xử lý trở lại.

Vì vậy có thể mô hình hóa:

```text
Failover demand =
    surviving normal demand
  + rerouted demand
  + retry / reconnect amplification
  + recovery / replication work
```

Nếu load shedding hoặc client retry policy không được kiểm soát, failover capacity được tính theo traffic bình thường sẽ bị thiếu.

### 7.1. Retry budget và load shedding

Thiết kế retry cần backoff, jitter, deadline và giới hạn số lần. Gateway/service nên:
- Từ chối sớm workload ít ưu tiên khi capacity gần cạn.
- Giới hạn concurrency và queue depth.
- Bảo vệ dependency bằng bulkhead và circuit breaker.
- Không retry đồng thời ở client, gateway, service và worker mà không có budget chung.
- Ưu tiên giao dịch đã bắt đầu cần hoàn tất hoặc đối soát.
- Trả 429/503 cùng retry guidance phù hợp.

Capacity planning và traffic policy phải được tính cùng nhau.

## 8. Compute capacity trong kịch bản mất AZ

Compute thường dễ hình dung nhất nhưng không chỉ đếm số VM/container.

Cần tính:

- vCPU thực dùng được và mức CPU throttling.
- Memory working set, cache memory và GC headroom.
- Instance type/shape còn quota ở AZ/region.
- Pod requests/limits và scheduler placement constraints.
- Autoscaling maximum, node group maximum và IP/subnet address capacity.
- Startup time, image pull, initialization và readiness.
- Placement spread/anti-affinity để replica không cùng miền lỗi.
- System workload/daemon overhead.

### 8.1. Static capacity và autoscaling

Static spare capacity có thể nhận tải ngay sau failover, nhưng tốn chi phí khi bình thường. Autoscaling có thể tiết kiệm hơn, nhưng cần thời gian phát hiện, provision, boot, pull image, warm-up và pass readiness.

Thời gian scale-out:

```text
T_scale =
    detection delay
  + provisioning delay
  + boot / image pull
  + initialization / warm-up
  + readiness / traffic ramp
```

Nếu workload cần hấp thụ ngay từ giây đầu, không thể dựa hoàn toàn vào autoscaling có T_scale vài phút. Cần baseline spare capacity, queue buffering hoặc degraded mode trong giai đoạn scale-up.

### 8.2. Kubernetes topology spread

Khi chạy Kubernetes, cần kiểm tra:
- Pod replicas phân bố qua các zone, không chỉ khác node.
- Topology spread constraints và pod anti-affinity.
- PodDisruptionBudget có phù hợp rollout và node drain.
- Node pool/cluster capacity ở zone còn lại.
- Persistent volume topology và khả năng attach sau zone failure.
- Cluster autoscaler có thể tạo node ở zone còn sống.
- IP subnet, CNI và quota không chặn scale-out.

PodDisruptionBudget không tự bảo đảm khả năng chịu AZ failure. Nó chủ yếu kiểm soát voluntary disruption; mất zone là failure ngoài kế hoạch.

## 9. Stateful capacity: database, cache và storage

Compute stateless có thể chuyển sang node khác tương đối dễ. Stateful tier thường khó hơn do data placement, replication, quorum và throughput.

### 9.1. Database capacity

Đừng chỉ tính số database instances. Cần tính:
- Query throughput sau khi failover.
- Connection budget và connection pool.
- CPU, memory, lock contention và IOPS.
- Replication lag và khả năng catch-up.
- Leader/quorum behavior khi mất AZ.
- Read replica có thể promotion và capacity sau promotion.
- Storage write throughput và free capacity.
- Connection storm khi clients reconnect.

Nếu primary mất, replica mới có thể trở thành primary nhưng phải gánh cả write và một phần read traffic đang chuyển tới. Nếu replica được sizing chỉ để phục vụ read nhỏ, nó có thể quá tải ngay sau promotion.

### 9.2. Quorum và replica placement

Với 3 voting replicas đặt ở 3 AZ, quorum majority là 2 trong mô hình consensus phổ biến. Mất một AZ vẫn còn hai thành viên có thể duy trì quorum, tùy protocol và trạng thái cluster.

Tuy vậy, số replica và quorum không bảo đảm performance. Hai replicas còn lại phải có đủ CPU, IOPS, network và disk; leader election/recovery có thể gây tăng latency. Không đặt hai trong ba voting members cùng một AZ nếu mục tiêu là chịu mất một AZ.

### 9.3. Cache capacity

Mất một cache node/zone có thể làm:
- Replica/cache shard mất dữ liệu.
- Key được remap sang node khác.
- Hit ratio giảm và database QPS tăng.
- Rebuild/warmup tạo network/CPU surge.

Cần capacity dự phòng cả cho cache service lẫn origin database trong tình huống cache cold. Replication cache không thay thế source of truth; dữ liệu cần độ bền phải được lưu ở storage phù hợp.

### 9.4. Object/block/file storage

Xác định:
- Replication/erasure coding có chịu được failure domain đang xét?
- Storage throughput còn lại sau mất một nhóm node/zone.
- Persistent volume có thể attach ở AZ khác không?
- Snapshot/backup nằm cùng hay khác failure domain?
- Data recovery và rehydration mất bao lâu?
- Read/write semantics trong degraded mode.

Không giả định multi-AZ storage có cùng guarantee về availability, RPO và performance cho mọi storage class.

## 10. Network capacity và đường đi failover

Mất một zone có thể dồn traffic qua các đường còn lại. Network là bottleneck thường bị bỏ quên vì compute/database dashboard vẫn xanh.

Cần tính:
- Load balancer capacity và connection rate.
- NAT/firewall/inspection throughput.
- Transit gateway/router bandwidth và packet processing.
- Cross-AZ/cross-region replication traffic.
- Egress bandwidth ra Internet.
- DNS, service discovery và connection tracking.
- Subnet/IP address capacity cho pod/instance scale-out.
- TLS termination và certificate/handshake CPU.

### 10.1. Traffic concentration

Nếu traffic bình thường chia đều ba AZ, mỗi AZ mang khoảng một phần ba. Mất một AZ nghĩa hai AZ còn lại phải gánh tổng traffic. Nhưng nếu load balancer hoặc client affinity làm phân bố lệch, phần tải có thể không đều.

Ví dụ tổng 9 Gbit/s traffic:
- Bình thường mỗi AZ nhận 3 Gbit/s.
- Sau khi mất một AZ, hai AZ còn lại cần nhận trung bình 4,5 Gbit/s mỗi AZ, chưa tính retry hoặc đường đi khác.
- Nếu một AZ chỉ có link usable 4 Gbit/s, tổng capacity 8 Gbit/s không đủ dù compute còn dư.

### 10.2. Network dependency

Kiểm tra đường failover không dùng chung một bottleneck với miền lỗi. Hai AZ độc lập về compute nhưng cùng đi qua một NAT Gateway, firewall appliance hoặc transit link đơn lẻ vẫn có thể có failure domain chung.

## 11. Queue và background processing

Queue giúp hấp thụ burst và tách tốc độ tiếp nhận khỏi tốc độ xử lý. Nhưng sau khi một worker zone mất, consumer còn lại cần đủ năng lực drain backlog trong thời hạn mục tiêu.

Nếu:
- B là backlog message.
- λ là tốc độ message mới đến.
- μ là tổng processing rate còn lại.

Queue chỉ giảm backlog khi μ > λ. Thời gian drain gần đúng khi tốc độ ổn định:

```text
Drain time ≈ B / (μ - λ)
```

Ví dụ backlog 120.000 messages, arrival rate 200 msg/s và surviving workers xử lý 500 msg/s:

```text
Drain time ≈ 120,000 / (500 - 200)
           = 400 seconds
           ≈ 6.7 minutes
```

Nếu μ nhỏ hơn hoặc bằng λ, backlog không giảm. Queue depth thấp ban đầu có thể che giấu một vấn đề capacity đang diễn ra; theo dõi oldest message age và processing lag, không chỉ số message.

### 11.1. Consumer failover

- Consumer group/partition assignment phải tái cân bằng sau lỗi.
- Message visibility/lease timeout cần phù hợp thời gian xử lý.
- Consumer phải idempotent vì message có thể được giao lại.
- DLQ phải có capacity và quy trình redrive.
- Batch size tránh làm timeout hoặc tăng retry blast radius.
- Concurrency cap phải bảo vệ dependency downstream.

## 12. Dependency capacity và shared bottleneck

Capacity của ứng dụng bị giới hạn bởi dependency yếu nhất trên đường xử lý.

Ví dụ API có thể phục vụ 10.000 RPS nhưng database chỉ chịu 2.000 query units/s và payment provider chỉ cho 300 request/s. Nếu mọi request đều gọi hai dependency, hệ thống không thể có throughput cao hơn budget đó chỉ bằng cách tăng compute.

### 12.1. Capacity theo service chain

```text
End-to-end throughput <= min(
    compute capacity,
    database capacity,
    queue/worker capacity,
    network capacity,
    external provider quota
)
```

Đây là cách nhìn đơn giản; nếu service có cache, fan-out hoặc workload cost khác nhau thì phải quy đổi theo request mix và unit cost.

### 12.2. Shared dependency là failure domain ẩn

Các thành phần sau có thể làm mất ý nghĩa multi-AZ nếu chỉ có một instance/endpoint/capacity:
- Identity provider hoặc token validation dependency.
- DNS/resolver hoặc service discovery.
- KMS/secret manager theo quota hoặc regional endpoint.
- Shared cache, message broker hoặc schema registry.
- NAT/firewall/proxy hoặc observability collector.
- Control plane phục vụ scheduling/provisioning.

Không phải dependency nào cũng cần chạy trong cùng data plane, nhưng cần xác định cached credential, local fallback, retry policy và giới hạn quota trong thời gian sự cố.

## 13. Tính N+1 theo workload mix

RPS không phải đơn vị đủ tốt khi request cost khác nhau. Có thể quy đổi sang workload units:

```text
Total workload units/s =
    Σ (request_rate_i × cost_weight_i)

Example:
  Search: 500 req/s × 1 unit = 500
  Booking: 100 req/s × 5 units = 500
  Export: 10 req/s × 20 units = 200
  Total = 1,200 units/s
```

Nếu một AZ mất, capacity còn lại phải xử lý workload units tương ứng. Trong overload, có thể ưu tiên booking và giảm tốc export; khi đó capacity requirement phải dựa trên degraded policy đã định nghĩa chứ không phải giả định mọi route đều có quyền ngang nhau.

### 13.1. Phân bổ theo priority

| Priority | Ví dụ | Khi failover |
| --- | --- | --- |
| Critical | Authentication, booking commit, payment state | Giữ đầy đủ capacity theo SLO |
| Important | Search, booking read, profile | Duy trì phần lớn service |
| Best effort | Export lớn, analytics backfill | Có thể queue, throttle hoặc tạm dừng |
| Background maintenance | Reindex, cleanup, compaction | Hoãn nếu cạnh tranh capacity |

Đặt admission control theo tier để tránh background job làm critical path quá tải.

## 14. N+1 so với N+2 và mục tiêu chịu nhiều lỗi

N+1 thường chịu được một failure domain theo giả định. Nếu có yêu cầu chịu hai miền cùng lúc, dùng N+2 hoặc tính theo tập failure scenarios.

Với M miền giống nhau và cần chịu X miền mất:

```text
(M - X) × C >= D × (1 + H)

C >= D × (1 + H) / (M - X)
```

Ví dụ có 4 AZ, cần chịu đồng thời 2 AZ loss, demand 600 units/s và 20% headroom:

```text
C >= 600 × 1.20 / (4 - 2)
C >= 360 units/s per AZ

Total = 4 × 360 = 1,440 units/s
```

Sau khi mất hai AZ, hai AZ còn lại cung cấp 720 units/s, đủ cho 600 units/s demand và 20% headroom. Tuy nhiên, hai AZ lỗi có thể không độc lập về nguyên nhân. Sự cố region, network hub hoặc IAM có thể đánh sập nhiều AZ cùng lúc; N+2 theo AZ không bảo đảm chịu region-wide failure.

### 14.1. Fault combination và correlated failure

Liệt kê các cặp lỗi có thể cùng xảy ra:
- AZ mất và database replica đang bảo trì.
- AZ mất trong lúc deployment rollout.
- Region bị lỗi trong khi cross-region replication lag cao.
- Network partition khiến một vùng mất quorum nhưng compute vẫn chạy.
- Shared identity/KMS quota cạn đồng thời traffic tăng.
- Cache failover tạo database overload.

Capacity planning cần kiểm tra trạng thái đã degraded rồi lại gặp một lỗi nữa, không chỉ một failure đơn lẻ trong trạng thái bình thường.

## 15. Scale-out delay và warm spare strategy

Có ba chiến lược phổ biến:

- **Active-active:** mọi domain đều nhận traffic bình thường; khi một domain mất, phần còn lại tiếp nhận phần tải chuyển đến.
- **Active-standby/warm standby:** domain dự phòng được giữ ở trạng thái sẵn sàng một phần, cần scale-up hoặc promote khi lỗi.
- **Cold standby:** tài nguyên được provision sau sự cố; chi phí thấp hơn nhưng RTO dài và provisioning có thể thất bại khi control plane/quota bị ảnh hưởng.

| Chiến lược | Chi phí bình thường | Failover speed | Rủi ro chính |
| --- | --- | --- | --- |
| Active-active với N+1 capacity | Cao hơn do giữ headroom | Nhanh nếu traffic chuyển được | Phải sizing toàn bộ miền còn lại |
| Warm standby | Trung bình | Phụ thuộc promotion/scale-up | Cold resources hoặc quota không đủ |
| Cold standby | Thấp hơn khi idle | Chậm hơn | Provisioning trong sự cố có thể không thành công |

### 15.1. Capacity reserve thực sự ở đâu?

Nếu mọi customer cùng phụ thuộc một quota instance type ở region, “có thể autoscale” không đồng nghĩa còn quota. Dự phòng có thể cần:
- Quota được duyệt trước.
- Capacity reservation/commitment theo khả năng provider.
- Instance family thay thế đã benchmark.
- Node pool ở nhiều AZ.
- Image/package đã có sẵn ở region.
- Warm connection pool và secret cache.
- DNS/service discovery path đã diễn tập.

## 16. Storage growth và recovery bandwidth

Một miền lỗi có thể làm replica phải rebuild hoặc data phải copy qua network. Capacity cần dành cho recovery traffic, không chỉ user workload.

Ví dụ một replica cần đồng bộ 2 TB dữ liệu sau failover. Đường truyền hiệu dụng 500 MB/s là lý tưởng:

```text
2 TB ≈ 2,000,000 MB (decimal)
Transfer time ≈ 2,000,000 / 500
             = 4,000 seconds
             ≈ 66.7 minutes
```

Thời gian thực tế lớn hơn do apply log, checksum, contention, encryption và traffic người dùng. Nếu recovery bandwidth dùng chung với user traffic, restore có thể kéo dài hoặc làm SLO tệ hơn.

Cần xem xét:
- Snapshot/backup gần region/zone cần phục hồi.
- Replication lag và log retention.
- Throughput cho rebuild/reindex.
- Thứ tự ưu tiên phục hồi dataset.
- Có thể restore theo partition hoặc tenant trước không?
- Có throttling recovery để bảo vệ user traffic không?

## 17. Cost model của dư địa dự phòng

Capacity dự phòng làm tăng chi phí thường ngày, nhưng thiếu capacity có thể gây downtime, queue backlog, mất doanh thu và vi phạm SLA.

Một mô hình so sánh:

```text
Monthly resilience cost =
    baseline active capacity
  + reserved / warm capacity
  + replication and network transfer
  + backup / snapshot / storage
  + monitoring and failover tests
  + operational overhead

Expected incident cost =
    failure probability
  × (downtime impact + data loss impact + recovery cost + SLA credits)
```

Không thể dùng một con số xác suất chung cho mọi failure domain. Ước lượng dựa trên lịch sử, topology và provider evidence; sau đó thực hiện sensitivity analysis với kịch bản xác suất cao hơn.

### 17.1. Cost per unit of resilience

Có thể so sánh thêm:

```text
Incremental resilience cost =
    cost of N+1 design - cost of N-only design

Resilience premium per protected peak unit =
    incremental resilience cost / protected workload capacity
```

Đây là chỉ số quản trị để so các phương án; không thay thế đánh giá hậu quả downtime và correctness.

### 17.2. Tối ưu bằng degraded mode

Nếu không kinh tế để dự phòng full peak cho tất cả workload, có thể định nghĩa capacity sau lỗi theo service tier:
- 100% capacity cho critical transactions.
- 70% cho interactive reads.
- 0–20% cho export/batch và tạm dừng maintenance.
- Cache/replica stale có kiểm soát cho dữ liệu chỉ hiển thị.

Degraded mode phải là quyết định sản phẩm được chấp thuận, có thông báo phù hợp và không vi phạm invariant dữ liệu.

## 18. Autoscaling không thay thế capacity planning

Autoscaling là cơ chế thay đổi số tài nguyên theo metric; capacity planning xác định resource ceiling cần tồn tại và mức tải phải chịu được.

Autoscaler có thể không giúp khi:
- Zone còn lại không còn quota/host capacity.
- Subnet/IP hết địa chỉ.
- Maximum node/instance/pod được cấu hình quá thấp.
- Database không scale cùng compute.
- Scheduler không đặt được pod do volume topology/affinity.
- Metric phát hiện tải trễ hoặc không phản ánh queue age.
- Image pull/initialization kéo dài.
- Region control plane hoặc service quota gặp vấn đề.
- Scale-out làm downstream quá tải.

Hãy thử autoscaling trong kịch bản mất domain, không chỉ lúc tăng traffic trong môi trường khỏe.

## 19. Runbook và điều phối failover

Một runbook failover có thể mô tả:

1. Xác nhận domain thực sự lỗi bằng nhiều tín hiệu; tránh phản ứng chỉ với một health check sai.
2. Kiểm tra quorum/leader và quyền sở hữu dữ liệu.
3. Ngừng hoặc fence workload cũ nếu có nguy cơ split-brain.
4. Chuyển traffic và service discovery tới domain còn sống.
5. Bật warm capacity hoặc scale theo thứ tự ưu tiên.
6. Giảm/tạm dừng background workload nếu cần.
7. Giám sát CPU, DB, network, queue age và SLO trong lúc nhận tải.
8. Kiểm tra data consistency, duplicate và pending transactions.
9. Khi domain phục hồi, catch-up replication, xác minh health và rejoin có kiểm soát.
10. Rebalance traffic trở lại chỉ khi capacity và data state an toàn.

Failback cũng là một sự kiện có tải. Không chuyển traffic 100% về domain vừa phục hồi nếu replica đang catch-up hoặc node chưa warm.

## 20. Observability cho capacity failover

Không chỉ dashboard utilization bình thường; cần dashboard theo từng failure scenario.

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Demand | RPS/workload units, peak, burst | Tải thực tế và tải thiết kế |
| Compute | Usable CPU/memory, throttling, pod pending | Năng lực còn lại |
| Database | Query units, connections, IOPS, lag, failover time | Data tier có chịu được tải không |
| Network | Throughput, packet loss, NAT/firewall utilization | Đường truyền failover |
| Queue | Depth, oldest age, drain rate | Có xử lý backlog trong mục tiêu không |
| Autoscaling | Detection/provision/ready time, quota errors | Scale-out có đủ nhanh không |
| SLO | p95/p99, errors, success rate by operation | Người dùng có được phục vụ không |
| Recovery | Replica catch-up, rebuild time, RTO/RPO | Có thể trở lại đầy đủ không |
| Cost | Idle headroom, reservation, inter-zone transfer | Dư địa dự phòng tốn bao nhiêu |

Tạo metric mô phỏng **remaining capacity ratio**:

```text
Remaining capacity ratio =
    usable capacity after failure / design demand

Ratio >= 1 chỉ là điều kiện sơ bộ nếu chưa trừ headroom và kiểm tra từng resource. Nên báo thêm ratio theo CPU, DB, network, queue và workload critical.

### 20.1. Cảnh báo sớm

- Một AZ có utilization cao hơn các AZ khác bất thường.
- Sau khi giả lập loại một AZ, remaining capacity ratio dưới mục tiêu.
- Node pool/region quota gần giới hạn.
- Database connections hoặc replication lag gần saturation.
- Oldest queue message age tăng nhanh.
- Autoscaling ready time vượt RTO budget.
- Network egress/NAT/firewall gần giới hạn.
- Warm standby drift khỏi baseline version/configuration.

## 21. Kiểm thử và diễn tập N+1

Một bài diễn tập nên chứng minh cả **capacity**, **routing**, **data correctness** và **recovery**.

| Kịch bản | Cách thực hiện | Điều kiện đạt |
| --- | --- | --- |
| Mất một node | Drain/terminate node có kiểm soát | Replica còn lại gánh được tải node mất |
| Mất một AZ | Cô lập traffic hoặc dùng fault injection phù hợp | SLO và workload critical giữ mục tiêu |
| Peak + AZ loss | Tạo design peak rồi cô lập một AZ | Capacity sau lỗi đủ theo budget |
| Retry burst | Giả lập timeout để client retry | Không tạo retry storm |
| Cache cold | Xóa/đổi cache trong failover test | Origin chịu tải hoặc degraded policy hoạt động |
| DB failover | Promote replica theo quy trình | Query/connection capacity và RPO đạt |
| Queue backlog | Dừng consumer một zone rồi phục hồi | Drain time trong recovery objective |
| Network bottleneck | Giới hạn bandwidth/NAT | Không có shared bottleneck phá failover |
| Quota exhaustion | Giới hạn instance/IP/subnet quota | Runbook phát hiện và fallback hoạt động |
| Correlated failure | AZ loss khi đang deploy/backup | Mục tiêu failure combination được chịu |
| Failback | Rejoin domain đã phục hồi | Không split-brain, không quá tải |
| Degraded mode | Chủ động disable best-effort workload | Critical path vẫn đạt SLO |

### 21.1. Đo điều gì trong game day?

- Thời gian phát hiện và xác nhận lỗi.
- Thời gian chuyển traffic.
- Thời gian compute/data plane sẵn sàng.
- p95/p99 và error rate trong toàn sự kiện.
- Queue backlog cực đại và thời gian drain.
- Database connection/query/replication behavior.
- Dữ liệu mất, duplicate hoặc conflict.
- Tổng capacity thực tế còn lại so với dự báo.
- Thời gian failback và rebalance.
- Chi phí phát sinh và sự cố vận hành.

Sau diễn tập, cập nhật capacity model bằng số đo thực tế. Một bài test chỉ thành công nếu đạt tiêu chí được đặt trước, không phải chỉ vì dịch vụ cuối cùng tự hồi phục.

## 22. Quy trình tính capacity dự phòng

1. **Chọn failure domain:** node, AZ, region, cell hoặc shared dependency.
2. **Định nghĩa failure scenarios:** một miền, nhiều miền hoặc correlated failures.
3. **Lập workload profile:** typical, peak, burst, growth và retry amplification.
4. **Xác định criticality/SLO:** workload nào phải giữ 100%, workload nào có thể degrade.
5. **Đo capacity usable:** compute, memory, database, queue, network, storage và quota.
6. **Tính remaining capacity:** loại domain lỗi khỏi tổng; không cộng nhầm các resource khác loại.
7. **Thêm headroom:** định nghĩa rõ theo demand hay theo capacity.
8. **Tính failover demand:** tải reroute, retry, cache cold, reconnect và recovery traffic.
9. **Xác minh time-to-capacity:** static spare, warm, autoscale hoặc cold provision.
10. **Kiểm tra shared dependency:** IAM, DNS, KMS, NAT, broker và control plane.
11. **Đặt degraded/admission policy:** ưu tiên workload critical, bảo vệ dependency.
12. **Test/measure/iterate:** load + fault injection, game day và cập nhật model.

## 23. Tình huống thực hành: API đặt chỗ trên ba AZ

**Bối cảnh:** Một nền tảng booking chạy ở ba AZ. Design peak là 1.200 workload units/s. Workload được quy đổi từ search, booking và payment. Mục tiêu là mất một AZ vẫn phục vụ toàn bộ critical workload với 20% headroom. Mỗi AZ có capacity compute 800 units/s theo benchmark; database có 2.000 query units/s tổng, nhưng khi một AZ mất chỉ còn 1.400 query units/s thực dụng. Payment provider giới hạn 250 calls/s. Cache cold có thể làm DB load tăng 25%. Client retry có thể tăng ingress workload 10% nếu không có backoff tốt.

### 23.1. Tính compute sơ bộ

Nếu tính demand sau retry 10%:

```text
Failover demand = 1,200 × 1.10 = 1,320 units/s
With 20% headroom = 1,320 × 1.20 = 1,584 units/s
Two surviving AZ need 1,584 / 2 = 792 units/s each
```

Mỗi AZ có capacity benchmark 800 units/s nên vừa đủ về compute, nhưng chỉ còn khoảng 8 units/s headroom trên mỗi AZ so với target. Đây là một cấu hình rất sát giới hạn; sai số benchmark hoặc skew nhỏ cũng có thể làm không đạt.

### 23.2. Kiểm tra database

Nếu workload tạo 1.000 query units/s ở mức demand bình thường và cache cold làm tăng 25%, cộng retry 10% theo giả định độc lập:

```text
DB failover demand = 1,000 × 1.25 × 1.10
                   = 1,375 query units/s

With 20% headroom = 1,375 × 1.20
                  = 1,650 query units/s
```

Database surviving capacity chỉ 1.400 query units/s nên không đạt mục tiêu. Tăng compute sẽ không khắc phục được. Có thể giảm cache-cold amplification, tăng database capacity, dùng read replica phù hợp hoặc giảm workload best-effort.

### 23.3. Kiểm tra payment provider

Nếu payment chiếm 220 calls/s trước lỗi, retry không kiểm soát 10% có thể đẩy lên 242 calls/s; cộng headroom 20% cần 290,4 calls/s, vượt provider limit 250. Cần queue/rate cap, retry budget và trạng thái pending/reconciliation để không làm vượt quota hay charge trùng.

### 23.4. Kết luận thiết kế

Compute gần đạt nhưng DB và payment là bottleneck. Phương án nên:
- Tối ưu cache warm-up/replica và workload read.
- Giữ critical booking/payment path có budget riêng.
- Tạm hoãn export/analytics trong AZ failure.
- Điều tiết payment queue dưới provider rate.
- Tăng capacity DB hoặc giảm query units trên mỗi booking.
- Chạy lại test peak + AZ loss, bao gồm cache cold và reconnect.

Không kết luận N+1 đạt chỉ vì tổng vCPU còn lại đủ; tất cả critical dependencies phải đạt cùng lúc.

## 24. ADR mẫu: dự phòng capacity cho một AZ failure

```text
ADR-104: Active-active N+1 cho API booking trên ba AZ

Bối cảnh:
- Design peak 1,200 workload units/s.
- Phải chịu mất một AZ mà vẫn giữ critical workload.
- Database và payment provider có capacity thấp hơn compute.

Lựa chọn:
A. Chạy sát nhu cầu bình thường, dựa vào autoscaling khi lỗi.
B. Giữ đủ static capacity trên ba AZ để hai AZ còn lại xử lý peak + headroom.
C. Giữ compute N+1, giảm best-effort workload và điều tiết dependency khi failover.

Quyết định:
- Chọn C.
- Compute active-active được benchmark và phân tán trên ba AZ.
- Critical workload giữ đầy đủ capacity; export/maintenance có admission control.
- Database có pool/replica budget và kiểm thử cache-cold.
- Payment worker được rate cap theo provider quota.
- Runbook chuyển traffic, drain queue và reconcile pending operations.

Đánh đổi:
- Cần headroom và automation trên mỗi AZ.
- Một số background job chậm lại trong failover.
- Capacity DB/payment cần tối ưu riêng; compute dư không thay thế dependency capacity.

Kiểm chứng:
- Peak + AZ loss test giữ critical SLO.
- DB query/connection và payment quota không vượt.
- Queue age nằm trong recovery objective.
- Failback không tạo duplicate hoặc split-brain.

Điều kiện xem lại:
- Peak workload hoặc traffic mix thay đổi.
- Database/provider quota thay đổi.
- SLO/RTO/RPO thay đổi.
- Game day cho thấy remaining capacity thấp hơn dự báo.
```

## 25. Những sai lầm thường gặp

1. **Đếm số node thay cho capacity:** node dự phòng có thể không đủ throughput.
2. **Sizing theo average:** peak và burst sau failover bị bỏ qua.
3. **Chỉ tính compute:** database, network, queue và provider có thể là bottleneck.
4. **Coi autoscaling là dự phòng tức thời:** provisioning và warm-up mất thời gian, quota có thể không đủ.
5. **Cộng tổng capacity mà bỏ placement:** shard/key/volume có thể không chuyển được.
6. **Bỏ qua retry amplification:** tải tăng đúng lúc capacity giảm.
7. **Không tính cache cold:** origin/database có thể nhận surge lớn.
8. **Đặt quorum đúng nhưng node còn lại quá yếu:** consistency giữ nhưng performance không đạt.
9. **Bỏ qua subnet/IP và network appliance:** không scale được dù còn CPU.
10. **Giả định các AZ hoàn toàn độc lập:** shared dependency hoặc regional failure vẫn có thể đánh sập nhiều zone.
11. **N+1 không định nghĩa X:** không rõ đang chịu một node, AZ hay resource unit.
12. **Không chừa headroom riêng cho database connections:** reconnect storm làm connection exhaustion.
13. **Không kiểm tra failback:** node trở lại làm replication/rebalance quá tải.
14. **Dùng mọi workload cùng priority:** batch có thể chiếm capacity critical.
15. **Tin vào con số lý thuyết:** không benchmark dưới peak và fault injection.
16. **Không thử quota exhaustion:** scale-out có thể thất bại khi cần nhất.
17. **Không tính recovery traffic:** rebuild replica cạnh tranh với user traffic.
18. **Không có runbook/owner:** capacity đúng trên giấy nhưng không kích hoạt được khi sự cố.

## 26. Checklist trước production

- [ ] Failure domain và số lỗi cần chịu được được định nghĩa rõ.
- [ ] Có workload profile typical, design peak, burst và growth.
- [ ] Criticality/SLO và degraded mode đã được sản phẩm chấp thuận.
- [ ] Capacity được tính bằng đơn vị workload/resource đo được.
- [ ] N+1/N+X ghi rõ X và giả định placement.
- [ ] Dùng usable capacity, không chỉ capacity danh định.
- [ ] Headroom được định nghĩa rõ theo demand hoặc theo total capacity.
- [ ] Failover demand tính reroute, retry, reconnect, cache cold và recovery work.
- [ ] Compute/node/IP/quota có thể scale ở miền còn lại.
- [ ] Database connection/query/IOPS/replication capacity đạt sau lỗi.
- [ ] Storage durability, attach/restore và recovery bandwidth đạt yêu cầu.
- [ ] Network/NAT/firewall/load balancer có đủ throughput sau traffic shift.
- [ ] Queue consumer có drain capacity và deadline rõ.
- [ ] Shared dependencies có fallback hoặc capacity độc lập phù hợp.
- [ ] Autoscaling ready time nằm trong RTO budget hoặc có warm capacity.
- [ ] Admission control, retry budget và priority policy được cấu hình.
- [ ] Monitoring có remaining capacity ratio theo từng resource/failure scenario.
- [ ] Đã test peak + AZ/region/cell loss, cache cold, quota và failback.
- [ ] Runbook, owner, rollback và game-day cadence được xác định.
- [ ] Cost model bao gồm idle headroom, replication, network và operation.

---

**Ghi nhớ:** Dự phòng N+1 có ý nghĩa khi phần hạ tầng còn lại thực sự xử lý được design peak, headroom và tải phát sinh do failover. Phải tính theo từng resource và dependency, xét placement, autoscaling delay, quorum, queue, network và recovery traffic. Chỉ benchmark và diễn tập mất miền lỗi mới xác nhận được con số dự phòng trên giấy có chuyển thành SLO thực tế hay không.
