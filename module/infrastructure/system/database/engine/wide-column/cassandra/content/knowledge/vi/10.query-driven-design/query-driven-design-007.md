# Chấp nhận lặp dữ liệu để giảm truy vấn xuyên phân vùng

## Mục tiêu bài học

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, trong đó partition key quyết định nơi đặt và cách định tuyến dữ liệu, còn clustering column xác định thứ tự hàng trong một partition. Vì thế, một bảng đọc rất hiệu quả theo `customer_id` chưa chắc đọc tốt theo `status` hoặc `order_id`: các điều kiện đầu vào xác định những partition khác nhau.

Trong chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, giải pháp quan trọng là **chấp nhận lưu lặp những cột cần thiết vào nhiều bảng có khóa truy cập khác nhau**. Cách này thường gọi là *denormalization* hoặc *query projection*. Ta đổi một phần chi phí ghi và lưu trữ lấy khả năng đọc đúng partition, giảm truy vấn xuyên phân vùng, giảm lọc ở ứng dụng và đạt độ trễ dự đoán được.

Sau bài học, bạn có thể:

- Giải thích vì sao một bảng theo khách hàng có thể buộc truy vấn theo trạng thái thăm dò rất nhiều partition.
- Chuyển những đường đọc quan trọng thành các bảng projection với partition key và clustering key tương ứng.
- Phân tích khác biệt giữa **lặp dữ liệu nghiệp vụ** và **replication** trên các replica của Cassandra.
- Ước tính lợi ích giảm fan-out cùng chi phí tăng thêm về ghi, dung lượng, compaction, tombstone và độ trễ đồng bộ.
- Thiết kế thao tác khi dữ liệu bị đổi trạng thái, xử lý retry, bản ghi đến sai thứ tự và trường hợp cập nhật một projection thất bại.
- Viết ví dụ CQL và Java Driver, đồng thời xác định giới hạn `LIMIT`, paging và consistency level.

## 1. Một bảng phục vụ tốt một đường đọc chưa chắc phục vụ được đường đọc khác

Giả sử dịch vụ đơn hàng nhiều tenant có màn hình dành cho người mua:

> Xem 50 đơn gần nhất của một khách hàng trong tháng hiện tại, mới nhất trước.

Một bảng hợp lý cho kiểu đọc này có thể dùng:

```sql
PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)
```

Với partition key `(tenant_id, customer_id, month_bucket)`, Cassandra đọc một partition đã biết và trả hàng theo clustering `created_at DESC, order_id DESC`. Nhưng bộ phận vận hành cần thêm:

> Xem 50 đơn `PENDING` được tạo trong ngày hôm nay của **mọi khách hàng trong tenant**.

Người gọi chỉ có `tenant_id`, `status` và ngày UTC. Nó **không biết `customer_id`** nên không thể định vị partition của bảng theo khách hàng. `status` là một cột dữ liệu thông thường trong bảng đó, không tự biến thành chỉ mục truy cập theo trạng thái.

Một cách xử lý kém hiệu quả là lấy toàn bộ customer ID, đọc partition tháng của từng người rồi lọc `PENDING` và hợp nhất kết quả:

```text
tenant=T, status=PENDING, day=2026-11-21
        |
        +--> partition customer A / month 11
        +--> partition customer B / month 11
        +--> partition customer C / month 11
        |           ...
        +--> partition customer N / month 11
        |
        +--> lọc trạng thái + ngày, ghép/sắp xếp
        +--> trả 50 đơn gần nhất
```

Nếu tenant có 100.000 khách hàng, ứng dụng có nguy cơ phải thăm dò số lượng rất lớn partition mới biết khách hàng nào có đơn phù hợp. Thêm `LIMIT 50` vào từng truy vấn **không** tự giới hạn số partition cần thăm dò, cũng không đem lại thứ tự chung cho toàn bộ tenant.

Giải pháp thiết kế theo truy vấn là tạo **một projection theo trạng thái/ngày** có partition key mà caller Q03 thực sự biết. Khi đó truy vấn có thể đến đúng một partition logic, miễn là partition đó không quá lớn hoặc quá nóng.

## 2. Lặp dữ liệu là gì và không phải là gì?

Trong Cassandra, cùng một đơn có thể xuất hiện trong:

| Bảng | Khóa đọc chính | Tác vụ |
| --- | --- | --- |
| `orders_by_id` | `tenant_id + order_id` | Xem hoặc đối chiếu trạng thái của một đơn |
| `orders_by_customer_month` | `tenant_id + customer_id + month_bucket` | Danh sách đơn của khách theo thời gian |
| `orders_by_status_day` | `tenant_id + status + day_bucket` | Hàng đợi theo trạng thái của tenant |

Ba bảng chia sẻ một số cột như `order_id`, `created_at`, `status` hoặc `total_amount`. Việc lưu chúng trong ba partition key khác nhau là **lặp dữ liệu có chủ đích để trả lời ba query shape khác nhau**.

Đây là khái niệm khác với **replication**: Cassandra lưu nhiều **replica của cùng partition** theo replication factor và placement strategy để chịu lỗi. Tăng replication factor không thay đổi partition key; một truy vấn thiếu `customer_id` vẫn không xác định được partition trong bảng theo khách hàng. Ngược lại, bảng projection không thay thế tính sẵn sàng mà replication đem lại.

### 2.1. Chỉ lặp những cột cần để phục vụ truy vấn

Một bảng danh sách có thể chỉ cần ID, thời điểm, trạng thái, tổng tiền và một tên ngắn để hiển thị. Không nhất thiết nhân bản địa chỉ đầy đủ, chi tiết sản phẩm hoặc payload JSON dài vào mọi projection.

Mặt khác, projection quá ít cột có thể buộc ứng dụng phải thực hiện một lượt đọc `orders_by_id` cho **mỗi hàng trong danh sách** (mẫu N+1 lookups). Chọn cột projection dựa trên nội dung màn hình, rồi chỉ đọc chi tiết từ bảng ID khi người dùng mở một đơn cụ thể.

## 3. Thu thập query shape trước khi tạo projection

Ví dụ hệ thống thương mại điện tử có các truy vấn sau. Các giới hạn là **giả định minh họa**, không phải cấu hình chung của Cassandra.

| ID | Hành vi đọc | Đầu vào bắt buộc | Thứ tự/giới hạn |
| --- | --- | --- | --- |
| Q01 | Xem một đơn theo ID | Tenant, order ID | Một đơn |
| Q02 | Xem đơn của một khách trong tháng UTC | Tenant, customer ID, tháng | `created_at DESC`, 50 đơn |
| Q03 | Xem đơn đang `PENDING` được tạo trong một ngày UTC | Tenant, status, ngày tạo | `created_at DESC`, 50 đơn |
| Q04 | Xem các đơn `PENDING` trong bảy ngày lịch UTC | Tenant, status, bảy ngày | Thứ tự toàn màn hình, 50 đơn |
| Q05 | Tìm theo từ khóa và giá tiền, sort tùy ý trên toàn tenant | Nhiều filter tùy chọn | Chưa có đường đọc xác định |

Q01–Q03 có thể có **ba bảng riêng**. Q04 có thể tái dùng bảng Q03 với fan-out **hữu hạn** qua các ngày và hợp nhất ở tầng ứng dụng. Q05 cần được đánh giá như một query shape khác, có thể thích hợp với cơ chế tìm kiếm/phân tích hơn là bổ sung bảng Cassandra cho mọi tổ hợp bộ lọc.

Với mỗi query shape, phải ghi nhận thêm QPS trung bình/đỉnh, tỷ lệ đọc so với ghi, độ trễ p95/p99, số khách hàng, sự phân bố đơn theo tenant/trạng thái, số hàng/byte trong partition lớn nhất, mức độ mới cần hiển thị và chính sách lưu trữ.

## 4. Thiết kế ba bảng projection

### 4.1. Q01: tra cứu theo ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    updated_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, status, total_amount, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

`(tenant_id, order_id)` định vị một partition và một hàng tóm tắt. `revision` là phiên bản nghiệp vụ do ứng dụng cấp, **không tự tăng** bởi Cassandra. Bảng này là ứng viên cho trạng thái nguồn được ứng dụng kiểm soát, nhưng cần quy tắc xử lý cập nhật đồng thời nếu sử dụng làm nguồn quyết định trạng thái.

### 4.2. Q02: danh sách đơn theo khách hàng/tháng

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` là chuỗi `YYYY-MM` tính từ **`created_at` theo UTC**; ví dụ `2026-11`. Clustering theo thời gian và ID cho phép phân biệt đơn có timestamp tạo trùng nhau. Nếu truy vấn qua nhiều tháng, ứng dụng phải giới hạn số tháng được đọc và hợp nhất kết quả; một câu Q02 chỉ đọc **một partition tháng**.

### 4.3. Q03: danh sách đơn theo trạng thái/ngày

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, day_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
LIMIT 50;
```

`day_bucket` là **ngày UTC của `created_at`**, vì vậy Q03 trả “các đơn **được tạo trong ngày X** mà **hiện có trạng thái S**”. Nếu sản phẩm thực sự muốn “các đơn **chuyển sang trạng thái S trong ngày X**”, cần bucket theo thời điểm chuyển trạng thái và một mô hình truy cập khác; không dùng chung tên `day_bucket` cho hai nghĩa mà không phân biệt.

Trong bảng Q03, `status` trở thành thành phần partition key. Trong bảng Q02, `status` chỉ là cột hiển thị. Một thuộc tính có thể có vai trò khác nhau trong các bảng query-driven.

**Cảnh báo thiết kế:** partition `(tenant_id, status, day_bucket)` có thể rất lớn/hot khi tenant có nhiều đơn `PENDING` trong một ngày. Đừng chốt schema chỉ vì cú pháp CQL hợp lệ; cần đo kích thước và tốc độ cập nhật partition lớn nhất.

### 4.4. Tại sao chỉ biết order ID vẫn chưa sửa được mọi projection?

`order_id` là thành phần partition key trong `orders_by_id`, nhưng là clustering column trong hai bảng danh sách. Để cập nhật đúng một hàng ở `orders_by_customer_month`, ứng dụng phải biết `customer_id`, `month_bucket` và `created_at`. Để xóa hàng cũ trong `orders_by_status_day`, cần biết **trạng thái cũ**, ngày tạo, thời gian tạo và ID.

Do đó thông tin “định vị các bản sao” nên nằm trong trạng thái nguồn hoặc sự kiện thay đổi: `tenant_id`, `order_id`, `customer_id`, `created_at`, `old_status`, `new_status` và `revision`.

## 5. Đổi fan-out đọc lấy chi phí ghi và lưu trữ

So sánh đường đọc Q03:

| Khía cạnh | Chỉ bảng theo customer/month | Có projection status/day |
| --- | --- | --- |
| Input của API | Tenant, status, ngày | Giống nhau |
| Cách tìm partition | Không biết customer nào chứa đơn phù hợp | Biết trực tiếp `(tenant,status,day)` |
| Truy vấn | Có thể phải thăm dò rất nhiều customer/month | Một partition cho một status/ngày của tenant trong schema minh họa |
| Lọc trạng thái | Có thể phải lọc ở ứng dụng hoặc đường khác | Status thuộc partition key |
| Sắp xếp | Phải hợp nhất từ nhiều partition | Clustering sẵn theo `created_at` trong partition |
| Ghi dữ liệu | Ít bản sao hơn | Thêm một mutation cho mỗi đơn, thêm xóa/ghi khi đổi status |
| Rủi ro | Fan-out và độ trễ đọc lớn | Phải duy trì projection và kiểm soát hotspot |

Giả sử hàng đợi Q03 có 2.000 lượt gọi/phút và nếu không có projection cần thăm dò trung bình 5.000 partition/call: ước lượng khái niệm là **10 triệu lượt đọc partition logic/phút**. Đây **không phải** số RPC thật từ Cassandra; batching, cache, topology và dữ liệu quyết định chi phí thực tế. Nó cho thấy vì sao thay đổi khóa truy cập có thể quan trọng hơn tối ưu một `SELECT` riêng lẻ.

Đổi lại, mỗi đơn được lưu ở nhiều bảng: tăng số mutation trên đường ghi, tăng dung lượng lưu trữ, tăng tombstone khi di chuyển trạng thái và thêm việc đối soát. Chỉ nhân bản các query shape có giá trị đủ lớn về tần suất hoặc SLA; với truy vấn hiếm và fan-out nhỏ có chặn trước, đọc nhiều partition rồi hợp nhất có thể là lựa chọn tốt hơn.

## 6. Nếu partition projection theo trạng thái quá nóng?

Giả sử tenant tạo 250.000 đơn/ngày và tại một thời điểm có 40% đơn trong bucket ngày đang `PENDING`. Bảng trạng thái có thể chứa khoảng **100.000 hàng PENDING** cho một `(tenant, status, day)`. Nếu mỗi hàng có xấp xỉ 400 byte dữ liệu thô thì đó là khoảng **40 MB dữ liệu thô**, chưa gồm overhead, index, tombstone, compaction hoặc replication.

Không có một con số chung nào bảo đảm partition đó an toàn. Một partition còn có thể nóng do thay đổi trạng thái liên tục, kể cả kích thước chưa đặc biệt lớn. Khi đo thấy cần chia tải, có thể thêm shard:

```sql
CREATE TABLE orders_by_status_day_sharded (
    tenant_id text,
    status text,
    day_bucket date,
    shard_id int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, day_bucket, shard_id),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Nếu dùng 16 shard và quy tắc cố định `shard_id = hash(order_id) mod 16`, một order có vị trí được xác định ổn định. Đọc toàn bộ status/day phải đọc **tối đa 16 partition**, rồi hợp nhất kết quả theo `(created_at DESC, order_id DESC)`. Đây là fan-out nhưng **có giới hạn và biết trước**, thay vì thăm dò hàng nghìn khách hàng.

| Cách tổ chức | Số partition mục tiêu của Q03 | Đổi chác |
| --- | --- | --- |
| Không projection | Không biết trước; có thể cực lớn | Ít mutation phụ, đọc đắt |
| Projection status/day | 1 | Đơn giản đọc, nguy cơ partition nóng/lớn |
| Projection status/day/16 shard | Tối đa 16 | Giảm tải mỗi partition, tăng merge/paging |

Đừng tự thay số shard từ 8 lên 16 mà không có cách nhận diện dữ liệu cũ hoặc kế hoạch migration. Số shard là một phần hợp đồng giữa đường ghi và đọc; quy tắc hash phải đồng nhất ở mọi producer. Nếu tải vẫn nhỏ, không cần thêm shard chỉ để “chuẩn bị trước”.

## 7. Duy trì dữ liệu lặp khi ghi

Lợi ích ở đường đọc chỉ tồn tại bền vững khi các projection hội tụ về trạng thái đúng. Cassandra **không tự biết** ba bảng cùng nói về một đơn; ứng dụng hoặc pipeline dữ liệu phải cập nhật từng biểu diễn.

### 7.1. Tạo đơn mới

Một event “order created” có thể dẫn đến ba lệnh CQL:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, status, day_bucket, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Giá trị `created_at` và cách tính bucket phải thống nhất. Trong ví dụ cả `month_bucket` lẫn `day_bucket` đều tính từ **thời điểm tạo đơn theo UTC**, dù projection được ghi muộn hơn. Đừng tạo bucket từ thời điểm retry, vì cùng một order có thể bị đưa sang tháng/ngày khác khi phát lại sự kiện.

### 7.2. Đổi trạng thái phải xóa khóa cũ và ghi khóa mới

Giả sử đơn tạo ngày 21/11 đang `PENDING`; ngày 22/11 chuyển sang `PAID`. Vì `day_bucket` trong Q03 nghĩa là **ngày tạo đơn**, projection mới vẫn thuộc ngày 21/11. Tuy nhiên, `status` nằm trong partition key nên hàng đã **di chuyển sang một partition khác**.

Các bước nghiệp vụ cần được thiết kế:

1. Xác nhận thay đổi trạng thái mới theo quy tắc nghiệp vụ và phiên bản.
2. Cập nhật `orders_by_id` với trạng thái/revision được chấp nhận.
3. Cập nhật cột `status` trong `orders_by_customer_month` bằng đầy đủ primary key.
4. **Xóa** hàng ở `orders_by_status_day` với `old_status = PENDING`.
5. **Ghi** hàng ở `orders_by_status_day` với `new_status = PAID`.

Hai mutation của bảng trạng thái có thể viết:

```sql
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
  AND created_at = ?
  AND order_id = ?;

INSERT INTO orders_by_status_day (
    tenant_id, status, day_bucket, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`status` ở lệnh `DELETE` phải là **trạng thái cũ**; `status` ở lệnh `INSERT` phải là trạng thái mới. Không thể chỉ `UPDATE status = ?` trên một cột thuộc primary key. Xóa tạo tombstone, vì vậy với các đối tượng đổi status liên tục cần đo chi phí đọc/ghi, compaction và lựa chọn mô hình khác nếu cần.

### 7.3. Đến sai thứ tự, retry và bản ghi trùng

Xét hai sự kiện được ứng dụng phát:

```text
revision 11: PENDING
revision 12: PAID

Consumer nhận revision 12 trước, cập nhật PAID.
Sau đó consumer nhận revision 11 muộn, ghi lại PENDING.
Nếu không kiểm soát thứ tự, trạng thái cuối cùng bị ghi lùi.
```

Việc có cột `revision` **không tự động** khiến Cassandra từ chối phiên bản cũ. Cập nhật thường dùng timestamp ghi và quy tắc giải quyết xung đột của Cassandra, không so sánh `revision` như một ràng buộc nghiệp vụ.

Để giữ trạng thái đúng, cần chọn và triển khai quy tắc:

- Có **source of truth** cho trạng thái với `revision`/sequence tăng đơn điệu.
- Kiểm soát thay đổi được chấp nhận, có thể dùng xử lý tuần tự theo `order_id` hoặc **LWT/CAS** trên một hàng nguồn khi cần. Với LWT dạng `IF revision = ?`, caller phải kiểm tra kết quả `[applied]` và xử lý tranh chấp.
- Tạo mutation cho projection **từ những thay đổi đã được chấp nhận**; consumer phải xử lý trùng, thứ tự và lỗi từng phần.
- Có **đối soát/rebuild** các projection khi một update bị mất hoặc sai, thay vì tin rằng retry ngẫu nhiên sẽ tự sửa mọi trường hợp.

LWT trên một hàng nguồn **không biến** việc cập nhật nhiều partition trong nhiều bảng thành một giao dịch SQL cách ly hoàn toàn. Nếu yêu cầu nghiệp vụ đòi tất cả bảng lập tức cùng nhất quán, cần xem lại kiến trúc và hợp đồng đọc/ghi.

### 7.4. Có nên dùng CQL BATCH?

CQL batch nhóm nhiều mutation; **logged batch** hỗ trợ bảo đảm các mutation đã được chấp nhận cùng được áp dụng sau khi phục hồi lỗi, nhưng **không có tính cách ly quan sát như một transaction SQL**. Đọc ở nhiều bảng/partition vẫn có thể thấy trạng thái cập nhật từng phần tại những thời điểm khác nhau.

Batch quá lớn trải rộng nhiều partition cũng tăng tải coordinator/batchlog, **không** phải cách tăng throughput mặc định. Batch không giải quyết logic “sự kiện revision cũ có được ghi đè mới không”. Cần thiết kế riêng sự kiện nguồn, retry idempotent, thứ tự xử lý và đối soát.

### 7.5. Ghi trực tiếp hay cập nhật bất đồng bộ?

| Mô hình | Cách thức | Ưu điểm | Điều cần giải quyết |
| --- | --- | --- | --- |
| Ghi các projection trong request | Service ghi các bảng khi xử lý thao tác | Đơn giản theo dõi một luồng request; có thể cập nhật sớm | Thất bại từng phần, latency, concurrent update/retry |
| Dựa trên sự kiện đã chấp nhận | Ghi nguồn rồi consumer duy trì projection | Có thể mở rộng/đối soát/replay độc lập | **Eventual consistency**, lag, idempotency và xử lý sai thứ tự |

Với cập nhật bất đồng bộ, đo **projection lag** (chênh lệch giữa sự kiện nguồn được chấp nhận và projection phản ánh nó) và công bố cho sản phẩm độ mới có thể chấp nhận. Nếu một API cần đọc thấy ngay sau ghi, nên xét đọc bảng nguồn theo ID hoặc cơ chế xác nhận thích hợp, thay vì giả định bảng danh sách đã lập tức cập nhật.

## 8. Replication, consistency, compaction và repair không sửa được lỗi đồng bộ nghiệp vụ

Replication factor/placement giữ nhiều **replica** cho mỗi partition; consistency level (ví dụ `LOCAL_QUORUM` với topology phù hợp) quyết định mức đáp ứng của replica cho đọc/ghi. Đây là kiểm soát tính nhất quán **trong đường đọc/ghi dữ liệu đã được gửi đến Cassandra**.

Nếu `orders_by_id` đã cập nhật `PAID` nhưng consumer chưa ghi vào `orders_by_status_day`, tăng consistency level ở truy vấn status **không thể tự tạo mutation projection đang thiếu**. Sự chênh lệch đó thuộc nghiệp vụ, không phải replica lag của cùng một partition.

- **Repair** giúp các replica đồng bộ theo cơ chế Cassandra; nó không biết rằng pipeline quên xóa hàng `PENDING`.
- **Compaction** xử lý SSTable/tombstone theo điều kiện; nó không tái tạo hàng `PAID` ở một projection chưa được ghi.
- **TTL** có thể khiến các projection hết hạn vào thời điểm khác nhau nếu chính sách lưu trữ khác nhau; cần quy định vòng đời riêng phù hợp.

Do đó, bảng projection cần có **cơ chế đối soát ở cấp đối tượng**: so sánh revision/trạng thái giữa nguồn và projection, phát hiện ID bị thiếu/trùng, đo số mutation chưa xử lý, retry và khả năng tái tạo bảng khi cần.

## 9. Dùng projection từ Java

Ví dụ sử dụng **DataStax Java Driver 4.x**. Ứng dụng gọi đúng bảng theo những khóa mà API cung cấp, sử dụng prepared statement:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.UUID;

public final class OrderReader {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement byCustomerMonth;
    private final PreparedStatement byStatusDay;

    public OrderReader(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, status, total_amount, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.byCustomerMonth = session.prepare(
            "SELECT order_id, created_at, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
        this.byStatusDay = session.prepare(
            "SELECT order_id, customer_id, created_at, total_amount " +
            "FROM orders_by_status_day " +
            "WHERE tenant_id = ? AND status = ? AND day_bucket = ? " +
            "LIMIT 50"
        );
    }

    public Row findById(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet customerOrders(
        String tenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            byCustomerMonth.bind(tenantId, customerId, utcMonth.toString())
        );
    }

    public ResultSet pendingOrders(
        String tenantId, LocalDate createdUtcDay
    ) {
        return session.execute(
            byStatusDay.bind(tenantId, "PENDING", createdUtcDay)
        );
    }
}
```

`UUID` ánh xạ CQL `uuid`, `LocalDate` ánh xạ `date`, `YearMonth.toString()` cho chuỗi bucket `YYYY-MM`. `YearMonth` không mang timezone; nếu chuyển từ `Instant createdAt`, phải dùng UTC nhất quán. Dịch vụ cần xác thực/ủy quyền tenant, đặt timeout và giới hạn truy vấn; partition key có `tenant_id` **không thay thế** phân quyền.

Một `CqlSession` nên được quản lý theo vòng đời ứng dụng. Prepared statement cho từng query shape giúp bảo đảm đầu vào luôn có khóa phù hợp; không xây chuỗi `WHERE` tùy ý từ mọi filter rồi kỳ vọng schema nào cũng dùng được.

### 9.1. `LIMIT`, page size và đọc nhiều bucket

`LIMIT 50` trong các câu trên giới hạn **tổng số hàng của câu truy vấn**, thích hợp cho màn preview. Nếu API cần tải nhiều trang của cùng một partition, dùng câu truy vấn **không cố định `LIMIT 50`**, cấu hình page size của driver và xử lý paging state opaque gắn với query shape/giá trị bind.

```java
PreparedStatement customerHistory = session.prepare(
    "SELECT order_id, created_at, status, total_amount " +
    "FROM orders_by_customer_month " +
    "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ?"
);

var statement = customerHistory
    .bind(tenantId, customerId, monthBucket)
    .setPageSize(50);
```

Lặp toàn bộ `ResultSet` đồng bộ có thể làm driver tải thêm trang; endpoint chỉ trả một trang phải kiểm soát số hàng thực sự tiêu thụ và token tiếp tục. Khi dữ liệu đổi trong lúc phân trang, nhiều trang không mặc nhiên tạo một snapshot bất biến.

Với Q04 qua bảy ngày hoặc projection sharded, cần giữ vị trí đọc của từng partition, hợp nhất thứ tự `(created_at DESC, order_id DESC)` và chặn tổng số partition/hàng/byte. Một paging state của một truy vấn đơn lẻ **không** mô tả toàn bộ tiến trình fan-out qua nhiều partition.

## 10. Khi nào không nên thêm projection?

Denormalization là công cụ cho đường đọc quan trọng, không phải mục tiêu tự thân. Trước khi tạo bảng mới, hỏi:

1. Query này có tần suất hoặc yêu cầu SLA đáng để trả chi phí ghi/lưu trữ/đối soát lâu dài không?
2. API có sẵn đủ khóa của bảng đang có hoặc có thể lấy chúng bằng một lookup nhỏ không?
3. Nếu query chỉ đọc hai hoặc ba bucket đã biết, fan-out nhỏ có giới hạn có đủ đáp ứng không?
4. Query có nhiều filter và sort tùy ý không? Nếu có, một công cụ tìm kiếm/analytics hoặc phạm vi tính năng hẹp hơn có thể phù hợp.
5. Thuộc tính khóa projection (như `status`) có thay đổi thường xuyên không? Chi phí xóa/ghi/tombstone có đáng chấp nhận?
6. Có chính sách TTL, kiểm soát quyền truy cập và quy trình phục hồi projection nếu mất dữ liệu không?

Secondary index hoặc **Storage-Attached Index (SAI)**, khi phiên bản/triển khai Cassandra hỗ trợ, có thể là phương án cần đánh giá cho một số bộ lọc. Chúng không tự đảm bảo `ORDER BY` toàn cục hoặc mọi tổ hợp filter chạy hiệu quả. Đo tính chọn lọc, lượng dữ liệu đọc và độ trễ với workload thật trước khi quyết định.

## 11. Checklist kiểm chứng và vận hành

| Hạng mục | Tình huống kiểm tra | Quan sát cần có |
| --- | --- | --- |
| Định tuyến truy vấn | Q01/Q02/Q03 có đầy đủ partition key | Số partition bị chạm và p95/p99 |
| Hot partition | Tenant và status có lưu lượng lớn nhất | Kích thước hàng/byte, tốc độ mutation, replica nóng |
| Di chuyển trạng thái | `PENDING → PAID` | Xóa hàng cũ, có hàng mới sau khi projection hội tụ |
| Sự kiện đến sai thứ tự | Revision 12 được xử lý trước 11 | Không để trạng thái cuối cùng lùi |
| Retry/timeout | Mutation đã áp dụng nhưng client chưa nhận ACK | Không tạo hàng trùng hoặc làm mất thay đổi |
| Lỗi từng phần | Lookup đã cập nhật, status projection chưa cập nhật | Có backlog, retry, phát hiện và đối soát |
| TTL, xóa, tombstone | Nhiều lần chuyển trạng thái hoặc dữ liệu hết hạn | Truy vấn vẫn đạt SLA, không dùng TTL lệch ý định |
| Truy vấn nhiều ngày/shard | Q04 và bảng 16 shard | Có giới hạn fan-out, merge đúng và paging an toàn |
| Node lỗi, repair | Replica chậm hoặc vắng mặt | Đồng bộ replica đúng; không nhầm với projection sync |
| Đọc ngay sau ghi | Vừa cập nhật trạng thái và mở hàng đợi | Độ trễ đồng bộ nằm trong cam kết sản phẩm |

Nên đo **projection lag**, số mutation chưa xử lý, số bản ghi không khớp revision/trạng thái khi đối soát, độ trễ đọc/ghi p95/p99, tombstone scanned và số phân vùng trên một request. Câu CQL chạy đúng trên vài hàng mẫu **chưa chứng minh** đường đọc đã tối ưu hoặc đường ghi có thể phục hồi sau lỗi.

## 12. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Một bảng theo customer phục vụ mọi filter | Phải quét nhiều partition hoặc lọc trên regular column | Tạo projection theo truy vấn chính |
| Copy toàn bộ payload vào mỗi projection | Tăng chi phí ghi, lưu trữ và đồng bộ cột | Chỉ lặp các cột cần trả về |
| Projection status/day không đo tenant lớn nhất | Partition nóng hoặc quá lớn | Đo tải, bucket/shard khi cần |
| `UPDATE status` khi status thuộc primary key | Không thể đổi khóa bằng update thường | Xóa khóa cũ và ghi khóa mới |
| Có `revision` thì tin cập nhật cũ tự bị chặn | Dữ liệu có thể bị ghi lùi | CAS/ordering phù hợp và đối soát |
| Dùng logged batch như SQL transaction cách ly | Có thể thấy dữ liệu cập nhật từng phần | Hiểu giới hạn batch, retry/reconcile |
| Tăng consistency level để đồng bộ projection | Vẫn có projection lag hoặc thiếu mutation | Giám sát pipeline và phục hồi |
| Dùng `LIMIT 50` trên hàng trăm partition | Fan-out và sort vẫn rất tốn | Giới hạn bucket/shard và đo thực tế |
| Dựa vào repair để sửa bug ứng dụng | Projection vẫn thiếu hàng do source chưa ghi | Đối soát cấp nghiệp vụ và rebuild |
| Tạo bảng mới cho mọi filter hiếm dùng | Schema và đường ghi khó bảo trì | Chọn query shape có giá trị, xét cách khác |

## 13. Bài tập thực hành

Một ứng dụng Java quản lý ticket hỗ trợ có các cột:

```text
tenant_id, ticket_id, requester_id, created_at,
status, priority, title, updated_at, revision
```

Yêu cầu:

1. **R1:** Nhân viên mở một ticket bằng `ticket_id`.
2. **R2:** Người dùng xem 20 ticket gần nhất của mình trong tháng UTC.
3. **R3:** Trưởng nhóm xem 50 ticket `OPEN` được tạo trong ngày, mới nhất trước, trên toàn tenant.
4. **R4:** Khi ticket đổi `OPEN → RESOLVED`, hàng đợi OPEN không được còn ticket đó sau khi projection hội tụ.
5. **R5:** Tìm ticket bằng từ khóa trong tiêu đề và sắp theo `priority` trên toàn tenant.

Hãy trả lời:

1. Chọn bảng và partition key cho R1–R3; vì sao ba truy vấn không tự dùng một partition key?
2. Viết CQL `CREATE TABLE` và `SELECT` cho R3. Ngày bucket tính từ thời điểm tạo hay thời điểm chuyển trạng thái?
3. Mô tả thao tác trong R4: bảng theo ID, bảng theo requester/month, xóa hàng status cũ và ghi hàng status mới.
4. Nếu tenant có 500.000 ticket mới/ngày, cần đo gì trước khi dùng partition `(tenant, OPEN, day)`? Khi nào thêm shard?
5. Nếu revision 8 đến sau revision 9, cần quy tắc gì để tránh trạng thái hiện tại bị ghi lùi?
6. Vì sao R5 không tự được hỗ trợ bởi ba bảng trên? Đề xuất hướng truy cập khác và câu hỏi SLA/tính nhất quán cần làm rõ.

**Gợi ý đối chiếu:** R1 dùng `tickets_by_id` với partition key `(tenant_id, ticket_id)`. R2 dùng `tickets_by_requester_month` theo `(tenant_id, requester_id, month_bucket)` với clustering `created_at DESC, ticket_id DESC`. R3 dùng `tickets_by_status_day` theo `(tenant_id, status, day_bucket)`, clustering tương tự và `day_bucket` cần được định nghĩa nhất quán theo ngày tạo nếu yêu cầu là “được tạo trong ngày”. R4 cần xóa hàng khỏi partition OPEN và ghi vào RESOLVED, đồng thời cập nhật bảng ID/requester. R5 là bài toán tìm kiếm/sắp xếp khác, phải khảo sát index hoặc hệ tìm kiếm phù hợp thay vì chỉ thêm `ALLOW FILTERING`.

## Kết luận

Trong Cassandra, **chấp nhận lặp dữ liệu có chủ đích** giúp mỗi truy vấn quan trọng đi tới partition và thứ tự clustering phù hợp, giảm fan-out và chi phí lọc/hợp nhất ở ứng dụng. Đổi lại, mỗi projection tăng số mutation, dữ liệu lưu và trách nhiệm đồng bộ nghiệp vụ. Thiết kế tốt phải chứng minh đồng thời **đường đọc có chi phí giới hạn** và **đường ghi xử lý đúng thay đổi khóa, retry, sự kiện đến sai thứ tự và phục hồi sau lỗi**. Chọn projection theo nhu cầu thực tế, kiểm tra tải lớn nhất và duy trì đối soát để các cách nhìn dữ liệu cùng hội tụ về trạng thái đúng.
