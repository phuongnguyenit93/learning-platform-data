# Tách tenant lớn và giới hạn ảnh hưởng giữa các tenant

Một nền tảng SaaS dùng NoSQL phục vụ 50.000 tenant. Hầu hết tenant chỉ phát vài chục thao tác mỗi giây, nhưng một khách hàng doanh nghiệp đột ngột nhập dữ liệu với tốc độ 30.000 bản ghi/giây. Tổng CPU của cả cụm chưa đầy 50%, vậy mà độ trễ p99 của **những tenant nhỏ không liên quan** tăng từ 80 ms lên nhiều giây. Sau khi tạm dừng job nhập dữ liệu của tenant lớn, dịch vụ lại bình thường.

Đây là một dạng **noisy-neighbor problem**: workload của một tenant tiêu thụ tài nguyên chung tới mức gây hại cho tenant khác. Trong hệ thống phân tán, nguyên nhân có thể nằm ở **shard/partition nóng**, nhưng cũng có thể là thread pool, connection pool, cache, WAL, compaction, mạng, bộ điều phối truy vấn hoặc hệ thống index. Chỉ thêm node chưa chắc giải quyết được, nhất là nếu một **logical partition key** vẫn dồn toàn bộ lưu lượng vào cùng một đơn vị chịu tải.

Bài học thuộc **Database No SQL → Cân bằng và điểm nóng** này tập trung vào hai nhiệm vụ liên quan nhưng khác nhau:

1. **Tách tenant lớn:** chuyển, chia hoặc phân phối dữ liệu và thao tác của tenant quá lớn để tránh một key/shard/node thành nút cổ chai.
2. **Giới hạn ảnh hưởng giữa các tenant (blast-radius isolation):** bảo đảm lỗi, burst, truy vấn đắt hoặc tác vụ nền của tenant A không làm tenant B vượt SLO ngoài phạm vi được chấp nhận.

Ta sẽ phân tích shared/dedicated tenancy, phát hiện elephant tenants, tenant-aware routing, bucketing và rebalancing, quotas/admission control, worker/cache isolation, migration có an toàn dữ liệu, mức nhất quán, bảo mật, quan sát theo tenant và bài tập Java.

> **Nguyên tắc:** “Tách dữ liệu” không tự đồng nghĩa “cô lập tài nguyên”. Một tenant có shard riêng nhưng vẫn dùng chung cổng API, thread pool, metadata service hoặc mạng có thể tiếp tục ảnh hưởng tới tenant khác. Ngược lại, một hệ dùng chung shard có thể đạt mức công bằng tốt nếu phân bổ nguồn lực, admission control và cấu trúc key được thiết kế đúng.

> **Phạm vi:** Những cách đặt partition/shard, giới hạn throughput, cơ chế index và transaction phụ thuộc sản phẩm/phiên bản/cấu hình. Các số liệu minh họa là giả định để luyện suy luận, không phải benchmark của MongoDB, DynamoDB, Cassandra, Redis hoặc một nhà cung cấp cụ thể.

## 1. Định nghĩa tenant, elephant tenant và noisy neighbor

**Tenant** là một phạm vi khách hàng/tổ chức/đơn vị nghiệp vụ cần quản lý dữ liệu và tài nguyên riêng theo hợp đồng ứng dụng. Một tenant có thể gồm nhiều user, project, device, đơn hàng hoặc event stream.

**Elephant tenant** là tenant có quy mô **dữ liệu hoặc tải** lớn vượt đáng kể mức thông thường. Một tenant có thể là elephant ở nhiều chiều:

- Số tài liệu rất lớn.
- Dung lượng index cao.
- Write QPS hoặc bytes/giây cực lớn.
- Truy vấn tổng hợp/scan nặng.
- Concurrent requests cao.
- Tỷ lệ update/delete lớn làm compaction/GC tăng.
- Nhiều kết nối, change-stream consumers hoặc background jobs.
- Retention dài và backup/restore lớn.

**Noisy neighbor** là tenant có hành vi gây **suy giảm trải nghiệm hoặc tính sẵn sàng** của những tenant khác do cùng tranh một hoặc nhiều tài nguyên. Một elephant tenant chưa chắc là noisy neighbor nếu đã được phân bổ/cô lập tài nguyên hợp lý.

### 1.1. Ví dụ hai tenant chia một hot shard

~~~~text
Shard S1
  - Tenant A: 1.000 writes/s
  - Tenant B: 35.000 writes/s
  - Tenant C: 900 writes/s

Shard S2
  - 5.000 writes/s của nhiều tenant nhỏ

Shard S3
  - 4.500 writes/s của nhiều tenant nhỏ
~~~~

Nếu S1 có công suất ổn định theo workload chỉ khoảng 18.000 writes/s:
- Tenant B tạo queue tại S1.
- Các request của A và C **cùng shard** bị trễ.
- S2/S3 còn capacity nhưng không tự gánh tải của một logical key thuộc S1.
- Việc nhìn CPU trung bình toàn cluster có thể che giấu nút cổ chai.

### 1.2. Ví dụ tenant đã có shard riêng nhưng vẫn gây nhiễu

~~~~text
Tenant BIG -> Shard BIG
Tenant S1  -> Shard SMALL-1
Tenant S2  -> Shard SMALL-2
                   |
            Shared API gateway
            Shared connection pool
            Shared background worker
            Shared monitoring/log pipeline
~~~~

Tenant BIG gửi truy vấn khối lượng lớn, chiếm:
- Hết connection pool.
- Nhiều slot của thread pool.
- Băng thông egress.
- Hàng đợi worker.
- CPU của query router.

S1/S2 vẫn chậm dù shard của họ hoàn toàn khỏe. **Cô lập storage mà không cô lập đường yêu cầu end-to-end là chưa đủ.**

### 1.3. Những chiều isolation phải xác định riêng

| Chiều | Bất biến hoặc mục tiêu | Ví dụ |
| --- | --- | --- |
| **Data isolation** | Không tenant nào đọc/ghi dữ liệu tenant khác | Mọi key và auth đều gắn tenant |
| **Security isolation** | Quyền, secrets, encryption và audit theo tenant | Tenant A không gọi API của B |
| **Performance isolation** | Burst của A không đẩy p99 của B quá ngân sách | Per-tenant concurrency/quota |
| **Availability isolation** | Sự cố ở A không làm mọi tenant không dùng được | Pool, cell, shard hoặc cluster riêng |
| **Failure-domain isolation** | Node/zone lỗi chỉ ảnh hưởng phạm vi dự kiến | Cell assignment và placement |
| **Operational isolation** | Backup, restore, migration, import của A không phá B | Job scheduler có quota |
| **Cost isolation** | Đo và giới hạn phần tài nguyên mỗi tenant tiêu thụ | Chargeback/showback theo workload |
| **Compliance isolation** | Dữ liệu nằm ở nơi, thời hạn và đường sao chép phù hợp | Home region, backup locality |

Không nên coi một cờ **tenantId** trong JSON là bằng chứng đủ cho cả tám mục tiêu.

## 2. Những dấu hiệu cần tách tenant lớn

Các tín hiệu thường gặp:
- Tenant lớn chiếm tỷ lệ cao trong **write/read QPS**.
- Một partition/range chứa phần lớn write load.
- p99 tăng ở các tenant cùng node khi tenant lớn chạy import.
- Thêm node không làm p99/throughput cải thiện tương xứng.
- Tenant lớn có partition size, tombstone hoặc index footprint vượt ngưỡng đo được.
- Backup/restore hay report của tenant lớn tiêu tốn tài nguyên khiến tenant khác timeout.
- Query router chạm nhiều shard cho một tenant, tăng coordinator CPU.
- Tenant lớn cần RPO, data residency, maintenance window hoặc SLO khác nhóm còn lại.

Tuy nhiên **không được kết luận do tenant lớn chỉ vì tenant đó có nhiều bản ghi**. Cần tìm tài nguyên thật bị tranh chấp.

### 2.1. Phân loại theo ba loại kích thước

| Loại elephant | Đặc điểm | Hướng xử lý thường xem xét |
| --- | --- | --- |
| **Storage elephant** | Nhiều byte, lịch sử dài, scan/backup nặng | Time bucket, archive, split, storage tier, job isolation |
| **Write elephant** | Ingest/update liên tục vào ít key hoặc partition | Hash/salt buckets, admission control, batching phù hợp |
| **Read elephant** | Burst đọc hoặc truy vấn nặng, cache churn | Read replicas/projections, query budgets, cache partition, dedicated compute |
| **Concurrency elephant** | Nhiều kết nối và in-flight requests | Per-tenant concurrency, pool/cell isolation |
| **Maintenance elephant** | Index rebuild, deletes, repair, compaction lớn | Background I/O budget, lịch chạy, dedicated maintenance cell |

Một tenant có thể thuộc nhiều loại; cách tách theo dữ liệu không nhất thiết chữa được vấn đề đọc/cache.

### 2.2. “Tenant lớn” là khái niệm tương đối

Ngưỡng cần được xác định theo workload và capacity thực tế:
- 5.000 writes/s có thể bình thường với thiết kế A nhưng quá tải key của thiết kế B.
- Một tenant 100 GiB dữ liệu lạnh có thể ít ảnh hưởng hơn tenant 1 GiB nhưng tạo 20.000 update/s.
- Một tenant chỉ chạy report 10 lần/giờ có thể quét hàng terabyte.
- Một tenant premium có thể được phép peak lớn hơn tenant trial.

Vì thế **tiering phải xét nhiều dimension**, không chỉ tổng số hàng hoặc doanh thu.

## 3. Tìm đúng nút cổ chai trước khi đổi shard key

Một pipeline yêu cầu đi qua nhiều tài nguyên:

~~~~mermaid
flowchart LR
    USER["Tenant request"] --> EDGE["Gateway / auth"]
    EDGE --> API["API workers"]
    API --> ROUTER["NoSQL router"]
    ROUTER --> S1["Shard / partition"]
    ROUTER --> S2["Other shards"]
    S1 --> REPL["Replica / WAL"]
    S1 --> BG["Compaction / index"]
    API --> CACHE["Shared cache"]
~~~~

Độ trễ tổng quan:

\[
T_{\text{request}}=
T_{\text{queue}}+
T_{\text{gateway}}+
T_{\text{app}}+
T_{\text{routing}}+
T_{\text{storage}}+
T_{\text{merge}}+
T_{\text{network}}
\]

Đây là mô hình cộng các thành phần, không phải công thức đo chính xác cho mọi pipeline vì các bước có thể chồng lấp hoặc chạy song song. Điểm cần nhìn là **thời gian chờ/queue ở đâu đang tăng**.

### 3.1. Hot key khác hot shard và hot node

- **Hot key:** một giá trị partition key hoặc một record bị request dồn dập.
- **Hot logical partition:** tập rows cùng khóa logic quá lớn/quá nhiều thao tác.
- **Hot physical shard:** đơn vị vật lý nhận quá nhiều logical partitions nóng.
- **Hot node:** server đặt nhiều shard hoặc chịu compaction/replication/CPU cao.
- **Hot coordinator:** router phải merge quá nhiều truy vấn fan-out.
- **Hot shared service:** auth/metadata/cache/connection pool/queue gây nghẽn dù storage ổn.

Nếu một physical shard có nhiều key nóng, **rebalance placement** có thể giúp. Nếu **một key đơn lẻ** chịu toàn bộ write và không thể split trong atomic boundary, rebalance chỉ chuyển hotspot sang node khác; phải thay data model hoặc admission policy.

### 3.2. Tổng tải thấp vẫn có thể mất SLO

Giả sử:
- 12 shard, mỗi shard chịu khoảng 8.000 writes/s ở cấu hình thử.
- Tổng offered load 48.000 writes/s, tương đương trung bình 4.000/shard.
- Tenant BIG tạo 24.000 writes/s và bị route về một logical key.

Tổng công suất lý tưởng là 96.000 writes/s, nhưng partition chứa BIG vượt công suất; hàng đợi và timeout tăng. **Capacity trung bình không thay thế được capacity của key/shard nóng nhất.**

### 3.3. Đo độ lệch

Gọi:
- \(R\): tổng request/s.
- \(S\): số shard.
- \(R_{\max}\): request/s ở shard nóng nhất.

\[
R_{\text{avg}}=\frac{R}{S}
\]

\[
SkewRatio=\frac{R_{\max}}{R_{\text{avg}}}
\]

Nếu R=48.000/s, S=12, và shard nóng nhất nhận 26.000/s:

\[
SkewRatio=\frac{26.000}{4.000}=6{,}5
\]

Một shard gánh **6,5 lần** trung bình. Nhưng cần đo thêm **bytes, IOPS, CPU và thời gian xử lý**, vì một query lớn không tương đương một point lookup.

## 4. Ba mô hình multi-tenancy cơ bản

### 4.1. Pool chung: shared cluster, shared collection/table

~~~~text
Cluster SHARED
  Shard 1: Tenant A,B,C,...
  Shard 2: Tenant D,E,F,...
  Shard 3: Tenant G,H,I,...
~~~~

Ưu điểm:
- Tận dụng dung lượng/capacity.
- Dễ mở rộng số lượng tenant nhỏ.
- Ít hạ tầng và thao tác quản trị riêng.
- Dễ triển khai một schema/phiên bản chung.

Rủi ro:
- Shared hotspots và noisy neighbor.
- Một sự cố schema/index/compaction có thể ảnh hưởng nhiều tenant.
- Chi phí backup/migration/retention chung.
- Cần authorization và quota nghiêm ngặt.
- Khó cá thể hóa RPO/residency/maintenance cho tenant đặc biệt.

### 4.2. Silo riêng: dedicated cluster hoặc cell theo tenant

~~~~text
Tenant BIG -> Dedicated cluster / cell BIG
Tenant A,B,C -> Shared cell SMALL
~~~~

Ưu điểm:
- Có thể cô lập compute, memory, cache và storage tốt hơn.
- Dễ đặt quota/SLO và maintenance độc lập.
- Dễ điều chỉnh index/retention theo hợp đồng tenant.
- Một lỗi shard/node/cluster ít lan sang tenant khác nếu control plane cũng được cách ly phù hợp.

Đánh đổi:
- Overhead hạ tầng và vận hành.
- Capacity có thể bị bỏ trống.
- Backup, upgrade, monitoring theo nhiều đơn vị.
- Routing metadata và automation phức tạp.
- Shared gateway/auth/control plane vẫn có thể là điểm ảnh hưởng chung.

**Dedicated cluster không đồng nghĩa isolation tuyệt đối** nếu các tài nguyên phụ trợ vẫn chia sẻ mà không có ngân sách.

### 4.3. Bridge/hybrid: shared cho số đông, isolated cho elephant

Một chiến lược thực tế:

~~~~mermaid
flowchart TD
    ROUTER["Tenant-aware router"] --> LOOKUP["Placement catalog"]
    LOOKUP --> S1["Shared cell 1: small tenants"]
    LOOKUP --> S2["Shared cell 2: small tenants"]
    LOOKUP --> BIG["Dedicated cell: elephant tenant"]
    LOOKUP --> B2["Bucketed tenant on multi-shard cell"]
~~~~

Mỗi tenant có chính sách:
- Shared single partition.
- Shared nhưng chia nhiều buckets.
- Dedicated shard trong shared cluster.
- Dedicated compute cell hoặc cluster.
- Home region riêng theo hợp đồng.

Đây là **dải lựa chọn**, không phải hai trạng thái “chung hết” hoặc “tách hết”.

## 5. Chọn mức cô lập theo tenant

Một cách phân tầng vận hành:

| Tier minh họa | Workload | Placement có thể dùng | Guardrails |
| --- | --- | --- | --- |
| **Tiny** | Ít dữ liệu, QPS thấp | Shared pool | Quota cơ bản, max query cost |
| **Standard** | Tải ổn định | Shared multi-shard | Tenant concurrency, per-key metrics |
| **Growing** | Một số peak lớn | Dedicated buckets hoặc placement group | Adaptive limits, read projection |
| **Elephant** | Tải lớn, SLO chặt | Dedicated shard/cell | Reserved capacity, isolation tests |
| **Critical regulated** | RPO/residency/bảo mật riêng | Dedicated cluster/region nếu phù hợp | Audited routing, dedicated controls |

Đây chỉ là mô hình ví dụ. Không dùng tên gói thương mại làm thước đo kỹ thuật duy nhất: một khách hàng nhỏ có thể tạo burst lớn do bug; một khách hàng lớn nhưng dữ liệu lạnh có thể không cần dedicated compute.

### 5.1. Khi nào nên nâng một tenant khỏi shared pool?

Một policy có thể dựa trên:
- Sustained QPS hoặc bytes/s cao qua nhiều cửa sổ.
- Peak p99 ảnh hưởng tenant khác.
- Hot partition vượt ngưỡng capacity.
- Dung lượng hoặc index footprint vượt giới hạn an toàn.
- Job quét/backup dài gây tranh I/O.
- Hợp đồng SLO/RPO/residency riêng.
- Dự báo tăng trưởng đã được xác nhận.

**Không nên tự chuyển dữ liệu ngay khi có burst 30 giây**: migration có rủi ro và chi phí. Có thể dùng admission control để giữ ổn định tức thời, rồi đánh giá placement lâu dài.

### 5.2. Khi nào nên hạ tenant về shared pool?

Khi tenant giảm tải:
- Không xóa dedicated cell ngay nếu vẫn cần giữ dữ liệu/backup.
- Xem lại điều kiện SLO/residency/maintenance.
- Tính chi phí migration hai chiều.
- Tránh liên tục chuyển qua lại do dao động quanh một ngưỡng.

Có thể dùng **hysteresis**: ngưỡng promote và demote khác nhau, cùng thời gian quan sát đủ dài.

## 6. TenantId làm shard key: dễ truy cập nhưng dễ tạo elephant partition

Trong ứng dụng SaaS, nhiều query bắt đầu bằng tenantId:

~~~~text
GET /tenants/T-42/orders
GET /tenants/T-42/users/U-77
GET /tenants/T-42/events
~~~~

Chọn tenantId làm partition/shard key có thể:
- Định tuyến rõ theo tenant.
- Dễ thực thi một số transaction/aggregate trong tenant.
- Hỗ trợ export/backup theo tenant.
- Thuận tiện cho chi phí/giới hạn theo tenant.

Nhưng nếu tenant BIG có **35% total writes**, hash(tenantId) không tự chia 35% write ấy ra nhiều logical keys. Hash chỉ phân phối **các tenantId khác nhau**.

### 6.1. Lỗi suy luận phổ biến

> “Có hàng chục nghìn tenant nên tenantId cardinality cao, dữ liệu sẽ tự đều.”

Số giá trị phân biệt **không nói tỷ lệ request/byte ở mỗi giá trị**. Một khách hàng có thể chiếm 1/3 traffic; nhiều tenant nhỏ cộng lại chưa chắc cân bằng được.

### 6.2. Thêm physical nodes không chữa được single hot logical key

Nếu engine giữ một tenantId trong một logical partition/record có giới hạn throughput:
- Thêm node tăng tổng capacity.
- Một key vẫn có giới hạn theo partition/protocol.
- Di chuyển key sang node mạnh hơn chỉ tăng headroom tới một mức.
- Cần **chia tenant thành nhiều khóa** nếu invariant và query cho phép.

### 6.3. Khi engine tự chia physical storage

Một số managed NoSQL có cơ chế tự split/move/scale physical partitions. Điều này có thể giúp với **tập dữ liệu** hoặc range lớn, nhưng không được suy rằng nó có thể chia vô hạn mọi kiểu **single-key hot write** hoặc transaction contention.

Hãy kiểm chứng:
- Throughput thực đo trên **một partition key value**.
- API có giới hạn item/partition không?
- Adaptive capacity và split policies hỗ trợ workload này tới đâu?
- Index/GSI có hot key riêng không?
- Truy vấn/conditional writes cần cùng atomic boundary nào?

## 7. Chia tenant lớn thành buckets

Một cách phổ biến là dùng **tenantId + bucketId**.

~~~~text
Trước:
  PK = TENANT#BIG

Sau:
  PK = TENANT#BIG#BUCKET#00
  PK = TENANT#BIG#BUCKET#01
  ...
  PK = TENANT#BIG#BUCKET#15
~~~~

Nếu các bản ghi có ID độc lập và bucket được chọn ổn định, writes có thể được phân tán qua nhiều logical partitions.

### 7.1. Chọn bucket dựa trên stable entity ID

Ví dụ:

~~~~text
bucketId = stableHash(orderId) mod 16
partitionKey = tenantId + ":" + bucketId
~~~~

Lợi ích:
- Cùng orderId luôn quay về cùng bucket nếu thuật toán và bucketCount không đổi.
- Có thể route point lookup khi biết tenantId và orderId.
- Writes nhiều order độc lập có xu hướng phân tán nếu hash tốt.

Giới hạn:
- Query toàn tenant phải đọc nhiều bucket.
- Nếu orderId do client tạo mới mỗi retry, có thể tạo duplicate.
- Đổi 16 → 32 buckets làm mapping thay đổi; phải version routing/migrate.
- Một **order cực nóng** vẫn nằm một bucket; tăng số buckets không chia write trên chính order đó.

### 7.2. Bucketing theo userId

Nếu tenant lớn có rất nhiều user:
 
~~~~text
bucketId = stableHash(userId) mod 16
~~~~

Có thể giữ toàn bộ order của một user trong một logical bucket, hỗ trợ một số query user-local tốt hơn.

Nhưng nếu **một user** tạo 80% traffic tenant, nó vẫn là hot key. Do đó lựa chọn hash(orderId) hay hash(userId) phụ thuộc **tập thao tác cần locality và skew ở cấp user**.

### 7.3. Time bucket

Một thiết kế event log:

~~~~text
PK = (tenantId, dayBucket)
SK = (eventTime, eventId)
~~~~

Giúp giới hạn kích thước partition theo thời gian và hỗ trợ retention, nhưng toàn bộ writes hôm nay của tenant BIG có thể dồn vào **dayBucket hiện tại**.

Nếu cần phân tán active writes:

~~~~text
PK = (tenantId, dayBucket, hashBucket)
SK = (eventTime, eventId)
~~~~

Khi đó query một ngày phải fan-out các hashBucket và merge theo eventTime/eventId.

**Time bucket chủ yếu giới hạn kích thước/lịch sử; hash bucket giúp phân phối tải song song.** Hai mục tiêu không nên bị đánh đồng.

### 7.4. Tính số bucket theo capacity và headroom

Giả sử:
- Tenant BIG tạo peak **21.000 write/s**.
- Một logical partition chịu ổn định **4.000 write/s** theo benchmark cụ thể.
- Muốn chỉ sử dụng tối đa **65%** mức đó để giữ headroom.

Công suất mục tiêu mỗi bucket:

\[
R_{\text{bucket,target}}=4.000\times0{,}65=2.600\text{ write/s}
\]

Số bucket lý tưởng:

\[
B_{\min}=\left\lceil\frac{21.000}{2.600}\right\rceil=9
\]

Cần ít nhất **9 bucket** trong mô hình phân phối tuyệt đối đều, chưa tính skew, read traffic, replication, compaction và peak lớn hơn dự báo. Một triển khai có thể thử 12 hoặc 16 buckets sau khi đo tradeoff read fan-out.

**Không lấy công suất quảng cáo của toàn node làm công suất một partition**. Ngưỡng 4.000/s trên là giả định benchmark, không phải giới hạn chung của NoSQL.

### 7.5. Số bucket nhiều hơn không luôn tốt hơn

Nếu 16 buckets phục vụ tenant-wide query:
- Query một order có thể target 1 bucket nếu biết ID.
- Query “20 order mới nhất” có thể fan-out 16 buckets.
- Query “tổng doanh thu 12 tháng” có thể chạm rất nhiều time × hash buckets.

Coordinator phải merge, sort và phân trang; p99 có thể chịu ảnh hưởng bucket chậm nhất. Bucket count cần tính bằng **cost của cả read và write**, không chỉ throughput ghi.

## 8. Tách tenant lớn thành shard/cell riêng

Một hướng khác là **đưa tenant BIG khỏi shared pool**.

~~~~text
               Tenant routing catalog
                 /             \
          Shared cells       BIG cell
       T1,T2,T3,...          T-BIG
~~~~

Có các cấp tách:

| Cấp | Điều cô lập được nhiều hơn | Điều còn dùng chung |
| --- | --- | --- |
| **Dedicated logical partition** | Đường data/key | Node/CPU/disk/cache thường vẫn chung |
| **Dedicated physical shard** | Tải một số partition/storage | Router, cluster metadata, API, network |
| **Dedicated compute pool/cell** | Workers, connection pools, cache, storage ở mức cell | Global gateway, identity, billing |
| **Dedicated cluster** | Control plane dữ liệu và tài nguyên cluster riêng hơn | Gateway/auth/control plane/ops có thể chung |
| **Dedicated region/environment** | Failure domain/compliance tốt hơn theo thiết kế | Cross-region dependencies, shared services còn tồn tại |

**Một cell** thường là đơn vị vận hành chứa nhóm service/data capacity, có routing theo tenant. Thuật ngữ này là kiến trúc ứng dụng, không phải primitive chuẩn của mọi database.

### 8.1. Khi dedicated cell hiệu quả

- Một tenant yêu cầu công suất dự phòng riêng.
- Workload có query scan/aggregation hoặc index nặng khó chia.
- SLO và maintenance window cần khác tenant nhỏ.
- Replica placement, backup hoặc encryption policy riêng.
- Có sự cố nhiều lần chứng minh shared pool không đáp ứng isolation budget.

### 8.2. Khi dedicated shard chưa đủ

Một job tenant BIG tạo 10.000 request/giây và mỗi request:
- Dùng auth service chung.
- Giữ 1 connection trong API pool.
- Chiếm 1 worker thread.
- Gửi 100 KiB logs.

Kể cả DB shard riêng, tenant BIG vẫn có thể làm auth/API/log pipeline quá tải. Cần **quota và bulkhead từ edge tới storage**, không chỉ placement ở database.

### 8.3. Không tách tenant bằng cách copy data sang hai cluster rồi cùng ghi tự do

Nếu BIG được di chuyển từ shared sang dedicated, để **cả hai cluster làm authority ghi** mà không có transaction/conflict policy rõ sẽ tạo split brain:
- Hai booking cùng logical ID.
- Dữ liệu update lệch.
- Cùng operationId được thực thi hai nơi.
- Xóa ở nơi này nhưng bản kia “hồi sinh” sau replay.

Migration cần **quyết định một authority hoặc protocol đa vùng rõ ràng**, chứ không chỉ thay DNS.

## 9. Tách tenant theo một “routing catalog” có phiên bản

Một hệ hybrid cần biết tenant nào đang ở đâu. Routing metadata minh họa:

~~~~json
{
  "tenantId": "T-BIG",
  "placement": "DEDICATED_CELL",
  "cellId": "CELL-17",
  "homeRegion": "VN",
  "routingVersion": 12,
  "bucketScheme": "HASH_ORDER_ID_V1",
  "bucketCount": 16,
  "state": "ACTIVE"
}
~~~~

Một tenant nhỏ:

~~~~json
{
  "tenantId": "T-42",
  "placement": "SHARED",
  "cellId": "CELL-02",
  "homeRegion": "VN",
  "routingVersion": 4,
  "bucketScheme": "SINGLE_BUCKET",
  "bucketCount": 1,
  "state": "ACTIVE"
}
~~~~

### 9.1. Router cần những bảo đảm gì?

- **Định tuyến ổn định:** cùng tenant/operation không nhảy nơi tùy tiện.
- **Version hóa:** router biết mapping nào đang hiệu lực.
- **Auth isolation:** tenantId được lấy từ identity context đáng tin, không chỉ header client.
- **Khả năng hồi phục:** catalog không được chỉ nằm trong RAM của một service instance.
- **Độ mới metadata:** cache routing cần invalidation/epoch/fencing thích hợp.
- **Dự phòng:** catalog outage không khiến mọi tenant ngừng hoạt động nếu có chiến lược an toàn.
- **Quan sát:** log/tracing biết tenant/cell/routingVersion mà không làm metric cardinality bùng nổ.

### 9.2. Router stale trong cutover

~~~~text
T0 Tenant BIG thuộc CELL-A, routingVersion=11.
T1 Cutover sang CELL-B, routingVersion=12.
T2 API instance cũ vẫn cache version=11.
T3 Instance cũ gửi WRITE tới CELL-A.
~~~~

Nếu CELL-A vẫn chấp nhận ghi không kiểm tra epoch, **hai nơi** có thể cùng thay đổi một tenant.

Một hàng rào phù hợp có thể là:
- CELL-A chuyển sang read-only/redirect sau khi mất ownership.
- Write phải có **routingVersion/epoch** được nguồn kiểm tra.
- Chủ sở hữu mới chỉ hoạt động sau bước cutover hợp lệ.
- Stale writer bị từ chối hoặc redirect tới authority mới, không tự commit song song.

**Router cache TTL không phải cơ chế fencing đầy đủ.** Metadata cũ có thể tồn tại trong worker, retry queue hoặc process tạm dừng quá TTL.

## 10. Java 21: định tuyến tenant và bucket ổn định

Ví dụ một API Java tách logic định tuyến ra khỏi repository. Các kiểu sau minh họa kiến trúc, không phải SDK của một NoSQL cụ thể.

~~~~java
public enum Placement {
    SHARED,
    DEDICATED_CELL
}

public record TenantRoute(
        String tenantId,
        String cellId,
        String homeRegion,
        long routingVersion,
        Placement placement,
        int bucketCount
) {
    public TenantRoute {
        if (bucketCount <= 0) {
            throw new IllegalArgumentException(
                    "bucketCount must be positive");
        }
    }
}

public interface TenantRouteCatalog {
    TenantRoute routeFor(String authenticatedTenantId);
}
~~~~

### 10.1. Tính bucket bằng hash có tính ổn định

~~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class TenantBucket {
    private TenantBucket() {}

    public static int forEntity(String stableEntityId, int bucketCount) {
        if (stableEntityId == null || stableEntityId.isBlank()) {
            throw new IllegalArgumentException("stableEntityId is required");
        }
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount must be positive");
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(stableEntityId.getBytes(StandardCharsets.UTF_8));
            long bits = ByteBuffer.wrap(digest).getLong();
            return (int) Long.remainderUnsigned(bits, bucketCount);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~~

Cách sử dụng:

~~~~java
TenantRoute route = catalog.routeFor(authenticatedTenantId);

int bucket = TenantBucket.forEntity(
        stableOrderId,
        route.bucketCount()
);

String partitionKey =
        route.tenantId() + "#BUCKET#" + bucket;

// Gửi thao tác tới route.cellId(), kèm routingVersion.
// Storage cần validate ownership/version ở ranh giới ghi.
~~~~

**Lưu ý:**
- Thuật toán SHA-256 + modulo là ví dụ **application bucketing**, không phải hash/routing nội bộ bắt buộc của DynamoDB/MongoDB/Cassandra/Redis.
- Phải version hóa **hash algorithm, UTF-8 normalization, input identity và bucket count**.
- Đổi bucketCount làm phép chia lại thay đổi; dữ liệu cũ cần routing version/migration.
- **stableOrderId** phải giữ nguyên qua retry; nếu client sinh ID mới, hash ổn định vẫn không chống duplicate nghiệp vụ.
- Một nguồn dữ liệu có conditional/transaction guard vẫn cần bảo vệ uniqueness/invariant của order.

### 10.2. TenantId phải đến từ auth context

Luồng sai:

~~~~text
Client tự gửi X-Tenant-ID: T-VICTIM
Router tin header -> truy cập shard của T-VICTIM
~~~~

Luồng đúng phải có:
- Identity đã xác thực.
- Membership/role đối với tenant yêu cầu.
- TenantId được xác minh ở authorization layer.
- Data-level tenant guard nếu phù hợp.
- Audit không lộ dữ liệu của tenant khác.

**Routing isolation không thay thế authorization isolation.**

## 11. Isolation còn cần admission control

Chia dữ liệu nhưng không giới hạn lượng tài nguyên một tenant được dùng vẫn có nguy cơ noisy neighbor.

**Admission control** là quyết định **có cho request vào hệ thống tại thời điểm đó hay không** trước khi nó chiếm tài nguyên đắt.

Có thể kiểm soát:
- Requests/giây.
- Writes/giây hoặc bytes/giây.
- Số query concurrent.
- Số batch jobs đang chạy.
- Số bytes scanned.
- CPU cost ước lượng.
- Số connection hoặc worker slots.
- Memory/IO budget cho aggregation.
- Search result size và pagination depth.

### 11.1. Token bucket cho burst có kiểm soát

Token bucket có:
- **Rate r:** số token được bổ sung mỗi giây.
- **Capacity B:** tối đa token có thể tích lũy, cho phép burst ngắn.
- **Cost c:** mỗi request tiêu tốn c token.

Nếu tenant có r=1.000 tokens/s, B=5.000 và mỗi write tốn 1 token:
- Burst tối đa từ bucket đầy có thể dùng tới 5.000 token.
- Tải liên tục trung bình không nên vượt tốc độ refill 1.000 token/s.
- Nếu request tốn nhiều tài nguyên, cost nên lớn hơn 1 hoặc có một budget riêng.

Công thức ý tưởng:

\[
tokens(t)=\min(B, tokens(t_0)+r\cdot(t-t_0))
\]

Chỉ nhận request khi tokens >= c.

Token bucket **không bảo vệ mọi tài nguyên** nếu mỗi request có chi phí dao động 1–10.000 lần và tất cả chỉ tính c=1. Có thể cần một hệ giới hạn dựa trên **ước lượng cost và điều chỉnh theo quan sát**.

### 11.2. Concurrency limit không giống rate limit

100 request/s mỗi request chạy 20 ms có thể dùng ít worker slots; 100 request/s mỗi request chạy 20 giây có thể làm đầy toàn bộ pool.

Theo trực giác định luật Little:

\[
L \approx \lambda W
\]

Với \(\lambda=100\) requests/s và \(W=20\) giây:

\[
L\approx2.000\text{ requests in flight}
\]

Một tenant có thể không vượt QPS quota mà vẫn chiếm 2.000 connections/worker slots. Vì vậy cần **per-tenant in-flight cap, timeout và cancellation semantics** bên cạnh rate limiter.

### 11.3. Budget cho truy vấn nặng

Một query:

~~~~text
Find all events for tenant BIG
WHERE createdAt >= 2020
ORDER BY score DESC
~~~~

có thể chạm hàng trăm partition. Chỉ giới hạn 100 queries/s không đủ.

Có thể áp dụng:
- Max time range.
- Max rows/bytes scanned.
- Max shards touched.
- Pagination/cursor bắt buộc.
- Query timeout và memory cap.
- Tách analytical query sang hệ batch.
- Pre-aggregation và materialized views.
- Cost-based admission.

Nếu cắt ngang query đã ghi side effect, phải thiết kế **cancellation và retry** đúng; không tự suy rằng timeout của client đã hủy toàn bộ thao tác server.

## 12. Java: minh họa per-tenant concurrency guard

Một ứng dụng có thể giới hạn số thao tác nặng đồng thời theo tenant. Mã dưới đây chỉ minh họa **local process guard**, không phải quota phân tán hoàn chỉnh.

~~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public final class LocalTenantBulkhead {
    private final Map<String, Semaphore> permits =
            new ConcurrentHashMap<>();
    private final int maxConcurrentPerTenant;

    public LocalTenantBulkhead(int maxConcurrentPerTenant) {
        if (maxConcurrentPerTenant <= 0) {
            throw new IllegalArgumentException("positive limit required");
        }
        this.maxConcurrentPerTenant = maxConcurrentPerTenant;
    }

    public <T> T execute(String tenantId, Supplier<T> work) {
        Semaphore semaphore = permits.computeIfAbsent(
                tenantId,
                ignored -> new Semaphore(maxConcurrentPerTenant)
        );

        if (!semaphore.tryAcquire()) {
            throw new TenantBusyException(
                    "tenant concurrency limit reached");
        }

        try {
            return work.get();
        } finally {
            semaphore.release();
        }
    }

    public static final class TenantBusyException
            extends RuntimeException {
        public TenantBusyException(String message) {
            super(message);
        }
    }
}
~~~~

Ví dụ:

~~~~java
Order order = bulkhead.execute(tenantId, () ->
        orderRepository.findExpensiveOrder(tenantId, orderId)
);
~~~~

**Giới hạn của ví dụ:**
- Chỉ bảo vệ **một JVM**; 20 API instances có thể cấp 20 lần quota này.
- ConcurrentHashMap tăng theo số tenant; production cần chiến lược eviction/lifecycle để tránh memory growth.
- Không có queue fairness, ưu tiên, timeout theo tenant tier.
- Không tự giới hạn I/O bytes, database threads hoặc query CPU.
- Không kiểm soát external jobs/SDK retries.
- Không thay thế source-side quotas/conditional guards.

Một triển khai thực cần phối hợp **per-instance caps và global quota/lease/admission policy phù hợp**, tránh tự xây distributed lock không có fencing cho những bất biến quan trọng.

## 13. Fair scheduling: người nhiều request không được chiếm mọi worker

Nếu một shared worker queue là FIFO chung:

~~~~text
Queue:
  BIG, BIG, BIG, BIG, BIG, ... 50.000 jobs ...
  SMALL-A
  SMALL-B
~~~~

Jobs của tenant nhỏ có thể đợi sau một backlog khổng lồ dù chỉ có một thao tác.

Các hướng thiết kế:
- **Per-tenant queues** với lịch round-robin/weighted fairness.
- **Weighted fair queuing** cho tenant có tier/capacity khác nhau.
- **Reserved worker slots** cho workload nhạy cảm.
- **Queue caps** để một tenant không chiếm toàn bộ RAM/broker partition.
- **Deadline-aware scheduling** hoặc tách interactive vs batch.
- **Retry budgets** theo tenant.
- **Backpressure từ storage** trở lại API.
- **Dead-letter/recovery queues** không để job poison chặn cả hàng.

### 13.1. Weighted fairness có bảo đảm nào?

Giả sử worker pool có 100 slots:
- BIG được trọng số 5.
- SMALL-A, SMALL-B được mỗi tenant trọng số 1.

Một scheduler cân bằng có thể cấp phần capacity tương ứng với trọng số **khi các queue đều có tải**, nhưng con số thực phải có chính sách **minimum reserved capacity, cap và work-conserving behavior** rõ.

Điều quan trọng:
- Khi SMALL-A không có request, BIG có thể dùng capacity rảnh nếu cho phép.
- Khi SMALL-A trở lại, BIG phải nhường trong khoảng thời gian/SLO xác định.
- Nếu BIG có job 30 phút không preempt được, công bằng ở cấp enqueue chưa đủ; cần giới hạn **job duration/resource**.

### 13.2. Hàng đợi riêng không giúp nếu downstream vẫn nghẽn chung

Nếu scheduler rất công bằng nhưng mọi tenant đổ vào **một hot partition**, đến database vẫn có thể hàng chờ. Fairness cần xuất hiện ở:
- API gateway.
- Worker pool.
- DB connection pools.
- Shard routing.
- Background compaction/index jobs.
- Các downstream shared khác.

**Isolation là một thuộc tính của đường request, không phải một middleware duy nhất.**

## 14. Bulkhead pattern: tạo ranh giới chịu lỗi

**Bulkhead** mượn ý tưởng chia khoang tàu: một khoang ngập không khiến cả tàu ngập.

Trong SaaS NoSQL, bulkhead có thể là:
- Connection pool riêng cho BIG.
- Thread pool riêng cho report/ingest.
- Dedicated query coordinators.
- Tenant-aware queue partitioning.
- Dedicated cache namespace và memory budget.
- Dedicated background job scheduler.
- Cell/cluster riêng.
- Circuit breaker hoặc rate limit theo tenant/operation class.

### 14.1. Một circuit breaker dùng chung có thể gây hại

Nếu một global breaker mở vì tenant BIG liên tục timeout, mọi tenant có thể nhận lỗi mặc dù những shard khác khỏe.

Nên xem xét:
- Breaker theo **cell/shard/downstream**.
- Phân biệt lỗi theo operation type.
- Không gắn mọi tenant vào một semaphore/breaker chỉ vì tiện triển khai.
- Giới hạn số breaker labels/objects nếu tenant count rất lớn.
- Có fallback chỉ khi hợp đồng dữ liệu cho phép.

### 14.2. Shared connection pool

Giả sử API dùng pool 200 DB connections. Tenant BIG thực hiện 180 queries dài, còn 20 connection cho toàn bộ tenant khác.

Tách BIG sang một shard khác **không giải quyết** nếu API vẫn dùng chung pool 200. Có thể cần:
- Pool theo workload class/cell.
- Per-tenant concurrent query limit.
- Query timeouts/cancellation.
- Bulk scan sang batch pool.
- Admission control trước khi mượn connection.

Đặt **pool cho mỗi một trong 50.000 tenant** cũng không hợp lý; cần phân cấp: shared pooled classes, dedicated cho elephant, và quota ở logical tenant level.

## 15. Cache là tài nguyên chung dễ bị noisy neighbor

Một tenant có tập dữ liệu lớn có thể quét hàng triệu key và đẩy working set của tenant nhỏ ra khỏi cache.

~~~~text
Tenant SMALL:
  hot 10.000 keys, hit rate 95%

Tenant BIG:
  scan 5.000.000 distinct keys
  -> cache churn

Sau scan:
  SMALL hit rate giảm mạnh
  -> đọc storage nhiều hơn
  -> p99 tăng
~~~~

Giải pháp cần cân nhắc:
- Quota/cache partition cho workload lớn.
- Dedicated cache hoặc cache tier.
- Admission policy không đưa kết quả scan một lần vào hot cache.
- Per-tenant key prefix và instrumentation.
- TTL/eviction phù hợp.
- Limit query scans.
- Cache warmup và working set estimation.

### 15.1. Key namespace không phải memory isolation

~~~~text
cache:T-SMALL:...
cache:T-BIG:...
~~~~

Prefix giúp tìm/kiểm soát key và tránh collision, nhưng nếu mọi key dùng chung một eviction pool, BIG vẫn có thể đẩy dữ liệu SMALL khỏi cache.

### 15.2. Cache stampede sau khi tenant lớn được tách

Khi đổi placement/cell:
- Cache của BIG tại cell mới còn lạnh.
- Hàng nghìn request đồng thời cache miss.
- Database mới nhận burst đọc.
- Router có thể tạo retry vào cả cell cũ và mới nếu mapping chưa ổn.

Cần:
- Warmup có giới hạn.
- Request coalescing đối với hot keys.
- Gradual traffic shift.
- Giới hạn concurrency khi cache cold.
- Đo miss rate và backend saturation sau cutover.

**Migration “không downtime” vẫn có thể phá p99 nếu không tính cache warmup.**

## 16. Storage maintenance và background load

NoSQL không chỉ xử lý request trực tiếp. Storage engine còn chạy:
- WAL flush và checkpoint.
- Compaction/garbage collection.
- Index build/rebuild.
- TTL expiration/tombstone cleanup.
- Backup/snapshot.
- Anti-entropy/repair.
- Replica bootstrap.
- CDC/log shipping.
- Search refresh/segment merge.

Một tenant lớn có nhiều update/delete/TTL có thể tạo **write amplification** và I/O nền lớn dù QPS ở API đã giảm.

### 16.1. Tại sao p99 vẫn cao sau khi tạm dừng tenant BIG?

Giả sử BIG vừa thực hiện một đợt write/delete lớn:
- Frontend write QPS đã về 0.
- Compaction backlog vẫn cao.
- Tombstones còn trong SSTables.
- Index merge vẫn tiêu CPU/disk.
- Replica đang replay nhiều log.

Những tenant khác dùng chung đĩa/node vẫn bị chậm.

**Không đánh giá isolation bằng cách chỉ quan sát khoảng có request; phải đo thời kỳ backlog recovery.**

### 16.2. Giới hạn I/O nền

Các chiến lược tùy engine:
- Đặt compaction/repair budgets nếu được hỗ trợ.
- Dời job backup/import khỏi giờ cao điểm.
- Reserve storage headroom.
- Chia tenant BIG sang cell riêng nếu có maintenance độc lập.
- Giới hạn bulk deletes/updates theo batch có kiểm soát.
- Theo dõi backlog, file count, read/write amplification.
- Tránh chạy đồng thời resharding + index rebuild + backup trên cùng cell.

Không nên tự tắt compaction/repair vô thời hạn: có thể làm read amplification, disk pressure hoặc tính nhất quán/khả năng phục hồi tệ hơn.

## 17. Index, search và query fan-out giữa tenant

Một dataset chung có thể có index theo:

~~~~text
(tenantId, status, createdAt)
(tenantId, userId, createdAt)
(tenantId, roomId, day)
~~~~

Nếu tenant BIG có 100 triệu records, một index theo tenantId có thể vẫn giúp target phạm vi, nhưng truy vấn “tất cả pending trong 5 năm” có thể nặng và cạnh tranh với tenant nhỏ.

Cần phân biệt:
- Query targeted nhưng đọc rất nhiều dữ liệu.
- Query fan-out nhiều shards nhưng mỗi shard đọc ít.
- Query dùng global secondary index có chi phí/lag riêng.
- Query aggregation cần merge và memory lớn.
- Query bắt buộc cross-tenant/report có budget riêng.

### 17.1. Một tenant chia 16 buckets

Với:

~~~~text
PK = (tenantId, bucketId)
~~~~

Query biết tenantId nhưng không biết bucketId phải fan-out tới các bucket liên quan hoặc dùng projection.

~~~~text
Tenant BIG:
  Bucket 00 -> newest 20 candidates
  Bucket 01 -> newest 20 candidates
  ...
  Bucket 15 -> newest 20 candidates
                  |
                  v
           merge top 20 globally
~~~~

Đây là một cách triển khai top-k đơn giản khi local query và sort semantics cho phép; chi phí có thể lên tới 16 × 20 candidates trước merge. Pagination sau đó cần cursor/tie-breaker ổn định.

### 17.2. Read projection cho tenant-wide list

Có thể tách:
- **Source** partition theo (tenantId, bucketId) để ghi phân phối.
- **BookingsByUser** theo (tenantId, userId, month).
- **PendingByTenant** theo (tenantId, status, timeBucket, bucket).
- **RevenueDaily** là aggregate theo (tenantId, day).

~~~~mermaid
flowchart LR
    SRC[("Authoritative source")] --> OUT["Outbox / CDC"]
    OUT --> USER[("BookingsByUser")]
    OUT --> PEND[("PendingByTenant")]
    OUT --> REV[("RevenueDaily")]
~~~~

Nhưng read projections:
- Tăng write amplification và storage.
- Có replication/index lag.
- Có thể nhận event trùng/sai thứ tự.
- Cần eventId/version, idempotent consumer và reconciliation.
- Không được dùng projection stale làm **nguồn quyết định duy nhất** cho inventory/quota/payment.

### 17.3. Batch analytics phải dùng đường riêng khi cần

Một report quét hàng tỉ records có thể:
- Chạy trên replica/warehouse/lake phù hợp.
- Dùng time-window export hoặc CDC.
- Bị giới hạn thời gian, bytes, concurrency.
- Có freshness và consistency contract riêng.
- Không được làm thiếu DB connections cho interactive checkout.

**Phân luồng interactive và analytical workloads** thường quan trọng hơn việc chỉ thêm một index.

## 18. Isolation và transaction: đừng làm yếu bất biến để tăng throughput

Khi chia tenant BIG từ một partition thành nhiều buckets, các thao tác cần transaction có thể trở thành cross-partition.

Ví dụ một order cần:
- Reserve inventory của hai SKU.
- Ghi Order.
- Ghi OperationResult.
- Ghi OutboxEvent.

Nếu các bản ghi phân tán qua buckets, phải hỏi:
- Engine có multi-item/cross-shard transaction đúng phạm vi không?
- Có conditional update cho từng SKU không?
- Isolations chống oversell/lost update là gì?
- Commit outcome unknown xử lý ra sao?
- Có thể tái cấu trúc aggregate hoặc dùng reservation workflow không?

**Không được cho phép hai bucket tự xác nhận bán cùng món cuối chỉ vì muốn chia tải.**

### 18.1. Colocation theo business invariant

Một cách bảo vệ slot:

~~~~text
SlotKey = TENANT#T-BIG#ROOM#R-08#DAY#2026-12-01
~~~~

Một conditional write:
 
~~~~text
IF slot.status == FREE
THEN slot.status = RESERVED
     slot.bookingId = B-901
~~~~

Dù Order của tenant được sharded theo orderId, **SlotKey** có thể là điểm phân xử riêng cho invariant không đặt trùng slot.

Nếu một room/day cực nóng:
- Có thể phải chấp nhận contention tại điểm quyết định.
- Hoặc thiết kế quyền giữ slot theo các đơn vị nhỏ hơn nếu nghiệp vụ cho phép.
- Không tạo nhiều bản ghi “slot available” độc lập mà không có cơ chế ngăn double booking.

### 18.2. Cross-shard transactions có chi phí nhưng không bị cấm mặc định

Một số NoSQL hỗ trợ distributed transaction; chi phí có thể gồm:
- Coordination giữa shards.
- Two-phase commit hoặc protocol tương đương.
- Lock/conflict/abort.
- Timeout và unknown commit result.
- Phụ thuộc quorum của nhiều shards.
- p99 tăng khi một shard chậm.

Đừng suy rằng **cùng shard tự động có transaction**, cũng đừng suy **khác shard tuyệt đối không thể transaction**. Kiểm tra hợp đồng engine cụ thể.

### 18.3. Idempotency khi một tenant đổi cell

Nếu OP-101 đã commit ở CELL-A nhưng ACK mất; ngay sau đó tenant chuyển sang CELL-B:
- Retry OP-101 tới CELL-B có thể trông như thao tác mới nếu ledger chưa di chuyển.
- Nếu B chấp nhận mà không kiểm tra kết quả ở A, có thể tạo duplicate.
- Nếu A tiếp tục ghi, có thể tạo lịch sử phân nhánh.

Cần migrate **operation ledger, unique guards và commit history** đúng thứ tự; cutover phải có **fencing** và tra cứu được operation cũ.

## 19. Migration tenant lớn: không chỉ copy rows

Một kế hoạch chuyển BIG từ shared cell A sang dedicated cell B có thể gồm:

~~~~mermaid
flowchart TD
    S["ACTIVE on A"] --> P["PREPARING B"]
    P --> C["COPY SNAPSHOT"]
    C --> F["CATCH UP via CDC"]
    F --> Q["VERIFY parity"]
    Q --> X["FENCE A writes / CUTOVER"]
    X --> V["ACTIVE on B"]
    V --> R["RETIRE A after retention"]
~~~~

Đây là sơ đồ các giai đoạn khái niệm. Cách cutover cụ thể phải dựa trên khả năng database, replication protocol, transaction boundary và yêu cầu downtime của sản phẩm.

### 19.1. Giai đoạn chuẩn bị

- Tạo cell B với capacity và backup/replica policy phù hợp.
- Kiểm tra schema/index, TTL, data residency.
- Tạo routingVersion/ownership epoch mới.
- Cấu hình auth, encryption và observability đúng tenant.
- Xác định snapshot/CDC strategy.
- Dự phòng network/storage cho copy và dữ liệu tạm.

### 19.2. Snapshot và CDC

Một mô hình:
1. Ghi lại mốc snapshot đáng tin.
2. Copy dữ liệu tới B.
3. Song song thu nhận các thay đổi mới trên A.
4. Apply CDC theo ordering/version phù hợp.
5. Xử lý duplicate/out-of-order/delete/tombstone.
6. Chờ B bắt kịp checkpoint cần thiết.

**Snapshot + CDC không tự bảo đảm nhất quán nếu mốc snapshot và mốc bắt đầu CDC có gap.** Cần một phương pháp lấy checkpoint/snapshot có thể chứng minh không bỏ sót thay đổi.

### 19.3. Chỉ có một write authority trong cutover

Một chiến lược:
- A vẫn là authority cho tới mốc cutover.
- B nhận snapshot/CDC nhưng chưa chấp nhận writes độc lập.
- Khi B đạt điều kiện parity, hệ **fence A** ở epoch cũ.
- Router chuyển sang B ở epoch mới.
- B nhận writes và chịu trách nhiệm source of truth.
- A chỉ cho đọc/redirect/retention theo policy.

Nếu dùng dual-write để rút ngắn cutover, phải có cơ chế đồng bộ và khôi phục cụ thể khi một bên write thành công và bên kia thất bại. **Không tự xem hai PUT rời rạc là atomic.**

### 19.4. Những dữ liệu không được quên

Ngoài business rows còn có:
- OperationId/idempotency ledger.
- Unique constraint registry.
- Transaction/outbox records.
- Tombstones và deletion history.
- User/tenant metadata.
- Indexes, aggregates và materialized views.
- TTL/retention state.
- Sequence/version/epoch metadata.
- CDC checkpoints.
- Audit records và legal-hold flags khi áp dụng.

Nếu copy booking mà bỏ operation ledger, một retry sau cutover có thể tạo booking thứ hai.

### 19.5. Verify parity bằng bất biến, không chỉ row count

Row count bằng nhau chưa chắc:
- Amount/quantity đúng.
- Không mất update.
- Không có duplicate.
- Version/tombstone đủ mới.
- Unique constraints còn hiệu lực.
- Index read paths đã query-visible.
- CDC không có gap.

Nên đối soát:
- Counts và checksums theo bucket/time.
- Sum/aggregates có nguồn đối chứng.
- OperationId uniqueness.
- Sampled/full key-value compare tùy khả năng.
- Last-applied CDC checkpoint.
- Business invariants.
- Read/query behavior và p99 tại B.

### 19.6. Rollback không đơn giản khi B đã nhận write

Nếu B đã là authority và ghi thêm dữ liệu, “đổi router về A” có thể làm mất những write mới.

Rollback cần:
- Quyết định quyền sở hữu/epoch.
- Replay dữ liệu mới từ B sang A khi hỗ trợ.
- Fence B trước khi A ghi trở lại.
- Verify parity và transaction statuses.
- Không làm mất ACKed writes hoặc idempotency history.
- Có kế hoạch **forward fix** nếu rollback không còn an toàn.

Một migration có thể **không có rollback nhanh** sau mốc nào đó; phải nói rõ trước cutover.

## 20. Không nên promotion/demotion quá thường xuyên

Một tenant có burst theo ngày:
- Hôm nay vượt quota 10 phút.
- Ngày mai yên.
- Ngày kia lại vượt.

Nếu tự chuyển cell mỗi lần vượt:
- Chi phí copy rất lớn.
- Cache liên tục lạnh.
- Routing churn.
- Tăng rủi ro split brain/duplicate.
- Lãng phí tài nguyên tạm.

Cần một chính sách ổn định:
- Burst protection bằng quota/admission trước.
- Promote khi sustained pressure hoặc forecast có cơ sở.
- Hysteresis để tránh flapping.
- Capacity reservation đủ cho peak dự báo.
- Demote chỉ khi đáp ứng chính sách retention/SLO và chi phí di chuyển hợp lý.

### 20.1. Một policy minh họa

~~~~text
PROMOTE candidate:
  - >65% safe write capacity trong 7 ngày liên tiếp
  hoặc
  - ảnh hưởng p99 tenant khác >SLO 3 lần trong 30 ngày
  hoặc
  - yêu cầu residency/contract riêng.

DEMOTE candidate:
  - <25% safe capacity trong 60 ngày
  và
  - không có yêu cầu dedicated theo hợp đồng
  và
  - migration savings > migration/risk budget.
~~~~

**Các ngưỡng minh họa**, không phải best practice chung. Số ngày và tỷ lệ phải điều chỉnh theo dữ liệu/chi phí/rủi ro của sản phẩm.

## 21. SLO và error budget theo tenant

Nếu chỉ đo p99 toàn dịch vụ, tenant nhỏ có thể bị che khuất khi BIG chiếm phần lớn traffic.

Ví dụ:
- BIG phát 100.000 request, p99=80 ms.
- 100 tenant nhỏ, mỗi tenant 100 request, p99=2 s vì cùng một shard phụ.
- Toàn dịch vụ có thể vẫn hiện latency distribution tốt nếu BIG chiếm đa số.

Một SLO isolation phải trả lời:
- **Ai là đơn vị được bảo vệ?** Tenant, tier, cell, request class?
- **Đo trên request nào?** Interactive read, write, background batch?
- **So với baseline nào?** Khi noisy tenant vắng/đang burst.
- **Ngưỡng suy giảm nào chấp nhận?** p99 increase, error rate, queue wait?
- **Trong khoảng nào?** 1 phút, 1 giờ, 30 ngày?
- **Các tenant tiny có đủ samples để tính p99 không?**

### 21.1. SLI về blast radius

Một SLI minh họa:

\[
AffectedTenants =
\left|\left\{t : p99_t>SLO_t
\text{ trong incident}\right\}\right|
\]

Có thể đo thêm:
- Số tenant bị lỗi do một hot shard.
- Tenant-weighted success rate.
- Tỷ lệ tenant có p99 trong ngưỡng.
- Max number of tenants sharing an overloaded cell.
- Thời gian từ burst tới khi admission control có hiệu lực.
- Recovery time sau khi tenant BIG ngừng tải.

**Không dùng một chỉ số duy nhất thay cho cả performance lẫn correctness**. Một response nhanh nhưng trả sai tenant data là sự cố bảo mật nghiêm trọng, không phải SLO success.

### 21.2. Cardinality của metrics

Nếu có 200.000 tenant mà mỗi metric gắn:

~~~~text
tenantId
endpoint
status
shardId
operationType
region
~~~~

số series có thể bùng nổ, gây áp lực lên TSDB.

Một chiến lược:
- Metrics aggregate theo cell/tier/operation class.
- Per-tenant detailed metrics chỉ cho top-N/elephant tenants.
- On-demand tracing hoặc sampled logs với tenantId được kiểm soát.
- Heavy-hitter sketches/top-K để phát hiện tenant nóng.
- Audit logs riêng với kiểm soát PII và retention.
- Không dùng tenantId vô hạn như metric label cho mọi event.

**Cần quan sát tenant cụ thể mà không biến monitoring thành một noisy neighbor mới.**

## 22. Cost isolation và showback

Trong hệ shared, một tenant có thể tiêu tốn:
- Storage bytes và replica copies.
- Read/write capacity.
- Index write amplification.
- Cross-region transfer.
- Cache memory.
- Query CPU và memory.
- Backup/snapshot bytes.
- Compaction/repair/CDC.
- Search/analytics resources.

Nếu chỉ tính phí dựa trên số document, tenant có 1 triệu small rows và 50.000 update/s có thể tốn hơn tenant có 100 triệu cold rows.

### 22.1. Một cost model sơ bộ

\[
Cost_t \approx
c_rR_t+
c_wW_t+
c_sS_t+
c_nN_t+
c_bB_t+
c_qQ_t
\]

Trong đó:
- \(R_t,W_t\): read/write work theo đơn vị đo phù hợp.
- \(S_t\): replicated/indexed storage.
- \(N_t\): network/egress.
- \(B_t\): backup/maintenance work.
- \(Q_t\): scan/query CPU hoặc tương đương.

Các hệ số \(c_i\) là giá/chi phí nội bộ, không cố định giữa nhà cung cấp. Phải phân bổ overhead shared như metadata, standby capacity, compaction và backups để không đánh giá sai hiệu quả.

### 22.2. Dedicated tenant có thể đắt nhưng hợp lý

Chuyển BIG sang dedicated cell:
- Có thể tăng chi phí infrastructure riêng.
- Giảm tail latency và lỗi của 10.000 tenant khác.
- Giúp dự báo capacity.
- Giảm blast radius khi tenant BIG chạy job nặng.
- Hỗ trợ compliance/SLO có giá trị cao.

Quyết định cần so **chi phí incremental isolation** với **rủi ro SLO, revenue, support và vận hành** của mô hình shared.

## 23. Security và data isolation phải giữ nguyên khi tách tenant

Tenant migration là một thời điểm rủi ro security:
- Copy nhầm tenantId.
- Router chuyển sang namespace của tenant khác.
- API dùng key từ client chưa xác thực.
- Backup mới thiếu encryption/retention policy.
- Metrics/logs rò data hoặc tenant identifiers.
- Permissions ở cell mới chưa tương đương.
- Temporary migration credentials không được thu hồi.
- Data ở region mới vi phạm residency.

### 23.1. Tenant authorization ở mọi đường đi

Quy trình đúng về nguyên tắc:
1. Xác thực caller.
2. Xác định tenant membership/role.
3. Lấy tenantId đáng tin từ auth context.
4. Tra routing catalog.
5. Gửi query với tenant guard/namespace.
6. Enforce authorization ở storage/data access layer khi có thể.
7. Audit hành động nhạy cảm và migration.

**Shard location không phải credential**. Biết cellId hoặc partition key không được cho phép truy cập trái quyền.

### 23.2. Data residency

Đưa BIG sang dedicated cluster tại region khác phải xét:
- Source data.
- Read replicas và backups.
- WAL/CDC/change streams.
- Search indexes.
- Object storage exports.
- Observability logs và support tools.
- Disaster recovery.

Chỉ cấu hình **homeRegion=VN** trong catalog mà vẫn copy backup tới nơi không được phép sẽ không thỏa yêu cầu.

### 23.3. Xóa tenant sau khi chuyển

Khi retire cell cũ:
- Chắc chắn cell mới đã có dữ liệu được ACK theo chính sách.
- Giữ idempotency history cần thiết trong retention window.
- Bảo vệ outstanding retries/old CDC consumers.
- Xóa/cấp quyền backup, snapshots và caches đúng quy trình.
- Xác định legal hold và audit.
- Không xóa quá sớm trước khi có restore drill.

**Data migration completed** và **data erasure completed** là hai trạng thái vận hành khác nhau.

## 24. Cụ thể theo các hệ NoSQL

Không nên áp cùng công thức cho mọi engine vì **partitioning và sharding semantics khác nhau**.

### 24.1. MongoDB

Trong một MongoDB sharded cluster:
- Một collection có shard key/routing và các chunk/range được phân bổ tới shards theo cơ chế của phiên bản.
- Compound/hashed/ranged key ảnh hưởng targeted queries, data distribution và khả năng xuất hiện hotspot.
- TenantId đơn làm shard key có thể không đủ cho mega-tenant.
- Đổi shard key/resharding cần quan tâm unique indexes, migrations, transaction semantics và operationId.
- Một truy vấn tenant-wide có thể target một tập shard/range tùy key và query shape, không tự là một request một shard.

Một hướng thiết kế có thể dùng khóa ghép tenant và một thành phần phân phối. Không tự suy **mọi document cùng tenant được đặt hoàn toàn cùng shard** khi dùng compound key và chunk splitting.

Đo:
- Per-shard bytes/QPS.
- Hot chunks/ranges.
- Query targeting/explain.
- Index effectiveness.
- Migration/rebalance load.
- Transaction p99 và retry/abort rates.

### 24.2. DynamoDB

Ở DynamoDB:
- Partition key của table quyết định phần quan trọng của data distribution.
- Một giá trị partition key quá nóng có thể gặp giới hạn/bottleneck theo workload và cơ chế dịch vụ.
- Sort key giúp query theo range **trong phạm vi partition-key value**, không tự chia một logical key thành nhiều giá trị.
- Application write sharding có thể dùng synthetic bucket suffix.
- GSI có khóa và load distribution riêng; một GSI partition key nóng cũng có thể trở thành nút cổ chai.
- Managed adaptive capacity có thể hỗ trợ một số trường hợp, nhưng không được giả định mọi hot key hoặc strict atomic item được tách vô hạn.
- Conditional UpdateItem/TransactWriteItems và idempotency window là các vấn đề riêng, không giải bằng suffix key ngẫu nhiên.

Ví dụ logical key có thể là:

~~~~text
PK = TENANT#T-BIG#BUCKET#07
SK = ORDER#2026-11-14T09:00:00Z#O-901
~~~~

Query toàn tenant cần biết danh sách buckets hoặc sử dụng read model/index phù hợp.

### 24.3. Cassandra

Trong Cassandra:
- Partition key được hash thành token để quyết định placement.
- Clustering columns giúp sắp xếp records **bên trong partition**, không tự phân tải hot partition sang nhiều token.
- Một partition key tenantId khổng lồ có thể tạo áp lực đọc/ghi/tombstone.
- Một thiết kế thường xét là partition key (tenantId, timeBucket, hashBucket) với clustering (eventTime,eventId).
- Nhiều bảng denormalized phục vụ query-first access patterns có thể cần cho user/room/status views.
- Consistency level và LWT/conditional semantics không giống multi-partition ACID transaction chung.

Cần đo partition sizes, SSTables/tombstones, compaction/repair load, per-node skew và read p99.

### 24.4. HBase

Trong HBase:
- Row keys được sắp thứ tự trong các region ranges; sequential keys có thể tạo tail hotspot.
- Salt/hash prefix và pre-splitting có thể giúp phân phối writes.
- Một tenantId prefix không có salt có thể tập trung dữ liệu theo region.
- Tách tenant bằng prefix+bucket có thể phá locality scan; phải xây read/query strategy.
- WAL, RegionServer, region transitions và HDFS/cross-cluster replication ảnh hưởng operational isolation.

Một tenant riêng có thể phù hợp với table/namespace/cluster policy nhưng **namespace alone không đồng nghĩa dedicated CPU/IO**.

### 24.5. Redis Cluster

Redis Cluster phân phối key qua hash slots. Hash tags cho phép một số key cùng slot để hỗ trợ operations cần colocated keys:

~~~~text
order:{T-BIG}:O-901
stock:{T-BIG}:SKU-9
~~~~

Nhưng nếu mọi key cùng tag **{T-BIG}**, tenant lớn có thể dồn vào một slot/node.

Dùng tag theo bucket:

~~~~text
order:{T-BIG#07}:O-901
~~~~

có thể phân phối giữa slots, nhưng nhiều key ở buckets khác nhau **không cùng slot** để chạy multi-key atomic scripts/transactions theo yêu cầu cluster. Cần xác định invariant và consistency trước khi đổi tag.

Redis cache key prefixes cũng không tự phân bổ memory eviction budget theo tenant.

### 24.6. OpenSearch/Elasticsearch

Custom routing theo tenant có thể giảm shard fan-out cho tenant nhỏ, nhưng elephant tenant có thể làm một search shard nóng hoặc rất lớn. Một số phiên bản/tính năng có cách routing partitioned hoặc index design thích hợp; cần xem hợp đồng cụ thể.

Các phương án:
- Routing/index theo tier hoặc tenant nhóm.
- Dedicated index cho elephant tenant khi hợp lý.
- Shard sizing và replica count.
- Query/indexing backpressure.
- Tách analytic queries khỏi interactive search.
- Refresh/merge/backfill budgets.

**Không coi index riêng cho mỗi tenant là mặc định tốt khi có hàng trăm nghìn tenant**: overhead về shards/metadata/cluster state có thể rất lớn.

## 25. Một thiết kế tham chiếu: shared cells và elephant routing

Một kiến trúc nhiều tầng:

~~~~mermaid
flowchart TD
    CLIENT["Clients"] --> EDGE["API gateway + auth"]
    EDGE --> Q["Tenant quota / admission"]
    Q --> ROUTER["Placement router"]
    ROUTER --> CAT["Routing catalog"]
    ROUTER --> SMALL["Shared cells: many small tenants"]
    ROUTER --> BIG["Dedicated / bucketed big-tenant cell"]
    SMALL --> O1["Outbox / CDC"]
    BIG --> O2["Outbox / CDC"]
    O1 --> READ["Read projections"]
    O2 --> READ
    ROUTER --> STATUS["Operation status / reconciliation"]
~~~~

Các nguyên tắc:
- **Authenticated tenantId** được dùng để lấy policy.
- **Quota/admission** áp dụng trước khi request chiếm tài nguyên đắt.
- Routing theo **placement và routingVersion**.
- Dữ liệu source có **single authority hoặc contract đa vùng rõ**.
- Transaction/conditional guard giữ invariant.
- Outbox/CDC xây read models có freshness SLO riêng.
- OperationId ổn định qua retry và migration.
- Shared services có **bulkheads và budgets**.
- Monitoring tách per-cell/per-tier và top heavy tenants.

### 25.1. Control plane không nên là single point of global outage

Nếu mỗi request phải gọi routing catalog qua mạng:
- Catalog chậm có thể làm mọi tenant chậm.
- Catalog outage có thể làm mọi request lỗi.
- Một migration tenant BIG có thể gây traffic metadata tăng.

Có thể dùng:
- Cached catalog entries với version/TTL phù hợp.
- Push invalidations/change notifications.
- Preloaded route map cho cells.
- Fail-safe behavior cho stale ownership.
- Replicated control plane với khôi phục.
- Explicit redirect từ old cell khi mapping đã đổi.

**Cache route để tăng availability phải đi cùng fencing ở data plane**, nếu không stale cache có thể gây ghi vào authority cũ.

### 25.2. Cách xử lý khi một cell hỏng

Nếu CELL-17 của BIG hỏng:
- Không nên mở global circuit breaker chặn SMALL tenants.
- Router phải giới hạn retries tới CELL-17.
- Jobs cho BIG bị queue/reject theo contract.
- SMALL cells tiếp tục phục vụ.
- Alert/report xác định tenant và blast radius đúng.
- Recovery của BIG có thể consume shared network; cần repair/backfill budget.

Nếu một shared cell chứa 10.000 tenant hỏng, blast radius lớn hơn. Cần lựa chọn **cell size** theo khả năng vận hành và SLO, không chỉ theo hiệu quả sử dụng tài nguyên.

## 26. Fault injection để kiểm chứng blast radius

Không thể chứng minh isolation chỉ bằng benchmark một tenant hoặc khi cluster khỏe.

### 26.1. Ma trận tình huống

| Sự cố | Can thiệp trong môi trường thử | Điều cần quan sát |
| --- | --- | --- |
| Elephant burst writes | BIG tăng 10× write QPS | SMALL p99 và error không vượt ngân sách |
| Heavy read scan | BIG chạy query dài | Query limiter, CPU/IO, cache hit của SMALL |
| One hot partition | Dồn writes vào một key | Phân biệt key-level và node-level bottleneck |
| Heavy deletes/TTL | BIG xóa nhiều dữ liệu | Compaction backlog và ảnh hưởng kéo dài |
| Index rebuild | Pause/rebuild projection BIG | Không làm query interactive tenant khác nghẽn |
| Cache churn | BIG quét hàng triệu key | SMALL hit rate và source read spikes |
| Pool exhaustion | BIG mở nhiều queries dài | Bulkhead giới hạn concurrent |
| Shared queue flood | BIG enqueue hàng trăm nghìn jobs | SMALL job wait time/fairness |
| Tenant promotion | Migrate BIG shared → dedicated | Không duplicate/missing, p99 SMALL cải thiện |
| Router stale | Giữ instance dùng routingVersion cũ | Old authority phải fence/redirect |
| Lost write ACK | Commit xong rồi mất response | Same operationId không tạo effect trùng |
| Cell failure | Kill BIG cell | SMALL cells tiếp tục đúng contract |
| Network partition | BIG cell mất kết nối catalog/source | Không giả vờ commit khi thiếu authority |
| CDC lag | Pause CDC 15 phút | Projection staleness có cảnh báo, không sai checkout |
| Replica recovery | BIG cell bootstrap từ snapshot | Bảo vệ writes đã ACK và retention |
| Noisy observability | Bật per-tenant labels quá nhiều | Monitoring không hết bộ nhớ |

### 26.2. Không chỉ đo BIG thành công hay không

Một benchmark isolation phải có **control tenants**:
- SMALL-A trong cùng shared cell.
- SMALL-B ở cell khác.
- MEDIUM-C có workload tương tự.
- BIG tenant đang gây tải.

Ghi:
- p50/p95/p99 và error/timeout rate của từng nhóm.
- Shard QPS/CPU/IO/network.
- Queue wait và admission rejections.
- Cache hit/miss.
- Compaction/repair backlog.
- Index/search freshness.
- Business invariant violations.
- Recovery latency sau khi BIG ngừng burst.

Mục tiêu là đo **ảnh hưởng gián tiếp**, không chỉ throughput tối đa của tenant BIG.

### 26.3. Đo baseline và delta

Ví dụ giả định:

| Chỉ số | Trước burst | Trong burst không isolation | Trong burst có guardrails |
| --- | ---: | ---: | ---: |
| SMALL p99 read | 70 ms | 2.100 ms | 110 ms |
| SMALL timeout rate | 0,1% | 8,0% | 0,4% |
| BIG accepted writes/s | 8.000 | 30.000 offered, nhiều timeout | 12.000 accepted, phần còn lại throttled |
| Shard max/avg load | 1,4× | 6,8× | 2,1× |
| Oldest shared queue age | 0,2 s | 45 s | 1,3 s |

**Toàn bộ số liệu minh họa.** Việc BIG bị throttled có thể là **kết quả chủ động giữ SLO**; hệ phải trả mã lỗi/thông báo retry rõ ràng và không tuyên bố mọi request đã được commit.

### 26.4. Kiểm chứng tính đúng khi retry throttled requests

Một request nhận 429/503 trước khi được thực thi có thể được retry theo hợp đồng. Nhưng request timeout **sau khi đã gửi write vào DB** có thể mang kết quả UNKNOWN.

Cần phân biệt:
- **Rejected before execution**.
- **Condition failed**.
- **Accepted but queued**.
- **Committed**.
- **Timeout/UNKNOWN**.

Không dùng cùng một chiến lược retry mù cho cả năm trạng thái, nhất là lệnh increment, debit hoặc tạo booking.

## 27. Runbook khi tenant lớn làm tenant khác chậm

### Bước 1 — Xác định blast radius

- Những tenant/tier/cell nào bị ảnh hưởng?
- API nào: read, write, report, import hay search?
- p99, timeout, queue wait tăng vào thời điểm nào?
- Có một tenant/workload thay đổi đột ngột không?
- Các tenant ở cell khác có bình thường không?

### Bước 2 — Tìm tài nguyên chung bị nghẽn

- Shard/node CPU, disk IO, compaction?
- Một partition key nóng?
- Router fan-out/merge memory?
- Connection pool/thread pool?
- Cache churn?
- Shared job queue?
- Auth/control plane/metadata service?
- Cross-region network/replication?

### Bước 3 — Bảo vệ tenant còn lại ngay

Tùy contract:
- Giới hạn concurrent BIG queries.
- Throttle write/read bursts ở edge.
- Tạm dừng/giảm tốc batch import, backup, report.
- Ưu tiên interactive requests.
- Tách connection pool/worker lane.
- Hạn chế retry storm.
- Dùng circuit breaker theo cell thay vì global.

**Không được tắt bỏ một transaction đã commit rồi báo nghiệp vụ thất bại nếu outcome còn UNKNOWN.** Khi điều tiết, cần phân biệt trạng thái request trước/sau khi đi tới storage.

### Bước 4 — Giải pháp cấu trúc

- Nếu key quá nóng: xem bucket/salt hoặc thiết kế aggregate khác.
- Nếu physical shard nóng nhưng các key nhỏ: rebalance/placement.
- Nếu tenant scan nhiều: query projection và job isolation.
- Nếu dedicated cần thiết: promote tenant sang cell riêng.
- Nếu compaction I/O nền: tune budgets, retention, capacity.
- Nếu index/GSI hotspot: đổi access path hoặc index key.
- Nếu shared gateway nghẽn: bulkhead và quota tại edge.

### Bước 5 — Migration có kiểm chứng

- Snapshot + CDC checkpoint.
- Ownership epoch/fencing.
- Operation ledger/unique guard.
- Auth and residency parity.
- Verify data/checksums/invariants.
- Gradual cutover/cache warmup.
- Rollback/forward-fix decision.
- Monitor old/new cell cùng lúc.

### Bước 6 — Chốt incident

- Có bao nhiêu tenant bị tác động và trong bao lâu?
- Correctness/security có bị vi phạm không?
- BIG bị throttled theo đúng hợp đồng không?
- Queues/compaction backlog có trở về ngưỡng?
- Headroom cho peak và recovery còn đủ không?
- Có bổ sung per-tenant SLO, tracing và load test không?

## 28. Những nhầm lẫn dễ dẫn đến sự cố

1. **“Tenant có nhiều rows là noisy neighbor.”** Chưa chắc; phải đo tài nguyên gây nhiễu.
2. **“Cardinality tenantId cao nên writes đều.”** Elephant tenant có thể chiếm phần lớn traffic.
3. **“Hash tenantId chia tải của một tenant.”** Một tenantId vẫn có thể là một logical key.
4. **“Thêm node luôn chia hot key.”** Không nếu atomic/partition boundary không thể phân rã.
5. **“Cứ thêm bucket là mọi query nhanh hơn.”** Tenant-wide queries có thể fan-out nhiều hơn.
6. **“Chia time bucket là hết current write hotspot.”** Current time window vẫn có thể nhận mọi writes.
7. **“Random bucket mỗi retry cũng được.”** Có thể tạo duplicate effect.
8. **“Đổi 16 → 32 buckets chỉ là sửa config.”** Cần version routing và migration.
9. **“Có shard riêng là không còn noisy neighbor.”** API, cache, worker và network vẫn có thể chung.
10. **“Namespace riêng là dedicated compute.”** Không nhất thiết.
11. **“Cache prefix theo tenant bảo đảm memory isolation.”** Shared eviction vẫn có thể bị churn.
12. **“Rate limit QPS đủ cho query nặng.”** Còn cần bytes scanned, CPU, in-flight caps.
13. **“Semaphore trong một JVM là quota toàn hệ.”** Nhiều instances làm vượt quota global.
14. **“Mọi job vào một FIFO queue vẫn công bằng.”** Burst lớn có thể chặn tenant nhỏ.
15. **“Circuit breaker global là an toàn nhất.”** Có thể làm lan sự cố từ một cell sang tất cả.
16. **“Tăng cache size sẽ chắc chắn hết chậm.”** Nếu scan liên tục, cache churn vẫn xảy ra.
17. **“Tách tenant rồi là khỏi cần quota.”** Dedicated cell cũng có finite capacity và external dependencies.
18. **“Một physical shard chứa một tenant thì transaction đa item tự atomic.”** Scope do engine quyết định.
19. **“Nhiều bucket tự giữ global inventory nonnegative.”** Cần conditional/transaction/escrow.
20. **“GSI/read projection mới ngay sau source commit.”** Có eventual lag.
21. **“Thấy bản ghi chưa có ở cell mới nghĩa write cũ chưa commit.”** CDC có thể chậm.
22. **“Dual-write hai cluster là một transaction.”** Lỗi giữa hai write gây lệch.
23. **“TTL router cache là fencing.”** Stale worker có thể hoạt động sau cutover.
24. **“Copy business rows là đủ.”** Cần ledger, tombstone, outbox, versions và metadata.
25. **“Row count bằng nhau chứng minh migration đúng.”** Cần kiểm tra version/consistency/invariants.
26. **“Rollback chỉ cần đổi route về cell cũ.”** Dữ liệu mới ở cell mới có thể mất.
27. **“Routing key chứa tenantId thì không thể rò dữ liệu.”** Authorization phải enforce riêng.
28. **“HomeRegion trong catalog tự đáp ứng residency.”** Backups/logs/replicas cũng phải kiểm tra.
29. **“Dedicated index cho mọi tenant càng tốt.”** Metadata/shard overhead có thể khổng lồ.
30. **“Chỉ đo p99 toàn hệ là đủ.”** Tenant nhỏ có thể bị che khuất bởi tenant lớn.
31. **“Gắn tenantId vào mọi metric label là tốt.”** Có thể làm monitoring cardinality bùng nổ.
32. **“Throttling là lỗi cần tránh mọi giá.”** Có thể là cơ chế giữ isolation theo hợp đồng.
33. **“Timeout nghĩa database chưa chạy.”** Commit ACK có thể mất.
34. **“Auto-rebalance luôn chữa được hotspot.”** Cần xem granularity, split speed và ongoing load.
35. **“Một lần benchmark uniform đủ để chọn placement.”** Tải thực có skew, bursts và recovery.
36. **“Sau khi dừng tenant BIG là hết ảnh hưởng ngay.”** Compaction/repair/index backlog còn kéo dài.

## 29. Bài tập thực hành: tách elephant tenant trong SaaS

Một nền tảng quản lý đơn hàng dùng Java 21 và NoSQL có:
- 50.000 tenant, 200 triệu orders.
- **40.000 read/s** và **25.000 write/s** giờ bình thường.
- Tenant BIG chiếm **30% writes**, chỉ 3% reads, 45% bytes dữ liệu nóng.
- 12 logical shards, mỗi shard có replica theo hợp đồng của engine.
- Shared gateway/API workers, shared DB connection pools và shared Redis cache.
- Tenant BIG có job import 2 giờ mỗi ngày.
- Tenant nhỏ cần p99 đọc dưới 150 ms; BIG có SLO write riêng.
- Source lưu Order và OperationResult, search/read model cập nhật async.
- Một transaction đặt hàng phải giữ bất biến inventory và chống duplicate theo operationId.
- Có thể tách BIG thành 16 buckets hoặc dedicated cell.

### Phần A — Xác định vấn đề

Giả sử trong 25.000 write/s có 30% đến từ BIG:

\[
25.000\times0{,}30=7.500\text{ write/s}
\]

1. Nếu key=tenantId, vì sao 7.500 write/s có thể dồn vào một logical partition?
2. Nếu tổng CPU cluster còn 55%, tại sao p99 của những tenant cùng shard vẫn có thể vượt SLO?
3. Cần thu thêm metrics nào để phân biệt **hot key, hot physical shard, cache churn và connection pool exhaustion**?

### Phần B — Tính buckets

Giả sử benchmark cho một logical partition ngưỡng bền vững 3.000 write/s và cần headroom 30%.

Công suất mục tiêu:

\[
3.000\times0{,}70=2.100\text{ write/s}
\]

Số bucket tối thiểu lý tưởng:

\[
\lceil7.500/2.100\rceil=4
\]

Giải thích vì sao **4 chỉ là cận dưới lý tưởng**, 8 hoặc 16 buckets có thể được thử trong benchmark, và vì sao quá nhiều bucket tăng chi phí list/search toàn tenant.

### Phần C — Chọn phương án

So sánh:
1. TenantId nguyên bản.
2. (tenantId, hash(orderId)%16).
3. Dedicated physical shard.
4. Dedicated cell/cluster.
5. Source theo orderId và read projection theo tenant/time.

Lập bảng về write distribution, read fan-out, transaction locality, query latency, migration cost, operational isolation và expected blast radius.

### Phần D — Thiết kế per-tenant admission

Tenant BIG chạy import 30.000 writes/s trong 10 phút, nhưng service chỉ muốn chấp nhận 10.000 writes/s với burst allowance rõ.

Thiết kế:
- Token bucket rate/capacity.
- Concurrency cap.
- Queue deadline và max backlog.
- Priority giữa checkout và import.
- Response 429/503/202 có ngữ nghĩa khác nhau thế nào?
- Cách giữ operationId qua retry và tránh duplicate effects.

### Phần E — Di chuyển BIG sang cell riêng

Mô tả state machine:

~~~~text
ACTIVE_A
-> PREPARE_B
-> SNAPSHOT_COPY
-> CDC_CATCHUP
-> VERIFY
-> FENCE_A
-> CUTOVER_B
-> ACTIVE_B
-> RETIRE_A
~~~~

Với mỗi bước, nêu:
- Source of truth hiện tại.
- RoutingVersion/ownership epoch.
- CDC checkpoint.
- Điều kiện abort/rollback.
- Cách xử lý old workers/stale caches.
- Dữ liệu nào ngoài Order phải được migrate.
- Metric nào phải đạt trước khi tiếp tục.

### Phần F — Đường truy vấn sau chia buckets

Nếu tenant BIG có 16 buckets:
- Tính số bucket cần query để liệt kê 20 order mới nhất theo tenant nếu không có index phụ.
- Thiết kế merge top-k và cursor ổn định.
- Đề xuất BookingsByUser/OrdersByStatus/RevenueDaily projections.
- Nêu freshness SLO và lý do checkout không thể tin projection stale.

### Phần G — Java và routing ổn định

Viết một helper tạo bucket từ stableOrderId, có routingVersion. Giải thích:
- Retry cùng operationId nhưng nhận ACK loss.
- Một service dùng routingVersion=11 khi hệ đã chuyển 12.
- Đổi 16 → 32 buckets.
- Stale writer bị fence thế nào.
- Một idempotency ledger chưa catch up gây nguy cơ gì.

### Phần H — Data isolation và cost

Tenant BIG được cấp dedicated region khác. Kiểm tra:
- Authorization và tenant-scoped query.
- Encryption và migration credentials.
- Replicas/backups/logs/CDC đúng residency policy.
- Cost allocation theo storage, write I/O, index, backup, network.
- Kế hoạch retire dữ liệu cũ và giữ audit.
- Vì sao tenantId trong key không tự bảo đảm security isolation.

### Phần I — Fault injection

Thiết kế ít nhất tám test:
1. BIG burst 10× traffic.
2. BIG chạy full-tenant scan.
3. BIG gây cache churn.
4. Worker queue bị BIG flood.
5. Compaction/index backlog sau import.
6. Tenant promotion giữa lúc writes đang diễn ra.
7. Old router tiếp tục dùng mapping cũ.
8. ACK mất sau commit.
9. CELL-B chết sau cutover.
10. BIG chạy report khi SMALL checkout peak.

Với từng test, đưa ra **SLO tenant nhỏ, blast radius target, nguồn truth, invariant và tiêu chí pass/fail**.

### Hướng giải

Thiết kế hợp lý có thể giữ **đa số tenant trong shared cells** với quota/admission và fairness, còn tenant BIG được **bucketed hoặc promoted sang dedicated cell** khi điều kiện thực tế yêu cầu. Nguồn quyết định inventory/order phải giữ **unique/conditional guard và operation ledger**; các read projections theo user/status/time có thể eventual. Router phải version hóa placement, cell cũ bị fence khi cutover, và migration cần snapshot+CDC+verification. Mọi đường API/cache/worker/background jobs phải có resource budgets để hạn chế noisy neighbor. Quan sát phải tách per-cell, per-tier và top elephant tenant, đo cả **affected tenants và thời gian recovery**.

## 30. Checklist trước khi đưa tenant isolation vào production

1. **TenantId được xác thực, không chỉ lấy từ header client?**
2. **Đã phân biệt storage/read/write/concurrency elephant?**
3. **Đã có per-key và per-shard QPS/bytes/IO metrics?**
4. **Có đo p99 theo tier/cell và những tenant control không?**
5. **Logical hot key có thể split theo engine không?**
6. **Bucket key có deterministic và idempotent qua retry không?**
7. **Bucket count/hash/routing version có được giữ ổn định?**
8. **Queries tenant-wide có fan-out/cursor budget rõ?**
9. **Có read projection/index phục vụ access pattern mâu thuẫn?**
10. **Có tách nguồn truth khỏi index/cache eventual?**
11. **Các transaction/invariant còn đúng khi cross-bucket?**
12. **Có chống double charge/order khi commit ACK mất?**
13. **Có per-tenant admission, concurrency và query cost limits?**
14. **Có worker fairness, queue caps và retry budgets?**
15. **Cache có quota/admission hoặc dedicated policy cho elephant?**
16. **Connection pools/thread pools có bulkhead theo workload class?**
17. **Background repair/compaction/index/backup có capacity budgets?**
18. **Dedicated tenant có thật sự giảm blast radius end-to-end?**
19. **Routing catalog có replication/cache và ownership fencing?**
20. **Migration có snapshot+CDC checkpoint không gap?**
21. **Có verify operation ledger, outbox, tombstone và indexes?**
22. **Có kế hoạch rollback/forward fix sau B nhận write?**
23. **Có auth/encryption/residency parity ở cell mới?**
24. **Có quan sát tenant count mà không bùng nổ metric cardinality?**
25. **Có runbook khi một tenant làm nhiều tenant khác chậm?**
26. **Có fault injection gồm burst, cache churn, cutover và cell failure?**
27. **Có cost/showback để đánh giá dedicated vs shared?**
28. **Có hysteresis tránh promote/demote liên tục?**
29. **Có headroom cho peak, failover, repair và cache warmup?**
30. **Có tiêu chí xác nhận isolation bằng SLO/correctness, không chỉ CPU?**

**Kết luận:** Tách tenant lớn trong NoSQL là bài toán **định tuyến dữ liệu lẫn quản trị tài nguyên**, không chỉ đổi shard key hoặc thêm node. Một elephant tenant có thể cần **hash/time buckets, dedicated shard/cell hoặc read projections**, nhưng để giới hạn ảnh hưởng tới tenant khác còn cần **admission control, per-tenant quotas, fair scheduling, connection/cache bulkheads, maintenance budgets và SLO theo tenant**. Việc migration phải giữ **một write authority, routingVersion/fencing, operationId/idempotency, dữ liệu CDC không gap và các bất biến giao dịch**. Hãy chọn mức isolation bằng dữ liệu **skew và p99 thực tế**, kiểm chứng với **burst, crash, cutover và recovery**, và luôn đo **bao nhiêu tenant khác bị ảnh hưởng**, thay vì chỉ đo tenant lớn chạy nhanh đến đâu.
