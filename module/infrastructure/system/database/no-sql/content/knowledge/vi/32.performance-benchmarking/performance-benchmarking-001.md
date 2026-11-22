# Xác định độ trễ, thông lượng và phạm vi thao tác được đo

## 1. Bắt đầu từ một câu hỏi có thể kiểm chứng

Giả sử một đội phát triển Java đang cân nhắc dùng MongoDB, Cassandra và DynamoDB cho dịch vụ tra cứu đơn hàng. Báo cáo benchmark ban đầu ghi:

> “Database A đạt 15.000 ops/s, độ trễ trung bình 4 ms. Database B chỉ đạt 8.000 ops/s nhưng p99 là 20 ms.”

Có thể chọn A ngay không? **Chưa.** Những con số trên gần như không có ý nghĩa nếu chưa biết:

- `ops/s` là số thao tác **được phát đi**, được **database ACK**, hay được **nghiệp vụ hoàn thành**?
- Một thao tác là `GET` theo primary key, query theo index, scan, batch 100 records, hay transaction chứa nhiều writes?
- 4 ms được đo ở server, driver, HTTP API hay từ thiết bị của người dùng?
- Các requests timeout, retry, bị từ chối, hoặc trả dữ liệu sai có được tính?
- Cùng payload, consistency level, partition distribution và cache hit rate không?
- Dữ liệu có đủ lớn để vượt RAM không? Có index, replica và compaction tương tự không?
- p99 được tính trên bao nhiêu mẫu, trong khoảng thời gian nào, ở mức tải nào?

Trong chương **Hiệu năng và đo tải** của **Database No SQL**, bài này tập trung vào công việc nền tảng nhất: **định nghĩa chính xác độ trễ (latency), thông lượng (throughput) và phạm vi thao tác (operation scope) trước khi đo**.

Mục tiêu không phải thu thật nhiều số, mà là làm cho mỗi số có cùng **đơn vị, ranh giới, tập yêu cầu, trạng thái hoàn tất và điều kiện đo** để so sánh có ý nghĩa.

## 2. Bộ ba khái niệm: latency, throughput, operation scope

### 2.1. Độ trễ (latency)

Độ trễ của một thao tác thường là thời gian từ một mốc bắt đầu được định nghĩa đến một mốc hoàn thành được định nghĩa:

\[
L_i=t_{\text{end},i}-t_{\text{start},i}
\]

Ví dụ `getOrder("O100")` bắt đầu gọi driver tại `10:00:00.100` và trả kết quả tại `10:00:00.118`:

\[
L=18\ \text{ms}
\]

Nhưng nếu trước đó request chờ 40 ms trong queue của API, **độ trễ end-to-end** đã khác.

### 2.2. Thông lượng (throughput)

Thông lượng là lượng công việc **đã được xử lý/hoàn thành** trong một đơn vị thời gian, theo loại công việc và tiêu chí đếm được định nghĩa:

\[
X=\frac{N_{\text{completed operations}}}{\Delta t}
\]

Ví dụ 6.000 thao tác hợp lệ hoàn tất trong 2 giây:

\[
X=3.000\ \text{ops/s}
\]

Nếu 6.000 thao tác được phát nhưng chỉ 4.000 thành công và 2.000 timeout, phải báo cả **offered load, completed throughput và error rate**, không viết chung một số “6.000 ops/s”.

### 2.3. Phạm vi thao tác

Một “operation” cần có định nghĩa như:

```text
Operation: GetOrderById
Key: orderId
Result: một document gồm 12 fields
Consistency: primary read / mode được nêu rõ
Payload: ~2 KiB
Start: trước khi gọi driver
End: khi driver trả kết quả hoặc exception
Success: tìm thấy document hợp lệ
Timeout: 200 ms
Retries: tối đa 1, được tính riêng
```

**Không có operation scope thì latency và throughput là những con số không có ngữ cảnh.**

## 3. Một phép đo tốt phải là một hợp đồng

Thay vì ghi “MongoDB read p99=25 ms”, hãy ghi:

```text
Workload ID:
  orders-get-by-id-2k-payload-v1

Source:
  MongoDB replica set 3 members, topology được ghi lại

Operation:
  find one order by primary key
  read preference=primary
  projection=12 fields, ~2 KiB serialized BSON

Measurement boundary:
  Java caller -> synchronous driver -> response decoded

Offered load:
  4,000 requests/s, open-loop

Duration:
  warmup 5 phút; measure 20 phút

Result:
  achieved successful throughput 3,970 ops/s
  p50=8 ms, p95=22 ms, p99=58 ms
  timeout=0.4%, error=0.35%, remainder theo rule cụ thể
```

Các số minh họa không phải kết quả benchmark của một sản phẩm thật.

### 3.1. Điều kiện nào là một phần của hợp đồng?

- Database và phiên bản.
- Cluster topology, shard/replica count, failure domains.
- Dataset size, distribution và index.
- Loại thao tác, size, query/projection.
- Read/write consistency, durability, transaction scope.
- Cache mode và hit ratio.
- Load model, arrival rate, concurrency.
- Driver/SDK version, connection pool, retry policy.
- Network topology, region, TLS.
- Warmup, measurement window.
- Định nghĩa success/error/timeout.
- Cách tạo histogram và ghi số liệu.

Khi thiếu một điều kiện quan trọng, nên ghi rõ **chưa xác định** thay vì suy từ con số tổng hợp.

## 4. Các ranh giới đo thường gặp

Sơ đồ một request:

```text
Browser
   |
   | A: browser network
   v
API Gateway / Load Balancer
   |
   | B: queue, auth, routing
   v
Java Application
   |
   | C: validation/business logic/cache
   v
NoSQL Driver
   |
   | D: pool wait, serialization, retry, network
   v
NoSQL Coordinator/Server
   |
   | E: admission, execution, storage/replication
   v
NoSQL Response
   |
   | F: decode, application processing
   v
API Response
   |
   v
Browser
```

Có thể đo:

| Chỉ số | Mốc bắt đầu → kết thúc | Bao gồm |
|---|---|---|
| Client-perceived latency | Người dùng/client gửi → nhận kết quả | Mạng, gateway, API, DB, response |
| HTTP server latency | Gateway/API bắt đầu xử lý → trả response | Queue tùy instrumentation, business logic, dependencies |
| Repository latency | Vào method repository → return | Mapping, driver, database, lỗi/retry tùy method |
| Driver operation latency | Trước lệnh driver → nhận result/exception | Pool wait, serialize, network, server, decode, retry |
| Server execution time | Server nhận request → hoàn tất xử lý | Chỉ phạm vi server instrumentation |
| Storage service time | Worker bắt đầu thao tác storage → xong | Không bao gồm mọi queue, network |
| Cache lookup latency | GET cache bắt đầu → trả | Chỉ lookup; miss có thể kích hoạt đường khác |
| Business workflow latency | Intent checkout → trạng thái CONFIRMED/FAILED | Nhiều services, queues, retries và waits |

**Không trừ hai số đo ở hai máy bằng wall-clock timestamps một cách tùy tiện:** đồng hồ có thể lệch. Đo duration tốt nhất bằng đồng hồ monotonic **trên cùng tiến trình**, hoặc tracing có cơ chế hiệu chỉnh/đánh giá clock skew phù hợp.

## 5. Client latency khác server execution time

Ví dụ:

```text
Java driver call:             35 ms
  Connection pool wait:       10 ms
  Serialization/routing:       2 ms
  Network round trip:         12 ms
  Server queue + execution:    8 ms
  Decode/other:                3 ms
```

Server dashboard có thể hiển thị **8 ms**, trong khi ứng dụng thấy **35 ms**. Cả hai có thể đúng vì đo các đoạn khác nhau.

### 5.1. Khi nào đo client-side?

- Khi lập SLO cho ứng dụng.
- Khi so driver/configuration.
- Khi đánh giá tác động của network/connection pool.
- Khi người dùng than phiền dù server CPU thấp.

### 5.2. Khi nào đo server-side?

- Khi tìm bottleneck query engine/storage.
- Khi đánh giá index, compaction, shard hotspot.
- Khi hiểu queue/admission/throttling.
- Khi phân tích các phép đo phía client tăng mà server execution không tăng.

### 5.3. Không cộng các số một cách máy móc

Một số giai đoạn có thể overlap, được đo bằng clocks khác hoặc dùng aggregation windows khác. Thời gian p99 của pool wait cộng p99 của server execution **không tự bằng p99 end-to-end**.

## 6. Response time, service time và queueing time

Một phân tích gần đúng:

\[
T_{\text{response}}\approx
T_{\text{queue}}+T_{\text{service}}+T_{\text{network}}+
T_{\text{client overhead}}
\]

- **Queue time:** đợi pool, scheduler, server admission hoặc worker.
- **Service time:** thực thi thao tác khi được tài nguyên phục vụ.
- **Network time:** chuyển dữ liệu, RTT, TLS, congestion.
- **Client overhead:** encode, decode, mapping, application work.

### 6.1. Vì sao queueing quan trọng?

Database thực thi một query chỉ 2 ms nhưng pool đã bão hòa, request có thể chờ 200 ms trước khi được gửi đi. Giảm server execution từ 2 ms xuống 1 ms chưa chắc giải quyết hết p99.

### 6.2. Một timeout có thể bắt đầu ở nhiều mốc

- Chờ connection pool;
- Chờ server selection;
- Chờ socket/HTTP;
- Chờ query;
- Chờ commit quorum;
- Chờ toàn workflow.

Cần nêu rõ `timeout=200 ms` áp dụng cho **một attempt**, **driver call bao gồm retries**, hay **toàn request**.

### 6.3. Cancellation

Client hủy request không bảo đảm server đã dừng thao tác hoặc chưa commit. Đếm canceled requests riêng khi có thể; business writes cần idempotency.

## 7. Đơn vị phải thống nhất

| Đại lượng | Đơn vị | Ví dụ |
|---|---|---|
| Duration | µs, ms, s | `p99=42 ms` |
| Request throughput | req/s hoặc RPS | `4.000 HTTP requests/s` |
| Database operation throughput | ops/s | `8.000 item GET/s` |
| Transaction throughput | tx/s hoặc TPS | `700 committed transactions/s` |
| Document throughput | documents/s | `80.000 documents/s` |
| Row throughput | rows/s | `100.000 returned rows/s` |
| Byte throughput | MB/s, MiB/s | `200 MiB/s read` |
| Event throughput | events/s | `5.000 CDC events/s` |
| Request unit/capacity | RU/s, RCU/WCU, service-specific unit | Theo contract vendor |
| Concurrency | in-flight operations | `250 concurrent requests` |
| Queue backlog | messages/operations | `40.000 pending` |

### 7.1. MB và MiB

\[
1\ \text{MB}=10^6\ \text{bytes}
\]

\[
1\ \text{MiB}=2^{20}\ \text{bytes}
\]

Một báo cáo phải dùng nhất quán khi so disk/network throughput.

### 7.2. Ops/s không tự suy ra MB/s

5.000 GET/s × payload 2 KiB khác xa 5.000 GET/s × payload 2 MiB. Cần cả request bytes, response bytes, index scan bytes và replication traffic nếu chúng có ảnh hưởng.

### 7.3. Request units không phải đơn vị phổ quát

Một dịch vụ managed NoSQL có thể tính capacity theo RU/RCU/WCU hoặc hệ số riêng. Không quy đổi thành CPU hay ops/s của database khác nếu không có workload và công thức chính xác.

## 8. Offered load, achieved throughput và goodput

Phân biệt ba số:

- **Offered load:** tốc độ yêu cầu được đưa vào hệ đo, ví dụ 5.000 req/s.
- **Achieved throughput:** tốc độ requests đã hoàn tất (thành công và/hoặc thất bại, phải ghi rõ).
- **Goodput:** tốc độ tác vụ **thành công, hợp lệ và hữu ích theo hợp đồng**.

Ví dụ một cửa sổ 10 giây:

```text
Submitted requests:       50.000
Finished successfully:    38.000
Finished with errors:      7.000
Still pending / timeout:   5.000
```

Nếu tính trên 10 giây theo mốc arrivals:

```text
Offered load = 5.000 req/s
Successful goodput ~ 3.800 req/s
```

Tỷ lệ lỗi/timeout nên có công thức và denominator rõ, vì những requests pending có thể hoàn thành sau cửa sổ.

### 8.1. Không đổi tên submitted thành throughput

Một load generator có thể **phát 100.000 requests/s** nhưng server chỉ hoàn thành 10.000/s. Gọi 100.000/s là “database throughput” gây hiểu lầm.

### 8.2. Không loại bỏ lỗi khỏi biểu đồ một cách âm thầm

Nếu chỉ tính latency của requests thành công và bỏ 30% timeouts, p99 được báo có thể trông tốt hơn đáng kể dù hệ suy giảm nghiêm trọng.

### 8.3. Goodput cần correctness

Một read trả `200 OK` nhưng dữ liệu stale trái hợp đồng, hoặc một checkout trả CONFIRMED trùng ghế, không thể mặc nhiên tính là thành công nghiệp vụ.

## 9. Định nghĩa một operation khi đo NoSQL

Một thao tác có thể là một trong các mức sau:

```text
Database command
   |-- một key GET
   |-- một query trả nhiều documents
   |-- một batch chứa nhiều sub-operations
   |-- một transaction gồm nhiều commands

Application operation
   |-- repository.findById()
   |-- cache-aside read với hit/miss
   |-- business reserve() có conditional write

Workflow operation
   |-- checkout qua Order, Inventory, Payment
```

Nếu một HTTP GET gọi database ba lần, **1 HTTP request** có thể tương ứng **3 DB operations**. Không so 10.000 HTTP RPS với 10.000 DB ops/s như nhau.

### 9.1. Đếm query hay đếm rows?

Một query trả 1.000 rows có thể được đếm:

- 1 query;
- 1.000 returned rows;
- 1 cursor và nhiều `fetchNextPage`;
- 100 KiB/10 MiB response.

Mỗi cách trả lời một câu hỏi khác.

### 9.2. Batch write

Một batch 100 items:

```text
One batch request = 1 RPC
100 item writes = tối đa 100 item operations
```

Nếu 5 items thất bại và được retry riêng, cần báo cả **batch RPC/s, item/s, successful item/s và retries**.

### 9.3. Transaction

Một transaction gồm hai reads, ba writes và một commit. Có thể báo:

```text
TPS = số transactions commit/s
Commands/s = tổng commands bên trong/s
Commit latency = từ begin tới commit ACK
```

Không lấy 5 commands × 1.000 TPS rồi nói “5.000 TPS”.

## 10. Xác định thành công của một read

Một read thành công có thể được định nghĩa khác nhau:

- Đọc được key tồn tại.
- Trả `NOT_FOUND` đúng cho key không tồn tại.
- Trả tài liệu từ cache.
- Trả bản ghi **đủ mới** theo session/read consistency.
- Trả một page đúng size và continuation token.
- Trả top-K vector results đủ điều kiện recall/quality.
- Trả graph traversal thỏa depth/limit.

### 10.1. `NOT_FOUND` có phải success?

Nếu benchmark có 20% keys không tồn tại, `NOT_FOUND` có thể là outcome hợp lệ. Phải tách hit/miss vì chi phí khác nhau và ảnh hưởng tới latency.

### 10.2. Đọc từ secondary

Một secondary read có thể nhanh và rẻ hơn ở một vùng nhưng stale. Nếu mục tiêu là authoritative read, phải tính freshness/consistency vào correctness.

### 10.3. Pagination

Query có `LIMIT 100` trả page đầu không tương đương truy xuất **toàn bộ 10.000 records**. Định nghĩa thao tác là `fetchPage` hay `fetchAll` trước khi tính latency.

## 11. Xác định thành công của một write

Các mốc của một write:

```text
Request received
   |
   v
Validated
   |
   v
Accepted/queued
   |
   v
Applied locally
   |
   v
Replicated / committed
   |
   v
Durable according to contract
   |
   v
Visible on read path
   |
   v
Downstream projection updated
```

Tùy hệ, những mốc này có thể khác thời điểm và không tạo thành một chuỗi tuyệt đối đơn giản ở mọi topology.

### 11.1. ACK có nghĩa gì?

- MongoDB: write concern và journaling/majority context.
- Cassandra: consistency level cho regular write hoặc LWT semantics.
- DynamoDB: item/transaction success theo API, global replication mode là câu hỏi khác.
- Redis: command ACK, persistence/replication/failover phụ thuộc mode.
- Elasticsearch: index write ACK khác search refresh visibility.

### 11.2. Một `202 Accepted` không phải DB commit

Nếu ghi qua write-behind hoặc durable queue, API có thể chỉ xác nhận command đã được nhận bền, database chưa áp dụng. Benchmark phải đo riêng **accept latency** và **persist latency**.

### 11.3. Write có điều kiện bị từ chối

`IF NOT EXISTS` trả condition false có thể là **business conflict hợp lệ**, không phải lỗi hạ tầng. Báo số conflict rate riêng và không đếm như một thành công claim.

### 11.4. Timeout sau commit

Write có thể đã commit nhưng response mất. Một lần retry có thể không an toàn nếu tạo ID mới hoặc thực hiện side effect mới. Benchmark cần dùng operation ID và xác minh outcome trước khi phân loại.

## 12. Loại truy vấn phải tách trong báo cáo

| Operation class | Điều cần xác định | Nhân tố chi phối |
|---|---|---|
| Primary-key point read | Hit/miss, projection, size, consistency | Network, cache, partition placement |
| Partition-key range read | Range length, clustering/order, page size | Số rows, scan bytes, tombstones |
| Secondary-index query | Index, selectivity, covered/projection | Index fan-out, fetch, sort |
| Full scan | Dataset size, filters, parallelism | I/O, CPU, partitions |
| Aggregation | Group/sort/join/lookup, spill | Memory, shuffle, query plan |
| Full-text search | Analyzers, terms, scoring, shards | Search index, candidate count |
| Vector KNN/ANN | Dimensionality, top-K, recall target | Index/search parameters, recall-latency |
| Graph traversal | Start node, hop count, fan-out | Index, graph degree, visited set |
| Counter update | Atomic increment vs client RMW | Contention, partition hotspot |
| Conditional write | CAS/LWT/transaction scope | Coordination, conflict rate |
| Batch/transaction | Batch size, read/write mix, durability | Coordination, failure handling |
| CDC consume | Events decoded/applied/checkpointed | Source shards, sink speed, retention |

**Một đường truy vấn được tối ưu không đại diện cho toàn bộ hệ NoSQL.**

## 13. Primary-key lookup và document size

Một benchmark `GET by id` cần ghi:

```text
Dataset: 10 million documents
Key distribution: uniform hoặc Zipfian
Document sizes: p50/p95/p99 bytes
Projection: full document hay vài fields
Cache: warm/cold
Read path: primary/replica/local region
```

Nếu dataset chỉ có 1.000 documents đều nằm trong RAM, kết quả không đại diện tải disk-heavy ở production.

### 13.1. Phân phối keys

- **Uniform:** xác suất truy cập các keys gần bằng nhau.
- **Zipfian/skewed:** một số keys nhận phần lớn requests.
- **Latest:** ưu tiên records mới được tạo.
- **Hotspot:** cố tình dồn tải vào một partition/key.
- **Sequential:** tạo hoặc đọc keys có thứ tự liên tục.

Từng phân phối ảnh hưởng cache hit ratio, partition contention và storage access.

### 13.2. Document size

Một GET trả 500 bytes khác GET trả 500 KiB: network, deserialization, heap allocations và GC khác nhau.

### 13.3. Projection

Nếu chỉ cần `status`, đo query trả full document 100 fields sẽ phóng đại chi phí API thật. Ngược lại, một benchmark chỉ lấy `_id` có thể làm chi phí nhỏ hơn thực tế.

## 14. Query, index và scan phải được tách riêng

Một query NoSQL:

```text
find orders where customerId=U42 and status=PAID
```

có thể dùng:

- Index khớp predicates;
- Partition key + clustering key;
- GSI;
- Search index;
- Full scan/filter;
- Fan-out qua nhiều shards.

### 14.1. Benchmark query tối ưu

Ghi index definition, cardinality, selectivity và explain/plan. Không chỉ ghi câu lệnh filter rồi đo.

### 14.2. Query không có index

Một full scan trả 10 kết quả có thể quét hàng triệu records. Độ trễ phụ thuộc dữ liệu đã đọc, không chỉ số results.

### 14.3. Pagination token và offset

Offset pagination sâu có thể tốn chi phí hơn keyset/continuation token; phải phân biệt `page 1` và `page 1.000`.

### 14.4. Explain khác benchmark

Execution plan cho biết hướng truy cập, không thay phép đo dưới tải thật. Một plan hợp lý vẫn có thể bị queueing hay hot partition.

## 15. Write workload cũng phải được phân loại

- `INSERT` key mới;
- `UPSERT` ghi đè key đã có;
- `UPDATE` vài fields;
- Full-document replacement;
- `DELETE` tạo tombstone/metadata xóa;
- Conditional insert/update;
- Atomic increment;
- Batch write;
- Transaction với nhiều items;
- Write gây secondary-index updates;
- Write có TTL;
- Write có CDC/outbox fan-out.

### 15.1. Upsert khác insert thuần

Nếu 50% keys đã tồn tại, index maintenance, update path và conflict behavior khác workload toàn inserts.

### 15.2. Delete không phải lúc nào cũng rẻ về dài hạn

Trong LSM NoSQL, tombstone, compaction và repair có thể tạo chi phí sau này. Benchmark chỉ 60 giây DELETE rồi dừng có thể chưa thấy hậu quả.

### 15.3. TTL

Các expirations có thể xảy ra sau tải ghi; disk/compaction behavior cần đo cả giai đoạn ổn định và cleanup.

### 15.4. Conditional conflict rate

Nếu 90% requests cố claim cùng key và fail, throughput “condition-check/s” khác throughput **successful claims/s**.

## 16. Batch, pipeline và transaction: đo cả hai mẫu số

Ví dụ:

```text
Batch size: 100 items
Batches completed: 300/s
Items successfully written: 29,500/s
Items rejected/failed: 500/s
```

Báo cả:

- 300 batch RPC/s;
- 29.500 successful item writes/s;
- batch latency p50/p95/p99;
- per-item failure rate;
- retry attempts;
- batch response bytes.

### 16.1. Batch lớn chưa chắc tốt nhất

Batch giúp giảm per-request overhead nhưng có thể tăng queueing, memory pressure, head-of-line blocking và latency cho những items cuối.

### 16.2. Transaction throughput

Một transaction 10 items thường có cost/coordination khác 10 independent item writes. Báo committed TPS và số items/transaction.

### 16.3. Partial success

Một số bulk APIs trả status từng item; không được xem HTTP 200 cho batch là mọi sub-operation thành công. Consumer phải kiểm tra nội dung response.

### 16.4. Retry amplification

Một item thất bại trong batch rồi batch được gửi lại toàn bộ có thể làm số **physical operations** tăng hơn **logical operations**.

## 17. Read/write mix và chu kỳ tải

Một workload 95% reads, 5% writes rất khác 50/50.

Ví dụ:

```text
Read  70% -> GET order by id
Write 20% -> UPDATE status with version
Scan   5% -> List orders by customer
Event  5% -> Read CDC event and index
```

Phải ghi rõ mẫu số: 70% theo **requests**, **items** hay **thời gian sử dụng CPU**?

### 17.1. Mixed workload có tác động chéo

Writes có thể đẩy cache, kích hoạt compaction và thay index; reads có thể tranh CPU/I/O với writes. Benchmark đọc riêng và ghi riêng không mô tả đầy đủ khi chạy đồng thời.

### 17.2. Background jobs

Repair, snapshot, index build, backup, TTL cleanup, CDC, replication và compaction có thể ăn tài nguyên. Thử nghiệm production-like nên ghi lịch những hoạt động này.

### 17.3. Tải theo thời gian

Các đợt peak, flash-sale, batch ETL lúc đêm và traffic trễ từ vùng khác tạo phân phối khác tải đều.

## 18. Average latency và nhược điểm của trung bình

Một ví dụ có 100 requests:

```text
99 requests: 10 ms
 1 request: 1.000 ms
```

Mean:

\[
\bar L=\frac{99\times10+1000}{100}=19{,}9\ \text{ms}
\]

Mean 19,9 ms trông ổn, nhưng một request đã chờ 1 giây.

### 18.1. Số trung bình che tail

Khi API có nhiều dependencies, một phần nhỏ chậm có thể gây timeout, trải nghiệm không ổn định hoặc queue buildup.

### 18.2. Mean vẫn hữu ích

Mean có ích cho mô hình chi phí và Little's Law nếu thống kê đúng population/window, nhưng **không thay p95/p99** cho SLO.

### 18.3. Min/max

Min có thể phản ánh cache hit hoàn hảo; max dễ bị ảnh hưởng bởi một outlier. Cần nhìn distribution và định nghĩa timeouts.

## 19. Percentiles p50, p90, p95, p99 và p99.9

Percentile \(p_q\) là một ngưỡng mà khoảng \(q\%\) observations không vượt quá, theo phương pháp tính quantile được nêu hoặc chọn nhất quán.

| Percentile | Cách hiểu gần đúng |
|---|---|
| p50 | 50% thao tác không chậm hơn ngưỡng này |
| p90 | 90% không chậm hơn |
| p95 | 95% không chậm hơn |
| p99 | 99% không chậm hơn |
| p99.9 | 99,9% không chậm hơn |

### 19.1. p99 không phải “request chậm nhất”

Trong 1.000.000 requests, khoảng 10.000 requests có thể nằm phía trên p99. Đó là một tập đủ lớn để ảnh hưởng người dùng.

### 19.2. p99 trên ít mẫu có thể không ổn định

Nếu chỉ có 100 observations, vùng 1% chậm nhất tương ứng khoảng một mẫu. Để ước lượng p99/p99.9 đáng tin cần đủ samples, thời gian quan sát và report uncertainty phù hợp.

### 19.3. Không tính p99 từ p99 của mỗi phút bằng cách lấy trung bình

Ví dụ:

```text
Minute 1: p99=20ms, 10.000 requests
Minute 2: p99=200ms, 100 requests
```

Trung bình hai p99 là 110 ms, **không phải p99 của cả cửa sổ**. Cần gộp histogram/distribution với counts đúng.

### 19.4. Histogram precision

Buckets quá thưa có thể ước lượng p99 sai. Chọn histogram/t-digest/HDRHistogram theo dải latency, dung lượng và độ chính xác yêu cầu.

## 20. Histogram và distribution

Một histogram mẫu:

```text
Latency bucket    Count
0–5 ms            4,000
5–10 ms           3,000
10–20 ms          1,500
20–50 ms          1,000
50–100 ms           400
>100 ms             100
Total             10,000
```

Histogram cho thấy có bao nhiêu requests nằm ở mỗi dải; hữu ích hơn một mean duy nhất.

### 20.1. Buckets cho SLO

Nếu mục tiêu là `p99 < 100 ms`, buckets nên có độ phân giải quanh 100 ms đủ để phân tích. Một histogram chỉ có bucket 0–1s không phân biệt 99 ms với 900 ms tốt.

### 20.2. High dynamic range

Một benchmark có latency từ 50 µs đến 30 s cần cấu trúc histogram phù hợp. HDRHistogram giúp lưu số đo nhiều bậc độ lớn với độ chính xác tương đối cấu hình; vẫn cần xác định cách đo/coordinated omission correction.

### 20.3. Không cộng percentiles

Percentiles không cộng tuyến tính và không thể suy p99 end-to-end từ tổng p99 các span.

### 20.4. Đếm timeouts bên cạnh histogram

Một request timeout ở 5 s là observation của request đã thất bại/không hoàn thành theo một quy tắc. Không tự drop nó khỏi biểu đồ và gọi p99 “đủ nhanh”.

## 21. SLO, SLI và error budget

**SLI** là chỉ số đo chất lượng, ví dụ:

```text
SLI: tỷ lệ GET Order hợp lệ hoàn tất trong 100 ms
     trong điều kiện và khoảng thời gian xác định.
```

**SLO** là mục tiêu:

```text
Trong cửa sổ 30 ngày, ít nhất 99% các GET Order
hợp lệ phải thành công trong 100 ms.
```

**Error budget** là lượng vi phạm được phép theo SLO.

### 21.1. Độ trễ và availability có thể là một mục tiêu chung

Một request trả lỗi 500 ngay trong 2 ms không nên được tính là “đạt latency SLO” nếu mục tiêu là **successful response under threshold**.

### 21.2. Khi đo NoSQL

Đặt SLI theo loại operation, ví dụ `GetOrderById`, `ReserveInventory`, `SearchProducts`. Không gộp 1 triệu cache hits với 100 payment-critical writes rồi suy hệ “đạt p99”.

### 21.3. SLO theo vùng và tenant

Một vùng xa data center hoặc tenant có hot partition có thể có p99 khác. Cần chỉ rõ SLO có theo region, AZ, tenant tier hay toàn hệ.

## 22. Offered load model: open-loop

**Open-loop** phát yêu cầu theo lịch/arrival process tương đối độc lập với việc những requests trước hoàn thành.

Ví dụ mục tiêu 1.000 req/s:

```text
T=0ms:     request A
T=1ms:     request B
T=2ms:     request C
...
```

Một request chậm không nhất thiết làm load generator ngừng phát những requests kế tiếp.

### 22.1. Ưu điểm

Mô phỏng traffic external có thể tiếp tục đến ngay cả khi hệ chậm; giúp thấy queue buildup và overload.

### 22.2. Cần kiểm soát generator

Nếu load generator không phát đúng lịch khi CPU bận, offered load thực tế có thể thấp hơn plan. Phải đo **scheduled vs actually issued arrivals**.

### 22.3. Arrival distribution

Constant-rate, Poisson arrival, bursty và replay từ production traces tạo queueing khác nhau dù mean RPS giống nhau.

### 22.4. Không tạo backlog vô hạn

Mô hình open-loop dưới tải cao cần queue caps, timeout và backpressure ở công cụ, đồng thời ghi rõ khi offered load không còn được duy trì.

## 23. Closed-loop: số client đồng thời cố định

**Closed-loop** có N workers, mỗi worker chờ request trước hoàn thành rồi mới phát request tiếp.

```text
Worker 1: request -> response -> request -> response
Worker 2: request -> response -> request -> response
...
Worker N: request -> response -> request -> response
```

### 23.1. Khi nào phù hợp?

- Một nhóm hữu hạn người dùng thực hiện request–think–request.
- Cần đánh giá tác động khi số clients/connections tăng.
- Workloads có tự nhiên một outstanding request cho mỗi client.

### 23.2. Nhược điểm khi dùng để đo overload

Khi server chậm, clients chờ lâu nên **tốc độ phát mới tự giảm**. Biểu đồ có thể cho cảm giác hệ chịu tải ổn hơn thực tế nếu production arrivals không dừng theo cách ấy.

### 23.3. Không gọi concurrency 100 là 100 RPS

100 requests đang in-flight là **mức đồng thời**, không phải số request mỗi giây.

## 24. Coordinated omission: lỗi thống kê nổi tiếng

**Coordinated omission** xảy ra khi load generator chỉ ghi latency của requests thực tế đã phát và ngừng phát trong lúc hệ bị chậm, làm **bỏ qua những requests lẽ ra đã đến** theo lịch tải.

Ví dụ lịch kỳ vọng 1.000 req/s, nhưng một worker bị block 1 giây:

```text
Expected:
  ~1.000 arrivals trong 1 giây

Actual closed-loop:
  worker chờ một request 1 giây,
  không phát những arrivals kế tiếp
```

Histogram từ những requests được gửi có thể **không thể hiện hết tác động của khoảng stall** lên tải theo lịch kỳ vọng.

### 24.1. Cách giảm

- Chọn open-loop khi muốn mô phỏng arrivals không phụ thuộc response.
- Ghi cả scheduled start và actual issue/start.
- Nếu dùng công cụ/histogram correction, chỉ hiệu chỉnh theo **mô hình expected interval hợp lệ**.
- Ghi source/generator saturation.
- Đừng dùng kết quả corrected và uncorrected như thể cùng một metric.

### 24.2. Không dùng correction bừa bãi

Một workload closed-loop thực sự có thể đại diện business behavior: người dùng chờ kết quả rồi mới thao tác. Áp correction open-loop không phù hợp có thể làm sai mô hình. Cần chọn workload model trước.

### 24.3. Test stall/fault

Chèn một pause có kiểm soát trong staging và quan sát histogram. Nếu p99 vẫn “đẹp” dù nhiều requests không được phát đúng lịch, cần xem lại generator/instrumentation.

## 25. Throughput, concurrency và Little's Law

Với một hệ **ổn định trong trạng thái phù hợp**:

\[
L=\lambda W
\]

Trong đó:

- \(L\): số công việc trung bình trong hệ (in-flight).
- \(\lambda\): tốc độ công việc hoàn thành/đến trong steady state, đơn vị operations/s.
- \(W\): thời gian trung bình mỗi công việc ở trong hệ, đơn vị giây.

Ví dụ:

\[
\lambda=5.000\ \text{ops/s},\quad W=0{,}04\ \text{s}
\]

thì:

\[
L=5.000\times0{,}04=200\ \text{in-flight operations}
\]

### 25.1. Dùng để làm gì?

- Ước lượng concurrency tương ứng throughput và mean latency.
- Kiểm tra xem số liệu có nhất quán về mặt đơn vị.
- Lập capacity cho pool/queue trong điều kiện ổn định.

### 25.2. Điều kiện sử dụng

Không áp dụng thẳng nếu backlog tăng mãi, requests bị drop, đo sai boundaries, hoặc lấy arrival rate một phía và response time phía khác.

### 25.3. Không thế p99 vào công thức mean

Little's Law dùng **mean system time**, không phải p99. Viết \(L=\lambda\times p99\) rồi gọi đó là kỳ vọng concurrency là sai.

### 25.4. Think time

Trong closed-loop với users có think time, số active users không đồng nghĩa số requests in-flight; mô hình interactive response time law cần tính think time riêng.

## 26. Đường cong bão hòa (saturation curve)

Một benchmark nên tăng tải từng mức, ví dụ:

```text
Offered RPS:  500  1000  2000  3000  4000  5000  6000
Goodput:      500  1000  2000  2990  3910  4200  4100
p99 ms:        12    15    22    35    85   400  1500
```

Số liệu giả định cho mục đích học.

Diễn giải:

- Giai đoạn đầu, goodput tăng gần tuyến tính.
- Khi tài nguyên chạm ngưỡng, p99 tăng nhanh.
- Ở 5.000–6.000 offered RPS, goodput gần như không tăng hoặc giảm.
- Latency/error rate phản ánh queue buildup và timeout.

### 26.1. “Max throughput” theo cách nào?

- Tốc độ hoàn thành cao nhất dù p99 1,5 s?
- Tốc độ cao nhất vẫn đạt p99 dưới 100 ms?
- Tốc độ cao nhất vẫn dưới 0,1% errors?
- Tốc độ sustained 30 phút không backlog tăng?

Cần định nghĩa **capacity threshold** theo SLO, không chỉ đỉnh của biểu đồ ops/s.

### 26.2. Knee point

Điểm mà tăng tải bắt đầu làm latency tăng mạnh so với throughput tăng thêm thường là vùng cảnh báo. Operating margin cần tính bursts, failover và growth.

## 27. Đo tail latency trong hệ có nhiều dependencies

Một HTTP request có thể thực hiện:

```text
1. Redis GET
2. MongoDB GET
3. DynamoDB conditional UPDATE
4. Publish event
```

Nếu làm tuần tự, latency có thể tích lũy. Nếu làm song song, completion phụ thuộc bước lâu nhất hoặc critical path.

### 27.1. Fan-out

Một request gọi 20 shards song song, chỉ cần một shard chậm là toàn request chậm nếu phải chờ tất cả.

Nếu mỗi shard có xác suất độc lập \(1\%\) vượt một ngưỡng, xác suất **ít nhất một** trong 20 shards vượt ngưỡng theo mô hình đơn giản:

\[
P(\text{ít nhất một chậm})=1-(0{,}99)^{20}\approx18{,}2\%
\]

Phép tính minh họa giả định độc lập; các shards thực tế có thể có correlated failures.

### 27.2. Ghi fan-out size

Một query fan-out tới 2 shards khác query fan-out tới 200 shards. Không so p99 khi một phía đã đổi số shards tham gia.

### 27.3. Hedged requests

Phát thêm read song song tới replica khác có thể giảm tail trong một số mô hình, nhưng tăng load và phải tuân thủ read consistency. Benchmark ghi rõ policy nếu bật.

## 28. Cache hit ratio ảnh hưởng latency và throughput

Một API cache-aside gồm hai đường:

```text
Cache HIT:
  Redis GET -> return

Cache MISS:
  Redis GET -> NoSQL GET -> cache SET -> return
```

Nếu 90% reads hit cache, p50 chủ yếu phản ánh Redis; database có thể chỉ phục vụ 10% requests. Gọi kết quả đó là “MongoDB GET p50” là sai.

### 28.1. Báo tách

- `cache_hit_rate`.
- `cache_hit_latency`.
- `cache_miss_end_to_end_latency`.
- `source_db_read_latency`.
- `api_end_to_end_latency`.
- Source QPS và cache QPS.

### 28.2. Cold cache và warm cache

Một benchmark warm cache tốt không mô tả cold start/failover, khi toàn bộ requests quay về database.

### 28.3. Cache warming

Nếu pre-load 100.000 hot keys, ghi rõ quá trình warmup và số data trong cache. Hai môi trường khác cache sizes sẽ không công bằng.

### 28.4. TTL/invalidation

Update-driven cache invalidation và TTL hết hàng loạt có thể tạo stampede. Nên có test expiration burst riêng.

## 29. Read consistency và write durability là biến workload

NoSQL thường cho chọn những mức đọc/ghi khác nhau. Ví dụ:

- MongoDB read preference/read concern, write concern.
- Cassandra `ONE`, `QUORUM`, `LOCAL_QUORUM`, LWT/serial consistency.
- DynamoDB eventually/strongly consistent read theo API, transactional operations, multi-region mode.
- Redis persistence/replication ACK semantics.
- Cosmos DB consistency levels và region topology.
- Firestore transaction/strong consistency với scope và client mode phù hợp.

### 29.1. Không so read `ONE` với read `QUORUM` như cùng operation

Một đường đọc có ít coordination hơn có thể nhanh hơn nhưng đem lại guarantee khác. Đó là hai workload khác nhau.

### 29.2. Không so write ACK local với majority durable write

Một phép đo write 2 ms chỉ chờ primary local khác phép đo 10 ms chờ majority commit. Nếu yêu cầu durability là majority, đường 2 ms không phải ứng viên tương đương.

### 29.3. Staleness cần đo riêng

Đọc nhanh nhưng trả version cũ không tự là “tốt hơn”. Có thể đo:

```text
sourceVersion
readVersion
ageOfData
percentageStale
maxStalenessObserved
```

### 29.4. Invariant quan trọng

Một read nhanh ở cache không có quyền xác nhận ghế cuối cùng. Capacity planning cho `ReserveSeat` phải đo authoritative conditional claim, không dùng GET cache hit làm đại diện.

## 30. Replication, quorum và địa lý

Một NoSQL cluster ba replicas trong cùng AZ khác cụm trải ba AZ hoặc nhiều regions.

### 30.1. Network RTT

Các RPC liên vùng tăng latency floor khi cần đợi remote acknowledgements. Benchmark phải ghi vùng của load generator và data replicas.

### 30.2. Quorum và failover

Khi một replica chậm/down, driver có thể route lại hoặc consensus election xảy ra. Cần đo cả steady-state và fault/recovery windows.

### 30.3. Read locality

Đọc replica gần client có thể giảm RTT nhưng có thể stale hoặc thuộc consistency mode khác. Report read path.

### 30.4. Không suy cluster một node đại diện production

Single-node benchmark hữu ích cho baseline storage/CPU, nhưng không bao gồm replication, quorum, failover và cross-node fan-out. Không dùng để cam kết production SLA của distributed cluster.

## 31. Data shape và size distribution

Một dataset thực tế thường không đồng nhất.

Ví dụ:

```text
Order document p50 size:   2 KiB
Order document p95 size:  10 KiB
Order document p99 size: 100 KiB
```

Nếu benchmark chỉ tạo 1 KiB fixed-size documents, serialization/network/GC và query plans có thể khác production.

### 31.1. Số lượng records

Dataset nên đủ lớn để kích hoạt storage/index/cache behavior mục tiêu. Nếu production có 500 triệu records mà benchmark có 10.000, kết quả có thể quá lạc quan.

### 31.2. Index cardinality

Các fields như `tenantId`, `status`, `createdAt` có selectivity khác nhau. Query `status=PAID` có thể trả phần lớn records; query `orderId=O100` có thể trả một record.

### 31.3. Tombstones và TTL

LSM stores có thể có nhiều tombstones sau churn; benchmark clean dataset khác cluster sau 12 tháng deletes/TTLs.

### 31.4. Compression và data entropy

Payload toàn ký tự `A` thường nén tốt hơn JSON ngẫu nhiên thực tế. Dataset generator cần phản ánh entropy/compressibility phù hợp.

## 32. Hot key, hot partition và multi-tenant workload

NoSQL phân phối dữ liệu theo partition key/token/shard. Tải không đều có thể khiến một shard bão hòa dù cluster còn CPU.

Ví dụ:

```text
Tenant A: 70% requests -> Partition P1
Tenant B/C/D: 30% requests -> các partitions khác
```

### 32.1. Báo phân phối

- QPS theo key/partition/tenant.
- Top N hot keys.
- Hot partition CPU/queue time.
- Size và growth của partitions.
- Split/rebalance behavior.

### 32.2. Uniform benchmark có thể che hotspot

Nếu benchmark luôn chọn keys ngẫu nhiên đều nhưng production có 20% products cực nóng, tail latency thực sẽ khác.

### 32.3. Query fan-out và skew

Một phân tích query qua nhiều partitions có thể chờ shard chậm nhất; cần phân biệt average node utilization với hotspot.

### 32.4. Fairness

Tăng tải tenant A có làm p99 tenant B xấu đi không? Nhiều hệ cần workload isolation và per-tenant SLO thay vì chỉ báo average cluster throughput.

## 33. LSM, compaction, page cache và hiệu năng dài hạn

Một số NoSQL dùng LSM storage engine (ví dụ hệ theo họ Cassandra/RocksDB) trong khi hệ khác có kiến trúc khác. Khi benchmark cần xem xét:

- Memtable/write buffer.
- WAL/commit log persistence.
- Flush.
- Compaction.
- Bloom filters.
- Tombstone cleanup.
- Read amplification.
- Write amplification.
- SSD IOPS/bandwidth.
- OS page cache.
- Disk fullness.

### 33.1. Write amplification

Một write logic có thể tạo nhiều bytes ghi vật lý do WAL, replication, index maintenance và compaction. `5.000 writes/s` không mô tả tổng disk I/O.

### 33.2. Read amplification

Một point lookup có thể cần tra nhiều cấu trúc/index segments; tombstones và cache misses tăng chi phí.

### 33.3. Đo đủ lâu

Benchmark 2 phút trên dữ liệu sạch có thể chỉ đo memory buffer. Chạy sustained test đủ để flush/compaction/GC/TTL diễn ra nếu muốn đánh giá long-run capacity.

### 33.4. Disk age

SSD wear, fullness, background rebuild và storage volume burst credits (nếu cloud provider có cơ chế ấy) ảnh hưởng kết quả. Ghi cấu hình hạ tầng.

## 34. Java-specific overhead khi benchmark NoSQL

Ứng dụng Java tạo tải và xử lý kết quả có thêm:

- JIT compilation/warmup.
- Garbage collection.
- Heap size.
- Thread scheduling.
- Connection pooling.
- BSON/JSON serialization.
- Object mapping (Spring Data/driver codec).
- TLS.
- Logging/tracing.
- Allocation pressure.

### 34.1. Warmup JVM

Chạy một lần ngắn rồi báo p50 dễ phản ánh class loading/JIT. Có giai đoạn warmup riêng, nhưng không dùng warmup để che cost cold start nếu đó là yêu cầu sản phẩm.

### 34.2. GC pauses

Một p99 spike có thể do GC pause ở load generator hoặc Java app, không phải NoSQL server. Thu thập JVM metrics hoặc GC logs khi cần.

### 34.3. JSON conversion

Một DAO trả `Document` khác DAO map thành nested POJO. Để so database engines, cần cố định conversion overhead hoặc đo riêng driver-level và service-level.

### 34.4. Logging

Log mỗi request trong benchmark có thể làm disk/CPU của load generator bottleneck. Nhưng tắt mọi logging/tracing cũng có thể làm thử nghiệm khác cấu hình production; ghi mức sampling.

## 35. Java: đo duration bằng `System.nanoTime()`

Trong Java, `System.nanoTime()` phù hợp để đo **khoảng thời gian trôi qua** trong cùng JVM:

```java
long started = System.nanoTime();

try {
    Order result = orderRepository.getById("O100");
    // kiểm tra result theo business contract
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // ghi measurement, bao gồm cả path ném exception
}
```

### 35.1. Không dùng `currentTimeMillis()` để đo duration ngắn

Wall-clock time có thể bị điều chỉnh. `nanoTime()` là monotonic-style elapsed time source cho cùng JVM, không có ý nghĩa absolute epoch.

### 35.2. Không so nanoTime của hai tiến trình

Giá trị `System.nanoTime()` ở JVM A và JVM B không có origin chung đáng tin để trừ trực tiếp.

### 35.3. Phải ghi cả lỗi

Nếu code chỉ đo sau khi method trả thành công, exceptions sẽ biến mất khỏi latency sampling. Dùng `finally` và outcome classification.

### 35.4. Không in console mỗi operation

`System.out.println` trong hot path có thể làm sai kết quả. Dùng histogram/counters hoặc sampling được thiết kế trước.

## 36. Java: ví dụ collector cho latency và outcome

Ví dụ Java 17 độc lập thư viện NoSQL, đo một call trong JVM. Nó minh họa **measurement boundary**, không là một benchmark production hoàn chỉnh:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.LongAdder;

public final class OperationMeter {

    private final LongAdder success = new LongAdder();
    private final LongAdder failure = new LongAdder();
    private final LongAdder totalDurationNanos = new LongAdder();

    public <T> T measure(
            String operationName,
            Callable<T> action
    ) throws Exception {
        long begin = System.nanoTime();
        boolean succeeded = false;

        try {
            T value = action.call();
            succeeded = true;
            return value;
        } finally {
            long elapsed = System.nanoTime() - begin;
            totalDurationNanos.add(elapsed);

            if (succeeded) {
                success.increment();
            } else {
                failure.increment();
            }

            // operationName phải là low-cardinality label.
            // Production: ghi vào histogram + counter;
            // không tạo một time series cho mỗi orderId.
        }
    }

    public long successes() { return success.sum(); }
    public long failures()  { return failure.sum(); }
    public long totalNanos() {
        return totalDurationNanos.sum();
    }
}
```

Sử dụng:

```java
OperationMeter meter = new OperationMeter();

Order order = meter.measure(
        "get-order-by-id",
        () -> repository.getById("O100")
);
```

### 36.1. Những giới hạn của ví dụ

- Không ghi histogram/percentiles.
- Không phân biệt timeout, conflict, not-found hay lỗi hạ tầng.
- `success` chỉ có nghĩa callable không ném exception; nghiệp vụ có thể cần kiểm tra nội dung result.
- Không tính offered load/scheduled time.
- Không hỗ trợ distributed tracing/correlation.
- `LongAdder.sum()` không là snapshot atomic đồng bộ khi đang có concurrent updates.

Với production/benchmark nghiêm túc, dùng metrics library/histogram thích hợp và ghi outcome với định nghĩa chính xác.

## 37. Java: Micrometer Timer và labels

Trong Spring Boot, Micrometer thường được dùng để xuất latency histogram/counters tới hệ metrics phù hợp.

Ví dụ minh họa:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;

public final class OrderReadMetrics {

    private final MeterRegistry registry;
    private final OrderRepository repository;

    public OrderReadMetrics(
            MeterRegistry registry,
            OrderRepository repository
    ) {
        this.registry = registry;
        this.repository = repository;
    }

    public Order getById(String id) throws Exception {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return repository.getById(id);
        } catch (Exception e) {
            outcome = "error";
            throw e;
        } finally {
            sample.stop(
                    Timer.builder("nosql.operation.latency")
                            .tag("operation", "getOrderById")
                            .tag("outcome", outcome)
                            .publishPercentileHistogram()
                            .register(registry)
            );
        }
    }

    public interface OrderRepository {
        Order getById(String id) throws Exception;
    }

    public record Order(String id, String status) {}
}
```

### 37.1. Label cardinality

Không gắn `orderId`, `userId`, raw SQL/CQL hay random request ID thành metric tags. Số lượng time series có thể bùng nổ.

### 37.2. Timer boundary

Timer đo **từ trước repository call tới khi return/throw**, gồm mapping/driver retries xảy ra bên trong call. Nó không tự đo HTTP queue time.

### 37.3. Percentiles ở backend

Tùy Prometheus/OTel/backend, histogram, summary và percentile aggregation khác nhau. Cần thống nhất buckets, registry config và query; không gộp p99 gauges như trung bình.

### 37.4. Outcome tag

Ví dụ chỉ có `success/error`, nhưng benchmark thực cần thêm `timeout`, `condition_failed`, `not_found`, `canceled` theo số nhóm hữu hạn.

## 38. Java load generator: đóng vòng và nguy cơ đo sai

Một cách tạo concurrency đơn giản:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class ClosedLoopLoadExample {
    public static void run(
            int workers,
            int operationsPerWorker,
            Runnable operation
    ) throws InterruptedException {
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);

        for (int i = 0; i < workers; i++) {
            pool.submit(() -> {
                for (int n = 0; n < operationsPerWorker; n++) {
                    operation.run();
                }
            });
        }

        pool.shutdown();
        if (!pool.awaitTermination(10, TimeUnit.MINUTES)) {
            pool.shutdownNow();
            throw new IllegalStateException(
                    "Load run did not finish"
            );
        }
    }
}
```

### 38.1. Đây là closed-loop

Mỗi worker đợi `operation.run()` xong mới chạy lần tiếp. Khi DB chậm, offered load giảm. Không dùng ví dụ này để tự kết luận hệ chịu được 10.000 arrivals/s độc lập.

### 38.2. Chưa ghi failures/latency đầy đủ

`submit` giữ exceptions bên trong `Future` nếu không gọi `get`; code minh họa không thu hồi `Future`s. Trong benchmark thật phải lấy outcomes của từng task, ghi histogram và verify completion.

### 38.3. Generator có giới hạn

100 threads không nghĩa 100 concurrent database connections nếu pool thấp. Ngược lại, 100 threads có thể làm load generator CPU/GC bottleneck.

### 38.4. Đo đúng thời gian

Một run phải có barrier bắt đầu, warmup, measurement window và flush metrics; không chỉ đo từ lúc tạo pool tới lúc JVM dừng nếu đang đo server throughput.

## 39. Công cụ đo tải: chọn theo tầng

| Công cụ/nhóm | Phù hợp | Không tự giải quyết |
|---|---|---|
| YCSB | Workloads NoSQL theo key-value/read/update/scan, bindings tương thích | Domain transaction, mọi feature NoSQL, network/application SLO |
| k6/JMeter/Gatling | HTTP API và hành vi user/arrival | Native DB time nếu không có instrumentation |
| Custom Java driver benchmark | Một API/feature đặc thù | Correct load model/histogram nếu tự viết thiếu |
| JMH | Microbenchmark Java code/serialization/mapper | Thông lượng production của distributed database |
| Prometheus/Micrometer/OpenTelemetry | Metrics/traces vận hành | Tạo tải, correctness, workload reproducibility |
| Database native profiler/metrics | Server execution/index/storage | End-to-end user latency |
| Linux/OS profiling | CPU, disk, network, scheduler | Business operation semantics |

### 39.1. YCSB

YCSB có các kiểu thao tác như read/update/insert/scan theo workloads và database bindings. Cần kiểm tra version binding, cấu hình thread count, operation count, field size, request distribution và batching. Không coi benchmark mặc định là đại diện mọi query chuyên biệt.

### 39.2. JMH

JMH có warmup/fork/blackhole để microbenchmark code. Nó tốt để so BSON codec/JSON mapping nội bộ, nhưng networked NoSQL chịu queueing, replication, compaction và failover; chỉ benchmark một method local không thể suy cluster TPS.

### 39.3. HTTP load tests

Đo user-facing checkout/search/get profile nên phát HTTP traffic qua đường thật (gateway, auth, cache) và kết hợp tracing để tách DB span.

### 39.4. Native database benchmark

Khi so engines hoặc driver semantics, đo trực tiếp DB API để giảm app noise nhưng vẫn ghi network/driver overhead.

## 40. Một workload matrix có thể tái lập

Thiết kế ma trận thay vì một con số duy nhất:

| Case | Operation | Payload | Keys | Consistency | Offered load |
|---|---|---|---|---|---|
| R1 | GetById | 2 KiB | Uniform | mode A | 1k/3k/5k RPS |
| R2 | GetById | 2 KiB | Zipfian | mode A | 1k/3k/5k |
| R3 | GetById | 32 KiB | Zipfian | mode A | 1k/3k |
| Q1 | QueryByCustomer | 100 rows/page | Skewed | mode A | 500/1k |
| W1 | UpdateStatusCAS | 2 fields | Uniform | durable mode B | 500/1k/2k |
| W2 | ReserveHotInventory | 1 item | Hot key | conditional/serial | 100/500 |
| B1 | BatchUpsert | 100 items | Uniform | mode B | 100/300 batches/s |
| T1 | MultiItemTransaction | 3 items | Partitioned | transaction mode | 200/500 TPS |
| S1 | Search top-K | 20 results | Realistic vectors | specified quality | 100/300 RPS |
| C1 | CDC to sink | 2 KiB events | 16 shards | at-least-once | 5k/10k eps |

Các giá trị chỉ minh họa. Các chế độ A/B phải được thay bằng cấu hình cụ thể trước khi chạy.

### 40.1. Một lần chỉ thay biến quan trọng

Muốn đánh giá ảnh hưởng payload, giữ các yếu tố khác gần như cố định. Muốn đánh giá concurrency, dùng cùng dataset/query distribution.

### 40.2. Random seed

Ghi seed của generator để tái lập key selection, nhưng nhớ production variability vẫn cần nhiều runs.

### 40.3. Workload scale

Chạy từ baseline thấp tới điểm SLO fail, không chỉ một mức quá tải rồi không biết tại sao.

## 41. Các pha của phép đo tải

Một bài đo nên có các pha:

```text
Provision/prepare data
       |
       v
Validate query/index/configuration
       |
       v
Warmup JVM, pools, caches/storage
       |
       v
Ramp up offered load
       |
       v
Sustained measurement window
       |
       v
Steady-state / compaction observation
       |
       v
Ramp down and drain
       |
       v
Reconcile success/error/pending
       |
       v
Archive report/config/metrics
```

### 41.1. Warmup

Không lẫn warmup với measurement window trừ khi cold-start behavior là mục tiêu chính.

### 41.2. Steady-state

Throughput, backlog, memory và disk usage nên tương đối ổn định. Nếu queue tăng mãi, throughput ngắn hạn có thể đánh lừa.

### 41.3. Cooldown/drain

Sau khi ngừng phát tải, vẫn có requests đang pending. Đếm chúng và outcome cuối; không biến chúng thành “không tồn tại”.

### 41.4. Recovery/failover

Một bài riêng cần đo thời gian trở về SLO sau khi mất node/region, chứ không trộn sự cố không chủ ý vào run baseline mà không ghi.

## 42. Load generator cũng cần được đo

Một load generator chậm có thể khiến server trông rất khỏe.

### 42.1. Metrics phía generator

- CPU/memory/GC.
- Scheduled arrivals.
- Actual issued requests.
- Failed-to-schedule count.
- Active tasks/queue length.
- Outgoing bandwidth.
- Connection errors.
- DNS/TLS setup.
- Local histogram throughput.
- Timestamp precision.

### 42.2. Phát tải từ nhiều máy

Nếu một generator không đủ CPU/network, phân phối tải nhưng phải đồng bộ định nghĩa measurement window và tổng hợp histogram đúng. Đồng hồ không đồng bộ gây lỗi khi so cross-node timestamps.

### 42.3. Co-located generator

Không chạy benchmark quá tải trên cùng node với database trừ khi mục tiêu cố tình đo chung contention. Thường nên tách tài nguyên để không làm nghẽn CPU/disk của source.

### 42.4. Load generator success

Thành công là phát được load theo lịch và ghi kết quả đúng, không chỉ “script chạy không lỗi”.

## 43. Retry và timeout làm thay đổi phép đo

Giả sử 1.000 logical API requests mỗi giây, 10% phải retry một lần.

```text
Logical requests:   1,000/s
Physical attempts:  1,100/s
```

Nếu một số requests retry hai lần, amplification tăng hơn nữa. Công thức:

\[
A_{\text{retry}}=
\frac{N_{\text{physical attempts}}}
{N_{\text{logical requests}}}
\]

### 43.1. Đo theo hai tầng

- End-to-end logical request latency: bắt đầu đến business outcome cuối.
- Per-attempt latency: thời gian của mỗi driver/broker attempt.

Một logical request có thể gồm nhiều attempts và backoff.

### 43.2. Bỏ failed attempts làm đẹp biểu đồ giả

Nếu attempt đầu timeout 200 ms và retry thành công 10 ms, báo `latency=10ms` bỏ qua 200 ms người dùng phải chờ là sai cho end-to-end SLO.

### 43.3. Timeouts và canceled writes

Timeout có thể xảy ra sau source commit. Không tự tạo command mới với ID mới khi benchmark business writes có side effects.

### 43.4. Retry storm

Tăng load làm timeout, retry làm physical load tăng, gây thêm timeout. Cần đo retry rate và ứng xử dưới overload, không chỉ tăng thread count.

## 44. Lỗi và outcomes phải được phân loại

Một bảng kết quả có thể tách:

| Outcome | Ví dụ | Cách báo |
|---|---|---|
| Success | GET trả đúng dữ liệu theo hợp đồng | Successful goodput + latency |
| Valid miss | Key không tồn tại và expected | Separate hit/miss rates |
| Business conflict | CAS version mismatch, seat taken | Conflict rate, latency riêng |
| Throttled | 429/provisioned limit | Throttle rate, retry cost |
| Timeout | Deadline vượt | Timeout rate, unknown outcome nếu write |
| Server error | 5xx, unavailable | Error rate, recovery |
| Client error | Invalid request/schema | Exclude from capacity conclusions nếu workload sai; vẫn báo |
| Canceled | Client abort | Count/latency policy |
| Stale/incorrect | Response trái consistency/business contract | Correctness violation |
| Pending | Workflow accepted nhưng chưa hoàn tất | Queue age, completion latency |

### 44.1. Không gộp conflicts vào failures mơ hồ

Một hệ inventory có nhiều khách tranh một ghế có thể từ chối 99 claims đúng cách. Đó là hành vi business hợp lệ, nhưng không phải 99 successful reservations.

### 44.2. Unknown write outcome

Nếu client timeout, cần đối soát bằng idempotency key/trạng thái authoritative trước khi tuyên bố failed/succeeded.

### 44.3. Response verification

Một benchmark chỉ kiểm tra HTTP 200 mà không kiểm tra JSON/result correctness có thể đánh giá cao hệ trả dữ liệu trống/sai.

## 45. CDC và read-model freshness: độ trễ khác API latency

Một write vào MongoDB có thể commit ở T0, change stream nhận T1, broker publish T2, search index apply T3, search query thấy T4.

```text
T0 Source commit
   |
T1 CDC capture
   |
T2 Broker publish
   |
T3 Sink apply
   |
T4 Search visible
```

Có ít nhất:

- **Capture lag:** T1 − T0.
- **Publish lag:** T2 − T1.
- **Sink apply lag:** T3 − T2.
- **Visibility lag:** T4 − T3.
- **End-to-end freshness lag:** T4 − T0.

### 45.1. `event/s` khác `business operation/s`

Một Order update có thể phát nhiều changes/events. CDC throughput 10.000 events/s không tương đương 10.000 checkout/s.

### 45.2. Lag backlog

Khi source tạo 20k events/s nhưng sink xử lý 15k/s, backlog tăng. Short burst throughput có thể đẹp nhưng freshness SLO sẽ xấu.

### 45.3. Checkpoint không bằng visible

Consumer checkpoint event đã được gửi tới search service có thể xảy ra trước khi search query thấy record nếu refresh asynchronous.

### 45.4. Đo correct freshness

Dùng source version/timestamp theo contract, event IDs và kiểm chứng read model để đo độ trễ người dùng thực sự quan sát được.

## 46. NoSQL cost efficiency: throughput trên tài nguyên

Bên cạnh ops/s và latency, capacity planning cần chi phí:

\[
\text{Cost per million successful operations}
=\frac{\text{Cost over window}}
{N_{\text{successful operations}}/10^6}
\]

Phải nêu chi phí gồm:

- Compute/database nodes.
- Storage và IOPS.
- Cross-AZ/region data transfer.
- Managed request/capacity charges.
- Replicas/backups.
- Cache.
- Logging/metrics.
- CDC/broker.
- Load generation nếu muốn tính full test cost.

### 46.1. So sánh công bằng

Một hệ có p99=10ms nhờ 20 nodes có thể đắt hơn hệ p99=20ms nhờ 3 nodes, trong khi cả hai đáp ứng SLO 50ms.

### 46.2. Khả năng mở rộng

Đo performance khi tăng cluster từ N lên 2N, nhưng ghi throughput tăng bao nhiêu, p99 thay đổi thế nào, hot partitions còn không, rebalancing cost ra sao.

### 46.3. Không đánh giá chỉ ops/s/node

Nodes khác CPU/RAM/SSD hoặc managed capacity config thì ops/s/node không phải mẫu số công bằng. Ghi hardware specs và cost/time.

## 47. Benchmark trong điều kiện lỗi và suy giảm

Một hệ phân tán có thể đạt SLO khi khỏe nhưng suy giảm mạnh khi:

- Replica/node crash.
- Leader election.
- Network partition.
- Rolling upgrade.
- Snapshot/backup.
- Compaction peak.
- Cache restart.
- Storage I/O throttling.
- Region failover.
- CDC connector restart.

### 47.1. Đo recovery metrics

- Time to detect outage.
- Unavailability window.
- Data loss hoặc unknown outcomes nếu có.
- p99 trong và sau fault.
- Backlog/queue drain time.
- Recovered goodput.
- Staleness/freshness lag.

### 47.2. Không trộn “healthy baseline” và “fault test”

Hai runs có mục đích khác; report riêng kèm timeline sự cố.

### 47.3. Không chạy destructive chaos trên production không được phép

Dùng staging hoặc runbook được phê duyệt, dữ liệu giả, kiểm soát blast radius và rollback.

## 48. Ví dụ báo cáo benchmark chi tiết

Một báo cáo cho `GetOrderById` có thể trình bày:

```text
Workload:
  GET Order by primary key; 2 KiB payload
  12 million orders; 80% hot keys / 20% cold keys
  3-node replica set; read from primary
  4,000 offered requests/s; open-loop
  Warmup 5 min, measure 20 min
  Java driver synchronous; pool max 200
  No application cache

Outcomes:
  Scheduled: 4,800,000 requests
  Completed successful: 4,776,000
  Timeout: 12,000
  Other errors: 12,000

Latencies for successful responses:
  p50: 8 ms
  p95: 26 ms
  p99: 71 ms
  p99.9: 180 ms

Other:
  Successful goodput: 3,980 ops/s
  Timeout rate: 0.25% of scheduled
  Error rate: 0.25% of scheduled
  Retries: disabled for benchmark
  Client CPU peak: 55%
  Server CPU peak: 68%
  Oldest request backlog: 0 during steady state
```

Các số giả định nhưng nhất quán: `4,000 × 1,200s = 4,800,000` scheduled; `4,776,000 / 1,200 = 3,980` successful ops/s. Nếu pending requests còn sau window, report phải tính và giải thích riêng.

### 48.1. Không trộn mẫu latency

Bảng trên ghi rõ percentiles cho **successful responses** và timeouts/errors riêng. Có thể thêm SLI “successful within 100ms / total scheduled” để tránh percentiles success-only che availability.

### 48.2. Câu hỏi còn phải hỏi

- Data volume vượt RAM chưa?
- Cache hit rate của DB page cache thế nào?
- Có compaction/GC spikes không?
- Một request có được xác minh nội dung không?
- Các percentile tính bằng cách nào?
- RPS có giữ đều theo thời gian không?
- Có retry do driver mặc định không?
- Read staleness theo primary read contract có phù hợp không?

## 49. Phân tích một kết quả benchmark sai

Giả sử hai thử nghiệm:

```text
Test A:
  50 threads closed-loop
  20,000 ops/s completed
  p99=30ms
  1 KiB keys hot in RAM
  cache enabled
  relaxed read consistency

Test B:
  5,000 req/s open-loop
  4,900 success/s
  p99=80ms
  100 KiB documents mixed hot/cold
  cache disabled
  stronger read consistency
```

Không thể kết luận A “nhanh gấp bốn lần” B vì:

1. Khác load model.
2. Khác payload.
3. Khác dataset/cache.
4. Khác consistency.
5. Khác kiểu tác vụ.
6. Khác offered load và concurrency.
7. Percentiles có thể khác sampling/outcome policy.

### 49.1. So sánh đúng

Giữ cùng operation, size, keys, consistency, result correctness, load shape, measurement boundary, duration và môi trường tương đương; đo nhiều mức tải.

### 49.2. Tùy mục tiêu

Nếu cần chọn hạ tầng cho ứng dụng thực, so **end-to-end SLO + cost**. Nếu muốn đo engine storage internals, tách ứng dụng và mapper overhead.

## 50. Những sai lầm thường gặp

**“Thông lượng là số request đã gửi.”** Không. Phải tách offered load, completed throughput và goodput.

**“p99 chính là request chậm nhất.”** Không; còn khoảng 1% observations phía trên.

**“Mean thấp nghĩa mọi user đều nhanh.”** Không; tail có thể rất cao.

**“p99 của tổng hệ bằng tổng p99 của các service.”** Không.

**“Lấy trung bình p99 từng phút ra p99 cả ngày.”** Không.

**“Không đo timeout vì không có response time.”** Sai cho SLO; cần timeout/error metrics.

**“Query trả 1000 rows là 1000 queries.”** Không, tùy mẫu số đã định nghĩa.

**“Một batch 100 items là một item write.”** Không; cần cả RPC/s và item/s.

**“Một transaction gồm 10 commands là 10 transactions.”** Không.

**“Driver call 5ms nghĩa browser request 5ms.”** Không; scope khác.

**“Database server execution 2ms nghĩa connection pool không nghẽn.”** Không.

**“50 concurrent threads nghĩa 50 requests/s.”** Không.

**“Closed-loop luôn đo overload chính xác.”** Không; có thể coordinated omission.

**“Open-loop đúng tốc độ chỉ vì script đặt rate=1000.”** Không; cần đo issued/scheduled arrivals.

**“Cache hit p50 là database p50.”** Không.

**“Read `ONE` và read `QUORUM` so được như cùng operation.”** Không nếu contract khác.

**“Write ACK local và majority-durable write giống nhau.”** Không.

**“Một key GET trên dataset 10k records đại diện cluster tỷ records.”** Không chắc.

**“Không thấy compaction trong 2 phút thì nó không ảnh hưởng throughput.”** Không.

**“Tăng batch size vô hạn sẽ tăng throughput.”** Không; memory, latency, partial failures có giới hạn.

**“Retry không ảnh hưởng load.”** Không; physical attempts có thể cao hơn logical traffic.

**“HTTP 200 là thành công nghiệp vụ.”** Chưa chắc; kiểm tra nội dung/invariants.

**“CDC event/s là checkout/s.”** Không; một nghiệp vụ có thể phát nhiều events.

**“Thêm 10 nodes là tăng 10 lần performance.”** Không nếu hot partition/single leader/sink là bottleneck.

**“Benchmarks ở localhost đại diện multi-region.”** Không; network/quorum khác.

**“Khi quá tải, p99 success-only vẫn thấp nên ổn.”** Không nếu phần lớn requests timeout/drop.

## 51. Bài tập thực hành

### Bài tập 1 — Throughput cơ bản

6.000 thao tác thành công trong 2 giây.

**Câu hỏi:** Goodput?

**Gợi ý:** 3.000 ops/s.

### Bài tập 2 — Offered vs achieved

Load generator phát 10.000 requests trong 1 giây, server hoàn tất 7.000, trong đó 6.500 thành công.

**Câu hỏi:** Offered load, completed throughput, goodput?

**Gợi ý:** 10.000 req/s, 7.000 completions/s, 6.500 successes/s trong cửa sổ giả định.

### Bài tập 3 — Mean latency

99 requests mất 10ms và một request mất 1000ms.

**Câu hỏi:** Mean?

**Gợi ý:** 19,9 ms.

### Bài tập 4 — p99

Hệ xử lý 1 triệu requests.

**Câu hỏi:** Khoảng bao nhiêu requests có thể nằm trên p99?

**Gợi ý:** Khoảng 10.000 (tùy định nghĩa quantile và tie).

### Bài tập 5 — Little's Law

Goodput ổn định 5.000/s, mean response 40ms.

**Câu hỏi:** Mean in-flight operations?

**Gợi ý:** Khoảng 200.

### Bài tập 6 — Không dùng p99 cho Little

Throughput 2.000/s, p99 100ms.

**Câu hỏi:** Có thể suy mean concurrency bằng 200 không?

**Gợi ý:** Không; phải có mean response time và điều kiện ổn định.

### Bài tập 7 — Driver vs server

Client thấy 50ms, server execution 5ms.

**Câu hỏi:** Còn những thành phần nào cần đo?

**Gợi ý:** Pool wait, network, queue, serialize/decode, retry.

### Bài tập 8 — Batch

200 batches/s, mỗi batch 100 items, 5% items thất bại.

**Câu hỏi:** Successful item writes/s lý tưởng?

**Gợi ý:** 19.000 items/s, nếu 5% tính trên 20.000 attempted items/s.

### Bài tập 9 — Transaction

500 transactions/s, mỗi transaction có 3 writes.

**Câu hỏi:** Đây là 1.500 TPS không?

**Gợi ý:** Không; 500 TPS, khoảng 1.500 item writes/s nếu mỗi transaction commit đủ.

### Bài tập 10 — Pagination

Query trả page 1 gồm 100 records.

**Câu hỏi:** Có đo latency truy xuất toàn bộ 10.000 records không?

**Gợi ý:** Không; mới đo một page.

### Bài tập 11 — Cache

Hit 90%, cache read 2ms, DB miss path 50ms.

**Câu hỏi:** Báo `DB p50=2ms` có đúng không?

**Gợi ý:** Không; đây là application cache path.

### Bài tập 12 — Query không index

Query trả 10 results nhưng scan 10 triệu docs.

**Câu hỏi:** Metric bổ sung nào quan trọng?

**Gợi ý:** Scanned records/bytes, query plan và index selectivity.

### Bài tập 13 — Retry amplification

1.000 logical requests, 200 requests retry một lần.

**Câu hỏi:** Physical attempts và amplification?

**Gợi ý:** 1.200 attempts, amplification 1,2.

### Bài tập 14 — Timeout sau commit

Client timeout nhưng DB đã cập nhật.

**Câu hỏi:** Có nên đếm chắc là failed write không?

**Gợi ý:** Unknown outcome; tra operation ID/source.

### Bài tập 15 — Conditional conflict

100 clients tranh một ghế, một client được reserve.

**Câu hỏi:** 99 conflicts có phải 99 successful reservations không?

**Gợi ý:** Không; tính riêng conflict outcome.

### Bài tập 16 — Closed-loop

100 threads mỗi thread chờ response xong mới gửi tiếp.

**Câu hỏi:** Khi response chậm gấp đôi, offered rate thường thế nào?

**Gợi ý:** Giảm nếu không có workload khác; đó là closed-loop.

### Bài tập 17 — Coordinated omission

Một worker block 2 giây, không gửi các requests đáng lẽ theo lịch.

**Câu hỏi:** Histogram có thể che điều gì?

**Gợi ý:** Tác động của các arrivals bị bỏ qua khi hệ stall.

### Bài tập 18 — Open-loop generator

Script đặt 5.000 req/s nhưng CPU generator bão hòa và chỉ gửi 3.000.

**Câu hỏi:** Nên ghi số nào?

**Gợi ý:** Cả target 5.000 và actual issued 3.000, với generator bottleneck.

### Bài tập 19 — Multi-region

Benchmark từ cùng AZ có p99=5ms, production clients ở lục địa khác.

**Câu hỏi:** Có hứa p99 5ms cho clients đó không?

**Gợi ý:** Không; RTT/route khác.

### Bài tập 20 — Strong vs eventual read

Test A dùng eventual read, B dùng strongly consistent read.

**Câu hỏi:** Có so latency trực tiếp để quyết định không?

**Gợi ý:** Không nếu yêu cầu consistency giống B.

### Bài tập 21 — Hot partition

Cluster CPU trung bình 30%, một partition worker 100%.

**Câu hỏi:** Vì sao p99 vẫn cao?

**Gợi ý:** Hotspot/queueing, average CPU che bottleneck.

### Bài tập 22 — LSM compaction

Một test 1 phút cho 20k writes/s, test 1 giờ giảm còn 11k/s.

**Câu hỏi:** Cần điều tra gì?

**Gợi ý:** Flush/compaction, disk, GC, cache, tombstones.

### Bài tập 23 — Payload

Test A đọc 1 KiB, B đọc 1 MiB.

**Câu hỏi:** `5k ops/s` có cùng ý nghĩa capacity không?

**Gợi ý:** Không; bytes/s, network, deserialize khác.

### Bài tập 24 — p99 aggregation

Minute 1 có 10.000 requests p99 20ms, minute 2 có 100 requests p99 200ms.

**Câu hỏi:** p99 tổng có bằng 110ms không?

**Gợi ý:** Không; phải gộp toàn bộ distribution.

### Bài tập 25 — Server time vs end-to-end

DB query execution 10ms, API queue 100ms.

**Câu hỏi:** Đường tối ưu đầu tiên có nhất thiết là query index không?

**Gợi ý:** Chưa; xem queue/pool và saturation.

### Bài tập 26 — CDC

Source commit T0, CDC capture T1, broker T2, sink T3, search visible T4.

**Câu hỏi:** User-facing freshness lag đo từ đâu tới đâu?

**Gợi ý:** T4 − T0.

### Bài tập 27 — Goodput SLO

Offered 10.000 RPS, 9.000 successful dưới 100ms, 500 successful sau 100ms, 500 failed.

**Câu hỏi:** Tỷ lệ đạt “successful under 100ms”?

**Gợi ý:** 90% của 10.000.

### Bài tập 28 — Cost

Một benchmark tiêu 30 USD cho 15 triệu successful operations.

**Câu hỏi:** Cost per million successes?

**Gợi ý:** 2 USD/triệu, trong phạm vi chi phí được nêu.

### Bài tập 29 — Failure capacity

Healthy cluster goodput 5k/s, mất một node còn 3k/s với p99 vượt SLO.

**Câu hỏi:** Nên báo capacity nào cho kế hoạch HA?

**Gợi ý:** Cả healthy và degraded SLO-compliant capacity.

### Bài tập 30 — Thiết kế bài đo hoàn chỉnh

Một Java service dùng Redis cache-aside cho Order, MongoDB làm source, Kafka CDC cập nhật Elasticsearch, Inventory ở DynamoDB.

**Yêu cầu:** Thiết kế workload matrix, 3 measurement boundaries, load model, dataset, metrics, success criteria, retry handling và failure tests.

**Gợi ý:** Đo cache hit/miss riêng, MongoDB point read, DynamoDB conditional reserve, HTTP checkout, CDC/search freshness; chọn open-loop cho incoming traffic, ghi source versions, p50/p95/p99 cùng errors/goodput; test cache restart, source failover, unknown commit, hot inventory và CDC lag.

## 52. Mẫu biểu định nghĩa một benchmark

Sử dụng mẫu này trước khi chạy:

```yaml
benchmarkId: orders-get-by-id-v1

objective:
  description: "Capacity theo SLO cho point read"
  target: "99% successful requests <= 100ms"
  maximumErrorRate: "0.1%"

operation:
  name: GetOrderById
  scope: "one driver call, one existing order"
  keyDistribution: "Zipfian, params specified separately"
  payload: "2 KiB typical, report distribution"
  consistency: "primary read, exact mode in config"
  success: "valid document, expected version/freshness"
  retries: "disabled in baseline"
  timeout: "200ms end-to-end driver call"

environment:
  databaseVersion: "record exact version"
  topology: "3 voting/data nodes, AZ/region documented"
  datasetRecords: 12000000
  index: "primary key"
  clientRegion: "same region, separate load node"
  cache: "disabled"
  tls: true

load:
  model: "open-loop"
  arrivalRatesRps: [1000, 2000, 3000, 4000, 5000]
  warmupMinutes: 5
  measureMinutes: 20
  repetitions: 3

report:
  latency: [p50, p90, p95, p99, p999]
  throughput: [offered, completed, successfulGoodput]
  outcomes: [success, notFound, conflict, timeout, error]
  resources: [cpu, memory, gc, network, disk, pool, queue]
  correctness: [validResponse, dataFreshness]
```

Đây là **mẫu tài liệu YAML**, không phải cấu hình chạy trực tiếp của YCSB/k6. Giá trị phải được thay và làm rõ theo mục tiêu thực tế.

### 52.1. Vì sao ghi repetitions?

Một run có thể bị ảnh hưởng bởi compaction, GC hoặc cloud noisy neighbor. Nhiều runs giúp thấy biến thiên và tránh chọn “run đẹp nhất” làm kết luận.

### 52.2. Vì sao ghi objective trước?

Nếu mục tiêu là 99% reads dưới 100ms, tối ưu throughput cao nhất bất kể p99 không giải quyết câu hỏi kinh doanh.

## 53. Checklist đo tải NoSQL

- [ ] Đã định nghĩa operation với start/end và outcome.
- [ ] Phân biệt HTTP request, DB command, transaction, batch item và workflow.
- [ ] Ghi rõ đơn vị req/s, ops/s, tx/s, rows/s, bytes/s.
- [ ] Ghi offered load, achieved completions và successful goodput.
- [ ] Không bỏ timeout/errors khỏi khả năng phục vụ.
- [ ] Đã nêu histogram/percentile sampling method và measurement window.
- [ ] Không suy p99 từ average hoặc từ p99 từng phút.
- [ ] Có client-side, driver-side và server-side latency khi cần.
- [ ] Biết pool wait, network, queue, execute và decode boundaries.
- [ ] Chọn open-loop/closed-loop theo tình huống và ghi coordinated-omission policy.
- [ ] Kiểm tra generator phát đúng arrivals dự kiến.
- [ ] Không gọi số concurrent threads là requests/s.
- [ ] Dùng Little's Law đúng mean và ổn định.
- [ ] Benchmark nhiều mức load để tìm SLO-compliant capacity.
- [ ] Dataset size, shape và key distribution đại diện.
- [ ] Tách hot/cold cache, hit/miss, TTL/invalidation.
- [ ] Có index/explain và query selectivity.
- [ ] Tách GET, query, scan, aggregation, write, CAS, batch, transaction.
- [ ] Với write, biết rõ ACK/durability/consistency semantics.
- [ ] Với read, biết freshness và nơi replica phục vụ.
- [ ] Với batch, báo RPC/s và successful items/s.
- [ ] Với transaction, báo committed TPS và transaction size.
- [ ] Với retries, báo logical vs physical attempts.
- [ ] Với Java, ghi driver/JVM/GC/pool/serialization settings.
- [ ] Có warmup/ramp/sustained/drain phases và repetitions.
- [ ] Có metrics CPU, memory, disk, network, shards, pool, queue.
- [ ] Có long-running tests cho compaction/TTL/repair/background jobs.
- [ ] Có failure/degraded tests và recovery timeline.
- [ ] Với CDC, đo source-to-visible freshness, không chỉ broker lag.
- [ ] Có correctness checks cho stale read, lost update, oversell.
- [ ] Report kèm topology, region, phiên bản và chi phí.
- [ ] Không kết luận database “nhanh hơn” khi operation/guarantee khác nhau.

## 54. Tổng kết

Để đo hiệu năng NoSQL một cách có ý nghĩa, trước hết phải trả lời ba câu hỏi:

**Độ trễ của thao tác nào?** Đó là thời gian từ đâu đến đâu: request người dùng, method Java, driver command, server execution, transaction commit hay thay đổi đã hiện lên search projection? Các ranh giới này có thể khác nhau hàng chục hoặc hàng trăm mili-giây.

**Thông lượng của thứ gì?** Offered requests/s, completed operations/s, successful transactions/s, item writes/s, bytes/s và CDC events/s là những mẫu số khác nhau. Chỉ gọi một con số là “ops/s” khi operation và success criteria được định nghĩa rõ.

**Phạm vi và điều kiện đo là gì?** Query shape, index, payload size, key distribution, cache hit rate, consistency, replication, region, transaction size, concurrency, open/closed load, retries và timeouts đều thay đổi kết quả. p50/p95/p99 chỉ so sánh được khi population và phương pháp đo tương thích.

Khi dữ liệu đã đo có ý nghĩa, hãy tăng offered load theo từng mức để thấy **đường cong throughput–latency–error**, dùng SLO để chọn capacity vận hành, đồng thời kiểm tra long-run compaction, Java GC, cache cold start, failover và downstream freshness.

**Nguyên tắc cốt lõi:** *Đừng bắt đầu bằng “database chịu được bao nhiêu QPS?”. Hãy bắt đầu bằng “một thao tác thành công theo đúng nghĩa nghiệp vụ là gì, được xác nhận ở đâu, mất bao lâu từ góc nhìn nào, và với tải nào hệ vẫn giữ đúng hợp đồng đó?”.* Chỉ khi trả lời được, những số latency và throughput mới trở thành căn cứ đáng tin cậy để thiết kế, tối ưu và lựa chọn NoSQL.

