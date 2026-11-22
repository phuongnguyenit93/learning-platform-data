# Tombstone quá nhiều hoặc truy vấn chạm phân vùng lớn

## 1. Tình huống thực tế: API timeline chậm dù chỉ lấy 20 bản ghi

Một hệ thống Java dùng **Apache Cassandra** lưu sự kiện IoT và cho phép truy vấn 20 sự kiện gần nhất của một thiết bị. Những tháng đầu, API có p99 dưới 50 ms. Sau khi bật TTL 30 ngày, tăng lượng ingestion và thêm thao tác xóa hàng loạt, một số truy vấn mất vài giây hoặc trả read timeout. Log node đôi khi xuất hiện cảnh báo **quét rất nhiều tombstone**, trong khi một nhóm thiết bị khác có **partition quá lớn** nên đọc chậm dù gần như không có tombstone.

Vấn đề đáng chú ý: hai tình huống cùng có thể xảy ra trên một bảng, nhưng **nguyên nhân, bằng chứng và cách xử lý không giống nhau**:

- **Tombstone-heavy read:** replica phải duyệt nhiều marker xóa/hết hạn hoặc phiên bản SSTable trước khi tìm được đủ hàng sống; `LIMIT 20` không đồng nghĩa chỉ đọc 20 ô vật lý.
- **Oversized/hot partition:** một partition key gom quá nhiều clustering rows/bytes hoặc quá nhiều request, làm tăng memtable/SSTable work, compaction, heap/GC, disk/network, đặc biệt khi query quét một khoảng rộng.
- **Cả hai:** một partition khổng lồ có nhiều hàng TTL hết hạn hoặc nhiều range delete; p99 tăng mạnh và cần kết hợp xử lý workload/query shape cùng data lifecycle.

~~~mermaid
flowchart TD
    A["API SELECT LIMIT 20, p99 cao"] --> B["Coordinator đọc theo partition key"]
    B --> C["Một/nhiều full replicas đọc memtable + SSTables"]
    C --> D{"Hàng sống tìm thấy dễ không?"}
    D -->|Tombstones dày đặc| E["Scan nhiều deletion markers/cells"]
    D -->|Partition lớn hoặc range rộng| F["Quét nhiều clustering rows/bytes và SSTables"]
    E --> G["Disk/CPU/GC/network, read timeout hoặc warning"]
    F --> G
    G --> H["Cần đo đúng nguồn, không chỉ tăng timeout"]
~~~

Bài học thuộc chương **Xử lý sự cố** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`: kiến trúc phân tán, mô hình wide-column, partition key, thiết kế bảng theo truy vấn, read/write consistency, replication, compaction, repair và tích hợp ứng dụng Java.

**Mục tiêu:**

1. Phân biệt tombstone, expired TTL cell, partition/range/row deletion, phân vùng lớn và hot partition.
2. Đọc tín hiệu timeout, cảnh báo tombstone, histograms, tracing và phân bố tải trước khi chọn phương án sửa.
3. Viết truy vấn CQL có **đầy đủ partition key + clustering range + limit**; biết tại sao vẫn có thể đắt.
4. Truy nguyên nguyên nhân từ TTL, `DELETE`, `UPDATE ... SET column=null`, write patterns, bucket size, data skew và compaction strategy.
5. Đánh giá an toàn của `gc_grace_seconds`, tombstone purge, hints, replica repair và nguy cơ zombie data.
6. Phân biệt giải pháp giảm tác động ngắn hạn (rate/concurrency/page/timeout policy) với giải pháp bền vững (bucket/shard/table theo truy vấn).
7. Xây runbook, dashboard, Java Driver guardrails, integration/load tests và điều kiện xác nhận sự cố đã được xử lý.

> **Phạm vi phiên bản:** ví dụ dùng CQL/driver 4.x và các khái niệm Apache Cassandra 4.x/5.x; tên lệnh, metric, guardrails, compaction options và mặc định cảnh báo có thể thay đổi theo bản triển khai. Không coi giá trị minh họa là ngưỡng áp dụng cho production. Những lệnh vận hành có thể gây tải chỉ được thực hiện khi có quyền và kế hoạch trên cluster phù hợp.

## 2. Đầu tiên phân biệt ba hiện tượng

| Hiện tượng | Thường thấy | Cần chứng minh gì? | Sửa theo hướng nào? |
| --- | --- | --- | --- |
| **Tombstone-heavy query** | Log warning/error quét deletion markers; tombstone-scanned histogram cao; ít live rows nhưng latency lớn. | Truy vấn đang quét bao nhiêu tombstone, thuộc partition/range nào, xóa/TTL từ đâu. | Chặn pattern tạo tombstone quá mức, cải thiện query locality, retention/compaction/repair theo chính sách. |
| **Large partition** | Estimated/max partition size lớn, nhiều clustering rows, scan/truyền nhiều bytes, GC/disk/compaction tăng. | Partition key nào dồn dữ liệu, tỉ lệ bytes/rows và truy vấn đụng bao nhiêu range. | Thiết kế lại partition key, bucket thời gian, shard bounded, projection theo query. |
| **Hot partition** | Một vài key chịu read/write QPS cao, một số replica/coordinator nóng dù partition không cực lớn. | Phân phối QPS theo keys/tokens và replica placement, có hay không skew. | Cache/rollup, rate control, phân bố/sharding có giới hạn, sửa workload. |
| **Cluster overload khác** | p99 cao trên nhiều tables, GC/disk/compaction/repair backlog, network hoặc driver throttler. | Tương quan timeline với CPU, disk, GC, pending tasks, retries. | Xử lý bottleneck vận hành, không kết luận do tombstone nếu chưa có bằng chứng. |

Một partition có thể chỉ vài MiB nhưng **rất nóng**; ngược lại partition vài trăm MiB có thể ít đọc và không gây incident ngay. Không gán mọi p99 cao cho “partition lớn” chỉ vì table chứa nhiều rows toàn cluster: Cassandra phân phối **theo token của từng partition**, còn câu hỏi là **một key cụ thể** lớn/nóng tới mức nào.

### 2.1. Dấu hiệu cần phân loại ngay từ client

~~~text
request:
  query_name          = events_recent_by_device_day
  CQL shape           = SELECT ... WHERE full_partition_key AND time_range
  regular CL          = LOCAL_QUORUM
  driver page size    = 100
  CQL LIMIT           = 100
  request timeout     = 1s (ví dụ)
  device/day          = đã redact hoặc hash có kiểm soát

observed:
  error class         = ReadTimeout / Unavailable / client timeout / other
  latency             = ...
  attempts/coordinator= ...
  rows actually read  = ...
  app JSON bytes      = ...
~~~

**`ReadTimeout`**, **`Unavailable`** và driver request timeout không giống nhau; cũng không có nghĩa dữ liệu đã mất. Một truy vấn bị chặn vì tombstone limit khác với request thất bại do không đủ replicas. Phân loại lỗi chính xác trước khi retry/thay CL.

## 3. Tombstone là gì trong Cassandra?

**Tombstone** là dấu đánh dấu deletion/expiry trong cấu trúc dữ liệu Cassandra, được dùng khi hòa giải nhiều phiên bản cell trên replicas và SSTables. Việc một API không còn nhìn thấy row **không có nghĩa** dữ liệu vật lý cùng deletion marker đã được xóa khỏi tất cả SSTables ngay lập tức.

### 3.1. Các dạng thường gặp

| Dạng | Nguồn phổ biến | Hệ quả đọc/vận hành |
| --- | --- | --- |
| **Cell tombstone** | Xóa/đặt `null` một column, hoặc TTL của cell kết thúc. | Có thể phải xét deletion marker trước khi quyết định cột nào còn sống. |
| **Row deletion** | `DELETE` một row theo đầy đủ clustering key. | Các cell của row bị che theo deletion timestamp; cần replica convergence. |
| **Range tombstone** | `DELETE` một khoảng clustering rows trong partition. | Quét clustering range có thể phải xét interval markers, nhất là nhiều khoảng chồng nhau. |
| **Partition deletion** | `DELETE` cả partition theo partition key. | Có thể che các rows của toàn partition với deletion time; scope/range và SSTables vẫn quan trọng. |
| **TTL expiration** | `USING TTL` hoặc `default_time_to_live`. | Cell hết hạn về mặt logic, được xử lý như deletion/expiry trong read/compaction. |

**Không phải mọi `UPDATE` đều tạo tombstone:** ghi giá trị hợp lệ lên cùng cell tạo một version mới; xóa cột hoặc đặt `null` thường là thao tác xóa cần được kiểm chứng theo mapping/driver. Cũng không đúng khi nói “mọi cell cũ sau overwrite đều là tombstone”: version cũ có thể bị shadowing và được compaction dọn theo các quy tắc tương ứng.

### 3.2. Vì sao không xóa ngay?

Cassandra có nhiều replicas và lưu memtables/SSTables theo mô hình LSM. Nếu R1 nhận `DELETE` khi R3 đang down, R3 có thể vẫn giữ row cũ. Tombstone phải tồn tại đủ lâu và được lan truyền bởi replication/repair để tránh row cũ tái xuất hiện (**zombie data**) khi replica quay lại.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant R1 as R1
    participant R2 as R2
    participant R3 as R3 (down)
    C->>R1: DELETE key
    C->>R2: DELETE key
    C--xR3: Missing delete
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>C: LOCAL_QUORUM đạt 2/3
    Note over R1,R2: Tombstone còn để chặn version cũ
    Note over R3: Row cũ vẫn có thể còn
    Note over R1,R3: Repair/hint và grace policy quyết định an toàn
~~~

### 3.3. Tombstone scan count không phải tổng tombstones tồn tại trên đĩa

Một cảnh báo “scanned X tombstones” phản ánh **đường đọc cụ thể** ở replica/coordinator theo instrumentation/version. Nó **không** đồng nghĩa toàn table chỉ có X tombstones, cũng không có nghĩa một hàng sống tương ứng một tombstone. Mặt khác, histogram table có thể là **phân phối phép quét gần đây**, không phải phép đếm tất cả tombstone storage.

## 4. Large partition: kích thước logic, kích thước trên đĩa và số hàng quét

Một Cassandra partition gồm các rows có cùng **full partition key**, được sắp theo clustering keys. Partition có thể trải qua nhiều SSTables và nhiều replicas, nên “kích thước partition” cần gắn định nghĩa:

- **Logical live bytes/rows:** lượng dữ liệu hiện đang đọc được theo CQL tại một thời điểm/CL.
- **SSTable partition bytes:** lượng dữ liệu trong SSTable cụ thể, có thể gồm versions/tombstones; một logical partition hiện diện trên nhiều SSTables.
- **Tài nguyên của một read:** số SSTables/bytes/cells/markers thực sự phải giải mã hoặc hợp nhất để trả query.
- **Hotness:** số read/write requests, concurrency và replicas bị đánh nóng bởi một key, không tỉ lệ thuận đơn giản với bytes.

### 4.1. Mẫu bảng dễ tạo partition phình to

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_diag
WITH replication = {'class':'NetworkTopologyStrategy','dc1':3};

-- V1: MỖI thiết bị chỉ có một partition, mọi năm sự kiện tích lũy chung.
CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_v1 (
    tenant_id text,
    device_id text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id,device_id),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

Nếu `device-7` tạo 25 sự kiện/giây và mỗi row trung bình 600 bytes **payload + overhead ước tính**:

\[
25\times86{,}400\times600
=1{,}296{,}000{,}000\ \text{bytes/ngày}
\approx1{,}21\ \text{GiB/ngày}.
\]

Chỉ một tháng đã có thể vượt **vài chục GiB** về lượng dữ liệu ghi logic cho **một partition key** nếu không có TTL/bucket; physical disk còn phụ thuộc compression, compaction, tombstones và replication RF. Con số chỉ **minh họa**, không phải một ngưỡng Cassandra hay cam kết tỷ lệ nén.

### 4.2. Cassandra không có một giới hạn partition “tốt cho mọi workload”

Không viết quy tắc “mọi partition phải dưới đúng X MiB” như một đảm bảo chính thức. Mục tiêu vận hành nên đặt theo **thống kê workload**:

| Chỉ số | Hỏi gì? | Vì sao liên quan? |
| --- | --- | --- |
| p95/p99 partition size ước tính | Có đuôi phân phối lớn khác thường? | Một vài key có thể chiếm phần lớn dung lượng và disk work. |
| Max partition size/row count | Key nào gây outlier? | Query/range rộng chịu rủi ro cao. |
| Rows read/page và bytes returned | Có đọc quá rộng hoặc kéo `payload` không cần? | Heap/GC/network ở Java và replicas. |
| SSTables per read | Có phải hợp nhất nhiều file/versions không? | Read amplification. |
| Partition-specific QPS | Một key có bị hotspot? | Replica/coordinator scheduling và cache pressure. |
| TTL/delete density | Tỉ lệ tombstones so với live rows? | Tombstone scanning/compaction. |

Một partition vài chục MiB vẫn có thể gây vấn đề nếu chứa **hàng triệu rows cực nhỏ** và phải quét nhiều tombstone; một partition lớn nhưng query có clustering range hẹp có thể ổn hơn. **Đo read path thật**, không chỉ dùng kích thước file làm lời giải thích cuối.

## 5. Đường đọc: vì sao `LIMIT 20` vẫn chậm?

### 5.1. CQL chỉ giới hạn *kết quả logic*

~~~sql
-- Truy vấn có full partition key, nhưng KHÔNG có bound thời gian.
SELECT event_time,event_id,event_type,payload
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a' AND device_id='device-7'
LIMIT 20;
~~~

Nếu 500.000 rows gần vị trí đọc đầu tiên đã hết TTL/tombstoned, Cassandra có thể phải **đi qua nhiều deletion markers/versions** để tìm 20 live rows. `LIMIT` không bắt replica chỉ xét 20 physical cells hoặc 20 bytes. Trường hợp xấu có thể tạo warning, tombstone failure hoặc timeout tùy version/threshold/workload.

### 5.2. Dùng clustering range đúng nhu cầu

~~~sql
SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z'
LIMIT 100;
~~~

Đây là **partition lookup + clustering time range** có giới hạn, tốt hơn quét toàn bộ lịch sử nếu sản phẩm chỉ hỏi một ngày. Tuy nhiên, nếu **chính khoảng ngày đó** có hàng trăm nghìn tombstones hoặc row payload quá lớn, truy vấn vẫn chậm; thêm range **giảm phạm vi**, không bảo đảm tombstone bằng 0.

### 5.3. `page-size` cũng không phải thuốc chữa

Java Driver có thể đặt page size 50 thay vì 500. Điều đó giúp giới hạn row count trên mỗi network page (mang tính mục tiêu, không phải byte cap tuyệt đối) và tránh giữ quá nhiều data ở Java, nhưng **nếu replica phải quét 100.000 tombstones trước một live row thì page size=10 vẫn có thể timeout**.

Tương tự, truy vấn `SELECT *` có thể kéo cột `payload` lớn không dùng đến. Nên chọn **cột cần thiết**, giới hạn query và quan sát server-side work.

## 6. Hành vi tạo tombstone trong ứng dụng Java/CQL

### 6.1. `DELETE` và `UPDATE` đặt `null`

~~~sql
-- Xóa một cột của một hàng có đủ primary key:
DELETE payload FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;

-- Xóa cả hàng:
DELETE FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;

-- Một số mapper/driver code có thể gửi null như deletion:
UPDATE telemetry_diag.events_by_device_v1
SET payload = null
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;
~~~

Trong Java Driver, phân biệt **CQL NULL** với **UNSET**: `setToNull(...)` mang semantics deletion, `unset(...)` (khi version/protocol hỗ trợ) cho biết không cập nhật trường đó. Một Spring Data save với entity chỉ load **vài cột** rồi để các field khác `null` có thể vô tình xóa các cells tùy converter/mapping configuration. Phải kiểm tra generated CQL và integration test, **không** suy từ Java object `null` rằng “không thay đổi”.

### 6.2. `DELETE` theo clustering range

~~~sql
-- Ví dụ trên bảng có clustering column event_time đầu tiên:
DELETE FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time < '2026-11-01T00:00:00Z';
~~~

Xóa một khoảng clustering có thể tạo **range tombstone** thay vì vật lý xóa ngay toàn bộ SSTable rows. Nếu mỗi giờ job xóa một range chồng lên các range cũ, replica read cần xét nhiều intervals/deletion markers. Thiết kế retention bằng **bucket + TTL hợp lý** thường tốt hơn quét rồi `DELETE` hàng triệu rows theo lịch, nhưng compaction/repair policy vẫn quyết định khi nào thu hồi an toàn.

### 6.3. TTL mặc định và TTL từng write

~~~sql
-- Minh họa: thời hạn 7 ngày tính từ mutation write, không từ event_time.
INSERT INTO telemetry_diag.events_by_device_v1
  (tenant_id,device_id,event_time,event_id,event_type,payload)
VALUES
  ('tenant-a','device-ttl','2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174002,'HEARTBEAT','ok')
USING TTL 604800;
~~~

TTL hết hạn theo **write-time / server semantics**, không tự xóa file khi `event_time` già hơn bảy ngày. Nếu một late event có timestamp thuộc năm trước nhưng mới được insert hôm nay, TTL bảy ngày thông thường bắt đầu **khi insert**, không phải từ ngày event đã xảy ra. Với dữ liệu time-series nên xác định policy **ingestion-time retention hay event-time retention** thật rõ và kiểm thử replay/backfill.

**Không** thay TTL vô hạn cho mọi bảng để “xóa tombstones”; bỏ TTL có thể làm partition/disk tăng liên tục, còn TTL quá ngắn có thể phá retention/business correctness.

## 7. `gc_grace_seconds`: điều kiện an toàn, không phải nút “dọn ngay”

`gc_grace_seconds` là khoảng thời gian liên quan việc giữ deletion markers để các replicas đã miss delete có cơ hội được đồng bộ. Các chi tiết thu hồi còn phụ thuộc SSTable overlap, compaction strategy, repair trạng thái dữ liệu và phiên bản Cassandra.

### 7.1. Rủi ro zombie data

~~~mermaid
sequenceDiagram
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3 (down)
    R1->>R1: DELETE -> tombstone
    R2->>R2: DELETE -> tombstone
    Note over R3: Giữ live row cũ
    Note over R1,R2: Không repair đủ sớm
    Note over R1,R2: Compaction sau grace có thể thu hồi tombstone
    R3-->>R1: Node cũ trở lại với live row
    Note over R1,R3: Zombie data có thể tái xuất hiện
~~~

### 7.2. Quy tắc vận hành

- Repair toàn bộ phạm vi replicas/table/token cần thiết **đủ thường xuyên so với grace/maintenance window**; ghi nhận **coverage và last successful repair**, không chỉ số lần chạy command.
- Không đặt `gc_grace_seconds=0` trên bảng có RF>1, deletes, replica outages hoặc compliance retention mà chưa có **điều kiện đặc biệt được DBA/SRE xác nhận**.
- Không chạy `nodetool compact`/force compaction với suy nghĩ “ép giải phóng tất cả tombstones” khi replicas chưa repair; có thể thêm I/O và không bảo đảm thu hồi an toàn.
- Không xóa SSTable/commit log/hints hoặc tự sửa timestamp mutation để “dọn dữ liệu bẩn”; có thể làm mất thông tin xóa.
- Khi một node down lâu gần/vượt grace, cần **runbook phục hồi/replace/restore** và reconciliation với nguồn chân lý ngoài cluster, không tự tuyên bố full repair chắc chắn cứu được dữ liệu đã mất deletion history.

### 7.3. Hints và read repair không thay anti-entropy

Hinted handoff giúp một replica vắng mặt nhận một số writes bị bỏ lỡ trong cửa sổ có giới hạn, **best-effort**; read repair chỉ sửa phạm vi các reads nó thực sự tham gia theo version/config. Để giữ đúng semantics tombstone, cần kế hoạch **anti-entropy repair** theo token range/DC/replicas. Nếu một tombstone đã mất ở mọi bản còn có thể làm nguồn, repair không thể tái tạo ý định xóa từ hư không.

## 8. Tombstone warnings và failures thực chất biểu thị gì?

Trong nhiều dòng Cassandra, cấu hình có các tham số như:

~~~yaml
# Đây là sơ đồ minh họa tên tham số theo Cassandra đời phổ biến,
# KHÔNG phải cấu hình cần tự ý áp vào production.
tombstone_warn_threshold: 1000
tombstone_failure_threshold: 100000
~~~

Các giá trị **1.000/100.000 chỉ là ví dụ mặc định phổ biến ở một số phiên bản**, không phải tiêu chuẩn cố định của mọi Cassandra version, vendor distribution, guardrail hay truy vấn. Những threshold này nói đến lượng tombstones được **quét** trong một read theo semantics implementation, **không phải số tombstones đang tồn tại trên một partition**.

### 8.1. Phân biệt warning, failure, timeout

| Hiện tượng | Ý nghĩa có thể có | Cần làm |
| --- | --- | --- |
| Warning “Scanned over ... tombstones” | Một read quét nhiều tombstones, vượt mức cảnh báo cấu hình. | Xác định query/key/range, log/metric và mutation source. |
| Tombstone failure / `TombstoneOverwhelmingException` | Server chặn read vượt mức tombstone scan để bảo vệ tài nguyên. | Xử lý gốc tombstone/query; không đơn giản tăng threshold. |
| `ReadTimeout` / driver timeout | Query quá chậm hoặc replica/queue/network không đáp ứng deadline. | Phân tích load, SSTables/tombstones, CL, GC/disk và coordinator. |
| `Unavailable` | Không đủ replicas phù hợp CL theo phát hiện hiện tại. | Kiểm topology/RF/DC, không quy mặc định cho tombstone. |
| Client memory/GC pressure | `SELECT *`, page/bytes lớn, accumulation ở Java. | Giới hạn projection/page/row count, profile heap và driver. |

**Cảnh báo tombstone và timeout có thể cùng xuất hiện, nhưng không đồng nhất.** Một partition lớn có nhiều live rows cũng có thể làm query chậm mà không có warning tombstone.

### 8.2. Vì sao tăng threshold chỉ che vấn đề?

Nếu nâng `tombstone_failure_threshold` lên rất lớn để read “không còn báo lỗi”, Cassandra có thể tiêu CPU/disk/heap lâu hơn, làm hại hàng xóm cùng replica và tăng p99 toàn cụm. Chỉ cân nhắc điều chỉnh **sau khi** biết query workload, benchmark, resource budget và có approval/rollback; đó không phải biện pháp sửa chính.

## 9. Triage trong 15 phút đầu: bảo vệ SLO và thu chứng cứ

Khi p99 tăng hoặc xuất hiện tombstone failure, ưu tiên **giảm thiểu tác động** và **phân loại nguyên nhân** trước khi đụng tới SSTables.

### 9.1. Bản đồ hành động đầu tiên

~~~mermaid
flowchart TD
    A["Read p99 cao hoặc tombstone warning"] --> B["Xác minh query_name, CL, partition và UTC window"]
    B --> C{"Lỗi phổ biến trên mọi query?"}
    C -->|Có| D["Kiểm node health, GC, disk, pending tasks, compaction, network"]
    C -->|Không, vài partition| E["Đo tombstone scan, partition size, hot keys, query range"]
    D --> F{"Node overloaded / replica down?"}
    F -->|Có| G["Giảm tải ngoài luồng, xử lý availability và capacity"]
    F -->|Không| E
    E --> H{"Tombstone-scanned cao?"}
    H -->|Có| I["Kiểm TTL/DELETE/null writes, SSTables/compaction, repair"]
    H -->|Không| J["Kiểm partition bytes/rows, rộng range, payload, QPS"]
    I --> K["Mitigation bounded + thay đổi schema/retention có kế hoạch"]
    J --> K
    G --> L["Đo lại SLO + consistency + data correctness"]
    K --> L
~~~

**Không phải mọi thứ đều giải được trong 15 phút.** Đây là thứ tự **thu thập dấu vết và bảo vệ cụm**; việc redesign bảng, repair hoặc thay compaction strategy cần kế hoạch riêng và thử trên staging.

### 9.2. Các câu hỏi phải trả lời được

1. **Bắt đầu từ khi nào?** Có deploy Java, backfill, TTL policy, batch DELETE, compaction/repair hay thay RF/CL ngay trước thời điểm p99 tăng không?
2. **Ảnh hưởng bao rộng?** Một `query_name`, một tenant/device/day, một table, một token range hay toàn cluster?
3. **Đường đọc nào?** Query dùng full partition key không, có `ALLOW FILTERING`, `IN`, range quá rộng hay `SELECT *` kéo payload lớn?
4. **Replica nào chậm?** Có node down, disk wait, GC pause, queue/drop hoặc compaction backlog không?
5. **Dấu hiệu tombstone?** Server log có scan warning, JMX histogram có tăng và request nào tương ứng?
6. **Partition size/hotness?** Key cụ thể chứa bao nhiêu rows/bytes; request rate có skew mạnh?
7. **Consistency contract?** Caller có thực sự cần `LOCAL_QUORUM`; có multi-DC/repair lag làm read phức tạp hơn không?
8. **Có thể giảm tải an toàn?** Tắt/giảm batch analytic, rate-limit endpoint phi thiết yếu, thu hẹp time window, chọn projection mà không thay correctness.

### 9.3. Không thu thập theo cách làm tình hình tệ hơn

- Không chạy `SELECT * FROM ks.table`, `COUNT(*)` toàn table hoặc `ALLOW FILTERING` rộng trên production khi hệ đang chậm.
- Không bật `TRACING ON` cho toàn bộ traffic, không liên tục force compaction/flush chỉ để “nhìn trạng thái”.
- Không in raw partition keys, payload, JWT, credentials hoặc CQL literals nhạy cảm vào dashboard/log; dùng query name, sampled hash và phân quyền log.
- Không tăng driver retries vô hạn: một request bị chậm có thể làm nhiều coordinator/replica xử lý trùng, gây **retry amplification**.
- Không tự hạ `LOCAL_QUORUM` xuống `LOCAL_ONE` để làm biểu đồ xanh khi chưa đánh giá nhất quán nghiệp vụ.

## 10. Công cụ quan sát phía Cassandra: lệnh, metric và giới hạn

### 10.1. Lệnh `nodetool` trên node có quyền

~~~bash
# Quan sát trước; không có lệnh xóa dữ liệu ở đây.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_diag.events_by_device_v1
nodetool tablehistograms telemetry_diag events_by_device_v1
~~~

| Công cụ | Trả lời được | **Không** tự trả lời |
| --- | --- | --- |
| `nodetool status` | Node/DC/rack/token membership, `UN`/`DN`. | Key nào quá lớn hoặc tombstone scan của một query; `UN` không chứng minh replicas đã hội tụ. |
| `nodetool info` | Load, uptime, key cache và thông tin node theo version. | Root cause chính xác của read timeout. |
| `nodetool tpstats` | Thread pool pending/completed/dropped tasks. | Điều gì nằm trong SSTable của partition cụ thể. |
| `nodetool compactionstats` | Pending/running compactions, bytes/progress ước tính. | Một tombstone cụ thể đã được purge an toàn hay chưa. |
| `nodetool gcstats` | Số/độ dài GC theo node. | Có tombstone nhiều nếu không có bằng chứng từ table/query. |
| `nodetool proxyhistograms` | Phân phối latency read/write ở node làm coordinator. | Latency end-to-end HTTP/serialization/connection wait. |
| `nodetool tablestats` | Table-local read/write, SSTables, partition estimates, cache/bloom/tombstones tùy version. | Tổng logical rows chính xác hoặc mọi replica có cùng dữ liệu. |
| `nodetool tablehistograms` | Một số histogram về table partition/cell/latency theo version. | Truy vấn nào gây histogram outlier nếu không tương quan log/query. |

**Cần đối chiếu phiên bản:** Cassandra 3.x có thể dùng `cfstats`/`cfhistograms` là tên cũ; Cassandra 4.x/5.x có thay đổi output/flags. Đừng copy tên metric/tùy chọn từ một version sang bản khác mà không kiểm chứng trong lab.

### 10.2. JMX/metrics đáng quan sát

| Metric (tên khái niệm, có thể khác tên exact) | Ý nghĩa khi điều tra |
| --- | --- |
| `TombstoneScannedHistogram` | Phân phối số tombstone được scan qua reads của table, theo cách đo của bản Cassandra. |
| `LiveScannedHistogram` | So số live cells/rows quét với tombstones; không phải exact row count trên disk. |
| `EstimatedPartitionSizeHistogram` | Dữ liệu ước tính về kích thước partition; tìm đuôi phân phối. |
| `MaxPartitionSize` / `MeanPartitionSize` | Dấu hiệu outlier/partition tăng quá nhanh, semantics có thể là per SSTable. |
| Table `ReadLatency`, coordinator `ClientRequest.Read.Latency` | Phân biệt table read path và tổng read request, theo scope metrics. |
| `SSTablesPerReadHistogram` | Read amplification do merge nhiều SSTables. |
| `PendingCompactions`, compaction throughput | Khả năng hệ có xử lý data/retention kịp không. |
| Thread pool `PendingTasks`/`DroppedTasks` | Backlog/overload, không chỉ tombstone. |
| JVM heap/GC/disk await/CPU/RTT | Tài nguyên vật lý làm tăng tail latency. |

Tên MBean thường thuộc các domain kiểu `org.apache.cassandra.metrics` với `type=Table`, `keyspace`, `scope`, `name`; **không tự suy tên exact** từ bảng trên, nhất là Cassandra 5.x và distributions. Lấy danh sách metrics được exporter hỗ trợ, thiết lập dashboard theo **node + DC + keyspace/table + query name** và tránh cardinality theo từng raw partition key.

### 10.3. Đọc histograms đúng cách

- **Histogram là phân phối của các phép đo** trong một khoảng thời gian/scope, không phải luôn là “tombstone hiện có trong bảng”.
- **Cumulative vs per-window:** reset/restart hoặc exporter có thể thay đổi cách hiển thị; đừng so số cộng dồn một node 10 ngày với node vừa restart.
- **p99 trên từng node không cộng/trung bình** để ra p99 toàn cluster. Cần histogram gộp đúng phương pháp/scope.
- **Estimated partition size** dựa trên thống kê on-disk có thể không bằng live logical bytes hoặc kích thước phân vùng lớn nhất sau khi gộp mọi SSTable.
- **p99 cao có thể là bão hòa queue** dù tombstone histogram chỉ tăng nhẹ; đặt histogram cạnh CPU/GC/compaction, offered QPS và timeouts.

### 10.4. Tìm partition/hot key nào gây vấn đề

Phương pháp ít xâm lấn, theo thứ tự:

1. Từ **application tracing/structured logs**, định danh sampled `query_name` và hashed/canonical partition IDs của requests chậm.
2. So distribution của **số event theo thiết bị/bucket** từ application ingestion ledger hoặc nguồn rollup, **không** `COUNT(*)` toàn table.
3. Dùng `nodetool toppartitions` hoặc công cụ node/metrics **nếu version hỗ trợ và được phép**, với duration/top-K phù hợp; nó phản ánh **hoạt động/hotness** trong cửa sổ đo, không phải danh sách chính xác các partition lớn nhất về bytes.
4. Đối chiếu với `tablestats`/`tablehistograms`, sampled query traces và disk/GC.
5. Nếu cần forensic SSTable, dùng `sstablemetadata`/`sstabledump` theo runbook **trên bản sao snapshot/đường offline phù hợp**, không quét/bẻ khóa mọi live SSTable khi sự cố đang diễn ra.

**Bảo mật:** partition keys có thể chứa tenant/device identifiers; lọc/ẩn hoặc hash trong báo cáo, không đưa full values vào hệ telemetry chung nếu không có quyền.

## 11. Query tracing và log: xác định tombstone thuộc query nào

### 11.1. Một câu CQL mẫu có giới hạn

~~~sql
-- Thực hiện trên lab/staging hoặc truy vấn mẫu được phê duyệt.
-- CONSISTENCY/TRACING là lệnh cqlsh, không gửi qua Java Driver.
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_v1
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

Trace có thể chỉ ra coordinator, replicas được hỏi, giai đoạn read/merge và một số số liệu SSTable/tombstone theo version; **không phải mọi thông tin ứng dụng/GC/network đều có trong trace**. Với query ngốn tài nguyên, bật tracing có thêm overhead: chỉ lấy mẫu có chọn lọc và dừng khi đủ chứng cứ.

### 11.2. Cảnh báo và error trong `system.log`

Các dấu hiệu có thể tìm theo query/correlation/time window (tên/error message biến thiên):

~~~text
WARN  ... Read ... live rows and ... tombstone cells ...
WARN  ... Scanned over ... tombstones ...
ERROR ... TombstoneOverwhelmingException ...
ERROR ... ReadTimeoutException / overloaded / dropped messages ...
INFO  ... Compaction ... / Repair ...
~~~

**Đây là các mẫu log khái niệm**, không phải câu chữ tuyệt đối của mọi Cassandra version. Một số warning được server trả qua **protocol warnings** cho Driver 4.x và có thể xuất hiện trong `ExecutionInfo.getWarnings()`. Để liên hệ với Java request, ghi **CQL shape/query name**, timestamp UTC, CL, selected coordinator và warning count, thay vì log raw payload.

### 11.3. Khi query warning đến từ một node khác

Driver có thể chọn nhiều coordinators; coordinator lại chọn replicas theo token/CL. Nếu API request log ở Java nói `coordinator=R1`, read hotspot có thể do replica R2/R3 thực thi storage work. Dùng metrics/logs **các natural replicas của affected key**, không chỉ xem một node mà client đang kết nối.

## 12. Bảng giả thuyết nguyên nhân và phép kiểm chứng

| Giả thuyết | Dấu hiệu | Phép kiểm tra không phá dữ liệu | Hướng xử lý |
| --- | --- | --- | --- |
| TTL tạo tombstones dày trong window. | TTL expiration trùng thời điểm p99 tăng; nhiều tombstones nhưng ít live rows. | CQL `TTL(col)` mẫu trên rows còn sống, retention config, histogram/trace. | Bucket/time-window/compaction policy đúng, không tăng TTL tùy tiện. |
| Batch `DELETE` phạm vi lớn. | Job release và tombstone warning cùng mốc, range tombstones chồng. | Audit/job logs, CQL shape, SSTable/tombstone statistics. | Dừng job ngoài luồng, thiết kế retention theo bucket/TTL phù hợp. |
| Application update null liên tục. | `payload`/field biến mất bất ngờ sau deploy Spring Data. | Driver CQL logs redact, integration test null vs UNSET. | Chỉ update columns cần thiết, dùng UNSET đúng version, sửa mapping. |
| Partition per device không có bucket. | Max partition size lớn, thiết bị lâu năm/chạy nhanh là outlier. | Ingestion rate × row bytes × duration, table metrics, sample bounded query. | V2 theo day/hour/shard, dual-write/backfill/cutover. |
| `SELECT *` lấy payload lớn. | Network/heap/JSON serialization cao; số rows nhỏ. | So query projection hẹp/cùng CL/page, bytes response và JVM profiling. | Hẹp projection, DTO hoặc summary table. |
| Query thiếu clustering range. | `WHERE` full partition key nhưng quét mọi ngày. | Query trace, filters ở HTTP, rows/bytes. | Bắt buộc time range hữu hạn và bucket. |
| `ALLOW FILTERING`/wide token scan. | Nhiều partitions đọc, latency/IO tăng theo volume. | CQL query review, warning, table metrics. | Thiết kế bảng theo query/index phù hợp; bỏ filtering tràn lan. |
| SSTables chồng nhiều, compaction backlog. | SSTablesPerRead, pending compactions và disk await cao. | `tablestats`, `compactionstats`, LSM metrics. | Capacity/throttle/strategy đúng, không ép major compaction mù. |
| Node/replica chậm hoặc thiếu quorum. | `UN`/GC/network, `Unavailable`/timeout rộng nhiều tables. | `nodetool status`, `tpstats`, driver CL/routing, OS metrics. | Khôi phục replica/capacity, repair theo runbook. |
| Repair/tombstone grace không đủ. | Lỗi xóa tái xuất hiện, dữ liệu giữa replicas khác. | Last successful repair coverage, grace, outage/tombstone history. | Chuyên gia DBA/SRE xử lý zombie/restore, không chỉ tăng compaction. |

Không chọn một hàng trong bảng trên rồi sửa ngay. Mỗi giả thuyết cần ít nhất **một tín hiệu trực tiếp** và **một phép đối chứng** (query hẹp, metric, ingestion/compaction timeline hoặc test staging) trước khi ghi kết luận.

## 13. Compaction: vì sao tombstone không tự biến mất đúng ngày hết hạn?

Cassandra ghi dữ liệu theo LSM: mutation vào commit log/memtable, flush thành SSTables bất biến, compaction merge SSTables và xử lý versions/deletion markers theo quy tắc an toàn.

~~~mermaid
flowchart LR
    A["INSERT/UPDATE/DELETE/TTL"] --> B["Commit log + memtable"]
    B --> C["Flush -> SSTable files"]
    C --> D["SSTable nhiều versions/tombstones"]
    D --> E["Compaction theo strategy"]
    E --> F{"Purge an toàn? overlap/grace/repair conditions"}
    F -->|Không| G["Tombstone tiếp tục tồn tại"]
    F -->|Có| H["Một phần obsolete data/tombstone được thu hồi"]
~~~

### 13.1. Tại sao một tombstone qua grace vẫn còn?

- File chứa tombstone có thể **chưa được chọn** để compaction.
- SSTable khác còn dữ liệu/versions bị tombstone che; xóa marker trước sẽ có nguy cơ **resurrect** dữ liệu.
- Compaction strategy, overlap/repair state, TTL expiry của các cells cùng SSTable và guardrails có thể cản hoặc trì hoãn purge.
- Một phần SSTables thuộc repaired/unrepaired state khác nhau, làm yêu cầu an toàn phức tạp hơn.
- Đĩa gần đầy hoặc pending compactions cao khiến công việc thu dọn bị trì hoãn.

**Không có cam kết:** “TTL 30 ngày + grace 10 ngày = dữ liệu vật lý nhất định biến mất ở ngày 40”. TTL là semantic read/retention, không phải hẹn giờ xóa block storage.

### 13.2. So sánh các compaction strategies

| Strategy | Phù hợp điển hình | Tác động tới tombstone/partition | Nguy cơ cần kiểm tra |
| --- | --- | --- | --- |
| **STCS** (Size-Tiered) | Write-heavy, general-purpose workloads. | Merge các SSTables cùng kích thước; tombstone purge tùy overlap và compaction scheduling. | Read amplification/SSTables nhiều, đặc biệt khi TTL/DELETE rải rác. |
| **LCS** (Leveled) | Read-heavy với nhu cầu giới hạn SSTables/read. | Có thể giảm read amplification nhờ level organization. | Write amplification/compaction I/O cao; vẫn không sửa partition key xấu. |
| **TWCS** (Time-Window) | Time-series append mostly in time order, TTL tương đối đồng nhất. | Các SSTables theo cửa sổ thời gian; có thể drop whole expired SSTables khi an toàn và không bị shadowing. | Late/out-of-order writes, replays/deletes/cross-window data có thể cản expired SSTable drop và làm tombstones tồn tại. |
| **UCS** (Unified, khi version hỗ trợ) | Các workload có cân bằng read/write và policy tự tinh chỉnh theo triển khai. | Hành vi khác với STCS/LCS/TWCS; phải benchmark/đọc docs version. | Không tự mặc định bật ở mọi Cassandra 4.x/5.x hoặc xem nó giải quyết mọi tombstone. |

**TWCS không phải nút bật để chữa mọi bảng có TTL.** Nếu có nhiều updates đối với cùng partition/row qua các time windows, hoặc backfill với timestamp khác thời điểm ingest, cần xác minh **write timestamp/compaction window semantics** và nguy cơ SSTables chứa shadowed data. Time-series có update/delete nhiều cần phân tích khác append-only.

### 13.3. Đổi compaction strategy không sửa một bảng sai partition key

Nếu v1 chứa **toàn bộ lịch sử của device** trong một partition hàng chục GiB, chuyển STCS → TWCS có thể thay read/write amplification hoặc TTL cleanup, nhưng **full partition vẫn lớn** và một query không giới hạn time vẫn có vấn đề. Hướng bền vững là **thiết kế bảng theo query với bucket/shard**; compaction là tham số lưu trữ bổ sung, không thay token placement.

### 13.4. Những thao tác không nên phản xạ thực hiện

~~~text
KHÔNG làm ngay trên production khi thấy tombstones:
  - nodetool compact toàn cluster, chạy cùng lúc mọi node
  - nodetool garbagecollect trên mọi tables không xét overlap/repair
  - giảm gc_grace_seconds về 0 để "hết tombstone"
  - sửa tombstone_failure_threshold lên cực lớn để query không lỗi
  - chạy repair full tất cả token ranges đồng thời
  - xóa SSTable/hints/commitlog thủ công
  - ALTER TABLE đổi TWCS mà không benchmark dữ liệu đã tồn tại
~~~

Nếu một công cụ có thể giải phóng dung lượng, vẫn phải đánh giá **data safety, replica repair coverage, disk headroom, I/O budget, phiên bản Cassandra và rollback**. Không chạy các lệnh trên chỉ vì một dashboard báo tombstone histogram cao.

## 14. Thiết kế lại partition: bucket thời gian và truy vấn có giới hạn

Đối với timeline sự kiện, **bucket theo thời gian** là hướng phổ biến để một thiết bị không dồn nhiều năm dữ liệu vào cùng một partition.

### 14.1. Ví dụ V2 partition theo ngày và giờ

~~~sql
-- Mỗi key (tenant_id,device_id,event_day,event_hour) là một partition.
CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_hour_v2 (
    tenant_id text,
    device_id text,
    event_day date,
    event_hour int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
      (tenant_id,device_id,event_day,event_hour),
      event_time,event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

`event_day` và `event_hour` tính từ **`event_time` ở UTC** nếu sản phẩm phân vùng theo event time, không dùng timezone mặc định của pod. Cả producer, Java reader, replay/backfill và repair/reconciliation tooling phải đồng ý cách tính bucket. Nếu product phân theo ingestion time, đó là **mô hình khác**, có thể phù hợp với late events nhưng query theo event time sẽ phải cân nhắc lại.

### 14.2. Ước lượng bucket theo p95/p99 thiết bị, không dùng mức trung bình toàn fleet

Với 25 events/giây, row 600 bytes:

~~~text
Per day  = 25 × 86.400 × 600 ≈ 1.296.000.000 bytes ≈ 1,21 GiB
Per hour = 25 ×  3.600 × 600 ≈    54.000.000 bytes ≈ 51,5 MiB
~~~

Kích thước này là **ước lượng bytes logic ghi**, chưa gồm overhead/SSTable compression, live data overlap, deletions, replication factor hay snapshots. Nếu thiết bị lớn nhất đạt **100 events/giây**, partition một giờ có thể ~206 MiB (với 600B/event). Vì vậy:

1. Đo **phân phối sự kiện/giây theo từng key**, không chỉ mean global.
2. Ước lượng row bytes thực bằng profiling/sample và quan sát disk/SSTable.
3. Chọn bucket day/hour/15-minute theo **partition byte budget và read/query patterns**.
4. Tính tăng trưởng, peaks và late-data/backfill, không mặc định p99 lưu lượng bằng mean.
5. Benchmark p99/GC/disk/compaction với dataset có TTL/deletes giống production.

**Không có một “ngưỡng Cassandra bắt buộc = 50 MiB”.** Trong ví dụ, bucket một giờ giảm đáng kể độ lớn so với một partition nhiều năm; bucket phù hợp cuối cùng phải được chọn từ SLO/capacity và test.

### 14.3. CQL phục vụ một giờ thay vì cả lịch sử

~~~sql
SELECT event_time,event_id,event_type
FROM telemetry_diag.events_by_device_hour_v2
WHERE tenant_id='tenant-a'
  AND device_id='device-7'
  AND event_day='2026-11-21'
  AND event_hour=8
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Query này có **full partition key** và clustering range hữu hạn. Nó giảm phạm vi cần đọc và số bytes nếu dùng projection hẹp, nhưng **không xóa tombstones đã có** trong bảng v1 hoặc tự sửa lịch repair.

### 14.4. Khi một giờ vẫn quá lớn

Với thiết bị cực nóng, thêm **deterministic shard** vào partition key:

~~~sql
-- Ví dụ biến thể mới có thêm shard_id; không ALTER v2 in-place.
PRIMARY KEY (
  (tenant_id,device_id,event_day,event_hour,shard_id),
  event_time,event_id
)
~~~

Chọn shard bằng hàm hash bền trên **event ID hoặc logical key**, ví dụ `shard = stableHash(eventId) mod 8` (hàm phải đồng nhất mọi ngôn ngữ/client). Một writer retry cùng event ID phải chọn **cùng shard**, nếu không tạo duplicate logical event trên nhiều partitions.

**Đánh đổi:** query tất cả events của một giờ phải **fan-out đến tối đa tám shards**, giới hạn concurrency, merge/sort theo `(event_time,event_id)` và áp **global LIMIT**, không tự cho rằng Cassandra có `ORDER BY` xuyên shards. Tăng từ 8 lên 16 shards sau này thay đổi routing; nên version hóa bảng/mapping và migration thay vì đổi modulus trên dữ liệu cũ.

## 15. Query-first redesign: làm rõ người dùng thực sự hỏi gì

### 15.1. Bảng đề xuất theo nhu cầu

| Nhu cầu API | Partition/projection phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| 50 events gần nhất của **một device trong ngày** | `events_by_device_day` với clustering time DESC, bucket day (hoặc hour nếu cần). | Nếu ngày của thiết bị nóng quá lớn, giảm bucket; latest có thể đi qua nhiều giờ. |
| Tìm theo **khoảng một giờ** | `events_by_device_hour_v2` full key + time range. | Late events và timezone UTC. |
| Tất cả events của **site** trong một phút | Bảng/projection theo `site_id,minute` hoặc rollup riêng. | Không quét `N` devices không giới hạn. |
| Count events theo event type/ngày | Pre-aggregated counters/rollup (semantics retry rõ). | Không `COUNT(*)` toàn bảng cho dashboard realtime. |
| Tra event bằng `event_id` | Bảng lookup/projection theo event ID nếu đây là query bắt buộc. | Dual-write/CDC/reconciliation; không dùng `ALLOW FILTERING` trực tiếp. |
| Lọc payload text bất kỳ | Search/analytics engine chuyên biệt hoặc index được kiểm chứng. | Không lấy Cassandra query `ALLOW FILTERING` làm full-text search. |

Với wide-column, **thiết kế bảng theo query** có thể chấp nhận denormalization và nhiều projections. Nhưng “thêm bảng” đồng nghĩa **đồng bộ mutations, TTL, DELETE và backfill**; không tự thành transaction ACID đa bảng.

### 15.2. Chọn bucket theo ổn định kích thước và độ phức tạp đọc

Bucket quá dài → partition lớn, read/compaction/tombstone pressure. Bucket quá ngắn → query phải đọc nhiều partitions để trả timeline, tăng coordinator requests/latency/concurrency. Tìm điểm cân bằng bằng workload:

~~~text
target_partition_bytes =
  (peak_events_per_second_per_key)
  × (bucket_seconds)
  × (observed_bytes_per_event)

estimated_query_partitions =
  ceil(query_window_seconds / bucket_seconds)
  × shard_count
~~~

Công thức là **ước tính có giới hạn**: còn phải tính uneven arrival rate, event-time skew, row variations, SSTable amplification và off-by-one ở UTC bucket boundaries. Khi số partition một query vượt budget, API phải trả validation error hoặc dùng **projection/rollup**, không fan-out vô hạn.

### 15.3. Late events và thay đổi khóa

Nếu event đến muộn nhưng event time thuộc bucket tháng trước, có thể làm SSTable window cũ xuất hiện dữ liệu mới và ảnh hưởng TWCS whole-SSTable expiration. Nếu change event time nghĩa là **đổi clustering key/partition**, Cassandra không sửa primary key in-place; cần **INSERT key mới + DELETE key cũ** và idempotent reconciliation. Đây là nơi phát sinh tombstone/duplicate nếu migration/repair không quản lý.

## 16. Java Driver 4.x: phòng ngừa read quá rộng ngay từ ứng dụng

API không nên nhận `deviceId` rồi tùy ý chạy `SELECT *` toàn lịch sử. Ví dụ sau giới hạn **một giờ UTC, 1–100 rows và projection hẹp**; giả định Spring Boot đã quản lý `CqlSession` sống lâu.

~~~java
// EventWindowReader.java — Java 17, Driver 4.x.
package example.cassandra.troubleshooting;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class EventWindowReader {
    public record EventSummary(Instant at, UUID id, String type) {}

    private final CqlSession session;
    private final PreparedStatement query;

    public EventWindowReader(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT event_time,event_id,event_type " +
            "FROM telemetry_diag.events_by_device_hour_v2 " +
            "WHERE tenant_id=? AND device_id=? " +
            "AND event_day=? AND event_hour=? " +
            "AND event_time>=? AND event_time<? LIMIT ?");
    }

    public List<EventSummary> fetchOneHour(
            String tenantId, String deviceId,
            Instant fromInclusive, Instant untilExclusive, int limit) {

        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("Partition key required");
        }
        if (fromInclusive == null || untilExclusive == null
                || !fromInclusive.isBefore(untilExclusive)) {
            throw new IllegalArgumentException("Invalid time window");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Limit outside [1,100]");
        }

        var utcStart = fromInclusive.atZone(ZoneOffset.UTC);
        LocalDate day = utcStart.toLocalDate();
        int hour = utcStart.getHour();
        Instant nextHour = utcStart.truncatedTo(
                java.time.temporal.ChronoUnit.HOURS)
            .plusHours(1)
            .toInstant();

        if (untilExclusive.isAfter(nextHour)) {
            throw new IllegalArgumentException(
                "Window crosses hour bucket; split with bounded fan-out");
        }

        BoundStatement statement = query.bind(
                tenantId, deviceId, day, hour,
                fromInclusive, untilExclusive, limit)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(limit, 50))
            .setTimeout(Duration.ofSeconds(2));

        ResultSet result = session.execute(statement);
        List<EventSummary> output = new ArrayList<>();
        // CQL LIMIT vẫn là trần logic của statement dù driver fetch nhiều pages.
        for (Row row : result) {
            output.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return output;
    }
}
~~~

### 16.1. Ví dụ bảo vệ gì?

- **Không tạo session theo mỗi request**, chỉ chuẩn bị statement một lần và dùng `CqlSession` được inject/managed.
- Chỉ đọc đúng **một partition theo UTC hour** và time range nằm trong giờ đó; không bỏ qua hour boundary một cách im lặng.
- **Page size <=50** để hạn chế một phần bộ nhớ/network-page (không phải byte cap tuyệt đối); CQL `LIMIT<=100` để giới hạn tổng số rows.
- Chọn **ba cột cần thiết**, không đọc `payload` vài trăm KiB/hàng rồi serialize bỏ.
- Giữ `LOCAL_QUORUM` theo consistency contract ví dụ; timeout 2 giây là **policy minh họa cần đo**, không phải giải pháp tombstone.
- Nếu cần nhiều giờ, phải split thành **bounded buckets**, đặt global limit/merge và query deadlines; không đổi một query thành hàng nghìn requests.

### 16.2. Ví dụ **không** bảo vệ gì?

- Không chặn replica quét nhiều tombstones **bên trong chính bucket giờ**.
- Không thay tenant authorization: service/filter phải xác minh caller được quyền đọc `tenantId/deviceId`, vì Cassandra table RBAC không tự chặn row-level tenant access.
- Không biến result thành snapshot khi có concurrent inserts/deletes/TTL.
- Không xử lý recovery của `ReadTimeout` một cách kỳ diệu; exception phải được phân loại và ghi metric, retry bounded khi thích hợp.
- Không bảo đảm toàn bộ packet/response dưới kích thước byte tối đa; payload về schema, column projection và ingress limits vẫn cần được đo.

### 16.3. Không tăng timeout/CL một cách cảm tính

Thời gian query 2 giây có thể dài gấp nhiều lần p99 target. Tăng lên 20 giây khiến request threads/heap/in-flight tồn tại lâu hơn, tạo queue và load amplification. **Timeout là budget bảo vệ service**, không là cơ chế tối ưu storage. Mỗi lần thay cần đo **offered/achieved rate, p95/p99, in-flight và replica metrics**; không tự hạ `LOCAL_QUORUM` để né chi phí.

## 17. Spring Data Cassandra: sự tiện lợi của repository không thay query design

### 17.1. Derived methods không tạo index kỳ diệu

~~~java
// PHẢN MẪU tư duy: không phải cứ viết method Java này là Cassandra
// có access path efficient để tìm mọi event_type trên mọi partitions.
// List<EventEntity> findByEventType(String eventType);
~~~

Nếu `event_type` là regular column của một bảng partition theo device/time, Cassandra không tự cung cấp truy vấn rẻ theo `event_type` chỉ vì Spring Data có derived query. `ALLOW FILTERING` rộng thường không giải quyết query production.

### 17.2. Entity `null` và partial updates

Trong các đường mapping, một entity đọc thiếu một số cột rồi `repository.save(entity)` có thể tạo mutations không mong muốn tùy version/converter/null mapping, bao gồm xóa cell và tăng tombstones. Thay vì “đọc DTO 3 cột rồi save lại nguyên entity”, dùng:

- Update CQL tường minh **chỉ những cột cần sửa** với full primary key.
- `UNSET` trên bind variables khi thực sự có semantics “không đụng cột này”, kiểm version/protocol.
- Test tích hợp xem generated CQL và tombstone/null behavior đúng Spring Data patch đã pin.
- Nếu cần optimistic locking, gắn **`@Version`/conditional mutation** phù hợp; không lấy raw upsert của mapper để ghi đè khi state đã cũ.

**`@Version` có thể thêm LWT/Paxos cost**, không nên bật nó cho mọi append-only event chỉ để sửa một vấn đề tombstone. Concurrency correctness và tombstone creation là **hai chiều độc lập** của thiết kế.

## 18. Migration V1 → V2: không thể `ALTER PRIMARY KEY` rồi hy vọng hết partition lớn

Thay đổi từ partition `(tenant_id,device_id)` sang `(tenant_id,device_id,event_day,event_hour)` thay **token ownership/replica placement và query routing**. Cassandra không hỗ trợ đổi primary key structure của table hiện có bằng `ALTER TABLE` như một thay cột thường.

### 18.1. State machine chuyển đổi có thể rollback

~~~mermaid
flowchart LR
    A["V1 serving"] --> B["CREATE V2 + capacity"]
    B --> C["Dual-write/CDC giữ future mutations"]
    C --> D["Backfill theo device/time range có checkpoint"]
    D --> E["Catch-up late writes, TTL/deletes"]
    E --> F["Reconcile ID/value/expiry"]
    F --> G["Shadow read + canary V2"]
    G --> H["Cut over read/write có rollback"]
    H --> I["Đủ retention/approval -> retire V1"]
~~~

### 18.2. Các rủi ro làm số tombstone “giảm” nhưng dữ liệu sai

| Vấn đề | Tại sao nguy hiểm | Hướng kiểm chứng |
| --- | --- | --- |
| Backfill copy row hết TTL thành `INSERT` mới không TTL. | Dữ liệu được giữ vô hạn, vi phạm retention/compliance. | Lấy expiry/remaining TTL policy, không reset hạn sống. |
| Copy event `event_time` theo timezone máy. | Ghi nhầm `event_day,event_hour`, query không thấy. | UTC conversion tests quanh midnight/DST nếu có timezone input. |
| Dual-write một bảng thành công, bảng kia timeout. | Data drift v1/v2, có thể mất late events. | Durable CDC/event log, retry idempotent, DLQ/reconciliation. |
| Replay DELETE không theo đúng key ở V2. | V2 có row sống mà v1 đã xóa; compliance risk. | Deletion ledger/CDC, point/row/range delete mapping. |
| UUID mới khi retry/backfill. | Logical duplicate ở V2, counts không khớp. | Stable full primary key, compare ID sets. |
| Cutover khi V2 chưa đủ những bucket truy vấn. | API trả thiếu sự kiện. | Query shadow/canary, coverage windows/late buckets. |
| DROP V1 quá sớm. | Mất khả năng rollback hoặc đối soát nguồn. | Backup/retention, signed approval, clients off V1. |

### 18.3. Không “fix partition size” bằng xoá data thủ công

Một `DELETE` hàng triệu rows của v1 có thể tạo thêm tombstones và không làm partition vật lý nhỏ ngay. Nếu V1 cần được thay thế, dùng **migration/versioned table/cutover**, sau đó retire cũ theo dữ liệu/retention/rollback policy, không xóa tùy tiện ở giai đoạn incident.

## 19. Hot partition và skew: khi phân vùng không quá lớn vẫn gây timeout

Giả sử toàn cluster lưu một triệu partitions, mỗi partition chỉ 5 MiB. Một thiết bị `gateway-master` nhận 40% tất cả reads, còn phần lớn partitions khác hầu như không được truy cập. Token placement có thể khiến những replica sở hữu `gateway-master` phải xử lý nhiều request hơn các nodes khác. **Thêm node** không nhất thiết phân phối tải của **một key không đổi** ra mọi node; RF quy định số replicas tự nhiên cho key ấy.

### 19.1. Skew ảnh hưởng gì?

~~~mermaid
flowchart TD
    A["Fleet có nhiều partition keys"] --> B["Phần lớn keys: QPS thấp"]
    A --> C["gateway-master: QPS rất cao"]
    C --> D["Token placement chỉ chọn RF natural replicas"]
    D --> E["CPU/disk/cache/queue nóng trên những replicas đó"]
    E --> F["Read p99, timeouts, retries tăng"]
    B --> G["Các node khác có thể còn tài nguyên rảnh"]
~~~

**Không có nghĩa mọi request nóng đều do Cassandra:** một cache miss storm, retry storm hoặc sai key trong client có thể tạo hotspot. Kiểm client QPS, coordinator distribution, node token load và partition-specific sampling.

### 19.2. Đo phân phối thay vì chỉ số trung bình

| Quan sát | Diễn giải cần kiểm chứng |
| --- | --- |
| 1% keys tạo 80% read QPS. | Có thể cần cache/precompute/single writer hoặc projection mới. |
| 1% keys chiếm 60% live bytes. | Bucket/shard/capacity theo high-percentile keys. |
| Một số nodes p99 cao, các nodes khác nhàn. | Token/replica set skew hoặc disk/GC issue local. |
| Hot key có ít bytes nhưng latency cao. | Concurrency, cache churn, read/write contention hoặc network/queue. |
| Partition lớn nhưng chỉ đọc last 10 rows. | Độ rộng thực của query, tombstone density và SSTablesPerRead mới quyết định chi phí. |

Đừng tự dùng shard count cực lớn làm mặc định. Nếu endpoint cần đọc toàn bộ dữ liệu của một device, `N` shards có thể khiến query **fan-out N lần**. Cần **latency budget, global limit, bounded concurrency, merge order, pagination và backpressure** trước khi thêm shard.

### 19.3. Khi nào caching hoặc rollup có ích?

- **Latest settings / summary** ít thay đổi: cache với TTL/invalidation rõ, hoặc bảng `latest_event_by_device` riêng.
- **Count/aggregate**: precompute theo site/device/hour; không đọc toàn bộ raw events để vẽ dashboard.
- **Raw event timeline**: query các buckets có giới hạn, phân trang theo clustering key; cache có thể hữu ích nhưng phải quản lý invalidation khi late writes/deletes.
- **Compliance delete**: phải xóa/invalidate cả cache/projections, không để UI “thấy dữ liệu đã xóa” từ Redis/CDN.

Cache chỉ dịch chuyển chi phí; **không giải quyết tombstone safety, repair cadence hoặc phân vùng gốc phình to trên disk**.

## 20. Replication, consistency và repair khi điều tra một read chậm

### 20.1. RF=3 và `LOCAL_QUORUM`

~~~text
Keyspace: NetworkTopologyStrategy {'dc1': 3}
Full natural replicas: R1, R2, R3
Read LOCAL_QUORUM: cần 2 responses từ full replicas trong dc1
Read LOCAL_ONE: chỉ cần 1 response trong dc1
Read ALL: cần cả 3 full replicas
~~~

Nếu R2 chứa nhiều SSTables/tombstones hoặc bị disk GC nặng, một query có thể chậm hơn khi nó tham gia read. Tuy nhiên **`LOCAL_QUORUM` không mặc định “đọc từ hai replica nhanh nhất bất kể correctness”**; read path, replica selection, digest/full-data requests và speculative retry phụ thuộc version/config. Không phỏng đoán coordinator/replica chỉ từ contact point.

### 20.2. Tại sao đổi `LOCAL_QUORUM` sang `LOCAL_ONE` chưa phải sửa?

- Có thể giảm số replica phản hồi cần chờ, nhưng **thay đổi consistency contract**; một replica chưa repair có thể trả dữ liệu stale.
- Tombstone scan của **replica được chọn** vẫn có thể rất lớn, nên `LOCAL_ONE` vẫn timeout.
- Không bảo đảm giảm hot key load: vẫn chỉ có một tập natural replicas, driver có thể chọn cùng node nóng.
- Nếu API dùng `LOCAL_QUORUM` để đáp ứng yêu cầu read-after-write/accuracy, downgrade có thể làm hỏng logic nghiệp vụ.

Giữ CL đã duyệt; nếu đề xuất thay đổi, phải có đánh giá correctness, quorum math, multi-DC và canary/rollback rõ.

### 20.3. Read repair không đồng nghĩa full anti-entropy repair

Một read ở quorum có thể giúp sửa những khác biệt được phát hiện **trong phạm vi đọc**, tùy Cassandra version/table config. Nó không tự quét mọi keys ít truy cập hoặc xác minh rằng replica down đã nhận toàn bộ deletes/TTLs. **Anti-entropy repair** so sánh replica datasets theo token ranges, thường qua Merkle trees/streaming; chạy đúng phạm vi và theo lịch giúp giảm data divergence/lỗi zombie.

### 20.4. Multi-DC làm chẩn đoán khó hơn

Với `dc1:3,dc2:3`, `LOCAL_QUORUM` từ `dc1` chỉ cần **hai full replicas ở dc1**. Nếu remote DC lag, UI chạy ở dc2 có thể quan sát khác biệt; hint delivery/repair/DC-specific settings quan trọng. Một **local-only repair** không mặc định đồng bộ đầy đủ giữa hai DC nếu phạm vi sửa không bao trùm cross-DC differences.

**Đừng** dùng “read đúng ở dc1” để chứng minh tombstones ở dc2 đã an toàn khi một replica remote down quá lâu.

## 21. Giảm tác động ngắn hạn trong incident: ưu tiên những thay đổi có thể rollback

### 21.1. Biện pháp thường ít rủi ro hơn

| Biện pháp | Tại sao có thể giúp | Phải kiểm tra |
| --- | --- | --- |
| Giới hạn time window của endpoint. | Giảm số clustering rows/ranges phải xét. | Không bỏ dữ liệu người dùng yêu cầu; contract pagination. |
| Chỉ chọn columns cần dùng, bỏ `payload` lớn. | Giảm network/deserialize/memory pressure. | Sửa DTO/API có tương thích không; tombstone scan có thể còn. |
| Giới hạn `LIMIT`, page size, bytes, request rate. | Giảm full-response và in-flight footprint. | Page size không bảo đảm giảm tombstone scan nội bộ. |
| Bounded concurrency và admission control. | Ngăn overload/retry amplification ở replicas nóng. | Không drop writes bắt buộc lưu mà không có durable queue/ACK policy. |
| Tạm giảm/suspend batch report và backfill. | Giải phóng disk/CPU/compaction/network. | Có resume/checkpoint và deadline nghiệp vụ. |
| Cache/projection chỉ cho endpoint phù hợp. | Giảm repeated hot reads. | Invalidation, consistency, tenant security và TTL. |
| Chuyển traffic sang schema V2 đã được canary. | Giảm scan của partition v1. | V2 reconciliation/late writes/delete policy đã đạt. |

### 21.2. Hành động cần phê duyệt và đo riêng

- **Tăng instance/node count**: chỉ hữu ích nếu hotspot/replica placement hoặc capacity có thể phân tán, không thay partition key cố định; topology changes sinh streaming/cleanup/repair work.
- **Tăng timeout**: có thể tạm giảm errors nhưng tăng in-flight/wait và che vấn đề; theo dõi p99, queue, achieved rate.
- **Thay compaction strategy**: cần benchmark, có thể gây compaction backlog lớn và đòi disk headroom.
- **Chạy repair**: thiết yếu khi dữ liệu lệch, nhưng không phải thuốc chữa p99 tombstone tức thời; tiêu CPU/disk/network và phải được lập lịch.
- **Thay `gc_grace_seconds` hoặc tombstone thresholds**: có correctness/data-safety implications; không làm phản xạ khi incident.

### 21.3. Stop criteria

Ví dụ xác định trước thử nghiệm:

~~~text
STOP / ROLLBACK IF:
  HTTP errors > approved budget during canary window
  Cassandra read p99 > baseline×2 trong thời gian đã định
  pending tasks/dropped messages liên tục tăng
  disk free xuống thấp hơn mức an toàn
  retry attempts/s vượt global budget
  GC pauses/OOM risk vượt ngưỡng vận hành
  missing ACKed events hoặc unexpected delete/resurrection
~~~

Các ngưỡng ở đây **mang tính phương pháp**, không có một giá trị chuẩn cho mọi deployment. Phải ghi baseline, query traffic, thời gian quan sát và owner/escalation trước khi canary.

## 22. Java service xử lý lỗi: không biến timeouts thành kết quả rỗng

Một phản mẫu:

~~~java
// PHẢN MẪU — code minh họa:
try {
    return reader.fetchOneHour(tenant, device, from, until, 100);
} catch (Exception ignored) {
    return List.of(); // Trả "không có dữ liệu" khi DB timeout.
}
~~~

Nếu Cassandra trả `ReadTimeout`, việc trả danh sách rỗng khiến caller tin không có events; có thể kích hoạt replay/duplicate hoặc làm sai báo cáo. Phân loại:

| Lỗi | Hành vi API thường hợp lý | Ghi chú |
| --- | --- | --- |
| `ReadTimeout` / driver request timeout | Trả lỗi tạm thời (ví dụ 503/504 theo contract), có budget retry nếu an toàn. | Không trả `404` hay `[]` như một read thành công. |
| `Unavailable` | Thông báo dịch vụ/tài nguyên tạm không đủ CL. | Kiểm replica availability, không hạ CL tự động. |
| Tombstone-overwhelming/invalid query | Lỗi query/data shape; cảnh báo ops và bảo vệ endpoint. | Không retry nhanh vô hạn cùng partition/range. |
| Invalid range input | 400/422 theo contract, trước khi gửi CQL. | `from < until`, giới hạn bucket count/page size. |
| `Unauthorized` / tenant mismatch | 403 hoặc 404 theo security policy. | Không thử lại bằng admin role. |
| Mapping/codec/schema drift | 500 hoặc failure mode được quản lý. | Sửa dependency/schema; không quy tombstone mặc định. |

### 22.1. Driver retry policy và speculative execution

Java Driver có thể retry các request được coi là retryable/idempotent theo config, hoặc speculative execute trên nhiều coordinator nếu bật. Điều này **có thể tăng load trên những natural replicas của partition nóng**. Khi root cause là tombstone-heavy read, retry sang coordinator khác không biến tombstones mất đi.

Đặt **global retry budget, deadline, driver throttler/in-flight limits và per-endpoint concurrency**, theo dõi retry attempts/s. Không chỉ đo số HTTP requests; một request có thể tạo nhiều CQL attempts.

### 22.2. Client metric labels không được chứa raw keys

~~~text
metrics labels:
  query_name     = events_recent_by_device_hour
  outcome        = success | read_timeout | unavailable | invalid_range
  local_dc       = dc1
  table          = events_by_device_hour_v2
  api_route      = /events

KHÔNG gắn:
  tenant_id, device_id, event_id, raw CQL literals, API token, payload
~~~

Nếu cần điều tra partition nóng, dùng **sample logs với phân quyền**, hash/pseudonymous ID có chính sách phù hợp, TTL log và truy vết từ incident ticket. Cardinality của partition key có thể làm metrics backend quá tải và lộ thông tin.

## 23. Integration test: tombstone, null/UNSET và read giới hạn

### 23.1. Những test cần Cassandra thật

Unit test mock repository có thể kiểm service reject window quá rộng, nhưng **không thể chứng minh** TTL/delete tạo deletion markers, một query scan nhiều tombstone hay compaction/repair behaves đúng. Dùng Cassandra lab/Testcontainers cho behavior CQL và Java Driver; cluster **một node RF1** không chứng minh RF3/quorum, repair hoặc zombie.

### 23.2. Fixture có tombstones và probe sống

~~~sql
-- Chỉ chạy trong keyspace test cô lập; RF của lab phải phù hợp node count.
CREATE KEYSPACE IF NOT EXISTS diag_test
WITH replication = {'class':'NetworkTopologyStrategy','datacenter1':1};

CREATE TABLE IF NOT EXISTS diag_test.events (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

Test Java có thể:

~~~text
1. Seed một partition key test duy nhất với 1.000 rows.
2. Xóa 900 rows bằng DELETE có full clustering key hoặc cho TTL hết.
3. SELECT window chứa các rows đã xóa + ít live rows, LIMIT 20.
4. Ghi elapsed/ExecutionInfo warnings và compare live row IDs.
5. SELECT một window nhỏ chỉ có live rows để làm đối chứng.
6. Đo metrics/traces theo version (không assert exact tombstone count
   trong mọi build/compaction scheduling).
7. Dọn fixture theo test lifecycle, không TRUNCATE shared test table.
~~~

**Kỳ vọng có thể khẳng định:** sau `DELETE` đã ACK và khi read theo CL phù hợp, các rows bị xóa không còn là kết quả sống; dữ liệu không bị lẫn partition; query window tuân thủ `LIMIT`. **Không nên assert:** tombstone warning chắc chắn xuất hiện sau đúng 900 deletes trên mọi version/compaction moment; cần một test metrics/threshold riêng nếu muốn xác minh guardrail.

### 23.3. Kiểm `NULL` khác `UNSET`

~~~text
Seed row:
  payload="A", event_type="ALERT"

UPDATE chỉ event_type="WARN":
  - path A: SET payload=null (CQL deletion)
  - path B: bind payload UNSET (không cập nhật column, khi hỗ trợ)

SELECT full PK:
  path A: payload không còn giá trị logic
  path B: payload vẫn "A"

Xem generated CQL, mapper behavior, storage version và warning/metrics.
~~~

Đây là lý do **Spring Data partial entity update** cần integration test với đúng dependency graph, không chỉ mock `save()`.

### 23.4. Test giới hạn tại HTTP layer

| Input | Kỳ vọng |
| --- | --- |
| Không có `tenantId/deviceId`. | Reject trước khi tạo statement. |
| `until <= from`. | Reject invalid time range. |
| Query qua hai giờ nhưng service chỉ hỗ trợ một giờ. | Reject hoặc split đúng hai buckets có budget; không mất event qua UTC boundary. |
| `limit=0` hoặc `limit>100`. | Reject hoặc clamp theo contract rõ, không đưa `LIMIT` vô hạn. |
| Client hủy request. | Không fetch vô hạn những pages tiếp theo; resources được thu hồi. |
| Read timeout ở Cassandra. | API trả failure rõ, không `[]` ngụy tạo. |
| Tenant B xin key tenant A. | Authorization deny, không thử query cross-tenant. |
| Row có payload lớn. | Endpoint projection hẹp không deserialize payload, benchmark bytes. |

## 24. Load test: phân biệt tombstone density và partition size

Thay vì chỉ test “1 triệu rows”, hãy chủ động tạo **ma trận hai biến**:

| Dataset | Partition bytes/rows | Tombstone density | Điều muốn quan sát |
| --- | --- | --- | --- |
| **S1** | Nhỏ. | Thấp. | Baseline latency/CPU/network. |
| **S2** | Nhỏ. | Cao. | Tombstone scan riêng, cảnh báo nếu vượt threshold. |
| **S3** | Lớn, nhiều live rows. | Thấp. | Read amplification/broad range, disk/heap/GC. |
| **S4** | Lớn. | Cao. | Tác động cộng hưởng lên p95/p99/timeouts. |
| **S5** | Bucket nhỏ hơn V2. | Retention tương tự S4. | Chứng minh giảm phạm vi read khi chọn key/time. |
| **S6** | Bytes không lớn nhưng QPS tập trung một key. | Thấp hoặc trung bình. | Hot partition/queuing, không nhầm với storage size. |

### 24.1. Giữ workload so sánh được

~~~text
Fixed per experiment:
  Cassandra version/topology/RF/CL
  Java Driver/timeout/page size/retry policy
  Query CQL shape + payload projection
  Read/write ratio, request arrival pattern
  TTL/delete policy, compaction strategy, data age distribution

Record:
  offered RPS, achieved RPS, timed-out/rejected, in-flight
  p50/p95/p99, bytes returned, pages fetched
  tombstones/live scanned histograms, SSTablesPerRead
  CPU/GC/disk await/network, pending compactions
  correct result IDs/values, not just count
~~~

**Closed-loop** load test có thể tự giảm offered requests khi latency tăng và làm outage trông tốt giả. Khi cần phân tích capacity, dùng open-loop rate có **bounded queue/in-flight**, deadline và backpressure; nếu đo histograms, tránh **coordinated omission**. Không biến load generator thành nguyên nhân gây sập cluster test.

### 24.2. Định nghĩa pass/fail trước

Ví dụ, test V2 được coi là cải thiện khi **cùng nghiệp vụ/query correctness** và traffic:

- p95/p99, server scanned tombstones và SSTablesPerRead giảm hoặc đạt target đã thống nhất.
- Không có increase bất thường trong **global CQL requests** do fan-out qua nhiều buckets/shards.
- Heap/GC và disk/network ổn định, compaction backlog không tiếp tục tăng.
- TTL/delete/replay idempotency và event ID sets không sai.
- Read consistency/CL và tenant isolation giữ nguyên; không “tăng performance” bằng đổi correctness contract.

**Không được dùng số benchmark minh họa thay SLA.** Chính workload, retention, RF/DC và SLO của ứng dụng mới quyết định threshold.

## 25. Case study A: TTL dày và range delete khiến trang 20 hàng bị timeout

### 25.1. Bối cảnh giả lập

Một bảng telemetry V1 partition theo `device_id`, TTL 14 ngày. Sau một sự kiện audit, đội ứng dụng chạy job xóa event cũ theo từng khoảng `event_time`; cùng lúc một số clients vẫn replay event thuộc các ngày đã qua. API `GET /devices/{id}/events?limit=20` bắt đầu bị p99 tăng mạnh.

| Thời điểm | Quan sát | Diễn giải cần kiểm chứng |
| --- | --- | --- |
| Ngày 1 | Một thiết bị ghi 20 events/s, partition tăng liên tục. | Không có bucket nên tất cả lịch sử chung một token key. |
| Ngày 15 | Nhiều cells bắt đầu hết TTL. | Deleted/expired data tăng, chưa chắc SSTables được drop. |
| Ngày 16 | Job `DELETE` khoảng thời gian cũ chạy nhiều lượt. | Có thể tạo range tombstones, overlap markers. |
| Ngày 17 | `LIMIT 20` vẫn mất >2 giây ở vài devices. | Có thể phải quét tombstones trước live rows. |
| Incident | Server warning tombstone scan, SSTablesPerRead cao. | Cần đo xác định cùng query/key/time window; không chỉ nhìn warning tổng. |

**Các con số và timeline là giả lập**, không phải số đo production hay kết luận version-independent.

### 25.2. Hướng điều tra

1. Thu `query_name`, full partition key (redacted), CL, selected time window, timeout, p99 và warning từ sample requests.
2. Xem `TombstoneScannedHistogram`, `LiveScannedHistogram`, `SSTablesPerReadHistogram` của table trên các replica liên quan.
3. Đối chiếu lịch **TTL expiration, batch DELETE, mapper null writes, repairs và compaction**.
4. Chạy **bounded query một giờ** và **đối chứng cùng shape trên ngày chưa nhiều deletes** ở staging hoặc sample production được phép.
5. Kiểm TWCS/STCS/LCS và trạng thái SSTables: có late/out-of-order writes khiến expired SSTable không thể drop không?
6. Xác minh **repair cadence và gc grace safety** trước mọi đề xuất purge.

### 25.3. Mitigation và sửa tận gốc

- Tạm giảm **batch DELETE** nếu đang sinh tải, giữ checkpoint/job replay; không dừng luồng deletion bắt buộc compliance mà không có phương án thay.
- Giới hạn API theo **UTC bucket/time window**, chỉ lấy projection cần dùng và giới hạn số requests đang đọc cùng key.
- Thiết kế V2 theo **hour/day bucket phù hợp với p99 ingestion**, retention/TTL nhất quán và query theo partition.
- Đánh giá lại việc dùng **TTL so với range DELETE**: tránh hai cơ chế chồng lên nhau không cần thiết, nhưng vẫn giữ policy xóa đúng nghiệp vụ.
- Nếu TWCS phù hợp append-only, benchmark trên dữ liệu có late writes/deletes thật; không chuyển strategy mù quáng.
- Sau cutover, đối chiếu event IDs, live/deleted state, TTL expiry và repair; không chỉ thấy warning giảm rồi tuyên bố thành công.

**Điều không nên làm:** tăng `tombstone_failure_threshold` để “không báo lỗi nữa”, ép major compaction toàn cluster, hoặc `gc_grace_seconds=0` khi replicas chưa được bảo đảm hội tụ.

## 26. Case study B: phân vùng lớn nhưng ít tombstone; case C: null từ mapper

### 26.1. Case B — hot gateway 30 GiB, time range không giới hạn

Giả sử một gateway tạo 10.000 events/phút, tất cả được ghi trong **một partition per device**. API hiển thị “50 sự kiện gần nhất” nhưng một chức năng export dùng `SELECT * WHERE device_id=?` không có bound, trả toàn bộ payload qua Java.

**Dấu hiệu:**

- `MaxPartitionSize`/sample SSTable partition estimates cao.
- Client bytes/JSON serialization, heap/GC cao; server disk/network cao.
- Tombstone histogram không nhất thiết cao; latency tăng theo **rows/bytes và số pages**.
- Key gateway chịu QPS nhiều hơn các devices bình thường.

**Chẩn đoán phân biệt:** chạy hai phép đối chứng cùng CL, trên dữ liệu/cụm test phù hợp: (a) select projection hẹp với clustering range 1 giờ, (b) select projection đầy đủ với query rộng. Nếu (a) tốt và (b) xấu, điều đó gợi ý **query width/bytes** là nút thắt; cần đo thêm replica SSTables/queue thay vì quy chụp tombstone.

**Sửa:** chuyển bảng per-device sang **hour bucket**, chọn projection hẹp cho timeline, export batch có checkpoint/byte budget hoặc pipeline analytics riêng; nếu một bucket giờ vẫn nóng, xem sharding/caching/rollup. Không giả định thêm 10 Cassandra nodes sẽ chia một partition hiện có ra 10 token locations.

### 26.2. Case C — sau deploy Spring Data, tombstones tăng nhưng TTL không đổi

Một endpoint đọc entity có ít cột, đổi một field rồi `save(entity)`. Phiên bản mapper được nâng và chiến lược `null` thay đổi, làm `payload` liên tục bị đặt `null` khi save. Bảng không có TTL nhưng tombstone scan tăng.

**Dấu hiệu:** tombstone warning bắt đầu trùng deploy; số CQL writes và row deletes không tăng tương ứng; một số field biến mất dù business không yêu cầu xóa.

**Kiểm tra:** review **generated CQL** được redact, phân biệt `UNSET` vs `NULL`, kiểm Spring Data/Driver resolved versions và integration test: seed row A, update field B, assert A vẫn còn.

**Sửa:** dùng statement `UPDATE ... SET fieldB=? WHERE full_key` hoặc mapping update policy đã được xác minh, đảm bảo không xóa cell do partial entity. Cần đối soát/làm sạch dữ liệu bị sửa sai theo nguồn chân lý; chỉ sửa code không tự khôi phục giá trị đã tombstoned.

### 26.3. Vì sao cần tách case study?

| Case | Evidence nổi bật | Cách sửa nền tảng |
| --- | --- | --- |
| A — TTL + DELETE | Tombstone scanned cao, retention/delete overlap. | Policy retention + bucket/compaction/repair. |
| B — partition/hot key | Large partition/bytes/QPS, tombstones có thể thấp. | Schema/query-first design, bucket/shard, bounded export. |
| C — mapping `null` | Sau deploy, deletion markers xuất hiện bất thường. | Generated CQL, mapping/UNSET, test/update semantics. |

Nếu dùng một giải pháp duy nhất “tăng timeout rồi compact”, cả ba trường hợp đều có thể **không được xử lý tận gốc**.

## 27. Runbook sự cố: từ phát hiện đến hậu kiểm

### 27.1. Phase 0 — xác nhận impact và quyền thay đổi

~~~text
Incident ID:
Environment / cluster / DC:
Start UTC:
Affected API / query_name / table:
RF and requested CL:
P95/P99 / throughput / errors vs baseline:
Affected tenant/device scope (redacted):
Recent deployment / TTL/delete/backfill/repair changes:
Incident commander / DB operator / rollback owner:
~~~

Không trực tiếp chạy lệnh maintenance chỉ vì biểu đồ đỏ. Xác định có **node down/multi-DC lag**, backup/repair state và điều kiện bảo vệ dữ liệu trước.

### 27.2. Phase 1 — thu mẫu có kiểm soát

1. Chọn **3–5 sampled slow queries** có `query_name`, CL, time-window, result row count và warning/timeout class.
2. Kiểm logs/metrics trên **các natural replicas** của affected partitions, không chỉ coordinator.
3. Chụp `tablestats`, `tablehistograms`, `compactionstats`, `tpstats`, `gcstats`, disk/CPU/RTT.
4. So trend tombstone scanned vs live scanned, partition bytes/rows/SSTablesPerRead và hot-key QPS.
5. Review TTL, recent DELETE ranges, mapper null writes, schema/query changes, last repair coverage.
6. Phân loại **tombstone-heavy**, **oversized**, **hot-key** hay **overload khác**, có thể đồng thời nhiều nguyên nhân.

### 27.3. Phase 2 — giảm tải an toàn

- Ngừng hoặc throttle các backfills/exports/crawl phi thiết yếu có checkpoint.
- Giới hạn request range và số bucket, trả lỗi validation rõ cho query quá rộng.
- Chuyển endpoint dùng **projection hẹp**, giảm unneeded `payload` và serialized bytes.
- Giới hạn in-flight/retry, có global deadline và rate theo tenant/device khi cần.
- Không thay consistency/retention contract hoặc xóa dữ liệu mà không có approval.
- Nếu một node down, xử lý **availability/recovery** song song, vì tombstones và replica lag là hai yếu tố khác nhau.

### 27.4. Phase 3 — sửa nguồn gốc có thử nghiệm

| Phát hiện | Change đề xuất | Điều kiện trước canary |
| --- | --- | --- |
| Partition per device quá lớn. | V2 theo day/hour + possibly shard. | Schema, dual-write/CDC, TTL/delete replay, reconciliation. |
| Query đọc rộng không cần thiết. | Clustering range + limit + projection. | Test cùng request semantics, regression cho paging/buckets. |
| Mapper tạo `null` deletions. | Update field-specific / UNSET policy. | Test integration null vs UNSET, no silent data loss. |
| TTL/delete overlap + tombstone scan. | Đổi lifecycle/retention/compaction cho append-only. | Test expired SSTable drop, out-of-order writes, repair safety. |
| Compaction/disk backlog. | Capacity/rate/throttling/strategy tuning. | Headroom, version, load test, rollback/observability. |
| Replica stale/outage dài. | Anti-entropy/restore plan. | Token/DC coverage, gc grace, available sources, operator approval. |

### 27.5. Phase 4 — xác minh hồi phục

**Success** cần ít nhất:

1. API p95/p99, achieved throughput, timeout/error/retry và queue/in-flight đạt ngưỡng được duyệt trong cửa sổ traffic đại diện.
2. Tombstone warnings/scan distribution và query bytes/partition ranges **cải thiện theo nguyên nhân đã xác định**, không chỉ “log hết cảnh báo”.
3. Data correctness: expected **event IDs/values/live vs deleted** được đối soát trên representative partitions/buckets.
4. Repair/retention/compaction policy không tạo zombie/expiry sai; resource CPU/GC/disk/compaction không bị chuyển sang rủi ro mới.
5. Client/API tenant isolation, pagination/global ordering/UTC buckets và rollback path còn đúng.

Không báo “cố định hoàn toàn” sau một lần `SELECT LIMIT 20` thành công nếu p99 cùng workload vẫn cao hoặc missing IDs chưa được giải thích.

### 27.6. Phase 5 — hậu kiểm

Ghi rõ:

~~~text
Root cause:     confirmed tombstone / large partition / hotspot / other
Evidence:       query + metric + logs + timeline (redacted)
Immediate fix:  bounded query / rate limit / load isolation / ...
Permanent fix:  schema, retention, compaction, repair cadence, API contract
Correctness:    ID/value + TTL/delete reconciliation
Performance:    p95/p99 before/after at comparable offered load
Rollback:       artifact/schema/feature-flag path + stop criteria
Prevention:     monitors/alerts/tests/deployment checklist
Owner and due:  ...
~~~

## 28. Các phản mẫu nên nhận diện ngay

| Phản mẫu | Hậu quả | Hướng thay thế |
| --- | --- | --- |
| “`LIMIT 20` nghĩa replica đọc đúng 20 physical cells.” | Có thể quét nhiều SSTables/deletion markers trước live row. | Đo tombstones/live scanned, clustering range, bytes và server latency. |
| “Tất cả read timeout đều do tombstones.” | Bỏ qua partition size, hot QPS, GC, disk, network, coordinator. | Phân loại nguồn từ metrics, tracing và workload. |
| “Partition size = tổng kích thước keyspace chia số partitions.” | Mean che đuôi phân phối và skew. | Đo p95/p99/max sizes, ingestion distribution theo keys. |
| “Node thêm mới sẽ chia một partition khổng lồ ra mọi node.” | Một key vẫn hash ra một token và RF replica set. | Thay partition key/bucket/shard; scale-out chỉ hỗ trợ workloads phân bố được. |
| “Chỉ cần đổi STCS thành TWCS là hết mọi tombstone.” | Late writes/deletes/overlap vẫn cản purge; partition key không đổi. | Benchmark đúng workload/retention, redesign theo query. |
| “TTL hết hạn là SSTable biến mất ngay.” | Bỏ qua grace, overlap, compaction và repair. | Hiểu TTL logic và physical cleanup riêng. |
| “Giảm `gc_grace_seconds=0` để hết tombstones.” | Zombie data khi replica miss deletes. | Repair cadence, grace safety và retention plan. |
| “Major compaction sẽ xóa an toàn mọi marker.” | Chi phí I/O lớn; không bảo đảm purge; có thể phá data safety nếu xử lý sai. | Compaction policy có headroom và repair evidence. |
| “Tăng `tombstone_failure_threshold` lên cực lớn là fix.” | Đọc tiếp tục tốn tài nguyên, p99 và cluster blast radius tăng. | Sửa query/TTL/delete/model. |
| “`COUNT(*)` toàn table để tìm large partitions.” | Scan nặng, gây overload ngay lúc incident. | Metrics, ingestion ledger, sampled scoped queries. |
| “`ALLOW FILTERING` để lấy mọi events theo status.” | Wide scans, performance khó dự đoán. | Projection/table theo query, index phù hợp có benchmark. |
| “`SELECT *` rồi lọc payload trong Java.” | Kéo bytes/heap/network không cần. | CQL projection hẹp, DTO, summary table. |
| “Một partition per device cho toàn lịch sử là tự nhiên.” | Thiết bị lâu năm tạo partition khổng lồ. | Day/hour buckets theo measured peaks. |
| “Sharding thành 256 partitions là luôn tốt.” | Fan-out/merge/overhead lớn cho mỗi read. | Shard count dựa trên QPS/bytes và bounded queries. |
| “Thay number of shards bằng modulus mới trực tiếp.” | Old writes/read routing không khớp, duplicate/missing. | V2 schema/versioned migration và stable hashing. |
| “Backfill dữ liệu TTL thành INSERT không TTL.” | Dữ liệu giữ quá hạn, vi phạm retention. | Giữ expiry/remaining TTL semantics. |
| “Xóa lịch sử V1 bằng hàng triệu DELETE để thu hồi disk ngay.” | Sinh thêm tombstone, chưa có physical reclamation ngay. | Migration/cutover rồi retire table an toàn. |
| “Partial entity save với field null là no-op.” | Có thể gửi deletion markers. | Kiểm generated CQL, UNSET và field-specific updates. |
| “`LOCAL_ONE` luôn là cách chữa read timeout.” | Có thể trả stale, tombstone scan vẫn đắt. | Giữ CL contract, sửa root cause. |
| “`LOCAL_QUORUM` chứng minh mọi replica đều hội tụ.” | Replica thứ ba có thể lag. | Repair/hints/replica-specific validation. |
| “Nếu `nodetool status` là `UN` thì tombstones an toàn.” | Membership không chứng minh delete đã propagate. | Repair coverage, gc grace, deletion ledger. |
| “Read timeout = thiết bị không có sự kiện.” | API trả sai dữ liệu rỗng/404. | Phân loại transient failure, retry bounded, preserve correctness. |
| “Retry vô hạn sẽ tự làm query nhanh.” | Amplification lên các replicas nóng. | Deadline, rate/admission limits, query redesign. |
| “Một test mock repository đủ chứng minh không tạo tombstone.” | Không kiểm CQL/storage/TTL thực. | Integration tests trên Cassandra version cụ thể. |
| “Cho biểu đồ p99 đẹp bằng giảm offered load mà không ghi lại.” | Benchmark không công bằng. | Báo offered/achieved/errors/GC và query shape thống nhất. |
| “Làm compaction, repair và schema migration cùng lúc để tiết kiệm thời gian.” | Khó cô lập nguyên nhân, quá tải I/O, rollback khó. | Lập lịch thay đổi từng lớp, canary + validation. |

## 29. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một query `SELECT ... LIMIT 20` chạy 3 giây và server cảnh báo quét 100.000 tombstones. Vì sao `LIMIT 20` không cứu được?

**Đáp án:** `LIMIT` là số **hàng kết quả logic**, không ràng buộc số deletion markers/SSTable versions cần xét để tìm đủ 20 live rows. Phải giảm phạm vi query, xem TTL/delete pattern, compaction và data model.

**Bài 2.** `ReadTimeout` đồng nghĩa luôn có quá nhiều tombstones?

**Đáp án:** **Không.** Node/replica down, disk/GC/queue, network, hot partition, payload lớn hoặc query quá rộng đều có thể timeout. Cần phân loại theo warning, histogram, traces và resource metrics.

**Bài 3.** Sự khác nhau giữa **large partition** và **hot partition**?

**Đáp án:** Large partition liên quan **bytes/rows của một full partition key**; hot partition liên quan **tần suất/concurrency request** tới key. Một key vài MiB có thể rất nóng và một partition lớn có thể ít QPS.

**Bài 4.** Với bảng `PRIMARY KEY ((tenant_id,device_id),event_time,event_id)`, điều gì quyết định token?

**Đáp án:** Toàn bộ **composite partition key `(tenant_id,device_id)`**. `event_time,event_id` chỉ xác định thứ tự/định danh hàng bên trong partition, không tạo token mới.

**Bài 5.** Thiết bị tạo 25 events/s, mỗi event 600 bytes. Một ngày khoảng bao nhiêu bytes logic?

**Đáp án:** `25 × 86.400 × 600 = 1.296.000.000 bytes ≈ 1,21 GiB`. Chưa tính compression, replication và storage overhead.

**Bài 6.** Nếu chuyển sang bucket một giờ, 25 events/s × 600B/event thì bucket một giờ khoảng bao nhiêu?

**Đáp án:** `25 × 3.600 × 600 = 54.000.000 bytes ≈ 51,5 MiB`. Đây chỉ là ước tính; cần đo peaks và p99 partition size.

**Bài 7.** Vì sao một bảng chỉ có 100 partitions có thể gây vấn đề lớn hơn bảng có 1 triệu partitions?

**Đáp án:** Nếu từng partition trong bảng 100 keys chứa rất nhiều rows/bytes hoặc chịu QPS cao, read/compaction/hotspot có thể nặng hơn. **Số lượng partitions toàn bảng** không thay thế phân phối kích thước và hotness **từng key**.

**Bài 8.** `UPDATE ... SET payload = null` có cùng semantics với không gửi `payload` không?

**Đáp án:** **Không mặc định.** `NULL` trong CQL có thể tạo deletion/tombstone, còn `UNSET` khi hỗ trợ biểu thị không cập nhật cột. Phải kiểm cách mapper/driver gửi bind values.

**Bài 9.** Điều gì xảy ra khi job `DELETE` một clustering range rộng?

**Đáp án:** Cassandra có thể ghi **range tombstone** để che các rows trong khoảng; việc xóa logic không đồng nghĩa dữ liệu vật lý lập tức biến mất. Các reads/compactions sau cần xử lý marker đó.

**Bài 10.** Vì sao `gc_grace_seconds` tồn tại?

**Đáp án:** Nó góp phần giữ deletion markers đủ thời gian để các replicas đã miss delete có cơ hội được đồng bộ. Dọn tombstone quá sớm khi replica cũ còn row có thể gây **zombie data**.

**Bài 11.** Có nên đổi `gc_grace_seconds=0` chỉ vì disk gần đầy không?

**Đáp án:** **Không.** Điều đó ảnh hưởng correctness/repair và không bảo đảm thu hồi disk tức thì. Cần xem compaction, overlap, disk headroom, repair cadence và retention policy.

**Bài 12.** Row hết TTL sau 7 ngày có chắc SSTable được xóa vào ngày thứ 7 không?

**Đáp án:** **Không.** TTL làm row/cell hết hạn logic theo semantics viết, còn physical purge phụ thuộc compaction, overlap, grace và state replicas.

**Bài 13.** Event có `event_time` một năm trước nhưng được insert hôm nay với `USING TTL 604800`. TTL tính từ event time hay thời điểm write?

**Đáp án:** Thông thường từ **write-time semantics** của Cassandra, không từ `event_time`. Đây là lý do backfill/late events phải có expiry policy rõ.

**Bài 14.** Vì sao `COUNT(*)` toàn keyspace không thích hợp để điều tra large partition giữa incident?

**Đáp án:** Nó có thể quét rộng, gây tải lên cluster đang khó khăn và không chỉ ra ngay key nào là outlier. Dùng table metrics, ingestion ledger và bounded partition-scope queries.

**Bài 15.** Tác dụng của `TombstoneScannedHistogram`?

**Đáp án:** Nó giúp quan sát **phân phối lượng tombstone quét qua các reads** của table (theo version/instrumentation), không phải tổng số tombstones còn tồn tại trên disk.

**Bài 16.** Nếu `SSTablesPerReadHistogram` và disk await cùng tăng, có thể kết luận chỉ do tombstone không?

**Đáp án:** **Không.** Read amplification do nhiều SSTables/compaction hoặc broad read có thể cao cả khi tombstone ít. Cần đối chiếu live/tombstone scans, query ranges và storage metrics.

**Bài 17.** Khi `nodetool status` cả ba replicas đều `UN`, dữ liệu delete đã hội tụ chắc chưa?

**Đáp án:** **Chưa.** Membership không chứng minh từng tombstone được phát tới mọi replica. Hints best-effort và anti-entropy repair/validation theo token/DC/retention còn quan trọng.

**Bài 18.** Thay `LOCAL_QUORUM` bằng `LOCAL_ONE` có giải quyết tận gốc tombstone-heavy reads không?

**Đáp án:** **Không.** Replica được hỏi vẫn phải xử lý tombstones; consistency contract còn bị thay đổi và có thể đọc state stale. Phải sửa query/retention/storage, không downgrade CL tùy tiện.

**Bài 19.** TWCS thích hợp hơn trong tình huống nào?

**Đáp án:** Nhiều workload **time-series append mostly in order, TTL đồng nhất** có thể được lợi nhờ các time windows và whole-SSTable expiration khi an toàn. Late/out-of-order writes, updates và deletes xuyên windows cần đánh giá vì có thể cản cleanup.

**Bài 20.** STCS và LCS khác nhau về trọng tâm?

**Đáp án:** STCS nhóm SSTables theo kích thước phù hợp write-heavy; LCS tổ chức levels để thường giảm số SSTables phải xét trên reads, đổi lại write/compaction amplification. Không strategy nào tự sửa partition key sai.

**Bài 21.** Nếu `events_by_device_hour_v2` vẫn có partition 2 GiB cho thiết bị cực nóng, nên làm gì?

**Đáp án:** Đo p99 event rate/row bytes; giảm bucket duration hoặc thêm **shard deterministically** với giới hạn số shards/fan-out, rồi test query latency/merge/global limit. Không tăng shard count mù.

**Bài 22.** Hash shard ID từ một UUID mới mỗi lần retry gây vấn đề gì?

**Đáp án:** Cùng logical event có thể vào **khác partition/key** và tạo duplicate. Producer phải giữ ổn định event ID và full primary key qua retries.

**Bài 23.** Vì sao tăng từ 8 lên 16 shard bằng cách đổi `hash(eventId)%N` trực tiếp có thể làm mất dữ liệu khỏi query?

**Đáp án:** Dữ liệu cũ đã được định tuyến theo N=8, nhưng reader mới theo N=16 có thể không đọc đúng partitions cũ. Cần versioned routing/table và backfill/cutover.

**Bài 24.** Một API chỉ cần `event_time,event_type` nhưng đọc cả `payload` 200 KiB/row. Fix đầu tiên?

**Đáp án:** Dùng **column projection hẹp**/DTO, giới hạn số rows/bytes, benchmark cùng CL/query. Nếu server vẫn quét tombstones nặng, cần xử lý riêng storage issue.

**Bài 25.** Sau đổi schema, backfill vô tình INSERT những rows hết TTL thành dữ liệu không TTL. Rủi ro?

**Đáp án:** **Gia hạn retention hoặc giữ vô hạn**, có thể vi phạm compliance. Migration phải bảo tồn expiry/remaining TTL/deletes và có reconciliation.

**Bài 26.** Một ứng dụng catch `ReadTimeout` rồi trả `[]`. Điều gì sai?

**Đáp án:** Lỗi dịch vụ bị biến thành dữ liệu “không có event”, có thể làm sai báo cáo/logic retry. Trả transient failure đúng contract, log/metric và retry bounded khi an toàn.

**Bài 27.** Tại sao retry mù từ 1 request thành 5 CQL attempts có thể làm một hot partition xấu hơn?

**Đáp án:** Các attempts tiếp tục đổ lên cùng natural replicas và quét cùng SSTables/tombstones, khuếch đại CPU/disk/queue. Cần deadline/retry budget, admission và sửa query/model.

**Bài 28.** `nodetool toppartitions` và `MaxPartitionSize` có cùng chức năng?

**Đáp án:** **Không.** `toppartitions` chủ yếu quan sát keys **hot theo hoạt động** trong cửa sổ/version; partition-size metrics ước lượng **bytes/rows trên disk**. Một key hot có thể không lớn.

**Bài 29.** Một test integration xóa 900/1.000 rows rồi assert warning threshold chắc chắn xuất hiện. Có đáng tin không?

**Đáp án:** **Không phải assertion portable**. Warning phụ thuộc query shape, threshold, live/tombstone cells scanned, compaction và version. Assert logical deletes đúng, đo warning/histograms trong test hiệu năng có config cố định riêng.

**Bài 30.** Khi p99 giảm sau khi tăng timeout, root cause đã được xử lý chưa?

**Đáp án:** **Chưa thể kết luận.** Timeout tăng chỉ cho request thời gian lâu hơn; load/in-flight có thể tăng, correctness và tombstone scan vẫn như cũ. Phải đo p99 thực, throughput, bytes, server scans, errors và node resource ở cùng offered load.

## 30. Checklist chẩn đoán và triển khai an toàn

~~~text
TRIAGE / SCOPE
[ ] Phân biệt tombstone-heavy, large partition, hot partition và global overload.
[ ] Ghi query_name, CQL shape, CL, RF/DC, UTC window, LIMIT/page size.
[ ] Phân loại ReadTimeout, Unavailable, tombstone failure, driver timeout.
[ ] Chụp offered vs achieved QPS, p95/p99, retries, queue/in-flight.
[ ] Có incident marker UTC và deployment/delete/TTL/repair timeline.

DATA MODEL / QUERY
[ ] Full partition key được cung cấp; không quét rộng/ALLOW FILTERING mù.
[ ] Clustering range và CQL LIMIT phù hợp contract của endpoint.
[ ] SELECT projection hẹp, không deserialize payload không cần.
[ ] P95/p99 partition bytes/rows và per-key event rate được đo.
[ ] Bucket day/hour/minute dựa trên peaks và row bytes thực, không mean global.
[ ] Shards có stable hash/routing, bounded fan-out và global ordering.
[ ] UTC boundaries, late events và identical timestamps có integration tests.

TOMBSTONE / RETENTION
[ ] TTL (default/write), DELETE row/range/partition và null writes đã audit.
[ ] Phân biệt CQL NULL vs UNSET trong mapper/Driver.
[ ] TombstoneScannedHistogram/LiveScannedHistogram được đối chiếu logs.
[ ] SSTablesPerRead, pending compactions, disk await và GC được theo dõi.
[ ] gc_grace_seconds và last successful repair coverage đáp ứng safety policy.
[ ] Không hạ grace về 0, xóa SSTable/hints, truncatehints hoặc ép compaction mù.
[ ] Compaction strategy phù hợp append/out-of-order/TTL/UPDATE/DELETE patterns.
[ ] Nếu đổi strategy, có capacity/headroom/canary/rollback rõ.

JAVA / HTTP
[ ] Managed CqlSession + prepared CQL, không tạo session mỗi request.
[ ] Server-side LIMIT và client page size khác nhau, có byte/row budgets.
[ ] CQL request deadline, bounded in-flight/retry/backpressure.
[ ] Timeout không bị chuyển thành empty list/404.
[ ] Tất cả endpoints kiểm tra tenant/device authorization.
[ ] Không log raw payload/partition IDs vào metrics high cardinality.
[ ] Spring Data generated CQL được test, null không vô tình xóa cột.

MIGRATION / CORRECTNESS
[ ] V2 CREATE riêng; không ALTER partition key in-place.
[ ] Dual-write/CDC có durable catch-up, stable full keys và retry idempotent.
[ ] Backfill giữ TTL expiry, DELETE, timestamps/generation phù hợp.
[ ] Reconcile event IDs, live/deleted state và values, không chỉ COUNT.
[ ] Shadow read/canary, SLO stop criteria, rollback artifact/schema.
[ ] V1 chỉ retire sau retention, backup, approval và mọi clients đã chuyển.

VALIDATION / OPERATIONS
[ ] Test shape S1..S6: nhỏ/lớn × ít/nhiều tombstones + hot QPS.
[ ] Multi-node RF3/LOCAL_QUORUM và anti-entropy được test riêng nếu cần.
[ ] Không thay CL/timeout/page/projection giữa A/B benchmark mà không ghi.
[ ] Server metrics và client p99 cải thiện dưới offered load tương đương.
[ ] Correctness, pagination, TTL/delete/tenant isolation còn đúng sau fix.
[ ] Có incident report, ownership, repair schedule, monitoring alerts.
~~~

## 31. Sơ đồ quyết định dùng trong trực sự cố

~~~mermaid
flowchart TD
    A["Read timeout/p99 cao"] --> B["Tìm request/query/table/CL, UTC time window"]
    B --> C{"Nhiều tables/keys cùng chậm?"}
    C -->|Có| D["Check replica availability, GC, disk, queue, repair/compaction"]
    D --> E{"Node/cluster overload?"}
    E -->|Có| F["Reduce noncritical load, repair availability/capacity safely"]
    E -->|Không| G["Inspect narrow sample, table metrics và query shape"]
    C -->|Không| G
    G --> H{"Tombstone-scanned high?"}
    H -->|Có| I["Check TTL, DELETE range, NULL mapper, gc grace, SSTables"]
    H -->|Không| J{"Partition bytes/rows hoặc per-key QPS cao?"}
    J -->|Có| K["Reduce range/projection; bucket/shard/rollup design"]
    J -->|Không| L["Inspect network/driver/JSON, filters, cache, compaction"]
    I --> M["Mitigation bounded + retention/compaction/repair plan"]
    K --> M
    L --> M
    F --> N["Verify p99, QPS, errors, ID/value correctness"]
    M --> N
    N --> O{"Target đạt trên traffic đại diện?"}
    O -->|Không| P["Rollback/escalate, test next hypothesis"]
    P --> G
    O -->|Có| Q["Canary rollout, add alerts and postmortem"]
~~~

### 31.1. Mẫu ghi kết luận có thể kiểm chứng

~~~text
Đã xác định:
  query_name=events_recent_by_device
  nguyên nhân chính=TTL + range tombstones trong partition theo device
  bằng chứng=server warning + tombstone histogram + CQL trace + delete job UTC

Biện pháp:
  ngay lập tức=giới hạn UTC time window, giảm batch deletion, bounded in-flight
  lâu dài=V2 hour bucket + projection hẹp, TTL/repair policy được kiểm thử

Không thay:
  LOCAL_QUORUM / tenant authorization / business retention policy

Đã xác minh:
  client p99 và timeout dưới workload tương đương
  expected IDs/values/TTL/deletes đúng trên sampled partitions/buckets
  compaction/disk/GC/backlog trong giới hạn, repair coverage được ghi

Còn rủi ro:
  partitions cũ v1 / late writes / backup restore / cross-DC ...
~~~

Không viết một kết luận chung chung “Cassandra có nhiều tombstones nên đã force compact và ổn” khi chưa nêu **query nào, giới hạn của phép kiểm, correctness nào được bảo vệ, hậu quả trên replica/storage và ai chịu trách nhiệm theo dõi**.

## 32. Nguồn tham khảo và tổng kết

Các thông số cấu hình và API cần được đối chiếu với **đúng phiên bản Cassandra/Java Driver/Spring Data** đã pin:

1. [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/): tổng quan kiến trúc, read/write path, storage engine, replication và cấu hình theo phiên bản.
2. [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, TTL, CQL conditions, `LIMIT`.
3. [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): chiến lược STCS/LCS/TWCS/UCS tùy version, SSTable expiration, tombstone handling.
4. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy repair, Merkle trees, token range scope, full/incremental repair và tombstone safety.
5. [Apache Cassandra — Nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): node/table statistics, compaction/task health và cú pháp tools thực tế.
6. [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/): prepared/bound statements, bind parameters và reuse.
7. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): page size, full traversal và giới hạn phân trang native.
8. [Spring Data Cassandra — Mapping/Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): mapping, persistence/partial updates theo Spring Data release line.

**Tổng kết:** tombstone-heavy read và large/hot partition đều có thể làm Cassandra **read p99 cao, timeout hoặc GC/disk/network tăng**, nhưng chúng cần **bằng chứng và cách sửa khác nhau**. Tombstones hình thành qua `DELETE`, `NULL`, TTL và range deletions; chúng phải sống đủ lâu để bảo vệ consistency khi replica chưa bắt kịp, nên **`gc_grace_seconds`, compaction và anti-entropy repair** không phải nút dọn đĩa tùy tiện. Partition lớn bắt nguồn từ **partition key/bucket/workload**; một `LIMIT` nhỏ hay compaction strategy không sửa được model lưu cả nhiều năm vào một token key. Khi xử lý sự cố, hãy bắt đầu từ **query shape + CL + metrics/log/tracing + phân phối partition/QPS**, giảm tải an toàn, rồi thiết kế **bucket/shard/projection** theo truy vấn thực và migration có TTL/delete/reconciliation. Chỉ xác nhận đã xử lý xong khi **p95/p99, achieved throughput, tombstone/partition scans, resource pressure và correctness của IDs/values/retention** đều đạt trên workload đại diện — không phải chỉ vì warning đã biến mất.
