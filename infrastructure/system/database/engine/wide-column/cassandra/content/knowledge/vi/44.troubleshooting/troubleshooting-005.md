# InvalidQuery do điều kiện khóa, kiểu dữ liệu hoặc truy vấn không được hỗ trợ trong Apache Cassandra

## 1. Mục tiêu và phạm vi bài học

Trong Apache Cassandra, một câu CQL hợp lệ về **cú pháp** vẫn có thể bị từ chối khi chạy vì không phù hợp với **partition key, clustering key, type, index, loại statement hoặc quy tắc truy vấn**. Ở ứng dụng Java Driver, lỗi có thể xuất hiện dưới dạng `InvalidQueryException`, một ngoại lệ server khác, hoặc **lỗi codec/bind ngay tại client** trước khi request được gửi đi.

Bài học thuộc chương **Xử lý sự cố** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Nó liên kết trực tiếp đến mục tiêu của module: hiểu mô hình wide-column và partition routing, thiết kế bảng theo truy vấn, replication/consistency, thực hành CQL và kết nối Java.

Sau bài, bạn sẽ:

1. Phân biệt `InvalidQuery` với `SyntaxError`, `Unauthorized`, lỗi chuẩn bị/bind CQL, timeout và unavailable.
2. Đọc đúng thông báo server mà không **phụ thuộc string message cố định** giữa các Cassandra releases.
3. Chẩn đoán lỗi thiếu/thừa **partition key**, sai thứ tự/range của clustering columns.
4. Sửa các truy vấn `ORDER BY`, `IN`, filtering, secondary-index và các phép tổng hợp không phù hợp.
5. Phân biệt kiểu dữ liệu CQL với Java Driver 4.x: `uuid`, `date`, `timestamp`, `timeuuid`, `decimal`, `varint`, collection và UDT.
6. Hiểu tình huống DML không hỗ trợ, đặc biệt **counter, TTL, LWT, batch** và không được suy từ SQL quan hệ.
7. Viết truy vấn CQL đúng bằng **prepared statement và bind parameters**, đồng thời xử lý null/unset an toàn.
8. Xây dựng runbook triage theo lỗi, schema thực, query template và workload thực.
9. Thiết kế test negative/positive và checklist trước khi sửa ứng dụng hoặc migration schema.

**Phạm vi phiên bản:** Ví dụ sử dụng các khái niệm CQL phổ biến trong Cassandra 4.x/5.x và Java Driver 4.x. Một số restrictions, index support, `GROUP BY`, `IN`, `LIKE`, `ANN`, JSON, SAI/SASI, duration, DDL và tên exception có thể thay đổi theo Cassandra/server/distribution/driver. **Không khẳng định một câu CQL không hỗ trợ ở mọi phiên bản chỉ từ một thông điệp của một cluster.** Khi khác biệt có ý nghĩa, bài nêu điều kiện cần xác minh.

**Nguyên tắc thực hành:** Chỉ thực hiện mutation/DDL trong keyspace lab được phép. Đừng chạy `ALLOW FILTERING`, scan lớn, `TRUNCATE` hoặc migration production chỉ để “test xem lỗi có biến mất không”.

## 2. `InvalidQuery` nằm ở đâu trong vòng đời yêu cầu?

~~~mermaid
flowchart TD
    A["Ứng dụng Java tạo statement"] --> B{"Bind/codec hợp lệ?"}
    B -->|"Không"| C["Client-side type/bind/codec exception"]
    B -->|"Có"| D["Native protocol tới coordinator"]
    D --> E{"Parse CQL syntax?"}
    E -->|"Không"| F["SyntaxError hoặc tương đương"]
    E -->|"Có"| G{"Validate schema, key, type, CQL rules?"}
    G -->|"Không"| H["InvalidQuery hoặc server validation error"]
    G -->|"Có"| I{"Role được phép?"}
    I -->|"Không"| J["Unauthorized/auth-related error"]
    I -->|"Có"| K["Route / replica read-write theo CL"]
    K --> L{"Phục vụ thành công?"}
    L -->|"Không"| M["Timeout / Unavailable / execution error"]
    L -->|"Có"| N["ResultSet / AsyncResultSet"]
~~~

Sơ đồ chỉ mô tả **các lớp kiểm tra về mặt khái niệm**, không cam kết thứ tự nội bộ chính xác trong mọi version (ví dụ authorization/schema validation hoặc prepare có thể diễn ra ở các giai đoạn khác nhau).

### 2.1. Một số nhóm ngoại lệ

| Nhóm | Dấu hiệu thông thường | Điều tra ở đâu? |
|---|---|---|
| `InvalidQueryException` | Server từ chối câu CQL sau khi phân tích/validate | Schema, PK, clustering, type, CQL operation |
| `SyntaxError` | Câu lệnh không parse theo ngữ pháp CQL | Từ khóa, dấu phẩy, ngoặc, quotation |
| Client codec/bind error | Java value không mã hóa được thành CQL type | `PreparedStatement` metadata, Java getters/setters, codecs |
| `UnauthorizedException` | Role không đủ quyền | Role/grants/authorizer, không đổi PK |
| `AuthenticationException` | Credentials/role LOGIN không hợp lệ | Authenticator, session credentials |
| `UnpreparedException` hoặc prepare-related | Prepared statement id không còn được node biết | Driver prepare/reprepare, schema changes |
| `ReadTimeoutException` / `WriteTimeoutException` | Request có thể tới replica, không đủ phản hồi đúng hạn | RF/CL, latency, node health |
| `UnavailableException` | Không đủ replica đáp ứng CL trước khi thực thi | Topology/liveness, RF/CL |
| `AllNodesFailedException` | Driver không có candidate coordinator phục vụ | Cause per-node; network/TLS/server availability |

Một HTTP 500 hoặc `CompletionException` là **vỏ bọc**, không phải root cause. Giữ class/cause chain, loại operation, keyspace, query template ID và version để phân loại.

### 2.2. Không tìm nguyên nhân từ một dòng message

Ví dụ các thông điệp có thể gặp (chỉ minh họa, **không đảm bảo nguyên văn**):

~~~text
Cannot execute this query as it might involve data filtering...
Some partition key parts are missing...
Cannot restrict clustering column ...
ORDER BY is only supported when ...
Invalid ... constant ...
Cannot use ... for counters ...
~~~

Một message chứa “filtering” thường chỉ ra access path chưa có partition/index phù hợp; không có nghĩa đây là lỗi tài nguyên heap. Một message “Invalid ... constant” có thể do literal/type, khác với Java codec exception trước khi request được gửi.

## 3. Schema chuẩn xuyên suốt bài

### 3.1. Keyspace lab một node

~~~cql
-- Chỉ cho Cassandra lab có một node.
CREATE KEYSPACE IF NOT EXISTS troubleshooting_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
}
AND durable_writes = true;
~~~

`SimpleStrategy` RF=1 chỉ dành cho **lab một node**. Production nhiều datacenter thường cần `NetworkTopologyStrategy`, RF theo DC, và consistency level phù hợp. **Không chỉnh RF/CL production để làm một truy vấn InvalidQuery chạy được.**

### 3.2. Bảng thiết kế theo truy vấn “thiết bị trong ngày”

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.readings_by_device_day (
        device_id uuid,
        event_day date,
        event_time timestamp,
        reading_value double,
        status text,
        source text,
        PRIMARY KEY ((device_id, event_day), event_time)
    )
WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Ở đây:

- **Composite partition key:** `(device_id, event_day)`. Cả hai giá trị quyết định partition/token.
- **Clustering column:** `event_time`, sắp theo thời gian giảm dần trong partition.
- **Regular columns:** `reading_value`, `status`, `source`, không mặc định là index.
- Không có foreign key/joins như trong SQL quan hệ.
- Một **full primary key** là `(device_id,event_day,event_time)`; nếu hai events có cùng millisecond trong cùng partition thì sẽ cạnh tranh cùng row. Thêm `event_id` vào clustering key nếu cần phân biệt events cùng thời điểm.

### 3.3. Seed dữ liệu giả định

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value,
   status, source)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', '2026-11-21T09:00:00Z',
   25.4, 'OK', 'edge');

INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value,
   status, source)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', '2026-11-21T09:05:00Z',
   25.9, 'WARN', 'edge');
~~~

**Lưu ý:** đây là CQL minh họa, chưa được chạy trong môi trường thực. `date` biểu diễn ngày lịch, `timestamp` biểu diễn thời điểm với độ chính xác thường là millisecond. Java cần thống nhất quy ước tính `event_day` theo UTC hay một timezone nghiệp vụ — nếu sai bucket, query có thể **hợp lệ nhưng trả 0 row**, không phải `InvalidQuery`.

### 3.4. Truy vấn đúng cho bảng

~~~cql
SELECT event_time, reading_value, status
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
ORDER BY event_time DESC
LIMIT 20;
~~~

Ở production, dùng **prepared statement/bind**, không nối trực tiếp UUID/ngày từ request của người dùng vào CQL string.

## 4. Sai điều kiện partition key

### 4.1. Thiếu một thành phần của composite partition key

~~~cql
-- Sai cho access path thông thường của bảng này.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111;
~~~

Cassandra không tự biết `event_day` để xác định duy nhất partition; query thường bị từ chối hoặc yêu cầu cơ chế filtering/index phù hợp. Đây không phải “Cassandra mất dữ liệu”.

Sửa đúng nếu API đã biết ngày:

~~~cql
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

### 4.2. Chỉ có ngày mà không có device ID

~~~cql
-- Không phù hợp với partition key trên:
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE event_day = '2026-11-21';
~~~

Nếu nghiệp vụ cần “mọi thiết bị trong một ngày”, đó là **truy vấn khác**. Cân nhắc bảng riêng theo ngày/shard/người dùng/tenant, pipeline phân tích, hoặc storage/query engine thích hợp; không mặc định scan toàn bảng Cassandra phục vụ traffic online.

### 4.3. Query nhiều ngày của một thiết bị

Cassandra không có một partition duy nhất bao trùm mọi `event_day` cho device. Với khoảng ngày hữu hạn:

~~~text
Requested: device A, 2026-11-19 .. 2026-11-21

Application:
  SELECT partition (A, 2026-11-19)
  SELECT partition (A, 2026-11-20)
  SELECT partition (A, 2026-11-21)
  Merge results theo timestamp, giới hạn fan-out và bytes.
~~~

Đây là **cách orchestration có kiểm soát**, không tạo một truy vấn CQL thiếu partition key. Một số release hỗ trợ `IN` trong giới hạn nhất định, nhưng không có nghĩa query trên hàng nghìn partitions sẽ hiệu quả. Giới hạn số partition/bucket, thời gian, concurrency và pagination; khi cần query đa ngày thường xuyên, cân nhắc **table phục vụ truy vấn đó**.

### 4.4. Partition key không được null/unset

~~~cql
-- Sai: primary key không được null.
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value)
VALUES (null, '2026-11-21',
        '2026-11-21T09:00:00Z', 23.4);
~~~

Tất cả thành phần **primary key** của row phải xác định theo CQL semantics. Với Java, kiểm tra các bind markers `device_id`/`event_day`/`event_time` trước khi execute; bind `null` hoặc `unset` vào key có thể dẫn đến server validation error hoặc client-side bind error tùy đường đi/version.

### 4.5. Không thêm `ALLOW FILTERING` chỉ để “qua lỗi”

~~~cql
-- CẢNH BÁO: ví dụ chống-pattern,
-- không chạy trên bảng lớn.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN'
ALLOW FILTERING;
~~~

Trong một số cấu hình/release, `ALLOW FILTERING` cho phép Cassandra quét nhiều dữ liệu rồi bỏ hàng không khớp; tính hợp lệ chính xác tùy query/version/index. Nhưng:

- Số partitions/rows phải đọc có thể rất lớn.
- Thời gian và read amplification không được ràng buộc chỉ bởi số row trả về.
- Một `LIMIT 10` vẫn có thể yêu cầu scan nhiều dữ liệu.
- Dễ gây timeout, tombstone warnings, heap/GC/disk pressure.
- Không biến regular column thành indexed lookup.

**Giải pháp là đúng data model/access path**, không coi filtering là sửa lỗi truy vấn.

## 5. Clustering key: equality prefix và range

### 5.1. Bảng có nhiều clustering columns

Để phân biệt nhiều sự kiện trong cùng millisecond:

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.events_by_device_day (
        device_id uuid,
        event_day date,
        event_time timestamp,
        event_id uuid,
        event_type text,
        reading_value double,
        PRIMARY KEY (
          (device_id, event_day),
          event_time,
          event_id
        )
    )
WITH CLUSTERING ORDER BY (
  event_time DESC,
  event_id ASC
);
~~~

Cấu trúc chính:

~~~text
Partition key:
  (device_id, event_day)

Clustering order:
  event_time -> event_id

Regular columns:
  event_type, reading_value
~~~

### 5.2. Truy vấn hợp lệ theo partition + clustering prefix

~~~cql
SELECT event_time, event_id, event_type
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?;
~~~

Truy vấn này có đầy đủ partition key và một range trên **clustering column đầu tiên**. Nó phù hợp với use case đọc event theo giờ/phút trong một ngày.

~~~cql
SELECT event_time, event_id, event_type
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
  AND event_id = ?;
~~~

Truy vấn full primary key để đọc đúng một event.

### 5.3. Truy vấn nhảy qua clustering prefix

~~~cql
-- Không phù hợp với đường truy cập thông thường:
SELECT *
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_id = ?;
~~~

`event_id` là clustering column sau `event_time`. Khi không có restriction trên `event_time`, Cassandra thường không cho sử dụng restriction trên `event_id` như truy vấn định tuyến chính xác theo clustering key, trừ khi có index/filtering support phù hợp với phiên bản.

Cách sửa:

- Nếu biết `event_time`, bind cả time và ID.
- Nếu nghiệp vụ tra trực tiếp theo `event_id`, thiết kế bảng riêng `events_by_id`.
- Nếu chỉ cần query theo một filter khác, xem index/SAI phù hợp release và đo hiệu suất.
- Không lập tức thêm `ALLOW FILTERING` cho traffic lớn.

### 5.4. Range và các restrictions sau range

~~~cql
-- Chỉ nên dùng với sự hiểu biết rất rõ về rules/versions:
SELECT *
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time > ?
  AND event_id = ?;
~~~

Khi clustering column trước đã là range, giới hạn column phía sau có thể không được hỗ trợ hoặc đòi filtering, tùy dạng truy vấn/release. Quy tắc thiết kế thực dụng: **equality prefix trước, rồi đến range cần thiết**; nếu muốn tìm event ID độc lập với timestamp, dùng bảng theo ID.

### 5.5. Khóa clustering không phải cột có thể cập nhật

~~~cql
-- Không có semantics UPDATE primary key bằng SET.
UPDATE troubleshooting_lab.events_by_device_day
SET event_time = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
  AND event_id = ?;
~~~

Primary key xác định vị trí row; không thể chuyển `event_time` của một row bằng `SET`. Để “đổi khóa”, lập kế hoạch **INSERT row ở key mới và DELETE row cũ** theo quy tắc idempotency/consistency và backfill có kiểm soát. Hai mutation không được coi là một transaction ACID tổng quát.

## 6. `ORDER BY` và phạm vi sắp xếp

### 6.1. `ORDER BY` không phải SQL sort tùy cột

~~~cql
-- Hợp lý: sort theo clustering column trong một partition.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 20;
~~~

~~~cql
-- Sai theo schema: reading_value là regular column,
-- không phải clustering column.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY reading_value DESC
LIMIT 20;
~~~

Nếu ứng dụng cần “20 giá trị lớn nhất”, hãy:

1. Cân nhắc bảng/materialized representation theo query và retention.
2. Giữ dữ liệu theo bucket phù hợp để sắp xếp có thể phục vụ bằng clustering order.
3. Chỉ sort tại application khi result **đã bounded** nhỏ và đáp ứng SLO.
4. Dùng analytical engine khi cần top-N trên toàn tập lớn.

### 6.2. `ORDER BY` không tạo thứ tự toàn cluster

Một truy vấn chỉ `ORDER BY event_time` không giúp Cassandra sắp thứ tự trên mọi device/day partitions. Nếu query dùng nhiều partition values (chẳng hạn `IN` được release hỗ trợ), phạm vi/semantics thứ tự và chi phí phải kiểm chứng riêng.

**Đừng tuyên bố một p99 hoặc sort order toàn cluster** từ sự sắp xếp trong một partition.

### 6.3. Chiều sort và nhiều clustering columns

Với nhiều clustering columns, Cassandra hỗ trợ thứ tự theo clustering order đã định nghĩa và trong một số trường hợp đảo chiều tương thích. Các tổ hợp `ORDER BY event_time ASC, event_id ASC` không mặc nhiên hợp lệ khi schema định nghĩa **mixed directions**. Kiểm tra đầy đủ yêu cầu ORDER BY của release và thiết kế thứ tự truy cập ngay trong schema.

## 7. `IN`, filter trên regular columns và secondary indexes

### 7.1. `IN` có thể hợp lệ nhưng rất đắt

`IN` không phải phép JOIN. Các giới hạn về partition/clustering restrictions và kết hợp với `ORDER BY` phụ thuộc Cassandra release/query shape.

~~~cql
-- Một số bản Cassandra hỗ trợ IN ở những dạng điều kiện cụ thể.
-- Đây chỉ là mẫu kiểm tra trên lab; không đảm bảo mọi version.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day IN ('2026-11-20', '2026-11-21');
~~~

Nếu release/query path không hỗ trợ, thay bằng **hai prepared reads** theo partition cụ thể, với concurrency và result merge bounded. Nếu có hỗ trợ, vẫn cần giới hạn số ngày/partitions, timeout và resource budget.

### 7.2. Regular column predicate có thể cần index

~~~cql
-- Không có index trên status trong schema minh họa:
SELECT device_id, event_day, event_time
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN';
~~~

Cassandra **không** mặc định truy cập dữ liệu theo regular column như RDBMS query planner có secondary B-tree index tự động. Nhiều query dạng này bị từ chối vì filtering hoặc không được hỗ trợ.

Lựa chọn:

| Nhu cầu | Phương án |
|---|---|
| `status` trong đúng device/day | Đọc partition bounded rồi filter ở app nếu ít row |
| Tra status rộng trên nhiều partitions | Bảng theo status/time bucket/shard nếu yêu cầu đọc thường xuyên |
| Index hỗ trợ predicate | Xem secondary index/SAI theo đúng Cassandra version/distribution |
| Full text/complex search | Search engine chuyên dụng khi cần |
| Analytical aggregation/scan | Hệ thống analytical/batch, không ép online CQL |

### 7.3. Index không phải lời giải miễn phí

Index có thể tăng **write amplification**, memory/disk footprint, index build/rebuild, compaction và availability risks. Một `CREATE INDEX` không chứng minh query mới đáp ứng SLO.

Đánh giá bằng workload:

- Selectivity của giá trị và cardinality.
- Số partitions/rows match.
- Read p95/p99, tombstone scanning, CPU/heap/disk.
- Write throughput và compaction background.
- Điều kiện kết hợp nhiều predicates mà engine thực sự hỗ trợ.
- Version/Cassandra distribution: `2i`, `SAI`, `SASI` không có cùng semantics.

### 7.4. `LIKE`, `CONTAINS` và search operator phụ thuộc index/type

~~~cql
-- Không mặc định rằng câu này hoạt động trên text thường:
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE source LIKE '%edge%';
~~~

`LIKE`/pattern matching phải kiểm loại index và cú pháp được release hỗ trợ; không dùng SQL-style pattern như giả định chung.

`CONTAINS` thường gắn với **collection membership** và index/query support; không có nghĩa chứa substring trong mọi `text`. Phân biệt collection `CONTAINS`, map key `CONTAINS KEY` và text search.

## 8. Kiểu dữ liệu: lỗi literal trên CQL và codec ở Java

### 8.1. Các loại CQL ↔ Java phổ biến

| CQL | Java Driver 4.x type thường dùng | Bẫy |
|---|---|---|
| `uuid` | `java.util.UUID` | Không bind text bất kỳ vào UUID marker |
| `timeuuid` | `UUID` version 1 (time-based) | Không phải UUID v4 thông thường |
| `date` | `java.time.LocalDate` | Không có timezone/giờ phút |
| `timestamp` | `java.time.Instant` | Thường precision millisecond, không giữ ZoneId |
| `time` | `java.time.LocalTime` | Giờ trong ngày, không phải timestamp |
| `bigint` | `long` / `Long` | Không thay bằng int nếu vượt range |
| `int` | `int` / `Integer` | Có giới hạn signed 32-bit |
| `smallint` | `short` / `Short` | Range nhỏ |
| `tinyint` | `byte` / `Byte` | Range rất nhỏ |
| `float` | `float` / `Float` | Floating-point precision |
| `double` | `double` / `Double` | Không phù hợp tiền cần decimal |
| `decimal` | `java.math.BigDecimal` | Scale/rounding, tránh double |
| `varint` | `java.math.BigInteger` | Không tự chuyển long nếu quá range |
| `boolean` | `boolean` / `Boolean` | Không coi string `"yes"` là boolean |
| `text` / `varchar` | `String` | Charset/UTF-8 và size |
| `blob` | `ByteBuffer` | Direct/heap, vị trí buffer, bytes |
| `list<text>` | `List<String>` | Element type/null rules, update semantics |
| `set<uuid>` | `Set<UUID>` | Codec/element type |
| `map<text,int>` | `Map<String,Integer>` | Key/value types |
| UDT | `UdtValue` hoặc mapped codec | Schema/version, frozen/field types |
| tuple | `TupleValue` | Vị trí và exact element types |
| `duration` | Cassandra/driver-specific duration type | Không đồng nhất Java Duration cho mọi semantics |

Tên class/method có thể phụ thuộc driver 4.x minor/version và custom codec. Luôn kiểm metadata của `PreparedStatement.getVariableDefinitions()` và prepared CQL type trước khi bind.

### 8.2. Literal sai kiểu trong CQL

~~~cql
-- Sai type: double column không nhận một string 'high'.
UPDATE troubleshooting_lab.readings_by_device_day
SET reading_value = 'high'
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:00:00Z';
~~~

~~~cql
-- Sai type: date không thể parse từ 'yesterday'.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = 'yesterday';
~~~

Một literal `'2026-11-21'` được parser CQL chuyển sang `date` trong ngữ cảnh type phù hợp; nhưng literal arbitrary string và Java `String` bind cho `date` marker **không giống nhau**. Prepared marker có expected CQL type, Java phải cung cấp value/codec tương thích.

### 8.3. Type mismatch không phải lúc nào là `InvalidQueryException`

Nếu Java gọi `bound.setString("event_day", "2026-11-21")` mà marker là CQL `date`, driver có thể ném lỗi codec/type trước khi gửi tới coordinator. Đây là **client programming error**, không nên retry, không nên gọi `nodetool repair` và không xử lý như server timeout.

### 8.4. `timeuuid` khác `uuid`

Một giá trị UUID v4 hợp lệ về chuỗi/kiểu `uuid` **không đảm bảo** được chấp nhận ở cột `timeuuid` vì CQL `timeuuid` yêu cầu UUID version tương thích thời gian. Không đổi mọi event ID thành `timeuuid` chỉ để có ordering; hãy xem yêu cầu identity, uniqueness và write time.

### 8.5. Timestamp, timezone và partition day

~~~text
Instant event_time: 2026-11-21T17:30:00Z
event_day UTC:       2026-11-21
event_day VN +07:    2026-11-22
~~~

Nếu writer bind event_day UTC và reader bind local date, truy vấn có **đủ partition key và hoàn toàn hợp lệ** nhưng trả **zero rows**. Phải phân biệt “hợp lệ, sai bucket” với server `InvalidQuery` để tránh sửa schema sai mục đích.

## 9. Prepared statements: chống lỗi bind và injection

### 9.1. Truy vấn tham số hóa

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class ReadingsRepository {
    private final CqlSession session;
    private final PreparedStatement latestByDeviceDay;

    public ReadingsRepository(CqlSession session) {
        this.session = session;
        this.latestByDeviceDay = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM troubleshooting_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "LIMIT ?"
        );
    }

    public ResultSet latest(
            UUID deviceId, LocalDate eventDay, int limit) {
        if (deviceId == null || eventDay == null) {
            throw new IllegalArgumentException(
                "Partition key components are required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be within 1..100");
        }

        BoundStatement bound = latestByDeviceDay.bind(
            deviceId, eventDay, limit
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

        return session.execute(bound);
    }
}
~~~

**Chú ý:** Đây là lab một node RF=1 nên `LOCAL_ONE` là consistency đơn giản; production phải dùng CL phù hợp yêu cầu đúng đắn và availability, không sao chép setting này. `ResultSet` có thể fetch pages; caller vẫn cần giới hạn kết quả/bytes và quản lý tài nguyên. Đừng diễn giải `LIMIT 100` như cam kết chỉ đọc đúng 100 storage cells.

### 9.2. Tránh nối user input vào CQL string

~~~java
// ANTI-PATTERN: injection risk + literal/type issues.
String cql =
    "SELECT * FROM troubleshooting_lab.readings_by_device_day " +
    "WHERE device_id = " + userInput +
    " AND event_day = '" + dayInput + "'";
~~~

Đúng hơn:

- Dùng prepared markers cho **giá trị**.
- Parse `UUID`, `LocalDate`, `Instant` và validate trong application boundary.
- Identifiers như keyspace/table/column names **không bind bằng `?` giống value**; cần allowlist tên schema cố định hoặc metadata được phê duyệt.
- Không đưa raw CQL/giá trị bind vào metric labels hoặc exception logs.

### 9.3. `null` và `unset` không tương đương

Trong update/upsert, Cassandra/driver có cơ chế phân biệt **set null** (thường biểu thị delete/tombstone cho cell theo operation) và **unset** (không ghi marker ấy) ở những phiên bản hỗ trợ. Nhưng:

- Primary-key components không được null/unset.
- Không tùy tiện `setToNull` cho cột khi business muốn “giữ nguyên”.
- Với JSON patch/API partial update, phải định nghĩa rõ omitted field khác explicit null.
- Counter, collection, TTL và update semantics có quy tắc riêng.
- Xác minh driver 4.x `BoundStatement.setToNull(...)`/`unset(...)` và Cassandra version khi dùng.

### 9.4. Kiểm expected type của marker thay vì thử sai

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time FROM " +
    "troubleshooting_lab.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ?"
);

// Kiểm metadata trong debugger/test; không log dữ liệu bí mật.
var definitions = prepared.getVariableDefinitions();
// Chữ ký/iterator access cần đối chiếu driver version.
~~~

Nếu message cho biết expected `date` nhưng actual Java value là `String`, sửa mapping ở application layer. Không cast toàn bộ values sang `String` để “tránh mismatch”.

## 10. `INSERT`, `UPDATE`, `DELETE` và yêu cầu khóa đầy đủ

### 10.1. `INSERT` không được bỏ thành phần primary key

~~~cql
-- Sai: thiếu event_time, clustering component bắt buộc.
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, reading_value)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', 25.0);
~~~

Sửa bằng cách cung cấp `event_time` thật và đúng type; không tự dùng ngày thay thời điểm hoặc random timestamp để giấu lỗi model.

### 10.2. `UPDATE` để cập nhật một row phải định vị đủ key

~~~cql
-- Sai cho update một regular cell: thiếu event_time.
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'WARN'
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21';
~~~

~~~cql
-- Đúng với full primary key:
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'WARN'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

`UPDATE` của CQL có semantics **upsert** trong những mutation thông thường: row chưa có vẫn có thể được tạo tại full PK khi không dùng condition. Nó không trả “rows affected=0” theo giả định của một số SQL APIs.

### 10.3. `DELETE` một row khác xóa toàn partition

~~~cql
-- Xóa một row: full primary key.
DELETE FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;

-- Xóa TOÀN BỘ partition của device/day.
DELETE FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

Hai statements có ý nghĩa hoàn toàn khác nhau. `DELETE` theo full partition key có thể hợp lệ dù `UPDATE` regular cell cần full row key; **không dùng xóa partition để né lỗi UPDATE**.

~~~cql
-- Xóa một regular cell trong một row.
DELETE status
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

### 10.4. Không cập nhật một thành phần primary key bằng SET

~~~cql
-- Sai: event_time thuộc PRIMARY KEY.
UPDATE troubleshooting_lab.readings_by_device_day
SET event_time = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Đổi primary key cần kế hoạch INSERT ở key mới + DELETE key cũ, kèm idempotency, concurrency, CL, read consistency và tombstone/compaction. Hai mutations không tự trở thành một transaction ACID SQL tổng quát.

## 11. Counter là một loại dữ liệu và mutation đặc biệt

### 11.1. Counter table

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.device_daily_counts (
        device_id uuid,
        event_day date,
        total_events counter,
        PRIMARY KEY ((device_id, event_day))
    );
~~~

Non-primary-key columns trong counter table phải tuân quy tắc counter của Cassandra. Đừng trộn regular `text`/`int` columns với `counter` trong cùng table theo kiểu schema thông thường.

### 11.2. Tăng và giảm counter

~~~cql
UPDATE troubleshooting_lab.device_daily_counts
SET total_events = total_events + 1
WHERE device_id = ?
  AND event_day = ?;
~~~

~~~cql
-- Sai: gán counter thành giá trị tùy ý.
UPDATE troubleshooting_lab.device_daily_counts
SET total_events = 10
WHERE device_id = ?
  AND event_day = ?;

-- Sai: INSERT regular counter value.
INSERT INTO troubleshooting_lab.device_daily_counts
  (device_id, event_day, total_events)
VALUES (?, ?, 10);
~~~

Counter có thêm restrictions:

- Không dùng `USING TTL` như update regular cell.
- Không LWT/conditional update như cột thường ở các Cassandra versions phổ biến.
- Không trộn counter mutations với regular mutations trong cùng batch trái rules.
- Retry phép cộng **không idempotent**; nếu attempt đầu đã apply nhưng client timeout, retry có thể cộng hai lần.
- Không ALTER kiểu `counter` thành `bigint` tùy tiện để “chữa lỗi”; thường cần table mới/migration có đối soát.

## 12. TTL, mutation timestamp và LWT

### 12.1. TTL hợp lệ trên regular cells

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
USING TTL 86400;

UPDATE troubleshooting_lab.readings_by_device_day
USING TTL 600
SET status = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

TTL được tính theo expiration/mutation semantics, không tự trừ từ `event_time`. `TTL 0` và table `default_time_to_live` có semantics cần xác minh theo release; đừng coi nó là “expire immediately”. Không áp TTL để thay đổi riêng primary key. TTL trên counter có restrictions khác regular data.

### 12.2. `USING TIMESTAMP` khác cột `event_time`

CQL mutation write timestamp thường tính bằng microseconds, còn cột `event_time timestamp` biểu diễn dữ liệu nghiệp vụ với precision thường milliseconds. `WRITETIME(reading_value)` không đồng nhất `event_time`.

Một số tổ hợp `USING TIMESTAMP`, conditional statements/counters bị từ chối. Khi gặp invalid query:

1. Xác định option `TIMESTAMP` đang dùng cho mutation nào.
2. Xác định có `IF`/LWT hay counter không.
3. Xem CQL release cho phép tổ hợp ấy không.
4. Không xóa `IF` chỉ để tăng tốc độ nếu business cần compare-and-set.

### 12.3. LWT có conditions riêng

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

~~~cql
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'DONE'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
IF status = 'NEW';
~~~

LWT/Paxos có thêm chi phí và `wasApplied()`/serial consistency; không coi mọi dạng `IF` SQL là CQL hợp lệ. Một `ReadTimeout`/`WriteTimeout` sau conditional write là **uncertain outcome**, không phải lỗi validation đơn giản; đừng retry/overwrite vô điều kiện.

## 13. BATCH không chữa query sai và không phải bulk SQL transaction

### 13.1. Một batch có hai prepared mutations hợp lệ

~~~cql
BEGIN BATCH
  INSERT INTO troubleshooting_lab.readings_by_device_day
    (device_id, event_day, event_time, reading_value)
  VALUES (?, ?, ?, ?);
  INSERT INTO troubleshooting_lab.readings_by_device_day
    (device_id, event_day, event_time, reading_value)
  VALUES (?, ?, ?, ?);
APPLY BATCH;
~~~

Nếu một thành phần PK/typing bên trong sai, `BATCH` không làm nó hợp lệ.

### 13.2. Các lỗi suy luận thường gặp

| Trường hợp | Vì sao cần kiểm? |
|---|---|
| Counter + non-counter cùng batch | Restrictions theo loại mutation |
| Batch gồm nhiều partitions | Coordinator/batchlog/timeout overhead |
| Conditional/LWT batch | Điều kiện, partition restriction và serial semantics |
| Batch rất lớn để “bulk ingest” | Tăng memory/network/latency, không mặc định tăng throughput |
| Mong rollback/isolation như SQL transaction | CQL batch có guarantees khác SQL ACID transactions |

Dùng bounded concurrent prepared writes với rate/bytes limits khi mục tiêu là throughput; giữ batch cho trường hợp bảo đảm atomicity phù hợp được document trong Cassandra.

## 14. Collections, frozen values và UDT

### 14.1. Collection phải bind đúng CQL element type

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.device_metadata (
        device_id uuid PRIMARY KEY,
        tags set<text>,
        attributes map<text, text>,
        owners list<uuid>
    );

INSERT INTO troubleshooting_lab.device_metadata
  (device_id, tags, attributes, owners)
VALUES
  (11111111-1111-1111-1111-111111111111,
   {'edge', 'critical'},
   {'region': 'vn', 'team': 'ops'},
   [22222222-2222-2222-2222-222222222222]);
~~~

Java cần `Set<String>`, `Map<String,String>`, `List<UUID>` và codec tương ứng. Một `String` chứa JSON không tự biến thành map CQL nếu chưa có explicit transform/custom codec.

Không nhét null collection elements hoặc values sai type; kiểm các restrictions/semantics của list/set/map theo server release. Collection rất lớn trong một cell/partition còn tạo p99/compaction pressure.

### 14.2. UDT và `frozen`

~~~cql
CREATE TYPE IF NOT EXISTS troubleshooting_lab.geo_point (
  latitude double,
  longitude double
);

CREATE TABLE IF NOT EXISTS troubleshooting_lab.device_locations (
  device_id uuid PRIMARY KEY,
  last_point frozen<geo_point>
);
~~~

`frozen` thường khiến giá trị được đối xử atomic ở mutation level; không thể cập nhật subfield như với một non-frozen UDT trong các trường hợp được hỗ trợ. Nếu error nhắc `frozen`/UDT/collection, xem **schema type** và update syntax thực thay vì thêm filtering.

### 14.3. `CONTAINS` không đồng nghĩa substring search

~~~cql
-- Cần index/query support theo release.
SELECT *
FROM troubleshooting_lab.device_metadata
WHERE attributes CONTAINS KEY 'region';
~~~

`CONTAINS`/`CONTAINS KEY` thường gắn collection membership; `LIKE` trên text tùy index/release. Cả hai không phải “WHERE tùy ý có sẵn trên mọi regular column”.

## 15. Những phép SQL không chuyển thẳng sang CQL

### 15.1. Không có JOIN tổng quát

~~~sql
-- SQL quan hệ minh họa, không phải CQL hợp lệ:
SELECT d.name, r.value
FROM devices d
JOIN readings r ON d.id = r.device_id
WHERE d.region = 'vn';
~~~

Cassandra không cung cấp relational JOIN/subquery planner tổng quát như RDBMS. Định hướng thường là table theo query, denormalization, bounded application fan-out, read-model hoặc analytical/search engine.

### 15.2. Không mặc định có subqueries, `OR` và arbitrary predicates

~~~sql
-- SQL-style subquery, không phải CQL mặc định:
SELECT *
FROM readings
WHERE device_id IN (
  SELECT device_id FROM devices WHERE region = 'vn'
);
~~~

Các dạng boolean `OR`/index combinations có khác biệt theo Cassandra release/index support; **không khẳng định mọi OR luôn sai trên tất cả phiên bản**, nhưng không được dựa vào SQL syntax để phỏng đoán CQL. So query thật với tài liệu CQL của đúng release.

### 15.3. Aggregation không tự rẻ

~~~cql
SELECT count(*)
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

Một `COUNT(*)` có thể hợp lệ nhưng vẫn phải đọc nhiều dữ liệu trong partition. Đừng dùng nó cho mỗi HTTP request nếu partition rất rộng. Tính toán trước read-model/counter/analytics theo business requirement và trade-offs.

### 15.4. `GROUP BY`, `DISTINCT` và `PER PARTITION LIMIT`

Các tính năng CQL này có thể có trong những releases nhất định, nhưng có rules về **primary key, partition, clustering order và query shape**. Không mặc định:

~~~sql
-- SQL-style không nhất thiết hợp lệ trong CQL:
SELECT status, avg(reading_value)
FROM readings
GROUP BY status;
~~~

Với `status` là regular column, đây không phải truy vấn tự nhiên của schema `readings_by_device_day`. Chọn pre-aggregation theo status/time bucket hoặc analytical system.

### 15.5. Không có OFFSET paging kiểu SQL thông thường

~~~sql
-- Không được giả định CQL có offset random access:
SELECT * FROM readings LIMIT 50 OFFSET 10000;
~~~

Java Driver/Cassandra thường paging bằng **paging state** có version/routing/correctness caveats, không bằng offset. Paging không đảm bảo snapshot across pages và state nên được coi là opaque token, không để người dùng tùy ý sửa.

## 16. `token()` và range scans thuộc phạm vi khác

~~~cql
-- Chỉ minh họa cú pháp cho lab/tooling. Loại token bound
-- phụ thuộc partitioner và Cassandra release.
SELECT device_id, event_day, event_time
FROM troubleshooting_lab.readings_by_device_day
WHERE token(device_id, event_day) > ?
  AND token(device_id, event_day) <= ?;
~~~

Token-range scans có thể hữu dụng cho ETL/backfill nhưng **không chữa query filter theo regular column**. Nếu dùng trong vận hành: có pagination, checkpoint, per-node load budget, disk/GC headroom, topology changes và read CL.

Không đưa token scan không giới hạn vào API latency-sensitive; nếu chỉ cần dữ liệu của một device/day, truyền đúng partition key.

## 17. Schema thực tế, identifiers và cache

### 17.1. Đọc schema ở cluster thật

~~~cql
-- Lệnh của cqlsh, không phải native CQL gửi trực tiếp
-- qua session.execute():
DESCRIBE KEYSPACE troubleshooting_lab;
DESCRIBE TABLE troubleshooting_lab.readings_by_device_day;
~~~

`DESCRIBE` do cqlsh/client thực hiện. Qua Java, dùng driver metadata APIs hoặc queries `system_schema` được release hỗ trợ, **không sửa system tables**.

Nếu deployment vừa chạy DDL:

- Xác minh schema agreement.
- Xác minh đúng keyspace/table/column types trên tất cả coordinator candidates.
- Kiểm migration version/order và driver schema metadata.
- Driver có prepare/reprepare behavior riêng khi schema thay đổi.
- `UnpreparedException` khác bản chất `InvalidQuery` do query sai PK.

### 17.2. Quoted identifier có phân biệt case

~~~cql
CREATE TABLE troubleshooting_lab."DeviceEvents" (
  id uuid PRIMARY KEY
);

-- Phải dùng cùng quoted name:
SELECT * FROM troubleshooting_lab."DeviceEvents"
WHERE id = ?;
~~~

Tên không quote được chuẩn hóa theo CQL rules; tên trong dấu ngoặc kép có case-sensitivity. `"DeviceEvents"` và `deviceevents` không mặc nhiên cùng table.

### 17.3. Keyspace mặc định và từ khóa dành riêng

Khi CQL chạy thành công trong cqlsh có `USE troubleshooting_lab` nhưng Java session không chọn keyspace, unqualified table name có thể chỉ đến keyspace khác hoặc báo unknown table. Ưu tiên fully qualified CQL template.

Tên cột trùng reserved keyword có thể cần quoting theo CQL release, nhưng tốt hơn thiết kế identifier đơn giản, nhất quán.

## 18. Query hợp lệ chưa đảm bảo business correctness/SLO

| Lớp | Ví dụ |
|---|---|
| Syntax | CQL parse được |
| Server validation | Đủ PK, type, restrictions và statement rules |
| Security | Role/tenant được phép truy cập |
| Business data | Writer/reader dùng đúng UTC event_day |
| Operations | p99, CPU/disk/tombstone load đạt yêu cầu |

Một SELECT đúng PK nhưng event_day sai timezone trả **0 row**, không phải InvalidQuery. Một SELECT với `ALLOW FILTERING` có thể trả đúng 5 rows nhưng phải scan quá nhiều dữ liệu, gây timeout/GC.

CL `ONE`/`LOCAL_QUORUM` không làm regular column trở thành indexed key hoặc sửa codec Java. Nếu query đã hợp lệ nhưng request timeout, điều tra **RF/CL/replica liveness/disk/compaction**, không sửa câu WHERE theo kiểu đoán mò.

Với multi-tenant, bind UUID đúng type cũng **không thay application-level authorization**: principal phải có quyền xem device/tenant tương ứng.

## 19. Java Driver 4.x: phân loại lỗi trước khi retry

### 19.1. Phân biệt prepare, bind và execute

~~~text
User input -> UUID/LocalDate/Instant validation
  -> Prepare CQL, server parse/validate
  -> Bind typed markers, driver codec
  -> Execute, server semantic/permission check
  -> Replica read/write according to CL
  -> ResultSet / AsyncResultSet
~~~

- `session.prepare(...)` có thể nhận server `InvalidQueryException` hoặc `SyntaxError` **ngay trước khi execute**.
- `bound.setString(...)` với marker CQL `date` có thể ném lỗi codec/type **ngay trên Java client**.
- Server cũng có thể từ chối statement ở execute khi validation/schema khác.
- Request đã thực thi nhưng timeout là một nhánh khác, có thể có **uncertain write outcome**.

### 19.2. Phân loại ngoại lệ Java 4.x

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import com.datastax.oss.driver.api.core.servererrors.SyntaxError;
import com.datastax.oss.driver.api.core.servererrors.UnauthorizedException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class CqlFailureKinds {
    private CqlFailureKinds() {}

    static Throwable unwrap(Throwable failure) {
        Throwable t = failure;
        for (int i = 0; i < 8; i++) {
            if ((t instanceof CompletionException
                    || t instanceof ExecutionException)
                    && t.getCause() != null) {
                t = t.getCause();
            } else {
                return t;
            }
        }
        return t;
    }

    static String classify(Throwable failure) {
        Throwable t = unwrap(failure);
        if (t instanceof InvalidQueryException)
            return "CQL_SEMANTIC_VALIDATION";
        if (t instanceof SyntaxError)
            return "CQL_SYNTAX";
        if (t instanceof UnauthorizedException)
            return "CQL_AUTHORIZATION";
        if (t instanceof ReadTimeoutException)
            return "READ_TIMEOUT";
        if (t instanceof AllNodesFailedException)
            return "NO_COORDINATOR_CANDIDATE";
        return "CLIENT_CODEC_OR_OTHER";
    }
}
~~~

**Giới hạn:** Ví dụ chỉ là classifier tối thiểu; chưa phân biệt `WriteTimeout`, `DriverTimeout`, `Unavailable`, `Unprepared`, custom codecs và per-node root causes. API/type names cần xác minh trên đúng driver artifact. Với `AllNodesFailedException`, kiểm `getAllErrors()` theo **coordinator candidates**, không coi đó là danh sách tất cả replicas.

### 19.3. Logging an toàn

~~~text
event=cql_execution_failure
timestamp_utc=2026-11-21T10:10:00Z
service=telemetry-reader
query_template=latest20_by_device_day
error_kind=CQL_SEMANTIC_VALIDATION
schema_release=known_or_unknown
driver_major=4
consistency=LOCAL_QUORUM
~~~

Đây là **log schema do ứng dụng tự thiết kế**, không phải output mặc định. Không log raw bind values, UUID tenant/device, passwords, CQL string ghép user input hoặc error messages chưa redaction. Query template ID/error class là labels ít cardinality.

### 19.4. Retry theo loại lỗi

| Loại | Có tự retry? | Lý do |
|---|---|---|
| InvalidQuery/SyntaxError | **Không** | Query/schema/type sai ổn định |
| Client codec/type error | **Không** | Bind Java sai, không phải node chậm |
| Unauthorized | **Không** | Permissions không đổi do retry |
| Unprepared | Theo cơ chế reprepare của driver | Không retry vòng ngoài vô hạn |
| Timeout/Unavailable | Có điều kiện | CL, idempotency, deadline, budget |
| AllNodesFailed/network | Có điều kiện | Phân loại cause, TLS không tự sửa |

Nếu InvalidQuery tăng ngay sau deploy, **rollback/fix query template hoặc migration mismatch** thường hợp lý hơn tăng timeout/pool.

## 20. Thu bằng chứng trước khi thay schema

### 20.1. Tối thiểu cần có

1. Cassandra/server và Java Driver versions.
2. Keyspace/table thực tế, PRIMARY KEY, clustering order, data types, indexes.
3. Query template (đã ẩn values nhạy cảm), statement type.
4. Lỗi xảy ra ở prepare, bind hay execute/page fetch.
5. Exception class, cause chain, safe excerpt của message.
6. Local DC, consistency level, coordinator candidate nếu có.
7. UTC timeline, app/DDL migration version, schema agreement.
8. Query intent: tra theo device/day, event ID, status hay tổng hợp?
9. Payload/partition width, TTL/tombstone mix và latency budget.
10. Môi trường lab/staging được phép test và rollback owner.

### 20.2. Không dùng production scan để thử

~~~cql
-- CẢNH BÁO: anti-pattern trên bảng lớn.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN'
ALLOW FILTERING;
~~~

Nếu muốn xác minh query semantics, dùng **lab với dữ liệu nhỏ**. Một truy vấn `ALLOW FILTERING` trả dữ liệu không chứng minh vận hành được với hàng triệu partitions và nhiều tombstones.

### 20.3. Schema metadata và migration

Đối chiếu cqlsh `DESCRIBE` với Java Driver metadata, `system_schema`/schema agreement theo release. `DESCRIBE` là lệnh cqlsh, **không phải native CQL statement** gửi vào `session.execute`. Không sửa trực tiếp system tables. `UnpreparedException` sau DDL không đồng nghĩa Cassandra SSTables corrupt.

## 21. Runbook A — `WHERE` thiếu partition key

**Tình huống:** `WHERE device_id=?` trên table có partition key `(device_id,event_day)` bị từ chối.

1. Xác định chính xác SELECT/UPDATE/DELETE và query template.
2. Đọc PRIMARY KEY thực, không chỉ DDL trong Git.
3. Xác nhận có `event_day` ở request/business context không.
4. Nếu có, bind typed `LocalDate` và giữ cùng timezone policy giữa writer/reader.
5. Nếu không, bounded fan-out qua các day partitions hoặc thiết kế table theo truy vấn.
6. Không thêm `ALLOW FILTERING` làm giải pháp mặc định.
7. Test positive đủ partition key và negative thiếu key.
8. Nếu thay table, có migration/backfill/dual-write/rollback.
9. Theo dõi request p99, timeouts, bytes và node read load.
10. Xác minh không làm sai tenant ownership/data access.

**Giảm consistency từ LOCAL_QUORUM xuống ONE không sửa lỗi partition key.**

## 22. Runbook B — Clustering restriction hoặc `ORDER BY` bị từ chối

**Tình huống:** Query theo `event_id` mà không có `event_time` trên table clustering `(event_time,event_id)`, hoặc muốn `ORDER BY reading_value`.

1. Đọc full partition/clustering keys và sort directions.
2. Kiểm equality prefix, range position và các restrictions sau range.
3. Kiểm `ORDER BY` có dùng clustering columns trong partition không.
4. Nếu biết event_time, bind cả time và event ID.
5. Nếu lookup trực tiếp theo ID, cân nhắc `events_by_id` read-model.
6. Nếu cần top-N theo reading value, thiết kế clustering order theo query.
7. Sort Java chỉ khi result bounded nhỏ và được phép.
8. Không đoán index giải quyết order; kiểm version/operators.
9. Test timestamp tie, uniqueness và reverse-order cases.
10. Đo p95/p99, Cassandra read amplification và correctness.

**ORDER BY trong một partition không bảo đảm thứ tự toàn cluster.**

## 23. Runbook C — Sai kiểu literal hoặc Java codec

**Tình huống:** cqlsh báo invalid date literal; Java bind `String` vào marker `date` bị từ chối.

1. Xác định lỗi ở Java bind, server prepare hay server execution.
2. Xác minh schema type: `uuid`, `date`, `timestamp`, `decimal`, `timeuuid`, collections.
3. Kiểm expected type của prepared markers.
4. Parse input sớm bằng `UUID.fromString`/`LocalDate.parse`/`Instant.parse`.
5. Dùng `BigDecimal` cho decimal chính xác, `BigInteger` cho varint lớn.
6. Kiểm UTC day bucket và millisecond timestamp precision.
7. Kiểm element type, frozen UDT, null/unset semantics.
8. Không sửa bằng cách cast mọi giá trị thành `String`.
9. Unit test invalid input và integration round-trip với Cassandra thật.
10. Không retry client codec errors; ghi type mismatch mà không log dữ liệu nhạy cảm.

**Literal conversion ở cqlsh khác typed bind từ Java Driver.**

## 24. Runbook D — Filtering/index: InvalidQuery biến mất nhưng hiệu năng xấu

**Tình huống:** `WHERE status='WARN'` bị từ chối; nhóm phát triển thêm `ALLOW FILTERING`, dữ liệu lab nhỏ trả kết quả, nhưng staging p99 tăng.

1. Xác định query intent: status trên **một device/day** hay trên toàn hệ thống?
2. Nếu đã biết full partition key và có ít rows, cân nhắc bounded read rồi filter ở ứng dụng.
3. Nếu cần tìm mọi WARN trong nhiều partitions, thiết kế table theo `status/day/shard` hoặc indexed access path.
4. Kiểm index type: 2i/SAI/SASI và release/distribution; không khẳng định cùng operators.
5. Đo selectivity, số partitions, tombstones và SSTables phải scan.
6. Giới hạn response bytes, in-flight và phép đo workload.
7. So read p50/p95/p99, CPU/GC/disk cùng write amplification của index.
8. Không scan production để “chứng minh” filtering hợp lệ.
9. Canary query path mới và có rollback khi SLO xấu.
10. Viết negative test ngăn hồi quy dùng filtering ngoài policy.

**InvalidQuery biến mất không đồng nghĩa query đã an toàn cho production.**

## 25. Runbook E — Counter, TTL, LWT hoặc BATCH bị từ chối

**Tình huống:** App cố `INSERT` counter, gán `count=10`, dùng TTL trên counter hoặc trộn counter với regular mutation trong batch.

1. Đọc type của table: có `counter` hay regular `bigint`?
2. Nếu counter, dùng `UPDATE ... SET count=count+delta` với đủ key.
3. Không trộn counter/non-counter columns trái CQL rules.
4. Kiểm `USING TTL` và `USING TIMESTAMP` hợp lệ cho mutation này không.
5. Nếu có `IF`, xác định LWT semantics và supported conditions.
6. Nếu batch, kiểm loại batch và các statements bên trong hợp lệ.
7. Đánh giá idempotency: counter increment retry sau timeout có thể double count.
8. Không chuyển conditional write thành unconditional để “sửa” validation.
9. Cân nhắc table mới khi business muốn absolute count, TTL hoặc CAS khác counter.
10. Test cả invalid statements, applied/not-applied outcomes và retries trong lab.

**Câu CQL đúng syntax không đủ bảo đảm nghiệp vụ counter hoặc LWT đúng.**

## 26. Runbook F — Unknown column/table sau migration

**Tình huống:** App mới query một column vừa thêm, một số coordinators báo unknown column, nhưng cqlsh ở node khác đã thấy schema mới.

1. Xác định cluster/keyspace/local DC của app, tránh nhầm staging/production.
2. Kiểm migration version/order và DDL đã apply chưa.
3. So schema trên các nodes có quyền, kiểm schema agreement.
4. Kiểm quoted identifier casing và keyspace fully qualified.
5. Kiểm Java Driver schema metadata và prepare/reprepare behavior.
6. Không xóa `system_schema` hoặc drop/recreate data table mù quáng.
7. Dùng additive schema migration trước app code rollout khi có thể.
8. Với rollback, kiểm compatibility app cũ/mới và migration safety.
9. Canary CQL prepare+execute qua nodes/clients, xác minh hết errors.
10. RCA: cập nhật migration ordering, rollout gates và schema tests.

**Unprepared/metadata race không tự chứng minh SSTables corrupt.**

## 27. Runbook G — Query hợp lệ nhưng trả không có dữ liệu

**Tình huống:** SELECT có đủ `device_id` và `event_day`, chạy thành công, trả 0 rows dù source đã nhận event.

1. Không ghi nhãn InvalidQuery nếu không có server validation exception.
2. Kiểm UUID device_id thực/tenant ownership.
3. So writer/reader tính `event_day` theo UTC hay timezone khác.
4. So `event_time` millisecond precision và full clustering key.
5. Kiểm producer đã ghi thành công chưa; write timeout có outcome không chắc chắn.
6. Xem TTL/deletion/tombstone/retention policy.
7. Xem RF/CL, replica liveness và read/write consistency.
8. Không dùng `ALLOW FILTERING` để tìm row “mất” trên toàn cluster.
9. Nếu sai partition bucket, lập kế hoạch backfill/dual-read/reconciliation.
10. Test date-boundary, late-arrival, dedup và read-back từ cùng key.

**Zero rows là kết quả query hợp lệ, không phải cùng loại lỗi với InvalidQuery.**

## 28. Thiết kế read models cho những query cần thiết

### 28.1. Một tập dữ liệu có thể cần nhiều bảng

| Truy vấn nghiệp vụ | Read model theo truy vấn | Đánh đổi |
|---|---|---|
| Latest 20 by device/day | `readings_by_device_day`, clustering time DESC | Multi-day cần bounded fan-out |
| Event theo ID | `events_by_id`, partition event ID | Ghi/đối soát thêm bảng |
| WARN events theo ngày | `events_by_status_day`, partition status/day/shard | Hot partition/shard sizing |
| Events theo tenant/day | `events_by_tenant_day_shard` | Fan-out theo shard |
| Counts realtime | Counter hoặc pre-aggregated table | Retry/correctness trade-offs |
| Search/analytics phức tạp | Search/analytical engine | Đồng bộ và vận hành thêm |

Cassandra không tối ưu một normalized table duy nhất cho mọi `WHERE`/`JOIN`/`ORDER BY` giống một SQL optimizer.

### 28.2. Ví dụ bảng tra event ID trực tiếp

~~~cql
CREATE TABLE IF NOT EXISTS troubleshooting_lab.events_by_id (
    event_id uuid PRIMARY KEY,
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_type text
);
~~~

App lookup event ID trước, rồi tra table by device/day nếu cần payload. Nếu duplicate data sang nhiều bảng, cần định nghĩa consistency khi một write thành công còn write kia timeout; lập kế hoạch idempotency, repair/reconciliation và TTL đồng nhất.

### 28.3. Lộ trình migration query-first

~~~text
1. Mô tả query thật và expected p99/throughput.
2. Chọn partition key/clustering theo access path.
3. Test distribution, hotspots, tombstones và TTL trên staging.
4. Migration ADD table/index an toàn theo version.
5. Dual-write/backfill có checkpoint/rate limits.
6. Đối soát dữ liệu với business invariants.
7. Canary readers, rollback plan, dần chuyển traffic.
8. Theo dõi write amplification, disk, compaction, repair.
9. Thu hồi path cũ khi retention/consumer inventory cho phép.
~~~

Không dùng `ALTER TABLE` để tự chuyển primary key đang tồn tại sang key mới; Cassandra có restrictions khác migration kiểu RDBMS. Thay đổi PK thường cần table mới và backfill.

### 28.4. Query design và security

Ngay cả khi một request có đầy đủ partition key và Java bind types đúng, service vẫn cần **kiểm tra principal được quyền đọc device/tenant**. IDOR/cross-tenant leakage là lỗi authorization nghiệp vụ, không tự bị Cassandra `InvalidQuery` chặn.

Cũng không tạo metric label chứa raw device/tenant IDs, vì vừa tăng cardinality vừa lộ dữ liệu.

## 29. Ma trận kiểm thử âm/dương cho truy vấn CQL

| ID | Tình huống | Kỳ vọng đúng | Lớp kiểm thử |
|---|---|---|---|
| T01 | Full partition key by device/day | SELECT thành công | Integration |
| T02 | Bỏ `event_day` khỏi composite PK | Query bị từ chối nếu không có access path được hỗ trợ | Integration |
| T03 | Chỉ `event_day`, thiếu `device_id` | Không được coi là indexed query mặc định | Integration |
| T04 | `device_id = null` khi INSERT | PK invalid | Integration |
| T05 | Bỏ clustering key khi INSERT | PK invalid | Integration |
| T06 | UPDATE regular cell thiếu event_time | Key restrictions invalid | Integration |
| T07 | DELETE full partition key | Phân biệt xóa cả partition | Integration cô lập |
| T08 | Clustering prefix + range | Query đúng theo table design | Integration |
| T09 | Clustering suffix không có prefix | Validation hoặc filtering tùy path/version | Integration |
| T10 | ORDER BY clustering column | Sort theo partition | Integration |
| T11 | ORDER BY regular column | Bị từ chối khi không hỗ trợ | Integration |
| T12 | Regular column filter không index | Error/giới hạn theo release | Integration |
| T13 | IN nhiều ngày | Xác minh support + bounded costs | Integration/load |
| T14 | Bind UUID type đúng | Thành công | Unit + integration |
| T15 | Bind String vào date marker | Driver codec/type error | Unit/driver |
| T16 | Literal date không parse được | Server validation error | Integration |
| T17 | Bind Instant milisecond | Round-trip đúng precision | Integration |
| T18 | UUID v4 cho timeuuid | Type/version validation error | Integration |
| T19 | Counter increment | Tăng đúng theo semantics | Integration |
| T20 | Counter SET absolute value | Invalid counter mutation | Integration |
| T21 | Counter + TTL | Invalid/unavailable combination | Integration |
| T22 | LWT IF NOT EXISTS | `wasApplied()` đúng | Integration |
| T23 | LWT timeout/retry | Không gán timeout = rollback | Cluster integration |
| T24 | Collection wrong element type | Codec/validation error | Unit + integration |
| T25 | Frozen UDT wrong field operation | Type/mutation restriction | Integration |
| T26 | cqlsh DESCRIBE trong native execute | Không coi là valid native CQL | Unit + integration |
| T27 | Quoted table name khác case | Phân biệt identifiers | Integration |
| T28 | Schema migration chưa agreement | Fail/canary và driver metadata | Multi-node lab |
| T29 | Wrong UTC/local event_day | 0 row nhưng query hợp lệ | Unit + integration |
| T30 | Missing tenant authorization | Application từ chối trước CQL | Security integration |

### 29.1. Unit tests không đủ chứng minh CQL support

Một unit test mock `CqlSession` có thể kiểm ứng dụng truyền `UUID`/`LocalDate`, nhưng **không** xác minh Cassandra server có chấp nhận `WHERE`, `ORDER BY` hoặc schema/index combinations. Cần chạy integration trên **server version thực**.

### 29.2. Negative tests phải có giới hạn an toàn

Test malformed query/type trong keyspace lab có volume nhỏ. Không dùng `DELETE partition`, `TRUNCATE` hoặc `ALLOW FILTERING` scan lớn trên production để tạo expected errors.

### 29.3. Cần test load cho những query vừa trở nên hợp lệ

Khi thêm index/table mới hoặc `ALLOW FILTERING`, kết quả “prepare/execute thành công” mới là **functional gate**. Vẫn phải kiểm:

- Read p50/p95/p99 và timeout/availability budget.
- Rows returned vs rows scanned, tombstone density.
- SSTables/read, CPU/GC, disk IOPS/await.
- Index build/compaction, write amplification.
- Hot partitions/tenant distribution, data growth.
- RF/CL và node failure/recovery headroom.

## 30. Ví dụ JUnit 5 integration test với Java Driver 4.x

### 30.1. Fixture dành cho Cassandra lab được cấp sẵn

Ví dụ này giả định keyspace/table của mục 3 đã được tạo, Cassandra đang chạy và JUnit kết nối qua biến môi trường/secret provider được kiểm soát. Đây là **minh họa contract tests**, chưa được compile/run trong bước soạn. Version của Driver 4.x, JDK và server phải được pin tương thích.

~~~java
package demo.cassandra.validation;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class CqlValidationIntegrationTest {
    static CqlSession session;

    @BeforeAll
    static void open() {
        // Chỉ lab/test container; không commit secrets.
        session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
        // DC name phải khớp chính xác cluster lab thực tế.
    }

    @AfterAll
    static void close() {
        if (session != null) session.close();
    }

    @Test
    void fullPartitionKeyCanRead() {
        UUID id = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        PreparedStatement stmt = session.prepare(
            "SELECT event_time, reading_value " +
            "FROM troubleshooting_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "LIMIT 10");

        Row row = session.execute(stmt.bind(id, day)).one();

        // Seed của mục 3 phải được nạp trước test.
        assertNotNull(row);
        assertNotNull(row.getInstant("event_time"));
    }

    @Test
    void missingCompositePartitionKeyPartIsRejected() {
        assertThrows(InvalidQueryException.class, () ->
            session.prepare(
                "SELECT event_time " +
                "FROM troubleshooting_lab.readings_by_device_day " +
                "WHERE device_id = ?"));
    }

    @Test
    void wrongDateLiteralIsRejected() {
        assertThrows(InvalidQueryException.class, () ->
            session.execute(
                "SELECT event_time " +
                "FROM troubleshooting_lab.readings_by_device_day " +
                "WHERE device_id = " +
                "11111111-1111-1111-1111-111111111111 " +
                "AND event_day = 'not-a-date'"));
    }

    @Test
    void sameInstantMayProduceDifferentLocalDateBuckets() {
        Instant eventTime =
            Instant.parse("2026-11-21T17:30:00Z");

        LocalDate utcDay = eventTime
            .atZone(java.time.ZoneOffset.UTC).toLocalDate();

        LocalDate vnDay = eventTime
            .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertEquals(LocalDate.of(2026, 11, 21), utcDay);
        assertEquals(LocalDate.of(2026, 11, 22), vnDay);
    }
}
~~~

**Giới hạn của fixture:**

- `127.0.0.1:9042`/`datacenter1` chỉ là giả định; dùng contact points/local DC của lab.
- Nếu có TLS/auth, cấu hình session bằng approved SSLContext/auth provider, không vô hiệu hóa security.
- Seed phải chạy trước test, đúng UUID/ngày và schema.
- Một số server/driver versions có thể ném class validation cụ thể khác; trong CI, pin version và sửa assertion theo error contract đã quan sát, **không làm test quá lỏng bằng catch mọi RuntimeException**.
- Test này không chứng minh RF=3, multi-DC, node failure hoặc index performance.

### 30.2. Test fail sớm ở application boundary

~~~java
import java.time.LocalDate;
import java.util.UUID;

record DeviceDayRequest(UUID deviceId, LocalDate eventDay) {
    DeviceDayRequest {
        if (deviceId == null || eventDay == null) {
            throw new IllegalArgumentException(
                "Both deviceId and eventDay are required");
        }
    }
}
~~~

Cần tách **HTTP 400 cho client input không hợp lệ** khỏi **server CQL InvalidQuery do developer/migration mismatch**. Không trả nguyên database exception message cho người dùng cuối, vì có thể lộ schema/query details.

### 30.3. Viết test để bắt regression khi thay partition key

Nếu migration thay bảng `readings_by_device_day` sang cấu trúc có thêm `tenant_id` trong composite partition key, positive tests cũ phải được sửa để bind đủ tenant ID. Thử thiếu tenant ID nên thất bại và API phải từ chối theo policy; không tự fallback sang query không filter tenant.

## 31. Các ngộ nhận làm lỗi tái diễn

| Ngộ nhận | Thực tế |
|---|---|
| “CQL SELECT giống SQL, WHERE cột nào cũng được.” | Cassandra chủ yếu truy vấn theo partition/clustering/index path |
| “Thiếu event_day chỉ cần tăng timeout.” | Timeout không làm xuất hiện partition key |
| “Hạ CL từ QUORUM xuống ONE sửa InvalidQuery.” | CL không thay validation rules |
| “ALLOW FILTERING là tối ưu query.” | Có thể quét nhiều dữ liệu với chi phí lớn |
| “LIMIT 10 nghĩa chỉ đọc 10 storage cells.” | Tombstones/scan work có thể lớn |
| “ORDER BY regular column được vì nó là text/double.” | ORDER BY phụ thuộc clustering/query shape |
| “IN 1000 keys luôn tương đương một query rẻ.” | Fan-out/latency/resource có giới hạn |
| “Clustering key có thể nhảy qua prefix.” | Restrictions theo clustering order/index/filter |
| “UPDATE không tìm thấy row sẽ trả 0 affected rows.” | CQL UPDATE thường là upsert |
| “DELETE thiếu clustering key luôn sai.” | DELETE theo full partition key có thể xóa cả partition |
| “Thay PK bằng UPDATE SET là được.” | Primary key xác định row placement |
| “String ngày Java giống date marker CQL.” | Prepared bind cần LocalDate/codec phù hợp |
| “timeuuid là uuid bất kỳ.” | Timeuuid yêu cầu UUID version phù hợp |
| “Double phù hợp tiền decimal.” | Dùng BigDecimal khi cần exact decimal |
| “Counter INSERT hoặc SET 10 được.” | Counter cần update increment/decrement semantics |
| “Counter retry vô hại.” | Có thể double-count |
| “TTL tự tính từ event_time column.” | TTL tính theo mutation/expiration semantics |
| “LWT timeout nghĩa IF không apply.” | Outcome có thể không chắc chắn |
| “BATCH sửa mọi invalid statement.” | Mỗi mutation vẫn phải hợp lệ |
| “BATCH giống transaction SQL đa table.” | Guarantees khác, không có arbitrary JOIN/rollback |
| “Cassandra tự JOIN các bảng.” | Thiết kế read models/denormalization hoặc layer khác |
| “GROUP BY status trên table nào cũng được.” | CQL aggregation có PK/release restrictions |
| “OFFSET hỗ trợ paging như SQL.” | Dùng paging state theo driver/CQL |
| “DESCRIBE là native CQL trong Java execute.” | DESCRIBE là client/cqlsh facility |
| “Unknown column nghĩa SSTable corrupted.” | Có thể schema/migration/keyspace/case mismatch |
| “Prepared statement chống mọi lỗi quyền truy cập.” | Bind chống injection, app vẫn cần tenant authorization |
| “0 row nghĩa InvalidQuery.” | Query có thể hợp lệ nhưng sai bucket/time/TTL |
| “Driver codec exception cần nodetool repair.” | Sửa Java type mapping, không sửa replicas |
| “Tất cả OR/LIKE/index features giống nhau mọi bản.” | CQL/index support phụ thuộc release/distribution |

## 32. Câu hỏi luyện tập và đáp án

### Câu 1 — Partition key

Bảng có `PRIMARY KEY ((device_id,event_day),event_time)`. Query chỉ có `WHERE device_id=?`. Vấn đề chính là gì?

**Đáp án:** Thiếu `event_day` của composite partition key cho access path thông thường. Bổ sung typed day hoặc thiết kế read model/query multi-day có giới hạn, không tăng timeout.

### Câu 2 — Zero rows

Query đủ PK, không báo lỗi nhưng trả 0 rows. Có thể khẳng định InvalidQuery không?

**Đáp án:** Không. Kiểm key values, UTC/local day bucket, timestamp precision, TTL, write outcome và CL. InvalidQuery là lỗi validation riêng.

### Câu 3 — Clustering prefix

Bảng clustering `(event_time,event_id)`. Tra `event_id` không có event_time có tự hiệu quả không?

**Đáp án:** Không mặc định. Clustering restrictions theo prefix/order và index support. Lookup event ID thường cần bảng riêng theo ID.

### Câu 4 — ORDER BY

`ORDER BY reading_value DESC` khi reading_value là regular column. Vì sao không mặc định hỗ trợ?

**Đáp án:** Cassandra tổ chức thứ tự theo clustering columns trong partition, không sort tùy cột toàn cluster như SQL. Cần query-first schema hoặc sort bounded nhỏ ở app.

### Câu 5 — ALLOW FILTERING

Sau khi thêm `ALLOW FILTERING`, query trả đúng 5 rows. Có đủ để đưa production không?

**Đáp án:** Không. Nó có thể scan rất nhiều partitions/tombstones; cần load test, data size và SLO, hoặc sửa index/table design.

### Câu 6 — IN

Một query dùng `event_day IN` cho 1.000 ngày. Nếu release chấp nhận cú pháp, có chứng minh hiệu quả không?

**Đáp án:** Không. Cần bound fan-out/bytes/concurrency, page costs và thông lượng. Hạn chế query window hoặc dùng data model phù hợp.

### Câu 7 — UPDATE thiếu clustering key

`UPDATE ... SET status=? WHERE device_id=? AND event_day=?` trên bảng có clustering event_time. Sửa thế nào?

**Đáp án:** Cần xác định row bằng event_time (full key) hoặc thay thiết kế dữ liệu khi nghiệp vụ thật sự cập nhật theo partition.

### Câu 8 — DELETE partition

`DELETE FROM ... WHERE device_id=? AND event_day=?` có thể hợp lệ không?

**Đáp án:** Có, đây là thao tác xóa **partition** nếu đủ partition-key parts. Cực kỳ khác DELETE một row; phải dùng có kiểm soát.

### Câu 9 — Immutable primary key

Muốn đổi `event_time` bằng `UPDATE SET`. Có phù hợp không?

**Đáp án:** Không. Row placement định bởi PK; thường cần INSERT key mới + DELETE key cũ, idempotency và reconciliation.

### Câu 10 — Date type

Prepared CQL marker `event_day date`, Java bind `"2026-11-21"` bằng String. Vì sao có thể lỗi dù literal cqlsh hợp lệ?

**Đáp án:** CQL literal parsing theo ngữ cảnh khác typed Java bind. Dùng `LocalDate` và codec đúng.

### Câu 11 — Timestamp vs date

Một event tại `2026-11-21T17:30:00Z`. Event day theo UTC và Việt Nam có cùng ngày không?

**Đáp án:** Không. UTC là 2026-11-21, Việt Nam (+07) là 2026-11-22. Nếu writer/reader dùng khác policy, query hợp lệ nhưng sai partition.

### Câu 12 — Decimal

Cột `decimal` nên map qua Java `double` rồi chuyển BigDecimal hay bind `BigDecimal` trực tiếp?

**Đáp án:** Dùng `BigDecimal` để giữ chính xác số thập phân khi nghiệp vụ yêu cầu; qua double có thể tạo sai số.

### Câu 13 — Timeuuid

UUID v4 có thể bind vào `timeuuid` vì đều là đối tượng `UUID` trong Java không?

**Đáp án:** Không mặc định. CQL timeuuid yêu cầu UUID mang semantics/version time-based phù hợp.

### Câu 14 — Null primary key

`INSERT` với `device_id=null` có hợp lệ không?

**Đáp án:** Không. Mọi primary-key component phải xác định; validate tại API boundary trước khi bind.

### Câu 15 — Counter

Muốn đặt `total_events=10` trên counter table bằng `SET total_events=10`. Có đúng không?

**Đáp án:** Không. Counter dùng tăng/giảm theo expression; absolute count cần model khác.

### Câu 16 — Counter retry

Một increment counter timeout, client retry. Có thể cộng hai lần không?

**Đáp án:** Có. Counter increment không idempotent; timeout không chứng minh attempt trước chưa apply.

### Câu 17 — TTL

`USING TTL 3600` trên row có event_time của tuần trước có tự hết hạn ngay vì event cũ không?

**Đáp án:** Không. TTL theo mutation/expiration semantics, không tự tính từ data column event_time.

### Câu 18 — LWT

`INSERT IF NOT EXISTS` timeout rồi retry trả `wasApplied()==false`. Có kết luận attempt đầu thất bại không?

**Đáp án:** Không. Row có thể đã được tạo lần đầu; cần đối soát identity/outcome.

### Câu 19 — BATCH

Dồn 1.000 mutations sai WHERE vào một BATCH có khiến chúng hợp lệ không?

**Đáp án:** Không. Mỗi statement vẫn phải pass validation; batch lớn còn tăng coordinator overhead.

### Câu 20 — Collection type

CQL marker `map<text,int>` nhưng Java bind `Map<String,String>`. Lỗi ở đâu?

**Đáp án:** Có thể client codec/type error hoặc server validation; sửa typed map và entry conversion, không cast toàn object sang text.

### Câu 21 — JOIN

Cần lấy device name và readings trong một CQL JOIN. Cassandra có native general SQL join planner không?

**Đáp án:** Không. Dùng denormalization/read model, bounded app orchestration hoặc analytical engine theo workload.

### Câu 22 — COUNT

`SELECT count(*)` trong một partition lớn có thể hợp lệ. Có luôn nhanh không?

**Đáp án:** Không. Có thể phải scan nhiều dữ liệu; dùng aggregates/read model khi cần frequency cao.

### Câu 23 — DESCRIBE

`session.execute("DESCRIBE TABLE ...")` bị syntax error. Vì sao?

**Đáp án:** `DESCRIBE` là chức năng cqlsh/client, không phải native CQL statement trong session.execute. Dùng driver metadata hoặc system_schema phù hợp.

### Câu 24 — Quoted identifiers

Schema tạo table `"DeviceEvents"`, Java query `deviceevents`. Vì sao có thể unknown table?

**Đáp án:** Quoted identifiers phân biệt case; dùng đúng qualified quoted name và nhất quán migration.

### Câu 25 — CL

`InvalidQuery` vì thiếu PK. Hạ `LOCAL_QUORUM` xuống `ONE` có hợp lý không?

**Đáp án:** Không. CL chỉ thay replica acknowledgement/consistency requirements, không sửa CQL validation.

### Câu 26 — Prepared marker error

`setString("event_day", ...)` ném exception trước khi gọi execute. Có nên retry networking không?

**Đáp án:** Không. Đây là lỗi client-side mapping; sửa setter/type và test marker metadata.

### Câu 27 — Schema agreement

Một số coordinators báo unknown column ngay sau migration. Điều tra gì?

**Đáp án:** Đúng cluster, migration order, schema agreement, quoted identifiers, driver schema cache/reprepare. Không xóa system tables.

### Câu 28 — Tenant authorization

CQL bind đúng device UUID nhưng thuộc tenant khác. Driver chuẩn hóa type có ngăn lộ dữ liệu không?

**Đáp án:** Không. Ứng dụng cần kiểm principal/tenant ownership trước query; prepared markers không thay authorization.

### Câu 29 — Error handling

`InvalidQueryException` tăng sau deploy. Có nên catch rồi trả empty list để tránh 500 không?

**Đáp án:** Không. Empty result khác validation failure, che bug deployment. Ghi error kind/query template an toàn và rollback/fix.

### Câu 30 — Query-first design

Nhu cầu mới tìm 20 WARN events theo ngày trên tất cả thiết bị. Cần lựa chọn gì?

**Đáp án:** Thiết kế read model/index hợp release và workload, partition theo day/status/shard phù hợp; kiểm hot partitions, write amplification, TTL và SLO. Không mặc định full scan.

## 33. Checklist trước khi merge bản sửa InvalidQuery

### 33.1. Chẩn đoán

~~~text
[ ] Xác định đúng InvalidQuery, SyntaxError, codec, auth, timeout hay Unprepared.
[ ] Có exception class, safe cause, query template và UTC timestamp.
[ ] Biết lỗi xảy ra tại prepare, bind, execute hay paging.
[ ] Đã xem schema thực, PK, clustering order, columns/types/indexes.
[ ] Đã kiểm keyspace, quoted identifiers, migration version/agreement.
[ ] Đã xác minh Cassandra/driver release và CQL rules của release đó.
[ ] Không suy server down từ client codec error hoặc InvalidQuery.
~~~

### 33.2. Query và data model

~~~text
[ ] Read/update có đầy đủ partition/clustering key phù hợp.
[ ] Clustering range đúng prefix, ORDER BY đúng clustering rules.
[ ] Không dùng ALLOW FILTERING chỉ để loại lỗi production.
[ ] IN/fan-out có quota partitions, bytes, concurrency và deadlines.
[ ] Regular-column filters có access path/index/table phù hợp.
[ ] Không có JOIN/subquery/OFFSET SQL được giả định như CQL.
[ ] Aggregations/GROUP BY/DISTINCT đã kiểm hỗ trợ và chi phí.
[ ] DELETE partition và DELETE row được phân biệt.
[ ] Primary-key migration có table mới/backfill nếu cần.
[ ] Có query-first design cho nhu cầu lookup/sort mới.
~~~

### 33.3. Data types và mutation semantics

~~~text
[ ] UUID/LocalDate/Instant/BigDecimal/BigInteger bind đúng types.
[ ] Timestamp precision và event_day timezone thống nhất writer/reader.
[ ] Timeuuid có UUID version phù hợp.
[ ] Collections/UDT/tuple có exact element/field types.
[ ] Null và unset semantics đúng, không cho null PK.
[ ] Counter increment/TTL/conditional restrictions đúng release.
[ ] BATCH chỉ chứa mutation hợp lệ, không làm bulk transaction bừa.
[ ] LWT condition/wasApplied/timeout/retry được xử lý đúng.
[ ] Không chuyển counter/PK type tùy tiện bằng ALTER.
~~~

### 33.4. Java, tests và rollout

~~~text
[ ] Prepared CQL dùng markers cho values; identifiers theo allowlist.
[ ] API input validation fail sớm trước Cassandra khi có thể.
[ ] Codec/type error không bị retry vô hạn.
[ ] Server InvalidQuery không bị đổi thành empty result.
[ ] Không log secrets, tenant IDs, bind values hay raw CQL nguy hiểm.
[ ] Unit tests validate UUID/date/Instant/limit/tenant ownership.
[ ] Integration tests chạy trên đúng Cassandra/driver versions.
[ ] Có negative tests cho missing key/wrong type/ORDER BY.
[ ] Có positive read/write tests với dataset seeded, CL phù hợp.
[ ] Nếu thêm index/table, đã test p99/timeout/compaction/write cost.
[ ] Nếu đổi PK, có dual-write/backfill/checkpoint/reconciliation.
[ ] Deployment migration trước app rollout, canary và rollback rõ.
[ ] Không chạy STEP 6 QA chuyên môn trong bước viết này.
~~~

## 34. Tổng kết

Để xử lý **InvalidQuery do điều kiện khóa, kiểu dữ liệu hoặc truy vấn không được hỗ trợ** trong Cassandra:

1. **Tách lỗi server validation khỏi parser, Java codec, auth và timeout.** Một thông điệp ở lớp khác đòi biện pháp khác.
2. **Thiết kế bảng theo truy vấn**: partition key cho placement, clustering key cho phạm vi/thứ tự trong partition, không áp dụng WHERE/ORDER BY SQL tùy ý.
3. **Không bỏ thành phần composite partition key** hoặc nhảy qua clustering prefix khi chưa có access path được release hỗ trợ.
4. **`ALLOW FILTERING` không phải tối ưu truy vấn**, còn `LIMIT`/page size không giới hạn toàn bộ scan/IO.
5. **Bind đúng CQL types bằng Java Driver**: UUID, LocalDate, Instant, BigDecimal, collection/UDT; literal parser và typed bind không giống nhau.
6. **Đọc DML restrictions theo từng operation**: INSERT/UPDATE/DELETE khác nhau về full key, counter/TTL/LWT/batch có semantics riêng.
7. **Không giả định CQL là SQL quan hệ**: joins, subqueries, OR, GROUP BY, ORDER BY, OFFSET có giới hạn/khác biệt theo version.
8. **Một query hợp lệ có thể trả sai dữ liệu hoặc quá chậm** nếu dùng sai event_day timezone, retention, index selectivity hoặc query distribution.
9. **Không hạ CL, chạy repair, tăng retry hay trả empty list để che InvalidQuery.** Sửa data model, mapping, schema migration hoặc query đúng nguyên nhân.
10. **Xác minh bằng cả negative và positive tests** trên Cassandra version thực, và đo p99/CPU/disk khi đổi index/schema.
11. **Theo dõi schema agreement, quoted identifiers và driver prepared statement metadata** trong rolling migrations.
12. **Giữ security và correctness**: prepared statements chống injection giá trị, nhưng tenant authorization/ownership vẫn là trách nhiệm ứng dụng.

Câu hỏi chẩn đoán hữu ích nhất không phải “Làm sao thêm cú pháp cho query hết lỗi?”, mà là: **“Truy vấn cần trả dữ liệu gì, partition/clustering key nào phục vụ đúng access path, Java đang bind đúng type chưa, Cassandra release hỗ trợ operator đó không, và bản sửa có giữ được correctness/SLO trong workload thực hay không?”** Khi trả lời đủ các câu này, `InvalidQuery` trở thành tín hiệu về thiết kế và validation — không phải lý do để mở full scan, hạ consistency hay che lỗi.

