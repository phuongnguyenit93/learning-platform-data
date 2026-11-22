# Primary index và truy cập qua partition/clustering key

## 1. Primary index trong Cassandra có nghĩa gì?

Trong Apache Cassandra, **primary index** là cơ chế truy cập cơ bản dựa trên **partition key** của bảng. Khi biết partition key, Cassandra có thể xác định các replica phụ trách partition và tìm dữ liệu liên quan mà không phải quét toàn bộ bảng. Bên trong mỗi partition, các **clustering columns** quyết định thứ tự các row, cho phép truy cập một row cụ thể hoặc một đoạn row liên tiếp.

Điều này khác với thói quen suy nghĩ về index trong hệ quản trị quan hệ: không phải mỗi cột đặt trong `WHERE` đều được tìm nhanh bằng một B-tree. Cassandra là hệ **wide-column phân tán**, thiết kế bảng **theo truy vấn sẽ chạy**, chứ không mặc định tạo một schema chuẩn hóa rồi đặt index để hỗ trợ mọi kiểu lọc.

Trong chương **Chỉ mục** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài học tập trung vào cách **primary index, partition key và clustering key** phối hợp với token ring, replication và storage engine. Nắm được cơ chế này giúp thực hành CQL, giải thích các lỗi truy vấn, chọn consistency đọc/ghi, quan sát compaction/repair và kết nối Java Driver đúng cách.

**Sau bài học, bạn có thể:**

1. Phân biệt **PRIMARY KEY**, **partition key**, **clustering columns** và **primary indexing**.
2. Giải thích đường đi client → coordinator → replica → memtable/SSTable khi truy vấn theo khóa.
3. Viết `SELECT` theo partition key, điểm row, khoảng thời gian và thứ tự clustering.
4. Nhận diện truy vấn thiếu partition key, bỏ qua tiền tố clustering hoặc lọc trên regular column.
5. Đọc metadata schema và dùng Java Driver prepared statement để truy vấn có khóa.
6. Phân biệt primary index với **secondary index (2i)** và **Storage-Attached Index (SAI)**, kể cả giới hạn theo phiên bản.
7. Hiểu vì sao partition quá rộng hoặc partition key quá nóng vẫn khiến truy vấn chậm dù có primary indexing.

## 2. PRIMARY KEY = partition key + clustering columns

Mỗi bảng CQL cần khai báo một **primary key**. Primary key xác định duy nhất row trong bảng, nhưng gồm hai phần với nhiệm vụ khác nhau:

| Thành phần | Vai trò | Tác động lên truy cập |
| --- | --- | --- |
| **Partition key** | Quyết định partition và token để chọn replica | Hướng truy vấn đến tập replica có partition cần đọc. |
| **Clustering columns** | Xác định các row khác nhau và thứ tự trong cùng partition | Cho phép định vị row hoặc đọc một khoảng liên tục có thứ tự. |
| **Regular columns** | Lưu thuộc tính dữ liệu không thuộc khóa | Không tự tạo đường tra cứu primary index trên giá trị của chúng. |

Ví dụ ba định nghĩa:

~~~sql
-- Chỉ một partition key, mỗi giá trị key có một row.
CREATE TABLE IF NOT EXISTS example_single_key (
  device_id text PRIMARY KEY,
  model text
);

-- device_id là partition key; event_time, event_id là clustering columns.
CREATE TABLE IF NOT EXISTS example_one_partition_column (
  device_id text,
  event_time timestamp,
  event_id uuid,
  PRIMARY KEY (device_id, event_time, event_id)
);

-- Cặp (device_id, event_day) cùng tạo composite partition key.
CREATE TABLE IF NOT EXISTS example_composite_partition (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
);
~~~

Đoạn trên **minh họa cú pháp** khi đã `USE` một keyspace phù hợp. Phần lab sau sẽ khai báo keyspace và bảng đầy đủ, có thể chạy độc lập.

Sự khác nhau quan trọng:

- `PRIMARY KEY (device_id, event_day, event_time)` có **một** partition key là `device_id`; `event_day` và `event_time` là clustering columns.
- `PRIMARY KEY ((device_id, event_day), event_time)` có partition key là **cặp** `(device_id, event_day)`; `event_time` là clustering column.
- Cùng ba cột có thể tạo ra **phân bố dữ liệu và khả năng truy vấn hoàn toàn khác nhau** tùy vị trí dấu ngoặc.
- **Primary index dựa trên partition key được Cassandra duy trì tự động**, không cần và không nên chạy `CREATE INDEX` để “tạo primary index” cho khóa phân vùng.

### 2.1. Primary key xác định tính duy nhất

Trong một bảng có `PRIMARY KEY ((device_id, event_day), event_time, event_id)`, hai row có cùng `device_id` và `event_day` nhưng khác `event_time` hoặc `event_id` là **hai row riêng biệt**. Nếu chạy `INSERT` nhiều lần với **cùng toàn bộ primary key**, Cassandra thực hiện **upsert** giá trị của row đó; nó không tạo một row trùng khóa chính.

Không nên nhầm điều này với tính duy nhất của một cột regular như `event_type`. Nhiều row có thể cùng giá trị `event_type = 'temperature'`, vì nó không nằm trong primary key.

### 2.2. Minh họa tổ chức partition

~~~mermaid
flowchart TB
    K["Partition key = (device_id, event_day)"] --> P1["Partition A<br/>(sensor-01, 2026-11-21)"]
    K --> P2["Partition B<br/>(sensor-02, 2026-11-21)"]
    P1 --> A1["01:10 — event-id-3"]
    A1 --> A2["01:05 — event-id-2"]
    A2 --> A3["01:00 — event-id-1"]
    P2 --> B1["01:03 — event-id-4"]
~~~

Hình mô tả **logical partitions**, không phải bản đồ một-một giữa partition và một máy duy nhất. Mỗi partition được lưu trên **tập replica** xác định bởi token và replication strategy; có thể có nhiều bản sao trên các node khác nhau. Trong mỗi bản sao, thứ tự clustering giúp đọc `01:10` trước `01:05` rồi `01:00` khi bảng khai báo `event_time DESC`.

## 3. Primary index dẫn request đến replica như thế nào?

### 3.1. Từ partition key đến token

Khi ứng dụng gửi truy vấn với partition key, Cassandra dùng **partitioner** (mặc định thường là `Murmur3Partitioner`) để tính **token** từ giá trị khóa. Các token range được gán cho node và replica theo topology; replication strategy của keyspace xác định **tập replica** lưu partition đó.

Ví dụ khái niệm:

~~~text
Partition key ("sensor-01", 2026-11-21)
            |
            v
     Token = hash(partition key)
            |
            v
   Token range + replication strategy
            |
            v
  Replica set (ví dụ Node A, Node B, Node C)
            |
            v
  Coordinator đọc/ghi theo consistency level
~~~

**Không được suy ra token bằng cách hash từng cột riêng rồi cộng lại.** Cassandra dùng encoding của composite partition key và partitioner cụ thể. Thứ tự, kiểu và giá trị từng cột đều quan trọng.

### 3.2. Coordinator và replica là hai vai trò khác nhau

~~~mermaid
sequenceDiagram
    participant App as Java Driver / cqlsh
    participant Coord as Node coordinator
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    App->>Coord: SELECT WHERE partition key = ... (CL)
    Coord->>Coord: Tính token, xác định replica
    Coord->>A: Yêu cầu đọc partition
    Coord->>B: Yêu cầu đọc/digest khi cần
    opt Theo CL/topology và chiến lược đọc
        Coord->>C: Giao tiếp replica bổ sung
    end
    A-->>Coord: Dữ liệu hoặc phản hồi
    B-->>Coord: Phản hồi
    Coord-->>App: Kết quả hoặc lỗi timeout/unavailable
~~~

Sơ đồ minh họa chứ không phải quy định phải gửi request đến cả ba replica mỗi lần. Phụ thuộc **CL, trạng thái node, read path và phiên bản**. Coordinator có thể đồng thời là một replica. Java Driver nhận biết token/topology có thể chọn một coordinator phù hợp, nhưng **truy vấn đúng partition key không đồng nghĩa dữ liệu chỉ nằm trên một node**.

Trong cluster đa datacenter:

- `NetworkTopologyStrategy` và RF theo DC xác định replica ở các DC.
- `LOCAL_QUORUM` đòi số phản hồi quorum của **local DC**, không phải lấy một tỉ lệ cố định từ tổng số node toàn cluster.
- Primary indexing giúp **định vị partition**; consistency điều khiển **điều kiện phản hồi**. Hai khái niệm không thay thế nhau.

## 4. Primary index hoạt động bên trong storage engine

Cassandra sử dụng kiến trúc ghi kiểu **LSM (Log-Structured Merge)**: thao tác ghi đi qua commit log và memtable, sau đó được flush thành **SSTable bất biến**. Compaction gom các SSTable và tái tổ chức dữ liệu trên đĩa. Primary indexing không chỉ là một bảng ánh xạ nằm ngoài dữ liệu mà liên quan trực tiếp đến **cấu trúc lưu trữ theo partition**.

### 4.1. Đường ghi, phân vùng và thứ tự row

~~~mermaid
flowchart LR
    W["INSERT / UPDATE"] --> C["Commit log + memtable"]
    C -->|"Flush"| S["SSTable bất biến"]
    S --> D["Partition theo token"]
    D --> R["Row theo clustering order"]
    S --> M["Compaction với SSTable khác"]
~~~

Khi cùng partition có dữ liệu ghi nhiều lần, một phần dữ liệu có thể nằm trong **memtable** và nhiều **SSTable khác nhau**. Một thao tác đọc phải xem xét dữ liệu liên quan ở các nguồn cần thiết, hòa giải phiên bản/timestamp/tombstone; không thể mặc định “mỗi partition có duy nhất một file”.

### 4.2. SSTable chứa những thành phần chỉ mục gì?

Tên file **phụ thuộc phiên bản/định dạng SSTable**, nhưng ý tưởng chung là tìm **partition key** rồi mới đi đến row cần thiết:

| Thành phần/cơ chế | Mục đích | Cách hiểu đúng |
| --- | --- | --- |
| **Memtable** | Giữ dữ liệu chưa flush, có cấu trúc tra theo khóa | Có thể phục vụ đọc mà không phải vào đĩa. |
| **Bloom filter** | Loại bỏ các SSTable chắc chắn không chứa partition key | Có thể báo *có thể có* dù thực tế không có; không dùng để chứng minh row tồn tại. |
| **Partition index** | Tìm vị trí dữ liệu của partition trong SSTable | Là bộ phận nền của primary indexing vật lý. |
| **Index summary** | Thu gọn/sampling thông tin index ở một số format | Giúp giảm RAM/index lookup, không phải danh sách mọi row. |
| **Row/partition block index** | Hỗ trợ định vị phần dữ liệu trong partition rộng | Cấu trúc và tên file thay đổi theo format. |
| **Data component** | Lưu nội dung row, cell và các metadata liên quan | Chỉ mục dẫn đến dữ liệu, không thay thế dữ liệu. |

**Lưu ý theo phiên bản:**

- Với định dạng SSTable truyền thống (thường gọi **BIG**), tài liệu mô tả `Index.db` ánh xạ partition key tới vị trí trong `Data.db`, `Summary.db` lấy mẫu index và `Filter.db` lưu Bloom filter.
- Cassandra 5.0 có định dạng chỉ mục **Big Trie (BTI)** với các thành phần `Partitions.db` và `Rows.db` thay cho `Index.db` kiểu cũ. Cụ thể format và file thực tế còn phụ thuộc phiên bản/config và SSTable đang có.
- Vì vậy không nên viết công cụ vận hành dựa trên giả định **mọi** SSTable hiện tại phải có đúng `Index.db` hoặc `Summary.db`. Hãy kiểm tra format/tài liệu chính thức của phiên bản chạy.

### 4.3. Đường đọc qua primary index

Giả sử đọc toàn bộ các row của một partition đã biết:

1. Coordinator dùng partition key để xác định replica theo token/ring.
2. Replica kiểm tra dữ liệu liên quan trong memtable và các SSTable có thể chứa khóa.
3. Bloom filter có thể loại trừ một số SSTable **chắc chắn không có** partition.
4. Partition index và cấu trúc phụ trợ giúp định vị partition trong những SSTable liên quan.
5. Với điều kiện clustering, Cassandra chọn **row hoặc khoảng row** cần thiết trong partition theo thứ tự đã lưu.
6. Replica/coordinator xử lý timestamp, tombstone, consistency và trả kết quả hợp lệ cho ứng dụng.

Vì dữ liệu có thể nằm trong nhiều SSTable, tìm đúng partition **không có nghĩa chỉ cần đúng một lần đọc đĩa**. Số SSTable, độ rộng partition, compaction, cache, tombstone và tình trạng replica đều tác động chi phí thực tế.

### 4.4. Không phải B-tree index của RDBMS

Primary indexing trong Cassandra mang tính **định vị theo partition** trong hệ phân tán và LSM storage, không giống một index B-tree cho phép chạy tùy ý `WHERE age > 18 ORDER BY score` trên bảng lớn.

Với query chỉ lọc `event_type = 'temperature'` mà không có partition key, primary index không có căn cứ định vị tập partition phù hợp. Muốn hỗ trợ truy vấn ấy, phải **thiết kế bảng theo truy vấn** hoặc đánh giá giải pháp index bổ sung phù hợp phiên bản.

## 5. Lab CQL: từ primary key đến kết quả đọc

### 5.1. Dựng schema trên Cassandra lab một node

Giả định đã chạy Cassandra và có `cqlsh` trên `127.0.0.1:9042`:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS primary_index_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS primary_index_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE primary_index_lab.events_by_device_day;
~~~

`SimpleStrategy` và RF = 1 chỉ dùng để **học trên một node**. Khi triển khai nhiều datacenter, phải xem xét `NetworkTopologyStrategy` với RF theo từng DC, nhất là khi đánh giá `LOCAL_QUORUM`. Nếu bảng đã tồn tại với schema khác, `IF NOT EXISTS` **không sửa schema cũ**; hãy kiểm tra `DESCRIBE TABLE` trước khi tiếp tục.

### 5.2. Tạo fixture với primary key cố định

~~~sql
INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.3);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:10:00Z',
        33333333-3333-4333-8333-333333333333, 'humidity', 60.0);

INSERT INTO primary_index_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:03:00Z',
        44444444-4444-4444-8444-444444444444, 'temperature', 23.8);
~~~

Các timestamp có `Z` (UTC), UUID cố định. Chạy lại với cùng khóa chính sẽ **upsert** cùng row, không tự tăng số row như một log append-only. Vì Cassandra xử lý ghi theo timestamp, không dùng việc chạy lại script để suy ra thứ tự ghi ở các client đồng thời.

### 5.3. Truy cập một partition bằng primary index

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Kỳ vọng **3 row** của `sensor-01`, lần lượt:

| event_time (UTC) | event_type | value |
| --- | --- | ---: |
| 2026-11-21 01:10 | humidity | 60.0 |
| 2026-11-21 01:05 | temperature | 25.3 |
| 2026-11-21 01:00 | temperature | 25.1 |

Nếu bạn chạy một lần trước đó và tự chèn thêm row trong cùng partition, số row có thể khác. Để kiểm tra đúng bài, dùng keyspace/bảng lab mới hoặc dữ liệu được reset **chỉ trên lab độc lập** theo chính sách phù hợp; không dùng `TRUNCATE` bừa bãi trên cluster chia sẻ.

Tại sao truy vấn này hiệu quả về mặt định tuyến?

- `device_id` **và** `event_day` xác định trọn composite partition key.
- Replica có thể tìm đúng partition nhờ primary indexing.
- Rows trong partition đã được sắp theo clustering key; không cần sort dữ liệu của mọi partition.

### 5.4. Truy cập một khoảng clustering key

~~~sql
SELECT event_time, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T01:05:00Z';
~~~

Kết quả kỳ vọng **2 row** lúc `01:10` và `01:05`. Cassandra đã xác định **một partition** trước khi áp dụng điều kiện range lên clustering column đầu tiên. Đây là lợi ích chính của thiết kế **partition + ordered range**.

Lấy một row có đầy đủ primary key:

~~~sql
SELECT event_time, event_type, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T01:05:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Kỳ vọng **1 row** với `temperature / 25.3`. Khi đã cung cấp đủ partition key cùng toàn bộ clustering columns, query nhắm vào một row cụ thể.

### 5.5. Thứ tự clustering và ORDER BY

Bảng khai báo:

~~~sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

Khi đọc một partition, thứ tự mặc định thường là `event_time DESC`, với `event_id ASC` để sắp các row có cùng thời điểm. Có thể dùng `ORDER BY` theo thứ tự phù hợp được CQL cho phép, ví dụ đảo chiều của toàn bộ clustering order:

~~~sql
SELECT event_time, event_id, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC
LIMIT 10;
~~~

Kỳ vọng `01:00` trước `01:05` rồi `01:10`. **ORDER BY trên clustering columns không phải ORDER BY toàn cluster**, và Cassandra hạn chế những thứ tự/kiểu lọc không phù hợp schema. Không dùng `ORDER BY value` cho regular column rồi kỳ vọng Cassandra tự sort mọi partition.

`LIMIT 10` chỉ giới hạn lượng row trả về trong ngữ cảnh truy vấn. Nó không biến truy vấn thiếu partition key thành truy vấn định vị hiệu quả; `LIMIT` trên một truy vấn quét rộng vẫn có thể gây chi phí đáng kể.

## 6. Những truy vấn sai và nguyên nhân từ primary index

### 6.1. Bỏ thiếu thành phần composite partition key

~~~sql
-- Không có đủ partition key (thiếu event_day):
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01';
~~~

Vì partition key gồm **cả** `device_id` và `event_day`, chỉ biết `device_id` chưa đủ để tính token/định vị partition cụ thể. Cassandra thường từ chối dạng truy vấn này trong bảng chưa có index khác phù hợp; tùy phiên bản có thể báo lỗi thiếu hoặc hạn chế partition key.

**Không nhầm:** query theo “một thiết bị qua mọi ngày” là nhu cầu nghiệp vụ khác query theo “một thiết bị trong một ngày”. Nếu nhu cầu nhiều ngày phổ biến, có thể thiết kế **bucket và nhiều query có kiểm soát** hoặc một bảng khác được xây cho truy vấn ấy; tránh quét toàn cluster.

### 6.2. Chỉ có clustering column

~~~sql
-- Không xác định partition nào; không thể tận dụng clustering order toàn bảng.
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE event_time >= '2026-11-21T01:05:00Z';
~~~

Clustering key chỉ có ý nghĩa định vị **sau khi đã biết partition**. Query theo `event_time` trên mọi thiết bị sẽ cần phương án data modeling khác, index thích hợp hoặc pipeline phân tích bên ngoài. Không nên chọn `ALLOW FILTERING` làm cách chữa chung.

### 6.3. Bỏ qua tiền tố clustering

~~~sql
-- Đã biết partition nhưng bỏ event_time để lọc bằng event_id.
SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Theo thứ tự clustering `(event_time, event_id)`, thường phải ràng buộc **tiền tố clustering** trước khi dùng cột phía sau để tìm row hiệu quả. Không có `event_time` thì `event_id` không phải một đường tìm row được sắp độc lập trong partition.

### 6.4. Lọc trên regular column

~~~sql
-- event_type không có trong primary key, bảng chưa tạo index phụ.
SELECT device_id, event_day, event_time, value
FROM primary_index_lab.events_by_device_day
WHERE event_type = 'temperature';
~~~

Primary index không tra được danh sách partition theo `event_type`. Nếu nhu cầu nghiệp vụ là “xem tất cả temperature events”, cân nhắc:

1. Một bảng **thiết kế theo truy vấn**, ví dụ group theo event_type và time bucket với partition key/cardinality phù hợp.
2. Secondary index/SAI nếu **đúng phiên bản**, workload và đặc điểm cardinality/selectivity, sau khi benchmark.
3. Hệ thống phân tích/tổng hợp dữ liệu riêng nếu thực sự cần quét/aggregate toàn cluster.

Thêm `ALLOW FILTERING` có thể khiến Cassandra chấp nhận một số truy vấn vốn bị từ chối nhưng kéo theo quét/lọc lượng lớn dữ liệu; **nó không tạo primary index** và không bảo đảm query nhanh trên dataset lớn.

### 6.5. Bảng so sánh query patterns

| Query pattern | Có tận dụng primary indexing trực tiếp? | Đánh giá |
| --- | --- | --- |
| Đủ `device_id` và `event_day` | **Có** | Định vị một partition. |
| Đủ partition + `event_time = ?` | **Có** | Tìm row/range trong một partition. |
| Đủ partition + range trên `event_time` | **Có** | Đọc đoạn liên tiếp theo clustering order. |
| Đủ partition + đầy đủ clustering key | **Có** | Điểm row cụ thể. |
| Chỉ `device_id` | **Không đầy đủ** | Thiếu thành phần composite partition key. |
| Chỉ `event_time` | **Không** | Clustering chỉ có ý nghĩa trong partition đã xác định. |
| Đủ partition nhưng chỉ lọc `event_id` | **Không theo prefix clustering** | Bỏ qua `event_time`. |
| Chỉ `event_type` | **Không** | Regular column, chưa có index phụ. |
| `SELECT ... LIMIT 10` không WHERE | **Không phải point lookup** | Vẫn phải duyệt/phân phối công việc đọc phù hợp. |

**Ngoại lệ có chủ đích:** CQL có hỗ trợ một số query theo `TOKEN(...)` hoặc `IN` để đọc nhiều partition và một số index phụ. Chúng có quy tắc riêng, không làm thay đổi nguyên tắc thiết kế truy vấn hiệu quả: ưu tiên biết partition key và giới hạn lượng dữ liệu mỗi partition.

## 7. Primary index và secondary indexing khác nhau ở đâu?

Trong Cassandra, từ “index” thường được dùng cho nhiều cơ chế, cần phân biệt:

| Loại | Tạo ra bằng cách nào? | Tra cứu theo đâu? | Đánh đổi |
| --- | --- | --- | --- |
| **Primary index** | **Tự động** khi định nghĩa `PRIMARY KEY` của bảng | Partition key; sau đó truy vấn clustering rows | Phải thiết kế schema theo access pattern; rất hiệu quả nếu biết khóa. |
| **Secondary index cũ (2i)** | Tạo index qua CQL khi phiên bản hỗ trợ | Non-primary key column được index | Index thường cục bộ mỗi node; truy vấn có thể tốn nhiều node nếu thiếu partition key. |
| **Storage-Attached Index (SAI)** | Tạo index theo cú pháp/khả năng của phiên bản hỗ trợ, **Apache Cassandra 5.0** | Cột được lập index gắn với SSTable | Có thêm storage/chi phí maintenance; cần đánh giá workload và giới hạn predicate. |
| **Bảng truy vấn bổ sung** | Tạo một bảng khác với primary key phù hợp và ghi đồng bộ từ ứng dụng | Một access pattern khác | Phải duy trì dữ liệu ở nhiều bảng, xử lý nhất quán ở tầng ứng dụng. |

Khi không có chỉ mục phụ, Cassandra **không tự lập index trên mọi regular column**. Khi có SAI/2i, việc một câu CQL có thể chạy vẫn **không bảo đảm độ trễ thấp hoặc chi phí ổn định** ở mọi cardinality, phân vùng, kích thước dữ liệu và cluster topology.

### 7.1. Khi nào nên chọn bảng mới thay vì index phụ?

Ví dụ nghiệp vụ có hai kiểu truy vấn:

- **Q1:** “Các sự kiện của `sensor-01` ngày `2026-11-21`” → bảng `events_by_device_day` hiện tại phù hợp.
- **Q2:** “Các sự kiện `temperature` ngày `2026-11-21` tại một site” → nên đánh giá một bảng được bucket theo **site + event_type + day**, với clustering theo thời gian và phân phối khóa tránh hotspot; hoặc SAI/analytics nếu nhu cầu phức tạp.

Không nên tạo partition khổng lồ kiểu `PRIMARY KEY ((event_type), event_time, device_id)` chỉ vì chỉ còn hai giá trị `event_type`. Partition key cardinality quá thấp gây **hot partitions** và chênh lệch tải giữa replica.

### 7.2. Index phụ không chữa được mọi lỗi dữ liệu

Một secondary index có thể giúp tìm một tập giá trị không thuộc primary key, nhưng không thay thế:

- **Partition sizing** và time bucketing hợp lý.
- Khả năng chịu tải replica, RF/CL và đường internode.
- Thiết kế để tránh **hot keys** và các partition cực lớn.
- Phân tích chi phí query/range, compaction, tombstones và disk I/O.
- Phân biệt truy vấn OLTP theo khóa với analytics quét toàn dataset.

## 8. Thiết kế partition/clustering key từ access pattern

### 8.1. Quy trình thiết kế

Trước khi tạo bảng, ghi rõ:

1. **Ai truy vấn?** Một thiết bị cụ thể, một site, một khách hàng hay toàn hệ thống?
2. **Phải biết tham số nào trong WHERE?** Có thể cung cấp trọn partition key ở hầu hết request không?
3. **Có cần range hoặc thứ tự không?** Ví dụ 100 sự kiện mới nhất trong một ngày.
4. **Tốc độ ghi của một key là bao nhiêu?** Một device có thể ghi hàng trăm nghìn row/ngày không?
5. **Số row/kích thước partition dự kiến?** Bucket ngày, giờ hoặc tháng nên dựa trên dữ liệu thật.
6. **Mức phân bố khóa?** Một số device phát sinh 90% traffic có làm nóng vài replica không?
7. **RF/CL và topology?** Truy vấn phục vụ local DC, nhiều DC hay cần mức bảo đảm mạnh hơn?

Chỉ sau khi trả lời, mới chọn:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

Lựa chọn này phù hợp query theo thiết bị và ngày. Nó không tự phù hợp cho mọi báo cáo theo `event_type`, site hoặc phân tích tổng thể.

### 8.2. Bucket quá rộng và quá hẹp

| Thiết kế | Rủi ro |
| --- | --- |
| `PRIMARY KEY ((device_id), event_time)` | Partition của thiết bị có thể lớn mãi khi ghi liên tục. |
| `PRIMARY KEY ((device_id, event_day), event_time)` | Hợp lý khi lượng row/ngày vừa phải và truy vấn theo ngày. |
| `PRIMARY KEY ((device_id, event_hour), event_time)` | Giảm độ rộng partition nếu traffic cao, nhưng đọc 24 giờ cần nhiều partition. |
| `PRIMARY KEY ((event_type), event_time)` | Một vài event type tạo partition rất nóng và rộng. |
| Bucket quá nhỏ | Nhiều partition cần truy cập hơn cho một query dài hạn, tăng overhead quản lý. |

Không có bucket nào tối ưu cho mọi dịch vụ. Với Cassandra, lựa chọn tốt phụ thuộc **số row, kích thước row, tần suất truy vấn, p95/p99 latency và phân bố tải**.

### 8.3. ORDER BY trong một partition, không phải toàn bảng

Nếu yêu cầu “trả 20 sự kiện mới nhất của mọi thiết bị”, câu truy vấn sẽ không tự được giải quyết bằng `ORDER BY event_time DESC LIMIT 20` trên bảng `events_by_device_day`. Vì các partition được phân tán theo token, thứ tự clustering chỉ có nghĩa **trong từng partition**. Cần mô hình truy vấn/bảng khác hoặc pipeline tổng hợp nếu muốn một danh sách toàn cục có thứ tự.

## 9. Đọc metadata để tự kiểm chứng primary key

Trong cqlsh:

~~~sql
DESCRIBE TABLE primary_index_lab.events_by_device_day;

SELECT column_name, kind, position, type, clustering_order
FROM system_schema.columns
WHERE keyspace_name = 'primary_index_lab'
  AND table_name = 'events_by_device_day';
~~~

Kết quả `system_schema.columns` dự kiến có:

| column_name | kind | Ghi chú |
| --- | --- | --- |
| `device_id` | `partition_key` | Thành phần thứ nhất của composite partition key. |
| `event_day` | `partition_key` | Thành phần thứ hai của partition key. |
| `event_time` | `clustering` | Clustering column thứ nhất, `DESC`. |
| `event_id` | `clustering` | Clustering column thứ hai, `ASC`. |
| `event_type`, `value` | `regular` | Không thuộc primary key. |

Đừng dùng **thứ tự row** mà `SELECT` từ system table trả về làm chỉ báo thứ tự khóa. Đọc `kind`, `position` và `clustering_order` cùng câu `CREATE TABLE`.

Kiểm tra replication của lab:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'primary_index_lab';
~~~

`replication` giải thích các bản sao dữ liệu được đặt ở đâu, nhưng không tự cho biết node nào đang Up/Down hay request có đạt CL. Cần thêm `nodetool status` và metrics nếu điều tra sự cố phân tán.

### 9.1. TRACING: quan sát đường thực thi trong lab

~~~sql
TRACING ON;

SELECT event_time, value
FROM primary_index_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;

TRACING OFF;
~~~

Trace có thể giúp thấy coordinator, thao tác đọc và thời gian của các bước. Nó có **overhead**, ID/timing thay đổi theo lần chạy và không phải phép đo benchmark không nhiễu. Chỉ bật cho số lượng truy vấn nhỏ có chủ đích; không giữ `TRACING ON` trên workload production lớn.

### 9.2. Quan sát partition width và SSTable khi truy vấn chậm

~~~bash
# Chạy từ node quản trị có quyền; không phải câu lệnh cqlsh.
nodetool tablestats primary_index_lab.events_by_device_day

# Thống kê độ rộng/số row partition (cú pháp tùy version).
nodetool tablehistograms primary_index_lab events_by_device_day

# Xem compaction đang diễn ra.
nodetool compactionstats
~~~

Kiểm tra log/metrics về SSTable count, tombstone, read latency, partition size, GC, disk I/O và cache. Lệnh `nodetool` sử dụng đường quản trị/JMX theo phiên bản, **không dùng native CQL 9042** như Java Driver. Không chạy `nodetool compact` hoặc `repair` chỉ để chữa một câu SELECT chậm mà chưa chẩn đoán chi phí và tình trạng dữ liệu.

## 10. Java Driver: prepared statement theo partition key

Ví dụ cho **Java Driver 4.x** và bảng lab đã tạo. Truy vấn luôn ràng buộc **đủ partition key** và giới hạn khoảng clustering.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;

public class PrimaryIndexQueryDemo {
    public static void main(String[] args) {
        // datacenter1 chỉ là ví dụ; thay bằng giá trị từ system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, event_type, value " +
                "FROM primary_index_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? " +
                "AND event_time >= ?");

            BoundStatement bound = prepared.bind(
                    "sensor-01",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T01:05:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100);

            for (Row row : session.execute(bound)) {
                System.out.println(
                    row.getInstant("event_time") + " / " +
                    row.getUuid("event_id") + " / " +
                    row.getString("event_type") + " / " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

**Đọc đoạn Java theo lớp:**

1. `PreparedStatement` chứa câu CQL có placeholder, không nối chuỗi dữ liệu do người dùng cung cấp.
2. `device_id`, `event_day` được bind đầy đủ để định vị partition; `event_time` là giới hạn clustering.
3. Driver trao đổi qua **native protocol**, có thể chọn coordinator phù hợp dựa trên metadata/token awareness.
4. `setConsistencyLevel(ONE)` đặt CL cho **statement Java**. Nó không phụ thuộc lệnh `CONSISTENCY` ở một phiên cqlsh khác.
5. `setPageSize(100)` điều khiển số row được yêu cầu theo page của driver (không đồng nghĩa toàn bộ query chỉ trả tối đa 100 row).

Trong hệ thống thật, cần cung cấp credentials, TLS/CA, contact points có thể truy cập được, local datacenter đúng và retry/timeout phù hợp. Tên `datacenter1` **không phải giá trị cố định**; kiểm tra bằng:

~~~sql
SELECT data_center, release_version FROM system.local;
~~~

`CqlSession` nên có vòng đời dài và tái sử dụng trong service. Nếu bảng vừa thay schema, cần xem schema agreement và cơ chế refresh metadata/reprepare của driver thay vì kết luận primary index “mất”.

## 11. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Query `WHERE device_id = ?` bị từ chối | Thiếu `event_day` của composite partition key | Ràng buộc đủ khóa hoặc thiết kế bảng hỗ trợ truy vấn nhiều ngày. |
| Query chỉ có `event_time` không chạy | Clustering không định vị partition trên toàn bảng | Thêm full partition key hoặc dùng mô hình/index khác phù hợp. |
| Query theo `event_id` trong partition bị từ chối | Bỏ tiền tố clustering `event_time` | Đưa điều kiện theo clustering prefix hoặc đánh giá data model. |
| Query `event_type = ?` không chạy | Regular column không có đường truy cập primary index | Thiết kế bảng theo query hoặc đánh giá SAI/2i được hỗ trợ. |
| `ALLOW FILTERING` cho phép query nhưng rất chậm | Cần quét/lọc nhiều partition/row | Tránh full scan; thiết kế partition key/index phù hợp. |
| `ORDER BY value` bị từ chối | `value` không phải clustering column | Chọn bảng theo thứ tự truy vấn hoặc xử lý ở tầng phù hợp. |
| `ReadTimeout` dù có full partition key | Hot/large partition, replica chậm, SSTable/tombstone/GC/network | Xem partition size, CL, node health, compaction và tracing chọn lọc. |
| `Unavailable` ở `LOCAL_QUORUM` | Không đủ replica khả dụng theo RF/DC/CL | Xem keyspace replication, topology và mạng internode; không hạ CL tùy tiện. |
| Kết quả trông khác sau khi upsert | Cùng primary key, cell timestamp hoặc concurrent writes | Xem dữ liệu fixture, write timestamp, TTL và quy tắc ghi. |
| Java kết nối được nhưng vài query mất node | Driver discovery, native endpoint, topology/route | Xem `broadcast_rpc_address`, local DC, TLS/auth và log từng node. |
| Đọc đúng partition nhưng latency vẫn cao | Có nhiều SSTable/partition rộng/row lớn hoặc tải hệ thống | Theo dõi p95/p99, metrics, compaction và thiết kế bucket. |

### 11.1. Checklist phân tích một truy vấn chậm

1. **Đúng table/keyspace?** `DESCRIBE TABLE` và metadata có cùng schema với câu query không?
2. **Đủ partition key?** Với composite key, đã đủ **tất cả thành phần** và đúng kiểu dữ liệu chưa?
3. **Clustering predicates hợp lệ?** Có đi theo tiền tố clustering và tạo khoảng liên tiếp không?
4. **Độ rộng partition?** Có hot device hoặc bucket ngày quá lớn không?
5. **RF/CL và replica?** Node/dc nào nhận request, tình trạng gossip và internode thế nào?
6. **Memtable/SSTable?** Số file, compaction, tombstone, cache, disk I/O có bất thường?
7. **Client?** Java Driver có dùng đúng prepared statement, local DC, page size và timeout không?
8. **Đánh giá có kiểm soát:** đo nhiều lần trên dataset đại diện, không suy từ một trace duy nhất.

## 12. Bài tập tự thực hành

1. Nêu khác biệt giữa `PRIMARY KEY (a, b, c)` và `PRIMARY KEY ((a, b), c)`. Chỉ rõ partition key và clustering columns.
2. Tạo `primary_index_lab.events_by_device_day` và dữ liệu mẫu. Dùng `DESCRIBE TABLE` để xác minh composite partition key.
3. Chạy `SELECT` lọc đủ `device_id` + `event_day`. Liệt kê ba row theo `event_time DESC` rồi giải thích tại sao không cần global sorting.
4. Thêm điều kiện `event_time >= '2026-11-21T01:05:00Z'`; dự đoán số row và lý giải vai trò range của clustering column đầu tiên.
5. Truy vấn bằng toàn bộ primary key của row `01:05` và xác nhận chỉ có một row.
6. Bỏ điều kiện `event_day`; ghi lỗi cqlsh và giải thích tại sao `device_id` riêng lẻ không đủ để tính token composite partition.
7. Bỏ `event_time` nhưng lọc `event_id`. Vì sao thứ tự clustering không hỗ trợ đường tra cứu mong muốn?
8. Thử `SELECT` theo regular column `event_type` khi chưa tạo index phụ. So sánh với truy vấn có partition key và nêu rủi ro `ALLOW FILTERING`.
9. Dùng `system_schema.columns` để liệt kê `kind`, `position` và `clustering_order`. Giải thích vai trò của các trường này.
10. Vẽ đường đi client → coordinator → token/replica → memtable/SSTable và nêu Bloom filter có thể/chắc chắn kết luận điều gì.
11. Giải thích vì sao một partition có thể trải trên nhiều SSTable và vì sao compaction ảnh hưởng hiệu năng đọc nhưng không làm thay đổi primary key.
12. Thiết kế bảng hỗ trợ truy vấn “20 temperature events mới nhất của một site trong một ngày” mà không tạo partition quá lớn. Nêu các giả định về traffic/bucket.
13. So sánh primary indexing, 2i và SAI; nói rõ tại sao tính khả dụng của SAI phụ thuộc phiên bản và index phụ không mặc định giải quyết hotspot.
14. Chạy Java Driver query `sensor-01` với range trên `event_time`; giải thích sự khác nhau giữa statement CL của Java và lệnh `CONSISTENCY` của cqlsh.

**Tiêu chí hoàn thành:** nhìn vào `CREATE TABLE` là xác định đúng partition/clustering key; biết vì sao query theo khóa nhanh hơn quét/lọc, viết được point/range queries hợp lệ; hiểu primary index được duy trì tự động và có cấu trúc SSTable phụ thuộc phiên bản; đánh giá được hậu quả của hot/large partition khi thiết kế dữ liệu cho Cassandra.

## Tài liệu tham khảo

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/indexing-concepts.html): primary indexing dựa trên partition key, secondary index 2i và SAI.
- [Apache Cassandra — Data Definition (DDL)](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html): `PRIMARY KEY`, composite partition key, clustering columns và `CLUSTERING ORDER BY`.
- [Apache Cassandra — Data Manipulation (DML)](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): quy tắc `WHERE`, clustering range, `ORDER BY`, `TOKEN`, `IN` và `ALLOW FILTERING`.
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html): commit log, memtable, SSTable, Bloom filter, partition index và biến thể Big Trie.
- [Apache Cassandra — Bloom Filters](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bloom_filters.html): loại trừ SSTable khi đọc theo partition key và xác suất false positive.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): quan sát `tablestats`, `tablehistograms` và `compactionstats`.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): `CqlSession`, prepared statements, consistency và paging.
