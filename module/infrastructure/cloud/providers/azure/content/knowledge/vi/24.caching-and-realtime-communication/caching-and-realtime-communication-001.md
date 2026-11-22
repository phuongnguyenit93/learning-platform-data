# Lựa chọn Azure Managed Redis cho ứng dụng

Một hệ thống thương mại điện tử có **Azure App Service** phục vụ API, **Azure SQL Database** giữ dữ liệu giao dịch và **Azure Container Apps/AKS** chạy các workers. Khi chương trình khuyến mãi bắt đầu, nhiều người đồng thời mở trang sản phẩm. API liên tục đọc cùng một bản ghi hàng hóa, giá và tồn kho; thời gian phản hồi tăng và database trở thành nút nghẽn. Nhóm phát triển muốn dùng Redis để giữ dữ liệu truy cập thường xuyên trong bộ nhớ, giảm số lần truy vấn SQL và đáp ứng lưu lượng đột biến.

Tuy nhiên, chọn một dịch vụ Redis không chỉ là quyết định “cache lớn bao nhiêu GB?”. Nếu yêu cầu **100.000 request/giây** nhưng dữ liệu chỉ 8 GB, bottleneck có thể là **CPU và throughput**, không phải RAM. Nếu dataset 800 GB nhưng chỉ 10% được đọc thường xuyên, cần xem tier hỗ trợ RAM + flash và chấp nhận độ trễ của dữ liệu lạnh. Nếu ứng dụng dùng thư viện Redis không hỗ trợ cluster redirect, chọn sai **clustering policy** có thể làm chương trình không hoạt động. Nếu Redis chứa session hoặc token, mất cache hoặc lỗi xác thực có thể làm hàng loạt người dùng mất phiên.

**Azure Managed Redis (AMR)** là dịch vụ Redis Enterprise do Azure quản lý. Bài học này hướng dẫn chọn Azure Managed Redis theo **mẫu truy cập, tier, kích thước, cluster policy, Redis modules, khả năng phục hồi, bảo mật, mạng và chi phí**, sau đó thiết kế tích hợp đúng vai trò cache. Đây là bài trong chương **Cache và giao tiếp thời gian thực** của module **CLOUD_PROVIDERS_AZURE**: khám phá Azure từ subscription/resource group/Microsoft Entra ID tới mạng ảo, compute, storage và dữ liệu, đồng thời triển khai, giám sát, bảo vệ và kiểm soát chi phí ứng dụng.

Sau bài học, bạn sẽ:

- Đánh giá **có thật sự cần Redis** và không nhầm cache với database, queue hay message broker bền vững.
- Phân biệt bốn tier **Memory Optimized, Balanced, Compute Optimized, Flash Optimized** và lựa chọn theo đặc tính tải.
- Chọn **OSS Cluster, Enterprise Cluster hoặc Non-clustered** dựa trên client, multi-key operations và module.
- Ước tính working set, memory overhead, connection limits, throughput, headroom, TTL và eviction.
- Thiết kế cache-aside, invalidation, chống cache stampede, session/rate-limit và graceful degradation.
- Chọn **high availability, persistence, backup/export, active geo-replication** theo mục tiêu phục hồi và ràng buộc kỹ thuật.
- Bảo vệ Redis bằng **TLS, Microsoft Entra ID, managed identity, data access permissions, Private Endpoint**.
- Xây lab Azure Portal, kiểm tra kết nối và hành vi cache với client phù hợp.
- Thiết kế giám sát, migration từ Azure Cache for Redis, đánh giá chi phí và runbook sự cố.

## 1. Redis nằm ở đâu trong kiến trúc Azure?

**Redis** là kho dữ liệu tốc độ cao, hỗ trợ key–value và nhiều cấu trúc dữ liệu như string, hash, list, set, sorted set; một số modules/tính năng còn hỗ trợ JSON, tìm kiếm và các bài toán khác. Một cache Redis thường giữ **bản sao dữ liệu** từ nguồn gốc (source of truth) để tối ưu tốc độ, không thay thế transaction database.

~~~mermaid
flowchart LR
    USER[Web/mobile client] --> API[App Service: Catalog API]
    API -->|GET key| REDIS[(Azure Managed Redis)]
    REDIS -->|Cache hit| API
    API -->|Cache miss| DB[(Azure SQL Database)]
    DB -->|Result| API
    API -->|SET with TTL| REDIS
    API --> USER
    WORKER[Background worker] -. Update business record .-> DB
    WORKER -. Invalidate affected keys .-> REDIS
    OBS[Azure Monitor / App Insights] -. Observe .-> API
    OBS -. Observe .-> REDIS
~~~

### 1.1. Chức năng cache phổ biến

| Use case | Ví dụ | Điều cần nhớ |
|---|---|---|
| **Cache-aside / read-through logic trong app** | `product:123` giữ JSON mô tả sản phẩm | Có TTL/invalidation; dữ liệu gốc nằm ở SQL |
| **Session store** | Session token/state tạm của web app | Redis outage có thể làm user logout; đánh giá security/HA |
| **Rate limiting counter** | Số request của client trong một cửa sổ | Dùng thao tác atomic/expiry và thiết kế fail-open/closed |
| **Real-time leaderboard** | Sorted set theo điểm | Bảo vệ consistency, không giả định rank luôn là dữ liệu lâu dài |
| **Feature flags / config cache** | Danh sách cấu hình ít thay đổi | TTL và versioning tránh giữ config lỗi |
| **Pub/Sub thông báo tức thời** | Worker thông báo nội bộ có cập nhật | Redis Pub/Sub không tự là durable queue |
| **Distributed coordination** | Lock ngắn hạn, token trạng thái | Cần fencing/timeout; không xây correctness từ lock cache đơn giản |
| **Search/JSON** | Tìm danh mục theo thuộc tính | Cần module và clustering policy hỗ trợ |

**Cache là một tối ưu hóa có điều kiện.** Nếu hệ thống cần replay, dead-letter handling, transaction messaging hoặc lưu message lâu dài, Azure Service Bus/Event Hubs/Event Grid (tùy use case) thường phù hợp hơn việc dùng Redis Pub/Sub như queue.

### 1.2. Phân biệt source of truth và derived data

Ví dụ bảng `Products` trên SQL chứa:

~~~text
Id=123, Name="Tai nghe A", Price=1_200_000, Version=17
~~~

Redis giữ dữ liệu dễ dựng lại:

~~~text
Key: catalog:v3:product:123
Value: {"id":123,"name":"Tai nghe A","price":1200000,"version":17}
TTL: 300 seconds
~~~

Khi Redis hết hạn hoặc bị xóa, API vẫn có thể đọc SQL rồi nạp lại dữ liệu. **Không đặt dữ liệu giao dịch duy nhất** như số dư cuối cùng, đơn hàng đã thanh toán hay thông tin kế toán chỉ trong cache. Nếu dùng Redis cho dữ liệu không thể tái tạo, yêu cầu durability/backup/transaction phải được đánh giá riêng; Azure Managed Redis không mặc nhiên là giải pháp thay database quan hệ.

### 1.3. Khi nào không nên thêm Redis?

Không cần Redis nếu dữ liệu ít truy cập lặp lại, database đã đáp ứng SLO, network latency tới Redis làm tăng tổng thời gian hoặc chi phí vận hành vượt lợi ích. Trước khi mua một Redis instance, đo:

- P50/p95/p99 API latency và tỷ lệ thời gian chờ SQL.
- Tần suất đọc lại cùng key, **working set**, hit-rate kỳ vọng.
- Mức tải CPU/IO/connection pool của SQL trước/sau khi cache.
- Độ mới dữ liệu được phép: chấp nhận stale 5 giây hay tuyệt đối không?
- Tổn thất khi cache bị xóa, failover hoặc hết TTL hàng loạt.
- Chi phí backend tiết kiệm được so với Redis compute/network/monitoring.

Redis **không miễn phí** chỉ vì là cache. Một cache kém hiệu quả với hit ratio thấp có thể vừa tạo thêm một network hop vừa tăng phí.

## 2. Azure Managed Redis khác Azure Cache for Redis cũ như thế nào?

Hai tên sản phẩm dễ bị nhầm:

- **Azure Managed Redis**: dịch vụ quản lý hiện đại dựa trên Redis Enterprise, với các tier/tính năng mới và mô hình cấu hình riêng.
- **Azure Cache for Redis**: dịch vụ thế hệ trước có những tiers **Basic, Standard, Premium, Enterprise/Enterprise Flash**. Những tiers này **không phải** bốn tier của Azure Managed Redis.

Theo thông báo vòng đời của Microsoft tính đến giai đoạn bài học:

| Dòng dịch vụ cũ | Mốc cần lập kế hoạch | Ý nghĩa |
|---|---|---|
| **Azure Cache for Redis Enterprise / Enterprise Flash** | Dự kiến ngừng dịch vụ ngày **31/03/2027** theo thông báo | Cần kế hoạch di chuyển lên Azure Managed Redis trước hạn |
| **Azure Cache for Redis Basic / Standard / Premium** | Dự kiến ngừng dịch vụ ngày **30/09/2028** | Cần đánh giá/di chuyển trước khi bị ngừng |
| **Khách hàng mới tạo cache cũ** | Có các hạn chế tạo mới đã áp dụng năm 2026 theo tenant/region | Ưu tiên Azure Managed Redis cho dự án mới |

Các mốc là **thông tin vòng đời sản phẩm có thể thay đổi**; luôn xác minh thông báo Microsoft trước khi ký hợp đồng/migration. Đừng chọn Azure Cache for Redis Basic chỉ vì thấy nhiều tutorial cũ dùng SKU đó rồi giả định đây vẫn là mặc định cho dự án mới.

Azure Managed Redis có **Redis Enterprise architecture và sharding** ngay trong thiết kế nền tảng; clustering policy quyết định hành vi phía **client**. Các giới hạn, port, endpoint DNS, modules, high availability, connection behavior và cách tạo resource có thể khác cache cũ. Đặc biệt, **Azure Managed Redis dùng endpoint thường có dạng `<cache-name>.<region>.redis.azure.net:10000`**, khác hostname/port phổ biến của các tier Azure Cache for Redis đời trước. Không copy `6380` hay connection string cũ sang AMR mà chưa kiểm tra.

> **Nguồn tham khảo chính thức:** Azure Managed Redis overview: https://learn.microsoft.com/azure/redis/overview; Azure Cache for Redis retirement: https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq.

## 3. Bốn tier Azure Managed Redis: chọn theo RAM, CPU và access pattern

Azure Managed Redis có **ba tier in-memory** khác nhau về memory-to-vCPU, và **một tier RAM + NVMe flash** cho dataset lớn. Tỷ lệ sau thể hiện **định hướng thiết kế tier**; vCPU/shard thực tế của từng SKU có thể thay đổi khi dịch vụ tối ưu hóa.

| Tier | Memory : vCPU định hướng | Khi phù hợp | Khi không phù hợp |
|---|---:|---|---|
| **Memory Optimized** | **8 : 1** | Dataset lớn, số lần truy cập/giây vừa phải, thiên về dung lượng | CPU/throughput rất cao trên mỗi GB dữ liệu |
| **Balanced** | **4 : 1** | Workload tổng quát: cache-aside, sessions, web APIs | Dataset cực lớn hoặc workloads CPU-bound cực nặng |
| **Compute Optimized** | **2 : 1** | Command rate/CPU cao, throughput lớn, workload dùng nhiều compute | Ít request, cần nhiều GB và tối ưu phí bộ nhớ |
| **Flash Optimized** | RAM kết hợp **NVMe flash** | Dataset vài trăm GB đến TB, hot/cold rõ rệt, chịu được tail latency biến thiên | Workload đọc ngẫu nhiên đều toàn dataset, ghi nặng, latency cực thấp ổn định hoặc cần modules không được hỗ trợ |

### 3.1. Memory Optimized

Tier này ưu tiên **RAM trên mỗi đơn vị CPU**, hữu ích khi dataset lớn nhưng command volume không quá cao. Ví dụ một doanh nghiệp cần cache 100 GB danh mục/feature flags cho workload đọc tương đối đều và query nhẹ.

**Không suy luận RAM lớn = luôn nhanh hơn.** Một cache 100 GB ở Memory Optimized có thể gặp bottleneck command processing trong khi cache 20 GB ở Compute Optimized chịu được nhiều requests hơn. Phải đo ops/s, Server Load/CPU và latency thật.

### 3.2. Balanced

Balanced là điểm khởi đầu hợp lý cho nhiều ứng dụng khi chưa có bằng chứng cần tối ưu cực đoan về compute/memory: giữ session, product cache và các key nhỏ cho API. Nếu muốn chạy Redis production, hãy chọn **HA** và SKU/size đáp ứng SLA/network requirements; **chọn tier Balanced không tự bật đúng tất cả security/HA settings**.

### 3.3. Compute Optimized

Compute Optimized phù hợp khi:

- Số command/giây cao và CPU/Server Load thường xuyên đạt ngưỡng.
- Có nhiều operations/computationally costly commands.
- Dataset không quá lớn so với throughput.
- Cần nhiều shards/vCPU để song song hóa hơn so với tier thiên về RAM.

Tuy nhiên, trước khi scale, hãy tìm **hot keys, lệnh O(N) gây blocking, large values, pipeline sai và kết nối quá nhiều**. Mua thêm CPU không tự chữa một key khiến tất cả traffic dồn vào một shard.

### 3.4. Flash Optimized

Flash Optimized dùng RAM cho dữ liệu nóng và NVMe flash cho dữ liệu lạnh. Một mô hình tham khảo: khoảng **20% dung lượng trên RAM** và phần còn lại trên flash (tỷ lệ thực/hành vi cần kiểm tra theo SKU). Giá trị trên flash phải được nạp về RAM khi truy cập, nên p95/p99 latency phụ thuộc mức độ nóng/lạnh của dữ liệu.

**Giới hạn quan trọng:** theo hướng dẫn hiện hành, Flash Optimized **không hỗ trợ active geo-replication**, **Non-clustered**, **RediSearch**, **RedisBloom**, **RedisTimeSeries**; cần xác nhận module hỗ trợ (ví dụ RedisJSON) trước khi chọn. Nếu workload cần tìm kiếm vector/RediSearch, **đừng chọn Flash chỉ vì dataset lớn**.

Ví dụ:

~~~text
Dataset: 900 GB
Hot working set: 100 GB
Access pattern: 90% requests to hot keys
Potential fit: Flash Optimized, but measure p95/p99 after loading production-size data.

Dataset: 900 GB
Hot working set: 850 GB
Access pattern: random reads across all keys
Potential issue: flash misses/tail latency; consider other tier/architecture.
~~~

**Hiệu năng phải đo ở mức dữ liệu gần production**. Một Flash cache mới chứa 5 GB đều ở RAM có thể trông cực nhanh trong lab, nhưng không phản ánh độ trễ khi production dataset lớn hơn RAM.

### 3.5. Chú ý SKU, preview và vùng

Một tier có nhiều **SKU sizes** với dung lượng và số client connections khác nhau; một số sizes lớn có thể ở **preview**. Không đưa preview sizes/features vào production critical workloads mà chưa kiểm tra hỗ trợ, SLA, region và governance. Các vùng Azure có tính khả dụng khác nhau; cần kiểm tra **region availability** và tính năng tier tại thời điểm tạo, không suy từ một giá toàn cầu.

**Thông tin tham chiếu:** https://learn.microsoft.com/azure/redis/plan-tiers-and-capacity.

## 4. Chọn clustering policy trước khi tạo cache

Azure Managed Redis dùng Redis Enterprise nội bộ, nhưng **client protocol** phụ thuộc clustering policy. Đây là một trong những quyết định quan trọng nhất vì **OSS/Enterprise thường không thể đổi sau khi tạo**, và lựa chọn còn ảnh hưởng modules, multi-key commands, performance.

### 4.1. Ba chính sách

| Policy | Cách client kết nối | Ưu điểm | Hạn chế |
|---|---|---|---|
| **OSS Cluster** | Client hỗ trợ Redis Cluster API, khám phá shards và xử lý `MOVED`/`ASK` | Thường throughput cao, route trực tiếp tới shard | Client phải cluster-aware; multi-key phải cùng hash slot |
| **Enterprise Cluster** | Client dùng một endpoint như Redis thường; proxy nội bộ route tới shards | Dễ tích hợp client không cluster-aware, hỗ trợ RediSearch | Proxy có thể giới hạn throughput; một số multi-key vẫn có cross-slot restrictions |
| **Non-clustered** | Client kết nối một Redis không sharding | Tương thích một số workloads nonclustered/multikey; hỗ trợ RediSearch | Chỉ tới mức dung lượng nhỏ (thường ≤25 GB), không khai thác nhiều shards; availability/tính năng preview tùy sản phẩm |

**Tên “Enterprise Cluster” không có nghĩa chỉ tier Enterprise mới dùng được.** Đây là **clustering policy**, còn Memory Optimized/Balanced/Compute Optimized/Flash Optimized là **data tier**. Hai trục lựa chọn độc lập nhưng có ràng buộc tính năng.

### 4.2. OSS Cluster và hash slots

Ở OSS clustering, Redis phân phối keys theo **hash slots**. Multi-key command/transaction/script cần các keys liên quan **cùng hash slot** hoặc có thể nhận lỗi:

~~~text
MGET product:101 product:102
    → Có thể CROSSSLOT nếu hai keys nằm ở slot khác nhau.

MGET cart:{customer-42}:items cart:{customer-42}:total
    → Hash tag {customer-42} giúp các keys thuộc cùng slot.
~~~

Không thêm hash tag `{all}` vào mọi key chỉ để bỏ lỗi: nó dồn toàn bộ workload lên một shard và phá mục tiêu scale-out. Thiết kế hash tag theo nhóm transaction thực sự cần atomic multi-key.

Một số commands/scripts không được dịch vụ quản lý cho phép. Kiểm tra Redis command compatibility, không giả định dùng được `CLUSTER SETSLOT`/thao tác quản trị topology ở managed service.

### 4.3. Enterprise Cluster: endpoint đơn giản nhưng không vô hạn

Client thấy một endpoint, proxy route nội bộ đến shard. Điều này hữu ích khi ứng dụng cũ dùng `redis.Redis`/standalone clients hoặc cần RediSearch. Tuy nhiên, **multi-key across arbitrary slots không tự được bảo đảm hỗ trợ toàn bộ**, và proxy có thể thành nút cổ chai cho workload throughput cực cao.

**Không khẳng định Enterprise Cluster hỗ trợ mọi Redis transaction across keys**. Kiểm thử command set thực sự, bao gồm Lua scripts, MULTI/EXEC, cross-slot behavior, scan, pipeline và RedisJSON/RediSearch khi dùng.

### 4.4. Non-clustered

Non-clustered phục vụ workloads nhỏ cần semantics một shard hoặc migration ứng dụng chưa thể dùng cluster. Giới hạn kích thước và trạng thái preview phải được xác minh trước production. Khi instance chuyển từ Non-clustered sang clustered, không mặc định có thể chuyển ngược. Với workloads phát triển nhanh, việc chọn Non-clustered chỉ để tránh cập nhật client có thể tạo gánh nặng migration sau này.

### 4.5. Client Java, .NET, Node.js, Python phải đúng topology

| Client library | OSS Cluster | Enterprise/Non-clustered |
|---|---|---|
| **Lettuce (Java)** | `RedisClusterClient` | `RedisClient` |
| **Jedis (Java)** | `RedisClusterClient` / API phiên bản tương ứng | `RedisClient` hoặc client đơn |
| **redis-py (Python)** | `RedisCluster` | `redis.Redis` |
| **node-redis** | `createCluster` | `createClient` |
| **StackExchange.Redis (.NET)** | Cluster discovery được thư viện hỗ trợ | Single-endpoint connection model |

Azure Managed Redis thường bắt đầu qua **TCP 10000**; với OSS Cluster, client khám phá và kết nối tới **các shard ports 85xx** theo topology hiện tại. Đừng hardcode shard ports/hostnames vào code; firewall/private network phải cho phép kết nối theo cách dịch vụ hỗ trợ.

### 4.6. Cây quyết định chọn clustering policy

~~~mermaid
flowchart TD
    START[Redis workload] --> SEARCH{Cần RediSearch / vector search?}
    SEARCH -->|Có| SINGLE{Dataset nhỏ và cần nonclustered semantics?}
    SINGLE -->|Có, fits limits| NON[Evaluate Non-clustered]
    SINGLE -->|Không| ENTER[Enterprise Cluster]
    SEARCH -->|Không| LIB{Client hỗ trợ Redis Cluster API?}
    LIB -->|Có| OSS[Ưu tiên benchmark OSS Cluster]
    LIB -->|Không| MUTLI{Có cần unsharded + nhỏ?}
    MUTLI -->|Có| NON
    MUTLI -->|Không| ENTER
    OSS --> BENCH[Benchmark workload and command compatibility]
    ENTER --> BENCH
    NON --> BENCH
~~~

**Chọn policy trước provision.** Khi một cache đã tạo với OSS/Enterprise, chuyển policy có thể yêu cầu tạo instance mới và migrate dữ liệu/clients, kéo theo chi phí và thời gian đổi endpoint.

**Nguồn:** https://learn.microsoft.com/azure/redis/choose-clustering-policy.

## 5. Redis modules và phiên bản: không chọn muộn

Azure Managed Redis hỗ trợ các tính năng/modules bổ sung Redis theo **phiên bản, tier và clustering policy**. Nhiều module configuration là quyết định **tại thời điểm tạo cache**, không thể bật sau đó cho cùng instance một cách tùy ý.

### 5.1. Các trường hợp cần module

| Chức năng | Mục đích | Lưu ý lựa chọn |
|---|---|---|
| **RedisJSON** | Lưu/truy cập một phần JSON document | Kiểm tra dữ liệu JSON, version, memory overhead |
| **RediSearch** | Full-text, secondary indexes, có thể có vector search theo tính năng | **Không hỗ trợ OSS Cluster** theo chính sách hiện hành; chọn Enterprise/Non-clustered phù hợp |
| **RedisBloom** | Bloom/Cuckoo filters, giảm memory cho membership tests | False positives là đặc tính thiết kế; không thay authoritative data |
| **RedisTimeSeries** | Time-series ingestion/aggregation | Không thay hệ thống analytics dài hạn nếu cần retention/audit đặc thù |

Với **Flash Optimized**, modules được hỗ trợ **khác** các tier in-memory; theo hướng dẫn hiện hành, RedisJSON là module chủ yếu được hỗ trợ ở Flash, trong khi RediSearch/Bloom/TimeSeries không có. Luôn xem compatibility matrix đúng engine/version tại lúc tạo.

### 5.2. Redis 7.4 và Redis 8.x

Theo hướng dẫn dịch vụ tại thời điểm soạn, **Redis 7.4** là lựa chọn mặc định ổn định. **Redis 8.2** có thể xuất hiện ở trạng thái **preview** trên một số tier in-memory, tích hợp sẵn nhiều modules nhưng có các giới hạn như không hỗ trợ Flash, active geo-replication và một số custom access policies; không nhất thiết cho phép nâng cấp một instance hiện hữu từ 7.4 lên bản preview.

Đừng lấy version số lớn hơn làm tiêu chí duy nhất. Với production:

1. Chọn Redis version có hỗ trợ/SLA và command compatibility được chấp nhận.
2. Kiểm tra modules/cluster policy ở phiên bản đó.
3. Test sự khác biệt protocol RESP2/RESP3, client libraries và commands.
4. Đánh giá cơ chế upgrade/downgrade có hỗ trợ hay phải tạo instance mới.
5. Với preview, xem rõ **support policy và feature exclusions** trước khi quyết định.

### 5.3. Module có thể tăng chi phí bộ nhớ/CPU

Một secondary index trên hàng triệu JSON documents có thể tốn lượng RAM đáng kể ngoài kích thước dữ liệu gốc; tìm kiếm có thể gây CPU spikes. Đừng đánh giá size cache chỉ bằng tổng bytes JSON chưa index. Dự toán cần tính cả **index, per-key metadata, replication buffers, TTL bookkeeping và hot working set**.

**Trước khi tạo cache:** ghi rõ module set dự kiến và test query patterns. Nếu một tháng sau mới phát hiện cần RediSearch trong cache OSS Cluster, bạn có thể phải **tạo instance khác** và di chuyển ứng dụng.

## 6. Capacity planning: RAM, overhead, CPU, connections và headroom

Chọn SKU đúng cần **định lượng** thay vì “chọn 10 GB vì database có 10 GB”. Redis giữ dữ liệu theo cấu trúc riêng; keys, pointers, expiration metadata, indexes, replication và bộ nhớ dành cho hệ thống có overhead.

### 6.1. Tính raw dataset size

Giả sử catalog API cache:

- 2.000.000 products.
- Payload JSON trung bình **1.200 bytes/key**.
- Key string trung bình **40 bytes/key**.
- Metadata/overhead theo key và cấu trúc thực tế ước tính **100 bytes/key** để bắt đầu.

Raw estimate:

\[
2{,}000{,}000 \times (1{,}200 + 40 + 100)
=2{,}680{,}000{,}000\ \text{bytes}\approx 2.68\ \text{GB}.
\]

Đây là **ước tính sơ bộ**, không phải bộ nhớ Redis chính xác; serializer, Redis data types, index, memory allocator và key cardinality có thể thay đổi kết quả. Dùng `MEMORY USAGE` trên sample data nếu command được hỗ trợ và đo metrics của instance lab.

### 6.2. Reserved memory và replica

Azure Managed Redis dành khoảng **20% available memory** làm buffer phục vụ các tác vụ hệ thống theo mô hình dịch vụ; giá trị thực và cách metric hiển thị cần kiểm tra theo tier/SKU. **Không coi advertised capacity = 100% chỗ trống cho payload**.

Khi HA bật, một số raw memory metrics có thể cộng cả primary và replica khiến số liệu trông gần như gấp đôi. **Đừng nhân đôi dataset một lần nữa** chỉ vì raw metric gồm replica; hãy dùng **Used Memory Percentage** và SKU effective memory semantics để sizing. Đó là lý do cần nắm rõ metric definition, không chỉ đọc bảng “GB”.

### 6.3. Ví dụ sizing với headroom

Giả sử:

~~~text
Measured dataset after encoding/indexing:   18 GB
Expected one-year growth:                   30%
Target operational headroom:                25%
Additional workload assumptions:            validated via load test
~~~

Một ước lượng ban đầu về **effective usable memory**:

\[
18 \times 1.30 = 23.4\ \text{GB (dataset dự kiến)};
\]

\[
\text{Required effective capacity}
\approx\frac{23.4}{0.75}=31.2\ \text{GB}.
\]

Con số **31.2 GB effective usable** chưa phải tên một Azure SKU. Phải đối chiếu dung lượng usable sau reserve buffer/replicas theo tier, tiếp đó chọn một SKU có headroom thực và kết quả load test đạt. Nếu workload có indexes hoặc Flash hot/cold, cần thêm mô hình tương ứng.

### 6.4. Throughput không suy từ bộ nhớ

Hai workload cùng 10 GB có thể rất khác:

| Workload | Requests/giây | Đặc điểm | Nút nghẽn tiềm năng |
|---|---:|---|---|
| Feature flags cache | 1.000 | GET key nhỏ, nhiều hit | Mạng, connection/latency |
| Product lookup | 50.000 | GET/SET, cache-aside | Server Load, CPU, shards |
| Leaderboard | 10.000 | ZADD/ZRANGE, key distribution | Hot sorted set, CPU |
| Session store | 20.000 | GET/SETEX, TTL, many connections | Connection limits, memory, serialization |
| Full-text search | 2.000 queries | RediSearch index và filtering | Index memory, CPU, cluster policy |

Một Compute Optimized nhỏ có thể phù hợp workload throughput cao tốt hơn Memory Optimized lớn. Ngược lại, dataset lớn ít truy cập có thể ưu tiên Memory/Flash. **Phải benchmark với command mix và dữ liệu giống production**.

### 6.5. Connection limits và quản lý client

Mỗi SKU có số **client connections tối đa**. Con số này có thể làm bạn phải chọn SKU lớn hơn ngay cả khi Used Memory và CPU còn thấp.

Ví dụ hệ thống có:

~~~text
20 App Service instances × 150 Redis connections/instance = 3,000 connections
5 background workers × 200 connections/instance = 1,000 connections
Monitoring/maintenance/peak margin = 500 connections
Total plan ≈ 4,500 connections
~~~

Nhưng 150 connections/instance có thể đã **quá nhiều** cho cách dùng Redis phổ biến. Một số client (StackExchange.Redis, Lettuce) được khuyến nghị **tái sử dụng kết nối** thay vì tạo kết nối mới mỗi request. Đừng tăng SKU để chữa lỗi code mở/đóng kết nối liên tục.

### 6.6. Chọn headroom và điểm scale

Theo hướng dẫn hiện hành, nên quan sát **Used Memory Percentage** và cân nhắc scale khi mức sử dụng kéo dài trên **khoảng 75%**, đồng thời xem Server Load/CPU, connection count, evictions và p95/p99. Đây là **ngưỡng tham khảo**, không phải giới hạn cứng áp dụng cho mọi workload.

Bạn cần trả lời:

- Nếu 30% keys hết hạn cùng lúc, database có chịu nổi cache misses không?
- Nếu traffic gấp 3 trong 10 phút, throughput/cache hit ratio ra sao?
- Nếu một shard trở thành hot spot, scale memory có giải quyết được không?
- Nếu Redis failover, clients có reconnect và retry an toàn không?
- Nếu cần scale xuống, usage và constraints cho phép không?

## 7. TTL, expiration và eviction policy: cache sống bao lâu?

Trong Redis, **TTL (time to live)** xác định key hết hạn khi nào. **Eviction** là quá trình loại keys dưới áp lực bộ nhớ theo policy. Hai cơ chế không giống nhau.

### 7.1. TTL cho từng loại dữ liệu

| Dữ liệu | TTL ví dụ | Invalidation cần bổ sung? |
|---|---|---|
| Public product description | 5–30 phút | Khi product được sửa |
| Giá khuyến mãi | 15–60 giây nếu được phép stale | Khi marketing thay giá |
| Inventory availability | Rất ngắn hoặc không cache tùy consistency | Khi đơn hàng trừ tồn; source of truth phải xác nhận |
| User session | Theo chính sách đăng nhập và bảo mật | Logout/revoke; không dựa chỉ TTL |
| Feature flags | 30–120 giây | Nếu đổi policy khẩn cấp cần invalidate nhanh |
| Rate-limit counter | Theo cửa sổ thuật toán | Dùng atomic operations và expiry |

Các TTL trên **chỉ minh họa**, phải xác định từ SLA nghiệp vụ. **Không cache giá/stock có thể gây giao dịch sai** nếu hệ thống không chấp nhận staleness. Đặt TTL ngắn không loại hoàn toàn race condition; checkout phải đọc/khóa dữ liệu tồn kho từ nguồn có transaction.

### 7.2. Expiration vs eviction

~~~text
Key "catalog:product:123" TTL 300s:
    → hết 300s thì key hết hạn, bất kể Redis còn RAM hay không.

Key chưa hết TTL nhưng Redis gần đầy:
    → eviction policy có thể loại key sớm nếu thuộc phạm vi được chọn.
~~~

Ứng dụng phải coi **cache miss là bình thường**, kể cả khi TTL chưa hết. Redis HA/failover, eviction, manual flush hoặc thay instance đều có thể làm key không còn.

### 7.3. Chọn eviction policy

Azure Managed Redis thường có mặc định **`volatile-lru`**: khi thiếu bộ nhớ, ưu tiên loại **keys có TTL** theo hành vi LRU. Nếu phần lớn keys không có TTL, Redis có thể **không còn key đủ điều kiện eviction** và writes bắt đầu thất bại khi cạn capacity.

| Policy | Mô tả | Use case |
|---|---|---|
| `volatile-lru` | LRU trong những keys **có TTL** | Cache kết hợp keys không được tự loại với keys hết hạn |
| `allkeys-lru` | LRU trên mọi keys | Cache thuần có thể dựng lại, keys đều có thể evict |
| `volatile-ttl` | Ưu tiên keys có TTL sắp hết | Khi TTL là tiêu chí quan trọng |
| `noeviction` | Không tự evict khi đầy; writes có thể lỗi | Trường hợp không chấp nhận mất keys, cần alert/scale rất sớm |

**Không chọn `allkeys-lru` cho data/coordination keys mà ứng dụng coi là không thể mất** nếu chưa có recovery protocol. Còn với cache-aside thuần, allkeys-lru có thể hợp lý hơn khi các keys đều có thể rebuild.

### 7.4. Tránh đồng loạt hết TTL

Nếu 1 triệu keys được tạo lúc 10:00 với TTL 300 giây, chúng có thể hết hạn cùng lúc lúc 10:05 khiến backend SQL nhận một **cache avalanche**. Một cách giảm rủi ro là random jitter:

~~~text
baseTTL = 300 seconds
jitter  = random(0..60)
TTL     = baseTTL + jitter
~~~

Trong production, chỉ thêm jitter khi freshness SLA cho phép. Với keys mang authorization/session, không tùy tiện kéo dài hạn hiệu lực của credential; TTL liên quan security phải được tính từ thời điểm cấp/hết hạn thật.

### 7.5. Hot key và big key

- **Hot key**: một key nhận traffic vượt trội, làm một shard/CPU thành bottleneck dù cache tổng thể chưa đầy.
- **Big key**: một value/hash/list/set quá lớn, khiến serialize/network/Redis command latency cao.
- **High cardinality**: hàng triệu keys nhỏ làm per-key overhead trở nên đáng kể.

Điều tra key access distribution, value sizes và command complexity; hạn chế dùng `KEYS *` trên production vì có thể tốn CPU/latency. Dùng scan/tính năng monitoring được hỗ trợ, giới hạn quyền truy xuất và tránh log values nhạy cảm.

### 7.6. Thứ tự lựa chọn TTL/eviction

1. Định nghĩa **staleness budget** theo nghiệp vụ.
2. Chọn key naming và owner.
3. Quyết định TTL, invalidation trên write và khả năng cache miss.
4. Chọn eviction policy phù hợp mức độ “có thể mất” của data.
5. Chạy load test với working set gần đầy, đo evictions/misses/DB load.
6. Thiết lập alert/scale trước khi memory pressure tạo retry storm.

Nếu dùng **active geo-replication**, có các hạn chế về thay eviction policy sau khi đã ghép group; phải chốt sớm.

## 8. Cache patterns: thiết kế đúng trước khi scale Redis

### 8.1. Cache-aside (lazy loading)

Phổ biến nhất với API đọc dữ liệu:

~~~mermaid
sequenceDiagram
    participant API as Catalog API
    participant R as Managed Redis
    participant DB as Azure SQL
    API->>R: GET catalog:v3:product:123
    alt Cache hit
      R-->>API: cached product JSON
    else Cache miss
      R-->>API: null
      API->>DB: SELECT product 123
      DB-->>API: authoritative row
      API->>R: SET key value EX 300
    end
~~~

Ưu điểm: không cần nạp trước mọi dữ liệu. Nhược điểm: miss chậm, race khi SQL update gần lúc cache set, có thể xảy ra **cache stampede** nếu hàng nghìn requests cùng miss.

### 8.2. Invalidate sau khi ghi

~~~text
1. Backend validates request and updates SQL in a transaction.
2. SQL COMMIT succeeds.
3. Backend deletes cache key or bumps a versioned key.
4. Next GET misses cache, reads new authoritative data, repopulates Redis.
~~~

Không xóa cache **trước** SQL commit mà không cân nhắc race: request khác có thể read old SQL row rồi repopulate cache ngay trước commit. Cần xử lý trường hợp invalidation thất bại (outbox/change feed/retry) nếu dữ liệu cần freshness chặt.

Đối với payment/inventory có tính nhất quán cao, **cache không được là nguồn quyết định cuối**; bản ghi giao dịch cần được xác thực trong database/transaction dù GET trước đó dùng Redis.

### 8.3. Cache stampede

Nếu một hot key hết hạn và 5.000 requests cùng đến, cả 5.000 có thể gọi SQL:

~~~text
Redis: key missing
   ├─ Request 1 → SQL
   ├─ Request 2 → SQL
   ├─ ...
   └─ Request 5000 → SQL overloaded
~~~

Các kỹ thuật giảm:

- TTL jitter và pre-warming những hot keys.
- **Request coalescing/single-flight** trong mỗi app instance.
- Bounded lock có **timeout và fencing** nếu dùng phân tán; không phụ thuộc lock Redis như cơ chế correctness duy nhất.
- Stale-while-revalidate nếu nghiệp vụ cho phép dữ liệu cũ trong một cửa sổ được kiểm soát.
- Rate limiting/circuit breaker đến database khi cache miss storm.
- Background refresh, giới hạn đồng thời và fallback an toàn.

### 8.4. Cache penetration và negative caching

Nếu user/bot gọi hàng triệu product IDs không tồn tại, mọi cache miss có thể xuống SQL. **Negative caching** giữ “không tồn tại” ngắn hạn cho ID hợp lệ nhưng vắng mặt:

~~~text
GET product:nonexistent
→ SQL: not found
→ Cache sentinel for 10–30s if appropriate
~~~

Phải phân biệt **not found** và **database error**. Không cache lỗi 500/timeout thành “không tồn tại” hàng giờ. Validate ID/rate limit trước khi truy vấn, bảo đảm negative cache không vô tình làm 404 kéo dài sau khi product vừa được tạo.

### 8.5. Cần ứng dụng có thể chạy khi Redis unavailable

Nếu Redis lỗi, một API catalog có thể chuyển sang SQL với **bounded concurrency**/rate limiting. Nhưng một session store dùng Redis thì mất cache có thể làm user logout, không có fallback “đọc SQL” nếu session chỉ lưu trong Redis. Phải định nghĩa availability degradation **cho từng use case**, không phải một catch-all bỏ qua mọi Redis exception.

**Anti-pattern:** cứ thấy Redis timeout thì mỗi API instance lập tức gửi 100% tải xuống SQL, làm SQL ngã theo. Cần circuit breaker, timeouts ngắn hợp lý và downstream capacity budgets.

## 9. Bảo mật Azure Managed Redis: mạng, TLS và Microsoft Entra ID

Redis thường giữ dữ liệu theo keys ngắn gọn nên các nhóm dễ xem nhẹ bảo mật. Nhưng một cache bị truy cập trái phép có thể lộ sessions, PII, access flags, API responses hoặc cho phép kẻ tấn công tạo tải lớn lên database bằng cách xóa cache. **Mạng riêng, xác thực, phân quyền Redis và bảo vệ payload là các lớp riêng biệt**.

### 9.1. Những câu hỏi bảo mật phải trả lời

| Câu hỏi | Cơ chế |
|---|---|
| Runtime nào được kết nối tới Redis? | VNet/Private Endpoint, DNS, public access policy |
| Kết nối có mã hóa và xác minh đúng máy chủ không? | TLS và certificate validation |
| Ứng dụng là danh tính nào? | Microsoft Entra ID/managed identity, hoặc access key khi được phê duyệt |
| Danh tính được thao tác những keys/commands nào? | Redis data access policies/ACLs theo tính năng |
| Ai được tạo/xóa/cache/đổi cấu hình? | Azure RBAC control plane và pipeline governance |
| Cache có dữ liệu nhạy cảm không? | Data classification, application encryption, TTL/retention |

### 9.2. Endpoint và port

Azure Managed Redis thường có hostname dạng:

~~~text
<cache-name>.<azure-region>.redis.azure.net
~~~

**TLS endpoint thông thường dùng port `10000`**. Với **OSS Cluster**, client khám phá shards và các kết nối tiếp theo có thể dùng **ports 85xx**, phụ thuộc cluster topology. Cần firewall/Private Endpoint routing đúng; không suy rằng mở port 10000 là đủ cho mọi Redis Cluster client nếu shard connections bị chặn.

**Không copy port `6380`** trong tutorial Azure Cache for Redis Basic/Standard/Premium cũ vào client Azure Managed Redis. Lấy hostname/port từ chính resource Azure Managed Redis hiện tại và hướng dẫn client/library tương ứng.

### 9.3. Private Endpoint và DNS

~~~mermaid
flowchart LR
    APP[App Service/AKS/VM] --> NET[Outbound VNet route]
    NET --> DNS[Azure Private DNS / resolver]
    DNS --> IP[Private Endpoint IP]
    IP --> AMR[(Azure Managed Redis)]
    APP -. TLS + Entra token .-> AMR
    PUB[Public access] -. Disabled by policy .-> AMR
~~~

Một Private Endpoint đưa một NIC/private IP vào subnet của bạn để kết nối dịch vụ. Tên client vẫn dùng FQDN chuẩn `<name>.<region>.redis.azure.net`; vùng Private DNS liên quan tên `privatelink.redis.azure.net` theo mô hình dịch vụ. **Không kết nối thẳng bằng private IP hoặc `*.privatelink...`** để tránh lỗi TLS hostname/certificate và sự phụ thuộc IP.

**Lưu ý triển khai:** Private Endpoint **không tự đảm bảo** ứng dụng App Service có **outbound VNet Integration**. App Service private endpoint inbound là chức năng khác. AKS cần DNS/Pod networking, Container Apps cần VNet/network configuration và on-premises cần VPN/ExpressRoute + DNS forwarding.

### 9.4. Public network access là quyết định riêng

Azure Managed Redis có setting **`publicNetworkAccess`** tách biệt với Private Endpoint trong các API versions mới. Với mục tiêu private-only, cấu hình **disable public access** cùng Private Endpoint/DNS đúng. Một số resource cũ/tài liệu có hành vi mặc định khác nhau khi thêm/xóa Private Endpoint; **không suy rằng “tạo Private Endpoint là auto đóng public”**.

Trước khi đổi public network access:

1. Inventory mọi consumers: API, workers, batch jobs, CI, monitoring, admin tools.
2. Tạo Private Endpoint, phê duyệt connection và cấu hình DNS.
3. Test từ **runtime thật**: DNS → TCP → TLS → Entra AUTH → GET/SET.
4. Xác định reconnect behavior của clients sau network change.
5. Disable public access theo change approval; test positive từ private và negative từ public.

Không mở public access vô thời hạn chỉ để Redis Insight từ laptop quản trị kết nối dễ hơn; nếu cần vận hành, dùng một đường VPN/Jump Host/private runner được phê duyệt.

### 9.5. Microsoft Entra ID theo mặc định

Azure Managed Redis ưu tiên **Microsoft Entra authentication**. Khi tạo instance mới theo hướng dẫn hiện hành, Entra authentication được bật mặc định và **access key authentication có thể được tắt mặc định** vì lý do bảo mật. Không viết ứng dụng mới với giả định sẵn có một static Redis password/access key.

Một luồng Entra authentication cơ bản:

~~~mermaid
sequenceDiagram
    participant APP as App with Managed Identity
    participant ENTRA as Microsoft Entra ID
    participant REDIS as Azure Managed Redis
    APP->>ENTRA: Acquire token for redis.azure.com scope
    ENTRA-->>APP: Access token with expiration
    APP->>REDIS: TLS connection to endpoint:10000
    APP->>REDIS: AUTH <principal-object-id> <access-token>
    REDIS-->>APP: OK if principal allowed
    Note over APP,REDIS: Refresh token and re-AUTH before expiry
~~~

Theo cơ chế Entra Redis:

- **Username** thường là **object ID** của managed identity/service principal.
- **Password** là **short-lived Entra access token**, không phải account key.
- Token scope thường là `https://redis.azure.com/.default`.
- Principal phải được **thêm vào Redis users/data access configuration**, không phải chỉ cấp Azure Contributor.
- Client cần **refresh token và re-authenticate trước khi hết hạn**, nếu không kết nối lâu dài có thể đứt.
- Microsoft Entra **groups không được hỗ trợ như Redis users** theo hướng dẫn hiện hành; phải cấu hình đúng supported principal types.

**Important:** Azure RBAC Contributor trên cache resource là quyền **control plane**. Nó **không tự tạo** quyền Redis data-plane `GET/SET` cho managed identity. Xác thực Redis phải được cấu hình riêng; đánh giá custom data access policies và giới hạn preview khi cần.

### 9.6. Access keys và rotation

Khi buộc phải dùng access keys để tương thích client:

- Lưu secret trong Azure Key Vault hoặc secret store tương đương.
- Không đưa key vào Git, Docker image, Terraform state plaintext, query string hay log.
- Hạn chế người có quyền xem/regenerate keys.
- Lập kế hoạch rotate có dual-credential strategy nếu dịch vụ hỗ trợ.
- Chuyển dần sang Entra token và tắt key auth khi mọi clients đã sẵn sàng.

**Đổi key-auth mode có thể làm các kết nối bị ngắt**, kể cả những clients đang dùng Entra theo behavior dịch vụ; phải có reconnect/re-auth logic và change window, không bấm tắt ở production mà chưa kiểm chứng.

### 9.7. Data access policies và phân loại dữ liệu

Khi nhiều ứng dụng dùng chung cache, cần phân tách:

~~~text
Principal orders-api:
    read/write keys orders-cache:*

Principal catalog-api:
    read/write keys catalog:*

Principal monitoring:
    read-only metrics/approved commands
~~~

Đây là **policy intent**, không phải cú pháp ACL được bảo đảm hợp lệ. Khả năng custom data access permissions có thể ở preview hoặc không được hỗ trợ trên một số phiên bản Redis; cần kiểm tra capability trước khi thiết kế bảo mật dựa vào nó.

**Một Redis instance không là ranh giới tenant isolation tuyệt đối** nếu nhiều tenants share memory, CPU, eviction và quyền rộng. Dùng key prefixes không thay ACL/identity. Với dữ liệu nhạy cảm, cân nhắc cache instance riêng hoặc encryption của ứng dụng, vì encryption-at-rest cho persistence disks **không có nghĩa payload trong RAM được mã hóa bằng khóa của ứng dụng**.

### 9.8. TLS và certificate validation

Kết nối Redis cần xác minh certificate chain/hostname, không chỉ bật flag TLS một cách hình thức. Đừng kết nối bằng private IP, bỏ certificate validation hoặc hạ xuống non-TLS để chữa lỗi DNS. Cập nhật trust store/runtime và Redis client khi certificate/TLS requirements thay đổi.

**Nguồn:** https://learn.microsoft.com/azure/redis/secure-azure-managed-redis; https://learn.microsoft.com/azure/redis/entra-for-authentication; https://learn.microsoft.com/azure/redis/private-link.

## 10. High availability, persistence, backup và geo-replication

“Redis có replica” không có nghĩa “tất cả dữ liệu vĩnh viễn an toàn”. Azure Managed Redis có nhiều tính năng reliability, mỗi tính năng bảo vệ một loại lỗi khác nhau. Phải chọn theo **business RPO/RTO và mức mất cache có thể chấp nhận**, thay vì bật tất cả chỉ vì thấy công tắc.

### 10.1. High Availability (HA)

HA phân bổ **primary và replica shards** trên nhiều nodes để có thể failover khi node/shard lỗi hoặc bảo trì. Với production, **bật HA**; hướng dẫn hiện hành nêu HA là điều kiện để có coverage dưới SLA của Managed Redis. Instance không HA có nguy cơ downtime/data loss cao hơn, chỉ nên dùng cho **dev/test disposable**.

Khi cache đã bật HA, không mặc định có thể tắt lại; lựa chọn này có hạn chế chiều thay đổi. Tính năng HA không tạo backup/restore point độc lập.

### 10.2. Availability zones

Ở những region hỗ trợ Availability Zones, cache có HA thường được triển khai phân tán zones theo mô hình dịch vụ, giúp chịu lỗi zone. Nhưng:

- Zone redundancy không tự chống **region-wide outage**.
- Dữ liệu đang replicate có thể có **lag** trước failover.
- Client phải reconnect và retry safely sau topology change.
- Cần kiểm tra tính khả dụng theo region/SKU và tính năng tự động chọn zone.

### 10.3. Data persistence: RDB và AOF

Theo tính năng được hỗ trợ:

- **RDB persistence:** snapshot định kỳ trạng thái Redis vào disk của dịch vụ, thuận tiện khôi phục sau một số loại lỗi; có thể mất changes kể từ snapshot cuối.
- **AOF persistence:** ghi log write operations và đồng bộ theo cơ chế dịch vụ, có thể thu hẹp cửa sổ mất dữ liệu so với RDB định kỳ nhưng không đảm bảo database transaction semantics.

**Persistence không phải backup.** Những thay đổi xấu/khóa bị xóa nhầm cũng có thể được persist. Các file persistence nội bộ thường dành để dịch vụ **khôi phục chính cache đó**, không phải artifact người dùng lấy ra để restore vào cache khác. Muốn có bản sao có thể import, hãy dùng **Export/Import** hoặc backup ở tầng dữ liệu/ứng dụng.

Data persistence yêu cầu HA theo hướng dẫn dịch vụ và **không kết hợp với active geo-replication** trên cùng cache. Flash Optimized có các điều kiện riêng, có thể preview. Không thiết kế cả AOF + geo-replication rồi giả định Portal cho bật đồng thời.

### 10.4. Active geo-replication

Geo-replication chủ động có thể đồng bộ/cache giữa các Azure regions theo mô hình eventual consistency. Đây là giải pháp cho một số bài toán multi-region/DR nhưng cần lưu ý:

- Không phải **synchronous strong consistency** và không có SLA đồng bộ tức thời; conflict/lag phải được ứng dụng chấp nhận.
- Các instances trong group phải có cấu hình tương thích (SKU/capacity, modules, cluster policy, eviction/TLS theo yêu cầu).
- **Flash Optimized không hỗ trợ** tính năng này theo tài liệu hiện hành.
- Một số SKU nhỏ như **Balanced B0/B1** không được hỗ trợ.
- Không kết hợp với persistence.
- Việc thêm/xóa member khỏi geo-replication group có thể ảnh hưởng dữ liệu hiện có; cần runbook migration và test.

Nếu cache chỉ giữ product descriptions có thể rebuild, đôi khi **cache độc lập theo region** và pre-warm từ authoritative DB dễ vận hành hơn geo-replication. Nếu Redis chứa session state cần share multi-region, đánh giá privacy/TTL/conflict/latency rõ trước.

### 10.5. Export/Import và backup vận hành

Azure Managed Redis có các cơ chế **Export/Import dữ liệu** theo hỗ trợ, thường tương tác với Azure Blob Storage. Dùng chúng khi cần snapshot cho migration/testing/khôi phục, nhưng cần xác minh:

1. Format/version compatibility và modules.
2. Dung lượng dữ liệu, thời gian export/import, network/storage permissions.
3. Encryption/retention và nơi lưu artifact, data classification.
4. Có automation schedule riêng hay không; đừng mặc định Azure tự tạo bản backup export hằng đêm.
5. Import vào instance đang chứa data có thể gây overwrite/side effects theo semantics.
6. Recovery objective: backup RDB có thể mất dữ liệu giữa các lần chụp.

**Redis cache vẫn nên có source of truth khác** cho dữ liệu không thể mất. Nếu cache mất toàn bộ, hệ thống phải có chiến lược rebuild hoặc chấp nhận tác động được ghi trong SLO.

### 10.6. Chọn tính năng theo failure mode

| Failure mode | HA | Persistence | Geo-replication | Rebuild/source of truth |
|---|---|---|---|---|
| Một node mất | Bảo vệ tốt hơn, có failover | Phụ trợ theo cấu hình | Không bắt buộc | Fallback khi cache miss |
| Region mất | Không đủ | Không đủ | Có thể hỗ trợ kiến trúc multi-region | DB/region DR vẫn quan trọng |
| Xóa nhầm toàn bộ keys | Không | Có thể lưu trạng thái xóa | Có thể lan truyền xóa | **Backup độc lập + source of truth** |
| Cache instance bị thay/xóa | Không đủ | Không là bản backup portable | Cần runbook group | Export/import hoặc rebuild |
| Ứng dụng ghi dữ liệu sai | Không | Persist dữ liệu sai | Replicate dữ liệu sai | Business validation và sửa source |

**Nguồn:** https://learn.microsoft.com/azure/redis/plan-reliability-and-durability; https://learn.microsoft.com/azure/redis/how-to-persistence.

## 11. Chọn cách kết nối và topology trong Azure

### 11.1. App Service → Redis Private Endpoint

~~~text
Client Browser
  → App Service (HTTP ingress)
      → App Service VNet Integration (outbound)
          → Private DNS resolution
              → Azure Managed Redis Private Endpoint
                  → TLS port 10000 + Entra authentication
~~~

**Private Endpoint inbound cho App Service** không tự cấp App Service quyền outbound vào Redis Private Endpoint. Phải kiểm tra App Service plan/VNet Integration, DNS và route.

### 11.2. AKS → Redis OSS Cluster

Ở AKS, Redis client trong Pod cần:

- Đúng **Kubernetes service account/Workload Identity** nếu dùng Entra token.
- Cluster DNS/CoreDNS resolve Redis FQDN về private IP.
- NSG/UDR/NetworkPolicy cho phép Redis port 10000 và các shard ports do client khám phá khi dùng OSS cluster.
- Client hỗ trợ Redis Cluster API và dynamic topology/`MOVED` redirects.
- Timeouts/reconnect/circuit breakers và key hash-slot compatibility.

Một debug Pod có thể truy cập Redis trong khi production Pod bị NetworkPolicy chặn. Kiểm tra từ **đúng Pod namespace và service account**, không chỉ từ một VM quản trị.

### 11.3. Azure Container Apps/Functions/VM và on-premises

Mỗi runtime có networking khác nhau:

| Runtime | Điều phải kiểm tra |
|---|---|
| Container Apps | VNet environment/egress, private DNS, identity/token, scale concurrency |
| Azure Functions | Hosting plan hỗ trợ outbound VNet, cold-start, connection reuse, token refresh |
| VM | VNet/NSG/UDR, DNS, managed identity và trust store |
| On-premises | VPN/ExpressRoute route + conditional DNS forwarding + firewall |
| Hosted CI runner | Không tự nằm trong private VNet; dùng self-hosted/private runner khi test private data-plane |

### 11.4. Nhiều private endpoints và hub-spoke DNS

Nếu nhiều applications ở VNet khác nhau truy cập cùng Redis:

- Xác định owner của **Private DNS zone**/links và resolvers.
- Kiểm tra route tới private IP từ từng spoke/VPN network.
- Không tạo A records xung đột khiến client ở spoke A resolve IP không route được ở spoke B.
- Với custom DNS, cấu hình conditional forwarding tới resolver có thể truy vấn Private DNS zone.
- Đặt Redis gần workloads để giảm network latency/egress và đánh giá multi-region requirements.

**Không bỏ TLS hostname verification** hoặc đặt Redis client trỏ thẳng vào Private Endpoint IP chỉ để tránh sửa DNS.

## 12. Lab có kiểm soát: tạo và kiểm tra Azure Managed Redis

Lab dưới đây **không được chạy trong lúc viết bài**. Nếu người học thực hành, cần Azure subscription/resource group **được phép**, quyền tạo Azure Managed Redis, budget cảnh báo và môi trường test riêng. Azure Managed Redis là tài nguyên tính phí, có thể có chi phí đáng kể dù chỉ tạo để học. Không dùng cache production chung với dữ liệu thật.

### 12.1. Kịch bản lab

~~~text
Goal: Cache-aside for product catalog
Azure resource: Azure Managed Redis
Region: gần App Service/SQL test
Tier: Balanced, initial supported size
Clustering policy: Enterprise (for simple standalone Python client lab)
Redis version: generally available supported version, e.g. Redis 7.4
High Availability: enabled if testing a production-like setup
Auth: Microsoft Entra ID
Network: private endpoint if runtime VNet is available
Data: synthetic product data only
~~~

**Tại sao lab chọn Enterprise policy?** Để ví dụ dùng client Redis đơn giản (`redis.Redis`) và không phải cấu hình cluster discovery. **Đây không phải khuyến nghị mọi production app chọn Enterprise**; nếu production cần throughput tối đa và client hỗ trợ Redis Cluster, hãy benchmark OSS policy.

### 12.2. Tạo instance bằng Azure Portal

1. Đăng nhập Azure Portal vào **subscription lab**.
2. Chọn **Create a resource → Azure Managed Redis**.
3. Chọn **Resource group**, tên cache hợp lệ, region có dịch vụ, tier và kích thước đủ cho test.
4. Trong **Networking**, chọn mô hình public/private đúng khả năng kết nối từ client lab. Ưu tiên **Private Endpoint** nếu có VM/AKS/App Service runtime trong VNet.
5. Trong **Advanced**, chọn Redis version ổn định, **clustering policy phù hợp**, module cần thiết (nếu có), HA và persistence nếu cần test riêng.
6. Xác nhận **Entra authentication**, không bật access key auth chỉ để tránh cấu hình identity.
7. Xem **Review + Create**: kiểm tra giá, SKU preview, region, networking, policy và các quyết định khó đổi sau tạo.
8. Tạo cache và theo dõi provisioning; ghi lại cache **hostname, port, tier, policy và resource ID**.
9. Trong cache **Authentication/Data access configuration**, cấp quyền Redis user cho managed identity hoặc developer principal được phép truy cập dữ liệu test.

Các nhãn trên Portal có thể thay đổi; nguyên tắc không đổi là phải ghi rõ **tier, capacity, clustering, modules, network, auth và HA** trước provision.

### 12.3. Azure CLI để kiểm kê, không tự thay đổi tài nguyên

CLI có nhóm lệnh `az redisenterprise`, được cung cấp qua extension tương ứng; resource type có thể vẫn là `Microsoft.Cache/redisEnterprise` dù tên sản phẩm được công bố là **Azure Managed Redis**.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-redis-lab"
CACHE_NAME="<lab-managed-redis-name>"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name}" -o table

az redisenterprise list \
  --resource-group "$RG" \
  --output table

az redisenterprise show \
  --resource-group "$RG" \
  --name "$CACHE_NAME" \
  --output json
~~~

Các giá trị `<...>` phải thay bằng tài nguyên lab thật. Với Azure CLI phiên bản mới, kiểm tra:

~~~bash
az version
az redisenterprise --help
az redisenterprise show --help
az redisenterprise database --help
~~~

**Không chạy `az redisenterprise create` có cú pháp chưa xác minh hoặc trên tên cache đã tồn tại.** Một số CLI/API có thể **overwrite/recreate** resource theo cách gây downtime. Nếu nhóm platform dùng Bicep/Terraform, tạo resource qua approved pipeline chứ không tạo riêng qua Portal mà không ghi nhận IaC.

### 12.4. Kiểm tra DNS và TCP từ client runtime

Cache hostname thường dạng:

~~~text
<cache-name>.<region>.redis.azure.net
~~~

Từ **VM/Pod/App Service runtime** đã được phép:

~~~bash
nslookup "<cache-name>.<region>.redis.azure.net"

nc -vz "<cache-name>.<region>.redis.azure.net" 10000
~~~

Nếu dùng OSS Cluster, cần kiểm tra thêm các shard ports sau cluster discovery. `nc -vz` chỉ xác nhận đường TCP, **không chứng minh TLS hoặc Redis AUTH hợp lệ**.

Với Private Endpoint, xác minh DNS cuối trỏ private IP. Nếu DNS trả public IP trong khi public network access đã tắt, sửa Private DNS/VNet integration/forwarding trước khi thay authentication.

### 12.5. Cài Python SDK/client cho bài lab

Trên môi trường Python 3 được phép kết nối Redis:

~~~bash
python -m pip install redis azure-identity
~~~

Đặt environment variables, **không** đưa access token vào source:

~~~bash
export REDIS_HOST="<cache-name>.<region>.redis.azure.net"
export REDIS_PORT="10000"
export REDIS_PRINCIPAL_OBJECT_ID="<entra-principal-object-id>"
~~~

`REDIS_PRINCIPAL_OBJECT_ID` là **object ID** của identity đã được thêm vào Redis authentication configuration, không mặc định là application (client) ID. Một user/service principal có thể có nhiều ID khác nhau; dùng đúng object ID được Redis chấp nhận.

### 12.6. Python example: Entra auth và Redis commands

Đây là **smoke test ngắn** cho **Enterprise Cluster/Non-clustered** client model. Nó lấy một Entra token tại thời điểm chạy, nên **không thích hợp giữ kết nối hàng giờ** nếu chưa bổ sung refresh/re-auth logic.

~~~python
import json
import os

from azure.identity import DefaultAzureCredential
import redis

redis_host = os.environ["REDIS_HOST"]
redis_port = int(os.environ.get("REDIS_PORT", "10000"))
principal_oid = os.environ["REDIS_PRINCIPAL_OBJECT_ID"]

# DefaultAzureCredential uses developer auth locally or workload identity
# in an approved Azure runtime. Do not log the token.
credential = DefaultAzureCredential()
token = credential.get_token("https://redis.azure.com/.default").token

client = redis.Redis(
    host=redis_host,
    port=redis_port,
    username=principal_oid,
    password=token,
    ssl=True,
    ssl_cert_reqs="required",
    socket_connect_timeout=3,
    socket_timeout=3,
    decode_responses=True,
)

key = "lab:catalog:v1:product:123"
payload = json.dumps({
    "id": 123,
    "name": "Demo Headphones",
    "price": 1200000,
})

try:
    print("PING:", client.ping())
    client.set(name=key, value=payload, ex=60)
    print("GET:", client.get(key))
    print("TTL:", client.ttl(key))
    client.delete(key)  # Only remove the synthetic lab key.
finally:
    client.close()
~~~

**Trước khi chạy:** chỉ thực hành khi cache có tên đúng, network path hoạt động và principal được cấp quyền Redis data-plane. Nếu Entra token hợp lệ nhưng principal không được thêm vào Redis users, Redis có thể trả **NOAUTH/WRONGPASS**. Đây không nhất thiết là lỗi firewall.

### 12.7. Production: token refresh phải tự động

Trong production, một app Java/.NET/Python/Node.js có thể giữ Redis client hàng ngày. Entra access token hết hạn, vì vậy:

- Dùng authentication helper/client library được khuyến nghị cho Azure Managed Redis.
- Refresh token **trước expiry** (hướng dẫn Microsoft gợi ý dư khoảng vài phút) và gửi **AUTH** mới trên connections phù hợp.
- Với RESP2/RESP3 và Pub/Sub, kiểm tra các kết nối chuyên dụng có được re-auth hay không.
- Không tạo client mới mỗi HTTP request; tái sử dụng connection/pool phù hợp.
- Xử lý reconnect sau Redis failover, DNS/network changes, token refresh failures.
- Không log access token hoặc password vào Redis URL, exception hay diagnostics.

Ví dụ Python ở phần 12.6 **chỉ phục vụ lab ngắn**. Không copy nó nguyên xi vào một worker chạy liên tục rồi giả định token sẽ tự refresh sau 60 phút.

### 12.8. Với OSS Cluster phải dùng client hỗ trợ cluster

Ví dụ khởi tạo **topology khác** (mang tính minh họa, không chạy song song với ví dụ standalone trong cùng cache):

~~~python
from redis.cluster import RedisCluster

# credential and token reused from earlier lab initialization
cluster_client = RedisCluster(
    host=redis_host,
    port=redis_port,
    username=principal_oid,
    password=token,
    ssl=True,
    ssl_cert_reqs="required",
    decode_responses=True,
)

try:
    print(cluster_client.get("lab:catalog:v1:product:123"))
finally:
    cluster_client.close()
~~~

Với RedisCluster, firewall/DNS/network phải cho phép cluster discovery và shard connections. Các commands cùng nhiều keys phải có hash-slot compatibility; không dùng client standalone và gọi lỗi Redis là “cache hỏng” khi service đang chạy OSS Cluster đúng thiết kế.

### 12.9. Tiêu chí pass cho lab

| Điều kiện | Bằng chứng |
|---|---|
| Đúng Azure resource | Subscription/RG/name/tier/policy/region |
| Networking | Redis FQDN resolve đúng private IP hoặc public path được phê duyệt |
| TLS | Client xác minh certificate thành công |
| Entra ID | PING/SET/GET qua principal object ID đã đăng ký |
| TTL | `TTL` có giá trị và key biến mất sau expiry |
| Security | Một principal không được cấp quyền bị từ chối |
| Cost | Có tag/owner/budget và cleanup plan |
| Operational | Metrics/alerts được cấu hình và read-back |

**Không chạy `FLUSHALL`, `FLUSHDB` hoặc các lệnh xóa rộng** trên một cache dùng chung để kiểm thử TTL. Dùng prefix `lab:` và xóa đúng key thử nghiệm.

## 13. Benchmark để chứng minh lựa chọn tier/policy

Các thông số **“GB RAM”, “vCPU ratio” hoặc “giá/giờ”** không đủ để chốt tier. Trước production, phải benchmark bằng workload gần thực tế.

### 13.1. Tối thiểu phải đo

- Dataset size, số keys, kích thước value, TTL distribution, hot/cold access.
- Command mix: GET/SET/EXPIRE/HGET/HSET/ZADD/RedisJSON/Search.
- Commands/giây mục tiêu, peak và burst.
- Concurrency, connections, pipelining, batch/payload sizes.
- Cache hit ratio, p50/p95/p99 application latency.
- Redis Server Load/CPU, Used Memory Percentage, eviction rate, connected clients.
- Network latency giữa app và cache region, Private Link/DNS overhead.
- Failover/reconnect, token refresh, cache miss surge và backend degradation.

### 13.2. Ma trận thử nghiệm minh họa

| Test | Dataset | Load | Tiêu chí pass ví dụ |
|---|---|---|---|
| Baseline | 10% expected working set | 1× traffic | p95 API đạt mục tiêu; no errors |
| Production-size | 100% expected working set | 1× traffic | Redis memory/CPU còn headroom |
| Burst | Production-size | 3× trong 10 phút | Không timeout kéo dài/DB overload |
| Hot-key | Một key chiếm 30% reads | 2× | Hot shard/CPU còn trong ngưỡng |
| Cold miss | Evict/invalidate selected test keys | 1× | DB fallback có limit, không stampede |
| Failover | HA enabled | 1× | Clients reconnect, business SLO theo runbook |
| Token expiry | >60 phút với Entra helper | 1× | Tự refresh/re-auth không gián đoạn dài |
| Flash hot/cold | Dataset vượt RAM share | 1×/2× | p99 chịu được cold read latency |

Các con số là **test design**, không phải SLA do Azure cam kết. Nếu production traffic biến thiên, cần chọn peak hợp lý từ đo đạc thật.

### 13.3. Benchmark công cụ Redis

`redis-benchmark` hoặc load generator riêng có thể đo throughput synthetic commands. Nhưng benchmark command đơn giản trên một VM không đại diện cho **ứng dụng thực có JSON serialization, database fallback, Entra token, network latency, request composition và Redis Cluster sharding**.

Không chạy benchmark tải cực cao trên cache production không được phép; có thể gây CPU spike, eviction và ảnh hưởng khách hàng thật. Benchmark trên **instance lab riêng** có tier/size/data pattern tương đồng.

### 13.4. Khi benchmark không đạt

| Dấu hiệu | Ưu tiên điều tra |
|---|---|
| CPU/Server Load cao, memory thấp | Compute tier, hot keys, O(N) commands, cluster topology |
| Used Memory cao, CPU thấp | Size/tier memory, TTL/eviction, big keys/overhead |
| Nhiều connection errors | Client reuse/pool, token re-auth, connection cap, DNS/TLS |
| Cache hit ratio thấp | Key design, invalidation/TTL, working set mismatch |
| p99 xấu trên Flash | Hot/cold skew và flash reads, không chỉ average latency |
| Redis latency tốt nhưng API vẫn chậm | App serialization, SQL misses, network, other dependencies |
| CROSSSLOT errors | OSS/Enterprise cluster policy và multi-key hash tags |

**Không vội chuyển tier** trước khi tách lỗi do client/configuration. Nếu phải chuyển Memory → Compute/Flash tier family, kiểm tra khả năng nâng/đổi tier: một số lựa chọn **fixed** sau creation, phải tạo cache mới.

## 14. Observability: làm sao biết Redis đang giúp hay đang làm chậm?

Một cache hit ratio 95% nghe có vẻ tốt, nhưng nếu 5% misses đều là những truy vấn SQL đắt nhất, backend vẫn có thể chậm. Ngược lại, cache hit ratio 70% cũng có thể hiệu quả nếu đã giảm được phần lớn truy vấn nặng.

### 14.1. Các lớp metrics cần liên kết

| Lớp | Metrics/logs | Điều cần quyết định |
|---|---|---|
| **Application** | Cache hit/miss, cache latency p95/p99, fallback rate | Cache có giảm business latency không? |
| **Redis service** | Used Memory Percentage, Server Load, CPU, connected clients | Thiếu RAM, compute hay connections? |
| **Commands** | GET/SET rate, operations/second, cache reads/writes | Traffic mix có đổi không? |
| **Memory** | Evicted keys, expired keys, memory trend | TTL/eviction/capacity có hợp lý không? |
| **Networking** | Private DNS, TCP connection errors, egress, TLS errors | Client có đúng route và auth không? |
| **Entra** | Authentication failures, token refresh/re-AUTH errors | Có hết token hoặc thiếu principal Redis không? |
| **Backend** | SQL query count/CPU/p95/deadlocks | Redis có thực sự giảm tải authoritative store? |
| **Reliability** | Failover events, geo-replication health, data recovery tests | HA/DR có đạt RTO/RPO? |
| **FinOps** | Cache tier/units, Private Link, logs, DB compute savings | Tổng lợi ích có xứng chi phí? |

Azure Managed Redis cung cấp Azure Monitor metrics và diagnostic settings; tên metrics/dimensions có thể khác version/tier. **Không mặc định mỗi metric là p99.** Ví dụ cache latency ở platform có thể là **average**, còn p95/p99 ứng dụng phải tự instrument.

### 14.2. Tính hit ratio

Với một workload có:

~~~text
Cache Hits   = 900,000
Cache Misses = 100,000
~~~

\[
\text{Hit ratio} = \frac{\text{Hits}}{\text{Hits}+\text{Misses}} \times 100
=90\%.
\]

Đừng tính `Cache Hits / All Redis commands` vì SET, EXPIRE và các commands khác không phải lookup hit/miss. Cũng cần phân biệt cache hit ở **application-local L1 cache** với Redis L2 cache nếu dùng hai tầng.

### 14.3. Alert ưu tiên

| Alert | Ý nghĩa | Runbook phản ứng |
|---|---|---|
| **Used Memory Percentage** cao kéo dài | Gần giới hạn; dễ evict/ghi lỗi | Phân tích keys, TTL, resize theo sizing |
| **Server Load/CPU** cao | Throughput/compute bottleneck | Hot keys/slow commands, Compute tier/shards |
| **Client Connections** gần limit | Pool/reconnect storm | Reuse client, giảm per-instance connections |
| **Evicted keys** tăng bất thường | Cache pressure hoặc policy không phù hợp | Kiểm tra TTL/eviction, DB load khi miss |
| **Cache Misses** tăng đột ngột | Flush, TTL avalanche, version key changed | Kiểm tra invalidation và SQL fallback |
| **Connection errors/NOAUTH** tăng | DNS, TLS, Entra refresh, Redis user permissions | Điều tra theo lớp, không bật static keys tùy tiện |
| **Application p99** cao | Tail latency ảnh hưởng người dùng | Tách Redis vs SQL vs network/serialization |
| **Geo replication unhealthy** | Multi-region state không được đồng bộ như dự kiến | Kiểm tra link/region/network, DR runbook |

**Alert phải có owner** và phân biệt lỗi Redis với nguồn khác. Một người vận hành có thể scale Redis lên lớn gấp đôi nhưng lỗi vẫn do database miss stampede hoặc code tạo connection mỗi request.

### 14.4. Azure diagnostics và dữ liệu nhạy cảm

Azure Portal cho phép cấu hình metrics/diagnostics export theo tính năng. Không mặc định Azure Monitor/Log Analytics tự có đầy đủ **per-command payload logs**. Nếu bật auditing kết nối/diagnostic streams:

- Chọn storage/Log Analytics/Event Hub phù hợp retention/cost.
- Hạn chế quyền truy cập logs theo phân loại dữ liệu.
- Không ghi `password`/Entra token/access key hoặc JSON chứa PII.
- Tương quan correlation ID ở application với Redis request/operation metrics.
- Đánh giá sampling, high cardinality labels và hóa đơn ingestion.

### 14.5. Synthetic tests

Một synthetic probe **chỉ dùng keys dành riêng cho kiểm thử**:

~~~text
SET health:catalog-test random-value EX 30
GET health:catalog-test
DEL health:catalog-test
~~~

Nó giúp chứng minh Redis có thể nhận commands từ một client được cấp phép. Nhưng **PING/GET thành công không chứng minh cache hit ratio tốt hay SQL đang khỏe**. Cần thêm synthetic business flow, test token refresh và failover của app.

## 15. Migration từ Azure Cache for Redis hoặc self-hosted Redis

Những dự án dùng Redis từ trước không nên chỉ đổi DNS endpoint rồi tuyên bố migration xong. Azure Managed Redis có khác biệt **tier, cluster policies, auth, ports, command/module compatibility và network topology**.

### 15.1. Khảo sát source

Trước migration, ghi nhận:

1. Source là Azure Cache for Redis Basic/Standard/Premium/Enterprise hay Redis tự quản lý?
2. Redis version, modules, blocked/used commands, LUA scripts, clustering, key hash tags.
3. Data size, connected clients, hot keys, TTL distribution, eviction policy.
4. Authentication hiện tại là access key/password/ACL hay Entra?
5. Hostnames/ports/network path; app VM, AKS, Functions, App Service nào đang dùng?
6. Có **Pub/Sub**, queues/streams hoặc session data không thể rebuild dễ dàng không?
7. RPO/RTO, expected downtime, acceptable cold-cache warming time.
8. Rollback plan và cách xác định key consistency.

### 15.2. Không mặc định “Redis tương thích 100%”

- **OSS Cluster** cần client cluster-aware và multi-key hash-slot design.
- **Enterprise Cluster** có proxy, vẫn có các giới hạn multi-key.
- **Non-clustered** có giới hạn size.
- Một số management commands bị chặn; module feature sets khác nhau.
- Port `10000`, TLS/client auth khác cache cũ.
- Entra principal authorization và token refresh phải được thêm vào client.
- Public/Private Endpoint DNS không giống cấu hình cũ.

Nếu code dùng `KEYS *`, scripts trên nhiều keys hoặc tự quản lý Redis CLUSTER commands, phải kiểm tra lệnh được phép trước khi chọn clustering policy. Với workload có RedisJSON/RediSearch, module compatibility có thể quyết định tier/policy ngay từ đầu.

### 15.3. Chọn mô hình chuyển đổi

| Phương pháp | Khi dùng | Rủi ro |
|---|---|---|
| **Rebuild from SQL/source** | Cache-aside thuần, cache data có thể tái tạo | Cold-start/DB spike và thời gian warm-up |
| **Export/Import** | Cần di chuyển snapshot của dataset, có downtime plan | Snapshot stale, format/version/module compatibility |
| **Migration tooling được Azure hỗ trợ** | Có hành trình migration phù hợp source tier và feature | Điều kiện/preview/endpoint update khác từng dòng |
| **Dual-write / shadow-read có kiểm soát** | Cần giảm downtime hoặc test mức tương thích | Dữ liệu lệch, double side effects, complexity |

**Không chạy dual-write nếu ứng dụng không có idempotency/consistency plan.** Với Redis chỉ là cache, đôi khi **tạo cache mới rồi warming/rebuild** an toàn hơn cố di chuyển toàn bộ keys.

### 15.4. Kế hoạch migration mẫu

~~~mermaid
flowchart TD
    INVENTORY[Inventory clients/keys/modules/commands] --> PLAN[Choose tier size cluster policy auth network]
    PLAN --> BUILD[Provision Azure Managed Redis target]
    BUILD --> TEST[Validate TLS/Entra/network/client cluster commands]
    TEST --> WARM[Warm target or import approved snapshot]
    WARM --> SHADOW[Compare values/latency and verify TTL]
    SHADOW --> CUT[Cut over one app/traffic cohort]
    CUT --> OBS[Observe SLO, misses, DB load, errors]
    OBS --> DEC{Acceptable?}
    DEC -->|No| ROLL[Rollback endpoint with reviewed plan]
    DEC -->|Yes| ALL[Promote remaining clients]
    ALL --> RETIRE[Retire old cache after retention/approval]
~~~

### 15.5. Cutover phải nghĩ đến TTL/invalidation

Hai cache có thể chứa giá trị cũ/mới khác nhau vì invalidation chỉ được gửi tới một phía hoặc source SQL đã đổi trong lúc import. Cần:

- Có **event/version key** hoặc cache namespace mới nếu cần phân biệt schema.
- Bảo đảm invalidation/writes trong giai đoạn dual-read/write được thiết kế.
- Không kết luận dữ liệu đúng chỉ từ số lượng keys.
- Với session storage, kiểm tra user experience khi chuyển endpoints (logout, token TTL, cookie behavior).
- Nếu dùng Redis Streams/PubSub cho business messaging, kiểm tra semantics replay/consumer groups; đừng biến event quan trọng thành một key dễ mất.

### 15.6. Migration theo vòng đời Azure Cache for Redis

Theo hướng dẫn Azure hiện hành, doanh nghiệp nên có lộ trình tới **Azure Managed Redis** trước các mốc retirement của dòng Azure Cache for Redis cũ. Có thể có migration tools ở **GA hoặc preview** tùy source tier; kiểm tra chi tiết support, dữ liệu, downtime và SKU availability trước khi chọn.

**Nguồn:** https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq; https://learn.microsoft.com/azure/redis/overview.

## 16. Bảng quyết định: chọn tier, clustering, reliability và security

Một quyết định mua Redis nên được lưu như **Architecture Decision Record** (ADR), không chỉ là screenshot Portal.

### 16.1. Ma trận theo workload

| Workload | Tier ưu tiên để benchmark | Cluster policy | Cần module? | Reliability |
|---|---|---|---|---|
| Catalog API vừa, cache 5–20 GB | **Balanced** | OSS nếu client cluster-aware; Enterprise nếu cần single endpoint | Không | HA, TTL + invalidation, fallback SQL |
| Feature flag dataset 100 GB, read nhẹ | **Memory Optimized** | OSS/Enterprise theo client | Không | HA, cache rebuild |
| Rate-limit counter throughput cao | **Compute Optimized** | OSS nếu key distribution tốt | Không | HA, atomic semantics, xác định fail-open/closed |
| Dataset 1 TB, 10% hot, mostly GET | **Flash Optimized** | Chính sách Flash hỗ trợ | RedisJSON nếu cần, không RediSearch | HA + benchmark cold reads, DR khác geo |
| Search/vector catalog | **Balanced/Compute/Memory** theo index/CPU | **Enterprise** hoặc Non-clustered trong limits | **RediSearch** | HA, index memory, reindex/rebuild |
| Session nhỏ, client legacy nonclustered | **Balanced** | Enterprise/Non-clustered theo compatibility | Không | HA; evaluate token/session loss |
| Multi-region active cache | In-memory tier compatible | Policy đồng nhất giữa vùng | Chỉ modules được hỗ trợ | HA + active geo, app routing, no persistence |

Bảng này là **điểm khởi đầu**, không phải kết luận thay benchmark. Redis size/SKU và feature support thay đổi; người học cần kiểm tra SKU cụ thể, region và giá tại thời điểm triển khai.

### 16.2. Cây quyết định rút gọn

~~~mermaid
flowchart TD
    START[Ứng dụng đang chậm hoặc cần cache] --> NEED{Có working set và repeat reads?}
    NEED -->|Không| SKIP[Optimize DB/query first, Redis may not help]
    NEED -->|Có| SIZE{Dataset rất lớn, hot/cold rõ?}
    SIZE -->|Có| FLASH{Chấp nhận cold latency và feature limits?}
    FLASH -->|Có| FLASH_T[Benchmark Flash Optimized]
    FLASH -->|Không| MEM_T[Benchmark in-memory tier]
    SIZE -->|Không| THROUGHPUT{CPU/ops bound hay memory bound?}
    THROUGHPUT -->|CPU/ops bound| COMPUTE[Compute Optimized]
    THROUGHPUT -->|Memory bound| MEMORY[Memory Optimized]
    THROUGHPUT -->|Chưa rõ| BAL[Start Balanced and benchmark]
    FLASH_T --> POLICY[Select cluster policy/modules]
    MEM_T --> POLICY
    COMPUTE --> POLICY
    MEMORY --> POLICY
    BAL --> POLICY
    POLICY --> SEC[Entra + TLS + network]
    SEC --> HA[HA + persistence/geo/rebuild choice]
    HA --> BENCH[Load test + cost + approval]
~~~

### 16.3. ADR mẫu

~~~yaml
# Ví dụ ADR dữ liệu trong tài liệu, không phải schema Azure Resource Manager.
decision: "Redis cho Product Catalog API"
authoritativeStore: "Azure SQL Database"
dataClassification: "Internal"
datasetMeasuredGb: 12
peakOpsPerSecond: 35000
workingSetHotRatio: 0.80
dataTierCandidate: "Balanced"
clusterPolicyCandidate: "OSS Cluster"
redisVersionCandidate: "Supported GA version"
modules: []
highAvailability: true
network: "Private Endpoint, public disabled"
authentication: "Microsoft Entra managed identity"
ttlSeconds: 300
evictionPolicy: "allkeys-lru if all keys rebuildable"
fallback: "SQL with bounded concurrency + circuit breaker"
monitoring:
  - cacheHitRatio
  - redisUsedMemoryPercentage
  - serverLoad
  - connectionErrors
rollback: "Switch back to prior cache or SQL fallback with SLO guardrails"
decisionGate: "Load test and security review"
~~~

**Chú ý:** `dataTierCandidate` hay `clusterPolicyCandidate` trong ADR không tự tạo Azure resource. Trường hợp RedisJSON/RediSearch, thay modules/policy theo compatibility trước provision.

### 16.4. Những gì cố định và có thể thay đổi

| Quyết định | Tính linh hoạt |
|---|---|
| Tier family in-memory so với Flash | Thường **khó/không đổi trực tiếp**, có thể cần tạo cache mới |
| OSS/Enterprise clustering policy | Thường **không đổi sau tạo** |
| Non-clustered → clustered | Có thể hỗ trợ một chiều trong điều kiện nhất định |
| Redis modules trên 7.4 | Thường phải chọn khi tạo |
| HA | Có thể bật thêm nhưng không nên mặc định tắt lại |
| Capacity size | Scale up và scale down có constraints |
| Public access/Private Endpoint | Có thể điều chỉnh theo network/change policy |
| Entra principals/diagnostics | Có thể quản trị qua lifecycle |
| Persistence/active geo | Có thể có restrictions, **không kết hợp cùng cache** |

Đây là lý do quyết định **tier family, clustering và modules** phải được review trước khi tạo production instance.

## 17. Troubleshooting: Redis chậm, mất kết nối hoặc lỗi Redis Cluster

Khi API chậm sau khi thêm Redis, cần phân biệt **DNS/network**, **TLS/authentication**, **client topology**, **memory/CPU**, **cache logic** và **database fallback**. Không tắt TLS hoặc bật access key authentication để khắc phục mọi lỗi.

### 17.1. Bảng lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Việc cần làm |
|---|---|---|
| `Name or service not known` | Redis FQDN sai hoặc Private DNS không resolve | Kiểm tra hostname/region, private zone/VNet links/resolver |
| DNS trả public IP khi định dùng private | App không có VNet Integration hoặc Private DNS link | Probe từ runtime thật; sửa network/DNS |
| TCP timeout ở `:10000` | NSG/firewall/route, PE Pending, public disabled nhưng client đi public | Kiểm tra approved PE, route và TCP |
| TLS certificate hostname mismatch | Kết nối qua IP/privatelink alias hoặc CA trust cũ | Dùng FQDN chuẩn, cập nhật trust store |
| `NOAUTH`/`WRONGPASS` | Entra token sai audience/expired, object ID không được thêm vào Redis users | Kiểm tra token scope/identity/data-plane grants |
| Kết nối chạy 1 giờ rồi đứt | Entra token không được refresh/re-AUTH | Dùng helper hỗ trợ long-lived auth |
| `CROSSSLOT Keys in request don't hash to same slot` | Multi-key command ở OSS/Enterprise cluster | Thiết kế hash tag hoặc đổi command/data model |
| `MOVED`/`ASK` chưa được client xử lý | Dùng standalone client với OSS Cluster | Dùng RedisCluster/cluster-aware library |
| `ERR unknown command`/blocked command | Dịch vụ quản lý chặn một số commands hoặc module chưa bật | Kiểm tra supported commands/modules |
| `OOM command not allowed` | Cache đầy và eviction policy/keys không cho loại | Xem Used Memory, TTL, eviction, resize |
| Evictions tăng sau release | Big keys, memory pressure, TTL/working set thay đổi | Đo key count/size, capacity |
| Hit ratio giảm | New key prefix/schema, TTL quá ngắn, invalidation sai | Phân tích key design và lookup patterns |
| Server Load cao | Hot key/CPU-heavy command/too many ops | Optimize commands, shard key, Compute tier |
| p99 tăng mạnh trên Flash | Cold values đọc từ flash, uniform access | Benchmark hot/cold, xem lại tier |
| Redis khỏe nhưng SQL quá tải | Cache misses avalanche hoặc fallback không giới hạn | Single-flight, TTL jitter, bounded SQL |
| 429/403 ở Azure management API | Azure RBAC/Policy/resource provider | Phân biệt control plane với Redis data-plane |
| Failover làm app treo | Client không reconnect, DNS/shard topology stale | Backoff, reconnect, token refresh, circuit breaker |

### 17.2. Runbook chẩn đoán theo thứ tự

**Bước 1 — Xác nhận resource:** đúng Azure subscription, resource group, cache name, tier, cluster policy, Redis version, private/public network setting.

**Bước 2 — DNS:** từ runtime bị lỗi, resolve **`<name>.<region>.redis.azure.net`**. Nếu private-only, phải có private endpoint IP phù hợp.

**Bước 3 — TCP:** kiểm tra port 10000; với OSS Cluster phải cho client kết nối shard ports sau discovery.

**Bước 4 — TLS:** certificate chain, hostname verification, supported TLS version, không dùng IP thay FQDN.

**Bước 5 — Identity:** kiểm tra Entra token scope `https://redis.azure.com/.default`, principal **object ID**, Redis user/data access policy; với connection lâu, kiểm tra re-AUTH.

**Bước 6 — Client topology:** RedisCluster hay single-endpoint client có khớp OSS/Enterprise/Non-clustered không? Có CROSSSLOT/blocked command?

**Bước 7 — Runtime load:** memory%, Server Load, CPU, connections, evictions, hits/misses, hot keys và p99.

**Bước 8 — Business fallback:** SQL/database CPU, cache stampede, latency và lỗi dữ liệu có đúng nguyên nhân không?

**Bước 9 — Recovery:** sửa đúng lớp, validate synthetic tests, monitor SLO và ghi incident/source-of-truth.

### 17.3. Tình huống token refresh

~~~text
09:00  App obtains Entra token and connects to Redis.
09:05  GET/SET requests succeed.
10:05  Token is expired; client keeps old token.
10:07  Authentication begins to fail on re-auth/new connections.
10:10  Team incorrectly regenerates Redis access key.
~~~

Giải pháp là dùng **token refresh/re-AUTH** có kiểm soát, không tạo static password như đường tắt. Nếu client đang dùng Redis Pub/Sub/RESP2 với connections chuyên dụng, kiểm tra helper hỗ trợ re-auth trên tất cả connections tương ứng.

### 17.4. Tình huống hot key

API có 10.000 sản phẩm nhưng 60% request đến `catalog:product:hot-item`. Redis toàn cluster mới dùng 30% memory, nhưng một shard CPU cao và p99 latency xấu. Nâng Memory Optimized lên size gấp đôi có thể **không** cải thiện phân bố key.

Hướng xử lý:

- Tìm hot key, request distribution và command complexity.
- Dùng near-cache/L1 cache ngắn hạn nếu cho phép staleness.
- Tối ưu serialization/value size và pooling.
- Cân nhắc shard-friendly key design và client batching.
- Benchmark Compute Optimized/cluster topology thay vì chỉ thêm memory.

### 17.5. Tình huống cache quá đầy

Cache default `volatile-lru`, nhiều keys không TTL nên không thuộc tập eviction. Used Memory cao, SET bắt đầu lỗi dù API GET đôi khi vẫn chạy. Sửa đúng:

- Xác định keys không TTL và vì sao chúng tồn tại.
- Thêm expiration phù hợp nghiệp vụ cho các keys có thể rebuild.
- Nếu **tất cả** data là cache có thể evict, cân nhắc `allkeys-lru` sau review.
- Tăng capacity với headroom nếu working set thực lớn.
- Thiết lập alerts; không chạy `FLUSHALL` trên production để giải phóng RAM.

## 18. FinOps: Redis có tiết kiệm chi phí thật không?

Một lựa chọn tối ưu tài chính phải so sánh **tổng chi phí không cache** với **Redis + app + database + network + operations**, không chỉ giá Redis SKU/giờ.

### 18.1. Các thành phần chi phí

| Thành phần | Ví dụ |
|---|---|
| **Managed Redis tier/size/HA** | Chi phí cấp phát cache, CPU/RAM capacity |
| **Active geo-replication** | Nhiều Redis instances ở nhiều region, network/DR |
| **Persistence/backup/export** | Disk/storage, Export Blob, automation và operations |
| **Private Endpoint/Private DNS/Resolver** | Endpoint, DNS, peering, VPN/Firewall/egress |
| **Application client compute** | CPU serialization, networking, retries, fallback |
| **Backend database** | SQL CPU/IO/throughput giảm nhờ hit hoặc tăng khi misses |
| **Observability** | Azure Monitor, Log Analytics, App Insights ingestion/retention |
| **CI/DR/test** | Staging instance, load tests, region backup, runbooks |

### 18.2. Ví dụ phân tích lợi ích

Giả sử trước khi cache:

~~~text
API requests:       5,000,000/day
Read-heavy share:   80%
SQL reads from API: 4,000,000/day
Expected cache hit ratio: 85%
~~~

Nếu các requests tương đương nhau và cache coverage đúng:

\[
\text{SQL reads avoided} \approx 4{,}000{,}000 \times 0.85
=3{,}400{,}000 \text{ reads/day}.
\]

SQL reads còn lại từ phần đó khoảng 600.000/day, nhưng đây là **định lượng request count**, không trực tiếp là **tiền tiết kiệm**. Nếu SQL database vẫn cần cùng vCore/SKU cho write peak, hóa đơn SQL có thể không giảm tương xứng. Ngược lại Redis đem lại latency/SLO tốt hơn dù không giảm được chi phí DB ngay.

Một business case nên:

1. Đo SQL CPU/IO p95 trước và sau.
2. Chạy load test để xác nhận hit ratio và command rate.
3. Xác định có thể **right-size SQL** an toàn hay không.
4. Tính Redis HA, networking, logs và staging resources.
5. Đánh giá cost của outage, session loss và production incident.
6. Dự toán growth 6–12 tháng và khả năng scale.

### 18.3. Tier nào “rẻ nhất”?

Không có tier rẻ nhất cho mọi workload:

- Memory Optimized có thể tiết kiệm nếu cần **RAM lớn/CPU vừa phải**.
- Compute Optimized có thể hiệu quả nếu cần throughput cao mà dataset nhỏ.
- Balanced có thể tốt nếu không cần extreme resource ratio.
- Flash Optimized có thể giảm chi phí dataset lớn có hot/cold pattern, nhưng phải chấp nhận khác biệt latency/feature.

**Giá và SKU availability thay đổi** theo region, currency, date, reservations và contract. Dùng Azure pricing calculator/Cost Management thay vì hardcode USD trong bài.

### 18.4. Reservation và commitment

Azure có thể cung cấp cơ chế reservation/commitment cho Azure Managed Redis theo điều kiện hiện hành. Chỉ cân nhắc sau khi biết **tier, region, capacity baseline và thời gian sử dụng ổn định**. Đừng ký commitment dài hạn khi chưa quyết định cluster policy/module hoặc còn dự kiến đổi tier family.

### 18.5. Những chi phí ẩn về chất lượng

- TTL quá ngắn → DB spike → cần SQL SKU lớn hơn.
- Quá nhiều logs chứa key/value → phí ingestion và rủi ro PII.
- Cấu hình Redis không HA → downtime và mất session.
- Shared Redis giữa các teams → một workload hot key làm chậm workload khác.
- Flash không hợp access pattern → tăng p99, phải migrate sang in-memory.
- Scale Redis mà không giảm database footprint → cộng chi phí hai hệ thống.

**Budget alerts không tự chặn phát sinh phí.** Với lab cần có owner/TTL tài nguyên và cleanup plan.

## 19. Case study: thương mại điện tử chạy chương trình khuyến mãi

**Bối cảnh giả định:** Nhóm Commerce có Azure App Service phục vụ Catalog API, Azure SQL Database giữ hàng hóa, Azure Container Apps phục vụ worker cập nhật bảng giá. Trong giờ cao điểm:

- 40.000 GET/giây đọc dữ liệu sản phẩm.
- Dataset có 12 GB payload/metadata sau khi serialize, dự kiến tăng 50% trong năm.
- Hot set chiếm khoảng 70% tổng dữ liệu.
- Product description chấp nhận stale tối đa vài phút.
- Giá khuyến mãi cần cập nhật gần real-time (staleness budget 10 giây).
- Tồn kho và thanh toán phải kiểm tra SQL transaction, không tin cache để commit.
- Client Java dùng Lettuce và có khả năng Redis Cluster.
- Private VNet, Entra managed identity và HA là yêu cầu production.

### 19.1. Kiến trúc tham chiếu

~~~mermaid
flowchart TB
    BUYER[Buyer web/mobile] --> API[Azure App Service - Catalog API]
    API -->|GET catalog keys| CACHE[(Azure Managed Redis)]
    API -->|Cache miss/fresh consistency| SQL[(Azure SQL)]
    API -->|Checkout transaction| SQL
    WORKER[Price update worker] -->|Commit price change| SQL
    WORKER -->|Invalidate related keys| CACHE
    CACHE -. Private Link/TLS/Entra .-> API
    MON[Azure Monitor/App Insights] -. Observe .-> CACHE
    MON -. Observe .-> API
    MON -. Observe .-> SQL
~~~

### 19.2. Lựa chọn ban đầu

| Quyết định | Lựa chọn để benchmark | Lý do |
|---|---|---|
| Tier | **Balanced** hoặc **Compute Optimized** | 40k GET/s, cần đo Server Load/throughput |
| Initial size | Sau đo dataset + 50% growth + headroom | Không suy từ 12 GB payload thô |
| Cluster policy | **OSS Cluster** | Lettuce RedisClusterClient hỗ trợ và GET theo key riêng |
| Modules | Không cần | Catalog lookup theo product ID không phải full-text search |
| Auth | Managed identity + Entra token auto-refresh | Không giữ static access key |
| Network | Private Endpoint + public disabled | API chỉ truy cập qua VNet |
| Availability | HA/zone redundancy nếu region hỗ trợ | Production SLO và failover |
| TTL descriptions | 180–300 giây + jitter | Chấp nhận stale ngắn và chống avalanche |
| TTL prices | 5–10 giây hoặc invalidate sau commit | Cần freshness cao; checkout xác nhận SQL |
| Eviction | Đánh giá `allkeys-lru` nếu toàn bộ keys có thể rebuild | Giảm rủi ro OOM, cần review |
| Degradation | Bounded SQL fallback + circuit breaker | Không để cache outage làm SQL ngã |
| DR | Rebuild cache từ SQL, có prewarming plan | Cache là derived state, geo có thể không cần |

**Không chọn Flash** nếu working set đủ nhỏ so với in-memory và yêu cầu latency ổn định ở mức hàng chục nghìn requests/s; Flash có ích chủ yếu khi dataset lớn và hot/cold pattern có ý nghĩa.

### 19.3. Capacity estimate

Giả sử sau đo đạc, cache dataset thực (gồm metadata) là 18 GB, tăng 50% sẽ thành 27 GB. Để giữ operational headroom 25%:

\[
\text{Effective memory target}
= \frac{27}{0.75}=36\ \text{GB}.
\]

Phải chọn Azure SKU có **effective usable capacity ≥36 GB**, sau khi xem reserved memory và semantics metric, rồi load test ở 40k–80k ops/s với đúng network/auth. Không chọn một SKU “36 GB” theo công thức nếu Azure không có SKU đó; dùng size được Azure cung cấp.

### 19.4. Khi có price update

~~~mermaid
sequenceDiagram
    participant W as Price Worker
    participant SQL as Azure SQL
    participant R as Managed Redis
    participant API as Catalog API
    W->>SQL: UPDATE price + COMMIT
    SQL-->>W: Success
    W->>R: DEL price:product:123 / update cache version
    Note over W: Retry invalidation via outbox if Redis fails
    API->>R: GET price:product:123
    alt Miss
       R-->>API: null
       API->>SQL: SELECT current price
       SQL-->>API: Committed price
       API->>R: SET value EX short TTL
    else Hit
       R-->>API: Cached price
    end
~~~

Với giá và tồn kho, phải xác định **acceptable stale window**. Nếu một mã giảm giá chỉ được áp dụng sau một mốc chính xác, checkout/service chịu trách nhiệm kiểm tra dữ liệu authoritative; cache có thể phục vụ display nhanh nhưng không là cơ sở cuối cùng cho thanh toán.

### 19.5. Incident: Redis outage gây SQL stampede

Trong một lần Redis failover, ứng dụng gặp timeout; mọi requests lập tức fallback xuống SQL và gây 100% CPU/IO. Cách xử lý:

1. Client Redis có bounded timeout/reconnect và circuit breaker.
2. Giới hạn số truy vấn SQL fallback đồng thời; có thể trả 503 với retry-after thay vì overload toàn hệ thống.
3. Cache hot keys được warm lại từ background worker.
4. TTL jitter/single-flight giảm herd sau phục hồi.
5. Theo dõi application hit ratio, SQL dependency rate, Redis load và 5xx.
6. Diễn tập lại failover với production-size dataset, ghi recovery time thực.

### 19.6. Khi nào đổi tier?

Nếu Balanced đạt memory headroom nhưng Server Load/CPU cao và p99 chậm, benchmark **Compute Optimized** với cùng workload. Nhưng đổi tier family không được mặc định là scale-in-place: cần check tính năng, pricing, cách tạo instance mới và migration plan. Nếu lỗi do hot key, đổi tier có thể chỉ cải thiện tạm mà không giải quyết root cause.

**Kết luận case:** Redis là công cụ giảm truy vấn và cải thiện latency; **thiết kế TTL/invalidation, cluster-awareness, fallback và database transaction** quyết định đúng/sai nghiệp vụ, không phải kích thước cache.

## 20. Bài thực hành: chọn Azure Managed Redis cho ba hệ thống

**Đề bài:** Bạn là cloud architect và phải lựa chọn giải pháp Redis cho ba ứng dụng chạy trên Azure. Không tự tạo tài nguyên production; bài thực hành có thể hoàn thành trên giấy/ADR hoặc trong **subscription lab** được cấp phép.

### 20.1. Các workload giả định

| Thuộc tính | Hệ A — Product Catalog | Hệ B — Analytics Hot/Cold | Hệ C — Realtime Counter |
|---|---|---|---|
| Dataset | 15 GB hiện tại; tăng 50% | 900 GB dữ liệu, 12% rất nóng | 5 GB |
| Tải | 20.000 GET/s | 2.000 queries/s, chủ yếu đọc | 100.000 INCR/s |
| Client | Java Lettuce cluster-aware | Python redis-py, yêu cầu client cluster-aware hoặc thay | .NET StackExchange.Redis |
| Độ trễ | p95 thấp, ổn định | Chấp nhận cold reads chậm hơn | p99 rất thấp |
| Chức năng | GET/SET/EXPIRE | JSON documents + có thể tìm kiếm theo field | Atomic increments, TTL |
| Recoverability | Có thể rebuild từ SQL | Có thể export/rebuild nhưng mất thời gian | Không được mất tính đúng đắn của quota |
| Network | Private VNet | Private VNet | API đa vùng |

### 20.2. Nhiệm vụ phân tích

1. **Hệ A:** chọn Balanced hay Compute Optimized làm baseline? Khi nào mới xem Memory Optimized?
2. Tính effective capacity target nếu A có 15 GB measured dataset, tăng 50% và muốn 25% headroom.
3. **Hệ B:** Flash Optimized có phù hợp không nếu cần RediSearch? Hãy giải thích feature incompatibility và đề xuất phương án khác.
4. Nếu B chỉ dùng GET/SET và hot set 12%, xây benchmark nào để quyết định Flash?
5. **Hệ C:** chọn Compute Optimized hay Memory Optimized? Vì sao throughput quan trọng hơn raw GB?
6. Nếu C dùng rate-limiter, làm sao tránh key count bị mất/evict khiến client vượt quota?
7. **Cluster policy:** nếu Java dùng Lettuce RedisClusterClient, tại sao OSS Cluster có thể tốt? Nếu dùng client không cluster-aware, chọn gì?
8. Viết hai Redis keys dùng **hash tag** để một atomic multi-key command có cơ hội cùng slot.
9. Phân biệt **RedisJSON** và **RediSearch**, xác định module nào cần khi chỉ GET object theo ID.
10. Vẽ luồng **App Service → outbound VNet → Private DNS → Redis Private Endpoint**. Vì sao app private endpoint inbound không đủ?
11. Thiết kế Microsoft Entra authentication cho một managed identity; nêu token scope, username và hành động refresh.
12. Vì sao Azure Contributor không tự được phép GET/SET trên cache?
13. Chọn HA/persistence/geo-replication cho A/B/C theo business RPO/RTO; xác định tính năng nào không kết hợp được.
14. Thiết kế TTL/invalidation cho product description (stale vài phút) và stock (cần transaction đúng).
15. Tính cache hit ratio nếu có 1.800.000 hits và 200.000 misses.
16. Viết kịch bản load test với data gần đầy, 1×/3× traffic, failover, token expiry và Redis unavailable.
17. Liệt kê metrics giúp quyết định thiếu RAM hay thiếu compute.
18. Nếu Redis Cluster trả `CROSSSLOT`, giải thích cách sửa và rủi ro đưa mọi key cùng hash tag.
19. Xây lộ trình chuyển từ Azure Cache for Redis Basic cũ sang Azure Managed Redis khi client vẫn dùng port 6380.
20. Viết ADR gồm tier, size, clustering, modules, auth, network, HA, fallback, monitoring và cost owner.

### 20.3. Lời giải có hướng dẫn

**Câu 2 — capacity:**

\[
\text{Dataset sau tăng trưởng}=15 \times 1.5=22.5\ \text{GB}.
\]

\[
\text{Effective memory target}=\frac{22.5}{0.75}=30\ \text{GB}.
\]

Phải đối chiếu 30 GB **effective memory** với SKU thực tế, reserved memory, HA memory metrics, key overhead và benchmark; không chọn bừa một cache size ghi 30 GB.

**Câu 3 — Flash + RediSearch:** theo compatibility hiện hành, Flash Optimized không hỗ trợ RediSearch. Nếu search là yêu cầu chính, cần chọn **tier in-memory + Enterprise/Non-clustered policy** hoặc tách search index sang dịch vụ phù hợp (chẳng hạn Azure AI Search), giữ Flash cho key–value caching nếu thật sự có lợi.

**Câu 5 — counter:** ít RAM nhưng rất nhiều INCR/s dễ là **compute/throughput-bound**. Benchmark Compute Optimized/OSS Cluster với phân bố keys thực; nếu mọi cập nhật dồn một key, phải sửa data/algorithm hoặc chấp nhận giới hạn single-shard, không chỉ mua thêm CPU.

**Câu 8 — hash tag:**

~~~text
cart:{customer-42}:items
cart:{customer-42}:total
~~~

Cùng phần trong ngoặc nhọn có thể giúp keys cùng hash slot trong OSS Cluster. Không dùng một hash tag cho mọi customer vì mất cân bằng shards.

**Câu 11 — Entra:** tạo managed identity và add principal object ID vào Redis users, yêu cầu scope `https://redis.azure.com/.default`, kết nối TLS với username=object ID, password=access token; có re-auth/token refresh trước hết hạn.

**Câu 15 — hit ratio:**

\[
\frac{1{,}800{,}000}{1{,}800{,}000+200{,}000}
=90\%.
\]

**Câu 19 — migration:** tạo AMR mục tiêu theo tier/policy/modules, test client library/cluster topology, port 10000, Entra auth, Private DNS, dữ liệu; warming/rebuild hoặc migration tooling theo support, chuyển clients có rollback và chỉ retire cache cũ khi metrics/business SLO ổn.

### 20.4. Tiêu chí bài đạt

Một câu trả lời tốt không chỉ ghi “Balanced” hoặc “Compute Optimized”. Nó phải có:

- Giả định về **dataset/working set, command mix, ops/s, latency, connection count**.
- Lý do cho **tier, initial size, cluster policy và module** tương thích.
- Quyết định **private networking/TLS/Entra principal**.
- HA/DR, persistence hoặc geo theo failure mode, hiểu các tính năng không tương thích.
- Cache logic đúng: TTL, invalidation, eviction, fallback và source of truth.
- Bộ benchmark/metrics chứng minh performance.
- Chi phí, rủi ro migration, kế hoạch cleanup và người chịu trách nhiệm.

## 21. Checklist lựa chọn và triển khai production

### 21.1. Trước khi tạo Redis instance

- [ ] Xác định use case là cache/session/coordination hay cần database/message broker khác.
- [ ] Có authoritative data store và thiết kế fallback/khôi phục khi cache trống.
- [ ] Đo dataset size, key count/value sizes, hot working set và tăng trưởng.
- [ ] Đo peak ops/s, latency p95/p99, connection limits và client concurrency.
- [ ] Chọn **Memory/Balanced/Compute/Flash** theo RAM/CPU/hot–cold, không theo cảm tính.
- [ ] Chọn **OSS/Enterprise/Non-clustered** theo client library, multi-key operations và modules.
- [ ] Xác nhận Redis version và **module set lúc tạo**, nhất là RediSearch/Flash restrictions.
- [ ] Kiểm tra region/SKU/size/preview/support và giá hiện hành.
- [ ] Bật **HA** cho production; xem zone distribution và reliability target.
- [ ] Quyết định persistence, geo-replication hay rebuild/Export; không giả định tất cả có thể bật cùng nhau.
- [ ] Chọn network architecture Private Endpoint/DNS/VNet và policy public access.
- [ ] Chọn Entra managed identity, Redis user permissions, TLS, token-refresh library.
- [ ] Quy định key naming, TTL, eviction, invalidation và sensitive-data policy.
- [ ] Có người sở hữu, IaC/CI/CD change controls, alerts và Cost Management budget.

### 21.2. Sau khi tạo / trước production traffic

- [ ] Đọc lại tier/size/policy/modules của **resource thật**, không chỉ manifest dự kiến.
- [ ] Private Endpoint connection Approved; DNS từ runtime trả private IP.
- [ ] TLS hostname/CA verify thành công, TCP 10000 và shard ports (nếu OSS) được phép.
- [ ] Managed identity có Redis data-plane permissions, không chỉ Azure RBAC.
- [ ] Token re-auth hoạt động qua nhiều chu kỳ expiry với long-lived connections.
- [ ] Test GET/SET/TTL/DEL trên keys synthetic và command compatibility.
- [ ] Benchmark working set gần production và throughput 1×/peak/burst.
- [ ] Test multi-key/CROSSSLOT nếu dùng OSS, RediSearch nếu module bắt buộc.
- [ ] HA failover/reconnect và SQL fallback/circuit breaker hoạt động.
- [ ] Alert Used Memory/Server Load/evictions/connections/hit ratio/p99 hoạt động.
- [ ] Cache warm-up plan tránh stampede/DB overload khi đổi môi trường.
- [ ] Có approval của security, app owner, SRE và FinOps.

### 21.3. Trong vận hành

- [ ] Theo dõi hit/miss, memory%, Server Load/CPU, connections và latency p95/p99 theo app.
- [ ] Xem các hot keys/big keys và command patterns trước khi scale.
- [ ] Quan sát database CPU/IO và throughput savings thực tế.
- [ ] Cập nhật Redis client/CA trust store/Entra SDK, kiểm thử token refresh.
- [ ] Theo dõi changes của data access policies và public access.
- [ ] Review Redis metrics/diagnostics retention và tránh log PII.
- [ ] Diễn tập failover, outage, cache rebuild và import/export khi cần.
- [ ] Có plan scale/migrate nếu dataset vượt memory hoặc tier family không đủ.
- [ ] Review reservation/pricing và resources orphaned theo định kỳ.

### 21.4. Khi có incident

- [ ] Xác định đúng subscription/RG/cache, tenant/region, policy và runtime bị ảnh hưởng.
- [ ] Kiểm tra DNS/TCP/TLS trước khi sửa Redis password hoặc tier.
- [ ] Kiểm tra Entra token expiry/object ID/Redis users khi gặp auth failure.
- [ ] Kiểm tra CROSSSLOT/MOVED, client mode và shard access.
- [ ] Đối chiếu Used Memory/evictions và Server Load/CPU trước khi scale.
- [ ] Nếu Redis outage, giới hạn SQL fallback để không tạo cascading failure.
- [ ] Không chạy FLUSHALL/FLUSHDB trên production để “dọn” dữ liệu.
- [ ] Giữ evidence, thử recover/rollback, xác minh business SLO sau thay đổi.

## 22. Dọn dẹp lab và quản lý vòng đời tài nguyên

Azure Managed Redis và Private Endpoints có thể tiếp tục tính phí khi bạn đã ngừng chạy code. Nhưng xóa sai cache production khiến sessions và dữ liệu tạm của nhiều ứng dụng mất ngay; một Redis instance dùng chung có thể phục vụ nhiều teams.

### 22.1. Kiểm kê (chỉ đọc)

~~~bash
az account show --query "{id:id,name:name}" -o table

az redisenterprise list \
  --resource-group "$RG" \
  --output table

az redisenterprise show \
  --resource-group "$RG" \
  --name "$CACHE_NAME" \
  --output json

az resource list \
  --resource-group "$RG" \
  --output table
~~~

Các biến `RG` và `CACHE_NAME` phải được xác nhận, không dựa vào tên gần giống production. Nếu cache có active geo-replication, cần kiểm tra group membership/ownership và runbook unlink/delete tương ứng trước bất kỳ thao tác hủy tài nguyên nào.

### 22.2. Quy trình cleanup

1. Xác minh **đây là instance lab riêng**, không nằm trong product/application shared.
2. Kiểm tra có session/jobs/streams/keys cần giữ hay không.
3. Nếu cần lưu dữ liệu, thực hiện Export/backup theo chính sách rồi verify artifact và quyền lưu trữ.
4. Xác nhận app/worker/CI không còn kết nối hoặc sẽ chuyển sang cache khác.
5. Kiểm kê Private Endpoints, DNS links, subnet, logs, Key Vault references và network dependencies.
6. Chỉ xóa resource hoặc resource group khi 100% thuộc lab và có approval.
7. Kiểm tra charges còn lại (Redis, Private Link, DNS, VPN/Firewall, logs, storage artifacts).

**Không làm sạch lab bằng lệnh `FLUSHALL`** trên cache chưa xác minh ownership. Redis data-plane flush và Azure resource deletion là hai loại hành động khác nhau, đều có thể phá dữ liệu.

Các lệnh **chỉ để tham khảo, được comment**:

~~~bash
# KHÔNG tự thực thi:
# az redisenterprise delete \
#   --resource-group "$RG" \
#   --name "$CACHE_NAME" \
#   --yes

# Không xóa resource group nếu còn shared DB/VNet/Private DNS/Key Vault:
# az group delete --name "$RG" --yes
~~~

Nếu preview/CLI hiện tại có options khác, kiểm tra `az redisenterprise delete --help` trước khi dùng. **Đừng tự động retry delete khi API trả trạng thái không rõ**, đặc biệt với geo-replication group hoặc cache có source data không thể rebuild.

## 23. Tài liệu tham khảo và lưu ý tính thời điểm

Các cấu hình tier, version, pricing, SKU preview và khả năng hỗ trợ có thể thay đổi. Khi xây thiết kế production, xem lại tài liệu chính thức đúng region/SKU và phiên bản dịch vụ:

1. [Azure Managed Redis overview](https://learn.microsoft.com/azure/redis/overview) — sản phẩm, tier, features, version.
2. [Plan Azure Managed Redis configuration](https://learn.microsoft.com/azure/redis/plan-configuration) — các quyết định cố định khi tạo.
3. [Choose a tier and plan capacity](https://learn.microsoft.com/azure/redis/plan-tiers-and-capacity) — RAM/CPU/Flash, connection limits, memory headroom.
4. [Choose a clustering policy](https://learn.microsoft.com/azure/redis/choose-clustering-policy) — OSS/Enterprise/Non-clustered, client compatibility, hash slots.
5. [Quickstart: create Azure Managed Redis](https://learn.microsoft.com/azure/redis/quickstart-create-managed-redis) — Portal, networking, policy/modules.
6. [Use Microsoft Entra authentication](https://learn.microsoft.com/azure/redis/entra-for-authentication) — token, Redis users, re-AUTH.
7. [Secure Azure Managed Redis](https://learn.microsoft.com/azure/redis/secure-azure-managed-redis) — Private Link/TLS/data access.
8. [Azure Managed Redis Private Link](https://learn.microsoft.com/azure/redis/private-link) — Private Endpoint, DNS, public access.
9. [Plan reliability and durability](https://learn.microsoft.com/azure/redis/plan-reliability-and-durability) — HA/zone/persistence/geo/backup restrictions.
10. [Data persistence](https://learn.microsoft.com/azure/redis/how-to-persistence) — RDB/AOF khác Export backup.
11. [Monitoring data reference](https://learn.microsoft.com/azure/redis/monitor-cache-reference) — metrics và semantics.
12. [Azure Cache for Redis retirement FAQ](https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq) — vòng đời/migration.

**Chú ý quan trọng:** bất kỳ ví dụ về mốc retirement, Redis preview version, default auth, port, size/ratio hoặc product feature nào trong bài là để học cách **ra quyết định dựa trên tài liệu có kiểm chứng**; trước khi chốt production phải cập nhật lại theo thông báo và bảng tính năng hiện hành. Không dùng Redis module/cluster policy chỉ từ một bài blog cũ có ví dụ cho Azure Cache for Redis.

## 24. Ghi nhớ

**Lựa chọn Azure Managed Redis cho ứng dụng** là bài toán kết hợp **data pattern, memory, compute, client compatibility, reliability, security và FinOps**; lựa chọn SKU rẻ nhất hoặc nhiều GB nhất chưa chắc đáp ứng yêu cầu.

Những điểm then chốt:

1. **Redis không mặc nhiên là database nguồn:** giữ dữ liệu gốc ở Azure SQL/Cosmos DB hoặc nơi có durability/transaction phù hợp; định nghĩa cache miss/fallback.
2. **Chọn tier theo bottleneck:** Memory Optimized ưu tiên capacity, Balanced cân bằng, Compute Optimized ưu tiên throughput, Flash Optimized cho dataset hot/cold lớn với latency/feature tradeoff.
3. **Clustering policy ảnh hưởng client:** OSS yêu cầu Redis Cluster-aware và đúng hash slots; Enterprise dùng proxy/single endpoint; Non-clustered giới hạn size.
4. **Modules phải chọn sớm:** RedisJSON/RediSearch/Bloom/TimeSeries có ràng buộc Redis version, tier và policy; Redis 8 preview không thay thế kiểm tra production suitability.
5. **Capacity phải có số đo:** data size + key overhead + reserved memory + growth + headroom + connection cap + benchmark, không chỉ GB.
6. **TTL/eviction quyết định tính đúng và chi phí:** cache stale/evicted là bình thường; invalidation và authoritative transaction giữ business correctness.
7. **Bảo mật nhiều lớp:** Private Endpoint/DNS/public access, TLS certificate verification, Microsoft Entra managed identity, Redis data access permissions; không nhầm Azure RBAC với Redis AUTH.
8. **HA không phải backup:** replica/zone chống hỏng node, persistence tự phục hồi cùng cache, active geo cho multi-region theo eventual consistency, Export/Import cho portable backup; có các tính năng không thể dùng đồng thời.
9. **Quan sát SLO cuối cùng:** cache hit ratio, p95/p99, memory%, Server Load, connections, evictions, Redis auth/network và tác động lên database.
10. **Migration/FinOps phải có kế hoạch:** Azure Cache for Redis cũ có lịch retirement, AMR có endpoint/policy mới; benchmark, có rollback, theo dõi chi phí và dọn lab an toàn.

Một quyết định Azure Managed Redis đạt yêu cầu khi bạn trả lời được: **Ứng dụng có dữ liệu nào cần cache, khối lượng/độ trễ ra sao, tier và cluster policy nào thực sự tương thích, keys có thể mất thế nào, client sẽ xác thực/kết nối qua đâu, Redis outage ảnh hưởng nghiệp vụ thế nào, và bằng chứng benchmark/cost nào chứng minh lựa chọn đó đáng triển khai?**
