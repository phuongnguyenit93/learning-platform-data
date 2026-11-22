# High availability, scaling và theo dõi Redis

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng trên Azure. Ở chương **Cache và giao tiếp thời gian thực**, bài học này hướng dẫn thiết kế **Redis có tính sẵn sàng cao (high availability – HA)**, lựa chọn phương án **scaling** và xây dựng **monitoring/alerting** đủ tin cậy để vận hành ứng dụng Java.

Giả sử nền tảng đặt hàng có 12 replicas của `orders-api` trên AKS, truy vấn Azure SQL Database và dùng Redis để cache chi tiết sản phẩm, cấu hình khuyến mại và một số dữ liệu session không mang tính giao dịch. Redis làm giảm áp lực truy vấn database và cải thiện độ trễ p95. Nhưng lúc Redis primary failover, một số requests nhận lỗi kết nối; nếu toàn bộ API lập tức truy vấn database không giới hạn, database có thể bị quá tải. Nếu tiếp tục scale ứng dụng lên 40 pods mà mỗi pod tạo quá nhiều kết nối Redis, sự cố càng lan rộng. Vì vậy, kiến trúc phải trả lời ba câu hỏi:

1. **HA:** Redis hỏng một node thì dữ liệu và dịch vụ ứng xử ra sao? Những gì thực sự được bảo đảm?
2. **Scaling:** Tăng sức mạnh một node, thêm shards hoặc điều chỉnh ứng dụng khi traffic/memory tăng thế nào?
3. **Monitoring:** Dựa vào tín hiệu nào để phát hiện quá tải, failover, memory pressure, hot keys và hiệu ứng domino sang database?

Sau bài học, bạn có thể:

- Phân biệt **Azure Managed Redis** với những triển khai **Azure Cache for Redis** hiện hữu; không áp cấu hình của một sản phẩm/tier cho tất cả.
- Giải thích **primary/replica**, replication, failover, zone redundancy, persistence, RPO/RTO và giới hạn dữ liệu cache.
- Lựa chọn **scale up/scale out**, hiểu Redis Cluster, shards, hash slots, hot keys và rủi ro trong lúc resharding.
- Thiết kế **cache-aside**, TTL, eviction, fallback, request coalescing và giới hạn tải database khi Redis gián đoạn.
- Dùng **Java Spring Data Redis/Lettuce** và các chính sách timeout/retry/circuit breaker có giới hạn.
- Theo dõi Redis qua **Azure Monitor, Metrics Explorer, diagnostic settings**, application metrics và logs/traces.
- Xây dashboard, alert, runbook failover, load test và kiểm soát chi phí, bảo mật mạng/TLS.

## 1. Redis làm gì trong hệ thống?

**Redis** là kho dữ liệu in-memory có độ trễ thấp, thường được dùng làm cache, rate limiter, session store và cho một số bài toán dữ liệu thời gian thực. Khi được triển khai như **cache-aside**, Redis không phải nguồn sự thật duy nhất; dữ liệu nghiệp vụ bền vững nằm trong database hoặc hệ thống được chỉ định.

```text
Client
  |
  v
Orders Java API (AKS/App Service)
  |
  +---- GET product:1042 ---> Redis
  |                             |
  |                 Hit <--------+
  |                  |
  |                  v
  |             Return cached response
  |
  +---- Miss / Redis unavailable
                   |
                   v
             Azure SQL Database
                   |
                   v
       Có thể lưu lại vào Redis với TTL
                   |
                   v
              Return response
```

**Cache hit:** tìm thấy dữ liệu hợp lệ trong Redis. **Cache miss:** không có key, đã hết TTL hoặc dữ liệu bị eviction. **Cache unavailable:** lỗi kết nối, authentication, timeout hoặc cluster không thể phục vụ thao tác; tình huống này không đồng nghĩa với miss và cần metric riêng.

### 1.1. Những gì không nên chỉ lưu trong Redis cache

| Dữ liệu | Redis có thể dùng | Nguồn sự thật nên là |
|---|---|---|
| Danh mục sản phẩm, cấu hình đọc nhiều | Cache-aside, TTL, invalidation | Database/config service |
| Trạng thái đơn hàng tài chính | Cache một projection đọc có kiểm soát | Transactional database |
| Giỏ hàng/session tạm thời | Tùy yêu cầu mất dữ liệu, TTL, replication và persistence | Cần xem tính quan trọng của phiên và chiến lược phục hồi |
| Khóa phân tán | Chỉ khi đã phân tích failure semantics | Database constraints/transaction hoặc cơ chế coordination phù hợp |
| Access token/secret | Không tùy tiện cache plaintext | Identity/secrets store chuyên trách với kiểm soát truy cập |
| Counter/leaderboard | Có thể phù hợp Redis data structures | Cần đánh giá RPO, durability và consistency |

Với dữ liệu quan trọng, một lỗi Redis không được biến thành lỗi ghi tài chính hoặc thay đổi logic thanh toán. **Không coi việc Redis có replica là bằng chứng mọi write đã bền vững.**

### 1.2. Redis khác hệ thống quan hệ ở đâu?

Redis ưu tiên access time thấp và các data structures (string, hash, sorted set, stream, v.v. theo engine/configuration). Dù hỗ trợ atomic operations/transactions trong phạm vi xác định, Redis không tự thay thế ACID transactions, relational constraints hay audit history của Azure SQL/PostgreSQL. Cần chọn công nghệ theo semantics dữ liệu, không chỉ theo tốc độ benchmark.

## 2. Chọn dịch vụ Redis trên Azure theo vòng đời sản phẩm

Trong tài liệu Azure, bạn có thể gặp **Azure Managed Redis** và **Azure Cache for Redis** (bao gồm các triển khai/tier trước đây). Đây **không** phải cùng một tên giao diện hoặc tập tính năng trong mọi thời điểm.

| Tiêu chí | Azure Managed Redis | Azure Cache for Redis hiện hữu |
|---|---|---|
| Hướng sử dụng | Dịch vụ Redis được Azure quản lý cho triển khai mới theo khả năng hiện hành | Nhiều hệ thống cũ đang chạy với Basic/Standard/Premium/Enterprise và những biến thể có sẵn |
| HA, clustering, persistence | Phụ thuộc cấu hình, SKU và khả năng của dịch vụ | Có sự khác nhau đáng kể giữa các tiers |
| Zone redundancy/geo-distribution | Xác minh region, SKU và topology được hỗ trợ | Không mặc định có trên mọi instance/tier |
| Endpoint, port và authentication | Lấy từ resource thực tế | Có thể khác giữa classic Redis và Enterprise offerings |
| Metrics/diagnostics | Xem danh sách metric/dimensions thực tế của resource | Tên metrics và categories có thể khác |
| Kế hoạch dài hạn | Kiểm tra roadmap/support và pricing đang áp dụng | Với triển khai cũ cần đánh giá kế hoạch di chuyển và mốc hỗ trợ được Microsoft công bố |

**Quy tắc vận hành:** trước khi làm theo lệnh/tài liệu, xác định **tên sản phẩm, tier/SKU, Redis engine/version, region, topology, authentication và endpoint** thực tế. Đừng suy rằng `az redis ...` của một Azure Cache for Redis classic áp dụng cho mọi Azure Managed Redis instance. Nếu tổ chức đang có cache cũ, đánh giá migration một cách có kế hoạch; **không** đổi dịch vụ production theo tên gọi mới mà chưa kiểm thử compatibility, failover và dữ liệu.

### 2.1. Những câu hỏi cần hỏi trước khi triển khai

1. Redis chỉ là cache có thể làm đầy lại hay lưu trạng thái có yêu cầu không mất dữ liệu?
2. Cần chịu được mất một node, mất một availability zone hay cả region?
3. Latency SLO là bao nhiêu? Traffic đọc/ghi có phân bố đều không?
4. Keyspace và kích thước dữ liệu tăng thế nào? Có hot keys/big keys?
5. Application clients có hỗ trợ cluster-aware routing, TLS và credential refresh không?
6. Cần multi-region reads hay active-active writes? Chấp nhận consistency/conflict semantics gì?
7. Budget gồm instance, network, logs, compute, replication và downtime dự kiến thế nào?

## 3. Các mức tính sẵn sàng cao của Redis

**High availability** là khả năng dịch vụ tiếp tục hoặc phục hồi cung cấp chức năng khi một thành phần lỗi. Nó không đồng nghĩa **zero downtime**, **zero data loss** hay **mỗi request luôn thành công**.

```text
AZ-1                                   AZ-2
+-------------------+                  +-------------------+
| Redis primary     |--replication---->| Redis replica     |
| Reads/Writes*     |                  | Standby / reads*  |
+-------------------+                  +-------------------+
          |                                       |
          +------ Redis service endpoint ---------+
                                 |
                     Java client có reconnect/refresh

* Khả năng đọc từ replica, zone placement và routing
  phụ thuộc sản phẩm/tier/cấu hình thực tế.
```

### 3.1. Primary và replica

Trong một topology primary/replica phổ biến:

- **Primary** nhận write cho tập dữ liệu/shard liên quan.
- **Replica** nhận bản sao dữ liệu để dùng khi failover và/hoặc phục vụ đọc nếu topology cho phép.
- **Replication thường bất đồng bộ** trong Redis; replica có thể chưa nhận toàn bộ write mới nhất lúc primary lỗi.
- Một cơ chế quản lý failover chọn replica phù hợp làm primary mới theo dịch vụ.
- Clients cần phát hiện và kết nối đúng endpoint/role sau topology change.

Nếu ứng dụng dùng Redis cache để tăng tốc đọc và dữ liệu có thể tái tạo từ Azure SQL, mất một vài keys cuối cùng có thể là **cache miss** chấp nhận được. Nhưng với dữ liệu chỉ tồn tại trong Redis, cùng sự kiện đó có thể là **mất dữ liệu nghiệp vụ**.

### 3.2. Failover có những giai đoạn nào?

```text
T0   Primary xử lý requests bình thường
T1   Primary mất kết nối hoặc bảo trì
T2   Dịch vụ phát hiện lỗi, thực hiện election/promote theo topology
T3   Có giai đoạn kết nối mới hoặc writes thất bại/timeout
T4   Replica phù hợp được promote; topology/endpoints thay đổi
T5   Java clients reconnect/refresh cluster topology
T6   Cache hoạt động lại; dữ liệu có thể cần warm-up
```

Các mốc chỉ minh họa. **Thời gian failover** thực tế phụ thuộc dịch vụ, tier, tải, topology, điều kiện lỗi và cách client phát hiện/retry. Không đưa một thời gian RTO cố định nếu chưa có SLA/tài liệu chính thức áp dụng cho SKU và chưa kiểm thử trong môi trường của bạn.

### 3.3. Availability Zones

**Zone redundancy** khi được dịch vụ/SKU/region hỗ trợ nhằm giảm rủi ro lỗi một datacenter zone. Muốn đạt mục tiêu chịu mất zone:

1. Chọn một cấu hình cache hỗ trợ phân bố node/replica trên nhiều zones.
2. Xác minh Redis resource được triển khai đúng zones chứ không chỉ region có nhiều zones.
3. Đảm bảo **Java app, ingress, VNet, DNS, database** cũng có kế hoạch chịu mất zone.
4. Kiểm thử failover và latency từ các application zones thực tế.

**Một Redis zone-redundant nhưng Azure SQL chỉ có một điểm lỗi chưa được bảo vệ không tạo HA end-to-end.** Cần phân tích toàn request path.

### 3.4. Replication, persistence và backup khác nhau

| Khả năng | Giải quyết | Không tự giải quyết |
|---|---|---|
| **Replication** | Có bản sao để failover và/hoặc đọc tùy topology | Chưa chắc nhận write mới nhất, không chống xóa nhầm lan sang replica |
| **Zone redundancy** | Giảm rủi ro mất một availability zone | Không thay disaster recovery đa vùng |
| **Persistence RDB/AOF** (nếu hỗ trợ) | Lưu snapshots/log ghi để khôi phục dữ liệu theo cơ chế | Không đồng nghĩa mỗi write luôn durable hoặc RPO=0 |
| **Backup/export** (nếu hỗ trợ) | Phục hồi dữ liệu tại điểm lưu | Có RPO, tốn thời gian restore, phải kiểm thử khôi phục |
| **Geo-replication** (nếu hỗ trợ) | Có bản sao/ứng dụng dữ liệu sang region khác | Không luôn là zero loss hoặc automatic disaster failover |
| **Cache-aside + database SoT** | Dữ liệu cache có thể tái dựng | Khi Redis rớt, DB có thể chịu áp lực lớn |

Tùy tier, persistence có thể không có hoặc có các giới hạn khác nhau. Không hứa dữ liệu bền vững chỉ vì resource có tên “managed”.

## 4. RPO, RTO, SLO và failure domains

**RTO (Recovery Time Objective)** là thời gian tối đa mục tiêu để khôi phục chức năng. **RPO (Recovery Point Objective)** là mức mất dữ liệu theo thời gian mà hệ thống có thể chấp nhận.

Ví dụ với dữ liệu cache:

| Workload Redis | Ví dụ RPO | Ví dụ RTO | Thiết kế |
|---|---|---|---|
| Product cache | Có thể mất toàn bộ cache vì có database nguồn | Có thể chấp nhận vài phút degraded performance | Cache-aside, fallback bounded, warm-up |
| Session store | Có thể chấp nhận mất một số session hoặc phải đăng nhập lại, tùy sản phẩm | Mục tiêu phục hồi nhanh | HA topology, TTL, UX failover và cân nhắc persistence |
| Rate limiter | Mất counter có thể ảnh hưởng chống abuse | Mục tiêu có phương án degrade | Thiết kế fail-open/fail-closed theo risk, giới hạn tại edge |
| Payment ledger | Không phù hợp làm nguồn thật trong cache | Tính nhất quán nghiêm ngặt | Dùng transactional database/ledger, Redis chỉ làm acceleration |

Các con số RPO/RTO phải được xác nhận với chủ sản phẩm và kiểm thử, không suy ra từ SLA chung. Có thể có **HA ở cấp Redis** nhưng ứng dụng không đạt SLO vì retry lâu, connection pool không refresh hoặc traffic đổ ồ ạt xuống database.

### 4.1. Failure domains cần xem

- **Process:** một Redis process lỗi.
- **Node/host:** VM/host hoặc phần mềm host lỗi.
- **Zone:** một Availability Zone gián đoạn.
- **Region:** sự cố khu vực Azure.
- **Network/DNS:** Redis vẫn khỏe nhưng clients không kết nối được.
- **Client/application:** bug, config/credential hết hạn, hot key, retry storm.
- **Operator:** xóa key nhầm, thay policy/scale sai, flush, migration lỗi.

Không có một cấu hình HA duy nhất xử lý tất cả failure domains. Các lớp khác nhau cần các runbook và tests riêng.

## 5. Data consistency trong lúc failover

Một Redis write được primary trả success có thể chưa được sao chép đầy đủ sang replica khi primary mất đột ngột. Trong topology replication bất đồng bộ, lần đọc sau failover có thể không thấy write gần đây nhất.

```text
Java --> SET order:1042 PENDING --> primary ACK
                                    |
                               replication lag
                                    |
                             primary bị lỗi
                                    |
                                  promote replica
                                    |
Java --> GET order:1042 --> có thể miss hoặc thấy bản cũ
```

Nếu key là **cache projection từ database**, ứng dụng nên đọc database để tái tạo. Nếu key lại được dùng như quyết định duy nhất “đơn đã thanh toán”, thiết kế rất nguy hiểm.

### 5.1. Có nên dùng WAIT để ép đồng bộ replica?

Redis có lệnh như `WAIT` để đợi một số replicas xác nhận đã nhận write theo semantics của engine. Tuy nhiên, **acknowledgment replication không biến hệ thống thành kho dữ liệu có giao dịch bền vững tuyệt đối**; vẫn có các tình huống crash/persistence/failover dẫn tới mất dữ liệu. Dịch vụ managed có thể giới hạn lệnh hay topology. Không dùng `WAIT` như thay thế cho database transaction và RPO planning.

### 5.2. Tính nhất quán của cache-aside

Khi một record thay đổi trong Azure SQL:

1. Transaction cập nhật database thành công.
2. Ứng dụng xóa/đánh dấu invalid cache key sau commit.
3. Request sau thấy miss và đọc bản mới từ database.
4. Key được cache lại với TTL.

Vẫn có các race conditions: một request cũ có thể đọc dữ liệu DB trước commit rồi ghi lại cache sau invalidation. Cần cân nhắc TTL ngắn, versioned keys/values, event invalidation, optimistic version checks và read-after-write strategy theo mức nhất quán mong muốn.

**Cache invalidation không có exactly-once guarantee xuyên SQL + Redis** nếu không có workflow bền vững. Với dữ liệu nhạy cảm hoặc chính xác theo giao dịch, có thể bỏ cache cho đường truy vấn đó.

## 6. Failover tự động không đồng nghĩa client tự phục hồi đúng

Trong một sự kiện failover, Java có thể nhận:

- Connection reset/EOF/TLS socket close.
- Command timeout dù server đang bắt đầu phục hồi.
- Redirect/moved topology khi dùng Redis Cluster.
- Lỗi tạm thời liên quan loading, primary election hoặc slot migration.
- Cache miss do dữ liệu chưa sao chép hoặc bị eviction.

Ứng dụng cần **giới hạn timeout**, refresh connection/topology và chỉ retry thao tác phù hợp. Một instance Redis khỏe trở lại không bảo đảm tất cả TCP connections cũ còn có giá trị.

### 6.1. Retry GET khác retry write

| Command/workflow | Retry sau timeout? | Vì sao |
|---|---|---|
| `GET product:42` | Thường có thể retry một lần theo deadline, hoặc fallback DB | Đọc idempotent khi giá trị có thể tái tạo |
| `SET key value EX 300` | Có thể an toàn hơn nếu cùng value/version/TTL semantics phù hợp | Phải kiểm tra yêu cầu thời điểm hết hạn và concurrent writers |
| `INCR payments:counter` | **Không blind retry** khi kết quả không chắc chắn | Server có thể đã tăng nhưng ACK bị mất |
| `LPUSH queue event` | Không blind retry khi side effect lặp gây lỗi | Có thể đã push nhưng client không nhận ACK |
| Lua script tạo side effect | Tùy tính idempotent cụ thể | Script có thể đã chạy trước khi client timeout |
| DB fallback sau Redis unavailable | Có, **có giới hạn tải** | Nếu mọi request cùng fallback, DB có thể sập |

Không đánh đồng Redis command timeout với lệnh chưa thực hiện. Với lệnh thay đổi trạng thái, lỗi mạng sau khi gửi tạo **outcome uncertain**, tương tự vấn đề commit acknowledgment.

### 6.2. Kết nối với application design

Một client library như **Lettuce** có cơ chế reconnect và topology refresh theo cấu hình. Nhưng cần:

1. Chọn client hỗ trợ cluster topology của cache đang dùng.
2. Đặt connect/command timeouts theo request budget.
3. Giới hạn số retries, không retry đồng loạt vô hạn.
4. Cho phép degrade hoặc trả lỗi có chủ đích thay vì giữ thread mãi.
5. Quan sát latency/error rate sau failover.

Không khắc phục failover bằng cách tăng mọi timeout lên 60 giây: điều đó có thể giữ kín tài nguyên app, gây queueing và làm request p95/p99 tệ hơn.

## 7. Scaling: scale up, scale out và scale ứng dụng

**Scaling Redis** có ít nhất ba chiều:

- **Scale up/vertical:** chọn compute/memory capacity cao hơn cho instance/shards hiện có.
- **Scale out/horizontal:** phân phối keyspace và tải lên nhiều shards, nếu service/tier hỗ trợ clustering.
- **Application scaling:** tăng Java replicas, điều chỉnh concurrency, caching strategy và kết nối tới Redis.

Ba hướng này không thay thế lẫn nhau. Một cache 200 GB có thể cần thêm shards vì không đủ memory một node; nhưng một hot key chiếm 70% traffic không tự được chia đều sang shards mới chỉ nhờ resharding.

### 7.1. Scale up khi nào?

Các dấu hiệu thường dẫn tới xem xét scale up:

- Memory usage thường xuyên gần giới hạn sau khi tối ưu TTL/eviction.
- Server CPU/load cao, latency tăng trong tải ổn định.
- Throughput network/command giới hạn bởi capacity của mỗi node.
- Workload không dễ phân chia, cluster-mode còn hạn chế.

Ưu điểm: có thể đơn giản hơn về topology và client. Hạn chế: vẫn có giới hạn capacity/giá; thao tác thay đổi SKU/capacity có thể tác động tới availability, node rotation hoặc reconnect theo dịch vụ. **Không hứa scale up “zero downtime”** nếu chưa kiểm tra quy trình áp dụng của sản phẩm/tier và test với client.

### 7.2. Scale out khi nào?

Khi keyspace lớn hoặc cần throughput phân tán và dịch vụ hỗ trợ sharding, có thể tăng số shards. Tuy nhiên:

- Client phải biết cách phân phối keys nếu dùng Redis Cluster client-side routing.
- Resharding có thể di chuyển dữ liệu và làm latency/CPU/network tăng tạm thời.
- Multi-key operations có thể bị giới hạn bởi hash slots.
- Hotspot không biến mất nếu một key hoặc một nhóm key vẫn tập trung traffic.
- Failover có thể xảy ra cho từng shard; tổng số node/replica tăng.

**Scale out không có nghĩa mọi command hỗ trợ multi-shard transaction.** Cần hiểu dữ liệu và client trước khi kích hoạt cluster.

### 7.3. So sánh quyết định

| Tình huống | Hướng xử lý ưu tiên |
|---|---|
| Keyspace nhiều, eviction tăng vì thiếu RAM | Đánh giá TTL/size/eviction, rồi scale up/out |
| Server load cao do nhiều keys trải đều | Đánh giá command cost và cluster horizontal capacity |
| Một key rất nóng | App-side local cache, replication/read strategy khi hỗ trợ, key design, phân rã workload |
| App tăng 5→50 pods, Redis connections tăng mạnh | Reuse/multiplex connections và kiểm soát client count; không chỉ tăng cache capacity |
| DB quá tải khi Redis misses tăng | Request coalescing, TTL jitter, bounded fallback và cache warming |
| Redis endpoint failover làm Java timeout | Timeouts/reconnect/topology handling, không mặc định giải bằng nhiều shards |
| Latency tăng vì lệnh `KEYS *` hoặc Lua rất lâu | Thay command/data model, slowlog và load tests |

### 7.4. Capacity planning trước khi scale

Để ước lượng bộ nhớ:

\[
Memory_{needed}\approx KeyCount\times AverageEntryFootprint
 + Replication/metadata/fragmentation\ overhead
\]

`AverageEntryFootprint` bao gồm **key/value, data structure overhead, TTL metadata và allocator effects**; không chỉ bằng kích thước JSON plaintext. Ví dụ minh họa:

```text
2 triệu keys × kích thước hiệu dụng 1,5 KiB ≈ 2,86 GiB
Overhead/reserve/fragmentation sẽ làm nhu cầu cao hơn
```

Số liệu là ước lượng, không dùng làm sizing cuối. Cần lấy **used memory, resident memory/fragmentation, evictions, key count, working set, peak growth** từ Redis/service metrics thực tế.

## 8. Redis Cluster và 16.384 hash slots

Trong mô hình **Redis Cluster** phù hợp, keyspace được chia thành **16.384 hash slots**. Mỗi key được ánh xạ tới một slot, slot được phân bổ cho các primary shards. Client cluster-aware theo dõi topology để gửi lệnh tới node chứa slot.

```text
                          Redis Cluster
   0 ---------------------------------------- 16383
   |                 |                       |
   v                 v                       v
 Shard A           Shard B                 Shard C
 primary+replica   primary+replica         primary+replica
 (một tập slots)   (một tập slots)         (một tập slots)
       ^                 ^                       ^
       +-------- Java cluster-aware client ------+
                    (routing / topology refresh)
```

**Không mặc định mọi Azure Redis SKU sử dụng cùng cơ chế cluster routing.** Một số triển khai có proxy/routing layer khác và client có thể chỉ kết nối qua endpoint được quản lý. Hãy xác định topology/endpoint mà tài nguyên đang cung cấp và chọn client tương thích.

### 8.1. MOVED và ASK

Khi dùng Redis Cluster trực tiếp, client có thể nhận phản hồi định tuyến:

- **`MOVED`:** slot thuộc node khác; cần cập nhật topology/routing.
- **`ASK`:** redirect tạm thời trong quá trình di chuyển slot.

Lettuce/Jedis cluster clients phù hợp có thể xử lý redirects và refresh topology. Nếu code tự dùng một single-node client tới một shard và không hỗ trợ cluster, thao tác có thể thất bại sau reshard/failover.

Không tăng số lượng `MOVED` redirects vô hạn để “chịu được mọi lỗi”; quá nhiều redirects có thể là triệu chứng topology stale/resharding liên tục cần xử lý.

### 8.2. Hash tags để nhóm keys cùng slot

Trong Redis Cluster, phần bên trong dấu ngoặc nhọn có thể được dùng làm **hash tag** để keys liên quan nằm cùng slot:

```text
order:{1042}:header
order:{1042}:items
order:{1042}:status
```

Thiết kế này hữu ích nếu một Lua script/multi-key operation bắt buộc truy cập các keys cùng slot. Nhưng **đừng đặt tất cả hệ thống vào tag `{all}`**: mọi keys sẽ rơi vào cùng slot và làm mất lợi ích phân tán.

### 8.3. Cross-slot operations

Một số multi-key commands, Lua scripts và transactions của Redis Cluster yêu cầu keys cùng hash slot. Nếu app gọi một thao tác trên `order:1042` và `product:7` ở hai slots khác nhau, có thể nhận lỗi `CROSSSLOT` hoặc không được hỗ trợ.

Giải pháp không phải always “bật retries”: phải **đổi data model, nhóm keys theo một business partition**, hoặc chuyển transaction quan trọng sang database/điều phối workflow phù hợp.

### 8.4. Resharding và kiểm thử client

Khi tăng/giảm shards:

1. Snapshot baseline latency, hit rate, server load và client errors.
2. Đảm bảo driver/client hỗ trợ topology refresh và cluster failover.
3. Đánh giá big keys/hot keys trước khi di chuyển slots.
4. Thực hiện trong cửa sổ thay đổi được phê duyệt nếu môi trường cần.
5. Theo dõi `MOVED/ASK`, timeouts, p95/p99 latency, server load, bandwidth.
6. Kiểm tra application SLO và không có write side effects trùng.
7. Có rollback/migration procedure theo tính năng thực tế của SKU.

Không thay cluster topology production chỉ vì memory usage cao trong vài phút mà chưa kiểm tra TTL/eviction và traffic patterns.

## 9. Hot keys và big keys: khi scaling thông thường không đủ

### 9.1. Hot key

Một key nhận phần lớn số request – ví dụ `promotion:global` được 100.000 clients đọc trong vài giây – là **hot key**. Dù có nhiều shards, key thường được đặt tại một slot/shard, có thể gây single-shard CPU/network pressure.

Biện pháp:

- Cache nhỏ thêm ở JVM/local L1 cache có TTL ngắn và invalidation được thiết kế.
- Phân tán workload theo các keys/partitions hợp lý nếu semantics cho phép.
- Với dữ liệu công khai ít đổi, cân nhắc CDN/edge caching.
- Giảm request burst bằng request coalescing/near-cache.
- Theo dõi per-shard load và key access patterns theo công cụ hỗ trợ.

**Không sao chép cùng một key thành nhiều phiên bản tùy tiện** nếu cần nhất quán mạnh: mỗi bản sao cần chiến lược invalidation rõ.

### 9.2. Big key

Một key có value 50 MiB hoặc collection chứa rất nhiều phần tử có thể làm:

- Network transfer và serialization latency tăng.
- Một số operations chiếm CPU/event loop lâu.
- Resharding chậm và tăng memory pressure.
- Application heap/GC tăng đột biến.

Giải pháp: chia dữ liệu theo trang/đối tượng, đặt giới hạn size, lưu payload lớn tại Blob Storage hoặc database, cache chỉ những phần nhỏ hay dùng. Redis **không** là kho lưu file lớn vì có RAM nhanh.

### 9.3. Các lệnh có độ phức tạp cao

Một số operations có độ phức tạp phụ thuộc số keys hoặc số phần tử. Tránh lệnh `KEYS *` trong runtime production để liệt kê toàn keyspace; xem xét `SCAN` với giới hạn và permission phù hợp khi cần inventory. Nhưng `SCAN` cũng tạo tải và không cho một snapshot nguyên tử toàn keyspace, nên chỉ chạy có kiểm soát.

Khi điều tra latency, phân tích **command mix và time complexity**, không chỉ nhìn tổng số operations/second.

## 10. Memory management: TTL, eviction và fragmentation

Redis in-memory bị giới hạn dung lượng. Khi bộ nhớ gần giới hạn, tùy **maxmemory policy** và dịch vụ:

- Một số keys có thể bị **evict** để dành chỗ cho dữ liệu mới.
- Một số writes có thể thất bại nếu policy `noeviction` hoặc điều kiện khác ngăn giải phóng memory.
- Memory fragmentation có thể khiến RAM/resident memory khác kích thước dữ liệu hữu ích.
- Background operations, replication, persistence hoặc buffers cần overhead theo triển khai.

### 10.1. TTL là hợp đồng dữ liệu

```text
product:1042:details        TTL = 300 giây
promotion:public:rules      TTL = 60 giây
session:opaque:abc          TTL = theo chính sách session
```

**TTL là thời gian tồn tại tối đa mong muốn của cache entry**, không bảo đảm Redis chỉ xóa key đúng vào thời điểm đó theo nghĩa tài nguyên được giải phóng ngay tức thì, và không ngăn eviction sớm hơn. Cần biết dữ liệu có thể stale trong khoảng TTL hoặc sau một race write/invalidation.

### 10.2. Thêm jitter để tránh đồng loạt hết hạn

Nếu 100.000 keys đều được set TTL 300 giây lúc một đợt triển khai, chúng có thể hết hạn gần đồng thời gây **cache stampede**.

Một thiết kế:

```text
effectiveTTL = baseTTL + random(0 .. jitterWindow)
Ví dụ: 300s + random 0..60s
```

Jitter phù hợp cho dữ liệu không cần expiration vào đúng một thời điểm. Không thêm jitter cho những chính sách bảo mật có thời hạn cứng (ví dụ session/token expiry) nếu làm gia hạn trái phép thời gian hiệu lực.

### 10.3. Eviction policies

Các tên policy thường gặp trong Redis gồm:

- `noeviction`: từ chối một số writes cần thêm memory khi đạt giới hạn.
- `allkeys-lru` / `allkeys-lfu`: chọn keys để evict dựa trên chính sách gần đây/tần suất sử dụng.
- `volatile-lru` hoặc các biến thể chỉ xét keys có TTL.
- `allkeys-random` / `volatile-random` trong một số cấu hình.

**Chính sách khả dụng và cách cấu hình phụ thuộc Redis service, engine/tier và quyền quản trị.** Không giả định Azure Managed Redis cho phép chạy `CONFIG SET maxmemory-policy ...` trực tiếp trên production. Nếu workload cần dữ liệu session không được tự evict, phải thiết kế partition/instance riêng hoặc cơ chế durable phù hợp.

### 10.4. Evicted Keys và Expired Keys khác nhau

- **Expired Keys:** keys bị loại vì hết TTL.
- **Evicted Keys:** keys bị loại do áp lực memory/eviction policy.

Expired Keys tăng có thể bình thường đối với cache TTL ngắn. Evicted Keys tăng liên tục **khi nhiều misses và DB load tăng** thường là tín hiệu capacity/workload cần chú ý. Số evictions đơn độc không đủ kết luận: phải xem hit rate, working set và impact lên ứng dụng.

### 10.5. Memory fragmentation

Redis process dùng allocator và có overhead; resident memory có thể cao hơn logical used memory. Nếu **fragmentation ratio** cao, cần điều tra patterns phân bổ/big keys, memory churn và khả năng active defragmentation theo engine/service. Đừng dùng một ngưỡng ratio cố định cho mọi SKU, vì nhỏ/lớn của dataset, OS buffers và persistence có thể ảnh hưởng cách đọc metric.

## 11. Connection management khi ứng dụng Java scale

Redis dùng TCP/TLS connections. Khi ứng dụng Java có nhiều replicas, số clients có thể tăng đột biến:

\[
Connections_{potential}\approx Replicas_{max}\times ConnectionsPerReplica
\]

Ví dụ minh họa:

```text
30 Java pods × 20 physical Redis connections/pod = 600 connections
Thêm workers, monitoring clients, admin tools và rollout surge
=> Peak có thể cao hơn 600
```

Nếu một client library hỗ trợ **multiplexing** nhiều commands trên một connection (ví dụ Lettuce trong nhiều kiểu dùng), tạo 20 connections/pod có thể không cần thiết. Ngược lại, **blocking operations** như `BLPOP`, Pub/Sub subscriptions hoặc một số workflows riêng có thể cần connections dedicated, tùy client.

### 11.1. Lettuce và Jedis

| Client Java | Đặc điểm | Lưu ý |
|---|---|---|
| **Lettuce** | Redis client phổ biến, hỗ trợ async/reactive, reconnect và cluster theo cấu hình | Có thể multiplex nhiều operations; không chia sẻ stateful commands/transactions sai ngữ cảnh |
| **Jedis** | Redis client Java phổ biến, có connection pooling/cluster theo API phù hợp | Kiểm tra version, thread safety và lifecycle client |
| **Spring Data Redis** | Abstraction `RedisTemplate`/cache repository và tích hợp Lettuce/Jedis | Chọn serializer, TTL, authentication và metrics rõ ràng |

**Không suy rằng mọi loại Redis connection đều thread-safe**: các tính năng transaction, pub/sub, blocking commands, pipeline và client wrapper có ràng buộc. Đọc contract của phiên bản library trong dự án và test khi failover/resharding.

### 11.2. Connection storm lúc failover

Khi Redis phục hồi, 30 pods có thể cùng:

1. Nhận timeout.
2. Hủy hàng loạt sockets.
3. Cùng reconnect.
4. Retry các requests đang chờ.
5. Đổ cache misses xuống database.

Giải pháp cần phối hợp **reconnect backoff + jitter**, số connections hữu hạn, circuit breaker, timeout budgets và bounded DB fallback. Tăng Redis capacity không giải quyết được nếu clients reconnect cùng một thời điểm mà không kiểm soát.

### 11.3. Pooling không phải phép chữa mọi latency

Một pooled connection đang chờ key lớn/truy vấn chậm có thể khiến requests khác queue ở client. Một multiplexer cũng có giới hạn network throughput và head-of-line behavior. Cần đo **client command queue time, command latency, in-flight commands, server latency và bandwidth** để phân biệt bottleneck.

## 12. Kết nối Java Spring Boot với Redis trên Azure

Trong bài thực hành, chúng ta dùng **Java 17+, Spring Boot, Spring Data Redis và Lettuce**. Vì endpoint, port, credentials và cluster mode của Azure Managed Redis có thể khác những Azure Cache for Redis đang hoạt động, **lấy giá trị từ đúng resource và môi trường**, không copy port mặc định của một sản phẩm khác.

### 12.1. Dependency

Ứng dụng Spring Boot với dependency management phù hợp có thể dùng:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
  </dependency>
</dependencies>
```

Các versions do **Spring Boot BOM** đã được kiểm thử quyết định. Không lấy một phiên bản Lettuce ngẫu nhiên và ép vào Spring Data Redis khi chưa kiểm tra compatibility, TLS, cluster routing và credential provider.

### 12.2. Cấu hình TLS và timeouts

Ví dụ `application.yml` cho một endpoint đơn hoặc gateway topology tương ứng:

```yaml
spring:
  data:
    redis:
      host: "${REDIS_HOST}"
      port: "${REDIS_PORT}"
      username: "${REDIS_USERNAME:}"
      password: "${REDIS_PASSWORD}"
      ssl:
        enabled: true
      connect-timeout: 1s
      timeout: 500ms

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
```

`REDIS_HOST` là hostname được Azure cấp, `REDIS_PORT` là cổng **TLS** của resource thực tế, không thêm `redis://` vào trường hostname. Biến `REDIS_USERNAME` có thể để rỗng **chỉ khi mô hình xác thực thật sự cho phép**; Redis ACL/Entra token mode có thể yêu cầu username riêng. `REDIS_PASSWORD` dùng để minh họa chế độ **password/access-key authentication** đã được cho phép, **không nên hard-code**.

**Quan trọng:** với **Microsoft Entra ID access token** dùng cho Redis, không được coi access token là password bất biến trong `REDIS_PASSWORD` suốt vòng đời JVM. Token hết hạn, clients/reconnect phải có cơ chế **refresh và re-authentication** được chính dịch vụ và client library hỗ trợ. Hãy sử dụng credential provider/integration đã được kiểm thử, hoặc tài liệu chính thức áp dụng cho SKU của bạn. Đừng đưa token tĩnh vào Helm values/Git.

### 12.3. Về cổng và TLS

Ở nhiều **Azure Cache for Redis classic** triển khai cũ, TLS endpoint sử dụng cổng **6380**; nhưng **không suy ra 6380 cho mọi Azure Managed Redis hoặc Enterprise deployment**. Một số kiểu tài nguyên dùng cổng/hostname khác. Kiểm tra resource connection information trên Azure Portal/IaC output và firewall rules trước khi triển khai.

Đối với TLS, giữ certificate validation và hostname matching. Không tự bật “insecure TLS/trust all certificates” để vượt lỗi handshake. Nếu private DNS trỏ hostname không khớp certificate, phải sửa DNS hoặc cách client chọn hostname thay vì vô hiệu hóa xác thực server.

### 12.4. Redis Cluster trong Spring Data Redis

Với Redis Cluster client-side routing, cấu hình nodes qua tùy chọn `spring.data.redis.cluster.nodes` theo phiên bản Spring Boot:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "${REDIS_NODE_1}"
          - "${REDIS_NODE_2}"
      ssl:
        enabled: true
      timeout: 500ms
```

Các giá trị node thường ở dạng `host:port`, **chỉ sử dụng khi resource thực sự yêu cầu/cho phép client-aware cluster routing**. Không đặt config cluster cho một Azure Managed Redis endpoint dùng managed proxy nếu documentation của deployment đó yêu cầu cấu hình standalone. Dù có cluster mode, authentication và TLS vẫn phải cấu hình theo resource và topology thực tế.

### 12.5. RedisTemplate và serialization

Spring Data Redis hỗ trợ `StringRedisTemplate` cho key/value dạng string và `RedisTemplate<K,V>` cho các kiểu khác. Với JSON cache:

- Đặt key prefix rõ ràng, ví dụ `catalog:v3:product:1042`.
- Dùng serializer ổn định/versioned, tránh Java native object serialization không được kiểm soát.
- Không lưu class names/Java package internals trong cache payload nếu schema dễ thay đổi.
- Bắt lỗi deserialization riêng với cache miss/connection timeout.
- Kiểm soát kích thước value; JSON nhiều MB không phải cache entry lý tưởng.

Một Redis JSON value lỗi schema không nên khiến toàn API sập: có thể bỏ key và đọc database, nhưng phải ghi metric/data quality alert để không che một đợt deploy serializer không tương thích.

## 13. Java cache-aside có fallback an toàn

Mẫu dưới đây minh họa cách dùng `StringRedisTemplate`. Nó có chủ đích **không coi Redis là nguồn thật**, và phân biệt cache hit, miss với cache unavailable.

### 13.1. Service ví dụ

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ProductCacheService {
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final ProductRepository repository;

    public ProductCacheService(
            StringRedisTemplate redis,
            ObjectMapper json,
            ProductRepository repository) {
        this.redis = redis;
        this.json = json;
        this.repository = repository;
    }

    public Optional<ProductDto> findProduct(String productId) {
        String key = "catalog:v3:product:" + productId;

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return Optional.of(json.readValue(cached, ProductDto.class));
                } catch (JsonProcessingException corruptCacheValue) {
                    // Cache data không còn tương thích; không log raw payload.
                    try {
                        redis.delete(key);
                    } catch (DataAccessException ignored) {
                        // Delete cache là best-effort, dữ liệu DB vẫn là nguồn thật.
                    }
                }
            }
        } catch (DataAccessException cacheFailure) {
            // Log/metrics: cache_unavailable, không in secret hoặc giá trị key nhạy cảm.
        }

        // Ở production: bounded DB fallback + request coalescing.
        Optional<ProductDto> fromDb = repository.findById(productId);
        fromDb.ifPresent(product -> {
            try {
                long ttlSeconds =
                        300L + ThreadLocalRandom.current().nextLong(0L, 61L);
                redis.opsForValue().set(
                        key,
                        json.writeValueAsString(product),
                        Duration.ofSeconds(ttlSeconds));
            } catch (DataAccessException | JsonProcessingException cacheError) {
                // Không làm một DB read thành lỗi chỉ vì cache set thất bại.
                // Ghi metrics/log đã ẩn dữ liệu nhạy cảm.
            }
        });
        return fromDb;
    }
}
```

`ProductRepository` và `ProductDto` là các types nghiệp vụ **minh họa**, không phải lớp có sẵn trong Redis library. Code còn thiếu authentication/authorization theo bản ghi, metrics thực tế, bounded fallback và request coalescing – sẽ được bổ sung về mặt kiến trúc ở phần tiếp theo. Không copy ví dụ này cho nghiệp vụ tài chính yêu cầu nhất quán mạnh.

### 13.2. Tại sao fallback chưa đủ?

Nếu Redis bị lỗi 2 phút và 10.000 requests/s đều đi thẳng vào Azure SQL, **fallback làm database sập** dù API đã “chịu lỗi cache”. Vì vậy, production cần:

1. **Bounded concurrency:** giới hạn số requests được fallback đồng thời vào DB.
2. **Circuit breaker:** sau nhiều Redis failures, ngừng cố gọi Redis cho mọi request trong một khoảng thời gian phù hợp.
3. **Rate limit/backpressure:** chặn hoặc trả 503 cho lưu lượng vượt capacity.
4. **Request coalescing/single-flight:** nhiều requests cùng key chỉ có một lần load từ database.
5. **Local short-lived cache:** phục vụ một số dữ liệu ít đổi khi Redis unavailable.
6. **Timeout budget:** Redis connect/command timeouts không chiếm toàn bộ HTTP deadline.
7. **Safe stale-while-revalidate** khi dữ liệu cho phép và đã định nghĩa maximum staleness.

### 13.3. Single-flight theo một key

Giả sử 1.000 requests đồng thời cùng tìm `product:1042` sau khi key hết TTL. Nếu mỗi request gọi DB, sẽ có 1.000 queries. Một **single-flight coordinator** trong từng JVM gom các requests theo key:

```text
1000 requests for product:1042
          |
          v
Single-flight group trong mỗi JVM
          |
          +-- 1 owner tải database
          +-- Các followers chờ kết quả có timeout
          |
          v
Redis cache set / trả kết quả
```

Single-flight trong JVM **không tự gom được requests trên 20 pods**. Nếu cache stampede ở quy mô lớn, có thể phối hợp jitter, distributed lock được thiết kế cẩn thận hoặc background warming, nhưng tránh biến Redis lock thành phụ thuộc bắt buộc đúng lúc Redis đang outage.

### 13.4. Negative caching

Khi sản phẩm không tồn tại, không lưu mọi lần miss với cùng TTL dài như sản phẩm thật. Có thể cache một sentinel “not found” với TTL ngắn để giảm repeated misses, nhưng:

- Kiểm tra quyền/tenant trước khi dùng “không tồn tại” như kết luận có thể lộ enumeration.
- Dữ liệu có thể được tạo ngay sau đó.
- Negative cache phải có version/namespace rõ và TTL phù hợp.

### 13.5. Stale dữ liệu và giới hạn nghiệp vụ

Một cache product price có TTL 5 phút có thể làm khách hàng nhìn thấy giá cũ sau thay đổi. Nếu giá dùng để thanh toán, server phải **revalidate giá và điều kiện khuyến mại từ nguồn tin cậy** khi tạo order/payment. Cache tốt cho trải nghiệm đọc, không là bằng chứng pháp lý về giá/thanh toán cuối.

## 14. Timeout, retry và circuit breaker cho Redis

Đặt timeout theo **end-to-end deadline**. Một ví dụ ngân sách request:

```text
HTTP request deadline                    2.0s
Redis command timeout                    0.2s
DB fallback (nếu cần và được phép)       1.2s
Serialization + network response margin 0.6s
```

Đây là cấu hình minh họa, không phải ngưỡng chung cho Azure Redis. Nếu Redis lỗi kéo dài, mỗi request nên chỉ chờ một khoảng có ý nghĩa rồi fallback hoặc trả lỗi, thay vì giữ threads quá lâu.

### 14.1. Không retry mọi Redis command

Một `GET` thường có thể retry có giới hạn vì không tạo side effect, trong khi `INCR`, `LPUSH`, một Lua script hoặc transaction đã gửi có thể đã chạy dù response timeout. Cần **phân loại command và yêu cầu idempotency** trước khi retry.

| Tình huống | Retry | Hành vi ưu tiên |
|---|---|---|
| `GET` timeout ngắn | Có thể thử lại 1 lần trong deadline | Nếu vẫn lỗi: bounded DB fallback |
| `SET` same value + TTL | Có thể khi semantics cho phép | Đảm bảo không ghi đè value mới hơn |
| `INCR`/counter không idempotent | Không blind retry | Dùng event ID/idempotency hoặc chuyển nghiệp vụ sang DB |
| Redis connection refused do firewall sai | Không retry dồn dập | Alert và sửa cấu hình mạng |
| Redis failover, client reconnect | Retry an toàn có jitter/backoff | Theo dõi status, reconnect và DB load |
| `MOVED`/`ASK` | Client cluster-aware xử lý topology | Không replay thao tác không biết outcome |

### 14.2. Circuit breaker tách health và business success

Một Redis circuit breaker có thể:

1. **CLOSED:** gọi Redis bình thường, đo timeout/failure rate.
2. **OPEN:** Redis được coi unavailable ngắn hạn; bỏ qua cache call và chuyển sang fallback bounded nếu cho phép.
3. **HALF_OPEN:** thử số request nhỏ để xác định Redis đã phục hồi.

Không mở circuit cho cả database chỉ vì Redis lỗi nếu DB vẫn khỏe, nhưng cũng không để toàn bộ traffic dồn vào DB. Khi circuit mở mà DB đã bão hòa, **fail fast** hoặc trả cached stale data (nếu chính sách cho phép) có thể an toàn hơn.

### 14.3. Retry storm khi failover

```text
Redis failover
     |
     +-- 40 pods cùng mất kết nối
     |
     +-- Mỗi pod 100 in-flight requests
     |
     +-- Mỗi request retry 5 lần ngay lập tức
     |
     +-- Lên tới hàng chục nghìn attempts trong thời gian ngắn
```

Giảm rủi ro bằng **jitter**, giới hạn concurrency, số attempts nhỏ, deadline, circuit breaker và tách high-value paths. Không đặt retry ở nhiều tầng với cấu hình không phối hợp.

### 14.4. Redis không phục hồi: degrade gracefully

Theo mức quan trọng:

- **Product cache:** đọc DB với giới hạn, hoặc trả stale product cache có thời hạn.
- **Session store:** có thể buộc đăng nhập lại hoặc báo phiên tạm thời không sẵn sàng; không cấp quyền giả.
- **Rate limit/security counter:** lựa chọn fail-closed/fail-open dựa trên threat model; không mặc định bỏ toàn bộ bảo vệ.
- **Payment state:** vẫn phải dựa vào database authoritative và transaction.

Degraded mode phải được kiểm thử trước; không tự “bắt mọi exception và trả dữ liệu rỗng” khiến app hiển thị sai tình trạng đơn hàng.

## 15. Độ nhất quán khi cập nhật và invalidation cache

### 15.1. Cache-aside với write path

Ví dụ cập nhật tên sản phẩm:

```text
1. BEGIN SQL transaction
2. UPDATE products ... WHERE product_id=1042
3. COMMIT SQL
4. DEL catalog:v3:product:1042
5. Các reads sau miss -> lấy DB mới -> SET TTL
```

**Vấn đề:** nếu Java chết sau SQL commit nhưng trước `DEL`, cache cũ còn tới TTL. Nếu yêu cầu tính nhất quán cao, có thể lưu outbox invalidation event trong SQL transaction và chạy relay; vẫn cần xử lý duplicate/ordering/race. Đừng xóa cache trước SQL commit rồi tin dữ liệu luôn được cập nhật.

### 15.2. Race giữa miss và invalidation

```text
Reader A: Redis miss
Reader A: đọc DB cũ
Writer B: COMMIT DB mới
Writer B: DEL Redis key
Reader A: SET Redis value cũ sau DEL
```

Đây là race hợp lệ ngay cả khi quy tắc “write DB rồi DEL cache” được áp dụng. Giải pháp có thể gồm TTL ngắn, **versioned cache entries**, compare-and-set với version/timestamp được tin cậy, read-after-write cache bypass hoặc invalidation bổ sung. Redis chỉ hỗ trợ atomic per-command/script trong điều kiện/slot nhất định; **không có transaction SQL + Redis tự nhiên**.

### 15.3. Cache versioning

Key prefix `catalog:v3:product:1042` cho phép release schema mới không deserialize nhầm cache cũ. Khi thay JSON shape, có thể tăng `v3` lên `v4` và dùng TTL để old keys hết hạn. Nhưng cách này **tăng memory tạm thời** do cả hai phiên bản tồn tại, cần tính peak memory khi deploy.

### 15.4. Không dùng Redis cache làm leader election duy nhất

Redis commands như `SET key value NX PX ...` có thể hỗ trợ simple locking, nhưng một distributed lock an toàn cần xem **lock ownership, TTL, clock assumptions, failover và fencing tokens**. Nếu lock hết hạn khi worker vẫn chạy, worker khác có thể vào critical section cùng lúc. Với giao dịch quan trọng, cần database constraints/transactions hoặc coordination service có semantics phù hợp.

## 16. Azure Monitor: theo dõi Redis cần những tín hiệu gì?

Một cache có thể có 99% availability ở mức resource nhưng làm API chậm do **hot shard**, **evictions**, **network latency** hoặc **cache stampede**. Vì vậy monitoring nên kết hợp **Azure platform metrics**, **Redis engine metrics khi được hỗ trợ**, **application/client telemetry** và **backend/database metrics**.

### 16.1. Bốn lớp quan sát

```text
Azure Redis resource
   |
   +-- Platform metrics: CPU/load, memory, connections, commands...
   |
   +-- Diagnostic settings / logs nếu dịch vụ cung cấp
   |
   +-- Redis engine stats/slowlog trong phạm vi quyền cho phép
   |
   v
Azure Monitor / Metrics Explorer / alerts / Workbooks
   ^
   |
Java application metrics:
   cache_hit, cache_miss, cache_error, command_latency,
   reconnects, fallback_to_db, p95 request latency
   |
   v
Azure SQL / PostgreSQL:
   CPU, active connections, slow queries, throttling, failover
```

Một dashboard chỉ có Redis CPU/memory sẽ bỏ sót khi cache hit rate tụt mà DB bắt đầu quá tải. Ngược lại, ứng dụng báo nhiều cache misses không đủ kết luận Redis yếu: có thể key TTL quá ngắn hoặc deploy vừa thay namespace.

### 16.2. Nhóm metrics nền tảng quan trọng

| Nhóm | Tín hiệu cần tìm | Cách diễn giải |
|---|---|---|
| **Capacity/CPU** | Server load/CPU, per-shard load nếu có | Cao kéo dài cùng latency tăng → capacity/command bottleneck |
| **Memory** | Used memory, memory percentage, resident/fragmentation nếu có | Working set gần giới hạn, có nguy cơ eviction/write failure |
| **Connections** | Connected clients, connection failures | Đột biến khi deploy/failover, connection leak hoặc storm |
| **Throughput** | Operations/sec, commands processed, read/write rates | So với baseline và latency |
| **Cache hiệu quả** | Cache hits, cache misses, hit rate | Kết hợp TTL, warm-up, eviction và database fallback |
| **Eviction/expiration** | Evicted keys, expired keys | Eviction tăng do memory khác TTL expiration bình thường |
| **Latency** | Server/cache latency, p95/p99 client command latency | Phân biệt network, queueing, hot key, CPU |
| **Errors** | Timeout, connection resets, rejected writes, protocol/cluster errors | Phân loại theo giai đoạn và command |
| **Availability/replication** | Node/replica state, failover events, replication lag khi có | Xác định chuyển đổi vai trò và khả năng mất data |
| **Network** | Bandwidth/egress/ingress | Big keys, serialization hoặc network saturation |

**Tên metric, dimensions, đơn vị và aggregation chính xác thay đổi theo sản phẩm/SKU**. Ví dụ tên thường gặp ở các tài nguyên Redis cũ có thể là `connectedclients`, `usedmemory`, `cachehits` hoặc `serverLoad`; không viết alert production bằng tên đoán. Luôn **liệt kê metric definitions từ resource** và chọn chỉ số thực sự được cung cấp.

### 16.3. Dựa vào Max và phân bố shard, không chỉ Average

Giả sử một cluster có bốn shards:

```text
Shard A server load: 95%
Shard B server load: 15%
Shard C server load: 20%
Shard D server load: 10%
Average toàn cluster: 35%
```

Chỉ nhìn trung bình 35% sẽ bỏ sót shard A đã bão hòa. Khi metric có **dimension shard/node**, cần xem cả **Max, từng shard, p95/p99 latency** và hot-key distribution. Nếu metric không có shard dimension, phải dùng các cơ chế được dịch vụ hỗ trợ để hiểu lệch tải mà không tự suy từ số tổng.

### 16.4. Cache hit ratio

\[
HitRatio=\frac{Hits}{Hits+Misses}\times 100\%
\]

Ví dụ trong một khoảng thời gian:

```text
Hits   = 900.000
Misses = 100.000
Hit ratio = 90%
```

Phải **tính từ các increments trong cùng time window**, không chia hai counter cumulative ở các khoảng lấy mẫu không tương thích. Cần phân biệt:

- **Redis hit ratio** theo engine metrics.
- **Application cache hit ratio** theo nghiệp vụ/endpoints.
- **Bypass rate** khi circuit breaker bỏ qua Redis.

Một cache hit ratio cao có thể vẫn gây khó khăn nếu hot key nằm trên một shard; một hit ratio thấp có thể hợp lý với workload ít tái sử dụng dữ liệu. Đặt SLO dựa vào **latency, DB load và user experience**, không coi 100% hit là mục tiêu tự thân.

## 17. Xem metrics và diagnostic settings trên Azure

### 17.1. Azure Portal

Quy trình phù hợp cho hầu hết Redis resource trong Azure:

1. Mở **đúng Redis resource** trong Azure Portal, xác định tên dịch vụ/tier, region, capacity và networking.
2. Vào **Monitoring → Metrics** hoặc mục metrics tương đương.
3. Chọn **metric name** được liệt kê thực tế, thời gian và aggregation.
4. Dùng dimension theo node/shard khi có.
5. So sánh memory, server load, connections, hits/misses, evictions với application request latency.
6. Lưu biểu đồ trong dashboard/Workbook theo tính năng hỗ trợ.
7. Kiểm tra **Alerts** và **Diagnostic settings** riêng; metrics hiển thị trong Portal không có nghĩa raw Redis logs đã được lưu ở Log Analytics.

### 17.2. Azure CLI – khám phá metric definitions

Khi có Resource ID chính xác (lấy từ Portal hoặc IaC output):

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

REDIS_RESOURCE_ID="<full-azure-resource-id-of-your-redis-instance>"

az monitor metrics list-definitions \
  --resource "$REDIS_RESOURCE_ID" \
  --output table
```

Lệnh này giúp **khám phá những metrics mà Azure Monitor cung cấp** cho resource và tránh nhầm namespace/metric names giữa Azure Managed Redis và Azure Cache for Redis. Nếu resource dùng metric namespace khác, sử dụng các tham số phù hợp theo hướng dẫn CLI đang có.

Sau khi chọn tên metric **được trả về thực tế**:

```bash
METRIC_NAME="<metric-name-from-list-definitions>"

az monitor metrics list \
  --resource "$REDIS_RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --interval PT1M \
  --output json
```

Không giả định mọi metric hỗ trợ granularity 1 phút; nếu lệnh trả invalid interval, lấy **supported time grains** từ metric definition rồi chọn hợp lệ. Các values, unit và aggregation chỉ có nghĩa khi phù hợp metric.

### 17.3. Azure CLI – xem diagnostic settings

```bash
az monitor diagnostic-settings list \
  --resource "$REDIS_RESOURCE_ID" \
  --output json
```

Những diagnostic categories được hỗ trợ phụ thuộc resource. Có thể gửi logs/metrics theo cấu hình đến Log Analytics workspace, Storage account hoặc Event Hubs theo tính năng Azure Monitor đang áp dụng. **Không mặc định Redis command logs/slowlog có sẵn ở Log Analytics chỉ vì đã bật platform metrics.**

Nếu organization yêu cầu log audit/connection:

- Xem resource có category phù hợp không.
- Chọn đích lưu, data residency, retention và quyền truy vấn.
- Không bật logging quá chi tiết gây lộ key names hoặc chi phí cao mà không có mục đích.
- Kiểm thử sự kiện giả lập an toàn để xác minh dữ liệu tới đích.

### 17.4. Azure Cache for Redis classic – kiểm tra resource

Chỉ với **Azure Cache for Redis classic** sử dụng resource/CLI tương thích, một lệnh quản lý điển hình:

```bash
az redis show \
  --resource-group "<legacy-cache-resource-group>" \
  --name "<legacy-cache-name>" \
  --output json
```

Đây **không** phải lệnh chung cho mọi Azure Managed Redis hoặc các biến thể Enterprise. Với Managed Redis, dùng Azure Portal hoặc resource provider/CLI được **phiên bản hiện tại của sản phẩm** hỗ trợ; không giả định lệnh classic có thể xem hoặc thay đổi tài nguyên khác.

## 18. Logs và KQL: hiểu pipeline trước khi query

**Azure Monitor Metrics** và **Log Analytics logs** là hai dạng dữ liệu/luồng khác nhau. Trên Redis:

- **Platform metrics** thường có thể xem qua Metrics Explorer và API metrics nếu resource cung cấp.
- **Diagnostic logs** cần category và diagnostic settings tương ứng nếu hỗ trợ.
- **Java application logs** có thể đến Application Insights/Log Analytics qua OpenTelemetry, Azure Monitor Agent hoặc pipeline riêng.
- **Redis INFO/SLOWLOG** là các công cụ Redis, không tự đồng nghĩa với một bảng KQL.

### 18.1. Khám phá bảng thay vì đoán schema

Trong Log Analytics workspace đã cấu hình:

```kusto
AzureMetrics
| where TimeGenerated > ago(2h)
| take 10
```

Lệnh KQL này **chỉ hữu ích nếu metrics của Redis đã được xuất đến workspace và bảng tương ứng tồn tại**. Tên bảng có thể khác theo routing và kiểu tài nguyên. Nếu query không có dữ liệu, hãy xác minh **diagnostic settings, destination workspace, enabled categories và ingestion**. Không khẳng định Redis không có metrics chỉ vì bảng `AzureMetrics` trống.

Một truy vấn khám phá tên metric nếu bảng có schema tương ứng:

```kusto
AzureMetrics
| where TimeGenerated > ago(24h)
| summarize Samples=count() by MetricName
| top 30 by Samples desc
```

Khi nhiều Azure resources gửi chung workspace, phải lọc theo resource identity/cột tương ứng sau khi xem schema thật; không trộn metrics của Redis dev, prod và các services khác thành một chart rồi đưa ra alert.

### 18.2. Logs của Java Redis client

Một structured log **minh họa**:

```json
{
  "timestamp": "2026-11-20T10:05:31Z",
  "service": "orders-api",
  "cacheOperation": "GET",
  "cacheKeyPrefix": "catalog:v3",
  "result": "TIMEOUT",
  "durationMs": 205,
  "cluster": "orders-prod",
  "fallback": "DATABASE",
  "traceId": "trace-93a5"
}
```

Không log access key/Entra token, raw cached value, personal user ID hay toàn bộ key nếu key chứa định danh nhạy cảm. Với load lớn, dùng **metrics tổng hợp** cho mọi request và sample lỗi/log có chọn lọc thay vì ghi DEBUG cho từng GET.

### 18.3. Tracing giúp phân biệt Redis với database

```text
GET /products/1042       610ms
  |
  +-- Redis GET           200ms timeout
  +-- DB SELECT           350ms
  +-- Serialization        20ms
  +-- HTTP response        40ms
```

Nếu chỉ nhìn DB query 350ms, có thể bỏ qua 200ms lãng phí ở Redis. Nên instrument **Redis command span, database dependency span, fallback reason và request deadline**. Dùng OpenTelemetry/Application Insights hoặc giải pháp tương thích nhưng không lưu payload/credential trong spans.

### 18.4. Redis SLOWLOG và INFO

Lệnh Redis như `INFO` và `SLOWLOG GET` có thể hữu ích khi dịch vụ và quyền cho phép:

```text
INFO memory
INFO stats
SLOWLOG GET 20
```

Chúng có thể bị giới hạn hoặc thay bằng Azure-native telemetry trên các dịch vụ managed. `SLOWLOG` phản ánh những commands vượt threshold **ở phía Redis engine**, không bao gồm toàn bộ network RTT/serialization/client waiting. Những command logs có thể chứa key names; cần kiểm soát quyền và dữ liệu nhạy cảm. **Không chạy `MONITOR` liên tục trên Redis production** chỉ để “xem tất cả commands”: nó có thể gây overhead và lộ dữ liệu.

## 19. Thiết kế dashboard Redis + application + database

Một dashboard có giá trị nên trả lời “Redis có giúp ứng dụng nhanh và ổn định không?”, không chỉ “process Redis còn chạy không?”.

| Vùng | Biểu đồ | Dùng để quyết định |
|---|---|---|
| **Redis capacity** | Used memory %, fragmentation/reserve, server load | Scale/optimize, tránh memory pressure |
| **Redis performance** | Commands/s, p95/p99 latency, per-shard load | Hot shard, big key, client bottleneck |
| **Cache effectiveness** | Hit/miss ratio, expired/evicted keys | TTL, working set, invalidation |
| **Redis reliability** | Connected clients, reconnect/timeout rate, failover events | Network, HA, client recovery |
| **Application** | HTTP p95, error rate, cache fallback count, circuit state | User impact và degraded mode |
| **Database** | CPU, query p95, active connections, throttling | Redis outage có đổ tải vào nguồn thật không |
| **Deployment** | Redis scaling/migration, AKS rollout, app config changes | Tương quan thay đổi với sự cố |
| **Cost** | Cache tier/capacity, network, monitoring ingestion | Hạ chi phí mà không bỏ SLO |

### 19.1. Ví dụ diễn giải một sự cố

```text
10:00 Redis hit rate      97%
10:03 Redis evicted keys  tăng mạnh
10:05 Redis hit rate      62%
10:06 DB CPU              91%
10:07 API HTTP p95        từ 120ms lên 1900ms
```

Một giả thuyết hợp lý là **memory pressure → eviction → cache miss → tăng SQL traffic → API latency**. Nhưng cần xác nhận working set, app logs, traffic spikes, DB query plans và thời điểm rollout. **Tương quan thời gian không tự chứng minh quan hệ nhân quả.**

### 19.2. Metric đặt tên theo kết quả nghiệp vụ

Nếu Redis là optional cache, định nghĩa:

- `cache_lookup_total{result=hit|miss|error|bypassed}`.
- `cache_command_duration_seconds` theo operation an toàn, không theo từng raw key.
- `cache_db_fallback_total{reason=miss|timeout|circuit_open}`.
- `cache_degraded_requests_total`.
- `redis_reconnect_total` theo client/instance ở mức cardinality phù hợp.

**Không dùng `userId`, `orderId`, full Redis key hoặc request ID làm metric label**: cardinality có thể tăng cực lớn, gây chi phí và khó vận hành. Dùng những dimensions có số lượng hữu hạn như app, environment, result, command type.

## 20. Cảnh báo Redis: ngưỡng, cửa sổ và runbook

Một alert tốt cần nêu **signal → phạm vi → cửa sổ đánh giá → ngưỡng → người nhận → hành động**. Không nên đặt tất cả alerts theo một ngưỡng cố định, vì Redis instance 1 GB dùng cho dev khác với cluster nhiều shards của production.

### 20.1. Những cảnh báo ưu tiên

| Alert | Điều kiện gợi ý để hiệu chỉnh | Hành động |
|---|---|---|
| **Memory pressure** | Used memory cao kéo dài, có hoặc sắp có evictions | Xem TTL, big keys, growth, scale plan |
| **Evictions tăng bất thường** | Eviction rate cao hơn baseline và miss/DB load tăng | Điều tra working set, eviction policy |
| **Server load/capacity** | Server load cao nhiều phút, p95 command latency tăng | Tìm hot keys/slow commands, đánh giá scale |
| **Hot shard** | Một shard load/latency vượt xa các shards khác | Phân tích slot/key distribution, hotspot |
| **Connections spike** | Connected clients tăng sau rollout/failover | Kiểm tra Java client lifecycle/reconnect |
| **Cache unavailable** | Java cache error/timeout rate vượt SLO | Mở incident, kiểm tra Redis/network/identity |
| **DB fallback quá tải** | Cache fallback tăng cùng DB CPU/connections | Bật bounded fallback, giảm traffic, bảo vệ DB |
| **Hit rate giảm** | Hit ratio giảm lớn so với baseline theo workload | Kiểm tra deploy, key version, TTL, eviction |
| **Replication/failover** | Redis node/role/health thay đổi hoặc có sự kiện maintenance | Kiểm tra RTO, client recovery, dữ liệu |
| **Cost/capacity** | Memory growth dự báo sắp vượt mức hoặc tier cost tăng | Dự báo scale và tối ưu cache |

Không đánh giá cache hit ratio khi tổng số hits+misses gần bằng 0 rồi báo động vì tỷ lệ biến động lớn trên ít mẫu. Thêm **minimum traffic condition**, evaluation window và suppression/cooldown để giảm alert noise.

### 20.2. Ví dụ alert policy

Đối với Redis phục vụ catalog:

```text
Signal: cache_error_rate do Java đo
Scope: orders-api production
Condition: > 2% requests tra cứu cache trong 5 phút
AND: số cache lookups > 1000 trong 5 phút
Severity: P2 nếu DB fallback khỏe, P1 nếu API error/p95 vượt SLO
Action group: SRE on-call + incident system
Runbook: "Redis unavailable / fallback overload"
```

Ngưỡng là **ví dụ để minh họa chính sách**, không phải thông số chuẩn Azure. Với workload khác phải suy ra từ traffic và SLO thật.

### 20.3. Alert không nên dựa chỉ một nguồn

Nếu Redis `server load=90%` nhưng API p95, hit ratio, error rate vẫn bình thường, có thể là tải dự kiến; cần capacity planning thay vì lập tức coi là outage. Nếu Redis resource metrics bình thường nhưng Java client timeouts tăng, có thể là DNS, TLS, network hoặc client event loop bị nghẽn. **Cross-correlate** để tránh xử lý sai.

### 20.4. Alert pipeline và permissions

Trong Azure Monitor, một metric alert hoặc log search alert thường cần:

1. Scope đúng resource/workspace.
2. Signal thực sự tồn tại (metric name, dimension, unit).
3. Aggregation và granularity phù hợp.
4. Threshold và evaluation window.
5. Action group, người nhận, severity và lịch trực.
6. Tag môi trường/owner, ticket/runbook link.
7. Kiểm thử một tình huống giả lập trong dev/staging.

Người được phép **xem metrics** không nhất thiết được phép **sửa alert hoặc Redis resource**. Tách RBAC và sử dụng IaC/change review cho cấu hình alerts quan trọng.

## 21. Disaster recovery đa vùng và geo-replication

**HA trong một region** không đủ khi toàn region gặp sự cố. Với yêu cầu cao, cần một kế hoạch **disaster recovery (DR)** gồm vùng dự phòng, cách định tuyến app, nguồn dữ liệu, RPO/RTO và thao tác failover/failback.

### 21.1. Các mô hình DR phổ biến

| Mô hình | Nguyên lý | Lưu ý |
|---|---|---|
| **Recreate cache in secondary region** | Dựng Redis mới, làm đầy từ DB/nguồn dữ liệu | Phù hợp cache tái tạo; cold-start và DB load lớn |
| **Passive geo-replication** (nếu hỗ trợ) | Dữ liệu được nhân bản sang cache vùng dự phòng | Async replication có lag; failover có thể cần thao tác riêng |
| **Active-active geo-distribution** (nếu hỗ trợ) | Nhiều vùng xử lý reads/writes theo mô hình dữ liệu tương thích | Conflict resolution/consistency khác Redis single-primary; phải kiểm thử |
| **Dual-region application + independent caches** | Mỗi region dùng cache gần app, DB source of truth có DR riêng | Không có shared cache consistency tự động |

Các hình thức geo-replication và active-active **không có trên mọi Azure Redis product/tier**. Xác minh đúng SKU, region pairing, network, licensing/features và các giới hạn của multi-region data structures trước khi thiết kế.

### 21.2. Async replication và RPO

Với geo-replication bất đồng bộ, region B có thể chậm hơn region A. Nếu region A mất đột ngột, những writes chưa tới B có thể bị mất. **Không tự hứa RPO=0** chỉ vì có một secondary Redis.

Với cache product, có thể rebuild; với session, người dùng có thể phải đăng nhập lại; với business state quan trọng, phải dựa vào durable database có DR thích hợp.

### 21.3. DR runbook cần bao gồm

1. **Trigger:** khi nào quyết định failover region? Ai được phê duyệt?
2. **Data classification:** cache có thể bỏ qua/rebuild hay cần restore/replication?
3. **Dependencies:** Azure SQL/Storage/Service Bus, identity, DNS, secrets, network.
4. **Traffic routing:** Front Door/Traffic Manager/DNS hoặc cơ chế phù hợp.
5. **Cache connection:** endpoint, port, TLS, ACL/Entra auth của region B.
6. **Warm-up:** tránh mọi ứng dụng cùng tải toàn bộ keys từ database.
7. **Validation:** API p95/error rate, hit rate, DB load, stale data.
8. **Failback:** phục hồi A rồi quay lại thế nào, xử lý dữ liệu xung đột/lost cache.

Một runbook “đổi DNS sang region B” là chưa đủ nếu database/identity/backend chưa sẵn sàng ở B hoặc app đang giữ Redis hostname cũ trong JVM.

### 21.4. Cache consistency trong active-active

Nếu sản phẩm/tier có active-active Redis dựa trên conflict-free replicated data types hoặc cơ chế tương đương, không mặc định tất cả commands, data types và Lua/transactions có cùng semantics như một Redis primary duy nhất. Với writes đồng thời từ hai regions, cần hiểu **conflict resolution và eventual consistency**. Đánh giá workload phù hợp; những invariant tài chính cần transaction store có cơ chế nhất quán được thiết kế riêng.

## 22. Security: TLS, private connectivity và authentication

Redis tốc độ cao nhưng không được đặt trên mạng mở với credentials yếu. Trong Azure, cần thiết kế **mạng, danh tính, secret lifecycle và quyền data plane**.

### 22.1. Private networking

Một sơ đồ khái niệm:

```text
AKS / App Service / Container Apps
              |
              | VNet integration / node egress
              v
        VNet / private DNS
              |
        NSG / Firewall / route
              |
              v
       Azure Redis endpoint
       (private access nếu SKU hỗ trợ)
```

Các kiểu private endpoint/virtual network injection và mức hỗ trợ **khác giữa Managed Redis và Cache for Redis tiers**. Không tự bật/tắt public access production chỉ vì thấy một hướng dẫn cho SKU khác; phải xác minh toàn bộ clients/diagnostics/migration tools kết nối được sau thay đổi.

### 22.2. TLS bắt buộc theo chính sách

- Chỉ dùng TLS khi trao đổi credentials và cache data qua mạng.
- Xác minh server certificate chain và hostname.
- Đừng bật kết nối plaintext/disable SSL để sửa lỗi DNS.
- Lập kế hoạch certificate/CA rotation trong JVM containers.
- Kiểm tra từ **runtime thực tế**, không chỉ laptop developer.

### 22.3. Microsoft Entra ID và ACL/access keys

Một số Azure Redis offerings hỗ trợ **Microsoft Entra authentication** với data access policy/Redis ACL model; những triển khai khác còn dùng **access keys/password**. Khả năng hỗ trợ tùy dịch vụ/tier/region/phiên bản, nên:

1. Ưu tiên identity-based authentication nếu workload và Redis resource hỗ trợ.
2. Xác định **runtime principal** (managed identity, workload identity, service principal) thực sự dùng.
3. Cấp đúng **Redis data-plane permissions**, không mặc định Azure RBAC Contributor trên tài nguyên đồng nghĩa được chạy mọi Redis commands.
4. Khi Entra token có hạn, hỗ trợ **refresh/re-auth** trước khi token hết hạn và khi reconnect.
5. Nếu còn dùng keys, lưu trong secrets manager, rotation và audit; không commit key vào repository.
6. Giới hạn Redis commands theo nhu cầu khi ACL/tính năng cho phép, tránh đặc quyền flush/config/admin cho web app.

### 22.4. Key naming và PII

Không nhúng email, số điện thoại, token hoặc user ID nhạy cảm trực tiếp trong Redis key nếu không cần. Key names có thể xuất hiện trong logs, diagnostics, metrics sampling hoặc debugging tools. Dùng opaque identifiers và prefix có version; định nghĩa retention/TTL phù hợp data classification.

### 22.5. Tránh lệnh nguy hiểm ở production

Các lệnh như `FLUSHALL`, `FLUSHDB`, những `CONFIG SET` nhạy cảm, `KEYS *` hay `MONITOR` có thể gây mất dữ liệu, nghẽn hoặc rò rỉ thông tin. Dịch vụ managed có thể cấm/giới hạn một số lệnh; nếu có quyền dùng, vẫn cần change review và môi trường thử nghiệm. **Không dùng `FLUSHALL` làm cách sửa cache performance.**

## 23. Chi phí và capacity planning

Chi phí Redis trên Azure không chỉ là kích thước cache:

| Khoản | Điều ảnh hưởng | Hướng kiểm soát |
|---|---|---|
| **Redis tier/instance** | Capacity, SKU, vùng, số node/shards và thời gian chạy | Chọn theo working set và SLO, không đoán theo số users |
| **HA replication** | Số replicas/zones theo topology | Thiết kế theo RTO/RPO thực |
| **Geo-replication/DR** | Secondary region, network và dữ liệu đồng bộ | Chỉ dùng khi business RTO/RPO yêu cầu |
| **Network** | Private endpoints, Firewall/NAT, cross-region traffic, egress | Chọn vùng gần app, tối ưu traffic |
| **Monitoring** | Diagnostic log volume, retention, alerts, Application Insights | Thu dữ liệu có mục đích, sample logs |
| **Application/database** | Cache misses làm tăng SQL compute/IOPS | Tối ưu hit ratio, TTL, fallback và warm-up |
| **Migration/scale operations** | Resharding/dual run, testing, temporary peak capacity | Lập maintenance và rollback plan |

**Không đưa một bảng giá cố định** vì product/tier/region và pricing thay đổi. Dùng Azure Pricing Calculator, Cost Management và usage thực tế để lựa chọn.

### 23.1. Mở rộng RAM hay giảm dữ liệu cache?

Nếu used memory đạt 90% và evictions tăng:

1. Xác định keys thật sự cần cache.
2. Kiểm tra payload size, TTL quá dài, stale keys của các schema versions cũ.
3. Xem working set theo traffic; loại cache những objects ít được đọc.
4. Kiểm tra big keys, serialized format và memory fragmentation.
5. Sau khi tối ưu, dự báo tăng trưởng và cân nhắc scale.

Không giảm TTL xuống gần 0 chỉ để giảm RAM: misses tăng có thể đẩy chi phí lớn hơn lên Azure SQL và làm xấu user latency.

### 23.2. Dự toán mở rộng và rollout

Giả sử Redis hit rate giảm từ 96% xuống 80% trên 10 triệu reads/ngày:

```text
Trước: misses ≈ 400.000/ngày
Sau:   misses ≈ 2.000.000/ngày
Tăng:  1.600.000 DB fallback reads/ngày
```

Đây là mô hình đơn giản nếu mỗi cache miss dẫn đến một DB read; request coalescing và application-local cache có thể giảm, trong khi multi-query load có thể tăng hơn. Khi đánh giá Redis capacity, tính cả **giá database traffic sau miss**.

### 23.3. Cost-aware monitoring

Giữ metrics tổng hợp (hit/error/memory/latency) để phát hiện vấn đề, nhưng không log mọi key-value trên mỗi request. Đặt retention/diagnostic categories theo nhu cầu audit và điều tra. Với metrics có dimensions, tránh labels có cardinality lớn như raw key/transaction ID để không tăng chi phí và gây tải hệ thống theo dõi.

## 24. Runbook: khi Redis primary failover

### 24.1. Dấu hiệu nhận biết

- Redis platform health/failover event hoặc node role thay đổi theo tín hiệu dịch vụ cung cấp.
- Client errors: connection reset, timeout hoặc cluster redirects tăng.
- Java circuit breaker chuyển OPEN, cache fallback tăng.
- DB read traffic và latency bắt đầu tăng.
- Redis hit rate giảm tạm thời do cache chưa warm hoặc dữ liệu mới chưa sync.

**Không tự kết luận primary failover chỉ từ một timeout**: mạng, credentials, client threads hoặc GC cũng có thể gây lỗi.

### 24.2. Quy trình ứng phó

1. **Xác nhận incident scope:** một application replica, một shard hay toàn Redis resource?
2. **Kiểm tra Azure Redis resource health:** có maintenance/failover/scale operation đang diễn ra không?
3. **Kiểm tra Java metrics:** Redis timeout/reconnect, p95, circuit state, fallback volume.
4. **Kiểm tra DB:** SQL CPU/active connections/query latency có tăng do misses không?
5. **Giới hạn tải:** bật bounded fallback, request coalescing, rate limit nếu cần.
6. **Không flush/restart mọi pods:** tránh đồng loạt reconnect/cache cold start.
7. **Chờ/reconnect có kiểm soát:** client cập nhật topology và thử lại những operations an toàn.
8. **Xác minh data:** cache có thể thiếu/stale, nhưng giao dịch quan trọng phải lấy từ DB source of truth.
9. **Theo dõi recovery:** cache error giảm, hit ratio tăng, DB trở về baseline, API SLO hồi phục.
10. **Postmortem:** timeline, RTO thực tế, RPO/keys có thể mất, chất lượng alerts và cải tiến runbook.

### 24.3. Điều không nên làm

- Không tăng connection timeout lên vài phút cho toàn API.
- Không retry `INCR`/list push mù khi ACK có thể đã mất.
- Không gọi `FLUSHALL` để “đồng bộ cache”.
- Không ép tất cả requests fallback vào DB khi DB đã bão hòa.
- Không tự chuyển DNS/primary sang region khác nếu chưa có DR approval/data reconciliation.
- Không tắt TLS/Redis authentication để loại lỗi connectivity.

### 24.4. Dấu hiệu khôi phục hoàn tất

Khôi phục không chỉ là Redis resource báo healthy. Cần xác nhận:

```text
Redis command error/timeout rate về baseline
Redis read/write latency đạt SLO
Java connection/reconnect ổn định
Cache hit ratio phục hồi theo working set
DB CPU/connections giảm sau burst fallback
API p95/p99 và error rate phục hồi
Không có side effect trùng ở Redis counters/flows quan trọng
```

Nếu Redis healthy nhưng Java p95 vẫn cao, tiếp tục điều tra cache warm-up, thread pool, DNS, client topology và database backpressure.

## 25. Runbook: Redis memory pressure và eviction storm

### 25.1. Kịch bản

Một cache catalog bắt đầu tăng evictions, DB read load tăng, API p95 xấu đi. Redis server load có thể chưa cao, nên không thể chỉ nhìn CPU.

### 25.2. Các bước

1. Xác minh **used memory**, eviction rate, expired keys và hit ratio theo cửa sổ thời gian.
2. So sánh key count/working set với deployment gần đây, thay serializer/version hoặc batch jobs.
3. Kiểm tra memory fragmentation và top-sized values/collections bằng công cụ cho phép.
4. Xem TTL distribution: có keys không TTL dù nghiệp vụ không cần tồn tại mãi?
5. Xác định một thay đổi key prefix mới có làm tăng double-cache memory không.
6. Giới hạn producers tạo keys ít giá trị; sửa data model/TTL/serialization nếu cần.
7. Đánh giá scale up/out dựa trên working set đã tối ưu, không scale mù.
8. Theo dõi DB fallback và API latency sau thay đổi.
9. Tạo cảnh báo predictive capacity thay vì đợi tới mức 100% mới hành động.

### 25.3. Phân biệt eviction và expiration

Nếu **Expired Keys** tăng theo TTL và hit ratio vẫn ổn định, đó có thể là hành vi bình thường. Nếu **Evicted Keys** tăng cùng used memory cao, misses tăng và DB bão hòa, workload có thể không phù hợp với dung lượng/policy. Cần xem **tập hợp tín hiệu**, không dựa duy nhất một counter.

### 25.4. Không thay maxmemory policy tùy tiện

Nếu chuyển từ `noeviction` sang `allkeys-lru`, ứng dụng vốn dựa vào key tồn tại có thể bắt đầu mất data không dự kiến. Nếu chuyển ngược lại, write errors có thể tăng ngay khi memory đầy. Phải xác định phân loại dữ liệu cache, backup/persistence và behavior của application trước khi đổi policy.

## 26. Runbook: Redis healthy nhưng Java client timeout

### 26.1. Đặt câu hỏi đúng

Redis metrics ổn nhưng Java `RedisCommandTimeoutException` tăng. Những nguyên nhân có thể:

- AKS node egress, NSG/firewall, NAT/SNAT pressure hoặc DNS resolution.
- TLS handshake/certificate/trust store hoặc credentials hết hạn.
- Client-side event loop bị block, CPU/GC pause, quá nhiều in-flight commands.
- Connection pool/queueing trong thư viện Java.
- Big key response, serializer chậm hoặc command blocking.
- Topology stale sau resharding, client không cluster-aware.
- Network RTT giữa region app và Redis quá cao.

### 26.2. Thứ tự kiểm tra

1. **Scope:** một pod, một node, tất cả pods hay một region?
2. **Client:** version Lettuce/Spring Data Redis, thread/GC metrics, command timeout, reconnect count.
3. **Kết nối:** DNS, endpoint/port, TLS, ACL/Entra token refresh từ runtime thực tế.
4. **Mạng:** route, firewall/private endpoint, packet loss và cross-region path.
5. **Redis:** server load/per-shard latency, connections, command mix, slowlog khi có quyền.
6. **App:** serialize/deserialize time, response size và in-flight command count.
7. **Topology:** Redis Cluster slot mapping, redirects, có reshard/failover vừa diễn ra?
8. **Test có kiểm soát:** một GET/SET key lab trên đường kết nối hợp lệ; không chạy destructive commands.
9. **Khắc phục đúng nguyên nhân:** code/client, credentials, route, hot key hoặc capacity.
10. **Xác minh SLO:** Java timeout p95 giảm và DB fallback không quá tải.

### 26.3. Kiểm tra bằng redis-cli

Trong môi trường lab hoặc máy quản trị đã được phép truy cập:

```bash
REDIS_HOST="<redis-host-from-azure-resource>"
REDIS_PORT="<tls-port-from-azure-resource>"

# Lựa chọn auth an toàn theo sản phẩm: Entra token/Redis ACL/secret store.
# Tránh truyền password trực tiếp trên command line hoặc trong shell history.
redis-cli --tls -h "$REDIS_HOST" -p "$REDIS_PORT" PING
```

Đây là lệnh **kết nối cơ bản**, có thể trả lỗi authentication nếu resource yêu cầu credential (điều đó bình thường). Hãy dùng quy trình credential mà đội bảo mật phê duyệt; với Entra token/ACL có thể cần thêm username/secret và phiên bản redis-cli tương thích.

`PING` thành công chứng minh chỉ **một** kết nối/command tại thời điểm thử, không chứng minh mọi shards, commands, permissions, failover hoặc application SLO đều tốt.

## 27. Kiểm thử HA và scaling trước production

Không nên bật HA rồi tuyên bố hệ thống an toàn nếu chưa kiểm thử **client recovery và DB fallback**. Chỉ thực hiện fault injection/failover trong môi trường được phép, tránh cố tình phá production resource của các nhóm khác.

### 27.1. Ma trận kiểm thử

| Bài test | Cách thử có kiểm soát | Kết quả mong muốn |
|---|---|---|
| **Cache hit/miss** | Gọi một key có/không có trong Redis lab | Application phân biệt hit/miss đúng |
| **TTL expiry** | Key hết hạn | Đọc DB đúng, không data corruption |
| **Redis network outage** | Chặn kết nối từ một Java pod trong test | Timeout có giới hạn, bounded fallback |
| **Primary failover** | Dùng cơ chế test/failover được dịch vụ hỗ trợ và đã phê duyệt | Client reconnect, SLO degrade trong mục tiêu |
| **Zone failure scenario** | Thử theo khả năng giả lập của môi trường | Topology chịu lỗi như đã thiết kế |
| **Cold cache** | Tạo cache mới trống | DB không sập vì cache stampede |
| **Eviction pressure** | Tạo dataset test vượt working set có kiểm soát | Policy ứng xử đúng, alerts kích hoạt |
| **Cluster resharding** | Scale shards trong dev/staging | Cluster client refresh topology, không mất nghiệp vụ |
| **Hot key** | Dồn requests vào một key | Nhận diện shard/latency hotspot |
| **Connection storm** | Khởi động đồng thời nhiều app replicas | Không vượt client/Redis/network limits |
| **Credential rotation** | Rotation test theo chính sách | New connections/reconnect lấy credential hợp lệ |
| **Entra token expiration** | Chạy app qua chu kỳ token expiry | Token refresh không làm Redis mất kết nối kéo dài |
| **Region DR** | Chuyển traffic sang region test | App, DB, Redis endpoint và auth đều sẵn sàng |
| **Chaos duplicate outcome** | Cắt ACK của stateful Redis command trong test | App không tạo side effects trùng ngoài contract |

### 27.2. Load test có những số đo nào?

Chạy nhiều kịch bản:

```text
App replicas:     2 -> 8 -> 20
Cache hit ratio:  98% -> 80% -> 40%
Key size:         small -> medium -> large
Traffic pattern:  uniform -> hotspot
Redis topology:   baseline -> scaled
```

Quan sát **throughput, client p50/p95/p99, Redis server load, per-shard distribution, used memory, evictions, connections, DB CPU, SQL query p95, cache fallback và error rate**.

Đừng tối ưu chỉ theo commands/second. Nếu Redis throughput tăng nhưng HTTP p99 xấu hơn và SQL cost tăng, phương án chưa chắc đáp ứng mục tiêu hệ thống.

### 27.3. Đo RTO theo góc nhìn người dùng

RTO của Redis resource và **thời gian API phục hồi SLO** có thể khác nhau. Một primary được promote nhanh, nhưng ứng dụng còn cần reconnect, refresh DNS, warm cache và giảm DB pressure. Khi nghiệm thu, ghi cả:

- Thời điểm Redis bắt đầu lỗi.
- Thời điểm Redis endpoint phục hồi lệnh kiểm thử.
- Thời điểm Java cache errors trở lại baseline.
- Thời điểm API error rate/p95 trở lại SLO.
- Khoảng thời gian nào xảy ra stale/missing cache và có gây side effects không.

### 27.4. Kiểm thử mà không làm lộ production secrets

Sử dụng riêng lab Redis resource, synthetic keys và secrets test, không copy raw session tokens hay dữ liệu khách hàng vào lab. Với dữ liệu thật có liên quan privacy, cần phương án masking/anonymization và quyền rõ ràng.

## 28. Tình huống thực tế: cache Redis của nền tảng đặt hàng

### 28.1. Yêu cầu nghiệp vụ

Hệ thống dùng:

```text
Azure Front Door / API gateway
          |
          v
AKS orders-api (12 pods, tối đa 30)
          |
          +-- L1 cache: data đọc ít thay đổi, TTL ngắn trong JVM
          |
          +-- Azure Redis: catalog và promotion cache
          |       |
          |       +-- HA primary/replica theo SKU
          |       +-- TLS, private connectivity
          |       +-- Metrics/alerts
          |
          +-- Azure SQL: product/order source of truth
          |
          +-- Application Insights / Azure Monitor
```

Các mục tiêu:

- Redis đọc sản phẩm đạt độ trễ thấp trong hoạt động bình thường.
- Redis failover không gây mất dữ liệu đơn hàng hoặc double charge.
- Trong lúc cache unavailable, app phải bảo vệ Azure SQL bằng bounded fallback.
- Traffic tăng gấp ba không làm một hot key/shard quá tải.
- SRE có dashboard, alert, runbook và kiểm thử failover có bằng chứng.
- Cache được tối ưu theo budget/tier phù hợp.

### 28.2. Phân loại dữ liệu

| Dữ liệu | Nguồn thật | Cache design | Trong failover |
|---|---|---|---|
| Product details | Azure SQL | Redis TTL 5 phút + jitter | Bounded DB fallback, có thể local stale ngắn |
| Promotion rules | Config/SQL | Redis TTL ngắn, versioned | Kiểm tra điều kiện áp dụng cuối ở nguồn tin cậy |
| Order payment status | Azure SQL | Cache chỉ là projection để hiển thị | Không xác nhận thanh toán từ cache |
| Idempotency record | Transactional DB | Không dùng Redis là source of truth | Không thực hiện charge trùng |
| Session | Phụ thuộc yêu cầu authentication | TTL/security policy riêng | Có thể buộc login lại nếu chấp nhận mất session |

### 28.3. Tính capacity

Giả sử:

```text
1.500.000 product entries
Average effective footprint ~2 KiB/key
Raw estimate ~2,86 GiB trước overhead khác
Peak traffic ~50.000 cache lookups/s
Hot promotion key có thể chiếm 35% requests
```

Đánh giá theo hai chiều:

1. **Memory:** working set, TTL, replication/persistence overhead và fragmentation, cần headroom cho deploy và reshard.
2. **Throughput:** nhiều requests dồn một hot key có thể quá tải một shard dù tổng memory thấp.

Phương án xử lý hot promotion key: JVM L1 cache TTL 2–5 giây nếu nghiệp vụ chấp nhận, request coalescing và event invalidation khi thay rules; đồng thời kiểm tra Redis load trên shard liên quan.

### 28.4. Khi failover xảy ra

Kịch bản giả định:

```text
14:00:00 Redis normal, hit ratio 96%
14:05:00 Redis primary failover begins
14:05:02 Java cache timeouts increase
14:05:04 Circuit breaker OPEN; bounded DB fallback
14:05:10 SQL CPU tăng nhưng vẫn dưới ngưỡng chịu tải
14:05:20 Redis clients reconnect, cache requests phục hồi
14:06:00 Redis hit ratio dần tăng nhờ warm-up
14:07:00 HTTP p95 trở lại baseline
```

Đây là timeline **minh họa**, không phải SLA hay số đo thực tế của Azure Redis. Nếu SQL CPU chạm 100% khi fallback, runbook cần điều chỉnh concurrency/rate limits và đánh giá việc phục vụ stale data được phép thay vì chỉ chờ Redis hồi phục.

### 28.5. Tiêu chí nghiệm thu

- App xác minh kết nối TLS và quyền Redis từ runtime thật.
- Không có secrets trong key/value/log/metric label.
- HA/failover không được báo cáo như zero data loss nếu dùng async replication.
- Redis command error giảm sau recovery; API p95 đạt SLO đã đặt.
- SQL không sập vì cache cold-start/fallback.
- Product cache có TTL, jitter, serialization version, invalidation.
- Hot key và per-shard imbalance có alert hoặc phương án quan sát.
- DR có runbook độc lập với HA intra-region.
- Chi phí Redis, SQL fallback, network và monitoring có baseline.

## 29. Migration và nâng cấp Redis không làm mất kiểm soát

Khi nâng version engine, đổi tier hoặc chuyển từ một Azure Cache for Redis hiện hữu sang Azure Managed Redis, không nên coi đó là thao tác đổi hostname đơn giản.

### 29.1. Compatibility checklist

| Thành phần | Cần kiểm tra |
|---|---|
| **Redis engine/modules** | Commands, data structures, Lua/scripts, features/limits |
| **Cluster mode** | Proxy vs direct cluster, hash slots, redirect behavior, multi-key operations |
| **Authentication** | Access keys/ACL vs Entra, client username, token refresh |
| **TLS/network** | Endpoint, port, cert chain, private DNS/endpoint availability |
| **HA/DR** | Replica count, zones, persistence, geo-replication, RPO/RTO |
| **Memory policy** | Maxmemory, eviction semantics, cache warming |
| **Client Java** | Lettuce/Jedis/Spring Data Redis versions, topology refresh |
| **Monitoring** | Metrics/categories/tables, dashboard/alert mapping |
| **Pricing** | New tier instance cost, temporary dual-run/network |

### 29.2. Migration theo từng bước

1. **Inventory:** xác định Redis product/tier/version, keys, TTLs, value schema, command usage và constraints.
2. **Classification:** dữ liệu nào có thể mất/rebuild? Có session/counter/workflow state không?
3. **Compatibility test:** Java client, SSL, ACL, cluster, scripts/multi-key semantics.
4. **Target deployment:** tạo Redis ở đúng region/network/HA và giám sát.
5. **Data transfer strategy:** chọn phương án export/import, replication hoặc cache warming được **cả nguồn và đích hỗ trợ**, không tự coi mọi cặp sản phẩm cho phép online migration.
6. **Canary:** chuyển lưu lượng ít rủi ro, đối chiếu hit ratio, latency, stale data, failover.
7. **Gradual cutover:** tách config/feature flag, theo dõi errors và DB load.
8. **Rollback:** giữ đủ điều kiện quay lại khi có lỗi; xác định cách xử lý keys ghi sau cutover.
9. **Decommission:** chỉ xóa cache cũ khi kiểm tra không còn clients/keys cần giữ.

**Không dùng `FLUSHALL` tại nguồn trước cutover**. Nếu dữ liệu không chỉ là cache tái tạo, cần phương án bảo vệ và khôi phục tương ứng với độ bền dữ liệu.

### 29.3. Dual-write có rủi ro gì?

Một ứng dụng gửi `SET` cho hai Redis resources có thể thành công ở A và thất bại ở B; không có atomic transaction tự nhiên trên hai deployments. Khi cutover, dữ liệu có thể lệch. Với **cache-aside**, thường an toàn hơn khi target cache cold/warm và để database quyết định dữ liệu đúng; với session/counter cần chiến lược migration riêng và kiểm thử.

### 29.4. Kiểm tra support lifecycle và roadmap

Kế hoạch Azure Redis và khả năng của từng tier có thể thay đổi. Trước khi chọn mới hoặc gia hạn kiến trúc cũ, kiểm tra **thông báo vòng đời sản phẩm, thời hạn hỗ trợ/migration, parity features và regional availability** từ nhà cung cấp. Không tự lập ngày retirement hoặc tính năng chỉ dựa trên một ví dụ code.

## 30. Bài tập thực hành

### Bài tập A – HA và tính nhất quán

Một cache sản phẩm dùng primary + replica theo mô hình replication bất đồng bộ. Java vừa `SET product:1042` rồi primary lỗi trước khi replica nhận write.

**Nhiệm vụ:** giải thích vì sao sau failover `GET` có thể miss; xác định RPO phù hợp cho product cache, session store và payment ledger; nêu vì sao “đã có replica” không đồng nghĩa zero data loss.

**Hướng giải:** cache product đọc lại SQL, session có thể cần UX fallback hoặc persistence/DR phù hợp, payment ledger không được lấy Redis làm source of truth.

### Bài tập B – Scale out và Redis Cluster

Một cluster có ba shards, keys phân phối đều. Ứng dụng cần atomic operation trên `order:1042:header` và `order:1042:items` nhưng gặp `CROSSSLOT`.

**Nhiệm vụ:** thiết kế lại keys dùng hash tag, giải thích vì sao không dùng `{all}` cho mọi keys, và mô tả kiểm thử khi tăng lên sáu shards.

**Hướng giải:** nhóm `order:{1042}:header` và `order:{1042}:items` cùng slot; giữ mỗi order ở partition riêng để tránh hotspot. Kiểm tra client topology refresh và redirects.

### Bài tập C – Cache stampede

Key `promotion:global` có 40.000 reads/s và TTL 300 giây. Sau một rollout, key hết hạn, Redis miss hàng loạt; Azure SQL nhận thêm 40.000 queries/s.

**Nhiệm vụ:** đề xuất TTL jitter, single-flight, L1 cache, bounded DB fallback và đo metrics. Giải thích trường hợp một key duy nhất cần thêm chiến lược gì ngoài jitter giữa nhiều keys.

**Hướng giải:** jitter giữa các keys không giải quyết hoàn toàn **một hot key**. Cần coalescing/near-cache/background refresh và limit fallback.

### Bài tập D – Azure Monitor dashboard

Bạn có một Azure Redis resource nhưng không biết metric names và dimensions. Viết quy trình:

1. Liệt kê metric definitions bằng Azure CLI/Portal.
2. Chọn used memory, server load, connections, evictions, hits/misses và latency **nếu được hỗ trợ**.
3. Dùng per-shard dimensions để tránh average che hot shard.
4. Ghép với Java cache errors/p95 và Azure SQL CPU.
5. Đặt một alert có evaluation window, owner và runbook.

**Hướng giải:** dùng `az monitor metrics list-definitions` với đúng Resource ID, kiểm tra aggregation/time grains và naming trước khi tạo alert.

### Bài tập E – Redis timeout trên AKS

Redis báo healthy nhưng một nhóm pods trên node A liên tục timeout sau khi networking policy thay đổi.

**Nhiệm vụ:** phân biệt Redis server load với network/DNS/TLS/client GC, kiểm tra đường từ **pod thật**, và chỉ ra vì sao tăng Redis size không phải lời giải.

**Hướng giải:** xem pod/node scope, DNS, egress, private endpoint, firewall/NSG, TLS và Redis client metrics. Không vô hiệu hóa TLS hoặc mở public network để “thử”.

### Bài tập F – Migrate từ cache hiện hữu

Một ứng dụng Redis cũ dùng access keys, port TLS đặc thù, single-node client và Lua script truy cập nhiều keys. Tổ chức dự định dùng Azure Managed Redis.

**Nhiệm vụ:** lập compatibility plan về endpoint, auth, version, cluster, Lua/multi-key restrictions, replication/persistence, metrics và migration/rollback.

**Hướng giải:** chọn target SKU theo tính năng thực tế, test Java client, đánh giá chuyển đổi password→Entra nếu được hỗ trợ, đo cold-cache load và không coi dual-write là atomic.

### Bài tập G – Failover game day

Trong staging, thực hiện một failover theo khả năng dịch vụ và quyền đã được phê duyệt. Đo:

- Thời gian Redis endpoint ngừng/khôi phục.
- Java command timeout/reconnect và circuit state.
- DB fallback rate và CPU.
- API p95/p99/error rate.
- Cache hit ratio sau warm-up.
- Sự khác nhau giữa HA resource recovery và end-to-end application RTO.

**Hướng giải:** dùng một incident timeline UTC, đánh giá alerts có kích hoạt đủ sớm và không tạo side effects trùng, rồi đề xuất chỉnh timeout/backoff/DB bulkhead.

### Bài tập H – Phân tích memory pressure

Một Redis instance có used memory 92%, evicted keys tăng và hit ratio giảm từ 94% xuống 75%.

**Nhiệm vụ:** xác định liệu có big keys, TTL quá dài, payload schema mới gây double-cache, fragmentation hoặc thay đổi traffic; chọn giữa tối ưu data model và scale up/out, kèm tiêu chí nghiệm thu.

**Hướng giải:** đo working set/entry sizes trước, phân biệt evictions với expirations; chọn scale dựa trên load test và chi phí tổng Redis + Azure SQL fallback.

## 31. Câu hỏi tự kiểm tra

**1. High availability của Redis có đồng nghĩa không mất một write nào khi primary lỗi?** Không. Replication có thể bất đồng bộ; RPO còn phụ thuộc topology, persistence và điều kiện failover.

**2. Redis replica khác backup ở đâu?** Replica là bản sao hoạt động phục vụ replication/failover; backup là điểm dữ liệu lưu để restore. Replica cũng có thể nhận xóa nhầm.

**3. Zone redundancy có bảo vệ khi mất cả Azure region không?** Không. Cần disaster recovery đa vùng độc lập.

**4. Khi dùng Redis chỉ làm cache sản phẩm, nguồn sự thật nên nằm ở đâu?** Database hoặc hệ thống authoritative được thiết kế, ví dụ Azure SQL.

**5. Redis primary failover có thể khiến Java thấy lỗi gì?** Connection reset, command timeout, reconnect hoặc cluster redirects tùy topology/client.

**6. Vì sao không tự retry `INCR` khi timeout?** Lệnh có thể đã tăng counter nhưng ACK bị mất; retry có thể tăng lần hai.

**7. Scale up và scale out khác nhau thế nào?** Scale up tăng capacity node/instance; scale out phân chia dữ liệu/tải sang nhiều shards theo cơ chế được hỗ trợ.

**8. Redis Cluster có bao nhiêu hash slots?** 16.384.

**9. `MOVED`/`ASK` thường liên quan điều gì?** Cluster routing hoặc slot migration; cluster-aware client cần xử lý topology.

**10. Khi nào hash tag `{orderId}` hữu ích?** Khi multi-key operation yêu cầu các keys của một đơn nằm cùng slot.

**11. Vì sao một hot key không tự hết nóng khi tăng shards?** Một key thường vẫn thuộc một slot/shard; traffic không tự tách đều.

**12. Big key có tác hại gì?** Tăng latency, network, CPU/serialization, pressure khi reshard và memory.

**13. Evicted Keys khác Expired Keys ở đâu?** Eviction do memory pressure/policy, expiration do TTL.

**14. Cache hit ratio cao có luôn nghĩa performance tốt không?** Không. Hot shard, large value, network RTT hoặc Java client contention vẫn có thể gây latency cao.

**15. Vì sao phải xem per-shard Max thay vì chỉ Average server load?** Average che một shard 95% load khi shards khác rảnh.

**16. Bật Azure Monitor metric view có đồng nghĩa mọi Redis diagnostic logs đã vào Log Analytics không?** Không. Logs cần categories, diagnostic settings và destination theo khả năng dịch vụ.

**17. Khi Redis unavailable, fallback DB luôn tốt hơn trả lỗi không?** Không. Nếu mọi request cùng fallback, database có thể sập; cần bulkhead/backpressure và lựa chọn degrade phù hợp.

**18. Single-flight giải quyết vấn đề gì?** Gom nhiều requests cùng key để giảm duplicated DB loads khi miss, nhưng single-flight một JVM không tự gom được requests giữa các pods.

**19. TTL jitter dùng làm gì?** Giảm nguy cơ nhiều keys đồng loạt hết hạn và tạo cache stampede.

**20. Redis SET có luôn an toàn để retry không?** Không. Phải xét value/version, TTL, concurrent writers và side effects.

**21. Vì sao không dùng Redis làm payment ledger duy nhất?** Replica/failover/eviction/persistence không tự cung cấp những invariant và durability của giao dịch tài chính.

**22. Redis resource healthy nhưng Java timeout tăng có thể do gì?** DNS, TLS, credential/token, network, GC/event loop, command queue hoặc topology stale.

**23. Redis private endpoint có tự tạo authorization không?** Không. Private network chỉ giới hạn kết nối; vẫn cần data-plane authentication/permissions.

**24. Có thể đặt Entra access token một lần trong password config rồi dùng mãi không?** Không. Token có thời hạn; cần refresh và re-auth khi mở/reconnect.

**25. Managed Redis và Azure Cache for Redis legacy có luôn cùng CLI/port/metrics không?** Không. Phải kiểm tra resource product/tier/version cụ thể.

**26. Geo-replication bảo đảm RPO=0 không?** Không mặc định; nhiều mô hình bất đồng bộ và có consistency/conflict semantics riêng.

**27. Cache-aside invalidation có race condition không?** Có. Read cũ có thể ghi cache lại sau khi writer đã commit và xóa key.

**28. Cần đo RTO của Redis hay của application?** Cả hai; mục tiêu người dùng là thời điểm API phục hồi SLO, bao gồm reconnect, DB fallback và cache warm-up.

**29. Vì sao không dùng `KEYS *`/`MONITOR` liên tục trên production?** Có thể gây overhead, lộ key names và làm xấu hiệu năng.

**30. Ba tín hiệu ưu tiên khi Redis evictions tăng là gì?** Used memory/working set, cache hit/miss rate và application/DB fallback latency-load.

## 32. Checklist triển khai Redis production

### 32.1. Sản phẩm và kiến trúc HA

- [ ] Đã xác định **Azure Managed Redis** hay một **Azure Cache for Redis** tier hiện hữu.
- [ ] Đã kiểm tra region, engine/version, network, endpoint/port/TLS và feature availability.
- [ ] Đã phân loại dữ liệu cache có thể rebuild với trạng thái cần persistence/durability.
- [ ] Đã xác định RPO/RTO/SLO và business owners, không hứa zero loss từ replica.
- [ ] Primary/replica và zone redundancy được cấu hình đúng SKU và vùng, nếu cần.
- [ ] Có DR đa region khi business yêu cầu, cùng traffic routing/database dependencies.
- [ ] Đã kiểm thử failover và đo **application RTO** ngoài resource recovery.
- [ ] Có runbook failover, DR/failback, data reconciliation và cache warm-up.

### 32.2. Scaling và dữ liệu

- [ ] Đã đo working set, memory overhead/fragmentation và peak growth.
- [ ] Scale up/out dựa trên memory, server load, throughput và latency thực.
- [ ] Client Java có hỗ trợ cluster/proxy topology đúng với Redis deployment.
- [ ] Đã thử slot migration và `MOVED/ASK` nếu dùng Redis Cluster.
- [ ] Đã phân tích big keys, hot keys và multi-key operations/cross-slot constraints.
- [ ] TTL/invalidation/schema-versioning phù hợp yêu cầu consistency.
- [ ] Eviction policy được lựa chọn dựa trên data classification, không đổi tùy tiện.
- [ ] Đã tính chi phí, headroom cho reshard/upgrade và memory tăng khi dual-version caches.

### 32.3. Ứng dụng Java

- [ ] Java dùng Lettuce/Jedis/Spring Data Redis phiên bản tương thích và được kiểm thử.
- [ ] Redis clients/connections được tái sử dụng đúng, không tạo client cho từng request.
- [ ] Có connect/command timeout, bounded retries và jitter/backoff.
- [ ] Không blind retry `INCR`, list push hoặc scripts có side effects chưa rõ outcome.
- [ ] Có circuit breaker, bounded DB fallback và request coalescing khi Redis mất kết nối.
- [ ] Cache miss và cache unavailable có metrics riêng.
- [ ] Không để Redis unavailable gây unbounded SQL queries.
- [ ] Session/security counters có fail-open/fail-closed policy rõ theo threat model.
- [ ] Không dùng cache projection làm nguồn dữ liệu thanh toán authoritative.
- [ ] Có graceful shutdown, reconnect và topology refresh khi scale/rollout.

### 32.4. Bảo mật và vận hành

- [ ] TLS certificate chain/hostname validation hoạt động từ pod/VM thực tế.
- [ ] Private connectivity, DNS, firewall và routing được kiểm tra theo resource SKU.
- [ ] Authentication dùng Entra/ACL hoặc keys theo khả năng; data-plane permissions tối thiểu.
- [ ] Nếu dùng Entra token, có refresh/re-auth khi token hết hạn.
- [ ] Access keys/secrets có lifecycle rotation và không nằm trong Git/log/image.
- [ ] Không có raw PII, bearer tokens hoặc Redis key nhạy cảm trong logs/metric labels.
- [ ] Không có runtime quyền quản trị không cần thiết như flush/config.
- [ ] Azure Monitor metrics definitions, aggregation/time grains và shard dimensions đã xác minh.
- [ ] Có dashboard Redis + Java + database, alerts có owner và runbook.
- [ ] Diagnostic settings/log retention đúng nhu cầu và quyền, không logging toàn keyspace.
- [ ] Đã thử network outage, eviction, hot key, failover, reshard, token expiry và cold-start.
- [ ] Có baseline chi phí/tier, traffic, hit ratio, Redis capacity, DB fallback và user p95.
- [ ] Migration/upgrade sử dụng staging, compatibility tests, canary, rollback và change review.

## 33. Kết luận

**High availability, scaling và theo dõi Redis** là một bài toán kiến trúc toàn hệ thống, không chỉ là tùy chọn bật replica trên Azure. Một topology **primary/replica** có thể giúp phục hồi khi node lỗi, nhưng replication bất đồng bộ không bảo đảm zero data loss; **zone redundancy** không thay thế DR đa vùng; persistence và backup có mục đích khác nhau. Khi tăng tải, phải phân biệt **scale up, scale out, hot keys, big keys, cluster slots và connection storm**, đồng thời lựa chọn đúng khả năng của Azure Managed Redis hoặc Redis tier hiện hữu.

Ứng dụng Java cần **TLS, authentication, timeouts, reconnect, bounded retries, cache-aside, TTL/invalidation, circuit breaker và bảo vệ database fallback** để chịu lỗi Redis. Về vận hành, hãy ghép **Azure Monitor metrics/diagnostics** với **Java command latency, cache hit/error/bypass, API SLO và Azure SQL metrics**; đặt cảnh báo có người chịu trách nhiệm và diễn tập failover/cold-cache trước production. Khi cache không còn là một single point of failure của hệ thống mà vẫn giữ được độ trễ, tính nhất quán phù hợp và ngân sách, Redis mới thực sự phát huy giá trị trên Azure.
