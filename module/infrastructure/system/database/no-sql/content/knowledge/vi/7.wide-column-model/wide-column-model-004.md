# Lặp dữ liệu giữa các bảng để phục vụ các đường truy cập khác nhau

## 1. Vì sao một dữ liệu lại được lưu trong nhiều bảng?

Giả sử hệ thống bán hàng cần trả lời ba câu hỏi thường xuyên:

1. **Chi tiết đơn hàng:** đơn có `order_id` cụ thể đang ở trạng thái nào?
2. **Lịch sử khách hàng:** lấy 20 đơn hàng mới nhất của khách hàng A.
3. **Danh sách xử lý của người bán:** lấy các đơn đang chờ xử lý của người bán B, ưu tiên đơn mới nhất.

Trong cơ sở dữ liệu quan hệ, ta có thể lưu một bảng `orders` chuẩn hóa, đặt các chỉ mục phù hợp và phục vụ nhiều kiểu truy vấn trên cùng bảng. Với mô hình **wide-column** như Apache Cassandra, một cách thiết kế phổ biến lại là tạo **nhiều bảng có cấu trúc khóa khác nhau**, mỗi bảng tối ưu cho một đường truy cập đã biết.

Ví dụ, cùng một đơn hàng xuất hiện trong:

```text
                   Đơn hàng ORD-1001
                          |
           +--------------+------------------+
           |              |                  |
           v              v                  v
      orders_by_id   orders_by_customer  orders_by_seller_status
       Tìm theo ID     Lịch sử khách        Hàng chờ người bán
```

Trong ví dụ trên, tên bảng biểu đạt **câu hỏi mà bảng trả lời**. Một số trường như `order_id`, `created_at`, `status` hoặc `total_cents` được lưu lặp lại ở nhiều bảng.

Đây là **phi chuẩn hóa dữ liệu (denormalization)** có chủ đích. Mục tiêu của việc lặp dữ liệu là tạo ra **đường đọc đơn giản, xác định được partition và tận dụng thứ tự clustering**. Đổi lại, hệ thống phải chịu thêm ghi, lưu trữ và công việc duy trì sự nhất quán giữa các bản sao logic.

> Trong bài này, “lặp dữ liệu giữa các bảng” là tạo **nhiều hình chiếu nghiệp vụ (read models)** trong các bảng khác nhau. Nó **khác với replication**: replication sao chép một bảng hoặc partition đến nhiều nút để đáp ứng yêu cầu về độ sẵn sàng, chịu lỗi và nhất quán.

## 2. Đặc điểm của mô hình cột rộng ảnh hưởng đến cách thiết kế bảng

### 2.1. Partition key quyết định nơi tìm dữ liệu

Trong Cassandra, một bảng dùng **primary key** gồm:

- **Partition key:** quyết định partition chứa hàng và là đầu vào để phân phối dữ liệu giữa các nút.
- **Clustering columns:** quyết định thứ tự các hàng bên trong partition.

Ví dụ:

```sql
CREATE TABLE events_by_user_day (
    user_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    action text,
    PRIMARY KEY ((user_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Với bảng này:

- `(user_id, event_day)` là partition key ghép.
- `occurred_at` và `event_id` là clustering columns.
- Truy vấn biết cả `user_id` và `event_day` có thể định vị partition cần đọc.
- Các hàng trong partition đã được tổ chức theo thứ tự clustering, thuận tiện lấy sự kiện mới nhất.

Truy vấn phù hợp:

```sql
SELECT occurred_at, event_id, action
FROM events_by_user_day
WHERE user_id = ?
  AND event_day = ?
LIMIT 20;
```

Dấu `?` thể hiện tham số của một prepared statement; ứng dụng cần bind giá trị đúng kiểu trước khi thực thi.

### 2.2. Một bảng không tự động tối ưu mọi điều kiện lọc

Nếu muốn “lấy 20 sự kiện mới nhất **của tất cả người dùng** trong ngày D”, bảng trên không còn đường truy cập trực tiếp theo một partition vì truy vấn thiếu `user_id`.

Không nên mặc định rằng cứ thêm điều kiện `WHERE event_day = ?` là database sẽ truy xuất hiệu quả mọi hàng thỏa điều kiện. Với Cassandra, khả năng và chi phí lọc phụ thuộc partition key, clustering key, chỉ mục và phiên bản sản phẩm. Quét nhiều partition hoặc dùng `ALLOW FILTERING` trên tập dữ liệu lớn có thể tạo chi phí đáng kể.

Một phương án là thêm bảng `events_by_day` với partition/bucket thiết kế cho câu hỏi “theo ngày”. Khi đó, sự kiện được lưu thêm ở đường đọc mới.

### 2.3. Khác biệt với tư duy chuẩn hóa

| Góc nhìn | Thiết kế quan hệ chuẩn hóa | Thiết kế wide-column theo truy vấn |
|---|---|---|
| Điểm bắt đầu | Thực thể, thuộc tính, quan hệ và ràng buộc | Các câu truy vấn quan trọng và khả năng định vị partition |
| Một thực thể xuất hiện ở đâu? | Thường có một bản ghi chính cho mỗi thực thể | Có thể xuất hiện trong nhiều bảng theo đường đọc |
| Kết hợp dữ liệu | JOIN và index giúp phục vụ nhiều góc nhìn | Thường đọc trực tiếp bảng đã tổ chức phù hợp |
| Khi thêm truy vấn mới | Có thể thêm/chỉnh index hoặc truy vấn | Có thể cần bảng/read model mới |
| Cập nhật dữ liệu | Ít bản sao logic hơn, giao dịch quản lý ràng buộc | Cần cập nhật và đối soát nhiều hình chiếu |
| Đánh đổi | JOIN, chỉ mục, giao dịch có chi phí | Ghi, lưu trữ, đồng bộ, thay đổi schema có chi phí |

Cơ sở dữ liệu quan hệ vẫn có thể phi chuẩn hóa; Cassandra cũng có nhiều cơ chế chỉ mục và truy vấn bổ sung. Bảng trên mô tả **hướng thiết kế chủ đạo** thường áp dụng, không phải giới hạn tuyệt đối của từng sản phẩm.

## 3. Bài toán xuyên suốt: ba cách đọc cùng một đơn hàng

Giả sử dịch vụ xử lý đơn hàng có các trường:

| Trường | Ý nghĩa |
|---|---|
| `order_id` | Mã định danh đơn hàng, duy nhất |
| `customer_id` | Khách hàng đặt đơn |
| `seller_id` | Người bán xử lý đơn |
| `created_at` | Thời điểm tạo đơn |
| `status` | Trạng thái như `CREATED`, `PAID`, `SHIPPED`, `CANCELLED` |
| `total_cents` | Tổng tiền tính bằng đơn vị nhỏ nhất |
| `currency` | Mã tiền tệ |

Để tập trung vào cách tổ chức truy vấn, ta giả định một đơn chỉ có một người bán, trạng thái được mô tả bằng một chuỗi được kiểm soát, và giá trị tiền là `bigint` để tránh sai số thập phân của `double`. Một hệ thống đơn hàng thực có thể cần thêm chi tiết mặt hàng, giao dịch, kho và quy tắc nghiệp vụ.

Ba yêu cầu đọc:

- **Q1:** tìm đơn theo `order_id`.
- **Q2:** lấy 20 đơn mới nhất của một `customer_id` trong tháng đã chọn.
- **Q3:** lấy 20 đơn theo `seller_id`, `status` và tháng đã chọn, mới nhất trước.

Nếu chỉ có một bảng khóa theo `order_id`, Q1 thuận lợi nhưng Q2 và Q3 cần cách truy cập khác. Ta tạo ba bảng, với khóa chính được thiết kế riêng cho mỗi truy vấn.

## 4. Thiết kế bảng thứ nhất: truy vấn chi tiết theo mã đơn

```sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    seller_id uuid,
    created_at timestamp,
    status text,
    total_cents bigint,
    currency text
);
```

Đường truy cập:

```sql
SELECT order_id, customer_id, seller_id,
       created_at, status, total_cents, currency
FROM orders_by_id
WHERE order_id = ?;
```

Vì `order_id` là partition key, truy vấn có thể định vị partition chứa đơn hàng cần đọc. Đây là một **point lookup**, thuận lợi cho trang chi tiết đơn, API kiểm tra trạng thái hoặc xử lý sự kiện liên quan đến một đơn.

Nhưng nếu truy vấn:

```sql
-- Không phải đường truy cập được thiết kế cho bảng này
SELECT *
FROM orders_by_id
WHERE customer_id = ?;
```

thì `customer_id` không nằm trong primary key. Không nên xem việc thêm `WHERE` là đủ để lọc hiệu quả theo khách hàng. Tùy hệ và cấu hình, truy vấn có thể bị từ chối hoặc đòi hỏi chỉ mục/cơ chế lọc khác.

Ta cần một bảng phục vụ lịch sử đơn hàng của khách.

## 5. Thiết kế bảng thứ hai: truy vấn lịch sử khách hàng

### 5.1. Tại sao khóa theo khách hàng chưa đủ?

Nếu chỉ dùng `customer_id` làm partition key, một khách đặt hàng rất thường xuyên có thể tích lũy quá nhiều đơn trong một partition. Đọc và bảo trì partition lớn có thể tốn kém; tải truy cập tập trung vào một khách lớn có thể thành **hot partition**.

Để giới hạn theo thời gian, ta thêm `bucket_month` là chuỗi dạng `YYYY-MM`. Một partition khi đó chứa các đơn của **một khách trong một tháng**.

```sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    bucket_month text,
    created_at timestamp,
    order_id uuid,
    seller_id uuid,
    status text,
    total_cents bigint,
    currency text,
    PRIMARY KEY ((customer_id, bucket_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Ý nghĩa các phần của khóa:

- `(customer_id, bucket_month)`: xác định partition.
- `created_at DESC`: các đơn mới hơn được truy cập trước trong cùng partition.
- `order_id`: phân biệt khi nhiều đơn có cùng `created_at`, hỗ trợ thứ tự xác định.
- Các trường còn lại là dữ liệu được **lặp lại** để hiển thị danh sách mà không cần đọc từng đơn từ `orders_by_id`.

### 5.2. Truy vấn được tối ưu

```sql
SELECT created_at, order_id, seller_id,
       status, total_cents, currency
FROM orders_by_customer_month
WHERE customer_id = ?
  AND bucket_month = ?
LIMIT 20;
```

Sau khi có danh sách, trang lịch sử khách hàng có thể hiển thị trạng thái và số tiền từ bảng này. Nếu cần toàn bộ chi tiết từng đơn, ứng dụng có thể đọc bổ sung `orders_by_id` cho những đơn được chọn.

### 5.3. Nếu người dùng muốn xem 3 tháng gần nhất?

Một partition chỉ chứa một tháng. Ứng dụng có thể:

1. Xác định các tháng cần đọc.
2. Truy vấn từng partition `(customer_id, bucket_month)` tương ứng.
3. Gộp kết quả theo `created_at` rồi `order_id`.
4. Giới hạn số kết quả và dùng cơ chế phân trang phù hợp.

Việc chia theo tháng **giảm kích thước partition** nhưng khiến truy vấn xuyên tháng cần nhiều lượt đọc. Nếu khách rất ít đơn, bucket theo quý/năm có thể đơn giản hơn; nếu khối lượng cực lớn, bucket theo ngày hoặc có thêm shard có thể hợp lý hơn.

Lựa chọn bucket phải dựa trên lưu lượng, kích thước dữ liệu và mẫu truy vấn thật.

## 6. Thiết kế bảng thứ ba: hàng chờ theo người bán và trạng thái

Người bán thường xem danh sách **đơn đang chờ xử lý** theo thời gian. Truy vấn muốn biết:

- `seller_id` nào?
- `status` nào?
- Tháng nào?
- 20 đơn mới nhất là những đơn nào?

Tạo bảng:

```sql
CREATE TABLE orders_by_seller_status_month (
    seller_id uuid,
    status text,
    bucket_month text,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_cents bigint,
    currency text,
    PRIMARY KEY ((seller_id, status, bucket_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Đường truy vấn:

```sql
SELECT created_at, order_id, customer_id,
       total_cents, currency
FROM orders_by_seller_status_month
WHERE seller_id = ?
  AND status = ?
  AND bucket_month = ?
LIMIT 20;
```

**Trạng thái được đưa vào partition key** để câu hỏi “đơn `CREATED` của người bán B” xác định ngay partition cần đọc. Đây là thiết kế hữu ích nếu nhóm trạng thái là điều kiện lọc quan trọng.

Tuy nhiên, đưa **trường thường xuyên thay đổi** vào khóa có hệ quả đáng kể: Cassandra không cho sửa primary key của một hàng bằng `UPDATE` thông thường. Khi trạng thái đổi, ta phải **xóa bản ghi ở vị trí khóa cũ và tạo bản ghi ở vị trí khóa mới**.

Điều này không nhất thiết sai, nhưng phải được tính vào luồng cập nhật, xử lý lỗi và đồng bộ.

## 7. Nhìn rõ dữ liệu đã được lặp như thế nào

Một đơn hàng:

```text
order_id      = 44444444-4444-4444-8444-444444444444
customer_id   = 11111111-1111-4111-8111-111111111111
seller_id     = 22222222-2222-4222-8222-222222222222
created_at    = 2026-11-14T08:30:00Z
bucket_month  = "2026-11"
status        = "CREATED"
total_cents   = 25990
currency      = "USD"
```

sẽ xuất hiện logic trong ba bảng:

| Bảng | Khóa truy cập | Một số trường được sao chép |
|---|---|---|
| `orders_by_id` | `order_id` | `customer_id`, `seller_id`, `created_at`, `status`, `total_cents` |
| `orders_by_customer_month` | `(customer_id, bucket_month)` + `created_at, order_id` | `seller_id`, `status`, `total_cents`, `currency` |
| `orders_by_seller_status_month` | `(seller_id, status, bucket_month)` + `created_at, order_id` | `customer_id`, `total_cents`, `currency` |

Những trường lặp có giá trị vì **đáp ứng đúng nội dung cần hiển thị**. Không nhất thiết sao chép mọi trường của đơn hàng vào mọi bảng. Nếu trang danh sách không cần chi tiết địa chỉ giao hàng và từng mặt hàng, giữ các thông tin lớn đó ở nơi khác giúp giảm dung lượng và chi phí cập nhật.

Đây là sự đánh đổi giữa:

- **Ít lượt đọc và truy vấn đơn giản** ở bảng phục vụ danh sách.
- **Nhiều bản sao logic hơn** khi đơn được tạo, sửa hoặc xóa.

### 7.1. Đọc và ghi một đơn hàng bằng CQL

Giả sử ứng dụng dùng prepared statements cho các thao tác sau:

```sql
-- Bảng theo mã đơn hàng
INSERT INTO orders_by_id
(order_id, customer_id, seller_id, created_at,
 status, total_cents, currency)
VALUES (?, ?, ?, ?, ?, ?, ?);

-- Bảng lịch sử khách hàng
INSERT INTO orders_by_customer_month
(customer_id, bucket_month, created_at, order_id,
 seller_id, status, total_cents, currency)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);

-- Bảng hàng chờ của người bán
INSERT INTO orders_by_seller_status_month
(seller_id, status, bucket_month, created_at, order_id,
 customer_id, total_cents, currency)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Ba câu lệnh ghi **ba cấu trúc vật lý khác nhau**. Chúng không phải ba lệnh để tạo cùng một hàng duy nhất. Khi ứng dụng thực thi, thứ tự, mức xác nhận ghi, retry và cơ chế phát hiện thao tác thiếu phải được thiết kế rõ ràng.

Trong Cassandra, `INSERT` về bản chất là thao tác upsert đối với khóa chính được cung cấp: viết cùng khóa có thể cập nhật các cột của hàng đã có theo quy tắc timestamp/xung đột. Điều này hữu ích cho retry, nhưng **không tự đảm bảo** một sự kiện cũ gửi lại sẽ không ghi đè dữ liệu mới hơn.

## 8. Tư duy “một bảng cho mỗi đường truy cập” và giới hạn của nó

Một phương pháp thiết kế hữu ích:

1. **Liệt kê truy vấn thật:** đầu vào, kết quả, filter, sort, limit.
2. **Gom các truy vấn có cùng đường truy cập:** chưa chắc mỗi truy vấn cần một bảng riêng.
3. **Thiết kế partition key:** biết được khi truy vấn chạy, có phân phối dữ liệu đủ đều không?
4. **Thiết kế clustering key:** hỗ trợ sort/range và phân trang cần thiết.
5. **Chọn trường lặp:** chỉ mang dữ liệu thực sự cần để trả kết quả.
6. **Tính chi phí ghi và đồng bộ:** một thay đổi ảnh hưởng bao nhiêu bảng?
7. **Đo thực tế:** số partition đọc, p95/p99, kích thước hàng, chi phí vận hành.

Khẩu hiệu “one table per query” giúp học tư duy query-first, nhưng **không nên hiểu máy móc**. Một bảng có thể phục vụ nhiều truy vấn chia sẻ cùng partition key và thứ tự clustering. Ngược lại, một câu hỏi phức tạp có thể cần nhiều bảng hoặc hệ phân tích chuyên dụng.

### 8.1. Không biến Cassandra thành công cụ JOIN qua mọi quan hệ

Ví dụ, trang lịch sử đơn hàng chỉ cần `order_id`, `status` và `total_cents`. Nếu bảng danh sách chỉ chứa `order_id`, ứng dụng sẽ phải đọc một danh sách rồi phát nhiều truy vấn chi tiết đơn để lấy thông tin hiển thị:

```text
Read 20 order IDs
    |
    +--> read order 1
    +--> read order 2
    +--> ...
    +--> read order 20
```

Đây là mẫu **fan-out/N+1 reads**. Có thể chấp nhận trong một số tình huống, nhất là nếu dữ liệu không thay đổi nhiều hoặc có cache. Nhưng nếu hầu hết trang danh sách luôn cần trạng thái và số tiền, sao chép các trường nhỏ đó vào bảng danh sách thường làm đường đọc gọn hơn.

Không cần sao chép cả một đối tượng lớn chỉ để tránh một lần đọc thêm hiếm gặp.

## 9. Khi đơn hàng thay đổi: ba bảng phải đi về cùng một trạng thái

Giả sử đơn `ORD-1001` chuyển từ `CREATED` sang `PAID`.

Ba ảnh hưởng chính:

1. `orders_by_id` phải có `status = PAID`.
2. `orders_by_customer_month` phải hiển thị `PAID` để khách thấy trạng thái đúng.
3. `orders_by_seller_status_month` phải xóa hàng thuộc partition `CREATED` và thêm hàng thuộc partition `PAID`.

CQL minh họa:

```sql
-- Cập nhật trạng thái ở bản ghi theo ID
UPDATE orders_by_id
SET status = ?
WHERE order_id = ?;

-- Cập nhật bản ghi trong lịch sử khách
UPDATE orders_by_customer_month
SET status = ?
WHERE customer_id = ?
  AND bucket_month = ?
  AND created_at = ?
  AND order_id = ?;

-- Bỏ đơn khỏi danh sách trạng thái cũ
DELETE FROM orders_by_seller_status_month
WHERE seller_id = ?
  AND status = ?
  AND bucket_month = ?
  AND created_at = ?
  AND order_id = ?;

-- Thêm đơn vào danh sách trạng thái mới
INSERT INTO orders_by_seller_status_month
(seller_id, status, bucket_month, created_at, order_id,
 customer_id, total_cents, currency)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Trong thao tác xóa, tham số `status` phải là **trạng thái cũ**; trong thao tác thêm, tham số `status` là **trạng thái mới**. Ứng dụng phải biết cả hai.

### 9.1. Các trạng thái không đồng bộ tạm thời

Giả sử ứng dụng hoặc worker cập nhật các bảng theo từng bước:

```text
T0: orders_by_id               = CREATED
    orders_by_customer_month   = CREATED
    seller_status/CREATED      = có đơn

T1: orders_by_id               = PAID
    orders_by_customer_month   = CREATED
    seller_status/CREATED      = có đơn

T2: orders_by_id               = PAID
    orders_by_customer_month   = PAID
    seller_status/CREATED      = có đơn

T3: orders_by_id               = PAID
    orders_by_customer_month   = PAID
    seller_status/CREATED      = đã xóa
    seller_status/PAID         = có đơn
```

Ở T1 hoặc T2, hai trang ứng dụng có thể hiển thị trạng thái khác nhau. Đây là vấn đề **nhất quán giữa các read model**. Sản phẩm phải quyết định khoảng thời gian lệch dữ liệu nào chấp nhận được và làm gì với thao tác đòi hỏi tính đúng đắn tức thời.

Nếu xử lý đơn phụ thuộc trạng thái chính xác, phải đối chiếu trạng thái ở **nguồn dữ liệu có bảo đảm nghiệp vụ**, không tự động coi bảng hàng chờ phi chuẩn hóa là nơi quyết định cuối cùng.

### 9.2. Vì sao thay đổi khóa khó hơn thay đổi cột dữ liệu?

Trong `orders_by_seller_status_month`, `status` là một phần primary key. Chuyển từ `CREATED` sang `PAID` làm thay đổi địa chỉ logic của hàng trong partition. Cassandra không chuyển hàng sang khóa khác chỉ bằng:

```sql
-- Không phải cách đổi partition key
UPDATE orders_by_seller_status_month
SET status = 'PAID'
WHERE ...;
```

Thay vào đó, hệ thống cần xóa khóa cũ và ghi khóa mới. Nếu cập nhật liên tục qua nhiều trạng thái, chi phí ghi và việc duy trì chỉ mục sẽ tăng.

Đây là một lý do phải cân nhắc liệu nên đặt trạng thái vào partition key hay dùng thiết kế khác, ví dụ:

- Bảng hàng chờ **chỉ chứa trạng thái đang hoạt động**, không lưu mọi trạng thái lịch sử.
- Bảng theo người bán/thời gian, trạng thái làm dữ liệu phụ, nhưng tìm theo trạng thái có thể phải lọc thêm.
- Dùng một hệ chỉ mục/tìm kiếm/đọc chuyên dụng khi cần nhiều bộ lọc thay đổi linh hoạt.

Không có cấu trúc nào tối ưu đồng thời cho mọi kiểu cập nhật và truy vấn.

## 10. Ba cách duy trì dữ liệu giữa các bảng

### 10.1. Ghi đồng bộ từ dịch vụ ứng dụng

Ứng dụng tạo đơn và chủ động ghi cả ba bảng trước khi trả kết quả.

```text
API createOrder
    |
    +--> write orders_by_id
    +--> write orders_by_customer_month
    +--> write orders_by_seller_status_month
    |
    +--> trả phản hồi
```

**Ưu điểm:**

- Dễ hình dung, không bắt buộc có hệ thống message ngay từ đầu.
- Các đường đọc thường được cập nhật sớm.
- Phù hợp với hệ có tải và số read model còn hạn chế.

**Rủi ro và giới hạn:**

- Có thể xảy ra **ghi một phần** nếu một câu lệnh thất bại.
- Nhiều thao tác mạng làm tăng độ trễ ghi.
- Retry có thể đến sai thứ tự khi nhiều cập nhật xảy ra đồng thời.
- Khó đảm bảo toàn bộ các bảng cho cùng một ảnh chụp nhất quán tại mọi thời điểm.

Có thể giảm rủi ro bằng retry có giới hạn, thao tác idempotent, ghi log trạng thái đồng bộ và một tiến trình đối soát. **Không nên mặc định** nhiều câu `INSERT` riêng lẻ tạo thành giao dịch xuyên bảng kiểu RDBMS.

### 10.2. Ghi một nguồn chính rồi cập nhật các hình chiếu bất đồng bộ

Một kiến trúc phổ biến hơn khi có nhiều read model:

```text
                API / Command Handler
                          |
                          v
               Nguồn dữ liệu chính
                 (canonical state)
                          |
                   Change event
                          |
                    Event stream
                          |
          +---------------+----------------+
          |                                |
          v                                v
     Projector A                       Projector B
          |                                |
          v                                v
 orders_by_customer_month     orders_by_seller_status_month
```

Nguồn chính có thể là `orders_by_id` nếu toàn bộ thiết kế nghiệp vụ và bảo đảm ghi cho phép, hoặc một dịch vụ giao dịch/database khác nếu cần tính nguyên tử của những thay đổi phức tạp.

**Ưu điểm:**

- Có đường cập nhật rõ ràng từ một trạng thái chuẩn.
- Có thể thêm hoặc xây dựng lại read model từ nguồn/sự kiện.
- Tách chi phí cập nhật nhiều view khỏi đường phản hồi API trong một số trường hợp.

**Đánh đổi:**

- Các view có **độ trễ cập nhật**.
- Cần hạ tầng sự kiện, retry, xử lý sự kiện trùng và giám sát backlog.
- Cần bảo đảm sự kiện thay đổi **không bị mất** khi thao tác ghi chính đã thành công.

Nếu nguồn sự thật nằm trong RDBMS có giao dịch, mô hình **transactional outbox** thường ghi cả thay đổi nghiệp vụ lẫn bản ghi sự kiện outbox trong cùng một giao dịch, sau đó chuyển sự kiện ra broker. Nếu nguồn là Cassandra, cần đánh giá cơ chế CDC/luồng sự kiện, độ bền và giới hạn thực tế của sản phẩm; **không được tự suy ra** rằng ghi một hàng Cassandra và phát message luôn nguyên tử với nhau.

### 10.3. Dùng materialized view hoặc chỉ mục phụ của sản phẩm

Một số hệ wide-column có **materialized view**, **secondary index**, hoặc công nghệ chỉ mục chuyên biệt; các khả năng này thay đổi theo sản phẩm và phiên bản.

Chúng có thể giảm phần mã đồng bộ do ứng dụng tự viết trong một số tình huống, nhưng vẫn cần xem:

- Loại điều kiện lọc được hỗ trợ;
- Giới hạn về primary key và tập cột được đưa vào view;
- Độ trễ cập nhật và mức nhất quán;
- Chi phí ghi, sửa, rebuild và vận hành;
- Tải ở hot partition;
- Hạn chế hoặc khuyến nghị của đúng phiên bản.

Không nên mặc định cứ có materialized view thì mọi vấn đề đồng bộ và truy vấn được giải quyết. Các **bảng phi chuẩn hóa do ứng dụng quản lý** cho phép kiểm soát đường đọc và biến đổi dữ liệu linh hoạt hơn, đồng thời đặt trách nhiệm duy trì lên ứng dụng.

## 11. Đồng bộ đúng khi có retry, trùng sự kiện và sai thứ tự

Tạo ba bảng không phải phần khó nhất. Phần khó nằm ở việc đảm bảo chúng tiếp tục trả lời đúng sau hàng triệu lượt ghi, khi có sự cố mạng, dịch vụ tự khởi động lại hoặc sự kiện đến lặp.

### 11.1. Retry và idempotency

Giả sử projector nhận sự kiện tạo đơn hai lần vì consumer crash sau khi ghi thành công nhưng trước khi xác nhận message đã xử lý.

Với cùng `order_id`, `created_at` và khóa chính của bảng view, một lệnh upsert lặp lại có thể cập nhật cùng hàng. Tuy nhiên, từ đó **không thể kết luận mọi quy trình hoàn toàn idempotent**:

- Nếu lần xử lý thứ hai sinh UUID mới cho hàng view, nó sẽ tạo bản ghi thứ hai.
- Nếu tăng counter bằng lệnh cộng, chạy hai lần có thể cộng hai lượt.
- Nếu sự kiện cũ đến sau sự kiện mới, dữ liệu cũ có thể ghi đè trạng thái mới.
- Nếu có bước “xóa khóa cũ, thêm khóa mới”, thứ tự các bước và timestamp ghi ảnh hưởng kết quả.

Một thiết kế đáng tin cậy dùng **khóa hàng ổn định** dựa trên ID nghiệp vụ, tránh tác động cộng dồn không có kiểm soát và có cách nhận biết sự kiện đã xử lý.

### 11.2. Sự kiện đến không đúng thứ tự

Một đơn chuyển:

```text
CREATED -> PAID -> SHIPPED
```

Nhưng projector có thể nhận:

```text
1. OrderCreated(version=1)
2. OrderShipped(version=3)
3. OrderPaid(version=2)    <-- đến trễ
```

Nếu mỗi event chạy `UPDATE status = ...` với timestamp mới tại thời điểm xử lý, trạng thái `PAID` đến muộn có thể ghi đè `SHIPPED`. Cassandra dùng cơ chế giải quyết xung đột theo timestamp cho các giá trị ghi; chỉ lưu trường `version` mà **không kiểm tra nó** chưa đủ bảo vệ.

Các hướng xử lý tùy kiến trúc:

- Bảo đảm **thứ tự xử lý theo `order_id`** trong một luồng xử lý được phân vùng và không cho xử lý song song sai thứ tự của cùng đơn.
- Đính kèm **phiên bản tăng dần**, kiểm tra phiên bản trước khi áp dụng; nếu cần kiểm tra nguyên tử thì đánh giá conditional update/LWT trong phạm vi khóa được hỗ trợ và chi phí của nó.
- Dùng chiến lược timestamp ghi nhất quán với thứ tự phiên bản **đã được thiết kế và kiểm thử**, vì xóa hàng/tombstone và các cột ở nhiều bảng có thể ảnh hưởng kết quả.
- Khi phát hiện thứ tự bất thường, đọc trạng thái chuẩn rồi **xây dựng lại view** cho đơn tương ứng.

Cơ chế kiểm tra nguyên tử ở một partition **không biến** nhiều bảng/partition thành một transaction nhất quán tức thời.

### 11.3. Trạng thái cũ phải được dọn sạch

Với bảng `orders_by_seller_status_month`, một thay đổi trạng thái có thể tạo lỗi **bản ghi ma trong hàng chờ**:

1. Đơn đã là `SHIPPED` ở nguồn chính.
2. View `SHIPPED` được thêm thành công.
3. Xóa bản ghi ở view `PAID` thất bại.
4. Một thời gian sau, đơn xuất hiện ở cả hai danh sách.

Giải pháp cần có retry thao tác xóa, thông tin khóa cũ, kiểm tra trạng thái chuẩn khi thực hiện hành động quan trọng, và **job reconciliation** để tìm/dọn các bản ghi lỗi tồn tại lâu.

### 11.4. Một trạng thái chuẩn và nhiều bản sao phục vụ đọc

Một nguyên tắc thiết kế:

> Mỗi trường nghiệp vụ cần xác định **nơi quyết định giá trị chuẩn** và **các view chỉ phục vụ đọc**.

Ví dụ `orders_by_id` hoặc hệ thống giao dịch nguồn quyết định trạng thái đơn cuối cùng. Hai bảng còn lại là các hình chiếu để truy cập nhanh. Khi phát hiện khác biệt, nguồn chuẩn là căn cứ sửa view.

Không nên dựa vào hành vi **last-write-wins** ngầm định để quyết định điều gì là trạng thái nghiệp vụ mới nhất, đặc biệt khi nhiều worker dùng đồng hồ và thứ tự xử lý khác nhau.

## 12. Batch trong Cassandra có thay thế giao dịch nhiều bảng không?

Đây là một nhầm lẫn phổ biến khi học về phi chuẩn hóa trong wide-column.

Cassandra hỗ trợ **batch statements**, trong đó có logged batch. Tuy nhiên, batch **không mang đầy đủ ý nghĩa của transaction ACID xuyên nhiều bảng** theo cách thường mong đợi ở cơ sở dữ liệu quan hệ:

- Batch không cung cấp cơ chế **cô lập (isolation)** tổng quát cho các đọc xen kẽ trên nhiều partition.
- Một người đọc có thể thấy một số cập nhật trước khi toàn bộ hình chiếu được cập nhật và hội tụ.
- Logged batch có cơ chế hỗ trợ hoàn tất các đột biến trong trường hợp lỗi, nhưng không có nghĩa mọi bảng luôn được quan sát như cùng chuyển trạng thái trong một thời điểm.
- Batch trải qua nhiều partition có thể gây overhead và không nên dùng làm mẹo tăng throughput cho các ghi độc lập.

Ví dụ cú pháp minh họa:

```sql
BEGIN BATCH
  INSERT INTO orders_by_id
  (order_id, customer_id, seller_id, created_at,
   status, total_cents, currency)
  VALUES (?, ?, ?, ?, ?, ?, ?);

  INSERT INTO orders_by_customer_month
  (customer_id, bucket_month, created_at, order_id,
   seller_id, status, total_cents, currency)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?);
APPLY BATCH;
```

Không nên suy từ việc cú pháp có `BEGIN BATCH` ra rằng đọc từ hai bảng trong mọi thời điểm sẽ nhìn thấy cùng một trạng thái. Nếu nghiệp vụ đòi hỏi nhất quán giao dịch nhiều thực thể, phải thiết kế cơ chế riêng có thể chứng minh đáp ứng ràng buộc đó.

### 12.1. Consistency level và read model khác nhau là hai vấn đề

Cassandra có các mức nhất quán đọc/ghi như `ONE` hoặc `QUORUM` tùy topology. Mức nhất quán điều chỉnh số bản sao cần xác nhận/đáp ứng **trong phạm vi dữ liệu được truy cập**.

Ngay cả khi đọc/ghi một hàng với mức nhất quán mạnh hơn, điều đó **không tự đảm bảo**:

- `orders_by_id` và `orders_by_customer_month` có cùng phiên bản;
- hai bảng view cập nhật đồng thời;
- chuỗi cập nhật trạng thái nhiều bảng là một giao dịch cô lập.

**Replication giữa các node** và **denormalization giữa các bảng** giải quyết hai vấn đề khác nhau. Bảo đảm của replication không thay thế quy trình duy trì dữ liệu lặp.

## 13. Chi phí của việc lặp dữ liệu

### 13.1. Write amplification

Giả sử 250 đơn hàng mới mỗi giây, một đơn được ghi vào ba bảng:

```text
250 đơn/s × 3 bảng = 750 logical row writes/s
```

Đây là **số lượt ghi logic để tạo read model** trước khi tính đến replication, index, commit log, compaction và những thao tác ghi lại do retry.

Nếu mỗi đơn chuyển trạng thái 3 lần, và mỗi lần cập nhật đụng đến nhiều view, chi phí cập nhật có thể vượt xa chi phí tạo ban đầu.

Không nhất thiết mọi bảng đều cần cập nhật mọi trường:

- `total_cents` ít thay đổi sau khi xác nhận đơn; sao chép để đọc danh sách có thể hợp lý.
- `status` thay đổi nhiều lần; khi nằm trong partition key, đổi trạng thái đòi hỏi di chuyển hàng.
- Dữ liệu profile khách hàng thường thay đổi độc lập; sao chép email hiện tại vào từng đơn có thể dẫn đến cập nhật hàng loạt không cần thiết.

### 13.2. Storage amplification

Giả sử một đơn chiếm trung bình:

| Bảng | Kích thước logic minh họa/đơn |
|---|---:|
| `orders_by_id` | 650 byte |
| `orders_by_customer_month` | 300 byte |
| `orders_by_seller_status_month` | 250 byte |
| **Tổng ba bảng** | **1.200 byte** |

Với 10 triệu đơn, riêng dữ liệu logic minh họa khoảng **12 GB** trước metadata, replication, nén, index, tombstone và overhead lưu trữ. Kích thước thật phụ thuộc kiểu dữ liệu, cách mã hóa, phân vùng và storage engine.

Nếu chỉ có bảng chính 650 byte/đơn, tổng logic là khoảng 6,5 GB. Việc thêm view có chi phí dung lượng, nhưng có thể tránh nhiều truy vấn N+1 và giảm thời gian phản hồi cho người dùng. Cần đo **tổng chi phí ứng dụng**, thay vì chỉ tối thiểu hóa số byte lưu.

### 13.3. Nhiều bảng hơn nghĩa là nhiều trách nhiệm vận hành

Mỗi bảng mới có thể đòi hỏi:

- Thiết kế partition/clustering key và kiểm soát phân phối tải;
- Theo dõi p95/p99, kích thước partition, đọc/ghi theo node;
- Quản lý TTL, backup, restore và retention;
- Quy trình cập nhật khi thêm trường hoặc thay đổi schema;
- Xử lý lỗi replay, rebuild, reconciliation;
- Kiểm soát dữ liệu nhạy cảm bị sao chép vào nhiều nơi;
- Kiểm tra quyền truy cập và chính sách xóa dữ liệu.

“Truy vấn nhanh hơn” chưa đủ; các lợi ích cần vượt chi phí trên.

## 14. Chọn khóa phân vùng cho từng đường truy cập

### 14.1. Không tạo partition vô hạn

Ví dụ chỉ dùng `customer_id` cho mọi đơn của một khách trong 10 năm có thể tạo partition lớn. Giới hạn bằng tháng/ngày giúp dễ quản lý và truy vấn trong khoảng tương ứng.

Tuy nhiên, **một đơn vị thời gian phù hợp với khách nhỏ có thể vẫn quá lớn với khách rất lớn**. Một marketplace có người bán xử lý hàng trăm nghìn đơn/ngày có thể cần thêm bucket/shard.

Ví dụ khóa có bổ sung:

```text
(seller_id, status, day, bucket)
```

Ứng dụng có thể tính `bucket` theo hash ổn định của `order_id`. Nhờ vậy, các đơn của một người bán lớn được phân phối vào nhiều partition.

### 14.2. Mỗi bucket mới làm việc đọc khó hơn

Nếu dùng 8 bucket cho một `seller_id` trong ngày, để lấy 20 đơn mới nhất toàn bộ người bán:

1. Ứng dụng có thể phải truy vấn cả 8 partition.
2. Mỗi partition trả một đoạn kết quả đã sắp xếp.
3. Ứng dụng gộp theo timestamp và khóa phụ để chọn 20 đơn.
4. Phân trang cần giữ thông tin vị trí ở từng nguồn hoặc dùng chiến lược tương đương.

Bổ sung bucket có thể giảm hot partition nhưng **tăng fan-out**. Phải tìm điểm cân bằng bằng benchmark theo dữ liệu thật.

### 14.3. Cẩn trọng với khóa trạng thái

`status` thường có ít giá trị. Nếu partition key **chỉ** là trạng thái `CREATED`, tất cả đơn mới có thể dồn vào một partition rất lớn/hot.

Ghép `seller_id`, thời gian và, khi cần, bucket giúp phân tán tốt hơn. Tuy nhiên, một seller có tải cực lớn vẫn có thể nóng trong một bucket; cần nhìn phân phối thực tế, không chỉ số lượng giá trị trên lý thuyết.

### 14.4. Đổi thuộc tính trong khóa khác với đổi thuộc tính thường

Thay `status` ở bảng theo trạng thái cần thao tác xóa/thêm. Thay `total_cents` là cột thường trong bảng theo khách có thể cập nhật tại cùng khóa.

Vì vậy, hãy hỏi trước khi đặt trường vào primary key: **Trường này có đổi sau khi tạo bản ghi không? Nếu có, tần suất và chi phí di chuyển hàng là bao nhiêu?**

## 15. Xóa, TTL và tombstone trên các bản sao

### 15.1. Xóa phải đi qua mọi read model liên quan

Giả sử cần xóa đơn hàng khỏi hệ thống theo chính sách giữ dữ liệu. Xóa hàng ở `orders_by_id` **không tự động xóa** các hàng cùng đơn ở `orders_by_customer_month` và `orders_by_seller_status_month`.

Cần kế hoạch xác định:

- Đơn hàng có mặt ở những view nào?
- Khóa đầy đủ của từng hàng là gì?
- Trạng thái/bucket cũ phải lấy từ đâu?
- Nếu một bước xóa thất bại, ai sẽ retry?
- Làm sao phát hiện view còn sót?
- Nếu hệ thống tìm kiếm, cache hoặc data warehouse cũng chứa dữ liệu, cách xóa được lan truyền ra sao?

Việc lặp dữ liệu làm yêu cầu **xóa dữ liệu và bảo vệ dữ liệu cá nhân** phức tạp hơn. Không nên để read model trở thành nơi còn lưu thông tin sau khi nguồn chính đã được xử lý theo chính sách.

### 15.2. TTL không đồng nghĩa dữ liệu biến mất ngay

Trong Cassandra, TTL và thao tác xóa có thể tạo **tombstone**. Tombstone là thông tin đánh dấu dữ liệu đã bị xóa/hết hạn để hệ thống phân tán có thể đồng bộ và tránh phục hồi dữ liệu cũ không phù hợp.

Nếu dùng TTL khác nhau cho các bảng, một đơn có thể biến mất khỏi bảng lịch sử nhưng vẫn tồn tại ở bảng chính hoặc ngược lại. Điều này chỉ hợp lý nếu **chính sách retention của từng read model đã được định nghĩa**.

Nhiều tombstone hoặc kiểu truy vấn quét qua phạm vi có nhiều dữ liệu đã hết hạn có thể làm tăng chi phí đọc/compaction. Cần theo dõi cơ chế tombstone và vận hành repair/compaction theo hướng dẫn của sản phẩm, thay vì coi TTL là cách dọn dữ liệu miễn phí.

### 15.3. Những dữ liệu không nên sao chép tùy tiện

Ví dụ, thông tin thanh toán nhạy cảm hoặc các trường có chính sách truy cập nghiêm ngặt không nên được đưa vào mọi bảng danh sách chỉ để tiện đọc. Đưa dữ liệu đến nhiều vị trí làm tăng bề mặt quản lý quyền truy cập, mã hóa, sao lưu và xóa.

Nguyên tắc thực dụng: **sao chép những trường đủ để trả lời truy vấn, không sao chép toàn bộ thực thể theo thói quen**.

## 16. Khi thêm một đường truy cập mới

Sau khi triển khai, nhóm sản phẩm muốn thêm trang “mọi đơn trên 1.000 USD trong tuần này, bất kể người bán và khách hàng”.

Ba bảng hiện tại được thiết kế cho:

- Theo `order_id`;
- Theo `customer_id` và tháng;
- Theo `seller_id`, `status` và tháng.

Không bảng nào có đường truy cập tự nhiên cho một truy vấn **toàn hệ thống theo khoảng tiền và thời gian**. Những cách giải quyết có thể là:

1. **Thêm một bảng read model mới** nếu đây là truy vấn quan trọng, có bộ lọc cố định và có cách tạo partition tránh nóng.
2. **Dùng chỉ mục/search engine** nếu công nghệ hiện tại và khối lượng dữ liệu phù hợp.
3. **Đưa sự kiện/đơn hàng sang hệ phân tích OLAP/warehouse** nếu mục tiêu là báo cáo quy mô lớn và nhiều chiều.
4. **Xây API báo cáo bất đồng bộ** nếu không cần trả kết quả ngay ở đường giao dịch.

Không nhất thiết tạo bảng Cassandra cho mọi ý tưởng báo cáo ad hoc. Wide-column thuận lợi nhất khi **mẫu truy vấn có thể xác định trước** và thiết kế khóa mang lại lợi ích rõ ràng.

### 16.1. Backfill bảng mới

Khi thêm một view mới, những đơn hàng đã tồn tại trước đó cần được **backfill** để trang mới trả đầy đủ dữ liệu.

Một quy trình khả thi:

```text
1. Xây schema và logic tạo view mới.
2. Xác định nguồn dữ liệu chuẩn và mốc lịch sử cần backfill.
3. Bắt đầu thu nhận các thay đổi mới có thể replay.
4. Nạp dữ liệu cũ theo từng lô có giới hạn tải.
5. Áp dụng các thay đổi phát sinh trong lúc backfill.
6. Đối soát số lượng và nội dung theo khóa nghiệp vụ.
7. Chuyển dần traffic đọc sang view mới.
8. Tiếp tục theo dõi lag và sai lệch.
```

Rủi ro là dữ liệu cũ được backfill **sau** khi một cập nhật mới hơn đã đi vào view, rồi ghi đè trạng thái mới. Cần phiên bản/chiến lược ordering, không thể chỉ “quét hết bảng nguồn và insert” một cách vô điều kiện.

## 17. Đánh giá hiệu quả bằng số liệu

Một thiết kế phi chuẩn hóa nên được kiểm tra ở **mức tải thực tế**, gồm cả đọc lẫn ghi.

### 17.1. Ví dụ mục tiêu đo lường

Giả sử hệ thống dự kiến:

- 250 đơn hàng mới mỗi giây vào giờ cao điểm.
- 500 lượt đổi trạng thái/giây.
- 3.000 lượt đọc lịch sử khách hàng/giây.
- 1.000 lượt đọc hàng chờ người bán/giây.
- Mỗi trang danh sách thường lấy 20 hàng.

Một bộ tiêu chí minh họa:

| Chỉ số | Điều muốn biết |
|---|---|
| p95/p99 đọc lịch sử khách | Có giữ trong ngưỡng phản hồi API tại tải dự kiến? |
| p95/p99 đọc hàng chờ người bán | Có phát sinh fan-out/hot partition? |
| Throughput ghi và độ trễ ghi | Có đáp ứng tạo đơn và đổi trạng thái? |
| Projector lag | View chậm cập nhật so với nguồn chính bao lâu? |
| Tỷ lệ view sai lệch | Có đơn xuất hiện sai trạng thái hoặc thiếu khỏi danh sách không? |
| Kích thước partition | Có người bán/khách lớn tạo partition quá lớn? |
| Tombstone, compaction, I/O | Chi phí xóa/chuyển trạng thái có đang tăng? |
| Dung lượng mỗi view | Lợi ích truy vấn có xứng với chi phí lưu trữ? |

Các con số tải chỉ để minh họa; mục tiêu chất lượng cụ thể phải dựa trên yêu cầu sản phẩm.

### 17.2. Kiểm thử các trường hợp lỗi

Không chỉ thử “tạo đơn rồi đọc thấy đơn”. Cần mô phỏng:

- Ghi nguồn chính thành công nhưng cập nhật một view thất bại.
- Event bị gửi lại 2–3 lần.
- Event `PAID` đến sau event `SHIPPED`.
- Thao tác xóa khóa cũ thất bại sau khi thêm khóa mới.
- Backfill chạy đồng thời với traffic thật.
- Một khách hàng hoặc người bán có lượng đơn lớn bất thường.
- Một node chậm, replica lag hoặc mạng gián đoạn.

Kết quả phải trả lời được câu hỏi: hệ thống **phát hiện, sửa và đo được độ lệch** hay sẽ giữ dữ liệu sai âm thầm?

## 18. Những sai lầm thường gặp

### Sai lầm 1: Thiết kế một bảng rồi mong `WHERE` nào cũng nhanh

Trong wide-column, partition key và clustering key là phần cốt lõi của đường truy cập. Bộ lọc không phù hợp có thể buộc quét rộng, bị từ chối hoặc phụ thuộc index riêng. Cần thiết kế bảng từ câu truy vấn thực tế.

### Sai lầm 2: Coi phi chuẩn hóa là sao chép toàn bộ bản ghi

Chỉ sao chép trường cần thiết cho màn hình/truy vấn. Bản sao càng lớn, chi phí cập nhật, dung lượng và quản lý dữ liệu càng cao.

### Sai lầm 3: Coi batch là transaction ACID xuyên bảng

Batch và mức nhất quán replica không mặc định tạo ảnh chụp nhất quán tức thời cho nhiều bảng. Cần cơ chế nghiệp vụ phù hợp khi dữ liệu có ràng buộc chặt.

### Sai lầm 4: Không xử lý event đến sai thứ tự

Chỉ có retry là chưa đủ. Retry cũ có thể ghi đè giá trị mới nếu thiếu chiến lược version/order. Bảng theo trạng thái còn có thể xuất hiện bản ghi cũ chưa bị xóa.

### Sai lầm 5: Dùng partition key có quá ít giá trị

Bảng khóa chỉ bằng `status = CREATED` có thể khiến mọi đơn đang chờ tập trung ở một partition. Cần phân phối theo chủ thể và thời gian/bucket phù hợp.

### Sai lầm 6: Mặc định một bảng mới không ảnh hưởng đường ghi

Thêm view nghĩa là thêm xử lý và thường thêm storage/write amplification. Phải tính chi phí, độ trễ đồng bộ và quy trình rebuild.

### Sai lầm 7: Quên xóa và chính sách retention của bản sao

Xóa nguồn chính nhưng quên một bảng phụ có thể để dữ liệu cũ tồn tại. TTL khác nhau mà không có thiết kế có thể gây dữ liệu hiển thị thiếu hoặc sai.

### Sai lầm 8: Dùng bảng read model để quyết định giao dịch quan trọng mà không xác minh trạng thái

Một hàng chờ có thể chưa kịp nhận sự kiện trạng thái mới. Thao tác nghiệp vụ cần dựa trên nguồn trạng thái có bảo đảm đúng đắn được xác định rõ.

## 19. Bài tập thực hành

### Bài tập 1: chọn khóa cho lịch sử sự kiện

Một dịch vụ lưu `device_id`, `occurred_at`, `event_type`, `payload`. Giao diện thường lấy 100 sự kiện gần nhất của một thiết bị trong ngày.

**Yêu cầu:** Đề xuất partition key và clustering key. Có cần sao chép `event_type` vào bảng đọc không?

**Gợi ý:** Có thể dùng `(device_id, event_day)` làm partition key, `occurred_at DESC, event_id` làm clustering key. Nếu danh sách sự kiện luôn hiển thị loại sự kiện, sao chép `event_type` giúp trả kết quả trong một lần đọc. Cần đánh giá partition lớn với thiết bị ghi quá nhiều.

### Bài tập 2: thêm truy vấn theo loại sự kiện

Từ bảng bài tập 1, nay cần “lấy các sự kiện `ERROR` gần nhất của thiết bị D”. Bảng cũ có partition theo device/day và clustering theo thời gian.

**Yêu cầu:** Nêu ít nhất hai cách giải quyết và đánh đổi.

**Gợi ý:** Có thể thêm bảng `events_by_device_type_day` với `event_type` trong partition key, thuận lợi cho đọc nhưng tăng ghi/đồng bộ; hoặc dùng index/chức năng lọc thích hợp của database nếu thỏa workload thực tế. Không nên coi việc thêm `WHERE event_type = 'ERROR'` là tự nhiên hiệu quả khi không có đường truy cập.

### Bài tập 3: chuyển trạng thái đơn hàng

Một đơn đã có trong `orders_by_seller_status_month` với `status = CREATED`. Trạng thái chuyển thành `PAID`.

**Yêu cầu:** Những tác động nào phải thực hiện ở ba bảng? Điều gì xảy ra nếu chỉ cập nhật hai bảng đầu?

**Gợi ý:** Cập nhật trạng thái ở `orders_by_id` và `orders_by_customer_month`; với bảng theo trạng thái cần xóa hàng khóa `CREATED` và thêm hàng khóa `PAID`. Nếu bỏ bước cuối, hàng chờ người bán hiển thị dữ liệu cũ.

### Bài tập 4: tìm lỗi do thứ tự event

Projector nhận `OrderCreated(v1)`, `OrderShipped(v3)` rồi `OrderPaid(v2)`.

**Yêu cầu:** Vì sao chỉ dùng `INSERT/UPDATE` không đủ? Thiết kế nào giúp khắc phục?

**Gợi ý:** Một event cũ có thể ghi trạng thái `PAID` sau `SHIPPED` nếu không có ordering/version guard. Có thể phân vùng xử lý theo order ID, dùng version check phù hợp phạm vi nguyên tử hoặc xây dựng lại view theo nguồn chính. Cần kiểm thử retry, timestamp và tombstone.

### Bài tập 5: ước lượng write amplification

Hệ nhận 800 đơn/s và ghi 4 read model mỗi đơn. Mỗi đơn sau đó có trung bình 2 lần thay đổi trạng thái; mỗi lần ảnh hưởng 3 read model bằng ít nhất một thao tác logic/bảng.

**Yêu cầu:** Ước lượng số lượt ghi logic tối thiểu do tạo và cập nhật đơn, chưa tính replication, xóa+thêm khóa, retry và index.

**Gợi ý:**

```text
Tạo mới:   800 × 4      = 3.200 logical writes/s
Cập nhật:  800 × 2 × 3  = 4.800 logical writes/s
Tổng tối thiểu           = 8.000 logical writes/s
```

Phép tính giả định tải trạng thái đã ổn định theo cùng tốc độ đơn; các thay đổi cần xóa + thêm hàng thực tế có thể làm số thao tác cao hơn.

### Bài tập 6: thiết kế đường truy cập mới

Nhóm vận hành cần báo cáo “tổng doanh thu 12 tháng của tất cả người bán theo thành phố”, không có sẵn `seller_id` ở đầu vào.

**Yêu cầu:** Có nên dùng các bảng đơn hàng `orders_by_seller_status_month` cho báo cáo này không?

**Gợi ý:** Các bảng hiện tại tối ưu truy vấn theo người bán/trạng thái/tháng. Báo cáo tổng hợp xuyên nhiều người bán và nhiều chiều có thể phải đọc rất nhiều partition. Nên xem xét một bảng tổng hợp được cập nhật riêng hoặc hệ OLAP/warehouse, tùy yêu cầu độ mới của số liệu.

## 20. Kết luận

Trong mô hình cột rộng, **lặp dữ liệu giữa các bảng là cách đổi thêm lưu trữ và công ghi để lấy đường truy cập đọc phù hợp hơn**. Mỗi bảng được thiết kế từ điều kiện truy vấn: khóa phân vùng giúp tìm đúng nhóm dữ liệu, khóa clustering giúp đọc theo thứ tự mong muốn, còn các cột được sao chép giúp trả lời ngay nội dung mà ứng dụng cần.

Việc lặp dữ liệu chỉ thực sự có ích khi hệ thống quản lý được **nguồn sự thật, thứ tự cập nhật, thao tác xóa, retry, dữ liệu đến trễ, giới hạn partition và độ lệch giữa các view**. Vì vậy, sau khi mô tả truy vấn, bước thiết kế quan trọng không kém là mô tả **một thay đổi nghiệp vụ sẽ đi qua những bảng nào và hệ thống sẽ tự phục hồi ra sao khi chỉ một phần cập nhật thành công**.
