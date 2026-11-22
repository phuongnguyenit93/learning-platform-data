# Mô phỏng khóa nóng, phân vùng lớn hoặc nhiều tombstone trong Apache Cassandra

## 1. Mục tiêu: tạo tải có kiểm soát để tìm đúng nguyên nhân

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Dữ liệu được định vị qua **partition key**, nhân bản theo **replication factor (RF)**, và đọc/ghi với **consistency level (CL)**. Tốc độ xử lý truy vấn phụ thuộc vào cách thiết kế bảng theo truy vấn, kích thước partition, trạng thái replica, SSTable, compaction, repair, mạng và cách ứng dụng Java gửi request.

Trong chương **Đo tải và lỗi phân tán** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, ba dạng tải sau rất dễ bị nhầm:

- **Khóa nóng (hot partition key):** một hoặc một nhóm rất nhỏ partition key nhận phần lớn request. Partition có thể rất **nhỏ** nhưng QPS quá cao.
- **Phân vùng lớn (wide/large partition):** một partition chứa quá nhiều clustering rows/cells hoặc dung lượng dữ liệu lớn. Partition có thể chỉ được đọc ít lần nhưng mỗi lần tốn I/O, bộ nhớ hoặc thời gian.
- **Nhiều tombstone:** đường đọc phải xử lý lượng lớn dấu xóa/giá trị hết TTL trước khi tìm đủ dữ liệu còn sống. Partition không nhất thiết lớn về số row còn tồn tại.

Ba tình huống có thể xuất hiện **đồng thời**, nhưng cần mô phỏng riêng để biết nguyên nhân. Ví dụ một partition vừa nhận 80% traffic, vừa lưu vài triệu events, vừa bị xóa liên tục sẽ chậm vì nhiều yếu tố; nếu tăng timeout hoặc page size trước khi biết yếu tố nào chi phối, rất khó đánh giá tác dụng.

### Kết quả mong đợi

Sau bài, bạn có thể:

1. Tạo keyspace và ba bảng thử nghiệm để cô lập các kiểu tải.
2. Phân bố request đồng đều rồi tạo skew về một partition key và đo latency/QPS theo key/replica.
3. Tăng có kiểm soát số hàng và bytes của một partition, quan sát kích thước và read behavior.
4. Tạo tombstone từ `DELETE`/TTL, kiểm read amplification và cảnh báo.
5. Dùng Java Driver 4.x gửi truy vấn bất đồng bộ với **giới hạn in-flight** thay vì phát tải không kiểm soát.
6. Đọc các chỉ số p50/p95/p99, throughput thành công, timeout, compaction, GC và tombstone scans.
7. Kiểm nghiệm hướng sửa: **bucketing theo thời gian**, **sharding có kiểm soát**, retention và thay đổi mẫu truy vấn.
8. Viết báo cáo before/after có thể tái hiện và phân biệt giới hạn của bài test một node với cluster RF=3.

## 2. Quy tắc an toàn trước khi mô phỏng sự cố

**Chỉ thực hiện trên Cassandra cluster dành riêng cho lab/staging thử nghiệm, với dữ liệu giả.** Bài học đưa ra CQL và mã tải có giới hạn nhằm phục vụ kiểm thử; không chạy trực tiếp lên cluster production hoặc keyspace dữ liệu thật.

Trước khi chạy:

- Chốt **endpoint, tên cluster, keyspace và quyền truy cập**. Không dùng role superuser production.
- Ghi rõ số node, tên datacenter, Cassandra Server/Java Driver version, RF/CL, disk quota và các tiến trình nền.
- Đặt **giới hạn tối đa**: số partition, hàng/partition, bytes/payload, request count, duration, in-flight, tốc độ submit và tỷ lệ lỗi cho phép.
- Có điều kiện dừng: disk gần đầy, dropped messages tăng nhanh, p99/timeout quá ngưỡng, GC kéo dài hoặc health của node suy giảm.
- Không tắt compaction/repair, không hạ `gc_grace_seconds` hoặc nâng ngưỡng tombstone để “cho bài test chạy qua”.
- Không tạo dữ liệu tải nặng cùng lúc với backup, repair, bootstrap hoặc bài test khác trên cluster dùng chung.
- Nếu cần mô phỏng node DOWN, network loss hay disk chậm, sử dụng **testbed nhiều node riêng** và kế hoạch khôi phục rõ.

### Mức tải thăm dò đề xuất cho lab

Các mức sau chỉ là **ví dụ để bắt đầu đo**, không phải công thức cấu hình Cassandra:

| Trục thử | Mức thấp | Mức vừa | Mức cao có gate |
| --- | ---: | ---: | ---: |
| Số request thử | 200 | 1.000 | 5.000 |
| Số request in-flight | 4 | 16 | 32 |
| Tỷ lệ request vào một hot key | 1–5% | 40% | 80% |
| Số hàng/partition | 100 | 2.000 | 10.000 |
| Kích thước `payload` | 128 B | 512 B | 1 KiB |
| Tỷ lệ row bị xóa trong partition | 0% | 50% | 90% |

Không tự động áp mức “cao” nếu container/CI chỉ có ít RAM hoặc disk. Khi thay biến số, giữ những biến còn lại **không đổi**; ví dụ muốn so 5% với 80% hot key, không đồng thời đổi RF, CQL, heap hoặc kích thước row.

## 3. Phân biệt hot key, wide partition và tombstone

| Đặc tính | Khóa nóng | Phân vùng lớn | Nhiều tombstone |
| --- | --- | --- | --- |
| Vấn đề cốt lõi | **QPS tập trung** vào một partition/nhóm replica | **Số hàng/cells/bytes lớn** trong một partition | **Dấu xóa/hết TTL** nằm trên đường đọc |
| Có cần nhiều row sống? | Không | Thường có nhiều cells/bytes | Không; row sống có thể ít |
| Có thể xảy ra với traffic thấp? | Ít mang ý nghĩa “nóng” nếu QPS thấp | Có | Có |
| Dấu hiệu điển hình | Replica của hot token bận, p99 tăng ở một key | P99 tăng theo kích thước partition/fetch, read bytes cao | Read scanning nhiều tombstone, cảnh báo tombstone, LIMIT nhỏ vẫn chậm |
| Đổi page size có giải quyết gốc? | Không | Chỉ điều tiết fetch; không xóa partition lớn | Không |
| Hướng sửa | Phân phối tải theo partition/shard, cache/bulkhead đúng | Bucket dữ liệu, giới hạn retention, partition theo query | Giảm xóa/TTL bất hợp lý, bucket/TWCS khi phù hợp, repair/compaction đúng quy trình |
| Cần theo dõi | Per-key traffic, token replicas, queue, p99 | Partition bytes/rows, SSTables, fetch latency | Tombstone scanned, SSTables, compaction, GC |

### 3.1. Một row nhỏ vẫn có thể là “khóa nóng”

Nếu `account_id=A` được đọc 10.000 lần/giây, các replica sở hữu partition A phải phục vụ phần lớn yêu cầu đó. Cassandra không chuyển những hàng cùng partition key sang nhiều token chỉ vì partition đang nóng. Token-aware driver có thể chọn replica phù hợp, nhưng **tập replica của một partition vẫn bị giới hạn bởi RF/topology**.

### 3.2. Partition lớn không đồng nghĩa một query luôn đọc hết

Partition chứa 100.000 clustering rows, nhưng query luôn xác định khoảng clustering key hẹp có thể hợp lý hơn query cần quét cả partition. Dù vậy, partition lớn vẫn tạo rủi ro cho compaction, streaming, repair, cache và những truy vấn không giới hạn; cần đo workload thực.

### 3.3. Tombstone không phải “row đã xóa nhưng vẫn tồn tại như row sống”

Cassandra dùng **tombstone** để biểu diễn xóa/TTL hết hạn trong hệ thống phân tán và ngăn dữ liệu cũ bị đưa trở lại khi replica hội tụ. Tombstone có vòng đời phụ thuộc compaction, overlap giữa SSTable, grace period, repair và phiên bản. Nó **không được xóa khỏi mọi replica ngay sau một câu DELETE**.

## 4. Chuẩn bị cluster và schema cô lập

Các lệnh ở phần này dành riêng cho keyspace `load_it` trên cluster thử nghiệm có datacenter `datacenter1`.

### 4.1. Keyspace cho lab một node

```sql
CREATE KEYSPACE IF NOT EXISTS load_it
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 1
}
AND durable_writes = true;
```

Nếu testbed có RF=3 tại DC `dc1`, tạo keyspace phù hợp cluster đó thay vì sao chép `datacenter1:1`. Để xác minh DC trên node kết nối:

```sql
SELECT data_center, release_version
FROM system.local;
```

**Một node RF=1 không kiểm chứng được quorum/failover RF=3**, dù bạn đặt CL `LOCAL_QUORUM`: quorum của RF=1 chỉ cần một replica. Muốn đo tác động khi một replica chậm/đứt kết nối, cần cluster nhiều node và test riêng.

### 4.2. Bảng không bucket: dùng để mô phỏng hot và wide partition

```sql
CREATE TABLE IF NOT EXISTS load_it.events_unbucketed (
    device_id uuid,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_ts, event_id)
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

Ở bảng này:

- `device_id` là **partition key duy nhất**.
- `event_ts` và `event_id` là clustering columns.
- Tất cả events cùng `device_id` sẽ thuộc **một partition logic**, dù số row tăng.
- Có thể đọc gần đây nhất theo `device_id`; nếu lưu lịch sử mãi mãi, partition có thể trở nên quá lớn.
- `event_id` tránh ghi đè hai events cùng timestamp.

Truy vấn đọc nhỏ:

```sql
SELECT event_ts, event_id, payload
FROM load_it.events_unbucketed
WHERE device_id = ?
LIMIT 10;
```

**Không đánh đồng** `LIMIT 10` với chi phí chỉ đọc 10 physical cells. Nếu 10 row sống nằm sau hàng nghìn tombstones, Cassandra có thể phải duyệt nhiều dấu xóa để trả 10 row.

### 4.3. Bảng có bucket và shard để thử hướng sửa

```sql
CREATE TABLE IF NOT EXISTS load_it.events_bucketed (
    device_id uuid,
    event_day date,
    shard int,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (device_id, event_day, shard),
        event_ts,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

Đây là **một mô hình thí nghiệm**:

- `event_day` chia lịch sử theo ngày UTC (hoặc quy ước được công bố).
- `shard` phân phối traffic của một device trong cùng ngày ra nhiều partition.
- `event_ts/event_id` giữ thứ tự trong **mỗi shard**, không tự tạo thứ tự tổng cho tất cả shard.
- Query “20 events mới nhất của device” phải biết bucket ngày cần đọc, truy vấn các shard cần thiết và **merge kết quả ở ứng dụng**, có giới hạn fan-out.

Không mặc định chọn 8 shards cho mọi workload. Số shard phải dựa trên QPS/bytes thực, RF, tải replica, số query đọc và chi phí merge.

### 4.4. Bảng riêng cho tombstone test

```sql
CREATE TABLE IF NOT EXISTS load_it.events_delete_heavy (
    device_id uuid,
    event_ts timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_ts, event_id)
) WITH CLUSTERING ORDER BY (
    event_ts DESC,
    event_id ASC
);
```

Giữ riêng bảng này để các lệnh `DELETE` không làm bẩn kết quả hot-key và wide-partition tests. Không dùng bảng production và không thay đổi `gc_grace_seconds` chỉ để tombstone biến mất nhanh hơn.

### 4.5. Gate xác nhận schema

Trong Java Driver 4.x, sau khi tạo DDL:

```java
if (!session.checkSchemaAgreement()) {
    throw new IllegalStateException("Schema agreement chưa đạt");
}

session.refreshSchema();

boolean ready = session.getMetadata()
    .getKeyspace("load_it")
    .flatMap(k -> k.getTable("events_unbucketed"))
    .isPresent();

if (!ready) {
    throw new IllegalStateException("Bảng test chưa có trong metadata");
}
```

`session` là `CqlSession` đã kết nối. Với cluster nhiều node, có thể cần **poll bounded** cho schema agreement thay vì fail ngay lần đầu; không dùng `Thread.sleep` vô hạn. Kiểm bảng tồn tại vẫn **chưa chứng minh primary key/options giống schema mong đợi**. Kiểm expected structure hoặc dùng migration/test query phù hợp.

## 5. Mô phỏng 1 — hot partition key

### 5.1. Giữ row count giống nhau, chỉ thay phân phối request

Để tách riêng “nóng” khỏi “rộng”:

1. Chuẩn bị **64 device IDs**, mỗi device có **cùng khoảng 20 events** với payload giống nhau.
2. Một device được đánh dấu `HOT_DEVICE`; nhưng nó **không** có nhiều row hơn các device khác.
3. Chạy baseline: chọn device gần như đồng đều.
4. Chạy hot scenario: **80% query** nhắm `HOT_DEVICE`, 20% phân tán vào các device còn lại.
5. Giữ CQL, CL, page size, timeout, số in-flight, số request và thời gian đo tương đương.
6. Thu latency tổng và **tách metric cho hot key/cold keys**.

Nếu hot scenario chậm hơn, bạn có bằng chứng liên quan đến **skew traffic**, chứ không phải partition lớn/tombstone vì fixture của các device có kích thước tương đương.

### 5.2. Phân phối xác suất cụ thể

Với 2.000 read requests và `hotRatio=0.80`:

\[
E[\text{reads vào hot key}]=2000\times0.80=1600
\]

Khoảng 400 reads còn lại phân tán trên các IDs khác. Số thực tế dao động do random sampling. Dùng **seed của RNG cố định** để có thể tái hiện sequence, nhưng không coi việc dùng seed cố định là đủ để tái hiện network/GC latency.

**Với RF=3:** cùng một hot partition được sở hữu bởi một nhóm replica theo token/topology. Việc nhiều coordinator cùng nhận request không khiến dữ liệu partition đó tự phân tán ra mọi node. Trong cluster 12 node, có thể thấy một vài replica của hot token bận nhiều hơn các node khác.

### 5.3. Phân biệt hot *partition* và hot *coordinator*

Một client không dùng token-aware routing hoặc có cấu hình contact point/load balancing không phù hợp có thể dồn quá nhiều request vào một coordinator, dù partition keys phân tán. Khi điều tra, phải hỏi:

- Traffic **có thật sự tập trung theo partition key** không?
- Coordinator bị quá tải có đúng là replica của các partition đó không?
- Driver token-aware policy, local DC, pool/connection và node state có đúng không?
- Một request có retry/speculative execution khiến cùng operation xuất hiện nhiều attempts không?

**Không chẩn đoán hot partition chỉ từ CPU cao trên một node**. Có thể là compaction, GC, coordinator routing lệch, disk, streaming hoặc query fan-out.

### 5.4. Kết quả mong đợi, không phải con số bắt buộc

Khi độ skew tăng, các replica sở hữu hot partition có thể gặp latency/pending tasks/CPU cao hơn, trong khi replica khác còn headroom. Tuy nhiên, nếu tổng QPS thấp hoặc cache hiệu quả, p99 có thể **chưa tăng**. Điều này là kết quả hợp lệ: cần tăng tải theo gate hoặc ghi rằng chưa tái hiện ở mức đã thử, **không cố ép cluster lỗi**.

## 6. Mô phỏng 2 — phân vùng rộng/lớn

### 6.1. Tăng kích thước partition theo từng bước

Dùng một `device_id` riêng, không trùng hot-device fixture. Trong `events_unbucketed`, nạp theo các mốc:

| Mốc | Tổng rows trong partition | Payload/row ví dụ | Payload thô gần đúng |
| --- | ---: | ---: | ---: |
| A | 100 | 512 B | 50 KiB |
| B | 2.000 | 512 B | 0,98 MiB |
| C | 10.000 | 512 B | 4,88 MiB |
| D — chỉ khi có headroom | 50.000 | 512 B | 24,4 MiB |

Kích thước **trên disk và trong bộ nhớ khác** phép nhân trên vì còn clustering keys, metadata, encoding, SSTable compression, index, tombstone và storage overhead. Các con số giúp đặt gate, **không phải kết quả đo**.

Các phép đọc nên so:

```sql
-- Chỉ đọc một vài events mới nhất.
SELECT event_ts, event_id
FROM load_it.events_unbucketed
WHERE device_id = ?
LIMIT 20;

-- Đọc một khoảng clustering key (mốc thời gian phải được bind).
SELECT event_ts, event_id, payload
FROM load_it.events_unbucketed
WHERE device_id = ?
  AND event_ts >= ?
LIMIT 100;
```

Tùy clustering order và khoảng thời gian, hai query có đường đọc khác nhau. Không biến benchmark thành `SELECT *` không giới hạn rồi mang toàn bộ result set về một `List` trong Java.

### 6.2. Quan sát page size khác LIMIT

Trong Java:

```java
BoundStatement query = selectRange.bind(deviceId, startTime)
    .setPageSize(100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);
```

`setPageSize(100)` điều tiết **số row mục tiêu mỗi trang CQL**, **không** giới hạn tổng row có thể duyệt. `LIMIT 100` giới hạn tổng số row query trả theo semantics CQL. Kích thước trang nhỏ có thể giảm memory spike nhưng tăng network round trips, không thay đổi partition key.

### 6.3. Đo với hai chế độ đọc

- **Point/range read**: `LIMIT 10/20/100` với partition key và điều kiện clustering phù hợp; đo p99, bytes/query, SSTables đọc.
- **Full logical traversal có giới hạn**: dùng paging qua một số trang cố định, ghi số row và bytes thực xử lý; **không** tải hết 50.000 rows vào RAM nếu không cần.

Nếu query point vẫn nhanh nhưng paging/compaction/repair chậm, báo cáo phải ghi rõ workload gây vấn đề. Partition lớn không được khẳng định “mọi query đều chậm” chỉ từ độ dài.

### 6.4. Không dùng `COUNT(*)` để đo health thường xuyên

```sql
-- Không dùng như health probe định kỳ trên partition rất rộng:
SELECT COUNT(*)
FROM load_it.events_unbucketed
WHERE device_id = ?;
```

Lệnh đếm có thể phải duyệt nhiều dữ liệu và tạo tải không cần thiết. Sử dụng dataset manifest, số rows đã seed, metadata/table histograms và kiểm chứng có kiểm soát thay vì làm COUNT mỗi giây.

## 7. Mô phỏng 3 — nhiều tombstone trên đường đọc

### 7.1. Chuẩn bị một partition có nhiều row sống

Dùng bảng `events_delete_heavy` và một `device_id` riêng. Seed ví dụ 2.000 rows có timestamp tăng dần từ mốc cố định:

```sql
INSERT INTO load_it.events_delete_heavy (
    device_id, event_ts, event_id, payload
) VALUES (?, ?, ?, ?);
```

Sau khi xác minh row có thể đọc, xóa **1.800 rows mới nhất** bằng câu CQL có đủ primary key:

```sql
DELETE FROM load_it.events_delete_heavy
WHERE device_id = ?
  AND event_ts = ?
  AND event_id = ?;
```

Do clustering order là `event_ts DESC`, query sau có thể phải đi qua nhiều vị trí vừa xóa trước khi đến các row cũ còn sống:

```sql
SELECT event_ts, event_id
FROM load_it.events_delete_heavy
WHERE device_id = ?
LIMIT 10;
```

Đây là mô phỏng **tombstone-heavy read**. Dấu hiệu quan trọng là số tombstone phải xem xét để tìm **10 row sống**, không chỉ tổng row trả về.

**Không có bảo đảm mỗi lần DELETE tạo đúng một tombstone có thể đếm độc lập bằng trace.** Cấu trúc cell/range tombstone, memtable/SSTable, compaction và các phiên bản Cassandra ảnh hưởng cách biểu diễn cũng như thống kê.

### 7.2. Biến thể TTL

Thay vì DELETE, có thể tạo dữ liệu hết TTL:

```sql
INSERT INTO load_it.events_delete_heavy (
    device_id, event_ts, event_id, payload
) VALUES (?, ?, ?, ?)
USING TTL 5;
```

TTL tính theo giây từ thời điểm ghi, không theo `Instant` giả lập trong mã Java. Khi dữ liệu hết TTL, nó được xử lý theo tombstone semantics. Nhưng:

- Một test chờ đúng 5 giây bằng `Thread.sleep(5000)` dễ flaky do clock/scheduling/GC/latency.
- Dùng **poll có deadline** và ghi rõ thời gian thực của server; TTL không thể được “freeze” chỉ bằng mock clock phía Java.
- Nếu muốn cô lập ảnh hưởng TTL, không chạy biến thể DELETE/TTL trên cùng partition khi đo baseline.
- Không đổi `gc_grace_seconds` thành 0 để “dọn sạch” nhanh: với replication/repair không đầy đủ có thể gây nguy cơ dữ liệu đã xóa xuất hiện lại.

### 7.3. Khi nào tombstone thật sự gây chậm?

Tombstones nằm trên đường truy vấn và trong SSTables liên quan có thể làm tăng số cells phải xem xét. Cường độ ảnh hưởng tùy:

- Clustering key range mà SELECT phải đi qua.
- Có bao nhiêu tombstones còn hiện diện trong memtable/SSTables.
- Số SSTables phải đối chiếu, overlapping data và compaction strategy.
- RF/CL: đọc từ replica nào, reconcile dữ liệu ra sao.
- Cache, disk latency, GC và số query đồng thời.
- Row size và việc chỉ cần một số row sống cho `LIMIT`.

**LIMIT nhỏ không tự động bỏ qua tombstones.** Tương tự, tăng timeout có thể khiến request chờ lâu hơn nhưng không loại bỏ read amplification.

### 7.4. Ý nghĩa của tombstone warning/failure threshold

Cassandra có những cơ chế/cấu hình giới hạn việc quét tombstone quá nhiều, với tên và cách hành xử phụ thuộc phiên bản, ví dụ `tombstone_warn_threshold` và `tombstone_failure_threshold` trong các cấu hình cổ điển.

Khi vượt ngưỡng, server có thể ghi warning hoặc từ chối truy vấn để bảo vệ hệ thống. **Đừng tăng các ngưỡng này chỉ để benchmark đạt 100% thành công.** Hãy thu warning/tracing và điều tra data model/TTL/delete/compaction. Phiên bản Cassandra mới có thể có giới hạn và cơ chế bảo vệ khác; kiểm tài liệu bản đang chạy.

## 8. Seed fixture bằng Java Driver 4.x có giới hạn

Để so sánh các scenario, dùng `CqlSession` tái sử dụng và prepared statements. Không tạo session cho từng insert hay mỗi HTTP request.

### 8.1. Helper seed một partition

Ví dụ dưới đây **có thể ghép vào test-only fixture class**, dùng JDK 11+ và Java Driver 4.x. Nó cố ý chặn số hàng và payload để tránh vô tình tạo partition hàng gigabyte.

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class EventFixture {

    private static final Instant BASE =
        Instant.parse("2025-03-01T00:00:00Z");

    public static void seedUnbucketed(
            CqlSession session, UUID deviceId,
            int rows, int payloadChars) {

        if (rows < 1 || rows > 10_000) {
            throw new IllegalArgumentException(
                "rows phải nằm trong [1, 10000]");
        }
        if (payloadChars < 1 || payloadChars > 1024) {
            throw new IllegalArgumentException(
                "payloadChars phải nằm trong [1, 1024]");
        }

        PreparedStatement insert = session.prepare(
            "INSERT INTO load_it.events_unbucketed " +
            "(device_id, event_ts, event_id, payload) " +
            "VALUES (?, ?, ?, ?)");

        // Dùng ASCII nên payloadChars ở đây cũng bằng số bytes UTF-8.
        String payload = "x".repeat(payloadChars);

        for (int i = 0; i < rows; i++) {
            UUID eventId = UUID.nameUUIDFromBytes(
                ("event-" + deviceId + "-" + i)
                    .getBytes(StandardCharsets.UTF_8));

            session.execute(insert.bind(
                deviceId,
                BASE.plusMillis(i),
                eventId,
                payload));
        }
    }

    private EventFixture() { }
}
```

**Đặc điểm của helper:**

- `rows <= 10_000` và `payloadChars <= 1024` là guard học tập, không phải hard limit của Cassandra.
- Nếu chạy 64 devices × 20 rows, số insert là 1.280; nếu chạy 10.000 rows vào một device, đó là kịch bản rộng riêng.
- Timestamp/UUID được tạo **deterministic** cho mỗi device/index.
- Dùng ASCII `x` để so bytes đơn giản; dữ liệu thực có UTF-8 nhiều byte/row, compression khác.
- Đoạn này ghi **tuần tự**, phù hợp seed quy mô nhỏ. Khi cần seed lớn, dùng bounded async/batch workflow và rate limit, không tạo một batch khổng lồ trên nhiều partitions.
- Dùng một test keyspace chỉ sau khi xác minh đúng cluster. Không copy helper thành tác vụ production.

### 8.2. Dữ liệu cho hot-key test

Một setup hợp lý:

```java
UUID hotDevice = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

EventFixture.seedUnbucketed(session, hotDevice, 20, 256);

// Tạo 63 device IDs khác với hotDevice, mỗi ID 20 row.
// Các IDs này cần được đưa vào workload driver bên dưới.
```

Giữ **cùng số row/payload** cho hot và cold keys. Nếu hot key chứa 10.000 rows còn cold keys chứa một row, bạn không còn kiểm riêng hot-key skew nữa.

### 8.3. Seed tombstone test có thể tái lập

Dùng cùng cách tạo timestamp/UUID như helper, nhưng bảng `events_delete_heavy`. Gợi ý một helper:

```java
PreparedStatement insert = session.prepare(
    "INSERT INTO load_it.events_delete_heavy " +
    "(device_id, event_ts, event_id, payload) " +
    "VALUES (?, ?, ?, ?)");

PreparedStatement delete = session.prepare(
    "DELETE FROM load_it.events_delete_heavy " +
    "WHERE device_id = ? AND event_ts = ? AND event_id = ?");

UUID deviceId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
Instant base = Instant.parse("2025-03-01T00:00:00Z");

for (int i = 0; i < 2000; i++) {
    UUID id = UUID.nameUUIDFromBytes(
        ("tombstone-" + i).getBytes(
            java.nio.charset.StandardCharsets.UTF_8));

    session.execute(insert.bind(
        deviceId, base.plusMillis(i), id, "payload"));
}

// Xóa 1.800 row mới nhất theo clustering order DESC.
// Chừa lại i=0..199 là 200 row sống.
for (int i = 200; i < 2000; i++) {
    UUID id = UUID.nameUUIDFromBytes(
        ("tombstone-" + i).getBytes(
            java.nio.charset.StandardCharsets.UTF_8));

    session.execute(delete.bind(
        deviceId, base.plusMillis(i), id));
}
```

Đây là fixture **chỉ dùng trên bảng test**, không phải script vận hành xóa hàng loạt trên production. Với Cassandra, một số tombstone có thể tiếp tục tồn tại sau reset và qua các giai đoạn compaction. Nếu muốn baseline thật sự sạch, nên **recreate isolated container/schema** cho scenario khác thay vì giả định DELETE hoặc TRUNCATE tái tạo cùng trạng thái SSTable.

## 9. Java Driver 4.x: một load generator bounded cho hot-key scenario

Đoạn mã dưới đây minh họa **closed-loop asynchronous workload**. Nó không phát tất cả future cùng lúc: chỉ gửi tiếp khi còn slot in-flight. Điều này giúp tránh làm JVM mất kiểm soát trước khi Cassandra được đo.

### 9.1. Thiết kế phép đo

- Tổng số request cố định: 1.000 cho mỗi run.
- Concurrency giới hạn: tối đa 16 in-flight.
- 64 device IDs đã có cùng số row.
- Hai run: `hotRatio=1.0/64` gần đồng đều và `hotRatio=0.80` tập trung vào một key.
- Truy vấn và `LOCAL_ONE` giống nhau cho **lab RF=1**; khi chuyển sang multi-node RF=3, chọn CL phù hợp và giữ nó giống giữa các run.
- Thu số request hoàn tất, thành công/lỗi, throughput và latency percentiles.
- Không đọc/serialize mọi row trong callback; chỉ xác nhận nhận được trang đầu.

### 9.2. Ví dụ load driver

```java
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class BoundedHotReadLoad {

    private static final int REQUESTS = 1_000;
    private static final int MAX_IN_FLIGHT = 16;

    static void measure(
            CqlSession session,
            PreparedStatement read,
            UUID hotDevice,
            List<UUID> allDevices,
            double hotRatio,
            long randomSeed) throws InterruptedException {

        if (allDevices.isEmpty()
                || !allDevices.contains(hotDevice)
                || hotRatio < 0.0 || hotRatio > 1.0) {
            throw new IllegalArgumentException("Invalid workload setup");
        }

        Semaphore slots = new Semaphore(MAX_IN_FLIGHT);
        CountDownLatch done = new CountDownLatch(REQUESTS);
        List<Long> successfulLatencies =
            Collections.synchronizedList(new ArrayList<>());
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();
        Random random = new Random(randomSeed);
        long wallStart = System.nanoTime();

        for (int i = 0; i < REQUESTS; i++) {
            // Backpressure ở phía producer.
            slots.acquire();

            UUID target;
            if (random.nextDouble() < hotRatio) {
                target = hotDevice;
            } else {
                target = allDevices.get(
                    random.nextInt(allDevices.size()));
            }

            long started = System.nanoTime();

            try {
                session.executeAsync(
                    read.bind(target)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_ONE)
                        .setPageSize(100)
                        .setTimeout(Duration.ofSeconds(2))
                        .setIdempotent(true)
                ).whenComplete((page, error) -> {
                    try {
                        if (error == null && page != null) {
                            succeeded.incrementAndGet();
                            successfulLatencies.add(
                                System.nanoTime() - started);
                        } else {
                            failed.incrementAndGet();
                        }
                    } finally {
                        slots.release();
                        done.countDown();
                    }
                });
            } catch (RuntimeException error) {
                failed.incrementAndGet();
                slots.release();
                done.countDown();
            }
        }

        if (!done.await(90, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Run vượt deadline; kiểm các request còn in-flight");
        }

        double wallSec =
            (System.nanoTime() - wallStart) / 1_000_000_000.0;

        Collections.sort(successfulLatencies);

        System.out.printf(
            "hotRatio=%.2f ok=%d fail=%d goodput=%.1f ops/s%n",
            hotRatio,
            succeeded.get(),
            failed.get(),
            succeeded.get() / wallSec);

        if (!successfulLatencies.isEmpty()) {
            System.out.printf(
                "p50=%.2fms p95=%.2fms p99=%.2fms%n",
                percentileMs(successfulLatencies, 0.50),
                percentileMs(successfulLatencies, 0.95),
                percentileMs(successfulLatencies, 0.99));
        }
    }

    static double percentileMs(List<Long> sortedNs, double q) {
        int index = Math.max(0,
            Math.min(sortedNs.size() - 1,
                (int) Math.ceil(q * sortedNs.size()) - 1));
        return sortedNs.get(index) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        UUID hotDevice = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        // Đây là placeholder: điền 64 IDs đã seed với cùng
        // số row/payload, bao gồm hotDevice.
        List<UUID> devices = loadSeededDeviceIds();
        if (devices.size() != 64) {
            throw new IllegalStateException(
                "Cần 64 devices có fixture tương đương");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement read = session.prepare(
                "SELECT event_ts, event_id " +
                "FROM load_it.events_unbucketed " +
                "WHERE device_id = ? LIMIT 10");

            // Warmup riêng, bỏ kết quả warmup khỏi mẫu đo.
            // Cần bổ sung hàm warmup bounded phù hợp.
            // warmup(session, read, devices, 200);

            measure(session, read,
                hotDevice, devices, 0.0, 42L);
            measure(session, read,
                hotDevice, devices, 0.80, 42L);
        }
    }

    // Helper DEMO — phải thay bằng danh sách IDs fixture thật.
    static List<UUID> loadSeededDeviceIds() {
        throw new UnsupportedOperationException(
            "Cần cung cấp IDs đã seed trước khi chạy");
    }
}
```

**Ranh giới của mã minh họa:**

1. `loadSeededDeviceIds()` là **stub cố ý**: code không thể chạy benchmark trước khi cung cấp danh sách 64 IDs đã seed. Không tuyên bố đoạn này là một executable benchmark hoàn chỉnh.
2. `hotRatio=0.0` chọn đều từ `allDevices` (bao gồm hot key) → xác suất hot key là khoảng `1/64`. `hotRatio=0.80` vẫn có một phần hot key trong nhánh 20% còn lại → tỷ lệ thực gần **80,3%** nếu có 64 keys; muốn đúng 80% tuyệt đối thì nhánh cold phải loại hot key.
3. Đây là **closed-loop**, producer chờ slot. Nó có thể che `coordinated omission` khi server chậm. Cần test open-loop theo arrival rate với admission/queue bounded để kiểm SLO production.
4. Percentile chỉ tính **các request thành công**. Phải báo **failure/timeout rate riêng**, và tốt hơn có histogram latency của failed requests để không che tail latency.
5. `List<Long>` có giới hạn vì `REQUESTS=1.000`; khi thử tải lớn phải dùng histogram bounded, không giữ hàng triệu sample objects.
6. Thời gian tính từ lúc có slot trước `executeAsync`; nó **không** gồm thời gian chờ slot ở producer. Đo riêng queue/admission wait nếu đánh giá end-to-end API SLO.
7. Code không đưa CPU-heavy processing vào driver callback. Nếu cần serialize JSON, dùng executor bounded riêng và đo queue của tầng đó.
8. Với timeout write, **không** tự retry khi chưa chứng minh idempotency; ví dụ này chỉ đọc.
9. **Không khởi chạy trên production.** Kết nối `127.0.0.1`, DC và CL chỉ là tham số lab cần xác nhận.

### 9.3. Vì sao benchmark phải kiểm cả goodput và lỗi?

Giả sử run A submit 1.000 reads, thành công 997; run B submit 1.000, thành công 650. Nếu B kết thúc nhanh hơn vì nhiều request fail ngay, throughput tính từ **attempts/s** có thể cao nhưng dịch vụ thực tệ đi. Hãy báo:

\[
\mathrm{goodput} =
\frac{\text{số operation thành công, có kết quả đúng}}
     {\text{thời gian đo}}
\]

\[
\mathrm{error\ rate} =
\frac{\text{số operation thất bại}}{\text{số operation đã hoàn tất}}
\]

Đối với workload write, cần phân biệt **successful CQL response** với trạng thái **nghiệp vụ đã được xác nhận**, nhất là `WriteTimeout` và retry.

## 10. Quan sát cluster: không chỉ nhìn kết quả Java

### 10.1. Lệnh vận hành chỉ đọc

Trong **testbed** và với quyền phù hợp:

```bash
# Tình trạng node và topology:
nodetool status
nodetool describecluster

# Thread pools và những công việc đang chờ:
nodetool tpstats

# Compaction đang thực thi:
nodetool compactionstats

# Thống kê bảng/các phân vị:
nodetool tablestats load_it.events_unbucketed
nodetool tablestats load_it.events_delete_heavy
nodetool tablehistograms load_it events_unbucketed
nodetool tablehistograms load_it events_delete_heavy
```

Tên/khả năng của một số subcommand và nhãn statistic thay đổi theo phiên bản Cassandra. `tablehistograms`/`tablestats` là góc nhìn từ **node đang được hỏi** và có thể phản ánh SSTables/compaction trước đó; không suy luận chính xác toàn cluster từ một lần chụp trên một node.

Nếu cần xác định replica/token của một partition, dùng công cụ/metadata token map hoặc `nodetool getendpoints` theo cú pháp phiên bản thực tế. Chỉ khi biết **replica của hot partition** mới kết luận được tải đang tập trung đúng nơi mong đợi.

### 10.2. Cần đo những gì?

| Nhóm | Metric/góc quan sát | Mục đích |
| --- | --- | --- |
| **Java service** | p50/p95/p99, success/error, concurrency, queue wait | Người dùng thực thấy gì |
| **Java Driver** | request latency, timeout, retry/speculation, pool/in-flight | Tách lỗi driver/routing/retry |
| **Node Cassandra** | CPU, load, disk I/O, network, GC | Xác định node/replica bão hòa |
| **Read path** | read latency, SSTables per read, tombstone scanned khi có | Tìm read amplification |
| **Write path** | write latency, memtable/commit log, dropped messages | Tìm tải ghi và độ bền |
| **Partition metrics** | estimated partition size/cell count distribution | Phát hiện partition quá lớn |
| **Compaction** | pending/running tasks, bytes processed, disk pressure | Tìm ảnh hưởng SSTable/tombstone |
| **Topology** | node UP/DOWN, replica placement, RF/CL | Đọc đúng kết quả phân tán |
| **Test generator** | offered load, admitted load, queue, drops | Tránh load generator tự nghẽn |

**Chỉ số p99 mà không có tỷ lệ lỗi/throughput không đủ.** Tương tự, “CPU cao” không chứng minh nguyên nhân là hot key nếu compaction hoặc GC đang chạy đồng thời.

### 10.3. Cẩn thận với metrics về partition size

Kích thước partition thường được ước tính từ SSTable data/histograms trong khoảng thời gian nhất định; nó không nhất thiết phản ánh tất cả memtable data vừa ghi, mọi bản sao hoặc kích thước logical row trong Java. Ghi chú thời điểm **flush/compaction**, phương thức đo và node đang quan sát.

## 11. Tracing và tombstone diagnostics

### 11.1. Dùng trace có chọn lọc

Trong `cqlsh` trên keyspace test:

```sql
TRACING ON;

SELECT event_ts, event_id
FROM load_it.events_delete_heavy
WHERE device_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
LIMIT 10;

TRACING OFF;
```

Trong trace/logs theo phiên bản, bạn có thể thấy số rows/cells sống và tombstone scanned hoặc các bước SSTable read/reconciliation. Không phải bản Cassandra nào cũng trình bày cùng trường/văn bản; **không assert exact trace line** như một API ổn định.

Trace có overhead và ghi metadata, nên chỉ kích hoạt cho **một số truy vấn lab** khi cần chẩn đoán, không bật toàn bộ traffic. Nếu cần xem tombstone warnings, kiểm server logs/metrics tương ứng trong cửa sổ test.

### 11.2. Kết luận nào là hợp lệ từ một trace?

| Quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Trace cho thấy nhiều tombstones được xét trước 10 rows sống | Query cụ thể chịu read amplification do tombstones | Mọi partition trên bảng đều bị như vậy |
| Một page chậm nhưng tombstone count thấp | Có một đường chậm khác cần tìm | Không nhất thiết wide partition là nguyên nhân |
| Tombstone warning tăng sau DELETE | Delete-heavy workload gây pressure trong test | Tăng threshold là cách sửa đúng |
| Có SSTable overlap và compaction backlog | Cần xem compaction/read amplification | `nodetool compact` lập tức sẽ giải quyết an toàn mọi trường hợp |
| Sau compaction query nhanh hơn | Data layout ảnh hưởng latency | Mọi đợt compaction trong production đều nên bị ép chạy thủ công |

**Không dùng trace/`SELECT COUNT(*)` liên tục trên wide partitions** để “đo cho chắc”; việc chẩn đoán có thể trở thành tải bổ sung.

## 12. Thực nghiệm có kiểm soát: tách từng biến số

### 12.1. Ma trận các run

| Run | Dataset | Phân phối request | Xóa/TTL | Mục tiêu |
| --- | --- | --- | --- | --- |
| `B0` | 64 partitions × 20 rows | Đồng đều | Không | Baseline |
| `H40` | Giữ B0 | 40% vào một key | Không | Bắt đầu quan sát skew |
| `H80` | Giữ B0 | 80% vào một key | Không | Tải tập trung |
| `W2K` | Một partition khác có 2.000 rows | Đọc có giới hạn | Không | Wide ở mức vừa |
| `W10K` | Cùng quy trình, 10.000 rows | Đọc tương đương | Không | Tác động kích thước |
| `T0` | Partition riêng 2.000 rows | Đọc top 10 | Chưa xóa | Tombstone baseline |
| `T90` | Partition của scenario riêng | Đọc top 10 | Xóa 90% row mới | Tombstone-heavy read |
| `R` | Mô hình bucket/shard | Phân phối như H80/W10K | Policy được kiểm soát | Kiểm hướng sửa |

**Giữ các run độc lập**: nếu dùng lại một bảng/partition cho `W10K` và `T90` mà không tái tạo môi trường, các SSTables/tombstones/compaction từ scenario trước có thể làm kết quả khó giải thích.

### 12.2. Closed-loop và open-loop

- **Closed-loop:** tối đa C request đang chờ; server chậm thì client phát chậm theo. Phù hợp khám phá capacity theo concurrency.
- **Open-loop:** gửi theo arrival rate mục tiêu, độc lập với tốc độ hoàn tất. Phù hợp phát hiện queue buildup, rejected/admission và SLO khi overload.

Trong open-loop, phải đặt **bounded queue** và backpressure/drop policy. Nếu producer tạo 100.000 futures chưa hoàn tất, bạn đang đo JVM OOM/retry storm trước khi hiểu Cassandra.

### 12.3. Warmup và repeatability

Một run đáng tin cần:

1. Preload fixture và xác nhận correctness.
2. Warmup đủ để JVM JIT/connection/cache ổn định, **không tính vào đo chính**.
3. Tạo traffic với arrival/concurrency được ghi lại.
4. Thu kết quả trong cửa sổ cố định, có timeouts/deadlines.
5. Giữ cluster idle/cooling period nếu compaction/GC vẫn ảnh hưởng.
6. Lặp lại nhiều run, thay thứ tự các scenario khi có thể để tránh lợi thế run sau vì cache.
7. Ghi version, schema, token distribution, RF/CL, row bytes, test generator host, GC, CPU/disk quota.

Một “benchmark tốt” có thể cho kết quả khác sau khi dữ liệu được cache, memtable flush hoặc compaction. Đây là thực tế vận hành cần ghi lại, không nên xóa các điểm bất lợi khỏi báo cáo.

## 13. Chọn hướng sửa đúng cho từng nguyên nhân

### 13.1. Hot partition: phân tải theo khóa mới, không chỉ tăng thread

Nếu một device có QPS lớn, một cách thử là dùng `shard` trong partition key:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class EventPartitioning {
    public static final int SHARDS = 8;

    public static int shardFor(UUID eventId) {
        return Math.floorMod(eventId.hashCode(), SHARDS);
    }

    public static LocalDate dayUtc(Instant eventTime) {
        return eventTime.atZone(ZoneOffset.UTC).toLocalDate();
    }

    private EventPartitioning() { }
}
```

Ghi:

```sql
INSERT INTO load_it.events_bucketed (
    device_id, event_day, shard, event_ts, event_id, payload
) VALUES (?, ?, ?, ?, ?, ?);
```

**Hệ quả cần trả giá:**

- Để đọc một event khi biết `event_id`, ứng dụng có thể tính shard nếu cùng thuật toán đã được version hóa, **nhưng vẫn cần biết `event_day`** hoặc có bảng lookup.
- Để đọc “20 events mới nhất trong ngày”, phải truy vấn **tối đa 8 shards** rồi merge theo timestamp/event ID.
- Tăng shards làm tăng fan-out, số partitions/query và số request Java; dùng concurrency cap để không tự tạo tải mới.
- Không thay `SHARDS=8` thành 16 vô điều kiện sau này: nếu thuật toán tính shard thay đổi, các events cũ nằm ở shard cũ. Cần versioned routing, dual read hoặc migration/backfill.
- Một hot key có thể được **cache có TTL và invalidation** nếu workload đọc nhiều, nhưng phải xét yêu cầu consistency và staleness.
- Với write-heavy hot key, kiểm contention/LWT, monotonic counters và semantics idempotency.

**Không dùng random shard** nếu yêu cầu tìm một event bằng ID mà không có index/routing metadata; hash shard deterministic giúp định vị nhưng vẫn cần thiết kế đọc.

### 13.2. Wide partition: bucket theo thời gian và giới hạn retention

Nếu một device tạo events liên tục trong nhiều năm, chia partition theo `event_day` hoặc `event_week` có thể giới hạn rows/partition. Chọn bucket dựa trên:

\[
\mathrm{rows/bucket}\approx \mathrm{write\ rate}\times\mathrm{bucket\ duration}
\]

Ví dụ 2 events/giây trong một ngày:

\[
2\times86{,}400=172{,}800\ \mathrm{rows/day}
\]

Điều này **có thể vẫn quá nhiều** tùy row size và workload; bucket một giờ hoặc thêm shard có thể phù hợp hơn. Không chọn “theo ngày” theo thói quen khi một device có QPS cao.

Khi áp dụng:

- Xác định mọi query cần biết `event_day`/time range như thế nào.
- Giới hạn số buckets mà một request được phép fan-out.
- Đảm bảo timestamp và bucket được tính theo **cùng timezone/quy tắc**; với event UTC, dùng ngày UTC.
- Đối soát backfill, late-arriving events và thao tác DELETE/TTL.
- Chọn compaction strategy theo write-time/TTL workload, không coi việc chọn TWCS là thuốc chữa mọi partition lớn.
- Nếu cần “latest event” tức thời, có thể có bảng projection `latest_event_by_device` riêng, nhưng phải xử lý denormalization, idempotency và consistency.

### 13.3. Tombstone-heavy: sửa pattern ghi/xóa và đường đọc

Các hướng thường xem xét:

1. **Giảm xóa từng row** trên một partition lớn. Có thể dùng bucket/partition lifecycle để loại bỏ dữ liệu theo khoảng đã hết retention bằng cách thiết kế partition phù hợp; vẫn phải tuân thủ ngữ nghĩa xóa phân tán.
2. Rà soát TTL: giá trị khác nhau/tạo expired data nằm xen với dữ liệu sống có thể làm đọc tốn công.
3. Với bảng time-series và TTL tương đối đồng nhất, đánh giá **TimeWindowCompactionStrategy (TWCS)** theo tài liệu/version và đặc tính out-of-order writes; TWCS **không** tự giải quyết mọi tombstone.
4. Kiểm repair và compaction trước khi thay `gc_grace_seconds`; không giảm bừa vì nguy cơ dữ liệu xóa bị tái xuất hiện.
5. Thay query để dùng clustering range hẹp, không ép quét qua vùng đã xóa khi có lựa chọn mô hình khác.
6. Theo dõi tombstone scanned/read, compaction backlog và p99 sau mỗi thay đổi.
7. Nếu workload cần xóa hàng loạt lịch sử, cân nhắc **đổi mô hình partition theo vòng đời dữ liệu** thay vì DELETE hàng triệu clustering rows riêng lẻ.

**Không khuyến nghị chạy `nodetool compact` trên production như một cách “dọn tombstone ngay”**: forced compaction tiêu tốn I/O/disk và không bảo đảm tombstones đủ điều kiện purge. Mọi thay đổi compaction/repair cần runbook và kiểm tra an toàn.

## 14. Kết quả trước/sau: trình bày không đánh tráo workload

Một bảng ví dụ **hoàn toàn giả định** để minh họa báo cáo, không phải số đo Cassandra:

| Scenario | Goodput (ops/s) | p50 | p95 | p99 | Error % | Tombstones/read |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline B0 | 800 | 8 ms | 20 ms | 35 ms | 0,0% | Thấp |
| Hot H80 | 770 | 12 ms | 55 ms | 140 ms | 0,2% | Thấp |
| Wide W10K, đọc range | 650 | 20 ms | 85 ms | 210 ms | 0,5% | Thấp |
| Tombstone T90 | 480 | 34 ms | 160 ms | 390 ms | 2,1% | Cao |
| Bucket/shard R | 780 | 10 ms | 29 ms | 60 ms | 0,1% | Phụ thuộc query |

Không nên so bảng này theo kiểu R “tốt nhất” nếu query ở R đã trở thành đọc **một shard** trong khi baseline phải đọc **tất cả events**. Để so công bằng, ứng dụng phải thực hiện **cùng kết quả nghiệp vụ**, bao gồm fan-out và merge; thời gian đo phải tính cả chi phí ở phía Java.

### 14.1. Khi nào kết luận “đã tìm được nguyên nhân”?

Chỉ nên kết luận khi có bằng chứng chéo:

- Hot key: request distribution lệch + replica sở hữu token chịu tải + latency theo key/replica biến thiên cùng mức skew.
- Wide partition: kích thước partition/cell count tăng + query I/O/fetch latency tăng theo kích thước hoặc phạm vi đọc.
- Tombstone-heavy: trace/metric chỉ ra tombstone scanned cao + p99 tăng sau delete/TTL có kiểm soát + hiệu ứng có thể tái hiện.
- Cùng lúc loại trừ: network/GC của load generator, compaction/repair đang chạy, thay CL/page size và node mất kết nối.
- Kịch bản sửa có **query semantics giống trước**, có số request/bytes/fan-out thực, không chỉ nhìn một chỉ số.

## 15. Phân biệt các loại timeout khi tải tăng

| Tình huống | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| `UnavailableException` | Không đủ replica khả dụng để thỏa CL theo coordinator | Không phải mọi dữ liệu đã mất |
| `ReadTimeoutException` | Coordinator chưa nhận đủ response/data đọc trong hạn | Không phải partition không tồn tại |
| `WriteTimeoutException` | Ghi chưa có đủ ACK trong hạn | Không phải mutation chắc chắn chưa xảy ra |
| Driver request timeout | Client chưa có kết quả trước timeout | Không biết server đã thực hiện mutation chưa |
| Tombstone-related query failure | Truy vấn có thể bị bảo vệ do scan quá nhiều tombstone | Không nên sửa bằng hạ ngưỡng bảo vệ |
| Application deadline exceeded | Toàn endpoint vượt SLO | Không nhất thiết CQL attempt đơn lẻ đã timeout |

Khi mô phỏng tải ghi hoặc xóa:

- Không retry tự động mọi `WriteTimeout`.
- Nếu ghi append list/counter hoặc phát effect ngoài Cassandra, replay có thể gây side effect lặp.
- Đặt `setIdempotent(...)` theo **bản chất thao tác**, không theo mong muốn tăng throughput.
- Giới hạn retries/backoff/jitter và giữ **logical request ID** khi cần reconciliation.
- Không đổi CL chỉ để benchmark ít lỗi hơn nếu ứng dụng production yêu cầu nhất quán cao hơn.

Đặc biệt với hot partition có LWT contention, việc tăng concurrency có thể làm latency lớn hơn mà không cải thiện throughput nghiệp vụ. Cần tách **contention** khỏi read/write latency thông thường.

## 16. Bài test fault injection nhiều node: chỉ mở rộng sau khi có baseline

Hot/wide/tombstone là các **kịch bản tải và hình dạng dữ liệu**, không bắt buộc gây lỗi node. Để liên hệ chúng với tính phân tán, testbed nhiều node có thể bổ sung:

1. Chạy baseline RF=3, `LOCAL_QUORUM`, đo đủ health/latency.
2. Tạo hot-key hoặc tombstone-heavy dataset với tải thấp có kiểm soát.
3. Giới hạn request in-flight và đặt stop condition.
4. Làm **một** replica của partition chậm hoặc không khả dụng bằng công cụ fault injection được quản trị trong cluster lab.
5. Quan sát `Unavailable` vs `ReadTimeout` vs `WriteTimeout`, routing và replica fallback/retries.
6. Khôi phục node/network, chờ cluster ổn định, kiểm consistency/read-back theo CL.
7. So kết quả với cùng fault khi dữ liệu/traffic không bị skew.

### 16.1. Những điều không được suy từ một node RF=1

- Không chứng minh đọc quorum RF=3 vẫn thành công khi một node DOWN.
- Không chứng minh repair/anti-entropy giữa replica.
- Không mô phỏng cross-DC latency hay `EACH_QUORUM`.
- Không suy hiệu năng compaction/streaming production từ container nhỏ.
- Không kiểm được coordinator lựa chọn replica trong một token ring nhiều node như production.

### 16.2. Không đưa lệnh phá hoại cluster vào test runner dùng chung

Lỗi mạng, dừng node hoặc giới hạn disk I/O cần môi trường và quyền riêng. Không tạo một helper tự động “kill Cassandra node” nhận địa chỉ tùy ý từ user input. Tất cả destructive fault injection phải được cấp quyền, có allowlist, timeout và cleanup/rollback rõ.

## 17. Runbook thực hành

### Pha A — Chuẩn bị

1. Chọn cluster test cô lập, ghi Cassandra/Driver version và topology.
2. Tạo `load_it` với NTS và RF phù hợp số node/DC thật.
3. Tạo ba bảng `events_unbucketed`, `events_bucketed`, `events_delete_heavy`.
4. Kiểm schema agreement/expected schema; chuẩn bị IDs/timestamps/payload deterministic.
5. Chọn bộ chỉ số: success goodput, latency p50/p95/p99, error breakdown, in-flight, CPU/GC/disk, tombstone scanned, partition bytes.
6. Đặt guard: max rows, request count, duration, disk, p99, timeouts và abort/teardown.

### Pha B — Hot-key scenario

1. Seed 64 partitions × 20 rows/payload đồng đều.
2. Warmup với traffic đồng đều, ghi baseline.
3. Chạy `hotRatio=0.0`, phân tích số request tới hot/cold.
4. Chạy `hotRatio=0.40` và `0.80` với cùng QPS/concurrency.
5. So p99 theo key/replica, số attempts, CPU, network/queue.
6. Không tăng tổng throughput cùng lúc thay distribution nếu chưa có run riêng.

### Pha C — Wide-partition scenario

1. Dùng `device_id` mới và schema sạch.
2. Seed 100 → 2.000 → 10.000 rows, giữ payload/row không đổi.
3. Đọc `LIMIT 20` rồi một range có bounds tường minh.
4. Đo partition size/bytes/fetch latency, SSTables và client memory.
5. Không dùng query full-scan/`COUNT(*)` làm health check lặp lại.
6. Chạy đối chứng với bucket theo thời gian; tính cả fan-out nếu có.

### Pha D — Tombstone scenario

1. Dùng bảng/partition riêng, seed 2.000 rows còn sống.
2. Đo read baseline với `LIMIT 10`.
3. Xóa 1.800 rows mới nhất bằng prepared `DELETE`, chờ các writes hoàn tất.
4. Đọc lại cùng query, quan sát trace/tombstone warnings và latency.
5. Không coi một lần compaction ngẫu nhiên giữa hai run là biến kiểm soát; ghi trạng thái SSTables/compaction.
6. Thử biến thể TTL ở môi trường sạch khác, không trộn với DELETE run.
7. Không hạ `gc_grace_seconds` hoặc threshold để ép kết quả.

### Pha E — Phân tích và thử remediation

1. Xác định hot, wide, tombstones hoặc kết hợp bằng evidence.
2. Chọn **một** thay đổi data model/retention/routing để thử.
3. Nếu bucket/shard, cập nhật code ghi và code đọc/merge có giới hạn.
4. Chạy lại workload **trả cùng thông tin nghiệp vụ** và CL như trước.
5. So goodput, p99, error, bytes/query, request fan-out, CPU/disk/compaction.
6. Dừng/rollback nếu tổng chi phí hoặc correctness tệ hơn.
7. Ghi báo cáo và cleanup container/schema test an toàn.

## 18. Bài tập thực hành và gợi ý giải

### Bài 1 — Phân biệt hiện tượng

Ba partition:

- A: 20 rows, nhận 5.000 reads/s.
- B: 200.000 rows, nhận 5 reads/s.
- C: 300 rows còn sống, nhưng phải duyệt hàng nghìn dấu xóa để trả `LIMIT 10`.

Hãy phân loại hot/wide/tombstone. Với mỗi partition, chọn **hai metric** và một hướng sửa.

**Gợi ý:**

- A: hot key; per-key QPS, replica CPU/queue, shard/cache khi business cho phép.
- B: wide partition; partition bytes/rows, SSTables/range latency, time bucket/retention.
- C: tombstone-heavy; tombstone scanned/read, p99/compaction; giảm delete-heavy pattern và phân vùng theo vòng đời dữ liệu.

### Bài 2 — Phân phối hot key

Có 1.500 reads/s và 80% requests vào một partition key.

1. Bao nhiêu reads/s kỳ vọng vào hot key?
2. Nếu cluster có 12 nodes và RF=3, có thể giả định 1.200 reads/s tự chia đều cho cả 12 nodes không?
3. Vì sao tăng coordinator threads không tạo thêm replicas cho partition?
4. Làm sao kiểm ứng dụng thật đang chọn token-aware coordinators?

**Gợi ý:** `1500×0.8=1200` reads/s. Partition chỉ có nhóm replica theo RF/topology, không trải đều lên mọi node. Kiểm driver routing, token/replica map và per-node/per-key metrics.

### Bài 3 — Wide partition và bytes

Một device lưu 100.000 events, payload trung bình 800 B/row.

1. Payload thô gần bao nhiêu MiB?
2. Vì sao kích thước on-disk có thể khác?
3. `setPageSize(100)` có chia partition vật lý thành 1.000 partition không?
4. Nếu device tạo 2 events/s, bucket theo ngày chứa khoảng bao nhiêu rows?

**Gợi ý:** khoảng `76,3 MiB` payload thô chưa overhead/compression. Page size là paging protocol, không thay partition key. Hai events/s × 86.400 giây ≈ 172.800 rows/day, có thể cần bucket nhỏ hơn hoặc shard.

### Bài 4 — LIMIT và tombstones

Bạn seed 2.000 rows, xóa 1.800 rows mới nhất, sau đó query `LIMIT 10` theo clustering order DESC.

1. Query có thể phải xử lý bao nhiêu vị trí đã xóa trước khi lấy row sống?
2. Vì sao LIMIT 10 không bảo đảm query nhẹ?
3. Những metric/log nào nên kiểm?
4. Có nên nâng `tombstone_failure_threshold` để test không lỗi?

**Gợi ý:** có thể đi qua rất nhiều tombstones; số scanned thực tế phải đo. Kiểm tombstone scanned/read, trace, p99, SSTables/compaction. Không nâng threshold để che read amplification.

### Bài 5 — Thí nghiệm thiếu công bằng

Baseline dùng `LOCAL_QUORUM`, 10.000 rows và payload 1 KiB. Run mới dùng `LOCAL_ONE`, chỉ 100 rows và payload 128 B, nhưng báo p99 giảm 80%.

1. Vì sao chưa thể kết luận code bucket/shard tốt hơn?
2. Cần giữ biến nào giống nhau?
3. Nếu dùng shard, phải đo thêm chi phí nào để phục vụ query “20 events mới nhất”?

**Gợi ý:** đã đổi CL, row count, payload và query semantics. Giữ cùng workload/CL/dataset nghiệp vụ; đo fan-out và merge, không chỉ một shard query.

### Bài 6 — Retry storm dưới tải

Một service 2.000 requests/s gặp timeout 30%; middleware tự retry tối đa 3 lần và driver còn retry riêng.

1. Vì sao attempts có thể lớn hơn logical operations?
2. Nhiều retries có thể làm hot partition tệ hơn thế nào?
3. Với `WriteTimeout`, có chắc mutation chưa áp dụng không?
4. Chính sách an toàn nào cần có?

**Gợi ý:** retry có thể tăng tải khi server vẫn đang xử lý request cũ. Giới hạn in-flight, retry budget, backoff/jitter; write outcome có thể không rõ, cần idempotency/reconciliation.

### Bài 7 — Chọn remediation cho thiết bị có tải cực lệch

Một số `device_id` tạo 10.000 events/phút; phần lớn devices khác chỉ vài events/ngày. API cần tìm events theo ngày và lấy 20 events mới nhất.

1. Chỉ bucket theo ngày có đủ cho hot devices không?
2. Nên xét shard nào, dựa trên metric gì?
3. Fan-out đọc cần kiểm soát thế nào?
4. Khi số shards đổi, lịch sử cũ được đọc bằng thuật toán nào?

**Gợi ý:** bucket ngày có thể còn lớn/hot. Xem bytes/day, QPS/partition, p99 và replica pressure; chọn shard count theo tải, version routing và merge bounded.

### Bài 8 — Ghi báo cáo trước/sau

Hãy lập bảng gồm:

- CQL, schema/partition key, dataset size, TTL/delete ratio.
- RF/CL, Driver/Server version, node/DC và load-generator hardware.
- Arrival rate/in-flight, duration/warmup, goodput, p50/p95/p99, error rate.
- Tombstone scanned, partition size histogram, compaction/disk/GC.
- Kết luận còn thiếu bằng chứng gì và điều kiện rollback.

**Gợi ý:** nêu rõ số liệu là dữ liệu đo thật hay giả định, ghi nguồn metric và tính thời điểm. Một thay đổi p99 không chứng minh cải thiện tổng thể nếu error rate/bytes/fan-out tăng.

## 19. Checklist trước khi kết luận

- [ ] Đã sử dụng keyspace và cluster **thử nghiệm cô lập** với dữ liệu giả.
- [ ] Có giới hạn request, in-flight, row count, payload size, disk/time và abort condition.
- [ ] RF/CL đúng topology; không suy quorum RF=3 từ một node RF=1.
- [ ] Biết partition key, clustering key và mẫu query thực tế của ba bảng.
- [ ] Hot-key run giữ row count/payload tương đương giữa hot/cold partitions.
- [ ] Có phân phối key rõ ràng (uniform/skew) và seed RNG để tái hiện.
- [ ] Đã loại trừ coordinator routing lệch trước khi kết luận hot partition.
- [ ] Wide-partition run thay số rows/bytes có kiểm soát và đo range/read/page behavior.
- [ ] Không nhầm driver page size, CQL LIMIT và kích thước physical partition.
- [ ] Không dùng `COUNT(*)`/full scan như health check lặp lại trên partition lớn.
- [ ] Tombstone run có baseline trước DELETE/TTL và partition test riêng.
- [ ] Đo tombstone scanned/read hoặc trace có chọn lọc, không dựa chỉ vào số rows đã DELETE.
- [ ] Không hạ `gc_grace_seconds` hoặc nâng tombstone thresholds để che vấn đề.
- [ ] Theo dõi trạng thái compaction/SSTables, repair, GC, disk và network khi so các run.
- [ ] Thu p50/p95/p99, goodput, timeout/error breakdown và latency của failed requests.
- [ ] Java load generator dùng prepared statements, session reuse và bounded concurrency.
- [ ] Open-loop test có bounded queue/backpressure, không phát vô hạn futures.
- [ ] Không để retries/speculative attempts làm sai phép đo logical throughput.
- [ ] Với writes, đã phân biệt response timeout và kết quả mutation chưa rõ.
- [ ] Remediation bucket/shard được test với **cùng business query** và fan-out/merge thực.
- [ ] Có kế hoạch version shard routing, late events, retention và migration/backfill.
- [ ] Có multi-node test riêng nếu kết luận liên quan failover/quorum/repair.
- [ ] Không thực hiện destructive fault injection ngoài testbed có allowlist và recovery.
- [ ] Báo cáo ghi rõ version, dataset, node/DC, RF/CL, query, latency, metrics và giới hạn kết luận.

## 20. Tài liệu cần đối chiếu theo phiên bản

- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): primary key, partition/clustering columns, DELETE, TTL và truy vấn.
- [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/latest/): kiến trúc phân tán, compaction, repair và monitoring theo bản Server cụ thể.
- [Apache Cassandra Java Driver — Request Tracking](https://apache.github.io/cassandra-java-driver/4.18.1/core/request_tracker/): quan sát statement/retry/latency phía client.
- [Apache Cassandra Java Driver — Query Options](https://apache.github.io/cassandra-java-driver/4.18.1/core/query_options/): timeout, page size, CL và idempotence theo statement.
- [Apache Cassandra Java Driver — Manual Paging](https://apache.github.io/cassandra-java-driver/4.18.1/core/paging/): sự khác nhau giữa paging đồng bộ/bất đồng bộ.
- [Apache Cassandra — nodetool reference](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html): các lệnh kiểm node/table và metrics; cú pháp có thể đổi theo version.

**Kết luận:** Trong Cassandra, **khóa nóng** là vấn đề phân bố request theo partition key, **phân vùng lớn** là vấn đề kích thước/lượng dữ liệu trong một partition, còn **tombstone-heavy read** là vấn đề read amplification do xóa/TTL. Cả ba có thể làm p99 tăng nhưng cần **fixture và phép đo tách biệt** để tìm đúng nguyên nhân. Hãy mô phỏng trong testbed cô lập, giữ RF/CL/CQL/dataset được kiểm soát, phát tải Java có giới hạn, theo dõi replica/SSTables/tombstone và so **goodput + p99 + error rate + correctness**. Chỉ sau khi có bằng chứng mới đánh giá bucketing/sharding, retention, compaction strategy hoặc thay đổi mẫu truy vấn — không dùng tăng timeout, tăng page size hay retry không giới hạn làm giải pháp thay thế cho thiết kế dữ liệu.
