# Tối ưu mức sử dụng tài nguyên và tác động môi trường

## Mục tiêu học tập

Cloud giúp cấp phát compute, storage và network theo nhu cầu, nhưng khả năng mở rộng nhanh cũng khiến tài nguyên dư thừa dễ tích lũy. Một cluster chạy ở mức sử dụng thấp trong phần lớn thời gian, database được cấp cấu hình quá lớn, log được giữ vô thời hạn hoặc dữ liệu được sao chép nhiều vùng mà không có nhu cầu rõ ràng đều làm tăng chi phí và tiêu thụ năng lượng. Ngược lại, cắt giảm quá mạnh có thể làm tăng latency, tạo lỗi khi tải cao, giảm khả năng phục hồi hoặc vi phạm yêu cầu lưu trữ dữ liệu.

**Tối ưu mức sử dụng tài nguyên** là quá trình đưa capacity, cấu hình và cách vận hành gần hơn với nhu cầu thực tế trong khi vẫn đáp ứng mục tiêu dịch vụ. **Tính bền vững môi trường** xem xét năng lượng, phát thải, nước làm mát, vật liệu và vòng đời phần cứng liên quan đến workload. Hai mục tiêu thường có vùng giao nhau: giảm tài nguyên nhàn rỗi, hạn chế xử lý lặp, tăng hiệu quả lưu trữ và giảm truyền dữ liệu có thể vừa giảm chi phí vừa giảm tác động môi trường. Tuy nhiên, chi phí cloud và phát thải không phải lúc nào cũng tỷ lệ thuận; cần đo thay vì suy luận từ hóa đơn.

Bài học này trình bày cách đo và tối ưu utilization trên compute, database, storage, data platform và network; thiết kế autoscaling, scheduling, rightsizing, lifecycle và workload placement; đồng thời đưa ra cách xây dựng FinOps practice và đánh giá tác động môi trường một cách có căn cứ. Nội dung đặt các quyết định vào bối cảnh Cloud Architecture từ yêu cầu nghiệp vụ tới network, compute, data và deployment model, với trọng tâm là đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt utilization, saturation, efficiency, capacity headroom và unit economics.
- Xác định baseline workload theo tải trung bình, peak, seasonality và burst.
- Rightsize VM, container, database, serverless và managed services bằng telemetry.
- Thiết kế autoscaling, scale-to-zero và schedule theo nhu cầu mà không làm hỏng SLO.
- Tối ưu storage tier, retention, replication, snapshots, backup và data lifecycle.
- Giảm chi phí network/egress bằng placement, caching và giảm truyền dữ liệu dư thừa.
- Tối ưu data pipeline để giảm full scan, duplicate processing và small files.
- Xây cost allocation, tagging, budgets, anomaly detection và unit cost theo product/tenant.
- Phân biệt chi phí cloud, năng lượng tiêu thụ và phát thải carbon; hiểu giới hạn của dữ liệu ước tính.
- Xem xét carbon intensity, location, timing và hardware lifecycle khi đặt workload.
- Đưa tiêu chí sustainability vào architecture review, procurement và vận hành.
- Xây dựng thử nghiệm tối ưu có giả thuyết, guardrail, đo trước/sau và rollback.

## 1. Vì sao utilization và sustainability cần được thiết kế cùng nhau?

Một kiến trúc cloud có thể mở rộng rất tốt nhưng không hiệu quả. Ví dụ, một nhóm giữ 40 node compute chạy liên tục để phục vụ peak chỉ xuất hiện hai giờ mỗi ngày. Hệ thống có nhiều headroom, nhưng phần lớn capacity đang nhàn rỗi. Một nhóm khác chạy batch analytics full scan toàn bộ data lake mỗi giờ dù chỉ có vài partition thay đổi. Chi phí compute tăng, storage/network I/O tăng và workload tạo thêm năng lượng tiêu thụ.

Tối ưu không đơn giản là đẩy CPU lên 90% hoặc giảm số máy càng nhiều càng tốt. CPU utilization cao kéo dài có thể làm tail latency tăng, autoscaling không kịp hoặc mất khả năng chịu lỗi. Một cụm database cần capacity dư để failover; một workload tuân thủ RTO/RPO có thể phải duy trì replica/backup; một hệ thống regulated không thể chuyển dữ liệu tùy tiện sang region rẻ hơn.

Mục tiêu là tìm mức sử dụng phù hợp với **workload demand và service objectives**, đồng thời tránh lãng phí không tạo giá trị.

### 1.1. Ba câu hỏi khi tối ưu

1. **Tài nguyên có được dùng hiệu quả không?** Capacity có tương xứng với workload, có xử lý dư thừa, idle hoặc duplicate không?
2. **Dịch vụ còn đáp ứng yêu cầu không?** Latency, throughput, availability, durability, RTO/RPO và security có được giữ?
3. **Tác động môi trường thay đổi thế nào?** Có giảm energy/emissions hoặc tài nguyên vật lý cần thiết không, và dữ liệu đo có đủ tin cậy?

### 1.2. Cost optimization và sustainability có liên quan nhưng khác nhau

| Khía cạnh | Cost optimization | Environmental sustainability |
| --- | --- | --- |
| Đơn vị quan sát | Tiền tệ, cost/unit, budget | Năng lượng, carbon, nước, vật liệu, vòng đời |
| Driver | Usage, pricing, commitment, license, egress | Workload energy, location, grid mix, cooling, hardware |
| Tác động | Hóa đơn và unit economics | Phát thải và tiêu thụ tài nguyên môi trường |
| Tối ưu thường gặp | Rightsizing, schedule, commitment, storage tier | Giảm xử lý dư, tăng utilization, location/time awareness |
| Rủi ro khi làm sai | Overprovision hoặc chi phí cao | Phát thải/tiêu thụ lớn hoặc chuyển gánh nặng sang nơi khác |

Một workload rẻ hơn có thể tạo phát thải cao hơn nếu chuyển sang phần cứng/region có cường độ carbon cao hoặc phát sinh truyền dữ liệu lớn. Một workload phát thải thấp hơn có thể đắt hơn do chọn năng lượng sạch, region khác hoặc cấu hình có dự phòng. Cần đo và công bố mục tiêu riêng, không thay thế metric môi trường bằng số tiền tiết kiệm.

## 2. Đo workload trước khi tối ưu

Tối ưu khi chưa có baseline thường dẫn tới thay đổi dựa trên cảm giác. Trước tiên cần thu thập workload profile theo thời gian đủ dài để bao quát peak, batch cycle, ngày trong tuần, mùa vụ và campaign.

### 2.1. Những tín hiệu cần thu thập

| Nhóm | Metrics | Ý nghĩa |
| --- | --- | --- |
| Compute | CPU, memory working set, throttling, run queue, CPU time | Mức tiêu thụ compute và dấu hiệu thiếu capacity |
| Application | Request rate, concurrency, latency p50/p95/p99, error rate | Demand và trải nghiệm người dùng |
| Container | Requests/limits, restart, OOMKill, pending pods | Cấu hình và scheduling capacity |
| Database | CPU, memory, connections, IOPS, locks, query latency | Tải transaction và contention |
| Storage | Logical/physical bytes, IOPS, throughput, object count | Dung lượng và workload access |
| Network | Ingress/egress bytes, cross-zone/region traffic, packet rate | Chi phí và network demand |
| Queue/stream | Backlog, oldest message age, throughput, consumer lag | Khả năng xử lý burst và batch |
| Reliability | Availability, error budget, failover margin, RTO/RPO | Headroom cần duy trì |
| Cost | Spend by service/account/tag, unit cost, commitments | Tiền gắn với workload |
| Environment | Energy/carbon estimates where available | Tác động môi trường có thể đo/ước tính |

Chỉ số trung bình không đủ. CPU trung bình 25% có thể che một spike 100% ngắn làm request timeout. Memory utilization thấp nhưng working set có thể tăng theo cache warm-up. Cần percentile, maximum, duration above threshold và correlation với SLO.

### 2.2. Utilization, saturation và efficiency

- **Utilization:** tỷ lệ tài nguyên đang được sử dụng so với capacity có sẵn.
- **Saturation:** mức độ tài nguyên không còn đáp ứng thêm demand, thường thể hiện qua queue, throttling, wait time hoặc contention.
- **Efficiency:** lượng output có ích trên một đơn vị tài nguyên/chi phí.
- **Headroom:** capacity dự phòng để chịu burst, failover hoặc tăng trưởng.
- **Waste:** tài nguyên đã trả tiền/được cấp nhưng không tạo giá trị tương xứng.

Một CPU ở 70% chưa chắc bão hòa; nếu queue tăng và latency p99 xấu đi, hệ thống có thể đã bị saturation ở một dependency khác. Một service ở 15% CPU có thể vẫn cần headroom vì workload cần phản hồi trong vài trăm millisecond khi burst.

### 2.3. Xác định unit of work

Muốn so sánh hiệu quả, phải chọn output có ý nghĩa:
- Cost per successful booking.
- Compute seconds per million events.
- GB scanned per report.
- Storage GB-month per active tenant.
- kWh hoặc kgCO2e per thousand transactions nếu có dữ liệu đủ tin cậy.
- Cost per API request class hoặc per business outcome.

Không so cost giữa hai tháng nếu volume, mix, region, data retention hoặc SLO thay đổi mà không normalize.

## 3. Capacity planning và headroom

Capacity planning xác định tài nguyên cần thiết trong điều kiện thông thường và bất thường. Headroom không phải lãng phí hoàn toàn; một phần là chi phí mua resilience và performance.

### 3.1. Demand profile

Phân tích:
- Average load.
- Peak and percentile load.
- Burst duration/frequency.
- Seasonality.
- Growth forecast.
- Batch window.
- Failover/recovery demand.
- Deployment surge và rolling upgrade overhead.

Với queue-based workload, throughput cần đủ xử lý incoming rate cộng backlog drain. Nếu event đến 500/s và worker xử lý 600/s, dư địa chỉ 100/s; backlog lớn cần tính thời gian drain chứ không chỉ nhìn current throughput.

### 3.2. Headroom theo SLO và failure scenario

Một hệ thống multi-AZ không thể luôn chạy mỗi zone ở 95% utilization nếu một zone failure sẽ dồn toàn bộ traffic sang hai zone còn lại. Capacity cần tính cho failure mode đã cam kết.

~~~text
Required surviving capacity
  >= Peak demand after failure
     + Recovery/replay overhead
     + Safe operating headroom
~~~

Đây là nguyên tắc lập kế hoạch, không phải công thức sizing đầy đủ. Cần mô phỏng traffic distribution, autoscaling delay, dependency quota và data replication.

### 3.3. Right-size không đồng nghĩa giảm đều

Rightsizing có thể:
- Giảm VM size nếu CPU/memory headroom dư và SLO vẫn đạt.
- Tăng memory thay CPU nếu workload memory-bound.
- Chuyển workload sang compute family phù hợp.
- Tách service để không cấp cùng một size cho workload khác nhau.
- Điều chỉnh container requests/limits.
- Dùng managed/serverless service khi workload phù hợp.
- Giảm capacity dự phòng bằng autoscaling có kiểm chứng.

Không giảm instance chỉ vì average CPU thấp. Cần xem memory, I/O, network, burst, noisy neighbor và failover.

## 4. Rightsizing compute

### 4.1. Virtual machines

Theo dõi CPU, memory, disk I/O, network, process count và runtime profile. Chọn instance family theo workload:
- Compute optimized cho xử lý CPU-bound.
- Memory optimized cho cache/in-memory database.
- General purpose cho workload cân bằng.
- Storage/I/O optimized cho workload có throughput cao.

Đánh giá cả licensing, network bandwidth, local disk behavior, burst credit và availability. Một instance nhỏ hơn có thể rẻ hơn theo giờ nhưng cần nhiều instance hơn hoặc tăng network hops.

### 4.2. Container requests và limits

Kubernetes scheduling dựa trên resource requests; CPU/memory limits tác động tới runtime behavior. Requests quá cao làm cluster scale sớm và node utilization thấp. Requests quá thấp có thể gây scheduling overcommit, CPU contention hoặc OOM.

Ví dụ deployment minh họa:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "2"
    memory: "1Gi"
~~~

Giá trị phải dựa trên telemetry và load test. Memory limit có thể dẫn tới OOMKill nếu working set vượt ngưỡng; CPU limit có thể throttle workload dù node còn CPU. Cần xem throttling metrics và latency, không chỉ dashboard utilization.

### 4.3. Bin packing và cluster utilization

Scheduler có thể đặt workload lên node để tăng utilization. Nhưng bin packing quá chặt làm giảm khả năng chịu pod failure, tăng noisy-neighbor và tạo rebalancing khi deploy. Cần phối hợp:
- Pod topology spread/anti-affinity.
- Node pool theo workload class.
- Requests chính xác.
- Cluster autoscaler.
- Pod disruption budget.
- Capacity buffer cho rollout và failover.

### 4.4. Compute family và kiến trúc processor

Chuyển sang instance family/processor hiệu quả hơn có thể giảm cost/compute và energy per task, nhưng cần benchmark ứng dụng, native dependency, license, architecture compatibility, memory bandwidth và network performance. Không giả định CPU mới tiết kiệm hơn cho mọi workload nếu task bị giới hạn I/O hoặc lock.

## 5. Autoscaling, scheduling và scale-to-zero

Autoscaling đưa capacity gần với demand, giảm idle resource nhưng tạo thêm độ trễ khi scale-out và nguy cơ scale-in quá sớm.

### 5.1. Horizontal và vertical scaling

- **Horizontal scaling:** thêm/bớt instance/pod/worker.
- **Vertical scaling:** tăng/giảm resource của instance.
- **Scheduled scaling:** thay capacity theo lịch biết trước.
- **Event-driven scaling:** dựa queue depth, request rate hoặc custom metric.
- **Predictive scaling:** dự báo demand tương lai nếu có pattern đủ ổn định.

Horizontal scaling thường cần ứng dụng stateless hoặc state externalized. Vertical scaling có thể cần restart/recreate và giới hạn trần.

### 5.2. Chọn scaling signal

CPU không phải lúc nào cũng là tín hiệu tốt. Worker queue nên scale theo backlog/oldest age; API có thể theo request concurrency/latency; database cần xem connections, IOPS và query queue; storage có thể cần scale capacity theo throughput.

Autoscaling theo metric quá nhiễu có thể oscillate. Cần smoothing, stabilization window, cooldown, min/max và scale policy phù hợp.

### 5.3. Ví dụ HPA

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: booking-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: booking-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

Ví dụ minh họa. Cần đo thời gian khởi động pod, warm-up cache, quota node, readiness và latency trong lúc scale. Min replicas phải đủ cho failure/availability target; scaleDown stabilization giúp tránh giảm capacity quá sớm nhưng không thay thế load test.

### 5.4. Scheduled scaling và môi trường non-production

Development, test, demo hoặc batch environments có thể chạy theo lịch và scale-to-zero khi không cần. Cần xác định:
- Giờ hoạt động và timezone.
- Ai có quyền bật lại.
- Trạng thái persistent data.
- Job/backup chạy ngoài giờ.
- Thời gian cold start.
- Cost của standby/network/IP/storage còn tồn tại.

Không tắt database hoặc service chỉ dựa vào lịch nếu có consumer, integration hoặc backup cần chạy.

### 5.5. Scale-to-zero

Scale-to-zero hữu ích cho workload hiếm dùng như dev preview, function/event consumer hoặc batch job. Đánh đổi là cold start, connection establishment, cache warm-up và khả năng đáp ứng burst đầu tiên. Với API có SLO latency nghiêm ngặt, giữ minimum capacity có thể hợp lý hơn.

## 6. Database và managed services

Database thường có chi phí và rủi ro cao vì vừa phục vụ transaction vừa giữ state.

Tối ưu:
- Rightsize compute dựa CPU, memory, cache hit, IOPS và query profile.
- Tối ưu query/index trước khi tăng instance size.
- Tách read workload sang replica/warehouse khi phù hợp.
- Pool connection và giới hạn concurrency.
- Dùng storage autoscaling có ngưỡng và alert.
- Chọn backup/retention theo RPO/RTO và compliance.
- Xem license/capacity charge và minimum managed-service tier.
- Đo idle connections, slow queries và lock contention.

### 6.1. Tách cost do storage và compute

Một số dịch vụ tính storage, I/O và compute riêng; scale compute xuống không nhất thiết giảm storage cost. Snapshot, backup, log và replica có thể tạo storage tăng theo thời gian.

### 6.2. Replica không phải resource miễn phí

Read replica cải thiện read capacity hoặc DR nhưng dùng compute/storage/network và có replication overhead. Xác định:
- Replica phục vụ query hay recovery?
- Có cần ở nhiều region?
- Replication lag acceptable không?
- Read routing có hiệu quả?
- Backup/retention có bị nhân lên?
- Test failover có đo được khả năng promote?

Không xóa replica chỉ vì CPU thấp nếu nó là thành phần của RTO/RPO.

## 7. Storage lifecycle và data efficiency

Data thường tiếp tục tăng ngay cả khi workload không tăng. Thiết kế retention và lifecycle ngay từ đầu có thể giảm storage footprint, backup cost và data processing.

### 7.1. Phân tầng storage

| Tier | Access pattern | Mục đích |
| --- | --- | --- |
| Hot | Truy cập thường xuyên, latency thấp | Database, active objects |
| Warm | Truy cập thỉnh thoảng | Historical reports, recent logs |
| Cold/archive | Truy cập hiếm, chấp nhận retrieval delay | Long-term retention, compliance archive |
| Ephemeral | Tạm thời, có TTL | Scratch files, test artifacts, cache |

Các tier cụ thể và phí retrieval phụ thuộc provider. Trước khi chuyển archive, kiểm tra restore latency, minimum storage duration, early deletion fee, replication, object size và legal hold.

### 7.2. Retention policy

Chia theo loại dữ liệu:
- Operational logs.
- Audit/security logs.
- Business transaction records.
- Application metrics/traces.
- Backups/snapshots.
- Temporary artifacts.
- Analytics intermediate data.

Retention phải đáp ứng privacy, legal, audit và business need. Giữ mọi log vô hạn không chỉ tốn tiền mà còn tăng rủi ro dữ liệu; xóa quá sớm có thể phá điều tra hoặc vi phạm yêu cầu lưu trữ.

### 7.3. Data minimization và compression

Giảm dữ liệu cần lưu/truyền:
- Chỉ giữ field cần thiết.
- Loại duplicate và temporary copy.
- Dùng columnar format cho analytical workload.
- Compression phù hợp với CPU/latency trade-off.
- Partition hợp lý để query không scan thừa.
- Compact small files.
- Dùng incremental processing thay full reload.
- Tránh log payload chứa PII/secret.
- Retire dataset không còn consumer sau approval.

Compression giảm byte lưu/truyền nhưng tăng CPU. Chọn codec và level qua benchmark, đặc biệt với latency-sensitive path.

### 7.4. Backup và snapshot

Backup là yêu cầu reliability/security, nhưng nhiều snapshot không có policy có thể chiếm storage đáng kể. Quản lý:
- Backup frequency và retention theo criticality.
- Cross-region copy chỉ khi cần RPO/DR.
- Immutable backup khi cần ransomware protection.
- Expiration và legal hold.
- Restore verification.
- Backup catalog và owner.
- Xóa snapshot orphan sau khi xác minh không còn phụ thuộc.

Không giảm backup chỉ để giảm cost nếu làm RPO/RTO hoặc compliance không đạt.

## 8. Data platform và analytics efficiency

Data pipeline có thể tiêu thụ compute lớn vì full scan, reprocessing, duplicate jobs hoặc dữ liệu layout kém.

### 8.1. Incremental thay vì full refresh

Nếu chỉ 1% dữ liệu thay đổi, pipeline có thể xử lý phần delta với change data capture, watermark hoặc partition update. Cần bảo đảm late data, correction và backfill vẫn đúng.

### 8.2. Query efficiency

- Chọn partition theo filter workload thực.
- Column pruning và predicate pushdown.
- Dùng materialized view/aggregate cho query lặp lại.
- Tránh SELECT * khi không cần.
- Giới hạn query scan và concurrency.
- Tối ưu join key/cardinality.
- Cache kết quả có freshness contract.
- Tách exploratory query khỏi critical serving path.

### 8.3. Orchestration và scheduling

Job batch không cần chạy mỗi phút nếu nghiệp vụ chỉ cần dữ liệu hàng giờ. Gộp job nhỏ hoặc event-driven theo nhu cầu giúp giảm startup overhead. Tuy vậy, batching quá lớn có thể tăng latency và peak memory; chọn interval theo freshness SLO.

### 8.4. Lifecycle của data product

Dataset cần owner, consumer, freshness, retention, classification và cost owner. Dữ liệu không còn consumer cần được deprecate có thông báo, backup/retention check và approval trước khi xóa.

## 9. Network efficiency và data transfer

Network cost và environmental impact tăng khi dữ liệu di chuyển nhiều giữa AZ, region, cloud provider hoặc Internet.

Biện pháp:
- Đặt compute gần dữ liệu theo latency, residency và cost.
- Cache content gần consumer.
- Dùng private endpoint hoặc service endpoint nếu phù hợp semantics/pricing.
- Giảm cross-region query hoặc replication dư thừa.
- Batch request nhỏ khi latency/consistency cho phép.
- Nén payload có benchmark.
- Tránh gửi lại object/file không thay đổi.
- Dùng CDN cho static content.
- Theo dõi NAT, egress, inter-zone và inter-region traffic.

Không chuyển workload về cùng AZ chỉ để giảm transfer cost nếu làm mất khả năng chịu zone failure hoặc vi phạm isolation. Network topology cần được đánh giá cả security và resilience.

## 10. Observability cho cost và utilization

Tối ưu cần dữ liệu liên kết được resource, workload, team, tenant và business outcome.

### 10.1. Allocation tags và hierarchy

Các dimension hữu ích:
- Account/project/subscription.
- Environment.
- Service/product/domain.
- Owner team.
- Cost center.
- Tenant hoặc customer group nếu policy cho phép.
- Data classification.
- Region.
- Workload criticality.

Tag cần có taxonomy, validation và coverage. Với shared infrastructure không thể gắn cost trực tiếp, dùng cost allocation driver và hiển thị shared overhead.

### 10.2. FinOps metrics

| Metric | Câu hỏi |
| --- | --- |
| Total spend by service | Tiền đang đi đâu? |
| Idle/unused resource cost | Chi phí nào không tạo workload value? |
| Utilization distribution | Capacity có phù hợp với demand? |
| Cost per transaction | Mỗi business outcome tốn bao nhiêu? |
| Cost per tenant | Tenant nào có cost to serve cao? |
| Cost per GB/query | Data platform hiệu quả thế nào? |
| Commitment utilization | Reserved/committed capacity có được dùng? |
| Egress cost | Dữ liệu đang đi đâu? |
| Forecast variance | Actual lệch dự báo bao nhiêu? |
| Unit cost trend | Hiệu quả có cải thiện theo thời gian? |

### 10.3. Cost anomaly

Cảnh báo khi:
- Một service spend tăng nhanh so baseline.
- Egress bất thường sau deployment.
- Resource mới tạo nhưng không tag/owner.
- Storage tăng ngoài growth forecast.
- Autoscaling vượt max/commitment.
- Query scan hoặc log ingestion tăng đột biến.
- Commitment utilization thấp.
- Cost per successful transaction xấu đi.

Anomaly cần được phân loại theo volume, pricing change, deployment, campaign và incident; không tắt tài nguyên chỉ vì cost tăng nếu chưa hiểu business impact.

## 11. FinOps: quy trình cộng tác liên tục

FinOps kết nối engineering, finance, product và operations để đưa quyết định chi phí vào vòng đời workload. Không chỉ là nhóm finance cắt ngân sách; engineering cần hiểu cost driver và product cần hiểu unit economics.

### 11.1. Vòng lặp FinOps

~~~mermaid
flowchart LR
    OBS["Measure usage and spend"] --> ATTR["Allocate and explain"]
    ATTR --> OPT["Prioritize optimization"]
    OPT --> CHANGE["Implement with guardrails"]
    CHANGE --> VERIFY["Measure impact"]
    VERIFY --> OBS
~~~

Các hoạt động:
- Inform: inventory, allocation, dashboards và forecast.
- Optimize: rightsizing, scheduling, pricing, architecture changes.
- Operate: policy, budget, ownership, cadence và accountability.

### 11.2. Unit economics

Ví dụ cost per successful booking:

~~~text
Cost per successful booking
  = Total attributable platform cost
    / Number of successful bookings
~~~

Nếu spend tăng 10% nhưng booking tăng 30%, unit cost có thể giảm. Nếu spend giảm 10% nhưng error rate tăng và booking giảm 25%, tối ưu có thể làm business kém hơn.

Tính mẫu số cẩn thận: successful booking, active tenant, monthly active user hay report run phải có định nghĩa ổn định.

### 11.3. Budget và forecast

Budget nên liên kết growth forecast, seasonality, commitment, launch plan và risk buffer. Cảnh báo có thể theo forecasted month-end spend thay vì chỉ actual-to-date. Với workload tăng đột biến, cần escalation thay vì tự động scale down làm vi phạm SLO.

### 11.4. Commitment và discount

Reserved capacity/savings commitment có thể giảm đơn giá nhưng tạo obligation nếu usage giảm. Trước khi commit:
- Phân tích baseline và forecast.
- Xác định phần workload ổn định.
- Xem flexibility về family/region/service.
- Đánh giá utilization và expiry.
- Không mua commitment chỉ để đạt discount headline.
- Theo dõi unused commitment.

Commitment không làm giảm resource consumption tự thân; nó thay đổi pricing. Không dùng discount như bằng chứng sustainability.

## 12. Đo tác động môi trường

Tác động môi trường của cloud workload có thể gồm:
- Electricity used by compute, memory, storage và network.
- Data center cooling và water use.
- Carbon intensity của electricity grid.
- Manufacturing/embodied emissions của server, storage, network equipment.
- Vòng đời thiết bị, reuse, refurbishment và recycling.
- E-waste và vật liệu.
- Data transfer và nguồn năng lượng tại nơi xử lý.

Khách hàng cloud thường không trực tiếp đo điện năng tại server vật lý. Họ có thể dùng dữ liệu carbon/energy do provider cung cấp, model ước tính hoặc báo cáo môi trường đã công bố. Cần ghi rõ phạm vi, phương pháp, thời gian và mức độ ước tính.

### 12.1. Operational và embodied emissions

- **Operational emissions:** phát sinh từ vận hành workload/data center, thường gắn với điện năng và năng lượng làm mát.
- **Embodied emissions:** phát sinh trong khai thác nguyên liệu, sản xuất, vận chuyển, bảo trì và xử lý thiết bị.

Một instance cloud không chỉ tiêu thụ điện trong lúc chạy; phần cứng cũng có footprint sản xuất. Tăng utilization có thể giúp dùng hiệu quả phần cứng đã tồn tại, nhưng không thể kết luận một cách chính xác embodied emissions được chia theo workload nếu provider không công bố phương pháp phân bổ.

### 12.2. Carbon intensity và location

Cùng một lượng điện có thể có emissions khác nhau tùy grid mix và thời điểm. Khi workload linh hoạt, có thể xem xét location/time có carbon intensity thấp hơn, nhưng cần cân nhắc:
- Data residency và sovereignty.
- Latency tới user và dependency.
- Cross-region transfer.
- Availability/DR.
- KMS/identity/control-plane dependencies.
- Pricing, quota và service availability.
- Provider carbon methodology.

Không di chuyển dữ liệu restricted qua region khác chỉ để tối ưu một chỉ số carbon. Compliance và security là constraints trước khi tính carbon-aware placement.

### 12.3. Carbon-aware scheduling

Batch workload có deadline linh hoạt có thể được xếp lịch trong cửa sổ có năng lượng/carbon intensity phù hợp hơn, nếu có dữ liệu và cơ chế scheduling. Không áp dụng cho real-time transaction hoặc job có deadline cứng. Cần đánh giá việc chờ đợi có làm tăng backlog, tăng latency hay phải chạy capacity lâu hơn không.

### 12.4. Water và tài nguyên vật lý

Data center dùng hệ thống làm mát và hạ tầng điện. Một số provider báo cáo water usage hoặc water-related metrics theo vùng/phương pháp riêng. Không nên so sánh trực tiếp hai con số nếu ranh giới đo khác nhau. Workload placement có thể xem water stress và provider disclosure khi có dữ liệu đủ tin cậy, song không được suy luận chỉ từ địa chỉ region.

## 13. Carbon/energy efficiency trong kiến trúc ứng dụng

Các cải tiến có thể giảm công việc phải thực hiện:
- Xử lý incremental thay vì lặp lại toàn bộ dataset.
- Cache kết quả có thể tái sử dụng.
- Tránh polling quá thường xuyên.
- Chọn batch interval theo freshness need.
- Nén dữ liệu có lợi về tổng CPU/network/storage.
- Giảm log noise và trace sampling hợp lý.
- Loại bỏ retry storm và request trùng.
- Tối ưu query và algorithm complexity.
- Dùng autoscaling/scheduling để giảm idle capacity.
- Tắt môi trường không dùng.
- Retire data/object/resource không còn mục đích.
- Tái sử dụng hardware/platform managed khi workload phù hợp.

### 13.1. Efficiency theo business outcome

Tăng CPU utilization không phải mục tiêu cuối. Tốt hơn là hoàn thành cùng số giao dịch với ít compute time hơn mà vẫn giữ latency và correctness. Với batch job, đo energy/cost per record hoặc per completed job; với API, đo cost per successful request và emissions estimate per business transaction nếu có dữ liệu.

### 13.2. Algorithm và data structure

Một query hoặc thuật toán tốt hơn có thể giảm CPU, memory và I/O nhiều hơn việc chuyển sang instance rẻ. Tối ưu algorithm cần benchmark input thực tế và đánh giá correctness. Cache có thể giảm compute nhưng tạo storage, invalidation và staleness complexity; lợi ích phải đo trên cả lifecycle.

## 14. Tối ưu theo workload pattern

| Workload | Cơ hội tối ưu | Guardrail |
| --- | --- | --- |
| Stateless API | HPA, rightsizing, cache, request limits | p95/p99, error rate, failover headroom |
| Batch analytics | Incremental, schedule, partition pruning | Freshness SLA, late data, completion deadline |
| Queue workers | Scale theo backlog/oldest age | Queue age, retry, consumer recovery |
| Database | Query/index tuning, rightsizing, pooling | Transaction latency, connection budget, RPO |
| ML/AI inference | Batch/continuous batching, accelerator utilization | Model latency, quality, data privacy |
| Development/test | Schedule, ephemeral env, scale-to-zero | Test availability, persistent data, CI deadline |
| Static delivery | CDN/cache/compression | Freshness, security, egress placement |
| Long-term archive | Lifecycle tiering, retention | Restore time, legal hold, retrieval charge |

### 14.1. AI/accelerator workload

Accelerator đắt và tiêu thụ năng lượng đáng kể. Tối ưu có thể gồm batching, model quantization, right accelerator, utilization monitoring, autoscaling theo queue và model-serving efficiency. Tuy vậy, batching lớn có thể tăng latency; quantization có thể giảm quality; scale-to-zero có thể gây cold start. Đo quality/latency/cost cùng nhau.

### 14.2. Multi-tenant workload

Phân bổ capacity theo tenant/tier, weighted fairness và quota giúp tăng utilization mà vẫn tránh noisy-neighbor. Cần đo cost per tenant và không ép tenant dùng capacity thấp đến mức vi phạm SLA/contract.

## 15. Architecture trade-offs: không tối ưu một metric riêng lẻ

Tối ưu cost/utilization có thể tác động trực tiếp tới reliability, security và performance.

| Thay đổi | Lợi ích có thể có | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Giảm instance size | Cost/energy per hour thấp hơn | CPU throttling, memory pressure, latency |
| Giảm số replica | Ít compute nhàn rỗi | Failover capacity và rollout |
| Scale-to-zero | Giảm idle cost | Cold start và first-request latency |
| Giảm backup retention | Giảm storage cost | RPO, compliance và recovery |
| Giảm replication region | Giảm transfer/storage | DR và data durability |
| Chọn region khác | Pricing/carbon khác | Residency, latency, grid data, availability |
| Tăng compression | Giảm storage/network | CPU overhead và decompression latency |
| Tăng batch interval | Ít startup/overhead | Freshness và peak resource demand |
| Tăng utilization target | Bin packing tốt hơn | Saturation, noisy-neighbor, failure margin |

Không đưa optimization vào production nếu chưa xác định guardrail và rollback trigger.

## 16. Quy trình tối ưu có kiểm soát

~~~mermaid
flowchart TD
    BASE["Baseline: SLO, usage, cost, environment"] --> HYP["Form a measurable hypothesis"]
    HYP --> DESIGN["Design change and guardrails"]
    DESIGN --> TEST["Benchmark / staging / canary"]
    TEST --> DEC{"SLO and correctness pass?"}
    DEC -->|No| ROLL["Rollback / revise"]
    DEC -->|Yes| PROD["Progressive production rollout"]
    PROD --> MEASURE["Measure cost, utilization, impact"]
    MEASURE --> REVIEW["Review and record decision"]
    REVIEW --> BASE
~~~

Các bước:

1. Chọn workload/service có spend hoặc waste đáng kể.
2. Xác định owner và business outcome.
3. Thu baseline đủ đại diện.
4. Phân tích cost driver và bottleneck.
5. Đưa giả thuyết có thể đo.
6. Xác định guardrail về SLO, security, resilience, data và environment.
7. Test bằng benchmark/staging/canary.
8. Rollout theo batch/percentage.
9. Đo trước/sau đã normalize workload mix.
10. Ghi kết quả, cost impact, environmental impact estimate và residual risk.
11. Giám sát sau thay đổi và rollback khi guardrail breach.
12. Chuẩn hóa cấu hình mới vào IaC/policy.

### 16.1. Ví dụ giả thuyết

“Giảm request CPU của booking worker từ 1 vCPU xuống 700m dựa trên p95 CPU usage 35% trong 30 ngày, nhưng chỉ rollout 10% trước. Chấp nhận thay đổi khi queue oldest age, job duration p95, error rate và recovery throughput đều không xấu hơn guardrail; sau đó so sánh cost per completed job.”

Giả thuyết phải nêu rõ workload, dữ liệu baseline, exposure và điều kiện rollback.

## 17. Cost governance và trách nhiệm vận hành

Một chương trình tối ưu thất bại nếu chỉ chạy một lần rồi không ai duy trì.

Cần:
- Service owner chịu trách nhiệm unit cost và SLO.
- Platform team cung cấp capacity/usage tooling.
- Finance/FinOps quản lý allocation, commitment và forecast.
- Security/compliance xác định retention, region và control.
- Product/business xác định MBCO, demand và value.
- Sustainability owner xác định method, target và reporting boundary.

### 17.1. FinOps review cadence

Một nhịp review có thể gồm:
- Hàng tuần: anomaly, unusual spend, failed optimization.
- Hàng tháng: service cost, unit economics, idle resources, forecast.
- Hàng quý: architecture review, commitments, storage lifecycle, region/placement.
- Khi có release lớn: cost impact review và budget guardrail.
- Khi thay đổi workload: rebaseline và kiểm tra capacity.

Tần suất phải phù hợp tốc độ thay đổi và quy mô. Không biến mọi team thành người làm báo cáo thủ công; tự động hóa cost ownership và anomaly detection khi có thể.

### 17.2. Architecture Decision Record (ADR)

ADR về tối ưu nên ghi:
- Vấn đề và business context.
- Baseline metrics.
- Các phương án.
- Cost/utilization/environment estimates và phương pháp.
- SLO/security/compliance constraints.
- Quyết định và lý do.
- Rollout/rollback.
- Owner, review date và evidence.
- Điều kiện đánh giá lại.

## 18. Case study: tối ưu nền tảng booking đa vùng

### 18.1. Bối cảnh

Một nền tảng booking chạy API trên Kubernetes, PostgreSQL managed, Redis cache, object storage, queue workers và data lake. Traffic có peak buổi tối/cuối tuần. Cluster được giữ capacity cao suốt ngày để đáp ứng peak. Analytics chạy full refresh hàng giờ. Log application giữ một năm ở hot storage. Một số báo cáo đọc trực tiếp transaction database.

Vấn đề:
- Compute ban ngày utilization thấp.
- Worker batch cạnh tranh với API interactive.
- Database CPU tăng khi báo cáo chạy.
- Storage và log cost tăng liên tục.
- Egress cross-region cao do pipeline đọc dữ liệu từ vùng khác.
- Team chưa có cost per successful booking.

### 18.2. Đo baseline

Team thu 30 ngày request rate, p95/p99, CPU/memory, pod requests, queue age, DB query profile, storage growth, log volume và egress. Finance gắn chi phí theo service/environment; booking team tính cost per successful booking. Các guardrail gồm booking availability, API p95, payment completion, queue freshness và RPO/RTO.

### 18.3. Các thay đổi

**Compute:** điều chỉnh pod requests theo working set và CPU profile; tách reporting worker pool; autoscale API theo concurrency/CPU; batch worker scale theo queue backlog; non-production chạy theo lịch.

**Database:** tối ưu query/report; chuyển báo cáo nặng sang warehouse/replica; duy trì connection pool budget; không giảm replica DR phục vụ RPO.

**Data:** thay full refresh bằng incremental pipeline; partition pruning; compact small files; loại intermediate data có TTL; log application chuyển sang retention tier theo classification.

**Network:** đặt compute analytics gần data lake trong cùng region phù hợp; giảm cross-region transfer không cần thiết; cache static assets.

**Sustainability:** giảm idle compute, scan lặp và log retention dư; sử dụng báo cáo carbon/energy của provider theo phương pháp được ghi rõ; không suy luận emissions chỉ từ số tiền tiết kiệm.

### 18.4. Rollout và kiểm chứng

Thay đổi được thử ở staging rồi canary theo từng worker pool. Guardrail dừng rollout nếu API p95, queue age, payment outcome hoặc DB connection vượt ngưỡng. So sánh cùng weekday/traffic mix và số booking thành công. IaC cập nhật requests/limits, autoscaling và retention sau khi test pass.

### 18.5. Kết quả cần báo cáo

Báo cáo sau thay đổi cần có:
- Spend trước/sau đã normalize theo booking volume.
- Cost per successful booking.
- CPU/memory utilization và saturation.
- API p95/p99 và error rate.
- Queue backlog/oldest age.
- DB query latency và connection.
- Storage bytes, log volume và egress.
- Environmental estimate, methodology và scope nếu provider có dữ liệu.
- SLO, recovery margin và residual risk.

Không tuyên bố một tỷ lệ tiết kiệm hoặc giảm carbon nếu chưa có số liệu và cách tính kiểm chứng.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tối ưu theo CPU average | Bỏ sót memory/I/O/tail latency | Dùng workload profile đa chiều |
| Giảm headroom tối đa | Failover/burst không đủ capacity | Capacity test theo failure scenario |
| Rightsize mọi workload đồng loạt | Một nhóm workload có bottleneck khác | Canary theo service/class |
| Autoscale chỉ theo CPU | Queue hoặc latency tăng mà CPU thấp | Chọn signal theo bottleneck |
| Scale-to-zero tùy tiện | Cold start phá SLO | Giữ minimum capacity hoặc prewarm |
| Xóa replica vì usage thấp | DR/RPO hoặc read capacity suy giảm | Xác định vai trò trước khi bỏ |
| Chuyển archive không xét restore | RTO/chi phí retrieval không đạt | Test restore và lifecycle |
| Retain mọi log vô hạn | Storage cost và privacy risk tăng | Retention theo classification |
| Full refresh dữ liệu thường xuyên | Compute/IO lãng phí | Incremental và partition pruning |
| Tối ưu egress bằng cách phá HA | Failure domain lớn hơn | Cân bằng topology, resilience và cost |
| Dùng cost làm proxy cho carbon | Kết luận môi trường sai | Dùng dữ liệu energy/carbon có method |
| Chuyển region bỏ qua residency | Vi phạm compliance | Residency/security là constraint |
| Mua commitment chỉ vì discount | Unused capacity và obligation | Forecast và theo dõi utilization |
| Tuyên bố sustainability thiếu scope | Báo cáo thiếu tin cậy | Nêu boundary, method, uncertainty |

## 20. Bài tập thực hành

Một nền tảng SaaS vận hành ba workload: API tương tác, batch analytics và development environments. API có peak 10 lần average trong 90 phút mỗi ngày. Analytics hiện full scan 20 TB mỗi giờ nhưng chỉ 2% partition thay đổi. Dev environments chạy 24/7 dù chỉ dùng giờ hành chính. Database có multi-AZ và backup cross-region theo cam kết DR. Finance muốn giảm cloud spend; sustainability team muốn giảm energy/emissions estimate.

Hãy thực hiện:

1. Xác định metrics/baseline cần thu trong 30 ngày cho compute, storage, DB, network, queue, SLO và cost.
2. Phân tích headroom và failure scenario cho API khi một AZ mất.
3. Đề xuất rightsizing và autoscaling signals cho API/worker; nêu cooldown, min/max và guardrails.
4. Thiết kế schedule/scale-to-zero cho dev environments mà không làm hỏng CI, backup hoặc persistent data.
5. Thay full scan analytics bằng incremental processing; xác định watermark, late data, backfill và correctness tests.
6. Đề xuất storage lifecycle cho logs, artifacts, snapshots và analytics data theo classification/retention.
7. Tối ưu egress/cross-region transfer nhưng vẫn giữ data residency và DR objectives.
8. Tính unit cost per API success và per analytics report; giải thích cách normalize traffic.
9. Xác định dữ liệu cần thiết để ước tính energy/carbon; ghi rõ operational/embodied boundary và uncertainty.
10. Thiết kế carbon-aware scheduling cho phần batch có deadline linh hoạt.
11. Lập canary plan, SLO guardrail, rollback và evidence cho từng thay đổi.
12. Viết ADR so sánh cost saving, environmental impact, reliability, performance và compliance.
13. Xây FinOps dashboard và cadence review với owner cho từng action.

**Gợi ý tự đánh giá:** Bài làm đạt khi tối ưu dựa trên telemetry, giữ đủ headroom theo failure scenario, không cắt control backup/DR tùy tiện, tính unit economics đúng, và mọi tuyên bố môi trường có method/boundary rõ.

## 21. Checklist trước production

- [ ] Workload có owner, criticality, SLO và unit of work rõ.
- [ ] Baseline bao phủ average, percentile, peak, burst và seasonality.
- [ ] Utilization được xem cùng saturation, latency và error.
- [ ] Rightsizing đã benchmark theo compute, memory, I/O và network.
- [ ] Container requests/limits phù hợp working set và throttling.
- [ ] Autoscaling signal, min/max, stabilization và cold start được test.
- [ ] Headroom đủ cho AZ/region failure và deployment surge.
- [ ] Database query, connection và replica role được xác định.
- [ ] Storage tier/retention phù hợp access, legal, privacy và restore.
- [ ] Backup/replication vẫn đáp ứng RPO/RTO và được restore test.
- [ ] Data processing dùng incremental/partition pruning khi semantics cho phép.
- [ ] Network placement/egress tối ưu nhưng không phá HA/residency.
- [ ] Cost được gắn owner/service/environment và unit economics.
- [ ] Budget/anomaly/forecast có alert và action owner.
- [ ] Environmental estimate nêu nguồn, boundary, period và uncertainty.
- [ ] Carbon-aware placement/scheduling tuân thủ latency, security và compliance.
- [ ] Thay đổi có canary, guardrail, rollback và đo trước/sau.
- [ ] IaC/config được cập nhật sau optimization đã xác minh.
- [ ] Có lịch FinOps và sustainability review.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review utilization và sustainability |
| --- | --- |
| **Operational Excellence** | Usage/cost/environment metrics có owner, baseline, review cadence và action loop không? |
| **Security** | Tối ưu retention, region, telemetry và data transfer có giữ classification, encryption, access và audit không? |
| **Reliability** | Rightsizing/autoscaling có giữ failover headroom, backup, RPO/RTO và recovery capacity không? |
| **Performance Efficiency** | Compute, query, storage, network và scheduling có phù hợp workload pattern và SLO không? |
| **Cost Optimization** | Unit economics, idle resource, allocation, commitments, egress và forecast có được quản lý không? |
| **Sustainability** | Workload có giảm xử lý dư, idle capacity, data movement và footprint trong giới hạn method đo đáng tin không? |

**Kết luận:** Tối ưu sử dụng cloud resources bắt đầu bằng đo workload và unit of work, sau đó điều chỉnh compute, database, storage, data pipeline, network và lịch chạy theo demand. Headroom, backup, replication và capacity dự phòng vẫn cần thiết để giữ reliability; tối ưu tốt là loại bỏ lãng phí mà không chuyển rủi ro sang availability, security, compliance hoặc người dùng. Đánh giá tác động môi trường cần có phạm vi và phương pháp minh bạch, phân biệt cost với energy/carbon, operational với embodied impact. Hãy triển khai từng thay đổi bằng canary, guardrail, đo trước/sau và cập nhật IaC để cải tiến được duy trì theo tinh thần Well-Architected.
