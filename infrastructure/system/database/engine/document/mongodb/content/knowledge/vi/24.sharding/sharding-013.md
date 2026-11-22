# Đánh giá thời điểm cần sharding và chi phí quản trị đi kèm trong MongoDB

## 1. Mục tiêu bài học

Một MongoDB replica set có thể đáp ứng tốt hệ thống trong thời gian dài. Khi dữ liệu, số lượng người dùng và tốc độ ghi tăng, đội kỹ thuật bắt đầu cân nhắc **sharding**: chia dữ liệu của một sharded collection thành các phần vật lý đặt trên nhiều shard. Nhưng sharding không phải công tắc “bật lên là mọi query nhanh hơn”. Nó giúp phân phối **dung lượng và một phần workload** với điều kiện chọn shard key phù hợp, đồng thời tạo thêm nhiều thành phần phải vận hành.

Bài thuộc chương **Sharding** tập trung vào hai câu hỏi:

1. **Khi nào thật sự cần sharding?** Cần xác minh giới hạn của một replica set, phân tích tăng trưởng và đánh giá các giải pháp đơn giản hơn.
2. **Chi phí quản trị đi kèm là gì?** Không chỉ tiền máy chủ mà còn router, config servers, index, balancer, network, backup, upgrades, distributed transactions, monitoring và kỹ năng vận hành.

Sau bài học, bạn có thể:

- Đọc các dấu hiệu capacity về CPU, RAM, IOPS, disk, network, throughput và query latency.
- Phân biệt **scale-up, replication, sharding và business partitioning**.
- Dùng dữ liệu/metric để đưa ra quyết định **chưa shard / chuẩn bị shard / nên shard**.
- Ước tính sơ bộ số shard dựa trên tăng trưởng, headroom và data skew.
- Đánh giá shard-key cardinality, frequency, monotonicity và query targeting.
- Phân tích ảnh hưởng của sharding tới unique index, aggregation, transaction và consistency.
- Lập kế hoạch benchmark, migration, quan sát lỗi và bảo trì cluster.
- Trình bày quyết định kiến trúc bằng bảng chi phí–lợi ích có căn cứ.

**Nguyên tắc cốt lõi:** Chỉ nên sharding khi có **nút thắt đã đo được**, workload **có thể phân phối hiệu quả**, và lợi ích vượt chi phí vận hành tăng thêm.

## 2. So sánh các chiến lược mở rộng

| Phương án | Bản chất | Lợi ích chính | Giới hạn |
| --- | --- | --- | --- |
| **Tối ưu query/index** | Giảm dữ liệu phải đọc/xử lý | Giảm p95/p99 và I/O không cần thiết | Không tăng dung lượng máy vật lý |
| **Scale-up** | Tăng CPU, RAM, disk/IOPS cho node | Nâng năng lực một node, ít thay đổi ứng dụng | Có giới hạn phần cứng/chi phí |
| **Replication** | Nhiều bản sao cùng dataset trong replica set | HA, failover, tùy chọn secondary reads | Write thông thường vẫn về một primary |
| **Sharding** | Phân phối document theo shard key lên nhiều shards | Scale-out storage và workload phù hợp | Thêm router, metadata, balancing, fan-out |
| **Phân vùng nghiệp vụ** | Tách theo tenant, năm, vùng hoặc đơn vị kinh doanh | Dễ quản lý, cách ly và retention | Có thể chỉ là logic, không phải chia máy |

Một replica set gồm primary và secondary **không** tương đương ba shards:

~~~text
Replica set
  Primary A       Secondary B       Secondary C
  cùng dataset    cùng dataset      cùng dataset
       |                ^                 ^
       +----------------+-----------------+
               Sao chép dữ liệu

Sharded cluster
  Application
       |
     mongos
    /  |   \
   v   v    v
Shard 1  Shard 2  Shard 3
subset A subset B subset C
   |       |         |
replica  replica   replica
set      set       set
~~~

Trong một sharded cluster tiêu chuẩn, mỗi shard thường là một **replica set** để chịu lỗi member; `mongos` định tuyến truy vấn và **config server replica set (CSRS)** giữ metadata. MongoDB 8.0 giới thiệu lựa chọn config shard trong trường hợp hỗ trợ; thiết kế thực tế cần theo phiên bản cụ thể.

**Sharding phân phối dữ liệu**, còn **replication nhân bản dữ liệu của từng shard**. Hai cơ chế bổ trợ nhau.

## 3. Xác định nút thắt trước khi đưa ra giải pháp

Câu nói “database đang chậm” không đủ để chứng minh cần sharding. Những nguyên nhân thường gặp:

- Một query dùng `COLLSCAN` vì thiếu index.
- `$sort` hoặc `$group` xử lý quá nhiều document.
- Working set dữ liệu + index nóng vượt RAM/cache.
- Disk latency cao vì SSD thiếu IOPS.
- Primary bị bão hòa write CPU/lock contention.
- Query báo cáo của một tenant chiếm tài nguyên.
- Quá nhiều indexes làm write amplification tăng.
- Ứng dụng tạo N+1 queries hoặc phân trang bằng `skip` quá sâu.
- Kết nối/network chậm hoặc connection pool bị nghẽn.
- Replication lag hoặc failover khiến một số request bị timeout.

Chuyển một query thiếu index từ một replica set sang năm shards có thể biến nó thành **năm collection scans** cộng thêm công đoạn merge. Kết quả chưa chắc nhanh hơn.

### 3.1. Bộ metric tối thiểu cần thu thập

| Nhóm | Metric nên quan sát | Câu hỏi phải trả lời |
| --- | --- | --- |
| Query | p50/p95/p99 theo operation, timeout/error rate | Chậm ở API và thời điểm nào? |
| Query plan | `IXSCAN`/`COLLSCAN`, `totalDocsExamined`, `totalKeysExamined` | Có đang quét dữ liệu thừa? |
| CPU | Primary/secondary CPU, system/user CPU | CPU dùng cho write hay query? |
| Cache/RAM | Cache occupancy, eviction, page faults, working set | Data/index nóng có vừa RAM? |
| Disk | Data + index size, free space, tăng trưởng | Khi nào chạm mức capacity an toàn? |
| I/O | IOPS, latency, queue depth, throughput | Ổ đĩa có đang bão hòa? |
| Write | Ops/s, write latency, concurrency | Primary còn headroom không? |
| Replication | Lag, oplog window, election | Có vấn đề HA hoặc secondary overload? |
| Network | RTT, bandwidth, retransmits | Nút thắt có nằm ngoài MongoDB? |
| Skew | QPS/bytes theo tenant hoặc key ứng viên | Một key có giữ phần lớn workload? |

Không có ngưỡng phổ quát như **“collection trên 500 GB là bắt buộc shard”** hay **“CPU 80% thì shard”**. Với máy/SSD/index/workload khác nhau, cùng một con số có thể có ý nghĩa khác nhau.

### 3.2. Thu cả workload bình thường và giờ cao điểm

Một snapshot CPU lúc 2 giờ sáng không đại diện traffic lúc 9 giờ sáng. Cần bao phủ chu kỳ ngày/tuần, giờ sale, report cuối tháng, batch jobs và những hoạt động maintenance đáng kể.

Nên gắn metrics với:

- Tenant hoặc business unit nếu có.
- API operation name.
- Mẫu filter và sort.
- Kích thước response.
- Loại đọc/ghi.
- Read concern/write concern và retry rate.

Thông tin nhạy cảm trong query và tenant identifiers phải được xử lý theo quy tắc bảo mật; không dump nguyên payload chứa dữ liệu cá nhân ra log.

## 4. Đặt SLO và giới hạn cho phép trước

Ví dụ một hệ thống đặt đơn hàng đưa ra **SLO giả định**:

- p95 đọc chi tiết đơn dưới 80 ms vào giờ cao điểm.
- p99 tạo đơn dưới 250 ms.
- Lỗi ghi dưới mức error budget đã thống nhất.
- Có ít nhất 18 tháng headroom dung lượng.
- Chịu lỗi một member mà không mất khả năng phục vụ lâu dài.
- Report không khiến API thanh toán chậm vượt SLO.

Những con số trên **chỉ là ví dụ**, không phải chỉ tiêu MongoDB mặc định.

Quyết định sharding nên xuất phát từ việc một replica set đã tối ưu **không thể đáp ứng SLO/capacity tương lai** một cách kinh tế và đáng tin cậy, không chỉ vì muốn dùng công nghệ mới.

## 5. Những tín hiệu cho thấy nên bắt đầu đánh giá sharding

### 5.1. Dung lượng và working set áp sát giới hạn một node

Nếu data + indexes tiếp tục tăng, một node có thể không còn đủ:

- Disk capacity với headroom cho compaction/backup/index builds.
- RAM/cache phục vụ working set.
- I/O cho đọc/ghi/replication.
- Thời gian phục hồi phù hợp RTO.

Tuy nhiên, dataset lớn không đồng nghĩa working set lớn. Nếu 90% là lịch sử không truy cập, chiến lược **archive, retention, time-based partitioning hoặc storage tiering** có thể giảm áp lực trước khi shard.

### 5.2. Write throughput bão hòa tại primary

Một replica set thông thường chỉ có **một primary nhận write**. Thêm secondary tăng khả năng chịu lỗi, không tự phân chia write lên nhiều primary.

Sharding có ích khi các write **được phân phối trên nhiều shard key values và nhiều shards**. Nếu hầu hết write thuộc một shard key value, hiệu quả có thể rất thấp.

### 5.3. Workload đọc có thể target ít shards

Điều kiện tốt:

~~~javascript
// Ví dụ dự kiến shard key {tenantId: 1, orderId: 1}
db.orders.findOne({
  tenantId: "T1",
  orderId: "ORD-1001"
});
~~~

Nếu router xác định được vùng shard key, query có thể target hẹp.

Điều kiện khó hơn:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Không có shard key trong filter có thể dẫn tới **scatter-gather**, gửi query đến nhiều/tất cả shards.

### 5.4. Giới hạn scale-up đã được chứng minh

Sau khi tối ưu truy vấn, schema, index, pooling, caching, batch operations, archive và capacity máy, nhóm kỹ thuật vẫn thấy:

- Peak traffic vượt sustainable throughput của một primary.
- Tăng kích thước máy tạo lợi ích giảm dần so với chi phí.
- Working set và recovery time không còn phù hợp một replica set.
- Có shard key candidate phân phối tốt trên workload đại diện.

Đây là nền tảng hợp lý để chuyển từ thảo luận sang POC sharding.

## 6. Những trường hợp chưa nên shard

| Vấn đề | Vì sao sharding chưa chắc giúp | Hướng ưu tiên |
| --- | --- | --- |
| `COLLSCAN` trên query nóng | Chuyển sang nhiều shard chỉ làm scan phân tán | Index/query rewrite |
| `skip` hàng trăm nghìn document | Offset pagination vẫn tốn kém | Keyset pagination |
| Một aggregation tạo mảng rất lớn | Bộ nhớ và BSON limits vẫn tồn tại | Tối ưu pipeline/output |
| Dữ liệu lịch sử ít đọc chiếm phần lớn dung lượng | Active dataset có thể nhỏ | Archive/retention |
| Primary CPU cao do quá nhiều indexes | Sharding không sửa write amplification | Rà index dư thừa |
| Chỉ muốn HA | Sharding vẫn cần replica set trong từng shard | Replica set + backup |
| Một tenant chiếm 90% write và key chỉ là tenantId | Một giá trị key dễ trở thành hotspot | Compound key hoặc isolate tenant |
| Chưa có SLO hay baseline | Không đo được lợi ích | Instrumentation |
| Không có runbook/backup cluster-wide | Rủi ro khi sự cố và migration | Xây năng lực vận hành trước |
| Query đều là global reports | Fan-out và merge có thể tốn kém | Cân nhắc pre-aggregation/caching |

Một quyết định **chưa shard** sau khi đo đạc và tối ưu có thể là quyết định kỹ thuật tốt nhất.

## 7. Mô hình ước tính dung lượng và số shard

Giả sử **số liệu minh họa**:

- Data + index của một bản dataset hiện tại: **1,20 TB**.
- Tăng trưởng dự báo: **0,08 TB/tháng**.
- Horizon cần dự phòng: **18 tháng**.
- Mục tiêu sử dụng dành cho data + indexes: **0,80 TB/shard** trong mức capacity an toàn đã chọn.
- Hệ số dự phòng cho phân bố lệch và hot ranges: **25%**.

### 7.1. Tính dung lượng dự báo

~~~text
Dung lượng 18 tháng
  = 1,20 TB + (0,08 TB × 18)
  = 2,64 TB
~~~

### 7.2. Tính shard sơ bộ

~~~text
N = ceil(2,64 / 0,80)
  = ceil(3,30)
  = 4 shards
~~~

### 7.3. Thêm hệ số skew

~~~text
N có dự phòng = ceil(2,64 × 1,25 / 0,80)
              = ceil(4,125)
              = 5 shards
~~~

Đây chỉ là **mô hình storage sizing sơ bộ**, không phải lệnh phải mua năm shards. Cần kiểm tra riêng throughput, IOPS, RAM, query targeting, số tenant, migration headroom và chi phí.

### 7.4. Chi phí replication trên các shards

Nếu mỗi shard có **3 data-bearing members**:

~~~text
5 shards × 3 members = 15 data-bearing mongod members

Data + index copies, về mặt lý thuyết:
2,64 TB × 3 = 7,92 TB

Chưa tính oplog, journal, filesystem overhead,
temporary files, compression differences,
config servers, backups và dung lượng dự phòng.
~~~

**25% safety factor không nhất thiết là 25% dữ liệu bổ sung**. Đây là capacity reservation nhằm tránh đạt sát ngưỡng, không phải số byte thực tế bắt buộc được nhân thêm.

Dù sharding phân tán 2,64 TB logic, replication vẫn tạo nhiều bản sao của từng shard.

## 8. Mô hình throughput: dữ liệu đều không có nghĩa tải đều

Giả sử benchmark cho thấy một primary đạt SLO ở **8.000 writes/giây** nhưng ở **12.000 writes/giây** thì p99 và I/O tăng quá cao. Hệ thống dự báo cần **18.000 writes/giây**.

Một phép chia lý tưởng:

~~~text
Shard A: 6.000 writes/s
Shard B: 6.000 writes/s
Shard C: 6.000 writes/s
~~~

có thể phù hợp nếu mỗi shard xử lý được và query/replication overhead chấp nhận được.

Nhưng một phân bố xấu:

~~~text
Shard A: 15.000 writes/s
Shard B:  2.000 writes/s
Shard C:  1.000 writes/s
~~~

vẫn khiến Shard A quá tải dù tổng capacity danh nghĩa cao.

**Không suy ra throughput tăng tuyến tính theo số shards.** Cần đo:

- Write QPS theo tenant/key candidate.
- Top 1% và top 10% key chiếm bao nhiêu tải.
- Số key phân biệt.
- Kích thước document và indexes per shard.
- Query pattern và transaction frequency.
- Network/replication overhead.
- Balancer movement khi đang có tải.

## 9. Shard key là quyết định quan trọng nhất

Sharding dựa trên **shard key** để ánh xạ document tới chunks/ranges. Shard key ảnh hưởng:

1. Phân phối dữ liệu.
2. Phân phối write.
3. Số shard mà mỗi query phải chạm.
4. Khả năng dùng ranges/zones.
5. Unique constraints.
6. Migration và resharding về sau.

### 9.1. Cardinality

**Cardinality** là số giá trị shard key khác nhau.

- Cardinality rất thấp có thể khó chia dữ liệu thành nhiều ranges nhỏ.
- Cardinality cao thường tạo nhiều lựa chọn phân chia hơn.
- Nhưng cardinality cao **không bảo đảm** phân bố đều nếu một vài key cực nóng.

### 9.2. Frequency

**Frequency** là số document/operation có cùng giá trị.

Ví dụ:

~~~text
Tenant A: 90% write QPS
Tenant B:  5% write QPS
Tenant C:  3% write QPS
Còn lại:  2%
~~~

Shard key chỉ là `{tenantId: "hashed"}` không tự chia traffic của tenant A ra nhiều shard, vì tất cả document cùng tenantId A cho cùng một giá trị hash.

### 9.3. Monotonicity

Khóa tăng tuần tự, như thời gian hoặc số đơn hàng tăng liên tục, có thể đưa các writes mới vào range cuối cùng của một shard.

Ranged key có thể hữu ích cho range queries, nhưng cần xử lý hotspot của khóa tăng đơn điệu. Hashed key có thể cải thiện phân phối một số loại workload, nhưng làm mất tính liên tiếp của các giá trị gốc.

### 9.4. Ranged và hashed sharding

| Thuộc tính | Ranged shard key | Hashed shard key |
| --- | --- | --- |
| Phân phối | Theo khoảng giá trị có thứ tự | Theo khoảng của giá trị hash |
| Query range theo key gốc | Thường thuận lợi hơn | Ít thuận lợi hơn |
| Khóa tăng liên tục | Có nguy cơ hotspot | Có thể phân tán tốt hơn |
| Một key chiếm nhiều write | Vẫn có thể nóng | Vẫn nóng vì cùng hash value |
| Unique hashed index | Không áp dụng | Hashed index không hỗ trợ `unique: true` |
| Zone policy | Dùng ranges của key | Cần hiểu ranges theo hash |

### 9.5. Compound shard key

Ví dụ:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Sử dụng hai trường có thể giúp có nhiều giá trị khóa trong từng tenant. Tuy nhiên:

- Query theo `tenantId` có thể vẫn chạm nhiều ranges/shards.
- Query theo đầy đủ `tenantId` và `orderId` thường có cơ sở target hẹp hơn.
- Query chỉ theo `status` có thể scatter-gather.
- Unique index cần tương thích shard-key prefix và các quy tắc version.

Không chọn compound key theo cảm giác “nhiều trường thì chia tốt hơn”, mà phải đo trên workload thật.

## 10. Query targeting và chi phí scatter-gather

Giả sử collection dùng shard key `{tenantId:1,orderId:1}`.

**Point query có đầy đủ shard key:**

~~~javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "A-001"
});
~~~

**Query chỉ theo tiền tố:**

~~~javascript
db.orders.find({
  tenantId: "A"
});
~~~

**Query không có shard key:**

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Khả năng routing thông thường:

| Query | Khả năng routing |
| --- | --- |
| Equality đầy đủ shard key | Thường target hẹp nhất |
| Filter trên tiền tố compound key | Có thể chạm một hoặc nhiều shards |
| Range theo shard key | Có thể target những ranges liên quan |
| Filter hoàn toàn ngoài shard key | Thường phải hỏi nhiều/tất cả shards |

Scatter-gather tạo thêm:

- Nhiều request nội bộ.
- Chi phí đọc/index scan trên mỗi shard.
- Network transfer.
- Merge/sort/aggregation liên shard.
- Phụ thuộc vào shard có phản hồi chậm nhất.

**Sharding và index giải quyết hai việc khác nhau:** shard key quyết định **hỏi shard nào**, còn index giúp mỗi shard **đọc ít dữ liệu hơn**. Một targeted query không có index vẫn có thể chậm; query có index nhưng hỏi mọi shard vẫn có chi phí fan-out.

## 11. Ràng buộc unique và transaction có thể đổi chi phí đáng kể

### 11.1. Unique indexes trên sharded collection

Trên sharded collection, việc enforce uniqueness có các điều kiện về shard key. Với ranged sharding, unique index thường phải có **toàn bộ shard key làm tiền tố** theo quy tắc MongoDB.

Giả sử shard key `{tenantId:1}`. Index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

bảo vệ cặp tenant/email, **không** bảo vệ email duy nhất trên toàn hệ thống.

Nếu yêu cầu email global unique, cần thiết kế lại shard key hoặc dùng một registry/coordination phù hợp. Không chỉ bỏ `tenantId` khỏi unique index rồi mong cluster bảo vệ mọi shard.

Với sharded collection mà `_id` không phải shard key, tính duy nhất của `_id` có thể chỉ được enforce trong phạm vi từng shard; ứng dụng cần tạo ID đủ duy nhất toàn hệ thống.

### 11.2. Giao dịch nhiều shard

Một chuyển tiền:

~~~text
Debit account ở Shard A
Credit account ở Shard B
~~~

không tự thành một thao tác nguyên tử chỉ vì chạy qua `mongos`. MongoDB hỗ trợ distributed transactions trên topology/phiên bản phù hợp, nhưng có thêm:

- Coordination và commit protocol.
- Network hops giữa participants.
- Transaction state/locks/resources.
- Retry khi xung đột hoặc lỗi tạm thời.
- Khả năng ảnh hưởng p99 latency.
- Đòi hỏi application xử lý lỗi giao dịch đúng.

Không có hệ số chi phí cố định cho mọi transaction; cần benchmark. Nhưng **tỷ lệ transactions chạm nhiều shards** là metric cần tính trước khi triển khai.

### 11.3. Read consistency không tự tốt hơn nhờ nhiều shards

Secondary của shard replica set vẫn có thể replication lag. Read concern, write concern và causal consistency vẫn cần thiết kế theo yêu cầu.

Ví dụ cập nhật tồn kho cần atomic conditional update:

~~~javascript
db.inventory.updateOne(
  { tenantId: "A", sku: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);
~~~

Không đọc stock cũ trên secondary rồi ghi trừ vô điều kiện và cho rằng sharding giải quyết được race condition.

## 12. Chi phí hạ tầng: từ ba member lên nhiều thành phần

### 12.1. Replica set đơn

Một replica set ba data-bearing members:

~~~text
App -> (P, S, S)
       3 mongod
~~~

Đội vận hành quản lý election, replication lag, oplog, backup, indexes và upgrades.

### 12.2. Sharded cluster ba shard

Một cấu hình minh họa với dedicated config servers:

~~~text
                          App
                           |
                        2 mongos
                           |
        +------------------+------------------+
        |                  |                  |
      Shard A            Shard B            Shard C
      P/S/S              P/S/S              P/S/S
        |                  |                  |
        +------------------+------------------+
                           |
                    CSRS (3 members)
~~~

Số tiến trình trong mô hình:

- 3 shard replica sets × 3 data-bearing members = **9 `mongod`**.
- 1 config server replica set × 3 members = **3 `mongod`**.
- 2 routers để tăng availability = **2 `mongos`**.
- Tổng **14 tiến trình** trước khi tính monitoring agents, backups, load balancers và infrastructure khác.

Đây **không phải cấu hình bắt buộc** trong mọi version/deployment: managed services và config shard có phương án khác. Nó chỉ minh họa vì sao tăng ba shards không phải “thêm đúng hai máy”.

### 12.3. Công thức TCO

~~~text
TCO =
  Compute của tất cả shard members
+ Storage / indexes / oplog / headroom
+ Config servers, routers
+ Network giữa member, shard, region
+ Backup và restore
+ Monitoring, logging, alerting
+ Upgrade và migration
+ On-call, runbooks, incident response
+ Chi phí kiểm thử và phát triển ứng dụng
~~~

Không thể chỉ nhân giá một database node với số shard rồi coi là tổng chi phí. Với managed service, một số khoản được gộp vào hóa đơn nhưng trách nhiệm thiết kế shard key, query routing và data correctness vẫn còn.

## 13. Chi phí quản trị theo vòng đời

| Hạng mục | Replica set đơn | Sharded cluster |
| --- | --- | --- |
| Topology | Primary + secondary | Shard replica sets, CSRS, routers |
| Query | Index/plan trên dataset | Thêm shard targeting, merge và fan-out |
| Data placement | Không có chunk migrations | Chunks/ranges và balancer |
| Monitoring | CPU, storage, lag | Những chỉ số đó **trên từng shard** + metadata/routing |
| Hotspot | Query, node, collection | Hot shard, hot range, shard-key value |
| Index management | Index của collection | Shard-key và unique constraints |
| Capacity | Scale-up replica set | Scale-up/down từng shard và thêm shards |
| Backup | Backup phù hợp replica set | Cluster-wide consistent backup |
| Restore | Khôi phục dataset | Cần phối hợp shards + metadata |
| Upgrade | Rolling upgrade/election | Trình tự shards, config servers, routers, FCV |
| Failover | Election trong replica set | Election trong mỗi shard + shard outages |
| Transactions | Một replica set | Có thể phát sinh distributed commit |
| Data reorganization | Migration riêng | Balancing, zones, resharding |

### 13.1. Balancer không cân bằng mọi thứ

MongoDB quản lý những khoảng shard key dưới dạng ranges/chunks. Balancer có thể di chuyển ranges theo cấu hình và zone rules.

Chi phí di chuyển gồm network, I/O, metadata coordination và temporary storage. Balancer chủ yếu giải quyết **placement**, không hứa làm CPU, bytes, số query và write QPS đều tuyệt đối.

Một hot tenant có thể tạo 80% writes trên một shard trong khi dung lượng mỗi shard khá cân bằng.

### 13.2. Backup, restore và RPO/RTO

Trong sharded cluster, snapshot từng shard ở những thời điểm tùy ý không đủ để khẳng định đã có **một trạng thái cluster-wide nhất quán**.

Cần phương án backup hỗ trợ topology và phiên bản, kiểm tra:

- Dữ liệu của tất cả shards.
- Config metadata/routing.
- Snapshot hoặc point-in-time consistency.
- Restore một collection/tenant hay toàn cluster.
- Thời gian phục hồi so với RTO.
- Mức mất dữ liệu chấp nhận so với RPO.
- Khả năng tái lập indexes, users và schema.
- Kịch bản restore được tập dượt thường xuyên.

Replication **không thay backup**: một thao tác xóa nhầm được chấp nhận có thể được sao chép tới các bản sao.

### 13.3. Upgrade và FCV

Sharded cluster có nhiều thành phần với yêu cầu tương thích version và **feature compatibility version (FCV)**. Thứ tự nâng cấp, preconditions, trạng thái balancer và chiến lược rollback phải theo tài liệu chính thức của phiên bản triển khai.

Không được tùy ý nâng cấp mỗi shard/router theo thứ tự bất kỳ chỉ vì các thành phần là những server riêng.

### 13.4. Observability per shard

Một dashboard chỉ hiển thị **CPU trung bình toàn cluster** có thể che khuất shard nóng. Nên theo dõi:

- CPU/RAM/IOPS/storage trên **từng shard member**.
- Read/write throughput per shard.
- Replication lag của từng replica set.
- Chunk/range distribution và migration activity.
- Tỷ lệ targeted vs scatter-gather.
- Slow operations, server-selection errors và router metrics.
- Connection pool, network, election events.
- Query p99 theo API/tenant.
- Capacity headroom và thời gian dự báo tới ngưỡng.

## 14. Failure domains: thêm shard cũng thêm tình huống lỗi

### 14.1. Mất một member

Nếu Shard A có replica set còn đa số voting members và member đủ điều kiện, một member hỏng có thể được xử lý bằng election/failover. Đây là lợi ích replication.

### 14.2. Mất cả shard

Nếu **toàn Shard B** không khả dụng, Shard A/C khỏe **không có bản sao toàn bộ subset B**. Các query cần dữ liệu của B có thể không thành công, dù những shards khác vẫn có thể phục vụ một phần workload.

### 14.3. Router/config metadata

`mongos` routes cần được triển khai có dự phòng phù hợp. Config server replica set giữ metadata cần thiết để điều phối cluster. Lỗi mạng hoặc metadata có thể ảnh hưởng operation và maintenance.

### 14.4. Hot shard

Nếu một shard đạt 100% CPU mà các shard khác ở 20%, trung bình cluster có vẻ chưa quá tải. Nhưng latency của query tới hot shard vẫn tệ.

**Quy tắc:** Khi sharding, phải giám sát **max per-shard resource utilization**, không chỉ mức trung bình.

## 15. Phân vùng nghiệp vụ như giải pháp thay thế hoặc bổ sung

### 15.1. TenantId trong cùng collection

~~~javascript
{
  tenantId: "tenant-A",
  orderId: "A-001",
  status: "PAID"
}
~~~

Dùng `tenantId` và compound index là **phân vùng logic**; nếu collection chưa được shard, dữ liệu vẫn ở một replica set.

### 15.2. Collection theo năm

~~~text
orders_2024
orders_2025
orders_2026
~~~

Có thể hỗ trợ archive/retention và giới hạn query trong một kỳ, nhưng nếu tất cả collections cùng một replica set thì không tự tăng write capacity.

### 15.3. Database per tenant

Mỗi tenant có database riêng có thể thuận tiện cho một số chính sách quản trị. Đổi lại, số namespace, migrations, backups và indexes tăng. Nếu cùng một cluster/primary, có thể vẫn cạnh tranh tài nguyên.

### 15.4. Dedicated cluster cho tenant lớn

Một tenant chiếm gần hết QPS hoặc cần SLA/vùng dữ liệu riêng có thể được tách vào cluster độc lập. Chi phí: mapping tenant→cluster, migration, cross-tenant reporting và quản lý nhiều deployments.

Không nhầm phương án nhiều clusters do application tự route với một sharded cluster mà `mongos` quản lý một sharded collection logic.

### 15.5. Archive trước khi shard

Nếu 80% storage là lịch sử lạnh, xem xét:

- Retention chính thức.
- TTL khi cho phép xóa.
- Collection phân chia theo kỳ.
- Cold storage.
- Pre-aggregated reports.
- Time-series collections nếu phù hợp measurement workload.

Cần phân biệt **có thể lưu ít dữ liệu nóng hơn** với **có cần scale-out những dữ liệu nóng còn lại không**.

## 16. Khung quyết định ba mức

| Trạng thái | Bằng chứng | Hành động |
| --- | --- | --- |
| **Chưa shard** | SLO đạt, headroom đủ, query chưa tối ưu | Tối ưu và đo tiếp |
| **Chuẩn bị shard** | Growth áp sát ngưỡng, key candidate rõ, còn thời gian POC | Thiết kế key, benchmark, staging, runbook |
| **Nên shard** | Bottleneck xác nhận, scale-up kém, workload phân phối tốt, đã sẵn sàng vận hành | Triển khai kiểm soát và theo dõi |

### 16.1. Go/no-go gates

Trước khi quyết định, cần trả lời:

- **G1 — Nút thắt:** tài nguyên nào thực sự hết headroom?
- **G2 — Phương án thay thế:** index/schema/cache/archive/scale-up đã được đánh giá chưa?
- **G3 — Key distribution:** cardinality/frequency/skew trên dữ liệu thật thế nào?
- **G4 — Query mix:** bao nhiêu phần trăm query target hẹp, bao nhiêu global?
- **G5 — Correctness:** unique indexes, transactions, consistency có phù hợp không?
- **G6 — TCO và vận hành:** có ngân sách, backup, monitoring, on-call và phương án rollback không?

Chỉ cần một **điều kiện bắt buộc** chưa rõ cũng có thể là lý do dừng rollout để thu thêm bằng chứng.

### 16.2. Ma trận điểm để hỗ trợ trao đổi

Có thể chấm từ 0 đến 3, nhưng không dùng tổng điểm như quyết định tự động:

| Yếu tố | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Dung lượng | Dư nhiều | Có áp lực | Sắp chạm giới hạn | Vượt ngưỡng an toàn |
| Growth 18 tháng | Chậm | Trung bình | Nhanh | Vượt capacity dự báo |
| Write saturation | Không | Chưa rõ | Có bằng chứng | Đã xác nhận và khó scale-up |
| Key distribution | Rất lệch | Chưa đo | Tương đối | Tốt trên workload thật |
| Query targeting | Hầu hết global | Nhiều global | Nhiều query target | Đa số target hẹp |
| Readiness | Chưa có | Thiếu | Staging/runbook | Đã rehearsal và có DR |

Điểm capacity cao không bù được shard key tệ. Các yếu tố có thể là **điều kiện bắt buộc**, không chỉ thành phần cộng điểm.

## 17. Lab mongosh: đo phân bố trước khi shard

Ví dụ này **không yêu cầu sharded cluster** và chỉ thao tác database thực hành.

~~~javascript
const lab = db.getSiblingDB("sharding_decision_lab");

// Chỉ xóa collection lab, không chạy trên production.
lab.orders.drop();

lab.orders.insertMany([
  { _id: 101, tenantId: "A", orderId: "A-001",
    status: "PAID", total: 100, createdAt: ISODate("2026-01-01T08:00:00Z") },
  { _id: 102, tenantId: "A", orderId: "A-002",
    status: "PAID", total: 150, createdAt: ISODate("2026-01-02T08:00:00Z") },
  { _id: 103, tenantId: "A", orderId: "A-003",
    status: "PENDING", total: 230, createdAt: ISODate("2026-01-03T08:00:00Z") },
  { _id: 104, tenantId: "A", orderId: "A-004",
    status: "PAID", total: 400, createdAt: ISODate("2026-01-04T08:00:00Z") },
  { _id: 105, tenantId: "A", orderId: "A-005",
    status: "PAID", total: 80, createdAt: ISODate("2026-01-05T08:00:00Z") },
  { _id: 106, tenantId: "A", orderId: "A-006",
    status: "CANCELLED", total: 20, createdAt: ISODate("2026-01-06T08:00:00Z") },
  { _id: 107, tenantId: "A", orderId: "A-007",
    status: "PAID", total: 260, createdAt: ISODate("2026-01-07T08:00:00Z") },
  { _id: 108, tenantId: "A", orderId: "A-008",
    status: "PAID", total: 110, createdAt: ISODate("2026-01-08T08:00:00Z") },

  { _id: 201, tenantId: "B", orderId: "B-001",
    status: "PAID", total: 75, createdAt: ISODate("2026-01-01T09:00:00Z") },
  { _id: 202, tenantId: "B", orderId: "B-002",
    status: "PAID", total: 125, createdAt: ISODate("2026-01-02T09:00:00Z") },
  { _id: 203, tenantId: "B", orderId: "B-003",
    status: "PENDING", total: 50, createdAt: ISODate("2026-01-03T09:00:00Z") },
  { _id: 204, tenantId: "B", orderId: "B-004",
    status: "PAID", total: 200, createdAt: ISODate("2026-01-04T09:00:00Z") },

  { _id: 301, tenantId: "C", orderId: "C-001",
    status: "PAID", total: 40, createdAt: ISODate("2026-01-01T10:00:00Z") },
  { _id: 302, tenantId: "C", orderId: "C-002",
    status: "CANCELLED", total: 60, createdAt: ISODate("2026-01-02T10:00:00Z") },
  { _id: 303, tenantId: "C", orderId: "C-003",
    status: "PAID", total: 90, createdAt: ISODate("2026-01-03T10:00:00Z") },

  { _id: 401, tenantId: "D", orderId: "D-001",
    status: "PAID", total: 700, createdAt: ISODate("2026-01-01T11:00:00Z") }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_date" }
);

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "uq_tenant_order" }
);
~~~

Có **16 orders** và **4 tenants**. Dữ liệu nhỏ để đối chiếu bằng tay, không phải dữ liệu đủ để benchmark sharding.

### 17.1. Phân bố số document

~~~javascript
lab.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      n: { $sum: 1 }
    }
  },
  { $sort: { n: -1, _id: 1 } }
]).toArray();
~~~

| Tenant | Số đơn | Tỷ lệ |
| --- | ---: | ---: |
| A | 8 | 50% |
| B | 4 | 25% |
| C | 3 | 18,75% |
| D | 1 | 6,25% |
| **Tổng** | **16** | **100%** |

Điều này **không chứng minh A tạo 50% QPS**: số document lịch sử và số operation mỗi giây là hai đại lượng khác nhau.

### 17.2. Tổng hợp đơn PAID

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

| Tenant | Đơn PAID | Giá trị PAID |
| --- | ---: | ---: |
| A | 6 | 1.100 |
| B | 3 | 400 |
| C | 2 | 130 |
| D | 1 | 700 |
| **Tổng** | **12** | **2.330** |

Đây là số giả định của lab, không phải báo cáo doanh thu thực. Với dữ liệu tiền tệ, cần kiểu số và quy tắc làm tròn phù hợp, ví dụ Decimal128.

### 17.3. Xem query plan

~~~javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Kiểm tra query plan, docs examined, keys examined và latency. Index `ix_tenant_status_date` được định nghĩa hỗ trợ pattern này, nhưng MongoDB có thể chọn plan khác trên collection lab rất nhỏ.

Trước khi quyết định sharding, hãy chắc chắn **query trong một shard đã hiệu quả**.

### 17.4. Xem thống kê collection

~~~javascript
lab.runCommand({
  collStats: "orders",
  scale: 1048576
});
~~~

Đầu ra phụ thuộc phiên bản và topology, nhưng có thể cung cấp thông tin về kích thước, storage/index và count. `scale` chỉ thay đơn vị hiển thị.

## 18. Thử nghiệm riêng trên sharded cluster đã chuẩn bị

Những thao tác sau **chỉ dành cho staging** kết nối qua `mongos`. Không tự thay đổi production metadata.

### 18.1. Quan sát cluster

~~~javascript
sh.status();
~~~

Trong nhiều cấu hình, `db.hello()` chạy qua `mongos` trả `msg: "isdbgrid"`, giúp phân biệt router với một `mongod` member.

### 18.2. Ví dụ shardCollection

Giả định workload đã được đánh giá và shard key `{tenantId:1,orderId:1}` đáp ứng preconditions:

~~~javascript
// Thay đổi kiến trúc/metadata: CHỈ chạy tại môi trường thử nghiệm.
sh.shardCollection(
  "sharding_decision_lab.orders",
  { tenantId: 1, orderId: 1 }
);
~~~

Điều kiện áp dụng và hành vi trên collection có dữ liệu phụ thuộc MongoDB version, indexes, uniqueness và trạng thái cluster. Đừng coi một lệnh ngắn là migration plan.

### 18.3. Targeted versus scatter-gather

~~~javascript
lab.orders.explain("queryPlanner").find({
  tenantId: "A",
  orderId: "A-001"
});

lab.orders.explain("queryPlanner").find({
  status: "PAID"
});
~~~

Trong explain, quan sát số shards được query và plan bên trong từng shard; cấu trúc field khác nhau theo version và query engine. Đừng nhầm `IXSCAN` trên mỗi shard với việc query đã target một shard duy nhất.

Có thể tham khảo `sh.status()` và các công cụ phân bố collection như `getShardDistribution()` nếu phiên bản/ngữ cảnh hỗ trợ. **Số chunks chưa phải chứng cứ QPS đã cân bằng.**

## 19. Benchmark ứng viên sharding

Đánh giá candidate cluster bằng **cùng dữ liệu và query mix** với baseline replica set, bao gồm traffic peak, skews, concurrency và các read/write concerns.

| Loại test | Metric | Mục đích |
| --- | --- | --- |
| Point read có full shard key | p95/p99, target shards | Kiểm tra routing hẹp |
| Tenant-only read | Fan-out, latency | Tenant lớn có trải nhiều shards? |
| Global aggregation | Scatter-gather, merge, CPU | Đo overhead báo cáo |
| Writes phân tán | Ops/s, p99, CPU per shard | Chứng minh scale-out |
| Writes từ một hot tenant | Hot shard, error rate | Phát hiện khóa lệch |
| Multi-shard transactions | Commit latency, retries | Đo coordination |
| Balancing/migration | Network, p99, resource spikes | Đánh giá tác động nền |
| Member failover | Error/recovery | Kiểm tra HA trong shard |
| Shard outage | Lỗi ứng dụng, partial availability | Kiểm tra failure handling |
| Backup/restore | RPO/RTO, consistency | Chứng minh phục hồi |

Nếu throughput trung bình tăng nhưng p99/error rate vượt SLO, phương án có thể **không đạt yêu cầu**.

Cần so sánh **tổng chi phí trên một đơn vị workload đáp ứng SLO**, không chỉ số request tối đa trong một benchmark ngắn.

## 20. Lộ trình triển khai có kiểm soát

### Giai đoạn A — Discovery

1. Thu metrics và query patterns đại diện.
2. Tối ưu query/index/schema còn có thể cải thiện.
3. Dự báo data + index growth và workload tăng trưởng.
4. Đo phân bố shard-key candidates.
5. Phân tích unique index, multi-shard transactions và global queries.
6. Đưa ra lợi ích/chi phí sơ bộ so với scale-up hoặc partitioning.

### Giai đoạn B — Proof of concept

1. Dựng staging sharded cluster phù hợp version/topology.
2. Nạp dataset đại diện, gồm hot tenants và dữ liệu tăng tuần tự.
3. Tạo indexes phù hợp từng query.
4. Đo throughput, p95/p99, storage, CPU/IOPS/network theo shard.
5. Thử balancer, failover và long-running aggregation.
6. Thử backup/restore thật, không chỉ tạo snapshot.

### Giai đoạn C — Readiness

1. Chuẩn bị connection URI/`mongos`/driver pools.
2. Rà shard-key requirements cho find/update/upsert.
3. Kiểm tra global unique IDs và constraints.
4. Xác định consistency/transaction semantics.
5. Thiết lập monitoring, alerting và runbooks.
6. Chuẩn bị contingency khi migration kéo dài hoặc thất bại.

### Giai đoạn D — Migration

1. Có backup được kiểm chứng trước khi thay đổi.
2. Chọn quy trình MongoDB hỗ trợ cho version/data state.
3. Kiểm soát writes trong các giai đoạn nhạy cảm.
4. Đối chiếu số lượng và business invariants.
5. Theo dõi chunk movement và query routing.
6. Cắt lưu lượng theo kế hoạch, có mốc dừng nếu vượt SLO.
7. Không tự coi việc “bỏ shard key” là rollback đơn giản; resharding/unsharding có điều kiện riêng.

### Giai đoạn E — Vận hành lâu dài

1. Theo dõi hot shards, growth và capacity headroom.
2. Định kỳ kiểm tra scatter-gather queries.
3. Kiểm thử restore, outage và upgrade.
4. Cập nhật shard-key assumptions khi workload thay đổi.
5. Đánh giá nhu cầu thêm shards hoặc resharding theo evidence.

Sharding là **một năng lực vận hành lâu dài**, không phải thao tác làm một lần.

## 21. Các kịch bản ra quyết định

### Kịch bản A — Query chậm vì thiếu index

Dataset 200 GB, CPU 85%, một endpoint p99 500 ms. `explain` cho thấy quét quá nhiều document vì thiếu index compound trên `status/category/price`.

**Quyết định:** Tối ưu index/query, đo lại trước. Nếu p99 giảm về mức SLO và còn headroom, chưa cần shard.

### Kịch bản B — Dung lượng và write QPS vượt một node

Dataset tăng đều, write QPS dự báo vượt ngưỡng primary, đa số query có tenant/order key và candidate shard key phân phối được write.

**Quyết định:** POC sharding là hợp lý. Phải đo thêm tỷ lệ hot tenant, global queries, unique constraints và chi phí.

### Kịch bản C — Một tenant lớn chiếm phần lớn traffic

Tenant A chiếm 92% write. Key `{tenantId:"hashed"}` không tự phân phối document cùng tenantId A.

**Quyết định:** Đánh giá compound shard key có trường phân phối trong tenant, dedicated cluster hoặc mô hình partition có routing phù hợp.

### Kịch bản D — Phần lớn dữ liệu là lịch sử lạnh

85% storage là logs không đọc trong vài năm. Retention và archive có thể giảm active dataset đáng kể.

**Quyết định:** Đánh giá archival/tiering/time partitions trước; không xóa dữ liệu ngoài chính sách.

### Kịch bản E — Data residency theo khu vực

EU và APAC cần vị trí lưu khác nhau. Có thể dùng zone sharding hoặc clusters riêng theo vùng.

**Quyết định:** So sánh locality và TCO. Zone placement **không tự bảo đảm** mọi replica member, backup, log hoặc export đều nằm đúng khu vực pháp lý.

## 22. Lỗi nhận thức thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Dữ liệu hơn 1 TB chắc chắn phải sharding” | Không có ngưỡng kích thước phổ quát |
| “Database chậm nên thêm shards” | Trước tiên xác định query/index/I/O bottleneck |
| “Ba replica members là ba shards” | Replica members giữ cùng dataset; shards giữ subsets |
| “Thêm secondary tăng write capacity” | Write thường vẫn về primary của replica set |
| “Shard càng nhiều query càng nhanh” | Scatter-gather và merge có thể đắt |
| “Hash tenantId chia một hot tenant ra tất cả shards” | Một tenantId cho một hashed value |
| “Balancer tự cân bằng CPU/QPS tuyệt đối” | Balancer chủ yếu xử lý placement/ranges |
| “Shard key chọn sai có thể đổi miễn phí” | Resharding tiêu tốn tài nguyên và có preconditions |
| “Có `tenantId` là đã sharding” | Có thể chỉ là business partition logic |
| “Unique index trên sharded collection như replica set thường” | Có shard-key prefix/uniqueness constraints |
| “Primary shard là primary member của replica set” | Hai khái niệm ở cấp khác nhau |
| “Đặt `$match` tốt là mọi aggregation chỉ một shard” | Cần filter phù hợp shard key và query plan |
| “Snapshot mỗi shard tùy thời điểm là backup nhất quán” | Cần backup cluster-wide có phối hợp |
| “Có replicas là khỏi cần backup” | Xóa nhầm và lỗi logic cũng được replicate |
| “TCO chỉ là tiền của các shard nodes” | Còn CSRS, router, network, DR, operations |
| “Chỉ benchmark insert/s là đủ” | Phải đo p99, global queries, balancing, failover |
| “Sharding hoàn tất thì không cần theo dõi” | Skew và workload thay đổi theo thời gian |

## 23. Bài tập thực hành

### Bài 1 — Chọn phương án mở rộng

Một ứng dụng cần: (a) chịu lỗi một server; (b) giảm query p99 do COLLSCAN; (c) mở rộng storage logic vượt node; (d) archive dữ liệu theo năm. Chọn replication, indexing, sharding hoặc business partitioning làm ưu tiên cho từng mục và giải thích.

### Bài 2 — Tính capacity 18 tháng

Dữ liệu + index = 1,20 TB; tăng 80 GB/tháng; horizon 18 tháng; mục tiêu 0,80 TB/shard; safety factor 25%. Tính số shard sơ bộ và sau safety factor.

**Đáp án:** 2,64 TB dự báo; 4 shards sơ bộ; 5 shards sau dự phòng.

### Bài 3 — Storage replication

Với 5 shards và 3 data-bearing members/shard, có bao nhiêu data-bearing members? Với dataset logic data + index 2,64 TB, tổng bytes của ba bản sao là bao nhiêu nếu bỏ qua overhead?

**Đáp án:** 15 members; 7,92 TB dữ liệu + index bản sao.

### Bài 4 — Hot shard

Ba shards nhận lần lượt 15.000/2.000/1.000 writes/s. Vì sao tổng throughput danh nghĩa đủ nhưng p99 vẫn có thể xấu?

**Đáp án:** Một shard nóng trở thành bottleneck; cần xem shard-key skew, phân bố workload và capacity.

### Bài 5 — Query targeting

Shard key `{tenantId:1,orderId:1}`. So sánh routing của:

~~~javascript
db.orders.findOne({ tenantId: "A", orderId: "A-001" });
db.orders.find({ tenantId: "A" });
db.orders.find({ status: "PAID" });
~~~

**Đáp án:** Full key thường target hẹp nhất; tenant-only có thể nhiều shards; status-only thường scatter-gather.

### Bài 6 — Kiểm chứng index trước shard

Chạy explain trên `lab.orders` với `tenantId="A"`, `status="PAID"` và sort theo `createdAt`. Index nào đã được tạo cho query này? Vì sao cần kiểm tra query plan trước khi shard?

### Bài 7 — Phân bố tenant

Fixture có A=8, B=4, C=3, D=1 document. Tính tỷ lệ và giải thích vì sao không thể dùng tỷ lệ này làm write QPS distribution.

**Đáp án:** 50%, 25%, 18,75%, 6,25%; số document tồn tại không đo tốc độ ghi mới.

### Bài 8 — Báo cáo PAID

Tính số đơn PAID/tổng giá trị theo tenant. Đối chiếu kết quả:

~~~text
A: 6 đơn, 1.100
B: 3 đơn,   400
C: 2 đơn,   130
D: 1 đơn,   700
Tổng: 12 đơn, 2.330
~~~

Nếu aggregation phải tổng hợp toàn cluster, cần những thao tác merge nào giữa shards?

### Bài 9 — Chi phí process

So sánh replica set 3 members với ba shards × ba members + CSRS ba members + hai routers.

**Đáp án:** 3 `mongod` so với 9 + 3 = 12 `mongod` và 2 `mongos`, tổng 14 processes ở phương án minh họa.

### Bài 10 — Unique email toàn cục

Sharded collection theo `tenantId`, nhưng email phải duy nhất toàn ứng dụng. Vì sao index unique trên `{tenantId:1,emailKey:1}` chưa đáp ứng? Đề xuất registry hoặc thiết kế shard key khác.

### Bài 11 — Backup/restore

Tại sao snapshot bốn shards ở bốn thời điểm khác nhau không tự tạo một cluster-wide consistent backup? Nêu các yêu cầu RPO/RTO và metadata.

### Bài 12 — Transaction xuyên shard

Một chuyển tiền cập nhật hai accounts ở hai shards. Khi nào cần distributed transaction? Nêu ít nhất ba chi phí so với hai writes độc lập.

### Bài 13 — Zone và tuân thủ

Dữ liệu EU phải ở EU. Một zone range đã được cấu hình thì đã đủ chưa? Liệt kê replica placement, backup, logs và exports cần kiểm tra.

### Bài 14 — Quyết định với hot tenant

Một tenant chiếm 92% writes và cần SLA riêng. So sánh compound shard key trong shared cluster với dedicated cluster. Ưu/nhược về isolation, chi phí và routing?

### Bài 15 — Benchmark plan

Thiết kế benchmark so sánh một replica set đã tối ưu và một sharded cluster candidate. Phải bao gồm targeted read, global aggregation, hot tenant writes, balancing, failover và p99/error rate.

### Bài 16 — Quyết định GO/NO-GO

Lập bảng G1–G6 cho một hệ thống giả định: bottleneck, alternatives, shard key distribution, query mix, unique/transaction constraints, TCO, runbook và DR. Kết luận **chưa shard**, **chuẩn bị shard** hoặc **nên shard** bằng bằng chứng định lượng.

## 24. Tổng kết

Sharding hữu ích khi cần **scale-out dung lượng và workload** vượt giới hạn kinh tế/kỹ thuật của một shard. Nó chỉ mang lại hiệu quả tốt khi shard key phân phối dữ liệu và tải, các query có thể được target hợp lý và hệ thống có năng lực quản trị cluster.

Mười nguyên tắc:

1. Đo bottleneck và SLO trước khi shard.
2. Tối ưu index/schema/cache/scale-up trước khi tăng độ phức tạp.
3. Dự báo growth và capacity với headroom rõ ràng.
4. Đánh giá shard-key cardinality, frequency, monotonicity và skew.
5. Đo cả targeted queries lẫn scatter-gather/global aggregations.
6. Không kỳ vọng throughput tăng tuyến tính theo số shards.
7. Giữ replication/backup: sharding không thay HA hay disaster recovery.
8. Tính TCO đầy đủ: shard members, CSRS, routers, balancing, network, monitoring và on-call.
9. Kiểm tra unique constraints, consistency, transactions và migration plan.
10. Dùng benchmark có workload thật, p95/p99 và failure scenarios để quyết định.

**Không sharding khi chưa cần cũng là một quyết định đúng**. Khi đã có bằng chứng scale-out và vận hành sẵn sàng, sharding mở rộng khả năng phát triển của MongoDB, với chi phí quản trị phải được chấp nhận và duy trì lâu dài.

### Tài liệu MongoDB chính thức

- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — khái niệm, thành phần cluster và phân phối dữ liệu.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shard replica sets, `mongos`, config servers.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — những yếu tố đánh giá shard key.
- [Shard Key Cardinality](https://www.mongodb.com/docs/manual/core/shard-key-cardinality/) — phân biệt số giá trị shard key.
- [Shard Key Frequency](https://www.mongodb.com/docs/manual/core/shard-key-frequency/) — tần suất khóa và hotspots.
- [Shard Key Monotonicity](https://www.mongodb.com/docs/manual/core/shard-key-monotonic/) — tăng tuần tự và write distribution.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — range query và placement.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hash distribution và trade-offs.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — chunk/range distribution.
- [Balancer Administration](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — balancing và migration.
- [Resharding](https://www.mongodb.com/docs/manual/core/resharding/) — thay shard key trong điều kiện được hỗ trợ.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — placement theo vùng khóa.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — unique index và shard key.
- [Replication](https://www.mongodb.com/docs/manual/replication/) — replica set và failover.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — giao dịch nhiều document/shard.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — phân tích query plan.
- [collStats Command](https://www.mongodb.com/docs/manual/reference/command/collStats/) — thống kê storage/index.
