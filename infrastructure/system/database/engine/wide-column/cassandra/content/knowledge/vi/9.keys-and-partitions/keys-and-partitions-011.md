# Chia bucket theo thời gian hoặc miền dữ liệu

Trong Apache Cassandra, **partition key** quyết định dữ liệu thuộc phân vùng logic nào và tập replica nào phục vụ phân vùng ấy. Nếu một partition key tích lũy quá nhiều hàng, cell hoặc byte, phân vùng có thể trở thành **large partition**; nếu một khóa nhận phần lớn lưu lượng trong khoảng ngắn, nó có thể trở thành **hot partition**. Một kỹ thuật thiết kế bảng wide-column quan trọng để kiểm soát hai rủi ro này là **chia bucket** (*bucketing*): thêm một hoặc nhiều thành phần phân nhóm có quy tắc vào partition key.

Có hai hướng chính:

- **Bucket theo thời gian:** nhóm dữ liệu vào các cửa sổ ngày, giờ, phút hoặc một khoảng thời gian xác định. Ví dụ mỗi cặp `(device_id, event_day)` là một phân vùng.
- **Bucket theo miền dữ liệu:** nhóm theo thực thể hoặc phạm vi nghiệp vụ như tenant, khách hàng, dịch vụ, thiết bị, khu vực hoặc loại đơn hàng. Ví dụ mỗi cặp `(tenant_id, device_id)` là một phân vùng. Khi một miền vẫn quá tải, có thể bổ sung một **shard/bucket nhân tạo** được tính ổn định từ định danh sự kiện.

Hai cách có thể được **kết hợp**. Tuy nhiên, bucket không phải chỉ là thủ thuật tạo thêm partition keys: nó thay đổi **các truy vấn CQL hợp lệ**, số phân vùng phải đọc, cách sắp xếp kết quả và logic định tuyến trong ứng dụng Java. Chọn bucket phải đi từ truy vấn chủ lực, phân bố dữ liệu và mức tải thực tế.

Bài học thuộc chương **Khóa và phân vùng**, liên hệ với kiến trúc Cassandra phân tán, replication, consistency level, TTL, compaction, xử lý lỗi và truy cập từ Java.

Sau bài học, bạn có thể:

1. Giải thích mục tiêu của time bucket, domain bucket và shard nhân tạo.
2. Định nghĩa schema CQL có partition key ghép để giới hạn số hàng và byte mỗi phân vùng.
3. Ước lượng kích thước bucket theo tốc độ ghi, payload và thời gian lưu.
4. Thực hiện truy vấn khoảng trong một bucket, xử lý truy vấn băng qua nhiều bucket và hợp nhất kết quả.
5. Nhận biết khi chia bucket chưa giải quyết được write hotspot hoặc gây fan-out quá lớn.
6. Thiết kế thuật toán tính bucket nhất quán giữa writer, reader và các lần retry từ Java.

## 1. Bucket là một phần của partition key, không phải tính năng tự động của Cassandra

Xét bảng lưu sự kiện của thiết bị:

```sql
CREATE TABLE events_by_device_all_time (
    tenant_id   text,
    device_id   uuid,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Partition key là `(tenant_id, device_id)`, còn `event_time` và `event_id` là clustering columns. Mọi sự kiện của một thiết bị thuộc cùng tenant tích lũy vào **một phân vùng logic**, dù chúng được ghi cách nhau nhiều năm.

```text
Partition ('acme', device-A)
  2026-11-21 10:05  event-104
  2026-11-21 10:00  event-103
  2026-11-20 09:00  event-102
  2026-11-19 07:00  event-101
  ...
  2024-01-01 00:00  event-001
```

Cassandra không tự tạo partition mới khi `event_time` sang ngày kế tiếp; clustering columns **không tham gia tính token**. Để chia dữ liệu theo ngày, phải đưa `event_day` vào **partition key** và tính giá trị cột này ngay trong quá trình ghi:

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    event_time,
    event_id
)
```

Khi đó, `('acme', device-A, 2026-11-20)` và `('acme', device-A, 2026-11-21)` là **hai partition keys khác nhau**. Mỗi khóa được hash riêng để xác định token và replica. Không thể chỉ dùng `CLUSTERING ORDER BY` hoặc `LIMIT` để đạt hiệu quả chia phân vùng tương đương.

### Phân loại bucket

| Cách chia | Thành phần partition key điển hình | Mục tiêu | Đánh đổi |
| --- | --- | --- | --- |
| Theo thời gian | `(device_id, event_day)` | Giới hạn lịch sử trong từng phân vùng | Truy vấn nhiều ngày phải đọc nhiều phân vùng. |
| Theo miền nghiệp vụ | `(tenant_id, device_id)` | Tách dữ liệu theo thực thể mà truy vấn đã biết | Thực thể rất lớn/nóng vẫn tạo phân vùng lớn/nóng. |
| Theo miền + thời gian | `(tenant_id, device_id, hour_bucket)` | Giới hạn từng thiết bị trong từng giờ | Truy vấn nhiều thiết bị/giờ cần fan-out. |
| Theo miền + thời gian + shard | `(tenant_id, service_id, minute_bucket, shard_id)` | Chia tải của một thực thể rất nóng trong cùng khoảng thời gian | Đọc phải biết hoặc duyệt các shard liên quan. |
| Bucket nhân tạo không theo thời gian | `(tenant_id, shard_id)` | Phân tán nhiều đối tượng cùng một miền | Cần thuật toán định tuyến và hợp nhất khi đọc toàn miền. |

**Lưu ý về thuật ngữ:** “bucket theo miền dữ liệu” ở đây là cách chia theo **ranh giới nghiệp vụ** (tenant, thiết bị, service, category...), không phải việc dùng `token()` để chia phạm vi token ring. Sharding nhân tạo là phương án riêng khi ranh giới nghiệp vụ tự nhiên chưa đủ phân phối tải.

## 2. Thiết kế bucket theo thời gian

Giả sử ứng dụng cần:

- Đọc các bản đo mới nhất của một thiết bị **trong ngày**.
- Đọc khoảng thời gian `[08:00, 09:00)` của thiết bị đó.
- Giữ dữ liệu theo chính sách lưu trữ, không để một phân vùng tăng vô hạn.

Ta thiết kế:

```sql
CREATE TABLE readings_by_device_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    measured_at timestamp,
    reading_id  uuid,
    temperature double,
    humidity    double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        measured_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (measured_at DESC, reading_id ASC);
```

Trong bảng này:

- `(tenant_id, device_id, event_day)` là **toàn bộ partition key**.
- `measured_at` quyết định thứ tự sự kiện trong phân vùng; `reading_id` phân biệt các bản đo cùng thời điểm.
- `event_day` nên được tính theo **một quy tắc đã thống nhất**, chẳng hạn ngày UTC của `measured_at`.
- Cột ngày là dữ liệu **định tuyến**, không phải cột dùng để sắp thứ tự toàn cục giữa nhiều phân vùng.

### Ghi dữ liệu vào đúng ngày

```sql
INSERT INTO readings_by_device_day (
    tenant_id, device_id, event_day,
    measured_at, reading_id, temperature, humidity
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:35:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    37.9,
    65.0
);
```

Cùng thiết bị ghi một sự kiện vào `2026-11-22` sẽ có partition key khác vì `event_day` khác.

### Truy vấn một bucket

```sql
SELECT measured_at, reading_id, temperature, humidity
FROM readings_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

CQL đã có **đầy đủ partition key**, nên Cassandra biết cần đọc phân vùng nào; hai điều kiện khoảng ràng buộc clustering column đầu tiên. Thứ tự mặc định vẫn là `measured_at DESC`. Viết khoảng đóng–mở `[start, end)` giúp hai khoảng liền nhau không cùng chứa bản ghi ở đúng ranh giới.

### Truy vấn qua hai ngày

Một yêu cầu từ `2026-11-21T23:30:00Z` đến trước `2026-11-22T00:30:00Z` bao phủ hai partition keys:

```text
Bucket 2026-11-21:
  [2026-11-21T23:30:00Z, 2026-11-22T00:00:00Z)

Bucket 2026-11-22:
  [2026-11-22T00:00:00Z, 2026-11-22T00:30:00Z)
```

Ứng dụng truy vấn từng phân vùng rồi **hợp nhất theo `measured_at` và `reading_id`** nếu cần một dòng thời gian thống nhất. `CLUSTERING ORDER BY` chỉ đảm bảo thứ tự **bên trong một partition**, không tạo thứ tự toàn cục trên nhiều ngày.

## 3. Chọn độ dài time bucket: phút, giờ hay ngày?

Bucket càng dài thì mỗi phân vùng chứa càng nhiều dữ liệu nhưng truy vấn lịch sử cần đọc ít partition keys hơn. Bucket càng ngắn thì số hàng/byte trên một phân vùng thường nhỏ hơn, đổi lại số truy vấn và metadata phân vùng tăng.

### Ước lượng từ workload

Giả sử một thiết bị ghi trung bình **50 sự kiện/giây**, mỗi sự kiện có **400 byte payload logic**, không tính clustering key, metadata, tombstone hay nén.

| Độ dài bucket | Số sự kiện ước tính | Payload logic ước tính |
| --- | ---: | ---: |
| 1 phút | 3.000 | 1,2 MB (khoảng 1,14 MiB) |
| 15 phút | 45.000 | 18 MB (khoảng 17,2 MiB) |
| 1 giờ | 180.000 | 72 MB (khoảng 68,7 MiB) |
| 1 ngày | 4.320.000 | 1.728 MB (khoảng 1,61 GiB) |

Đây là **ước lượng payload**, không phải dung lượng SSTable chính xác. Mức thực tế chịu ảnh hưởng số cột/cell, key, compression, collection, tombstone, TTL và compaction. Với `replication factor = 3`, cluster giữ ba bản sao theo chiến lược replication, nhưng không thể lấy con số payload nhân ba rồi xem đó là kích thước đĩa chính xác.

**Công thức kế hoạch ban đầu:**

```text
rows_per_bucket ≈ events_per_second × bucket_seconds
logical_payload ≈ rows_per_bucket × average_payload_bytes

Ví dụ: 50 event/s × 900 s × 400 byte
      = 18.000.000 byte payload mỗi bucket 15 phút
```

Nhưng hãy tính thêm:

1. **Đỉnh lưu lượng:** có thiết bị nào phát sinh 5.000 event/giây thay vì 50?
2. **Mức độ lệch:** bao nhiêu tenant/thiết bị chiếm phần lớn dữ liệu?
3. **Số lần sửa/xóa:** dữ liệu ghi nhiều lần hoặc TTL hết hạn có làm tăng tombstone?
4. **Kiểu đọc:** người dùng thường xem 5 phút hay 30 ngày?
5. **Mục tiêu độ trễ:** p95/p99 query, tốc độ streaming, repair và compaction có đáp ứng không?

Không tồn tại một ngưỡng “bucket dưới X MB” đúng cho mọi phiên bản Cassandra và mọi cluster. Chọn bucket dựa trên kiểm thử tải và số liệu vận hành, không chọn chỉ vì số hàng trung bình đẹp.

## 4. Chia bucket theo miền dữ liệu

Thời gian không phải ranh giới duy nhất. Nhiều ứng dụng có các **miền nghiệp vụ** mà truy vấn thường biết sẵn: khách hàng, thiết bị, tenant, đơn hàng, kho hàng hoặc dịch vụ.

Ví dụ ứng dụng lưu trạng thái của từng thiết bị trong một tenant:

```sql
CREATE TABLE device_state_by_tenant_and_id (
    tenant_id       text,
    device_id       uuid,
    device_name     text,
    firmware        text,
    last_heartbeat  timestamp,
    PRIMARY KEY ((tenant_id, device_id))
);
```

Cặp `(tenant_id, device_id)` tách mỗi thiết bị thành một phân vùng logic chứa một hàng. Đây là cách chọn partition key **theo miền nghiệp vụ**: ứng dụng tra cứu một thiết bị biết đầy đủ tenant và device.

```sql
SELECT device_name, firmware, last_heartbeat
FROM device_state_by_tenant_and_id
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Khác với việc chỉ dùng `tenant_id`, cách này tránh gom toàn bộ thiết bị của tenant `acme` vào **một phân vùng**. Tuy nhiên, nó cũng không hỗ trợ trực tiếp câu hỏi “liệt kê mọi thiết bị của tenant” chỉ bằng điều kiện `tenant_id = 'acme'`. Cần **một bảng phục vụ truy vấn liệt kê tenant** hoặc cơ chế chỉ mục phù hợp.

### Một ví dụ domain bucket cho sự kiện theo service

Giả sử một tenant có nhiều microservice. Nếu hệ thống truy vấn log **theo từng service**, có thể dùng:

```sql
CREATE TABLE service_logs_by_day (
    tenant_id   text,
    service_id  text,
    event_day   date,
    logged_at   timestamp,
    log_id      uuid,
    log_level   text,
    message     text,
    PRIMARY KEY (
        (tenant_id, service_id, event_day),
        logged_at,
        log_id
    )
) WITH CLUSTERING ORDER BY (logged_at DESC, log_id ASC);
```

Bảng kết hợp **miền** (`tenant_id + service_id`) và **thời gian** (`event_day`). Cùng ngày, log của service `auth` và `billing` thuộc **hai phân vùng logic khác nhau**; sang ngày mới, mỗi service có bucket mới.

**Lưu ý:** thêm `service_id` chỉ giúp phân phối tốt nếu các service phát sinh lưu lượng tương đối phù hợp. Nếu `auth` tạo 95% log của tenant, partition `('acme', 'auth', hôm nay)` vẫn có thể rất lớn hoặc nóng.

### Khi miền dữ liệu là category, status hoặc region

Một ranh giới nghiệp vụ **ít giá trị** có thể làm phân vùng còn tệ hơn:

```sql
-- Tất cả đơn ACTIVE vào cùng một partition key:
PRIMARY KEY (status, created_at, order_id)

-- Một region lớn chứa mọi event trong ngày:
PRIMARY KEY ((region, event_day), occurred_at, event_id)
```

Nếu `status` chỉ có 3 giá trị, hoặc region `asia` chiếm 90% lưu lượng, đó là partition key **cardinality thấp hoặc phân bố lệch**. Không phải cứ là “domain bucket” thì sẽ cân bằng.

Hãy chọn thành phần **khớp truy vấn chủ lực** và đánh giá số giá trị phân biệt, mức tập trung hàng/byte, read/write rate theo từng giá trị.

## 5. Kết hợp domain và time bucket cho dữ liệu wide-column

Một bảng lịch sử thường cần cả hai tiêu chí:

- **Miền:** đọc theo một thiết bị hoặc một khách hàng cụ thể.
- **Thời gian:** giới hạn lượng lịch sử trong mỗi phân vùng.

Ví dụ:

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id     text,
    customer_id   uuid,
    month_bucket  text,
    ordered_at    timestamp,
    order_id      uuid,
    total_amount  decimal,
    status        text,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
```

Ứng dụng quy định `month_bucket` có dạng `YYYY-MM` và được tính từ `ordered_at` theo UTC, ví dụ `2026-11`. Đây là một ví dụ bucket theo tháng; kiểu `text` làm mã bucket dễ đọc nhưng ứng dụng phải kiểm soát **định dạng và phép tăng/giảm tháng**.

Truy vấn của một khách hàng trong tháng:

```sql
SELECT ordered_at, order_id, total_amount, status
FROM orders_by_customer_month
WHERE tenant_id = 'acme'
  AND customer_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND month_bucket = '2026-11'
LIMIT 30;
```

Muốn truy vấn “mọi đơn hàng của tenant trong tháng” thì bảng này không phù hợp với đường truy cập bằng primary key vì còn thiếu `customer_id`. Cassandra không tự coi prefix `tenant_id` của partition key ghép như một chỉ mục sắp thứ tự cho mọi customer.

Có thể cần bảng khác theo đường đọc đó, chẳng hạn `orders_by_tenant_day_shard`, hoặc bảng tổng hợp theo tenant. Việc ghi nhiều bảng phải đi kèm cơ chế retry, kiểm tra dữ liệu và xử lý **partial failure**, không mặc định atomic transaction đa phân vùng.

## 6. Bucket nhân tạo khi một miền hoặc một time bucket vẫn nóng

Domain bucketing và time bucketing chủ yếu thay đổi **nhóm dữ liệu và vòng đời**. Chúng chưa chắc giải quyết được việc **một nhóm đang hoạt động nhận quá nhiều ghi**.

Giả sử service `ingest` của tenant `whale` nhận 12.000 sự kiện/giây. Dù partition key là `(tenant_id, service_id, event_day)`, **12.000 ghi/giây** vẫn thuộc **cùng phân vùng ngày**. Có thể bổ sung `shard_id` trong partition key để nhiều phân vùng cùng tồn tại trong một bucket thời gian.

```sql
CREATE TABLE service_events_by_minute_shard (
    tenant_id     text,
    service_id    text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, service_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Giả sử có **12 shard**. Producer gán shard bằng một hàm hash ổn định của `event_id`:

```text
shard_id = floorMod(stableHash(event_id), 12)

Các partition keys trong phút 08:30 UTC:
  ('whale', 'ingest', 08:30, 0)
  ('whale', 'ingest', 08:30, 1)
  ...
  ('whale', 'ingest', 08:30, 11)
```

Nếu phân bố lý tưởng, mỗi shard nhận khoảng `12.000 / 12 = 1.000` ghi/giây. Với `500 byte payload/event` và bucket 60 giây, mỗi shard có thể nhận khoảng `60.000` hàng và `30 MB` payload logic trong phút, chưa tính overhead, replica và compaction.

**Không có bảo đảm** 12 shard sẽ nằm trên 12 node khác nhau hoặc tải cân bằng tuyệt đối: token có thể chọn các replica sets trùng nhau, workload có thể lệch và node còn phục vụ nhiều partition khác.

### Ghi một sự kiện theo shard đã tính

```sql
INSERT INTO service_events_by_minute_shard (
    tenant_id, service_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    'ingest',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'accepted',
    '{"bytes":500}'
);
```

`shard_id = 7` là giá trị **minh họa**; trong hệ thống thật nó phải là kết quả thuật toán định tuyến chung cho sự kiện. Nếu retry cùng một event, phải dùng **cùng `event_id`, `occurred_at`, bucket và shard** để ghi về cùng full primary key.

### Đọc một shard

```sql
SELECT occurred_at, event_id, event_type
FROM service_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND service_id = 'ingest'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

Muốn đọc toàn bộ service trong phút này, ứng dụng cần đọc **các shard liên quan**. Nếu yêu cầu là “top 100 event mới nhất toàn service”, hãy thực hiện merge đã sắp theo cùng comparator `occurred_at DESC, event_id ASC`, rồi lấy 100 hàng đầu tiên. `ORDER BY` của Cassandra không sắp toàn cục trên 12 partition keys.

## 7. Chi phí fan-out và giới hạn của cách chia bucket

**Fan-out** là việc một truy vấn nghiệp vụ phải đọc nhiều partition keys. Chia nhỏ bucket giúp giới hạn dữ liệu mỗi partition nhưng làm số truy vấn tăng.

Ví dụ, yêu cầu đọc **24 giờ** dữ liệu của **một service**:

| Thiết kế | Số partition keys lý thuyết cần đọc |
| --- | ---: |
| Bucket ngày, không shard | 1–2 bucket ngày, tùy ranh giới thời gian |
| Bucket giờ, không shard | 24–25 bucket giờ, tùy ranh giới |
| Bucket phút, không shard | 1.440–1.441 bucket phút |
| Bucket phút và 12 shard | 17.280–17.292 partition keys |

Bảng giả định dữ liệu được truy vấn theo khoảng liên tục đúng 24 giờ và ứng dụng không có chỉ mục phụ để bỏ qua các bucket rỗng. Các con số tính theo số bucket giao nhau với cửa sổ thời gian; cách đếm cụ thể phụ thuộc đầu/cuối có trùng ranh giới và tính khoảng đóng–mở.

Đây là lý do **bucket nhỏ nhất không phải lúc nào cũng tốt nhất**. Hệ thống có thể phải thiết kế bảng riêng cho:

- Tra cứu 100 event gần nhất.
- Đọc sự kiện trong một giờ của một service.
- Báo cáo tổng hợp 30 ngày.
- Tra cứu trực tiếp một event theo `event_id`.

### Phân trang và hợp nhất trên ứng dụng

Khi phải đọc nhiều phân vùng:

1. Tạo danh sách bucket/shard theo quy tắc định tuyến.
2. Truy vấn song song với **giới hạn concurrency**, không gửi hàng chục nghìn truy vấn đồng thời.
3. Mỗi partition đọc theo clustering order, đặt giới hạn số hàng/trang phù hợp.
4. Hợp nhất các luồng kết quả bằng comparator rõ ràng (timestamp + ID) trước khi phân trang ra API.
5. Giữ **paging state** cho từng luồng hoặc chiến lược cursor phù hợp để không bỏ sót dữ liệu có cùng timestamp.
6. Không giả định giới hạn `LIMIT 100` trên mỗi shard tương đương `LIMIT 100` trên toàn bộ kết quả.

**Lưu ý:** để tìm top 100 toàn cục theo cùng comparator, đọc tối đa 100 phần tử đầu tiên của mỗi shard/bucket liên quan là một cách đủ về mặt thứ tự, nhưng có thể đọc dư nhiều hàng. Việc merge theo trang giúp giảm chi phí trong ứng dụng thực tế.

## 8. Tính bucket phải nhất quán với event time và múi giờ

Một lỗi phổ biến là producer tính `event_day` theo UTC nhưng reader tính theo giờ Việt Nam, hoặc retry dùng **thời gian hiện tại** thay cho thời điểm sự kiện ban đầu.

Ví dụ sự kiện:

```text
occurred_at = 2026-11-21T23:30:00Z

Theo UTC:          event_day = 2026-11-21
Theo UTC+07:       ngày lịch = 2026-11-22

Nếu writer ghi partition ngày UTC,
reader hỏi partition ngày UTC+07
=> có thể không tìm thấy event dù event đã được ghi.
```

Do đó cần quy định:

- Bucket được tính theo **event time**, **ingestion time**, hay một thời điểm nghiệp vụ khác.
- Múi giờ chuẩn (thường chọn UTC cho dữ liệu giao tiếp giữa nhiều dịch vụ).
- Quy tắc làm tròn: đầu phút/đầu giờ/ngày theo múi giờ đã chọn.
- Khoảng đọc dùng `[start, end)` để xử lý ranh giới không chồng lặp.
- Chính sách sự kiện đến trễ, đồng hồ thiết bị lệch, backfill và sửa timestamp.
- Idempotency key và full primary key phải **ổn định giữa các lần retry**.

Nếu event đến trễ sau hai ngày nhưng bucket được tính theo `occurred_at`, nó vẫn phải được ghi vào bucket của thời điểm event. Điều này có thể ảnh hưởng compaction strategy của dữ liệu time-series; không nên bí mật đổi sang bucket “hôm nay” chỉ vì thao tác ghi xảy ra hôm nay.

## 9. TTL, compaction và replication có thay được bucket không?

Không. Chúng giải quyết những tầng vấn đề khác nhau.

### TTL

Có thể ghi dữ liệu với TTL, ví dụ 7 ngày:

```sql
INSERT INTO service_events_by_minute_shard (
    tenant_id, service_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale', 'ingest', '2026-11-21T08:30:00Z', 7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'accepted', '{"bytes":500}'
) USING TTL 604800;
```

`604800` là số giây của 7 ngày. TTL làm các cell hết hạn sau khoảng thời gian tính từ lúc ghi theo ngữ nghĩa TTL; nó **không** làm bucket tự tách thêm partition keys. Dữ liệu hết hạn có thể để lại tombstone và chỉ được dọn khỏi SSTable khi đủ điều kiện an toàn qua compaction.

Điều đáng chú ý: với sự kiện đến trễ, `USING TTL 604800` giữ dữ liệu 7 ngày **từ thời điểm ghi**, không nhất thiết đúng 7 ngày **từ thời điểm nghiệp vụ**. Nếu chính sách retention dựa trên event time, cần thiết kế TTL/vòng đời tương ứng thay vì giả định hai thời điểm là một.

### Compaction

`TimeWindowCompactionStrategy` (TWCS) thường được cân nhắc cho dữ liệu chuỗi thời gian append-mostly với TTL và cửa sổ ghi phù hợp. Nhưng TWCS:

- Không sửa partition key hoặc tự chia một phân vùng quá lớn.
- Có thể chịu ảnh hưởng của dữ liệu đến muộn, cập nhật/xóa dữ liệu cũ và các TTL không đồng đều.
- Cần được kiểm tra theo workload và phiên bản Cassandra thực tế.

### Replication, consistency và repair

- Partition key hoàn chỉnh được hash thành token; chiến lược replication quyết định tập replica.
- `replication factor` tạo thêm bản sao, **không** chia nhỏ một hot partition.
- Consistency level quy định mức yêu cầu xác nhận/đọc, không làm một truy vấn thiếu partition key trở nên hiệu quả.
- Repair đồng bộ dữ liệu giữa replica; nó không đổi cách dữ liệu được chia bucket.

Khi chuyển từ bucket ngày sang giờ hoặc thêm shard, thao tác đó thay **mô hình primary key**; thông thường cần tạo bảng mới, chuyển luồng ghi/đọc và lập kế hoạch dữ liệu cũ.

## 10. Java Driver: tính bucket theo thời gian và miền dữ liệu

Ví dụ Java Driver 4.x dưới đây ghi event vào `service_events_by_minute_shard`. `tenantId` và `serviceId` là thành phần **domain bucket**. `minuteBucket` được tính từ `occurredAt` theo UTC, còn `shardId` lấy từ hash ổn định của `eventId`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class ServiceEventRepository {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement selectByBucketAndShard;

    public ServiceEventRepository(CqlSession session) {
        this.session = session;

        this.insert = session.prepare(
            "INSERT INTO service_events_by_minute_shard " +
            "(tenant_id, service_id, minute_bucket, shard_id, " +
            "occurred_at, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );

        this.selectByBucketAndShard = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM service_events_by_minute_shard " +
            "WHERE tenant_id = ? AND service_id = ? " +
            "AND minute_bucket = ? AND shard_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ? " +
            "LIMIT 100"
        );
    }

    public void writeEvent(
            String tenantId, String serviceId,
            Instant occurredAt, UUID eventId,
            String eventType, String payload) {

        Instant bucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shard = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, serviceId, bucket, shard,
            occurredAt, eventId, eventType, payload
        ));
    }

    public com.datastax.oss.driver.api.core.cql.ResultSet readOneShard(
            String tenantId, String serviceId, Instant bucket,
            short shard, Instant startInclusive, Instant endExclusive) {

        Instant bucketEnd = bucket.plus(1, ChronoUnit.MINUTES);

        if (startInclusive.isBefore(bucket) ||
            !startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Khoang doc phai thuoc mot bucket phut UTC");
        }

        return session.execute(selectByBucketAndShard.bind(
            tenantId, serviceId, bucket, shard,
            startInclusive, endExclusive
        ));
    }
}
```

### Những điều cần kiểm soát trong ứng dụng

1. `eventId` phải được sinh **một lần cho sự kiện nghiệp vụ**, không sinh UUID mới mỗi lần retry.
2. `occurredAt`, `minuteBucket` và `shard` phải ổn định khi retry; nếu một thành phần primary key đổi, Cassandra có thể tạo **hàng khác**.
3. Trong ví dụ, `UUID.hashCode()` là hàm băm xác định theo Java. Hệ thống đa ngôn ngữ nên đặc tả chính xác thuật toán hash trên bytes và versioning, không dựa vào tên hàm của từng runtime.
4. `SHARD_COUNT` là một phần của quy ước lưu trữ. Đổi 12 thành 24 **không tự chuyển dữ liệu đã ghi**; reader phải biết cấu hình áp dụng cho bucket cũ hoặc thực hiện migration.
5. `PreparedStatement` được tái sử dụng. Bind đầy đủ partition key giúp driver xác định routing key khi metadata cluster cho phép.
6. Các truy vấn một shard chỉ đọc một phân vùng; khi API cần toàn service hoặc nhiều phút, tầng dịch vụ phải **lập kế hoạch fan-out**, giới hạn concurrency và merge kết quả.
7. Client timeout không chứng minh thao tác trước chưa được áp dụng. Dùng cùng khóa và payload khi retry; nếu yêu cầu cấm ghi đè, đánh giá ghi điều kiện/LWT đúng phạm vi thay vì xem upsert là giao dịch nghiệp vụ “exactly once”.

Đoạn mã là ví dụ đồng bộ để làm rõ định tuyến. Khi throughput cao, có thể dùng asynchronous driver với backpressure và chính sách retry phù hợp, không tăng số request song song vô hạn.

## 11. Vận hành và đo hiệu quả của bucket

Sau khi chia bucket, cần chứng minh rằng mỗi phân vùng **nhỏ hơn hoặc ít nóng hơn**, trong khi truy vấn nghiệp vụ vẫn đáp ứng SLO.

| Nhóm số liệu | Câu hỏi cần trả lời |
| --- | --- |
| **Partition size histogram / max** | Một số bucket còn có số byte cực lớn không? |
| **Cell count / hàng trên partition** | Số cell và clustering rows có được kiểm soát ở tải đỉnh không? |
| **Top read/write partition keys** | Một bucket đang mở hoặc một shard đang nhận phần lớn tải không? |
| **Latency p95/p99, timeout** | Độ trễ giảm cho cả query đọc chính lẫn ghi không? |
| **CPU/I/O/GC/network trên replica** | Tải có cân bằng hơn giữa node không? |
| **SSTables per read, tombstones** | Dữ liệu TTL/xóa có gây read amplification không? |
| **Số partition lookups/API request** | Bucket nhỏ có làm fan-out quá lớn và tăng chi phí truy vấn không? |
| **Compaction/repair/streaming backlog** | Công việc nền có thể hoàn thành trong ngân sách vận hành không? |

Một số công cụ thường gặp, tùy phiên bản Cassandra:

```bash
nodetool tablestats app_ks.service_events_by_minute_shard
nodetool tablehistograms app_ks service_events_by_minute_shard
```

Số liệu từ histogram/compaction không phải phép đo chính xác tức thời của tất cả phân vùng sống. Dùng thêm tracing/metrics, thống kê từ luồng ghi và phân tích top keys có kiểm soát để tìm các outlier. Tránh gọi `SELECT COUNT(*)` trên phân vùng khổng lồ dưới tải cao chỉ để đo kích thước.

### Chọn bucket theo quy trình

1. **Liệt kê truy vấn chính** cùng khóa thực thể người dùng biết lúc đọc.
2. **Ước lượng dữ liệu theo key**: tốc độ trung bình/đỉnh, số hàng, số cell, payload và retention.
3. **Đánh giá skew**: có tenant/thiết bị/service nổi trội không?
4. **Chọn bucket domain và thời gian** theo đường truy vấn, không chỉ theo tổng số khóa tạo ra.
5. **Thêm shard khi thật sự cần** giảm tải đồng thời trong cùng bucket; thiết kế sẵn cách đọc đủ shard.
6. **Ước lượng fan-out** cho các query phổ biến, đặc biệt khi đọc xuyên nhiều giờ/ngày.
7. **Kiểm tra TTL/compaction/repair** theo mô hình dữ liệu và cập nhật thực tế.
8. **Thử nghiệm workload đại diện**, theo dõi p95/p99, replica load, partition max và read cost; hiệu chỉnh độ dài bucket, số shard.

## 12. Chuyển đổi mô hình bucket mà không làm mất dữ liệu

Đang dùng `PRIMARY KEY ((tenant_id, service_id), occurred_at, event_id)` nhưng muốn chuyển sang `(tenant_id, service_id, minute_bucket, shard_id)` nghĩa là **đổi primary key**. Cassandra không chỉ cần thay một tham số `ALTER TABLE`; cần một chiến lược migration.

Một quy trình điển hình:

1. **Tạo bảng mới** với partition key, clustering key và TTL phù hợp truy vấn.
2. **Định nghĩa hàm bucket/shard có version**: múi giờ, độ dài bucket, hash, số shard, nguồn thời gian.
3. **Chuyển writer** sang mô hình mới bằng dual-write hoặc một nguồn sự kiện có thể replay, có nhận diện và khôi phục partial failure.
4. **Backfill lịch sử** có giới hạn tốc độ, checkpoint và ID ổn định để retry không tạo trùng logic.
5. **Đọc đối chiếu** giữa bảng cũ và mới theo nhiều tenant/service/bucket, kiểm tra ranh giới, dữ liệu đến trễ, TTL và xóa.
6. **Chuyển reader** khi kiểm chứng đạt yêu cầu, theo dõi latency và timeout; giữ fallback theo chính sách.
7. **Dừng mô hình cũ** sau khi chắc chắn không còn đường đọc/ghi phụ thuộc, rồi xử lý dữ liệu cũ theo retention.

**Điểm rủi ro:** dual-write qua hai bảng/partition khác nhau không mặc nhiên nguyên tử. Nếu bảng A ghi thành công, bảng B timeout, cần có retry/reconciliation rõ ràng. Việc sửa partition key để giảm hotspot là một thay đổi mô hình dữ liệu lẫn quy trình ứng dụng.

## 13. Những sai lầm hay gặp

| Nhận định | Điều bị bỏ sót | Cách xử lý |
| --- | --- | --- |
| “Thêm `event_day` vào clustering key là đã chia ngày.” | Clustering column không tham gia tính token; phân vùng vẫn chỉ theo partition key. | Đưa bucket ngày vào **partition key**. |
| “Bucket theo tenant luôn cân bằng vì có nhiều tenant.” | Một vài tenant có thể phát sinh phần lớn dữ liệu hoặc request. | Đo skew; kết hợp thiết bị/service, thời gian hoặc shard. |
| “Chia bucket càng ngắn càng hiệu quả.” | Fan-out cho lịch sử dài có thể tăng rất mạnh. | Chọn độ dài theo cả yêu cầu đọc và tải ghi. |
| “12 shard chắc chắn phân bổ đều trên 12 máy.” | Token placement và replica sets có thể trùng; hash có độ lệch. | Đo phân phối thực, điều chỉnh topology/shard khi cần. |
| “Mỗi shard có `LIMIT 100` nên tổng API sẽ có đúng 100 hàng.” | Có thể nhận tối đa 1.200 hàng từ 12 shard. | Merge toàn cục rồi lấy top 100. |
| “Đổi `SHARD_COUNT` trong code không ảnh hưởng dữ liệu cũ.” | Cùng ID có thể định tuyến sang shard khác. | Versioning/migration và đường đọc theo cấu hình cũ. |
| “TTL 7 ngày nghĩa là dữ liệu vật lý biến mất ngay lúc hết hạn.” | Tombstone và compaction vẫn có vòng đời riêng. | Theo dõi TTL, tombstone, compaction và retention. |
| “Replication factor cao sẽ chia nhỏ large partition.” | Replica là bản sao của một partition logic. | Thay partition key/bucket, không chỉ tăng RF. |
| “Retry với `now()` sinh ID mới vẫn là cùng một event.” | Full primary key đã thay đổi, có thể tạo hàng mới. | Giữ event ID, timestamp, bucket và shard ổn định. |
| “Một bảng bucket theo user đủ cho query toàn tenant.” | Query thiếu thành phần partition key; không có thứ tự giữa các partition. | Tạo bảng phục vụ tenant timeline hoặc đường tổng hợp riêng. |

## 14. Bài tập tự kiểm tra

Một nền tảng thương mại điện tử cần ghi sự kiện đặt hàng. Mỗi event có `tenant_id`, `store_id`, `occurred_at` và `event_id`. Workload:

- Có 200 tenant, mỗi tenant có nhiều cửa hàng.
- Cửa hàng phổ thông phát sinh **5 event/giây**.
- Một cửa hàng lớn phát sinh **600 event/giây** vào giờ cao điểm.
- Payload logic mỗi event trung bình **800 byte**.
- **Q1:** lấy 50 event gần nhất của **một cửa hàng trong 15 phút**.
- **Q2:** tạo báo cáo tổng hợp sự kiện của toàn tenant trong 30 ngày.

Nhóm thiết kế đưa ra ba phương án:

```sql
-- A: một partition cho toàn tenant:
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: mỗi cửa hàng trong mỗi giờ là một partition:
PRIMARY KEY ((tenant_id, store_id, hour_bucket), occurred_at, event_id)

-- C: mỗi cửa hàng trong mỗi giờ có thêm shard:
PRIMARY KEY (
    (tenant_id, store_id, hour_bucket, shard_id),
    occurred_at,
    event_id
)
```

**Câu hỏi:**

1. A có nguy cơ large/hot partition nếu tenant có nhiều cửa hàng không? Vì sao?
2. B dùng loại bucket nào? Q1 có thể phải đọc bao nhiêu bucket giờ khi khoảng 15 phút cắt ranh giới giờ?
3. Cửa hàng lớn tạo khoảng bao nhiêu hàng và payload logic trong một giờ nếu dùng B?
4. Nếu C dùng 6 shard và dữ liệu chia lý tưởng, mỗi shard nhận trung bình bao nhiêu event/giây?
5. Với C, có thể chỉ query `WHERE tenant_id = ... AND store_id = ... AND hour_bucket = ...` để đọc toàn bộ 6 shard không?
6. Q2 có nên đọc toàn bộ event thô 30 ngày qua hàng nghìn bucket trên mỗi lượt mở dashboard không?
7. Nếu một event đến muộn một giờ, quy tắc bucket theo **event time** sẽ ghi vào giờ nào?
8. Đổi số shard từ 6 sang 12 mà không có kế hoạch migration có thể dẫn đến vấn đề gì?
9. Một `SELECT LIMIT 50` trên mỗi shard có bảo đảm tổng kết quả 50 hàng đã sắp theo thời gian không?

**Đáp án giải thích:**

1. **Có.** `tenant_id` là partition key duy nhất; tất cả sự kiện của tenant nằm trong một phân vùng, còn `occurred_at` chỉ là clustering column.
2. B kết hợp **domain bucket** `(tenant_id, store_id)` và **time bucket** `hour_bucket`. Một cửa sổ 15 phút có thể giao **1 hoặc 2 bucket giờ**.
3. `600 × 3.600 = 2.160.000` hàng/giờ; payload `2.160.000 × 800 = 1.728.000.000 byte ≈ 1,61 GiB`, chưa overhead/replica.
4. `600 / 6 = 100 event/giây/shard` ở mức trung bình lý tưởng; không bảo đảm mọi shard/replica chịu tải đều.
5. **Không theo đường truy cập primary key đơn giản**: `shard_id` là thành phần partition key; phải cung cấp nó hoặc tổ chức đọc đủ shard.
6. Thường **không**. Q2 nên dùng đường tổng hợp/bảng chuyên biệt, định nghĩa rõ mức chính xác và chu kỳ cập nhật, thay vì quét dữ liệu thô quá nhiều phân vùng mỗi lần.
7. Vào bucket của **thời điểm sự kiện**, không phải giờ hiện tại khi ghi, theo quy ước đã chọn.
8. Cùng event ID có thể ánh xạ sang shard khác, khiến reader không tìm đúng dữ liệu cũ hoặc retry tạo hàng trùng ở partition mới.
9. **Không.** Cần merge các luồng đã sắp theo comparator thống nhất rồi lấy top 50 toàn cục.

## 15. Ghi nhớ

- **Bucket theo thời gian** giới hạn lượng lịch sử của một partition trong cửa sổ xác định; **bucket theo miền** tách dữ liệu theo thực thể hoặc ranh giới nghiệp vụ mà truy vấn biết.
- Bucket không tự xuất hiện từ clustering columns: muốn thay đổi phân vùng phải đưa thành phần bucket vào **partition key**.
- **Kết hợp miền + thời gian** thường phù hợp dữ liệu sự kiện, log, đơn hàng và cảm biến; nếu một khóa vẫn nóng, có thể bổ sung **shard nhân tạo**.
- Mỗi thành phần thêm vào partition key giúp phân chia dữ liệu nhưng cũng yêu cầu reader **biết hoặc truy vấn nhiều giá trị bucket/shard**, kèm chi phí fan-out và merge.
- Chọn bucket từ **truy vấn chủ lực + kích thước phân vùng + đỉnh tải + phân bố lệch + độ trễ**, không dùng một ngưỡng MB chung cho mọi cluster.
- Chuẩn hóa **múi giờ, event time, cách làm tròn, thuật toán hash và số shard**; giữ đầy đủ primary key ổn định khi retry.
- TTL, replication, consistency level, compaction và repair ảnh hưởng vòng đời dữ liệu và vận hành, nhưng **không thay thế** thiết kế partition key.

Thiết kế bucket đúng giúp Cassandra khai thác mô hình wide-column và kiến trúc phân tán một cách dự đoán được: đọc theo khóa và khoảng hiệu quả, phân phối tải phù hợp, kiểm soát compaction/repair, và kết nối từ ứng dụng Java mà không làm sai ngữ nghĩa dữ liệu khi retry hay xử lý sự kiện đến trễ.

