# Ví dụ mô hình đơn hàng, hoạt động người dùng hoặc dữ liệu thiết bị

## Mục tiêu bài học

Trong Apache Cassandra, câu hỏi trước tiên không phải “một thực thể có bao nhiêu cột?” mà là **“ứng dụng sẽ đọc dữ liệu bằng khóa nào, cần thứ tự nào và đọc tối đa bao nhiêu hàng?”**. Đây là tinh thần của **thiết kế theo truy vấn** (*query-driven design*) trong mô hình wide-column phân tán.

Ba miền nghiệp vụ dưới đây cùng có dữ liệu gắn với thời gian nhưng đòi những thiết kế khác nhau:

- **Đơn hàng:** cần tra cứu trạng thái hiện tại và liệt kê theo khách hàng hoặc hàng đợi xử lý.
- **Hoạt động người dùng:** cần đọc timeline theo người dùng/ngày và đôi khi xem diễn biến của một phiên.
- **Dữ liệu thiết bị:** cần ghi liên tục, đọc khoảng thời gian gần đây, xử lý thiết bị nóng và sự kiện đến muộn.

Bài thuộc chương **Thiết kế theo truy vấn** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Qua ba ví dụ độc lập, chúng ta kết hợp partition key, clustering key, CQL, replication, mức nhất quán đọc/ghi, TTL, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.

Sau bài học, bạn có thể:

1. Viết **hợp đồng truy vấn** trước khi chọn cấu trúc bảng, rồi giải thích được khóa của từng bảng.
2. Thiết kế bảng theo ID, bảng lịch sử theo bucket và bảng projection theo một đường đọc khác.
3. Dự đoán partition lớn/hot, số lượt đọc qua nhiều bucket và chi phí lặp dữ liệu.
4. Xử lý cập nhật trạng thái, sự kiện trùng hoặc đến sai thứ tự mà không nhầm consistency giữa replica với consistency nghiệp vụ giữa các bảng.
5. Viết và gọi các prepared statement CQL từ Java, gồm các kiểu `uuid`, `timestamp` và `date`.
6. Chọn TTL, giới hạn paging, đầu vào để đối soát và phép đo để thẩm định schema trước sản xuất.

## 1. Cùng là dữ liệu có thời gian, vì sao không dùng một mẫu bảng?

Hãy bắt đầu với một bảng so sánh **đường đọc chủ đạo**, không phải định nghĩa entity trong Java:

| Miền | Caller thường biết | Câu hỏi chủ đạo | Partition key ứng viên | Clustering key |
| --- | --- | --- | --- | --- |
| Đơn hàng | Tenant và order ID | Đơn hiện ở trạng thái nào? | `(tenant_id, order_id)` | Không cần khi một đơn là một hàng |
| Đơn hàng | Tenant, customer ID, tháng | 50 đơn gần nhất của khách? | `(tenant_id, customer_id, month_bucket)` | `created_at DESC, order_id DESC` |
| Hoạt động người dùng | Tenant, user ID, ngày | Những hoạt động gần nhất trong ngày? | `(tenant_id, user_id, day_bucket)` | `occurred_at DESC, event_id DESC` |
| Hoạt động người dùng | Tenant và session ID | Hoạt động của một phiên ngắn? | `(tenant_id, session_id)` | `occurred_at ASC, event_id ASC` nếu UI xem tuần tự |
| Dữ liệu thiết bị | Tenant, device ID, giờ | Đọc telemetry trong một giờ? | `(tenant_id, device_id, hour_bucket)` | `event_time DESC, event_id DESC` |
| Cảnh báo thiết bị | Tenant, site ID, ngày, shard | Cảnh báo nghiêm trọng tại site? | `(tenant_id, site_id, day_bucket, shard_id)` | `event_time DESC, event_id DESC` |

Đây là **các ứng viên theo yêu cầu minh họa**, chưa phải những schema phải áp dụng cho mọi hệ thống. Với Cassandra:

- **Partition key** xác định partition logic, ảnh hưởng phân phối token/replica và đường định tuyến của request. Khóa ghép ở dạng `PRIMARY KEY ((a, b, c), d, e)` có nghĩa **`(a,b,c)` cùng tạo một partition key**, còn `d,e` là clustering columns.
- **Clustering columns** xác định thứ tự trong partition và khả năng lọc theo tiền tố/phạm vi phù hợp. Chúng không làm Cassandra tự sắp xếp toàn bộ các partition.
- **Regular columns** lưu dữ liệu trả về nhưng không tự cung cấp một đường tìm kiếm hiệu quả cho các filter tùy ý.
- **Denormalization** là lưu cùng thông tin nghiệp vụ ở các bảng khác nhau để đáp ứng các đường đọc khác nhau. Nó không phải replication factor của Cassandra.

**Quy trình chung cho cả ba ví dụ:**

1. Liệt kê các API và đầu vào chắc chắn có.
2. Ghi rõ số hàng, thứ tự, khoảng thời gian, mức độ mới và SLO.
3. Từ API quan trọng nhất, chọn partition/clustering key có thể định vị trực tiếp.
4. Tính hàng/byte và tốc độ ghi của **partition bận rộn nhất**, không chỉ trung bình.
5. Với API còn lại, chọn fan-out có giới hạn, bảng projection hoặc hệ khác nếu cần.
6. Thiết kế luồng ghi, lỗi và đối soát; sau đó mới benchmark và chốt schema.

## 2. Ví dụ A: mô hình đơn hàng đa tenant

### 2.1. Hợp đồng truy vấn

Giả sử cửa hàng trực tuyến có các request sau:

| Mã | API | Đầu vào bắt buộc | Kết quả |
| --- | --- | --- | --- |
| O01 | Chi tiết một đơn | `tenant_id`, `order_id` | Một đơn hiện tại |
| O02 | Đơn của khách trong tháng | Tenant, customer ID, tháng UTC | Mới nhất trước, tối đa 50 |
| O03 | Hàng đợi `PENDING` được tạo trong ngày | Tenant, status, ngày tạo UTC | Mới nhất trước, tối đa 50 |
| O04 | Danh sách của khách qua ba tháng lịch | Tenant, customer ID, ba tháng | Nhiều partition và hợp nhất có giới hạn |
| O05 | Tìm theo ghi chú/toàn văn và số tiền | Tenant, filter linh hoạt | Cần khảo sát search thay vì gượng ép schema |

O01, O02 và O03 có **ba bộ khóa định vị khác nhau**. Không nên kỳ vọng một bảng đơn hàng duy nhất với `PRIMARY KEY ((tenant_id, order_id))` đồng thời hỗ trợ cả danh sách theo khách và hàng đợi theo status.

### 2.2. Bảng tra cứu đơn theo ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    last_changed_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, current_status,
       total_amount, last_changed_at, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Một tổ hợp `(tenant_id, order_id)` định vị một partition với một hàng tóm tắt. Không cần clustering column vì O01 không yêu cầu nhiều phiên bản của cùng đơn. `revision` là phiên bản nghiệp vụ **do ứng dụng cấp và kiểm soát**, không tự tăng trong Cassandra.

Lưu ý: đặt tenant vào khóa giúp thể hiện không gian dữ liệu của yêu cầu nhưng **không thay thế xác thực/ủy quyền**. Service phải bảo đảm người gọi được phép truy cập tenant đã chọn.

### 2.3. Bảng danh sách đơn theo khách hàng/tháng

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    current_status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, current_status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` có dạng `YYYY-MM`, tính từ `created_at` sau khi chuyển sang UTC, ví dụ `2026-11`. `created_at` đứng trước trong clustering key để đọc gần nhất trước; `order_id` phân biệt những đơn có timestamp tạo trùng nhau.

Nếu O04 hỏi ba tháng, API tính danh sách **ba bucket tháng lịch được phép**, đọc từng partition rồi hợp nhất theo `(created_at DESC, order_id DESC)`. Một câu O02 chỉ trả dữ liệu trong **một tháng**. Nếu sản phẩm định nghĩa “90 ngày trượt” thay vì ba tháng lịch, số bucket tháng cần đọc có thể **lên tới bốn** do ranh giới; phải tính từ khoảng nửa mở `[from, to)` thực tế.

### 2.4. Bảng hàng đợi theo trạng thái và ngày tạo

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    current_status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, current_status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT created_at, order_id, customer_id, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = 'PENDING'
  AND created_day = ?
LIMIT 50;
```

`created_day` là **ngày UTC đơn được tạo**, không phải ngày đơn chuyển sang `PENDING`. O03 có nghĩa “những đơn **được tạo ngày X** hiện đang PENDING”. Nếu sản phẩm hỏi “các đơn chuyển sang PENDING ngày X”, đó là query shape khác, cần dữ liệu thời điểm đổi trạng thái.

Trên bảng này, status là **một phần partition key**, khác với regular column `current_status` của bảng khách hàng. Khi status thay đổi, không thể `UPDATE` trực tiếp một thành phần primary key để di chuyển hàng.

### 2.5. Đường ghi và lỗi khi đổi trạng thái

Khi một đơn mới được tạo, hệ thống cần ghi đủ những projection được chọn. Ví dụ:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, last_changed_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, current_status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Giả sử trạng thái được chấp nhận chuyển từ `PENDING` sang `PAID`. Dòng xử lý nghiệp vụ:

1. Đảm bảo transition hợp lệ và cập nhật **trạng thái nguồn** với revision mới.
2. Cập nhật regular columns `current_status`/`revision` trong bảng khách/tháng.
3. Xóa hàng `PENDING` theo **đầy đủ khóa cũ** của bảng status/day.
4. Ghi hàng `PAID` theo **đầy đủ khóa mới** của bảng status/day.

```sql
-- Xóa hàng đã tồn tại tại partition status cũ.
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

-- Tạo projection tại partition status mới.
INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

**Thứ tự sự kiện là vấn đề riêng:** Nếu transition revision 12 (`PAID`) được áp dụng trước, rồi retry revision 11 (`PENDING`) tới muộn, một consumer ghi vô điều kiện có thể tái tạo hàng PENDING sai. Chỉ có cột `revision` trên bảng không tự khiến Cassandra từ chối dữ liệu phiên bản cũ.

Có thể dùng một nguồn quyết định trạng thái rõ ràng, xử lý tuần tự theo order hoặc **LWT/CAS** khi nghiệp vụ cần điều kiện ở hàng nguồn:

```sql
-- Minh họa cập nhật có điều kiện với hàng nguồn đã tồn tại.
UPDATE orders_by_id
SET current_status = ?, last_changed_at = ?, revision = ?
WHERE tenant_id = ? AND order_id = ?
IF revision = ?;
```

Caller phải kiểm tra kết quả `[applied]` và bảo đảm `nextRevision` hợp lệ. LWT tốn thêm chi phí; nó **không** tự tạo transaction cách ly trên cả ba bảng. Mutation projection cần lấy từ các transition **đã được chấp nhận**, với sự kiện bền vững, retry, xử lý thứ tự và đối soát.

**Logged batch** có thể giúp một nhóm mutation cuối cùng cùng được áp dụng theo ngữ nghĩa batch khi xử lý lỗi, nhưng **không cung cấp cách ly quan sát như transaction SQL xuyên partition**. Không dùng batch để thay thế kiểm soát revision hoặc làm mẹo tăng throughput với nhiều partition.

### 2.6. Hot partition trong bảng status/day

Giả sử một tenant tạo **300.000 đơn/ngày** và tại một thời điểm 40% số đơn trong bucket đó là `PENDING`:

```text
Số hàng PENDING ≈ 300.000 × 40% = 120.000 hàng
Nếu ước tính 350 B/hàng dữ liệu nghiệp vụ thô:
    120.000 × 350 = 42.000.000 B ≈ 42 MB
```

Đây là giả định **chưa gồm overhead, tombstone, compression, replication và tải cập nhật**; không phải ngưỡng partition an toàn. Phải đo kích thước và QPS của tenant lớn nhất, số lần status chuyển đổi và độ trễ p95/p99.

Nếu một partition `(tenant, PENDING, created_day)` quá nóng, cân nhắc thêm `shard_id` ổn định theo `order_id` và đọc/merge một số shard hữu hạn. Việc thêm shard giảm tải trên mỗi partition nhưng tăng fan-out; không làm tổng dữ liệu nhỏ lại.

## 3. Ví dụ B: hoạt động người dùng theo thời gian

### 3.1. Khác đơn hàng ở điểm nào?

Một sự kiện hoạt động (mở trang, nhấn nút, bắt đầu phiên, xác thực, đổi cài đặt) là **một quan sát đã xảy ra**, không phải chỉ một trường trạng thái cuối của đối tượng. Nếu muốn truy tìm hành trình người dùng, phải lưu nhiều sự kiện thành nhiều hàng.

Ví dụ một event:

```text
tenant_id      = "tenant-A"
user_id        = user-42
session_id     = session-007
event_id       = event-e1
occurred_at    = 2026-11-21T09:15:20Z
received_at    = 2026-11-21T09:15:23Z
event_type     = "PAGE_VIEW"
page_name      = "checkout"
```

Các ID trong sơ đồ là nhãn mô tả, không phải UUID literal để dán vào CQL.

| Mã | Hành vi | Input | Yêu cầu |
| --- | --- | --- | --- |
| U01 | 100 sự kiện gần nhất của user trong một ngày | Tenant, user ID, ngày UTC | `occurred_at DESC` |
| U02 | Sự kiện trong khoảng giờ của cùng ngày | Tenant, user ID, ngày, `from/to` | Lọc theo clustering |
| U03 | Hành trình của một session | Tenant, session ID | Thứ tự `occurred_at ASC` |
| U04 | Hoạt động của user trong bảy ngày lịch | Tenant, user ID, các ngày | Đọc nhiều bucket có giới hạn |
| U05 | Thống kê funnel của một triệu user trong tháng | Tenant, cohort, tháng | Đường phân tích, không phải đọc timeline từng user |

U01 và U03 có **partition key khác nhau**. U04 có thể đọc nhiều partition theo ngày rồi hợp nhất; U05 thường nên được chuyển sang pipeline phân tích hoặc các aggregate đã chuẩn bị riêng.

### 3.2. Bảng timeline theo user/ngày

```sql
CREATE TABLE user_activity_by_day (
    tenant_id text,
    user_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    session_id uuid,
    received_at timestamp,
    event_type text,
    page_name text,
    payload text,
    PRIMARY KEY ((tenant_id, user_id, day_bucket),
                 occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Tại sao chọn như vậy?

- `(tenant_id, user_id, day_bucket)` định vị timeline một người trong một ngày.
- `occurred_at DESC` phục vụ màn hình “mới nhất trước”.
- `event_id` phân biệt sự kiện có timestamp bằng nhau. Thứ tự UUID khi trùng timestamp là thứ tự khóa, không phải bảo đảm thứ tự nhân quả.
- `session_id`, `event_type` và `page_name` là regular columns, không tự biến bảng thành đường tìm kiếm mọi session hoặc mọi event type.

U01:

```sql
SELECT occurred_at, event_id, session_id, event_type, page_name
FROM user_activity_by_day
WHERE tenant_id = ?
  AND user_id = ?
  AND day_bucket = ?
LIMIT 100;
```

U02 với khoảng nửa mở:

```sql
SELECT occurred_at, event_id, event_type, page_name
FROM user_activity_by_day
WHERE tenant_id = ?
  AND user_id = ?
  AND day_bucket = ?
  AND occurred_at >= ?
  AND occurred_at < ?;
```

Tầng dịch vụ phải xác định `[fromInclusive, toExclusive)` có nằm trong ngày được yêu cầu hay không. Nếu khoảng qua 00:00 UTC, tính thêm bucket ngày kế tiếp và đọc hai partition tương ứng, không dùng một `day_bucket` cho cả hai ngày.

### 3.3. Bảng theo session nếu U03 là đường đọc quan trọng

Nếu ứng dụng có phiên ngắn, có số event tối đa được quy định, và support thường hỏi toàn bộ hành trình của một phiên, có thể thêm:

```sql
CREATE TABLE user_activity_by_session (
    tenant_id text,
    session_id uuid,
    occurred_at timestamp,
    event_id uuid,
    user_id uuid,
    event_type text,
    page_name text,
    PRIMARY KEY ((tenant_id, session_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);

SELECT occurred_at, event_id, user_id, event_type, page_name
FROM user_activity_by_session
WHERE tenant_id = ? AND session_id = ?;
```

U03 định vị theo session ID, clustering **tăng dần** để tái hiện hành trình từ đầu đến cuối. Nhưng nếu phiên tồn tại hàng tuần hoặc có sự kiện khổng lồ, `(tenant_id, session_id)` vẫn có nguy cơ trở thành partition không giới hạn. Khi ấy cần bucket theo session và/hoặc thời gian, cùng hợp đồng đọc cụ thể.

Tạo bảng session nghĩa là **mỗi event có thêm một lần ghi** và một vòng đời dữ liệu khác cần duy trì. Nếu U03 rất hiếm và caller đã biết user ID/ngày, có thể cân nhắc đọc vài bucket đã biết rồi lọc/ghép có chặn trước khi thêm projection.

### 3.4. Retention, sự kiện đến muộn và quyền riêng tư

Giả sử chính sách giữ hành vi **30 ngày tính từ lúc sự kiện xảy ra**, nhưng điện thoại có thể offline và gửi muộn. Một `INSERT` vào bảng user/day có thể dùng TTL được tính bởi ứng dụng:

```sql
INSERT INTO user_activity_by_day (
    tenant_id, user_id, day_bucket, occurred_at, event_id,
    session_id, received_at, event_type, page_name, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

`TTL` của Cassandra là **số giây kể từ khi ghi**, không tự đọc `occurred_at`. Nếu event xảy ra cách đây 5 ngày nhưng mới nhận, TTL còn khoảng 25 ngày theo hợp đồng 30 ngày từ event time. Nếu TTL còn `<= 0`, đừng truyền `TTL 0` rồi giả định nó xóa ngay; ứng dụng cần xử lý dữ liệu quá hạn theo chính sách, chẳng hạn không ghi hoặc chuyển vào luồng đối soát được phê duyệt.

Nếu bảng session cũng lưu cùng sự kiện, phải chọn chính sách giữ dữ liệu tương ứng và truyền sự kiện xóa/ẩn theo yêu cầu. Khi có dữ liệu cá nhân, `payload` phải được tối thiểu hóa; việc giữ thêm projection, backup hoặc export có thể tạo thêm nơi cần quản lý quyền và retention.

**TTL không phải xóa vật lý tức thì.** Ô hết hạn có thể để lại tombstone và SSTable cũ chờ compaction. Repair đồng bộ replica theo cơ chế Cassandra; nó không sửa được sự kiện không được ghi vào bảng session do một consumer thất bại.

### 3.5. Đánh giá tải của user nóng nhất

Giả sử một tài khoản tự động tạo **12 event/giây liên tục**, payload trung bình khoảng **500 B dữ liệu thô**:

```text
Một giờ: 12 × 3.600 = 43.200 event
          43.200 × 500 B = 21,6 MB dữ liệu thô

Một ngày: 12 × 86.400 = 1.036.800 event
           1.036.800 × 500 B = 518,4 MB dữ liệu thô
```

Với account như vậy, **bucket ngày** có thể cần được đánh giá lại thành bucket giờ, nhưng khi đó U01 đọc cả ngày phải thăm dò tối đa 24 partition giờ. Hãy đo partition lớn nhất, tombstone scanned và p95/p99; không có một ngưỡng MB phổ quát kết luận mô hình nào an toàn.

Ngoài ra, một cửa sổ trượt đúng 24 giờ có thể chạm **25 bucket giờ** nếu hai đầu không trùng biên giờ. Phải tính số bucket giao với khoảng `[from, to)`, không lấy độ dài giờ làm số partition theo cảm tính.

## 4. Ví dụ C: telemetry và cảnh báo của thiết bị

### 4.1. Khác activity log ở điểm nào?

Dữ liệu thiết bị thường có:

- Tốc độ ghi liên tục, có thể có đỉnh rất cao trên **một thiết bị**.
- Sự kiện đến muộn khi gateway mất mạng, hoặc phát lại hàng loạt sau khi kết nối phục hồi.
- Retention khác nhau giữa telemetry thông thường và cảnh báo nghiêm trọng.
- Hai màn hình rất khác: đồ thị của **một thiết bị** và danh sách cảnh báo tại **một site**.

Ví dụ input:

```text
tenant_id, site_id, device_id, event_id,
event_time, received_at, metric_name, metric_value,
severity, payload
```

| Mã | Truy vấn | Input | Đường đọc |
| --- | --- | --- | --- |
| D01 | 50 sự kiện gần nhất của thiết bị trong một giờ | Tenant, device ID, giờ UTC | Một partition theo device/hour |
| D02 | Giá trị trong khoảng `[09:10,09:40)` của giờ | Tenant, device ID, giờ, from/to | Clustering range |
| D03 | Sự kiện thiết bị trong sáu giờ trượt | Tenant, device ID, khoảng | Nhiều bucket có giới hạn |
| D04 | Các cảnh báo `CRITICAL` tại site trong một ngày | Tenant, site ID, ngày | Projection riêng hoặc công cụ giám sát |
| D05 | So sánh xu hướng mọi site trong hai năm | Tenant, nhiều chiều | Kho phân tích/OLAP |

### 4.2. Bảng dữ liệu theo thiết bị/giờ

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    metric_name text,
    metric_value double,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

`hour_bucket` là mốc **đầu giờ UTC của `event_time`**, ví dụ `2026-11-21T09:00:00Z` cho khoảng `[09:00,10:00)`. Nó phải được tính nhất quán ở mọi writer và reader.

Hai câu CQL cho D01–D02:

```sql
SELECT event_time, event_id, metric_name, metric_value, severity
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;

SELECT event_time, event_id, metric_name, metric_value
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

Truy vấn D02 chỉ đọc khoảng trong một partition giờ; nếu khoảng vượt đầu giờ, tầng ứng dụng phải chia thành nhiều truy vấn theo bucket. `LIMIT 50` là giới hạn số hàng **trả về**, không phải bảo đảm chỉ quét 50 cell vật lý, đặc biệt khi có tombstone/TTL.

### 4.3. Telemetry nóng: kiểm tra giờ và shard

Giả sử thiết bị nóng nhất ghi **40 event/giây** liên tục, kích thước dữ liệu thô trung bình **650 B/event**:

| Phạm vi | Số event | Dữ liệu thô ước tính |
| --- | ---: | ---: |
| Một phút | 2.400 | 1,56 MB |
| Một giờ | 144.000 | 93,6 MB |
| Một ngày | 3.456.000 | 2.246,4 MB (~2,25 GB) |

Đây không phải số byte SSTable. Compression, metadata, partition/index, tombstone, compaction và replication làm dung lượng thực tế khác đi. Bucket giờ chỉ là một **ứng viên cần benchmark**. Một thiết bị cực nóng vẫn có thể tạo hotspot trên một partition giờ; khi đo thấy không đạt SLA, có thể chia thành bucket ngắn hơn hoặc thêm shard:

```sql
CREATE TABLE device_events_by_hour_sharded (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    metric_name text,
    metric_value double,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Quy tắc ví dụ `shard_id = hash(event_id) mod N` phải dùng hàm hash, `N` và version nhất quán giữa các writer. Nếu `N=8`, D01 cần đọc **tám partition**, rồi merge theo `(event_time DESC, event_id DESC)` để lấy 50 hàng mới nhất. Một paging state của **một shard** không đại diện cho trạng thái phân trang của cả tám shard.

Không tự shard khi dữ liệu chưa chứng minh hotspot, vì chi phí fan-out/paging có thể lớn hơn lợi ích.

### 4.4. Projection theo site để hiển thị cảnh báo

D04 yêu cầu “tất cả cảnh báo `CRITICAL` tại một site trong ngày”. Bảng `device_events_by_hour` tổ chức theo **device ID**; chỉ biết site không xác định được danh sách partition của từng device.

Nếu D04 là màn hình quan trọng, có thể tạo projection chỉ ghi event **CRITICAL** và chia 8 shard cho site nhiều tải:

```sql
CREATE TABLE critical_device_events_by_site_day (
    tenant_id text,
    site_id uuid,
    day_bucket date,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    device_id uuid,
    metric_name text,
    metric_value double,
    PRIMARY KEY ((tenant_id, site_id, day_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Khi nguồn nhận event CRITICAL, ứng dụng/pipeline ghi event vào bảng device/hour **và** bảng site/day với `shard_id` tính ổn định theo event ID. Reader D04 đọc tối đa tám shard của site/ngày và hợp nhất; nếu site nhỏ, có thể khảo sát thiết kế không shard.

Những yêu cầu phải được định nghĩa:

1. `site_id` trong event là **site của thiết bị tại thời điểm sự kiện** hay site hiện tại? Khi thiết bị chuyển site, có di chuyển lịch sử hay không?
2. Nếu severity được sửa từ `CRITICAL` sang `WARN`, bản ghi ở projection CRITICAL có bị xóa không?
3. Nếu projection ghi thất bại còn bảng device/hour đã ghi, làm thế nào **retry và đối soát**?
4. Retention của cảnh báo có dài hơn telemetry bình thường không? Nếu có, phải quản lý TTL của từng biểu diễn.
5. Tải lớn nhất là bao nhiêu event/s trên một site, và giới hạn fan-out có phù hợp với SLA?

**Trùng event ID trong toàn bộ site/day** không được Cassandra tự ngăn nếu clustering gồm `event_time` và key khác; phải giữ khóa ổn định khi retry hoặc có cơ chế dedupe ở nguồn.

### 4.5. TTL theo thời gian sự kiện

Giả sử telemetry thường giữ **7 ngày kể từ `event_time`**. Với thiết bị offline, cố định `USING TTL 604800` ở lúc nhận **sẽ giữ event đến muộn lâu hơn 7 ngày tính từ lúc xảy ra**.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket,
    event_time, event_id, site_id, received_at,
    metric_name, metric_value, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

Quy tắc trong ứng dụng:

```text
expires_at = event_time + 7 ngày
seconds_left = expires_at - current_write_time

seconds_left > 0  -> INSERT USING TTL seconds_left
seconds_left <= 0 -> áp chính sách với sự kiện đã quá hạn
```

Ví dụ event đến muộn hai ngày chỉ còn khoảng **năm ngày TTL**. TTL tính bằng giây, có giới hạn của Cassandra và sai số đồng hồ; cần kiểm tra miền giá trị hợp lệ, không truyền 0/âm và không coi TTL là thời gian xóa vật lý chắc chắn.

Sự kiện `CRITICAL` có thể giữ 30 ngày trong projection riêng theo policy, nhưng nếu bảng device/hour chỉ giữ 7 ngày thì sau 7 ngày **không thể mặc định đọc chi tiết cũ từ bảng telemetry**. Projection CRITICAL phải chứa các trường cần hiển thị hoặc có đường archive thích hợp.

## 5. Đặt ba ví dụ cạnh nhau: khác nhau ở đường đọc và đường ghi

| Tiêu chí | Đơn hàng | Hoạt động người dùng | Dữ liệu thiết bị |
| --- | --- | --- | --- |
| Giá trị trung tâm | Trạng thái hiện tại và các danh sách | Chuỗi event theo người dùng/phiên | Chuỗi event theo thiết bị/site |
| Khóa định vị chính | `(tenant,order_id)` hoặc `(tenant,customer,month)` | `(tenant,user,day)` | `(tenant,device,hour)` |
| Clustering | `created_at` của danh sách | `occurred_at` của event | `event_time` của telemetry |
| Cần projection khi | Đọc theo status/ngày | Đọc theo session mà không biết user/ngày | Đọc cảnh báo theo site thay vì device |
| Dạng mutation khó | Status thay đổi làm di chuyển khóa projection | Event trùng, đến muộn, xóa theo quyền riêng tư | Ingest đỉnh, replay sau offline, TTL khác giữa bảng |
| Nguy cơ chính | Partition status/day quá nóng, trạng thái sai giữa bảng | Partition timeline của user tự động quá lớn | Partition device/hour nóng, site alert fan-out |
| Retention | Theo vòng đời đơn/hồ sơ | Theo chính sách hoạt động/người dùng | Thường theo loại telemetry/cảnh báo |
| Đọc rộng toàn tenant | Có thể cần search | Funnel/cohort cần analytics | Xu hướng dài hạn cần analytics/OLAP |

Không có quy tắc “mọi đối tượng có thời gian đều dùng bucket ngày”. Chọn **bucket** theo giao giữa query shape và tải lớn nhất; chọn **projection** theo truy vấn có giá trị; chọn **retention** theo yêu cầu nghiệp vụ. Một schema hợp lý trong miền này không thể tự bê sang miền kia mà không xem lại các giả định.

## 6. Cách đánh giá chi phí của ba mô hình

### 6.1. Hàng/byte của partition lớn nhất

Một ước lượng thô:

```text
rows_per_bucket ≈ max_events_per_second_for_key × bucket_seconds
raw_bytes_per_bucket ≈ rows_per_bucket × average_raw_row_bytes
```

Với đơn hàng, `max_events_per_second_for_key` có thể là số đơn mới của **tenant trong một status/ngày**. Với hoạt động người dùng, đó là **user bận rộn nhất**. Với telemetry, đó là **device** hoặc **site** nóng nhất.

Chỉ tính trung bình toàn cluster có thể bỏ sót một tenant, user tự động hoặc device đột biến. Đồng thời, một bucket nhỏ làm số partition phải đọc cho cửa sổ dài tăng lên; luôn đo **cả write hotspot và read fan-out**.

### 6.2. Chi phí ghi nhiều bảng

Ví dụ một order mới ghi vào ba bảng: ít nhất ba mutation logic. Nếu một lần đổi status cần cập nhật hàng nguồn và danh sách, xóa status cũ và ghi status mới, kịch bản ấy có thể có bốn mutation logic — **chưa tính retry, audit/event log hoặc index**.

Một user event được lưu đồng thời ở bảng user/day và session: ít nhất hai mutation. Một CRITICAL telemetry event ghi vào bảng device/hour và site/day: ít nhất hai mutation. Đây là **các phép đếm theo sơ đồ ví dụ**, không phải định mức Cassandra cho mọi hệ thống.

Replication factor `RF=3` có thể khiến mỗi mutation được nhân bản tới ba replica trong DC theo topology. Nhưng phép nhân `logic mutations × 3` chỉ là ước lượng sơ bộ số lượt áp dụng ở replica, **không phải tổng I/O đĩa**: còn commit log, memtable, SSTable, compaction, batchlog, repair, retries và compression.

### 6.3. Số byte trên đĩa không bằng raw JSON

```text
logical_payload_bytes ≈ live_rows × raw_bytes_per_row
base_table_one_replica ≈ live_rows × measured_disk_bytes_per_live_row
replicated_base ≈ base_table_one_replica × RF
cluster_provisioned ≈ modeled_used_bytes / target_utilization
```

`measured_disk_bytes_per_live_row` phải đo trên schema, data distribution, compaction và TTL đại diện; không dùng một hệ số overhead cố định để áp cho mọi bảng. Nếu có secondary index, SAI hoặc projection, tính đúng phạm vi mỗi cấu trúc và tránh cộng trùng bytes đã nằm trong số đo.

Thời điểm TTL kết thúc cũng **không** là thời điểm SSTable được thu hồi ngay. Tombstone, dữ liệu ghi đè cũ và compaction backlog có thể làm dung lượng tạm thời cao hơn lượng dữ liệu đang sống. Cụm cần headroom cho compaction, repair, rebuild/streaming, snapshot và các đợt backfill.

### 6.4. Khi nào giữ fan-out thay vì tạo thêm bảng?

| Truy vấn phụ | Giải pháp thường đáng đánh giá |
| --- | --- |
| Lịch sử một customer trong 2–3 tháng đã biết | Đọc 2–3 partition khách/tháng rồi hợp nhất có giới hạn |
| Hoạt động một user trong 2 ngày đã biết | Đọc 2 partition user/day, giới hạn byte và paging |
| Telemetry một device trong 6 giờ | Đọc các bucket giờ giao khoảng, tối đa khoảng 7 nếu lệch biên |
| Tìm đơn theo từ khóa và nhiều filter tùy ý | Hệ tìm kiếm có index, không thăm dò mọi customer partition |
| Thống kê hàng năm trên toàn tenant hoặc toàn site | OLAP/warehouse hoặc pipeline tổng hợp |

**Bảy bucket giờ cho một khoảng trượt sáu giờ** là trường hợp thường xảy ra khi hai đầu không khớp biên. API phải tính số bucket bằng khoảng nửa mở `[from, to)`, không dùng một số cố định không xét timestamp cụ thể.

## 7. Java Driver 4.x: ba kiểu truy vấn, ba prepared statement

Đoạn Java minh họa đường **đọc** của ba miền. Nó giả định ứng dụng đã tạo các bảng CQL như trên và có một `CqlSession` được quản lý theo vòng đời dịch vụ (không tạo lại cho từng HTTP request).

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class QueryDrivenExamples {
    private final CqlSession session;
    private final PreparedStatement orderById;
    private final PreparedStatement activityByDay;
    private final PreparedStatement deviceByHourRange;

    public QueryDrivenExamples(CqlSession session) {
        this.session = session;
        this.orderById = session.prepare(
            "SELECT customer_id, created_at, current_status, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.activityByDay = session.prepare(
            "SELECT occurred_at, event_id, session_id, event_type, page_name " +
            "FROM user_activity_by_day " +
            "WHERE tenant_id = ? AND user_id = ? AND day_bucket = ? " +
            "LIMIT 100"
        );
        this.deviceByHourRange = session.prepare(
            "SELECT event_time, event_id, metric_name, metric_value " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public Row findOrder(String tenantId, UUID orderId) {
        return session.execute(orderById.bind(tenantId, orderId)).one();
    }

    public ResultSet latestUserActivity(
        String tenantId, UUID userId, LocalDate utcDay
    ) {
        return session.execute(
            activityByDay.bind(tenantId, userId, utcDay)
        );
    }

    public ResultSet deviceRangeInsideHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }
        Instant hour = fromInclusive.truncatedTo(ChronoUnit.HOURS);
        if (toExclusive.isAfter(hour.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Split into hourly buckets");
        }
        BoundStatement bound = deviceByHourRange
            .bind(tenantId, deviceId, hour, fromInclusive, toExclusive)
            .setPageSize(50);
        return session.execute(bound);
    }

    public static LocalDate utcDay(Instant timestamp) {
        return timestamp.atZone(ZoneOffset.UTC).toLocalDate();
    }

    public static String utcMonth(Instant timestamp) {
        return YearMonth.from(timestamp.atZone(ZoneOffset.UTC)).toString();
    }
}
```

Điểm cần kiểm tra khi chuyển mã thành API sản xuất:

1. `tenantId` phải được xác thực và kiểm tra quyền truy cập; composite key chứa tenant **không tự phân quyền**.
2. `UUID` ánh xạ `uuid`, `Instant` ánh xạ `timestamp` và `LocalDate` ánh xạ `date` trong driver. `YearMonth` chỉ được dùng để tạo chuỗi bucket `YYYY-MM` **sau khi đã chuyển UTC**.
3. Mỗi prepared statement ràng buộc đủ **partition key**; `deviceRangeInsideHour` từ chối khoảng vượt đầu giờ thay vì âm thầm trả dữ liệu thiếu.
4. `LIMIT 100` ở activity query giới hạn **tổng hàng của câu truy vấn**. `setPageSize(50)` ở device range là kích thước trang mục tiêu, không phải `LIMIT 50`. Driver có thể tự fetch thêm khi lặp hết `ResultSet`.
5. Với API tải nhiều trang, nên dùng query không cố định một `LIMIT` preview, kiểm soát số hàng tiêu thụ và paging state opaque theo đúng query shape/bind values; không tái sử dụng cursor cho tenant/bucket khác.
6. Với fan-out nhiều bucket hoặc shard, service phải quản lý vị trí từng luồng và hợp nhất thứ tự; một paging state từ một truy vấn đơn không đủ mô tả toàn bộ tiến trình.
7. Cần timeout, consistency level, concurrency limit, backpressure, kiểm tra kích thước payload và phân loại retry an toàn cho cả đọc/ghi.

## 8. Lỗi, replication, consistency và công tác vận hành

### 8.1. Nhất quán của replica khác đồng bộ các projection

Cassandra duy trì các replica theo replication factor và placement của keyspace. Với topology phù hợp, mức như `LOCAL_QUORUM` cho đọc/ghi có thể là lựa chọn cho một số yêu cầu đọc sau ghi trên **cùng dữ liệu**, tùy RF, datacenter và lỗi được chấp nhận.

Nhưng nếu ứng dụng đã ghi `orders_by_id` mà chưa cập nhật `orders_by_status_day`, hoặc đã ghi `device_events_by_hour` nhưng consumer chưa ghi projection cảnh báo, việc tăng consistency level khi đọc bảng phụ **không thể tạo ra mutation còn thiếu**. Đó là sai lệch **giữa các bảng nghiệp vụ**, cần retry, event log và đối soát.

### 8.2. Bảng theo thời gian, TTL và tombstone

Đối với user activity và telemetry:

- TTL theo write time phù hợp khi retention tính từ lúc nhận/ghi; TTL theo event time cần tính **thời gian còn lại** khi ghi.
- Event đến muộn phải được đưa về bucket tính từ **timestamp đã chọn trong hợp đồng**, không tự dùng thời điểm server hiện tại.
- Ghi lại một event với TTL mới có thể thay đổi thời điểm hết hạn của các ô được ghi; idempotency cần xét cả key, payload, timestamp và policy.
- Tombstone và SSTable cũ có thể tồn tại sau khi giá trị không còn được trả về; `LIMIT` không đảm bảo số cell vật lý phải đọc.

Với bảng time-series chủ yếu append-only và TTL khá đồng nhất, **TimeWindowCompactionStrategy (TWCS)** có thể được đưa vào benchmark. Nhưng cửa sổ TWCS dựa trên timestamp ghi trong storage, **không tự lấy từ `day_bucket` hay `hour_bucket`**. Backfill, sửa dữ liệu cũ hoặc TTL khác nhau có thể làm compaction không thu hồi dữ liệu theo cửa sổ như kỳ vọng.

**Repair** đồng bộ dữ liệu giữa replica theo cơ chế Cassandra; nó không sửa logic partition key hoặc phát hiện projection nghiệp vụ bị bỏ ghi. Không giảm `gc_grace_seconds` tùy tiện chỉ để dọn tombstone nhanh, vì an toàn xóa liên quan đến node mất kết nối và lịch repair.

### 8.3. Ma trận lỗi theo ba miền

| Miền | Tình huống lỗi | Triệu chứng | Cách thiết kế khắc phục |
| --- | --- | --- | --- |
| Đơn hàng | Update source thành PAID, xóa hàng PENDING thất bại | Một đơn còn trong hàng đợi cũ | Retry bằng khóa cũ, durable event, reconcile |
| Đơn hàng | Revision cũ đến sau revision mới | Trạng thái có thể bị ghi lùi | CAS/sequence theo order, bỏ update lỗi thời |
| Hoạt động người dùng | Timeout rồi client tạo event ID khác khi retry | Hai hàng cho cùng hành vi | Event ID ổn định, dedupe và kiểm tra khóa |
| Hoạt động người dùng | Event đến muộn qua ranh giới ngày | Ghi nhầm bucket khiến timeline thiếu | Bucket theo occurred_at UTC đã chốt |
| Dữ liệu thiết bị | Gateway offline rồi backfill lớn | Write burst và compaction/backpressure | Quota, batch ingest có giới hạn, TTL còn lại |
| Dữ liệu thiết bị | Ghi telemetry thành công, projection CRITICAL thất bại | Cảnh báo không xuất hiện ở site | Retry bền vững, đối soát theo event ID |
| Cả ba | Replica tạm vắng | Dữ liệu cần hội tụ sau khi node trở lại | Replication/CL/repair và giám sát |
| Cả ba | Đọc qua nhiều bucket khi TTL đang hết hạn | Trang kết quả thay đổi | Cursor có hợp đồng rõ, không hứa snapshot bất biến |

## 9. Checklist áp dụng vào dự án thực tế

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Truy vấn nào thực sự quan trọng? | Bảng query shapes với input, sort, QPS, SLO và giới hạn |
| Caller có biết đủ partition key không? | Mỗi CQL hot path có predicate chính xác trên khóa |
| Clustering đã phục vụ thứ tự và range chưa? | Test các truy vấn mới nhất/khoảng với dữ liệu trùng timestamp |
| Bucket tính từ thời điểm nào? | Quy định UTC và phân biệt event time, created time, received time |
| Partition lớn nhất có an toàn không? | Đo rows/bytes, peak writes, tombstone và p95/p99 trên khóa nóng |
| Fan-out có giới hạn trước không? | API giới hạn số ngày/giờ/shard, byte và concurrency |
| Có lặp dữ liệu không? | Có bảng mapping projection, nguồn sự thật và các mutation cập nhật |
| Có xử lý lỗi từng phần không? | Event ID/revision, retry, ordering, đối soát/rebuild |
| Retention có chính xác không? | TTL theo mốc nghiệp vụ, xử lý dữ liệu đến muộn và xóa |
| Replication/consistency có phù hợp không? | RF theo DC, CL theo SLA và kiểm thử node lỗi |
| Đã xét chi phí disk/compaction chưa? | SSTable đo thực tế, tombstone, headroom, index/projection |
| Java có kiểm soát paging không? | Không đọc vô hạn; token ràng buộc query shape và quyền tenant |
| Có đường cho tìm kiếm/analytics rộng không? | Truy vấn không phù hợp Cassandra được tách hoặc giới hạn |

## 10. Bài tập tổng hợp: chọn bảng cho một hệ thống giao nhận

Một ứng dụng Java quản lý đơn giao hàng và thiết bị quét mã. Dữ liệu gồm:

```text
Order:
  tenant_id, order_id, customer_id, created_at, status, revision

Scan event:
  tenant_id, parcel_id, scanner_id, site_id,
  scan_id, scanned_at, received_at, scan_status

Activity event:
  tenant_id, user_id, session_id, event_id,
  occurred_at, action_type
```

Yêu cầu:

1. **R1:** Tra trạng thái hiện tại của một order theo ID.
2. **R2:** Xem 50 order gần nhất của một customer trong tháng.
3. **R3:** Xem 100 scan gần nhất của một parcel trong một giờ UTC.
4. **R4:** Xem activity của một user trong ngày, mới nhất trước.
5. **R5:** Xem danh sách scan `FAILED` tại một site/ngày trên nhiều parcel.
6. **R6:** Báo cáo tổng số lần giao thất bại theo site mỗi tuần trong hai năm.

Các điều kiện bổ sung:

- Một parcel có thể được quét **25 lần/giây** trong giờ cao điểm; một scan có khoảng **800 B dữ liệu thô**.
- Scan có thể đến muộn hai ngày; cần giữ **7 ngày kể từ `scanned_at`**.
- User activity giữ 30 ngày kể từ `occurred_at`.
- Các API danh sách chỉ trả tối đa 100 hàng/lượt và phải có giới hạn thời gian.

**Câu hỏi:**

1. Chọn partition key và clustering key cho R1–R4; viết ít nhất hai câu `CREATE TABLE` và ba câu `SELECT` phù hợp.
2. Đề xuất một projection cho R5 và giải thích vì sao bảng scan theo parcel/giờ không thể trực tiếp liệt kê toàn site. Khi nào cần thêm shard?
3. Tính số scan và dữ liệu thô của parcel nóng nhất trong **một giờ** và **một ngày** nếu tải đỉnh duy trì liên tục. Nêu vì sao đây chưa phải byte SSTable.
4. Một scan xảy ra lúc 12:00 ngày 01/11, đến server lúc 12:00 ngày 03/11. Nếu retention 7 ngày từ `scanned_at`, TTL còn lại bao nhiêu tại thời điểm ghi?
5. Nếu API xem scan trong cửa sổ trượt 6 giờ, tối đa bao nhiêu bucket giờ có thể bị chạm? Cần phân trang/hợp nhất ra sao?
6. Một scan `FAILED` đã ghi ở bảng parcel/hour nhưng ghi bảng site/day lỗi. Nêu cách phát hiện, retry và bảo đảm không nhân đôi hàng.
7. Với R6, vì sao không nên quét tất cả parcel/hour trên cụm Cassandra giao dịch mỗi lần báo cáo? Chọn hướng dữ liệu phân tích thích hợp và nêu yêu cầu đối soát.

**Gợi ý đối chiếu:**

- R1: bảng `orders_by_id` với `PRIMARY KEY ((tenant_id, order_id))`.
- R2: bảng theo `(tenant_id, customer_id, month_bucket)` và clustering `created_at DESC, order_id DESC`.
- R3: bảng theo `(tenant_id, parcel_id, hour_bucket)` và clustering `scanned_at DESC, scan_id DESC`.
- R4: bảng theo `(tenant_id, user_id, day_bucket)` và clustering `occurred_at DESC, event_id DESC`.
- R5: projection theo `(tenant_id, site_id, day_bucket, shard_id)` với clustering `scanned_at DESC, scan_id DESC` chỉ lưu scan FAILED, có giới hạn shard/fan-out.
- Tải 25 scan/s tạo **90.000 scan/giờ**, khoảng **72 MB thô/giờ**; **2.160.000 scan/ngày**, khoảng **1.728 MB thô/ngày** (~1,73 GB). Đó chưa gồm khóa, metadata, index, compression, TTL, tombstone và RF.
- Scan đến muộn hai ngày còn khoảng **năm ngày TTL** từ event time; cửa sổ trượt 6 giờ có thể chạm **bảy bucket giờ**.
- R6 là bài toán tổng hợp dài hạn; có thể đưa event đã chấp nhận vào pipeline bền vững và kho OLAP/aggregate chuyên dụng, quản lý sự kiện trùng và đối chiếu kết quả theo site/tuần.

## Kết luận

Ba ví dụ đơn hàng, hoạt động người dùng và dữ liệu thiết bị cho thấy **cùng một Cassandra nhưng không có một primary key phù hợp với mọi đường đọc**. Đơn hàng cần phân biệt trạng thái hiện tại với danh sách theo khách/trạng thái; activity cần timeline theo người dùng hoặc phiên; telemetry cần bucket nhỏ đủ để kiểm soát tải và projection khác cho cảnh báo theo site. Thiết kế đúng bắt đầu từ **hợp đồng truy vấn, khóa định vị, thứ tự clustering và giới hạn tăng trưởng**, rồi mới quyết định số bảng, TTL, mức nhất quán và chiến lược vận hành. Hãy kiểm tra bằng CQL cụ thể, kiểm thử lỗi và phép đo trên partition nóng nhất trước khi coi mô hình sẵn sàng cho tải sản xuất.
