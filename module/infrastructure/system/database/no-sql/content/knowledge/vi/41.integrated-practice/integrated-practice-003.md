# Thiết kế khóa và phân vùng cho dữ liệu có phân bố lệch

Một thiết kế NoSQL có thể hoạt động rất tốt trên dữ liệu thử nghiệm đồng đều nhưng gặp sự cố ngay khi đi vào sản xuất: một khách hàng lớn chiếm phần lớn lưu lượng, một sản phẩm trong đợt flash sale nhận hàng chục nghìn cập nhật mỗi giây, các bản ghi mới đều rơi vào một khoảng khóa thời gian, hoặc một partition tăng quá lớn trong khi những partition khác gần như rỗng. Thêm node không tự giải quyết nếu phần lớn công việc vẫn bị ghim vào **một khóa nóng**, **một nhóm replica**, hoặc **một logical partition**.

Bài thực hành này tập trung vào việc **thiết kế khóa và phân vùng cho dữ liệu có phân bố lệch** trong NoSQL: thu thập phân phối thực tế, xác định access patterns, dự đoán hotspot, lựa chọn khóa phân vùng, định tuyến, thử tải và điều chỉnh phương án khi các giả định ban đầu thay đổi.

**Ý chính:** Khóa phân vùng tốt không chỉ phân phối số bản ghi tương đối đều; nó phải phân phối **tải đọc/ghi và dung lượng**, hỗ trợ **truy vấn quan trọng với fan-out chấp nhận được**, giữ đúng **ràng buộc nguyên tử/nhất quán**, đồng thời có cách xử lý **tenant/key nóng** và mở rộng khi tải tăng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **primary key**, **partition/shard key**, **sort/clustering key**, **logical partition**, **physical partition**, **shard** và **replica**.
2. Phân biệt **data skew**, **request skew**, **read/write skew**, **hot key**, **hot partition**, **hot shard** và **temporal hotspot**.
3. Đo và mô tả phân phối bằng **top-k share, percentiles, cardinality, Gini, hệ số lệch tải và heatmap theo thời gian**.
4. Lập bảng **access patterns** trước khi chọn key, bao gồm filters, ordering, latency, write rate, consistency, TTL và atomicity.
5. So sánh **range**, **hash**, **composite**, **tenant-aware**, **time bucket**, **salting/bucketing** và **directory-based routing**.
6. Lý giải khác biệt giữa **khóa có cardinality cao** và **khóa thật sự phân phối work**; hiểu vì sao hash chưa giải quyết được một hot logical key.
7. Thiết kế riêng cho **event append**, **order lookup**, **timeline theo tenant**, **inventory counter**, **leaderboard** và **time-series/latest-first**.
8. Tính giới hạn **fan-out, write amplification, read amplification, storage/replica footprint và headroom**.
9. Viết ví dụ Java để **tạo dữ liệu skew, tính thống kê, ánh xạ bucket, lập kế hoạch truy vấn** và hỗ trợ migration key version.
10. Lập **bộ kiểm thử tải, quan sát, runbook và kế hoạch resharding** trước khi áp dụng trên production.

> **Phạm vi:** Những con số, tên tenant, quy mô và cấu hình bên dưới là tình huống giả lập để thực hành, **không phải benchmark đã đo của một engine cụ thể**. Khi áp dụng MongoDB, Cassandra/ScyllaDB, DynamoDB, Cosmos DB, Redis Cluster hoặc Elasticsearch/OpenSearch, phải tuân thủ đúng semantics, giới hạn và phiên bản triển khai.

## 2. Tình huống xuyên suốt: nền tảng đặt hàng đa tenant

Một ứng dụng Java quản lý đơn hàng cho 5.000 khách hàng doanh nghiệp (tenant). Mỗi đơn có thể chứa nhiều mặt hàng; người dùng tra cứu đơn theo ID và xem danh sách đơn gần đây. Đồng thời, một đợt flash sale khiến cùng một SKU được truy cập liên tục.

### 2.1. Quy mô giả lập

| Đặc điểm | Giá trị minh họa |
| --- | ---: |
| Số tenants | 5.000 |
| Số Orders lưu dài hạn | 200 triệu |
| Dung lượng logical Orders và metadata | 12 TiB |
| Ghi mới/cập nhật thông thường | 4.000 operations/s |
| Ghi trong đợt cao điểm | 20.000 operations/s |
| Đọc thông thường | 30.000 operations/s |
| Tenant lớn nhất T-A | 45% total write traffic trong flash sale |
| 10 tenants lớn nhất | 72% writes trong flash sale |
| SKU nóng nhất | 30% reservation traffic |
| Yêu cầu `GET Order` | p99 dưới 150 ms |
| Yêu cầu danh sách gần đây | p99 dưới 250 ms |
| Reservation quan trọng | Không được trừ tồn kho hai lần |

Phân phối này cố ý **không đồng đều**. Nó đặt ra ba vấn đề khác nhau:

- T-A tạo **9.000 writes/s** trong đỉnh 20.000 writes/s.
- Nhóm 10 tenants tạo **14.400 writes/s**, các tenants còn lại tạo 5.600 writes/s.
- SKU bán chạy có thể dồn những cập nhật nguyên tử vào cùng một stock record hoặc cùng một nhóm replica.

Một thiết kế phân tán tốt phải tách được **hot tenant**, **hot SKU/state invariant** và **time hotspot**, vì chúng không luôn có chung lời giải.

### 2.2. Entity mẫu

~~~json
{
  "tenantId": "T-A",
  "orderId": "O-20261114-000001",
  "customerId": "C-789",
  "createdAt": "2026-11-14T11:31:00Z",
  "status": "PAID",
  "amountMinorUnits": 259900,
  "currency": "VND",
  "items": [
    {"sku": "SKU-HOT", "quantity": 1},
    {"sku": "SKU-OTHER", "quantity": 2}
  ],
  "version": 7
}
~~~

Một số nghiệp vụ có dữ liệu khác loại:

~~~text
Orders: mutable aggregate, lookup/update by tenant + orderId
OrderEvents: append-only audit history, often time-ordered
Inventory: mutable per SKU/warehouse stock invariant
OrderTimeline: query latest orders for a tenant
Search/Analytics: flexible cross-tenant filters or aggregates
~~~

**Không ép tất cả các collection/table vào cùng một partition-key strategy.** Khóa tốt cho append-only event timeline có thể tệ cho inventory counter, và ngược lại.

### 2.3. Những câu hỏi phải trả lời

1. Nếu dùng `tenantId` làm partition key, T-A có bị dồn vào một logical partition?
2. Nếu dùng `orderId` phân phối ngẫu nhiên, truy vấn `latest 50 orders of T-A` phải quét bao nhiêu partitions?
3. Nếu dùng `createdAt` theo range, writes mới có dồn vào cuối dải thời gian không?
4. Nếu thêm 16 buckets cho T-A, fan-out và correctness thay đổi thế nào?
5. Làm thế nào bảo đảm `reserve(SKU-HOT)` không oversell khi stock key được chia nhỏ?
6. Khi chuyển từ key v1 sang v2, những indexes, CDC consumers, idempotency và pagination cursors bị ảnh hưởng ra sao?

## 3. Thuật ngữ: cùng chữ “key” nhưng chức năng khác nhau

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Business identity | Xác định entity theo nghiệp vụ | `(tenantId, orderId)` |
| Primary key | Định danh record theo API/schema | Key hoặc tuple tùy engine |
| Partition/shard key | Chọn logical partition hoặc routing target | `tenantId`, `hash(orderId)`, `tenantBucket` |
| Sort/clustering key | Thứ tự records trong một partition hoặc index | `createdAt DESC, orderId` |
| Logical partition | Nhóm records có chung partition identity | Mọi events của tenant T-A ngày D |
| Physical partition/shard | Đơn vị lưu/routing vật lý hoặc logical container lớn hơn | Shard node group, service partition |
| Replica | Bản sao để HA/reads/durability | RF=3 hoặc managed replica set |
| Index key | Tăng tốc access path, không nhất thiết đổi placement | `(tenantId, status)` |
| Bucket/salt | Thành phần bổ sung để chia workload hot | `(tenantId, bucket)` |
| Routing directory | Bảng tra key range/tenant đến shard | `T-A -> [shard-2, shard-5]` |

Ví dụ `tenantId#07` chỉ là **bucket identity**; engine có thể tự hash giá trị này rồi gán lên physical partitions. **16 buckets không có nghĩa chắc chắn 16 nodes hoặc 16 physical partitions độc lập.**

### 3.1. Sharding khác replication

~~~text
Logical keyspace
  ├── Shard 0 -> Replica A, B, C
  ├── Shard 1 -> Replica D, E, F
  └── Shard 2 -> Replica G, H, I
~~~

Sharding chia **phạm vi dữ liệu/công việc**; replication lưu **nhiều copies** cho từng shard. Replication factor 3 không làm một key nóng có throughput gấp 3 nếu mọi mutation phải serialize/coordinate trên cùng logical item/partition.

### 3.2. “Đều dữ liệu” khác “đều tải”

Hai shards mỗi bên chứa 2 TiB nhưng:

~~~text
Shard A:  500 req/s
Shard B: 9,500 req/s
~~~

Dung lượng bằng nhau **không** nghĩa CPU, disk IOPS, network hoặc p99 bằng nhau. Một hot key trong B có thể làm throughput giới hạn dù A nhàn.

### 3.3. Physical capacity không chỉ là node count

Đặt thêm node giúp khi có thể **di chuyển hoặc chia được những partitions nóng**. Nếu toàn bộ writes bắt buộc cập nhật một document bằng compare-and-set, nút mới không phá được serialization point đó. Cần thay đổi **data model hoặc domain coordination protocol**, không đơn thuần thêm máy.

## 4. Đo skew trước khi thiết kế

### 4.1. Data skew và traffic skew

**Data skew**: dung lượng, số bản ghi hoặc kích thước record phân bố lệch.

**Traffic skew**: request count hoặc resource cost phân bố lệch, ví dụ một key nhỏ có nhiều GET/s.

**Temporal skew**: hoạt động lệch theo giờ, đặc biệt writes mới liên tục vào dải khóa cuối.

**Access skew**: một tập records được truy cập bất cân xứng so với phần còn lại, thường có heavy-tail/Zipf-like behavior.

Không đánh đồng số records với số **read/write IOPS**. Một write kích hoạt nhiều indexes/replicas hoặc một analytic scan lớn có chi phí cao hơn một point GET.

### 4.2. Top-k share

\[
\mathrm{TopKShare}=
\frac{\sum_{i=1}^{k} w_{(i)}}{\sum_{i=1}^{N} w_i}
\]

Trong đó \(w_i\) là lượng writes/reads/cost của key hay tenant i, và \(w_{(i)}\) sắp giảm dần.

Ví dụ:

~~~text
T-A:   45%
T-B:   10%
T-C:    6%
T-D:    5%
T-E:    3%
T-F:    3%
T-G:    2%
T-H:    2%
T-I:    2%
T-J:    2%
Others: 20%
~~~

Trong minh họa này Top1=45%; Top10=80% (khác với bộ giả định Top10=72% ở mục 2.1 vì đây là **một phân phối ví dụ độc lập**). Khi báo cáo thật, không trộn các phân phối hoặc cửa sổ quan sát khác nhau.

### 4.3. Max-to-mean load ratio

Giả sử 8 shards có write QPS:

~~~text
S0:  400
S1:  500
S2:  600
S3:  650
S4:  700
S5:  750
S6:  800
S7: 5,600
~~~

Tổng = 10.000 writes/s, trung bình 1.250 writes/s/shard.

\[
\mathrm{SkewRatio}=\frac{\max_i w_i}{\operatorname{mean}(w)}
=\frac{5600}{1250}=4{,}48
\]

Max-to-mean = **4,48** phản ánh một shard gánh 4,48 lần trung bình. Tuy nhiên cần đo thêm **capacity cụ thể**: shard nóng có thể chạy phần cứng mạnh hơn hoặc operations tốn tài nguyên khác nhau.

### 4.4. Gini coefficient

Gini có thể mô tả độ bất bình đẳng của phân phối tải:

\[
G=\frac{\sum_{i=1}^{n}\sum_{j=1}^{n}|x_i-x_j|}
{2n\sum_{i=1}^{n}x_i}
\]

Với mọi \(x_i\) đều bằng nhau, \(G=0\); gần 1 nghĩa tải tập trung rất mạnh khi n lớn. Không lấy Gini thay thế per-partition hotspot detection; một key chiếm 30% traffic vẫn nguy hiểm ngay cả khi tổng Gini từ nhiều keys có vẻ vừa phải.

### 4.5. Zipf-like workload

Trong nhiều workload, keys được xếp hạng \(i\) có xác suất gần:

\[
p_i\propto \frac{1}{i^\alpha}
\]

với \(\alpha\) điều chỉnh độ lệch. Đây là **mô hình tạo tải thử nghiệm**, không khẳng định dữ liệu nào cũng thật sự tuân Zipf. Cần dùng cả **real production top-k histogram** nếu có.

### 4.6. Phân phối theo nhiều chiều

Skew cần được xem qua:

~~~text
tenantId × operationType
tenantId × hour / burst window
tenantId × status
sku × warehouse
partitionKey × write/read/scan cost
shard × CPU/IO/network
requestRoute × fanout
~~~

Nếu gộp reads và writes, một tenant có nhiều cached reads có thể trông nóng hơn một tenant có writes đắt đỏ dù shard I/O không tương ứng.

## 5. Công thức cân đối tải: tính lower bound trước

Với \(N\) logical partitions/physical processing units có thể độc lập và total request rate \(R\), mức bình quân lý tưởng:

\[
R_{\mathrm{ideal}}=\frac{R}{N}
\]

Nhưng nếu một key có rate \(r_{\mathrm{hot}}\) và **không thể chia**, thì bất kỳ placement nào cũng có:

\[
R_{\mathrm{maxPartition}}\ge r_{\mathrm{hot}}
\]

Ví dụ 20.000 writes/s, 16 shards, mỗi shard lý tưởng 1.250 writes/s. T-A có 9.000 writes/s và toàn bộ T-A nằm trong một partition:

\[
R_{\mathrm{maxPartition}}\ge 9\,000
\]

Tức chỉ riêng T-A đã gấp **7,2 lần** mức bình quân. Dù hash đặt T-A lên shard ngẫu nhiên, vấn đề **không biến mất**.

### 5.1. Nếu chia T-A thành 12 buckets

Trong mô hình giả định writes của T-A được phân phối đều và độc lập trên buckets:

\[
\frac{9000}{12}=750\ \mathrm{writes/s/bucket}
\]

Phần traffic khác vẫn cần phân bổ, và **12 bucket chưa chắc ánh xạ tới 12 physical shards**. Cũng có thể có hot subkey nội bộ (một Order hoặc SKU) vẫn gây contention.

### 5.2. Không dùng phép chia đều làm cam kết

Lượng writes ngẫu nhiên theo bucket có biến động; một số buckets có thể dồn vào cùng host; read/transaction fan-out có chi phí khác writes. Cần **load test và đo mapped partitions/shards**, không tuyên bố đạt SLO chỉ từ 9.000/12.

### 5.3. Capacity theo cost, không chỉ số request

Nếu một small GET tốn 1 cost unit, một update + index write tốn 10 units và một scan tốn 1.000 units, tổng workload cost:

\[
C=\sum_{\mathrm{operationType}\ t}r_t c_t
\]

Thiết kế key cần phân tán **cost per partition** thay vì chỉ records count. Với managed services, dùng metrics thực tế như consumed request units/capacity/throttled requests thay cho cost unit giả.

## 6. Bắt đầu bằng access patterns, không bắt đầu bằng câu hỏi “hash gì?”

NoSQL thường tối ưu cho **một tập truy vấn và ghi được dự đoán trước**, không phải mọi biểu thức tùy ý đều có cùng chi phí. Hãy ghi các access patterns cụ thể trước khi quyết định partition key:

| ID | Truy vấn/thao tác | Filter, sort | Tần suất đỉnh | Yêu cầu |
| --- | --- | --- | ---: | --- |
| AP1 | `GET /tenants/{t}/orders/{id}` | `tenantId`, `orderId` | 15.000/s | Point lookup, low p99 |
| AP2 | Danh sách 50 đơn mới của tenant | `tenantId`, `createdAt DESC` | 4.000/s | Cursor ổn định, recent-first |
| AP3 | Danh sách đơn của customer | `tenantId`, `customerId`, time | 3.000/s | Không scan cả tenant |
| AP4 | Tạo Order | tenant + globally unique order ID | 20.000/s | Không duplicate |
| AP5 | Update status theo ID | `tenantId`, `orderId`, version | 8.000/s | CAS/idempotency |
| AP6 | Reserve stock | `sku`, `warehouse`, quantity | 10.000/s | Không oversell |
| AP7 | Aggregate doanh thu theo ngày | tenant + date range | batch | Eventual read model chấp nhận được |
| AP8 | Tra audit events của Order | tenant + order + sequence | 2.000/s | Theo đúng thứ tự phiên bản |

Giá trị tần suất trong bảng là **kịch bản minh họa**; các operations có thể overlap và không cộng trực tiếp thành total writes của mục 2.

### 6.1. Đánh dấu access pattern không thể thỏa bằng scatter-gather

AP1 và AP5 quan trọng và cần biết **partition routing deterministic**. AP2 có thể chấp nhận fan-out nhỏ có kiểm soát; AP7 có thể dùng materialized aggregate hoặc analytics store thay vì scan toàn cluster.

### 6.2. Đánh dấu yêu cầu nguyên tử

AP5 muốn update một Order có expectedVersion; nên cố gắng giữ toàn bộ fields cần CAS trong cùng phạm vi atomically updated mà engine hỗ trợ.

AP6 muốn bảo toàn `available >= 0`. Nếu chia tồn kho thành nhiều counters/buckets mà không có escrow/lease/reservation protocol đúng, cộng kết quả cuối cùng không giải quyết được **oversell trong lúc ghi đồng thời**.

### 6.3. Xác định loại dữ liệu nào có thể denormalize

Để phục vụ AP2/AP3, có thể tạo các **read-oriented projections**:

~~~text
Canonical Orders by (tenantId, orderId)
RecentOrdersByTenant as read projection
OrdersByCustomer as read projection
RevenueByDay as aggregate projection
~~~

Nhưng mỗi projection tạo chi phí duy trì, replay/CDC/repair và lựa chọn freshness. Không tuyên bố index/projection cập nhật **cùng transaction** nếu engine không hỗ trợ atomic multi-partition writes.

### 6.4. Ràng buộc chi phí quan trọng

Đánh giá thiết kế theo một hàm chi phí:

\[
\mathrm{Cost}=
w_1(\mathrm{writeHotspotRisk})
+w_2(\mathrm{queryFanout})
+w_3(\mathrm{storageOverhead})
+w_4(\mathrm{consistencyRisk})
+w_5(\mathrm{migrationCost})
\]

Các hệ số \(w_i\) do business SLO và rủi ro quyết định, không phải công thức tối ưu chung. Ví dụ giao dịch tài chính có thể chấp nhận read latency cao hơn để tránh distributed write anomalies.

## 7. Thiết kế A: partition key = tenantId

Giả sử:

~~~text
Partition key: tenantId
Sort key: createdAt#orderId

Partition T-A:
  Order O1
  Order O2
  ...
  millions of Orders
~~~

### 7.1. Ưu điểm

- AP2 (`latest orders by tenant`) có locality nếu sort/index hỗ trợ.
- Tenant isolation trong một số operations dễ lý giải.
- Ít fan-out cho một truy vấn theo tenant.

### 7.2. Nhược điểm

- Tenant lớn có thể thành **oversized/hot logical partition**.
- Tenant T-A chiếm 9.000 writes/s, mọi writes có thể bị đẩy vào cùng partition key.
- Một partition đơn có thể vượt capacity/size limit của engine hoặc trở thành hotspot theo topology.
- Queries theo Order ID không có tenant ID cần thêm lookup/secondary index.

### 7.3. Kết luận thực hành

`tenantId` là lựa chọn **đúng về truy vấn nhưng có thể sai về throughput** dưới dữ liệu lệch. Không vì có 5.000 tenants mà coi partition key có cardinality đủ cao: **distribution của traffic trên 5.000 values** mới quyết định.

## 8. Thiết kế B: partition key = orderId hoặc hash(orderId)

Giả sử Order IDs là đủ phân tán:

~~~text
Partition key: orderId
Record: Order

O1001 -> hash -> shard 12
O1002 -> hash -> shard 03
O1003 -> hash -> shard 27
~~~

### 8.1. Ưu điểm

- Writes mới thường phân phối đều hơn, kể cả tenant T-A.
- AP1 lookup theo Order ID có thể target một partition.
- AP5 update theo Order ID có thể target một item/document.

### 8.2. Nhược điểm

- AP2 truy vấn toàn bộ đơn của một tenant có thể **scatter-gather** qua nhiều shards nếu không có index/projection.
- AP3 theo customer tương tự.
- Tenant-level export/deletion khó hơn vì không có locality trong primary partition.
- Một hot **single orderId** vẫn hot dù hash(orderId) phân phối đa số IDs đẹp.

### 8.3. Đừng nhầm Order ID có dạng tăng dần với hash key

Nếu engine dùng **range sharding trên giá trị orderId tăng dần**, các inserts mới có thể dồn ở **end-of-range chunk**. Nếu dùng **hashed shard key** hoặc entropy có phân phối thực sự, behavior có thể khác. Phải phân biệt **key value distribution** và **partition routing strategy**.

### 8.4. Vì sao UUID không tự giải quyết?

UUID/ULID/Snowflake có đặc tính thứ tự và entropy khác nhau. Một UUID ngẫu nhiên được hash thường giúp phân tán **distinct IDs**, nhưng:

- Read AP2 cần thêm access path.
- Một ID bị cập nhật 100.000 lần/s vẫn là hot key.
- Giá trị gắn timestamp có thể tạo hotspot nếu range-partition theo prefix.
- Một số engine hash toàn composite key khác hash một field.

UUID không thay phân tích workload và storage engine.

## 9. Thiết kế C: tenantId + bucket(orderId)

Để chia hot tenant, tạo một **virtual bucket** dựa trên hàm hash ổn định:

\[
b=\operatorname{floorMod}(H(\mathrm{orderId}), B)
\]

Với \(B=16\):

~~~text
Partition key: (tenantId, bucket)
Sort/clustering key: (createdAt, orderId)

T-A#00 -> Orders subset
T-A#01 -> Orders subset
...
T-A#15 -> Orders subset

T-B#00 -> ...
~~~

### 9.1. Write distribution

Giả sử T-A có 9.000 writes/s, mỗi Order ID đủ phân tán và 16 buckets có hiệu lực:

\[
9000/16=562{,}5\ \mathrm{writes/s/bucket}
\]

Đây là **mức kỳ vọng trung bình** cho riêng T-A, không phải giới hạn cứng. Những buckets có thể cùng host hoặc có hot order riêng; cần test.

### 9.2. Point lookup AP1

Nếu biết `(tenantId, orderId)`, client tính bucket deterministic rồi query một partition:

~~~text
bucket = floorMod(stableHash(orderId), 16)
partitionKey = tenantId + "#" + bucket
sortKey = orderId or createdAt#orderId
~~~

Nếu sort key bắt đầu bằng `createdAt` mà lookup chỉ có `orderId`, **không biết toàn sort key**. Cần:

- Một `OrdersById` table/index với point lookup.
- Hoặc sort key thiết kế bắt đầu theo orderId.
- Hoặc directory mapping `orderId -> createdAt/bucket`.

Tránh viết “point GET là O(1)” chỉ vì đã tính bucket trong khi sort key vẫn thiếu.

### 9.3. Query recent orders AP2

Để lấy **50 Orders mới nhất của tenant T-A**, phải query 16 buckets (tối đa theo thiết kế), lấy top candidates rồi merge sort.

~~~text
For bucket in 0..15:
    query latest orders for tenant+bucket
Merge ordered streams
Return global top 50
~~~

Không thể lấy top 50 từ bucket 00 rồi coi là top 50 toàn tenant.

### 9.4. Chi phí fan-out

Nếu \(B=16\), một logical tenant timeline read có thể tạo **16 partition reads**, làm tăng RU/IO/network và tail latency. Số calls thực phụ thuộc API hỗ trợ batch, index/projection và pagination; **16 bucket không tự là 16 network round trips tuần tự** nếu được parallelize.

Một thiết kế tốt phải cân bằng **write sharding** với **read fan-out**.

### 9.5. Pagination không còn đơn giản

Cursor không thể chỉ là `lastCreatedAt` nếu từng bucket có progress riêng và nhiều Orders trùng timestamp. Một cursor bền cần:

~~~json
{
  "keyVersion": 2,
  "tenantId": "T-A",
  "bucketCount": 16,
  "perBucketCursor": {
    "0": "opaque-0",
    "1": "opaque-1",
    "15": "opaque-15"
  },
  "tieBreaker": {
    "createdAt": "2026-11-14T10:00:00Z",
    "orderId": "O-200"
  }
}
~~~

Cursor cần encode đúng **snapshot/freshness contract**: nếu data thay đổi giữa các trang, có thể thấy records mới/duplicates/misses trừ khi query snapshot/cut được engine hỗ trợ. `tieBreaker` giúp order ổn định nhưng **không tự tạo snapshot isolation**.

## 10. Chọn bucket count B: không có một số luôn đúng

### 10.1. Một bảng đánh đổi

Với T-A 9.000 writes/s và giả định hash orderId phân tán đều:

| B | Writes trung bình/bucket | Fan-out tối đa để đọc timeline T-A |
| ---: | ---: | ---: |
| 1 | 9.000 | 1 |
| 2 | 4.500 | 2 |
| 4 | 2.250 | 4 |
| 8 | 1.125 | 8 |
| 16 | 562,5 | 16 |
| 32 | 281,25 | 32 |
| 64 | 140,625 | 64 |

Không chọn 64 chỉ vì writes phân tán đẹp: AP2 đọc 50 Orders gần nhất có thể phải chạm 64 buckets, gây p99/fan-out cao và tốn read units.

### 10.2. Sizing theo mục tiêu capacity

Nếu một logical bucket nên nhận tối đa **800 writes/s ở peak** (giả định từ load test, sau khi chừa headroom):

\[
B_{\mathrm{min}}=\left\lceil\frac{9000}{800}\right\rceil=12
\]

Chọn \(B=16\) có thể giúp hash modulo thuận tiện, nhưng **power of two không phải bắt buộc** và `B_min=12` không chứng minh physical placement độc lập. Cần tính thêm per-bucket storage, read fan-out và skew.

### 10.3. B có thể khác theo tenant

Giả sử:

~~~text
Small tenants: B=1
Medium tenants: B=4
T-A hot tenant: B=16
~~~

Điều này tránh 5.000×16 partitions vô ích. Nhưng client cần **bucket policy lookup** theo tenant, routing/cache policy và versioning. Khi T-A từ 16→32, point lookup old data không tự chuyển buckets nếu chỉ đổi `B` ở client.

### 10.4. Bảo vệ key-version compatibility

Một manifest:

~~~yaml
tenantPartitionPolicies:
  T-A:
    activeVersion: 2
    bucketCount: 16
    routingAlgorithm: "sha256-truncated-modulo"
    migrationState: "CUTOVER"
  T-B:
    activeVersion: 1
    bucketCount: 1
    migrationState: "STABLE"
~~~

**Đây là metadata mẫu**, không phải cấu hình chung của NoSQL. Thay bucket count phải đi cùng **backfill/rekey + read routing đúng phiên bản** hoặc sử dụng một policy immutable cho historical records.

### 10.5. Modulo gây remapping khi B đổi

Với `bucket = hash(id) mod B`, khi B đổi từ 16→32, nhiều IDs sẽ trỏ bucket mới. Nếu records cũ không di chuyển, điểm GET theo policy mới có thể **không thấy record**. Các phương án:

- Giữ `keyVersion`/B của từng record hoặc directory.
- Query old+new placement trong migration window, có dedup/version guard.
- Backfill/repartition toàn bộ với checkpoint rồi cutover.
- Dùng virtual shards cố định + routing table thay vì thay modulus của data key.

**Không tự đổi một hằng số `BUCKETS` trong code production** và coi là scale-out không cần migration.

## 11. Thiết kế D: time buckets cho event và lịch sử

Giả sử cần lưu append-only events:

~~~json
{
  "tenantId": "T-A",
  "orderId": "O-123",
  "eventId": "E-987",
  "occurredAt": "2026-11-14T10:10:15.123Z",
  "eventType": "OrderPaid",
  "aggregateVersion": 4
}
~~~

Một khóa gợi ý:

~~~text
Partition key: tenantId#YYYY-MM-DD
Clustering/sort key: occurredAt#eventId
~~~

### 11.1. Vì sao bucket theo ngày hữu ích?

- Giới hạn phạm vi lịch sử cần quét.
- Có thể archive/drop/TTL theo retention window với công cụ phù hợp.
- Truy vấn events theo thời gian dễ khoanh vùng.

### 11.2. Nhưng hôm nay có thể là một hot partition

Nếu T-A tạo 9.000 events/s trong ngày flash sale, partition `T-A#2026-11-14` vẫn nhận 9.000/s. Time bucketing đơn lẻ chỉ tách **hôm qua và hôm nay**, không chia được **concurrent load trong hôm nay**.

### 11.3. Time bucket + hash subbucket

~~~text
Partition key:
  tenantId#date#bucket(orderId, B)

Sort key:
  occurredAt#eventId
~~~

Ví dụ T-A dùng 16 subbuckets/ngày, mỗi bucket lý tưởng nhận ~562,5 events/s khi 9.000 events/s được trải theo orderId.

### 11.4. Chọn granularity phù hợp

| Time bucket | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Year | Ít partitions | Partitions cực lớn/nóng |
| Month | Dễ archive theo kỳ | Tenant nóng vẫn dồn writes |
| Day | Cân bằng lịch sử và query | Hot-day cần subbucket |
| Hour | Mỗi partition nhỏ | Nhiều partitions; current hour vẫn hot |
| Minute | Size nhỏ, dễ expire | Metadata/read fan-out lớn, burst vẫn hot |

Không chọn bucket càng nhỏ càng tốt. Granularity nên dựa trên **bytes/partition, peak writes/partition, retention and query time range**, có test fan-out.

### 11.5. UTC và timestamp precision

Thiết kế bucket theo `UTC day` tránh lỗi do timezone/DST. Nếu business cần báo cáo theo local day, chuyển timestamp theo **tenant's time zone policy** khi truy vấn hoặc lưu thêm day key có ý nghĩa nghiệp vụ. Phải phân biệt event time (`occurredAt`) và ingestion time (`receivedAt`) vì late events có thể đến sau ngày phát sinh.

### 11.6. Late-arriving event

Event xảy ra hôm qua nhưng nhận hôm nay:

~~~text
occurredAt=2026-11-13T23:59:00Z
receivedAt=2026-11-14T00:10:00Z
~~~

Nếu bucket theo `occurredAt`, writer phải route vào partition ngày 13, kể cả ngày 14 đang active. Nếu bucket theo `receivedAt`, query theo event time cần xử lý out-of-order records. Đây là **chọn semantic của thời gian**, không phải chỉ format key.

## 12. Thiết kế E: directory/virtual shards để mở rộng hot tenant

Một cách khác là tạo **số lượng virtual buckets cố định đủ lớn**, sau đó map chúng đến physical shard groups:

~~~text
Logical virtual bucket:
  hash(orderId) mod 128

Routing directory:
  bucket 0..31   -> shard group A
  bucket 32..63  -> shard group B
  bucket 64..95  -> shard group C
  bucket 96..127 -> shard group D
~~~

Khi cluster thêm physical nodes, có thể **chuyển ownership của virtual buckets** mà không đổi business key. Tuy nhiên:

- Cần directory/mapping version nhất quán giữa clients/routers.
- Đổi ownership phải thực hiện online reshard/rebalance có fencing/catch-up.
- Số virtual buckets quyết định granularity tối thiểu của placement.
- Một virtual bucket đã quá nóng vẫn cần subpartition/higher virtual count hay thay access pattern.

### 12.1. Virtual bucket không phải vật lý replica

Mỗi bucket có thể được replicate trên nhiều nodes; routing directory phải biết primary/leader hoặc engine-owned ownership. Không viết application router tùy tiện cạnh tranh với MongoDB `mongos`, Cassandra token-aware driver hay DynamoDB managed placement nếu đã có routing layer phù hợp.

### 12.2. Consistent hashing vs modulo

Modulo đơn giản đổi \(B\) sẽ remap nhiều keys. Consistent hashing/rendezvous hashing có thể giảm **mức độ remapping giữa nodes** khi topology thay đổi, nhưng:

- Không giải quyết một hot key.
- Cần deterministic stable hashing và membership mapping.
- Không thay engine-native resharding requirements.
- Nếu application key đã lưu theo shard-specific format, đổi routing vẫn cần migration.

### 12.3. Control plane cũng phải HA

Nếu directory dùng một Redis node duy nhất và nó lỗi, mọi Java client có thể không route được dù data shards khỏe. Cần versioned metadata, cache/watch invalidation, expiry/fallback policy, consistency/atomic cutover và recovery plan cho directory.

## 13. Hot key khác hot partition: trường hợp inventory SKU-HOT

Giả sử `SKU-HOT` có 6.000 reservations/s trong flash sale. Mỗi reservation cập nhật:

~~~text
Inventory(warehouse=W1, sku=SKU-HOT):
  available = available - quantity
  reserved = reserved + quantity

Invariant:
  available >= 0
~~~

Nếu một record cần atomic compare-and-update, **key `(W1,SKU-HOT)` là serialization hotspot**. Hash SKU lên shard khác chỉ thay **nút bị nóng**, không phá serialized write bottleneck.

### 13.1. Sai lầm: chia counter thành 16 buckets rồi trừ bất kỳ bucket

~~~text
inventoryAvailable[0..15] each holds a number
write chooses random bucket
read sums all buckets
~~~

Nếu mỗi bucket tự quyết định số lượng mà không được cấp quota hợp lệ, hai workers có thể đồng thời “bán đơn vị cuối cùng” ở hai buckets khác nhau. Tổng negative hoặc oversell là **vi phạm bất biến nghiệp vụ**. Không biến inventory accounting thành eventual sum một cách tùy tiện.

### 13.2. Escrow/quota allocation

Một phương án có thể **phân bổ trước quotas**:

~~~text
Total stock: 1,000 units
Bucket 0 escrow: 200
Bucket 1 escrow: 200
Bucket 2 escrow: 200
Bucket 3 escrow: 200
Bucket 4 escrow: 200

Each bucket grants reservations <= its owned escrow balance.
~~~

Nếu tổng quotas được chuyển giao nguyên tử và không cấp phát trùng, mỗi bucket có thể serialize riêng mà vẫn giữ global available>=0. Nhưng cần giao thức:

- Một authority cấp quota ban đầu, bảo đảm tổng escrow ≤ stock hiện có.
- Atomic conditional decrement per bucket.
- Chuyển quota giữa buckets an toàn, không tạo hoặc mất units.
- Expiration/cancel/release reservation có idempotency.
- Reconciliation khi worker/region chết hoặc có unknown commit outcome.

### 13.3. Chuyển quota là một transaction nghiệp vụ

~~~text
Transfer 20 units from Bucket A to Bucket B.

Must not make both buckets able to sell the same 20 units
while A/B messages are in flight.
~~~

Có thể dùng một nguồn authority phát lease/escrow tokens hoặc transaction protocol phù hợp. Nếu không thiết kế được bất biến này, **chấp nhận throughput thấp hơn nhưng giữ một stock authority** có thể là lựa chọn an toàn hơn.

### 13.4. Inventory cập nhật trạng thái khác event append

Events `OrderCreated`, `StockReserved` là records riêng có thể append trên các buckets; nhưng state `available` có tính nguyên tử và thường cần conditional update/ledger. Đừng vì event log scale tốt mà giả định **aggregate stock invariant** cũng scale theo.

### 13.5. Kiểm thử concurrency

Một test:

~~~text
Initial stock: 100
Concurrent clients: 1,000
Each attempts reservation quantity=1
Injected faults: timeout after commit, duplicate retry, worker restart
Expected:
  exactly 100 successful unique reservation IDs
  remaining stock never below 0
  900 rejected/not allocated requests
  no idempotency duplicate effects
~~~

Nếu hệ cho phép cancellation/release trong test, kỳ vọng phải điều chỉnh theo những release commits; cần chốt workload model thay vì áp con số 100 cứng cho mọi lịch.

## 14. Secondary indexes và read models: trả giá cho phân phối write

Một key dựa `orderId` phân tán tốt nhưng AP2 theo tenant+time trở nên khó. Có thể dùng:

~~~text
Primary Orders:
  key = (tenantId, orderId)
  storage/routing hashed on orderId or tenant#bucket

RecentOrdersByTenant:
  key = (tenantId, date, bucket)
  sort = createdAt DESC, orderId

OrdersByCustomer:
  key = (tenantId, customerId, bucket)
  sort = createdAt DESC, orderId
~~~

Đây là **logical access-path plan**; implementation có thể là secondary index, GSI, materialized view, dedicated table, stream processor hoặc search engine tùy sản phẩm.

### 14.1. Read amplification

Nếu timeline T-A có 16 buckets, một query top50 thực hiện 16 routed reads và merge:

\[
\mathrm{ReadFanout}\le16
\]

Nếu mỗi bucket lấy 50 candidates, worst-case có thể đọc tới \(16\times50=800\) records trước khi merge (bỏ qua optimizations/lazy paging), để trả 50. Tỷ lệ candidates/returned là **16×**.

Không bắt buộc đọc 50 từ mọi bucket trong một implementation tối ưu; có thể dùng **k-way merge, adaptive prefetch hoặc maintained top-N projection** nếu đáp ứng semantics.

### 14.2. Write amplification

Mỗi Order mutation có thể cập nhật:

~~~text
Canonical Orders
RecentOrdersByTenant
OrdersByCustomer
Analytics/change stream
~~~

Nếu ba stores được duy trì bằng 3 writes, raw mutation calls có thể tăng 3 lần hoặc hơn; replication/index cost riêng. Phải đo chi phí **write amplification + eventual consistency lag + replay correctness**.

### 14.3. Projection lag và causal reads

Một Order vừa được tạo ở primary có thể chưa xuất hiện trong `RecentOrdersByTenant` projection. Nếu API hứa read-your-writes, dùng session version/watermark, read-after-write fallback sang canonical source hoặc cơ chế đồng bộ được hỗ trợ; không trả “không tìm thấy” mà không hiểu delay.

### 14.4. Cross-tenant aggregate

Một báo cáo `top products across all tenants` không nên giả định primary key theo tenant phục vụ tốt. Có thể dùng stream analytics/OLAP hoặc pre-aggregated model; tránh scan hàng triệu tenant partitions trong synchronous API.

## 15. Chi phí ghi và hot index

Một data table đã được hash đều nhưng một **secondary index theo timestamp** vẫn có thể hotspot nếu mọi inserts dùng sort key tăng dần và index partition strategy tập trung.

### 15.1. Hot base table vs hot index

~~~text
Orders base writes:  spread across shards
GSI on createdAt:    all new writes target latest time range
~~~

Điểm nghẽn có thể nằm ở index write path; đo throttling/index partition cost riêng thay vì chỉ histogram của primary partition keys.

### 15.2. Bucketing index

Ví dụ index theo ngày + random bucket:

~~~text
GSI partition: YYYY-MM-DD#bucket(orderId)
GSI sort:      createdAt#orderId
~~~

Đọc global latest của ngày D phải query nhiều buckets; nếu cần “latest toàn hệ” với p99 thấp, có thể duy trì **bounded top-K feed** riêng.

### 15.3. Unique constraints toàn cluster

Phân tán Order IDs lên nhiều buckets có thể khiến kiểm soát uniqueness cross-shard khó. Dùng ID globally unique (với collision policy), unique directory/conditional reservation hoặc engine-supported global unique index; **đừng chỉ gọi `exists` rồi insert ở shard khác** vì race.

### 15.4. Fan-out làm tail latency

Một read cần 16 subqueries thành công thì tổng p99 có thể cao hơn p99 một subquery, ngay cả khi chạy song song. Nếu mỗi call có 1% xác suất chậm độc lập, xác suất ít nhất một trong 16 chậm:

\[
P(\ge1\text{ slow})=1-(1-0{,}01)^{16}\approx14{,}85\%
\]

Đây chỉ là ví dụ với **independent events**; faults trong cluster có thể correlated. Nhưng nó giải thích tại sao fan-out cao làm aggregate tail latency khó đạt.

### 15.5. Query fan-out và deadline

Nếu 16 subreads có deadline 100ms, API top50 không nên chờ từng subread 100ms tuần tự. Cần concurrent plan với bounded fan-out, per-subquery deadline, cancellation và clear partial-result policy. Không trả “top50 đầy đủ” nếu một bucket bị bỏ qua do timeout mà không công bố partial/staleness semantics.

## 16. Java 17: hàm bucket ổn định để các service thống nhất

Một bài thực hành thiết kế partition key cần bảo đảm **mọi worker/SDK/ngôn ngữ tính cùng bucket cho cùng business key và cùng key version**. Tránh dùng `String.hashCode()` vô tình khi hệ gồm nhiều languages và không có đặc tả canonicalization chung.

### 16.1. Hàm hash minh họa

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class OrderBucket {
    private OrderBucket() {}

    public static int bucket(String orderId, int bucketCount) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("Invalid bucket count");
        }

        byte[] id = orderId.getBytes(StandardCharsets.UTF_8);
        final byte[] digest;
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            digest = md.digest(id);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }

        // First 4 digest bytes interpreted as unsigned 32-bit
        // big-endian, then integer modulo bucketCount.
        int prefix = ByteBuffer.wrap(digest, 0, 4)
            .order(ByteOrder.BIG_ENDIAN)
            .getInt();
        return Integer.remainderUnsigned(prefix, bucketCount);
    }

    public static String partitionKey(
        String tenantId, String orderId, int bucketCount
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenantId");
        }
        return tenantId + "#" + bucket(orderId, bucketCount);
    }
}
~~~

Đây là **hashing/routing minh họa cho application-level bucket**, không thay engine-native partition hashing. SHA-256 có chi phí CPU, nhưng chủ đích là một protocol dễ định nghĩa xuyên ngôn ngữ, không phải thuật toán hash nhanh nhất.

### 16.2. Các rủi ro thường bị bỏ sót

- **Canonicalization:** `"O-123"` khác `"o-123"` và khác Unicode normalization form; phải quy định chính xác identity.
- **Delimiter collision:** `tenantId + "#" + bucket` chỉ an toàn nếu escaping/encoding tenantId rõ; nên dùng tuple fields nếu engine hỗ trợ.
- **Hash version:** SHA-256 first 32 bits big-endian khác CRC32/FNV/Murmur3 và khác việc dùng toàn 256 bits.
- **Modulo bias:** 32-bit space không chia hết cho mọi B; bias nhỏ trong phần lớn thiết kế nhưng phải hiểu khi đòi phân phối cực chính xác.
- **Bucket collisions:** hai orderIds cùng bucket không phải lỗi; partition key được thiết kế để gom nhiều orders.
- **Routing ownership:** cùng bucket có thể nằm chung physical shard với bucket khác.
- **Permission/tenant identity:** không tin tenantId do client tùy ý gửi; verify authorization để tránh cross-tenant access.

### 16.3. Test vectors là hợp đồng

Khi các ứng dụng Java, Python, Node và CDC workers đều tính bucket, hãy lưu các **test vectors từ một implementation chuẩn được phê duyệt**:

~~~json
{
  "algorithm": "sha256_first_uint32_be_mod_bucketCount",
  "keyVersion": 2,
  "canonicalization": "exact UTF-8 bytes",
  "examples": [
    {"orderId": "O-001", "bucketCount": 16, "expected": "from-reference-run"},
    {"orderId": "O-002", "bucketCount": 16, "expected": "from-reference-run"}
  ]
}
~~~

Không tự điền số expected bằng suy đoán. Những vectors cần được tạo và ký duyệt trong implementation test, rồi dùng ở mọi service để ngăn lệch routing.

## 17. Java: bộ tạo phân phối Zipf-like cho thí nghiệm

Để so sánh key strategies, cần **đưa vào cùng một chuỗi workload**, thay vì mỗi thiết kế nhận tập requests khác nhau.

### 17.1. Sampler theo CDF

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;

public final class ZipfSampler {
    private final double[] cdf;
    private final SplittableRandom random;

    public ZipfSampler(int keyCount, double alpha, long seed) {
        if (keyCount < 1 || !Double.isFinite(alpha) || alpha < 0) {
            throw new IllegalArgumentException("Invalid distribution");
        }
        this.random = new SplittableRandom(seed);
        this.cdf = new double[keyCount];
        double total = 0.0;
        for (int rank = 1; rank <= keyCount; rank++) {
            total += 1.0 / Math.pow(rank, alpha);
        }
        double cumulative = 0.0;
        for (int rank = 1; rank <= keyCount; rank++) {
            cumulative += (1.0 / Math.pow(rank, alpha)) / total;
            cdf[rank - 1] = cumulative;
        }
        cdf[keyCount - 1] = 1.0; // Avoid a rounding gap at the tail.
    }

    public int sampleRankZeroBased() {
        double u = random.nextDouble();
        int index = Arrays.binarySearch(cdf, u);
        if (index < 0) {
            index = -index - 1; // First CDF >= u.
        }
        return Math.min(index, cdf.length - 1);
    }
}
~~~

Với `alpha=0`, các ranks gần đồng xác suất. Khi `alpha` cao, những ranks đầu được chọn thường xuyên hơn. `SplittableRandom` tạo tập mô phỏng tái lập bằng seed, **không dùng cho cryptographic security**.

### 17.2. Vì sao cần seed?

Hai chiến lược key nên chạy với:

~~~text
same tenant distribution
same ordered sequence of logical operations
same request sizes
same hot periods and query mix
same experiment duration
same random seed
~~~

Nhờ vậy sự khác biệt giữa shard heatmaps chủ yếu đến từ **routing/key choice**, không do bộ random tạo ra những đợt traffic khác nhau.

### 17.3. Zipf không thể mô phỏng đủ mọi skew

Một workload thật có thể có:

- **Single-key flash crowd:** một SKU bất ngờ chiếm 60% requests.
- **Diurnal cycles:** khác biệt theo giờ và quốc gia.
- **Tenant growth:** tenants mới có tốc độ tăng khác nhau.
- **Moving hotspot:** key nóng đổi liên tục.
- **Time-order append:** các record mới theo timestamp.
- **Correlated workloads:** một event tạo nhiều index writes.

Do đó chạy nhiều distributions: uniform baseline, Zipf alpha thấp/cao, **one-key concentration**, bursts, shifting top tenants, late arrivals và data-size skew.

## 18. Java: thống kê phân bố giữa physical shards

Giả sử đã có một mapping **mô phỏng** từ logical record → physical shard index. Đếm total writes để xem skew:

~~~java
import java.util.Arrays;

public final class ShardLoadStats {
    public static void print(long[] writesByShard) {
        if (writesByShard.length == 0) {
            throw new IllegalArgumentException("No shards");
        }
        long total = 0L;
        long max = 0L;
        long min = Long.MAX_VALUE;
        for (long count : writesByShard) {
            if (count < 0L) throw new IllegalArgumentException("Negative count");
            total += count;
            max = Math.max(max, count);
            min = Math.min(min, count);
        }
        double mean = (double) total / writesByShard.length;
        double skew = mean == 0.0 ? 0.0 : max / mean;
        System.out.println("writesByShard=" +
                           Arrays.toString(writesByShard));
        System.out.printf(
            "total=%d, min=%d, max=%d, mean=%.2f, maxToMean=%.2f%n",
            total, min, max, mean, skew
        );
    }
}
~~~

### 18.1. Một driver mô phỏng độc lập

~~~java
import java.util.SplittableRandom;

public final class SimpleShardSimulation {
    public static void main(String[] args) {
        int shardCount = 16;
        int tenantCount = 5_000;
        long[] byTenantKey = new long[shardCount];
        long[] byOrderIdKey = new long[shardCount];
        long[] byTenantBucket = new long[shardCount];

        ZipfSampler tenantPopularity =
            new ZipfSampler(tenantCount, 1.2, 42L);
        SplittableRandom ids = new SplittableRandom(2026L);

        for (int i = 0; i < 1_000_000; i++) {
            int tenant = tenantPopularity.sampleRankZeroBased();
            String tenantId = "T-" + tenant;
            String orderId = "O-" + ids.nextLong();

            int tenantRoute =
                OrderBucket.bucket(tenantId, shardCount);
            int orderRoute =
                OrderBucket.bucket(orderId, shardCount);
            int subbucket =
                OrderBucket.bucket(orderId, 16);

            // Toy physical mapping ONLY:
            int compositeRoute =
                OrderBucket.bucket(tenantId + "#" + subbucket,
                                   shardCount);
            byTenantKey[tenantRoute]++;
            byOrderIdKey[orderRoute]++;
            byTenantBucket[compositeRoute]++;
        }

        System.out.println("Tenant-only routing");
        ShardLoadStats.print(byTenantKey);
        System.out.println("Order-ID routing");
        ShardLoadStats.print(byOrderIdKey);
        System.out.println("Tenant + order subbucket routing");
        ShardLoadStats.print(byTenantBucket);
    }
}
~~~

**Giới hạn của mô phỏng:**

- Đây là **toy placement hash**, không phải routing thật của MongoDB/Cassandra/DynamoDB/Cosmos.
- Sample thực hiện **một write cho mỗi Order ID mới**; nó chưa mô phỏng hot existing Order/Inventory key.
- Mapping composite buckets có thể trùng physical shards.
- Số request count không phản ánh IO/CPU cost của operation hoặc replication.
- Để đánh giá engine thật, chạy cùng workload qua SDK và lấy **actual partition/shard metrics**.

### 18.2. Một thí nghiệm phản chứng quan trọng

Đổi vòng lặp thành **80% writes luôn cập nhật cùng `orderId="O-HOT"`**. Dù partition routing theo Order ID khá đồng đều trên dữ liệu mới, lần update liên tục vào O-HOT vẫn tập trung tại **một routing partition**. Kết luận: key cardinality cao không loại bỏ hotspot nếu workload updates theo một key cực nóng.

### 18.3. Đo bytes và cost thay count

Có thể mở rộng simulator:

~~~text
request:
  logicalKey
  operationType
  bytesRead
  bytesWritten
  indexWriteCount
  partitionRouting
  latency
~~~

Tổng hợp per-shard:

- Reads/s và writes/s.
- Total read/write bytes.
- Distinct hot keys.
- Max/mean cost.
- Predicted fan-out.
- Simulated overloaded intervals.

Sau đó kiểm chứng trong staging bằng driver metrics, vì capacity thực không tỷ lệ tuyến tính với simulated cost units.

## 19. MongoDB: hashed shard key, ranged key và jumbo/hot chunks

MongoDB sharded cluster có **shard key**, **chunks/ranges**, `mongos` routers và balancer/resharding features theo phiên bản. Chọn shard key cần xét **đường truy vấn, cardinality, frequency và monotonicity**, không chỉ distinct values.

### 19.1. Ví dụ shard key theo tenantId

~~~javascript
// Ví dụ KHÁI NIỆM về key; không chạy shardCollection
// hoặc reshardCollection trên production nếu chưa có plan.
{
  tenantId: "T-A",
  orderId: "O-100"
}
~~~

Nếu `tenantId` là shard key, một tenant rất nóng có thể dồn vào key range/placement không chia tiếp được theo mong muốn của workload. Một shard key có **low effective cardinality dưới traffic** cũng có thể khiến load lệch ngay cả khi tổng tenants lớn.

### 19.2. Hashed shard key

Hashing một field có nhiều distinct values có thể làm writes phân tán tốt hơn so với range trên increasing values:

~~~text
Ranged increasing orderId:
  many newest writes -> end of current range

Hashed orderId:
  distinct orderIds -> spread across hash keyspace
~~~

Nhưng nếu một Order ID đang hot, hashed shard key vẫn chỉ đặt **một document/identity** ở một shard; MongoDB không nhân một document thành nhiều independent write authorities.

### 19.3. Targeted vs scatter-gather queries

Một query có đầy đủ shard-key routing constraints thường có khả năng **target** một tập shards nhỏ; query không có shard key có thể phải broadcast/scatter-gather. Query planner/indexes giúp chọn access paths nhưng **không tự xóa fan-out giữa shards**.

Ví dụ:

~~~javascript
// Nếu shard key/routing hỗ trợ:
db.orders.findOne({tenantId: "T-A", orderId: "O-100"});

// Chỉ có status có thể fan-out rộng:
db.orders.find({status: "PAID"}).limit(20);
~~~

Không kết luận targeted chỉ từ việc predicate chứa một field **không thuộc shard-key prefix/compound routing rules**; phải xem query targeting thực của phiên bản/topology.

### 19.4. Compound keys và order

Sắp xếp fields trong compound shard key có thể thay đổi router targeting:

~~~text
(tenantId, orderId)
versus
(orderId, tenantId)
~~~

Một key đặt tenant trước có thể giữ locality tenant trong một số chiến lược; hashed/ranged component và split behavior quyết định khả năng tránh hotspots. Cần kiểm tra tài liệu của MongoDB version đang dùng và explain/shard statistics.

### 19.5. Resharding không thay đổi invariants

Khi đổi shard key, cần:

- Theo dõi balancer/migration/resharding progress.
- Đo source/target load trong quá trình copy và catch-up.
- Kiểm soát write amplification và storage headroom.
- Đảm bảo transaction/idempotency correctness.
- Cập nhật index/query planning và ứng dụng.

Một resharding thành công về metadata không tự chứng minh **p99 thấp** hoặc tenants đã phân bố tốt.

### 19.6. Những số liệu phải lấy

~~~text
per-shard dataSize / docs
per-shard read/write ops and CPU
number and size distribution of chunks/ranges
balancer/migration activity
targeted vs broadcast query ratio
hot-key patterns
query p95/p99 and index usage
~~~

Không dùng số chunks gần bằng nhau làm chứng minh traffic đã cân bằng.

## 20. Cassandra/ScyllaDB: partition key và clustering columns

Trong Cassandra/ScyllaDB, **partition key được hash thành token**, rồi placement theo token ranges/replica strategy; clustering columns quyết định thứ tự các rows bên trong logical partition. Khác với một số engines khác, **tập dữ liệu cùng partition key có tính locality rất mạnh** cho reads.

### 20.1. Thiết kế sai khi tenant cực lớn

~~~sql
-- Schema minh họa anti-pattern đối với hot tenant
CREATE TABLE order_events_by_tenant (
    tenant_id text,
    event_time timestamp,
    event_id text,
    payload text,
    PRIMARY KEY ((tenant_id), event_time, event_id)
);
~~~

Toàn bộ lịch sử của T-A nằm trong một logical partition, có thể phát triển quá lớn và nhận quá nhiều writes. Thêm nodes không chia được `tenant_id=T-A` ra nhiều partition keys độc lập.

### 20.2. Time + hash bucket

~~~sql
CREATE TABLE order_events_by_tenant_day_bucket (
    tenant_id text,
    day_utc date,
    bucket smallint,
    event_time timestamp,
    event_id text,
    order_id text,
    payload text,
    PRIMARY KEY (
        (tenant_id, day_utc, bucket),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

Đây là một **schema ví dụ**, cần rà soát data type, compaction/TTL, query patterns và phiên bản CQL khi dùng thật. Bài học chính là `(tenant_id, day_utc, bucket)` nằm trong **đôi ngoặc composite partition key**.

### 20.3. Đúng clustering order vẫn phải query nhiều buckets

Từng partition trả events theo descending time; để lấy global latest 50 trong tenant/day, query toàn bộ buckets ứng với ngày đó và merge. Cassandra không tự cung cấp global ORDER BY qua tất cả partition keys như một bảng quan hệ tổng quát.

### 20.4. Partition size matters

Một partition quá lớn gây:

- Read amplification/long scans.
- Memory/storage pressure theo size.
- High compaction/tombstone costs.
- Hot replica set và repair time.

Chọn day/hour và B dựa trên **bytes per partition**, không chỉ write QPS.

### 20.5. TTL và time-bucket deletion

TTL có thể sinh tombstones, compaction/repair obligations. Một schema theo ngày cho phép quản lý retention theo partitions/tables trong một số data models, nhưng không được tự xóa tombstones/giảm GC grace khi replica chưa đồng bộ.

### 20.6. LWT/conditional mutation

Lightweight transactions/conditional writes có cost và semantics riêng, không dùng như write-sharding primitive tùy ý cho một inventory counter nóng. Nếu business cần `stock>=0`, test đúng serializable invariant/escrow scheme, không đếm update ACK từ nhiều partitions như một giao dịch nguyên tử.

### 20.7. Token aware driver

Java driver có thể biết partition key và route tới coordinator phù hợp. Nếu application bỏ các partition key components hoặc dùng key encoding không nhất quán, token routing và query efficiency có thể giảm. Cần test actual request routing/replica and slow partitions.

## 21. DynamoDB: partition key, sort key, GSIs và hot items

DynamoDB là dịch vụ managed phân phối dữ liệu dựa trên **partition key**; partition key và sort key cùng xác định item identity trong table có composite primary key. Không giả định một logical partition key đồng nghĩa một máy cố định trong mọi thời điểm; service có thể có những cơ chế split/auto-scaling riêng tùy access pattern và feature.

### 21.1. Một thiết kế dễ bị hot partition

~~~text
PK = TENANT#T-A
SK = ORDER#2026-11-14T11:31:00Z#O-100
~~~

Truy vấn tenant timeline có locality nhưng writes của T-A dồn vào cùng PK. Một hot item có thể làm condition/update throughput bị giới hạn riêng.

### 21.2. Write sharding theo tenant/time

~~~text
PK = TENANT#T-A#DAY#2026-11-14#BUCKET#07
SK = TS#2026-11-14T11:31:00Z#ORDER#O-100
~~~

Query latest tenant/day cần đọc nhiều `PK`s và merge; SDK API tính read request/capacity cho từng query. Nếu cần direct lookup Order, duy trì **OrdersById** với PK dựa trên tenant+order ID hoặc mapping chính xác.

### 21.3. GSI có hot partition riêng

Một GSI với PK=`STATUS#PAID` có thể nhận rất nhiều writes/updates; độ lệch không biến mất khi base table phân phối tốt. Khi lựa chọn GSI, tính:

- Item projection size.
- Write/update frequency.
- Index PK cardinality/access skew.
- Consistency/freshness (GSI thường có eventual update semantics theo dịch vụ).
- Extra read queries/rate/cost.

### 21.4. Adaptive capacity không phải “phép màu”

Managed capacity redistribution/split strategies có thể giảm một số hotspots, nhưng hot single-item contention, sustained rate, schema choices và transaction constraints vẫn quan trọng. Không đưa một con số “mỗi partition luôn X writes/s” thành luật bất biến, vì giới hạn phụ thuộc item size, capacity mode, current service capabilities và workload.

### 21.5. Conditional writes và transaction semantics

Một Order version update có thể dùng condition expressions; conflict không phải transient throttling để retry mù. Nếu inventory có nhiều bucket, cần domain-level escrow/protocol thay vì `ADD stock` ngẫu nhiên trên mọi item.

### 21.6. Batch APIs và retry

Batch operations có thể trả unprocessed items; retry đúng phần còn lại với backoff, không suy cả batch thất bại. Benchmark write sharding cần đo **consumed capacity, throttled requests, hot keys và GSI effects**, không chỉ total table RPS.

## 22. Azure Cosmos DB for NoSQL: logical partition key và RU hotness

Cosmos DB for NoSQL định tuyến theo **partition key**, tính capacity qua request units; một hot logical partition key có thể bị throttled dù tổng throughput account/container còn dư, tùy cấu hình và features hiện hành.

### 22.1. Tenant-only partition key

~~~json
{
  "id": "O-100",
  "tenantId": "T-A",
  "orderStatus": "PAID"
}
~~~

Nếu partition key là `/tenantId`, T-A có thể là hot logical key. Scale RU tổng lên không nhất thiết giải quyết ngay **per-key throughput ceiling**.

### 22.2. Synthetic partition key

~~~json
{
  "id": "O-100",
  "tenantId": "T-A",
  "tenantDayBucket": "T-A#2026-11-14#07"
}
~~~

Nếu container partition key là `/tenantDayBucket`, mỗi tenant/day có nhiều logical partition keys. Cần direct lookup biết cả partition key và `id` hoặc có mapping/index/query path phù hợp.

### 22.3. Hierarchical partition keys

Một số cấu hình Cosmos DB hỗ trợ **hierarchical partition keys** và partition split/placement behaviors theo service version. Không mặc định `/tenantId` và hierarchical `/tenantId,/day,/bucket` hoàn toàn tương đương synthetic string key: query routing, transactional scope, uniqueness và limits có thể khác.

### 22.4. RU không phân bố theo item count

Một tenant có nhiều point reads nhỏ, tenant khác chạy queries scan lớn có thể tiêu thụ RU khác rất nhiều. Đo:

~~~text
requestCharge/RU by operation
429 throttling by partition key / logical range
query fanout / cross-partition queries
physical partition load and hotness
consistency/session token behavior
~~~

Thêm 16 buckets nhưng mọi read cross-partition scan có thể **tăng tổng RU**, làm cost tăng dù write throttling giảm.

### 22.5. Transactional batch scope

Các operations trong một transactional batch có scope logical partition key theo sản phẩm. Chia một entity cần atomic multi-record update thành nhiều synthetic partition keys có thể **làm mất khả năng dùng một single-partition atomic batch**. Đây là trade-off cần ghi trong decision record.

## 23. Redis Cluster: hash slots và hot keys

Redis Cluster chia keyspace theo **hash slots**, mỗi primary chịu một số slots và có replicas theo topology. Một key có slot cố định; hot key có thể dồn tải lên một primary dù slots phân bố đều.

### 23.1. Hash slot mapping

Nếu một tenant có nhiều keys, tên key và **hash tags** có thể ảnh hưởng colocated placement:

~~~text
order:T-A:O1
order:T-A:O2

order:{T-A}:O1
order:{T-A}:O2
~~~

Với Redis Cluster, phần trong `{...}` được dùng để chọn slot theo documented hash-tag behavior. Dùng `{T-A}` cho tất cả Orders có thể **cố tình gom mọi keys vào một slot**, tốt cho một số multi-key operations nhưng xấu cho hot-tenant distribution.

### 23.2. Tránh hash tag quá rộng

Nếu cần một atomic multi-key operation trên vài keys liên quan, colocate chúng có thể là yêu cầu; nhưng colocate **toàn tenant** rất lớn sẽ làm một slot nóng. Phân vùng theo Order/operation group/bucket và giải thích rõ operations nào cần atomicity.

### 23.3. Counter sharding

Một counter read-only approximate có thể chia thành 16 counters:

~~~text
viewCount:SKU-HOT:b00
...
viewCount:SKU-HOT:b15
~~~

Ghi chọn bucket, đọc tổng. Kỹ thuật này phù hợp một số **approximate/eventual aggregation**, nhưng không thay inventory stock invariant.

### 23.4. Một hot key không thể “di chuyển cho hết nóng”

Chuyển slot chứa hot key sang primary khác có thể phân bố tải tổng cluster tốt hơn, nhưng nếu một key vượt capacity một primary, vẫn cần **shard the value/semantics, cache/replica reads, batching hoặc thay access pattern**.

### 23.5. Đo

Redis Cluster cần quan sát per-primary CPU, commands/s, network, memory, slowlog, hot keys, slot ownership và replication health. Không xem số slots mỗi primary bằng nhau là bằng chứng QPS cân bằng.

## 24. Elasticsearch/OpenSearch: routing key, primary shards và search fan-out

Elasticsearch/OpenSearch phân documents vào **primary shards** dựa trên routing và index settings; replicas phục vụ availability/reads theo product semantics.

### 24.1. Routing bằng tenant

~~~text
_routing = tenantId
~~~

Một truy vấn tenant có thể target shard nhỏ hơn (tùy routing/index). Nhưng mọi documents của T-A có thể cùng routing shard, tạo hotspot. Nếu một tenant cực lớn, có thể cần **routing partition size** hoặc thiết kế index khác theo feature version.

### 24.2. Routing theo Order ID

Indexing phân tán tốt hơn cho distinct IDs, nhưng tenant query có thể fan-out qua nhiều shards. Cần quyết định theo read/write mix.

### 24.3. Search-oriented denormalization

Có thể phục vụ tenant timeline bằng separate per-tenant/time index hoặc index strategy phù hợp, nhưng index count/shard count quá lớn tạo metadata/heap/operational overhead. Không tạo một index cho mỗi tiny tenant mặc định.

### 24.4. Hot shard và document update

Một document được cập nhật liên tục có thể gây primary shard write/indexing pressure. Replica count không tự tăng throughput write cho chính document ấy. Khi dùng ingest pipelines, heavy analyzers và mappings, **operation cost** khác nhau theo field/value.

### 24.5. Fan-out và search p99

Một query chạy trên nhiều shards phải chờ nhiều subresults; độ lệch shard size/CPU có thể làm search p99 bị quyết định bởi shard chậm nhất. Monitor shard-level slowlogs, rejections, queues và routing metrics, không chỉ cluster aggregate QPS.

## 25. So sánh ý nghĩa “partition key” giữa các hệ

| NoSQL | Vai trò key chính | Cảnh báo khi dữ liệu skew |
| --- | --- | --- |
| MongoDB sharded | Shard key và routing/chunks | Low-cardinality/monotonic key, hot shard, scatter-gather |
| Cassandra/ScyllaDB | Hash partition key thành token | Một logical partition key rất lớn/hot khó chia |
| DynamoDB | Partition key và optional sort key | Hot partition/item, GSI PK skew, RU/capacity |
| Cosmos DB for NoSQL | Logical partition key/physical partitions | RU hot key, transaction batch scope |
| Redis Cluster | Hash slot theo key/hash tag | Hot key/slot; co-locate quá rộng |
| Elasticsearch/OpenSearch | Routing to primary shard | Hot shard, search fan-out, many-small-shards |

**Không dùng `partition key` như một khái niệm hoàn toàn đồng nhất giữa các sản phẩm.** Kiến trúc hợp lý là hiểu invariant và access pattern trước, sau đó mapping vào routing/consistency/size limits cụ thể.

## 26. Xây bộ thí nghiệm: so A/B/C bằng cùng workload

Một bài thực hành đúng phải đánh giá **cả ba thiết kế key** trên cùng traffic model:

~~~text
A: partitionKey = tenantId
B: partitionKey = stableHash(orderId)
C: partitionKey = tenantId#bucket(orderId, 16)
~~~

### 26.1. Dữ liệu seed

Chuẩn bị synthetic dataset:

- 5.000 tenants.
- T-A chiếm 45% writes trong peak; top10 chiếm 72%.
- 20 triệu Orders (staging scale) với kích thước document biến thiên.
- Một số Orders lớn gấp 100 lần median.
- Một SKU hot và một số Order IDs bị cập nhật nhiều lần.
- `createdAt` tăng theo thời gian, có late-arriving updates/events.
- Deletes/TTL/archived Orders với retention khác nhau.

**Không dùng dữ liệu khách hàng thật/PII** nếu không có chính sách và quyền tương ứng; synthetic data đủ tái hiện profile skew.

### 26.2. Kịch bản thử

| Test | Workload | Điều muốn quan sát |
| --- | --- | --- |
| U0 | Uniform keys, low load | Baseline latency/capacity |
| S1 | Zipf tenant skew | Hot tenant placement |
| S2 | T-A 45% writes | Partition capacity ceiling |
| S3 | Một Order nhận 30% updates | Hot single-item bound |
| S4 | Một SKU 30% reservations | Data invariant under contention |
| S5 | T-A latest-50 query tăng 10× | Fan-out/read amplification |
| S6 | Monotonic timestamp inserts | Rightmost range hotspot |
| S7 | Burst traffic 5× trong 60s | Queue/admission/resilience |
| S8 | T-A tăng từ 16→32 buckets | Backfill/cutover/dual placement |
| S9 | Node/shard relocation trong peak | Recovery and routing correctness |
| S10 | Deletes/TTL trong hot partition | Tombstones/compaction and reads |
| S11 | Mixed large and small documents | Weighted cost skew |
| S12 | One AZ failure + rebalancing | Degraded capacity and replica placement |

### 26.3. Ma trận tham số

~~~yaml
benchmark:
  dataset:
    tenants: 5000
    orders: 20000000
    medianDocumentBytes: 2000
    largeDocumentSharePercent: 2
  load:
    normalWriteRps: 4000
    peakWriteRps: 20000
    normalReadRps: 30000
    hotTenantWriteShare: 0.45
    hotSkuReservationShare: 0.30
    durations:
      warmupMinutes: 10
      steadyMinutes: 20
      burstMinutes: 5
      recoveryMinutes: 10
  variants:
    - tenant-only
    - order-id-hash
    - tenant-plus-16-buckets
    - tenant-day-plus-16-buckets
  validation:
    queryResultsCorrect: true
    duplicateBusinessEffectsAllowed: false
    lostDeletesAllowed: false
~~~

Đây là **đặc tả thử nghiệm** chứ không phải config của một load generator cụ thể. Khi triển khai thật phải bổ sung cluster size, RF, capacity mode, version, clients, network, index definitions và cost limits.

### 26.4. Open-loop offered load

Dùng một load generator có khả năng gửi traffic theo lịch độc lập với latency backend, để không mắc **coordinated omission** khi database chậm. Báo cùng lúc:

~~~text
scheduled logical RPS
actual sent logical RPS
accepted/rejected logical RPS
physical backend requests
latency including queue and retry
~~~

Nếu load generator chỉ chạy closed-loop, số RPS có thể giảm khi response chậm, che quá tải và cho kết quả “p99 vẫn tốt” sai lệch.

### 26.5. Các kết quả cần ghi theo shard

~~~text
shard_id
resident logical bytes and record count
physical bytes and replica placements
partition/key count
read QPS / write QPS
CPU, memory, disk IOPS/throughput, network
throttling/rejections/timeouts
p50/p95/p99 per operation
hot tenant/key top-k
compaction/repair/rebalance activity
~~~

Một chiến lược key có max-to-mean write ratio = 1,4 nhưng read fan-out p99 tăng 4× có thể không tốt hơn phương án ratio = 2,0 vẫn đáp ứng cả SLO. **Không tối ưu một metric đơn lẻ**.

## 27. Bảng kết quả giả định: nhận diện đánh đổi

Giả sử chạy load tests cùng mức workload, kết quả có thể là:

| Thiết kế | Max/mean writes/shard | AP1 p99 | AP2 p99 | AP2 partitions/read | Kết luận bước đầu |
| --- | ---: | ---: | ---: | ---: | --- |
| A: tenant-only | 7,1 | 60 ms | 75 ms | 1 | Hot tenant làm shard quá tải |
| B: orderId hashed | 1,3 | 55 ms | 410 ms | 32 | Read timeline quá tốn |
| C: tenant+16 bucket | 1,8 | 70 ms | 180 ms | 16 | Cân bằng tốt hơn trong ví dụ |
| D: tenant+day+16 bucket | 1,7 | 80 ms | 200 ms | 16/day | Retention tốt hơn, multi-day fan-out |

**Đây là số liệu giả định phục vụ cách đọc trade-off**, không phải benchmark của bất kỳ NoSQL product. Kết luận production phải có đo thật, confidence interval/repeat runs và business acceptance.

### 27.1. Đừng kết luận D luôn tốt hơn C

Với AP2 cần 30 ngày lịch sử, D có thể chạm \(30\times16=480\) partition-key ranges trước khi tối ưu; còn C theo tenant+bucket có thể query history trong 16 partitions nhưng mỗi partition lớn hơn. Time bucketing tốt cho retention nhưng có chi phí multi-window queries.

### 27.2. SLO theo từng operation

Một thiết kế không đạt AP2 p99 nhưng có thể đạt khi:

- Thêm bounded `RecentOrdersByTenant` projection.
- Thay pagination strategy.
- Dùng smarter k-way merge.
- Caching an approved freshness window.

Phải tính **chi phí duy trì projection và correctness** trước khi chọn.

### 27.3. Phân biệt backend p99 và user p99

AP2 gọi 16 buckets; database per-bucket p99 tốt nhưng Java merge/queue/network/cancellation có thể làm API p99 cao. Báo trace breakdown:

~~~text
API admission and auth
bucket lookup policy
parallel subqueries
slowest subquery
merge sort / serialization
response send
~~~

## 28. Quy trình chọn partition key có thể lặp lại

Một decision flow:

~~~mermaid
flowchart TD
    A["List access patterns and invariants"] --> B["Measure key, read/write and size skew"]
    B --> C{"Any hot single-item invariant?"}
    C -->|Yes| D["Redesign coordination/escrow/serialization"]
    C -->|No| E["Generate key candidates"]
    D --> E
    E --> F["Estimate data/write distribution and read fanout"]
    F --> G["Simulate same workload for each candidate"]
    G --> H["Load test with real SDK and cluster"]
    H --> I{"SLO, correctness, capacity, cost all pass?"}
    I -->|No| E
    I -->|Yes| J["Plan key version, migration and rollback"]
    J --> K["Canary and observe"]
~~~

### 28.1. Đặt “capacity envelope”

Một ví dụ planning envelope cho từng key/partition:

~~~text
Maximum logical partition payload: vendor limit with headroom
Peak writes per partition: <= measured safe threshold
Peak read cost per partition: <= measured safe threshold
Shard p99 under degraded mode: <= operation SLO
Maximum fanout for critical API: bounded and measured
Replication/backup overhead: budgeted
~~~

Không điền ngưỡng bằng thông số marketing chung; dùng **measured thresholds** trên setup tương ứng và official product limits.

### 28.2. Guardrails ở schema level

Ví dụ:

- Khi tạo Order, bắt buộc cung cấp `tenantId` từ auth context.
- Đặt unique identity `(tenantId, orderId)`/operation ID theo engine.
- Gắn `keyVersion` và `bucketCount` đúng routing policy.
- Cho phép query only by supported access patterns trên high-traffic paths.
- Reject unbounded scans/requests không có deadline.
- Alert nếu one tenant/partition vượt share threshold.

### 28.3. Không tối ưu chỉ write path

Giảm max shard writes từ 9.000 xuống 600/s nhưng làm mỗi read fan-out 64 có thể tăng cost gấp nhiều lần. Với workload đọc nhiều hơn ghi, phải tính **weighted total cost** trên thực tế.

## 29. Chi phí dữ liệu, replica và headroom

Giả sử logical Orders data 12 TiB, replication factor 3:

\[
12\times3=36\ \mathrm{TiB}
\]

Đây là **raw replicated logical payload tối thiểu theo giả định copies đầy đủ**, không gồm indexes, WAL/commit log, compaction, snapshots, compression differences, backups và hệ thống search.

### 29.1. Nếu dùng 12 data nodes

Giả sử phân phối hoàn hảo:

\[
36/12=3\ \mathrm{TiB/node}
\]

Nếu một node chỉ có usable capacity 4 TiB, bình quân 3 TiB/node tương ứng 75% trước overhead. Điều đó có thể **quá sát giới hạn** cho rebuild/compaction, dù bình quân bytes nhìn ổn.

### 29.2. Nếu shard skew factor 2

Một node có thể giữ tương đương 6 TiB trong mô hình 3 TiB bình quân ×2, vượt 4 TiB usable. Đây là ví dụ vì sao sizing cần **max/skew/headroom**, không chỉ data total / nodes.

### 29.3. Replica placement và miền lỗi

Hash bucket có thể phân bố vào nhiều logical partitions nhưng replicas cần trải AZ/racks theo failure model. Không tuyên bố “16 buckets = chịu mất AZ” nếu mọi replicas vẫn nằm trong một failure domain.

### 29.4. Khi cần rebalancing

Thêm node hoặc chuyển bucket owner làm phát sinh:

- Copy data và index.
- Network/disk IO, compaction.
- Temporary storage.
- Replication/log catch-up.
- Routing metadata updates.
- Potential transaction/CDC interaction.

Một phương án chỉ đạt SLO lúc cluster ổn định nhưng sập p99 trong resharding **chưa đủ**.

### 29.5. Availability under peak after failure

Nếu một hot tenant traffic đã dùng 80% safe per-shard throughput khi healthy, mất một replica/AZ có thể khiến remaining nodes vượt khả năng. Hãy thử **peak workload + one-AZ loss + ongoing rebalancing**, không chỉ benchmark healthy full cluster.

## 30. Quy trình migration khi đổi partition key

Thay partition key có thể đòi **tạo table/collection/index mới, backfill, CDC catch-up và cutover**; không phải engine nào cũng cho đổi trực tiếp. Một giao thức tổng quát:

~~~mermaid
flowchart LR
    V1["Old key version v1"] --> B["Snapshot/backfill to v2"]
    B --> C["Replay change stream / dual-write policy"]
    C --> D["Reconcile keys, values, versions, deletes"]
    D --> E["Shadow reads v2"]
    E --> F["Route reads/writes to v2"]
    F --> G["Fence v1 writes"]
    G --> H["Retain v1 backup/rollback window"]
    H --> I["Decommission v1 after gates"]
~~~

### 30.1. Backfill snapshot boundary

Chọn một **consistent source cut** hoặc documented backfill+change-capture protocol. Nếu scan v1 rồi bắt đầu CDC sau khi scan xong, có thể bỏ writes ở giữa.

### 30.2. Record ID và routing key version

Trong migration 16→32 buckets:

~~~json
{
  "tenantId": "T-A",
  "orderId": "O-100",
  "keyVersion": 2,
  "bucketCount": 16,
  "bucket": 7
}
~~~

Nếu cùng entity nằm ở v1 và v2 trong chuyển tiếp, dùng **operationId/recordVersion** để quyết định mới nhất và chống duplicate effects. Không lấy `updatedAt` do client gửi làm source-of-truth ordering.

### 30.3. Read routing trong migration window

Các lựa chọn:

- Chỉ đọc v1 đến khi v2 catch-up và cutover.
- Read primary v1, shadow query v2 và so kết quả.
- Read v2, fallback v1 có giám sát/guard khi mới cutover.
- Dual-read theo versioned directory khi records được chuyển dần.

Fallback không được trả stale data vi phạm read-your-writes; mọi cách phải có **authority, precedence và error policy** rõ.

### 30.4. Dual-write cẩn trọng

App ghi cả v1 và v2 có các cases:

~~~text
v1 write succeeds; v2 fails
v2 succeeds; v1 times out after commit
delete applied in one but not the other
concurrent updates arrive out of order
~~~

Nếu không có distributed transaction, cần outbox/CDC/idempotency và reconciliation; không coi dual-write hai API calls là atomic.

### 30.5. Chốt cutover

Một cutover plan có thể xác định:

~~~text
source commit position L0 (per shard if necessary)
target applied/durable position through L0
reconciliation report at equivalent state
write fencing / authority epoch
new routing directory/version
client rollout status
rollback and forward recovery plan
~~~

### 30.6. Resharding không được phá pagination

Nếu pagination cursor chứa 16 per-bucket positions, khi đổi sang 32 buckets:

- Có giữ routing version cho cursor cũ?
- Có cho cursor cũ hết hạn rõ ràng?
- Có snapshot watermark để không duplicate/miss?
- Có migration mapping với old/new buckets?

Không âm thầm diễn giải cursor v1 bằng routing v2.

### 30.7. Decommission source cũ

Chỉ xóa v1 khi:

- Không còn writers/readers/CDC phụ thuộc v1.
- Keys/versions/deletes/TTL đã đối soát.
- New backup/PITR restore được.
- Rollback horizon đã đóng hoặc có forward recovery.
- Retention/privacy/legal hold được xử lý.
- Tài liệu vận hành/alert/IAM được cập nhật.

Key redesign là **thay đổi vòng đời dữ liệu**, không chỉ refactor một field.

## 31. Giám sát skew và cảnh báo sớm

Một dashboard tốt phải cho biết **ai nóng, nóng ở đâu, gây tốn tài nguyên gì và gây ảnh hưởng access pattern nào**.

### 31.1. Bộ metric tối thiểu

| Lớp | Metrics | Câu hỏi |
| --- | --- | --- |
| Business workload | top tenants, SKU, key classes; reads/writes/s | Ai tạo tải bất cân xứng? |
| Data distribution | bytes/records per logical partition/shard | Dữ liệu có lớn lệch? |
| Traffic distribution | request/cost per partition/shard | Tải có hot bất thường? |
| Query | targeted vs scatter-gather, fan-out | Truy vấn có chạm quá nhiều partitions? |
| API | p50/p95/p99, error, timeout | Người dùng bị ảnh hưởng thế nào? |
| Capacity | CPU/IOPS/disk/network/RU/throttling | Điểm nghẽn tài nguyên ở đâu? |
| Replication | follower lag, quorum/leader status | Replica placement/correctness ra sao? |
| Background | compaction, repair, rebalancing | Hotspot có trùng maintenance? |
| Cost | per-operation RU/index writes/egress | Chia bucket làm bill tăng bao nhiêu? |
| Key migration | old/new versions, CDC lag, mismatches | Rekey đã hoàn tất chưa? |

### 31.2. Các phép đo tổng hợp

~~~text
top1_write_share
top10_write_share
max_to_mean_write_cost_per_shard
max_to_mean_storage_bytes_per_shard
per_tenant_hot_buckets
read_query_fanout_p50_p95_p99
throttled_operations_by_route
one_key_update_contention
~~~

Tránh đưa raw `orderId`/PII làm metric label vì cardinality cao và rò rỉ thông tin. Lưu hot-key samples trong kênh diagnostics có quyền/retention riêng, hash/aggregate khi phù hợp.

### 31.3. Không chỉ nhìn bản đồ nhiệt trung bình một ngày

Một shard có load 100 writes/s trong 23 giờ nhưng nhận 10.000/s trong 1 giờ sẽ có daily average:

\[
\frac{23\times100+1\times10000}{24}
\approx512{,}5\ \mathrm{writes/s}
\]

Average 512,5/s che **peak 10.000/s**, trong khi timeout diễn ra lúc burst. Cần max/percentile theo 1m/5m và peak business windows.

### 31.4. Alert theo capacity, không chỉ relative skew

Max/mean ratio 4 có thể còn an toàn nếu toàn cluster gần idle; ratio 1,5 có thể không an toàn nếu mọi shards ở 90% capacity. Cần cả hai:

~~~text
imbalance threshold exceeded
AND/OR
specific shard/partition resource ceiling exceeded
~~~

### 31.5. Alert khi top tenant đổi

Đừng hard-code chỉ T-A. Một tenant mới T-Z có thể trở thành top1 sau campaign. Detection nên theo dynamic top-k và owner/cost classification.

### 31.6. Distinct “hot reads” và “hot writes”

Nếu một key có 50.000 GET/s và có thể cache với freshness hợp lệ, giải pháp có thể là caching/read replicas. Nếu nó có 50.000 conditional UPDATE/s, caching **không** giúp distributed serialization; cần đổi domain coordination/sharding.

## 32. Runbook xử lý hot partition dưới tải

### Bước 1 — Xác định loại hotspot

Hỏi:

~~~text
Is it data size skew?
Is it reads, writes, or one expensive query?
Is it one logical key, one tenant, or one physical shard?
Is it a monotonically increasing range?
Is it a secondary index / search shard hotspot?
Is it correlated with failover/rebalance/compaction?
~~~

### Bước 2 — Bảo vệ service

- Giữ consistency/transaction contract.
- Bound request concurrency, retries, scans và batch work.
- Rate-limit/shaping noncritical workloads theo tenant nếu policy cho phép.
- Tránh chạy toàn bộ backfill/repair trong peak.
- Trả controlled errors nếu hệ không thể giữ an toàn dữ liệu.

Không tự “fix” overload bằng hạ durability hoặc bỏ condition khỏi inventory update.

### Bước 3 — Tìm short-term mitigation

| Tình huống | Mitigation có thể xem xét |
| --- | --- |
| Read hotspot cho immutable catalog | Cache/read replicas theo freshness |
| Hot tenant với nhiều distinct Order IDs | Repartition tenant/time+hash buckets |
| One hot Inventory item | Escrow/quota/serialization/admission |
| End-of-range sequential writes | Hashed routing/subbucket phù hợp |
| Unbounded analytics scans | Materialized aggregate/index/batch isolation |
| Hot GSI | Phân phối index key/thiết kế projection |
| Hot Redis Cluster hash tag | Đổi colocate scope/routing |
| Rebalance gây I/O | Throttle migration, capacity headroom |

### Bước 4 — Đo effect

Theo dõi trước/sau:

- Actual routed shard load.
- Backend throttling/error rate.
- User-facing p99.
- Read fan-out và cost.
- Domain invariants/duplicates.
- Replication/recovery health.

### Bước 5 — Lập long-term fix

Nếu cần đổi partition key, thiết kế key version, backfill/change-capture, compatibility routing và rollback. Không đổi schema/connector đồng loạt trong production mà thiếu test ở realistic skew.

### Bước 6 — Cập nhật kiến thức vận hành

Ghi hot-key root cause, routing rule, capacity envelope, bucket count/version, query pagination behavior, migration evidence và thông tin cần theo dõi.

## 33. Case study A — Tenant lớn phá key theo tenant

### Bối cảnh

Hệ có 10.000 tenants, 99,9% tenants rất nhỏ; T-A có hơn 50% peak writes. Partition key là `tenantId`.

### Hiện tượng

Shard chứa T-A có write QPS gấp nhiều lần các shards khác; thêm 4 nodes không giảm load cho partition key T-A.

### Nguyên nhân

High tenant cardinality không đảm bảo **effective traffic cardinality**; một key vẫn chi phối.

### Hướng xử lý

Đặt `(tenantId, stableHash(orderId)%B)` với bucket policy riêng cho T-A; duy trì query projection cho latest Orders; thực hiện backfill/cutover và đo p99/fan-out. Với one-hot Order còn cần cách xử lý riêng.

## 34. Case study B — UUID tốt cho writes, tệ cho timeline

### Bối cảnh

Primary key là random Order ID; writes đều. Trước cutover AP2 `latest 50 per tenant` đọc một partition, sau cutover phải scan trên toàn cluster.

### Hiện tượng

Writes p99 giảm, nhưng tenant timeline p99 tăng và RU/network cost lớn.

### Bài học

Khóa tốt cho distribution không đồng nghĩa tốt cho reads. Thiết kế targeted `RecentOrdersByTenant` projection/index với có kiểm soát về freshness, fan-out và update cost.

## 35. Case study C — Monotonic time key làm rightmost hotspot

### Bối cảnh

Một team sharding theo range của `createdAt`, mọi event mới có timestamp tăng.

### Hiện tượng

Các inserts mới dồn vào highest key range dù lịch sử 200 triệu events được trải nhiều ranges.

### Hướng xử lý

Hash subbucket/time bucket phù hợp hoặc engine-supported hashed shard key; cân nhắc cost cho range queries và ordering. Không chỉ “thêm index createdAt” rồi coi placement đã đổi.

## 36. Case study D — Hash(Order ID) không xử lý hot Order

### Bối cảnh

Mỗi flash sale cập nhật một Order aggregate nhiều lần/giây; shard key đã hash theo orderId.

### Hiện tượng

Các Orders khác đều nhưng shard chứa O-HOT quá tải do serialized update. Hash key đặt O-HOT ở vị trí ngẫu nhiên, **không chia bản thân O-HOT**.

### Hướng xử lý

Điều tra có nên lưu append-only events và async materialization, batch coalescing, versioned conditional updates hoặc chia independent sub-aggregates. Phải giữ domain invariant; với một serialization point thật sự, chấp nhận throughput ceiling và admission có thể là lựa chọn đúng.

## 37. Case study E — Random inventory shards gây oversell

### Bối cảnh

Stock 100, tạo 10 counters mỗi counter “available=100”, mỗi reservation chọn random counter rồi decrement.

### Kết quả

Có thể bán tới 1.000 units vì 10 buckets đều tự coi mình có 100. Đây là một ví dụ **data model vi phạm global invariant**, không phải lỗi triển khai hash.

### Hướng xử lý

Escrow/quota allocations tổng ≤100, atomic decrement per owned quota, chuyển quota an toàn và idempotency. Nếu không bảo đảm, giữ một authoritative stock record.

## 38. Case study F — 64 buckets tạo read fan-out quá lớn

### Bối cảnh

Tenant T-A chia 64 buckets để writes giảm tải; mobile API gọi danh sách recent Orders mỗi 2 giây.

### Hiện tượng

Mỗi AP2 request tạo nhiều subqueries, p99 tăng, cost cao và SDK pool saturation trong peak reads.

### Hướng xử lý

Giảm B theo measured capacity nếu an toàn, hoặc tạo bounded recent-order feed/index, adaptive k-way merge và pagination với per-bucket cursors. Đo cả **write capacity và AP2 p99**.

## 39. Case study G — Thay BUCKETS=16 thành 32 làm “mất” Orders

### Bối cảnh

Java code tính `hash(orderId)%16` từ trước. Deploy mới đổi thành `%32` mà không backfill old records.

### Hiện tượng

Một số point GET route sang buckets mới, trả NotFound dù records vẫn ở buckets cũ.

### Giải pháp

Key version/bucket policy immutable, directory hoặc dual read có version guard trong migration, copy/catch-up/reconciliation rồi cutover. Không dùng rollout hằng số đơn giản để đổi stored partition key.

## 40. Case study H — Một GSI hot dù base table đều

### Bối cảnh

Base table dùng Order ID hashed, nhưng GSI partition key là `status="PAID"`. Trong đỉnh traffic, hầu hết updates chuyển sang `PAID`.

### Hiện tượng

Index write path throttled, khiến base writes chậm hoặc errors theo service behavior. Histogram base PK nhìn đều nên team tưởng database khỏe.

### Hướng xử lý

Đổi index key sang status+time bucket/salt, tạo domain projection hoặc aggregate theo query need; đo index capacity/write amplification/read fan-out và consistency.

## 41. Case study I — Redis hash tags gom cả tenant vào một slot

### Bối cảnh

Mọi Redis keys có dạng `order:{T-A}:id`, nhằm hỗ trợ multi-key scripts.

### Hiện tượng

T-A traffic dồn vào một slot/primary. Dù thêm primaries, hot slot vẫn là điểm nghẽn.

### Hướng xử lý

Giảm colocate scope, nhóm theo order/bucket phục vụ atomic operation nhỏ hơn. Cần xác định **multi-key commands nào mất khả năng chạy atomic** nếu keys chuyển slots.

## 42. Case study J — Partition theo giờ nhưng có late events

### Bối cảnh

Event xảy ra 23:58 nhưng tới database lúc 00:10. Writer partition theo ingestion day, báo cáo nghiệp vụ query theo event day.

### Hiện tượng

Daily report bỏ event vì nó nằm ở partition ngày tiếp theo.

### Hướng xử lý

Định nghĩa `occurredAt` vs `receivedAt`, late-data window, event-time index và query window/correction processing. Time bucketing là **quyết định semantics** chứ không chỉ giảm size.

## 43. Case study K — Skew theo bytes, không theo QPS

### Bối cảnh

Shards cùng 1.000 writes/s, nhưng shard A nhận large documents trung bình 100 KiB, shard B nhận 1 KiB.

### Hiện tượng

Shard A có disk/network/compaction throughput cao hơn ~100× theo payload raw, có thể đạt I/O ceiling trước.

### Hướng xử lý

Weight workload by bytes/index amplification, cân nhắc tách large blobs sang object storage và giữ references, kiểm tra metadata/backup/RPO. Không chỉ count writes.

## 44. Case study L — Hotspot “di chuyển” theo campaign

### Bối cảnh

Hôm nay T-A nóng, tuần sau T-Z nóng. Cấu hình chỉ gắn `T-A=16 buckets`.

### Hiện tượng

T-Z vẫn dùng một partition, overload mới xảy ra dù team đã “sửa hot tenant”.

### Hướng xử lý

Top-k monitoring tự động, tenant policy versioning, criteria khi nâng B, migration orchestration và per-tenant capacity alerts; không hard-code tên tenant trong data model lâu dài.

## 45. Case study M — Partition đều nhưng replica placement sai

### Bối cảnh

16 buckets được đặt đều vào 8 shard groups; nhưng replicas chủ yếu cùng AZ. Sau mất AZ, nhiều groups mất quorum dù healthy load từng shard đẹp.

### Bài học

Partition key giải quyết phân phối work, **không thay replica/AZ placement**. Topology/failure domains và N+AZ capacity phải đánh giá riêng.

## 46. Case study N — Scatter-gather biến một read thành 100 requests

### Bối cảnh

Một API request `GET /tenant/T-A/orders/recent` không có routing key phù hợp, fan-out 100 shards; trong outage một shard chậm.

### Hiện tượng

Latency dominated by slowest shard, CPU/requests inflated; API p99 cao dù từng shard phần lớn khỏe.

### Hướng xử lý

Tenant-focused projection, bounded fan-out và merge, consistent pagination/freshness, deadline. Đo **physical backend operations per logical read**.

## 47. Case study O — Phân vùng tốt nhưng CDC rekey làm mất deletes

### Bối cảnh

Backfill từ key v1 sang key v2, nhưng change stream chỉ replay INSERT/UPDATE, bỏ delete.

### Hậu quả

Một record đã xóa ở nguồn v1 được giữ tại v2; sau cutover có thể hồi sinh dữ liệu.

### Hướng xử lý

Reconcile keysets/versions/deletes theo source cut, giữ continuous CDC changes, idempotent event application, query results validation và old backup/rollback horizon.

## 48. Case study P — Caching che hotspot trong lab

### Bối cảnh

Load test dùng chỉ 1.000 Order IDs với 95% cache hit, trong khi production có nhiều unique active IDs và 30% writes.

### Hiện tượng

Lab p99 rất tốt; production cache misses làm storage IOPS tăng và hot shard xuất hiện.

### Hướng xử lý

Tạo workload có **key cardinality, cache-hit ratio, read/write mix và skew** tương tự production; có cả cold-cache/warm-cache runs và hot partition experiments.

## 49. Anti-patterns trong thiết kế khóa cho skew

| Anti-pattern | Vì sao sai | Sửa bằng |
| --- | --- | --- |
| Mỗi tenant đúng một partition bất kể kích thước | Hot tenant thành bottleneck | Tenant/time/hash subbucket |
| Chỉ đếm records | Bỏ traffic/IO skew | QPS/cost/bytes per partition |
| Hash một hot item | Không chia chính item | Domain redesign/escrow/admission |
| Dùng `createdAt` range thuần | Monotonic rightmost writes | Hash/range hybrid theo access |
| Đổi modulus B trực tiếp | Historical keys đổi bucket | Versioned routing/rekey |
| Coi bucket = physical node | Placement trùng, RF khác | Measure actual shard/replica |
| Bucket càng nhiều càng tốt | Read fan-out/cost lớn | Optimize measured trade-off |
| Bỏ tenant ID khỏi routing/security | Cross-tenant data leak | Authorized tenant context |
| Prefix key theo client clock | Late/skew timestamps | Canonical timestamp policy |
| Coi GSI miễn phí | Index write hotspot/RU cost | Index workload analysis |
| Chỉ nhìn average CPU | Che hot partition and p99 | Per-shard p99/top-k |
| Mỗi tenant một index | Small-shard/metadata overhead | Shared indexed schema/policy |
| Partition theo status ít giá trị | Low-cardinality hot partitions | Composite/high-cardinality key |
| Materialize mọi query | Write amplification | Prioritize important access |
| Hash bằng `Math.abs(hashCode())` | MIN_VALUE/cross-language mismatch | Stable documented algorithm |
| Bỏ clustering/sort key design | Timeline query không target được | Co-design access path |
| Rebalance trong peak không headroom | Disk/network saturation | Capacity/maintenance plan |
| Xóa v1 ngay sau copy | CDC gaps/deletes/data loss | Reconciliation/rollback gates |
| Count-only reconciliation | Duplicate/missing records che nhau | Key/version/delete comparison |
| Counter sharding cho inventory không escrow | Oversell | Atomic quota protocol |
| `SCAN` trên một Redis primary | Miss other hash slots | Cluster-aware coverage |
| Không test client SDK actual routing | Toy hash khác engine | Real SDK load experiments |

## 50. Bài tập thực hành

### Bài 1 — Top-k share

Một hệ có 10 tenants, số writes/s lần lượt:

~~~text
T1=4800, T2=1600, T3=900, T4=700, T5=600,
T6=500, T7=300, T8=250, T9=200, T10=150
~~~

1. Tổng writes/s?
2. Top1 share và Top3 share?
3. Nếu partition theo `tenantId`, tenant nào đáng kiểm tra nhất?
4. Có thể kết luận overload chỉ từ Top1 share không?

### Bài 2 — Max-to-mean shard load

Có 8 shards, writes/s:

~~~text
400, 500, 600, 650, 700, 750, 800, 5600
~~~

1. Tổng và mean?
2. Max-to-mean ratio?
3. Nếu threshold per-shard là 2.000 writes/s, shard nào vi phạm?
4. Nếu thêm 8 nodes nhưng không thể chia hot logical key, điều gì xảy ra?

### Bài 3 — Hot tenant lower bound

Peak 20.000 writes/s, tenant T-A chiếm 45%, 16 physical shards.

1. T-A writes/s?
2. Mean ideal writes/s/shard?
3. Với key tenant-only không chia T-A, lower bound tải shard chứa T-A?
4. Tỷ lệ lower bound so với ideal?

### Bài 4 — Sizing bucket count

Tenant T-A 9.000 writes/s. Mỗi bucket nên giữ dưới 750 writes/s tại peak theo measured safe throughput.

1. \(B_{\min}\) lý thuyết?
2. Với B=16, expected writes/s/bucket?
3. Nếu hash distribution skew 30% ở bucket nóng nhất so với expected, lượng writes/s bucket đó?
4. Nếu yêu cầu max 750, B=16 còn hợp lệ trong mô hình skew này không?

### Bài 5 — Fan-out đọc timeline

Một tenant dùng 32 hash buckets. API trả latest 50 Orders và implementation lấy 50 candidates/bucket trước merge.

1. Số routed partition queries?
2. Số candidates tối đa?
3. Candidate-to-returned ratio?
4. Cần tối ưu nào khi AP2 chạy 5.000 RPS?

### Bài 6 — B cân bằng writes nhưng hại reads

Hai phương án:

~~~text
A: 1 tenant partition, AP2 fanout=1, max writes/key=9000/s
B: 32 subbuckets, AP2 fanout=32, expected max writes/bucket=281.25/s
~~~

1. Nếu backend mỗi subquery tốn 1 cost unit, fan-out base cost khác bao nhiêu?
2. Vì sao không suy p99 tăng đúng 32×?
3. Những bước nào có thể giảm fan-out?
4. Khi nào buộc phải chấp nhận B dù AP2 tốn hơn?

### Bài 7 — Time bucket

T-A tạo 100.000 events/phút. Data model key `tenantId#day`, không hash subbucket.

1. Đổi sang key `tenantId#hour` có chia writes trong **cùng phút** không?
2. Nếu thêm B=20 hash subbuckets, expected events/s/subbucket?
3. Query một tuần cần xem những partition ranges nào?
4. Late events ảnh hưởng routing như thế nào?

### Bài 8 — Thay modulus từ 16 sang 32

Ứng dụng cũ lưu Orders với `bucket=hash(orderId)%16`; ứng dụng mới đọc `bucket=hash(orderId)%32`.

1. Có chắc mọi old Order vẫn target đúng không?
2. Cần metadata/keyVersion gì?
3. Có thể dual-read old/new một thời gian không? Điều kiện?
4. Khi nào được xóa old placement?

### Bài 9 — Single hot item

Một `Order O-HOT` được cập nhật 3.000 lần/s, các Orders khác phân phối đều.

1. Hash orderId trên 100 shards có giúp chia O-HOT writes không?
2. Khi nào append events hoặc phân nhỏ aggregate có thể phù hợp?
3. Nếu Order cần một CAS version tuần tự, ràng buộc nào còn tồn tại?
4. Đặt mục tiêu admission/throughput thế nào?

### Bài 10 — Inventory escrow

Stock 1.000 units được phân bổ quotas:

~~~text
B0=200, B1=250, B2=300, B3=250
~~~

1. Tổng quotas?
2. Nếu B0 hết mà B2 còn 40, có được tự tăng B0 thêm 40 không?
3. Những bước tối thiểu để transfer 40 units an toàn?
4. Khi response của transfer timeout, xử lý unknown outcome sao?

### Bài 11 — Oversell phản ví dụ

10 inventory counters đều được khởi tạo `available=100` cho cùng stock thực tế 100.

1. Tối đa lý thuyết có thể bán bao nhiêu nếu mỗi bucket tự quyết định?
2. Domain invariant bị vi phạm là gì?
3. Vì sao tổng cuối cùng không thể “sửa” một physical item đã oversold?
4. Thiết kế lại với quota như thế nào?

### Bài 12 — Hot GSI

DynamoDB primary PK phân phối theo Order ID, GSI PK là status `PAID`, chiếm 80% updates.

1. Vì sao base table metrics đều không đủ?
2. Đổi GSI PK sang status#day#bucket giúp gì?
3. Read query `all PAID today` cần làm gì?
4. Những chi phí mới về RU/fan-out và eventual consistency?

### Bài 13 — Tenant locality vs Order lookup

Cassandra table key:

~~~text
Partition: (tenantId, dayUtc, bucket)
Cluster: (createdAt DESC, orderId)
~~~

Một GET chỉ biết `(tenantId, orderId)` không biết `createdAt`.

1. Có thể point-read một row bằng primary key hiện tại không?
2. Những access paths nào giúp?
3. Vì sao nên thiết kế table `orders_by_id` khác `events_by_tenant_day_bucket`?
4. Cần giữ two tables đồng bộ thế nào?

### Bài 14 — MongoDB ranged key

MongoDB shard key theo range `createdAt` tăng; writes mới dồn cuối range.

1. Đây là skew loại gì?
2. Thay hashed key có trade-off nào cho query theo date range?
3. Một query chỉ theo tenantId có thể scatter-gather không?
4. Balancer có tự giải quyết hot range ngay lập tức không?

### Bài 15 — Redis hash tags

Keys:

~~~text
cart:{T-A}:C1
cart:{T-A}:C2
cart:{T-A}:C3
~~~

1. Chúng có cùng hash slot theo Redis Cluster rules không?
2. Đổi sang `cart:{T-A#bucket}:C1` có thể phân tán thế nào?
3. Rủi ro với multi-key scripts/transactions?
4. Nếu chỉ một cart C1 nóng, bucket theo cart ID có giải quyết không?

### Bài 16 — Cosmos logical partition

Container có partition key `/tenantId`, 60% RU do T-A tạo. Team tăng tổng RU/s gấp đôi.

1. Có chắc T-A hết throttling không?
2. Synthetic key `/tenantDayBucket` giúp gì?
3. Transactional batch qua các buckets có còn single-partition atomic không?
4. Session read-your-writes cần giữ thế nào?

### Bài 17 — Search routing

Elasticsearch index dùng `_routing=tenantId`; T-A chiếm 70% indexing.

1. Vì sao T-A dồn vào một primary shard?
2. Có thể thay routing partition strategy hoặc thay data/index model thế nào?
3. Query tenant timeline và global search trả giá gì?
4. Nếu T-A chỉ nóng reads chứ không writes, cân nhắc gì khác?

### Bài 18 — Data skew theo bytes

Hai shards cùng 2.000 writes/s:

~~~text
Shard A median payload 1 KiB
Shard B median payload 100 KiB
~~~

1. Raw payload write throughput theo median*rate cho từng shard?
2. Vì sao so writes/s chưa đủ?
3. Cần tính index/WAL/replica cost nào?
4. Khi nào tách blobs khỏi NoSQL document?

### Bài 19 — Fan-out tail latency

Một subquery độc lập có xác suất chậm 2%. Một API đợi tất cả 20 subqueries.

1. Xác suất ít nhất một subquery chậm?
2. Vì sao độc lập là assumption mạnh?
3. Nếu cùng physical shard/network route, xác suất correlated thay đổi ra sao?
4. Có thể dùng materialized top-N feed thế nào?

### Bài 20 — RF và storage headroom

Logical data 12 TiB, RF=3, 12 nodes có usable 4 TiB/node.

1. Raw replicated payload?
2. Bình quân per node nếu đều?
3. Normal storage utilization theo payload-only?
4. Vì sao không đủ headroom cho index/compaction/failure?

### Bài 21 — Partition data size

T-A tạo 5.000 events/s, average event 2 KiB, bucket theo ngày và B=8.

1. Tổng raw bytes/ngày cho T-A theo assumptions?
2. Expected raw bytes một bucket/ngày?
3. Cần thêm chi phí gì để chọn cap?
4. Nếu max desired partition 20 GiB, B=8 có đủ theo data-size model?

### Bài 22 — Timezone và late events

Business báo cáo theo múi giờ tenant, event-time UTC, dữ liệu trễ tới 48 giờ.

1. Nên lưu canonical event timestamp thế nào?
2. Dùng bucket theo UTC hay local calendar, trade-offs?
3. Query daily report cần bù 48 giờ late arrivals thế nào?
4. TTL/retention có được xóa bucket cũ ngay sau nửa đêm không?

### Bài 23 — Cluster expansion

Một application hash vào 128 virtual buckets rồi map đến 4 shard groups. Team thêm 4 groups.

1. Nếu không đổi 128 bucket identities, bước nào phải làm?
2. Vì sao chỉ sửa routing table mà chưa copy data có thể tạo 404/data loss?
3. Cần cutover/epoch/fencing thế nào?
4. Nếu một virtual bucket vẫn hot, có cần đổi số physical nodes tiếp không?

### Bài 24 — CDC trong key migration

Backfill xong v2 lúc L1000; source v1 tiếp tục ghi tới L1500, connector v2 mới áp tới L1490.

1. Có được cutover ngay không?
2. Cần đối soát records/deletes/versions ở mốc nào?
3. Nếu có cross-shard transaction, scalar L có đủ không?
4. Old routing cần giữ đến khi nào?

### Bài 25 — Pagination cursor

T-A có 16 buckets, API trả 50 Orders/page. Cursor chỉ lưu `lastCreatedAt`, nhiều Orders cùng timestamp.

1. Vì sao có thể duplicate/miss records?
2. Cần deterministic tie-breaker nào?
3. Có cần per-bucket positions không?
4. Khi bucket policy đổi lên v3, xử lý cursor v2 ra sao?

### Bài 26 — Hot partition vs replica placement

Một cluster có 3 AZ, logical bucket distribution gần đều nhưng cả 3 replicas của shard nóng đều ở AZ A.

1. Hash key tốt có bảo đảm AZ resilience không?
2. Khi AZ A mất, điều gì xảy ra?
3. Cần cấu hình replica placement nào?
4. N+AZ headroom đo thế nào?

### Bài 27 — Adaptive tenant policy

T-A có B=16, T-B có B=1. Tháng sau T-B tăng lên 10.000 writes/s.

1. Có thể đổi B của T-B trực tiếp thành 16 không?
2. Cần metadata/keyVersion và migration nào?
3. Khi nào auto-tune B có thể tạo oscillation?
4. Cách xác định hot-tenant threshold theo measured capacity?

### Bài 28 — Open-loop skew test

Load generator 1.000 clients theo closed-loop và mỗi client đợi response. Một hot shard chậm từ 20ms lên 1s.

1. Vì sao measured RPS có thể giảm?
2. Nếu dùng open-loop 10.000 offered RPS, cần giám sát gì?
3. Coordinated omission có thể che p99 thế nào?
4. Driver/browser/network generator có thể thành bottleneck không?

### Bài 29 — Bài tổng hợp: thiết kế Order Service

Yêu cầu:

~~~text
5,000 tenants, 200 million Orders
Peak 20,000 writes/s; T-A contributes 45%
30,000 reads/s
AP1: GET by tenant+orderId p99 <150ms
AP2: latest50 orders per tenant p99 <250ms
AP3: search by customer and time
Inventory SKU-HOT: 30% of reservations
Need durable write outcome and no oversell
3 AZ, must tolerate one AZ failure
~~~

Đề xuất một thiết kế có:

1. Canonical Orders primary/routing key.
2. Tenant timeline projection/index và pagination.
3. Customer query access path.
4. Hot-tenant bucket policy và cách đổi version.
5. Inventory invariant/escrow hoặc single authority.
6. Fan-out/cost/capacity estimates.
7. Replica/AZ placement và degraded headroom.
8. Key migration/CDC/rollback plan.
9. Load tests, SLI/alerts và acceptance gates.

### Bài 30 — Phản biện proposal

Một bản đề xuất:

> “Dùng `tenantId` làm partition key vì có 5.000 tenants nên chắc chắn đều. Gắn `createdAt` làm sort key để mọi writes của tenant chạy nhanh. Khi tenant nóng, chỉ thêm nodes. Nếu vẫn nóng, đổi `BUCKETS=16` thành 32 ngay trên Java. Lấy recent orders bằng cách query tất cả buckets nhưng không cần cursor per bucket. Hàng tồn kho chia 10 counters, mỗi counter có toàn bộ stock ban đầu. Redis keys đều gắn `{tenantId}` để atomic. Dashboard chỉ theo dõi total table QPS, không cần per-shard metrics. Sau migration, xóa v1 vì record count bằng nhau.”

Hãy chỉ ra **ít nhất mười giả định sai hoặc thiếu bằng chứng**; viết lại design và test/rollout checklist để đáp ứng access patterns, performance, consistency và recovery.

## 51. Lời giải mẫu và hướng phân tích

### 51.1. Bài 1 — Top-k

Tổng là **10.000 writes/s**.

\[
\mathrm{Top1}=\frac{4800}{10000}=48\%
\]

\[
\mathrm{Top3}=\frac{4800+1600+900}{10000}=73\%
\]

T1 cần ưu tiên kiểm tra vì một `tenantId` có gần nửa traffic. Tuy nhiên **48% chưa đủ khẳng định quá tải** nếu mỗi partition/shard đủ capacity, item cost nhỏ và placement/reads không tương ứng; cần đo actual cost và SLO.

### 51.2. Bài 2 — Shard skew

Tổng **10.000 writes/s**, mean **1.250 writes/s**.

\[
\mathrm{MaxToMean}=\frac{5600}{1250}=4{,}48
\]

Chỉ shard 5.600 writes/s vượt threshold 2.000/s. Thêm nodes không làm một **hot single partition key** tự chia nhỏ nếu engine không split/reroute work theo semantics yêu cầu.

### 51.3. Bài 3 — Lower bound

\[
R_{T-A}=20\,000\times45\%=9\,000/s
\]

\[
R_{\mathrm{ideal}}=20\,000/16=1\,250/s
\]

\[
9000/1250=7{,}2
\]

Shard chứa toàn bộ T-A chịu ít nhất 7,2× mean lý tưởng, **chưa tính các tenants khác cùng shard**.

### 51.4. Bài 4 — B tối thiểu

\[
B_{\min}=\lceil9000/750\rceil=12
\]

Với B=16:

\[
9000/16=562{,}5/s
\]

Nếu bucket nóng hơn expected 30%:

\[
562{,}5\times1{,}3=731{,}25/s
\]

Theo đúng assumptions, **731,25 dưới 750** nên B=16 vẫn đạt giới hạn load bình quân trên hot bucket đó. Nhưng đây không phải proof per-physical-node capacity, burst headroom hoặc guarantee mọi bucket sẽ ở dưới 750.

### 51.5. Bài 5 — Fan-out

32 buckets ⇒ tối đa **32 partition queries**, mỗi bucket lấy 50 ⇒ **1.600 candidates** để trả 50, ratio candidates/returned = **32×**. Cần k-way merge lazy/adaptive fetch, bounded fan-out, projection/index và per-bucket cursors nếu API p99 yêu cầu thấp.

### 51.6. Bài 6 — Reads vs writes

Trong mô hình 1 cost unit/subquery: AP2 base query cost **1 vs 32 units**, chưa cộng network/merge. P99 không nhất thiết 32× vì subqueries có thể chạy song song, cache, adaptive fetch; nhưng càng nhiều subqueries càng dễ gặp slowest-shard tail. Chấp nhận B nếu tenant-only vi phạm write capacity/correctness và có cách đáp ứng read SLO.

### 51.7. Bài 7 — Time bucket

Đổi day→hour **không chia writes trong cùng giờ/phút** vì tất cả vẫn có cùng hour key.

\[
100\,000\text{ events/min}\div60\approx1666{,}67/s
\]

Với 20 buckets:

\[
1666{,}67/20\approx83{,}33/s/bucket
\]

Query tuần có thể cần 7 ngày ×20 buckets nếu key day+bucket, hoặc 168 giờ ×20 nếu hour+bucket, trước tối ưu. Late events phải route theo event-time/ingestion-time policy đã chọn, không im lặng đổi nghĩa timestamp.

### 51.8. Bài 8 — Modulo migration

Đổi B=16→32 có thể đổi routing nhiều old keys. Cần **keyVersion**, stored bucketCount, versioned directory hoặc explicit old/new lookup during migration, backfill/CDC/cutover và dedup/conditional apply. Xóa old placement chỉ sau đối soát version/deletes, new backup và hết rollback horizon.

### 51.9. Bài 9 — Hot Order

Hash đặt O-HOT vào **một** shard, không chia được 3.000 updates/s của cùng entity. Nếu một CAS version phải serialize mọi update, throughput có ceiling do coordination/storage. Có thể chuyển sang append events/independent sub-aggregates khi domain invariant cho phép, hoặc giữ one authority với admission và batching.

### 51.10. Bài 10 — Escrow

\[
200+250+300+250=1000
\]

B0 không thể tự tăng thêm 40 nếu B2 vẫn được quyền bán 40 đó. Cần reservation/lease/transfer protocol ngăn **double allocation**: debit/lock source quota và ghi transfer state durable trước khi credit destination, idempotency ID và outcome lookup khi timeout.

### 51.11. Bài 11 — Oversell

10 buckets mỗi bucket có `available=100` có thể chấp nhận tổng **1.000 reservations**, dù stock thực tế 100, oversell 900. Đúng là phải chia 100 physical units thành quotas sao cho tổng không vượt 100 và mọi transfer/bucket decrement được quản lý nguyên tử theo protocol.

### 51.12. Bài 12 — GSI hotspot

Base PK phân phối đều không đảm bảo GSI PK có cardinality/load đều. `PAID` là low-cardinality index key; shard theo `status#day#bucket` giúp phân tán writes nhưng query PAID hôm nay phải fan-out nhiều keys rồi merge/aggregate. Cần đo GSI write cost, consumed capacity, eventual lag và query p99.

### 51.13. Bài 13 — Clustering key và point lookup

Biết `(tenantId,orderId)` nhưng không biết `dayUtc,bucket,createdAt` không đủ tạo full primary-key lookup trong table example. Dùng **orders_by_id** (key theo tenant+orderId) và **events_by_tenant_day_bucket** cho timeline, duy trì theo atomic transaction nếu engine hỗ trợ scope hoặc qua outbox/CDC với idempotency/freshness policy.

### 51.14. Bài 14 — Range hotspot

`createdAt` tăng làm writes vào rightmost range. Hashed key có thể phân tán distinct IDs nhưng date-range scans khó targeted hơn. Balancer/chunk splits có thể giúp khi giới hạn engine cho phép, song không được giả định split tức thời sửa mọi hotspot mà không cần đo.

### 51.15. Bài 15 — Redis hash tag

Các keys `cart:{T-A}:...` hash cùng phần `{T-A}` nên thường cùng hash slot. Đổi tag thành bucket có thể trải across slots nhưng multi-key operations **khác slots** có thể mất tính hỗ trợ/atomicity. Nếu một cart C1 thật sự nóng, mọi requests đến C1 vẫn chung bucket.

### 51.16. Bài 16 — Cosmos RU

Tăng tổng RU không tự đảm bảo một hot logical partition hết throttling. Synthetic key chia T-A thành nhiều logical keys; cần query fan-out và PK knowledge. Transactional batch across different PK values **không còn là cùng logical partition transaction**; consistency/session tokens phải được xử lý theo product contract.

### 51.17. Bài 17 — Search routing

`_routing=tenantId` gom documents T-A vào một routing shard, có thể hot. Các phương án gồm routing partition strategy được engine hỗ trợ, index modeling, splitting hot tenant hoặc ingest reshape. Đổi routing thường tăng read fan-out cho tenant queries; nếu hot là reads, consider replicas/caches với freshness.

### 51.18. Bài 18 — Data bytes

Shard A:

\[
2000\times1\ \mathrm{KiB/s}=2000\ \mathrm{KiB/s}
\approx1{,}95\ \mathrm{MiB/s}
\]

Shard B:

\[
2000\times100\ \mathrm{KiB/s}=200\,000\ \mathrm{KiB/s}
\approx195{,}31\ \mathrm{MiB/s}
\]

Raw payload B ≈ **100×** A theo median-as-representative giả định; thực tế dùng distribution/average bytes và index/WAL/replica multipliers, vì median×QPS không nhất thiết bằng total bytes thực.

### 51.19. Bài 19 — Slowest subquery

Với 2% xác suất chậm độc lập trên 20 subqueries:

\[
P(\ge1\text{ slow})=1-(0{,}98)^{20}
\approx33{,}24\%
\]

Khi các subqueries cùng node/network, sự kiện có thể tương quan và công thức độc lập không còn đúng; cần fault-load measurements. Bounded top-N projection giảm fan-out nhưng tăng write maintenance.

### 51.20. Bài 20 — RF storage

12 TiB logical × RF3 = **36 TiB replicated raw payload**. Trên 12 nodes, bình quân **3 TiB/node**, bằng **75%** usable 4 TiB/node trước indexes/compaction/snapshots/overhead. Đây có thể là rủi ro lớn với node failure/rebalancing.

### 51.21. Bài 21 — Partition size

Một ngày có \(86\,400\) giây:

\[
5000\times86400\times2=864\,000\,000\ \mathrm{KiB}
\]

\[
\frac{864\,000\,000}{1024^2}\approx823{,}97\ \mathrm{GiB/day}
\]

Với B=8:

\[
823{,}97/8\approx103{,}00\ \mathrm{GiB/bucket/day}
\]

**B=8 không đạt target 20 GiB logical payload/partition** trong giả định uniform distribution. Lower bound theo bytes \(\lceil823{,}97/20\rceil=42\) buckets; cần thêm headroom và cost/read fan-out trước chọn B. Nếu events chỉ chạy một phần ngày thì phải tính lại.

### 51.22. Bài 23 — Virtual buckets

128 virtual bucket identities có thể giữ nguyên khi tăng 4→8 shard groups; di chuyển selected buckets' data/ownership qua engine-supported rebalancing, đồng bộ directory version/cutover. Chỉ sửa directory trước khi copy data có thể route requests tới nơi chưa có record. Một virtual bucket tự nó hot có thể vẫn cần chia subkey/domain workload.

### 51.23. Bài 24 — CDC gap

Target applied tới L1490 trong khi source committed tới L1500 ⇒ còn **unapplied suffix** trong mô hình scalar log. Không cutover nếu yêu cầu no-loss và chưa reconcile. Với multiple shards hoặc distributed transactions, cần per-shard positions/global cut protocol; không suy hoàn tất từ một số L duy nhất.

### 51.24. Bài 25 — Cursor

`lastCreatedAt` không đủ khi cùng timestamp và bucket có riêng progress; cần stable tuple `(createdAt, orderId)`, per-bucket cursors/watermarks và keyVersion. Cursor v2 khi policy v3 nên được xử lý bằng compatibility routing hoặc explicit expiration/restart, không diễn giải lặng lẽ.

### 51.25. Bài 26 — Replica placement

Hash/bucket distribution không bảo đảm AZ independence. Nếu cả replicas cùng AZ A, mất A có thể mất availability hoặc data theo durability semantics. Cần replica placement trải failure domains và N+AZ CPU/IO/storage headroom + single-AZ fault tests.

### 51.26. Bài 27 — Adaptive policy

Không đổi B trực tiếp nếu data persisted theo old routing. Cần policy version, backfill/CDC, gradual cutover và guard chống split authority. Auto-tune B phải có hysteresis/minimum observation period và cost model để không tăng/giảm liên tục khi workload dao động.

### 51.27. Bài 28 — Open-loop

Closed-loop workers đợi response nên khi latency tăng, RPS có thể tự giảm, che overload. Open-loop giữ lịch offered requests nhưng phải báo actual sent/accepted/queued/rejected, driver/SDK attempts, user latency và generator saturation. Coordinated omission làm p99 có vẻ thấp hơn thực tế.

### 51.28. Bài 29 — Một phương án kiến trúc

Một thiết kế khả thi để **đưa vào thử nghiệm**, chưa phải kết luận cuối:

~~~text
Canonical Orders:
  Business identity (tenantId, orderId)
  Routing/partition derived from stable orderId or tenant+bucket
  Conditional version update with operationId

RecentOrdersByTenant:
  Partition (tenantId, UTC day, bucket)
  Sort (createdAt DESC, orderId)
  Query latest50 via bounded parallel fan-out + k-way merge

OrdersByCustomer:
  Partition (tenantId, customerId, timeBucket/bucket)
  Sort by createdAt

Inventory:
  Single authority for SKU-HOT OR proven escrow/quota protocol
  Stable reservation IDs + atomic conditional decrement

Operations:
  Per-keyVersion routing directory/manifest
  Replicas across AZs, degraded N+AZ capacity
  Backfill + CDC + reconciliation + versioned cursor
  Per-shard top-k and p99/cost dashboards
~~~

**Gate quyết định:** AP1/AP2 p99, peak partition throttling, no oversell/no duplicates, realistic fan-out cost, one-AZ failure performance, restore/rollback ability. Nếu một gate không đạt, cần đổi key/projection/capacity.

### 51.29. Bài 30 — Các lỗ hổng đề xuất

1. Cardinality 5.000 tenants không đồng nghĩa phân phối đều.
2. Một tenant lớn có thể nhận 45% traffic.
3. `createdAt` sort key không tự chia hot writes.
4. Thêm nodes không tự chia hot logical partition.
5. Không có measured per-key/shard capacity ceiling.
6. Đổi modulo 16→32 làm old keys đổi bucket.
7. Không có backfill/cutover/CDC/keyVersion.
8. Timeline query nhiều buckets cần bounded fan-out và merge.
9. Cursor chỉ timestamp có thể miss/duplicate.
10. Inventory counters cùng full stock làm oversell.
11. Redis hash tag tenant rộng gom mọi keys cùng slot.
12. Aggregate table QPS che hot shard/index partition.
13. Record counts bằng nhau không chứng minh keyset/versions/deletes đúng.
14. Xóa v1 trước rollback/backup gates gây data loss.
15. Không xem GSI/search/read projection write amplification.
16. Không có fault/load test với hot tenants, burst và AZ outage.
17. Không có idempotency, conditional versions, write outcome plan.
18. Không đo storage skew, IOPS, p99, fan-out và cost.

Kế hoạch tốt hơn: access-pattern inventory → đo top-k và capacity → chọn một số candidate keys → mô phỏng với cùng workload → staging load/fault benchmark → keyVersion/backfill/CDC/rollback → canary với metrics → decommission theo gates.

## 52. Checklist 60 điểm cho thiết kế khóa và phân vùng

### 52.1. Yêu cầu và mô hình dữ liệu

1. Đã liệt kê các access patterns quan trọng, RPS và p99 yêu cầu chưa?
2. Có phân biệt GET by ID, timeline, range query, analytics và batch không?
3. Có xác định business identities và unique constraints không?
4. Có yêu cầu read-your-writes/transaction consistency/conditional mutations không?
5. Có xác định state là source-of-truth, event log, cache hay projection không?
6. Có phân loại dữ liệu mutable, append-only, counter và blob riêng không?
7. Có xác định các records/operations không được chia atomic scope không?
8. Có thiết kế key/cursor cho pagination và stable ordering không?
9. Có xem yêu cầu multi-tenant isolation và authorization không?
10. Có biết retention/TTL/backup/archive phụ thuộc key structure không?

### 52.2. Đo skew

11. Có đo top1/top10 share theo reads và writes tách biệt không?
12. Có đo max-to-mean per-shard load và capacity saturation không?
13. Có heatmap theo giờ/phút, không chỉ daily average không?
14. Có đo bytes/partition và large-document distribution không?
15. Có phân biệt hot single key và hot logical partition không?
16. Có đo read cost vs write cost vs index/replica overhead không?
17. Có kiểm tra SKU/customer/tenant/region/time skew không?
18. Có kiểm tra shifting hotspots khi campaign/business growth không?
19. Có đo actual physical shard ownership/replica placement không?
20. Có bảo vệ PII/cardinality khi thu thập hot-key diagnostics không?

### 52.3. Thiết kế khóa và query

21. Có so tenant-only, order-hash, composite và bucketed keys không?
22. Có tính lower bound từ hot tenant/partition rate không?
23. Có chọn bucket count theo measured safe load và headroom không?
24. Có kiểm tra data-size ceiling cho mỗi logical partition không?
25. Có phân biệt time bucket với hash subbucket không?
26. Có xử lý late-arriving events và UTC/local timezone semantics không?
27. Có stable hash/canonicalization/test vectors across services không?
28. Có keyVersion/directory khi bucket count thay đổi không?
29. Có tính targeted vs scatter-gather và query fan-out/p99 không?
30. Có explicit index/projection design cho customer/timeline queries không?

### 52.4. Tính đúng dữ liệu và hot mutable state

31. Có tách single hot-item contention khỏi record distribution không?
32. Có conditional update/optimistic version và idempotency keys không?
33. Có ghi rõ unknown write outcome và retry semantics không?
34. Với inventory, có proof không oversell hoặc authoritative serialization không?
35. Nếu dùng escrow, tổng quotas và transfers có invariant không?
36. Có plan tránh duplicate reservation khi timeout/replay không?
37. Có tính write amplification của secondary indexes/materialized views không?
38. Có tính freshness/catch-up lag của projections không?
39. Có test session consistency/fallback khi read model chậm không?
40. Có hiểu atomic batch/transaction scope khi data chuyển buckets không?

### 52.5. Benchmark và vận hành

41. Có staging dataset/skew/traffic mix giống production enough không?
42. Có uniform, Zipf, hot-key, burst, time-append tests không?
43. Có open-loop load và offered-vs-accepted RPS không?
44. Có theo dõi actual SDK routing, backend attempts và p99 không?
45. Có test physical shard distribution, not just logical buckets không?
46. Có test one-AZ failure và degraded capacity/rebalancing không?
47. Có theo dõi CPU/IOPS/disk/network/RU/throttling và cost không?
48. Có rate limits, bounded concurrency và stop conditions khi hotspot không?
49. Có test cold/warm cache và large-document tails không?
50. Có runbook xử lý hot tenants và partition growth không?

### 52.6. Migration, backup và quyết định cuối

51. Có biết đổi partition key có được engine hỗ trợ trực tiếp không?
52. Có keyVersion/bucket count/directory migration plan không?
53. Có consistent snapshot/backfill and CDC continuation không?
54. Có đối soát keys/values/versions/deletes/TTL trước cutover không?
55. Có fencing/authority epoch để ngăn old/new divergence không?
56. Có pagination cursor compatibility qua rekey không?
57. Có backup/PITR/recovery và rollback/forward-repair plan không?
58. Có canary success/p99/cost/consistency acceptance gates không?
59. Có owner, ADR, schema/docs, dashboard và on-call handoff không?
60. Có đóng old key version/decommission sau retention/approval gates không?

## 53. Mẫu Architecture Decision Record

~~~markdown
# ADR — Order partition-key strategy for skewed tenants

## Business context
- Top tenant share during peak: [measured]
- Important access patterns and SLOs: [measured]
- Business invariants: [listed]

## Candidate strategies
1. tenant-only
2. hashed order ID
3. tenant + stable order bucket
4. tenant + UTC-day + stable order bucket

## Evidence
- Top-k tenant/key distributions: [link]
- Per-shard load / bytes / index hotness: [link]
- Simulated and real SDK load tests: [link]
- AP1/AP2 p99 and fan-out: [link]
- Storage and AZ-failure capacity: [link]

## Decision
- Canonical Orders PK/shard routing: [explicit]
- Timeline/customer read model: [explicit]
- Bucket count, hash algorithm and version: [explicit]
- Inventory consistency/escrow policy: [explicit]

## Trade-offs
- Write distribution versus read fan-out
- Extra index/projection writes and freshness lag
- Pagination complexity
- Data movement and rebalancing cost
- Operational dependencies and failure domains

## Migration
- Snapshot/backfill boundary: [source position]
- CDC/high-water and reconciliation: [evidence]
- Shadow reads / canary / cutover epoch: [plan]
- Rollback and retained backup: [plan]

## Acceptance
- Per-shard safe load/bytes: [measured thresholds]
- User API success and p99: [measured SLO]
- Zero duplicate reservation/oversell: [test]
- One-AZ degraded mode: [test]
- Cost ceiling and alert thresholds: [approval]
~~~

Đây là **mẫu lập luận**, không phải ADR đã được nghiệm thu. Những giá trị `[measured]` cần thay bằng số liệu có nguồn, không tự suy đoán.

## 54. Một phương án triển khai theo từng bước

Trong bài toán Order Service, có thể theo chuỗi công việc sau:

1. **Quan sát hiện trạng:** lấy read/write traffic theo tenant, key, date, p99, backend cost và top-k share. Xác nhận có T-A 45% traffic, không chỉ từ dự đoán.
2. **Xếp loại access patterns:** AP1 và AP5 cần direct lookup; AP2/AP3 có thể dùng read model; inventory yêu cầu bất biến không oversell.
3. **Đề xuất candidate keys:** tenant-only, hashed orderId, tenant+bucket, tenant+day+bucket. Ghi giả định consistency/size.
4. **Tính toán sơ bộ:** T-A 9.000/s, B=16 expected 562,5/s/bucket; 16-way AP2 fan-out; storage/index/replication capacity.
5. **Mô phỏng reproducible workload:** seed cố định, uniform+Zipf+hot-key/bursts; xem per-shard max-to-mean và fan-out.
6. **Thử với engine thật:** key/index definitions, SDK routing, per-shard metrics, p99, throttling, storage costs; đưa case hot SKU vào test.
7. **Bảo vệ correctness:** versioned conditional writes, idempotency, authoritative stock or escrow protocol, query projection freshness policy.
8. **Chuẩn bị migration:** keyVersion, source cut, backfill, CDC continuation, dual routing and snapshot consistency.
9. **Đối soát và cutover:** compare keysets/versions/deletes, route changes có fencing, canary và rollback.
10. **Đánh giá sau triển khai:** monitor hotspots mới, read amplification, physical placement/AZ failure, backup/restore và tài liệu vận hành.

Không bước nào trong 10 bước cho phép thay thế **thử nghiệm với engine thật** bằng một toy hash simulator khi ra quyết định production.

## Kết luận

**Thiết kế khóa và phân vùng cho dữ liệu có phân bố lệch là bài toán phối hợp dữ liệu, truy vấn, tải và tính đúng nghiệp vụ.** Không có quy tắc “cứ hash là đều” hoặc “cứ thêm buckets là xong”.

Những kết luận cần nhớ:

- **Key cardinality cao chưa đủ:** phân phối thực tế của reads/writes/cost mới quyết định hotspot.
- **Hash giúp phân phối nhiều distinct keys**, không phá bottleneck của một mutable hot item.
- **Tenant-only locality tốt cho reads nhưng dễ thành hot partition** khi một tenant có 45% traffic.
- **Composite hash buckets chia hot tenant**, nhưng tăng read fan-out, pagination complexity và chi phí duy trì indexes/projections.
- **Time bucketing chia lịch sử**, còn hot current-time writes có thể vẫn cần hash subbucket.
- **Thêm nodes không thay atomic scope:** inventory `available >= 0` cần serialization/escrow/quota protocol đúng.
- **Sort/clustering keys và query access paths phải thiết kế cùng partition keys**, không thể tối ưu writes rồi quên GET-by-ID hay latest-50.
- **Secondary indexes cũng có hotspots riêng**, dù primary table phân phối rất đều.
- **Bucket count phải có version/routing policy:** đổi `%16` sang `%32` mà không migrate có thể làm records trở nên không tìm thấy.
- **Physical placement, replica/AZ placement và N+AZ headroom** là những vấn đề khác nhau; virtual buckets không phải physical nodes.
- **Kiểm thử phải dùng real skew, bursts, fan-out và full fault/recovery**, rồi xác nhận per-shard load, p99, RU/IOPS và business invariants.
- **Migration là quá trình có dữ liệu và trạng thái đồng thời tồn tại ở hai nơi:** phải backfill, tiếp nhận changes, đối soát, fence, cutover, backup và có rollback plan.

Câu hỏi cuối cùng khi đánh giá một thiết kế:

> **“Với tenant/key nóng nhất, mỗi partition thật sự nhận bao nhiêu công việc và bytes trong giờ cao điểm; mỗi truy vấn quan trọng phải chạm bao nhiêu partitions; những giao dịch nào cần giữ nguyên tử; và kết quả load test có chứng minh mọi yêu cầu vẫn đúng khi hotspot dịch chuyển hoặc một miền lỗi biến mất không?”**

Nếu trả lời được bằng workload có thể tái lập, số liệu per-shard thực và kết quả đối soát, việc chọn partition key mới là **một quyết định thiết kế NoSQL có căn cứ**, không phải chọn công thức hash theo cảm giác.
