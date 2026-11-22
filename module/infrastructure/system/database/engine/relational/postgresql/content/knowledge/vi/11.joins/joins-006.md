# Đặt điều kiện trong ON hoặc WHERE với outer join trong PostgreSQL

## 1. Vấn đề cốt lõi: cùng một điều kiện, khác vị trí, khác kết quả

Khi viết `LEFT JOIN`, `RIGHT JOIN` hoặc `FULL JOIN`, một điều kiện có thể được đặt trong hai vị trí:

- **`ON`:** xác định hai hàng có được coi là **khớp nhau** trong phép nối không.
- **`WHERE`:** quyết định một hàng của **kết quả sau phép nối** có được giữ lại không.

Với `INNER JOIN`, nhiều điều kiện thông thường đặt trong `ON` hoặc chuyển xuống `WHERE` vẫn cho cùng kết quả. Nhưng với **outer join**, việc di chuyển điều kiện có thể thay đổi hoàn toàn những hàng được bảo toàn.

Xét hai yêu cầu gần giống nhau:

> A. “Liệt kê **mọi khách hàng**, kèm **đơn đã thanh toán** nếu có.”

> B. “Liệt kê những **khách hàng có đơn đã thanh toán**, kèm đơn tương ứng.”

Yêu cầu A phải giữ khách hàng chưa thanh toán hoặc chưa có đơn: điều kiện trạng thái đơn thường cần nằm trong `ON` của `LEFT JOIN`.

Yêu cầu B chỉ giữ khách hàng đã có đơn thanh toán: dùng điều kiện ở `WHERE` sau phép nối có thể phù hợp.

Đây là một trong những nguồn sai lệch dữ liệu phổ biến nhất ở báo cáo SQL: câu truy vấn có chữ `LEFT JOIN` nhưng kết quả lại làm mất những hàng mà nghiệp vụ yêu cầu phải xuất hiện.

### Mục tiêu bài học

Bạn sẽ học cách:

1. Phân biệt **matching predicate** trong `ON` và **result filter** trong `WHERE`.
2. Tính thủ công kết quả của cùng điều kiện khi đặt ở hai vị trí.
3. Hiểu **NULL-extended rows** và logic SQL ba trạng thái.
4. Tránh chuyển `LEFT JOIN` thành dạng lọc gần giống `INNER JOIN` ngoài ý muốn.
5. Đặt điều kiện của **bảng được bảo toàn** và **bảng không được bảo toàn** cho đúng.
6. Viết anti-join bằng `IS NULL` và `NOT EXISTS`, kể cả khi tìm “không có đơn thỏa điều kiện”.
7. Áp dụng cùng nguyên tắc cho `RIGHT JOIN`, `FULL JOIN` và chuỗi nhiều outer join.
8. Đếm, tổng hợp, phân trang và sử dụng `FILTER`/`COALESCE` không làm sai kết quả.
9. Phân tích tác động lên `EXPLAIN`, chỉ mục và xử lý nhiều tenant.
10. Lựa chọn cấu trúc SQL tương ứng với ý nghĩa nghiệp vụ, thay vì thay đổi vị trí điều kiện theo cảm tính.

Bài được xây dựng cho PostgreSQL và dùng một bộ dữ liệu cố định để bạn tự chạy, quan sát và đối chiếu.

## 2. Thiết lập dữ liệu mẫu: khách hàng và đơn hàng

Để thấy rõ sự khác nhau giữa `ON` và `WHERE`, ta cần dữ liệu với **nhiều trạng thái ghép**:

- Có khách hàng có đơn `PAID` lẫn `CANCELLED`.
- Có khách hàng chỉ có đơn `CANCELLED`.
- Có khách hàng chỉ có đơn `PENDING`.
- Có khách hàng có đơn `PAID`.
- Có khách hàng **chưa từng có đơn**.

### 2.1. Sơ đồ

```text
customers                             orders
+-----+------+---------------+        +------+-------------+-----------+--------+
| id  | name | city          |        | id   | customer_id | status    | amount |
+-----+------+---------------+        +------+-------------+-----------+--------+
|  1  | An   | Hồ Chí Minh   |<-------| 1001 |      1      | PAID      |  500   |
|     |      |               |<-------| 1002 |      1      | CANCELLED |  100   |
|  2  | Bình | Hà Nội        |<-------| 1003 |      2      | CANCELLED |  200   |
|  3  | Chi  | Hồ Chí Minh   |<-------| 1004 |      3      | PENDING   |  300   |
|  4  | Dũng | Đà Nẵng       |<-------| 1005 |      4      | PAID      |  400   |
|  5  | Hà   | Hà Nội        |        |      |             |           |        |
+-----+------+---------------+        +------+-------------+-----------+--------+

Khách 5: không có đơn.
Khách 2, 3: có đơn, nhưng không có đơn PAID.
Khách 1, 4: có ít nhất một đơn PAID.
```

### 2.2. Tạo bảng

Kết nối tới một database **lab** của PostgreSQL bằng tài khoản được phép tạo schema và bảng:

```sql
CREATE SCHEMA IF NOT EXISTS join144;

CREATE TABLE join144.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE join144.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES join144.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    placed_at timestamptz NOT NULL
);
```

Các ví dụ giả định bảng `join144.customers` và `join144.orders` **chưa tồn tại**. Nếu đã tạo trước đó, hãy sử dụng môi trường lab riêng hoặc migration thích hợp; không tùy tiện xóa dữ liệu để chạy lại.

### 2.3. Thêm dữ liệu

```sql
INSERT INTO join144.customers(customer_id, customer_name, city)
VALUES
    (1, 'An',   'Hồ Chí Minh'),
    (2, 'Bình', 'Hà Nội'),
    (3, 'Chi',  'Hồ Chí Minh'),
    (4, 'Dũng', 'Đà Nẵng'),
    (5, 'Hà',   'Hà Nội');

INSERT INTO join144.orders
    (order_id, customer_id, status, amount, placed_at)
VALUES
    (1001, 1, 'PAID',      500.00, '2026-11-14 09:00:00+07'),
    (1002, 1, 'CANCELLED', 100.00, '2026-11-14 09:30:00+07'),
    (1003, 2, 'CANCELLED', 200.00, '2026-11-14 10:00:00+07'),
    (1004, 3, 'PENDING',   300.00, '2026-11-14 10:30:00+07'),
    (1005, 4, 'PAID',      400.00, '2026-11-14 11:00:00+07');
```

### 2.4. Kiểm tra trạng thái dữ liệu

```sql
SELECT customer_id, customer_name, city
FROM join144.customers
ORDER BY customer_id;

SELECT order_id, customer_id, status, amount
FROM join144.orders
ORDER BY order_id;
```

Kết quả dự kiến ở bảng khách hàng có **5 hàng**; bảng đơn hàng có **5 hàng**.

Trong các bảng kết quả ở bài này, ký hiệu `NULL` là **giá trị NULL thực sự**, không phải chuỗi văn bản `'NULL'`. Sắp xếp kết quả bằng `ORDER BY` để quan sát theo cùng một thứ tự.

## 3. Ôn lại ngữ nghĩa LEFT JOIN trước khi thêm điều kiện

Truy vấn cơ bản:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 1 | An | 1002 | CANCELLED |
| 2 | Bình | 1003 | CANCELLED |
| 3 | Chi | 1004 | PENDING |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

Đếm kết quả:

- Khách 1 có 2 đơn → đóng góp **2 hàng**.
- Khách 2, 3, 4 mỗi người có 1 đơn → tổng **3 hàng**.
- Khách 5 không có đơn → vẫn đóng góp **1 hàng** với dữ liệu phía đơn hàng NULL.
- Tổng cộng: **6 hàng**.

Câu `LEFT JOIN` giữ mọi khách hàng, nhưng **không có nghĩa luôn trả đúng 5 hàng**. Khi một hàng trái ghép được nhiều hàng phải, hàng trái xuất hiện một lần cho **mỗi cặp ghép**.

### 3.1. Hàng NULL mở rộng là gì?

Hàng cuối:

```text
customer_id = 5
customer_name = Hà
order_id = NULL
status = NULL
```

không phải một đơn hàng đã được lưu với mã NULL. Đó là **hàng được tạo trong kết quả outer join** để đại diện cho khách hàng Hà không tìm thấy đơn hàng tương ứng.

Ta gọi phần này là **null extension**: PostgreSQL bảo toàn hàng từ bảng trái, rồi điền NULL vào các cột phía phải vì không có hàng ghép.

Khác biệt này quyết định cách `WHERE o.status = 'PAID'` hoạt động.

## 4. Bộ lọc trong ON: thay đổi điều kiện được coi là “khớp”

Yêu cầu:

> “Hiển thị **tất cả khách hàng**, kèm những **đơn PAID** nếu khách có đơn PAID.”

Viết:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 2 | Bình | NULL | NULL |
| 3 | Chi | NULL | NULL |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

Tổng cộng **5 hàng**.

### 4.1. Vì sao khách Bình vẫn còn?

Khách Bình **có đơn hàng 1003**, nhưng đơn ấy có trạng thái `CANCELLED`. Điều kiện ghép yêu cầu đồng thời:

```sql
o.customer_id = c.customer_id
AND o.status = 'PAID'
```

Đơn 1003 không thỏa điều kiện thứ hai nên **không phải hàng ghép hợp lệ** trong truy vấn này. Vì khách Bình ở bảng trái được bảo toàn và không có đơn PAID nào, PostgreSQL tạo một hàng với các cột đơn hàng NULL.

Điều tương tự áp dụng cho Chi (chỉ có `PENDING`) và Hà (không có đơn nào).

### 4.2. Một điểm không nên hiểu nhầm

Kết quả NULL của Bình và Chi **không chứng minh hai khách này chưa từng có đơn**. Nó chỉ cho biết:

> “Không có đơn nào **thỏa toàn bộ điều kiện trong ON**.”

Vì thế, cách trình bày “Chưa có đơn PAID” sẽ chính xác hơn “Chưa có đơn hàng”.

### 4.3. Công thức trực giác

Với một khách hàng `c`:

- Nếu có `n > 0` đơn thỏa **toàn bộ ON**, xuất `n` hàng ghép.
- Nếu không có đơn nào thỏa ON, vẫn xuất **một hàng** của khách với các cột đơn hàng NULL.

Chính yếu tố “nếu không có cặp khớp thì vẫn giữ hàng trái” tạo ra khác biệt cơ bản với `WHERE`.

## 5. Cùng điều kiện trong WHERE: lọc kết quả sau LEFT JOIN

Bây giờ chuyển `o.status = 'PAID'` từ `ON` xuống `WHERE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 4 | Dũng | 1005 | PAID |

Chỉ còn **2 hàng**.

### 5.1. Vì sao Bình và Chi biến mất?

Lúc ghép, họ đã có các hàng đơn hàng thật:

```text
Bình - 1003 - CANCELLED
Chi  - 1004 - PENDING
```

Nhưng `WHERE o.status = 'PAID'` loại hai hàng vì điều kiện FALSE.

### 5.2. Vì sao Hà cũng biến mất?

Hà không có đơn nào nên LEFT JOIN tạo hàng NULL mở rộng:

```text
Hà - NULL - NULL
```

Trong SQL:

```sql
NULL = 'PAID'
```

cho kết quả **UNKNOWN/NULL**, không phải TRUE. `WHERE` chỉ giữ các hàng có điều kiện TRUE, vì thế loại cả Hà.

### 5.3. Kết luận trọng tâm

Hai câu sau **không tương đương**:

```sql
-- A: giữ tất cả khách hàng, chỉ ghép đơn PAID
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
```

```sql
-- B: chỉ giữ hàng kết quả có đơn PAID
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
```

**A** trả đủ 5 khách hàng; **B** chỉ trả hai khách có ít nhất một đơn PAID.

Bảng đối chiếu:

| Khách hàng | Dữ liệu đơn gốc | Lọc trạng thái trong ON | Lọc trạng thái trong WHERE |
|---|---|---|---|
| An | PAID + CANCELLED | Giữ An, ghép PAID | Giữ An, ghép PAID |
| Bình | Chỉ CANCELLED | Giữ Bình, đơn NULL | Loại Bình |
| Chi | Chỉ PENDING | Giữ Chi, đơn NULL | Loại Chi |
| Dũng | Chỉ PAID | Giữ Dũng, ghép PAID | Giữ Dũng, ghép PAID |
| Hà | Không có đơn | Giữ Hà, đơn NULL | Loại Hà |

## 6. Thứ tự xử lý logic: ON, NULL extension, WHERE

Một mô hình tinh thần hữu ích cho `LEFT JOIN` là:

```text
         customers                     orders
             |                            |
             +-------- ON ----------------+
                     ghép cặp
                        |
              Với khách không khớp
              tạo hàng NULL mở rộng
                        |
                      WHERE
               lọc kết quả JOIN
                        |
                      SELECT
                        |
                     ORDER BY
```

Diễn giải:

1. Đọc hai nguồn của phép nối.
2. Dùng điều kiện `ON` để xác định **những cặp hàng khớp**.
3. Vì là `LEFT JOIN`, bổ sung hàng null-extended cho mỗi hàng trái không có cặp khớp.
4. Áp dụng `WHERE` lên các hàng đã hình thành sau phép nối.
5. Thực hiện các bước SQL tiếp theo như gom nhóm, tính cột kết quả, sắp xếp và giới hạn.

Đây là **ngữ nghĩa logic** để lý giải kết quả. PostgreSQL optimizer có thể tổ chức các bước thực thi vật lý theo kế hoạch khác, miễn sao kết quả tuân thủ ngữ nghĩa SQL.

### 6.1. Điều kiện ON và WHERE không chỉ khác thời điểm

Chúng trả lời hai câu hỏi khác nhau:

| Vị trí | Câu hỏi | Tác động với LEFT JOIN |
|---|---|---|
| `ON` | Hàng phải nào được coi là khớp với hàng trái? | Có thể đổi hàng ghép thành hàng NULL, nhưng vẫn giữ hàng trái |
| `WHERE` | Hàng kết quả nào được giữ sau khi ghép? | Có thể loại hoàn toàn cả hàng trái |
| `HAVING` | Nhóm tổng hợp nào được giữ? | Có thể loại nhóm sau GROUP BY |
| `FILTER (WHERE ...)` | Hàng nào tham gia một phép aggregate cụ thể? | Không nhất thiết loại cả hàng khỏi báo cáo |

Từ “WHERE” bên trong `FILTER (WHERE ...)` thuộc cú pháp aggregate, không phải một bộ lọc `WHERE` toàn truy vấn.

## 7. NULL và logic ba giá trị khiến WHERE loại hàng

PostgreSQL sử dụng các giá trị logic **TRUE**, **FALSE** và **UNKNOWN** khi biểu thức có NULL.

```sql
SELECT
    ('PAID' = 'PAID') AS match_true,
    ('CANCELLED' = 'PAID') AS match_false,
    (NULL::text = 'PAID') AS unknown_result;
```

Kết quả:

| match_true | match_false | unknown_result |
|---|---|---|
| true | false | NULL |

Trong `WHERE`:

- TRUE → giữ hàng.
- FALSE → bỏ hàng.
- UNKNOWN → bỏ hàng.

Vì vậy, bộ lọc:

```sql
WHERE o.status = 'PAID'
```

không giữ hàng null-extended của những khách không có đơn PAID.

### 7.1. Điều kiện “null-rejecting” là gì?

Một predicate được gọi theo cách không chính thức là **null-rejecting** đối với một phía khi các giá trị NULL do outer join tạo ra **không thể khiến predicate cho TRUE**.

Ví dụ với phía `orders`:

```sql
o.status = 'PAID'
o.amount > 100
o.order_id IS NOT NULL
o.placed_at >= TIMESTAMPTZ '2026-11-14 00:00+07'
```

Khi hàng orders không tồn tại và mọi cột orders trở thành NULL, các điều kiện trên không TRUE. Đặt chúng trong `WHERE` sau `LEFT JOIN` sẽ loại hàng null-extended.

Trái lại:

```sql
o.order_id IS NULL
```

**giữ** hàng null-extended; đó là cơ sở của mẫu anti-join.

### 7.2. Không phải mọi WHERE đều biến LEFT JOIN thành INNER JOIN

Ví dụ điều kiện lọc **khách hàng**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.city = 'Hà Nội'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id |
|---:|---|---:|
| 2 | Bình | 1003 |
| 5 | Hà | NULL |

Bộ lọc `WHERE c.city = 'Hà Nội'` chọn những khách hàng ở Hà Nội, rồi kết quả vẫn cho thấy Hà chưa có đơn. Không có điều kiện nào đòi cột của phía orders phải khác NULL.

Điều cần hỏi là: **predicate này có loại bỏ các hàng NULL mở rộng của phía không được bảo toàn không?**

## 8. Trường hợp đặc biệt: lọc thuộc tính của bảng trái trong ON

Không chỉ điều kiện trên bảng phải; đặt điều kiện của **bảng trái** trong `ON` cũng dễ gây hiểu nhầm.

Yêu cầu:

> “Chỉ báo cáo khách hàng ở Hồ Chí Minh, kèm đơn của họ.”

Nếu viết:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND c.city = 'Hồ Chí Minh'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

kết quả vẫn chứa **mọi khách hàng**:

| customer_id | customer_name | city | order_id |
|---:|---|---|---:|
| 1 | An | Hồ Chí Minh | 1001 |
| 1 | An | Hồ Chí Minh | 1002 |
| 2 | Bình | Hà Nội | NULL |
| 3 | Chi | Hồ Chí Minh | 1004 |
| 4 | Dũng | Đà Nẵng | NULL |
| 5 | Hà | Hà Nội | NULL |

Tại sao Bình, Dũng và Hà vẫn có mặt?

Vì với một `LEFT JOIN`, điều kiện `c.city = 'Hồ Chí Minh'` **trong ON** chỉ quyết định xem khách đó có được ghép với đơn hàng hay không. Khách bên trái vẫn được bảo toàn, dù điều kiện thành phố FALSE.

### 8.1. Cách đúng nếu muốn loại khách ngoài Hồ Chí Minh

Dùng bộ lọc trên bảng được bảo toàn trong `WHERE`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.city = 'Hồ Chí Minh'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả chỉ có khách **An và Chi**; An tạo hai hàng, Chi một hàng.

### 8.2. Hai yêu cầu có thể kết hợp

Yêu cầu:

> “Chỉ khách ở Hồ Chí Minh; trong số đó, hiển thị đơn đã thanh toán nếu có.”

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.city = 'Hồ Chí Minh'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 3 | Chi | NULL | NULL |

Cách chia trách nhiệm rất rõ:

- `WHERE c.city ...` chọn tập khách hàng cần báo cáo.
- `ON ... AND o.status ...` chọn những đơn được phép ghép.
- `LEFT JOIN` giữ cả khách Chi dù không có đơn PAID.

## 9. Bẫy “OR o.order_id IS NULL” không luôn tương đương lọc trong ON

Một cách sửa sai thường gặp:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
   OR o.order_id IS NULL
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Người viết hy vọng “vừa lấy đơn PAID, vừa giữ khách không có đơn PAID”. Nhưng kết quả là:

| customer_id | customer_name | order_id | status |
|---:|---|---:|---|
| 1 | An | 1001 | PAID |
| 4 | Dũng | 1005 | PAID |
| 5 | Hà | NULL | NULL |

**Bình và Chi vẫn biến mất**.

### 9.1. Vì sao?

Cần phân biệt:

- **Không có đơn nào:** Hà → LEFT JOIN sinh hàng NULL → `o.order_id IS NULL` TRUE.
- **Có đơn nhưng tất cả đều không phải PAID:** Bình/Chi → LEFT JOIN sinh **các hàng đơn thật**; không có hàng NULL mở rộng → điều kiện `status = 'PAID'` FALSE và `order_id IS NULL` FALSE.

Vì thế câu `WHERE o.status='PAID' OR o.order_id IS NULL` không tương đương với:

```sql
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
```

Với điều kiện trong ON, Bình và Chi **không có cặp ghép PAID**, nên mỗi người được tạo một hàng NULL. Đó là khác biệt quan trọng nhất của bài.

### 9.2. Quy tắc sử dụng OR ... IS NULL

Chỉ dùng mẫu:

```sql
WHERE o.status = 'PAID'
   OR o.order_id IS NULL
```

nếu **đúng nghiệp vụ** là:

> “Những khách có đơn PAID, cộng thêm những khách **hoàn toàn không có đơn hàng**; loại khách chỉ có đơn trạng thái khác.”

Đừng dùng nó làm mẹo phổ quát để biến lọc WHERE thành lọc ON.

## 10. Lọc trong subquery bên phải: cách viết tường minh

Điều kiện của bảng phải cũng có thể đưa vào một nguồn đã lọc:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN (
    SELECT order_id, customer_id, status
    FROM join144.orders
    WHERE status = 'PAID'
) AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả giống với:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id;
```

Cả hai giữ **mọi khách hàng**, chỉ ghép đơn PAID.

### 10.1. Có thể dùng CTE để tăng tính rõ ràng

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, status
    FROM join144.orders
    WHERE status = 'PAID'
)
SELECT
    c.customer_id,
    c.customer_name,
    p.order_id
FROM join144.customers AS c
LEFT JOIN paid_orders AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id, p.order_id NULLS LAST;
```

Đây là một cách diễn đạt rõ **“bảng phải chỉ gồm các đơn PAID”** trước khi thực hiện phép nối.

Tùy phiên bản PostgreSQL, mức độ tham chiếu và đặc điểm CTE, optimizer có thể inline hay materialize CTE theo quy tắc riêng. Không mặc định CTE luôn nhanh hoặc luôn chậm; ở đây ta chọn vì **dễ đọc và đúng ngữ nghĩa**.

### 10.2. Khi nào nên lọc từng nguồn trước FULL JOIN?

Đối với `FULL JOIN`, hai phía **đều được bảo toàn**. Nếu muốn đối soát “các hàng đủ điều kiện” của **cả hai nguồn** thì việc lọc từng nguồn trong subquery/CTE **trước khi FULL JOIN** thường rõ hơn đặt bộ lọc chung ở `WHERE` sau join. Phần 16 sẽ minh họa.

## 11. Đếm số đơn: COUNT(*) và COUNT(o.order_id) không giống nhau

Yêu cầu:

> “Liệt kê mọi khách hàng và số đơn PAID, khách chưa có đơn PAID phải có số 0.”

Dùng `LEFT JOIN` với điều kiện ở `ON`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | paid_order_count |
|---:|---|---:|
| 1 | An | 1 |
| 2 | Bình | 0 |
| 3 | Chi | 0 |
| 4 | Dũng | 1 |
| 5 | Hà | 0 |

### 11.1. Vì sao dùng COUNT(o.order_id)?

Đối với khách không có đơn PAID, `LEFT JOIN` tạo **một hàng NULL mở rộng**. Vì thế:

- `COUNT(*)` đếm hàng đó thành **1**.
- `COUNT(o.order_id)` bỏ qua giá trị NULL và trả **0**.

Kiểm tra trực tiếp:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_row_count,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | joined_row_count | paid_order_count |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 1 | 0 |
| 3 | 1 | 0 |
| 4 | 1 | 1 |
| 5 | 1 | 0 |

Nếu khách 1 có ba đơn PAID, cả hai bộ đếm ở khách 1 sẽ thành 3; với khách 2 không có đơn PAID, `COUNT(*)` vẫn là 1.

### 11.2. Đặt trạng thái ở WHERE sẽ làm mất nhóm khách

Viết:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_order_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

chỉ trả nhóm khách 1 và 4. Khách 2, 3, 5 **không xuất hiện với số 0**, vì đã bị `WHERE` loại trước khi `GROUP BY`.

Đây là lỗi phổ biến trong dashboard: biểu đồ không hiển thị những nhóm có số lượng 0, dù nghiệp vụ muốn báo cáo đầy đủ.

## 12. Aggregate FILTER: đếm nhiều trạng thái trong cùng báo cáo

Nếu cần **tổng số đơn, số đơn PAID, số đơn CANCELLED** của mọi khách hàng, có thể giữ tất cả đơn ở `ON` rồi dùng `FILTER` cho từng aggregate:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PAID'
    ) AS paid_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'CANCELLED'
    ) AS cancelled_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PENDING'
    ) AS pending_orders
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả:

| Khách | Tổng | PAID | CANCELLED | PENDING |
|---|---:|---:|---:|---:|
| An | 2 | 1 | 1 | 0 |
| Bình | 1 | 0 | 1 | 0 |
| Chi | 1 | 0 | 0 | 1 |
| Dũng | 1 | 1 | 0 | 0 |
| Hà | 0 | 0 | 0 | 0 |

### 12.1. FILTER (WHERE ...) không phải WHERE toàn truy vấn

Trong cú pháp:

```sql
COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
```

điều kiện chỉ kiểm soát **những hàng đóng góp vào aggregate COUNT này**; nó không xóa cả khách hàng khỏi nhóm.

Đó là lý do `FILTER` đặc biệt hữu ích cho báo cáo “giữ tất cả nhóm nhưng tính nhiều chỉ số điều kiện”.

### 12.2. Nếu chỉ cần tổng tiền PAID

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_amount
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả dự kiến:

| customer_id | paid_amount |
|---:|---:|
| 1 | 500.00 |
| 2 | 0 |
| 3 | 0 |
| 4 | 400.00 |
| 5 | 0 |

Lưu ý `SUM` trên nhóm không có giá trị phù hợp thường trả NULL, nên `COALESCE(...,0)` được dùng khi báo cáo muốn số 0. Nếu nghiệp vụ cần phân biệt “chưa có dữ liệu” với “tổng bằng 0”, hãy giữ ngữ nghĩa NULL.

## 13. Anti-join: “không có hàng nào thỏa điều kiện”

Có hai câu hỏi khác nhau:

1. Khách nào **chưa từng có đơn**?
2. Khách nào **không có đơn PAID**, dù có thể có đơn trạng thái khác?

### 13.1. Chưa từng có đơn

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả: chỉ **Hà (5)**.

Vì `order_id` là khóa chính NOT NULL, `o.order_id IS NULL` sau join chứng minh **không có hàng orders thật sự được ghép**.

### 13.2. Không có bất kỳ đơn PAID nào

Cần đặt điều kiện `PAID` trong `ON`, rồi tìm những hàng không có đối tác PAID:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
|---:|---|
| 2 | Bình |
| 3 | Chi |
| 5 | Hà |

Bình có đơn CANCELLED, Chi có đơn PENDING, Hà không có đơn; **cả ba đều không có đơn PAID**.

### 13.3. Viết bằng NOT EXISTS

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join144.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả cũng là Bình, Chi và Hà.

Mẫu `NOT EXISTS` diễn đạt trực tiếp **“không tồn tại đơn PAID của khách này”**, không cần dùng hàng NULL mở rộng. PostgreSQL optimizer thường có thể sử dụng một kiểu **anti join** trong kế hoạch khi phù hợp.

### 13.4. Vì sao không chọn cột tùy ý để kiểm tra NULL?

Mẫu:

```sql
WHERE o.order_id IS NULL
```

dùng được vì `order_id` là khóa chính, một hàng thật không thể có `order_id NULL`.

Nếu thay bằng:

```sql
WHERE o.some_nullable_field IS NULL
```

câu truy vấn có thể chọn cả những đơn đã ghép nhưng trường `some_nullable_field` thực sự NULL. Vì thế, để nhận diện “không có đối tác”, dùng **cột bảo đảm NOT NULL của bảng bên kia** hoặc `NOT EXISTS`.

## 14. RIGHT JOIN: ON và WHERE cũng có cùng khác biệt

`RIGHT JOIN` bảo toàn mọi hàng **bên phải**. Có thể coi:

```sql
A RIGHT JOIN B ON ...
```

có cùng khả năng biểu đạt với:

```sql
B LEFT JOIN A ON ...
```

sau khi đổi thứ tự bảng và điều chỉnh phần SELECT/điều kiện.

### 14.1. Yêu cầu: mọi khách hàng, đơn PAID nếu có

Viết theo `RIGHT JOIN`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả vẫn có **5 khách hàng**: An 1001; Bình NULL; Chi NULL; Dũng 1005; Hà NULL.

Bảng **bên phải** là `customers` nên được giữ dù không có đơn PAID phù hợp.

### 14.2. Chuyển lọc đơn sang WHERE

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Kết quả chỉ còn An và Dũng, giống ví dụ LEFT JOIN lọc phía không được bảo toàn trong `WHERE`.

### 14.3. Đặt điều kiện của bảng được bảo toàn vào ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id
FROM join144.orders AS o
RIGHT JOIN join144.customers AS c
    ON o.customer_id = c.customer_id
   AND c.city = 'Hồ Chí Minh'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Điều kiện thành phố trong ON **không loại các khách ở Hà Nội hay Đà Nẵng** khỏi kết quả, vì họ nằm phía phải được bảo toàn. Nó chỉ khiến những khách ngoài Hồ Chí Minh không có đơn nào được ghép trong truy vấn này.

Muốn chỉ giữ khách ở Hồ Chí Minh, đặt:

```sql
WHERE c.city = 'Hồ Chí Minh'
```

ở cuối truy vấn.

### 14.4. Quy tắc khi đọc RIGHT JOIN

Đừng nhớ máy móc “điều kiện của bảng phải phải để WHERE”. Hãy nhớ:

- **Bảng bên phải được bảo toàn** trong RIGHT JOIN.
- Bộ lọc trên **bảng trái không được bảo toàn** đặt trong WHERE có thể loại hàng phải null-extended.
- Bộ lọc trên bảng phải đặt trong ON không nhất thiết loại hàng phải.

Đối xứng với LEFT JOIN, chỉ thay hướng bảo toàn.

## 15. FULL JOIN: cả hai phía đều được bảo toàn trong ON

`FULL JOIN` bảo toàn:

1. Mọi **cặp khớp** theo ON.
2. Những hàng **chỉ có bên trái**.
3. Những hàng **chỉ có bên phải**.

Vì cả hai phía đều có thể sinh hàng NULL mở rộng, chuyển bộ lọc giữa `ON` và `WHERE` ở FULL JOIN càng dễ tạo khác biệt khó thấy.

### 15.1. Bộ dữ liệu đối soát độc lập

Tạo hai nguồn tồn kho đơn giản. Chúng cố ý **không có khóa ngoại với nhau**, vì mục tiêu là tìm các mã chỉ tồn tại ở một bên.

```sql
CREATE TABLE join144.erp_inventory (
    sku text PRIMARY KEY,
    erp_qty integer NOT NULL,
    approved boolean NOT NULL
);

CREATE TABLE join144.wms_inventory (
    sku text PRIMARY KEY,
    wms_qty integer NOT NULL,
    verified boolean NOT NULL
);

INSERT INTO join144.erp_inventory(sku, erp_qty, approved)
VALUES
    ('A', 10, TRUE),
    ('B', 20, FALSE),
    ('C', 30, TRUE);

INSERT INTO join144.wms_inventory(sku, wms_qty, verified)
VALUES
    ('B', 20, TRUE),
    ('C', 35, FALSE),
    ('D', 40, TRUE);
```

### 15.2. FULL JOIN cơ bản

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
ORDER BY COALESCE(e.sku, w.sku);
```

Kết quả:

| erp_sku | erp_qty | wms_sku | wms_qty |
|---|---:|---|---:|
| A | 10 | NULL | NULL |
| B | 20 | B | 20 |
| C | 30 | C | 35 |
| NULL | NULL | D | 40 |

Có **4 hàng**: A chỉ bên trái; B, C khớp; D chỉ bên phải.

### 15.3. Thêm điều kiện ở ON

Giả sử chỉ coi WMS là một **cặp ghép hợp lệ** khi hàng WMS đã được xác minh:

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty,
    w.verified
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
   AND w.verified = TRUE
ORDER BY COALESCE(e.sku, w.sku),
         e.sku NULLS LAST;
```

Điểm quan trọng:

- B có `verified = TRUE` nên vẫn ghép thành một hàng B–B.
- C có `verified = FALSE` nên **không được coi là cặp ghép**.
- Vì FULL JOIN bảo toàn cả hai bên, hàng ERP có SKU C **vẫn xuất hiện riêng**, và hàng WMS có SKU C **cũng vẫn xuất hiện riêng**.
- A chỉ có ERP và D chỉ có WMS vẫn xuất hiện.

Kết quả có **5 hàng**: A chỉ trái; B ghép; C trái riêng; C phải riêng; D phải riêng.

Đây là đặc điểm rất khác với LEFT JOIN: khi thêm điều kiện vào ON, một cặp trước đó khớp có thể trở thành **hai hàng đơn phương**, vì cả hai phía đều được bảo toàn.

### 15.4. Chuyển điều kiện vào WHERE

```sql
SELECT
    e.sku AS erp_sku,
    e.erp_qty,
    w.sku AS wms_sku,
    w.wms_qty,
    w.verified
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE w.verified = TRUE
ORDER BY COALESCE(e.sku, w.sku);
```

Kết quả:

| erp_sku | erp_qty | wms_sku | wms_qty | verified |
|---|---:|---|---:|---|
| B | 20 | B | 20 | true |
| NULL | NULL | D | 40 | true |

Ở đây:

- A bị loại vì cột `w.verified` NULL.
- C bị loại vì WMS có `verified = FALSE`.
- B và D được giữ.

**FULL JOIN vẫn xuất hiện trong SQL, nhưng WHERE đã loại nhiều hàng của một hoặc cả hai nhóm bảo toàn.**

### 15.5. Khi nào bộ lọc trong ON là đúng?

Nếu yêu cầu là:

> “Đối soát mọi bản ghi ERP và WMS, nhưng chỉ coi hai hàng là tương ứng khi WMS được xác minh.”

điều kiện `w.verified = TRUE` trong `ON` có thể là đúng. Bản ghi WMS chưa xác minh vẫn xuất hiện **riêng** để người kiểm tra nhận biết.

Nếu yêu cầu là:

> “Chỉ báo cáo những hàng kết quả có bản ghi WMS đã xác minh.”

điều kiện ở `WHERE` có thể đúng, nhưng nó không bảo toàn đầy đủ hai nguồn.

Nếu yêu cầu là:

> “Trước tiên chỉ chọn các bản ghi hợp lệ của mỗi hệ thống, sau đó đối soát toàn bộ hai danh sách đã lọc.”

thì **lọc từng nguồn trước FULL JOIN** thường rõ nghĩa nhất.

## 16. Lọc từng nguồn trước FULL JOIN để giữ đầy đủ tập đã chọn

Ví dụ chỉ xét ERP đã duyệt và WMS đã xác minh:

```sql
WITH approved_erp AS (
    SELECT sku, erp_qty
    FROM join144.erp_inventory
    WHERE approved IS TRUE
),
verified_wms AS (
    SELECT sku, wms_qty
    FROM join144.wms_inventory
    WHERE verified IS TRUE
)
SELECT
    COALESCE(e.sku, w.sku) AS sku,
    e.erp_qty,
    w.wms_qty,
    CASE
        WHEN e.sku IS NULL THEN 'ONLY_WMS'
        WHEN w.sku IS NULL THEN 'ONLY_ERP'
        WHEN e.erp_qty IS DISTINCT FROM w.wms_qty THEN 'QTY_DIFF'
        ELSE 'MATCH'
    END AS match_status
FROM approved_erp AS e
FULL JOIN verified_wms AS w
    ON e.sku = w.sku
ORDER BY sku;
```

Sau lọc:

- ERP được duyệt: A, C.
- WMS đã xác minh: B, D.

Hai danh sách này **không có SKU chung**, vì thế FULL JOIN trả bốn hàng đơn phương:

| sku | erp_qty | wms_qty | match_status |
|---|---:|---:|---|
| A | 10 | NULL | ONLY_ERP |
| B | NULL | 20 | ONLY_WMS |
| C | 30 | NULL | ONLY_ERP |
| D | NULL | 40 | ONLY_WMS |

Không nên nhầm kết quả này với FULL JOIN ở phần 15.3, nơi C ở WMS dù chưa xác minh **vẫn được giữ** nhưng không được ghép.

### 16.1. Ba cách đặt điều kiện tương ứng với ba yêu cầu

| Cách viết | Ngữ nghĩa chủ đạo |
|---|---|
| `FULL JOIN ... ON e.sku=w.sku AND w.verified` | Cả hai nguồn gốc được giữ, chỉ những cặp thỏa toàn bộ ON mới được ghép |
| `FULL JOIN ... ON e.sku=w.sku WHERE w.verified` | Ghép theo SKU trước, rồi chỉ giữ hàng kết quả có WMS verified |
| `FROM (ERP đã lọc) FULL JOIN (WMS đã lọc)` | Chọn tập nguồn mong muốn trước, rồi bảo toàn cả hai tập đã chọn |

Đây là lý do không tồn tại mẹo “mọi điều kiện FULL JOIN cứ để ON” hoặc “mọi điều kiện lọc cứ để WHERE”. **Ý nghĩa nghiệp vụ quyết định vị trí**, không phải thói quen cú pháp.

## 17. Phân loại hàng không khớp trong FULL JOIN

Nếu chỉ muốn tìm những SKU xuất hiện ở đúng một nguồn:

```sql
SELECT
    e.sku AS erp_sku,
    w.sku AS wms_sku
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL
   OR w.sku IS NULL
ORDER BY COALESCE(e.sku, w.sku);
```

Kết quả: **A chỉ ERP** và **D chỉ WMS**.

Khóa `sku` ở mỗi bảng là `PRIMARY KEY NOT NULL`, nên:

- `e.sku IS NULL` nghĩa là không có hàng ERP khớp.
- `w.sku IS NULL` nghĩa là không có hàng WMS khớp.

### 17.1. Chỉ lấy phía ERP không có WMS

```sql
SELECT e.sku, e.erp_qty
FROM join144.erp_inventory AS e
LEFT JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE w.sku IS NULL
ORDER BY e.sku;
```

Kết quả: A.

### 17.2. Chỉ lấy phía WMS không có ERP

```sql
SELECT w.sku, w.wms_qty
FROM join144.erp_inventory AS e
RIGHT JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL
ORDER BY w.sku;
```

Kết quả: D.

Có thể viết rõ hơn bằng `wms_inventory w LEFT JOIN erp_inventory e` và `WHERE e.sku IS NULL`.

### 17.3. Vì sao phân loại dựa trên khóa NOT NULL?

Không nên dùng:

```sql
WHERE e.some_nullable_column IS NULL
```

để kết luận “không tồn tại ERP”, vì bản ghi ERP có thể tồn tại mà cột tùy chọn đó NULL.

Khi có `FULL JOIN` và cần phân loại ba nhóm `MATCHED`, `LEFT_ONLY`, `RIGHT_ONLY`, hãy dùng **một khóa bảo đảm NOT NULL ở từng nguồn** hoặc một marker đáng tin cậy.

## 18. LEFT JOIN qua nhiều bảng: WHERE ở bảng thứ ba có thể loại cả hàng đầu tiên

Trong một báo cáo thực tế:

```text
customers LEFT JOIN orders LEFT JOIN payments
```

Một điều kiện trên `payments` ở `WHERE` có thể làm biến mất không chỉ đơn hàng mà còn **khách hàng** của outer join đầu tiên.

### 18.1. Tạo bảng thanh toán

```sql
CREATE TABLE join144.payments (
    payment_id bigint PRIMARY KEY,
    order_id bigint NOT NULL UNIQUE
        REFERENCES join144.orders(order_id),
    payment_status text NOT NULL
        CHECK (payment_status IN ('SETTLED', 'FAILED'))
);

INSERT INTO join144.payments
    (payment_id, order_id, payment_status)
VALUES
    (9001, 1001, 'SETTLED'),
    (9002, 1003, 'FAILED'),
    (9003, 1005, 'SETTLED');
```

### 18.2. Câu dễ sai: WHERE trên bảng cuối

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    p.payment_status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join144.payments AS p
    ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED'
ORDER BY c.customer_id;
```

Kết quả chỉ là:

| customer_id | customer_name | order_id | payment_status |
|---:|---|---:|---|
| 1 | An | 1001 | SETTLED |
| 4 | Dũng | 1005 | SETTLED |

Nếu yêu cầu là “mọi khách hàng, giao dịch thanh toán thành công nếu có”, truy vấn trên **sai** vì lọc kết quả cuối làm mất các khách không có payment SETTLED.

### 18.3. Đặt điều kiện thanh toán trong ON

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    p.payment_status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join144.payments AS p
    ON p.order_id = o.order_id
   AND p.payment_status = 'SETTLED'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Câu này giữ mọi khách hàng, nhưng **vẫn giữ cả các đơn không có thanh toán SETTLED**. Ví dụ:

- An có hàng đơn 1001 với SETTLED, và đơn 1002 có payment NULL.
- Bình có đơn 1003 với payment NULL vì FAILED không thỏa ON.
- Chi có đơn 1004 với payment NULL.
- Dũng có 1005 với SETTLED.
- Hà có cả order/payment NULL.

Điều này đúng khi muốn nhìn **mọi đơn** và chỉ ghép payment SETTLED.

### 18.4. Muốn chỉ ghép các đơn có payment SETTLED nhưng vẫn giữ mọi khách hàng?

Cần xác định cả “đơn đủ điều kiện” **trước phép JOIN đầu tiên**. Có thể dùng một nguồn con kết hợp orders + payments:

```sql
WITH settled_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        p.payment_id
    FROM join144.orders AS o
    INNER JOIN join144.payments AS p
        ON p.order_id = o.order_id
       AND p.payment_status = 'SETTLED'
)
SELECT
    c.customer_id,
    c.customer_name,
    s.order_id,
    s.payment_id
FROM join144.customers AS c
LEFT JOIN settled_orders AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id, s.order_id NULLS LAST;
```

Kết quả có đủ **5 khách hàng**, chỉ ghép đơn 1001 và 1005; khách Bình, Chi, Hà có phần đơn NULL.

**Đây không giống** việc `LEFT JOIN orders` tất cả trước, sau đó chỉ lọc payments trong `ON`. Hai yêu cầu khác nhau:

- “Mọi đơn, kèm payment thành công nếu có” → LEFT JOIN hai cấp và lọc payment ở ON cuối.
- “Chỉ các đơn thanh toán thành công, nhưng mọi khách vẫn hiện” → lọc/cấu tạo nguồn `settled_orders` trước rồi LEFT JOIN.

## 19. Khi FULL/LEFT JOIN được dùng với điều kiện không phải dấu bằng

`ON` không bắt buộc chỉ có `a.id = b.id`. PostgreSQL cho phép điều kiện theo khoảng thời gian, ngưỡng số, so khớp chuỗi hoặc các biểu thức phù hợp.

Ví dụ cần tìm giá khuyến mãi hiệu lực khi đơn được đặt:

```sql
-- Khuôn mẫu minh họa, các bảng promotion cần được tạo riêng.
SELECT
    o.order_id,
    p.promotion_name
FROM orders AS o
LEFT JOIN promotions AS p
    ON p.product_id = o.product_id
   AND o.placed_at >= p.valid_from
   AND o.placed_at < p.valid_to;
```

Trong câu trên, ba điều kiện trong ON xác định **một promotion đủ điều kiện ghép với đơn**. Với đơn không có promotion hợp lệ, LEFT JOIN vẫn giữ đơn và điền NULL cho promotion.

Nếu chuyển:

```sql
WHERE o.placed_at >= p.valid_from
  AND o.placed_at < p.valid_to
```

xuống cuối, các đơn không có promotion sẽ bị loại do so sánh với NULL không TRUE. Đây là cùng nguyên tắc ON/WHERE, **không phụ thuộc toán tử '='**.

Các bảng `orders`/`promotions` ở đoạn này là khuôn mẫu nghiệp vụ, không phải các bảng đã tạo trong schema lab.

### 19.1. Dùng range operator trong ON

Với PostgreSQL, một mô hình có thể dùng range:

```sql
-- Khuôn mẫu minh họa khi promotions.valid_period là tstzrange:
SELECT
    o.order_id,
    p.promotion_id
FROM orders AS o
LEFT JOIN promotions AS p
    ON p.product_id = o.product_id
   AND p.valid_period @> o.placed_at;
```

Phép `@>` được đưa vào ON vì nó xác định **promotion có hiệu lực ở thời điểm đặt đơn**. Các đơn không có promotion vẫn được bảo toàn.

## 20. Khi nào có thể chuyển predicate giữa ON và WHERE?

Không phải mọi câu điều kiện đều tạo khác biệt. Nhưng phải có căn cứ ngữ nghĩa.

### 20.1. Với INNER JOIN

Hai câu sau tương đương về tập hàng kết quả trong trường hợp điều kiện đơn giản này:

```sql
SELECT c.customer_id, o.order_id
FROM join144.customers AS c
INNER JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

```sql
SELECT c.customer_id, o.order_id
FROM join144.customers AS c
INNER JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Vì INNER JOIN không tạo hàng NULL mở rộng để bảo toàn bảng nào, cả hai chỉ giữ các cặp đáp ứng toàn bộ điều kiện.

Tuy nhiên, khi câu truy vấn chứa thêm outer join, subquery, aggregate, window function, điều kiện biến đổi hoặc các phép nối có ngữ nghĩa khác, cần xem **toàn bộ vị trí biểu thức**, không suy luận máy móc từ hai câu INNER JOIN đơn giản.

### 20.2. Với LEFT JOIN và predicate chỉ phụ thuộc bảng phải

Thông thường:

```sql
LEFT JOIN B ON A.key=B.key AND B.flag=TRUE
```

**không tương đương** với:

```sql
LEFT JOIN B ON A.key=B.key
WHERE B.flag=TRUE
```

vì câu thứ hai có thể loại các hàng A không có đối tác thỏa điều kiện.

### 20.3. Với LEFT JOIN và predicate chỉ phụ thuộc bảng trái

Thông thường:

```sql
LEFT JOIN B ON A.key=B.key AND A.region='VN'
```

**không tương đương** với:

```sql
LEFT JOIN B ON A.key=B.key
WHERE A.region='VN'
```

vì ở câu thứ nhất, tất cả hàng A vẫn được giữ; ở câu thứ hai, hàng A ngoài vùng bị loại.

### 20.4. Với FULL JOIN

Cả hai phía được bảo toàn, nên đặt predicate chỉ phụ thuộc A hoặc B trong ON **không nhất thiết loại các hàng của phía đó**. Nó có thể biến một cặp khớp thành hai hàng không khớp.

Ngược lại, một WHERE yêu cầu cột A/B thỏa điều kiện có thể loại chính những hàng không có đối tác mà FULL JOIN vừa sinh.

### 20.5. Quy tắc chung để chọn vị trí

Hãy viết mục tiêu bằng lời:

- “Chỉ **ghép** những B thỏa điều kiện, còn A luôn xuất hiện” → điều kiện B ở ON của LEFT JOIN.
- “Chỉ **giữ** những A thỏa điều kiện” → WHERE trên A, hoặc nguồn A được lọc trước.
- “Chỉ **giữ những cặp** thỏa điều kiện” → INNER JOIN hoặc WHERE cuối tùy truy vấn.
- “Chỉ **đối soát tập hợp con** của mỗi nguồn” → lọc từng nguồn trước FULL JOIN.
- “Chỉ **tìm A không có B thỏa điều kiện**” → điều kiện B trong ON và WHERE B.pk IS NULL, hoặc NOT EXISTS.

Đừng di chuyển điều kiện chỉ để SQL trông gọn hơn.

## 21. EXPLAIN: PostgreSQL có thể tối ưu LEFT JOIN thành INNER JOIN

Một điểm rất quan trọng: câu truy vấn viết `LEFT JOIN` **không bảo đảm kế hoạch thực thi luôn chứa node “Left Join”**.

Ví dụ:

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Vì `WHERE o.status = 'PAID'` **loại mọi hàng NULL mở rộng** của orders, PostgreSQL có thể chứng minh rằng phép LEFT JOIN không cần giữ những hàng trái không khớp và **biến đổi nó thành inner join tương đương** trong kế hoạch.

Điều đó là tối ưu hóa hợp lệ theo ngữ nghĩa SQL. Không phải PostgreSQL “bỏ qua” câu lệnh; nó đã nhận ra rằng bộ lọc cuối khiến khả năng bảo toàn trái không còn tạo khác biệt trong kết quả.

### 21.1. Truy vấn lọc trong ON không tương tự

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Ở đây hàng khách không có đơn PAID **phải được giữ**, nên optimizer không được tự đổi thành một inner join khiến các hàng đó biến mất.

Tuy nhiên, PostgreSQL vẫn có thể thay đổi hướng trình bày join, chọn Hash/Merge/Nested Loop hoặc đẩy những điều kiện an toàn xuống nguồn phù hợp. Đừng kỳ vọng tên plan node giống chữ SQL trong mọi trường hợp.

### 21.2. Kiểm tra hiệu năng bằng EXPLAIN ANALYZE

Trong database lab:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

`ANALYZE` **thực thi câu query**, nên chỉ dùng với phép SELECT lab hoặc có biện pháp an toàn tương ứng khi truy vấn có side effect. Dữ liệu ví dụ rất nhỏ, vì vậy planner hoàn toàn có thể chọn sequential scan thay vì index.

### 21.3. Chỉ mục hỗ trợ điều kiện ghép

Với workload cần lấy đơn theo khách hàng và trạng thái:

```sql
CREATE INDEX idx_join144_orders_customer_status
ON join144.orders(customer_id, status);
```

Hoặc nếu phần lớn truy vấn chỉ quan tâm đơn PAID, cân nhắc partial index:

```sql
CREATE INDEX idx_join144_orders_paid_customer
ON join144.orders(customer_id)
WHERE status = 'PAID';
```

Chỉ mục partial hỗ trợ một số truy vấn có predicate đủ rõ để planner chứng minh phù hợp. Không phải mọi câu query hay mọi biến thể parameter hóa đều tận dụng nó.

Quan trọng: **chọn đặt điều kiện trong ON/WHERE phải dựa trên kết quả đúng trước**, rồi mới tối ưu. Đừng thay đổi ngữ nghĩa báo cáo để hy vọng dùng index nhanh hơn.

## 22. Khi tham số NULL hoặc điều kiện động xuất hiện

Ứng dụng thường cho phép người dùng chọn trạng thái đơn hoặc bỏ qua bộ lọc. Một mẫu dễ gây khó hiểu:

```sql
WHERE o.status = :selected_status
   OR :selected_status IS NULL
```

`:selected_status` là placeholder do framework cung cấp, **không phải cú pháp parameter của PostgreSQL khi gửi trực tiếp trong psql**.

Nếu tham số NULL, toàn bộ predicate có thể TRUE và giữ cả hàng NULL mở rộng. Nếu tham số là `PAID`, nó sẽ loại những khách không có PAID. Nghĩa là **bật/tắt bộ lọc có thể thay cả tập khách**.

### 22.1. Khi yêu cầu luôn giữ mọi khách

Nên đặt điều kiện status của đơn trong ON:

```sql
-- Khuôn mẫu prepared statement; $1 là tham số text.
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND ($1::text IS NULL OR o.status = $1::text)
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Với tham số `PAID`, câu query giữ mọi khách và chỉ ghép đơn PAID.

Với tham số NULL, điều kiện trở thành TRUE cho mọi đơn của khách, nên query ghép tất cả đơn — **không còn là một hàng cho mỗi khách**. Điều này cần được xác nhận với thiết kế API; đôi khi báo cáo nên có hai query hoặc luôn aggregate nếu muốn đúng một hàng mỗi khách.

### 22.2. Tránh nối tham số người dùng thành SQL

Trong JDBC, dùng `PreparedStatement` để bind giá trị status; đừng xây chuỗi như:

```text
"... ON ... AND o.status = '" + userInput + "'"
```

Nối trực tiếp dữ liệu vào SQL tạo rủi ro injection và lỗi escaping. Predicate vẫn phải được đặt đúng vị trí sau khi dùng parameter binding; **parameterization và ngữ nghĩa OUTER JOIN là hai vấn đề độc lập**.

## 23. Phân trang với LEFT JOIN: một khách có nhiều đơn

Một query như:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST
LIMIT 3;
```

chỉ giới hạn **3 hàng kết quả sau JOIN**, không phải “3 khách hàng”.

Trong dữ liệu mẫu, khách An có 2 đơn, nên ba hàng đầu có thể là:

```text
An - 1001
An - 1002
Bình - 1003
```

Chỉ có hai khách hàng khác nhau trong 3 hàng kết quả.

### 23.1. Nếu muốn phân trang theo khách hàng

Hãy chọn tập khách trước, rồi mới join:

```sql
WITH page_customers AS (
    SELECT
        customer_id,
        customer_name
    FROM join144.customers
    ORDER BY customer_id
    LIMIT 3 OFFSET 0
)
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM page_customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Tập trang đầu gồm khách 1, 2, 3, rồi phép LEFT JOIN giữ cả ba — một người có đơn PAID, hai người không có.

Điều kiện PAID nằm trong ON để trang khách không bị mất người.

### 23.2. COUNT tổng số khách cho phân trang

Nếu API muốn `total_customers`, đếm từ nguồn khách thỏa điều kiện nghiệp vụ, không mặc định:

```sql
SELECT COUNT(*)
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
  ON o.customer_id = c.customer_id;
```

Vì join một-nhiều, `COUNT(*)` ở đây trả **6** thay vì số khách **5**. Nếu mục tiêu là số khách:

```sql
SELECT COUNT(*) AS total_customers
FROM join144.customers;
```

Hoặc đếm từ tập khách đã lọc. Đừng dùng `COUNT(DISTINCT c.customer_id)` chỉ để che mọi vấn đề thiết kế; xác định rõ mức chi tiết của báo cáo.

## 24. Multi-tenant: điều kiện tenant ở ON có thể vẫn làm lộ hàng trái

Với ứng dụng nhiều tenant, đặt filter không đúng vị trí có thể không chỉ gây sai báo cáo mà còn làm **rò rỉ dữ liệu**.

Giả sử hai bảng dùng chung cho nhiều tổ chức:

```text
customers(tenant_id, customer_id, ...)
orders(tenant_id, order_id, customer_id, ...)
```

Một câu nguy hiểm:

```sql
-- Sai nếu mục tiêu là chỉ trả khách thuộc tenant được xác thực.
SELECT c.customer_id, c.customer_name, o.order_id
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
   AND o.tenant_id = $1;
```

Vấn đề:

1. Không có bộ lọc `c.tenant_id` ở phía bảng trái.
2. Vì là LEFT JOIN, **mọi khách của mọi tenant** vẫn được bảo toàn, chỉ có phần orders có thể NULL.
3. Điều kiện ghép còn thiếu tenant ID của khách, nên nếu customer ID chỉ duy nhất theo tenant, có thể ghép sai khách ở hai tenant khác nhau.

Một mẫu rõ hơn:

```sql
-- $1 là tenant_id đã xác thực và được phép truy cập.
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.tenant_id = $1;
```

Câu này tách ba mục tiêu:

- `WHERE c.tenant_id = $1` giới hạn **tập khách được trả về**.
- `ON o.tenant_id = c.tenant_id AND ...` giữ đúng quan hệ cùng tenant.
- `AND o.status = 'PAID'` trong ON chọn các đơn hợp lệ nhưng vẫn giữ mọi khách của tenant.

Tuy nhiên, **không dựa duy nhất vào WHERE** để bảo vệ dữ liệu: hệ thống cần xác thực tenant, phân quyền ứng dụng, khóa ghép đúng, và Row-Level Security (RLS) khi phù hợp. RLS là một lớp bảo vệ bổ sung; table owner, superuser và role có `BYPASSRLS` có các ngoại lệ quan trọng.

Các bảng `app.customers`/`app.orders` trong ví dụ này là mẫu kiến trúc; chúng không phải bảng tạo ở schema lab `join144`.

## 25. Outer join, view và thay đổi filter ở tầng ngoài

Giả sử bạn tạo một view báo cáo mọi khách hàng và đơn PAID:

```sql
CREATE VIEW join144.customer_paid_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    c.city,
    o.order_id,
    o.status
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Khi đọc:

```sql
SELECT *
FROM join144.customer_paid_orders
ORDER BY customer_id;
```

view giữ mọi khách hàng.

Nhưng người dùng view có thể thêm filter:

```sql
SELECT *
FROM join144.customer_paid_orders
WHERE order_id IS NOT NULL
ORDER BY customer_id;
```

Lúc này chỉ giữ những khách có đơn PAID. Điều đó không trái với định nghĩa view: bộ lọc của **truy vấn ngoài** vẫn được áp dụng lên kết quả logic của view.

### 25.1. Thiết kế view theo hợp đồng rõ ràng

Tên view nên diễn đạt:

- Nó gồm **tất cả khách** hay chỉ khách có đơn?
- Nó gồm **mỗi khách một hàng** hay một hàng cho mỗi đơn?
- NULL trong cột order nghĩa là **không có đơn PAID**, hay “không có đơn bất kỳ”?
- View có cài đặt phân quyền/RLS phù hợp không?

Một view có LEFT JOIN không tự bảo đảm các query phía ngoài luôn giữ mọi khách; ứng dụng vẫn phải đọc đúng ngữ nghĩa và tránh bộ lọc ngoài làm mất hàng ngoài ý muốn.

## 26. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Chuyển điều kiện bảng phải xuống WHERE

```sql
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
```

Làm mất khách không có đơn PAID.

**Sửa:** nếu muốn giữ mọi khách, đặt `o.status='PAID'` trong `ON` hoặc lọc nguồn orders trước khi LEFT JOIN.

### Lỗi 2 — Nghĩ OR o.id IS NULL giải quyết mọi trường hợp

```sql
WHERE o.status = 'PAID' OR o.order_id IS NULL
```

chỉ giữ khách có đơn PAID hoặc **hoàn toàn không có đơn**, không giữ khách chỉ có đơn khác PAID.

**Sửa:** xác định đúng yêu cầu; dùng predicate trong ON nếu cần giữ mọi khách.

### Lỗi 3 — Đặt điều kiện bảng trái vào ON với mục đích lọc bảng trái

```sql
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND c.city = 'Hà Nội'
```

không loại khách ngoài Hà Nội.

**Sửa:** dùng `WHERE c.city='Hà Nội'` hoặc nguồn c đã lọc trước.

### Lỗi 4 — Đếm các hàng NULL mở rộng bằng COUNT(*)

Với `LEFT JOIN`, khách không có đơn PAID vẫn có một hàng, nên `COUNT(*)` trả 1.

**Sửa:** `COUNT(o.order_id)` nếu `order_id` là khóa NOT NULL.

### Lỗi 5 — Dùng cột nullable để phát hiện không có đối tác

`WHERE o.optional_note IS NULL` có thể chọn đơn thật có ghi chú NULL.

**Sửa:** dùng khóa chính NOT NULL hoặc `NOT EXISTS`.

### Lỗi 6 — Nghĩ FULL JOIN với ON filter sẽ xóa hàng không hợp lệ

Trong FULL JOIN, một hàng WMS không thỏa predicate trong ON **vẫn có thể xuất hiện riêng**, vì phía WMS cũng được bảo toàn.

**Sửa:** nếu muốn loại hàng WMS không hợp lệ khỏi **tập đầu vào**, lọc bảng WMS bằng CTE/subquery trước khi FULL JOIN.

### Lỗi 7 — Thêm WHERE trên một phía sau FULL JOIN mà vẫn mong bảo toàn hai nguồn

Bộ lọc `WHERE w.verified=TRUE` loại các hàng chỉ có ERP vì `w.verified` NULL.

**Sửa:** dựa vào nghiệp vụ, hoặc lọc từng nguồn trước FULL JOIN, hoặc viết CASE/phân loại đúng.

### Lỗi 8 — Tưởng RIGHT JOIN đảo được bằng LEFT JOIN mà không đổi thứ tự bảng

`orders RIGHT JOIN customers` tương đương `customers LEFT JOIN orders`, không phải `orders LEFT JOIN customers`.

**Sửa:** xác định chính xác phía **được bảo toàn**.

### Lỗi 9 — Lạm dụng NOT IN để tìm hàng không tồn tại

`NOT IN (subquery)` có thể gặp lỗi logic khi subquery chứa NULL.

**Sửa:** `NOT EXISTS` hoặc `LEFT JOIN ... IS NULL` dựa trên khóa NOT NULL.

### Lỗi 10 — Không phân biệt “chưa có đơn” với “chưa có đơn PAID”

Hai câu hỏi tương ứng với hai điều kiện anti-join khác nhau.

**Sửa:** điều kiện trạng thái của đơn phải nằm **trong tập được kiểm tra tồn tại**, chẳng hạn trong ON hoặc subquery NOT EXISTS.

### Lỗi 11 — LEFT JOIN nhiều cấp rồi WHERE lọc bảng cuối

Một `WHERE p.payment_status='SETTLED'` có thể loại khách ngay cả khi `customers LEFT JOIN orders` ban đầu đã bảo toàn họ.

**Sửa:** làm rõ tập hợp quan hệ cần ghép và lọc nguồn đủ điều kiện trước.

### Lỗi 12 — Nhầm số hàng JOIN với số khách khi phân trang

`LIMIT 10` sau JOIN giới hạn **10 hàng kết quả**, có thể chỉ thuộc vài khách.

**Sửa:** phân trang tập khách trước, rồi JOIN các đơn liên quan.

### Lỗi 13 — Viết điều kiện nối thiếu khóa tenant

`o.customer_id=c.customer_id` có thể không đủ ở mô hình ID chỉ duy nhất trong từng tenant.

**Sửa:** thêm `o.tenant_id=c.tenant_id` vào ON và giới hạn bảng trái trong WHERE theo tenant xác thực.

### Lỗi 14 — Thêm DISTINCT để “sửa” hàng bị trùng

JOIN một-nhiều tạo nhiều cặp hợp lệ. `DISTINCT` có thể che lỗi hoặc loại những hàng trông giống nhau nhưng khác bản chất.

**Sửa:** xác định grain của báo cáo và aggregate đúng cấp độ.

### Lỗi 15 — Giả định ON được thực thi trước WHERE theo thứ tự vật lý cố định

Mô hình ON → null extension → WHERE là **ngữ nghĩa logic**, optimizer có thể tối ưu và đẩy predicate khi hợp lệ.

**Sửa:** đọc `EXPLAIN` nhưng không suy luận rằng mọi plan đều phản chiếu nguyên văn SQL.

### Lỗi 16 — Viết điều kiện sai dấu ngoặc

```sql
ON o.customer_id = c.customer_id
AND o.status = 'PAID'
OR o.amount > 1000
```

Theo ưu tiên toán tử, điều này được hiểu là:

```sql
ON (
    o.customer_id = c.customer_id
    AND o.status = 'PAID'
)
OR o.amount > 1000
```

Nhánh `OR o.amount > 1000` có thể ghép đơn với khách **không liên quan** nếu đơn đạt ngưỡng.

**Sửa:**

```sql
ON o.customer_id = c.customer_id
AND (
    o.status = 'PAID'
    OR o.amount > 1000
)
```

Từ khóa `AND`/`OR` cũng là một phần của việc định nghĩa **cặp hàng khớp**; sai ngoặc có thể dẫn đến ghép nhầm dữ liệu hàng loạt.

## 27. Bài tập thực hành có lời giải

Các bài tập sử dụng bộ dữ liệu lab ở phần 2 và phần 15.

### Bài 1 — Mọi khách hàng, đơn PAID nếu có

**Yêu cầu:** trả toàn bộ 5 khách, cột `order_id` NULL nếu không có đơn PAID.

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id;
```

**Đáp án:** An 1001; Bình NULL; Chi NULL; Dũng 1005; Hà NULL.

### Bài 2 — Chỉ khách có đơn PAID

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id;
```

**Đáp án:** An 1001 và Dũng 1005.

### Bài 3 — Chỉ khách chưa có đơn PAID

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Đáp án:** Bình, Chi, Hà.

### Bài 4 — Chỉ khách chưa có đơn bất kỳ

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

**Đáp án:** Hà.

### Bài 5 — Khách Hà Nội, đơn PAID nếu có

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.city = 'Hà Nội'
ORDER BY c.customer_id;
```

**Đáp án:** Bình NULL, Hà NULL.

### Bài 6 — Đặt city trong ON thì có lọc khách ngoài thành phố không?

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND c.city = 'Hà Nội'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

**Lời giải:** không. Tất cả 5 khách vẫn xuất hiện. Bình có đơn CANCELLED 1003 nên được ghép; Hà không có đơn; An, Chi, Dũng không thuộc Hà Nội nên có các cột order NULL.

### Bài 7 — Đếm số đơn PAID nhưng giữ cả khách số 0

```sql
SELECT c.customer_id,
       COUNT(o.order_id) AS paid_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** khách 1→1; 2→0; 3→0; 4→1; 5→0.

### Bài 8 — Đếm cả PAID và CANCELLED trong cùng hàng

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id)
      FILTER (WHERE o.status='PAID') AS paid_count,
    COUNT(o.order_id)
      FILTER (WHERE o.status='CANCELLED') AS cancelled_count
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** An (1,1), Bình (0,1), Chi (0,0), Dũng (1,0), Hà (0,0).

### Bài 9 — FULL JOIN, lấy SKU chỉ tồn tại một nguồn

```sql
SELECT e.sku AS erp_sku, w.sku AS wms_sku
FROM join144.erp_inventory AS e
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
WHERE e.sku IS NULL OR w.sku IS NULL
ORDER BY COALESCE(e.sku, w.sku);
```

**Đáp án:** A chỉ ERP, D chỉ WMS.

### Bài 10 — Tại sao điều kiện WMS trong ON không làm mất C?

Khi:

```sql
FULL JOIN join144.wms_inventory AS w
    ON e.sku = w.sku
   AND w.verified = TRUE
```

SKU C có `verified = FALSE` ở WMS.

**Lời giải:** C không được coi là cặp ghép, nhưng **cả hai nguồn đều được FULL JOIN bảo toàn**, nên hàng C từ ERP và hàng C từ WMS xuất hiện **riêng biệt**.

### Bài 11 — Sửa query mất khách do payment

Yêu cầu mọi khách, chỉ ghép đơn có thanh toán SETTLED.

**Lời giải:** tạo nguồn `settled_orders` bằng `INNER JOIN orders–payments ON p.order_id=o.order_id AND p.payment_status='SETTLED'`, sau đó `customers LEFT JOIN settled_orders`. Kết quả giữ đủ 5 khách.

### Bài 12 — Vì sao WHERE làm mất Chi?

```sql
LEFT JOIN join144.orders o ON o.customer_id=c.customer_id
WHERE o.status='PAID'
```

**Lời giải:** Chi có đơn PENDING, nên hàng ghép thật bị WHERE loại; không có hàng NULL thay thế vì LEFT JOIN đã tìm thấy đối tác trước khi lọc.

### Bài 13 — Khi nào dùng NOT EXISTS thay anti-join?

**Lời giải:** khi yêu cầu là “không tồn tại B thỏa một tập điều kiện”, `NOT EXISTS` thường diễn đạt ngắn gọn và không cần tìm cột NOT NULL của B để kiểm tra. Ví dụ tìm khách không có đơn PAID đã trình bày ở phần 13.3.

### Bài 14 — Tìm khách vừa có đơn CANCELLED vừa có đơn PAID

```sql
SELECT c.customer_id, c.customer_name
FROM join144.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
AND EXISTS (
    SELECT 1
    FROM join144.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'CANCELLED'
)
ORDER BY c.customer_id;
```

**Đáp án:** An. Dùng hai `EXISTS` giúp thể hiện rõ điều kiện tồn tại theo hai trạng thái khác nhau, tránh nhân hàng khi tự nối bảng orders hai lần.

### Bài 15 — Giải thích khác biệt hai câu filter

A:

```sql
LEFT JOIN join144.orders o
    ON o.customer_id=c.customer_id
   AND o.status='PAID'
```

B:

```sql
LEFT JOIN join144.orders o
    ON o.customer_id=c.customer_id
WHERE o.status='PAID'
   OR o.order_id IS NULL
```

**Lời giải:** A giữ mọi khách. B chỉ giữ những khách có đơn PAID hoặc không có đơn nào; Bình và Chi bị loại trong B.

### Bài 16 — Vì sao COUNT(*) = 1 khi không có đơn PAID?

**Lời giải:** `LEFT JOIN` giữ một hàng khách với các cột orders NULL mở rộng. `COUNT(*)` đếm hàng kết quả; `COUNT(o.order_id)` chỉ đếm đơn thật sự khớp.

### Bài 17 — Điều kiện AND/OR bị sai ngoặc

Câu:

```sql
ON o.customer_id=c.customer_id
AND o.status='PAID'
OR o.amount>1000
```

có thể ghép đơn hàng khác khách do nhánh OR.

**Lời giải:**

```sql
ON o.customer_id=c.customer_id
AND (o.status='PAID' OR o.amount>1000)
```

Luôn giữ điều kiện định danh đúng trong mọi nhánh logic.

### Bài 18 — Nếu query FULL JOIN có WHERE e.approved=TRUE thì còn mọi WMS không?

**Lời giải:** không. Những hàng chỉ tồn tại ở WMS có `e.approved NULL`, nên bị WHERE loại. Nếu muốn đối soát WMS với **tập ERP đã duyệt**, hãy lọc nguồn ERP trước rồi FULL JOIN với WMS.

## 28. Checklist khi review một truy vấn outer join

| Câu hỏi kiểm tra | Lý do |
|---|---|
| Phía nào phải được giữ đầy đủ? | Xác định LEFT, RIGHT hay FULL |
| Điều kiện nào xác định cặp hàng khớp? | Đặt trong ON |
| Điều kiện nào giới hạn tập bản ghi của phía được bảo toàn? | Đặt trong WHERE hoặc nguồn đã lọc |
| Bộ lọc WHERE có tham chiếu cột phía không được bảo toàn không? | Có thể loại null-extended rows |
| Có trường hợp chỉ có hàng không thỏa điều kiện nhưng vẫn cần giữ cha không? | Phân biệt lọc trong ON với OR ... IS NULL |
| Không có cặp ghép nghĩa là không có B, hay không có B đủ điều kiện? | Quyết định đúng diễn giải NULL |
| Đang đếm COUNT(*) hay COUNT(B.pk)? | Tránh đếm nhầm hàng null-extended |
| Có cần nhiều chỉ số trạng thái? | Cân nhắc aggregate FILTER |
| Có cần tìm A không có B phù hợp? | Dùng NOT EXISTS hoặc ON + B.pk IS NULL |
| FULL JOIN có lọc từng nguồn trước không? | Phân biệt bảo toàn nguồn gốc với bảo toàn nguồn đã chọn |
| Có LEFT JOIN nhiều cấp không? | WHERE ở bảng sau có thể xóa hàng của bảng đầu |
| Join có làm tăng số hàng không? | Kiểm soát fan-out trước khi LIMIT, SUM và COUNT |
| Khóa tenant có được lọc và ghép đầy đủ không? | Tránh rò rỉ và ghép chéo tổ chức |
| Giá trị NULL có thể có sẵn trong cột thật không? | Dùng khóa NOT NULL để phát hiện không khớp |
| Có ORDER BY rõ ràng không? | PostgreSQL không bảo đảm thứ tự nếu thiếu ORDER BY |
| Đã xác nhận kết quả đúng trước khi tối ưu chưa? | Đúng nghiệp vụ quan trọng hơn tên plan/index |

## 29. Bảng ghi nhớ nhanh

| Nhu cầu | Mẫu SQL | Kết quả chính |
|---|---|---|
| Giữ mọi khách, đơn PAID nếu có | `LEFT JOIN orders o ON o.customer_id=c.id AND o.status='PAID'` | Khách không có PAID vẫn hiện |
| Chỉ khách có đơn PAID | `LEFT JOIN ... ON ... WHERE o.status='PAID'` | Loại khách không có PAID |
| Chỉ khách trong thành phố X, đơn nếu có | `LEFT JOIN ... ON ... WHERE c.city='X'` | Giữ mọi khách thuộc X |
| Giữ mọi khách nhưng chỉ ghép đơn khi khách ở X | `LEFT JOIN ... ON ... AND c.city='X'` | Khách ngoài X vẫn hiện, đơn NULL |
| Khách chưa từng có đơn | `LEFT JOIN ... ON ... WHERE o.order_id IS NULL` | Chỉ khách không có đơn |
| Khách không có đơn PAID | `LEFT JOIN ... ON ... AND o.status='PAID' WHERE o.order_id IS NULL` | Gồm cả khách chỉ có CANCELLED |
| Thay anti-join | `WHERE NOT EXISTS (SELECT 1 FROM orders ... AND status='PAID')` | Diễn đạt điều kiện không tồn tại |
| Đếm đơn PAID, giữ số 0 | `COUNT(o.order_id)` sau LEFT JOIN lọc PAID trong ON | Không mất khách |
| Đếm nhiều trạng thái | `COUNT(o.order_id) FILTER (WHERE o.status='...')` | Một hàng báo cáo cho mỗi khách |
| Giữ mọi bản ghi hai hệ thống | `A FULL JOIN B ON A.key=B.key` | MATCH/ONLY_A/ONLY_B |
| FULL JOIN chỉ coi B verified là cặp khớp | `FULL JOIN B ON A.key=B.key AND B.verified` | B chưa verified vẫn có thể hiện riêng |
| Đối soát hai nguồn đã lọc | `FROM (SELECT ... WHERE ...) A FULL JOIN (SELECT ... WHERE ...) B` | Giữ toàn bộ tập nguồn sau lọc |
| Giữ mọi khách qua nhiều bảng | `customers LEFT JOIN (orders INNER JOIN payments đã lọc) ...` | Không mất khách khi payment thiếu |
| Giữ mọi bảng phải | `A RIGHT JOIN B ...` | Tương đương B LEFT JOIN A |
| Phân trang theo khách | Lọc/LIMIT khách trước, LEFT JOIN đơn sau | Không lấy nhầm số hàng đã join |
| Kiểm tra kế hoạch | `EXPLAIN SELECT ...` | Có thể tối ưu LEFT thành INNER nếu WHERE null-rejecting |

## 30. Tổng kết: nhớ “ON chọn cặp ghép, WHERE chọn hàng kết quả”

Ba phép outer join tạo khả năng **giữ hàng không có đối tác**:

- `LEFT JOIN` giữ phía trái.
- `RIGHT JOIN` giữ phía phải.
- `FULL JOIN` giữ cả hai phía.

Nhưng cơ chế bảo toàn đó có thể bị thay đổi ở bước **lọc kết quả**.

Đối chiếu lần cuối:

```sql
-- Mục tiêu 1: mọi khách hàng; chỉ đơn PAID nếu có.
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Truy vấn này giữ cả **Bình, Chi, Hà** dù họ không có đơn PAID.

```sql
-- Mục tiêu 2: chỉ khách hàng có đơn PAID.
SELECT c.customer_id, c.customer_name, o.order_id
FROM join144.customers AS c
LEFT JOIN join144.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Truy vấn này chỉ trả **An và Dũng**.

Không có câu nào luôn “tốt hơn” câu còn lại: **chúng trả lời hai câu hỏi nghiệp vụ khác nhau**.

Các quy tắc nên ghi nhớ:

1. **Điều kiện trong ON** quyết định một hàng có được ghép với hàng khác hay không; khi không ghép được, outer join vẫn có thể giữ phía cần bảo toàn bằng hàng NULL mở rộng.
2. **Điều kiện trong WHERE** lọc kết quả đã được nối; các predicate null-rejecting trên phía không được bảo toàn thường làm biến mất các hàng không ghép được.
3. **Điều kiện của bảng được bảo toàn trong ON không tự lọc bảng ấy.** Muốn bỏ hàng của bảng được bảo toàn, thường đặt bộ lọc ở WHERE hoặc lọc nguồn trước.
4. **FULL JOIN cần cẩn trọng ở cả hai phía.** Điều kiện ON có thể tách một cặp thành hai hàng đơn phương; WHERE có thể loại cả những hàng chỉ nằm ở một nguồn.
5. **COUNT(*) và COUNT(cột khóa của phía phải) khác nhau** khi có hàng NULL mở rộng; dùng aggregate FILTER cho nhiều chỉ số trạng thái.
6. **“Không có B” khác “không có B thỏa điều kiện”.** Anti-join với điều kiện trong ON hoặc NOT EXISTS giúp diễn đạt chính xác.
7. **Nhiều outer join có thể tương tác với nhau.** Bộ lọc ở bảng thứ ba, ORDER BY/LIMIT và fan-out có thể thay đổi toàn bộ báo cáo.
8. **Đúng ngữ nghĩa trước, tối ưu sau.** PostgreSQL có thể biến đổi plan khi điều đó giữ nguyên kết quả; index/EXPLAIN không sửa được một yêu cầu nghiệp vụ bị biểu diễn sai.

Nếu chỉ chọn một câu để nhớ, đó là: **`ON` quyết định “ghép với ai”; `WHERE` quyết định “giữ hàng kết quả nào”.** Với outer join, hai câu hỏi này không thể tùy tiện hoán đổi.

