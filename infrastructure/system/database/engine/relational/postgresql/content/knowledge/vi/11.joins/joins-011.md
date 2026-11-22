# Kiểm chứng kết quả join bằng dữ liệu có NULL và quan hệ thiếu trong PostgreSQL

Một truy vấn `JOIN` có thể chạy thành công, không phát sinh lỗi SQL, thậm chí trả ra những dòng trông hợp lý nhưng vẫn **sai về nghiệp vụ**. Điều này thường xảy ra khi dữ liệu không “đẹp” như những ví dụ lý tưởng: khách hàng chưa đặt đơn, đơn hàng chưa gắn khách, bảng nhập liệu chứa mã khách không tồn tại, cột dùng để nối có `NULL`, hoặc một khóa tưởng là duy nhất thực ra khớp nhiều hàng ở bảng bên phải.

Ví dụ, một báo cáo “tất cả khách hàng và số đơn của họ” dùng `INNER JOIN` sẽ **bỏ mất khách chưa mua hàng**. Một báo cáo dùng `LEFT JOIN` nhưng đặt bộ lọc đơn đã thanh toán trong `WHERE` cũng có thể vô tình biến kết quả thành kiểu gần giống `INNER JOIN`. Còn công thức `COUNT(*)` trên kết quả `LEFT JOIN` có thể báo khách chưa có đơn vẫn có “1 đơn”, vì bản thân khách vẫn có một hàng đầu ra với các cột bên phải đều `NULL`.

Vì vậy, kiểm tra `JOIN` không chỉ là xem kết quả có đúng cú pháp hay không. Ta cần tạo **bộ dữ liệu kiểm thử cố ý chứa các tình huống biên**, dự đoán số hàng và tập khóa trước khi chạy, rồi đối chiếu các bất biến của kết quả.

Bài học này hướng dẫn một quy trình kiểm chứng có thể thực hiện trực tiếp trong PostgreSQL, từ `INNER JOIN`, `LEFT/RIGHT/FULL OUTER JOIN` đến `NULL`, `ON` so với `WHERE`, anti-join, dữ liệu mồ côi trong staging, quan hệ một-nhiều và các phép đếm/tổng hợp. Nội dung cũng chỉ ra cách biến những kiểm tra đó thành truy vấn đối soát và bài tập có kết quả kỳ vọng.

## 1. “JOIN đúng” phải trả lời được những câu hỏi nào?

Trước khi đọc một câu SQL, hãy viết ra các yêu cầu:

1. **Đơn vị của một hàng đầu ra là gì?** Một khách hàng, một đơn hàng, hay một cặp khách–đơn?
2. **Bên nào là nguồn cần giữ đủ hàng?** Tất cả khách, tất cả đơn, hay chỉ những cặp có quan hệ?
3. **Khóa nối có thể `NULL` không?** Nếu có, `NULL` nghĩa là “chưa biết”, “không áp dụng” hay một giá trị nghiệp vụ riêng?
4. **Dữ liệu thiếu quan hệ có hợp lệ không?** Một khách chưa có đơn là bình thường; một `customer_id = 999` không tồn tại có thể là lỗi nhập liệu.
5. **Có thể có nhiều hàng khớp một khóa không?** Khách có nhiều đơn là đúng; hai bản ghi vùng giao hàng cùng mã có thể nhân đôi dòng báo cáo.
6. **Bộ lọc phải loại hàng nào?** Lọc hàng bên phải ngay khi nối hay loại cả hàng bên trái khỏi kết quả?
7. **Cần kiểm chứng bằng số hàng, khóa hoặc giá trị tổng hợp nào?**

Đây là điểm xuất phát quan trọng hơn việc học thuộc rằng “INNER là giao nhau, LEFT giữ bên trái”.

### 1.1. Tư duy theo hạt dữ liệu (*grain*)

Xét hai bảng:

```text
customers:  1 hàng / customer_id
orders:     1 hàng / order_id, nhiều hàng có thể cùng customer_id
```

Khi nối theo `customer_id`, một khách có ba đơn tạo ra **ba hàng ghép**. Một bảng tổng hợp mong một hàng cho mỗi khách cần `GROUP BY` hoặc cách tổng hợp khác để quay về grain “khách hàng”.

Nếu không xác định grain trước, bạn có thể dùng `SUM(customers.credit_limit)` sau JOIN và vô tình nhân hạn mức tín dụng của khách lên theo số đơn.

## 2. Dựng bộ dữ liệu kiểm thử có chủ đích

Ta sẽ tạo hai bảng chính và một bảng staging trong schema độc lập. Bộ dữ liệu được thiết kế để bao gồm **đủ các nhóm ca kiểm thử** thay vì chỉ một vài hàng có quan hệ hoàn chỉnh.

### 2.1. Tạo schema

Chỉ chạy trên database hoặc schema thực hành được phép:

```sql
CREATE SCHEMA IF NOT EXISTS join_check;

CREATE TABLE join_check.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    region_code text
);

CREATE TABLE join_check.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint
        REFERENCES join_check.customers(customer_id),
    order_status text NOT NULL
        CHECK (order_status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0)
);

CREATE TABLE join_check.order_imports (
    import_id bigint PRIMARY KEY,
    external_customer_id bigint,
    source_name text NOT NULL
);
```

Chú ý sự khác nhau:

- `join_check.orders.customer_id` **cho phép SQL NULL** nhưng có foreign key khi giá trị khác NULL. Nó hỗ trợ tình huống một đơn đang chờ gắn khách, đồng thời bảo vệ các tham chiếu đã được khai báo.
- `join_check.order_imports.external_customer_id` cố ý **không có foreign key** vì mô phỏng bảng staging nhận dữ liệu chưa được xác minh từ ngoài. Bảng này có thể chứa mã 999 không tồn tại.
- `customers.region_code` cho phép NULL để kiểm tra các phép nối trên thuộc tính tùy chọn, không phải khóa chính.

Nếu dùng `NOT NULL` cho `orders.customer_id`, các hàng đơn chưa gắn khách trong bài sẽ không chèn được; đó có thể là một thiết kế phù hợp với nghiệp vụ khác, nhưng sẽ làm mất trường hợp cần kiểm chứng ở đây.

### 2.2. Chèn khách hàng

```sql
INSERT INTO join_check.customers
    (customer_id, customer_name, region_code)
VALUES
    (1, 'An',   'Bac'),
    (2, 'Binh', NULL),
    (3, 'Chi',  'Nam'),
    (4, 'Dung', 'Trung'),
    (5, 'Ha',   'Nam'),
    (6, 'Lan',  NULL);
```

### 2.3. Chèn đơn hàng

```sql
INSERT INTO join_check.orders
    (order_id, customer_id, order_status, amount)
VALUES
    (101, 1,    'paid',      120000.00),
    (102, 1,    'pending',    50000.00),
    (103, 2,    'paid',       90000.00),
    (104, 3,    'cancelled',  30000.00),
    (105, NULL, 'pending',    40000.00),
    (106, 3,    'paid',       20000.00),
    (107, 5,    'paid',       70000.00),
    (108, NULL, 'cancelled',  10000.00);
```

### 2.4. Chèn dữ liệu nhập chưa xác minh

```sql
INSERT INTO join_check.order_imports
    (import_id, external_customer_id, source_name)
VALUES
    (201, 1,    'batch-A'),
    (202, 999,  'batch-A'),
    (203, NULL, 'batch-B'),
    (204, 4,    'batch-B');
```

Nếu chạy lại các câu `INSERT` trên cùng dữ liệu, các khóa chính có thể báo trùng. Nên khởi tạo một schema lab mới, hoặc xóa dữ liệu theo quy trình an toàn trước khi chạy lại; không dùng `DROP SCHEMA ... CASCADE` tùy tiện trong database đang có đối tượng thật.

### 2.5. Sơ đồ quan hệ

```text
customers                       orders
---------                       ------
1 An    ----------------------> 101, 102
2 Binh  ----------------------> 103
3 Chi   ----------------------> 104, 106
4 Dung  ----------------------> (không có đơn)
5 Ha    ----------------------> 107
6 Lan   ----------------------> (không có đơn)

                                 105 -> customer_id NULL
                                 108 -> customer_id NULL

order_imports (staging, KHÔNG có FK)
  201 -> 1        (khớp khách)
  202 -> 999      (mã khách không tồn tại: orphan)
  203 -> NULL     (chưa có mã)
  204 -> 4        (khớp khách)
```

### 2.6. Dự đoán số lượng trước khi chạy JOIN

| Đặc điểm | Số lượng | Định danh |
| --- | ---: | --- |
| Tổng khách hàng | 6 | 1, 2, 3, 4, 5, 6 |
| Tổng đơn hàng | 8 | 101–108 |
| Đơn có khách hợp lệ | 6 | 101, 102, 103, 104, 106, 107 |
| Đơn có `customer_id IS NULL` | 2 | 105, 108 |
| Khách có ít nhất một đơn | 4 | 1, 2, 3, 5 |
| Khách chưa có đơn | 2 | 4, 6 |
| Staging có mã khách không tồn tại | 1 | import 202, customer 999 |
| Staging có mã khách NULL | 1 | import 203 |

Những con số này là **oracle kiểm thử** của bài: khi một truy vấn bất ngờ trả 7, 9 hoặc 12 hàng, hãy lý giải chính xác vì sao thay vì thêm `DISTINCT` cho đến khi kết quả trông đẹp.

## 3. INNER JOIN: chỉ giữ những cặp khớp điều kiện

`INNER JOIN` chỉ tạo hàng đầu ra khi có cặp hàng bên trái và bên phải làm điều kiện `ON` nhận giá trị TRUE.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM join_check.customers AS c
INNER JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Kết quả kỳ vọng:

| customer_id | customer_name | order_id | order_status | amount |
| ---: | --- | ---: | --- | ---: |
| 1 | An | 101 | paid | 120000 |
| 1 | An | 102 | pending | 50000 |
| 2 | Binh | 103 | paid | 90000 |
| 3 | Chi | 104 | cancelled | 30000 |
| 3 | Chi | 106 | paid | 20000 |
| 5 | Ha | 107 | paid | 70000 |

Kết quả có **6 hàng**, không phải 4 hàng, vì mỗi đơn hàng khớp một khách, nhưng một khách có thể xuất hiện nhiều lần.

Hai nhóm dữ liệu biến mất khỏi kết quả:

- Khách 4 và 6 vì **không có đơn**.
- Đơn 105 và 108 vì `customer_id` là NULL và không thể khớp với khóa chính khách hàng bằng phép so sánh `=`.

### 3.1. Kiểm tra tập khóa thay vì chỉ đếm hàng

```sql
SELECT
    array_agg(o.order_id ORDER BY o.order_id) AS matched_order_ids
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

Kết quả kỳ vọng:

```text
{101,102,103,104,106,107}
```

Đếm 6 hàng là cần thiết nhưng chưa đủ: một truy vấn sai có thể trả 6 hàng với **sai ID**. Tập khóa hoặc cặp khóa là bằng chứng mạnh hơn khi kiểm tra logic JOIN.

### 3.2. Không có FROM cột bên phải thì JOIN vẫn có thể đổi số hàng

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Mặc dù select list chỉ lấy cột từ `c`, kết quả vẫn lặp khách 1 và 3 vì họ có hai đơn. **Danh sách cột SELECT không quyết định cardinality của JOIN.**

Nếu muốn mỗi khách có đơn xuất hiện một lần, dùng `EXISTS` hoặc cách tổng hợp phù hợp với nhu cầu, không mặc nhiên thay bằng `SELECT DISTINCT c.*` mà chưa xác định logic.

## 4. LEFT JOIN: giữ mọi hàng bên trái

Khi muốn hiển thị **toàn bộ khách hàng, kể cả khách chưa có đơn**, đặt khách ở bên trái:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id | amount |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 120000 |
| 1 | An | 102 | 50000 |
| 2 | Binh | 103 | 90000 |
| 3 | Chi | 104 | 30000 |
| 3 | Chi | 106 | 20000 |
| 4 | Dung | NULL | NULL |
| 5 | Ha | 107 | 70000 |
| 6 | Lan | NULL | NULL |

Có **8 hàng**: 6 cặp khớp cộng 2 khách không khớp. Ở hai khách không có đơn, PostgreSQL tạo **một hàng mở rộng với các cột của bên phải là SQL NULL**.

Không có bản ghi `orders.order_id = NULL` thực sự được lưu cho khách 4 hoặc 6. Các giá trị NULL đó xuất hiện **chỉ ở đầu ra của outer join**.

### 4.1. Đổi bên trái làm đổi ý nghĩa

Để giữ **tất cả đơn hàng**, kể cả đơn chưa có `customer_id`:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    o.amount
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Truy vấn có **8 hàng**; đơn 105 và 108 vẫn có mặt với `customer_name = NULL`, còn khách 4 và 6 không xuất hiện vì không có đơn để tạo hàng đầu ra.

Hai truy vấn `LEFT JOIN` đều trả 8 hàng trong bộ dữ liệu này, nhưng **hai tập kết quả không giống nhau**. Do đó chỉ so sánh `COUNT(*)` là cách kiểm chứng không đủ.

### 4.2. Những quy tắc cần nhớ

- `LEFT JOIN` bảo toàn **mỗi hàng bên trái ít nhất một lần** khi chưa có lọc ở ngoài; nếu có nhiều cặp khớp, một hàng bên trái có thể xuất hiện nhiều lần.
- Một hàng bên phải không có đối tác ở bên trái **không tự xuất hiện**.
- Cột bên phải là NULL trong hàng outer join **không nhất thiết có nghĩa dữ liệu gốc chứa NULL**; đó có thể là hàng NULL được tạo vì thiếu đối tác.
- Khi viết `WHERE`, bạn có thể loại những hàng được bảo toàn — cần kiểm tra ở phần tiếp theo.

## 5. RIGHT JOIN: giữ mọi hàng bên phải

`RIGHT JOIN` bảo toàn các hàng của nguồn bên phải:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.customers AS c
RIGHT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Trong ví dụ, truy vấn trên tương đương về ý nghĩa dữ liệu với:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Cả hai giữ 8 đơn, gồm 105 và 108 không có khách.

Không có quy tắc nào nói `RIGHT JOIN` là sai; tuy nhiên, trong nhiều truy vấn người đọc thường thấy `LEFT JOIN` với bảng cần giữ nằm bên trái dễ hiểu hơn. Quan trọng là **hướng bảo toàn hàng**, không phải sở thích cú pháp.

## 6. FULL OUTER JOIN: giữ hàng không khớp từ cả hai phía

`FULL OUTER JOIN` tạo cặp hàng khi khớp; khi không khớp, nó vẫn giữ hàng của cả bên trái và bên phải bằng cách điền NULL cho phía còn thiếu.

```sql
SELECT
    c.customer_id AS customer_row_id,
    c.customer_name,
    o.order_id,
    o.customer_id AS order_customer_id
FROM join_check.customers AS c
FULL OUTER JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id NULLS LAST,
    o.order_id NULLS LAST;
```

Dự đoán:

```text
6 cặp khớp
+ 2 khách không có đơn (4, 6)
+ 2 đơn chưa có khách (105, 108)
= 10 hàng
```

Trong đầu ra:

- Khách 4 và 6 có `customer_row_id` nhưng `order_id = NULL`.
- Đơn 105 và 108 có `order_id` nhưng `customer_row_id = NULL`.
- Hai nhóm này đều được bảo toàn, không phải là các cặp hàng nối với nhau.

### 6.1. Tách các hàng không khớp ở mỗi phía

```sql
SELECT
    c.customer_id AS customer_row_id,
    o.order_id,
    o.customer_id AS order_customer_id,
    CASE
        WHEN c.customer_id IS NULL
            THEN 'order_without_matched_customer'
        WHEN o.order_id IS NULL
            THEN 'customer_without_order'
        ELSE 'matched'
    END AS join_class
FROM join_check.customers AS c
FULL JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY join_class, c.customer_id, o.order_id;
```

Ở ví dụ này, `c.customer_id` và `o.order_id` đều là primary key `NOT NULL` trong bảng gốc. Vì vậy, khi chúng thành NULL ở kết quả outer join, ta có thể dùng chúng như **dấu hiệu vắng hàng tương ứng**.

Nếu bạn dùng một cột bên phải **có thể NULL tự nhiên** để kiểm tra “có hàng bên phải hay không”, kết luận có thể sai. Hãy chọn cột `NOT NULL` đáng tin, thường là primary key, hoặc một cờ hiện diện rõ ràng.

### 6.2. Tránh dùng COALESCE làm mất nguồn gốc khi debug

Trong báo cáo đôi khi ta gộp khóa:

```sql
SELECT
    COALESCE(c.customer_id, o.customer_id) AS displayed_customer_id,
    o.order_id
FROM join_check.customers AS c
FULL JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

Điều đó có thể tiện cho trình bày, nhưng khi kiểm tra lỗi, nên giữ **hai cột khóa gốc**. Một giá trị hiển thị sau `COALESCE` có thể che mất thông tin hàng đến từ bên nào, đặc biệt khi dữ liệu staging có mã khách không hợp lệ.

## 7. NULL trong điều kiện ON: không giống một giá trị thông thường

SQL sử dụng logic ba trạng thái: `TRUE`, `FALSE` và `UNKNOWN`.

```sql
SELECT
    NULL::bigint = NULL::bigint AS equality_of_nulls,
    NULL::bigint IS NULL AS left_is_null,
    NULL::bigint IS NOT DISTINCT FROM NULL::bigint
        AS null_safe_equality;
```

Kết quả về ý nghĩa:

| Biểu thức | Kết quả |
| --- | --- |
| `NULL = NULL` | SQL NULL / UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT DISTINCT FROM NULL` | TRUE |

Điều kiện `JOIN ... ON a = b` chỉ coi một cặp hàng là khớp khi phép so sánh là **TRUE**. Nếu một hoặc hai vế là NULL, `a = b` không cho TRUE; cặp đó không khớp.

### 7.1. Vì sao đơn 105 không nối với một “khách NULL”?

Trong bài, `orders.customer_id` có NULL ở đơn 105 và 108, còn `customers.customer_id` là khóa chính không thể NULL. Nhưng ngay cả khi một bảng khác cho phép khóa nối nullable ở **cả hai phía**, biểu thức `a.key = b.key` cũng không tự coi hai giá trị NULL là bằng nhau.

Đây là điểm khác giữa suy nghĩ “cả hai đều không có mã, vậy là giống nhau” với ngữ nghĩa SQL. Hai mã chưa biết **không có bằng chứng là cùng một thực thể**.

### 7.2. NULL của dữ liệu gốc khác NULL do outer join tạo

Với:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_id AS matched_customer_id
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Ở đơn 105:

- `o.customer_id IS NULL` vì cột trong **hàng orders gốc** đang chưa có mã.
- `c.customer_id IS NULL` vì **không có hàng customers khớp** và outer join tạo giá trị NULL cho phía phải.

Hai cột cùng NULL nhưng xuất phát từ hai nguyên nhân khác nhau. Khi kiểm tra chất lượng dữ liệu, đừng gộp nguyên nhân thành một nhãn duy nhất.

## 8. Phân biệt khách không có đơn với đơn không có khách

Đây là hai yêu cầu nghiệp vụ ngược hướng.

### 8.1. Tìm khách chưa từng có đơn

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả đúng là khách **4 và 6**. Ở đây `o.order_id` là khóa chính không cho NULL nên kiểm tra `IS NULL` chỉ ra hàng khách không có đối tác ở `orders`.

### 8.2. Tìm đơn chưa gắn khách

```sql
SELECT
    order_id,
    order_status,
    amount
FROM join_check.orders
WHERE customer_id IS NULL
ORDER BY order_id;
```

Kết quả đúng là đơn **105 và 108**.

Không cần JOIN để nhận diện trường hợp này: giá trị chưa gắn nằm ngay trong cột của `orders`. Dùng JOIN chỉ khi bạn cần phân biệt thêm những nguyên nhân khác, chẳng hạn mã khách có nhưng không tồn tại ở bảng cha.

### 8.3. Hai câu trả lời không thể hoán đổi

“Khách hàng không có đơn” lấy khách làm đối tượng cần kiểm tra. “Đơn hàng không có khách” lấy đơn làm đối tượng. Một truy vấn có đúng số hàng nhưng đảo vai trò hai phía vẫn sai mục tiêu.

## 9. Quan hệ thiếu khi có và không có FOREIGN KEY

Một câu hỏi quan trọng: nếu `orders.customer_id` tham chiếu `customers.customer_id` bằng foreign key, sao đơn vẫn có thể không nối được với khách?

Vì trong ví dụ, cột foreign key **được phép NULL**. PostgreSQL theo cơ chế `MATCH SIMPLE` thông thường không yêu cầu xác minh một tham chiếu đơn cột khi giá trị foreign key là NULL.

```sql
-- Hợp lệ trong schema lab vì customer_id nullable:
INSERT INTO join_check.orders (
    order_id, customer_id, order_status, amount
)
VALUES (109, NULL, 'pending', 1000.00);
```

Lệnh trên là ví dụ riêng, **không chạy nếu muốn giữ nguyên số đếm của bộ dữ liệu 8 đơn**. Nếu đã chạy, những kết quả kỳ vọng trong các phần khác cần được cập nhật vì bảng có thêm đơn 109.

### 9.1. Mã không tồn tại sẽ bị FK chặn

```sql
-- Minh họa câu không nên chạy trong lab dùng số liệu cố định:
-- INSERT INTO join_check.orders
--     (order_id, customer_id, order_status, amount)
-- VALUES (110, 999, 'paid', 1000.00);
```

Nếu `customer_id = 999` không tồn tại, foreign key thông thường sẽ từ chối hàng đó. Vì vậy, với một bảng đã có foreign key hợp lệ và được PostgreSQL thực thi, dữ liệu “khóa có giá trị nhưng không tìm thấy cha” không nên xuất hiện trong trạng thái đã commit bình thường.

Các ngoại lệ vận hành cần xem xét khi điều tra thực tế bao gồm dữ liệu cũ trước khi constraint được xác thực, constraint tạm thời trì hoãn theo transaction, hoặc đường nhập dữ liệu được vận hành thiếu an toàn. Không nên vô hiệu hóa ràng buộc trên production chỉ để tái hiện một orphan trong bài học.

### 9.2. Dữ liệu staging không có FK có thể chứa orphan

`join_check.order_imports` là bảng staging cố ý không ràng buộc foreign key. Tìm bản ghi có **mã khách khác NULL nhưng không tồn tại**:

```sql
SELECT
    i.import_id,
    i.external_customer_id,
    i.source_name
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
WHERE i.external_customer_id IS NOT NULL
  AND c.customer_id IS NULL
ORDER BY i.import_id;
```

Kết quả chỉ có:

| import_id | external_customer_id | source_name |
| ---: | ---: | --- |
| 202 | 999 | batch-A |

Hai điều kiện `IS NOT NULL` và `IS NULL` phục vụ **hai nhiệm vụ khác nhau**:

- `i.external_customer_id IS NOT NULL`: người gửi đã cung cấp mã khách.
- `c.customer_id IS NULL`: PostgreSQL không tìm được hàng khách khớp mã đó.

Nếu bỏ điều kiện đầu, import 203 có `external_customer_id = NULL` cũng xuất hiện trong danh sách, khiến hai loại lỗi bị trộn lẫn.

### 9.3. Phân loại staging thành ba nhóm

```sql
SELECT
    i.import_id,
    i.external_customer_id,
    CASE
        WHEN i.external_customer_id IS NULL
            THEN 'missing_customer_id'
        WHEN c.customer_id IS NULL
            THEN 'unknown_customer_id'
        ELSE 'valid_customer_id'
    END AS data_quality_class
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
ORDER BY i.import_id;
```

Kỳ vọng:

| import_id | external_customer_id | data_quality_class |
| ---: | ---: | --- |
| 201 | 1 | valid_customer_id |
| 202 | 999 | unknown_customer_id |
| 203 | NULL | missing_customer_id |
| 204 | 4 | valid_customer_id |

Đây là cách chuyển kết quả JOIN thành **thông tin để xử lý dữ liệu nhập**: chưa có mã khác với mã đã cho nhưng không hợp lệ.

## 10. ON và WHERE trong OUTER JOIN: nguồn lỗi phổ biến nhất

Một truy vấn `LEFT JOIN` thường bị “mất” các hàng không khớp khi đưa điều kiện của bên phải vào `WHERE`.

### 10.1. Điều kiện đặt trong WHERE

Yêu cầu: “Tìm các khách hàng có đơn đã thanh toán.”

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id;
```

Kết quả gồm các đơn paid **101, 103, 106, 107**; có 4 hàng. Khách 4 và 6 bị loại, vì ở hàng outer join của họ, `o.order_status` là NULL và điều kiện `NULL = 'paid'` là UNKNOWN, không phải TRUE.

Ngay cả khách có đơn nhưng chỉ có đơn chưa thanh toán cũng sẽ bị loại. Vì vậy kết quả này thể hiện **khách có ít nhất một đơn paid**, không phải “mọi khách và đơn paid nếu có”.

### 10.2. Điều kiện đặt trong ON

Yêu cầu khác: “Hiển thị **mọi khách hàng**, gắn đơn paid của họ nếu có.”

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả có **6 hàng**, một hàng cho mỗi khách trong bộ dữ liệu này:

| customer_id | customer_name | order_id | order_status |
| ---: | --- | ---: | --- |
| 1 | An | 101 | paid |
| 2 | Binh | 103 | paid |
| 3 | Chi | 106 | paid |
| 4 | Dung | NULL | NULL |
| 5 | Ha | 107 | paid |
| 6 | Lan | NULL | NULL |

Ở đây:

- `ON` quy định **những dòng bên phải được coi là đối tác phù hợp**.
- Nếu không có đơn paid khớp, hàng khách vẫn được giữ, cột đơn là NULL.
- Dữ liệu minh họa chỉ có một đơn paid mỗi khách; trong hệ thống thực, một khách có nhiều đơn paid vẫn có thể tạo nhiều hàng.

**Không có quy tắc rằng đưa mọi điều kiện từ `WHERE` sang `ON` luôn giữ nguyên kết quả.** Trong outer join, thay vị trí điều kiện có thể thay đổi chính ý nghĩa nghiệp vụ.

### 10.3. So sánh trực tiếp

| Điều kiện | Số hàng | Ý nghĩa |
| --- | ---: | --- |
| `LEFT JOIN ... ON key; WHERE o.order_status = 'paid'` | 4 | Chỉ khách có ít nhất một đơn paid và những đơn paid đó. |
| `LEFT JOIN ... ON key AND o.order_status = 'paid'` | 6 | Mọi khách; hiển thị đơn paid nếu có. |
| `INNER JOIN ... ON key AND o.order_status = 'paid'` | 4 | Chỉ những cặp khách–đơn paid khớp. |

Một câu SQL có từ `LEFT JOIN` **không bảo đảm hàng bên trái còn tồn tại sau khi áp dụng WHERE**.

## 11. WHERE chứa điều kiện IS NULL: đọc đúng ngữ nghĩa

Giả sử cần tìm “khách chưa có đơn paid”, **kể cả khách có đơn pending/cancelled**. Viết:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Trong dữ liệu hiện tại, khách 4 và 6 chưa có đơn nào; không có khách chỉ có đơn pending/cancelled trong tập 6 khách. Kết quả là **4, 6**.

Nhưng hai yêu cầu:

- “Khách **không có đơn**.”
- “Khách **không có đơn paid**.”

không tương đương về mặt tổng quát. Chỉ cần thêm một khách có đơn pending nhưng không có paid, truy vấn thứ hai sẽ bao gồm họ, còn truy vấn thứ nhất thì không.

### 11.1. Vì sao không viết WHERE o.order_status <> 'paid'?

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status <> 'paid';
```

Câu trên tìm **các cặp khách–đơn không paid**. Nó không tìm “khách không có đơn paid”, bởi một khách vừa có đơn paid vừa có đơn pending vẫn xuất hiện theo đơn pending.

Trong ví dụ, khách 1 có đơn pending 102 nên vẫn có mặt, dù họ **đã có đơn paid 101**. Hãy sử dụng anti-join hoặc `NOT EXISTS` để kiểm tra sự vắng mặt của **mọi** đơn paid, thay vì chỉ kiểm tra có ít nhất một đơn không paid.

## 12. Anti-join: tìm những gì KHÔNG có quan hệ

Anti-join là cách truy vấn “những hàng ở bên trái không có hàng phù hợp ở bên phải”.

### 12.1. LEFT JOIN ... IS NULL

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả: khách 4 và 6.

### 12.2. NOT EXISTS

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả cũng là 4 và 6.

`NOT EXISTS` trực tiếp biểu đạt ý định “không tồn tại một hàng đơn khớp”. Nó thường dễ kiểm tra hơn khi query bên phải có nhiều điều kiện hoặc khi bạn không cần trả bất cứ cột nào từ bảng bên phải.

### 12.3. NOT EXISTS có thể an toàn hơn NOT IN khi có NULL

Một cái bẫy rất phổ biến:

```sql
SELECT
    customer_id,
    customer_name
FROM join_check.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM join_check.orders
)
ORDER BY customer_id;
```

Trong bộ dữ liệu, subquery trả cả `NULL` vì các đơn 105 và 108 chưa gắn khách. Với một `customer_id` không xuất hiện trong các giá trị khác NULL, điều kiện `NOT IN (..., NULL)` có thể cho kết quả UNKNOWN và không được `WHERE` giữ lại. Kết quả ở đây là **không có hàng nào**, dù khách 4 và 6 thực sự chưa có đơn.

Nếu vẫn muốn dùng `NOT IN` với một cột khóa bên trái `NOT NULL`, cần loại NULL ở nguồn so sánh:

```sql
SELECT customer_id, customer_name
FROM join_check.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM join_check.orders
    WHERE customer_id IS NOT NULL
)
ORDER BY customer_id;
```

Câu này trả 4 và 6. Nhưng cho bài toán quan hệ thiếu, `NOT EXISTS` thường biểu đạt ý định rõ hơn và tránh lỗi do NULL trong tập con.

### 12.4. NOT EXISTS với điều kiện nghiệp vụ

“Khách không có **bất kỳ** đơn paid nào”:

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'paid'
)
ORDER BY c.customer_id;
```

Trong bộ dữ liệu hiện tại, kết quả 4 và 6. Nếu về sau thêm khách 7 chỉ có đơn pending, họ cũng thuộc tập không có đơn paid dù có đơn.

## 13. EXISTS và vì sao JOIN có thể nhân hàng

“Lấy các khách có ít nhất một đơn” có thể viết:

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả có **4 khách**: 1, 2, 3, 5; mỗi khách một hàng.

Trong khi đó:

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

trả **6 hàng**, vì An và Chi mỗi người có hai đơn.

Nếu chỉ muốn kiểm tra tồn tại, `EXISTS` tránh việc tạo nhiều hàng ghép rồi phải loại trùng. PostgreSQL optimizer có thể sử dụng chiến lược semi-join phù hợp; hiệu năng thực tế vẫn phải đo trên dữ liệu thật.

**Không dùng `SELECT DISTINCT` như phản xạ đầu tiên để chữa hiện tượng nhân hàng**. Trước hết hãy xác nhận grain: mỗi khách, mỗi đơn, hay mỗi cặp.

## 14. COUNT(*) và COUNT(bên phải) sau LEFT JOIN

Một trong những lỗi báo cáo khó thấy nhất xảy ra ở phép đếm:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS rows_after_join,
    COUNT(o.order_id) AS actual_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | rows_after_join | actual_orders |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 2 |
| 2 | Binh | 1 | 1 |
| 3 | Chi | 2 | 2 |
| 4 | Dung | 1 | 0 |
| 5 | Ha | 1 | 1 |
| 6 | Lan | 1 | 0 |

Tại sao khách 4 có `rows_after_join = 1`?

Vì outer join giữ **một hàng khách** dù không có đơn; `COUNT(*)` đếm hàng kết quả ấy. Trong khi đó `COUNT(o.order_id)` chỉ đếm giá trị `o.order_id` **khác NULL**, nên đúng là 0 với khách không có đơn.

**Quy tắc quan trọng:** khi đếm số hàng khớp bên phải của một outer join, dùng một **cột định danh bên phải bảo đảm NOT NULL** và đếm cột đó, thay vì mặc nhiên dùng `COUNT(*)`.

### 14.1. COUNT(cột nullable) cũng có thể gây thiếu

Nếu `orders.note` được phép NULL, `COUNT(o.note)` sẽ không đếm các đơn không có ghi chú. Muốn đếm **đơn**, nên `COUNT(o.order_id)` vì `order_id` là khóa chính không NULL.

Phải trả lời: “Tôi muốn đếm **hàng có quan hệ**, hay muốn đếm **giá trị được khai báo**?” Hai yêu cầu không tương đương.

### 14.2. Tổng giá trị với SUM

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.amount), 0) AS total_order_amount
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kỳ vọng:

| customer_id | total_order_amount |
| ---: | ---: |
| 1 | 170000.00 |
| 2 | 90000.00 |
| 3 | 50000.00 |
| 4 | 0 |
| 5 | 70000.00 |
| 6 | 0 |

`SUM` bỏ qua các giá trị NULL. Với nhóm không có giá trị số cần cộng, `SUM` trả NULL; `COALESCE(..., 0)` biến kết quả thành 0 **nếu nghiệp vụ cho phép xem không có đơn là tổng bằng 0**.

Không nên gộp “không có dữ liệu để cộng” và “giá trị thực sự bằng 0” nếu báo cáo cần phân biệt hai trường hợp đó.

## 15. Tổng hợp có điều kiện mà không đánh mất khách

Đếm số đơn paid trên mỗi khách, bao gồm cả khách có 0 đơn paid:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'pending'
    ) AS pending_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | paid_orders | pending_orders |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 1 | 0 |
| 3 | 1 | 0 |
| 4 | 0 | 0 |
| 5 | 1 | 0 |
| 6 | 0 | 0 |

`FILTER (WHERE ...)` áp dụng điều kiện cho **một phép tổng hợp cụ thể**, không loại toàn bộ khách khỏi kết quả trước khi nhóm.

Một cách khác là đẩy điều kiện vào `ON`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Cả hai cách đều hợp lý để đếm đơn paid, nhưng `FILTER` thuận tiện khi cần nhiều chỉ số có điều kiện khác nhau trong cùng một phép JOIN.

## 16. Kiểm tra số hàng và tính bảo toàn bằng công thức

Với quan hệ một-nhiều `customers (1) → orders (n)` trong bộ dữ liệu hiện tại:

```text
INNER JOIN:
  6 hàng orders có customer_id hợp lệ
  = 6 hàng ghép

customers LEFT JOIN orders:
  6 hàng ghép
  + 2 khách không có đơn
  = 8 hàng

orders LEFT JOIN customers:
  6 hàng ghép
  + 2 đơn không có khách
  = 8 hàng

FULL OUTER JOIN:
  6 hàng ghép
  + 2 khách không có đơn
  + 2 đơn không có khách
  = 10 hàng
```

Đây là công thức **cho bộ dữ liệu có tính duy nhất của khóa và cardinality đã mô tả**, không phải công thức cứng cho mọi JOIN bất kỳ.

### 16.1. Kiểm tra tổng số hàng bằng SQL

```sql
SELECT
    (SELECT COUNT(*)
     FROM join_check.customers) AS customers_count,
    (SELECT COUNT(*)
     FROM join_check.orders) AS orders_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS inner_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS customers_left_count,
    (SELECT COUNT(*)
     FROM join_check.orders AS o
      LEFT JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id) AS orders_left_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      FULL JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS full_count;
```

Kỳ vọng theo thứ tự: `6, 8, 6, 8, 8, 10`.

### 16.2. Không kiểm tra bằng một COUNT duy nhất

Giả sử một truy vấn JOIN nhầm `order_id` với `customer_id` nhưng tình cờ cũng trả 6 hàng trong dữ liệu khác. Đếm vẫn “đúng số” trong khi quan hệ bị sai.

Kiểm chứng mạnh hơn kết hợp:

- Tổng số hàng.
- `COUNT(DISTINCT ...)` hoặc tập ID.
- Những hàng **bắt buộc phải có**.
- Những hàng **bắt buộc không có**.
- Giá trị aggregate đã tính tay.
- Phân loại unmatched theo từng phía.

## 17. Tránh nhân hàng ngoài ý muốn khi khóa không duy nhất

Khóa chính của `customers` bảo đảm mỗi `customer_id` chỉ có một khách. Nhưng nếu bạn nối theo một thuộc tính **không duy nhất**, số hàng có thể tăng mạnh.

Tạo bảng vùng giao hàng có chủ đích chứa mã vùng trùng nhau:

```sql
CREATE TABLE join_check.delivery_zones (
    zone_id bigint PRIMARY KEY,
    region_code text,
    zone_label text NOT NULL
);

INSERT INTO join_check.delivery_zones
    (zone_id, region_code, zone_label)
VALUES
    (10, 'Bac',  'Bắc thường'),
    (20, 'Nam',  'Nam nội thành'),
    (21, 'Nam',  'Nam ngoại thành'),
    (30, NULL,   'Chưa xác định vùng'),
    (40, 'Tay',  'Tây');
```

Như vậy:

```text
region_code = 'Bac' -> 1 hàng zones
region_code = 'Nam' -> 2 hàng zones
region_code IS NULL  -> 1 hàng zones, nhưng không khớp bằng =
```

### 17.1. Nối khách với vùng giao hàng

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.region_code,
    z.zone_id,
    z.zone_label
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
ORDER BY c.customer_id, z.zone_id;
```

Kết quả có **5 hàng**:

- An thuộc vùng Bac, khớp zone 10: 1 hàng.
- Chi thuộc Nam, khớp zone 20 và 21: 2 hàng.
- Ha thuộc Nam, khớp zone 20 và 21: 2 hàng.
- Binh và Lan có `region_code = NULL`: không khớp bằng `=` với hàng zone NULL.
- Dung có `Trung`: không có zone nào mã Trung.

Nếu nghiệp vụ mong **mỗi khách đúng một vùng**, dữ liệu vùng trùng mã đã phá kỳ vọng cardinality. Thêm `DISTINCT c.customer_id` có thể che vấn đề chứ không giải quyết quy tắc chọn vùng nội thành/ngoại thành.

### 17.2. JOIN nhiều bảng có thể nhân đôi doanh số

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders,
    SUM(o.amount) AS summed_amount_after_join
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kỳ vọng:

| customer_id | joined_rows | distinct_orders | summed_amount_after_join |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 170000.00 |
| 3 | 4 | 2 | 100000.00 |
| 5 | 2 | 1 | 140000.00 |

Tại sao tổng của Chi tăng từ 50.000 lên 100.000, của Ha từ 70.000 lên 140.000?

Vì mỗi đơn của họ **khớp hai hàng delivery_zones** cùng mã `Nam`. `SUM(o.amount)` được thực hiện **sau khi JOIN nhân hàng**, nên số tiền bị cộng hai lần.

**Đừng sửa bằng `SUM(DISTINCT o.amount)`.** Hai đơn hợp lệ có cùng số tiền cũng sẽ bị gộp mất một lần. Cách đúng là sửa quan hệ hoặc tách phép tổng hợp khỏi nguồn có thể nhân hàng.

### 17.3. Cách tránh nhân hàng khi chỉ cần kiểm tra vùng tồn tại

Nếu yêu cầu chỉ là “khách có ít nhất một vùng giao hàng đã khai báo”, dùng `EXISTS`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
ORDER BY c.customer_id;
```

Kết quả có khách 1, 3, 5 — mỗi khách một lần, không bị nhân theo số vùng.

Nếu thực sự cần chọn một vùng trong nhiều vùng Nam, phải có **quy tắc nghiệp vụ** (ưu tiên, thời gian hiệu lực, mã quận, loại địa chỉ...) để xác định vùng hợp lệ. Không chọn hàng tùy ý bằng `LIMIT 1` không có `ORDER BY` và tiêu chí đúng.

## 18. NULL-safe equality: IS NOT DISTINCT FROM

Thông thường, SQL không coi `NULL = NULL` là TRUE. Nhưng có một số bài toán thực sự muốn hai giá trị nullable được xem là tương đương, chẳng hạn nhóm dữ liệu đã được chuẩn hóa để biểu diễn cùng một trạng thái “không khai báo”.

PostgreSQL có toán tử `IS NOT DISTINCT FROM`:

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS both_null_equal,
    'Nam'::text IS NOT DISTINCT FROM 'Nam'::text
        AS same_region,
    'Nam'::text IS NOT DISTINCT FROM NULL::text
        AS region_and_null;
```

Kết quả là TRUE, TRUE, FALSE.

### 18.1. So sánh hai kiểu JOIN trên thuộc tính nullable

Với bảng `delivery_zones` đã tạo:

```sql
-- Nối theo phép bằng thông thường.
SELECT COUNT(*) AS normal_join_rows
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON c.region_code = z.region_code;
```

Kết quả: **5**.

Nếu thay bằng:

```sql
SELECT COUNT(*) AS null_safe_join_rows
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON c.region_code IS NOT DISTINCT FROM z.region_code;
```

Kết quả: **7**, vì ngoài 5 hàng trước còn có:

- Binh (`region_code = NULL`) khớp zone 30 có mã NULL.
- Lan (`region_code = NULL`) cũng khớp zone 30.

### 18.2. Có nên coi mọi NULL là một vùng không?

**Không mặc nhiên.** Nếu NULL nghĩa là “chưa biết vùng của khách”, việc ghép mọi khách chưa biết với một “vùng chưa xác định” có thể mang giá trị trình bày, nhưng không chứng minh họ **cùng một vùng địa lý**.

Chỉ dùng `IS NOT DISTINCT FROM` khi nghiệp vụ thực sự định nghĩa hai NULL là cùng một nhóm hoặc cùng trạng thái cần khớp. Với khóa nhận dạng thực thể, ghép “không biết ID” với “không biết ID” thường là sai.

### 18.3. COALESCE để nối NULL có thể che xung đột

Một mẫu dễ gây rủi ro:

```sql
-- Không khuyến nghị làm mặc định cho khóa nhận dạng:
-- ON COALESCE(c.region_code, 'UNKNOWN')
--    = COALESCE(z.region_code, 'UNKNOWN')
```

Nếu chuỗi `'UNKNOWN'` cũng là giá trị dữ liệu thật, bạn có thể ghép cả NULL với một giá trị có ý nghĩa riêng. `IS NOT DISTINCT FROM` thể hiện ý định NULL-safe rõ hơn, nhưng vẫn phải xác nhận ngữ nghĩa dữ liệu.

## 19. FULL JOIN và quan hệ nhiều-một khi dữ liệu thiếu

Một biểu thức `FULL JOIN` có thể được dùng để **đối soát hai hệ thống**: ví dụ bảng danh mục từ nguồn A và nguồn B. Nhưng đối soát không chỉ là “xem có hàng bên nào không”; còn phải xác định **khóa ghép có thật sự duy nhất**.

Xét hai bảng giả định:

```text
Nguồn A                     Nguồn B
-------                     -------
code K1, giá trị 10         code K1, giá trị 10
code K2, giá trị 20         code K3, giá trị 30
code NULL, giá trị 99       code NULL, giá trị 99
```

Nếu JOIN theo `a.code = b.code`:

- K1 khớp.
- K2 chỉ có ở A.
- K3 chỉ có ở B.
- Hai hàng code NULL **không khớp nhau**, nên mỗi hàng vẫn xuất hiện riêng sau `FULL JOIN`.

Đừng đọc kết quả có `COALESCE(a.code,b.code) IS NULL` là “đã khớp hai NULL”. Có thể đang có **hai hàng mồ côi ở hai phía**.

### 19.1. Kiểm tra khóa có duy nhất trước khi FULL JOIN

Với nguồn cần quan hệ một-một, hãy thử:

```sql
SELECT region_code, COUNT(*) AS row_count
FROM join_check.delivery_zones
GROUP BY region_code
HAVING COUNT(*) > 1;
```

Kết quả cho vùng `Nam` có 2 hàng. Nếu dùng `region_code` làm khóa ghép một-một, đây là tín hiệu **không đạt giả định**, ngay cả khi SQL JOIN vẫn chạy được.

Lưu ý: `GROUP BY` gom các NULL vào cùng nhóm trong kết quả tổng hợp, nhưng điều đó không đồng nghĩa toán tử `=` trong `ON` sẽ coi hai NULL là bằng nhau.

## 20. Phân biệt thiếu dữ liệu, thiếu quan hệ và mối quan hệ không duy nhất

Ba nhóm lỗi có triệu chứng khác nhau:

| Nhóm | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| Khóa ở bảng con là NULL | `orders.customer_id IS NULL` | Lọc trực tiếp ở bảng con, không cần JOIN. |
| Có khóa nhưng không tìm được bảng cha | `external_customer_id IS NOT NULL` và hàng cha không khớp | `LEFT JOIN ... WHERE parent.pk IS NULL` hoặc `NOT EXISTS`. |
| Một khóa khớp nhiều hàng không dự kiến | Số hàng JOIN lớn hơn số hàng theo grain mục tiêu | `GROUP BY join_key HAVING COUNT(*) > 1`, `COUNT(DISTINCT ...)`, kiểm tra constraint. |

Một bản nhập liệu có khóa 999 và một đơn có `customer_id = NULL` cần **hai loại xử lý**: một bản có mã lỗi, một bản chưa được cung cấp mã. Đừng cùng gán một nhãn `orphan` nếu quy trình nghiệp vụ cần phân biệt.

### 20.1. Dữ liệu hoàn chỉnh và dữ liệu chưa hoàn chỉnh có mục đích khác nhau

Trong môi trường production:

- Khóa ngoại, `NOT NULL` và `UNIQUE` giúp **ngăn** nhiều loại dữ liệu sai xuất hiện ở bảng chính.
- Staging có thể cho phép dữ liệu chưa hoàn chỉnh để **thu nhận rồi kiểm tra** trước khi nạp vào bảng chính.
- JOIN diagnostic trên staging giúp **giải thích** vì sao một hàng chưa thể import.
- Snapshot lịch sử hoặc dữ liệu bị ẩn theo chính sách retention có thể khiến một quan hệ được thiết kế khác với schema hoạt động thường ngày.

Kiểm chứng JOIN tốt luôn gắn với **ý nghĩa của bảng** và trạng thái dữ liệu mà bảng ấy được phép chứa.

## 21. Quy tắc lọc trong ON và WHERE đối với nhiều bảng

Khi câu SQL có nhiều JOIN, điều kiện trên một bảng bên phải có thể gây hiệu ứng dây chuyền.

Ví dụ:

```sql
SELECT
    c.customer_id,
    o.order_id,
    z.zone_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
WHERE z.zone_label = 'Nam nội thành'
ORDER BY c.customer_id, o.order_id;
```

`WHERE z.zone_label = 'Nam nội thành'` loại mọi khách không có zone khớp nhãn này. Vì vậy, dù đã dùng hai `LEFT JOIN`, tập khách được bảo toàn ở bước cuối **không còn đầy đủ**.

Nếu yêu cầu là giữ mọi khách và chỉ hiển thị zone thuộc nhãn đã chọn:

```sql
SELECT
    c.customer_id,
    o.order_id,
    z.zone_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
   AND z.zone_label = 'Nam nội thành'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Khi đó các khách khác vẫn có mặt, nhưng `zone_id` là NULL nếu không tìm được zone phù hợp.

### 21.1. Cẩn trọng khi nối thêm bảng sau OUTER JOIN

Nếu bảng `z` được nối theo một cột ở `o` thay vì `c`, những hàng khách không có đơn sẽ mang giá trị NULL phía `o`. Một `INNER JOIN` tiếp theo qua `o` có thể loại các hàng khách ấy. Cấu trúc JOIN phải được phân tích **theo chuỗi nguồn và điều kiện cụ thể**, không chỉ dựa vào lần xuất hiện đầu tiên của từ khóa `LEFT`.

## 22. Kiểm tra hàng trùng sau JOIN bằng khóa, không phải mắt nhìn

Để biết kết quả theo grain “mỗi đơn một hàng” có bị nhân:

```sql
WITH joined AS (
    SELECT
        o.order_id,
        c.customer_id
    FROM join_check.orders AS o
    LEFT JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id
)
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM joined
GROUP BY order_id
HAVING COUNT(*) <> 1
ORDER BY order_id;
```

Trên bộ dữ liệu này, truy vấn **không trả hàng** vì mỗi đơn cho đúng một hàng sau khi LEFT JOIN với bảng khách có primary key duy nhất.

Nếu đổi bảng bên phải thành nguồn có khóa trùng, truy vấn kiểm tra có thể tìm được các đơn xuất hiện hơn một lần.

### 22.1. COUNT(DISTINCT) không luôn giải quyết sai tổng tiền

```sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS unique_orders,
    SUM(o.amount) AS summed_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code;
```

`COUNT(DISTINCT o.order_id)` giúp phát hiện rằng số hàng ghép lớn hơn số đơn duy nhất, nhưng **`SUM(o.amount)` vẫn bị nhân**. Muốn tính tiền đúng, phải loại bỏ hiệu ứng nhân hàng bằng cách chọn quan hệ phù hợp hoặc tổng hợp theo grain của đơn trước.

Một cách tính tổng không bị nhân bởi bảng zones:

```sql
SELECT
    c.customer_id,
    SUM(o.amount) AS total_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Ở đây `EXISTS` chỉ kiểm tra sự tồn tại của vùng, không nhân số hàng đơn theo số vùng có cùng mã.

## 23. Kiểm tra kết quả bằng các phép đối soát tập hợp

Thay vì nhìn thủ công một bảng 10.000 hàng, có thể viết truy vấn tìm **định danh bị thiếu** giữa tập kỳ vọng và tập thực tế.

### 23.1. EXCEPT: khách không xuất hiện trong tập kết quả

Giả sử truy vấn cần giữ mọi khách:

```sql
WITH result_customers AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
)
SELECT customer_id
FROM join_check.customers
EXCEPT
SELECT customer_id
FROM result_customers;
```

Kết quả **không có hàng**. Điều này chứng minh mọi khóa khách hiện đều có mặt trong kết quả ít nhất một lần.

Nếu vô tình viết `WHERE o.order_status = 'paid'` trong CTE, truy vấn `EXCEPT` sẽ phát hiện khách 4 và 6 không còn trong kết quả.

### 23.2. Kiểm tra hai chiều

Khi so sánh hai tập khóa, cần xem cả:

- **Thiếu:** những khóa đáng lẽ có nhưng không xuất hiện.
- **Thừa:** những khóa không thuộc tập mong đợi nhưng lại có mặt.

`EXCEPT` trả tập không lặp mặc định, vì vậy nó rất hữu ích cho **membership** nhưng không thể thay thế phép kiểm tra **multiplicity**. Nếu cả hai tập có cùng ID nhưng một ID bị nhân ba, `EXCEPT` có thể vẫn rỗng.

Kết hợp `EXCEPT` với `GROUP BY ... HAVING COUNT(*) > 1` hoặc `EXCEPT ALL` khi bài toán cần xét số lần lặp.

### 23.3. Kiểm tra tổng hợp

Ví dụ tổng doanh số của các đơn có khách:

```sql
SELECT SUM(amount) AS source_amount
FROM join_check.orders
WHERE customer_id IS NOT NULL;
```

Kỳ vọng: `380000.00`.

So với:

```sql
SELECT SUM(o.amount) AS joined_amount
FROM join_check.orders AS o
JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id;
```

Kỳ vọng cũng là `380000.00` với foreign key và dữ liệu hiện tại.

Nếu kết quả khác, có thể có hàng bị mất hoặc nhân sau JOIN. Nhưng tổng bằng nhau không bảo đảm mọi hàng đúng vì các sai lệch có thể bù trừ; vẫn cần đối chiếu khóa và cardinality.

## 24. Viết các bài kiểm thử SQL có kết quả PASS/FAIL

Bạn có thể biến dự đoán thành truy vấn chỉ đọc. Cách này hữu ích trong notebook, migration verification hoặc quy trình kiểm tra dữ liệu sau khi sửa JOIN.

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM join_check.customers
    ) = 6 AS customers_pass,
    (
        SELECT COUNT(*)
        FROM join_check.orders
    ) = 8 AS orders_pass,
    (
        SELECT COUNT(*)
        FROM join_check.customers AS c
        JOIN join_check.orders AS o
            ON o.customer_id = c.customer_id
    ) = 6 AS inner_join_pass,
    (
        SELECT COUNT(*)
        FROM join_check.customers AS c
        FULL JOIN join_check.orders AS o
            ON o.customer_id = c.customer_id
    ) = 10 AS full_join_pass;
```

Kỳ vọng bốn cột đều `true`.

### 24.1. Kiểm tra tập khóa chính xác

```sql
SELECT (
    SELECT array_agg(o.order_id ORDER BY o.order_id)
    FROM join_check.orders AS o
    JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id
) = ARRAY[101, 102, 103, 104, 106, 107]::bigint[]
  AS inner_join_ids_pass;
```

Kiểm tra này phát hiện được lỗi chọn sai cặp khóa trong nhiều tình huống mà phép đếm không phát hiện.

### 24.2. Kiểm tra khách không có đơn

```sql
WITH actual AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM join_check.orders AS o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT
    array_agg(customer_id ORDER BY customer_id)
        = ARRAY[4, 6]::bigint[] AS no_orders_pass
FROM actual;
```

### 24.3. Kiểm tra staging orphan

```sql
WITH invalid_refs AS (
    SELECT i.import_id
    FROM join_check.order_imports AS i
    LEFT JOIN join_check.customers AS c
        ON c.customer_id = i.external_customer_id
    WHERE i.external_customer_id IS NOT NULL
      AND c.customer_id IS NULL
)
SELECT
    array_agg(import_id ORDER BY import_id)
        = ARRAY[202]::bigint[] AS orphan_import_pass
FROM invalid_refs;
```

Khi áp dụng cho production, không giữ các con số lab cố định. Thay chúng bằng **bất biến nghiệp vụ hoặc tập expected được suy ra độc lập**, đồng thời có cách ghi nhận bằng chứng và xử lý khi có mismatch.

## 25. Khi dùng các bộ lọc với NULL, nhớ ba trạng thái logic

Trong `WHERE`:

- `TRUE`: hàng được giữ.
- `FALSE`: hàng bị loại.
- `UNKNOWN`: hàng cũng bị loại.

```sql
SELECT
    NULL::integer = 1 AS null_equals_one,
    NULL::integer <> 1 AS null_not_equals_one,
    NULL::integer IS NULL AS null_is_null;
```

Hai biểu thức đầu trả SQL NULL (UNKNOWN), biểu thức cuối TRUE.

Ví dụ:

```sql
SELECT order_id, customer_id
FROM join_check.orders
WHERE customer_id <> 1
ORDER BY order_id;
```

Truy vấn trên **không** trả đơn 105 và 108 có customer_id NULL, dù trực giác có thể nói “NULL đâu phải khách 1”. SQL không thể xác định `NULL <> 1` là TRUE.

Nếu yêu cầu là “mọi đơn không thuộc khách 1 **hoặc chưa gắn khách**”:

```sql
SELECT order_id, customer_id
FROM join_check.orders
WHERE customer_id IS DISTINCT FROM 1
ORDER BY order_id;
```

`IS DISTINCT FROM` có ngữ nghĩa rõ ràng với NULL. Cũng có thể viết `customer_id <> 1 OR customer_id IS NULL`, nhưng hãy chọn theo yêu cầu nghiệp vụ.

### 25.1. Đặt điều kiện phía trái vào ON cũng có thể thay nghĩa

Một sai lầm ngược:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND c.customer_id = 1;
```

Câu này **không** chỉ trả khách 1. Những khách khác vẫn được bảo toàn bởi `LEFT JOIN` nhưng không khớp đơn vì điều kiện `c.customer_id = 1` trong `ON` không đúng.

Nếu muốn thực sự chỉ lấy khách 1, đặt điều kiện lọc khách ở `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 1;
```

Đây là minh chứng rằng **đặt đúng điều kiện vào đúng mệnh đề phụ thuộc chính xác đối tượng cần lọc**.

## 26. GROUP BY, NULL và sự khác nhau với JOIN equality

`GROUP BY` của PostgreSQL xem các giá trị NULL của một biểu thức nhóm thuộc **cùng một nhóm**:

```sql
SELECT
    customer_id,
    COUNT(*) AS orders_count
FROM join_check.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
```

Kết quả có các nhóm khách 1, 2, 3, 5 và **một nhóm customer_id NULL gồm hai đơn 105, 108**.

Đây không phải bằng chứng cho thấy hai đơn “thuộc cùng khách không biết ID”. Chúng chỉ được đặt vào cùng **nhóm aggregate mang nhãn NULL**.

Sự khác nhau:

| Thao tác | Hai giá trị NULL |
| --- | --- |
| `a = b` trong `ON` | Không cho TRUE. |
| `a IS NOT DISTINCT FROM b` | Cho TRUE. |
| `GROUP BY a` | Các hàng NULL của `a` được xếp cùng một nhóm. |
| `DISTINCT a` | Chỉ giữ một đại diện NULL trong tập kết quả. |
| `COUNT(a)` | Không đếm giá trị NULL của `a`. |
| `COUNT(*)` | Đếm mọi hàng, kể cả hàng có cột NULL. |

Nắm các quy tắc này giúp tránh nhầm lẫn khi chuyển từ JOIN sang tổng hợp hoặc đối soát.

## 27. Kiểm tra trường hợp không có hàng bên phải nhưng nhiều hàng bên trái

Một bảng có khóa NULL không đồng nghĩa chỉ có **một** hàng chưa khớp.

Trong `orders`, đơn 105 và 108 đều có `customer_id = NULL`. Khi `orders LEFT JOIN customers`:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
```

Kết quả vẫn là **hai hàng** — mỗi đơn một hàng, không bị gộp thành một dòng “khách NULL”.

Ngược lại, nếu viết:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS number_of_orders
FROM join_check.orders AS o
GROUP BY o.customer_id
ORDER BY o.customer_id NULLS LAST;
```

thì hai đơn NULL được tính chung một nhóm. Cần phân biệt **JOIN giữ từng thực thể** với **GROUP BY gom theo giá trị khóa**.

## 28. Đừng để phép nối phụ thuộc vào phép biến đổi thiếu kiểm soát

Đôi khi có hai nguồn dùng định dạng mã khác nhau: một nguồn có khoảng trắng thừa, nguồn kia dùng chữ hoa, hoặc một nguồn là text còn nguồn khác là số.

Ví dụ mô phỏng:

```sql
SELECT
    ' ABC '::text AS raw_code,
    trim(' ABC ') AS normalized_code,
    lower(trim(' ABC ')) AS normalized_lower;
```

Có thể nối bằng biểu thức:

```sql
-- Ví dụ hình thức, cần thay bảng và quy tắc nghiệp vụ thực tế.
-- ON lower(trim(a.code)) = lower(trim(b.code))
```

Nhưng chuẩn hóa khóa ngay tại thời điểm JOIN có những đánh đổi:

- Có thể khiến hai giá trị khác nhau bị gộp thành một nếu case hoặc khoảng trắng thực sự có ý nghĩa.
- Biểu thức trên khóa có thể cần expression index hoặc cột chuẩn hóa riêng để đạt hiệu năng phù hợp.
- Một bảng chứa nhiều hàng sau chuẩn hóa có thể tạo nhiều cặp khớp, khiến JOIN nhân hàng.
- Dùng cast không kiểm soát có thể gây lỗi khi dữ liệu staging chứa chuỗi không thể chuyển kiểu.

Trong quy trình nhập liệu, thường nên tách bước **chuẩn hóa, xác thực và phát hiện khóa trùng** khỏi bước JOIN nghiệp vụ quan trọng.

## 29. Kiểm tra execution plan mà không nhầm với correctness

PostgreSQL có thể dùng nested loop, hash join hoặc merge join tùy kích thước và thống kê. Không nên xem một thuật toán JOIN nhất định là bằng chứng truy vấn đúng hoặc sai.

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

`EXPLAIN` cho kế hoạch ước lượng. Nếu muốn đo:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

`EXPLAIN ANALYZE` thực sự chạy truy vấn để đo. Trong lab, truy vấn chỉ đọc có thể dùng an toàn với mức tải nhỏ; trên production, phải xem xét chi phí chạy câu SQL cụ thể.

### 29.1. Hai trục kiểm tra khác nhau

| Trục | Câu hỏi | Công cụ |
| --- | --- | --- |
| **Đúng dữ liệu** | Có giữ đủ khách không? Có sai cặp khóa không? Có nhân hàng không? | Bộ dữ liệu biên, so sánh tập khóa, COUNT, EXCEPT, NOT EXISTS, kiểm tra aggregate. |
| **Hiệu năng** | JOIN đọc bao nhiêu hàng? Sử dụng index nào? Có sort/hash nặng không? | EXPLAIN, ANALYZE, BUFFERS, thống kê, đo latency. |

Không bỏ qua câu hỏi đúng/sai chỉ vì execution plan “đẹp”. Một query dùng index rất hiệu quả nhưng nối bằng sai cột vẫn có thể trả lời sai nghiệp vụ nhanh hơn.

## 30. Xử lý kết quả NULL ở ứng dụng Java/JDBC

Khi PostgreSQL trả một `LEFT JOIN`, cột của bảng bên phải có thể là SQL NULL do không có hàng khớp.

Ví dụ:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Ứng dụng Java cần giữ đúng nghĩa:

- Với khách 4, `order_id` là **không có đơn khớp**, không phải đơn có ID 0.
- Nếu dùng `ResultSet.getLong("order_id")`, JDBC trả kiểu primitive `long` và khi giá trị SQL là NULL, giá trị Java có thể là 0; phải gọi `wasNull()` để phân biệt.
- Có thể dùng `ResultSet.getObject("order_id", Long.class)` trong môi trường driver phù hợp để nhận `Long` nullable và tránh một số nhầm lẫn primitive.
- DTO muốn biểu diễn “không có đối tượng đơn” thường nên dùng kiểu nullable/optional phù hợp, không tự dựng một đơn giả với ID 0.

Một đoạn Java minh họa:

```java
try (ResultSet rs = preparedStatement.executeQuery()) {
    while (rs.next()) {
        long customerId = rs.getLong("customer_id");
        Long orderId = rs.getObject("order_id", Long.class);

        if (orderId == null) {
            // Khách tồn tại nhưng hàng LEFT JOIN không có đơn khớp.
        } else {
            // Có đơn thực với ID orderId.
        }
    }
}
```

Đoạn mã giả định `preparedStatement` đã được tạo và thực thi trong một ngữ cảnh JDBC hợp lệ. Mục đích của nó là diễn giải giá trị NULL trong kết quả, không phải thay thế toàn bộ phương án mapping ứng dụng.

### 30.1. COALESCE có thể phù hợp cho nhãn, nhưng không phải cho ID

```sql
SELECT
    c.customer_name,
    COALESCE(o.order_status, 'Chưa có đơn') AS order_label
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

Đây là cách trình bày nhãn, có thể thuận tiện cho giao diện. Nhưng:

```sql
-- Không nên tùy tiện biến vắng đơn thành ID 0:
-- COALESCE(o.order_id, 0) AS order_id
```

Khi một cột ID dùng để xác định đối tượng, giá trị 0 giả có thể bị ứng dụng hiểu thành một đối tượng hợp lệ hoặc dẫn đến request sai. Giữ nullable và xử lý vắng quan hệ rõ ràng thường an toàn hơn.

## 31. Quy trình kiểm chứng JOIN trước khi đưa vào báo cáo

Một checklist ngắn có thể áp dụng cho từng truy vấn:

1. **Viết grain mong đợi.** Một khách, một đơn, một cặp khách–đơn, một nhóm ngày?
2. **Xác định bên cần được bảo toàn.** Dùng INNER, LEFT, RIGHT hoặc FULL theo đúng mục tiêu.
3. **Kiểm tra khóa nối.** Kiểu dữ liệu, NULL, unique, FK và khả năng nhiều hàng khớp.
4. **Chuẩn bị ca biên.** Có dữ liệu khớp, không khớp trái/phải, khóa NULL, orphan staging và khóa trùng.
5. **Dự đoán số hàng và ID.** Không đợi có kết quả rồi mới quyết định thế nào là đúng.
6. **Xem ON so với WHERE.** Đặc biệt với bộ lọc ở bảng bên phải của outer join.
7. **Đếm đúng.** `COUNT(*)` khác `COUNT(right.pk)`; `SUM` có thể bị nhân hàng.
8. **Kiểm tra anti-join.** `NOT EXISTS` thường an toàn hơn `NOT IN` khi subquery có NULL.
9. **Đối soát tập khóa, không chỉ tổng.** Dùng `EXCEPT`, `COUNT(DISTINCT)` hoặc test kỳ vọng.
10. **Giữ dữ liệu chưa khớp có ngữ nghĩa rõ.** NULL không đồng nghĩa mã không tồn tại hoặc quan hệ bị vi phạm.
11. **Kiểm tra đầu ra Java/API.** Nullability trong ResultSet và DTO cần phản ánh đúng dữ liệu.
12. **Sau khi đúng mới đo hiệu năng.** `EXPLAIN` không thay thế phép chứng minh kết quả nghiệp vụ đúng.

## 32. Bài tập thực hành

Các bài sau dựa trên dữ liệu **6 khách, 8 đơn, 4 dòng staging** tạo ở phần 2; nếu đã chạy ví dụ `INSERT` thêm đơn 109 hoặc thay đổi bảng, hãy chuẩn bị lại dữ liệu lab trước khi so với đáp án cố định.

### Bài 1. Dự đoán INNER JOIN

Viết truy vấn hiển thị `order_id`, `customer_name` của các đơn có khách hợp lệ. Dự đoán số hàng và danh sách `order_id`.

**Gợi ý:** dùng `JOIN ... ON c.customer_id = o.customer_id`, rồi sắp xếp theo `order_id`.

### Bài 2. Giữ mọi khách

Viết truy vấn hiển thị mọi khách và `order_id` nếu có, bao gồm khách 4 và 6.

**Gợi ý:** `customers LEFT JOIN orders` và không lọc điều kiện bên phải trong `WHERE`.

### Bài 3. Giữ mọi đơn

Viết truy vấn hiển thị mọi đơn và tên khách nếu có. Kiểm tra đơn 105 và 108 còn trong kết quả.

**Gợi ý:** `orders LEFT JOIN customers`.

### Bài 4. FULL JOIN

Viết `FULL OUTER JOIN` để thống kê ba nhóm: matched, customer_without_order và order_without_customer. Dự đoán số hàng từng nhóm và tổng.

**Gợi ý:** dùng `CASE` trên hai primary keys không NULL.

### Bài 5. Hai phiên bản lọc paid

Viết hai truy vấn:

1. Chỉ khách **có đơn paid**.
2. **Mọi khách**, nhưng gắn đơn paid nếu có.

Đặt điều kiện `order_status = 'paid'` ở đúng `WHERE` hoặc `ON`. Giải thích số hàng khác nhau.

### Bài 6. COUNT(*) khác COUNT(order_id)

Viết thống kê cho mỗi khách gồm `COUNT(*)` và `COUNT(o.order_id)` sau `LEFT JOIN`. Giải thích tại sao khách Dung có kết quả 1 và 0.

### Bài 7. Staging orphan

Tìm những bản ghi `order_imports` có `external_customer_id` khác NULL nhưng không khớp khách. Phân biệt với bản ghi chưa có mã.

**Kỳ vọng:** import 202 là unknown ID, 203 là missing ID.

### Bài 8. NOT IN và NULL

Thử ba cách tìm khách chưa có đơn: `NOT EXISTS`, `LEFT JOIN ... IS NULL` và `NOT IN` với subquery không loại NULL. Giải thích vì sao cách thứ ba không trả 4, 6 trong bộ dữ liệu này.

### Bài 9. NULL-safe JOIN

Nối `customers.region_code` với `delivery_zones.region_code` bằng `=` và bằng `IS NOT DISTINCT FROM`. So sánh 5 và 7 hàng.

### Bài 10. Nhân hàng do dữ liệu vùng trùng

Nối `customers`, `orders` và `delivery_zones` để tính tổng tiền theo khách. Vì sao tổng của Chi và Ha bị nhân đôi? Sửa bằng `EXISTS` nếu chỉ cần lọc khách có zone tồn tại.

### Bài 11. Tìm đơn không có khách

Tìm đơn có `customer_id IS NULL`; đối chiếu với kết quả `orders LEFT JOIN customers WHERE c.customer_id IS NULL`. Trong bảng có FK và dữ liệu hiện tại, hai cách có khớp không? Nếu là staging không FK, cách phân biệt orphan sẽ khác thế nào?

### Bài 12. Truy vấn có đúng số hàng nhưng sai tập ID

Giả sử hai câu truy vấn đều trả 6 hàng. Hãy đề xuất ít nhất hai phép kiểm tra bổ sung để biết câu nào đúng.

**Gợi ý:** tập `order_id` được sắp xếp, cặp `(customer_id, order_id)` và phép `EXCEPT` hai chiều.

### Bài 13. Tổng hợp paid theo khách không bỏ khách chưa thanh toán

Viết `COUNT(o.order_id) FILTER (WHERE ...)` để trả số đơn paid của mọi khách, bao gồm khách có 0 đơn paid.

### Bài 14. WHERE trên bảng bên trái

So sánh:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND c.customer_id = 1;
```

với:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 1;
```

Giải thích vì sao câu đầu không chỉ trả khách 1.

### Bài 15. Viết phép kiểm tra tự động

Viết một câu `SELECT` trả boolean `pass` nếu:

- INNER JOIN có 6 hàng.
- FULL JOIN có 10 hàng.
- Tập khách không có đơn là đúng `{4,6}`.

Không dùng thao tác chỉnh dữ liệu hoặc xóa bảng.

## 33. Đáp án và diễn giải

### Đáp án 1: INNER JOIN

```sql
SELECT o.order_id, c.customer_name
FROM join_check.orders AS o
JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Kết quả 6 đơn: 101, 102, 103, 104, 106, 107.

### Đáp án 2: mọi khách

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

8 hàng, bao gồm khách 4 và 6 với `order_id = NULL`.

### Đáp án 3: mọi đơn

```sql
SELECT o.order_id, o.customer_id, c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

8 hàng, trong đó đơn 105 và 108 có `customer_name = NULL`.

### Đáp án 4: FULL JOIN ba nhóm

```sql
WITH classified AS (
    SELECT
        CASE
            WHEN c.customer_id IS NULL
                THEN 'order_without_customer'
            WHEN o.order_id IS NULL
                THEN 'customer_without_order'
            ELSE 'matched'
        END AS join_class
    FROM join_check.customers AS c
    FULL JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
)
SELECT join_class, COUNT(*) AS row_count
FROM classified
GROUP BY join_class
ORDER BY join_class;
```

Kỳ vọng: matched = 6; customer_without_order = 2; order_without_customer = 2; tổng = 10.

### Đáp án 5: WHERE so với ON

```sql
-- Chỉ các cặp khách–đơn paid:
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'paid';

-- Mọi khách, chỉ nối đơn paid nếu có:
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid';
```

Câu thứ nhất có 4 hàng; câu thứ hai có 6 hàng theo bộ dữ liệu này.

### Đáp án 6: COUNT

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS orders_count
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Khách 4 và 6 không có đơn nhưng vẫn có một hàng NULL-extended, nên `COUNT(*) = 1` và `COUNT(o.order_id) = 0`.

### Đáp án 7: phân biệt orphan staging

```sql
SELECT
    i.import_id,
    CASE
        WHEN i.external_customer_id IS NULL THEN 'missing_id'
        WHEN c.customer_id IS NULL THEN 'unknown_id'
        ELSE 'valid_id'
    END AS import_status
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
ORDER BY i.import_id;
```

Kỳ vọng: 201 valid, 202 unknown, 203 missing, 204 valid.

### Đáp án 8: anti-join và NULL

```sql
SELECT c.customer_id
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Trả 4 và 6. `NOT IN` với subquery chứa NULL có thể tạo UNKNOWN cho những khóa không khớp, khiến chúng bị loại khỏi `WHERE`.

### Đáp án 9: NULL-safe equality

```sql
SELECT
    (SELECT COUNT(*)
     FROM join_check.customers AS c
     JOIN join_check.delivery_zones AS z
       ON z.region_code = c.region_code) AS normal_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
     JOIN join_check.delivery_zones AS z
       ON z.region_code IS NOT DISTINCT FROM c.region_code)
       AS null_safe_count;
```

Kết quả 5 và 7. Sự khác biệt đến từ Binh và Lan có `region_code = NULL` khớp zone NULL khi dùng `IS NOT DISTINCT FROM`.

### Đáp án 10: tránh nhân tổng

```sql
SELECT
    c.customer_id,
    SUM(o.amount) AS total_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Đúng theo nguồn: An 170.000; Chi 50.000; Ha 70.000. Không nhân đơn theo số dòng zone.

### Đáp án 11: đơn không gắn khách

```sql
SELECT order_id
FROM join_check.orders
WHERE customer_id IS NULL
ORDER BY order_id;
```

Trả 105 và 108. Với bảng `orders` có FK hợp lệ và dữ liệu hiện tại, `orders LEFT JOIN customers WHERE c.customer_id IS NULL` cũng trả hai đơn đó. Trên staging không FK, cần phân biệt **mã NULL** và **mã không tồn tại** như phần 9.

### Đáp án 12: kiểm tra nhiều chiều

Có thể so sánh `array_agg(order_id ORDER BY order_id)`, `EXCEPT` trên tập ID/cặp ID, và `GROUP BY order_id HAVING COUNT(*) > 1` để phát hiện nhân hàng. `COUNT(*)` một mình không đủ.

### Đáp án 13: đếm paid giữ mọi khách

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kỳ vọng theo khách 1 đến 6: `1,1,1,0,1,0`.

### Đáp án 14: điều kiện trên bảng trái

Trong `ON`, `c.customer_id = 1` chỉ quyết định những cặp khách–đơn nào được nối; các khách khác vẫn xuất hiện vì `LEFT JOIN` bảo toàn trái. Trong `WHERE`, điều kiện loại mọi hàng khách khác khỏi kết quả.

### Đáp án 15: PASS/FAIL

```sql
WITH missing_customers AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM join_check.orders AS o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT
    (
        (SELECT COUNT(*)
         FROM join_check.customers AS c
         JOIN join_check.orders AS o
           ON o.customer_id = c.customer_id) = 6
        AND
        (SELECT COUNT(*)
         FROM join_check.customers AS c
         FULL JOIN join_check.orders AS o
           ON o.customer_id = c.customer_id) = 10
        AND
        (SELECT array_agg(customer_id ORDER BY customer_id)
         FROM missing_customers) = ARRAY[4, 6]::bigint[]
    ) AS pass;
```

Kỳ vọng: `true`.

## 34. Một bài kiểm tra hoàn chỉnh cho báo cáo khách hàng

Giả sử yêu cầu thực tế:

> Hiển thị toàn bộ khách hàng, số đơn đã thanh toán, tổng tiền đã thanh toán. Khách chưa mua hoặc chưa có đơn paid vẫn phải xuất hiện với số 0.

### 34.1. Truy vấn đáp ứng yêu cầu

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS paid_total
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả kỳ vọng:

| customer_id | customer_name | paid_order_count | paid_total |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 120000.00 |
| 2 | Binh | 1 | 90000.00 |
| 3 | Chi | 1 | 20000.00 |
| 4 | Dung | 0 | 0 |
| 5 | Ha | 1 | 70000.00 |
| 6 | Lan | 0 | 0 |

Đặc điểm:

- Mọi khách có một hàng vì `GROUP BY` theo khóa khách.
- Không đếm đơn pending/cancelled vì điều kiện paid nằm trong `ON`.
- Không bỏ khách không có đơn paid vì `LEFT JOIN` vẫn giữ họ.
- `COUNT(o.order_id)` trả 0 nếu không có đơn paid.
- `COALESCE(SUM(o.amount), 0)` trả 0 cho nhóm không có số tiền để cộng, theo quy ước báo cáo đã nêu.

### 34.2. Một cách khác dùng FILTER

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_order_count,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.order_status = 'paid'
        ),
        0
    ) AS paid_total
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Với dữ liệu bài học, hai cách cho cùng kết quả. Dùng `FILTER` có thể dễ mở rộng nếu muốn thêm số đơn pending, cancelled và paid trong cùng bảng báo cáo.

### 34.3. Đối soát tổng paid

Tổng số tiền của mọi đơn paid có khách là:

```sql
SELECT SUM(o.amount) AS paid_source_total
FROM join_check.orders AS o
WHERE o.order_status = 'paid'
  AND o.customer_id IS NOT NULL;
```

Kỳ vọng: `300000.00` (120000 + 90000 + 20000 + 70000).

Tổng `paid_total` sau khi nhóm theo mọi khách cũng phải là 300000.00 khi không có nhân hàng:

```sql
WITH report AS (
    SELECT
        c.customer_id,
        COALESCE(SUM(o.amount), 0) AS paid_total
    FROM join_check.customers AS c
    LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
       AND o.order_status = 'paid'
    GROUP BY c.customer_id
)
SELECT SUM(paid_total) AS report_total
FROM report;
```

Đây là một kiểm tra **tổng hợp bổ sung**. Để chắc chắn kết quả đúng, vẫn nên đối soát số đơn, tập khóa và các tình huống không có quan hệ.

## 35. Tổng kết

Kiểm chứng `JOIN` trong PostgreSQL là kiểm chứng **ý nghĩa của dữ liệu đầu ra**, không chỉ kiểm tra SQL có chạy hay không.

Những nguyên tắc cốt lõi:

- **`INNER JOIN` chỉ giữ cặp khớp.** Nó loại cả khách chưa có đơn lẫn đơn chưa gắn khách.
- **`LEFT/RIGHT/FULL OUTER JOIN` bảo toàn các phía tương ứng**, nhưng hàng không khớp được mở rộng bằng SQL NULL; chúng vẫn có thể bị loại bởi `WHERE`.
- **`NULL = NULL` không cho TRUE** trong điều kiện `ON`. Dùng `IS NOT DISTINCT FROM` chỉ khi nghiệp vụ thật sự muốn coi hai NULL là tương đương.
- **Khóa NULL khác khóa không tồn tại.** Bảng có FK nullable có thể chứa NULL hợp lệ; mã 999 không có bảng cha thường bị FK chặn, trừ những mô hình dữ liệu chưa được ràng buộc như staging.
- **Điều kiện ở `ON` và `WHERE` có thể thay đổi kết quả outer join.** Muốn giữ toàn bộ phía trái nhưng chỉ nối các đơn paid, đặt điều kiện paid trong `ON` hoặc dùng aggregate `FILTER`.
- **`COUNT(*)` khác `COUNT(right.pk)`.** Khách không có đơn vẫn có một hàng của `LEFT JOIN`, nên phải đếm khóa bên phải để có số đơn bằng 0.
- **JOIN trên khóa không duy nhất có thể nhân hàng và làm sai `SUM`.** Cần kiểm tra cardinality và dùng `EXISTS` khi chỉ muốn biết quan hệ tồn tại.
- **`NOT EXISTS` thường phù hợp cho anti-join**, trong khi `NOT IN` với tập con chứa NULL dễ tạo kết quả rỗng ngoài dự kiến.
- **Đừng chỉ so số hàng.** Hãy kiểm tra tập ID, các hàng bắt buộc, các nhóm không khớp, kết quả aggregate và số lần xuất hiện của mỗi khóa.
- **Đọc đúng NULL ở ứng dụng** để không biến quan hệ vắng mặt thành một đối tượng giả.

Khi viết bất kỳ `JOIN` nào cho báo cáo hoặc API, hãy tự hỏi: **“Nếu một bên hoàn toàn không có dữ liệu, nếu khóa nối là NULL, hoặc nếu bên kia có hai hàng cùng khóa, câu truy vấn này sẽ trả chính xác những gì?”** Nếu bạn có bộ dữ liệu kiểm thử và câu SQL đối soát trả lời được câu hỏi đó, độ tin cậy của truy vấn sẽ cao hơn nhiều so với việc chỉ chạy nó trên dữ liệu đang tình cờ đầy đủ.
