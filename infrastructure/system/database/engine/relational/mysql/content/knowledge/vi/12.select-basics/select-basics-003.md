# WHERE, phép so sánh và kết hợp AND, OR, NOT

Mệnh đề `WHERE` lọc các hàng theo điều kiện trước khi truy vấn trả kết quả. Điều kiện có thể so sánh số, chuỗi, ngày giờ, kiểm tra `NULL`, kiểm tra một giá trị thuộc tập hợp hoặc kết hợp nhiều biểu thức bằng `AND`, `OR`, `NOT`. Viết điều kiện đúng giúp truy vấn trả đúng dữ liệu nghiệp vụ, tránh các lỗi thường gặp với `NULL`, thứ tự ưu tiên toán tử và chuyển đổi kiểu ngầm định.

Trong module `DATABASE_MYSQL`, `WHERE` là nền tảng của truy vấn SQL, join, cập nhật/xóa có điều kiện và tối ưu index. Một điều kiện đúng về logic nhưng không phù hợp kiểu dữ liệu hoặc không tận dụng được index vẫn có thể gây lỗi hoặc làm truy vấn chậm. Bài học dùng MySQL 8.x và ví dụ trên bảng đơn hàng.

## Mục tiêu

Sau bài này, bạn có thể:

- Dùng `WHERE` để lọc hàng bằng phép so sánh và biểu thức điều kiện.
- Kết hợp nhiều điều kiện bằng `AND`, `OR`, `NOT` và dấu ngoặc.
- Dự đoán thứ tự ưu tiên của toán tử logic.
- Xử lý đúng `NULL` theo logic ba giá trị của SQL.
- Dùng `IN`, `BETWEEN`, `LIKE`, `IS NULL` và so sánh null-safe.
- Tránh lỗi do chuyển đổi kiểu ngầm định, collation và điều kiện ngày giờ.
- Viết điều kiện có khả năng tận dụng index và kiểm tra bằng `EXPLAIN`.

## 1. WHERE dùng để làm gì?

`WHERE` xác định những hàng thỏa điều kiện. Với một hàng, biểu thức trong `WHERE` có thể cho kết quả `TRUE`, `FALSE` hoặc `UNKNOWN`. Chỉ những hàng có kết quả `TRUE` mới được giữ lại; `FALSE` và `UNKNOWN` đều bị loại.

Cú pháp cơ bản:

```sql
SELECT column_list
FROM table_name
WHERE condition;
```

Ví dụ, lấy các đơn hàng đã thanh toán:

```sql
SELECT order_id, customer_id, total_amount, status
FROM orders
WHERE status = 'PAID';
```

Điều kiện có thể áp dụng cho các lệnh khác:

```sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

DELETE FROM orders
WHERE status = 'CANCELLED';
```

Với `UPDATE` và `DELETE`, thiếu hoặc viết sai `WHERE` có thể làm thay đổi/xóa nhiều hàng hơn dự định. Trước thao tác ghi trên dữ liệu quan trọng, hãy chạy `SELECT` với chính điều kiện đó để xác nhận tập hàng bị ảnh hưởng.

## 2. Dữ liệu mẫu để thực hành

Các ví dụ sau sử dụng bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    shipping_fee DECIMAL(10, 2) NULL,
    created_at DATETIME(6) NOT NULL,
    paid_at DATETIME(6) NULL,
    note VARCHAR(255) NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_status (status),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO orders
    (customer_id, status, total_amount, shipping_fee, created_at, paid_at, note)
VALUES
    (101, 'PAID',       125000.00, 15000.00, '2026-01-05 09:10:00', '2026-01-05 09:12:00', 'Giao buổi sáng'),
    (102, 'PENDING',     89000.00,     NULL, '2026-01-06 10:00:00', NULL,                  NULL),
    (101, 'CANCELLED',  210000.00, 20000.00, '2026-01-07 11:30:00', NULL,                  'Khách đổi ý'),
    (103, 'PAID',       350000.00, 25000.00, '2026-01-08 14:00:00', '2026-01-08 14:03:00', 'Ưu tiên'),
    (104, 'PROCESSING',  99000.00,     NULL, '2026-01-09 08:15:00', NULL,                  'Chờ xác nhận'),
    (102, 'REFUNDED',   125000.00, 15000.00, '2026-01-10 16:45:00', '2026-01-06 10:05:00', NULL);
```

`status` được khai báo `NOT NULL`; `shipping_fee`, `paid_at` và `note` có thể là `NULL`. Các cột này giúp quan sát sự khác nhau giữa so sánh thông thường và kiểm tra `NULL`.

## 3. Các phép so sánh cơ bản

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `=` | Bằng | `status = 'PAID'` |
| `<>` hoặc `!=` | Khác | `status <> 'CANCELLED'` |
| `>` | Lớn hơn | `total_amount > 100000` |
| `>=` | Lớn hơn hoặc bằng | `total_amount >= 100000` |
| `<` | Nhỏ hơn | `total_amount < 100000` |
| `<=` | Nhỏ hơn hoặc bằng | `total_amount <= 100000` |

Ví dụ lọc đơn hàng có giá trị lớn hơn hoặc bằng 100.000:

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount >= 100000;
```

Tìm đơn hàng không ở trạng thái hủy:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED';
```

Do `status` trong bảng mẫu là `NOT NULL`, câu trên có thể phân loại mọi hàng. Nếu cột cho phép `NULL`, hàng có `status IS NULL` không được trả về vì `NULL <> 'CANCELLED'` cho kết quả `UNKNOWN`. Phải quyết định rõ có muốn giữ các hàng chưa có trạng thái hay không.

### 3.1. So sánh chuỗi và collation

So sánh chuỗi chịu ảnh hưởng của character set và collation của cột hoặc biểu thức. Collation quyết định quy tắc so sánh như phân biệt hoa/thường, dấu và thứ tự ký tự.

Ví dụ với collation không phân biệt hoa thường:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'paid';
```

Kết quả có thể khớp `PAID` nếu collation của `status` là collation case-insensitive, chẳng hạn một collation có hậu tố `_ci`. Nếu cần so sánh phân biệt hoa thường, hãy dùng collation phù hợp hoặc biểu thức binary có chủ đích. Không giả định mọi cột chuỗi đều có cùng quy tắc; kiểm tra collation thực tế của cột.

```sql
SHOW FULL COLUMNS FROM orders;
```

### 3.2. So sánh số và tránh ép kiểu không mong muốn

So sánh cột số với literal số cùng loại thường dễ hiểu và có khả năng tận dụng index:

```sql
SELECT order_id
FROM orders
WHERE customer_id = 101;
```

Tránh so sánh cột số với chuỗi không phải số hoặc dựa vào chuyển đổi ngầm định:

```sql
-- Không nên dựa vào chuyển đổi kiểu ngầm định:
SELECT order_id
FROM orders
WHERE customer_id = 'customer-101';
```

MySQL có thể chuyển đổi một toán hạng để thực hiện phép so sánh; kết quả có thể khác kỳ vọng, phát warning hoặc làm optimizer khó sử dụng index hiệu quả. Hãy bind đúng kiểu dữ liệu từ ứng dụng và dùng literal đúng loại trong SQL.

## 4. Kết hợp điều kiện bằng AND

`AND` chỉ cho kết quả `TRUE` khi tất cả điều kiện thành phần đều `TRUE`.

Ví dụ lấy đơn đã thanh toán có tổng tiền ít nhất 100.000:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE status = 'PAID'
  AND total_amount >= 100000;
```

Có thể thêm nhiều điều kiện:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND customer_id = 101
  AND total_amount BETWEEN 100000 AND 200000;
```

Mỗi điều kiện phải đúng để hàng được giữ lại. Nếu một điều kiện là `FALSE` hoặc `UNKNOWN`, kết quả `AND` không thể là `TRUE`.

## 5. Kết hợp điều kiện bằng OR

`OR` cho kết quả `TRUE` nếu ít nhất một điều kiện thành phần là `TRUE`.

Ví dụ lấy đơn đang chờ hoặc đang xử lý:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
   OR status = 'PROCESSING';
```

Có thể dùng `OR` để kết hợp hai nhóm tiêu chí:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE status = 'PAID'
   OR total_amount >= 300000;
```

Truy vấn trên lấy đơn đã thanh toán hoặc đơn có tổng tiền từ 300.000 trở lên, kể cả khi đơn đó chưa thanh toán. Hãy đọc điều kiện theo đúng ý nghĩa “ít nhất một nhánh đúng”.

### 5.1. OR có thể mở rộng tập hàng

Một lỗi thường gặp là dùng `OR` trong khi muốn cả hai điều kiện đều đúng:

```sql
-- Truy vấn này lấy đơn PAID hoặc đơn có giá trị cao.
WHERE status = 'PAID' OR total_amount > 300000
```

Nếu yêu cầu là đơn vừa `PAID` vừa có giá trị cao, phải dùng `AND`:

```sql
WHERE status = 'PAID' AND total_amount > 300000
```

Trước khi chạy truy vấn trên dữ liệu thật, hãy diễn đạt điều kiện bằng lời: “tất cả điều kiện đều đúng” tương ứng `AND`; “ít nhất một điều kiện đúng” tương ứng `OR`.

## 6. Phủ định bằng NOT

`NOT` đảo kết quả logic: `TRUE` thành `FALSE`, `FALSE` thành `TRUE`, còn `UNKNOWN` vẫn là `UNKNOWN`.

Ví dụ lấy đơn không phải `CANCELLED`:

```sql
SELECT order_id, status
FROM orders
WHERE NOT (status = 'CANCELLED');
```

Với cột `status NOT NULL`, câu này tương đương `status <> 'CANCELLED'`. Nếu cột có thể `NULL`, cả hai cách đều loại hàng `NULL` vì kết quả không xác định.

Phủ định một nhóm điều kiện:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE NOT (
    status = 'CANCELLED'
    OR total_amount < 100000
);
```

Theo định luật De Morgan, biểu thức trên tương đương:

```sql
WHERE status <> 'CANCELLED'
  AND total_amount >= 100000
```

Sự tương đương này cần được hiểu cùng logic `NULL`: nếu các cột có thể null, cả hai biểu thức vẫn có thể cho `UNKNOWN` và loại hàng đó. Nếu muốn giữ các hàng có `NULL`, phải thêm điều kiện riêng.

## 7. Thứ tự ưu tiên AND, OR, NOT

Trong MySQL, `NOT` có độ ưu tiên cao hơn `AND`, còn `AND` có độ ưu tiên cao hơn `OR`. Vì vậy, điều kiện:

```sql
WHERE status = 'PAID'
   OR status = 'PENDING'
  AND total_amount >= 100000
```

được hiểu là:

```sql
WHERE status = 'PAID'
   OR (status = 'PENDING' AND total_amount >= 100000)
```

Nó không tương đương với:

```sql
WHERE (status = 'PAID' OR status = 'PENDING')
  AND total_amount >= 100000
```

Hai truy vấn trên có thể trả về tập hàng khác nhau. Trong ví dụ đầu, mọi đơn `PAID` được chọn bất kể tổng tiền; chỉ nhánh `PENDING` mới cần tổng tiền từ 100.000. Trong ví dụ sau, cả `PAID` và `PENDING` đều phải đạt ngưỡng tiền.

**Thói quen tốt:** dùng dấu ngoặc để thể hiện nhóm logic theo ý định nghiệp vụ, kể cả khi đã biết thứ tự ưu tiên. Dấu ngoặc làm truy vấn dễ đọc, review và bảo trì hơn.

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE (status = 'PAID' OR status = 'PENDING')
  AND total_amount >= 100000;
```

## 8. Logic ba giá trị và NULL

SQL không chỉ có `TRUE` và `FALSE`. Khi một biểu thức so sánh có toán hạng `NULL`, kết quả thường là `UNKNOWN`.

| Biểu thức | Kết quả |
|---|---|
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> 10` | `UNKNOWN` |
| `10 = 10` | `TRUE` |
| `10 <> 20` | `TRUE` |
| `NOT UNKNOWN` | `UNKNOWN` |

Trong `WHERE`, chỉ hàng có điều kiện `TRUE` được giữ. Vì vậy:

```sql
SELECT order_id
FROM orders
WHERE paid_at = NULL;
```

không tìm được hàng có `paid_at` là `NULL`. Phải dùng:

```sql
SELECT order_id
FROM orders
WHERE paid_at IS NULL;
```

Tìm các đơn đã có thời điểm thanh toán:

```sql
SELECT order_id, paid_at
FROM orders
WHERE paid_at IS NOT NULL;
```

### 8.1. Bảng chân trị của AND, OR, NOT

Trong bảng dưới đây, `U` là `UNKNOWN`:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | U | U | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | U | FALSE | U |
| U | TRUE | U | TRUE |
| U | FALSE | FALSE | U |
| U | U | U | U |

`NOT TRUE = FALSE`, `NOT FALSE = TRUE`, `NOT U = U`.

Ví dụ, với `shipping_fee` có thể `NULL`:

```sql
SELECT order_id
FROM orders
WHERE shipping_fee > 10000;
```

Các hàng có `shipping_fee IS NULL` bị loại vì phép so sánh cho `UNKNOWN`. Nếu nghiệp vụ xem phí vận chuyển chưa xác định như 0:

```sql
SELECT order_id
FROM orders
WHERE shipping_fee IS NULL
   OR shipping_fee = 0;
```

Không tự động xem `NULL` là 0. `NULL` thường có nghĩa là chưa biết, chưa được cung cấp hoặc không áp dụng; chỉ gộp nó với 0 khi nghiệp vụ định nghĩa như vậy.

### 8.2. So sánh null-safe với `<=>`

MySQL có toán tử `<=>` để so sánh null-safe:

```sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS null_vs_number,
    10 <=> 10 AS same_number;
```

Kết quả lần lượt là `1`, `0`, `1`. Khác với `=`, `<=>` trả về TRUE khi cả hai toán hạng đều `NULL` và FALSE khi chỉ một bên `NULL`.

Ví dụ tìm các hàng có `note` bằng giá trị tham số, kể cả khi tham số là `NULL`:

```sql
SELECT order_id, note
FROM orders
WHERE note <=> NULL;
```

Trong truy vấn ứng dụng, `<=>` hữu ích khi cần so sánh null-safe. Nếu chỉ muốn tìm giá trị thiếu, `IS NULL` dễ đọc và thể hiện ý định rõ hơn.

## 9. IN và NOT IN

`IN` kiểm tra một biểu thức có bằng một trong các giá trị trong danh sách hay không:

```sql
SELECT order_id, status
FROM orders
WHERE status IN ('PAID', 'PROCESSING', 'PENDING');
```

Điều kiện trên tương đương kết hợp nhiều phép bằng bằng `OR`:

```sql
WHERE status = 'PAID'
   OR status = 'PROCESSING'
   OR status = 'PENDING'
```

`NOT IN` phủ định việc thuộc tập hợp:

```sql
SELECT order_id, status
FROM orders
WHERE status NOT IN ('CANCELLED', 'REFUNDED');
```

### 9.1. Cẩn thận khi danh sách NOT IN có NULL

Nếu danh sách `NOT IN` chứa `NULL`, kết quả có thể là `UNKNOWN` cho các giá trị không khớp bất kỳ phần tử nào. Ví dụ:

```sql
SELECT 1
WHERE 1 NOT IN (2, NULL);
```

Không có hàng nào được trả về, vì phép so sánh với `NULL` làm kết quả không xác định. Đây là lỗi thường gặp khi danh sách đến từ một subquery mà cột trả về có thể chứa `NULL`:

```sql
-- Có thể loại bỏ tất cả hàng ngoài các giá trị khớp nếu subquery trả NULL.
SELECT o.order_id
FROM orders AS o
WHERE o.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
);
```

Nếu dùng `NOT IN`, bảo đảm tập con không chứa `NULL`:

```sql
SELECT o.order_id
FROM orders AS o
WHERE o.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
    WHERE b.customer_id IS NOT NULL
);
```

Hoặc dùng `NOT EXISTS`, thường diễn đạt rõ ý “không có hàng khớp” và tránh bẫy `NULL` ở tập con:

```sql
SELECT o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customer AS b
    WHERE b.customer_id = o.customer_id
);
```

Nếu `o.customer_id` cũng có thể `NULL`, hãy quyết định rõ có muốn giữ hàng đó hay không. Với ví dụ bảng mẫu, `customer_id` là `NOT NULL`.

## 10. BETWEEN và điều kiện khoảng

`BETWEEN low AND high` kiểm tra giá trị nằm trong khoảng bao gồm cả hai đầu mút. Nó tương đương:

```sql
value >= low AND value <= high
```

Ví dụ:

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000;
```

Hàng có giá trị đúng 100.000 hoặc 200.000 vẫn được chọn. Nếu muốn khoảng nửa mở, hãy viết rõ `>=` và `<`.

### 10.1. Lọc ngày giờ theo khoảng nửa mở

Với cột `DATETIME` hoặc `TIMESTAMP`, nên dùng khoảng bắt đầu bao gồm và kết thúc loại trừ để lọc một ngày/tháng:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
```

Cách này lấy toàn bộ thời điểm trong tháng 1, kể cả phần microsecond cuối ngày 31/1. Tránh viết `BETWEEN '2026-01-01' AND '2026-01-31'` cho cột có thành phần thời gian vì mốc cuối thường được hiểu là đầu ngày 31/1, bỏ sót các thời điểm còn lại trong ngày.

## 11. LIKE và ký tự đại diện

`LIKE` tìm chuỗi theo mẫu:

- `%` khớp với không hoặc nhiều ký tự.
- `_` khớp với đúng một ký tự.

Ví dụ tìm ghi chú bắt đầu bằng “Giao”:

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE 'Giao%';
```

Tìm ghi chú có chứa từ “sáng”:

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE '%sáng%';
```

### 11.1. ESCAPE ký tự đại diện

Nếu cần tìm ký tự `%` hoặc `_` theo nghĩa literal, dùng ký tự escape:

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE '%!_%' ESCAPE '!';
```

Ví dụ trên tìm ghi chú có dấu gạch dưới. Ký tự `!` được khai báo làm escape character, nên `_` ngay sau nó được hiểu là dấu gạch dưới literal thay vì wildcard. Chọn một ký tự escape rõ ràng giúp tránh phụ thuộc vào cách SQL literal diễn giải backslash trong các cấu hình có `NO_BACKSLASH_ESCAPES`.

### 11.2. LIKE và index

Điều kiện dạng prefix như `name LIKE 'An%'` có thể dùng range scan trên index phù hợp. Điều kiện có wildcard ở đầu như `name LIKE '%An%'` thường không thể dùng B-tree index để tìm range trực tiếp vì không biết điểm bắt đầu của chuỗi. Với nhu cầu tìm kiếm chứa từ ở nội dung dài, cân nhắc FULLTEXT hoặc công cụ tìm kiếm phù hợp thay vì thêm index B-tree thông thường.

## 12. Điều kiện ngày giờ và kiểu dữ liệu

MySQL hỗ trợ so sánh ngày giờ với literal đúng định dạng:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-08 00:00:00'
  AND created_at <  '2026-01-10 00:00:00';
```

Literal ở đây biểu diễn giá trị ngày giờ; với cột `TIMESTAMP`, kết quả còn chịu ảnh hưởng của session timezone khi MySQL diễn giải và trả giá trị. Với `DATETIME`, giá trị được so sánh như ngày giờ lịch không tự chuyển múi giờ.

Không nên bọc cột được index trong hàm nếu có thể lọc bằng khoảng trực tiếp:

```sql
-- Thường khó tận dụng range index trên created_at:
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-08';

-- Ưu tiên điều kiện range:
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-08 00:00:00'
  AND created_at <  '2026-01-09 00:00:00';
```

Điều kiện range giữ nguyên cột index ở một phía của phép so sánh và thường dễ được optimizer sử dụng hơn.

## 13. Điều kiện WHERE và index

`WHERE` xác định tập hàng cần đọc; index có thể giúp MySQL tìm những hàng thỏa điều kiện mà không quét toàn bộ bảng. Tuy nhiên, việc dùng index phụ thuộc cardinality, thống kê, số hàng cần trả, thứ tự cột trong composite index, kiểu dữ liệu và hình dạng biểu thức.

### 13.1. Điều kiện bằng trên cột có index

Với index `idx_orders_customer(customer_id)`:

```sql
EXPLAIN
SELECT order_id, status, total_amount
FROM orders
WHERE customer_id = 101;
```

Optimizer có thể chọn index lookup/range trên `customer_id`. Xem các cột `key`, `type`, `rows` và `filtered` trong `EXPLAIN`; không chỉ nhìn một giá trị `type` để kết luận.

### 13.2. Kết hợp AND và composite index

Nếu truy vấn thường lọc theo khách hàng và trạng thái, một composite index có thể phù hợp:

```sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
```

Truy vấn:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101
  AND status = 'PAID';
```

có thể dùng cả hai phần của index. Thứ tự cột quan trọng: index `(customer_id, status)` thường hỗ trợ truy vấn theo `customer_id` hoặc theo cả `customer_id` và `status`; nó không tương đương index chỉ có `status` khi truy vấn không lọc `customer_id`.

### 13.3. OR và index

`OR` có thể làm optimizer chọn nhiều range scan hoặc một access path khác. Ví dụ:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 101
   OR status = 'PENDING';
```

Nếu mỗi nhánh có index riêng, MySQL có thể cân nhắc Index Merge. Nhưng Index Merge không luôn nhanh hơn table scan hoặc một index khác. Hãy kiểm tra `EXPLAIN` và số hàng thực tế, không tự tách `OR` thành `UNION` khi chưa xác nhận kết quả và hiệu năng.

### 13.4. Tránh biến đổi cột trong WHERE

Một biểu thức như:

```sql
WHERE YEAR(created_at) = 2026
```

thường không tận dụng được range access trên index thường của `created_at`. Thay bằng khoảng:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

Tương tự, tránh `CAST(indexed_column AS ...)`, `LOWER(indexed_column)` hoặc phép toán trên cột nếu mục tiêu là range lookup. Nếu cần truy vấn theo biểu thức, cân nhắc functional index hoặc generated column được index, sau khi kiểm tra khả năng hỗ trợ của phiên bản và workload.

## 14. Dùng WHERE an toàn trong ứng dụng

Không ghép trực tiếp dữ liệu người dùng vào chuỗi SQL. Dùng prepared statement để truyền giá trị dưới dạng tham số:

```java
String sql = """
    SELECT order_id, status, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
      AND total_amount >= ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);
    statement.setBigDecimal(3, minimumAmount);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Đọc kết quả theo cột cần thiết.
        }
    }
}
```

Prepared statement giúp tách dữ liệu khỏi cấu trúc SQL, giảm nguy cơ SQL injection và tránh lỗi escape literal. Placeholder chỉ đại diện cho giá trị; không thể dùng `?` để bind tên bảng, tên cột, toán tử hoặc từ khóa `ASC`/`DESC`. Các phần cấu trúc động phải được chọn từ danh sách cho phép.

Với điều kiện tùy chọn, hãy xây dựng phần SQL theo cấu trúc đã kiểm soát và bind từng giá trị. Tránh mẫu `WHERE (? IS NULL OR column = ?)` một cách máy móc trên bảng lớn vì biểu thức OR có thể ảnh hưởng khả năng dùng index; có thể tạo câu SQL riêng cho từng trường hợp lọc.

## 15. Các lỗi WHERE thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| `column = NULL` | So sánh với NULL cho `UNKNOWN` | Dùng `IS NULL` hoặc `<=>` khi cần null-safe equality |
| Nhầm AND/OR do thiếu ngoặc | `AND` có ưu tiên cao hơn `OR` | Dùng ngoặc thể hiện nhóm điều kiện |
| `NOT IN` nhận danh sách có NULL | Kết quả có thể thành `UNKNOWN` | Lọc NULL trong subquery hoặc dùng `NOT EXISTS` |
| `BETWEEN` cho ngày kết thúc là ngày cuối lúc 00:00 | Bỏ sót phần còn lại của ngày cuối | Dùng khoảng `>= start AND < next_start` |
| So sánh số với chuỗi tùy tiện | Phát sinh chuyển kiểu ngầm định | Bind đúng kiểu, kiểm tra warning và schema |
| `LIKE '%text%'` kỳ vọng dùng B-tree | Wildcard đầu chuỗi không tạo range prefix | Cân nhắc FULLTEXT hoặc giải pháp tìm kiếm phù hợp |
| Bọc cột index trong hàm | Có thể khiến điều kiện không sargable | Chuyển đổi biên trước, so sánh trực tiếp với cột |
| Chạy UPDATE/DELETE mà chưa kiểm tra WHERE | Có thể tác động nhầm nhiều hàng | Chạy SELECT cùng điều kiện, kiểm tra số hàng và dùng transaction khi phù hợp |

## 16. Quy trình viết và kiểm tra điều kiện

Khi viết truy vấn có nhiều điều kiện, làm theo trình tự:

1. Viết yêu cầu bằng lời, xác định điều kiện bắt buộc và điều kiện thay thế.
2. Xác định cột nào có thể `NULL`, kiểu dữ liệu và collation của cột chuỗi.
3. Chia nhóm logic bằng dấu ngoặc; dùng `AND` cho điều kiện đồng thời và `OR` cho các lựa chọn.
4. Kiểm tra các trường hợp biên: giá trị bằng ngưỡng, `NULL`, chuỗi rỗng, danh sách `IN` rỗng/đặc biệt và thời điểm ở biên ngày.
5. Chạy truy vấn trên dữ liệu mẫu để xác nhận kết quả.
6. Dùng `EXPLAIN` để xem access path, index được chọn và ước lượng số hàng.
7. Với `UPDATE`/`DELETE`, chạy `SELECT` có cùng `WHERE` trước khi thực hiện và xác nhận phạm vi thay đổi.

Ví dụ yêu cầu: lấy các đơn hàng của khách 101 hoặc 102, ở trạng thái đã thanh toán, có tổng tiền từ 100.000 trở lên:

```sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE customer_id IN (101, 102)
  AND status = 'PAID'
  AND total_amount >= 100000;
```

Nếu yêu cầu là đơn của khách 101, hoặc bất kỳ đơn nào của khách 102 có giá trị cao, cần nhóm điều kiện khác:

```sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE customer_id = 101
   OR (customer_id = 102 AND total_amount >= 300000);
```

Hai truy vấn có ý nghĩa nghiệp vụ khác nhau dù cùng nhắc tới hai customer ID. Dấu ngoặc giúp biểu đạt chính xác nhánh điều kiện.

## 17. Bài thực hành

Thực hiện với bảng `orders` ở phần 2:

1. Lấy các đơn có `status = 'PAID'` và `total_amount >= 100000`.
2. Lấy đơn có trạng thái `PENDING` hoặc `PROCESSING` bằng `OR`, sau đó viết lại bằng `IN`.
3. Lấy đơn không phải `CANCELLED` và giải thích kết quả nếu cột `status` cho phép `NULL`.
4. Lấy các đơn có `paid_at IS NULL`; thử lại bằng `paid_at = NULL` và giải thích vì sao không trả kết quả mong muốn.
5. Dùng `<=>` để so sánh một tham số có thể null với `note`.
6. Viết truy vấn `NOT IN` với một subquery có thể trả `NULL`, quan sát kết quả rồi sửa bằng `NOT EXISTS`.
7. Lọc đơn trong toàn bộ tháng 1/2026 bằng khoảng nửa mở; so sánh với điều kiện `BETWEEN` có mốc cuối là ngày 31.
8. Tìm ghi chú bắt đầu bằng `Giao`, chứa `sáng`, và chứa ký tự `_` theo nghĩa literal.
9. Viết hai truy vấn có `AND`/`OR` nhưng khác cách đặt ngoặc; tạo dữ liệu kiểm thử để chứng minh tập kết quả khác nhau.
10. Chạy `EXPLAIN` cho truy vấn theo `customer_id`, theo `status` và theo cả hai; thử thêm composite index phù hợp rồi so sánh access path.
11. Viết một `UPDATE` trong transaction lab: chạy `SELECT` cùng `WHERE` trước, kiểm tra số hàng, cập nhật, xác minh và commit/rollback.
12. Viết truy vấn JDBC dùng `PreparedStatement` với ba tham số lọc và kiểm tra kiểu bind.

Bạn hoàn thành bài khi tự dự đoán được kết quả của điều kiện nhiều nhánh, xử lý đúng `NULL`, chọn được khoảng ngày giờ chính xác và giải thích được index có thể hỗ trợ điều kiện nào.

## 18. Nguyên tắc cần ghi nhớ

- `WHERE` chỉ giữ hàng khi biểu thức trả về `TRUE`; `FALSE` và `UNKNOWN` đều bị loại.
- Dùng `IS NULL`/`IS NOT NULL` để kiểm tra NULL; dùng `<=>` khi cần so sánh null-safe.
- `NOT` ưu tiên cao hơn `AND`, `AND` ưu tiên cao hơn `OR`; dùng ngoặc để nhóm logic rõ ràng.
- `IN` tương đương nhiều phép bằng kết hợp `OR`; cẩn thận với `NOT IN` khi tập con chứa `NULL`.
- `BETWEEN` bao gồm cả hai đầu mút; với ngày giờ thường nên dùng khoảng `>= start AND < next_start`.
- So sánh chuỗi phụ thuộc collation; so sánh số/ngày giờ nên dùng đúng kiểu dữ liệu.
- Điều kiện prefix `LIKE 'text%'` có thể tận dụng B-tree index; wildcard đầu chuỗi thường không thể dùng range prefix.
- Giữ cột index ở dạng trực tiếp trong điều kiện; tránh bọc hàm nếu muốn range access.
- Dùng prepared statement cho giá trị do người dùng cung cấp.
- Trước `UPDATE` hoặc `DELETE`, xác minh tập hàng bằng `SELECT` có cùng điều kiện.
