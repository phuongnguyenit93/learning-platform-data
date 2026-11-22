# Thiết kế bảng tra cứu và bảng lịch sử theo thời gian

## Mục tiêu bài học

Trong Apache Cassandra, một nghiệp vụ thường có ít nhất hai cách đọc dữ liệu rất khác nhau: **tra cứu nhanh một đối tượng hiện tại** bằng định danh và **xem diễn biến của đối tượng theo thời gian**. Ví dụ nhân viên hỗ trợ cần biết ngay một đơn hàng đang ở trạng thái nào, sau đó mở lịch sử những lần thay đổi trạng thái của chính đơn hàng đó.

Hai yêu cầu này có thể liên quan đến cùng thực thể nhưng lại cần **hai đường truy cập**: bảng tra cứu theo ID và bảng lịch sử có thứ tự thời gian. Thiết kế theo truy vấn (query-driven design) của Cassandra chấp nhận lưu dữ liệu theo nhiều biểu diễn có chủ đích để mỗi truy vấn quan trọng đi tới partition phù hợp, thay vì dựa vào `JOIN`, lọc toàn bảng hoặc sắp xếp toàn cục.

Bài học thuộc chương **Thiết kế theo truy vấn** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Kiến thức được đặt trong bối cảnh hệ thống phân tán wide-column, CQL, replication, consistency, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.

Sau bài học, bạn có thể:

- Phân biệt yêu cầu của **lookup table** và **time-series/history table** và chọn partition key, clustering column tương ứng.
- Viết các bảng và truy vấn CQL cho tra cứu theo ID, xem lịch sử một bucket, lọc theo khoảng và phân trang.
- Quyết định cách chia bucket theo ngày/tháng, xử lý đọc qua nhiều bucket, sự kiện đến muộn và các thời điểm trùng nhau.
- Nhận biết trách nhiệm duy trì nhiều bảng, bản ghi hiện tại khi sự kiện đến sai thứ tự, TTL, tombstone và sai lệch tạm thời giữa các bản sao nghiệp vụ.
- Thiết kế hợp đồng đọc phù hợp cho ứng dụng Java và lập checklist thử nghiệm trước khi sử dụng trong sản xuất.

## 1. Cùng một đơn hàng, hai câu hỏi khác nhau

Giả sử một dịch vụ Java quản lý đơn hàng cho nhiều tenant:

> **Câu hỏi A:** “Đơn hàng `orderId` này hiện ở trạng thái nào?”

> **Câu hỏi B:** “Những sự kiện nào đã xảy ra với đơn này trong tháng 11, mới nhất trước?”

Với câu A, caller có `tenantId` và `orderId`; cần đúng một kết quả, không quan tâm thứ tự thời gian. Với câu B, caller cũng biết `tenantId` và `orderId` nhưng muốn **nhiều hàng theo thời gian**, có thể lọc khoảng và tải thêm.

| Tiêu chí | Bảng tra cứu theo ID | Bảng lịch sử theo thời gian |
| --- | --- | --- |
| Mục đích | Trả trạng thái/thuộc tính mới nhất của một đơn | Trả chuỗi sự kiện hoặc các phiên bản theo thời gian |
| Partition key ứng viên | `(tenant_id, order_id)` | `(tenant_id, order_id, month_bucket)` |
| Clustering key | Không cần nếu mỗi đơn chỉ một hàng | `(event_time, event_id)` |
| Dạng kết quả | Một bản ghi hiện tại | Danh sách sự kiện có thứ tự |
| Biến động | Cập nhật khi trạng thái/tóm tắt đổi | Chủ yếu thêm sự kiện mới; tránh sửa lịch sử không cần thiết |
| Chiến lược giới hạn | Đọc một partition xác định | `LIMIT`, paging, bucket và giới hạn fan-out |
| Vòng đời dữ liệu | Có thể cần giữ trong suốt vòng đời đơn | Có thể có chính sách lưu trữ/TTL riêng |

Chỉ vì hai bảng cùng chứa `order_id`, `status` hoặc `updated_at` không có nghĩa chúng có thể gộp thành một bảng mà vẫn đáp ứng hiệu quả cả hai đường đọc.

### 1.1. Bảng tra cứu không chỉ là index

Một bảng lookup trong Cassandra có thể lưu **toàn bộ thông tin giao diện cần** để trả về ngay, ví dụ tên người mua, tổng tiền, trạng thái hiện tại và thời điểm thay đổi cuối. Nó cũng có thể chỉ là bảng **ánh xạ khóa** (ví dụ từ mã ngoài sang `order_id`) để bước tiếp theo đọc bảng chính.

Lựa chọn giữa **trả dữ liệu ngay** và **tra khóa rồi đọc tiếp** là một đánh đổi: lưu thêm dữ liệu làm tăng chi phí ghi và nguy cơ sai lệch các bản sao; thêm bước đọc tạo thêm round-trip và độ trễ.

### 1.2. Bảng lịch sử không đơn thuần là “đã cập nhật lúc nào”

Một cột `updated_at` trên hàng lookup chỉ cho biết một mốc gần đây, **không** thể tái tạo mọi sự kiện: ai đổi trạng thái, trạng thái cũ/mới, lý do và thời điểm xảy ra. Bảng lịch sử lưu **mỗi thay đổi thành một hàng riêng**, được định danh và sắp xếp theo thời gian.

Nếu bài toán yêu cầu audit bất biến hoặc tuân thủ pháp lý, cần xác định riêng cơ chế bảo vệ dữ liệu, kiểm soát sửa/xóa và độ tin cậy của nguồn sự kiện. Một bảng Cassandra thông thường với cách ghi append-only ở ứng dụng **không tự là nhật ký bất biến về mặt pháp lý**.

## 2. Thu thập hợp đồng truy vấn trước khi chọn bảng

Danh mục truy vấn minh họa:

| ID | Nhu cầu | Đầu vào bắt buộc | Phạm vi và thứ tự | Hướng thiết kế |
| --- | --- | --- | --- | --- |
| Q01 | Xem trạng thái và thông tin tóm tắt của đơn | `tenant_id`, `order_id` | Đúng một đơn | Bảng `orders_by_id` |
| Q02 | Xem 50 sự kiện mới nhất của đơn trong một tháng UTC | `tenant_id`, `order_id`, `month_bucket` | Một partition, `event_time DESC` | Bảng `order_events_by_month` |
| Q03 | Xem sự kiện trong một khoảng giờ thuộc tháng | Đủ khóa như Q02, `from`, `to` | Một partition, range theo `event_time` | Dùng chung bảng Q02 |
| Q04 | Xem lịch sử 3 tháng gần nhất | Tenant, order, khoảng tháng | Nhiều partition, hợp nhất thời gian | Đọc có giới hạn qua các tháng |
| Q05 | Tra cứu đơn bằng mã giao dịch của đối tác | Tenant, `external_ref` | Đúng một mã | Cần đường lookup theo mã ngoài |
| Q06 | Xem sự kiện `FAILED` của mọi đơn thuộc một tenant trong ngày | Tenant, ngày, loại sự kiện | Nhiều đơn, cần thứ tự toàn tenant | Query shape khác, thiết kế riêng |

Các con số như “50 sự kiện”, “3 tháng” là **giả định nghiệp vụ cho ví dụ**, không phải cấu hình mặc định của Cassandra.

Trước khi chốt schema, cần bổ sung QPS trung bình/đỉnh, p95/p99 mục tiêu, kích thước hàng, số sự kiện lớn nhất của mỗi đơn/tháng, khả năng sự kiện đến muộn, thời gian giữ lịch sử và yêu cầu đọc thấy dữ liệu mới sau khi ghi. Đây là những dữ liệu quyết định có nên chia bucket nhỏ hơn hay không.

## 3. Thiết kế bảng tra cứu theo định danh

### 3.1. Schema phục vụ Q01

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    last_event_time timestamp,
    last_event_id uuid,
    last_event_month text,
    PRIMARY KEY ((tenant_id, order_id))
);
```

`(tenant_id, order_id)` là **composite partition key**. Một tổ hợp tenant/đơn xác định một partition logic; không cần clustering column vì mỗi tổ hợp khóa đại diện cho một hàng tóm tắt.

Không chọn `tenant_id` làm partition key đơn cho mọi đơn của tenant: ở tenant lớn, một partition có thể phát triển không giới hạn và bị nóng. Cũng không chọn riêng `order_id` nếu hợp đồng truy cập cần luôn xác định và kiểm soát phạm vi tenant; dùng khóa gồm tenant giúp biểu đạt đường tra cứu và cô lập không gian khóa ở mức mô hình dữ liệu. **Phân quyền** vẫn phải được kiểm tra ở lớp ứng dụng, không chỉ dựa vào partition key.

### 3.2. Tra cứu đúng một đơn

```sql
SELECT customer_id, created_at, current_status, total_amount,
       last_event_time, last_event_id, last_event_month
FROM orders_by_id
WHERE tenant_id = ?
  AND order_id = ?;
```

Các dấu `?` dành cho **prepared statement**. Nếu dùng `cqlsh` tương tác, thay bằng literal CQL phù hợp. Truy vấn đưa đủ partition key và đọc một partition xác định; thông thường không cần `LIMIT 1` để biểu diễn “một đơn” vì schema đã chỉ có một hàng cho mỗi khóa.

Trên hàng lookup:

- `current_status` là **trạng thái tóm tắt hiện tại**; đây là dữ liệu nghiệp vụ cần đồng bộ khi có sự kiện mới.
- `last_event_time` và `last_event_id` giúp giao diện biết mốc sự kiện hiện đang được tóm tắt.
- `last_event_month` có thể dùng làm **gợi ý** bucket lịch sử gần nhất mà luồng xử lý đã công nhận, nhưng không chứng minh các tháng cũ đều có dữ liệu hay thay thế quy tắc tìm tất cả tháng.

**Quan trọng:** `last_event_time` không tự được Cassandra cập nhật vì có hàng mới trong `order_events_by_month`. Ứng dụng hoặc pipeline phải duy trì các cột lookup bằng một quy tắc rõ ràng.

### 3.3. Khi lookup có nhiều kiểu khóa

Nếu nhân viên hỗ trợ chỉ có mã từ cổng thanh toán (`external_ref`) mà không biết `order_id`, bảng `orders_by_id` không cung cấp truy cập một partition theo mã ấy. Có thể tạo một bảng ánh xạ nếu `external_ref` là duy nhất trong phạm vi tenant:

```sql
CREATE TABLE order_id_by_external_ref (
    tenant_id text,
    external_ref text,
    order_id uuid,
    PRIMARY KEY ((tenant_id, external_ref))
);

SELECT order_id
FROM order_id_by_external_ref
WHERE tenant_id = ? AND external_ref = ?;
```

Sau đó dịch vụ dùng `(tenant_id, order_id)` đọc `orders_by_id`. Hai lượt đọc này có thể phù hợp khi lookup theo mã ngoài ít thường xuyên và chỉ cần lưu mapping; nếu API cần một round-trip, cân nhắc sao chép các cột kết quả cần thiết và chấp nhận trách nhiệm duy trì chúng.

Nếu `external_ref` có thể **không duy nhất**, thiết kế bảng mapping một hàng trên sẽ ghi đè các giá trị chung khóa. Khi ấy phải thay hợp đồng nghiệp vụ hoặc schema để một mã có thể ánh xạ nhiều đơn và định nghĩa thứ tự/lựa chọn kết quả.

## 4. Thiết kế bảng lịch sử theo thời gian

### 4.1. Vì sao cần bucket?

Nếu toàn bộ lịch sử của một đơn nằm trong partition `(tenant_id, order_id)`, số hàng có thể tăng mãi với thời gian. Với đơn có rất nhiều biến cố, partition lớn gây khó kiểm soát tải, SSTable, độ trễ và xử lý tombstone.

Với yêu cầu Q02–Q03, ta chọn **bucket theo tháng UTC**:

```sql
CREATE TABLE order_events_by_month (
    tenant_id text,
    order_id uuid,
    month_bucket text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    status_before text,
    status_after text,
    actor_id uuid,
    note text,
    recorded_at timestamp,
    PRIMARY KEY ((tenant_id, order_id, month_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Cột `month_bucket` trong ví dụ là chuỗi chuẩn **`YYYY-MM` theo UTC** như `2026-11`. Cần một quy tắc duy nhất khi ghi và đọc; có thể dùng kiểu/định dạng khác nếu ứng dụng kiểm soát đồng nhất, nhưng không được biến `2026-11` và `2026-011` thành hai cách viết của cùng tháng.

Schema có:

1. **Partition key** `(tenant_id, order_id, month_bucket)` định vị lịch sử của một đơn trong một tháng.
2. **Clustering column** `event_time` tổ chức sự kiện theo thời gian.
3. **Clustering column** `event_id` phân biệt những sự kiện có cùng `event_time`, tránh cùng primary key.
4. Các cột `event_type`, `status_before`, `status_after`, `actor_id` và `note` chứa nội dung sự kiện; không mặc nhiên hỗ trợ bộ lọc tùy ý.

```text
Partition (tenant-A, order-42, 2026-11)
    (2026-11-21T10:40:00Z, event-c)  -> DELIVERED
    (2026-11-21T09:15:00Z, event-b)  -> OUT_FOR_DELIVERY
    (2026-11-20T15:00:00Z, event-a)  -> PACKED

Partition (tenant-A, order-42, 2026-10)
    (2026-10-30T08:00:00Z, event-x)  -> CREATED
```

Hai tháng là **hai partition khác nhau**; thứ tự `DESC` chỉ được bảo đảm trong từng partition tương ứng. Các mã ở sơ đồ là nhãn minh họa, không biểu diễn thứ tự thực tế của khóa `uuid` khi timestamp bằng nhau.

### 4.2. Q02: lấy các sự kiện mới nhất trong một tháng

```sql
SELECT event_time, event_id, event_type,
       status_before, status_after, actor_id, note, recorded_at
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?
LIMIT 50;
```

Với đầy đủ partition key và `CLUSTERING ORDER BY` giảm dần, truy vấn đọc sự kiện mới nhất trước trong tháng. `LIMIT 50` là **giới hạn tổng số hàng** của câu truy vấn này, phù hợp cho preview 50 hàng.

Nếu API định nghĩa “50 sự kiện gần nhất **bất kể tháng**”, Q02 chưa đủ. Cần xác định tháng mới nhất, quy tắc thử tháng trước và cách dừng. Không được xem dữ liệu ở `last_event_month` là lời giải đầy đủ khi các tháng có thể trống hoặc sự kiện đến muộn.

### 4.3. Q03: lọc khoảng thời gian trong một tháng

```sql
SELECT event_time, event_id, event_type, status_after, note
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

`event_time` là **clustering column đầu tiên**, nên có thể thu hẹp theo khoảng. Dùng khoảng nửa mở `[fromInclusive, toExclusive)` để tránh đếm trùng tại ranh giới. Ví dụ sự kiện xảy ra đúng 11:00 thuộc `[11:00, 12:00)` nhưng không thuộc `[10:00, 11:00)`.

Cần xác nhận hai mốc đang hỏi thuộc cùng `month_bucket`. Với khoảng đi qua ranh giới tháng, hãy chia thành các khoảng trong từng tháng:

```text
Yêu cầu: [2026-10-31T23:30:00Z, 2026-11-01T00:30:00Z)

Đọc partition 2026-10:
    [2026-10-31T23:30:00Z, 2026-11-01T00:00:00Z)
Đọc partition 2026-11:
    [2026-11-01T00:00:00Z, 2026-11-01T00:30:00Z)
```

Điều kiện `month_bucket = ?` không thể tự mở rộng sang tháng kế tiếp khi thời gian truy vấn vượt ranh giới.

### 4.4. Q04: lịch sử qua nhiều tháng

Nếu người dùng muốn tất cả sự kiện của một đơn từ tháng 9 đến hết tháng 11, ứng dụng có thể xác định các bucket `2026-09`, `2026-10`, `2026-11` rồi:

1. Đọc các partition tương ứng với giới hạn số tháng đã thống nhất.
2. Lấy dữ liệu mỗi partition theo clustering `(event_time DESC, event_id DESC)`.
3. Hợp nhất các luồng kết quả theo cùng thứ tự để hiển thị.
4. Quản lý vị trí đọc/trạng thái phân trang của từng partition, kèm giới hạn tổng số hàng và dữ liệu.

Một **cửa sổ trượt** dài đúng 90 × 24 giờ có thể chạm **bốn tháng lịch**, tùy mốc bắt đầu; nó không tương đương chính xác với “ba tháng lịch”. Hợp đồng API phải quy định một trong hai ý nghĩa trước khi tính số partition.

Không mặc định dùng `IN` trên nhiều partition key kết hợp `ORDER BY` sẽ tự tạo thứ tự toàn cục và chi phí thấp. Nếu truy vấn lịch sử toàn thời gian có lưu lượng cao hoặc SLA nghiêm ngặt, cân nhắc cách bucket khác, bảng projection chuyên biệt hoặc thiết kế luồng đọc riêng có kiểm soát.

## 5. Bảng lookup và bảng history phối hợp ở đường ghi

Sự kiện mới phát sinh hai nhu cầu khác nhau:

- **History:** ghi một hàng biểu diễn sự kiện.
- **Lookup:** cập nhật trạng thái hiện tại hoặc thông tin tóm tắt *nếu* sự kiện đó thực sự là trạng thái hợp lệ mới nhất theo quy tắc nghiệp vụ.

### 5.1. Ví dụ thao tác ghi

Giả sử ứng dụng đã kiểm tra và chuẩn hóa các giá trị đầu vào:

```sql
INSERT INTO order_events_by_month (
    tenant_id, order_id, month_bucket, event_time, event_id,
    event_type, status_before, status_after, actor_id, note, recorded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

Sau khi xử lý sự kiện theo quy tắc trạng thái hợp lệ, một cập nhật bảng lookup có thể có dạng:

```sql
UPDATE orders_by_id
SET current_status = ?,
    last_event_time = ?,
    last_event_id = ?,
    last_event_month = ?
WHERE tenant_id = ?
  AND order_id = ?;
```

Hai câu CQL trên **không đủ** để đảm bảo tính đúng nghiệp vụ nếu được thực thi độc lập và đồng thời trong mọi tình huống. Cassandra áp dụng quy tắc giải quyết xung đột theo timestamp ghi cho các giá trị ô; **sự kiện đến sau chưa chắc là sự kiện xảy ra muộn hơn**.

Ví dụ:

```text
09:00  Đơn chuyển sang PACKED (event E1)
10:00  Đơn chuyển sang SHIPPED (event E2)

Ứng dụng nhận E2 trước và cập nhật lookup = SHIPPED.
Sau đó E1 đến muộn, ghi đè lookup = PACKED nếu cập nhật vô điều kiện.

History có thể chứa cả E1 và E2 theo thứ tự event_time đúng;
lookup lúc này lại phản ánh sự kiện cũ.
```

Vì vậy cần định nghĩa trạng thái hiện tại theo **version/sequence đáng tin cậy**, luồng xử lý tuần tự theo đơn, hoặc thao tác **conditional update/LWT** có kiểm tra phiên bản trước khi ghi. Ứng dụng phải so sánh phiên bản hợp lệ và xử lý retry/thất bại; không thể chỉ dùng `MAX(event_time)` của bảng history một cách tự động để làm cột lookup luôn đúng.

### 5.2. Ví dụ kiểm soát phiên bản bằng điều kiện

Một phương án khi nghiệp vụ có **revision** tăng dần là bổ sung cột `revision bigint` trong hàng lookup từ **lúc thiết kế schema**, và dùng conditional update sau khi đọc giá trị hiện có:

```sql
-- Minh họa với schema lookup có thêm cột revision bigint.
-- Chỉ áp dụng khi ứng dụng đã xác minh nextRevision hợp lệ.
UPDATE orders_by_id
SET current_status = ?,
    last_event_time = ?,
    last_event_id = ?,
    last_event_month = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

Điều kiện `IF revision = ?` dùng cơ chế **lightweight transaction (LWT)**; caller phải kiểm tra kết quả `[applied]` và khi không áp dụng cần đọc lại/tranh chấp theo quy tắc nghiệp vụ. Câu lệnh không tự chứng minh rằng `nextRevision` lớn hơn giá trị cũ; đó là trách nhiệm của thuật toán/nguồn cấp revision. LWT có chi phí và độ trễ lớn hơn thao tác ghi thông thường, nên chỉ chọn sau khi xác định yêu cầu nhất quán.

Một luồng tiêu thụ sự kiện tuần tự theo `(tenant_id, order_id)` có thể là phương án khác nếu hệ thống đảm bảo nguồn và thứ tự xử lý. Dù chọn cách nào, cần kế hoạch xử lý trùng sự kiện, sự kiện đến muộn, retry, lỗi tạm thời và đối soát giữa lookup/history.

### 5.3. Có nên dùng CQL BATCH?

Logged batch có thể giúp các mutation qua nhiều partition được **ghi nhận để cuối cùng cùng được áp dụng** khi có lỗi từng phần, nhưng **không cung cấp cách ly giao dịch như database quan hệ**: độc giả vẫn có thể quan sát một phần thay đổi trước phần còn lại. Không nên dùng batch qua nhiều partition như mẹo tăng throughput hay thay thế một cơ chế quản lý nhất quán nghiệp vụ.

Với hệ thống cần bảo đảm phát và ghi sự kiện bền vững, có thể dùng pipeline với durable log/outbox, cơ chế retry có tính idempotent và đối soát. Phải thiết kế theo yêu cầu lỗi thật: mất kết nối sau khi lệnh ghi được áp dụng, gửi lặp, cập nhật lookup thành công nhưng history chưa có, hoặc ngược lại.

### 5.4. Định danh và replay sự kiện

Sự kiện có thể được gửi lại sau timeout. Nếu luôn giữ **cùng** `(tenant_id, order_id, month_bucket, event_time, event_id)` và cùng nội dung, ghi lặp vào history là một dạng **upsert idempotent về mặt khóa**. Nhưng cần nhớ:

- Cùng `event_id` với **event_time khác** sẽ tạo hàng khác; schema này không cưỡng bức duy nhất `event_id` trên toàn bộ các tháng.
- Nếu nội dung khác hoặc timestamp ghi khác, ghi lại có thể làm thay đổi ô dữ liệu.
- Nếu có TTL, ghi lại có thể làm đổi thời điểm hết hạn của các ô được ghi; không tự coi replay là vô hại trong mọi chính sách lưu trữ.

Nếu cần bảo đảm duy nhất toàn cục của event ID trong tenant, hãy thiết kế nguồn cấp ID/dedupe hoặc bảng ánh xạ riêng phù hợp; đừng suy từ việc có cột `event_id` trong clustering key.

## 6. Phân trang lịch sử và giới hạn phạm vi đọc

Trong Cassandra, `LIMIT`, page size và giới hạn API phục vụ ba mục đích khác nhau:

| Khái niệm | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `LIMIT 50` trong CQL | Giới hạn tổng số hàng của **câu truy vấn** | Preview 50 sự kiện |
| Page size của driver | Mục tiêu số hàng của mỗi lần lấy trang | API tải nhiều trang của cùng một query shape |
| Giới hạn API | Giới hạn tháng, số partition, tổng số hàng/byte và thời gian xử lý | Ngăn fan-out và truy vấn quá rộng |

Để tải nhiều trang từ một bucket, có thể dùng câu truy vấn **không cố định `LIMIT 50`**:

```sql
SELECT event_time, event_id, event_type, status_before, status_after, note
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?;
```

Sau đó đặt **page size** ở driver, trả token tiếp tục cho caller khi còn dữ liệu. **Paging state** của driver là dữ liệu opaque gắn với câu truy vấn và bind values; không tự sửa, không dùng lại với khóa khác hoặc khoảng khác và không xem nhiều trang là một ảnh chụp bất biến nếu có sự kiện mới/xóa đồng thời.

Khi phân trang **nhiều tháng**, một token đơn của một truy vấn một tháng không đủ mô tả toàn bộ tiến trình. Dịch vụ cần thiết kế cách lưu vị trí mỗi tháng, thứ tự hợp nhất, mốc snapshot logic nếu sản phẩm yêu cầu và điều kiện dừng. Nên bảo vệ tính toàn vẹn token do API cấp và luôn kiểm tra tenant/quyền truy cập khi tiếp tục.

Đọc ít hàng trả về không bảo đảm đọc ít tài nguyên: nhiều **tombstone** hoặc nhiều partition cần thăm dò để tìm đủ 50 hàng vẫn có thể làm truy vấn chậm.

## 7. Kết nối từ ứng dụng Java

Ví dụ dưới đây dùng API của **DataStax Java Driver 4.x** cho hai đường đọc. `CqlSession` được tạo và quản lý theo vòng đời dịch vụ, không tạo mới ở mỗi request.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.YearMonth;
import java.util.UUID;

public final class OrderReader {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement historyByMonth;

    public OrderReader(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, current_status, total_amount, " +
            "last_event_time, last_event_id, last_event_month " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.historyByMonth = session.prepare(
            "SELECT event_time, event_id, event_type, status_before, " +
            "status_after, actor_id, note, recorded_at " +
            "FROM order_events_by_month " +
            "WHERE tenant_id = ? AND order_id = ? AND month_bucket = ?"
        );
    }

    public Row getOrder(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet history(
        String tenantId, UUID orderId, YearMonth utcMonth
    ) {
        String monthBucket = utcMonth.toString(); // YYYY-MM
        BoundStatement statement = historyByMonth
            .bind(tenantId, orderId, monthBucket)
            .setPageSize(50);
        return session.execute(statement);
    }
}
```

Ví dụ chỉ minh họa **cách gọi hai đường đọc**. Ứng dụng thực tế cần:

1. Xác thực và phân quyền `tenantId/orderId` trước khi thực thi truy vấn.
2. Xác nhận `utcMonth` được tính theo **UTC** nếu nó được suy từ `event_time`; kiểu `YearMonth` tự nó không chứa múi giờ.
3. Thiết kế API trả một trang cụ thể: nếu lặp hết `ResultSet` đồng bộ, driver có thể tự lấy thêm trang. Cần kiểm soát số hàng đã duyệt và paging state theo API của phiên bản driver đang dùng.
4. Cấu hình timeout, consistency level, giới hạn fan-out, thông tin lỗi và retry phù hợp cho dịch vụ.

Trong đường ghi, có thể lấy bucket tháng bằng Java:

```java
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneOffset;

public static String monthBucket(Instant eventTime) {
    return YearMonth.from(eventTime.atZone(ZoneOffset.UTC)).toString();
}
```

Quy tắc này phải thống nhất ở mọi producer/consumer. Nếu dùng `recorded_at` để tạo bucket khi ghi nhưng `event_time` để chọn tháng khi đọc, sự kiện đến muộn có thể nằm trong tháng khác và không xuất hiện ở truy vấn mong đợi.

## 8. TTL, compaction, repair và consistency

### 8.1. Chọn vòng đời khác nhau cho lookup và history

Hàng lookup có thể cần sống đến khi đơn hoàn tất và hết thời gian lưu trữ nghiệp vụ. Lịch sử có thể giữ 90 ngày, 12 tháng hoặc dài hơn tùy quy định sản phẩm. Nếu áp dụng TTL trên bảng history, CQL có thể dùng:

```sql
-- Ví dụ 90 ngày tính bằng giây, chỉ dùng nếu chính sách lưu trữ cho phép.
INSERT INTO order_events_by_month (
    tenant_id, order_id, month_bucket, event_time, event_id,
    event_type, status_before, status_after, actor_id, note, recorded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL 7776000;
```

TTL trong Cassandra áp dụng ở mức ô dữ liệu, hết hạn sẽ tạo dấu xóa (tombstone) được dọn theo cơ chế storage/compaction khi đủ điều kiện. TTL 90 ngày **không tương đương** “giữ đúng ba tháng lịch”; phải xác nhận mục tiêu lưu trữ, khối lượng tombstone và chính sách xóa trước khi dùng.

Không tự đặt cùng TTL cho lookup và history: nếu hàng lookup hết hạn sớm hơn lịch sử, Q01 sẽ không còn trạng thái hiện tại dù timeline vẫn còn. Ngược lại, nếu history hết hạn còn lookup vẫn ghi `last_event_month`, giao diện cần xử lý trường hợp không còn sự kiện ở bucket được chỉ.

### 8.2. Compaction theo đặc điểm ghi và TTL

Bảng history chủ yếu ghi append và có thể có TTL theo thời gian, vì vậy **TimeWindowCompactionStrategy (TWCS)** là một lựa chọn đáng đánh giá trong các tải thời gian phù hợp. Tuy nhiên:

- TWCS không tự bảo đảm chi phí thấp nếu có nhiều ghi/sửa **ngoài cửa sổ thời gian** hoặc trộn dữ liệu sống lâu và ngắn hạn không phù hợp.
- Sự kiện đến muộn, TTL không đồng nhất và các mutation sau khi window đã đóng cần được xét khi chọn chiến lược và kích thước cửa sổ.
- Bảng lookup cập nhật nhiều lần trên cùng hàng có mẫu ghi khác history; không mặc định áp dụng cùng compaction strategy cho cả hai.

Compaction không thay thế partition key và clustering key đúng. Các chỉ số quan trọng gồm SSTable per read, tombstone scanned, kích thước partition, p95/p99 và tải đĩa.

### 8.3. Replication và consistency không đồng bộ nghiệp vụ giữa hai bảng

Replication factor và placement ở keyspace xác định các replica; consistency level cho mỗi đọc/ghi (chẳng hạn `LOCAL_QUORUM` trong topology phù hợp) xác định mức xác nhận từ replica. Chọn mức nhất quán đúng giúp đáp ứng yêu cầu chịu lỗi/đọc sau ghi trong phạm vi thiết kế, nhưng **không biến** việc ghi lookup và history thành một giao dịch SQL có thể đọc đồng thời hai bảng ở cùng một thời điểm logic.

**Repair** xử lý sự sai lệch dữ liệu giữa replica theo cơ chế Cassandra; nó **không** tự phát hiện rằng pipeline ứng dụng bỏ sót một bản ghi history hay không cập nhật lookup. Đó là công việc đối soát ở lớp nghiệp vụ. Các khoảng dừng ghi, lỗi mạng và retry cần được đưa vào kiểm thử vận hành.

## 9. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng một bảng chỉ có `PRIMARY KEY (tenant_id, order_id)` cho cả timeline | Chỉ có một hàng cho mỗi đơn, không lưu nhiều sự kiện lịch sử | Tách bảng lookup và bảng history có clustering theo thời gian |
| Dùng `PRIMARY KEY ((tenant_id, order_id), event_time)` cho lịch sử vô hạn | Partition có thể tăng rất lớn theo thời gian | Đánh giá bucket ngày/tháng và kích thước lớn nhất |
| Chỉ giữ `updated_at` để thay cho audit trail | Mất các sự kiện trung gian, actor và trạng thái trước/sau | Lưu mỗi sự kiện như một hàng có ID và thời gian riêng |
| Dùng `event_time` duy nhất làm clustering key | Sự kiện trùng timestamp có cùng primary key | Thêm `event_id` hoặc sequence phân định |
| Ghi sự kiện đến muộn rồi luôn cập nhật lookup | Trạng thái hiện tại có thể bị ghi lùi | Áp quy tắc version/ordering, CAS hoặc xử lý tuần tự |
| Bật `ALLOW FILTERING` để tìm bằng mã ngoài | Có thể quét nhiều dữ liệu, chi phí khó dự đoán | Bảng mapping `external_ref → order_id` phù hợp |
| Tưởng `LIMIT 50` làm mọi truy vấn lịch sử nhẹ | Vẫn có tombstone, fan-out qua nhiều tháng | Giới hạn bucket, page size, dữ liệu/byte và đo thực tế |
| Dùng chung TTL cho lookup và history theo thói quen | Trạng thái hiện tại biến mất hoặc timeline không còn theo mong đợi | Định nghĩa vòng đời riêng từng bảng |
| Tưởng repair sẽ tự khôi phục projection bị thiếu do bug ứng dụng | Dữ liệu lookup và history vẫn không khớp nghiệp vụ | Có queue bền vững, retry, đối soát và cơ chế tái tạo |

## 10. Checklist kiểm chứng trước khi chốt schema

| Kiểm chứng | Dấu hiệu đạt |
| --- | --- |
| Lookup có đầu vào đủ không? | Mọi request Q01 có `tenant_id` và `order_id` |
| Một mã ngoài có duy nhất không? | Có quy tắc uniqueness rõ trước khi tạo mapping |
| History có partition key phù hợp không? | Caller biết đơn và khoảng/bucket cần xem |
| Clustering có đúng thứ tự đọc không? | `event_time DESC, event_id DESC` đáp ứng list và range |
| Sự kiện có thể trùng timestamp không? | Có khóa phân định với định danh đủ duy nhất |
| Có sự kiện đến muộn/ngoài thứ tự không? | Lookup update theo quy tắc phiên bản, có retry/đối soát |
| Có cần đọc nhiều bucket không? | Số tháng tối đa được định nghĩa, có logic hợp nhất/paging |
| Kích thước partition lớn nhất thế nào? | Có số liệu hàng/byte/đỉnh ghi theo đơn và bucket |
| TTL và compaction đã phù hợp chưa? | Chính sách lưu từng bảng, tombstone và sự kiện đến muộn đã được xét |
| SLA và consistency đã được kiểm chứng chưa? | Có thử nghiệm dữ liệu lớn, failure/retry, read-after-write và đo p95/p99 |

Nên kiểm tra CQL với `cqlsh`, prepared statement với Java driver, dữ liệu nhiều tháng, các sự kiện cùng timestamp, khoảng qua ranh giới UTC, lịch sử có tombstone, trường hợp mất mạng sau ghi và sự kiện đến muộn. Việc một `SELECT` chạy đúng trên vài hàng mẫu **chưa chứng minh** bảng đáp ứng lưu lượng sản xuất.

## 11. Bài tập áp dụng

Một nền tảng giao hàng cần hai màn hình:

1. Nhập `parcelId` để xem **trạng thái hiện tại** của kiện hàng và thời điểm thay đổi mới nhất.
2. Xem **lịch sử quét mã** của kiện hàng trong một ngày UTC, mới nhất trước, tải 20 bản ghi mỗi trang.

Mỗi lần quét có `tenant_id`, `parcel_id`, `scan_time`, `scan_id`, `location_id`, `status_after` và `received_at`. Sự kiện có thể đến muộn; một kiện hàng có thể được quét nhiều lần ở cùng millisecond.

Hãy giải quyết:

1. Chọn partition key cho bảng tra cứu và các cột để trả lời yêu cầu trạng thái hiện tại.
2. Chọn partition key, clustering columns và thứ tự cho bảng lịch sử quét theo ngày; viết `CREATE TABLE`.
3. Viết câu CQL cho màn hình trạng thái và truy vấn lịch sử trong khoảng `[09:00, 12:00)` cùng ngày.
4. Phân biệt `LIMIT 20` và driver page size 20 nếu giao diện phải tải hàng trăm bản ghi qua nhiều trang.
5. Mô tả lỗi xảy ra nếu scan lúc 09:00 đến server **sau** scan lúc 10:00, nhưng cả hai cùng cập nhật lookup vô điều kiện.
6. Nếu sản phẩm thêm “tìm tất cả kiện hàng đã quét tại một địa điểm trong ngày”, giải thích vì sao hai bảng ban đầu chưa đủ và đề xuất hướng query-driven.

**Gợi ý đối chiếu:** Bảng lookup có thể dùng `PRIMARY KEY ((tenant_id, parcel_id))`. Bảng history có thể dùng `PRIMARY KEY ((tenant_id, parcel_id, day_bucket), scan_time, scan_id)` với thứ tự `DESC`, do `scan_id` phân biệt các bản ghi trùng `scan_time`. Với câu hỏi theo location/ngày, có thể cần bảng khác định vị theo `tenant_id`, `location_id` và bucket phù hợp, sau đó clustering theo thời gian, nhưng phải ước lượng tải và kích thước của địa điểm bận rộn nhất. Lookup phải cập nhật theo quy tắc thứ tự sự kiện/version thay vì “ai đến sau là mới nhất”.

## Kết luận

Trong Cassandra, **bảng tra cứu theo ID** tối ưu cho việc định vị nhanh một đối tượng hoặc một ánh xạ khóa, còn **bảng lịch sử theo thời gian** dùng partition key theo đối tượng/bucket và clustering key theo thời điểm để đọc sự kiện có thứ tự. Hai bảng bổ trợ nhau nhưng đem theo trách nhiệm ở đường ghi: chống replay sai, xử lý sự kiện đến muộn, đồng bộ trạng thái hiện tại và đối soát bản sao nghiệp vụ. Thiết kế hoàn chỉnh phải quy định rõ giới hạn bucket/paging, TTL, tải lớn nhất, consistency và kiểm thử lỗi thực tế trước khi coi các truy vấn đã được hỗ trợ.
