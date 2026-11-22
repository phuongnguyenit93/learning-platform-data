# NOT IN, NULL và truy vấn tìm phần thiếu trong PostgreSQL

Một bài toán thường gặp khi kết hợp dữ liệu là tìm **những bản ghi chưa có quan hệ tương ứng**. Ví dụ: khách hàng chưa đặt đơn, sản phẩm chưa được bán, sinh viên chưa đăng ký khóa học, hóa đơn chưa có thanh toán, hoặc mã khách hàng trong file import không tồn tại trong bảng chính.

Người mới học SQL thường viết:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

Câu trên có vẻ đúng: chọn những mã khách hàng không nằm trong danh sách mã xuất hiện ở đơn hàng. Nhưng chỉ cần subquery trả về **một giá trị `NULL`**, một kết quả đáng ngạc nhiên có thể xảy ra: truy vấn `NOT IN` không trả về khách hàng nào, ngay cả khi thực tế có nhiều người chưa có đơn.

Nguyên nhân là SQL sử dụng **logic ba giá trị**: `TRUE`, `FALSE` và `UNKNOWN`. PostgreSQL không xem so sánh với `NULL` là so sánh bằng thông thường. Khi tìm dữ liệu thiếu, việc hiểu `NULL` quyết định kết quả đúng hay sai.

Bài học này giải thích những cách diễn đạt **anti-join**, tức “lấy hàng từ tập A mà không tồn tại hàng khớp ở tập B”, bằng:

- `NOT IN` khi bảo đảm ngữ nghĩa `NULL` phù hợp.
- `NOT EXISTS` với điều kiện tương quan, thường là cách diễn đạt rõ ràng và an toàn cho bài toán **không có hàng khớp**.
- `LEFT JOIN ... IS NULL` với cột kiểm tra không NULL ở hàng B thực sự đã khớp.
- `EXCEPT` để lấy hiệu của hai tập kết quả.
- `IS DISTINCT FROM` và `IS NOT DISTINCT FROM` khi nghiệp vụ cần phép so sánh xác định với `NULL`.

Chúng ta cũng xem xét các điều kiện phụ như trạng thái đơn, khoảng thời gian, khóa ghép, duplicate, index, transaction và các tình huống khiến hai câu SQL trông giống nhau nhưng không tương đương.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `NOT IN` tương tác với `NULL` và vì sao `NOT (UNKNOWN)` vẫn là `UNKNOWN`.
2. Viết `NOT EXISTS` để tìm khách hàng không có đơn, sản phẩm chưa được liên kết hoặc bản ghi import không có khóa tham chiếu.
3. Dùng `LEFT JOIN ... WHERE right_table.primary_key IS NULL` để tìm hàng không khớp.
4. Đặt điều kiện lọc bảng bên phải đúng trong `ON` khi tìm **không có hàng thỏa một điều kiện cụ thể**.
5. Dùng `EXCEPT` và hiểu cách loại duplicate cũng như cách các phép toán tập hợp xử lý `NULL`.
6. Phân biệt `NULL` là “chưa biết” với “không tồn tại hàng liên quan”.
7. Phân tích những trường hợp đặc biệt: danh sách rỗng, cột nullable, khóa ghép và giá trị thiếu ở hai phía.
8. Chọn câu truy vấn phù hợp về mặt ngữ nghĩa và xem `EXPLAIN` khi bảng lớn.
9. Hiểu rằng truy vấn phát hiện thiếu dữ liệu **không tự tạo ràng buộc toàn vẹn vĩnh viễn** trong môi trường nhiều giao dịch.
10. Hoàn thành bài thực hành SQL tự chứa trên PostgreSQL.

**Thông điệp cốt lõi:** khi muốn hỏi “**không tồn tại một hàng ở bảng B khớp với hàng hiện tại ở bảng A**”, hãy bắt đầu từ ý nghĩa `NOT EXISTS`; chỉ dùng `NOT IN` khi bạn đã xác minh chính xác cách dữ liệu và `NULL` được xử lý.

---

## 2. “Phần thiếu” có nhiều ý nghĩa khác nhau

Trước khi viết SQL, cần xác định **thiếu điều gì**:

| Câu hỏi nghiệp vụ | Hàng muốn tìm | Điều kiện khớp |
| --- | --- | --- |
| Khách hàng chưa từng có đơn | Khách hàng không có bất kỳ order | `orders.customer_id = customers.customer_id` |
| Khách hàng chưa có đơn đã thanh toán | Khách hàng không có order `status = 'PAID'` | Khớp ID **và** status PAID |
| Khách hàng chưa có đơn trong tháng 3 | Không có order trong khoảng tháng 3 | Khớp ID **và** thời gian |
| Dòng CSV dùng customer_id không tồn tại | Dòng staging với mã tham chiếu sai | Khớp ID với bảng customers |
| Mã tham chiếu của file bị bỏ trống | Dòng staging có `customer_id IS NULL` | Không phải cùng vấn đề “mã có nhưng không tồn tại” |
| Sản phẩm chưa xuất hiện trong chi tiết đơn | Sản phẩm không có order_item tương ứng | Khớp `product_id` qua bảng trung gian |
| Cặp (tenant_id, external_id) không tồn tại | Bản ghi chưa có đúng khóa ghép | Khớp **cả hai** cột |

Câu “khách hàng chưa có đơn” và “khách hàng chưa có đơn đã thanh toán” **không tương đương**. Một người có đơn DRAFT hoặc CANCELED vẫn là người **đã có đơn**, nhưng chưa có đơn PAID.

Trước khi chọn cú pháp, hãy viết rõ:

> Lấy các hàng A mà **không tồn tại** hàng B thỏa điều kiện kết nối và điều kiện nghiệp vụ xác định.

Cách diễn đạt này giúp tránh việc vô tình tìm những hàng “có một đơn chưa thanh toán” thay vì “không có đơn thanh toán nào”.

---

## 3. Chuẩn bị bảng và dữ liệu thực hành

Chúng ta tạo hai bảng chính: `customers` và `orders`. Một khách hàng có thể có nhiều đơn; một đơn trong bảng nghiệp vụ phải tham chiếu một khách hàng tồn tại.

Ngoài ra, bảng `customer_exclusions` chứa cố ý một `customer_id NULL` để minh họa bẫy `NOT IN`. Bảng `imported_order_refs` mô phỏng dữ liệu chưa được kiểm tra từ CSV, cho phép mã khách hàng không tồn tại hoặc bị thiếu.

> **Cảnh báo:** Các lệnh `DROP TABLE IF EXISTS` bên dưới xóa dữ liệu hiện có trong đúng các bảng của schema `missing_lab`. Chỉ chạy trong **database học tập có quyền reset**, không chạy nguyên khối trên production.

### 3.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS missing_lab;

DROP TABLE IF EXISTS missing_lab.orders;
DROP TABLE IF EXISTS missing_lab.customers;
DROP TABLE IF EXISTS missing_lab.customer_exclusions;
DROP TABLE IF EXISTS missing_lab.imported_order_refs;

CREATE TABLE missing_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE missing_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES missing_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE missing_lab.customer_exclusions (
    exclusion_id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    reason TEXT NOT NULL
);

CREATE TABLE missing_lab.imported_order_refs (
    import_ref TEXT PRIMARY KEY,
    customer_id BIGINT,
    raw_description TEXT NOT NULL
);
```

Trong bảng `orders`, `customer_id` có cả `NOT NULL` lẫn `FOREIGN KEY`, nên **không thể có đơn hàng hợp lệ với customer_id NULL** hoặc với mã không tồn tại ở bảng customers. Đây là những bảo đảm của schema, không phải của `NOT IN`.

Hai bảng còn lại không có foreign key vì nhiệm vụ của chúng là lưu dữ liệu **có thể thiếu hoặc sai**, để chúng ta thử các truy vấn tìm phần thiếu.

### 3.2. Thêm khách hàng

```sql
INSERT INTO missing_lab.customers (
    customer_id, customer_name, region
)
VALUES
    (1, 'An',   'NORTH'),
    (2, 'Bình', 'SOUTH'),
    (3, 'Chi',  'NORTH'),
    (4, 'Dũng', 'CENTRAL'),
    (5, 'Hà',   'SOUTH'),
    (6, 'Lan',  'CENTRAL'),
    (7, 'Mai',  'NORTH'),
    (8, 'Nam',  'SOUTH');
```

Có tám khách hàng, từ ID 1 tới 8.

### 3.3. Thêm đơn hàng

```sql
INSERT INTO missing_lab.orders (
    order_id, customer_id, status, total_amount, ordered_at
)
VALUES
    (101, 1, 'PAID',      120000, '2026-01-05 08:00:00+00'),
    (102, 1, 'DRAFT',      25000, '2026-02-02 09:00:00+00'),
    (103, 2, 'CANCELED',   50000, '2026-02-10 11:00:00+00'),
    (104, 3, 'PAID',       99000, '2026-02-11 15:00:00+00'),
    (105, 5, 'PAID',      250000, '2026-03-01 00:00:00+00'),
    (106, 5, 'PAID',       65000, '2026-04-01 00:00:00+00'),
    (107, 6, 'DRAFT',      35000, '2026-03-20 17:00:00+00'),
    (108, 8, 'CANCELED',   22000, '2026-04-02 10:00:00+00');
```

Quan hệ dữ liệu:

```text
Khách hàng        Đơn hàng                 Có đơn PAID?
-------------------------------------------------------------
1  An             101 PAID, 102 DRAFT       Có
2  Bình           103 CANCELED              Không
3  Chi            104 PAID                  Có
4  Dũng           (không có đơn)            Không
5  Hà             105 PAID, 106 PAID        Có
6  Lan            107 DRAFT                 Không
7  Mai            (không có đơn)            Không
8  Nam            108 CANCELED              Không
```

Từ dữ liệu này:

- **Chưa có bất kỳ đơn nào:** khách hàng 4, 7.
- **Chưa có đơn PAID:** khách hàng 2, 4, 6, 7, 8.
- **Đã có đơn nhưng chưa có đơn PAID:** khách hàng 2, 6, 8.
- **Có đơn PAID trong tháng 3/2026 theo UTC:** chỉ khách hàng 5.

Những tập kết quả này sẽ là căn cứ đối chiếu trong bài.

### 3.4. Thêm dữ liệu có NULL

```sql
INSERT INTO missing_lab.customer_exclusions (
    exclusion_id, customer_id, reason
)
VALUES
    (1, 2, 'Tạm ngừng liên hệ'),
    (2, NULL, 'Chưa xác định mã khách hàng'),
    (3, 6, 'Không tham gia chương trình');

INSERT INTO missing_lab.imported_order_refs (
    import_ref, customer_id, raw_description
)
VALUES
    ('r1', 1,    'Tham chiếu hợp lệ tới An'),
    ('r2', 3,    'Tham chiếu hợp lệ tới Chi'),
    ('r3', 99,   'Mã khách hàng không tồn tại'),
    ('r4', NULL, 'Mã khách hàng bị để trống'),
    ('r5', 99,   'Tham chiếu thiếu lặp lại');
```

Bảng exclusions có **một NULL ở danh sách bên phải**; bảng import có **một NULL ở cột cần tra cứu** và hai hàng cùng tham chiếu mã 99 không tồn tại. Điều này giúp so sánh nhiều câu SQL trên cùng dữ liệu.

### 3.5. Kiểm tra bảng

```sql
SELECT customer_id, customer_name
FROM missing_lab.customers
ORDER BY customer_id;

SELECT order_id, customer_id, status, ordered_at
FROM missing_lab.orders
ORDER BY order_id;

SELECT exclusion_id, customer_id
FROM missing_lab.customer_exclusions
ORDER BY exclusion_id;

SELECT import_ref, customer_id
FROM missing_lab.imported_order_refs
ORDER BY import_ref;
```

Nếu mọi INSERT đã thành công, có 8 khách hàng, 8 đơn hàng, 3 dòng exclusion và 5 dòng import.

---

## 4. Trước NOT IN: SQL có ba giá trị logic

Trong SQL, phép so sánh có thể trả:

- `TRUE`: đúng.
- `FALSE`: sai.
- `NULL`/UNKNOWN: không đủ thông tin để xác định đúng hoặc sai.

Ví dụ:

```sql
SELECT
    5 = 5 AS true_case,
    5 = 6 AS false_case,
    5 = NULL::INTEGER AS unknown_case,
    NULL::INTEGER = NULL::INTEGER AS two_nulls_equal;
```

Hai biểu thức so sánh với `NULL` trả `NULL`, **không phải FALSE**, và hai NULL cũng không được coi là bằng nhau dưới toán tử `=` thông thường.

Điều này dẫn tới bảng:

| Biểu thức | Kết quả |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 6` | FALSE |
| `5 = NULL` | NULL |
| `NULL = NULL` | NULL |
| `NOT TRUE` | FALSE |
| `NOT FALSE` | TRUE |
| `NOT NULL` | NULL |

### 4.1. WHERE chỉ giữ TRUE

Một câu:

```sql
SELECT *
FROM some_table
WHERE condition;
```

chỉ giữ hàng khi `condition` là **TRUE**. Hàng có FALSE và NULL đều không được trả về.

Vì vậy một phép lọc có thể “mất” hàng mà không có lỗi SQL nào: biểu thức trả UNKNOWN chứ không phải TRUE.

### 4.2. NULL khác với không tồn tại hàng

Hai khái niệm cần phân biệt:

1. **Không có hàng khớp:** bảng bên phải không chứa một bản ghi thỏa điều kiện.
2. **Có hàng nhưng khóa của nó là NULL:** dữ liệu bên phải có bản ghi, nhưng giá trị cần so sánh bị thiếu.

Với `NOT EXISTS`, chúng ta hỏi trực tiếp câu (1). Với `NOT IN`, các phép so sánh với NULL trong câu (2) có thể làm kết quả thành UNKNOWN.

---

## 5. IN và NOT IN hoạt động như thế nào?

Cú pháp:

```sql
expression IN (value_1, value_2, ...)
expression NOT IN (value_1, value_2, ...)
```

Với một danh sách giá trị không NULL:

```sql
SELECT
    2 IN (1, 2, 3) AS two_is_in,
    4 NOT IN (1, 2, 3) AS four_is_not_in;
```

Kết quả đều TRUE.

Có thể suy nghĩ:

```sql
x IN (a, b, c)
```

gần với:

```sql
x = a OR x = b OR x = c
```

và:

```sql
x NOT IN (a, b, c)
```

gần với:

```sql
x <> a AND x <> b AND x <> c
```

Với `NULL`, phép so sánh có thể trả UNKNOWN nên trực giác “không bằng bất kỳ cái nào” dễ bị sai.

### 5.1. Một NULL bên phải làm thay đổi kết quả

```sql
SELECT
    2 NOT IN (2, NULL) AS matched_left,
    3 NOT IN (2, NULL) AS unmatched_left,
    3 IN (2, NULL) AS in_with_null;
```

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `2 NOT IN (2, NULL)` | FALSE, vì 2 đã khớp 2 |
| `3 NOT IN (2, NULL)` | NULL, vì `3 <> NULL` là UNKNOWN |
| `3 IN (2, NULL)` | NULL, vì không có phần tử TRUE nhưng có UNKNOWN |

Tại sao `3 NOT IN (2,NULL)` không phải TRUE?

```text
3 NOT IN (2, NULL)
    |
    v
(3 <> 2) AND (3 <> NULL)
    |
    v
 TRUE AND UNKNOWN
    |
    v
 UNKNOWN
    |
    v
WHERE không giữ hàng
```

Nói cách khác: PostgreSQL không thể khẳng định 3 **khác mọi phần tử** của danh sách nếu một phần tử chưa biết giá trị.

### 5.2. Không phải cứ xuất hiện NULL là mọi hàng đều UNKNOWN

Với:

```sql
SELECT 2 NOT IN (2, NULL);
```

câu trả FALSE vì đã có phép so sánh `2 = 2` là TRUE; điều này đủ kết luận 2 **thuộc** danh sách.

Do đó, khi danh sách bên phải có NULL:

- Giá trị đã khớp một phần tử non-NULL → `NOT IN` trả FALSE.
- Giá trị không khớp phần tử non-NULL nào → `NOT IN` thường trả NULL.
- Trong điều kiện WHERE → không có hàng nào được giữ nếu tất cả khóa bên trái là non-NULL và danh sách bên phải chứa NULL.

Đây là một lỗi dữ liệu có thể khiến truy vấn “tìm phần thiếu” trả **tập rỗng sai**.

---

## 6. Ví dụ bẫy NOT IN với subquery

Trong lab, `customer_exclusions` chứa các mã:

```text
2
NULL
6
```

Giả sử mục tiêu là tìm khách hàng **không có trong danh sách bị loại trừ**.

Câu dễ viết:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM missing_lab.customer_exclusions AS e
)
ORDER BY c.customer_id;
```

**Kết quả:** không có hàng nào, dù chỉ có khách hàng 2 và 6 được xác định trong exclusions.

Lý do: subquery có một `NULL`. Với khách hàng khác 2 và 6, PostgreSQL không chứng minh được `customer_id <> NULL`, nên `NOT IN` trả UNKNOWN. Với khách hàng 2 và 6, kết quả FALSE vì đã khớp một giá trị.

### 6.1. Cách sửa thứ nhất: loại NULL trong subquery

Nếu nghiệp vụ nói rằng hàng exclusion chưa có mã khách hàng **không chặn bất kỳ khách hàng cụ thể nào**, có thể viết:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM missing_lab.customer_exclusions AS e
    WHERE e.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Kết quả là:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 3 | Chi |
| 4 | Dũng |
| 5 | Hà |
| 7 | Mai |
| 8 | Nam |

Vì `customers.customer_id` là PRIMARY KEY, khóa bên trái cũng không NULL. Sau khi loại NULL ở bên phải, `NOT IN` có thể diễn đạt đúng phép loại trừ theo mã.

Nhưng chú ý: **lọc bỏ NULL là một quyết định nghiệp vụ**, không phải lúc nào cũng được phép bỏ dữ liệu thiếu. Nếu một dòng exclusion không rõ customer_id cần được điều tra, nên ghi nhận riêng thay vì âm thầm coi nó không có ảnh hưởng.

### 6.2. Cách sửa thứ hai: NOT EXISTS

Viết:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.customer_exclusions AS e
    WHERE e.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả cũng là sáu khách hàng 1, 3, 4, 5, 7, 8.

Ở đây, điều kiện `e.customer_id = c.customer_id` chỉ TRUE khi hai giá trị **thực sự bằng nhau**. Dòng `e.customer_id = NULL` không khớp bất kỳ `customer_id` non-NULL nào, nên không làm toàn bộ phép tìm phần thiếu thành UNKNOWN.

### 6.3. Có nên luôn dùng NOT EXISTS?

Khi yêu cầu là “không có bản ghi tương ứng”, `NOT EXISTS` thường là điểm bắt đầu **dễ diễn đạt ngữ nghĩa và ít bị bẫy NULL của tập bên phải**.

Tuy vậy, “NOT EXISTS luôn đúng” cũng cần hiểu điều kiện bên trong:

- Bạn phải đặt **đúng khóa kết nối**.
- Phải đặt **đúng bộ lọc nghiệp vụ**.
- Nếu muốn hai giá trị NULL được xem là khớp nhau, toán tử `=` thông thường **không đủ**.
- Nếu subquery là tập dữ liệu từ tenant khác hoặc thời điểm khác, kết quả vẫn sai dù cú pháp NOT EXISTS chuẩn.
- Nếu có điều kiện lọc thời gian hoặc soft-delete, phải định nghĩa “tồn tại” theo phạm vi đó.

Vì vậy, ưu tiên `NOT EXISTS` không có nghĩa bỏ qua bước xác định quan hệ khớp.

---

## 7. NOT EXISTS: hỏi trực tiếp “có hàng khớp hay không?”

Dạng tổng quát:

```sql
SELECT a.*
FROM table_a AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM table_b AS b
    WHERE b.key = a.key
);
```

PostgreSQL đánh giá `EXISTS (subquery)` theo việc subquery có **ít nhất một hàng** hay không:

- Có ít nhất một hàng → `EXISTS` là TRUE → `NOT EXISTS` là FALSE.
- Không có hàng → `EXISTS` là FALSE → `NOT EXISTS` là TRUE.

`EXISTS` không quan tâm cột được SELECT bên trong có giá trị gì, kể cả NULL.

### 7.1. SELECT 1 hay SELECT *?

Hai cách phổ biến:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

và:

```sql
WHERE NOT EXISTS (
    SELECT *
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

thường tương đương về ý nghĩa đối với subquery cơ bản: chỉ cần biết có hàng hay không. `SELECT 1` là quy ước diễn đạt rõ rằng **không cần dữ liệu từ hàng bên trong**.

Không nên khẳng định cách `SELECT 1` luôn nhanh hơn `SELECT *`: planner có thể tối ưu cả hai theo cách tương tự. Sự khác biệt quan trọng nằm ở điều kiện khớp và kế hoạch truy vấn, không phải giá trị literal được SELECT trong EXISTS.

### 7.2. Correlated subquery

Trong:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

`c.customer_id` là cột của truy vấn **bên ngoài**. Subquery tham chiếu đến giá trị tương ứng của hàng đang xét nên gọi là **correlated subquery**.

Về mặt ý nghĩa:

```text
Với mỗi khách hàng c:
   Có bất kỳ đơn hàng o nào có o.customer_id = c.customer_id?
       Có   -> loại khách hàng
       Không -> giữ khách hàng
```

Đây là mô hình khái niệm, **không phải mô tả bắt buộc cách PostgreSQL thực thi từng hàng**. Planner có thể chuyển NOT EXISTS thành anti-join, dùng hash, merge hoặc index tùy kế hoạch.

### 7.3. EXISTS chỉ quan tâm số hàng, không quan tâm giá trị NULL trong SELECT

Ví dụ:

```sql
SELECT
    EXISTS (SELECT NULL::INTEGER) AS exists_null_row,
    NOT EXISTS (SELECT NULL::INTEGER) AS not_exists_null_row,
    EXISTS (SELECT 1 WHERE FALSE) AS exists_empty;
```

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `EXISTS (SELECT NULL::INTEGER)` | TRUE |
| `NOT EXISTS (SELECT NULL::INTEGER)` | FALSE |
| `EXISTS (SELECT 1 WHERE FALSE)` | FALSE |

`SELECT NULL` vẫn trả **một hàng**; giá trị của cột trong hàng là NULL. Vì vậy EXISTS nhận TRUE.

Điều này khác hoàn toàn với việc so sánh một giá trị bằng NULL qua `IN` hoặc `NOT IN`.

---

## 8. Thực hành: khách hàng chưa có đơn hàng nào

Yêu cầu:

> Lấy những khách hàng không có **bất kỳ hàng nào** trong bảng `orders`.

### 8.1. Dùng NOT EXISTS

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 4 | Dũng |
| 7 | Mai |

Bảng đơn hàng có 8 hàng, nhưng điều đó không nói lên có bao nhiêu khách hàng đã đặt: một khách hàng có thể có nhiều đơn, và những khách hàng khác có thể chưa có đơn.

### 8.2. Dùng NOT IN khi khóa không nullable

Trong lab, `orders.customer_id` là NOT NULL và `customers.customer_id` là PRIMARY KEY, nên:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM missing_lab.orders AS o
)
ORDER BY c.customer_id;
```

cho cùng kết quả 4 và 7.

**Lý do truy vấn này phù hợp trong lab:** schema đã bảo đảm rằng subquery không thể trả `NULL` ở `o.customer_id` và cột bên trái cũng không NULL. Nếu sau này đổi nguồn sang staging nullable hoặc dùng biểu thức có thể tạo NULL, phải phân tích lại.

### 8.3. Đừng suy luận “có nhiều order thì có nhiều customer”

`SELECT COUNT(*) FROM orders` là 8, nhưng số lượng khách hàng có đơn khác 8. Nếu cần đếm số khách hàng có đơn:

```sql
SELECT COUNT(DISTINCT customer_id) AS customers_with_orders
FROM missing_lab.orders;
```

Kết quả là 6 (các mã 1, 2, 3, 5, 6, 8). Tám khách hàng trừ sáu khách hàng đã có đơn bằng hai khách hàng không có đơn.

Đây là phép đối soát hợp lý trong dataset nhỏ đã biết. Trên hệ thống lớn, khi cần truy vấn riêng những khách hàng thiếu quan hệ, dùng anti-join thay vì mặc định tìm bằng phép trừ hai số đếm và cố suy ra hàng cụ thể.

---

## 9. LEFT JOIN ... IS NULL: một cách viết anti-join khác

`LEFT JOIN` giữ mọi hàng ở bảng trái; nếu không có hàng tương ứng bên phải, PostgreSQL tạo một **hàng kết quả bên phải chứa NULL**.

Hãy xem:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Với khách hàng 4 và 7 không có đơn, giá trị `o.order_id` sẽ là NULL ở hàng kết quả sau join.

Nếu chỉ cần những khách hàng đó:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả là 4 và 7, giống `NOT EXISTS`.

### 9.1. Tại sao kiểm tra o.order_id IS NULL?

`orders.order_id` là PRIMARY KEY và do đó **không thể NULL ở một đơn hàng thực sự tồn tại**.

Vì vậy, nếu giá trị `o.order_id` bằng NULL **sau LEFT JOIN**, ta có thể kết luận rằng không có hàng `orders` nào khớp điều kiện ON.

Cách này an toàn hơn việc kiểm tra một cột bên phải **cho phép NULL ngay cả khi hàng thực sự tồn tại**.

Ví dụ một bảng order cho phép `coupon_code NULL`. Nếu viết:

```sql
-- Ý tưởng SAI: coupon_code NULL không chứng minh thiếu order.
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.coupon_code IS NULL
```

thì những khách hàng **có đơn nhưng đơn chưa có mã coupon** cũng có thể được giữ. Kiểm tra thiếu quan hệ bằng cột không thể NULL của hàng đã khớp, thường là PRIMARY KEY.

Trong lab, dùng `o.order_id IS NULL` là rõ ràng.

### 9.2. So sánh NOT EXISTS và LEFT JOIN ... IS NULL

| Khía cạnh | NOT EXISTS | LEFT JOIN ... IS NULL |
| --- | --- | --- |
| Diễn đạt trực tiếp “không tồn tại hàng B” | Rất rõ | Cần hiểu outer join |
| Bẫy NULL của danh sách NOT IN | Không gặp bẫy đó | Không gặp bẫy đó |
| Cần chọn cột phía B để kiểm tra NULL | Không | Có; chọn cột non-NULL của hàng khớp |
| Lấy cột bảng B trong kết quả tìm hàng thiếu | Không cần | Bên B sẽ NULL khi thiếu |
| Có thể tối ưu thành anti-join | Có | Có trong những mẫu phù hợp |
| Điều kiện B phải đặt đúng vị trí | Trong subquery | Trong ON để giữ nghĩa outer join |
| Kết quả có trùng hàng A do B có nhiều match không | Không với anti-match | Các hàng A có match bị loại; hàng A không match giữ lại |
| Dễ mở rộng yêu cầu nhiều cột/điều kiện | Có | Có, nhưng lưu ý ON vs WHERE |

**Không có kết luận cố định rằng NOT EXISTS luôn nhanh hơn LEFT JOIN ... IS NULL hoặc ngược lại.** Điều quan trọng trước tiên là cùng diễn đạt đúng ngữ nghĩa, sau đó kiểm tra execution plan và dữ liệu thực tế.

---

## 10. Bẫy ON và WHERE khi kết hợp LEFT JOIN

Đây là một trong những lỗi phổ biến nhất khi tìm “phần thiếu với điều kiện”.

Yêu cầu:

> Tìm khách hàng **chưa có đơn PAID**.

Nếu muốn dùng LEFT JOIN, điều kiện `status = 'PAID'` thuộc về **định nghĩa một hàng bên phải được xem là khớp**, nên nó phải nằm trong `ON`:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả mong đợi:

| customer_id | customer_name | Lý do |
| ---: | --- | --- |
| 2 | Bình | Chỉ có order CANCELED |
| 4 | Dũng | Không có order |
| 6 | Lan | Chỉ có order DRAFT |
| 7 | Mai | Không có order |
| 8 | Nam | Chỉ có order CANCELED |

### 10.1. Cách viết sai thứ nhất: lọc status ở WHERE

```sql
-- SAI cho yêu cầu "khách hàng chưa có đơn PAID".
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
LEFT JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL;
```

Đây là mâu thuẫn trong trường hợp lab: yêu cầu `o.status = 'PAID'` cần có hàng bên phải, còn `o.order_id IS NULL` cần không có hàng bên phải. Kết quả rỗng.

Khi điều kiện trên cột phía phải được đặt trong WHERE, nó có thể **lọc bỏ những hàng NULL-extended** mà outer join vừa tạo, khiến truy vấn không còn giữ được những hàng không khớp.

### 10.2. Cách viết sai thứ hai: WHERE o.status <> 'PAID'

```sql
-- SAI: tìm người có ít nhất một đơn KHÔNG PAID.
SELECT DISTINCT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
JOIN missing_lab.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status <> 'PAID'
ORDER BY c.customer_id;
```

Truy vấn này trả các khách hàng có ít nhất một đơn DRAFT/CANCELED: 1, 2, 6, 8. Nó **sai** cho yêu cầu “không có đơn PAID” vì khách hàng 1 có cả order PAID và DRAFT. Đồng thời khách hàng 4 và 7 không có order nào lại bị bỏ sót.

So sánh hai mệnh đề:

```text
Có ít nhất một order KHÔNG PAID
      EXISTS(order WHERE status <> PAID)

Không tồn tại order PAID
      NOT EXISTS(order WHERE status = PAID)
```

Hai mệnh đề này hoàn toàn khác nhau khi một khách hàng có nhiều order.

### 10.3. Quy tắc nhớ nhanh

Đối với LEFT JOIN tìm không khớp:

1. Đặt **khóa join** và **điều kiện xác định bản ghi B cần tìm** trong `ON`.
2. Đặt điều kiện `right_primary_key IS NULL` ở `WHERE`.
3. Đặt các filter độc lập của bảng A ở `WHERE`.
4. Tránh đưa filter bắt buộc có hàng B sang WHERE nếu mục tiêu là tìm hàng A không có B.

---

## 11. NOT EXISTS với điều kiện nghiệp vụ

NOT EXISTS giúp diễn đạt “không có order PAID” trực tiếp:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả là 2, 4, 6, 7, 8.

### 11.1. Có order nhưng không có order PAID

Nếu cần **chỉ những khách hàng có ít nhất một order nhưng chưa từng có order PAID**, phải kết hợp `EXISTS` và `NOT EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 2 | Bình |
| 6 | Lan |
| 8 | Nam |

Đây là một mẫu quan trọng: **có quan hệ loại X**, nhưng **không có quan hệ loại Y**.

### 11.2. Không có order trong một khoảng thời gian

Giả sử yêu cầu:

> Tìm khách hàng không có đơn hàng **bất kỳ trạng thái nào** trong tháng 03/2026 theo UTC.

Dùng khoảng thời gian nửa mở:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
      AND o.ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
)
ORDER BY c.customer_id;
```

Trong dữ liệu lab, khách hàng 5 có order PAID ngày 01/03; khách hàng 6 có order DRAFT ngày 20/03. Những khách hàng còn lại **không có order trong tháng 03**.

Lý do dùng `< 2026-04-01` thay vì `BETWEEN '2026-03-01' AND '2026-03-31'`: kiểu `TIMESTAMPTZ` có thể chứa giờ, phút, giây và phần lẻ. Mốc 31/03 00:00:00 không bao gồm cả ngày 31/03.

### 11.3. Không có đơn PAID trong tháng 03

Nếu mục tiêu chỉ xét **đơn PAID trong tháng 03**, thêm điều kiện vào subquery:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
      AND o.ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
)
ORDER BY c.customer_id;
```

Kết quả là các mã **1, 2, 3, 4, 6, 7, 8**, vì chỉ khách hàng 5 có đơn PAID trong tháng 03.

Khách hàng 1 và 3 từng có đơn PAID trước tháng 03, nhưng vẫn phù hợp với yêu cầu “không có đơn PAID **trong tháng 03**”.

### 11.4. Điều kiện ở bảng trái

Ví dụ chỉ muốn khách hàng vùng NORTH chưa có order:

```sql
SELECT c.customer_id, c.customer_name, c.region
FROM missing_lab.customers AS c
WHERE c.region = 'NORTH'
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.orders AS o
      WHERE o.customer_id = c.customer_id
  )
ORDER BY c.customer_id;
```

Kết quả là **Mai (7)**. An (1) và Chi (3) thuộc NORTH nhưng đã có order.

Điều kiện `c.region = 'NORTH'` lọc bảng **A**, vì thế có thể đặt ở WHERE ngoài subquery. Điều kiện `o.status = 'PAID'` là điều kiện để xác định một hàng **B được xem là khớp**, vì thế đặt trong NOT EXISTS bên trong.

---

## 12. Tập rỗng và NOT IN: một trường hợp cần hiểu riêng

Nếu subquery **không trả bất kỳ hàng nào**, `NOT IN` trả TRUE cho mọi giá trị bên trái, kể cả NULL.

Ví dụ:

```sql
SELECT
    5 NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS five_not_in_empty,

    NULL::INTEGER NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS null_not_in_empty;
```

Hai kết quả đều TRUE, vì không có phần tử bên phải nào để phản chứng mệnh đề “không thuộc tập”.

Đây là ngoại lệ cần nhớ khi diễn đạt đơn giản rằng “NULL ở bên trái làm NOT IN trở thành UNKNOWN”: **nếu tập bên phải rỗng, kết quả NOT IN là TRUE**.

Tương tự, `NOT EXISTS (subquery trả 0 hàng)` là TRUE.

### 12.1. IN () không hợp lệ

Cú pháp:

```sql
-- KHÔNG HỢP LỆ trong PostgreSQL:
WHERE id IN ()
```

không được PostgreSQL chấp nhận.

Nếu API nhận một danh sách rỗng, có thể:

- Quy định nghiệp vụ rằng danh sách rỗng nghĩa là “không lọc”, “không lấy hàng nào”, hoặc “tất cả không bị loại trừ”; xử lý rõ ở ứng dụng.
- Dùng tham số mảng khi phù hợp:
  `id = ANY('{}'::BIGINT[])` hoặc `id <> ALL('{}'::BIGINT[])`.
- Không tự xây câu SQL bằng cách nối danh sách đầu vào vào chuỗi query.

Với mảng rỗng, `= ANY` thường cho FALSE và `<> ALL` cho TRUE, phù hợp phép tồn tại/tất cả trên tập rỗng. Khi mảng chứa NULL, logic ba giá trị vẫn cần xem xét.

---

## 13. LEFT JOIN, duplicate và ý nghĩa “không có hàng”

Nếu một khách hàng có 10 orders, LEFT JOIN có thể tạo 10 hàng kết quả cho khách hàng đó trước khi lọc. Nhưng khi dùng:

```sql
WHERE o.order_id IS NULL
```

mọi khách hàng có ít nhất một order sẽ bị loại khỏi kết quả tìm thiếu, còn khách hàng không có order được giữ một lần theo hàng bên trái.

Do đó, với bảng A mỗi khóa một hàng, mẫu anti-join đúng không tự tạo duplicate chỉ vì bên B có nhiều order.

Tuy nhiên, nếu **bảng A có duplicate ngay từ đầu** (ví dụ bảng import chứa hai dòng cùng customer_id 99), `NOT EXISTS` sẽ trả **cả hai hàng A** nếu chúng không khớp. Đó là hành vi đúng theo ngữ nghĩa “lấy các hàng thiếu”:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

Kết quả:

| import_ref | customer_id |
| --- | ---: |
| r3 | 99 |
| r5 | 99 |

Hai dòng import khác nhau cùng tham chiếu ID 99. Nếu mục tiêu là **danh sách mã thiếu không trùng**, thêm `DISTINCT`:

```sql
SELECT DISTINCT r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.customer_id;
```

Kết quả chỉ có mã 99.

Đây là khác biệt giữa:

- **Tìm các dòng import lỗi** để sửa từng dòng.
- **Tìm các mã tham chiếu thiếu** để báo cáo danh sách ID.

Không tự thêm DISTINCT vào mọi truy vấn nếu người dùng cần giữ số lần lỗi xuất hiện.

---

## 14. Dữ liệu import có NULL ở phía bên trái

Bảng `imported_order_refs` có:

```text
r1 -> customer_id = 1
r2 -> customer_id = 3
r3 -> customer_id = 99
r4 -> customer_id = NULL
r5 -> customer_id = 99
```

Nếu muốn tìm **dòng import không có khách hàng tương ứng**, viết:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.customers AS c
    WHERE c.customer_id = r.customer_id
)
ORDER BY r.import_ref;
```

Kết quả: **r3, r4, r5**.

Tại sao `r4` (customer_id NULL) được giữ? Vì không có khách hàng nào làm biểu thức `c.customer_id = NULL` trả TRUE, nên subquery không có hàng khớp, dẫn tới NOT EXISTS TRUE.

Điều này **không nhất thiết sai**. Nếu mục tiêu là “dòng import không có liên kết hợp lệ”, cả mã thiếu và mã không tồn tại đều có thể được xem là lỗi. Nhưng nếu mục tiêu là:

> Tìm mã khách hàng **đã được cung cấp**, nhưng không có trong bảng customers,

thì phải tách `NULL`:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

Kết quả chỉ là r3 và r5.

### 14.1. Phân loại hai loại dữ liệu lỗi

```sql
SELECT
    r.import_ref,
    r.customer_id,
    CASE
        WHEN r.customer_id IS NULL
            THEN 'MISSING_CUSTOMER_ID'
        WHEN NOT EXISTS (
            SELECT 1
            FROM missing_lab.customers AS c
            WHERE c.customer_id = r.customer_id
        )
            THEN 'CUSTOMER_NOT_FOUND'
        ELSE 'VALID_REFERENCE'
    END AS validation_status
FROM missing_lab.imported_order_refs AS r
ORDER BY r.import_ref;
```

Kết quả về ý nghĩa:

| import_ref | customer_id | validation_status |
| --- | --- | --- |
| r1 | 1 | VALID_REFERENCE |
| r2 | 3 | VALID_REFERENCE |
| r3 | 99 | CUSTOMER_NOT_FOUND |
| r4 | NULL | MISSING_CUSTOMER_ID |
| r5 | 99 | CUSTOMER_NOT_FOUND |

Đây là cách staging hợp lý: thay vì coi mọi thiếu dữ liệu là một loại lỗi, phân biệt **thiếu giá trị đầu vào** với **giá trị được cung cấp nhưng không tham chiếu được**.

---

## 15. EXCEPT: tìm hiệu của hai tập

PostgreSQL hỗ trợ phép toán tập hợp `EXCEPT`:

```sql
SELECT key FROM table_a
EXCEPT
SELECT key FROM table_b;
```

Ý nghĩa: lấy những giá trị xuất hiện ở tập A nhưng **không xuất hiện ở tập B**, theo quy tắc so sánh của phép toán tập hợp SQL.

### 15.1. Tìm khách hàng chưa có đơn bằng EXCEPT

```sql
SELECT customer_id
FROM missing_lab.customers

EXCEPT

SELECT customer_id
FROM missing_lab.orders;
```

Kết quả gồm **4 và 7**, nhưng **không bảo đảm thứ tự** nếu bạn không đặt ORDER BY cho kết quả cuối.

Có thể viết:

```sql
SELECT missing_id
FROM (
    SELECT customer_id AS missing_id
    FROM missing_lab.customers

    EXCEPT

    SELECT customer_id AS missing_id
    FROM missing_lab.orders
) AS missing
ORDER BY missing_id;
```

Nếu muốn lấy thêm `customer_name`, có thể JOIN kết quả hiệu tập hợp trở lại customers:

```sql
SELECT c.customer_id, c.customer_name
FROM missing_lab.customers AS c
JOIN (
    SELECT customer_id
    FROM missing_lab.customers
    EXCEPT
    SELECT customer_id
    FROM missing_lab.orders
) AS x
  ON x.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Đối với bài toán lấy thông tin khách hàng, `NOT EXISTS` thường ngắn và dễ đọc hơn vì không cần bước JOIN lại như ví dụ.

### 15.2. EXCEPT mặc định loại các dòng trùng

`EXCEPT` thực hiện logic **tập hợp** và thường loại duplicate. Khác với `NOT EXISTS`, nó không tự giữ tất cả dòng A trùng nhau.

Ví dụ:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)

EXCEPT

SELECT id
FROM (VALUES (1)) AS b(id);
```

Kết quả chỉ chứa `2`.

Với `EXCEPT ALL`, số lần xuất hiện được tính theo bội số:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)

EXCEPT ALL

SELECT id
FROM (VALUES (1)) AS b(id);
```

Kết quả có **một hàng 1** và **một hàng 2**, vì bên trái có hai số 1 và bên phải loại một lần xuất hiện. Thứ tự của kết quả chưa được bảo đảm nếu không có ORDER BY ngoài cùng.

### 15.3. EXCEPT so sánh tất cả cột được SELECT

Hai nhánh của `EXCEPT` cần có số cột tương thích, và việc xác định dòng trùng/khác dựa trên **toàn bộ tuple kết quả**, không tự hiểu khóa nghiệp vụ.

Ví dụ:

```sql
SELECT customer_id, customer_name
FROM missing_lab.customers

EXCEPT

SELECT customer_id, status
FROM missing_lab.orders;
```

Truy vấn có thể hợp lệ về kiểu dữ liệu nhưng **sai ý nghĩa**, vì nó so sánh cặp (customer_id, customer_name) với cặp (customer_id, status), không phải “có order cho customer_id hay không”.

Muốn tìm mã thiếu, trước tiên EXCEPT **chỉ trên mã tương ứng**, rồi JOIN lại thông tin khác nếu cần.

---

## 16. EXCEPT và NULL khác NOT EXISTS như thế nào?

Phép toán tập hợp của SQL xử lý các giá trị NULL theo quy tắc loại trùng của set operation. Đối với `EXCEPT`, hai hàng chỉ gồm NULL có thể được xem là cùng một giá trị khi xác định phần chung cần loại.

Thử:

```sql
SELECT id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)

EXCEPT

SELECT id
FROM (VALUES (NULL::INTEGER)) AS b(id);
```

Kết quả chỉ còn **1**, vì NULL ở vế trái được loại khi vế phải có NULL tương ứng trong ngữ nghĩa tập hợp.

Trong khi đó, với NOT EXISTS dùng `=`:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id = a.id
);
```

truy vấn có thể trả cả **1** và **NULL**:

- `1 = NULL` là UNKNOWN → không có match → giữ 1.
- `NULL = NULL` cũng UNKNOWN → không có match → giữ NULL.

Vì thế, **EXCEPT và NOT EXISTS dùng toán tử = không luôn tương đương nếu các khóa nullable**.

### 16.1. Nếu muốn coi hai NULL là khớp nhau

PostgreSQL hỗ trợ toán tử null-safe:

```sql
a IS NOT DISTINCT FROM b
```

Nó trả TRUE khi hai giá trị bằng nhau hoặc **cả hai đều NULL**.

Ví dụ:

```sql
SELECT
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER
        AS nulls_match,
    NULL::INTEGER IS DISTINCT FROM 10
        AS null_differs_from_number,
    5 IS NOT DISTINCT FROM 5
        AS equal_nonnull;
```

Ba biểu thức trả TRUE.

Sửa NOT EXISTS:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id IS NOT DISTINCT FROM a.id
);
```

Kết quả chỉ giữ **1**, vì hàng bên trái có NULL giờ khớp với hàng bên phải có NULL.

**Lưu ý:** Việc coi hai NULL là cùng khóa phải là một **quy tắc nghiệp vụ có chủ đích**. Nhiều hệ thống không nên xem “hai customer_id chưa biết” là cùng một khách hàng. `IS NOT DISTINCT FROM` là công cụ kỹ thuật để thực thi chính sách so sánh, không tự quyết định chính sách.

### 16.2. NULL trong EXCEPT ALL

Với `EXCEPT ALL`, NULL vẫn được tính khi đối trừ số lần xuất hiện của các hàng được xem là không khác biệt theo ngữ nghĩa set operation. Ví dụ nếu bên trái có hai dòng NULL và bên phải một dòng NULL, kết quả `EXCEPT ALL` có thể còn một dòng NULL.

Điều này khác `NOT IN`, nơi một NULL bên phải có thể biến mọi phép kiểm tra “không thuộc” của các khóa không khớp thành UNKNOWN.

---

## 17. So sánh bốn phương pháp tìm phần thiếu

Giả sử `A.key` và `B.key` đều NOT NULL, điều kiện chỉ cần so sánh một khóa.

### Cách 1: NOT EXISTS

```sql
SELECT a.*
FROM missing_lab.customers AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS b
    WHERE b.customer_id = a.customer_id
);
```

Thường là cách diễn đạt trực tiếp nhất cho “không có hàng B”.

### Cách 2: LEFT JOIN ... IS NULL

```sql
SELECT a.*
FROM missing_lab.customers AS a
LEFT JOIN missing_lab.orders AS b
  ON b.customer_id = a.customer_id
WHERE b.order_id IS NULL;
```

Cần kiểm tra một cột bên phải không thể NULL ở hàng có match.

### Cách 3: NOT IN

```sql
SELECT a.*
FROM missing_lab.customers AS a
WHERE a.customer_id NOT IN (
    SELECT b.customer_id
    FROM missing_lab.orders AS b
);
```

Cho cùng kết quả **trong schema lab** vì khóa hai phía không NULL. Nếu B chứa NULL hoặc A nullable, phải phân tích lại.

### Cách 4: EXCEPT

```sql
SELECT customer_id FROM missing_lab.customers
EXCEPT
SELECT customer_id FROM missing_lab.orders;
```

Trả danh sách mã thiếu, mặc định loại trùng và có ngữ nghĩa NULL riêng. Nếu cần lấy toàn bộ cột A, thường phải JOIN lại.

### 17.1. Bảng quyết định nhanh

| Tiêu chí | NOT EXISTS | LEFT JOIN ... IS NULL | NOT IN | EXCEPT |
| --- | --- | --- | --- | --- |
| Diễn đạt “không có hàng tương ứng” | Rõ | Rõ nếu dùng đúng cột kiểm tra | Dễ nhầm với NULL | Rõ cho hiệu tập giá trị |
| Dễ bị một NULL bên phải phá kết quả | Không theo kiểu NOT IN | Không theo kiểu NOT IN | **Có** | Không theo kiểu NOT IN |
| NULL bên trái khớp NULL bên phải theo mặc định | Không với `=` | Không với `=` | Không theo so sánh thường, trừ tập rỗng | Có trong quy tắc set operation |
| Giữ duplicate ở bảng trái | Có | Có đối với những hàng không khớp | Có nếu điều kiện TRUE | Không với EXCEPT mặc định |
| Điều kiện nghiệp vụ ở bảng phải | Trong subquery | Trong `ON` | Trong subquery, chú ý NULL | Trong mỗi nhánh, dễ phức tạp |
| Trả thêm cột bảng trái | Dễ | Dễ | Dễ | Cần lựa chọn tuple phù hợp hoặc JOIN lại |
| Có thể được planner tối ưu hóa | Có | Có | Có, nhưng ngữ nghĩa NULL ảnh hưởng lựa chọn | Có, tùy set operation |
| Lựa chọn bắt đầu cho anti-join | **Thường nên dùng** | Phù hợp | Chỉ khi hiểu NULL | Phù hợp so sánh hai tập |

Đây là bảng **ngữ nghĩa và khả năng biểu đạt**, không phải benchmark khẳng định một cú pháp luôn nhanh nhất.

---

## 18. Khóa ghép: không được chỉ kiểm tra một cột

Trong hệ thống nhiều tenant, mã `external_id` có thể chỉ duy nhất **trong phạm vi tenant**. Khi tìm bản ghi thiếu, cần khớp cả `tenant_id` và `external_id`.

Giả sử dữ liệu:

```text
Source:
tenant_id  external_id
10         500
20         500

Target:
tenant_id  external_id
10         500
```

Nếu chỉ so `external_id = 500`, bạn sẽ kết luận sai rằng bản ghi của tenant 20 đã tồn tại.

### 18.1. NOT EXISTS với khóa ghép

Một mẫu tổng quát:

```sql
SELECT s.tenant_id, s.external_id
FROM source_records AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM target_records AS t
    WHERE t.tenant_id = s.tenant_id
      AND t.external_id = s.external_id
);
```

Đây là cú pháp minh họa; `source_records` và `target_records` không thuộc lab đã tạo.

### 18.2. Row NOT IN có thể phức tạp hơn với NULL

PostgreSQL hỗ trợ so sánh tuple:

```sql
WHERE (s.tenant_id, s.external_id) NOT IN (
    SELECT t.tenant_id, t.external_id
    FROM target_records AS t
)
```

Tuy nhiên, phép so sánh row với các thành phần NULL có quy tắc ba giá trị phức tạp. Một thành phần đã khác nhau có thể đủ để xác định hai tuple không bằng nhau; các thành phần còn lại chứa NULL có thể tạo UNKNOWN nếu không có bằng chứng khác biệt.

Vì vậy, với khóa ghép có thể nullable, ưu tiên viết điều kiện `NOT EXISTS` rõ ràng theo từng cột và quyết định chính sách NULL.

### 18.3. NULL-safe equality cho khóa ghép

Nếu nghiệp vụ **cho phép và muốn** coi NULL ở cả hai phía là tương đương:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM target_records AS t
    WHERE t.tenant_id IS NOT DISTINCT FROM s.tenant_id
      AND t.external_id IS NOT DISTINCT FROM s.external_id
)
```

Nhưng hãy tự hỏi: có nên coi hai giá trị external_id chưa biết là cùng một bản ghi? Trong nhiều hệ thống, câu trả lời là **không**; nên yêu cầu khóa bắt buộc có giá trị hoặc phân loại dữ liệu thiếu riêng.

### 18.4. Ràng buộc ở schema nên phản ánh khóa nghiệp vụ

Khi cặp `(tenant_id, external_id)` là khóa của một đối tượng, nên xem xét:

```sql
UNIQUE (tenant_id, external_id)
```

hoặc khóa chính ghép nếu phù hợp. Constraint giúp ngăn duplicate khi có nhiều transaction cùng ghi, còn NOT EXISTS dùng để **truy vấn phát hiện**. Hai vai trò này không thể thay thế nhau.

---

## 19. Truy vấn phát hiện thiếu tham chiếu và FOREIGN KEY

Một use case quan trọng:

> Trong file import có những mã khách hàng không tồn tại trong bảng chính; làm thế nào tìm chúng trước khi nạp order?

Bảng staging `imported_order_refs` đã được thiết kế để giữ mã không hợp lệ, vì nó **không có foreign key**.

Truy vấn:

```sql
SELECT r.import_ref, r.customer_id
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  )
ORDER BY r.import_ref;
```

cho r3 và r5.

Nhưng khi chuyển dữ liệu vào bảng `orders` có `FOREIGN KEY (customer_id) REFERENCES customers(customer_id)`, database vẫn phải kiểm tra constraint. Dù truy vấn trước đó không tìm thấy lỗi, **dữ liệu có thể thay đổi giữa lúc kiểm tra và lúc ghi**, hoặc file khác có thể được dùng.

### 19.1. Không dùng NOT EXISTS thay FOREIGN KEY

Một câu `NOT EXISTS` phát hiện thiếu liên kết tại **thời điểm truy vấn**. Nó không bảo vệ việc:

- Một hàng customer bị xóa sau khi kiểm tra.
- Hai giao dịch đồng thời sửa dữ liệu.
- Một client khác insert order với customer_id sai.
- Một job import bypass logic kiểm tra ở ứng dụng.

`FOREIGN KEY` được PostgreSQL triển khai để duy trì toàn vẹn quan hệ trước những thao tác ghi/xóa phù hợp và phối hợp với concurrency.

**Vì vậy: NOT EXISTS để báo cáo/kiểm tra; FOREIGN KEY để bảo vệ bất biến tham chiếu.**

### 19.2. Phân biệt “không tồn tại khách hàng” với “không có đơn”

Hai câu:

```sql
-- Tìm mã khách hàng từ file import không tồn tại trong customers.
SELECT r.import_ref
FROM missing_lab.imported_order_refs AS r
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM missing_lab.customers AS c
      WHERE c.customer_id = r.customer_id
  );
```

và:

```sql
-- Tìm khách hàng hợp lệ chưa có order.
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

đều dùng NOT EXISTS, nhưng **bảng A và B đảo vai trò**, nên chúng trả lời hai câu hỏi khác nhau.

Trước khi viết anti-join, luôn xác định tập gốc cần giữ lại là tập nào.

---

## 20. Điều kiện filter và soft delete

Nhiều hệ thống không xóa hàng vật lý, mà đánh dấu `deleted_at` hoặc `is_deleted`. Khi hỏi “không có order”, cần xác định liệu order đã soft-delete có được tính là tồn tại hay không.

Ví dụ giả định bảng `orders` có `deleted_at TIMESTAMPTZ`:

```sql
-- Tìm khách hàng không có order CHƯA bị xóa mềm.
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders_with_soft_delete AS o
    WHERE o.customer_id = c.customer_id
      AND o.deleted_at IS NULL
);
```

`orders_with_soft_delete` là bảng minh họa, chưa được tạo trong lab.

Nếu bỏ `o.deleted_at IS NULL`, một order đã bị đánh dấu xóa vẫn được tính là “có order”. Cả hai cách có thể đúng tùy yêu cầu nghiệp vụ.

Với LEFT JOIN, điều kiện `o.deleted_at IS NULL` cần nằm trong `ON`:

```sql
SELECT c.customer_id
FROM missing_lab.customers AS c
LEFT JOIN orders_with_soft_delete AS o
  ON o.customer_id = c.customer_id
 AND o.deleted_at IS NULL
WHERE o.order_id IS NULL;
```

Nếu chuyển điều kiện này sang WHERE, có thể thay đổi tập khách hàng được giữ và diễn đạt sai “không có order chưa xóa”.

---

## 21. Truy vấn tìm thiếu không mặc nhiên bảo đảm tính nhất quán khi ghi

Giả sử một job thực hiện:

1. Tìm khách hàng chưa có order PAID.
2. Phát ưu đãi cho những người đó.
3. Trong lúc job xử lý, một order PAID mới được tạo.

Kết quả tìm phần thiếu có thể **đúng tại snapshot của truy vấn nhưng không còn đúng khi job phát ưu đãi**.

Ví dụ:

```text
T1: Job A chạy NOT EXISTS -> khách hàng 2 chưa có order PAID
T2: Job B tạo và COMMIT order PAID cho khách hàng 2
T3: Job A phát ưu đãi vì dùng kết quả T1
```

Nếu nghiệp vụ yêu cầu ưu đãi chỉ phát khi không có order PAID tại đúng thời điểm phát, cần thiết kế thêm đồng bộ dữ liệu.

### 21.1. READ COMMITTED và snapshot

Trong PostgreSQL, ở mức cô lập `READ COMMITTED` thông thường, mỗi statement nhìn một snapshot phù hợp tại thời điểm bắt đầu statement. Một kết quả `NOT EXISTS` hợp lệ lúc chạy không phải một bảo đảm “sẽ không có hàng khớp trong tương lai”.

Dùng `REPEATABLE READ` hay `SERIALIZABLE` thay đổi cách transaction quan sát và giải quyết concurrency, nhưng **không tự biến mọi câu SELECT thành ràng buộc nghiệp vụ vĩnh viễn**.

### 21.2. Nếu “mỗi khách hàng chỉ được có một ưu đãi” là bất biến

Hãy tạo unique constraint hoặc unique index phù hợp trên bảng ưu đãi, ví dụ `UNIQUE(customer_id, campaign_id)`, để chống việc phát hai lần cùng chương trình.

Nếu việc phát ưu đãi còn phụ thuộc vào trạng thái order, cần phối hợp:

- Transaction và thời điểm kiểm tra.
- Cơ chế khóa phù hợp khi các writers tương tác.
- Mức cô lập và retry khi gặp `serialization_failure` trong tình huống tương ứng.
- Unique/foreign key và idempotency key.
- Quy tắc nghiệp vụ giải quyết sự kiện order thay đổi sau khi ưu đãi đã phát.

Không dùng `SELECT NOT EXISTS` rồi coi kết quả như một “khóa” chống các giao dịch khác.

### 21.3. Một ngoại lệ quan trọng: NOT EXISTS rồi INSERT khi cạnh tranh

Mẫu:

```sql
INSERT INTO some_table (business_key)
SELECT 'A'
WHERE NOT EXISTS (
    SELECT 1
    FROM some_table
    WHERE business_key = 'A'
);
```

không tự ngăn hai transaction cùng lúc quan sát rằng A chưa tồn tại rồi cùng thử insert A. Nếu muốn bảo đảm duy nhất, cần **unique constraint**, và thường dùng `INSERT ... ON CONFLICT ...` với chính sách phù hợp.

Anti-join tìm dữ liệu thiếu; **constraint xử lý tính duy nhất dưới cạnh tranh**.

---

## 22. Hiệu năng: PostgreSQL có thể thực thi anti-join như thế nào?

Một correlated NOT EXISTS trông như “chạy subquery một lần cho mỗi khách hàng”. Nhưng PostgreSQL optimizer có thể nhận ra nhiều mẫu và chuyển thành các kế hoạch anti-join khác nhau.

Một số dạng có thể xuất hiện trong EXPLAIN:

- **Hash Anti Join**: tạo hash table cho bảng nhỏ hơn/đầu vào thích hợp, rồi tìm những hàng A không khớp.
- **Nested Loop Anti Join**: với mỗi hàng A, tìm B qua index hoặc điều kiện phù hợp; thường hiệu quả nếu tập A nhỏ và index B tốt.
- **Merge Anti Join**: dùng hai tập đã được sắp theo khóa để xác định phần không khớp.
- **SubPlan** hoặc **hashed SubPlan**: có thể gặp ở một số dạng subquery, đặc biệt khi ngữ nghĩa ba giá trị của `NOT IN` cần được bảo toàn.
- **SetOp/HashSetOp/Sort**: các kế hoạch liên quan khi dùng `EXCEPT`.

Không thể đoán chính xác từ mặt chữ SQL. PostgreSQL cân nhắc thống kê, kích thước bảng, index, selectivity, work_mem, kiểu dữ liệu, điều kiện và phiên bản.

### 22.1. Dùng EXPLAIN cho truy vấn tìm thiếu

```sql
EXPLAIN
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Nếu muốn quan sát thực thi trên **SELECT đọc dữ liệu**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

`EXPLAIN ANALYZE` **thực sự chạy câu lệnh**, nên không dùng tùy tiện với DML trên production. Ở đây, truy vấn là SELECT thuần nên phù hợp cho lab.

### 22.2. Index phía bảng được kiểm tra tồn tại

Một index phổ biến:

```sql
CREATE INDEX idx_orders_customer_id
ON missing_lab.orders(customer_id);
```

Index này có thể giúp truy vấn kiểm tra order theo customer_id, đặc biệt với tập khách hàng tương đối nhỏ và bảng orders lớn.

Đối với truy vấn “không có order PAID” thường xuyên:

```sql
CREATE INDEX idx_orders_paid_customer
ON missing_lab.orders(customer_id)
WHERE status = 'PAID';
```

Đây là **partial index** chỉ lưu các order PAID, có thể hữu ích khi số order PAID là một phần nhỏ so với tổng và truy vấn lọc `status = 'PAID'` chính xác.

Những yếu tố cần xem:

- Cột index phù hợp với điều kiện join thực tế.
- Tỷ lệ hàng thỏa status.
- Điều kiện ngày giờ có thường xuyên dùng không.
- Chi phí index khi INSERT/UPDATE order.
- Query planner có dùng index thực sự không.

Với bảng lab chỉ có 8 orders, PostgreSQL hoàn toàn có thể chọn sequential scan vì đơn giản và rẻ hơn. Điều này bình thường.

### 22.3. NOT EXISTS hay LEFT JOIN nhanh hơn?

Không có quy tắc cố định “NOT EXISTS luôn nhanh hơn” hoặc “LEFT JOIN luôn nhanh hơn”. Với những mẫu tương đương về ngữ nghĩa, PostgreSQL có thể lập kế hoạch **cùng kiểu anti-join**.

Quan trọng hơn là:

1. Có đúng điều kiện join không?
2. Predicate của bảng B có được đặt đúng chỗ không?
3. Có cần xử lý NULL khác bình thường không?
4. Có index phù hợp với workload không?
5. Thống kê có đủ cập nhật không?
6. Dữ liệu có quá nhiều duplicate hoặc skew không?
7. Kết quả đã được kiểm tra theo yêu cầu nghiệp vụ chưa?

Tối ưu sai câu hỏi chỉ giúp query sai chạy nhanh hơn.

### 22.4. EXCEPT có thể tốn chi phí loại trùng

Với `EXCEPT` mặc định, PostgreSQL cần thực hiện logic tập hợp và thường phải loại trùng theo kiểu dữ liệu/cấu trúc thực thi. Nếu bạn cần lấy **mọi hàng A không khớp B**, `NOT EXISTS` có thể trực tiếp hơn mà không cần tạo một tập khóa và JOIN lại.

Tuy nhiên, khi nhiệm vụ là **so sánh hai danh sách mã** và mong kết quả không trùng, EXCEPT có ngữ nghĩa rất thích hợp.

### 22.5. NOT IN và kế hoạch thực thi

`NOT IN` cần giữ đúng logic SQL khi subquery chứa NULL. Điều này có thể giới hạn cách biến đổi optimizer so với `NOT EXISTS` trong một số trường hợp, hoặc tạo kế hoạch SubPlan khác.

Nếu cột bên phải có `NOT NULL` từ schema, planner có thể tận dụng thông tin đó theo phiên bản/cấu trúc truy vấn. Nhưng không nên viết truy vấn chỉ vì hy vọng optimizer suy ra tất cả tính chất dữ liệu.

**Ưu tiên ngữ nghĩa rõ ràng, kiểm tra execution plan sau.**

---

## 23. Cách phát hiện “có hàng A nhưng không có B đủ điều kiện” trong báo cáo

Một báo cáo thường cần phân nhóm khách hàng:

- Có PAID.
- Có order nhưng không có PAID.
- Chưa từng có order.

Có thể tạo nhãn bằng các biểu thức EXISTS:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM missing_lab.orders AS o
            WHERE o.customer_id = c.customer_id
              AND o.status = 'PAID'
        )
            THEN 'HAS_PAID_ORDER'

        WHEN EXISTS (
            SELECT 1
            FROM missing_lab.orders AS o
            WHERE o.customer_id = c.customer_id
        )
            THEN 'HAS_ORDER_NO_PAID'

        ELSE 'NO_ORDER'
    END AS customer_order_class
FROM missing_lab.customers AS c
ORDER BY c.customer_id;
```

Kết quả:

| ID | Tên | Phân loại |
| ---: | --- | --- |
| 1 | An | HAS_PAID_ORDER |
| 2 | Bình | HAS_ORDER_NO_PAID |
| 3 | Chi | HAS_PAID_ORDER |
| 4 | Dũng | NO_ORDER |
| 5 | Hà | HAS_PAID_ORDER |
| 6 | Lan | HAS_ORDER_NO_PAID |
| 7 | Mai | NO_ORDER |
| 8 | Nam | HAS_ORDER_NO_PAID |

Cách này minh họa rằng một câu hỏi có thể cần nhiều loại **tồn tại/không tồn tại**. Trật tự các nhánh CASE quan trọng: kiểm tra có PAID trước, rồi mới kiểm tra có order bất kỳ, giúp mỗi khách hàng vào đúng một nhóm.

Khi báo cáo trên bảng lớn, có thể cân nhắc tạo bảng/tập hợp trạng thái đã tổng hợp theo customer_id rồi join một lần, tùy workload và kế hoạch. Không mặc định nhiều EXISTS nghĩa là chạy nhiều lần tốn kém nếu chưa xem execution plan.

---

## 24. Dùng LEFT JOIN để kiểm tra phần thiếu của nhiều quan hệ

Giả sử một quy trình ETL cần phân biệt dữ liệu import đã khớp hay chưa. Ngoài NOT EXISTS, có thể dùng LEFT JOIN với CASE:

```sql
SELECT
    r.import_ref,
    r.customer_id,
    CASE
        WHEN r.customer_id IS NULL
            THEN 'MISSING_CUSTOMER_ID'
        WHEN c.customer_id IS NULL
            THEN 'CUSTOMER_NOT_FOUND'
        ELSE 'VALID_REFERENCE'
    END AS validation_status
FROM missing_lab.imported_order_refs AS r
LEFT JOIN missing_lab.customers AS c
  ON c.customer_id = r.customer_id
ORDER BY r.import_ref;
```

Kết quả phân loại giống ví dụ `CASE + NOT EXISTS` ở mục 14.

Điều kiện `c.customer_id IS NULL` là dấu hiệu không khớp vì `customers.customer_id` là PRIMARY KEY.

### 24.1. Nếu cột bên phải nullable

Khi join theo một cột B nullable và kiểm tra đúng cột đó, hãy tự hỏi:

- Nếu hàng B **thực sự match**, cột đang kiểm tra có chắc non-NULL không?
- Nếu không, kết quả IS NULL có thể là **NULL của dữ liệu**, không phải NULL do outer join tạo ra.
- Có cột PK hoặc ID khác luôn non-NULL ở B không?

Ví dụ tổng quát:

```sql
-- Đúng hơn: kiểm tra B.id NOT NULL từ schema nếu một hàng B match.
SELECT a.*
FROM table_a AS a
LEFT JOIN table_b AS b
  ON b.some_nullable_attribute = a.some_attribute
WHERE b.id IS NULL;
```

Nếu `b.id` là PK non-NULL, đây là dấu hiệu vắng match đáng tin cậy. Nhưng điều kiện `b.some_nullable_attribute = a.some_attribute` có thể vẫn không khớp khi cả hai NULL: chuyện đó thuộc **quy tắc join** và cần giải quyết độc lập.

---

## 25. Phân tích nhanh những lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `NOT IN (subquery)` trả 0 hàng dù có phần thiếu | Subquery chứa NULL | Phân tích ngữ nghĩa; dùng `NOT EXISTS` hoặc loại NULL có chủ đích |
| `NOT EXISTS` trả cả hàng có khóa NULL | Không có match theo `= NULL` | Dùng `IS NOT NULL` nếu mục tiêu chỉ là mã được cung cấp; hoặc `IS NOT DISTINCT FROM` nếu NULL phải match |
| LEFT JOIN ... IS NULL trả hàng A vốn có B | Kiểm tra một cột B nullable | Kiểm tra PK/non-NULL của B |
| LEFT JOIN tìm không có PAID trả rỗng | Đặt `o.status = 'PAID'` ở WHERE cùng `o.id IS NULL` | Đưa status vào ON |
| “Không có PAID” bị lẫn khách hàng có PAID | Dùng `o.status <> 'PAID'` để tìm hàng nonpaid | Dùng `NOT EXISTS` lọc `status = 'PAID'` |
| Khách hàng chưa có order nhưng bị loại | Dùng INNER JOIN hoặc WHERE có điều kiện B không NULL | Dùng anti-join |
| EXCEPT mất duplicate | EXCEPT mặc định loại trùng | Dùng NOT EXISTS cho dòng A hoặc EXCEPT ALL nếu đúng yêu cầu |
| EXCEPT so sánh sai ý nghĩa | SELECT hai cột không đồng nghĩa giữa hai vế | EXCEPT đúng khóa/tuple cần đối chiếu |
| EXCEPT và NOT EXISTS khác nhau với NULL | Set operation và `=` có ngữ nghĩa NULL khác | Định nghĩa chính sách NULL; dùng null-safe equality khi phù hợp |
| Kết quả anti-join đúng trước khi ghi nhưng sau đó trùng | Concurrency; hai transaction cùng thấy thiếu | UNIQUE/FOREIGN KEY, transaction, khóa/idempotency |
| Query tìm thiếu chậm | Bảng B lớn, thiếu index, thống kê chưa phù hợp | EXPLAIN/ANALYZE trên SELECT, index theo join/predicate |
| Dữ liệu tenant khác bị tính là có | Bỏ sót tenant_id trong điều kiện join | Khớp đầy đủ khóa ghép |
| Truy vấn bỏ sót cuối ngày/tháng | Dùng BETWEEN với ngày kết thúc là đầu ngày | Dùng khoảng nửa mở timestamp |
| Danh sách giá trị từ API tạo `IN ()` | Không xử lý mảng rỗng | Bind array hoặc nhánh nghiệp vụ riêng |
| Lọc soft-deleted data sai | Không xác định bản ghi xóa mềm có được tính là tồn tại | Thêm predicate soft-delete vào đúng vị trí |

---

## 26. Bài tập thực hành

### Bài 1 — Dự đoán NOT IN có NULL

Dự đoán kết quả:

```sql
SELECT
    5 NOT IN (1, 2, NULL) AS a,
    2 NOT IN (1, 2, NULL) AS b,
    5 NOT IN (1, 2, 3)    AS c;
```

Giải thích vì sao `a` là UNKNOWN, `b` là FALSE và `c` là TRUE. Kết quả `WHERE a` sẽ giữ hay bỏ hàng?

### Bài 2 — Khách hàng chưa có order

Từ bảng lab, hãy viết:

1. `NOT EXISTS`.
2. `LEFT JOIN ... IS NULL`.
3. `NOT IN` (với schema đã bảo đảm khóa non-NULL).
4. `EXCEPT` chỉ trên customer_id.

Đối chiếu rằng kết quả đều là **4, 7**. Phân tích vì sao các cách này tương đương **trong điều kiện của lab**, không phải với mọi schema nullable.

### Bài 3 — Khách hàng chưa có PAID

Viết câu NOT EXISTS tìm khách hàng chưa có order PAID, dự kiến **2, 4, 6, 7, 8**.

Sau đó thử viết LEFT JOIN với `o.status = 'PAID'` trong `ON`. Tại sao `WHERE o.status <> 'PAID'` không cùng ý nghĩa?

### Bài 4 — Có order nhưng chưa có PAID

Dùng `EXISTS` và `NOT EXISTS` để tìm khách hàng:

- Có ít nhất một order bất kỳ.
- Không có order PAID.

Kết quả dự kiến **2, 6, 8**. Vì sao Dũng và Mai không thuộc tập này?

### Bài 5 — Không có order tháng 03/2026

Lấy những khách hàng chưa có order trong tháng 03/2026 theo UTC, bất kể status.

Viết điều kiện:

```sql
o.ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
AND o.ordered_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'
```

và kết hợp trong NOT EXISTS. Vì sao không nên dùng mốc `'2026-03-31'` làm đầu trên inclusive cho kiểu timestamp?

### Bài 6 — Không có order PAID tháng 03

Viết NOT EXISTS có cả `status = 'PAID'` và khoảng thời gian tháng 03. Tìm lý do vì sao khách hàng 1 và 3 vẫn xuất hiện dù họ đã có order PAID ở thời điểm khác.

### Bài 7 — NOT IN trên exclusion có NULL

Chạy:

```sql
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE c.customer_id NOT IN (
    SELECT customer_id
    FROM missing_lab.customer_exclusions
)
ORDER BY c.customer_id;
```

Giải thích vì sao không trả hàng. Sửa bằng hai cách:

1. Lọc `customer_id IS NOT NULL` trong subquery.
2. Dùng NOT EXISTS.

Đối chiếu kết quả là **1, 3, 4, 5, 7, 8**.

### Bài 8 — Hai loại lỗi import

Với `imported_order_refs`, hãy tách:

- Dòng không có customer_id.
- Dòng có customer_id nhưng không tồn tại trong customers.
- Dòng hợp lệ.

Dự kiến:

```text
r1 -> VALID_REFERENCE
r2 -> VALID_REFERENCE
r3 -> CUSTOMER_NOT_FOUND
r4 -> MISSING_CUSTOMER_ID
r5 -> CUSTOMER_NOT_FOUND
```

Viết một truy vấn dùng `CASE` và `NOT EXISTS`, rồi viết lại bằng `LEFT JOIN`.

### Bài 9 — EXCEPT và trùng hàng

Chạy:

```sql
SELECT id
FROM (VALUES (1), (1), (2)) AS a(id)
EXCEPT
SELECT id
FROM (VALUES (1)) AS b(id);
```

Sau đó thay `EXCEPT` bằng `EXCEPT ALL`. Giải thích khác biệt giữa tập hợp và đa tập, cũng như khi nào cần giữ duplicate của dữ liệu nguồn.

### Bài 10 — NULL và EXCEPT

So sánh hai truy vấn:

```sql
SELECT id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
EXCEPT
SELECT id
FROM (VALUES (NULL::INTEGER)) AS b(id);
```

và:

```sql
SELECT a.id
FROM (VALUES (1::INTEGER), (NULL::INTEGER)) AS a(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (NULL::INTEGER)) AS b(id)
    WHERE b.id = a.id
);
```

Vì sao kết quả khác nhau? Sửa NOT EXISTS bằng `IS NOT DISTINCT FROM` để có chính sách NULL tương ứng với hiệu tập hợp.

### Bài 11 — Khóa ghép nhiều tenant

Hai bảng giả định có cột `tenant_id` và `external_id`. Bên A có cặp `(10,500)` và `(20,500)`; bên B chỉ có `(10,500)`.

Viết NOT EXISTS khớp **hai cột** và giải thích tại sao chỉ so external_id làm sai kết quả. Nếu external_id nullable, có nên xem hai NULL là một khóa trùng nhau không? Đưa ra yêu cầu nghiệp vụ cần quyết định trước.

### Bài 12 — EXPLAIN và index

Xem:

```sql
EXPLAIN
SELECT c.customer_id
FROM missing_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM missing_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Tạo index theo `orders(customer_id)` hoặc partial index cho `status = 'PAID'` như mục 22. Giải thích vì sao PostgreSQL có thể vẫn dùng sequential scan khi bảng chỉ có 8 orders.

### Bài 13 — Kiểm tra concurrency

Hai transaction cùng tìm “chưa có bản ghi khóa nghiệp vụ X” bằng NOT EXISTS, rồi cùng insert.

Trả lời:

1. Vì sao NOT EXISTS không tự ngăn duplicate dưới concurrency?
2. Cơ chế constraint nào nên bảo vệ tính duy nhất?
3. Khi có `ON CONFLICT`, ứng dụng cần xác định chính sách cập nhật/bỏ qua thế nào?
4. Nếu dùng SERIALIZABLE, ứng dụng cần xử lý loại lỗi nào và retry ra sao?

---

## 27. Checklist thiết kế truy vấn tìm phần thiếu

| Câu hỏi | Hướng kiểm tra |
| --- | --- |
| Tập A là gì? | Xác định đúng những hàng cần giữ lại |
| Tập B là gì? | Xác định bảng/quan hệ dùng để kiểm tra tồn tại |
| Thế nào được coi là một hàng B khớp? | Đủ khóa, tenant, status, khoảng thời gian và điều kiện nghiệp vụ |
| Bên phải có thể chứa NULL không? | Đặc biệt tránh `NOT IN` bị UNKNOWN |
| Bên trái có thể chứa NULL không? | Tách thiếu ID với ID không tồn tại hoặc chọn null-safe equality |
| NULL có được coi khớp NULL không? | Cân nhắc `IS NOT DISTINCT FROM` nếu đúng nghiệp vụ |
| Chỉ cần biết có hàng hay không? | Thường chọn `NOT EXISTS` |
| Dùng LEFT JOIN? | Đặt predicate của B trong ON, kiểm tra PK B IS NULL |
| Có nhiều B tương ứng một A không? | Không nhầm “có B không hợp lệ” với “không có B hợp lệ” |
| Cần giữ duplicate ở A không? | NOT EXISTS giữ; EXCEPT mặc định loại trùng |
| Chỉ cần danh sách khóa khác biệt? | EXCEPT hoặc DISTINCT có thể phù hợp |
| Có kiểm tra soft-delete không? | Quy định bản ghi đã xóa mềm có tính là tồn tại không |
| Có lọc thời gian không? | Khoảng nửa mở và timezone rõ ràng |
| Có viết NOT IN với subquery không? | Bảo đảm cả khóa bên trái và tập khóa bên phải xử lý NULL đúng |
| Có muốn đưa dữ liệu thiếu sang bảng đích không? | FOREIGN KEY/UNIQUE và transaction vẫn cần |
| Có thể hai transaction cùng thấy thiếu không? | Cơ chế khóa, constraint, retry và idempotency |
| Query có chậm không? | EXPLAIN, thống kê, index cho điều kiện khớp |
| Có kết quả rỗng bất ngờ không? | Kiểm tra NULL bên phải, ON/WHERE, filter và dữ liệu gốc |
| Có dữ liệu từ API không? | Bind parameter, xử lý danh sách rỗng và giới hạn input |

## Kết luận

Trong PostgreSQL, bài toán “tìm phần thiếu” là bài toán xác định **những hàng ở tập A không có hàng tương ứng ở tập B**. `NOT IN` có thể làm việc đúng khi các giá trị so sánh được bảo đảm không NULL, nhưng khi subquery có một `NULL`, những giá trị không khớp có thể cho kết quả UNKNOWN và bị loại khỏi WHERE. Đây là một trong những bẫy quan trọng nhất của logic ba giá trị SQL.

Các cách tiếp cận cần nhớ:

- **`NOT EXISTS`**: thường là lựa chọn khởi đầu rõ ràng nhất khi muốn kiểm tra không có hàng B khớp điều kiện.
- **`LEFT JOIN ... IS NULL`**: cũng diễn đạt anti-join tốt khi đặt điều kiện khớp ở ON và dùng một cột B chắc chắn non-NULL nếu có hàng.
- **`NOT IN`**: phù hợp khi đã kiểm soát NULL ở cả hai phía, nhưng cần đặc biệt cẩn thận với subquery và danh sách chứa NULL.
- **`EXCEPT`**: phù hợp khi so sánh hiệu của hai tập; mặc định loại duplicate và có ngữ nghĩa riêng với NULL.
- **`IS NOT DISTINCT FROM`**: hỗ trợ so sánh null-safe nếu nghiệp vụ chủ đích coi hai NULL là tương đương.

Một truy vấn đúng còn cần **đúng phạm vi quan hệ**: khóa ghép, tenant, trạng thái, thời gian, soft delete và phân loại dữ liệu thiếu. Khi dùng kết quả để ghi dữ liệu trong môi trường nhiều giao dịch, phải phối hợp `FOREIGN KEY`, `UNIQUE`, transaction, khóa và idempotency theo yêu cầu, vì truy vấn phát hiện thiếu không tự tạo bảo đảm toàn vẹn vĩnh viễn.

Khi phân biệt rõ “không có hàng” với “có hàng nhưng khóa NULL”, chọn đúng toán tử và đúng vị trí điều kiện kết nối, bạn có thể viết các truy vấn đối soát, kiểm tra dữ liệu nhập và báo cáo phần thiếu đáng tin cậy trong PostgreSQL.
