# Chi phí chỉ mục, sao chép, mức nhất quán và giao dịch

Một hệ **Database No SQL** có thể đọc rất nhanh với vài chỉ mục, chịu được lỗi node nhờ replication, cho phép read mạnh hơn hoặc commit nhiều document trong một giao dịch. Tuy nhiên, các khả năng đó **không miễn phí**. Mỗi chỉ mục bổ sung có thể làm tăng lượng dữ liệu phải cập nhật; mỗi bản sao làm tăng sử dụng ổ đĩa và lưu lượng đồng bộ; mức nhất quán chặt có thể buộc request chờ thêm node hoặc từ chối khi mất quorum; giao dịch dài làm tăng contention, thời gian giữ tài nguyên và chi phí retry.

Khi đo tải, câu hỏi đúng không phải “bật càng nhiều tính năng càng tốt?” mà là:

> Với một workload và một hợp đồng đúng đắn cụ thể, **bộ cấu hình nào đáp ứng SLO với chi phí, khả năng chịu lỗi và độ phức tạp chấp nhận được?**

Bài học thuộc chương **Hiệu năng và đo tải** trong **Database No SQL**. Chúng ta sẽ phân tích bốn nhóm chi phí — **chỉ mục, sao chép, mức nhất quán, giao dịch** — và đặc biệt là **tác động kết hợp** giữa chúng. Ví dụ được đặt trong bối cảnh Java backend dùng MongoDB, Cassandra, DynamoDB hoặc Redis, với mô hình đo p95/p99, throughput, tài nguyên, conflict, replication lag và độ chính xác của kết quả.

Mọi con số trong bài là **minh họa thiết kế hoặc dữ liệu giả định của benchmark**, không phải đặc tả hiệu năng cố định của bất kỳ nhà cung cấp hay phiên bản nào. Muốn kết luận về một hệ thực tế phải đo trên topology, driver, dữ liệu và access pattern tương ứng.

## 1. “Chi phí” bao gồm những gì?

Không nên quy mọi thứ thành số mili giây trung bình. Một thay đổi cấu hình có thể ảnh hưởng nhiều chiều:

| Chiều chi phí | Ví dụ đo | Hệ quả |
|---|---|---|
| **Read latency** | p50, p95, p99 GET/query | Trải nghiệm đọc |
| **Write latency** | p95/p99 update, commit | Trải nghiệm ghi |
| **Throughput** | Ops/s với error rate cho phép | Khả năng phục vụ tải |
| **CPU** | CPU của primary/replicas, compaction | Độ bão hòa |
| **Memory** | Index cache, buffer, heap, allocator | Headroom/OOM |
| **Storage** | Data, index, oplog/WAL, snapshots | Dung lượng và tiền |
| **Disk I/O** | IOPS, throughput, queue length | Tắc nghẽn đọc/ghi |
| **Network** | Cross-AZ/region bytes, RTT | Chi phí và latency |
| **Availability** | Thời gian không có quorum/leader | SLO sẵn sàng |
| **Freshness** | Replication lag, read staleness | Chất lượng dữ liệu |
| **Correctness** | Lost update, overselling, anomaly | Bất biến nghiệp vụ |
| **Operational cost** | Backup, reindex, repair, migration | Công sức vận hành |
| **Monetary cost** | DB instance/RCU/WCU/bytes/egress | Ngân sách |

Một phương án có thể tăng write latency 20% nhưng loại bỏ nguy cơ overselling. Không thể gọi đó là thất bại nếu bất biến nghiệp vụ là yêu cầu bắt buộc.

## 2. Hiệu năng luôn đi cùng hợp đồng nhất quán

So sánh:

~~~text
Candidate A:
  read từ replica bất kỳ
  acknowledgment nhanh
  ít giao dịch
  15 ms p99

Candidate B:
  đọc theo consistency contract chặt hơn
  đợi đủ acknowledgment
  transaction bảo vệ nhiều writes
  40 ms p99
~~~

Không thể kết luận A “tốt hơn” chỉ từ p99. Nếu A cho phép khách thấy dữ liệu cũ hoặc commit sai trạng thái, hai hệ **không giải cùng bài toán**.

Cần viết trước:

- Dữ liệu có thể stale tối đa bao lâu?
- Ghi thành công nghĩa là đã được xác nhận ở những bản sao nào?
- Một operation có cần atomic trên một hay nhiều items?
- Có cho phép read-your-writes không?
- Khi network partition xảy ra, ưu tiên chờ/từ chối hay phục vụ dữ liệu cũ?
- Những lỗi nào bắt buộc phải ngăn chặn: duplicate, lost update, write skew, overselling?

**Benchmark chỉ công bằng nếu các cấu hình đáp ứng cùng bộ yêu cầu bắt buộc.**

## 3. Bốn nhóm tính năng trong một sơ đồ

~~~mermaid
flowchart TD
    Java["Java API / driver"] --> Query["Query planner / write coordinator"]
    Query --> Index["Index structures"]
    Query --> Tx["Transaction / concurrency control"]
    Tx --> Primary["Authoritative data state"]
    Primary --> Replica["Replication / log propagation"]
    Query --> Consistency["Read/write consistency policy"]
    Consistency --> Replica
    Index --> Storage["CPU / RAM / Disk IO"]
    Tx --> Storage
    Replica --> Network["Network / extra storage"]
    Consistency --> Latency["Wait / retries / unavailable"]
~~~

Các thành phần tương tác:

- Một transaction cập nhật ba documents phải duy trì indexes của cả ba.
- Replication phải lan truyền những mutation/transaction-log records theo giao thức.
- Một consistency level yêu cầu nhiều replica phản hồi có thể tăng thời gian chờ.
- Một transaction bị conflict tạo thêm read/write attempts.
- Index build có thể cạnh tranh I/O với replication và queries.

Vì vậy không đo “giá của index” riêng rồi cộng cơ học với “giá của replication” để dự đoán mọi workload.

## 4. Baseline trước khi tối ưu

Một hệ muốn thay đổi chỉ mục hoặc mức nhất quán nên có baseline:

~~~text
Workload:
  80% read point lookup
  10% filtered search
  10% conditional write

Data:
  10 million documents
  average document 2 KiB
  key cardinality and skew recorded

Topology:
  3 replicas, one region, AZ placement documented

Contract:
  writes meet configured durable acknowledgment
  business updates do not overwrite newer versions
  read freshness policy documented

Measurements:
  p50/p95/p99, throughput, errors, retry counts
  CPU, memory, disk IO, network, replication lag
~~~

Nếu baseline chỉ gồm “QPS” mà không có read/write mix và data distribution, ta không biết bottleneck đến từ đâu.

## 5. Phân biệt throughput đạt được với offered load

**Offered load** là số request client cố gửi. **Achieved throughput** là số operation thành công hoặc được xử lý theo outcome được định nghĩa.

Ví dụ:

~~~text
Client offers 20,000 ops/s
Server completes 12,000 ops/s
3,000 ops/s timeout
5,000 ops/s queued or rejected
~~~

Không báo “cluster đạt 20.000 ops/s” chỉ vì tool load test gửi được 20.000 requests. Cần phân loại success, business rejection, throttling, failed transaction và timeout.

Một throughput cao nhờ bỏ qua lỗi hoặc bỏ rơi request **không phải cải thiện hiệu năng hữu ích**.

## 6. Little's Law giúp đọc số liệu tải

Trong trạng thái tương đối ổn định:

\[
L \approx \lambda W
\]

Trong đó:

- \(L\): số operation đang tồn tại trong hệ.
- \(\lambda\): tốc độ hoàn thành operation.
- \(W\): thời gian trung bình một operation ở trong hệ.

Ví dụ 2.000 requests/s với average end-to-end time 50 ms:

\[
L \approx 2000\times0.05=100
\]

Tức trung bình khoảng 100 requests in flight theo phạm vi đo.

Đây là một **quan hệ trung bình ở trạng thái ổn định**, không thay thế p99 analysis và không đúng khi dùng sai phạm vi arrival/completion hoặc hệ đang overload kéo dài.

## 7. Vì sao p99 quan trọng hơn trung bình khi có replication?

Một write phải chờ nhiều node sẽ bị ảnh hưởng bởi **straggler** trong tập node phản hồi. Dù mỗi node trung bình nhanh, một network pause, compaction hoặc GC có thể làm đuôi latency dài.

Ví dụ một write có ACK sau 5 ms phần lớn thời gian, nhưng 1% requests cần 200 ms do một replica chậm hoặc retry. Average có thể nhìn ổn trong khi p99 vi phạm SLO.

Không suy “replication factor 3 nghĩa latency x3”. Chi phí phụ thuộc **ACK semantics, topology, số node cần chờ, network RTT và contention**.

---

## 8. Chỉ mục: vì sao đọc nhanh hơn nhưng ghi tốn hơn?

Một index là cấu trúc phụ trợ giúp tìm document theo field hoặc predicate mà không scan toàn bộ dữ liệu.

Ví dụ MongoDB:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 }
);
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-17",
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(20);
~~~

Nếu access pattern phù hợp index, engine có thể giảm số document cần đọc/sort. Nhưng mỗi lần insert, delete hoặc đổi các indexed fields, hệ phải duy trì metadata index tương ứng.

## 9. Một index có những khoản chi phí nào?

| Nhóm | Khi nào phát sinh |
|---|---|
| Index entry storage | Mỗi key/document liên quan được index |
| Memory/cache footprint | Các page index nóng được giữ trong RAM |
| Write CPU | Encode/compare key, bảo trì cấu trúc |
| Write IO | Cập nhật page, WAL/log, LSM memtable/SSTables |
| Compaction/maintenance | Merge, split, cleanup, vacuum hoặc rebalancing tùy engine |
| Replication traffic | Indexed data hoặc log mutation được replay theo engine |
| Index creation/rebuild | Scan dữ liệu, sort/merge, xây index |
| Operational complexity | Monitoring, uniqueness, index migrations |
| Query planning | Chọn giữa nhiều candidate indexes |

**Không phải tất cả chi phí này tăng tuyến tính theo số index**. Một field được update không nằm trong index có thể gây lượng index maintenance khác với insert/delete hoặc đổi indexed key.

## 10. Mô hình write amplification

Giả sử một logical write ghi 2 KiB business data nhưng database phải:

~~~text
Append to transaction log
Update primary data structure
Update 3 secondary indexes
Replicate log / mutation
Flush and compact persisted structures
~~~

Có thể định nghĩa một chỉ số đo thực tế:

\[
WA_{\text{storage}}=
\frac{\text{physical bytes written to storage}}
{\text{logical user-data bytes written}}
\]

Và một dạng khác:

\[
WA_{\text{operation}}=
\frac{\text{internal write operations}}
{\text{business write requests}}
\]

Hai định nghĩa **không tương đương**. Mỗi engine có cơ chế đo khác nhau; không gán một hằng số như “mỗi index thêm đúng một lần ghi đĩa”.

## 11. Index làm tăng dung lượng trên các replicas

Giả sử data logical 100 GiB và secondary indexes 30 GiB trên mỗi bản sao. Với replication factor 3, một ước lượng rất thô:

\[
S_{\text{replicated}}\approx3\times(100+30)=390\text{ GiB}
\]

Chưa tính WAL/oplog, compaction headroom, filesystem overhead, snapshots, backups và buffer đặc thù. Đây là mô hình ước lượng **nếu mỗi replica lưu bộ dữ liệu và indexes tương đương**, không phải hóa đơn chính xác của mọi engine.

Một index mới 10 GiB/replica có thể khiến tổng footprint thêm xấp xỉ 30 GiB trước các phần phụ khác.

## 12. Chi phí index trong read-heavy workload

Nếu 95% requests đọc theo `tenantId,status,createdAt`, một compound index khớp query có thể giảm latency rất lớn. Việc tốn thêm RAM/IO ghi có thể hợp lý vì:

- Giảm collection scan.
- Giảm documents examined.
- Giảm sorting/temporary memory.
- Giảm disk random reads.
- Tăng throughput đọc trên cùng hardware.

Điều quan trọng là **tỷ lệ query được hưởng lợi** và mức giảm origin work, không phải số lượng indexes tối đa.

## 13. Chi phí index trong write-heavy workload

Với 80% insert/update, một index hiếm khi được query có thể tạo chi phí vô ích:

~~~text
10,000 writes/s
  -> maintain primary data
  -> update secondary index A
  -> update secondary index B
  -> update secondary index C
  -> replicate and persist
~~~

Nếu thêm index D mà chỉ 0,01% reads dùng đến, hệ có thể giảm write throughput, tăng disk usage và giảm cache hiệu quả.

Cần kiểm chứng index usage, query plans, write p95/p99 và background compaction/maintenance trước khi thêm hoặc gỡ index.

## 14. Index “ít dùng” chưa chắc vô ích

Một unique index có thể được dùng rất ít trong truy vấn nhưng bảo vệ **bất biến uniqueness**:

~~~javascript
db.usernames.createIndex(
  { tenantId: 1, normalizedUsername: 1 },
  { unique: true }
);
~~~

Gỡ index chỉ vì index usage counter thấp có thể tạo duplicate usernames.

Tương tự TTL index hoặc index phục vụ incident/admin queries có thể có **giá trị chức năng**, không chỉ hit trong query planner. Mỗi index phải có lý do thuộc một trong các nhóm **performance, correctness, lifecycle, operations**.

## 15. Compound index và thứ tự field

Hai indexes:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ createdAt: -1, tenantId: 1, status: 1 }
~~~

có thể có hiệu quả khác nhau cho query filter tenant và status rồi sort theo createdAt.

Trong thiết kế compound index, cần xét:

- Equality predicates.
- Range predicates.
- Sort order.
- Selectivity.
- Prefix usage.
- Index-covered projection.
- Multi-tenant access pattern.
- Query shape thực tế.

Không tạo mọi hoán vị field để “đảm bảo index luôn khớp”. Mỗi hoán vị có storage/write cost.

## 16. Covering index: tránh document fetch nhưng index có thể phình

Một query chỉ cần `tenantId,status,createdAt,orderId`. Nếu index chứa đủ field cần để trả kết quả theo semantics engine, query có thể tránh fetch toàn bộ document.

Lợi ích:

- Giảm random data-page reads.
- Giảm IO và p95 của read-heavy endpoint.

Chi phí:

- Index entry lớn.
- RAM nóng bị chiếm.
- Mọi update field liên quan có thể phải cập nhật index.
- Một số field kích thước lớn không đáng đưa vào index.

Đừng tối ưu query “covered” bằng cách đưa cả payload lớn vào index mà không đo memory, write throughput và read latency.

## 17. High-cardinality, low-cardinality và selectivity

Một index `status` với hai giá trị ACTIVE/INACTIVE có thể không giúp nhiều nếu query lấy 70% dataset; nhưng kết hợp `tenantId` và sort có thể hữu ích.

Ngược lại index theo `orderId` có độ phân biệt cao thường thuận cho point lookup.

**Cardinality không phải tiêu chí duy nhất**. Phải xem histogram/distribution, query predicates, size, plan, caching, data skew và phần dữ liệu thực tế được filter.

## 18. Multikey, inverted và vector indexes có chi phí khác

Không phải mọi index đều có “một entry cho một document”.

- Array/multikey index có thể tạo nhiều index entries.
- Full-text inverted index tạo postings theo token.
- Geospatial index dùng cấu trúc không gian.
- Vector ANN index có graph/quantization/training và memory/recall trade-offs.
- TTL/indexed expiration có background cleanup.
- Unique index còn thực hiện constraint checking.

Một document chứa hàng nghìn tags có thể làm index maintenance nặng hơn document có một scalar field. **Đo index entry count/size** nếu engine cung cấp, thay vì suy từ document count.

## 19. Index selectivity kém làm read vẫn chậm

Ví dụ:

~~~text
Data: 20 million orders
Query: status IN ["PENDING", "APPROVED"]
Result: 15 million documents
```

Một index trên status có thể không giúp đủ nếu engine vẫn phải fetch lượng dữ liệu rất lớn. Tối ưu có thể cần:

- Cursor pagination.
- Better predicate / tenant scoping.
- Read model khác cho access pattern.
- Compound index theo sort + filter.
- Query giới hạn fields.
- Avoid unbounded scans.
- Asynchronous analytics path.

**Có index** không đồng nghĩa query phải nhanh.

## 20. Index và hot write path

Một secondary index key có phân phối không đều, ví dụ mọi update chạy vào một timestamp range hoặc một partition nóng, có thể gây contention.

Chi phí không chỉ từ mỗi document update mà còn từ:

- Cùng index pages được sửa liên tục.
- Storage compaction backlog.
- Hot partition trong một index-backed datastore.
- Lock/latch contention.
- Large index scans cạnh tranh write IO.

Khi benchmark, cần mô phỏng **write key distribution thực**. Random uniform keys có thể che hot-key behavior của production.

## 21. Index build là một tải riêng

Tạo index trên collection lớn có thể phải:

~~~text
Read existing dataset
Build/sort index entries
Write index pages/SSTables
Catch up concurrent writes
Update catalog metadata
```

Tùy engine/version/deployment, index build có thể online hoặc có các giai đoạn làm tăng resource/lock pressure. Cần:

- Thử trên staging dữ liệu gần thực.
- Dự trù disk/temporary space.
- Giới hạn load và quan sát replication lag.
- Xác định rollback/drop index path.
- Đo p95/p99 trong suốt build, không chỉ sau build.
- Không giả định từng thành viên cluster build đồng thời cùng thời gian.

## 22. Drop index cũng có rủi ro

Gỡ index có thể cải thiện write path và tiết kiệm storage, nhưng làm read query đổi plan, phát sinh scan/sort và tăng tail latency. Nếu index hỗ trợ unique/TTL contract, gỡ còn đổi correctness/lifecycle.

Để thử:

1. Lập danh sách queries/index usage theo thời gian đủ dài.
2. Xác định chức năng constraint/index.
3. Dự đoán fallback query plan.
4. Test load mix trước/sau.
5. Canary nếu engine cho phép.
6. Theo dõi p99, CPU/IO và errors.
7. Có kế hoạch xây lại index nếu cần.

## 23. MongoDB: dùng explain để so index

Ví dụ shell:

~~~javascript
db.orders.find({
  tenantId: "t-17",
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");
~~~

Những tín hiệu thường hữu ích:

- Winning plan, index scan so với collection scan.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- Execution time estimate/stats theo API.
- Stages có sort/fetch.
- Số shards được nhắm tới trong cluster sharded.

Không chỉ nhìn một giá trị executionTimeMillis từ lần chạy có cache ấm rồi coi đó là p99 production. `explain` giúp hiểu plan; **load test** mới đo contention và tail latency.

## 24. Java và MongoDB index definitions

Ví dụ Java sync driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

public void ensureOrderReadIndex(
        MongoCollection<Document> orders) {

    orders.createIndex(
        new Document("tenantId", 1)
            .append("status", 1)
            .append("createdAt", -1)
    );
}
~~~

Đoạn code minh họa API tạo index, nhưng không khuyến nghị gọi `createIndex` cho từng HTTP request. Nên quản lý schema/index migration có kiểm soát khi deploy.

Khi dùng `createIndex` cần xét index options, collation và shard key nếu có unique requirement. Chỉ thay annotation trong code mà không triển khai migration trên production có thể không tạo kết quả như mong muốn.

## 25. DynamoDB GSI cũng có giá đọc và ghi

DynamoDB Global Secondary Index (GSI) phục vụ access pattern theo key khác base table. Một write vào base table có thể dẫn tới cập nhật GSI tương ứng, làm tăng:

- Index storage.
- Write capacity/consumption.
- Propagation work và throttling risk.
- Chi phí vận hành theo billing mode.
- Eventual consistency lag của GSI.

Một query GSI **không hỗ trợ strongly consistent reads** như base table trong những API scope tương ứng. Không thêm GSI chỉ vì muốn query bằng mọi field; chọn partition/sort keys theo access patterns và chi phí duy trì.

## 26. Cassandra index không giống MongoDB index

Cassandra và những hệ LSM/distributed wide-column có kiến trúc truy vấn khác. Secondary indexing, materialized views, search integration hoặc giải pháp SAI tùy phiên bản có performance/consistency/maintenance semantics riêng.

Trong Cassandra, thiết kế table thường bắt đầu từ:

- Partition key.
- Clustering columns.
- Query predicates.
- Partition size và data locality.
- Replication topology.
- Write/read consistency.

Không bê nguyên “thêm index trên mọi field” từ MongoDB vào một bảng Cassandra rồi kỳ vọng throughput tương đương.

## 27. Index cost không chỉ xuất hiện trên write thành công

Một update có thể:

- Kiểm constraint trước khi ghi.
- Chạm structures/indexes.
- Bị conflict hoặc abort.
- Tạo WAL/temporary work tùy engine.
- Được retry.

Do đó khi transaction conflict tăng, **chi phí index cũng có thể bị lặp ở nhiều attempts**, dù business-level successful write QPS không tăng. Đo `DB writes attempted` và `business writes committed` riêng.

---

## 28. Sao chép: mục tiêu và giá phải trả

**Replication** duy trì nhiều bản dữ liệu hoặc log trên các nodes/regions để tăng khả năng phục hồi và phục vụ read. Nó có thể giúp:

- Chịu hỏng node/ổ đĩa.
- Failover sang leader/primary mới.
- Phục vụ read ở nhiều locations theo consistency policy.
- Bảo đảm một số mức acknowledgment/durability.

Chi phí thường gồm:

- Nhiều bản lưu dữ liệu và indexes.
- Traffic truyền mutation/log.
- CPU để replay/index/compaction.
- Network round trips hoặc chờ ACK.
- Monitoring, repair, rebalancing, snapshots.
- Consistency/conflict management.

**Replication không tự thay backup/PITR**: xóa logic hoặc corruption có thể được sao chép tới mọi replica.

## 29. Replication factor và dung lượng

Gọi:

- \(D\): logical data + indexes trên một replica theo mô hình đơn giản.
- \(RF\): số replica lưu bản tương đương.

Ước lượng thô:

\[
S_{\text{cluster}}\approx RF\times D
\]

Nếu mỗi replica dùng 130 GiB và RF=3:

\[
S_{\text{cluster}}\approx390\text{ GiB}
\]

Chưa tính log, compaction, snapshots, backups, metadata, spare capacity và cách sharding/RF được phân phối.

Trong một cluster sharded, không nhất thiết **mỗi node** giữ toàn dataset; RF thường áp lên **mỗi shard/partition**. Không nhầm `3 nodes` với `RF=3` trong mọi topology.

## 30. Replication network amplification

Ví dụ nguồn nhận 1.000 logical updates/s, mỗi update chứa 2 KiB payload nghiệp vụ:

\[
B_{\text{logical}}=1000\times2\text{ KiB/s}\approx1.95\text{ MiB/s}
\]

Nếu dữ liệu này cần lan sang hai replicas khác, lượng payload sao chép tối thiểu theo mô hình giả định xấp xỉ gấp đôi phần payload đó, chưa tính headers, logs, batching, compression, retries hoặc engine-specific encoding.

Không nên nói “RF=3 luôn tốn đúng 3 lần network bytes”. Trong leader-replica replication, primary có thể gửi tới hai followers; trong hệ gossip/anti-entropy, đường truyền khác. **Phải đo actual inter-node traffic**.

## 31. Synchronous và asynchronous replication

Hai khái niệm dễ bị gộp:

- **Synchronous acknowledgment path:** request success có thể phải chờ nhiều replica hoặc một commit quorum.
- **Asynchronous propagation:** leader có thể phản hồi trước khi các followers bắt kịp.

Cả hai có thể cùng tồn tại trong một hệ tùy policy ACK, write concern và background replication. Một leader ACK nhanh **không tự** cho phép khẳng định mọi bản sao đã durable.

## 32. Quorum trong mô hình lý tưởng

Với \(N\) replicas, nếu mỗi write được chấp nhận bởi \(W\) replicas và read hỏi \(R\) replicas, điều kiện:

\[
R+W>N
\]

giúp các tập read/write **giao nhau ít nhất một replica** trong một mô hình lý tưởng.

Ví dụ \(N=3, W=2, R=2\):

\[
2+2>3
\]

Nhưng đây **chỉ là điều kiện giao tập**, không phải phép chứng minh mọi hệ thực tế đều linearizable: còn cần version ordering, conflict resolution, read repair, failure model, coordinator protocol, stale replicas, hinted handoff và semantics cụ thể của engine.

Không áp máy móc công thức này cho MongoDB read/write concerns, DynamoDB, Redis, hoặc mọi chế độ Cassandra rồi khẳng định strong consistency.

## 33. RF không trực tiếp cho biết acknowledgment policy

Hai cluster cùng RF=3 có thể cấu hình khác:

~~~text
Cluster A:
  RF=3
  write ACK from local/leader only

Cluster B:
  RF=3
  write ACK after an eligible quorum
~~~

Dung lượng cơ sở có thể tương tự, nhưng:

- Latency write ACK khác.
- Hành vi khi một replica lỗi khác.
- Rủi ro mất acknowledged writes khi failover khác.
- Availability khi không đủ eligible replicas khác.

Vì vậy benchmark cần ghi **cả RF lẫn consistency/ack policy**.

## 34. Replication lag là chi phí của sự không đồng bộ

Một follower có thể trễ so với source:

~~~text
Primary committed version=1000
Secondary applied version=995
Lag=5 versions, hoặc theo thời gian/bytes nếu đo được
~~~

Lag lớn có thể do:

- Network congestion.
- Disk/CPU bottleneck ở follower.
- Large writes/transactions.
- Compaction hoặc index build.
- Snapshot/initial sync.
- Throttle/load imbalance.
- WAN latency hoặc partition.

Không chỉ đo p99 write trên primary. Nếu ứng dụng đọc từ follower, **freshness** cũng là một kết quả quan trọng.

## 35. Lag theo thời gian và theo số bản ghi khác nhau

Hai cách đo:

- `appliedThroughVersion` hoặc log position difference.
- `timeSinceSourceCommit` hoặc replay delay.

Nếu workload ngưng ghi, “5 events behind” có thể là hàng phút; khi workload tăng mạnh, 1.000 events behind có thể chỉ vài giây. Timestamp đo lag cũng có clock-skew và source/target semantics.

Cần biết metric phản ánh **what exactly has been applied** ở từng node, không gộp các con số khác loại.

## 36. Replication trong multi-region

Cross-region replication còn thêm:

- WAN RTT.
- Bandwidth/egress cost.
- Data residency constraints.
- Region outage behavior.
- Concurrent writes/conflict policy.
- Read locality versus staleness.
- CDC backlog và retention risk.

Một cấu hình “reads gần user, writes sang region chính” có thể nhanh cho read nhưng tăng write latency và làm read-your-writes phức tạp.

**Chọn region gần nhất không tự là cách đạt causal consistency**; phải có session/version hoặc cơ chế phù hợp.

## 37. Availability chịu tác động bởi quorum

Nếu một operation cần ACK từ quorum mà network partition làm không đủ eligible replicas, hệ có thể trả unavailable/timeout dù vài nodes còn hoạt động.

Trong một số use case đây là quyết định đúng để tránh ghi vào trạng thái không đủ bằng chứng nhất quán. Không nên “tăng availability” bằng cách tự giảm consistency khi nghiệp vụ không cho phép.

Cần đo:

- Success rate dưới failure scenario.
- Failover time.
- Operation latency trong election.
- Unknown commit outcomes.
- Data staleness/loss risk.
- Khả năng recover/quorum restoration.

## 38. Một primary không phải một bản sao không có chi phí

MongoDB replica set có primary phục vụ write, secondary theo replication log. Nhưng secondary vẫn tiêu tốn:

- Storage data/index.
- CPU apply writes.
- Disk flush và maintenance.
- Replication buffers/network.
- Snapshot/backup overhead.
- Monitoring và connection management.

Thêm secondary có thể tăng read capacity **nếu read preference/consistency cho phép**, nhưng không tự tăng primary write capacity theo tỉ lệ số nodes.

## 39. Replication và index tương tác thế nào?

Một write thay field indexed có thể khiến:

~~~text
Primary:
  update data + indexes
  append change/log

Replica:
  receive relevant log/mutation
  apply data changes
  maintain equivalent index structures
~~~

Tùy engine, replication có thể chuyển logical operations/log records thay vì gửi full index pages. Vì vậy index write amplification trên mỗi replica không đồng nghĩa replication payload cũng tăng bằng đúng số index entries.

Khi benchmark index cost trên replicated cluster, đo **primary write work** và **secondary apply/lag** riêng.

## 40. Replication không xóa hot partition

Nếu 90% writes tới một logical key hoặc partition, RF=3 không tự chia những cập nhật ấy thành ba independent owners có thể commit tùy ý.

Các writes vẫn cần tuân theo concurrency/ordering protocol; có thể phát sinh:

- Hot leader/coordinator.
- CAS conflicts.
- Serialization bottleneck.
- Compaction pressure.
- Replica catch-up lag.

Giải pháp có thể là thiết kế aggregate, sharding key, batching hoặc command queue theo domain — không đơn giản chỉ tăng RF.

---

## 41. Mức nhất quán là một quyết định về thời điểm được đọc/ghi

Các lựa chọn có thể ưu tiên:

- Read nhanh từ một bản sao.
- Read có khả năng nhìn thấy write vừa commit.
- Read theo phiên có causal order.
- Read theo snapshot nhất quán.
- Read từ quorum hoặc leader.
- Read từ dữ liệu stale nhưng trong giới hạn.
- Từ chối thao tác nếu điều kiện bảo đảm không đạt.

Không thể sắp một thứ tự đơn giản “eventual < quorum < linearizable” áp cho tất cả API/engines mà bỏ qua semantics riêng. **Từ ngữ giống nhau không luôn là guarantee giống nhau**.

## 42. Độ trễ đọc theo số replica được chờ

Trong mô hình lý tưởng:

~~~text
Read from 1 healthy local replica:
    one path

Read requiring 2 confirmations:
    coordinator contacts replicas,
    waits for required results,
    resolves versions as protocol defines
~~~

Đường chờ có thể dài hơn do network/straggler, nhưng đôi khi parallelism/read repair/cache làm hiệu năng khác dự đoán. Không gắn một hệ số cứng như “QUORUM read luôn chậm gấp đôi ONE read”.

Benchmark phải đo **latency distributions và error rates**, dưới cả healthy và degraded topology.

## 43. Eventual read đổi lấy gì?

Một read có thể lấy dữ liệu từ replica/local projection chưa bắt kịp:

**Lợi ích có thể có:**

- Giảm latency và WAN traffic.
- Tăng số nodes phục vụ đọc.
- Hỗ trợ availability khi một vùng bị cô lập.
- Giảm tải leader.

**Giới hạn:**

- Đọc trạng thái cũ.
- Read-your-writes có thể không đạt.
- Có thể thấy version đi lùi giữa hai requests nếu không dùng session/monotonic semantics.
- Quyết định nghiệp vụ sai nếu cache/follower được dùng làm authority.

Đọc eventual hợp lý cho nhiều màn hình discovery, nhưng không dùng duy nhất để bảo vệ quota hay chuyển tiền.

## 44. Strong read không có nghĩa mọi thao tác còn lại an toàn

Một read mạnh hơn có thể bảo đảm nhìn thấy một trạng thái theo contract, nhưng nếu sau read ứng dụng ghi ở lệnh khác không có điều kiện, state có thể đổi giữa hai bước.

~~~text
Read available=1
Another request reserves 1
Write available=0 based on old read
```

Để tránh lost update/overselling cần **atomic conditional write/transaction**, không chỉ tăng read consistency.

**Freshness của read và atomicity của update là hai trục độc lập.**

## 45. Causal/session consistency phục vụ read-your-writes

Nếu user update profile rồi ngay lập tức đọc lại, hệ có thể cần:

- Session token/version.
- Primary/local writer read path.
- Causal session với read/write concerns phù hợp.
- Wait for projection to reach source version.
- Return write result directly.

Causal consistency có thể đòi theo dõi metadata và route/chờ đủ mốc. Chi phí gồm **routing constraints, waiting và read path ít lựa chọn hơn**, nhưng giúp UX không nhìn thấy cập nhật của mình bị mất tạm thời.

## 46. MongoDB: ba cấu hình không được nhầm

| Thành phần | Trả lời |
|---|---|
| `readPreference` | Driver đọc từ loại server nào? |
| `readConcern` | Dữ liệu được đọc với semantics gì? |
| `writeConcern` | Khi nào write được acknowledge và ở mức nào? |

Ví dụ `readPreference=secondary` không tự bảo đảm read-your-writes; `writeConcern=majority` không biến mọi query thiếu read concern thích hợp thành linearizable; `readConcern=snapshot` chỉ có ý nghĩa trong phạm vi hỗ trợ.

Các lựa chọn cụ thể phụ thuộc MongoDB server/driver version và topology; không suy từ một option sang mọi consistency guarantee.

## 47. Java MongoDB: cấu hình read/write concerns

Ví dụ Java Sync Driver:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class OrderReads {
    private final MongoCollection<Document> orders;

    public OrderReads(MongoClient client) {
        this.orders = client.getDatabase("shop")
            .getCollection("orders")
            .withReadPreference(ReadPreference.primary())
            .withReadConcern(ReadConcern.MAJORITY)
            .withWriteConcern(WriteConcern.MAJORITY);
    }

    public Document get(String id) {
        return orders.find(new Document("_id", id)).first();
    }
}
~~~

Đây là minh họa cấu hình API chứ không phải khẳng định `MAJORITY` đáp ứng mọi nghiệp vụ linearizable. Nên đặt policy theo use case/operation; đo p99 và đánh giá read-your-writes/visibility trong các tình huống failover.

## 48. MongoDB: majority không luôn đồng nghĩa read linearizable

Các khái niệm cần tách:

- Majority acknowledgment nhằm bảo vệ những đặc tính durability/rollback theo contract.
- Majority read concern có visibility semantics riêng.
- Linearizable read concern (trong những điều kiện hỗ trợ) có yêu cầu và chi phí khác.
- Snapshot reads phục vụ một tập đọc nhất quán trong scope.
- Read preference và session placement cũng ảnh hưởng đường đi.

Không lấy read từ secondary với majority read concern rồi mặc định nó là real-time linearizable read sau mọi write đồng thời.

## 49. Cassandra: LOCAL_ONE và LOCAL_QUORUM

Trong một cluster Cassandra có replication theo datacenter, consistency level như `LOCAL_ONE` và `LOCAL_QUORUM` có thể tạo trade-off khác nhau:

- `LOCAL_ONE` chờ một replica phù hợp local DC.
- `LOCAL_QUORUM` đòi đủ quorum replicas trong local DC theo replication strategy.
- Mức yêu cầu cao hơn có thể tăng latency và giảm availability trong failure.
- Read repair/repair/anti-entropy và conflict resolution vẫn cần hiểu.

Không suy từ công thức `R+W>RF` rằng mọi cấu hình Cassandra đều tuyến tính hóa mọi thao tác. Cassandra có last-write-wins/timestamp/conflict semantics và các giới hạn riêng.

## 50. Java Cassandra: consistency theo statement

Ví dụ Java Driver 4.x-style:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class ProductQuery {
    private final CqlSession session;
    private final PreparedStatement select;

    public ProductQuery(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT name, status FROM product_by_tenant "
          + "WHERE tenant_id=? AND product_id=?"
        );
    }

    public void query(String tenantId, String productId) {
        BoundStatement statement = select.bind(tenantId, productId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(statement);
    }
}
~~~

Code chỉ minh họa API consistency level; bảng phải được thiết kế đúng partition key và local datacenter phải khớp topology. Cần đo coordinator/replica response, timeout, consistency errors và dữ liệu stale dưới các failure scenarios.

## 51. DynamoDB: strong vs eventually consistent reads

Trong những API được hỗ trợ, DynamoDB cho phép chọn `ConsistentRead=true` cho một số đọc trên base tables/LSIs; GSI không hỗ trợ strong read theo cách đó.

Lựa chọn có thể tác động:

- Read capacity tiêu thụ.
- Query latency.
- Khả năng nhìn thấy update mới.
- Throttle/cost theo billing.
- Đường đọc ở region cụ thể.

Không dùng một GSI eventual result làm kiểm tra duy nhất trước khi cập nhật một invariant quan trọng; dùng conditional writes/transaction trên authoritative items.

## 52. Java AWS SDK v2: consistent read

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import java.util.Map;

public void readStronglyWhenSupported(DynamoDbClient client) {
    GetItemRequest request = GetItemRequest.builder()
        .tableName("Inventory")
        .key(Map.of(
            "pk", AttributeValue.fromS("SKU#A"),
            "sk", AttributeValue.fromS("STATE")
        ))
        .consistentRead(true)
        .build();

    client.getItem(request);
}
~~~

Chỉ là ví dụ request trên table được giả định có composite primary key. Không chuyển `consistentRead(true)` nguyên xi sang GSI hoặc một cross-region replica rồi mặc định API hỗ trợ.

## 53. Redis: atomic primary execution không đồng nghĩa strong durability

Redis có thể thực thi một command/script nguyên tử trên primary, nhưng:

- Replication tới replicas thường có phần bất đồng bộ.
- AOF/RDB persistence có trade-off về độ bền và IO.
- Failover có thể ảnh hưởng observed writes.
- Các lệnh như `WAIT` có semantics chờ acknowledgment nhưng **không biến Redis thành một consensus DB tuyến tính hóa mọi giao dịch**.

Dùng Redis làm cache và dùng Redis làm source ledger là hai bài toán với yêu cầu rất khác nhau. Đừng dùng mức hit ratio hoặc RTT Redis để kết luận tính an toàn của nghiệp vụ.

## 54. Consistency làm thay đổi read routing

Nếu read có thể tới any local replica, driver có nhiều candidates. Nếu cần leader/primary, candidates ít hơn.

Ảnh hưởng tiềm năng:

- Leader CPU tăng.
- WAN read khi primary ở region khác.
- Giảm khả năng cân bằng read load.
- Tail latency tăng trong election.
- Read availability giảm khi leader unavailable.

Nên đo per-node/per-region distribution và **network hop count** thay vì chỉ nhìn endpoint-level p99.

## 55. Strong consistency không thay authorization

Một read dù linearizable vẫn có thể trả dữ liệu tenant khác nếu ứng dụng filter sai. Một transaction dù serializable vẫn có thể thực thi nghiệp vụ sai nếu policy kiểm quyền không đúng.

Performance benchmark cần có correctness assertions bên ngoài metrics latency. Không được “tối ưu” bằng cách bỏ tenant checks, unique constraints hay audit safeguards.

---

## 56. Giao dịch: để mua atomicity/isolation phải trả chi phí gì?

Một transaction nhiều document có thể cần:

- Bắt đầu session/transaction context.
- Chụp hoặc duy trì snapshot/MVCC state.
- Đọc các dependencies theo isolation.
- Giữ locks/intents hoặc validate versions.
- Quản lý undo/redo/log records.
- Phát hiện conflicts/deadlocks.
- Commit protocol/coordination.
- Replicate commit records.
- Retry toàn attempt khi bị abort.
- Dọn tài nguyên sau commit/abort.

Chính xác bước nào tồn tại tùy engine. Không suy rằng mọi NoSQL transaction đều dùng two-phase commit hoặc lock toàn bộ documents.

## 57. Transaction đơn document có thể tránh nhiều overhead

Nếu invariant chỉ là:

~~~text
available >= quantity
available := available - quantity
~~~

và dữ liệu nằm trong một document/item, atomic conditional update thường đơn giản hơn mở multi-document transaction.

MongoDB:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-17#sku-A",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
~~~

Khi filter không match, đó có thể là `SOLD_OUT` hoặc missing entity — không phải transient error cần retry vô hạn.

## 58. Optimistic concurrency có chi phí đọc lại và retry

Một document:

~~~json
{
  "_id": "order-100",
  "status": "PENDING",
  "version": 7
}
~~~

Update có filter version 7 và tăng version 8. Nếu writer khác đã thay state, update không match. Tính đúng được giữ, nhưng attempt thất bại đã tiêu tốn:

- Read trước đó.
- Network request.
- Version/condition validation.
- Possibly transaction work.
- Retry backoff.
- Re-read dependencies.

Khi hot-key contention tăng, throughput business success có thể giảm dù tổng DB requests tăng.

## 59. Retry amplification

Gọi:

- \(A\): tổng số attempts.
- \(C\): số business operations committed.
- \(Q\): tổng queries/read-write requests.

Có thể đo:

\[
\text{AttemptsPerCommit}=\frac{A}{C}
\]

\[
\text{DBRequestsPerCommit}=\frac{Q}{C}
\]

Nếu 10.000 business operations thành công tạo 15.000 attempts, hệ có trung bình 1,5 attempts/success. Nếu mỗi attempt đọc ba documents và ghi hai, load DB có thể khác rất xa QPS business mà dashboard báo.

Nên đo cả **rejected/failed business requests**, không bỏ chúng khỏi mẫu số đến mức làm số liệu đẹp giả.

## 60. Xác suất conflict phụ thuộc thời gian transaction mở

Trong một mô hình định tính:

~~~text
Transaction A:
  read inventory
  call payment gateway (200ms)
  write order
  commit
```

Một transaction giữ state/snapshot lâu làm tăng cơ hội writer khác thay dữ liệu liên quan. Payment call bên trong còn nguy hiểm vì callback có thể bị retry và tạo external side effect lặp.

Tốt hơn:

~~~text
Short DB transaction:
  validate state
  reserve inventory
  insert Order + Outbox
  commit

External workflow:
  process payment idempotently
  reconcile outcome
```

**Không đặt network I/O ngoài database vào callback transaction có thể chạy lại** nếu không có thiết kế chống lặp.

## 61. Snapshot isolation không tự là serializable

Ví dụ hai bác sĩ:

~~~text
A.onCall=true
B.onCall=true

T1 reads A and B; writes A=false
T2 reads A and B; writes B=false
~~~

Nếu engine dùng snapshot isolation và không có conflict chung/predicate protection, cả hai có thể commit làm số người trực bằng 0.

Vì vậy:

- **Transaction exists** không đủ để chứng minh invariant.
- Cần xác định isolation.
- Có thể đưa invariant về một owner/counter document cập nhật điều kiện.
- Hoặc dùng serializable protection khi engine hỗ trợ.
- Test concurrency/write skew thật.

Đo benchmark transaction nhanh nhưng sai invariant là **không hợp lệ**.

## 62. Phantom trong booking

Quy tắc: không cho hai booking cùng room overlap time interval.

~~~text
T1 query overlapping bookings -> none
T2 query overlapping bookings -> none
T1 inserts booking A
T2 inserts booking B
~~~

Nếu hai transactions không tạo write conflict/constraint và isolation không bảo vệ predicate, cả hai có thể thành công.

Có thể thiết kế:

- Unique occupancy slot keys.
- Shared owner/serializing record.
- Conditional reservation.
- Transaction với isolation thực bảo vệ predicate.
- Domain-specific conflict check có version/fencing.

Không xem `SELECT` trong transaction là đủ nếu engine có write skew.

## 63. Multi-document transaction khác multi-shard transaction

Một transaction chạm một shard/partition group có thể có chi phí khác transaction trải nhiều shards/nodes.

Với một số engine, cross-shard transaction cần thêm coordination, logs, commit protocol và network hops. Trong những engine không hỗ trợ arbitrary distributed transaction, code có thể phải dùng saga.

Các biến cần đo:

- Số documents/items.
- Số shards/partitions.
- Số reads/writes.
- Query selectivity.
- Transaction lifetime.
- Commit acknowledgment policy.
- Retry/conflict frequency.
- Distributed coordinator round trips.

Không lấy một benchmark update một document để dự báo chi phí tạo đơn hàng cần ba shards.

## 64. Two-phase commit là một mô hình, không phải công thức chung

Một số giao dịch phân tán dùng biến thể của two-phase commit:

~~~text
Coordinator:
  Prepare participating shards
  Collect votes
  Decide commit/abort
  Persist and propagate decision
```

Chi phí có thể là thêm network round trips, coordinator state và recovery work.

Nhưng:

- Không phải mọi engine/transaction đều dùng 2PC.
- Một hệ có thể dùng Paxos/consensus hoặc giao thức khác.
- Một transaction local không giống cross-shard transaction.
- Thời gian commit không tăng đúng một hằng số cho mọi workloads.

Hãy xem kiến trúc **engine và version thực** trước khi giải thích tail latency bằng 2PC.

## 65. Isolation level và contention trade-off

Trong một số workloads:

- Isolation chặt hơn loại bỏ anomalies quan trọng.
- Nhưng có thể phát sinh validation failures, serialization retries hoặc waiting.
- Transaction scope dài làm xấu tail latency.
- Fewer concurrent commits trên cùng hot aggregate.

Không tối ưu bằng cách hạ isolation nếu đó là lý do duy nhất invariant còn được giữ. Có thể **thay đổi data model** để giữ đúng invariant với một atomic single-document operation thay vì transaction rộng.

## 66. MongoDB Java: transaction callback

Ví dụ MongoDB Java Sync Driver, minh họa context:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public String reserveAndCreate(
        MongoClient client,
        MongoCollection<Document> stock,
        MongoCollection<Document> orders,
        String sku,
        String orderId) {

    TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .readPreference(ReadPreference.primary())
        .writeConcern(WriteConcern.MAJORITY)
        .build();

    try (ClientSession session = client.startSession()) {
        return session.withTransaction(() -> {
            var r = stock.updateOne(
                session,
                and(eq("_id", sku), gte("available", 1)),
                inc("available", -1)
            );

            if (r.getMatchedCount() != 1) {
                throw new IllegalStateException("SOLD_OUT");
            }

            orders.insertOne(session, new Document()
                .append("_id", orderId)
                .append("sku", sku));

            return orderId;
        }, options);
    }
}
~~~

Ví dụ **chưa phải checkout production**: chưa gồm idempotency, business error mapping, outbox, versioned price, concurrent duplicate request, driver exception categories và deadline. Cần deployment/driver MongoDB hỗ trợ transactions và error handling phù hợp.

Khi đo, so:

- Một conditional update đơn document.
- Transaction với hai documents.
- Transaction với các shards khác nhau nếu topology hỗ trợ.
- Tỷ lệ conflict với cùng key.
- P95/p99 và transaction abort/retry count.

## 67. DynamoDB TransactWriteItems có chi phí riêng

DynamoDB transactional APIs mang atomicity trong phạm vi API hỗ trợ, nhưng có:

- Transaction request/billing semantics khác non-transaction writes.
- Validation và condition checks.
- Item/action size/count limits.
- Transaction conflict/cancellation.
- Retry/idempotency token semantics.
- Capacity/throttling behavior.
- Region/account scope.

Không kết luận “transaction gấp đôi latency” mà không đo; cũng không coi multi-item transaction áp dụng xuyên Global Tables regions hoặc external services theo cùng guarantee.

## 68. Cassandra LWT: chi phí coordination

Cassandra Lightweight Transactions (LWT) dùng Paxos-style coordination cho conditional operations trong scope hỗ trợ. Nó có thể cần thêm trao đổi giữa các replicas so với write thường.

Ví dụ:

~~~sql
UPDATE inventory
SET available = ?, version = ?
WHERE tenant_id = ?
  AND sku = ?
IF version = ?;
~~~

LWT có thể đáng dùng để ngăn lost update, nhưng làm p95/p99 tăng khi contention hoặc network RTT lớn. Không dùng LWT trên mọi write nếu không có invariant yêu cầu conditional semantics.

Đồng thời, **một LWT không tự biến toàn bộ multi-partition workflow thành arbitrary serializable transaction**.

## 69. Redis MULTI và Lua không cùng nghĩa transaction ACID

Redis có thể thực thi một Lua script nguyên tử trong server và hỗ trợ MULTI/EXEC/WATCH với semantics riêng. Nhưng:

- Không mặc định có SQL-style rollback cho lỗi runtime trong MULTI.
- Atomic execution khác durable commit qua failover.
- Redis Cluster giới hạn multi-key operations theo hash slot.
- Watch conflicts dẫn tới retry/read lại.
- Long script chặn event loop và tăng latency mọi clients.

Benchmark Redis script p50 thấp không chứng minh nó có durability/isolation như một ledger DB.

## 70. Phân biệt retry commit với retry transaction body

Khi transaction abort do conflict, driver/ứng dụng có thể cần **mở attempt mới và đọc lại state**.

Khi commit response mất, transaction **có thể đã commit**. Lúc đó không replay body mù, vì có thể tạo Order hoặc external effect trùng.

Cần:

- Driver retry contract.
- Stable operation/idempotency ID.
- Unknown commit handling.
- Reconciliation của outcome.
- Separate transaction retry metrics và commit retry metrics.

Trong benchmark, phải đếm **commits cuối cùng đã xác định**, không xem timeout là chắc chắn rollback.

## 71. Transaction với secondary indexes: hiệu ứng kết hợp

Giả sử một transaction tạo ba documents, mỗi collection có bốn secondary indexes.

So với một conditional update một document, nó có thể:

- Tạo nhiều index entries.
- Ghi nhiều log records.
- Chạm nhiều shards.
- Đòi thêm replication acknowledgment.
- Giữ snapshot lâu hơn.
- Có thêm điểm conflict.
- Retry toàn bundle khi một write fail.

Các ảnh hưởng **có thể phi tuyến** khi đạt capacity/IO saturation. Không dùng phép cộng đơn giản “3 docs × 4 indexes = 12 lần chậm hơn” để dự đoán response latency.

---

## 72. Tác động kết hợp: một bảng quyết định

| Thay đổi | Read path | Write path | Resource/correctness |
|---|---|---|---|
| Thêm secondary index hữu ích | Có thể nhanh hơn | Maintenance tăng | Storage/RAM tăng |
| Thêm index không phục vụ query | Ít lợi ích | Có thể chậm hơn | Waste/compaction |
| Tăng RF | Có thể thêm read replicas | Replication work tăng | Durability/availability tùy policy |
| Chờ nhiều ACK hơn | Không nhất thiết đổi read | ACK latency có thể tăng | Durability/consistency contract khác |
| Read nhất quán chặt hơn | Có thể chờ lâu hơn/ít candidates | Không trực tiếp | Freshness/correctness cải thiện theo scope |
| Dùng conditional write | Tránh lost update | Condition check/conflict | Business invariant được bảo vệ |
| Thêm multi-item transaction | Có thể coherent snapshot | Coordination/retry tăng | Atomic multi-write |
| Thu nhỏ transaction scope | Ít snapshot/locks | Ít conflict | Phải giữ invariant đúng |
| Chuyển read sang cache/projection | Read có thể nhanh | Invalidation/indexing overhead | Freshness cần kiểm soát |

Bảng mô tả **xu hướng**, không phải định luật hiệu năng.

## 73. Tình huống: thêm index rồi tăng RF

Một hệ trước đó có 1 primary + 2 replicas và một index đơn giản. Nhóm thêm ba indexes để tối ưu dashboard.

Có thể quan sát:

~~~text
Primary write CPU increases
Secondary apply workload increases
Replication lag increases under peak writes
Write p99 rises
Dashboard queries become faster
```

Nếu chỉ benchmark dashboard query sau index, sẽ bỏ qua chi phí lên write pipeline và followers.

Cần đo đồng thời:

- Query p99 theo index.
- Write throughput/p99.
- Index size per replica.
- Replication lag.
- Disk/CPU utilization.
- Queue length và repair/compaction.

## 74. Tình huống: nâng consistency khi có index nặng

Một query yêu cầu read từ nhiều replicas hoặc leader theo guarantee mới. Nếu các replicas đang chạy index build, tail latency có thể bị chi phối bởi slow node.

Không suy từ read concern thay đổi đơn lẻ; cần quan sát:

- Selected server/replica latency.
- Index/cache warmness trên từng node.
- Compaction/index build progress.
- Cross-AZ RTT.
- Failover/retry.
- Eligible server count theo policy.

**Consistency và maintenance workload thường giao thoa ở p99**, nơi average che mất stragglers.

## 75. Tình huống: transaction có hot key

Ứng dụng nhận 10.000 requests/s cùng cập nhật một inventory aggregate. Mỗi transaction đọc stock, price, coupon rồi ghi Order và Inventory.

Nếu stock là hot key:

- Nhiều attempts cạnh tranh.
- Write conflicts/serialization aborts tăng.
- Mỗi retry đọc lại nhiều dependencies.
- Secondary index/update cost bị lặp.
- Tail latency và CPU tăng.
- Có thể xảy ra retry storm.

Giải pháp không nhất thiết là nâng CPU. Có thể:

- Dùng atomic conditional decrement cho một document.
- Tách reservation khỏi phần ít cần atomic.
- Queue theo aggregate/key.
- Hạn chế concurrent writers.
- Dùng sharded counter nếu domain chấp nhận consistency contract tương ứng.
- Bounded retry/backoff và admission control.

## 76. Tình huống: hạ consistency để tăng throughput

Một thử nghiệm chuyển từ read policy chặt sang read từ follower bất kỳ, thu được throughput cao hơn 40%.

Trước khi triển khai, hỏi:

- Read có thể stale đến mức nào?
- Có cần read-your-writes?
- Có phiên người dùng nào thấy state đi lùi?
- Write path có conditional invariant riêng không?
- Khi failover hoặc lag cao, data age là bao nhiêu?
- Có tenant/security/financial operations bị ảnh hưởng không?

Nếu use case là search discovery với stale tolerance phù hợp, cấu hình có thể tốt. Nếu là kiểm tra đã sử dụng coupon trước khi chi tiêu, đó có thể là **đánh đổi không được phép**.

## 77. Một mô hình chi phí tổng hợp

Có thể dùng một mô hình định tính:

\[
C_{\text{total}}=
C_{\text{index}}+
C_{\text{replication}}+
C_{\text{consistency-wait}}+
C_{\text{transaction}}+
C_{\text{retry}}+
C_{\text{operations}}
\]

Đây là **phân nhóm chi phí**, không phải công thức cộng số tiền/latency đã độc lập. Một số thành phần chia sẻ CPU/IO, có thể bị đếm trùng; latency các bước có thể chạy song song hoặc gây waiting/queueing phi tuyến.

Khi gần saturation, chỉ tăng 10% offered load có thể làm p99 tăng nhiều lần do queueing.

## 78. Amdahl's Law và giới hạn tối ưu một đoạn

Nếu một request dành 20% thời gian cho index scan, dù tăng tốc scan vô hạn, thời gian tổng theo mô hình Amdahl không thể giảm hơn phần 20% đó nếu những phần khác không đổi.

\[
Speedup = \frac{1}{(1-f)+f/s}
\]

Với \(f=0.2\), \(s\to\infty\):

\[
Speedup_{\max}=\frac{1}{0.8}=1.25
\]

Tăng tốc index 10 lần không tự tăng throughput toàn hệ 10 lần khi replication, transaction coordination hoặc application serialization mới là bottleneck.

## 79. Capacity planning không dựa trên benchmark một operation

Một database có thể đạt 50.000 simple GET/s khi cache ấm, nhưng chỉ 5.000 mixed operations/s nếu 20% là large writes có indexes và transactions.

Capacity planning phải gắn với:

- Weighted operation mix.
- Item/document sizes.
- Index count/size.
- RF và network zones.
- Consistency/ACK policy.
- Transaction size/lifetime.
- Hot key distribution.
- Background compaction/repair.
- Failover headroom.
- Peak burst duration.
- SLO p95/p99 và error budget.

Không dùng một điểm số GET benchmark để dự báo cả hệ.

---

## 80. Phương pháp benchmark có kiểm soát

Muốn so cấu hình, hãy thay đổi **một biến chính mỗi lượt** khi khả thi, đồng thời kiểm chứng correctness:

~~~text
Baseline:
  indexes I0
  RF=3
  read/write consistency C0
  no multi-document transaction for point-update

Variant A:
  add candidate index I1

Variant B:
  same indexes, modify consistency policy

Variant C:
  same indexes/consistency, use transaction

Variant D:
  interaction combination
```

Tuy nhiên một số yếu tố không tách độc lập được: thay RF có thể cần topology/rebalance, nên kết quả phải ghi rõ khác biệt.

## 81. Benchmark matrix

Một ma trận có thể dùng:

| ID | Indexes | RF | Read policy | Write policy | Operation |
|---|---|---:|---|---|---|
| A | Primary only | 3 | Eligible local/default | Default ACK | Point read/write |
| B | + targeted index | 3 | Như A | Như A | Filtered read/write |
| C | Như B | 3 | Stronger eligible read | Như A | Point/read mix |
| D | Như B | 3 | Như B | Stronger ACK | Write |
| E | Như B | 3 | Như B | Như D | Multi-document tx |
| F | Như B | 3 | Như B | Như D | Hot-key tx |

Đây là **ma trận ý tưởng**; không phải mọi engine hỗ trợ mọi tổ hợp. Không gắn nhãn “stronger” chung chung trong báo cáo cuối: phải ghi **tên option/API, phiên bản và semantics thực**.

## 82. Ghi đầy đủ điều kiện thí nghiệm

Mỗi benchmark run nên có:

~~~yaml
benchmarkRun:
  engine: MongoDB
  serverVersion: recorded
  javaDriverVersion: recorded
  topology: recorded
  storageClass: recorded
  regionZones: recorded
  replicaCount: 3
  indexDefinitions: recorded
  readPreference: recorded
  readConcern: recorded
  writeConcern: recorded
  transactionMode: recorded
  dataCount: 10000000
  avgDocumentBytes: 2048
  keyDistribution: zipfLike
  readWriteMix: "80/20"
  clientConcurrency: recorded
  offeredLoad: recorded
  warmupDuration: recorded
  steadyMeasurementDuration: recorded
  errorPolicy: recorded
~~~

Đây là cấu trúc tài liệu benchmark minh họa. Mục đích là **tái lập** kết quả, không chỉ lưu một ảnh biểu đồ p99.

## 83. Đúng dữ liệu mới đo đúng index

Dữ liệu test phải gần thực về:

- Document size và field entropy.
- Cardinality và skew.
- Array lengths/multikey entries.
- Index selectivity.
- Active versus archived data.
- Tenant size distribution.
- Shard/partition key distribution.
- Update-in-place versus insert/delete.
- TTL expiry rate.
- Query result sizes.
- Compression ratio.

Một dataset toàn random keys có thể làm index selectivity khác production. Một dataset nhỏ nằm hoàn toàn trong RAM cũng che disk IO/compaction cost.

## 84. Warm-up, steady state và maintenance phase

Tách những giai đoạn:

1. **Cold start:** driver pool, caches và OS page cache chưa ấm.
2. **Warm-up:** load đủ lâu cho JIT, connection pools, cache và compaction ổn định.
3. **Steady state:** đo latency/throughput khi hệ không tích tụ backlog.
4. **Burst:** đo phản ứng spike.
5. **Index build/repair:** đo tác động công việc nền.
6. **Node failure/election:** đo degraded behavior.
7. **Recovery/catch-up:** đo thời gian replica trở lại, lag giảm.
8. **Long soak:** phát hiện memory leak, compaction debt, storage growth.

Không coi kết quả steady-state trong vài phút là bằng chứng cluster chịu được load kéo dài nếu replication queue cứ tăng.

## 85. Open-loop và closed-loop load generation

**Closed-loop** clients thường chờ response rồi mới gửi request tiếp. Khi server chậm, offered load có thể tự giảm, làm kết quả “có vẻ ổn”.

**Open-loop** cố giữ arrival rate độc lập latency, giúp bộc lộ saturation và queue growth, nhưng phải kiểm soát client capacity và backlog.

Nếu tool load test có **coordinated omission**, các request đáng ra xuất hiện trong lúc server pause có thể không được ghi nhận như latency thực. Cần dùng cách phát tải/đo phản ánh mục tiêu thực tế và kiểm tra khả năng generator.

## 86. Warm cache có thể che chi phí index

Nếu 100% index pages và documents nằm trong memory, một query có thể nhanh hơn lúc cold/steady production có data vượt RAM.

Nên đo:

- Hot cache warm.
- Working set lớn hơn RAM.
- Cold start sau node restart.
- Index page faults/cache misses.
- Disk queue.
- Compaction/index build.

Cả hai điều kiện đều có giá trị; không trình bày chỉ kết quả thuận lợi nhất.

## 87. Đo p95/p99 không lấy trung bình phân vị

Nếu có ba Java API pods, mỗi pod xuất p99 riêng, **không lấy trung bình ba p99** rồi gọi là p99 toàn service.

Cần gộp request-level observations hoặc histograms phù hợp rồi tính quantile tổng. Đồng thời nên báo p99 per pod/zone để phát hiện hot instance.

Ví dụ PromQL với classic histogram:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(db_operation_duration_seconds_bucket{
      operation="checkout"
    }[5m])
  )
)
~~~

Metric names/labels là ví dụ. Buckets, sampling, throughput và interval phải phù hợp để phân vị có ý nghĩa.

## 88. Đừng chỉ đo completed successes

Một trial có:

~~~text
Offered requests: 100,000
Succeeded: 70,000
Timed out: 20,000
Rejected: 10,000
Success p99: 80ms
```

Nếu chỉ đo 70.000 successes, p99=80ms có thể trông rất tốt vì 20.000 slow requests **đã bị loại khỏi phân vị**.

Báo:

- Offered RPS.
- Success RPS.
- Business rejection rate.
- Timeout/transport error rate.
- p99 của requests có outcome xác định.
- Deadline violations.
- Queue length và in-flight.
- Client-side observed latency.

Không tối ưu cấu hình bằng cách làm timeout nhiều hơn rồi chỉ báo p99 thành công.

## 89. Saturation và queueing

Khi CPU, disk hoặc connection pools gần mức tối đa, một chút load tăng có thể làm:

- Queue wait tăng.
- Tail latency tăng mạnh.
- Retry storm.
- Replication lag tích lũy.
- More transaction conflicts.
- Application threads bị block.
- Error rate nhảy vọt.

Vì vậy tìm **điểm gãy SLO** và headroom, không chỉ maximum throughput tại 100% CPU.

## 90. Replication lag phải được đo sau test

Ví dụ write throughput 10.000 ops/s trong một phút, primary vẫn phản hồi nhanh, nhưng secondary backlog tăng 500.000 mutations.

Hệ không thật sự ở steady state nếu nó chỉ **chuyển nợ công việc** sang replicas. Cần tiếp tục theo dõi:

- Lag during load.
- Time to catch up after load.
- Oplog/log retention margin.
- Read freshness.
- Disk/CPU on followers.
- Recovery impact.

Một cấu hình chỉ giữ được throughput vài phút rồi lag không hồi phục không đạt capacity lâu dài.

## 91. Transaction conflict rate cần đo theo key

Hai benchmarks đều 10.000 writes/s:

- Uniform random keys.
- 90% writes tới 10 hot keys.

Kết quả transaction abort và p99 có thể rất khác. Đo:

- Conflict rate per aggregate class.
- Retry attempts per success.
- Time waiting on coordination.
- Source read/version changes.
- Hot partition/key distribution.

Đừng đổ toàn bộ lỗi lên driver hoặc RF nếu thực chất data model tạo contention vào một owner document.

## 92. Client-side Java load generator không được là bottleneck

Một Java load test có thể bị giới hạn bởi:

- Thread pool nhỏ.
- Synchronous blocking calls.
- Connection pool exhaustion.
- GC pauses.
- Serialization CPU.
- Network interfaces/port exhaustion.
- Load generator ở region xa.
- TLS setup cho từng request.
- Logging synchronous quá nhiều.

Để kết luận DB chậm, phải chứng minh **client đủ headroom** hoặc dùng nhiều load generators. Đo client CPU/GC/pool và server CPU/IO cùng lúc.

## 93. Java: một phép đo latency có ranh giới rõ

Pseudocode đo một operation:

~~~java
long started = System.nanoTime();

try {
    WriteOutcome outcome = orderRepository.confirmConditionally(
        tenantId, orderId, expectedVersion
    );
    metrics.outcome(outcome.category()).increment();
} catch (Exception ex) {
    metrics.failure(classify(ex)).increment();
    throw ex;
} finally {
    long elapsed = System.nanoTime() - started;
    metrics.dbOperationTimer.record(
        elapsed, java.util.concurrent.TimeUnit.NANOSECONDS
    );
}
~~~

Đây là **Java pseudocode** vì domain Repository/metrics types và exception mapping cần implement. `System.nanoTime()` thích hợp cho elapsed duration, không dùng làm timestamp chung giữa nodes.

Phải ghi metadata về operation, cache hit/bypass, consistency mode và transaction path để so các nhóm cùng phạm vi.

## 94. Không dùng JMH microbenchmark để kết luận DB end-to-end

JMH hữu ích để đo **phần Java in-process**, ví dụ serialization, key encoding hoặc hash function. Nhưng MongoDB/DynamoDB/Cassandra round trips bị chi phối bởi network, server scheduling, replication, storage, queueing và load mix.

Một JMH benchmark gọi remote DB có thể không đại diện production arrival model. Để đo end-to-end hãy dùng load generator/benchmark framework phù hợp, test trong môi trường đại diện và theo dõi server metrics.

Kết hợp JMH cho micro-optimizations của Java với **system benchmark** cho database.

## 95. Bộ metric tối thiểu cho từng nhóm chi phí

| Nhóm | Metrics |
|---|---|
| Index | index size, usage, keys/docs examined, index build progress, write amplification |
| Replication | per-replica CPU/IO, lag, log apply rate, network bytes, failover/catch-up |
| Consistency | read/write latency by policy, stale read count, quorum failures, unavailable |
| Transactions | duration, abort/conflict, retry attempts, commits, unknown outcome |
| Storage | disk IO queue, compaction debt, space/headroom, WAL/oplog |
| API | offered/success RPS, p50/p95/p99, timeouts, error rate |
| Java driver | pool wait, connections, selected nodes, retry counters |
| Business | invariant violations, duplicate operations, stale authorization/price |
| Cost | instance/storage/index/egress/throughput billed units |

Nếu một KPI không có measurement path đáng tin, không suy ra nó từ read latency trung bình.

## 96. Ghi lại benchmark results có cấu trúc

Ví dụ kết quả giả định:

| Trial | Successful ops/s | Read p99 | Write p99 | Conflict % | Replica lag |
|---|---:|---:|---:|---:|---:|
| A: ít indexes | 8.000 | 95 ms | 20 ms | 1% | 0,2 s |
| B: thêm index | 7.500 | 30 ms | 28 ms | 1% | 0,5 s |
| C: B + tx rộng | 5.200 | 35 ms | 80 ms | 8% | 1,1 s |

Những số liệu này **được dựng để minh họa**, không phải kết quả của MongoDB hay một hệ cụ thể.

Với read-critical workload, B có thể tốt hơn A dù writes hơi chậm. Nếu transaction C là yêu cầu correctness, A/B có thể không phải phương án hợp lệ để so.

## 97. Chi phí tiền không bằng chi phí hiệu năng

Một managed NoSQL có thể tính tiền theo:

- Provisioned/on-demand throughput.
- Read/write consumed capacity.
- Storage and indexes.
- Cross-region replication.
- Backups/restore.
- Data transfer.
- Instance/cluster size.

Một self-managed deployment còn có on-call, hardware, repair, upgrade và incident response.

Một index giúp giảm DB CPU đủ để dùng instance nhỏ hơn có thể **tiết kiệm tiền tổng thể**, dù chính index ấy tốn storage. Ngược lại, thêm RF ở region khác có thể đáp ứng resilience nhưng làm egress và storage cost tăng.

## 98. Total cost of ownership nên gồm SLO risk

Khi một cấu hình tiết kiệm 10% tiền nhưng tăng nguy cơ downtime/incorrect reads, đánh giá cần nhìn:

- Financial cost.
- SLO violation probability.
- Recovery time.
- Data loss/consistency risk.
- Operational complexity.
- Engineering maintenance effort.
- Compliance/security requirements.

Không biến mọi rủi ro thành một con số tiền thiếu căn cứ; dùng **guardrails và bắt buộc correctness** trước khi tối ưu cost.

---

## 99. Thí nghiệm A: thêm chỉ mục cho truy vấn phổ biến

### Dữ kiện giả định

~~~text
Collection: 10 million orders
Reads: 5,000/s
Writes: 1,000/s
Query: tenantId + status + sort createdAt
Candidate index: {tenantId:1,status:1,createdAt:-1}
~~~

### Cách làm

1. Chạy baseline khi chưa thêm candidate index, kiểm query plan.
2. Đo p95/p99 read và write, CPU/IO, docs examined.
3. Tạo index theo kế hoạch migration; đo **cả chi phí build**.
4. Sau khi các nodes ổn định, warm-up và chạy cùng workload.
5. Ghi index size, read improvement, write penalty, replica apply lag.
6. Kiểm plan của các query phụ, không chỉ query mục tiêu.
7. Nếu kết quả có lợi và đúng constraints, rollout có kiểm soát.

### Bài học

Index có giá trị khi **tổng lợi ích read/query** lớn hơn overhead và operational risk theo SLO.

## 100. Thí nghiệm B: tăng replication factor

### Dữ kiện giả định

~~~text
RF=2 vs RF=3
Read/write policy kept as comparable as engine allows
Data size and partition distribution documented
```

### Cần đo

- Storage bytes/indexes per replica.
- Network sync bytes.
- Primary/coordinator write p99.
- Read p99 theo selected replicas.
- Failure tolerance và availability under one-node loss.
- Time to recover/catch up.
- Consistency semantics không bị thay đổi ngầm.

### Bài học

Thêm replica có thể **cải thiện fault tolerance** mà tăng storage/network/apply cost; không tự tăng write capacity tuyến tính.

## 101. Thí nghiệm C: thay mức nhất quán

### Dữ kiện giả định

~~~text
Read policy R1: allow local replica
Read policy R2: require stronger guarantee as supported
Write policy: fixed
```

### Cần đo

- p50/p95/p99 read.
- Stale-read violations theo source version.
- Read-your-writes.
- Timeouts khi node/zone lỗi.
- Cross-AZ/region bytes.
- Per-replica load và tail behavior.

### Bài học

Nếu R1 không đáp ứng read freshness bắt buộc, không chọn R1 chỉ vì p99 nhanh. Nếu cả hai đều hợp lệ, xem R1/R2 như quyết định latency/availability/cost.

## 102. Thí nghiệm D: từ atomic update sang multi-document tx

### Dữ kiện giả định

~~~text
Operation 1:
  decrement stock if available >= q

Operation 2:
  decrement stock + insert Order + add Outbox
```

Đây là **hai business operations khác nhau**, nên không thể so raw latency rồi tuyên bố transaction “chậm hơn một phép trừ x lần” như một nhận xét có ý nghĩa độc lập. Muốn đo transaction overhead gần hơn, cần so những implementations mang **cùng logical effect và correctness**, trong giới hạn engine cho phép.

Đo transaction lifetime, commits, aborts, retry amplification và end-to-end business success.

## 103. Thí nghiệm E: transaction rộng và transaction hẹp

Giả sử cả hai cách đều bảo vệ invariant:

~~~text
Wide:
  read 20 documents
  update 5
  hold transaction 250 ms

Narrow:
  read 3 authoritative dependencies
  update 2
  hold transaction 20 ms
```

Nếu narrow transaction thật sự vẫn bảo đảm business rules, nó có thể giảm conflict và tail latency. Nhưng không tự bỏ 17 reads chỉ vì muốn nhanh; phải chứng minh chúng không phải decision dependencies.

**Thu nhỏ scope hợp lệ là tối ưu tốt; bỏ invariant để giảm scope là lỗi correctness.**

## 104. Thí nghiệm F: thêm unique constraint

Một unique index hoặc conditional insert làm write path tốn thêm validation/maintenance nhưng ngăn duplicate username/coupon usage.

Trong báo cáo, đánh dấu:

~~~text
Correctness guardrail:
  duplicate keys committed = 0
```

Nếu phương án không có unique constraint commit duplicate, nó **không đạt yêu cầu** và không được chọn chỉ vì throughput cao.

## 105. Thí nghiệm G: background index build dưới tải

Trong giờ cao điểm, index build tiêu thụ IO:

~~~text
Index build start
Read p99 rises
Write queue grows
Replication lag increases
Index build completes
Cluster catches up
~~~

Cần quyết định:

- Index build window.
- Throttle/capacity reserve.
- Resource headroom.
- Monitoring thresholds.
- Rollback/abort capability.
- Replica catch-up budget.

Một index tốt sau build vẫn có thể có **chi phí migration không chấp nhận được** nếu triển khai không có kế hoạch.

## 106. Thí nghiệm H: failover và retry

Không chỉ benchmark healthy cluster. Tạo failure injection trong môi trường được phép:

1. Ổn định workload.
2. Cho primary/leader của một scope bước xuống hoặc ngắt một node theo quy trình.
3. Ghi số requests timeout, unknown commit outcomes.
4. Theo dõi topology discovery/selection.
5. Đo read/write SLO trong election.
6. Xác minh không mất/cộng trùng business effect.
7. Kiểm tra recovery/replica catch-up.

Nếu thao tác không được phép trên production, làm trong staging hoặc test cluster đại diện.

## 107. Thí nghiệm I: hot-key và retry storm

Dùng hai phân bố:

~~~text
Uniform: 100,000 keys, accesses spread evenly
Skewed: 90% writes target 10 keys
```

Đo conflict rates, transaction durations, retries và successful throughput. Nếu skewed workload sụp, xem lại aggregate boundaries, conditional primitive và admission control; không chỉ tăng pool size.

## 108. Thí nghiệm J: cross-region consistency

Cho các users/clients ở hai regions:

- Đo read locality.
- Đo commit/replication RTT.
- Kiểm tra data residency.
- Kiểm tra concurrent writes nếu active-active.
- Mô phỏng region isolation.
- Đo stale window và conflict reconciliation.
- Xác minh endpoint failover không nhân đôi business operation.

Không gọi một cấu hình active-active là strong global transaction chỉ vì các vùng tự động replicate.

---

## 109. Những anti-pattern khi tối ưu hiệu năng NoSQL

1. **Chỉ đo GET với warm cache**, bỏ writes và index maintenance.
2. **Tăng indexes không có chủ đích**, dẫn tới disk/IO áp lực.
3. **Gỡ unique index vì ít được query**, phá domain constraint.
4. **Tăng RF rồi kỳ vọng write throughput tăng theo RF**.
5. **Chỉ đo primary**, không thấy follower apply lag.
6. **Báo quorum là linearizable** mà không xét engine semantics.
7. **Dùng eventual read để duyệt payment**, sai freshness/invariant.
8. **Dùng strong read rồi update không điều kiện**, vẫn lost update.
9. **Dùng multi-document transaction cho một atomic single-item update** khi không cần.
10. **Dùng transaction nhưng không bảo vệ write skew/phantom**.
11. **Giữ transaction mở trong lúc gọi external API**.
12. **Tăng retry limit để che hot-key contention**.
13. **Bỏ timeout requests khỏi latency histogram**.
14. **Lấy trung bình các p99 instance** rồi gọi là p99 cluster.
15. **Đo QPS offered thay QPS thành công**.
16. **Chạy benchmark trên data nhỏ nằm vừa RAM** rồi suy ra production.
17. **Không ghi driver, server và topology versions**, không tái lập được.
18. **Thay đổi nhiều knobs đồng thời**, không biết yếu tố nào gây kết quả.
19. **Tối ưu chi phí bỏ qua resilience/SLO risk**.
20. **Dùng one-size-fits-all consistency/transaction API** qua MongoDB, Cassandra, DynamoDB, Redis.
21. **Giữ queue/repl lag tăng khi kết thúc test**, nhưng gọi throughput bền vững.
22. **Không tính index storage trên replicas**.
23. **Không kiểm invariant dưới concurrent writes**.
24. **Suy transaction success từ response khi commit có thể unknown**.
25. **Tăng pool vô hạn khi server đã saturation**.

## 110. Bài tập A — Dung lượng index và RF

Data+index trên một replica là 130 GiB, RF=3.

**Hỏi:** footprint cơ sở xấp xỉ bao nhiêu, chưa tính logs/headroom?

**Hướng giải:** \(3\times130=390\) GiB. Cần tính thêm oplog/WAL/compaction/snapshots trước capacity planning.

## 111. Bài tập B — Tăng thêm index

Một index mới chiếm 8 GiB/replica, RF=3.

**Hỏi:** tổng dung lượng data/index tăng xấp xỉ bao nhiêu theo giả định replica giống nhau?

**Hướng giải:** khoảng 24 GiB, chưa tính temporary/build overhead.

## 112. Bài tập C — Quorum lý tưởng

N=3, W=2, R=2.

**Hỏi:** \(R+W>N\) có đúng không? Nó có tự chứng minh linearizability của mọi NoSQL engine không?

**Hướng giải:** có, \(2+2>3\), nhưng chỉ bảo đảm giao tập trong mô hình lý tưởng; còn cần consistency/version/conflict semantics của engine.

## 113. Bài tập D — Replication và write capacity

Một primary có hai secondaries. Nhóm thêm một secondary.

**Hỏi:** write throughput có chắc tăng 33%?

**Hướng giải:** không; primary vẫn điều phối writes, replication cost còn tăng. Tác động phụ thuộc topology và ACK policy.

## 114. Bài tập E — Strong read và lost update

Hai clients strong-read stock=1 rồi cùng ghi `stock=0` bằng unconditional write.

**Hỏi:** strong read đủ ngăn overselling?

**Hướng giải:** không. Cần conditional decrement, CAS hoặc transaction bảo vệ invariant tại điểm ghi.

## 115. Bài tập F — Unique index ít dùng

Unique index trên `(tenantId,username)` hiếm khi được query.

**Hỏi:** có nên drop vì index usage thấp?

**Hướng giải:** không nếu nó là ràng buộc uniqueness; phải bảo toàn constraint trước khi đổi.

## 116. Bài tập G — Write amplification

Một logical write 2 KiB tạo tổng 16 KiB physical storage writes trong điều kiện đo đã định.

**Hỏi:** storage write amplification bằng bao nhiêu?

**Hướng giải:** \(16/2=8\). Phải mô tả scope và phương pháp đo, không so tùy tiện với một engine dùng định nghĩa khác.

## 117. Bài tập H — Conflict retry

10.000 business commits cần 15.000 transaction attempts.

**Hỏi:** trung bình attempts per commit?

**Hướng giải:** 1,5 attempts/commit; nếu có failures không commit, cần báo cả tỷ lệ và số attempts của chúng.

## 118. Bài tập I — Index build trong giờ cao điểm

Read p99 tăng từ 40 lên 180 ms trong lúc build; replication lag cũng tăng.

**Hỏi:** cần đo gì trước khi kết luận index gây ảnh hưởng?

**Hướng giải:** disk/CPU/index build progress, per-replica lag, request mix, latency histograms, pool wait; so run có/không build với điều kiện tương đương.

## 119. Bài tập J — GSI nhất quán mạnh

App dùng DynamoDB GSI query rồi bật `ConsistentRead=true` để bảo vệ quota.

**Hỏi:** giả định sai ở đâu?

**Hướng giải:** GSI không hỗ trợ strongly consistent reads theo API tương ứng; quota nên được bảo vệ bằng authoritative conditional/transaction write.

## 120. Bài tập K — Cassandra LOCAL_QUORUM

Chuyển từ LOCAL_ONE sang LOCAL_QUORUM.

**Hỏi:** có thể kỳ vọng read latency thấp hơn một cách chắc chắn không?

**Hướng giải:** không. Cần đo request waiting/replica latency và failures; mức nhất quán chặt hơn có thể đổi availability/latency theo workload.

## 121. Bài tập L — Transaction write skew

Hai transactions sửa hai doctors khác nhau sau khi đọc cả hai đều on-call.

**Hỏi:** transaction nhiều document có tự ngăn quy tắc “ít nhất một bác sĩ trực” bị phá?

**Hướng giải:** không dưới một số snapshot isolation nếu không có conflict/predicate protection; cần thiết kế invariant/serializable semantics phù hợp.

## 122. Bài tập M — Load generator closed-loop

Server chậm gấp 10 lần, client closed-loop tự gửi requests ít hơn.

**Hỏi:** số successful QPS có thể che điều gì?

**Hướng giải:** hệ chưa được thử ở arrival rate mục tiêu; cần hiểu offered load, coordinated omission, queueing và client limits.

## 123. Bài tập N — Percentiles

Có ba instances p99 lần lượt 50, 100, 200 ms.

**Hỏi:** lấy trung bình 116,7 ms có phải p99 toàn service?

**Hướng giải:** không. Cần aggregate observations/histogram đúng; kết quả phụ thuộc số lượng và distribution requests từng instance.

## 124. Bài tập O — Read nhanh nhưng stale

Read từ follower mất 4 ms, primary mất 12 ms. Follower lag 5 giây; user cần read-your-writes trong 100 ms.

**Hỏi:** chọn follower vì nhanh hơn?

**Hướng giải:** không nếu không có causal/session/version mechanism đáp ứng freshness SLO. Tốc độ không bù cho việc không đúng hợp đồng.

## 125. Bài tập P — Query không có index

Một query không index chỉ chạy 5 ms khi 10.000 documents nằm trong RAM; production có 100 triệu documents.

**Hỏi:** có thể dự báo query 5 ms ở production?

**Hướng giải:** không. Cần query plan, data scale, selectivity và workload disk/cache tương ứng.

## 126. Bài tập Q — Transaction và email

Transaction callback ghi Order, gửi email, sau đó abort và retry.

**Hỏi:** chi phí/risks nào không xuất hiện trong chỉ số DB commit p99?

**Hướng giải:** email trùng, external latency, side effects không rollback, retry amplification. Dùng outbox/idempotent consumer.

## 127. Bài tập R — RF và backup

Cluster RF=3, một application bug xóa tất cả Order documents.

**Hỏi:** replication có thay backup/PITR không?

**Hướng giải:** không; logical deletes có thể được replicate. Cần independent recoverable backup và restore drills.

## 128. Bài tập S — Nợ replication

Primary xử lý 20.000 ops/s trong benchmark nhưng secondary lag tăng liên tục.

**Hỏi:** benchmark có chứng minh throughput bền vững?

**Hướng giải:** chưa; cần steady state không tăng backlog không giới hạn và thời gian catch-up trong SLO.

## 129. Bài tập T — So hai cấu hình khác correctness

A không có unique constraint và đạt 15.000 writes/s; B có constraint bảo vệ duplicate và đạt 12.000 writes/s.

**Hỏi:** A tốt hơn?

**Hướng giải:** nếu uniqueness là yêu cầu bắt buộc, A **không hợp lệ**, không thể chọn bằng raw throughput.

## 130. Bài tập U — Hot key

Một hot stock aggregate gây 60% transaction abort khi tăng concurrent clients.

**Hỏi:** thêm CPU có phải giải pháp duy nhất?

**Hướng giải:** không. Giảm transaction scope, atomic conditional update, admission control, per-key queue hoặc redesign aggregate.

## 131. Bài tập V — Chi phí đa region

RF tăng từ hai bản trong một region lên ba bản với một bản khác region.

**Hỏi:** chi phí nào cần bổ sung?

**Hướng giải:** WAN egress/RTT, replication lag, data residency, conflict/failover semantics, storage và recovery costs.

## 132. Bài tập W — Index scan và covered query

Một compound index giúp query chỉ đọc indexed fields mà không fetch documents, nhưng index size tăng nhiều.

**Hỏi:** kết luận tối ưu là gì?

**Hướng giải:** đo read p95/p99, memory, write maintenance, storage/replication and cost với workload thật; covered không tự luôn tốt.

## 133. Bài tập X — Retry storm

SDK retry tối đa ba lần, service retry ba lần, gateway retry ba lần.

**Hỏi:** có thể phát sinh bao nhiêu attempts lý thuyết nếu mọi tầng lặp lại?

**Hướng giải:** trong một cấu trúc lồng nhau có thể tới \(3\times3\times3=27\) low-level attempts; cần phối hợp deadline và retry budgets.

---

## 134. Checklist trước khi tối ưu bốn yếu tố

**Yêu cầu nghiệp vụ**

1. Đã viết rõ invariant phải giữ chưa?
2. Read staleness được phép đến mức nào?
3. Write success cần durability/ACK nào?
4. Có cần read-your-writes/causal session không?
5. Những trường hợp nào cần transaction và những trường hợp nào chỉ cần atomic update?
6. Có tài liệu hóa semantics khi timeout/unknown commit không?

**Chỉ mục**

7. Index nào phục vụ query shape nào?
8. Có index ít dùng nhưng bảo vệ unique/TTL constraint không?
9. Có query plans và keys/docs examined chưa?
10. Index sizes và memory headroom đã đo chưa?
11. Có đo write throughput sau khi thêm index không?
12. Có đo index build/compaction và rollback plan không?
13. Có chú ý multikey, large fields và hot index ranges không?

**Sao chép**

14. RF áp trên shard/partition nào?
15. Đã tính data+index footprint nhân replica chưa?
16. Replication network/CPU/IO đã đo chưa?
17. Có theo dõi apply lag và log retention margin không?
18. Đã thử một node/AZ lỗi và recovery chưa?
19. Có independent backup/PITR, không dựa replication như backup không?
20. Có tính cross-region egress và data residency không?

**Mức nhất quán**

21. Đã ghi cụ thể read/write options của engine chưa?
22. Có nhầm read preference với read concern/write concern không?
23. Có dùng eventual projection làm authority cho action quan trọng không?
24. Read-your-writes và stale reads đã có test không?
25. Quorum assumptions đã được kiểm với engine semantics chưa?
26. Có benchmark healthy và degraded topology không?

**Giao dịch**

27. Có thể đưa invariant về atomic single-item operation không?
28. Multi-document transaction có đúng deployment support không?
29. Isolation có ngăn write skew/phantom cần thiết không?
30. Transaction scope có ngắn và không gọi external API không?
31. Có đo retry/abort/unknown outcome không?
32. Idempotency/outbox có bảo vệ replay và side effects không?
33. Hot-key conflict có bị che bằng tăng retry vô hạn không?

**Đo tải và quyết định**

34. Có thống nhất dataset, workload mix và key distribution không?
35. Có tách offered load, achieved throughput, errors và rejections không?
36. Có warm-up, steady state, burst và soak không?
37. Load generator có đủ capacity, tránh coordinated omission không?
38. Có p95/p99 đúng scope, không trung bình p99 không?
39. Có đo server CPU/IO, network, pools và queuing không?
40. Có xác minh replication lag hồi về mức ổn định sau test không?
41. Có ghi driver/server version, topology và indexes để tái lập không?
42. Có so chi phí tiền, capacity headroom, vận hành và SLO risk không?
43. Thử nghiệm có guardrails về correctness và data freshness không?
44. Có kế hoạch canary/rollback từng thay đổi cấu hình không?

## 135. Một mẫu báo cáo benchmark

~~~yaml
study: IndexReplicationConsistencyTransactionTradeoffs
scope:
  service: JavaOrdersApi
  database: NoSQL
  workload: documentedReadWriteMix
correctness:
  required:
    - noOverselling
    - uniqueOrderPerOperationId
    - noCrossTenantWrites
    - documentedReadFreshness
variants:
  - id: baseline
    indexConfiguration: I0
    replicaConfiguration: R0
    readWritePolicy: C0
    transactionPath: T0
  - id: candidate
    indexConfiguration: I1
    replicaConfiguration: R1
    readWritePolicy: C1
    transactionPath: T1
measurement:
  input:
    - offeredRps
    - concurrency
    - dataSize
    - keySkew
    - documentSize
    - runtimeAndDriverVersions
  result:
    - successfulRps
    - businessRejections
    - timeoutErrorRate
    - readP95
    - readP99
    - writeP95
    - writeP99
    - transactionAbortRate
    - attemptsPerCommit
    - sourceCpuIo
    - indexBytes
    - replicationLag
    - networkEgress
    - monthlyCostEstimate
    - invariantViolationCount
runPhases:
  - coldStart
  - warmup
  - steadyState
  - burst
  - failover
  - recovery
guardrails:
  - noCorrectnessRegression
  - noUnboundedReplicationBacklog
  - deadlineAndErrorSlo
  - regionDataResidency
decision:
  chooseOnlyAmongContractCompliantVariants: true
  rationale: recordTradeoffs
~~~

Đây là **YAML tài liệu phương pháp thử nghiệm**, không phải cấu hình tự chạy trên MongoDB, Cassandra, DynamoDB, Redis hay load tool. Các tên mục cần được ánh xạ sang metric instrumentation thật.

## 136. Kết luận

Trong NoSQL, **chỉ mục, replication, consistency và transaction là bốn công cụ để mua những đặc tính khác nhau bằng tài nguyên và độ phức tạp**:

- **Chỉ mục** mua khả năng tìm kiếm có chọn lọc nhanh hơn, đổi lấy storage, RAM, write maintenance và chi phí migration.
- **Sao chép** mua fault tolerance và một số khả năng mở rộng đọc, đổi lấy storage, network, apply work và bài toán lag/failover.
- **Mức nhất quán** quy định điều kiện quan sát và xác nhận; tăng chặt có thể giảm lựa chọn route, tăng latency/waiting hoặc giảm availability khi lỗi.
- **Giao dịch** mua atomicity và isolation trong scope được hỗ trợ, đổi lấy coordination, contention, commit cost, retries và recovery complexity.

Quan trọng nhất là **các khoản chi phí cộng hưởng**. Một transaction trên hot key, nhiều secondary indexes, đòi quorum acknowledgment và trải nhiều shards có thể gây p99 rất khác tổng những microbenchmark riêng lẻ.

> **Không chọn cấu hình đạt QPS cao nhất khi nó không đáp ứng tính đúng đắn. Hãy chọn cấu hình đáp ứng invariant và SLO, có khả năng chịu lỗi, đo được toàn bộ chi phí, và giữ đủ headroom để vận hành lâu dài.**

Kỹ sư cần kết thúc mỗi quyết định bằng câu trả lời có bằng chứng: **query nào được tăng tốc; mỗi write tốn thêm bao nhiêu; các replicas có theo kịp không; mức đọc/ghi nào được bảo đảm; transaction có giữ invariant không; p99 và error rate thay đổi ra sao; và chi phí có còn hợp lý khi tải thật tăng hoặc một node ngừng hoạt động?**
