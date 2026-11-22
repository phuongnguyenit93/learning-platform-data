# CREATE/DROP INDEX và quan sát trạng thái sẵn sàng

## 1. Vì sao câu lệnh CREATE INDEX thành công chưa đủ?

Trong Apache Cassandra, **primary index** đã được hình thành từ **partition key** của bảng: hệ thống dùng token để xác định replica rồi dùng clustering key để duyệt row trong partition. Khi ứng dụng cần truy vấn theo cột **không thuộc khóa chính**, Cassandra có thể cung cấp **secondary index**. Việc tạo index bổ sung ảnh hưởng tới schema, đường đọc/ghi, compaction, mạng giữa các node và khả năng ứng dụng Java thực thi CQL.

Lệnh `CREATE INDEX` chỉ là **khởi đầu của vòng đời index**. Nếu bảng đã có dữ liệu, Cassandra còn phải tạo các cấu trúc tra cứu cho dữ liệu hiện hữu trên những node liên quan. Khi triển khai vào cluster nhiều node, cần phân biệt:

1. **Schema đã ghi nhận index**: tra được định nghĩa qua `system_schema.indexes`.
2. **Schema agreement**: các node đã nhận cùng phiên bản thay đổi schema.
3. **Index build/query readiness**: index của dữ liệu cũ đã được xây dựng, các node cần phục vụ truy vấn đã sẵn sàng.
4. **Hiệu năng và tính đúng đắn đã được xác minh**: query trả kết quả mong đợi ở CL thực, trong giới hạn latency/tải chấp nhận được.

Ba mốc đầu **không tự chứng minh mốc cuối**. Hơn nữa, `DROP INDEX` xóa đường truy vấn phụ: bảng cơ sở vẫn còn, nhưng các câu `WHERE indexed_column = ?` có thể **không còn hợp lệ**. Do đó, cả tạo và xóa index đều là thay đổi schema cần phối hợp với ứng dụng.

Bài thuộc chương **Chỉ mục** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó kết nối kiến thức partition key, bảng thiết kế theo truy vấn, replication, consistency, compaction, repair, lỗi Cassandra và Java Driver với một quy trình quản lý chỉ mục có thể kiểm chứng.

**Kết quả học tập:**

- Viết `CREATE INDEX`, `DROP INDEX`, `IF NOT EXISTS` và `IF EXISTS` đúng ngữ cảnh.
- Phân biệt primary index, legacy 2i, SAI và các giới hạn theo phiên bản.
- Tra cứu metadata `system_schema.indexes`; kiểm tra SAI với `system_views.indexes` và các chỉ số node-local trên Cassandra 5.x.
- Xây dựng lab CQL có dữ liệu **trước khi tạo index** để quan sát nhu cầu backfill/build.
- Biết cách xác nhận index dùng được trên **toàn bộ các node ứng dụng có thể liên hệ**, không chỉ một coordinator.
- Thiết kế bước deploy, thử nghiệm, đổi truy vấn, drop và rollback an toàn.
- Chẩn đoán các lỗi `InvalidRequest`, chưa queryable, `Unauthorized`, timeout và kết nối Java.

## 2. Phân biệt các loại index trước khi viết DDL

| Loại | Cách hình thành | Cơ chế truy cập | Có dùng CREATE/DROP INDEX không? |
| --- | --- | --- | --- |
| **Primary index** | Tự có từ `PRIMARY KEY` của bảng | Partition key/token; clustering rows trong partition | **Không** tạo bằng `CREATE INDEX`. |
| **2i, legacy secondary index** | Index phụ kiểu cũ; được duy trì như bảng index ẩn cục bộ mỗi node | Có thể phải phối hợp nhiều node khi query không có partition key | **Có**, với cú pháp/default tùy phiên bản. |
| **SAI, Storage-Attached Index** | Index theo cột gắn với memtable/SSTable, tích hợp trong **Apache Cassandra 5.0+** | Hỗ trợ nhiều predicate/range phù hợp qua index query planner | **Có**, ghi rõ `USING 'sai'` trên bản hỗ trợ. |
| **SASI, SSTable-Attached Secondary Index** | Custom index legacy, có mã nguồn và mode riêng | Feature thử nghiệm, **không được khuyến nghị production** | Có cú pháp custom, nhưng không bật chỉ để học bài này. |

**Giới hạn phiên bản:** Apache Cassandra 3.x/4.x upstream có 2i, nhưng **SAI tích hợp từ 5.0**. Các bản phân phối Cassandra-compatible có thể khác về tính năng, mặc định hoặc hỗ trợ; phải đối chiếu đúng server đang chạy. SASI không tương đương SAI và không phải lựa chọn mới mặc định.

Trong Cassandra 5.x, cấu hình `default_secondary_index`/guardrails có thể ảnh hưởng loại index tạo ra khi câu `CREATE INDEX` **không ghi `USING`**. Vì vậy, khi tài liệu hoặc migration cần chính xác loại index, hãy **khai báo implementation nếu phiên bản hỗ trợ** và luôn kiểm tra metadata sau tạo. Một tên như `status_idx` không cho biết đó là 2i hay SAI.

### 2.1. Một index không có nghĩa một truy vấn luôn nhanh

Index giúp chọn các row ứng viên theo một cột. Nó **không** tự:

- Biến `status` thành partition key của bảng cơ sở.
- Bảo đảm câu `WHERE status='OK'` chỉ phải đọc ít dữ liệu khi `OK` khớp phần lớn bảng.
- Tạo thứ tự toàn cluster cho `ORDER BY event_time`.
- Xóa mọi chi phí replica/consistency, tombstone, network hoặc read repair.
- Thay việc thiết kế **partition/bucket**, chống hot partition và kiểm soát số row mỗi partition.

Khi query chủ yếu biết đầy đủ partition key, thường ưu tiên primary-key access thay vì thêm secondary index.

## 3. Cú pháp CREATE INDEX: chọn đúng mục tiêu và phiên bản

### 3.1. Dạng thường dùng

~~~sql
-- Mẫu cú pháp chung, KHÔNG phải lệnh chạy khi chưa có bảng.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name);

-- Chỉ trên Apache Cassandra 5.x có SAI.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name)
USING 'sai';

-- Loại legacy chỉ khi phiên bản triển khai hỗ trợ tên implementation.
CREATE INDEX IF NOT EXISTS index_name
ON keyspace_name.table_name (column_name)
USING 'legacy_local_table';
~~~

Giải thích:

- `index_name`: tên index **duy nhất trong keyspace**; không thể dùng cùng tên cho hai index khác nhau trong cùng keyspace.
- `keyspace_name.table_name`: bảng đã tồn tại và có cột đích hợp lệ.
- `column_name`: cột được index. Mỗi SAI index áp dụng cho **một cột**, muốn lọc theo nhiều cột cần xem quy tắc nhiều SAI indexes.
- `IF NOT EXISTS`: giúp tránh lỗi khi một index cùng tên đã tồn tại, nhưng **không so sánh và sửa implementation/options**; không dùng nó để khẳng định hệ thống đã đúng cấu hình kỳ vọng.
- `USING 'sai'`: yêu cầu SAI và chỉ chạy trên server thực sự hỗ trợ.
- `USING 'legacy_local_table'`: cách khai báo rõ loại legacy trên những phiên bản hỗ trợ. Ở Cassandra 4.x có thể cần dùng cú pháp 2i thường và kiểm tra index tạo ra.

Trong Cassandra 5.0, `CREATE INDEX` có thể nhận tùy chọn bổ sung như `WITH OPTIONS` cho SAI. Ví dụ `case_sensitive`, `normalize` và `ascii` có thể tác động ngữ nghĩa so khớp text. **Không thay các tùy chọn này khi không hiểu ảnh hưởng lên kết quả và khả năng build lại index.**

### 3.2. Đối tượng index nào được phép tạo?

Không phải mọi cột hay toán tử đều hỗ trợ như nhau. Ví dụ:

| Trường hợp | Lưu ý trước khi tạo |
| --- | --- |
| Cột `text`, `int`, `double`, `timestamp` | Thường có thể tạo secondary index tùy implementation/version. |
| Cột là partition key đơn | Primary index đã tối ưu lookup; SAI không cho tạo trên **partition key chỉ có một cột**. |
| Một thành phần của composite partition key | SAI 5.x có thể hỗ trợ index trên thành phần, nhưng phải đánh giá query thực tế. |
| Clustering/regular/static columns | Kiểm tra giới hạn loại index; không coi mọi cột cùng semantics. |
| Collection `list/set/map` | Cú pháp `KEYS`, `VALUES`, `ENTRIES`, `FULL` phụ thuộc loại dữ liệu/index; phải đối chiếu docs đúng bản. |
| `counter` | Không hỗ trợ tạo SAI index trên counter. |
| Non-frozen UDT | SAI có các giới hạn rõ; không giả định mọi dạng UDT đều index được. |

Một lỗi như `InvalidRequest` hoặc `Cannot create index` lúc này thường là lỗi **schema/feature/constraint**, không nhất thiết do index build hay node chết. Đọc thông báo server trước khi tìm cách “tăng timeout”.

### 3.3. Cú pháp DROP INDEX

~~~sql
-- Tên được định danh theo keyspace, không theo table.
DROP INDEX IF EXISTS keyspace_name.index_name;
~~~

`DROP INDEX` xóa **định nghĩa và cấu trúc index**, không xóa bảng cơ sở hoặc toàn bộ các row. `IF EXISTS` làm thao tác không lỗi khi index không tồn tại, nhưng **không chứng minh việc xóa không ảnh hưởng application**. Khi index biến mất, request dùng predicate chỉ nhờ index có thể bị `InvalidRequest`.

**Không dùng `DROP TABLE` để xóa index**. Một câu `DROP TABLE` là thao tác phá hủy schema/dữ liệu ứng dụng; phạm vi tác động hoàn toàn khác `DROP INDEX`.

## 4. Thời điểm: metadata → schema agreement → index build → queryable

~~~mermaid
flowchart TD
    DDL["CREATE INDEX gửi tới Cassandra"] --> SCHEMA["Schema chứa index"]
    SCHEMA --> AGREEMENT["Kiểm tra schema agreement giữa node"]
    SCHEMA --> BUILD["Build index trên dữ liệu đã tồn tại"]
    BUILD --> READY{"Index trên node liên quan queryable?"}
    READY -->|"Chưa"| OBS["Theo dõi logs, trạng thái, lỗi; không chuyển traffic"]
    OBS --> BUILD
    READY -->|"Có"| CHECK["So sánh kết quả theo primary key + indexed query"]
    AGREEMENT --> CHECK
    CHECK --> PERF["Thử tải, CL/replica, latency và rollback"]
    PERF --> SWITCH["Chuyển traffic có kiểm soát"]
~~~

Các nhánh có thể diễn ra song song; đây là **runbook logic**, không phải trình tự bên trong bất biến của mọi implementation.

### 4.1. “Có trong system_schema” chỉ là trạng thái định nghĩa

~~~sql
SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab';
~~~

Bảng metadata chứa các index khai báo của keyspace (sau khi lab đã tạo). Nó không chứa cột chung `is_queryable` đáng tin cậy cho mọi loại 2i/SAI. Các trường `kind`/`options` cần đối chiếu với loại index và phiên bản để nhận diện 2i hoặc SAI.

**Đừng đánh đồng:** `DESCRIBE TABLE` đã in `CREATE INDEX` ≠ index của dữ liệu lịch sử đã hoàn tất build ở tất cả node.

### 4.2. Schema agreement là gì?

Sau DDL, các node trao đổi metadata schema. **Schema agreement** nghĩa là cluster đạt một góc nhìn đồng thuận về **định nghĩa schema**. Nhưng:

- Không chứng minh tất cả replica của dữ liệu đã đồng bộ.
- Không đảm bảo mọi index background build đã hoàn thành.
- Không chứng minh mọi Java Driver session đã refresh metadata/schema.
- Không chứng minh index query đạt SLA ở CL và concurrency thực.

Từ node quản trị có quyền:

~~~bash
nodetool describecluster
nodetool status
~~~

Kết quả `nodetool describecluster` có thể giúp xem nhóm schema versions, còn `nodetool status` cho biết trạng thái cluster từ góc nhìn node được hỏi. Để khẳng định index sẵn sàng, **vẫn cần theo dõi build và kiểm tra query thực tế**.

### 4.3. Index trên dữ liệu có sẵn cần backfill/build

Khi tạo index **trên bảng đã chứa dữ liệu**, Cassandra phải xây các mục index tương ứng dữ liệu cũ. Theo tài liệu Apache:

- 2i có **background index build**, không cấm các thao tác đọc/ghi bảng cơ sở trong toàn bộ quá trình.
- SAI có quy trình build index cho SSTables và memtable; với dữ liệu cũ, phải chờ trạng thái index **queryable**.
- Ghi mới sau khi tạo index được xử lý theo write/index maintenance của implementation.
- Thời lượng build có thể tăng theo data volume, số SSTable, disk/CPU, compaction đang chạy và node health.

Vì thế không đưa query phụ thuộc index mới ra production ngay khi DDL trả thành công. Hãy chuẩn bị **giai đoạn chờ readiness có giám sát**, ghi rõ điều kiện “hoàn tất” thay vì dùng sleep cố định.

## 5. Hai nguồn quan sát: system_schema và system_views

### 5.1. system_schema.indexes: mọi loại index được khai báo

~~~sql
-- Metadata schema, có thể dùng khi version hỗ trợ bảng system_schema này.
SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab';
~~~

Ở ví dụ lab sẽ có `events_2i` và/hoặc `events_sai`. Nếu tên index dự kiến không xuất hiện, hãy xác minh:

1. Bạn có kết nối đúng cluster/port/native endpoint không (`SHOW HOST`)?
2. Tên keyspace/table/index có đúng không?
3. DDL có thất bại vì quyền, syntax, giới hạn chỉ mục, hoặc default index type không?
4. Có node/schema nào chưa thấy thay đổi không?

Sự có mặt của row metadata chỉ xác nhận **index được khai báo**. Đừng coi số row metadata là số replica đã build xong.

### 5.2. SAI 5.x: system_views.indexes cho trạng thái runtime

Trên Apache Cassandra 5.0 trở lên, SAI cung cấp virtual table **`system_views.indexes`**. Xem schema trước:

~~~sql
DESCRIBE TABLE system_views.indexes;

-- Đúng key của virtual table: keyspace_name + index_name.
SELECT keyspace_name, index_name, table_name, column_name,
       is_building, is_queryable, indexed_sstable_count,
       per_column_disk_size, per_table_disk_size
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_status_idx';
~~~

Các trường chính:

| Cột | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| `is_building` | Node đang ghi nhận quá trình build index hay không | `false` **không đủ** để chứng minh có index queryable. |
| `is_queryable` | Có thể sử dụng index để phục vụ query tại node được hỏi | Không chứng minh tất cả node khác cũng đã sẵn sàng. |
| `indexed_sstable_count` | Số SSTable thực sự có dữ liệu được index | Không bằng số SSTable của toàn bảng nếu có SSTable không chứa dữ liệu cần index. |
| `per_column_disk_size` | Dung lượng disk của phần index riêng cho cột | Không phải toàn bộ dung lượng table. |
| `per_table_disk_size` | Dung lượng index components dùng chung trong table | Không nhân/cộng bừa giữa nhiều index cùng bảng. |
| `column_name`/`table_name` | Nhận diện cột/bảng của index | Không xác nhận permission/query shape đã đúng. |

**Góc nhìn node-local:** virtual table này phản ánh node đang phục vụ câu CQL. Trong cluster nhiều node, hãy kiểm tra trên **từng native endpoint có thể nhận query liên quan** hoặc dùng monitoring tập trung có nhãn node. Đọc `true` từ một contact point không có nghĩa mọi replica đã xong build.

Nếu bản Cassandra không có bảng/cột trên, **không viết thêm bảng** và không sửa trực tiếp `system_views`: xác nhận server version, implementation và schema virtual table của bản đang chạy.

### 5.3. Vì sao không dùng system_views.indexes để kiểm tra 2i?

`system_views.indexes` được tài liệu hóa cho **SAI**, không phải API trạng thái tổng quát của mọi 2i và SASI. Với legacy 2i:

- Đọc `system_schema.indexes` để xác nhận DDL/type.
- Theo dõi thông điệp build, logs và metrics từ **từng node** có index.
- Kiểm tra schema agreement và sức khỏe node; quan sát `nodetool`.
- Chạy truy vấn index **có thể đối chiếu được với dữ liệu gốc** sau khi build, trên cluster lab/traffic có kiểm soát.
- Nếu buộc rebuild, dùng `nodetool rebuild_index` theo runbook, **không xem rebuild là bước bắt buộc sau mọi CREATE INDEX**.

Một câu query index trả về 2 row đúng ở cluster lab một node **không chứng minh** build trên cluster nhiều node hoàn tất. Cần kiểm tra từng node hoặc nguồn quan sát phù hợp.

## 6. Lab chung: chuẩn bị bảng theo partition key và dữ liệu cố định

### 6.1. Điều kiện

Ví dụ dùng **Cassandra lab một node**, có `cqlsh` và quyền tạo schema/index. Nhánh 2i dùng được trên 4.x/5.x sau khi kiểm tra default; nhánh SAI **chỉ chạy trên Apache Cassandra 5.0+**.

Từ terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS index_ops_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS index_ops_lab.events_2i (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE index_ops_lab.events_2i;
~~~

`SimpleStrategy`/RF = 1 phục vụ lab **không chịu lỗi**. Trên production đa datacenter thường chọn `NetworkTopologyStrategy` và RF theo DC; không copy cấu hình này làm mặc định deployment.

**Thiết kế bảng:** composite partition key `(device_id, event_day)` cho query một thiết bị trong một ngày; clustering `event_time`, `event_id` giúp đọc theo thời gian. `status` là regular column, không tự tạo primary-index lookup.

### 6.2. Ghi fixture trước khi tạo index

~~~sql
INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'OK', 24.2);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'WARN', 30.8);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 'WARN', 28.5);

INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'OK', 25.0);
~~~

Các UUID/UTC timestamp cố định giúp **chạy lại là upsert cùng row**, không thêm row trùng primary key. Nếu bảng đã chứa dữ liệu khác, đừng tuyên bố chính xác chỉ có bốn row; kiểm tra bảng và trạng thái fixture. `IF NOT EXISTS` không thay đổi schema bảng cũ đã có cấu trúc khác.

Truy vấn baseline, **không cần index**:

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Kỳ vọng `01:05 WARN 30.8` rồi `01:00 OK 24.2`. Đây là đường truy cập hợp lý theo partition/clustering key.

### 6.3. Trước index, query theo status có thể bị từ chối

~~~sql
-- Chỉ thực hiện TRƯỚC khi tạo index trong lab.
-- Đúng cú pháp SELECT, nhưng chưa có đường truy cập vào regular column.
SELECT device_id, event_day, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Khi chưa có index trên `status`, Cassandra thường trả `InvalidRequest`/cảnh báo truy vấn cần filtering. Không sửa bằng cách thêm `ALLOW FILTERING` cho production. Đây là **phép thử âm** để minh họa index sẽ thay đổi khả năng truy vấn.

## 7. Nhánh A: tạo và kiểm chứng legacy 2i

### 7.1. Xem version, chọn đúng cú pháp

**Trên Cassandra 4.x** có 2i truyền thống, ví dụ:

~~~sql
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_ops_lab.events_2i (status);
~~~

**Trên Cassandra 5.x** và bản có implementation name phù hợp, để tránh phụ thuộc default:

~~~sql
-- Chạy THAY cho câu CREATE INDEX ở trên, không chạy cả hai.
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_ops_lab.events_2i (status)
USING 'legacy_local_table';
~~~

**Chọn đúng một nhánh** theo server version. Nếu vừa chạy cả hai lệnh, `IF NOT EXISTS` có thể bỏ qua yêu cầu sau chứ không tự “đổi index thành loại kia”. Để kiểm tra:

~~~sql
DESCRIBE TABLE index_ops_lab.events_2i;

SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_2i';
~~~

Kiểm tra `kind`/`options` để xác nhận loại index thực, đặc biệt trên Cassandra 5.x với cấu hình default khác nhau.

### 7.2. Sau CREATE INDEX: khi nào dùng được?

Vì bốn row được ghi **trước** khi index tạo, hệ thống phải index dữ liệu đã có. Với 2i, quá trình build được thực hiện trong nền; việc `CREATE INDEX` trả về không thay thế xác minh build.

Trên lab một node, sau khi hoạt động build hoàn tất và query sẵn sàng:

~~~sql
SELECT device_id, event_day, event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Kỳ vọng **2 row**: `sensor-01` lúc `01:05` và `sensor-02` lúc `01:03`. Thứ tự hai row khác partition **không được đảm bảo**.

Không giả định một lần SELECT thành công khi index mới tạo đồng nghĩa index trên mọi node trong cluster production đã đầy đủ. Với cluster nhiều node, xem logs/build/health của từng node và thực hiện kiểm tra nhiều partition đại diện.

### 7.3. Ghi thêm dữ liệu sau khi có index

~~~sql
INSERT INTO index_ops_lab.events_2i
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-04', '2026-11-21', '2026-11-21T01:09:00Z',
        55555555-5555-4555-8555-555555555555, 'WARN', 31.0);

SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Kỳ vọng **3 row** sau khi thao tác ghi được phản ánh ở CL của lab. Hệ thống duy trì index cho dữ liệu ghi mới tự động. Trong cluster thật có concurrent writers và RF > 1, phải xem CL/replica readiness trước khi kết luận “mọi node đã quan sát thấy cùng trạng thái”.

### 7.4. Xem tác động UPDATE vào cột được index

~~~sql
UPDATE index_ops_lab.events_2i
SET status = 'OK'
WHERE device_id = 'sensor-02'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:03:00Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;

SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Kỳ vọng `sensor-02` **không còn nằm trong kết quả `WARN`**, còn `sensor-01` và `sensor-04` vẫn khớp. Đọc theo primary key nếu cần đối soát row. Update/delete index column có chi phí maintenance và tombstone, đặc biệt với 2i trên dữ liệu biến động nhiều.

## 8. Nhánh B: SAI trên Apache Cassandra 5.0+

### 8.1. Tạo bảng lab riêng

**Bỏ qua toàn bộ mục 8 nếu đang dùng Cassandra 3.x/4.x upstream.** SAI được tích hợp từ Apache Cassandra 5.0 và có cú pháp riêng.

~~~sql
CREATE TABLE IF NOT EXISTS index_ops_lab.events_sai (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- Đưa dữ liệu trước khi CREATE INDEX để mô phỏng index build.
INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'WARN', 30.8);

INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 'WARN', 28.5);

INSERT INTO index_ops_lab.events_sai
  (device_id, event_day, event_time, event_id, status, temperature)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'OK', 25.0);
~~~

### 8.2. Tạo SAI và quan sát trạng thái

~~~sql
-- Apache Cassandra 5.0+.
CREATE INDEX IF NOT EXISTS events_sai_status_idx
ON index_ops_lab.events_sai (status)
USING 'sai';

-- Có thể thêm index trên numeric column khi workload cần range.
CREATE INDEX IF NOT EXISTS events_sai_temperature_idx
ON index_ops_lab.events_sai (temperature)
USING 'sai';

-- Xác minh index có trong schema.
SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_sai';

-- Xem cấu trúc virtual table trên bản đang chạy.
DESCRIBE TABLE system_views.indexes;
~~~

Trạng thái cụ thể:

~~~sql
SELECT index_name, table_name, column_name, is_building, is_queryable,
       indexed_sstable_count
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_status_idx';

SELECT index_name, table_name, column_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND index_name = 'events_sai_temperature_idx';
~~~

Ở cluster nhiều node, kiểm tra trạng thái này **theo node**. Nếu giá trị `is_queryable = false`, index chưa phục vụ được các query dùng nó. Nếu `is_building = false` mà `is_queryable = false`, vẫn phải điều tra, không tự coi “hết xây” đồng nghĩa sẵn sàng.

### 8.3. Thực hiện truy vấn chỉ sau khi SAI queryable

~~~sql
-- Hai row WARN trong fixture của bảng events_sai.
SELECT device_id, event_time, status, temperature
FROM index_ops_lab.events_sai
WHERE status = 'WARN';

-- Hai predicate đều có SAI; chỉ sensor-01 khớp nhiệt độ >= 30.
SELECT device_id, event_time, status, temperature
FROM index_ops_lab.events_sai
WHERE status = 'WARN'
  AND temperature >= 30.0;
~~~

Kỳ vọng:

| Query | Kết quả trên bảng `events_sai` |
| --- | --- |
| `status = 'WARN'` | 2 row: `sensor-01`, `sensor-02`. |
| `status = 'WARN' AND temperature >= 30` | 1 row: `sensor-01`, `30.8`. |

Mỗi SAI index lập trên một cột; hệ thống có thể phối hợp nhiều indexed predicates trong một query phù hợp. **Không dùng `LIKE '%text%'` để minh họa SAI 5.0**, vì `LIKE` không được hỗ trợ bởi SAI theo tài liệu.

### 8.4. Thêm, xóa index SAI có ảnh hưởng gì?

- Bảng cơ sở vẫn phục vụ các truy vấn **không phụ thuộc index**.
- Khi tạo lại SAI trên bảng có sẵn dữ liệu, cần chờ build/queryable trên những node liên quan.
- Index SAI có index components gắn với SSTable; flush/compaction và dữ liệu mới tác động tới vòng đời thành phần index.
- Khi `DROP INDEX`, các truy vấn phụ thuộc duy nhất index đó không thể tiếp tục được giữ như một API ổn định nếu không có đường truy cập khác.

Không coi `DROP` rồi `CREATE` là thao tác “sửa index trong chớp mắt” trên production có tải: khoảng chuyển tiếp có thể làm ứng dụng trả lỗi và build lại tốn disk/CPU.

## 9. DROP INDEX: thứ tự an toàn trước và sau khi xóa

### 9.1. Quy trình trước khi drop

Không chạy `DROP INDEX` trực tiếp chỉ vì thấy index không còn xuất hiện trong một truy vấn kiểm thử. Một checklist hợp lý:

1. **Inventory** tất cả query/service/Job dùng cột indexed; chú ý dynamic CQL và query nội bộ.
2. Xác nhận **đường truy vấn thay thế**: partition key, bảng materialized/query-oriented, SAI khác phù hợp hoặc search service.
3. Triển khai client mới/feature flag và kiểm tra không còn request phụ thuộc index cũ.
4. Giám sát query pattern, error rate, latency và metrics index trên cluster đại diện.
5. Chụp metadata/schema, ghi **tên index + options** chính xác để có thể tạo lại khi rollback.
6. Có maintenance window/approval nếu drop ảnh hưởng nhiều service hoặc rebuild lớn.

### 9.2. Thử DROP trong lab

Sau khi hoàn tất các kiểm tra ở nhánh A:

~~~sql
-- Chỉ xóa index của lab events_2i.
DROP INDEX IF EXISTS index_ops_lab.events_2i_status_idx;

SELECT index_name, table_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_ops_lab'
  AND table_name = 'events_2i';

-- Bảng gốc vẫn còn và query theo partition key vẫn chạy được.
SELECT event_time, status, temperature
FROM index_ops_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

**Sau khi schema đã hội tụ**, câu query chỉ biết `status='WARN'` trên `events_2i` thường trở lại lỗi vì không có index. Đây là hành vi **dự kiến trong lab**, không phải mất dữ liệu:

~~~sql
-- Phép thử âm: query này cần index/phương án truy vấn khác.
SELECT device_id, event_time, status
FROM index_ops_lab.events_2i
WHERE status = 'WARN';
~~~

Đối với nhánh SAI riêng, nếu cần thử drop ở Cassandra 5.x:

~~~sql
-- Chỉ sau khi đã ghi nhận metadata và kiểm tra tác động.
DROP INDEX IF EXISTS index_ops_lab.events_sai_temperature_idx;

-- Index trên status vẫn tồn tại; truy vấn status-only vẫn được hỗ trợ.
SELECT device_id, event_time, status
FROM index_ops_lab.events_sai
WHERE status = 'WARN';
~~~

**Không kết luận** câu `WHERE status='WARN' AND temperature>=30` vẫn có hiệu quả/được phép như trước, vì một điều kiện không còn index. Trên bản Cassandra 5.x, planner có thể yêu cầu filtering hoặc trả `InvalidRequest`. Không tự thêm `ALLOW FILTERING` để giữ service hoạt động mà chưa đo chi phí.

### 9.3. Rollback không phải là “IF NOT EXISTS” thần kỳ

Nếu drop nhầm index hoặc cần quay lại:

1. Dùng bản ghi `CREATE INDEX` cũ và **đúng implementation/options**.
2. Xác nhận không có index cùng tên nhưng khác cấu hình.
3. Tạo lại index và chờ schema agreement + build/queryable.
4. Kiểm tra kết quả theo primary key, một vài giá trị indexed và CL.
5. Chỉ sau khi đủ điều kiện mới chuyển traffic trở lại.

Đặt `IF NOT EXISTS` vào câu create lại **không khôi phục ngay dữ liệu index**. Index cần build lại cho các row đã tồn tại; với cluster lớn có thể tạo tải đáng kể.

## 10. Khi nào dùng nodetool rebuild_index?

Với 2i/native secondary index, Cassandra có lệnh quản trị:

~~~bash
# CHỈ minh họa; không chạy ngoài lab/runbook được duyệt.
# Cú pháp: nodetool rebuild_index <keyspace> <table> <indexName...>
nodetool rebuild_index index_ops_lab events_2i events_2i_status_idx
~~~

Lệnh có thể thực hiện **hot rebuild của native secondary index** trên node được `nodetool` liên hệ. Vì `nodetool` dùng kênh quản trị/JMX (thường 7199 nếu được cấu hình), nó **khác native CQL port 9042**.

**Không dùng `rebuild_index` như bước mặc định sau `CREATE INDEX`**. Cassandra đã có cơ chế build tự động. Chỉ cân nhắc rebuild khi có bằng chứng index node-local lỗi/mất đồng bộ và runbook đúng phiên bản cho phép. Rebuild có chi phí CPU/disk/compaction; cần kế hoạch từng node, giám sát, dung lượng, khả năng tải và rollback.

Cũng cần phân biệt:

- **`nodetool repair`**: đồng bộ **dữ liệu replica** theo token ranges/anti-entropy.
- **`nodetool rebuild_index`**: xây lại **native secondary index** trên node cụ thể.
- **`nodetool compact`**: chạy compaction SSTable theo thao tác được hỗ trợ.
- **`DROP/CREATE INDEX`**: thay đổi **schema index** (và khởi tạo/loại bỏ cấu trúc index), có thể ảnh hưởng query client.

Không thay thế lẫn nhau vì thấy một câu `SELECT` trả `ReadTimeout`.

## 11. Vì sao trạng thái sẵn sàng phải xét cả RF, CL và topology?

Giả sử cluster có một datacenter, RF = 3. Với `LOCAL_QUORUM`, mỗi request đọc/ghi thông thường cần số phản hồi từ **quorum replica trong local DC** (thường 2 khi RF=3). Tuy nhiên, query secondary index **không có partition key** có thể tìm trên nhiều token ranges/nhiều node: số node cần phục vụ công việc tìm index có thể **khác** số replica cần cho một partition.

Một node đã có `is_queryable=true` có thể không đại diện cho các node còn lại. Khi một query index phân tán chạy:

- Coordinator phải tìm dữ liệu ở những node/phạm vi thích hợp.
- Nếu một replica không khả dụng, `Unavailable` hoặc timeout có thể xuất hiện tùy CL và trạng thái cluster.
- Nếu SAI chưa queryable trên node cần thiết, query có thể thất bại/chưa dùng được đường index.
- Nếu chỉ xem kết quả tại một node, bạn có thể bỏ sót hiện tượng build chưa xong ở node khác.
- Nếu ứng dụng Java khám phá peers và route request tới nhiều coordinator, kiểm tra đúng native endpoints và local DC.

**Quy tắc triển khai:** với cluster nhiều node, cần **gắn trạng thái index với node, keyspace, index name và thời gian kiểm tra**. Không gộp “một query chạy được” thành “mọi replica đã hoàn tất”.

## 12. Runbook vận hành CREATE → READY → SWITCH → DROP

| Pha | Công việc | Điều kiện qua cổng (gate) |
| --- | --- | --- |
| **Trước CREATE** | Chốt query pattern, server versions, DC/RF/CL, schema, index type, dung lượng, người sở hữu dịch vụ | Có mô hình dữ liệu, quyền DDL và kế hoạch thay đổi hợp lệ. |
| **CREATE** | Chạy CQL đúng implementation, tên duy nhất; ghi timestamp/log DDL | Không có lỗi permission/type/guardrail. |
| **SCHEMA** | Kiểm tra `system_schema.indexes` và schema agreement | Các node đã nhận đúng định nghĩa; không có index sai loại. |
| **BUILD** | Kiểm tra logs/build; với SAI kiểm tra `system_views.indexes` theo node | Index queryable tại các node cần thiết, không còn lỗi build. |
| **VALIDATE** | Đối chiếu indexed query với truy vấn theo primary key/dataset gốc | Không thiếu/sai row; các kiểu update/delete/TTL quan trọng được thử. |
| **LOAD TEST** | Thử phân bố khóa, selectivity phổ biến/hiếm, p95/p99, CPU/GC, disk/compaction, network | Không vượt SLO, không tạo quá tải/timeout bất thường. |
| **SWITCH** | Bật query mới theo feature flag/canary | Metric và lỗi client chấp nhận được; có rollback. |
| **DROP OLD** | Chứng minh không còn dependency rồi xóa index cũ | Query mới ổn định, schema được backup, có kế hoạch khôi phục. |
| **POSTCHECK** | Kiểm tra schema, kết nối client, query errors và disk metrics | Hệ thống ổn định, ghi lại kết quả và bài học. |

### 12.1. Quan sát tải trong pha build

| Nhóm metrics | Điều cần theo dõi |
| --- | --- |
| **Index state** | `is_building`/`is_queryable` ở SAI, logs 2i, lỗi index build. |
| **CPU/GC** | Tăng tải do xây index/scan SSTable, pause time và queue. |
| **Disk** | Dung lượng trống, index size, write/read I/O, compaction backlog. |
| **Native latency** | p50/p95/p99 read/write, timeout/retry, request throughput. |
| **Internode** | Message/bytes, node down hoặc mạng mất gói. |
| **Consistency** | RF/CL, `Unavailable`, `ReadTimeout`, `WriteTimeout`. |
| **Data correctness** | Query theo primary key vs index query, sample trên partition/key khác nhau. |

Không dùng một ngưỡng cố định “index build luôn xong sau N phút” áp dụng mọi cluster. Mục tiêu là **điều kiện readiness đo được**, không phải đợi đủ thời gian ước lượng.

## 13. Java Driver 4.x: ứng dụng nên xử lý thay đổi index ra sao?

Ứng dụng Java gửi CQL qua native protocol; **index là đối tượng schema phía server**, không phải driver tự tạo khi dùng prepared statement. Đoạn dưới giả định lab `events_sai` trên Cassandra 5.x **đã queryable**, hoặc có thể thay bằng bảng `events_2i` với index đang hoạt động.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;

public final class CassandraIndexReadinessDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement byIndex = session.prepare(
                "SELECT device_id, event_time, status, temperature " +
                "FROM index_ops_lab.events_sai WHERE status = ?");

            BoundStatement query = byIndex.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int rowCount = 0;
            for (Row row : session.execute(query)) {
                rowCount++;
                System.out.println(row.getString("device_id") + " : " +
                    row.getDouble("temperature"));
            }
            System.out.println("matching_rows=" + rowCount);
        } catch (RuntimeException error) {
            // Không log password/token/bind values bí mật.
            System.err.println("query_failed_type=" +
                error.getClass().getName());
            throw error;
        }
    }
}
~~~

**Điều kiện:**

- `events_sai` chỉ tồn tại ở nhánh Cassandra 5.x đã tạo; dùng đúng `events_2i` và index legacy nếu làm lab Cassandra 4.x.
- `datacenter1` là ví dụ; lấy tên DC thực từ `SELECT data_center FROM system.local;`.
- Mẫu không chứa TLS/credentials vì giả định lab local không bật auth. Ở hệ thực, phải cấu hình SSL/CA, authentication, contact points và quyền CQL.
- `setConsistencyLevel(ONE)` và `setTimeout(5s)` là cấu hình statement để minh họa, **không phải mặc định production**.
- `setPageSize(100)` chỉ quy định page size, không chứng minh tổng số row cần tìm hay fan-out trên cluster chỉ là 100.
- `PreparedStatement` có thể bị ảnh hưởng bởi schema change; sau drop, query chỉ dựa vào indexed column có thể bị từ chối lúc prepare hoặc execute. Không retry vô hạn cùng câu query.

### 13.1. Tránh race condition lúc rollout

Nếu service deploy phiên bản mới **trước** khi index đã queryable, request có thể thất bại ngay cả khi schema đã có tên index. Quy trình an toàn:

1. Có **feature flag** để query mới chưa được gửi tự động.
2. DBA/operator hoàn tất schema/build/readiness trên node liên quan.
3. Chạy smoke test đúng identity/TLS/CL của ứng dụng và so dữ liệu gốc.
4. Bật canary traffic, quan sát error rate và latency.
5. Mở traffic dần khi kết quả ổn định.

Sau khi drop index cũ, chỉ bật lại query phụ thuộc nó khi đã **tạo lại và hoàn tất build**, không chỉ vì người vận hành đã chạy `CREATE INDEX`.

## 14. Chẩn đoán lỗi theo giai đoạn

| Triệu chứng | Lớp vấn đề | Cách kiểm tra |
| --- | --- | --- |
| `CREATE INDEX` bị `SyntaxException` | Cú pháp/version | `SHOW VERSION`, tên index/`USING` và tài liệu bản server. |
| `InvalidRequest: index already exists` | DDL/tên index | Index name unique trong keyspace; đọc metadata trước khi dùng `IF NOT EXISTS`. |
| `CREATE INDEX ... USING 'sai'` không được nhận trên 4.x | Tính năng không có | SAI upstream tích hợp từ 5.0; dùng 2i hoặc thiết kế bảng theo truy vấn. |
| `Unauthorized` khi CREATE/DROP | Quyền DDL | Kiểm tra role/authorizer, không tắt authentication. |
| Index có trong `system_schema.indexes` nhưng query không chạy | Build chưa sẵn sàng hoặc type không phù hợp | Với SAI đọc `system_views.indexes` theo node; với 2i đọc logs/build. |
| `is_building=false, is_queryable=false` | SAI chưa thể phục vụ query | Xem server logs, disk, build failure, node health; không coi là READY. |
| Index query dùng được ở node A nhưng lỗi ở B | Readiness không đồng nhất hoặc schema/topology khác | Kiểm tra từng node, schema agreement, version, cluster health. |
| Query sau drop trả `InvalidRequest` | Thiếu đường truy cập indexed | Xác nhận client còn query cũ; chuyển sang data model khác hoặc rollback. |
| `ReadTimeout` / `DriverTimeoutException` | Replica/fan-out/overload | Xem CL/RF, network, index selectivity, CPU/disk/compaction, retries. |
| `Unavailable` | Không đủ replica khả dụng theo CL | `nodetool status`, replication, DC, mạng internode. |
| `AllNodesFailedException` trong Java | Kết nối native chưa thành công | DNS, port 9042, TLS/auth, contact points, local DC; không quy lỗi cho index nếu chưa kết nối. |
| Query status phổ biến chậm dù SAI queryable | Selectivity thấp, nhiều kết quả | Đo số row khớp, p95/p99 và chi phí; cân nhắc bảng query-oriented. |
| DDL bị guardrail chặn | Hạn chế vận hành/feature | Kiểm tra default index type, số index/bảng, loại cột và policy theo version. |

### 14.1. Hai lỗi thường bị nhầm

**“Tôi thấy index trong DESCRIBE nên nó sẵn sàng”** — chưa đủ: `DESCRIBE` phản ánh schema, không phải trạng thái local index build trên mọi node.

**“DROP INDEX xong vẫn SELECT theo partition key được nên không ảnh hưởng app”** — chưa đủ: chỉ những query không dựa vào index mới tiếp tục được đảm bảo; các API dùng `WHERE status=?` có thể trả lỗi ngay khi schema thay đổi.

## 15. Bài tập thực hành

1. Phân biệt primary index, 2i và SAI. Tại sao không dùng `CREATE INDEX` cho primary key?
2. Tạo `index_ops_lab.events_2i`, nạp bốn row **trước** khi tạo index, thử query `status='WARN'` và ghi nhận lỗi.
3. Chạy `CREATE INDEX` legacy theo đúng phiên bản. Dùng `system_schema.indexes.kind/options` để xác minh thực sự đã tạo loại nào.
4. Giải thích ba trạng thái **schema tồn tại**, **schema agreement**, **index build/queryable** và vì sao chúng không phải một.
5. Sau khi 2i hoàn tất build, query `status='WARN'`: dự đoán hai row. Ghi thêm `sensor-04 WARN` rồi kiểm tra index duy trì ra sao.
6. Cập nhật `sensor-02 WARN→OK`. Dùng truy vấn theo primary key và index để đối chiếu, thảo luận write amplification/tombstone.
7. Trên Apache Cassandra 5.0+ lab, tạo bảng `events_sai`, tạo hai SAI index; kiểm tra `is_building`/`is_queryable` qua `system_views.indexes`.
8. Tại sao `is_queryable=true` trên một node không chứng minh toàn cluster sẵn sàng? Đề xuất cách lấy trạng thái có nhãn node.
9. Dùng SAI query `status='WARN' AND temperature>=30`. Kiểm tra row mong đợi và giải thích hai index theo cột phối hợp.
10. Thử `DROP INDEX` của lab 2i, xác nhận bảng/data không mất và query theo `status` thất bại đúng dự kiến.
11. Trình bày kế hoạch rollback nếu vừa drop một index production vẫn có service phụ thuộc: nêu cách ngừng query lỗi, tạo lại index, chờ build và xác minh.
12. So sánh `nodetool rebuild_index`, `nodetool repair` và `DROP/CREATE INDEX`. Vì sao không thể thay thế chúng tùy tiện?
13. Lập checklist vận hành trước CREATE index trên bảng có hàng chục triệu row: dung lượng, số node, CL/RF, maintenance window, metrics, retries.
14. Dùng Java Driver 4.x với prepared `WHERE status=?`, giải thích tại sao client cần chờ rollout readiness trước khi bật query mới.
15. Vẽ một quy trình CI/CD hoặc change-management có **CREATE → BUILD → VERIFY → CANARY → SWITCH → DROP OLD**, nêu điều kiện qua cổng từng pha.

**Tiêu chí hoàn thành:** biết tạo/xóa index đúng type và phiên bản, đọc schema metadata, hiểu rõ build không đồng nghĩa schema agreement, kiểm tra SAI queryability theo node và 2i bằng build/log/query validation, đồng thời có quy trình chuyển traffic/rollback an toàn mà không làm mất bảng hoặc gây lỗi truy vấn bất ngờ.

## Tài liệu tham khảo chính thức

- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-index.html): cú pháp index, `IF NOT EXISTS`, `USING 'sai'` và giới hạn kiểu dữ liệu.
- [Apache Cassandra — DROP INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/drop-index.html): cú pháp `DROP INDEX IF EXISTS keyspace.index`.
- [Apache Cassandra — Secondary Indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexes.html): loại index, build async và `legacy_local_table`.
- [Apache Cassandra — Rebuilding and maintaining 2i](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/operations/2i-build.html): background build và hot rebuild qua nodetool.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): SAI gắn với memtable/SSTable và query planner.
- [Apache Cassandra — Monitor SAI indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/operations/monitoring.html): ý nghĩa `is_queryable`, `is_building` và trạng thái node-local.
- [Apache Cassandra — SAI virtual tables](https://cassandra.apache.org/doc/stable/cassandra/reference/sai-virtual-table-indexes.html): cấu trúc `system_views.indexes` và index metrics.
- [Apache Cassandra — nodetool rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html): cú pháp rebuild index và phạm vi node.
- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): khi chọn primary/2i/SAI.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): session, prepared statement, consistency, timeout và metadata.
