# Chi phí mạng, broker, lưu trữ và dữ liệu sao chép

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Chi phí và đánh đổi  
> **Mục tiêu:** Phân tích chi phí hạ tầng phát sinh từ giao tiếp mạng, message broker, lưu trữ và sao chép dữ liệu; biết đo đúng đơn vị tiêu thụ, dự báo theo tải, lựa chọn kiến trúc theo SLO và tối ưu tổng chi phí sở hữu mà không làm suy giảm tính đúng đắn, bảo mật hay khả năng phục hồi.

## 1. Vì sao chi phí hạ tầng phải được xem như một phần của kiến trúc?

Một hệ thống microservices có thể chạy tốt trong giai đoạn đầu nhưng chi phí tăng nhanh khi số người dùng, lưu lượng, số service và dữ liệu cùng tăng. Một checkout không chỉ tiêu tốn CPU của Order API. Nó có thể tạo nhiều lượt gọi mạng, truy vấn database, message events, bản sao dữ liệu, log, trace và backup.

Ví dụ một đơn hàng đi qua:

~~~text
Client
  |
  v
API Gateway
  |
  v
Order Service
  |----> Inventory Service
  |----> Payment Service
  |----> Pricing Service
  |
  +----> PostgreSQL
  |
  +----> Outbox / Message Broker
             |
             +----> Notification
             +----> Analytics
             +----> Search Projection
~~~

Một request đầu vào có thể tạo ra:

- Nhiều network hops giữa gateway, services, database và broker.
- Lưu lượng liên vùng hoặc liên availability zone.
- Phí NAT gateway, load balancer, public IP hoặc data transfer theo nhà cung cấp.
- Message ingress/egress, broker storage, partition replicas và consumer traffic.
- Nhiều lần ghi dữ liệu: source database, read replica, event log, search index, warehouse.
- Chi phí lưu trữ nóng, snapshot, backup, archive và truy xuất dữ liệu cũ.
- Chi phí telemetry, retention, data processing và data egress khi phân tích.
- Chi phí vận hành do phải quản lý thêm cluster, replication topology và failure modes.

Một thiết kế tối ưu riêng CPU có thể làm chi phí mạng và storage tăng. Một thiết kế giảm network calls bằng cách nhân bản dữ liệu có thể làm chi phí consistency, reconciliation và backup tăng.

**Tối ưu chi phí phải nhìn theo toàn bộ hành trình dữ liệu và request**, không chỉ một hóa đơn dịch vụ hoặc một chỉ số CPU.

## 2. Phân biệt chi phí trực tiếp, gián tiếp và chi phí rủi ro

| Nhóm | Ví dụ | Cách nhìn |
|---|---|---|
| **Compute** | CPU, RAM, nodes, serverless invocations | Thời gian chạy và mức tài nguyên |
| **Network** | Egress, cross-zone, cross-region, NAT, LB, CDN | Bytes, connections, requests, transfer path |
| **Broker** | Partitions, throughput, requests, retained bytes, replication | Message volume, size, retention, consumer count |
| **Storage** | GB-month, IOPS, throughput, snapshots, requests | Dung lượng, tần suất truy cập và hiệu năng |
| **Replication** | Replica compute/storage, transfer, log shipping | Số bản sao, khoảng cách và độ trễ |
| **Observability** | Logs, metrics, traces, query/retention | Ingestion volume, cardinality, retention |
| **Operations** | On-call, upgrades, capacity planning, incident recovery | Độ phức tạp và kỹ năng cần thiết |
| **Risk / opportunity** | Outage, data loss, lock-in, chậm phát triển | Tác động kinh doanh, không chỉ bill |

**Chi phí trực tiếp** xuất hiện trong hóa đơn. **Chi phí gián tiếp** gồm thời gian đội ngũ, sự phức tạp vận hành và công sức khắc phục. **Chi phí rủi ro** là hậu quả có thể xảy ra nếu giảm quá mức redundancy, backup hoặc capacity.

Không nên đánh giá một kiến trúc chỉ bằng chi phí compute tháng hiện tại. Nếu một lựa chọn rẻ hơn 20% nhưng làm tăng nguy cơ mất dữ liệu hoặc kéo dài RTO, tổng trade-off có thể bất lợi.

## 3. Xây cost model từ workload thực tế

Trước khi so sánh công nghệ, cần xác định workload:

- Request trung bình và peak theo giây.
- Số request/service call trung bình cho một business transaction.
- Payload size trung bình và p95/p99.
- Số messages tạo ra trên mỗi transaction.
- Tốc độ dữ liệu tăng mới mỗi ngày/tháng.
- Số consumer và số lần mỗi message được đọc.
- Retention của database, broker, logs và backups.
- Số replicas, vùng triển khai và khoảng cách địa lý.
- SLO về latency, availability, RPO/RTO.
- Tỷ lệ cache hit, compression, retry và duplicate delivery.

Một mô hình khái quát:

~~~text
Total Cost
  = Compute
  + Network
  + Broker
  + Primary Storage
  + Replication
  + Backup / Archive
  + Observability
  + Operational Overhead
  + Risk Allowance
~~~

Với một workload cụ thể, có thể lập bảng:

| Input | Đơn vị | Ví dụ giả định |
|---|---|---:|
| API requests | requests/day | 10.000.000 |
| Average network payload | KB/request | 12 |
| Internal service hops | calls/request | 4 |
| Events produced | events/order | 6 |
| Average event size | KB/event | 3 |
| Broker retention | days | 7 |
| Replication factor | copies | 3 |
| New persistent data | GB/day | 80 |
| Backup retention | days | 30 |
| Read replicas | count | 2 |

Các số trên chỉ minh họa cách lập mô hình. Không dùng chúng làm sizing mặc định. Cần đo từ production telemetry, load test hoặc forecast có cơ sở.

**Một mô hình tốt phải ghi rõ giả định, đơn vị, thời gian đo và phạm vi tính phí.** Ví dụ GB thập phân khác GiB nhị phân; một số nhà cung cấp tính egress theo GB, số khác theo tier hoặc request.

## 4. Chi phí mạng: Bytes chỉ là một phần của câu chuyện

Chi phí mạng có thể bao gồm:

- Data transfer ra Internet.
- Transfer giữa availability zones.
- Transfer giữa regions.
- Transfer giữa cloud accounts/projects hoặc giữa cloud providers.
- Traffic qua NAT gateways, firewalls, proxies và load balancers.
- Public IPv4, bandwidth reservation hoặc dedicated connectivity.
- CDN requests, cache fill và origin fetch.
- Cross-region replication và backup transfer.
- Traffic đến observability vendors hoặc SaaS APIs.

**Không có một bảng giá chung cho mọi cloud/region.** Mức phí phụ thuộc nhà cung cấp, vị trí nguồn/đích, loại dịch vụ, tier, hợp đồng và thời điểm. Cost model cần lấy giá thực tế từ billing catalog/contract đang áp dụng.

### 4.1. Ingress và egress

Một số cloud provider miễn phí hoặc định giá khác nhau cho traffic đi vào, traffic nội bộ và traffic đi ra Internet. Không được suy luận rằng mọi chiều đều miễn phí.

Ví dụ:

~~~text
Internet user
    |
    | request ingress
    v
Cloud load balancer
    |
    | internal traffic
    v
Application
    |
    | response egress
    v
Internet user
~~~

Một response lớn có thể tốn egress nhiều hơn request. Một service gọi SaaS API có thể phát sinh phí egress theo tổng bytes gửi đi, ngoài phí API của nhà cung cấp.

**Cần đo cả hai chiều** và tách theo destination class: Internet, same-zone, cross-zone, cross-region, private endpoint, third-party.

### 4.2. Cross-zone traffic

Nếu Order Pod chạy ở zone A nhưng Payment Pod, database hoặc broker leader ở zone B, mỗi request có thể đi qua mạng liên zone.

~~~text
Zone A                       Zone B
Order Pod  ----------------> Payment Pod
           cross-zone bytes
Order Pod  ----------------> DB endpoint
           cross-zone bytes
~~~

Cross-zone traffic có thể làm tăng latency và chi phí transfer theo chính sách provider. Nhưng đặt mọi thành phần trong cùng zone để tránh phí có thể tạo single-zone failure domain.

Cần cân bằng:

- Availability và khả năng chịu mất zone.
- Latency giữa các service.
- Data transfer charges.
- Placement của replicas, partitions và database leaders.
- Khả năng failover khi zone mất.
- Topology spread và workload locality.

**Không hy sinh HA chỉ để loại bỏ cross-zone cost** nếu SLO yêu cầu chịu lỗi zone. Có thể tối ưu placement để giảm traffic thường ngày nhưng vẫn duy trì đủ redundancy.

### 4.3. Cross-region traffic

Cross-region transfer thường có chi phí và latency cao hơn nội vùng. Những nguồn phát sinh:

- Active-active service calls giữa regions.
- Database replication/WAL shipping.
- Kafka MirrorMaker hoặc broker replication.
- Backup và object replication.
- Centralized logs/traces.
- Client requests được route về region xa.

Một kiến trúc active-active có thể giảm latency cho user toàn cầu nhưng tăng replication traffic, conflict resolution và chi phí dữ liệu. Active-passive có thể rẻ hơn nhưng failover chậm hơn hoặc RPO cao hơn.

Đánh giá bằng **total cross-region bytes, replication lag, failover time và cost per successful transaction**, không chỉ bytes trên một link.

## 5. Ước lượng network transfer

Một phép tính sơ bộ:

~~~text
Transfer per day
  = requests per day
    × average payload bytes
    × network hops included in the billing scope
~~~

Ví dụ 10 triệu responses/ngày, trung bình 12 KB:

~~~text
10.000.000 × 12 KB
= 120.000.000 KB
≈ 120 GB/day (decimal units)
≈ 3.600 GB/month nếu tính 30 ngày
~~~

Đây là **ước lượng đơn giản cho một luồng payload**. Không nhân số hop một cách mù quáng: có hop nằm trong cùng vùng/đường truyền không tính phí như Internet egress, và một số payload được nén/cache. Ngược lại, retry, replication, sidecar proxy, telemetry và nhiều consumers có thể làm tổng bytes thực tế lớn hơn.

Để tính bill:

1. Xác định byte nào thuộc loại transfer tính phí.
2. Tách ingress, Internet egress, same-zone, cross-zone và cross-region.
3. Tính payload thực tế sau compression.
4. Thêm retries, replication và fan-out.
5. Áp dụng free tier/tiered pricing/commit discounts theo hợp đồng.
6. Đối chiếu với billing export sau khi triển khai.

Không dùng **network bytes per request** đơn lẻ nếu một request có thể tạo nhiều downstream calls hoặc payload biến thiên mạnh.

## 6. NAT Gateway và đường đi của traffic

Một số kiến trúc đưa traffic outbound của nhiều private subnets qua NAT gateway:

~~~text
Private application Pods
       |
       v
Private subnet route
       |
       v
NAT Gateway
       |
       v
Internet / External API
~~~

Chi phí có thể đến từ số NAT gateways đang chạy, bytes được xử lý, public IP và data transfer theo provider. NAT tập trung có thể trở thành bottleneck hoặc failure concentration nếu không thiết kế HA.

Tối ưu:

- Dùng private endpoints cho cloud services nếu có lợi về chi phí, bảo mật và route.
- Đặt workloads hợp lý theo zone để tránh hairpin qua NAT ở zone khác.
- Tránh để internal service traffic đi vòng qua public Internet.
- Kiểm tra endpoint policies, DNS và route tables khi chuyển sang private connectivity.
- Giới hạn egress không cần thiết và loại bỏ calls thừa.
- Theo dõi bytes processed, connection errors, port exhaustion và per-destination traffic.

**Private endpoint không mặc định luôn rẻ hơn NAT.** Cần so chi phí endpoint hourly, data processing, network path và operational overhead theo dịch vụ cụ thể.

## 7. Load balancer, proxy và service mesh

Mỗi tầng trung gian có thể tạo chi phí:

- Load balancer hourly/LCU hoặc request/bytes processed.
- API Gateway request count, policy execution và data transfer.
- Sidecar proxy CPU/RAM và extra network hops.
- Service mesh control plane, telemetry và certificate rotation.
- WAF inspection, TLS termination và logging.
- Ingress controller replicas và egress gateway.

Service mesh mang lại mTLS, identity-based policy, retries/timeouts và telemetry, nhưng có overhead về CPU, memory, latency và data volume. Với service traffic rất lớn, overhead nhỏ trên mỗi request có thể thành chi phí đáng kể.

Trước khi triển khai, đo:

- Proxy CPU/memory per Pod.
- Bytes/request và số network hops.
- p50/p95/p99 latency có/không proxy.
- Telemetry generated per request.
- Chi phí control plane và data plane.
- Tỷ lệ tính năng thực sự được sử dụng.

Không loại bỏ mesh chỉ vì có overhead nếu nó giải quyết yêu cầu security/operability quan trọng. Hãy so **chi phí bổ sung với năng lực và rủi ro giảm được**.

## 8. CDN và cache giảm chi phí origin như thế nào?

CDN lưu nội dung gần người dùng và giảm số lần origin phải phục vụ cùng một payload.

~~~text
User
  |
  v
CDN edge
  |
  +-- Cache hit --> Return object
  |
  +-- Cache miss --> Origin storage / application
                         |
                         v
                    Cache fill
~~~

CDN có thể giảm:

- Origin egress.
- Origin compute cho nội dung tĩnh hoặc cacheable.
- Latency người dùng.
- Load trên database nếu cache đúng dữ liệu.
- Băng thông của các assets lặp lại.

Nhưng cũng có chi phí:

- CDN requests và data transfer.
- Cache invalidation/purge.
- Origin fetch và cache miss.
- Cache key complexity.
- Security controls, signed URLs/cookies và WAF.
- Stale content hoặc data leakage nếu cache policy sai.

Không cache dữ liệu theo user/tenant mà thiếu cache key scope phù hợp. Một cache hit sai tenant là lỗi bảo mật, dù bill rất thấp.

Đo **cache hit ratio**, origin bytes, invalidation count, stale response incidents và cost per delivered GB. Cache hit ratio cao không tự chứng minh cache đang tạo giá trị nếu nội dung nhỏ hoặc chi phí origin thấp.

## 9. Message broker: Chi phí không chỉ là số message

Kafka, RabbitMQ, cloud queues và streaming platforms có cách tính phí khác nhau. Những yếu tố thường ảnh hưởng:

- Số messages hoặc requests.
- Tổng bytes được produce/consume.
- Số partitions, queues, topics và connections.
- Broker nodes, CPU, memory, disk và IOPS.
- Replication factor và cross-zone/region replication.
- Retention, compaction và segment overhead.
- Consumer count và consumer lag.
- Data transfer đến consumers/connector/analytics.
- Schema registry, connector runtime và managed control plane.

Một message nhỏ nhưng được gửi tới nhiều topics/consumers hoặc giữ lâu có thể tạo chi phí lớn hơn một message lớn chỉ được đọc một lần.

### 9.1. Ước lượng storage của broker

Một mô hình gần đúng cho retained log:

~~~text
Logical retained bytes
  = incoming bytes per second
    × retention seconds

Physical broker storage
  ≈ logical retained bytes
    × replication factor
    × overhead factor
~~~

Ví dụ topic nhận 2 MB/s, giữ 7 ngày, replication factor 3:

~~~text
2 MB/s × 86.400 × 7
= 1.209.600 MB
≈ 1,21 TB logical (decimal)

Physical copies at RF=3
≈ 3,63 TB before additional overhead
~~~

Đây là ước lượng để lập capacity, không phải con số billing chính xác. Còn segment/index overhead, compression, compaction, retention cleanup delay, broker filesystem headroom và provider-specific storage accounting.

**Replication factor 3 không có nghĩa có ba bản độc lập về region hoặc ba failure domains khác nhau.** Cần kiểm tra rack/zone awareness và broker placement.

### 9.2. Partitions có chi phí vận hành

Tăng partitions có thể tăng parallelism và throughput, nhưng cũng làm tăng:

- Metadata và leader/replica management.
- File handles, segment counts và recovery work.
- Consumer assignment/rebalance overhead.
- Network replication streams.
- Operational complexity và thời gian failover.
- Khả năng skew nếu key distribution không đều.

Không tạo hàng nghìn partitions chỉ vì muốn có nhiều consumers. Số partitions nên dựa trên throughput, parallelism, ordering requirements, broker capacity và growth plan.

### 9.3. Retention và compaction

Retention theo thời gian giữ event trong một khoảng nhất định; compaction giữ giá trị mới nhất theo key theo semantics của broker. Hai chính sách phục vụ mục đích khác nhau.

- Event history phục vụ audit/replay có thể cần retention đủ dài.
- Topic chứa current state có thể phù hợp log compaction nếu semantics cho phép.
- Tombstones cần giữ đủ lâu để consumers nhìn thấy deletion.
- Retention ngắn làm giảm storage nhưng thu hẹp khả năng replay/recovery.
- Retention dài làm tăng storage, replication và backup/restore work.

**Không rút retention chỉ để giảm bill khi downstream chưa bảo đảm đã xử lý dữ liệu hoặc có nguồn phục hồi khác.**

## 10. Message fan-out và số lần đọc

Một event có thể được nhiều consumer groups đọc:

~~~text
OrderConfirmed topic
       |
       +--> Inventory consumer group
       +--> Notification consumer group
       +--> Analytics consumer group
       +--> Fraud consumer group
       +--> Search indexing consumer group
~~~

Trong Kafka, mỗi consumer group thường đọc độc lập log, nên một event có thể được truyền và xử lý nhiều lần theo số groups. Broker storage không nhất thiết nhân toàn bộ dữ liệu theo số groups, nhưng network, consumer compute và downstream writes có thể tăng.

Cần đo:

- Bytes produced.
- Bytes fetched per consumer group.
- Số lần xử lý thành công và retry.
- Consumer lag và reprocessing volume.
- Số sink writes tạo ra.
- Chi phí connector/egress nếu consumer ở vùng khác.

Nếu consumer chỉ cần một phần payload, có thể dùng event phù hợp theo bounded context hoặc projection riêng, nhưng tránh tạo quá nhiều topics/events trùng lặp gây schema và governance overhead.

## 11. Message size, compression và batch size

Message lớn làm tăng network, broker storage, replication, memory và latency. Một số tối ưu:

- Không nhúng file lớn vào event; lưu object trong storage và truyền reference có quyền truy cập an toàn.
- Chỉ gửi fields consumer cần, nhưng không làm payload mất semantics.
- Compression khi CPU overhead thấp hơn network/storage savings.
- Batch producer/consumer phù hợp throughput và latency SLO.
- Giới hạn payload size và từ chối message vượt contract.
- Dùng schema compact và tránh lặp metadata không cần.
- Đặt max in-flight/prefetch để không giữ quá nhiều message trong RAM.

Compression có trade-off: CPU tăng, compression ratio phụ thuộc dữ liệu, latency batch có thể tăng. Với dữ liệu đã nén như JPEG/ZIP, lợi ích có thể nhỏ.

**Đo compressed bytes thực tế**, không ước lượng bằng một tỷ lệ nén cố định cho mọi topic.

## 12. Consumer lag: Chi phí của backlog

Khi producer nhanh hơn consumer, backlog tăng:

~~~text
Producer rate: 20.000 events/s
Consumer rate: 15.000 events/s
Net backlog growth: 5.000 events/s
~~~

Nếu không có thay đổi, backlog tăng 300.000 events mỗi phút. Hậu quả:

- Retained storage và broker disk pressure tăng.
- Consumer recovery/replay mất lâu hơn.
- Dữ liệu downstream stale.
- Khi scale consumer, DB/API phía sau có thể bị quá tải.
- Job cũ có thể hết giá trị nghiệp vụ nhưng vẫn tiêu tốn tài nguyên.

Tối ưu không chỉ là tăng consumers. Phải xác định bottleneck ở broker fetch, deserialization, CPU, DB writes, external API, partition skew hoặc rate limit.

Một chính sách tốt có thể gồm bounded consumer concurrency, backpressure, batch size, pause/resume, DLQ và expiry policy cho sự kiện không còn giá trị. Không drop event tài chính/critical chỉ vì backlog cao; cần xử lý theo data contract và business policy.

## 13. Broker và lựa chọn queue/stream

| Nhu cầu | Lựa chọn có thể phù hợp | Trade-off |
|---|---|---|
| Work queue đơn giản, ack/retry | Managed queue hoặc RabbitMQ | Visibility/ordering/throughput khác nhau |
| Event log, replay, nhiều consumers | Kafka hoặc managed streaming | Partitions, retention, operations |
| Pub/sub notification | Managed pub/sub | Delivery semantics, ordering, egress |
| Delayed/scheduled jobs | Queue có delay hoặc scheduler | Timing, duplicate handling |
| Event sourcing | Append-only event store/log | Schema evolution, replay và query complexity |

Không chọn Kafka chỉ vì hệ thống dùng microservices. Nếu chỉ cần một job queue nhỏ, managed queue có thể giảm operational overhead. Ngược lại, nếu cần replay dài, nhiều consumer groups và throughput cao, một queue đơn giản có thể không đáp ứng.

So sánh theo:

- Delivery semantics, ordering và durability.
- Throughput và message size.
- Retention/replay.
- Replication/failure domains.
- Consumer concurrency và lag behavior.
- Security, tenancy và audit.
- Cost model và team expertise.
- Backup/restore và DR strategy.

## 14. Storage: GB-month không phải toàn bộ chi phí

Chi phí lưu trữ có thể bao gồm:

- Dung lượng provisioned hoặc consumed.
- IOPS và throughput provisioned.
- Read/write requests.
- Snapshot storage và incremental changed blocks.
- Backup retention.
- Cross-region replication.
- Retrieval fees và early deletion fees.
- Metadata/index overhead.
- Encryption/KMS operations.
- Data transfer khi đọc hoặc xuất dữ liệu.
- Operational costs của storage classes và lifecycle rules.

Một volume có giá GB-month thấp nhưng IOPS đắt có thể trở thành nguồn chi phí lớn. Một archive rẻ nhưng retrieval mất hàng giờ có thể không phù hợp dữ liệu cần RTO thấp.

**Tách storage capacity khỏi performance capacity.** Chỉ nhìn dung lượng không đủ để chọn storage class.

## 15. Storage tiers: Hot, warm, cold và archive

| Tier | Mục đích | Đặc điểm trade-off |
|---|---|---|
| **Hot** | Dữ liệu giao dịch/truy vấn thường xuyên | Latency thấp, IOPS cao, chi phí thường cao |
| **Warm** | Dữ liệu ít truy cập nhưng vẫn cần truy vấn hợp lý | Chi phí thấp hơn, hiệu năng có thể giảm |
| **Cold** | Dữ liệu hiếm khi đọc, có thể chờ | Retrieval delay/fee, giới hạn thao tác |
| **Archive** | Lưu dài hạn, compliance/forensic | Chi phí lưu thấp hơn nhưng phục hồi chậm hơn |

Một chính sách lifecycle:

~~~text
New transaction data
        |
        v
Hot storage
        |
        | after 30 days (example)
        v
Warm storage
        |
        | after 180 days (example)
        v
Archive / immutable retention
        |
        | after policy expiry
        v
Approved deletion
~~~

Mốc 30/180 ngày chỉ là ví dụ. Phải xác định theo access pattern, legal retention, data classification, backup policy và RTO.

Đừng archive dữ liệu trước khi biết hệ thống cần truy vấn lịch sử trong bao lâu. Một API support cần truy cập hóa đơn 5 năm không thể giả định dữ liệu archive sẽ phản hồi như bảng hot.

## 16. Database storage và index overhead

Dung lượng database gồm:

- Table data.
- Indexes.
- Transaction logs/WAL/binlogs.
- Temporary files và sort/hash spill.
- MVCC dead tuples hoặc fragmentation tùy engine.
- Replicas và snapshots.
- Backup full/incremental/logs.
- Metadata/catalog và system overhead.

Index giúp query nhanh nhưng tốn storage và làm chậm writes/maintenance. Một index ít được dùng có thể tăng chi phí backup, replication và cache pressure mà không đem lại lợi ích.

Cần đo:

- Table/index size theo dataset.
- Index hit/use và query plans.
- Bloat/dead tuples theo engine.
- Write amplification.
- WAL/binlog generation rate.
- Vacuum/compaction/maintenance cost.
- Storage IOPS/latency và connection saturation.

Không xóa index chỉ vì ít hit trong một tuần nếu có query theo mùa hoặc query hiếm nhưng critical. Cần phân tích workload horizon và kiểm thử.

## 17. Snapshots và backup storage

Snapshot có thể giảm thời gian tạo bản sao hoặc hỗ trợ clone môi trường, nhưng vẫn có chi phí:

- Snapshot metadata và changed blocks.
- Retention của snapshot.
- Cross-region copy.
- Restore/clone operations.
- Performance impact nếu provider có behavior liên quan.
- Orphan snapshots không còn owner.
- Data growth khi nhiều snapshots giữ các block cũ.

Một snapshot incremental không nhất thiết chỉ tính phần changed blocks theo cùng một cách ở mọi provider; phải kiểm tra billing semantics. Xóa snapshot cũ cũng cần hiểu dependency chain hoặc snapshot lineage.

**Backup và snapshot cần có owner, retention, recovery test và deletion policy.** Không để snapshots tồn tại vô hạn chỉ vì không ai biết chúng còn cần hay không.

## 18. Replication: Chi phí của độ bền và khả năng phục hồi

Replication tạo thêm bản sao dữ liệu để tăng availability, read capacity hoặc geographic reach. Các mô hình:

- **Synchronous replication:** commit có thể chờ replica xác nhận theo semantics engine, giảm một số loại data loss nhưng tăng latency và phụ thuộc replica availability.
- **Asynchronous replication:** primary không chờ replica hoàn tất; latency thấp hơn nhưng có replication lag và có thể mất phần dữ liệu chưa chuyển khi thảm họa.
- **Semi-synchronous/quorum:** thỏa hiệp theo cơ chế cụ thể.
- **Multi-region replication:** tăng khả năng phục hồi địa lý nhưng thêm transfer, conflict và failover complexity.
- **Read replicas:** phân tải reads nhưng dữ liệu có thể stale.

~~~text
Primary DB
   |
   +---- synchronous replica (same failure domain policy)
   |
   +---- asynchronous replica (another zone)
   |
   +---- backup/PITR archive (separate account/region)
~~~

Không đồng nhất **replica** với **backup**. Xóa nhầm, corruption logic hoặc ransomware có thể lan sang replica. Cần bản sao lịch sử/immutable hoặc PITR độc lập.

## 19. Replication factor và chi phí vật lý

Nếu một dataset có logical size S và replication factor R:

~~~text
Approximate replicated capacity = S × R
~~~

Ví dụ 4 TB logical data, replication factor 3 có thể cần khoảng 12 TB raw capacity trước overhead. Nhưng billing thực tế còn phụ thuộc compression, storage engine, reserved capacity, erasure coding, snapshots và provider pricing.

Replication factor cao hơn có thể tăng:

- Storage capacity.
- Network replication bytes.
- Write amplification.
- Recovery/rebalance traffic.
- Broker/database CPU và I/O.
- Operational complexity.

Đổi lại có thể tăng durability/availability hoặc read throughput tùy topology. Chọn factor dựa trên failure model, durability target và công nghệ; không mặc định RF=3 là luôn đúng.

**Ba replica trên cùng một host hoặc cùng một failure domain không tạo khả năng chịu lỗi tương đương ba bản ở các failure domains độc lập.**

## 20. Read replicas và consistency trade-off

Read replicas có thể giảm tải query lên primary và đặt dữ liệu gần người dùng. Nhưng async replication tạo **staleness**:

~~~text
Write: Order status = CONFIRMED on primary
                 |
                 | replication lag
                 v
Read replica still shows PENDING
~~~

Nếu API cần read-your-writes, có thể:

- Đọc từ primary sau write.
- Dùng session consistency token/version.
- Chờ replica catch up trong giới hạn.
- Route query critical sang primary.
- Thiết kế response command trả trạng thái vừa commit thay vì đọc lại replica.

Đừng gửi mọi read tới primary chỉ để né stale nếu phần lớn use cases chấp nhận eventual consistency. Ngược lại, đừng dùng replica stale cho payment/authorization decision nếu business rules đòi dữ liệu mới nhất.

Read replica có chi phí compute/storage/network và có thể tăng phí transfer giữa zone/region. So sánh chi phí replica với phần primary capacity tiết kiệm và latency cải thiện.

## 21. Data locality: Đặt compute gần dữ liệu

Một service truy vấn database qua region khác có thể phát sinh:

- Latency cao.
- Transfer cost.
- Tăng thời gian giữ connections.
- Tăng retry/timeouts.
- Phụ thuộc network path dài.
- Ảnh hưởng availability khi inter-region link có sự cố.

Data locality giúp giảm transfer và latency, nhưng có thể dẫn đến nhiều bản sao dữ liệu hoặc khó cân bằng tải. Một nguyên tắc:

**Đặt compute gần dữ liệu mà nó truy cập thường xuyên; sao chép dữ liệu chỉ khi có nhu cầu đọc/availability/latency đủ rõ.**

Không tạo replica toàn cầu cho mọi bảng chỉ vì muốn “user ở đâu cũng nhanh”. Cần xét dữ liệu nào được phép lưu ở vùng nào, freshness, conflict, privacy và chi phí đồng bộ.

## 22. Replication và data consistency

Có ba câu hỏi cần trả lời:

1. **Durability:** Khi một write được xác nhận, những bản sao nào đã có dữ liệu bền vững?
2. **Consistency:** Reader nào có thể nhìn thấy write đó và vào thời điểm nào?
3. **Availability:** Khi một replica/network partition mất, hệ thống tiếp tục đọc/ghi theo policy nào?

Không có một lựa chọn tối ưu mọi thứ. Synchronous replication có thể tăng commit latency và giảm write availability nếu quorum/replica không đáp ứng. Asynchronous replication tăng responsiveness nhưng chấp nhận lag và một cửa sổ data loss khi primary mất.

Các khái niệm như strong consistency, eventual consistency, read-your-writes và causal consistency phải gắn với **operation cụ thể**, không mô tả chung chung cả hệ thống.

Ví dụ:

- Payment ledger có thể yêu cầu commit semantics mạnh và audit.
- Search index có thể chấp nhận eventual consistency vài giây.
- Product catalog cache có thể stale trong một cửa sổ được chấp nhận.
- Inventory reservation cần atomicity/locking hoặc allocation policy rõ để tránh oversell.

## 23. Multi-region active-active: Chi phí và độ phức tạp tăng mạnh

~~~text
Region A                         Region B
API + DB                         API + DB
   |                                |
   +---------- replication ---------+
   |                                |
   +---------- conflict resolution -+
~~~

Active-active có thể cải thiện latency và availability toàn cầu nhưng cần giải quyết:

- Concurrent writes cùng record.
- Conflict resolution và ordering.
- Unique ID generation.
- Cross-region replication lag.
- Data residency.
- Split-brain và network partition.
- Quota/provider capacity ở từng region.
- Failback và reconciliation.
- Double processing/side effects.
- Chi phí transfer và compute luôn chạy ở nhiều vùng.

Nếu dữ liệu cần single-writer semantics, active-passive hoặc regional ownership có thể đơn giản hơn. Active-active không phải mặc định tốt hơn chỉ vì nhiều region.

**Đừng triển khai active-active chỉ để tránh một vài GB egress** nếu chi phí consistency và vận hành vượt lợi ích.

## 24. Event sourcing và dữ liệu sao chép

Event sourcing lưu event log làm nguồn lịch sử; các read models/projections được tạo bằng cách replay.

Chi phí:

- Event log storage và retention.
- Nhiều projection databases/indexes.
- Consumer compute để build/rebuild.
- Replay traffic và thời gian rebuild.
- Schema evolution/upcasting.
- Backup log và snapshots của aggregate state.
- Observability cho lag và projection correctness.

Ưu điểm là audit/history và khả năng tái tạo read models khi có source events đầy đủ. Nhưng event log không miễn phí và không tự giải quyết query/reporting. Một số hệ thống chỉ cần transactional outbox + event broker và snapshot/read models đơn giản, không cần event sourcing toàn diện.

Chỉ giữ event history dài khi có yêu cầu audit, temporal reconstruction hoặc business value đủ lớn; đồng thời đặt retention/archival và privacy policy.

## 25. Data duplication: Khi nào nên nhân bản?

Một bản sao dữ liệu có thể được tạo để:

- Giảm read latency.
- Giảm tải primary database.
- Phục vụ search/analytics.
- Tách workload operational và analytical.
- Đưa dữ liệu tới region gần người dùng.
- Tăng availability hoặc hỗ trợ DR.

Nhưng mỗi bản sao kéo theo:

- Storage và replication transfer.
- Consumer/ETL compute.
- Schema evolution và contract management.
- Freshness lag và stale reads.
- Reconciliation, backfill và data quality monitoring.
- Backup/retention riêng.
- Security/privacy access control.
- Deletion propagation và quyền truy cập.
- Chi phí incident khi các bản sao lệch nhau.

**Một bản sao chỉ có giá trị nếu có consumer, SLO và owner rõ.** Bản sao không được dùng, không được kiểm tra và không có người chịu trách nhiệm thường chỉ là chi phí và rủi ro.

### 25.1. Materialized views và search indexes

Materialized view hoặc search index là dữ liệu dẫn xuất. Có thể rebuild từ source nếu:

- Source đủ đầy đủ.
- Transformation deterministic/versioned.
- Replay throughput đáp ứng RTO.
- Schema và mapping cũ còn tương thích.
- Rebuild không làm quá tải source.

Nếu rebuild mất 3 ngày nhưng RTO là 2 giờ, dữ liệu dẫn xuất đó thực tế cần snapshot/backup hoặc warm replica. Quyết định phụ thuộc **chi phí giữ bản sao so với chi phí và thời gian dựng lại**.

## 26. Storage và network của observability

Logs, metrics và traces có thể là một trong những nguồn tiêu thụ dữ liệu lớn nhất:

~~~text
Service instrumentation
      |
      +--> Logs
      +--> Metrics
      +--> Traces
               |
               v
        Collector / Gateway
               |
               v
       Observability backend
               |
               v
        Query, retention, export
~~~

Chi phí gồm:

- Ingestion bytes/events.
- Metrics cardinality và series count.
- Trace spans per request và sampling.
- Indexing/query compute.
- Retention và archive.
- Cross-region export hoặc SaaS egress.
- Replication/HA của observability backend.

Tối ưu có trách nhiệm:

- Dùng structured logs và log levels hợp lý.
- Không log payload lớn hoặc PII không cần thiết.
- Tránh metric labels có cardinality vô hạn.
- Sampling traces theo mục tiêu chẩn đoán; bảo đảm SLI/error rate không suy ra từ mẫu bị thiên lệch.
- Dùng retention tier theo nhu cầu.
- Aggregate metrics gần nguồn khi không cần raw high-cardinality data.
- Alert khi collector drop telemetry, không giảm volume âm thầm.

Không cắt audit/security logs bắt buộc để tiết kiệm chi phí telemetry. Phân biệt observability sampling với yêu cầu lưu audit.

## 27. Cost per transaction và unit economics

Một chỉ số hữu ích là **chi phí trên một business transaction thành công**:

~~~text
Cost per successful order
  = total attributable infrastructure cost
    / successful orders
~~~

Có thể phân rã:

~~~text
Order cost
  = API compute
  + network transfer
  + database read/write
  + broker production/consumption
  + storage growth
  + replication/backup share
  + observability share
~~~

Phân bổ cần cẩn trọng: một broker topic có thể phục vụ nhiều domains; database shared có thể chứa nhiều datasets. Có thể dùng cost allocation tags, namespaces, workload identities, topic ownership, database schemas hoặc usage telemetry.

Không chia đều hóa đơn cluster cho tất cả service nếu traffic và resource usage khác nhau. Nhưng cũng không tạo một hệ chargeback quá phức tạp khiến chi phí vận hành cao hơn lợi ích.

**Unit economics giúp trả lời một thay đổi kiến trúc có làm chi phí trên một đơn hàng tăng hay giảm**, kể cả khi tổng bill tăng vì số đơn tăng.

## 28. FinOps: Gắn chi phí với owner và workload

Một mô hình quản trị:

- **Cloud/platform team:** cung cấp billing export, pricing, tags và dashboards.
- **Service owner:** hiểu workload, tối ưu code, requests, network calls và data retention.
- **Finance/FinOps:** định nghĩa allocation, budgets, forecasts và anomaly review.
- **Architecture:** xem xét trade-offs khi chọn replication, broker, storage hoặc topology.
- **Security/compliance:** đảm bảo tối ưu không phá retention, privacy, encryption hoặc resilience.

Các thực hành:

1. Tag tài nguyên theo service, domain, environment, owner và cost center.
2. Dùng naming conventions cho buckets, topics, volumes và clusters.
3. Theo dõi idle/unattached resources, orphan snapshots và old disks.
4. Đặt budgets/alerts theo workload và environment.
5. So forecast với actual billing.
6. Ghi nhận cost changes trong ADR khi tác động lớn.
7. Đưa cost/performance measurements vào load tests.
8. Review retention và replication định kỳ.
9. Xây dashboard cost per transaction và cost per GB/event.
10. Không xóa tài nguyên production chỉ vì tag thiếu; cần inventory và owner resolution.

**Cost allocation không phải công cụ phạt team.** Nó giúp tìm nơi tiêu thụ và ra quyết định kiến trúc dựa trên dữ liệu.

## 29. Ví dụ: So sánh hai cách lưu event

Giả sử hệ thống phát 100 triệu events/tháng, mỗi event trung bình 2 KB, cần phục vụ ba consumer groups.

### Phương án A — Giữ broker retention 30 ngày

- Broker lưu event đủ lâu để consumers replay.
- Storage nhân theo replication factor.
- Consumer groups đọc độc lập.
- Vận hành đơn giản hơn cho replay trong cửa sổ retention.
- Retention và replication có chi phí liên tục.

### Phương án B — Broker retention ngắn, archive raw events sang object storage

- Broker giữ vài ngày để phục vụ streaming.
- Raw events được archive theo partition/time.
- Replay lịch sử cần job import/backfill.
- Storage archive có thể rẻ hơn nhưng retrieval/processing chậm hơn.
- Cần schema versions, manifest, checksums và restore tooling.
- Có thêm connector/ETL compute và egress khi replay.

So sánh:

| Tiêu chí | Broker retention dài | Broker ngắn + object archive |
|---|---|---|
| Replay gần thời gian thực | Thuận tiện | Phải load lại archive |
| Storage nóng | Cao hơn | Thấp hơn |
| Chi phí archive | Ít/không tách riêng | Có |
| RTO rebuild projection | Có thể nhanh hơn | Phụ thuộc retrieval/import |
| Độ phức tạp | Thấp hơn nếu broker quản lý tốt | Cao hơn, cần archive pipeline |
| Data governance | Broker retention policy | Thêm lifecycle/manifest/privacy |

Không có đáp án mặc định. Nếu cần replay tức thì nhiều tháng, archive cold có thể không đáp ứng RTO. Nếu hiếm khi replay lịch sử, giữ tất cả trên broker có thể lãng phí.

## 30. Ví dụ: Chọn số read replicas cho database

Giả sử primary DB có 70% read, 30% write. Một số truy vấn analytics làm latency OLTP tăng.

Các lựa chọn:

1. Tối ưu query/index và cache trước.
2. Tách analytics sang warehouse/read replica chuyên dụng.
3. Thêm một read replica cùng region/zone topology phù hợp.
4. Thêm replica ở region gần user nếu có demand và consistency policy.
5. Tạo projection riêng nếu query shape khác xa transactional model.

Mỗi replica thêm chi phí compute/storage/transfer và replication lag. Nếu 90% reads có thể cache an toàn trong 60 giây, một cache có thể rẻ hơn replica thứ ba. Nếu read cần consistency mạnh, cache/replica stale có thể không phù hợp.

Đánh giá:

- Read QPS thực sự chuyển khỏi primary.
- Primary CPU/IOPS giảm bao nhiêu.
- Replica lag và stale-read incidents.
- Cross-zone/region bytes.
- Replica cost per month.
- Tác động đến failover và recovery.
- Chi phí cache invalidation/consistency nếu dùng cache.

**Không thêm replica nếu query vẫn bị giới hạn bởi lock, index thiếu hoặc một hot partition.** Cần tìm bottleneck trước.

## 31. Ví dụ: Tính chi phí dữ liệu mới và retention

Giả sử ứng dụng tạo 80 GB dữ liệu mới mỗi ngày, giữ hot 30 ngày, warm 90 ngày tiếp theo và archive 2 năm. Chưa xét compression, index và replication:

~~~text
Hot capacity ≈ 80 GB/day × 30 days = 2.4 TB
Warm capacity ≈ 80 GB/day × 90 days = 7.2 TB
Archive capacity ≈ 80 GB/day × 730 days = 58.4 TB
~~~

Tổng logical data gần 68 TB theo giả định tăng trưởng đều và retention không có deletion. Nếu có replication factor 2 ở hot tier, snapshot, indexes và backup, physical/billable capacity có thể lớn hơn đáng kể.

Thực tế cần tính:

- Data growth không đều theo ngày.
- Compression ratio theo loại data.
- Index/table overhead.
- Retention expiry và legal hold.
- Snapshot incremental behavior.
- Replication copies và cross-region transfer.
- Archive retrieval volume.
- Data deletion và compaction.
- Storage minimum billing/early deletion terms.

**Retention là một quyết định kiến trúc và governance**, không chỉ một con số trong lifecycle rule.

## 32. Cost optimization không được phá consistency hoặc security

Các cách giảm chi phí có vẻ hấp dẫn nhưng rủi ro:

- Giảm replication factor làm giảm durability/availability.
- Rút retention làm mất khả năng replay và audit.
- Dùng cache quá mạnh gây stale reads hoặc cross-tenant leakage.
- Gộp mọi service vào một broker/DB để giảm cluster count nhưng tăng blast radius.
- Tắt TLS để giảm CPU/bytes mà phá trust boundary.
- Giảm logs quá mức khiến incident không thể điều tra.
- Dùng một region duy nhất để giảm egress nhưng không đáp ứng DR.
- Nén hoặc thay schema không tương thích khiến consumer mất dữ liệu.

Mỗi optimization cần có **guardrails**:

1. SLO vẫn đạt.
2. RPO/RTO không vượt cam kết.
3. Data contract và event replay vẫn hoạt động.
4. Security/privacy controls không bị suy yếu.
5. Có monitoring và rollback.
6. Có owner và bằng chứng trước/sau.

**Cost optimization tốt là loại bỏ lãng phí trong khi giữ nguyên những thuộc tính hệ thống cần bảo vệ.**

## 33. Network optimization: Giảm bytes và hops có kiểm soát

Các biện pháp:

- **Payload minimization:** chỉ truyền fields consumer cần.
- **Compression:** giảm bytes khi CPU trade-off có lợi.
- **Batching:** gộp operations để giảm per-request overhead.
- **Connection reuse:** tránh TLS handshake/connection churn không cần.
- **Locality-aware routing:** đặt service gần dependency thường xuyên dùng.
- **CDN/cache:** giảm origin fetch cho dữ liệu phù hợp.
- **Private endpoints:** tối ưu route và trust boundary khi có lợi.
- **Avoid chatty APIs:** thay nhiều calls nhỏ bằng API/use case phù hợp.
- **Async events:** giảm synchronous coupling, nhưng tính thêm broker/consumer costs.
- **Avoid duplicate telemetry:** không export cùng log/span qua nhiều pipeline vô ích.

Trước/sau phải đo:

- Bytes per transaction.
- Cross-zone/cross-region bytes.
- Request count và network hops.
- p95/p99 latency.
- CPU compression/proxy overhead.
- Error/retry rates.
- Cost per successful operation.

Không gom quá nhiều dữ liệu vào một response khổng lồ chỉ để giảm số calls; payload lớn có thể tăng memory, latency, egress và retry cost.

## 34. Broker optimization: Retention, partitions và consumers

- Xóa topics/queues không còn owner sau khi kiểm tra consumers và retention obligations.
- Điều chỉnh retention theo replay/DR requirement.
- Compression/batching theo payload và latency profile.
- Chọn partition count dựa trên parallelism thực.
- Tránh key skew gây một partition nóng.
- Giới hạn message size và đưa binary blobs sang object storage.
- Giảm consumer groups trùng lặp nếu cùng tạo một projection.
- Theo dõi consumer lag và xử lý nguyên nhân, không scale vô hạn.
- Tối ưu batch writes xuống database.
- Có DLQ policy để poison messages không loop vô hạn.
- Review replication factor theo failure domains và durability SLO.
- Lập capacity cho rebalance/replay, không chỉ steady-state.

**Không giảm replication hoặc retention trên topic critical mà không xác nhận backup/replay path.**

## 35. Storage optimization: Lifecycle, compression và data model

- Xóa dữ liệu tạm/derived theo policy có owner.
- Archive dữ liệu ít truy cập.
- Dùng compression phù hợp và đo CPU/latency.
- Giảm index dư thừa; kiểm tra query plan trước khi xóa.
- Partition bảng lớn theo truy vấn và retention.
- Chọn block/object sizes hợp lý để tránh quá nhiều tiny objects.
- Dùng columnar formats cho analytical workloads khi phù hợp.
- Tránh lưu cùng một payload lớn trong nhiều hệ thống nếu có thể dùng immutable reference.
- Dùng deduplication khi semantics cho phép.
- Xác định retention cho WAL/binlog, snapshots và backups riêng.
- Theo dõi orphan volumes, unattached disks và snapshots không owner.
- Không xóa dữ liệu audit/financial theo optimization thông thường.

Object reference cần access control, checksum, version và retention. Dùng một URL công khai thay cho file copy không phải tối ưu an toàn nếu tài liệu nhạy cảm.

## 36. Replication optimization: Sao chép đúng thứ cần thiết

Một số câu hỏi trước khi nhân bản:

- Có cần bản sao để tăng read throughput, giảm latency hay DR?
- Có thể rebuild từ source hay bắt buộc giữ snapshot?
- Dữ liệu nào cần đồng bộ tức thì, dữ liệu nào chấp nhận eventual consistency?
- Có thể replicate projection nhỏ thay vì toàn bộ database?
- Có thể chỉ replicate fields cần thiết theo privacy policy?
- Có thể đặt replica trong cùng region/zone topology để giảm transfer mà vẫn đạt failure objective?
- Có thể dùng backup immutable thay cho active replica nếu RTO dài hơn?
- Khi failover, ai quyết định write authority và fencing primary cũ?
- Replication lag được alert theo RPO thế nào?
- Chi phí reconciliation và conflict resolution có được tính không?

**Replicate ít hơn không tự động tốt hơn.** Cần giữ dữ liệu đủ để phục hồi và đáp ứng user-facing workflows đã cam kết.

## 37. Capacity planning và headroom

Chi phí thấp nhất tại mức tải trung bình có thể làm hệ thống không chịu được peak. Cần dự báo:

- Average, peak và burst traffic.
- Growth rate theo tháng/quý.
- Seasonality/campaign spikes.
- Failure scenarios: một zone/replica mất, còn lại phải gánh bao nhiêu.
- Replay/backfill/restore workloads chạy đồng thời với production.
- Broker rebalance và database failover.
- Storage headroom để compaction, WAL và snapshots hoạt động.
- Network bandwidth trong replication catch-up.

Một hệ thống có 80% utilization bình thường nhưng cần 2x capacity khi mất một zone sẽ phải trả chi phí headroom hoặc chấp nhận degraded service. Đây là **trade-off availability và cost** cần được phê duyệt, không phải lãng phí mặc định.

## 38. FinOps dashboards và allocation metrics

Các chỉ số nên theo dõi theo service/domain/environment:

~~~text
network_egress_bytes_total
network_cross_zone_bytes_total
network_cross_region_bytes_total
nat_bytes_processed_total
cdn_cache_hit_ratio
broker_bytes_in_total
broker_bytes_out_total
broker_retained_bytes
broker_consumer_lag
storage_logical_bytes
storage_billable_bytes
storage_read_iops
storage_write_iops
replication_lag_seconds
replication_bytes_total
backup_retained_bytes
cost_per_successful_transaction
~~~

Đây là tên metric minh họa; một số số liệu phải lấy từ cloud billing export/provider APIs thay vì application instrumentation. Billing là nguồn xác nhận phí cuối cùng; telemetry runtime giúp giải thích nguyên nhân.

Dashboard cần có:

- Cost by service/team/environment.
- Cost by resource type/provider/region.
- Cost per successful order/payment/report.
- Unit cost trend theo traffic growth.
- Unallocated/shared cost.
- Idle resources và orphaned resources.
- Forecast vs actual.
- Top cost anomalies.
- Data transfer paths và storage growth.
- Replication/backup costs cùng SLO.

Không nhầm **estimated cost telemetry** với invoice đã được provider xác nhận; thể hiện rõ nguồn và độ trễ cập nhật.

## 39. Anomaly detection và budgets

Một bill tăng có thể do traffic tăng hợp lệ, retry storm, bug tạo messages trùng, log level đổi hoặc data egress bất thường.

Quy trình:

1. Phát hiện mức tăng vượt baseline/budget.
2. Phân rã theo service, resource, region, account và thời gian.
3. Đối chiếu deployment/config/traffic changes.
4. Tìm nguồn bytes/requests/storage mới.
5. Xác nhận có phải workload hợp lệ hay lỗi.
6. Ước lượng tác động nếu rollback/throttle.
7. Chỉ thay đổi khi owner và risk controls rõ.
8. Ghi lại savings và tác động tới SLO.

Budgets nên có **warning và action policy**. Không tự tắt database production hoặc xóa backups khi vượt budget. Budget alert là tín hiệu điều tra, không phải quyền phá hủy tài nguyên.

## 40. ADR cho một quyết định có tác động chi phí

Một Architecture Decision Record nên mô tả:

~~~text
Title: Keep 30-day broker retention or archive after 3 days

Context:
- 30-day replay currently used by reporting rebuilds.
- Broker storage and replication costs are rising.
- Finance requires recoverability for settlement events.

Options:
A. Keep 30 days on broker.
B. Keep 3 days on broker and archive raw events to object storage.
C. Keep 7 days plus a separate immutable event archive.

Decision:
- Chosen option and why.

Cost model:
- Broker storage, replication, archive, retrieval, compute, egress.
- Cost per month and per replay exercise.

Operational impact:
- Replay RTO, data validation, schema availability, owner.

Risks:
- Archive gap, restore tooling, permissions, provider lock-in.

Guardrails:
- RPO/RTO, checksums, reconciliation, alert thresholds.

Review date:
- When workload or pricing assumptions should be revisited.
~~~

ADR giúp quyết định không biến thành “chọn dịch vụ rẻ nhất” mà không có ngữ cảnh. Giá nhà cung cấp thay đổi, nên ghi ngày và nguồn pricing assumptions.

## 41. Vendor pricing và cloud lock-in

Các dịch vụ managed giảm operational overhead nhưng có thể gắn với pricing model, APIs và network topology riêng.

Đánh giá:

- Giá compute/storage/network theo region.
- Phí request, IOPS, throughput, egress và retrieval.
- Minimum commitment/reserved capacity.
- Managed control plane và support tier.
- Data export/migration costs.
- API limits và quota.
- Encryption/KMS dependencies.
- Backup export format và khả năng restore ở nơi khác.
- Skill/operations cost nếu tự quản lý.
- Cost của downtime hoặc migration.

**Không giả định tự host luôn rẻ hơn managed service.** Phải cộng engineer time, upgrades, on-call, capacity reserve, hardware failure và support.

Cũng không giả định managed service không lock-in. Cần xác định mức portability thực tế, nhất là dữ liệu lớn và dịch vụ proprietary.

## 42. So sánh managed broker và self-managed broker

| Tiêu chí | Managed broker | Self-managed |
|---|---|---|
| Provision/upgrade | Nhà cung cấp hỗ trợ nhiều phần | Team chịu trách nhiệm chính |
| Compute/storage | Theo pricing model dịch vụ | VM/node/disk/network riêng |
| Replication/HA | Theo capability/tier | Team thiết kế và vận hành |
| Monitoring | Tích hợp sẵn ở mức nào đó | Tự triển khai/duy trì |
| Scaling | Theo quota/plan/provider | Tự capacity plan |
| Customization | Có giới hạn | Linh hoạt hơn |
| Operational staffing | Thường thấp hơn | Có thể cao hơn đáng kể |
| Portability | Phụ thuộc API/format | Có thể chủ động hơn, nhưng không miễn phí |

Managed service có thể đắt hơn theo bill nhưng rẻ hơn theo total cost of ownership. Self-managed chỉ hợp lý nếu tổ chức có quy mô, năng lực vận hành và lý do kiểm soát đủ lớn.

## 43. Trade-off theo workload type

| Workload | Ưu tiên thường gặp | Trade-off cần xem |
|---|---|---|
| Transactional OLTP | Latency, consistency, durability | Replication, storage IOPS, backup |
| Search | Read latency, index availability | Derived storage, rebuild time |
| Analytics | Scan throughput, retention | Columnar storage, egress, compute |
| Event streaming | Throughput, replay, ordering | Broker partitions, retention, replication |
| Media/static assets | Delivery latency, bandwidth | CDN, cache, object tiers |
| Audit/ledger | Integrity, retention, traceability | Immutable storage, controlled access |
| Cache | Low latency, low compute | Memory cost, staleness, rebuild |
| Batch/ETL | Throughput, cost per record | Spot/preemptible compute, queue/backfill |

Không dùng một storage class, replication policy hoặc broker configuration cho mọi workload. Phân tầng theo **criticality, access pattern, consistency, RPO/RTO và retention**.

## 44. Quy trình đánh giá một thay đổi kiến trúc về chi phí

1. **Xác định business goal:** giảm latency, tăng availability, giảm bill hay tăng replay capability?
2. **Đo baseline:** requests, bytes, storage, broker lag, replicas, bill.
3. **Xây workload model:** average/peak/burst, data growth và retention.
4. **Liệt kê options:** gồm giữ nguyên hiện trạng, tối ưu code/config, đổi topology hoặc đổi dịch vụ.
5. **Ước lượng total cost:** direct, shared, operations, backup/DR và migration.
6. **Đánh giá non-functional:** SLO, security, consistency, RPO/RTO, privacy.
7. **Load test/benchmark:** dùng traffic mix gần thực.
8. **Pilot/canary:** giới hạn blast radius và theo dõi bill/runtime.
9. **So actual với forecast:** điều chỉnh assumptions.
10. **Ghi ADR và owner:** quyết định, guardrails, expiry/review trigger.

Không phê duyệt optimization chỉ dựa trên một bảng giá tĩnh nếu workload chưa được đo.

## 45. Những anti-pattern thường làm chi phí tăng

**1. Chatty microservices:** một business request tạo hàng chục network calls nhỏ và nhiều serialization overhead.

**2. Mọi service đều nhân bản toàn bộ database:** tăng storage, replication, privacy surface và consistency work.

**3. Cross-region calls cho mọi request:** tăng latency, transfer cost và failure dependencies.

**4. Dùng NAT tập trung không kiểm soát:** traffic đi vòng, tăng bytes processed và tạo bottleneck.

**5. Không có CDN/cache cho static content lớn:** origin egress và compute bị lặp.

**6. Message payload chứa file lớn:** broker storage/replication/network tăng không cần thiết.

**7. Retention vô hạn:** broker, database, logs và object storage tăng liên tục.

**8. Tăng partitions không có throughput evidence:** metadata/rebalance/operations overhead tăng.

**9. Consumer groups trùng chức năng:** cùng đọc và ghi các projection tương tự.

**10. Scale consumers mà bỏ qua database:** broker lag giảm nhưng DB connection/IOPS quá tải.

**11. Read replicas nhưng query vẫn sai:** tăng chi phí mà không giải quyết lock/index/hot partition.

**12. Replication factor cao trong cùng failure domain:** bill tăng nhưng resilience không tăng tương xứng.

**13. Dùng active-active cho mọi dataset:** conflict resolution và cross-region traffic quá phức tạp.

**14. Snapshot không có retention/owner:** orphan snapshots và changed blocks tăng.

**15. Backup toàn bộ dữ liệu dẫn xuất mà không xem khả năng rebuild:** lưu trữ trùng lặp đắt đỏ.

**16. Archive dữ liệu nhưng không test retrieval:** tiết kiệm storage nhưng không đạt RTO.

**17. Sampling telemetry bừa bãi:** giảm bill nhưng mất tín hiệu cần thiết để đo SLO/incident.

**18. Không có cost allocation:** không biết service/team nào tạo bill.

**19. Tối ưu một dịch vụ làm tăng chi phí dịch vụ khác:** ví dụ cache làm giảm DB nhưng tăng egress và invalidation.

**20. Coi cloud bill là chi phí duy nhất:** bỏ qua engineer time, incident risk, migration và support.

## 46. Checklist cho thiết kế mạng, broker, storage và replication

1. **Workload:** Có request rate, peak, payload size, message rate và data growth đã đo?
2. **Network:** Đã phân loại ingress, Internet egress, same-zone, cross-zone, cross-region?
3. **Topology:** Có traffic hairpin qua NAT/proxy/region không cần thiết?
4. **CDN/cache:** Có nội dung cacheable và cache key/security policy đúng?
5. **Broker:** Throughput, partitions, retention, replication factor và consumer groups dựa trên workload?
6. **Message size:** Có binary blobs/payload dư thừa không?
7. **Consumer:** Có lag, backpressure, bounded concurrency và DLQ policy?
8. **Storage:** Đã tính data, indexes, logs, snapshots, IOPS và request charges?
9. **Tiering:** Access pattern, retrieval time và legal retention đã rõ?
10. **Replication:** Mục tiêu là HA, read scaling, locality hay DR?
11. **Consistency:** Sync/async, lag và read-your-writes semantics có rõ?
12. **Failure domains:** Replica nằm ở đâu, có độc lập thực sự không?
13. **Backup:** Có độc lập với replica và có restore tests?
14. **Observability:** Telemetry volume, cardinality, retention và egress được kiểm soát?
15. **Cost allocation:** Service/owner/environment tags và unit economics có sẵn?
16. **Forecast:** Có model average/peak/growth và headroom khi mất zone?
17. **Trade-offs:** Có so SLO, RPO/RTO, security, consistency và operational cost?
18. **Evidence:** Có load test, billing export, canary và review sau triển khai?
19. **Ownership:** Ai theo dõi budget, alert và remediation?
20. **Lifecycle:** Có owner/retention cho topics, volumes, snapshots, backups và replicas?

## 47. Ví dụ tổng hợp: Thiết kế kiến trúc tiết kiệm nhưng vẫn đáp ứng SLO

Giả sử một nền tảng bán hàng cần:

- Order và Payment phải bền vững.
- Search có thể eventual consistency.
- Notification có thể xử lý bất đồng bộ.
- Reporting có thể chậm vài phút.
- Hóa đơn cần lưu lâu dài và mở được theo policy.
- Hệ thống cần chịu lỗi một zone và có DR region.

Một cấu trúc có thể là:

~~~text
Primary region
  |
  +-- API Gateway / CDN
  |
  +-- Order + Payment services
  |      |
  |      +-- Transactional databases
  |      |      +-- HA replicas across failure domains
  |      |      +-- PITR backup to protected storage
  |      |
  |      +-- Outbox
  |             |
  |             v
  |          Managed broker
  |             +-- Short operational retention
  |             +-- Replication across zones
  |             +-- Consumers with bounded concurrency
  |
  +-- Search projection
  |      +-- Rebuildable index
  |
  +-- Reporting pipeline
  |      +-- Raw event archive in object storage
  |      +-- Analytical storage tier
  |
  +-- Invoice objects
         +-- Versioning/retention policy
         +-- Protected cross-region copy

DR region
  +-- IaC/bootstrap definitions
  +-- Protected database backups / selected replicas
  +-- Artifact and configuration recovery
  +-- Controlled restore and traffic cutover
~~~

Trade-offs:

- CDN giảm egress/compute cho assets tĩnh.
- Database HA replicas phục vụ availability; PITR backups bảo vệ logical corruption.
- Broker retention ngắn hơn nếu raw event archive có thể replay trong RTO.
- Search index được rebuild thay vì backup mọi index version.
- Reporting dùng storage tier phù hợp access pattern.
- Invoice object có retention và integrity checks.
- DR region giữ đủ dữ liệu/hạ tầng theo RPO/RTO đã phê duyệt.
- Bounded consumers ngăn scale-out làm quá tải database.
- Billing tags và cost per order giúp nhìn tác động khi traffic tăng.

Đây là một **mẫu kiến trúc**, không phải cấu hình tối ưu cho mọi tổ chức. Các lựa chọn cuối cùng phải dựa trên provider pricing, data residency, workload và RPO/RTO thực.

## 48. Kết luận

Chi phí mạng, broker, lưu trữ và dữ liệu sao chép là hệ quả trực tiếp của cách kiến trúc di chuyển, giữ, nhân bản và phục vụ dữ liệu.

Một quyết định tốt cần trả lời được:

- **Dữ liệu đi đâu?** Ingress, egress, cross-zone, cross-region, NAT, CDN và consumer fan-out.
- **Dữ liệu được giữ ở đâu?** Broker retention, database, indexes, snapshots, backups, archive.
- **Dữ liệu được nhân bản vì sao?** HA, read scaling, locality, DR hay replay.
- **Mỗi bản sao có giá trị gì?** Consumer, freshness, SLO, owner và recovery path.
- **Chi phí được đo thế nào?** Bytes, requests, IOPS, GB-month, replication lag, cost per transaction.
- **Đánh đổi nào được chấp nhận?** Latency, consistency, availability, RPO/RTO, security và operational complexity.

**Câu hỏi tự kiểm tra:** *Nếu số đơn hàng tăng gấp ba, những bytes nào tăng theo request, broker, replication và backup; dữ liệu nào cần giữ nóng, dữ liệu nào có thể archive hoặc rebuild; và phương án giảm bill có còn đáp ứng consistency, security, RPO/RTO cùng SLO không?*

Một hệ thống quản lý chi phí tốt không chỉ tìm dịch vụ rẻ hơn. Nó hiểu rõ **vì sao mỗi byte, message, replica và snapshot tồn tại**, ai sở hữu chúng, lợi ích chúng mang lại và điều gì sẽ xảy ra nếu thay đổi chính sách.
