# Khóa tăng dần, thời gian trong khóa và phân phối tải

Trong Apache Cassandra, một giá trị **partition key** được đưa qua *partitioner* để xác định token và nhóm replica chịu trách nhiệm lưu dữ liệu. Nhiều hệ thống sinh khóa theo **thứ tự tăng dần**, chẳng hạn số sự kiện 1001, 1002, 1003 hoặc timestamp của từng lần ghi. Điều này đặt ra câu hỏi quan trọng: khóa tăng dần có làm mọi bản ghi mới dồn về một node như trong một số hệ thống lưu trữ sắp thứ tự theo khóa hay không?

**Câu trả lời phụ thuộc vào khóa đang tăng và vị trí của nó trong `PRIMARY KEY`.** Với `Murmur3Partitioner` thường dùng trong Cassandra, partition key tăng dần **không được đặt vào các token tăng dần tương ứng**: giá trị được hash nên các partition keys khác nhau có thể phân bố khắp ring. Nhưng nếu partition key giữ nguyên, còn **clustering column thời gian** tăng dần, mọi hàng mới vẫn nằm trong **cùng phân vùng logic**. Tương tự, dùng timestamp đã làm tròn theo phút làm partition key có thể tạo một phân vùng “đang mở” nhận toàn bộ ghi trong phút đó.

Bài học thuộc chương **Khóa và phân vùng**, nối kiến thức wide-column, phân phối token và thiết kế bảng theo truy vấn với các vấn đề thực tế về ghi theo thời gian, hot partition, đọc theo khoảng, replication, mức nhất quán và ứng dụng Java.

Sau bài học, bạn có thể:

- Phân biệt **giá trị partition key tăng dần** với **clustering key tăng dần**.
- Giải thích chính xác vai trò của Murmur3, token, replica và vì sao *hashing không chữa được hot partition*.
- Nhận biết sai lầm khi dùng `event_day`, `minute_bucket` hoặc `status` làm partition key duy nhất cho lưu lượng lớn.
- Chọn partition key theo thực thể, **time bucket** và **shard** có kiểm soát để cân bằng tải ghi với chi phí đọc.
- Viết truy vấn CQL theo khoảng thời gian trong một phân vùng và tổng hợp kết quả khi phải đọc nhiều phân vùng.
- Duy trì khóa, timestamp và shard ổn định khi thử lại thao tác ghi từ Java.

## 1. Nhìn đúng các thành phần của primary key

Xét bảng chuỗi thời gian:

```sql
CREATE TABLE readings_by_device (
    device_id   uuid,
    measured_at timestamp,
    reading_id  uuid,
    temperature double,
    PRIMARY KEY (device_id, measured_at, reading_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, reading_id ASC);
```

Trong định nghĩa này:

| Thành phần | Cột | Vai trò |
| --- | --- | --- |
| Partition key | `device_id` | Quyết định phân vùng, token và tập replica. |
| Clustering column đầu | `measured_at` | Sắp các hàng theo thời gian **trong cùng phân vùng**. |
| Clustering column tiếp theo | `reading_id` | Phân biệt các bản đo cùng timestamp. |
| Cột dữ liệu | `temperature` | Giá trị đo riêng của từng hàng. |

Nếu 10.000 bản đo mới được gửi cho cùng `device_id`, chúng có 10.000 clustering keys khác nhau nhưng **chỉ một giá trị partition key**. Token của partition đó không thay đổi khi `measured_at` tiến từ 08:00 sang 09:00.

```text
Partition key = device-A -> token(device-A) -> tập replica X

  clustering key (09:03, id-4) -> reading mới
  clustering key (09:02, id-3)
  clustering key (09:01, id-2)
  clustering key (09:00, id-1)

Tăng measured_at / reading_id không tạo partition mới.
```

Từ đây có hai trường hợp hoàn toàn khác nhau:

1. **Tăng giá trị partition key:** `event_id = 1001, 1002, 1003, ...`, mỗi ID là một partition key riêng.
2. **Tăng giá trị clustering key:** `measured_at` lần lượt 08:00, 08:01, 08:02 nhưng `device_id` vẫn giữ nguyên.

Chỉ trường hợp thứ nhất tạo thêm partition keys. Trường hợp thứ hai làm phân vùng đã chọn **rộng hơn theo số hàng**, và nếu nhiều client ghi đồng thời vào khóa đó thì phân vùng có thể trở thành điểm nóng.

## 2. Khóa phân vùng tăng dần có tạo hotspot theo token không?

Với Cassandra triển khai phổ biến sử dụng `Murmur3Partitioner`, partition key được mã hóa thành bytes rồi hash để tính token. Các số `1001`, `1002`, `1003` liền nhau **không mặc nhiên có token liền nhau**.

Ví dụ bảng chỉ tra cứu một event theo ID:

```sql
CREATE TABLE events_by_id (
    event_id bigint PRIMARY KEY,
    occurred_at timestamp,
    payload text
);
```

Ứng dụng có thể ghi:

```sql
INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1001, '2026-11-21T08:00:00Z', 'event A');

INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1002, '2026-11-21T08:00:01Z', 'event B');

INSERT INTO events_by_id (event_id, occurred_at, payload)
VALUES (1003, '2026-11-21T08:00:02Z', 'event C');
```

Vì ba giá trị `event_id` là ba partition keys khác nhau, hệ thống tính token riêng cho từng giá trị. Thứ tự số học `1001 < 1002 < 1003` **không dự đoán được thứ tự token**.

```text
event_id 1001 --hash--> token T3 ----> replica set R3
event_id 1002 --hash--> token T1 ----> replica set R1
event_id 1003 --hash--> token T2 ----> replica set R2

T1/T2/T3 ở đây chỉ là ký hiệu minh họa, không phải token thực tế.
Các replica set cũng có thể trùng nhau ở cluster nhỏ.
```

**Hệ quả:** không nên áp dụng máy móc lập luận “khóa tăng dần luôn ghi vào mép phải của một index B-tree” cho Cassandra dùng Murmur3. Tuy nhiên, cũng **không được kết luận** mọi workload có khóa tăng dần đều cân bằng:

- Nếu tại một thời điểm chỉ có **một hoặc vài partition keys đang được ghi**, tải vẫn dồn vào các replica của những key đó.
- Một số khóa có thể nhận **nhiều lệnh hơn** hoặc payload lớn hơn các khóa khác; hash phân bố **vị trí khóa**, không chia workload của một khóa.
- Phân bố thực còn phụ thuộc số node, token/vnode, topology, replication strategy, trạng thái node và sự phân bố khóa thực tế.
- Nếu cluster sử dụng partitioner khác Murmur3, không được mặc định quy tắc phân phối giống nhau; cần xác minh cấu hình đang chạy.

### Tại sao khóa duy nhất cho mỗi event chưa chắc là schema tốt?

Bảng `events_by_id` rất hợp với truy vấn:

```sql
SELECT occurred_at, payload
FROM events_by_id
WHERE event_id = 1002;
```

Nhưng không phù hợp để hỏi “100 sự kiện mới nhất của thiết bị A”, bởi `event_id` không nhóm sự kiện theo thiết bị và thời gian. Không có một partition key chứa timeline để đọc theo clustering order.

**Cardinality cao giúp có nhiều khóa để phân phối; thiết kế bảng vẫn phải bắt đầu từ câu truy vấn.**

## 3. Timestamp trong partition key và clustering key khác nhau thế nào?

Timestamp là một kiểu dữ liệu thời gian. Việc đặt nó vào vị trí nào mới quyết định truy vấn và phân bố tải.

| Thiết kế | Partition key | Điều xảy ra khi thời gian tăng |
| --- | --- | --- |
| `PRIMARY KEY (event_time)` | `event_time` | Mỗi giá trị timestamp khác nhau có thể tạo một partition; token được hash. |
| `PRIMARY KEY (device_id, event_time)` | `device_id` | Các event của cùng thiết bị liên tục thêm clustering rows vào cùng partition. |
| `PRIMARY KEY ((device_id, event_day), event_time)` | `(device_id, event_day)` | Tạo một partition mới **mỗi ngày, mỗi thiết bị**; ghi trong ngày vẫn tập trung vào partition ấy. |
| `PRIMARY KEY (minute_bucket, event_time, event_id)` | `minute_bucket` | Tất cả ghi của mọi thiết bị trong phút hiện tại có thể tập trung vào một partition. |
| `PRIMARY KEY ((tenant_id, minute_bucket, shard_id), event_time, event_id)` | `(tenant_id, minute_bucket, shard_id)` | Nhiều shard cùng tồn tại mỗi phút; phải fan-out khi đọc timeline tenant. |

Cần chú ý dấu ngoặc: `PRIMARY KEY (device_id, event_time)` có **partition key đơn `device_id`**; không phải partition key ghép hai cột.

### Timestamp có độ phân biệt cao làm partition key

```sql
CREATE TABLE events_by_timestamp (
    event_time timestamp PRIMARY KEY,
    event_type text
);
```

Cấu trúc trên làm `event_time` vừa là partition key vừa là primary key đầy đủ. Nếu hai event có **cùng giá trị timestamp** theo độ chính xác mà hệ thống lưu, chúng ghi vào **cùng một hàng logic**. Nếu timestamp thay đổi từng mili giây, chúng thường tạo nhiều partition nhỏ nhưng truy vấn khoảng toàn cục theo timestamp **không** tương đương một range scan hiệu quả của clustering key.

Do đó timestamp đơn lẻ thường không phải khóa tốt cho event stream có nhiều sự kiện đồng thời và nhu cầu truy vấn lịch sử theo thực thể.

### Timestamp tăng trong clustering key

```sql
CREATE TABLE events_by_device_day (
    device_id  uuid,
    event_day  date,
    event_time timestamp,
    event_id   uuid,
    payload    text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Đây là mẫu phù hợp khi ứng dụng biết `device_id` và `event_day` để lấy một lát cắt thời gian. `event_time` tăng theo đồng hồ nhưng **không tham gia tính token**. Điều kiện khoảng trên clustering key giúp đọc dữ liệu theo thứ tự thời gian trong một partition đã định vị.

**Đừng nhầm:** *clustering order* là thứ tự dữ liệu bên trong partition. Nó không đồng nghĩa Cassandra sắp partition keys toàn cluster theo timestamp; cũng không làm các event mới tự dịch sang node tiếp theo khi thời gian tăng.

## 4. Trường hợp dễ nóng nhất: một time bucket đang hoạt động

Giả sử hệ thống lưu mọi event của một tenant theo phút:

```sql
CREATE TABLE tenant_events_by_minute (
    tenant_id     text,
    minute_bucket timestamp,
    occurred_at   timestamp,
    event_id      uuid,
    payload       text,
    PRIMARY KEY ((tenant_id, minute_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Thiết kế trên có partition key ghép `(tenant_id, minute_bucket)`. Khi phút chuyển từ 08:30 sang 08:31, Cassandra tạo partition key mới và tính token mới. Nhưng **trong phút 08:30**, tất cả event của tenant `whale` nằm trong một partition, bất kể số client gửi là bao nhiêu.

```text
08:30:00 - 08:30:59
  partition ('whale', 08:30)
  <- tất cả lệnh ghi hiện tại của tenant whale

08:31:00 - 08:31:59
  partition ('whale', 08:31)
  <- tất cả lệnh ghi trong phút tiếp theo

Hashing chỉ phân bố hai partition keys này giữa các replica.
Nó không chia một phút đang hoạt động thành nhiều phân vùng.
```

Nếu tenant gửi **8.000 event/giây**, mỗi event chứa trung bình **1.000 byte payload logic**:

```text
Một phút:
  8.000 × 60 = 480.000 hàng
  480.000 × 1.000 = 480.000.000 byte
                     ≈ 457,8 MiB payload logic

Tải ghi của một partition đang mở: 8.000 event/giây
```

Các con số chỉ minh họa, chưa tính clustering keys, cell metadata, compression, tombstone hay số replica. Dù bucket phút tránh tích lũy nhiều ngày vào một phân vùng, **480.000 hàng và 8.000 ghi/giây trong một phút** vẫn có thể quá lớn hoặc quá nóng với hệ thống cụ thể.

### Phân biệt ba loại tình huống

| Tình huống | Điều có thể xảy ra | Cách nhìn đúng |
| --- | --- | --- |
| Mỗi event có một partition key tăng dần riêng | Nhiều token được hash, có thể phân tán theo ring | Tốt cho tra cứu event theo ID, không tự đáp ứng timeline. |
| Nhiều event cùng một `device_id`, timestamp clustering tăng | Một partition chứa ngày càng nhiều hàng và nhận tải hiện tại | Có thể tạo **large partition** và **hot partition**. |
| Mọi event cùng `minute_bucket` hiện tại | Tải ghi tập trung vào một partition cho mỗi tổ hợp các thành phần còn lại | Chuyển phút tạo partition mới, nhưng **không sửa nóng ngay trong phút**. |

Không có ngưỡng sự kiện/giây hay MiB chung áp dụng cho mọi cluster. Cần nhìn **đỉnh tải, kích thước payload, topology, compaction, số lượng replica và SLO latency**.

## 5. Thiết kế time bucket theo thực thể

Với truy vấn chủ lực “lấy 100 sự kiện mới nhất của **một thiết bị trong một giờ**”, một thiết kế phổ biến:

```sql
CREATE TABLE device_events_by_hour (
    tenant_id    text,
    device_id    uuid,
    hour_bucket  timestamp,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    payload      text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Mỗi tổ hợp `tenant_id + device_id + hour_bucket` là một partition key. Hàng trong partition được sắp theo `occurred_at DESC` rồi `event_id ASC`.

Một truy vấn phù hợp:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM device_events_by_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND occurred_at >= '2026-11-21T08:20:00Z'
  AND occurred_at <  '2026-11-21T08:30:00Z'
LIMIT 100;
```

Cassandra xác định **một partition** từ ba điều kiện bằng, sau đó duyệt khoảng `[08:20, 08:30)` theo clustering order. `LIMIT 100` giới hạn kết quả, không bảo đảm chỉ đọc đúng 100 cell nếu dữ liệu có tombstone hoặc nhiều SSTable.

### Vì sao thêm `device_id` cải thiện phân phối?

Giả sử tenant có 200 thiết bị đang hoạt động trong một giờ. Thay vì mọi event của tenant trong giờ dùng `(tenant_id, hour_bucket)`, mỗi thiết bị có partition key riêng:

```text
('acme', D01, 08:00)
('acme', D02, 08:00)
...
('acme', D200, 08:00)
```

Các khóa độc lập được hash thành token, vì vậy workload **có cơ hội phân bố** qua nhiều replica sets. Tuy vậy, nếu thiết bị D01 phát sinh 90% event thì partition D01 vẫn nóng; thêm nhiều thiết bị khác không san sẻ tải của riêng nó.

### Bucket ngắn hơn có luôn tốt hơn?

Không. Bucket phút thay vì giờ giảm thời gian một partition tích lũy dữ liệu, nhưng làm truy vấn lịch sử 24 giờ phải xử lý tới 1.440 bucket phút trên mỗi thiết bị, thay vì 24 bucket giờ. Điều đó làm tăng số request, tổng số partition cần đọc và chi phí merge kết quả.

Chọn bucket phải cân đối:

1. Lưu lượng ghi và **đỉnh** sự kiện trên mỗi thực thể/bucket.
2. Payload/row và **số hàng/cell/byte** mỗi partition.
3. Cửa sổ thời gian mà ứng dụng cần đọc thường xuyên.
4. Chi phí **fan-out** sang nhiều bucket và chi phí compaction/repair.
5. TTL và chính sách giữ dữ liệu.

## 6. Shard khi một thực thể vẫn quá nóng

Nếu một tenant hoặc thiết bị phát sinh lượng sự kiện rất lớn **trong cùng một bucket**, có thể thêm `shard_id` vào partition key. Ví dụ nhu cầu đọc timeline **toàn tenant trong một phút**:

```sql
CREATE TABLE tenant_events_by_minute_shard (
    tenant_id     text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Giả sử dùng **16 shard** và mỗi event có một `event_id` ổn định:

```text
shard_id = floorMod(stableHash(event_id), 16)

('whale', 08:30,  0) -> partition 0
('whale', 08:30,  1) -> partition 1
...
('whale', 08:30, 15) -> partition 15
```

Nếu 8.000 event/giây phân bố gần đều, mỗi shard nhận **trung bình 500 event/giây**. Trong một phút, mỗi shard có khoảng **30.000 hàng** và **30 MB payload logic** nếu dùng mức 1.000 byte/event. Đây là kỳ vọng toán học, không phải bảo đảm mỗi shard ở node riêng hoặc chắc chắn không bị nóng.

### CQL ghi và đọc một shard

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    'order-created'
);
```

Giá trị shard `7` chỉ minh họa. Khi chạy thật, producer phải tính shard theo thuật toán chung dựa trên ID sự kiện. Truy vấn một shard:

```sql
SELECT occurred_at, event_id, event_type
FROM tenant_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

Để đọc **100 event mới nhất trên cả 16 shard**, ứng dụng cần:

1. Đọc các shard liên quan với giới hạn concurrency.
2. Nhận các luồng đã sắp theo `occurred_at DESC, event_id ASC` trong từng partition.
3. **Merge** theo cùng comparator, rồi lấy top 100 cho toàn tenant/phút.
4. Dùng paging nếu cần nhiều dữ liệu hơn; không dựa vào `ORDER BY` của Cassandra để sắp thứ tự tự động trên 16 partition keys.

**Giá phải trả cho sharding** là số partition lookup tăng, khó hơn khi truy vấn nhiều bucket, và phải giữ nhất quán thuật toán hash, số shard cùng vòng đời chuyển phiên bản schema.

### Đổi số shard không tự di chuyển dữ liệu cũ

Nếu ban đầu dùng 16 shard rồi chuyển sang 32 shard, cùng một `event_id` có thể cho kết quả shard khác. Dữ liệu đã ghi vẫn ở partition cũ. Phải versioning quy tắc hoặc xác định mốc chuyển đổi, giữ khả năng đọc các bucket cũ hay backfill có kiểm soát; không chỉ sửa hằng số trong ứng dụng rồi cho rằng mọi truy vấn lịch sử vẫn đúng.

## 7. Thời gian tạo sự kiện, write timestamp và timeuuid

Có **ba khái niệm thời gian** thường bị nhầm:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Event time** (thời điểm nghiệp vụ) | `occurred_at timestamp` | Dùng trong clustering key để tổ chức timeline, hoặc tính bucket. |
| **Cassandra write timestamp** | Microsecond timestamp gắn với cell/mutation | Tham gia cơ chế phân giải xung đột giữa các bản ghi. |
| **TimeUUID** | `timeuuid` do `now()` tạo | Định danh chứa thành phần thời gian, có thể dùng làm clustering column. |

**`occurred_at` không tự quyết định bản ghi nào thắng khi hai lệnh ghi cùng primary key**, trừ khi ứng dụng chủ động sử dụng các semantics liên quan write timestamp. Cassandra phân giải các cell theo write timestamp và quy tắc xử lý xung đột của nó. Đây là hai lớp khái niệm khác nhau.

### Dùng `timeuuid` cho clustering column

```sql
CREATE TABLE messages_by_room_day (
    room_id      uuid,
    message_day  date,
    message_id   timeuuid,
    sender_id    uuid,
    body         text,
    PRIMARY KEY ((room_id, message_day), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC);
```

Trong bảng này, `message_id` là clustering column kiểu `timeuuid`; thứ tự của nó phản ánh thành phần thời gian theo comparator của Cassandra, hữu ích cho timeline. Nhưng token vẫn tính từ `(room_id, message_day)`. Không thể vì `message_id` thay đổi ở mỗi tin nhắn mà kỳ vọng ghi được phân tán sang các partition keys mới.

Hàm CQL `now()` sinh một `timeuuid` mới mỗi lần thực thi. Nếu retry một `INSERT` với `now()` ngay trong primary key, có thể tạo **hàng khác** cho cùng sự kiện nghiệp vụ. Khi cần idempotency, hãy tạo `message_id` một lần, lưu hoặc chuyển qua luồng retry để dùng lại chính giá trị đó.

### Event đến trễ và sai lệch đồng hồ

Thời gian event có thể khác thời gian ghi do queue, mạng hoặc clock skew. Nếu bucket được tính từ `occurred_at`:

- Sự kiện đến muộn ngày hôm sau vẫn phải vào **bucket của event time đã xác định**, nếu đó là quy ước nghiệp vụ.
- Không được tính lại bucket theo thời gian máy chủ hiện tại khi retry.
- Mọi producer/consumer phải thống nhất múi giờ (ví dụ UTC), độ chính xác và ranh giới `[start, end)`.
- Nếu cần truy vấn theo **ingestion time** thay vì event time, có thể phải thiết kế đường truy cập riêng.

TimeUUID cũng không tạo thứ tự tuyệt đối đáng tin giữa tất cả client có đồng hồ lệch hoặc sự kiện ghi trễ; yêu cầu thứ tự nghiệp vụ mạnh hơn cần cơ chế phối hợp thích hợp.

## 8. Hot partition do thời gian tăng khác với hot node

Phân biệt:

- **Hot partition**: một partition key đang nhận quá nhiều đọc/ghi, dù kích thước chưa lớn.
- **Large partition**: một partition key đang chứa nhiều hàng/cell/byte, kể cả khi hiếm được truy cập.
- **Hot node**: một node chịu tải vượt trội, có thể do một hot partition, nhiều key cùng ánh xạ lên các replica liên quan hoặc do I/O, compaction, coordinator và topology.

Ví dụ, `minute_bucket = 08:30` là **một khóa đang hoạt động**; sang 08:31, hotspot có thể dịch sang tập replica khác. Di chuyển điểm nóng theo phút **không tương đương loại bỏ điểm nóng**. Mỗi phút vẫn có thể khiến replica phụ trách bị quá tải.

Nếu bảng có hàng triệu partition keys khác nhau và việc truy cập tương đối đều, Murmur3 cùng phân phối token phù hợp giúp trải workload hơn. Nhưng tính cân bằng phải kiểm chứng bằng số liệu về **top keys**, số lần đọc/ghi, phân bố byte và độ trễ trên từng node.

### Replication và consistency có giúp tự chia tải không?

Keyspace dùng replication strategy để chọn bản sao cho mỗi token. Với replication factor `3`, partition có ba replica theo chính sách của keyspace. Tăng RF không biến một phân vùng thành nhiều phân vùng dữ liệu nhỏ hơn; ghi vẫn phải được chuyển đến các replica chịu trách nhiệm.

Consistency level như `LOCAL_ONE` hoặc `LOCAL_QUORUM` quyết định yêu cầu xác nhận/đọc ở mức nào, ảnh hưởng latency và tính sẵn sàng. Nó **không thay đổi partition key** và không thay thế biện pháp bucket/shard để giảm tải tập trung. Khi chẩn đoán, cần quan sát cả coordinator lẫn replica liên quan, thay vì chỉ so số request trung bình trên toàn cluster.

## 9. Quan sát và chẩn đoán tải lệch

Không nên chỉ nhìn `SELECT LIMIT 20` trả nhanh rồi kết luận phân vùng không nóng. Một phân vùng có thể trả trang đầu tốt nhưng vẫn chứa nhiều byte/tombstone hoặc đang nhận ghi với tần suất quá cao.

| Nhóm chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| **Top read/write partition keys** | Có một vài key nhận phần lớn request không? |
| **Partition size/cell count histogram** | Phân vùng đang mở có tích lũy quá nhiều hàng và byte không? |
| **Read/write latency p95, p99, timeout** | Có đuôi độ trễ cao vào lúc chuyển bucket hoặc tăng lưu lượng không? |
| **CPU, disk I/O, network, GC theo node** | Có replica/coordinator nào bị tập trung tải? |
| **SSTables per read, tombstone scans** | Đọc chậm do lượng dữ liệu sống, tombstone hay nhiều SSTable? |
| **Compaction backlog, streaming/repair** | Hoạt động nền có đang khuếch đại vấn đề không? |
| **Tần suất event theo tenant/device/bucket/shard** | Phân bố thực có đều như giả định về hashing không? |

Ví dụ công cụ quản trị thường gặp, cần điều chỉnh theo phiên bản Cassandra đang chạy:

```bash
nodetool tablestats app_ks.tenant_events_by_minute_shard
nodetool tablehistograms app_ks tenant_events_by_minute_shard
```

Nếu phiên bản hỗ trợ, `nodetool toppartitions` hoặc cơ chế sampling/metrics ở ứng dụng có thể giúp xác định các khóa nhận nhiều đọc/ghi. Hãy xác minh cú pháp và khả năng cung cấp theo phiên bản; histogram phân vùng thường là thống kê dựa trên SSTable, không phải kết quả đếm chính xác mọi partition sống tại thời điểm hiện tại.

Không nên dùng `SELECT COUNT(*)` trên phân vùng khổng lồ hoặc quét bảng dưới tải cao chỉ để đo số hàng. Một truy vấn đếm có thể buộc Cassandra xử lý lượng dữ liệu lớn và khiến sự cố nặng hơn.

### Quy trình chẩn đoán thực tế

1. Xác định **truy vấn và thời điểm** xảy ra p99 cao, timeout hoặc hàng đợi ghi.
2. Kiểm tra `PRIMARY KEY` để biết cột nào thực sự là partition key và có bao nhiêu khóa đang được ghi đồng thời.
3. Đo **max/percentile**, không chỉ trung bình, về lượng event và byte trên mỗi key/bucket.
4. Đối chiếu tải giữa các replica và node cùng các công việc compaction/repair.
5. Thử thay bucket theo thực thể hoặc thêm shard trong môi trường có workload đại diện.
6. Đo lại độ trễ ghi/đọc, kích thước partition, fan-out, timeout và khả năng retry idempotent.
7. Chỉ triển khai khi giải pháp phù hợp cả đường ghi **và** các kiểu truy vấn chính.

## 10. Java Driver: tính bucket và shard ổn định

Ví dụ sau sử dụng Cassandra Java Driver 4.x để ghi event vào bảng `tenant_events_by_minute_shard`. `eventId` được tạo **một lần từ luồng nghiệp vụ**, còn `occurredAt` là thời điểm sự kiện bất biến trong các lần retry. Dùng `Instant` để giữ mốc thời gian UTC.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventWriter {
    private static final int SHARD_COUNT = 16;

    private final CqlSession session;
    private final PreparedStatement insert;

    public TenantEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_minute_shard " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, event_type, payload) VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public void write(
            String tenantId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        Instant minuteBucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, minuteBucket, shardId, occurredAt,
            eventId, eventType, payload
        ));
    }
}
```

Những điều cần bảo đảm:

- `eventId` và `occurredAt` **không được tạo lại trong mỗi retry**; nếu đổi, toàn bộ primary key có thể thay đổi.
- `minuteBucket` được tính từ cùng `occurredAt` và quy tắc UTC ở mọi writer/reader.
- `eventId.hashCode()` là thuật toán ổn định trong ngữ cảnh Java `UUID`, nhưng nếu hệ thống đa ngôn ngữ, cần đặc tả cách hash byte, số shard và phiên bản thuật toán để các dịch vụ khác tính cùng kết quả.
- `SHARD_COUNT` là một phần của quy ước lưu trữ; đổi từ 16 sang 32 phải đi kèm kế hoạch đọc dữ liệu lịch sử.
- `PreparedStatement` được tái sử dụng, driver có thể dùng routing key khi bind đủ partition key.
- Ghi thường trong Cassandra có ngữ nghĩa upsert theo **toàn bộ primary key**. Điều này giúp tránh thêm hàng do retry nếu khóa ổn định, nhưng không bảo đảm side effect nghiệp vụ khác được thực hiện đúng một lần.

Với throughput cao, tầng ghi cần **giới hạn số lệnh đồng thời**, chính sách timeout/retry an toàn và theo dõi độ trễ. Một ứng dụng không nên tăng số asynchronous requests vô hạn vì đã chia shard.

### Đọc từ Java khi cần nhiều bucket

Tầng dịch vụ đọc phải xác định toàn bộ bucket/phân vùng liên quan, gọi các prepared queries có đầy đủ khóa và **merge** kết quả theo thứ tự `occurred_at` cùng `event_id`. Truy vấn một shard không đại diện cho toàn tenant; truy vấn chỉ một phút không bao phủ khoảng thời gian qua ranh giới phút. Paging và giới hạn concurrency giúp bảo vệ ứng dụng, còn việc chọn bucket/shard quyết định chi phí truy vấn thực tế.

## 11. Những hiểu lầm phổ biến

| Nhận định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “ID tăng từ 1 đến N luôn ghi vào node có token lớn nhất.” | Murmur3 hash partition key, token không tăng theo số ID. | Kiểm tra partitioner thực tế và phân bố token. |
| “Timestamp càng mới càng nằm trên node tiếp theo.” | Nếu timestamp là clustering column, token không đổi. | Partition key mới quyết định token. |
| “Thêm `event_day` vào partition key luôn hết hotspot.” | Cả ngày hiện tại có thể vẫn dùng một key quá nóng. | Tính mức ghi **trong bucket đang hoạt động**. |
| “Mỗi event một partition chắc chắn tối ưu.” | Đọc timeline có thể phải truy vấn vô số keys. | Nhóm theo thực thể/bucket phù hợp query. |
| “Dùng `CLUSTERING ORDER BY DESC` là cách phân phối ghi giữa node.” | Clustering chỉ sắp hàng **trong partition**. | Dùng partition key/bucket/shard để phân bố tải. |
| “16 shard chắc chắn nhanh gấp 16 lần.” | Replica sets, hotspot khác và chi phí fan-out vẫn tồn tại. | Kiểm chứng tải thực, p95/p99, timeout, read cost. |
| “Thay số shard trong config không ảnh hưởng dữ liệu cũ.” | Cùng event ID có thể map sang partition khác. | Có kế hoạch versioning/migration. |
| “Cứ retry với `now()` là idempotent.” | `now()` sinh timeuuid khác mỗi lần. | Giữ nguyên full primary key trong retry. |
| “Tăng RF hoặc consistency sẽ tự tách hot partition.” | Replica/ack không chia partition key. | Sửa thiết kế phân vùng và phân phối request. |
| “Time bucket không cần thống nhất múi giờ.” | Ghi và đọc có thể tìm ở hai partition keys khác nhau. | Chuẩn hóa cách tính bucket, thường là UTC. |

## 12. Bài tập áp dụng

Một nền tảng nhật ký giao dịch có 50 tenant. Trong giờ cao điểm, tenant `mega` gửi **6.000 sự kiện/giây**; 49 tenant còn lại mỗi tenant gửi **10 sự kiện/giây**. Dữ liệu trung bình **500 byte payload/event**. Hai kiểu truy vấn quan trọng:

- **Q1:** tra cứu chính xác một event bằng `event_id`.
- **Q2:** lấy 100 event mới nhất của một tenant trong **một phút**.

Nhóm thiết kế đề xuất:

```sql
-- A: một partition key cho một tenant, không bucket.
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: một partition key tenant + phút.
PRIMARY KEY ((tenant_id, minute_bucket), occurred_at, event_id)

-- C: tenant + phút + shard.
PRIMARY KEY ((tenant_id, minute_bucket, shard_id), occurred_at, event_id)

-- D: mỗi event là một partition key.
PRIMARY KEY (event_id)
```

**Câu hỏi:**

1. Trong A, `occurred_at` tăng dần có làm mỗi event của `mega` đi sang một partition khác không?
2. B làm phân vùng `mega` ngừng tăng vô hạn theo nhiều ngày, nhưng trong **một phút** vẫn nhận bao nhiêu hàng?
3. Payload logic của B trong một phút là khoảng bao nhiêu MB, chưa tính overhead?
4. Với C có 12 shard, mức ghi trung bình lý tưởng cho mỗi shard của `mega` là bao nhiêu event/giây?
5. C có thể dùng một `SELECT` với `tenant_id` và `minute_bucket` mà không có `shard_id` để lấy 100 event mới nhất toàn tenant không?
6. D thuận lợi cho Q1 hay Q2? Q2 cần thêm điều gì?
7. Nếu dữ liệu ghi theo C được retry với cùng `event_id` nhưng `minute_bucket` được tính lại theo **thời gian hiện tại**, có còn bảo đảm không tạo hàng trùng không?
8. Nếu cluster dùng Murmur3, các `event_id` số tăng liên tục trong D có nhất thiết map tới token tăng liên tục không?

**Đáp án:**

1. **Không.** Partition key chỉ là `tenant_id`; timestamp là clustering column nên mọi event của `mega` vào cùng partition logic.
2. `6.000 × 60 = 360.000` hàng/phút nếu mọi event tạo một full primary key mới.
3. `360.000 × 500 = 180.000.000 byte = 180 MB ≈ 171,7 MiB` payload logic.
4. `6.000 / 12 = 500 event/giây/shard` nếu hash phân bố lý tưởng.
5. **Không theo đường truy cập khóa chính thông thường.** Phải đọc đủ shard liên quan, merge theo clustering order rồi chọn top 100.
6. D thuận lợi cho **Q1**. Muốn đáp ứng Q2 hiệu quả cần thêm bảng timeline hoặc đường truy cập theo tenant, thời gian và bucket.
7. **Không.** Partition key có thể đổi; phải tính bucket từ event time ổn định theo quy tắc nhất quán.
8. **Không.** Murmur3 hash toàn bộ giá trị partition key; thứ tự số của key không dự đoán thứ tự token.

## 13. Ghi nhớ để vận hành Cassandra

- **Partition key tăng dần** dưới Murmur3 tạo các token được hash; không nên mặc định chúng đi tuần tự qua token ring theo thứ tự số học.
- **Clustering time tăng dần** chỉ thêm hàng trong phân vùng đã được chọn; nếu partition key đứng yên, điểm nóng vẫn nằm trên cùng tập replica.
- **Time bucket** giới hạn thời gian tích lũy và vòng đời phân vùng; **shard** tạo nhiều partition keys đồng thời để chia tải đang diễn ra. Cả hai làm tăng chi phí đọc qua nhiều phân vùng.
- **Cardinality** hữu ích, nhưng phải đo thêm phân bố byte, số hàng, tần suất request và hotspot ở replica.
- **Mẫu truy vấn quyết định schema:** tra cứu theo ID, timeline theo thiết bị và timeline toàn tenant thường cần các đường truy cập khác nhau.
- **Retry an toàn** đòi hỏi ID sự kiện, event time, bucket và shard nhất quán; `now()` mỗi lần gửi có thể tạo thêm hàng.
- **Replication, consistency, compaction và repair** ảnh hưởng vận hành nhưng không tự thay đổi khóa phân vùng hoặc chia nhỏ một hot partition.

Hiểu đúng sự khác nhau giữa khóa tăng dần, thời gian trong clustering key và phân phối theo token giúp thiết kế bảng Cassandra có độ trễ dự đoán được, tránh điểm nóng trên cluster và kết nối từ Java mà vẫn giữ đúng ngữ nghĩa dữ liệu khi retry hoặc chuyển bucket.

