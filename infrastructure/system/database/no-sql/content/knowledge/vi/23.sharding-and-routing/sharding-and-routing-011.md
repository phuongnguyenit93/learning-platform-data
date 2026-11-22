# Phân mảnh theo tenant và tenant có kích thước chênh lệch lớn

Một ứng dụng SaaS nhiều khách hàng (multi-tenant) thường bắt đầu với mô hình đơn giản: mỗi bản ghi có trường `tenantId`, và hệ thống chia dữ liệu theo `tenantId`. Cách này thuận tiện vì hầu hết truy vấn đều nằm trong một khách hàng, có thể gom dữ liệu liên quan và giảm truy vấn xuyên shard.

Nhưng khi quy mô phát triển, các tenant hiếm khi có kích thước hoặc tải giống nhau. Một doanh nghiệp chỉ lưu vài trăm hóa đơn mỗi tháng; một doanh nghiệp khác có hàng trăm triệu sự kiện, hàng nghìn người dùng đồng thời và các chiến dịch ghi theo đợt. Nếu mỗi `tenantId` được đặt nguyên vẹn trong một partition/shard, **một tenant rất lớn có thể chiếm quá nhiều dung lượng hoặc tạo hot partition**, dù tổng số tenant được phân bố đều.

Vấn đề thiết kế vì vậy không chỉ là “hash `tenantId` sang shard nào” mà là:

- Đơn vị nào cần được đặt cùng nhau để đọc và ghi hiệu quả?
- **Tenant nhỏ, tenant vừa và tenant cực lớn** nên được phân bổ tài nguyên khác nhau thế nào?
- Khi một tenant lớn dần, có thể **chia nhỏ dữ liệu bên trong tenant** mà không làm mất ranh giới bảo mật và tính đúng đắn không?
- Router tìm đúng nơi chứa dữ liệu khi tenant được chuyển cụm, đổi vùng hoặc thêm bucket ra sao?
- Transaction, unique constraints, truy vấn theo thời gian và phép đếm trên toàn tenant bị ảnh hưởng thế nào?
- Migration diễn ra thế nào để không mất hoặc nhân đôi những ghi đã ACK?

Bài học này thuộc chương **Phân mảnh và định tuyến** của Database No SQL. Chúng ta sẽ đi từ mô hình tải lệch, lựa chọn partition key, virtual buckets, tenant directory và chiến lược cô lập tenant lớn đến ví dụ NoSQL, mã Java, quy trình di chuyển trực tuyến và kiểm thử vận hành.

> **Lưu ý:** `partition`, `shard`, `partition key`, `tenant database` và `routing` không có cùng nghĩa trong mọi sản phẩm. MongoDB, DynamoDB, Cosmos DB for NoSQL, Cassandra/ScyllaDB và các hệ khác có cách tạo logical/physical partitions, giới hạn kích thước, transaction scope, rebalance và adaptive capacity khác nhau. Các con số và schema sau đây mang tính minh họa; trước khi triển khai cần xác minh version, topology, SKU, quota và contract của chính sản phẩm.

## 1. Làm rõ các khái niệm

**Tenant** là đơn vị khách hàng hoặc tổ chức có ranh giới dữ liệu, quyền truy cập, cấu hình, vòng đời và đôi khi cả vùng lưu trữ riêng. Nó có thể là công ty, workspace hoặc account doanh nghiệp.

**Multi-tenant data model** là cách nhiều tenant cùng sử dụng hạ tầng nhưng vẫn được tách biệt về mặt logic và, khi cần, về tài nguyên hoặc vật lý.

**Partition key** là giá trị mà cơ sở dữ liệu hoặc ứng dụng dùng để xác định nhóm dữ liệu/đơn vị lưu trữ và phân phối tải.

**Logical partition** là nhóm dữ liệu theo một khóa logic ở những hệ có khái niệm này. Một logical partition không nhất thiết bằng một physical partition.

**Shard/physical partition** là đơn vị lưu trữ và phục vụ tải trên hạ tầng; một shard có thể chứa nhiều tenant hoặc nhiều logical buckets.

**Tenant routing** là việc tìm đúng cụm, database, shard và bucket cho request thuộc tenant nào.

**Whale tenant** là tenant lớn bất thường so với phần còn lại; cần phân biệt “lớn về dữ liệu” với “nóng về lượng truy cập”.

**Noisy neighbor** là tình trạng một tenant dùng quá nhiều CPU, IO, memory, connections hay capacity khiến tenant khác bị ảnh hưởng dù dữ liệu được phân tách logic.

### 1.1. Ba lớp định tuyến không nên trộn

~~~mermaid
flowchart TD
    REQ["Request đã xác thực tenant"] --> DIR["Tenant Directory / Placement policy"]
    DIR --> POOL["Chọn cluster hoặc nhóm shard"]
    POOL --> BUCKET["Tính bucket/partition theo entity"]
    BUCKET --> DB["Đọc/ghi trên owner có thẩm quyền"]
~~~

Tenant directory có thể quyết định **cluster hoặc region**; bucket function quyết định **phần dữ liệu bên trong tenant**; database partitioner quyết định **physical placement**. Đặt cả ba trách nhiệm vào `hash(tenantId) % N` khiến việc mở rộng hoặc di chuyển về sau khó hơn.

### 1.2. Dữ liệu có tách không có nghĩa tài nguyên được tách

Hai tenant có thể được lưu ở hai logical partitions khác nhau nhưng vẫn dùng chung cùng physical node, CPU, IO hoặc quota. “Đã sharding” không chứng minh “mỗi tenant được bảo đảm hiệu năng độc lập”.

### 1.3. Tenant boundary không nhất thiết là transaction boundary

Toàn bộ dữ liệu của một doanh nghiệp có thể gồm hàng triệu đơn. Không cần và thường không thể có một transaction bao trùm toàn doanh nghiệp. Transaction boundary phù hợp thường là **aggregate nhỏ** như Order, Wallet hoặc Inventory reservation; tenant chỉ là lớp **phân quyền và định tuyến**.

## 2. Vì sao phân phối tenant thường lệch?

Ví dụ một nền tảng có 10.000 tenant:

| Nhóm | Số tenant | Dữ liệu mỗi tenant | Tải trung bình mỗi tenant |
|---|---:|---:|---:|
| Nhỏ | 9.950 | 0,1 GiB | 2 requests/s |
| Vừa | 49 | 20 GiB | 200 requests/s |
| Whale | 1 | 2.048 GiB | 10.000 requests/s |

Những số này là **giả định minh họa**, không phải thống kê sản phẩm nào. Dù chỉ có một whale, nó nắm hơn 2 TiB dữ liệu và có thể tạo 10.000 request/s: ngang nhiều tenant vừa cộng lại. Nếu phân phối chỉ theo số lượng tenant, một shard chứa whale có thể quá tải, còn những shard chứa nhiều tenant nhỏ vẫn rảnh.

### 2.1. Kích thước và độ nóng là hai trục độc lập

Một tenant có **3 TiB dữ liệu lưu trữ lịch sử nhưng ít truy cập** khác tenant **20 GiB nhưng 50.000 write/s**. Cách tối ưu khác nhau:

| Trục | Đo như thế nào? | Giới hạn có thể chạm |
|---|---|---|
| Data size | GiB/TiB, số documents, số items | Capacity, compaction, backup/restore |
| Read rate | Reads/s, throughput, cache hit | CPU, IO, connections |
| Write rate | Writes/s, write bytes/s | WAL, replication, partition hot |
| Peak/burst | p95/p99 tải theo cửa sổ thời gian | Throttling, retry storms |
| Hot-key share | % traffic vào key nóng nhất | Single-key contention |
| Growth rate | GiB/day, documents/day | Sớm chạm hạn partition |
| Query fan-out | Số buckets/shards mỗi truy vấn | Latency và chi phí |
| Recovery cost | Backfill, reindex, failover duration | RTO, redundancy |

Một whale “lớn nhưng lạnh” có thể cần tách storage/retention. Một whale “nhỏ nhưng nóng” cần chia write traffic hoặc xử lý hotspot theo entity.

### 2.2. Không chỉ xem giá trị trung bình

Đánh giá tenant bằng QPS trung bình dễ bỏ sót việc doanh nghiệp gửi file import khổng lồ hoặc flash sale trong 15 phút. Cần đo **peak theo tenant, top-N tenants, tỷ lệ ghi trên hot keys và skew giữa các shard**.

### 2.3. Data size skew khác key skew

Một tenant có 100 triệu Order phân bố đều có thể chia theo OrderId. Nhưng nếu mọi Order đều cùng cập nhật `TenantTotalCounter`, counter đó vẫn là hotspot. **Sharding dữ liệu con không tự sharding invariant hoặc state dùng chung.**

## 3. Mô hình đơn giản: một tenant được định tuyến tới một shard

Một sơ đồ quen thuộc:

~~~text
shard = hash(tenantId) modulo shardCount
~~~

Ví dụ:

~~~text
Tenant A -> Shard 1
Tenant B -> Shard 3
Tenant C -> Shard 2
Tenant WHALE -> Shard 1
Tenant D -> Shard 4
~~~

Ưu điểm:

- Tìm vị trí nhanh từ `tenantId`.
- Query có điều kiện `tenantId` có thể dễ route tới một nơi.
- Một số phép tính/transaction tenant-local có thể tận dụng locality nếu API hỗ trợ.
- Tách dữ liệu và vận hành theo tenant tương đối rõ.

Nhược điểm:

- Nếu whale ở Shard 1, mọi dữ liệu và ghi của whale có thể tập trung vào một shard.
- Tenant nhỏ cùng shard chịu noisy neighbor.
- Khi tăng `shardCount` và thay đổi phép modulo, nhiều tenant có thể cần di chuyển.
- Giới hạn dung lượng/throughput của một physical shard có thể trở thành giới hạn kích thước của tenant.

### 3.1. Hash đều `tenantId` không có nghĩa tải đều

Giả sử 100 tenant được hash vào 10 shard. Số tenant mỗi shard có thể gần nhau, nhưng nếu một tenant chiếm 60% write throughput, shard chứa nó vẫn quá tải.

Hashing phân bố **khóa** tương đối đều, không đảm bảo phân bố **trọng số của các khóa** đều khi trọng số rất lệch.

### 3.2. Consistent hashing không tự chữa whale

Consistent hashing có thể giảm số **tenant phải đổi shard khi thêm/bớt node** so với hash modulo trực tiếp. Nhưng nếu mỗi tenant vẫn là một đơn vị bất khả phân, một whale vẫn nằm trên một owner và vượt năng lực node ấy.

Giải pháp là tăng tính hạt mịn của đơn vị đặt dữ liệu: **virtual buckets bên trong tenant**, hoặc tách tenant lớn sang tài nguyên riêng.

### 3.3. Khi mô hình một tenant–một shard vẫn tốt

Nếu phần lớn tenant nhỏ, mọi tenant đều nằm dưới giới hạn dung lượng/tải của một shard, yêu cầu query tenant-local cao và ít whale, mô hình này có thể đơn giản, rẻ và phù hợp. Không cần tạo fan-out xuyên nhiều buckets khi chưa có nhu cầu.

## 4. Phân biệt tenant placement và entity partitioning

Một kiến trúc linh hoạt tách:

1. **Placement:** tenant này thuộc pool/cluster nào?
2. **Partitioning:** dữ liệu của tenant được phân thành bao nhiêu buckets và bucket nào chứa entity?
3. **Physical mapping:** bucket nằm trên shard/partition vật lý nào?

~~~mermaid
flowchart TD
    A["Tenant nhỏ A"] --> P["Shared Pool"]
    B["Tenant vừa B"] --> P
    C["Tenant whale C"] --> D["Dedicated Pool"]
    P --> S1["Shard 1"]
    P --> S2["Shard 2"]
    D --> C0["C/Bucket 0..15"]
    D --> C1["C/Bucket 16..31"]
    D --> C2["C/Bucket 32..63"]
~~~

Đặt tenant lớn sang dedicated pool và chia tenant đó thành nhiều buckets là **hai quyết định riêng**. Chuyển whale sang một server lớn có thể giải quyết noisy neighbor nhưng vẫn không vượt được giới hạn một hot partition; chia buckets giải quyết phân phối dữ liệu nhưng không tự tạo cô lập tài nguyên nếu vẫn dùng chung node.

### 4.1. Routing granularity

| Đơn vị định tuyến | Được gì? | Mất gì? |
|---|---|---|
| `tenantId` | Query tenant-local đơn giản | Whale không thể phân tán trong một tenant |
| `(tenantId, timeBucket)` | Quản lý dữ liệu theo thời gian/retention | Truy vấn nhiều tháng fan-out |
| `(tenantId, entityBucket)` | Dàn trải nhiều entities trong tenant | List toàn tenant cần fan-out/merge |
| `(tenantId, aggregateId)` | Phân phối tốt khi ID đa dạng | Query theo tenant phải dùng index/read model |
| Dedicated cluster per whale | Cô lập chi phí/vận hành | Chi phí nền và migration |
| Hybrid | Linh hoạt theo tier | Router/control plane phức tạp |

## 5. Chọn partition key theo đường truy cập

Đừng chọn shard key dựa trên vẻ đẹp của chuỗi khóa. Hãy liệt kê các query chính:

~~~text
1. GET Order bằng (tenantId, orderId).
2. LIST Orders của tenant theo createdAt, newest first.
3. GET Invoice bằng (tenantId, invoiceId).
4. Tìm toàn bộ Order của một customer trong tenant.
5. Thống kê doanh thu tenant theo ngày.
6. Dọn dữ liệu quá retention.
7. Query toàn hệ cho dashboard nội bộ.
~~~

Mỗi cách partition tối ưu một số truy vấn và làm khó số khác.

### 5.1. `tenantId` làm tiền tố bắt buộc

Đặt `tenantId` trong khóa định danh/truy vấn giúp bảo vệ ranh giới và route:

~~~text
Order key:
    (tenantId, orderId)

Invoice key:
    (tenantId, invoiceId)
~~~

Nhưng việc có tenantId trong ID chưa có nghĩa database sẽ phân phối nhiều shard bên trong tenant. Cần biết **trường nào thực sự được hash/range partition**.

### 5.2. Không dùng một field tăng đơn điệu làm điểm dồn tải

Nếu tất cả Order ghi theo `createdAt` tăng dần và partitioner đặt phần mới nhất vào một range/physical owner, write traffic có thể dồn vào một vùng. Kết hợp time bucketing và hash/salt hợp lý nếu cần, đồng thời chấp nhận chi phí đọc nhiều bucket.

### 5.3. EntityId phải ổn định

Nên chọn bucket của một Order bằng `orderId` hoặc một stable aggregateId. Không dùng `status` hoặc timestamp có thể thay đổi để tính bucket nếu điều đó buộc mỗi update thành cross-partition move.

### 5.4. Chìa khóa của thiết kế là invariant

Nếu Order có 20 line items và tổng tiền cần commit cùng nhau, nên giữ chúng trong một aggregate/document hoặc transaction đúng scope. Không phân tán ngẫu nhiên line items sang 20 buckets rồi kỳ vọng một transaction single-partition vẫn hoạt động.

## 6. Chiến lược 1: giữ tenant nhỏ trong shared shards

Với “long tail” gồm nhiều tenant nhỏ, pooled storage thường tiết kiệm tài nguyên:

~~~text
Shared Cluster
  Shard 1: Tenant A, D, F, H...
  Shard 2: Tenant B, E, G...
  Shard 3: Tenant C, I, J...
~~~

Một tenant nhỏ có thể ở **một bucket logic**. Hệ dùng tenant-aware routing để đưa mọi thao tác của tenant đó vào owner tương ứng.

### 6.1. Lợi ích

- Giảm chi phí hạ tầng cố định trên mỗi tenant.
- Dễ provisioning tenant mới.
- Dễ đặt quota, retention và baseline SLO theo tier.
- Cần ít metadata hơn mô hình mỗi tenant nhiều buckets.

### 6.2. Rủi ro

- Tenant tăng trưởng bất ngờ chạm ngưỡng một shard.
- Một tenant import dữ liệu lớn gây compaction/IO pressure cho những tenant khác.
- Một lỗi shard có thể ảnh hưởng nhiều tenant cùng lúc.
- Hard isolation cho dữ liệu có quy định đặc biệt có thể không đủ.

### 6.3. Khi nào nâng tier?

Quy định trigger theo **dung lượng, throughput, tốc độ tăng, hot-key ratio, isolation requirement và dự báo**, không chỉ số users.

~~~text
Example policy (illustrative):
    if sustained throughput is high,
    or storage approaches safe shard headroom,
    or residency/security requires isolation:
        evaluate dedicated placement or internal bucketing.
~~~

Không có một mốc GiB/QPS đúng cho mọi NoSQL. Hãy đo và gắn policy với quota/thực lực của cụm đang chạy.

## 7. Chiến lược 2: tách whale sang dedicated placement

Một số tenant rất lớn nên được tách ra:

~~~text
Tenant Directory
  small tenant -> shared cluster A
  medium tenant -> shared cluster B
  whale tenant -> dedicated cluster W
~~~

**Dedicated** có thể nghĩa là database riêng, cluster riêng, shard group riêng hoặc nguồn tài nguyên cô lập hơn, tùy sản phẩm.

### 7.1. Tại sao không tách tất cả tenant?

Nếu hàng nghìn tenant nhỏ mỗi tenant dùng một cluster riêng, chi phí baseline, monitoring, backup, security patching và upgrade có thể quá lớn.

### 7.2. Dedicated cluster không tự dàn trải một hot key

Whale ghi mọi request vào `TenantBalanceCounter` hoặc một Inventory SKU. Chuyển sang cluster riêng giảm ảnh hưởng tenant khác, nhưng hot key vẫn có thể giới hạn throughput. Cần giảm contention hoặc thay đổi protocol ghi tại key đó.

### 7.3. Hạn chế workload “đưa whale về sau”

Nếu ngay từ đầu đã biết tenant có hàng trăm triệu records, việc bắt đầu bằng single-partition đơn lẻ có thể tạo migration lớn và rủi ro. Cần provisioning policy theo quy mô dự kiến, không chỉ chờ sau khi quá tải.

### 7.4. Dedicated và yêu cầu pháp lý

Một tenant có thể yêu cầu region, encryption key, retention hoặc audit policy riêng. Placement cần theo **residency/compliance** trước rồi mới tối ưu tải; không tự di chuyển dữ liệu sang vùng rẻ hơn nếu điều đó vi phạm hợp đồng.

## 8. Chiến lược 3: chia một tenant thành nhiều virtual buckets

Với tenant whale, thêm bucket bên trong tenant:

~~~text
tenantId = enterprise-900
bucketCount = 64

Order O-100 -> bucket 07
Order O-101 -> bucket 29
Order O-102 -> bucket 07
Order O-103 -> bucket 41
...
~~~

Một hàm minh họa:

\[
\operatorname{bucket}(tenantId, entityId)
=\operatorname{hash}(tenantId \Vert entityId)\bmod B
\]

Trong đó \(B\) là số virtual buckets và \(\Vert\) biểu diễn mã hóa ghép trường rõ ràng. Cần chọn hàm hash **ổn định qua ngôn ngữ/phiên bản ứng dụng**, tránh dùng hash có seed ngẫu nhiên từng process.

### 8.1. Virtual bucket không nhất thiết bằng physical shard

~~~text
Tenant enterprise-900:
    logical bucket 00..15 -> Physical Shard A
    logical bucket 16..31 -> Physical Shard B
    logical bucket 32..47 -> Physical Shard C
    logical bucket 48..63 -> Physical Shard D
~~~

Khi thêm Shard E, có thể **chuyển một số buckets** sang E mà không thay đổi cách tính bucket của Order. Đây là lý do tách **entity-to-bucket mapping** khỏi **bucket-to-shard placement**.

### 8.2. Lợi ích

- Phân tán read/write các entities độc lập của whale.
- Di chuyển lượng dữ liệu nhỏ hơn toàn tenant.
- Giảm nguy cơ một logical partition tăng không giới hạn.
- Có thể dành nhiều physical shards hơn cho whale khi cần.

### 8.3. Tradeoff

- Query theo toàn bộ tenant phải fan-out nhiều buckets.
- Aggregate across buckets không còn là transaction một partition.
- Unique key toàn tenant cần một registry/authority phù hợp.
- Cross-bucket joins hoặc tổng hợp có thêm network/latency.
- Router/control plane và migration phức tạp hơn.

### 8.4. Không tăng `bucketCount` bằng đổi modulo một cách vô tư

Nếu trước đây:

~~~text
bucket = hash(orderId) mod 16
~~~

đột nhiên thay bằng:

~~~text
bucket = hash(orderId) mod 64
~~~

nhiều Order cũ sẽ có bucket mới khác bucket đang chứa dữ liệu. Client có thể trả 404 giả, tạo duplicate hoặc đọc nhầm.

**Các lựa chọn an toàn:** giữ số virtual buckets cố định đủ dư địa từ đầu; dùng mapping có version và di chuyển dữ liệu đúng protocol; hoặc giữ generation cũ có cơ chế lookup/forwarding cho dữ liệu chưa migrate. Không tự đổi modulo rồi mong database tự rehash bản ghi.

## 9. Cách chọn bucketing: ID, thời gian hoặc kết hợp

### 9.1. Hash theo aggregate ID

~~~text
bucket = stableHash(tenantId, orderId) % bucketCount
~~~

Phù hợp khi GET/UPDATE bằng `orderId`, Order độc lập, traffic phân tán. Những query “danh sách tất cả Orders mới nhất” phải fan-out/merge hoặc dùng read model riêng.

### 9.2. Time buckets

~~~text
partitionKey = (tenantId, yyyyMM)
~~~

Phù hợp dữ liệu time series, logs, events, audit records:

- Xóa/archiving theo tháng thuận tiện.
- Query tháng gần đây có thể route đúng các buckets.
- Dữ liệu lâu năm không dồn một partition.

Nhưng **tháng hiện tại** có thể là hot partition nếu một whale gửi quá nhiều events. Cần thêm hash/salt cho write distribution khi cần.

### 9.3. Time × hash bucket

~~~text
partitionKey = (tenantId, month, hashBucket)
~~~

Ví dụ một whale có 16 hash buckets cho tháng 2026-11. Query theo tháng fan-out 16 buckets; query một event có stable `eventId` xác định được bucket trực tiếp.

### 9.4. Bucket theo customer/subaccount

~~~text
partitionKey = (tenantId, customerId)
~~~

Hữu ích khi truy vấn chủ yếu theo customer. Nhưng một customer cực lớn vẫn tạo hot partition; cần kiểm tra độ lệch **bên trong tenant**.

### 9.5. Bucket theo shard ownership business

Một hệ booking có thể phân theo `(tenantId, propertyId)` để giữ tất cả reservation thuộc property trong cùng owner. Cách này hợp lý khi invariant/transaction chủ yếu trong một property, nhưng property whale có thể cần tách tiếp.

### 9.6. Bucket không nên theo mutable field

`status`, `currentAssignee` hoặc `lastUpdatedAt` có thể đổi liên tục. Nếu dùng chúng làm owner partition key, một update tưởng đơn giản trở thành move dữ liệu, transaction xuyên partitions hoặc thao tác delete+insert nguy hiểm.

## 10. Tính toán sức chứa và hệ số lệch

Đánh giá placement phải xét ít nhất:

~~~text
capacity budget per shard:
    storage usable headroom
    sustainable read/write throughput
    peak CPU / IO / memory
    connections / transactions
    recovery time
~~~

Với shard \(s\), một chỉ số đơn giản:

\[
\operatorname{loadRatio}(s)
=\max\left(
\frac{\operatorname{bytes}(s)}{\operatorname{safeBytes}(s)},
\frac{\operatorname{writeOps}(s)}{\operatorname{safeWriteOps}(s)},
\frac{\operatorname{readOps}(s)}{\operatorname{safeReadOps}(s)}
\right).
\]

Đây là mô hình minh họa; trong thực tế IO size, read/write amplification, query complexity, contention và working set có thể quan trọng hơn ops/s thô.

### 10.1. Vì sao không chỉ cân bằng theo dung lượng?

Shard A có 500 GiB dữ liệu cold và 100 QPS, Shard B có 50 GiB nhưng 20.000 QPS trên hot indexes. Chỉ cân bằng bytes có thể tiếp tục làm B nghẽn. Cần workload-aware placement.

### 10.2. Hot tenant và hot key

Một whale có 64 buckets nhưng 80% requests đều cập nhật một `tenantQuota` record. Load của từng bucket Orders có thể cân bằng, còn quota key vẫn nghẽn. Tách **tenant aggregate traffic** khỏi **shared control record traffic** để đo đúng.

### 10.3. Headroom cho failover và migration

Nếu shard đang chạy ở 95% sustained capacity, khi một node chết hoặc cần backfill tenant lớn, hệ có thể không còn đủ headroom. Placement policy nên dự phòng khả năng chịu lỗi và chi phí dữ liệu di chuyển, không tối đa hóa utilization ở trạng thái bình thường.

## 11. Tenant directory: lớp điều khiển vị trí dữ liệu

Một directory ánh xạ tenant và buckets sang storage:

~~~json
{
  "tenantId": "enterprise-900",
  "routingEpoch": 17,
  "region": "region-A",
  "placement": "dedicated-cluster-W",
  "bucketCount": 64,
  "hashFunctionVersion": 2,
  "state": "ACTIVE",
  "bucketOwners": {
    "00-15": "shard-A",
    "16-31": "shard-B",
    "32-47": "shard-C",
    "48-63": "shard-D"
  }
}
~~~

Đây là **dữ liệu mô tả kiến trúc**; cần mô hình bucketOwners có thể tra cứu máy móc và transaction/consistency phù hợp trong implementation. Không phải mọi metadata đều nên nằm trong một document dài vô hạn.

### 11.1. Data plane và control plane

~~~mermaid
flowchart LR
    AUTH["Auth / tenant context"] --> ROUTER["Tenant-aware router"]
    ROUTER --> DIR["Tenant Directory (control plane)"]
    DIR --> ROUTER
    ROUTER --> A["Data Shard A"]
    ROUTER --> B["Data Shard B"]
    ROUTER --> C["Dedicated Cluster"]
~~~

**Control plane** quản lý placement, policy, migration state và version. **Data plane** thực thi truy vấn/ghi theo route. Cả hai phải có availability/durability contract rõ; directory outage có thể ảnh hưởng requests dù database shards vẫn khỏe.

### 11.2. Routing epoch

Mỗi lần thay đổi owner, tăng `routingEpoch` hoặc generation một cách đơn điệu:

~~~text
epoch 17: tenant A writes to shard X
epoch 18: tenant A writes to shard Y
~~~

Router giữ cache epoch 17 không được tiếp tục ghi vào X sau khi epoch 18 đã có hiệu lực, nếu điều đó tạo hai owners đồng thời. Cần fencing hoặc server-side ownership validation.

### 11.3. Directory là nguồn có thẩm quyền

Không để mỗi service tự duy trì map thủ công khác nhau. Nếu một service route Tenant A tới X còn service khác route tới Y sau migration, read/write có thể phân kỳ hoặc tạo duplicate. Tốt hơn là có một contract directory nhất quán, versioned và có cơ chế invalidation.

### 11.4. Định tuyến theo tenant và entity

Hai thao tác khác nhau:

~~~text
resolveTenant(tenantId) -> placement, bucket scheme, epoch
resolveEntity(tenantId, orderId) -> bucket, physical owner
~~~

Một lệnh `LIST Orders` không có orderId cần **query planner** khác GET by ID: fan-out theo các buckets liên quan hoặc đọc read model. Không cố dùng router point lookup cho mọi query.

### 11.5. Cache route an toàn

Directory lookup mỗi request có thể tăng latency. Có thể cache routing metadata với TTL/notifications, nhưng **TTL không phải fencing**. Server cũ phải từ chối write mang epoch đã lỗi thời hoặc client phải được redirect/refresh theo protocol khi owner đổi.

## 12. Thiết kế routing cho long-tail và whale cùng tồn tại

Một chính sách dạng tier:

~~~text
Tier SMALL:
    cluster = shared-A
    bucket scheme = ONE

Tier MEDIUM:
    cluster = shared-B
    bucket scheme = 8 virtual buckets

Tier WHALE:
    cluster = dedicated-W
    bucket scheme = 64 virtual buckets
~~~

Chỉ là ví dụ. Không mặc định 8/64 là con số tối ưu hoặc mọi engine cần nhiều physical partitions cho mỗi tenant.

### 12.1. Quy tắc chuyển tier phải dự báo trước

Nếu tenant chạm giới hạn maximum logical partition trước khi migration bắt đầu, việc chuyển có thể khó và tốn downtime. Dùng growth forecasts, safe-headroom thresholds và lịch migration trước ngưỡng rủi ro.

### 12.2. Đừng coi “medium” là một loại kích thước cứng

Tenant 100 GiB với QPS thấp có thể ở shared cluster dung lượng lớn; tenant 5 GiB nhưng write rất nóng cần dedicated throughput. Tiering nên xét nhiều chiều.

### 12.3. Tenant có thể cần nhiều collections với partitioning khác nhau

Order, clickstream, analytics, settings và audit logs có đường truy cập khác nhau:

~~~text
Tenant configuration:
    small bounded document keyed by tenantId.

Orders:
    bucket by stable orderId.

Events:
    bucket by time × hash.

Analytics:
    pre-aggregated read model.
~~~

Không áp một shard key thống nhất cho mọi collection chỉ vì chúng thuộc cùng tenant.

## 13. Cross-bucket queries và pagination

Một tenant whale có 64 buckets. API:

~~~text
GET /tenants/{tenantId}/orders?sort=createdAt_desc&limit=50
~~~

Nếu Orders phân theo hash(OrderId), dữ liệu mới nhất có thể nằm ở bất kỳ bucket nào. Query cần:

1. Chọn các buckets thuộc tenant và phạm vi lọc.
2. Đọc top-N có thứ tự từ mỗi bucket.
3. Merge các luồng đã sắp xếp.
4. Trả 50 item đầu cùng cursor ổn định.

~~~mermaid
flowchart LR
    Q["List Orders"] --> B1["Bucket 1: top-N"]
    Q --> B2["Bucket 2: top-N"]
    Q --> B3["Bucket 3: top-N"]
    B1 --> M["Merge by createdAt, orderId"]
    B2 --> M
    B3 --> M
    M --> RES["Page + composite cursor"]
~~~

### 13.1. Không dùng OFFSET toàn cục một cách ngây thơ

`OFFSET 100000` trên nhiều shards có thể buộc đọc/sắp xếp lượng lớn dữ liệu. Cursor/keyset pagination thường hợp lý hơn:

~~~text
sortKey = (createdAt DESC, orderId DESC)
cursor per bucket = last examined sortKey
~~~

Cần xử lý thứ tự đồng hạng, insert mới khi phân trang và consistent snapshot nếu API yêu cầu không bỏ sót/trùng.

### 13.2. Fan-out làm tăng tail latency

Nếu một page phải đợi 64 shard requests, xác suất có một shard chậm tăng. Dùng bounded concurrency, timeout hợp lý, adaptive query planning và read models cho những đường đọc nóng. Không vì hashing write tốt mà chấp nhận mọi GET fan-out vô hạn.

### 13.3. Query qua tenant nhỏ không cần fan-out

Một tenant nhỏ có thể chỉ dùng một bucket. Router nên biết scheme và tránh gửi 64 requests không cần thiết chỉ vì whale dùng 64 buckets.

### 13.4. Cross-tenant analytics cần pipeline riêng

Dashboard “tổng doanh thu tất cả tenants” không nên fan-out hàng chục nghìn tenant synchronously trên đường request người dùng. Thường dùng CDC/events, stream processing, OLAP warehouse hoặc materialized aggregates phù hợp.

## 14. Unique constraints và identity toàn tenant

Một ràng buộc:

~~~text
Mỗi tenant chỉ có tối đa một user mang canonicalUsername=an123.
~~~

Nếu Users phân tán vào 64 buckets theo userId, hai requests có thể tạo `an123` trong hai buckets khác nhau. Một unique index **chỉ trong mỗi bucket** không bảo vệ uniqueness trên toàn tenant.

### 14.1. Unique registry có owner rõ

~~~text
UsernameRegistry key:
    (tenantId, canonicalUsername)

Atomic conditional create:
    only if key does not exist
~~~

Tất cả requests cùng username phải cạnh tranh trên cùng key có thẩm quyền.

### 14.2. Registry và User profile có thể khác partition

Nếu create registry và profile không cùng transaction scope, có thể xảy ra registry đã cấp nhưng profile chưa tạo. Cần:

- Transaction nhiều item nếu hệ hỗ trợ phạm vi đúng.
- Workflow `RESERVED -> ACTIVE` có idempotency, deadline và reconciliation.
- Thiết kế registry làm source of truth với projection profile thích hợp.

Không gọi hai independent writes trong một method rồi coi là atomic.

### 14.3. Tenant-wide quota

Một whale có 64 buckets và quota tối đa 100.000 active tasks. Kiểm tra `COUNT(*)` ở từng bucket và cộng lại ngoài transaction rồi insert ở một bucket **không bảo vệ quota dưới concurrency**.

Có thể dùng một quota authority/guard record được giảm có điều kiện; hoặc phân bổ quota cho buckets:

~~~text
totalQuota = 100000
bucketQuota[0..63] with sum <= totalQuota
~~~

Điều chỉnh quota giữa buckets cần protocol bền và chống double allocation. Tách counters thành shards tùy ý không đủ để chứng minh tổng quota không vượt.

### 14.4. Order/Invoice numbering

Yêu cầu số hóa đơn tăng liên tục trong một tenant thường tạo một sequence owner nóng. Nếu nghiệp vụ chấp nhận khoảng trống hoặc block allocation, có thể cấp dải ID trước cho các buckets. Nếu bắt buộc serial/gapless theo luật, cần đánh giá chi phí coordination và semantics khi transaction abort; hashing không thể loại bỏ một ràng buộc toàn cục.

## 15. Transaction và aggregate boundaries khi split tenant

Trước khi chia tenant, một transaction có thể đã cập nhật:

~~~text
Order O-100
OrderLine O-100/I-1
Outbox OrderConfirmed:O-100
~~~

Nếu tất cả nằm trong một aggregate hoặc một logical partition được DB hỗ trợ transaction, thao tác có thể atomic. Khi chuyển OrderLine sang các buckets khác nhau, invariant “total khớp items” có thể vượt phạm vi.

### 15.1. Giữ aggregate cùng bucket

Một quy tắc tốt:

~~~text
bucket(Order O-100)
    = bucket(OrderLine of O-100)
    = bucket(OrderOutboxEvent for O-100)
~~~

Tất cả dùng cùng stable `orderId` khi tính bucket. Nhờ vậy phần dữ liệu cần commit cùng nhau vẫn có cơ hội ở một partition/transaction scope, **nếu schema và sản phẩm thực sự hỗ trợ**.

### 15.2. Không tự suy từ bucket giống nhau là một transaction

Hai collections cùng `bucketId` nhưng DB yêu cầu cùng logical partition hoặc transaction không hỗ trợ xuyên collection thì vẫn có thể không atomic. Cần đọc exact API contract.

### 15.3. Invariant xuyên Orders

Một quota “toàn tenant không quá 100 open Orders” sẽ không được bảo vệ bằng transaction của một Order bucket. Cần central guard, preallocated quotas, serializable transaction trên phạm vi hỗ trợ, hoặc định nghĩa state machine chấp nhận reservation workflow.

### 15.4. Read model không là nguồn quyết định commit

Một materialized counter toàn tenant có thể cập nhật bất đồng bộ và thích hợp cho dashboard, nhưng không được dùng để check rồi tạo Order nếu cần invariant chính xác.

## 16. Ví dụ MongoDB: tenant-aware shard key

Trong MongoDB, shard key quyết định cách phân phối document trong sharded collection theo phiên bản và cấu hình. Một field `tenantId` xuất hiện trong document **không tự làm nó được shard theo tenant**; phải xem shard key thực tế.

Ví dụ document:

~~~json
{
  "_id": "O-100",
  "tenantId": "enterprise-900",
  "orderId": "O-100",
  "bucketId": 7,
  "createdAt": "2026-11-14T08:00:00Z",
  "status": "CONFIRMED",
  "items": [
    {"sku": "SKU-A", "quantity": 2, "unitPriceMinor": 12000}
  ],
  "version": 3
}
~~~

### 16.1. Shard chỉ theo tenant

Một shard key chỉ theo `tenantId` có thể giữ/định tuyến dữ liệu của tenant gần nhau tùy sharding mode. Nhưng với một whale, mọi document có cùng shard-key value sẽ không tự được rải đều theo `orderId`; phải xem khả năng split/chunk balancing của sản phẩm.

### 16.2. Key bao gồm bucket hoặc entity

Một chiến lược ứng dụng tạo `bucketId` từ orderId, rồi thiết kế shard key/index hỗ trợ phân phối theo `(tenantId, bucketId, ...)` hoặc một dạng hashed compound key **được phiên bản MongoDB hỗ trợ**.

Không khẳng định mọi compound/hashed shard key tự phân phối đồng đều; thứ tự field, cardinality, chunk behavior và query pattern quyết định kết quả.

### 16.3. Query có tenant scope

~~~javascript
db.orders.find({
  tenantId: "enterprise-900",
  bucketId: 7,
  orderId: "O-100"
});
~~~

Truy vấn có đủ thông tin shard key có thể giúp targeted routing theo khả năng của cấu hình. Truy vấn thiếu bucket trong mô hình nhiều buckets có thể scatter/gather.

### 16.4. Unique index

Unique constraint trên sharded collection có quy tắc về shard key/prefix và phạm vi được hỗ trợ. Không đặt unique `orderId` rồi cho rằng nó bảo vệ toàn tenant/xuyên shards theo mọi schema. Cần thiết kế ID, unique index hoặc registry đúng documented constraint.

### 16.5. Di chuyển tenant không chỉ là đổi shard key

Thay đổi shard key/resharding, di chuyển chunks và di chuyển tenant sang cluster khác là các thao tác khác nhau với công cụ và giới hạn riêng. Application tenant directory có thể cần phối hợp, nhất là khi tenant có data residency hoặc dedicated cluster.

## 17. Ví dụ DynamoDB: partition key chứa tenant

Trong DynamoDB, một mẫu single-table:

~~~text
PK = TENANT#enterprise-900
SK = ORDER#O-100
~~~

Mẫu này hỗ trợ truy vấn item collection theo tenant rất thuận tiện. Nhưng một whale có thể tạo tải cao vào cùng partition-key value và gặp giới hạn/thiết kế partition của dịch vụ, dù DynamoDB có cơ chế quản lý capacity và phân phối storage nội bộ.

### 17.1. Write sharding theo bucket

~~~text
PK = TENANT#enterprise-900#BUCKET#07
SK = ORDER#O-100
~~~

Khi đặt Order O-100, ứng dụng tính `bucketId` ổn định. GET biết orderId có thể route đến bucket; LIST toàn tenant phải query nhiều PK và merge.

### 17.2. Adaptive capacity không thay thế data model

Managed service có các tối ưu adaptive/split partitions tùy điều kiện, nhưng không nên dùng chúng làm bằng chứng một hot key hoặc unbounded item collection chắc chắn mở rộng vô hạn. Đọc giới hạn throughput theo key/partition/index và các điều kiện như local secondary indexes của schema đang dùng.

### 17.3. GSI có đường truy cập và consistency riêng

Một GSI hỗ trợ query `customerId` có thể cập nhật và có giới hạn/consistency khác base table. Không dùng read từ GSI trễ như điều kiện duy nhất để enforce quota hoặc uniqueness.

### 17.4. Transaction nhiều item

`TransactWriteItems` có phạm vi và quota API cụ thể; nó không biến một lệnh fan-out qua 64 buckets thành transaction vô hạn. Khi chia aggregate, phải giữ các thay đổi cần commit cùng nhau trong scope được hỗ trợ.

### 17.5. Sử dụng commandId khi move bucket

Nếu migrate một Order từ old bucket sang new bucket, request retry sau timeout không được tạo hai Order. Cần route generation và unique business ID được tra ở owner có thẩm quyền.

## 18. Ví dụ Azure Cosmos DB for NoSQL: logical partition và hierarchical keys

Cosmos DB for NoSQL đặt trọng tâm vào partition key. Một lựa chọn chỉ dùng:

~~~text
/tenantId
~~~

có thể tạo logical partition rất lớn hoặc nóng cho whale. Một số chế độ/phiên bản hỗ trợ hierarchical partition keys, cho phép mô hình nhiều cấp như tenant và một đơn vị nhỏ hơn.

### 18.1. Phác thảo key

~~~text
tenantId = enterprise-900
bucketId = 07

Hierarchical key concept:
    (tenantId, bucketId, aggregateId or category)
~~~

Phải xác minh số cấp, path, cách routing query theo prefix, giới hạn logical partition và cách HPK được hỗ trợ ở tài nguyên cụ thể.

### 18.2. Transaction scope

Transactional batch/stored procedures trong Cosmos DB for NoSQL có phạm vi **logical partition key** theo API. Không được nhầm query theo tiền tố `tenantId` với việc toàn bộ dữ liệu tenant cùng một logical partition nếu khóa thực tế gồm thêm bucket/cấp khác.

Ví dụ Order và Outbox muốn cùng transaction phải thực sự cùng full logical partition key đúng phạm vi, không chỉ có tenantId giống nhau.

### 18.3. Một logical partition lớn là giới hạn thiết kế

Không đợi đến lúc gần chạm giới hạn storage/request throughput rồi mới đổi partition key. Với whale, khả năng phân nhỏ từ lúc xây schema hoặc có migration protocol là cần thiết.

### 18.4. Multi-region và consistency

Chuyển tenant giữa regions không chỉ chuyển partition; còn liên quan account/region topology, replication, consistency, read/write routing, residency và việc xử lý dữ liệu chưa đồng bộ. “Cosmos có multi-region” không đủ để chứng minh một cutover tenant không mất ghi.

## 19. Ví dụ Cassandra/ScyllaDB: tránh partition quá lớn

Trong wide-column stores, partition key ảnh hưởng trực tiếp nhóm rows được lưu và đọc cùng nhau. Nếu:

~~~sql
CREATE TABLE orders_by_tenant (
    tenant_id text,
    created_at timestamp,
    order_id text,
    payload text,
    PRIMARY KEY ((tenant_id), created_at, order_id)
);
~~~

toàn bộ Orders của một whale có thể nằm trong **một partition rất lớn**, gây vấn đề về kích thước, compaction, tombstones, latency và hot partition.

### 19.1. Chia theo tháng và bucket

~~~sql
CREATE TABLE orders_by_tenant_bucket (
    tenant_id text,
    month_bucket text,
    hash_bucket int,
    created_at timestamp,
    order_id text,
    payload text,
    PRIMARY KEY (
        (tenant_id, month_bucket, hash_bucket),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Đây là schema minh họa; xem loại dữ liệu, key width, TTL/tombstones, query limitations, partition size và options của phiên bản đang chạy.

### 19.2. Query theo thời gian

~~~sql
SELECT created_at, order_id, payload
FROM orders_by_tenant_bucket
WHERE tenant_id = 'enterprise-900'
  AND month_bucket = '202611'
  AND hash_bucket = 7
LIMIT 50;
~~~

Muốn LIST cả tháng phải chạy query cho những `hash_bucket` liên quan rồi merge; không có cross-partition ORDER BY miễn phí.

### 19.3. LWT và transaction phạm vi

Conditional statements/LWT có phạm vi riêng; logged batch không tự là serializable transaction xuyên mọi partitions. Không chia dữ liệu ra nhiều partitions rồi dùng batch để tuyên bố invariant tenant-wide được commit atomically.

### 19.4. Bucketing phải phù hợp read path

Nếu 95% queries theo customer, phân theo month×hash(OrderId) có thể làm truy vấn customer fan-out lớn. Có thể tạo bảng truy vấn theo customer (materialized/denormalized) với semantics cập nhật được quản lý rõ.

## 20. Tenant routing trong Java: bucket ổn định và placement có version

Một adapter có thể tách **bucket assignment** khỏi **physical shard lookup**. Java 17+:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Map;

public record TenantRoute(
    String tenantId,
    String region,
    String clusterId,
    long routingEpoch,
    int virtualBucketCount,
    int hashFunctionVersion,
    Map<Integer, String> shardByBucket
) {}

public record ShardTarget(
    String region,
    String clusterId,
    String shardId,
    int bucketId,
    long routingEpoch
) {}

public interface TenantDirectory {
    TenantRoute resolve(String authorizedTenantId);
}

public final class StableBucketAssigner {
    private StableBucketAssigner() {}

    public static int assign(
        String tenantId, String entityId, int bucketCount
    ) {
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount <= 0");
        }
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            // Length-prefix to avoid ambiguous field concatenations.
            byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
            byte[] entity = entityId.getBytes(StandardCharsets.UTF_8);
            sha.update(ByteBuffer.allocate(4).putInt(tenant.length).array());
            sha.update(tenant);
            sha.update(ByteBuffer.allocate(4).putInt(entity.length).array());
            sha.update(entity);
            long hash = ByteBuffer.wrap(sha.digest()).getLong();
            return (int) Long.remainderUnsigned(hash, bucketCount);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Mã minh họa sử dụng SHA-256 để có định nghĩa ổn định giữa instances; điều này không có nghĩa SHA-256 tối ưu tốc độ/chi phí cho mọi workload. Hash inputs/encoding/version phải là một **contract được kiểm thử**, không được tùy tiện đổi khi triển khai ngôn ngữ khác.

### 20.1. Router dùng directory

~~~java
public final class TenantRouter {
    private final TenantDirectory directory;

    public TenantRouter(TenantDirectory directory) {
        this.directory = directory;
    }

    public ShardTarget targetFor(
        String authorizedTenantId, String aggregateId
    ) {
        TenantRoute route = directory.resolve(authorizedTenantId);
        if (!authorizedTenantId.equals(route.tenantId())) {
            throw new IllegalStateException("wrong tenant route");
        }
        if (route.hashFunctionVersion() != 2) {
            throw new IllegalStateException("unsupported hash version");
        }
        int bucket = StableBucketAssigner.assign(
            route.tenantId(), aggregateId, route.virtualBucketCount()
        );
        String shard = route.shardByBucket().get(bucket);
        if (shard == null) {
            throw new IllegalStateException("unmapped bucket");
        }
        return new ShardTarget(
            route.region(),
            route.clusterId(),
            shard,
            bucket,
            route.routingEpoch()
        );
    }
}
~~~

Đoạn mã chưa làm I/O, epoch fencing, migration redirects, caching, authorization, region enforcement hoặc retries; đó là **routing skeleton**, không phải client production. Trong thực tế còn cần adapter kiểm tra shard vẫn sở hữu bucket ở epoch đó trước khi nhận ghi.

### 20.2. Version của hash function

Nếu thay hash implementation, even cùng `bucketCount`, entity có thể đổi bucket. Ghi `hashFunctionVersion` và chỉ chuyển version thông qua migration có kiểm soát; không deploy hai service cùng lúc dùng hai thuật toán không tương thích mà không có routing bridge.

### 20.3. Stable bucket count là invariant vị trí

Với tenant nhỏ `bucketCount=1`, mọi entity bucket 0. Khi whale được tăng lên 64 buckets, **không được chỉ thay directory** vì existing records vẫn ở bucket 0. Cần data migration hoặc scheme version hỗ trợ dữ liệu legacy.

### 20.4. TenantId phải lấy từ ngữ cảnh đã xác thực

`authorizedTenantId` trong ví dụ là tenant được xác định/cho phép bởi authentication/authorization, không phải một tham số URL tự do. Router không được dùng request-supplied tenantId để truy cập tùy tenant khác.

## 21. Chuyển tenant lớn giữa các cụm

Giả sử Tenant T được chuyển từ Shared Cluster A sang Dedicated Cluster W. Cách làm sai:

~~~text
Copy old data.
Change routing table.
Done.
~~~

Trong khi copy, vẫn có writes trên A. Nếu chỉ copy snapshot đầu rồi đổi route, những writes phát sinh sau snapshot có thể mất hoặc không nằm trên W.

Một quy trình hợp lý cần xử lý **backfill, các thay đổi phát sinh trong thời gian copy, quyền owner và những request đang bay**.

### 21.1. State machine migration

~~~mermaid
stateDiagram-v2
    [*] --> PLANNED
    PLANNED --> BACKFILLING: Prepare target + capture change stream
    BACKFILLING --> CATCHING_UP: Bulk copy completed
    CATCHING_UP --> FENCING: Replica lag below safe boundary
    FENCING --> CUTOVER: Old writer frozen / epoch advanced
    CUTOVER --> VERIFYING: New owner accepting writes
    VERIFYING --> COMPLETED: Reconcile and retire old copy
    VERIFYING --> RECOVERING: Mismatch or stale writes
    RECOVERING --> VERIFYING: Repair under a single authority
~~~

Các tên state là mẫu thiết kế, không phải tính năng có sẵn của mọi database.

### 21.2. Bước 1 — Chuẩn bị và lưu checkpoint

Tạo target collection/index/config tương thích. Ghi tenant migration ID, source/target, routing epoch cũ, target schema version và vị trí trong change stream/log làm mốc.

### 21.3. Bước 2 — Backfill

Copy dữ liệu lịch sử theo chunks/pages có checkpoint. Mỗi record có tenantId, stable primary key và version. Thao tác copy nên idempotent để restart từ checkpoint không tạo trùng.

### 21.4. Bước 3 — Change capture/catch-up

Trong lúc backfill, source vẫn nhận write. Capture thay đổi bằng CDC/change streams hoặc một cơ chế đủ tin cậy, apply tới target theo **per-entity order/version**.

Không suy rằng stream sẵn có đảm bảo exactly-once; có thể có duplicate, retry, out-of-order hoặc retention expiry. Cần idempotency và cách phát hiện gap.

### 21.5. Bước 4 — Fencing source writer

Khi gần bắt kịp, cần xác định một cutover boundary bền. Có thể tạm dừng **writes của tenant T** trong một khoảng ngắn, đợi in-flight commands có outcome rõ, flush/apply mọi changes tới boundary, rồi đổi epoch owner.

Nếu chọn live dual-write thay vì freeze, phải có **protocol chống partial dual-write**. Hai API ghi vào A và W tuần tự không tạo atomic dual-write chỉ vì code gọi cả hai.

### 21.6. Bước 5 — Atomic directory cutover

Thay directory mapping:

~~~text
Tenant T:
    epoch 17, owner=A
  ->
    epoch 18, owner=W
~~~

Cutover nên dùng conditional/CAS update trên version, với một owner có thẩm quyền; shard A sau đó từ chối mutation mang epoch 17 hoặc yêu cầu router refresh. Nếu A và W cùng được chấp nhận ghi độc lập, migration có thể split brain.

### 21.7. Bước 6 — Read verification

Đối chiếu record counts theo buckets, sampled/full key checksums theo mục tiêu, high-watermarks, event/version continuity, unique constraints, tenant quotas và các business invariants quan trọng. Không chỉ so tổng số bytes.

### 21.8. Bước 7 — Dọn source có kiểm soát

Giữ source ở trạng thái read-only/tombstoned trong retention window phù hợp. Chỉ xóa sau khi route mới ổn định, dữ liệu verified, legal retention được kiểm tra và rollback/failback policy rõ ràng.

### 21.9. Đừng xóa tenant cũ ngay sau cutover

In-flight readers, stale caches, pending background jobs, compaction hoặc CDC checkpoint có thể còn tham chiếu source. Xóa ngay có thể khiến recovery rất khó nếu phát hiện missing records.

## 22. Từ một bucket thành nhiều buckets: migration phức tạp hơn move shard

Có hai thao tác khác:

**Physical relocation:** giữ nguyên `bucketId` của entity nhưng chuyển bucket từ shard A sang shard B.

**Repartitioning:** đổi cách gán entity vào bucket (ví dụ 1 -> 64 buckets), nên **entity IDs có thể đổi logical partition**.

### 22.1. Relocation

Nếu bucket 07 vẫn là bucket 07, router chỉ cần đổi `bucket07 -> newOwner` qua epoch và migration. Primary keys/bucket logic không đổi.

### 22.2. Repartitioning

Khi `bucketCount` đổi, phải đọc vị trí legacy và target theo migration generation:

~~~text
old:
    bucket scheme v1: single bucket 0.

new:
    bucket scheme v2: hash(orderId) % 64.
~~~

Trong giai đoạn chuyển tiếp, có thể:

- Freeze writes ngắn để backfill rồi cutover.
- Duy trì `entityLocation`/forwarding index versioned.
- Dùng dual-read rõ ràng với ưu tiên owner và version checks.
- Migrate per-range/per-entity có checkpoint và fencing.

Không cho client tùy tiện fallback “không thấy ở W thì đọc A và ghi lại W”, vì absence có thể do consistency lag hoặc quyền đã đổi, tạo resurrect dữ liệu đã xóa.

### 22.3. Tombstone và delete trong migration

Nếu record đã bị xóa ở source sau snapshot nhưng tombstone không được replay, target có thể **hồi sinh record đã xóa**. Change capture phải giữ deletes, ordering, expiry/TTL semantics và retention đủ lâu.

### 22.4. Transaction đang chạy khi chuyển owner

Một transaction của Order có thể đọc ở A, rồi trước commit directory đổi sang W. Cần epoch fencing ở commit, abort/retry an toàn hoặc cơ chế drain in-flight transactions. Không để một half-transaction commit trên old owner sau cutover.

### 22.5. Outbox và CDC checkpoint

Nếu Order và Outbox được chuyển cùng tenant, không được phát lại business event một cách gây duplicate side effect không kiểm soát. Dedupe theo eventId, giữ aggregate version, và bảo đảm event stream bắt kịp tới cutover boundary.

## 23. Dual-write là con dao hai lưỡi

Một chiến lược dễ nghĩ:

~~~text
On every write:
    write source A
    write target W
~~~

Nhưng giả sử A thành công, W timeout. Hoặc W thành công, A trả lỗi. Hoặc cả hai thành công nhưng response mất. **Không có transaction nguyên tử xuyên hai database chỉ nhờ chạy hai lệnh**.

### 23.1. Các hướng xử lý

- **Single authoritative source + CDC:** trong migration, chỉ A nhận write, target W nhận changes có thứ tự và có checkpoint.
- **Quiesce + replay:** tạm ngừng writes của một tenant, chuyển những thay đổi còn lại rồi cutover.
- **Durable write intent/outbox:** ghi intent cùng mutation source nếu transaction scope cho phép, rồi apply idempotently sang W.
- **Transactional replication protocol thực:** nếu sản phẩm có khả năng riêng, dùng đúng hợp đồng của nó.

### 23.2. Nếu bắt buộc dual-write

Cần định nghĩa:

~~~text
Which copy is authoritative?
How are partial successes detected?
Which version wins?
How are retries deduplicated?
How is cutover fenced?
How are deletions and TTL propagated?
What happens if CDC retention expires?
~~~

Không được tuyên bố exactly-once hay zero-loss từ một `try/catch` rồi retry.

### 23.3. Đừng cho reads trộn hai sources tùy tiện

Nếu read ở A thấy Order v8 và read ở W thấy v7, ứng dụng không được tùy tiện lấy v7 vì W gần hơn. Phải xác định owner và version precedence; trong migration có thể chỉ phục vụ reads ở A cho đến khi W được xác nhận catch-up.

## 24. Xử lý request cũ sau khi tenant được chuyển

Router cache:

~~~text
Service 1: tenant T -> shard A, epoch 17.
Service 2: tenant T -> shard W, epoch 18.
~~~

Nếu cả hai shard chấp nhận mutation, dữ liệu của T phân kỳ.

### 24.1. Fencing ở data plane

Storage adapter hoặc ownership service phải xác nhận epoch còn hợp lệ trước khi commit write. Shard A có thể trả `MOVED`/`STALE_EPOCH` với thông tin redirect được xác thực, sau đó client refresh directory.

### 24.2. Không tự retry một lệnh có outcome không rõ

Giả sử request tới A đã commit nhưng response mất đúng lúc epoch đổi. Service 1 retry ở W với commandId mới có thể tạo duplicate. Phải dùng **stable commandId** và một cách tra cứu/đối soát outcome qua cutover.

### 24.3. In-flight background jobs

Job queue có message cũ chứa shard A. Worker có thể xử lý sau migration hàng giờ. Payload chỉ nên chứa **tenantId + stable entity ID + commandId**, còn owner được tra lại khi thực thi, hoặc message có epoch và bị từ chối khi stale.

### 24.4. Fencing chỉ ở router chưa đủ

Một service bypass router, cron job cũ hoặc retry qua connection pool cũ có thể vẫn ghi A. Data plane cần enforcement phù hợp; nếu không, việc cập nhật directory không đảm bảo owner duy nhất.

### 24.5. Route not found khác entity not found

Nếu directory không có mapping hoặc shard trả `STALE_ROUTE`, không nên trả 404 “Order không tồn tại” cho người dùng. Phân loại lỗi routing, unavailable, unauthorized và not-found rõ ràng.

## 25. Tenant isolation không chỉ là partition key

Một record có `tenantId` là bước đầu, không phải toàn bộ mô hình bảo mật.

### 25.1. Tenant context từ authentication

Một request:

~~~http
GET /tenants/enterprise-900/orders/O-100
Authorization: Bearer <token>
~~~

Không được dùng path `enterprise-900` như bằng chứng user có quyền. Phải xác minh principal được phép truy cập tenant đó, rồi tạo context được dùng nhất quán ở routing và query.

### 25.2. Truy vấn phải có tenant predicate

~~~javascript
db.orders.findOne({
  tenantId: authorizedTenantId,
  orderId: requestedOrderId
});
~~~

Tùy mô hình ID, chỉ `orderId` có thể là định danh toàn hệ, nhưng vẫn phải kiểm tra ownership. Không cho một API admin tiện lợi bỏ `tenantId` rồi vô tình trả dữ liệu tenant khác.

### 25.3. Physical isolation và blast radius

Dedicated cluster có thể giúp giảm sự lan truyền một sự cố tải, nhưng còn cần access controls, secrets, encryption, backup, network segmentation và operational boundaries. Shared database có thể vẫn bảo vệ dữ liệu logic tốt nếu kiểm soát đúng; hai mô hình khác nhau về threat model.

### 25.4. Tenant data residency

Directory nên mang placement constraints như `allowedRegions`, `dataClass`, `encryptionPolicy` nếu hệ cần. Migration phải kiểm tra trước khi copy; cross-region backup/replication cũng là **di chuyển dữ liệu** cần tuân thủ hợp đồng.

### 25.5. Delete tenant

Offboarding/erasure không đơn giản là xóa một key `tenantId`. Dữ liệu có thể nằm ở 64 buckets, search indexes, backups, CDC logs, caches, object storage và analytics projections. Cần lifecycle job có checkpoint, retention/legal holds, proof-of-erasure theo policy và chống resurrection từ source cũ.

## 26. Noisy neighbor và công bằng tài nguyên

Ngay cả với phân mảnh hợp lý, resource contention vẫn có thể xảy ra ở cluster chung:

- Một tenant scan toàn bộ 1 TiB, chiếm IO của các tenant khác.
- Một tenant import hàng triệu documents, khiến compaction và replica lag tăng.
- Một tenant tạo nhiều connection pools hoặc transactions dài.
- Một tenant chạy query không có partition predicate khiến scatter/gather.
- Một tenant có keys quá nóng gây throttling liên tục.

### 26.1. Per-tenant admission control

Một thiết kế:

~~~text
tenantBudget:
    max concurrent operations
    max read/write rate
    burst allowance
    max background scan slots
    max query fanout
~~~

Khi vượt, system có thể queue hoặc trả rate-limit theo contract, thay vì cho tenant đó làm cạn tài nguyên chung.

### 26.2. Fair scheduling

Tách pools/queues cho interactive reads, writes, backfills và analytics. Một migration whale không được chiếm toàn bộ IO khiến checkout tenant nhỏ vượt SLO.

### 26.3. Per-tenant retry budgets

Nếu một whale bị throttle, retry vô hạn có thể gây retry storm và ảnh hưởng cả pool. Dùng bounded exponential backoff có jitter, concurrency limits và circuit breakers theo failure mode.

### 26.4. Cô lập chi phí

Tenant placement policy có thể gắn service tier, dedicated capacity, usage accounting và billing. Nhưng **billing estimate không thay thế placement engineering**: một tenant có thể trả tiền cao nhưng tạo hot key không thể mở rộng bằng tăng CPU.

## 27. Một trường hợp đặc biệt: tenant có hot keys bên trong

Một whale lưu Order phân đều vào 64 buckets. Mọi Order lại làm:

~~~text
UPDATE TenantSummary
SET totalOrders = totalOrders + 1
~~~

`TenantSummary` vẫn là single hot item. Nếu chỉ cần dashboard eventual:

~~~text
Order committed
    -> outbox event
    -> stream processor
    -> aggregate shards/projection
~~~

Read model có thể cập nhật bất đồng bộ; cần dedupe eventId và xử lý event order.

Nếu `totalOrders` phải chính xác tức thời để enforce quota, không thể tự đổi sang eventual counter mà giữ nguyên invariant.

### 27.1. Quota phân bổ theo buckets

Ví dụ quota 100 active jobs cho whale:

~~~text
Bucket 0 quota 15
Bucket 1 quota 10
...
Sum bucket quota <= 100
~~~

Mỗi bucket cấp jobs trong quota local bằng atomic conditional update. Tăng quota bucket cần chuyển quyền từ pool chưa cấp hoặc bucket khác qua protocol để không double allocate.

### 27.2. Single-writer cho một entity

Nếu mọi writes tranh một Order hoặc Account, việc hash hàng triệu Orders không giúp **một Order cực nóng**. Có thể dùng queue/actor theo aggregate, CAS, batching hoặc protocol domain giảm contention.

### 27.3. Bucketing và chính xác tài chính

Một ledger có thể phân event stream để tăng throughput, nhưng số dư khả dụng và tiền không được double-spend cần nguồn authority/transaction riêng. Đừng coi distributed counters eventual là thay thế cho ledger correctness.

## 28. Index và truy vấn toàn tenant sau khi bucketing

Một index tenant-centric:

~~~text
(tenantId, status, createdAt)
~~~

có thể thuận lợi cho query theo tenant/status, nhưng nếu physical data chia theo `bucketId`, vẫn cần biết index đó có partitioned/global semantics, cross-shard scatter và consistency ra sao.

### 28.1. Secondary index không tự đổi data placement

Một global secondary index có thể giúp một query nhưng có latency, chi phí write amplification và propagation lag. Nếu index là eventual, không dùng nó để quyết định uniqueness hay quota tức thời.

### 28.2. Query fan-out theo API

Ví dụ:

| API | Placement key biết trước? | Hướng xử lý |
|---|---|---|
| GET Order by orderId | Có, hash(orderId) | Point lookup đúng bucket |
| GET OrderLines by orderId | Có, cùng aggregate bucket | Local aggregate query |
| LIST newest Orders | Không | Fan-out/merge hoặc materialized view |
| GET Customer Orders | Có thể theo customerId nếu model hỗ trợ | Customer-centric index/read model |
| SUM revenue by day | Thường nhiều buckets | Stream aggregate/OLAP |
| Delete all tenant data | Cần enumerate buckets | Managed lifecycle job |

### 28.3. Có thể denormalize theo query

Một read model `orders_by_customer` có thể được cập nhật bằng events/CDC và dùng để lấy danh sách nhanh. Source Order vẫn là authority cho status/invariants; projection cần idempotency, version, lag monitoring và rebuild path.

### 28.4. Pagination consistency

Query 64 buckets trong nhiều round-trips có thể thấy inserts/deletes ở các mốc khác nhau. Nếu yêu cầu một snapshot nhất quán của toàn tenant, phải có distributed snapshot/query API hỗ trợ hoặc kiến trúc đọc riêng, không chỉ một cursor token tự chế.

## 29. Backup, restore, TTL và retention theo tenant

Khi tenant nằm trên nhiều shards:

- Backup toàn tenant cần biết **danh sách buckets và owner tại một epoch nhất quán**.
- Restore một tenant phải tránh trộn dữ liệu các mốc không phù hợp nếu ứng dụng có invariant xuyên buckets.
- TTL theo collection/partition có thể khác retention contract của từng tenant.
- Tombstones/deletions phải được giữ đủ lâu qua migration/CDC để không resurrect dữ liệu.
- Indexes/projections cũng cần khả năng rebuild.

### 29.1. Backup theo cluster không tự bằng backup theo tenant

Một backup cluster có thể chứa dữ liệu hàng trăm tenant. Restore một tenant riêng cần tooling lọc đúng tenant/buckets và kiểm tra quyền/phạm vi; không đơn giản restore cả cluster đè dữ liệu tenant khác.

### 29.2. Thời gian khôi phục whale

Một tenant 2 TiB sẽ có restore/backfill time khác tenant 1 GiB. Nếu yêu cầu RTO thấp, có thể cần dedicated replication, incremental backups và diễn tập restore riêng cho whale.

### 29.3. Region migration và backups

Nếu tenant chuyển sang region mới theo residency policy, bản backup ở region cũ có thể vẫn tồn tại. Data movement plan phải tính backup retention và việc xóa/cô lập bản sao cũ phù hợp.

## 30. Một case study: hệ quản lý đặt phòng nhiều tenant

Ứng dụng cho doanh nghiệp quản lý properties và bookings. Có:

~~~text
Tenant
Property
Room
Reservation
Invoice
AuditEvent
~~~

Các tenant nhỏ có vài property; một chuỗi khách sạn lớn có hàng nghìn property và hàng triệu reservations mỗi tháng.

### 30.1. Phương án ban đầu

~~~text
PK = tenantId
~~~

Ưu điểm query tất cả booking tenant đơn giản. Nhưng whale tenant có một partition lớn/hot.

### 30.2. Phương án phát triển

~~~text
Tenant small:
    shared pool, one bucket

Tenant whale:
    dedicated pool
    placement by propertyId
    additional time bucketing for audit events
~~~

Reservation invariant “một room không được double-book một time slot” thuộc **Property/Room authority**, không thuộc toàn tenant. Có thể đặt tất cả reservations của room (hoặc một time-slice phù hợp) để thực hiện conditional write/transaction bảo vệ overlap theo contract.

### 30.3. Không chia mù theo random ReservationId

Nếu hai requests cùng đặt Room R1 cho thời gian trùng nhau, chúng có thể vào hai buckets khác nhau khi hash ReservationId. Một truy vấn overlap từ snapshot không nhất thiết chặn cả hai. Cần một owner/lock/guard theo room/time slot hoặc transaction serializable đúng phạm vi.

### 30.4. Đường đọc

- Search available rooms: read model có thể lag nhưng checkout phải xác minh lại.
- GET reservation by ID: route qua deterministic bucket/locator.
- LIST bookings by property/date: query bounded partitions.
- Tenant monthly analytics: streaming aggregate.

### 30.5. Di chuyển whale

Migrate từng property bucket sang dedicated cluster, dùng epoch/fencing và CDC. Nếu một property đang được chuyển, route writes của property đó tới đúng một authority; không để hai owners cùng accept booking.

## 31. Một case study: nền tảng sự kiện và tenant có burst lớn

Một tenant thường có tải thấp nhưng mở sự kiện online, tạo 1 triệu registrations trong thời gian ngắn.

### 31.1. Vấn đề

Ngay cả khi tenant có ít dữ liệu lịch sử, đợt ghi dồn có thể gây:

~~~text
hot tenantId partition
connection pool exhaustion
write throttling
replica lag
CDC backlog
impact to neighboring tenants
~~~

### 31.2. Cách tiếp cận

- Partition registrations theo stable eventId/registrationId hoặc time × hash nếu workload phù hợp.
- Giữ quota/seat inventory tại nguồn có thẩm quyền, dùng atomic reservation.
- Dùng async ingestion cho thông tin có thể xử lý muộn.
- Đặt per-tenant concurrency/rate budgets và dedicated capacity khi cần.
- Đo backlog và không trả “REGISTERED” nếu mới chỉ nhận vào hàng đợi.

### 31.3. Tránh mất semantics khi queue

Một API `202 ACCEPTED` có nghĩa lệnh đang chờ; chỉ khi durable registration/seat allocation được commit mới nên trả trạng thái nghiệp vụ `CONFIRMED`. Idempotency key giúp chống duplicate do client retry.

## 32. Observability: đo skew và routing thay vì chỉ CPU cluster

| Metric | Mục tiêu |
|---|---|
| Top tenants by storage | Tìm whales về dung lượng |
| Top tenants by read/write rate | Tìm whales về tải |
| Tenant peak/burst factor | Phát hiện event/import bất thường |
| Per-shard bytes and QPS | Đánh giá cân bằng |
| Hot-key concentration | Phân biệt tenant skew và entity skew |
| p95/p99 latency per tenant tier | Kiểm chứng SLO của long tail |
| Throttle/retry per tenant | Noisy neighbor và retry storm |
| Bucket count/fan-out per query | Theo dõi chi phí bucketing |
| Routing lookup/cache hit | Directory overhead |
| Stale epoch / MOVED responses | Phát hiện routes cũ khi migration |
| Migration backlog and CDC lag | Kiểm soát catch-up |
| Missing/duplicate record reconciliation | Chứng minh data movement đúng |
| Cross-region routing violations | Cảnh báo sai residency |
| Tenant restore time | Ước lượng RTO |

### 32.1. Không tạo metrics cardinality vô hạn

Gắn `tenantId` làm label cho hàng triệu time series có thể làm monitoring quá tải. Dùng top-K tenants, sampling, tier labels, logs/traces có tenant context được bảo vệ, và các hệ phân tích phù hợp để điều tra tenant cụ thể.

### 32.2. Cần theo dõi cả long tail

Nếu chỉ đo whale p99, một whale được cô lập nhưng 9.000 tenant nhỏ vẫn bị chậm do shared database/index. SLO phải theo **tier và percentile có ý nghĩa**, cùng số tenant bị ảnh hưởng khi một shard quá tải.

### 32.3. Migration là một nghiệp vụ có SLO

Theo dõi `bytesCopied`, `cdcLag`, `lastAppliedVersion`, `routingEpoch`, `reconciliationMismatches`, `inFlightWrites`, `cutoverDuration` và `rollback/repair state`. Một migration không có checkpoint/tracing khó khôi phục sau crash.

## 33. Kiểm thử phân mảnh với tải lệch

### 33.1. Tạo workload có phân phối Zipf-like

Đừng test bằng 10.000 tenant đồng đều 100 QPS. Hãy tạo:

~~~text
many tiny tenants
some medium tenants
one giant storage tenant
one bursty hot tenant
one tenant with a single extremely hot key
~~~

Đo từng phương án placement theo peak, p99, read/write amplification và headroom.

### 33.2. Test deterministic routing

Cùng `(tenantId, entityId, hashVersion, bucketCount)` phải ra cùng bucket trên mọi instance/ngôn ngữ. Test Unicode, dấu phân tách, empty strings, IDs rất dài và số buckets khác nhau. Không dùng `String.hashCode()` như một hợp đồng cross-language nếu chưa có đặc tả tương thích.

### 33.3. Test tăng số buckets

Tenant ban đầu có một bucket, nâng lên 64 bằng migration. Xác minh GET theo old/new IDs không trả 404 giả, UPDATE không tạo duplicate, DELETE không resurrect và list query không bỏ sót.

### 33.4. Test routing cache stale

Service A giữ epoch 17; Service B dùng epoch 18. Sau cutover, gửi write qua A. Kỳ vọng old owner từ chối/redirect theo protocol, **không** commit state rẽ nhánh.

### 33.5. Test migration mid-write

Cho client gửi update đúng lúc chuyển epoch, cắt network ngay khi commit/ACK. Sau recovery, dùng commandId kiểm tra update được áp dụng **một lần hoặc có outcome hợp lệ**, không mất/nhân đôi.

### 33.6. Test CDC gap và deletes

Tạm dừng CDC đến khi gần hết retention. Xác minh hệ phát hiện gap và **không tự tuyên bố target đã synchronized**. Xóa record trong lúc backfill, bảo đảm tombstone được áp dụng và record không hồi sinh.

### 33.7. Test query fan-out

Một tenant 64 buckets, LIST top-50 theo createdAt. Chèn một bucket chậm, đo p99, timeout, partial results policy và cursor correctness. Không âm thầm thiếu kết quả mà vẫn trả response hoàn chỉnh.

### 33.8. Test tenant isolation

Tạo cùng `orderId` ở hai tenants, thử API với token của tenant A nhưng route ID thuộc B. Kỳ vọng data không lộ. Kiểm tra cả cache keys, projections, background jobs và admin endpoints.

### 33.9. Test quota dưới concurrency

Hai buckets cùng tạo jobs làm tổng vượt tenant-wide quota. Nếu kiến trúc dùng preallocated quotas, kiểm tra tổng quota còn đúng khi chuyển quota, crash và retry.

### 33.10. Test failover/routing

Một shard owner chết hoặc directory unavailable. Xác định request nào có thể sử dụng route cache an toàn, request nào phải fail closed, và strong writes có được reroute tới replica đủ điều kiện hay không.

## 34. Ví dụ JUnit kiểm thử tính ổn định của bucket mapping

Mẫu dùng class `StableBucketAssigner` ở trên:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import java.util.HashSet;
import java.util.Set;

class StableBucketAssignerTest {

    @Test
    void sameTenantAndAggregateAlwaysMapToSameBucket() {
        int expected = StableBucketAssigner.assign(
            "enterprise-900", "O-100", 64
        );
        for (int i = 0; i < 100; i++) {
            assertEquals(
                expected,
                StableBucketAssigner.assign(
                    "enterprise-900", "O-100", 64
                )
            );
        }
    }

    @Test
    void bucketsAreInConfiguredRange() {
        for (int i = 0; i < 2000; i++) {
            int bucket = StableBucketAssigner.assign(
                "enterprise-900", "O-" + i, 64
            );
            assertTrue(bucket >= 0 && bucket < 64);
        }
    }

    @Test
    void sampleEntitiesUseMoreThanOneBucket() {
        Set<Integer> buckets = new HashSet<>();
        for (int i = 0; i < 2000; i++) {
            buckets.add(StableBucketAssigner.assign(
                "enterprise-900", "O-" + i, 64
            ));
        }
        assertTrue(buckets.size() > 1);
    }
}
~~~

Những test này **chỉ kiểm tra hàm bucket** trong một JVM, không chứng minh cluster balance hoặc tính đúng đắn migration. Cần golden vectors cross-language và integration tests trên directory/physical placement.

### 34.1. Golden vectors

Lưu các cặp `(tenantId, entityId, hashVersion, bucketCount, expectedBucket)` được kiểm thử cho Java, Go, Node.js và worker batch. Nếu hai ngôn ngữ mã hóa Unicode hoặc trường ghép khác nhau, routing có thể phân kỳ dù cùng tên hash algorithm.

### 34.2. Test khi directory đổi epoch

Test adapter phải đảm bảo một request có epoch cũ bị từ chối tại owner cũ. Kết quả `STALE_EPOCH` là tín hiệu retry route **sau khi xác định outcome của request trước** nếu request có thể đã commit.

### 34.3. Không dùng test phân phối để chứng minh security

Hai tenant rơi vào cùng shard hoặc cùng bucket number không phải cross-tenant leak nếu keys/predicates đúng; ngược lại, nằm ở hai shards khác nhau cũng không tự chứng minh authorization được thực thi.

## 35. Các sai lầm thường gặp

### “Hash `tenantId` là tự động cân bằng tải”

Không. Hash cân bằng số khóa tương đối, nhưng tenant có trọng số tải khác nhau. Một whale vẫn tạo shard nóng.

### “Một tenant phải ở một shard để dễ quản lý”

Không bắt buộc. Tenant lớn có thể cần virtual buckets, còn tenant nhỏ vẫn một shard. Phải cân bằng query locality và throughput.

### “Dedicated cluster giải quyết mọi hot key”

Không. Single hot aggregate vẫn có contention dù cluster riêng.

### “Chia Order theo random ID sẽ bảo vệ quota toàn tenant”

Không. Cross-bucket invariant cần authority/transaction/quota protocol.

### “Cứ đổi từ modulo 16 sang 64 là dữ liệu tự chuyển”

Không. Entity bucket thay đổi nhưng data cũ còn nguyên; cần migration/versioned routing.

### “Consistent hashing giải quyết tenant whale”

Không nếu whale vẫn là một placement unit không thể chia.

### “Thấy `tenantId` trong document là chắc chắn sharded đúng”

Không. Phải biết actual shard/partition key và routing behavior.

### “Một shard key dùng được cho mọi collection”

Không. Orders, events, configuration và analytics có đường truy cập và vòng đời khác nhau.

### “Tăng buckets luôn tăng hiệu năng”

Không. Query fan-out, index overhead, coordination và hot keys có thể khiến p99 tệ hơn.

### “Các buckets cùng tenant tự nằm trong một transaction”

Không. Transaction scope là contract của DB, không phải ý nghĩa business của `tenantId`.

### “Đọc mọi bucket rồi cộng COUNT là kiểm tra quota an toàn”

Không dưới concurrent writes nếu không có cơ chế bảo vệ predicate/authority lúc commit.

### “Một unique index ở mỗi bucket là unique toàn tenant”

Không. Hai buckets có thể chứa cùng username; cần scope unique đúng.

### “Directory đổi route là dữ liệu đã move xong”

Không. Phải backfill, catch up, fence writes, cutover và verify.

### “TTL cache là đủ để ngăn owner cũ ghi”

Không. Router cache stale cần server-side fencing/version checks.

### “Dual-write source/target là transaction”

Không. Hai ghi độc lập có thể thành công một bên và fail bên kia.

### “Không tìm thấy ở shard mới thì đọc shard cũ và tạo lại”

Nguy hiểm: có thể làm hồi sinh dữ liệu đã xóa hoặc bỏ qua consistency/epoch.

### “Tenant nằm khác shards là đã an toàn bảo mật”

Không. Authentication, authorization, query predicates, admin tools và cache keys vẫn cần tenant isolation.

### “Phân tán đều storage nghĩa là không có noisy neighbor”

Không. CPU, IO, query fan-out, background compaction và connection pools vẫn có thể bị chia sẻ.

### “Một migration hoàn tất khi số record hai bên bằng nhau”

Không. Cần đối soát versions, deletes, CDC offsets, invariants và in-flight writes.

### “Có backup cluster là khôi phục một tenant đơn giản”

Không. Tenant có thể nằm trên nhiều buckets/regions và cùng backup với tenants khác.

### “Chuyển whale sang region rẻ hơn chỉ là thay DNS”

Không. Cần residency constraints, durability/catch-up, routing epoch và phục hồi sau lỗi.

## 36. Checklist ra quyết định

1. **Phân loại workload:** tenant nhỏ/vừa/whale theo dung lượng, QPS, burst và growth.
2. **Liệt kê invariant:** điều gì cần commit cùng nhau trong tenant, property, Order hoặc Inventory?
3. **Vẽ access patterns:** point lookup, tenant list, time-range, customer queries, global analytics.
4. **Xác định partition key thực:** không chỉ field có sẵn trong schema.
5. **Đo skew và hot keys:** dùng top tenants, top entities và per-shard metrics.
6. **Chọn placement tiers:** pooled, dedicated, hybrid với dự phòng failover.
7. **Chọn bucket scheme:** stable entity hash, time, property hoặc kết hợp phù hợp.
8. **Định nghĩa route registry:** cluster, region, bucket owner, epoch, hash version và state.
9. **Đảm bảo tenant auth:** tenantId được xác thực ở mọi read/write và background job.
10. **Đánh giá cross-bucket query:** fan-out, pagination, index/read model và cost.
11. **Đánh giá transaction scope:** aggregate/Outbox/unique/quota có còn được bảo vệ không?
12. **Thiết kế migration:** backfill, CDC, fencing, owner cutover, deletes và reconciliation.
13. **Thiết kế retry/idempotency:** stable commandId qua timeouts và route change.
14. **Tuân thủ locality/residency:** bao gồm backup, CDC và logs.
15. **Đặt per-tenant quotas:** concurrency, throughput, query fan-out và background work.
16. **Kiểm thử skew:** whale QPS, hot key, lag, failover và stale directory.
17. **Đặt SLO:** p99 theo tier, throughput, migration duration, RPO/RTO và tenant isolation.
18. **Dự phòng tăng trưởng:** không để tenant tới giới hạn cứng mới bắt đầu tách.

### 36.1. Mẫu quyết định kỹ thuật

~~~yaml
feature: tenant-order-storage
tenantId: enterprise-900
tenantClass: whale

workload:
  storage: "<measured GiB>"
  sustainedWritesPerSecond: "<measured>"
  peakWritesPerSecond: "<measured>"
  hotKeyConcentration: "<measured>"

placement:
  region: "<allowed region>"
  cluster: "<target cluster>"
  isolationTier: "<pooled/dedicated>"
  routingEpoch: "<control-plane version>"

partitioning:
  aggregate: "Order"
  bucketStrategy: "stable hash(tenantId, orderId)"
  bucketCount: "<versioned count>"
  hashVersion: "<stable contract>"

correctness:
  tenantAuthorization: "required"
  transactionBoundary: "Order plus related outbox intent"
  tenantWideQuota: "<authority/escrow design>"
  idempotencyKey: "stable commandId"

migration:
  source: "<old placement>"
  target: "<new placement>"
  changeCapture: "<documented mechanism>"
  fencing: "epoch-based owner enforcement"
  verification: "per-key versions, deletes, checksums, CDC watermark"

evidence:
  databaseProductVersion: "<exact version>"
  partitionLimits: "<verified docs>"
  loadTest: "<run ID>"
  migrationDrill: "<run ID>"
~~~

Đây là mẫu hồ sơ để review, không phải một cấu hình production đã được xác nhận. Không điền những giá trị giới hạn bằng suy đoán.

## 37. Bài tập thực hành

### Bài 1 — Skew theo tenant

Một hệ có 1.000 tenants, trong đó một tenant tạo 70% write QPS. Nếu dùng `hash(tenantId)` và mỗi tenant ở một shard, giải thích vì sao tăng từ 4 lên 8 shards không nhất thiết giải quyết whale hotspot.

### Bài 2 — Tenant lớn nhưng lạnh

Tenant A có 3 TiB audit logs nhưng chỉ 10 QPS; Tenant B có 5 GiB nhưng 30.000 write/s. So sánh chiến lược storage placement, time bucketing, hot-key mitigation và dedicated throughput.

### Bài 3 — Chọn partition key

Thiết kế khóa cho Orders có ba truy vấn: GET by orderId, LIST newest Orders trong tenant, LIST Orders của customer. Nêu tradeoff của `(tenantId, orderId)`, `(tenantId, timeBucket, hashBucket)` và `(tenantId, customerId)`.

### Bài 4 — Virtual buckets

Whale có 64 virtual buckets trên 4 shards. Khi thêm shard thứ năm, hãy đề xuất cách chuyển 8 buckets sang shard mới mà không đổi `bucket(orderId)` của các Order cũ.

### Bài 5 — Thay modulo

Ứng dụng đổi `hash(orderId) % 16` thành `% 64` qua một deploy. Hãy mô tả vì sao GET có thể 404 giả, và đề xuất scheme version/migration/forwarding an toàn.

### Bài 6 — Tenant directory

Thiết kế directory record gồm `tenantId`, cluster, region, buckets, hashVersion, routingEpoch và migration state. Làm sao để service có cache epoch cũ không ghi vào old owner?

### Bài 7 — Migration đang nhận write

Copy tenant 500 GiB từ A sang B trong 3 giờ, source vẫn nhận update. Thiết kế backfill + CDC + cutover, bao gồm checkpoint, delete tombstone, in-flight transactions và đối soát.

### Bài 8 — Dual-write partial failure

Ứng dụng ghi A thành công rồi B timeout. Client retry và cả hai đã có thể chứa dữ liệu. Xây state machine hoặc giải pháp single-authority+CDC để không tạo hai phiên bản nguồn.

### Bài 9 — Cross-bucket quota

Whale có 32 buckets và quota tối đa 1.000 active tasks. Hai buckets cùng tạo thêm jobs. Hãy thiết kế quota authority hoặc preallocated quota để invariant không bị phá khi concurrency cao.

### Bài 10 — Username unique trong tenant

Users được hash theo userId vào 64 buckets. Hai client cùng tạo username `an123`. Vì sao unique index tại từng bucket không đủ? Thiết kế canonical key registry và lifecycle khi tạo profile thất bại.

### Bài 11 — Cassandra

Cho schema partition chỉ theo `(tenantId)` với 100 triệu events của một whale. Viết mô hình `tenantId + month + hashBucket`, mô tả query thời gian và chi phí fan-out.

### Bài 12 — DynamoDB

So sánh `PK=TENANT#X` với `PK=TENANT#X#BUCKET#07`. Nêu hệ quả cho read item collection, hot partition, GSI, transactional write và kiểm thử adaptive capacity.

### Bài 13 — Cosmos DB

Một thiết kế HPK gồm tenant và bucket. Kiểm tra logical partition key của transactional batch, sự khác biệt giữa prefix query theo tenant và transaction trên full partition key.

### Bài 14 — MongoDB

Một sharded collection dùng shard key chỉ có `tenantId`. Một whale ghi rất nóng. Đề xuất bucket/compound key hoặc dedicated placement và xác định các query/index cần đánh giá lại.

### Bài 15 — Cross-tenant leak

API GET Order nhận tenantId qua URL và orderId qua query, rồi chỉ tìm bằng orderId. Thiết kế kiểm thử dùng hai tenants có cùng orderId và cách bảo vệ router/repository/authorization.

### Bài 16 — Room reservation

Một whale có hàng nghìn properties. Đặt Reservation theo hash(reservationId) giúp cân bằng tải, nhưng làm sao ngăn hai booking trùng Room/time slot? Thiết kế authority/guard có transaction scope rõ.

### Bài 17 — List newest Orders

Một tenant có 64 buckets, mỗi bucket trả top-50 Orders. Thiết kế k-way merge và composite cursor `(createdAt, orderId)`; phân tích inserts mới, duplicate/missing page và p99 khi một bucket chậm.

### Bài 18 — Noisy neighbor

Một tenant chạy analytics scan làm p99 của 500 tenant khác tăng gấp bốn. Đề xuất per-tenant admission control, job queue separation, dedicated tier và metrics kiểm chứng.

### Bài 19 — Region residency

Tenant phải nằm trong Region A nhưng router có thể chuyển sang cluster rảnh ở Region B. Hãy đề xuất placement constraints, validation khi migration, backup/CDC policy và alert khi routing vi phạm.

### Bài 20 — Migration crash

Worker migration chết sau backfill nhưng trước hoàn tất CDC. Thiết kế checkpoint idempotent để resume; giải thích vì sao không được chuyển directory sang target nếu chưa có high-watermark và reconciliation.

### Bài 21 — Hot counter

Orders đã trải trên 128 buckets nhưng mỗi Order vẫn tăng một tenant-wide counter. Phân tích contention và chọn between eventual projection, batching, guard/counter authority hoặc escrow quota tùy invariant.

### Bài 22 — Review kiến trúc

Một tài liệu đề xuất: “Dùng hash tenantId nên mọi tenant được cân bằng; whale quá lớn thì chỉ tăng số shards, đổi modulo, và trong migration ghi song song source/target rồi sửa DNS.” Hãy chỉ ra tất cả assumptions nguy hiểm về skew, routing, old data, ACK, dual-write, fencing, query fan-out và bảo mật.

---

**Kết luận:** Phân mảnh theo tenant là một lựa chọn tự nhiên của NoSQL multi-tenancy, nhưng **tenant không có kích thước và tải đồng đều**. Hash `tenantId` có thể phân phối nhiều tenant nhỏ khá tốt mà vẫn tạo điểm nghẽn nghiêm trọng khi một whale chiếm phần lớn dữ liệu hoặc QPS. Kiến trúc trưởng thành thường **tách tenant placement khỏi entity bucketing**, giữ long tail trong shared pools, tách tenant rất lớn sang tài nguyên phù hợp, và chia dữ liệu whale bằng **stable virtual buckets** khi cần. Lợi ích phân phối tải đi kèm chi phí **fan-out query, index, uniqueness, transaction và quota xuyên buckets**; những bất biến này cần nguồn có thẩm quyền, không thể giải quyết bằng hash đơn thuần. Cuối cùng, thay đổi vị trí tenant là một **quy trình di chuyển dữ liệu có trạng thái**, đòi backfill, CDC/catch-up, fencing bằng routing epoch, idempotency, kiểm chứng deletes và cutover an toàn. Thiết kế đúng phải đồng thời bảo vệ **hiệu năng, khả năng mở rộng, tenant isolation, data residency và tính đúng đắn của các ghi đã xác nhận**.
