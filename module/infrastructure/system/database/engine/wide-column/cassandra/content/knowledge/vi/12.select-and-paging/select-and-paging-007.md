# DISTINCT, GROUP BY và các ràng buộc CQL cần kiểm tra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `SELECT DISTINCT` với `GROUP BY` trong Apache Cassandra và giải thích vì sao chúng không hoạt động như các phép nhóm/sắp xếp tùy ý của SQL quan hệ.
2. Viết `DISTINCT` hợp lệ cho **partition key** và **static columns**, đồng thời nhận diện truy vấn `DISTINCT` trên clustering column hoặc cột thường không hợp lệ.
3. Dùng `GROUP BY` theo **tiền tố primary key**, kết hợp `COUNT(*)`, `SUM`, `MIN`, `MAX` hoặc `AVG` khi phạm vi truy vấn được giới hạn.
4. Phân biệt giá trị tổng hợp với một cột không thuộc nhóm nhưng vẫn được chọn; tránh diễn giải cột đại diện như một đặc tính của cả nhóm.
5. Kiểm tra các ràng buộc của CQL về `WHERE`, `ORDER BY`, `LIMIT`, `HAVING` và số partition bị đọc trước khi đưa thống kê vào API.
6. Lựa chọn khi nào cần bảng tổng hợp duy trì trước thay cho truy vấn phân tích trực tiếp trên dữ liệu giao dịch trong cluster phân tán.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Apache Cassandra là cơ sở dữ liệu wide-column phân tán, nên cách **phân vùng dữ liệu**, **thứ tự clustering**, **replication**, **consistency** và thiết kế bảng theo truy vấn ảnh hưởng trực tiếp đến độ đúng và chi phí của phép nhóm. Ví dụ CQL và Java dưới đây hướng tới cả mục đích học cú pháp lẫn nhận diện truy vấn nào thực sự phù hợp cho ứng dụng.

## 1. DISTINCT và GROUP BY trả lời hai câu hỏi khác nhau

Trong bảng Cassandra có khóa chính:

```sql
PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
```

hãy phân biệt:

- **`DISTINCT`:** “Những **partition** nào xuất hiện?” Cassandra giới hạn danh sách selector của `DISTINCT` vào các cột thuộc partition key và static columns; nó không phải công cụ loại trùng trên một cột bất kỳ.
- **`GROUP BY`:** “Với các dòng đã chọn, có bao nhiêu dòng hoặc tổng số tiền của **mỗi nhóm theo tiền tố primary key**?” CQL chỉ hỗ trợ những hình dạng nhóm tương thích với khóa, thay vì tùy ý theo bất kỳ biểu thức/cột nào.
- **Aggregate không có `GROUP BY`:** “Trong tập dòng khớp truy vấn, tổng là bao nhiêu?” Chẳng hạn `COUNT(*)` của **một partition đã biết**.

| Truy vấn mong muốn | Công cụ CQL phù hợp | Ràng buộc chính |
| --- | --- | --- |
| Liệt kê các tháng có partition của một cửa hàng | `SELECT DISTINCT store_id, month_bucket` | Chọn partition key; phạm vi đọc vẫn phụ thuộc `WHERE`. |
| Đếm đơn trong một tháng | `COUNT(*)` | Cần đọc những dòng thuộc tập cần đếm. |
| Đếm đơn theo từng ngày trong một tháng | `GROUP BY` trên tiền tố khóa gồm `order_day` | Clustering key phải phù hợp thứ tự của primary key. |
| Liệt kê các trạng thái `PAID`/`CREATED` duy nhất | Không dùng trực tiếp `DISTINCT status` trên bảng ví dụ | `status` là regular column; cân nhắc bảng đọc/tổng hợp khác. |
| Thống kê tổng tiền theo trạng thái của toàn hệ thống | Không có `GROUP BY status` tùy ý trên bảng ví dụ | Cần luồng tổng hợp hoặc bảng theo mẫu truy vấn. |

Điểm khác SQL quan hệ: dù về mặt toán học các câu hỏi đều liên quan tới “loại trùng” và “gom nhóm”, **CQL không cung cấp cơ chế sort/hash aggregate tùy ý cho mọi cột dữ liệu** trên toàn cluster.

## 2. Lab CQL: bảng có composite partition key và static column

Giả sử một ứng dụng thương mại điện tử cần truy vấn các đơn của **một cửa hàng trong một tháng**. Trong mỗi partition tháng, ngày đặt đơn là clustering column đầu; `order_id` phân biệt các đơn cùng ngày.

### 2.1. Tạo keyspace và bảng

```sql
-- RF=1 và SimpleStrategy chỉ dành cho môi trường lab một node.
CREATE KEYSPACE IF NOT EXISTS cql_group_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cql_group_lab;

CREATE TABLE IF NOT EXISTS orders_by_store_month (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_id uuid,
    store_name text static,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day ASC, order_id ASC);
```

Các cột có ý nghĩa:

| Cột | Vai trò | Lưu ý |
| --- | --- | --- |
| `store_id`, `month_bucket` | **Composite partition key** | Hash toàn bộ cặp để chọn partition và replica. |
| `order_day`, `order_id` | **Clustering columns** | Định danh và sắp thứ tự dòng trong mỗi partition. |
| `store_name` | **Static column** | Giá trị ở cấp partition, được chia sẻ bởi các dòng của partition đó. |
| `status`, `amount_cents` | **Regular columns** | Thuộc từng dòng, không thể `DISTINCT`/`GROUP BY` tự do theo các cột này. |

`store_name` là static column, không có nghĩa là tên cửa hàng đồng bộ tự động giữa mọi partition tháng. Khi cửa hàng đổi tên, những partition lưu static value có thể cần được cập nhật theo yêu cầu sản phẩm. Tác vụ thống kê phải cân nhắc tính nhất quán và việc ghi nhiều bảng/partition.

### 2.2. Nạp dữ liệu cố định

```sql
-- Cửa hàng A, tháng 11: ba đơn ngày 20.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000001, 'PAID', 10000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000002, 'PAID', 15000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000003, 'CREATED', 30000
);

-- Cửa hàng A, tháng 11: hai đơn ngày 21.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21',
    00000000-0000-4000-8000-000000000004, 'PAID', 20000
);

INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21',
    00000000-0000-4000-8000-000000000005, 'SHIPPED', 40000
);

-- Cửa hàng A, tháng 12: một đơn ngày 01.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12', '2026-12-01',
    00000000-0000-4000-8000-000000000006, 'PAID', 60000
);

-- Cửa hàng B, tháng 11: một đơn ngày 20.
INSERT INTO orders_by_store_month
    (store_id, month_bucket, order_day, order_id, status, amount_cents)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11', '2026-11-20',
    00000000-0000-4000-8000-000000000007, 'CREATED', 80000
);

-- Cập nhật static column ở đúng cấp partition; không cần clustering key.
UPDATE orders_by_store_month SET store_name = 'Cua hang A'
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

UPDATE orders_by_store_month SET store_name = 'Cua hang A'
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-12';

UPDATE orders_by_store_month SET store_name = 'Cua hang B'
WHERE store_id = 22222222-2222-4222-8222-222222222222
  AND month_bucket = '2026-11';
```

Dữ liệu mẫu có **ba partition có dữ liệu**, tổng cộng **bảy dòng**:

| Partition key | Clustering groups theo ngày | Dòng | Tổng `amount_cents` |
| --- | --- | ---: | ---: |
| (A, `2026-11`) | 20/11: 3, 21/11: 2 | 5 | 115.000 |
| (A, `2026-12`) | 01/12: 1 | 1 | 60.000 |
| (B, `2026-11`) | 20/11: 1 | 1 | 80.000 |

Với các khóa cố định trong ví dụ, chạy lại `INSERT` là **upsert** trên cùng primary key, không thêm một dòng trùng khóa. Nếu bảng có dữ liệu trước đó ngoài các dòng mẫu, các con số trên không còn là dự báo duy nhất.

## 3. DISTINCT: chỉ chọn cột phù hợp ở cấp partition

### 3.1. Liệt kê các partition tháng đã biết của cửa hàng A

```sql
SELECT DISTINCT store_id, month_bucket
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

Với dữ liệu mẫu, kết quả là **hai dòng**:

| `store_id` | `month_bucket` |
| --- | --- |
| A | `2026-11` |
| A | `2026-12` |

Mỗi dòng thể hiện một **partition key đầy đủ**, không phải một đơn hàng. Partition A/11 có năm đơn nhưng chỉ đóng góp **một dòng `DISTINCT`**.

Đừng diễn giải truy vấn này là “lấy hai tháng gần nhất” nếu chưa có cơ chế truy cập tháng và giới hạn thứ tự rõ ràng. `IN` chỉ nêu hai tháng đã biết; `DISTINCT` không tự sắp các partition theo thời gian.

### 3.2. Chọn static column cùng partition key

```sql
SELECT DISTINCT store_id, month_bucket, store_name
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

`store_name` là static column, nên có thể nằm trong danh sách selector của `DISTINCT`. Kết quả vẫn là **hai dòng theo hai partition**, mỗi dòng mang tên cửa hàng ở cấp partition.

Nếu không có static value cho partition, giá trị có thể là `null`. `DISTINCT` không tự đồng bộ static value giữa nhiều partition của cùng cửa hàng.

### 3.3. DISTINCT không dùng tùy ý trên clustering/regular column

Các truy vấn sau **không hợp lệ** theo ràng buộc của `DISTINCT` đối với bảng lab:

```sql
-- Sai: status là regular column.
SELECT DISTINCT status
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Sai: order_day là clustering column, không phải partition key.
SELECT DISTINCT order_day
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Sai: trộn DISTINCT hợp lệ với regular column.
SELECT DISTINCT store_id, month_bucket, status
FROM orders_by_store_month;
```

Muốn biết tập các ngày có đơn, có thể dùng `GROUP BY` theo clustering key như ví dụ tiếp theo **trên một partition đã biết**. Muốn biết các trạng thái `PAID`/`CREATED`/`SHIPPED` trên nhiều đơn, phải chọn một cách lưu/đọc phù hợp; không giả định Cassandra cung cấp `SELECT DISTINCT status` như một SQL analytics engine.

### 3.4. DISTINCT không biến truy vấn toàn bảng thành truy vấn rẻ

```sql
-- Dùng để quan sát trong lab nhỏ; tránh dùng tùy tiện trên production lớn.
SELECT DISTINCT store_id, month_bucket
FROM orders_by_store_month;
```

Truy vấn trên có thể phải duyệt **nhiều partition trên nhiều node**. Dù số dòng đầu ra nhỏ hơn số đơn hàng, hệ thống vẫn cần đọc đủ thông tin để xác định những partition xuất hiện. Thêm `LIMIT 10` chỉ giới hạn đầu ra; nó không cung cấp một partition key để định tuyến truy vấn tới một phạm vi nhỏ đã biết.

Trong hệ thống thực, nếu API thường xuyên cần danh sách tháng đã có dữ liệu cho mỗi cửa hàng, hãy cân nhắc một bảng riêng ghi nhận những tháng có đơn, hoặc truy vấn những bucket tháng đã biết trong một phạm vi được kiểm soát.

## 4. GROUP BY: gom nhóm theo tiền tố primary key

### 4.1. Quy tắc nền tảng

Trong bảng:

```sql
PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
```

thứ tự khóa là:

```text
store_id, month_bucket   |   order_day   |   order_id
<-- partition key ---->  |  clustering  | clustering

prefix an toàn để GROUP BY:
  (store_id, month_bucket)
  (store_id, month_bucket, order_day)
  (store_id, month_bucket, order_day, order_id)
```

CQL `GROUP BY` thông thường chỉ nhóm theo **các cột thuộc primary key và theo thứ tự của khóa**, có xét các cột đã bị cố định bằng trong `WHERE`. Khi cần GROUP BY trên tập nhiều partition, nên thể hiện **đầy đủ partition key** trong khóa nhóm, và giới hạn số partition bằng `WHERE`. Một số phiên bản Cassandra còn hỗ trợ những biểu thức chuyên biệt như hàm `floor()` để gom theo bucket thời gian trên clustering column phù hợp; điều đó không có nghĩa `GROUP BY` được tùy ý áp dụng cho mọi biểu thức hay regular column.

Khác với SQL quan hệ, `GROUP BY status` không trở nên hợp lệ chỉ vì `status` nằm trong `SELECT` hay có ít giá trị khác nhau.

### 4.2. Đếm đơn theo ngày trong một partition tháng

```sql
SELECT store_id,
       month_bucket,
       order_day,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

**Kết quả tính từ dữ liệu mẫu:**

| `month_bucket` | `order_day` | `order_count` | `gross_cents` |
| --- | --- | ---: | ---: |
| `2026-11` | 2026-11-20 | 3 | 55.000 |
| `2026-11` | 2026-11-21 | 2 | 60.000 |

Các giá trị của `store_id` và `month_bucket` không đổi trong truy vấn này vì `WHERE` đã xác định một partition. Cassandra có thể duyệt các dòng theo clustering order đã định nghĩa, và nhóm theo tiền tố khóa `(store_id, month_bucket, order_day)`.

Giải thích tổng:

```text
2026-11-20:
  count = 3
  sum   = 10000 + 15000 + 30000 = 55000

2026-11-21:
  count = 2
  sum   = 20000 + 40000 = 60000

Toàn partition tháng 11:
  count = 5
  sum   = 115000
```

Đây là kiểu `GROUP BY` phù hợp vì điều kiện `WHERE` đã định vị partition và khóa nhóm chỉ dựa trên **tiền tố của clustering key**.

### 4.3. GROUP BY theo partition key khi đọc nhiều tháng

```sql
SELECT store_id,
       month_bucket,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12')
GROUP BY store_id, month_bucket;
```

Với dữ liệu mẫu, có hai nhóm:

| Partition/group | `order_count` | `gross_cents` |
| --- | ---: | ---: |
| (A, `2026-11`) | 5 | 115.000 |
| (A, `2026-12`) | 1 | 60.000 |

Như vậy, `GROUP BY store_id, month_bucket` có thể tạo **một kết quả tổng hợp cho mỗi partition**. Cách viết này khác `SELECT DISTINCT store_id, month_bucket` ở chỗ `GROUP BY` còn thực hiện công việc **đọc các dòng và tính aggregate**.

`IN` trên thành phần cuối của composite partition key tạo **hai khóa partition ứng viên**. Nếu danh sách có 100 tháng/bucket, chi phí đọc nhiều partition cần được đánh giá riêng; `GROUP BY` không biến các partition ấy thành một vùng liên tục trên token ring.

### 4.4. Tổng hợp một partition mà không cần GROUP BY

Nếu câu hỏi chỉ là “tháng 11 của cửa hàng A có bao nhiêu đơn, tổng bao nhiêu tiền?”, có thể viết ngắn:

```sql
SELECT count(*) AS order_count,
       sum(amount_cents) AS gross_cents,
       min(amount_cents) AS min_cents,
       max(amount_cents) AS max_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Với dữ liệu mẫu: `order_count = 5`, `gross_cents = 115000`, `min_cents = 10000`, `max_cents = 40000`. Vì đây là **một tập dòng đã được xác định bằng partition key**, không cần `GROUP BY` để chia thành nhiều nhóm.

Không nên sử dụng `COUNT(*)` toàn bảng thường xuyên cho màn hình dashboard và giả định việc trả về một ô có nghĩa truy vấn rẻ. Cassandra vẫn cần xử lý những dòng/partition thuộc tập đang đếm.

## 5. Các ràng buộc GROUP BY thường khiến truy vấn bị từ chối

### 5.1. Không GROUP BY regular column tùy ý

```sql
-- Sai: status không thuộc primary key.
SELECT status, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY status;
```

Trong mô hình dữ liệu hiện tại, đơn của trạng thái `PAID` không nằm cạnh nhau theo `status`. Nếu cần số đơn theo trạng thái ở quy mô lớn và độ trễ thấp, cân nhắc **bảng tổng hợp theo (store, month, status)** hoặc cách ghi/chuyển đổi dữ liệu phục vụ truy vấn đó.

### 5.2. Không nhảy qua clustering column đứng trước

```sql
-- Sai: bỏ qua order_day rồi GROUP BY order_id.
SELECT order_id, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_id;
```

`order_id` đứng sau `order_day` trong clustering key. Các nhóm dựa trên `order_id` nhưng bỏ qua `order_day` không theo **tiền tố primary key**. Cũng không thể đặt cột nhóm tùy ý đảo thứ tự khóa để ép Cassandra chạy như một SQL engine.

### 5.3. Không dùng HAVING như SQL quan hệ

```sql
-- Sai: CQL không hỗ trợ HAVING trong SELECT như SQL quan hệ.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
HAVING count(*) > 2;
```

Trong trường hợp tập nhóm **nhỏ và được giới hạn**, ứng dụng có thể nhận các nhóm hợp lệ rồi lọc `order_count > 2` sau khi đọc kết quả. Nếu đây là điều kiện nóng trên hàng triệu nhóm hoặc cần phân trang chính xác theo aggregate, hãy **tổ chức và duy trì dữ liệu tổng hợp** ở tầng ghi/luồng dữ liệu.

### 5.4. Không ORDER BY tùy ý theo giá trị tổng hợp

```sql
-- Sai: ORDER BY không sắp theo alias của aggregate.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
ORDER BY order_count DESC;
```

`ORDER BY` của Cassandra dựa trên **clustering columns** và chiều sắp được schema hỗ trợ, không phải sort theo `count(*)` trên tập nhóm tính tạm. Nếu API cần “10 ngày có nhiều đơn nhất”, phải suy nghĩ tới bảng top-N/summary hoặc lấy một tập nhóm có giới hạn để ứng dụng sắp xếp.

## 6. Cột ngoài nhóm trong SELECT: giá trị đại diện dễ gây hiểu nhầm

CQL cho phép một số truy vấn aggregate chọn thêm cột không có trong khóa nhóm. Giá trị cột không thuộc nhóm có thể được lấy từ **dòng đầu tiên của nhóm** theo cách duyệt kết quả; nó **không** đại diện cho tất cả dòng.

```sql
-- Chú ý: status không phải khóa nhóm.
SELECT order_day,
       status,
       count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

Điều nguy hiểm là người đọc có thể tưởng câu trên “đếm đơn theo ngày và trạng thái”. Thực tế, `GROUP BY` chỉ gom theo `store_id`, `month_bucket`, `order_day`. Trên ngày 20, các dòng mang `PAID`, `PAID`, `CREATED`: một giá trị `status` đơn lẻ bên cạnh `order_count = 3` không có nghĩa là **cả ba** đơn đều ở trạng thái đó.

Do đó:

- Chỉ hiển thị **cột thuộc khóa nhóm** và các **aggregate** khi thiết kế response thống kê.
- Nếu cần thống kê theo `status`, phải có dữ liệu được tổ chức theo trạng thái hoặc một pipeline tổng hợp rõ ràng.
- Tránh sử dụng `SELECT *` cùng aggregate rồi suy nghĩa kinh doanh từ những cột thường được trả ra.

Ngay cả khi một ví dụ có vẻ trả đúng giá trị mong đợi do dữ liệu nhỏ hoặc clustering order hiện tại, cách suy luận đó không biến cột đại diện thành **thuộc tính của cả nhóm**.

## 7. Hàm aggregate và ý nghĩa khi gặp dữ liệu thiếu

Những hàm thường gặp gồm:

| Hàm | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `count(*)` | Đếm các dòng khớp | Có thể phải duyệt nhiều dòng; không là bộ đếm sẵn cho mọi truy vấn. |
| `count(amount_cents)` | Đếm các giá trị không null ở cột | Khác `count(*)` khi một số dòng thiếu cột. |
| `sum(amount_cents)` | Tổng các giá trị số | Cần xem kiểu kết quả và nguy cơ tràn số. |
| `avg(amount_cents)` | Trung bình của các giá trị số | Cân nhắc kiểu và độ chính xác với dữ liệu tiền. |
| `min(amount_cents)`, `max(amount_cents)` | Giá trị nhỏ nhất/lớn nhất | Không có nghĩa lấy nguyên dòng gắn với min/max. |

Ví dụ muốn lấy giá trị trung bình dưới dạng có kiểm soát:

```sql
SELECT count(*) AS order_count,
       sum(amount_cents) AS total_cents,
       avg(CAST(amount_cents AS decimal)) AS avg_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Với năm giá trị `10000, 15000, 30000, 20000, 40000`, trung bình là `23000` cents. Việc chuyển sang `decimal` trước khi lấy trung bình làm rõ kiểu kết quả mong muốn. Với tiền tệ, lưu số tiền ở đơn vị nhỏ nhất và dùng kiểu có độ chính xác phù hợp trong ứng dụng.

**Lưu ý:** Kiểu trả về của hàm phụ thuộc chữ ký hàm CQL và phiên bản Cassandra. Không suy ra rằng mọi hàm aggregate có thể áp dụng cho mọi kiểu dữ liệu, hoặc mọi phép tính thập phân sẽ giữ nguyên độ chính xác nếu đầu vào đã bị chia nguyên trước đó.

### Dữ liệu thiếu, TTL và xóa

Nếu một dòng không có `amount_cents`, `count(*)` vẫn xét dòng tồn tại, còn `count(amount_cents)` không đếm giá trị null/không tồn tại. Nếu một cell hết TTL hoặc bị xóa, dữ liệu đang thấy tại thời điểm đọc có thể thay đổi khi replica hội tụ.

Trong Cassandra phân tán, mức đọc nhất quán (ví dụ `LOCAL_ONE` và `LOCAL_QUORUM` trong cấu hình replication phù hợp) ảnh hưởng **replica nào phải trả lời**. Nó không biến `COUNT(*)` thành một số liệu giao dịch toàn cluster có snapshot nhất quán qua nhiều truy vấn khác nhau.

## 8. Ràng buộc về WHERE, LIMIT và phạm vi dữ liệu phải đọc

### 8.1. Khóa phân vùng quyết định mức độ fan-out

Hai truy vấn có thể tạo cùng số dòng tổng hợp nhưng có phạm vi đọc khác nhau:

```sql
-- Phạm vi gọn: một partition cụ thể.
SELECT count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';

-- Phạm vi rộng: không cung cấp partition key.
SELECT store_id, month_bucket, count(*) AS order_count
FROM orders_by_store_month
GROUP BY store_id, month_bucket;
```

Câu thứ hai chỉ minh họa về **phạm vi toàn bảng** trong lab nhỏ. Dù kết quả chỉ có ba nhóm theo ba partition ở dữ liệu mẫu, ở production nó có thể cần đọc rất nhiều partition trên nhiều node. Nếu API luôn truy vấn **một cửa hàng**, hãy đưa đầy đủ partition key/bucket vào `WHERE` và thiết kế schema theo phạm vi cần đọc.

### 8.2. LIMIT không làm aggregate trở nên rẻ một cách tự động

```sql
SELECT store_id,
       month_bucket,
       order_day,
       count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
LIMIT 1;
```

`LIMIT 1` giới hạn số **dòng kết quả nhóm** được trả về; nó không có nghĩa Cassandra chỉ đọc **một dòng đơn hàng** để tính `COUNT(*)`. Để cho ra số đếm đúng của nhóm được trả về, Cassandra phải xét những dòng thuộc nhóm đó theo semantics của aggregate.

Trong truy vấn có `GROUP BY`, `PER PARTITION LIMIT` và `LIMIT`, đừng đánh đồng **giới hạn số nhóm/result rows** với **giới hạn số raw rows được dùng để tính aggregate**. Cần kiểm tra hành vi trên phiên bản cluster và bài toán thực tế, nhất là khi phải chọn top-N theo một phép tổng hợp.

### 8.3. GROUP BY không thay điều kiện clustering hợp lệ

```sql
-- Hợp lý: giới hạn một partition và một ngày theo clustering.
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND order_day = '2026-11-20'
GROUP BY store_id, month_bucket, order_day;
```

Ngược lại, thêm `GROUP BY` vào câu có `WHERE status = 'PAID'` không tự làm điều kiện `status` trở thành khóa hoặc chỉ mục. `ALLOW FILTERING` nếu được dùng cho một số truy vấn chỉ cho phép Cassandra lọc dữ liệu rộng hơn, không tạo đường đọc rẻ hay khả năng nhóm tùy ý.

## 9. DISTINCT, GROUP BY và thiết kế bảng theo truy vấn

Một hệ Cassandra vận hành lâu dài nên xác định **loại thống kê thật sự cần cập nhật**, tần suất truy vấn và giới hạn độ trễ. Có ba hướng thực tế:

| Nhu cầu | Cách tiếp cận | Khi nào hợp lý |
| --- | --- | --- |
| Đếm tổng đơn của một cửa hàng trong một tháng nhỏ | `COUNT(*)` theo partition key đầy đủ | Số dòng trong partition được kiểm soát và QPS thống kê thấp. |
| Gom theo ngày trong một tháng nhỏ | `GROUP BY` theo tiền tố khóa `order_day` | Clustering order phù hợp, một partition hữu hạn. |
| Thống kê theo trạng thái/toàn hệ thống liên tục | Bảng tổng hợp duy trì trước hoặc pipeline ETL/streaming | Truy vấn nhiều partition, nhiều nhóm, yêu cầu p95/p99 thấp. |
| Liệt kê tháng có dữ liệu của cửa hàng | Bảng mục lục bucket hoặc `DISTINCT` trên tập partition đã biết | Tránh scan toàn bảng khi danh sách tháng lớn. |

Ví dụ bảng lưu số liệu đã tổng hợp theo ngày:

```sql
CREATE TABLE IF NOT EXISTS daily_order_summary_by_store_month (
    store_id uuid,
    month_bucket text,
    order_day date,
    order_count bigint,
    gross_cents bigint,
    PRIMARY KEY ((store_id, month_bucket), order_day)
) WITH CLUSTERING ORDER BY (order_day ASC);
```

Ứng dụng/pipeline có thể cập nhật số liệu theo quy trình riêng, rồi đọc:

```sql
SELECT order_day, order_count, gross_cents
FROM daily_order_summary_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11';
```

Mẫu này đưa chi phí tổng hợp ra khỏi đường đọc API; đổi lại, việc ghi đơn và cập nhật summary có thể xảy ra **không đồng thời**. Cần thiết kế xử lý trùng sự kiện, xóa/hủy đơn, retry, idempotency, backfill, sửa lệch và độ mới chấp nhận được. Không coi một `BATCH` CQL hoặc counter là giải pháp mặc định cho mọi yêu cầu đồng bộ nhiều partition.

Với yêu cầu thống kê realtime chính xác cao trên nhiều partition, cần xem xét kiến trúc xử lý tổng hợp ngoài truy vấn CQL trực tiếp, cùng chính sách consistency phù hợp.

## 10. Tích hợp Java: đọc nhóm với prepared statement

Ví dụ dùng Cassandra Java Driver 4.x, Java 15+ cho text blocks, và giả định đã có `CqlSession session` kết nối keyspace `cql_group_lab`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID storeId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

PreparedStatement prepared = session.prepare("""
    SELECT order_day,
           count(*) AS order_count,
           sum(amount_cents) AS gross_cents
    FROM orders_by_store_month
    WHERE store_id = ?
      AND month_bucket = ?
    GROUP BY store_id, month_bucket, order_day
    """);

BoundStatement statement = prepared.bind(
    storeId, "2026-11"
).setPageSize(50);

for (Row group : session.execute(statement)) {
    LocalDate day = group.getLocalDate("order_day");
    long count = group.getLong("order_count");
    long sumCents = group.getLong("gross_cents");
    System.out.printf("%s: count=%d, cents=%d%n",
        day, count, sumCents);
}
```

Với dữ liệu mẫu, vòng lặp có **hai nhóm**: ngày 20 (3, 55.000) và ngày 21 (2, 60.000). Lưu ý:

- Bind marker cho `store_id` (`uuid`) dùng `UUID`; `month_bucket` (`text`) dùng `String`.
- `count(*)` và `sum(amount_cents)` trên `bigint` trong ví dụ được đọc bằng `getLong`. Nếu đổi kiểu aggregate, phải điều chỉnh kiểu CQL và getter phù hợp.
- `setPageSize(50)` là **kích thước fetch** của driver, không giới hạn tập dòng Cassandra phải đọc để tính các nhóm. Nếu cần giới hạn số nhóm trả về, dùng mệnh đề `LIMIT` đúng ngữ nghĩa.
- Trong cluster phân tán, đọc với consistency level khác nhau có thể quan sát dữ liệu khác nhau nếu replica chưa hội tụ. Không trộn kết quả của các thời điểm khác nhau và gọi đó là snapshot giao dịch.

Nếu API cần nhiều tháng, cân nhắc truy vấn từng tháng bằng partition key đầy đủ, quản lý mức đồng thời và xác định có cần hợp nhất kết quả ở tầng ứng dụng hay không. Tránh chạy `GROUP BY` toàn bảng trong mỗi request phục vụ người dùng.

## 11. Bảng kiểm các ràng buộc CQL cần kiểm tra

| Câu hỏi kiểm tra | Ví dụ sai hoặc rủi ro | Hướng xử lý |
| --- | --- | --- |
| `DISTINCT` chọn cột gì? | `SELECT DISTINCT status` | Chỉ dùng partition key/static columns; cần trạng thái duy nhất thì thiết kế đường đọc khác. |
| `GROUP BY` dựa trên khóa nào? | `GROUP BY status` | Dùng primary-key prefix hợp lệ hoặc duy trì bảng tổng hợp theo trạng thái. |
| Có bỏ qua clustering column đứng trước? | `GROUP BY store_id, month_bucket, order_id` | Thêm `order_day` ở đúng vị trí nếu cần chia theo full key; hoặc đổi mô hình truy vấn. |
| `WHERE` định vị bao nhiêu partition? | `GROUP BY` toàn bảng | Đưa partition key đầy đủ vào `WHERE`; cân nhắc bucket phù hợp. |
| Có muốn lọc nhóm bằng `HAVING`? | `HAVING count(*) > 2` | CQL không có `HAVING` thông dụng; lọc nhóm nhỏ ở ứng dụng hoặc dùng summary. |
| Có muốn sắp theo aggregate? | `ORDER BY order_count DESC` | Cassandra `ORDER BY` phụ thuộc clustering order, không sắp theo alias tổng hợp. |
| Có chọn cột ngoài nhóm? | `SELECT status, count(*) GROUP BY ...` | Giá trị `status` chỉ đại diện một dòng, không đại diện nhóm; bỏ hoặc aggregate rõ ràng. |
| Có hiểu `LIMIT`? | `COUNT(*) ... LIMIT 1` được cho là đọc một raw row | Giới hạn result rows, không bảo đảm chi phí xử lý aggregate nhỏ. |
| Có cần thứ tự toàn cục trên nhiều partition? | `GROUP BY` với `IN` rất dài | Giới hạn fan-out, thiết kế cách hợp nhất hoặc bảng tổng hợp. |
| Đã kiểm soát dữ liệu động? | TTL/xóa/ghi đồng thời và inconsistency tạm thời | Quy định consistency, độ mới chấp nhận được và cơ chế đối soát. |

## 12. Bài tập thực hành có đáp án

### Bài 1. DISTINCT tháng có dữ liệu

**Yêu cầu:** Liệt kê những partition tháng `2026-11` và `2026-12` có dữ liệu của cửa hàng A, kèm static name.

**Đáp án:**

```sql
SELECT DISTINCT store_id, month_bucket, store_name
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket IN ('2026-11', '2026-12');
```

Với dữ liệu mẫu có **hai dòng kết quả**, mỗi dòng đại diện cho một partition tháng, không phải một đơn hàng.

### Bài 2. Đếm số đơn theo ngày trong một tháng

**Yêu cầu:** Cửa hàng A tháng 11, mỗi ngày có bao nhiêu đơn và tổng `amount_cents` là bao nhiêu?

**Đáp án:**

```sql
SELECT order_day,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
```

Ngày 20/11: **3 đơn, 55.000 cents**. Ngày 21/11: **2 đơn, 60.000 cents**.

### Bài 3. Phân tích truy vấn không hợp lệ

```sql
SELECT status, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY status;
```

**Đáp án:** `status` là regular column, không nằm trong primary key. Cassandra không hỗ trợ GROUP BY tùy ý trên cột này. Có thể tạo bảng tổng hợp theo trạng thái hoặc nhóm ở tầng ứng dụng nếu tập dữ liệu đã bị giới hạn rất nhỏ và yêu cầu cho phép.

### Bài 4. LIMIT có làm GROUP BY chỉ đọc một đơn?

```sql
SELECT order_day, count(*) AS order_count
FROM orders_by_store_month
WHERE store_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day
LIMIT 1;
```

**Đáp án:** Không. `LIMIT 1` giới hạn **một dòng nhóm trong kết quả**, không bảo đảm chỉ một đơn hàng được đọc để tính `count(*)` của nhóm đó.

### Bài 5. Nhu cầu top 10 trạng thái theo số đơn

**Yêu cầu:** Một dashboard muốn “10 trạng thái có số đơn nhiều nhất trong toàn hệ thống, cập nhật liên tục”, nhưng bảng chỉ có `status` là regular column.

**Đáp án gợi ý:** `GROUP BY status ORDER BY count(*) DESC` không phải truy vấn CQL được hỗ trợ trên bảng này. Cần một đường tổng hợp có kiểm soát (bảng summary, stream processor, analytical system), xác định cách cập nhật khi trạng thái đơn thay đổi và quy định độ mới dữ liệu. Đọc quét toàn bảng trong từng request sẽ không cho hiệu năng dự đoán được.

## 13. Ghi nhớ khi thiết kế truy vấn thống kê

Trước khi dùng `DISTINCT` hoặc `GROUP BY`, hãy tự trả lời:

1. **Phạm vi partition:** `WHERE` đã có đủ partition key hoặc danh sách partition hữu hạn chưa? Có thể ước lượng fan-out không?
2. **Khả năng DISTINCT:** Các cột được chọn có chỉ thuộc partition key/static columns không? Có nhầm với “distinct value của regular column” không?
3. **Khả năng GROUP BY:** Danh sách nhóm có là tiền tố primary key hợp lệ, đúng thứ tự, và phù hợp các cột đã hạn chế trong `WHERE` không?
4. **Ý nghĩa aggregate:** Có chọn cột ngoài nhóm rồi hiểu sai nó như đại diện cho toàn nhóm không? Kiểu `SUM`/`AVG`, null/TTL và đơn vị tiền có được xử lý đúng không?
5. **Giới hạn truy vấn:** `LIMIT` chỉ hạn chế result rows hay thật sự đã giới hạn tập dữ liệu phải đọc? Có cần pre-aggregation vì QPS/partition size lớn không?
6. **Vận hành phân tán:** Replication/consistency, retry, tombstones, compaction và repair tác động thế nào tới chi phí và dữ liệu quan sát?
7. **Ứng dụng Java:** Kiểu trả về, bind marker, paging và phạm vi của mỗi request có được kiểm soát và đo đạc không?

Điểm chính là **`DISTINCT` làm việc ở cấp partition key/static value, còn `GROUP BY` tuân theo cấu trúc primary key**. Nếu thống kê chủ yếu dựa trên cột thường hoặc cần nhóm/sắp xếp toàn cluster với độ trễ thấp, hãy tổ chức thêm dữ liệu phục vụ truy vấn đó thay vì kỳ vọng CQL sẽ xử lý như một SQL analytics engine.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Manipulation: SELECT, DISTINCT và GROUP BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra — CQL Data Definition: primary key, clustering và static columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra — CQL Functions: aggregate, COUNT, SUM, AVG](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html)
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
