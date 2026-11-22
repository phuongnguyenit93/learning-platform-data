# Điểm nóng do một khóa, một nhóm dữ liệu hoặc một miền thời gian

## 1. Một cụm NoSQL có nhiều node vẫn có thể nghẽn ở một điểm

Một nền tảng bán vé đặt dữ liệu trên 12 shard. Trong ngày thường, hệ xử lý khoảng 20.000 yêu cầu mỗi giây. Đến giờ mở bán một buổi hòa nhạc, 100.000 người liên tục kiểm tra **cùng một sự kiện** và tranh mua **cùng một nhóm ghế**.

Biểu đồ cho thấy:

~~~text
Shard A:  1.800 ops/s, p99 = 20 ms
Shard B:  2.100 ops/s, p99 = 24 ms
Shard C:  1.900 ops/s, p99 = 22 ms
Shard D: 48.000 ops/s, p99 = 2.300 ms, nhiều timeout
Shard E..L: còn khá nhiều tài nguyên
~~~

Điều kỳ lạ là **toàn cụm vẫn còn CPU, RAM và ổ đĩa trống**. Thêm nhiều node hoặc tăng replication factor chưa chắc khiến shard D bớt nghẽn. Nguyên nhân có thể là:

- Một **khóa cực nóng**: mọi người cùng đọc/cập nhật đối tượng EVENT#E01 hoặc COUNTER#VIEW#E01.
- Một **nhóm dữ liệu nóng**: toàn bộ hoạt động của tenant T17 hoặc danh mục EVENT#E01 cùng tập trung trên một partition/shard.
- Một **miền thời gian nóng**: mọi giao dịch vừa tạo có timestamp mới nhất nên cùng đi vào range cuối của index, shard hoặc time bucket.

Ba kiểu này có nguyên nhân, dấu hiệu và cách xử lý khác nhau. Chúng cũng có thể xuất hiện đồng thời.

Bài học thuộc module **Database No SQL**, chương **Cân bằng và điểm nóng**, tập trung vào cách phân biệt **hot key**, **hot group/partition** và **hot time range**, quan sát chúng trong production, điều chỉnh mô hình dữ liệu và tránh phá vỡ ràng buộc nghiệp vụ trong lúc phân tán tải.

### Bạn sẽ học được gì?

1. Nhận biết những cấp độ nóng: request key, logical partition, physical shard, index, cache và mạng.
2. Giải thích vì sao hash đều theo *số lượng khóa* không đảm bảo đều theo *lưu lượng*.
3. Chẩn đoán bằng QPS, byte, CPU/I/O, hàng đợi, p99, throttling và độ trễ replication.
4. Phân biệt giải pháp dành cho **một key** với giải pháp dành cho **một nhóm key** và **miền thời gian tăng tuần tự**.
5. Áp dụng sharded counter, write bucketing, cache, coalescing, queue, rate limiting, isolated placement, resharding và read model.
6. Phân tích giới hạn nhất quán, uniqueness, ordering và giao dịch khi tách một điểm nóng thành nhiều nơi.
7. Liên hệ DynamoDB, Cassandra/ScyllaDB, MongoDB, Redis Cluster và Elasticsearch/OpenSearch.
8. Thiết kế thử nghiệm tải và fault injection để kiểm tra hiệu quả thay đổi.

## 2. Nóng là gì? Đừng nhầm nhiều dữ liệu với nhiều tải

Một điểm nóng (*hotspot*) là nơi nhận lượng công việc vượt khả năng xử lý tương ứng, trong khi tài nguyên ở những nơi khác còn chưa được tận dụng hiệu quả.

Nơi đó có thể là:

- Một item/document/key.
- Một logical partition.
- Một partition key hoặc token range.
- Một shard/tablet/chunk.
- Một primary shard của search index.
- Một Redis hash slot.
- Một leader/coordinator.
- Một hàng đợi, CPU core, ổ đĩa hoặc network link.

### 2.1. Hotspot về kích thước

~~~text
Shard A: 100 GB
Shard B: 110 GB
Shard C: 900 GB
~~~

C có thể gần đầy dung lượng, khiến compaction, backup, recovery và resharding khó khăn. Nhưng nếu gần như không được truy cập, đây là **storage skew**, chưa chắc là hotspot về throughput.

### 2.2. Hotspot về số thao tác

~~~text
Shard A: 2.000 ops/s
Shard B: 2.100 ops/s
Shard C: 40.000 ops/s
~~~

C có thể quá tải CPU, hàng đợi hoặc giới hạn request ngay cả khi lưu ít dữ liệu.

### 2.3. Hotspot về byte và chi phí thao tác

Hai shard đều nhận 10.000 writes/s nhưng:

~~~text
Shard A: mỗi write khoảng 1 KB.
Shard B: mỗi write khoảng 200 KB.
~~~

B có write bandwidth và storage churn cao hơn nhiều. Đếm requests đơn thuần không cho bức tranh đủ.

### 2.4. Một thao tác có thể đắt khác thường

Thí dụ:

- Update một counter nhỏ: ít byte nhưng rất nhiều contention.
- Quét một partition 10 triệu hàng: QPS thấp nhưng read amplification lớn.
- Ghi document kèm nhiều secondary indexes: write amplification cao.
- Query có sort/aggregate: tiêu tốn CPU/RAM trên coordinator.

**Độ nóng phụ thuộc chi phí thực của thao tác**, không chỉ số request.

## 3. Ba nguồn gốc chính

| Nguồn nóng | Đơn vị có cùng vị trí | Dấu hiệu điển hình | Vì sao khó chia |
|---|---|---|---|
| **Một khóa** | Cùng business key/primary key | Một item nhận phần lớn GET/UPDATE | Hash cùng key luôn ra cùng nơi; thao tác nguyên tử cần phối hợp |
| **Một nhóm dữ liệu** | Cùng tenant, course, category, partition hoặc slot | Nhiều keys nhưng chung logical partition/owner | Shard key có cardinality thấp hoặc nhóm có tải quá lớn |
| **Một miền thời gian** | Khóa tăng dần, latest timestamp, active time bucket | Ghi mới tập trung ở range cuối | Range locality dồn mọi mutation mới vào cùng đoạn |

Một ví dụ có cả ba:

~~~text
Campaign TENANT#T17 / EVENT#E01 (nhóm nóng)
    |
    +--> COUNTER#E01 (một key nóng)
    |
    +--> ORDERS#2026-11-14#CURRENT (bucket thời gian nóng)
~~~

Không thể giải quyết tất cả chỉ bằng thêm một index hay một hash function.

## 4. Điểm nóng do một khóa duy nhất

### 4.1. Ví dụ counter toàn cục

~~~json
{
  "id": "VIEW_COUNT#EVENT#E01",
  "count": 5982741
}
~~~

Mỗi lượt xem gửi:

~~~text
INCREMENT VIEW_COUNT#EVENT#E01 BY 1
~~~

Nếu có 50.000 lượt xem/giây, mọi mutation đều nhắm cùng một key. Hash phân phối khóa đó vào **một logical placement**; tăng tổng shard count không làm một key tự nhân thành 50.000 owner độc lập.

### 4.2. Khóa nóng do đọc

Một bài đăng nổi tiếng có thể nhận hàng trăm nghìn GET/giây nhưng ít UPDATE. Với dữ liệu phù hợp, caching và request coalescing có thể giảm lượng read tới nguồn.

### 4.3. Khóa nóng do ghi

Một item bị cập nhật liên tục:

~~~text
UPDATE stock SET quantity=quantity-1
WHERE productId=P101
~~~

Nếu mọi cập nhật phải giữ atomicity trên cùng số lượng tồn, chúng cần **một trật tự/điểm quyết định** nào đó. Chia item thành 16 counters và cộng lại có thể tăng throughput, nhưng không tự ngăn oversell.

### 4.4. Read hotspot và write hotspot không giống nhau

| Vấn đề | Read-hot key | Write-hot key |
|---|---|---|
| Nút thắt thường gặp | QPS, network, cache miss | Atomic update contention, throughput, replication |
| Giảm tải khả thi | Cache, CDN, coalescing, replica reads khi cho phép | Batching, shard counters, append events, queue, partitioned ownership |
| Đánh đổi | Stale data, invalidation | Ordering, uniqueness, exactness, reconciliation |
| Điểm cần hỏi | Đọc cũ bao lâu được? | Những thao tác nào bắt buộc cùng một quyết định nguyên tử? |

### 4.5. Băm không chia được một key

Giả sử:

\[
\text{shard}(K)=H(K)\bmod16.
\]

Với \(K=\texttt{VIEW\_COUNT\#E01}\), kết quả luôn như nhau. Hash chỉ làm nhiều **khóa khác nhau** phân phối có vẻ ngẫu nhiên; nó không chia lưu lượng của **cùng một khóa**.

Muốn phân tán lưu lượng phải **thay đơn vị dữ liệu hoặc cách truy cập**, không chỉ thay số shard.

## 5. Một khóa nóng có thể xuất hiện từ thao tác tưởng như độc lập

### 5.1. Cùng một metadata record

Một ứng dụng ghi nhiều event khác nhau nhưng mọi writer đều cập nhật:

~~~text
TENANT#T17#LAST_UPDATED_AT
~~~

Các event phân phối trên nhiều shard, nhưng metadata record này vẫn nhận một UPDATE cho mỗi event, tạo hotspot thứ cấp.

### 5.2. Đồng hồ hoặc sequence toàn cục

Một counter cấp ID tăng tuần tự:

~~~text
GLOBAL_ORDER_SEQUENCE = GLOBAL_ORDER_SEQUENCE + 1
~~~

Mọi order tạo mới tranh cùng một item. Dù order data được hash theo orderId, **bộ cấp sequence** vẫn là nút thắt.

Có thể dùng ID phân tán, cấp dải sequence, hoặc coordinator chuyên trách tùy yêu cầu về uniqueness và thứ tự.

### 5.3. Materialized aggregate

~~~text
Course C101 -> totalEnrolled += 1
~~~

Ghi enrollment phân bố đều nhưng materialized count của một khóa vẫn bị dồn tải. Đây là write amplification biến một nhóm thao tác phân tán thành một điểm nóng duy nhất.

### 5.4. Global lock

Một distributed lock key dùng cho mọi tenant:

~~~text
LOCK#IMPORT
~~~

có thể serialize quá nhiều công việc vốn độc lập. Đôi khi chỉ cần lock scoped theo tenant hoặc resource, nhưng phải bảo đảm rằng những công việc bị chia thực sự không cùng invariant.

### 5.5. Một leader nhận mọi yêu cầu

Ngay cả khi storage shards khác nhau, application có thể gửi mọi mutation qua một coordinator, một queue consumer hoặc một gateway instance. Khi đó hotspot nằm ở **tầng định tuyến/ứng dụng**, không phải shard key.

## 6. Điểm nóng do một nhóm dữ liệu

### 6.1. Shard theo tenantId

~~~text
shardKey = tenantId
~~~

Giả sử:

~~~text
Tenant T01: 100 requests/s
Tenant T02: 120 requests/s
Tenant T17: 45.000 requests/s
Tenant T18: 90 requests/s
~~~

T17 chiếm phần lớn tải. Hash đều tên tenant không giúp chia T17; mọi khóa trong tenant ấy có thể được gán cùng logical partition hoặc cùng physical placement theo mô hình.

### 6.2. Nhóm khóa ít phân biệt

Ví dụ shard key hoặc index partition key:

~~~text
status = PENDING | PAID | FAILED
~~~

Nếu 90% items có status=PENDING, toàn bộ activity của PENDING có thể tập trung vào một hoặc vài key/partition/slot. Đây là hiện tượng **low-cardinality partition key**.

### 6.3. Course, campaign và project

Một course bình thường có 500 học viên nhưng một course nổi tiếng có 5 triệu học viên. Nếu dữ liệu enrollment cùng đặt theo courseId, course nổi tiếng có thể trở thành partition lớn và nóng.

### 6.4. Nhóm nóng có thể chứa nhiều keys

~~~text
TENANT#T17#USER#U001
TENANT#T17#USER#U002
TENANT#T17#USER#U003
...
~~~

Mỗi key riêng chỉ có 5 QPS, nhưng hàng triệu keys cùng thuộc T17 có thể làm một shard quá tải nếu shard key chỉ là tenantId.

Khác với hot single key, **có thể chia group theo subkey** nếu query và invariant cho phép.

### 6.5. Nhóm nóng do custom routing

Trong search engine hoặc Redis Cluster, custom routing/hash tag cố gom mọi document/key của một tenant vào cùng shard/slot để giảm fan-out hoặc hỗ trợ multi-key operations.

Đồng vị trí giúp một số thao tác nhanh và dễ nguyên tử hơn, nhưng có thể chuyển toàn bộ tải một tenant khổng lồ thành một hotspot.

## 7. Điểm nóng do một miền thời gian

### 7.1. Range key tăng liên tục

Giả sử các shard được chia theo timestamp:

~~~text
Shard A: [2026-11-01, 2026-11-07)
Shard B: [2026-11-07, 2026-11-14)
Shard C: [2026-11-14, +inf)
~~~

Tất cả event mới ở ngày 14/11 đi tới Shard C. Khi thời gian tăng, hotspot di chuyển theo **miền mới nhất**.

Đây thường được gọi là **hot tail**, **moving hotspot** hoặc **monotonic-key hotspot**.

### 7.2. Auto-increment ID

Một shard key dạng:

~~~text
ORDER#000001
ORDER#000002
ORDER#000003
...
~~~

nếu range-sharded theo orderId, các order mới rơi vào range cuối. Thay ID từ số sang chuỗi không tự khắc phục nếu thứ tự chuỗi vẫn tăng theo cùng hướng.

### 7.3. Mọi ghi cùng một time bucket

~~~text
PK = EVENT#2026-11-14
SK = 09:15:00.000#EVT1
SK = 09:15:00.001#EVT2
...
~~~

Nếu chỉ có một partition key cho ngày hiện tại, 1 triệu event/giây cùng vào một logical partition. Tạo bucket theo ngày là tốt hơn gom tất cả thời gian vào một key, nhưng **ngày hiện tại vẫn có thể quá nóng**.

### 7.4. Secondary index cũng có hot tail

Một bảng chính phân phối theo userId có thể ổn, nhưng index theo **createdAt** tăng liên tục có thể tập trung writes vào range mới nhất của index.

Đánh giá primary data mà bỏ qua secondary index sẽ dẫn tới kết luận sai: “Shard key đã đều mà sao vẫn throttling?”

### 7.5. Query mới nhất làm tăng nhiệt

Hot time range không chỉ do ghi. Dashboard thường xuyên hỏi:

~~~text
ORDER BY createdAt DESC LIMIT 100
~~~

Mọi reader đều chạm miền mới nhất, trong khi các range lịch sử ít được đọc. Có thể xảy ra **read-hot tail kết hợp write-hot tail**.

### 7.6. Late-arriving events

Event xảy ra lúc 08:00 nhưng tới nguồn lúc 12:00. Nếu route theo eventTime, ghi sẽ quay về bucket cũ. Nếu route theo ingestionTime, sẽ vào bucket hiện tại.

Chọn theo event time hoặc ingest time ảnh hưởng:

- Distribution.
- Retention.
- Range queries.
- Replay/reconciliation.
- Khả năng đóng/compaction bucket cũ.

Không nên để hai producers dùng hai quy tắc khác nhau cho cùng bảng.

## 8. Hotspot có thể xuất hiện ở tầng thứ cấp

Một request ghi NoSQL thường không dừng ở một item:

~~~mermaid
flowchart TD
    A["Write event"] --> B["Base table"]
    B --> C["Secondary index"]
    B --> D["Counter/aggregate"]
    B --> E["CDC / Outbox"]
    E --> F["Search projection"]
    E --> G["Cache invalidation"]
~~~

Các dạng hotspot:

| Tầng | Điểm nóng | Biểu hiện |
|---|---|---|
| Base table | Một PK/partition | Throttling, CAS contention, p99 cao |
| Secondary index | Status PENDING hoặc timestamp mới nhất | Index write lag, query p99 |
| Counter/materialized view | Một aggregate record | Update contention |
| CDC/outbox | Một partition của event stream | Consumer lag, delayed projections |
| Search | Một primary shard | Indexing queue, refresh pressure |
| Cache | Một popular key hoặc slot | CPU/network trên cache node |
| Application | Một coordinator hoặc lock | Thread pool/queue chờ |

**Sửa hotspot ở bảng chính có thể chỉ chuyển nút thắt sang index, stream hoặc cache.** Cần trace và metric dọc toàn đường ghi.

## 9. Phân tích phân bố tải thay vì chỉ nhìn tổng QPS

### 9.1. Bình quân dễ che lệch

Một cụm 10 shards nhận 100.000 ops/giây có average 10.000 ops/giây/shard. Nhưng:

~~~text
Shard 1..9: mỗi shard ~5.000 ops/s.
Shard 10:   55.000 ops/s.
~~~

Đó là hotspot dù average có vẻ trong khả năng xử lý của mỗi node.

### 9.2. Tỷ lệ tải trên shard nóng nhất

Một chỉ số tự định nghĩa:

\[
\text{MaxShardShare}
=\frac{\max_i Q_i}{\sum_i Q_i}.
\]

Với Q tổng 100.000 ops/giây và shard nóng nhất 55.000:

\[
\text{MaxShardShare}=55\%.
\]

Nếu 10 shard hoàn toàn đồng đều thì mỗi shard khoảng 10%. Chênh lệch lớn là tín hiệu phải tìm nguyên nhân.

### 9.3. Skew ratio

~~~text
SkewRatio = maxShardLoad / averageShardLoad
~~~

Trong ví dụ:

\[
55.000 / 10.000 = 5,5.
\]

Shard nóng nhất chịu tải gấp 5,5 lần trung bình.

**Chú ý:** Đây là các metric phân tích tùy định nghĩa, không phải tên chuẩn bắt buộc của một NoSQL engine. Nếu shards có capacity khác nhau, cần chuẩn hóa tải theo khả năng thực tế của từng shard.

### 9.4. Top-key share

Với key K:

\[
\text{TopKeyShare}
=\frac{\text{request rate của K}}
{\text{request rate toàn nhóm}}.
\]

Nếu một key đóng góp 80% writes vào partition, sharding theo user khác có thể ít giúp ích; phải xử lý K hoặc cấu trúc phụ thuộc K.

### 9.5. Tách read, write và scan

Đừng dùng một con số **ops/s** trộn các chi phí:

~~~text
GET small item:          1 operation.
UPDATE with 3 indexes:  1 logical operation + write amplification.
SCAN million rows:      1 API request, huge resource cost.
~~~

Theo dõi riêng số đọc/ghi, byte, returned rows, storage I/O, index/compaction work và queue length.

## 10. Metric cần đo ở từng cấp

| Cấp | Metric hữu ích | Dấu hiệu |
|---|---|---|
| Key/partition | Read/write QPS, bytes, throttled requests, top keys | Một key chiếm phần lớn |
| Shard | CPU, disk IOPS, network, queue, p95/p99 | Một shard lệch khỏi nhóm |
| Router | Targeted vs scatter-gather, redirects, stale mapping | Query vào quá nhiều shards |
| Database | Timeouts, conflicts, lock/CAS retries | Contention tăng |
| Index | Write backlog, search/index latency, segment/refresh | Hot secondary index |
| Stream/CDC | Consumer lag, oldest pending age | Downstream theo không kịp |
| Cache | Key miss rate, hit rate, evictions, hot slot | Nút cache quá tải |
| Application | Pool saturation, request coalescing, retry count | Bottleneck upstream |

### 10.1. p99 theo shard

Nếu toàn cụm có p99 100 ms nhưng chỉ tenant T17 có p99 3 giây, dashboard toàn hệ không thể hiện đủ tác động. Cần breakdown theo shard, tenant class, Region và operation.

### 10.2. Không gắn PII vào metric label

Tên email, username, raw tenant token hoặc requestId có thể vừa nhạy cảm vừa tạo cardinality lớn.

Có thể dùng top-N hot keys được băm/ẩn danh ở hệ chẩn đoán có kiểm soát truy cập và thời hạn lưu phù hợp. Không ghi raw secrets vào logs/traces.

### 10.3. Đo latency ở nguồn và tại client

Database thấy UPDATE hoàn tất 30 ms nhưng client mất 2 giây có thể do connection pool, gateway, retry hoặc network. Một metric DB riêng không chỉ ra toàn bộ hành trình.

### 10.4. Tăng replica có giúp không?

Với read workload có consistency cho phép, thêm read replicas có thể chia tải đọc. Với single-key write cần một authoritative owner, tăng replica có thể **tăng chi phí replication** thay vì nhân thông lượng ghi.

## 11. Quy trình chẩn đoán trước khi sửa

### Bước 1 — Phân loại sự cố

Quan sát:

~~~text
Nhiều reads hay writes?
Một item hay nhiều items?
Một tenant/category hay mọi tenant?
Chỉ giờ hiện tại hay mọi khoảng thời gian?
Throttling từ base table, index, cache hay consumer?
~~~

### Bước 2 — Xác nhận phân bố

Thu QPS, bytes, p99, throttling theo shard/partition. Tìm top keys, top tenants và time buckets.

### Bước 3 — Liên hệ truy vấn và data model

Kiểm tra:

- Partition/shard key hiện tại.
- Secondary index keys.
- Các thao tác cập nhật aggregate/counter.
- Những query không mang đủ routing key.
- Những thao tác có lock hoặc transaction chéo.

### Bước 4 — Phân biệt nguyên nhân

Nếu **một key** chiếm tải: cần giảm số lần chạm key hoặc thay cấu trúc lưu.

Nếu **một group** chiếm tải: có thể chia sub-buckets, isolate tenant hoặc đổi placement.

Nếu **range mới nhất** nhận mọi ghi: cần hash/striping trong miền thời gian, thay partition scheme hoặc tách hot/cold tier.

### Bước 5 — Xác định invariant trước khi thay đổi

Trả lời:

~~~text
Counter có thể trễ vài giây không?
Tồn kho có được âm không?
Username có phải unique toàn tenant không?
Event có cần total ordering không?
Người dùng vừa ghi phải đọc lại thấy ngay không?
~~~

Nếu bỏ qua những câu hỏi này, một giải pháp giảm latency có thể làm sai nghiệp vụ.

### Bước 6 — Benchmark và chọn giải pháp

Đo trước/sau với cùng workload, bao gồm peak và failure cases. Không chỉ đo average throughput; p99, error rate, consistency và mức tài nguyên sử dụng cũng là kết quả.

## 12. Giảm điểm nóng do đọc: cache, replica và request coalescing

### 12.1. Cache cho dữ liệu ít thay đổi

Nếu 100.000 người cùng xem mô tả buổi hòa nhạc:

~~~text
GET /events/E01
~~~

thay vì gửi mọi GET vào database, có thể:

~~~text
Clients
   |
   v
CDN / Edge cache
   |
   v
Application cache
   |
   v
NoSQL source
~~~

Một cache hit cao giúp giảm read QPS tới hot key nguồn.

### 12.2. Đánh đổi về độ mới

Giá vé, số ghế còn lại hoặc trạng thái hủy sự kiện có thể thay đổi. Cần xác định:

- TTL hoặc max-age được phép.
- Cache invalidation khi nguồn thay đổi.
- Version/ETag nếu có.
- Có chấp nhận stale-while-revalidate không.
- Endpoint nào phải đọc nguồn có thẩm quyền.

Ví dụ phần **mô tả sự kiện** có thể stale vài giây, nhưng số lượng ghế được phép bán ở bước checkout không nên quyết định từ cache eventual.

### 12.3. Cache stampede

Một hot key hết TTL. Hàng nghìn requests đồng thời cache miss:

~~~text
t0: Cache E01 expired.
t1: 10.000 requests -> miss.
t2: 10.000 requests -> source GET E01.
~~~

Điểm nóng chuyển ngược về nguồn đúng lúc cache mất hiệu lực.

### 12.4. Request coalescing / single-flight

Các request cùng key trong một khoảng ngắn dùng **một lần tải nguồn**, sau đó chia sẻ kết quả:

~~~text
10.000 requests miss E01
          |
          v
Single-flight E01
          |
          v
1 source GET
          |
          v
10.000 responses
~~~

Single-flight trong một application instance chỉ gom requests của instance đó. Nếu có 100 instances, có thể vẫn còn 100 source GET đồng thời; cần tính phạm vi cache/coalescing.

### 12.5. TTL jitter

Nếu 100.000 keys cùng hết TTL đúng một thời điểm, source có thể nhận một đợt miss lớn. Thêm độ lệch ngẫu nhiên hợp lý vào TTL làm các thời điểm refresh bớt đồng bộ.

Không áp dụng jitter để kéo dài hiệu lực một cách không kiểm soát cho token bảo mật hoặc quyền đã thu hồi.

### 12.6. Read replicas

Với dữ liệu có thể đọc từ bản sao trễ theo contract, phân phối đọc sang read replicas có thể giảm tải read. Nhưng một query cần **read-your-writes**, trạng thái xác thực hoặc dữ liệu vừa commit có thể phải dùng đường đọc mạnh hơn.

### 12.7. Negative caching

Nếu một key không tồn tại bị hàng nghìn bot thử liên tục, cache kết quả NOT_FOUND trong khoảng ngắn có thể giảm tải. Tuy nhiên nếu key được tạo sau đó, negative cache có thể làm người dùng không nhìn thấy bản ghi mới. Phải có invalidation hoặc TTL thích hợp.

## 13. Giảm điểm nóng do ghi: batching và aggregation có kiểm soát

### 13.1. Mỗi event không nhất thiết phải ghi counter ngay

Ví dụ 100.000 page views/giây nhưng dashboard chỉ cần tổng gần đúng sau vài giây.

Thay vì:

~~~text
100.000 INCREMENT requests mỗi giây tới một item.
~~~

ứng dụng có thể gom:

~~~text
Events -> 100 workers
Mỗi worker cộng trong bộ nhớ có giới hạn
Mỗi 1 giây flush một delta tới nguồn
~~~

Mỗi worker có thể gửi một delta thay vì hàng nghìn update, giảm write QPS tới hot item.

### 13.2. Không được bỏ qua độ bền

Gom trong RAM rồi reset khi process chết có thể làm mất số đếm. Nếu count quan trọng, dùng:

- Durable queue/log.
- Checkpoint.
- Dedup event IDs.
- At-least-once processing với idempotent aggregation.
- Hệ thống counter có semantics được xác định.

### 13.3. Tránh đếm đôi khi flush retry

~~~text
Worker gửi delta +500.
Database commit +500.
ACK bị mất.
Worker retry delta +500.
~~~

Nếu không có idempotency, count tăng 1.000 thay vì 500.

Một thiết kế có thể lưu **per-worker lastCommittedSequence** hoặc dùng event ledger để áp dụng mỗi delta đúng một lần theo contract. Transaction/conditional write cần bảo vệ cùng lúc sequence và value trong phạm vi storage hỗ trợ.

### 13.4. Batching giảm số thao tác, không xóa mọi contention

Nếu mọi worker cuối cùng vẫn update **cùng một item**, việc mỗi worker flush delta có thể giảm tần suất tranh chấp, nhưng item đó vẫn có giới hạn write capacity.

Muốn tăng thông lượng vượt nút thắt single-key, có thể cần **sharded counter hoặc thay đổi đơn vị aggregate**.

### 13.5. Queue theo khóa

Một queue có partition key theo business key có thể serialize những mutation cùng key:

~~~text
orderId -> queue partition -> single consumer per partition
~~~

Việc này giảm race và concurrency vô ích, nhưng có thể tạo **hot consumer partition**. Nếu business invariant bắt buộc thứ tự toàn phần cho một key, throughput của key vẫn bị giới hạn bởi điểm serialize đó.

## 14. Sharded counter: chia một giá trị logic thành nhiều phần vật lý

### 14.1. Cấu trúc

Thay:

~~~text
COUNTER#E01 -> 5000000
~~~

bằng:

~~~text
COUNTER#E01#BUCKET#00 -> 312450
COUNTER#E01#BUCKET#01 -> 309811
COUNTER#E01#BUCKET#02 -> 314108
...
COUNTER#E01#BUCKET#15 -> 311600
~~~

Tổng logic:

\[
C(E01)=\sum_{b=0}^{15} C(E01,b).
\]

### 14.2. Chọn bucket khi ghi

Một event có eventId ổn định. Chọn:

\[
b=H(\text{eventId})\bmod16.
\]

Các event khác nhau thường phân bố qua nhiều buckets. Cùng eventId khi retry vẫn chọn **cùng bucket**, nhưng điều đó **chưa tự ngăn duplicate increment**.

### 14.3. Điểm tốt

- Giảm contention trên một item.
- Tăng khả năng ghi song song khi các bucket được phân phối phù hợp.
- Cho phép điều chỉnh số buckets khi có quy trình versioning/migration.

### 14.4. Đánh đổi khi đọc

Muốn tổng chính xác tại một thời điểm logic, cần đọc mọi bucket và có consistency/snapshot phù hợp.

Nếu đọc:

~~~text
Bucket 0 tại t1.
Bucket 1 tại t2.
...
Bucket 15 tại t16.
~~~

trong khi writes vẫn diễn ra, kết quả không tự là **một snapshot nguyên tử**.

Với lượt xem, tổng gần đúng có thể chấp nhận. Với tiền/tồn kho, không thể tự kết luận đủ điều kiện nghiệp vụ chỉ vì tổng các counter đọc eventual còn dương.

### 14.5. Số buckets không nên tăng tùy tiện

Nhiều buckets:

- Giảm write contention.
- Tăng số reads để tính tổng.
- Tăng metadata/storage overhead.
- Làm rebuild/reconciliation phức tạp hơn.

Số lượng buckets phải được benchmark theo peak writes và tần suất đọc aggregate.

### 14.6. Bảo đảm idempotency

Nếu count cần chính xác, mỗi event chỉ được cộng một lần theo một idempotency contract:

~~~text
Event E1001 -> bucket 7.
Apply E1001 nếu chưa có processed marker hoặc sequence.
Update bucket 7 atomically cùng marker nếu phạm vi hỗ trợ.
~~~

Nếu marker và update nằm trên hai storage độc lập, không tự có atomicity. Cần outbox/ledger, CRDT có semantics phù hợp hoặc reconciliation.

### 14.7. Sharded counter không là kho tiền

Một số dư khả dụng không được âm yêu cầu ràng buộc mạnh khi trừ tiền. Chia một con số tài khoản thành 32 buckets và cho nhiều Region cùng trừ có thể dẫn tới số dư âm hoặc chấp nhận hai khoản chi vượt hạn mức.

Có thể phân bổ **escrow quota** theo bucket với giới hạn được bảo vệ, hoặc dùng một ledger/transaction có quyền quyết định thống nhất. Không dùng sharded counter gần đúng để quyết định tiền.

## 15. Phân tán một nhóm nóng bằng composite partition key

### 15.1. Từ tenant đơn sang tenant + user

Trước:

~~~text
PK = TENANT#T17
SK = USER#U101
SK = USER#U102
...
~~~

Khi T17 quá lớn, mọi user có thể bị dồn vào một logical partition.

Sau:

~~~text
PK = TENANT#T17#USER#U101
PK = TENANT#T17#USER#U102
...
~~~

Các user độc lập có thể được phân phối hơn, tùy thuật toán placement của engine.

### 15.2. Điểm đổi

Lấy dữ liệu của **một user** dễ định tuyến hơn. Nhưng yêu cầu “lấy tất cả users của T17” có thể trở thành fan-out lớn.

Muốn phục vụ tenant-wide dashboard, có thể tạo query table/materialized view/analytics projection theo tenant thay vì scan mọi user trên đường yêu cầu tương tác.

### 15.3. Bucket theo subkey

Với nhóm có hàng triệu event:

~~~text
PK = TENANT#T17#BUCKET#00
PK = TENANT#T17#BUCKET#01
...
PK = TENANT#T17#BUCKET#31
~~~

Bucket có thể được chọn từ eventId, userId hoặc khóa con.

**Chọn từ userId** nếu cần gom event của một user vào một bucket.

**Chọn từ eventId** nếu ưu tiên phân phối writes độc lập; nhưng event của cùng user có thể nằm trên nhiều buckets.

Điều này cho thấy cùng một tiền tố tenant không nói đủ về locality.

### 15.4. Deterministic routing

Nếu cùng entity phải được đọc/ghi từ đúng một bucket, cần một hàm ổn định:

~~~text
bucket = hash(tenantId, userId) mod 32
~~~

Mọi service/worker dùng cùng encoding, hash algorithm và bucket count/version.

Nếu ghi chọn bucket ngẫu nhiên mà đọc chỉ hỏi một bucket tính theo userId, dữ liệu sẽ “biến mất” đối với query.

### 15.5. Query fan-out

Muốn lấy toàn bộ event một tenant trong một ngày khi có 32 buckets:

~~~text
READ bucket 00..31
MERGE / SORT / AGGREGATE
~~~

Số subqueries, network bytes, tail latency và kết quả partial phải được đo.

### 15.6. Uniqueness xuyên buckets

Nếu hai request tạo username=alice và chọn hai buckets khác nhau dựa trên random eventId, **unique index/conditional write cục bộ từng bucket không bảo vệ uniqueness toàn tenant**.

Giải pháp thường là:

- Một unique claim key được định tuyến xác định theo (tenantId,usernameCanonical).
- Conditional create hoặc transaction tại nơi có quyền quyết định.
- Để dữ liệu profile phân tán nhưng uniqueness claim duy nhất.

Không đánh đổi integrity lấy phân bố writes.

## 16. Điểm nóng nhóm: isolate tenant hoặc chia nhóm?

### 16.1. Isolate một tenant lớn

Nếu T17 có hàng trăm users nhưng traffic tổng quá lớn, directory-based routing có thể đưa T17 sang shard/node có capacity riêng.

~~~text
Tenant T17 -> Dedicated Shard D
Tenants khác -> Shared Shards A/B/C
~~~

Lợi ích:

- Giảm ảnh hưởng lên tenants nhỏ.
- Dễ theo dõi capacity/cost theo tenant.
- Có thể đáp ứng yêu cầu isolation/residency.

### 16.2. Chỉ chuyển hotspot chưa chắc đã giải quyết

Nếu tenant T17 yêu cầu 100.000 writes/s nhưng Shard D chỉ chịu được 30.000 writes/s, isolate chỉ làm overload tách khỏi phần còn lại.

Cần **phân chia dữ liệu trong chính tenant**, throttle, batching hoặc tối ưu workload.

### 16.3. Virtual buckets hoặc subshards

Một hybrid:

~~~text
Tenant T17 -> 64 logical buckets

Buckets 00..15 -> Shard D
Buckets 16..31 -> Shard E
Buckets 32..47 -> Shard F
Buckets 48..63 -> Shard G
~~~

Directory có thể điều chuyển bucket khi cân bằng tải mà không phải đổi hash key→bucket.

### 16.4. Vòng đời tenant nhỏ thành tenant lớn

Ban đầu T17 là tenant nhỏ, sau đó trở thành khách hàng lớn. Một hệ cần quy trình:

1. Phát hiện tăng trưởng.
2. Chọn cách split/isolated placement.
3. Copy snapshot và replay mutation.
4. Chuyển owner có epoch/fencing.
5. Refresh route caches.
6. Đối soát và cleanup an toàn.

Không phải đổi một row directory là tự di chuyển dữ liệu.

## 17. Điểm nóng miền thời gian: bucketing kết hợp hashing

### 17.1. Time bucket một tầng

Ví dụ:

~~~text
PK = EVENT#DAY#2026-11-14
SK = TIMESTAMP#eventId
~~~

Hữu ích cho read theo ngày, nhưng mọi ghi hôm nay cùng một PK.

### 17.2. Time bucket + hash bucket

Đổi thành:

~~~text
PK = EVENT#DAY#2026-11-14#B00
PK = EVENT#DAY#2026-11-14#B01
...
PK = EVENT#DAY#2026-11-14#B31
SK = TIMESTAMP#eventId
~~~

Với eventId ổn định:

\[
b=H(\text{eventId})\bmod32.
\]

Ghi ngày hiện tại được phân tán qua 32 logical buckets thay vì một.

### 17.3. Đọc nguyên một ngày

Một query lấy tất cả event ngày 14/11 cần:

~~~text
Query B00..B31
Merge by (timestamp,eventId)
Apply page limit
~~~

Không thể dùng một LIMIT 100 trên mỗi bucket rồi nối tùy ý nếu API đòi **global latest 100**. Cần merge theo comparator chung.

### 17.4. Đọc một thiết bị trong một ngày

Nếu query quan trọng là (deviceId, day), có thể chọn:

~~~text
PK = DEVICE#D17#DAY#2026-11-14
SK = timestamp#eventId
~~~

Các deviceId khác nhau phân tán. Nhưng một thiết bị tạo 80% mọi events vẫn có thể thành hot partition; khi ấy cần bucket bổ sung theo device/time segment.

### 17.5. Chọn kích thước bucket thời gian

Một ngày, một giờ hay năm phút?

| Bucket | Ưu điểm | Hạn chế |
|---|---|---|
Ngày | Ít partitions, query ngày dễ | Ngày có thể quá lớn/nóng |
Giờ | Giảm kích thước partition và thời gian nóng | Query ngày đọc 24 buckets mỗi entity |
5 phút | Phân tán/retention theo thời gian nhỏ hơn | Nhiều partitions; query dài phải fan-out nhiều |

Thực tế số partitions còn nhân với số hash buckets/thiết bị. Chọn dựa trên throughput, partition size và query shape.

### 17.6. Late-arriving events và retention

Nếu sự kiện được route theo eventTime, event đến muộn có thể ghi vào time bucket cũ. Nếu bucket đó đã đóng hoặc dữ liệu đã được chuyển sang cold storage, cần policy:

- Cho phép reopen/backfill.
- Gửi event tới correction stream.
- Giữ một grace window.
- Từ chối events quá cũ có lý do.

Không dùng TTL/retention tự động mà bỏ qua event đến trễ trong nghiệp vụ cần đầy đủ.

### 17.7. Index vẫn có thể nóng

Base table phân phối theo (day,bucket) nhưng một GSI dùng partition key day=2026-11-14 vẫn tập trung ghi. Cần thiết kế index theo workload tương tự, không chỉ sửa primary table.

## 18. Hash-based và range-based: chọn đúng điểm cần giữ locality

### 18.1. Hashed key

Hash một khóa tuần tự như orderId có thể làm order mới rải khắp nhiều mảnh. Point lookup theo orderId vẫn định vị.

Đổi lại, một query:

~~~text
WHERE orderId BETWEEN 1000 AND 2000
~~~

có thể mất locality theo orderId và phải fan-out.

### 18.2. Range key

Range sharding giữ locality khi query theo một khoảng orderId/timestamp. Nhưng một miền hiện tại nhận phần lớn writes có thể nóng.

### 18.3. Kết hợp

Một cách:

~~~text
Route by (day, hash(deviceId) mod B).
Within partition sort by occurredAt.
~~~

Như vậy:

- Hash/bucket giúp phân phối writes.
- Local time ordering hỗ trợ range query trong partition.
- Global time scan cần nhiều subqueries.

### 18.4. Không phải mọi hệ cho kiểm soát physical placement

Trong managed databases, ứng dụng có thể chọn partition key nhưng không được tự chọn node lưu từng bucket. Hiệu quả thực còn tùy giới hạn per-partition, adaptive capacity, indexing, replication và cơ chế partition splitting của engine.

Một mô hình logic hợp lý vẫn phải được benchmark trên sản phẩm và topology triển khai.

## 19. Hotspot và backpressure: tránh tạo hiệu ứng dây chuyền

### 19.1. Overload cascade

~~~text
Hot partition chậm
      |
      v
Application requests chờ
      |
      v
Connection pool đầy
      |
      v
Client timeout và retry
      |
      v
Hot partition còn nhận thêm tải
~~~

Đây là vòng lặp khuếch đại. Một điểm nóng có thể kéo sập nhiều endpoints nếu chúng chia sẻ thread pool/connection pool.

### 19.2. Rate limiting theo key/tenant

Có thể đặt quota:

~~~text
tenant T17: tối đa X requests/s theo hợp đồng.
event E01: tối đa Y request kiểm tra/s.
~~~

Rate limiting giúp giới hạn một tenant/hot key ảnh hưởng hàng xóm, nhưng yêu cầu bị từ chối vẫn cần được đo trong operational SLI theo contract.

### 19.3. Backpressure

Thay vì nhận vô hạn:

- Queue có capacity hữu hạn.
- Producer giảm tốc khi consumer chậm.
- Return 429/503 theo contract với Retry-After phù hợp.
- Giới hạn concurrency cho hot key.
- Ưu tiên request quan trọng.

### 19.4. Retry có jitter

Nếu 10.000 clients cùng retry sau đúng 100 ms, load spike có thể lặp lại đều đặn. Exponential backoff với jitter giúp phân tán retry.

Business conflict như username đã thuộc người khác **không nên retry vô hạn**. Chỉ lỗi transient mới có retry policy có giới hạn.

### 19.5. Bulkhead

Tách tài nguyên cho hoạt động khác nhau:

~~~text
Checkout pool
Search pool
Analytics pool
~~~

Một truy vấn analytics nóng không nên chiếm hết connection pool của checkout.

### 19.6. Load shedding không phải tối ưu dữ liệu

Load shedding giữ hệ hoạt động có kiểm soát khi quá tải; nó không làm phân bố shard key trở nên cân bằng. Khi peak kết thúc vẫn cần sửa cấu trúc/chi phí thao tác nếu hotspot xuất hiện thường xuyên.

## 20. DynamoDB: hot partition key, hot item và secondary index

### 20.1. Partition key quyết định phân phối

DynamoDB là managed service: ứng dụng định nghĩa partition key và optional sort key; dịch vụ quản lý các physical partitions. Không nên tính hash(PK) modulo số node vật lý để tự route.

Ví dụ:

~~~text
Table: EventCounters
PK = EVENT#E01
views = 9,000,000
~~~

Nếu mọi lượt xem UPDATE cùng PK, đây là **hot item**. Adaptive capacity và cơ chế tách/điều phối partitions của dịch vụ có giới hạn và không nên được hiểu là có thể tự chia một item thành vô hạn điểm ghi độc lập.

### 20.2. Sharded counters

Thiết kế:

~~~text
PK = EVENT#E01#COUNT#00
PK = EVENT#E01#COUNT#01
...
PK = EVENT#E01#COUNT#31
~~~

Mỗi event chọn bucket từ eventId; các update vào items khác nhau có thể phân tán hơn.

Muốn tổng, phải đọc các bucket và cộng. Nếu đọc qua nhiều items, không tự có một snapshot nguyên tử ở mọi thời điểm. Nếu cần đếm chính xác, phải xử lý duplicate/retry.

### 20.3. Low-cardinality GSI

Một GSI:

~~~text
GSI_PK = status
GSI_SK = createdAt
~~~

Nếu phần lớn công việc mới có status=PENDING, hàng nghìn writes có thể tập trung vào một logical GSI partition key.

Một thiết kế khác:

~~~text
GSI_PK = STATUS#PENDING#B00
GSI_PK = STATUS#PENDING#B01
...
GSI_PK = STATUS#PENDING#B31
GSI_SK = createdAt#jobId
~~~

Worker query PENDING cần fan-out 32 buckets và merge. Chỉ số pending state có thể vẫn được cập nhật bất đồng bộ ở GSI, vì GSI không hỗ trợ strongly consistent read.

**Cảnh báo:** Không sử dụng GSI eventual để cấp độc quyền xử lý job nếu hai workers có thể cùng thấy một job; dùng conditional update/claim trên item có thẩm quyền.

### 20.4. Hot key vì cùng một giá trị

Nếu PK chỉ có một giá trị cho mọi row:

~~~text
PK = GLOBAL
SK = EVENT#...
~~~

thì việc SK khác nhau không tự phân tán một logical item collection thành nhiều partition keys. Thiết kế cần thêm entropy vào PK phù hợp với access patterns, không chỉ thêm sort key.

### 20.5. Throttling cần phân loại

DynamoDB throttling có thể liên quan:

- Hot key hoặc hot GSI key.
- Capacity/quota cấu hình.
- Kích thước item và access pattern.
- Khu vực hay bảng đang nhận peak.
- Transaction retries và contention.

Không kết luận mọi throttling do một key nóng. Quan sát metrics, request-level reasons và những hot keys có thể xác định qua công cụ được dịch vụ cung cấp.

### 20.6. Exact quota

Nếu business rule là “chỉ 100 coupons có thể được xác nhận”, một sharded counter 32 items được increment độc lập **không tự đảm bảo tổng không vượt 100**. Cần quota reservation/escrow, conditional claim hoặc transaction phù hợp với invariant.

## 21. Cassandra/ScyllaDB: hot partition và partition lớn

### 21.1. Partition key được băm thành token

Trong hệ họ Cassandra/ScyllaDB, logical partition key được đưa qua partitioner/token placement. Một partition key cố định có một token và được lưu bởi tập replica tương ứng theo cấu hình.

Ví dụ:

~~~sql
CREATE TABLE activity_by_course (
    course_id text,
    occurred_at timestamp,
    event_id uuid,
    learner_id text,
    action text,
    PRIMARY KEY ((course_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Nếu course C101 cực nổi tiếng, partition course_id=C101 có thể rất lớn và nóng.

### 21.2. Thêm day bucket vào partition key

~~~sql
CREATE TABLE activity_by_course_day (
    course_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    learner_id text,
    action text,
    PRIMARY KEY (
        (course_id, activity_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Partition theo (course_id, activity_day) giúp chia dữ liệu qua nhiều ngày và hạn chế một partition phình mãi.

**Nhưng:** Nếu C101 tạo 500.000 events/giây trong ngày hiện tại, partition của C101 hôm nay vẫn cực nóng.

### 21.3. Thêm write bucket

~~~sql
CREATE TABLE activity_by_course_day_bucket (
    course_id text,
    activity_day date,
    bucket smallint,
    occurred_at timestamp,
    event_id uuid,
    learner_id text,
    action text,
    PRIMARY KEY (
        (course_id, activity_day, bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Router ứng dụng chọn bucket ổn định theo eventId. Query toàn ngày phải query nhiều partitions và merge.

### 21.4. Clustering key không tự chia physical load

Nếu partition key là (course_id, activity_day), thêm clustering column eventId **không làm partition tách qua nhiều token**. Đây là nhầm lẫn phổ biến.

### 21.5. Partition lớn và tombstone

Partition quá lớn có thể làm:

- Read một partition tốn I/O.
- Compaction và repair nặng.
- Scan tombstone tốn CPU.
- Thời gian truyền dữ liệu khi phục hồi lâu.

Không đặt mục tiêu mỗi partition đúng một kích thước cố định cho mọi deployment; đo theo dữ liệu thực, engine version và các khuyến nghị vận hành hiện hành.

### 21.6. Materialized count

Nếu mỗi enrollment vừa ghi event bucket vừa cập nhật một row tổng số học viên cho course C101, hàng tổng vẫn hot. Cần tách đường analytics/eventual aggregate hoặc thiết kế counter thích hợp.

### 21.7. LWT không thay sharding

Lightweight transaction **IF NOT EXISTS** hữu ích cho một quyết định unique claim, nhưng tăng phối hợp đồng thuận và không tự phân tán một business key tranh chấp quá nhiều.

Không dùng INSERT thông thường thay cho create-if-absent trong Cassandra rồi nghĩ database sẽ trả duplicate key như MongoDB.

## 22. MongoDB: một document nóng, shard key và hot range

### 22.1. Hashed shard key

Trong MongoDB sharded cluster đã cấu hình phù hợp, có thể dùng hashed shard key:

~~~javascript
sh.shardCollection(
  "academy.learners",
  { learnerId: "hashed" }
);
~~~

Khóa learnerId tuần tự có thể được phân phối tốt hơn giữa các miền hash so với phân mảnh theo thứ tự gốc.

### 22.2. Single hot document vẫn là một điểm

~~~javascript
db.events.updateOne(
  { _id: "E01" },
  { $inc: { viewCount: 1 } }
);
~~~

Nếu hàng chục nghìn writers cùng cập nhật document E01, hash _id cũng không làm một document trở thành nhiều document.

Giải pháp có thể là:

- Cache / coalesce đọc.
- Ghi view events vào collection phân phối.
- Aggregate bất đồng bộ.
- Dùng counter shards nếu độ mới và exactness cho phép.

### 22.3. Ranged shard key và khóa tăng

~~~javascript
sh.shardCollection(
  "academy.orders",
  { createdAt: 1 }
);
~~~

Đây là ví dụ biểu đạt ý tưởng range shard key, không phải khuyến nghị shard key tốt mặc định. Khi mọi order mới có createdAt tăng, các writes có nguy cơ dồn vào range/chunk mới nhất.

Shard key thật còn chịu điều kiện index, cardinality, uniqueness, shard-key selection và cơ chế balancer/split của MongoDB.

### 22.4. Secondary index có thể là nút thắt khác

Một collection phân phối theo learnerId nhưng truy vấn/ghi theo createdAt có thể vẫn gặp chi phí index, hot pages hoặc query fan-out. Phải đo cả index operations và data locality.

### 22.5. Jumbo chunk hoặc range khó chia

Nếu một khoảng dữ liệu tập trung vào shard do phân bố khóa hoặc shard key không đủ phân biệt, quá trình split/move chunk có thể không giải quyết điểm nóng như kỳ vọng. Đánh giá thông tin balancer, chunk/range sizes và giới hạn sharding của phiên bản đang dùng.

### 22.6. Unique index xuyên shard

MongoDB có quy định riêng cho unique indexes trên sharded collections, gắn với shard key và hình dạng index được hỗ trợ. Không mặc định unique email trên từng shard đủ bảo vệ email duy nhất toàn cụm.

Đổi shard key để giảm hotspot phải đồng thời xem các ràng buộc unique hiện tại.

### 22.7. Không tự sửa routing của MongoDB

Trong sharded cluster, mongos và metadata do MongoDB quản lý có vai trò routing. Không nên lấy Java hashCode modulo số shards để truy cập physical shard và bỏ qua cơ chế đó.

## 23. Redis Cluster: hot slot và hot key

### 23.1. Slot mapping

Redis Cluster thường phân phối keys qua **16.384 hash slots**, rồi gán slot cho nodes.

~~~text
Redis key -> hash slot -> node
~~~

Một key nóng không thể được chia chỉ bằng việc chuyển slot sang node khác. Việc chuyển có thể giảm ảnh hưởng đến hàng xóm nhưng tải key vẫn tồn tại.

### 23.2. Hash tags có thể gây hot slot

~~~text
user:{T17}:profile
user:{T17}:settings
user:{T17}:events
user:{T17}:sessions
~~~

Các keys cùng hash tag T17 được định tuyến cùng slot theo quy tắc Redis Cluster.

Điều đó có lợi cho một số multi-key commands/scripts, nhưng T17 cực nóng sẽ tập trung về một slot/node.

### 23.3. Tránh gom không cần thiết

Nếu data của từng user có thể độc lập, thay vì cùng hash tag tenant có thể thiết kế tags theo từng user hoặc resource:

~~~text
user:{T17:U101}:profile
user:{T17:U101}:settings
user:{T17:U102}:profile
~~~

Như vậy mỗi user có nhóm key cùng slot, còn những users khác có thể phân phối. Chọn đúng phạm vi cần atomic multi-key operations, không gom rộng hơn yêu cầu.

### 23.4. Counter shards

~~~text
views:E01:00 -> 120
views:E01:01 -> 133
views:E01:02 -> 115
~~~

Nếu các counter keys được thiết kế phân bố qua slots, writes có thể trải ra. Nhưng:

- Tổng cần nhiều reads.
- Script nguyên tử trên nhiều keys **khác slot** không tự được hỗ trợ như một multi-key atomic operation thông thường.
- Failover/replication/persistence ảnh hưởng durability.

Đây là mẫu hữu ích cho số đếm chấp nhận eventual, không thay nguồn quyết định tiền/tồn kho.

### 23.5. Read hotspot ở cache

Đưa một hot key từ database sang Redis có thể giảm tải DB nhưng khiến một Redis node nghẽn CPU hoặc network.

Với dữ liệu tĩnh hoặc ít thay đổi, cân nhắc local in-process cache, CDN hoặc cache hierarchy để tránh biến Redis thành điểm nóng mới. Cần chính sách invalidation/TTL rõ.

### 23.6. MOVED và ASK

Trong Redis Cluster, client cluster-aware xử lý slot mapping và các redirect liên quan resharding. Việc tự pin một key vào node cũ có thể dẫn đến lỗi khi slot được chuyển.

## 24. Elasticsearch/OpenSearch: hot shard ở indexing và search

### 24.1. Document routing

Search index phân phối documents qua primary shards theo routing key/ID và có thể có replica shards.

Nếu custom routing đặt tất cả documents của tenant T17 vào cùng một primary shard:

~~~text
_routing = T17
~~~

tenant nóng có thể làm shard đó quá tải indexing/search, dù những shards khác rảnh.

### 24.2. Tìm kiếm có thể scatter–gather

Một query không có routing constraint có thể chạy trên nhiều shards. Khi query có hot index/range, p99 bị chi phối bởi shard chậm.

Nếu truy vấn chỉ cần T17 và custom routing phù hợp, cung cấp routing có thể giảm fan-out; nhưng nó đồng thời có nguy cơ gom tất cả T17 vào một primary shard.

### 24.3. Một write index của time series

Với data streams/time-series indices, ghi mới thường vào **current write index/backing index** theo mô hình hệ. Rollover chia dữ liệu theo vòng đời, nhưng không tự đảm bảo mọi write lúc peak được chia đủ đều giữa các primary shards của index hiện tại.

### 24.4. Hot shard do indexing pipeline

Ngoài document routing, còn có:

- Segment creation/merge.
- Refresh pressure.
- Bulk indexing queue.
- Translog/storage I/O.
- Mapping/indexing cost.

Một shard có dữ liệu gần bằng shard khác vẫn có thể nóng nếu nhận phần lớn writes hoặc expensive queries.

### 24.5. Không lạm dụng số primary shards

Tăng số shards có thể giảm tải ở một số trường hợp, nhưng tăng:

- Metadata, file handles và heap overhead.
- Fan-out cho queries.
- Recovery và coordination cost.

Cần cân bằng shard size, indexing distribution, search fan-out và hardware. Không đặt một “số shards chuẩn” cho mọi index.

### 24.6. Search không phải nơi quyết định uniqueness

Search-before-insert theo email có refresh lag và race. Dù search shards đã phân bố tốt, unique claim vẫn phải được cưỡng chế ở nguồn có thẩm quyền.

## 25. Hot consumer partition và event-stream bottleneck

### 25.1. Keyed event stream

Một event log được partition theo courseId:

~~~text
partition = hash(courseId) mod N
~~~

Nếu phần lớn events thuộc course C101, một stream partition/consumer có thể trở thành hotspot.

### 25.2. Tách khóa có làm mất order?

Nếu tách course C101 thành 16 sub-partitions, events của cùng course có thể được xử lý song song nhưng không còn một total order đơn giản trên toàn course.

Nếu dữ liệu yêu cầu:

~~~text
CREATE course
UPDATE course
DELETE course
~~~

phải được áp dụng theo thứ tự, có thể cần một luồng sự kiện quản lý metadata và các luồng sub-entities độc lập.

### 25.3. Tách event theo thực thể con

Một cách:

~~~text
courseId + learnerId -> stream partition
~~~

Các hoạt động của từng learner có thể giữ thứ tự theo learner, trong khi nhiều learners khác nhau xử lý song song.

Đổi lại tổng hợp cấp course phải merge và giữ watermark/lag riêng.

### 25.4. Consumer lag không nhất thiết từ database

Source NoSQL ghi nhanh nhưng một consumer partition chậm có thể làm search index, analytics hoặc cache projection trễ nhiều giờ. Khi sửa hotspot, đo **end-to-end visibility lag** thay vì chỉ nhìn source write latency.

## 26. Hotspot xuyên Region và bản sao

### 26.1. Read hotspot toàn cầu

Một sản phẩm phổ biến ở nhiều quốc gia có thể được cache tại edge/CDN để giảm khoảng cách mạng và read load tới source.

Nếu dữ liệu thay đổi thường xuyên, phải thiết kế invalidation/freshness contract ở từng Region.

### 26.2. Write hotspot không tự mất với active-active

Nếu hai Region đồng thời ghi cùng stock counter hoặc claim username, eventual replication có thể tạo conflict. Nhiều Region nhận ghi không đồng nghĩa mỗi Region được tự cấp cùng một tài nguyên mà không có coordination.

### 26.3. Phân bổ quota trước

Ví dụ 100 vé được phân bổ:

~~~text
Region A: quota 60.
Region B: quota 40.
~~~

Mỗi Region chỉ bán trong quota đã được cấp. Nếu quyền phân bổ được bảo vệ nguyên tử và không có double allocation, các vùng có thể bán song song trong hạn mức local.

Nhưng cần giải quyết:

- Cân bằng quota khi một Region bán hết còn Region khác còn vé.
- Thu hồi/chuyển quota an toàn.
- Failover và outstanding reservations.
- Giao dịch thanh toán chưa rõ kết quả.

Đây là mô hình **escrow/allocated capacity**, không phải tùy tiện chia global counter rồi mỗi nơi tự trừ.

### 26.4. Home Region cho một key

Một cách khác là định tuyến mọi mutation nhạy cảm của một business key về một home Region/leader. Điều này bảo vệ một điểm quyết định nhưng tạo latency cross-Region và ảnh hưởng availability khi home Region không thể truy cập.

## 27. Khi nào phải reshard hoặc migration?

### 27.1. Dịch chuyển shard không bằng chia hot key

Chuyển một hot tenant sang node khỏe có thể giảm contention với tenants khác. Nhưng nếu một item duy nhất cần 100.000 atomic writes/giây, di chuyển nó không tự làm throughput vô hạn.

### 27.2. Chọn mục tiêu

Ví dụ:

~~~text
Old schema:
  PK = COURSE#C101

New schema:
  PK = COURSE#C101#DAY#2026-11-14#B05
~~~

Cần xác định:

- Dữ liệu lịch sử sẽ được migrate toàn bộ hay chỉ dữ liệu mới?
- Các readers cũ và mới cùng hoạt động bao lâu?
- Cần giữ một source of truth nào trong cutover?
- DELETE và update đến muộn được xử lý ra sao?
- Có unique/counter nào bị split sai nghĩa không?

### 27.3. Snapshot và change log

Một migration khi đang ghi có thể theo quy trình:

~~~text
1. Capture snapshot watermark.
2. Copy dữ liệu cũ sang schema mới.
3. Replay mutations sau watermark.
4. Đối soát key, version, tombstone.
5. Cutover router bằng placement epoch.
6. Ngăn writer cũ tiếp tục commit.
7. Quan sát và cleanup sau thời gian an toàn.
~~~

### 27.4. Dual write không tự nguyên tử

Nếu application PUT tới hai tables/buckets riêng biệt, một write có thể thành công còn cái kia thất bại.

Trong giai đoạn migration, cần idempotency, checkpoint, reconciliation và một quy tắc authoritative write. Không gọi hai PUT là một distributed transaction.

### 27.5. Stale router

~~~text
Router X dùng epoch 41: T17 -> Shard A.
Directory epoch 42: T17 -> Shard B.
~~~

Shard A phải từ chối write không còn hợp lệ hoặc có cơ chế forward/redirect được bảo vệ, không nhận mutation tạo hai owner sau cutover.

### 27.6. Tombstone và dữ liệu hồi sinh

Nếu record đã DELETE ở nguồn nhưng bản copy cũ còn ở destination, một replay không có version/tombstone có thể làm nó xuất hiện lại.

Giữ metadata xóa đủ lâu và dùng version/generation để ngăn sự kiện cũ thắng trong quá trình đổi schema.

## 28. Ví dụ Java: chia event theo ngày và hash bucket

### 28.1. Mục tiêu

Thiết kế một bảng hoạt động cho sự kiện rất nổi tiếng:

~~~text
courseId = C101
activityDay = 2026-11-14 (UTC)
eventId = EVT-1001
occurredAt = 2026-11-14T09:15:00Z
~~~

Để tránh một partition cho mọi sự kiện C101 trong ngày, tạo 32 logical buckets:

~~~text
PK = COURSE#C101#DAY#2026-11-14#BUCKET#00..31
SK = TIME#2026-11-14T09:15:00Z#EVT#EVT-1001
~~~

### 28.2. Hàm chọn bucket ổn định

Đoạn Java sau minh họa định tuyến logic bằng String.hashCode. Đây **không phải** thuật toán physical sharding do một sản phẩm NoSQL quản lý:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class ActivityBucketRouter {
    private final int bucketCount;

    public ActivityBucketRouter(int bucketCount) {
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount must be positive");
        }
        this.bucketCount = bucketCount;
    }

    public int bucketOf(String eventId) {
        // Stable trong Java nếu chuỗi đầu vào không đổi.
        // Nếu nhiều ngôn ngữ cùng route, cần thống nhất hash
        // và encoding ở mức protocol.
        return Math.floorMod(eventId.hashCode(), bucketCount);
    }

    public String partitionKey(
            String courseId,
            Instant occurredAt,
            String eventId
    ) {
        LocalDate utcDay = occurredAt
                .atZone(ZoneOffset.UTC)
                .toLocalDate();
        int bucket = bucketOf(eventId);

        return "COURSE#" + courseId
                + "#DAY#" + utcDay
                + "#BUCKET#" + String.format("%02d", bucket);
    }

    public String sortKey(
            Instant occurredAt,
            String eventId
    ) {
        return "TIME#"
                + DateTimeFormatter.ISO_INSTANT.format(occurredAt)
                + "#EVT#" + eventId;
    }
}
~~~

**Điều kiện sử dụng:**

1. eventId phải ổn định khi retry.
2. Cần quy ước phân tách/escape rõ nếu courseId/eventId có thể chứa ký tự phân cách.
3. Mọi writer phải dùng cùng UTC day và quy tắc timestamp.
4. Không âm thầm thay bucketCount từ 32 lên 64 với dữ liệu đã có.
5. String.hashCode là ví dụ dễ hiểu, không nên mặc định phù hợp cho mọi ngôn ngữ hoặc khóa được attacker kiểm soát; production cần lựa chọn hash/partition policy và benchmark cụ thể.
6. Chọn bucket bằng hash eventId không tự tạo idempotency: nếu cùng eventId được INSERT ở cùng key, thao tác phải có điều kiện hoặc overwrite semantics thích hợp.

### 28.3. Nếu hash key không có đủ entropy

Nếu eventId luôn là cùng một giá trị do bug, toàn bộ writes vẫn vào một bucket. Hash tốt không sửa được đầu vào không có độ phân biệt.

Nếu eventId bị tạo từ timestamp được làm tròn tới giây và hàng nghìn events có cùng ID, trước hết phải sửa định danh sự kiện, không tăng số buckets vô hạn.

### 28.4. Đọc toàn bộ ngày

Một reader cần hỏi 32 buckets:

~~~text
for bucket in 00..31:
    query PK = COURSE#C101#DAY#2026-11-14#BUCKET#bucket
~~~

Khi muốn top 100 mới nhất, mỗi bucket có thể trả những phần tử mới nhất theo SK (với comparator phù hợp). Coordinator dùng merge có thứ tự để chọn top 100 toàn cục.

### 28.5. Pseudocode merge

~~~text
readLatest(courseId, day, limit):
    streams = []

    for bucket in allBucketsForSchemaVersion():
        streams.add(queryBucketDescending(
            courseId,
            day,
            bucket,
            limit
        ))

    heap = priorityQueue(orderByOccurredAtAndEventIdDescending)
    pushFirstFromEachStream(heap)

    result = []
    while result.size < limit and not heap.empty:
        item, stream = heap.pop()
        if notAlreadySeen(item.eventId):
            result.add(item)
        pushNextFromStream(heap, stream)

    return result
~~~

Đây là ý tưởng thuật toán. Trong production còn cần:

- Cursor/pagination theo từng bucket.
- Timeout và partial failure semantics.
- Giới hạn số subqueries song song.
- Snapshot/consistency khi writes đang diễn ra.
- Dedupe eventId nếu migration hoặc at-least-once ingestion tạo bản ghi lặp.
- Chính sách cho schema cũ có số buckets khác.

### 28.6. Chọn 32 buckets là một giả định

Không có quy tắc “mọi hệ phải dùng 32”. Phải benchmark 4, 8, 16, 32 hoặc số khác theo peak write throughput, read fan-out và kích thước partition.

## 29. Consistency và tính đúng đắn giới hạn những cách chia tải

### 29.1. Một counter analytics khác một counter inventory

**Page views:** Nếu dashboard trễ 3 giây và có thể hòa giải duplicate, sharded counter/async aggregation là lựa chọn khả thi.

**Inventory:** Nếu hai requests mua chiếc hàng cuối cùng, cả hai không được cùng thắng. Một counter phân mảnh không có cơ chế reservation toàn cục có thể dẫn tới oversell.

### 29.2. Unique key không thể được cấp độc lập ở nhiều buckets

Nếu mỗi request tạo username chọn một random bucket:

~~~text
Request A: username=alice -> bucket 3 -> SUCCESS.
Request B: username=alice -> bucket 7 -> SUCCESS.
~~~

Mỗi bucket có thể enforce unique local nhưng hệ vẫn có hai owners.

Phải định tuyến claim theo **cùng unique business key** và dùng conditional create/unique index có phạm vi đủ mạnh.

### 29.3. Transaction xuyên nhóm dữ liệu

Nếu một order update ba items trên ba shards, việc tách data để giảm hotspot có thể làm giao dịch trước đây trong một partition trở thành cross-partition.

Cần xem:

- Database có hỗ trợ transaction trong phạm vi cần thiết không?
- Latency/throughput của cross-shard transaction ra sao?
- Retry và unknown outcome được xử lý thế nào?
- Có thể thiết kế ledger/outbox/saga phù hợp mà vẫn giữ invariant không?

### 29.4. Causal ordering

Nếu tạo, cập nhật, xóa cùng entity phải theo thứ tự:

~~~text
v10 CREATE
v11 UPDATE
v12 DELETE
~~~

phân tán mỗi event vào một bucket khác nhau có thể khiến consumer nhận v12 trước v10. Một projector cần version/generation và quy tắc chống stale event; hoặc định tuyến cùng entity về một event partition để giữ thứ tự theo entity.

### 29.5. Read-your-writes

Với cache/replicas eventual, người dùng vừa cập nhật hồ sơ có thể đọc lại bản cũ. Có thể dùng:

- Read từ nguồn/leader phù hợp.
- Session token hoặc minimum version.
- Cache invalidation có version.
- Optimistic UI kèm rollback khi thất bại.

Giảm read hotspot không được âm thầm phá một API hứa RYW.

### 29.6. Đọc tổng xuyên buckets không là snapshot nguyên tử

~~~text
Bucket A đọc tại t1: 100.
Bucket B đọc tại t2: 200.
Trong khoảng t1–t2 có nhiều ghi mới.
~~~

Tổng 300 không nhất thiết là giá trị tại một thời điểm duy nhất. Điều này chấp nhận được ở analytics gần đúng, nhưng không thể dùng như số dư khả dụng chính xác.

### 29.7. Rate limit phân tán

Nếu rate limiter được sharding theo Region, mỗi Region có thể cấp 100 requests/s, tổng hai Region thành 200 requests/s.

Nếu cần global cap 100, phải có phân bổ quota hoặc coordination; rate limit local trên mỗi Region không tự tạo global quota.

## 30. Ma trận chọn giải pháp theo loại điểm nóng

| Hiện tượng | Giải pháp có thể xem xét | Đánh đổi chính |
|---|---|---|
Một key bị GET rất nhiều | CDN/cache, read replicas khi cho phép, coalescing | Stale data, invalidation |
Một counter được INCREMENT liên tục | Batch delta, sharded counter, event log | Tổng cần merge; idempotency/exactness |
Một unique claim bị tranh chấp | Conditional create, admission control, queue theo key | Một điểm quyết định khó chia tự do |
Một tenant cực lớn | Directory isolation, sub-buckets theo user/resource | Tenant-wide scans, migration |
Một course có quá nhiều events | Composite PK theo course/day/bucket | Query course/day phải fan-out |
Status=PENDING dồn vào GSI | Status+bucket GSI, queue/read model | Query phải đọc nhiều buckets; eventual GSI |
Timestamp tăng liên tục | Hash/striping trong time bucket | Global range query cần merge |
Query latest data gây read-hot tail | Cache latest window, materialized top-N | Freshness và rebuild |
Redis cùng hash tag quá lớn | Thu hẹp hash tag, tách resources độc lập | Một số multi-key ops khó hơn |
Search primary shard nóng | Routing strategy, index/shard planning | Fan-out/overhead, reindex |
Consumer partition nóng | Partition theo entity con, tăng consumers nếu có partitions | Ordering toàn group |
Một node quá nóng nhưng keys độc lập | Rebalance/move buckets/chunks | Streaming, route epoch, cutover |
Cluster tổng thể quá tải đều | Scale capacity, tối ưu query, load shedding | Chi phí; không chỉ sửa shard key |
Storage lớn nhưng QPS nhỏ | Split/retention/cold storage | Repair/backup/operational complexity |

**Không triển khai nhiều biện pháp cùng lúc mà không có số liệu**, vì rất khó biết thay đổi nào thực sự cải thiện latency và thay đổi nào làm dữ liệu lệch.

## 31. Mô hình thử nghiệm tải có skew

### 31.1. Test đều và test nóng

Một benchmark chỉ tạo userId ngẫu nhiên đồng đều có thể làm mọi shard trông ổn. Nhưng workload production thường lệch mạnh: vài users, campaigns hoặc thời gian nhận phần lớn traffic.

Nên có ít nhất:

1. **Uniform keys:** phân phối đều để đo baseline.
2. **Single hot key:** 70–90% writes vào một key.
3. **Hot tenant:** nhiều keys khác nhau nhưng 70% traffic thuộc một tenant.
4. **Monotonic time:** mọi writes có timestamp/ID tăng theo thời gian.
5. **Burst:** peak kéo dài vài chục giây đến vài phút theo nhu cầu thực.
6. **Read/write mixed:** vừa cập nhật vừa đọc latest và aggregate.

### 31.2. Các chỉ số cần giữ

~~~text
Throughput completed operations/s
p50/p95/p99 end-to-end latency
Timeout/throttling/error rates
Per-shard utilization and skew
Per-key read/write distribution
Retry attempts and queue depth
CDC/index/cache lag
Total and per-tenant resource cost
Correctness and idempotency failures
~~~

### 31.3. So sánh giải pháp công bằng

Ví dụ so:

~~~text
Baseline: one daily PK.
Variant A: daily PK + 8 hash buckets.
Variant B: daily PK + 32 hash buckets.
Variant C: per-device daily PK.
~~~

Giữ payload, traffic shape, hardware và điều kiện đọc tương ứng. Nếu Variant B tăng throughput nhưng global query top 100 mất 5 giây, phải xét cả hai mục tiêu.

### 31.4. Test đúng mức consistency

Đừng chỉ dùng eventual reads để benchmark trong khi production phải đọc mạnh và enforce unique transactions. Kết quả throughput của chế độ consistency yếu không chứng minh chế độ mạnh đáp ứng tải.

### 31.5. So sánh chi phí

Một giải pháp giảm p99 bằng cách nhân 32 lần subqueries có thể tăng network, read capacity và hóa đơn đáng kể.

Đo cost per successful operation, cache hit rate, storage amplification và total background work.

## 32. Fault injection và recovery

### 32.1. Hot partition trong failover

Khi node chứa hot key bị lỗi, traffic có thể chuyển sang replica/leader mới đang cần phục hồi. Nếu mọi clients retry cùng lúc, hot key có thể gây overload ở nơi mới.

Kiểm tra:

- Có retry storm không?
- Leader/replica mới có đủ capacity không?
- Stale reads có vượt contract không?
- Unknown outcomes có làm duplicate increments/charges không?

### 32.2. Cache stampede

Giả lập hot key hết hạn đúng lúc 50.000 clients cùng GET. So sánh:

- Không cache.
- Cache có TTL đơn giản.
- Cache + single-flight.
- Cache + TTL jitter + stale-while-revalidate ở trường hợp cho phép.

Đo source QPS và p99, không chỉ cache hit ratio trung bình.

### 32.3. Consumer crash sau commit

~~~text
Consumer đọc EVT-101.
Consumer increment counter.
Consumer crash trước khi lưu checkpoint.
Consumer restart và nhận lại EVT-101.
~~~

Test count không tăng hai lần nếu contract yêu cầu exactly-once effect. Cần idempotency marker hoặc cơ chế xử lý phù hợp.

### 32.4. Rebalance trong lúc ghi

Trong lúc một hot bucket được chuyển từ Shard A sang B:

- Gửi writes liên tục.
- Giả lập router cache cũ.
- Gây timeout sau commit.
- Đưa một DELETE rồi gửi lại UPDATE cũ.
- Kiểm tra version/tombstone.

Không chấp nhận mất mutation, tạo hai owners hay hồi sinh dữ liệu đã xóa.

### 32.5. Không làm thử nghiệm phá dữ liệu trên production tùy tiện

Fault injection cần môi trường, phạm vi, rollback và telemetry rõ. Với tài nguyên nhạy cảm, phải có phê duyệt vận hành trước khi thử phân vùng mạng hoặc gián đoạn replica.

## 33. Những hiểu lầm phổ biến

| Hiểu lầm | Vì sao sai | Cách tiếp cận đúng |
|---|---|---|
| Có 20 shards nên một key sẽ được chia tải trên 20 shards | Một key ổn định thường có một placement/owner logic | Thay data model hoặc giảm số lần truy cập key |
| Hash đều theo số key nghĩa tải đều | Keys có mức độ nóng rất khác nhau | Đo QPS và bytes theo key |
| Thêm read replicas sẽ tăng throughput UPDATE cùng item | Ghi có thể vẫn cần phối hợp trên một owner | Tách read/write hotspot và consistency |
| Chia counter ra nhiều bucket luôn tốt | Read tổng đắt hơn và có thể không chính xác tức thời | Chọn theo độ mới, idempotency, invariant |
| Sharded counter phù hợp cho số dư | Tổng eventual có thể không giữ số dư không âm | Ledger/escrow/transaction phù hợp |
| Tăng số physical shards giải quyết một hot partition | Hot partition có thể tiếp tục nằm ở một shard | Split logical partition hoặc redesign |
| TenantId là shard key hoàn hảo vì có nhiều tenant | Một tenant có thể chiếm phần lớn traffic | Isolate và subpartition tenant lớn |
| Thêm clustering column chia tải Cassandra | Clustering không thay partition token | Đổi partition key/buckets |
| GSI được DynamoDB tự làm đều nên không cần quan tâm key | GSI có access pattern, hotspots và capacity riêng | Đo/index bucket theo workload |
| Lưu dữ liệu theo ngày luôn hết điểm nóng | Ngày hiện tại vẫn nhận mọi writes | Time bucket kết hợp hash/device bucket |
| Timestamp range key tốt cho mọi ghi mới | Khóa tăng tuần tự gây hot tail | Hash/striping, range theo truy vấn |
| Thêm random suffix vào PK không cần sửa đọc | Read không biết suffix sẽ không tìm thấy dữ liệu | Deterministic mapping hoặc fan-out có kiểm soát |
| Một local unique index mỗi bucket đảm bảo unique toàn tenant | Hai claimant có thể chọn buckets khác nhau | Một unique claim có thẩm quyền |
| Redis hash tags càng rộng càng dễ dùng | Cùng tag quá nhiều keys có thể tạo hot slot | Gom đúng phạm vi cần multi-key atomicity |
| Elasticsearch thêm replicas làm write hot shard biến mất | Primary shard vẫn là điểm indexing chính | Xem routing/primary shard và indexing workload |
| Cache giúp giảm hotspot mà không có nhược điểm | Stale data và stampede có thể xảy ra | TTL/invalidation/version/coalescing |
| Dual writes hai schema chắc chắn cùng thành công | Hai writes độc lập có thể commit một phần | Migration với log/checkpoint/reconciliation |
| Moving hot tenant qua shard khác là xong | Một tenant có thể vượt capacity cả shard mới | Subpartition hoặc thay workload |
| Tăng bucket count từ 16 lên 32 không ảnh hưởng dữ liệu cũ | Hash modulo thay mapping; reader cũ không biết | Schema version và migration |
| Mean latency tốt chứng minh không có hotspot | p99 ở shard nóng có thể rất cao | Đo tail theo shard/key/tenant |
| Global QPS cao nghĩa mọi shard đều hoạt động hiệu quả | Có thể một shard quá tải, nhiều shard nhàn rỗi | Skew ratio và max-share |
| Throttling luôn do database quá nhỏ | Có thể hot key/GSI, client retry, quota hoặc index | Phân loại nguyên nhân trước khi tăng capacity |
| UPDATE sự kiện độc lập không cần quan tâm ordering | Projection/counter có thể bị event muộn làm sai | Version, idempotency và tombstone |
| Có thể trả partial top-N âm thầm khi một shard lỗi | Kết quả có thể sai toàn cục | Contract partial result rõ hoặc fail query |
| Dùng một bucket lớn giúp query ít fan-out nhất nên luôn tốt | Write hotspot và partition size có thể quá lớn | Cân bằng giữa reads và writes |

## 34. Bài tập 1 — phân loại ba kiểu điểm nóng

Một hệ có các hiện tượng:

~~~text
A. 80% GET vào PRODUCT#P101.
B. 70% writes thuộc tenant T17, trên 2 triệu userIds.
C. Tất cả event mới có createdAt tăng dần và đi vào
   chunk mới nhất.
D. Một COUNTER#TOTAL_ENROLLED bị cập nhật 50.000 lần/giây.
E. Status=PENDING chứa 95% items trong GSI.
~~~

Yêu cầu:

1. Phân loại hot key, hot group hoặc hot time range.
2. Nêu metric xác nhận của từng hiện tượng.
3. Đề xuất một giải pháp cho từng trường hợp.
4. Nêu rủi ro consistency hoặc query-cost của giải pháp đó.

## 35. Bài tập 2 — tính mức skew

Một cụm có 10 shards, tổng tải 100.000 ops/giây. Shard nóng nhất nhận 55.000 ops/giây.

1. Tính average ops/giây/shard.
2. Tính MaxShardShare.
3. Tính SkewRatio.
4. Nếu cả 10 shards có capacity 15.000 ops/giây/shard, tại sao tổng capacity lý thuyết chưa chắc giúp request ở shard nóng hoàn tất?
5. Đề xuất cách đo hot keys và xác định có nên split logical partition không.

**Gợi ý:** Average 10.000 ops/giây; max share 55%; skew ratio 5,5.

## 36. Bài tập 3 — hot single-key counter

Ứng dụng gửi 100.000 INCREMENT/giây tới:

~~~text
VIEW_COUNT#E01
~~~

Dashboard chấp nhận dữ liệu chậm tối đa 5 giây và tổng sau đối soát phải đúng.

1. Vì sao hash E01 sang 32 physical shards vẫn chỉ đặt E01 ở một nơi?
2. Đề xuất 16 hoặc 32 counter buckets.
3. Chọn bucket dựa trên eventId ra sao?
4. Nếu một event được giao hai lần, vì sao bucket ổn định vẫn chưa ngăn đếm đôi?
5. Thiết kế checkpoint/dedup phù hợp.
6. So sánh chi phí đọc total trước và sau sharding.

## 37. Bài tập 4 — không oversell khi phân tán writes

Một sản phẩm còn đúng 10 vé. Hệ tạo 10 counter buckets và để mỗi Region trừ một bucket tùy ý.

1. Có đảm bảo tổng quantity không âm không?
2. Vì sao đọc tổng eventual trước khi cấp vé không loại race?
3. Đề xuất conditional reservation ở một nguồn có thẩm quyền.
4. Hoặc phân bổ quota/escrow trước cho hai Region, tổng quota bằng 10.
5. Khi Region A hết quota còn Region B còn, phải chuyển quota thế nào để không cấp trùng?

## 38. Bài tập 5 — hot tenant

Một dịch vụ SaaS có:

~~~text
9.999 tenants: 100 writes/giây mỗi tenant.
Tenant T17:   50.000 writes/giây.
Shard key = tenantId.
~~~

Yêu cầu:

1. Giải thích vì sao hash tenantId không chia writes của T17.
2. So sánh cô lập T17 lên shard riêng với chia T17 thành 32 sub-buckets.
3. Nếu query thường theo learnerId, nên chọn subkey nào?
4. Nếu dashboard cần mọi rows của T17, chi phí đọc thay đổi thế nào?
5. Đề xuất metric bảo đảm tenants nhỏ không bị ảnh hưởng.

## 39. Bài tập 6 — hot time range

Hệ ghi event theo:

~~~text
PK = EVENT#DAY#2026-11-14
SK = TIMESTAMP#eventId
~~~

Mỗi giây tạo 200.000 events trong ngày hiện tại.

1. Vì sao time bucket theo ngày vẫn nóng?
2. Thiết kế thêm hash bucket theo eventId.
3. Với 32 buckets, đọc mọi event trong ngày phải làm gì?
4. Nếu người dùng hỏi latest 100, tại sao không được nối trực tiếp 100 rows từ từng bucket?
5. Thiết kế comparator với timestamp và eventId để sắp thứ tự xác định.
6. Khi event đến muộn, bucket nên dựa trên eventTime hay ingestionTime?

## 40. Bài tập 7 — khóa tăng tuần tự và range sharding

Collection orders có shard key tăng:

~~~text
ORDER#100001
ORDER#100002
ORDER#100003
...
~~~

1. Miền nào nhận phần lớn writes mới?
2. Hashed shard key giúp gì cho những orderIds khác nhau?
3. Query BETWEEN theo orderId phải đánh đổi điều gì?
4. Nếu có thêm index createdAt, hotspot nào có thể vẫn tồn tại?
5. Nếu mỗi order có nhiều updates sau đó, hash orderId có đủ không để giải quyết một order cực nóng?

## 41. Bài tập 8 — DynamoDB GSI

Một bảng có:

~~~text
Base PK = JOB#jobId
GSI PK  = status
GSI SK  = createdAt
~~~

Trong peak, 95% jobs có status=PENDING.

1. Vì sao base PK có độ phân biệt cao vẫn có thể đi kèm hot GSI?
2. Thiết kế status + bucket làm GSI partition key.
3. Những workers muốn đọc tất cả PENDING phải fan-out ra sao?
4. Tại sao eventual GSI không phải công cụ cấp quyền xử lý một job độc quyền?
5. Đề xuất conditional claim trên base item.

## 42. Bài tập 9 — Cassandra

Bảng:

~~~sql
CREATE TABLE events_by_course (
    course_id text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((course_id), occurred_at, event_id)
);
~~~

Course C101 quá nóng.

1. Partition key là gì?
2. Vì sao clustering columns không chia writes sang token khác?
3. Thiết kế bảng có (course_id, day, bucket) làm partition key.
4. Cần biết day và bucket thế nào khi query?
5. Nếu một course tạo hàng trăm triệu events mỗi ngày, chọn bucket size theo metric nào?
6. Ghi nhiều tombstones trong partition lớn có tác động gì tới reads/repair?

## 43. Bài tập 10 — Redis Cluster

Keys:

~~~text
cache:{T17}:user:U001
cache:{T17}:user:U002
cache:{T17}:user:U003
...
~~~

1. Chúng có khả năng cùng hash slot theo rule Redis Cluster không?
2. Lợi ích của cùng slot là gì với một số multi-key operations?
3. Nếu T17 cực nóng, hot slot xuất hiện thế nào?
4. Đề xuất thu hẹp hash tag theo user/resource.
5. Những thao tác đa key trước đây có thể bị ảnh hưởng gì?
6. Vì sao chuyển slot sang node khác chưa chắc giải quyết hot key?

## 44. Bài tập 11 — Elasticsearch routing

Một search index có 12 primary shards. Tất cả documents của tenant T17 sử dụng custom routing=T17 và T17 tạo 80% indexing writes.

1. Vì sao một shard có thể nóng dù index có 12 primary shards?
2. Nếu bỏ custom routing, điều gì thay đổi với search theo tenant?
3. Vì sao chỉ thêm replica shards không tự chia tải primary indexing?
4. Đề xuất dữ liệu hoặc routing scheme khác phù hợp với tenant cực lớn.
5. Nêu ảnh hưởng của reindex/rollover và query fan-out.

## 45. Bài tập 12 — cache stampede

Một hot key được cache TTL=60 giây; 30.000 requests đồng thời tới đúng khi key hết hạn.

1. Dự đoán lượng source GET khi không có coalescing.
2. Single-flight làm giảm GET như thế nào trên một instance?
3. Vì sao 100 instances vẫn có thể tạo nhiều source GET?
4. TTL jitter giúp gì?
5. Khi dữ liệu là giá thanh toán, có được stale-while-revalidate tùy ý không?
6. Cache invalidation cần version/ETag trong tình huống nào?

## 46. Bài tập 13 — mutation retry và idempotency

Consumer xử lý:

~~~text
EVT-101: increment course count by 1.
Database đã commit.
Consumer chết trước khi lưu checkpoint.
Consumer restart và nhận lại EVT-101.
~~~

1. Nếu increment lại, count sai bao nhiêu?
2. Định tuyến cả hai lần vào cùng bucket có tự ngăn duplicate không?
3. Thiết kế marker hoặc sequence để áp dụng đúng một lần.
4. Nếu marker nằm ở store khác counter, rủi ro transaction là gì?
5. Khi không thể bảo đảm atomic effect, reconciliation có vai trò gì?

## 47. Bài tập 14 — hot partition khi failover

Node chứa hot partition có p99 2 giây rồi bị lỗi. Hàng chục nghìn clients retry vào replica vừa nhận quyền.

1. Vì sao retry storm có thể khiến replica mới nhanh chóng quá tải?
2. Đề xuất bounded retry/backoff/jitter.
3. Có thể dùng coalescing hoặc queue theo key để giảm tải không?
4. Phải xử lý unknown-outcome writes thế nào?
5. Quan sát metric nào để phân biệt failover kéo dài với hot key thật?

## 48. Bài tập 15 — thiết kế benchmark

Một nhóm triển khai thử bốn phương án:

~~~text
A: một partition key theo course.
B: course + day.
C: course + day + 8 buckets.
D: course + day + 32 buckets.
~~~

Workload:

- 70% writes vào course C101.
- 25% events còn lại phân phối trên 10.000 courses.
- 5% reads tổng hợp và latest 100 cho C101.
- Burst gấp 10 lần average trong 2 phút.

Hãy:

1. Giữ cùng payload/engine/hardware để so sánh.
2. Thu throughput, p99, throttle và per-shard skew.
3. Đo latency latest 100 và số subqueries.
4. Đo consistency của aggregate và duplicate rate.
5. Thử một failover giữa burst.
6. Chọn phương án phù hợp với SLA/SLO, không chỉ phương án có peak writes/s cao nhất.

## 49. Bài tập 16 — migration schema khi đang ghi

Một hệ chuyển từ:

~~~text
OLD: PK = COURSE#C101
NEW: PK = COURSE#C101#DAY#2026-11-14#BUCKET#b
~~~

Trong lúc copy snapshot, dữ liệu vẫn được UPDATE và DELETE.

1. Xác định snapshot watermark.
2. Mô tả replay mutation sau snapshot.
3. Giải thích vì sao không được bỏ qua DELETE.
4. Thiết kế cutover với routing epoch/fencing.
5. Nếu router cũ ghi vào OLD sau cutover, phải có phản hồi gì?
6. Nếu request timeout sau commit, retry qua NEW phải được đối soát ra sao?
7. Nêu điều kiện để xóa dữ liệu OLD an toàn.

## 50. Bài tập 17 — phân tích một dịch vụ thật

Một nền tảng học tập có triệu chứng:

~~~text
Source DB read p99: 25 ms.
Source DB write p99: 35 ms.
Search visibility lag: 50 phút.
Event stream partition 7 lag: 8 triệu events.
Tất cả event của course C101 dùng stream key=C101.
~~~

1. Bottleneck có nằm ở source DB không?
2. Có phải điểm nóng của một nhóm dữ liệu trên event stream không?
3. Nếu partition stream theo learnerId, ordering cấp course bị ảnh hưởng gì?
4. Đề xuất cách đảm bảo thứ tự theo learner và aggregate theo course.
5. Những metric nào chứng minh search đã bắt kịp sau thay đổi?

## 51. Tổng kết

Điểm nóng trong NoSQL không chỉ là câu chuyện “một node quá bận”. Nó thường bắt đầu từ **một mô hình khóa hoặc truy cập khiến quá nhiều công việc tập trung vào cùng một đơn vị điều phối**.

Ba dạng cốt lõi:

1. **Một khóa nóng:** Cùng item/document/counter nhận rất nhiều GET/UPDATE. Hash không chia một key; cần cache, coalescing, batching, sharded counter hoặc thay đổi cách bảo vệ invariant.
2. **Một nhóm dữ liệu nóng:** Nhiều bản ghi cùng tenant, course, status hoặc hash tag bị gom vào một logical partition/shard/slot. Có thể chia theo subkey, isolate tenant, directory placement hoặc tạo read model.
3. **Một miền thời gian nóng:** Khóa tăng tuần tự hoặc time bucket hiện tại làm mọi writes/queries mới dồn vào range cuối. Có thể kết hợp time bucketing với hash/striping, nhưng phải chấp nhận query fan-out và thiết kế merge.

Những nguyên tắc cần giữ:

- **Phân bố đều số khóa không có nghĩa phân bố đều tải.** Đo request rate, byte, chi phí thao tác và p99 theo key/partition/shard.
- **Không chỉ nhìn bảng chính.** Secondary index, counter, cache, CDC, search và consumer partitions đều có thể là hotspot.
- **Không giải hotspot single-key bằng tăng shard count một cách máy móc.** Muốn phân tải phải thay đơn vị dữ liệu hoặc giảm số lần truy cập.
- **Mọi cách chia bucket đều có chi phí đọc.** Fan-out, merge, pagination và snapshot consistency cần được tính từ đầu.
- **Bảo vệ uniqueness, tồn kho, số dư và ordering.** Một dữ liệu đã “chia đều” nhưng cho phép hai người cùng thắng là thiết kế sai.
- **Giảm tải ngắn hạn và sửa data model là hai việc khác nhau.** Rate limiting, cache và backpressure giúp ổn định sự cố; thay partition key/index giải quyết nguyên nhân sâu hơn.
- **Migration cần giao thức an toàn.** Snapshot, replay, epoch/fencing, idempotency và reconciliation là thiết yếu khi chuyển một hot group sang schema/owner mới.
- **Kiểm thử bằng workload lệch thực tế.** Uniform benchmark thường che single hot key, hot tenant và moving time range.

Câu hỏi cuối cùng khi hệ NoSQL gặp điểm nóng không phải là **“Cần thêm bao nhiêu shard?”**, mà là:

> **“Tải đang tập trung vì cùng một khóa, cùng một nhóm định tuyến hay cùng một miền thời gian; thao tác nào bắt buộc phải có một điểm quyết định, và có thể phân tán phần công việc còn lại bằng cách nào mà vẫn giữ đúng dữ liệu, độ mới và chi phí truy vấn?”**




