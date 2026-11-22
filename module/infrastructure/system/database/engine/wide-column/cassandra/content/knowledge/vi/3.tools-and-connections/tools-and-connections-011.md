# system_schema, system_views và metadata phục vụ thực hành

## 1. Vì sao cần đọc metadata trước khi chạy CQL?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**: dữ liệu được phân vùng bằng **partition key**, sắp xếp trong partition bằng **clustering columns**, sao chép theo replication strategy của keyspace và đọc/ghi theo consistency level (CL). Trước khi tối ưu truy vấn, kiểm tra lỗi timeout, mở rộng cluster hoặc kết nối Java Driver, người thực hành cần biết **schema nào đang tồn tại** và **node nào đang cung cấp thông tin vận hành**.

Trong chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài học này sử dụng ba nguồn thông tin:

1. **`system_schema`**: metadata về định nghĩa keyspace, bảng, cột, index, kiểu dữ liệu và các đối tượng CQL liên quan.
2. **`system_views`**: nhóm **virtual tables** để xem thông tin đang chạy và metrics **của node nhận truy vấn**.
3. **`system.local`, `system.peers_v2` và Java Driver metadata**: thông tin node/topology và cách ứng dụng khám phá schema để định tuyến request.

Các nhóm này bổ sung cho nhau nhưng không thể thay thế tùy ý. Đọc được schema không chứng minh các replica đều khỏe; đọc một virtual table không tự cho biết số liệu tổng của toàn cluster.

**Sau bài này, bạn có thể:**

- Tra cứu replication của keyspace, các bảng, primary key và clustering order từ metadata CQL.
- Phân biệt **`system_schema.views`** (định nghĩa *materialized views*, nếu có) với **`system_views`** (keyspace các *virtual tables*).
- Xem kết nối native/TLS, cấu hình node, thread pool, disk usage và công việc SSTable bằng các virtual table phù hợp.
- Hiểu tại sao virtual table là **node-local**, chỉ đọc và không dùng để sửa cấu hình Cassandra.
- Đối chiếu metadata CQL với `DESCRIBE`, `nodetool`, metrics và Java Driver 4.x.
- Chẩn đoán lệch schema, sai keyspace/partition key, driver discovery và lỗi đọc/ghi mà không sửa bảng hệ thống bằng tay.

## 2. Bản đồ các keyspace hệ thống

| Keyspace/bảng | Thông tin cung cấp | Tính chất cần nhớ |
| --- | --- | --- |
| `system_schema.keyspaces` | Tên keyspace, replication strategy/replica theo DC, durable writes | Metadata schema; đọc để xác minh định nghĩa hiện tại. |
| `system_schema.tables` | Tên bảng và các tùy chọn như compaction, compression, TTL mặc định | Không cung cấp số row hay toàn bộ tình trạng storage thực tế. |
| `system_schema.columns` | Tên cột, kiểu dữ liệu, kind, position, clustering order | Phù hợp để phân tích partition/clustering key. |
| `system_schema.indexes` | Metadata secondary index (nếu có) | Không đồng nghĩa mọi kiểu index có cùng chi phí truy vấn. |
| `system_schema.types` | Định nghĩa user-defined types | Chỉ có row nếu schema tạo type. |
| `system_schema.views` | Định nghĩa **materialized view** của bảng | **Không phải** virtual keyspace `system_views`. |
| `system_views.*` | Metrics/trạng thái nội bộ qua virtual tables | **Node-local, không replicate và thường read-only**. |
| `system_virtual_schema.*` | Metadata về các virtual keyspace/table/column | Dùng để hiểu virtual schema; chủ yếu phục vụ nội bộ, không phải bảng ứng dụng. |
| `system.local` | Metadata của node cục bộ, ví dụ data center, version, schema version | Một hàng đại diện node đang phục vụ truy vấn. |
| `system.peers_v2` | Metadata peer được node biết (Cassandra hiện đại) | Có thể khác khi topology/gossip đang thay đổi; bản cũ có `system.peers`. |

**Quy tắc an toàn:** những bảng hệ thống là nguồn để **quan sát**, không phải nơi người học thực hiện `INSERT`/`UPDATE`/`DELETE` nhằm “sửa metadata”. Quản lý schema bằng CQL DDL có thẩm quyền (`CREATE`, `ALTER`, `DROP`), quản lý cluster bằng quy trình `nodetool` và công cụ vận hành theo phiên bản.

### 2.1. Điểm khác biệt quan trọng

~~~mermaid
flowchart LR
    DDL["CREATE/ALTER KEYSPACE, TABLE"] --> META["system_schema<br/>định nghĩa schema"]
    META --> APP["Driver metadata<br/>Keyspace/Table/Column"]
    RUNTIME["Node đang chạy"] --> VIRTUAL["system_views<br/>virtual tables node-local"]
    RUNTIME --> LOCAL["system.local / peers_v2<br/>metadata node/topology"]
    APP -->|"CQL request"| RUNTIME
~~~

Sơ đồ chỉ mô tả mối liên hệ khái niệm. Driver nhận schema metadata qua cơ chế riêng và làm mới theo event/chính sách của driver; không nên nghĩ rằng ứng dụng phải tự `SELECT system_schema` cho mỗi request. Trong quá trình đồng bộ schema giữa các node, thông tin có thể **chưa hội tụ tức thời**.

## 3. Chuẩn bị lab: schema phục vụ truy vấn cảm biến

Ví dụ chạy trên Cassandra đơn node có `cqlsh`, đủ quyền tạo schema. **RF = 1 chỉ dành cho lab**, không đại diện cho kiến trúc chịu lỗi production.

Từ terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS metadata_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS metadata_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0;

INSERT INTO metadata_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO metadata_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.4);
~~~

Thiết kế phục vụ truy vấn **“các sự kiện của một thiết bị trong một ngày, mới nhất trước”**. Composite partition key là `(device_id, event_day)`; `event_time` và `event_id` là clustering columns. Bảng chưa có secondary index hay materialized view; vì thế metadata tương ứng có thể không có hàng nào.

Kiểm tra dữ liệu bằng câu CQL phù hợp với schema:

~~~sql
SELECT event_time, event_type, value
FROM metadata_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Nếu lab chưa chứa dữ liệu trước đó, dự kiến có hai row, mốc `01:05` trước `01:00`. Các UUID cố định giúp chạy lại lab theo cùng primary key; `INSERT` với key trùng là upsert, không tạo thêm row. Nếu bảng đã tồn tại nhưng schema khác, `IF NOT EXISTS` **không tự chỉnh lại schema**; cần đọc định nghĩa trước khi chạy tiếp.

## 4. system_schema: đọc định nghĩa keyspace và bảng

### 4.1. Tìm đúng keyspace và replication

~~~sql
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE metadata_lab;

SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'metadata_lab';
~~~

`replication` là map chứa tên strategy và replica configuration. Với lab, bạn sẽ thấy `SimpleStrategy`/`replication_factor = 1`. Trên production đa datacenter, thường dùng `NetworkTopologyStrategy` và replication factor **theo từng datacenter**; phải đọc **tên DC thực** trước khi diễn giải `LOCAL_QUORUM`.

**Không nhầm:**

- **RF** trong `replication`: mỗi partition có bao nhiêu replica theo topology.
- **CL** của một request: cần bao nhiêu replica phản hồi để đọc/ghi thành công.
- **Seed nodes**: điểm gossip discovery của node mới, không quyết định số replica và không xuất hiện như một cột “seed” trong bảng replication.

Ví dụ giả định một DC RF = 3: `LOCAL_QUORUM` cần 2 replica trong DC đó phản hồi. Với RF = 1 của lab, `LOCAL_QUORUM` trong một DC cũng chỉ cần 1 replica; metadata không chứng minh cluster đã có hai hoặc ba node.

### 4.2. Liệt kê bảng và các lựa chọn lưu trữ

~~~sql
DESCRIBE TABLES;
DESCRIBE TABLE metadata_lab.events_by_device_day;

SELECT keyspace_name, table_name, compaction, compression,
       default_time_to_live
FROM system_schema.tables
WHERE keyspace_name = 'metadata_lab';
~~~

Ở đây `DESCRIBE TABLE` của **cqlsh** thường là cách dễ nhất để xem lại câu `CREATE TABLE` có thể đọc được. `system_schema.tables` phù hợp khi cần lọc/lập danh sách metadata theo nhiều bảng.

Ý nghĩa của một số cột:

| Thuộc tính schema | Mô tả | Điều không thể suy ra |
| --- | --- | --- |
| `compaction` | Strategy và tham số compaction cấu hình cho bảng | Không cho biết compaction đang chạy hay backlog hiện tại. |
| `compression` | Thuật toán và lựa chọn nén SSTable | Không phải chỉ số disk usage thực tế. |
| `default_time_to_live` | TTL mặc định cho các ghi vào bảng nếu khác 0 | Không hiển thị TTL còn lại của từng cell. |
| `gc_grace_seconds` | Tham số liên quan tombstone/garbage collection | Không chứng minh repair đã được thực hiện đúng lịch. |
| `caching` | Cấu hình cache của bảng | Không phải cache hit ratio hiện tại. |

Đây là **metadata định nghĩa**, không phải metric thay đổi liên tục. Nếu cần xem compaction task hoặc disk usage thực tế, hãy dùng virtual tables/`nodetool`/metrics ở phần sau.

### 4.3. Phân tích partition key và clustering columns bằng columns

~~~sql
SELECT column_name, kind, position, type, clustering_order
FROM system_schema.columns
WHERE keyspace_name = 'metadata_lab'
  AND table_name = 'events_by_device_day';
~~~

Các cột đáng quan sát:

| `column_name` | `kind` dự kiến | Vai trò |
| --- | --- | --- |
| `device_id` | `partition_key` | Thành phần đầu tiên của composite partition key. |
| `event_day` | `partition_key` | Thành phần thứ hai của partition key (bucket ngày). |
| `event_time` | `clustering` | Clustering column đầu tiên, sắp giảm dần. |
| `event_id` | `clustering` | Clustering column thứ hai, sắp tăng dần. |
| `event_type`, `value` | `regular` | Các trường dữ liệu không thuộc khóa chính. |

`position` ghi vị trí thành phần khóa trong nhóm khóa tương ứng; đừng chỉ dựa vào **thứ tự các hàng của kết quả SELECT** để xác định thứ tự composite partition/clustering key. Dùng `kind` + `position`, `clustering_order` và so với `DESCRIBE TABLE`.

**Bẫy điển hình:** metadata cho thấy `event_time` là clustering, **không phải partition key độc lập**. Truy vấn:

~~~sql
-- Không phù hợp với primary key của bảng lab nếu thiếu partition key.
SELECT event_time, value
FROM metadata_lab.events_by_device_day
WHERE event_time > '2026-11-21T01:00:00Z';
~~~

có thể bị từ chối do hạn chế lọc/định tuyến, dù CQL đúng cú pháp. Việc sửa đúng là bổ sung **đầy đủ partition key** hoặc thiết kế thêm bảng theo mẫu truy vấn khác, không mặc định dùng `ALLOW FILTERING` để quét rộng.

### 4.4. Tìm indexes, types, functions, aggregates và materialized views

~~~sql
-- Có thể trả về 0 hàng trong lab chưa tạo index/view/UDT.
SELECT keyspace_name, table_name, index_name, kind
FROM system_schema.indexes
WHERE keyspace_name = 'metadata_lab';

SELECT keyspace_name, type_name, field_names, field_types
FROM system_schema.types
WHERE keyspace_name = 'metadata_lab';

-- Metadata của materialized views (không phải virtual tables).
SELECT keyspace_name, view_name, base_table_name
FROM system_schema.views
WHERE keyspace_name = 'metadata_lab';
~~~

`system_schema.functions` và `system_schema.aggregates` lưu metadata của các user-defined functions/aggregates nếu phiên bản/cấu hình hỗ trợ và đối tượng được tạo. Đừng suy ra “không có hỗ trợ” chỉ vì bảng metadata trống trong một keyspace mới.

**Cực kỳ quan trọng:**

| Tên | Ý nghĩa |
| --- | --- |
| **`system_schema.views`** | Bảng metadata ghi định nghĩa **materialized views** được tạo trên các bảng dữ liệu. |
| **`system_views`** | **Keyspace virtual tables** để đọc metrics/cấu hình/trạng thái của **node cục bộ**. |

Sự giống nhau của chữ “views” là trùng tên khái niệm, **không phải cùng loại đối tượng**.

## 5. system_views: virtual tables node-local

Virtual tables được Apache Cassandra giới thiệu từ dòng **4.0**. Thay vì lưu nội dung thành SSTable như bảng thông thường, virtual table cung cấp **giao diện CQL đọc dữ liệu do node tạo ra lúc truy vấn**: thông tin client, cấu hình, thread pool, SSTable task, một số chỉ số latency/disk.

Theo tài liệu Cassandra về virtual tables:

- Các virtual tables ở `system_views` là **cục bộ cho node**, không được phân tán/replicate giống bảng ứng dụng.
- Chúng **không có SSTable tương ứng** và không phải đích sao lưu dữ liệu ứng dụng.
- Với các virtual tables hiện hành, **không dùng DML để cập nhật metric/cấu hình**; `INSERT`, `UPDATE`, `DELETE`/`TRUNCATE` hay DDL trên virtual table không phải API quản trị.
- **Consistency level cho SELECT trên virtual table bị bỏ qua**, vì không có yêu cầu đọc nhiều replica như một bảng replicated.
- Danh sách bảng/cột **thay đổi theo phiên bản Cassandra**; một ví dụ trong tài liệu 5.x có thể không áp dụng nguyên vẹn cho cluster 4.0/4.1.

Để khám phá những gì cluster đang chạy hỗ trợ:

~~~sql
DESCRIBE KEYSPACE system_views;
DESCRIBE TABLES;
DESCRIBE TABLE system_views.clients;
DESCRIBE TABLE system_views.settings;
~~~

`DESCRIBE TABLES` không chỉ liệt kê riêng keyspace `system_views` nếu bạn chưa chọn ngữ cảnh `USE system_views`. Để tránh nhầm:

~~~sql
USE system_views;
DESCRIBE TABLES;

-- Quay về keyspace lab để tiếp tục truy vấn dữ liệu.
USE metadata_lab;
~~~

Lệnh `DESCRIBE` có thể in cấu trúc “VIRTUAL TABLE ...” chỉ mang tính tham khảo; **đừng sao chép DDL đó rồi kỳ vọng tự tạo được virtual table**.

### 5.1. system_virtual_schema là gì?

Trong dòng Cassandra có virtual tables, keyspace **`system_virtual_schema`** mô tả virtual keyspaces, virtual tables và columns (ví dụ `keyspaces`, `tables`, `columns`). Đây là metadata phục vụ cơ chế virtual schema, **không phải nơi người dùng thêm cột hệ thống**.

~~~sql
-- Kiểm tra sự tồn tại và định nghĩa, không sửa schema ảo.
DESCRIBE KEYSPACE system_virtual_schema;
DESCRIBE TABLE system_virtual_schema.tables;
~~~

Đây là nguồn metadata nội bộ; khi cần quan sát danh sách virtual table thực tế, thường nên dùng `DESCRIBE KEYSPACE system_views` hoặc `DESCRIBE TABLES` trong ngữ cảnh phù hợp. Không viết ứng dụng phụ thuộc cứng vào mọi cột/tên virtual table như một API ổn định giữa các bản major.

### 5.2. system_views.clients: ai đang kết nối vào node?

~~~sql
DESCRIBE TABLE system_views.clients;

SELECT address, port, driver_name, driver_version,
       protocol_version, ssl_enabled
FROM system_views.clients
LIMIT 20;
~~~

Bảng này thường hiển thị **các native connections của node đang nhận câu SELECT**. Một số phiên bản còn có `username`, `request_count`, `ssl_protocol`, `connection_stage` và các metadata client khác. Những cột sẵn có phụ thuộc phiên bản: nếu `DESCRIBE TABLE` không có cột nào đó, điều chỉnh `SELECT` trước khi chạy.

Các câu hỏi có thể trả lời:

1. Client đang kết nối bằng driver nào và native protocol version nào?
2. Những kết nối đang quan sát có bật TLS không?
3. Có kết nối nào chưa ở giai đoạn sẵn sàng (`connection_stage`) hoặc có số request tăng bất thường?
4. Trong đợt nâng cấp driver/TLS, còn client cũ hoặc plaintext connection nào đang kết nối node này không?

**Đừng diễn giải `0 rows` thành “không ứng dụng nào đang kết nối toàn cluster”.** Có thể bạn đang truy vấn một node không nhận các kết nối ấy, hoặc quyền/phiên bản/điều kiện thời điểm khiến kết quả khác dự kiến. Trên cluster nhiều node, quan sát từng node phù hợp và tổng hợp riêng.

Các trường như địa chỉ IP, username, driver và cấu hình mã hóa có thể nhạy cảm về vận hành; chỉ cấp quyền đọc cho tài khoản cần thiết, hạn chế xuất log/screenshot.

### 5.3. system_views.settings: cấu hình runtime có đang như mong đợi?

~~~sql
DESCRIBE TABLE system_views.settings;

-- Truy vấn một tham số khi schema của phiên bản có name/value.
SELECT name, value
FROM system_views.settings
WHERE name = 'native_transport_port';

SELECT name, value
FROM system_views.settings
WHERE name = 'storage_port';
~~~

Các giá trị phản ánh **cấu hình của node đang phục vụ truy vấn**, giúp đối chiếu `cassandra.yaml`, native/internode port, một số cấu hình timeout hoặc cache. Không phải tất cả bí mật đều lộ nguyên văn qua bảng này: các phiên bản có cơ chế ẩn một số tham số nhạy cảm.

Nếu vừa sửa `cassandra.yaml` nhưng chưa triển khai/restart đúng quy trình, giá trị runtime có thể khác file trên đĩa. **Không thể `UPDATE system_views.settings SET ...` để thay cấu hình**; thực hiện qua cơ chế quản lý cấu hình/JMX/`nodetool` được hỗ trợ của phiên bản.

### 5.4. Thread pools: request có bị dồn hàng đợi?

~~~sql
DESCRIBE TABLE system_views.thread_pools;

SELECT name, active_tasks, pending_tasks, blocked_tasks
FROM system_views.thread_pools
LIMIT 30;
~~~

Nếu số `pending_tasks` hoặc `blocked_tasks` cao và tăng liên tục ở executor xử lý request, đó là **dấu hiệu cần điều tra tải**, không tự động là kết luận “nguyên nhân gốc đã được tìm thấy”. Cần kết hợp CPU, GC, disk I/O, network, request latency, dropped messages và query pattern.

Không cộng số `pending_tasks` của từng node rồi coi đó là metrics thống nhất với thời điểm chụp; khi truy vấn lần lượt nhiều node, snapshot có thể khác thời điểm.

### 5.5. SSTable tasks: quan sát compaction/streaming liên quan

~~~sql
DESCRIBE TABLE system_views.sstable_tasks;

SELECT keyspace_name, table_name, kind, progress, total, unit
FROM system_views.sstable_tasks
LIMIT 20;
~~~

Khi đang có task, các trường thường cho biết loại công việc (ví dụ compaction), tiến độ và đơn vị. Nếu bảng trống, có thể đơn giản là **không có tác vụ được bảng này ghi nhận tại thời điểm SELECT**; không kết luận “cluster không bao giờ compaction”.

Đối chiếu với:

~~~bash
nodetool compactionstats
nodetool netstats
~~~

`nodetool compactionstats` theo dõi compaction; `nodetool netstats` hỗ trợ xem streaming trong bootstrap/repair. Chúng không phải lệnh tương đương hoàn toàn với `system_views.sstable_tasks`. Khi gặp latency cao, không chạy `compact` hoặc `repair` chỉ vì có task xuất hiện; cần đánh giá backlog, tải, lịch bảo trì và mục đích của từng thao tác.

### 5.6. Disk/latency/internode: đọc đúng loại số liệu

Các virtual tables có thể gặp ở một số phiên bản Cassandra:

| Virtual table | Câu hỏi thường dùng |
| --- | --- |
| `system_views.disk_usage` | Bảng/keyspace nào đang tiêu thụ tài nguyên lưu trữ trên node được hỏi? |
| `system_views.local_read_latency` | Độ trễ đọc **local** của table trên node này ra sao? |
| `system_views.coordinator_read_latency` | Độ trễ đọc **qua coordinator** được node này quan sát thế nào? |
| `system_views.local_write_latency`, `coordinator_write_latency` | Trạng thái latency ghi ở các lớp local/coordinator. |
| `system_views.internode_inbound` / `internode_outbound` | Thông điệp node–node có queue, error, bytes hoặc throughput đáng chú ý không? |
| `system_views.rows_per_read` / `tombstones_per_read` | Truy vấn có xu hướng đọc nhiều row/tombstone không? |
| `system_views.max_partition_size` | Gợi ý bảng nào có partition lớn trên node, cần điều tra hot/large partition. |

Khám phá schema trước khi chọn cột:

~~~sql
DESCRIBE TABLE system_views.disk_usage;
SELECT * FROM system_views.disk_usage LIMIT 20;

DESCRIBE TABLE system_views.local_read_latency;
SELECT * FROM system_views.local_read_latency LIMIT 20;

DESCRIBE TABLE system_views.internode_outbound;
SELECT * FROM system_views.internode_outbound LIMIT 20;
~~~

Các tên/cột có thể khác giữa 4.x và 5.x. Tránh viết lệnh cố định tên column metric không tồn tại rồi coi `InvalidRequest` là lỗi Cassandra. Đọc `DESCRIBE TABLE` trước, chọn số liệu cần thiết, hạn chế `SELECT *` với bảng có nhiều trường trong hệ có lưu lượng lớn.

**Không hiểu sai chỉ số:**

- `local_read_latency` đo hoạt động cục bộ, không thay cho latency end-to-end của client.
- `coordinator_read_latency` liên quan request do node phối hợp, không đồng nghĩa mỗi replica đều chậm như nhau.
- Disk usage là thông tin **theo node/thời điểm**, không phải tổng dung lượng nhân với RF để suy ra chính xác logical size.
- Metrics có thể được reset theo vòng đời process và thay đổi liên tục; nên đo xu hướng/time series trước khi kết luận.

## 6. system.local và system.peers_v2: topology bổ sung

Trong nhiều tình huống debug driver, `system_schema` chỉ cho biết RF chứ không cho biết node đang ở datacenter nào. Đọc:

~~~sql
SELECT cluster_name, data_center, rack, release_version, schema_version
FROM system.local;

-- Chỉ chạy trên bản có peers_v2 (thường Cassandra 4.x trở lên).
DESCRIBE TABLE system.peers_v2;
SELECT * FROM system.peers_v2 LIMIT 10;
~~~

Với bản Cassandra cũ, có thể dùng `system.peers` thay cho `system.peers_v2`. Cấu trúc các bảng hệ thống khác theo phiên bản, nên kiểm tra `DESCRIBE TABLE` khi cần tên trường cụ thể như `peer`, `native_address`, `native_port`, `host_id`, `data_center` hay `rack`.

**Giới hạn:**

- `system.local` là metadata của **node nhận request**.
- `system.peers_v2` phản ánh **góc nhìn peer của node ấy**, không phải hệ thống registry trung tâm luôn đồng bộ tức thời.
- `schema_version` giúp so sánh schema agreement ở mức metadata, nhưng tự so một số UUID chưa thay thế quy trình chẩn đoán schema agreement đúng phiên bản.
- Khi node bootstrap, thay địa chỉ hoặc gossip chưa hội tụ, các node có thể nhìn thấy peer khác nhau. Kết hợp `nodetool status`, `nodetool describecluster` và log.

### 6.1. Thực hành kiểm tra schema agreement

Giả sử vừa chạy `ALTER TABLE` trong lab hoặc rollout schema production. Có thể ghi nhận version của node được hỏi:

~~~sql
SELECT schema_version, release_version
FROM system.local;
~~~

Ở cluster nhiều node, thu thập metadata tương ứng trên các node bằng cơ chế phù hợp, kết hợp:

~~~bash
nodetool describecluster
nodetool status
~~~

**Schema agreement không có nghĩa mọi replica đã đồng bộ dữ liệu.** Nó chỉ nói về sự hội tụ của **định nghĩa schema**. Repair/streaming/replication của dữ liệu là vấn đề khác. Java Driver có thể chờ schema agreement sau DDL, nhưng không nên xem metadata đọc ở một thời điểm là bất biến mãi mãi.

## 7. Một runbook truy vấn metadata theo tình huống

### Tình huống A: SELECT bị từ chối vì thiếu partition key

1. Xem câu truy vấn và tên bảng/keyspace chính xác.
2. Chạy:

   ~~~sql
   DESCRIBE TABLE metadata_lab.events_by_device_day;

   SELECT column_name, kind, position, type, clustering_order
   FROM system_schema.columns
   WHERE keyspace_name = 'metadata_lab'
     AND table_name = 'events_by_device_day';
   ~~~

3. Xác định `device_id` + `event_day` là partition key, không phải `event_time`.
4. Sửa truy vấn cho đúng phân vùng hoặc thiết kế bảng khác theo yêu cầu query. Không thêm `ALLOW FILTERING` vô tội vạ.

### Tình huống B: timeout với LOCAL_QUORUM

1. Xem RF của **keyspace thật**, không dùng RF của một lab khác:

   ~~~sql
   SELECT replication FROM system_schema.keyspaces
   WHERE keyspace_name = 'metadata_lab';
   ~~~

2. Kiểm tra local DC của coordinator, trạng thái replica và mạng internode:

   ~~~sql
   SELECT data_center, rack, release_version FROM system.local;
   ~~~

   ~~~bash
   nodetool status
   nodetool gossipinfo
   ~~~

3. Khi cần, kiểm tra `system_views.thread_pools`, latency table và `sstable_tasks` **trên node có vấn đề** để tìm dấu hiệu quá tải.
4. Phân biệt `Unavailable` (coordinator nhận thấy không đủ replica khả dụng) với `ReadTimeout`/`WriteTimeout` (không đủ phản hồi đúng hạn). Hạ CL production không phải cách sửa mặc định.

### Tình huống C: Java Driver báo lỗi handshake/TLS hoặc protocol

~~~sql
DESCRIBE TABLE system_views.clients;
SELECT address, port, driver_name, driver_version,
       protocol_version, ssl_enabled
FROM system_views.clients LIMIT 20;
~~~

Kiểm tra **đúng node** mà Java Driver đang cố kết nối. `ssl_enabled = false` có thể là bình thường trong lab không TLS, nhưng là tín hiệu phải kiểm tra nếu triển khai yêu cầu TLS bắt buộc. Nếu client chưa hoàn tất native handshake, nó có thể không xuất hiện như một connection sẵn sàng.

Tiếp tục kiểm tra DNS, TCP 9042, native TLS, CA/hostname, credentials, local datacenter và `broadcast_rpc_address` của các peer. Cần lưu ý `system_views.clients` có thể chứa thông tin nhạy cảm, không xuất dữ liệu thật ra nơi không được phép.

### Tình huống D: compaction backlog hoặc dữ liệu ngày càng lớn

~~~sql
DESCRIBE TABLE metadata_lab.events_by_device_day;
DESCRIBE TABLE system_views.disk_usage;
DESCRIBE TABLE system_views.sstable_tasks;

SELECT * FROM system_views.disk_usage LIMIT 20;
SELECT * FROM system_views.sstable_tasks LIMIT 20;
~~~

Kiểm tra config compaction của bảng qua `system_schema.tables`, rồi quan sát workload thực bằng `nodetool compactionstats` và metrics. Cân nhắc số lượng/độ lớn partition, tombstones, TTL và lưu lượng ghi. Không chỉnh compaction strategy chỉ từ một snapshot metrics.

## 8. Java Driver 4.x: dùng Metadata API thay vì tự parse DESCRIBE

Trong ứng dụng Java, bạn không cần gửi `DESCRIBE` như một CQL statement. `DESCRIBE` là lệnh **cqlsh**. Java Driver 4.x cung cấp **metadata API** để đọc schema mà driver đã khám phá.

Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.schema.KeyspaceMetadata;
import com.datastax.oss.driver.api.core.metadata.schema.TableMetadata;

import java.net.InetSocketAddress;
import java.util.Optional;

public class CassandraMetadataDemo {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            Optional<KeyspaceMetadata> keyspace = session.getMetadata()
                    .getKeyspace(CqlIdentifier.fromCql("metadata_lab"));
            if (keyspace.isEmpty()) {
                throw new IllegalStateException("Khong tim thay keyspace metadata_lab");
            }

            Optional<TableMetadata> table = keyspace.get()
                    .getTable(CqlIdentifier.fromCql("events_by_device_day"));
            if (table.isEmpty()) {
                throw new IllegalStateException("Khong tim thay bang");
            }

            System.out.println("Partition key:");
            table.get().getPartitionKey().forEach(column ->
                    System.out.println("  " + column.getName()));

            System.out.println("All columns:");
            table.get().getColumns().forEach((name, column) ->
                    System.out.println("  " + name + " = " + column.getType()));
        }
    }
}
~~~

**Điều kiện và giới hạn:**

- `datacenter1` chỉ là tên minh họa. Xem `SELECT data_center FROM system.local;` để đặt `withLocalDatacenter` đúng deployment.
- Java Driver không tự bật TLS/auth chỉ vì cqlsh trên máy đã kết nối được; cấu hình SSL context, credentials và native contact points khi cần.
- `session.getMetadata()` trả **snapshot metadata bất biến** của driver tại thời điểm gọi. Nếu cần thấy schema mới sau DDL, lấy metadata lại sau khi driver refresh/schema agreement; không giữ mãi một reference cũ rồi cho rằng nó tự cập nhật. <https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/schema/>.
- Metadata discovery có thể bị tắt hoặc giới hạn keyspace theo cấu hình driver; khi không thấy schema mong đợi, kiểm tra policy/config và quyền thay vì tự ý sửa `system_schema`.
- `system_views` là node-local. Một query `SELECT * FROM system_views.clients` qua pool driver có thể được gửi đến **coordinator được driver chọn**, không bảo đảm trả dữ liệu của mọi node. Muốn kiểm tra từng node, chọn cách kết nối/định tuyến có kiểm soát và xác minh endpoint.
- Dữ liệu metadata không thay thế **prepared statements** và query đúng partition key. Đọc schema chỉ giúp ứng dụng biết cấu trúc; consistency và replica vẫn được xử lý theo mỗi request.

### 8.1. Đối chiếu schema với ứng dụng

Giả sử Java Driver báo `InvalidQueryException` vì cột không tồn tại. Cách điều tra:

1. Xác nhận keyspace/table mà ứng dụng thực sự gửi (ưu tiên tên đủ `keyspace.table`).
2. Đọc `DESCRIBE TABLE` trong cqlsh và kiểm tra `system_schema.columns`.
3. Đọc metadata qua `session.getMetadata()` và xác nhận đã refresh sau migration DDL.
4. Kiểm tra schema agreement của cluster và log migration/schema nếu có.
5. Sửa query, prepared statement hoặc luồng migration; không `INSERT` vào bảng hệ thống để “tạo cột”.

## 9. Quyền truy cập và những điều không nên làm

Các system keyspaces có thể tiết lộ **topology, username, IP, driver versions, configuration, performance và schema của dữ liệu nghiệp vụ**. Chỉ đọc metadata mà một role thực sự cần; không cấp quyền mở rộng trên toàn `system`/`system_views` cho mọi ứng dụng chỉ vì tiện debug.

**Không thực hiện:**

- `UPDATE system_schema.columns ...` hoặc `DELETE FROM system_schema.tables ...` để sửa bảng; phải dùng DDL hợp lệ.
- `UPDATE system_views.settings ...` để sửa giá trị cấu hình; virtual tables không phải API quản trị cấu hình theo DML.
- `DROP` hoặc `TRUNCATE` virtual tables để “xóa metrics”.
- Giả định `system_views.clients` đọc từ một coordinator là danh sách kết nối của cả cluster.
- Giả định `system_schema.tables` cho biết số row, dữ liệu logic hoặc throughput.
- Đánh đồng `system_schema.views` với `system_views`.
- Mặc định mọi bảng hệ thống tồn tại trên mọi Cassandra version; phải kiểm tra `SHOW VERSION`/`DESCRIBE`.
- Chạy `SELECT *` trên bảng không giới hạn ở production khi chưa hiểu kích thước/chi phí. Metadata hệ thống thường nhỏ hơn dữ liệu ứng dụng nhưng vẫn cần dùng có mục đích.

### 9.1. Các lỗi dễ gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `unconfigured table system_views...` | Server quá cũ hoặc virtual table không tồn tại ở phiên bản đó | `SHOW VERSION`, `DESCRIBE KEYSPACE system_views`, xem tài liệu đúng version. |
| `Unauthorized` khi xem metadata | Role thiếu quyền đọc bảng hệ thống | Xin quyền tối thiểu có phê duyệt; không vô hiệu hóa authorizer. |
| `InvalidRequest` khi `UPDATE system_views.settings` | Virtual table không cho DML sửa dữ liệu | Dùng cơ chế cấu hình/JMX/`nodetool` được hỗ trợ. |
| `system_schema.views` không có row | Lab chưa tạo materialized view | Đây không liên quan việc `system_views` có hay không. |
| Java metadata không có bảng mới | Snapshot cũ, schema refresh/policy/DDL chưa hội tụ | Lấy snapshot mới, kiểm tra schema agreement và migration. |
| `system_views.clients` ít kết nối hơn mong đợi | Chỉ phản ánh node đang được hỏi | Quan sát từng native endpoint, đối chiếu driver contact points/topology. |
| `sstable_tasks` trống giữa lúc hệ thống tải cao | Không có tác vụ ghi nhận ở thời điểm SELECT hoặc bảng không phản ánh nguyên nhân tải | Xem thread pools, metrics, logs, `nodetool compactionstats`/`netstats`. |
| Không thấy `system.peers_v2` | Version/metadata hỗ trợ khác | Kiểm tra `system.peers` và docs version, không sửa bảng hệ thống. |
| CL thay đổi nhưng kết quả virtual table không khác | Virtual tables node-local không áp dụng quorum như bảng dữ liệu | Dùng CL cho bảng replicated; cần chọn đúng node khi xem metrics. |

## 10. Bài tập thực hành

1. Tạo `metadata_lab.events_by_device_day`, rồi dùng `DESCRIBE TABLE` và `system_schema.columns` để chỉ ra **hai cột partition key**, thứ tự clustering và kiểu dữ liệu.
2. Dùng `system_schema.keyspaces` xem replication của `metadata_lab`. Giải thích tại sao RF = 1 không mô phỏng quorum nhiều replica.
3. So sánh `system_schema.tables.compaction` với `system_views.sstable_tasks`. Một nguồn trả cấu hình, một nguồn trả trạng thái gì?
4. Truy vấn `system_schema.views` và `DESCRIBE KEYSPACE system_views`. Giải thích vì sao hai tên “views” khác mục đích.
5. Chạy `DESCRIBE TABLE system_views.clients` rồi xem một số kết nối trên node. Các trường nào giúp kiểm tra native protocol version và TLS?
6. Truy vấn `system_views.settings` cho `native_transport_port` và `storage_port`. Tại sao không thể `UPDATE` virtual table để thay port?
7. Xem `system_views.thread_pools` và `sstable_tasks` khi lab có truy vấn. Nếu `pending_tasks = 0` hay bảng task trống, điều đó có đủ để chứng minh toàn cluster không có vấn đề hiệu năng không?
8. Chạy `SELECT cluster_name, data_center, release_version, schema_version FROM system.local;`. Phân biệt thông tin node-local với metadata schema của keyspace.
9. Viết Java sử dụng `session.getMetadata().getKeyspace(...)` và `getTable(...)` để in tên các cột. Sau DDL, tại sao cần lấy metadata mới thay vì giữ snapshot cũ?
10. Giả sử SELECT theo `event_time` không có `device_id/event_day` thất bại. Dùng metadata để giải thích lỗi và viết lại câu truy vấn đúng.
11. Với cluster nhiều node, tại sao cần đọc `system_views.clients` hoặc `disk_usage` trên **từng node** khi điều tra thay vì một coordinator bất kỳ?
12. Khi hệ thống báo timeout và compaction backlog, liệt kê ít nhất ba nguồn metadata/metrics cần đối chiếu trước khi thay compaction strategy hay consistency.

**Tiêu chí hoàn thành:** phân biệt schema metadata với node-local virtual metrics; đọc và giải thích được partition/clustering key từ `system_schema`; chọn đúng bảng quan sát `system_views`; không sửa bảng hệ thống; và biết dùng metadata API của Java Driver để xác minh schema khi phát triển ứng dụng.

## Tài liệu tham khảo

- [Apache Cassandra — Virtual Tables](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/virtualtables.html): cách virtual tables hoạt động, `system_views`, `system_virtual_schema` và giới hạn node-local/read-only.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): keyspace, table, primary key, options và các đối tượng schema.
- [Apache Cassandra — System Keyspaces](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): kiến trúc cluster, metadata và node.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `describecluster`, `compactionstats`, `netstats`.
- [Apache Cassandra Java Driver — Schema Metadata 4.18.1](https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/schema/): `session.getMetadata()`, `getKeyspace`, `getTable`, snapshot và schema agreement.
