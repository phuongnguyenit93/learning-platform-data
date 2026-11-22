# Đối chiếu 2i, SASI và SAI theo phiên bản, trạng thái hỗ trợ

## 1. Vì sao cần kiểm tra phiên bản trước khi chọn index?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**, tối ưu cho các truy vấn có thể định vị dữ liệu qua **partition key**, sau đó lọc/duyệt các **clustering columns** trong partition. Trong thực tế, ứng dụng cũng cần tìm dữ liệu theo những cột khác khóa chính, ví dụ `status = 'WARN'`, `temperature >= 30` hoặc tên bắt đầu bằng một tiền tố.

Ba tên rất dễ bị nhầm:

- **2i**: *legacy secondary index*, chỉ mục phụ truyền thống, duy trì ở mỗi node dưới dạng bảng index ẩn cục bộ.
- **SASI**: *SSTable-Attached Secondary Index*, một triển khai chỉ mục tùy biến có cấu trúc gắn với SSTable, từng hỗ trợ truy vấn tiền tố/chuỗi con và range, nhưng **được Apache Cassandra xếp là tính năng thử nghiệm, không khuyến nghị production**.
- **SAI**: *Storage-Attached Indexing*, cơ chế index hiện đại được tích hợp trong **Apache Cassandra 5.0**, với read/write path gắn vào memtable/SSTable và khả năng lập kế hoạch nhiều index.

**SASI và SAI không phải hai cách viết của cùng một feature.** SASI là mã triển khai `org.apache.cassandra.index.sasi.SASIIndex` có các chế độ như `PREFIX`, `CONTAINS` và `SPARSE`. SAI là triển khai mới có cơ chế index/query khác, được tạo với `USING 'sai'` trên những bản Cassandra hỗ trợ. Cũng không thể giả định mọi tính năng SASI, nhất là `LIKE '%...%'`, tồn tại trong SAI.

Bài thuộc chương **Chỉ mục** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Việc chọn index ảnh hưởng trực tiếp đến mô hình bảng theo truy vấn, lượng dữ liệu phân vùng, độ trễ coordinator/replica, replication/consistency, compaction/repair và cách ứng dụng Java gửi CQL.

**Sau bài học, bạn có thể:**

1. Đọc ma trận phiên bản và phân biệt **có mã nguồn**, **tạo được index**, **được khuyến nghị** và **được hỗ trợ production**.
2. Nêu khác biệt kiến trúc, toán tử và giới hạn của **2i, SASI, SAI**.
3. Tạo/kiểm tra 2i trên lab phổ thông; chạy ví dụ SAI **chỉ trên Cassandra 5.x phù hợp**; nhận biết yêu cầu opt-in và rủi ro SASI.
4. Giải thích chi phí fan-out khi thiếu partition key và lý do một index không thay thế thiết kế bảng theo truy vấn.
5. Kiểm tra loại index thực tế qua `system_schema.indexes`, phiên bản server và cấu hình thay vì đoán từ tên.
6. Lập kế hoạch chuyển từ 2i/SASI sang SAI hoặc bảng truy vấn mới với tiêu chí correctness, latency, data consistency và rollback.
7. Viết Java Driver prepared statements đúng query shape mà không phụ thuộc các giả định sai về hỗ trợ index.

## 2. Hiểu đúng chữ “hỗ trợ”

Một tính năng có thể **tồn tại trong mã nguồn**, có trang hướng dẫn và vẫn **không được khuyến nghị cho môi trường sản xuất**. Vì vậy, cần tách ít nhất bốn trạng thái:

| Trạng thái | Câu hỏi cần xác minh | Ý nghĩa |
| --- | --- | --- |
| **Có implementation** | JAR/class/loại index có trong bản server không? | Chưa chứng minh tính năng đã được bật hoặc ổn định. |
| **Cho phép tạo** | CQL, `cassandra.yaml`, guardrail và quyền DDL có cho tạo index không? | Có thể chạy lab, chưa chắc được phép triển khai production. |
| **Có hướng dẫn sử dụng** | Tài liệu đúng **phiên bản và bản phân phối** mô tả gì? | Tài liệu có thể dành cho thử nghiệm hoặc legacy compatibility. |
| **Được hỗ trợ vận hành** | Nhà cung cấp/bản phân phối có cam kết support, upgrade, backup, repair, rebuild không? | Phải kiểm tra chính sách của chính hệ thống đang dùng. |

**Đặc biệt với SASI:** trang tài liệu của Apache Cassandra vẫn mô tả `SASIIndex`, nhưng cấu hình `sasi_indexes_enabled` được ghi rõ là **experimental** và **not recommended for production use**. Sự có mặt của một trang tài liệu SASI không có nghĩa đây là phương án đầu tư mới an toàn.

### 2.1. Ma trận thực hành cho Apache Cassandra

| Phiên bản Apache Cassandra | Primary indexing | 2i legacy | SASI | SAI |
| --- | --- | --- | --- | --- |
| **3.11** | Có | Có | Có triển khai SASI trong các nhánh 3.x liên quan; cần kiểm tra cấu hình/bản build và chính sách thử nghiệm | **Không có SAI tích hợp như Apache 5.0** |
| **4.0** | Có | Có | SASI là feature thử nghiệm; kiểm tra khả năng bật/cấu hình của chính bản vá | **Không có SAI tích hợp như Apache 5.0** |
| **4.1** | Có | Có | `sasi_indexes_enabled` được tài liệu ghi **mặc định false**, tính năng thử nghiệm, không khuyến nghị production | **Không có SAI tích hợp như Apache 5.0** |
| **5.0** | Có | Có cho tương thích legacy | Còn tài liệu/triển khai SASI, nhưng bị đánh dấu thử nghiệm; mặc định không bật trong cấu hình được tài liệu hóa | **Có SAI tích hợp**, là hướng lựa chọn được ưu tiên cho nhiều truy vấn secondary indexing |

Ma trận này nói về **Apache Cassandra upstream**, không thay thế bảng tương thích của DataStax Enterprise, Astra DB, ScyllaDB, fork nội bộ hay một dịch vụ managed Cassandra-compatible khác. Một sản phẩm có thể cung cấp SAI trước Cassandra 5.0 hoặc có cú pháp/hạn chế riêng: **không suy phiên bản feature chỉ từ việc API có tên Cassandra**.

Đối với các phiên bản mới hơn/nhánh thử nghiệm, phải đọc tài liệu release cụ thể tại thời điểm vận hành. Không suy luận một tính năng “5.0 có” sẽ được giữ nguyên option/default/syntax mãi mãi.

### 2.2. Đừng suy loại index chỉ từ `CREATE INDEX`

Trên Cassandra 5.x, cấu hình như `default_secondary_index` có thể quyết định implementation khi câu `CREATE INDEX` **không viết `USING`**. Cấu hình tương thích thường mô tả loại `legacy_local_table`, trong khi một cluster được cấu hình khác có thể chọn loại mặc định khác.

Vì vậy:

- Nếu muốn **tài liệu hóa 2i**, kiểm tra loại index sau tạo và mặc định của cluster; trên các bản hỗ trợ, khai báo rõ implementation khi cần.
- Nếu muốn **SAI**, ghi `USING 'sai'` trong CQL và xác minh bản Cassandra có hỗ trợ.
- Nếu muốn nghiên cứu **SASI**, chỉ chạy `CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex'` trên lab đã xác nhận opt-in được phép.
- `IF NOT EXISTS` không xác nhận index đã tồn tại **đúng loại và options**; luôn đọc lại metadata.

## 3. So sánh kiến trúc: dữ liệu được index nằm ở đâu?

~~~mermaid
flowchart TB
    APP["Java Driver / cqlsh"] --> CO["Coordinator: phân tích query"]
    CO --> R["Replica/node chịu trách nhiệm"]
    R --> BASE["Base table: memtable + SSTables"]
    R --> I2["2i: hidden local index table"]
    R --> IS["SASI: chỉ mục gắn SSTable / memtable"]
    R --> IA["SAI 5.x: index gắn SSTable + memtable"]
    I2 -.->|"Tra primary key ứng viên"| BASE
    IS -.->|"Tra primary key ứng viên"| BASE
    IA -.->|"Tra primary key ứng viên"| BASE
~~~

Sơ đồ là **minh họa ba nhánh triển khai có thể chọn**, không có nghĩa một bảng nên bật cả ba loại index cùng lúc. Trong lab bên dưới, mỗi loại dùng **bảng riêng** để tránh xung đột và làm rõ hiệu quả.

### 3.1. Legacy 2i: bảng index ẩn trên từng node

2i được Cassandra duy trì cục bộ ở mỗi node có dữ liệu bảng cơ sở. Node dùng index để tìm key ứng viên, rồi có thể phải đọc/xác minh row trong bảng gốc. Vì index không tập trung, truy vấn **chỉ biết cột secondary** nhưng **không có partition key** có thể làm coordinator tìm trên nhiều node/token ranges.

Điểm cần nhớ:

- 2i vẫn là index phân tán về **phạm vi truy vấn**, dù cấu trúc được lưu **cục bộ trên các node**.
- Giá trị rất phổ biến như `status='OK'` có thể có tập khớp khổng lồ.
- Cột update/delete thường xuyên tạo thêm index maintenance/tombstones.
- Tài liệu Apache ưu tiên dùng 2i **khi đã biết partition key**, không xem 2i là giải pháp tổng quát thay primary-key query.

### 3.2. SASI: triển khai index theo SSTable nhưng vẫn thử nghiệm

SASI (*SSTable-Attached Secondary Index*) được viết dưới dạng custom index, tận dụng cấu trúc trên memtable/SSTable và các on-disk index chuyên cho tra cứu. Tài liệu mô tả các mode:

| Mode SASI | Ý tưởng truy vấn | Cảnh báo |
| --- | --- | --- |
| `PREFIX` | Tiền tố của một giá trị text, ví dụ `LIKE 'Over%'` | Phụ thuộc analyzer/case sensitivity và implementation. |
| `CONTAINS` | Tìm chuỗi con/suffix theo khả năng của analyzer, ví dụ `LIKE '%heat%'` | Có thể tăng footprint, không tương đương full-text search. |
| `SPARSE` | Tối ưu trường hợp phù hợp với dữ liệu số/dải giá trị đặc thù | Không phải tùy chọn tăng tốc mọi truy vấn range. |

SASI có thể hỗ trợ một số kiểu query mà 2i không phục vụ thuận tiện, nhưng điều này **không xóa nhãn experimental**. Một query nhanh trên lab 100 row không chứng minh SASI phù hợp production về ổn định, tính đúng đắn khi xóa/update, streaming, rebuild, upgrades hoặc hỗ trợ lâu dài.

**Kết luận vận hành:** hãy xem SASI là **legacy/experimental feature để hiểu hoặc duy trì hệ cũ**, không là lựa chọn mặc định cho thiết kế mới của Apache Cassandra.

### 3.3. SAI: cơ chế mới tích hợp với storage engine

Trong Apache Cassandra 5.0, SAI lập index trên memtable và SSTable theo từng cột, giữ các index data ở cùng node với dữ liệu. Khi query, coordinator có thể tổ chức distributed range reads, đánh giá selectivity và các replica có thể **kết hợp điều kiện từ nhiều SAI indexes**.

Ưu điểm theo tài liệu SAI:

- Index gắn với vòng đời **flush/compaction** của SSTable, không đơn thuần là hidden table riêng như 2i.
- Hỗ trợ **equality và range** trên những kiểu được công bố; cho phép nhiều predicate indexed trong một truy vấn phù hợp.
- Có đường quan sát **index build state/metrics**, cơ chế streaming và rebuild gắn với vận hành cluster.
- Hỗ trợ nhiều kiểu cột như số, text, UUID, date/timestamp và collection theo quy tắc riêng của SAI.

**Không nên suy:** “SAI không tốn write amplification”, “SAI đảm bảo mọi query đều 1 node”, hay “SAI thay Elasticsearch/lucene cho mọi loại tìm kiếm”. SAI vẫn tiêu tốn CPU/RAM/disk, index build và distributed coordination; nó là **filtering/indexing engine**, không tự tạo một trật tự toàn cục cho kết quả.

## 4. Ma trận khả năng truy vấn: ba loại không tương đương

| Nhu cầu | 2i | SASI | SAI Apache 5.x | Gợi ý |
| --- | --- | --- | --- | --- |
| `status = 'WARN'` | Có với cột được index | Có khi feature được bật | Có | Ưu tiên primary key/bảng theo truy vấn; SAI nếu cần secondary filter trên 5.x. |
| `temperature >= 30.0` | Không xem 2i là giải pháp range tổng quát | Có chế độ numeric/range tùy cấu hình | Có range numeric | Xác minh kiểu cột/operator bằng version. |
| `note LIKE 'Over%'` | Không phải khả năng của 2i cơ bản | Có thể bằng SASI PREFIX | **SAI không hỗ trợ LIKE** | Tránh giả định chuyển SASI → SAI giữ nguyên query text. |
| `note LIKE '%heat%'` | Không phải khả năng của 2i cơ bản | Có thể bằng SASI CONTAINS | **SAI không hỗ trợ LIKE** | Nếu cần substring/full-text thực sự, đánh giá search engine hoặc mô hình khác. |
| `status='WARN' AND temperature>=30` | Phối hợp nhiều 2i bị hạn chế, có thể cần filtering | Có thể có compound predicates, phụ thuộc cú pháp/options | SAI có thể kết hợp nhiều SAI indexes | Benchmark selectivity và số kết quả trả về. |
| Tìm theo partition key + clustering range | **Primary index đã đủ** | Không cần | Không cần | Tránh thêm index vô ích. |
| Top-N có thứ tự **toàn cluster** | Không tự giải quyết | Không tự giải quyết | Không tự giải quyết | Cần bảng/bucket/index ordering hoặc tầng tổng hợp riêng. |
| Quét/aggregate gần như toàn bộ bảng | Không phải workload lý tưởng | Không phải workload lý tưởng | Không phải workload lý tưởng | Dùng batch analytics/ETL hoặc bảng tổng hợp. |

Các giới hạn trên chỉ mô tả **tập tính năng tiêu biểu**. Chẳng hạn text tokenization/analyzer, collection `CONTAINS`, `IN`, AND/OR và vector search phụ thuộc bản CQL/SAI và loại dữ liệu cụ thể. Không dùng sự có mặt của từ `CONTAINS` trong collection CQL để suy rằng SAI hỗ trợ **substring text** kiểu SASI `LIKE '%...%'`.

### 4.1. Cardinality và selectivity quan trọng hơn tên index

Giả sử bảng có 10 triệu row:

- `status='OK'` khớp **9,8 triệu row**: index có thể dẫn đến khối lượng kết quả/đọc rất lớn.
- `status='WARN'` khớp **200 row**: index có cơ hội giúp thu hẹp tốt hơn, nhưng coordinator có thể vẫn cần tìm ở nhiều vùng dữ liệu.
- `request_id` gần như duy nhất: nếu đây là đường truy vấn chủ đạo, **partition key** trực tiếp thường dễ dự đoán chi phí hơn 2i trên UUID.
- `note LIKE '%error%'`: nếu tìm kiếm text tự do là core workflow, cần phân tích riêng ngữ nghĩa tokenizer, ranking, language và update rate.

Không có ngưỡng “low cardinality luôn thích hợp cho 2i” hoặc “SAI luôn nhanh với mọi selectivity”. Hãy đo **matching fraction từng giá trị**, số row trả về, p95/p99, network fan-out, size và write/update overhead.

## 5. Trước khi viết DDL: xác minh phiên bản và cấu hình

### 5.1. Xem phiên bản server/cqlsh

Từ terminal nơi có cqlsh:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

`SHOW VERSION` hiển thị phiên bản cqlsh/server/CQL/native protocol được kết nối. `release_version` từ `system.local` là phiên bản **node đang phục vụ câu SELECT**, không chứng minh mọi node trong cluster đã cùng phiên bản khi rolling upgrade.

### 5.2. Xem index metadata trong schema

~~~sql
-- Chạy sau khi tạo keyspace/bảng/index của lab ở các phần tiếp.
SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab';
~~~

`kind` và `options` cho biết thông tin implementation/index options mà Cassandra ghi trong schema; **cách biểu diễn khác nhau theo version**. Không dựa duy nhất vào tên `status_idx` hoặc `IF NOT EXISTS` để khẳng định một index là 2i hay SAI.

### 5.3. Kiểm tra `cassandra.yaml` và guardrails

| Mục cần xem | Vấn đề cần xác minh |
| --- | --- |
| `sasi_indexes_enabled` | Trong tài liệu Cassandra 4.1/5.0: SASI experimental, mặc định **false**, không khuyến nghị production. |
| `default_secondary_index` | Ở phiên bản hỗ trợ: khi không viết `USING`, tạo 2i hay SAI? |
| `default_secondary_index_enabled` | Cluster có chấp nhận `CREATE INDEX` không `USING` hay bắt buộc khai báo implementation? |
| SAI guardrails | Số SAI indexes/bảng, indexable types/options, query limits và nguồn tài nguyên. |
| DDL permissions | Role có `CREATE` trên keyspace/index resource liên quan không? |
| Mixed versions | Tất cả node đã hoàn tất nâng cấp, hiểu index type và schema mới chưa? |

Không cần và không nên **bật SASI chỉ vì bài học đưa ra ví dụ**. Nếu tổ chức không cho phép, hãy đọc phần SASI như **lý thuyết**, chỉ chạy lab 2i hoặc SAI. Việc thay `cassandra.yaml`/rolling restart nằm ngoài phạm vi bài học và phải có quy trình vận hành phê duyệt.

## 6. Lab cơ sở: bảng và dữ liệu giống nhau để đối chiếu

**Điều kiện an toàn:** cluster lab độc lập, không có dữ liệu sản xuất. Các ví dụ tạo keyspace RF=1 và dùng `SimpleStrategy` chỉ để dễ thực hành **một node**; chúng không mô phỏng replication nhiều datacenter hoặc chịu lỗi.

Tạo keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS index_versions_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};
~~~

Mẫu dữ liệu được dùng có:

| record | device_id | event_day | event_time UTC | status | temperature | note |
| --- | --- | --- | --- | --- | ---: | --- |
| 1 | sensor-01 | 2026-11-21 | 01:00 | OK | 24.2 | Normal |
| 2 | sensor-01 | 2026-11-21 | 01:05 | WARN | 30.8 | Overheat motor |
| 3 | sensor-02 | 2026-11-21 | 01:03 | WARN | 28.5 | Overflow pump |
| 4 | sensor-03 | 2026-11-21 | 01:07 | WARN | 31.2 | Overheat valve |

**Kỳ vọng chức năng:** `status='WARN'` khớp 3 record, còn `status='WARN' AND temperature >= 30` khớp 2 record (sensor-01 và sensor-03). Không suy ra thứ tự toàn cục của những record thuộc các partition khác nhau.

### 6.1. Định nghĩa bảng dùng cho 2i

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_2i (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Trong bảng này, `(device_id, event_day)` là **composite partition key**; `event_time`, `event_id` là clustering columns. `status`, `temperature`, `note` là regular columns; nếu chưa có index, không thể kỳ vọng lọc theo các cột này trên mọi partition với chi phí kiểu point lookup.

### 6.2. Nạp bốn row với primary key cố định

~~~sql
INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111,
        'OK', 24.2, 'Normal');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222,
        'WARN', 30.8, 'Overheat motor');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333,
        'WARN', 28.5, 'Overflow pump');

INSERT INTO index_versions_lab.events_2i
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444,
        'WARN', 31.2, 'Overheat valve');
~~~

UUID/timestamps cố định giúp chạy lại là **upsert** cùng primary key, không tạo row mới. Nếu bảng đã tồn tại khác schema, `IF NOT EXISTS` không sửa định nghĩa; kiểm tra `DESCRIBE TABLE` trước khi chạy. Nếu lab có các row cũ không thuộc fixture, tổng số row có thể khác; chỉ reset data trên **lab độc lập** theo chính sách an toàn.

Kiểm tra baseline **không dùng secondary index**:

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, temperature
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Kỳ vọng hai row của `sensor-01`, `01:05 WARN` rồi `01:00 OK`. Đây là mô hình truy vấn ưu tiên khi application có partition key.

## 7. Nhánh lab A: legacy 2i (phổ biến trên các phiên bản)

### 7.1. Tạo index và xác minh loại

~~~sql
-- Trên Cassandra 4.x: CREATE INDEX đơn giản thường là 2i legacy.
-- Trên 5.x: kiểm tra default_secondary_index; không đoán chỉ từ DDL.
CREATE INDEX IF NOT EXISTS events_2i_status_idx
ON index_versions_lab.events_2i (status);

DESCRIBE TABLE index_versions_lab.events_2i;

SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_2i';
~~~

Nếu Cassandra 5.x được cấu hình `default_secondary_index: sai` hoặc yêu cầu `USING` tường minh, câu lệnh trên **không còn bảo đảm là 2i**. Với phiên bản hỗ trợ khai báo loại index:

~~~sql
-- CHỈ dùng nếu bản Cassandra hỗ trợ tên implementation này,
-- và chỉ trên bảng lab riêng chưa có index trùng tên/cột.
-- Cú pháp tham khảo cho Apache Cassandra 5.x:
CREATE INDEX IF NOT EXISTS explicit_legacy_status_idx
ON index_versions_lab.events_2i (status)
USING 'legacy_local_table';
~~~

**Chọn một trong hai cách tạo index**, không chạy cả hai trên cùng một cột chỉ để “chắc chắn”. Nếu đã tạo loại sai, xác minh type trước, `DROP INDEX` đúng index lab và tạo lại theo quy trình có kiểm soát.

### 7.2. Truy vấn qua index cục bộ

~~~sql
SELECT device_id, event_day, event_time, status, temperature
FROM index_versions_lab.events_2i
WHERE status = 'WARN';
~~~

Sau khi index xây dựng xong trên dữ liệu đã có, kỳ vọng **3 row**, có thể theo thứ tự khác nhau giữa các lần/cluster. Trong cluster nhiều node, coordinator có thể phải truy vấn nhiều local indexes; số row trả về thấp **không bảo đảm** tổng số message/network thấp.

Kiểm tra một partition kèm index predicate:

~~~sql
SELECT event_time, status
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND status = 'WARN';
~~~

Việc có full partition key thu hẹp phạm vi một cách rõ ràng. Nếu planner/bản Cassandra yêu cầu lọc bổ sung, cần đối chiếu rules và xem query chỉ theo partition key rồi filter một tập nhỏ ở ứng dụng. Không thêm `ALLOW FILTERING` tùy tiện trong production.

### 7.3. Giới hạn của 2i

- `status='WARN' AND temperature>=30` không tự trở thành giao của hai index chỉ vì ta tạo hai 2i legacy.
- Index được duy trì trên các node có dữ liệu, và thường phải đọc base row để kiểm chứng ứng viên.
- Update/delete index column tạo chi phí bảo trì/tombstone.
- Dữ liệu cực lệch (`status='OK'` khớp 98% row) hoặc partition rộng có thể làm truy vấn chậm.
- DDL index trên bảng đã có dữ liệu cần **quá trình build**; metadata tồn tại không đủ chứng minh mọi node đã xây xong.

**Không sử dụng một lab RF=1 để kết luận 2i tốt cho cluster nhiều node.** Lab chủ yếu xác minh query syntax và semantics, không phải benchmark.

## 8. Nhánh lab B: SASI (chỉ đọc/thực nghiệm có kiểm soát)

### 8.1. Cảnh báo trạng thái

SASI có thể nằm trong mã nguồn/binary và tài liệu 4.1/5.0, nhưng tài liệu `cassandra.yaml` ghi **`sasi_indexes_enabled: false` theo mặc định** và đánh dấu tính năng thử nghiệm, **không khuyến nghị production**. Bài này **không hướng dẫn bật SASI trên cluster đang phục vụ dữ liệu thật**.

Nếu môi trường không cho phép `SASIIndex`, **bỏ qua toàn bộ CQL trong mục 8**, vẫn có thể hoàn thành bài bằng ma trận và lab 2i/SAI. Đừng tự đổi `cassandra.yaml` hoặc restart nhiều node chỉ để làm ví dụ.

### 8.2. Bảng lab riêng và ví dụ PREFIX

**Chỉ chạy nếu** quản trị đã chuẩn bị sẵn **cluster lab riêng** với SASI được phép và bản Cassandra có implementation:

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_sasi (
  event_id uuid PRIMARY KEY,
  note text,
  temperature double
);

CREATE CUSTOM INDEX IF NOT EXISTS events_sasi_note_idx
ON index_versions_lab.events_sasi (note)
USING 'org.apache.cassandra.index.sasi.SASIIndex'
WITH OPTIONS = {'mode': 'PREFIX'};

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (55555555-5555-4555-8555-555555555555,
        'Overheat motor', 30.8);

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (66666666-6666-4666-8666-666666666666,
        'Overflow pump', 28.5);

INSERT INTO index_versions_lab.events_sasi (event_id, note, temperature)
VALUES (77777777-7777-4777-8777-777777777777,
        'Normal', 24.2);

-- SASI PREFIX: query LIKE prefix trên bản hỗ trợ.
SELECT event_id, note
FROM index_versions_lab.events_sasi
WHERE note LIKE 'Over%';
~~~

Kỳ vọng hai row `Overheat motor` và `Overflow pump`, **nếu SASI được bật, index đã sẵn sàng và analyzer/option đúng**. Trình tự trả hàng không mang ý nghĩa thứ tự toàn cục.

Để tìm **chuỗi con** như `'%heat%'`, SASI có chế độ `CONTAINS` trên một index riêng (không phải chỉ thêm `LIKE` vào index PREFIX). Cần xác minh mode/analyzer, chi phí và giới hạn chính xác của bản đang chạy. Không trộn thêm index khác loại trên cùng bảng để so sánh trực tiếp.

### 8.3. SASI không phải SAI

Các bẫy điển hình:

1. Thấy class name chứa `SASIIndex` rồi nghĩ server hỗ trợ `USING 'sai'` — **sai**.
2. Thấy SAI cũng gắn với SSTable rồi cho rằng SAI hỗ trợ `LIKE 'Over%'` — **không đúng theo tài liệu Apache 5.0**.
3. Thấy SASI vẫn được document ở 5.0 rồi xem đây là feature production-stable — **sai vì trạng thái experimental**.
4. Dùng dữ liệu nhỏ/ít concurrent writes để tuyên bố SASI nhanh hoặc không có chi phí tombstone/rebuild — **thiếu bằng chứng**.
5. Cài bằng cách bật option SASI trên một node trong cluster nhiều node mà không kiểm tra rollout/config — **rủi ro schema và tính ổn định**.

## 9. Nhánh lab C: SAI (chỉ Apache Cassandra 5.x hỗ trợ)

### 9.1. Điều kiện

**Không chạy các lệnh này trên Apache Cassandra 4.0/4.1/3.11 upstream**, vì SAI được tích hợp từ Cassandra 5.0. Nếu dùng bản phân phối khác có SAI, hãy dùng tài liệu của bản phân phối đó thay vì giả định mọi cú pháp/operator tương thích.

Tạo bảng riêng, không có 2i/SASI:

~~~sql
CREATE TABLE IF NOT EXISTS index_versions_lab.events_sai (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  status text,
  temperature double,
  note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE INDEX IF NOT EXISTS events_sai_status_idx
ON index_versions_lab.events_sai (status)
USING 'sai';

CREATE INDEX IF NOT EXISTS events_sai_temperature_idx
ON index_versions_lab.events_sai (temperature)
USING 'sai';
~~~

**Kết quả:** mỗi SAI index là một index theo cột. Hai index trên hai cột cùng bảng có thể được dùng trong một query có điều kiện AND hỗ trợ, khác với giả định “hai 2i luôn tự động giao nhau”.

### 9.2. Nhập dữ liệu cùng semantics với lab 2i

~~~sql
INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111,
        'OK', 24.2, 'Normal');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222,
        'WARN', 30.8, 'Overheat motor');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333,
        'WARN', 28.5, 'Overflow pump');

INSERT INTO index_versions_lab.events_sai
 (device_id, event_day, event_time, event_id, status, temperature, note)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444,
        'WARN', 31.2, 'Overheat valve');
~~~

### 9.3. SELECT bằng một và hai SAI indexes

~~~sql
-- Equality: kỳ vọng 3 row.
SELECT device_id, event_time, status, temperature
FROM index_versions_lab.events_sai
WHERE status = 'WARN';

-- Hai predicate indexed: kỳ vọng 2 row.
SELECT device_id, event_time, status, temperature
FROM index_versions_lab.events_sai
WHERE status = 'WARN'
  AND temperature >= 30.0;

-- Numeric range theo SAI: kỳ vọng 2 row.
SELECT device_id, temperature
FROM index_versions_lab.events_sai
WHERE temperature >= 30.0;
~~~

Các câu trên cần **Cassandra 5.x đã xây xong index**. Không dựa trên thứ tự trả về để khẳng định partition của `sensor-03` đến trước `sensor-01`: clustering order chỉ áp dụng trong partition, không sort mọi partition toàn cluster.

**Phép thử âm bắt buộc:**

~~~sql
-- CẢNH BÁO: truy vấn cố ý không được hỗ trợ bởi SAI text index.
-- SAI không hỗ trợ LIKE theo tài liệu Cassandra 5.0.
SELECT device_id, note
FROM index_versions_lab.events_sai
WHERE note LIKE 'Over%';
~~~

Ở bảng này `note` còn chưa có SAI; ngay cả nếu tạo SAI cho cột `note`, **`LIKE` vẫn không được hỗ trợ theo tài liệu SAI 5.0**. Không giải thích lỗi này bằng cách “quên bật `ALLOW FILTERING`” rồi chạy full scan production.

### 9.4. Xác minh index đã queryable

Trên Cassandra 5.x có virtual table quản lý SAI phù hợp:

~~~sql
DESCRIBE TABLE system_views.indexes;

SELECT keyspace_name, table_name, index_name, is_queryable, is_building
FROM system_views.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_sai';
~~~

Nếu bản Cassandra không có `system_views.indexes` hoặc cột khác với ví dụ, kiểm tra `DESCRIBE`/tài liệu đúng version. `is_queryable` và `is_building` được mô tả trong tài liệu SAI, giúp phân biệt “index đã có trong schema” với “index đã sẵn sàng ở node hiện tại”.

**Virtual table là góc nhìn node đang nhận query**. Với cluster nhiều node, cần kiểm tra trạng thái build/metrics trên các node liên quan; một node báo `is_queryable=true` không chứng minh toàn cluster đã sẵn sàng trong lúc rollout.

## 10. Hiểu chi phí vận hành theo vòng đời dữ liệu

| Hoạt động | 2i | SASI | SAI |
| --- | --- | --- | --- |
| **INSERT/UPDATE** | Duy trì hidden index table cục bộ | Duy trì cấu trúc SASI theo memtable/SSTable | Duy trì memtable indexes và index data gắn SSTable |
| **DELETE/TTL/tombstones** | Có thể để lại stale candidates/tombstones, tăng maintenance | Phải xem hành vi của SASI và ảnh hưởng các tombstone theo bản | Có read-path post-filtering/tombstone handling tích hợp với SSTable lifecycle |
| **Build trên bảng có sẵn dữ liệu** | Có quá trình build trên mỗi node | Cần xây index SASI khi được bật | Có index build, quan sát trạng thái queryable/building |
| **Flush/compaction** | Hidden index có hoạt động storage/compaction riêng | Gắn với quá trình flush/SSTable theo implementation | Index components theo vòng đời SSTable/compaction |
| **Bootstrap/streaming** | Cần tính đến tính sẵn sàng của index cục bộ và quy trình rebuild | Không dựa vào feature experimental cho phương án vận hành mới | SAI hỗ trợ tích hợp streaming; kiểm tra thực tế/version |
| **Backup/restore** | Không chỉ sao chép DDL rồi coi dữ liệu và index đã phục hồi | Yêu cầu runbook tương thích nếu vẫn dùng | Index gắn với storage nhưng vẫn cần backup/restore và kiểm tra truy vấn |
| **Index drop** | Xóa index, không xóa bảng cơ sở | Xóa custom index, không xóa bảng cơ sở | Xóa SAI, không xóa bảng cơ sở |

Một index không tự động sửa **replica data inconsistency**. `nodetool repair` phục vụ đồng bộ các replica; rebuild index là công việc khác. Đừng chạy `repair`/`compact`/`rebuild_index` tùy tiện sau khi thấy một query chậm.

### 10.1. Cột biến động nhiều là thử thách khác biệt

Ví dụ `status` đổi từ `WARN` sang `OK` hàng chục lần trong vòng đời một row. Cần đo:

- Chi phí ghi và số index updates thực tế.
- Kích thước SSTable/index components và tốc độ compaction.
- Tombstones và số base rows phải kiểm tra lại.
- Độ trễ query theo một giá trị index vừa thay đổi dưới CL đang dùng.
- Dữ liệu sau khi TTL hết hạn/xóa và kiểm tra rằng query không trả row cũ không còn hợp lệ.

Không suy rằng “SASI gắn SSTable” hoặc “SAI hiện đại” đồng nghĩa tất cả update/delete **miễn phí**. Tính đúng đắn vẫn phải kiểm tra trong điều kiện replication/consistency của ứng dụng.

## 11. Quy trình quyết định chọn index

~~~mermaid
flowchart TD
    A["Có truy vấn theo partition key không?"] -->|"Có"| B["Ưu tiên primary indexing + clustering"]
    A -->|"Không"| C{"Apache Cassandra phiên bản nào?"}
    C -->|"5.0 có SAI"| D{"SAI hỗ trợ operator + datatype?"}
    D -->|"Có"| E["Thử SAI trên bảng riêng, benchmark, kiểm tra queryable"]
    D -->|"Không"| F["Thiết kế bảng theo query / search service"]
    C -->|"3.x/4.x upstream"| G{"Legacy 2i đáp ứng và đo chấp nhận được?"}
    G -->|"Có, phạm vi hạn chế"| H["2i có kiểm soát + đo tải thực"]
    G -->|"Không"| F
    C -->|"SASI đã tồn tại"| I["Experimental: bảo trì legacy, không lựa chọn mới mặc định"]
    I --> F
    E --> J["Review p95/p99, disk, build/repair, rolling upgrade"]
    H --> J
~~~

### 11.1. Checklist đánh giá kỹ thuật

Trước khi đề xuất index, trả lời:

1. **Truy vấn nghiệp vụ**: các câu `WHERE` và số row cần trả cụ thể là gì? Có bắt buộc sort toàn cluster không?
2. **Version/phân phối**: Apache upstream hay managed/distribution? Có feature tương ứng và được hỗ trợ production không?
3. **Selectivity**: mỗi giá trị khớp bao nhiêu row; giá trị nào phổ biến nhất, cardinality ra sao?
4. **Partition key**: đã xác định được partition/bucket chưa? Có thể thiết kế bảng query-oriented thay index không?
5. **Write path**: tần suất update/delete/TTL của indexed column; compaction backlog và dung lượng index chấp nhận được?
6. **RF/CL**: local DC nào, bao nhiêu replica cần phản hồi, tình trạng node/repair hiện tại?
7. **Operational readiness**: build/rebuild, streaming, backup/restore, rolling upgrade và permissions cho DDL đã có runbook?
8. **SLA**: throughput, p95/p99, số request đồng thời, timeouts, retry rate và giới hạn tài nguyên.
9. **Rollback**: nếu index không tốt, ứng dụng có phương án query khác trước khi `DROP INDEX` không?

## 12. Chuyển từ 2i/SASI sang SAI hoặc bảng theo truy vấn

### 12.1. Không có “ALTER INDEX TYPE SASI TO SAI”

Đây là **chuyển đổi chiến lược truy vấn**, không phải đổi một flag để biến file index cũ thành index mới. Một kế hoạch an toàn:

1. **Inventory**: từ schema và logs, liệt kê tên index, index type/options, query patterns, người dùng/ứng dụng phụ thuộc, phiên bản server.
2. **Kiểm tra target**: chọn phiên bản Cassandra có hỗ trợ feature đích; hoàn tất đánh giá upgrade/topology trước khi tạo index mới.
3. **Chọn bảng/cluster thử nghiệm riêng**: nạp dữ liệu đại diện; không trộn SAI và 2i trên cùng bảng nếu tài liệu version khuyến cáo tránh.
4. **Tạo SAI hoặc bảng query-oriented**: mỗi cột/predicate được index theo quy tắc của bản đích.
5. **Chờ build xong và validate**: kiểm tra `system_schema.indexes`, `system_views.indexes` nếu có, sample row theo primary key và truy vấn indexed.
6. **So sánh semantics**: đặc biệt chuyển `SASI LIKE 'prefix%'` hoặc `'%substring%'` sang SAI **không tương đương** vì SAI 5.0 không hỗ trợ `LIKE`.
7. **Benchmark**: cùng dataset, RF/CL, tải, nhiệt độ cache, page size và số row trả; đo p50/p95/p99, CPU/GC, disk/network, compaction.
8. **Rollout ứng dụng có khả năng rollback**: chỉ chuyển traffic sau khi chuẩn bị feature flag và cách quay về truy vấn cũ/bảng cũ.
9. **Theo dõi sau rollout**: correctness, query timeouts, disk growth, build/queryability trên từng node, retries và tail latency.
10. **Dọn index legacy**: `DROP INDEX` chỉ sau khi xác nhận **không còn query phụ thuộc** và tuân thủ change management.

### 12.2. Lưu ý cụ thể khi đang nâng cấp Cassandra 4.x → 5.x

Một cluster mixed-version đang rolling upgrade **không phải môi trường mặc nhiên an toàn để tạo schema SAI mới**. Tất cả node cần tương thích với index type và schema; kế hoạch upgrade phải tuân theo tài liệu của bản đang chạy và quy trình orchestrator. Không chỉ kiểm tra `SHOW VERSION` của một coordinator rồi tạo SAI ngay trên production khi còn node 4.x.

Nếu không thể dùng SAI mà vẫn cần predicate ngoài partition key, cân nhắc bảng thiết kế theo truy vấn:

~~~sql
-- Phương án thay thế minh họa: tìm WARN theo site + ngày.
-- Thêm shard nếu một partition quá nóng; cần logic shard/merge.
CREATE TABLE IF NOT EXISTS index_versions_lab.warn_by_site_day (
  site_id text,
  event_day date,
  shard smallint,
  event_time timestamp,
  device_id text,
  event_id uuid,
  temperature double,
  PRIMARY KEY ((site_id, event_day, shard),
               event_time, device_id, event_id)
) WITH CLUSTERING ORDER BY
  (event_time DESC, device_id ASC, event_id ASC);
~~~

Bảng này chỉ phù hợp nếu workload cần `WARN` theo site/ngày và pipeline **chỉ ghi các WARN events**. Nó không tự cập nhật từ bảng `events_2i`. Nếu event đổi trạng thái, ứng dụng phải xử lý cập nhật/xóa trên bảng thứ cấp, idempotency và đối soát. Shard partition key giúp phân tải, nhưng query top-N trên nhiều shard phải hợp nhất kết quả ở application.

## 13. Quan sát index và truy vấn bằng cqlsh/nodetool

### 13.1. Metadata và trạng thái index

~~~sql
DESCRIBE KEYSPACE index_versions_lab;
DESCRIBE TABLE index_versions_lab.events_2i;

SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'index_versions_lab';
~~~

Với SAI trên Cassandra 5.x:

~~~sql
-- Chỉ khi bản server có system_views.indexes.
DESCRIBE TABLE system_views.indexes;
SELECT keyspace_name, table_name, index_name, is_queryable, is_building
FROM system_views.indexes
WHERE keyspace_name = 'index_versions_lab'
  AND table_name = 'events_sai';
~~~

**Không dùng metadata schema thay trạng thái runtime**: index được khai báo trong schema không chứng minh index đã build xong trên từng replica. Các giá trị virtual table có thể **node-local**; khi troubleshooting cluster nhiều node phải đọc ở các node liên quan.

### 13.2. So sánh trace có kiểm soát

~~~sql
TRACING ON;

-- Baseline theo partition key (không cần secondary index).
SELECT event_time, temperature
FROM index_versions_lab.events_2i
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Query qua index không biết partition key.
SELECT device_id, event_time, temperature
FROM index_versions_lab.events_2i
WHERE status = 'WARN';

TRACING OFF;
~~~

Trace có thể cho thấy coordinator/replica, remote requests và thời gian một số giai đoạn, nhưng **tracing có overhead**, không phải benchmark trung lập. Đo latency không tracing với workload lớn hơn mới có ý nghĩa so sánh p95/p99. Không bật tracing cho toàn bộ traffic sản xuất.

Từ node quản trị, các lệnh phổ biến:

~~~bash
nodetool status
nodetool describecluster
nodetool compactionstats
nodetool tablestats index_versions_lab.events_2i
~~~

`nodetool` thường sử dụng đường quản trị/JMX, không phải native 9042. Lệnh có thể khác theo phiên bản; không chạy `rebuild_index` hoặc major compaction chỉ vì một query index bị chậm. Cần xác định index type, build status, replica health và nguyên nhân trước.

### 13.3. Ma trận kiểm thử production-like

| Nhóm đo | Kịch bản tối thiểu |
| --- | --- |
| **Correctness** | So row theo primary key; update `WARN→OK`; delete; TTL hết hạn; read ở CL thực. |
| **Selectivity** | `status='WARN'` hiếm và `status='OK'` phổ biến; range có tỉ lệ khớp khác nhau. |
| **Scalability** | Tăng số partition/node/data size; đo remote requests và coordinator CPU. |
| **Write overhead** | INSERT/UPDATE/DELETE dưới concurrency thật, compaction và disk index growth. |
| **Recovery** | Index build/rebuild, restart node, bootstrap/streaming, thay đổi topology trên cluster lab. |
| **Client behavior** | Paging, timeout, retry policy, driver local DC, TLS/auth, query cancellation. |
| **Long-running** | Chạy qua chu kỳ flush/compaction/repair và theo dõi p95/p99. |

Không có ngưỡng cố định “SAI gấp N lần 2i” áp dụng mọi hệ. Bộ số liệu phải gắn với phần cứng, phiên bản, workload và cấu hình cụ thể.

## 14. Java Driver 4.x: các index thay đổi schema, không thay API gửi CQL

Java Driver vẫn gửi **prepared statements qua native protocol**. Index type được quyết định bởi schema phía Cassandra, **không phải Java Driver tự chọn giữa 2i/SASI/SAI**. Khi thay index/query syntax, ứng dụng cần cập nhật statement tương ứng.

Ví dụ dùng **lab 2i phổ thông**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;

public class IndexVersionQueryDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT device_id, event_time, status, temperature " +
                "FROM index_versions_lab.events_2i " +
                "WHERE status = ?");

            BoundStatement query = ps.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int rows = 0;
            for (Row row : session.execute(query)) {
                rows++;
                System.out.println(
                    row.getString("device_id") + " / " +
                    row.getInstant("event_time") + " / " +
                    row.getDouble("temperature"));
            }
            System.out.println("matching_rows=" + rows);
        }
    }
}
~~~

**Điều kiện:** 2i đã tạo và build sẵn sàng; lab không bật TLS/auth để ví dụ ngắn. `datacenter1` là **tên minh họa**, lấy local DC thực từ `SELECT data_center FROM system.local;`. Trên hệ thống thật phải bật TLS/CA, credentials, timeout và retry chính sách của tổ chức.

Với SAI 5.x, query `WHERE status = ? AND temperature >= ?` là statement khác và bảng khác (`events_sai`); cần chuẩn bị đúng SAI indexes. Với SASI `LIKE`, query chỉ chạy nếu SASI được phép, không thể copy sang SAI 5.x giữ nguyên semantics.

**Kết quả và latency:** một Java client chạy query 2i có thể chọn coordinator không giữ dữ liệu phù hợp; query không có partition key thường không thể token-aware route đến một token duy nhất. `setPageSize(100)` không bảo đảm tổng query chỉ quét/đọc 100 row, còn `setTimeout(5s)` chỉ là giá trị mẫu. Đo và log loại lỗi (nhưng không log password/bind values bí mật) để phân biệt `InvalidRequest`, `Unavailable`, server read timeout và driver timeout.

## 15. Bảng chẩn đoán lỗi theo loại index

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm tra đúng |
| --- | --- | --- |
| Cassandra 4.1 báo không biết `USING 'sai'` | SAI chưa tích hợp upstream 4.1 | Đọc `SHOW VERSION` và tài liệu bản server; dùng bảng query-oriented/2i có kiểm chứng. |
| SASI `CREATE CUSTOM INDEX` bị từ chối | Feature experimental chưa bật hoặc distribution không cho phép | Xem `sasi_indexes_enabled` và policy; không bật trên production để né lỗi. |
| `CREATE INDEX` không `USING` tạo loại khác dự kiến | `default_secondary_index` đã được cấu hình | Đọc `system_schema.indexes.kind/options` và server config. |
| Query `LIKE` chạy trên SASI nhưng lỗi trên SAI | SAI 5.x không hỗ trợ `LIKE` | Chọn query semantics khác hoặc search service; không giả định tương đương. |
| SAI index có trong schema nhưng query chưa chạy | Index vẫn build/chưa queryable trên node | Kiểm tra `system_views.indexes` và build metrics/logs theo node. |
| 2i query không có partition key chậm | Distributed fan-out, selectivity kém hoặc data lớn | Đo p95/p99, remote requests, result count, topology/CL. |
| `status='OK'` rất chậm nhưng `WARN` nhanh | Giá trị OK khớp phần lớn bảng | Đo matching fraction, cân nhắc primary key/bảng phù hợp. |
| Index maintenance gây write latency | Update/delete/tombstones, flush/compaction | Quan sát CPU, disk, GC, compaction, per-index metrics. |
| `Unavailable` ở `LOCAL_QUORUM` | Thiếu replica theo keyspace RF/DC/CL | `nodetool status`, replication settings, internode network. |
| `ReadTimeout` ở index query | Replica chậm, fan-out lớn, cluster tải cao | Tracing chọn lọc, metrics, query selectivity, cluster health. |
| Java `AllNodesFailedException` | DNS/TCP/TLS/auth/peer discovery chưa hoạt động | Kiểm tra native endpoints và driver local DC trước khi đổ lỗi cho index. |
| Sau `DROP INDEX` ứng dụng lỗi | Query đang phụ thuộc index đã xóa | Inventory queries và rollout trước khi drop; có rollback. |
| `ALLOW FILTERING` làm query chạy nhưng chậm | Cho phép đọc/lọc dữ liệu rộng; không tạo index mới | Viết query theo partition hoặc tạo data model/index đúng phép thử. |

## 16. Bài tập thực hành và tự đánh giá

1. Phân biệt **implementation tồn tại**, **feature được bật** và **feature được khuyến nghị production** qua ví dụ SASI.
2. Lập bảng 2i/SASI/SAI cho Cassandra 3.11, 4.1, 5.0. Giải thích tại sao không đem cú pháp SAI vào 4.1 upstream.
3. Trong Cassandra 5.0, tại sao `CREATE INDEX ...` không có `USING` không đủ chứng minh index là legacy 2i?
4. Tạo `events_2i` và bốn row mẫu. Đối chiếu truy vấn có partition key với truy vấn chỉ theo `status`.
5. Truy vấn `system_schema.indexes` để phân biệt tên index, loại và options. Nếu index vừa tạo trên bảng đã có dữ liệu, cần xem thêm trạng thái nào?
6. Giải thích vì sao 2i lưu cục bộ nhưng query không có partition key vẫn sinh fan-out qua coordinator.
7. Giả sử `status='OK'` khớp 98% row và `WARN` khớp 0,01%. Phân tích selectivity riêng cho từng giá trị, không chỉ cardinality.
8. Xem phần SASI và giải thích sự khác nhau giữa `PREFIX` và `CONTAINS`. Vì sao không tự bật `sasi_indexes_enabled` trong production?
9. Trên cluster lab **5.x có SAI**, tạo hai SAI indexes trên `events_sai` và chạy query `status='WARN' AND temperature>=30`. Dự đoán hai row được trả.
10. Thử `LIKE 'Over%'` trên lab SAI và giải thích giới hạn operator; tại sao chuyển từ SASI sang SAI có thể phải sửa truy vấn?
11. Dùng `system_views.indexes` trên 5.x để kiểm tra `is_queryable` và `is_building`. Tại sao phải quan sát từng node trong cluster nhiều node?
12. Thiết kế bảng để lấy cảnh báo mới nhất theo site/ngày mà không cần scan toàn cluster. Xem xét shard/merge và cập nhật khi trạng thái đổi.
13. Viết một runbook migration từ 2i/SASI sang SAI gồm inventory, setup lab, build, query validation, benchmark, rollout/rollback, drop legacy.
14. Dùng Java Driver với prepared statement `WHERE status = ?` và nêu các thành phần đo latency ngoài Java (replica, coordinator, compaction, internode).
15. Đề xuất khi nào nên bỏ cả ba loại index để dùng ETL/analytics hoặc search engine độc lập.

**Tiêu chí hoàn thành:** đọc đúng **ma trận version/state**, phân biệt rõ 2i–SASI–SAI về kiến trúc và operator, thực hành đúng nhánh lab của phiên bản, không nhầm SASI experimental với SAI stable, và có khả năng thiết kế migration/query an toàn dựa trên bằng chứng về data distribution, CL/RF và vận hành cluster.

## Tài liệu tham khảo chính thức

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): primary index, secondary index 2i và mốc SAI trong Apache Cassandra 5.0.
- [Apache Cassandra — 2i concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-concepts.html): index cục bộ dưới dạng bảng ẩn và tác động lên truy vấn phân tán.
- [Apache Cassandra — SASI Index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/SASI.html): custom index, `SASIIndex`, `PREFIX`, `CONTAINS` và `SPARSE`.
- [Apache Cassandra 4.1 — cassandra.yaml](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html): `sasi_indexes_enabled`, trạng thái experimental và default false.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): SASI opt-in, `default_secondary_index` và các guardrails.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): read/write path trên memtable/SSTable và kết hợp indexed predicates.
- [Apache Cassandra — SAI FAQ](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-faq.html): supported operators (không hỗ trợ `LIKE`), dữ liệu được index và `system_views.indexes`.
- [Apache Cassandra — SAI quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/sai-quickstart.html): ví dụ tạo và truy vấn SAI trên Cassandra 5.0.
- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-index.html): cú pháp `USING`, kiểu index và giới hạn.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): kiểm tra node, compaction và trạng thái cluster.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): session, prepared statement, paging, consistency và timeout.
