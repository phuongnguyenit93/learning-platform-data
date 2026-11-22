# Tối ưu vị trí xử lý, dữ liệu và khoảng cách địa lý

## 1. Vị trí triển khai là một quyết định hiệu năng

Một request có thể đi qua nhiều chặng: thiết bị người dùng, mạng ISP, CDN hoặc edge, load balancer, application service, cache, database và dịch vụ bên thứ ba. Dù từng thành phần xử lý nhanh, tổng thời gian vẫn có thể lớn nếu các thành phần ở xa nhau hoặc request phải qua nhiều lần truyền dữ liệu.

**Placement** là quyết định đặt compute, dữ liệu và các thành phần hạ tầng ở đâu: edge location, availability zone (AZ), region, quốc gia, trung tâm dữ liệu hoặc vị trí gần hệ thống on-premises. Mục tiêu không chỉ là giảm khoảng cách địa lý mà là giảm latency end-to-end trong khi vẫn đáp ứng tính đúng đắn dữ liệu, availability, bảo mật, residency, chi phí và khả năng vận hành.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc ứng dụng cloud được thiết kế từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Vì vậy, quyết định placement cần dựa trên latency budget và workload thực tế, đồng thời đánh giá đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài này, bạn có thể:

- Phân tích latency theo từng network hop và compute/data access.
- Chọn region, AZ, edge và CDN dựa trên phân bố người dùng cùng yêu cầu nghiệp vụ.
- Áp dụng data locality và data gravity để giảm truyền dữ liệu liên vùng.
- Chọn chiến lược multi-AZ, multi-region, active-active hoặc active-passive.
- Đánh giá replication lag, consistency, cache locality và write locality.
- Thiết kế edge processing cho workload cần phản hồi nhanh hoặc xử lý gần nguồn dữ liệu.
- Cân bằng performance với data residency, security, DR và chi phí egress.
- Kiểm chứng placement bằng latency telemetry, load test và failover exercise.

## 2. Đo khoảng cách bằng latency budget, không chỉ bằng bản đồ

### 2.1. Latency end-to-end

Thời gian người dùng chờ thường gồm nhiều thành phần:

\[
T_{\text{total}} =
T_{\text{client}} +
T_{\text{network}} +
T_{\text{queue}} +
T_{\text{compute}} +
T_{\text{data}} +
T_{\text{external}}
\]

Trong đó:

- Client: DNS lookup, connection setup, TLS handshake và xử lý trên thiết bị.
- Network: propagation, routing, packet loss và retransmission.
- Queue: thời gian chờ load balancer, worker, connection pool hoặc broker.
- Compute: CPU, memory, serialization, application logic.
- Data: cache/database read-write, lock, replication và storage I/O.
- External: thời gian gọi payment, identity, analytics hoặc API bên thứ ba.

Tách các thành phần này để biết placement nào thực sự tạo ra cải thiện. Nếu 80% latency nằm trong database lock, chuyển API sang region gần user có thể không giúp nhiều.

### 2.2. Latency budget

Ví dụ BookingCloud đặt mục tiêu p95 cho GET catalog dưới 250 ms:

| Thành phần | Budget minh họa |
|---|---:|
| DNS/connection/TLS và client overhead | 35 ms |
| Client tới edge/origin và network routing | 55 ms |
| API gateway và application compute | 45 ms |
| Cache/database read | 65 ms |
| Serialization và response transfer | 25 ms |
| Dự phòng biến động | 25 ms |
| **Tổng** | **250 ms** |

Các con số là budget mục tiêu, không phải latency cố định của một region/provider. Khi một thành phần vượt budget, nhóm phải biết ảnh hưởng lan tới SLO ra sao.

### 2.3. p50, p95 và p99

Khoảng cách địa lý tác động tới mọi request, nhưng queueing, routing và tải khiến phân phối latency có tail dài. Chỉ đo average có thể che giấu người dùng ở vùng xa hoặc request gặp cross-region hop.

- p50 cho biết trải nghiệm điển hình.
- p95 cho biết nhóm request chậm đáng kể.
- p99 giúp tìm tail latency, thường nhạy với queue, retry, cross-region dependency và cold path.

Hãy phân đoạn metric theo region người dùng, region xử lý, endpoint, workload class và cache status. Tránh label theo từng user/request ID làm cardinality tăng mạnh.

## 3. Khoảng cách vật lý và các loại độ trễ mạng

### 3.1. Propagation delay

Tín hiệu cần thời gian truyền qua cáp quang, tuyến mạng, thiết bị chuyển tiếp và các điểm peering. Một đường truyền dài hơn thường có propagation delay cao hơn, nhưng đường đi thực tế không phải đường thẳng trên bản đồ; routing, peering, congestion và topology có ảnh hưởng lớn.

Không nên tính latency chỉ bằng khoảng cách đường chim bay. Hai region gần nhau có thể có routing khác nhau; một điểm edge gần người dùng có thể vẫn phải quay về origin xa để đọc dữ liệu động.

### 3.2. Connection setup

Một request mới có thể tốn thời gian cho DNS, TCP handshake, TLS handshake và authentication. Reuse connection, HTTP/2 hoặc HTTP/3, keep-alive và connection pooling có thể giảm overhead, nhưng cần giới hạn pool, idle timeout và xử lý stale connection.

### 3.3. Network path

Đường đi có thể qua:

- ISP và public Internet.
- CDN/edge point of presence (PoP).
- Cloud backbone hoặc inter-region link.
- NAT gateway, firewall, proxy và service mesh sidecar.
- Private endpoint, VPN, transit gateway hoặc peering.

Mỗi hop có thể thêm latency và failure mode. Placement review cần vẽ path thật, xác minh DNS resolution, route, TLS termination và egress, thay vì chỉ nhìn region label.

## 4. Chọn region theo phân bố người dùng và yêu cầu nghiệp vụ

### 4.1. Những yếu tố quyết định

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| User geography | Người dùng chính ở quốc gia/vùng nào? Tải có phân bố đều không? |
| Latency objective | p95/p99 cần đạt bao nhiêu? Có thao tác realtime không? |
| Data residency | Dữ liệu nào phải lưu hoặc xử lý trong một quốc gia/khu vực? |
| Service availability | Region có đủ dịch vụ, SKU, quota và feature cần thiết? |
| Resilience | Có region thứ hai phù hợp để DR hoặc failover? |
| Dependency | Payment, identity, on-premises và partner endpoint nằm ở đâu? |
| Cost | Compute, storage, cross-region transfer, egress và support cost là bao nhiêu? |
| Operations | Đội vận hành có thể hỗ trợ timezone, incident và compliance không? |

Chọn region gần user không tự động là tối ưu nếu dữ liệu chính nằm ở nơi khác, external dependency chỉ có endpoint ở một khu vực, hoặc việc chuyển dữ liệu vi phạm residency policy.

### 4.2. Workload phân bố theo geography

BookingCloud có 75% user ở Việt Nam, 15% ở Singapore và 10% ở các thị trường khác. Một phương án có thể đặt primary application/data ở region phục vụ phần lớn khách hàng và dùng CDN cho static assets. Tuy nhiên cần đo latency tới region thực tế, kiểm tra provider service availability và xác minh yêu cầu dữ liệu.

Nếu user distribution thay đổi theo mùa hoặc chiến dịch, không nên dựa vào một snapshot ngắn. Hãy phân tích theo ngày, giờ, campaign và loại operation.

### 4.3. Region selection matrix

| Tiêu chí | Region A | Region B | Cách đánh giá |
|---|---|---|---|
| User p95 latency | 75 ms | 125 ms | Synthetic/user telemetry |
| Database latency | 8 ms | 2 ms | Data locality |
| Service/SKU coverage | Đủ | Thiếu một service | Provider capability |
| Data residency | Phù hợp | Cần review pháp lý | Data classification |
| DR pairing | Có | Có | Failover test |
| Monthly cost | Trung bình | Cao hơn | Full cost model |

Giá trị chỉ là ví dụ. Quyết định cuối phải dựa trên measurement và policy được xác minh, không suy từ tên region.

## 5. Availability Zone và placement bên trong region

### 5.1. Khi nào dùng multi-AZ?

Multi-AZ đặt workload trên nhiều failure domain độc lập trong cùng region. Mục tiêu thường là giảm rủi ro mất một AZ và tăng availability mà không tạo độ trễ địa lý lớn như multi-region.

Lưu ý:

- Load balancer cần health check và phân phối request tới target khỏe.
- Database cần replication/failover semantics được kiểm tra.
- Cache, queue và session state phải có mô hình chia sẻ hoặc replica phù hợp.
- Cross-AZ network transfer có thể tăng cost.
- Subnet, IP, security policy, KMS và endpoint phải có ở các AZ cần thiết.

### 5.2. Synchronous replication và latency

Nếu database ghi đồng bộ tới replica ở AZ khác, commit latency có thể tăng theo network round trip và storage acknowledgement. Đổi lại, failover có thể giảm data loss tùy cơ chế.

Không phải mọi hệ thống cần đồng bộ mọi dữ liệu. Có thể chia:

- Critical transaction cần durable acknowledgement và consistency rõ.
- Read replica có thể cập nhật bất đồng bộ.
- Cache hoặc search index có thể eventual consistency.
- Analytics/event projection có thể chấp nhận lag lớn hơn.

Chọn theo business invariant, không chỉ theo benchmark.

### 5.3. AZ affinity và anti-affinity

Scheduler có thể đặt replica gần nhau để tận dụng locality hoặc cố ý phân tán để giảm correlated failure. Với service stateless, thường nên có anti-affinity theo zone/host; với data-intensive workload, cần cân nhắc locality và replica placement.

Không đặt tất cả replica của một service trong cùng một AZ chỉ vì node ở đó rẻ hoặc image đã warm.

## 6. Data locality và data gravity

### 6.1. Data locality

Data locality là đặt compute gần dữ liệu mà nó đọc/ghi thường xuyên. Khi application và database cách xa nhau, mỗi query hoặc transaction có thể cần một hoặc nhiều network round trip. Một workflow nhiều query tuần tự sẽ khuếch đại latency.

Ví dụ application ở Region A gọi database ở Region B:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant A as App Region A
    participant B as Database Region B
    U->>A: API request
    A->>B: Query 1
    B-->>A: Result 1
    A->>B: Query 2
    B-->>A: Result 2
    A->>B: Query 3
    B-->>A: Result 3
    A-->>U: Response
    Note over A,B: Mỗi round trip cộng thêm network latency
~~~

Nếu mỗi DB round trip thêm 40 ms và request tuần tự ba lần, chỉ riêng phần network có thể thêm khoảng 120 ms, chưa kể query execution. Batch, join, data access redesign hoặc colocate service/data có thể hiệu quả hơn chuyển nguyên database.

### 6.2. Data gravity

Khi dữ liệu lớn và nhiều hệ thống phụ thuộc vào nó, việc di chuyển compute tới dữ liệu thường dễ hơn di chuyển dữ liệu tới compute. Đây là một cách diễn giải thực tiễn của data gravity.

Hãy xem xét:

- Kích thước dữ liệu và tốc độ tăng.
- Số service đọc/ghi thường xuyên.
- Chi phí egress/replication.
- Data residency và encryption/key location.
- Thời gian đồng bộ và recovery.
- Khả năng giữ cache/index/materialized view gần consumer.

### 6.3. Data locality không đồng nghĩa chỉ một bản dữ liệu

Có thể duy trì canonical data store và các read model/replica gần user. Nhưng phải xác định source of truth, update path, freshness SLA, invalidation, conflict handling và behavior khi link liên vùng mất.

Không tạo nhiều bản sao tùy tiện. Mỗi copy tăng chi phí, dữ liệu cần bảo vệ, phạm vi xóa/retention và khả năng divergence.

## 7. Chọn chiến lược placement cho ứng dụng và dữ liệu

### 7.1. Colocation

Đặt application service và data store chính trong cùng region, thường cùng AZ gần nhất khi cần. Ưu điểm là giảm round trip và đơn giản consistency. Đánh đổi là người dùng ở xa vẫn có latency cao và region trở thành failure domain lớn.

### 7.2. Regional read replicas

Giữ primary write database ở một region, tạo read replica hoặc projection ở region khác. Request đọc gần user được phục vụ tại địa phương; write chuyển về primary.

Đánh đổi:

- Replication lag có thể làm read sau write trả dữ liệu cũ.
- Failover/promote replica cần quy trình tránh split brain.
- Cross-region transfer và storage tăng cost.
- Query có thể không đọc được ngay dữ liệu vừa commit.

### 7.3. Regional write ownership

Với workload cần write local, có thể phân vùng ownership theo region/tenant/entity. Mỗi record có một nơi authoritative để tránh hai region cùng ghi không điều phối.

Ví dụ tenant Việt Nam ghi tại region A, tenant Singapore ghi tại region B; truy cập chéo region có thể đọc qua API có kiểm soát. Cần thiết kế migration tenant, cross-region collaboration và disaster recovery.

### 7.4. Active-active multi-region

Nhiều region cùng nhận traffic và có thể nhận write. Điều này tăng khả năng phục vụ gần user và resilience, nhưng khó hơn về consistency, conflict resolution, global identity, replication ordering, idempotency và failover.

Chỉ chọn active-active khi latency/availability requirement đủ mạnh để biện minh cho complexity. Không coi “có hai region” là active-active nếu write vẫn chỉ đi về một primary.

### 7.5. Active-passive

Một region xử lý traffic chính; region thứ hai standby hoặc chạy footprint nhỏ. Khi failover, chuyển traffic và promote/recover data theo RTO/RPO. Mô hình đơn giản hơn active-active nhưng failover có thể chậm và DR region cần quota/capacity sẵn sàng.

~~~mermaid
flowchart TB
    USERS["Users in multiple locations"] --> ROUTER["Global traffic manager"]
    ROUTER --> RA["Primary region"]
    ROUTER -. "Failover" .-> RB["DR region"]
    RA --> APPA["Application"]
    APPA --> DBA[("Primary database")]
    DBA -. "Replication" .-> DBB[("Standby replica")]
    RB --> APPB["Warm standby application"]
    APPB --> DBB
~~~

## 8. Replication, consistency và read-after-write

### 8.1. Replication lag

Asynchronous replication xác nhận write tại primary trước khi replica nhận và apply. Khoảng trễ có thể biến động theo write rate, network, log shipping và replica capacity.

Metric quan trọng:

- Replication lag theo thời gian và bytes/LSN/offset.
- Apply throughput và queue/backlog.
- Cross-region network errors.
- Oldest unreplicated event.
- Failover readiness và data loss estimate.

### 8.2. Read-after-write

Một user cập nhật booking ở Region A rồi request tiếp theo được route sang read replica Region B. Nếu replica chưa nhận update, user có thể thấy trạng thái cũ.

Các lựa chọn:

- Sticky/session routing về primary trong khoảng ngắn.
- Đọc từ primary khi operation cần read-after-write.
- Trả version/commit token và đợi replica đạt version.
- Dùng bounded wait rồi fallback về primary hoặc trả trạng thái pending.
- Chấp nhận eventual consistency nếu business cho phép.

Không giả định replica luôn đủ mới chỉ vì ở cùng cloud provider.

### 8.3. Conflict và ownership

Với multi-writer, hai region có thể cập nhật cùng entity đồng thời. Phải định nghĩa conflict resolution: single-writer per key, version/vector clock, last-write-wins (chỉ phù hợp với một số dữ liệu), CRDT hoặc domain-specific merge.

Với booking slot, last-write-wins có thể gây double booking; cần transaction/locking hoặc authoritative inventory service. Không chọn replication model chỉ dựa trên khả năng đồng bộ của database.

## 9. Edge và CDN: xử lý gần người dùng

### 9.1. CDN

CDN lưu cache nội dung tại các edge PoP gần user. Thường phù hợp:

- Static assets: JS, CSS, image, font.
- Public product images và nội dung công khai.
- Một số API response có cache policy rõ.
- Large file delivery và streaming.

CDN giảm origin load và round trip cho cache hit. Cache miss vẫn phải tới origin; nội dung dynamic/private cần Cache-Control, vary key, authorization, invalidation và TTL phù hợp.

Không cache response chứa dữ liệu người dùng riêng tư tại shared cache nếu cache key không bao gồm security scope hoặc policy không bảo đảm isolation.

### 9.2. Edge compute

Edge compute chạy logic gần user/thiết bị, ví dụ:

- Redirect, routing và request normalization.
- Authentication token validation hoặc policy check phù hợp.
- A/B test, personalization không nhạy cảm.
- Image transformation, compression, content filtering.
- Lightweight API aggregation hoặc cache lookup.
- IoT protocol translation và xử lý gần nguồn sự kiện.

### 9.3. Những việc không nên đẩy ra edge một cách tùy tiện

- Transaction cần atomicity với central data store.
- Business logic phụ thuộc nhiều dữ liệu authoritative.
- Workflow cần state nhất quán toàn cục.
- Chức năng đòi hỏi secret lớn hoặc quyền truy cập quá rộng ở nhiều PoP.
- Dữ liệu bị giới hạn residency nếu edge location nằm ngoài vùng được phép.

Edge giảm độ trễ cho một số bước, nhưng có thể thêm complexity trong deployment, debugging, secret distribution, version consistency và data governance.

## 10. Placement cho workload đặc thù

| Workload | Placement gợi ý | Lưu ý |
|---|---|---|
| Public static content | CDN/edge | Cache key, TTL, purge và origin protection |
| API read-heavy | Region gần user + local cache/read replica | Freshness, replication lag và invalidation |
| Transactional write | Gần authoritative database/leader | Consistency và idempotency |
| Batch analytics | Gần data lake/warehouse | Di chuyển compute tới dữ liệu lớn |
| Video/image processing | Edge ingress hoặc compute gần object storage | Egress, GPU capacity và object transfer |
| IoT ingestion | Regional ingress gần thiết bị | Buffer, local processing và link outage |
| Payment integration | Theo provider endpoint/contract và data policy | Idempotency, audit và secure egress |
| Search/vector index | Gần consumer hoặc regional partition | Index freshness và reindex cost |
| DR/backup | Region failure domain riêng | RPO/RTO, key availability và restore test |

## 11. Placement và data residency/security

Khoảng cách thấp không được phép làm suy yếu yêu cầu dữ liệu.

### 11.1. Phân loại dữ liệu

Trước khi chọn region, phân loại:

- Public content.
- Internal business data.
- Personal data.
- Financial/payment metadata.
- Authentication/identity data.
- Security logs/audit records.
- Backup, replica, cache và derived data.

Yêu cầu residency có thể áp dụng cho storage, processing, backup, support access hoặc transfer. Cần kiểm tra nghĩa vụ pháp lý/hợp đồng theo dữ liệu và thị trường cụ thể; không suy ra chỉ từ nơi đặt database.

### 11.2. Replication cũng là data transfer

Cross-region replication, log shipping, backup copy, analytics export và cache fill đều có thể chuyển dữ liệu ra ngoài region. Kiểm tra encryption, key, destination authorization, retention và legal basis.

### 11.3. Edge location và dữ liệu

Edge code có thể xử lý metadata hoặc payload tại nhiều quốc gia. Cần biết request body, log, cache và secret nào được lưu tại PoP; thời gian giữ; ai có quyền truy cập; và dữ liệu nào phải gửi về origin.

## 12. Chi phí của placement và khoảng cách

Một kiến trúc gần user hơn có thể giảm latency nhưng tăng chi phí do nhiều region, replica, data transfer, endpoint và vận hành.

### 12.1. Cost components

- Compute và standby capacity ở từng region.
- Database replica, storage và backup copy.
- Inter-AZ và inter-region data transfer.
- Internet egress, CDN origin fetch và cache fill.
- Private endpoint, NAT gateway và transit traffic.
- Replication log, stream và broker throughput.
- Monitoring, log ingestion và trace export.
- On-call/support và complexity vận hành.

### 12.2. Cost per request và latency value

Có thể so sánh:

\[
\text{Cost per successful request} =
\frac{\text{Total placement-related cost}}
{\text{Successful requests}}
\]

Nên kết hợp với p95/p99, conversion, booking completion hoặc business outcome. Giảm 30 ms latency không nhất thiết đáng giá nếu cần thêm hai database region đắt tiền mà business không cần.

### 12.3. Data transfer amplification

Một request API nhỏ có thể kích hoạt nhiều lần truy vấn, query result lớn, log/trace export và cache replication. Tổng bytes liên vùng có thể lớn hơn payload client nhiều lần. Cần đo bytes theo source/destination/workload, không chỉ nhìn egress bill tổng.

## 13. Đo lường và kiểm chứng placement

### 13.1. Instrument theo user region và processing region

Ghi nhận các thuộc tính an toàn:

- Client region/country ở mức aggregate phù hợp.
- Serving region/AZ.
- Origin/data region.
- CDN PoP/cache status.
- Dependency region/endpoint.
- Request route và workload version.
- Cross-region bytes và latency.

Không ghi IP/user location chi tiết nếu không có mục đích và quyền hợp lệ; có thể dùng geolocation ở mức vùng hoặc sample.

### 13.2. Network test

- Synthetic probes từ các vùng người dùng quan trọng.
- DNS resolution và TLS handshake duration.
- TCP connect, packet loss, retransmission và route.
- Application request p50/p95/p99.
- Cross-region round-trip benchmark.
- Throughput test cho transfer/replication.

### 13.3. Database/data test

- Query latency từ từng app region.
- Connection pool wait và query plan.
- Replication lag dưới peak write.
- Read-after-write correctness.
- Failover RTO/RPO và split-brain prevention.
- Cache hit, freshness và invalidation delay.

### 13.4. So sánh trước/sau

Khi thay placement, dùng cùng workload mix, dataset, request distribution và thời gian quan sát. So sánh:

| Chỉ số | Baseline | Sau thay đổi |
|---|---:|---:|
| User p95 latency | Đo thực tế | Đo cùng điều kiện |
| p99 latency | Đo thực tế | Đo cùng điều kiện |
| Database round trips | Đếm/query | Đếm/query |
| Cross-region bytes | Bytes/period | Bytes/period |
| Replication lag | p95/max | p95/max |
| Error/timeout rate | Rate | Rate |
| Cost per request | Cost/request | Cost/request |

Chỉ kết luận placement tốt hơn nếu cải thiện có ý nghĩa và không phá consistency, availability, security hoặc cost objective.

## 14. Kiến trúc tham chiếu cho BookingCloud

Giả sử phần lớn người dùng ở một thị trường, có một nhóm user ở khu vực lân cận và hệ thống phục vụ catalog read-heavy cùng booking transactional.

~~~mermaid
flowchart TB
    U1["Users: primary market"] --> EDGE1["Nearby CDN / edge"]
    U2["Users: nearby markets"] --> EDGE2["Regional CDN / edge"]
    EDGE1 --> ROUTE["Global / regional routing"]
    EDGE2 --> ROUTE
    ROUTE --> APP["Primary application region"]
    APP --> DB[("Authoritative booking DB")]
    APP --> CACHE["Regional cache"]
    APP --> OBJ[("Object storage")]
    APP -. "Async read replication" .-> READ["Regional read model"]
    EDGE1 --> STATIC["Cached public assets"]
    EDGE2 --> STATIC
    READ --> APPNEAR["Regional read API"]
~~~

Phân tách flow:

- Catalog/static content có thể được phục vụ từ CDN và cache gần user.
- Booking write đi tới authoritative service/database để bảo vệ inventory invariant.
- Read model có thể được replicate gần nhóm user khác nếu freshness cho phép.
- Payment gọi endpoint phù hợp theo provider contract; không thêm cross-region hop không cần thiết.
- Backup/DR đặt ở failure domain đáp ứng RPO/RTO và residency.

## 15. Bài thực hành: tối ưu placement cho BookingCloud

BookingCloud phục vụ người dùng ở ba vùng. Hiện tại application và database cùng Region A. Một số user ở Region C có p95 API 420 ms. Catalog là read-heavy; booking write cần tránh double-booking. Database có read replica ở Region C nhưng lag thay đổi 0,5–8 giây. Chi phí cross-region data transfer đang tăng.

Hãy thực hiện:

**Bài 1 — Latency decomposition:** đo DNS/TLS, network, compute, cache/database và external calls; xác định phần nào gây p95 420 ms.

**Bài 2 — User geography:** phân tích traffic theo market, giờ cao điểm và endpoint. Chọn region/edge theo p95/p99 thay vì khoảng cách bản đồ.

**Bài 3 — Data locality:** xác định query nào nên đọc replica, query nào phải đọc primary; đề xuất read-after-write strategy.

**Bài 4 — Placement alternatives:** so sánh colocated single-region, regional read replica, regional write ownership và active-active.

**Bài 5 — Edge/CDN:** chọn nội dung có thể cache ở edge; xác định cache key, TTL, invalidation và dữ liệu tuyệt đối không cache shared.

**Bài 6 — Consistency:** xử lý trường hợp user đặt booking ở Region A rồi được route tới read replica Region C đang lag.

**Bài 7 — DR:** đề xuất multi-AZ/multi-region, RTO/RPO, quota/capacity và data replication; tính cả residency.

**Bài 8 — Cost:** đo inter-region bytes, replica cost, CDN hit ratio và cost per successful booking.

**Bài 9 — Verification:** tạo synthetic probes, load test, failover test và so sánh baseline.

### Khung kết quả tự kiểm tra

| Quyết định | Cần chứng minh |
|---|---|
| Chuyển compute gần user | Giảm network latency thực tế, không chỉ giảm khoảng cách địa lý |
| Giữ write tại primary | Bảo toàn consistency và booking invariant |
| Đọc replica vùng xa | Có freshness bound và fallback khi lag vượt ngưỡng |
| Đưa content ra CDN | Cache policy không làm lộ dữ liệu riêng tư |
| Multi-region | RTO/RPO, quota, identity, key và residency đều khả thi |
| Giảm inter-region traffic | Bớt round trip/bytes mà không tạo stale hoặc mất dữ liệu |
| Tối ưu cost | Cost per successful request và user-visible SLO cải thiện |

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu placement map, region routing và replication health? | Service map, synthetic probes, runbook, failover exercise |
| **Security** | Data transfer, edge processing và replica có đáp ứng identity, encryption và residency? | Data classification, route policy, encryption, access audit |
| **Reliability** | Mất region/link hoặc replication lag cao thì hệ thống hoạt động ra sao? | RTO/RPO, multi-AZ/region tests, authoritative write model |
| **Performance Efficiency** | Compute/data đặt gần request path? Có cross-region round trip dư? | p95/p99 by region, trace, network and query metrics |
| **Cost Optimization** | Replica, egress, CDN và standby có tạo giá trị tương xứng? | Cost per request, bytes transferred, cache hit, utilization |
| **Sustainability** | Có nhân bản dữ liệu/compute quá mức hoặc truyền byte không cần thiết? | Data lifecycle, deduplication, placement utilization, egress trends |

Tối ưu placement là tối ưu toàn bộ hành trình dữ liệu. Một compute region gần user nhưng database ở xa có thể làm request chậm hơn; một replica gần user nhưng lag lớn có thể làm kết quả sai; một edge function nhanh nhưng tạo thêm dữ liệu nhạy cảm ở nhiều quốc gia có thể tăng rủi ro.

## 17. Checklist trước khi thay đổi placement

- [ ] Có latency budget và phân rã network/queue/compute/data/external.
- [ ] Đã đo p50/p95/p99 theo user region, serving region và endpoint.
- [ ] Có bản đồ user distribution và demand theo thời gian.
- [ ] Đã kiểm tra provider service/SKU/quota, network path và peering.
- [ ] Compute được đặt gần dữ liệu authoritative hoặc có read model phù hợp.
- [ ] Read/write ownership, consistency và replication lag được định nghĩa.
- [ ] Multi-AZ/region có RTO/RPO, failover path và capacity/quota dự phòng.
- [ ] CDN/edge cache có key, TTL, invalidation và privacy policy rõ.
- [ ] Data residency, backup, log, cache và edge processing được review.
- [ ] Cross-region transfer, NAT, endpoint, replication và observability cost được tính.
- [ ] Synthetic probes, load test và failover test đã đo trước/sau.
- [ ] Có fallback khi replica lag, region outage hoặc route/DNS không khả dụng.
- [ ] Monitoring có replication lag, cross-region bytes, p95/p99 và user impact.
- [ ] Runbook và owner cho global routing/data failover đã được cập nhật.

Tối ưu vị trí xử lý và dữ liệu cần dựa trên latency budget, locality và semantics của workload. Đưa compute gần user có thể giảm network delay; đặt compute gần data có thể giảm round trip và transfer; edge/CDN có thể phục vụ nội dung cacheable nhanh hơn. Nhưng mọi lựa chọn phải giữ consistency, data residency, security, failover và chi phí trong giới hạn đã cam kết. Đo lường end-to-end và kiểm thử failure mới chứng minh được placement thực sự tốt hơn.
