# Kiểm soát collection hoặc chuỗi lịch sử tăng trưởng không giới hạn

## Mục tiêu bài học

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, trong đó thiết kế partition key và clustering column quyết định đường đọc, kích thước partition và cách tải được phân bố giữa các node. Khi lập trình, một giải pháp có vẻ tự nhiên là lưu mọi sự kiện của một đối tượng vào một cột `list` hoặc `map` rồi cập nhật liên tục. Cách khác là dùng một partition chứa toàn bộ lịch sử của đối tượng từ trước đến nay. Cả hai đều có nguy cơ biến dữ liệu **tăng trưởng không có giới hạn** thành điểm nghẽn lâu dài.

Bài thuộc chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung tập trung vào việc nhận diện collection phù hợp, thay collection lịch sử bằng các hàng có khóa và bucket thời gian, giới hạn đường đọc/ghi, áp dụng TTL đúng ngữ nghĩa và vận hành với replication, compaction, repair cũng như ứng dụng Java.

Sau khi hoàn thành bài, bạn có thể:

- Phân biệt `list`, `set`, `map`, `frozen` và **chuỗi hàng có clustering key** trong Cassandra.
- Giải thích vì sao **collection không giới hạn** hoặc **partition lịch sử không bucket** làm tăng chi phí đọc, ghi, xóa, tombstone và rủi ro hot partition.
- Ước tính hàng/byte trong một partition từ lưu lượng đỉnh, kích thước sự kiện và độ rộng bucket.
- Viết CQL lưu sự kiện thành **một hàng cho mỗi sự kiện** với partition key theo đối tượng/bucket và clustering theo thời gian.
- Thiết kế cách xem N sự kiện mới nhất, lọc khoảng, đọc qua nhiều bucket và phân trang mà không quét vô hạn.
- Dùng collection nhỏ có giới hạn cho metadata thích hợp; xử lý replay, TTL, dữ liệu đến muộn và di trú từ collection cũ.

## 1. Hai kiểu tăng trưởng cần nhận diện

Giả sử một hệ thống IoT nhận dữ liệu từ thiết bị. Mỗi sự kiện gồm:

```text
tenant_id, device_id, event_id,
event_time, received_at, event_type, severity, payload
```

Thiết bị có thể phát nhiều sự kiện mỗi giây và tồn tại nhiều năm. Hai kiểu thiết kế dễ gặp:

1. **Một hàng, một collection luôn được bổ sung:** `events list<...>` hoặc `event_ids set<uuid>` tăng theo mỗi sự kiện. Đường đọc có thể phải lấy một cấu trúc rất lớn để hiển thị vài mục.
2. **Nhiều hàng nhưng cùng một partition mãi mãi:** `PRIMARY KEY ((tenant_id, device_id), event_time, event_id)`. Các hàng có trật tự tốt, nhưng tổng số hàng trong partition không có ranh giới tăng trưởng.

Điểm chung: dữ liệu của **một khóa logic** không có cơ chế chia nhỏ hoặc giới hạn đủ rõ. Hash/token phân bố **các partition key khác nhau**, không chia một collection khổng lồ hoặc một partition quá nóng thành nhiều partition độc lập.

### 1.1. Đường đọc quyết định lựa chọn

Ví dụ danh mục truy vấn:

| ID | Nhu cầu | Giá trị caller có | Phạm vi |
| --- | --- | --- | --- |
| Q01 | 50 sự kiện mới nhất của một thiết bị trong giờ UTC | Tenant, device, giờ | Một bucket giờ |
| Q02 | Sự kiện từ 09:20 đến trước 09:40 UTC | Tenant, device, hai mốc | Một khoảng trong giờ |
| Q03 | 50 sự kiện mới nhất của thiết bị trong 6 giờ gần đây | Tenant, device, khoảng | Nhiều bucket có giới hạn |
| Q04 | Hiển thị 5 tag và vài tùy chọn cấu hình thiết bị | Tenant, device | Metadata nhỏ, có giới hạn |
| Q05 | Tra sự kiện chỉ bằng event ID | Tenant, event ID | Đường lookup khác |
| Q06 | Thống kê tất cả sự kiện của tenant trong 1 năm | Tenant, khoảng năm | Phạm vi phân tích rộng |

Q01–Q03 cần **chuỗi lịch sử được sắp theo thời gian**, không phải một cột collection khổng lồ. Q04 lại là ví dụ có thể dùng `set` hoặc `map` nhỏ. Q05 có thể cần bảng tra cứu riêng; Q06 có thể phù hợp kho phân tích/luồng tổng hợp, chứ không phải tải mọi collection hoặc mọi partition về một Java service.

## 2. Collection trong CQL: công cụ cho dữ liệu nhỏ, có ranh giới

Cassandra hỗ trợ các loại collection như `list<T>`, `set<T>` và `map<K,V>`. Chúng thuận tiện khi một hàng chứa **một tập thuộc tính nhỏ có quan hệ chặt với chính hàng đó**.

| Loại | Ngữ nghĩa | Ví dụ phù hợp | Rủi ro khi dùng cho lịch sử |
| --- | --- | --- | --- |
| `list<text>` | Dãy phần tử, có thể trùng; có thứ tự danh sách | Một tập nhỏ bước hướng dẫn do quản trị viên cấu hình | Append liên tục tạo danh sách không giới hạn, thứ tự không tương đương event time |
| `set<text>` | Các giá trị duy nhất theo so sánh kiểu phần tử | Một số tag của thiết bị | Không có thứ tự lịch sử, chỉ độc nhất theo giá trị |
| `map<text,text>` | Ánh xạ key → value | Vài tùy chọn hiển thị | Mỗi event ID làm key khiến map lớn dần |
| `frozen<map<...>>` | Collection được xem như một giá trị đơn trong thao tác cập nhật | Snapshot cấu hình nhỏ được thay nguyên khối | Mỗi thay đổi có thể cần ghi lại toàn collection; không phù hợp tăng trưởng vô hạn |
| Các hàng clustering | Nhiều hàng bên trong một partition xác định | Lịch sử theo thiết bị và giờ/ngày | Vẫn cần giới hạn bằng bucket và đo partition lớn nhất |

Với collection **không frozen**, Cassandra có thể quản lý các phần tử/entry như nhiều cell trong cùng một hàng. Xóa/thay đổi phần tử có thể tạo tombstone. Với `frozen`, collection được xử lý như một giá trị nguyên khối; thay một entry thường đồng nghĩa thay giá trị collection, chứ không tạo ra bảng con có partition độc lập.

**Quan trọng:** collection không phải một bảng con tự chia partition theo phần tử. Đưa hàng triệu phần tử vào một cột không giải quyết bài toán định tuyến, phân bố tải hay đọc một khoảng thời gian.

### 2.1. Ví dụ dùng collection nhỏ hợp lý

```sql
CREATE TABLE device_profiles_by_id (
    tenant_id text,
    device_id uuid,
    display_name text,
    tags set<text>,
    display_settings frozen<map<text, text>>,
    PRIMARY KEY ((tenant_id, device_id))
);

-- Thêm một tag vào set nhỏ.
UPDATE device_profiles_by_id
SET tags = tags + {'indoor'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;

-- Bỏ một tag không còn dùng.
UPDATE device_profiles_by_id
SET tags = tags - {'retired'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;

-- Thay nguyên snapshot settings nhỏ vì đây là frozen map.
UPDATE device_profiles_by_id
SET display_settings = {'unit': 'metric', 'theme': 'dark'}
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;
```

Giả sử sản phẩm quy định tối đa **10 tag** và **8 khóa cấu hình** cho một thiết bị. Đó là **giới hạn nghiệp vụ minh họa**, không phải giới hạn mặc định do Cassandra tự áp đặt. Ứng dụng phải kiểm soát cả các thao tác đồng thời: hai writer cùng thêm phần tử có thể khiến tổng vượt giới hạn nếu mỗi writer chỉ kiểm tra một bản đọc cũ.

Nếu cần kiểm soát quota chính xác dưới cạnh tranh cao, hãy thiết kế cơ chế đồng bộ phù hợp ở lớp nghiệp vụ thay vì giả định việc đọc kích thước set rồi ghi là một transaction nguyên tử. Với dữ liệu cấu hình ít thay đổi, cập nhật theo phiên bản hoặc một writer sở hữu cấu hình có thể đơn giản hơn.

### 2.2. Anti-pattern: dùng collection làm timeline

```sql
-- KHÔNG khuyến nghị cho luồng sự kiện tăng không giới hạn.
CREATE TABLE device_events_bad (
    tenant_id text,
    device_id uuid,
    recent_event_ids list<uuid>,
    PRIMARY KEY ((tenant_id, device_id))
);

-- Tưởng như chỉ thêm một phần tử, nhưng list cứ tăng mãi.
UPDATE device_events_bad
SET recent_event_ids =
    recent_event_ids + [00000000-0000-4000-8000-000000000010]
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001;
```

Những vấn đề xuất hiện:

- **Không có ranh giới tăng trưởng** nếu không có logic dọn dữ liệu rõ ràng.
- Một truy vấn trả collection có thể kéo theo lượng dữ liệu lớn dù UI chỉ cần 20–50 sự kiện gần nhất.
- Thao tác trên list theo vị trí, xóa/chỉnh sửa phần tử có thể có chi phí đọc trước và tạo tombstone tùy cách thực hiện; mutation list dưới retry và ghi đồng thời cần được kiểm soát.
- Danh sách được append không tự bảo đảm đúng **thứ tự `event_time`** nếu thiết bị gửi sự kiện đến muộn hoặc có nhiều producer đồng thời.
- `set<uuid>` có thể loại trùng ID nhưng **không phục vụ thứ tự thời gian**; `map<uuid, payload>` cũng không biến thành đường range scan theo `event_time`.
- `frozen<list<...>>` chỉ chuyển sang ghi/thay nguyên collection, không làm lịch sử mở rộng vô hạn trở thành thiết kế tốt.

Cố duy trì danh sách “mới nhất 50 phần tử” bằng chuỗi **đọc → sửa list → ghi lại** cũng dễ có race giữa các writer: một writer có thể ghi đè kết quả của writer khác. Nếu không thể chứng minh một giới hạn chặt và cách cập nhật an toàn, nên dùng **bảng sự kiện theo hàng** thay vì collection.

## 3. Anti-pattern thứ hai: partition lịch sử không có bucket

Tránh kết luận rằng chỉ cần đổi collection thành nhiều hàng là đủ. Ví dụ:

```sql
-- Có thứ tự thời gian, nhưng một partition/thiết bị tăng mãi.
CREATE TABLE device_events_unbounded (
    tenant_id text,
    device_id uuid,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Bảng này hỗ trợ lấy sự kiện theo thời gian **trong cùng một partition**, nhưng toàn bộ nhiều năm dữ liệu của `(tenant_id, device_id)` thuộc cùng một partition logic. Các hàng không được phân ra thành nhiều partition chỉ vì clustering key có nhiều timestamp.

Replication bảo đảm có các bản sao của partition theo cấu hình keyspace; nó không tự chia partition nóng. Compaction và repair giúp duy trì storage/replica nhưng **không tự sửa khóa phân vùng** thiếu ranh giới.

### 3.1. Ước lượng kích thước từ thiết bị nóng nhất

Giả sử thiết bị bận rộn nhất tạo **20 sự kiện/giây liên tục**, mỗi sự kiện có **600 byte dữ liệu nghiệp vụ thô**:

```text
Một phút:
  20 × 60 = 1.200 sự kiện
  1.200 × 600 B = 720.000 B ≈ 0,72 MB

Một giờ:
  20 × 3.600 = 72.000 sự kiện
  72.000 × 600 B = 43.200.000 B ≈ 43,2 MB

Một ngày:
  20 × 86.400 = 1.728.000 sự kiện
  1.728.000 × 600 B = 1.036.800.000 B ≈ 1,04 GB
```

Đây là phép tính giả định **chưa gồm** partition index, metadata, compression, tombstone, SSTable, compaction, replica và peak burst. Nó **không** xác lập ngưỡng partition an toàn phổ quát; phải đo trên cụm và workload thật.

Nếu retention là 30 ngày nhưng partition key **không có bucket**, dữ liệu đang sống trong cùng partition vẫn có thể đại diện cho hàng chục ngày, chưa kể tombstone và lịch sử lưu trên đĩa đang đợi compaction. **TTL 30 ngày không biến một partition thành 30 partition ngày.**

### 3.2. Độ lớn, độ nóng và số partition phải đọc

| Phương án | Kích thước/tải mỗi partition | Giá của đọc khoảng dài |
| --- | --- | --- |
| Một partition/thiết bị vô hạn | Có nguy cơ tăng rất lớn và tập trung tải | Đọc một partition nhưng có thể quá lớn/tốn tombstone |
| Một partition/thiết bị/ngày | Dữ liệu được chia theo ngày | Đọc 7 ngày cần tối đa 7 partition ngày lịch |
| Một partition/thiết bị/giờ | Giảm dữ liệu mỗi partition so với ngày | Đọc 24 giờ có thể chạm **25 bucket giờ** nếu cửa sổ trượt lệch biên |
| Bucket giờ + shard | Có thể phân tán tải của thiết bị cực nóng | Đọc nhiều shard mỗi giờ và hợp nhất |

**Lưu ý ranh giới:** “7 ngày lịch UTC” đã chọn tương ứng bảy bucket ngày; “cửa sổ trượt đúng 7 × 24 giờ” có thể chạm **tám** bucket ngày. Tương tự một cửa sổ trượt 24 giờ có thể chạm 25 bucket giờ. Dùng khoảng nửa mở `[from, to)` và tính bucket thực tế trước khi đặt giới hạn fan-out.

## 4. Thiết kế bảng sự kiện: một hàng cho mỗi event, partition theo giờ

Với giả định thiết bị nóng có thể ghi hàng chục sự kiện/giây, ta **khảo sát** bucket giờ UTC như một ứng viên. Schema:

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Trong đó:

1. `hour_bucket` là mốc **đầu giờ UTC** lấy từ `event_time`; ví dụ `2026-11-21T09:00:00Z` đại diện cho `[09:00, 10:00)`.
2. Toàn bộ `(tenant_id, device_id, hour_bucket)` là **một composite partition key**; Cassandra dùng tổ hợp để định tuyến partition/token/replica.
3. `event_time` là clustering column đầu tiên, phục vụ sort và lọc khoảng **trong partition**.
4. `event_id` phân biệt sự kiện trùng millisecond. Một UUID ngẫu nhiên cung cấp thứ tự xác định theo giá trị khóa, **không** chứng minh thứ tự nhân quả khi timestamp bằng nhau.
5. `payload` và các regular column khác không mặc nhiên được dùng để lọc/sort hiệu quả ngoài đường truy vấn thiết kế.

```text
Partition: (tenant-A, device-X, 2026-11-21T09:00:00Z)
    (09:59:58.300, id-103) -> ERROR
    (09:40:11.000, id-102) -> WARN
    (09:05:07.900, id-101) -> INFO

Partition: (tenant-A, device-X, 2026-11-21T10:00:00Z)
    (10:00:02.100, id-104) -> INFO
```

Các ID trong hình chỉ là nhãn minh họa. Nếu hai hàng trùng `event_time`, thứ tự thực được Cassandra xác định theo giá trị khóa `uuid` ở cột clustering thứ hai.

### 4.1. Ghi một sự kiện

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, received_at,
    event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

Dấu `?` dành cho prepared statement của driver; `cqlsh` tương tác cần literal CQL tương ứng. Dùng cùng `event_id` và `event_time` khi retry để không tạo một hàng khác khóa. Nếu `event_id` đổi giữa các lần retry, hoặc việc chuẩn hóa giờ không đồng nhất, một sự kiện có thể xuất hiện nhiều lần ở các hàng/partition khác nhau.

**Không được suy ra ID duy nhất toàn hệ thống** chỉ vì nó nằm trong clustering key. Primary key trong bảng này chỉ bảo đảm định danh hàng theo tổ hợp `(tenant, device, hour_bucket, event_time, event_id)`. Tra cứu chỉ bằng `event_id` cần một đường lookup hoặc index khác được kiểm chứng.

### 4.2. Q01: đọc 50 sự kiện mới nhất trong một giờ

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;
```

Đây là một truy vấn **đủ partition key**, kết quả theo clustering `DESC` mặc định. Nó không phải `ORDER BY` tùy ý trên toàn bộ thiết bị hoặc tenant.

### 4.3. Q02: đọc theo khoảng trong một giờ

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

Quy ước `[fromInclusive, toExclusive)` tránh đếm trùng ở ranh giới. Nếu khoảng vượt 10:00 UTC, ứng dụng phải tách phần nằm trong bucket 09:00 và phần trong bucket 10:00. Một giá trị `hour_bucket = 09:00` không tự tìm dữ liệu của partition 10:00.

### 4.4. Q03: đọc 50 sự kiện mới nhất trong 6 giờ

Nếu khoảng `[08:20, 14:20)`, các bucket giờ bắt đầu từ `08:00` đến `14:00`, tổng cộng **7 bucket**. Để lấy N sự kiện mới nhất:

1. Xác định bucket giao với khoảng, có giới hạn tối đa (trong ví dụ là 7).
2. Đọc bucket **mới nhất trước**, với lát thời gian phù hợp và giới hạn số hàng được tải.
3. Hợp nhất theo `(event_time DESC, event_id DESC)` hoặc đọc nối từ bucket mới đến cũ khi các bucket thời gian rời nhau và đã được xác định đúng.
4. Dừng khi đủ N hàng; lưu trạng thái tiếp tục phù hợp nếu UI có “tải thêm”.

Không giả định một `ORDER BY` CQL trên nhiều partition tạo được thứ tự toàn cục với chi phí thấp. Nếu đọc qua **shard** trong cùng bucket, các dải thời gian ở các shard trùng nhau, nên cần **k-way merge** thực sự thay vì chỉ nối các kết quả theo thứ tự shard.

### 4.5. `LIMIT`, paging và giới hạn API khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| `LIMIT 50` | Tổng số hàng tối đa của một câu CQL |
| Page size của driver | Số hàng mục tiêu mỗi lần fetch trang, có thể fetch tiếp |
| Fan-out limit | Số partition/bucket/shard tối đa cho một yêu cầu |
| Resource limit | Số hàng/byte trung gian, thời gian, concurrency và bộ nhớ tối đa |

`LIMIT 50` không tự làm một truy vấn nhẹ nếu partition chứa nhiều tombstone. Với API đọc nhiều bucket, không được tải vô hạn dữ liệu của tất cả bucket rồi mới lấy 50 hàng cuối. Cần đặt cả giới hạn phạm vi và kế hoạch phân trang ngay từ đầu.

## 5. Metadata nhỏ và lịch sử dài nên tách bảng

Một thiết bị có thể có **cấu hình hiện tại** và **chuỗi sự kiện lịch sử**. Hai loại dữ liệu có vòng đời và cách truy cập khác nhau:

| Thuộc tính | `device_profiles_by_id` | `device_events_by_hour` |
| --- | --- | --- |
| Đường đọc | Một thiết bị cụ thể | Một thiết bị và một giờ/khoảng |
| Khóa | `(tenant_id, device_id)` | `(tenant_id, device_id, hour_bucket)` |
| Hình dạng | Một hàng, metadata có giới hạn | Nhiều hàng sự kiện, clustering theo thời gian |
| Thao tác | Đổi tên, thêm/bỏ tag, cập nhật tùy chọn | Append sự kiện, hiếm khi sửa khóa |
| Vòng đời | Theo thời gian sống thiết bị | TTL/retention theo dữ liệu telemetry |

Không đưa hàng nghìn event ID vào `tags` hay `display_settings` chỉ vì cùng liên quan đến thiết bị. Ngược lại, cũng không tạo một hàng lịch sử mới mỗi khi người dùng đổi một setting nhỏ nếu nghiệp vụ chỉ cần **giá trị cấu hình hiện tại**.

Nếu sản phẩm cần **cả lịch sử thay đổi setting**, hãy lưu snapshot hiện tại ở bảng profile và phát thêm một **sự kiện thay đổi cấu hình** vào timeline. Đó là hai đường đọc, cần xử lý đúng khi ghi, retry và đối soát — không phải thêm một collection vô hạn vào hàng profile.

## 6. TTL và retention giúp giới hạn tuổi dữ liệu, không thay thế bucket

Chính sách minh họa: giữ sự kiện **14 ngày tính từ thời điểm xảy ra**. Có thể ghi mỗi event với TTL còn lại:

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, received_at,
    event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

Trong CQL, `TTL` là **số giây kể từ thời điểm ghi**, không tự đọc giá trị `event_time`. Vì thế:

```text
expires_at = event_time + retention_duration
remaining_ttl_seconds = expires_at - now_at_write

remaining_ttl_seconds > 0  -> ghi với TTL còn lại
remaining_ttl_seconds <= 0 -> sự kiện đã hết hạn theo chính sách
```

Nếu retention là **14 ngày** và một event xảy ra 3 ngày trước khi server nhận được, TTL còn khoảng **11 ngày** tại lúc ghi. Nếu dùng TTL cố định 14 ngày cho mọi lần `INSERT`, event đến muộn được giữ gần 17 ngày kể từ `event_time`, lệch hợp đồng retention theo thời điểm xảy ra.

### 6.1. TTL không làm partition nhỏ lại ngay lập tức

TTL làm giá trị hết hạn không còn hiển thị như dữ liệu sống, nhưng Cassandra cần xử lý dấu xóa (**tombstone**) và các bản dữ liệu cũ trong SSTable. Việc thu hồi dung lượng vật lý phụ thuộc compaction, điều kiện an toàn xóa và tình trạng replica. Khi query `LIMIT 50` đi qua nhiều dữ liệu đã hết hạn, nó vẫn có thể tốn công đọc tombstone.

Bucket theo giờ vẫn cần thiết nếu một giờ có lưu lượng rất lớn. Retention 14 ngày chỉ hạn chế **khoảng thời gian sống**, không biến một partition giờ quá nóng thành nhiều partition.

### 6.2. TTL của collection cũng không tạo ranh giới hoàn hảo

Với các collection không frozen, những phần tử/cell có thể có TTL và thao tác cập nhật khác nhau, dẫn đến hết hạn theo những thời điểm khác nhau. Với frozen collection, thao tác thay giá trị có ngữ nghĩa vòng đời của giá trị nguyên khối. Cả hai đều không thay cho một **lịch sử có partition key theo thời gian**.

Nếu ứng dụng liên tục append và ghi lại collection, retry hoặc cập nhật có thể ảnh hưởng thời điểm hết hạn của các ô được ghi. Không cho rằng việc “cứ thêm TTL” sẽ tự tạo một hàng đợi bounded list an toàn, nhất quán và có thứ tự event time.

### 6.3. Repair và compaction

- **Compaction** tổ chức SSTable, xử lý tombstone khi đủ điều kiện; nó không tự chia partition lớn hoặc chuyển collection sang bảng lịch sử.
- **Repair** giúp dữ liệu giữa replica hội tụ theo cơ chế Cassandra; nó không tự sửa event ID do ứng dụng tạo lặp hay bucket tính sai.
- **Replication factor** xác định số bản sao partition theo topology. Nó giúp chịu lỗi nhưng không phân phối **một partition nóng** thành nhiều partition logic.
- **Consistency level** như `LOCAL_QUORUM` trong cấu hình phù hợp quy định số replica xác nhận thao tác; nó không biến phép đọc collection lớn thành một range scan rẻ.
- **`gc_grace_seconds`** liên quan đến an toàn xóa và bảo trì replica. Không giảm tùy tiện chỉ để dọn tombstone sớm, vì có thể tăng nguy cơ dữ liệu cũ xuất hiện lại trong những điều kiện replica chưa đồng bộ.

### 6.4. Khi nào xem xét TWCS?

Với dữ liệu sự kiện phần lớn append-only, TTL khá đồng đều và ít sửa bản ghi cũ, **TimeWindowCompactionStrategy (TWCS)** là một ứng viên có thể đánh giá. Tuy nhiên **cửa sổ compaction** được tổ chức theo timestamp ghi trong storage, **không** theo cột `hour_bucket` trong primary key.

Sự kiện đến muộn, backfill, sửa dữ liệu cũ và trộn nhiều TTL có thể làm chiến lược theo thời gian không dọn SSTable như kỳ vọng. Không chọn TWCS chỉ vì tên bảng có `_by_hour`. Cần so sánh trên workload thật, quan sát tombstone scanned, số SSTable mỗi lượt đọc, độ trễ và tài nguyên compaction.

## 7. Sự kiện đến muộn, replay, sửa khóa và hotspot

### 7.1. Sự kiện đến muộn

Một sự kiện xảy ra lúc `2026-11-20T09:59:59Z` nhưng tới server lúc `2026-11-21T10:00:00Z` vẫn phải vào bucket `2026-11-20T09:00:00Z` nếu key được thiết kế từ **event time**. Nếu một producer tính bucket từ `received_at`, trong khi reader tính từ `event_time`, event sẽ ở sai partition so với đường tìm kiếm.

Thống nhất cả ba quyết định:

- Timestamp nào dùng để **sắp xếp** (`event_time` hay `received_at`)?
- Timestamp nào dùng để **tính bucket**?
- Timestamp nào dùng để **tính retention**?

Chúng có thể khác nhau vì yêu cầu nghiệp vụ, nhưng khi đó mọi API phải hiểu và thực hiện đúng hợp đồng; không được đổi một trường mà giữ giả định cũ ở reader.

### 7.2. Replay và định danh sự kiện

Nếu timeout sau khi Cassandra đã nhận ghi, producer có thể gửi lại. Một quy tắc tốt là giữ nguyên `event_id`, `event_time` và bucket của sự kiện. Ghi lặp cùng toàn bộ primary key là **upsert trên cùng hàng logic**, nhưng không tự đảm bảo mọi chính sách TTL, nội dung cell và thứ tự update đều bất biến.

Nếu cùng event ID xuất hiện với timestamp/bucket khác, bảng lịch sử có thể lưu hai hàng. Khi cần **tính duy nhất của event ID trên toàn tenant**, phải có cơ chế nguồn cấp ID/dedupe hoặc bảng lookup riêng theo `(tenant_id, event_id)` được thiết kế và vận hành phù hợp.

### 7.3. Sửa thời gian đã nằm trong primary key

`event_time` là clustering column; `hour_bucket` là partition key. Cassandra không cho phép thay đổi primary key của một hàng bằng một `UPDATE` thông thường. Muốn sửa thời điểm một sự kiện, thường phải **ghi hàng mới theo khóa mới và xóa hàng ở khóa cũ**. Đây là nhiều mutation, có thể tạo tombstone và cần quy tắc khôi phục nếu thao tác thất bại giữa chừng.

Với hệ thống audit, nên cân nhắc lưu sự kiện điều chỉnh hoặc version bổ sung thay vì âm thầm sửa lịch sử; mức bất biến và chính sách xóa là yêu cầu nghiệp vụ cần chốt.

### 7.4. Shard nếu ngay cả bucket giờ vẫn quá nóng

Nếu đo thấy một thiết bị có tốc độ ghi quá cao trong một giờ, có thể thêm `shard_id` vào partition key:

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

Một thuật toán phân shard ví dụ là `shard_id = hash(event_id) mod N`, với **hàm hash, số shard N và phiên bản quy tắc** đồng nhất ở tất cả writer/reader. Đọc toàn bộ sự kiện một giờ phải đọc **N partition** rồi hợp nhất; không biết ID từng sự kiện thì reader không chọn được duy nhất một shard.

| Thiết kế | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Giờ, không shard | Một partition/thiết bị/giờ, đọc đơn giản | Một thiết bị cực nóng vẫn gây hotspot |
| Giờ + N shard | Chia traffic của một thiết bị/giờ qua N partition | Fan-out N khi đọc toàn bộ giờ, paging/merge phức tạp |
| Bucket ngắn hơn | Giảm số hàng/partition theo thời gian | Tăng số partition cần đọc khoảng dài |
| Kho tìm kiếm/phân tích riêng | Phục vụ filter và aggregate rộng | Thêm chi phí đồng bộ, dữ liệu có thể trễ |

Không mặc định sharding là lựa chọn tốt hơn. Thêm shard khi có số liệu cho thấy cần thiết và khi chi phí đọc fan-out vẫn đáp ứng SLA.

## 8. Java: ghi sự kiện có bucket giờ và TTL, đọc khoảng có giới hạn

Ví dụ dùng **DataStax Java Driver 4.x**. Ứng dụng tạo `hour_bucket` từ `event_time` ở UTC bằng cách cắt đến đầu giờ và tính TTL còn lại cho retention theo event time.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class DeviceEventRepository {
    private static final Duration RETENTION = Duration.ofDays(14);

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insertEvent;
    private final PreparedStatement readHourRange;

    public DeviceEventRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insertEvent = session.prepare(
            "INSERT INTO device_events_by_hour (" +
            "tenant_id, device_id, hour_bucket, event_time, event_id, " +
            "received_at, event_type, severity, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
        this.readHourRange = session.prepare(
            "SELECT event_time, event_id, event_type, severity, payload " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public static Instant hourBucket(Instant eventTime) {
        return eventTime.truncatedTo(ChronoUnit.HOURS); // UTC hour boundary
    }

    // true nếu lệnh ghi hoàn tất theo cấu hình driver; false nếu đã hết hạn.
    public boolean write(
        String tenantId, UUID deviceId, UUID eventId,
        Instant eventTime, Instant receivedAt,
        String eventType, String severity, String payload
    ) {
        Instant expiresAt = eventTime.plus(RETENTION);
        long secondsLeft = Duration.between(clock.instant(), expiresAt).getSeconds();
        if (secondsLeft <= 0) {
            return false;
        }

        int ttlSeconds = Math.toIntExact(secondsLeft);
        BoundStatement statement = insertEvent.bind(
            tenantId, deviceId, hourBucket(eventTime),
            eventTime, eventId, receivedAt,
            eventType, severity, payload, ttlSeconds
        );
        session.execute(statement);
        return true;
    }

    public ResultSet readRangeInsideOneHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Khoang thoi gian khong hop le");
        }
        Instant bucket = hourBucket(fromInclusive);
        if (toExclusive.isAfter(bucket.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Phai chia truy van theo bucket gio");
        }

        return session.execute(
            readHourRange.bind(
                tenantId, deviceId, bucket, fromInclusive, toExclusive
            ).setPageSize(50)
        );
    }
}
```

Các điểm cần hiểu:

1. `Instant` tương ứng kiểu CQL `timestamp`, `UUID` tương ứng `uuid`. `Instant.truncatedTo(HOURS)` tạo ranh giới giờ UTC nhất quán.
2. `TTL ?` là số giây còn lại đến `event_time + 14 ngày` ở lúc chuẩn bị ghi; trường hợp đã hết hạn được xử lý riêng. Đồng hồ ứng dụng/node và thời điểm ghi thực tế có thể làm xuất hiện sai số nhỏ.
3. `Math.toIntExact` làm lộ lỗi nếu TTL vượt phạm vi số nguyên thay vì ép kiểu âm thầm. Ví dụ giả định retention chỉ 14 ngày.
4. Hàm `readRangeInsideOneHour` từ chối khoảng vượt bucket; tầng API phải phân rã khoảng nhiều giờ thành những lời gọi riêng với giới hạn fan-out.
5. `setPageSize(50)` là cỡ trang mục tiêu của driver, **không phải `LIMIT 50` của toàn câu truy vấn**. Nếu lặp hết `ResultSet` đồng bộ, driver có thể tự fetch thêm trang.
6. `true` chỉ báo lời gọi execute hoàn tất không ném lỗi theo cấu hình; nó không bảo đảm dữ liệu đã ở mọi replica hoặc mọi bảng projection khác.

Trong ứng dụng thật phải có kiểm tra quyền tenant, giới hạn kích thước `payload`, idempotency/retry, timeout, backpressure và metric. `CqlSession` nên được dùng chung theo vòng đời dịch vụ thay vì tạo mới cho mỗi sự kiện.

### 8.1. Giới hạn ở tầng API

Ví dụ một hợp đồng đọc:

```text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?from=2026-11-21T08:20:00Z
    &to=2026-11-21T14:20:00Z
    &limit=50
    &cursor=...

Quy tắc server:
  - tenantId lấy/đối chiếu từ ngữ cảnh xác thực
  - max range = 6 giờ
  - max bucket fan-out = 7 (theo thời gian và biên UTC)
  - max page size = 50
  - max concurrent partition reads được cấu hình, có backpressure
  - cursor được ràng buộc với tenant, device, from/to và query shape
```

Một cursor cho nhiều partition cần mô tả tiến trình merge và vị trí từng luồng; không thể dùng bừa paging state của một partition cho toàn bộ fan-out. Khi sự kiện mới được thêm hoặc sự kiện cũ hết TTL, các trang đọc liên tiếp **không tự tạo snapshot bất biến**. Phải công bố semantics phù hợp cho UI.

## 9. Di trú từ collection cũ sang bảng lịch sử có bucket

Nếu một hệ thống đã lưu lịch sử trong `list` hoặc `map` lớn, không nên xóa ngay cột cũ rồi hy vọng đọc từ bảng mới đã đầy đủ. Quá trình di trú phải giải quyết dữ liệu tồn tại và các sự kiện vẫn đang ghi.

Một kế hoạch an toàn về mặt ý tưởng:

1. **Chốt schema mới và quy tắc khóa**: event ID ổn định, bucket theo event time UTC, clustering theo thời gian, retention và chính sách xử lý duplicate.
2. **Chọn nguồn hoàn chỉnh**: durable event log, export hoặc snapshot có thể duyệt. Nếu chỉ có collection cũ, cần đánh giá nguy cơ đọc một giá trị rất lớn; không để API người dùng đọc toàn bộ collection để migrate.
3. **Bảo đảm sự kiện mới không bị mất**: triển khai đường phát/ghi bền vững sang bảng mới, kèm checkpoint và retry; nếu dual-write, phải có cơ chế phát hiện/khôi phục lỗi từng phần.
4. **Backfill có giới hạn**: xử lý theo partition/device nhỏ, kiểm soát QPS, byte và bộ nhớ; sử dụng cùng event ID/bucket và TTL theo chính sách gốc.
5. **Chống dữ liệu cũ ghi đè mới**: nếu có cập nhật/sửa sự kiện, dùng revision hoặc quy tắc version được xác minh; backfill không được ghi nhầm trạng thái cũ sau thay đổi mới.
6. **Đối soát**: so tập event ID, số hàng, timestamp, trường dữ liệu và bucket đại diện; kiểm tra dữ liệu hết TTL không bị tái tạo trái chính sách.
7. **Chuyển dần đường đọc**: canary, so kết quả theo ngày/thiết bị, đo p95/p99, lỗi timeout, độ nóng partition và tombstone.
8. **Dọn mô hình cũ** sau khi xác nhận đủ dữ liệu, không còn consumer phụ thuộc collection và có kế hoạch rollback hợp lý. Xóa collection lớn cũng có chi phí tombstone/compaction cần được vận hành.

**Không nên** làm thao tác “đọc toàn bộ list hàng triệu event → gửi một câu UPDATE lớn” trong một request hoặc một batch xuyên nhiều partition khổng lồ. Phân lô có checkpoint và nguồn dữ liệu có thể khôi phục tốt hơn.

### 9.1. Bất biến khi đối soát

Với mỗi `(tenant_id, device_id, event_id)` hợp lệ trong thời hạn lưu, cần xác minh:

| Bất biến | Cách kiểm |
| --- | --- |
| Một sự kiện có một khóa lịch sử chính xác | Tính bucket từ event time; kiểm tra toàn bộ primary key |
| Không bị nhân đôi do replay hoặc đổi bucket | Dùng event ID ổn định và nguồn/manifest dedupe |
| Các trường cần hiển thị khớp nguồn | So `event_type`, `severity`, `payload`/hash và timestamp |
| Sự kiện hết retention không bị tái tạo | Áp policy khi backfill, không ghi TTL âm hoặc thay tuổi dữ liệu |
| Không thiếu dữ liệu khi chuyển dual-write | So watermark, checkpoint, sự kiện nằm giữa snapshot/live |

Không dựa vào một phép `COUNT(*)` toàn tenant trên Cassandra giao dịch làm công cụ đối soát duy nhất. Có thể cùng số hàng nhưng thiếu một event và trùng một event khác. Tốt hơn là dùng nguồn có thể duyệt và so theo khóa/phiên bản trong các lô có giới hạn.

## 10. Giám sát để biết dữ liệu có đang tăng ngoài kiểm soát?

Một bản thiết kế tốt cần **định nghĩa ranh giới** và đo xem thực tế có vượt ranh giới đó không:

| Chỉ số | Ý nghĩa | Khi vượt dự kiến |
| --- | --- | --- |
| Số phần tử collection lớn nhất | Phát hiện metadata đang trở thành lịch sử trá hình | Chặn thêm, tách bảng hoặc di trú |
| Kích thước hàng/collection đọc về | Chi phí network/heap và serialization | Giảm trường hiển thị, bỏ unbounded list |
| Số hàng và byte ở partition lớn nhất | Đánh giá bucket có đủ nhỏ | Chuyển bucket ngắn hơn hoặc shard có kiểm chứng |
| Tốc độ ghi vào partition nóng nhất | Phát hiện hotspot ngay cả khi dung lượng chưa lớn | Phân tải, giới hạn input, backpressure |
| p95/p99 của đọc một bucket và nhiều bucket | Kiểm tra SLA, fan-out/merge | Giảm phạm vi, tối ưu truy vấn hoặc thêm đường đọc |
| Tombstone scanned và số SSTable mỗi read | Ảnh hưởng của TTL/xóa/compaction | Điều chỉnh mô hình vòng đời, kiểm chứng compaction |
| Lag của event ingestion/replay | Sự kiện đến muộn hoặc pipeline bị nghẽn | Cấp tài nguyên, retry, đối soát |
| Số request bị giới hạn range/fan-out | Người dùng đang cần use case rộng hơn? | Phân loại lại, cân nhắc search/OLAP |
| Lượng dữ liệu hết TTL chưa thu hồi trên đĩa | Dự báo dung lượng và quá trình compaction | Kiểm tra TTL, repair/grace, compaction |

Nếu API cho phép giới hạn mặc định nhưng một số người dùng thường xuyên vượt, không chỉ tăng giới hạn theo cảm tính. Có thể nhu cầu đó thực sự là **truy vấn phân tích**, cần một bảng projection khác hoặc kho tìm kiếm/OLAP.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `list<event>` append mãi vào một row | Collection rất lớn, đọc và cập nhật tốn tài nguyên | Một event = một hàng, có bucket theo thời gian |
| Dùng `set<uuid>` để thay toàn bộ lịch sử | Có ID duy nhất nhưng không có thứ tự event time | Clustering theo thời gian và ID |
| Dùng `frozen<map>` rồi nghĩ có thể truy vấn range từng entry | Toàn collection là một giá trị, không phải partition con | Collection frozen nhỏ hoặc bảng riêng |
| Chuyển từ list sang nhiều hàng nhưng partition key chỉ là device | Partition vẫn tăng vô hạn | Thêm bucket theo truy vấn và tải |
| Chọn ngày cho thiết bị rất nóng mà không tính kích thước | Một partition ngày có thể quá lớn | Đo peak, thử bucket giờ/ngắn hơn |
| Chia bucket rất nhỏ nhưng API vẫn đọc cả năm | Fan-out hàng nghìn partition | Giới hạn range hoặc kho phân tích |
| Tưởng TTL 14 ngày là tự tính từ event time | Event đến muộn có tuổi dữ liệu sai | TTL còn lại từ thời hạn nghiệp vụ |
| Tin `LIMIT 50` đảm bảo đọc 50 cell | Tombstone và dữ liệu hết hạn vẫn tốn chi phí | Đo tombstone, giới hạn partition/range |
| Xóa/sửa nhiều phần tử list như thao tác O(1) chắc chắn | Read-before-write, tombstone, race tùy thao tác | Thiết kế mutation theo khóa hàng và tránh list vô hạn |
| Retry bằng event ID mới | Lịch sử có sự kiện trùng | ID ổn định và quy tắc dedupe |
| Đọc tất cả event rồi sort ở Java | Tốn network/heap và tăng độ trễ | Clustering theo sort, paging và merge có chặn |
| Dựa vào repair/compaction để sửa schema sai | Không thay khóa truy cập hoặc logic event | Thiết kế lại partition/bucket và di trú |
| Giảm `gc_grace_seconds` để “dọn nhanh” | Có thể tăng rủi ro resurrection khi replica lỗi | Lập chính sách repair/xóa cùng vận hành |

## 12. Bài tập thực hành

Một hệ thống giao hàng lưu lịch sử quét mã của kiện hàng. Mỗi bản ghi gồm:

```text
tenant_id, parcel_id, scan_id, scanned_at, received_at,
location_id, status, note
```

Ban đầu nhóm phát triển dùng một hàng `parcels_by_id` với cột `scan_ids list<uuid>` và append mỗi lần quét. Một số kiện hàng được quét rất dày: **30 lần/giây** trong nhiều giờ. Mỗi bản ghi lịch sử giả định có **900 byte dữ liệu thô**. Sản phẩm cần:

1. Xem **30 lần quét gần nhất của kiện hàng trong một giờ UTC**.
2. Xem lịch sử của kiện trong khoảng trượt **2 giờ**.
3. Giữ lịch sử **3 ngày từ `scanned_at`**.
4. Thiết bị cầm tay có thể gửi dữ liệu muộn 1 ngày.
5. Trang hồ sơ kiện chỉ cần 5 tag và trạng thái hiện tại.

**Yêu cầu:**

1. Nêu ít nhất ba lý do `scan_ids list<uuid>` không phù hợp để làm toàn bộ timeline; vì sao đổi thành `set<uuid>` hoặc `frozen<list<uuid>>` vẫn chưa giải quyết yêu cầu sắp theo `scanned_at`?
2. Đề xuất partition key, clustering key và `CREATE TABLE` cho lịch sử theo **bucket giờ UTC**, với `scan_id` phân biệt các sự kiện trùng timestamp.
3. Tính số hàng/byte thô của một bucket **ngày** và bucket **giờ** nếu tải 30 sự kiện/giây duy trì liên tục. Dùng số liệu đó để giải thích đánh đổi.
4. Với khoảng trượt đúng 2 giờ, hỏi tối đa bao nhiêu bucket giờ có thể bị chạm nếu hai đầu lệch ranh giới? Hãy phác thảo cách đọc/merge.
5. Sự kiện xảy ra 1 ngày trước lúc nhận, retention 3 ngày từ `scanned_at`: TTL còn lại khoảng bao nhiêu tại lúc ghi?
6. Nếu màn hình chỉ cần 5 tag cho kiện hàng, collection nào có thể dùng và phải có quy tắc giới hạn gì?
7. Mô tả kế hoạch chuyển dữ liệu từ list cũ sang bảng lịch sử, bao gồm retry, sự kiện trùng, backfill, đối soát và thời điểm dọn cột cũ.

**Gợi ý đối chiếu:** Với giờ UTC, ứng viên là `PRIMARY KEY ((tenant_id, parcel_id, hour_bucket), scanned_at, scan_id)` cùng `CLUSTERING ORDER BY (scanned_at DESC, scan_id DESC)`. Ở tải **30 sự kiện/giây**, một giờ có `108.000` hàng, khoảng `97,2 MB` dữ liệu thô; một ngày có `2.592.000` hàng, khoảng `2.332,8 MB` (xấp xỉ `2,33 GB`). Một khoảng trượt 2 giờ có thể chạm **ba bucket giờ**, cần đọc theo từng bucket và hợp nhất có giới hạn. Sự kiện đến muộn 1 ngày còn khoảng **2 ngày TTL** theo chính sách 3 ngày từ thời điểm xảy ra. Với metadata, `set<text>` nhỏ có giới hạn (ví dụ tối đa 5 tag) là một lựa chọn; lịch sử quét cần các hàng riêng. Chốt bucket cuối cùng bằng phép đo phân vùng/tải thực tế, không chỉ bằng phép tính thô.

## Kết luận

Trong Cassandra, **collection thích hợp cho tập thuộc tính nhỏ, có ranh giới và gắn với một hàng**, không phải nơi chứa chuỗi lịch sử phát sinh vô hạn. Thay collection bằng nhiều hàng chỉ giải quyết một phần vấn đề: partition vẫn phải được chia bằng **bucket hoặc shard phù hợp với đường truy vấn và tải**, clustering key phải phục vụ thứ tự/khoảng, còn API phải giới hạn fan-out, phân trang và byte xử lý. TTL, compaction, repair và replication không thay thế thiết kế khóa; sự kiện đến muộn, replay và tombstone cần được tính vào vận hành. Một giải pháp bền vững là giải pháp có **giới hạn tăng trưởng rõ, CQL cụ thể, cơ chế di trú/đối soát và kết quả đo trên dữ liệu lớn nhất**.
