# Chọn timestamp và timeuuid theo thứ tự đọc cần bảo đảm

Một ứng dụng lưu dữ liệu theo thời gian thường phải trả lời câu hỏi **“dữ liệu nào xuất hiện trước, dữ liệu nào xuất hiện sau?”**. Ví dụ, dashboard thiết bị muốn hiển thị 100 phép đo gần nhất; lịch sử đơn hàng muốn sắp xếp theo **thời điểm sự kiện thực sự xảy ra**; hệ thống nhật ký muốn cho người dùng xem các bản ghi theo **thứ tự được tiếp nhận**. Ba yêu cầu này nghe tương tự, nhưng có thể dẫn đến **hai kiểu clustering key khác nhau** trong Apache Cassandra: `timestamp` và `timeuuid`.

Với **Spring Data Cassandra**, cả hai kiểu có thể truy cập qua entity mapping, `CassandraRepository`, `CassandraTemplate`, hoặc CQL được gửi bằng `CqlTemplate`/Java driver. Chọn kiểu cột chỉ là một phần: thứ tự đọc phụ thuộc **partition key, clustering columns, CLUSTERING ORDER BY, nguồn thời gian, tie-breaker và cách phân trang**.

**Điểm cốt lõi:** `timestamp` giúp sắp xếp theo **mốc thời gian do bạn cung cấp**; `timeuuid` giúp định danh và sắp xếp theo **thành phần thời gian bên trong UUID phiên bản 1**. **Cả hai đều không tự chứng minh thứ tự nghiệp vụ tuyệt đối giữa nhiều writer**. Nếu yêu cầu của hệ thống là “event số 102 chắc chắn sau event số 101 dù clock lệch”, bạn cần một **sequence/version có nguồn thứ tự đáng tin cậy**, không chỉ thay kiểu cột.

Bài nằm trong chương **Dữ liệu thời gian** của module **SPRING_DATA_CASSANDRA**, tập trung vào truy cập Apache Cassandra bằng Spring Data với entity mapping, repository, CassandraTemplate và truy vấn CQL; đồng thời vận dụng thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng. Các ví dụ tham chiếu Apache Cassandra CQL, **Java driver 4.19**, **Spring Data Cassandra 4.5.x** và Java 17+; cần kiểm tra tương thích với stack thực tế trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **event time**, **ingest/receive time**, **write timestamp Cassandra** và **thời điểm tạo timeuuid**.
2. Giải thích kiểu CQL **`timestamp` (millisecond từ Unix epoch)** và **`timeuuid` (UUID v1, 128 bit chứa timestamp theo tick 100 ns)**.
3. Lựa chọn clustering key phù hợp với câu hỏi: “đọc theo thời điểm event” hay “đọc theo lúc ghi nhận”.
4. Nhận diện nguy cơ **ghi đè khi dùng `timestamp` làm clustering key duy nhất** và cách thêm tie-breaker `event_id`.
5. Dùng `CLUSTERING ORDER BY (... DESC)` để lấy dữ liệu mới nhất **trong một partition** mà không phải sort tập dữ liệu rộng.
6. Tạo `timeuuid` bằng CQL `now()` hoặc Java driver `Uuids.timeBased()`; không dùng UUID v4 trong cột `timeuuid`.
7. Truy vấn timeuuid theo khoảng với `min_timeuuid`/`max_timeuuid` hoặc driver `Uuids.startOf`/`endOf`.
8. Hiểu rằng **độ phân giải 100 ns trong UUID v1 không phải độ chính xác đồng hồ 100 ns**, không bảo đảm thứ tự tuyệt đối toàn hệ thống.
9. Thiết kế **time bucket** cho partition, query nửa mở `[start, end)`, phân trang và đọc qua nhiều bucket.
10. Ánh xạ hai kiểu dữ liệu trong Spring Data Cassandra bằng `Instant`, `UUID` và composite primary key.
11. Biết khi nào bắt buộc cần **sequence tăng đơn điệu, single writer hoặc CAS/LWT** để bảo vệ thứ tự nghiệp vụ.
12. Viết integration test kiểm chứng ordering, event trùng mili-giây, lọc khoảng và tính ổn định khi phân trang.

## 2. Trước khi chọn kiểu CQL: “thứ tự” có nghĩa gì?

Hãy làm rõ ba thời điểm trong một sự kiện:

| Tên | Tình huống | Câu hỏi nó trả lời |
|---|---|---|
| **Event time** (`event_at`) | Sensor đo nhiệt độ lúc 09:00:01.123 UTC | Sự kiện **thực sự được ghi nhận ở nguồn** lúc nào? |
| **Ingest time** (`received_at`) | Server nhận message lúc 09:00:07 UTC | Hệ thống **tiếp nhận** sự kiện khi nào? |
| **Persistence/write time** | Cassandra xử lý mutation | Mutation được **ghi** theo đồng hồ và write timestamp nào? |

Ví dụ đường truyền mất kết nối trong 10 phút:

```text
09:00:00  Sensor sinh event A
09:00:01  Sensor sinh event B
09:10:00  Gateway gửi lại event B
09:10:02  Gateway gửi lại event A
09:10:03  Cassandra nhận các mutation
```

Nếu sắp xếp theo **event time**, ta muốn `A, B`.

Nếu sắp xếp theo **ingest time**, ta có thể thấy `B, A`.

Nếu sắp xếp theo **thứ tự request đến coordinator**, ngay cả ingest time/`timeuuid` không tự cho bạn một thứ tự toàn hệ thống khi request đi qua **nhiều JVM, coordinator và đồng hồ**.

### 2.1. Thứ tự cần bảo đảm có nhiều cấp

| Yêu cầu đọc | Mức bảo đảm mong muốn | Lựa chọn khởi đầu |
|---|---|---|
| Dashboard: các sự kiện **theo thời điểm đo** | Sắp theo timestamp do nguồn cung cấp | `event_at timestamp` + `event_id` làm tie-break |
| Feed: các sự kiện **theo thời điểm API ghi nhận** | Sắp theo thời điểm tạo khóa khi ingest | `ingest_id timeuuid` (UUID v1) |
| Nhận nhiều event trong cùng 1 ms | Không được ghi đè/đánh mất event | `timestamp + event_id` hoặc `timeuuid` sinh độc lập |
| Lấy dữ liệu theo khoảng thời gian | Phạm vi clustering theo thời gian trong partition | Cả hai, với cú pháp bound khác nhau |
| Cùng một event retry nhiều lần | Một event logic chỉ xuất hiện một lần | **Event ID ổn định/idempotency key**, không sinh ID mới mỗi retry |
| “102 phải sau 101” bất kể clock | **Strict business order** | `sequence bigint` do nguồn thứ tự duy nhất/CAS cấp phát |
| Tổng hợp nhiều thiết bị theo time | Sắp xếp **toàn cục** sau khi đọc nhiều partition | Merge tại ứng dụng/read model; không chỉ `ORDER BY` Cassandra |

Không nên chọn `timeuuid` chỉ vì chữ “time” hay chọn `timestamp` chỉ vì dễ hiển thị. Hãy viết **truy vấn quan trọng nhất** trước, rồi chọn primary key.

### 2.2. Ba loại timestamp khác nhau

**Lưu ý đặc biệt:**

- Cột CQL `timestamp`: giá trị thời điểm, lưu bằng **số mili-giây** từ Unix epoch.
- Thành phần thời gian của `timeuuid`: UUID v1 dùng **số tick 100 nano-giây** tính từ mốc Gregorian **1582-10-15**, kết hợp clock sequence/node identifier.
- **Write timestamp** của Cassandra (dùng khi giải quyết LWW): metadata mutation tính bằng **microsecond** từ Unix epoch, có thể lấy bằng `WRITETIME(column)` với regular column.

Chúng không tự đồng bộ hay thay thế nhau. Một row có `event_at` năm 2025, `timeuuid` được tạo năm 2026 do backfill, và `WRITETIME(payload)` lúc nhập dữ liệu năm 2026 — tất cả đều có thể đúng.

## 3. Kiểu timestamp: mốc thời gian tường minh

### 3.1. Dữ liệu và độ phân giải

Cassandra lưu `timestamp` dưới dạng signed 64-bit integer biểu diễn **mili-giây từ 1970-01-01T00:00:00Z**.

```sql
SELECT *
FROM system.local;
```

Lệnh `SELECT` trên chỉ là ví dụ CQL cơ bản; khi tạo bảng có kiểu timestamp, bạn có thể truyền literal có timezone rõ:

```sql
CREATE TABLE IF NOT EXISTS sdc_time_lab.timestamp_demo (
    id uuid PRIMARY KEY,
    occurred_at timestamp
);

INSERT INTO sdc_time_lab.timestamp_demo (id, occurred_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-25T09:00:00.123Z'
);
```

`09:00:00.123Z` được lưu như một **instant UTC**, không lưu nguyên chuỗi timezone đầu vào. Khi hiển thị, cqlsh/client có thể áp dụng timezone khác; hãy cấu hình/biểu diễn UTC rõ ràng để không nhầm.

**Không nhầm** `timestamp` với CQL `time`: kiểu `time` biểu diễn giờ trong ngày với độ phân giải nanosecond nhưng **không có ngày**, không phù hợp làm thứ tự của log kéo dài qua nhiều ngày.

### 3.2. Java Instant ánh xạ sang CQL timestamp

Java driver/Spring Data thường ánh xạ:

```java
Instant eventAt = Instant.parse("2026-11-25T09:00:00.123Z");
```

sang CQL `timestamp`.

Nếu upstream cung cấp `Instant` có phần nanosecond, cột `timestamp` Cassandra **không bảo toàn độ phân giải nanosecond**. Ví dụ `...123456789Z` khi round-trip qua cột CQL timestamp không còn đủ các chữ số phần lẻ ban đầu. Viết test tương đương theo **millisecond** thay vì assert toàn bộ nanosecond.

### 3.3. Timestamp không tự là khóa duy nhất

Nếu schema chỉ có:

```sql
CREATE TABLE sdc_time_lab.bad_samples (
    device_id uuid,
    day_bucket date,
    event_at timestamp,
    value double,
    PRIMARY KEY ((device_id, day_bucket), event_at)
);
```

thì hai event cùng `device_id`, cùng `day_bucket` và cùng `event_at` **có cùng primary key**. Mutation sau có thể **ghi đè hoặc hòa giải cùng row** thay vì tạo dòng mới.

```text
Event A: event_at=09:00:00.123, value=20.0
Event B: event_at=09:00:00.123, value=21.0
Cùng partition + cùng clustering key -> cùng row logic
```

**Đây là lỗi thiết kế thường gặp nhất khi chọn timestamp làm clustering key cho workload tần suất cao.** Đừng tin “sensor chỉ gửi 10 event mỗi giây, chắc chắn không trùng mili-giây” khi có retry, nhiều source, batch import hoặc clock bị làm tròn.

### 3.4. Cách sửa: timestamp + tie-breaker

Thêm một clustering key `event_id uuid`:

```sql
PRIMARY KEY ((device_id, day_bucket), event_at, event_id)
```

Hai event có cùng mili-giây nhưng khác `event_id` trở thành **hai row riêng**. Sorting theo thời gian đến mili-giây, sau đó dùng giá trị UUID làm thứ tự **deterministic khi timestamp trùng**.

**Không diễn giải tie-breaker UUID v4 thành “event nào đến trước”.** UUID v4 giúp phân biệt các event, nhưng thứ tự byte/UUID giữa hai event trùng timestamp không đại diện cho thời gian thực tế.

## 4. Kiểu timeuuid: UUID v1 có thành phần thời gian

### 4.1. Timeuuid không phải một timestamp đơn thuần

CQL `timeuuid` chỉ nhận **UUID phiên bản 1** (UUID time-based). UUID này có 128 bit, trong đó có trường thời gian với đơn vị tick **100 nano-giây** từ mốc 1582-10-15; các phần còn lại gồm clock sequence và node identifier.

So sánh:

| Kiểu CQL | Dung lượng logic | Chứa thời gian? | Chứa thành phần giúp phân biệt event? |
|---|---:|---|---|
| `timestamp` | 8 byte | Có, millisecond Unix epoch | **Không** |
| `uuid` | 16 byte | Không có cam kết timestamp; có thể là UUID v4 | Có identifier, nhưng không mang thứ tự thời gian đáng tin |
| `timeuuid` | 16 byte | Có, UUID v1 timestamp | Có clock sequence/node identifier |

Cassandra có comparator riêng cho `timeuuid` để sắp xếp theo phần thời gian trước khi xét phần còn lại. Đây là điểm khiến `timeuuid` hữu ích cho **clustering key của feed/event log**.

### 4.2. CQL now() tạo timeuuid

```sql
CREATE TABLE IF NOT EXISTS sdc_time_lab.feed_by_source_day (
    source_id uuid,
    ingest_day date,
    ingest_id timeuuid,
    payload text,
    event_at timestamp,
    PRIMARY KEY ((source_id, ingest_day), ingest_id)
) WITH CLUSTERING ORDER BY (ingest_id DESC);
```

Khi ghi:

```sql
INSERT INTO sdc_time_lab.feed_by_source_day
(source_id, ingest_day, ingest_id, payload, event_at)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    now(),
    'Received sample',
    '2026-11-25T08:55:00Z'
);
```

**Chú ý lab:** `now()` tạo timeuuid theo thời gian **coordinator đang thực thi**, trong khi `ingest_day = '2026-11-25'` là giá trị bạn điền bằng tay. Khi chạy vào ngày khác, hãy đổi `ingest_day` cho phù hợp ngày thực tế để tránh khóa thời gian và bucket không đồng nhất. Production nên sinh cả key và bucket bằng một chiến lược nguồn thời gian nhất quán.

`now()` có ích khi INSERT. **Không** dùng `WHERE ingest_id = now()` để tìm hàng vừa chèn: mỗi lần gọi `now()` tạo UUID mới, không trùng với giá trị trước đó.

### 4.3. timeuuid cho thứ tự ingest, không tự cho thứ tự event

Giả sử một event được đo từ 08:00 nhưng nhận lúc 09:00. Nếu gọi `now()` lúc ingest:

```text
event_at  = 08:00 (do sensor cung cấp)
ingest_id = UUID v1 có thời gian 09:00
```

Khi query theo `ingest_id DESC`, row được xếp như **event tiếp nhận lúc 09:00**, không như event thực sự xảy ra lúc 08:00.

Nếu muốn sắp theo **event time có nguồn riêng**, chọn `event_at timestamp` làm clustering key chính và thêm tie-breaker, hoặc dùng một thiết kế khác có thứ tự authoritative. Không đổi nhãn `ingest_id` thành `event_id` rồi ngầm coi đây là event time.

### 4.4. Timeuuid không bảo đảm thứ tự tuyệt đối toàn cluster

Mặc dù UUID v1 có tick 100 ns:

- **Độ phân giải biểu diễn** không đồng nghĩa đồng hồ máy chính xác tới 100 ns.
- Mỗi JVM/coordinator có clock riêng, có thể bị skew hoặc chỉnh bởi NTP/VM.
- Nhiều writer chạy đồng thời không chia sẻ global sequence.
- Retry một event mà tạo **timeuuid mới** sẽ tạo **một row mới** nếu ID là clustering key.
- Cùng một event có thể được xử lý ở coordinator khác vào thời điểm khác.
- Khi thời gian được làm tròn/bằng nhau, phần clock sequence/node đem lại thứ tự deterministic, **không phải thứ tự nghiệp vụ**.

Vì thế **timeuuid là một khóa sắp xếp thuận tiện theo thời điểm tạo**, không phải “globally monotonically increasing event sequence”.

### 4.5. Không dùng UUID.randomUUID cho timeuuid

Trong Java:

```java
UUID randomId = UUID.randomUUID(); // UUID v4
```

UUID v4 phù hợp cột CQL `uuid`, **không phải** cột `timeuuid`. Một prepared INSERT gửi UUID v4 vào cột `timeuuid` có thể bị server từ chối vì type chỉ cho UUID v1.

Thay bằng:

```java
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.util.UUID;

UUID ingestId = Uuids.timeBased(); // UUID v1
```

Driver `Uuids.timeBased()` tạo UUID v1 theo thời gian **lúc tạo trong JVM**. CQL `now()` tạo trên **coordinator**. Hai cách đều thích hợp cho thời gian ghi nhận theo hệ thống tương ứng nhưng **không nên trộn mà không đánh giá clock policy và order**.

## 5. Sắp xếp clustering columns đúng với truy vấn

### 5.1. Cassandra không ORDER BY tùy ý như hệ SQL truyền thống

Cassandra chỉ hỗ trợ `ORDER BY` trong phạm vi truy vấn phù hợp với **partition key** và **clustering order**. Kết quả mặc định được trả theo thứ tự clustering đã định nghĩa; có thể yêu cầu thứ tự đảo ngược **hợp lệ** của clustering order.

Một query:

```sql
SELECT *
FROM sdc_time_lab.feed_by_source_day
ORDER BY ingest_id DESC;
```

không tự trở thành “top feed của toàn hệ thống”: không có điều kiện partition key nên có thể bị từ chối hoặc yêu cầu quét không phù hợp. **Phải hạn chế partition**.

### 5.2. DESC giúp lấy mới nhất trước

Trong bảng `feed_by_source_day`:

```sql
PRIMARY KEY ((source_id, ingest_day), ingest_id)
WITH CLUSTERING ORDER BY (ingest_id DESC)
```

Query theo đúng partition:

```sql
SELECT ingest_id, payload, event_at
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
LIMIT 20;
```

Trả tối đa 20 row theo **timeuuid giảm dần** trong bucket đó. Không cần `ALLOW FILTERING`.

### 5.3. Mixed ordering của nhiều clustering columns

Với `timestamp` và `uuid`:

```sql
WITH CLUSTERING ORDER BY (event_at DESC, event_id ASC)
```

thì dữ liệu được sắp:

1. `event_at` **mới nhất trước**.
2. Nếu hai giá trị `event_at` trùng đến mili-giây, `event_id` sắp theo comparator của kiểu `uuid` **tăng dần** để giữ kết quả xác định.

Không thể tự yêu cầu một tổ hợp thứ tự khác hoàn toàn so với clustering order đã khai báo. Cassandra thường cho phép **thứ tự đã khai báo hoặc đảo ngược toàn bộ**, không phải đảo riêng một clustering column tùy ý.

### 5.4. Không phải sort toàn cục trên nhiều partition

Nếu đọc bucket ngày 24/11 và 25/11 hoặc hai thiết bị khác nhau, `ORDER BY event_at DESC` bên trong mỗi query **không sắp xếp toàn cục** mọi row của hai partition.

Muốn hiển thị timeline tổng hợp, cần:
- Truy vấn những partition/bucket liên quan.
- **Merge** các chuỗi đã sắp thứ tự ở tầng ứng dụng, có tie-breaker thống nhất.
- Hoặc xây bảng **read model theo timeline chung** nếu access pattern đòi hỏi.
- Có giới hạn số partition, số row, concurrency và deadline.

Đừng dùng `ALLOW FILTERING` chỉ để “có ORDER BY toàn cluster”.

## 6. Thiết kế A: dữ liệu theo event time dùng timestamp + UUID

Đây là lựa chọn khởi đầu cho telemetry hoặc event có mốc thời gian do **nguồn dữ liệu cung cấp**.

### 6.1. Keyspace lab

```sql
CREATE KEYSPACE IF NOT EXISTS sdc_time_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};
```

Lưu ý: các bảng ví dụ ở mục 3/4 giả định keyspace này đã có. Khi chạy tuần tự trong `cqlsh`, **chạy CREATE KEYSPACE trước** các `CREATE TABLE`.

`SimpleStrategy` và replication factor 1 chỉ dùng cho lab một node; production nhiều datacenter cần `NetworkTopologyStrategy`/RF/consistency phù hợp.

### 6.2. Schema timestamp chính, UUID phân biệt

```sql
CREATE TABLE IF NOT EXISTS sdc_time_lab.measurements_by_device_day (
    device_id uuid,
    bucket_day date,
    event_at timestamp,
    event_id uuid,
    temperature_c double,
    received_at timestamp,
    PRIMARY KEY (
        (device_id, bucket_day),
        event_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_at DESC,
    event_id ASC
);
```

Thiết kế:

- `device_id + bucket_day` tạo **composite partition key**, hạn chế kích thước partition theo ngày.
- `event_at` là **clustering key chính**; biểu diễn thời gian event.
- `event_id` phân biệt các event trùng millisecond, làm tie-breaker deterministic.
- `received_at` giữ mốc ingest để phân tích độ trễ, **không quyết định thứ tự đọc**.
- `temperature_c` là regular column.
- Dùng `bucket_day` theo **ngày UTC của `event_at`**. Nếu event time là từ nguồn, late arrivals vẫn được đưa đúng bucket ngày đã xảy ra.

### 6.3. Seed dữ liệu có trùng mili-giây

```sql
INSERT INTO sdc_time_lab.measurements_by_device_day
(device_id, bucket_day, event_at, event_id,
 temperature_c, received_at)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-25',
    '2026-11-25T09:00:00.123Z',
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    24.5,
    '2026-11-25T09:00:05Z'
);

INSERT INTO sdc_time_lab.measurements_by_device_day
(device_id, bucket_day, event_at, event_id,
 temperature_c, received_at)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-25',
    '2026-11-25T09:00:00.123Z',
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    24.6,
    '2026-11-25T09:00:06Z'
);

INSERT INTO sdc_time_lab.measurements_by_device_day
(device_id, bucket_day, event_at, event_id,
 temperature_c, received_at)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-25',
    '2026-11-25T09:00:01.100Z',
    cccccccc-cccc-4ccc-8ccc-cccccccccccc,
    24.7,
    '2026-11-25T09:00:07Z'
);
```

Kỳ vọng có **3 row**, trong đó hai row cùng timestamp `09:00:00.123Z` nhưng khác `event_id`. Nếu schema chỉ có `event_at` làm clustering key, hai event này sẽ cùng khóa và **không còn hai row riêng**.

### 6.4. Query mới nhất trong một bucket

```sql
SELECT event_at, event_id, temperature_c, received_at
FROM sdc_time_lab.measurements_by_device_day
WHERE device_id = 33333333-3333-4333-8333-333333333333
  AND bucket_day = '2026-11-25'
LIMIT 50;
```

Do `CLUSTERING ORDER BY (event_at DESC, event_id ASC)`, row `09:00:01.100Z` xuất hiện trước hai row `09:00:00.123Z`. Trong nhóm trùng millisecond, `event_id` quyết định thứ tự deterministic, **không thể suy ra event nào xảy ra trước** nếu sensor không có sequence khác.

### 6.5. Truy vấn nửa mở [start, end)

```sql
SELECT event_at, event_id, temperature_c
FROM sdc_time_lab.measurements_by_device_day
WHERE device_id = 33333333-3333-4333-8333-333333333333
  AND bucket_day = '2026-11-25'
  AND event_at >= '2026-11-25T09:00:00.000Z'
  AND event_at <  '2026-11-25T09:01:00.000Z'
LIMIT 100;
```

Khoảng **`[start, end)`** có hai lợi ích:

- Không đếm trùng event đúng ở biên `end` khi ghép các cửa sổ liên tiếp.
- Dễ chuyển ngày/bucket và giữ quy tắc rõ ràng.

**Lưu ý:** với `event_at` kiểu timestamp, biên phải được đưa về **độ phân giải mili-giây** của CQL. Nếu nguồn dùng nanosecond, xác định quy tắc làm tròn/cắt trước khi ghi và query.

### 6.6. Late event và backfill

Một event thực tế xảy ra ngày 24/11 nhưng gateway nhập ngày 25/11:

```text
event_at     = 2026-11-24T23:59:55Z
received_at  = 2026-11-25T00:10:00Z
bucket_day   = 2026-11-24
```

Nếu yêu cầu là **timeline theo event time**, bucket được tính từ **`event_at`**, không phải thời điểm ghi. Phải chấp nhận rằng dữ liệu cũ có thể được chèn vào **vị trí trước** của timeline sau khi client đã lấy page đầu.

**Không có một snapshot cố định chỉ vì query đã ORDER BY**. Khi có late events, client phải định nghĩa watermark, độ trễ cho phép hoặc refresh/merge.

## 7. Thiết kế B: feed theo thời điểm tạo khóa dùng timeuuid

### 7.1. Schema timeuuid

```sql
CREATE TABLE IF NOT EXISTS sdc_time_lab.feed_by_source_day (
    source_id uuid,
    ingest_day date,
    ingest_id timeuuid,
    event_at timestamp,
    payload text,
    PRIMARY KEY (
        (source_id, ingest_day),
        ingest_id
    )
) WITH CLUSTERING ORDER BY (ingest_id DESC);
```

Trong kiểu thiết kế này, `ingest_id` **vừa là định danh row, vừa là trục thời gian đọc**. Mỗi event được cấp một timeuuid mới khi được ingest.

### 7.2. CQL ghi bằng now()

```sql
INSERT INTO sdc_time_lab.feed_by_source_day
(source_id, ingest_day, ingest_id, event_at, payload)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    now(),
    '2026-11-24T23:59:55Z',
    'Late event received today'
);
```

Khi chạy vào một ngày UTC khác, hãy thay `ingest_day` theo thời điểm tạo `now()`. Thực tế tốt hơn là **tạo timeuuid tại ứng dụng trước rồi tính ingest day từ chính UUID đó**, nhằm tránh lệch bucket ở ranh giới ngày (xem mục 9).

Để thử thêm row:

```sql
INSERT INTO sdc_time_lab.feed_by_source_day
(source_id, ingest_day, ingest_id, event_at, payload)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    now(),
    '2026-11-25T09:05:00Z',
    'Another event'
);
```

### 7.3. Đọc timeuuid mới nhất

```sql
SELECT ingest_id, event_at, payload
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
LIMIT 20;
```

Các row được sắp theo **`ingest_id DESC`** trong partition. Nếu ví dụ chạy nhiều ngày sau 25/11/2026, timeuuid mang thời điểm chạy thực và nằm trong bucket bạn gán bằng tay; đó là **mismatch của bài lab**, không phải hành vi Cassandra tự sửa partition key.

### 7.4. Đọc thời điểm chứa trong timeuuid

CQL có hàm chuyển đổi:

```sql
SELECT ingest_id,
       to_timestamp(ingest_id) AS uuid_time,
       to_unix_timestamp(ingest_id) AS uuid_unix_ms,
       event_at,
       payload
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
LIMIT 20;
```

`to_timestamp(ingest_id)` trả thời điểm **theo millisecond**, và `to_unix_timestamp(ingest_id)` trả epoch **millisecond**. **Phần tick dưới millisecond bên trong UUID v1 có thể bị mất khi chuyển đổi** sang CQL timestamp; đừng suy ra hai timeuuid cùng `to_timestamp` thì có cùng UUID.

### 7.5. Tạo timeuuid trong JVM thay vì coordinator

Ở service Java:

```java
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.util.UUID;

UUID ingestId = Uuids.timeBased();
```

Ưu điểm: có UUID **trước khi gửi INSERT**, dễ lưu làm idempotency key, log correlation ID và tính bucket. Điểm đánh đổi: thành phần thời gian dựa trên **đồng hồ phía client**, không phải clock coordinator. Khi nhiều JVM có clock skew, thứ tự trong feed có thể không phản ánh “request nào được Cassandra nhận trước”.

`Uuids.timeBased()` cũng không nhận event time tùy ý; nó tạo timeuuid **ở thời điểm gọi**. Với event lịch sử, hãy giữ `event_at timestamp` riêng nếu muốn kiểm tra độ trễ event–ingest.

## 8. Range query cho timeuuid: min_timeuuid và max_timeuuid

### 8.1. Tại sao không WHERE timeuuid = chuỗi ngày?

Một `timeuuid` là **UUID đầy đủ**, không phải string timestamp:

```sql
-- Không dùng biểu thức tương đương thế này để tìm một khoảng:
SELECT *
FROM sdc_time_lab.feed_by_source_day
WHERE ingest_id = '2026-11-25T09:00:00Z';
```

Muốn lọc khoảng theo thời gian chứa trong UUID v1, Cassandra cung cấp các hàm tạo **UUID biên giả**:

- `min_timeuuid(t)`: timeuuid sentinel nhỏ nhất trong mốc millisecond `t` theo comparator Cassandra.
- `max_timeuuid(t)`: timeuuid sentinel lớn nhất trong mốc millisecond `t`.
- Tài liệu CQL cũ đôi khi viết `minTimeuuid`/`maxTimeuuid` theo camelCase; ví dụ ở đây dùng cú pháp **snake_case theo tài liệu CQL hiện tại**.

**Quan trọng:** các UUID này chỉ dùng **làm biên query**, không phải UUID v1 thông thường để INSERT. Chúng không tuân theo quá trình sinh unique timeuuid hợp lệ.

### 8.2. Khoảng nửa mở [start, end)

Giả sử muốn lấy sự kiện có thành phần thời gian **từ 08:00 đến trước 09:00 UTC**:

```sql
SELECT ingest_id, payload
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
  AND ingest_id >= min_timeuuid('2026-11-25 08:00:00+0000')
  AND ingest_id <  min_timeuuid('2026-11-25 09:00:00+0000')
LIMIT 100;
```

Với timeuuid v1 thông thường, dùng **`>= min_timeuuid(start)`** và **`< min_timeuuid(end)`** biểu diễn khoảng **`[start, end)`** ở độ phân giải millisecond của tham số. Những UUID sinh trong cùng millisecond ở start được bao gồm.

### 8.3. Khoảng mở (start, end)

Nếu muốn **loại toàn bộ UUID sinh đúng millisecond tại start và end**, dùng:

```sql
SELECT ingest_id, payload
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
  AND ingest_id > max_timeuuid('2026-11-25 08:00:00+0000')
  AND ingest_id < min_timeuuid('2026-11-25 09:00:00+0000');
```

So sánh:

| Yêu cầu | Biểu thức cho timeuuid |
|---|---|
| Bắt đầu **bao gồm** mọi UUID trong ms `start` | `ingest_id >= min_timeuuid(start)` |
| Bắt đầu **sau hẳn** ms `start` | `ingest_id > max_timeuuid(start)` |
| Kết thúc **trước hẳn** ms `end` | `ingest_id < min_timeuuid(end)` |
| Kết thúc **bao gồm** mọi UUID trong ms `end` | `ingest_id <= max_timeuuid(end)` |

**Không** dùng `>= max_timeuuid(start)` rồi nghĩ đã bao gồm các UUID đúng thời điểm `start`: sentinel `max` nằm **sau** các timeuuid thật trong millisecond đó.

### 8.4. Không dùng fake timeuuid làm khóa ghi

Ví dụ sau **không nên làm**:

```sql
-- Chỉ dùng để minh họa anti-pattern, KHÔNG INSERT:
-- ingest_id = min_timeuuid('2026-11-25 09:00:00+0000')
```

Hàm trả UUID giả cho mục đích so sánh, không bảo đảm uniqueness và có thể không phải UUID v1 sinh đúng chuẩn. Nếu gán nhiều event cùng boundary này, chúng có thể va chạm khóa và gây mất dữ liệu.

## 9. Java driver Uuids.timeBased(), startOf(), endOf()

Các tiện ích UUID v1 nằm trong `com.datastax.oss.driver.api.core.uuid.Uuids` của Java driver 4.19.

### 9.1. Sinh ID đúng kiểu

```java
import com.datastax.oss.driver.api.core.uuid.Uuids;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public class IngestKeyFactory {

    public record IngestKey(
        UUID ingestId,
        LocalDate ingestDay,
        Instant derivedIngestAt
    ) {}

    public IngestKey newKey() {
        UUID id = Uuids.timeBased();

        // unixTimestamp(UUID) -> epoch MILLISECOND, khác UUID.timestamp()
        long unixMillis = Uuids.unixTimestamp(id);
        Instant derived = Instant.ofEpochMilli(unixMillis);

        return new IngestKey(
            id,
            LocalDate.ofInstant(derived, ZoneOffset.UTC),
            derived
        );
    }
}
```

Cách này lấy `ingestDay` từ **chính timeuuid** thay vì gọi riêng `LocalDate.now()` rồi tạo UUID ở mốc ngày khác. Tính nhất quán **giữa bucket và khóa** tốt hơn, dù clock JVM vẫn có thể skew so với thực tế.

**Lưu ý kỹ thuật:** `UUID.timestamp()` của Java trả số tick 100 ns từ mốc **1582**, không phải Unix milliseconds. Phải dùng `Uuids.unixTimestamp(uuid)` nếu cần epoch millisecond.

### 9.2. Uuids.startOf/endOf là sentinel để query

```java
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.time.Instant;
import java.util.UUID;

Instant start = Instant.parse("2026-11-25T08:00:00Z");
Instant end = Instant.parse("2026-11-25T09:00:00Z");

UUID inclusiveStart = Uuids.startOf(start.toEpochMilli());
UUID exclusiveEnd = Uuids.startOf(end.toEpochMilli());

UUID inclusiveEnd = Uuids.endOf(end.toEpochMilli());
```

- `startOf(unixMillis)` tạo UUID biên nhỏ nhất tại millisecond.
- `endOf(unixMillis)` tạo UUID biên lớn nhất tại millisecond.
- **Không INSERT các UUID sentinel này.**
- Không truyền trực tiếp `uuid.timestamp()` vào `startOf` vì sai epoch/đơn vị.
- `startOf`/`endOf` dùng comparator **timeuuid của Cassandra**; Java `UUID.compareTo` **không có cùng thứ tự**. Đừng sort client bằng comparator Java mặc định rồi giả định kết quả khớp Cassandra timeuuid.

### 9.3. Prepared CQL đọc khoảng

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.uuid.Uuids;

public class FeedRangeDao {

    private final CqlSession session;
    private final PreparedStatement readWindow;

    public FeedRangeDao(CqlSession session) {
        this.session = session;
        this.readWindow = session.prepare("""
            SELECT ingest_id, event_at, payload
            FROM sdc_time_lab.feed_by_source_day
            WHERE source_id = ?
              AND ingest_day = ?
              AND ingest_id >= ?
              AND ingest_id < ?
            LIMIT ?
            """);
    }

    public ResultSet read(
        UUID sourceId, LocalDate day,
        Instant start, Instant end, int limit
    ) {
        if (!start.isBefore(end) || limit < 1 || limit > 500) {
            throw new IllegalArgumentException("Range/limit khong hop le");
        }

        UUID startBound = Uuids.startOf(start.toEpochMilli());
        UUID endBound = Uuids.startOf(end.toEpochMilli());

        BoundStatement stmt = readWindow.bind(
            sourceId, day, startBound, endBound, limit
        ).setPageSize(50);

        return session.execute(stmt);
    }
}
```

**Giới hạn đáng chú ý:**

- `Instant.toEpochMilli()` làm tròn về milliseconds; đoạn code dùng **boundary tại millisecond**. Nếu caller truyền `start = ...123456Z`, semantics không còn là chính xác tới micro/nanosecond. Nên validate `start/end` đã được chuẩn hóa về millisecond.
- Range trên `ingest_id` chỉ hữu ích nếu **ngày bucket phù hợp với thời gian embedded**. Nếu data backfill dùng ID hiện tại cho event lịch sử, query event time phải dùng bảng timestamp riêng.
- `setPageSize(50)` là kích thước page mục tiêu, không phải `LIMIT 50`; ở đây `LIMIT ?` được bind riêng.
- `ResultSet` có thể fetch page bổ sung; production cần kiểm soát tổng row và thời gian xử lý.

### 9.4. Chèn UUID v1 bằng PreparedStatement

```java
PreparedStatement insert = session.prepare("""
    INSERT INTO sdc_time_lab.feed_by_source_day
    (source_id, ingest_day, ingest_id, event_at, payload)
    VALUES (?, ?, ?, ?, ?)
    """);

IngestKeyFactory.IngestKey key = new IngestKeyFactory().newKey();

session.execute(insert.bind(
    sourceId,
    key.ingestDay(),
    key.ingestId(),
    eventAt,
    payload
));
```

Đây là ví dụ ghép với `FeedRangeDao` và `IngestKeyFactory` trong một service thực. `sourceId`, `eventAt`, `payload` phải được xác thực/khởi tạo từ request. Khi retry **cùng event logic**, hãy giữ `ingestId` ổn định nếu contract là một event một row — không gọi `newKey()` lại vô điều kiện mỗi lần retry.

## 10. Ánh xạ Spring Data Cassandra cho timestamp

### 10.1. Composite primary key theo event time

`MeasurementKey.java`:

```java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class MeasurementKey implements Serializable {

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "bucket_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private LocalDate bucketDay;

    @PrimaryKeyColumn(
        name = "event_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant eventAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING
    )
    private UUID eventId;

    public MeasurementKey() {}

    public MeasurementKey(
        UUID deviceId, LocalDate bucketDay,
        Instant eventAt, UUID eventId
    ) {
        this.deviceId = deviceId;
        this.bucketDay = bucketDay;
        this.eventAt = eventAt;
        this.eventId = eventId;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public LocalDate getBucketDay() { return bucketDay; }
    public void setBucketDay(LocalDate value) { bucketDay = value; }

    public Instant getEventAt() { return eventAt; }
    public void setEventAt(Instant value) { eventAt = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof MeasurementKey other)) return false;
        return Objects.equals(deviceId, other.deviceId)
            && Objects.equals(bucketDay, other.bucketDay)
            && Objects.equals(eventAt, other.eventAt)
            && Objects.equals(eventId, other.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, bucketDay, eventAt, eventId);
    }
}
```

Annotation `ordering = Ordering.DESCENDING` và `Ordering.ASCENDING` thể hiện thứ tự clustering đã định nghĩa trong schema. **Không đặt ordering để đổi schema production đã tồn tại**: schema CQL và entity mapping phải khớp nhau, migration bảng Cassandra có giới hạn thay đổi primary key.

### 10.2. Entity ánh xạ đúng bảng

```java
import java.time.Instant;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("measurements_by_device_day")
public class Measurement {

    @PrimaryKey
    private MeasurementKey key;

    @Column("temperature_c")
    private Double temperatureC;

    @Column("received_at")
    private Instant receivedAt;

    public Measurement() {}

    public Measurement(
        MeasurementKey key, Double temperatureC, Instant receivedAt
    ) {
        this.key = key;
        this.temperatureC = temperatureC;
        this.receivedAt = receivedAt;
    }

    public MeasurementKey getKey() { return key; }
    public void setKey(MeasurementKey value) { key = value; }

    public Double getTemperatureC() { return temperatureC; }
    public void setTemperatureC(Double value) { temperatureC = value; }

    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant value) { receivedAt = value; }
}
```

Với entity này:

- `key.eventAt` map thành CQL `event_at timestamp` → Java `Instant`.
- `key.eventId` map thành CQL `event_id uuid` → Java `UUID` (có thể UUID v4).
- `key.bucketDay` map thành CQL `date` → `LocalDate`.
- `receivedAt` chỉ là regular column; **không quyết định clustering order**.

### 10.3. Cấp key đúng từ event time

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public Measurement toEntity(
    UUID deviceId, UUID stableEventId,
    Instant eventAt, double temperatureC, Instant receivedAt
) {
    // Thống nhất độ phân giải CQL timestamp là millisecond.
    Instant normalized = Instant.ofEpochMilli(
        eventAt.toEpochMilli()
    );

    LocalDate bucket = LocalDate.ofInstant(
        normalized, ZoneOffset.UTC
    );

    MeasurementKey key = new MeasurementKey(
        deviceId, bucket, normalized, stableEventId
    );

    return new Measurement(key, temperatureC, receivedAt);
}
```

Chọn `stableEventId` từ nguồn nếu event đã có ID. Nếu tạo UUID mới **mỗi retry**, một sự kiện logic có thể tạo nhiều row do primary key chứa `event_id`. Nếu không có event ID, cần thiết kế idempotency (ví dụ fingerprint theo nguồn, sequence, event time và payload) phù hợp collision/duplicate policy.

### 10.4. Repository đọc theo CQL có giới hạn

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface MeasurementRepository
        extends CassandraRepository<Measurement, MeasurementKey> {

    @Query("""
        SELECT *
        FROM measurements_by_device_day
        WHERE device_id = ?0
          AND bucket_day = ?1
          AND event_at >= ?2
          AND event_at < ?3
        LIMIT ?4
        """)
    List<Measurement> findEventWindow(
        UUID deviceId,
        LocalDate bucketDay,
        Instant startInclusive,
        Instant endExclusive,
        int limit
    );
}
```

`@Query` ở đây chỉ dùng CQL với bind markers theo thứ tự, không tự tạo query scan đa partition. `LIMIT` giới hạn row, nhưng **không thay thế partition key**. Với nhu cầu đọc hàng triệu row, không materialize tất cả trong `List`; sử dụng paging/streaming có quản lý và đo kích thước partition.

**Quan trọng:** trong Cassandra, `@Query`/entity mapping không khiến `LIMIT 100` có tính “top 100 event toàn bảng” — đây là **100 row trong một partition theo clustering order**.

### 10.5. Khi cần CassandraTemplate

`CassandraTemplate` cung cấp entity mapping và query DSL. Một đoạn minh họa CQL query theo composite partition key có thể dùng `CqlTemplate` thông qua hạ tầng Spring hoặc Java driver:

```java
PreparedStatement p = session.prepare("""
    SELECT event_at, event_id, temperature_c
    FROM sdc_time_lab.measurements_by_device_day
    WHERE device_id = ? AND bucket_day = ?
      AND event_at >= ? AND event_at < ?
    LIMIT ?
    """);

ResultSet rows = session.execute(
    p.bind(deviceId, bucketDay, start, end, 100)
);
```

Khi cần map đầy đủ entity với `@PrimaryKeyClass`, dùng `MeasurementRepository`/`CassandraTemplate`; khi chỉ cần vài cột, prepared CQL thấp tầng có thể đơn giản hơn. `session`, `deviceId`, `bucketDay`, `start`, `end` là biến trong scope service đã được xác thực/khởi tạo.

## 11. Ánh xạ Spring Data Cassandra cho timeuuid

### 11.1. UUID Java cho cột timeuuid

Spring Data/Java driver dùng Java **`UUID`** cho CQL `timeuuid`. Tuy nhiên **bản thân kiểu Java UUID không buộc nó là UUID v1**. Ứng dụng phải bảo đảm ID đưa vào cột `timeuuid` được tạo đúng phiên bản.

Ví dụ composite key:

```java
import java.io.Serializable;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class FeedKey implements Serializable {

    @PrimaryKeyColumn(
        name = "source_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID sourceId;

    @PrimaryKeyColumn(
        name = "ingest_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private LocalDate ingestDay;

    @PrimaryKeyColumn(
        name = "ingest_id", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private UUID ingestId;

    public FeedKey() {}

    public FeedKey(UUID sourceId, LocalDate day, UUID ingestId) {
        this.sourceId = sourceId;
        this.ingestDay = day;
        this.ingestId = ingestId;
    }

    public UUID getSourceId() { return sourceId; }
    public void setSourceId(UUID value) { sourceId = value; }

    public LocalDate getIngestDay() { return ingestDay; }
    public void setIngestDay(LocalDate value) { ingestDay = value; }

    public UUID getIngestId() { return ingestId; }
    public void setIngestId(UUID value) { ingestId = value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof FeedKey other)) return false;
        return Objects.equals(sourceId, other.sourceId)
            && Objects.equals(ingestDay, other.ingestDay)
            && Objects.equals(ingestId, other.ingestId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(sourceId, ingestDay, ingestId);
    }
}
```

Mapping `UUID` này tương ứng cột CQL **`ingest_id timeuuid`**, không tự chuyển thành UUID v1 nếu setter nhận UUID v4.

### 11.2. Entity timeuuid

```java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("feed_by_source_day")
public class FeedEntry {

    @PrimaryKey
    private FeedKey key;

    @Column("event_at")
    private Instant eventAt;

    @Column("payload")
    private String payload;

    public FeedEntry() {}

    public FeedEntry(
        FeedKey key, Instant eventAt, String payload
    ) {
        this.key = key;
        this.eventAt = eventAt;
        this.payload = payload;
    }

    public FeedKey getKey() { return key; }
    public void setKey(FeedKey value) { key = value; }

    public Instant getEventAt() { return eventAt; }
    public void setEventAt(Instant value) { eventAt = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
```

### 11.3. Dịch vụ ghi feed bảo toàn khóa qua retry

```java
import com.datastax.oss.driver.api.core.uuid.Uuids;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public class FeedEntryFactory {

    public FeedEntry newEntry(
        UUID sourceId, Instant sourceEventAt, String payload
    ) {
        UUID ingestId = Uuids.timeBased();
        long ingestMillis = Uuids.unixTimestamp(ingestId);

        LocalDate bucketDay = LocalDate.ofInstant(
            Instant.ofEpochMilli(ingestMillis), ZoneOffset.UTC
        );

        return new FeedEntry(
            new FeedKey(sourceId, bucketDay, ingestId),
            sourceEventAt,
            payload
        );
    }
}
```

Sau khi tạo entity, **giữ nguyên `FeedKey`** trong retry/queue nếu mục tiêu là một event logic một row. Không tạo lại `ingestId` trong mỗi attempt.

Có thể dùng repository:

```java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface FeedEntryRepository
        extends CassandraRepository<FeedEntry, FeedKey> {
}
```

Khi gọi `repository.save(entry)`, mapping gửi cùng UUID v1 trong composite key. `save` là write theo semantics Cassandra, **không phải “create exactly once”** nếu không có điều kiện/idempotency business.

## 12. Nếu cần bảo đảm thứ tự tuyệt đối: sequence, không phải clock

Đây là phần quan trọng nhất khi yêu cầu dùng từ “**bảo đảm**”.

### 12.1. Ba bảo đảm khác nhau

| Bảo đảm | `timestamp` + UUID | `timeuuid` | Sequence có nguồn đáng tin |
|---|---|---|---|
| Có thứ tự **deterministic** trong partition | Có, theo timestamp và UUID tie-break | Có, theo comparator timeuuid | Có, theo sequence |
| Thứ tự phản ánh **event time do nguồn cung cấp** | Có theo **giá trị source** (nếu nguồn đúng) | Không nếu sinh lúc ingest | Chỉ nếu nguồn sequence được cấp theo event order |
| Không ghi đè hai event trùng millisecond | Có, nếu ID khác | Thường có, với ID duy nhất hợp lệ | Có, nếu sequence duy nhất |
| Thứ tự **đúng thực tế qua nhiều clock lệch** | Không tự bảo đảm | Không tự bảo đảm | Có thể, nếu hệ cấp thứ tự có contract phù hợp |
| Có thứ tự **toàn cluster/mọi partition** | Không do CQL ORDER BY | Không do CQL ORDER BY | Có thể cần service/merge/transaction riêng |
| Replay cùng event tạo đúng một row | Chỉ nếu giữ ID ổn định | Chỉ nếu giữ timeuuid ổn định | Chỉ nếu giữ sequence/ID ổn định |

**Deterministic ordering** nghĩa là cùng tập row và cùng comparator thì thứ tự ổn định. Nó **không đồng nghĩa** causal ordering, happens-before, hay thứ tự commit của mọi service.

### 12.2. Ví dụ sequence trong một stream

Một stream có single writer hoặc dịch vụ cấp số thứ tự đáng tin:

```text
event A -> sequence = 101
event B -> sequence = 102
event C -> sequence = 103
```

Có thể lưu:

```sql
CREATE TABLE IF NOT EXISTS sdc_time_lab.events_by_stream_bucket (
    stream_id uuid,
    bucket_id int,
    sequence bigint,
    event_id uuid,
    event_at timestamp,
    payload text,
    PRIMARY KEY ((stream_id, bucket_id), sequence)
) WITH CLUSTERING ORDER BY (sequence ASC);
```

**Điều kiện quan trọng:** CQL schema **không tự cấp phát hoặc khóa sequence**. Ứng dụng phải bảo đảm:

- Một nguồn thực sự phát sequence tăng theo thứ tự mong muốn.
- Không có hai writer cấp cùng sequence cho hai event khác nhau.
- Xử lý crash/retry/replay và phát hiện sequence bị thiếu.
- Khi chia bucket, định nghĩa thứ tự giữa các bucket.
- Nếu dùng CAS/LWT để cấp số, chấp nhận chi phí và ràng buộc một aggregate/partition.

Không dùng `System.currentTimeMillis()` như một sequence thay thế, và không cộng một biến `AtomicLong` ở từng JVM rồi coi là sequence toàn cluster.

### 12.3. Khi có nhiều writer

Nếu hai JVM có thể ghi cùng stream, lựa chọn an toàn tùy yêu cầu:

1. **Single writer per stream/partition** theo một cơ chế ownership rõ ràng.
2. **Sequencer service** cấp số tăng và durable.
3. **Compare-and-set/LWT** trên trạng thái version nếu thực sự cần chặn stale writer.
4. **Event log có thứ tự được định nghĩa** (ví dụ thứ tự trong một phân vùng Kafka), rồi ghi Cassandra giữ sequence từ nguồn.
5. Khi không cần thứ tự tuyệt đối, chấp nhận **event-time order + tie-breaker** và xử lý late events.

Chỉ gắn `timeuuid` không thay thế được bất kỳ điều kiện cấp thứ tự nào ở trên.

### 12.4. “Cần bảo đảm” còn phải nói rõ phạm vi

Một hệ thống có thể bảo đảm **per-device** order nhưng không bảo đảm **global** order trên tất cả thiết bị; nhiều khi đó là lựa chọn hợp lý nhất. Nên viết contract rõ, ví dụ:

> Các phép đo của từng thiết bị được sắp theo `event_at` mà thiết bị báo cáo; khi timestamp trùng, `event_id` xác định thứ tự ổn định nhưng không thể suy ra thứ tự vật lý. Event đến muộn có thể xuất hiện ở trang cũ.

Hoặc:

> Các sự kiện của mỗi `stream_id` có `sequence` tăng đơn điệu do một sequencer cấp; API hiển thị theo sequence, không theo đồng hồ máy.

Đây là contract có thể test, monitor và giải thích được cho người sử dụng.

## 13. Time bucket: giữ partition có kích thước kiểm soát được

### 13.1. Vì sao cần bucket?

Bảng có partition chỉ theo `device_id` có thể tích lũy hàng trăm triệu row của một thiết bị. Partition quá rộng làm tăng chi phí đọc, compaction, repair và paging; một số thao tác timeout ngay cả khi query chỉ cần vài row.

Một mô hình thường dùng:

```text
partition key = (device_id, bucket_day)
clustering    = event_at DESC, event_id ASC
```

hoặc:

```text
partition key = (source_id, ingest_day)
clustering    = ingest_id DESC
```

Bucket theo ngày là **ví dụ**, không phải chuẩn bắt buộc; có workload cần bucket theo giờ, tuần hoặc ngày + shard.

### 13.2. Chọn bucket từ đúng trục thời gian

- Bảng `measurements_by_device_day` sắp theo **event time**: lấy `bucket_day` từ `event_at`.
- Bảng `feed_by_source_day` sắp theo **ingest time/timeuuid`: lấy `ingest_day` từ thành phần thời gian của timeuuid hoặc clock ingest nhất quán.
- Nếu copy dữ liệu từ nguồn cũ, định nghĩa chính sách **backfill** trước; đừng gán bucket current day nhưng sắp theo event_at lịch sử rồi kỳ vọng query 24/11 truy ra nó.

### 13.3. Bucket quá lớn và quá nhỏ

| Bucket | Ưu điểm | Rủi ro |
|---|---|---|
| Theo **giờ** | Partition nhỏ, dọn TTL dễ hơn | Query 24 giờ cần nhiều partition hơn |
| Theo **ngày** | Cân bằng cho nhiều use case | Thiết bị tần suất cao vẫn có partition lớn |
| Theo **tháng** | Ít partition cho query dài ngày | Dễ thành wide partition |
| Theo ngày + **shard** | Giảm hot partition khi ghi rất cao | Đọc phải fan-out nhiều shard và merge |

Đánh giá bằng **số row/partition, kích thước bytes/partition, p95/p99 và pattern query**, không chọn “một ngày” vì nó dễ code.

### 13.4. Query xuyên midnight

Nếu cần dữ liệu từ 23:55 ngày 24/11 đến 00:05 ngày 25/11, hai partition có thể được đọc:

```text
(device_id, 2026-11-24) -> event_at >= 23:55
(device_id, 2026-11-25) -> event_at < 00:05
```

Sau đó ghép hai kết quả theo comparator **(event_at DESC, event_id ASC)**. Không viết một CQL `ORDER BY event_at` rồi kỳ vọng Cassandra kết hợp đa partition thành thứ tự toàn cục.

**Với nhiều thiết bị**, số partition cần đọc còn tăng; có thể cần read model khác cho dashboard toàn bộ fleet.

## 14. Paging, cursor và thứ tự ổn định

### 14.1. LIMIT khác fetch size

```sql
SELECT event_at, event_id, temperature_c
FROM sdc_time_lab.measurements_by_device_day
WHERE device_id = 33333333-3333-4333-8333-333333333333
  AND bucket_day = '2026-11-25'
LIMIT 50;
```

`LIMIT 50` giới hạn tổng row của query này; page size/fetch size của Java driver chỉ điều chỉnh lượng row mục tiêu trên mỗi lượt fetch. `LIMIT` không bảo đảm một snapshot bất biến khi dữ liệu thay đổi giữa các lượt truy vấn/phân trang.

### 14.2. Cursor phải chứa đủ khóa thứ tự

Với timestamp + UUID, chỉ lưu:

```text
cursor = event_at
```

là **không đủ** nếu có hai event trùng millisecond. Chuyển sang trang tiếp theo chỉ bằng `event_at < lastEventAt` có thể **bỏ sót** event cùng timestamp mà chưa xuất hiện trên trang trước.

Cursor logic cần gồm:

```text
(device_id, bucket_day, event_at, event_id)
```

đồng thời phải hiểu đúng **mixed clustering order DESC/ASC** để chọn predicate tuple/cách tiếp trang. Nếu không kiểm chứng predicate keyset với schema/order của Cassandra version thực tế, hãy dùng **driver paging state** cùng query và bind values ổn định.

### 14.3. Timeuuid có cursor tự nhiên hơn trong một bucket

Với `ingest_id timeuuid DESC`, một cursor đơn là **timeuuid cuối trang** có thể dùng để đọc các row “cũ hơn”:

```sql
SELECT ingest_id, payload
FROM sdc_time_lab.feed_by_source_day
WHERE source_id = 22222222-2222-4222-8222-222222222222
  AND ingest_day = '2026-11-25'
  AND ingest_id < 8d6b24e0-9e2c-11f1-8d70-0242ac120002
LIMIT 20;
```

UUID trong ví dụ là một literal định dạng v1 dùng để minh họa **cursor được trả từ trang trước**. Trong ứng dụng thật, cursor phải là **ID thực của row cuối cùng**; không tự đoán hay chế literal. Nếu timeuuid được tạo không đúng thời gian/thiết bị, thứ tự vẫn là comparator của UUID, không tự sửa clock skew.

Không coi `min_timeuuid(time)` là **cursor chính xác của một row**: nó chỉ là sentinel theo millisecond. Dùng ID đầy đủ để tiếp sau **chính row đó** và tránh skip/duplicate trong trường hợp nhiều event cùng millisecond.

### 14.4. Paging state không phải snapshot

Driver Cassandra có paging state opaque để tiếp tục **cùng query, cùng tham số, cùng cấu hình phù hợp**. Nó không phải transaction snapshot dài hạn. Trong thời gian lấy các page:

- Event đến muộn có thể được chèn vào giữa các clustering keys.
- Một số row bị xóa hoặc TTL hết hạn.
- Retry/ingest có thể tạo row mới.
- Khi đổi bucket hoặc filter, paging state cũ không còn hợp lệ.

Nếu frontend cần “một báo cáo bất biến cho một phiên export”, hãy thiết kế **watermark/cutoff**, dataset snapshot/export riêng hoặc nguồn dữ liệu có semantics phù hợp; không ép Cassandra pagination thành snapshot ACID.

### 14.5. Thứ tự ổn định khác dữ liệu không đổi

Một cursor có đủ khóa giúp tránh lỗi tie-breaking của **tập row cố định**. Nó không ngăn concurrent insert/delete. Phải mô tả cho client:

- “Trang được sắp theo thứ tự deterministic tại thời điểm query.”
- “Dữ liệu mới có thể xuất hiện khi refresh.”
- “Event đến muộn có thể được chèn vào trang cũ.”
- “Trang không phải snapshot lịch sử cố định.”

## 15. Chất lượng thời gian: clock skew, out-of-order và retry

### 15.1. Đồng hồ lệch giữa sensor/service

Sensor A chạy nhanh 30 giây, sensor B chạy đúng giờ. Khi query theo `event_at`, dữ liệu sensor A có thể trông như “đến từ tương lai”.

Tương tự, hai server sinh timeuuid có clock lệch; thứ tự `ingest_id DESC` có thể khác thứ tự Kafka/HTTP request thực tế. **Không có kiểu cột Cassandra nào tự sửa đồng hồ sai**.

Biện pháp:

1. Đồng bộ clock NTP/chrony cho các host kiểm soát được.
2. Ghi và quan sát cả **`event_at` và `received_at`**.
3. Theo dõi drift, late arrival và event time bất hợp lệ.
4. Có **watermark** cho stream processing nếu cho phép late events.
5. Với invariant thứ tự nghiêm ngặt, dùng sequence/CAS chứ không dựa vào clock.

### 15.2. Retry và duplicate IDs

Với schema `timestamp + UUID`:

```text
retry event A với cùng event_id -> cùng primary key (nếu event_at/bucket giữ nguyên)
retry event A với event_id mới -> thêm một row
```

Với schema `timeuuid`:

```text
retry cùng ingest_id -> cùng primary key
retry bằng Uuids.timeBased() mới -> row mới
```

Không chỉ cần “UUID unique”: **nếu bài toán yêu cầu idempotent ingest, UUID phải ổn định theo event logic**. Thêm `IF NOT EXISTS` có thể ngăn trùng key khi tất cả attempts dùng **cùng key**, nhưng không loại bỏ duplicate có key khác.

### 15.3. Khi nào một event bị ghi đè?

Cassandra xét **tất cả thành phần primary key**. Nếu hai mutation cùng partition key và clustering columns, chúng là cùng row và chịu semantics last-write-wins/tombstone cho các cell.

- `timestamp` chỉ một clustering key: dễ collision trong cùng ms.
- `timestamp + event_id`: collision chỉ nếu cả timestamp và ID trùng.
- `timeuuid`: collision nếu cùng ID (cần generator đúng và key policy).
- `sequence`: collision nếu hai event được cấp cùng sequence.

Trong tất cả trường hợp, bảo vệ uniqueness ở mức business vẫn cần thiết khi nguồn không đáng tin hoặc nhiều writer.

### 15.4. Write timestamp và TTL không quyết định clustering order

`USING TIMESTAMP` của CQL dùng **write timestamp microsecond** để giải quyết phiên bản cell; **không làm đổi vị trí row** theo clustering `event_at` hoặc `ingest_id` đã nằm trong primary key.

`USING TTL 3600` quyết định **giá trị sống bao lâu**, không tạo thứ tự đọc mới. Khi row hết TTL, query có thể không còn trả row dù sorting key vẫn tồn tại trong SSTable/tombstone cho tới compaction.

**Không dùng `WRITETIME(payload)` như event sequence.** Nó là metadata write của regular column, không phải bằng chứng nghiệp vụ thứ tự gửi/nhận toàn cluster.

## 16. Giới hạn hiệu năng khi dùng time-series

### 16.1. Partition quá rộng

Một thiết bị ghi 100.000 event/giờ vào bucket ngày có thể tạo hàng triệu row/ngày. Nếu query thường chỉ đọc 5 phút mới nhất, bucket theo giờ hoặc strategy khác có thể hợp lý hơn.

Đo:

- Row count/estimated row size theo partition.
- Latency p95/p99 của query `LIMIT 50` và range.
- Số partition/bucket bị fan-out trong một API request.
- SSTable count, compaction và tombstone.
- Query có phải đọc từ clustering mới nhất theo hướng mong muốn?
- Có event ID collision/retry/backfill bất thường không?

### 16.2. Comparator không thay dữ liệu vật lý

`CLUSTERING ORDER BY` giúp lưu/đọc trong partition theo thứ tự clustering hiệu quả. Nó không tạo **global secondary ordering index** và không giải quyết query theo non-key columns. Query “tất cả event có temperature > 50 trên mọi device” là **một access pattern khác**; cần read model/index phù hợp, không thêm `ALLOW FILTERING` mù quáng.

### 16.3. TTL và compaction cho dữ liệu theo thời gian

Với dữ liệu telemetry có retention, TTL/TWCS có thể hữu ích. Nhưng:

- TTL tạo tombstone sau khi hết hạn.
- Backfill/write vào partition cũ có thể ảnh hưởng compaction.
- Trộn TTL dài/ngắn và dữ liệu không TTL làm khó thu hồi SSTable.
- `gc_grace_seconds` liên quan an toàn repair, không kéo dài dữ liệu đọc được.
- Không chọn TWCS chỉ vì bảng có cột `timestamp`; phải đánh giá **đường ghi, late writes và retention**.

Lựa chọn kiểu clustering và chính sách TTL/compaction là **hai quyết định liên quan nhưng riêng biệt**.

## 17. Tình huống thiết kế và bài tập phân tích

### 17.1. Sensor thu dữ liệu với thời gian từ thiết bị

**Đề bài:** Sensor có timestamp từ thiết bị, có thể gửi trễ và có nhiều phép đo trong một mili-giây. API phải hiển thị đúng theo timestamp của sensor.

**Đề xuất:** `PRIMARY KEY ((device_id, bucket_day), event_at, event_id)`, `event_at timestamp DESC`, `event_id uuid ASC`. Bucket theo UTC ngày event. Để giữ **thứ tự vật lý giữa các event có cùng timestamp**, nguồn còn phải cung cấp sequence; UUID chỉ giúp ổn định tie-break.

### 17.2. Audit feed theo thời gian nhận tại API

**Đề bài:** Yêu cầu “hiển thị bản ghi mà hệ thống vừa nhận gần đây trước” và giữ ID để tiếp trang.

**Đề xuất:** `PRIMARY KEY ((source_id, ingest_day), ingest_id)`, `ingest_id timeuuid DESC`. Tạo `Uuids.timeBased()` tại ingestion service hoặc `now()` của Cassandra, chọn **một chính sách nhất quán** và giữ key qua retry.

**Giới hạn:** Clock skew giữa các service/coordinator, không có thứ tự global và không có đảm bảo event source order.

### 17.3. Event stream cần strict per-stream order

**Đề bài:** Nếu Kafka stream đảm bảo mỗi partition phát event có offset tăng, consumer muốn Cassandra đọc theo đúng offset.

**Đề xuất:** Lưu **offset/sequence bigint** làm clustering key hoặc một phần khóa. Giữ mapping stream→partition phù hợp. Không chuyển offset sang timeuuid rồi mất tính chất thứ tự authoritative.

### 17.4. Dashboard tổng hợp nhiều thiết bị

**Đề bài:** “Hiển thị 100 event mới nhất của toàn bộ 10.000 thiết bị”.

**Không phù hợp:** Truy vấn một bảng partition theo device rồi `ORDER BY event_at DESC LIMIT 100` mà thiếu partition key.

**Đề xuất:** Read model theo group/time bucket, fan-out có giới hạn và merge, hoặc một pipeline tổng hợp riêng. Cần cân nhắc hot partition, shard và fan-out. Cột timeuuid không tự làm điều này thành global order.

### 17.5. Hệ thống có dữ liệu từ tương lai

**Đề bài:** Một số sensor gửi timestamp năm 2099 do clock lỗi. Query `event_at DESC` luôn hiện chúng ở đầu dashboard.

**Đề xuất:** Validate event time so với nhận, quarantine event vượt ngưỡng, phân biệt event/ingest time và không rewrite lịch sử tùy tiện. Timeuuid tạo ở ingest có thể tránh lỗi display-order theo sensor clock, nhưng nếu nghiệp vụ cần event time vẫn phải lưu và xử lý separately.

## 18. Integration test: hai event cùng millisecond không được mất

### 18.1. Spring Data repository test

Ví dụ với `MeasurementRepository` và entity ở mục 10:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MeasurementOrderingIT {

    @Autowired
    MeasurementRepository repository;

    @Test
    void shouldKeepTwoEventsWithinSameMillisecond() {
        UUID deviceId = UUID.randomUUID();

        Instant at = Instant.parse("2026-11-25T09:00:00.123Z");
        LocalDate day = LocalDate.ofInstant(at, ZoneOffset.UTC);

        Measurement first = new Measurement(
            new MeasurementKey(deviceId, day, at, UUID.randomUUID()),
            24.5, Instant.now()
        );
        Measurement second = new Measurement(
            new MeasurementKey(deviceId, day, at, UUID.randomUUID()),
            24.6, Instant.now()
        );

        repository.save(first);
        repository.save(second);

        List<Measurement> rows = repository.findEventWindow(
            deviceId,
            day,
            Instant.parse("2026-11-25T09:00:00Z"),
            Instant.parse("2026-11-25T09:01:00Z"),
            100
        );

        assertThat(rows).hasSize(2);
        assertThat(rows)
            .extracting(m -> m.getKey().getEventAt())
            .containsOnly(at);

        assertThat(rows)
            .extracting(m -> m.getKey().getEventId())
            .containsExactlyInAnyOrder(
                first.getKey().getEventId(),
                second.getKey().getEventId()
            );
    }
}
```

Điều kiện: Cassandra test cluster đã tạo keyspace/bảng trước, Spring Boot trỏ đúng keyspace, và không có writer khác cùng UUID device. `@SpringBootTest` không tự khởi động Cassandra; dùng Testcontainers hoặc cluster test riêng nếu cần.

### 18.2. Test DESC khi timestamp khác nhau

```java
Instant older = Instant.parse("2026-11-25T09:00:00Z");
Instant newer = Instant.parse("2026-11-25T09:00:01Z");

// Insert hai row (cùng device/day) với UUID khác nhau.
// Đọc findEventWindow(...) -> assert eventAt[0] == newer,
// eventAt[1] == older nếu không có row khác.
```

Đây là khung test; phải tạo entity, save và dùng UUID mới như mục 18.1. Test nên khẳng định **thứ tự do Cassandra clustering trả về**, không tự sort list trong Java trước assert.

### 18.3. Test timeuuid đúng kiểu và gần thời điểm tạo

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.uuid.Uuids;

@Test
void shouldGenerateTimeBasedUuid() {
    Instant before = Instant.now();
    UUID id = Uuids.timeBased();
    Instant embedded = Instant.ofEpochMilli(
        Uuids.unixTimestamp(id)
    );
    Instant after = Instant.now();

    assertThat(id.version()).isEqualTo(1);
    assertThat(embedded).isBetween(
        before.minusSeconds(2),
        after.plusSeconds(2)
    );
}
```

Test dùng **khoảng dung sai**, vì thời gian đo đồng hồ và scheduler có thể thay đổi. Nó chỉ kiểm tra UUID v1 vừa được tạo trong **một JVM**, **không chứng minh strict ordering giữa nhiều host**.

### 18.4. Test range boundary

Tạo các ID bằng `Uuids.timeBased()`, ghi vào bảng test và lưu lại `Uuids.unixTimestamp(id)`. Với mỗi cửa sổ millisecond `[start,end)`, xác minh mọi UUID có embedded millis trong khoảng được SELECT trả về, còn các ID ngoài khoảng không xuất hiện.

**Không** dùng `Uuids.startOf(...)` làm ID của row test, vì đó là **fake UUID boundary**. Và nếu test tự tạo UUID bằng `timeBased()` vào các thời điểm quá gần, hãy kiểm soát đồng hồ/độ phân giải thay vì dựa vào `Thread.sleep(1)` để khẳng định thứ tự tuyệt đối.

### 18.5. Test không thể chứng minh điều gì?

Một test chỉ chạy trong một JVM/một node có thể chứng minh mapping, CQL, sorting và range filter. Nó **không chứng minh** clock skew không tồn tại giữa nhiều writer/coordinator, không chứng minh global sequence, và không chứng minh pagination có snapshot khi dữ liệu liên tục thay đổi.

Để đánh giá yêu cầu mạnh, cần fault injection, nhiều writer, time-skew simulation và hợp đồng hệ thống về thứ tự.

## 19. Troubleshooting: dữ liệu “không theo thứ tự”

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Event mới nhận bị xếp trước event xảy ra trước đó | Dùng `timeuuid` ingest order thay vì `event_at` | Chọn đúng trục thời gian và read model |
| Hai event cùng millisecond chỉ còn một row | PK chỉ có `timestamp`, thiếu tie-breaker | Thêm `event_id` vào clustering key qua bảng mới/migration |
| `UUID.randomUUID()` ghi vào `timeuuid` bị từ chối | UUID v4 không hợp lệ cho CQL timeuuid | Dùng `Uuids.timeBased()` hoặc CQL `now()` |
| Sắp client khác thứ tự Cassandra | Dùng `UUID.compareTo` cho timeuuid | Dùng comparator tương thích với CQL timeuuid hoặc giữ thứ tự query server |
| Query `WHERE ingest_id = now()` không thấy row | `now()` tạo UUID mới mỗi lần | Lưu ID đã tạo và bind ID thật |
| Query range bỏ sót event đúng biên `start` | Dùng `max_timeuuid(start)` sai | Dùng `>= min_timeuuid(start)` cho inclusive start |
| Query range trả quá nhiều/ít ở cuối | Nhầm inclusive/exclusive boundary | Chuẩn hóa `[start, end)`, test millisecond |
| Backfill xuất hiện ở ngày không mong muốn | Bucket theo ingest day nhưng query event time | Tách event-time và ingest-time model |
| `ORDER BY` bị từ chối | Không đủ partition key hoặc order không khớp clustering | Thiết kế PK/CLUSTERING ORDER đúng query |
| Có dữ liệu “tương lai” | Clock sensor/server skew | Kiểm tra NTP, event validation, watermark |
| Retry tạo nhiều row cho một event | Sinh UUID mới ở mỗi attempt | Giữ event ID/timeuuid ổn định |
| Phân trang bỏ sót event trùng millisecond | Cursor chỉ có timestamp, thiếu UUID | Dùng full clustering key/paging state đúng query |
| ORDER BY giữa nhiều ngày không đúng toàn cục | Mỗi bucket là partition riêng | Merge read results hoặc read model khác |
| `Uuids.startOf(uuid.timestamp())` cho biên sai | `UUID.timestamp()` dùng 100 ns từ năm 1582 | Dùng `Uuids.unixTimestamp(uuid)` hoặc epoch millis |
| `WRITETIME(payload)` không trùng `event_at` | Write metadata khác thời gian event | Không dùng WRITETIME làm business event time |
| CQL timestamp mất phần nano | Kiểu timestamp có precision millisecond | Normalize precision, lưu dữ liệu khác nếu cần |
| Partition quá lớn dù query LIMIT nhỏ | Bucket size chưa phù hợp | Chỉnh bucket/shard theo workload và benchmark |
| `CLUSTERING ORDER BY` trong mapping khác schema | Annotations không tự migrate PK | Tạo bảng mới/migration và backfill |

### 19.1. Checklist điều tra

1. Nêu rõ phải sắp theo **event time, ingest time hay sequence**.
2. Đọc CQL `CREATE TABLE` và xác định **partition key + clustering order**.
3. Xác nhận query `WHERE` có đủ partition key và range đúng clustering column.
4. Kiểm tra **milli-/micro-/nano-second**; CQL `timestamp` không giữ nanosecond.
5. Nếu `timeuuid`, kiểm tra `uuid.version() == 1`, nguồn tạo và clock.
6. Đối chiếu event ID/tie-breaker khi hai event cùng millisecond.
7. Xác minh bucket được tính từ **đúng nguồn thời gian**.
8. Xem page size, `LIMIT`, cursor và query có đổi giữa các page không.
9. Kiểm tra late events, replay/retry và key idempotency.
10. Nếu cần strict order, kiểm tra **sequencer/single writer/CAS**, không chỉ timestamp.
11. Đo partition size, p95/p99, compaction, TTL/tombstone và các query fan-out.
12. Bổ sung integration test một partition và multi-writer tests nếu cần.

## 20. Bài tập thực hành

### Bài 1 — Nhận diện timestamp collision

Một bảng có:

```sql
PRIMARY KEY ((device_id, bucket_day), event_at)
```

Hai event khác nhau từ cùng thiết bị có `event_at='2026-11-25T09:00:00.123Z'`.

**Câu hỏi:** Có hai row hay một row? Sửa schema như thế nào?

**Đáp án:** Cùng primary key nên là **một row logic**, không an toàn cho hai event. Thêm clustering key `event_id uuid` để phân biệt.

### Bài 2 — Chọn trục thời gian

Một sự kiện được sensor đo lúc 09:00 nhưng service chỉ nhận lúc 09:10.

**Câu hỏi:** Nếu dashboard hiển thị timeline theo lúc đo, dùng `event_at timestamp` hay `ingest_id timeuuid` làm clustering chính?

**Đáp án:** `event_at timestamp`, thêm event ID làm tie-breaker. Giữ ingest time riêng để biết độ trễ.

### Bài 3 — UUID v4 có phù hợp timeuuid không?

```java
UUID id = UUID.randomUUID();
```

**Đáp án:** Không. Java tạo UUID v4, trong khi CQL timeuuid yêu cầu UUID v1. Dùng `Uuids.timeBased()`.

### Bài 4 — timeuuid và strict order

Hai service A và B có clock lệch nhau 30 giây; cả hai tạo `Uuids.timeBased()`.

**Câu hỏi:** ID nào lớn hơn có nhất thiết được Cassandra ghi cuối cùng không?

**Đáp án:** Không. Comparator theo timestamp nhúng trong UUID, không có global sequence và clock có thể lệch.

### Bài 5 — Inclusive start

Muốn lấy các timeuuid từ đúng 08:00:00.000 UTC và trước 09:00:00.000 UTC.

**Đáp án:** Dùng `ingest_id >= min_timeuuid(start) AND ingest_id < min_timeuuid(end)` với partition key đầy đủ.

### Bài 6 — Loại toàn bộ ms đầu

Muốn lấy **sau hẳn** toàn bộ UUID trong millisecond `08:00:00.000`.

**Đáp án:** Dùng `ingest_id > max_timeuuid('...08:00:00.000...')`.

### Bài 7 — Java epoch đúng

Vì sao `Uuids.startOf(uuid.timestamp())` sai?

**Đáp án:** `UUID.timestamp()` là tick 100 ns từ mốc 1582; `Uuids.startOf(long)` nhận Unix **millisecond**. Dùng `Uuids.unixTimestamp(uuid)`.

### Bài 8 — Cùng bucket hay khác bucket?

Hai event cùng device nhưng ngày UTC lần lượt 24/11 và 25/11. Query một partition của 25/11 có trả cả hai không?

**Đáp án:** Không. Chúng thuộc hai composite partition keys, cần truy vấn hai bucket và merge.

### Bài 9 — Cursor timestamp chỉ có ms

Một trang kết thúc ở `event_at=09:00:00.123Z`, còn ba event khác cùng timestamp chưa đọc.

**Câu hỏi:** Có nên dùng `WHERE event_at < '09:00:00.123Z'` cho trang sau?

**Đáp án:** Không; có thể bỏ sót event cùng mili-giây. Cursor phải chứa đủ clustering key hoặc dùng driver paging state với cùng query.

### Bài 10 — Idempotent retry

Một retry của cùng message tạo timeuuid mới nên có thêm row.

**Cách sửa:** Gán ID một lần cho event logic, giữ ID và bucket khi retry; nếu source có event ID đáng tin, dùng nó làm idempotency key.

### Bài 11 — Sequence authoritative

Một stream Kafka có offset 100, 101, 102. Thiết kế bảng đọc theo đúng offset bất kể host clock.

**Gợi ý:** `PRIMARY KEY ((stream_id, bucket_id), offset)` với `offset bigint`; cần định nghĩa nguồn offset, bucket và xử lý replay, không thay offset bằng timeuuid.

### Bài 12 — Test sorting

Tạo 3 event cùng device/day:
- Event A: 08:00:00.123
- Event B: 08:00:00.123
- Event C: 08:00:01.000

**Yêu cầu:** Dùng Spring Data repo để assert C đứng trước; A/B đều tồn tại, nhưng không khẳng định thứ tự vật lý giữa A và B nếu chỉ có UUID v4 tie-break.

### Bài 13 — Chọn bucketing

Thiết bị ghi 10.000 event/giây và retention 30 ngày; query chủ yếu lấy 15 phút mới nhất.

**Yêu cầu:** So sánh bucket theo ngày/giờ và option shard. Đo row/partition, hot partition và chi phí merge trước khi chọn.

### Bài 14 — Kết quả đọc toàn cục

API cần “100 event mới nhất từ 500 thiết bị”. Vì sao `ORDER BY event_at DESC LIMIT 100` không đủ với partition key theo device/day?

**Đáp án:** Cassandra sắp trong mỗi partition, không global across partitions. Cần read model phù hợp hoặc bounded fan-out và merge.

### Bài 15 — Timeuuid boundary và ngày

Nếu `Uuids.timeBased()` tạo ID lúc 00:00:00.001 UTC ngày 26/11 nhưng service dùng `LocalDate.now()` lấy ngày 25/11 do timezone khác, điều gì xảy ra?

**Đáp án:** Bucket key và thời gian UUID không đồng nhất. Chọn quy tắc UTC và tính bucket từ timestamp embedded trong UUID để thống nhất.

## 21. Câu hỏi tự kiểm tra

1. **CQL `timestamp` có độ phân giải nào?** Millisecond từ Unix epoch.
2. **CQL `timeuuid` nhận UUID phiên bản nào?** UUID v1.
3. **UUID v1 chứa thành phần thời gian theo đơn vị nào?** Tick 100 ns từ mốc 1582-10-15.
4. **Độ phân giải 100 ns bảo đảm clock chính xác 100 ns không?** Không.
5. **CQL write timestamp có phải cột `timestamp` không?** Không; write timestamp là metadata microsecond.
6. **Nếu có nhiều event cùng ms, chỉ dùng timestamp làm clustering key có an toàn không?** Không.
7. **Cách phổ biến để tránh collision trên timestamp?** Thêm stable `event_id` vào clustering key.
8. **UUID v4 tie-break có thể biểu diễn thứ tự thực tế giữa hai event cùng ms không?** Không.
9. **`now()` tạo kiểu nào?** Timeuuid UUID v1 trên coordinator.
10. **`Uuids.timeBased()` tạo kiểu nào?** UUID v1 trong JVM.
11. **Java `UUID.randomUUID()` có dùng được trong CQL timeuuid không?** Không, nó sinh UUID v4.
12. **`WHERE timeuuid = now()` có tìm row vừa ghi không?** Không, now() tạo UUID mới.
13. **`min_timeuuid` dùng cho INSERT không?** Không; chỉ dùng làm bound query.
14. **Khoảng nửa mở timeuuid dùng điều kiện nào?** `>= min_timeuuid(start) AND < min_timeuuid(end)`.
15. **`Uuids.startOf` nhận milliseconds hay UUID ticks?** Unix milliseconds.
16. **`Uuids.unixTimestamp(uuid)` trả gì?** Thời gian embedded trong UUID v1 theo Unix milliseconds.
17. **Có nên sort timeuuid bằng Java `UUID.compareTo` rồi coi như CQL order?** Không, comparator khác.
18. **`ORDER BY` có sắp dữ liệu toàn cluster không?** Không; giới hạn theo partition/clustering.
19. **`CLUSTERING ORDER BY (event_at DESC, event_id ASC)` nghĩa gì?** Mới nhất trước, trùng ms sắp deterministic theo UUID.
20. **Bucket theo event time hay ingest time?** Theo trục thời gian mà bảng/query được thiết kế.
21. **Paging state có đóng băng snapshot không?** Không.
22. **Cursor chỉ có timestamp có thể bỏ sót row không?** Có nếu nhiều event trùng timestamp.
23. **timeuuid có bảo đảm thứ tự Kafka offset không?** Không.
24. **Muốn strict per-stream order bất kể clock dùng gì?** Sequence authoritative/single writer/CAS phù hợp.
25. **Một event retry với ID mới có thể tạo duplicate không?** Có.
26. **TTL có quyết định thứ tự clustering không?** Không.
27. **`WRITETIME` có chứng minh event xảy ra khi nào không?** Không.
28. **Một query theo nhiều day buckets có thứ tự tổng hợp tự động không?** Không.
29. **Để đọc top N theo time, cần điều kiện khóa nào?** Đủ partition key và clustering order phù hợp.
30. **Test trên một JVM chứng minh global order giữa nhiều service được không?** Không.

## 22. Tổng kết

- **Bắt đầu từ câu hỏi đọc:** cần thứ tự theo **event time**, theo **ingest time** hay theo **business sequence**? Đây là ba contract khác nhau.
- **`timestamp`** biểu diễn millisecond Unix epoch; phù hợp khi **nguồn sự kiện cung cấp thời gian**. Thêm **`event_id`** vào clustering key để giữ các event trùng millisecond.
- **`timeuuid`** là UUID v1 có timestamp tick 100 ns và thành phần định danh; phù hợp feed sắp theo **thời điểm tạo ID**. Tạo bằng CQL `now()` hoặc Java driver `Uuids.timeBased()`, không dùng UUID v4.
- Timeuuid giúp có **thứ tự deterministic trong partition**, nhưng không bảo đảm clock chính xác 100 ns, không tạo global sequence, không bảo đảm event order giữa nhiều host bị skew.
- Dùng `min_timeuuid`/`max_timeuuid` hoặc `Uuids.startOf`/`endOf` để tạo **range boundaries**; các UUID fake này **không được dùng làm khóa INSERT**.
- `CLUSTERING ORDER BY` định nghĩa thứ tự **trong partition**, không phải `ORDER BY` trên toàn bộ cluster. Bucket theo ngày/giờ giới hạn kích thước partition nhưng đòi hỏi đọc/merge nhiều bucket khi query vượt biên.
- Trong Spring Data Cassandra, dùng `Instant` cho CQL `timestamp`, `UUID` cho CQL `uuid`/`timeuuid`; annotation `@PrimaryKeyColumn(ordering=...)` phải khớp schema, và code phải bảo đảm UUID dành cho `timeuuid` thực sự là v1.
- **Cursor/paging phải giữ đủ khóa thứ tự** và không được coi paging state là snapshot transaction; late events, retry, TTL và delete có thể đổi kết quả.
- Nếu yêu cầu là **thứ tự nghiệp vụ nghiêm ngặt**, dùng sequence có nguồn cấp phát đáng tin, single writer hoặc CAS phù hợp; không thay bằng timestamp hay timeuuid rồi kỳ vọng mạnh hơn những gì chúng bảo đảm.

## Tài liệu tham khảo

1. [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): `timestamp` theo Unix milliseconds, `timeuuid` UUID v1, `date`/`time` và định dạng timezone.
2. [Apache Cassandra — Native Protocol: Data Types](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html): mã hóa `timestamp` 8 byte và `timeuuid` 16 byte UUID v1.
3. [Apache Cassandra — CQL Functions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html): `now()`, `min_timeuuid`, `max_timeuuid`, `to_timestamp`, `to_unix_timestamp`.
4. [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `PRIMARY KEY`, `CLUSTERING ORDER BY` và giới hạn thay đổi schema.
5. [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `WHERE`, range trên clustering columns, `ORDER BY`, `LIMIT` và `ALLOW FILTERING`.
6. [Apache Cassandra Java Driver 4.19 — Uuids API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/uuid/Uuids.html): `timeBased()`, `startOf`, `endOf`, `unixTimestamp` và cảnh báo khác biệt với Java UUID.compareTo.
7. [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): bind UUID/Instant/LocalDate và tái sử dụng prepared CQL.
8. [Spring Data Cassandra 4.5 — PrimaryKeyColumn](https://docs.spring.io/spring-data/cassandra/docs/4.5.x/api/org/springframework/data/cassandra/core/mapping/PrimaryKeyColumn.html): `ordinal`, `PrimaryKeyType` và `ordering`.
9. [Spring Data Cassandra 4.5 — Ordering](https://docs.spring.io/spring-data/cassandra/docs/4.5.x/api/org/springframework/data/cassandra/core/cql/Ordering.html): `Ordering.ASCENDING` và `Ordering.DESCENDING`.
10. [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): composite primary key, entity mapping, `@Table`, `@PrimaryKey`.
11. [Spring Data Cassandra — Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): `CassandraRepository` và CQL `@Query`.
12. [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): query-first design, partition key, clustering và hạn chế wide partition.
13. [Apache Cassandra — TimeWindowCompactionStrategy](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/twcs.html): sử dụng TWCS cho workload time-series/TTL có điều kiện phù hợp.
