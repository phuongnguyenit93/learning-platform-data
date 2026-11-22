# COUNT, hàm tổng hợp và chi phí đọc thực tế trong Apache Cassandra

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt ý nghĩa của `COUNT(*)`, `COUNT(1)` và `COUNT(column)`, đặc biệt khi một cột không có giá trị.
2. Sử dụng các hàm tổng hợp cơ bản `MIN`, `MAX`, `SUM`, `AVG`, `CAST` và hiểu kiểu dữ liệu, độ chính xác, nguy cơ tràn số.
3. Viết truy vấn tổng hợp có phạm vi rõ ràng nhờ **partition key**, **clustering columns** và khoảng thời gian trong một partition.
4. Giải thích vì sao `SELECT COUNT(*) FROM table` có thể rất chậm hoặc timeout trên Cassandra phân tán, ngay cả khi kết quả chỉ có một số.
5. Hiểu giới hạn của `LIMIT`, `PER PARTITION LIMIT`, paging và `GROUP BY` khi kết hợp với aggregate.
6. Lựa chọn giữa **đếm trực tiếp**, **duy trì bảng tổng hợp**, **counter** và **pipeline tổng hợp** theo yêu cầu độ trễ, độ chính xác và độ mới dữ liệu.
7. Đọc kết quả aggregate từ Java Driver, đồng thời biết cách đo và xử lý lỗi khi phép đếm đụng nhiều partition, tombstone hoặc replica.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trong Apache Cassandra, dữ liệu được phân tán bằng partition key và sắp theo clustering columns trong từng partition. Vì vậy, **một ô kết quả nhỏ không đồng nghĩa một truy vấn rẻ**: để tính được ô đó, hệ thống có thể phải duyệt rất nhiều dòng từ nhiều replica. Đây cũng là nền tảng để thiết kế API Java an toàn, lựa chọn consistency, và hiểu tác động của compaction, repair, TTL cùng các tình huống lỗi thực tế.

## 1. COUNT trong CQL đang đếm cái gì?

Giả sử bảng chứa các dòng đơn hàng, một vài dòng chưa có số tiền cuối cùng:

| Hàm | Ý nghĩa | Lưu ý quan trọng |
| --- | --- | --- |
| `COUNT(*)` | Số **dòng còn hiệu lực** khớp truy vấn | Không phải tổng số cell vật lý, SSTable record hay tombstone. |
| `COUNT(1)` | Dạng tương đương `COUNT(*)` trong CQL | Không nhanh hơn đáng kể chỉ vì viết `1`. |
| `COUNT(amount_cents)` | Số dòng khớp có **giá trị khác null** ở `amount_cents` | Có thể nhỏ hơn `COUNT(*)`. |
| `COUNT(status)` | Số giá trị `status` khác null trong tập dòng khớp | Không phải số **trạng thái khác nhau**. |

Không đánh đồng:

- **Số dòng:** bao nhiêu primary key còn có dữ liệu phù hợp để trả về.
- **Số partition:** bao nhiêu full partition key cần xác định/đọc.
- **Số giá trị non-null:** bao nhiêu dòng có một cột cụ thể hiện diện.
- **Số giá trị phân biệt:** bao nhiêu giá trị khác nhau; `COUNT(column)` không tự làm `DISTINCT`.
- **Số phiên bản vật lý phải kiểm tra:** phụ thuộc memtable, SSTable, TTL, tombstone, compaction và tình trạng replica, không được phản ánh trực tiếp bởi kết quả `COUNT`.

Ví dụ một partition có 5 dòng nhưng chỉ 4 dòng có `amount_cents`: `COUNT(*) = 5`, `COUNT(amount_cents) = 4`. Mọi câu đếm đều đang tính trên **tập dòng khớp** tại thời điểm và mức nhất quán của lần đọc.

## 2. Bảng lab: đơn hàng theo cửa hàng và tháng

Ứng dụng muốn hiển thị số đơn, tổng tiền, giá trị nhỏ nhất/lớn nhất theo **một cửa hàng trong một tháng**. Chúng ta thiết kế bảng theo truy vấn đó:

```sql
-- Chỉ dành cho lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_aggregate_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_aggregate_lab;

CREATE TABLE IF NOT EXISTS orders_by_store_month (
    store_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at ASC, order_id ASC);
```

### 2.1. Vì sao dùng khóa này?

| Thành phần | Loại | Vai trò |
| --- | --- | --- |
| `(store_id, month_bucket)` | **Composite partition key** | Mỗi cửa hàng/tháng là một partition; Cassandra tính token từ cả hai giá trị. |
| `created_at` | Clustering column thứ nhất | Cho phép chọn khoảng thời gian **trong một partition**. |
| `order_id` | Clustering column thứ hai | Phân biệt các đơn có thể cùng timestamp; hoàn thiện primary key. |
| `status`, `amount_cents` | Regular columns | Lưu trạng thái và tiền; không có đường truy cập theo riêng các cột này trong schema lab. |

Thứ tự `ASC` ở đây phục vụ ví dụ duyệt theo thời gian. Nó **không** làm cho các partition của cùng cửa hàng tự nằm kề nhau theo tháng: `month_bucket` là một phần partition key, không phải clustering column.

### 2.2. Tạo tám dòng mẫu

```sql
-- Cửa hàng A, tháng 11: ba dòng ngày 20.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'PAID', 10000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'CREATED', 15000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'PAID', 30000
);

-- Cửa hàng A, tháng 11: hai dòng ngày 21.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAID', 20000
);

-- Đơn hủy chưa có amount_cents: cố ý bỏ cột khi INSERT.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21 11:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'CANCELLED'
);

-- Cửa hàng A, tháng 12: hai dòng thuộc partition khác.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01 08:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'PAID', 50000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01 09:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'REFUNDED', 70000
);

-- Cửa hàng B, tháng 11: partition thứ ba.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, created_at, order_id, status, amount_cents)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'PAID', 80000
);
```

**Tóm tắt dữ liệu của bảng mới tạo:**

| Partition | Dòng còn hiệu lực | Dòng có `amount_cents` | Tổng tiền (cents) |
| --- | ---: | ---: | ---: |
| Cửa hàng A / `2026-11` | 5 | 4 | 75.000 |
| Cửa hàng A / `2026-12` | 2 | 2 | 120.000 |
| Cửa hàng B / `2026-11` | 1 | 1 | 80.000 |
| **Toàn bảng lab** | **8** | **7** | **275.000** |

Các kết quả số dưới đây giả định **chỉ có tám dòng mẫu**, chưa bị TTL/xóa hoặc sửa bởi request khác. Vì primary key được khai báo cố định, chạy lại cùng `INSERT` là upsert, không tạo dòng trùng khóa. Cũng nên lưu ý: `month_bucket` là chuỗi quy ước tháng nghiệp vụ; hệ thống thật phải kiểm tra nó thống nhất với múi giờ và `created_at`.

## 3. COUNT(*) theo đúng một partition

### 3.1. Đếm các đơn của một cửa hàng trong một tháng

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

**Kết quả:** `order_count = 5`.

Coordinator dùng cặp `(store_id, month_bucket)` để tìm partition và những replica liên quan. Nhưng sau khi tìm thấy partition, Cassandra còn phải **xử lý các dòng cần thiết để đếm**, thay vì lấy số 5 từ một bộ đếm giao dịch luôn có sẵn trong metadata của bảng.

So với truy vấn đếm toàn bảng, cách này có **phạm vi partition được xác định rõ**. Tuy vậy, nếu một partition chứa hàng triệu dòng hoặc nhiều tombstone, `COUNT(*)` trong đúng một partition vẫn có thể tốn kém.

```sql
-- COUNT(1) là dạng tương đương để đếm dòng.
SELECT count(1) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Đừng chọn `COUNT(1)` vì kỳ vọng nó nhanh hơn `COUNT(*)`: cả hai vẫn phải xét tập dòng khớp.

### 3.2. COUNT(column) bỏ qua những dòng thiếu giá trị ở cột

```sql
SELECT count(*) AS total_orders,
       count(amount_cents) AS priced_orders,
       count(status) AS orders_with_status
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

| Kết quả | Giá trị | Tại sao |
| --- | ---: | --- |
| `total_orders` | 5 | Có năm primary key của đơn hàng trong partition. |
| `priced_orders` | 4 | Đơn `CANCELLED` có giá trị `amount_cents` không hiện diện. |
| `orders_with_status` | 5 | Cả năm dòng đều có `status`. |

CQL không cho phép suy luận “`COUNT(status) = số loại trạng thái`”. Trong năm dòng, `PAID` xuất hiện ba lần, nhưng `COUNT(status)` vẫn là **5**, không phải số giá trị khác nhau. Nếu sản phẩm cần “số đơn theo trạng thái”, đó là **nhóm theo trạng thái**, không phải đếm các giá trị non-null của một cột.

### 3.3. Truy vấn một dòng theo khóa đầy đủ

```sql
SELECT count(*) AS matched_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

Đây là **full primary-key lookup**, nên `matched_count` tối đa bằng một. Nhưng nếu API đã có toàn bộ khóa và chỉ cần kiểm tra sự tồn tại, có thể đọc một cột khóa:

```sql
SELECT order_id
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

Nếu không có dòng, kết quả rỗng. Nếu có dòng, trả về `order_id`. Cách này thể hiện ý định **kiểm tra tồn tại**, không yêu cầu aggregate khi không cần thiết; trong hệ thống phân tán, mức consistency vẫn quyết định dữ liệu mà request có thể quan sát.

## 4. COUNT trong một khoảng clustering

Với bảng lab, `created_at` là clustering column đầu tiên. Sau khi cố định đầy đủ partition key, có thể đếm một cửa sổ thời gian.

### 4.1. Khoảng nửa mở [start, end)

```sql
SELECT count(*) AS morning_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 10:00:00+0000';
```

**Kết quả:** `morning_orders = 2`, do hai đơn lúc 09:00 và 09:30. Đơn lúc 08:00 nằm ngoài khoảng, các đơn ngày 21 cũng vậy.

Hai lớp lọc:

```text
Partition key:
  (store A, month 2026-11)
       |
       +-- created_at theo thứ tự ASC
           20/11 08:00  -- ngoài khoảng
           20/11 09:00  -- được đếm
           20/11 09:30  -- được đếm
           21/11 10:00  -- ngoài khoảng
           21/11 11:00  -- ngoài khoảng

COUNT(*) = 2
```

Sử dụng cận `>=` ở đầu và `<` ở cuối tránh đếm trùng dòng đúng điểm giao nhau giữa hai cửa sổ liền kề. Nếu bài toán phân nhóm theo ngày địa phương, nên tính đầu và cuối ngày bằng quy tắc múi giờ nghiệp vụ, không tự đồng nhất ngày địa phương với UTC.

### 4.2. Giới hạn clustering không biến cột thường thành chỉ mục

Truy vấn sau không được hỗ trợ theo đường khóa thông thường của schema lab:

```sql
-- status không là partition key, clustering column hoặc index.
SELECT count(*) AS paid_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND status = 'PAID';
```

Dù chỉ có một partition, Cassandra **không có sẵn một vùng clustering liên tục theo `status`** để dùng điều kiện này. Một số câu truy vấn có thể thực hiện khi thêm `ALLOW FILTERING` hoặc chỉ mục phù hợp, nhưng điều đó không khiến việc đếm trở thành O(1).

Để đếm `PAID` thường xuyên, xem xét:

- Một **bảng đọc theo trạng thái** với partition key/clustering phù hợp.
- Một **bảng summary** theo `(store_id, month_bucket, status)` được cập nhật theo luồng dữ liệu.
- Một chỉ mục phù hợp với phiên bản Cassandra (chẳng hạn SAI) **khi thực sự đáp ứng độ chọn lọc và tải đọc**; vẫn phải đo chi phí aggregate.

Không thêm `ALLOW FILTERING` chỉ để một ví dụ `COUNT` chạy được mà bỏ qua rủi ro quét dòng.

## 5. COUNT qua nhiều partition và toàn bảng

### 5.1. Hai tháng đã biết của cùng cửa hàng

```sql
SELECT count(*) AS order_count,
       count(amount_cents) AS priced_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

Với dữ liệu mẫu, `order_count = 7`, `priced_orders = 6`. Đây là một aggregate trên những dòng thuộc **hai partition đầy đủ**:

```text
(store A, 2026-11) -> 5 đơn, 4 đơn có tiền
(store A, 2026-12) -> 2 đơn, 2 đơn có tiền
                     ------------------------
Tổng                     7             6
```

Điều kiện `IN` trên `month_bucket` (thành phần cuối của composite partition key) liệt kê những partition ứng viên. Danh sách dài hơn sẽ tăng phạm vi cần đọc/điều phối, ngay cả khi số dòng trả về của aggregate vẫn chỉ là **một dòng**.

### 5.2. COUNT toàn bảng: ví dụ cần tránh ở production

```sql
-- Chỉ minh họa trong keyspace lab nhỏ; không chạy tùy tiện
-- trên bảng production có số lượng partition lớn.
SELECT count(*) AS total_orders
FROM orders_by_store_month;
```

Trên dữ liệu mẫu, kết quả là **8**. Nhưng trong cluster thật, thiếu `WHERE` có nghĩa không có một khóa phân vùng cụ thể để định vị. Cassandra có thể phải duyệt **toàn bộ token range/partition của bảng**, liên hệ nhiều node và xử lý rất nhiều dữ liệu.

Nếu bảng lớn:

- Coordinator phải điều phối công việc trên nhiều partition và replica.
- Việc đếm các dòng **còn sống** không thể mặc nhiên suy từ kích thước file, số SSTable hay thống kê ước lượng.
- TTL và tombstone làm tăng công việc xác minh dòng hợp lệ.
- Kết quả có thể timeout trước khi hoàn thành, dù câu lệnh chỉ yêu cầu **một giá trị `bigint`**.
- Những lần đọc riêng biệt ở các thời điểm khác nhau không tự tạo ra một snapshot giao dịch toàn bảng.

Một kết quả số duy nhất là **kích cỡ output**, không phải thước đo kích cỡ input mà Cassandra đã phải xử lý.

## 6. Hàm tổng hợp SUM, AVG, MIN, MAX

### 6.1. Các aggregate cơ bản

```sql
SELECT count(*) AS order_count,
       count(amount_cents) AS priced_count,
       sum(amount_cents) AS total_cents,
       min(amount_cents) AS min_cents,
       max(amount_cents) AS max_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

| Cột kết quả | Giá trị trong lab |
| --- | ---: |
| `order_count` | 5 |
| `priced_count` | 4 |
| `total_cents` | 75.000 |
| `min_cents` | 10.000 |
| `max_cents` | 30.000 |

`MIN(amount_cents)` và `MAX(amount_cents)` trả **giá trị** nhỏ nhất/lớn nhất, không phải toàn bộ dòng đơn hàng ứng với giá trị đó. Nếu cần biết `order_id` của đơn có tiền lớn nhất, hãy dùng một bảng/đường truy vấn phù hợp hoặc đọc và so sánh trên tập hữu hạn; đừng chọn kèm `order_id` rồi nghĩ đó chắc chắn là ID của dòng có `MAX`.

### 6.2. AVG trên kiểu số nguyên có thể làm mất phần thập phân

`amount_cents` là `bigint`. Các aggregate `SUM`/`AVG` phụ thuộc kiểu đầu vào; đối với kiểu số nguyên, nguy cơ **tràn số** hoặc **làm tròn/cắt phần thập phân** cần được xem xét. Với dữ liệu tiền, cách đơn giản là chuyển đầu vào sang kiểu thập phân trước khi tính:

```sql
SELECT avg(CAST(amount_cents AS decimal)) AS avg_cents_decimal,
       sum(CAST(amount_cents AS varint)) AS total_cents_wide
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Vì chỉ bốn dòng có số tiền, trung bình của chúng là:

```text
(10000 + 15000 + 30000 + 20000) / 4 = 18750 cents
```

Không chia cho `COUNT(*) = 5` khi quy tắc nghiệp vụ là trung bình trên **những đơn đã có số tiền**. Nếu sản phẩm quy ước đơn chưa có tiền bằng 0, đó là **quy tắc dữ liệu nghiệp vụ** khác, cần biểu diễn minh bạch ở tầng ghi/tổng hợp thay vì mặc định mọi `null` là zero.

Việc `CAST` sang `varint` trước `SUM` giúp chọn kiểu số nguyên có miền giá trị lớn hơn `bigint`, nhưng ứng dụng phải đọc đúng kiểu trả về. Hàm và chuyển kiểu được hỗ trợ tùy chữ ký hàm/phiên bản; cần kiểm thử trên Cassandra thực tế.

### 6.3. Aggregate không nhất thiết phản ánh số liệu kế toán cuối cùng

Ví dụ trên cộng số tiền của cả đơn `PAID`, `CREATED` và `REFUNDED` vì không có điều kiện trạng thái. Số `75.000` là tổng của những `amount_cents` hiện có trong **partition được đọc**, **không tự động là doanh thu đã thanh toán hoặc doanh thu thuần**.

Muốn “doanh thu đã thanh toán” hoặc “doanh thu sau hoàn tiền”, cần xác định:

1. Mỗi trạng thái nào được tính và quy tắc đổi trạng thái ảnh hưởng ra sao.
2. Giá trị nào đại diện cho khoản tiền thu, hoàn hay điều chỉnh.
3. Cách thiết kế dữ liệu hoặc summary để tính được số liệu theo quy tắc đó mà không quét nhiều cột thường.

Cassandra cung cấp primitive aggregate, chứ không tự hiểu định nghĩa kế toán của ứng dụng.

## 7. GROUP BY khi muốn một số liệu cho từng ngày

Trong bảng lab, full primary key là:

```sql
PRIMARY KEY ((store_id, month_bucket), created_at, order_id)
```

Chúng ta có thể **nhóm theo partition key hoặc tiền tố clustering key**, nhưng không tự do `GROUP BY status` như trong công cụ SQL phân tích.

Một ví dụ nhóm theo **ngày** dựa trên ngày của timestamp sẽ cần một mô hình dữ liệu phù hợp. Với schema hiện tại, `created_at` là timestamp đầy đủ, không phải `order_day`; mỗi thời điểm khác nhau là một giá trị clustering khác nhau. Do đó:

```sql
-- Hợp lệ theo primary-key prefix, nhưng nhóm theo timestamp CHÍNH XÁC,
-- không phải tự động theo ngày.
SELECT created_at, count(*) AS orders_at_timestamp
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, created_at;
```

Với dữ liệu mẫu, các timestamp đều khác nhau nên có **năm nhóm**, mỗi nhóm đếm một dòng. Đây không phải báo cáo “ngày 20: ba đơn, ngày 21: hai đơn”.

Để báo cáo theo ngày là đường truy vấn chính, một bảng đọc phù hợp có thể thêm `order_day` làm clustering column đầu tiên:

```sql
CREATE TABLE IF NOT EXISTS orders_by_store_month_day (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_id uuid,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day ASC, order_id ASC);
```

Khi ứng dụng **ghi dữ liệu vào bảng thứ hai** theo cùng sự kiện nghiệp vụ, có thể truy vấn:

```sql
-- Truy vấn minh họa trên bảng thứ hai; cần nạp dữ liệu trước.
SELECT order_day,
       count(*) AS orders_per_day,
       sum(amount_cents) AS amount_per_day
FROM orders_by_store_month_day
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

Lợi ích là ngày đã trở thành **cột clustering có thể nhóm theo tiền tố primary key**. Đổi lại, bảng denormalized phải được ghi/sửa/xóa nhất quán theo chính sách nghiệp vụ. Bài học ở đây không phải “cứ cần GROUP BY thì tạo bảng tùy tiện”, mà là **mô hình dữ liệu phải phản ánh câu hỏi cần trả lời**.

Nếu chỉ cần thống kê theo ngày cho dữ liệu nhỏ đã đọc vào Java, ứng dụng cũng có thể tổng hợp trên một partition đã bị giới hạn. Tuy nhiên phương án đó vẫn truyền/đọc nhiều dòng về client và phải tính giới hạn dung lượng, độ trễ cùng tính nhất quán khi có ghi đồng thời.

## 8. LIMIT, PER PARTITION LIMIT và paging có làm COUNT nhanh hơn?

### 8.1. LIMIT 1 không làm COUNT(*) chỉ xử lý một dòng

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

Trong Cassandra hiện đại, `COUNT(*)` không được biến thành phép đếm “tối đa một dòng” chỉ vì `LIMIT 1`. Aggregate trả về **một dòng kết quả**, và giới hạn output không giải quyết công việc **xử lý các dòng khớp để tính số 5**. Với dữ liệu lab, `order_count` vẫn là **5**.

Phân biệt với:

```sql
SELECT order_id, created_at
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

Truy vấn thứ hai không cần tính tổng hợp trên cả partition; nó chỉ yêu cầu tối đa **một dòng dữ liệu** theo clustering order. Đây là khác biệt rất lớn về mục đích và tiềm năng chi phí.

**Lưu ý phiên bản:** Một số tài liệu rất cũ của Cassandra 2.1 đã từng diễn giải `LIMIT` đối với `COUNT` theo cách khác. Kể từ dòng Cassandra 2.2 và các phiên bản hiện đại, không dùng mẹo `COUNT(*) ... LIMIT N` để kỳ vọng “đếm tối đa N dòng”. Nên kiểm tra behavior trên phiên bản cluster đang triển khai nếu ứng dụng có logic phụ thuộc chi tiết này.

### 8.2. PER PARTITION LIMIT cũng không thay bảng summary

`PER PARTITION LIMIT n` là cách hạn chế số **dòng kết quả từ mỗi partition** theo cú pháp CQL, thường hữu ích cho `SELECT` dữ liệu từng dòng. Khi kết hợp với aggregate hoặc `GROUP BY`, phải phân biệt **dòng nguồn được xử lý**, **nhóm được tạo** và **dòng kết quả**; không suy rằng cứ thêm `PER PARTITION LIMIT 1` sẽ tạo bộ đếm O(1) trên mỗi partition.

Nếu mục tiêu là **đếm toàn bộ đơn của mỗi tháng**, `PER PARTITION LIMIT 1` không phải cách dựng sẵn một tổng số cho từng tháng. Hãy thiết kế aggregate theo khóa, giới hạn phạm vi hoặc đọc bảng tổng hợp.

### 8.3. Page size chỉ điều tiết fetch, không thay phạm vi aggregate

Java driver có page size và paging state. Đây là hai khái niệm khác `LIMIT`:

| Cơ chế | Tác động chính | Có làm COUNT toàn bảng rẻ không? |
| --- | --- | --- |
| `WHERE` full partition key | Định vị partition cần đọc | **Có thể giảm phạm vi**, nhưng vẫn phải xét các dòng cần đếm. |
| Điều kiện clustering range | Giới hạn đoạn dòng trong partition | **Có thể giảm tập cần đếm.** |
| `LIMIT` | Giới hạn số dòng kết quả | **Không tự loại chi phí xử lý aggregate.** |
| `PER PARTITION LIMIT` | Giới hạn theo partition của result set | **Không phải index/bộ đếm.** |
| Driver page size | Điều tiết fetch qua các page | **Không làm toàn bộ phép đếm có phạm vi nhỏ đi.** |
| Driver paging state | Tiếp tục cùng một truy vấn | **Không tạo snapshot hay aggregate sẵn.** |

Nếu API cần phân trang danh sách đơn, có thể lấy `pageSize + 1` dòng hoặc sử dụng paging state để biết còn trang tiếp theo theo chính sách API; không nên chạy thêm `COUNT(*)` toàn bảng cho **mọi request chỉ để tạo nhãn tổng số trang**.

## 9. Chi phí đọc thực tế: từ partition đến SSTable

### 9.1. Một mô hình ước lượng dễ hiểu

Xem bảng các mức phạm vi sau:

| Mẫu truy vấn | Partition-key candidates | Dòng khớp trong lab | Nhận xét |
| --- | ---: | ---: | --- |
| Store A, `2026-11`, không có clustering range | 1 | 5 | Đếm một partition, không phải đọc toàn bảng. |
| Store A, `2026-11`, `created_at` trong `[09:00,10:00)` ngày 20 | 1 | 2 | Đếm một lát cắt nhỏ của partition. |
| Store A, `month_bucket IN ('2026-11','2026-12')` | 2 | 7 | Aggregate từ hai partition. |
| `SELECT COUNT(*) FROM orders_by_store_month` | Toàn bộ partition trong bảng | 8 | Quét rộng; chỉ phù hợp lab nhỏ. |

Các số trên đếm **dòng khớp và partition ứng viên của dữ liệu mẫu**, không nói chính xác hệ thống gửi bao nhiêu thông điệp mạng hay đọc bao nhiêu block trên đĩa.

Về mặt khái niệm:

```text
API / Java driver
       |
       v
Coordinator
       |
       +--> tìm partition bằng token của partition key
       |
       +--> liên hệ replica theo consistency / topology
                 |
                 +--> memtable và SSTable
                 +--> xử lý tombstone / TTL / reconciliation
                 +--> tập dòng còn hiệu lực khớp WHERE
                                   |
                                   v
                                COUNT / SUM / AVG ...
                                   |
                                   v
                              một/few result rows
```

**Đọc nhiều replica không nhân kết quả đếm theo replication factor.** Ba replica chứa cùng dữ liệu logic không có nghĩa `COUNT(*)` phải nhân ba số đơn. Replication và consistency ảnh hưởng cách thực thi và dữ liệu nhìn thấy, không đổi ý nghĩa đếm các dòng logic của bảng.

### 9.2. Những yếu tố làm truy vấn chậm dù kết quả ít

| Yếu tố | Ảnh hưởng có thể thấy |
| --- | --- |
| **Nhiều partition** | Fan-out và điều phối qua nhiều token/node; coordinator có thể chịu tải. |
| **Partition quá lớn** | Một `COUNT(*)` vẫn phải xét rất nhiều dòng bên trong partition. |
| **Tombstone, TTL** | Các phiên bản/xóa/hết hạn cần được xử lý để chỉ đếm dữ liệu hợp lệ. |
| **Nhiều SSTable và compaction chưa theo kịp** | Read amplification tăng; một hàng logic có thể cần hợp nhất thông tin từ nhiều nơi. |
| **Repair/replica chưa hội tụ** | Tăng chi phí reconciliation và ảnh hưởng dữ liệu quan sát ở các consistency level khác nhau. |
| **Consistency level cao hơn** | Có thể phải chờ nhiều replica; trade-off độ mới/khả dụng/độ trễ. |
| **Đọc đồng thời và retry** | Tăng áp lực coordinator/replica; retry vô hạn dễ tạo vòng khuếch đại tải. |

Một công thức **ước lượng định tính**, không phải cost model chính thức:

```text
Chi phí đọc COUNT
  ~ công việc tìm/đọc partition được chọn
  + công việc duyệt các dòng/cell cần kiểm tra
  + xử lý dữ liệu hết hạn, tombstone và hợp nhất
  + chi phí mạng, replica và điều phối

Số dòng output thường rất nhỏ (1 hoặc số nhóm).
```

### 9.3. Tracing và metrics cần quan sát gì?

Khi lab nhỏ, có thể bật tracing trong `cqlsh` để quan sát đường đi của một query:

```sql
TRACING ON;

SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

TRACING OFF;
```

Trong production, chỉ bật tracing một cách **chọn lọc** theo chính sách vận hành để tránh tạo thêm tải. Các tín hiệu nên theo dõi:

- Read latency p50/p95/p99 của query/endpoint, timeout và unavailable.
- Số partition đọc, kích thước và skew giữa partition.
- Tombstone warnings, các truy vấn đọc nhiều tombstone và read amplification.
- SSTable/memtable và hiệu quả compaction, thời gian repair, trạng thái replica.
- Coordinator load, concurrency, speculative execution, retry counts và mức consistency.

Không chỉ tối ưu `COUNT` bằng cách tăng timeout: kéo dài timeout có thể che triệu chứng trong khi cluster vẫn đọc quá rộng hoặc bị quá tải.

## 10. Java Driver: đọc aggregate đúng kiểu và giới hạn phạm vi

Ví dụ với **Apache Cassandra Java Driver 4.x** và Java 15+ (text blocks). Giả định ứng dụng đã có `CqlSession session` kết nối keyspace `cassandra_aggregate_lab`.

### 10.1. Đếm và tổng hợp trong một partition

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

UUID storeId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

PreparedStatement prepared = session.prepare("""
    SELECT count(*) AS order_count,
           count(amount_cents) AS priced_count,
           sum(amount_cents) AS total_cents
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
    """);

BoundStatement statement = prepared.bind(storeId, "2026-11");
Row row = session.execute(statement).one();
if (row != null) {
    long totalOrders = row.getLong("order_count");
    long pricedOrders = row.getLong("priced_count");
    long totalCents = row.getLong("total_cents");
    System.out.printf("%d orders, %d priced, %d cents%n",
        totalOrders, pricedOrders, totalCents);
}
```

Với dữ liệu mẫu, in `5 orders, 4 priced, 75000 cents`. CQL `COUNT` trả kiểu số thích hợp cho bộ đếm (thường `bigint`); `SUM(amount_cents)` trên đầu vào `bigint` có thể đọc bằng `getLong` theo chữ ký hàm hiện tại. Nếu bạn thay `CAST` hay kiểu cột, phải cập nhật getter Java tương ứng.

**Quan trọng:** `setPageSize(...)` trên statement aggregate không khiến Cassandra chỉ đếm một trang của partition. Page size phục vụ việc truyền kết quả, không phải cách biến việc đếm một tập lớn thành phép đọc metadata.

### 10.2. Bind khoảng thời gian để chỉ đếm dữ liệu cần thiết

```java
import java.time.Instant;

PreparedStatement byWindow = session.prepare("""
    SELECT count(*) AS matching_orders
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
      AND created_at >= ?
      AND created_at < ?
    """);

BoundStatement window = byWindow.bind(
    storeId,
    "2026-11",
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T10:00:00Z")
);

Row one = session.execute(window).one();
long matchingOrders = one == null
    ? 0L
    : one.getLong("matching_orders");
System.out.println(matchingOrders); // 2 trong dữ liệu mẫu
```

Trong một API thực tế, đầu vào `store_id` phải đến từ người dùng đã được xác thực/ủy quyền, không chỉ từ tham số URL do client tự chọn. `month_bucket` cần được kiểm tra theo quy ước nghiệp vụ; không cho phép client tự tạo danh sách hàng nghìn tháng và quét vô hạn.

### 10.3. Thời gian, consistency và lỗi

- **Timeout / unavailable:** đánh giá phạm vi đọc, số partition, consistency, trạng thái replica và tài nguyên; điều chỉnh retry dựa trên tính idempotent và tải, không retry vô hạn.
- **InvalidQuery:** thường do điều kiện khóa hoặc phép lọc/sắp xếp không được hỗ trợ; không sửa bằng cách tăng timeout.
- **Sai khác số liệu giữa hai lần đọc:** có thể do ghi/xóa/TTL giữa các request hoặc replica chưa hội tụ. Cần xác định yêu cầu độ mới trước khi chọn `LOCAL_ONE`, `LOCAL_QUORUM` hoặc lựa chọn khác.
- **Khả năng quá tải:** giới hạn concurrency, áp request timeout hợp lý và theo dõi p95/p99. Nếu dashboard hỏi cùng một số đếm liên tục, cân nhắc bảng tổng hợp hoặc cache có TTL phù hợp.

## 11. Khi nào không nên COUNT trực tiếp?

### 11.1. So sánh các chiến lược

| Nhu cầu | Cách làm phù hợp | Đánh đổi |
| --- | --- | --- |
| Đếm vài trăm dòng trong một partition đã biết, ít request | `COUNT(*)` trực tiếp với full partition key | Đơn giản; chi phí tăng theo dữ liệu cần xử lý. |
| Đếm trong một cửa sổ clustering ngắn | `COUNT(*)` với hai cận thời gian | Giới hạn được phạm vi, nhưng vẫn đọc các dòng trong khoảng. |
| Dashboard cần số đơn toàn hệ thống mỗi giây | Summary table / stream aggregator | Đọc rẻ; phải duy trì số liệu và xử lý replay/sửa/xóa. |
| Báo cáo dài trên rất nhiều partition | Batch analytics/ETL/warehouse | Hợp cho tổng hợp lớn; có độ trễ cập nhật và chi phí pipeline. |
| Đếm sự kiện tăng/giảm đơn giản | Counter column nếu semantics phù hợp | Cần đặc biệt xử lý retry, idempotency, sai lệch và đối soát. |
| Kiểm tra có đơn theo full primary key | Point lookup một cột khóa | Trả thông tin tồn tại thay vì aggregate không cần thiết. |

### 11.2. Bảng summary đọc nhanh hơn COUNT lịch sử

Nếu sản phẩm thường xuyên cần số đơn và tổng tiền theo **cửa hàng/tháng**, có thể thiết kế bảng tóm tắt:

```sql
CREATE TABLE IF NOT EXISTS monthly_order_summary (
    store_id uuid,
    month_bucket text,
    order_count bigint,
    priced_count bigint,
    total_cents varint,
    updated_at timestamp,
    PRIMARY KEY (store_id, month_bucket)
);
```

Khi pipeline đã duy trì đúng các giá trị, đọc số liệu là một point lookup:

```sql
SELECT order_count, priced_count, total_cents, updated_at
FROM monthly_order_summary
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Lệnh `CREATE TABLE` chỉ định nghĩa schema; nó **không tự nạp hay tự cập nhật summary** từ bảng đơn hàng. Ứng dụng cần cơ chế cập nhật theo sự kiện như tạo đơn, hủy đơn, hoàn tiền, xóa và backfill. `total_cents` có thể phải xử lý các thay đổi giá trị, không chỉ cộng vô điều kiện mỗi lần ghi.

Một hướng thiết kế đáng cân nhắc:

```text
Order event (có event_id duy nhất)
    |
    v
Pipeline xác thực + loại sự kiện trùng (idempotent)
    |
    +--> ghi orders_by_store_month
    |
    +--> cập nhật monthly_order_summary
                |
                v
       API đọc 1 dòng summary

Định kỳ đối soát summary với dữ liệu nguồn theo bucket.
```

Việc ghi giữa nhiều partition/bảng không mặc nhiên mang tính giao dịch như một SQL transaction xuyên bảng. Cần xác định cách xử lý khi pipeline ghi một nơi thành công, nơi khác thất bại; dùng idempotency key, retry có kiểm soát và đối soát.

### 11.3. Cẩn thận với counter columns

Cassandra có kiểu `counter`, phù hợp một số phép tăng/giảm. Tuy nhiên:

- Không dùng `counter` như một kết quả `COUNT(*)` tự động của bảng khác; application phải thực hiện cập nhật.
- Việc tăng counter **không phải thao tác idempotent đơn giản**: nếu một request được thực thi rồi retry, có nguy cơ cộng hai lần nếu không quản lý logic ứng dụng.
- Counter table có các giới hạn schema/ghi khác regular table; không trộn các cột thường tùy ý trong cùng cách sử dụng counter.
- Với sự kiện có thể đổi trạng thái, bị hủy hoặc được nhập lại, cần thiết kế bù trừ và đối soát, không chỉ tăng mỗi khi thấy event.

Vì thế, chọn **counter** chỉ khi mô hình sự kiện và yêu cầu chính xác phù hợp; nếu không, summary table được cập nhật từ luồng sự kiện idempotent hoặc hệ thống analytics có thể dễ vận hành hơn.

## 12. Những lỗi thường gặp

| Nhận định / câu truy vấn | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `SELECT COUNT(*) FROM orders_by_store_month` cho 1 số nên rẻ | Có thể quét toàn bộ bảng/cluster. | Luôn xét `WHERE`, thiết kế bucket hoặc summary. |
| `COUNT(1)` đọc metadata nhanh hơn `COUNT(*)` | Hai cách cùng đếm dòng khớp. | Chọn dạng rõ ràng, không coi `COUNT(1)` là tối ưu đặc biệt. |
| `COUNT(amount_cents) = COUNT(*)` trong mọi trường hợp | Cột có thể thiếu/null hoặc hết TTL. | Phân biệt số dòng và số giá trị non-null. |
| `COUNT(status)` là số trạng thái khác nhau | Nó đếm các **giá trị status non-null**, không đếm distinct. | Thiết kế đường nhóm/summary nếu cần theo trạng thái. |
| `COUNT(*) ... LIMIT 1` chỉ xử lý một raw row | `LIMIT` giới hạn output aggregate chứ không tạo bộ đếm O(1). | Đặt giới hạn trong `WHERE` hoặc dùng summary. |
| `WHERE status = 'PAID'` sẽ được `COUNT` tối ưu tự động | `status` là regular column chưa có index trong schema lab. | Thay mô hình bảng, chỉ mục phù hợp hoặc aggregation pipeline. |
| `SUM` luôn giữ nguyên độ chính xác với `bigint` | Có thể tràn miền giá trị; `AVG` có thể làm tròn/cắt phần thập phân. | `CAST` đầu vào và kiểm tra kiểu dữ liệu. |
| `MIN(amount)` kèm `order_id` trả ID đơn nhỏ nhất | Cột không aggregate có thể lấy từ dòng đầu, không phải dòng min. | Tách yêu cầu “min value” và “dòng có min value”. |
| `GROUP BY` tự do theo mọi cột như SQL | CQL đặt ràng buộc theo primary key. | Tạo bảng theo truy vấn/tổng hợp ngoài. |
| Driver page size 50 làm `COUNT` chỉ xem 50 đơn | Page size chỉ liên quan fetch kết quả. | Giới hạn phạm vi bằng khóa, không thay aggregate bằng paging. |
| Có `RF=3` thì `COUNT` phải nhân ba | Replica cùng lưu các bản sao của dòng logic. | Không nhân theo RF; chọn consistency đúng nghiệp vụ. |
| `COUNT` trả về “số thật tuyệt đối tại mọi thời điểm” | Ghi đồng thời, TTL và replica chưa hội tụ có thể làm số đếm thay đổi. | Quy định thời điểm/độ mới, đối soát và consistency phù hợp. |

## 13. Bài tập có đáp án

### Bài 1. Đếm đơn có tiền và chưa có tiền

**Đề:** Tại partition cửa hàng A/tháng `2026-11`, có bao nhiêu dòng tất cả, bao nhiêu dòng có `amount_cents`, và chênh lệch bao nhiêu?

**Đáp án CQL:**

```sql
SELECT count(*) AS total_orders,
       count(amount_cents) AS priced_orders
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Kết quả `5` và `4`; chênh lệch **1** dòng chưa có `amount_cents`.

### Bài 2. Tổng tiền trong một ngày

**Đề:** Chỉ tính tổng `amount_cents` của ngày 20/11, cửa hàng A, nhưng không đọc ngày 21.

**Đáp án:**

```sql
SELECT count(*) AS orders_on_day,
       sum(amount_cents) AS total_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-20 00:00:00+0000'
  AND created_at <  '2026-11-21 00:00:00+0000';
```

Kết quả: **3 đơn**, **55.000 cents**. Đây là khoảng timestamp UTC, không phải mặc định ngày địa phương của người mua.

### Bài 3. Vì sao COUNT(*) toàn bảng có thể timeout?

**Đề:** Một bảng có 200 triệu đơn trên nhiều node. Dashboard chạy `SELECT COUNT(*) FROM orders_by_store_month;` sau mỗi lần tải trang, dù kết quả chỉ là một số. Nêu ít nhất ba nguyên nhân rủi ro.

**Đáp án gợi ý:** Không có partition key trong `WHERE` nên phải xét dữ liệu trải rộng nhiều partition/token; cần xử lý những dòng còn sống sau TTL/tombstone và có thể hợp nhất nhiều SSTable; công việc nhiều replica/coordinator cộng với tải đồng thời làm tăng độ trễ hoặc timeout. Giải pháp có thể là summary/counter/pipeline tùy semantics và cơ chế đối soát, không phải chỉ tăng timeout.

### Bài 4. LIMIT 1 có thay phép đếm không?

```sql
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 1;
```

**Đáp án:** Trên Cassandra hiện đại, `order_count` vẫn là **5**. `LIMIT 1` không có nghĩa chỉ xử lý một dòng để tính aggregate. Nếu cần xem **một đơn**, dùng `SELECT order_id ... LIMIT 1` thay vì đếm.

### Bài 5. Phân biệt kết quả số và ý nghĩa nghiệp vụ

**Đề:** Tại cửa hàng A/tháng 11, `SUM(amount_cents)` bằng `75.000`. Có thể gọi ngay đây là “doanh thu đã thanh toán” không?

**Đáp án:** **Không.** Tập dòng có cả trạng thái `CREATED` và `CANCELLED`; `SUM(amount_cents)` không lọc theo trạng thái. Cần quy tắc nghiệp vụ rõ và schema/query/summary thể hiện đúng những trạng thái cần tính.

### Bài 6. AVG và giá trị thiếu

**Đề:** Trong tháng 11 cửa hàng A, có năm đơn nhưng chỉ bốn giá trị tiền. Trung bình `amount_cents` của các dòng có tiền là bao nhiêu?

**Đáp án:** `(10000+15000+30000+20000)/4 = 18750` cents. Câu CQL:

```sql
SELECT avg(CAST(amount_cents AS decimal)) AS avg_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Không dùng năm làm mẫu số khi định nghĩa thống kê là trung bình của **giá trị non-null**.

## 14. Checklist trước khi đưa COUNT vào hệ thống

1. **Bài toán:** Cần đếm dòng tồn tại, cột non-null, theo trạng thái, theo ngày hay một KPI nghiệp vụ có quy tắc riêng?
2. **Phạm vi:** Truy vấn có đầy đủ partition key không? Có clustering range để thu hẹp không? Nếu `IN`, có bao nhiêu partition ứng viên?
3. **Kích thước:** Mỗi partition chứa bao nhiêu dòng và tombstone? Chi phí đếm có chấp nhận được ở p95/p99 và số request đồng thời không?
4. **Cú pháp:** `COUNT(*)` hay `COUNT(column)`, `SUM`/`AVG` trên kiểu gì? Có cần `CAST` tránh cắt số/tràn số không? `GROUP BY` có tương thích primary key không?
5. **Giới hạn:** Đã hiểu rằng `LIMIT` và driver paging không tự làm aggregate nhẹ chưa?
6. **Phân tán:** Replication, consistency, compaction/repair và retry có ảnh hưởng thế nào tới độ trễ và tính mới của giá trị trả về?
7. **Thiết kế lại:** Nếu dashboard gọi liên tục hoặc cần số liệu trên toàn cluster, có summary/pipeline/counter và cơ chế idempotency, đối soát, backfill phù hợp chưa?
8. **Java:** Đã bind đúng kiểu, dùng getter tương thích kiểu aggregate, đặt timeout/concurrency hợp lý và không dựa vào quét toàn bảng trong đường request nóng chưa?

**Điểm cốt lõi:** `COUNT(*)` trong Cassandra **không phải phép lấy sẵn tổng số dòng từ metadata**. Nó tổng hợp trên những dòng phải được đọc và đánh giá theo `WHERE`, trạng thái dữ liệu và consistency. Hãy dùng **partition key và clustering range** để giảm chi phí khi có thể; với thống kê lớn và thường xuyên, ưu tiên thiết kế **summary/query model** đáp ứng đúng yêu cầu sản phẩm.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — Functions: COUNT, MIN, MAX, SUM, AVG](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html)
- [Apache Cassandra Documentation — CQL Data Manipulation: WHERE, GROUP BY, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY và CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
