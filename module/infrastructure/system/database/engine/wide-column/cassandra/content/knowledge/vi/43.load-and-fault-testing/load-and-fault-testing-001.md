# Thiết kế tải đọc/ghi theo truy vấn nghiệp vụ để đo tải và lỗi phân tán trong Cassandra

## 1. Vì sao đo “100.000 request/giây” vẫn có thể sai bài toán?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Dữ liệu nằm trên các replica được quyết định bởi **partition key**, **replication factor (RF)**, topology datacenter/rack; kết quả đọc/ghi phụ thuộc **consistency level (CL)** và tình trạng từng replica. Cassandra không tự phân bổ chi phí mọi câu CQL như nhau. Hai request cùng trả một hàng có thể khác rất xa về số SSTable phải đọc, độ nóng partition, network, compaction và việc coordinator phải làm.

Giả sử một hệ thống thương mại điện tử thực sự có:

- 60% thao tác xem danh sách đơn mới nhất của khách hàng hoặc tenant trong một ngày.
- 20% xem chi tiết đơn theo mã đơn.
- 15% tạo đơn, ghi vào hai bảng phục vụ hai kiểu đọc khác nhau.
- 5% cập nhật trạng thái đơn, cũng ghi vào hai bảng.

Nếu bài benchmark chỉ chạy `SELECT ... WHERE order_id = ?` trên vài nghìn key được cache và công bố “100.000 QPS”, nó **không đo được** chi phí listing partition dài, ghi nhân đôi, cập nhật đồng thời, tombstone từ TTL, hay các partition nóng xuất hiện khi có chiến dịch bán hàng.

Ngược lại, một benchmark chỉ spam `INSERT` ngẫu nhiên cũng không phản ánh tỷ lệ đọc/ghi hoặc đường truy vấn nghiệp vụ. Khi có node lỗi, một kết quả trung bình “vẫn còn 80% throughput” không cho biết **khách hàng có xem được đơn vừa tạo hay không**.

**Bài này hướng dẫn thiết kế workload từ nghiệp vụ tới CQL/Java**, thu thập số liệu có thể giải thích, và xây ranh giới an toàn để sau đó thử lỗi phân tán. Các con số trong ví dụ là **giả định để lập mô hình**, không phải benchmark thực tế hay cấu hình mặc định được khuyến nghị cho mọi cluster.

### Kết quả học tập

1. Chuyển journey/API của ứng dụng thành **ma trận query CQL** và tỷ lệ xuất hiện thực tế.
2. Phân biệt **logical business operations**, CQL statements, driver attempts và replica-level work.
3. Thiết kế dữ liệu seed và **phân bố khóa nóng/lạnh**, payload, TTL, xóa, trạng thái lifecycle.
4. Đặt **offered load**, giới hạn concurrency, open-loop/closed-loop và các giai đoạn đo tải.
5. Đo p50/p95/p99, throughput đạt được, tỷ lệ lỗi, dữ liệu sai, queue/backpressure và node health.
6. Dùng CQL, Java Driver 4.x, công cụ quan sát và fault matrix mà không đánh đồng một benchmark đơn lẻ với SLO production.
7. Xác định ngưỡng **dừng** khi đo tải, đặc biệt trước khi inject node/network/disk failure.

> **Nguyên tắc:** Bắt đầu từ **hành động người dùng → câu CQL thực tế → partition/replica được tác động → SLO và tính đúng dữ liệu**. Chỉ sau đó mới chọn công cụ tạo tải.

## 2. Bốn đơn vị đo tải không được trộn lẫn

| Cấp độ | Ví dụ | Đơn vị đo | Điều dễ hiểu nhầm |
| --- | --- | --- | --- |
| Business operation | “Tạo một đơn” | operations/s | Một operation có thể thực hiện nhiều CQL |
| CQL execution | `INSERT orders_by_id` | executions/s | Một CQL có thể retry/speculate thành nhiều attempts |
| Driver attempt | Gửi tới coordinator, có thể thử lại | attempts/s | Timeout chưa chắc mutation chưa được áp dụng |
| Replica/internal work | Coordinator gửi read/write tới replica | internal messages, CPU, I/O | Không suy đơn giản bằng CQL rate × RF cho mọi read/write |

Với một thao tác tạo đơn phải ghi hai bảng, một lần “create order” có thể tạo **ít nhất hai câu INSERT**. Với retry, một thao tác HTTP có thể sinh thêm attempts; với paging, một lần mở danh sách có thể fetch nhiều page.

Công thức kế hoạch đơn giản:

\[
R_{\text{CQL,offered}} \approx \sum_{i=1}^{n} R_{\text{business},i}
\times \overline{Q}_{i}
\]

Trong đó:

- \(R_{\text{business},i}\): số business operations/s thuộc loại \(i\).
- \(\overline{Q}_{i}\): số CQL executions trung bình trên **một** business operation loại \(i\), bao gồm các lần fetch page được thiết kế trước.
- Chưa tính retries/speculative executions; phải đo chúng riêng.

**Đây là phép ước tính input, không phải công thức đo CPU/disk hay số replica messages.** Một statement có thể tác động nhiều SSTables, replica hoặc token ranges khác nhau; CL và RF ảnh hưởng theo cách phụ thuộc read/write path.

## 3. Xây workload từ bản đồ hành trình nghiệp vụ

### Bước 1 — Liệt kê hành động người dùng hoặc hệ thống

Một bảng đầu vào:

| Journey | API/worker | Hành vi chính | Tiêu chí đúng |
| --- | --- | --- | --- |
| Xem danh sách | `GET /tenants/{t}/orders?day=D` | `SELECT` một partition theo ngày, có paging | Thứ tự mới nhất trước, không lọt tenant khác |
| Xem chi tiết | `GET /orders/{id}` | `SELECT` theo full partition key | Trả đúng trạng thái, không trộn đơn |
| Tạo đơn | `POST /orders` | Hai `INSERT` vào hai bảng query | Không mất đơn/nhân đôi logical order |
| Đổi trạng thái | Worker thanh toán | Hai `UPDATE` theo full keys | Status phản ánh quy trình chuyển trạng thái |
| Hết hạn/xóa dữ liệu | Retention job | TTL/delete theo policy | Không giữ dữ liệu quá hạn, biết tombstones |

Không nhất thiết mỗi API tương ứng đúng một CQL. Mọi query ẩn trong repository, cache fallback, permission lookup, truy vấn idempotency hoặc fan-out theo nhiều ngày đều phải được đưa vào mô hình.

### Bước 2 — Ghi rõ query shape, không chỉ tên API

Với mỗi hành động, lưu:

- CQL template/prepared statement và các **bound variables** có ý nghĩa.
- Partition key và clustering predicate; có `IN`, range, index/SAI hoặc fan-out không?
- Số rows/bytes trả về; page size, xác suất fetch page tiếp.
- Tỷ lệ read/write, đồng thời và mốc cao điểm.
- CL, local DC, request timeout, retry/idempotency.
- Những hành động khác phải xảy ra trước đó (ví dụ **tạo đơn rồi xem chi tiết**).
- Điều kiện dữ liệu: còn sống, vừa ghi, TTL sắp hết, tombstone, sửa lại.

### Bước 3 — Phân nhóm thay vì lấy một tỷ lệ trung bình

Không gộp hai loại `SELECT` khác hẳn:

```text
READ_DETAIL:
  WHERE order_id=?
  1 partition, tối đa 1 row, payload nhỏ

READ_LIST:
  WHERE tenant_id=? AND order_day=?
  1 partition, nhiều clustering rows
  1–3 page, có thể chạm nhiều SSTables/tombstones
```

Một trung bình “80% reads” giấu đi khác biệt quan trọng. Cần dashboard tách theo **query template** và phân khúc khóa nóng/lạnh, kích thước hàng, DC, CL.

## 4. Ví dụ lập tỷ lệ tải và fan-out thành CQL

Giả định **1.000 logical operations/s** ở giờ cao điểm:

| Hành động | Tỷ lệ | Business ops/s | CQL executions/operation ở mô hình |
| --- | ---: | ---: | --- |
| READ_LIST | 60% | 600 | Trung bình 1,4 lượt fetch page |
| READ_DETAIL | 20% | 200 | 1 SELECT |
| CREATE_ORDER | 15% | 150 | 2 INSERT |
| UPDATE_STATUS | 5% | 50 | 2 UPDATE |
| **Tổng** | **100%** | **1.000** | Phụ thuộc hành động |

Khi chưa tính retry, offered CQL rate xấp xỉ:

\[
600 \times 1{,}4 + 200 \times 1
+ 150 \times 2 + 50 \times 2 = 1440\ \text{CQL executions/s}
\]

Tách:

- Reads: \(840+200=1040\) CQL/s.
- Writes: \(300+100=400\) CQL/s.
- Read/write ở cấp business: 80%/20%.
- Read/write ở cấp **CQL executions**: khoảng 72,2%/27,8%.

**Lưu ý:** tỷ lệ reads/writes sẽ thay đổi khi paged reads nhiều trang hơn, dual writes bị retry hoặc application bổ sung kiểm tra quyền/transaction ledger. Vì vậy không nên cấu hình generator chỉ theo “80% read, 20% write” rồi kết luận đã phản ánh hệ thống.

### Nếu có retries?

Giả sử driver/gateway tạo thêm một phần attempts do timeouts, **không** đơn giản cộng mọi attempt như một business operation thành công. Báo cáo riêng:

```text
logical_operations_offered
logical_operations_completed_successfully
cql_executions_requested
driver_attempts
retries_and_speculations
unknown_write_outcomes
```

Với counter/list append/LWT và TTL, retry mù có thể làm kết quả sai. Không được đánh đổi correctness để tăng số “successful requests”.

## 5. Schema lab: hai bảng theo hai đường đọc nghiệp vụ

Lab giả định datacenter `dc1` với **ba replica** để minh họa `LOCAL_QUORUM` RF3. Nếu chỉ có một node, hãy đổi RF phù hợp **chỉ trong lab**; RF1 không thể mô phỏng quorum 2/3 hay lỗi một replica.

```sql
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS load_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    tenant_id text,
    order_day date,
    created_at timestamp,
    status text,
    total_cents bigint
);

CREATE TABLE IF NOT EXISTS load_lab.orders_by_tenant_day (
    tenant_id text,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    total_cents bigint,
    PRIMARY KEY ((tenant_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
```

**Mục đích của từng bảng:**

- `orders_by_id` hỗ trợ `GET /orders/{id}`: partition key `order_id`.
- `orders_by_tenant_day` hỗ trợ listing đơn của một tenant/ngày: partition key `(tenant_id, order_day)` và clustering theo `created_at DESC, order_id ASC`.

Đây là **denormalization có chủ đích**. Một logical order được biểu diễn ở hai bảng theo hai query shapes. Muốn benchmark đúng `CREATE_ORDER` phải đo cả hai writes, lỗi từng write và cơ chế reconciliation nếu một bảng đã ghi mà bảng kia chưa ghi. Không giả định hai `INSERT` tới **hai partition khác nhau** là transaction ACID chỉ vì nằm trong cùng service.

### Query templates ứng với ma trận

```sql
-- READ_DETAIL: một order_id, thường tối đa một row.
SELECT order_id, status, total_cents, tenant_id, order_day
FROM load_lab.orders_by_id
WHERE order_id = ?;

-- READ_LIST: đúng composite partition key, có thứ tự clustering.
SELECT created_at, order_id, status, total_cents
FROM load_lab.orders_by_tenant_day
WHERE tenant_id = ? AND order_day = ?
LIMIT 100;

-- CREATE_ORDER — write thứ nhất.
INSERT INTO load_lab.orders_by_id (
    order_id, tenant_id, order_day, created_at, status, total_cents
) VALUES (?, ?, ?, ?, ?, ?);

-- CREATE_ORDER — write thứ hai.
INSERT INTO load_lab.orders_by_tenant_day (
    tenant_id, order_day, created_at, order_id, status, total_cents
) VALUES (?, ?, ?, ?, ?, ?);

-- UPDATE_STATUS trong bảng đọc chi tiết.
UPDATE load_lab.orders_by_id
SET status = ?
WHERE order_id = ?;

-- UPDATE_STATUS trong bảng đọc danh sách:
-- phải có đầy đủ partition + clustering key.
UPDATE load_lab.orders_by_tenant_day
SET status = ?
WHERE tenant_id = ? AND order_day = ?
  AND created_at = ? AND order_id = ?;
```

Giữ nguyên logical `order_id`, `tenant_id`, `order_day` và `created_at` khi ghi hai bảng. Nếu lần retry tạo `order_id` mới, generator có thể vô tình nhân đôi dữ liệu thay vì mô phỏng retry đúng nghĩa.

### Không dùng `ALLOW FILTERING` để giả lập business query

Truy vấn như `SELECT * FROM orders_by_id WHERE status='PAID' ALLOW FILTERING` có thể quét lượng lớn dữ liệu và **không đại diện** cho endpoint đọc theo ID. Nếu nghiệp vụ cần tìm đơn theo status, phải có bảng/index/query plan riêng và **một dòng workload riêng**.

## 6. Phân bố khóa: tenant nóng, partition nóng và “long tail”

Khi load generator chọn khóa, hai cực đoan đều sai:

- **Uniform toàn bộ keys** trong khi production có một số tenant rất nóng.
- **Chỉ một key/partition** trong khi production có hàng triệu tenants phân bố rộng.

Một mô hình phân bố chỉ để minh họa:

| Nhóm tenant | Tỷ lệ tenant | Tỷ trọng request |
| --- | ---: | ---: |
| Top 1% “rất nóng” | 1% | 45% |
| Nhóm tiếp theo | 9% | 35% |
| 90% còn lại | 90% | 20% |

Đây là cấu hình **skew giả định**, không phải định luật Zipf hay dữ liệu sản xuất. Phải lấy histogram/top-k an toàn từ telemetry đã giảm dữ liệu nhạy cảm; không copy raw tenant IDs production sang lab.

### Phân bố cần đo ở nhiều cấp

1. **Tenant:** request rate theo tenant.
2. **Partition:** cùng tenant nhưng ngày hiện tại và ngày quá khứ có mật độ đọc khác nhau.
3. **Clustering range:** người dùng thường đọc “20 đơn mới nhất”, ít khi đọc toàn bộ lịch sử.
4. **Order ID:** một đơn đang xử lý thanh toán có thể được đọc/làm mới nhiều lần.
5. **Trạng thái:** `CREATED`/`PAID`/`CANCELLED` có tỷ lệ khác nhau.
6. **Tuổi dữ liệu:** đơn mới, đơn cũ, đơn gần hết retention, dữ liệu vừa update/xóa.

### Độ nóng ảnh hưởng gì?

Một partition key quá nóng có thể làm tập replica sở hữu nó chịu tải lệch, dù tổng QPS của cluster chưa cao. RF3 vẫn chỉ đặt **ba bản sao của partition đó**; tăng số node không tự phân tán một partition nóng lên mọi node.

Đọc một partition có hàng triệu clustering rows cũng có thể gây read amplification, SSTables/read và tombstone scans. `setPageSize(20)` điều tiết response, không biến wide partition thành nhỏ.

### Dùng bucket hay shard?

Nếu `(tenant_id, order_day)` quá lớn, cân nhắc bucket giờ hoặc shard có quy tắc; nhưng như vậy truy vấn listing có thể cần **fan-out + merge** trên nhiều partitions. Load model phải tính thêm số CQL và thuật toán trộn, không chỉ đo một select của bảng cũ.

## 7. Thiết kế dữ liệu seed đại diện về dung lượng và vòng đời

Benchmark với **10 rows và không có tombstone** trên một node vừa khởi động không phản ánh cluster giữ dữ liệu nhiều tháng.

Các chiều cần lập kế hoạch:

| Chiều dữ liệu | Mẫu seed cần có | Tại sao |
| --- | --- | --- |
| Số partitions | Đủ số tenant × buckets theo phân bố | Ảnh hưởng token distribution/cache |
| Rows/partition | Median, p95, p99, và một số partition nóng | Ảnh hưởng listing/range reads |
| Row size | Small/medium/large payload thật về byte | Ảnh hưởng network, heap, compaction |
| Data age | Dữ liệu mới và cũ qua nhiều SSTables | Ảnh hưởng cache và read amplification |
| TTL | Một phần dữ liệu có tuổi thọ khác nhau | Tạo expiration/tombstones |
| Delete/update | Có tỷ lệ mutation theo nghiệp vụ | Thay đổi SSTable density và GC pressure |
| Trạng thái | Nhiều status, read/write transitions hợp lệ | Tránh toàn bộ data ở một trạng thái vô nghĩa |
| Hot/cold | Nhiều read vào một số buckets, long tail còn lại | Đo cache và replica imbalance |
| Compression/compaction | Chính sách giống môi trường mục tiêu | Chi phối disk space/write amplification |
| Multi-DC | Data replication và routing thật khi có yêu cầu | Kiểm tra độ trễ và headroom theo DC |

### Ước lượng dung lượng mà không ngụy tạo một con số chính xác

Ví dụ 2 triệu logical orders, mỗi đơn **được ghi hai bảng**. Tổng logical row count ở hai bảng đã khoảng 4 triệu trước TTL, metadata, index và tombstone. Nhưng **không được lấy row count × payload bytes × RF làm dự báo disk chính xác**, vì còn:

- SSTable encoding, partition/clustering metadata và compression.
- Index, Bloom filter, summary và memtable.
- Replication giữa DC/rack.
- Compaction tạo temporary disk space và write amplification.
- Tombstones, overwritten cells, snapshots/backups.

Kế hoạch capacity cần đo disk footprint sau bulk load, sau compaction ổn định và dưới write/update/TTL. Nhớ dành **headroom cho compaction và node recovery**, không nạp đầy disk chỉ để đạt một kích thước dữ liệu.

### Seed đúng identity và hành vi đọc sau ghi

Generator nên giữ một danh mục `order_id` đã seed để `READ_DETAIL` trúng dữ liệu thật. Nếu chọn UUID ngẫu nhiên mọi lần đọc, đa số query chỉ trả “không tìm thấy”, làm benchmark quá dễ và sai mục đích.

Một tỷ lệ 404 hợp lệ có thể có, nhưng phải được **mô hình hóa có chủ đích**, ví dụ 2% detail lookups miss, không do lỗi tạo khóa.

## 8. RF, CL và DC: mỗi workload class có contract riêng

Với `NetworkTopologyStrategy` RF3 ở `dc1`, một read/write thông thường:

| CL | Yêu cầu phản hồi local | Ý nghĩa thực hành |
| --- | --- | --- |
| `LOCAL_ONE` | Ít nhất một replica local | Độ trễ thấp hơn trong một số tình huống, nhưng độ mới/bảo đảm khác |
| `LOCAL_QUORUM` | Ít nhất hai trong ba replica local | Thường chọn khi cần cân bằng consistency/availability |
| `ALL` trong một DC RF3 | Cả ba replica | Một replica lỗi có thể làm request không đạt CL |

Quy tắc quorum thường là \(\lfloor RF/2\rfloor+1\); với RF3 là 2. Trong nhiều DC, `LOCAL_QUORUM` thuộc local DC, không phải quorum toàn bộ keyspace.

**Tải với CL=ONE không thay thế được tải với CL=LOCAL_QUORUM.** Chênh lệch về tail latency, số replica ACK và availability khi lỗi có thể đáng kể. Ghi CL, local DC, RF và keyspace trong tất cả kết quả.

### Một “read-after-write test” cũng cần contract

- Ghi và đọc cùng key với CL được chọn, trên DC nào?
- Có time lag giữa write và read không?
- Có concurrent writers/clock skew không?
- Có được phép eventual visibility hay yêu cầu user đọc được đơn vừa tạo?
- Hai bảng denormalized có thể lệch nhau tạm thời sau partial failure không?

Nếu một câu `INSERT` ở bảng A đã thành công nhưng bảng B bị timeout, lỗi nghiệp vụ là **cross-table projection drift**, không nhất thiết lỗi replication của Cassandra. Thêm phép đối soát tương ứng thay vì chỉ đếm HTTP 200.

## 9. Kiểm tra semantics của mutation trước khi bật retry

| Mutation | Rủi ro khi gửi lại | Gợi ý thiết kế workload |
| --- | --- | --- |
| `SELECT` thuần đọc | Tăng tải, thay đổi kết quả nếu dữ liệu sống | Retry có giới hạn nếu idempotent |
| Upsert cùng khóa và giá trị ổn định | Có thể ghi đè concurrent writer nếu timestamp mới hơn | Dùng operation ID, version/state transition phù hợp |
| `counter = counter + 1` | Có thể cộng hai lần sau timeout | Đừng auto retry; đếm event ID và reconciliation |
| `list = list + [...]` | Có thể append trùng | Dùng item identity và data model phù hợp |
| `USING TTL` | Retry muộn có thể thay expiration | Lưu hạn tuyệt đối nếu policy yêu cầu |
| `INSERT ... IF NOT EXISTS` | Retry có thể trả `[applied]=false` dù lần đầu đã tạo | Đối chiếu operation ID và trạng thái |
| Dual-write hai bảng | Có thể thành công một bảng, thất bại bảng kia | Track outcome từng write và reconcile |

**Đừng đánh dấu mọi statement `setIdempotent(true)` chỉ để driver retry mạnh hơn.** Driver không biết nghiệp vụ tiền/tồn kho. Workload generator còn phải tạo cùng logical order ID khi replay một operation, không sinh UUID mới rồi coi là thành công.

## 10. Offered load, achieved throughput và concurrency

Một bài test cần công bố:

- **Offered load:** generator dự định gửi bao nhiêu logical operations/s.
- **Admitted load:** bao nhiêu operation thực sự vượt qua bộ giới hạn in-flight.
- **Achieved throughput:** bao nhiêu operation hoàn thành thành công mỗi giây.
- **Failures/unknown:** bao nhiêu request timeout/rejected/failed/mutation outcome chưa chắc chắn.
- **Backlog/queue wait:** bao nhiêu operation phải chờ client-side trước khi gửi CQL.

Nếu offered 1.000 ops/s, nhưng chỉ 700 được nhận và 650 hoàn thành thành công, không báo kết quả “650 ops/s, lỗi 0%” bằng cách **bỏ 300 rejected và 50 failures ra khỏi mẫu**.

### Little's Law: làm rõ quan hệ QPS và độ trễ

Ở trạng thái ổn định theo các giả định của định luật, số công việc đồng thời trung bình xấp xỉ:

\[
L \approx \lambda W
\]

Ví dụ offered 1.000 ops/s, latency trung bình 80 ms nếu đã ổn định, thì **khoảng 80 operations** có thể đang in-flight. Nếu tail latency đẩy lên 500 ms hoặc server chậm dần, nhu cầu in-flight cao hơn; đây không phải giới hạn cứng.

**Không** dùng phép tính này để suy p99 hay kết luận pool 80 connections là đủ. Driver có multiplexing, requests có nhiều CQL, concurrent workloads và variance; phải đo in-flight thực tế, queue depth và deadline.

### Open-loop và closed-loop

| Mô hình | Generator làm gì? | Lợi thế | Rủi ro khi diễn giải |
| --- | --- | --- | --- |
| **Closed-loop** | Mỗi worker chờ hoàn thành rồi gửi request tiếp | Mô phỏng số users cố định có think time | Khi server chậm, offered load tự giảm, dễ che tail latency |
| **Open-loop** | Phát request theo lịch/tốc độ dự định, độc lập với thời gian hoàn tất | Đo khả năng chịu offered QPS và overload | Phải giới hạn queue/in-flight, tính requests bị shed |
| **Hybrid** | Users/session flow + global rate/tenant quota | Mô phỏng hành vi thực hơn | Cần báo cả offered và completed, tránh định nghĩa mơ hồ |

Trong closed-loop, “100 users” không đồng nghĩa “1000 QPS”; QPS phụ thuộc think time, số request/flow và latency. Trong open-loop, khi server bị stall, lịch phát request vẫn tiếp tục; phải **đếm requests đến hạn nhưng không gửi được** để tránh che overload.

### Coordinated omission

Nếu generator chỉ đo latency của những request **đã được gửi** và ngừng phát request lúc server tắc, percentile có thể đẹp giả. Khi đánh giá overload, cần đo:

1. Latency **end-to-end** từ thời điểm logical operation đáng lẽ được phát.
2. Thời gian xếp hàng/admission.
3. Latency của driver/CQL thực sự đã gửi.
4. Requests bị từ chối hoặc rơi deadline trước khi gửi.

Không sửa histogram bằng cách tự thêm “số 0” cho missed requests. Chọn generator/metric phù hợp mô hình tải, ghi rõ cách tính và tránh tuyên bố p99 của một population mà thực chất đã bỏ các request chậm.

## 11. Thiết kế các giai đoạn đo tải và ngưỡng dừng

| Giai đoạn | Mục tiêu | Ví dụ trên lab cô lập |
| --- | --- | --- |
| **Preflight** | Node/replica/keyspace/CL, dữ liệu seed, auth/TLS | Query mẫu đúng, không còn repair/compaction bất thường trước test |
| **Warm-up** | Ổn định JIT, driver pools, caches, memtables | Tải vừa đủ để quan sát thay đổi ban đầu |
| **Baseline** | Độ trễ và lỗi ở tải bình thường | 30% peak theo workload mix |
| **Ramp** | Tìm vùng p99 bắt đầu xấu và saturation | 50%, 70%, 90%, 100% offered peak |
| **Steady-state peak** | Đo SLO tại peak dự kiến | Giữ tải đến khi số liệu đủ ổn định |
| **Burst** | Đánh giá tăng đột ngột có giới hạn | Thêm một đợt tải cao ngắn được phê duyệt |
| **Soak** | Quan sát compaction, GC, tombstones, disk lâu hơn | Giữ tải đại diện trong thời gian đủ nhìn nền |
| **Cool-down** | Quan sát backlog và recovery về baseline | Dừng phát workload, kiểm tra pending tasks |

Thời lượng và tỷ lệ chỉ là **mẫu lập kế hoạch**, phải điều chỉnh theo workload và SLO. Đặc biệt với Cassandra, test vài phút có thể không đi qua nhiều vòng flush/compaction/TTL, nên không đủ nói về steady-state lâu dài.

### Ngưỡng dừng cần được thống nhất trước test

Ví dụ điều kiện dừng:

- p99 HTTP hoặc CQL vượt ngưỡng hợp đồng liên tục theo một cửa sổ xác định.
- Lỗi `Unavailable`/timeout vượt error budget của test.
- Disk free thấp hơn **headroom đã được phê duyệt** cho compaction/streaming.
- Pending compaction/tasks hoặc dropped messages tăng liên tục không hồi.
- Một node chuyển trạng thái lỗi ngoài kịch bản test.
- Không bảo đảm safety/correctness của dual writes, operation IDs hoặc authentication.
- Generator đã quá tải CPU/GC và không còn phát chính xác offered rate.

Không chọn một con số % disk/CPU phổ quát nếu chưa biết compaction strategy, dữ liệu, ổ đĩa và replica repair window. **Một guardrail thiếu dữ liệu vẫn tốt hơn việc mặc định “cứ đẩy đến khi cluster chết”**.

## 12. Các chỉ số phải đo cùng nhau

| Lớp | Metric | Dùng để trả lời |
| --- | --- | --- |
| User/API | Logical success/error, HTTP p95/p99, deadline | Người dùng chịu trải nghiệm gì? |
| Load generator | Offered/admitted/completed/rejected, scheduling lag, CPU | Có thực sự tạo đúng tải không? |
| Java Driver | CQL latency, retry/attempts, in-flight, connection pool, local DC | Bottleneck nằm ở driver/route? |
| Query template | `READ_LIST`/`READ_DETAIL`/`CREATE`/`UPDATE` latency/timeout riêng | Loại truy vấn nào xấu trước? |
| Cassandra node | Read/write latency, pending work, dropped messages | Replica/coordinator đang bão hòa? |
| Storage | SSTables/read, tombstones, compaction backlog, disk utilization | Read/write amplification tăng? |
| JVM/OS | Heap/GC, CPU, network, disk latency, file descriptors | Có bottleneck nền không? |
| Consistency | RF/CL/DC, unavailable/timeouts, sai khác giữa bảng | Đủ replica và đúng dữ liệu không? |
| Correctness | Missing orders, duplicate logical IDs, status drift | Benchmark có âm thầm làm sai dữ liệu? |

### Percentiles và số lượng mẫu

Không lấy trung bình p99 của từng node để thành p99 toàn cluster. Nếu dùng histogram, phải hợp nhất **các mẫu/histogram phù hợp**, kèm labels/cửa sổ thời gian và số mẫu; percentile trung bình không có ý nghĩa thống kê như vậy.

Một nhóm truy vấn chỉ có vài chục mẫu mỗi phút thì p99 rất nhiễu. Báo:

- Số request trong cửa sổ.
- p50, p95, p99 (và p99.9 nếu số mẫu đủ).
- Timeout/rejection/error count **bên cạnh** percentiles.
- Percentiles theo DC, CL, hot/cold, row-size class.

**Không lọc bỏ timeouts rồi chỉ báo p99 của những response nhanh.** Timeouts phải được tính vào trải nghiệm SLO theo một quy tắc được công bố; percentile của successes có thể dùng như số phụ, không thay thế tỷ lệ lỗi.

## 13. Chọn công cụ phù hợp thay vì để công cụ quyết định workload

| Công cụ/đường đo | Khi nào dùng? | Giới hạn cần nhớ |
| --- | --- | --- |
| `cassandra-stress` | Thăm dò khả năng CQL/driver/cluster với những workload được công cụ hỗ trợ | Workload mặc định thường **không phải** business journey của bạn |
| NoSQLBench hoặc framework workload tương đương | Mô hình nhiều query/parameters và workload phase | Phải xác minh plugin, syntax, phiên bản và phân bố key |
| YCSB và workload benchmark chuẩn | So sánh các pattern đọc/ghi có thể lặp lại | Phân bố và semantics của workload chuẩn có thể khác ứng dụng |
| Java Driver 4.x generator tùy chỉnh | Cần đúng prepared CQL, CL, page behavior, hot keys, order lifecycle | Phải xây đo đạc, giới hạn tải, rate scheduler và safety |
| k6/Gatling/JMeter qua HTTP API | Đo cả authentication, Spring Boot, service logic và CQL | Không cô lập được chi phí Cassandra nếu không instrument từng tầng |
| Synthetic traffic replay đã khử dữ liệu nhạy cảm | Tái hiện tần suất/mix/bursts gần thực tế | Không được copy PII/secret; replay còn phụ thuộc state dữ liệu |

Nếu dùng `cassandra-stress`, câu lệnh, custom user profile, throttle và các metric **thay đổi theo bản công cụ đi kèm distribution**; hãy đọc help của bản được pin trong lab. Đừng viết một command từ tài liệu phiên bản khác và tự tin rằng nó đo đúng workload.

### Nên dùng tối thiểu hai góc nhìn

**A — CQL-level test:** Java Driver hoặc công cụ gửi prepared statements trực tiếp tới Cassandra, giúp tách routing, RF/CL, disk, compaction và chi phí query.

**B — API-level test:** đi qua HTTP controller, auth, validation, caching, multiple CQL, serialization và downstream calls, để thấy SLO thực của người dùng.

Đừng so **1000 API requests/s** với **1000 CQL/s** như hai đại lượng tương đương. Ghi lại số CQL per API operation và tổng attempts.

## 14. Java Driver 4.x: bộ phát tải bất đồng bộ có giới hạn

Ví dụ sau dùng Java 17 và Java Driver 4.x để minh họa **một JVM phát tải theo tỷ lệ 60/20/15/5**, không chặn callback và không gửi vô hạn. Nó có:

- `ScheduledExecutorService` phát logical operations theo tốc độ danh định.
- `Semaphore` giới hạn số operations đang in-flight.
- `PreparedStatement` giữ query shapes đúng mục 5.
- `CompletionStage`/`thenCompose` để nối hai writes của một business operation **không dùng `join()`**.
- Một danh sách `OrderKey` được seed trước, có thể **lặp phần tử theo trọng số** để mô phỏng hot keys.
- Bộ đếm offered, rejected, acknowledged, error và latency tổng.

**Quan trọng:** Code chỉ là generator cơ sở. Nó **chưa** ghi histogram p99, scheduling lag, retries per attempt, outstanding partial writes, per-DC metrics hay kiểm tra correctness. Không tự tuyên bố nó là framework benchmark production chỉ vì có `Semaphore`.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class BusinessWorkloadGenerator implements AutoCloseable {
    public record OrderKey(
        UUID orderId, String tenantId, LocalDate day,
        Instant createdAt) {}

    private enum Kind {
        READ_LIST, READ_DETAIL, CREATE_ORDER, UPDATE_STATUS
    }

    private final CqlSession session;
    private final List<OrderKey> weightedSeedKeys;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
    private final Semaphore inFlight = new Semaphore(128);

    private final PreparedStatement readList;
    private final PreparedStatement readDetail;
    private final PreparedStatement insertById;
    private final PreparedStatement insertByDay;
    private final PreparedStatement statusById;
    private final PreparedStatement statusByDay;

    private final LongAdder offered = new LongAdder();
    private final LongAdder rejected = new LongAdder();
    private final LongAdder acknowledged = new LongAdder();
    private final LongAdder errors = new LongAdder();
    private final LongAdder totalDurationNanos = new LongAdder();
    private volatile ScheduledFuture<?> scheduled;

    public BusinessWorkloadGenerator(
            CqlSession session, List<OrderKey> weightedSeedKeys) {
        if (weightedSeedKeys == null || weightedSeedKeys.isEmpty()) {
            throw new IllegalArgumentException("Seed keys required");
        }
        this.session = session;
        this.weightedSeedKeys = List.copyOf(weightedSeedKeys);

        readList = session.prepare(
            "SELECT created_at, order_id, status, total_cents " +
            "FROM load_lab.orders_by_tenant_day " +
            "WHERE tenant_id=? AND order_day=? LIMIT 100");

        readDetail = session.prepare(
            "SELECT order_id, status, total_cents " +
            "FROM load_lab.orders_by_id WHERE order_id=?");

        insertById = session.prepare(
            "INSERT INTO load_lab.orders_by_id " +
            "(order_id, tenant_id, order_day, created_at, " +
            "status, total_cents) VALUES (?, ?, ?, ?, ?, ?)");

        insertByDay = session.prepare(
            "INSERT INTO load_lab.orders_by_tenant_day " +
            "(tenant_id, order_day, created_at, order_id, " +
            "status, total_cents) VALUES (?, ?, ?, ?, ?, ?)");

        statusById = session.prepare(
            "UPDATE load_lab.orders_by_id " +
            "SET status=? WHERE order_id=?");

        statusByDay = session.prepare(
            "UPDATE load_lab.orders_by_tenant_day " +
            "SET status=? WHERE tenant_id=? AND order_day=? " +
            "AND created_at=? AND order_id=?");
    }

    // Ví dụ: 200 operations/s danh định; không dùng rps cực cao
    // với một scheduler thread rồi coi scheduling là chính xác.
    public void start(int targetRps) {
        if (targetRps < 1 || targetRps > 5_000) {
            throw new IllegalArgumentException("Rate outside lab range");
        }
        if (scheduled != null) {
            throw new IllegalStateException("Already started");
        }
        long periodNanos = TimeUnit.SECONDS.toNanos(1)
            / targetRps;
        scheduled = scheduler.scheduleAtFixedRate(
            this::dispatchOne, 0, periodNanos, TimeUnit.NANOSECONDS);
    }

    private void dispatchOne() {
        offered.increment();
        if (!inFlight.tryAcquire()) {
            rejected.increment();
            return;
        }

        long started = System.nanoTime();
        try {
            int draw = ThreadLocalRandom.current().nextInt(100);
            Kind kind = draw < 60 ? Kind.READ_LIST
                : draw < 80 ? Kind.READ_DETAIL
                : draw < 95 ? Kind.CREATE_ORDER
                : Kind.UPDATE_STATUS;

            OrderKey key = weightedSeedKeys.get(
                ThreadLocalRandom.current().nextInt(
                    weightedSeedKeys.size()));

            // Completion callback chỉ O(1): không JDBC/HTTP/sleep.
            execute(kind, key).whenComplete((unused, error) -> {
                totalDurationNanos.add(
                    System.nanoTime() - started);
                if (error == null) {
                    acknowledged.increment();
                } else {
                    errors.increment();
                    // Phân loại timeout/partial-write riêng ở service.
                    // Không tự retry mutation ở đây.
                }
                inFlight.release();
            });
        } catch (RuntimeException failure) {
            errors.increment();
            totalDurationNanos.add(
                System.nanoTime() - started);
            inFlight.release();
        }
    }

    private CompletionStage<AsyncResultSet> execute(
            Kind kind, OrderKey seed) {
        switch (kind) {
            case READ_LIST: {
                BoundStatement stmt = readList.bind(
                        seed.tenantId(), seed.day())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setPageSize(20)
                    .setIdempotent(true);
                return session.executeAsync(stmt)
                    .thenCompose(first -> {
                        // Có thể fetch thêm 1 page ở ~40% requests
                        // KHI thực sự còn page tiếp theo.
                        boolean next = ThreadLocalRandom.current()
                            .nextInt(10) < 4;
                        if (next && first.hasMorePages()) {
                            return first.fetchNextPage();
                        }
                        return CompletableFuture.completedFuture(first);
                    });
            }
            case READ_DETAIL: {
                BoundStatement stmt = readDetail.bind(seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(true);
                return session.executeAsync(stmt);
            }
            case CREATE_ORDER: {
                // ID tạo đúng một lần cho logical operation này.
                // Bucket ngày phải theo business timezone đã công bố.
                Instant now = Instant.now()
                    .truncatedTo(ChronoUnit.MILLIS);
                LocalDate businessDay = now.atZone(
                    ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
                OrderKey fresh = new OrderKey(
                    UUID.randomUUID(), seed.tenantId(), businessDay, now);
                BoundStatement first = insertById.bind(
                        fresh.orderId(), fresh.tenantId(), fresh.day(),
                        fresh.createdAt(), "CREATED", 125_000L)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                BoundStatement second = insertByDay.bind(
                        fresh.tenantId(), fresh.day(), fresh.createdAt(),
                        fresh.orderId(), "CREATED", 125_000L)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);

                // Đây là hai writes độc lập, không phải transaction.
                return session.executeAsync(first)
                    .thenCompose(ignore -> session.executeAsync(second));
            }
            case UPDATE_STATUS: {
                BoundStatement first = statusById.bind(
                        "PAID", seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                BoundStatement second = statusByDay.bind(
                        "PAID", seed.tenantId(), seed.day(),
                        seed.createdAt(), seed.orderId())
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .setIdempotent(false);
                return session.executeAsync(first)
                    .thenCompose(ignore -> session.executeAsync(second));
            }
            default:
                throw new IllegalArgumentException("Unknown workload");
        }
    }

    // Snapshot chỉ để debug; hệ thống đo thật cần histogram per-kind.
    public String snapshot() {
        return "offered=" + offered.sum()
            + ", rejected=" + rejected.sum()
            + ", acknowledged=" + acknowledged.sum()
            + ", errors=" + errors.sum()
            + ", totalDurationNanos=" + totalDurationNanos.sum()
            + ", inFlight=" + (128 - inFlight.availablePermits());
    }

    @Override
    public void close() {
        ScheduledFuture<?> job = scheduled;
        if (job != null) {
            job.cancel(false);
        }
        scheduler.shutdown();
        // CqlSession do caller sở hữu và phải đóng ngoài runner.
        // Những CompletionStage in-flight có thể còn hoàn tất sau đây.
    }
}
```

### Cách dùng trong một bài test có kiểm soát

```java
// session: một CqlSession được cấu hình đúng local DC/auth/TLS.
// seedKeys: danh sách OrderKey thực sự tồn tại và đã được seed.
BusinessWorkloadGenerator generator =
    new BusinessWorkloadGenerator(session, seedKeys);
generator.start(200);  // Tốc độ giả định cho lab.

// Test controller điều phối thời lượng và guardrails,
// đọc metrics, rồi đóng generator khi kết thúc giai đoạn.
// Không gọi Thread.sleep() bên trong driver callback.
```

Mã trên là **trích đoạn orchestration**: `session` và `seedKeys` do test bootstrap tạo ra. Nó không tự đóng session, không tự dừng sau một khoảng thời gian, và không inject lỗi. Thiết kế thật cần một test controller phát giai đoạn, dừng theo guardrails, chờ in-flight/drain, ghi histogram và kiểm tra dữ liệu.

### Giới hạn quan trọng của skeleton

1. **Scheduling:** `scheduleAtFixedRate` không đảm bảo phát chính xác 200 request/s khi JVM bị pause hoặc scheduler chậm; task có thể chạy bù. Cần đo **intended send time, actual dispatch time và scheduling lag**, không chỉ chia `offered` cho wall-clock.
2. **Skew:** `weightedSeedKeys` cho phép lặp phần tử để tăng xác suất, nhưng phân bố thực tế phải lấy từ telemetry. Không mặc định một uniform sampler là “production-like”.
3. **Read-after-write:** `CREATE_ORDER` tạo ID mới và tính bucket theo múi giờ nghiệp vụ minh họa `Asia/Ho_Chi_Minh`, nhưng chưa thêm vào seed. Để mô hình hóa “tạo → xem chi tiết”, cần **stateful workflow** hoặc queue các ID đã tạo thành công/UNKNOWN cần xác minh. Phải thống nhất business timezone của môi trường thực tế, không mặc định timezone JVM.
4. **Partial writes:** Nếu `insertById` thành công, `insertByDay` lỗi, future lỗi **không rollback bảng đầu**. Cần track từng stage và reconcile theo `order_id`; ở đoạn mẫu chưa có ledger.
5. **Update realism:** `UPDATE_STATUS` chọn một seed key và đặt `PAID`, chưa mô phỏng state machine hay contention payment. Thêm preconditions, phân bố transition và concurrent writers theo workload thực.
6. **Latency:** `totalDurationNanos` chỉ cho tổng của mọi logical operations được nhận, không cung cấp p99 hay CQL latency per-kind. Thực tế nên dùng histogram/Micrometer với số mẫu, labels và deadline.
7. **Retries:** `setIdempotent(false)` giúp policy driver biết mutation không được tuyên bố idempotent; HTTP/job/gateway hoặc code ngoài vẫn có thể lặp logical operation.
8. **Backpressure:** `Semaphore` cho tối đa 128 operations in-flight, nhưng không phải một request queue; các lần không nhận được permit phải được đếm như **shed/rejected offered load**.
9. **Pacing:** Tạo 5.000 scheduled callbacks/s từ một JVM chưa chắc phù hợp; để tạo tải lớn phải phân tán generators, đồng bộ giai đoạn và tránh chính máy phát tải bão hòa.
10. **Tài nguyên:** Trong benchmark, không in mỗi row/UUID ra logs, không giữ hàng triệu futures trong memory, không dùng `join()` trong callback, và đo CPU/GC của generator để tránh bị client giới hạn.

### Không nhận “SUCCESS” chỉ vì stage không ném exception

Với `READ_DETAIL`, stage thành công nhưng kết quả không có hàng có thể là **404 hợp lệ hoặc lỗi seed distribution**. Với `READ_LIST`, một page có thể rỗng dù còn page tiếp. Với dual-write, stage thứ hai thành công không chứng minh các hệ thống khác như payment gateway đã hoàn tất. **Phân loại success theo hợp đồng nghiệp vụ, không chỉ theo transport ACK.**

## 15. Phép đo đầy đủ hơn cho generator: per-operation và per-query

Bộ phát tải phía trên cần được instrument theo hai dòng sự kiện:

```text
BUSINESS_OP_STARTED
  op=CREATE_ORDER
  logicalOperationId=...
  scheduledAt=...

CQL_ATTEMPT
  queryTemplate=insertOrdersById
  cl=LOCAL_QUORUM
  attempt=1
  latency=...

CQL_ATTEMPT
  queryTemplate=insertOrdersByTenantDay
  cl=LOCAL_QUORUM
  attempt=1
  latency=...

BUSINESS_OP_FINISHED
  status=CONFIRMED / UNKNOWN / PARTIAL / CONFLICT
  endToEndDuration=...
```

**Không log full UUID/customer IDs/PII hoặc secrets trên mọi request.** Event identifiers dùng để reconcile có thể lưu ở **kho test có hạn dùng và được bảo vệ**, còn metrics nên tổng hợp theo query template, CL, DC, tenant cohort (hot/warm/cold) và status.

### Đo chi phí của paged reads

Nếu `READ_LIST` trung bình fetch 1,4 pages/operation, phải đo thực tế:

- Số pages/READ_LIST.
- Page size được yêu cầu và số rows/page thực tế.
- Payload bytes/page, tombstone warnings, retry/failure per page.
- Thời gian chờ sau page đầu (UI think time) nếu API fetch trang sau theo user action.
- Trường hợp user chỉ mở danh sách một lần rồi không kéo tiếp.

Không dùng một request Java tự động fetch **toàn bộ ResultSet** rồi gọi kết quả là “một page”. Với Java Driver 4.x, `ResultSet` đồng bộ có thể tự tải trang sau khi lặp; `AsyncResultSet.currentPage()` tách rõ page hiện tại.

### Đo read/write mix theo cửa sổ thời gian

Một tỷ lệ 60/20/15/5 cho cả ngày có thể giấu burst:

```text
08:00–09:00: nhiều READ_LIST, READ_DETAIL
12:00–12:05: chiến dịch tạo đơn → CREATE_ORDER burst
20:00–20:30: worker xác nhận thanh toán → UPDATE_STATUS tăng
00:00–02:00: retention jobs, compaction, backup
```

Đây là lịch **minh họa**. Lấy burst ratio/duration từ telemetry thật và mô hình các phase khác nhau, không xáo đều mọi loại request khiến peak nghiệp vụ biến mất.

## 16. Cách đo tính đúng dữ liệu: throughput cao mà không mất đơn

Một bài test tạo đơn phải giữ **expected state** để đối chiếu. Chỉ đếm `INSERT` “completed” không đủ khi writes đi hai bảng hoặc có retry.

| Invariant | Cách kiểm chứng | Kết quả lỗi thường thấy |
| --- | --- | --- |
| Một logical `order_id` duy nhất | So event/operation ledger với bảng `orders_by_id` | Duplicate do tạo ID mới khi retry |
| Hai bảng phản ánh cùng đơn | Đọc cả hai theo key đã biết | Partial write, write B bị timeout |
| Status không đi lùi trái phép | So transition version/event log | Retry status cũ ghi đè trạng thái mới |
| READ_DETAIL đúng tenant/ID | Đối chiếu seeded key và tenant authorization | Bug CQL bind/mapping hoặc dữ liệu cũ |
| READ_LIST chỉ trong partition | So `tenant_id`, `order_day` và clustering order | Chọn key sai, merger/fan-out lỗi |
| Không có quá nhiều “miss” | Đo 404 theo phân bố đã thiết kế | Generator chọn random UUID không tồn tại |
| Expiration theo policy | So `expires_at` và TTL/retention | TTL replay làm trôi hạn |
| Recovery sau lỗi | Reconcile những `UNKNOWN`/`PARTIAL` | Test dừng khi còn dữ liệu sai |

### Công việc đối soát không nên chạy trên hot path của load generator

Nếu sau mỗi `INSERT`, generator chạy thêm ba `SELECT` kiểm chứng thì workload **khác ma trận ban đầu**. Có hai cách hợp lệ nhưng phải nói rõ:

1. **Validation workload là một phần sản phẩm:** tính các reads kiểm chứng vào tỷ lệ truy vấn.
2. **Test harness audit độc lập:** lấy mẫu hoặc chạy sau giai đoạn tải, ghi rõ các query đối soát để không lẫn với business throughput.

Với lỗi timeout, kết quả mutation có thể **UNKNOWN**; không tự đánh dấu “đơn thất bại” rồi tạo một ID khác. Giữ ID bất biến trong ledger, đọc lại theo CL thích hợp và phân loại CONFIRMED, PARTIAL, CONFLICT, UNKNOWN theo quy tắc đã thống nhất.

### Có nên dùng `COUNT(*)` để kiểm chứng mọi đơn?

Không chạy `SELECT COUNT(*)` toàn bảng liên tục dưới tải để “đếm writes đã thành công”. Đếm có thể scan nhiều partitions/SSTables và bóp méo workload. Hãy dùng **manifest/ledger IDs và read theo key** để đối soát theo mẫu hoặc sau test; nếu cần count chính xác cho dữ liệu đã chốt, thiết kế export/snapshot job riêng.

## 17. Fault testing phải bổ sung, không thay thế load model

Sau khi đã có baseline trên cluster ổn định, có thể đưa **một lỗi có kiểm soát** vào một giai đoạn tải đại diện để kiểm tra điều mà người dùng thật quan tâm: request có đạt SLO không, dữ liệu có đúng không, hệ thống có phục hồi mà không tạo retry storm không.

Một ma trận kịch bản:

| Lỗi được thử trong lab/staging | Workload nên giữ | Kỳ vọng/điều phải quan sát |
| --- | --- | --- |
| Một replica/node Down trong DC RF3 | Mix READ_LIST, READ_DETAIL, writes | `LOCAL_QUORUM` còn có thể đạt với hai replica local khỏe; p99 có thể tăng |
| Coordinator bị dừng sau khi nhận request | CREATE_ORDER + READ_DETAIL | Write outcome có thể UNKNOWN, ứng dụng phải reconcile |
| Tăng network latency tới một node | Reads và writes cùng CL | Tail latency, coordinator routing, timeouts/retries |
| Gián đoạn một liên kết WAN | Multi-DC read/write theo contract | `LOCAL_QUORUM` local và convergence giữa DC khác nhau |
| Compaction backlog / disk I/O pressure | Paged reads và writes | SSTables/read, pending tasks, write latency, disk headroom |
| Một JVM load generator bị quá tải | Giữ server không fault | Phân biệt artifact của client với Cassandra failure |
| Cassandra node restart có kiểm soát | Workload peak đã biết | Connection recovery, in-flight failures, latency hậu restart |
| Một hot tenant/partition bị đột biến tải | Hot-key profile tách riêng | Replica imbalance, p99 theo cohort, throttling |

**Đây là kế hoạch kịch bản, không phải hướng dẫn phá hạ tầng production.** Lỗi node, mạng hoặc disk chỉ được inject trên môi trường được phê duyệt, có quyền kiểm soát và rollback/fail-safe cụ thể. Không gây `disk full`, network partition, kill nhiều replica hoặc ép compaction trên cluster phục vụ người dùng thật.

### Tách các chế độ lỗi

- **Graceful drain/shutdown** khác **process kill**; write path, ACK và recovery có thể khác.
- **Node Down** khác **network partition**: một node có thể còn xử lý mutations nhưng không phản hồi client.
- **Replica failure** khác **coordinator failure**: client routing và knowledge of outcome khác.
- **Một DC mất WAN** khác **mất toàn bộ local quorum**.
- **Server chậm** khác **driver callback bị chặn** trong ứng dụng Java.

Nếu chỉ thử một lệnh “stop node” và gọi đó là “đã test mọi lỗi phân tán”, kết luận là quá rộng.

## 18. Runbook thử một replica Down dưới tải nghiệp vụ

**Giả định chỉ dành cho cluster lab/staging được phép thử lỗi:**

- Một datacenter `dc1` với RF3 cho các bảng đang đo.
- Có ba replica thực sự đặt đúng rack/failure-domain theo thiết kế lab.
- Java Driver kết nối đúng local DC và dùng `LOCAL_QUORUM`.
- Đã có data seed đại diện, generator phát ổn định business workload mix.
- Đã có quyền dừng/khởi động node và **phương án rollback** được phê duyệt.

### Trước khi inject lỗi

1. Chụp topology/baseline từ các node: `nodetool status`, bảng, RF/CL/DC/rack.
2. Kiểm tra authentication/TLS, application health, retry policy và idempotency.
3. Xác minh backup/snapshot/restore policy phù hợp; **không** giả định fault test không thể mất dữ liệu.
4. Đặt tối đa offered RPS, duration, in-flight và disk headroom.
5. Chuẩn bị guardrails/alerts: p99, timeout, unavailable, pending tasks, dropped messages và correctness.
6. Giữ **một nhóm replica còn đủ quorum khỏe** trước khi thử; nếu baseline đã lỗi, **không inject thêm**.
7. Đồng bộ đồng hồ/phase markers của client, generator, Cassandra nodes và metrics.

Lệnh quan sát **chỉ đọc** trên node lab:

```bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool compactionstats
nodetool tablestats load_lab.orders_by_id
nodetool tablestats load_lab.orders_by_tenant_day
nodetool tablehistograms load_lab orders_by_tenant_day
```

`nodetool` báo tình trạng/node-local metrics; không đo trực tiếp HTTP latency hay trạng thái task queue của Java generator. Kết hợp với driver/app metrics và thông số OS/disk.

### Trong giai đoạn lỗi

1. Ghi mốc `T_fault_start` và **chỉ inject một loại fault đã phê duyệt**, một node/đường mạng cụ thể.
2. Giữ workload mix và offered rate như baseline nếu guardrails cho phép, tránh thay đồng thời hai biến.
3. Đo p95/p99 theo `READ_LIST`/`READ_DETAIL`/`CREATE_ORDER`/`UPDATE_STATUS`, không chỉ trung bình tất cả.
4. Đo thêm số driver attempts/retries, read/write timeouts và application rejections.
5. Theo dõi đúng các partition nóng thuộc replica đang bị lỗi, không chỉ traffic tổng của cluster.
6. Ghi mọi `UNKNOWN`/`PARTIAL` writes để đối soát; không tự retry counter/list/LWT mù.
7. **Dừng inject/load** nếu một guardrail vượt ngưỡng hoặc xuất hiện lỗi ngoài phạm vi.

Với RF3/`LOCAL_QUORUM`, nếu một replica Down nhưng **hai replica địa phương còn lại khỏe và được truy cập**, nhiều request thường vẫn có thể đạt quorum. Điều này **không phải cam kết** throughput/latency không đổi hay mọi partition đều khỏe; client routing, coordinator và tải trên hai replica còn lại vẫn quyết định outcome.

### Sau khi phục hồi node

1. Khôi phục node/network theo runbook vận hành, không thực hiện thêm thao tác phá hoại.
2. Kiểm tra lại trạng thái node và khả năng truy cập của các request CQL.
3. Theo dõi streaming/hints/repair debt, compaction và backlog theo phiên bản/topology.
4. Giữ quan sát đến khi độ trễ, error rate, disk và pending tasks **trở về ngưỡng chấp nhận**, không chỉ khi `nodetool status` báo `UN`.
5. Đối soát logical orders trên hai bảng, các operation UNKNOWN/PARTIAL và trạng thái sai.
6. So baseline trước lỗi, trong lỗi và sau recovery trên **cùng phân bố workload**.
7. Lưu report, artifacts đã scrub PII và quyết định go/no-go cho lần thử tiếp theo.

Không dùng `nodetool repair` hay `major compaction` như một “nút reset” thiếu kế hoạch. Repair/compaction có chi phí tài nguyên và yêu cầu tương thích với trạng thái cluster; không tự phân biệt business writes đúng/sai.

## 19. Tách lỗi ứng dụng Java khỏi lỗi Cassandra

Một test đo “Cassandra chậm” có thể thực chất bị giới hạn ở client:

| Triệu chứng | Giả thuyết ưu tiên | Kiểm chứng |
| --- | --- | --- |
| Generator CPU 100%, Cassandra CPU thấp | Client phát tải không đủ/tốn serialize | Đo scheduling lag, bytes, client GC |
| Driver I/O threads có `join/get/sleep` | Blocking callback | Thread dump, refactor `thenCompose`/executor giới hạn |
| Local semaphore rejection tăng | Client đạt in-flight limit | So offered/admitted, không chỉ completed |
| HTTP p99 xấu, CQL p99 vẫn ổn | Service auth/JSON/other dependency | Trace per stage, CPU/GC của Spring Boot |
| CQL READ_LIST p99 tăng, READ_DETAIL ổn | Wide/hot partition, SSTables/tombstones | Phân nhóm hot/cold, tablehistograms/tracing có chọn lọc |
| CQL CREATE p99 tăng khi compaction backlog | Disk/write amplification | `compactionstats`, disk I/O, memtable/flush |
| `Unavailable` tăng khi node Down | RF/CL/quorum không đủ hoặc routing | Kiểm tra đúng replica, DC, CL |
| Timeout tăng nhưng write vẫn xuất hiện sau đó | ACK không đủ/trễ, outcome UNKNOWN | Reconcile, không auto coi timeout=rollback |
| Một DC đọc cũ hơn DC kia | WAN/convergence, CL và routing | Đo per-DC, giữ contract nhất quán |

### Không “sửa benchmark” bằng cách vô hiệu hóa consistency

Nếu `LOCAL_QUORUM` đã là contract của API, giảm xuống `ONE` để throughput tăng có thể tạo một **kết quả so sánh thú vị**, nhưng **không phải phép tối ưu tương đương về tính đúng**. Trong report phải đặt tên là một **scenario CL khác** và ghi rõ thay đổi semantics; không trộn hai kết quả vào một đường baseline.

### Không để load generator tạo thêm lỗi vì retry storm

Một số driver retries có thể hợp lệ cho `SELECT` idempotent, nhưng:

- Số requests thực tế tới Cassandra có thể lớn hơn offered logical operations.
- Attempts được gửi sau timeout có thể đẩy cluster đang quá tải tệ hơn.
- Speculative executions cũng dùng tài nguyên, chỉ phù hợp statements được chứng minh an toàn.
- Counter increments, list appends, TTL replay và LWT timeout cần chính sách riêng.

Một throughput chart không kèm retry count **có thể che chi phí thật** của việc phục vụ người dùng.

## 20. Mẫu báo cáo benchmark có thể so sánh và tái lập

Một report chuẩn nên bắt đầu bằng **điều kiện thử**:

```yaml
# Chỉ là mẫu metadata báo cáo, KHÔNG phải cấu hình công cụ.
scenario_id: business-mix-peak-rf3-lq
environment: isolated-staging
workload_version: orders-v3
data_model_version: orders-two-tables-v2
generator_instances: 2
offered_logical_ops_per_second: 1000
business_mix:
  READ_LIST: 60
  READ_DETAIL: 20
  CREATE_ORDER: 15
  UPDATE_STATUS: 5
read_list_mean_pages_target: 1.4
partition_distribution: sampled-hot-warm-cold
replication: "NetworkTopologyStrategy dc1=3"
consistency: LOCAL_QUORUM
local_dc: dc1
retry_policy: "record actual configured policy/version"
fault: "none; baseline"
measurement_window: "steady-state phase, exact timestamps"
```

Nếu có lỗi, thêm `fault_type`, `fault_target`, `T_fault_start`, `T_fault_end`, thời gian recovery và guardrail đã chạm. Không copy host IP/secret/tenant IDs nhạy cảm vào báo cáo phát hành rộng.

### Mẫu bảng kết quả — số giả định, không phải phép đo

| Metric | Baseline ví dụ | Khi một replica Down ví dụ | Sau recovery ví dụ |
| --- | ---: | ---: | ---: |
| Offered logical ops/s | 1.000 | 1.000 | 1.000 |
| Admitted logical ops/s | 995 | 940 | 992 |
| Completed successful ops/s | 991 | 900 | 987 |
| Rejected ops/s | 5 | 60 | 8 |
| Errors/unknown ops/s | 4 | 40 | 5 |
| READ_LIST p99 (ms) | 85 | 180 | 95 |
| CREATE_ORDER p99 (ms) | 120 | 300 | 135 |
| Driver attempts/logical op | 1,02 | 1,17 | 1,03 |
| Correctness violations | 0 đã kiểm chứng | Cần đối soát UNKNOWN | 0 sau reconciliation |

**Tất cả số trong bảng là dữ liệu minh họa**. Dòng “correctness violations = 0” chỉ hợp lệ sau khi có phương pháp kiểm chứng đủ coverage; nếu còn UNKNOWN chưa đối soát, phải ghi **“chưa xác định”**, không được tự điền 0.

### Một kết luận report chấp nhận được

> “Ở workload mix X, seed dataset Y, RF3/LOCAL_QUORUM trong DC1, khi fault Z xảy ra, READ_LIST p99 vượt SLO trong N phút; throughput đạt được giảm, errors và retries tăng. Sau khôi phục, backlog compaction và p99 hồi về ngưỡng sau M phút. Những write outcomes chưa chắc chắn đã được đối soát theo operation ID với coverage K.”

Các biến X/Y/Z/N/M/K phải được thay bằng **số liệu có nguồn đo**; không suy từ vài mẫu để kết luận mọi node/DC/đường truy vấn khác đều đáp ứng.

## 21. Những sai lầm phổ biến khi thiết kế tải đọc/ghi

### 21.1. Đếm HTTP requests nhưng quên CQL fan-out

Một `POST /orders` ghi hai bảng, một `GET /orders` có thể đọc hai pages. Một API operation không tương đương một CQL execution.

### 21.2. Chỉ dùng Uniform random keys

Production có tenant nóng; uniform random làm tải trải đều và benchmark đẹp hơn thực tế. Phải giữ hot/warm/cold và kích thước partition.

### 21.3. Chỉ dùng một hot key

Khi đó bài test có thể biến thành thí nghiệm contention trên một vài replica, không phản ánh toàn cluster. Hotness phải có tỷ lệ được định nghĩa và cold tail.

### 21.4. Mọi `READ_DETAIL` đều miss

Generator tạo UUID mới thay vì chọn order đã seed; query rỗng nhanh bất thường. Đặt hit/miss rate chủ động.

### 21.5. Mọi row đều nhỏ, mới và không có tombstone

Đo dataset quá sạch làm cache/SSTable behavior khác hẳn production giữ TTL, delete và compaction. Seed phải có data age và write/update lifecycle.

### 21.6. Closed-loop làm giảm offered load khi server chậm

Server bị stall, user threads chờ, request rate tự giảm; p99 có thể không phản ánh nhu cầu không được phục vụ. Đo offered/scheduled và queue wait, không chỉ completed.

### 21.7. Vô hạn concurrency để tìm “QPS tối đa”

Khi quá nhiều requests được queue, cả client và Cassandra có thể OOM hoặc retry storm. Dùng rate ramp và bounded in-flight, có guardrail.

### 21.8. Xem timeout là write failed rồi retry mù

Một mutation có thể đã áp dụng dù client không nhận ACK. Với dual-write, timeout giữa hai bảng tạo `PARTIAL`; phải reconcile theo logical ID.

### 21.9. Chỉ báo average latency

p99 của READ_LIST có thể cao gấp nhiều lần READ_DETAIL; average chung không đại diện tail người dùng. Phân theo template/cohort.

### 21.10. So hai benchmark khác RF/CL/dataset như tương đương

RF1, `ONE`, 10 GB dữ liệu sạch không cùng bài toán với RF3, `LOCAL_QUORUM`, hàng TB dữ liệu có TTL/tombstones. Phải chuẩn hóa điều kiện hoặc công bố khác biệt.

### 21.11. Chạy fault test khi baseline đã lỗi

Nếu cluster đang pending compaction, disk thiếu headroom hoặc một replica đã Down, inject thêm lỗi có thể gây mất quorum ngoài dự kiến. Dừng và sửa baseline.

### 21.12. Một node `UN` được coi là đã phục hồi hoàn toàn

Node Up có thể còn repair debt, pending compaction, dữ liệu chưa hội tụ hoặc pool Java chưa ổn định. Đo thêm recovery period và correctness.

## 22. Bài tập tình huống và đáp án định hướng

### Tình huống A — Tính từ API rate sang CQL rate

Hệ thống có 1.000 business operations/s, 60% READ_LIST (1,4 pages/op), 20% READ_DETAIL (1 CQL), 15% CREATE (2 writes), 5% UPDATE (2 writes). Không tính retry, ước tính CQL rate?

**Đáp án:** \(600×1,4+200+150×2+50×2=1440\) CQL/s, trong đó khoảng 1040 read CQL/s và 400 write CQL/s. Đây là ước tính **trung bình**, không áp dụng cho mọi cửa sổ peak.

### Tình huống B — 50.000 QPS từ một bảng ID

Team chứng minh `orders_by_id` đạt 50.000 QPS khi mọi read hit cache. Frontend danh sách theo tenant/day có đủ an toàn không?

**Đáp án:** Không thể kết luận. READ_LIST truy cập partition/clustering khác, kích thước khác, cần paging và có thể chạm nhiều SSTables/tombstones. Phải benchmark query shape đó.

### Tình huống C — RF3 một replica Down

Trong DC RF3, một node Down, `LOCAL_QUORUM` còn yêu cầu mấy replica local? Có thể bảo đảm p99 không tăng?

**Đáp án:** Cần hai local replica. Nhiều partitions vẫn có thể phục vụ nếu đủ hai replica khỏe; **không** bảo đảm p99 giữ nguyên, vì node còn lại chịu tải/route khác.

### Tình huống D — Read detail 0,5 ms nhưng phần lớn trả rỗng

Generator tạo `UUID.randomUUID()` cho mọi read. Read latency cực đẹp.

**Đáp án:** Tải không đại diện. Hãy seed keys và kiểm soát hit/miss distribution; đo cả correctness.

### Tình huống E — Tạo đơn thành công một bảng

`INSERT orders_by_id` trả OK, `INSERT orders_by_tenant_day` timeout. Java service ghi “FAILED” và tạo order ID khác khi retry HTTP.

**Đáp án:** Outcome bảng thứ hai chưa chắc chắn; bảng đầu đã thành công. Giữ `order_id`/operation ID ổn định, đánh dấu `PARTIAL/UNKNOWN`, đối soát và hoàn tất projection thay vì nhân đôi đơn.

### Tình huống F — Peak trong 5 phút

Tỷ lệ 60/20/15/5 đo cả ngày; trong đợt flash sale, CREATE_ORDER tăng mạnh trong 5 phút và queue thanh toán chạy sau đó.

**Đáp án:** Thiết kế **phases** và burst profile riêng dựa trên telemetry; không rải đều workload 24 giờ rồi nói đã test peak.

### Tình huống G — Offered 1000, completed 650

Generator từ chối 300 vì semaphore, 50 requests lỗi, 650 success. Báo “650 ops/s với error rate 0%” đúng không?

**Đáp án:** Không. Cần phân biệt offered/admitted/acknowledged/errors/rejected và báo denominator. Đang có 35% offered operations không hoàn tất thành công trong ví dụ.

### Tình huống H — Benchmark tốt sau khi hạ CL

Sau khi đổi từ `LOCAL_QUORUM` sang `ONE`, latency giảm 40%. Có được dùng biểu đồ mới để chứng minh “đã tối ưu cùng workload”?

**Đáp án:** Đây là **scenario consistency khác**. Có thể so sánh để phân tích trade-off, nhưng không gọi tương đương về ngữ nghĩa. Giữ rõ RF/CL/DC trong báo cáo.

### Tình huống I — Generator CPU đạt 100%

Driver queue nhỏ, node Cassandra CPU chỉ 25%, offered 2000 nhưng measured ~900 ops/s.

**Đáp án:** Đo scheduling lag, GC, CPU và queue của generator. Có thể bottleneck phía client; phân tán generator hoặc tối ưu serialization trước khi quy lỗi cho Cassandra.

### Tình huống J — Tăng TTL để giảm disk pressure

Team phát hiện tombstones làm READ_LIST chậm; muốn tăng TTL từ 1 ngày lên 90 ngày mà không kiểm tra retention/policy, rồi chạy lại benchmark.

**Đáp án:** Không nên đổi semantics dữ liệu để làm benchmark đẹp. Xác định TTL/compaction/partition design đúng nghiệp vụ, đo với data age và cleanup thực tế, rồi mới lựa chọn.

### Tình huống K — Node trở lại `UN` sau fault

Sau restart, `nodetool status` báo `UN`, team dừng đo và tuyên bố cluster recovered.

**Đáp án:** Cần kiểm tra thêm latency/error trở lại baseline, pending repair/compaction, driver connection recovery, data convergence và những operations còn UNKNOWN.

### Tình huống L — p99 của các nhóm bị lấy trung bình

READ_DETAIL có p99=20 ms; READ_LIST có p99=200 ms. Team lấy trung bình ra 110 ms rồi gọi là p99 ứng dụng.

**Đáp án:** Không hợp lệ về thống kê. Percentile của hợp tập không phải trung bình percentile các nhóm. Cần histogram/mẫu phù hợp và báo riêng từng loại query.

## 23. Checklist trước khi kết luận bài đo tải đã đại diện nghiệp vụ

**Dữ liệu và truy vấn**

- [ ] Có danh sách business journeys và query templates thật; không chỉ một `SELECT`/`INSERT` tổng quát.
- [ ] Đo được số CQL per business operation, bao gồm paged reads và dual writes.
- [ ] Query khớp partition/clustering key; không bật `ALLOW FILTERING` để che query sai.
- [ ] Có seed data đủ partitions, rows/partition, payload bytes, hot/cold và tuổi dữ liệu.
- [ ] Có tỷ lệ reads hit/miss hợp lệ, và state machine tạo/đọc/cập nhật/xóa phản ánh nghiệp vụ.
- [ ] Có TTL/delete/tombstone/compaction patterns khi hệ thống thật sử dụng chúng.
- [ ] Có operation ID bất biến và cách reconcile writes vào nhiều bảng.

**Thiết kế phát tải**

- [ ] Công bố offered, admitted, acknowledged, rejected, errors và actual driver attempts.
- [ ] Phân biệt open-loop, closed-loop, think time, scheduling lag và coordinated omission.
- [ ] Có concurrency/rate/backpressure giới hạn; không lưu futures/rows vô hạn trong memory.
- [ ] Dùng lại `CqlSession`, prepared statements và xử lý async không blocking callback.
- [ ] Bảo toàn tỷ lệ truy vấn ở cả giờ thường, peak, burst và soak.
- [ ] Máy phát tải không phải bottleneck; có CPU/GC/queue metrics của generator.
- [ ] Kiểm tra request deadline, retry budget, speculative execution và idempotency.

**Cassandra và hệ phân tán**

- [ ] Công bố Cassandra version/distribution, topology DC/rack, RF, CL, driver/JDK/version.
- [ ] Đã xác minh local DC và client routing, không hạ CL để che timeout.
- [ ] Theo dõi read/write latency, p95/p99, dropped messages, pending tasks, SSTables/read, disk/GC.
- [ ] Có headroom disk/memory/CPU cho compaction và node recovery.
- [ ] Không suy từ RF1 test rằng RF3/multi-DC failure sẽ hành xử giống nhau.
- [ ] Có baseline ổn định trước fault injection và giới hạn blast radius rõ ràng.
- [ ] Không inject lỗi nhiều replica/network/disk trên production hoặc cluster không được phê duyệt.

**SLO, tính đúng và phục hồi**

- [ ] p99 được đo theo query template/cohort và công bố số mẫu/cửa sổ.
- [ ] Timeouts/rejections/UNKNOWN không bị loại khỏi báo cáo SLO.
- [ ] Có kiểm tra missing orders, duplicate logical IDs và projection drift.
- [ ] Có mốc fault/recovery và guardrails dừng tải rõ ràng.
- [ ] Recovery được xác nhận bằng throughput, latency, backlog và correctness, không chỉ `UN`.
- [ ] Báo cáo phân biệt giả định, kết quả thực đo và hạn chế của môi trường.
- [ ] Có thể tái lập kịch bản từ workload version, seed profile, RF/CL, thời gian và config.

**Ghi nhớ:** Một bài đo tải Cassandra có giá trị khi nó phản ánh **những câu CQL mà nghiệp vụ thực sự phát ra**, với phân bố partition, tỷ lệ đọc/ghi, page fetch, dual writes, RF/CL và dữ liệu đã trải qua update/TTL/compaction. Đo **offered load và lỗi bị từ chối** cùng throughput, p99 và correctness; sau đó mới bổ sung fault testing có kiểm soát. Mục tiêu không phải tìm một con số QPS đẹp, mà là biết **hệ thống còn giữ SLO và dữ liệu đúng đến đâu khi tải và lỗi phân tán xảy ra**.


