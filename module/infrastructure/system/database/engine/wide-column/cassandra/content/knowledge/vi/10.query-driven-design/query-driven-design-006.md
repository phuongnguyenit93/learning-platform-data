# Thiết kế dữ liệu sự kiện với bucket và thời hạn lưu

## Mục tiêu bài học

Apache Cassandra phù hợp với nhiều hệ thống ghi liên tục các sự kiện như telemetry, nhật ký truy cập, thông báo và thay đổi trạng thái. Điểm khó của thiết kế không nằm ở việc lưu được một sự kiện mà ở chỗ **lưu hàng triệu sự kiện theo một khóa truy cập, đọc chúng có thứ tự, giới hạn kích thước partition và loại bỏ dữ liệu hết hạn mà hệ thống vẫn vận hành ổn định**.

Trong chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này tập trung vào hai quyết định liên quan chặt chẽ:

1. **Bucket**: chia sự kiện thành những partition theo thời gian hoặc shard để mỗi lượt đọc/ghi có phạm vi xác định, tránh partition vô hạn và giảm nguy cơ điểm nóng.
2. **Thời hạn lưu (retention)**: quy định sự kiện được giữ bao lâu, dùng TTL/chiến lược lưu trữ nào, và xử lý như thế nào khi sự kiện đến muộn, bị sửa hoặc đã hết hạn.

Sau bài học, bạn có thể:

- Chuyển hợp đồng truy vấn sự kiện thành partition key, clustering key và quy tắc tính bucket nhất quán.
- Ước tính kích thước partition từ tốc độ ghi, kích thước hàng, mức độ lệch tải và thời gian bucket.
- Viết CQL cho bảng sự kiện với `TTL`, truy vấn theo khoảng, `LIMIT` và phân trang.
- Phân biệt **thời điểm sự kiện xảy ra**, **thời điểm tiếp nhận**, **thời điểm ghi** và tác động của chúng đến TTL.
- Giải thích tombstone, compaction, repair, replication/consistency và những giới hạn thực tế của việc hết hạn dữ liệu.
- Cài đặt logic chọn bucket và TTL từ ứng dụng Java, bao gồm các tình huống hết hạn và ranh giới UTC.

## 1. Bắt đầu từ cách ứng dụng đọc sự kiện

Giả sử một dịch vụ Java nhận telemetry của nhiều thiết bị từ các tenant. Mỗi sự kiện có:

```text
tenant_id, device_id, event_id, event_time,
received_at, event_type, severity, payload
```

Các API có yêu cầu minh họa:

| ID | Nhu cầu | Đầu vào bắt buộc | Thứ tự / giới hạn |
| --- | --- | --- | --- |
| Q01 | Xem 50 sự kiện mới nhất của một thiết bị trong ngày UTC | `tenant_id`, `device_id`, `day_bucket` | `event_time DESC`, 50 hàng |
| Q02 | Xem sự kiện của thiết bị trong khoảng `[09:00, 10:00)` UTC | Tenant, device, ngày, hai mốc | `event_time DESC`, phân trang |
| Q03 | Xem sự kiện trong bảy ngày lịch UTC | Tenant, device, danh sách ngày | Thứ tự trên toàn khoảng, tối đa 100 hàng/lượt |
| Q04 | Tìm một sự kiện chỉ bằng `event_id` | Tenant, event ID | Một sự kiện |
| Q05 | Tìm mọi sự kiện `CRITICAL` trong một tenant/ngày | Tenant, ngày, mức độ | Danh sách trên nhiều thiết bị |

Q01–Q02 là một nhóm truy vấn tự nhiên: ứng dụng luôn biết **thiết bị** và **ngày**, cần đọc các hàng trong ngày theo thứ tự thời gian. Q03 có thể gọi lại cùng bảng nhiều lần rồi hợp nhất, nếu giới hạn số ngày hợp lý. Q04 và Q05 là **đường truy cập khác**; không thể tự động phục vụ hiệu quả từ bảng được thiết kế cho một thiết bị/ngày.

Trước khi chọn bucket, cần làm rõ những câu hỏi mà sản phẩm thường bỏ sót:

- “Bảy ngày gần đây” là **bảy ngày lịch** hay **cửa sổ trượt 7 × 24 giờ**? Hai loại có thể chạm số bucket khác nhau.
- Sự kiện được sắp theo `event_time` do thiết bị gửi hay `received_at` do server ghi?
- Tenant lớn nhất, thiết bị phát nhiều sự kiện nhất và tốc độ ghi đỉnh là bao nhiêu?
- Khi thiết bị gửi dữ liệu **muộn nhiều ngày**, lịch sử còn phải hiển thị hay đã được phép bỏ?
- Thời hạn lưu tính từ **khi sự kiện xảy ra** hay từ **khi dịch vụ nhận**?
- Người dùng cần tải tiếp các trang bao lâu, có chấp nhận rằng sự kiện có thể hết hạn giữa hai lần tải trang không?

Đây là các quyết định nghiệp vụ làm thay đổi partition key, TTL và cách ứng dụng truy vấn.

## 2. Bucket là gì và tại sao cần bucket?

**Bucket** là một giá trị có thể tính được từ sự kiện, thường từ thời gian, dùng làm thành phần của partition key. Thay vì gom mọi sự kiện của một thiết bị vào một partition không giới hạn, ta chia chúng theo ngày, giờ hoặc khoảng thời gian được định nghĩa rõ.

Ví dụ chọn bucket **theo ngày UTC của `event_time`**:

```text
Partition (tenant-A, device-42, 2026-11-20)
    (2026-11-20T23:58:00Z, event-e3)
    (2026-11-20T18:10:00Z, event-e2)

Partition (tenant-A, device-42, 2026-11-21)
    (2026-11-21T09:12:00Z, event-e5)
    (2026-11-21T08:00:00Z, event-e4)

Partition (tenant-A, device-42, 2026-11-22)
    (2026-11-22T00:02:00Z, event-e6)
```

Các partition này phân bố theo token của **toàn bộ composite partition key**. Các hàng trong một partition được tổ chức theo clustering column; thiết kế đang giả định sắp thời gian giảm dần.

Bucket mang lại hai lợi ích rõ ràng:

1. **Giới hạn tăng trưởng theo khóa logic**: partition của thiết bị/ngày không tích lũy mãi lịch sử nhiều năm.
2. **Cho phép định vị trực tiếp phạm vi đọc**: khi API hỏi một thiết bị/ngày, ứng dụng biết chính xác partition cần truy cập.

Bucket cũng tạo thêm chi phí: truy vấn qua nhiều ngày phải đọc **nhiều partition**, hợp nhất các luồng kết quả và quản lý phân trang. Bucket quá nhỏ làm tăng fan-out; bucket quá lớn gây partition lớn/hotspot.

### 2.1. Chọn độ rộng bucket từ dữ liệu thực tế

Ước lượng thô:

```text
rows_per_bucket ≈ events_per_second_of_hottest_device × bucket_seconds
raw_bytes_per_bucket ≈ rows_per_bucket × average_raw_event_bytes
```

Giả sử thiết bị bận rộn nhất ghi **25 sự kiện/giây** liên tục, mỗi sự kiện có khoảng **600 byte dữ liệu nghiệp vụ thô**:

| Bucket | Sự kiện dự kiến | Dữ liệu thô dự kiến |
| --- | ---: | ---: |
| 1 phút | 1.500 | 0,9 MB |
| 1 giờ | 90.000 | 54 MB |
| 1 ngày | 2.160.000 | 1.296 MB (~1,3 GB) |
| 7 ngày | 15.120.000 | 9.072 MB (~9,1 GB) |

Đây chỉ là **ước lượng theo giả định**, chưa gồm overhead lưu trữ, partition index, tombstone, SSTable, compaction, compression hoặc replication. Nó **không phải ngưỡng partition an toàn phổ quát**. Nếu thiết bị có đột biến lên 200 sự kiện/giây, số liệu ở giờ cao điểm cần tính lại theo đỉnh thay vì lấy 25 sự kiện/giây.

Với ví dụ này, bucket **giờ** có thể là một ứng viên đáng thử hơn bucket ngày cho thiết bị nhiều tải. Tuy nhiên, một truy vấn trọn ngày sẽ phải tìm/đọc tối đa 24 bucket giờ của thiết bị đó. Cần đo cả **độ trễ đọc nhiều bucket** lẫn **tải ghi của partition nóng nhất**, rồi mới chốt.

### 2.2. So sánh các mức bucket

| Bucket | Đường đọc phù hợp | Rủi ro cần đo |
| --- | --- | --- |
| Tháng | Lịch sử nhẹ, ít sự kiện, hay xem cả tháng | Tháng dài, có thể tạo partition lớn |
| Ngày | Truy vấn ngày là chính, lưu lượng vừa phải | Thiết bị nóng vẫn có thể ghi quá nhiều trong ngày |
| Giờ | Lưu lượng lớn, đọc khoảng giờ phổ biến | Truy vấn cả ngày/tuần phải đọc nhiều partition |
| Phút | Luồng cực dày và truy vấn rất hẹp | Fan-out và metadata tăng khi đọc khoảng dài |
| Thời gian + shard | Một khóa logic quá nóng ngay trong một bucket | Phải đọc/hợp nhất nhiều shard cho danh sách toàn bucket |

Chọn bucket từ **phân bố lớn nhất, p95/p99, tính chất truy vấn**, không chỉ từ trung bình toàn cụm. Partition key rất tốt cho thiết bị bình thường vẫn có thể không tốt cho một vài thiết bị phát sự kiện dày đặc.

### 2.3. Thống nhất cách tính bucket

Quy định rõ:

- **Thời gian nguồn**: `event_time` của thiết bị, hay `received_at` của hệ thống?
- **Múi giờ**: UTC hay múi giờ nghiệp vụ? Trong bài này dùng **UTC** ở cả đường ghi và đọc.
- **Biên bucket**: nửa mở `[startInclusive, endExclusive)`. Sự kiện đúng 00:00:00Z của ngày mới thuộc ngày mới.
- **Sự kiện đến muộn**: nếu bucket theo `event_time`, sự kiện ngày 20 đến server ngày 21 vẫn nằm trong bucket ngày 20.
- **Thay đổi thời gian**: nếu `event_time` là thành phần của primary key, chỉnh sửa thời gian có thể yêu cầu xóa khóa cũ và ghi khóa mới.

Một hệ thống vừa tính bucket theo `received_at` lúc ghi, vừa tìm theo `event_time` lúc đọc sẽ mất tính nhất quán về vị trí: dữ liệu vẫn nằm trong Cassandra nhưng API nhìn nhầm partition.

## 3. CQL: bảng sự kiện theo thiết bị/ngày

Đầu tiên xét **một bucket ngày UTC** vì Q01–Q02 luôn có ngày và một thiết bị. Schema:

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Phân tích:

- `(tenant_id, device_id, day_bucket)` là **composite partition key**; ba thành phần cùng xác định một partition, không phải ba index độc lập.
- `event_time` là **clustering column đầu tiên**, phục vụ thứ tự thời gian và điều kiện khoảng trong ngày.
- `event_id` là **clustering column thứ hai**, phân biệt các sự kiện có cùng timestamp. Một UUID ngẫu nhiên cung cấp thứ tự phân định theo giá trị khóa, **không chứng minh thứ tự nhân quả** nếu timestamp trùng.
- `event_type`, `severity`, `payload` là dữ liệu của sự kiện, không mặc nhiên là đường lọc hiệu quả.

### 3.1. Ghi sự kiện

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

Dấu `?` là bind marker cho prepared statement của ứng dụng. Nếu chạy trực tiếp trong `cqlsh`, dùng literal hợp lệ. Đường ghi phải tính `day_bucket` từ `event_time` chuẩn hóa UTC **trước khi bind**.

Nếu producer gửi lại **cùng một sự kiện**, ứng dụng nên dùng lại cùng `event_id`, `event_time` và bucket. Khi hai lượt ghi có cùng toàn bộ primary key, Cassandra thực hiện upsert trên cùng hàng logic. Ngược lại, nếu event ID được tạo mới ở mỗi lần retry, hoặc thời gian/bucket đổi, có thể xuất hiện nhiều hàng.

Upsert trùng khóa chỉ là một phần của idempotency: các ô được ghi lại, timestamp ghi và TTL có thể thay đổi kết quả. Nếu cần bảo đảm event ID duy nhất toàn tenant hoặc xử lý trùng xuyên bucket, phải có quy tắc ID/deduplication riêng.

### 3.2. Đọc các sự kiện mới nhất trong ngày

```sql
SELECT event_time, event_id, event_type, severity, payload, received_at
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Q01 cung cấp đủ partition key, và bảng có clustering `DESC`, do đó đọc mới nhất trước mà không cần sort toàn tenant. `LIMIT 50` chỉ giới hạn **số hàng trả về** của truy vấn; nó không bảo đảm Cassandra chỉ đọc đúng 50 hàng vật lý nếu có tombstone hoặc dữ liệu bị lọc.

### 3.3. Đọc một khoảng trong ngày

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

Khoảng nửa mở `[fromInclusive, toExclusive)` tránh trùng sự kiện khi ghép hai khoảng liên tiếp. Cả hai mốc phải thuộc phạm vi bucket đang hỏi; với khoảng vượt nửa đêm UTC, ứng dụng chia truy vấn thành nhiều phần.

Ví dụ:

```text
Yêu cầu [2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)

Lượt 1:
  day_bucket = 2026-11-20
  event_time >= 2026-11-20T23:45:00Z
  event_time <  2026-11-21T00:00:00Z

Lượt 2:
  day_bucket = 2026-11-21
  event_time >= 2026-11-21T00:00:00Z
  event_time <  2026-11-21T00:15:00Z
```

Hai partition **không có thứ tự toàn cục mặc định** chỉ nhờ `CLUSTERING ORDER BY`. Ứng dụng phải hợp nhất theo `(event_time DESC, event_id DESC)` nếu UI cần danh sách chung.

## 4. Thời hạn lưu: chọn chính sách trước khi cấu hình TTL

**Retention** trả lời câu hỏi “sự kiện được phép tồn tại và có thể truy vấn trong bao lâu?”. Đây là chính sách nghiệp vụ, có thể khác giữa sự kiện thông thường, lỗi nghiêm trọng, log phục vụ bảo mật hoặc dữ liệu phục vụ kiểm toán.

Ví dụ yêu cầu:

```text
Telemetry thông thường: giữ 14 ngày
Sự kiện cảnh báo nghiêm trọng: giữ 90 ngày
Sự kiện audit bắt buộc: giữ theo chính sách riêng đã được phê duyệt
```

Nếu áp dụng TTL trong Cassandra, cần phân biệt **logic hết hạn kết quả truy vấn** với **thời điểm byte vật lý được dọn**. Dữ liệu hết hạn không còn hiển thị như dữ liệu sống, nhưng tombstone và các phiên bản cũ có thể vẫn tồn tại trên đĩa cho tới khi đủ điều kiện compaction và cơ chế an toàn xóa.

### 4.1. Retention tính từ lúc ghi hay lúc xảy ra?

Giả sử thời hạn lưu là **14 ngày** và sự kiện có:

```text
event_time:    2026-11-01T10:00:00Z
received_at:  2026-11-05T10:00:00Z
thời hạn:     14 ngày
```

Hai chính sách khác nhau:

| Chính sách | Mốc bắt đầu | Thời điểm hết hạn theo nghiệp vụ |
| --- | --- | --- |
| 14 ngày **sau khi ghi/nhận** | 05/11 lúc 10:00Z | 19/11 lúc 10:00Z |
| 14 ngày **sau khi sự kiện xảy ra** | 01/11 lúc 10:00Z | 15/11 lúc 10:00Z |

Điều này quan trọng với **sự kiện đến muộn**. Nếu cấu hình TTL 14 ngày ở lúc ghi, sự kiện đến muộn 4 ngày được lưu đến 19/11, tức 18 ngày sau thời điểm xảy ra. Nếu sản phẩm cam kết xóa lịch sử 14 ngày sau `event_time` thì dùng TTL cố định lúc ghi là chưa đủ.

### 4.2. TTL mặc định ở cấp bảng

Với chính sách “giữ mỗi giá trị trong **14 ngày kể từ lúc ghi**”, có thể cấu hình:

```sql
CREATE TABLE device_events_by_day_ttl (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 1209600;
```

`1209600 = 14 × 24 × 60 × 60` giây. Giá trị `default_time_to_live` tự áp dụng TTL mặc định cho các giá trị được ghi vào bảng, theo quy tắc Cassandra. TTL tính từ **thời điểm ghi**, không phải tự đọc `event_time` của hàng.

Schema `device_events_by_day_ttl` chỉ là **biến thể minh họa** của bảng ở phần 3. Ứng dụng nên chọn **một schema thực tế phù hợp với chính sách**, không tạo cả hai bảng chỉ vì ví dụ này có hai tên.

TTL không phải một lệnh định kỳ `DELETE WHERE day_bucket < ...`. Dữ liệu hết hạn được đánh dấu không còn sống và quá trình loại bỏ vật lý chịu ảnh hưởng của compaction, tombstone/grace period và trạng thái replica. Không lấy thời điểm file SSTable biến mất làm thước đo duy nhất cho cam kết truy cập dữ liệu.

### 4.3. TTL cho từng lần INSERT

Khi sự kiện có thời hạn khác nhau hoặc retention tính từ `event_time`, có thể truyền TTL theo lần ghi:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

Cột `TTL` là **thời lượng tính bằng giây từ khi ghi**, không phải dấu thời gian hết hạn tuyệt đối. Đối với retention theo event time, ứng dụng nên tính:

```text
expires_at = event_time + retention_duration
remaining_seconds = expires_at - current_time

Nếu remaining_seconds <= 0:
    sự kiện đã hết hạn theo chính sách; không ghi vào bảng TTL đó
Nếu remaining_seconds > 0:
    INSERT ... USING TTL remaining_seconds
```

Ví dụ sự kiện xảy ra lúc 10:00 ngày 01/11, retention 14 ngày, nhận lúc 10:00 ngày 05/11: TTL còn **10 ngày** tại thời điểm ghi, để mốc hết hạn vẫn xấp xỉ 15/11. Độ chính xác của thời điểm hết hạn thực tế phụ thuộc độ phân giải giây, đồng hồ hệ thống và ngữ nghĩa TTL của Cassandra; cần đồng bộ thời gian các máy và quy định sai số chấp nhận được.

Nếu một sự kiện `CRITICAL` cần giữ 90 ngày còn sự kiện thường 14 ngày, phải ghi nhận quy tắc này trong hợp đồng dữ liệu và lựa chọn TTL tương ứng; đừng chỉ gắn cùng TTL 14 ngày cho mọi hàng vì nó là mặc định. Khi trộn nhiều TTL trên cùng bảng và partition, tác động tới tombstone/compaction cần được kiểm tra kỹ.

### 4.4. TTL tác động đến ô dữ liệu; ghi lại có thể thay đổi thời điểm hết hạn

TTL trong Cassandra gắn với **các giá trị ô** được ghi, chứ không phải một bộ đếm được tự động tính từ tên bucket hay một đối tượng “event” trừu tượng. Các ô cùng hàng có thể có TTL khác nhau nếu ứng dụng cập nhật chúng theo những lệnh khác nhau.

Hệ quả cần hiểu:

- Ghi lại một hàng với TTL mới có thể **làm mới thời điểm hết hạn** của các ô được ghi.
- `UPDATE` chỉ thay một số cột có thể làm các cột có vòng đời khác nhau.
- Truy vấn lấy TTL còn lại của một cột cụ thể bằng hàm `TTL` hỗ trợ kiểm tra sự tồn tại của chính sách trên dữ liệu mẫu:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 10;
```

`TTL(payload)` trả số giây còn lại đối với ô có TTL và có giá trị đang sống; kết quả `null` có thể biểu thị ô không có TTL hoặc không hiện diện, nên không suy diễn toàn bộ hàng từ duy nhất một cột. Việc cấu hình TTL cần tính cả **upsert, replay và mutation**.

## 5. Kết hợp bucket với retention như thế nào?

Bucket và TTL giải quyết **hai mục tiêu độc lập**:

- Bucket quyết định **đường định vị và độ lớn partition**.
- TTL quyết định **thời gian sống của dữ liệu đã ghi**.

Một partition có bucket **ngày** nhưng TTL **14 ngày** vẫn là partition của **một ngày**; sau ngày đó, ứng dụng có thể tiếp tục đọc nó cho tới khi dữ liệu bên trong hết TTL. TTL không tự biến bucket ngày thành bucket 14 ngày.

### 5.1. Chọn bucket dựa trên tải, retention dựa trên nghiệp vụ

Giả sử một thiết bị sinh 2 triệu sự kiện/ngày và API chủ yếu đọc một giờ. Retention chỉ có 7 ngày **không có nghĩa bucket ngày là hợp lý**: 2 triệu hàng trong một partition ngày có thể vẫn tạo độ lớn/độ nóng đáng lo. Ngược lại, một thiết bị sinh 50 sự kiện/ngày giữ 180 ngày có thể không cần bucket theo phút.

Các quyết định nên được ghi thành cặp:

```text
Partition scope: (tenant_id, device_id, hour_bucket)
Retention: 14 ngày kể từ event_time
Đọc chính: [from, to) tối đa 6 giờ/HTTP request
Phân trang: 50 hàng/lần; tối đa 6 bucket giờ trên đường đọc chính
Ngoại lệ: sự kiện nhận muộn quá 14 ngày được gửi đến nơi xử lý khác
```

**Chú ý ranh giới:** một khoảng trượt đúng 6 giờ có thể chạm **bảy** bucket giờ nếu hai đầu không thẳng biên giờ. Hãy tính số bucket thực tế theo khoảng nửa mở khi kiểm tra giới hạn API, thay vì mặc định bằng độ dài tính theo giờ.

### 5.2. Truy vấn dữ liệu đã hết hạn

Một màn hình hỏi “sự kiện hai tháng trước” trong bảng giữ 14 ngày cần có hành vi rõ ràng: trả kết quả rỗng, lỗi giới hạn khoảng truy vấn, hoặc chuyển sang hệ lưu trữ lịch sử khác nếu sản phẩm có hỗ trợ.

Không nên fan-out qua hàng trăm bucket để “tìm may” những sự kiện đã vượt chính sách retention. Ứng dụng có thể chặn đầu vào nằm ngoài cửa sổ được phép trước khi tạo CQL; kiểm tra này giúp bảo vệ tài nguyên và thông báo rõ giới hạn cho người dùng.

### 5.3. Retention không đồng nghĩa xóa ngay toàn bộ partition

Khi dùng TTL theo từng ô, các sự kiện của cùng một bucket có thể hết hạn ở các thời điểm khác nhau, nhất là nếu nhận muộn hoặc có nhiều retention policy. Tombstone có thể tồn tại sau khi dữ liệu không còn đọc được.

Không tự xóa trọn partition theo lịch chỉ vì đã qua ngày bucket, nếu một số sự kiện còn trong thời hạn lưu. Ngược lại, nếu yêu cầu pháp lý quy định **xóa vật lý trong thời gian rất chặt**, cần đánh giá cơ chế lưu trữ/xóa và khả năng chứng minh xóa phù hợp; chỉ dùng TTL rồi giả định SSTable biến mất ngay tại mốc hết hạn là không đủ.

## 6. Tombstone, compaction và repair

### 6.1. Tại sao TTL tạo tombstone?

Cassandra lưu dữ liệu dưới dạng SSTable bất biến trên đĩa. Khi dữ liệu hết TTL, Cassandra cần biết giá trị đã bị xóa để không làm dữ liệu cũ còn trong replica/SSTable khác **xuất hiện lại**. Tombstone là một phần cơ chế đánh dấu xóa đó.

Ví dụ một API dùng `LIMIT 50` trên partition mà nhiều sự kiện gần nhất đã hết TTL. Truy vấn có thể đi qua nhiều tombstone mới tìm đủ 50 hàng sống. Vì vậy:

- **Ít hàng trả về** không có nghĩa **ít dữ liệu phải đọc**.
- Theo dõi tombstone scanned, partition lớn, SSTables-per-read và p95/p99.
- Thử tình huống gần cuối thời hạn retention, nhiều TTL khác nhau và dữ liệu xóa thường xuyên.

### 6.2. Compaction phù hợp với dữ liệu thời gian

Với bảng ghi phần lớn append-only, ít cập nhật/xóa và các ô có tuổi thọ tương đối đồng nhất, **TimeWindowCompactionStrategy (TWCS)** là một lựa chọn có thể thử:

```sql
-- Cấu hình minh họa; cần đo với dữ liệu và lịch ghi thực tế.
ALTER TABLE device_events_by_day_ttl
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
```

TWCS nhóm SSTable theo **cửa sổ thời gian của timestamp ghi trong storage**, **không** theo giá trị `day_bucket` trong partition key. Vì thế **bucket ngày** và **compaction window một ngày** là hai khái niệm riêng; trùng tên “ngày” không đảm bảo chúng đồng bộ.

Những trường hợp làm chiến lược theo thời gian kém phù hợp hoặc cần đánh giá thêm:

- Ghi/sửa lại các bản ghi đã cũ trong thời gian dài.
- Có dữ liệu đến muộn và backfill, tạo mẫu timestamp ghi khác luồng thông thường.
- Dữ liệu cùng SSTable có thời hạn sống rất khác nhau.
- Xóa/cập nhật thường xuyên trên các partition đã cũ.

Không mặc định TWCS là lựa chọn tối ưu chỉ vì tên bảng có `_by_day`, và không tự đặt `compaction_window_size` bằng thời gian TTL nếu chưa hiểu mẫu ghi.

### 6.3. Repair và khoảng an toàn xóa

Sao chép (replication) giữ nhiều replica của một partition; consistency level xác định mức đáp ứng đọc/ghi. Trong điều kiện mất mạng, replica có thể lỡ một mutation. **Repair** giúp đồng bộ các replica theo cơ chế Cassandra.

Tombstone chỉ có thể được loại bỏ an toàn khi những điều kiện liên quan tới **grace period, trạng thái replica và compaction** được đáp ứng. Tham số `gc_grace_seconds` liên quan tới an toàn xóa; giảm nó tùy tiện có thể làm tăng nguy cơ dữ liệu đã xóa xuất hiện lại trong một số tình huống replica chưa được đồng bộ. Cần thiết kế lịch repair, quản lý node vắng mặt và chính sách xóa với nhóm vận hành trước khi thay đổi.

Ngay cả khi đọc/ghi với mức như `LOCAL_QUORUM` trong datacenter có replication factor thích hợp, điều đó **không** sửa được partition quá lớn, query range sai hoặc chính sách retention không rõ. Consistency điều chỉnh xác nhận từ replica, không biến một bảng theo thiết bị/ngày thành đường truy cập theo mọi trường tùy ý.

## 7. Java: tính UTC bucket và TTL theo thời gian sự kiện

Ví dụ dưới đây minh họa cách ứng dụng Java tính `day_bucket` và TTL còn lại theo **event time**, sau đó bind vào một prepared statement. Ví dụ dùng **DataStax Java Driver 4.x** với bảng `device_events_by_day` (chưa cấu hình TTL mặc định).

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class EventWriter {
    private static final Duration RETENTION = Duration.ofDays(14);

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public EventWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO device_events_by_day (" +
            "tenant_id, device_id, day_bucket, event_time, event_id, " +
            "received_at, event_type, severity, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    // true: đã gửi lệnh ghi; false: sự kiện đã hết hạn theo chính sách.
    public boolean write(
        String tenantId, UUID deviceId, UUID eventId,
        Instant eventTime, Instant receivedAt,
        String eventType, String severity, String payload
    ) {
        LocalDate bucket = eventTime.atZone(ZoneOffset.UTC).toLocalDate();
        Instant expiresAt = eventTime.plus(RETENTION);
        long secondsLeft = Duration.between(clock.instant(), expiresAt).getSeconds();

        if (secondsLeft <= 0) {
            return false; // Chuyển sang luồng xử lý dữ liệu cũ nếu cần.
        }

        int ttlSeconds = Math.toIntExact(secondsLeft);
        BoundStatement statement = insert.bind(
            tenantId, deviceId, bucket, eventTime, eventId,
            receivedAt, eventType, severity, payload, ttlSeconds
        );
        session.execute(statement);
        return true;
    }
}
```

Giải thích các quyết định:

1. `LocalDate` phù hợp kiểu CQL `date`; `Instant` phù hợp `timestamp`, `UUID` phù hợp `uuid`. Bucket được tính bằng **UTC theo `eventTime`**, không phải theo thời điểm server nhận.
2. `expiresAt` là thời hạn nghiệp vụ tính từ **sự kiện xảy ra**; TTL là **số giây còn lại tại thời điểm chuẩn bị ghi**.
3. Sự kiện đã hết hạn không được ghi vào bảng lưu 14 ngày. Nếu sản phẩm yêu cầu lưu để đối soát, đường xử lý dữ liệu cũ phải được định nghĩa riêng.
4. `Math.toIntExact` chủ động làm lộ lỗi khi TTL vượt phạm vi số nguyên; không được âm thầm ép kiểu. Ví dụ giả định retention 14 ngày nên thông thường TTL nằm trong phạm vi đó.
5. Boolean `true` trong ví dụ cho biết lệnh `execute` hoàn tất mà không ném lỗi trong lần gọi này; **không tự chứng minh** dữ liệu đã hiện diện ở mọi replica hoặc mọi projection khác của nghiệp vụ.

Trong hệ thống thực tế còn cần xác thực tenant, kiểm tra event ID, giới hạn kích thước payload, xử lý retry/idempotency, timeout, consistency level, backpressure và giám sát. Đồng hồ của ứng dụng và các node Cassandra phải được đồng bộ thích hợp: TTL được xử lý theo ngữ nghĩa thời gian của Cassandra, nên có thể có sai lệch nhỏ giữa mốc mong muốn và thời điểm hết hạn thực tế.

### 7.1. Đọc một khoảng từ Java

Một prepared statement cho Q02:

```java
PreparedStatement byRange = session.prepare(
    "SELECT event_time, event_id, severity, payload " +
    "FROM device_events_by_day " +
    "WHERE tenant_id = ? AND device_id = ? AND day_bucket = ? " +
    "AND event_time >= ? AND event_time < ?"
);

BoundStatement bound = byRange.bind(
    tenantId, deviceId, utcDay, fromInclusive, toExclusive
).setPageSize(50);
```

`setPageSize(50)` là mục tiêu số hàng cho mỗi trang của driver, **không phải `LIMIT 50`** của toàn câu truy vấn. Nếu endpoint chỉ trả một trang, cần kiểm soát số hàng đọc và trạng thái paging; lặp toàn bộ `ResultSet` đồng bộ có thể kích hoạt tải thêm các trang.

Ứng dụng phải kiểm tra rằng `fromInclusive < toExclusive` và hai mốc thuộc phạm vi bucket đang đọc. Nếu khoảng vượt ngày, hãy chia theo UTC và đọc các partition liên quan; không truyền một `utcDay` rồi kỳ vọng dữ liệu của ngày kế tiếp xuất hiện.

## 8. Dữ liệu đến muộn, backfill và thay đổi retention

### 8.1. Sự kiện đến muộn

Giả sử hôm nay là 21/11 và thiết bị gửi một sự kiện xảy ra ngày 19/11. Nếu bucket tính từ `event_time`, sự kiện thuộc partition ngày 19; nếu retention theo event time 14 ngày, TTL còn khoảng 12 ngày. Bản ghi đến muộn được chèn vào vị trí clustering theo thời điểm xảy ra, không nhất thiết nằm đầu danh sách mới nhất.

Vì vậy cần hỏi:

- Có cho phép ghi sự kiện đến muộn sau **N ngày** không?
- Đường xử lý có phát lại hàng loạt sau khi thiết bị mất mạng không?
- API cần thể hiện **thứ tự xảy ra** hay **thứ tự tiếp nhận**?
- Đã vượt retention thì bỏ, lưu ở archive hay chuyển sang xử lý điều tra?

Lựa chọn bucket theo `received_at` có thể hợp lý nếu sản phẩm chủ yếu xem sự kiện theo **thời điểm hệ thống nhận**, nhưng đó là **hợp đồng truy vấn khác**. Không đổi nguồn bucket mà vẫn dùng câu `WHERE event_time` như trước và giả định truy vấn một partition sẽ đầy đủ.

### 8.2. Backfill và sửa dữ liệu đã cũ

Backfill có thể ghi vào bucket lịch sử, nhưng **TTL lúc ghi** và **compaction window** có thể không trùng với thời gian xảy ra của sự kiện. Cần thiết kế:

- Hạn mức tốc độ backfill để không đẩy tải ghi tăng đột biến lên replica.
- Cách tính TTL còn lại khi event time cũ.
- Quy tắc định danh để tránh replay tạo nhiều hàng hoặc cập nhật TTL ngoài ý muốn.
- Ảnh hưởng đến compaction, tombstone và các SLA đọc đang chạy.

Nếu cần sửa `event_time` vốn nằm trong primary key, thông thường phải ghi hàng mới đúng khóa và xóa dữ liệu cũ theo quy tắc nghiệp vụ. Thao tác này có thể tạo tombstone; cần xử lý lỗi giữa hai lần ghi và tránh để dữ liệu trùng kéo dài.

### 8.3. Thay đổi thời hạn lưu

Giả sử trước đây sự kiện được giữ 30 ngày, giờ sản phẩm muốn còn 14 ngày. Thay `default_time_to_live` cho bảng **không tự bảo đảm mọi dữ liệu đã ghi trước đó được viết lại TTL mới**. Cần xác định ảnh hưởng đến dữ liệu cũ, cửa sổ thời gian được phép truy vấn, chiến lược xóa và kế hoạch di trú/kiểm thử. Khi tăng retention, dữ liệu **đã hết hạn và bị dọn** không tự quay trở lại.

Các thay đổi retention nên được xem như thay đổi hợp đồng dữ liệu, vì chúng tác động đồng thời tới người dùng, tải lưu trữ và tiến trình bảo trì.

## 9. Khi bucket vẫn quá nóng: thêm shard có kiểm soát

Nếu một thiết bị ghi rất dày ngay cả với bucket giờ, có thể cân nhắc thêm `shard_id` vào partition key để phân tải:

```sql
CREATE TABLE device_events_by_hour_sharded (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

`hour_bucket` phải là mốc đầu giờ UTC đã chuẩn hóa, không phải timestamp tùy ý. Ví dụ `2026-11-21T09:00:00Z` đại diện cho bucket `[09:00, 10:00)`. Có thể gán `shard_id = hash(event_id) mod N` với hàm hash, kiểu dữ liệu và `N` cố định/được phiên bản hóa giữa các producer.

Đổi lại:

- Truy vấn theo một event ID đã biết có thể tính shard nếu biết cách ánh xạ.
- Truy vấn “50 sự kiện gần nhất của thiết bị trong giờ” **không biết trước shard của mọi sự kiện**: ứng dụng cần đọc tới `N` partition rồi hợp nhất theo clustering.
- Tăng `N` mà không có chiến lược version/migration có thể khiến dữ liệu cũ và mới nằm ở hai sơ đồ shard khác nhau.
- Fan-out và số lượt đọc tăng theo `N`; cần đặt giới hạn API và đo độ trễ trên thiết bị nóng nhất.

Sharding là công cụ xử lý tải phân vùng **được đo là quá nóng**; không nên tự thêm khi bucket ngày/giờ đã đáp ứng yêu cầu.

## 10. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Partition chỉ có `device_id` cho toàn bộ lịch sử | Partition tăng không giới hạn | Chọn bucket từ truy vấn và tốc độ sự kiện |
| Chọn bucket ngày cho mọi thiết bị vì “dễ hiểu” | Thiết bị nhiều tải có thể tạo partition lớn/hot | Ước lượng peak rows/bytes theo thiết bị và thử bucket giờ |
| Bucket dựa trên server time nhưng đọc theo event time | Dữ liệu đến muộn nằm sai partition so với truy vấn | Chuẩn hóa một nguồn thời gian cho cả ghi và đọc |
| Tưởng TTL 14 ngày luôn tính từ `event_time` | Sự kiện đến muộn được giữ lâu hơn ý định | Tính TTL còn lại từ `expires_at` nếu chính sách theo event time |
| Tưởng hết TTL là byte trên đĩa biến mất ngay | Dự báo lưu trữ, xóa vật lý và compaction sai | Hiểu tombstone, grace, compaction và đo dung lượng |
| Dùng `LIMIT 50` để bảo đảm truy vấn nhẹ | Có thể quét tombstone hoặc nhiều bucket trước khi trả đủ hàng | Đo tombstone, fan-out và đặt giới hạn khoảng |
| Chọn TWCS chỉ vì dữ liệu có timestamp | Late updates, TTL không đều có thể làm dọn dữ liệu kém hiệu quả | Đánh giá mẫu ghi, TTL và cửa sổ compaction bằng phép đo |
| Giảm `gc_grace_seconds` tùy tiện để dọn nhanh | Có thể tăng nguy cơ resurrection nếu replica bỏ lỡ xóa | Chốt chính sách repair/xóa với vận hành |
| Replay event với ID hoặc TTL mới | Dữ liệu trùng, kéo dài thời hạn sống ngoài ý định | Dùng ID ổn định, quy tắc dedupe và retention cố định |
| Xem một token phân trang là snapshot bất biến | Sự kiện hết hạn/đến thêm làm thay đổi tập đọc | Quy định semantics paging và giới hạn tính nhất quán |

## 11. Checklist trước khi triển khai

| Câu hỏi kiểm tra | Tiêu chí có thể xác minh |
| --- | --- |
| Query shape chủ đạo đã rõ chưa? | Có đầu vào bắt buộc, phạm vi, sort, `LIMIT`/paging, p95/p99 |
| Bucket tính từ thời điểm nào? | Quy tắc UTC, event time/receive time và ranh giới đã ghi thành hợp đồng |
| Bucket đủ nhỏ để tránh partition lớn/hot không? | Có số liệu peak events/s, max rows/bytes và test ở thiết bị lớn nhất |
| Khoảng đọc có giới hạn fan-out không? | API chặn số bucket/ngày và tổng số hàng/byte cần đọc |
| TTL tính từ mốc nào? | Có retention theo event time hoặc write time được công bố rõ |
| Sự kiện cũ hơn retention được xử lý ra sao? | Có quy tắc bỏ/đưa archive/điều tra, không ghi TTL âm hoặc bằng 0 |
| Replay, backfill và sửa event time ra sao? | Có event ID ổn định, dedupe, retry, kiểm soát tải và xử lý đổi key |
| Compaction đã phù hợp chưa? | Có so sánh TWCS với mẫu ghi/TTL, quan sát SSTable và tombstone |
| Repair/xóa có được vận hành an toàn không? | Lịch repair, xử lý replica vắng và `gc_grace_seconds` được xác định |
| Mức nhất quán/replication phù hợp chưa? | Đã kiểm thử node lỗi, đọc sau ghi, latency và ảnh hưởng multi-DC |
| Java/driver có xử lý paging đúng không? | Không tải vô hạn; paging token cùng query shape và quyền tenant |

Trên môi trường kiểm thử, nên tạo các nhóm thiết bị bình thường, thiết bị rất nóng, sự kiện đến muộn, sự kiện trùng timestamp, sự kiện hết hạn và thiết bị mất mạng rồi phát lại. Xác nhận các truy vấn CQL hợp lệ, đo read/write p95/p99, tombstone scanned, kích thước partition và số partition bị chạm. Việc câu CQL chạy được với vài hàng mẫu chưa chứng minh bucket và retention phù hợp trong sản xuất.

## 12. Bài tập áp dụng

Một dịch vụ theo dõi thao tác người dùng lưu các sự kiện:

```text
tenant_id, user_id, event_id, occurred_at, received_at,
event_type, screen_name, payload
```

Yêu cầu nghiệp vụ:

1. Xem 100 sự kiện mới nhất của một user trong **một ngày UTC**.
2. Xem các sự kiện của user trong cửa sổ trượt **6 giờ**.
3. Giữ sự kiện thông thường **7 ngày kể từ `occurred_at`**.
4. Một số điện thoại hoạt động offline có thể gửi sự kiện **muộn 3 ngày**.
5. User lớn nhất có thể ghi 40 sự kiện/giây trong nhiều giờ.

Hãy trả lời:

1. Đề xuất partition key và clustering key cho truy vấn ngày; giải thích vai trò `event_id` khi timestamp trùng.
2. Tính số hàng trong bucket ngày và bucket giờ với tải 40 sự kiện/giây liên tục. Cần đo thêm điều gì trước khi chốt?
3. Một sự kiện xảy ra lúc 12:00 ngày 01/11 nhưng tới server lúc 12:00 ngày 04/11. Nếu retention là 7 ngày theo `occurred_at`, TTL còn bao nhiêu khi ghi?
4. Cửa sổ trượt 6 giờ có thể chạm tối đa mấy bucket giờ? Ứng dụng phải hợp nhất kết quả thế nào?
5. Vì sao `default_time_to_live = 604800` có thể không đáp ứng đúng yêu cầu số 3 nếu dữ liệu đến muộn?
6. Nêu hai tình huống có thể khiến dữ liệu không còn đọc được nhưng vẫn tốn dung lượng trên đĩa.

**Gợi ý đối chiếu:** Với truy vấn theo ngày, một ứng viên là `PRIMARY KEY ((tenant_id, user_id, day_bucket), occurred_at, event_id)` cùng clustering giảm dần; user 40 sự kiện/giây liên tục tạo `3.456.000` hàng/ngày hoặc `144.000` hàng/giờ trước khi xét kích thước hàng. Sự kiện đến muộn 3 ngày còn khoảng **4 ngày TTL** theo chính sách bảy ngày từ `occurred_at`. Một cửa sổ trượt 6 giờ có thể chạm **tối đa bảy bucket giờ**; các partition cần được đọc/hợp nhất theo `occurred_at DESC, event_id DESC` với giới hạn số hàng và paging. TTL mặc định bảy ngày ở lúc ghi sẽ kéo dài thời gian tồn tại tính từ thời điểm sự kiện. Tombstone, dữ liệu hết hạn đang đợi compaction và bản sao SSTable cũ có thể tiếp tục chiếm dung lượng sau khi truy vấn không còn trả các ô hết hạn.

## Kết luận

Thiết kế dữ liệu sự kiện trong Cassandra cần chốt **đường đọc, đơn vị bucket và chính sách retention cùng nhau**. Bucket kiểm soát phạm vi partition và fan-out; clustering key phục vụ thứ tự/điều kiện khoảng; TTL kiểm soát thời gian sống của giá trị, với ngữ nghĩa phụ thuộc thời điểm ghi hoặc TTL được ứng dụng tính từ thời gian sự kiện. Sự kiện đến muộn, replay, tombstone, compaction, repair và các truy vấn qua nhiều bucket phải được đưa vào thiết kế ngay từ đầu. Một phương án đáng tin cậy là phương án có CQL cụ thể, giới hạn API rõ và kết quả đo trên tải dữ liệu đại diện.
