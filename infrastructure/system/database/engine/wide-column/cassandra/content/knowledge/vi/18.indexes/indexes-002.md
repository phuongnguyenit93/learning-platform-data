# Chỉ mục phụ cục bộ và chi phí điều phối truy vấn

## 1. Vấn đề: tìm dữ liệu khi không biết partition key

Apache Cassandra là hệ cơ sở dữ liệu **wide-column phân tán**. Một bảng được phân bố theo **partition key**, còn các **clustering columns** sắp xếp row trong từng partition. Truy vấn biết đầy đủ partition key thường có đường định tuyến rõ ràng đến các replica chứa dữ liệu.

Nhưng một ứng dụng đôi khi hỏi: “Tìm mọi sự kiện có `status = 'WARN'`”, trong khi `status` không thuộc khóa chính. Để hỗ trợ điều kiện trên cột như vậy, Cassandra có cơ chế **secondary index**. Loại index đời đầu là **2i (legacy secondary index)**, triển khai bằng **cấu trúc chỉ mục cục bộ ở mỗi node**.

2i tạo cảm giác có một “chỉ mục toàn cluster” vì người dùng chỉ cần gửi một câu `SELECT ... WHERE status = ?`. Thực tế, **không có một node index trung tâm giữ danh sách đầy đủ tất cả row**. Mỗi node duy trì index đối với dữ liệu ở node đó; coordinator phải phối hợp việc tìm kiếm ở các node/replica liên quan. Đây là lý do 2i có thể chịu **chi phí fan-out, mạng, CPU, disk I/O và tổng hợp kết quả** lớn hơn một truy vấn theo partition key.

Bài thuộc chương **Chỉ mục** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, liên hệ với thiết kế bảng theo truy vấn, replication/consistency, compaction/repair, quan sát lỗi và truy cập Cassandra từ Java.

**Sau bài học, bạn có thể:**

1. Giải thích vì sao 2i được gọi là **local index** và vì sao truy vấn của nó có thể là **distributed query**.
2. So sánh đường đi của `SELECT` theo partition key với `SELECT` bằng 2i khi không có partition key.
3. Tạo, truy vấn, quan sát và xóa 2i bằng CQL trong lab an toàn.
4. Phân tích cardinality, số row khớp, partition rộng, tần suất update/delete và số node để dự đoán chi phí.
5. Hiểu rằng `LIMIT`, `ALLOW FILTERING` và tăng consistency không tự biến 2i thành truy vấn rẻ.
6. Biết khi nào nên ưu tiên bảng thiết kế theo truy vấn hoặc **SAI** (Apache Cassandra 5.0 trở lên) thay cho 2i.
7. Ghi nhận bằng chứng qua cqlsh, tracing, metrics và Java Driver trước khi quyết định dùng index trên production.

## 2. Phân biệt primary index, 2i và SAI

| Tiêu chí | Primary index | Legacy secondary index (2i) | Storage-Attached Index (SAI) |
| --- | --- | --- | --- |
| Điểm vào truy vấn | **Partition key** | Giá trị cột được index, kể cả cột không thuộc khóa chính | Giá trị cột có SAI |
| Tạo bằng cách nào? | Tự động khi tạo `PRIMARY KEY` | `CREATE INDEX` phù hợp version (loại legacy) | `CREATE INDEX ... USING 'sai'` theo cú pháp/version hỗ trợ |
| Lưu trữ | Cấu trúc partition/row của storage engine | **Bảng index ẩn, cục bộ trên mỗi node**, tách với bảng cơ sở | Cấu trúc index gắn với Memtable/SSTable |
| Nếu thiếu partition key | Không thể dùng cho point lookup một partition | Có thể phải tìm ở nhiều node rồi tổng hợp | Có cơ chế truy vấn index tối ưu hơn nhưng vẫn phải cân nhắc phân tán và selectivity |
| Chi phí duy trì | Gắn với ghi vào bảng | Thêm ghi/index data, tombstone, rebuild | Thêm chi phí lưu trữ/indexing; thiết kế tích hợp storage engine |
| Phiên bản | Mọi phiên bản Cassandra phổ biến | Cơ chế 2i lâu đời | **Apache Cassandra 5.0+** |
| Khuyến nghị thiết kế mới | Ưu tiên khi biết key | Hạn chế; dùng có kiểm chứng, nhất là khi biết partition key | Ưu tiên đánh giá nếu cần index trên non-key columns ở Cassandra 5.x+ |

Theo tài liệu Apache Cassandra 5.0, `legacy_local_table` là loại 2i mặc định khi dùng `CREATE INDEX` không chọn kiểu, còn `sai` là cơ chế mới. Đối với Cassandra 4.x, phải đối chiếu cú pháp và khả năng hỗ trợ của phiên bản; **không sao chép tùy chọn SAI của bản 5.x vào bản cũ**.

Không coi SAI là “giải pháp mọi truy vấn”: nếu truy vấn cần quét/aggregate phần lớn dữ liệu, vẫn cần xem thiết kế partition, workload, số node và giải pháp analytics.

## 3. Local index được duy trì ở mỗi node như thế nào?

### 3.1. Bảng ẩn lưu ánh xạ giá trị index tới row

Trong 2i, khi một node có dữ liệu bảng cơ sở, nó duy trì **một bảng index ẩn cục bộ** cho cột được lập index. Mô hình khái niệm:

~~~text
Node A:
  Base table:
    (sensor-01, 2026-11-21, 01:00) -> status=OK
    (sensor-02, 2026-11-21, 01:02) -> status=WARN
  Local 2i for status:
    OK   -> [khóa row sensor-01/...]
    WARN -> [khóa row sensor-02/...]

Node B:
  Base table:
    (sensor-03, 2026-11-21, 01:03) -> status=WARN
  Local 2i for status:
    WARN -> [khóa row sensor-03/...]
~~~

Đây là **mô hình đơn giản hóa**, không phải khẳng định dữ liệu đang được phân trên chính xác hai node hay format vật lý của hidden table giống dòng text. Với replication factor lớn hơn 1, nhiều replica có thể chứa cùng partition, và mỗi replica duy trì thông tin index **tại node của mình**.

Điểm mấu chốt:

- Index **không chuyển tất cả giá trị `status` tới một server index tập trung**.
- Index cục bộ giúp node tìm **khóa row ứng viên**, sau đó phải kiểm tra/đọc dữ liệu bảng cơ sở để trả kết quả đúng.
- Các bản sao và trạng thái dữ liệu vẫn tuân theo **replication, consistency, timestamp/tombstone** của Cassandra.
- Có thể có index entry cũ sau update/delete; đường đọc cần xử lý kiểm tra để tránh trả row không còn khớp điều kiện.

### 3.2. Index được cập nhật lúc nào?

Khi ứng dụng `INSERT` hoặc `UPDATE` một cột có 2i, Cassandra duy trì index cùng đường ghi của bảng. Nếu tạo index **sau khi dữ liệu đã tồn tại**, Cassandra phải **xây dựng index trên dữ liệu cũ**, thường thông qua quá trình background build. Trong thời gian đó, không được mặc định một truy vấn index sẽ có kết quả đầy đủ tức thì trên toàn cluster.

Khi đổi:

~~~text
status = 'WARN'  -->  status = 'OK'
~~~

node phải xử lý cả việc làm mất hiệu lực ánh xạ cũ và tạo ánh xạ mới. Các update/delete lặp lại có thể để lại **tombstone** trong index/nguồn dữ liệu, gây tăng chi phí đọc và compaction. Việc index duy trì tự động **không có nghĩa miễn phí**.

## 4. Vì sao coordinator phải làm nhiều việc hơn?

### 4.1. Truy vấn theo partition key: đã biết đích

Ví dụ bảng có partition key `(device_id, event_day)`:

~~~sql
SELECT event_time, status
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Coordinator tính token cho partition, xác định tập replica theo keyspace replication strategy, gửi yêu cầu đọc theo CL. Đường truy cập này có **phạm vi khóa rõ ràng**.

### 4.2. Truy vấn index mà thiếu partition key: chưa biết đích

~~~sql
SELECT device_id, event_day, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Ở đây `status` là cột index, nhưng mọi partition của bảng đều **có khả năng chứa** giá trị `WARN`. Coordinator không thể dùng `status` như partition key để tính một token duy nhất của bảng cơ sở. Nó phải tổ chức các công việc tìm kiếm trên **nhiều node/replica chịu trách nhiệm những phần dữ liệu liên quan**, lấy tập row ứng viên, xác minh điều kiện rồi hợp nhất kết quả.

~~~mermaid
flowchart LR
    App["cqlsh / Java Driver"] -->|"WHERE status='WARN'"| Coord["Coordinator"]
    Coord -->|"Tìm trong local 2i"| A["Node A: local index"]
    Coord -->|"Tìm trong local 2i"| B["Node B: local index"]
    Coord -->|"Tìm trong local 2i"| C["Node C: local index"]
    A -->|"Row candidates và dữ liệu"| Coord
    B -->|"Row candidates và dữ liệu"| Coord
    C -->|"Row candidates và dữ liệu"| Coord
    Coord -->|"Hợp nhất + kiểm tra + giới hạn kết quả"| App
~~~

**Sơ đồ chỉ minh họa fan-out**: không phải mỗi request 2i luôn gửi một message tới *mọi* node. Planner, token ranges, replica selection, CL và phiên bản quyết định số node thực sự tham gia. Tuy nhiên, khi thiếu partition key, số node/partition cần xét có thể tăng theo quy mô dữ liệu và cluster.

### 4.3. Cấu thành chi phí đọc

Một mô hình tư duy:

~~~text
Đọc bằng partition key:
  tìm replica của 1 partition
  + đọc partition / clustering range
  + phối hợp phản hồi theo CL

Đọc bằng 2i không có partition key:
  lập kế hoạch tìm index trên nhiều node/phạm vi token
  + giao tiếp và chờ nhiều nhánh tìm kiếm
  + đọc local index ở từng nhánh
  + đọc base rows / loại stale candidates
  + tổng hợp, phân trang và trả kết quả
~~~

Không biến sơ đồ này thành công thức thời gian `N × latency` tuyệt đối. Các tác vụ có thể chạy song song; thời gian cuối cùng có thể chịu ảnh hưởng của **nhánh chậm nhất, tail latency, lượng kết quả, mạng, paging, contention và deadline**. Tổng CPU/I/O/network trên cluster vẫn có thể tăng khi fan-out rộng.

### 4.4. Vai trò của consistency level

Với **RF = 3 trong một datacenter**, `LOCAL_QUORUM` thường cần hai replica đáp ứng trong DC đó cho từng phạm vi dữ liệu được truy vấn; `ONE` cần ít hơn. Nhưng **CL không phải số node phải truy vấn bằng 2i**, bởi một truy vấn index không có partition key có thể liên quan nhiều partition/token range.

Không đánh đồng:

- **Số replica cần phản hồi cho consistency**.
- **Số node/phạm vi cần liên hệ để tìm hết các row ứng viên**.
- **Số row thực sự khớp điều kiện**.

Do vậy, giảm `LOCAL_QUORUM` xuống `ONE` không làm mất bản chất distributed search và có thể làm yếu bảo đảm nhất quán; không dùng đó là “cách chữa” mặc định cho truy vấn 2i chậm.

## 5. Chọn cột để index: cardinality, selectivity và phân bố dữ liệu

### 5.1. Định nghĩa rõ hai thuật ngữ

- **Cardinality** của cột: số giá trị khác nhau (distinct values) trong tập dữ liệu. Boolean có tối đa hai giá trị, UUID gần như duy nhất có cardinality rất cao.
- **Matching fraction** (tỉ lệ row khớp một giá trị): số row đáp ứng `status = 'WARN'` chia tổng số row được xét. Ở ví dụ 1 triệu row, nếu `WARN` khớp 800.000 row thì kết quả rất lớn; nếu khớp 100 row thì kết quả nhỏ.

Một cột có cardinality không quá thấp vẫn có thể có **phân bố lệch**. Ví dụ `status` có 10 giá trị, nhưng `OK` chiếm 99% row: truy vấn `OK` có matching fraction lớn, còn `WARN` có thể nhỏ. Hiệu quả phải đánh giá **theo giá trị và workload thật**, không chỉ theo số distinct values.

### 5.2. Vì sao hai cực trị đều bất lợi với 2i?

| Đặc điểm cột | Ví dụ | Chi phí/rủi ro chính |
| --- | --- | --- |
| Cực ít giá trị | `is_active boolean`, `status = 'OK'` ở gần mọi row | Mỗi giá trị phổ biến có danh sách/posting rất lớn; partition của index có thể lớn và nóng. |
| Giá trị gần như duy nhất | `request_id uuid` hoặc email unique | Rất nhiều index entries và lookup/phân tán đắt so với point lookup theo key; maintenance/storage tăng. |
| Update/delete liên tục | `current_state` thay đổi nhiều lần/phút | Index tombstones/stale entries, read amplification và compaction overhead. |
| Cột vừa phải, thay đổi ít | `category` hoặc loại thiết bị ở tập hữu hạn | Có thể sử dụng được nếu query bị giới hạn rõ, nhất là đã biết partition key; vẫn phải benchmark. |
| Cột dùng để lấy phần lớn bảng | `status='OK'` ở 98% row | Index không làm việc xuất/scan khối lượng lớn trở thành thao tác nhỏ. |

Một quy tắc sai thường gặp là “**cardinality thấp thì luôn nên tạo 2i**”. Cardinality *quá thấp* có thể sinh những bucket index khổng lồ. Ngược lại, index trên cardinality *quá cao* có thể sinh vô số entry với lợi ích nhỏ mỗi truy vấn. Điểm phù hợp tùy **matching fraction, partition width, update rate, số node và tần suất đọc**.

### 5.3. Bảng rộng và hot partition vẫn quan trọng

Giả sử một `device_id` có hàng triệu event trong một partition không được bucket theo thời gian. Index `status` có thể đưa ra ứng viên ở nhiều clustering rows của partition đó; đọc base row, kiểm tra tombstone và phân trang vẫn rất nặng. **Index không thay thế time bucketing** hoặc kiểm soát kích thước partition.

Nếu quá nhiều ghi cùng lúc vào một giá trị index cực phổ biến trên một node, cấu trúc index cục bộ còn có thể trở thành nguồn contention/hotspot khác. Khi thiết kế, xem cả **partition key gốc** lẫn phân bố **giá trị indexed**.

## 6. Lab: tạo 2i và so sánh truy vấn theo khóa với truy vấn phân tán

Lab bên dưới giả định **Cassandra 4.1 hoặc 5.x, một node riêng, RF = 1**, không có production data. Nó minh họa **tính hợp lệ** và cú pháp 2i; **không đo được fan-out đa node**. Để đo chi phí coordinator, cần cluster lab nhiều node với dữ liệu lớn hơn và cùng cấu hình/tài nguyên.

### 6.1. Tạo keyspace và bảng theo truy vấn chính

Từ terminal có cqlsh:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS local_2i_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS local_2i_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  site_id text,
  status text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE local_2i_lab.events_by_device_day;
~~~

Với composite partition key `(device_id, event_day)`, truy vấn tốt nhất theo mô hình này là “sự kiện của một thiết bị trong một ngày”, có thể giới hạn `event_time`. `site_id` và `status` là **regular columns**, nên chỉ biết chúng chưa đủ để định vị partition bằng primary indexing.

### 6.2. Nhập dữ liệu mẫu có khóa cố định

~~~sql
INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'site-A', 'OK', 25.1);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'site-A', 'WARN', 29.4);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:02:00Z',
        33333333-3333-4333-8333-333333333333, 'site-B', 'OK', 24.0);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:07:00Z',
        44444444-4444-4444-8444-444444444444, 'site-B', 'WARN', 30.2);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:01:00Z',
        55555555-5555-4555-8555-555555555555, 'site-A', 'OK', 23.3);

INSERT INTO local_2i_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, site_id, status, value)
VALUES ('sensor-03', '2026-11-21', '2026-11-21T01:06:00Z',
        66666666-6666-4666-8666-666666666666, 'site-A', 'NEW', 24.1);
~~~

Vì UUID và primary key cố định, chạy lại cùng lệnh sẽ **upsert** cùng row chứ không thêm row trùng khóa. Nếu bảng lab đã chứa dữ liệu từ một lần chạy khác, kỳ vọng đếm row cần điều chỉnh hoặc chuẩn bị keyspace lab mới; **không TRUNCATE bảng ngoài lab**.

### 6.3. Baseline: SELECT theo partition key, không cần 2i

~~~sql
CONSISTENCY ONE;

SELECT event_time, status, value
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Kỳ vọng **hai row**, `01:05 WARN 29.4` rồi `01:00 OK 25.1`. Đây là đường truy cập hiệu quả theo partition key và clustering order, **không cần index phụ**.

### 6.4. Tạo 2i cục bộ trên status

~~~sql
-- Cú pháp legacy secondary index dùng được ở Cassandra 4.x/5.x.
-- Chỉ tạo trong lab vì index có chi phí vận hành thực.
CREATE INDEX IF NOT EXISTS local_2i_status_idx
ON local_2i_lab.events_by_device_day (status);

DESCRIBE TABLE local_2i_lab.events_by_device_day;

SELECT index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'local_2i_lab'
  AND table_name = 'events_by_device_day';
~~~

Theo tài liệu Cassandra 5.0, nếu không chọn `USING` thì index được tạo theo loại 2i legacy `legacy_local_table` (ở những bản áp dụng mặc định này). Trên phiên bản khác, hãy kiểm tra cấu hình/type và tài liệu bản đang chạy; đừng mặc định mọi `CREATE INDEX` đều là SAI.

Nếu tạo index **sau khi sáu row đã tồn tại**, quá trình build trên dữ liệu cũ có thể diễn ra **bất đồng bộ**. Trước khi kết luận query không đầy đủ, cần xác minh index đã xây dựng xong trên các node và đọc log/metrics nếu cần. Đừng coi dòng `CREATE INDEX` thành công là bằng chứng tự động index đã sẵn sàng trên toàn cluster ngay lúc đó.

### 6.5. SELECT qua 2i khi không có partition key

~~~sql
SELECT device_id, event_day, event_time, site_id, status, value
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Sau khi index sẵn sàng và không có dữ liệu thừa, kỳ vọng **hai row**:

| device_id | event_time (UTC) | site_id | status | value |
| --- | --- | --- | --- | ---: |
| `sensor-01` | `01:05` | `site-A` | `WARN` | 29.4 |
| `sensor-02` | `01:07` | `site-B` | `WARN` | 30.2 |

**Không kỳ vọng thứ tự hàng của hai partition cố định.** `CLUSTERING ORDER BY` chỉ áp dụng *trong cùng partition*, không tạo global sort cho những row được tìm qua index trên nhiều partition.

Đối với lab một node, kết quả rất nhanh không chứng minh query 2i sẽ nhanh khi bảng có hàng chục triệu row và nhiều node. Chi phí **fan-out/merge** chỉ xuất hiện đầy đủ khi có nhiều phạm vi token/nhiều replica cần phục vụ truy vấn.

### 6.6. Thêm partition key để giới hạn phạm vi

~~~sql
SELECT event_time, status, value
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND status = 'WARN';
~~~

Mục tiêu là tìm `WARN` **trong một partition đã biết**. Dạng này có phạm vi hẹp hơn về mặt logic so với `WHERE status='WARN'` trên toàn bảng, và là kịch bản mà 2i có thể ít rủi ro hơn. Tuy nhiên, cách planner phối hợp primary key và indexed predicate có thể phụ thuộc phiên bản; nếu bị từ chối vì filtering, **không thêm `ALLOW FILTERING` một cách mù quáng**. Hãy kiểm tra schema, quy tắc query, truy vấn thay thế chỉ dùng partition key rồi lọc tập row nhỏ ở ứng dụng, hoặc đánh giá SAI đúng version.

### 6.7. Một lỗi minh họa: nhiều điều kiện không được hỗ trợ chỉ bằng một 2i

~~~sql
-- site_id không nằm trong primary key và chưa có index riêng.
-- Trên nhiều phiên bản Cassandra sẽ báo lỗi về filtering.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN'
  AND site_id = 'site-A';
~~~

Không suy rằng đã có index `status` thì Cassandra tự lập chỉ mục kết hợp cho mọi cột khác. Legacy 2i có giới hạn với **nhiều predicate**; thậm chí tạo hai 2i riêng vẫn có thể cần `ALLOW FILTERING` trong một số truy vấn, như tài liệu Cassandra minh họa. Với nhu cầu tìm theo `site_id + status + day` thường xuyên, nên đánh giá **một bảng thiết kế theo query** hoặc **SAI trong Cassandra 5.x**.

## 7. Cập nhật/xóa cột indexed: ảnh hưởng gì?

### 7.1. Thay trạng thái một row

Chỉ thực hiện **sau khi đã đối chiếu kết quả `WARN` ban đầu**:

~~~sql
UPDATE local_2i_lab.events_by_device_day
SET status = 'OK'
WHERE device_id = 'sensor-02'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:07:00Z'
  AND event_id = 44444444-4444-4444-8444-444444444444;

-- Sau khi thay đổi được phản ánh, thường chỉ còn WARN của sensor-01.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';
~~~

Vì cập nhật theo **đầy đủ primary key**, Cassandra biết row cần đổi. 2i phải điều chỉnh ánh xạ ứng với giá trị cũ `WARN` và giá trị mới `OK`. Trong quá trình index maintenance, các **tombstone và mục index cũ** có thể làm tăng đọc/compaction, đặc biệt với cột cập nhật liên tục.

Đừng dùng kết quả đọc từ một replica duy nhất vào thời điểm đang ghi đồng thời để khẳng định tức thì tất cả replica/index đã hội tụ. Replication, CL, tốc độ xây index và trạng thái node vẫn ảnh hưởng quan sát trong cluster thật.

### 7.2. Tại sao stale index entry không phải dữ liệu đúng?

Một index có thể còn ánh xạ tới row sau khi row bị xóa hoặc giá trị index đã thay đổi, tùy trạng thái SSTable/tombstone/replica. Cassandra có các cơ chế **kiểm tra kết quả ứng viên và xử lý tombstone** để tránh trả thông tin sai; nhưng làm như vậy vẫn cần đọc dữ liệu gốc và tạo overhead. Đây là lý do những bảng update/delete dày đặc thường là **ứng viên không tốt cho legacy 2i**.

### 7.3. Gỡ index khỏi lab

~~~sql
-- Chỉ thao tác với index của lab; query dựa vào status có thể ngừng chạy.
DROP INDEX IF EXISTS local_2i_lab.local_2i_status_idx;
~~~

`DROP INDEX` xóa cấu trúc index, **không xóa bảng cơ sở**. Trên hệ thống thật, lệnh này có thể ảnh hưởng các ứng dụng đang query theo index; cần theo dõi migration và kế hoạch rollback, không chạy ngoài quy trình.

## 8. Truy vấn phân tán có thể đắt theo những cách nào?

### 8.1. Fan-out làm tăng tổng tài nguyên và tail latency

Khi query không xác định partition, coordinator có thể phải tìm ở nhiều token ranges và trao đổi với nhiều node. Khi cluster tăng quy mô:

- **Nhiều công việc con** hơn có thể tạo thêm request, queue và context switching.
- **Một nhánh chậm** có thể kéo dài thời gian trả kết quả cuối cùng.
- **Kết quả lớn** làm tăng bytes truyền, serialize/deserialize, phân trang và CPU tổng hợp.
- **Timeout và retry** có thể nhân tải trên cluster nếu mỗi request ban đầu đã fan-out.
- **RF/CL** ảnh hưởng số replica và mức phản hồi, nhưng không làm `status` trở thành partition key.

Do vậy, một số row khớp ít không nhất thiết có nghĩa query rẻ: Cassandra có thể vẫn phải **hỏi nhiều nơi** để chắc chắn tìm được các ứng viên.

### 8.2. LIMIT không chặn chi phí trước khi tìm

~~~sql
SELECT device_id, event_day, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'OK'
LIMIT 10;
~~~

`LIMIT 10` giới hạn số row được trả về, **không đảm bảo chỉ cần đọc mười mục index** hoặc liên hệ một node. Với index cục bộ phân tán, việc tìm ứng viên và phối hợp kết quả vẫn có thể đắt. `LIMIT` còn **không tạo thứ tự toàn cluster**; nếu cần “10 sự kiện OK mới nhất toàn hệ thống”, phải có mô hình/truy vấn đảm bảo thứ tự theo phạm vi phù hợp.

### 8.3. ALLOW FILTERING không tự xây index

~~~sql
-- Đây là ví dụ cảnh báo: không chạy trên bảng lớn.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN'
  AND site_id = 'site-A'
ALLOW FILTERING;
~~~

`ALLOW FILTERING` có thể cho phép Cassandra thực hiện các bước **lọc thêm** mà nó cảnh báo là không dự đoán tốt chi phí. Nó không biến `site_id` thành một index mới và không bảo đảm planner chỉ đọc một partition. Chỉ sử dụng có cân nhắc trong lab hoặc workload đã được đo; **không xem nó là nút “tối ưu query”**.

### 8.4. Index cục bộ và tính sẵn sàng

Nếu một phần node/index replica không phục vụ hoặc chưa xây xong, truy vấn 2i có thể gặp `Unavailable`, `ReadTimeout` hoặc `DriverTimeout` tùy CL, tình trạng node và planner. Một index ở vài node hoạt động tốt không chứng minh toàn cluster đã sẵn sàng.

Đọc đúng thông báo:

- `Unavailable`: không đủ replica sẵn sàng cho điều kiện consistency tương ứng.
- `ReadTimeout`: không nhận đủ phản hồi đúng thời hạn.
- `DriverTimeoutException`: client hết hạn chờ mà chưa nhận kết quả phù hợp.
- `InvalidRequest`: câu query/index/filtering không hợp lệ theo luật CQL hoặc schema.

Không giải quyết lỗi index bằng cách **bật mọi firewall port, giảm CL production hoặc tăng timeout vô hạn**.

## 9. Quan sát và đo: không suy từ một query nhỏ

### 9.1. Kiểm tra schema/index có tồn tại

~~~sql
SHOW VERSION;
DESCRIBE TABLE local_2i_lab.events_by_device_day;

SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'local_2i_lab'
  AND table_name = 'events_by_device_day';
~~~

Nếu không thấy index, kiểm tra lệnh tạo đã chạy trên **đúng cluster và keyspace** hay chưa. Nếu index vừa được tạo trên bảng có dữ liệu, cần xem **trạng thái build trên node**. Metadata schema có index không tự chứng minh rằng build local index trên mọi node đã hoàn tất.

### 9.2. Tracing theo hai mẫu truy vấn

~~~sql
-- Thao tác trên lab: TRACING có overhead.
TRACING ON;

-- Baseline định vị partition rõ ràng.
SELECT event_time, status
FROM local_2i_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Query chỉ dựa vào secondary index.
SELECT device_id, event_time, status
FROM local_2i_lab.events_by_device_day
WHERE status = 'WARN';

TRACING OFF;
~~~

Trong trace, đọc **coordinator, các bước index lookup, số/loại request tới peer và thời gian** nếu phiên bản ghi nhận được. Không suy rằng số dòng trace chính là số replica; truy vấn nhỏ trên một node chưa thể minh họa đủ mạng phân tán. Tracing tự tạo overhead nên cần đo thêm latency khi **không** bật tracing.

### 9.3. Số liệu cần đo ở client và cluster

| Nhóm metric | Câu hỏi |
| --- | --- |
| **Read latency p50/p95/p99** | Tail latency của `WHERE status=?` có khác lookup theo key không? |
| **Coordinator request latency** | Node nhận query mất bao lâu để tổng hợp? |
| **Internode traffic/messages** | Truy vấn index có sinh nhiều request đi qua mạng hơn không? |
| **Partition/index selectivity** | Có bao nhiêu row thật khớp từng giá trị? Giá trị nào chiếm 90% row? |
| **Disk I/O, SSTable count, compaction** | Đọc index/base rows, tombstone và compaction có gây nghẽn? |
| **CPU/GC, queue, dropped messages** | Fan-out làm tăng tải/độ trễ ở coordinator hay replica? |
| **Timeout/retry rate** | Tăng concurrency có tạo retry storm không? |
| **Index build/rebuild status** | Tất cả node đã xây index xong trước khi đo chưa? |

Với môi trường có quyền quản trị Cassandra:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats local_2i_lab.events_by_device_day
nodetool compactionstats
~~~

Các lệnh `nodetool` thường qua JMX, **không phải** CQL/native port 9042. Output phụ thuộc phiên bản và node đang kiểm tra. `nodetool status` hiển thị ring health, không tự cho biết chi phí mỗi query 2i; cần gắn metrics vào workload cụ thể.

### 9.4. Đo trên cluster nhiều node thế nào cho công bằng?

1. Dùng hai workload đại diện: `Q_key` biết đầy đủ partition key và `Q_2i` chỉ có predicate indexed; **không gọi chúng là cùng semantics** nếu số row trả về khác nhau.
2. Ghi **số row, bytes, key distribution, matching fraction** của mỗi query. Muốn so sánh latency nên chuẩn hóa mức công việc được yêu cầu.
3. Cố định Cassandra version, RF, CL, CPU/RAM/disk, client concurrency, page size và timeout; ghi cqlsh/driver version.
4. Tách warm-up và đo lặp nhiều lần; không kết luận từ một trace hoặc một query khi cache lạnh.
5. Thu **p95/p99, throughput, network bytes, CPU/GC, disk I/O, compaction/tombstone** trên nhiều node.
6. Thử với các giá trị indexed **phổ biến và hiếm**; không chỉ chọn một `WARN` có ít row.
7. Đánh giá khi node chậm hoặc mất kết nối trong **lab**; không fault injection tùy tiện trên production.

Không bịa ra ngưỡng “2i luôn nhanh dưới N node/N triệu row”. Điểm chuyển sang bảng khác/SAI tùy dữ liệu và SLA thực tế.

## 10. Bảo trì index và hoạt động nền

### 10.1. Index build và rebuild

Sau `CREATE INDEX` trên bảng có dữ liệu, Cassandra xây index cho dữ liệu cũ theo quy trình nền. Trên cluster nhiều node, cần xác nhận **từng node** đã hoàn tất quá trình liên quan, đồng thời theo dõi log/index metrics và ảnh hưởng read/write latency.

Nếu index native bị hỏng hoặc cần rebuild theo hướng dẫn phiên bản, Cassandra có lệnh quản trị:

~~~bash
# CHỈ là cú pháp tham khảo; không chạy tùy tiện trên production.
# Rebuild index có thể tạo tải CPU/disk/compaction đáng kể.
nodetool rebuild_index local_2i_lab events_by_device_day local_2i_status_idx
~~~

Lệnh áp dụng cho node được `nodetool` liên hệ (thường node local hoặc `-h` chỉ định host). Không nên gọi một lần rồi mặc định index trên **toàn bộ cluster** đã rebuild. Lập kế hoạch từng node, theo dõi tiến độ/log, quyền JMX, dung lượng và rollback theo runbook.

### 10.2. Compaction, repair, TTL và tombstone

2i là local index gắn với dữ liệu của node, chịu ảnh hưởng của cập nhật/xóa và bảo trì. Khi bảng có **TTL**, tombstone hoặc thay đổi giá trị indexed thường xuyên, index có thể tích lũy mục cũ/marker xóa và phải thực hiện thêm việc kiểm tra khi query.

Tuy nhiên, **repair dữ liệu replica** và **rebuild index cục bộ** là hai thao tác khác nhau:

- `nodetool repair` phục vụ đồng bộ dữ liệu replica theo token ranges/consistency vận hành.
- `nodetool rebuild_index` phục vụ tái xây native secondary index của bảng trên node được chỉ định.
- `nodetool compact`/compaction xử lý SSTable và tombstone theo strategy, không phải lệnh “chữa mọi query 2i”.

Không chạy rebuild, repair hoặc major compaction như một phép thử vô hại; cần đánh giá tải và nguyên nhân sự cố thực.

## 11. Phương án thay thế khi 2i gây chi phí điều phối lớn

### 11.1. Bảng thứ hai thiết kế theo truy vấn

Giả sử yêu cầu nghiệp vụ quan trọng là:

> Lấy các cảnh báo `WARN` tại một site trong một ngày, mới nhất trước, tối đa 100 row.

Bảng ban đầu có partition key `(device_id,event_day)` không phù hợp với access pattern này. Có thể thiết kế một bảng truy vấn riêng:

~~~sql
-- Mô hình minh họa: time bucket theo site, ngày, status và shard.
-- Shard cần một quy tắc ổn định; không tùy tiện đổi khi retry.
CREATE TABLE IF NOT EXISTS local_2i_lab.events_by_site_status_day (
  site_id text,
  event_day date,
  status text,
  shard smallint,
  event_time timestamp,
  device_id text,
  event_id uuid,
  value double,
  PRIMARY KEY ((site_id, event_day, status, shard),
               event_time, device_id, event_id)
) WITH CLUSTERING ORDER BY
  (event_time DESC, device_id ASC, event_id ASC);
~~~

Ví dụ truy vấn một shard:

~~~sql
SELECT event_time, device_id, event_id, value
FROM local_2i_lab.events_by_site_status_day
WHERE site_id = 'site-A'
  AND event_day = '2026-11-21'
  AND status = 'WARN'
  AND shard = 0
LIMIT 100;
~~~

Thiết kế này **không tự tạo dữ liệu** trong bảng mới. Ứng dụng/pipeline phải ghi hoặc backfill dữ liệu tương ứng. Nếu dùng nhiều shard, cần query các shard liên quan và **merge top-N** ở ứng dụng; số shard phụ thuộc throughput/partition size, không mặc định chọn một hằng số cho mọi site.

**Cảnh báo thay đổi trạng thái:** khi `status` là một thành phần của partition key ở bảng truy vấn, đổi `WARN → OK` thường cần **xóa row ở partition cũ và ghi row ở partition mới**. Đây là bài toán đồng bộ nhiều bảng có thể có lỗi giữa chừng, đòi idempotency/reconciliation. Cassandra `BATCH` không phải transaction SQL có rollback/isolation toàn cục.

### 11.2. SAI nếu Apache Cassandra 5.0+

**Storage-Attached Index (SAI)** được tích hợp trong Apache Cassandra 5.0, gắn index với Memtable/SSTable và hỗ trợ các loại predicate hiệu quả hơn 2i trong nhiều workload. Với schema hiện đại, tài liệu Cassandra khuyến nghị đánh giá SAI thay vì tạo 2i mới khi cần secondary indexing.

Một ví dụ **Cassandra 5.x dành cho bảng lab riêng**, không trộn SAI với 2i của bảng `events_by_device_day`:

~~~sql
-- Chỉ chạy nếu Cassandra 5.x đã hỗ trợ SAI.
-- Bảng riêng hoàn toàn, CHƯA có legacy 2i.
CREATE TABLE IF NOT EXISTS local_2i_lab.events_sai_demo (
  event_id uuid PRIMARY KEY,
  status text,
  site_id text
);

CREATE INDEX IF NOT EXISTS status_sai_idx
ON local_2i_lab.events_sai_demo (status)
USING 'sai';

INSERT INTO local_2i_lab.events_sai_demo (event_id, status, site_id)
VALUES (77777777-7777-4777-8777-777777777777, 'WARN', 'site-A');

SELECT event_id, status, site_id
FROM local_2i_lab.events_sai_demo
WHERE status = 'WARN';
~~~

Nếu đang dùng Cassandra 4.x thì **không thực hiện block SAI này**; chỉ chạy ví dụ trên bản hỗ trợ SAI và đã tạo keyspace `local_2i_lab` từ lab trước. Một số distribution/phiên bản Cassandra khác nhau có quy định index khác nhau. SAI cũng có **chi phí index/write/storage và phân tán truy vấn**, nên benchmark thay vì kỳ vọng “miễn phí fan-out”.

### 11.3. Khi nào không nên dùng cả 2i lẫn SAI?

- Truy vấn là **full-table scan, phân tích tổng hợp toàn hệ thống**: chọn Spark/analytics, pipeline ETL hoặc bảng tổng hợp thích hợp.
- Một vài giá trị index khớp **hầu hết bảng**: cấu trúc index ít giảm lượng dữ liệu cần đọc.
- Cần lấy **top-N toàn cluster có thứ tự toàn cục**: phải có mô hình bucket/aggregation và merge có kiểm soát.
- Dữ liệu bị cập nhật/xóa liên tục với nhiều trạng thái: đánh giá chi phí index, tombstone và đồng bộ.
- Nhu cầu truy vấn có thể biểu diễn tốt bằng **partition key rõ ràng**: primary-key query thường là lựa chọn đơn giản và có thể dự đoán chi phí hơn.

## 12. Java Driver: cùng phiên nhưng hai access patterns

Ví dụ cho **Java Driver 4.x**, với bảng lab và index `local_2i_status_idx` đã tạo. Đoạn mã thực hiện một point/partition query và một index query; **không dùng thời gian một lần chạy làm benchmark**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;

public class LocalSecondaryIndexDemo {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement byKey = session.prepare(
                "SELECT event_time, status, value " +
                "FROM local_2i_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            PreparedStatement byStatus = session.prepare(
                "SELECT device_id, event_time, status, value " +
                "FROM local_2i_lab.events_by_device_day " +
                "WHERE status = ?");

            BoundStatement keyQuery = byKey.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50)
                .setTimeout(Duration.ofSeconds(5));

            BoundStatement indexQuery = byStatus.bind("WARN")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(50)
                .setTimeout(Duration.ofSeconds(5));

            long startKey = System.nanoTime();
            int keyRows = 0;
            for (Row row : session.execute(keyQuery)) {
                keyRows++;
            }
            long keyElapsedNs = System.nanoTime() - startKey;

            long startIndex = System.nanoTime();
            int indexRows = 0;
            for (Row row : session.execute(indexQuery)) {
                indexRows++;
            }
            long indexElapsedNs = System.nanoTime() - startIndex;

            System.out.println("partition_rows=" + keyRows +
                    " duration_ns=" + keyElapsedNs);
            System.out.println("index_rows=" + indexRows +
                    " duration_ns=" + indexElapsedNs);
        }
    }
}
~~~

**Giới hạn và bài học của đoạn mã:** Nếu đã thực hiện `DROP INDEX` ở mục 7.3, cần tạo lại `local_2i_status_idx` và xác nhận index xây xong trước khi chạy ví dụ Java; nếu không, câu `byStatus` có thể bị từ chối.

- `datacenter1` là ví dụ; dùng tên DC thực từ `SELECT data_center FROM system.local;`.
- CL, page size và timeout là **statement-level settings**, không lấy từ lệnh `CONSISTENCY` của phiên cqlsh khác.
- Driver có thể chọn coordinator khác nhau giữa hai câu; index query không có partition key thường **không được định tuyến tới một token cụ thể** như query theo khóa.
- Hai câu có **semantics và số row có thể khác nhau**, nên thời gian in ra không phải phép so sánh hiệu năng công bằng.
- `System.nanoTime()` đo wall-clock phía client trong ví dụ, gồm overhead Java/network/deserialize; phải đo nhiều lần, warm-up và lấy percentile nếu cần benchmark.
- Đoạn mã không cấu hình TLS/auth để đơn giản cho lab. Production phải dùng SSL context, credentials, contact points và retry policy được cấp phép.
- Nếu index bị drop hoặc chưa build xong, `byStatus` có thể lỗi/không trả đủ dữ liệu; không tự động thêm `ALLOW FILTERING` hoặc retry vô hạn.

## 13. Troubleshooting: nhận diện đúng lỗi 2i

| Triệu chứng | Giải thích có thể | Kiểm tra/hành động |
| --- | --- | --- |
| `WHERE status='WARN'` bị từ chối | Index chưa tồn tại, sai keyspace/table, chưa hỗ trợ predicate | `DESCRIBE TABLE`, `system_schema.indexes`, kiểm tra version và câu query. |
| `CREATE INDEX` xong nhưng query chưa đủ kết quả | Background build chưa hoàn tất ở tất cả node hoặc dữ liệu/CL đang thay đổi | Xem log/index build status và trạng thái replica; không coi chỉ metadata là đủ. |
| Index query nhanh ở lab một node, chậm ở cluster | Fan-out, số token ranges, network/merge, hot index values | Đo p95/p99 và tổng resource trên nhiều node với dataset đại diện. |
| `status='OK'` chậm, `status='WARN'` nhanh | Phân bố matching fraction lệch, posting `OK` khổng lồ | Đo row khớp từng giá trị, đánh giá thiết kế bảng/index. |
| `status` update nhiều gây latency/tombstone | Maintenance index/old entries và compaction | Giảm index trên cột biến động, quan sát compaction, cân nhắc SAI/bảng khác. |
| Query có hai điều kiện regular columns bị `InvalidRequest` | Một hoặc hai 2i không đủ hỗ trợ kết hợp predicate hiệu quả | Kiểm tra rules, đừng tự thêm `ALLOW FILTERING` ở production. |
| `ReadTimeout` khi query index | Nhiều công việc con, replica chậm, cluster quá tải | Kiểm tra coordinator, CL, fan-out, queue, disk, network và logs. |
| `Unavailable` ở `LOCAL_QUORUM` | Không đủ replica theo RF/DC/CL | `nodetool status`, replication settings, mạng internode. |
| Java báo `AllNodesFailedException` | Chưa thiết lập session/native connections ổn định | DNS/TCP 9042, TLS/auth, `broadcast_rpc_address`, local DC; không quy lỗi cho 2i trước khi kết nối được. |
| `DROP INDEX` xong ứng dụng lỗi query | Ứng dụng phụ thuộc cột indexed, không còn đường query | Phân tích dependency/migration trước khi drop index. |
| Query dùng `LIMIT 10` vẫn tốn tài nguyên | LIMIT không xóa fan-out/index lookup ban đầu | Đánh giá scope/partition design, đo remote requests. |
| Row trả về thay đổi sau update/delete | Concurrent writes, timestamp/tombstone, CL và trạng thái index | Đọc theo primary key để đối chiếu, kiểm tra consistency và logs. |

## 14. Bài tập tự thực hành

1. Giải thích vì sao gọi legacy 2i là **local index** dù query `WHERE status='WARN'` có thể trả row từ nhiều node.
2. Vẽ đường đi từ **Java Driver → coordinator → các local indexes → base rows → kết quả** và so sánh với truy vấn theo partition key.
3. Tạo `local_2i_lab.events_by_device_day` và nạp dữ liệu mẫu. Chạy query theo `(device_id,event_day)` để kiểm chứng baseline.
4. Tạo `local_2i_status_idx`, đọc `system_schema.indexes` và xác nhận loại index trên đúng bảng. Nếu có dữ liệu trước đó, vì sao cần chờ build?
5. Truy vấn `status='WARN'`, nêu hai row dự kiến và giải thích tại sao không thể kỳ vọng thứ tự toàn cục.
6. Dùng truy vấn `status='WARN' AND site_id='site-A'` để quan sát lỗi/ràng buộc lọc của Cassandra; vì sao thêm 2i không tự giải quyết mọi predicate?
7. Cập nhật row `sensor-02` từ `WARN` sang `OK`. Quan sát thay đổi và giải thích tombstone/stale index candidate có thể làm tăng chi phí ra sao.
8. Với tập dữ liệu 10 triệu row và `status='OK'` chiếm 98%, vì sao index 2i trên `status` không có tính chọn lọc tốt cho query này?
9. So sánh index trên cột boolean, UUID gần unique và category có cardinality trung bình nhưng update hiếm. Không chọn chỉ dựa trên cardinality; nêu thêm hai metric cần biết.
10. Giải thích tại sao `LIMIT 10` trên query không có partition key chưa chắc làm giảm mạnh network fan-out và tổng I/O.
11. Trong cluster RF = 3, `LOCAL_QUORUM` cần bao nhiêu replica trong một DC có RF = 3? Tại sao đó **không phải** số node duy nhất có thể tham gia query 2i toàn bảng?
12. Chạy tracing có kiểm soát trên point query và index query, đọc các sự kiện liên quan coordinator/replica, rồi tắt tracing.
13. Đề xuất bảng truy vấn thay thế để lấy `WARN` ở một site trong một ngày. Nếu sharding, ứng dụng phải tổng hợp kết quả như thế nào?
14. Nêu lý do không nên kết hợp 2i với SAI trên cùng một bảng theo khuyến nghị tài liệu và vì sao Cassandra 4.x không dùng cú pháp SAI bản 5.x.
15. Soạn checklist triển khai index production: cardinality, matching fraction, update/delete, build time, RF/CL, latency tail, disk/compaction, rollback và quyền truy cập.

**Tiêu chí hoàn thành:** phân biệt chính xác cấu trúc **local index** với query **phân tán**, tự tạo và truy vấn 2i, giải thích được vì sao coordinator fan-out đắt, chọn/loại cột indexed dựa trên workload và đề xuất thiết kế bảng hoặc SAI khi 2i không phù hợp.

## Tài liệu tham khảo

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): phân biệt primary indexing, local 2i và SAI, khuyến nghị dùng 2i với partition key.
- [Apache Cassandra — Secondary index (2i) concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-concepts.html): local hidden table, giới hạn hiệu năng và sự khác nhau với SAI.
- [Apache Cassandra — When to use an index](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-when-to-use.html): low/high cardinality, index values có posting lớn, update/delete và partition rộng.
- [Apache Cassandra — Working with secondary indexing (2i)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/2i-working-with.html): tạo/xem/drop index, multi-predicate query và collection indexes.
- [Apache Cassandra — CREATE INDEX](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexes.html): cú pháp index, loại `legacy_local_table` và `sai`, background indexing.
- [Apache Cassandra — Rebuilding 2i](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/2i/operations/2i-build.html): index build và vận hành rebuild.
- [Apache Cassandra — nodetool rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html): cú pháp `nodetool rebuild_index keyspace table indexName`.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): prepared statements, consistency, paging, timeout và metadata/coordinator.
