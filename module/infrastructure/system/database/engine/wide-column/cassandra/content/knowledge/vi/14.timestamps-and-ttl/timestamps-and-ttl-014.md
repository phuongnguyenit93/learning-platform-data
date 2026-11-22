# Thiết kế dữ liệu theo thời gian, lưu giữ và kiểm thử đồng hồ trong Apache Cassandra

## 1. Mục tiêu và bối cảnh

**Apache Cassandra** là hệ quản trị cơ sở dữ liệu **wide-column phân tán**, phù hợp với nhiều luồng ghi lớn khi bảng được tổ chức theo **truy vấn** và có chiến lược partition phù hợp. Dữ liệu có yếu tố thời gian—telemetry, sự kiện, nhật ký truy cập, thông báo, kết quả xử lý tạm—đặt ra ba câu hỏi khác nhau:

1. **Đọc thế nào?** Lấy 100 sự kiện gần nhất của một thiết bị, tra cứu sự kiện trong ngày, hoặc đọc trạng thái hiện tại?
2. **Giữ bao lâu?** Xóa dữ liệu sau 7 ngày kể từ khi xảy ra, sau 7 ngày kể từ khi nhận, hay lưu tới một mốc `retention_until` cố định?
3. **Tin đồng hồ nào?** Sự kiện có thể đến muộn, client có thể sai giờ, coordinator có thể gán write timestamp khác giờ nghiệp vụ, và một phép thử nhanh có thể thất bại do dùng thời gian thực không kiểm soát.

Nếu không tách các câu hỏi đó, hệ thống dễ gặp **partition quá lớn, truy vấn phải quét dữ liệu, dữ liệu hết hạn sai thời điểm, last-write-wins làm lùi trạng thái và test chạy lúc được lúc không**.

Mục tiêu bài này là thiết kế một luồng sự kiện cảm biến có **truy vấn theo thiết bị và ngày**, thời hạn lưu giữ rõ ràng, khả năng nhận dữ liệu đến muộn, Java Driver 4.x và bộ kiểm thử **Clock** có thể lặp lại. Các ví dụ tập trung vào nguyên tắc để bạn chọn cấu hình phù hợp với workload và phiên bản Cassandra thực tế.

## 2. Bốn thời điểm cần mô hình hóa tách biệt

Một sự kiện đo nhiệt độ có thể mang nhiều mốc giờ cùng lúc. Chúng không phải từ đồng nghĩa.

| Tên | Ví dụ | Nguồn | Ý nghĩa |
|---|---|---|---|
| **Event time** (`event_at`) | 10:00:00.000 UTC | Thiết bị/nguồn phát sự kiện | Khi sự kiện được cho là đã xảy ra |
| **Ingest time** (`ingested_at`) | 10:05:12.400 UTC | Dịch vụ nhận/ghi | Khi hệ thống xử lý hoặc nhận sự kiện |
| **Mutation timestamp** | Epoch micro giây | Driver, CQL `USING TIMESTAMP` hoặc coordinator | Phân xử các phiên bản cell theo **last-write-wins** |
| **Retention deadline** (`retention_until`) | 10:00 UTC sau 7 ngày | Chính sách nghiệp vụ | Mốc sau đó dữ liệu không còn được sử dụng/giữ theo chính sách |

**TTL** là số **giây còn sống tương đối** được gán cho phiên bản cell khi ghi, còn `retention_until` là một **thời điểm tuyệt đối**. Tách hai thứ này đặc biệt quan trọng khi có retry, backfill hoặc dữ liệu đến trễ.

```text
Thiết bị ghi nhận           Dịch vụ tiếp nhận                 Hạn lưu giữ
    event_at                    ingested_at                  retention_until
        |                           |                              |
        +------ dữ liệu đến muộn -->|<------ TTL còn lại ---------->|
        |                           |
        |                   Cassandra nhận mutation
        |                   và gán/nhận write timestamp
        |
        +-- Nếu retention tính từ event time:
            retention_until = event_at + thời gian giữ
```

### Đơn vị phải nhất quán

- CQL kiểu `timestamp` biểu diễn thời gian nghiệp vụ với độ phân giải **mili giây**.
- `USING TIMESTAMP` và `writetime(column)` là **micro giây kể từ Unix epoch**, dùng cho mutation LWW.
- `USING TTL`, `default_time_to_live` và `ttl(column)` dùng **giây**.
- Java `Instant` biểu diễn thời điểm tuyệt đối; `LocalDate` mô tả ngày, cần quy định rõ múi giờ khi lấy ngày từ một `Instant`.
- `System.nanoTime()` là đồng hồ **đo khoảng thời gian**, không phải epoch timestamp để ghi vào Cassandra.

Không suy rằng write timestamp được cấp tại coordinator chính là `event_at`; một sự kiện từ hôm qua có thể được import hôm nay. Nếu dùng event time để đặt `USING TIMESTAMP`, dữ liệu đến muộn có thể bị một mutation timestamp mới hơn che; đó là quyết định thiết kế cần chứng minh, không phải mặc định.

## 3. Đặt truy vấn trước rồi mới chọn partition và clustering key

Giả sử yêu cầu của hệ thống IoT:

- Lấy **100 mẫu đo mới nhất** của một thiết bị trong một ngày.
- Lấy các mẫu của một thiết bị **trong một khoảng thời gian**.
- Đọc **mẫu đo cuối cùng đã được chấp nhận** của thiết bị.
- Giữ dữ liệu lịch sử **7 ngày**, không để request retry làm gia hạn thời gian lưu giữ.

Một bảng cho mọi mục tiêu thường không hiệu quả. Theo mô hình **query-first**, tách:

1. Bảng **lịch sử**: nhiều row theo thiết bị + bucket thời gian; clustering key giúp đọc theo thứ tự sự kiện.
2. Bảng **latest-state**: một row theo thiết bị; cập nhật có điều kiện hoặc theo nguồn version để không làm lùi trạng thái.

```text
             event(device_id, event_at, event_id, value)
                                |
                    +-----------+----------+
                    |                      |
                    v                      v
      readings_by_device_day      latest_reading_by_device
      partition: device+day       partition: device
      clustering: event time      1 row / thiết bị
      truy vấn lịch sử            truy vấn hiện trạng
```

**Không** dùng `ORDER BY writetime(value)` hoặc `ALLOW FILTERING` trên bảng lớn để giả lập một chỉ mục thời gian. Cassandra chỉ sắp xếp row trong partition theo **clustering key** đã khai báo.

## 4. Schema lịch sử theo thiết bị và ngày UTC

Chạy trong **keyspace thử nghiệm** đã tạo và chọn bằng `USE <keyspace>;`. Nếu các bảng cùng tên đã tồn tại với schema khác, hãy dùng tên khác; `IF NOT EXISTS` không thay đổi schema cũ.

```sql
CREATE TABLE IF NOT EXISTS readings_by_device_day (
    device_id text,
    event_day date,
    event_at timestamp,
    event_id uuid,
    temperature_c double,
    ingested_at timestamp,
    retention_until timestamp,
    PRIMARY KEY ((device_id, event_day), event_at, event_id)
) WITH CLUSTERING ORDER BY (event_at DESC, event_id ASC);
```

Ý nghĩa:

- **Partition key** là cặp `(device_id, event_day)`. Các row trong một ngày của một thiết bị được nhóm lại.
- **Clustering key** gồm `event_at` giảm dần và `event_id` để phân biệt hai sự kiện có cùng mili giây.
- `event_day` phải được tính **từ event_at theo UTC**, không từ timezone mặc định của máy chủ Java.
- `event_id` là định danh sự kiện **ổn định qua retry**. Nếu cùng một event retry với ID hoặc `event_at` khác, Cassandra có thể tạo **row khác**, gây dữ liệu trùng.
- `ingested_at` giúp đo độ trễ nguồn; `retention_until` ghi lại hạn tuyệt đối phục vụ chính sách lưu giữ.

Việc dùng `uuid` làm tie-breaker cho các sự kiện trùng `event_at` tạo thứ tự **xác định trong dữ liệu**, nhưng **không nói sự kiện nào thực sự xảy ra trước** nếu các đồng hồ nguồn sai lệch. Nếu cần thứ tự nhân quả, cần một sequence/version từ nguồn đáng tin cậy.

### Dữ liệu mẫu

```sql
INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-01',
    '2026-11-21',
    '2026-11-21T08:30:00.123Z',
    11111111-1414-4141-8141-111111111111,
    32.5,
    '2026-11-21T08:30:01Z',
    '2026-11-28T08:30:00.123Z'
)
USING TTL 604800;

INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-01',
    '2026-11-21',
    '2026-11-21T08:31:00.000Z',
    22222222-1414-4141-8141-222222222222,
    32.9,
    '2026-11-21T08:31:01Z',
    '2026-11-28T08:31:00.000Z'
)
USING TTL 604800;
```

Hai câu trên **minh họa cú pháp và cách đọc**: vì TTL 7 ngày được tính từ **lần ghi**, chúng thực hiện đúng retention 7 ngày từ `event_at` **chỉ khi thời gian nhập dữ liệu gần event_at**. Nếu chạy chúng tại ngày khác nhiều ngày sau 21/11/2026, hạn TTL không còn trùng `retention_until`; đó chính là vấn đề dữ liệu đến trễ sẽ được giải ở phần sau.

### Truy vấn theo partition và clustering range

```sql
-- 100 bản ghi mới nhất trong ngày của thiết bị.
SELECT event_at, event_id, temperature_c
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 100;

-- Giới hạn khoảng giờ trong cùng partition.
SELECT event_at, event_id, temperature_c
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_at >= '2026-11-21T08:00:00Z'
  AND event_at <  '2026-11-21T09:00:00Z';
```

Truy vấn một khoảng **qua nhiều ngày** cần biết các bucket ngày tương ứng và thực hiện nhiều partition reads rồi kết hợp ở tầng ứng dụng. Cassandra không tự cung cấp phép sắp xếp toàn cục theo `event_at` trên nhiều partition; nếu workload đòi truy vấn theo khách hàng/toàn bộ thiết bị hoặc theo một chiều khác, cần **bảng riêng thiết kế cho truy vấn đó**.

## 5. Kích thước time bucket: cân bằng hot partition và số truy vấn

Time bucket theo ngày **không phải công thức cố định**. Cỡ partition phụ thuộc tần suất ghi, kích thước row, số mẫu lưu giữ và truy vấn quan tâm.

Giả sử mỗi thiết bị sinh `10` sự kiện/giây:

```text
10 events/s × 60 × 60 × 24 = 864,000 events / thiết bị / ngày
```

Một partition/ngày có thể chứa **864 nghìn row** trước khi xét tombstone, overhead và các cột khác; đây có thể là một **partition lớn** đối với một số workload. Nếu bucket theo giờ:

```text
10 events/s × 60 × 60 = 36,000 events / thiết bị / giờ
```

| Bucket | Lợi ích | Đánh đổi |
|---|---|---|
| Theo ngày | Ít partition để truy vấn một ngày | Nguy cơ partition lớn/hot khi tốc độ ghi cao |
| Theo giờ | Phân tán ghi và giới hạn cỡ partition tốt hơn | Truy vấn một ngày cần đọc nhiều bucket |
| Theo phút | Hữu ích ở tốc độ rất cao | Nhiều partition nhỏ, tăng fan-out và metadata |

Cần **đo kích thước partition và latency thực tế**, không quyết định chỉ từ số hàng. Nếu mọi sự kiện mới của một thiết bị đều vào đúng một partition hiện hành, partition đó vẫn có thể là **hot partition** dù lưu giữ ngắn. Khi cần chia thêm, có thể dùng shard có kiểm soát trong partition key và cho truy vấn biết các shard phải đọc.

**Quy tắc:** bucket phải xuất phát từ **thời gian được chọn làm thứ tự truy vấn**, thường là `event_at`, với UTC rõ ràng. Nếu dùng `ingested_at` để bucket thì event đến muộn nằm ở ngày nhập, có thể làm truy vấn “mọi event của ngày xảy ra” thiếu dữ liệu nếu ứng dụng không quét bucket ingest tương ứng.

## 6. Bảng latest-state cần quy tắc thứ tự nghiệp vụ riêng

Một bảng latest-state đơn giản:

```sql
CREATE TABLE IF NOT EXISTS latest_reading_by_device (
    device_id text PRIMARY KEY,
    event_version bigint,
    event_id uuid,
    event_at timestamp,
    temperature_c double
);
```

Đọc latest theo partition key:

```sql
SELECT event_version, event_id, event_at, temperature_c
FROM latest_reading_by_device
WHERE device_id = 'sensor-01';
```

Tuy nhiên, nếu **sự kiện cũ đến muộn** và `UPDATE` thường mang mutation timestamp **lớn hơn** vì được ingest sau, nó có thể ghi đè mẫu đo thực sự mới hơn.

```text
10:00 event E1: 30°C
10:01 event E2: 32°C -> latest = 32°C
10:05 E1 được gửi lại với write timestamp mới -> latest có thể về 30°C
```

Khi nghiệp vụ bắt buộc latest theo **thứ tự sự kiện đáng tin cậy**, cân nhắc:

- Một writer/projector được phân công theo `device_id`, xử lý event theo sequence.
- Lưu `event_version` do nguồn có thứ tự cấp, chỉ áp dụng transition hợp lệ.
- **LWT** (*lightweight transaction*) `IF` để compare-and-set, kiểm tra kết quả `[applied]`.
- Event log append-only làm nguồn dữ liệu; latest-state chỉ là projection có thể tái tạo.

Ví dụ LWT với version đã được cấp:

```sql
INSERT INTO latest_reading_by_device (
    device_id, event_version, event_id, event_at, temperature_c
)
VALUES (
    'sensor-lwt-01', 1,
    33333333-1414-4141-8141-333333333333,
    '2026-11-21T08:00:00Z', 30.0
)
IF NOT EXISTS;

UPDATE latest_reading_by_device
SET event_version = 2,
    event_id = 44444444-1414-4141-8141-444444444444,
    event_at = '2026-11-21T08:01:00Z',
    temperature_c = 32.0
WHERE device_id = 'sensor-lwt-01'
IF event_version = 1;
```

Lệnh thứ hai chỉ áp dụng nếu version hiện tại là `1`; retry event version cũ sau khi lên `2` không nên được dùng để đảo ngược version. **LWT tốn thêm điều phối/độ trễ**, cần xem xét workload. Không dùng `USING TIMESTAMP` do client cấp trong conditional mutation như ghi thường; LWT có quy tắc timestamp riêng.

## 7. Hai định nghĩa retention: từ lúc xảy ra hay từ lúc nhận?

Một chính sách ghi “giữ 7 ngày” là **chưa đủ để triển khai**. Phải hỏi **7 ngày từ mốc nào**.

| Chính sách | Deadline | Khi event đến muộn 2 ngày | Nơi thường phù hợp |
|---|---|---|---|
| **Ingest-based retention** | `ingested_at + 7 ngày` | Vẫn sống khoảng 7 ngày kể từ khi nhận | Cache, dữ liệu xử lý tạm dựa vào lần nhập |
| **Event-based retention** | `event_at + 7 ngày` | Chỉ còn khoảng 5 ngày | Nhật ký/sự kiện giữ theo ngày phát sinh |
| **Explicit deadline** | `retention_until` do nguồn nghiệp vụ quy định | Giữ tới đúng mốc đã được cấp | Hợp đồng, quy tắc chuyên ngành, kết quả xử lý có hạn cố định |

Ví dụ event `E1` xảy ra `2026-11-20T10:00Z`, nhưng nhập Cassandra lúc `2026-11-22T10:00Z`:

```text
Event-based:  20/11 10:00 + 7 ngày = 27/11 10:00
Ingest-based: 22/11 10:00 + 7 ngày = 29/11 10:00

Nếu ghi USING TTL 604800 vào ngày 22/11,
Cassandra giữ khoảng 7 ngày từ LẦN GHI, tức gần 29/11.
Đó KHÔNG phải event-based retention 7 ngày.
```

Đối với event-based retention, thời gian còn lại cần được tính từ deadline đã xác định trước. **Không dùng trực tiếp `USING TTL 604800` cho dữ liệu backfill** nếu mục tiêu là hết hạn đúng 7 ngày sau event time.

## 8. Tính TTL còn lại từ deadline tuyệt đối

Giả sử chính sách là `retention_until = event_at + 7 ngày`. Tại lúc ghi:

```text
remaining = retention_until - trusted_now
ttl_seconds = số giây nguyên dương được chọn theo chính sách làm tròn
```

Cần phân biệt ba trường hợp:

1. **Deadline đã qua:** không tạo một mutation mới với TTL 0. Trong Cassandra, **`USING TTL 0` nghĩa là không TTL**, hoàn toàn ngược mục đích. Từ chối, bỏ qua hoặc chuyển vào luồng xử lý sự kiện quá hạn.
2. **Deadline còn trong phạm vi TTL hợp lệ:** ghi với TTL dương tương ứng phần thời gian còn lại.
3. **Deadline quá xa, vượt giới hạn TTL/expiration của deployment:** không tự cắt ngắn nếu retention là yêu cầu bắt buộc; phải chọn chính sách lưu giữ khác hoặc xử lý lỗi có thể quan sát.

### Quy tắc làm tròn

TTL dùng **giây nguyên**; còn `Instant` và `timestamp` có thể biểu diễn các phần nhỏ hơn của giây.

- **Làm tròn xuống** phần thời gian còn lại giúp tránh cố ý đặt hạn muộn hơn deadline, nhưng có thể làm giá trị hết hạn **sớm tới gần một giây**.
- **Làm tròn lên** giúp giữ dữ liệu ít nhất tới deadline theo mô hình lý tưởng, nhưng có thể làm cell còn sống **sau deadline** dưới một giây hoặc lâu hơn vì độ trễ/clock skew.
- **Kiểm tra thêm `retention_until` khi đọc/sử dụng** là cần thiết nếu deadline mang ý nghĩa nghiệp vụ chính xác. TTL là công cụ quản lý vòng đời lưu trữ, không phải đồng hồ pháp lý tuyệt đối.

Ngay cả khi ứng dụng tính TTL chính xác đến giây, **Cassandra server xử lý ghi sau thời điểm client tính** và đồng hồ các node có thể lệch. Vì vậy chính sách cần biên an toàn và đường đọc xác thực deadline.

### Thực hành CQL có chủ đích

```sql
-- Ví dụ giả định sự kiện còn 3600 giây để lưu theo deadline.
-- Sử dụng UUID mới; "retention_until" chỉ là metadata nghiệp vụ.
INSERT INTO readings_by_device_day (
    device_id, event_day, event_at, event_id,
    temperature_c, ingested_at, retention_until
)
VALUES (
    'sensor-retention-01',
    '2026-11-21',
    '2026-11-21T07:00:00Z',
    55555555-1414-4141-8141-555555555555,
    27.4,
    '2026-11-21T07:30:00Z',
    '2026-11-21T08:30:00Z'
)
USING TTL 3600;
```

**Những thời điểm trong câu lệnh trên chỉ để đọc ví dụ.** `USING TTL 3600` thực sự bắt đầu từ **lần Cassandra ghi**, không tự kiểm tra chênh lệch giữa `ingested_at` và `retention_until`. Trong code chạy thật, cần tính TTL từ deadline và thời điểm hiện tại trước khi gửi.

## 9. TTL mặc định, retry, tombstone và lưu giữ vật lý

TTL được áp dụng cho **cell được ghi**, không mặc định cho mọi row trong partition. `default_time_to_live` của bảng là lựa chọn thuận tiện khi mọi dữ liệu mới có vòng đời tương đồng:

```sql
CREATE TABLE IF NOT EXISTS transient_alert_by_id (
    alert_id uuid PRIMARY KEY,
    device_id text,
    description text
) WITH default_time_to_live = 86400;

INSERT INTO transient_alert_by_id (alert_id, device_id, description)
VALUES (
    66666666-1414-4141-8141-666666666666,
    'sensor-01', 'Temperature warning'
);
```

Các cell vừa ghi sẽ có TTL mặc định gần **86.400 giây**. Với dữ liệu cần TTL riêng, `INSERT/UPDATE ... USING TTL N` ưu tiên hơn TTL bảng; `USING TTL 0` tạo giá trị mới **không TTL**. Đổi `default_time_to_live` bằng `ALTER TABLE` không tự viết lại thời hạn của các cell đã có.

### Retry không phải một sự kiện mới

Một request bị timeout có thể đã được một số replica chấp nhận. Nếu ứng dụng retry bằng **mutation mới với TTL đầy đủ**, nó có thể **gia hạn thời hạn sống** ngoài ý muốn. Với bảng sự kiện, hãy giữ **`event_id`, `event_at` và `retention_until` ổn định qua retry**; mỗi lần cần gửi lại tính TTL từ cùng deadline, không tạo deadline mới.

Một cách đánh giá an toàn hơn là phân biệt:

- **Idempotent về khóa:** event retry không tạo row mới do thay `event_id` hoặc bucket.
- **Idempotent về trạng thái:** replay cũ không làm lùi latest-state.
- **Idempotent về hạn:** retry không dời deadline nghiệp vụ.
- **Idempotent về side effect:** không gửi thông báo/tính tiền/xử lý một event nhiều lần.

### Hết hạn logic khác thu hồi vật lý

Khi TTL hết, cell không còn sống trong kết quả đọc. Cassandra sử dụng expiration metadata/tombstone để tránh dữ liệu cũ từ replica hoặc SSTable khác xuất hiện trở lại. **Compaction** dọn dữ liệu/tombstone khi an toàn, phối hợp với **repair** và chính sách `gc_grace_seconds`. TTL 7 ngày không bảo đảm byte biến mất khỏi SSTable, snapshot hay backup đúng 7 ngày.

Với telemetry append-only và retention đồng đều, có thể cân nhắc **TimeWindowCompactionStrategy (TWCS)**. Nhưng backfill, TTL lệch nhau lớn, out-of-order writes và cập nhật ngẫu nhiên có thể làm SSTable chồng lấp/cản trở purge. Chọn chiến lược theo **mẫu ghi và điều kiện vận hành**, không chỉ theo tên “time-series”.

## 10. Đọc đúng hai loại đồng hồ: wall clock và monotonic clock

Trong ứng dụng Java có ít nhất hai nhu cầu đo thời gian:

| Câu hỏi | Công cụ phù hợp | Không nên làm |
|---|---|---|
| “Bây giờ là mấy giờ UTC?” | `Clock.instant()` hoặc `Instant.now(clock)` từ nguồn thời gian hệ thống đáng tin cậy | Dùng `System.nanoTime()` làm Unix epoch |
| “Đã trôi qua bao lâu cho thao tác này?” | `System.nanoTime()` cho khoảng thời gian trong cùng process | Lấy chênh hai lần `currentTimeMillis()` nếu đòi đo latency ổn định trước chỉnh giờ |
| “Event thuộc bucket ngày nào?” | `eventAt.atZone(ZoneOffset.UTC).toLocalDate()` | Dùng timezone mặc định của OS hoặc ngày nhận event |
| “Còn bao lâu tới deadline?” | `Duration.between(clock.instant(), expiresAt)` | Lấy TTL cố định ban đầu cho mọi lần retry |
| “Version nào mới hơn về nghiệp vụ?” | `event_version` / sequence / compare-and-set | Chỉ so thời gian nhận request tại coordinator |

**Wall clock** có thể thay đổi do đồng bộ giờ (NTP/chrony), cấu hình sai hoặc điều chỉnh máy ảo. **Monotonic clock** hữu ích để đo elapsed time bên trong tiến trình, nhưng **không** phải đồng hồ phân tán toàn cluster và không thay thế event time hoặc deadline tuyệt đối.

### UTC, timezone và DST

Nếu sự kiện UTC xảy ra lúc `2026-11-21T23:30:00Z`, giờ địa phương ở Việt Nam là sáng **22/11**, nhưng bucket của bảng đang thiết kế **phải là `2026-11-21`**. Không để máy chạy ở UTC+7 đổi `event_day` một cách ngầm định; hai service ở các timezone khác nhau sẽ ghi vào partition khác nhau cho **cùng event**.

Thay đổi giờ mùa hè (**DST**) ở một số múi giờ càng làm việc lấy bucket bằng local date/time dễ lỗi. Giữ `event_at` là `Instant` UTC và tách logic trình bày giờ địa phương khỏi khóa lưu trữ.

## 11. Clock skew/drift: nguy cơ với thứ tự LWW và dữ liệu

**Clock skew** là chênh lệch thời gian giữa hai đồng hồ tại cùng một thời điểm; **clock drift** là tốc độ đồng hồ lệch dần. Trong Cassandra, cả **máy chạy client/driver** và **coordinator/replica** đều cần được chú ý.

```text
Thời gian thực
  10:00:00      event E1 đúng giờ
  10:00:01      event E2 đúng giờ, mới hơn

Client A đồng hồ nhanh 3 phút:
  gán write timestamp khoảng 10:03:00 cho E1

Client B đồng hồ đúng:
  gán write timestamp khoảng 10:00:01 cho E2

LWW cùng cell: E1 có thể thắng E2 dù E1 là sự kiện cũ hơn.
```

Đối với bảng lịch sử append-only có **khóa sự kiện duy nhất**, hai event khác row ít tranh LWW hơn; nhưng `event_day`, `event_at` hoặc `retention_until` vẫn sai nếu lấy từ đồng hồ nguồn bị lỗi. Với bảng latest-state, write timestamp sai còn có thể làm **các cập nhật hợp lệ về sau bị che**.

Các biện pháp:

1. Đồng bộ giờ của Cassandra node và host dịch vụ bằng NTP/chrony hoặc hệ thống tương đương; giám sát offset và độ ổn định.
2. Xác định **nguồn authority của event time**. Đồng hồ trên thiết bị IoT có thể kém tin cậy; cân nhắc lưu cả `device_event_at` và `gateway_received_at`.
3. Định nghĩa **ngưỡng chấp nhận sự kiện tương lai/quá khứ** dựa trên nghiệp vụ, thay vì âm thầm gán timestamp tương lai vào mutation.
4. Giữ event ID và business version ổn định qua retry.
5. Không coi `QUORUM`, `ALL` hoặc repair là cách sửa timestamp đã sai: chúng giúp replica hội tụ theo luật Cassandra, không khôi phục thứ tự nghiệp vụ.

Đồng hồ sai cũng có thể làm thời gian expiration được quan sát lệch kỳ vọng; cần ghi log cả **nguồn giờ** và **khoảng chênh** khi điều tra TTL.

## 12. Java Driver 4.x: ghi event với deadline không đổi qua retry

Đây là ví dụ repository Java dùng **Apache/DataStax Cassandra Java Driver 4.x**. Nó nhận `eventId` và `retentionUntil` **đã được cấp từ nguồn nghiệp vụ**; không tự tạo chúng lại trong mỗi lần retry.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ReadingEventRepository {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public ReadingEventRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO readings_by_device_day (" +
            "device_id, event_day, event_at, event_id, " +
            "temperature_c, ingested_at, retention_until) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    // true: đã gửi và được execute() xác nhận theo CL;
    // false: sự kiện hết hạn theo chính sách, không phát mutation.
    public boolean save(
        String deviceId, UUID eventId, Instant eventAt,
        double temperatureC, Instant retentionUntil
    ) {
        Instant now = clock.instant();
        Duration maxFutureSkew = Duration.ofMinutes(2);
        if (eventAt.isAfter(now.plus(maxFutureSkew))) {
            throw new IllegalArgumentException("Event clock too far ahead");
        }

        long secondsLeft = Duration.between(now, retentionUntil)
            .getSeconds(); // Làm tròn xuống phần giây.
        if (secondsLeft <= 0) {
            return false; // Không biến 0 thành USING TTL 0!
        }
        if (secondsLeft > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL too large");
        }

        // Cũng phải xác minh giới hạn expiration theo phiên bản cluster.
        LocalDate eventDay = eventAt.atZone(ZoneOffset.UTC).toLocalDate();
        session.execute(insert.bind(
            deviceId, eventDay, eventAt, eventId, temperatureC,
            now, retentionUntil, Math.toIntExact(secondsLeft)
        ));
        return true;
    }
}
```

**Ba điểm then chốt:**

- `eventAt` và `retentionUntil` được giữ cố định cho **cùng event**. Nếu lần ghi timeout, luồng retry phải sử dụng **cùng `eventId`, `eventAt`, `retentionUntil`**, không phát sinh khóa hay hạn mới.
- `eventDay` được lấy từ **event time ở UTC**, không từ `ingested_at`. Điều này giữ đúng partition của event đến trễ.
- `secondsLeft` là **TTL còn lại**, không phải TTL 7 ngày cố định. Trường hợp chỉ còn ít hơn một giây có thể bị từ chối sớm do làm tròn xuống; đây là lựa chọn bảo thủ và cần được định nghĩa rõ trong sản phẩm.

Đoạn mã không gọi `setQueryTimestamp(eventAt)`: **event time không tự động là mutation timestamp**. Đồng hồ driver/coordinator và luật LWW có semantics khác; với bảng latest-state phải dùng business version/CAS nếu cần thứ tự.

**Giới hạn:** Repository này chưa xử lý dedupe điều kiện ở Cassandra, chưa kiểm tra `retention_until` ở đường đọc, chưa loại bỏ mọi hiệu ứng của skew và không đảm bảo tính nguyên tử của việc ghi cả lịch sử lẫn latest-state. Đó là những phần cần bổ sung vào kiến trúc ứng dụng thật.

## 13. Tách logic thời gian thành hàm kiểm thử được với `Clock`

Để có unit test **không phụ thuộc giờ thật**, hãy đưa mọi phép tính deadline/bucket/TTL vào một thành phần chỉ phụ thuộc tham số và `Clock`. Ví dụ Java:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

public final class RetentionClockPolicy {
    private RetentionClockPolicy() {}

    public static LocalDate utcBucket(Instant eventAt) {
        return eventAt.atZone(ZoneOffset.UTC).toLocalDate();
    }

    // Trả null khi đã quá hạn/không còn đủ một giây để lưu.
    public static Integer ttlSeconds(
        Clock clock, Instant eventAt, Instant expiresAt,
        Duration allowedFutureSkew
    ) {
        Instant now = clock.instant(); // Chỉ đọc clock một lần.
        if (eventAt.isAfter(now.plus(allowedFutureSkew))) {
            throw new IllegalArgumentException("Future event rejected");
        }
        long remaining = Duration.between(now, expiresAt).getSeconds();
        if (remaining <= 0) {
            return null; // Không gửi USING TTL 0.
        }
        if (remaining > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL out of range");
        }
        return Math.toIntExact(remaining);
    }
}
```

**Nguyên tắc thiết kế:** `Clock` được **inject** vào service và policy; chỉ code khởi tạo production quyết định dùng `Clock.systemUTC()`. Khi test, có thể dùng `Clock.fixed(...)` hoặc `Clock.offset(...)`, tránh phụ thuộc vào `Thread.sleep(...)` và thời điểm lịch thực.

Không cần đổi đồng hồ hệ điều hành để unit test. Mọi phép kiểm tra việc bucket/ngày, policy quá hạn và TTL tính từ deadline có thể chạy hoàn toàn trong JVM theo thời gian giả lập.

## 14. Ví dụ JUnit 5 kiểm thử biên ngày, deadline và đồng hồ lệch

Các kiểm thử dưới đây dùng `RetentionClockPolicy` ở mục trước:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class RetentionClockPolicyTest {
    private static final Duration MAX_FUTURE = Duration.ofMinutes(2);

    @Test
    void bucketUsesUtcEvenWhenEventNearLocalMidnight() {
        Instant event = Instant.parse("2026-11-21T23:30:00Z");
        assertEquals(LocalDate.of(2026, 11, 21),
            RetentionClockPolicy.utcBucket(event));
    }

    @Test
    void ttlIsRemainingTimeNotOriginalRetention() {
        Instant start = Instant.parse("2026-11-21T10:00:00Z");
        Instant deadline = start.plus(Duration.ofMinutes(10));
        Clock atStart = Clock.fixed(start, ZoneOffset.UTC);
        Clock afterNineMinutes = Clock.offset(
            atStart, Duration.ofMinutes(9));

        assertEquals(600, RetentionClockPolicy.ttlSeconds(
            atStart, start, deadline, MAX_FUTURE));
        assertEquals(60, RetentionClockPolicy.ttlSeconds(
            afterNineMinutes, start, deadline, MAX_FUTURE));
        assertNull(RetentionClockPolicy.ttlSeconds(
            Clock.offset(atStart, Duration.ofMinutes(11)),
            start, deadline, MAX_FUTURE));
    }

    @Test
    void rejectsDeviceClockThreeMinutesIntoFuture() {
        Instant now = Instant.parse("2026-11-21T10:00:00Z");
        Clock fixed = Clock.fixed(now, ZoneOffset.UTC);
        Instant eventAt = now.plus(Duration.ofMinutes(3));

        assertThrows(IllegalArgumentException.class, () ->
            RetentionClockPolicy.ttlSeconds(
                fixed, eventAt, now.plus(Duration.ofDays(7)), MAX_FUTURE));
    }

    @Test
    void neverTurnsSubsecondDeadlineIntoTtlZero() {
        Instant now = Instant.parse("2026-11-21T10:00:00Z");
        Clock fixed = Clock.fixed(now, ZoneOffset.UTC);
        assertNull(RetentionClockPolicy.ttlSeconds(
            fixed, now, now.plusMillis(500), MAX_FUTURE));
    }
}
```

Những test này **không mở kết nối Cassandra**. Chúng xác nhận logic Java: bucket UTC, TTL giảm theo đồng hồ được inject, chặn đồng hồ thiết bị quá nhanh và không vô tình phát `USING TTL 0`. Đây là nền tảng để logic retention có thể kiểm thử nhanh, ổn định và lặp lại.

### Những case nên bổ sung

| Case | Kỳ vọng |
|---|---|
| Event `23:59:59.999Z` và `00:00:00.000Z` ngày sau | Nằm ở **hai bucket UTC khác nhau** |
| Event đến trễ 2 ngày, cùng deadline gốc | TTL còn lại **giảm 2 ngày**, không reset thành 7 ngày |
| Replay cùng event ID và timestamp nghiệp vụ | Cùng partition/clustering key; không tạo row mới vì đổi ID |
| Event có timestamp tương lai vượt ngưỡng | Bị chặn hoặc đưa vào quarantine theo policy |
| Deadline đã qua | Không phát mutation với TTL 0 |
| Event bị trùng timestamp mili giây | `event_id` phân biệt row; thứ tự tie không hàm ý quan hệ nhân quả |
| Thay timezone mặc định của JVM | Bucket UTC **không đổi** |
| TTL vượt giới hạn phiên bản Cassandra | Có lỗi/luồng xử lý rõ ràng, không âm thầm cắt TTL trái retention |

## 15. Kiểm thử tích hợp TTL với Cassandra: không “đóng băng” server bằng `Clock.fixed`

Unit test giả lập `Clock` **chỉ tác động code Java**. Khi thực thi `USING TTL` thật, Cassandra dùng metadata expiration dựa trên thời gian phía server; **`Clock.fixed` trong JVM không thay đổi đồng hồ Cassandra**.

Vì vậy, chia kiểm thử thành hai tầng:

### Tầng A — Unit test

- Dùng `Clock.fixed` hoặc `Clock.offset`.
- Kiểm tra đúng bucket, deadline, TTL và quy tắc khi dữ liệu quá hạn.
- Không dùng sleep, không cần chạy cluster.
- Kiểm thử cả event được trả lại từ DLQ sau nhiều ngày, sau DST và lệch đồng hồ nguồn.

### Tầng B — Integration test trên cluster thử nghiệm

1. Tạo **keyspace/bảng riêng** hoặc UUID duy nhất.
2. Ghi cell có TTL ngắn nhưng đủ biên (ví dụ 10–20 giây).
3. Đọc ngay theo partition key: giá trị tồn tại, `ttl(col)` là **số dương** trong khoảng hợp lý.
4. Thăm dò có giới hạn trong khoảng dài hơn TTL; xác nhận cell cuối cùng **không còn sống**, không yêu cầu `ttl()` trả đúng `0` hoặc số âm.
5. Kiểm tra cell không TTL cùng row vẫn sống nếu schema cần hành vi đó.
6. Lặp trong các trường hợp retry/ghi đè có TTL mới, đồng thời phân biệt lỗi do race ở client với lỗi replica.

Ví dụ CQL cho một partition test riêng:

```sql
CREATE TABLE IF NOT EXISTS ttl_clock_test_by_id (
    id uuid PRIMARY KEY,
    ephemeral text,
    persistent_note text
);

INSERT INTO ttl_clock_test_by_id (id, persistent_note)
VALUES (
    77777777-1414-4141-8141-777777777777,
    'remains visible'
);

UPDATE ttl_clock_test_by_id
USING TTL 15
SET ephemeral = 'temporary'
WHERE id = 77777777-1414-4141-8141-777777777777;

SELECT ephemeral, ttl(ephemeral), persistent_note
FROM ttl_clock_test_by_id
WHERE id = 77777777-1414-4141-8141-777777777777;
```

Sau khi TTL kết thúc, `ephemeral` không còn giá trị sống, còn `persistent_note` vẫn có thể được đọc. Đừng khẳng định SSTable đã được dọn vật lý chỉ từ kết quả đọc; **compaction và repair** quyết định thời điểm thu hồi an toàn.

### Kiểm thử lệch đồng hồ trên node

Không tự chỉnh giờ hệ điều hành của node Cassandra production, máy dùng chung hoặc host Docker để giả lập skew: điều đó có thể ảnh hưởng dịch vụ khác, TLS, logging và chính Cassandra. Khi cần kiểm thử hệ thống phân tán trước clock skew, dùng **môi trường cô lập, công cụ fault injection phù hợp và kế hoạch phục hồi đồng hồ**. Trong ứng dụng, test unit có `Clock.offset` giải quyết phần lớn logic phân loại event tương lai mà không phải đổi giờ node.

## 16. Replication, CL, TWCS và kiểm tra retention trong vận hành

Lưu giữ dữ liệu có TTL không chỉ là câu `INSERT`. Trong cluster phân tán, cần đánh giá vòng đời đến lúc thu hồi an toàn:

| Thành phần | Câu hỏi vận hành |
|---|---|
| **Replication factor** | Có bao nhiêu replica giữ partition; replica nào tạm ngắt kết nối? |
| **Consistency level** | `ONE`, `QUORUM`, `ALL` ảnh hưởng xác nhận/đọc như thế nào? |
| **Clock health** | NTP/chrony offset, drift và các node/client lệch quá ngưỡng ra sao? |
| **Event lag** | P50/P95/P99 của `ingested_at - event_at`; có backfill lớn không? |
| **Partition size** | Có hot partition hoặc bucket ngày quá lớn không? |
| **Tombstones** | Workload TTL ngắn và update tạo bao nhiêu tombstone/expired cells? |
| **Compaction** | Backlog, SSTable overlap, I/O và retention thực tế có ổn định không? |
| **Repair** | Replica đã hội tụ trước khi tombstone có thể bị purge chưa? |
| **Snapshots/backups** | Dữ liệu hết TTL còn được giữ trong snapshot/backup tới khi nào? |

Ví dụ CQL kiểm tra metadata của một cell sống:

```sql
SELECT event_at, event_id, temperature_c,
       writetime(temperature_c) AS write_us,
       ttl(temperature_c) AS ttl_s,
       retention_until
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
```

**Đừng suy từ `writetime(temperature_c)` rằng `event_at` đã đúng**, hoặc từ `ttl_s` rằng mọi replica đã đồng bộ chính xác. `writetime()` phản ánh metadata của cell sống đang quan sát, còn `ttl()` phản ánh số giây còn lại; chúng không trả lịch sử retry, tombstone thua hoặc bằng chứng xóa vật lý.

### TWCS chỉ phù hợp khi mô hình ghi phù hợp

Với lịch sử sự kiện chủ yếu **append-only** và TTL gần đồng nhất, **TimeWindowCompactionStrategy** có thể giúp dọn SSTable theo cửa sổ thời gian hiệu quả. Nhưng nếu bản ghi đến muộn, thường xuyên cập nhật cell cũ hoặc TTL được tính là “thời gian còn lại tới deadline” rất khác nhau, SSTable có thể chứa nhiều vòng đời và việc dọn kém đơn giản.

**Không thay `gc_grace_seconds` hoặc ép compaction để sửa lỗi clock/retention.** Grace bảo vệ tombstone trước replica cũ; compaction không biến deadline nghiệp vụ sai thành đúng. Nếu có yêu cầu xóa vật lý/tuân thủ riêng, cần xem cả snapshot, backup, chiến lược repair và quá trình purge.

## 17. Checklist triển khai thiết kế thời gian

Trước khi đưa một bảng thời gian vào production, cần trả lời:

1. **Truy vấn chính là gì?** Partition key/clustering key có phục vụ được không, khoảng thời gian có đi qua nhiều bucket không?
2. **Nguồn event time là gì?** Có xác thực đồng hồ thiết bị, gateway và timezone không?
3. **Ngày bucket được tính từ đâu?** Dùng UTC và quy tắc duy nhất cho mọi writer/retry.
4. **ID và thứ tự sự kiện có ổn định không?** `event_id` không đổi qua replay; khi cần latest-state, có version/CAS hoặc single-writer.
5. **Retention được tính từ event, ingest hay deadline tuyệt đối?** SLA có quy tắc rõ cho late arrivals và backfill.
6. **TTL được tính ở đâu, làm tròn ra sao?** Chặn TTL 0 vô ý, kiểm tra giới hạn TTL/expiration theo phiên bản Cassandra.
7. **Clock được inject và kiểm thử chưa?** Unit test UTC midnight, future skew, expired event, replay; integration test không phụ thuộc con số `ttl()` chính xác tuyệt đối.
8. **Dữ liệu có thể hiện lại do replica cũ không?** Theo dõi repair, tombstone và grace; không tự giảm grace.
9. **Đã kiểm tra hot partition và compaction chưa?** Tính lưu lượng theo bucket, quan sát kích thước và chiến lược dọn.
10. **Có số liệu để chứng minh retention đúng không?** Ghi log `event_id`, `event_at`, `ingested_at`, `retention_until`, TTL được gửi, retry count và nguồn clock, tránh lưu thông tin nhạy cảm không cần thiết.

Một quyết định nên được ghi thành **hợp đồng thời gian của dịch vụ**: định nghĩa nguồn giờ, giới hạn độ trễ/skew, retention theo mốc nào, xử lý event quá hạn, thứ tự version, lựa chọn TTL và cách kiểm thử. Điều này quan trọng hơn việc chỉ bổ sung một cột tên `created_at` vào bảng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Một event xảy ra lúc 10:00 ngày 20/11, được ingest lúc 10:00 ngày 22/11. Retention tính 7 ngày từ event time. Nếu ghi `USING TTL 604800` lúc ingest, hạn thực tế theo TTL so với chính sách ra sao?

**Đáp án:** TTL mới kết thúc gần 29/11, còn hạn theo event time là 27/11. Phải tính **TTL còn lại** từ deadline cố định.

**Câu 2.** Vì sao chọn partition key chỉ là `device_id` có thể nguy hiểm với telemetry 10 sự kiện/giây lưu nhiều tháng?

**Đáp án:** Partition có thể tăng rất lớn và thành hot partition. Nên cân nhắc **time bucket**, ví dụ theo ngày/giờ, tùy tải và truy vấn.

**Câu 3.** Event UTC lúc `23:30` ngày 21/11 được xử lý ở máy chủ UTC+7. `event_day` theo thiết kế UTC là ngày nào?

**Đáp án:** **21/11**, không phải ngày 22/11 theo giờ địa phương.

**Câu 4.** Hai sự kiện có cùng `event_at` tới mili giây, nhưng `event_id` khác nhau. Vì sao giữ cả hai trong clustering key?

**Đáp án:** Để không ghi đè một row chỉ vì trùng độ phân giải thời gian. Thứ tự tie-break theo UUID **không chứng minh** thứ tự xảy ra thật.

**Câu 5.** Một event cũ đến sau và cập nhật latest-state với mutation timestamp mới hơn. Cassandra có chắc giữ sự kiện xảy ra mới nhất không?

**Đáp án:** **Không.** LWW so mutation timestamp, không suy luận thứ tự nghiệp vụ. Cần version/CAS, single writer hoặc projector có thứ tự.

**Câu 6.** Còn 0,5 giây tới `retention_until`; Java lấy `Duration.getSeconds()` ra 0. Có nên gửi `USING TTL 0` không?

**Đáp án:** **Không.** TTL 0 nghĩa **không TTL**; ví dụ policy bảo thủ từ chối ghi trường hợp còn dưới một giây.

**Câu 7.** Có thể dùng `Clock.fixed` trong unit test Java để ép Cassandra server hết TTL ngay lập tức không?

**Đáp án:** **Không.** `Clock.fixed` chỉ thay cách code Java đọc giờ. Server Cassandra vẫn dùng đồng hồ và metadata của nó; cần integration test riêng.

**Câu 8.** `System.nanoTime()` có thể dùng làm giá trị epoch micro giây cho `USING TIMESTAMP` không?

**Đáp án:** **Không.** `nanoTime` thích hợp đo khoảng thời gian trong process, không phải Unix epoch có ý nghĩa trên nhiều máy.

**Câu 9.** Vì sao compaction TWCS không luôn là lựa chọn tối ưu khi có nhiều event backfill?

**Đáp án:** Dữ liệu đến muộn/out-of-order và TTL khác nhau có thể trộn vòng đời trong SSTable, làm dọn hết hạn kém hiệu quả; phải đánh giá workload thực tế.

**Câu 10.** Ghi lại cùng event ID và deadline nhưng gọi `USING TTL 604800` mỗi lần retry có bảo toàn deadline không?

**Đáp án:** **Không.** Một mutation mới có thể đặt lại TTL tính từ lần retry. Cần giữ **`retention_until` bất biến** và tính TTL còn lại từ hạn đó.

---

**Ghi nhớ:** Thiết kế dữ liệu theo thời gian trong Cassandra phải tách **event time, ingest time, mutation timestamp và retention deadline**; chọn **partition/time bucket và clustering key theo truy vấn**; phân biệt retention tính từ **event** hay **ingest**; không để retry kéo dài deadline. Đưa `Clock` vào Java để kiểm thử logic một cách xác định, nhưng kiểm thử expiration thực tế trên Cassandra là bài kiểm thử tích hợp riêng. Cuối cùng, theo dõi **clock skew, RF/CL, tombstone, compaction và repair** để vừa truy vấn hiệu quả vừa thực thi vòng đời dữ liệu an toàn.
